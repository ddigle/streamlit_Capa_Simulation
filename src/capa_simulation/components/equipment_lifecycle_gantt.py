# Purpose: 호기별 생애주기 구간을 상태색 Gantt 한 장으로 보여 준다.

"""설비 생애주기 Gantt.

「호기 생애주기 상태 모니터링」 막대는 **오늘 몇 대가 어느 상태인가**를 답한다. 그런데
설비 일정에서 정작 알아야 할 것은 **언제 몇 대가 쓸 수 있게 되는가**다 — 입고는 언제고
Qual 은 언제 끝나며 반출은 언제인지, 그 사이가 얼마나 비는지.

날짜 컬럼 여섯 개(제진대·물류·입고·Qual·반출·이설)는 **점**이라 표로는 그 사이 간격이
보이지 않는다. Gantt 는 그 간격을 길이로 만든다.

구간 계산은 `services/equipment_availability.build_equipment_lifecycle_spans` 가 한다 —
상태 판정 규칙을 여기서 다시 적지 않는다. 색은 `tokens.EQUIPMENT_STAGE_COLORS` 로,
Space 배치도·상태 막대와 같은 값이다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.components.plotly_layout import chart_canvas_layout
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    EQUIPMENT_STATUSES,
)

ROW_HEIGHT_PX = 22
CHART_CHROME_PX = 110
MAX_CHART_HEIGHT_PX = 820
# 호기가 이보다 많으면 줄 이름이 겹쳐 아무것도 못 읽는다. 자를 때는 몇 대를 잘랐는지 적는다.
DEFAULT_MAX_UNITS = 40


def build_equipment_lifecycle_gantt(
    spans: pd.DataFrame,
    *,
    max_units: int = DEFAULT_MAX_UNITS,
    today: date | None = None,
) -> tuple[go.Figure | None, int]:
    """Gantt 와 **그리지 못하고 자른 호기 수**. 구간이 없으면 Figure 는 `None` 이다."""
    if spans.empty:
        return None, 0

    units = spans[EQUIPMENT_ID_COLUMN].astype(str).drop_duplicates().sort_values().tolist()
    hidden_units = max(0, len(units) - max_units)
    drawn_units = units[:max_units]
    drawn = spans.loc[spans[EQUIPMENT_ID_COLUMN].astype(str).isin(drawn_units)].copy()

    frame = drawn.copy()
    frame[EQUIPMENT_ID_COLUMN] = frame[EQUIPMENT_ID_COLUMN].astype(str)
    frame["상태"] = frame["상태"].astype(str)
    frame["시작"] = pd.to_datetime(frame["시작일"])
    # Plotly 의 구간은 끝을 **배타적**으로 읽는다. 마지막 날을 포함시키려면 하루를 더한다 —
    # 더하지 않으면 하루짜리 구간이 폭 0 으로 사라진다.
    frame["끝"] = pd.to_datetime(frame["종료일"]) + pd.Timedelta(days=1)

    figure = px.timeline(
        frame,
        x_start="시작",
        x_end="끝",
        y=EQUIPMENT_ID_COLUMN,
        color="상태",
        color_discrete_map=dict(tokens.EQUIPMENT_STAGE_COLORS),
        category_orders={
            EQUIPMENT_ID_COLUMN: drawn_units,
            "상태": list(EQUIPMENT_STATUSES),
        },
        custom_data=["상태", "공정소분류", "시작일", "종료일"],
    )
    figure.update_traces(
        marker={"line": {"color": tokens.SURFACE, "width": 1}},
        hovertemplate=(
            "%{y} · %{customdata[1]}<br>%{customdata[0]}"
            "<br>%{customdata[2]} ~ %{customdata[3]}<extra></extra>"
        ),
    )
    if today is not None:
        # 오늘 선이 있어야 「이미 지난 일정」과 「앞으로의 일정」이 갈린다.
        figure.add_vline(
            x=pd.Timestamp(today),
            line={"color": tokens.LINE, "width": 1, "dash": "dot"},
            annotation={"text": "오늘", "font": {"size": 11, "color": tokens.TEXT_MUTED}},
        )
    figure.update_layout(
        height=min(
            MAX_CHART_HEIGHT_PX, max(220, len(drawn_units) * ROW_HEIGHT_PX + CHART_CHROME_PX)
        ),
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        **chart_canvas_layout(font_size=11),
        legend={
            "title": None,
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.0,
            "xanchor": "left",
            "x": 0.0,
        },
        bargap=0.25,
    )
    figure.update_yaxes(autorange="reversed", title=None, showgrid=False)
    figure.update_xaxes(title=None, gridcolor=tokens.BORDER, showgrid=True)
    return figure, hidden_units


def render_equipment_lifecycle_gantt(
    spans: pd.DataFrame,
    *,
    key: str,
    max_units: int = DEFAULT_MAX_UNITS,
    today: date | None = None,
    owner_tab: OpenTab | None = None,
) -> None:
    """숨은 탭에서는 그리지 않는다. 다른 Plotly 그림과 같은 이유다."""
    if tab_is_hidden(owner_tab):
        return
    figure, hidden_units = build_equipment_lifecycle_gantt(spans, max_units=max_units, today=today)
    if figure is None:
        st.info("조회 기간에 그릴 호기 일정이 없습니다.")
        return
    st.plotly_chart(figure, width="stretch", key=key, config={"staticPlot": False})
    if hidden_units:
        # 자른 것을 적지 않으면 「이게 전부」로 읽힌다.
        st.caption(
            f"호기 이름 순으로 {max_units:,}행만 그렸습니다. 나머지 {hidden_units:,}행은 "
            "조회 조건을 좁혀서 보세요."
        )
