# Purpose: 세대 게시·받기·되돌리기의 차례와 어느 단계에서 끊겨도 정본을 잃지 않음을 검증한다.

"""유실을 막는 차례를 지키는 시험.

조각 시험(판정 · 사이드카 · 스냅샷)이 지키지 못하는 것이 여기 있다 — **포인터는 들어갔는데 실패로
끝난 뒤의 같은 프로세스 다음 회차**, 두 사이드카 사이의 실패, 회차 중 이어 적은 DB 에 든 저장,
끝나는 옛 pod 의 늦은 게시. 저장 전 실패만 흉내 내면 이 길이 모두 통과한다.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from object_store_fakes import (
    CONNECT_TEXT,
    Failure,
    FakeStore,
    add_row,
    fake_client,
    row_count,
    seed_database,
    seed_pair,
)

from capa_simulation import object_sync_engine as engine
from capa_simulation import settings as app_settings
from capa_simulation.io.object_storage import ObjectStorageError
from capa_simulation.object_sync_engine import ExportedSnapshot, PublishStop
from capa_simulation.object_sync_worker import (
    FAILURE_BACKOFF_SECONDS,
    WATCH_SECONDS,
    ObjectSyncWorker,
    StorageEngine,
)
from capa_simulation.persistence import snapshot_export, sync_state
from capa_simulation.services import object_storage_manifest as manifest
from capa_simulation.services.object_storage_manifest import (
    BLOCKING_PUSH,
    DatasetName,
    Member,
    PullDecision,
    PushDecision,
)


@pytest.fixture()
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """임시 자리의 두 DB + 가짜 저장소 + 첫 세대까지."""
    sync_state.clear_all()
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    paths = seed_pair(tmp_path)
    sync_state.enable(paths.registry)
    store = FakeStore()
    client = fake_client(store)
    exporter = engine.offline_exporter(paths)
    first = engine.init_generation(
        client, paths, exporter=exporter, note="첫 세대", keep_writer=True
    )
    assert first.published
    yield SimpleNamespace(
        paths=paths,
        store=store,
        client=client,
        exporter=exporter,
        simulation=paths.databases["simulation"],
        equipment=paths.databases["equipment"],
        folder=tmp_path,
    )
    sync_state.clear_all()


def _save(rig: SimpleNamespace, dataset: DatasetName = "simulation", value: int = 321) -> None:
    path = rig.paths.databases[dataset]
    add_row(path, value)
    sync_state.mark_dirty(path)


def _publish(rig: SimpleNamespace) -> engine.PublishOutcome:
    return engine.publish_generation(
        rig.client, rig.paths, exporter=rig.exporter, origin="app", note="앱 저장"
    )


def _state(rig: SimpleNamespace) -> sync_state.GenerationState:
    return sync_state.read_generation(rig.paths.generation)


def _head_seq(rig: SimpleNamespace) -> int:
    return manifest.seq_from_pointer_key(rig.store.pointer_keys()[0])


def _wipe_disk(rig: SimpleNamespace) -> None:
    """CI/CD 를 흉내 낸다 — 새 pod 의 빈 디스크."""
    for path in rig.paths.databases.values():
        path.unlink(missing_ok=True)
        snapshot_export.wal_path(path).unlink(missing_ok=True)
        sync_state.sidecar_path(path).unlink(missing_ok=True)
    rig.paths.generation.unlink(missing_ok=True)


def _another_writer_publishes(rig: SimpleNamespace, *, seq: int | None = None) -> str:
    """남이 세대를 낸다. 키만 넣어도 목록 판정에는 그것으로 족하다."""
    head = engine.read_pointer(rig.client, rig.store.pointer_keys()[0])
    pointer = manifest.next_pointer(
        head,
        members=head.members,
        origin="app",
        token="abcdef01",
        app_version="demo",
        author="demo@other",
        created_at_utc="2026-11-07T00:00:00Z",
        note="",
    )
    key = pointer.pointer_key
    rig.store.objects[key] = manifest.pointer_to_json(pointer).encode("utf-8")
    return key


# --------------------------------------------------------------------------- 올리기
def test_the_first_generation_holds_both_members(rig: SimpleNamespace) -> None:
    pointer = engine.read_pointer(rig.client, rig.store.pointer_keys()[0])

    assert pointer.seq == 1
    assert pointer.origin == "init"
    assert {member.seq for member in pointer.members.values()} == {1}


def test_only_the_changed_database_is_uploaded(rig: SimpleNamespace) -> None:
    """바뀌지 않은 DB 는 앞 세대의 멤버를 그대로 이어 적는다 — 그래서 키에 멤버 세대를 싣는다."""
    _save(rig)

    outcome = _publish(rig)

    assert outcome.published
    assert list(outcome.uploaded) == ["simulation"]
    pointer = engine.read_pointer(rig.client, rig.store.pointer_keys()[0])
    assert pointer.members["simulation"].seq == 2
    assert pointer.members["equipment"].seq == 1
    assert manifest.member_seqs_from_pointer_key(pointer.pointer_key) == {
        "simulation": 2,
        "equipment": 1,
    }
    assert len(rig.store.keys("equipment/snapshots/")) == 1


def test_publishing_follows_the_order(rig: SimpleNamespace) -> None:
    """목록 → 스냅샷(시뮬 → 설비) → 목록 → 포인터 → 목록. 이 차례가 유실 방지의 전부다."""
    _save(rig, "simulation")
    _save(rig, "equipment")
    rig.store.calls.clear()

    _publish(rig)

    kinds = [
        ("list" if op == "list-objects-v2" else key.split("/")[0])
        for op, key in rig.store.operations()
    ]
    assert kinds == ["list", "simulation", "equipment", "list", "generations", "list"]


def test_nothing_changed_uploads_nothing(rig: SimpleNamespace) -> None:
    before = dict(rig.store.objects)

    outcome = _publish(rig)

    assert outcome.decision is PushDecision.UP_TO_DATE
    assert rig.store.objects == before


def test_a_save_during_the_upload_keeps_its_mark(rig: SimpleNamespace) -> None:
    """스냅샷 뒤 저장은 그 세대에 없다. 게시는 성공하고 표시는 남아 다음 회차가 싣는다."""
    _save(rig)
    saved: list[str] = []

    def save_during_put(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith("simulation/") and not saved:
            saved.append(key)
            _save(rig, "simulation", 777)

    rig.store.before = save_during_put

    assert _publish(rig).published
    assert sync_state.treat_as_dirty(rig.simulation) is True

    rig.store.before = None
    assert _publish(rig).published
    assert sync_state.treat_as_dirty(rig.simulation) is False
    _wipe_disk(rig)
    assert engine.boot_pull(rig.client, rig.paths).ok
    assert row_count(rig.simulation) == 12


def test_a_save_to_the_carried_database_during_the_upload_keeps_its_mark(
    rig: SimpleNamespace,
) -> None:
    """이번 세대가 담지 않은 DB 의 표시는 건드리지 않는다. 지우면 그 저장이 영영 안 올라간다."""
    _save(rig, "simulation")
    saved: list[str] = []

    def save_during_put(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith("simulation/") and not saved:
            saved.append(key)
            _save(rig, "equipment", 777)

    rig.store.before = save_during_put

    assert _publish(rig).published
    assert sync_state.treat_as_dirty(rig.simulation) is False
    assert sync_state.treat_as_dirty(rig.equipment) is True

    rig.store.before = None
    assert _publish(rig).published
    assert sync_state.treat_as_dirty(rig.equipment) is False


def test_pending_is_written_before_the_pointer_put(rig: SimpleNamespace) -> None:
    """적기 전에 PUT 하면, 답이 끊긴 포인터를 다음 회차가 남의 것으로 읽는다."""
    _save(rig)
    seen = []

    def look(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith(manifest.HEAD_PREFIX):
            seen.append(_state(rig).pending)

    rig.store.before = look

    assert _publish(rig).published
    assert seen[0] is not None
    assert seen[0].pointer_key == rig.store.pointer_keys()[0]
    assert _state(rig).pending is None


def test_a_pointer_that_landed_without_an_answer_is_finished_next_cycle(
    rig: SimpleNamespace,
) -> None:
    """포인터는 들어갔는데 답이 끊겼다. 자기 포인터를 남의 것으로 읽으면 영원히 못 올린다."""
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=True))

    with pytest.raises(ObjectStorageError):
        _publish(rig)

    assert _head_seq(rig) == 2
    assert _state(rig).base_seq == 1
    assert _state(rig).pending is not None

    second = _publish(rig)

    assert second.settled is not None and second.settled.seq == 2
    assert second.decision is PushDecision.UP_TO_DATE
    assert _state(rig).base_seq == 2
    assert sync_state.treat_as_dirty(rig.simulation) is False

    _save(rig, value=555)
    assert _publish(rig).published
    assert _head_seq(rig) == 3


def test_a_head_check_knows_its_own_unanswered_pointer(rig: SimpleNamespace) -> None:
    """HEAD 가 답 끊긴 자기 포인터면 남이 앞선 것이 아니다. 판정은 올리기 회차가 마무리한다."""
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=True))
    with pytest.raises(ObjectStorageError):
        _publish(rig)

    result = engine.watch_head(rig.client, rig.paths)

    assert result.decision not in BLOCKING_PUSH
    assert result.head_seq == 2


def test_a_head_check_on_a_first_generation_without_an_answer_is_not_an_empty_remote(
    tmp_path: Path,
) -> None:
    """base 가 아직 없는 자리도 같다. 자기 포인터를 base 로 바꿔 읽으면 「원격이 빔」 이 된다."""
    paths = seed_pair(tmp_path)
    store = FakeStore()
    client = fake_client(store)
    store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=True))
    with pytest.raises(ObjectStorageError):
        engine.init_generation(
            client, paths, exporter=engine.offline_exporter(paths), note="최초 이관"
        )

    assert engine.watch_head(client, paths).decision not in BLOCKING_PUSH


def test_a_head_check_still_sees_someone_else_past_a_pending_pointer(
    rig: SimpleNamespace,
) -> None:
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))
    with pytest.raises(ObjectStorageError):
        _publish(rig)
    _another_writer_publishes(rig)

    assert engine.watch_head(rig.client, rig.paths).decision is PushDecision.PARENT_MOVED


def test_an_unanswered_pointer_and_a_due_head_check_do_not_delay_the_retry(
    rig: SimpleNamespace,
) -> None:
    """거짓 `SY-03` 을 내고 30초 재시도를 300초로 밀면 유실 창이 그만큼 는다."""
    moment = [1_000.0]
    worker = ObjectSyncWorker(
        StorageEngine(rig.client, rig.paths, rig.exporter), clock=lambda: moment[0]
    )
    worker.tick()
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=True))
    moment[0] += WATCH_SECONDS
    sync_state.request_upload()

    worker.tick()
    assert worker.status().failures == 1
    assert _state(rig).pending is not None

    worker.tick()
    assert worker.status().blocked is None

    moment[0] += FAILURE_BACKOFF_SECONDS[0]
    worker.tick()

    assert worker.status().blocked is None
    assert worker.status().seq == 2
    assert _state(rig).pending is None


def test_a_lost_confirmation_is_not_a_failed_publish(rig: SimpleNamespace) -> None:
    """포인터 뒤 목록이 실패해도 게시는 끝난 것이다. 다음 회차가 확인만 마저 한다."""
    _save(rig)
    pointers = []

    def fail_after_pointer(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith(manifest.HEAD_PREFIX):
            pointers.append(key)
            rig.store.failures.append(Failure("list-objects-v2", manifest.HEAD_PREFIX))

    rig.store.before = fail_after_pointer

    outcome = _publish(rig)

    assert outcome.published is False
    assert outcome.confirm_deferred is True
    assert _head_seq(rig) == 2

    rig.store.before = None
    rig.store.failures.clear()
    settled = _publish(rig)

    assert settled.settled is not None
    assert _state(rig).base_seq == 2
    assert len(pointers) == 1


def test_a_pointer_that_never_landed_is_sent_again_under_the_same_key(
    rig: SimpleNamespace,
) -> None:
    """스냅샷을 다시 올리지 않고 같은 키로 다시 PUT 한다."""
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))

    with pytest.raises(ObjectStorageError):
        _publish(rig)

    assert _head_seq(rig) == 1
    pending = _state(rig).pending
    assert pending is not None
    snapshots = len(rig.store.keys("simulation/snapshots/"))

    outcome = _publish(rig)

    assert outcome.settled is not None
    assert rig.store.pointer_keys()[0] == pending.pointer_key
    assert len(rig.store.keys("simulation/snapshots/")) == snapshots


def test_a_dry_run_push_leaves_a_pending_pointer_alone(rig: SimpleNamespace) -> None:
    """`--dry-run` 은 앞 회차의 포인터도 내지 않는다. 있다는 사실만 돌려준다."""
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))
    with pytest.raises(ObjectStorageError):
        _publish(rig)
    before = _state(rig)
    assert before.pending is not None
    rig.store.calls.clear()

    outcome = engine.publish_generation(
        rig.client, rig.paths, exporter=rig.exporter, origin="manual", note="", dry_run=True
    )

    assert outcome.dry_run and outcome.settled is None and outcome.pointer is None
    assert outcome.pending_pointer == before.pending.pointer_key
    assert _head_seq(rig) == 1
    assert rig.store.puts() == []
    assert _state(rig) == before
    assert sync_state.treat_as_dirty(rig.simulation) is True


def test_a_failed_generation_write_after_landing_is_recovered(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """게시는 끝났는데 상태 파일을 못 썼다. 스스로 「세대 모름」 을 만들지 않는다."""
    _save(rig)
    original = sync_state.write_generation
    calls = []

    def full_on_the_second_write(path: Path, state: sync_state.GenerationState) -> None:
        calls.append(state)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        original(path, state)

    monkeypatch.setattr(sync_state, "write_generation", full_on_the_second_write)

    with pytest.raises(OSError, match="No space left"):
        _publish(rig)

    monkeypatch.setattr(sync_state, "write_generation", original)
    assert _head_seq(rig) == 2

    outcome = _publish(rig)

    assert outcome.decision is PushDecision.UP_TO_DATE
    assert _state(rig).base_seq == 2
    assert sync_state.treat_as_dirty(rig.simulation) is False


def test_a_failed_mark_clear_only_uploads_once_more(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """base 를 옮긴 뒤에 표시를 지운다. 사이에서 끊기면 같은 내용을 한 번 더 올릴 뿐이다."""
    _save(rig)
    original = sync_state.clear_dirty

    def full(*_args: object, **_kwargs: object) -> bool:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sync_state, "clear_dirty", full)

    with pytest.raises(OSError, match="No space left"):
        _publish(rig)

    monkeypatch.setattr(sync_state, "clear_dirty", original)
    assert _state(rig).base_seq == 2

    assert _publish(rig).published
    assert _head_seq(rig) == 3


@pytest.mark.parametrize(
    "failure",
    [
        Failure("put-object", "simulation/snapshots/"),
        Failure("put-object", "equipment/snapshots/"),
        Failure("put-object", manifest.HEAD_PREFIX),
    ],
    ids=["simulation-snapshot", "equipment-snapshot", "pointer"],
)
def test_a_crash_at_any_upload_step_leaves_the_previous_generation_whole(
    rig: SimpleNamespace, failure: Failure
) -> None:
    """포인터가 없으면 HEAD 는 앞 세대 그대로다. 새 pod 는 앞 세대를 온전히 받는다."""
    _save(rig, "simulation")
    _save(rig, "equipment")
    rig.store.failures.append(failure)

    with pytest.raises(ObjectStorageError):
        _publish(rig)

    assert _head_seq(rig) == 1
    rig.store.failures.clear()
    _wipe_disk(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.ok
    assert outcome.action == engine.ACTION_DOWNLOADED
    assert row_count(rig.simulation) == 10
    assert row_count(rig.equipment) == 10


def test_a_crash_while_exporting_touches_nothing_remote(rig: SimpleNamespace) -> None:
    _save(rig)
    before = dict(rig.store.objects)

    def broken(_dataset: DatasetName, _destination: Path) -> ExportedSnapshot:
        raise OSError(5, "복사 실패")

    with pytest.raises(OSError, match="복사 실패"):
        engine.publish_generation(
            rig.client, rig.paths, exporter=broken, origin="app", note="앱 저장"
        )

    assert rig.store.objects == before
    assert sync_state.treat_as_dirty(rig.simulation) is True


def test_a_generation_state_that_cannot_be_written_stops_before_the_pointer(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """적지 못하면 PUT 하지 않는다. 고아 스냅샷만 남고 다음 회차가 다시 한다."""
    _save(rig)

    def full(_path: Path, _state: sync_state.GenerationState) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sync_state, "write_generation", full)

    with pytest.raises(OSError, match="No space left"):
        _publish(rig)

    assert _head_seq(rig) == 1


def test_work_files_are_removed_after_a_cycle(rig: SimpleNamespace) -> None:
    _save(rig)
    _publish(rig)

    leftovers = [
        path.name for path in snapshot_export.scratch_dir().iterdir() if path.suffix == ".duckdb"
    ]

    assert leftovers == []


def test_a_head_that_moves_during_the_upload_stops_the_pointer(rig: SimpleNamespace) -> None:
    """올린 스냅샷은 지우지 않는다. 그 세대가 곧 복구 수단이다."""
    _save(rig)
    moved: list[str] = []

    def move_after_snapshot(operation: str, key: str) -> None:
        if operation == "list-objects-v2" and rig.store.puts("simulation/snapshots/000000000002"):
            if not moved:
                moved.append(_another_writer_publishes(rig))

    rig.store.before = move_after_snapshot

    outcome = _publish(rig)

    assert outcome.stop is PublishStop.REMOTE_MOVED
    state = _state(rig)
    assert state.unpublished is not None and state.unpublished.reason == engine.UNPUBLISHED_MOVED
    assert len(rig.store.keys("simulation/snapshots/")) == 2
    assert sync_state.treat_as_dirty(rig.simulation) is True

    rig.store.before = None
    assert _publish(rig).decision is PushDecision.BLOCKED_UNPUBLISHED


def test_a_fork_found_after_the_pointer_is_parked(rig: SimpleNamespace) -> None:
    _save(rig)

    def fork_on_pointer(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith(manifest.HEAD_PREFIX):
            _another_writer_publishes(rig)

    rig.store.before = fork_on_pointer

    outcome = _publish(rig)

    assert outcome.stop is PublishStop.FORKED
    state = _state(rig)
    assert state.unpublished is not None and state.unpublished.reason == engine.UNPUBLISHED_FORKED
    assert state.pending is None


def test_a_moved_remote_blocks_and_an_unknown_base_blocks(rig: SimpleNamespace) -> None:
    _save(rig)
    _another_writer_publishes(rig)

    assert _publish(rig).decision is PushDecision.PARENT_MOVED

    sync_state.write_generation(rig.paths.generation, sync_state.GenerationState())

    assert _publish(rig).decision is PushDecision.UNKNOWN_BASE


def test_an_empty_remote_is_not_filled_by_the_app(tmp_path: Path) -> None:
    paths = seed_pair(tmp_path)
    store = FakeStore()

    outcome = engine.publish_generation(
        fake_client(store),
        paths,
        exporter=engine.offline_exporter(paths),
        origin="app",
        note="앱 저장",
    )

    assert outcome.decision is PushDecision.REMOTE_EMPTY
    assert store.objects == {}


def test_a_missing_database_stops_the_publish(rig: SimpleNamespace) -> None:
    _save(rig)
    rig.simulation.unlink()

    assert _publish(rig).stop is PublishStop.LOCAL_MISSING


def test_an_interrupted_init_is_finished_by_running_it_again(tmp_path: Path) -> None:
    """이관 포인터의 답이 끊겨도 다시 돌리면 끝난다. 그 PC 도 그때 넘긴 쪽이 된다."""
    paths = seed_pair(tmp_path)
    store = FakeStore()
    client = fake_client(store)
    store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=True))
    exporter = engine.offline_exporter(paths)

    with pytest.raises(ObjectStorageError):
        engine.init_generation(client, paths, exporter=exporter, note="최초 이관")

    outcome = engine.init_generation(client, paths, exporter=exporter, note="최초 이관")

    assert outcome.settled is not None
    assert sync_state.read_generation(paths.generation).handed_over_utc is not None
    assert len(store.pointer_keys()) == 1


def test_a_dry_run_init_neither_finishes_nor_hands_over(tmp_path: Path) -> None:
    """끊긴 첫 세대가 남아 있어도 `--dry-run init` 은 게시하지 않고 넘긴 표시도 찍지 않는다."""
    paths = seed_pair(tmp_path)
    store = FakeStore()
    client = fake_client(store)
    store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))
    exporter = engine.offline_exporter(paths)
    with pytest.raises(ObjectStorageError):
        engine.init_generation(client, paths, exporter=exporter, note="최초 이관")
    before = sync_state.read_generation(paths.generation)
    assert before.pending is not None
    store.calls.clear()

    outcome = engine.init_generation(client, paths, exporter=exporter, note="", dry_run=True)

    assert outcome.dry_run and outcome.pending_pointer == before.pending.pointer_key
    assert store.pointer_keys() == []
    assert store.puts() == []
    assert sync_state.read_generation(paths.generation) == before


# --------------------------------------------------------------------------- 받기
def test_a_new_pod_receives_both_databases_and_raises_a_fence(rig: SimpleNamespace) -> None:
    _save(rig)
    assert _publish(rig).published
    _wipe_disk(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.ok
    assert outcome.action == engine.ACTION_DOWNLOADED
    assert row_count(rig.simulation) == 11
    head = engine.read_pointer(rig.client, rig.store.pointer_keys()[0])
    assert head.origin == "boot"
    assert head.seq == 3
    assert outcome.seq == 3
    assert _state(rig).base_pointer_key == head.pointer_key
    assert sync_state.treat_as_dirty(rig.simulation) is False
    assert sync_state.treat_as_dirty(rig.equipment) is False


def test_the_fence_stops_a_late_upload_from_the_old_pod(rig: SimpleNamespace) -> None:
    """끝나는 옛 pod 의 게시는 「HEAD 그대로인가」 에서 멈춘다. 벽이 없으면 새 pod 가 옛 세대다."""
    _save(rig)
    old_state = _state(rig)
    assert engine.boot_pull(rig.client, rig.paths).ok

    sync_state.write_generation(rig.paths.generation, old_state)

    outcome = _publish(rig)

    assert outcome.decision is PushDecision.PARENT_MOVED
    assert len(rig.store.keys("simulation/snapshots/")) == 1


def test_a_fence_without_an_answer_is_dropped_when_the_head_moves(rig: SimpleNamespace) -> None:
    """펜스는 잃을 것이 없다. 미게시로 옮기면 변경 없는 새 pod 가 `diverged` 로 영영 머문다."""
    _wipe_disk(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))
    assert engine.boot_pull(rig.client, rig.paths).kind == manifest.FAILURE_TIMEOUT
    assert _state(rig).pending is not None
    rig.store.failures.clear()
    _another_writer_publishes(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.ok
    assert outcome.action == engine.ACTION_DOWNLOADED
    assert _state(rig).unpublished is None
    assert _state(rig).pending is None


def test_a_fence_without_an_answer_is_dropped_in_a_fork_too(rig: SimpleNamespace) -> None:
    _wipe_disk(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))
    assert not engine.boot_pull(rig.client, rig.paths).ok
    rig.store.failures.clear()
    _another_writer_publishes(rig)
    head = rig.store.pointer_keys()[0]
    rig.store.objects[head.replace("abcdef01", "abcdef02")] = rig.store.objects[head]

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_FORKED
    assert _state(rig).unpublished is None


def test_a_real_generation_without_an_answer_is_still_parked(rig: SimpleNamespace) -> None:
    """저장을 든 세대는 그대로 미게시다 — 버리면 사람이 고를 자리가 사라진다."""
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=False))
    with pytest.raises(ObjectStorageError):
        _publish(rig)
    rig.store.failures.clear()
    _another_writer_publishes(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_DIVERGED
    assert _state(rig).unpublished is not None


def test_a_clean_local_on_the_same_generation_is_kept(rig: SimpleNamespace) -> None:
    calls_before = len(rig.store.keys())

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.action == engine.ACTION_KEPT
    assert len(rig.store.keys()) == calls_before + 1
    assert ("get-object", rig.store.keys("simulation/snapshots/")[0]) not in rig.store.operations()


def test_a_dirty_local_on_the_same_generation_is_kept_for_the_worker(rig: SimpleNamespace) -> None:
    """같은 디스크로 다시 뜬 pod — 일꾼이 올린다. 덮으면 그 저장이 사라진다."""
    _save(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.action == engine.ACTION_KEPT
    assert row_count(rig.simulation) == 11
    assert sync_state.treat_as_dirty(rig.simulation) is True


def test_a_clean_local_behind_the_remote_is_replaced_and_kept_as_a_backup(
    rig: SimpleNamespace,
) -> None:
    _another_writer_publishes(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.action == engine.ACTION_DOWNLOADED
    assert list(snapshot_export.backup_dir().glob("capa_simulation.duckdb.*"))


def test_a_dirty_local_behind_the_remote_stays(rig: SimpleNamespace) -> None:
    """변경이 있는데 어긋났다. 덮지 않고 머문다 — CI/CD 로 디스크를 비우면 풀린다."""
    _save(rig)
    _another_writer_publishes(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_DIVERGED
    assert row_count(rig.simulation) == 11


def test_a_local_without_a_generation_is_replaced(rig: SimpleNamespace) -> None:
    """컨테이너에서 세대 없는 DB 는 빈 시드뿐이다. 옛 파일은 superseded 로 물러난다."""
    expected = row_count(rig.simulation)
    add_row(rig.simulation)
    rig.paths.generation.unlink()
    for path in rig.paths.databases.values():
        sync_state.sidecar_path(path).unlink()

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.action == engine.ACTION_DOWNLOADED
    assert row_count(rig.simulation) == expected


def test_an_empty_remote_stays(tmp_path: Path) -> None:
    """이관 전. 빈 DB 로 떠서 정본을 덮는 길을 막는다."""
    paths = seed_pair(tmp_path)

    outcome = engine.boot_pull(fake_client(FakeStore()), paths)

    assert outcome.kind == manifest.FAILURE_REMOTE_EMPTY


def test_a_forked_remote_stays(rig: SimpleNamespace) -> None:
    _another_writer_publishes(rig)
    head = rig.store.pointer_keys()[0]
    rig.store.objects[head.replace("abcdef01", "abcdef02")] = rig.store.objects[head]

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_FORKED


def test_an_unreadable_generation_file_stays(rig: SimpleNamespace) -> None:
    rig.paths.generation.write_text("{ 깨진", encoding="utf-8")

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_DIVERGED


def test_one_broken_member_installs_nothing(rig: SimpleNamespace) -> None:
    """한쪽이라도 실패하면 아무것도 안 건드린다 — 두 DB 는 한 쌍이다."""
    _wipe_disk(rig)
    seed_database(rig.simulation, "simulation", rows=3)
    seed_database(rig.equipment, "equipment", rows=3)
    key = rig.store.keys("equipment/snapshots/")[0]
    rig.store.objects[key] = b"broken"

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_CORRUPT
    assert row_count(rig.simulation) == 3
    assert row_count(rig.equipment) == 3


def test_a_failed_second_install_restores_the_first(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _another_writer_publishes(rig)
    add_row(rig.simulation)
    original = snapshot_export.install_snapshot

    def second_fails(source: Path, database: Path) -> snapshot_export.InstallResult:
        if "equipment" in database.name:
            raise OSError(5, "둘째 설치 실패")
        return original(source, database)

    monkeypatch.setattr(snapshot_export, "install_snapshot", second_fails)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_OTHER
    assert row_count(rig.simulation) == 11


def test_a_snapshot_newer_than_the_code_stays(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """옛 코드가 새 스키마를 고쳐 정본을 더럽히는 길을 막는다. 받기 전에 포인터로 가른다."""
    monkeypatch.setattr(snapshot_export, "code_migration_version", lambda _dataset: 0)
    _wipe_disk(rig)
    rig.store.calls.clear()

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_SCHEMA_NEWER
    assert not any(op == "get-object" and "snapshots" in key for op, key in rig.store.operations())


def test_a_snapshot_gone_from_the_store_is_a_broken_generation(rig: SimpleNamespace) -> None:
    """손으로 지웠거나 정리 사고다. 「그 밖의 실패」 면 임시 화면에서 되돌리기로 닿지 못한다."""
    for key in rig.store.keys("equipment/snapshots/"):
        del rig.store.objects[key]
    _wipe_disk(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_CORRUPT


def test_too_little_disk_stays_before_downloading(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(_folder: Path, _needed: int) -> None:
        raise snapshot_export.DiskSpaceShort(100, 1)

    monkeypatch.setattr(snapshot_export, "require_free_space", full)
    _wipe_disk(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_DISK_FULL


def test_an_unreachable_store_is_a_word_not_a_trace(rig: SimpleNamespace) -> None:
    rig.store.failures.append(Failure("list-objects-v2", stderr=CONNECT_TEXT))

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_UNREACHABLE


def test_a_head_that_moves_during_the_download_starts_over(rig: SimpleNamespace) -> None:
    """받는 시간이 틈이다. 재확인이 없으면 옛 세대로 뜨고 HEAD 와 어긋난 채 돈다."""
    _wipe_disk(rig)
    moved: list[str] = []

    def move_after_download(operation: str, key: str) -> None:
        if operation == "get-object" and "equipment/snapshots/" in key and not moved:
            moved.append(_another_writer_publishes(rig))

    rig.store.before = move_after_download

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.ok
    assert outcome.seq == 3
    assert engine.read_pointer(rig.client, moved[0]).seq == 2


def test_a_fence_that_forks_stays(rig: SimpleNamespace) -> None:
    def fork_on_fence(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith(manifest.HEAD_PREFIX):
            _another_writer_publishes(rig)

    rig.store.before = fork_on_fence

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.kind == manifest.FAILURE_FORKED


def test_leftover_work_files_do_not_fail_the_disk_check(rig: SimpleNamespace) -> None:
    """앞 시도가 끊기며 남긴 파일이 디스크를 차지하면 받기가 거짓으로 실패한다."""
    leftover = snapshot_export.prepare_scratch() / "simulation-download-old.duckdb"
    leftover.write_bytes(b"x")
    _wipe_disk(rig)

    assert engine.boot_pull(rig.client, rig.paths).ok
    assert not leftover.exists()


def test_a_pending_pointer_on_a_kept_disk_is_finished_at_boot(rig: SimpleNamespace) -> None:
    """같은 디스크로 다시 뜬 pod — 앞 프로세스가 끝내지 못한 게시를 마저 한다."""
    _save(rig)
    rig.store.failures.append(Failure("put-object", manifest.HEAD_PREFIX, stored=True))
    with pytest.raises(ObjectStorageError):
        _publish(rig)

    outcome = engine.boot_pull(rig.client, rig.paths)

    assert outcome.action == engine.ACTION_KEPT
    assert sync_state.treat_as_dirty(rig.simulation) is False


def test_the_watch_sees_a_head_that_moved_while_idle(rig: SimpleNamespace) -> None:
    """변경이 없으면 일꾼은 안 올린다. 보지 않으면 옛 데이터로 도는 줄 아무도 모른다."""
    assert engine.watch_head(rig.client, rig.paths).decision is PushDecision.UP_TO_DATE

    _another_writer_publishes(rig)

    assert engine.watch_head(rig.client, rig.paths).decision is PushDecision.PARENT_MOVED


# --------------------------------------------------------------------------- 사내 PC
def test_rollback_points_at_the_old_members_and_a_new_pod_receives_them(
    rig: SimpleNamespace,
) -> None:
    """망가진 세대가 게시돼도 앞 세대로 돌아갈 길이 있다. 지우지 않고 앞으로 간다."""
    _save(rig)
    assert _publish(rig).published

    pointer = engine.rollback(rig.client, to_seq=1, note="되돌림")

    assert pointer.seq == 3
    assert pointer.origin == "rollback"
    _wipe_disk(rig)
    assert engine.boot_pull(rig.client, rig.paths).ok
    assert row_count(rig.simulation) == 10


def test_rollback_resolves_a_fork(rig: SimpleNamespace) -> None:
    """갈라져도 맨 위 seq + 1 이라 풀린다."""
    _another_writer_publishes(rig)
    head = rig.store.pointer_keys()[0]
    rig.store.objects[head.replace("abcdef01", "abcdef02")] = rig.store.objects[head]

    with pytest.raises(ValueError, match="둘 이상"):
        engine.rollback(rig.client, to_seq=2, note="되돌림")

    pointer = engine.rollback(rig.client, to_seq=2, token="abcdef01", note="되돌림")

    assert pointer.seq == 3
    _wipe_disk(rig)
    assert engine.boot_pull(rig.client, rig.paths).ok


def test_rollback_refuses_a_generation_whose_snapshot_is_gone(rig: SimpleNamespace) -> None:
    del rig.store.objects[rig.store.keys("equipment/snapshots/")[0]]

    with pytest.raises(ValueError, match="저장소에 없습니다"):
        engine.rollback(rig.client, to_seq=1, note="되돌림")


def test_a_rollback_keeps_the_writer_mark(rig: SimpleNamespace) -> None:
    """되돌린 HEAD 도 운영 앱의 정본이다. `manual` 이면 표지 없는 PC 가 그 위로 올린다."""
    _save(rig)
    assert _publish(rig).published

    pointer = engine.rollback(rig.client, to_seq=1, note="되돌림")

    assert pointer.origin == "rollback"
    assert manifest.writer_taken_over(pointer) is True


def _newer_equipment_generation(rig: SimpleNamespace) -> manifest.Pointer:
    """남이 설비 DB 를 올려 HEAD 를 옮긴다 — 내 미게시 세대의 이어 적은 멤버보다 앞선다."""
    head = engine.read_pointer(rig.client, rig.store.pointer_keys()[0])
    body = b"newer equipment"
    member = Member(
        seq=head.seq + 1,
        snapshot_key=manifest.snapshot_key(
            "equipment", head.seq + 1, created_at_utc="2026-11-07T00:00:00Z", sha256="ab" * 32
        ),
        sha256="ab" * 32,
        md5_base64="",
        size_bytes=len(body),
        source_db_bytes=len(body),
        migration_version=1,
    )
    rig.store.objects[member.snapshot_key] = body
    pointer = manifest.next_pointer(
        head,
        members={**head.members, "equipment": member},
        origin="app",
        token="abcdef02",
        app_version="demo",
        author="demo@other",
        created_at_utc="2026-11-07T00:00:00Z",
        note="",
    )
    rig.store.objects[pointer.pointer_key] = manifest.pointer_to_json(pointer).encode("utf-8")
    return pointer


def _park_with_a_newer_equipment(rig: SimpleNamespace) -> manifest.Pointer:
    """시뮬레이션 DB 만 바꾼 내 세대가 미게시로 남고, 그 사이 설비 DB 가 앞서 있다."""
    _save(rig)
    moved: list[manifest.Pointer] = []

    def move_after_snapshot(operation: str, key: str) -> None:
        if operation == "list-objects-v2" and rig.store.puts("simulation/snapshots/000000000002"):
            if not moved:
                moved.append(_newer_equipment_generation(rig))

    rig.store.before = move_after_snapshot
    assert _publish(rig).stop is PublishStop.REMOTE_MOVED
    rig.store.before = None
    return moved[0]


def test_promoting_does_not_undo_the_other_databases_newer_save(rig: SimpleNamespace) -> None:
    """이어 적은 멤버는 그때의 앞 세대 값이다. 그대로 적으면 앞선 설비 저장이 HEAD 에서 빠진다."""
    moved = _park_with_a_newer_equipment(rig)

    promoted = engine.resolve_keep_mine(rig.client, rig.paths)

    assert promoted.members["equipment"] == moved.members["equipment"]
    assert promoted.members["simulation"].seq == 2
    assert promoted.members["simulation"] != moved.members["simulation"]


def test_a_promotion_that_took_the_remote_member_leaves_the_pc_behind_on_purpose(
    rig: SimpleNamespace,
) -> None:
    """이 PC 의 설비 DB 는 그 멤버가 아니다. base 가 HEAD 면 `pull` 이 받지 않는다."""
    _park_with_a_newer_equipment(rig)

    promoted = engine.resolve_keep_mine(rig.client, rig.paths)

    state = _state(rig)
    assert state.base_pointer_key != promoted.pointer_key
    assert engine.plan_pull(rig.client, rig.paths, force=False).decision is PullDecision.DOWNLOAD


def test_a_promotion_of_a_snapshot_that_is_gone_publishes_nothing(rig: SimpleNamespace) -> None:
    """확인 없이 게시하면 HEAD 가 없는 객체를 가리켜 새 pod 가 뜨지 못한다."""
    _park_with_a_newer_equipment(rig)
    for key in rig.store.keys("simulation/snapshots/000000000002"):
        del rig.store.objects[key]
    before = rig.store.pointer_keys()

    with pytest.raises(ValueError, match="스냅샷이 저장소에 없습니다"):
        engine.resolve_keep_mine(rig.client, rig.paths)

    assert rig.store.pointer_keys() == before
    assert _state(rig).unpublished is not None


def test_a_promotion_with_nothing_newer_keeps_every_member(rig: SimpleNamespace) -> None:
    """앞선 멤버가 없으면 내 세대 그대로다. 그때는 이 PC 의 파일이 HEAD 와 같다."""
    _save(rig)
    moved: list[str] = []

    def move_after_snapshot(operation: str, key: str) -> None:
        if operation == "list-objects-v2" and rig.store.puts("simulation/snapshots/000000000002"):
            if not moved:
                moved.append(_another_writer_publishes(rig))

    rig.store.before = move_after_snapshot
    assert _publish(rig).stop is PublishStop.REMOTE_MOVED
    rig.store.before = None

    promoted = engine.resolve_keep_mine(rig.client, rig.paths)

    assert _state(rig).base_pointer_key == promoted.pointer_key


def test_dropping_my_generation_leaves_the_pull_open(rig: SimpleNamespace) -> None:
    """내 세대를 버리면 표시도 함께 내린다 — 남기면 `pull` 이 변경이 있다며 막는다. 차례가 거꾸로면
    표시를 내리다 죽을 때 다시 돌릴 미게시 표지가 사라진다."""
    _park_with_a_newer_equipment(rig)
    assert sync_state.treat_as_dirty(rig.simulation) is True

    engine.resolve_keep_remote(rig.paths)

    state = _state(rig)
    assert state.unpublished is None and state.pending is None
    assert not any(sync_state.treat_as_dirty(path) for path in rig.paths.databases.values())
    assert engine.plan_pull(rig.client, rig.paths, force=False).proceeds


def test_a_failed_mark_clear_keeps_the_generation_to_drop(
    rig: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표시를 내리다 실패하면 미게시 표지를 그대로 두어 `resolve` 를 다시 돌릴 수 있다."""
    _park_with_a_newer_equipment(rig)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(sync_state, "adopt_clean", fail)

    with pytest.raises(OSError):
        engine.resolve_keep_remote(rig.paths)

    assert _state(rig).unpublished is not None


def test_rollback_refuses_an_unknown_generation(rig: SimpleNamespace) -> None:
    with pytest.raises(ValueError, match="찾지 못했습니다"):
        engine.rollback(rig.client, to_seq=99, note="되돌림")


def test_prune_deletes_snapshots_before_pointers_and_can_yield(rig: SimpleNamespace) -> None:
    for value in range(8):
        _save(rig, value=value)
        assert _publish(rig).published
    for key in rig.store.keys():
        if "__s000000000001__" in key or "/000000000001__" in key:
            rig.store.modified[key] = "2026-10-01T00:00:00+00:00"
    rig.store.modified[rig.store.keys("equipment/snapshots/")[0]] = rig.store.now
    rig.store.calls.clear()

    stopped = engine.prune(rig.client, keep_days=1, should_stop=lambda: True)
    assert stopped.interrupted and stopped.deleted == 0

    outcome = engine.prune(rig.client, keep_days=1)

    deleted = [key for op, key in rig.store.operations() if op == "delete-object"]
    assert deleted[0].startswith("simulation/snapshots/000000000001__")
    assert deleted[-1].startswith(manifest.HEAD_PREFIX)
    assert outcome.deleted == len(deleted)
    assert rig.store.keys("equipment/snapshots/")


def _ten_aged_generations(rig: SimpleNamespace) -> None:
    """세대 열 개 — 정리가 앞 세대를 지울 만큼 앞선 것들을 낡게 둔다."""
    for value in range(9):
        _save(rig, value=value)
        assert _publish(rig).published
    head = rig.store.pointer_keys()[0]
    for key in rig.store.keys():
        rig.store.modified[key] = "2026-10-01T00:00:00+00:00"
    rig.store.modified[head] = rig.store.now
    rig.store.calls.clear()


def test_a_rollback_during_the_prune_stops_the_deletions(rig: SimpleNamespace) -> None:
    """정리가 판정한 뒤 들어온 rollback 이 보존 밖 세대를 HEAD 로 되살린다. 옛 판정대로 끝까지
    지우면 그 HEAD 의 멤버가 사라지고 새 pod 가 `corrupt` 로 머문다."""
    _ten_aged_generations(rig)
    rolled: list[manifest.Pointer] = []

    def roll_back_on_first_delete(operation: str, key: str) -> None:
        if operation == "delete-object" and not rolled:
            rolled.append(engine.rollback(rig.client, to_seq=5, note="되돌림"))

    rig.store.before = roll_back_on_first_delete

    outcome = engine.prune(rig.client, keep_days=1)

    rig.store.before = None
    assert outcome.interrupted
    assert outcome.deleted == 1
    assert rolled[0].pointer_key == rig.store.pointer_keys()[0]
    _wipe_disk(rig)
    assert engine.boot_pull(rig.client, rig.paths).ok

    # 다음 정리는 새 HEAD 로 다시 판정해 그 멤버를 지킨다.
    assert not engine.prune(rig.client, keep_days=1).interrupted
    _wipe_disk(rig)
    assert engine.boot_pull(rig.client, rig.paths).ok


def test_a_fork_during_the_prune_stops_the_deletions(rig: SimpleNamespace) -> None:
    """갈라진 원격은 사람이 볼 물증이다 — 판정 뒤에 갈라져도 더 지우지 않는다."""
    _ten_aged_generations(rig)
    forked: list[str] = []

    def fork_on_first_delete(operation: str, key: str) -> None:
        if operation == "delete-object" and not forked:
            head = rig.store.pointer_keys()[0]
            token = head.rsplit("__", 1)[-1].removesuffix(".json")
            forked.append(head.replace(token, "abcdef09"))
            rig.store.objects[forked[0]] = rig.store.objects[head]

    rig.store.before = fork_on_first_delete

    outcome = engine.prune(rig.client, keep_days=1)

    rig.store.before = None
    assert outcome.interrupted
    assert outcome.deleted == 1


def test_a_rollback_says_so_when_a_member_went_away_after_its_pointer(
    rig: SimpleNamespace,
) -> None:
    """포인터를 낸 뒤 멤버가 사라졌으면 성공으로 끝내지 않는다 — 그 HEAD 로는 새 pod 가 못 뜬다."""
    _save(rig)
    assert _publish(rig).published
    member = rig.store.keys("simulation/snapshots/000000000001")[0]

    def lose_the_member(operation: str, key: str) -> None:
        if operation == "put-object" and key.startswith(manifest.HEAD_PREFIX):
            rig.store.objects.pop(member, None)

    rig.store.before = lose_the_member

    with pytest.raises(ValueError, match="다른 세대로 다시 rollback"):
        engine.rollback(rig.client, to_seq=1, note="되돌림")

    rig.store.before = None
    assert _head_seq(rig) == 3


def test_prune_never_lists_outside_its_prefixes(rig: SimpleNamespace) -> None:
    rig.store.objects["access/access_list.json"] = b"{}"
    rig.store.calls.clear()

    engine.prune(rig.client, include_orphans=True)

    prefixes = {key for op, key in rig.store.operations() if op == "list-objects-v2"}
    assert prefixes == set(manifest.PRUNE_PREFIXES)
    assert "access/access_list.json" in rig.store.objects


def test_the_engine_loads_without_streamlit() -> None:
    """일꾼 · 시작 스크립트가 부른다. Streamlit 이 딸려 오면 경계가 무너진다."""
    code = (
        "import sys; import capa_simulation.object_sync_engine; "
        "import capa_simulation.object_sync_worker; "
        "raise SystemExit(1 if 'streamlit' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
