# Purpose: 두 시나리오의 기간 계획 물량 차이를 분류별 덤벨 차트로 보여 준다.

"""시나리오 A↔B 덤벨.

비교 시나리오를 켜면 세부수량 표의 칸마다 증감이 작게 붙는다. 그런데 그 표는 분류 × 월
격자라 **「어느 분류가 가장 크게 달라졌나」는 어디에도 없다.** 칸 수백 개의 작은 글씨를
눈으로 합산해야 나오는 답이다.

덤벨은 그 답을 순서로 만든다. 한 줄에 점 두 개(비교·현재)를 놓고 선으로 잇는다 —
**선의 길이가 곧 차이**고, 위에서부터 큰 차이 순이다. 막대 두 개를 나란히 놓는 것보다
낫다: 막대는 절대값이 커 보이고 우리가 볼 것은 둘 사이 간격이다.

**연결선 색은 방향이다.** 늘었나 줄었나는 좋고 나쁨이 아니므로 상태색(확보·경고·부족)이
아니라 `tokens.DELTA_*` 를 쓴다 — 표의 증감 글자와 같은 색 체계다.

기간 합계로 접는다. 월별 모양은 이미 표가 답하므로 여기서 또 답하지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens

CURRENT_NAME = "현재"
COMPARISON_NAME = "비교"

ROW_HEIGHT_PX = 26
CHART_CHROME_PX = 90
DEFAULT_TOP_N = 12


def _period_totals(detail: pd.DataFrame, dimensions: Sequence[str]) -> pd.DataFrame:
    """분류별 기간 합계 한 컬럼으로 접는다. 월 컬럼이 없으면 합계는 0 이다."""
    keys = list(dimensions)
    month_columns = [column for column in detail.columns if column not in set(keys)]
    frame = detail[keys].astype("string").copy()
    if month_columns:
        values = detail[month_columns].apply(pd.to_numeric, errors="coerce")
        frame["합계"] = values.sum(axis=1, min_count=1)
    else:
        frame["합계"] = pd.NA
    # 그룹 키 말고 남는 컬럼은 `합계` 하나뿐이라 프레임 전체를 더하면 그것만 더해진다.
    return frame.groupby(keys, as_index=False, dropna=False, sort=False).sum(min_count=1)


def build_plan_comparison_dumbbell(
    current_detail: pd.DataFrame,
    comparison_detail: pd.DataFrame,
    *,
    dimensions: Sequence[str],
    top_n: int = DEFAULT_TOP_N,
) -> go.Figure | None:
    """차이가 큰 순으로 상위 `top_n` 분류. 차이가 하나도 없으면 `None` 이다."""
    keys = list(dimensions)
    if not keys or current_detail.empty and comparison_detail.empty:
        return None
    if any(column not in current_detail.columns for column in keys):
        return None
    if any(column not in comparison_detail.columns for column in keys):
        return None

    # 한쪽에만 있는 분류가 이 화면의 요점이다. 빠진 제품은 결측이 아니라 0 으로 읽어야
    # 「없어졌다」가 길이로 드러난다.
    merged = _period_totals(current_detail, keys).merge(
        _period_totals(comparison_detail, keys),
        on=keys,
        how="outer",
        suffixes=("_현재", "_비교"),
        validate="one_to_one",
    )
    merged["합계_현재"] = merged["합계_현재"].fillna(0.0)
    merged["합계_비교"] = merged["합계_비교"].fillna(0.0)
    merged["차이"] = merged["합계_현재"] - merged["합계_비교"]

    changed = merged.loc[merged["차이"] != 0].copy()
    if changed.empty:
        return None
    changed["크기"] = changed["차이"].abs()
    changed = changed.sort_values("크기", ascending=False).head(max(1, top_n))
    # 위에서부터 큰 차이 순으로 읽히게 뒤집는다. Plotly 의 y 축은 아래에서 위로 쌓인다.
    changed = changed.iloc[::-1].reset_index(drop=True)

    row_labels = [" · ".join(str(row[column]) for column in keys) for _, row in changed.iterrows()]
    figure = go.Figure()
    for label, current, comparison in zip(
        row_labels, changed["합계_현재"], changed["합계_비교"], strict=True
    ):
        figure.add_shape(
            type="line",
            x0=float(comparison),
            x1=float(current),
            y0=label,
            y1=label,
            line={
                "color": (
                    tokens.DELTA_INCREASE if current >= comparison else tokens.DELTA_DECREASE
                ),
                "width": 2,
            },
            layer="below",
        )
    figure.add_trace(
        go.Scatter(
            x=changed["합계_비교"],
            y=row_labels,
            mode="markers",
            name=COMPARISON_NAME,
            marker={
                "size": 9,
                "color": tokens.SURFACE,
                "line": {"color": tokens.TEXT_MUTED, "width": 2},
            },
            hovertemplate="%{y}<br>비교 %{x:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=changed["합계_현재"],
            y=row_labels,
            mode="markers+text",
            name=CURRENT_NAME,
            marker={
                "size": 10,
                "color": tokens.ACCENT,
                "line": {"color": tokens.SURFACE, "width": 2},
            },
            # 차이는 줄마다 적는다. 이 화면에서 읽을 값이 그것 하나뿐이라 「선택적 직접
            # 라벨」의 대상이 된다.
            text=[f"{value:+,.0f}" for value in changed["차이"]],
            textposition="middle right",
            textfont={"size": 11, "color": tokens.TEXT_MUTED},
            cliponaxis=False,
            hovertemplate="%{y}<br>현재 %{x:,.0f}<extra></extra>",
        )
    )
    figure.update_layout(
        height=len(row_labels) * ROW_HEIGHT_PX + CHART_CHROME_PX,
        margin={"l": 8, "r": 64, "t": 8, "b": 28},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.CHART_CANVAS,
        font={"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": 12},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.0,
            "xanchor": "left",
            "x": 0.0,
        },
        hovermode="closest",
    )
    figure.update_xaxes(
        title=None, gridcolor=tokens.BORDER, zeroline=False, rangemode="tozero", tickformat=",.0f"
    )
    figure.update_yaxes(title=None, showgrid=False, type="category")
    return figure


def render_plan_comparison_dumbbell(
    current_detail: pd.DataFrame,
    comparison_detail: pd.DataFrame,
    *,
    dimensions: Sequence[str],
    key: str,
    top_n: int = DEFAULT_TOP_N,
    owner_tab: OpenTab | None = None,
) -> None:
    """숨은 탭에서는 그리지 않는다. 다른 Plotly 그림과 같은 이유다."""
    if tab_is_hidden(owner_tab):
        return
    figure = build_plan_comparison_dumbbell(
        current_detail,
        comparison_detail,
        dimensions=dimensions,
        top_n=top_n,
    )
    if figure is None:
        st.info("두 시나리오의 계획 물량이 같습니다.")
        return
    st.plotly_chart(figure, width="stretch", key=key, config={"staticPlot": False})
    st.caption(
        f"조회 기간 **합계** 기준이고 차이가 큰 순으로 최대 {top_n}개만 그립니다. "
        "한쪽 시나리오에만 있는 분류는 다른 쪽을 0 으로 봅니다 — 빠진 계획이 길이로 "
        "드러나야 합니다. 월별 모양은 위의 계획 세부수량 표가 답합니다."
    )
