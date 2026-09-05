# Purpose: FAB 동·층·설비 좌표를 집계하고 3단계 Space Plotly Figure를 생성한다.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.plotly_layout import append_layout_items
from capa_simulation.design import tokens


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


def equipment_counts(equipment: pd.DataFrame) -> tuple[int, int, int]:
    if equipment.empty or "상태" not in equipment.columns:
        return 0, 0, 0
    production = int(equipment["가용여부"].fillna(False).sum())
    inactive = int(equipment["상태"].isin(["보관 설비", "운영 비가동"]).sum())
    progress = len(equipment) - production - inactive
    return production, progress, inactive


def building_counts(equipment: pd.DataFrame, building: str) -> tuple[int, int, int]:
    return equipment_counts(equipment.loc[equipment["동"].eq(building)])


def fab_counts(equipment: pd.DataFrame) -> tuple[int, int, int]:
    return equipment_counts(equipment)


def build_fab_figure(equipment: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    clickable_x: list[float] = []
    clickable_y: list[float] = []
    clickable_buildings: list[str] = []

    for index, building in enumerate(BUILDINGS):
        production, progress, inactive = building_counts(equipment, building.name)
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
                f"<b>{building.name}</b><br>가용 {production}대<br>진행 {progress}대<br>"
                f"비가동 {inactive}대<br><span style='font-size:10px'>클릭하여 상세 보기</span>"
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
    return figure


def build_floor_figure(equipment: pd.DataFrame, building: str) -> go.Figure:
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
        production, progress, inactive = equipment_counts(floor_equipment)
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
                f"<b>{building} {floor.floor}</b>　가용 {production}대　"
                f"진행 {progress}대　비가동 {inactive}대"
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
    return figure


def build_floor_layout_figure(
    equipment: pd.DataFrame,
    building: str,
    floor: str,
    *,
    background_image: str | None = None,
) -> go.Figure:
    figure = go.Figure()
    if background_image:
        figure.add_layout_image(
            source=background_image,
            x=0,
            y=60,
            sizex=100,
            sizey=60,
            sizing="stretch",
            opacity=0.65,
            layer="below",
        )
    figure.add_shape(
        type="rect",
        x0=0,
        x1=100,
        y0=0,
        y1=60,
        fillcolor=tokens.SPACE_CANVAS_OVERLAY if background_image else tokens.SPACE_CANVAS,
        line={"color": tokens.SPACE_BORDER, "width": 2.5},
        layer="below",
    )

    hover_x: list[float] = []
    hover_y: list[float] = []
    hover_text: list[str] = []
    # 호기마다 add_shape·add_annotation 을 부르면 호기 수 제곱으로 는다(200대 13~18초). 지금은
    # 호기 마스터가 비어 잠복해 있지만 들어오는 순간 클릭마다 멈춘다. 모아서 한 번에 넣는다.
    # 바깥 캔버스 rect 는 위에서 먼저 넣었으므로 layout.shapes[0] 자리가 유지된다.
    equipment_shapes: list[dict[str, Any]] = []
    equipment_labels: list[dict[str, Any]] = []
    records = cast(list[dict[str, object]], equipment.to_dict(orient="records"))
    for record in records:
        equipment_id = str(record.get("호기", ""))
        process = str(record.get("공정소분류", ""))
        stage = str(record.get("단계", "입고 예정"))
        status = str(record.get("상태", stage))
        downtime_type = record.get("비가동유형")
        x = _to_float(record.get("X좌표"))
        y = _to_float(record.get("Y좌표"))
        width = max(_to_float(record.get("Xsize")), 0.1)
        height = max(_to_float(record.get("Ysize")), 0.1)
        fill_color = tokens.EQUIPMENT_STAGE_COLORS.get(status, tokens.EQUIPMENT_STAGE_FALLBACK)
        equipment_shapes.append(
            {
                "type": "rect",
                "x0": x,
                "x1": x + width,
                "y0": y,
                "y1": y + height,
                "fillcolor": fill_color,
                "line": {"color": tokens.SPACE_BORDER, "width": 1.2},
                "layer": "above",
            }
        )
        equipment_labels.append(
            {
                "x": x + width / 2,
                "y": y + height / 2,
                "text": f"<b>{equipment_id}</b><br>{stage}",
                "showarrow": False,
                "font": {"size": 9, "color": tokens.SPACE_TEXT},
                "align": "center",
            }
        )
        hover_x.append(x + width / 2)
        hover_y.append(y + height / 2)
        downtime_text = (
            f"<br>비가동: {downtime_type}"
            if isinstance(downtime_type, str) and downtime_type
            else ""
        )
        hover_text.append(
            f"{equipment_id}<br>{process}<br>단계: {stage}{downtime_text}<br>"
            f"X {x:g} · Y {y:g} · 크기 {width:g}×{height:g}"
        )

    append_layout_items(figure, shapes=equipment_shapes, annotations=equipment_labels)
    figure.add_trace(
        go.Scatter(
            x=hover_x,
            y=hover_y,
            mode="markers",
            marker={"size": 28, "color": tokens.HIT_TARGET},
            text=hover_text,
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
        )
    )
    for status, color in tokens.EQUIPMENT_STAGE_COLORS.items():
        figure.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"size": 12, "symbol": "square", "color": color},
                name=status,
                hoverinfo="skip",
            )
        )

    figure.update_layout(
        title={"text": f"{building} {floor} Space 배치도", "x": 0.01, "xanchor": "left"},
        legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.14},
    )
    _apply_layout(figure, x_range=(0.0, 100.0), y_range=(0.0, 60.0), height=600)
    figure.update_xaxes(showgrid=True, gridcolor=tokens.SPACE_GRID, dtick=10)
    figure.update_yaxes(showgrid=True, gridcolor=tokens.SPACE_GRID, dtick=10)
    return figure


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


def invalid_equipment_rows(equipment: pd.DataFrame) -> list[int]:
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
        | numeric["X좌표"].add(numeric["Xsize"]).gt(100)
        | numeric["Y좌표"].add(numeric["Ysize"]).gt(60)
    )
    return [int(index) + 1 for index in numeric.index[invalid].tolist()]


def _to_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


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
        paper_bgcolor=tokens.SURFACE,
        plot_bgcolor=tokens.SURFACE,
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
