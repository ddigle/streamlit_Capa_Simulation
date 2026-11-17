# Purpose: Admin Area 「접속 명단」 — 개발자에게만 S3 명단 · 등급 파일의 목록·추가·등급
# 바꾸기·지우기·
# 다시 읽기와 「이 등급으로 보기」 를 그린다.

"""Admin 「접속 명단」.

자리는 통합인증이 켜지고 S3 명단이 켜진 서버의 **개발자 회차에만** 있다. 그 밖(꺼짐 · 사내 PC ·
개발 · S3 명단 꺼짐 · 개발자가 아닌 사람)에는 Streamlit 호출을 하나도 하지 않는다 — 요소 순번이
그대로다.

쓰기(추가 · 지우기 · 등급 바꾸기 · 다시 읽기)는 그 회차에 쿠키에서 다시 검증한 신원
(`sso_identity.verified_identity`)을 넘기고, 저장소 쪽(`auth/grade_store` → `auth/access_store`)이
신원 · 개발자를 다시 본다 — 이 화면이 개발자에게만 그려진다는 것을 믿지 않는다(보인 회차와 누른
회차의 권한이 달라질 수 있고 위젯 콜백은 본문보다 먼저 돈다). 등급은 넷(열람 · 실무자 · 관리자 ·
개발자)이고 명단 파일(`user` · `admin` — `admin` = 개발자)과 그 곁의 등급 파일(실무자 · 관리자)을
합쳐 읽는다(2026-11-18 접속 등급).

알림에는 개수와 까닭만 싣는다 — loginid 는 실제 사람을 가리켜 Alarm 복사 · 리뷰로 나가면 안
된다(런북 3-3). 저장 실패 · 그 사이 바뀜은 메모리를 바꾸지 않는다. 답을 받지 못한 PUT 은 저장소에
들어갔을 수 있어 「그대로」 라고 단언하지 않고 다시 읽기로 보낸다. 다시 읽기 · 지우기의 실패와
거부는 그 자리에 고칠 입력이 없어 알림창 · Alarm 에만 낸다(설계 규칙 UI-NTF-03). 「지울 사람을
고르세요」 는 곁 칸을 고치는 말이라 곁에 남는다.

붙여 넣은 글이 표면 머리 줄의 `loginid`(또는 이 표의 「계정」) 칸만 읽고, 그 칸을 찾지 못한 표는
넣지 않는다 — 다른 칸의 값(날짜 · 이름)이 명단에 들어가면 그 값을 가진 사람에게 접속이 열린다.

표는 계정 · 이름 · 부서 · 등록 시각 · 등록 길(스스로 등록 · 개발자가 넣음 — 아래 「최근 등록 ·
빼기」 의 「한 일」 과 같은 낱말 — E2E 보드 s-C-02) · 등급(열람 · 실무자 · 관리자 · 개발자 ·
개발자(환경변수))이다(2026-11-14 보드 p0-admin-list · n2 답 · 2026-11-18 결정 11). 「사람 고르기」
칸(「계정 · 이름 · 부서」)으로 여럿을 골라 「등급 바꾸기」 메뉴 하나(넷 가운데 하나)로 한 번에 같은
등급으로 바꾼다 — 고른 사람에 나 자신 · 환경변수 개발자가 있으면 개발자 아래 셋이 잠기고 까닭
풍선이 선다(저장소 쪽도 다시 본다). 「명단에 넣기」 창은 등급 칸 하나(처음 값 실무자)를 든다. 접속
명단 알림 `AD-08` · `AD-09` · `AD-19` · 등급 파일 `AD-25` 의 「그 화면으로」 가 이 펼침을
연다(`open_access_list` — 알림 칸의 받는 쪽 `ACCESS_LIST_TARGET_KIND`). 표 아래 접힌 「최근
등록 · 빼기(30일)」 은 파일의 고친 기록에서 꺼낸 읽기 전용 표다(시각 · 계정 · 한 일 — 등급 바꿈은
감사 기록이 맡는다).

「이 등급으로 보기」(`render_grade_preview`)는 운영 + 켜짐의 실제 개발자에게만 Admin Area 안쪽 탭 줄
오른쪽 끝 팝오버로 선다(설계 규칙 UI-LAY-13 — 탭 위 줄을 늘리지 않는다). 그 창의 세션 칸에만 적고
화면만 바뀐다 — 저장은 실제 등급이고, 창을 닫거나 앱 정보 카드의 「끝내기」 로 끝난다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.auth import access_store, grade_store, grades, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    VIA_SELF,
    ListDocument,
    ListEntry,
    SourceProblem,
    parse_entries,
)
from capa_simulation.auth.config import SsoMode
from capa_simulation.components import sso_identity
from capa_simulation.components.admin_dialog import (
    admin_dialog_is_open,
    close_admin_dialog,
    open_admin_dialog,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.module_status import TAB_ROW_RESERVE_REM
from capa_simulation.components.paste_form import refuse_paste, render_paste_form, tell_paste
from capa_simulation.components.sso_status import NEW_REGISTRATION_DAYS, access_problem_text
from capa_simulation.components.table_toolbar import toolbar_clearance
from capa_simulation.io.s3_small import S3Failure
from capa_simulation.korea_time import kst_clock
from capa_simulation.sidebar_status import remembered_box_key, remembered_expander

EXPANDER_KEY: Final = "admin_area_access_list"
EXPANDER_LABEL: Final = "접속 명단"
# 알림의 「그 화면으로」 가 Admin Area 에 닿은 뒤 이 펼침을 여는 받는 쪽의
# 이름(`alerts.GotoTarget`).
ACCESS_LIST_TARGET_KIND: Final = "access_list"
ACCESS_LIST_FLASH_KEY: Final = "admin_area_access_list_flash"
ACCESS_LIST_REMOVE_KEY: Final = "admin_area_access_list_remove"
ADD_DIALOG: Final = "access_list_add"
ADD_FORM_KEY: Final = "access_list_add"
ADD_TEXT_KEY: Final = "admin_area_access_list_add_text"
# 표의 머리 칸 이름. 머리 줄을 찾는 기준이고, 목록의 머리 줄로 들어와도 사람으로 넣지 않는다 —
# 이 표를 그대로 붙여 넣으면 「계정」 칸을 읽는다.
LOGINID_HEADER: Final = "loginid"
ACCOUNT_HEADER: Final = "계정"
_ACCOUNT_HEADERS: Final = (LOGINID_HEADER, ACCOUNT_HEADER)
TABLE_COLUMNS: Final = ("계정", "이름", "부서", "등록 시각", "등록 길", "등급")
# 명단에 든 길 — 「등록 길」 칸과 「최근 등록 · 빼기」 의 「한 일」 이 함께 쓰는 두 낱말.
VIA_SELF_LABEL: Final = "스스로 등록"
VIA_ADMIN_LABEL: Final = f"{grades.GRADE_LABELS[grades.DEVELOPER]}가 넣음"
VIA_LABELS: Final = {VIA_SELF: VIA_SELF_LABEL}
ENV_ADMIN_LABEL: Final = grades.ENV_DEVELOPER_LABEL
_CELL_SEPARATORS: Final = ("\t", ",", ";")

NOT_ADMIN_MESSAGE: Final = "개발자만 접속 명단을 고칠 수 있습니다"
UNREAD_MESSAGE: Final = (
    "접속 명단을 아직 읽지 못해 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
CONFLICT_MESSAGE: Final = (
    "그 사이 S3 의 접속 명단이 바뀌어 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
TABLE_REFUSED_MESSAGE: Final = (
    "칸이 여럿인 표라 넣지 않았습니다 — "
    "머리 줄에 loginid 칸(또는 계정 칸)이 있어야 그 칸만 읽습니다"
)
SELF_CHANGE_MESSAGE: Final = "자기 등급은 개발자 아래로 내리거나 자기를 지울 수 없습니다"
ENV_ADMIN_MESSAGE: Final = "환경변수 개발자는 개발자 아래로 내릴 수 없습니다"
GRADE_UNREAD_MESSAGE: Final = (
    "등급 파일을 아직 읽지 못해 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
# 둘째 쓰기의 실패 — 첫째는 남았다(넣기 · 빼기는 명단, 개발자 → 아래는 등급 파일).
ADD_GRADE_FAILED_MESSAGE: Final = (
    "명단에는 넣었고 등급은 적지 못해 열람으로 읽힙니다 — 「다시 읽기」 뒤 다시 하세요"
)
DOWN_LIST_FAILED_MESSAGE: Final = (
    "등급 파일에는 적었고 명단은 저장하지 못해 개발자로 남았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
GRADE_MENU_LABEL: Final = "등급 바꾸기"
GRADE_MENU_KEY: Final = "admin_area_access_list_grade_menu"
GRADE_BUTTON_KEY: Final = "admin_area_access_list_grade_{grade}"
# 개발자 아래 셋이 잠긴 까닭(고른 사람에 나 자신 · 환경변수 개발자가 있음).
GRADE_LOCKED_WHY: Final = "나 자신 · 환경변수 개발자는 개발자 아래로 내릴 수 없습니다"
ADD_GRADE_KEY: Final = "admin_area_access_list_add_grade"
ADD_GRADE_LABEL: Final = "등급"
UNREAD_GRADES_CAPTION: Final = "등급 파일 읽지 못함"
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
PICK_FIRST_MESSAGE: Final = "사람을 고르세요"
ADD_LOCKED_WHY: Final = "접속 명단을 읽은 뒤에 넣을 수 있습니다 — 「다시 읽기」"
# 글 칸이 빈 동안 잠긴 「명단에 넣기」 의 까닭 풍선 — 이 창은 표가 아니라 loginid 목록을 받는다.
ADD_EMPTY_WHY: Final = "loginid 를 넣으면 누를 수 있습니다."
REMOVE_HELP: Final = "고른 사람을 명단에서 뺍니다. 그 사람의 열린 탭은 다음 조작에 닫힙니다."
# 고르기 칸(지우기 · 등급 바꾸기가 함께 쓴다)의 이름 — 라벨을 접은 칸이라 자리표시 글로 보인다.
REMOVE_PICKER_LABEL: Final = "사람 고르기"
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


def _picked() -> tuple[str, ...]:
    return tuple(st.session_state.get(ACCESS_LIST_REMOVE_KEY) or ())


def _remove_selected() -> None:
    """「지우기」 콜백 — 본문보다 먼저 돌아 고른 칸을 비울 수 있다(옵션에서 빠진 값이 남지 않게)."""
    selected = _picked()
    if not selected:
        queue_flash(ACCESS_LIST_FLASH_KEY, PICK_FIRST_MESSAGE, kind="warning")
        return
    cfg = runtime.config()
    outcome = _write(
        lambda: grade_store.remove_people(cfg, sso_identity.verified_identity(), selected)
    )
    if isinstance(outcome, str):
        queue_flash(ACCESS_LIST_FLASH_KEY, outcome, kind="error", popup_only=True)
        return
    st.session_state[ACCESS_LIST_REMOVE_KEY] = []
    if outcome.changed:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"접속 명단에서 {outcome.removed}명을 뺐습니다 — 버전 {outcome.list_revision}",
        )
    else:
        queue_flash(ACCESS_LIST_FLASH_KEY, "바뀐 것이 없습니다", kind="info")


def _grade_selected(grade: str) -> None:
    """「등급 바꾸기」 메뉴 항목 콜백 — 고른 사람을 그 등급으로(결과는 수만)."""
    selected = _picked()
    if not selected:
        queue_flash(ACCESS_LIST_FLASH_KEY, PICK_FIRST_MESSAGE, kind="warning")
        return
    cfg = runtime.config()
    outcome = _write(
        lambda: grade_store.change_grades(
            cfg, sso_identity.verified_identity(), dict.fromkeys(selected, grade)
        )
    )
    if isinstance(outcome, str):
        queue_flash(ACCESS_LIST_FLASH_KEY, outcome, kind="error", popup_only=True)
        return
    st.session_state[ACCESS_LIST_REMOVE_KEY] = []
    if outcome.second_failed is not None:
        queue_flash(ACCESS_LIST_FLASH_KEY, DOWN_LIST_FAILED_MESSAGE, kind="error", popup_only=True)
        return
    if outcome.changed:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"{grades.label_of(grade)} {outcome.graded}명 — 등급 버전 "
            f"{outcome.grade_revision} · 명단 버전 {outcome.list_revision}",
        )
    else:
        queue_flash(ACCESS_LIST_FLASH_KEY, "바뀐 것이 없습니다", kind="info")


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
        what = "접속 명단" if listed is not None else "등급 파일"
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"{what}을 읽지 못했습니다 — {access_problem_text(problem)}",
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


def pasted_entries(text: str) -> tuple[tuple[str, ...], int] | None:
    """붙여 넣은 글 → (loginid 들, 읽지 못한 수). 어느 칸이 사람인지 모르는 표면 `None`.

    머리 줄에 `loginid` 칸이 있으면 그 칸만 읽는다(탭 · 쉼표 · 세미콜론). 머리 없이 탭이 든 글은
    표로 보고 받지 않는다. 그 밖은 쉼표 · 세미콜론 · 빈칸 · 줄바꿈으로 나눈 목록이다.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    for separator in _CELL_SEPARATORS:
        header = [cell.strip().casefold() for cell in (lines[:1] or [""])[0].split(separator)]
        named = [name for name in _ACCOUNT_HEADERS if name in header]
        if len(header) > 1 and named:
            column = header.index(named[0])
            rows = [line.split(separator) for line in lines[1:]]
            keys, unreadable = parse_entries(
                "\n".join(row[column] for row in rows if column < len(row))
            )
            return keys, unreadable + sum(1 for row in rows if column >= len(row))
    if "\t" in text:
        return None
    keys, unreadable = parse_entries(text)
    return tuple(key for key in keys if key != LOGINID_HEADER), unreadable


def _added_message(result: grade_store.ChangeResult, unreadable: int, grade: str) -> str:
    parts = [f"접속 명단에 {grades.label_of(grade)} {result.added}명을 넣었습니다"]
    if result.already:
        parts.append(f"이미 있음 {result.already}")
    if unreadable:
        parts.append(f"꼴이 아니라 뺌 {unreadable}")
    parts.append(f"버전 {result.list_revision}")
    return " · ".join(parts)


@st.dialog("접속 명단 · 추가", width="large", on_dismiss=close_admin_dialog)
def _add_dialog() -> None:
    # 넣는 사람의 첫 등급 — 처음 값 실무자(2026-11-18 결정 「새로 드는 사람」 가). 이 창에서 무엇을
    # 넣는지 말하는 글은 라벨뿐이라 라벨이 보인다(설계 규칙 UI-INP-08 「라벨 보이는 창」).
    chosen = st.radio(
        ADD_GRADE_LABEL,
        grades.GRADES,
        index=grades.GRADES.index(grades.EDITOR),
        key=ADD_GRADE_KEY,
        format_func=grades.label_of,
        horizontal=True,
    )
    submit = render_paste_form(
        ADD_FORM_KEY,
        text_key=ADD_TEXT_KEY,
        text_label="loginid 붙여넣기",
        apply_label="명단에 넣기",
        # 이 창에서 무엇을 넣는지 말하는 글은 라벨뿐이라 보인다(창 제목은 「접속 명단 · 추가」).
        label_visible=True,
        empty_why=ADD_EMPTY_WHY,
    )
    if submit is None:
        return
    pasted = pasted_entries(submit.text)
    if pasted is None:
        refuse_paste(ADD_FORM_KEY, TABLE_REFUSED_MESSAGE)
        return
    keys, unreadable = pasted
    if not keys:
        refuse_paste(ADD_FORM_KEY, f"넣을 loginid 가 없습니다 — 꼴이 아닌 항목 {unreadable}")
        return
    grade = chosen if chosen in grades.GRADES else grades.EDITOR
    cfg = runtime.config()
    outcome = _write(
        lambda: grade_store.add_people(cfg, sso_identity.verified_identity(), keys, grade)
    )
    if isinstance(outcome, str):
        refuse_paste(ADD_FORM_KEY, outcome)
        return
    if not outcome.changed:
        tell_paste(ADD_FORM_KEY, f"바뀐 것이 없습니다 — 이미 있음 {outcome.already}")
        return
    if outcome.second_failed is not None:
        queue_flash(ACCESS_LIST_FLASH_KEY, ADD_GRADE_FAILED_MESSAGE, kind="error", popup_only=True)
    else:
        queue_flash(ACCESS_LIST_FLASH_KEY, _added_message(outcome, unreadable, grade))
    st.session_state.pop(ADD_TEXT_KEY, None)
    close_admin_dialog()
    st.rerun()


def _when_text(value: str) -> str:
    """파일의 UTC 시각 → KST 글(`korea_time`). 읽거나 옮기지 못하면 받은 글 그대로(사람이 고친 파일
    — 시각대 없는 시각 포함)."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return kst_clock(moment, "%Y-%m-%d %H:%M")
    except (ValueError, OverflowError, OSError):
        return value


def people_table(
    document: ListDocument,
    env_admins: frozenset[str] = frozenset(),
    grade_of: Callable[[str], str] | None = None,
) -> pd.DataFrame:
    """목록 — 계정 | 이름 | 부서 | 등록 시각 | 등록 길 | 등급. 등급은 명단 · 등급 파일을 합친 넷
    (`grade_of` — 없으면 명단 칸만: `admin` 은 개발자, 그 밖은 열람)이고 환경변수 개발자는
    「개발자(환경변수)」."""

    def grade_text(entry: ListEntry) -> str:
        if entry.loginid in env_admins:
            return ENV_ADMIN_LABEL
        if grade_of is not None:
            return grades.label_of(grade_of(entry.loginid))
        return grades.label_of(grades.DEVELOPER if entry.grade == GRADE_ADMIN else grades.VIEWER)

    rows = [
        (
            entry.loginid,
            entry.name,
            entry.dept,
            _when_text(entry.added_at),
            VIA_LABELS.get(entry.via, VIA_ADMIN_LABEL),
            grade_text(entry),
        )
        for entry in document.entries
    ]
    return pd.DataFrame(rows, columns=list(TABLE_COLUMNS))


def person_label(entry: ListEntry) -> str:
    """「사람 고르기」 칸의 글 — 「계정 · 이름 · 부서」(빈 칸은 뺀다 — 개발자가 넣은 사람은
    계정만)."""
    return " · ".join(part for part in (entry.loginid, entry.name, entry.dept) if part)


def grade_menu_locked(selected: tuple[str, ...], own: str | None, env: frozenset[str]) -> bool:
    """고른 사람에 나 자신 · 환경변수 개발자가 있어 개발자 아래 셋을 잠그는가."""
    return any(key == own or key in env for key in selected)


def _render_grade_menu(env_admins: frozenset[str]) -> None:
    """「등급 바꾸기」 메뉴 하나 — 넷 가운데 하나로 고른 사람을 한 번에(결정 11)."""
    identity = sso_identity.verified_identity()
    own = None if identity is None else identity.loginid.casefold()
    locked = grade_menu_locked(_picked(), own, env_admins)
    with st.popover(GRADE_MENU_LABEL, icon=":material/badge:", key=GRADE_MENU_KEY):
        for grade in reversed(grades.GRADES):
            below = grade != grades.DEVELOPER
            st.button(
                grades.label_of(grade),
                key=GRADE_BUTTON_KEY.format(grade=grade),
                width="stretch",
                disabled=locked and below,
                help=GRADE_LOCKED_WHY if locked and below else None,
                on_click=_grade_selected,
                args=(grade,),
            )


def _render_remove_picker(document: ListDocument, env_admins: frozenset[str]) -> None:
    """작업 줄의 고르기 칸 · 「등급 바꾸기」 · 「지우기」. 칸 라벨은 접고(접근성 이름으로 남는다)
    자리표시 글이 그 이름이다.

    칩은 줄을 접는다 — 가로 칸 안의 기본값은 한 줄 가로 스크롤이라 고른 사람이 칸 밖으로 밀려
    보이지 않은 채 「지우기」 에 함께 빠진다(결과 알림은 수만 싣는다). 펼친 목록 맨 위의
    「Select all」 줄은 없다 — 한 번에 전원을 골라 지우면 되돌릴 단추가 없어 한 사람씩 고른다.
    """
    labels = {entry.loginid: person_label(entry) for entry in document.entries}
    options = list(labels)
    # 다시 읽기로 빠진 사람이 고른 칸에 남으면 위젯이 옵션 밖 값을 받는다.
    selected = st.session_state.get(ACCESS_LIST_REMOVE_KEY) or []
    kept = [item for item in selected if item in options]
    if len(kept) != len(selected):
        st.session_state[ACCESS_LIST_REMOVE_KEY] = kept
    st.multiselect(
        REMOVE_PICKER_LABEL,
        options,
        key=ACCESS_LIST_REMOVE_KEY,
        placeholder=REMOVE_PICKER_LABEL,
        label_visibility="collapsed",
        select_all=False,
        wrap=True,
        format_func=lambda key: labels.get(key, key),
    )
    _render_grade_menu(env_admins)
    st.button(
        "지우기",
        icon=":material/person_remove:",
        key="admin_area_access_list_remove_button",
        help=REMOVE_HELP,
        on_click=_remove_selected,
    )


def recent_changes_table(document: ListDocument, *, now: int) -> pd.DataFrame:
    """최근 `NEW_REGISTRATION_DAYS` 일의 등록(스스로 등록 · 관리자가 넣음) · 빼기 — 새것 먼저.

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


def _render_people(document: ListDocument, env_admins: frozenset[str]) -> None:
    if not document.entries:
        st.caption("명단에 사람이 없습니다")
        return
    toolbar_clearance()
    cfg = runtime.config()
    st.dataframe(
        people_table(document, env_admins, lambda key: grade_store.grade_of(cfg, key)),
        hide_index=True,
        width="stretch",
        placeholder="",
    )


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
    with remembered_expander(EXPANDER_LABEL, icon=":material/group:", key=EXPANDER_KEY):
        # 표 위 작업 줄은 한 줄이다(추가 · 다시 읽기 · 고르기 칸 · 등급 바꾸기 · 지우기, 끝에 버전 ·
        # 명단 · 개발자 수).
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.button(
                "추가",
                icon=":material/person_add:",
                key="admin_area_access_list_open_add",
                disabled=document is None,
                help=ADD_LOCKED_WHY if document is None else None,
                on_click=open_admin_dialog,
                args=(ADD_DIALOG,),
            )
            st.button(
                "다시 읽기",
                icon=":material/refresh:",
                key="admin_area_access_list_reread",
                on_click=_reread,
            )
            if document is not None and document.entries:
                _render_remove_picker(document, env_admins)
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
        # 곁 거부(「지울 사람을 고르세요」)는 누른 단추 줄 바로 아래 · 표 띄움 앞이다. 갈래(못
        # 읽음 · 빈 명단 · 표)마다 한 번 불려 그 회차의 알림이 늘 나간다.
        render_flash(ACCESS_LIST_FLASH_KEY)
        if document is None:
            st.caption("접속 명단 읽지 못함")
        else:
            _render_people(document, env_admins)
            _render_recent(document)
    if admin_dialog_is_open(ADD_DIALOG):
        _add_dialog()


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
