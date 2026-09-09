# Purpose: DuckDB 파일 옆 사이드카에 원격 세대와 미반영 변경 표시를 기록한다.

"""동기화 상태를 DB 파일 옆 작은 JSON 에 남기는 계층.

상태를 DuckDB 안에 넣지 않는다 — 그 파일 자체가 동기화 대상이라 순환이 된다. 메모리에도
두지 않는다: 프로세스가 죽으면 "이 PC 에만 있는 변경" 표시가 사라지고, 다음 기동의 pull 이
그 리비전을 백업 없이 덮는다.

`_write_transaction` 이 COMMIT 직후에 부르는 유일한 대상이라 **Streamlit·aws·io 를 import
하지 않는다.** 그리고 `enable()` 되지 않은 환경(개발 PC·CI)에서는 파일을 하나도 만들지
않는다 — 지금 동작을 한 글자도 바꾸지 않기 위해서다.

읽지 못하는 사이드카는 "변경 있음" 으로 본다(`treat_as_dirty`). 모르면 올리는 쪽이 안전하다.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from capa_simulation.services.object_storage_manifest import DatasetName

SIDECAR_SUFFIX: Final = ".sync.json"
SIDECAR_SCHEMA_VERSION: Final = 1
HEARTBEAT_INTERVAL_SECONDS: Final = 10.0
HEARTBEAT_STALE_SECONDS: Final = 90.0

# managed 모드에서 boot 가 한 번 등록한다. 비어 있으면 이 모듈은 아무 일도 하지 않는다.
_ENABLED: dict[Path, DatasetName] = {}
# 심장박동을 10초에 한 번만 쓰기 위한 마지막 기록 시각(단조 시계).
_LAST_HEARTBEAT: dict[Path, float] = {}


@dataclass(frozen=True)
class SyncState:
    """한 DB 의 동기화 상태."""

    dataset: DatasetName
    base_seq: int | None = None
    base_sha256: str | None = None
    base_snapshot_key: str | None = None
    base_synced_at_utc: str | None = None
    dirty: bool = False
    unpublished_snapshot_key: str | None = None
    unpublished_sha256: str | None = None
    unpublished_reason: str | None = None
    last_error: str | None = None
    instance_id: str | None = None
    heartbeat_utc: str | None = None


def sidecar_path(database_path: Path) -> Path:
    return database_path.with_name(database_path.name + SIDECAR_SUFFIX)


def _registry_key(database_path: Path) -> Path:
    """등록 대조에만 쓰는 정규화 경로.

    저장소는 `database_path.resolve()` 를 들고 있고 부트는 설정에 적힌 경로를 그대로 넘긴다.
    정규화하지 않으면 같은 파일인데 키가 달라 `_update` 가 조용히 아무 일도 하지 않는다 —
    변경 표시가 사라지고 다음 push 가 "올릴 것 없음" 으로 끝난다.
    """
    try:
        return Path(database_path).resolve()
    except OSError:
        return Path(database_path)


def enable(paths: Mapping[Path, DatasetName]) -> None:
    """managed 모드에서 boot 가 한 번 부른다. 이 호출 전에는 어떤 파일도 만들지 않는다."""
    _ENABLED.clear()
    _ENABLED.update({_registry_key(path): dataset for path, dataset in paths.items()})


def is_enabled(database_path: Path) -> bool:
    return _registry_key(database_path) in _ENABLED


def clear_all() -> None:
    """테스트 전용. 등록과 심장박동 기록을 비운다."""
    _ENABLED.clear()
    _LAST_HEARTBEAT.clear()


def read_state(database_path: Path) -> SyncState | None:
    """사이드카를 읽는다. 없거나 깨졌으면 None — 호출자는 `treat_as_dirty` 로 판단한다."""
    path = sidecar_path(database_path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SIDECAR_SCHEMA_VERSION:
        return None
    dataset = payload.get("dataset")
    if dataset not in ("simulation", "equipment"):
        return None
    known = {
        field: payload.get(field) for field in SyncState.__dataclass_fields__ if field != "dataset"
    }
    return SyncState(dataset=dataset, **known)  # type: ignore[arg-type]


def write_state(database_path: Path, state: SyncState) -> None:
    """임시파일에 쓰고 바꿔치기한다. 중간에 죽어도 반쪽 파일이 남지 않는다."""
    path = sidecar_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SIDECAR_SCHEMA_VERSION, **asdict(state)}
    text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), prefix=path.name + ".", delete=False
    )
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    except OSError:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _update(database_path: Path, **changes: object) -> None:
    """등록된 경로에만 쓴다. 실패는 삼킨다 — 저장 경로로 예외를 올려보내지 않는다."""
    path = Path(database_path)
    dataset = _ENABLED.get(_registry_key(path))
    if dataset is None:
        return
    try:
        state = read_state(path) or SyncState(dataset=dataset)
        write_state(path, replace(state, **changes))  # type: ignore[arg-type]
    except OSError:
        # 사이드카를 못 써도 저장 자체는 성공해야 한다. 대신 `treat_as_dirty` 가
        # "모르면 변경 있음" 으로 보아 다음 push 에서 만회한다.
        return


def mark_dirty(database_path: Path) -> None:
    """쓰기 트랜잭션이 COMMIT 된 직후에만 부른다."""
    _update(database_path, dirty=True)


def clear_dirty(database_path: Path, *, seq: int, sha256: str, snapshot_key: str) -> None:
    """업로드가 검증까지 끝난 뒤에만 부른다."""
    _update(
        database_path,
        dirty=False,
        base_seq=seq,
        base_sha256=sha256,
        base_snapshot_key=snapshot_key,
        base_synced_at_utc=_utc_now_text(),
        unpublished_snapshot_key=None,
        unpublished_sha256=None,
        unpublished_reason=None,
        last_error=None,
    )


def mark_unpublished(database_path: Path, *, snapshot_key: str, sha256: str, reason: str) -> None:
    """스냅샷은 올라갔는데 포인터를 게시하지 못한 상태. 그 키가 곧 복구 수단이다."""
    _update(
        database_path,
        unpublished_snapshot_key=snapshot_key,
        unpublished_sha256=sha256,
        unpublished_reason=reason,
    )


def clear_unpublished(database_path: Path) -> None:
    _update(
        database_path,
        unpublished_snapshot_key=None,
        unpublished_sha256=None,
        unpublished_reason=None,
    )


def record_error(database_path: Path, message: str | None) -> None:
    _update(database_path, last_error=message)


def adopt_generation(
    database_path: Path,
    *,
    dataset: DatasetName,
    seq: int | None,
    sha256: str | None,
    snapshot_key: str | None,
) -> None:
    """등록 여부와 무관하게 세대를 기록한다. 스크립트의 init·adopt·pull 이 쓴다."""
    path = Path(database_path)
    state = read_state(path) or SyncState(dataset=dataset)
    write_state(
        path,
        replace(
            state,
            dataset=dataset,
            base_seq=seq,
            base_sha256=sha256,
            base_snapshot_key=snapshot_key,
            base_synced_at_utc=_utc_now_text(),
            dirty=False,
            unpublished_snapshot_key=None,
            unpublished_sha256=None,
            unpublished_reason=None,
        ),
    )


def touch_heartbeat(database_path: Path, *, instance_id: str) -> None:
    """살아 있음을 알린다. 10초에 한 번만 실제로 쓴다 — rerun 마다 쓸 이유가 없다."""
    path = Path(database_path)
    if _registry_key(path) not in _ENABLED:
        return
    now = time.monotonic()
    last = _LAST_HEARTBEAT.get(path)
    if last is not None and now - last < HEARTBEAT_INTERVAL_SECONDS:
        return
    _LAST_HEARTBEAT[path] = now
    _update(path, instance_id=instance_id, heartbeat_utc=_utc_now_text())


def live_instance(database_path: Path, *, exclude: str | None = None) -> str | None:
    """다른 인스턴스가 살아 있으면 그 id. 90초 넘게 조용하면 죽은 것으로 본다."""
    state = read_state(Path(database_path))
    if state is None or not state.instance_id or not state.heartbeat_utc:
        return None
    if exclude is not None and state.instance_id == exclude:
        return None
    beat = _parse_utc(state.heartbeat_utc)
    if beat is None:
        return None
    if datetime.now(timezone.utc) - beat > timedelta(seconds=HEARTBEAT_STALE_SECONDS):
        return None
    return state.instance_id


def treat_as_dirty(database_path: Path) -> bool:
    """올려야 하는지. **사이드카를 읽지 못하면 True** — 모르면 올리는 쪽이 안전하다."""
    state = read_state(Path(database_path))
    if state is None:
        return True
    return bool(state.dirty or state.unpublished_snapshot_key)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
