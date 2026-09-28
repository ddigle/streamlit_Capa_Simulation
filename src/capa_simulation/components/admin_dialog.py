# Purpose: Admin Area 편집 탭들이 함께 쓰는 팝업 열림 상태(페이지에 한 칸)를 여닫는다.

"""Admin Area 의 팝업 한 칸.

탭(`Proc Rename`·`표시순서 관리`)은 닫혀 있어도 매 회차 그린다(폼 입력 보존). 그래서 두 탭이
각자 팝업 칸을 두면 한 회차에 팝업이 둘 뜰 수 있다 — 칸은 하나이고 **값**(어느 팝업인가)이
가른다. 키는 `PAGE_DIALOG_SUFFIX` 로 끝나 페이지를 떠나면 `forget_page_dialogs` 가 비운다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.page_bootstrap import PAGE_DIALOG_SUFFIX

ADMIN_DIALOG_KEY = f"admin_area{PAGE_DIALOG_SUFFIX}"


def open_admin_dialog(name: str) -> None:
    """여는 버튼의 콜백. 콜백은 스크립트보다 먼저 돌아 한 회차에 팝업이 하나로 정해진다."""
    st.session_state[ADMIN_DIALOG_KEY] = name


def close_admin_dialog() -> None:
    st.session_state.pop(ADMIN_DIALOG_KEY, None)


def admin_dialog_is_open(name: str) -> bool:
    return st.session_state.get(ADMIN_DIALOG_KEY) == name
