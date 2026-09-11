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
from capa_simulation.components.loading_progress import LoadingStage
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.design import tokens
from capa_simulation.performance import PerformanceTrace

# 네 번째 요소는 시나리오 내용 토큰이다. 편집 카운터(`revision`)를 쓰면 내용이 달라도
# 번호가 겹쳐 예전 Figure 가 그대로 나온다. 계산 캐시와 같은 근거로 토큰을 쓴다.
# 두 번째 요소는 공용 공정 표시명 프로필 버전이다. 표시명은 계산 입력이 아니라 라벨이므로
# 계산 캐시 키(`build_home_simulation_cache_key`)에는 넣지 않고 여기에만 접어 넣는다.
# 뒤의 셋은 화면 기준 토글이다 — EDP 포함 여부, 선행 반영 여부, 선행 물량 프로필 버전.
# 버전은 선행을 켰을 때만 채우므로 껐다 켜도 같은 칸을 다시 쓰지 않는다.
HomeFigureCacheKey = tuple[
    int, int, int, str, int, int, str, tuple[str, ...], float, float, bool, bool, int
]

HomeFigureSet = tuple[Any, ...]

HOME_FIGURE_CACHE_KEY = "home_dashboard_figure_cache"

# EDP 포함/제외 × 선행 ON/OFF 네 가지 상태를 사람이 오가며 비교한다. 3 칸이면 되돌릴
# 때마다 차트를 다시 조립해 2 초를 쓴다. 한 칸은 Figure 여섯 개다.
HOME_FIGURE_CACHE_MAX_ENTRIES = 8

HOME_FIGURE_SCHEMA_VERSION = 30

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
) -> None:
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
                    st.plotly_chart(
                        detail_figures[1],
                        width="stretch",
                        key="production_detail_months",
                        config={"displayModeBar": False, "staticPlot": True},
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
