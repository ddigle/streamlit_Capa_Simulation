# Purpose: Admin Area 「접속 명단」 — 관리자에게만 S3 명단의 목록·추가·등급 바꾸기·지우기·다시
# 읽기를 그린다.

"""Admin 「접속 명단」.

자리는 통합인증이 켜지고 S3 명단이 켜진 서버의 **관리자 회차에만** 있다. 그 밖(꺼짐 · 사내 PC ·
개발 · S3 명단 꺼짐 · 관리자가 아닌 사람)에는 Streamlit 호출을 하나도 하지 않는다 — 요소 순번이
그대로다.

쓰기(추가 · 지우기 · 다시 읽기)는 그 회차에 쿠키에서 다시 검증한 신원
(`sso_identity.verified_identity`)을 넘기고, 저장소 쪽(`auth/access_store`)이 신원 · 관리자를 다시
본다 — 이 화면이 관리자에게만 그려진다는 것을 믿지 않는다(보인 회차와 누른 회차의 권한이 달라질 수
있고 위젯 콜백은 본문보다 먼저 돈다).

알림에는 개수와 까닭만 싣는다 — loginid 는 실제 사람을 가리켜 Alarm 복사 · 리뷰로 나가면 안
된다(런북 3-3). 저장 실패 · 그 사이 바뀜은 메모리를 바꾸지 않는다. 답을 받지 못한 PUT 은 저장소에
들어갔을 수 있어 「그대로」 라고 단언하지 않고 다시 읽기로 보낸다. 다시 읽기 · 지우기의 실패와
거부는 그 자리에 고칠 입력이 없어 알림창 · Alarm 에만 낸다(설계 규칙 UI-NTF-03). 「지울 사람을
고르세요」 는 곁 칸을 고치는 말이라 곁에 남는다.

붙여 넣은 글이 표면 머리 줄의 `loginid`(또는 이 표의 「계정」) 칸만 읽고, 그 칸을 찾지 못한 표는
넣지 않는다 — 다른 칸의 값(날짜 · 이름)이 명단에 들어가면 그 값을 가진 사람에게 접속이 열린다.

표는 계정 · 이름 · 부서 · 등록 시각 · 등록 길(스스로 · 관리자) · 등급이다(2026-11-14 보드
p0-admin-list ·
n2 답). 등급은 고른 사람에게 「관리자로」 · 「일반으로」 — 환경변수 관리자는 늘 관리자라 내리지
못하고,
자기 등급은 자기가 내리지 못한다(`access_store` 가 다시 본다). 접속 명단 알림 `AD-08` · `AD-09` ·
`AD-19` 의 「그 화면으로」 가 이 펼침을 연다(`open_access_list` — 알림 칸의 받는 쪽
`ACCESS_LIST_TARGET_KIND`). 표 아래
접힌 「최근 등록 · 빼기(30일)」 은 파일의 고친 기록에서 꺼낸 읽기 전용 표다(시각 · 계정 · 한 일).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.auth import access_store, runtime
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    VIA_SELF,
    ListDocument,
    parse_entries,
)
from capa_simulation.components import sso_identity
from capa_simulation.components.admin_dialog import (
    admin_dialog_is_open,
    close_admin_dialog,
    open_admin_dialog,
)
from capa_simulation.components.flash import queue_flash, render_flash
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
VIA_LABELS: Final = {VIA_SELF: "스스로"}
VIA_ADMIN_LABEL: Final = "관리자"
GRADE_LABELS: Final = {GRADE_ADMIN: "관리자", GRADE_USER: "일반"}
ENV_ADMIN_LABEL: Final = "관리자(환경변수)"
_CELL_SEPARATORS: Final = ("\t", ",", ";")

NOT_ADMIN_MESSAGE: Final = "관리자만 접속 명단을 고칠 수 있습니다"
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
SELF_CHANGE_MESSAGE: Final = "자기 등급은 내리거나 자기를 지울 수 없습니다"
ENV_ADMIN_MESSAGE: Final = "환경변수 관리자는 일반으로 내릴 수 없습니다"
PICK_FIRST_MESSAGE: Final = "사람을 고르세요"
ADD_LOCKED_WHY: Final = "접속 명단을 읽은 뒤에 넣을 수 있습니다 — 「다시 읽기」"
# 글 칸이 빈 동안 잠긴 「명단에 넣기」 의 까닭 풍선 — 이 창은 표가 아니라 loginid 목록을 받는다.
ADD_EMPTY_WHY: Final = "loginid 를 넣으면 누를 수 있습니다."
REMOVE_HELP: Final = "고른 사람을 명단에서 뺍니다. 그 사람의 열린 탭은 다음 조작에 닫힙니다."
TO_ADMIN_HELP: Final = "고른 사람에게 관리자 등급을 줍니다 — Admin Area 를 열고 명단을 고칩니다."
TO_USER_HELP: Final = (
    "고른 사람의 관리자 등급을 뺍니다. 환경변수 관리자와 나 자신은 뺄 수 없습니다."
)
# 고르기 칸(지우기 · 등급 바꾸기가 함께 쓴다)의 이름 — 라벨을 접은 칸이라 자리표시 글로 보인다.
REMOVE_PICKER_LABEL: Final = "사람 고르기"
# 표 아래 접힌 「최근 등록 · 빼기」(보드 p0-admin-list) — 고친 기록(파일의 마지막 200건)에서 꺼낸다.
RECENT_EXPANDER_KEY: Final = "admin_area_access_list_recent"
RECENT_LABEL: Final = f"최근 등록 · 빼기({NEW_REGISTRATION_DAYS}일)"
RECENT_COLUMNS: Final = ("시각", "계정", "한 일")
RECENT_WHAT: Final = {
    access_store.CHANGE_SELF: "스스로 등록",
    access_store.CHANGE_ADD: "관리자가 넣음",
    access_store.CHANGE_REMOVE: "뺌",
}


def save_failure_message(failure: S3Failure) -> str:
    """답을 받은 거절만 「그대로」 라고 쓴다 — 답을 받지 못한 PUT 은 들어갔을 수 있다."""
    problem = access_store.problem_of(failure)
    reason = access_problem_text(problem)
    if problem.unconfirmed:
        return f"S3 에 저장됐는지 알 수 없습니다 — {reason} · 「다시 읽기」 로 확인하세요"
    return f"S3 에 저장하지 못했습니다 — {reason} · 명단은 그대로입니다"


def _save(
    *,
    add: tuple[str, ...] = (),
    remove: tuple[str, ...] = (),
    grades: dict[str, str] | None = None,
) -> access_store.SaveResult | str:
    """저장 한 번 — 결과 또는 거부 글. 신원은 이 회차의 쿠키에서 다시 꺼낸다."""
    cfg = runtime.config()
    try:
        return access_store.save_changes(
            cfg, sso_identity.verified_identity(), add=add, remove=remove, grades=grades
        )
    except access_store.SelfChangeError:
        return SELF_CHANGE_MESSAGE
    except access_store.EnvAdminError:
        return ENV_ADMIN_MESSAGE
    except access_store.NotAdminError:
        return NOT_ADMIN_MESSAGE
    except access_store.StoreUnreadError:
        return UNREAD_MESSAGE
    except access_store.StoreConflictError:
        return CONFLICT_MESSAGE
    except S3Failure as failure:
        return save_failure_message(failure)


def _remove_selected() -> None:
    """「지우기」 콜백 — 본문보다 먼저 돌아 고른 칸을 비울 수 있다(옵션에서 빠진 값이 남지 않게)."""
    selected = tuple(st.session_state.get(ACCESS_LIST_REMOVE_KEY) or ())
    if not selected:
        queue_flash(ACCESS_LIST_FLASH_KEY, PICK_FIRST_MESSAGE, kind="warning")
        return
    outcome = _save(remove=selected)
    if isinstance(outcome, str):
        queue_flash(ACCESS_LIST_FLASH_KEY, outcome, kind="error", popup_only=True)
        return
    st.session_state[ACCESS_LIST_REMOVE_KEY] = []
    if outcome.changed:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"접속 명단에서 {outcome.removed}명을 뺐습니다 — 버전 {outcome.revision}",
        )
    else:
        queue_flash(ACCESS_LIST_FLASH_KEY, "바뀐 것이 없습니다", kind="info")


def _grade_selected(grade: str) -> None:
    """「관리자로」 · 「일반으로」 콜백 — 고른 사람의 등급을 바꾼다(결과는 수만)."""
    selected = tuple(st.session_state.get(ACCESS_LIST_REMOVE_KEY) or ())
    if not selected:
        queue_flash(ACCESS_LIST_FLASH_KEY, PICK_FIRST_MESSAGE, kind="warning")
        return
    outcome = _save(grades=dict.fromkeys(selected, grade))
    if isinstance(outcome, str):
        queue_flash(ACCESS_LIST_FLASH_KEY, outcome, kind="error", popup_only=True)
        return
    st.session_state[ACCESS_LIST_REMOVE_KEY] = []
    if outcome.changed:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"{GRADE_LABELS[grade]} 등급 {outcome.graded}명 — 버전 {outcome.revision}",
        )
    else:
        queue_flash(ACCESS_LIST_FLASH_KEY, "바뀐 것이 없습니다", kind="info")


def _reread() -> None:
    """「다시 읽기」 콜백 — 실패해도 메모리 명단은 그대로다."""
    cfg = runtime.config()
    try:
        problem = access_store.reread(cfg, sso_identity.verified_identity())
    except access_store.NotAdminError:
        queue_flash(ACCESS_LIST_FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error", popup_only=True)
        return
    if problem is not None:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"접속 명단을 읽지 못했습니다 — {access_problem_text(problem)}",
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


def _added_message(result: access_store.SaveResult, unreadable: int) -> str:
    parts = [f"접속 명단에 {result.added}명을 넣었습니다"]
    if result.already:
        parts.append(f"이미 있음 {result.already}")
    if unreadable:
        parts.append(f"꼴이 아니라 뺌 {unreadable}")
    parts.append(f"버전 {result.revision}")
    return " · ".join(parts)


@st.dialog("접속 명단 · 추가", width="large", on_dismiss=close_admin_dialog)
def _add_dialog() -> None:
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
    outcome = _save(add=keys)
    if isinstance(outcome, str):
        refuse_paste(ADD_FORM_KEY, outcome)
        return
    if not outcome.changed:
        tell_paste(ADD_FORM_KEY, f"바뀐 것이 없습니다 — 이미 있음 {outcome.already}")
        return
    queue_flash(ACCESS_LIST_FLASH_KEY, _added_message(outcome, unreadable))
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


def people_table(document: ListDocument, env_admins: frozenset[str] = frozenset()) -> pd.DataFrame:
    """목록 — 계정 | 이름 | 부서 | 등록 시각 | 등록 길 | 등급. 환경변수 관리자는
    「관리자(환경변수)」."""
    rows = [
        (
            entry.loginid,
            entry.name,
            entry.dept,
            _when_text(entry.added_at),
            VIA_LABELS.get(entry.via, VIA_ADMIN_LABEL),
            ENV_ADMIN_LABEL
            if entry.loginid in env_admins
            else GRADE_LABELS.get(entry.grade, GRADE_LABELS[GRADE_USER]),
        )
        for entry in document.entries
    ]
    return pd.DataFrame(rows, columns=list(TABLE_COLUMNS))


def _render_remove_picker(document: ListDocument) -> None:
    """작업 줄의 고르기 칸 · 「지우기」. 칸 라벨은 접고(접근성 이름으로 남는다) 자리표시 글이 그
    이름이다.

    칩은 줄을 접는다 — 가로 칸 안의 기본값은 한 줄 가로 스크롤이라 고른 사람이 칸 밖으로 밀려
    보이지 않은 채 「지우기」 에 함께 빠진다(결과 알림은 수만 싣는다). 펼친 목록 맨 위의
    「Select all」 줄은 없다 — 한 번에 전원을 골라 지우면 되돌릴 단추가 없어 한 사람씩 고른다.
    """
    options = [entry.loginid for entry in document.entries]
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
    )
    st.button(
        "관리자로",
        icon=":material/admin_panel_settings:",
        key="admin_area_access_list_grade_admin",
        help=TO_ADMIN_HELP,
        on_click=_grade_selected,
        args=(GRADE_ADMIN,),
    )
    st.button(
        "일반으로",
        icon=":material/person:",
        key="admin_area_access_list_grade_user",
        help=TO_USER_HELP,
        on_click=_grade_selected,
        args=(GRADE_USER,),
    )
    st.button(
        "지우기",
        icon=":material/person_remove:",
        key="admin_area_access_list_remove_button",
        help=REMOVE_HELP,
        on_click=_remove_selected,
    )


def recent_changes_table(document: ListDocument, *, now: int) -> pd.DataFrame:
    """최근 `NEW_REGISTRATION_DAYS` 일의 등록(스스로 · 관리자) · 빼기 — 새것 먼저.

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
    st.dataframe(
        people_table(document, env_admins), hide_index=True, width="stretch", placeholder=""
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
        # 표 위 작업 줄은 한 줄이다(추가 · 다시 읽기 · 고르기 칸 · 지우기, 끝에 버전 · 명단 ·
        # 관리자 수).
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
                _render_remove_picker(document)
            if document is not None:
                access = runtime.current_access(cfg)
                st.caption(
                    f"버전 {document.revision} · 명단 {len(document.entries)} · "
                    f"관리자 {access.admin_count}(환경변수 {len(env_admins)})",
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
