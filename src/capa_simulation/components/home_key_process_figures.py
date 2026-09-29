# Purpose: 고른 주요 공정의 월별 확보율을 색 격자로 그린 Figure 한 쌍을 만든다.

"""주요공정 확보율 히트맵 Figure.

**행 축이 공정이라는 점이 상세 B/N 과 다르다.** 한 줄이 끝까지 같은 공정이라 부족이
시작되는 달이 가로로 읽힌다. 격자 크롬은 상세 B/N 과 같은 조각
(`home_figure_common` 의 `_grid_*`)을 쓴다.
"""

from __future__ import annotations

import html
from collections.abc import Collection, Sequence
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    KEY_PROCESS_CELL_GAP_PX,
    KEY_PROCESS_CELL_HEIGHT_PX,
    KEY_PROCESS_HEADER_HEIGHT_PX,
    KEY_PROCESS_NAME_FONT_SIZE_PX,
    KEY_PROCESS_NAME_INSET_PX,
    KEY_PROCESS_RATE_FONT_SIZE_PX,
    KEY_PROCESS_ROW_HEIGHT_PX,
)
from capa_simulation.components.home_figure_common import (
    BOTTLENECK_NAME_ELLIPSIS,
    BOTTLENECK_RANK_HEADER_FONT_SIZE_PX,
    _capacity_color,
    _execution_hover_note,
    _format_equipment_count,
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
from capa_simulation.services.month_columns import month_label

KEY_PROCESS_HOVER_TEMPLATE = (
    "<b>%{customdata[0]} · %{customdata[1]}</b>"
    "<br>확보율 %{customdata[2]}"
    "<br>가용대수 %{customdata[3]}"
    "<br>필요대수 %{customdata[4]}"
    # 조정이 없으면 빈 문자열이라 아무 줄도 붙지 않는다.
    "%{customdata[5]}"
    "<extra></extra>"
)

KEY_PROCESS_EMPTY_NOTICE = "Preference 탭에서 주요 공정을 고르세요"
# 프리셋에 공정은 있는데 이 시나리오·조회기간에 하나도 없을 때. 「고르세요」는 거짓 안내다.
KEY_PROCESS_ABSENT_NOTICE = "고른 프리셋의 공정이 이 시나리오·조회기간에 없습니다"


def _key_process_name_markup(value: object) -> str:
    """라벨 칸 폭(`DASHBOARD_LABEL_COLUMN_WIDTH_PX`)에 맞춰 자른 공정명.

    상세 B/N 의 `bottleneck_name_layout` 은 **월 칸 폭**(100px) 예산이라 여기 쓰면 260px
    칸에서 이름이 필요 이상으로 작아지고 일찍 잘린다. 잘린 전체 이름은 hover 에 뜬다.
    """
    process = str(value)
    available_px = DASHBOARD_LABEL_COLUMN_WIDTH_PX - 2 * KEY_PROCESS_NAME_INSET_PX
    unit_budget = available_px / KEY_PROCESS_NAME_FONT_SIZE_PX
    if _text_width_units(process) <= unit_budget:
        return html.escape(process)
    unit_budget -= _text_width_units(BOTTLENECK_NAME_ELLIPSIS)
    return html.escape(_truncate_to_units(process, unit_budget))


def build_key_process_heatmap_figures(
    *,
    securement_rate: pd.DataFrame,
    key_processes: Sequence[str],
    month_labels: list[str],
    secure_threshold: float,
    warning_threshold: float,
    process_labels: ProcessLabels | None = None,
    year_total_labels: Sequence[str] = (),
    past_month_labels: Collection[str] | None = None,
    empty_notice: str = KEY_PROCESS_EMPTY_NOTICE,
) -> tuple[go.Figure, go.Figure]:
    """고른 주요 공정의 월별 확보율을 색 격자로 그린 Figure 한 쌍을 만든다.

    그릴 공정이 없으면 `empty_notice` 한 줄을 남긴다 — 프리셋이 없을 때와 프리셋의 공정이 이
    화면에 없을 때 할 일이 달라 부르는 쪽이 고른다.

    **행 축이 공정이라는 점이 상세 B/N 과 다르다.** 상세 B/N 의 행은 순위라 같은 줄이
    매달 다른 공정이고, 그래서 「이 공정이 언제부터 무너지나」를 가로로 읽을 수 없다.
    여기서는 한 줄이 끝까지 같은 공정이라 부족이 시작되는 달이 가로로 보인다. 행 차례는
    사용자가 고른 차례 그대로다 — 확보율로 다시 정렬하면 매달 행이 뛰어다닌다.

    `go.Heatmap` 을 쓰지 않는다. 그 trace 는 칸 폭을 Plotly 가 정해 100px 월 격자·paper
    경계선과 맞지 않는다. 상세 B/N 과 같은 가로막대 방식이면 칠과 hover 가 한 trace 로
    끝나고, 색 판정도 `_capacity_color` 하나에서 나온다.

    **연간 Total 칸은 그리지 않는다.** 확보율은 합산도 평균도 할 수 없다 — 그 해 평균은
    부하량 가중이 필요한데 이 프레임에 근거가 없다. `Wafer Capa` 가 연간 Total 을 적지
    않는 것과 같은 규칙이고, 그 열은 면색만 깔아 「합계 자리」임을 알린다.
    """
    labels = process_labels or ProcessLabels()
    month_count = max(len(month_labels), 1)
    month_positions = {label: index for index, label in enumerate(month_labels)}
    processes = list(key_processes)
    row_count = max(len(processes), 1)
    table_height = KEY_PROCESS_HEADER_HEIGHT_PX + row_count * KEY_PROCESS_ROW_HEIGHT_PX
    # 칸은 열을 꽉 채우고 좌우로 1px 씩만 띈다. 그 틈이 격자선 노릇을 하므로 칸에 테두리를
    # 두르지 않는다 — 테두리를 두르면 색이 면이 아니라 칩으로 읽힌다.
    cell_inset = KEY_PROCESS_CELL_GAP_PX / tokens.MONTH_COLUMN_WIDTH_PX
    cell_length = 1.0 - 2 * cell_inset

    # 월 축의 근거는 `month_labels` 하나뿐이다. 자기 프레임의 월 목록으로 열을 만들면
    # 데이터가 없는 달에서 열 수와 Figure 폭이 갈라져 머리글이 뒤로 갈수록 밀린다.
    # 연간 Total 라벨은 `securement_rate` 에 없는 `년월` 이라 이 필터에서 자연히 빠진다.
    if processes and not securement_rate.empty:
        frame = securement_rate.loc[securement_rate["공정"].astype("string").isin(processes)].copy()
        frame["년월"] = [month_label(int(value)) for value in frame["생산계획년월"]]
        displayed = frame.loc[frame["년월"].isin(month_labels)]
    else:
        displayed = securement_rate.iloc[0:0].assign(년월="")

    row_by_process = {process: index for index, process in enumerate(processes)}
    cell_bases: list[float] = []
    cell_centers: list[float] = []
    cell_colors: list[str] = []
    hover_values: list[list[str]] = []
    rate_positions: list[float] = []
    rate_centers: list[float] = []
    rate_texts: list[str] = []
    for _, row in displayed.iterrows():
        month_index = month_positions[str(row["년월"])]
        row_index = row_by_process[str(row["공정"])]
        center_y = (
            table_height
            - KEY_PROCESS_HEADER_HEIGHT_PX
            - (row_index + 0.5) * KEY_PROCESS_ROW_HEIGHT_PX
        )
        rate = row["확보율"]
        missing_rate = bool(pd.isna(cast(Any, rate)))
        cell_bases.append(month_index + cell_inset)
        cell_centers.append(center_y)
        cell_colors.append(
            tokens.SURFACE
            if missing_rate
            else _capacity_color(
                float(rate),
                secure_threshold=secure_threshold,
                warning_threshold=warning_threshold,
            )
        )
        hover_values.append(
            [
                html.escape(str(row["년월"])),
                # 라벨 칸이 말줄임했을 때 전체 이름을 볼 유일한 자리다.
                html.escape(labels.label(row["공정"])),
                "-" if missing_rate else f"{float(rate):.1%}",
                _format_equipment_count(row.get("가용대수")),
                _format_equipment_count(row.get("소요대수")),
                _execution_hover_note(row.get("확보율 증감"), row.get("실행 비고")),
            ]
        )
        if not missing_rate:
            # 색만으로 뜻을 나르지 않는다. 칸마다 숫자가 있어야 색각이상·흑백에서도 읽힌다.
            rate_positions.append(month_index + 0.5)
            rate_centers.append(center_y)
            rate_texts.append(f"{float(rate):.0%}")

    key_process_label_figure = _grid_label_table_figure(
        row_count,
        header_height=KEY_PROCESS_HEADER_HEIGHT_PX,
        row_height=KEY_PROCESS_ROW_HEIGHT_PX,
        cell_font_size=KEY_PROCESS_NAME_FONT_SIZE_PX,
    )
    key_process_month_figure = go.Figure(
        [
            _grid_hover_target_bar(
                cell_centers,
                [position - cell_inset for position in cell_bases],
                row_height=KEY_PROCESS_ROW_HEIGHT_PX,
                customdata=hover_values,
                hovertemplate=KEY_PROCESS_HOVER_TEMPLATE,
            ),
            go.Bar(
                x=[cell_length] * len(cell_centers),
                y=cell_centers,
                base=cell_bases,
                orientation="h",
                width=KEY_PROCESS_CELL_HEIGHT_PX,
                # 테두리 없음. 1px 틈이 이미 칸을 가르고, 선을 두르면 히트맵이 아니라
                # 칸마다 테두리를 두른 표가 된다.
                marker={"color": cell_colors, "line": {"width": 0}},
                hoverinfo="skip",
                showlegend=False,
            ),
            go.Scatter(
                x=rate_positions,
                y=rate_centers,
                mode="text",
                text=rate_texts,
                textposition="middle center",
                textfont={
                    "color": tokens.TEXT,
                    "size": KEY_PROCESS_RATE_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY_NUMERIC,
                },
                hoverinfo="skip",
                showlegend=False,
            ),
        ]
    )
    key_process_layout = _grid_layout(table_height)
    key_process_label_figure.update_layout(**key_process_layout)
    key_process_month_figure.update_layout(
        **key_process_layout,
        **_grid_month_layout_options(
            month_labels, month_count=month_count, table_height=table_height
        ),
    )
    header_boundary_y = 1 - KEY_PROCESS_HEADER_HEIGHT_PX / table_height
    # 행 경계선은 **라벨 칸에만** 긋는다. 왼쪽은 이름이 줄줄이 선 표라 줄을 갈라야 읽히지만,
    # 오른쪽은 히트맵이다 — 칸 사이 1px 틈이 이미 경계를 만들고, 그 위에 선을 또 그으면
    # 색의 면이 격자에 잘려 지도가 아니라 표로 읽힌다.
    label_row_shapes = _grid_row_rules(
        row_count,
        header_height=KEY_PROCESS_HEADER_HEIGHT_PX,
        row_height=KEY_PROCESS_ROW_HEIGHT_PX,
        table_height=table_height,
    )
    header_underline = label_row_shapes[0]
    add_figure_outer_border(key_process_label_figure, emphasize_bottom=True)
    add_figure_outer_border(
        key_process_month_figure,
        emphasize_left=False,
        emphasize_bottom=True,
    )

    def name_annotation(row_index: int, text: str, color: str) -> dict[str, Any]:
        return {
            # 구분 칸은 네 구획이 세로로 잇는 **한 열**이다. 나머지 셋(`Capa LOB 현황`
            # 의 행 이름, `계획 세부수량` 의 분류, `상세 B/N` 의 순위)과 이 구획의 머리글까지
            # 모두 칸 한가운데에 서므로, 여기만 왼쪽에 붙이면 한 열이 두 규칙으로 읽힌다.
            "x": 0.5,
            "y": 1
            - (KEY_PROCESS_HEADER_HEIGHT_PX + (row_index + 0.5) * KEY_PROCESS_ROW_HEIGHT_PX)
            / table_height,
            "xref": "paper",
            "yref": "paper",
            "text": text,
            "showarrow": False,
            "xanchor": "center",
            "yanchor": "middle",
            "font": {
                "color": color,
                "size": KEY_PROCESS_NAME_FONT_SIZE_PX,
                "family": tokens.FONT_FAMILY,
            },
        }

    # 고른 공정이 없으면 행 한 줄짜리 안내만 남긴다. **Figure 를 빼지는 않는다** —
    # `render_home_figures` 는 정확한 개수를 요구하고, 개수를 분기시키면 두 칸의 정렬
    # 규칙이 두 벌이 된다.
    name_annotations = (
        [
            name_annotation(row_index, _key_process_name_markup(labels.label(process)), tokens.TEXT)
            for row_index, process in enumerate(processes)
        ]
        if processes
        else [name_annotation(0, empty_notice, tokens.TEXT_MUTED)]
    )
    append_layout_items(
        key_process_label_figure,
        shapes=label_row_shapes,
        annotations=[
            _grid_label_header_annotation(
                "<b>주요공정</b>",
                header_boundary_y=header_boundary_y,
                font_size=BOTTLENECK_RANK_HEADER_FONT_SIZE_PX,
            ),
            *name_annotations,
        ],
    )
    # `go.Table` 이 그려 주던 머리글 띠·셀 격자를 카테시안에서는 직접 그린다.
    append_layout_items(
        key_process_month_figure,
        shapes=[
            # 세로 월 경계선은 **머리글 띠 안에서만** 긋는다. 본문까지 내리면 칸 사이
            # 틈과 겹쳐 같은 자리에 선이 두 겹으로 앉는다. 분기 경계는 네 구획이 함께 읽는
            # 기준이라 아래에서 따로 긋는다.
            *_grid_month_chrome_shapes(
                month_labels,
                month_count=month_count,
                header_boundary_y=header_boundary_y,
                vertical_line_y0=header_boundary_y,
                year_totals=year_total_labels,
                past_month_labels=past_month_labels,
            ),
            header_underline,
        ],
        annotations=_grid_month_header_annotations(
            month_labels, month_count=month_count, header_boundary_y=header_boundary_y
        ),
    )
    add_quarter_boundaries(key_process_month_figure, month_labels)
    flush_layout_items(key_process_label_figure, key_process_month_figure)
    return key_process_label_figure, key_process_month_figure
