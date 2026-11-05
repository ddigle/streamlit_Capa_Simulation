# Purpose: Admin Area 「접속 명단」 — 관리자에게만 S3 명단의 목록·추가·지우기·다시 읽기를 그린다.

"""Admin 「접속 명단」.

자리는 통합인증이 켜지고 S3 명단이 켜진 서버의 **관리자 회차에만** 있다. 그 밖(꺼짐 · 사내 PC ·
개발 · S3 명단 꺼짐 · 관리자가 아닌 사람)에는 Streamlit 호출을 하나도 하지 않는다 — 요소 순번이
그대로다.

쓰기(추가 · 지우기 · 다시 읽기)는 그 회차에 쿠키에서 다시 검증한 신원
(`sso_identity.verified_identity`)을 넘기고, 저장소 쪽(`auth/access_store`)이 신원 · 관리자를 다시
본다 — 이 화면이 관리자에게만 그려진다는 것을 믿지 않는다(보인 회차와 누른 회차의 권한이 달라질 수
있고 위젯 콜백은 본문보다 먼저 돈다).

알림에는 개수와 까닭만 싣는다 — loginid 는 실제 사람을 가리켜 Alarm 복사 · 리뷰로 나가면 안
된다(런북 3-3). 저장 실패 · 그 사이 바뀜은 메모리를 바꾸지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation.auth import access_store, runtime
from capa_simulation.auth.access import ListDocument, parse_entries
from capa_simulation.components import sso_identity
from capa_simulation.components.admin_dialog import (
    admin_dialog_is_open,
    close_admin_dialog,
    open_admin_dialog,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.paste_form import refuse_paste, render_paste_form, tell_paste
from capa_simulation.components.sso_status import access_problem_text
from capa_simulation.io.s3_small import S3Failure
from capa_simulation.sidebar_status import remembered_expander

EXPANDER_KEY: Final = "admin_area_access_list"
ACCESS_LIST_FLASH_KEY: Final = "admin_area_access_list_flash"
ACCESS_LIST_REMOVE_KEY: Final = "admin_area_access_list_remove"
ADD_DIALOG: Final = "access_list_add"
ADD_FORM_KEY: Final = "access_list_add"
ADD_TEXT_KEY: Final = "admin_area_access_list_add_text"
# 표를 머리 줄째 붙여 넣어도 머리가 사람으로 들어가지 않게.
HEADER_WORDS: Final = frozenset({"loginid"})

NOT_ADMIN_MESSAGE: Final = "관리자만 접속 명단을 고칠 수 있습니다"
UNREAD_MESSAGE: Final = (
    "접속 명단을 아직 읽지 못해 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
CONFLICT_MESSAGE: Final = (
    "그 사이 S3 의 접속 명단이 바뀌어 저장하지 않았습니다 — 「다시 읽기」 뒤 다시 하세요"
)
ADD_LOCKED_WHY: Final = "접속 명단을 읽은 뒤에 넣을 수 있습니다 — 「다시 읽기」"
REMOVE_HELP: Final = "고른 사람을 명단에서 뺍니다. 그 사람의 열린 탭은 다음 조작에 닫힙니다."


def save_failure_message(failure: S3Failure) -> str:
    problem = access_store.problem_of(failure)
    return f"S3 에 저장하지 못했습니다 — {access_problem_text(problem)} · 명단은 그대로입니다"


def _save(
    *, add: tuple[str, ...] = (), remove: tuple[str, ...] = ()
) -> access_store.SaveResult | str:
    """저장 한 번 — 결과 또는 거부 글. 신원은 이 회차의 쿠키에서 다시 꺼낸다."""
    cfg = runtime.config()
    try:
        return access_store.save_changes(
            cfg, sso_identity.verified_identity(), add=add, remove=remove
        )
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
        queue_flash(ACCESS_LIST_FLASH_KEY, "지울 사람을 고르세요", kind="warning")
        return
    outcome = _save(remove=selected)
    if isinstance(outcome, str):
        queue_flash(ACCESS_LIST_FLASH_KEY, outcome, kind="error")
        return
    st.session_state[ACCESS_LIST_REMOVE_KEY] = []
    if outcome.changed:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"접속 명단에서 {outcome.removed}명을 뺐습니다 — 판 {outcome.revision}",
        )
    else:
        queue_flash(ACCESS_LIST_FLASH_KEY, "바뀐 것이 없습니다", kind="info")


def _reread() -> None:
    """「다시 읽기」 콜백 — 실패해도 메모리 명단은 그대로다."""
    cfg = runtime.config()
    try:
        problem = access_store.reread(cfg, sso_identity.verified_identity())
    except access_store.NotAdminError:
        queue_flash(ACCESS_LIST_FLASH_KEY, NOT_ADMIN_MESSAGE, kind="error")
        return
    if problem is not None:
        queue_flash(
            ACCESS_LIST_FLASH_KEY,
            f"접속 명단을 읽지 못했습니다 — {access_problem_text(problem)}",
            kind="error",
        )
        return
    source = runtime.access_source()
    document = ListDocument() if source is None else source.document or ListDocument()
    queue_flash(
        ACCESS_LIST_FLASH_KEY,
        f"접속 명단을 다시 읽었습니다 — 사용자 {len(document.entries)} · 판 {document.revision}",
    )


def _added_message(result: access_store.SaveResult, unreadable: int) -> str:
    parts = [f"접속 명단에 {result.added}명을 넣었습니다"]
    if result.already:
        parts.append(f"이미 있음 {result.already}")
    if unreadable:
        parts.append(f"꼴이 아니라 뺌 {unreadable}")
    parts.append(f"판 {result.revision}")
    return " · ".join(parts)


@st.dialog("접속 명단 · 추가", width="large", on_dismiss=close_admin_dialog)
def _add_dialog() -> None:
    submit = render_paste_form(
        ADD_FORM_KEY,
        text_key=ADD_TEXT_KEY,
        text_label="loginid 붙여넣기",
        apply_label="명단에 넣기",
    )
    if submit is None:
        return
    keys, unreadable = parse_entries(submit.text)
    keys = tuple(key for key in keys if key not in HEADER_WORDS)
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
    """파일의 UTC 시각 → 서버 시각대 글. 읽지 못하면 받은 글 그대로(사람이 고친 파일)."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def people_table(document: ListDocument) -> pd.DataFrame:
    """목록 — loginid | 넣은 때 | 넣은 사람."""
    rows = [
        (entry.loginid, _when_text(entry.added_at), entry.added_by) for entry in document.entries
    ]
    return pd.DataFrame(rows, columns=["loginid", "넣은 때", "넣은 사람"])


def _render_people(document: ListDocument) -> None:
    if not document.entries:
        st.caption("명단에 사람이 없습니다")
        return
    options = [entry.loginid for entry in document.entries]
    # 다시 읽기로 빠진 사람이 고른 칸에 남으면 위젯이 옵션 밖 값을 받는다.
    selected = st.session_state.get(ACCESS_LIST_REMOVE_KEY)
    if selected:
        st.session_state[ACCESS_LIST_REMOVE_KEY] = [item for item in selected if item in options]
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        st.multiselect("지울 사람", options, key=ACCESS_LIST_REMOVE_KEY)
        st.button(
            "지우기",
            icon=":material/person_remove:",
            key="admin_area_access_list_remove_button",
            help=REMOVE_HELP,
            on_click=_remove_selected,
        )
    st.dataframe(people_table(document), hide_index=True, width="stretch")


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
    with remembered_expander("접속 명단", icon=":material/group:", key=EXPANDER_KEY):
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
            if document is not None:
                access = runtime.current_access(cfg)
                st.caption(
                    f"판 {document.revision} · 사용자 {len(document.entries)} · "
                    f"관리자 {access.admin_count}(환경변수)"
                )
        render_flash(ACCESS_LIST_FLASH_KEY)
        if document is None:
            st.caption("접속 명단 읽지 못함")
        else:
            _render_people(document)
    if admin_dialog_is_open(ADD_DIALOG):
        _add_dialog()
