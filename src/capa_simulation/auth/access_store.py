# Purpose: S3 접속 명단 파일을 읽어 메모리 한 벌로 올리고 관리자의 고침을 S3 저장 뒤 반영한다.

"""S3 명단 — 사람을 넣고 뺄 때 재시작하지 않게.

흐름은 셋이다.

- **앱 시작** — 진입 파일이 한 번 받아 메모리에 올린다(`read_at_start`). 못 읽어도 앱은 뜨고
  관리자만 통과한다(열림으로 떨어지지 않는다).
- **접속 판정** — 메모리의 한 벌(`runtime.current_access`)로만 한다. 판정이 S3 에 가지 않으므로
  잘 읽어 둔 뒤에는 S3 가 막혀도 판정이 이어진다.
- **명단 수정** — Admin 화면 → S3 PUT 성공 → 메모리 교체(`save_changes`). 재시작이 없다. 실패면
  메모리는 그대로다.

파일은 작은 JSON 객체 하나다 — 형식 판(`format`) · 고칠 때마다 느는 판 번호(`revision`) · 사용자
항목 · 고친 기록 마지막 200건. **받아 둔 파일이 없을 때** 키가 없으면(404 `NoSuchKey`) 첫 판이다 —
환경변수 `CAPA_ACCESS_USERS` 를 그대로 쓰고, 그것도 비면 빈 명단이다(「못 읽음」 이 아니다). 첫
저장이 그 목록 + 고침을 판 1 로 쓰고, 그 뒤로 환경변수는 듣지 않는다. 받아 둔 파일이 있었는데 없다고
하면 실패(`KIND_FILE_GONE`)이고 메모리 명단을 그대로 둔다 — 메모리가 마지막 사본일 수 있고, 저장소
앞단의 일시 오류로 전원을 거절하지 않게.

**첫 판은 처음 한 번뿐이다.** 메모리는 재시작하면 비므로 「받아 둔 파일」 만으로는 새 프로세스가
처음과 사라짐을 못 가른다 — 그러면 파일이 지워진 뒤 옛 환경변수 명단이 되살아나 닫힘이 열림으로
바뀐다. 그래서 첫 저장 때 표지 객체(`names.ACCESS_SEEDED_OBJECT`)를 함께 쓰고, 표지가 있는데 파일이
없으면 받아 둔 파일이 없어도 `KIND_FILE_GONE` 이다(관리자만). 표지는 명단 다음에 쓴다 — 표지가 먼저
들어가고 명단이 실패하면 첫 판이 사라져 사용자가 모두 막힌다. 표지를 못 쓰면 다음 저장이 다시 쓴다.

깨졌거나 형식 판을 모르면 「못 읽음」 이다. 항목은 `access.entry_key` 꼴 판정을 그대로 거치고 읽지
못한 항목은 개수만 센다. 등급 칸은 사용자로만 읽는다 — 관리자는 환경변수뿐이다.

**새 배경 스레드를 세우지 않는다**(AGENTS 9장). 못 읽은 채로 뜬 프로세스는 콜백이 거절하기 직전
(`web.callback` → 스레드 풀 → `retry_unread`, 60초에 한 번까지)이나 Admin 「다시 읽기」 가 다시
읽는다. **이벤트 루프에서 네트워크를 부르지 않는다** — 콜백은 스레드 풀로 넘긴다.

입출력은 프로세스 잠금 하나로 줄 세운다(같은 프로세스의 동시 저장 · 읽기 — replica 1 전제). 저장
직전에 받을 때의 ETag(주지 않는 저장소면 판 번호)와 지금을 견줘 다르면 덮지 않고 「다시 읽기」 로
돌려보낸다. 조건부 쓰기(`If-Match`)는 쓰지 않는다 — 확인되지 않은 능력이다(`io/s3_small`).

쓰기 함수(`save_changes` · `reread`)는 화면과 별개로 신원 · 관리자를 다시 본다 — 위젯 콜백은 그
회차의 본문보다 먼저 돌고, 보인 회차와 누른 회차의 권한이 달라질 수 있다. 이 벽은 화면의 실수를
막는 것이고 같은 프로세스의 코드를 막지 못한다 — 모듈 코드가 의도를 가지면 이 함수와 키에 닿는다
(`docs/sso_setup.md` 4장, 방어선은 앱 관리자의 PR 점검). 명단의 값(넣고 뺀 사람의 loginid)은 사건 ·
로그 · repr 에 싣지 않고 개수만 싣는다. 저지른 관리자의 계정만 다른 사건과 같은 규칙으로 싣는다 —
서버 로그에는 전체 값(`login_ok` 와 같다), Admin 표에는 앞 두 글자.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Final

from capa_simulation.auth import names, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    AccessSource,
    ListChange,
    ListDocument,
    ListEntry,
    SourceProblem,
    compose_access,
    entry_key,
)
from capa_simulation.auth.config import SsoConfig, SsoMode
from capa_simulation.auth.identity import Identity, session_problem
from capa_simulation.io.s3_small import (
    KIND_OTHER,
    KIND_TIMEOUT,
    KIND_TLS,
    KIND_UNREACHABLE,
    S3Failure,
    S3Target,
    get_object,
    head_object,
    put_object,
)

OBJECT_FORMAT: Final = 1
MAX_CHANGES: Final = 200
RETRY_SECONDS: Final = 60

# `io/s3_small` 분류에 이 층이 더하는 까닭.
KIND_CORRUPT: Final = "corrupt"
KIND_UNKNOWN_FORMAT: Final = "unknown_format"
KIND_CONFIG: Final = "config"
KIND_FILE_GONE: Final = "file_gone"

# 보낸 뒤 답을 받지 못한 PUT 의 까닭 — 저장소에 들어갔는지 모른다.
_NO_ANSWER_KINDS: Final = frozenset({KIND_TIMEOUT, KIND_UNREACHABLE, KIND_TLS})

CHANGE_ADD: Final = "add"
CHANGE_REMOVE: Final = "remove"
CHANGE_DROP: Final = "drop_unreadable"
CHANGE_SEED: Final = "seed_users"

_IO_LOCK = threading.Lock()


class NotAdminError(PermissionError):
    """쓰기를 부른 사람이 지금 관리자가 아니다(또는 세션이 끝났다)."""


class StoreUnreadError(RuntimeError):
    """아직 명단을 읽지 못해 무엇을 덮을지 모른다 — 저장하지 않는다."""


class StoreConflictError(RuntimeError):
    """받은 뒤 저장소의 파일이 바뀌었다 — 덮지 않고 다시 읽게 한다."""


class SaveUnconfirmedError(S3Failure):
    """PUT 을 보내고 답을 받지 못했다 — 저장소에 들어갔는지 모른다. 메모리는 그대로다."""


@dataclass(frozen=True)
class SaveResult:
    """저장 한 번의 결과 — 개수만(값 없음). `revision` 은 저장 뒤 판 번호다."""

    added: int = 0
    removed: int = 0
    already: int = 0
    absent: int = 0
    revision: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def _text_field(raw: Mapping[str, Any], name: str) -> str:
    value = raw.get(name)
    return value if isinstance(value, str) else ""


def _parse_entries(raw: object) -> tuple[tuple[ListEntry, ...], int, int]:
    """파일의 사용자 칸 → (항목들, 읽지 못한 수, 등급을 사용자로 읽은 수)."""
    if not isinstance(raw, list):
        raise S3Failure(KIND_CORRUPT)
    entries: dict[str, ListEntry] = {}
    unreadable = demoted = 0
    for item in raw:
        loginid = item.get("loginid") if isinstance(item, dict) else None
        key = entry_key(loginid) if isinstance(loginid, str) else None
        if key is None or not isinstance(item, dict):
            unreadable += 1
            continue
        if item.get("grade", GRADE_USER) != GRADE_USER:
            demoted += 1
        entries[key] = ListEntry(key, _text_field(item, "added_by"), _text_field(item, "added_at"))
    return tuple(entries.values()), unreadable, demoted


def _parse_changes(raw: object) -> tuple[ListChange, ...]:
    """고친 기록 칸 — 판정에 쓰지 않으니 꼴이 틀린 줄은 버린다(깨짐으로 보지 않는다)."""
    if not isinstance(raw, list):
        return ()
    return tuple(
        ListChange(
            by=_text_field(item, "by"),
            at=_text_field(item, "at"),
            what=_text_field(item, "what"),
            loginid=_text_field(item, "loginid"),
        )
        for item in raw[-MAX_CHANGES:]
        if isinstance(item, dict)
    )


def _decoded(body: bytes) -> object:
    """파일 바이트 → JSON 값. 못 읽으면 `None`.

    실패를 여기서 올리지 않는다 — JSON 오류는 문서 전체(`doc`)를 들어, 처리 블록 안에서 올리면
    명단이 예외 사슬에 남는다. `ValueError` 는 UTF-8 · JSON 오류와 정수 자릿수 상한을 함께 받는다.
    """
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None


def parse_document(body: bytes) -> ListDocument:
    """파일 바이트 → 한 벌. 깨졌거나 형식 판을 모르면 `S3Failure`(값을 담지 않는다)."""
    payload = _decoded(body)
    if not isinstance(payload, dict):
        raise S3Failure(KIND_CORRUPT)
    if payload.get("format") != OBJECT_FORMAT:
        raise S3Failure(KIND_UNKNOWN_FORMAT)
    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise S3Failure(KIND_CORRUPT)
    entries, unreadable, demoted = _parse_entries(payload.get("users"))
    return ListDocument(
        revision=revision,
        entries=entries,
        changes=_parse_changes(payload.get("changes")),
        unreadable=unreadable,
        demoted=demoted,
    )


def render_document(document: ListDocument) -> bytes:
    """한 벌 → 파일 바이트. 사람이 저장소에서 열어 볼 수 있게 들여 쓴다."""
    payload = {
        "format": OBJECT_FORMAT,
        "revision": document.revision,
        "users": [
            {
                "loginid": entry.loginid,
                "grade": GRADE_USER,
                "added_by": entry.added_by,
                "added_at": entry.added_at,
            }
            for entry in document.entries
        ],
        "changes": [
            {"by": item.by, "at": item.at, "what": item.what, "loginid": item.loginid}
            for item in document.changes[-MAX_CHANGES:]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")


def is_on(cfg: SsoConfig) -> bool:
    """S3 명단을 쓰는 서버인가 — 통합인증이 켜졌고 키가 있다. 꺼진 서버는 S3 에 가지 않는다."""
    return cfg.mode is SsoMode.ON and cfg.access_s3_requested


def is_unread(cfg: SsoConfig) -> bool:
    """켜졌는데 아직 한 번도 읽지 못했는가(자가 회복 · 저장 막기 · Admin 경고의 판정)."""
    if not is_on(cfg):
        return False
    source = runtime.access_source()
    return source is None or source.document is None


def _base_source(cfg: SsoConfig) -> AccessSource:
    source = runtime.access_source()
    return AccessSource(access=cfg.access) if source is None else source


def problem_of(failure: S3Failure) -> SourceProblem:
    return SourceProblem(
        failure.kind,
        failure.status,
        failure.code,
        unconfirmed=isinstance(failure, SaveUnconfirmedError),
    )


def _holds_a_file(source: AccessSource) -> bool:
    """파일을 받아 둔 칸인가 — 못 읽은 칸과 없는 파일을 빈 명단 · 첫 판으로 읽은 칸은 아니다."""
    document = source.document
    if document is None or source.seeded:
        return False
    return bool(source.etag or document.revision or document.entries)


def holds_a_file() -> bool:
    """지금 파일을 받아 둔 서버인가 — 화면이 「환경변수를 쓰지 않음」 알림을 세울지 가른다."""
    source = runtime.access_source()
    return source is not None and _holds_a_file(source)


def _seed_document(cfg: SsoConfig) -> ListDocument:
    return ListDocument(entries=tuple(ListEntry(key) for key in cfg.access_seed_users))


def _fetch(cfg: SsoConfig, moment: int, *, held: bool) -> tuple[ListDocument, str, bool]:
    """받아 읽는다 — `(한 벌, ETag, 첫 판인가)`. 어떤 실패든 `S3Failure` 하나다(기동 · 콜백을 막지
    못한다).

    `held` 면 파일을 받아 둔 칸이라 「없음」 도 실패다. 표지 객체가 있어도 그렇다(모듈 설명).
    """
    target = cfg.access_s3
    if target is None:
        raise S3Failure(KIND_CONFIG)
    try:
        found = get_object(target, cfg.access_object_key, moment=moment)
        if found is not None:
            return parse_document(found.body), found.etag, False
        if not held and not cfg.access_seed_users:
            return ListDocument(), "", False
        if not held and head_object(target, names.ACCESS_SEEDED_OBJECT, moment=moment) is None:
            return _seed_document(cfg), "", True
        failure = S3Failure(KIND_FILE_GONE, 404, "NoSuchKey")
    except S3Failure:
        raise
    except Exception as exc:  # noqa: BLE001 — 예상 못 한 실패도 「못 읽음」 이다
        failure = S3Failure(KIND_OTHER, code=type(exc).__name__)
    raise failure


def _read_locked(cfg: SsoConfig, moment: int, *, retrying: bool = False) -> SourceProblem | None:
    """입출력 잠금 안에서 받아 한 벌을 바꾼다. 실패면 전의 명단을 그대로 두고 까닭만 적는다.

    `retrying` 은 자가 회복이다 — 실패를 고리에 적지 않고 누계만 센다(들어오지 못하는 사람이
    되풀이해 남길 수 있다, `runtime.ACCESS_RETRY_FAILED_EVENT`).
    """
    base = _base_source(cfg)
    try:
        document, etag, seeded = _fetch(cfg, moment, held=_holds_a_file(base))
    except S3Failure as failure:
        problem = problem_of(failure)
        runtime.publish_access_source(replace(base, attempted_at=moment, problem=problem))
        runtime.record_event(
            runtime.ACCESS_RETRY_FAILED_EVENT if retrying else "access_read",
            level=logging.WARNING,
            reason=problem.kind,
            status=str(problem.status or "-"),
        )
        return problem
    runtime.publish_access_source(
        replace(
            base,
            access=compose_access(cfg.access, document),
            document=document,
            etag=etag,
            read_at=moment,
            attempted_at=moment,
            problem=None,
            seeded=seeded,
            # 답을 받지 못한 쓰기는 읽어 보면 결과를 안다(들어갔으면 지금 한 벌에 있다).
            save_problem=(
                None
                if base.save_problem is not None and base.save_problem.unconfirmed
                else base.save_problem
            ),
        )
    )
    runtime.record_event(
        "access_read", users=str(len(document.entries)), revision=str(document.revision)
    )
    return None


def read_at_start(cfg: SsoConfig, *, now: int | None = None) -> None:
    """진입 파일이 기동 때 한 번 부른다. 꺼진 서버는 아무것도 하지 않는다."""
    if not is_on(cfg):
        return
    with _IO_LOCK:
        _read_locked(cfg, int(time.time()) if now is None else now)


def retry_unread(cfg: SsoConfig, *, now: int | None = None) -> None:
    """못 읽은 채로 떴으면 다시 읽어 본다 — 60초에 한 번까지. 스레드 풀에서 부른다."""
    moment = int(time.time()) if now is None else now
    if not is_unread(cfg):
        return
    if runtime.access_source() is None:
        # 진입 파일을 지나지 않고 켜진 경우의 첫 칸 — 시도 시각이 비어 곧바로 통과한다.
        runtime.publish_access_source(AccessSource(access=cfg.access))
    if not runtime.claim_access_retry(moment, RETRY_SECONDS):
        return
    if not _IO_LOCK.acquire(blocking=False):
        return
    try:
        _read_locked(cfg, moment, retrying=True)
    finally:
        _IO_LOCK.release()


def is_admin(cfg: SsoConfig, loginid: str) -> bool:
    """지금 관리자인가 — 합성 명단의 등급으로 묻는다(관리자는 환경변수 몫에서만 온다)."""
    return runtime.current_access(cfg).grade_of(loginid) == GRADE_ADMIN


def _require_admin(cfg: SsoConfig, identity: Identity | None, moment: int) -> Identity:
    """쓰는 자리의 두 번째 벽 — 신원이 지금도 유효하고 관리자인가."""
    if identity is None or session_problem(identity, cfg, moment) is not None:
        raise NotAdminError("session")
    if not is_admin(cfg, identity.loginid):
        raise NotAdminError("grade")
    return identity


def reread(
    cfg: SsoConfig, identity: Identity | None, *, now: int | None = None
) -> SourceProblem | None:
    """Admin 「다시 읽기」. 관리자만. 실패의 까닭을 돌려주고 메모리는 그대로다."""
    moment = int(time.time()) if now is None else now
    _require_admin(cfg, identity, moment)
    with _IO_LOCK:
        return _read_locked(cfg, moment)


def _iso_text(moment: int) -> str:
    return datetime.fromtimestamp(moment, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _changed_document(
    document: ListDocument,
    actor: str,
    *,
    add: Iterable[str],
    remove: Iterable[str],
    moment: int,
    seeded: bool = False,
) -> tuple[ListDocument, SaveResult]:
    """고침을 얹은 새 한 벌과 개수. 판 번호는 바뀐 것이 있을 때만 는다. 값은 꼴을 거친 것이다.

    `seeded` 면 첫 판이 파일이 되는 저장이다 — 환경변수에서 온 사람은 기록이 없으니 수로 남긴다.
    """
    stamp = _iso_text(moment)
    entries = {entry.loginid: entry for entry in document.entries}
    changes: list[ListChange] = []
    added = already = removed = absent = 0
    for key in dict.fromkeys(add):
        if key in entries:
            already += 1
            continue
        entries[key] = ListEntry(key, actor, stamp)
        changes.append(ListChange(actor, stamp, CHANGE_ADD, key))
        added += 1
    for key in dict.fromkeys(remove):
        if entries.pop(key, None) is None:
            absent += 1
            continue
        changes.append(ListChange(actor, stamp, CHANGE_REMOVE, key))
        removed += 1
    if not changes:
        return document, SaveResult(already=already, absent=absent, revision=document.revision)
    if document.unreadable:
        # 다시 쓰면 읽지 못한 항목은 파일에서 사라진다 — 무엇을 잃었는지 기록에 수로 남긴다.
        changes.append(ListChange(actor, stamp, f"{CHANGE_DROP} {document.unreadable}"))
    if seeded:
        changes.insert(0, ListChange(actor, stamp, f"{CHANGE_SEED} {len(document.entries)}"))
    revision = document.revision + 1
    fresh = ListDocument(
        revision=revision,
        entries=tuple(sorted(entries.values(), key=lambda entry: entry.loginid)),
        changes=(*document.changes, *changes)[-MAX_CHANGES:],
    )
    return fresh, SaveResult(added, removed, already, absent, revision)


def _remote_unchanged(target: S3Target, key: str, source: AccessSource, moment: int) -> bool:
    """저장소의 파일이 받을 때 그대로인가 — ETag 로, 그 값이 없으면 본문의 판 번호로 본다."""
    assert source.document is not None
    remote_etag = head_object(target, key, moment=moment)
    # 받을 때 파일이 없었던 칸(우리가 쓴 파일의 판 번호는 1 부터다) — 지금도 없어야 한다.
    was_missing = source.document.revision == 0 and not source.etag
    if remote_etag is None or was_missing:
        return remote_etag is None and was_missing
    if remote_etag and source.etag:
        return remote_etag == source.etag
    found = get_object(target, key, moment=moment)
    return found is not None and parse_document(found.body).revision == source.document.revision


def _left_seed_mark(target: S3Target, actor: str, moment: int) -> bool:
    """표지 객체를 쓴다. 실패는 저장 실패가 아니다 — 명단은 이미 들어갔고 다음 저장이 다시 쓴다."""
    try:
        put_object(target, names.ACCESS_SEEDED_OBJECT, b'{"format": 1}', moment=moment)
    except S3Failure as failure:
        runtime.record_event(
            "access_seed_mark_failed",
            level=logging.WARNING,
            loginid=actor,
            reason=failure.kind,
            status=str(failure.status or "-"),
        )
        return False
    return True


def _put_noting_no_answer(target: S3Target, key: str, body: bytes, moment: int) -> str:
    """올린다. 답을 받지 못하면 `SaveUnconfirmedError` — 앞의 대조에서 끊긴 실패와 가른다."""
    try:
        return put_object(target, key, body, moment=moment)
    except S3Failure as failure:
        if failure.kind not in _NO_ANSWER_KINDS:
            raise
        unconfirmed = SaveUnconfirmedError(failure.kind, failure.status, failure.code)
    raise unconfirmed


def save_changes(
    cfg: SsoConfig,
    identity: Identity | None,
    *,
    add: Iterable[str] = (),
    remove: Iterable[str] = (),
    now: int | None = None,
) -> SaveResult:
    """관리자의 고침 하나. 저장소에 먼저 쓰고, 쓴 뒤에만 메모리를 바꾼다.

    `NotAdminError`(권한) · `StoreUnreadError`(아직 못 읽음) · `StoreConflictError`(그 사이 바뀜) ·
    `SaveUnconfirmedError`(PUT 의 답을 받지 못함 — 들어갔는지 모른다, `S3Failure` 의 하나) ·
    `S3Failure`(대조 실패 · 거절된 PUT — 저장소 그대로, 파일이 상한을 넘어도 이것)를 낸다. 어느
    쪽이든 메모리는 그대로다. 바뀐 것이 없으면 쓰지 않는다.
    """
    moment = int(time.time()) if now is None else now
    actor = _require_admin(cfg, identity, moment).loginid
    with _IO_LOCK:
        source = runtime.access_source()
        target = cfg.access_s3
        if source is None or source.document is None or target is None:
            raise StoreUnreadError
        fresh, result = _changed_document(
            source.document, actor, add=add, remove=remove, moment=moment, seeded=source.seeded
        )
        if not result.changed:
            return result
        try:
            if not _remote_unchanged(target, cfg.access_object_key, source, moment):
                runtime.record_event(
                    "access_save_failed",
                    level=logging.WARNING,
                    loginid=actor,
                    reason="conflict",
                )
                raise StoreConflictError
            etag = _put_noting_no_answer(
                target, cfg.access_object_key, render_document(fresh), moment
            )
        except S3Failure as failure:
            problem = problem_of(failure)
            runtime.publish_access_source(replace(source, save_problem=problem))
            runtime.record_event(
                "access_save_failed",
                level=logging.WARNING,
                loginid=actor,
                reason=problem.kind,
                status=str(problem.status or "-"),
            )
            raise
        mark_missing = (source.seeded or source.seed_mark_pending) and not _left_seed_mark(
            target, actor, moment
        )
        runtime.publish_access_source(
            replace(
                source,
                access=compose_access(cfg.access, fresh),
                document=fresh,
                etag=etag,
                # 저장소에 닿았고 방금 쓴 것이 지금 명단이다 — 앞선 읽기 실패 경고를 남기지 않는다.
                problem=None,
                saved_at=moment,
                save_problem=None,
                seeded=False,
                seed_mark_pending=mark_missing,
            )
        )
        runtime.record_event(
            "access_saved",
            loginid=actor,
            added=str(result.added),
            removed=str(result.removed),
            revision=str(result.revision),
        )
        return result
