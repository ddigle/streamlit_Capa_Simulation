# Purpose: S3 접속 명단 파일을 읽어 메모리 한 벌로 올리고 관리자의 고침을 S3 저장 뒤 반영한다.

"""S3 명단 — 사람을 넣고 뺄 때 재시작하지 않게.

흐름은 셋이다.

- **앱 시작** — 진입 파일이 한 번 받아 메모리에 올린다(`read_at_start`). 못 읽어도 앱은 뜨고
  관리자만 통과한다(열림으로 떨어지지 않는다).
- **접속 판정** — 메모리의 한 벌(`runtime.current_access`)로만 한다. 판정이 S3 에 가지 않으므로
  잘 읽어 둔 뒤에는 S3 가 막혀도 판정이 이어진다.
- **명단 수정** — Admin 화면 → S3 PUT 성공 → 메모리 교체(`save_changes` — 넣기 · 빼기 · 등급
  바꾸기). 재시작이 없다. 실패면 메모리는 그대로다.
- **스스로 등록** — 거절 화면의 「접속 권한 신청」(`web.register` → 스레드 풀 →
  `register_self`). 신원은 콜백이 심은 거절 표에서만 오고, 늘 일반 등급이며, 이미 있으면 쓰지
  않는다(등급 그대로).

파일은 작은 JSON 객체 하나다 — 형식 판(`format`) · 고칠 때마다 느는 판 번호(`revision`) · 사용자
항목 · 고친 기록 마지막 200건. **받아 둔 파일이 없을 때** 키가 없으면(404 `NoSuchKey`) 첫 판이다 —
환경변수 `CAPA_ACCESS_USERS` 를 그대로 쓰고, 그것도 비면 빈 명단이다(「못 읽음」 이 아니다). 첫
저장이 그 목록 + 고침을 판 1 로 쓰고, 그 뒤로 환경변수는 듣지 않는다. 받아 둔 파일이 있었는데 없다고
하면 실패(`KIND_FILE_GONE`)이고 메모리 명단을 그대로 둔다 — 메모리가 마지막 사본일 수 있고, 저장소
앞단의 일시 오류로 전원을 거절하지 않게.

**첫 판은 처음 한 번뿐이다.** 메모리는 재시작하면 비므로 「받아 둔 파일」 만으로는 새 프로세스가
처음과 사라짐을 못 가른다 — 그러면 파일이 지워진 뒤 옛 환경변수 명단이 되살아나 닫힘이 열림으로
바뀐다. 그래서 **파일이 있으면 표지 객체(`names.ACCESS_SEEDED_OBJECT`)도 있게 맞춘다** — 파일을 처음
만든 저장이 쓰고, 파일을 받은 읽기가 표지가 없으면 쓴다(답 끊긴 첫 저장 · 표지만 실패한 저장 · 앞
코드가 만든 파일 · 옮긴 버킷). 표지가 있는데 파일이 없으면 받아 둔 파일이 없어도, 환경변수가 비어
있어도 `KIND_FILE_GONE` 이다(관리자만). 표지는 명단 다음에 쓴다 — 표지가 먼저 들어가고 명단이
실패하면 첫 판이 사라져 사용자가 모두 막힌다. 표지를 못 써도 저장 · 읽기의 실패가 아니다 — 다음
저장 · 다음 읽기가 다시 쓴다. 표지는 GET 으로 본다 — HEAD 는 본문이 없어 코드 없는 404 를 없음으로
읽는다.

깨졌거나 형식 판을 모르면 「못 읽음」 이다. 항목은 `access.entry_key` 꼴 판정을 그대로 거치고 읽지
못한 항목은 개수만 센다. 등급 칸은 `user` · `admin` 둘이고 그 밖은 일반으로 읽는다
(`demoted`). 이름 · 부서 · 든 길(`via`) 칸은 형식 판 1 에 더한 칸이다 — 판을 올리지 않아 옛
코드는 그 칸을 버리고 읽고(관리자 등급은 일반으로), 이 코드는 그 칸이 없는 옛 파일을 빈 이름 ·
부서 · 관리자가 넣음으로 읽는다.

**새 배경 스레드를 세우지 않는다**(AGENTS 9장). 못 읽은 채로 뜬 프로세스는 콜백이 거절하기 직전
(`web.callback` → 스레드 풀 → `retry_unread`, 60초에 한 번까지)이나 Admin 「다시 읽기」 가 다시
읽는다. **이벤트 루프에서 네트워크를 부르지 않는다** — 콜백은 스레드 풀로 넘긴다.

입출력은 프로세스 잠금 하나로 줄 세운다(같은 프로세스의 동시 저장 · 등록 · 읽기 — replica 1
전제). 관리자의 저장은 직전에 받을 때의 ETag(주지 않는 저장소면 판 번호)와 지금을 견줘 다르면
덮지 않고 「다시 읽기」 로 돌려보낸다(그 화면에 「다시 읽기」 가 있다). 스스로 등록은 누를 「다시
읽기」 가 없어 쓰기 직전에 저장소의 지금 판을 다시 받아 그 위에 얹는다(합침) — 그 사이 다른
쓰기가 들인 사람 · 등급을 잃지 않는다. 받은 판이 메모리 판보다 오래되면 얹지 않고 실패다(뺀 사람 ·
관리자 등급이 되살아나지 않게). 조건부 쓰기(`If-Match`)는 쓰지 않는다 — 확인되지 않은
능력이다(`io/s3_small`). 그래서 같은 버킷을 쓰는 다른 프로세스와의 받기 → 쓰기 틈은 replica 1
전제로 받아들인다.

관리자 쓰기 함수(`save_changes` · `reread`)는 화면과 별개로 신원 · 관리자를 다시 본다 — 위젯
콜백은 그 회차의 본문보다 먼저 돌고, 보인 회차와 누른 회차의 권한이 달라질 수 있다. 등급 규칙도
여기서 본다 — 환경변수 관리자는 일반으로 못 내리고(`EnvAdminError`), 자기 자신은 내리거나 지우지
못한다(`SelfChangeError`). 이 벽은 화면의 실수를
막는 것이고 같은 프로세스의 코드를 막지 못한다 — 모듈 코드가 의도를 가지면 이 함수와 키에 닿는다
(`docs/sso_setup.md` 4장, 방어선은 앱 관리자의 PR 점검). 명단의 값(넣고 뺀 사람의 loginid)은 사건 ·
로그 · repr 에 싣지 않고 개수만 싣는다. 저지른 관리자의 계정만 다른 사건과 같은 규칙으로 싣는다 —
서버 로그에는 전체 값(`login_ok` 와 같다), Admin 표에는 앞 두 글자. 스스로 등록은 저지른 사람이 곧
대상이라 사건 · 로그에 계정을 싣지 않는다 — 계정은 감사 기록(`user_self_registered`)에만 있다.
그 실패는 명단 밖 사람이 되풀이해 남길 수 있어 사건 고리에 두지 않고 누계만 센다
(`runtime.SELF_REGISTER_FAILED_EVENT`). 스스로 등록에 딸린 다시 쓰기의 일(못 읽은 항목이 빠짐 ·
첫 판 심기)은 그 사람이 아니라 자동 행위로 감사에 남긴다.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Final, NamedTuple

from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.auth import names, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    GRADES,
    VIA_ADMIN,
    VIA_SELF,
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
from capa_simulation.auth.tokens import clean_text
from capa_simulation.io import s3_small as s3_small_kinds
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
CHANGE_SELF: Final = "self_add"
CHANGE_REMOVE: Final = "remove"
CHANGE_GRADE: Final = "grade"
CHANGE_DROP: Final = "drop_unreadable"
CHANGE_SEED: Final = "seed_users"
# 이름 · 부서 칸의 글자 수 끝(통합인증 표시 칸 `tokens.MAX_DISPLAY_LENGTH` 와 같다).
MAX_PROFILE_LENGTH: Final = 100

_IO_LOCK = threading.Lock()


class NotAdminError(PermissionError):
    """쓰기를 부른 사람이 지금 관리자가 아니다(또는 세션이 끝났다)."""


class StoreUnreadError(RuntimeError):
    """아직 명단을 읽지 못해 무엇을 덮을지 모른다 — 저장하지 않는다."""


class StoreConflictError(RuntimeError):
    """받은 뒤 저장소의 파일이 바뀌었다 — 덮지 않고 다시 읽게 한다."""


class SaveUnconfirmedError(S3Failure):
    """PUT 을 보내고 답을 받지 못했다 — 저장소에 들어갔는지 모른다. 메모리는 그대로다."""


class SelfChangeError(PermissionError):
    """자기 자신의 등급을 일반으로 내리거나 자기를 명단에서 빼려 했다 — 쓰지 않는다."""


class EnvAdminError(PermissionError):
    """환경변수 관리자를 일반으로 내리려 했다 — 늘 관리자라 화면에서 빼지 못한다."""


class RegisterRefusedError(ValueError):
    """스스로 등록할 수 없는 계정이다(명단 항목 꼴이 아님) — 쓰지 않는다."""


@dataclass(frozen=True)
class SaveResult:
    """저장 한 번의 결과 — 개수만(값 없음). `revision` 은 저장 뒤 판 번호다."""

    added: int = 0
    removed: int = 0
    already: int = 0
    absent: int = 0
    revision: int = 0
    graded: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.graded)


def _text_field(raw: Mapping[str, Any], name: str) -> str:
    value = raw.get(name)
    return value if isinstance(value, str) else ""


def profile_text(value: object) -> str:
    """이름 · 부서 칸 — 글자만, 제어 · 서식 문자를 빼고 `MAX_PROFILE_LENGTH` 에서 자른다."""
    return clean_text(value, MAX_PROFILE_LENGTH) if isinstance(value, str) else ""


def _parse_entries(raw: object) -> tuple[tuple[ListEntry, ...], int, int]:
    """파일의 사용자 칸 → (항목들, 읽지 못한 수, 등급을 일반으로 읽은 수)."""
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
        grade = item.get("grade", GRADE_USER)
        if grade not in GRADES:
            demoted += 1
            grade = GRADE_USER
        entries[key] = ListEntry(
            key,
            _text_field(item, "added_by"),
            _text_field(item, "added_at"),
            name=profile_text(item.get("name")),
            dept=profile_text(item.get("dept")),
            via=VIA_SELF if item.get("via") == VIA_SELF else VIA_ADMIN,
            grade=str(grade),
        )
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
                "grade": entry.grade if entry.grade in GRADES else GRADE_USER,
                "name": entry.name,
                "dept": entry.dept,
                "via": entry.via if entry.via == VIA_SELF else VIA_ADMIN,
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


# 다시 해도 같은 까닭 — 관리자가 설정 · 파일 · 권한을 고쳐야 풀린다(거절 화면이 「1분 뒤」 를 말하지
# 않는다). 그 밖(닿지 못함 · 시간 초과 · 인증서 · 5xx)은 잠시 뒤 풀릴 수 있다.
_ADMIN_FIX_KINDS: Final = frozenset(
    {
        KIND_CONFIG,
        KIND_FILE_GONE,
        KIND_CORRUPT,
        KIND_UNKNOWN_FORMAT,
        s3_small_kinds.KIND_AUTH,
        s3_small_kinds.KIND_NO_BUCKET,
        s3_small_kinds.KIND_TOO_LARGE,
    }
)


def needs_admin_fix(problem: SourceProblem) -> bool:
    """읽기 실패의 까닭이 다시 해도 같은 것인가(설정 · 권한 · 파일을 고쳐야 풀린다). 값 없음."""
    if problem.kind in _ADMIN_FIX_KINDS:
        return True
    return problem.kind == KIND_OTHER and problem.status is not None and problem.status < 500


def unread_needs_admin(cfg: SsoConfig) -> bool:
    """못 읽은 까닭이 관리자가 고쳐야 풀리는 것인가(거절 화면 「점검 중」 의 두 갈래). 값 없음."""
    if not is_unread(cfg):
        return False
    source = runtime.access_source()
    problem = None if source is None else source.problem
    return problem is not None and needs_admin_fix(problem)


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


class _Fetched(NamedTuple):
    """읽은 한 벌. `from_file` 이면 저장소에 파일이 있었다(그러면 표지도 있어야 한다)."""

    document: ListDocument
    etag: str = ""
    seeded: bool = False
    from_file: bool = False


def _seed_mark_exists(target: S3Target, moment: int) -> bool:
    return get_object(target, names.ACCESS_SEEDED_OBJECT, moment=moment) is not None


def _fetch(cfg: SsoConfig, moment: int, *, held: bool) -> _Fetched:
    """받아 읽는다. 어떤 실패든 `S3Failure` 하나다(기동 · 콜백을 막지 못한다).

    `held` 면 파일을 받아 둔 칸이라 「없음」 도 실패다. 표지 객체가 있어도 그렇다(모듈 설명).
    """
    target = cfg.access_s3
    if target is None:
        raise S3Failure(KIND_CONFIG)
    try:
        found = get_object(target, cfg.access_object_key, moment=moment)
        if found is not None:
            return _Fetched(parse_document(found.body), found.etag, from_file=True)
        if not held and not _seed_mark_exists(target, moment):
            if cfg.access_seed_users:
                return _Fetched(_seed_document(cfg), seeded=True)
            return _Fetched(ListDocument())
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
        fetched = _fetch(cfg, moment, held=_holds_a_file(base))
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
    _publish_read(cfg, base, fetched, moment)
    document = fetched.document
    runtime.record_event(
        "access_read", users=str(len(document.entries)), revision=str(document.revision)
    )
    return None


def _publish_read(cfg: SsoConfig, base: AccessSource, fetched: _Fetched, moment: int) -> None:
    """잘 받은 한 벌을 메모리에 올린다 — 읽기(`_read_locked`)와 스스로 등록의 「이미 있음」 이 같이
    쓴다. 받은 파일이 있으면 표지도 맞추고, 답을 받지 못한 쓰기의 표시를 걷는다."""
    document = fetched.document
    mark_missing = fetched.from_file and not _left_seed_mark(cfg.access_s3, moment)
    runtime.publish_access_source(
        replace(
            base,
            access=compose_access(cfg.access, document),
            document=document,
            etag=fetched.etag,
            read_at=moment,
            attempted_at=moment,
            problem=None,
            seeded=fetched.seeded,
            seed_mark_pending=mark_missing,
            # 답을 받지 못한 쓰기는 읽어 보면 결과를 안다(들어갔으면 지금 한 벌에 있다).
            save_problem=(
                None
                if base.save_problem is not None and base.save_problem.unconfirmed
                else base.save_problem
            ),
        )
    )


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
    """지금 관리자인가 — 합성 명단의 등급으로 묻는다(환경변수 관리자 ∪ 명단 파일의 관리자 등급)."""
    return runtime.current_access(cfg).grade_of(loginid) == GRADE_ADMIN


def env_admins(cfg: SsoConfig) -> frozenset[str]:
    """환경변수 관리자(견주는 꼴) — 늘 관리자라 화면에서 일반으로 내리지 못한다."""
    return frozenset(key for key, grade in cfg.access.grades.items() if grade == GRADE_ADMIN)


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
    grades: Mapping[str, str] | None = None,
    seeded: bool = False,
    joined: ListEntry | None = None,
) -> tuple[ListDocument, SaveResult]:
    """고침을 얹은 새 한 벌과 개수. 판 번호는 바뀐 것이 있을 때만 는다. 값은 꼴을 거친 것이다.

    `grades` 는 loginid → 새 등급(이미 그 등급이면 `already`, 명단에 없으면 `absent`). `joined`
    는 스스로 등록하는 사람의 항목이다(이미 있으면 `already` — 등급 · 칸을 건드리지 않는다).
    `seeded` 면 첫 판이 파일이 되는 저장이다 — 환경변수에서 온 사람은 기록이 없으니 수로 남긴다.
    """
    stamp = _iso_text(moment)
    entries = {entry.loginid: entry for entry in document.entries}
    changes: list[ListChange] = []
    added = already = removed = absent = graded = 0
    if joined is not None:
        if joined.loginid in entries:
            already += 1
        else:
            entries[joined.loginid] = replace(joined, added_at=stamp)
            changes.append(ListChange(actor, stamp, CHANGE_SELF, joined.loginid))
            added += 1
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
    for key, grade in (grades or {}).items():
        entry = entries.get(key)
        if entry is None:
            absent += 1
            continue
        if entry.grade == grade:
            already += 1
            continue
        entries[key] = replace(entry, grade=grade)
        changes.append(ListChange(actor, stamp, f"{CHANGE_GRADE} {grade}", key))
        graded += 1
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
    return fresh, SaveResult(added, removed, already, absent, revision, graded)


def _check_grade_rules(
    cfg: SsoConfig, actor: str, *, remove: tuple[str, ...], grades: Mapping[str, str]
) -> None:
    """등급 규칙 — 정확히 둘 · 환경변수 관리자는 일반으로 못 내림 · 자기는 내리거나 빼지 못함."""
    if any(grade not in GRADES for grade in grades.values()):
        raise ValueError("grade")
    own = entry_key(actor)
    if own is not None and (own in remove or grades.get(own) == GRADE_USER):
        raise SelfChangeError(own)
    if any(grades.get(key) == GRADE_USER for key in env_admins(cfg)):
        raise EnvAdminError("env")


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


def _left_seed_mark(target: S3Target | None, moment: int, *, actor: str = "-") -> bool:
    """표지 객체가 저장소에 있게 한다. 실패는 저장 · 읽기의 실패가 아니다 — 다음 번이 다시 쓴다."""
    if target is None:
        return False
    try:
        if not _seed_mark_exists(target, moment):
            put_object(target, names.ACCESS_SEEDED_OBJECT, b'{"format": 1}', moment=moment)
    except Exception as exc:  # noqa: BLE001 — 표지는 판정 · 기동을 막지 못한다
        failure = (
            exc if isinstance(exc, S3Failure) else S3Failure(KIND_OTHER, code=type(exc).__name__)
        )
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
    grades: Mapping[str, str] | None = None,
    now: int | None = None,
    note_grades: bool = True,
) -> SaveResult:
    """개발자의 고침 하나(넣기 · 빼기 · 등급 바꾸기). 저장소에 먼저 쓰고, 쓴 뒤에만 메모리를 바꾼다.

    `note_grades` 가 거짓이면 명단 등급 칸의 바뀜을 감사에 남기지 않는다 — 등급 파일과 합친 등급으로
    부르는 쪽(`grade_store`)이 사람마다 한 줄을 남긴다.

    `NotAdminError`(권한) · `SelfChangeError`(자기 등급 내림 · 자기 빼기) · `EnvAdminError`(환경변수
    관리자 내림) · `ValueError`(모르는 등급) · `StoreUnreadError`(아직 못 읽음) ·
    `StoreConflictError`(그 사이 바뀜) · `SaveUnconfirmedError`(PUT 의 답을 받지 못함 — 들어갔는지
    모른다, `S3Failure` 의 하나) · `S3Failure`(대조 실패 · 거절된 PUT — 저장소 그대로, 파일이 상한을
    넘어도 이것)를 낸다. 어느 쪽이든 메모리는 그대로다. 바뀐 것이 없으면 쓰지 않는다.
    """
    moment = int(time.time()) if now is None else now
    actor = _require_admin(cfg, identity, moment).loginid
    removing = tuple(remove)
    grading = dict(grades or {})
    _check_grade_rules(cfg, actor, remove=removing, grades=grading)
    with _IO_LOCK:
        source = runtime.access_source()
        target = cfg.access_s3
        if source is None or source.document is None or target is None:
            raise StoreUnreadError
        fresh, result = _changed_document(
            source.document,
            actor,
            add=add,
            remove=removing,
            grades=grading,
            moment=moment,
            seeded=source.seeded,
        )
        if not result.changed:
            return result
        before = {entry.loginid for entry in source.document.entries}
        after = {entry.loginid for entry in fresh.entries}
        audit_targets = (sorted(after - before), sorted(before - after))
        try:
            if not _remote_unchanged(target, cfg.access_object_key, source, moment):
                runtime.record_event(
                    "access_save_failed",
                    level=logging.WARNING,
                    loginid=actor,
                    reason="conflict",
                )
                _audit_list_change(actor, audit_targets, source.document, result, out="fail")
                if note_grades:
                    _audit_grade_change(actor, source.document, fresh, result, out="fail")
                raise StoreConflictError
            etag = _put_noting_no_answer(
                target, cfg.access_object_key, render_document(fresh), moment
            )
        except S3Failure as failure:
            outcome = "unknown" if isinstance(failure, SaveUnconfirmedError) else "fail"
            _audit_list_change(actor, audit_targets, source.document, result, out=outcome)
            if note_grades:
                _audit_grade_change(actor, source.document, fresh, result, out=outcome)
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
        # 파일을 처음 만든 저장이거나 앞서 못 쓴 표지다. 파일을 받아 둔 칸은 그 읽기가 이미 맞췄다.
        unmarked = source.seed_mark_pending or not _holds_a_file(source)
        mark_missing = unmarked and not _left_seed_mark(target, moment, actor=actor)
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
        # 받은 판의 못 읽은 항목은 이 쓰기로 파일에서 빠진다 — 스스로 등록과 같은 칸 이름으로
        # 그 수를 싣는다(감사 기록기가 꺼진 서버에서도 남게).
        runtime.record_event(
            "access_saved",
            loginid=actor,
            added=str(result.added),
            removed=str(result.removed),
            graded=str(result.graded),
            revision=str(result.revision),
            dropped=str(source.document.unreadable),
        )
        _audit_list_change(
            actor,
            audit_targets,
            source.document,
            result,
            out="success",
            seeded=source.seeded,
        )
        if note_grades:
            _audit_grade_change(actor, source.document, fresh, result, out="success")
        return result


def _audit_list_change(
    actor: str,
    targets: tuple[list[str], list[str]],
    document: ListDocument,
    result: SaveResult,
    *,
    out: str,
    seeded: bool = False,
) -> None:
    """명단 고침의 감사 줄 — 대상 loginid 마다 한 줄(처리한 정보주체), 답을 못 받았으면 `unknown`.

    못 읽은 항목 정리 · 첫 판 심기는 수만 남긴다. 기록기가 꺼졌으면 아무것도 하지 않는다.
    """
    revisions = _audit_revisions(document.revision, result.revision, out=out)
    added, removed = targets
    for event, keys in (("user_created", added), ("user_deleted", removed)):
        for key in keys:
            audit_recorder.record(
                event,
                out=out,
                actor=actor,
                verified=True,
                tgt={"type": "loginid", "id": key},
                det=revisions,
            )
    if out != "success":
        return
    _audit_side_effects(document, result.revision, actor=actor, verified=True, seeded=seeded)


def _audit_revisions(before: int, attempted: int, *, out: str) -> dict[str, int]:
    """감사 줄의 명단 판 전 · 후. 쓰지 못한 실패(`fail` — 저장소가 거절했거나 쓰기 전에 멈춤)는
    명단이 그 판 그대로라 후 = 전이다(기록 보기 「판 n(그대로)」). 답을 못 받은 `unknown` 은
    들어갔을 수 있어 시도한 판을 적는다."""
    return {"rev_from": before, "rev_to": before if out == "fail" else attempted}


def _audit_side_effects(
    document: ListDocument, revision: int, *, actor: str, verified: bool, seeded: bool
) -> None:
    """다시 쓰기에 딸린 일의 감사 줄 — 못 읽은 항목이 빠짐 · 첫 판 심기(수만).

    관리자 저장은 그 관리자가 저지른 일로, 스스로 등록에 딸린 것은 자동 행위(`SYSTEM_SSO` —
    미검증)로 남긴다 — 일반 사용자의 누름이 관리 행위처럼 읽히지 않게.
    """
    revisions = {"rev_from": document.revision, "rev_to": revision}
    if document.unreadable:
        audit_recorder.record(
            "user_bulk_dropped",
            actor=actor,
            verified=verified,
            det={"count": document.unreadable, **revisions},
        )
    if seeded:
        audit_recorder.record(
            "user_seeded",
            actor=actor,
            verified=verified,
            det={"count": len(document.entries), **revisions},
        )


def _audit_grade_change(
    actor: str, before: ListDocument, after: ListDocument, result: SaveResult, *, out: str
) -> None:
    """등급 바꿈의 감사 줄 — 바뀐 loginid 마다 한 줄(전 → 후 등급 · 판). 바뀐 것이 없으면 없다."""
    if not result.graded:
        return
    old = {entry.loginid: entry.grade for entry in before.entries}
    for entry in after.entries:
        previous = old.get(entry.loginid)
        if previous is None or previous == entry.grade:
            continue
        audit_recorder.record(
            "user_grade_changed",
            out=out,
            actor=actor,
            verified=True,
            tgt={"type": "loginid", "id": entry.loginid},
            det={
                "grade_from": previous,
                "grade_to": entry.grade,
                **_audit_revisions(before.revision, result.revision, out=out),
            },
        )


@dataclass(frozen=True)
class RegisterResult:
    """스스로 등록 한 번의 결과 — 넣었나(아니면 이미 있었다) · 저장 뒤 판 번호(값 없음)."""

    added: bool
    revision: int


def can_register(cfg: SsoConfig) -> bool:
    """거절 화면이 「접속 권한 신청」 단추를 세울 수 있는가 — S3 명단이 켜졌고 한 번은 읽었다.

    읽어 둔 뒤의 읽기 실패는 막지 않는다 — 등록은 쓰기 직전에 다시 받으므로 그때 실패면 저장 실패
    화면(신청 글)으로 간다.
    """
    return is_on(cfg) and not is_unread(cfg) and cfg.access_s3 is not None


def _fresh_base(cfg: SsoConfig, source: AccessSource, moment: int) -> _Fetched:
    """스스로 등록이 얹을 판 — 저장소의 지금 판을 다시 받는다(합침). 파일이 사라졌으면 실패다.

    받아 둔 파일이 있었거나 표지가 있는데 없으면 `KIND_FILE_GONE` — 다시 만들지 않는다(메모리가
    마지막 사본일 수 있다). 처음(파일도 표지도 없음)이면 환경변수 첫 판 위에 얹어 그 쓰기가 파일을
    만든다.
    """
    return _fetch(cfg, moment, held=_holds_a_file(source))


def register_self(
    cfg: SsoConfig,
    loginid: str,
    *,
    name: str | None = None,
    dept: str | None = None,
    now: int | None = None,
) -> RegisterResult:
    """거절 화면 「접속 권한 신청」 — 통합인증으로 확인된 본인(`loginid` — 거절 표에서만 온다)을
    열람(명단 저장 값 `user` — 등급 파일 줄 없음)으로 명단에 넣는다. 스레드 풀에서 부른다(네트워크).

    쓰기 직전에 저장소의 지금 판을 다시 받아 그 위에 얹는다 — 그 사이 다른 쓰기(관리자의 등급
    바꿈 · 다른 사람의 등록)를 잃지 않는다. 받은 판이 메모리 판보다 오래되면(덮어쓴 직후 옛 판을
    돌려준 저장소 · 옛 사본을 쓴 다른 곳) 얹지도 올리지도 않는다(`StoreConflictError`) — 방금 뺀
    사람 · 관리자 등급이 되살아나지 않게. 이미 있으면 쓰지 않고(등급 · 이름 · 부서 그대로) 받은 판을
    메모리에 올린다. `RegisterRefusedError`(항목 꼴이 아님) · `StoreUnreadError`(S3 명단이 꺼졌거나
    아직 못 읽음) · `StoreConflictError` · `SaveUnconfirmedError` · `S3Failure`(받기 · 쓰기 실패 —
    파일 사라짐 포함)를 낸다. 실패면 메모리는 그대로이고 사건은 누계만 센다
    (`runtime.SELF_REGISTER_FAILED_EVENT`).
    """
    moment = int(time.time()) if now is None else now
    key = entry_key(loginid)
    if key is None:
        raise RegisterRefusedError("loginid")
    with _IO_LOCK:
        source = runtime.access_source()
        target = cfg.access_s3
        if not is_on(cfg) or source is None or source.document is None or target is None:
            raise StoreUnreadError
        joined = ListEntry(
            key,
            added_by=key,
            name=profile_text(name or ""),
            dept=profile_text(dept or ""),
            via=VIA_SELF,
            grade=GRADE_USER,
        )
        base: ListDocument = source.document
        try:
            fetched = _fresh_base(cfg, source, moment)
            if _older_than_memory(source, fetched):
                raise StoreConflictError
            base = fetched.document
            fresh, result = _changed_document(
                base, key, add=(), remove=(), moment=moment, joined=joined, seeded=fetched.seeded
            )
            if not result.changed:
                if fetched.from_file:
                    _publish_read(cfg, source, fetched, moment)
                return RegisterResult(added=False, revision=base.revision)
            etag = _put_noting_no_answer(
                target, cfg.access_object_key, render_document(fresh), moment
            )
        except StoreConflictError:
            _audit_self_register(key, base.revision, base.revision + 1, out="fail")
            runtime.record_event(
                runtime.SELF_REGISTER_FAILED_EVENT, level=logging.WARNING, reason="stale"
            )
            raise
        except S3Failure as failure:
            outcome = "unknown" if isinstance(failure, SaveUnconfirmedError) else "fail"
            _audit_self_register(key, base.revision, base.revision + 1, out=outcome)
            problem = problem_of(failure)
            runtime.publish_access_source(replace(source, save_problem=problem))
            runtime.record_event(
                runtime.SELF_REGISTER_FAILED_EVENT,
                level=logging.WARNING,
                reason=problem.kind,
                status=str(problem.status or "-"),
            )
            raise
        # 파일이 있으면 표지도 있게 — 이 쓰기가 파일을 처음 만들었거나 다른 곳이 만든 파일이다.
        mark_missing = not _left_seed_mark(target, moment)
        runtime.publish_access_source(
            replace(
                source,
                access=compose_access(cfg.access, fresh),
                document=fresh,
                etag=etag,
                read_at=moment if fetched.from_file else source.read_at,
                problem=None,
                saved_at=moment,
                save_problem=None,
                seeded=False,
                seed_mark_pending=mark_missing,
            )
        )
        # 받은 판의 못 읽은 항목은 이 쓰기로 파일에서 빠진다 — 그 수를 사건에도 싣는다(감사 기록기가
        # 꺼진 서버에서도 남게). 계정은 싣지 않는다.
        runtime.record_event(
            "access_self_registered",
            users=str(len(fresh.entries)),
            revision=str(result.revision),
            dropped=str(base.unreadable),
        )
        _audit_self_register(key, base.revision, result.revision, out="success")
        _audit_side_effects(
            base,
            result.revision,
            actor=audit_recorder.SYSTEM_SSO,
            verified=False,
            seeded=fetched.seeded,
        )
        return RegisterResult(added=True, revision=result.revision)


def _older_than_memory(source: AccessSource, fetched: _Fetched) -> bool:
    """다시 받은 판이 메모리에 올라 있는 판보다 오래되었나 — 파일을 받아 둔 칸만 견준다."""
    if not fetched.from_file or not _holds_a_file(source) or source.document is None:
        return False
    return fetched.document.revision < source.document.revision


def _audit_self_register(loginid: str, rev_from: int, rev_to: int, *, out: str) -> None:
    """스스로 등록의 감사 줄 — 저지른 사람이 곧 대상(인증 신원 — 거절 표). 계정은 이 줄에만.
    `rev_to` 는 시도한 판이다 — 실패 줄은 그 판 대신 그대로인 판을 적는다(`_audit_revisions`)."""
    audit_recorder.record(
        "user_self_registered",
        out=out,
        actor=loginid,
        verified=True,
        tgt={"type": "loginid", "id": loginid},
        det=_audit_revisions(rev_from, rev_to, out=out),
    )


def recent_self_registrations(document: ListDocument, *, now: int, days: int) -> tuple[int, str]:
    """`(최근 days 일 안에 스스로 등록해 지금도 명단에 있는 사람 수, 가장 새 스스로 등록 시각)`.

    시각은 고친 기록(덧붙이기만 하는 마지막 200건)에서 꺼낸다 — 사람을 빼도 줄지 않아 알림 지문이
    새 등록이 있을 때만 바뀐다. 값(loginid)은 돌려주지 않는다.
    """
    cutoff = _iso_text(now - days * 86400)
    count = sum(
        1 for entry in document.entries if entry.via == VIA_SELF and entry.added_at >= cutoff
    )
    latest = max((item.at for item in document.changes if item.what == CHANGE_SELF), default="")
    return count, latest
