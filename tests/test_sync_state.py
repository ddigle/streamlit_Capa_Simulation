# Purpose: 동기화 사이드카 상태와 변경 표시의 정상·예외 동작을 검증한다.

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from capa_simulation.persistence import sync_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_registry() -> object:
    sync_state.clear_all()
    yield
    sync_state.clear_all()


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "capa_simulation.duckdb"
    path.write_bytes(b"not a real duckdb, this module never opens it")
    return path


def test_marking_does_nothing_until_enabled(database: Path) -> None:
    """개발 PC·CI 에서 파일을 하나도 만들지 않아야 한다. 지금 동작이 그대로여야 한다."""
    sync_state.mark_dirty(database)
    sync_state.record_error(database, "무시되어야 한다")

    assert not sync_state.sidecar_path(database).exists()
    assert sync_state.is_enabled(database) is False


def test_mark_dirty_writes_only_for_registered_paths(database: Path, tmp_path: Path) -> None:
    other = tmp_path / "equipment_availability.duckdb"
    other.write_bytes(b"x")
    sync_state.enable({database: "simulation"})

    sync_state.mark_dirty(database)
    sync_state.mark_dirty(other)

    assert sync_state.read_state(database) is not None
    assert not sync_state.sidecar_path(other).exists()


def test_state_round_trips(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)

    state = sync_state.read_state(database)

    assert state is not None
    assert state.dataset == "simulation"
    assert state.dirty is True


def test_sidecar_path_is_gitignored() -> None:
    """사이드카가 커밋되면 남의 세대가 배포본에 실려 나간다."""
    result = subprocess.run(
        ["git", "check-ignore", "data/capa_simulation.duckdb.sync.json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0


def test_write_state_leaves_no_half_written_file(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)

    leftovers = [
        item
        for item in database.parent.iterdir()
        if item.name.startswith(sync_state.sidecar_path(database).name)
        and item != sync_state.sidecar_path(database)
    ]

    assert leftovers == []


def test_missing_or_broken_sidecar_is_treated_as_dirty(database: Path) -> None:
    """모르면 올리는 쪽이 안전하다. 모르면 건너뛰면 저장이 조용히 사라진다."""
    assert sync_state.treat_as_dirty(database) is True

    sync_state.enable({database: "simulation"})
    sync_state.sidecar_path(database).write_text("{ 깨진 JSON", encoding="utf-8")

    assert sync_state.read_state(database) is None
    assert sync_state.treat_as_dirty(database) is True


def test_unknown_sidecar_schema_is_not_guessed(database: Path) -> None:
    sync_state.sidecar_path(database).write_text(
        '{"schema": 99, "dataset": "simulation"}', encoding="utf-8"
    )

    assert sync_state.read_state(database) is None


def test_clear_dirty_clears_the_mark_it_saw(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)
    observed = sync_state.read_dirty_mark(database)

    assert sync_state.clear_dirty(database, observed=observed) is True

    state = sync_state.read_state(database)
    assert state is not None
    assert state.dirty is False
    assert sync_state.treat_as_dirty(database) is False


def test_heartbeat_is_throttled(database: Path) -> None:
    sync_state.enable({database: "simulation"})

    sync_state.touch_heartbeat(database, instance_id="first")
    sync_state.touch_heartbeat(database, instance_id="second")

    state = sync_state.read_state(database)
    assert state is not None
    # 10초 안의 두 번째 호출은 쓰지 않는다.
    assert state.instance_id == "first"


def test_live_instance_ignores_a_stale_heartbeat(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.touch_heartbeat(database, instance_id="ghost")
    state = sync_state.read_state(database)
    assert state is not None
    sync_state.write_state(
        database, type(state)(**{**state.__dict__, "heartbeat_utc": "2020-01-01T00:00:00Z"})
    )

    assert sync_state.live_instance(database) is None


def test_live_instance_reports_another_running_process(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    sync_state.touch_heartbeat(database, instance_id="other")

    assert sync_state.live_instance(database) == "other"
    assert sync_state.live_instance(database, exclude="other") is None


def test_adopting_a_clean_file_writes_even_without_enable(database: Path) -> None:
    """스크립트는 앱 밖에서 돈다. 받은 파일의 표시는 등록 없이도 남겨야 한다."""
    sync_state.adopt_clean(database, dataset="simulation")

    state = sync_state.read_state(database)
    assert state is not None
    assert state.dirty is False
    assert sync_state.treat_as_dirty(database) is False


def test_two_databases_are_marked_independently(tmp_path: Path) -> None:
    simulation = tmp_path / "capa_simulation.duckdb"
    equipment = tmp_path / "equipment_availability.duckdb"
    simulation.write_bytes(b"x")
    equipment.write_bytes(b"y")
    sync_state.enable({simulation: "simulation", equipment: "equipment"})

    sync_state.mark_dirty(simulation)

    assert sync_state.treat_as_dirty(simulation) is True
    equipment_state = sync_state.read_state(equipment)
    assert equipment_state is None or equipment_state.dirty is False


def test_registration_matches_the_same_file_through_a_different_path(tmp_path: Path) -> None:
    """저장소는 `resolve()` 한 경로를, 부트는 설정에 적힌 경로를 넘긴다.

    정규화하지 않으면 같은 파일인데 키가 달라 `_update` 가 조용히 아무 일도 하지 않는다.
    그러면 앱이 아무리 저장해도 변경 표시가 서지 않아 push 가 "올릴 것 없음" 으로 끝난다.
    """
    nested = tmp_path / "data" / "sub" / ".." / "capa_simulation.duckdb"
    nested.parent.parent.mkdir(parents=True, exist_ok=True)
    resolved = nested.resolve()
    resolved.write_bytes(b"x")

    sync_state.enable({nested: "simulation"})

    assert sync_state.is_enabled(resolved)
    sync_state.mark_dirty(resolved)
    assert sync_state.treat_as_dirty(resolved) is True


def test_each_mark_raises_the_change_counter_and_keeps_the_boolean(database: Path) -> None:
    """옛 코드는 `dirty` 불리언만 읽는다. 번호를 더해도 그 칸은 같은 뜻으로 남아야 한다."""
    sync_state.enable({database: "simulation"})

    for _ in range(3):
        sync_state.mark_dirty(database)

    state = sync_state.read_state(database)
    assert state is not None
    assert state.dirty_seq == 3
    assert state.dirty is True
    payload = json.loads(sync_state.sidecar_path(database).read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert payload["dirty"] is True


def test_clearing_keeps_a_mark_that_arrived_after_the_snapshot_was_taken(database: Path) -> None:
    """올리는 동안 들어온 저장은 그 스냅샷에 없다. 그 표시까지 지우면 다음 올리기가 빠뜨린다."""
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)
    observed = sync_state.read_dirty_mark(database)
    sync_state.mark_dirty(database)

    assert sync_state.clear_dirty(database, observed=observed) is False

    assert sync_state.treat_as_dirty(database) is True
    again = sync_state.read_dirty_mark(database)
    assert sync_state.clear_dirty(database, observed=again) is True
    assert sync_state.treat_as_dirty(database) is False


def test_a_file_written_by_an_old_build_is_read_from_the_boolean(database: Path) -> None:
    """번호가 없는 파일은 불리언에서 다시 세운다. 어긋나면 「변경 있음」 쪽을 따른다."""
    sync_state.sidecar_path(database).write_text(
        json.dumps({"schema": 1, "dataset": "simulation", "dirty": True}), encoding="utf-8"
    )

    state = sync_state.read_state(database)

    assert state is not None
    assert (state.dirty, state.dirty_seq, state.cleared_seq) == (True, 1, 0)


def test_adopting_a_clean_file_waits_for_the_sidecar_lock(database: Path) -> None:
    """잠금 밖에서 덮어쓰면 그 사이 들어온 변경 표시를 옛 내용으로 지운다."""
    finished = threading.Event()

    def adopt() -> None:
        sync_state.adopt_clean(database, dataset="simulation")
        finished.set()

    with sync_state._STATE_LOCK:
        worker = threading.Thread(target=adopt)
        worker.start()
        assert not finished.wait(0.3)
    worker.join(5)

    assert finished.is_set()


def test_a_mark_that_cannot_be_written_is_logged_and_still_counts(
    database: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """표시를 못 쓴 저장이 조용히 빠지면, 비교 후 지우기가 「그대로 N」 으로 보고 지운다."""
    sync_state.enable({database: "simulation"})
    sync_state.adopt_clean(database, dataset="simulation")
    observed = sync_state.read_dirty_mark(database)
    original = sync_state.write_state

    def disk_full(path: Path, state: sync_state.SyncState) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sync_state, "write_state", disk_full)
    with caplog.at_level("WARNING", logger=sync_state.__name__):
        sync_state.mark_dirty(database)

    assert any("변경 표시" in record.getMessage() for record in caplog.records)
    assert sync_state.unsaved_mark_error(database) is not None
    assert sync_state.treat_as_dirty(database) is True
    assert sync_state.has_pending_marks([database]) is True

    monkeypatch.setattr(sync_state, "write_state", original)
    assert not sync_state.clear_dirty(database, observed=observed)
    state = sync_state.read_state(database)
    assert state is not None and state.dirty is True


def test_the_listener_is_called_outside_the_sidecar_lock(database: Path) -> None:
    """저장 경로가 일꾼을 기다리지 않게 한다 — 리스너 안에서 그 잠금을 잡을 수 있어야 한다."""
    sync_state.enable({database: "simulation"})
    seen: list[bool] = []

    def listener() -> None:
        acquired = sync_state._STATE_LOCK.acquire(blocking=False)
        seen.append(acquired)
        if acquired:
            sync_state._STATE_LOCK.release()

    sync_state.set_listener(listener)
    sync_state.mark_dirty(database)

    assert seen == [True]


def test_a_failing_listener_does_not_reach_the_save(database: Path) -> None:
    sync_state.enable({database: "simulation"})

    def broken() -> None:
        raise RuntimeError("깨움 실패")

    sync_state.set_listener(broken)
    sync_state.mark_dirty(database)

    assert sync_state.treat_as_dirty(database) is True


def test_marks_remember_the_first_and_the_last_moment(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moments = iter([10.0, 25.0])
    monkeypatch.setattr(sync_state, "_monotonic", lambda: next(moments))
    sync_state.enable({database: "simulation"})

    sync_state.mark_dirty(database)
    sync_state.mark_dirty(database)

    clock = sync_state.mark_clock()
    assert (clock.first, clock.last) == (10.0, 25.0)
    assert clock.oldest == 10.0


def test_a_cycle_that_fails_puts_its_marks_back_as_the_oldest(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실패한 회차가 들고 간 표시를 잃으면 「5분 넘게 못 올림」 을 재지 못한다."""
    moments = iter([10.0, 50.0])
    monkeypatch.setattr(sync_state, "_monotonic", lambda: next(moments))
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)

    sync_state.begin_cycle()
    assert sync_state.mark_clock().first is None
    assert sync_state.mark_clock().oldest == 10.0
    sync_state.mark_dirty(database)
    sync_state.end_cycle(carried=False)

    clock = sync_state.mark_clock()
    assert clock.first == 10.0
    assert clock.carrying is None


def test_a_cycle_that_lands_keeps_only_the_marks_after_it(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moments = iter([10.0, 50.0])
    monkeypatch.setattr(sync_state, "_monotonic", lambda: next(moments))
    sync_state.enable({database: "simulation"})
    sync_state.mark_dirty(database)

    sync_state.begin_cycle()
    sync_state.mark_dirty(database)
    sync_state.end_cycle(carried=True)

    assert sync_state.mark_clock().first == 50.0


def test_leftover_marks_start_the_clock_only_once(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시작 때 남은 표시 · 놓친 깨우기를 만회한다. 이미 재고 있으면 늦추지 않는다."""
    moments = iter([3.0])
    monkeypatch.setattr(sync_state, "_monotonic", lambda: next(moments))

    sync_state.note_leftover_marks()
    sync_state.note_leftover_marks()

    assert sync_state.mark_clock().first == 3.0


def test_upload_request_is_ignored_where_nothing_is_registered() -> None:
    """개발 PC · CI 는 등록이 없다. 공식 발행이 아무 흔적도 남기지 않아야 한다."""
    calls: list[int] = []
    sync_state.set_listener(lambda: calls.append(1))

    sync_state.request_upload()

    assert sync_state.take_upload_request() is False
    assert calls == []


def test_upload_request_wakes_and_is_taken_once(database: Path) -> None:
    sync_state.enable({database: "simulation"})
    calls: list[int] = []
    sync_state.set_listener(lambda: calls.append(1))

    sync_state.request_upload()

    assert sync_state.upload_requested() is True
    assert sync_state.take_upload_request() is True
    assert sync_state.take_upload_request() is False
    assert calls == [1]


def test_a_missing_generation_file_differs_from_a_broken_one(tmp_path: Path) -> None:
    """새 디스크(없음)는 받으면 되고, 깨진 파일은 무엇을 잃었는지 모른다."""
    path = tmp_path / sync_state.GENERATION_FILENAME

    missing = sync_state.load_generation(path)
    path.write_text("{ 깨진 JSON", encoding="utf-8")
    broken = sync_state.load_generation(path)

    assert (missing.exists, missing.readable) == (False, True)
    assert (broken.exists, broken.readable) == (True, False)
    assert broken.state.base_pointer_key is None


def test_generation_state_round_trips_with_its_pending_marks(tmp_path: Path) -> None:
    path = tmp_path / sync_state.GENERATION_FILENAME
    state = sync_state.GenerationState(
        base_pointer_key="generations/heads/a.json",
        base_seq=7,
        base_pointer_json="{}",
        pending=sync_state.PendingPublish(
            pointer_key="generations/heads/b.json",
            pointer_json='{"seq": 8}',
            observed={"simulation": sync_state.DirtyMark(3, 1)},
        ),
        unpublished=sync_state.UnpublishedGeneration(
            pointer_json='{"seq": 9}',
            reason="moved",
            observed={"equipment": sync_state.DirtyMark(2, 0)},
        ),
        handed_over_utc="2026-11-07T00:00:00Z",
    )

    sync_state.write_generation(path, state)

    assert sync_state.read_generation(path) == state


def test_moving_the_base_keeps_the_handover_mark_and_drops_the_rest(tmp_path: Path) -> None:
    state = sync_state.GenerationState(
        handed_over_utc="2026-11-07T00:00:00Z",
        pending=sync_state.PendingPublish("k", "{}", {}),
    )

    moved = sync_state.with_base(state, pointer_key="k", seq=2, pointer_json="{}")

    assert moved.base_seq == 2
    assert moved.pending is None
    assert moved.handed_over_utc == "2026-11-07T00:00:00Z"
    assert moved.base_synced_at_utc is not None


def test_generation_file_path_sits_beside_the_databases_and_is_gitignored(
    database: Path,
) -> None:
    assert sync_state.generation_path(database).parent == database.parent
    result = subprocess.run(
        ["git", "check-ignore", "data/sync_generation.json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
