# Purpose: 사용자가 질문을 올리고 답을 주고받는 VOC 자유 게시판 화면을 그린다.

"""VOC.

**여기는 계산 화면이 아니다.** 시나리오도 조회기간도 보지 않는다. 쓰는 사람이 질문을
남기고 아는 사람이 답을 다는 자리이고, 그래서 시나리오를 지워도 그때 나온 질문은 남는다.

게시판을 화면 한 장에 두는 이유는 목록과 본문을 오가면 **답이 달렸는지 보려고 매번
들어가야** 하기 때문이다. 글마다 답글 수와 답변 완료 여부를 접힌 줄에 적어 두고, 펴면
그 자리에서 답을 단다.

작성자는 로그인 이름이 아니라 **직접 적는 이름**이다. 이 앱에는 인증이 없으므로 이름을
서버가 보증하는 척하지 않는다 — 누가 물었는지 답을 돌려줄 정도만 남긴다.
"""

from __future__ import annotations

from typing import Any, cast

import pandas as pd
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.write_guard import (
    current_generation,
    just_written,
    note_notice,
    notice_marks,
    write_once,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.services.voc_board import VOC_CATEGORIES, VocPostGoneError
from capa_simulation.settings import DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card, remembered_expander

AUTHOR_KEY = "voc_author"
# 글마다 하나씩 생기는 위젯이라 키에 글 번호를 붙인다. 접두를 리터럴로 흩어 두면
# 겹침 검사(`tests/test_session_key_collisions.py`)가 기준 키를 보지 못한다.
POST_EXPANDER_KEY = "voc_post_expander"
REPLY_FORM_KEY = "voc_reply_form"
REPLY_BODY_KEY = "voc_reply_body"
RESOLVE_KEY = "voc_resolve"
DELETE_CONFIRM_KEY = "voc_delete_confirm"
DELETE_KEY = "voc_delete"
# 글 하나의 처리(답변·답변 완료 표시·지우기)가 실패한 문구. 다음 회차에 그 글 상자 안 칸이
# 그린다(`flash`).
POST_ERROR_KEY = "voc_post_error"
CATEGORY_FILTER_KEY = "voc_category_filter"
OPEN_ONLY_KEY = "voc_open_only"
SEARCH_KEY = "voc_search"
FLASH_KEY = "voc_flash"
POST_FORM_KEY = "voc_post_form"
POST_CATEGORY_KEY = "voc_post_category"
POST_TITLE_KEY = "voc_post_title"
POST_BODY_KEY = "voc_post_body"
POST_FORM_ERROR_KEY = "voc_post_form_error"
# 그 사이 다른 세션이 지운 글에 답변·답변 완료 표시를 하려던 거절 `(문구, 적어 둔 답변)`. 지운 글의
# 상자는 다시 그리지 않으므로 글 상자가 아니라 머리 알림 칸에 그린다.
GONE_NOTICE_KEY = "voc_gone_notice"
# 쓰기 단추의 key 세대(AGENTS 9장 「쓰기 콜백은 빠른 두 번 누름을 거른다」). 새 글 폼은 하나,
# 답변 폼과 답변 완료 단추는 글마다 하나다. 비교와 쓰기는 `write_guard.write_once` 가
# 한다 — 더블클릭은 두 회차의 콜백이 겹쳐 와 세션 칸 비교만으로는 둘 다 지났다. 지운 글은
# 다시 그리지 않으므로 세대 대신 지운 글 id 를 적는다.
POST_FORM_GENERATION_KEY = "voc_post_form_generation"
REPLY_GENERATION_KEY = "voc_reply_generation"
RESOLVE_GENERATION_KEY = "voc_resolve_generation"
DELETE_HANDLED_KEY = "voc_delete_handled"
POSTED_MESSAGE = "글을 올렸습니다."
REPLIED_MESSAGE = "답변을 남겼습니다."

render_page_header("VOC")
render_page_guide("voc", title="VOC")

# 알림은 **늘 서 있는 한 칸** 안에 그린다(`render_flash` 가 세운다). 알림이 생기거나 사라질 때 아래
# 형제가 한 칸 밀리면, 알림 없는 회차와 알림 있는 회차 사이에서 key 있는 글 상자가 옛 자리에 회색
# 사본으로 남아 — 적은 답변까지 든 채로 — 새로고침 전까지 Admin·HOME 에도 따라왔다(2026-10-05 E2E,
# 답변 0 인 글에 첫 답변을 남길 때). 가용설비 현황과 같은 까닭이다. 지운 글 칸도 같은 칸에 그린다.
notices = render_flash(FLASH_KEY)
gone = st.session_state.pop(GONE_NOTICE_KEY, None)
if isinstance(gone, tuple) and len(gone) == 2:
    gone_message, kept_reply = gone
    notices.warning(str(gone_message), icon=":material/delete_forever:")
    # 적어 둔 답변은 버리지 않는다 — 답변 칸은 글과 함께 사라지므로 여기서 복사해 갈 수 있게 둔다.
    if str(kept_reply).strip():
        notices.caption("적어 둔 답변")
        notices.code(str(kept_reply), language=None, wrap_lines=True)

database_path = str(DUCKDB_PATH.resolve())
try:
    repository = get_scenario_repository(database_path)
    posts = repository.list_voc_posts()
    replies = repository.list_voc_replies()
except BOOTSTRAP_ERRORS as exc:
    st.error(bootstrap_error_message(exc))
    st.stop()

replies_by_post: dict[str, pd.DataFrame] = (
    {str(key): frame for key, frame in replies.groupby("post_id", sort=False)}
    if not replies.empty
    else {}
)


def _timestamp(value: object) -> str:
    """DuckDB 가 돌려준 시각 한 칸. 결측이면 대시 하나로 둔다."""
    moment = pd.Timestamp(cast(Any, value))
    if pd.isna(moment):
        return "-"
    return f"{moment:%Y-%m-%d %H:%M}"


def _author_value() -> str:
    return str(st.session_state.get(AUTHOR_KEY, "")).strip()


def _text(key: str) -> str:
    """콜백이 읽는 입력 칸 값. 아직 한 번도 그리지 않은 칸은 빈 글로 본다."""
    value = st.session_state.get(key)
    return value if isinstance(value, str) else ""


def _with_generation(key: str, generation: int) -> str:
    """세대 0 은 원래 key 그대로다 — 처음 그린 화면의 key 는 바뀌지 않는다."""
    return key if generation == 0 else f"{key}__g{generation}"


# 쓰기(새 글·답변·답변 완료 표시·글 삭제)는 모두 **콜백**이다. 본문에서 쓰고 `st.rerun()` 하면
# 끊긴 회차가 아직 그리지 않은 아래 글의 위젯 값을 버린다 — 체크해 둔 「삭제 확인」은 체크된 채
# 보이는데 「글 삭제」 단추가 사라졌다(AGENTS 9장). 콜백은 본문보다 먼저 돌아 새 글·답글·알림이
# 그 회차에 바로 선다.
#
# 단추를 그린 회차의 세대를 인자로 받아 지금 세대와 다르면 쓰지도 알리지도 않는다. 옛 화면의 누름도
# 콜백에 닿고(Streamlit 은 지나간 위젯의 콜백 정보를 지우지 않는다), key 가 같으면 새로 그린 단추의
# 인자로 불려 방금 남긴 글을 또 남기거나 방금 바꾼 답변 완료를 되돌린다. 같은 세대의
# 누름이 두 회차에 겹쳐 오는 더블클릭은 `write_once` 가 세대마다 한 번만 쓴다 — 입력은
# 그 앞에서 읽어 두고, 세대 올리기는 뒷정리의 맨 끝이다(그 앞에서 끊긴 콜백의 뒷정리를
# 겹쳐 온 콜백이 잇는다).


def _submit_post(database_path: str, generation: int) -> None:
    """「글 올리기」 콜백. 거절(작성자 빈칸 등)되면 문구만 남기고 적은 제목·내용은 둔다.

    세대가 다르면 이미 올린 폼의 제출이 한 번 더 들어온 것(빠른 두 번 누름)이다. 옛 화면이 함께
    보낸 제목·내용은 이미 올린 글이라 다시 비우기만 한다. 방금(`write_guard.just_written`) 올린
    뒤라면 성공도 다시 알린다 — 앞 회차가 꺼내 그린 알림을 이 회차가 지운다.
    """
    category = _text(POST_CATEGORY_KEY)
    title = _text(POST_TITLE_KEY)
    body = _text(POST_BODY_KEY)
    author = _author_value()
    if not title.strip() and not body.strip() and just_written(POST_FORM_GENERATION_KEY):
        # 느린 두 번 누름의 꼬리 — 둘째 누름이 방금 비운 새 폼에 닿았다(write_guard.just_written).
        queue_flash(FLASH_KEY, POSTED_MESSAGE)
        return
    try:
        repository = get_scenario_repository(database_path)
        written = write_once(
            POST_FORM_GENERATION_KEY,
            generation,
            lambda: repository.create_voc_post(
                category=category, title=title, body=body, author=author
            ),
        )
    except BOOTSTRAP_ERRORS as exc:
        queue_flash(POST_FORM_ERROR_KEY, bootstrap_error_message(exc), kind="error")
        return
    if not written:
        st.session_state[POST_TITLE_KEY] = ""
        st.session_state[POST_BODY_KEY] = ""
        if just_written(POST_FORM_GENERATION_KEY):
            # 아주 빠른 두 번 누름의 둘째 — 옛 화면의 단추가 닿았다(write_guard).
            queue_flash(FLASH_KEY, POSTED_MESSAGE)
        return
    queue_flash(FLASH_KEY, POSTED_MESSAGE)
    st.session_state[POST_TITLE_KEY] = ""
    st.session_state[POST_BODY_KEY] = ""
    st.session_state[POST_FORM_GENERATION_KEY] = generation + 1


def _submit_reply(database_path: str, post_id: str, generation: int) -> None:
    """「답변 남기기」 콜백. 새 글 폼과 같이 거절되면 적은 답변을 두고, 남기면 비운다."""
    reply_key = f"{REPLY_BODY_KEY}_{post_id}"
    generation_key = f"{REPLY_GENERATION_KEY}_{post_id}"
    body = _text(reply_key)
    author = _author_value()
    if not body.strip() and just_written(generation_key):
        # 느린 두 번 누름의 꼬리 — 둘째 누름이 방금 비운 새 답변 폼에 닿았다.
        queue_flash(FLASH_KEY, REPLIED_MESSAGE)
        return
    try:
        repository = get_scenario_repository(database_path)
        written = write_once(
            generation_key,
            generation,
            lambda: repository.create_voc_reply(post_id=post_id, body=body, author=author),
        )
    except VocPostGoneError as exc:
        st.session_state[GONE_NOTICE_KEY] = (str(exc), body)
        return
    except BOOTSTRAP_ERRORS as exc:
        queue_flash(f"{POST_ERROR_KEY}_{post_id}", bootstrap_error_message(exc), kind="error")
        return
    if not written:
        st.session_state[reply_key] = ""
        if just_written(generation_key):
            # 아주 빠른 두 번 누름의 둘째 — 옛 화면의 단추가 닿았다(write_guard).
            queue_flash(FLASH_KEY, REPLIED_MESSAGE)
        return
    queue_flash(FLASH_KEY, REPLIED_MESSAGE)
    st.session_state[reply_key] = ""
    st.session_state[generation_key] = generation + 1


def _set_resolved(database_path: str, post_id: str, resolved: bool, generation: int) -> None:
    """「답변 완료로 표시」·「미답변으로 되돌리기」 콜백."""
    generation_key = f"{RESOLVE_GENERATION_KEY}_{post_id}"
    try:
        repository = get_scenario_repository(database_path)
        written = write_once(
            generation_key,
            generation,
            lambda: repository.set_voc_post_resolved(post_id, resolved=resolved),
        )
    except VocPostGoneError as exc:
        st.session_state[GONE_NOTICE_KEY] = (str(exc), "")
        return
    except BOOTSTRAP_ERRORS as exc:
        queue_flash(f"{POST_ERROR_KEY}_{post_id}", bootstrap_error_message(exc), kind="error")
        return
    if written:
        st.session_state[generation_key] = generation + 1


def _delete_post(database_path: str, post_id: str, reply_count: int) -> None:
    """「글 삭제」 콜백. `reply_count` 는 단추를 그린 회차에 센 답글 수다 — 지운 뒤에는 셀 수 없다.

    이 세션이 이미 지운 글의 누름이 한 번 더 들어오면 쓰지 않는다. 지운 글 id 는 위젯이 아닌 세션
    칸에 적는다 — 옛 화면은 체크한 확인 칸 값을 함께 보낸다. 방금 지운 뒤의 누름(아주 빠른 두 번
    누름의 둘째)이면 머리 알림 칸이 쓰기 직후 적어 둔 알림을 다시 그린다(`flash.render_flash` —
    `write_guard.note_notice`) — 앞 회차가 꺼내 그린 알림을 이 회차가 지우지 않는다.
    """
    if st.session_state.get(DELETE_HANDLED_KEY) == post_id:
        return
    if not st.session_state.get(f"{DELETE_CONFIRM_KEY}_{post_id}"):
        return
    message = "글을 지웠습니다." if not reply_count else f"글과 답글 {reply_count}건을 지웠습니다."
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    marks = notice_marks()
    try:
        get_scenario_repository(database_path).remove_voc_post(post_id)
    except BOOTSTRAP_ERRORS as exc:
        queue_flash(f"{POST_ERROR_KEY}_{post_id}", bootstrap_error_message(exc), kind="error")
        return
    note_notice(marks, FLASH_KEY, message)
    st.session_state[DELETE_HANDLED_KEY] = post_id
    queue_flash(FLASH_KEY, message)


with st.container(border=True):
    st.markdown("#### :material/edit_note: 새 글 쓰기")
    # 이름은 폼 **밖**이다. 폼 안에 두면 글을 올릴 때마다 함께 지워져 매번 다시 적어야 한다.
    # 다른 화면에 갔다 와도 남는다(`persist_state`) — 그리지 않은 회차에 Streamlit 이 값을 버려
    # 돌아오면 빈 칸이었고, 글을 올리면 「작성자를 입력하세요.」로 막혔다(2026-10-01 브라우저 점검).
    st.text_input(
        "작성자",
        key=AUTHOR_KEY,
        persist_state="session",
        placeholder="예: 홍길동 / 제조기술",
        max_chars=40,
        help="이 앱에는 로그인이 없습니다. 답을 돌려줄 수 있을 만큼만 적어 주세요.",
    )
    # `clear_on_submit` 을 쓰지 않는다. 그것은 **거절된 제출**(작성자 빈칸 등)에도 제목·내용을
    # 지워, 4000자까지 적은 글이 되돌릴 길 없이 사라졌다(2026-10-05 E2E). 콜백이 올리기에 성공한
    # 때만 비운다.
    post_generation = current_generation(POST_FORM_GENERATION_KEY)
    with st.form(_with_generation(POST_FORM_KEY, post_generation)):
        category_column, title_column = st.columns([1, 3])
        with category_column:
            st.selectbox("분류", options=VOC_CATEGORIES, key=POST_CATEGORY_KEY)
        with title_column:
            st.text_input(
                "제목", placeholder="한 줄로 요약해 주세요", max_chars=120, key=POST_TITLE_KEY
            )
        st.text_area(
            "내용",
            height=140,
            placeholder="어떤 화면에서 무엇을 하려다 무엇이 막혔는지 적어 주시면 답이 빨라집니다.",
            max_chars=4000,
            key=POST_BODY_KEY,
        )
        st.form_submit_button(
            "글 올리기",
            icon=":material/send:",
            type="primary",
            width="stretch",
            on_click=_submit_post,
            args=(database_path, post_generation),
        )
    render_flash(POST_FORM_ERROR_KEY)

st.divider()

# 글 목록을 거르는 조건은 사이드바 조건 카드다(2026-09-29 사용자 결정 — 필터는 사이드바).
with condition_card("VOC 필터", name="voc", icon=":material/filter_alt:"):
    st.multiselect(
        "분류",
        options=VOC_CATEGORIES,
        key=CATEGORY_FILTER_KEY,
        persist_state="session",
        placeholder="미선택 시 전체",
    )
    st.text_input(
        "검색",
        key=SEARCH_KEY,
        persist_state="session",
        placeholder="제목·내용·작성자",
    )
    st.toggle("미답변만", key=OPEN_ONLY_KEY, persist_state="session")

visible = posts.copy()
selected_categories = list(st.session_state.get(CATEGORY_FILTER_KEY, []))
if selected_categories and not visible.empty:
    visible = visible.loc[visible["category"].isin(selected_categories)]
if bool(st.session_state.get(OPEN_ONLY_KEY, False)) and not visible.empty:
    visible = visible.loc[~visible["resolved"].astype(bool)]
keyword = str(st.session_state.get(SEARCH_KEY, "")).strip()
if keyword and not visible.empty:
    haystack = (
        visible["title"].astype("string").fillna("")
        + "\n"
        + visible["body"].astype("string").fillna("")
        + "\n"
        + visible["author"].astype("string").fillna("")
    )
    visible = visible.loc[haystack.str.contains(keyword, case=False, regex=False)]

open_count = 0 if posts.empty else int((~posts["resolved"].astype(bool)).sum())
st.caption(f"전체 {len(posts):,}건 · 미답변 {open_count:,}건 · 지금 보는 글 {len(visible):,}건")

if posts.empty:
    st.info("아직 올라온 글이 없습니다. 위에서 첫 글을 남겨 보세요.")
    st.stop()
if visible.empty:
    st.info("조건에 맞는 글이 없습니다.")
    st.stop()


def _render_post(row: Any) -> None:
    post_id = str(row["post_id"])
    post_replies = replies_by_post.get(post_id, replies.iloc[0:0])
    answered = bool(row["resolved"])
    state = ":green-badge[답변 완료]" if answered else ":orange-badge[미답변]"
    # 라벨은 마크다운으로 그려지므로 사람이 적은 제목·작성자만 글자 그대로 escape 한다. 분류는 고정
    # 목록이고 시각·답변 수는 코드가 만든다.
    summary = (
        f"[{row['category']}] {literal_markdown(row['title'])} · "
        f"{literal_markdown(row['author'])} · "
        f"{_timestamp(row['created_at'])} · 답변 {len(post_replies)}"
    )
    # 편 글은 답변을 남긴 뒤에도 편 채로 둔다. 라벨의 답변 수가 바뀌면 `key` 없는 상자는 새로
    # 만들어져 접혔다 — 「답변 완료로 표시」를 누르려면 다시 펴야 했다(2026-10-01 브라우저 점검).
    with remembered_expander(summary, key=f"{POST_EXPANDER_KEY}_{post_id}"):
        st.markdown(state)
        # `st.markdown` 이 아니라 `st.text` 다. 사용자가 적는 자유 글이라 `#`·`-`·`*` 가
        # 제목과 목록으로 바뀌면 쓴 사람이 의도하지 않은 모양이 된다.
        st.text(str(row["body"]))
        # 답글 목록도 늘 서 있는 한 칸이다 — 첫 답변이 달릴 때 아래 답변 폼(key 있는 칸)의 자리가
        # 밀리지 않게 한다(위 알림 칸과 같은 까닭).
        with st.container():
            if not post_replies.empty:
                st.divider()
                for _, reply in post_replies.iterrows():
                    with st.chat_message("assistant", avatar=":material/reply:"):
                        st.caption(
                            f"{literal_markdown(reply['author'])} · "
                            f"{_timestamp(reply['created_at'])}"
                        )
                        st.text(str(reply["body"]))
        # 새 글 폼과 같이 콜백이 남기기에 성공한 때만 비운다 — 거절된 답변이 지워지면 다시 적어야
        # 한다.
        reply_generation = current_generation(f"{REPLY_GENERATION_KEY}_{post_id}")
        with st.form(_with_generation(f"{REPLY_FORM_KEY}_{post_id}", reply_generation)):
            st.text_area(
                "답변",
                height=100,
                placeholder="답변을 적어 주세요.",
                max_chars=4000,
                key=f"{REPLY_BODY_KEY}_{post_id}",
            )
            st.form_submit_button(
                "답변 남기기",
                icon=":material/reply:",
                type="primary",
                on_click=_submit_reply,
                args=(database_path, post_id, reply_generation),
            )
        # 실패 문구 칸은 늘 선다 — 생기고 빠져도 아래 단추 줄의 자리가 그대로다.
        render_flash(f"{POST_ERROR_KEY}_{post_id}")
        resolve_generation = current_generation(f"{RESOLVE_GENERATION_KEY}_{post_id}")
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.button(
                "답변 완료로 표시" if not answered else "미답변으로 되돌리기",
                key=_with_generation(f"{RESOLVE_KEY}_{post_id}", resolve_generation),
                icon=":material/task_alt:",
                on_click=_set_resolved,
                args=(database_path, post_id, not answered, resolve_generation),
            )
            # 지우기는 확인을 한 단계 둔다. 글 하나가 사라지면 답글도 함께 사라진다.
            # 가로 줄 안의 checkbox 는 기본이 `wrap=False` 라 긴 라벨이 말줄임으로 잘린다.
            # 잘리는 뒷부분이 바로 경고라 여기서는 접어서라도 보여야 한다.
            if st.checkbox(
                "삭제 확인 · 답글까지 함께 사라지며 되돌릴 수 없습니다",
                key=f"{DELETE_CONFIRM_KEY}_{post_id}",
                wrap=True,
            ):
                st.button(
                    "글 삭제",
                    key=f"{DELETE_KEY}_{post_id}",
                    icon=":material/delete:",
                    on_click=_delete_post,
                    args=(database_path, post_id, len(post_replies)),
                )


for _, post_row in visible.iterrows():
    _render_post(post_row)
