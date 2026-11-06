# Purpose: 동기화 일꾼의 시계·재시도·정리와 멈춤을 일꾼 밖에서 알아채는 판정을 검증한다.

"""스레드 없이 `tick` 을 돌려 시계를 본다. 시각은 가짜이고 표시 시각도 같은 시계를 쓴다."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError, dataclass, field, replace
from pathlib import Path

import pytest
from object_store_fakes import seed_pair

from capa_simulation import object_sync_worker as worker_module
from capa_simulation import settings as app_settings
from capa_simulation import sync_boot
from capa_simulation.io.object_storage import CommandResult, ObjectStorageError
from capa_simulation.object_sync_engine import (
    PruneOutcome,
    PublishOutcome,
    PublishStop,
    SyncPaths,
    WatchResult,
)
from capa_simulation.object_sync_worker import (
    FAILURE_BACKOFF_SECONDS,
    GATHER_SECONDS,
    OVERDUE_FAILURES,
    OVERDUE_SECONDS,
    PRUNE_EVERY_SECONDS,
    PRUNE_FIRST_SECONDS,
    PRUNE_LEFTOVER_SECONDS,
    QUIET_SECONDS,
    SOFT_RETRY_SECONDS,
    THREAD_NAME,
    TICK_STALE_SECONDS,
    WATCH_SECONDS,
    ObjectSyncWorker,
    SyncHealth,
    WorkerStatus,
    assess,
    running_worker,
    start_object_sync,
)
from capa_simulation.persistence import snapshot_export, sync_state
from capa_simulation.persistence.sync_state import MarkClock
from capa_simulation.services.object_storage_manifest import PrunePlan, PushDecision

CLEAN = PublishOutcome(decision=PushDecision.UP_TO_DATE)
UNREACHABLE = ObjectStorageError(
    "실패",
    result=CommandResult(("aws",), 255, "", "Could not connect to the endpoint URL", 0.0),
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class FakeEngine:
    """차례 셋을 기록하는 가짜. `results` 가 비면 깨끗한 회차다."""

    paths: SyncPaths
    results: list[PublishOutcome | BaseException] = field(default_factory=list)
    uploads: int = 0
    watches: list[WatchResult] = field(default_factory=list)
    watched: int = 0
    prunes: list[PruneOutcome | BaseException] = field(default_factory=list)
    pruned: int = 0
    during_upload: Callable[[], None] | None = None
    should_stop: Callable[[], bool] | None = None

    def upload(self) -> PublishOutcome:
        self.uploads += 1
        if self.during_upload is not None:
            self.during_upload()
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        return CLEAN

    def watch(self) -> WatchResult:
        self.watched += 1
        return self.watches.pop(0) if self.watches else WatchResult(PushDecision.UP_TO_DATE, 1)

    def prune(self, should_stop: Callable[[], bool]) -> PruneOutcome:
        self.pruned += 1
        self.should_stop = should_stop
        if self.prunes:
            result = self.prunes.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        return PruneOutcome(plan=PrunePlan(), deleted=0)


@dataclass
class Rig:
    clock: FakeClock
    engine: FakeEngine
    worker: ObjectSyncWorker
    paths: SyncPaths

    def mark(self) -> None:
        sync_state.mark_dirty(self.paths.databases["simulation"])

    def tick_at(self, offset: float) -> float:
        self.clock.now = 1_000.0 + offset
        return self.worker.tick()


@pytest.fixture()
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    sync_state.clear_all()
    clock = FakeClock()
    monkeypatch.setattr(sync_state, "_monotonic", clock)
    paths = seed_pair(tmp_path)
    sync_state.enable(paths.registry)
    for name, path in paths.databases.items():
        sync_state.adopt_clean(path, dataset=name)
    engine = FakeEngine(paths)
    yield Rig(clock, engine, ObjectSyncWorker(engine, clock=clock), paths)
    sync_state.clear_all()


def _settled(rig: Rig) -> None:
    """시작 직후의 HEAD 확인을 지나 보낸다 — 시계 시험의 앞을 맑게."""
    rig.worker.tick()
    assert rig.engine.watched == 1


def test_a_quiet_save_goes_up_twenty_seconds_later(rig: Rig) -> None:
    _settled(rig)
    rig.mark()

    rig.tick_at(QUIET_SECONDS - 1)
    assert rig.engine.uploads == 0

    rig.tick_at(QUIET_SECONDS)
    assert rig.engine.uploads == 1


def test_saves_that_keep_coming_go_up_by_sixty_seconds(rig: Rig) -> None:
    """저장이 이어져도 1분 안에 올리기를 시작한다."""
    _settled(rig)
    for offset in range(0, 60, 10):
        rig.clock.now = 1_000.0 + offset
        rig.mark()
        rig.worker.tick()
    assert rig.engine.uploads == 0

    rig.tick_at(GATHER_SECONDS)

    assert rig.engine.uploads == 1


def test_the_screen_sees_a_clean_state_right_after_a_cycle(rig: Rig) -> None:
    """다음 확인(최대 60초)까지 「올릴 것 있음」 이 남으면 CI/CD 앞에서 사람이 기다린다."""
    _settled(rig)
    path = rig.paths.databases["simulation"]
    rig.mark()
    sync_state.request_upload()

    def lands() -> None:
        sync_state.clear_dirty(path, observed=sync_state.read_dirty_mark(path))

    rig.engine.during_upload = lands

    rig.worker.tick()

    assert rig.worker.status().dirty == {"simulation": False, "equipment": False}


def test_an_official_release_goes_up_at_once(rig: Rig) -> None:
    _settled(rig)
    rig.mark()
    sync_state.request_upload()

    rig.worker.tick()

    assert rig.engine.uploads == 1


def test_a_request_during_a_cycle_runs_right_after_it(rig: Rig) -> None:
    _settled(rig)

    def save_and_ask() -> None:
        rig.mark()
        sync_state.request_upload()

    rig.engine.during_upload = save_and_ask
    sync_state.request_upload()

    pause = rig.worker.tick()

    assert rig.engine.uploads == 1
    rig.engine.during_upload = None
    assert pause <= QUIET_SECONDS
    rig.worker.tick()
    assert rig.engine.uploads == 2


def test_upload_now_clears_the_backoff(rig: Rig) -> None:
    """CI/CD 를 누르기 전의 단추다. 물러남을 기다리지 않는다."""
    _settled(rig)
    rig.engine.results.append(UNREACHABLE)
    sync_state.request_upload()
    rig.worker.tick()
    assert rig.worker.status().failures == 1

    rig.worker.request_now()
    rig.worker.tick()

    assert rig.engine.uploads == 2
    assert rig.worker.status().failures == 0


def test_upload_now_on_a_blocked_worker_judges_again(rig: Rig) -> None:
    _settled(rig)
    rig.engine.results.append(PublishOutcome(decision=PushDecision.PARENT_MOVED))
    sync_state.request_upload()
    rig.worker.tick()
    assert rig.worker.status().blocked == PushDecision.PARENT_MOVED.value

    rig.worker.request_now()
    rig.worker.tick()

    assert rig.engine.uploads == 2
    assert rig.worker.status().blocked is None


def test_failures_back_off_in_steps_and_stay_at_the_last(rig: Rig) -> None:
    _settled(rig)
    rig.mark()
    steps = (*FAILURE_BACKOFF_SECONDS, FAILURE_BACKOFF_SECONDS[-1])
    rig.engine.results.extend([UNREACHABLE] * (len(steps) + 1))
    rig.tick_at(QUIET_SECONDS)
    moment = QUIET_SECONDS
    for count, step in enumerate(steps, 1):
        assert rig.engine.uploads == count
        rig.tick_at(moment + step - 1)
        assert rig.engine.uploads == count
        rig.tick_at(moment + step)
        moment += step

    assert rig.engine.uploads == len(steps) + 1
    assert rig.worker.status().failure_kind == "unreachable"


def test_a_success_resets_the_failures(rig: Rig) -> None:
    _settled(rig)
    rig.engine.results.append(UNREACHABLE)
    sync_state.request_upload()
    rig.worker.tick()

    rig.tick_at(FAILURE_BACKOFF_SECONDS[0])

    status = rig.worker.status()
    assert status.failures == 0
    assert status.failure_kind is None


@pytest.mark.parametrize(
    "error",
    [snapshot_export.SnapshotBusy("잠금"), snapshot_export.SnapshotRaced("움직임")],
    ids=["busy", "raced"],
)
def test_a_busy_copy_is_tried_again_soon_and_is_not_a_failure(
    rig: Rig, error: BaseException
) -> None:
    _settled(rig)
    rig.engine.results.append(error)
    sync_state.request_upload()
    rig.worker.tick()

    assert rig.worker.status().failures == 0
    rig.tick_at(SOFT_RETRY_SECONDS)
    assert rig.engine.uploads == 2


def test_an_unconfirmed_pointer_is_looked_at_again_soon(rig: Rig) -> None:
    _settled(rig)
    rig.engine.results.append(PublishOutcome(decision=PushDecision.PUBLISH, confirm_deferred=True))
    sync_state.request_upload()
    rig.worker.tick()

    rig.tick_at(SOFT_RETRY_SECONDS)

    assert rig.engine.uploads == 2


@pytest.mark.parametrize(
    "decision",
    [
        PushDecision.PARENT_MOVED,
        PushDecision.FORKED,
        PushDecision.BLOCKED_UNPUBLISHED,
        PushDecision.REMOTE_EMPTY,
        PushDecision.UNKNOWN_BASE,
    ],
)
def test_a_blocked_decision_stops_uploading_and_rechecks_slowly(
    rig: Rig, decision: PushDecision
) -> None:
    _settled(rig)
    rig.engine.results.append(PublishOutcome(decision=decision))
    sync_state.request_upload()
    rig.worker.tick()
    assert rig.worker.status().blocked == decision.value
    rig.mark()

    rig.tick_at(299)
    assert rig.engine.uploads == 1

    rig.tick_at(300)
    assert rig.engine.uploads == 2


@pytest.mark.parametrize("stop", [PublishStop.REMOTE_MOVED, PublishStop.FORKED])
def test_a_generation_that_could_not_be_published_blocks(rig: Rig, stop: PublishStop) -> None:
    _settled(rig)
    rig.engine.results.append(PublishOutcome(decision=PushDecision.PUBLISH, stop=stop))
    sync_state.request_upload()

    rig.worker.tick()

    assert rig.worker.status().blocked == PushDecision.BLOCKED_UNPUBLISHED.value


def test_the_head_is_looked_at_on_start_and_every_ten_minutes(rig: Rig) -> None:
    """변경이 없으면 올리지 않는다. 보지 않으면 옛 데이터로 도는 줄 첫 저장까지 모른다."""
    rig.worker.tick()
    assert rig.engine.watched == 1

    rig.tick_at(WATCH_SECONDS - 1)
    assert rig.engine.watched == 1

    rig.tick_at(WATCH_SECONDS)
    assert rig.engine.watched == 2


def test_a_head_that_moved_while_idle_blocks(rig: Rig) -> None:
    rig.engine.watches.append(WatchResult(PushDecision.PARENT_MOVED, 9))

    rig.worker.tick()

    assert rig.worker.status().blocked == PushDecision.PARENT_MOVED.value


def test_a_failed_watch_does_not_stop_anything(rig: Rig) -> None:
    def broken() -> WatchResult:
        raise UNREACHABLE

    rig.engine.watch = broken  # type: ignore[method-assign]

    rig.worker.tick()

    assert rig.worker.status().failures == 0


def test_leftover_marks_are_picked_up_without_a_wake(rig: Rig) -> None:
    """시작 때 남은 표시 · 놓친 깨우기 — 파일만 보고도 올린다."""
    rig.worker.tick()
    path = rig.paths.databases["simulation"]
    state = sync_state.read_state(path)
    assert state is not None
    sync_state.write_state(
        path, type(state)(**{**state.__dict__, "dirty": True, "dirty_seq": state.dirty_seq + 1})
    )

    rig.tick_at(30)
    assert rig.engine.uploads == 0

    rig.tick_at(30 + QUIET_SECONDS)
    assert rig.engine.uploads == 1


def test_prune_runs_ten_minutes_after_start_then_daily(rig: Rig) -> None:
    rig.worker.tick()
    rig.tick_at(PRUNE_FIRST_SECONDS - 1)
    assert rig.engine.pruned == 0

    rig.tick_at(PRUNE_FIRST_SECONDS)
    rig.tick_at(PRUNE_FIRST_SECONDS + 1)
    assert rig.engine.pruned == 1

    rig.tick_at(PRUNE_FIRST_SECONDS + PRUNE_EVERY_SECONDS - 1)
    assert rig.engine.pruned == 1

    rig.tick_at(PRUNE_FIRST_SECONDS + PRUNE_EVERY_SECONDS + 1)
    rig.tick_at(PRUNE_FIRST_SECONDS + PRUNE_EVERY_SECONDS + 2)
    assert rig.engine.pruned == 2
    assert rig.worker.status().last_prune_utc is not None


def _tick_until_pruned(rig: Rig, offset: float) -> None:
    rig.tick_at(offset)
    if not rig.engine.pruned:
        rig.tick_at(offset + 1)


def test_a_prune_with_leftovers_comes_back_in_an_hour(rig: Rig) -> None:
    rig.worker.tick()
    rig.engine.prunes.append(PruneOutcome(plan=PrunePlan(deferred=5), deleted=200))
    _tick_until_pruned(rig, PRUNE_FIRST_SECONDS)

    pruned = rig.engine.pruned
    rig.tick_at(PRUNE_FIRST_SECONDS + PRUNE_LEFTOVER_SECONDS + 2)
    rig.tick_at(PRUNE_FIRST_SECONDS + PRUNE_LEFTOVER_SECONDS + 3)

    assert rig.engine.pruned == pruned + 1


def test_a_failed_prune_waits_for_tomorrow_and_blocks_nothing(rig: Rig) -> None:
    rig.worker.tick()
    rig.engine.prunes.append(UNREACHABLE)
    _tick_until_pruned(rig, PRUNE_FIRST_SECONDS)

    status = rig.worker.status()
    assert status.prune_failure == "unreachable"
    assert status.failures == 0


def test_prune_yields_to_an_upload_request(rig: Rig) -> None:
    rig.worker.tick()
    _tick_until_pruned(rig, PRUNE_FIRST_SECONDS)
    should_stop = rig.engine.should_stop
    assert should_stop is not None
    assert should_stop() is False

    sync_state.request_upload()

    assert should_stop() is True


def test_status_is_a_frozen_copy(rig: Rig) -> None:
    status = rig.worker.status()

    with pytest.raises(FrozenInstanceError):
        status.failures = 3  # type: ignore[misc]


def test_a_landed_generation_records_the_numbers(rig: Rig) -> None:
    _settled(rig)
    from capa_simulation.services import object_storage_manifest as manifest

    pointer = manifest.Pointer(
        schema=2,
        seq=7,
        pointer_key="k",
        parent_seq=6,
        parent_pointer_key="p",
        origin="app",
        members={},
        app_version="demo",
        author="demo",
        created_at_utc="2026-11-07T00:00:00Z",
        note="",
    )
    rig.engine.results.append(
        PublishOutcome(
            decision=PushDecision.PUBLISH,
            published=True,
            pointer=pointer,
            lock_seconds=0.12,
            transfer_seconds=3.4,
        )
    )
    sync_state.request_upload()

    rig.worker.tick()

    status = rig.worker.status()
    assert status.seq == 7
    assert status.last_success_utc is not None
    assert status.lock_seconds == 0.12
    assert status.transfer_seconds == 3.4


def _status(**changes: object) -> WorkerStatus:
    status = WorkerStatus(alive=True, phase=worker_module.PHASE_IDLE, last_tick=1_000.0)
    return replace(status, **changes)  # type: ignore[arg-type]


NOW = 1_010.0


@pytest.mark.parametrize(
    ("status", "marks", "now", "expected"),
    [
        (None, MarkClock(), NOW, SyncHealth("실패", overdue="worker_absent")),
        (_status(alive=False), MarkClock(), NOW, SyncHealth("실패", overdue="worker_absent")),
        (
            _status(),
            MarkClock(),
            1_000.0 + TICK_STALE_SECONDS + 1,
            SyncHealth("실패", overdue="worker_absent"),
        ),
        (
            _status(
                phase=worker_module.PHASE_UPLOADING, cycle_started=1_000.0, cycle_deadline=1_500.0
            ),
            MarkClock(carrying=900.0),
            1_501.0,
            SyncHealth("실패", overdue="worker_absent"),
        ),
        (
            _status(
                phase=worker_module.PHASE_UPLOADING, cycle_started=1_000.0, cycle_deadline=9_000.0
            ),
            MarkClock(carrying=100.0),
            1_500.0,
            SyncHealth("올리는 중"),
        ),
        (
            _status(blocked="parent_moved"),
            MarkClock(),
            NOW,
            SyncHealth("멈춤", blocked="parent_moved"),
        ),
        (
            _status(failures=OVERDUE_FAILURES, failure_kind="denied"),
            MarkClock(),
            NOW,
            SyncHealth("실패", overdue="denied"),
        ),
        (
            _status(last_tick=NOW),
            MarkClock(first=NOW - OVERDUE_SECONDS - 1, last=NOW),
            NOW,
            SyncHealth("실패", overdue="other"),
        ),
        (
            _status(last_tick=NOW),
            MarkClock(first=NOW - 5, last=NOW),
            NOW,
            SyncHealth("올릴 것 있음"),
        ),
        (_status(dirty={"simulation": True}), MarkClock(), NOW, SyncHealth("올릴 것 있음")),
        (_status(), MarkClock(), NOW, SyncHealth("올릴 것 없음")),
    ],
    ids=[
        "no-worker",
        "dead-thread",
        "stale-tick",
        "hung-cycle",
        "long-upload-is-progress",
        "blocked",
        "three-failures",
        "five-minutes-late",
        "fresh-mark",
        "dirty-on-disk",
        "clean",
    ],
)
def test_health_is_judged_outside_the_worker(
    status: WorkerStatus | None, marks: MarkClock, now: float, expected: SyncHealth
) -> None:
    """멈춘 일꾼의 값도 함께 멈춘다. 판정은 지금 시각과 스레드 객체로 한다."""
    assert assess(status, marks, now) == expected


def test_a_dead_worker_is_seen_even_though_its_status_stopped(rig: Rig) -> None:
    """저장은 계속 들어오고 일꾼은 없다 — 첫 미반영 시각은 일꾼 밖에 있다."""
    rig.mark()

    status = rig.worker.status()

    assert status.alive is False
    assert assess(status, sync_state.mark_clock(), rig.clock.now).overdue == "worker_absent"


class _EndlessEngine(FakeEngine):
    """고리가 도는지 세는 가짜 — 실패를 던지고도 다시 불리는지 본다."""

    def upload(self) -> PublishOutcome:
        self.uploads += 1
        if self.uploads == 1:
            raise SystemExit(3)
        return CLEAN


@pytest.fixture()
def real_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    sync_state.clear_all()
    sync_boot.forget_boot_result()
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    yield tmp_path
    worker = running_worker()
    if worker is not None:
        worker.stop(5)
    sync_state.clear_all()
    sync_boot.forget_boot_result()


def _wait_for(condition: Callable[[], bool], seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def test_the_app_has_two_background_threads_and_no_more() -> None:
    """예약 하나와 일꾼 하나뿐이다. 스레드를 더하면 AGENTS 9장 규칙을 그 자리에서 고친다."""
    root = Path(__file__).resolve().parents[1]
    sources = [root / "app.py", root / "capa_server.py"]
    sources += sorted((root / "app_pages").rglob("*.py"))
    sources += sorted((root / "src").rglob("*.py"))

    found = sorted(
        path.relative_to(root).as_posix()
        for path in sources
        if "threading.Thread(" in path.read_text(encoding="utf-8")
    )

    assert found == [
        "src/capa_simulation/auto_update_scheduler.py",
        "src/capa_simulation/object_sync_worker.py",
    ]


def test_the_loop_survives_what_a_cycle_raises(real_thread: Path) -> None:
    """스레드가 죽으면 저장이 안 올라간다. `SystemExit` 도 고리 밖으로 새지 않는다."""
    paths = seed_pair(real_thread)
    sync_state.enable(paths.registry)
    engine = _EndlessEngine(paths)
    worker = ObjectSyncWorker(engine)
    worker.start()
    try:
        worker.request_now()
        assert _wait_for(lambda: worker.status().failures == 1)
        worker.request_now()
        assert _wait_for(lambda: engine.uploads >= 2)
        assert worker.status().alive is True
    finally:
        worker.stop(5)


def test_a_save_wakes_the_thread(real_thread: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_module, "QUIET_SECONDS", 0.0)
    paths = seed_pair(real_thread)
    sync_state.enable(paths.registry)
    engine = FakeEngine(paths)
    worker = ObjectSyncWorker(engine)
    worker.start()
    try:
        assert _wait_for(lambda: engine.watched == 1)
        sync_state.mark_dirty(paths.databases["simulation"])
        assert _wait_for(lambda: engine.uploads == 1)
    finally:
        worker.stop(5)


def _managed(monkeypatch: pytest.MonkeyPatch) -> None:
    from capa_simulation.io import object_storage

    settings = object_storage.StorageSettings(
        mode="managed",
        endpoint_url="http://example.invalid:9020",
        bucket="Demo_bucket",
        profile="demo",
        region="us-east-1",
        capabilities={},
    )
    monkeypatch.setattr(sync_boot, "load_settings", lambda: settings)


def _boot_record() -> sync_boot.BootRecord:
    return sync_boot.BootRecord(
        action="downloaded",
        seq=2,
        previous_upload_utc="2026-11-07T00:00:00Z",
        pull_seconds=1.5,
        finished_at_utc="2026-11-07T00:00:02Z",
    )


def test_no_worker_stands_in_local_mode(real_thread: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """개발 · 사내 PC · 시험의 스레드 목록이 그대로여야 한다."""
    sync_boot.write_boot_record(_boot_record())

    assert start_object_sync(build_engine=lambda: pytest.fail("서면 안 됨")) is None
    assert THREAD_NAME not in {thread.name for thread in threading.enumerate()}


def test_no_worker_stands_without_a_boot_record(
    real_thread: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """받기를 지나지 않은 앱이다 — `app.py` 개발 실행 · `managed` 를 켠 사내 PC."""
    _managed(monkeypatch)

    assert start_object_sync(build_engine=lambda: pytest.fail("서면 안 됨")) is None


def test_one_worker_stands_per_process(real_thread: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    sync_boot.write_boot_record(_boot_record())
    paths = seed_pair(real_thread)

    first = start_object_sync(build_engine=lambda: FakeEngine(paths))
    second = start_object_sync(build_engine=lambda: pytest.fail("둘째가 서면 안 됨"))

    assert first is not None
    assert second is first
    names = [thread.name for thread in threading.enumerate()]
    assert names.count(THREAD_NAME) == 1


def test_a_worker_that_cannot_start_does_not_stop_the_app(
    real_thread: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _managed(monkeypatch)
    sync_boot.write_boot_record(_boot_record())

    def broken() -> FakeEngine:
        raise RuntimeError("시작 실패")

    assert start_object_sync(build_engine=broken) is None
