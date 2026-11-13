# Purpose: 감사 스풀 · 읽기 — 동시 넣기의 빈틈 없는 순번, 남은 스풀, UTC 날짜 경계, 지우는 때, 겹침.

from __future__ import annotations

import errno
import threading
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from io import FileIO
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


def test_a_lone_surrogate_in_a_claim_name_never_costs_the_batch(
    clock: Clock, tmp_path: Path
) -> None:
    """IdP 이름 클레임의 짝 없는 서로게이트 — 기록기가 U+FFFD 로 고쳐 같은 묶음의 줄이 모두
    적힌다."""
    for _ in range(3):
        recorder.record("session_created", actor="demo.one")
    recorder.from_sso_event(
        "login_ok", {"loginid": "demo.two", "sid": "sid12345"}, {"name": "DEMO\ud800"}
    )
    recorder.record("session_created", actor="demo.three")

    assert spool.drain() == 5

    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, tmp_path))
    assert [line["seq"] for line in lines] == [1, 2, 3, 4, 5]
    assert lines[3]["name"] == "DEMO\ufffd"
    assert chain.verify(lines) == ()


def test_a_line_that_cannot_be_sealed_is_repaired_or_counted_never_lost_silently(
    clock: Clock, tmp_path: Path
) -> None:
    """기록기를 거치지 않고 큐에 든 줄도 — 서로게이트는 고쳐 적고, 적을 수 없는 줄은 순번을 쓰지
    않고 버린 수로 센다. 나머지 줄은 빈틈 없이 적힌다."""
    good = recorder.build_line("session_created", out="success", who=recorder.NOBODY)
    surrogate = {**good, "tgt": {"type": "scenario", "id": "s-1", "label": "깨진\udc80글"}}
    unserializable = {**good, "det": {"rows": object()}}
    recorder.requeue_front([good, surrogate, unserializable, good])

    assert spool.drain() == 3
    assert spool.drain() == 1

    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, tmp_path))
    assert [line["seq"] for line in lines] == [1, 2, 3, 4]
    assert lines[1]["tgt"]["label"] == "깨진\ufffd글"
    assert lines[3]["ev"] == "sys_audit_dropped" and lines[3]["det"] == {"count": 1}
    assert chain.verify(lines) == ()
    assert recorder.dropped_total() == 1


def test_any_failure_while_writing_puts_the_lines_back(
    clock: Clock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder.record("session_created", actor="demo.one")
    real = spool._append

    def broken(path: Path, lines: list[dict[str, object]]) -> None:
        raise RuntimeError("뜻밖의 실패")

    monkeypatch.setattr(spool, "_append", broken)
    assert spool.drain() == 0
    assert recorder.pending_count() == 1
    monkeypatch.setattr(spool, "_append", real)
    assert spool.drain() == 1
    assert spool.last_sealed()[0] == 1


def test_a_partial_write_on_a_full_disk_is_cut_back_and_no_seq_is_lost(
    clock: Clock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """디스크가 차 묶음의 앞 40바이트만 적히고 실패해도 — 꼬리를 되잘라 다음 비우기가 같은 순번을
    온전히 다시 적는다."""
    recorder.record("session_created", actor="demo.first")
    assert spool.drain() == 1
    real = spool._write_all

    def partial(handle: FileIO, payload: bytes) -> None:
        handle.write(payload[:40])
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(spool, "_write_all", partial)
    recorder.record("session_created", actor="demo.second")
    assert spool.drain() == 0
    monkeypatch.setattr(spool, "_write_all", real)
    recorder.record("session_created", actor="demo.third")
    assert spool.drain() == 2

    path = spool.spool_path("2026-11-13", INST, tmp_path)
    lines = spool.read_lines(path)
    assert [(line["seq"], line["actor"]) for line in lines] == [
        (1, "demo.first"),
        (2, "demo.second"),
        (3, "demo.third"),
    ]
    assert [line["seq"] for line in spool.unshipped_lines(path)] == [1, 2, 3]
    assert chain.verify(lines) == ()


def test_a_tail_left_without_a_newline_does_not_swallow_the_next_line(
    clock: Clock, tmp_path: Path
) -> None:
    """되자르기마저 실패해 반쪽 꼬리가 남은 파일 — 다음 덧붙이기가 줄바꿈부터 적어 새 줄은
    온전하다."""
    recorder.record("session_created", actor="demo.first")
    spool.drain()
    path = spool.spool_path("2026-11-13", INST, tmp_path)
    with path.open("ab") as handle:
        handle.write(b'{"seq":2,"ev":"session_cre')
    recorder.record("session_created", actor="demo.second")

    assert spool.drain() == 1

    assert [line["actor"] for line in spool.read_lines(path)] == ["demo.first", "demo.second"]


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
