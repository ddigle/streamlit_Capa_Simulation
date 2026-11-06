# Purpose: 오브젝트 스토리지 세대 포인터의 키 계약과 세대·분기·정리 판정을 순수 함수로 제공한다.

"""원격 스냅샷의 키 규칙과 받기·올리기·정리 판정을 담는 순수 계층.

`aws`·파일 IO·Streamlit 을 일절 import 하지 않는다. 판정을 `scripts/` 가 아니라 여기 두는
이유는 데이터 유실을 좌우하는 판정이 IO 와 섞이지 않은 순수 함수여야 단위 테스트가
그대로 부를 수 있기 때문이다 — 스크립트는 인자를 읽고 이 판정과 IO 를 잇기만 한다.

**두 DB 는 한 쌍이고 게시 단위는 세대 포인터 하나다.** DB 별 사슬이면 포인터 둘 사이에서 죽을 때
두 DB 가 어긋나고, 그것을 덮는 포인터를 또 두면 사슬끼리 어긋난다. 포인터 하나가 두 멤버를 함께
가리키고 그 PUT 하나가 게시다. 바뀌지 않은 DB 는 앞 세대의 멤버를 그대로 이어 적는다.

키 설계의 세 축:

- **스냅샷 키는 seq 가 맨 앞이다.** 목록 정렬이 곧 저장 순서다. 타임스탬프를 앞에 두면
  두 PC 의 시계가 어긋날 때 정렬이 뒤집힌다 — 시각은 사람이 읽는 장식으로만 둔다.
- **포인터 키는 내림차순이다.** `list --max-keys 8` 한 번이 언제나 최신 8개이고 저장이
  쌓여도 페이징이 필요 없다. 고정폭 ASCII 라 이진 정렬이 그대로 숫자 정렬이 된다.
- **포인터 키에 멤버 세대를 싣는다.** 정리가 포인터를 GET 하지 않고 목록 한 번으로 어느 스냅샷이
  참조되는지 안다 — 포인터마다 `aws` 를 띄우면 그만큼 초가 든다.

가변 포인터(`current.json`)를 쓰지 않는 것이 이 모듈의 핵심이다. 그것이 유일한
read-modify-write 지점이고, 두 사람이 같은 파일을 각자 갱신할 때 앞사람 저장이 사라지는
경로가 거기서만 생긴다. 포인터를 불변 객체의 시퀀스로 만들면 **같은 seq 에 포인터가 둘인
것 자체가 분기의 물증**이 되고, 올라간 스냅샷은 어느 경우에도 사라지지 않는다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Final, Literal, get_args

from capa_simulation.services.korean_particle import (
    with_direction_particle,
    with_object_particle,
)

POINTER_SCHEMA_VERSION: Final = 2
# 내림차순 키를 만들 때 쓰는 시퀀스 공간. 12자리 고정폭이라 seq 는 0 이상 이 값 이하만 쓴다.
SEQUENCE_SPACE: Final = 10**12 - 1
KEY_DIGITS: Final = 12
HEAD_PREFIX: Final = "generations/heads/"
# 정리가 건드리는 접두사의 전부. 접속 명단(`access/`)은 이 밖이라 어떤 경로로도 지우지 못한다.
PRUNE_PREFIXES: Final = (HEAD_PREFIX, "simulation/snapshots/", "equipment/snapshots/")
KEEP_LAST_GENERATIONS: Final = 5
KEEP_DAYS: Final = 7
# 회차 하나에 지우는 객체 수의 끝. `delete-object` 는 프로세스 하나씩이라 많으면 올리기를 막는다.
PRUNE_DELETE_LIMIT: Final = 200

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
# 누가 게시했는가. `init` — 사내 PC 의 최초 이관, `app` — 운영 앱의 저장, `boot` — 시작 때의 펜스
# (같은 멤버), `manual` — 사람이 돌린 `push`·`resolve`, `rollback` — 세대 되돌리기.
Origin = Literal["init", "app", "boot", "manual", "rollback"]
ORIGINS: Final[tuple[Origin, ...]] = get_args(Origin)
# 운영 앱이 정본을 넘겨받은 뒤의 표시. HEAD 가 이 값이면 사내 PC 는 올리지 못한다. 되돌린 HEAD 도
# 운영 앱의 정본이다 — 다음 시작의 펜스가 서기 전 틈에 표지 없는 PC 가 그 위로 올리면 안 된다.
WRITER_ORIGINS: Final = frozenset({"app", "boot", "rollback"})

# 실패 갈래 — 시작 화면 · 보고 · 상태 파일 · 알림이 함께 쓰는 고정 낱말. 서버 글을 싣지 않는다.
FAILURE_CONFIG: Final = "config"
FAILURE_CLI_MISSING: Final = "cli_missing"
FAILURE_UNREACHABLE: Final = "unreachable"
FAILURE_TIMEOUT: Final = "timeout"
FAILURE_DENIED: Final = "denied"
FAILURE_NO_BUCKET: Final = "no_bucket"
FAILURE_REMOTE_EMPTY: Final = "remote_empty"
FAILURE_FORKED: Final = "forked"
FAILURE_DIVERGED: Final = "diverged"
FAILURE_CORRUPT: Final = "corrupt"
FAILURE_SCHEMA_NEWER: Final = "schema_newer"
FAILURE_DISK_FULL: Final = "disk_full"
FAILURE_OTHER: Final = "other"
FAILURE_WORKER_ABSENT: Final = "worker_absent"
FAILURE_LABELS: Final[Mapping[str, str]] = {
    FAILURE_CONFIG: "설정 오류",
    FAILURE_CLI_MISSING: "aws 명령 없음",
    FAILURE_UNREACHABLE: "저장소에 닿지 못함",
    FAILURE_TIMEOUT: "시간 초과",
    FAILURE_DENIED: "저장소가 거절",
    FAILURE_NO_BUCKET: "버킷 없음",
    FAILURE_REMOTE_EMPTY: "원격이 비어 있음",
    FAILURE_FORKED: "원격이 갈라짐",
    FAILURE_DIVERGED: "원격과 어긋남",
    FAILURE_CORRUPT: "스냅샷이 깨짐",
    FAILURE_SCHEMA_NEWER: "DB 판이 코드보다 새로움",
    FAILURE_DISK_FULL: "디스크 부족",
    FAILURE_OTHER: "그 밖의 실패",
    FAILURE_WORKER_ABSENT: "동기화 일꾼이 돌지 않음",
}

_SNAPSHOT_KEY_PATTERN: Final = re.compile(
    r"^(?P<dataset>simulation|equipment)/snapshots/"
    r"(?P<seq>\d{12})__(?P<created>\d{8}T\d{6}Z)__(?P<sha8>[0-9a-f]{8})\.duckdb$"
)
_POINTER_KEY_PATTERN: Final = re.compile(
    r"^generations/heads/"
    r"(?P<descending>\d{12})__s(?P<simulation>\d{12})__e(?P<equipment>\d{12})__"
    r"(?P<token>[0-9a-f]{8})\.json$"
)


@dataclass(frozen=True)
class Member:
    """세대가 가리키는 DB 하나. `seq` 는 그 스냅샷을 만든 세대다(이어 적으면 앞 세대 번호)."""

    seq: int
    snapshot_key: str
    sha256: str
    md5_base64: str
    size_bytes: int
    source_db_bytes: int
    migration_version: int


@dataclass(frozen=True)
class Pointer:
    """어느 스냅샷 한 쌍이 현재 세대인지 가리키는 불변 포인터."""

    schema: int
    seq: int
    pointer_key: str
    parent_seq: int | None
    parent_pointer_key: str | None
    origin: Origin
    members: Mapping[DatasetName, Member]
    app_version: str
    author: str
    created_at_utc: str
    note: str

    @property
    def total_bytes(self) -> int:
        return sum(member.size_bytes for member in self.members.values())


@dataclass(frozen=True)
class WriterMark:
    """어느 PC 가 앱을 켰는지 알리는 조언적 표시. 아무것도 막지 않는다."""

    schema: int
    database: DatasetName
    owner: str
    instance_id: str
    started_at_utc: str
    app_version: str


def snapshot_prefix(dataset: DatasetName) -> str:
    return f"{dataset}/snapshots/"


def writer_key(dataset: DatasetName) -> str:
    return f"{dataset}/writer.json"


def format_descending(seq: int) -> str:
    """seq 를 내림차순 12자리 문자열로 바꾼다. 큰 seq 일수록 작은 문자열이 된다."""
    _require_sequence(seq)
    return f"{SEQUENCE_SPACE - seq:0{KEY_DIGITS}d}"


def pointer_key(seq: int, *, simulation_seq: int, equipment_seq: int, token: str) -> str:
    """포인터 키. 같은 seq 라도 token 이 달라 두 클라이언트가 같은 키를 만들 수 없다."""
    _require_sequence(simulation_seq)
    _require_sequence(equipment_seq)
    return (
        f"{HEAD_PREFIX}{format_descending(seq)}"
        f"__s{simulation_seq:0{KEY_DIGITS}d}__e{equipment_seq:0{KEY_DIGITS}d}"
        f"__{_validated_token(token)}.json"
    )


def seq_from_pointer_key(key: str) -> int:
    matched = _POINTER_KEY_PATTERN.match(key)
    if matched is None:
        raise ValueError(f"포인터 키 형식이 아닙니다: {key}")
    return SEQUENCE_SPACE - int(matched.group("descending"))


def member_seqs_from_pointer_key(key: str) -> dict[DatasetName, int]:
    """포인터 키에 실린 두 멤버의 세대. 정리가 GET 없이 참조를 안다."""
    matched = _POINTER_KEY_PATTERN.match(key)
    if matched is None:
        raise ValueError(f"포인터 키 형식이 아닙니다: {key}")
    return {name: int(matched.group(name)) for name in DATASET_NAMES}


def token_from_pointer_key(key: str) -> str:
    """포인터 키 꼬리 8자리. 같은 세대에 포인터가 둘일 때 사람이 고르는 값이다."""
    matched = _POINTER_KEY_PATTERN.match(key)
    if matched is None:
        raise ValueError(f"포인터 키 형식이 아닙니다: {key}")
    return matched.group("token")


def snapshot_key(dataset: DatasetName, seq: int, *, created_at_utc: str, sha256: str) -> str:
    """스냅샷 키. seq 가 맨 앞이라 목록 정렬이 곧 저장 순서다."""
    _require_sequence(seq)
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
        "seq": pointer.seq,
        "parent_seq": pointer.parent_seq,
        "parent_pointer_key": pointer.parent_pointer_key,
        "origin": pointer.origin,
        "members": {
            name: {
                "seq": member.seq,
                "snapshot_key": member.snapshot_key,
                "sha256": member.sha256,
                "md5_base64": member.md5_base64,
                "size_bytes": member.size_bytes,
                "source_db_bytes": member.source_db_bytes,
                "migration_version": member.migration_version,
            }
            for name, member in pointer.members.items()
        },
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
            f"포인터 스키마 {with_object_particle(str(schema))} 이 버전이 읽지 못합니다"
            f"(기대 {POINTER_SCHEMA_VERSION}). "
            "앱을 최신 배포본으로 올린 뒤 다시 시도하세요."
        )
    origin = payload.get("origin")
    if origin not in ORIGINS:
        raise ValueError(f"포인터의 origin 이 올바르지 않습니다: {origin!r}")
    raw_members = payload.get("members")
    if not isinstance(raw_members, dict) or set(raw_members) != set(DATASET_NAMES):
        raise ValueError(f"포인터에 두 DB 멤버가 없습니다: {pointer_key}")
    return Pointer(
        schema=POINTER_SCHEMA_VERSION,
        seq=int(payload["seq"]),
        pointer_key=pointer_key,
        parent_seq=None if payload.get("parent_seq") is None else int(payload["parent_seq"]),
        parent_pointer_key=(
            None
            if payload.get("parent_pointer_key") is None
            else str(payload["parent_pointer_key"])
        ),
        origin=origin,
        members={name: _member_from_json(raw_members[name], pointer_key) for name in DATASET_NAMES},
        app_version=str(payload.get("app_version", "")),
        author=str(payload.get("author", "")),
        created_at_utc=str(payload.get("created_at_utc", "")),
        note=str(payload.get("note", "")),
    )


def _member_from_json(raw: object, key: str) -> Member:
    if not isinstance(raw, dict):
        raise ValueError(f"포인터 멤버가 객체가 아닙니다: {key}")
    return Member(
        seq=int(raw["seq"]),
        snapshot_key=str(raw["snapshot_key"]),
        sha256=str(raw["sha256"]),
        md5_base64=str(raw.get("md5_base64", "")),
        size_bytes=int(raw.get("size_bytes", 0)),
        source_db_bytes=int(raw.get("source_db_bytes", 0)),
        migration_version=int(raw.get("migration_version", 0)),
    )


def next_pointer(
    parent: Pointer | None,
    *,
    members: Mapping[DatasetName, Member],
    origin: Origin,
    token: str,
    app_version: str,
    author: str,
    created_at_utc: str,
    note: str,
) -> Pointer:
    """다음 세대 포인터를 만든다. 부모 포인터 키가 체인의 근거이고 시계는 쓰지 않는다."""
    seq = 1 if parent is None else parent.seq + 1
    return Pointer(
        schema=POINTER_SCHEMA_VERSION,
        seq=seq,
        pointer_key=pointer_key(
            seq,
            simulation_seq=members["simulation"].seq,
            equipment_seq=members["equipment"].seq,
            token=token,
        ),
        parent_seq=None if parent is None else parent.seq,
        parent_pointer_key=None if parent is None else parent.pointer_key,
        origin=origin,
        members=dict(members),
        app_version=app_version,
        author=author,
        created_at_utc=created_at_utc,
        note=note,
    )


def writer_taken_over(head: Pointer | None) -> bool:
    """정본을 운영 앱이 넘겨받은 뒤인가. 그러면 사내 PC 의 쓰기 명령은 거절한다."""
    return head is not None and head.origin in WRITER_ORIGINS


class PushDecision(str, Enum):
    PUBLISH = "publish"
    UP_TO_DATE = "up_to_date"
    PARENT_MOVED = "parent_moved"
    FORKED = "forked"
    BLOCKED_UNPUBLISHED = "blocked_unpublished"
    REMOTE_EMPTY = "remote_empty"
    UNKNOWN_BASE = "unknown_base"


# 사람이 손대야 풀리는 판정 — 일꾼이 멈추고 알린다.
BLOCKING_PUSH: Final = frozenset(
    {
        PushDecision.PARENT_MOVED,
        PushDecision.FORKED,
        PushDecision.BLOCKED_UNPUBLISHED,
        PushDecision.REMOTE_EMPTY,
        PushDecision.UNKNOWN_BASE,
    }
)


def decide_push(
    *,
    head_key: str | None,
    forked: bool,
    base_pointer_key: str | None,
    dirty: bool,
    unpublished: bool,
) -> PushDecision:
    """올려도 되는지 판정한다. 판정 순서 자체가 계약이다.

    미해소 스냅샷이 있으면 새 push 를 하지 않는다 — 충돌을 쌓지 않고 사람이 한 번에 풀게 한다.
    원격에 HEAD 가 있는데 로컬이 어느 세대에서 왔는지 모르면(상태 파일이 없거나 base 가 빈 DB —
    빈 디스크에서 만든 데모 시드도 여기다) 멈춘다. 그 DB 를 HEAD 의 자식으로 게시하면 원격의
    마지막 세대를 남의 내용으로 덮는다. 기준은 사람이 `adopt`·`pull --force` 로 정한다.
    """
    if unpublished:
        return PushDecision.BLOCKED_UNPUBLISHED
    if forked:
        return PushDecision.FORKED
    if head_key is None:
        # 최초 이관은 앱이 하지 않는다. 스크립트의 init 만 빈 저장소를 채운다.
        return PushDecision.REMOTE_EMPTY
    if base_pointer_key is None:
        return PushDecision.UNKNOWN_BASE
    if head_key != base_pointer_key:
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
    head_key: str | None,
    forked: bool,
    base_pointer_key: str | None,
    local_exists: bool,
    dirty: bool,
    unpublished: bool,
) -> PullDecision:
    """사람이 돌리는 `pull` 의 판정.

    로컬에만 있는 변경을 덮지 않는 것이 이 함수의 존재 이유다. 사이드카를 읽지 못해
    `dirty` 를 모를 때 호출자가 True 를 넣는 규칙(`treat_as_dirty`)과 짝을 이룬다.
    """
    if head_key is None:
        return PullDecision.REMOTE_EMPTY
    if forked:
        return PullDecision.BLOCKED_FORKED
    if dirty or unpublished:
        return PullDecision.BLOCKED_DIRTY
    if not local_exists:
        return PullDecision.LOCAL_MISSING
    if base_pointer_key is None:
        # 로컬 DB 는 있는데 어느 세대에서 왔는지 모른다. 자동으로 덮지 않는다.
        return PullDecision.AMBIGUOUS
    if base_pointer_key == head_key:
        return PullDecision.UP_TO_DATE
    return PullDecision.DOWNLOAD


class BootDecision(str, Enum):
    DOWNLOAD = "download"
    KEEP = "keep"
    DIVERGED = "diverged"
    REMOTE_EMPTY = "remote_empty"
    FORKED = "forked"


def decide_boot(
    *,
    head_key: str | None,
    forked: bool,
    base_pointer_key: str | None,
    local_exists: bool,
    dirty: bool,
    state_unreadable: bool,
) -> BootDecision:
    """컨테이너 시작의 받기 판정. 앱이 뜨기 전이고 이 표 밖의 길은 없다.

    `decide_pull` 과 다른 자리가 하나다 — 세대를 모르는 로컬은 덮는다. 컨테이너에서 세대 없는 DB
    는 빈 시드뿐이고, 사람이 `adopt` 를 고를 자리가 없다. 다만 상태 파일이 있는데 **읽지 못하면**
    모르는 것이 아니라 망가진 것이라 변경이 있다고 보고 머문다.
    """
    if head_key is None:
        return BootDecision.REMOTE_EMPTY
    if forked:
        return BootDecision.FORKED
    if state_unreadable:
        return BootDecision.DIVERGED
    if not local_exists or base_pointer_key is None:
        return BootDecision.DOWNLOAD
    if base_pointer_key == head_key:
        return BootDecision.KEEP
    return BootDecision.DIVERGED if dirty else BootDecision.DOWNLOAD


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


@dataclass(frozen=True)
class ListedObject:
    """정리 판정에 넘기는 목록 한 줄. 시각은 저장소가 준 LastModified 뿐이다."""

    key: str
    last_modified: datetime | None


@dataclass(frozen=True)
class PrunePlan:
    """지울 것. 차례는 스냅샷 먼저, 포인터 뒤다(`prune_generations`)."""

    snapshots: tuple[str, ...] = ()
    pointers: tuple[str, ...] = ()
    kept_generations: int = 0
    protected_orphans: int = 0
    # 회차 상한을 넘어 다음 번으로 넘긴 수.
    deferred: int = 0

    @property
    def total(self) -> int:
        return len(self.snapshots) + len(self.pointers)


def prune_generations(
    *,
    pointers: Sequence[ListedObject],
    snapshots: Sequence[ListedObject],
    keep_last: int = KEEP_LAST_GENERATIONS,
    keep_days: int = KEEP_DAYS,
    include_orphans: bool = False,
    limit: int = PRUNE_DELETE_LIMIT,
) -> PrunePlan:
    """오래된 세대의 정리 판정. **목록 한 번**만 쓰고 GET 을 하지 않는다.

    - 남김 = HEAD ∪ 멤버 쌍이 다른 최신 `keep_last` 세대 ∪ HEAD 나이 기준 `keep_days` 일 안 세대.
      나이는 **HEAD 의 LastModified 에서** 잰다 — 앱 시계를 쓰지 않고, 한동안 저장이 없으면 정리도
      멈춘다. 저장 없는 시작이 되풀이되면 같은 멤버의 펜스 세대만 쌓이므로 쌍이 다른 세대로 센다.
    - 남긴 세대가 가리키는 스냅샷(이어 적은 앞 세대 멤버 포함)은 지키고, **어떤 포인터도 가리키지
      않는 고아는 늘 지킨다** — 경합에서 진 쪽의 데이터라 「유실 불가」 의 근거다.
      `include_orphans` 일 때만 `keep_days` 넘은 고아를 지운다.
    - 같은 (DB, 세대 번호) 스냅샷이 둘 이상이면 둘 다 지킨다. 포인터 키에는 번호뿐이라 어느 쪽이
      참조인지 목록으로 모르고, 하나는 경합에서 진 쪽일 수 있다(재시도의 찌꺼기도 함께 남는다).
    - 차례는 스냅샷 먼저, 포인터 뒤다. 사이에서 죽으면 뜬 포인터만 남아 다음 번에 치운다. 거꾸로면
      스냅샷이 고아가 되어 영영 안 지워진다. 같은 까닭으로 상한에 걸리면 그 스냅샷이 다 지워지는
      포인터만 이번 회차에 넣는다.
    - 갈라진 원격(같은 seq 포인터 둘)에서는 아무것도 지우지 않는다 — 사람이 볼 물증이다.
    - 모르는 꼴의 키는 건드리지 않는다.
    """
    if keep_last < 1:
        raise ValueError("보존 개수는 1 이상이어야 합니다.")
    if keep_days < 0:
        raise ValueError("보존 일수는 0 이상이어야 합니다.")
    known = [item for item in pointers if _POINTER_KEY_PATTERN.match(item.key)]
    keys = [item.key for item in known]
    head_key = select_head_key(keys)
    if head_key is None or detect_fork(keys):
        return PrunePlan()
    moments = {item.key: item.last_modified for item in known}
    head_moment = moments[head_key]
    if head_moment is None:
        return PrunePlan(kept_generations=len(known))
    cutoff = head_moment - timedelta(days=keep_days)

    kept = _kept_pointers(sorted(keys), moments, cutoff, keep_last)
    kept_refs = {
        (name, seq) for key in kept for name, seq in member_seqs_from_pointer_key(key).items()
    }
    all_refs = {
        (name, seq) for key in keys for name, seq in member_seqs_from_pointer_key(key).items()
    }
    doomed_snapshots: list[str] = []
    protected = 0
    owner: dict[tuple[str, int], list[str]] = {}
    references = {
        item.key: (matched.group("dataset"), int(matched.group("seq")))
        for item in snapshots
        if (matched := _SNAPSHOT_KEY_PATTERN.match(item.key)) is not None
    }
    same_number = Counter(references.values())
    for item in sorted(snapshots, key=lambda listed: listed.key):
        reference = references.get(item.key)
        if reference is None or reference in kept_refs:
            continue
        if reference in all_refs and same_number[reference] > 1:
            protected += 1
            continue
        if reference in all_refs:
            doomed_snapshots.append(item.key)
            owner.setdefault(reference, []).append(item.key)
            continue
        if include_orphans and item.last_modified is not None and item.last_modified < cutoff:
            doomed_snapshots.append(item.key)
        else:
            protected += 1

    doomed_pointers = [key for key in sorted(keys, reverse=True) if key not in kept]
    chosen_snapshots = doomed_snapshots[:limit]
    remaining = limit - len(chosen_snapshots)
    gone = set(chosen_snapshots)
    chosen_pointers: list[str] = []
    for key in doomed_pointers:
        if remaining <= 0:
            break
        exclusive = [
            snapshot
            for name, seq in member_seqs_from_pointer_key(key).items()
            if (name, seq) not in kept_refs
            for snapshot in owner.get((name, seq), [])
        ]
        if all(snapshot in gone for snapshot in exclusive):
            chosen_pointers.append(key)
            remaining -= 1
    return PrunePlan(
        snapshots=tuple(chosen_snapshots),
        pointers=tuple(chosen_pointers),
        kept_generations=len(kept),
        protected_orphans=protected,
        deferred=len(doomed_snapshots)
        + len(doomed_pointers)
        - (len(chosen_snapshots) + len(chosen_pointers)),
    )


def _kept_pointers(
    newest_first: Sequence[str],
    moments: Mapping[str, datetime | None],
    cutoff: datetime,
    keep_last: int,
) -> set[str]:
    kept = {newest_first[0]}
    pairs: set[tuple[int, int]] = set()
    for key in newest_first:
        seqs = member_seqs_from_pointer_key(key)
        pair = (seqs["simulation"], seqs["equipment"])
        moment = moments[key]
        if moment is None or moment >= cutoff:
            kept.add(key)
        if pair not in pairs and len(pairs) < keep_last:
            kept.add(key)
            pairs.add(pair)
    return kept


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
    *,
    head_seq: int | None,
    extra: Mapping[str, str] | None = None,
) -> str:
    """판정을 사람이 읽는 한국어 한 줄로 바꾼다. 화면과 스크립트가 같은 문구를 쓴다."""
    generation = "없음" if head_seq is None else f"seq {head_seq}"
    details = dict(extra or {})
    push_messages: Mapping[PushDecision, str] = {
        PushDecision.PUBLISH: f"두 DB 의 변경을 올립니다(원격 {generation}).",
        PushDecision.UP_TO_DATE: f"두 DB 는 원격과 같습니다(원격 {generation}).",
        PushDecision.PARENT_MOVED: (
            f"원격이 먼저 앞섰습니다(원격 {generation}). 로컬 저장은 그대로 있습니다 — "
            "resolve 로 어느 쪽을 남길지 정하세요."
        ),
        PushDecision.FORKED: (
            f"원격이 갈라져 있습니다(원격 {generation}). 양쪽 파일은 모두 남아 있습니다 — "
            "rollback 으로 이어 갈 세대를 정하세요."
        ),
        PushDecision.BLOCKED_UNPUBLISHED: (
            "아직 게시하지 못한 스냅샷이 있습니다. 그것을 먼저 정리해야 합니다."
        ),
        PushDecision.REMOTE_EMPTY: (
            "원격이 비어 있습니다. 최초 이관은 sync 스크립트의 init 이 합니다."
        ),
        PushDecision.UNKNOWN_BASE: (
            f"이 DB 가 어느 세대에서 왔는지 모릅니다(원격 {generation}). 원격을 덮지 않습니다 — "
            "adopt --source local 또는 pull --force 로 기준을 정하세요."
        ),
    }
    # 두 열거형은 `str` 을 섞은 Enum 이고 `up_to_date`·`remote_empty` 값이 겹친다. 한 사전에
    # 담으면 같은 값끼리 키가 충돌해 뒤에 적은 pull 문구가 push 문구를 덮어쓴다.
    pull_messages: Mapping[PullDecision, str] = {
        PullDecision.DOWNLOAD: f"두 DB 를 원격 {with_direction_particle(generation)} 내려받습니다.",
        PullDecision.UP_TO_DATE: f"두 DB 는 이미 원격 {generation} 입니다.",
        PullDecision.AMBIGUOUS: (
            "로컬 DB 가 어느 세대에서 왔는지 알 수 없습니다. 자동으로 덮지 않습니다 — "
            "adopt 로 어느 쪽을 기준으로 삼을지 정하세요."
        ),
        PullDecision.BLOCKED_DIRTY: ("이 PC 에만 있는 변경이 있습니다. 먼저 올린 뒤 내려받으세요."),
        PullDecision.BLOCKED_FORKED: f"원격이 갈라져 있어 내려받지 않습니다(원격 {generation}).",
        PullDecision.REMOTE_EMPTY: (
            "원격이 비어 있습니다. 최초 이관은 sync 스크립트의 init 이 합니다."
        ),
        PullDecision.LOCAL_MISSING: (
            f"로컬 DB 가 없어 원격 {with_object_particle(generation)} 받습니다."
        ),
    }
    message = (
        push_messages[decision] if isinstance(decision, PushDecision) else pull_messages[decision]
    )
    if details:
        message += " · " + " · ".join(f"{key} {value}" for key, value in sorted(details.items()))
    return message


def _require_sequence(seq: int) -> None:
    if seq < 0 or seq > SEQUENCE_SPACE:
        raise ValueError(f"시퀀스는 0 이상 {SEQUENCE_SPACE} 이하여야 합니다: {seq}")


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
