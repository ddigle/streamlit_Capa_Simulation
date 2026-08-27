from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import pandas as pd
import plotly.graph_objects as go


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
    active_count: int
    setup_count: int


BUILDINGS: Final[tuple[BuildingSpec, ...]] = (
    BuildingSpec("C5", x=0.5, width=1.45, height=3.3),
    BuildingSpec("C1", x=3.1, width=1.55, height=4.0),
    BuildingSpec("C2", x=4.65, width=1.75, height=4.7),
    BuildingSpec("C3", x=6.40, width=1.50, height=4.1),
    BuildingSpec("C4", x=7.90, width=1.70, height=3.5),
)

FLOORS: Final[tuple[FloorSpec, ...]] = (
    FloorSpec("C5", "3F", 4, 0),
    FloorSpec("C5", "2F", 5, 1),
    FloorSpec("C5", "1F", 6, 1),
    FloorSpec("C1", "4F", 5, 0),
    FloorSpec("C1", "3F", 6, 1),
    FloorSpec("C1", "2F", 7, 2),
    FloorSpec("C1", "1F", 8, 1),
    FloorSpec("C2", "5F", 5, 0),
    FloorSpec("C2", "4F", 6, 1),
    FloorSpec("C2", "3F", 7, 2),
    FloorSpec("C2", "2F", 8, 1),
    FloorSpec("C2", "1F", 9, 1),
    FloorSpec("C3", "4F", 5, 1),
    FloorSpec("C3", "3F", 6, 1),
    FloorSpec("C3", "2F", 8, 1),
    FloorSpec("C3", "1F", 7, 2),
    FloorSpec("C4", "3F", 5, 1),
    FloorSpec("C4", "2F", 7, 1),
    FloorSpec("C4", "1F", 6, 1),
)

ACTIVE_COLOR: Final = "#A8D5BA"
SETUP_COLOR: Final = "#F6D99B"
INACTIVE_COLOR: Final = "#D8DDE3"
BUILDING_COLORS: Final[tuple[str, ...]] = (
    "#E7EDF2",
    "#F3F5F7",
    "#E9EDF1",
    "#F3F5F7",
    "#E9EDF1",
)
BORDER_COLOR: Final = "#59636E"
TEXT_COLOR: Final = "#20262E"
CANVAS_COLOR: Final = "#F7F8FA"


def floors_for(building: str) -> list[FloorSpec]:
    return [floor for floor in FLOORS if floor.building == building]


def building_counts(building: str) -> tuple[int, int]:
    floors = floors_for(building)
    return (
        sum(floor.active_count for floor in floors),
        sum(floor.setup_count for floor in floors),
    )


def fab_counts() -> tuple[int, int]:
    return (
        sum(floor.active_count for floor in FLOORS),
        sum(floor.setup_count for floor in FLOORS),
    )


def build_fab_figure() -> go.Figure:
    figure = go.Figure()
    clickable_x: list[float] = []
    clickable_y: list[float] = []
    clickable_buildings: list[str] = []

    for index, building in enumerate(BUILDINGS):
        active_count, setup_count = building_counts(building.name)
        figure.add_shape(
            type="rect",
            x0=building.x,
            x1=building.x + building.width,
            y0=0.5,
            y1=0.5 + building.height,
            fillcolor=BUILDING_COLORS[index],
            line={"color": BORDER_COLOR, "width": 2.5},
            layer="below",
        )
        figure.add_annotation(
            x=building.x + building.width / 2,
            y=0.5 + building.height / 2,
            text=(
                f"<b>{building.name}</b><br>"
                f"가동 {active_count}대<br>셋업 {setup_count}대<br>"
                f"<span style='font-size:10px'>클릭하여 상세 보기</span>"
            ),
            showarrow=False,
            font={"size": 15, "color": TEXT_COLOR},
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
            marker={"size": 64, "color": "rgba(255,255,255,0.01)"},
            hovertemplate="%{customdata}동 상세 보기<extra></extra>",
            showlegend=False,
        )
    )
    figure.add_annotation(
        x=1.225,
        y=4.25,
        text="독립동",
        showarrow=False,
        font={"size": 12, "color": "#69727C"},
    )
    figure.add_annotation(
        x=6.35,
        y=5.25,
        text="C1 · C2 · C3 · C4 연결 구간",
        showarrow=False,
        font={"size": 12, "color": "#69727C"},
    )
    _apply_layout(figure, x_range=(0.0, 10.2), y_range=(0.0, 5.6), height=470)
    return figure


def build_floor_figure(building: str) -> go.Figure:
    floors = floors_for(building)
    figure = go.Figure()
    clickable_x: list[float] = []
    clickable_y: list[float] = []
    clickable_floors: list[str] = []
    band_height = 1.05
    gap = 0.15

    for index, floor in enumerate(floors):
        y0 = (len(floors) - index - 1) * (band_height + gap) + 0.5
        y1 = y0 + band_height
        figure.add_shape(
            type="rect",
            x0=0.8,
            x1=9.2,
            y0=y0,
            y1=y1,
            fillcolor=BUILDING_COLORS[index % len(BUILDING_COLORS)],
            line={"color": BORDER_COLOR, "width": 2},
            layer="below",
        )
        figure.add_annotation(
            x=5.0,
            y=(y0 + y1) / 2,
            text=(
                f"<b>{building} {floor.floor}</b>　"
                f"가동 {floor.active_count}대　셋업 {floor.setup_count}대　"
                "Capa —"
            ),
            showarrow=False,
            font={"size": 15, "color": TEXT_COLOR},
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
            marker={"size": 62, "color": "rgba(255,255,255,0.01)"},
            hovertemplate=f"{building} %{{customdata}} 상세 보기<extra></extra>",
            showlegend=False,
        )
    )
    figure_height = max(340, 105 * len(floors) + 80)
    y_max = len(floors) * (band_height + gap) + 0.65
    _apply_layout(figure, x_range=(0.0, 10.0), y_range=(0.0, y_max), height=figure_height)
    return figure


def default_equipment(building: str, floor: str) -> pd.DataFrame:
    floor_spec = next(item for item in FLOORS if item.building == building and item.floor == floor)
    processes = (
        "Die Attach",
        "TC Bonding",
        "Mold",
        "Wafer Sorter",
        "AVI",
    )
    statuses = ["가동"] * floor_spec.active_count + ["셋업중"] * floor_spec.setup_count
    rows: list[dict[str, object]] = []
    for index, status in enumerate(statuses):
        column = index % 4
        row = index // 4
        rows.append(
            {
                "설비 ID": f"{building}-{floor}-EQ{index + 1:02d}",
                "공정": processes[index % len(processes)],
                "X": float(7 + column * 23),
                "Y": float(43 - row * 17),
                "너비": float(14 + (index % 3) * 2),
                "높이": float(9 + (index % 2) * 2),
                "상태": status,
            }
        )
    return pd.DataFrame(rows)


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
        fillcolor="rgba(247,248,250,0.18)" if background_image else CANVAS_COLOR,
        line={"color": BORDER_COLOR, "width": 2.5},
        layer="below",
    )

    hover_x: list[float] = []
    hover_y: list[float] = []
    hover_text: list[str] = []
    records = cast(list[dict[str, object]], equipment.to_dict(orient="records"))
    for record in records:
        equipment_id = str(record.get("설비 ID", ""))
        process = str(record.get("공정", ""))
        status = str(record.get("상태", "비가동"))
        x = _to_float(record.get("X"))
        y = _to_float(record.get("Y"))
        width = max(_to_float(record.get("너비")), 0.1)
        height = max(_to_float(record.get("높이")), 0.1)
        fill_color = {
            "가동": ACTIVE_COLOR,
            "셋업중": SETUP_COLOR,
            "비가동": INACTIVE_COLOR,
        }.get(status, INACTIVE_COLOR)
        figure.add_shape(
            type="rect",
            x0=x,
            x1=x + width,
            y0=y,
            y1=y + height,
            fillcolor=fill_color,
            line={"color": BORDER_COLOR, "width": 1.2},
            layer="above",
        )
        figure.add_annotation(
            x=x + width / 2,
            y=y + height / 2,
            text=f"<b>{equipment_id}</b><br>{process}",
            showarrow=False,
            font={"size": 9, "color": TEXT_COLOR},
            align="center",
        )
        hover_x.append(x + width / 2)
        hover_y.append(y + height / 2)
        hover_text.append(
            f"{equipment_id}<br>{process}<br>{status}<br>X {x:g} · Y {y:g} · {width:g}×{height:g}"
        )

    figure.add_trace(
        go.Scatter(
            x=hover_x,
            y=hover_y,
            mode="markers",
            marker={"size": 28, "color": "rgba(255,255,255,0.01)"},
            text=hover_text,
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
        )
    )
    for status, color in (
        ("가동", ACTIVE_COLOR),
        ("셋업중", SETUP_COLOR),
        ("비가동", INACTIVE_COLOR),
    ):
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
        legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.08},
    )
    _apply_layout(figure, x_range=(0.0, 100.0), y_range=(0.0, 60.0), height=600)
    figure.update_xaxes(showgrid=True, gridcolor="#E5E8EB", dtick=10)
    figure.update_yaxes(showgrid=True, gridcolor="#E5E8EB", dtick=10)
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
    required = {"X", "Y", "너비", "높이"}
    if not required.issubset(equipment.columns):
        return list(range(len(equipment)))
    numeric = equipment.loc[:, ["X", "Y", "너비", "높이"]].apply(
        pd.to_numeric,
        errors="coerce",
    )
    invalid = (
        numeric.isna().any(axis=1)
        | numeric["X"].lt(0)
        | numeric["Y"].lt(0)
        | numeric["너비"].le(0)
        | numeric["높이"].le(0)
        | numeric["X"].add(numeric["너비"]).gt(100)
        | numeric["Y"].add(numeric["높이"]).gt(60)
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
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        hoverlabel={"bgcolor": "#FFFFFF", "font": {"color": TEXT_COLOR}},
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
