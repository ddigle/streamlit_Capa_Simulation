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

from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.services.voc_board import VOC_CATEGORIES
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
CATEGORY_FILTER_KEY = "voc_category_filter"
OPEN_ONLY_KEY = "voc_open_only"
SEARCH_KEY = "voc_search"
FLASH_KEY = "voc_flash"
POST_TITLE_KEY = "voc_post_title"
POST_BODY_KEY = "voc_post_body"
# 올리기에 **성공한 뒤에만** 폼을 비운다는 표지. 위젯을 그린 회차에는 그 값을 바꿀 수 없으므로
# 다음 회차 위젯 앞에서 빈 값을 적는다. 답변 폼은 글 번호를 붙인 칸이다.
POST_CLEAR_KEY = "voc_post_clear"
REPLY_CLEAR_KEY = "voc_reply_clear"

render_page_header("VOC")
render_page_guide("voc", title="VOC")

flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    st.success(flash)

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
    # 지워, 4000자까지 적은 글이 되돌릴 길 없이 사라졌다(2026-10-05 E2E). 성공한 뒤에만 비운다.
    if st.session_state.pop(POST_CLEAR_KEY, False):
        st.session_state[POST_TITLE_KEY] = ""
        st.session_state[POST_BODY_KEY] = ""
    with st.form("voc_post_form"):
        category_column, title_column = st.columns([1, 3])
        with category_column:
            category = st.selectbox("분류", options=VOC_CATEGORIES)
        with title_column:
            title = st.text_input(
                "제목", placeholder="한 줄로 요약해 주세요", max_chars=120, key=POST_TITLE_KEY
            )
        body = st.text_area(
            "내용",
            height=140,
            placeholder="어떤 화면에서 무엇을 하려다 무엇이 막혔는지 적어 주시면 답이 빨라집니다.",
            max_chars=4000,
            key=POST_BODY_KEY,
        )
        submitted = st.form_submit_button(
            "글 올리기", icon=":material/send:", type="primary", width="stretch"
        )
    if submitted:
        try:
            repository.create_voc_post(
                category=str(category),
                title=title,
                body=body,
                author=_author_value(),
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state[FLASH_KEY] = "글을 올렸습니다."
            st.session_state[POST_CLEAR_KEY] = True
            st.rerun()

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
    summary = (
        f"[{row['category']}] {row['title']} · {row['author']} · "
        f"{_timestamp(row['created_at'])} · 답변 {len(post_replies)}"
    )
    # 편 글은 답변을 남긴 뒤에도 편 채로 둔다. 라벨의 답변 수가 바뀌면 `key` 없는 상자는 새로
    # 만들어져 접혔다 — 「답변 완료로 표시」를 누르려면 다시 펴야 했다(2026-10-01 브라우저 점검).
    with remembered_expander(summary, key=f"{POST_EXPANDER_KEY}_{post_id}"):
        st.markdown(state)
        # `st.markdown` 이 아니라 `st.text` 다. 사용자가 적는 자유 글이라 `#`·`-`·`*` 가
        # 제목과 목록으로 바뀌면 쓴 사람이 의도하지 않은 모양이 된다.
        st.text(str(row["body"]))
        if not post_replies.empty:
            st.divider()
            for _, reply in post_replies.iterrows():
                with st.chat_message("assistant", avatar=":material/reply:"):
                    st.caption(f"{reply['author']} · {_timestamp(reply['created_at'])}")
                    st.text(str(reply["body"]))
        # 새 글 폼과 같이 성공한 뒤에만 비운다 — 거절된 답변이 지워지면 다시 적어야 한다.
        reply_key = f"{REPLY_BODY_KEY}_{post_id}"
        if st.session_state.pop(f"{REPLY_CLEAR_KEY}_{post_id}", False):
            st.session_state[reply_key] = ""
        with st.form(f"{REPLY_FORM_KEY}_{post_id}"):
            reply_body = st.text_area(
                "답변",
                height=100,
                placeholder="답변을 적어 주세요.",
                max_chars=4000,
                key=reply_key,
            )
            reply_submitted = st.form_submit_button(
                "답변 남기기", icon=":material/reply:", type="primary"
            )
        if reply_submitted:
            try:
                repository.create_voc_reply(
                    post_id=post_id,
                    body=reply_body,
                    author=_author_value(),
                )
            except BOOTSTRAP_ERRORS as exc:
                st.error(bootstrap_error_message(exc))
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[FLASH_KEY] = "답변을 남겼습니다."
                st.session_state[f"{REPLY_CLEAR_KEY}_{post_id}"] = True
                st.rerun()
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            if st.button(
                "답변 완료로 표시" if not answered else "미답변으로 되돌리기",
                key=f"{RESOLVE_KEY}_{post_id}",
                icon=":material/task_alt:",
            ):
                repository.set_voc_post_resolved(post_id, resolved=not answered)
                st.rerun()
            # 지우기는 확인을 한 단계 둔다. 글 하나가 사라지면 답글도 함께 사라진다.
            # 가로 줄 안의 checkbox 는 기본이 `wrap=False` 라 긴 라벨이 말줄임으로 잘린다.
            # 잘리는 뒷부분이 바로 경고라 여기서는 접어서라도 보여야 한다.
            if st.checkbox(
                "삭제 확인 · 답글까지 함께 사라지며 되돌릴 수 없습니다",
                key=f"{DELETE_CONFIRM_KEY}_{post_id}",
                wrap=True,
            ) and st.button(
                "글 삭제",
                key=f"{DELETE_KEY}_{post_id}",
                icon=":material/delete:",
            ):
                # 지워진 뒤에는 셀 수 없다. 화면용 프레임으로 먼저 센다.
                deleted_replies = len(post_replies)
                repository.remove_voc_post(post_id)
                st.session_state[FLASH_KEY] = (
                    "글을 지웠습니다."
                    if not deleted_replies
                    else f"글과 답글 {deleted_replies}건을 지웠습니다."
                )
                st.rerun()


for _, post_row in visible.iterrows():
    _render_post(post_row)
