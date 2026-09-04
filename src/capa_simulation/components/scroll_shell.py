# Purpose: 가로로 스크롤하는 영역과 그 안의 고정 폭 캔버스를 만드는 공통 셸을 제공한다.

"""Shared horizontal scroll shell for wide Plotly content.

월별 표 2종·HOME 대시보드·재공 현황이 각자 같은 CSS 와 컨테이너 중첩을 복제하고 있었다.
바깥 상자가 `overflow-x: auto` 로 스크롤을 받고, 안쪽 캔버스가 내용 폭을 px 로 강제해
Streamlit 컬럼 폭보다 넓은 Figure 를 그대로 눕히는 구조다.

네이티브 스크롤바를 숨길지는 호출자가 정한다. 숨기는 화면은 `horizontal_scrollbar`
컴포넌트로 대체해 표 위쪽에 스크롤바를 올린다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st
from streamlit.elements.lib.layout_utils import Gap


def _scroll_box_rules(
    key: str,
    *,
    hide_native_scrollbar: bool,
    padding_bottom: str | None,
) -> str:
    rules = [
        f".st-key-{key}_scroll {{",
        "    overflow-x: auto;",
        "    overflow-y: hidden;",
    ]
    if padding_bottom is not None:
        rules.append(f"    padding-bottom: {padding_bottom};")
    if hide_native_scrollbar:
        rules += [
            "    scrollbar-width: none !important;",
            "    -ms-overflow-style: none;",
            "}",
            f".st-key-{key}_scroll::-webkit-scrollbar {{",
            "    width: 0 !important;",
            "    height: 0 !important;",
            "    display: none !important;",
        ]
    rules.append("}")
    return "\n".join(rules)


def _canvas_rules(key: str, content_width_px: float) -> str:
    return "\n".join(
        [
            f".st-key-{key}_canvas {{",
            f"    width: {content_width_px}px !important;",
            f"    min-width: {content_width_px}px !important;",
            "    max-width: none !important;",
            "}",
        ]
    )


def scroll_shell_style(
    key: str,
    *,
    content_width_px: float,
    hide_native_scrollbar: bool,
    padding_bottom: str | None = None,
) -> str:
    """셸이 주입할 `<style>` 문자열을 만든다. 테스트가 규칙을 직접 검사할 수 있게 분리한다."""
    box = _scroll_box_rules(
        key,
        hide_native_scrollbar=hide_native_scrollbar,
        padding_bottom=padding_bottom,
    )
    return f"<style>\n{box}\n{_canvas_rules(key, content_width_px)}\n</style>"


@contextmanager
def horizontal_scroll_canvas(
    *,
    key: str,
    content_width_px: float,
    hide_native_scrollbar: bool,
    padding_bottom: str | None = None,
    # Streamlit 의 st.container 기본값과 같게 둔다. 호출부가 넘기지 않아도 동작이 바뀌지
    # 않아야 한다.
    gap: Gap | None = "small",
) -> Iterator[None]:
    """`{key}_scroll` 스크롤 상자와 `{key}_canvas` 고정 폭 캔버스를 열고 안을 채우게 한다.

    `key` 는 기존 DOM 클래스를 그대로 쓰기 위한 접두어다. Streamlit 은 컨테이너 key 를
    `.st-key-<key>` 클래스로 내보내므로 이 이름이 바뀌면 붙어 있던 CSS 가 끊어진다.
    """
    st.html(
        scroll_shell_style(
            key,
            content_width_px=content_width_px,
            hide_native_scrollbar=hide_native_scrollbar,
            padding_bottom=padding_bottom,
        )
    )
    with st.container(key=f"{key}_scroll"):
        with st.container(key=f"{key}_canvas", gap=gap):
            yield
