# Purpose: 명단 파일 곁의 등급 파일을 읽어 메모리 한 벌로 두고 개발자의 등급 바꿈을 두 객체 차례로
# 쓴다.

"""등급 파일 — 열람 · 실무자 · 관리자를 명단 파일과 따로 둔다(2026-11-18 접속 등급 결정 12 ~ 15).

**자리 · 꼴.** 명단 파일과 같은 버킷, 명단 객체 키의 디렉터리 + `grades.json`(기본
`access/grades.json`). 「있었다」 표지는 같은 디렉터리의 `grades_seen.json` 이고 첫 등급 파일 쓰기가
남긴다(명단의 `access/seeded.json` 선례). 로컬 파일 자리는 두지 않는다 — pod 디스크는 재시작에
사라지고 정본이 둘이 된다. 꼴은 명단과 같은 작은 JSON(들여쓰기 1) — 형식 판 · 판 번호 · 줄(loginid ·
등급 · 그 줄을 적을 때 명단 항목의 등록 시각 · 적은 사람 · 때) · 고친 기록 마지막 200건.

**적는 값은 `editor` · `manager` 둘이다.** 열람은 줄이 없고(열람으로 내리면 줄을 지운다) 개발자는
명단의 `admin` 이 정한다. 모르는 값의 줄은 원문을 지키고 판정만 열람이다. 쓸 때 명단에 없거나 등록
시각이 다른 줄은 뺀다 — 빠졌다 다시 든 사람은 등록 시각이 달라 옛 줄을 이어받지 않는다.

**판정**(`grade_of`) — 개발자(`access_store.is_admin` — 환경변수 ∪ 명단 `admin`)면 개발자, 아니면
명단 항목의 등록 시각과 등급 파일 줄의 등록 시각이 같고 값이 `editor` · `manager` 면 그 값, 그 밖(줄
없음 · 시각 다름 · 모르는 값 · 아직 못 읽음 · S3 명단 꺼짐)은 열람이다. 못 읽었다고 넓어지지 않는다.

**읽기.** 기동 때 한 번(`read_at_start` — `auth/server.start_sso` 가 명단 읽기 바로 뒤). 한 번 잘
읽은
뒤에는 S3 가 막혀도 파일이 사라져도 메모리로 잇는다. 못 읽은 동안은 로그인할 때마다(1분에 한
번까지 — `retry_unread`, 콜백이 스레드 풀에서 부른다)와 개발자의 「다시 읽기」(`reread` — 명단과
함께)로 다시 읽는다. 첫 부팅에 적어 두는 일은 없다 — 없음(404) + 표지 없음은 「아직 등급이 없음」
이라
모두 열람이고 정상이다. 없음 + 표지 · 깨짐 · 모르는 형식 판 · 읽기 실패는 「못 읽음」 이고 개발자
상태 알림 `AD-25` 가 선다(`components/sso_status`).

**쓰기 — 두 객체는 원자적이지 않다.** 실패는 늘 「앞 상태 또는 더 좁은 쪽」 이다.

- 열람 · 실무자 · 관리자 사이 → 등급 파일만.
- → 개발자: 명단만(`user` → `admin`). 등급 줄은 두되 개발자인 동안 보지 않는다.
- 개발자 → 아래: 등급 파일 먼저(목표 줄, 그 사람의 지금 등록 시각), 그다음 명단(`admin` → `user`).
  둘째가 실패하면 그대로 개발자(앞 상태)다.
- 빼기: 명단 먼저, 그다음 등급 줄 지움(둘째 실패는 무해 — 다시 들면 시각이 달라 버려지고, 「명단에
  넣기」 는 남은 줄을 명단 쓰기 앞에서 먼저 지운다 — 같은 초로 다시 매겨진 시각에 맞지 않게).
- 넣기(넣는 창에서 고른 등급): 명단 먼저(개발자면 `admin` 으로 바로 — 한 번의 쓰기), 그다음 실무자 ·
  관리자면 등급 파일. 둘째 실패면 열람(좁은 쪽)으로 읽히고 알림.
- 스스로 등록은 `access_store.register_self` 그대로다(줄 없음 → 열람).

여럿 골라 한 번 바꾸면 많아야 두 번 쓴다(등급 파일 한 번 + 명단 한 번). 자기 자신 · 환경변수
개발자를
개발자 아래로 내리는 것이 섞이면 통째 거절이다(`SelfChangeError` · `EnvAdminError`). 쓰는 함수는
화면과 별개로 신원 · 개발자를 다시 본다(명단 쓰기와 같은 두 번째 벽 — `access_store`). 조건부 쓰기는
명단과 같은 꼴(HEAD 의 ETag, 없으면 판 번호 대조 · `If-Match` 안 씀)이고, 입출력은 명단과 같은
프로세스 잠금(`access_store._IO_LOCK`)을 함께 쓴다(replica 1 전제).

**되돌림.** 앞 판 코드는 이 파일을 모르고 건드리지 않는다. 되돌린 동안은 등급이 아예 없어 개발자
말고 모두 옛 「일반」 이다. 다시 앞으로 오면 등록 시각이 같은 사람은 옛 줄로 돌아온다.

**감사.** 등급 바꿈은 사람마다 `user_grade_changed` 한 줄(합친 등급의 전 · 후 — 새 값), 읽기 · 쓰기
실패는 `sys_grade_read_fail` · `sys_grade_save_fail`. 사람 값은 감사 줄의 대상에만 싣는다.
"""

from __future__ import annotations

import json
import logging
import posixpath
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.auth import access_store, grades, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    GradeChange,
    GradeDocument,
    GradeLine,
    GradeSource,
    ListDocument,
    SourceProblem,
    entry_key,
)
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity
from capa_simulation.io import s3_small
from capa_simulation.io.s3_small import KIND_OTHER, S3Failure, S3Target

OBJECT_FORMAT: Final = 1
MAX_CHANGES: Final = 200
RETRY_SECONDS: Final = 60
GRADES_FILE: Final = "grades.json"
MARK_FILE: Final = "grades_seen.json"
CHANGE_CLEAR: Final = "clear"

_LOGGER = logging.getLogger(__name__)


class GradeUnreadError(RuntimeError):
    """등급 파일을 아직 한 번도 읽지 못해 무엇을 덮을지 모른다 — 쓰지 않는다."""


@dataclass(frozen=True)
class ChangeResult:
    """등급 바꿈 · 넣기 · 빼기 한 번의 결과 — 수만(값 없음).

    `graded` 는 등급이 바뀐 사람 수, `already` 는 이미 그 등급, `absent` 는 명단에 없음.
    `grade_revision` · `list_revision` 은 쓴 뒤 판 번호(쓰지 않았으면 그대로). `second_failed` 는
    둘째
    쓰기(넣기 · 빼기의 등급 파일, 개발자 → 아래의 명단)가 실패했다는 표지와 그 까닭이다 — 첫째는
    남았다.
    """

    graded: int = 0
    already: int = 0
    absent: int = 0
    added: int = 0
    removed: int = 0
    grade_revision: int = 0
    list_revision: int = 0
    second_failed: SourceProblem | None = None

    @property
    def changed(self) -> bool:
        return bool(self.graded or self.added or self.removed)


# ------------------------------------------------------------------ 자리 · 꼴
def _sibling(cfg: SsoConfig, name: str) -> str:
    folder = posixpath.dirname(cfg.access_object_key)
    return f"{folder}/{name}" if folder else name


def object_key(cfg: SsoConfig) -> str:
    """등급 파일 객체 키 — 명단 객체 키의 디렉터리 + `grades.json`."""
    return _sibling(cfg, GRADES_FILE)


def mark_key(cfg: SsoConfig) -> str:
    """「있었다」 표지 객체 키 — 같은 디렉터리의 `grades_seen.json`."""
    return _sibling(cfg, MARK_FILE)


def _text(raw: Mapping[str, Any], name: str) -> str:
    value = raw.get(name)
    return value if isinstance(value, str) else ""


def parse_document(body: bytes) -> GradeDocument:
    """파일 바이트 → 한 벌. 깨졌거나 형식 판을 모르면 `S3Failure`(값을 담지 않는다)."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        payload = None
    if not isinstance(payload, dict):
        raise S3Failure(access_store.KIND_CORRUPT)
    if payload.get("format") != OBJECT_FORMAT:
        raise S3Failure(access_store.KIND_UNKNOWN_FORMAT)
    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise S3Failure(access_store.KIND_CORRUPT)
    raw_lines = payload.get("grades")
    if not isinstance(raw_lines, list):
        raise S3Failure(access_store.KIND_CORRUPT)
    lines: dict[str, GradeLine] = {}
    unreadable = 0
    for item in raw_lines:
        loginid = item.get("loginid") if isinstance(item, dict) else None
        key = entry_key(loginid) if isinstance(loginid, str) else None
        grade = item.get("grade") if isinstance(item, dict) else None
        if key is None or not isinstance(item, dict) or not isinstance(grade, str) or not grade:
            unreadable += 1
            continue
        lines[key] = GradeLine(
            key,
            grade.strip()[:40],
            _text(item, "added_at"),
            _text(item, "by"),
            _text(item, "at"),
        )
    raw_changes = payload.get("changes")
    changes = tuple(
        GradeChange(
            _text(item, "by"), _text(item, "at"), _text(item, "what"), _text(item, "loginid")
        )
        for item in (raw_changes if isinstance(raw_changes, list) else [])[-MAX_CHANGES:]
        if isinstance(item, dict)
    )
    return GradeDocument(
        revision=revision, lines=tuple(lines.values()), changes=changes, unreadable=unreadable
    )


def render_document(document: GradeDocument) -> bytes:
    """한 벌 → 파일 바이트. 사람이 저장소에서 열어 볼 수 있게 들여 쓴다(명단과 같은 꼴)."""
    payload = {
        "format": OBJECT_FORMAT,
        "revision": document.revision,
        "grades": [
            {
                "loginid": line.loginid,
                "grade": line.grade,
                "added_at": line.added_at,
                "by": line.by,
                "at": line.at,
            }
            for line in document.lines
        ],
        "changes": [
            {"by": item.by, "at": item.at, "what": item.what, "loginid": item.loginid}
            for item in document.changes[-MAX_CHANGES:]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")


# ------------------------------------------------------------------ 판정
def _list_document() -> ListDocument | None:
    source = runtime.access_source()
    return None if source is None else source.document


def is_unread(cfg: SsoConfig) -> bool:
    """S3 명단 서버인데 등급 파일을 아직 한 번도 읽지 못했는가."""
    if not access_store.is_on(cfg):
        return False
    source = runtime.grade_source()
    return source is None or source.document is None


def read_problem(cfg: SsoConfig) -> SourceProblem | None:
    """등급 파일을 읽지 못한 까닭(못 읽은 동안 · 한 번 읽은 뒤 다시 읽기 실패). 없으면 `None`.

    S3 명단이 꺼진 서버 · 아직 읽으러 가지 않은 서버는 `None` 이다(등급 파일이 없는 서버).
    """
    if not access_store.is_on(cfg):
        return None
    source = runtime.grade_source()
    return None if source is None else source.problem


def stored_grade(cfg: SsoConfig, loginid: str) -> str:
    """등급 파일이 정하는 등급(개발자 판정 없이) — 실무자 · 관리자, 그 밖은 열람."""
    if not access_store.is_on(cfg):
        return grades.VIEWER
    source = runtime.grade_source()
    document = None if source is None else source.document
    listed = _list_document()
    key = entry_key(loginid)
    if document is None or listed is None or key is None:
        return grades.VIEWER
    entry = next((item for item in listed.entries if item.loginid == key), None)
    line = document.line_of(key)
    if entry is None or line is None or line.added_at != entry.added_at:
        return grades.VIEWER
    return line.grade if line.grade in grades.STORED_GRADES else grades.VIEWER


def grade_of(cfg: SsoConfig, loginid: str) -> str:
    """이 사람의 유효 등급 — 개발자 · 등급 파일 줄 · 열람(모듈 설명 「판정」)."""
    if access_store.is_admin(cfg, loginid):
        return grades.DEVELOPER
    return stored_grade(cfg, loginid)


# ------------------------------------------------------------------ 읽기
def _audit_failure(event: str, problem: SourceProblem, *, actor: str | None = None) -> None:
    audit_recorder.record(
        event,
        out="fail",
        actor=actor or audit_recorder.SYSTEM_SSO,
        verified=actor is not None,
        why=problem.kind,
        det={"reason": problem.kind, "status": problem.status},
    )


def _mark_exists(target: S3Target, cfg: SsoConfig, moment: int) -> bool:
    return s3_small.get_object(target, mark_key(cfg), moment=moment) is not None


def _leave_mark(target: S3Target, cfg: SsoConfig, moment: int) -> bool:
    """표지 객체가 저장소에 있게 한다. 실패는 읽기 · 저장의 실패가 아니다 — 다음 번이 다시 쓴다."""
    try:
        if not _mark_exists(target, cfg, moment):
            s3_small.put_object(target, mark_key(cfg), b'{"format": 1}', moment=moment)
    except Exception:  # noqa: BLE001 — 표지는 판정을 막지 못한다
        _LOGGER.warning("등급 파일 표지를 남기지 못했습니다.")
        return False
    return True


def _read_locked(cfg: SsoConfig, moment: int) -> SourceProblem | None:
    """입출력 잠금 안에서 받아 한 벌을 바꾼다. 실패면 전의 한 벌을 그대로 두고 까닭만 적는다."""
    base = runtime.grade_source() or GradeSource()
    target = cfg.access_s3
    try:
        if target is None:
            raise S3Failure(access_store.KIND_CONFIG)
        found = s3_small.get_object(target, object_key(cfg), moment=moment)
        if found is not None:
            document = parse_document(found.body)
            seen = base.seen or _leave_mark(target, cfg, moment)
            runtime.publish_grade_source(
                replace(
                    base,
                    document=document,
                    etag=found.etag,
                    read_at=moment,
                    attempted_at=moment,
                    problem=None,
                    seen=seen,
                )
            )
            return None
        held = base.document is not None and bool(base.etag or base.document.revision)
        if not held and not _mark_exists(target, cfg, moment):
            # 아직 등급이 없다 — 모두 열람이고 정상이다(첫 부팅에 적어 두지 않는다).
            runtime.publish_grade_source(
                replace(
                    base,
                    document=GradeDocument(),
                    etag="",
                    read_at=moment,
                    attempted_at=moment,
                    problem=None,
                )
            )
            return None
        failure = S3Failure(access_store.KIND_FILE_GONE, 404, "NoSuchKey")
    except S3Failure as exc:
        failure = exc
    except Exception as exc:  # noqa: BLE001 — 예상 못 한 실패도 「못 읽음」 이다
        failure = S3Failure(KIND_OTHER, code=type(exc).__name__)
    problem = access_store.problem_of(failure)
    runtime.publish_grade_source(replace(base, attempted_at=moment, problem=problem))
    runtime.record_event(
        "grade_read",
        level=logging.WARNING,
        reason=problem.kind,
        status=str(problem.status or "-"),
    )
    _audit_failure("sys_grade_read_fail", problem)
    return problem


def read_at_start(cfg: SsoConfig, *, now: int | None = None) -> None:
    """진입 파일이 기동 때 한 번 부른다(명단 읽기 바로 뒤). S3 명단이 꺼진 서버는 아무것도
    하지 않는다."""
    if not access_store.is_on(cfg):
        return
    with access_store._IO_LOCK:
        _read_locked(cfg, int(time.time()) if now is None else now)


def retry_unread(cfg: SsoConfig, *, now: int | None = None) -> None:
    """못 읽은 동안 로그인마다 다시 읽어 본다 — 60초에 한 번까지. 스레드 풀에서 부른다."""
    moment = int(time.time()) if now is None else now
    if not is_unread(cfg):
        return
    if not runtime.claim_grade_retry(moment, RETRY_SECONDS):
        return
    if not access_store._IO_LOCK.acquire(blocking=False):
        return
    try:
        _read_locked(cfg, moment)
    finally:
        access_store._IO_LOCK.release()


def reread(
    cfg: SsoConfig, identity: Identity | None, *, now: int | None = None
) -> tuple[SourceProblem | None, SourceProblem | None]:
    """Admin 「다시 읽기」 — 명단과 등급 파일을 함께. 개발자만. (명단 까닭, 등급 파일 까닭)."""
    moment = int(time.time()) if now is None else now
    listed = access_store.reread(cfg, identity, now=moment)
    if not access_store.is_on(cfg):
        return listed, None
    with access_store._IO_LOCK:
        graded = _read_locked(cfg, moment)
    return listed, graded


# ------------------------------------------------------------------ 쓰기
def _pruned(lines: Iterable[GradeLine], listed: ListDocument) -> tuple[GradeLine, ...]:
    """명단에 없거나 등록 시각이 다른 줄은 뺀다(어차피 버려지는 줄 — 되살아남을 막는 정리)."""
    stamps = {entry.loginid: entry.added_at for entry in listed.entries}
    return tuple(
        sorted(
            (line for line in lines if stamps.get(line.loginid) == line.added_at),
            key=lambda line: line.loginid,
        )
    )


def _remote_unchanged(target: S3Target, key: str, source: GradeSource, moment: int) -> bool:
    """저장소의 등급 파일이 받을 때 그대로인가 — 명단과 같은 꼴(ETag, 없으면 판 번호)."""
    assert source.document is not None
    remote_etag = s3_small.head_object(target, key, moment=moment)
    was_missing = source.document.revision == 0 and not source.etag
    if remote_etag is None or was_missing:
        return remote_etag is None and was_missing
    if remote_etag and source.etag:
        return remote_etag == source.etag
    found = s3_small.get_object(target, key, moment=moment)
    return found is not None and parse_document(found.body).revision == source.document.revision


def _write_lines(
    cfg: SsoConfig, actor: str, wanted: Mapping[str, str | None], moment: int
) -> tuple[GradeDocument, GradeDocument]:
    """등급 줄을 바꿔 한 번 쓴다 — `wanted` 는 loginid → 목표 값(`editor` · `manager`, `None` 은 줄
    지움). (앞 한 벌, 쓴 한 벌). 바뀐 것이 없으면 쓰지 않고 같은 두 벌을 돌려준다.

    `GradeUnreadError`(등급 파일 · 명단을 아직 못 읽음) · `access_store.StoreConflictError`(그 사이
    바뀜) · `S3Failure`(받기 · 쓰기 실패 — 답을 받지 못한 PUT 은 `SaveUnconfirmedError`)를 낸다.
    """
    with access_store._IO_LOCK:
        source = runtime.grade_source()
        listed = _list_document()
        target = cfg.access_s3
        if source is None or source.document is None or listed is None or target is None:
            raise GradeUnreadError
        before = source.document
        stamps = {entry.loginid: entry.added_at for entry in listed.entries}
        stamp = access_store._iso_text(moment)
        lines = {line.loginid: line for line in before.lines}
        changes: list[GradeChange] = []
        for key, grade in wanted.items():
            current = lines.get(key)
            if grade is None:
                if current is not None:
                    del lines[key]
                    changes.append(GradeChange(actor, stamp, CHANGE_CLEAR, key))
                continue
            if key not in stamps:
                continue
            if current is not None and current.grade == grade and current.added_at == stamps[key]:
                continue
            lines[key] = GradeLine(key, grade, stamps[key], actor, stamp)
            changes.append(GradeChange(actor, stamp, f"grade {grade}", key))
        kept = _pruned(lines.values(), listed)
        if not changes and kept == _pruned(before.lines, listed):
            return before, before
        fresh = GradeDocument(
            revision=before.revision + 1,
            lines=kept,
            changes=(*before.changes, *changes)[-MAX_CHANGES:],
        )
        key = object_key(cfg)
        try:
            if not _remote_unchanged(target, key, source, moment):
                raise access_store.StoreConflictError
            etag = access_store._put_noting_no_answer(target, key, render_document(fresh), moment)
        except access_store.StoreConflictError:
            problem = SourceProblem("conflict")
            runtime.publish_grade_source(replace(source, save_problem=problem))
            _audit_failure("sys_grade_save_fail", problem, actor=actor)
            raise
        except S3Failure as failure:
            problem = access_store.problem_of(failure)
            runtime.publish_grade_source(replace(source, save_problem=problem))
            _audit_failure("sys_grade_save_fail", problem, actor=actor)
            raise
        seen = source.seen or _leave_mark(target, cfg, moment)
        runtime.publish_grade_source(
            replace(
                source,
                document=fresh,
                etag=etag,
                problem=None,
                saved_at=moment,
                save_problem=None,
                seen=seen,
            )
        )
        runtime.record_event(
            "grade_saved",
            loginid=actor,
            changed=str(len(changes)),
            revision=str(fresh.revision),
        )
        return before, fresh


def _require_developer(cfg: SsoConfig, identity: Identity | None, moment: int) -> str:
    """쓰는 자리의 두 번째 벽 — 신원이 지금도 유효하고 개발자인가(명단 쓰기와 같은 벽)."""
    return access_store._require_admin(cfg, identity, moment).loginid


def _check_rules(cfg: SsoConfig, actor: str, targets: Mapping[str, str]) -> None:
    """모르는 등급 · 자기 자신 · 환경변수 개발자를 개발자 아래로 내림 — 통째 거절."""
    if any(grade not in grades.GRADES for grade in targets.values()):
        raise ValueError("grade")
    own = entry_key(actor)
    if own is not None and own in targets and targets[own] != grades.DEVELOPER:
        raise access_store.SelfChangeError(own)
    if any(
        targets.get(key) not in (None, grades.DEVELOPER) for key in access_store.env_admins(cfg)
    ):
        raise access_store.EnvAdminError("env")


def _audit_grades(
    actor: str,
    before: Mapping[str, str],
    after: Mapping[str, str],
    *,
    out: str,
    revisions: tuple[int, int],
) -> None:
    """등급 바꿈의 감사 줄 — 사람마다 한 줄(합친 등급의 전 · 후 — 새 값). 판 전 · 후는 명단을 쓴
    바꿈이면 명단 판, 등급 파일만 쓴 바꿈이면 등급 파일 판이다."""
    for key, grade in after.items():
        previous = before.get(key, grades.VIEWER)
        if previous == grade:
            continue
        audit_recorder.record(
            "user_grade_changed",
            out=out,
            actor=actor,
            verified=True,
            tgt={"type": "loginid", "id": key},
            det={
                "grade_from": previous,
                "grade_to": grade,
                "rev_from": revisions[0],
                "rev_to": revisions[1] if out != "fail" else revisions[0],
            },
        )


def _held_keys() -> set[str]:
    """메모리 등급 파일에 줄이 있는 loginid(명단에 있든 없든 — 못 읽었으면 빈 셋)."""
    source = runtime.grade_source()
    if source is None or source.document is None:
        return set()
    return {line.loginid for line in source.document.lines}


def _second_problem(failure: Exception) -> SourceProblem:
    """둘째 쓰기 실패의 까닭 — 저장소 실패 · 그 사이 바뀜 · 아직 못 읽음."""
    if isinstance(failure, S3Failure):
        return access_store.problem_of(failure)
    if isinstance(failure, GradeUnreadError):
        return SourceProblem("unread")
    return SourceProblem("conflict")


def _merged(cfg: SsoConfig, keys: Iterable[str]) -> dict[str, str]:
    return {key: grade_of(cfg, key) for key in keys}


def change_grades(
    cfg: SsoConfig,
    identity: Identity | None,
    targets: Mapping[str, str],
    *,
    now: int | None = None,
) -> ChangeResult:
    """여럿의 등급을 한 번에 바꾼다 — 많아야 두 번 쓴다(모듈 설명 「쓰기」).

    `targets` 는 loginid(견주는 꼴) → 새 등급(`grades.GRADES`). `access_store.NotAdminError` ·
    `SelfChangeError` · `EnvAdminError` · `ValueError` · `GradeUnreadError` ·
    `access_store.StoreUnreadError` · `StoreConflictError` · `S3Failure` 는 첫째 쓰기 전 · 첫째
    쓰기의
    실패다(아무것도 바뀌지 않음). 둘째 쓰기(개발자 → 아래의 명단)의 실패는 예외가 아니라
    `second_failed` 로 돌려준다 — 그 사람들은 그대로 개발자다.
    """
    moment = int(time.time()) if now is None else now
    actor = _require_developer(cfg, identity, moment)
    _check_rules(cfg, actor, targets)
    listed = _list_document()
    if listed is None:
        raise access_store.StoreUnreadError
    entries = {entry.loginid: entry for entry in listed.entries}
    absent = sum(1 for key in targets if key not in entries)
    present = {key: grade for key, grade in targets.items() if key in entries}
    before = _merged(cfg, present)
    already = sum(1 for key, grade in present.items() if before[key] == grade)
    wanted_lines: dict[str, str | None] = {}
    list_grades: dict[str, str] = {}
    for key, grade in present.items():
        if before[key] == grade:
            continue
        is_listed_admin = entries[key].grade == GRADE_ADMIN
        if grade == grades.DEVELOPER:
            list_grades[key] = GRADE_ADMIN
            continue
        wanted_lines[key] = grade if grade in grades.STORED_GRADES else None
        if is_listed_admin:
            list_grades[key] = GRADE_USER
    grade_before = runtime.grade_source()
    grade_revision = (
        0
        if grade_before is None or grade_before.document is None
        else grade_before.document.revision
    )
    grade_revision_before = grade_revision
    if wanted_lines:
        try:
            _, written = _write_lines(cfg, actor, wanted_lines, moment)
        except S3Failure:
            _audit_grades(
                actor,
                before,
                {key: present[key] for key in wanted_lines},
                out="fail",
                revisions=(grade_revision, grade_revision),
            )
            raise
        grade_revision = written.revision
    list_revision = listed.revision
    second_failed: SourceProblem | None = None
    if list_grades:
        try:
            saved = access_store.save_changes(
                cfg, identity, grades=list_grades, now=moment, note_grades=False
            )
            list_revision = saved.revision
        except (access_store.StoreConflictError, S3Failure) as failure:
            if not wanted_lines:
                _audit_grades(
                    actor,
                    before,
                    {key: present[key] for key in list_grades},
                    out="fail",
                    revisions=(listed.revision, listed.revision),
                )
                raise
            second_failed = _second_problem(failure)
    after = _merged(cfg, present)
    _audit_grades(
        actor,
        before,
        after,
        out="success",
        revisions=(
            (listed.revision, list_revision)
            if list_grades
            else (grade_revision_before, grade_revision)
        ),
    )
    graded = sum(1 for key in present if after[key] != before[key])
    return ChangeResult(
        graded=graded,
        already=already,
        absent=absent,
        grade_revision=grade_revision,
        list_revision=list_revision,
        second_failed=second_failed,
    )


def add_people(
    cfg: SsoConfig,
    identity: Identity | None,
    keys: Iterable[str],
    grade: str,
    *,
    now: int | None = None,
) -> ChangeResult:
    """개발자가 「명단에 넣기」 로 넣는다 — 넣는 창에서 고른 등급(모듈 설명 「쓰기」).

    명단 쓰기의 실패는 `access_store.save_changes` 의 예외 그대로다(아무것도 바뀌지 않음). 둘째
    쓰기(실무자 · 관리자의 등급 파일)의 실패는 `second_failed` 로 돌려준다 — 넣은 사람은 열람으로
    읽힌다.
    이미 명단에 있던 사람의 등급은 건드리지 않는다.

    새로 드는 사람에게 남은 등급 줄(빼기의 둘째 쓰기 실패 · 앞 ZIP 이 뺌)이 있으면 명단 쓰기
    **앞에서** 먼저 지운다 — 등록 시각은 초 단위 글이라 같은 초로 다시 매겨지면 옛 줄이 맞을 수
    있다. 그 지움이 실패하면 예외 그대로이고 아무것도 넣지 않는다(앞 상태).
    """
    if grade not in grades.GRADES:
        raise ValueError("grade")
    moment = int(time.time()) if now is None else now
    actor = _require_developer(cfg, identity, moment)
    adding = tuple(dict.fromkeys(keys))
    listed_before = _list_document()
    existing = set() if listed_before is None else {e.loginid for e in listed_before.entries}
    fresh = [key for key in adding if key not in existing]
    leftover = [key for key in fresh if key in _held_keys()]
    if leftover:
        _write_lines(cfg, actor, dict.fromkeys(leftover), moment)
    saved = access_store.save_changes(
        cfg,
        identity,
        add=adding,
        grades=dict.fromkeys(fresh, GRADE_ADMIN) if grade == grades.DEVELOPER else None,
        now=moment,
        note_grades=False,
    )
    second_failed: SourceProblem | None = None
    grade_revision = 0
    if grade in grades.STORED_GRADES and fresh and saved.added:
        try:
            _, written = _write_lines(cfg, actor, dict.fromkeys(fresh, grade), moment)
            grade_revision = written.revision
        except (GradeUnreadError, access_store.StoreConflictError, S3Failure) as failure:
            second_failed = _second_problem(failure)
    if saved.added:
        _audit_grades(
            actor,
            dict.fromkeys(fresh, grades.VIEWER),
            _merged(cfg, fresh),
            out="success",
            revisions=(saved.revision - 1, saved.revision),
        )
    return ChangeResult(
        graded=sum(1 for key in fresh if grade_of(cfg, key) != grades.VIEWER),
        already=saved.already,
        added=saved.added,
        grade_revision=grade_revision,
        list_revision=saved.revision,
        second_failed=second_failed,
    )


def remove_people(
    cfg: SsoConfig,
    identity: Identity | None,
    keys: Iterable[str],
    *,
    now: int | None = None,
) -> ChangeResult:
    """명단에서 뺀다 — 명단 먼저, 그다음 등급 줄 지움(둘째 실패는 무해 — 모듈 설명)."""
    moment = int(time.time()) if now is None else now
    actor = _require_developer(cfg, identity, moment)
    removing = tuple(dict.fromkeys(keys))
    saved = access_store.save_changes(cfg, identity, remove=removing, now=moment)
    second_failed: SourceProblem | None = None
    held = _held_keys()
    stale = {key: None for key in removing if key in held}
    if saved.removed and stale:
        try:
            _write_lines(cfg, actor, stale, moment)
        except (GradeUnreadError, access_store.StoreConflictError, S3Failure) as failure:
            second_failed = _second_problem(failure)
    return ChangeResult(
        removed=saved.removed,
        absent=saved.absent,
        list_revision=saved.revision,
        second_failed=second_failed,
    )


def grade_counts(cfg: SsoConfig) -> dict[str, int]:
    """명단 사람의 등급별 수(개발자 · 관리자 · 실무자 · 열람) — 값 없이 수만(캡션 · 런북 확인)."""
    listed = _list_document()
    counts = dict.fromkeys(grades.GRADES, 0)
    if listed is None:
        return counts
    for entry in listed.entries:
        counts[grade_of(cfg, entry.loginid)] += 1
    return counts
