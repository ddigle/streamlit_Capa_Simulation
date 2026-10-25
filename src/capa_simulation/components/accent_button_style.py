# Purpose: 강조색으로 칠한 Streamlit 단추의 글자색을 테마의 강조 면 위 글자색으로 맞춘다.

"""강조색으로 칠한 단추의 글자색(`docs/design_system.md` 2-2).

Streamlit 1.63 은 `type="primary"` 단추(`st.button`·`st.download_button`·`st.popover`·
`st.form_submit_button`)를 강조색(`primaryColor` — 토큰 `ACCENT`)으로 칠하고 글자를 늘 흰색으로
쓴다 — 글자색을 정하는 테마 칸이 없다. 밝은 테마의 강조색 위 흰 글자는 5.47:1 이지만, 어두운
테마의 강조색(어두운 면에서 읽히게 밝게 올린 값) 위 흰 글자는 1.86:1 이다. 그래서 강조 면 위
글자색 토큰(`tokens.ACCENT_TEXT` — 밝게는 흰색 그대로, 어둡게는 페이지 바탕색)을 앱 전체의 그
단추에 다시 건다. 밝은 테마는 Streamlit 이 그리던 그대로다.

- 잠긴 단추는 건드리지 않는다 — Streamlit 이 투명 바탕에 흐린 글자로 그린다.
- 올려 놓기·누름·키보드 초점은 바탕만 바뀌고 글자색은 그대로라 상태별 규칙을 두지 않는다.
- 링크 단추(`st.link_button`)는 이 앱이 쓰지 않는다.

테마는 그 회차의 `theme.current_mode()` 다 — `app.py` 가 `theme.begin_run()` 뒤, 부트스트랩
앞에서 매 회차 한 번 부른다(빠진 회차에는 규칙이 사라지고, 부트스트랩 오류 화면의 단추도 같은
색으로 선다). 스타일만 든 `st.html` 이라 이벤트 칸에 서고 본문 자리를 먹지 않는다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.design import tokens

__all__ = ["ACCENT_BUTTON_SELECTORS", "accent_button_style", "render_accent_button_style"]

# 강조색으로 칠한 단추 — 보통 단추는 `kind="primary"`, 폼 제출 단추는
# `kind="primaryFormSubmit"` 이다.
ACCENT_BUTTON_SELECTORS = (
    'button[kind="primary"]:not(:disabled)',
    'button[kind="primaryFormSubmit"]:not(:disabled)',
)


def accent_button_style() -> str:
    """지금 회차 테마의 강조 면 위 글자색을 칠한 단추에 거는 `<style>`."""
    selectors = ", ".join(ACCENT_BUTTON_SELECTORS)
    return f"<style>{selectors} {{ color: {tokens.ACCENT_TEXT}; }}</style>"


def render_accent_button_style() -> None:
    """`accent_button_style()` 를 보낸다(스타일만 든 `st.html`)."""
    st.html(accent_button_style())
