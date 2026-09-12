# Purpose: HOME 대시보드의 요약·계획 상세·B/N 상세 Plotly Figure 를 생성한다.

"""Plotly figures for the HOME dashboard.

각 함수는 고정 분류 영역과 스크롤 월 영역 두 Figure 를 한 쌍으로 돌려준다. 페이지는
이 결과를 캐시하고 렌더링만 담당한다.
"""

from __future__ import annotations

import html
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from capa_simulation.components.home_dimensions import (
    BOTTLENECK_DETAIL_BAR_HEIGHT_PX,
    BOTTLENECK_DETAIL_HEADER_HEIGHT_PX,
    BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
    LOB_BOTTOM_MARGIN_PX,
    LOB_CHART_HEIGHT_PX,
    LOB_FIGURE_HEIGHT_PX,
    LOB_TABLE_HEIGHT_PX,
    LOB_TABLE_ROW_HEIGHTS_PX,
    LOB_TOP5_HEIGHT_PX,
    LOB_TOP_MARGIN_PX,
    LOB_VALUE_FONT_SIZE_PX,
    lower_delta_row_height,
    lower_delta_yshift_px,
    table_row_height,
)
from capa_simulation.components.plotly_layout import (
    TRANSPARENT_COLOR,
    add_figure_outer_border,
    add_fixed_table_row,
    add_quarter_boundaries,
    append_layout_items,
    delta_color,
    fixed_row_domains,
    flush_layout_items,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import tokens
from capa_simulation.services.dashboard import (
    DETAIL_DIMENSION_HEADERS,
    DETAIL_DIMENSION_WIDTHS,
    PRODUCTION_DETAIL_DIMENSIONS,
)

# 상세 B/N 공정 시트가 보여줄 순위 상한. 페이지가 서비스에 넘기는 값이고, 자르는 곳은
# 서비스 한 곳이다. Figure 는 받은 프레임을 그대로 믿고 행 수를 `순위` 최대값으로만
# 정하므로, 유효 공정이 이보다 적은 달은 남는 칸을 비운다.
BOTTLENECK_DETAIL_RANK_LIMIT = 20

# 막대 길이가 표현하는 확보율 구간. 확보율은 비율이므로 0.80 = 80%, 1.50 = 150% 다
# (`services/securement_rate.py` 가 가용대수/소요대수를 그대로 넣는다). 80% 미만은
# 막대가 보이지 않고 150% 이상은 열 너비를 꽉 채운다.
BOTTLENECK_BAR_MIN_RATE = 0.80
BOTTLENECK_BAR_MAX_RATE = 1.50

# 월 열(MONTH_COLUMN_WIDTH_PX) 안에서 막대가 비우는 좌우 여백과, 막대 왼쪽 끝에서
# 공정명이 시작하는 자리. 이름은 막대 길이와 무관하게 이 고정 앵커에 그린다 — 확보율
# 오름차순이라 상위 순위는 대부분 막대가 0 길이인데, 이름을 막대 안에 넣으면 가장
# 심각한 병목의 공정명이 화면에서 사라진다.
BOTTLENECK_BAR_SIDE_INSET_RATIO = 0.04
BOTTLENECK_NAME_INSET_RATIO = 0.07

# 공정명 글자 크기 자동 축소 예산. 막대와 같은 줄에 한 줄로 들어가는 크기다.
BOTTLENECK_NAME_WIDTH_BUDGET_PX = 80
BOTTLENECK_NAME_MIN_FONT_PX = 8
BOTTLENECK_NAME_MAX_FONT_PX = 12

# 계획 세부수량 칸의 값 글자. 분류 칸과 월 칸이 같아야 두 칸의 글자가 같은 눈높이에 선다.
DETAIL_VALUE_FONT_SIZE_PX = 14

# 생산계획 LOB 막대 안 확보율 글자.
LOB_BAR_LABEL_FONT_SIZE_PX = 22

# 계획 세부수량 머리글. 칸 높이가 이 크기에서 나온다.
DETAIL_HEADER_FONT_SIZE_PX = 15

# 글자 크기가 최소값 바닥에 걸리면 더 줄일 수 없어 렌더 폭이 계속 늘어난다. `go.Scatter`
# 의 text 는 줄바꿈도 칸 단위 클립도 없어 그대로 옆 달 칸을 침범하므로, 남는 한 단계는
# 말줄임이다. 전체 이름은 hover 의 `customdata` 에 잘리지 않고 뜬다.
BOTTLENECK_NAME_ELLIPSIS = "…"

# `필요대수`는 화면 라벨이고 프레임의 컬럼명은 `소요대수`다. 화면 라벨 때문에 원본
# 컬럼명을 바꾸지 않는다.
BOTTLENECK_HOVER_TEMPLATE = (
    "<b>%{customdata[0]} · %{customdata[1]}</b>"
    "<br>확보율 %{customdata[2]}"
    "<br>가용대수 %{customdata[3]}"
    "<br>필요대수 %{customdata[4]}"
    "<br>Wafer Capa %{customdata[5]}"
    "<extra></extra>"
)


def _capacity_color(rate: float, *, secure_threshold: float, warning_threshold: float) -> str:
    """확보율을 확보·경고·부족 상태색으로 바꾼다."""
    if rate > secure_threshold:
        return tokens.STATUS_SECURE
    if rate >= warning_threshold:
        return tokens.STATUS_WARNING
    return tokens.STATUS_SHORTAGE


def bottleneck_bar_ratio(rate: object) -> float:
    """확보율을 상세 B/N 가로막대의 길이 비율(0~1)로 정규화한다.

    자르는 것은 막대 길이뿐이다. hover 에 뜨는 확보율 숫자는 150% 를 넘어도 실제 값
    그대로 보여준다.
    """
    if bool(pd.isna(cast(Any, rate))):
        return 0.0
    span = BOTTLENECK_BAR_MAX_RATE - BOTTLENECK_BAR_MIN_RATE
    ratio = (float(cast(Any, rate)) - BOTTLENECK_BAR_MIN_RATE) / span
    return min(max(ratio, 0.0), 1.0)


def _text_width_units(text: str) -> float:
    """글자 크기 1px 기준의 렌더 폭. 전각 1.0, 반각 0.6 으로 센다.

    Ambiguous(`A`) 도 전각으로 센다. 말줄임 `…` 와 `±`·`×` 가 여기 속하는데, 한글 face 는
    이들을 전각으로 그리므로 반각으로 세면 잘라 낸 이름이 다시 칸을 넘는다.
    """
    return sum(
        1.0 if unicodedata.east_asian_width(character) in {"F", "W", "A"} else 0.6
        for character in text
    )


def bottleneck_name_layout(value: object) -> tuple[str, int]:
    """공정명을 월 칸 안에 들어가는 표시 문자열과 글자 크기로 바꾼다.

    글자 크기를 폭 예산으로 먼저 정하고, 그래도 넘치면 뒤에서부터 잘라 말줄임을 붙인다.
    쓸 수 있는 폭은 월 칸 폭에서 이름 앵커 인셋을 뺀 만큼이다.
    """
    process = str(value)
    width_units = _text_width_units(process)
    font_size = max(
        BOTTLENECK_NAME_MIN_FONT_PX,
        min(
            BOTTLENECK_NAME_MAX_FONT_PX,
            round(BOTTLENECK_NAME_WIDTH_BUDGET_PX / max(width_units, 1.0)),
        ),
    )
    available_px = tokens.MONTH_COLUMN_WIDTH_PX * (1.0 - BOTTLENECK_NAME_INSET_RATIO)
    if width_units * font_size <= available_px:
        return process, font_size
    unit_budget = available_px / font_size - _text_width_units(BOTTLENECK_NAME_ELLIPSIS)
    kept: list[str] = []
    used = 0.0
    for character in process:
        character_units = _text_width_units(character)
        if used + character_units > unit_budget:
            break
        kept.append(character)
        used += character_units
    return "".join(kept) + BOTTLENECK_NAME_ELLIPSIS, font_size


def format_bottleneck_process_name(value: object) -> str:
    """공정명을 월 칸 폭에 맞춘 글자 크기의 `text` 마크업으로 만든다."""
    display_text, font_size = bottleneck_name_layout(value)
    return f'<span style="font-size:{font_size}px">{html.escape(display_text)}</span>'


# 증감이 이 값보다 작으면 적지 않는다. 화면에 보이는 자릿수에서 달라지지 않은 칸까지
# `+0.00` 을 달면 무엇이 움직였는지 오히려 안 읽힌다.
_GAP_EPSILON = 5e-3


def _aligned_by_label(frame: pd.DataFrame | None, month_labels: list[str]) -> pd.DataFrame | None:
    """월 축 라벨 차례로 프레임을 맞춘다. 축에 없는 칸은 결측이 된다."""
    if frame is None or "년월" not in frame.columns:
        return None
    return frame.set_index(frame["년월"].astype("string")).reindex(month_labels)


def _axis_series(frame: pd.DataFrame | None, column: str) -> list[float | None]:
    """칸마다 값 하나. 결측은 `None` 이라 Plotly 가 선을 끊는다."""
    if frame is None or column not in frame.columns:
        return []
    return [None if pd.isna(value) else float(value) for value in frame[column]]


def _axis_values(
    frame: pd.DataFrame,
    month_labels: list[str],
    totals: Mapping[str, Mapping[str, float]],
    column: str,
    number_format: str,
    *,
    scale: float = 1.0,
) -> list[str]:
    """표 한 행의 칸 글자. 연간 Total 칸은 미리 더해 둔 값에서 꺼낸다."""
    values = frame[column] if column in frame.columns else pd.Series(dtype="float64")
    rendered: list[str] = []
    for label, value in zip(month_labels, values, strict=True):
        total = totals.get(label, {}).get(column)
        amount = total if total is not None else value
        rendered.append("" if pd.isna(amount) else number_format.format(float(amount) / scale))
    return rendered


def _value_gaps(
    current: pd.DataFrame,
    baseline: pd.DataFrame | None,
    column: str,
    number_format: str,
    *,
    scale: float = 1.0,
) -> list[str] | None:
    """칸마다 적을 증감 문구. 기준이 없거나 달라진 칸이 없으면 `None` 이다."""
    if baseline is None or column not in current.columns or column not in baseline.columns:
        return None
    differences = (
        pd.to_numeric(current[column], errors="coerce").to_numpy()
        - pd.to_numeric(baseline[column], errors="coerce").to_numpy()
    ) / scale
    gaps = [
        "" if pd.isna(value) or abs(value) < _GAP_EPSILON else number_format.format(value)
        for value in differences
    ]
    return gaps if any(gaps) else None


def _bottleneck_rate_labels(
    bottleneck_capacity: pd.DataFrame,
    baseline: pd.DataFrame | None,
) -> list[str]:
    """막대 안 확보율 글자. 선행 전 기준이 있으면 그 위에 증감을 작게 얹는다.

    `texttemplate` 대신 칸마다 문자열을 만든다 — 한 trace 안에서 어떤 칸만 두 줄이 되고
    글자 크기도 달라야 하는데 서식 문자열 하나로는 그렇게 나눌 수 없다.
    """
    rates = pd.to_numeric(bottleneck_capacity["확보율"], errors="coerce")
    if baseline is None or "확보율" not in baseline.columns:
        return [_bar_rate_text(rate) for rate in rates]
    base_rates = pd.to_numeric(
        bottleneck_capacity[["생산계획년월"]].merge(
            baseline[["생산계획년월", "확보율"]], on="생산계획년월", how="left"
        )["확보율"],
        errors="coerce",
    )
    labels: list[str] = []
    for rate, base_rate in zip(rates, base_rates, strict=True):
        if pd.isna(rate):
            labels.append("")
            continue
        body = _bar_rate_text(rate)
        difference = rate - base_rate if pd.notna(base_rate) else float("nan")
        if pd.isna(difference) or abs(difference) < _GAP_EPSILON:
            labels.append(body)
            continue
        color = delta_color(f"{difference:+.0%}")
        gap = f'<span style="color:{color}">{difference * 100:+.0f}%</span>'
        labels.append(f"{gap}<br>{body}")
    return labels


def _bar_rate_text(rate: float) -> str:
    """막대 안 확보율 한 줄.

    trace 의 글자 크기는 증감 크기로 낮추고 값만 span 으로 키운다. Plotly 는 `<br>` 줄
    간격을 **요소의 글자 크기**로 정하므로, 값 크기를 그대로 두면 증감이 값에서 한 줄
    높이(약 29px)만큼 떨어져 따로 노는 글자로 읽힌다.
    """
    if pd.isna(rate):
        return ""
    return f'<span style="font-size:{LOB_BAR_LABEL_FONT_SIZE_PX}px"><b>{rate:.0%}</b></span>'


def build_lob_summary_figures(
    *,
    monthly_density: pd.DataFrame,
    monthly_top5: pd.DataFrame,
    bottleneck_capacity: pd.DataFrame,
    lob_summary: pd.DataFrame,
    month_labels: list[str],
    secure_threshold: float,
    warning_threshold: float,
    process_labels: ProcessLabels | None = None,
    baseline_lob_summary: pd.DataFrame | None = None,
    comparison_density: pd.DataFrame | None = None,
    comparison_wafer: pd.DataFrame | None = None,
    year_totals: Mapping[str, Mapping[str, float]] | None = None,
) -> tuple[go.Figure, go.Figure]:
    """생산계획·Wafer Capa·Bottleneck 요약 Figure 한 쌍을 만든다.

    `process_labels` 는 **화면 문자열에만** 쓴다. 프레임의 `공정` 값은 그대로 두므로
    월 위치 계산과 확보율 색 판정은 원본을 본다.

    `baseline_lob_summary` 는 선행 반영 **전**의 같은 요약이다. 주면 Density·Wafer 계획
    칸에 증감을 값 **위**에 작게 얹고 생산계획 LOB 에 기존 계획을 점선으로 함께 그린다.
    Wafer Capa 는 `계획 × 확보율` 이라 선행 전후가 정확히 같으므로 증감을 적지 않는다.

    `comparison_density`·`comparison_wafer` 는 비교 시나리오의 같은 월별 표다. 주면 값
    **아래**에 증감을 적는다. 위아래를 나눠 둔 것은 한 칸에 둘이 함께 붙을 수 있어서다.
    """
    labels = process_labels or ProcessLabels()
    totals = dict(year_totals or {})
    # 월 축의 근거는 `month_labels` 하나뿐이다. 연간 Total 칸이 끼면 프레임의 행 수와 칸
    # 수가 더는 같지 않으므로 라벨로 맞춘다. 맞추고 나면 Total 칸은 결측이라 증감도
    # 자연히 비고, 그것이 맞다 — 합계 칸에 전월 대비를 적을 자리는 없다.
    if "년월" not in lob_summary.columns:
        raise ValueError("LOB 요약에 월 축을 맞출 `년월` 컬럼이 없습니다.")
    aligned_summary = _aligned_by_label(lob_summary, month_labels)
    aligned_baseline = _aligned_by_label(baseline_lob_summary, month_labels)
    aligned_comparison_density = _aligned_by_label(comparison_density, month_labels)
    aligned_comparison_wafer = _aligned_by_label(comparison_wafer, month_labels)
    assert aligned_summary is not None
    density_gaps = _value_gaps(aligned_summary, aligned_baseline, "부하량", "{:+,.2f}")
    wafer_plan_gaps = _value_gaps(
        aligned_summary, aligned_baseline, "Wafer 부하량", "{:+,.0f}K", scale=1_000
    )
    density_comparison_gaps = _value_gaps(
        aligned_summary, aligned_comparison_density, "부하량", "{:+,.2f}"
    )
    wafer_plan_comparison_gaps = _value_gaps(
        aligned_summary, aligned_comparison_wafer, "Wafer 부하량", "{:+,.0f}K", scale=1_000
    )
    month_positions = list(range(len(month_labels)))
    month_position_by_value = {
        int(month): index
        for index, month in enumerate(aligned_summary["생산계획년월"])
        if pd.notna(month)
    }
    value_fills = [
        tokens.SURFACE_YEAR_TOTAL if label in totals else tokens.SURFACE for label in month_labels
    ]
    subplot_options = {
        "rows": 3,
        "cols": 1,
        "specs": [[{"type": "table"}], [{"type": "xy"}], [{"type": "xy"}]],
        "shared_xaxes": False,
        "vertical_spacing": 0,
        "row_heights": [
            LOB_TABLE_HEIGHT_PX,
            LOB_CHART_HEIGHT_PX,
            LOB_TOP5_HEIGHT_PX,
        ],
    }
    label_figure = make_subplots(**subplot_options)
    month_figure = make_subplots(**subplot_options)
    label_table_rows = (
        ("구분", tokens.HEADER_BACKGROUND, 21, True),
        ("Density (억Gb)", tokens.SURFACE_CLASSIFICATION, 20, True),
        ("Wafer 계획", tokens.SURFACE_CLASSIFICATION, 20, True),
        ("Wafer Capa", tokens.SURFACE_CLASSIFICATION, 20, True),
    )
    month_table_rows = (
        (
            [f"{month}" for month in month_labels],
            tokens.HEADER_BACKGROUND,
            21,
            True,
            None,
            None,
        ),
        (
            _axis_values(aligned_summary, month_labels, totals, "부하량", "{:,.2f}"),
            value_fills,
            LOB_VALUE_FONT_SIZE_PX,
            False,
            density_gaps,
            density_comparison_gaps,
        ),
        (
            _axis_values(
                aligned_summary, month_labels, totals, "Wafer 부하량", "{:,.0f}K", scale=1_000
            ),
            value_fills,
            LOB_VALUE_FONT_SIZE_PX,
            False,
            wafer_plan_gaps,
            wafer_plan_comparison_gaps,
        ),
        (
            # Wafer Capa 는 연간 Total 을 적지 않는다. 월별 Capa 의 단순 합은 연간 Capa 가
            # 아니다 — 더해 놓으면 그 해 투입 가능량으로 읽힌다.
            _axis_values(aligned_summary, month_labels, {}, "Wafer Capa", "{:,.0f}K", scale=1_000),
            value_fills,
            20,
            False,
            None,
            None,
        ),
    )
    lob_chart_domain = cast(Any, month_figure.layout.yaxis).domain
    full_table_domain = (float(lob_chart_domain[1]), 1.0)
    lob_table_domains = fixed_row_domains(
        float(full_table_domain[0]),
        float(full_table_domain[1]),
        LOB_TABLE_ROW_HEIGHTS_PX,
    )
    for row_domain, (value, fill_color, font_size, bold) in zip(
        lob_table_domains,
        label_table_rows,
        strict=True,
    ):
        add_fixed_table_row(
            label_figure,
            domain=row_domain,
            values=[value],
            fill_color=fill_color,
            font_size=font_size,
            bold=bold,
        )
    # 라벨 칸과 이름을 나눈다. 월 칸은 연간 Total 만 달리 칠하려고 칸별 면색 목록을 받는데,
    # 같은 이름을 쓰면 검사기가 라벨 칸의 단일 색 타입으로 고정한다.
    for row_domain, (
        month_values,
        month_fill,
        month_font_size,
        month_bold,
        gaps,
        lower_gaps,
    ) in zip(lob_table_domains, month_table_rows, strict=True):
        add_fixed_table_row(
            month_figure,
            domain=row_domain,
            values=month_values,
            fill_color=month_fill,
            font_size=month_font_size,
            bold=month_bold,
            gaps=gaps,
            lower_gaps=lower_gaps,
        )
    if bottleneck_capacity["B/N Capa"].notna().any():
        month_figure.add_trace(
            go.Bar(
                name="B/N 공정",
                x=[month_position_by_value[month] for month in bottleneck_capacity["생산계획년월"]],
                y=bottleneck_capacity["B/N Capa"],
                customdata=bottleneck_capacity[["년월", "확보율"]].assign(
                    공정=labels.series(bottleneck_capacity["공정"])
                ),
                text=_bottleneck_rate_labels(bottleneck_capacity, baseline_lob_summary),
                textposition="inside",
                insidetextanchor="start",
                # 값은 `_bar_rate_text` 가 span 으로 키운다. 여기 크기는 줄 간격을 정한다.
                textfont={
                    "color": tokens.TEXT,
                    "size": tokens.DELTA_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY_NUMERIC,
                },
                marker={
                    "color": [
                        _capacity_color(
                            rate,
                            secure_threshold=secure_threshold,
                            warning_threshold=warning_threshold,
                        )
                        for rate in bottleneck_capacity["확보율"]
                    ],
                    "line": {"color": tokens.LINE, "width": 1.2},
                },
                hovertemplate=(
                    "%{customdata[0]} · B/N %{customdata[2]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[1]:.1%}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )
    if baseline_lob_summary is not None:
        # 기존 계획은 비교용이라 표식과 라벨을 지운다. 두 줄 모두 값을 적으면 숫자가
        # 겹쳐 어느 쪽이 지금 기준인지 읽히지 않는다.
        month_figure.add_trace(
            go.Scatter(
                name="Density (선행 전)",
                x=month_positions,
                y=_axis_series(aligned_baseline, "부하량"),
                customdata=month_labels,
                mode="lines",
                line={"color": tokens.TEXT_MUTED, "width": 2, "dash": "dot"},
                cliponaxis=False,
                hovertemplate="%{customdata} · 선행 전<br>%{y:,.2f} 억Gb<extra></extra>",
            ),
            row=2,
            col=1,
        )
    month_figure.add_trace(
        go.Scatter(
            name="Density",
            x=month_positions,
            # 연간 Total 칸에서는 선을 끊는다. 합계 칸을 가로지르면 그 값이 그 달의 계획인
            # 것처럼 읽힌다.
            y=_axis_series(aligned_summary, "부하량"),
            customdata=month_labels,
            mode="lines+markers+text",
            text=_axis_series(aligned_summary, "부하량"),
            texttemplate="<b>%{text:,.2f}</b>",
            textposition="top center",
            textfont={"size": 20, "color": tokens.TEXT, "family": tokens.FONT_FAMILY_NUMERIC},
            line={"color": tokens.LINE, "width": 3},
            marker={
                "color": tokens.SURFACE,
                "size": 8,
                "line": {"color": tokens.LINE, "width": 2.0},
            },
            cliponaxis=False,
            hovertemplate="%{customdata}<br>%{y:,.2f} 억Gb<extra></extra>",
        ),
        row=2,
        col=1,
    )
    top5_annotations: list[dict[str, Any]] = []
    if not monthly_top5.empty:
        top5_axis_max = max(float(monthly_top5["B/N Capa"].max()) * 1.8, 1.0)
        wafer_capa_label_y = top5_axis_max * 0.04
        slot_offsets = {1: -0.36, 2: -0.18, 3: 0.0, 4: 0.18, 5: 0.36}
        top5_positions = [
            month_position_by_value[month] + slot_offsets[int(rank)]
            for month, rank in zip(monthly_top5["생산계획년월"], monthly_top5["순위"], strict=True)
        ]
        month_figure.add_trace(
            go.Bar(
                name="B/N Capa Top 5",
                x=top5_positions,
                y=monthly_top5["B/N Capa"],
                width=0.15,
                customdata=monthly_top5[["년월", "공정", "확보율", "Wafer Capa"]].assign(
                    공정=labels.series(monthly_top5["공정"])
                ),
                marker={
                    "color": [
                        _capacity_color(
                            rate,
                            secure_threshold=secure_threshold,
                            warning_threshold=warning_threshold,
                        )
                        for rate in monthly_top5["확보율"]
                    ],
                    "line": {"color": tokens.LINE, "width": 0.8},
                },
                hovertemplate=(
                    "%{customdata[0]} · %{customdata[1]}"
                    "<br>Capa %{y:,.2f} 억Gb"
                    "<br>확보율 %{customdata[2]:.1%}"
                    "<br>Wafer Capa %{customdata[3]:,.0f} 매"
                    "<extra></extra>"
                ),
                showlegend=False,
            ),
            row=3,
            col=1,
        )
        for x_position, capa, rate in zip(
            top5_positions,
            monthly_top5["B/N Capa"],
            monthly_top5["확보율"],
            strict=True,
        ):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": capa,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"<b>{rate:.0%}</b>",
                    "textangle": 270,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "xshift": -1.0,
                    "yshift": 10.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        for x_position, wafer_capa in zip(top5_positions, monthly_top5["Wafer Capa"], strict=True):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": wafer_capa_label_y,
                    "xref": "x2",
                    "yref": "y2",
                    "text": f"{wafer_capa / 1_000:,.0f}K",
                    "textangle": 270,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "xshift": -1.0,
                    "yshift": -6.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        for x_position, process in zip(top5_positions, monthly_top5["공정"], strict=True):
            top5_annotations.append(
                {
                    "x": x_position,
                    "y": 0,
                    "xref": "x2",
                    "yref": "y2",
                    "text": labels.label(process),
                    "textangle": 270,
                    "xanchor": "right",
                    "yanchor": "top",
                    "xshift": 11.0,
                    "yshift": -8.0,
                    "showarrow": False,
                    "font": {
                        "size": 15,
                        "color": tokens.TEXT_MUTED,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
    common_layout = {
        "height": LOB_FIGURE_HEIGHT_PX,
        "margin": {
            "l": 0,
            "r": 0,
            "t": LOB_TOP_MARGIN_PX,
            "b": LOB_BOTTOM_MARGIN_PX,
            # Plotly 는 그림 밖으로 나가는 글자에 맞춰 여백을 **스스로 늘린다**. 두 Figure 의
            # 글자가 다르므로 늘어나는 양도 달라지고, 그러면 왼쪽 라벨 칸과 월 칸의 행이
            # 어긋난다. 제목 여백 44px 이 그 차이를 가려 주고 있었다. 여백을 적은 대로만
            # 쓰게 해 두 칸이 같은 자리에서 시작하게 한다.
            "autoexpand": False,
        },
        "barmode": "overlay",
        "bargap": 0.16,
        "plot_bgcolor": tokens.CHART_CANVAS,
        "paper_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    label_figure.update_layout(**common_layout, showlegend=False)
    month_figure.update_layout(
        **common_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"color": tokens.TEXT_MUTED, "size": 13},
        },
    )
    append_layout_items(month_figure, annotations=top5_annotations)
    lob_axis_max = max(
        (
            float(value)
            for value in (
                monthly_density["부하량"].max(),
                bottleneck_capacity["B/N Capa"].max(),
            )
            if pd.notna(value)
        ),
        default=1.0,
    )
    lob_axis_max = max(lob_axis_max, 1.0)
    for target_figure in (label_figure, month_figure):
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[0, lob_axis_max * 1.35],
            row=2,
            col=1,
        )
        target_figure.update_yaxes(
            title=None,
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[
                0,
                top5_axis_max if not monthly_top5.empty else 1.0,
            ],
            row=3,
            col=1,
        )
    for row_number in (2, 3):
        month_figure.update_xaxes(
            tickmode="array",
            tickvals=month_positions,
            ticktext=month_labels,
            showticklabels=False,
            title=None,
            showgrid=False,
            range=[-0.5, max(len(month_positions) - 0.5, 0.5)],
            domain=[0.0, 1.0],
            row=row_number,
            col=1,
        )
        label_figure.update_xaxes(
            showticklabels=False,
            title=None,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
            row=row_number,
            col=1,
        )
    panel_bottom = -0.28
    lob_y_domain = month_figure.layout.yaxis.domain
    top5_y_domain = month_figure.layout.yaxis2.domain
    table_y_domain = (lob_table_domains[-1][0], lob_table_domains[0][1])
    append_layout_items(
        label_figure,
        annotations=[
            {
                "x": 0.5,
                "y": (lob_y_domain[0] + lob_y_domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>생산계획 LOB</b>",
                "showarrow": False,
                "font": {
                    "size": 20,
                    "color": tokens.TEXT_MUTED,
                    "family": tokens.FONT_FAMILY,
                },
            },
            {
                "x": 0.5,
                "y": (top5_y_domain[0] + top5_y_domain[1]) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>B/N Top 5</b>",
                "showarrow": False,
                "font": {
                    "size": 20,
                    "color": tokens.TEXT_MUTED,
                    "family": tokens.FONT_FAMILY,
                },
            },
        ],
    )
    horizontal_boundaries = [
        panel_bottom,
        (top5_y_domain[1] + lob_y_domain[0]) / 2,
        (lob_y_domain[1] + table_y_domain[0]) / 2,
        1.0,
    ]
    horizontal_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": y_boundary,
            "y1": y_boundary,
            "xref": "paper",
            "yref": "paper",
            "line": {
                "color": tokens.BORDER_STRONG if boundary_index in {1, 2} else tokens.BORDER,
                "width": tokens.OUTER_BORDER_WIDTH_PX
                if boundary_index in {1, 2}
                else tokens.GRID_LINE_WIDTH_PX,
            },
            "layer": "above" if boundary_index in {1, 2} else "below",
        }
        for boundary_index, y_boundary in enumerate(horizontal_boundaries)
    ]
    append_layout_items(
        label_figure,
        shapes=[
            *[
                {
                    "type": "rect",
                    "x0": 0,
                    "x1": 1,
                    "y0": y0,
                    "y1": y1,
                    "xref": "paper",
                    "yref": "paper",
                    "fillcolor": tokens.SURFACE_CLASSIFICATION,
                    "line": {"width": 0},
                    "layer": "below",
                }
                for y0, y1 in (
                    (horizontal_boundaries[0], horizontal_boundaries[1]),
                    (horizontal_boundaries[1], horizontal_boundaries[2]),
                )
            ],
            *[
                {
                    "type": "line",
                    "x0": x_boundary,
                    "x1": x_boundary,
                    "y0": panel_bottom,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                    "layer": "below",
                }
                for x_boundary in (0.0, 1.0)
            ],
            *horizontal_shapes,
        ],
    )
    append_layout_items(
        month_figure,
        shapes=[
            *[
                {
                    "type": "line",
                    "x0": index / len(month_labels),
                    "x1": index / len(month_labels),
                    "y0": panel_bottom,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                    "layer": "below",
                }
                for index in range(1, len(month_labels))
            ],
            *horizontal_shapes,
        ],
    )
    add_figure_outer_border(
        label_figure,
        y0=panel_bottom,
        emphasize_bottom=True,
        compensate_bottom=False,
    )
    add_figure_outer_border(
        month_figure,
        y0=panel_bottom,
        emphasize_left=False,
        emphasize_bottom=True,
        compensate_bottom=False,
    )
    lob_row_boundaries = (
        (lob_table_domains[0][0], tokens.OUTER_BORDER_WIDTH_PX, tokens.BORDER_STRONG),
        (lob_table_domains[1][0], tokens.GRID_LINE_WIDTH_PX, tokens.BORDER),
        (lob_table_domains[2][0], tokens.GRID_LINE_WIDTH_PX, tokens.BORDER),
    )
    lob_row_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": boundary_y,
            "y1": boundary_y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": boundary_color, "width": boundary_width},
            "layer": "above",
        }
        for boundary_y, boundary_width, boundary_color in lob_row_boundaries
    ]
    append_layout_items(label_figure, shapes=lob_row_shapes)
    # 차트 두 칸(생산계획 LOB·B/N Top 5)의 연간 Total 열. 표 칸은 행마다 칠했지만 차트는
    # 면이 하나라 여기서 세로 띠로 덮는다. 막대·꺾은선이 없는 칸이라 겹칠 것도 없다.
    total_column_shapes = [
        {
            "type": "rect",
            "x0": index / max(len(month_labels), 1),
            "x1": (index + 1) / max(len(month_labels), 1),
            "y0": panel_bottom,
            "y1": lob_table_domains[-1][0],
            "xref": "paper",
            "yref": "paper",
            "fillcolor": tokens.SURFACE_YEAR_TOTAL,
            "line": {"width": 0},
            "layer": "below",
        }
        for index, label in enumerate(month_labels)
        if label in totals
    ]
    append_layout_items(month_figure, shapes=[*total_column_shapes, *lob_row_shapes])
    add_quarter_boundaries(month_figure, month_labels, y0=panel_bottom)
    flush_layout_items(label_figure, month_figure)
    return label_figure, month_figure


def _detail_month_cell_values(
    displayed_detail: pd.DataFrame,
    month: str,
    comparison_detail: pd.DataFrame | None = None,
) -> tuple[list[str], list[str]]:
    """한 달의 세부수량 값과 그 아래 증감을 따로 돌려준다. 없는 달은 빈 칸이다.

    증감을 값과 한 칸에 담지 않는 이유는 두 가지다. 칸 안에서 `<br>` 로 줄을 더하면 값이
    칸 가운데 정렬 탓에 위로 올라가 왼쪽 분류 칸과 눈높이가 어긋나고, Plotly 가 줄 상자
    두 개에 고정 여백을 더한 높이를 요구해 행이 필요 이상으로 두꺼워진다. 값은 한 줄로
    두고 증감은 주석으로 얹는다.
    """
    if month not in displayed_detail.columns:
        return [""] * len(displayed_detail), [""] * len(displayed_detail)
    values = [
        "" if pd.isna(value) or float(value) == 0 else f"{float(value):,.0f}K"
        for value in displayed_detail[month]
    ]
    if comparison_detail is None:
        return values, [""] * len(values)
    comparison_values = (
        pd.to_numeric(comparison_detail[month], errors="coerce")
        if month in comparison_detail.columns
        else pd.Series([pd.NA] * len(displayed_detail), index=displayed_detail.index)
    )
    current_values = pd.to_numeric(displayed_detail[month], errors="coerce")
    gaps: list[str] = []
    for value, current, before in zip(values, current_values, comparison_values, strict=True):
        # 한쪽에만 있는 조합은 없는 쪽을 0 으로 본다. 비교의 목적이 사라지거나 새로 생긴
        # 제품을 보이게 하는 것이라 그 전액이 증감이어야 한다.
        current_amount = 0.0 if pd.isna(current) else float(current)
        before_amount = 0.0 if pd.isna(before) else float(before)
        difference = current_amount - before_amount
        if not value or abs(difference) < 0.5:
            gaps.append("")
            continue
        gaps.append(f"{difference:+,.0f}K")
    return values, gaps


def build_plan_detail_figures(
    *,
    production_detail: pd.DataFrame,
    month_labels: list[str],
    detail_dimensions: list[str] | None = None,
    comparison_detail: pd.DataFrame | None = None,
    year_total_labels: Sequence[str] = (),
) -> tuple[go.Figure, go.Figure]:
    """분류별 계획 세부수량 Figure 한 쌍을 만든다.

    `detail_dimensions` 는 왼쪽 분류 칸을 정한다. 기본은 제품·Stack 이고 `상세` 를 켜면
    거래선이 더해진다. 머리글과 칸 폭은 컬럼 이름에서 끌어오므로 분류가 늘어도 여기서
    다시 적을 것이 없다.
    """
    dimensions = list(detail_dimensions or PRODUCTION_DETAIL_DIMENSIONS)
    # 조회 범위의 모든 달을 컬럼으로 유지한다. 세부 데이터에 없는 달을 빼면 컬럼 수가
    # 줄어드는데 Figure 폭은 `len(month_labels)` 로 잡으므로, 컬럼 폭이 100px 그리드보다
    # 넓어져 헤더가 뒤로 갈수록 밀린다. 요약표와 월이 세로로 어긋나기도 한다.
    detail_month_columns = list(month_labels)
    displayed_detail = production_detail.copy()
    detail_dimension_values = [
        ["" if pd.isna(value) else str(value) for value in displayed_detail[column]]
        for column in dimensions
    ]
    grouped_dimension_values = [values.copy() for values in detail_dimension_values]
    for dimension_index, values in enumerate(grouped_dimension_values):
        previous_prefix: tuple[str, ...] | None = None
        for row_index in range(len(displayed_detail)):
            current_prefix = tuple(
                detail_dimension_values[prefix_index][row_index]
                for prefix_index in range(dimension_index + 1)
            )
            if row_index > 0 and current_prefix == previous_prefix:
                values[row_index] = ""
            previous_prefix = current_prefix
    detail_group_indices: list[int] = []
    detail_group_starts: list[int] = []
    previous_product: str | None = None
    group_index = -1
    product_values = detail_dimension_values[0] if detail_dimension_values else []
    for row_index, product in enumerate(product_values):
        if row_index == 0 or product != previous_product:
            group_index += 1
            if row_index > 0:
                detail_group_starts.append(row_index)
        detail_group_indices.append(group_index)
        previous_product = product

    detail_label_row_colors = [
        tokens.SURFACE_CLASSIFICATION
        if group_number % 2 == 0
        else tokens.SURFACE_CLASSIFICATION_GROUP
        for group_number in detail_group_indices
    ]
    detail_month_row_colors = [
        tokens.SURFACE if group_number % 2 == 0 else tokens.SURFACE_SUBTLE
        for group_number in detail_group_indices
    ]
    # 값 한 줄과 그 아래 증감 한 줄이 온전히 들어가는 높이. 증감이 없어도 같은 높이를 쓴다.
    detail_row_height = lower_delta_row_height(DETAIL_VALUE_FONT_SIZE_PX)
    detail_header_height = table_row_height(DETAIL_HEADER_FONT_SIZE_PX)
    # 제목 자리를 Figure 가 갖지 않는다. `계획 세부수량` 은 Plotly 주석이 아니라 Streamlit
    # 이 그려서 그 옆에 「상세」 토글을 둔다. 두 칸 모두 같은 높이의 줄을 끼우므로 여백을
    # 남겨 두면 표 위에 빈 띠만 생긴다.
    detail_figure_height = detail_header_height + max(len(displayed_detail), 1) * detail_row_height
    detail_label_figure = go.Figure(
        go.Table(
            columnwidth=[DETAIL_DIMENSION_WIDTHS.get(column, 1.0) for column in dimensions],
            header={
                "values": [
                    f"<b>{DETAIL_DIMENSION_HEADERS.get(column, column)}</b>"
                    for column in dimensions
                ],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": DETAIL_HEADER_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_header_height,
            },
            cells={
                "values": grouped_dimension_values,
                "align": "center",
                "fill_color": [detail_label_row_colors for _ in dimensions],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": DETAIL_VALUE_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_row_height,
            },
        )
    )
    detail_month_cells = [
        _detail_month_cell_values(displayed_detail, month, comparison_detail)
        for month in detail_month_columns
    ]
    detail_month_figure = go.Figure(
        go.Table(
            columnwidth=[1.0] * len(detail_month_columns),
            header={
                "values": [f"<b>{month}</b>" for month in detail_month_columns],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": DETAIL_HEADER_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_header_height,
            },
            cells={
                "values": [values for values, _ in detail_month_cells],
                "align": "center",
                "fill_color": [
                    [tokens.SURFACE_YEAR_TOTAL] * len(detail_month_row_colors)
                    if month in year_total_labels
                    else detail_month_row_colors
                    for month in detail_month_columns
                ],
                "line_color": TRANSPARENT_COLOR,
                "font": {
                    "color": tokens.TEXT,
                    "size": DETAIL_VALUE_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": detail_row_height,
            },
        )
    )
    detail_layout = {
        "height": detail_figure_height,
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        "paper_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    detail_label_figure.update_layout(**detail_layout)
    detail_month_figure.update_layout(
        **detail_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
    # 경계선 비율의 분모는 Figure 높이와 **같은 수**여야만 맞는다. 이름을 둘로 두면 한쪽
    # 행 높이만 고쳤을 때 머리글 밑줄과 그룹 경계가 조용히 어긋난다.
    detail_header_boundary_y = 1 - detail_header_height / detail_figure_height
    add_figure_outer_border(detail_label_figure, emphasize_bottom=True)
    add_figure_outer_border(
        detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    detail_header_shape = {
        "type": "line",
        "x0": 0,
        "x1": 1,
        "y0": detail_header_boundary_y,
        "y1": detail_header_boundary_y,
        "xref": "paper",
        "yref": "paper",
        "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
        "layer": "above",
    }
    append_layout_items(
        detail_label_figure,
        shapes=[
            detail_header_shape,
            {
                "type": "line",
                "x0": 1.4 / 2.0,
                "x1": 1.4 / 2.0,
                "y0": 0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                "layer": "above",
            },
        ],
    )
    append_layout_items(
        detail_month_figure,
        shapes=[
            detail_header_shape,
            *[
                {
                    "type": "line",
                    "x0": month_index / len(detail_month_columns),
                    "x1": month_index / len(detail_month_columns),
                    "y0": 0,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                    "layer": "above",
                }
                for month_index in range(1, len(detail_month_columns))
            ],
        ],
    )
    add_quarter_boundaries(detail_month_figure, detail_month_columns)
    # 증감은 칸 안의 둘째 줄이 아니라 값 아래에 얹는 주석이다. 칸이 값 한 줄만 담으므로
    # 행 높이가 한 줄짜리 칸의 최소 높이로 줄고, 증감이 붙든 말든 값은 같은 자리에 선다.
    # 기준점은 행의 **위 모서리**다 — Plotly 가 한 줄짜리 칸의 글자를 위에 붙여 그린다.
    detail_delta_yshift = lower_delta_yshift_px(DETAIL_VALUE_FONT_SIZE_PX)
    append_layout_items(
        detail_month_figure,
        annotations=[
            {
                "x": (month_index + 0.5) / len(detail_month_columns),
                "y": 1
                - (detail_header_height + row_index * detail_row_height) / detail_figure_height,
                "xref": "paper",
                "yref": "paper",
                "text": gap,
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "yshift": detail_delta_yshift,
                "font": {
                    "color": delta_color(gap),
                    "size": tokens.DELTA_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY_NUMERIC,
                },
            }
            for month_index, (_, gaps) in enumerate(detail_month_cells)
            for row_index, gap in enumerate(gaps)
            if gap
        ],
    )
    detail_group_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": 1
            - (detail_header_height + group_start * detail_row_height) / detail_figure_height,
            "y1": 1
            - (detail_header_height + group_start * detail_row_height) / detail_figure_height,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.GROUP_BORDER_WIDTH_PX},
            "layer": "above",
        }
        for group_start in detail_group_starts
    ]
    append_layout_items(detail_label_figure, shapes=detail_group_shapes)
    append_layout_items(detail_month_figure, shapes=detail_group_shapes)
    flush_layout_items(detail_label_figure, detail_month_figure)
    return detail_label_figure, detail_month_figure


def build_bottleneck_detail_figures(
    *,
    monthly_bottleneck_details: pd.DataFrame,
    month_labels: list[str],
    secure_threshold: float,
    warning_threshold: float,
    process_labels: ProcessLabels | None = None,
    year_total_labels: Sequence[str] = (),
) -> tuple[go.Figure, go.Figure]:
    """월별 B/N 상위 공정을 순위별 가로막대로 그린 Figure 한 쌍을 만든다.

    행 축은 공정이 아니라 순위다. 순위는 `services/dashboard.py` 가 달마다 독립으로
    매기므로 같은 행의 각 칸은 매달 다른 공정이고, 월별 열 그리드와 확보율 오름차순
    정렬이 충돌하지 않는다.

    막대는 확보율 80~150% 구간만 표현한다. 그래서 상위 순위는 대부분 막대가 0 길이다.
    공정명을 막대 안에 넣으면 가장 심각한 병목의 이름이 사라지므로, 이름은 막대와
    별개의 trace 로 각 칸 왼쪽 고정 앵커에 그린다.
    """
    labels = process_labels or ProcessLabels()
    month_count = max(len(month_labels), 1)
    month_positions = {label: index for index, label in enumerate(month_labels)}

    def format_equipment_count(value: object) -> str:
        if bool(pd.isna(cast(Any, value))):
            return "-"
        return f"{float(cast(Any, value)):,.1f}대"

    def format_wafer_capa(value: object) -> str:
        if bool(pd.isna(cast(Any, value))):
            return "-"
        return f"{float(cast(Any, value)) / 1_000:,.0f}K"

    # 월 축의 근거는 `month_labels` 하나뿐이다. 세부 프레임의 월 목록으로 칸을 만들면
    # 데이터가 없는 달에서 열 수와 Figure 폭이 갈라져 헤더가 밀린다.
    # 순위 상한은 서비스가 정본이다. 여기서 다시 자르면 근거가 둘로 갈라진다.
    displayed = monthly_bottleneck_details.loc[
        monthly_bottleneck_details["년월"].astype("string").isin(month_labels)
    ]
    # 행 수는 조회기간에서 유효 공정이 가장 많은 달을 따른다. 그보다 적은 달은 남는
    # 칸을 비운다.
    rank_count = 1 if displayed.empty else max(int(displayed["순위"].max()), 1)
    table_height = BOTTLENECK_DETAIL_HEADER_HEIGHT_PX + rank_count * BOTTLENECK_DETAIL_ROW_HEIGHT_PX
    # 제목 자리를 Figure 가 갖지 않는다. `상세 B/N 공정` 은 Plotly 주석이 아니라 Streamlit
    # 이 그린다 — 주석이 잡던 44px 과 Streamlit 줄의 높이가 달라 세 구획의 제목·표 간격이
    # 제각각이었다. 세 구획 모두 같은 줄 컴포넌트를 쓰면 간격이 하나로 맞는다.
    figure_height = table_height
    track_length = 1.0 - 2 * BOTTLENECK_BAR_SIDE_INSET_RATIO

    track_bases: list[float] = []
    track_centers: list[float] = []
    track_lengths: list[float] = []
    hover_values: list[list[str]] = []
    bar_bases: list[float] = []
    bar_centers: list[float] = []
    bar_lengths: list[float] = []
    bar_colors: list[str] = []
    name_positions: list[float] = []
    name_texts: list[str] = []
    for _, row in displayed.iterrows():
        month_index = month_positions[str(row["년월"])]
        rank = int(row["순위"])
        center_y = (
            table_height
            - BOTTLENECK_DETAIL_HEADER_HEIGHT_PX
            - (rank - 0.5) * BOTTLENECK_DETAIL_ROW_HEIGHT_PX
        )
        base = month_index + BOTTLENECK_BAR_SIDE_INSET_RATIO
        rate = row["확보율"]
        missing_rate = bool(pd.isna(cast(Any, rate)))
        track_bases.append(base)
        track_centers.append(center_y)
        track_lengths.append(track_length)
        hover_values.append(
            [
                html.escape(str(row["년월"])),
                html.escape(labels.label(row["공정"])),
                "-" if missing_rate else f"{float(rate):.1%}",
                format_equipment_count(row["가용대수"]),
                format_equipment_count(row["소요대수"]),
                format_wafer_capa(row["Wafer Capa"]),
            ]
        )
        name_positions.append(month_index + BOTTLENECK_NAME_INSET_RATIO)
        name_texts.append(format_bottleneck_process_name(labels.label(row["공정"])))
        ratio = bottleneck_bar_ratio(rate)
        if ratio <= 0:
            continue
        bar_bases.append(base)
        bar_centers.append(center_y)
        bar_lengths.append(ratio * track_length)
        bar_colors.append(
            _capacity_color(
                float(rate),
                secure_threshold=secure_threshold,
                warning_threshold=warning_threshold,
            )
        )

    bottleneck_detail_label_figure = go.Figure(
        go.Table(
            columnwidth=[1.0],
            header={
                "values": ["<b>B/N</b>"],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": 15,
                    "family": tokens.FONT_FAMILY,
                },
                "height": BOTTLENECK_DETAIL_HEADER_HEIGHT_PX,
            },
            cells={
                "values": [[str(rank) for rank in range(1, rank_count + 1)]],
                "align": "center",
                "fill_color": tokens.SURFACE_CLASSIFICATION,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": 14,
                    "family": tokens.FONT_FAMILY,
                },
                "height": BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
            },
        )
    )
    bottleneck_detail_month_figure = go.Figure(
        [
            # 보이지 않는 hover 표적. 눈에 보이는 트랙 막대는 행 높이보다 낮고 좌우
            # 인셋만큼 짧아 칸 가장자리에서 툴팁이 뜨지 않는다. 행 전체를 덮는 이
            # 막대가 표적이므로 막대가 0 길이인 칸에서도 칸 어디서나 값이 뜬다.
            go.Bar(
                x=[1.0] * len(track_centers),
                y=track_centers,
                base=[position - BOTTLENECK_BAR_SIDE_INSET_RATIO for position in track_bases],
                orientation="h",
                width=BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
                marker={"color": tokens.HIT_TARGET, "line": {"width": 0}},
                customdata=hover_values,
                hovertemplate=BOTTLENECK_HOVER_TEMPLATE,
                showlegend=False,
            ),
            go.Bar(
                x=track_lengths,
                y=track_centers,
                base=track_bases,
                orientation="h",
                width=BOTTLENECK_DETAIL_BAR_HEIGHT_PX,
                marker={
                    "color": tokens.BAR_TRACK,
                    "line": {"color": tokens.BORDER_STRONG, "width": tokens.GRID_LINE_WIDTH_PX},
                },
                hoverinfo="skip",
                showlegend=False,
            ),
            go.Bar(
                x=bar_lengths,
                y=bar_centers,
                base=bar_bases,
                orientation="h",
                width=BOTTLENECK_DETAIL_BAR_HEIGHT_PX,
                marker={
                    "color": bar_colors,
                    "line": {"color": tokens.LINE, "width": tokens.BAR_OUTLINE_WIDTH_PX},
                },
                hoverinfo="skip",
                showlegend=False,
            ),
            go.Scatter(
                x=name_positions,
                y=track_centers,
                mode="text",
                text=name_texts,
                textposition="middle right",
                textfont={
                    "color": tokens.TEXT,
                    "size": BOTTLENECK_NAME_MAX_FONT_PX,
                    "family": tokens.FONT_FAMILY,
                },
                hoverinfo="skip",
                showlegend=False,
            ),
        ]
    )
    bottleneck_detail_layout = {
        "height": figure_height,
        "margin": {
            "l": 0,
            "r": 0,
            "t": 0,
            "b": 0,
        },
        "paper_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    bottleneck_detail_label_figure.update_layout(**bottleneck_detail_layout)
    # 축 눈금으로 마진이 자동 확장되면 paper 0~1 이 표 영역과 어긋나 경계선 계산이
    # 전부 밀린다. 두 축 모두 `fixedrange` 여야 hover 를 켜도 드래그 확대가 붙지 않는다.
    hidden_axis = {
        "domain": [0.0, 1.0],
        "showgrid": False,
        "zeroline": False,
        "showline": False,
        "showticklabels": False,
        "ticks": "",
        "automargin": False,
        "fixedrange": True,
    }
    bottleneck_detail_month_figure.update_layout(
        **bottleneck_detail_layout,
        width=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        autosize=False,
        barmode="overlay",
        bargap=0,
        plot_bgcolor=tokens.SURFACE,
        showlegend=False,
        dragmode=False,
        hovermode="closest",
        hoverlabel={
            "bgcolor": tokens.SURFACE,
            "bordercolor": tokens.BORDER_STRONG,
            "font": {"color": tokens.TEXT, "size": 12, "family": tokens.FONT_FAMILY},
        },
        xaxis={**hidden_axis, "range": [0, month_count]},
        yaxis={**hidden_axis, "range": [0, table_height]},
    )
    header_boundary_y = 1 - BOTTLENECK_DETAIL_HEADER_HEIGHT_PX / table_height
    # 행 사이는 얇은 격자선으로 긋는다. 20행에 바깥 테두리 굵기를 쓰면 격자가 내용보다
    # 무거워진다. 머리글 밑줄만 굵게 남겨 위계를 지킨다.
    bottleneck_boundary_shapes = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": header_boundary_y,
            "y1": header_boundary_y,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
            "layer": "above",
        },
        *[
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": 1
                - (
                    BOTTLENECK_DETAIL_HEADER_HEIGHT_PX
                    + rank_index * BOTTLENECK_DETAIL_ROW_HEIGHT_PX
                )
                / table_height,
                "y1": 1
                - (
                    BOTTLENECK_DETAIL_HEADER_HEIGHT_PX
                    + rank_index * BOTTLENECK_DETAIL_ROW_HEIGHT_PX
                )
                / table_height,
                "xref": "paper",
                "yref": "paper",
                "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                "layer": "above",
            }
            for rank_index in range(1, rank_count)
        ],
    ]
    add_figure_outer_border(
        bottleneck_detail_label_figure,
        emphasize_bottom=True,
    )
    add_figure_outer_border(
        bottleneck_detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    append_layout_items(bottleneck_detail_label_figure, shapes=bottleneck_boundary_shapes)
    # `go.Table` 이 그려 주던 머리글 띠·셀 격자를 카테시안에서는 직접 그린다.
    append_layout_items(
        bottleneck_detail_month_figure,
        shapes=[
            {
                "type": "rect",
                "x0": 0,
                "x1": 1,
                "y0": header_boundary_y,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "fillcolor": tokens.HEADER_BACKGROUND,
                "line": {"width": 0},
                "layer": "below",
            },
            # 연간 Total 칸은 데이터가 없어 비지만, 비었다는 것과 그 칸이 합계 자리라는
            # 것은 다른 이야기다. 머리글 아래 본문만 살짝 어둡게 칠해 알린다.
            *[
                {
                    "type": "rect",
                    "x0": month_positions[label] / month_count,
                    "x1": (month_positions[label] + 1) / month_count,
                    "y0": 0,
                    "y1": header_boundary_y,
                    "xref": "paper",
                    "yref": "paper",
                    "fillcolor": tokens.SURFACE_YEAR_TOTAL,
                    "line": {"width": 0},
                    "layer": "below",
                }
                for label in year_total_labels
                if label in month_positions
            ],
            *[
                {
                    "type": "line",
                    "x0": month_index / month_count,
                    "x1": month_index / month_count,
                    "y0": 0,
                    "y1": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
                    "layer": "above",
                }
                for month_index in range(1, month_count)
            ],
            *bottleneck_boundary_shapes,
        ],
        annotations=[
            {
                "x": (month_index + 0.5) / month_count,
                "y": (1 + header_boundary_y) / 2,
                "xref": "paper",
                "yref": "paper",
                "text": f"<b>{html.escape(month)}</b>",
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "font": {"color": tokens.TEXT, "size": 15, "family": tokens.FONT_FAMILY},
            }
            for month_index, month in enumerate(month_labels)
        ],
    )
    add_quarter_boundaries(bottleneck_detail_month_figure, month_labels)
    flush_layout_items(bottleneck_detail_label_figure, bottleneck_detail_month_figure)
    return bottleneck_detail_label_figure, bottleneck_detail_month_figure
