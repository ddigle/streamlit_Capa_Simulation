# Purpose: 공정 × 월 확보율을 상태 3색 히트맵 한 장으로 보여 준다.

"""확보율 히트맵.

확보율 표는 66개 공정 × 12개월이라 **스크롤 없이는 전체 모양이 안 보인다.** 「어느 공정이
언제부터 무너지나」는 숫자를 훑어서 답할 것이 아니라 한눈에 보일 것이다. 같은 값을 같은
판정 기준으로 칠해 격자로 놓으면 그 답이 모양으로 나온다.

**연속 색이 아니라 상태 3색이다.** 확보율은 이 앱에서 이미 확보·경고·부족 세 상태로
판정하고, 그 경계는 사용자가 정한다. 연속 그라데이션을 쓰면 화면마다 다른 색 체계가 두 개
생기고, 105% 와 108% 의 미묘한 색차가 「경계를 넘었나」보다 도드라져 판정을 흐린다.
`home_figures.capacity_status` 와 같은 색·같은 경계를 쓴다. 경계는 **그 달의 실효 기준**이다 —
공용 판정 기준(`services/securement_threshold`)에 월별 예외가 있으면 그 달 열만 다른 경계로 칠한다.

색만으로 뜻을 나르지 않도록 범례(`home_preference.status_legend_markup`)를 함께 그리고,
칸이 적을 때는 숫자도 칸 안에 적는다.

**주요 공정을 지정해서 본다.** 66개를 다 깔면 모양은 보여도 「어느 것을 봐야 하나」가 없다.
관리 대상 공정 몇 개만 남기면 그 공정들이 **언제** 무너지는지가 가로로 읽힌다.
`shortage_summary()` 가 그 「언제」를 최초 부족 월과 개월 수로 따로 적는다 — 색을 세는
것보다 숫자가 빠르다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.components.home_preference import status_legend_markup
from capa_simulation.components.plotly_layout import chart_canvas_layout, hover_chart_config
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.securement_threshold import SecurementThresholds

# 칸 높이. 표의 27px 보다 낮게 잡아 66공정이 한 화면에 들어오게 한다.
CELL_HEIGHT_PX = 20
CHART_CHROME_PX = 70
MAX_CHART_HEIGHT_PX = 900
# 공정이 많아 칸이 낮아져도 이보다는 낮추지 않는다. **모든 행에 이름을 단다** — Plotly 자동 눈금은
# 칸이 낮으면 이름을 하나 건너 하나만 그려, 70공정에서 35개 행(부족 행 포함)이 이름 없이 남고
# 이름이 두 행 사이에 걸려 다른 공정으로 읽혔다(2026-10-05 E2E). 이 높이에서는 상한을 넘어 길어진다.
MIN_LABELLED_ROW_PX = 13
# 칸이 낮을 때의 공정 이름 글자 크기. 칸 높이보다 3px 작아야 위아래 이름이 붙지 않는다.
DENSE_TICK_FONT_PX = 10
# 월 눈금. 칸 폭은 브라우저에서야 정해지므로(`width="stretch"`) 가로로 둘지 세울지는 Plotly 가
# 그린 뒤 글자 폭과 칸 폭을 재어 고른다(`autotickangles`) — 들어가면 가로, 겹치면 세운다. 세워도
# 겹칠 만큼 달이 많을 때만 서버가 달을 솎는다. 1280px 창에서 70공정을 그리면 격자가 약 700px 이고,
# 세운 「26.07」 한 줄(11px 글씨)에는 16px 이 있어야 이웃과 붙지 않는다 — 그래서 눈금은 43개까지다.
MONTH_TICK_ANGLES = (0, -90)
NARROWEST_GRID_PX = 700
ROTATED_MONTH_SLOT_PX = 16
MAX_MONTH_TICKS = NARROWEST_GRID_PX // ROTATED_MONTH_SLOT_PX
# 솎을 때의 간격(개월). 달력과 맞는 간격만 쓴다 — 홀수 달·분기 첫 달·반기 첫 달처럼 읽힌다.
MONTH_TICK_STEPS = (1, 2, 3, 4, 6, 12)
# 이보다 칸이 많으면 숫자를 적지 않는다. 6pt 글씨로 가득 찬 격자는 모양도 숫자도 못 읽는다.
MAX_LABELLED_CELLS = 180

SHORTAGE_TIER = 0.0
WARNING_TIER = 1.0
SECURE_TIER = 2.0


def _tier(rate: float, *, thresholds: SecurementThresholds, month: int | None) -> float:
    """`home_figures.capacity_status` 와 같은 판정이다. 경계가 갈리면 두 화면이 다른 말을 한다.

    `month` 가 없으면(월이 아닌 열) 기본 기준으로 판정한다.
    """
    return {
        "secure": SECURE_TIER,
        "warning": WARNING_TIER,
        "shortage": SHORTAGE_TIER,
    }[thresholds.status(rate, month)]


def _column_month(column: object) -> int | None:
    """월 컬럼 `"202601"` 의 `YYYYMM`. 월이 아닌 컬럼이면 `None` 이다."""
    try:
        return int(str(column))
    except ValueError:
        return None


def _month_tick(column: object) -> str:
    """월 컬럼은 `"202601"` 같은 문자열이다. 월이 아닌 컬럼이 섞여 와도 멈추지 않는다."""
    try:
        return month_label(int(str(column)))
    except ValueError:
        return str(column)


def _month_tick_step(month_count: int) -> int:
    """눈금 간격(개월). 세운 눈금이 `MAX_MONTH_TICKS` 개를 넘지 않는 가장 촘촘한 달력 간격이다."""
    for step in MONTH_TICK_STEPS:
        if -(-month_count // step) <= MAX_MONTH_TICKS:
            return step
    return MONTH_TICK_STEPS[-1]


def _thinned_month_ticks(month_columns: Sequence[object], step: int) -> list[str]:
    """간격 `step` 으로 남길 눈금. 1월에서부터 세어 달력과 맞춘다(`step` 이 3 이면 1·4·7·10월)."""
    kept: list[str] = []
    for position, column in enumerate(month_columns):
        try:
            month = int(str(column)) % 100
        except ValueError:
            # 월이 아닌 컬럼은 차례로 센다(`_month_tick` 처럼 멈추지 않는다).
            month = position + 1
        if (month - 1) % step == 0:
            kept.append(_month_tick(column))
    return kept


def _discrete_colorscale() -> list[list[float | str]]:
    """세 계단만 갖는 색 눈금. 계단 사이에서 색이 섞이지 않게 경계마다 두 번씩 적는다."""
    steps = (tokens.STATUS_SHORTAGE, tokens.STATUS_WARNING, tokens.STATUS_SECURE)
    scale: list[list[float | str]] = []
    for index, color in enumerate(steps):
        scale.append([index / len(steps), color])
        scale.append([(index + 1) / len(steps), color])
    return scale


def build_securement_heatmap(
    table: pd.DataFrame,
    *,
    dimension_columns: Sequence[str],
    thresholds: SecurementThresholds,
    labels: ProcessLabels | None = None,
) -> go.Figure | None:
    """공정 × 월 격자. 그릴 것이 없으면 `None` 이다."""
    month_columns = [column for column in table.columns if column not in set(dimension_columns)]
    if table.empty or not month_columns or not list(dimension_columns):
        return None

    row_column = list(dimension_columns)[0]
    row_names = [
        labels.label(value) if labels is not None else str(value) for value in table[row_column]
    ]
    rates = table[month_columns].apply(pd.to_numeric, errors="coerce")

    column_months = [_column_month(column) for column in month_columns]
    tiers = [
        [
            None if pd.isna(value) else _tier(float(value), thresholds=thresholds, month=month)
            for value, month in zip(row, column_months, strict=True)
        ]
        for row in rates.to_numpy()
    ]
    # hover 와 칸 안 숫자는 실제 확보율이다. 3계단으로 접는 것은 색뿐이다.
    percents = [
        [None if pd.isna(value) else float(value) * 100.0 for value in row]
        for row in rates.to_numpy()
    ]
    show_text = len(row_names) * len(month_columns) <= MAX_LABELLED_CELLS
    text = [["" if value is None else f"{value:,.0f}" for value in row] for row in percents]

    figure = go.Figure(
        go.Heatmap(
            z=tiers,
            x=[_month_tick(column) for column in month_columns],
            y=row_names,
            customdata=percents,
            colorscale=_discrete_colorscale(),
            zmin=SHORTAGE_TIER - 0.5,
            zmax=SECURE_TIER + 0.5,
            showscale=False,
            hoverongaps=False,
            xgap=1,
            ygap=1,
            text=text if show_text else None,
            texttemplate="%{text}" if show_text else None,
            textfont={"size": 10, "color": tokens.TEXT},
            hovertemplate="%{y} · %{x}<br>확보율 %{customdata:,.1f}%<extra></extra>",
        )
    )
    rows = len(row_names)
    row_px = max(
        MIN_LABELLED_ROW_PX,
        min(CELL_HEIGHT_PX, (MAX_CHART_HEIGHT_PX - CHART_CHROME_PX) / max(rows, 1)),
    )
    height = max(180, round(rows * row_px + CHART_CHROME_PX))
    figure.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 28, "b": 8},
        **chart_canvas_layout(font_size=11),
    )
    # 표와 같은 순서로 위에서 아래로 읽힌다. Plotly 의 y 축은 기본이 아래에서 위다.
    # 두 축 모두 **범주**다. `"26.07"` 은 숫자로 읽히면 26.07 이 되어 월 칸이 실수 축에
    # 눌려 붙고 눈금이 `26.2·26.4` 로 나온다. 공정명도 마찬가지로 범주여야 한다.
    # 눈금은 행마다 하나(`dtick=1`)다 — 자동 눈금은 낮은 칸에서 이름을 건너뛴다.
    figure.update_yaxes(
        type="category",
        autorange="reversed",
        title=None,
        ticklabelposition="outside",
        tickmode="linear",
        dtick=1,
        tickfont={"size": 11 if row_px >= 14 else DENSE_TICK_FONT_PX},
    )
    # 월 축은 위에 둔다. 각도는 고정하지 않는다 — 고정한 가로 눈금은 칸이 좁아지면(1280px 창·30개월)
    # 「26.0726.08」처럼 이웃과 붙었다. `automargin` 이 세운 눈금만큼 위 여백을 늘린다. 두 축 모두
    # 확대를 막는다 — 격자 한 장을 확대할 일이 없고, 툴바를 끄면(`hover_chart_config`) 되돌릴 단추도
    # 없다. 툴바가 오른쪽 위 월 눈금을 덮던 것도 툴바를 끄는 것으로 걷는다.
    month_ticks: dict[str, object] = {}
    step = _month_tick_step(len(month_columns))
    if step > 1:
        kept = _thinned_month_ticks(month_columns, step)
        month_ticks = {"tickmode": "array", "tickvals": kept, "ticktext": kept}
    figure.update_xaxes(
        type="category",
        title=None,
        side="top",
        autotickangles=list(MONTH_TICK_ANGLES),
        automargin=True,
        fixedrange=True,
        **month_ticks,
    )
    figure.update_yaxes(fixedrange=True)
    return figure


SHORTAGE_SUMMARY_COLUMNS = ("공정", "최초 부족", "부족 개월")


def shortage_summary(
    table: pd.DataFrame,
    *,
    dimension_columns: Sequence[str],
    thresholds: SecurementThresholds,
    labels: ProcessLabels | None = None,
) -> pd.DataFrame:
    """공정별 **최초 부족 월**과 부족 개월 수. 부족이 없는 공정은 행이 없다.

    경계는 히트맵의 부족(빨강)과 같다 — **그 달의** 경고 기준 미만이다. 그림에서 빨간 칸을 세어 답할
    수 있는 것을 숫자로 먼저 적는 이유는, 그 답이 이 화면의 요점이기 때문이다.
    """
    keys = list(dimension_columns)
    month_columns = [column for column in table.columns if column not in set(keys)]
    if table.empty or not month_columns or not keys:
        return pd.DataFrame(columns=list(SHORTAGE_SUMMARY_COLUMNS))

    rates = table[month_columns].apply(pd.to_numeric, errors="coerce")
    month_warnings = pd.Series(
        [thresholds.warning_for(_column_month(column)) for column in month_columns],
        index=rates.columns,
        dtype="float64",
    )
    shortage = rates.lt(month_warnings, axis=1) & rates.notna()
    rows: list[dict[str, object]] = []
    for position, (_, flags) in enumerate(shortage.iterrows()):
        months = [column for column, is_short in zip(month_columns, flags, strict=True) if is_short]
        if not months:
            continue
        name = table[keys[0]].iloc[position]
        rows.append(
            {
                "공정": labels.label(name) if labels is not None else str(name),
                "최초 부족": _month_tick(months[0]),
                "부족 개월": len(months),
            }
        )
    summary = pd.DataFrame(rows, columns=list(SHORTAGE_SUMMARY_COLUMNS))
    # 빨리 무너지는 것부터, 같은 달이면 오래 무너지는 것부터 본다.
    return summary.sort_values(["최초 부족", "부족 개월"], ascending=[True, False]).reset_index(
        drop=True
    )


def render_securement_heatmap(
    table: pd.DataFrame,
    *,
    dimension_columns: Sequence[str],
    thresholds: SecurementThresholds,
    key: str,
    labels: ProcessLabels | None = None,
    owner_tab: OpenTab | None = None,
) -> None:
    """숨은 탭에서는 그리지 않는다. 다른 Plotly 표와 같은 이유다."""
    if tab_is_hidden(owner_tab):
        return
    figure = build_securement_heatmap(
        table,
        dimension_columns=dimension_columns,
        thresholds=thresholds,
        labels=labels,
    )
    if figure is None:
        st.info("히트맵으로 그릴 확보율이 없습니다.")
        return
    st.markdown(status_legend_markup(), unsafe_allow_html=True)
    st.plotly_chart(figure, width="stretch", key=key, config=hover_chart_config())
