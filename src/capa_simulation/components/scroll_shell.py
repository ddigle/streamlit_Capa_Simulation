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


def split_scroll_columns_style(
    *,
    label_key: str,
    month_key: str,
    label_width_px: float,
) -> str:
    """고정 라벨 컬럼과 남는 폭을 채우는 월 컬럼의 폭을 CSS 로 못박는다.

    `st.columns` 의 인자는 **비율**이라 컨테이너 폭에 비례해 늘고 준다. 그런데 라벨 폭은
    분류 컬럼 픽셀 폭의 합으로 계산한 **px** 값이어서, 창이 설계 폭보다 좁으면 라벨 컬럼도
    함께 줄고 분류 이름과 구획 제목이 잘린다. 1280px 창의 HOME 에서 라벨 컬럼이 149px 로
    줄어 "Capa LOB 현황" 이 잘리는 것이 그 예다. 반대로 조회 월이 두세 달뿐이면 비율이
    커져 라벨 컬럼이 필요 이상으로 넓어진다.

    라벨 컬럼을 px 로 고정하고 월 컬럼이 나머지를 가져가게 한다. 월 영역은 어차피 가로로
    스크롤하므로 좁아져도 내용이 잘리지 않는다.
    """
    return "\n".join(
        [
            "<style>",
            f'[data-testid="stColumn"]:has(.st-key-{label_key}) {{',
            f"    flex: 0 0 {label_width_px}px !important;",
            f"    width: {label_width_px}px !important;",
            f"    min-width: {label_width_px}px !important;",
            "}",
            f'[data-testid="stColumn"]:has(.st-key-{month_key}) {{',
            "    flex: 1 1 0 !important;",
            "    width: auto !important;",
            "    min-width: 0 !important;",
            "}",
            "</style>",
        ]
    )


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
