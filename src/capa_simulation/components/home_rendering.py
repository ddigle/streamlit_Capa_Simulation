# Purpose: HOME Figure 세션 캐시와 화면 렌더링·성능 표시를 담당한다.

"""Session-scoped figure cache and rendering for the HOME dashboard."""

from __future__ import annotations

import html
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pandas as pd
import streamlit as st

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    DASHBOARD_PANEL_TITLE_GAP_PX,
    DASHBOARD_SECTION_GAP_PX,
    DASHBOARD_TITLE_HEIGHT_PX,
)
from capa_simulation.components.home_preference import (
    render_plan_detail_title_row,
    render_section_title_row,
)
from capa_simulation.components.loading_progress import LoadingStage
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.performance import PerformanceTrace

# 네 번째 요소는 시나리오 내용 토큰이다. 편집 카운터(`revision`)를 쓰면 내용이 달라도
# 번호가 겹쳐 예전 Figure 가 그대로 나온다. 계산 캐시와 같은 근거로 토큰을 쓴다.
# 두 번째 요소는 공용 공정 표시명 프로필 버전이다. 표시명은 계산 입력이 아니라 라벨이므로
# 계산 캐시 키(`build_home_simulation_cache_key`)에는 넣지 않고 여기에만 접어 넣는다.
# 뒤의 여섯은 화면 기준이다 — EDP 포함 여부, 계획 세부수량 거래선 분류 여부, 비교 GAP
# 표시 여부와 비교 리비전, 선행 반영 여부, 선행 물량 프로필 버전, 과거 구간 프로필 버전.
# 버전은 선행을 켰을 때만 채우므로 껐다 켜도 같은 칸을 다시 쓰지 않는다.
HomeFigureCacheKey = tuple[
    int,
    int,
    int,
    str,
    int,
    int,
    str,
    tuple[str, ...],
    float,
    float,
    bool,
    bool,
    bool,
    str,
    bool,
    int,
    bool,
    int,
    int,
    float,
    float,
    int,
]

HomeFigureSet = tuple[Any, ...]

HOME_FIGURE_CACHE_KEY = "home_dashboard_figure_cache"

# EDP 포함/제외 × 선행 ON/OFF 네 가지 상태를 사람이 오가며 비교한다. 3 칸이면 되돌릴
# 때마다 차트를 다시 조립해 2 초를 쓴다. 한 칸은 Figure 여섯 개다.
HOME_FIGURE_CACHE_MAX_ENTRIES = 8

HOME_FIGURE_SCHEMA_VERSION = 39

# 누적 퍼센트는 합성 시드 콜드 실행의 단계별 소요 시간 비율에서 잡았다. 차트 생성이
# 대부분을 쓰고 계산 파이프라인이 그 다음이다. 단계 수로 균등 분할하면 막대가 30% 까지
# 순식간에 찬 뒤 남은 구간에서 멈춰 선 것처럼 보인다.
HOME_LOADING_STAGES = (
    LoadingStage("기준정보와 활성 시나리오를 확인하는 중", 5),
    LoadingStage("Capa 를 계산하는 중", 25),
    LoadingStage("B/N 순위를 집계하는 중", 32),
    LoadingStage("차트를 그리는 중", 95),
    LoadingStage("화면에 전달하는 중", 100),
)


def home_figure_cache() -> dict[HomeFigureCacheKey, HomeFigureSet]:
    cached = st.session_state.setdefault(HOME_FIGURE_CACHE_KEY, {})
    return cast(dict[HomeFigureCacheKey, HomeFigureSet], cached)


def take_home_figures(cache_key: HomeFigureCacheKey) -> HomeFigureSet | None:
    """꺼내면서 **가장 최근에 쓴 칸**으로 옮긴다.

    dict 는 넣은 차례만 기억한다. 꺼내 쓰기만 하면 차례가 그대로여서, 칸이 넘칠 때
    `store_home_figures` 가 방금 쓴 칸을 버린다. 토글 조합은 넷이라 최대 16 가지인데 칸은
    여덟이라 축출이 실제로 일어난다.
    """
    cache = home_figure_cache()
    figures = cache.pop(cache_key, None)
    if figures is not None:
        cache[cache_key] = figures
    return figures


def store_home_figures(
    cache_key: HomeFigureCacheKey,
    figures: HomeFigureSet,
) -> None:
    cache = home_figure_cache()
    cache.pop(cache_key, None)
    cache[cache_key] = figures
    while len(cache) > HOME_FIGURE_CACHE_MAX_ENTRIES:
        cache.pop(next(iter(cache)))


def render_home_performance(
    trace: PerformanceTrace,
    *,
    cache_hit: bool,
    enabled: bool,
) -> None:
    if not enabled:
        return
    with st.sidebar.expander("HOME 실행 시간", expanded=True):
        st.caption(f"Figure 캐시: {'적중' if cache_hit else '생성'}")
        st.dataframe(
            pd.DataFrame(trace.rows()),
            hide_index=True,
            width="stretch",
        )


def dashboard_title_row_style() -> str:
    """세 구획 제목 줄과 그 짝인 빈 줄의 높이를 하나로 못박는다.

    위젯 기본 높이에 맡기면 브라우저 글꼴이나 Streamlit 판이 바뀔 때마다 두 칸이
    어긋난다. 세 제목이 같은 높이라야 제목과 표 사이 간격도 하나로 맞는다.
    """
    return f"""
    <style>
    .st-key-lob_title_row,
    .st-key-plan_detail_title_row,
    .st-key-plan_detail_title_spacer,
    .st-key-bottleneck_title_row,
    .st-key-bottleneck_title_spacer {{
        height: {DASHBOARD_TITLE_HEIGHT_PX}px;
        min-height: {DASHBOARD_TITLE_HEIGHT_PX}px;
        margin: 0;
    }}
    .st-key-lob_title_row,
    .st-key-plan_detail_title_row,
    .st-key-bottleneck_title_row {{ align-items: center; }}
    </style>
    """


SUMMARY_NOTICE_KEY = "home_summary_notice"


def summary_notice_style() -> str:
    """공지 상자를 다른 구획 제목과 같은 모양으로 맞춘다.

    `st.expander` 의 기본 제목은 본문 글씨 크기다. 그대로 두면 바로 아래 `Capa LOB 현황`
    보다 작아 두 상자가 다른 화면에서 온 것처럼 보인다. 제목 글자와 앞의 강조 막대를
    구획 제목(`section_title_markup`)과 같은 값으로 맞춘다.

    **본문은 내용만큼 자란다.** 높이를 주거나 `overflow` 를 걸면 긴 공지가 잘려 스크롤
    안에 숨는데, 공지는 접힘을 펴는 순간 전부 보여야 하는 글이다.
    """
    return f"""
    <style>
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary p {{
        font-size: 20px;
        font-weight: 700;
    }}
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary p::before {{
        content: "▍";
        color: {tokens.ACCENT};
        font-weight: 400;
    }}
    .capa-summary-note {{
        margin: 0;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        overflow: visible;
        max-height: none;
        line-height: 1.65;
        color: {tokens.TEXT};
    }}
    </style>
    """


def render_summary_notice(note: str) -> None:
    """`Main` 탭 맨 위의 공지. 접힌 채로 열리고 내용이 없으면 아예 그리지 않는다.

    **Plotly 상자 밖**이다. 안에 두면 스크롤되는 월 영역과 폭을 나눠 가져 문구가 월 칸
    너비에 갇힌다.

    기본이 접힘인 이유는 이 화면의 주인공이 대시보드이기 때문이다. 공지가 펼친 채로
    뜨면 긴 글 하나가 차트를 화면 밖으로 밀어낸다.

    `st.expander` 를 쓰는 것은 펴고 접는 데 rerun 이 필요 없어서다. 버튼으로 만들면 누를
    때마다 HOME 전체가 다시 돌고, 그 비용을 문구 하나를 여닫는 데 치르게 된다.
    """
    if not note.strip():
        return
    st.html(summary_notice_style())
    with st.container(key=SUMMARY_NOTICE_KEY):
        with st.expander("Summary", expanded=False):
            # `st.markdown` 이 아니라 `st.html` 이다. 마크다운은 raw HTML 블록을
            # **빈 줄에서 끊으므로**(CommonMark block type 6), 문단을 나눈 공지의 둘째
            # 문단부터는 `<div>` 밖으로 나가 줄 앞의 `#`·`-` 가 제목과 목록으로 바뀐다.
            # `st.html` 은 파서를 거치지 않는다. `pre-wrap` 이 줄바꿈과 들여쓰기를 살리고
            # `html.escape` 가 태그를 막는다.
            st.html(f'<div class="capa-summary-note">{html.escape(note)}</div>')


@contextmanager
def home_dashboard_panel() -> Iterator[None]:
    """`Capa LOB 현황` 제목 줄과 여섯 Figure 를 함께 감싸는 테두리 상자.

    상자를 `render_home_figures` 안에서 열면 제목 줄만 상자 밖에 남는다. 그렇다고 제목
    줄을 그 함수 안으로 옮길 수는 없다 — 옆의 「선행」·「GAP」 토글은 숨은 탭에서도
    그려져야 하는데(그리지 않으면 값이 날아간다) 그 함수는 숨은 탭에서 통째로 건너뛴다.
    그래서 상자만 한 단계 위로 올리고 제목 줄과 Figure 를 나란히 받는다.

    `gap` 이 `DASHBOARD_SECTION_GAP_PX` 가 아닌 이유는 상수 주석에 적었다 — 라벨 캔버스가
    스크롤바 높이만큼 이미 내려와 있어 남는 몫만 여기서 준다.
    """
    st.html(dashboard_title_row_style())
    with st.container(border=True, key="home_dashboard_panel", gap=DASHBOARD_PANEL_TITLE_GAP_PX):
        yield


@st.fragment
def render_home_figures(
    figures: HomeFigureSet,
    month_labels: list[str],
    *,
    applied_plan_detail_customer: bool = False,
    leading_past_month_count: int = 0,
    owner_tab: OpenTab | None = None,
) -> None:
    """대시보드 여섯 Figure. **숨은 탭에서는 그리지 않는다.**

    숨겨진 요소 안에서는 SVG 글자 폭 측정이 0 이라 `go.Table` 이 머리글을 셀 가운데에
    놓지 못하고, 상세 세 Figure 는 `staticPlot` 이라 탭을 열어도 다시 그리지 않는다.
    어긋난 머리글이 그대로 남는다.

    여기서 건너뛰는 위젯은 「상세」 토글 하나뿐이고 `persist_state="session"` 이라 값이
    살아남는다. 선행·GAP 토글은 이 함수 밖이라 숨어도 계속 그려진다 — 테두리 상자는
    `home_dashboard_panel()` 이 한 단계 위에서 열어 그 제목 줄까지 함께 감싼다.
    """
    if tab_is_hidden(owner_tab):
        return
    if len(figures) != 6:
        raise ValueError("HOME Figure 묶음은 요약 2개와 상세 4개, 모두 6개여야 합니다.")
    label_figure, month_figure = figures[:2]
    detail_figures = figures[2:]
    visible_month_count = min(max(len(month_labels), 1), tokens.DASHBOARD_MONTH_SCROLL_THRESHOLD)

    # 구분 컬럼은 px 로 고정한다. 비율로 두면 창이 좁을 때 구획 제목이 잘리고, 조회
    # 월이 적을 때는 반대로 필요 이상 넓어진다. 비율은 CSS 적용 전 첫 그리기용이다.
    st.html(
        split_scroll_columns_style(
            label_key="production_lob_label_canvas",
            month_key="production_lob_month_region",
            label_width_px=DASHBOARD_LABEL_COLUMN_WIDTH_PX,
        )
    )
    label_column, month_column = st.columns(
        [
            DASHBOARD_LABEL_COLUMN_WIDTH_PX,
            visible_month_count * tokens.MONTH_COLUMN_WIDTH_PX,
        ],
        gap=None,
    )
    with label_column:
        with st.container(
            key="production_lob_label_canvas",
            gap=DASHBOARD_SECTION_GAP_PX,
        ):
            st.plotly_chart(
                label_figure,
                width="stretch",
                key="production_lob_labels",
                config={"displayModeBar": False, "staticPlot": True},
            )
            # `계획 세부수량` 제목과 「상세」 토글. 제목이 Plotly 주석으로 쓰던 자리를
            # 그대로 받는다. 월 칸에도 같은 높이의 빈 줄을 끼워야 행이 맞는다.
            render_plan_detail_title_row(applied_customer=applied_plan_detail_customer)
            st.plotly_chart(
                detail_figures[0],
                width="stretch",
                key="production_detail_labels",
                config={"displayModeBar": False, "staticPlot": True},
            )
            # `상세 B/N 공정` 제목. 앞의 두 구획과 같은 줄 컴포넌트라 제목과 표
            # 사이 간격이 셋 다 같다.
            render_section_title_row("상세 B/N 공정", key="bottleneck_title_row")
            st.plotly_chart(
                detail_figures[2],
                width="stretch",
                key="bottleneck_detail_labels",
                config={"displayModeBar": False, "staticPlot": True},
            )
    with month_column:
        # 라벨 영역은 월 영역 위에 얹힌 스크롤바 높이만큼 내려야 행이 맞는다.
        # 아래 `render_horizontal_scrollbar` 와 **반드시 같은 값**을 읽는다.
        st.html(
            f"""
            <style>
            .st-key-production_lob_label_canvas {{
                padding-top: {tokens.SCROLLBAR_HEIGHT_PX}px;
            }}
            </style>
            """
        )
        with st.container(key="production_lob_month_region", gap=None):
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=".st-key-production_lob_month_scroll",
                height=tokens.SCROLLBAR_HEIGHT_PX,
                key="production_lob_custom_scrollbar",
                # 화면을 열면 **DB 계산 구간의 첫 달**이 왼쪽에 선다. 과거 구간은 앞에
                # 붙어 있으므로 그 칸 수만큼 지나야 한다 — 왼쪽 끝은 지난 이력이라
                # 화면을 열자마자 보이는 것이 계획이 아니게 된다.
                initial_offset_px=leading_past_month_count * tokens.MONTH_COLUMN_WIDTH_PX,
            )
            with horizontal_scroll_canvas(
                key="production_lob_month",
                content_width_px=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
                hide_native_scrollbar=True,
                padding_bottom="0.25rem",
                gap=DASHBOARD_SECTION_GAP_PX,
            ):
                st.plotly_chart(
                    month_figure,
                    width="stretch",
                    key="production_lob_months",
                    # 드래그 확대는 Figure 축의 `fixedrange` 와 `dragmode=False` 가 막는다.
                    # 여기서는 더블클릭 복귀와 축 손잡이를 함께 끈다 — 확대가 없는데 그
                    # 둘만 살아 있으면 누를 때마다 아무 일도 안 일어나는 조작이 된다.
                    # hover 는 그대로 살린다.
                    config={
                        "displayModeBar": False,
                        "responsive": True,
                        "doubleClick": False,
                        "showAxisDragHandles": False,
                        "scrollZoom": False,
                    },
                )
                # 라벨 칸의 제목 줄과 같은 높이로 비워 둔다. 두 칸의 자식 수와 높이가
                # 같아야 아래 표의 행이 맞는다. 높이를 주지 않으면 빈 컨테이너를
                # Streamlit 이 아예 그리지 않아 월 칸만 위로 올라붙는다.
                st.container(
                    key="plan_detail_title_spacer",
                    height=DASHBOARD_TITLE_HEIGHT_PX,
                    border=False,
                )
                st.plotly_chart(
                    detail_figures[1],
                    width="stretch",
                    key="production_detail_months",
                    config={"displayModeBar": False, "staticPlot": True},
                )
                # 라벨 칸의 `상세 B/N 공정` 제목 줄과 짝이 되는 빈 줄.
                st.container(
                    key="bottleneck_title_spacer",
                    height=DASHBOARD_TITLE_HEIGHT_PX,
                    border=False,
                )
                # 상세 B/N 월 Figure 는 hover 를 쓰므로 `staticPlot` 을 빼 둔다.
                # 같은 캔버스의 상세 두 Figure 중 계획 세부수량 쪽은 켜져 있다.
                # `staticPlot` 은 hover 까지 함께 끈다. 빼면 `displayModeBar` 기본값이
                # "hover" 로, `doubleClick`·`showAxisDragHandles` 는 켜짐으로 돌아가므로
                # 셋을 직접 끈다. 드래그 확대는 Figure 축의 `fixedrange` 가 막는다.
                st.plotly_chart(
                    detail_figures[3],
                    width="stretch",
                    key="bottleneck_detail_months",
                    config={
                        "displayModeBar": False,
                        "doubleClick": False,
                        "showAxisDragHandles": False,
                    },
                )
