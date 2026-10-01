# Purpose: FAB 동·층 정의와 배치 집계, FAB·동 Plotly Figure, 층 상세 범례·도면 요소 색을 만든다.

from __future__ import annotations

import html
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.plotly_layout import flush_layout_items
from capa_simulation.design import theme, tokens
from capa_simulation.services.equipment_units import (
    UNIT_SHARE_COLUMN,
    format_unit_count,
    unit_total,
)
from capa_simulation.services.floor_layout_mark import MARK_COLOR_KEYS
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
)


@dataclass(frozen=True)
class BuildingSpec:
    name: str
    x: float
    width: float
    height: float


@dataclass(frozen=True)
class FloorSpec:
    building: str
    floor: str


BUILDINGS: Final[tuple[BuildingSpec, ...]] = (
    BuildingSpec("C5", x=0.5, width=1.45, height=3.3),
    BuildingSpec("C1", x=3.1, width=1.55, height=4.0),
    BuildingSpec("C2", x=4.65, width=1.75, height=4.7),
    BuildingSpec("C3", x=6.40, width=1.50, height=4.1),
    BuildingSpec("C4", x=7.90, width=1.70, height=3.5),
)
FLOORS: Final[tuple[FloorSpec, ...]] = tuple(
    FloorSpec(building, floor)
    for building in ("C5", "C1", "C2", "C3", "C4")
    for floor in ("6F", "5F", "4F", "3F", "2F", "1F")
)


def floors_for(building: str) -> list[FloorSpec]:
    return [floor for floor in FLOORS if floor.building == building]


def _unit_shares(equipment: pd.DataFrame) -> pd.Series:
    """행마다 설비지분. 상태 판정을 거치지 않은 표(지분 컬럼이 없는 표)는 행 하나가 한 대다."""
    if UNIT_SHARE_COLUMN in equipment.columns:
        return equipment[UNIT_SHARE_COLUMN].astype("float64").fillna(1.0)
    return pd.Series(1.0, index=equipment.index, dtype="float64")


def equipment_unit_total(equipment: pd.DataFrame) -> float:
    """행이 아니라 설비 대수. 모체호기로 묶은 모듈 행 넷이 한 대다."""
    return unit_total(_unit_shares(equipment))


def stage_counts(equipment: pd.DataFrame) -> dict[str, float]:
    """상태별 설비 대수(층 배치도 범례). 행을 세지 않고 설비지분을 더하고, 0 대인 상태는 뺀다.

    모듈 하나가 비가동이면 그 설비는 가용 0.75 · 운영 비가동 0.25 로 갈린다. 상태마다
    **직접 더한다** — 합계에서 빼면 반올림 끝자리가 -0.0 으로 남아 「-0대」가 찍힌다.
    """
    if equipment.empty or "상태" not in equipment.columns:
        return {}
    shares = _unit_shares(equipment)
    counts = {
        status: unit_total(shares.where(equipment["상태"].eq(status), 0.0))
        for status in tokens.EQUIPMENT_STAGE_COLORS
    }
    return {status: count for status, count in counts.items() if count > 0}


def occupancy_ratio(placed: pd.DataFrame, canvas_width: float, canvas_height: float) -> float:
    """도면에 그린 호기 사각형 면적 합 ÷ 캔버스 면적. 캔버스 단위의 상대값이고(실제 m² 아님)
    겹친 자리는 두 번 센다. 캔버스가 없으면 0."""
    area = canvas_width * canvas_height
    if placed.empty or area <= 0:
        return 0.0
    sizes = placed.loc[:, ["Xsize", "Ysize"]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return float((sizes["Xsize"] * sizes["Ysize"]).sum()) / area


def _placement_text(placed: float, unplaced: float) -> str:
    """동·층 칸의 글자: 「배치 12대」, 좌표가 아직 없는 호기가 있으면 「· 미배치 3대」를 붙인다."""
    text = f"배치 {format_unit_count(placed)}대"
    if unplaced > 0:
        text += f" · 미배치 {format_unit_count(unplaced)}대"
    return text


def build_fab_figure(
    equipment: pd.DataFrame, *, unplaced: Mapping[str, float] | None = None
) -> go.Figure:
    """FAB 전체. 동마다 도면에 배치된 설비 대수와(있으면) 동은 정했지만 좌표가 없는 미배치 대수."""
    figure = go.Figure()
    clickable_x: list[float] = []
    clickable_y: list[float] = []
    clickable_buildings: list[str] = []

    for index, building in enumerate(BUILDINGS):
        placed = equipment_unit_total(equipment.loc[equipment["동"].eq(building.name)])
        waiting = (unplaced or {}).get(building.name, 0.0)
        figure.add_shape(
            type="rect",
            x0=building.x,
            x1=building.x + building.width,
            y0=0.5,
            y1=0.5 + building.height,
            fillcolor=tokens.SPACE_BUILDING_FILLS[index],
            line={"color": tokens.SPACE_BORDER, "width": 2.5},
            layer="below",
        )
        figure.add_annotation(
            x=building.x + building.width / 2,
            y=0.5 + building.height / 2,
            text=(
                f"<b>{building.name}</b><br>배치 {format_unit_count(placed)}대<br>"
                + (f"미배치 {format_unit_count(waiting)}대<br>" if waiting > 0 else "")
                + "<span style='font-size:10px'>클릭하여 상세 보기</span>"
            ),
            showarrow=False,
            font={"size": 14, "color": tokens.SPACE_TEXT},
            align="center",
        )
        for y_ratio in (0.25, 0.50, 0.75):
            clickable_x.append(building.x + building.width / 2)
            clickable_y.append(0.5 + building.height * y_ratio)
            clickable_buildings.append(building.name)

    figure.add_trace(
        go.Scatter(
            x=clickable_x,
            y=clickable_y,
            mode="markers",
            customdata=clickable_buildings,
            marker={"size": 64, "color": tokens.HIT_TARGET},
            hovertemplate="%{customdata}동 상세 보기<extra></extra>",
            showlegend=False,
        )
    )
    figure.add_annotation(
        x=1.225,
        y=4.25,
        text="독립동",
        showarrow=False,
        font={"size": 12, "color": tokens.SPACE_LABEL_TEXT},
    )
    figure.add_annotation(
        x=6.35,
        y=5.25,
        text="C1 · C2 · C3 · C4 연결 구간",
        showarrow=False,
        font={"size": 12, "color": tokens.SPACE_LABEL_TEXT},
    )
    _apply_layout(figure, x_range=(0.0, 10.2), y_range=(0.0, 5.6), height=470)
    flush_layout_items(figure)
    return figure


def build_floor_figure(
    equipment: pd.DataFrame,
    building: str,
    *,
    unplaced: Mapping[str, float] | None = None,
    occupancy: Mapping[str, float] | None = None,
) -> go.Figure:
    """한 동의 층들. 층마다 배치 대수·점유율(캔버스 대비 호기 면적)과 미배치 대수."""
    floors = floors_for(building)
    figure = go.Figure()
    clickable_x: list[float] = []
    clickable_y: list[float] = []
    clickable_floors: list[str] = []
    band_height = 1.05
    gap = 0.15

    for index, floor in enumerate(floors):
        floor_equipment = equipment.loc[
            equipment["동"].eq(building) & equipment["층"].eq(floor.floor)
        ]
        placed = equipment_unit_total(floor_equipment)
        waiting = (unplaced or {}).get(floor.floor, 0.0)
        ratio = (occupancy or {}).get(floor.floor)
        y0 = (len(floors) - index - 1) * (band_height + gap) + 0.5
        y1 = y0 + band_height
        figure.add_shape(
            type="rect",
            x0=0.8,
            x1=9.2,
            y0=y0,
            y1=y1,
            fillcolor=tokens.SPACE_BUILDING_FILLS[index % len(tokens.SPACE_BUILDING_FILLS)],
            line={"color": tokens.SPACE_BORDER, "width": 2},
            layer="below",
        )
        figure.add_annotation(
            x=5.0,
            y=(y0 + y1) / 2,
            text=(
                f"<b>{building} {floor.floor}</b>　{_placement_text(placed, waiting)}"
                + (f"　점유율 {ratio:.1%}" if ratio is not None and placed > 0 else "")
            ),
            showarrow=False,
            font={"size": 15, "color": tokens.SPACE_TEXT},
        )
        for x in (2.0, 4.0, 6.0, 8.0):
            clickable_x.append(x)
            clickable_y.append((y0 + y1) / 2)
            clickable_floors.append(floor.floor)

    figure.add_trace(
        go.Scatter(
            x=clickable_x,
            y=clickable_y,
            mode="markers",
            customdata=clickable_floors,
            marker={"size": 62, "color": tokens.HIT_TARGET},
            hovertemplate=f"{building} %{{customdata}} 상세 보기<extra></extra>",
            showlegend=False,
        )
    )
    figure_height = max(340, 105 * len(floors) + 80)
    y_max = len(floors) * (band_height + gap) + 0.65
    _apply_layout(figure, x_range=(0.0, 10.0), y_range=(0.0, y_max), height=figure_height)
    flush_layout_items(figure)
    return figure


def mark_colors() -> dict[str, str]:
    """영역 색 키 → 지금 테마의 색. 검증된 범주 팔레트(제품별 비중과 같은 색)를 그대로 쓴다.
    편집기와 Plotly 배치도가 같은 색을 쓴다."""
    named = dict(zip(MARK_COLOR_KEYS[:-1], tokens.PRODUCT_SHARE_COLORS, strict=False))
    return {**named, MARK_COLOR_KEYS[-1]: tokens.PRODUCT_SHARE_OTHER}


def keep_out_color() -> str:
    """겹침·설비 금지 표시색. 다크의 부족색은 어두운 캔버스에서 1.9:1 로 묻혀 밝은 감소색을 쓴다."""
    return tokens.DELTA_AREA_DECREASE if theme.current_mode() == "dark" else tokens.STATUS_SHORTAGE


def stage_legend_markup(
    counts: Mapping[str, float] | None, *, exclude: Collection[str] = ()
) -> str:
    """층 상세 머리 줄 오른쪽의 상태 범례. `counts` 가 있으면 그 층에 있는 상태만 대수와 함께
    (「가용 5대」), 없으면 모든 상태의 색 뜻만 보인다(배치 편집 중 — 편집본은 저장본과 대수가
    다르다). 도면 안이 아니라 머리 줄에 두어 도면이 테두리 안을 다 쓴다."""
    chips = []
    for status, color in tokens.EQUIPMENT_STAGE_COLORS.items():
        if status in exclude or (counts is not None and status not in counts):
            continue
        text = status if counts is None else f"{status} {format_unit_count(counts[status])}대"
        chips.append(
            '<span style="display:inline-flex;align-items:center;gap:5px;white-space:nowrap">'
            f'<span aria-hidden="true" style="width:11px;height:11px;border-radius:2px;'
            f'background:{color};flex:none"></span>{html.escape(text)}</span>'
        )
    return (
        '<div style="display:flex;flex-wrap:wrap;justify-content:flex-end;gap:4px 14px;'
        f'font-size:0.82rem;color:{tokens.TEXT_MUTED}">{"".join(chips)}</div>'
    )


def first_selected_customdata(event: object) -> str | None:
    if not isinstance(event, Mapping):
        return None
    selection = event.get("selection")
    if not isinstance(selection, Mapping):
        return None
    points = selection.get("points")
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)) or not points:
        return None
    point = points[0]
    if not isinstance(point, Mapping):
        return None
    customdata = point.get("customdata")
    if isinstance(customdata, str):
        return customdata
    if isinstance(customdata, Sequence) and customdata and isinstance(customdata[0], str):
        return customdata[0]
    return None


def invalid_equipment_rows(
    equipment: pd.DataFrame,
    *,
    canvas_width: float = DEFAULT_CANVAS_WIDTH,
    canvas_height: float = DEFAULT_CANVAS_HEIGHT,
) -> list[int]:
    required = {"X좌표", "Y좌표", "Xsize", "Ysize"}
    if not required.issubset(equipment.columns):
        return list(range(1, len(equipment) + 1))
    numeric = equipment.loc[:, ["X좌표", "Y좌표", "Xsize", "Ysize"]].apply(
        pd.to_numeric, errors="coerce"
    )
    invalid = (
        numeric.isna().any(axis=1)
        | numeric["X좌표"].lt(0)
        | numeric["Y좌표"].lt(0)
        | numeric["Xsize"].le(0)
        | numeric["Ysize"].le(0)
        | numeric["X좌표"].add(numeric["Xsize"]).gt(canvas_width)
        | numeric["Y좌표"].add(numeric["Ysize"]).gt(canvas_height)
    )
    return [int(index) + 1 for index in numeric.index[invalid].tolist()]


def _apply_layout(
    figure: go.Figure,
    *,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    height: int,
) -> None:
    figure.update_layout(
        height=height,
        margin={"l": 16, "r": 16, "t": 42, "b": 16},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.CHART_CANVAS,
        hoverlabel={"bgcolor": tokens.SURFACE, "font": {"color": tokens.SPACE_TEXT}},
        clickmode="event+select",
        dragmode=False,
    )
    figure.update_xaxes(
        range=list(x_range),
        visible=False,
        fixedrange=True,
        zeroline=False,
    )
    figure.update_yaxes(
        range=list(y_range),
        visible=False,
        fixedrange=True,
        zeroline=False,
        scaleanchor="x",
        scaleratio=1,
    )
