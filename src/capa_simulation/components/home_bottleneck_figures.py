# Purpose: 월별 B/N 상위 공정을 순위별 가로막대로 그린 Figure 한 쌍을 만든다.

"""상세 B/N 공정 Figure.

행 축은 공정이 아니라 **순위**다. 순위는 서비스가 달마다 독립으로 매기므로 같은 행의 각
칸은 매달 다른 공정이고, 월별 열 그리드와 확보율 오름차순 정렬이 충돌하지 않는다.
격자 크롬은 주요공정 히트맵과 같은 조각(`home_figure_common` 의 `_grid_*`)을 쓴다.
"""

from __future__ import annotations

import html
from collections.abc import Collection, Sequence
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.home_dimensions import (
    BOTTLENECK_DETAIL_BAR_HEIGHT_PX,
    BOTTLENECK_DETAIL_HEADER_HEIGHT_PX,
    BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
)
from capa_simulation.components.home_figure_common import (
    BOTTLENECK_NAME_ELLIPSIS,
    BOTTLENECK_RANK_FONT_SIZE_PX,
    BOTTLENECK_RANK_HEADER_FONT_SIZE_PX,
    _capacity_color,
    _execution_hover_note,
    _format_equipment_count,
    _format_wafer_capa,
    _grid_hover_target_bar,
    _grid_label_header_annotation,
    _grid_label_table_figure,
    _grid_layout,
    _grid_month_chrome_shapes,
    _grid_month_header_annotations,
    _grid_month_layout_options,
    _grid_row_rules,
    _text_width_units,
    _truncate_to_units,
)
from capa_simulation.components.plotly_layout import (
    add_figure_outer_border,
    add_quarter_boundaries,
    append_layout_items,
    flush_layout_items,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import tokens

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
# **바닥을 올리면 그만큼 이름이 잘린다.** 칸에 쓸 수 있는 폭이 93px 로 정해져 있어 바닥이
# 8 이면 11.63 폭 단위까지, 9 면 10.33 단위까지만 온전히 들어간다. 그 사이(한글 약 11자)의
# 공정명은 바닥을 올리는 순간 전체 이름에서 말줄임으로 바뀐다. 로컬 표본은 합성이라 실제
# 공정명의 길이 분포를 여기서 알 수 없으므로, 읽기 쉬움보다 이름이 온전한 쪽을 택한다.
# 전체 이름은 hover 에 잘리지 않고 뜬다(`BOTTLENECK_HOVER_TEMPLATE` 의 `customdata`).
BOTTLENECK_NAME_MIN_FONT_PX = 8
BOTTLENECK_NAME_MAX_FONT_PX = 12

# 공정명을 행 한가운데로 내리는 보정. `go.Scatter` 의 `textposition="middle *"` 는 글자
# 상자 가운데가 아니라 **베이스라인**을 기준점에서 0.25×글자크기 아래에 놓는다. 라틴
# 이름은 디센더 칸이 대개 비어 있어 그 결과 잉크가 행 가운데보다 위로 뜬다 — 브라우저에서
# 재니 12px 에서 평균 1.8px 이었다. 한 상수로 완전히 맞출 수는 없다(이름에 g·p 가 있으면
# 1.7px 덜 뜬다). 평균을 0 에 맞추는 값이다.
BOTTLENECK_NAME_INK_DROP_RATIO = 0.15

# `필요대수`는 화면 라벨이고 프레임의 컬럼명은 `소요대수`다. 화면 라벨 때문에 원본
# 컬럼명을 바꾸지 않는다.
BOTTLENECK_HOVER_TEMPLATE = (
    "<b>%{customdata[0]} · %{customdata[1]}</b>"
    "<br>확보율 %{customdata[2]}"
    "<br>가용대수 %{customdata[3]}"
    "<br>필요대수 %{customdata[4]}"
    "<br>Wafer Capa %{customdata[5]}"
    # 조정이 없으면 빈 문자열이라 아무 줄도 붙지 않는다. 가용·필요대수는 기준정보 값
    # 그대로이므로, 확보율과 어긋나 보이는 까닭을 이 줄이 밝힌다.
    "%{customdata[6]}"
    "<extra></extra>"
)


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
    return _truncate_to_units(process, unit_budget), font_size


def format_bottleneck_process_name(value: object) -> str:
    """공정명을 월 칸 폭에 맞춘 글자 크기의 `text` 마크업으로 만든다."""
    display_text, font_size = bottleneck_name_layout(value)
    return f'<span style="font-size:{font_size}px">{html.escape(display_text)}</span>'


def build_bottleneck_detail_figures(
    *,
    monthly_bottleneck_details: pd.DataFrame,
    month_labels: list[str],
    secure_threshold: float,
    warning_threshold: float,
    process_labels: ProcessLabels | None = None,
    year_total_labels: Sequence[str] = (),
    past_month_labels: Collection[str] | None = None,
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
    bar_outline_widths: list[float] = []
    # 실행 Capa 반영으로 줄거나 늘어난 구간. 조정이 한 건도 없으면 비어 있고, 그때는
    # 아래에서 trace 자체를 만들지 않아 그림이 조정 전과 픽셀 단위로 같다.
    delta_bases: list[float] = []
    delta_centers: list[float] = []
    delta_lengths: list[float] = []
    delta_colors: list[str] = []
    increase_bases: list[float] = []
    increase_centers: list[float] = []
    increase_lengths: list[float] = []
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
                _format_equipment_count(row["가용대수"]),
                _format_equipment_count(row["소요대수"]),
                _format_wafer_capa(row["Wafer Capa"]),
                _execution_hover_note(
                    row.get("확보율 증감"),
                    row.get("실행 비고"),
                ),
            ]
        )
        name_positions.append(month_index + BOTTLENECK_NAME_INSET_RATIO)
        name_texts.append(format_bottleneck_process_name(labels.label(row["공정"])))
        ratio = bottleneck_bar_ratio(rate)
        # 기준 비율은 조정 전이다. 컬럼이 없으면(계약을 넓히기 전 호출) 조정 0 으로 본다.
        baseline_ratio = bottleneck_bar_ratio(row.get("기준 확보율", rate))
        grew = baseline_ratio < ratio
        if baseline_ratio != ratio:
            # 증감 영역은 두 비율 사이 구간이다. 테두리를 두지 않는 것이 규칙이라
            # 아래에서 `line.width = 0` 으로 그린다.
            delta_bases.append(base + min(baseline_ratio, ratio) * track_length)
            delta_centers.append(center_y)
            delta_lengths.append(abs(ratio - baseline_ratio) * track_length)
            delta_colors.append(tokens.DELTA_AREA_INCREASE if grew else tokens.DELTA_AREA_DECREASE)
        if grew:
            # 늘어난 경우 테두리는 **연두 영역까지 포함해** 결과값 전체를 두른다. 값 막대
            # 자신의 테두리를 끄고, 채움이 없는 막대를 위에 얹어 한 줄로 두른다.
            increase_bases.append(base)
            increase_centers.append(center_y)
            increase_lengths.append(ratio * track_length)
        # 값 막대는 두 비율 중 **짧은 쪽**까지다. 줄었으면 결과값까지(적분홍 제외),
        # 늘었으면 기준값까지 — 그 위를 연두가 잇는다.
        drawn_ratio = min(baseline_ratio, ratio)
        if drawn_ratio <= 0:
            continue
        bar_bases.append(base)
        bar_centers.append(center_y)
        bar_lengths.append(drawn_ratio * track_length)
        bar_outline_widths.append(0.0 if grew else tokens.BAR_OUTLINE_WIDTH_PX)
        bar_colors.append(
            _capacity_color(
                float(rate),
                secure_threshold=secure_threshold,
                warning_threshold=warning_threshold,
            )
        )

    bottleneck_detail_label_figure = _grid_label_table_figure(
        rank_count,
        header_height=BOTTLENECK_DETAIL_HEADER_HEIGHT_PX,
        row_height=BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
        cell_font_size=BOTTLENECK_RANK_FONT_SIZE_PX,
    )
    # 조정이 한 건이라도 있을 때만 증감 trace 를 끼운다. 빈 trace 를 항상 넣으면 조정
    # 0건에서도 Figure 구성이 달라져, 「조정이 없으면 오늘과 픽셀 단위로 같다」는 계약이
    # 깨진다.
    detail_month_traces: list[Any] = [
        _grid_hover_target_bar(
            track_centers,
            [position - BOTTLENECK_BAR_SIDE_INSET_RATIO for position in track_bases],
            row_height=BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
            customdata=hover_values,
            hovertemplate=BOTTLENECK_HOVER_TEMPLATE,
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
    ]
    if delta_centers:
        # 줄거나 늘어난 구간 자체. **테두리가 없다** — 규칙상 감소분은 테두리 밖이고,
        # 증가분은 아래 결과값 테두리가 통째로 두른다.
        detail_month_traces.append(
            go.Bar(
                x=delta_lengths,
                y=delta_centers,
                base=delta_bases,
                orientation="h",
                width=BOTTLENECK_DETAIL_BAR_HEIGHT_PX,
                marker={"color": delta_colors, "line": {"width": 0}},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    detail_month_traces.append(
        go.Bar(
            x=bar_lengths,
            y=bar_centers,
            base=bar_bases,
            orientation="h",
            width=BOTTLENECK_DETAIL_BAR_HEIGHT_PX,
            marker={
                "color": bar_colors,
                # 증가 행이 없으면 굵기가 모두 같다. 그때는 스칼라를 그대로 둬서 Figure
                # 규격이 조정 전과 한 글자도 다르지 않게 한다.
                "line": {
                    "color": tokens.LINE,
                    "width": (
                        bar_outline_widths if increase_centers else tokens.BAR_OUTLINE_WIDTH_PX
                    ),
                },
            },
            hoverinfo="skip",
            showlegend=False,
        )
    )
    if increase_centers:
        # 늘어난 결과값 **전체**를 두르는 테두리. 채움이 없어야 아래 연두가 비친다.
        detail_month_traces.append(
            go.Bar(
                x=increase_lengths,
                y=increase_centers,
                base=increase_bases,
                orientation="h",
                width=BOTTLENECK_DETAIL_BAR_HEIGHT_PX,
                marker={
                    "color": tokens.TRANSPARENT,
                    "line": {"color": tokens.LINE, "width": tokens.BAR_OUTLINE_WIDTH_PX},
                },
                hoverinfo="skip",
                showlegend=False,
            )
        )
    detail_month_traces.append(
        go.Scatter(
            x=name_positions,
            # 데이터 1 = 1px 이다(여백 0, Figure 높이 = 표 높이).
            y=[
                center - BOTTLENECK_NAME_MAX_FONT_PX * BOTTLENECK_NAME_INK_DROP_RATIO
                for center in track_centers
            ],
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
        )
    )
    bottleneck_detail_month_figure = go.Figure(detail_month_traces)
    bottleneck_detail_layout = _grid_layout(figure_height)
    bottleneck_detail_label_figure.update_layout(**bottleneck_detail_layout)
    bottleneck_detail_month_figure.update_layout(
        **bottleneck_detail_layout,
        **_grid_month_layout_options(
            month_labels, month_count=month_count, table_height=table_height
        ),
    )
    header_boundary_y = 1 - BOTTLENECK_DETAIL_HEADER_HEIGHT_PX / table_height
    bottleneck_boundary_shapes = _grid_row_rules(
        rank_count,
        header_height=BOTTLENECK_DETAIL_HEADER_HEIGHT_PX,
        row_height=BOTTLENECK_DETAIL_ROW_HEIGHT_PX,
        table_height=table_height,
    )
    add_figure_outer_border(
        bottleneck_detail_label_figure,
        emphasize_bottom=True,
    )
    add_figure_outer_border(
        bottleneck_detail_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )
    # 표 칸은 비워 두고 머리글·순위 글자를 행 한가운데를 직접 가리키는 주석으로 얹는다.
    # 여백이 0 이고 Figure 높이가 `table_height` 와 같아 paper 1.0 이 곧 표 전체다 —
    # 아래 주석과 `bottleneck_boundary_shapes` 가 같은 분모를 본다.
    append_layout_items(
        bottleneck_detail_label_figure,
        shapes=bottleneck_boundary_shapes,
        annotations=[
            _grid_label_header_annotation(
                "<b>B/N</b>",
                header_boundary_y=header_boundary_y,
                font_size=BOTTLENECK_RANK_HEADER_FONT_SIZE_PX,
            ),
            *[
                {
                    "x": 0.5,
                    "y": 1
                    - (
                        BOTTLENECK_DETAIL_HEADER_HEIGHT_PX
                        + (rank - 0.5) * BOTTLENECK_DETAIL_ROW_HEIGHT_PX
                    )
                    / table_height,
                    "xref": "paper",
                    "yref": "paper",
                    "text": str(rank),
                    "showarrow": False,
                    "xanchor": "center",
                    # 세로도 보정하지 않는다. 순위 칸은 숫자만 있어 잉크 가운데가 줄
                    # 상자 가운데와 같다(브라우저에서 실측). `value_ink_yshift_px` 는
                    # 한글이 섞인 LOB 표용 보정이라 여기 쓰면 1.5px 위로 지나친다.
                    "yanchor": "middle",
                    "font": {
                        "color": tokens.TEXT,
                        "size": BOTTLENECK_RANK_FONT_SIZE_PX,
                        "family": tokens.FONT_FAMILY,
                    },
                }
                for rank in range(1, rank_count + 1)
            ],
        ],
    )
    append_layout_items(
        bottleneck_detail_month_figure,
        shapes=[
            *_grid_month_chrome_shapes(
                month_labels,
                month_count=month_count,
                header_boundary_y=header_boundary_y,
                vertical_line_y0=0,
                year_totals=year_total_labels,
                past_month_labels=past_month_labels,
            ),
            # 머리글 밑줄과 순위 행 경계는 **양쪽 Figure 가 같아야** 왼쪽 순위 칸과
            # 오른쪽 막대가 같은 줄에서 끊긴다.
            *bottleneck_boundary_shapes,
        ],
        annotations=_grid_month_header_annotations(
            month_labels, month_count=month_count, header_boundary_y=header_boundary_y
        ),
    )
    add_quarter_boundaries(bottleneck_detail_month_figure, month_labels)
    flush_layout_items(bottleneck_detail_label_figure, bottleneck_detail_month_figure)
    return bottleneck_detail_label_figure, bottleneck_detail_month_figure
