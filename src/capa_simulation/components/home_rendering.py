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
)
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.design import tokens
from capa_simulation.performance import PerformanceTrace

# 세 번째 요소는 시나리오 내용 토큰이다. 편집 카운터(`revision`)를 쓰면 내용이 달라도
# 번호가 겹쳐 예전 Figure 가 그대로 나온다. 계산 캐시와 같은 근거로 토큰을 쓴다.
HomeFigureCacheKey = tuple[int, int, str, int, int, str, tuple[str, ...], float, float, bool]

HomeFigureSet = tuple[Any, ...]

HOME_FIGURE_CACHE_KEY = "home_dashboard_figure_cache"

HOME_FIGURE_CACHE_MAX_ENTRIES = 3

HOME_FIGURE_SCHEMA_VERSION = 26


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
) -> None:
    if len(figures) not in {2, 6}:
        raise ValueError("HOME Figure 묶음은 요약 2개 또는 상세 포함 6개여야 합니다.")
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
                if detail_figures:
                    st.plotly_chart(
                        detail_figures[0],
                        width="stretch",
                        key="production_detail_labels",
                        config={"displayModeBar": False, "staticPlot": True},
                    )
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
                    if detail_figures:
                        st.plotly_chart(
                            detail_figures[1],
                            width="stretch",
                            key="production_detail_months",
                            config={"displayModeBar": False, "staticPlot": True},
                        )
                        st.plotly_chart(
                            detail_figures[3],
                            width="stretch",
                            key="bottleneck_detail_months",
                            config={"displayModeBar": False, "staticPlot": True},
                        )
