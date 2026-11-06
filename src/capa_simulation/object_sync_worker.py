# Purpose: 저장을 모아 세대를 올리고 공식 발행은 바로 올리며 하루 한 번 정리하는 배경 스레드를 둔다.

"""동기화 일꾼 — 앱 프로세스 안 둘째 배경 스레드(`capa-object-sync`).

C-DEP 운영 서버는 영속 볼륨이 없고 끌 때 올릴 기회도 없다. 그래서 저장 뒤 스스로 정본 버킷에
올린다. 차례(`object_sync_engine`)를 부르는 **시계**가 이 모듈의 몫이다.

| 때 | 시작 |
|---|---|
| 평소 | `min(첫 표시 + 60초, 마지막 표시 + 20초)` |
| 공식 발행 · 「지금 올리기」 | 곧바로 |
| 회차 도는 중 요청 | 끝나자마자 다음 회차 |
| 실패 | 30 · 60 · 120 · 300초, 이후 300초 |
| 판정 막힘 | 올리지 않고 300초마다 다시 판정 |
| 쉬는 동안 | 시작 직후 · 10분마다 HEAD 를 본다 |
| 정리 | 시작 10분 뒤 첫 번, 이후 24시간마다(남으면 1시간 뒤) |

**언제 서나.** `capa_server.py` 가 `start_sso()` 뒤 `start_object_sync()` 를 부른다. 첫 접속을
기다리지 않는다 — 찾아오는 사람이 없는 날도 정리가 돈다. 조건은 `managed` + 시작 때의 받기가 남긴
부트 기록이다(`sync_boot`). 그래서 `app.py` 개발 실행 · 사내 PC · 시험에서는 서지 않는다.

**프로세스에 하나.** 스레드 이름(`THREAD_NAME`) + 시작 잠금 — `auto_update_scheduler` 와 같은
꼴이고 `st.cache_resource` 를 쓰지 않는다. **Streamlit 을 import 하지 않는다**(시험이 하위
프로세스로 본다). 캐시를 건드리지 않는다 — 저장 내용이 안 바뀐다.

**잠**: 일 없으면 `Event.wait(60초)`. `sync_state` 가 표시 때 리스너로 깨운다. 깨우기를 놓쳐도 60초
안에 표시를 다시 읽는다. **상태 잠금은 IO 동안 쥐지 않는다** — 화면이 일꾼을 기다리지 않게.

**멈춤을 판정하는 쪽은 일꾼 밖이다**(`assess`). 첫 미반영 시각은 `sync_state` 메모리에 있고 살아
있는지는 스레드 객체가 답한다. 일꾼이 만드는 값만 보면 멈춘 일꾼의 값도 함께 멈춘다.

**실패가 스레드를 죽이지 않는다.** 예상한 실패는 갈래로 적고 물러난다. 고리 바깥에서 `BaseException`
까지 받아 기록하고 계속한다.

자식 프로세스(`aws`)는 `subprocess.run` 기본(`close_fds=True`)이라 듣는 소켓을 물려받지 않고,
Python 3.10 은 vfork 를 쓰므로 앱 메모리를 복제하지 않는다.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, cast

from capa_simulation import sync_boot
from capa_simulation.io.object_storage import (
    ObjectStorageClient,
    classify_failure,
    load_settings,
    transfer_timeout_seconds,
)
from capa_simulation.object_sync_engine import (
    ExportedSnapshot,
    Exporter,
    PruneOutcome,
    PublishOutcome,
    PublishStop,
    SyncPaths,
    WatchResult,
    default_paths,
    prune,
    publish_generation,
    watch_head,
)
from capa_simulation.persistence import sync_state
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.persistence.snapshot_export import SnapshotBusy, SnapshotRaced
from capa_simulation.persistence.sync_state import MarkClock
from capa_simulation.services.object_storage_manifest import (
    BLOCKING_PUSH,
    DATASET_NAMES,
    FAILURE_OTHER,
    FAILURE_WORKER_ABSENT,
    DatasetName,
    PushDecision,
)

_LOGGER = logging.getLogger(__name__)

THREAD_NAME: Final = "capa-object-sync"
QUIET_SECONDS: Final = 20.0
GATHER_SECONDS: Final = 60.0
FAILURE_BACKOFF_SECONDS: Final = (30.0, 60.0, 120.0, 300.0)
SOFT_RETRY_SECONDS: Final = 30.0
BLOCKED_RECHECK_SECONDS: Final = 300.0
WATCH_SECONDS: Final = 600.0
PRUNE_FIRST_SECONDS: Final = 600.0
PRUNE_EVERY_SECONDS: Final = 86_400.0
PRUNE_LEFTOVER_SECONDS: Final = 3_600.0
# 일 없어도 깨어나 표시를 다시 읽는 간격. 깨우기를 놓친 표시와 시작 때 남은 표시를 만회한다.
WAKE_SECONDS: Final = 60.0
# 이 안에 고리가 돌지 않으면 일꾼이 멈춘 것이다.
TICK_STALE_SECONDS: Final = 3 * WAKE_SECONDS
OVERDUE_FAILURES: Final = 3
OVERDUE_SECONDS: Final = 300.0
# 회차 제한 시간의 여유. 스냅샷 복사 · 목록 · 포인터 몫이다.
CYCLE_SLACK_SECONDS: Final = 300.0

PHASE_IDLE: Final = "idle"
PHASE_WAITING: Final = "waiting"
PHASE_UPLOADING: Final = "uploading"
PHASE_RETRY: Final = "retry"
PHASE_BLOCKED: Final = "blocked"

TITLE_CLEAN: Final = "올릴 것 없음"
TITLE_DIRTY: Final = "올릴 것 있음"
TITLE_UPLOADING: Final = "올리는 중"
TITLE_FAILED: Final = "실패"
TITLE_BLOCKED: Final = "멈춤"


class SyncEngine(Protocol):
    """일꾼이 부르는 차례 셋. 시험은 가짜를 넣어 스레드 없이 `tick` 을 돌린다."""

    @property
    def paths(self) -> SyncPaths: ...

    def upload(self) -> PublishOutcome: ...

    def watch(self) -> WatchResult: ...

    def prune(self, should_stop: Callable[[], bool]) -> PruneOutcome: ...


def repository_exporter(paths: SyncPaths) -> Exporter:
    """앱 안 내보내기 — 저장소의 쓰기 잠금을 지나는 바이트 복사."""
    scenario = DuckDBScenarioRepository(paths.databases["simulation"])
    equipment = DuckDBEquipmentRepository(paths.databases["equipment"])

    def export(dataset: DatasetName, destination: Path) -> ExportedSnapshot:
        owner = scenario if dataset == "simulation" else equipment
        copied = owner.export_checkpoint_copy(destination)
        return ExportedSnapshot(copied.export, copied.observed, copied.lock_seconds)

    return export


@dataclass(frozen=True)
class StorageEngine:
    """실제 저장소에 붙은 차례. 프로세스에 하나다."""

    client: ObjectStorageClient
    paths: SyncPaths
    exporter: Exporter

    def upload(self) -> PublishOutcome:
        return publish_generation(
            self.client, self.paths, exporter=self.exporter, origin="app", note="앱 저장"
        )

    def watch(self) -> WatchResult:
        return watch_head(self.client, self.paths)

    def prune(self, should_stop: Callable[[], bool]) -> PruneOutcome:
        return prune(self.client, should_stop=should_stop)


@dataclass(frozen=True)
class WorkerStatus:
    """일꾼의 지금 상태. 잠금 안에서 만든 불변 사본이고 화면은 이것만 읽는다."""

    alive: bool
    phase: str
    last_tick: float
    dirty: Mapping[DatasetName, bool] = field(default_factory=dict)
    seq: int | None = None
    last_success_utc: str | None = None
    sizes: Mapping[DatasetName, int] = field(default_factory=dict)
    lock_seconds: float | None = None
    transfer_seconds: float | None = None
    failures: int = 0
    failure_kind: str | None = None
    blocked: str | None = None
    next_try_at: float | None = None
    cycle_started: float | None = None
    cycle_deadline: float | None = None
    last_prune_utc: str | None = None
    last_prune_deleted: int | None = None
    prune_failure: str | None = None


@dataclass(frozen=True)
class SyncHealth:
    """화면이 내는 판정. `overdue` 는 `SY-02` 의 갈래, `blocked` 는 `SY-03` 의 판정이다."""

    title: str
    overdue: str | None = None
    blocked: str | None = None


def _worker_gone(status: WorkerStatus | None, now: float) -> bool:
    if status is None or not status.alive:
        return True
    if status.cycle_started is not None:
        return status.cycle_deadline is not None and now > status.cycle_deadline
    return now - status.last_tick > TICK_STALE_SECONDS


def assess(status: WorkerStatus | None, marks: MarkClock, now: float) -> SyncHealth:
    """지금 상태 판정. 일꾼 밖에서 돈다 — 멈춘 일꾼의 값이 멈춰도 시간은 간다.

    올리는 중이면 5분을 넘겨도 진행으로 본다(큰 DB 의 정상 회차). 그 회차가 제한 시간을 넘기면
    매달린 것이다.
    """
    if _worker_gone(status, now):
        return SyncHealth(TITLE_FAILED, overdue=FAILURE_WORKER_ABSENT)
    assert status is not None
    if status.blocked is not None:
        return SyncHealth(TITLE_BLOCKED, blocked=status.blocked)
    oldest = marks.oldest
    uploading = status.phase == PHASE_UPLOADING
    late = oldest is not None and now - oldest > OVERDUE_SECONDS and not uploading
    if status.failures >= OVERDUE_FAILURES or late:
        return SyncHealth(TITLE_FAILED, overdue=status.failure_kind or FAILURE_OTHER)
    if uploading:
        return SyncHealth(TITLE_UPLOADING)
    if oldest is not None or any(status.dirty.values()):
        return SyncHealth(TITLE_DIRTY)
    return SyncHealth(TITLE_CLEAN)


class ObjectSyncWorker:
    """시계와 재시도. 판단(`tick`)은 스레드 없이도 불러 시험한다."""

    def __init__(
        self,
        engine: SyncEngine,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], str] = sync_state.utc_now_text,
    ) -> None:
        self._engine = engine
        self._clock = clock
        self._wall_clock = wall_clock
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        started = clock()
        self._manual = False
        self._retry_at: float | None = None
        self._blocked: PushDecision | None = None
        self._blocked_until: float | None = None
        self._watch_at = started
        self._prune_at = started + PRUNE_FIRST_SECONDS
        generation = sync_state.read_generation(engine.paths.generation)
        self._status = WorkerStatus(
            alive=False,
            phase=PHASE_IDLE,
            last_tick=started,
            seq=generation.base_seq,
            last_success_utc=generation.base_synced_at_utc,
        )

    # ------------------------------------------------------------------ 바깥에서
    def wake(self) -> None:
        """막히지 않는다 — `sync_state` 의 리스너로 저장 경로에서 불린다."""
        self._wake.set()

    def request_now(self) -> None:
        """「지금 올리기」. 물러남을 비우고, 막힘이면 다시 판정만 한다."""
        with self._state_lock:
            self._manual = True
        self._wake.set()

    def status(self) -> WorkerStatus:
        with self._state_lock:
            current = self._status
        thread = self._thread
        return _replaced(current, alive=thread is not None and thread.is_alive())

    def start(self) -> None:
        """배경 스레드를 세운다(데몬 — 앱 프로세스가 끝나면 함께 끝난다)."""
        if self._thread is not None:
            return
        sync_state.set_listener(self.wake)
        thread = threading.Thread(target=self._loop, name=THREAD_NAME, daemon=True)
        # 화면이 스레드 목록에서 이 객체를 찾는다(`running_worker`).
        thread.sync_worker = self  # type: ignore[attr-defined]
        self._thread = thread
        thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """다음 확인 전에 멈춘다(시험·종료용)."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------------ 고리
    def _loop(self) -> None:
        delay = 0.0
        while not self._stop.is_set():
            if delay > 0:
                self._wake.wait(min(delay, WAKE_SECONDS))
            self._wake.clear()
            if self._stop.is_set():
                return
            try:
                delay = self.tick()
            except BaseException as exc:  # noqa: BLE001 — 스레드가 죽으면 저장이 안 올라간다
                _LOGGER.exception("동기화 일꾼의 확인이 실패했습니다.")
                self._note_failure(self._clock(), classify_failure(exc))
                delay = SOFT_RETRY_SECONDS

    def tick(self) -> float:
        """확인 한 번. 할 일을 하고, 다음 확인까지 쉴 초를 돌려준다."""
        now = self._clock()
        requested = sync_state.take_upload_request()
        with self._state_lock:
            manual = self._manual
            self._manual = False
        if manual:
            self._retry_at = None
            self._blocked_until = now
            self._set(failures=0, failure_kind=None)
        dirty = self._read_dirty()
        if any(dirty.values()):
            sync_state.note_leftover_marks()
        self._set(last_tick=now, dirty=dirty)
        if requested or manual:
            self._retry_at = None
            due: float | None = now
        else:
            due = self._next_upload_at(sync_state.mark_clock())
        if due is not None and due <= now:
            self._run_upload(now)
        elif now >= self._watch_at:
            self._run_watch(now)
        elif now >= self._prune_at:
            self._run_prune(now)
        return self._pause(self._clock())

    def _read_dirty(self) -> dict[DatasetName, bool]:
        databases = self._engine.paths.databases
        return {name: sync_state.treat_as_dirty(databases[name]) for name in DATASET_NAMES}

    def _next_upload_at(self, marks: MarkClock) -> float | None:
        if self._blocked is not None:
            return self._blocked_until
        if self._retry_at is not None:
            return self._retry_at
        if marks.first is None or marks.last is None:
            return None
        return min(marks.first + GATHER_SECONDS, marks.last + QUIET_SECONDS)

    def _pause(self, now: float) -> float:
        """다음에 할 일까지의 초. 없어도 `WAKE_SECONDS` 안에는 깨어난다."""
        moments = [self._watch_at, self._prune_at]
        due = self._next_upload_at(sync_state.mark_clock())
        if due is not None:
            moments.append(due)
        wait = max(min(moments) - now, 0.0)
        phase = self._phase(due)
        self._set(phase=phase, next_try_at=due)
        return min(wait, WAKE_SECONDS)

    def _phase(self, due: float | None) -> str:
        if self._blocked is not None:
            return PHASE_BLOCKED
        if self._retry_at is not None:
            return PHASE_RETRY
        return PHASE_IDLE if due is None else PHASE_WAITING

    def _cycle_deadline(self, now: float) -> float:
        databases = self._engine.paths.databases
        total = 0
        for path in databases.values():
            try:
                total += path.stat().st_size
            except OSError:
                continue
        # 재시도 3번까지 든 시간이 끝이다(`ObjectStorageClient._run`).
        return now + 3 * transfer_timeout_seconds(total) + CYCLE_SLACK_SECONDS

    def _run_upload(self, now: float) -> None:
        sync_state.begin_cycle()
        self._set(
            phase=PHASE_UPLOADING, cycle_started=now, cycle_deadline=self._cycle_deadline(now)
        )
        carried = False
        try:
            carried = self._apply(self._engine.upload(), self._clock())
        except (SnapshotBusy, SnapshotRaced):
            self._retry_at = self._clock() + SOFT_RETRY_SECONDS
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — 어떤 실패든 물러나서 다시 한다
            self._note_failure(self._clock(), classify_failure(exc))
        finally:
            sync_state.end_cycle(carried=carried)
            self._set(cycle_started=None, cycle_deadline=None)

    def _apply(self, outcome: PublishOutcome, now: float) -> bool:
        """회차 결과를 상태에 적는다. 돌려주는 값은 들고 간 표시가 정본에 닿았는지다."""
        if outcome.settled is not None:
            self._note_success(outcome.settled.seq)
        if outcome.confirm_deferred:
            self._retry_at = now + SOFT_RETRY_SECONDS
            return False
        if outcome.stop is PublishStop.REMOTE_MOVED or outcome.stop is PublishStop.FORKED:
            self._note_blocked(PushDecision.BLOCKED_UNPUBLISHED, now)
            return False
        if outcome.stop is PublishStop.LOCAL_MISSING:
            self._note_failure(now, FAILURE_OTHER)
            return False
        if outcome.decision in BLOCKING_PUSH:
            self._note_blocked(outcome.decision, now)
            return False
        self._retry_at = None
        self._blocked = None
        self._blocked_until = None
        self._set(failures=0, failure_kind=None, blocked=None)
        if outcome.published and outcome.pointer is not None:
            self._note_success(
                outcome.pointer.seq,
                sizes={name: result.size_bytes for name, result in outcome.uploaded.items()},
                lock_seconds=outcome.lock_seconds,
                transfer_seconds=outcome.transfer_seconds,
            )
        self._watch_at = now + WATCH_SECONDS
        return True

    def _note_success(
        self,
        seq: int,
        *,
        sizes: Mapping[DatasetName, int] | None = None,
        lock_seconds: float | None = None,
        transfer_seconds: float | None = None,
    ) -> None:
        with self._state_lock:
            current = self._status
            self._status = _replaced(
                current,
                seq=seq,
                last_success_utc=self._wall_clock(),
                sizes={**current.sizes, **(sizes or {})},
                lock_seconds=current.lock_seconds if lock_seconds is None else lock_seconds,
                transfer_seconds=(
                    current.transfer_seconds if transfer_seconds is None else transfer_seconds
                ),
            )

    def _note_blocked(self, decision: PushDecision, now: float) -> None:
        self._blocked = decision
        self._blocked_until = now + BLOCKED_RECHECK_SECONDS
        self._retry_at = None
        self._set(blocked=decision.value)

    def _note_failure(self, now: float, kind: str) -> None:
        with self._state_lock:
            failures = self._status.failures + 1
            self._status = _replaced(self._status, failures=failures, failure_kind=kind)
        steps = FAILURE_BACKOFF_SECONDS
        self._retry_at = now + steps[min(failures, len(steps)) - 1]

    def _run_watch(self, now: float) -> None:
        self._watch_at = now + WATCH_SECONDS
        try:
            result = self._engine.watch()
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — 다음 확인에 다시 본다
            _LOGGER.warning("동기화 HEAD 확인 실패 — %s", classify_failure(exc))
            return
        if result.decision in BLOCKING_PUSH:
            self._note_blocked(result.decision, now)
        elif self._blocked is not None:
            self._blocked = None
            self._blocked_until = None
            self._set(blocked=None)

    def _run_prune(self, now: float) -> None:
        try:
            outcome = self._engine.prune(self._should_yield)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — 저장을 막지 않는다. 다음 날 다시
            self._prune_at = now + PRUNE_EVERY_SECONDS
            self._set(prune_failure=classify_failure(exc))
            return
        leftover = outcome.interrupted or outcome.plan.deferred > 0
        self._prune_at = now + (PRUNE_LEFTOVER_SECONDS if leftover else PRUNE_EVERY_SECONDS)
        self._set(
            last_prune_utc=self._wall_clock(),
            last_prune_deleted=outcome.deleted,
            prune_failure=None,
        )

    def _should_yield(self) -> bool:
        with self._state_lock:
            if self._manual:
                return True
        if sync_state.upload_requested():
            return True
        due = self._next_upload_at(sync_state.mark_clock())
        return due is not None and due <= self._clock()

    def _set(self, **changes: object) -> None:
        with self._state_lock:
            self._status = _replaced(self._status, **changes)


def _replaced(status: WorkerStatus, **changes: object) -> WorkerStatus:
    return WorkerStatus(**{**status.__dict__, **changes})


_START_LOCK = threading.Lock()


class WorkerHandle(Protocol):
    def status(self) -> WorkerStatus: ...

    def request_now(self) -> None: ...

    def stop(self, timeout: float | None = None) -> None: ...


def running_worker() -> WorkerHandle | None:
    """이 프로세스에서 살아 있는 일꾼. 없으면 None."""
    for thread in threading.enumerate():
        if thread.name != THREAD_NAME or not thread.is_alive():
            continue
        worker = getattr(thread, "sync_worker", None)
        if worker is not None and callable(getattr(worker, "status", None)):
            return cast(WorkerHandle, worker)
    return None


def current_status() -> WorkerStatus | None:
    """화면이 읽는 값. 메모리뿐이고 디스크 · 네트워크를 쓰지 않는다."""
    worker = running_worker()
    return None if worker is None else worker.status()


def build_storage_engine() -> StorageEngine:
    paths = default_paths()
    return StorageEngine(
        client=ObjectStorageClient(settings=load_settings()),
        paths=paths,
        exporter=repository_exporter(paths),
    )


def start_object_sync(
    *, build_engine: Callable[[], SyncEngine] = build_storage_engine
) -> WorkerHandle | None:
    """조건이 맞으면 이 프로세스의 일꾼을 (없을 때만) 세운다. 어떤 실패도 올리지 않는다.

    실패는 로그에 남고 `managed` 면 `assess` 가 `SY-02`(`worker_absent`)로 드러낸다.
    """
    try:
        if not sync_boot.enable_sync_state_if_managed():
            return None
        if sync_boot.read_boot_record() is None:
            _LOGGER.warning("시작 받기 기록이 없어 동기화 일꾼을 세우지 않습니다.")
            return None
        with _START_LOCK:
            existing = running_worker()
            if existing is not None:
                return existing
            worker = ObjectSyncWorker(build_engine())
            worker.start()
            return worker
    except Exception:
        _LOGGER.exception("동기화 일꾼을 시작하지 못했습니다.")
        return None
