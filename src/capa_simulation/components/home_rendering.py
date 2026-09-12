# Purpose: HOME Figure 세션 캐시와 화면 렌더링·성능 표시를 담당한다.

"""Session-scoped figure cache and rendering for the HOME dashboard."""

from __future__ import annotations

from typing import Any, cast

import pandas as pd
import streamlit as st

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    DASHBOARD_SCROLLBAR_HEIGHT_PX,
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
    int,
]

HomeFigureSet = tuple[Any, ...]

HOME_FIGURE_CACHE_KEY = "home_dashboard_figure_cache"

# EDP 포함/제외 × 선행 ON/OFF 네 가지 상태를 사람이 오가며 비교한다. 3 칸이면 되돌릴
# 때마다 차트를 다시 조립해 2 초를 쓴다. 한 칸은 Figure 여섯 개다.
HOME_FIGURE_CACHE_MAX_ENTRIES = 8

HOME_FIGURE_SCHEMA_VERSION = 35

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


@st.fragment
def render_home_figures(
    figures: HomeFigureSet,
    month_labels: list[str],
    *,
    applied_plan_detail_customer: bool = False,
    owner_tab: OpenTab | None = None,
) -> None:
    """대시보드 여섯 Figure. **숨은 탭에서는 그리지 않는다.**

    숨겨진 요소 안에서는 SVG 글자 폭 측정이 0 이라 `go.Table` 이 머리글을 셀 가운데에
    놓지 못하고, 상세 세 Figure 는 `staticPlot` 이라 탭을 열어도 다시 그리지 않는다.
    어긋난 머리글이 그대로 남는다.

    여기서 건너뛰는 위젯은 「상세」 토글 하나뿐이고 `persist_state="session"` 이라 값이
    살아남는다. 선행·GAP 토글은 이 함수 밖이라 숨어도 계속 그려진다.
    """
    if tab_is_hidden(owner_tab):
        return
    if len(figures) != 6:
        raise ValueError("HOME Figure 묶음은 요약 2개와 상세 4개, 모두 6개여야 합니다.")
    label_figure, month_figure = figures[:2]
    detail_figures = figures[2:]
    visible_month_count = min(max(len(month_labels), 1), tokens.DASHBOARD_MONTH_SCROLL_THRESHOLD)

    with st.container(border=True):
        # 구분 컬럼은 px 로 고정한다. 비율로 두면 창이 좁을 때 구획 제목이 잘리고, 조회
        # 월이 적을 때는 반대로 필요 이상 넓어진다. 비율은 CSS 적용 전 첫 그리기용이다.
        st.html(
            split_scroll_columns_style(
                label_key="production_lob_label_canvas",
                month_key="production_lob_month_region",
                label_width_px=DASHBOARD_LABEL_COLUMN_WIDTH_PX,
            )
        )
        # 제목 줄과 그 짝인 빈 줄을 같은 높이로 못박는다. 위젯 기본 높이에 맡기면 브라우저
        # 글꼴이나 Streamlit 판이 바뀔 때마다 두 칸이 어긋난다.
        st.html(
            f"""
            <style>
            .st-key-plan_detail_title_row,
            .st-key-plan_detail_title_spacer,
            .st-key-bottleneck_title_row,
            .st-key-bottleneck_title_spacer {{
                height: {DASHBOARD_TITLE_HEIGHT_PX}px;
                min-height: {DASHBOARD_TITLE_HEIGHT_PX}px;
                margin: 0;
            }}
            .st-key-plan_detail_title_row,
            .st-key-bottleneck_title_row {{ align-items: center; }}
            </style>
            """
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
            st.html(
                f"""
                <style>
                .st-key-production_lob_label_canvas {{
                    padding-top: calc({DASHBOARD_SCROLLBAR_HEIGHT_PX}px + 0.0rem);
                }}
                </style>
                """
            )
            with st.container(key="production_lob_month_region", gap=None):
                horizontal_scrollbar.render_horizontal_scrollbar(
                    target_selector=".st-key-production_lob_month_scroll",
                    height=DASHBOARD_SCROLLBAR_HEIGHT_PX,
                    key="production_lob_custom_scrollbar",
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
                        config={"displayModeBar": False, "responsive": True},
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
