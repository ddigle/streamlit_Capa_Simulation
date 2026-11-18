# Purpose: Admin Area 「접속 명단」 — 개발자에게만 S3 명단 · 등급 파일을 편집 표로 보이고 저장 ·
# 다시 읽기와 「이 등급으로 보기」 를 그린다.

"""Admin 「접속 명단」.

자리는 통합인증이 켜지고 S3 명단이 켜진 서버의 **개발자 회차에만** 있다. 그 밖(꺼짐 · 사내 PC · 개발
· S3 명단 꺼짐 · 개발자가 아닌 사람)에는 Streamlit 호출을 하나도 하지 않는다 — 요소 순번이 그대로다.

**편집 표**(2026-11-18 접속 등급 구현 확인 보드 「고칠 것」 — 사용자 답 「추가 · 지우기까지 표
안에서」). 기준 정보 · 생산 계획과 같은 범용 편집 그리드의 줄 규칙 표(`components/access_list_grid`)
다 — 칸 계정 · 이름 · 부서 · 등록일 · 등록 길(스스로 등록 · 개발자가 넣음 — 아래 「최근 등록 ·
빼기」 의 「한 일」 과 같은 낱말 — E2E 보드 s-C-02) · 등급(고르기 칸 — 열람 · 실무자 · 관리자 ·
개발자). 여러 줄을 골라 채우기 · 붙여넣기로 등급을 한 번에 바꾸고, 빈 새 줄에 계정(+ 이름 · 부서) ·
등급을 적어 넣고, 「줄 지우기」 로 뺀다. 나 자신과 환경변수로 정한 개발자의 등급 칸 · 줄 지우기는
잠긴다(까닭 풍선). 「저장」 한 번이 바뀐 것 전부를 지금 저장 함수로 쓴다 —
빼기(`grade_store.remove_people`) → 등급 바꿈(`change_grades`) → 넣기(`add_people` — 등급마다 한
번)의 좁히는 차례이고, 저장 판(`services/access_list_plan`)의 문제(빨간 칸 · 계정이 빔 · 꼴이 아님
· 머리 글 · 겹침 · 등급이 빔)가 하나라도 있으면 아무것도 쓰지 않는다. 등록 시각 · 다시 든 사람 규칙
· 감사 줄은 저장 함수 그대로다.

쓰기(저장 · 다시 읽기)는 그 회차에 쿠키에서 다시 검증한 신원(`sso_identity.verified_identity`)을
넘기고, 저장소 쪽(`auth/grade_store` → `auth/access_store`)이 신원 · 개발자를 쓰는 순간 다시 본다 —
이 화면이 개발자에게만 그려진다는 것을 믿지 않는다(보인 회차와 누른 회차의 권한이 달라질 수 있고
위젯 콜백은 본문보다 먼저 돈다). 등급은 넷이고 명단 파일(`user` · `admin` — `admin` = 개발자)과 그
곁의 등급 파일(실무자 · 관리자)을 합쳐 읽는다(2026-11-18 접속 등급).

알림에는 개수와 까닭만 싣는다 — loginid 는 실제 사람을 가리켜 Alarm 복사 · 리뷰로 나가면 안
된다(런북 3-3). 저장 실패 · 그 사이 바뀜은 메모리를 바꾸지 않는다. 답을 받지 못한 PUT 은 저장소에
들어갔을 수 있어 「그대로」 라고 단언하지 않고 다시 읽기로 보낸다. 저장 · 다시 읽기의 실패와 거부는
그 자리에 고칠 입력이 없어 알림창 · Alarm 에만 낸다(설계 규칙 UI-NTF-03). 저장 판의 문제는 표에서
고칠 일이라 작업 줄 바로 아래 곁 한 줄이다. 앞 쓰기가 남고 뒤 쓰기가 막히면 남은 수와 막힌 까닭을
함께 알리고 저장한 사람의 초안만 걷는다.

표 위 작업 줄은 한 줄이다(저장 · 편집 취소 · 다시 읽기, 끝에 버전 · 명단 · 개발자 수 — 넓은 창에서는
표 도구 막대가 같은 줄 오른쪽에 선다, `edit_grid.one_line_style`). 접속 명단 알림 `AD-08` · `AD-09`
· `AD-19` · 등급 파일 `AD-25` 의 「그 화면으로」 가 이 펼침을 연다(`open_access_list` — 알림 칸의
받는 쪽 `ACCESS_LIST_TARGET_KIND`). 표 아래 접힌 「최근 등록 · 빼기(30일)」 은 파일의 고친 기록에서
꺼낸 읽기 전용 표다(시각 · 계정 · 한 일 — 등급 바꿈은 감사 기록이 맡는다).

「이 등급으로 보기」(`render_grade_preview`)는 운영 + 켜짐의 실제 개발자에게만 Admin Area 안쪽 탭 줄
오른쪽 끝 팝오버로 선다(설계 규칙 UI-LAY-13 — 탭 위 줄을 늘리지 않는다). 그 창의 세션 칸에만 적고
화면만 바뀐다 — 저장은 실제 등급이고, 창을 닫거나 앱 정보 카드의 「끝내기」 로 끝난다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.auth import access_store, grade_store, grades, runtime
from capa_simulation.auth.access import ListDocument, SourceProblem, entry_key
from capa_simulation.auth.config import SsoConfig, SsoMode
from capa_simulation.auth.identity import Identity
from capa_simulation.components import access_list_grid, edit_grid, sso_identity
from capa_simulation.components.access_list_grid import VIA_ADMIN_LABEL, VIA_SELF_LABEL
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.module_status import TAB_ROW_RESERVE_REM
from capa_simulation.components.sso_status import NEW_REGISTRATION_DAYS, access_problem_text
from capa_simulation.components.table_toolbar import toolbar_clearance
from capa_simulation.io.s3_small import S3Failure
from capa_simulation.korea_time import kst_clock
from capa_simulation.services.access_list_plan import AccessPlan
from capa_simulation.sidebar_status import remembered_box_key, remembered_expander

EXPANDER_KEY: Final = "admin_area_access_list"
EXPANDER_LABEL: Final = "접속 명단"
# 알림의 「그 화면으로」 가 Admin Area 에 닿은 뒤 이 펼침을 여는 받는 쪽의
# 이름(`alerts.GotoTarget`).
ACCESS_LIST_TARGET_KIND: Final = "access_list"
ACCESS_LIST_FLASH_KEY: Final = "admin_area_access_list_flash"
# 표 위 칸의 key — 작업 줄 칸 안의 단추 줄이 `ACTION_ROW`, 그 바로 뒤 형제 칸이 그리드 칸이다.
ACTIONS_BOX: Final = "admin_area_access_actions"
ACTION_ROW: Final = "admin_area_access_action_row"
GRID_BOX: Final = "admin_area_access_grid_box"
SAVE_KEY: Final = "admin_area_access_list_save"
DISCARD_KEY: Final = "admin_area_access_list_discard"
REREAD_KEY: Final = "admin_area_access_list_reread"
SAVE_LABEL: Final = "저장"
SAVE_HELP: Final = (
    "바뀐 것 전부(등급 바꿈 · 넣기 · 줄 지우기)를 S3 에 저장합니다 — 뺀 사람의 열린 탭은 다음 "
    "조작에 닫힙니다."
)
SAVE_LOCKED_WHY: Final = "고친 칸이 있으면 누를 수 있습니다."
DISCARD_HELP: Final = "저장하지 않은 고침을 버립니다."
# 단추 줄과 표 도구 막대를 한 줄로 세우는 창 폭 · 단추 줄 자리(`edit_grid.one_line_style`).
ONE_LINE_MIN_WINDOW_PX: Final = 1500
ACTION_ROW_RESERVE_PX: Final = 640
ONE_LINE_STYLE: Final = edit_grid.one_line_style(
    ACTIONS_BOX,
    ACTION_ROW,
    GRID_BOX,
    min_window_px=ONE_LINE_MIN_WINDOW_PX,
    reserve_px=ACTION_ROW_RESERVE_PX,
)
ENV_ADMIN_LABEL: Final = grades.ENV_DEVELOPER_LABEL

NOT_ADMIN_MESSAGE: Final = "개발자만 접속 명단을 고칠 수 있습니다"
UNREAD_MESSAGE: Final = (
    "접속 명단을 아직 읽지 못해 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
CONFLICT_MESSAGE: Final = (
    "그 사이 S3 의 접속 명단이 바뀌어 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
SELF_CHANGE_MESSAGE: Final = "자기 등급은 개발자 아래로 내리거나 자기를 지울 수 없습니다"
ENV_ADMIN_MESSAGE: Final = "환경변수 개발자는 개발자 아래로 내릴 수 없습니다"
GRADE_UNREAD_MESSAGE: Final = (
    "등급 파일을 아직 읽지 못해 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
# 둘째 쓰기의 실패 — 첫째는 남았다(넣기는 명단, 개발자 → 아래는 등급 파일).
ADD_GRADE_FAILED_MESSAGE: Final = (
    "명단에는 넣었고 등급은 적지 못해 열람으로 읽힙니다 — 「다시 읽기」 뒤 다시 하세요"
)
DOWN_LIST_FAILED_MESSAGE: Final = (
    "등급 파일에는 적었고 명단은 저장하지 못해 개발자로 남았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
PROBLEMS_LEAD: Final = "저장하지 않았습니다 — "
NOTHING_CHANGED: Final = "바뀐 것이 없습니다"
UNREAD_GRADES_CAPTION: Final = "등급 파일 읽지 못함"
LIST_READ_FAILED: Final = "접속 명단을 읽지 못했습니다"
GRADES_READ_FAILED: Final = "등급 파일을 읽지 못했습니다"
# 「이 등급으로 보기」 — Admin Area 안쪽 탭 줄 오른쪽 끝 팝오버(운영 + 켜짐의 실제 개발자에게만).
PREVIEW_LABEL: Final = "이 등급으로 보기"
PREVIEW_POPOVER_KEY: Final = "admin_area_grade_preview_popover"
PREVIEW_TOOLS_KEY: Final = "admin_area_grade_preview_tools"
PREVIEW_CHOICE_KEY: Final = "admin_area_grade_preview_choice"
PREVIEW_START_KEY: Final = "admin_area_grade_preview_start"
PREVIEW_START_LABEL: Final = "보기"
PREVIEW_HELP: Final = (
    "이 창만 고른 등급의 화면으로 봅니다 — 저장은 내 실제 등급이고, 창을 닫거나 앱 정보 카드의 "
    "「끝내기」 로 끝납니다"
)
# 탭 줄 오른쪽에 비워 둘 폭(rem) — 「이 등급으로 보기」 단추 자리.
PREVIEW_TAB_RESERVE_REM: Final = 10
# 표 아래 접힌 「최근 등록 · 빼기」(보드 p0-admin-list) — 고친 기록(파일의 마지막 200건)에서 꺼낸다.
RECENT_EXPANDER_KEY: Final = "admin_area_access_list_recent"
RECENT_LABEL: Final = f"최근 등록 · 빼기({NEW_REGISTRATION_DAYS}일)"
RECENT_COLUMNS: Final = ("시각", "계정", "한 일")
RECENT_WHAT: Final = {
    access_store.CHANGE_SELF: VIA_SELF_LABEL,
    access_store.CHANGE_ADD: VIA_ADMIN_LABEL,
    access_store.CHANGE_REMOVE: "뺌",
}


def save_failure_message(failure: S3Failure) -> str:
    """답을 받은 거절만 「그대로」 라고 쓴다 — 답을 받지 못한 PUT 은 들어갔을 수 있다."""
    problem = access_store.problem_of(failure)
    reason = access_problem_text(problem)
    if problem.unconfirmed:
        return f"S3 에 저장됐는지 알 수 없습니다 — {reason} · 「다시 읽기」 로 확인하세요"
    return f"S3 에 저장하지 못했습니다 — {reason} · 명단은 그대로입니다"


Outcome = grade_store.ChangeResult | str


def _refusal(exc: Exception) -> str | None:
    """쓰기 거부의 글. 저장소 실패가 아니면 `None`(부르는 쪽이 다시 던진다)."""
    if isinstance(exc, access_store.SelfChangeError):
        return SELF_CHANGE_MESSAGE
    if isinstance(exc, access_store.EnvAdminError):
        return ENV_ADMIN_MESSAGE
    if isinstance(exc, access_store.NotAdminError):
        return NOT_ADMIN_MESSAGE
    if isinstance(exc, access_store.StoreUnreadError):
        return UNREAD_MESSAGE
    if isinstance(exc, grade_store.GradeUnreadError):
        return GRADE_UNREAD_MESSAGE
    if isinstance(exc, access_store.StoreConflictError):
        return CONFLICT_MESSAGE
    if isinstance(exc, S3Failure):
        return save_failure_message(exc)
    return None


def _write(action: Callable[[], grade_store.ChangeResult]) -> Outcome:
    """저장 한 번 — 결과 또는 거부 글."""
    try:
        return action()
    except (
        access_store.NotAdminError,
        access_store.SelfChangeError,
        access_store.EnvAdminError,
        access_store.StoreUnreadError,
        access_store.StoreConflictError,
        grade_store.GradeUnreadError,
        S3Failure,
    ) as exc:
        text = _refusal(exc)
        assert text is not None
        return text


def _reread() -> None:
    """「다시 읽기」 콜백 — 명단과 등급 파일을 함께. 실패해도 메모리 한 벌은 그대로다."""
    cfg = runtime.config()
    try:
        listed, graded = grade_store.reread(cfg, sso_identity.verified_identity())
    except access_store.NotAdminError:
        queue_flash(ACCESS_LIST_FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    problem: SourceProblem | None = listed or graded
    if problem is not None:
        lead = LIST_READ_FAILED if listed is not None else GRADES_READ_FAILED
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"{lead} — {access_problem_text(problem)}",
            kind="error",
            popup_only=True,
        )
        return
    source = runtime.access_source()
    document = ListDocument() if source is None else source.document or ListDocument()
    queue_flash(
        ACCESS_LIST_FLASH_KEY,
        f"접속 명단을 다시 읽었습니다 — 명단 {len(document.entries)} · 버전 {document.revision}",
    )


def _when_text(value: str) -> str:
    """파일의 UTC 시각 → KST 글(`korea_time`). 읽거나 옮기지 못하면 받은 글 그대로(사람이 고친 파일
    — 시각대 없는 시각 포함)."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return kst_clock(moment, "%Y-%m-%d %H:%M")
    except (ValueError, OverflowError, OSError):
        return value


def recent_changes_table(document: ListDocument, *, now: int) -> pd.DataFrame:
    """최근 `NEW_REGISTRATION_DAYS` 일의 등록(스스로 등록 · 개발자가 넣음) · 빼기 — 새것 먼저.

    칸은 시각 | 계정 | 한 일이다.

    고친 기록은 덧붙이기만 하는 마지막 200건이라 그보다 오래된 줄은 없다. 등급 바꿈 · 정리 줄은
    싣지 않는다(카드 「최근 등록 · 빼기」).
    """
    cutoff = datetime.fromtimestamp(now - NEW_REGISTRATION_DAYS * 86400, tz=timezone.utc)
    rows: list[tuple[str, str, str]] = []
    for item in reversed(document.changes):
        what = RECENT_WHAT.get(item.what)
        if what is None or not item.loginid:
            continue
        try:
            moment = datetime.fromisoformat(item.at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.tzinfo is None or moment < cutoff:
            continue
        rows.append((_when_text(item.at), item.loginid, what))
    return pd.DataFrame(rows, columns=list(RECENT_COLUMNS))


def _render_recent(document: ListDocument) -> None:
    """표 아래 접힌 「최근 등록 · 빼기(30일)」 — 읽기만 한다(값은 이 펼침 안 표에만)."""
    recent = recent_changes_table(document, now=int(time.time()))
    with st.expander(RECENT_LABEL, key=RECENT_EXPANDER_KEY):
        if recent.empty:
            st.caption("없음")
        else:
            # 펼침의 첫 표 — 표 도구 막대가 머리 오른쪽 끝(접기 누름)을 덮지 않게 띄운다.
            toolbar_clearance()
            st.dataframe(recent, hide_index=True, width="stretch", placeholder="")


def access_list_target() -> alerts.GotoTarget:
    """알림 「그 화면으로」 가 들고 가는 대상 — 받는 쪽이 이 펼침을 연다(나머지 칸은 쓰지
    않는다)."""
    return alerts.GotoTarget(kind=ACCESS_LIST_TARGET_KIND, scenario="-", revision="-")


def open_access_list(_scenario: str, _revision: str) -> None:
    """알림 칸의 「그 화면으로」 콜백이 Admin Area 에 닿은 회차 맨 앞에서 부른다 — 「접속 명단」
    펼침을 연다(설계 규칙 UI-NAV-01 — 데려가면 그 자리까지 연다)."""
    st.session_state[EXPANDER_KEY] = True
    st.session_state[remembered_box_key(EXPANDER_KEY)] = (True, EXPANDER_LABEL)


def list_caption(cfg_revision: int, people: int, developers: int, env: int, *, unread: bool) -> str:
    """작업 줄 끝 캡션 — 「버전 n · 명단 n · 개발자 n(환경변수 n)」(+ 등급 파일을 못 읽은 동안)."""
    text = f"버전 {cfg_revision} · 명단 {people} · 개발자 {developers}(환경변수 {env})"
    return f"{text} · {UNREAD_GRADES_CAPTION}" if unread else text


@dataclass
class _Saved:
    """저장 한 번의 결과 — 쓴 수 · 명단 판, 초안을 걷을 키, 둘째 쓰기 실패 글, 막힌 까닭."""

    removed: int = 0
    graded: int = 0
    added: int = 0
    revision: int = 0
    done: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    refusal: str | None = None

    def parts(self) -> list[str]:
        counts = ((self.removed, "뺌"), (self.graded, "등급"), (self.added, "넣음"))
        return [f"{word} {count}명" for count, word in counts if count]


def _write_plan(cfg: SsoConfig, identity: Identity | None, plan: AccessPlan) -> _Saved:
    """저장 판을 좁히는 차례로 쓴다 — 빼기 → 등급 바꿈 → 넣기(등급마다). 막히면 거기서 멈춘다."""
    saved = _Saved()
    if plan.removed:
        outcome = _write(lambda: grade_store.remove_people(cfg, identity, plan.removed))
        if isinstance(outcome, str):
            saved.refusal = outcome
            return saved
        saved.removed, saved.revision = outcome.removed, outcome.list_revision
        saved.done.update(plan.removed)
    if plan.graded:
        outcome = _write(lambda: grade_store.change_grades(cfg, identity, plan.graded))
        if isinstance(outcome, str):
            saved.refusal = outcome
            return saved
        saved.graded, saved.revision = outcome.graded, outcome.list_revision
        if outcome.second_failed is None:
            saved.done.update(plan.graded)
        else:
            saved.warnings.append(DOWN_LIST_FAILED_MESSAGE)
    for grade, people in plan.added_by_grade().items():
        profiles = {person.loginid: (person.name, person.dept) for person in people}
        outcome = _write(
            partial(
                grade_store.add_people,
                cfg,
                identity,
                [person.loginid for person in people],
                grade,
                profiles=profiles,
            )
        )
        if isinstance(outcome, str):
            saved.refusal = outcome
            return saved
        saved.added += outcome.added
        saved.revision = outcome.list_revision
        saved.done.update(person.row for person in people)
        if outcome.second_failed is not None and ADD_GRADE_FAILED_MESSAGE not in saved.warnings:
            saved.warnings.append(ADD_GRADE_FAILED_MESSAGE)
    return saved


def _current_table(cfg: SsoConfig) -> access_list_grid.AccessTable | None:
    """이 회차의 명단 한 벌로 지은 표(명단을 못 읽었거나 자리가 없으면 None)."""
    source = runtime.access_source()
    document = None if source is None else source.document
    if document is None:
        return None
    identity = sso_identity.verified_identity()
    own = None if identity is None else entry_key(identity.loginid)
    return access_list_grid.build_table(
        document,
        lambda key: grade_store.grade_of(cfg, key),
        own=own,
        env=access_store.env_admins(cfg),
    )


def _save() -> None:
    """「저장」 콜백 — 보낸 고침을 먼저 반영하고(출납은 300ms 묶음이라 마지막 회차보다 늦다) 저장
    판을 읽어 문제가 없으면 쓴다. 결과는 수만."""
    cfg = runtime.config()
    access_list_grid.collect()
    identity = sso_identity.verified_identity()
    if identity is None or not access_store.is_admin(cfg, identity.loginid):
        # 쓰는 순간의 실제 등급 — 저장 함수도 다시 보지만 저장 판(잠긴 줄)보다 먼저 까닭을 가른다.
        queue_flash(ACCESS_LIST_FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    table = _current_table(cfg)
    if table is None:
        queue_flash(ACCESS_LIST_FLASH_KEY, UNREAD_MESSAGE, kind="error", popup_only=True)
        return
    access_list_grid.apply(table)
    plan = access_list_grid.plan(table)
    if plan.problems.any:
        queue_flash(ACCESS_LIST_FLASH_KEY, PROBLEMS_LEAD + plan.problems.text(), kind="error")
        return
    if plan.empty:
        access_list_grid.discard()
        queue_flash(ACCESS_LIST_FLASH_KEY, NOTHING_CHANGED, kind="info")
        return
    saved = _write_plan(cfg, identity, plan)
    if saved.refusal is None and not saved.warnings:
        access_list_grid.discard()
    else:
        access_list_grid.forget(frozenset(saved.done))
    parts = saved.parts()
    if saved.refusal is not None:
        before = f" — 앞서 저장: {' · '.join(parts)}" if parts else ""
        queue_flash(ACCESS_LIST_FLASH_KEY, saved.refusal + before, kind="error", popup_only=True)
    elif saved.warnings:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            " · ".join([*saved.warnings, *parts]),
            kind="error",
            popup_only=True,
        )
    elif parts:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"접속 명단을 저장했습니다 — {' · '.join(parts)} · 버전 {saved.revision}",
        )
    else:
        queue_flash(ACCESS_LIST_FLASH_KEY, NOTHING_CHANGED, kind="info")


def _render_actions(
    document: ListDocument | None, cfg: SsoConfig, env_admins: frozenset[str]
) -> None:
    """표 위 작업 줄 — 저장 · 편집 취소(고친 것이 있을 때) · 다시 읽기 · 「고칠 칸 n개」 · 끝에 버전
    ·
    명단 · 개발자 수. 그 바로 아래가 곁 알림 칸이다(저장 판의 문제 · 못 읽음)."""
    cells, _, errors = access_list_grid.draft_counts()
    pending = cells > 0 and document is not None
    with st.container(key=ACTION_ROW, horizontal=True, vertical_alignment="center", gap="small"):
        st.button(
            SAVE_LABEL,
            icon=":material/save:",
            key=SAVE_KEY,
            type="primary",
            disabled=not pending,
            help=SAVE_HELP if pending else SAVE_LOCKED_WHY,
            on_click=_save,
        )
        if pending:
            st.button(
                "편집 취소",
                icon=edit_grid.DISCARD_ICON,
                key=DISCARD_KEY,
                help=DISCARD_HELP,
                on_click=access_list_grid.discard,
            )
        st.button(
            "다시 읽기",
            icon=":material/refresh:",
            key=REREAD_KEY,
            on_click=_reread,
        )
        if errors:
            st.markdown(f":red[고칠 칸 {errors:,}개]")
        if document is not None:
            access = runtime.current_access(cfg)
            st.caption(
                list_caption(
                    document.revision,
                    len(document.entries),
                    access.admin_count,
                    len(env_admins),
                    unread=grade_store.read_problem(cfg) is not None,
                ),
                width="content",
            )


def render_access_list_admin() -> None:
    """Admin 「접속 명단」 펼침. 자리가 없는 회차에는 아무것도 부르지 않는다(모듈 설명)."""
    cfg = runtime.config()
    if not access_store.is_on(cfg):
        return
    identity = sso_identity.verified_identity()
    if identity is None or not access_store.is_admin(cfg, identity.loginid):
        return
    source = runtime.access_source()
    document = None if source is None else source.document
    env_admins = access_store.env_admins(cfg)
    table = _current_table(cfg)
    if table is not None and access_list_grid.apply(table):
        # 채운 새 줄이 늘면 빈 새 줄을 더 단다(같은 업무 키라 초안은 제 줄에 붙는다).
        table = _current_table(cfg)
    with remembered_expander(EXPANDER_LABEL, icon=":material/group:", key=EXPANDER_KEY):
        actions = st.container(key=ACTIONS_BOX)
        grid_box = st.container(key=GRID_BOX)
        with actions:
            _render_actions(document, cfg, env_admins)
            # 곁 알림(저장 판의 문제)은 단추 줄 바로 아래 · 표 앞이다. 회차마다 한 번 불려 그
            # 회차의 알림이 늘 나간다.
            slot = render_flash(ACCESS_LIST_FLASH_KEY)
            if document is None:
                slot.caption("접속 명단 읽지 못함")
        with grid_box:
            access_list_grid.render(table, page_style=ONE_LINE_STYLE)
        if document is not None:
            _render_recent(document)


def preview_available() -> bool:
    """「이 등급으로 보기」 를 세우나 — 운영 + 켜짐의 실제 개발자(운영 아닌 곳은 제한이 없어 서지
    않는다)."""
    cfg = runtime.config()
    return cfg.operational and cfg.mode is SsoMode.ON and sso_identity.viewer_is_developer()


def _start_preview() -> None:
    """「보기」 콜백 — 다시 판정하고 고른 등급을 이 창의 세션 칸에만 적는다(화면만 바뀐다)."""
    chosen = st.session_state.get(PREVIEW_CHOICE_KEY)
    if not preview_available() or chosen not in sso_identity.PREVIEW_GRADES:
        return
    st.session_state[sso_identity.GRADE_PREVIEW_KEY] = chosen


def _preview_style(box_key: str, *, beside_module_status: bool) -> str:
    """단추 칸을 탭 줄 오른쪽 끝(모듈 상태 단추가 있으면 그 왼쪽)에 얹고 탭 줄 오른쪽을 비운다."""
    box = f'.st-key-{box_key}:has(> [data-testid="stTabs"])'
    holder = f'{box} > [data-testid="stLayoutWrapper"]:has(> .st-key-{PREVIEW_TOOLS_KEY})'
    tablist = f'{box} > [data-testid="stTabs"] > div > [role="tablist"]'
    offset = TAB_ROW_RESERVE_REM if beside_module_status else 0
    return (
        "<style>"
        f"{box} {{ position: relative; }}\n"
        f"{holder} {{ position: absolute; top: 0; right: {offset}rem; width: auto; z-index: 1; }}\n"
        f".st-key-{PREVIEW_TOOLS_KEY} button {{ min-height: 2rem; padding-top: 0.125rem; "
        "padding-bottom: 0.125rem; }\n"
        f"{tablist} {{ padding-right: {offset + PREVIEW_TAB_RESERVE_REM}rem !important; }}"
        "</style>"
    )


def render_grade_preview(*, box_key: str, beside_module_status: bool) -> None:
    """「이 등급으로 보기」 팝오버 — 탭 묶음을 담은 칸(`box_key`) 안 맨 앞에서 부른다(모듈 설명).
    자리가 없는 회차에는 아무것도 부르지 않는다."""
    if not preview_available():
        return
    with st.container(key=PREVIEW_TOOLS_KEY):
        st.html(_preview_style(box_key, beside_module_status=beside_module_status))
        with st.popover(
            PREVIEW_LABEL, icon=":material/visibility:", key=PREVIEW_POPOVER_KEY, help=PREVIEW_HELP
        ):
            # 처음 값은 열람(첫 항목) — 닫힌 팝오버 칸을 세션 대입으로 채우지 않는다.
            st.radio(
                PREVIEW_LABEL,
                sso_identity.PREVIEW_GRADES,
                index=0,
                key=PREVIEW_CHOICE_KEY,
                format_func=grades.label_of,
                label_visibility="collapsed",
            )
            st.button(
                PREVIEW_START_LABEL,
                key=PREVIEW_START_KEY,
                type="primary",
                on_click=_start_preview,
            )
