# Purpose: 감사 스풀 · 읽기 — 동시 넣기의 빈틈 없는 순번, 남은 스풀, UTC 날짜 경계, 지우는 때, 겹침.

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from capa_simulation.audit import chain, layout, read, recorder, spool

INST = "a1b2c3d4e5f6"


class Clock:
    def __init__(self, start: datetime) -> None:
        self.moment = start
        self.lock = threading.Lock()

    def __call__(self) -> datetime:
        with self.lock:
            return self.moment


@pytest.fixture()
def clock(tmp_path: Path) -> Iterator[Clock]:
    ticking = Clock(datetime(2026, 11, 13, 7, 0, tzinfo=timezone.utc))
    spool.configure(tmp_path)
    recorder.start(env="cdep", version="test", inst=INST, clock=ticking)
    yield ticking


def test_an_off_recorder_drains_nothing_and_writes_no_file(tmp_path: Path) -> None:
    spool.configure(tmp_path)

    assert spool.drain() == 0
    assert not (tmp_path / spool.SPOOL_DIR).exists()


def test_an_empty_queue_touches_no_file(clock: Clock, tmp_path: Path) -> None:
    assert spool.drain() == 0
    assert not (tmp_path / spool.SPOOL_DIR).exists()


def test_two_threads_recording_and_draining_leave_no_gap(clock: Clock, tmp_path: Path) -> None:
    def work(name: str) -> None:
        for index in range(200):
            recorder.record("session_created", actor=f"demo.{name}", sid8=f"{index:08d}")
            if index % 17 == 0:
                spool.drain()

    threads = [threading.Thread(target=work, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    spool.drain()

    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, tmp_path))
    assert [line["seq"] for line in lines] == list(range(1, 401))
    assert chain.verify(lines) == ()
    assert spool.last_sealed() == (400, lines[-1]["h"])


def test_lines_split_at_the_utc_date_and_the_kst_day_reads_both(
    clock: Clock, tmp_path: Path
) -> None:
    clock.moment = datetime(2026, 11, 13, 23, 59, 59, 999000, tzinfo=timezone.utc)
    recorder.record("session_created", actor="demo.late")
    clock.moment = datetime(2026, 11, 14, 0, 0, 0, tzinfo=timezone.utc)
    recorder.record("session_created", actor="demo.early")
    spool.drain()

    first = spool.read_lines(spool.spool_path("2026-11-13", INST, tmp_path))
    second = spool.read_lines(spool.spool_path("2026-11-14", INST, tmp_path))
    assert [line["actor"] for line in first] == ["demo.late"]
    assert [line["actor"] for line in second] == ["demo.early"]
    assert chain.verify([*first, *second]) == ()
    # KST 11-14 하루는 UTC 11-13 15:00 ~ 11-14 15:00 이다 — 두 줄 다 그 안이다.
    assert read.utc_dates(date(2026, 11, 14), date(2026, 11, 14)) == ["2026-11-13", "2026-11-14"]
    rows = read.load_lines(tmp_path, date(2026, 11, 14), date(2026, 11, 14))
    assert [row["actor"] for row in rows] == ["demo.late", "demo.early"]
    assert read.kst_text(rows[0]["ts"]) == "2026-11-14 08:59:59"
    assert read.load_lines(tmp_path, date(2026, 11, 13), date(2026, 11, 13)) == []


def test_a_leftover_spool_of_a_dead_instance_is_read_after_a_restart(
    clock: Clock, tmp_path: Path
) -> None:
    recorder.record("session_created", actor="demo.before")
    spool.drain()
    recorder.reset()
    spool.reset()
    recorder.start(env="cdep", version="test", inst="ffffffffffff", clock=clock)
    clock.moment += timedelta(minutes=1)
    recorder.record("session_created", actor="demo.after")
    spool.drain()

    rows = read.load_lines(tmp_path, date(2026, 11, 13), date(2026, 11, 13))
    assert [(row["inst"], row["seq"], row["actor"]) for row in rows] == [
        (INST, 1, "demo.before"),
        ("ffffffffffff", 1, "demo.after"),
    ]


def test_a_past_spool_stays_until_its_daily_file_is_in_the_mirror(
    clock: Clock, tmp_path: Path
) -> None:
    recorder.record("session_created", actor="demo.user")
    spool.drain()
    path = spool.spool_path("2026-11-13", INST, tmp_path)
    spool.mark_shipped(path, 1)

    assert spool.prune([], tmp_path) == []
    assert spool.prune(["2026-11-12"], tmp_path) == []
    assert path.exists()

    assert spool.prune(["2026-11-13"], tmp_path) == [path]
    assert not path.exists()


def test_an_unshipped_line_keeps_the_spool_even_with_a_daily_file(
    clock: Clock, tmp_path: Path
) -> None:
    recorder.record("session_created", actor="demo.user")
    recorder.record("session_logout", actor="demo.user")
    spool.drain()
    path = spool.spool_path("2026-11-13", INST, tmp_path)
    spool.mark_shipped(path, 1)

    assert [line["seq"] for line in spool.unshipped_lines(path)] == [2]
    assert spool.prune(["2026-11-13"], tmp_path) == []
    assert spool.unshipped_count() == 1


def test_a_daily_file_wins_and_the_same_line_twice_is_read_once(
    clock: Clock, tmp_path: Path
) -> None:
    recorder.record("session_created", actor="demo.user")
    recorder.record("session_logout", actor="demo.user")
    spool.drain()
    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, tmp_path))
    piece = layout.mirror_path(tmp_path, layout.piece_key("seg", "2026-11-13", INST, 1, 2))
    piece.parent.mkdir(parents=True)
    piece.write_bytes(layout.encode_lines(lines))

    rows = read.load_lines(tmp_path, date(2026, 11, 13), date(2026, 11, 13))
    assert [row["seq"] for row in rows] == [1, 2]

    daily = layout.mirror_path(tmp_path, layout.daily_key("2026-11-13", 0))
    daily.parent.mkdir(parents=True)
    daily.write_bytes(layout.encode_lines(lines[:1]))
    assert read.files_for(tmp_path, "2026-11-13") == [daily]
    rows = read.load_lines(tmp_path, date(2026, 11, 13), date(2026, 11, 13))
    assert [row["seq"] for row in rows] == [1]


def test_a_failed_write_puts_the_lines_back_without_a_gap(
    clock: Clock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder.record("session_created", actor="demo.one")
    real = spool._append

    def broken(path: Path, lines: list[dict[str, object]]) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(spool, "_append", broken)
    assert spool.drain() == 0
    assert recorder.pending_count() == 1
    monkeypatch.setattr(spool, "_append", real)
    recorder.record("session_logout", actor="demo.one")
    assert spool.drain() == 2

    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, tmp_path))
    assert [(line["seq"], line["ev"]) for line in lines] == [
        (1, "session_created"),
        (2, "session_logout"),
    ]
    assert chain.verify(lines) == ()


def test_the_fingerprint_changes_when_a_file_grows(clock: Clock, tmp_path: Path) -> None:
    day = date(2026, 11, 13)
    before = read.fingerprint(tmp_path, day, day)
    recorder.record("session_created", actor="demo.user")
    spool.drain()
    middle = read.fingerprint(tmp_path, day, day)
    recorder.record("session_logout", actor="demo.user")
    spool.drain()

    after = read.fingerprint(tmp_path, day, day)
    assert before != middle != after
    assert after == read.fingerprint(tmp_path, day, day)


def test_the_default_root_is_under_data_temp_but_tests_are_elsewhere() -> None:
    from capa_simulation import settings

    configured = spool.configured()
    assert configured is not None
    assert settings.DATA_DIR not in configured.parents
    spool.configure(None)
    try:
        assert spool.root() == settings.DATA_DIR / "temp" / "audit"
    finally:
        spool.configure(configured)
