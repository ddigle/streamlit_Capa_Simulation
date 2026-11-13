# Purpose: 감사 올리기 · 일별 묶음 · 미러를 가짜 S3 위에서 — 새 객체 · 재시도 · 막힘 · 늦은 조각.

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from object_store_fakes import seed_pair
from s3_mock_runner import MockStoreRunner, mock_client

from capa_simulation.audit import layout, read, recorder, shipper, spool
from capa_simulation.components import object_sync_status
from capa_simulation.io.object_storage import ObjectRecord
from capa_simulation.object_sync_engine import PruneOutcome, SyncPaths, WatchResult
from capa_simulation.object_sync_worker import ObjectSyncWorker, SyncHealth, WorkerStatus
from capa_simulation.persistence import sync_state
from capa_simulation.services.object_storage_manifest import PrunePlan, PushDecision

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from s3_mock_store import MockStore, start_mock  # noqa: E402

INST = "1a2b3c4d5e6f"
TODAY = date(2026, 11, 13)


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.moment


@dataclass
class Box:
    store: MockStore
    runner: MockStoreRunner
    bucket: shipper.ClientBucket
    clock: Clock
    base: Path

    def tasks(self, *, monotonic: Callable[[], float] | None = None) -> shipper.AuditTasks:
        return shipper.AuditTasks(
            self.bucket,
            clock=monotonic or (lambda: 0.0),
            today=lambda: TODAY,
            wall=self.clock,
            base=self.base,
        )

    def record(self, count: int, *, actor: str = "demo.user") -> None:
        for _ in range(count):
            recorder.record("session_created", actor=actor)
        spool.drain()

    def keys(self, prefix: str = layout.PREFIX) -> list[str]:
        return sorted(key for key in self.store.objects if key.startswith(prefix))


@pytest.fixture()
def box(tmp_path: Path) -> Iterator[Box]:
    store = MockStore()
    server, endpoint = start_mock(store)
    runner = MockStoreRunner(
        endpoint, store.bucket, store.region, store.access_key, store.secret_key
    )
    bucket = shipper.ClientBucket(mock_client(runner), tmp_path / "scratch")
    clock = Clock()
    base = tmp_path / "audit"
    spool.configure(base)
    shipper.reset()
    recorder.start(env="cdep", version="test", inst=INST, clock=clock)
    yield Box(store, runner, bucket, clock, base)
    server.shutdown()
    server.server_close()
    shipper.reset()


def _operations(runner: MockStoreRunner) -> list[str]:
    return [call[2] for call in runner.calls]


def test_ship_puts_new_objects_only_and_marks_the_spool(box: Box) -> None:
    box.record(3)

    outcome = shipper.ship(box.bucket, today=TODAY, base=box.base)

    key = layout.piece_key("seg", "2026-11-13", INST, 1, 3)
    assert outcome.keys == (key,) and outcome.lines == 3
    assert box.keys() == [key]
    spooled = spool.read_lines(spool.spool_path("2026-11-13", INST, box.base))
    assert layout.decode_lines(box.store.objects[key]) == spooled
    put = [call for call in box.runner.calls if call[2] == "put-object"]
    assert put and all("--if-none-match" in call for call in put)
    assert shipper.ship(box.bucket, today=TODAY, base=box.base).keys == ()
    assert spool.unshipped_count() == 0


def test_a_retry_of_the_same_piece_is_quietly_accepted(box: Box) -> None:
    box.record(2)
    shipper.ship(box.bucket, today=TODAY, base=box.base)
    path = spool.spool_path("2026-11-13", INST, box.base)
    path.with_name(path.name + spool.SHIPPED_SUFFIX).unlink()
    before = dict(box.store.objects)

    outcome = shipper.ship(box.bucket, today=TODAY, base=box.base)

    assert outcome.lines == 2
    assert box.store.objects == before
    assert spool.shipped_seq(path) == 2


def test_without_conditional_put_it_looks_before_it_writes(box: Box) -> None:
    bucket = shipper.ClientBucket(mock_client(box.runner, conditional_put=False), box.base / "s")
    box.record(1)
    shipper.ship(bucket, today=TODAY, base=box.base)
    path = spool.spool_path("2026-11-13", INST, box.base)
    path.with_name(path.name + spool.SHIPPED_SUFFIX).unlink()
    box.runner.calls.clear()

    shipper.ship(bucket, today=TODAY, base=box.base)

    assert _operations(box.runner) == ["head-object"]


@dataclass
class BlockedEngine:
    """DB 올리기가 막힌 서버 — HEAD 가 어긋남을 말한다. 올리기는 불리면 안 된다."""

    paths: SyncPaths
    watched: int = 0
    uploads: list[int] = field(default_factory=list)

    def upload(self) -> object:
        self.uploads.append(1)
        raise AssertionError("막힌 서버는 DB 를 올리지 않는다")

    def watch(self) -> WatchResult:
        self.watched += 1
        return WatchResult(PushDecision.PARENT_MOVED, 2)

    def prune(self, should_stop: Callable[[], bool]) -> PruneOutcome:
        return PruneOutcome(plan=PrunePlan(), deleted=0)


class Monotonic:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def worker_rig(box: Box, tmp_path: Path) -> Iterator[tuple[ObjectSyncWorker, Monotonic]]:
    sync_state.clear_all()
    monotonic = Monotonic()
    (tmp_path / "db").mkdir()
    paths = seed_pair(tmp_path / "db")
    sync_state.enable(paths.registry)
    for name, path in paths.databases.items():
        sync_state.adopt_clean(path, dataset=name)
    engine = BlockedEngine(paths)
    worker = ObjectSyncWorker(
        engine,  # type: ignore[arg-type]
        clock=monotonic,
        audit=box.tasks(monotonic=monotonic),
    )
    yield worker, monotonic
    sync_state.clear_all()


def test_audit_goes_up_while_the_db_upload_is_blocked(
    box: Box, worker_rig: tuple[ObjectSyncWorker, Monotonic]
) -> None:
    worker, monotonic = worker_rig
    worker.tick()
    assert worker.status().blocked == PushDecision.PARENT_MOVED.value

    box.record(2)
    monotonic.now += 5
    worker.tick()

    pieces = box.keys(layout.SEG_PREFIX)
    assert pieces, "막힌 DB 와 상관없이 감사는 올라간다"
    lines = [line for key in pieces for line in layout.decode_lines(box.store.objects[key])]
    assert "audit_chain_link" in [line["ev"] for line in lines]
    assert worker.status().blocked == PushDecision.PARENT_MOVED.value
    assert worker.status().failures == 0


def test_an_audit_failure_leaves_the_db_status_alone(
    box: Box, worker_rig: tuple[ObjectSyncWorker, Monotonic]
) -> None:
    worker, monotonic = worker_rig
    worker.tick()
    box.store.force_on("PUT", "audit/", times=50, status=500)
    box.record(1)
    monotonic.now += 5

    worker.tick()

    assert shipper.health().failures == 1
    assert worker.status().failures == 0
    spool.drain()
    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, box.base))
    assert "sys_audit_ship_fail" in [line["ev"] for line in lines]


def test_upload_now_ships_the_audit_first(
    box: Box, worker_rig: tuple[ObjectSyncWorker, Monotonic]
) -> None:
    worker, monotonic = worker_rig
    worker.tick()
    tasks = worker._audit
    assert tasks is not None
    tasks._ship_at = monotonic.now + 10_000
    box.record(1)
    assert not tasks.ship_due(monotonic.now)

    worker.request_now()
    worker.tick()

    shipped = [
        line
        for key in box.keys(layout.SEG_PREFIX)
        for line in layout.decode_lines(box.store.objects[key])
    ]
    assert "session_created" in [line["ev"] for line in shipped]


def _yesterday(box: Box, count: int, *, inst: str = INST) -> None:
    box.clock.moment = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    if inst != recorder.instance_id():
        recorder.reset()
        spool.reset()
        recorder.start(env="cdep", version="test", inst=inst, clock=box.clock)
    box.record(count, actor=f"demo.{inst[:4]}")
    shipper.ship(box.bucket, today=TODAY, base=box.base)
    box.clock.moment = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)


def test_compact_writes_a_daily_file_and_chains_the_late_supplement(box: Box) -> None:
    _yesterday(box, 3)

    first = shipper.compact(box.bucket, today=TODAY)

    assert first.written == (layout.daily_key("2026-11-12", 0),)
    manifest = json.loads(box.store.objects[layout.manifest_key("2026-11-12", 0)])
    daily = box.store.objects[layout.daily_key("2026-11-12", 0)]
    assert manifest["segments"] == box.keys(layout.SEG_PREFIX)
    assert manifest["lines"] == 3 and manifest["prev_manifest"] is None
    assert manifest["sha256"] == hashlib.sha256(daily).hexdigest()
    assert manifest["instances"][INST]["last"] == 3
    assert shipper.compact(box.bucket, today=TODAY).written == ()

    _yesterday(box, 2, inst="9f9f9f9f9f9f")
    second = shipper.compact(box.bucket, today=TODAY)

    assert second.written == (layout.daily_key("2026-11-12", 1),)
    supplement = json.loads(box.store.objects[layout.manifest_key("2026-11-12", 1)])
    p0 = box.store.objects[layout.manifest_key("2026-11-12", 0)]
    assert supplement["prev_manifest"] == hashlib.sha256(p0).hexdigest()
    assert supplement["lines"] == 2
    assert all("9f9f9f9f9f9f" in key for key in supplement["segments"])


def test_a_new_day_chains_to_the_last_manifest_of_the_day_before(box: Box) -> None:
    _yesterday(box, 1)
    shipper.compact(box.bucket, today=TODAY)
    box.clock.moment = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    box.record(1)
    shipper.ship(box.bucket, today=TODAY, base=box.base)

    shipper.compact(box.bucket, today=TODAY + timedelta(days=1))

    later = json.loads(box.store.objects[layout.manifest_key("2026-11-13", 0)])
    earlier = box.store.objects[layout.manifest_key("2026-11-12", 0)]
    assert later["prev_manifest"] == hashlib.sha256(earlier).hexdigest()


def test_a_piece_older_than_fourteen_days_is_noted_late(box: Box) -> None:
    box.clock.moment = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
    box.record(1)
    box.clock.moment = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)
    tasks = box.tasks()

    tasks.run_ship(0.0)

    assert shipper.chain_problems() == (layout.piece_key("seg", "2026-10-20", INST, 1, 1),)
    spool.drain()
    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, box.base))
    late = [line for line in lines if line["ev"] == "audit_late_segment"]
    assert late and late[0]["det"]["date"] == "2026-10-20"
    assert late[0]["lvl"] == "crit"


def test_mirror_takes_the_daily_file_and_then_drops_the_spool(box: Box) -> None:
    _yesterday(box, 2)
    shipper.compact(box.bucket, today=TODAY)
    spooled = spool.spool_path("2026-11-12", INST, box.base)
    assert spooled.exists()

    outcome = shipper.mirror(box.bucket, today=TODAY, base=box.base)

    assert layout.daily_key("2026-11-12", 0) in outcome.downloaded
    assert outcome.pruned == (spooled,)
    assert not spooled.exists()
    rows = read.load_lines(box.base, date(2026, 11, 12), date(2026, 11, 12))
    assert [row["seq"] for row in rows] == [1, 2]


def test_a_new_instance_links_to_the_tail_of_the_one_before(box: Box) -> None:
    box.record(2)
    shipper.ship(box.bucket, today=TODAY, base=box.base)
    tail = spool.read_lines(spool.spool_path("2026-11-13", INST, box.base))[-1]
    for path in spool.spool_files(box.base):
        path.unlink()
    recorder.reset()
    spool.reset()
    recorder.start(env="cdep", version="test", inst="7e7e7e7e7e7e", clock=box.clock)
    box.clock.moment += timedelta(minutes=1)

    box.tasks().run_ship(0.0)

    piece = layout.piece_key("seg", "2026-11-13", "7e7e7e7e7e7e", 1, 1)
    (link,) = layout.decode_lines(box.store.objects[piece])
    assert link["ev"] == "audit_chain_link"
    assert link["det"] == {
        "prev_inst": INST,
        "prev_seq": 2,
        "prev_h": tail["h"],
        "end_mark": "none",
    }


def test_a_clock_off_by_minutes_is_noted(box: Box, monkeypatch: pytest.MonkeyPatch) -> None:
    real = box.clock()
    box.store.clock = lambda: real + timedelta(minutes=5)
    box.record(1)

    box.tasks().run_ship(0.0)

    assert shipper.health().skew_seconds == pytest.approx(-300, abs=2)
    assert "시계 차이" in shipper.keeping_problems(managed=True)
    spool.drain()
    lines = spool.read_lines(spool.spool_path("2026-11-13", INST, box.base))
    assert "sys_clock_skew" in [line["ev"] for line in lines]


def test_keeping_problems_name_a_server_that_is_not_managed(box: Box) -> None:
    assert shipper.keeping_problems(managed=False) == ("동기화 아님",)
    assert shipper.keeping_problems(managed=True) == ()


def test_the_sync_panel_shows_the_unshipped_audit_lines(box: Box) -> None:
    box.record(3)
    status = WorkerStatus(alive=True, phase="idle", last_tick=0.0)
    health = SyncHealth("올릴 것 없음")

    lines = object_sync_status.status_lines(status, health, now=0.0)

    assert "**감사 미전송** · 3줄" in lines
    recorder.reset()
    assert not [
        line for line in object_sync_status.status_lines(status, health, now=0.0) if "감사" in line
    ]


def test_a_long_first_mirror_gives_way_to_a_pending_db_upload(box: Box, tmp_path: Path) -> None:
    """빈 디스크로 뜬 서버의 첫 미러(일별 파일 여럿)가 유일한 일꾼을 붙잡지 않는다 — 올릴 저장이
    생기면 받는 사이에 멈추고 DB 올리기가 먼저 돈 뒤, 남은 파일만 다음 고리에 잇는다."""
    for back in range(1, 31):
        day = (TODAY - timedelta(days=back)).isoformat()
        box.store.put(layout.daily_key(day, 0), layout.encode_lines([]))
        box.store.put(layout.manifest_key(day, 0), b"{}")
    sync_state.clear_all()
    monotonic = Monotonic()
    (tmp_path / "db").mkdir()
    paths = seed_pair(tmp_path / "db")
    sync_state.enable(paths.registry)
    for name, path in paths.databases.items():
        sync_state.adopt_clean(path, dataset=name)

    @dataclass
    class QuietEngine:
        paths: SyncPaths
        uploads: list[int] = field(default_factory=list)

        def upload(self) -> object:
            self.uploads.append(len(_mirrored()))
            from capa_simulation.object_sync_engine import PublishOutcome

            return PublishOutcome(PushDecision.UP_TO_DATE)

        def watch(self) -> WatchResult:
            return WatchResult(PushDecision.UP_TO_DATE, 1)

        def prune(self, should_stop: Callable[[], bool]) -> PruneOutcome:
            return PruneOutcome(plan=PrunePlan(), deleted=0)

    def _mirrored() -> list[Path]:
        return sorted((box.base / layout.MIRROR_DIR).rglob("*.jsonl.gz"))

    calls: list[str] = []

    @dataclass
    class SavingBucket:
        """셋째 받기 사이에 사람이 저장한 것처럼 올리기를 청한다."""

        inner: shipper.ClientBucket

        def records(self, prefix: str) -> tuple[ObjectRecord, ...]:
            return self.inner.records(prefix)

        def put_new(self, key: str, body: bytes) -> bool:
            return self.inner.put_new(key, body)

        def get(self, key: str) -> bytes:
            calls.append(key)
            if len(calls) == 3:
                sync_state.request_upload()
            return self.inner.get(key)

        def modified(self, key: str) -> datetime | None:
            return self.inner.modified(key)

    engine = QuietEngine(paths)
    tasks = shipper.AuditTasks(
        SavingBucket(box.bucket),
        clock=monotonic,
        today=lambda: TODAY,
        wall=box.clock,
        base=box.base,
    )
    worker = ObjectSyncWorker(engine, clock=monotonic, audit=tasks)  # type: ignore[arg-type]
    try:
        worker.tick()  # 시작 직후 HEAD 확인
        monotonic.now += shipper.MIRROR_FIRST_SECONDS + 1
        worker.tick()  # 미러 — 셋째 받기 뒤 저장 요청이 와 멈춘다
        stopped_at = len(_mirrored())
        assert 0 < stopped_at < 30
        assert not any(key.endswith(".manifest.json") for key in calls), "manifest 는 받지 않는다"
        worker.tick()  # DB 올리기가 먼저
        assert engine.uploads == [stopped_at]
        for _ in range(3):
            worker.tick()
        assert len(_mirrored()) == 30
    finally:
        sync_state.clear_all()


def test_the_worker_starts_even_if_the_audit_tasks_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from capa_simulation import object_sync_worker as worker_module
    from capa_simulation import sync_boot

    (tmp_path / "db").mkdir()
    paths = seed_pair(tmp_path / "db")
    monkeypatch.setattr(sync_boot, "enable_sync_state_if_managed", lambda: True)
    monkeypatch.setattr(sync_boot, "read_boot_record", lambda: object())

    def broken() -> shipper.AuditTasks:
        raise ValueError("남은 스풀이 깨졌다")

    @dataclass
    class IdleEngine:
        paths: SyncPaths

        def upload(self) -> object:
            raise AssertionError

        def watch(self) -> WatchResult:
            return WatchResult(PushDecision.UP_TO_DATE, 1)

        def prune(self, should_stop: Callable[[], bool]) -> PruneOutcome:
            return PruneOutcome(plan=PrunePlan(), deleted=0)

    handle = worker_module.start_object_sync(
        build_engine=lambda: IdleEngine(paths),  # type: ignore[arg-type,return-value]
        build_audit_work=broken,
    )
    try:
        assert handle is not None
        assert getattr(handle, "_audit", "missing") is None
    finally:
        if handle is not None:
            handle.stop(timeout=5)
        sync_state.clear_all()


def test_a_daily_file_left_without_its_manifest_is_never_reused(box: Box) -> None:
    _yesterday(box, 2)
    box.store.put(layout.daily_key("2026-11-12", 0), b"orphan")

    outcome = shipper.compact(box.bucket, today=TODAY)

    assert outcome.written == (layout.daily_key("2026-11-12", 1),)
    assert box.store.objects[layout.daily_key("2026-11-12", 0)] == b"orphan"
    manifest = json.loads(box.store.objects[layout.manifest_key("2026-11-12", 1)])
    assert (
        manifest["sha256"]
        == hashlib.sha256(box.store.objects[layout.daily_key("2026-11-12", 1)]).hexdigest()
    )
