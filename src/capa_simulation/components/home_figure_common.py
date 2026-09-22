# Purpose: HOME Figure 네 가족이 함께 쓰는 판정·서식·paper 좌표 도형 조각을 갖는다.

"""HOME Figure 공용 조각.

가족(요약 LOB·계획 세부수량·주요공정 히트맵·상세 B/N)을 **넘나드는 것만** 여기 둔다 —
확보율 3색 판정, 실행 반영 hover 문구, 과거·연간 Total 면색, paper 좌표 격자 크롬이다.
한 가족만 쓰는 조각은 그 가족 모듈에 남는다.

`tokens` 는 **부를 때** 읽는다. 모듈 수준 dict 나 기본 인자에 색을 담으면 모듈을 처음
임포트한 순간의 팔레트가 굳어 테마 전환이 그 색만 따라오지 못한다.
"""

from __future__ import annotations

import html
import unicodedata
from collections.abc import Collection, Container, Mapping, Sequence
from typing import Any, Final, Literal, cast

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.design import tokens

# 상세 B/N 왼쪽 표의 머리글·순위 글자. `go.Table` 은 칸 글자를 세로 가운데에 세우지
# 못한다 — plotly 6.9 `table.Cells` 에 `valign` 이 없어 한 줄짜리 글자가 칸 위 2.5px 에
# 붙는다. 계획 세부수량 표가 쓰는 빈 `<br>` 우회로는 **이 표에서는 못 쓴다**: 칸 글자에
# `<br>`·`<`·`&`·`>`·공백이 하나라도 있으면 Plotly 가 행 높이 바닥을 `글자상자 + 16px`
# (= `table_row_height`) 로 올려 29px 행이 37px 로 부푼다. 그래서 표 칸은 배경·격자만
# 맡기고 글자는 paper 주석으로 얹는다 — LOB 표의 `add_fixed_table_row` 와 같은 방법이다.
BOTTLENECK_RANK_HEADER_FONT_SIZE_PX = 15
BOTTLENECK_RANK_FONT_SIZE_PX = 14

# 글자 크기가 최소값 바닥에 걸리면 더 줄일 수 없어 렌더 폭이 계속 늘어난다. `go.Scatter`
# 의 text 는 줄바꿈도 칸 단위 클립도 없어 그대로 옆 달 칸을 침범하므로, 남는 한 단계는
# 말줄임이다. 전체 이름은 hover 의 `customdata` 에 잘리지 않고 뜬다.
BOTTLENECK_NAME_ELLIPSIS = "…"


def _execution_note_parts(delta: object, note: object) -> tuple[float, str] | None:
    """실행 반영 문구의 재료. 조정이 없으면 `None` 이라 두 포맷터가 빈 문자열을 낸다.

    마크업은 자리마다 다르지만 「무엇을 조정으로 볼 것인가」는 하나여야 한다 — 한쪽만
    판정을 바꾸면 같은 프레임을 두고 hover 마다 다른 말을 한다.
    """
    if bool(pd.isna(cast(Any, delta))) or float(cast(Any, delta)) == 0.0:
        return None
    label = "" if note is None or bool(pd.isna(cast(Any, note))) else str(note).strip()
    return float(cast(Any, delta)), label


def _execution_hover_note(delta: object, note: object) -> str:
    """hover 끝에 붙일 「실행 반영 ±n%p · 비고」 줄. 조정이 없으면 빈 문자열."""
    parts = _execution_note_parts(delta, note)
    if parts is None:
        return ""
    amount, label = parts
    text = f"<br>실행 반영 {amount:+.1f}%p"
    if label:
        # 비고는 사용자가 적는 자유 텍스트다. 꺾쇠가 들어오면 hover 마크업이 깨진다.
        text += f"<br>비고 {html.escape(label)}"
    return text


def _execution_delta_note(delta: object, note: object) -> str:
    """증감 영역 hover 에 띄울 「실행 반영 ±n%p · 비고」."""
    parts = _execution_note_parts(delta, note)
    if parts is None:
        return ""
    amount, label = parts
    text = f"<b>실행 반영 {amount:+.1f}%p</b>"
    if label:
        text += f"<br>{html.escape(label)}"
    return text


def _format_equipment_count(value: object) -> str:
    """hover 의 대수 한 칸. 값이 없으면 `-` 다."""
    if bool(pd.isna(cast(Any, value))):
        return "-"
    return f"{float(cast(Any, value)):,.1f}대"


def _format_wafer_capa(value: object) -> str:
    """hover 의 Wafer Capa 한 칸. 값이 없으면 `-` 다."""
    if bool(pd.isna(cast(Any, value))):
        return "-"
    return f"{float(cast(Any, value)) / 1_000:,.0f}K"


# 과거 구간에서 바탕색이 갈아타는 짝. 키가 없는 색은 그대로 둔다 — 머리글처럼 과거·현재를
# 나눌 이유가 없는 면까지 눌리면 월 라벨 줄이 구간마다 다른 회색으로 끊긴다.
# **색이 아니라 토큰 이름으로 들고 있는다.** 색으로 굳히면 모듈을 처음 읽은 순간의
# 팔레트가 키가 되어, 테마를 바꾼 뒤에는 어떤 면색도 이 짝에 걸리지 않는다.
_PAST_SURFACE_TOKENS: Final[Mapping[str, str]] = {
    "SURFACE": "SURFACE_PAST",
    "SURFACE_SUBTLE": "SURFACE_PAST_SUBTLE",
    "SURFACE_YEAR_TOTAL": "SURFACE_PAST_YEAR_TOTAL",
}


def _past_surface(surface: str) -> str:
    """그 면색의 과거 구간 짝."""
    for source, past in _PAST_SURFACE_TOKENS.items():
        if surface == getattr(tokens, source):
            return str(getattr(tokens, past))
    return surface


def _month_surface(
    label: str,
    year_totals: Container[str],
    past_month_labels: Collection[str] | None,
    *,
    base: str | None = None,
) -> str:
    """월 칸 하나의 바탕색.

    연간 Total 인지 먼저 보고, 그 위에 과거 여부를 얹는다. 두 성격은 서로 배타가 아니라서
    (과거만 든 해의 Total) 한쪽을 지우면 그 칸이 이웃보다 밝아져 거꾸로 읽힌다.

    **`base` 의 기본값을 `tokens.SURFACE` 로 적지 않는다.** 기본 인자는 `def` 를 읽을 때
    한 번 평가되므로 모듈이 처음 임포트된 순간의 팔레트로 굳는다. 그러면 테마를 바꿔도
    이 색만 따라오지 않고, 프로세스가 어두운 테마로 시작했으면 밝은 테마에서 월 칸이
    어둡게 남는다. `None` 을 받아 **부를 때** 조회한다.
    """
    surface = tokens.SURFACE_YEAR_TOTAL if label in year_totals else (base or tokens.SURFACE)
    if past_month_labels is not None and label in past_month_labels:
        return _past_surface(surface)
    return surface


# 축 눈금으로 마진이 자동 확장되면 paper 0~1 이 표 영역과 어긋나 경계선 계산이 전부
# 밀린다. 두 축 모두 `fixedrange` 여야 hover 를 켜도 드래그 확대가 붙지 않는다.
# **색이 하나도 없어야 모듈 상수로 올릴 수 있다.** `tokens.*` 가 섞이면 처음 임포트한
# 순간의 팔레트가 굳는다.
_HIDDEN_AXIS: Final[Mapping[str, object]] = {
    "domain": [0.0, 1.0],
    "showgrid": False,
    "zeroline": False,
    "showline": False,
    "showticklabels": False,
    "ticks": "",
    "automargin": False,
    "fixedrange": True,
}


def _paper_hrule(
    y: float, *, color: str, width: float, layer: str = "above", x0: float = 0.0
) -> dict[str, Any]:
    """paper 좌표 가로선 하나. 네 구획의 머리글 밑줄·행 경계가 모두 이 꼴이다.

    `x0` 를 주면 그 자리부터 긋는다. 왼쪽 분류 칸을 **가로지르지 않아야** 하는 선이
    있다 — 계획 세부수량의 Stack 경계가 제품 칸을 지나가면 제품 묶음이 끊겨 보인다.

    색·굵기·층을 기본값으로 두지 않는다 — 자리마다 다르고, `tokens.*` 를 기본 인자에
    적으면 `def` 를 읽는 순간의 팔레트로 굳는다.
    """
    return {
        "type": "line",
        "x0": x0,
        "x1": 1,
        "y0": y,
        "y1": y,
        "xref": "paper",
        "yref": "paper",
        "line": {"color": color, "width": width},
        "layer": layer,
    }


def _paper_month_lines(
    month_count: int, *, y0: float, layer: str, y1: float = 1
) -> list[dict[str, Any]]:
    """월 칸을 가르는 세로 경계선. 바깥 두 변은 테두리가 맡으므로 긋지 않는다."""
    return [
        {
            "type": "line",
            "x0": index / month_count,
            "x1": index / month_count,
            "y0": y0,
            "y1": y1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER, "width": tokens.GRID_LINE_WIDTH_PX},
            "layer": layer,
        }
        for index in range(1, month_count)
    ]


def _column_surface_rects(
    month_labels: Sequence[str],
    *,
    y0: float,
    y1: float,
    year_totals: Container[str],
    past_month_labels: Collection[str] | None,
) -> list[dict[str, Any]]:
    """연간 Total·과거 구간 열을 덮는 바탕 띠.

    기본 면색인 열은 아예 그리지 않는다 — 도형 수가 그대로 비용이다. 값 위를 덮지 않게
    `layer: below` 로 깐다.
    """
    count = max(len(month_labels), 1)
    return [
        {
            "type": "rect",
            "x0": index / count,
            "x1": (index + 1) / count,
            "y0": y0,
            "y1": y1,
            "xref": "paper",
            "yref": "paper",
            "fillcolor": surface,
            "line": {"width": 0},
            "layer": "below",
        }
        for index, label in enumerate(month_labels)
        if (surface := _month_surface(label, year_totals, past_month_labels)) != tokens.SURFACE
    ]


def _grid_row_rules(
    row_count: int,
    *,
    header_height: float,
    row_height: float,
    table_height: float,
) -> list[dict[str, Any]]:
    """머리글 밑줄과 그 아래 행 경계선. 첫 원소가 늘 머리글 밑줄이다.

    행 사이는 얇은 격자선으로 긋는다. 20행에 바깥 테두리 굵기를 쓰면 격자가 내용보다
    무거워진다. 머리글 밑줄만 굵게 남겨 위계를 지킨다.
    """
    return [
        _paper_hrule(
            1 - header_height / table_height,
            color=tokens.BORDER_STRONG,
            width=tokens.OUTER_BORDER_WIDTH_PX,
        ),
        *[
            _paper_hrule(
                1 - (header_height + row_index * row_height) / table_height,
                color=tokens.BORDER,
                width=tokens.GRID_LINE_WIDTH_PX,
            )
            for row_index in range(1, row_count)
        ],
    ]


def _grid_month_chrome_shapes(
    month_labels: Sequence[str],
    *,
    month_count: int,
    header_boundary_y: float,
    vertical_line_y0: float,
    year_totals: Container[str],
    past_month_labels: Collection[str] | None,
) -> list[dict[str, Any]]:
    """`go.Table` 이 그려 주던 머리글 띠·열 면색·세로 격자를 카테시안에서 직접 그린다.

    연간 Total 칸은 값을 더할 수 없어 비지만, 비었다는 것과 그 칸이 합계 자리라는 것은
    다른 이야기다. 과거 구간도 마찬가지라 머리글 아래 본문만 한 단계 눌러 칠한다. 이
    Figure 들은 표가 아니라 차트라 줄무늬 대신 열 띠 하나로 덮는다.

    `vertical_line_y0` 만 두 값이다 — 주요공정 히트맵은 칸 사이 1px 틈이 이미 경계를
    만들어 세로선을 머리글 띠 안에서만 긋고, 상세 B/N 은 전체 높이를 가른다. 머리글
    밑줄과 행 경계는 자리마다 달라 **호출자가 뒤에 붙인다**.
    """
    return [
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
        *_column_surface_rects(
            month_labels,
            y0=0,
            y1=header_boundary_y,
            year_totals=year_totals,
            past_month_labels=past_month_labels,
        ),
        *_paper_month_lines(month_count, y0=vertical_line_y0, layer="above"),
    ]


def _grid_month_header_annotations(
    month_labels: Sequence[str], *, month_count: int, header_boundary_y: float
) -> list[dict[str, Any]]:
    """머리글 띠에 세우는 월 라벨. 라벨 칸의 머리글과 같은 눈높이에 선다."""
    return [
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
    ]


def _grid_label_header_annotation(
    text: str, *, header_boundary_y: float, font_size: int
) -> dict[str, Any]:
    """라벨 칸 머리글. 월 머리글 라벨과 같은 식이라 두 칸의 글자가 같은 눈높이에 선다."""
    return {
        "x": 0.5,
        "y": (1 + header_boundary_y) / 2,
        "xref": "paper",
        "yref": "paper",
        "text": text,
        "showarrow": False,
        "xanchor": "center",
        "yanchor": "middle",
        "font": {
            "color": tokens.TEXT,
            "size": font_size,
            "family": tokens.FONT_FAMILY,
        },
    }


def _grid_label_table_figure(
    row_count: int,
    *,
    header_height: float,
    row_height: float,
    cell_font_size: int,
) -> go.Figure:
    """라벨 칸의 빈 표. 배경과 격자만 맡는다.

    `go.Table` 은 칸 글자를 세로 가운데에 세우지 못하고, 칸 글자에 공백 하나만 들어가도
    Plotly 가 행 높이 바닥을 `글자상자 + 16px` 로 올려 설계한 행 높이가 부푼다. 그래서
    글자는 전부 paper 주석으로 따로 얹는다.
    """
    return go.Figure(
        go.Table(
            columnwidth=[1.0],
            header={
                "values": [""],
                "align": "center",
                "fill_color": tokens.HEADER_BACKGROUND,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": BOTTLENECK_RANK_HEADER_FONT_SIZE_PX,
                    "family": tokens.FONT_FAMILY,
                },
                "height": header_height,
            },
            cells={
                "values": [[""] * row_count],
                "align": "center",
                "fill_color": tokens.SURFACE_CLASSIFICATION,
                "line_color": tokens.BORDER,
                "font": {
                    "color": tokens.TEXT,
                    "size": cell_font_size,
                    "family": tokens.FONT_FAMILY,
                },
                "height": row_height,
            },
        )
    )


def _grid_hover_target_bar(
    centers: Sequence[float],
    bases: Sequence[float],
    *,
    row_height: float,
    customdata: Sequence[Sequence[str]],
    hovertemplate: str,
) -> go.Bar:
    """보이지 않는 hover 표적.

    눈에 보이는 칸·막대는 행 높이보다 낮고 좌우 인셋만큼 짧아 칸 가장자리에서 툴팁이
    뜨지 않는다. 행 전체를 덮는 이 막대가 표적이므로 막대가 0 길이인 칸에서도 칸
    어디서나 값이 뜬다.
    """
    return go.Bar(
        x=[1.0] * len(centers),
        y=centers,
        base=bases,
        orientation="h",
        width=row_height,
        marker={"color": tokens.HIT_TARGET, "line": {"width": 0}},
        customdata=customdata,
        hovertemplate=hovertemplate,
        showlegend=False,
    )


def _grid_layout(height: float) -> dict[str, Any]:
    """두 카테시안 격자가 함께 쓰는 바깥 규격. 여백이 0 이라 paper 1.0 이 곧 표 전체다."""
    return {
        "height": height,
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        "paper_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }


def _grid_month_layout_options(
    month_labels: Sequence[str], *, month_count: int, table_height: float
) -> dict[str, Any]:
    """월 Figure 쪽에만 더 붙는 규격.

    축 눈금으로 마진이 자동 확장되면 paper 0~1 이 표 영역과 어긋나 경계선 계산이 전부
    밀린다. 두 축 모두 `fixedrange` 여야 hover 를 켜도 드래그 확대가 붙지 않는다.
    """
    return {
        "width": len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
        "autosize": False,
        "barmode": "overlay",
        "bargap": 0,
        "plot_bgcolor": tokens.SURFACE,
        "showlegend": False,
        "dragmode": False,
        "hovermode": "closest",
        "hoverlabel": {
            "bgcolor": tokens.SURFACE,
            "bordercolor": tokens.BORDER_STRONG,
            "font": {"color": tokens.TEXT, "size": 12, "family": tokens.FONT_FAMILY},
        },
        "xaxis": {**_HIDDEN_AXIS, "range": [0, month_count]},
        "yaxis": {**_HIDDEN_AXIS, "range": [0, table_height]},
    }


def capacity_status(
    rate: float, *, secure_threshold: float, warning_threshold: float
) -> Literal["secure", "warning", "shortage"]:
    """확보율 하나를 확보·경고·부족 세 상태로 판정한다.

    HOME 막대·히트맵의 색, 확보율 히트맵의 계단, 결론 한 줄의 색이 모두 이 부등호 하나를
    본다. 경계를 각자 적으면 한쪽만 바꿨을 때 같은 값을 두고 화면마다 다른 말을 한다.
    """
    if rate > secure_threshold:
        return "secure"
    if rate >= warning_threshold:
        return "warning"
    return "shortage"


def _capacity_color(rate: float, *, secure_threshold: float, warning_threshold: float) -> str:
    """확보율을 확보·경고·부족 상태색으로 바꾼다."""
    # 상태 → 색 짝은 **함수 안에서** 만든다. 모듈 상수로 올리면 처음 임포트한 순간의
    # 팔레트가 굳어 테마를 바꿔도 이 색만 따라오지 않는다.
    return {
        "secure": tokens.STATUS_SECURE,
        "warning": tokens.STATUS_WARNING,
        "shortage": tokens.STATUS_SHORTAGE,
    }[capacity_status(rate, secure_threshold=secure_threshold, warning_threshold=warning_threshold)]


def _text_width_units(text: str) -> float:
    """글자 크기 1px 기준의 렌더 폭. 전각 1.0, 반각 0.6 으로 센다.

    Ambiguous(`A`) 도 전각으로 센다. 말줄임 `…` 와 `±`·`×` 가 여기 속하는데, 한글 face 는
    이들을 전각으로 그리므로 반각으로 세면 잘라 낸 이름이 다시 칸을 넘는다.
    """
    return sum(
        1.0 if unicodedata.east_asian_width(character) in {"F", "W", "A"} else 0.6
        for character in text
    )


def _truncate_to_units(text: str, unit_budget: float) -> str:
    """폭 예산에 들어가는 데까지만 남기고 말줄임을 붙인다.

    예산에서 말줄임 자신의 폭을 빼는 것은 **호출자 몫**이다 — 예산의 근거(월 칸 폭이냐
    라벨 칸 폭이냐)가 자리마다 다르고, 뺄셈을 여기로 옮기면 그 근거가 한 겹 가려진다.
    """
    kept: list[str] = []
    used = 0.0
    for character in text:
        character_units = _text_width_units(character)
        if used + character_units > unit_budget:
            break
        kept.append(character)
        used += character_units
    return "".join(kept) + BOTTLENECK_NAME_ELLIPSIS
