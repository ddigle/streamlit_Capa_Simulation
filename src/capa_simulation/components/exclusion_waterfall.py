# Purpose: 제외 사유별로 몇 경로가 계산에서 빠졌는지 워터폴 한 장으로 보여 준다.

"""제외·탈락 워터폴.

제외 목록은 지금 표로만 있어서 **단계 간 크기 비교가 안 된다.** 확보율이 낮을 때
「진짜 설비가 모자란 것인지, 기준정보가 비어 절반이 계산에서 빠진 것인지」를 화면이
답하지 못한다. 후보 → 사유별 차감 → 남은 경로를 한 줄로 이어 그 답을 만든다.

**단위는 경로 수다.** 부하량으로 세면 업무 크기에 비례하지만 제외 프레임에 물량을 붙이는
조인이 하나 더 생기고, 그 조인이 실패하는 행을 또 다뤄야 한다. 지금은 경로 수로 세고
그 사실을 캡션에 적는다 — 「큰 제품 한 줄과 자잘한 열 줄이 같아 보인다」는 한계를 숨기지
않는 편이 낫다.

사유의 순서는 **제외가 실제로 일어난 순서**다(`services/unit_capacity.py` 의 판정 순서).
순서를 바꾸면 같은 데이터에서 다른 그림이 나온다 — 한 행이 두 사유에 걸리면 앞의 사유가
가져가기 때문이다.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens

REASON_COLUMN = "제외사유"

# 이 순서로 세로 막대가 선다. `unit_capacity.calculate_unit_capacity` 가 걸러 내는 차례와
# 같게 둔다 — 화면이 계산을 설명해야지 계산과 다른 이야기를 하면 안 된다.
REASON_ORDER = (
    "UPEH 0 이하",
    "CAPA_RUN_RATE 0 이하",
    "WF측정률 음수",
    "Lot 측정률 음수",
    "대당 Capa 0 이하",
)


def build_exclusion_waterfall(
    exclusions: pd.DataFrame,
    remaining_rows: int,
) -> go.Figure | None:
    """후보 → 사유별 차감 → 남은 경로. 제외가 없으면 `None` 이다.

    제외가 0 건이면 막대 두 개가 같은 높이로 서서 아무것도 말하지 않는다. 그럴 때는
    그리지 않고 호출부가 안내 문구만 남긴다.
    """
    if exclusions.empty or REASON_COLUMN not in exclusions.columns:
        return None

    counts = exclusions[REASON_COLUMN].astype("string").value_counts()
    # 계약에 없는 사유가 와도 버리지 않는다. 뒤에 붙여서 합이 맞게 둔다 — 합이 어긋나면
    # 그림이 조용히 거짓말을 한다.
    ordered = [reason for reason in REASON_ORDER if reason in counts.index]
    ordered += [str(reason) for reason in counts.index if reason not in REASON_ORDER]
    if not ordered:
        return None

    candidate_rows = remaining_rows + int(counts.sum())
    labels = ["후보 경로", *ordered, "계산에 남은 경로"]
    values = [float(candidate_rows), *(-float(counts[reason]) for reason in ordered), 0.0]
    measures = ["absolute", *("relative" for _ in ordered), "total"]

    figure = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            text=[
                f"{candidate_rows:,}",
                *(f"−{int(counts[reason]):,}" for reason in ordered),
                f"{remaining_rows:,}",
            ],
            textposition="outside",
            connector={"line": {"color": tokens.BORDER, "width": 1}},
            decreasing={"marker": {"color": tokens.STATUS_SHORTAGE}},
            increasing={"marker": {"color": tokens.STATUS_SECURE}},
            totals={"marker": {"color": tokens.ACCENT}},
            hovertemplate="%{x}<br>%{y:,.0f} 경로<extra></extra>",
        )
    )
    figure.update_layout(
        height=300,
        margin={"l": 8, "r": 8, "t": 24, "b": 8},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.CHART_CANVAS,
        font={"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": 12},
        showlegend=False,
    )
    figure.update_yaxes(
        title=None,
        rangemode="tozero",
        gridcolor=tokens.BORDER,
        zeroline=False,
    )
    figure.update_xaxes(title=None, showgrid=False)
    return figure


def render_exclusion_waterfall(
    exclusions: pd.DataFrame,
    remaining_rows: int,
    *,
    key: str,
    owner_tab: OpenTab | None = None,
) -> None:
    """숨은 탭에서는 그리지 않는다. 다른 Plotly 표와 같은 이유다."""
    if tab_is_hidden(owner_tab):
        return
    figure = build_exclusion_waterfall(exclusions, remaining_rows)
    if figure is None:
        return
    st.plotly_chart(figure, width="stretch", key=key, config={"staticPlot": False})
    st.caption(
        "경로 수 기준입니다. 한 경로가 두 사유에 걸리면 먼저 판정한 사유가 가져가므로 "
        "막대 합은 제외 목록 건수와 같습니다. 물량이 큰 경로와 작은 경로를 같은 1로 세는 "
        "점은 감안해 읽으세요."
    )
