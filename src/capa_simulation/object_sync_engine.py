# Purpose: 두 DB 한 쌍의 세대 게시·받기·되돌리기·정리 차례를 Streamlit 없이 돌려 결과로 준다.

"""사람이 돌리는 스크립트(`scripts/sync_object_storage.py`)와 앱 일꾼이 함께 쓰는 동기화 코어.

판정은 `services/object_storage_manifest.py`, 스냅샷 만들기·설치는 `persistence/snapshot_export.py`,
`aws` 호출은 `io/object_storage.py`, 변경 표시·게시 상태는 `persistence/sync_state.py` 가 맡는다. 이
모듈은 그 넷을 **유실을 막는 차례**로 잇기만 한다.

**게시 차례**(`publish_generation`):

1. 회차 머리 — 앞 회차가 남긴 `pending` 을 먼저 가린다(`_settle_pending`).
2. 목록 한 번 → 판정(`decide_push`).
3. 바뀐 DB 마다 스냅샷을 떠서 올리고 ETag 를 대조한다(시뮬 → 설비).
4. 목록을 다시 본다. 그 사이 남이 올렸으면 포인터를 게시하지 않고 미게시로 남긴다.
5. 게시 상태 파일에 `pending` 을 적고 포인터를 PUT 한다 ← 이 PUT 하나가 게시다.
6. 목록을 다시 보고 갈라졌는지 본다. 이 확인이 실패해도 게시 실패가 아니다 — 다음 회차가 가린다.
7. `base` 를 새 세대로 옮기고, 이번 세대가 실제로 담은 DB 의 표시만 비교 후 지운다.

어느 자리에서 죽어도 포인터가 없으면 HEAD 는 앞 세대 그대로이고 고아 스냅샷만 남는다. 포인터가
들어갔는데 답이 끊겼으면 `pending` 이 그 사실을 들고 있어 다음 회차가 자기 포인터를 남의 것으로
읽지 않는다.

print 도 종료 코드도 내지 않는다. 결과를 값으로 돌려주고, 사람이 읽을 글은 부르는 쪽이 그 결과로
찍는다. 진행 중에 찍어야 하는 줄(스냅샷을 떴다·올렸다)은 `report` 로 구조화된 사건을 넘긴다.
Streamlit 을 import 하지 않고 `subprocess` 도 직접 부르지 않는다 — 앱의 `subprocess` 자리는
`io/object_storage.py` 다.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Final, TypeAlias

from capa_simulation import settings
from capa_simulation.io import object_storage
from capa_simulation.io.object_storage import (
    ObjectStorageClient,
    ObjectStorageError,
    classify_failure,
)
from capa_simulation.persistence import snapshot_export, sync_state
from capa_simulation.persistence.snapshot_export import (
    ExportResult,
    InstallResult,
    SnapshotRejected,
)
from capa_simulation.persistence.sync_state import (
    DirtyMark,
    GenerationState,
    PendingPublish,
    UnpublishedGeneration,
)
from capa_simulation.services import object_storage_manifest as manifest
from capa_simulation.services.korean_particle import with_object_particle
from capa_simulation.services.object_storage_manifest import (
    DATASET_NAMES,
    FAILURE_CORRUPT,
    FAILURE_DIVERGED,
    FAILURE_FORKED,
    FAILURE_OTHER,
    FAILURE_REMOTE_EMPTY,
    FAILURE_SCHEMA_NEWER,
    BootDecision,
    DatasetName,
    Member,
    Origin,
    Pointer,
    PrunePlan,
    PullDecision,
    PushDecision,
)
from capa_simulation.settings import APP_VERSION

# HEAD 를 고르는 데 보는 포인터 수. 포인터 키가 내림차순이라 첫 쪽 몇 개가 언제나 최신이다.
HEAD_LIST_KEYS: Final = 8
# 받는 동안 HEAD 가 움직였을 때 처음부터 다시 받는 횟수.
BOOT_ATTEMPTS: Final = 3
_MIB: Final = 1024 * 1024
DISK_MARGIN_BYTES: Final = 200 * _MIB
DISK_MARGIN_RATIO: Final = 1.2
UNPUBLISHED_MOVED: Final = "moved"
UNPUBLISHED_FORKED: Final = "forked"
ORIGIN_NOTE_BOOT: Final = "시작 펜스"


@dataclass(frozen=True)
class SyncPaths:
    """두 DB 의 자리. 게시 상태 파일은 그 옆이다."""

    databases: Mapping[DatasetName, Path]

    @property
    def generation(self) -> Path:
        return sync_state.generation_path(self.databases["simulation"])

    @property
    def registry(self) -> dict[Path, DatasetName]:
        """`sync_state.enable` 에 넘기는 꼴."""
        return {path: name for name, path in self.databases.items()}


def default_paths() -> SyncPaths:
    return SyncPaths(
        {"simulation": settings.DUCKDB_PATH, "equipment": settings.EQUIPMENT_DUCKDB_PATH}
    )


@dataclass(frozen=True)
class RemoteHead:
    """원격 HEAD 키와 분기 물증. 같은 목록 한 번에서 나온다."""

    head_key: str | None
    forked: tuple[str, ...]

    @property
    def head_seq(self) -> int | None:
        return None if self.head_key is None else manifest.seq_from_pointer_key(self.head_key)


def read_remote_head(client: ObjectStorageClient) -> RemoteHead:
    """원격 HEAD 와 분기를 **목록 한 번**으로 읽는다. 따로 물으면 aws 호출만 는다."""
    records = client.list_objects(manifest.HEAD_PREFIX, max_keys=HEAD_LIST_KEYS)
    keys = [record.key for record in records]
    return RemoteHead(head_key=manifest.select_head_key(keys), forked=manifest.detect_fork(keys))


def read_pointer(
    client: ObjectStorageClient, key: str, *, scratch_dir: Path | None = None
) -> Pointer:
    text = client.get_text(key, scratch_dir=scratch_dir or snapshot_export.prepare_scratch())
    return manifest.pointer_from_json(text, pointer_key=key)


def _base_pointer(state: GenerationState) -> Pointer | None:
    if state.base_pointer_key is None or state.base_pointer_json is None:
        return None
    return manifest.pointer_from_json(state.base_pointer_json, pointer_key=state.base_pointer_key)


# --------------------------------------------------------------------------- 올리기
@dataclass(frozen=True)
class ExportedSnapshot:
    """뜬 스냅샷 하나와, 그 스냅샷이 담은 변경 번호."""

    export: ExportResult
    observed: DirtyMark
    lock_seconds: float = 0.0


Exporter: TypeAlias = Callable[[DatasetName, Path], ExportedSnapshot]


def offline_exporter(paths: SyncPaths) -> Exporter:
    """앱을 끈 자리의 내보내기 — ATTACH 복사(`snapshot_export` 머리 설명)."""

    def export(dataset: DatasetName, destination: Path) -> ExportedSnapshot:
        database_path = paths.databases[dataset]
        observed = sync_state.read_dirty_mark(database_path)
        return ExportedSnapshot(
            snapshot_export.export_snapshot(database_path, destination), observed
        )

    return export


class PublishStop(str, Enum):
    """게시를 멈춘 사유. 올라간 스냅샷은 어느 경우에도 지우지 않는다."""

    LOCAL_MISSING = "local_missing"
    REMOTE_MOVED = "remote_moved"
    FORKED = "forked"


@dataclass(frozen=True)
class SnapshotExported:
    """스냅샷을 떴다(아직 올리지 않았다)."""

    dataset: DatasetName
    export: ExportResult


@dataclass(frozen=True)
class SnapshotUploaded:
    """스냅샷을 올렸다(포인터는 아직이다)."""

    dataset: DatasetName
    snapshot_key: str


PublishProgress: TypeAlias = SnapshotExported | SnapshotUploaded
Report: TypeAlias = Callable[[PublishProgress], None]


@dataclass(frozen=True)
class PublishOutcome:
    """회차 하나의 결과."""

    decision: PushDecision
    head_seq: int | None = None
    published: bool = False
    dry_run: bool = False
    stop: PublishStop | None = None
    pointer: Pointer | None = None
    uploaded: Mapping[DatasetName, ExportResult] = field(default_factory=dict)
    lock_seconds: float = 0.0
    transfer_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    # 포인터를 PUT 했는데 들어간 것을 아직 못 봤다. 다음 회차가 가린다 — 게시 실패가 아니다.
    confirm_deferred: bool = False
    # 앞 회차가 남긴 세대를 이번 회차가 마무리했다.
    settled: Pointer | None = None

    @property
    def seq(self) -> int | None:
        return None if self.pointer is None else self.pointer.seq


class _Settle(Enum):
    NOTHING = "nothing"
    FINISHED = "finished"
    UNCONFIRMED = "unconfirmed"
    PARKED = "parked"


def _finish_publish(paths: SyncPaths, state: GenerationState) -> tuple[GenerationState, Pointer]:
    """게시 끝 — base 를 옮긴 뒤에 표시를 지운다. 차례가 거꾸로면 그 사이 죽을 때 표시를 잃는다.

    표시만 남으면 같은 내용을 한 번 더 올릴 뿐이다. 이번 세대가 담지 않은(이어 적은) DB 의 표시는
    건드리지 않는다 — 회차 중에 그쪽에 들어온 저장이 있을 수 있다.
    """
    pending = state.pending
    assert pending is not None
    pointer = manifest.pointer_from_json(pending.pointer_json, pointer_key=pending.pointer_key)
    updated = sync_state.with_base(
        state,
        pointer_key=pointer.pointer_key,
        seq=pointer.seq,
        pointer_json=pending.pointer_json,
    )
    sync_state.write_generation(paths.generation, updated)
    for name, observed in pending.observed.items():
        sync_state.clear_dirty(paths.databases[name], observed=observed, dataset=name)
    return updated, pointer


def _park_pending(paths: SyncPaths, state: GenerationState, reason: str) -> GenerationState:
    """게시하지 못한 세대로 옮긴다. 판정이 BLOCKED_UNPUBLISHED 로 멈춘다.

    펜스는 옮기지 않고 버린다(`observed` 가 비었다) — 담은 저장이 없어 잃을 것이 없고, 다시 받으면
    끝날 일이다. 옮기면 변경 없는 새 pod 가 「원격과 어긋남」 으로 머문다.
    """
    pending = state.pending
    assert pending is not None
    unpublished = (
        UnpublishedGeneration(
            pointer_json=pending.pointer_json, reason=reason, observed=pending.observed
        )
        if pending.observed
        else None
    )
    updated = replace(state, pending=None, unpublished=unpublished)
    sync_state.write_generation(paths.generation, updated)
    return updated


def _settle_pending(
    client: ObjectStorageClient,
    paths: SyncPaths,
    state: GenerationState,
    remote: RemoteHead,
    *,
    scratch_dir: Path,
) -> tuple[_Settle, GenerationState, RemoteHead, Pointer | None]:
    """앞 회차가 포인터를 PUT 하다 끝났다 — 결과를 가른다.

    - HEAD 가 그 포인터면 게시는 된 것이다. 차례 7 만 마저 한다.
    - HEAD 가 아직 base 면 안 들어간 것이다. **같은 키로** 다시 PUT 한다(스냅샷은 다시 안 올린다).
    - 그 밖이면 남이 앞섰거나 갈라졌다. 미게시로 옮긴다(펜스는 버린다 — `_park_pending`).
    """
    pending = state.pending
    if pending is None:
        return _Settle.NOTHING, state, remote, None
    if remote.forked:
        return _Settle.PARKED, _park_pending(paths, state, UNPUBLISHED_FORKED), remote, None
    if remote.head_key == pending.pointer_key:
        updated, pointer = _finish_publish(paths, state)
        return _Settle.FINISHED, updated, remote, pointer
    if remote.head_key != state.base_pointer_key:
        return _Settle.PARKED, _park_pending(paths, state, UNPUBLISHED_MOVED), remote, None
    client.put_text(pending.pointer_key, pending.pointer_json, scratch_dir=scratch_dir)
    after = read_remote_head(client)
    if after.forked:
        return _Settle.PARKED, _park_pending(paths, state, UNPUBLISHED_FORKED), after, None
    if after.head_key != pending.pointer_key:
        return _Settle.UNCONFIRMED, state, after, None
    updated, pointer = _finish_publish(paths, state)
    return _Settle.FINISHED, updated, after, pointer


def plan_push(
    client: ObjectStorageClient, paths: SyncPaths, *, scratch_dir: Path | None = None
) -> tuple[PushDecision, RemoteHead, GenerationState, dict[DatasetName, bool]]:
    """올려도 되는지 판정한다. `status` 도 같은 판정을 찍는다. 아무것도 고치지 않는다."""
    state = sync_state.read_generation(paths.generation)
    remote = read_remote_head(client)
    dirty = {name: sync_state.treat_as_dirty(paths.databases[name]) for name in DATASET_NAMES}
    decision = manifest.decide_push(
        head_key=remote.head_key,
        forked=bool(remote.forked),
        base_pointer_key=state.base_pointer_key,
        dirty=any(dirty.values()),
        unpublished=state.unpublished is not None,
    )
    return decision, remote, state, dirty


def publish_generation(
    client: ObjectStorageClient,
    paths: SyncPaths,
    *,
    exporter: Exporter,
    origin: Origin,
    note: str,
    dry_run: bool = False,
    report: Report | None = None,
    scratch_dir: Path | None = None,
) -> PublishOutcome:
    """변경이 있으면 새 세대를 게시한다. 차례는 모듈 설명 그대로다."""
    started = time.perf_counter()
    scratch = scratch_dir or snapshot_export.prepare_scratch()
    state = sync_state.read_generation(paths.generation)
    remote = read_remote_head(client)
    settle, state, remote, settled = _settle_pending(
        client, paths, state, remote, scratch_dir=scratch
    )
    if settle is _Settle.UNCONFIRMED:
        return PublishOutcome(
            decision=PushDecision.PUBLISH,
            head_seq=remote.head_seq,
            confirm_deferred=True,
            elapsed_seconds=_since(started),
        )
    dirty = {name: sync_state.treat_as_dirty(paths.databases[name]) for name in DATASET_NAMES}
    decision = manifest.decide_push(
        head_key=remote.head_key,
        forked=bool(remote.forked),
        base_pointer_key=state.base_pointer_key,
        dirty=any(dirty.values()),
        unpublished=state.unpublished is not None,
    )
    if decision is not PushDecision.PUBLISH:
        return PublishOutcome(
            decision=decision,
            head_seq=remote.head_seq,
            settled=settled,
            elapsed_seconds=_since(started),
        )
    parent = _base_pointer(state)
    if parent is None:
        return PublishOutcome(
            decision=PushDecision.UNKNOWN_BASE,
            head_seq=remote.head_seq,
            settled=settled,
            elapsed_seconds=_since(started),
        )
    outcome = _publish_members(
        client,
        paths,
        state,
        parent=parent,
        changed=tuple(name for name in DATASET_NAMES if dirty[name]),
        exporter=exporter,
        origin=origin,
        note=note,
        dry_run=dry_run,
        report=report,
        scratch=scratch,
        started=started,
    )
    return replace(outcome, settled=settled)


def init_generation(
    client: ObjectStorageClient,
    paths: SyncPaths,
    *,
    exporter: Exporter,
    note: str,
    keep_writer: bool = False,
    dry_run: bool = False,
    report: Report | None = None,
    scratch_dir: Path | None = None,
) -> PublishOutcome:
    """빈 저장소의 첫 세대. 이 뒤로 이 PC 는 쓰는 쪽이 아니다(`handed_over_utc`).

    이미 HEAD 가 있으면 건드리지 않는다. `keep_writer` 는 개발 버킷 시험용이다.
    """
    started = time.perf_counter()
    scratch = scratch_dir or snapshot_export.prepare_scratch()
    state = sync_state.read_generation(paths.generation)
    remote = read_remote_head(client)
    settle, state, remote, settled = _settle_pending(
        client, paths, state, remote, scratch_dir=scratch
    )
    if settle is _Settle.UNCONFIRMED:
        return PublishOutcome(
            decision=PushDecision.PUBLISH,
            head_seq=remote.head_seq,
            confirm_deferred=True,
            elapsed_seconds=_since(started),
        )
    if remote.head_key is not None:
        if settled is not None:
            _hand_over(paths, keep_writer=keep_writer)
        return PublishOutcome(
            decision=PushDecision.UP_TO_DATE,
            head_seq=remote.head_seq,
            settled=settled,
            elapsed_seconds=_since(started),
        )
    outcome = _publish_members(
        client,
        paths,
        state,
        parent=None,
        changed=DATASET_NAMES,
        exporter=exporter,
        origin="init",
        note=note,
        dry_run=dry_run,
        report=report,
        scratch=scratch,
        started=started,
    )
    if outcome.published:
        _hand_over(paths, keep_writer=keep_writer)
    return outcome


def _hand_over(paths: SyncPaths, *, keep_writer: bool) -> None:
    if keep_writer:
        return
    state = sync_state.read_generation(paths.generation)
    sync_state.write_generation(
        paths.generation, replace(state, handed_over_utc=snapshot_export.utc_timestamp())
    )


def _publish_members(
    client: ObjectStorageClient,
    paths: SyncPaths,
    state: GenerationState,
    *,
    parent: Pointer | None,
    changed: tuple[DatasetName, ...],
    exporter: Exporter,
    origin: Origin,
    note: str,
    dry_run: bool,
    report: Report | None,
    scratch: Path,
    started: float,
) -> PublishOutcome:
    head_seq = None if parent is None else parent.seq
    seq = 1 if parent is None else parent.seq + 1
    exports: dict[DatasetName, ExportedSnapshot] = {}
    work_paths: list[Path] = []
    try:
        for name in changed:
            if not paths.databases[name].exists():
                return PublishOutcome(
                    decision=PushDecision.PUBLISH,
                    head_seq=head_seq,
                    stop=PublishStop.LOCAL_MISSING,
                    elapsed_seconds=_since(started),
                )
            work = snapshot_export.unique_work_path(scratch, name, "export")
            work_paths.append(work)
            exports[name] = exporter(name, work)
            if report is not None:
                report(SnapshotExported(dataset=name, export=exports[name].export))
        lock_seconds = sum(item.lock_seconds for item in exports.values())
        results = {name: item.export for name, item in exports.items()}
        created_at = snapshot_export.utc_timestamp()
        members: dict[DatasetName, Member] = {} if parent is None else dict(parent.members)
        for name, result in results.items():
            members[name] = Member(
                seq=seq,
                snapshot_key=manifest.snapshot_key(
                    name, seq, created_at_utc=created_at, sha256=result.sha256_hex
                ),
                sha256=result.sha256_hex,
                md5_base64=result.md5_base64,
                size_bytes=result.size_bytes,
                source_db_bytes=result.source_bytes,
                migration_version=result.migration_version,
            )
        pointer = manifest.next_pointer(
            parent,
            members=members,
            origin=origin,
            token=uuid.uuid4().hex[:8],
            app_version=APP_VERSION,
            author=snapshot_export.author_label(),
            created_at_utc=created_at,
            note=note,
        )
        if dry_run:
            return PublishOutcome(
                decision=PushDecision.PUBLISH,
                head_seq=head_seq,
                dry_run=True,
                pointer=pointer,
                uploaded=results,
                lock_seconds=lock_seconds,
                elapsed_seconds=_since(started),
            )

        transfer_started = time.perf_counter()
        for name, result in results.items():
            uploaded = client.put_file(
                members[name].snapshot_key,
                result.path,
                content_md5_base64=result.md5_base64,
                metadata={"sha256": result.sha256_hex, "seq": str(seq)},
            )
            object_storage.assert_single_put_etag(uploaded.etag, local_md5_hex=result.md5_hex)
            if report is not None:
                report(SnapshotUploaded(dataset=name, snapshot_key=members[name].snapshot_key))

        observed = {name: item.observed for name, item in exports.items()}
        pending = PendingPublish(
            pointer_key=pointer.pointer_key,
            pointer_json=manifest.pointer_to_json(pointer),
            observed=observed,
        )
        # 스냅샷을 올린 뒤 다시 확인한다. 이 사이에 남이 올렸으면 포인터를 게시하지 않는다.
        current = read_remote_head(client)
        if current.head_key != (None if parent is None else parent.pointer_key):
            _park_pending(paths, replace(state, pending=pending), UNPUBLISHED_MOVED)
            return PublishOutcome(
                decision=PushDecision.PUBLISH,
                head_seq=current.head_seq,
                stop=PublishStop.REMOTE_MOVED,
                pointer=pointer,
                uploaded=results,
                lock_seconds=lock_seconds,
                elapsed_seconds=_since(started),
            )

        # 포인터 PUT **앞에** 적는다. 그 PUT 의 답이 끊겨도 다음 회차가 자기 포인터를 알아본다.
        state = replace(state, pending=pending)
        sync_state.write_generation(paths.generation, state)
        client.put_text(pointer.pointer_key, pending.pointer_json, scratch_dir=scratch)
        transfer_seconds = time.perf_counter() - transfer_started

        sent = PublishOutcome(
            decision=PushDecision.PUBLISH,
            head_seq=head_seq,
            pointer=pointer,
            uploaded=results,
            lock_seconds=lock_seconds,
            transfer_seconds=transfer_seconds,
        )
        try:
            after = read_remote_head(client)
        except ObjectStorageError:
            return replace(sent, confirm_deferred=True, elapsed_seconds=_since(started))
        if after.forked:
            _park_pending(paths, state, UNPUBLISHED_FORKED)
            return replace(
                sent,
                head_seq=after.head_seq,
                stop=PublishStop.FORKED,
                elapsed_seconds=_since(started),
            )
        if after.head_key != pointer.pointer_key:
            return replace(
                sent,
                head_seq=after.head_seq,
                confirm_deferred=True,
                elapsed_seconds=_since(started),
            )
        _finish_publish(paths, state)
        return replace(sent, head_seq=pointer.seq, published=True, elapsed_seconds=_since(started))
    finally:
        for work in work_paths:
            work.unlink(missing_ok=True)


def _require_members(client: ObjectStorageClient, members: Mapping[DatasetName, Member]) -> None:
    """HEAD 로 낼 멤버가 저장소에 그대로 있는가. 없는 객체를 가리키면 새 pod 가 뜨지 못한다."""
    for member in members.values():
        found = client.head(member.snapshot_key)
        if found is None:
            raise ValueError(f"스냅샷이 저장소에 없습니다: {member.snapshot_key}")
        if found.size_bytes != member.size_bytes:
            raise ValueError(f"스냅샷 크기가 포인터와 다릅니다: {member.snapshot_key}")


def _promoted_members(mine: Pointer, parent: Pointer | None) -> dict[DatasetName, Member]:
    """승격할 멤버. 내 세대가 만든 멤버만 내 것이다 — 이어 적은 멤버는 그때의 앞 세대 값이라 그대로
    적으면 그 사이 앞선 다른 DB 의 저장이 새 HEAD 에서 빠진다."""
    if parent is None:
        return dict(mine.members)
    return {
        name: member if member.seq == mine.seq else parent.members[name]
        for name, member in mine.members.items()
    }


def resolve_keep_mine(
    client: ObjectStorageClient, paths: SyncPaths, *, scratch_dir: Path | None = None
) -> Pointer:
    """게시하지 못한 세대를 HEAD 위 새 세대로 승격한다. 스냅샷은 이미 올라가 있다.

    이어 적은 멤버를 HEAD 값으로 바꿔 적었으면 이 자리의 그 DB 는 새 HEAD 와 다르다. 그때는 base 를
    옮기지 않는다 — base 가 HEAD 면 다음 `pull` 이 받지 않아 옛 파일이 그대로 남는다.
    """
    state = sync_state.read_generation(paths.generation)
    if state.unpublished is None:
        raise ValueError("해소할 미게시 세대가 없습니다.")
    scratch = scratch_dir or snapshot_export.prepare_scratch()
    mine = manifest.pointer_from_json(state.unpublished.pointer_json, pointer_key="unpublished")
    remote = read_remote_head(client)
    parent = None if remote.head_key is None else read_pointer(client, remote.head_key)
    members = _promoted_members(mine, parent)
    _require_members(client, members)
    pointer = manifest.next_pointer(
        parent,
        members=members,
        origin="manual",
        token=uuid.uuid4().hex[:8],
        app_version=APP_VERSION,
        author=snapshot_export.author_label(),
        created_at_utc=snapshot_export.utc_timestamp(),
        note="미게시 세대 승격",
    )
    pending = PendingPublish(
        pointer_key=pointer.pointer_key,
        pointer_json=manifest.pointer_to_json(pointer),
        observed=state.unpublished.observed,
    )
    state = replace(state, pending=pending, unpublished=None)
    sync_state.write_generation(paths.generation, state)
    client.put_text(pointer.pointer_key, pending.pointer_json, scratch_dir=scratch)
    _finish_publish(paths, state)
    if members != dict(mine.members):
        sync_state.write_generation(paths.generation, replace(state, pending=None))
    return pointer


def resolve_keep_remote(paths: SyncPaths) -> None:
    """내 세대를 버린다. 스냅샷은 저장소에 고아로 남는다. 다음 `pull` 이 원격을 받는다."""
    state = sync_state.read_generation(paths.generation)
    sync_state.write_generation(paths.generation, replace(state, unpublished=None, pending=None))


def adopt_local(paths: SyncPaths, pointer: Pointer) -> None:
    """로컬 파일을 기준으로 삼는다 — 원격 세대를 부모로 적고 두 DB 를 변경 있음으로 둔다."""
    state = sync_state.read_generation(paths.generation)
    sync_state.write_generation(
        paths.generation,
        sync_state.with_base(
            state,
            pointer_key=pointer.pointer_key,
            seq=pointer.seq,
            pointer_json=manifest.pointer_to_json(pointer),
        ),
    )
    for name in DATASET_NAMES:
        sync_state.adopt_dirty(paths.databases[name], dataset=name)


# --------------------------------------------------------------------------- 받기
def _download_member(client: ObjectStorageClient, member: Member, destination: Path) -> None:
    """HEAD 가 가리키는 스냅샷이 저장소에 없으면 망가진 세대다 — 되돌리기로 푸는 갈래로 올린다."""
    try:
        client.get_file(member.snapshot_key, destination, expected_bytes=member.size_bytes)
    except ObjectStorageError as exc:
        if object_storage.is_missing_object(exc):
            raise SnapshotRejected(
                f"스냅샷이 저장소에 없습니다: {member.snapshot_key}", kind=FAILURE_CORRUPT
            ) from exc
        raise


def _download_members(
    client: ObjectStorageClient, pointer: Pointer, *, scratch: Path
) -> dict[DatasetName, Path]:
    """두 멤버를 받아 **둘 다 검증한다.** 한쪽이라도 실패하면 아무것도 설치되지 않는다."""
    downloads: dict[DatasetName, Path] = {}
    try:
        for name in DATASET_NAMES:
            member = pointer.members[name]
            download = snapshot_export.unique_work_path(scratch, name, "download")
            downloads[name] = download
            _download_member(client, member, download)
            snapshot_export.verify_snapshot(
                download,
                dataset=name,
                expected_sha256=member.sha256,
                expected_size=member.size_bytes,
                code_version=snapshot_export.code_migration_version(name),
                rejected_path=scratch / f"{name}-download.duckdb.rejected",
            )
    except BaseException:
        for path in downloads.values():
            path.unlink(missing_ok=True)
        raise
    return downloads


def _install_pair(
    paths: SyncPaths, downloads: Mapping[DatasetName, Path]
) -> dict[DatasetName, InstallResult]:
    """두 파일 설치는 원자가 아니라, 둘째가 실패하면 첫째를 되돌린다.

    사이에서 죽으면 게시 상태가 옛값이라 다음 시작이 다시 받는다.
    """
    installed: dict[DatasetName, InstallResult] = {}
    try:
        for name in DATASET_NAMES:
            installed[name] = snapshot_export.install_snapshot(
                downloads[name], paths.databases[name]
            )
    except OSError:
        for name, result in installed.items():
            snapshot_export.restore_install(result, paths.databases[name])
        raise
    return installed


def _adopt_pointer(paths: SyncPaths, state: GenerationState, pointer: Pointer) -> GenerationState:
    updated = sync_state.with_base(
        state,
        pointer_key=pointer.pointer_key,
        seq=pointer.seq,
        pointer_json=manifest.pointer_to_json(pointer),
    )
    sync_state.write_generation(paths.generation, updated)
    for name in DATASET_NAMES:
        sync_state.adopt_clean(paths.databases[name], dataset=name)
        snapshot_export.prune_superseded_backups(paths.databases[name])
    return updated


def _needed_bytes(pointer: Pointer) -> int:
    return int(pointer.total_bytes * DISK_MARGIN_RATIO) + DISK_MARGIN_BYTES


@dataclass(frozen=True)
class PullPlan:
    """받기 전에 본 원격·로컬과 그 판정. `proceeds` 일 때만 `apply_pull` 이 받는다."""

    remote: RemoteHead
    state: GenerationState
    decision: PullDecision
    # 세대를 모르는(AMBIGUOUS) 로컬을 `--force` 로 덮기로 했다.
    forced: bool

    @property
    def proceeds(self) -> bool:
        if self.remote.head_key is None:
            return False
        return self.forced or self.decision in (PullDecision.DOWNLOAD, PullDecision.LOCAL_MISSING)


def plan_pull(client: ObjectStorageClient, paths: SyncPaths, *, force: bool) -> PullPlan:
    """사람이 돌리는 받기의 판정. 사이드카가 「변경 있음」 이라 적은 로컬은 늘 덮지 않는다.

    사이드카가 아예 없으면(읽지 못하면) 평소에는 「변경 있음」 으로 보아 막는다. `force` 는 바로 그
    「세대도 변경도 모름」 을 덮기로 한 것이라, 그때만 세대 미상(AMBIGUOUS)으로 판정해 받게 한다 —
    `push` 의 UNKNOWN_BASE 안내(`adopt` 또는 `pull --force`)가 막다른 길이 되지 않게. 옛 파일은
    superseded 로 물러난다.
    """
    remote = read_remote_head(client)
    state = sync_state.read_generation(paths.generation)
    local_exists = all(path.exists() for path in paths.databases.values())
    dirty = local_exists and any(
        sync_state.treat_as_dirty(path) for path in paths.databases.values()
    )
    if force and state.base_pointer_key is None:
        dirty = False
    decision = manifest.decide_pull(
        head_key=remote.head_key,
        forked=bool(remote.forked),
        base_pointer_key=state.base_pointer_key,
        local_exists=local_exists,
        dirty=dirty,
        unpublished=state.unpublished is not None,
    )
    return PullPlan(
        remote=remote,
        state=state,
        decision=decision,
        forced=decision is PullDecision.AMBIGUOUS and force,
    )


@dataclass(frozen=True)
class PullOutcome:
    """받기 한 번의 결과."""

    pointer: Pointer
    installs: Mapping[DatasetName, InstallResult]
    elapsed_seconds: float

    @property
    def seq(self) -> int:
        return self.pointer.seq


def apply_pull(
    client: ObjectStorageClient,
    paths: SyncPaths,
    plan: PullPlan,
    *,
    scratch_dir: Path | None = None,
) -> PullOutcome:
    """판정이 허락한 HEAD 를 받아 검증하고 제자리에 설치한다."""
    if plan.remote.head_key is None or not plan.proceeds:
        raise ValueError(f"받지 않기로 한 판정입니다: {plan.decision.value}")
    started = time.perf_counter()
    scratch = scratch_dir or snapshot_export.prepare_scratch()
    pointer = read_pointer(client, plan.remote.head_key, scratch_dir=scratch)
    snapshot_export.require_free_space(scratch, _needed_bytes(pointer))
    downloads = _download_members(client, pointer, scratch=scratch)
    try:
        installs = _install_pair(paths, downloads)
    finally:
        for path in downloads.values():
            path.unlink(missing_ok=True)
    _adopt_pointer(paths, plan.state, pointer)
    return PullOutcome(pointer=pointer, installs=installs, elapsed_seconds=_since(started))


@dataclass(frozen=True)
class BootOutcome:
    """컨테이너 시작의 받기 결과. `kind` 가 있으면 앱을 띄우지 않고 머문다."""

    kind: str | None = None
    action: str | None = None
    seq: int | None = None
    # 앞 pod 의 마지막 올림 시각 — 받은 세대의 `created_at_utc`.
    previous_upload_utc: str | None = None
    total_bytes: int = 0
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.kind is None


ACTION_DOWNLOADED: Final = "downloaded"
ACTION_KEPT: Final = "kept"


def boot_pull(
    client: ObjectStorageClient, paths: SyncPaths, *, scratch_dir: Path | None = None
) -> BootOutcome:
    """앱이 뜨기 전 받기 한 번. 받기 표(`decide_boot`) · 설치 · 펜스까지. 예상한 실패는 갈래로 준다.

    **펜스** — 설치 뒤 같은 멤버로 포인터 G+1 을 게시한다. 끝나는 옛 pod 가 그 뒤로 포인터를 내려면
    「HEAD 그대로인가」 에서 멈춘다. 세대 대조만 쓰므로 조건부 쓰기가 필요 없다.
    """
    started = time.perf_counter()
    try:
        for _attempt in range(BOOT_ATTEMPTS):
            outcome = _boot_once(client, paths, scratch_dir=scratch_dir, started=started)
            if outcome is not None:
                return outcome
    except SnapshotRejected as exc:
        return BootOutcome(kind=exc.kind, elapsed_seconds=_since(started))
    except ValueError:
        return BootOutcome(kind=FAILURE_CORRUPT, elapsed_seconds=_since(started))
    except (ObjectStorageError, OSError) as exc:
        return BootOutcome(kind=classify_failure(exc), elapsed_seconds=_since(started))
    return BootOutcome(kind=FAILURE_OTHER, elapsed_seconds=_since(started))


def _boot_once(
    client: ObjectStorageClient,
    paths: SyncPaths,
    *,
    scratch_dir: Path | None,
    started: float,
) -> BootOutcome | None:
    """`None` 이면 HEAD 가 움직였다 — 처음부터 다시 본다."""
    # 앞 시도가 끊기며 남긴 작업 파일이 디스크 앞 점검을 거짓으로 실패시키지 않게.
    snapshot_export.clear_scratch()
    scratch = scratch_dir or snapshot_export.prepare_scratch()
    read = sync_state.load_generation(paths.generation)
    state = read.state
    remote = read_remote_head(client)
    if read.readable and state.pending is not None:
        settle, state, remote, _ = _settle_pending(
            client, paths, state, remote, scratch_dir=scratch
        )
        if settle is _Settle.UNCONFIRMED:
            return None
    decision = manifest.decide_boot(
        head_key=remote.head_key,
        forked=bool(remote.forked),
        base_pointer_key=state.base_pointer_key,
        local_exists=all(path.exists() for path in paths.databases.values()),
        dirty=state.unpublished is not None
        or any(
            sync_state.sidecar_exists(path) and sync_state.treat_as_dirty(path)
            for path in paths.databases.values()
        ),
        state_unreadable=not read.readable,
    )
    stay = {
        BootDecision.REMOTE_EMPTY: FAILURE_REMOTE_EMPTY,
        BootDecision.FORKED: FAILURE_FORKED,
        BootDecision.DIVERGED: FAILURE_DIVERGED,
    }.get(decision)
    if stay is not None:
        return BootOutcome(kind=stay, seq=remote.head_seq, elapsed_seconds=_since(started))
    assert remote.head_key is not None
    pointer = read_pointer(client, remote.head_key, scratch_dir=scratch)
    for name, member in pointer.members.items():
        verdict = manifest.compare_migration_version(
            file_version=member.migration_version,
            code_version=snapshot_export.code_migration_version(name),
        )
        if verdict == "newer":
            return BootOutcome(
                kind=FAILURE_SCHEMA_NEWER, seq=pointer.seq, elapsed_seconds=_since(started)
            )
    if decision is BootDecision.DOWNLOAD:
        snapshot_export.require_free_space(scratch, _needed_bytes(pointer))
        downloads = _download_members(client, pointer, scratch=scratch)
        try:
            _install_pair(paths, downloads)
        finally:
            for path in downloads.values():
                path.unlink(missing_ok=True)
        state = _adopt_pointer(paths, state, pointer)
    return _raise_fence(
        client,
        paths,
        state,
        pointer,
        action=ACTION_DOWNLOADED if decision is BootDecision.DOWNLOAD else ACTION_KEPT,
        scratch=scratch,
        started=started,
    )


def _raise_fence(
    client: ObjectStorageClient,
    paths: SyncPaths,
    state: GenerationState,
    pointer: Pointer,
    *,
    action: str,
    scratch: Path,
    started: float,
) -> BootOutcome | None:
    current = read_remote_head(client)
    if current.forked:
        return BootOutcome(
            kind=FAILURE_FORKED, seq=current.head_seq, elapsed_seconds=_since(started)
        )
    if current.head_key != pointer.pointer_key:
        return None
    fence = manifest.next_pointer(
        pointer,
        members=pointer.members,
        origin="boot",
        token=uuid.uuid4().hex[:8],
        app_version=APP_VERSION,
        author=snapshot_export.author_label(),
        created_at_utc=snapshot_export.utc_timestamp(),
        note=ORIGIN_NOTE_BOOT,
    )
    text = manifest.pointer_to_json(fence)
    state = replace(
        state, pending=PendingPublish(pointer_key=fence.pointer_key, pointer_json=text, observed={})
    )
    sync_state.write_generation(paths.generation, state)
    client.put_text(fence.pointer_key, text, scratch_dir=scratch)
    after = read_remote_head(client)
    if after.forked:
        return BootOutcome(kind=FAILURE_FORKED, seq=after.head_seq, elapsed_seconds=_since(started))
    if after.head_key != fence.pointer_key:
        return None
    _finish_publish(paths, state)
    return BootOutcome(
        action=action,
        seq=fence.seq,
        previous_upload_utc=pointer.created_at_utc,
        total_bytes=pointer.total_bytes,
        elapsed_seconds=_since(started),
    )


@dataclass(frozen=True)
class WatchResult:
    """쉬는 동안 본 HEAD. 변경이 없어도 옛 데이터로 도는 줄 알아채는 자리다."""

    decision: PushDecision
    head_seq: int | None


def watch_head(client: ObjectStorageClient, paths: SyncPaths) -> WatchResult:
    """목록 한 번으로 HEAD 가 내 base 그대로인지 본다. 아무것도 고치지 않는다.

    HEAD 가 답 끊긴 내 포인터면 남이 앞선 것이 아니다 — 올리기 회차의 `_settle_pending` 이 가른다.
    """
    state = sync_state.read_generation(paths.generation)
    remote = read_remote_head(client)
    mine = state.pending is not None and remote.head_key == state.pending.pointer_key
    return WatchResult(
        decision=manifest.decide_push(
            head_key=state.base_pointer_key if mine else remote.head_key,
            forked=bool(remote.forked),
            base_pointer_key=state.base_pointer_key,
            dirty=False,
            unpublished=state.unpublished is not None,
        ),
        head_seq=remote.head_seq,
    )


# --------------------------------------------------------------------------- 사내 PC
def pointer_keys_at(client: ObjectStorageClient, seq: int) -> tuple[str, ...]:
    """그 세대의 포인터 키들. 갈라졌으면 둘 이상이다."""
    records = client.list_all_objects(manifest.HEAD_PREFIX)
    found = []
    for record in records:
        try:
            if manifest.seq_from_pointer_key(record.key) == seq:
                found.append(record.key)
        except ValueError:
            continue
    return tuple(sorted(found))


@dataclass(frozen=True)
class GenerationRow:
    """세대 목록 한 줄. 포인터 키에 실린 것뿐이라 포인터를 GET 하지 않는다."""

    seq: int
    members: Mapping[DatasetName, int]
    token: str
    last_modified: datetime | None


def list_generations(client: ObjectStorageClient) -> tuple[GenerationRow, ...]:
    """원격 세대를 최신부터. 펜스는 같은 멤버로 쌓이므로 되돌릴 세대는 멤버 번호로 고른다."""
    rows = []
    for record in sorted(client.list_all_objects(manifest.HEAD_PREFIX), key=lambda item: item.key):
        try:
            rows.append(
                GenerationRow(
                    seq=manifest.seq_from_pointer_key(record.key),
                    members=manifest.member_seqs_from_pointer_key(record.key),
                    token=manifest.token_from_pointer_key(record.key),
                    last_modified=record.last_modified,
                )
            )
        except ValueError:
            continue
    return tuple(rows)


def _choose_pointer(
    client: ObjectStorageClient, seq: int, *, token: str | None, scratch: Path
) -> Pointer:
    keys = pointer_keys_at(client, seq)
    if token is not None:
        keys = tuple(key for key in keys if key.endswith(f"__{token}.json"))
    if not keys:
        raise ValueError(f"세대 {with_object_particle(f'seq {seq}')} 원격에서 찾지 못했습니다.")
    if len(keys) > 1:
        tokens = " · ".join(manifest.token_from_pointer_key(key) for key in keys)
        raise ValueError(
            f"세대 seq {seq} 에 포인터가 둘 이상입니다 — --token 으로 고르세요: {tokens}"
        )
    return read_pointer(client, keys[0], scratch_dir=scratch)


@dataclass(frozen=True)
class FetchOutcome:
    """받아 둔 사본 한 벌."""

    pointer: Pointer
    folder: Path
    files: Mapping[DatasetName, Path]


def fetch_copy(
    client: ObjectStorageClient,
    paths: SyncPaths,
    destination: Path,
    *,
    seq: int | None = None,
    token: str | None = None,
) -> FetchOutcome:
    """세대 하나를 사본으로 받는다. `data/` 를 건드리지 않아 앱이 떠 있어도 된다.

    운영 자리(`settings.is_operational_database_place`)는 거절한다. 두 멤버를 검증한 뒤에만 그
    폴더에 두 DB 와 `generation.json` 을 둔다.
    """
    folder = Path(destination)
    if settings.is_operational_database_place(folder):
        raise ValueError(f"운영 DB 자리에는 받지 않습니다 — 저장소 밖 폴더를 주세요: {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    scratch = folder / ".fetch"
    scratch.mkdir(exist_ok=True)
    try:
        if seq is None:
            remote = read_remote_head(client)
            if remote.head_key is None:
                raise ValueError("원격이 비어 있습니다.")
            pointer = read_pointer(client, remote.head_key, scratch_dir=scratch)
        else:
            pointer = _choose_pointer(client, seq, token=token, scratch=scratch)
        snapshot_export.require_free_space(scratch, _needed_bytes(pointer))
        downloads = _download_members(client, pointer, scratch=scratch)
        files: dict[DatasetName, Path] = {}
        for name in DATASET_NAMES:
            target = folder / paths.databases[name].name
            snapshot_export.wal_path(target).unlink(missing_ok=True)
            downloads[name].replace(target)
            files[name] = target
        (folder / "generation.json").write_text(manifest.pointer_to_json(pointer), encoding="utf-8")
        return FetchOutcome(pointer=pointer, folder=folder, files=files)
    finally:
        for leftover in scratch.iterdir():
            leftover.unlink(missing_ok=True)
        scratch.rmdir()


def rollback(
    client: ObjectStorageClient,
    *,
    to_seq: int,
    token: str | None = None,
    note: str,
    scratch_dir: Path | None = None,
) -> Pointer:
    """그 세대의 멤버를 그대로 적은 새 HEAD 를 낸다. 지우지 않고 앞으로만 간다.

    갈라졌어도 맨 위 seq + 1 이라 풀린다. 쓰던 앱이 있으면 그 일꾼은 HEAD 가 움직인 것을 보고
    멈춘다(CI/CD 로 새 pod 가 이 세대를 받는다). 멤버 스냅샷이 저장소에 있는지 먼저 본다.
    """
    scratch = scratch_dir or snapshot_export.prepare_scratch()
    target = _choose_pointer(client, to_seq, token=token, scratch=scratch)
    _require_members(client, target.members)
    remote = read_remote_head(client)
    assert remote.head_key is not None
    parent = read_pointer(client, remote.head_key, scratch_dir=scratch)
    pointer = manifest.next_pointer(
        parent,
        members=target.members,
        origin="rollback",
        token=uuid.uuid4().hex[:8],
        app_version=APP_VERSION,
        author=snapshot_export.author_label(),
        created_at_utc=snapshot_export.utc_timestamp(),
        note=note,
    )
    client.put_text(pointer.pointer_key, manifest.pointer_to_json(pointer), scratch_dir=scratch)
    return pointer


# --------------------------------------------------------------------------- 정리
@dataclass(frozen=True)
class PruneOutcome:
    """정리 한 번의 결과."""

    plan: PrunePlan
    deleted: int
    interrupted: bool = False
    elapsed_seconds: float = 0.0


def plan_prune(
    client: ObjectStorageClient,
    *,
    keep_last: int = manifest.KEEP_LAST_GENERATIONS,
    keep_days: int = manifest.KEEP_DAYS,
    include_orphans: bool = False,
) -> PrunePlan:
    """목록만 읽어 판정한다. `generations/` · `simulation/` · `equipment/` 밖은 보지 않는다."""
    pointers = client.list_all_objects(manifest.HEAD_PREFIX)
    snapshots = [
        record
        for name in DATASET_NAMES
        for record in client.list_all_objects(manifest.snapshot_prefix(name))
    ]
    return manifest.prune_generations(
        pointers=[manifest.ListedObject(item.key, item.last_modified) for item in pointers],
        snapshots=[manifest.ListedObject(item.key, item.last_modified) for item in snapshots],
        keep_last=keep_last,
        keep_days=keep_days,
        include_orphans=include_orphans,
    )


def prune(
    client: ObjectStorageClient,
    *,
    keep_last: int = manifest.KEEP_LAST_GENERATIONS,
    keep_days: int = manifest.KEEP_DAYS,
    include_orphans: bool = False,
    should_stop: Callable[[], bool] | None = None,
) -> PruneOutcome:
    """판정대로 지운다 — 스냅샷 먼저, 포인터 뒤. 낱개 사이에 물러날 자리를 둔다.

    `delete-object` 는 프로세스 하나씩이라, 일꾼이 부르면 올리기 요청이 그만큼 밀린다.
    """
    started = time.perf_counter()
    plan = plan_prune(
        client, keep_last=keep_last, keep_days=keep_days, include_orphans=include_orphans
    )
    deleted = 0
    for key in (*plan.snapshots, *plan.pointers):
        if should_stop is not None and should_stop():
            return PruneOutcome(
                plan=plan, deleted=deleted, interrupted=True, elapsed_seconds=_since(started)
            )
        client.delete(key)
        deleted += 1
    return PruneOutcome(plan=plan, deleted=deleted, elapsed_seconds=_since(started))


def _since(started: float) -> float:
    return time.perf_counter() - started
