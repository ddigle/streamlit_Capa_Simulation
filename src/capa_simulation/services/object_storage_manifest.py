# Purpose: 오브젝트 스토리지 스냅샷 포인터의 키 계약과 세대·분기 판정을 순수 함수로 제공한다.

"""원격 스냅샷의 키 규칙과 pull·push 판정을 담는 순수 계층.

`aws`·파일 IO·Streamlit 을 일절 import 하지 않는다. 판정을 `scripts/` 가 아니라 여기 두는
이유는 `scripts/` 가 mypy strict 검사 밖이기 때문이다 — 데이터 유실을 좌우하는 판정이
타입 검사도 단위 테스트도 받지 않는 자리에 있으면 안 된다.

키 설계의 두 축:

- **스냅샷 키는 seq 가 맨 앞이다.** 목록 정렬이 곧 저장 순서다. 타임스탬프를 앞에 두면
  두 PC 의 시계가 어긋날 때 정렬이 뒤집힌다 — 시각은 사람이 읽는 장식으로만 둔다.
- **포인터 키는 내림차순이다.** `list --max-keys 8` 한 번이 언제나 최신 8개이고 저장이
  쌓여도 페이징이 필요 없다. 고정폭 ASCII 라 이진 정렬이 그대로 숫자 정렬이 된다.

가변 포인터(`current.json`)를 쓰지 않는 것이 이 모듈의 핵심이다. 그것이 유일한
read-modify-write 지점이고, 두 사람이 같은 파일을 각자 갱신할 때 앞사람 저장이 사라지는
경로가 거기서만 생긴다. 포인터를 불변 객체의 시퀀스로 만들면 **같은 seq 에 포인터가 둘인
것 자체가 분기의 물증**이 되고, 올라간 스냅샷은 어느 경우에도 사라지지 않는다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Final, Literal

POINTER_SCHEMA_VERSION: Final = 1
# 내림차순 키를 만들 때 쓰는 시퀀스 공간. 12자리 고정폭이라 seq 는 0 이상 이 값 이하만 쓴다.
SEQUENCE_SPACE: Final = 10**12 - 1
KEY_DIGITS: Final = 12

DatasetName = Literal["simulation", "equipment"]
DATASET_NAMES: Final[tuple[DatasetName, ...]] = ("simulation", "equipment")
DATASET_LABELS: Final[Mapping[DatasetName, str]] = {
    "simulation": "시뮬레이션",
    "equipment": "가용설비",
}
MIGRATION_SCHEMA: Final[Mapping[DatasetName, str]] = {
    "simulation": "app_meta.schema_migration",
    "equipment": "equipment_meta.schema_migration",
}

_SNAPSHOT_KEY_PATTERN: Final = re.compile(
    r"^(?P<dataset>simulation|equipment)/snapshots/"
    r"(?P<seq>\d{12})__(?P<created>\d{8}T\d{6}Z)__(?P<sha8>[0-9a-f]{8})\.duckdb$"
)
_POINTER_KEY_PATTERN: Final = re.compile(
    r"^(?P<dataset>simulation|equipment)/heads/"
    r"(?P<descending>\d{12})__(?P<token>[0-9a-f]{8})\.json$"
)


@dataclass(frozen=True)
class Pointer:
    """어느 스냅샷이 현재 세대인지 가리키는 불변 포인터."""

    schema: int
    database: DatasetName
    seq: int
    pointer_key: str
    snapshot_key: str
    sha256: str
    md5_base64: str
    size_bytes: int
    source_db_bytes: int
    parent_seq: int | None
    parent_sha256: str | None
    migration_version: int
    app_version: str
    author: str
    created_at_utc: str
    note: str


@dataclass(frozen=True)
class WriterMark:
    """어느 PC 가 앱을 켰는지 알리는 조언적 표시. 아무것도 막지 않는다."""

    schema: int
    database: DatasetName
    owner: str
    instance_id: str
    started_at_utc: str
    app_version: str


def head_prefix(dataset: DatasetName) -> str:
    return f"{dataset}/heads/"


def snapshot_prefix(dataset: DatasetName) -> str:
    return f"{dataset}/snapshots/"


def writer_key(dataset: DatasetName) -> str:
    return f"{dataset}/writer.json"


def format_descending(seq: int) -> str:
    """seq 를 내림차순 12자리 문자열로 바꾼다. 큰 seq 일수록 작은 문자열이 된다."""
    if seq < 0 or seq > SEQUENCE_SPACE:
        raise ValueError(f"시퀀스는 0 이상 {SEQUENCE_SPACE} 이하여야 합니다: {seq}")
    return f"{SEQUENCE_SPACE - seq:0{KEY_DIGITS}d}"


def pointer_key(dataset: DatasetName, seq: int, token: str) -> str:
    """포인터 키. 같은 seq 라도 token 이 달라 두 클라이언트가 같은 키를 만들 수 없다."""
    return f"{head_prefix(dataset)}{format_descending(seq)}__{_validated_token(token)}.json"


def seq_from_pointer_key(key: str) -> int:
    matched = _POINTER_KEY_PATTERN.match(key)
    if matched is None:
        raise ValueError(f"포인터 키 형식이 아닙니다: {key}")
    return SEQUENCE_SPACE - int(matched.group("descending"))


def snapshot_key(dataset: DatasetName, seq: int, *, created_at_utc: str, sha256: str) -> str:
    """스냅샷 키. seq 가 맨 앞이라 목록 정렬이 곧 저장 순서다."""
    if seq < 0 or seq > SEQUENCE_SPACE:
        raise ValueError(f"시퀀스는 0 이상 {SEQUENCE_SPACE} 이하여야 합니다: {seq}")
    compact = _compact_timestamp(created_at_utc)
    return f"{snapshot_prefix(dataset)}{seq:0{KEY_DIGITS}d}__{compact}__{sha256[:8]}.duckdb"


def parse_snapshot_key(key: str) -> tuple[int, str, str]:
    """스냅샷 키에서 (seq, 압축 시각, sha8) 을 돌려준다."""
    matched = _SNAPSHOT_KEY_PATTERN.match(key)
    if matched is None:
        raise ValueError(f"스냅샷 키 형식이 아닙니다: {key}")
    return int(matched.group("seq")), matched.group("created"), matched.group("sha8")


def select_head_key(keys: Sequence[str]) -> str | None:
    """현재 HEAD 포인터 키. 최소 키가 최대 seq 이고, 동률이면 사전순 최소로 결정론적이다.

    동률을 사전순으로 고정하는 이유는 모든 PC 가 같은 것을 HEAD 로 보게 하기 위해서다.
    시각이나 도착 순서로 고르면 PC 마다 다른 답을 본다.
    """
    valid = sorted(key for key in keys if _POINTER_KEY_PATTERN.match(key))
    return valid[0] if valid else None


def detect_fork(keys: Sequence[str]) -> tuple[str, ...]:
    """최대 seq 에 포인터가 둘 이상이면 그 키를 전부 돌려준다. 그것이 분기의 물증이다."""
    valid = sorted(key for key in keys if _POINTER_KEY_PATTERN.match(key))
    if len(valid) < 2:
        return ()
    top_seq = seq_from_pointer_key(valid[0])
    forked = tuple(key for key in valid if seq_from_pointer_key(key) == top_seq)
    return forked if len(forked) > 1 else ()


def pointer_to_json(pointer: Pointer) -> str:
    payload = {
        "schema": pointer.schema,
        "database": pointer.database,
        "seq": pointer.seq,
        "snapshot_key": pointer.snapshot_key,
        "sha256": pointer.sha256,
        "md5_base64": pointer.md5_base64,
        "size_bytes": pointer.size_bytes,
        "source_db_bytes": pointer.source_db_bytes,
        "parent_seq": pointer.parent_seq,
        "parent_sha256": pointer.parent_sha256,
        "migration_version": pointer.migration_version,
        "app_version": pointer.app_version,
        "author": pointer.author,
        "created_at_utc": pointer.created_at_utc,
        "note": pointer.note,
    }
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)


def pointer_from_json(text: str, *, pointer_key: str) -> Pointer:
    """포인터 JSON 을 읽는다. 스키마가 다르면 추측하지 않고 거부한다."""
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"포인터 JSON 을 읽지 못했습니다: {pointer_key}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"포인터 JSON 이 객체가 아닙니다: {pointer_key}")
    schema = payload.get("schema")
    if schema != POINTER_SCHEMA_VERSION:
        raise ValueError(
            f"포인터 스키마 {schema} 를 이 버전이 읽지 못합니다(기대 {POINTER_SCHEMA_VERSION}). "
            "앱을 최신 배포본으로 올린 뒤 다시 시도하세요."
        )
    database = payload.get("database")
    if database not in DATASET_NAMES:
        raise ValueError(f"포인터의 database 가 올바르지 않습니다: {database!r}")
    return Pointer(
        schema=POINTER_SCHEMA_VERSION,
        database=database,
        seq=int(payload["seq"]),
        pointer_key=pointer_key,
        snapshot_key=str(payload["snapshot_key"]),
        sha256=str(payload["sha256"]),
        md5_base64=str(payload.get("md5_base64", "")),
        size_bytes=int(payload.get("size_bytes", 0)),
        source_db_bytes=int(payload.get("source_db_bytes", 0)),
        parent_seq=None if payload.get("parent_seq") is None else int(payload["parent_seq"]),
        parent_sha256=(
            None if payload.get("parent_sha256") is None else str(payload["parent_sha256"])
        ),
        migration_version=int(payload.get("migration_version", 0)),
        app_version=str(payload.get("app_version", "")),
        author=str(payload.get("author", "")),
        created_at_utc=str(payload.get("created_at_utc", "")),
        note=str(payload.get("note", "")),
    )


def next_pointer(
    parent: Pointer | None,
    *,
    dataset: DatasetName,
    token: str,
    sha256: str,
    md5_base64: str,
    size_bytes: int,
    source_db_bytes: int,
    migration_version: int,
    app_version: str,
    author: str,
    created_at_utc: str,
    note: str,
) -> Pointer:
    """다음 세대 포인터를 만든다. 부모 해시가 체인의 근거이고 시계는 쓰지 않는다."""
    seq = 1 if parent is None else parent.seq + 1
    return Pointer(
        schema=POINTER_SCHEMA_VERSION,
        database=dataset,
        seq=seq,
        pointer_key=pointer_key(dataset, seq, token),
        snapshot_key=snapshot_key(dataset, seq, created_at_utc=created_at_utc, sha256=sha256),
        sha256=sha256,
        md5_base64=md5_base64,
        size_bytes=size_bytes,
        source_db_bytes=source_db_bytes,
        parent_seq=None if parent is None else parent.seq,
        parent_sha256=None if parent is None else parent.sha256,
        migration_version=migration_version,
        app_version=app_version,
        author=author,
        created_at_utc=created_at_utc,
        note=note,
    )


class PushDecision(str, Enum):
    PUBLISH = "publish"
    UP_TO_DATE = "up_to_date"
    PARENT_MOVED = "parent_moved"
    FORKED = "forked"
    BLOCKED_UNPUBLISHED = "blocked_unpublished"
    REMOTE_EMPTY = "remote_empty"


def decide_push(
    *,
    head: Pointer | None,
    forked: bool,
    base_sha256: str | None,
    dirty: bool,
    unpublished: bool,
) -> PushDecision:
    """올려도 되는지 판정한다. 판정 순서 자체가 계약이다.

    미해소 스냅샷이 있으면 새 push 를 하지 않는다 — 충돌을 쌓지 않고 사람이 한 번에 풀게 한다.
    """
    if unpublished:
        return PushDecision.BLOCKED_UNPUBLISHED
    if forked:
        return PushDecision.FORKED
    if head is None:
        # 최초 이관은 앱이 하지 않는다. 스크립트의 init 만 빈 저장소를 채운다.
        return PushDecision.REMOTE_EMPTY
    if base_sha256 is not None and head.sha256 != base_sha256:
        return PushDecision.PARENT_MOVED
    if not dirty:
        return PushDecision.UP_TO_DATE
    return PushDecision.PUBLISH


class PullDecision(str, Enum):
    DOWNLOAD = "download"
    UP_TO_DATE = "up_to_date"
    AMBIGUOUS = "ambiguous"
    BLOCKED_DIRTY = "blocked_dirty"
    BLOCKED_FORKED = "blocked_forked"
    REMOTE_EMPTY = "remote_empty"
    LOCAL_MISSING = "local_missing"


def decide_pull(
    *,
    head: Pointer | None,
    forked: bool,
    base_sha256: str | None,
    local_exists: bool,
    dirty: bool,
    unpublished: bool,
) -> PullDecision:
    """내려받아도 되는지 판정한다.

    로컬에만 있는 변경을 덮지 않는 것이 이 함수의 존재 이유다. 사이드카를 읽지 못해
    `dirty` 를 모를 때 호출자가 True 를 넣는 규칙(`treat_as_dirty`)과 짝을 이룬다.
    """
    if head is None:
        return PullDecision.REMOTE_EMPTY
    if forked:
        return PullDecision.BLOCKED_FORKED
    if dirty or unpublished:
        return PullDecision.BLOCKED_DIRTY
    if not local_exists:
        return PullDecision.LOCAL_MISSING
    if base_sha256 is None:
        # 로컬 DB 는 있는데 어느 세대에서 왔는지 모른다. 자동으로 덮지 않는다.
        return PullDecision.AMBIGUOUS
    if base_sha256 == head.sha256:
        return PullDecision.UP_TO_DATE
    return PullDecision.DOWNLOAD


def compare_migration_version(
    *, file_version: int, code_version: int
) -> Literal["ok", "older", "newer"]:
    """받은 파일의 마이그레이션 버전과 이 코드의 버전을 비교한다.

    파일이 더 최신이면 이 배포본은 그 DB 를 다룰 수 없다. 열어 보면 체크섬 대조나 스키마
    불일치로 더 늦게, 더 알아보기 어려운 오류가 난다.
    """
    if file_version > code_version:
        return "newer"
    if file_version < code_version:
        return "older"
    return "ok"


def orphan_snapshot_keys(
    snapshot_keys: Sequence[str], referenced: Sequence[str]
) -> tuple[str, ...]:
    """포인터가 가리키지 않는 스냅샷. 경합에서 진 쪽의 데이터라 기본 보호 대상이다."""
    known = set(referenced)
    return tuple(sorted(key for key in snapshot_keys if key not in known))


def prune_candidates(
    *,
    snapshot_keys: Sequence[str],
    pointers: Sequence[Pointer],
    keep_last: int,
    include_orphans: bool,
    protected: Sequence[str],
) -> tuple[str, ...]:
    """지워도 되는 스냅샷 키.

    고아는 `include_orphans` 를 명시할 때만 후보에 넣는다. 고아 스냅샷이 '유실 불가' 의
    유일한 근거인데 정리 명령이 그것부터 지우면 설계가 무너진다.
    """
    if keep_last < 1:
        raise ValueError("보존 개수는 1 이상이어야 합니다.")
    referenced = [pointer.snapshot_key for pointer in pointers]
    keep = {
        pointer.snapshot_key
        for pointer in sorted(pointers, key=lambda item: item.seq, reverse=True)[:keep_last]
    }
    keep.update(protected)
    orphans = set(orphan_snapshot_keys(snapshot_keys, referenced))
    candidates = []
    for key in sorted(snapshot_keys):
        if key in keep:
            continue
        if key in orphans and not include_orphans:
            continue
        candidates.append(key)
    return tuple(candidates)


def writer_age_message(
    mark: WriterMark | None,
    *,
    last_modified: datetime | None,
    server_now: datetime | None,
) -> str:
    """다른 PC 가 앱을 켜 두었는지 알리는 한 줄.

    나이는 **서버가 준 시각**으로만 잰다. 인자에 클라이언트 시각을 받는 자리를 두지 않는 것이
    이 함수의 계약이다 — PC 시계가 어긋나면 조언이 거짓말이 된다.
    """
    if mark is None:
        return ""
    if last_modified is None or server_now is None:
        return f"다른 PC 에서 앱을 켠 기록이 있습니다 · {mark.owner}"
    minutes = max(int((server_now - last_modified).total_seconds() // 60), 0)
    return f"다른 PC 에서 {minutes}분 전에 켰습니다 · {mark.owner}"


def decision_message(
    decision: PushDecision | PullDecision,
    dataset: DatasetName,
    *,
    head: Pointer | None,
    extra: Mapping[str, str] | None = None,
) -> str:
    """판정을 사람이 읽는 한국어 한 줄로 바꾼다. 화면과 스크립트가 같은 문구를 쓴다."""
    label = DATASET_LABELS[dataset]
    generation = "없음" if head is None else f"seq {head.seq}"
    details = dict(extra or {})
    messages: Mapping[PushDecision | PullDecision, str] = {
        PushDecision.PUBLISH: f"{label} 변경을 올립니다(원격 {generation}).",
        PushDecision.UP_TO_DATE: f"{label} 은 원격과 같습니다(원격 {generation}).",
        PushDecision.PARENT_MOVED: (
            f"{label} 원격이 먼저 앞섰습니다(원격 {generation}). 로컬 저장은 그대로 있습니다 — "
            "resolve 로 어느 쪽을 남길지 정하세요."
        ),
        PushDecision.FORKED: (
            f"{label} 원격이 갈라져 있습니다(원격 {generation}). 양쪽 파일은 모두 남아 있습니다."
        ),
        PushDecision.BLOCKED_UNPUBLISHED: (
            f"{label} 에 아직 게시하지 못한 스냅샷이 있습니다. 그것을 먼저 정리해야 합니다."
        ),
        PushDecision.REMOTE_EMPTY: (
            f"{label} 원격이 비어 있습니다. 최초 이관은 sync 스크립트의 init 이 합니다."
        ),
        PullDecision.DOWNLOAD: f"{label} 을 원격 {generation} 으로 내려받습니다.",
        PullDecision.UP_TO_DATE: f"{label} 은 이미 원격 {generation} 입니다.",
        PullDecision.AMBIGUOUS: (
            f"{label} 로컬 DB 가 어느 세대에서 왔는지 알 수 없습니다. 자동으로 덮지 않습니다 — "
            "adopt 로 어느 쪽을 기준으로 삼을지 정하세요."
        ),
        PullDecision.BLOCKED_DIRTY: (
            f"{label} 에 이 PC 에만 있는 변경이 있습니다. 먼저 올린 뒤 내려받으세요."
        ),
        PullDecision.BLOCKED_FORKED: (
            f"{label} 원격이 갈라져 있어 내려받지 않습니다(원격 {generation})."
        ),
        PullDecision.REMOTE_EMPTY: (
            f"{label} 원격이 비어 있습니다. 최초 이관은 sync 스크립트의 init 이 합니다."
        ),
        PullDecision.LOCAL_MISSING: f"{label} 로컬 DB 가 없어 원격 {generation} 을 받습니다.",
    }
    message = messages[decision]
    if details:
        message += " · " + " · ".join(f"{key} {value}" for key, value in sorted(details.items()))
    return message


def _validated_token(token: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{8}", token):
        raise ValueError(f"포인터 토큰은 소문자 16진수 8자리여야 합니다: {token!r}")
    return token


def _compact_timestamp(created_at_utc: str) -> str:
    """`2026-09-08T09:15:00Z` → `20260908T091500Z`. 키에 넣을 수 없는 문자를 없앤다."""
    compact = created_at_utc.replace("-", "").replace(":", "")
    if not re.fullmatch(r"\d{8}T\d{6}Z", compact):
        raise ValueError(f"UTC 시각 형식이 아닙니다: {created_at_utc!r}")
    return compact
