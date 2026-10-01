# Purpose: space layout 관련 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.components.space_layout import (
    BUILDINGS,
    build_fab_figure,
    build_floor_figure,
    build_floor_layout_figure,
    floor_layout_figure_height,
    floors_for,
    invalid_equipment_rows,
    keep_out_color,
    occupancy_ratio,
    stage_counts,
)
from capa_simulation.design.tokens import EQUIPMENT_STAGE_COLORS
from capa_simulation.services.floor_layout_mark import prepare_floor_layout_marks


def _space_equipment() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "호기": "EQ-01",
                "공정소분류": "A",
                "동": "C1",
                "층": "1F",
                "X좌표": 10,
                "Y좌표": 10,
                "Xsize": 15,
                "Ysize": 8,
                "단계": "가용",
                "상태": "가용",
                "보유여부": True,
                "가용여부": True,
                "비가동유형": None,
            },
            {
                "호기": "EQ-02",
                "공정소분류": "A",
                "동": "C1",
                "층": "1F",
                "X좌표": 30,
                "Y좌표": 10,
                "Xsize": 15,
                "Ysize": 6,
                "단계": "셋업 진행중",
                "상태": "셋업 진행중",
                "보유여부": True,
                "가용여부": False,
                "비가동유형": None,
            },
            {
                "호기": "EQ-03",
                "공정소분류": "B",
                "동": "C2",
                "층": "2F",
                "X좌표": 10,
                "Y좌표": 20,
                "Xsize": 12,
                "Ysize": 7,
                "단계": "운영 비가동",
                "상태": "운영 비가동",
                "보유여부": True,
                "가용여부": False,
                "비가동유형": "고장",
            },
        ]
    )


def test_fab_buildings_keep_c5_separate_and_c1_to_c4_connected() -> None:
    assert [building.name for building in BUILDINGS] == ["C5", "C1", "C2", "C3", "C4"]
    assert BUILDINGS[0].x + BUILDINGS[0].width < BUILDINGS[1].x
    assert [floor.floor for floor in floors_for("C1")] == [
        "6F",
        "5F",
        "4F",
        "3F",
        "2F",
        "1F",
    ]

    connected_buildings = BUILDINGS[1:]
    for left, right in zip(connected_buildings, connected_buildings[1:], strict=False):
        assert left.x + left.width == pytest.approx(right.x)


def test_stage_counts_name_only_the_states_that_are_on_the_floor() -> None:
    assert stage_counts(_space_equipment()) == {"셋업 진행중": 1, "가용": 1, "운영 비가동": 1}
    assert stage_counts(_space_equipment().iloc[0:0]) == {}


def test_fab_figure_has_one_building_shape_per_building() -> None:
    figure = build_fab_figure(_space_equipment())

    assert len(figure.layout.shapes) == len(BUILDINGS)


def test_fab_and_floor_figures_count_placement_not_state() -> None:
    """동·층 칸은 상태가 아니라 배치를 센다 — 상태는 층 배치도의 색과 범례가 말한다."""
    fab = build_fab_figure(_space_equipment(), unplaced={"C1": 2.0})
    texts = {
        annotation.text.split("<br>")[0]: annotation.text for annotation in fab.layout.annotations
    }
    assert "배치 2대" in texts["<b>C1</b>"] and "미배치 2대" in texts["<b>C1</b>"]
    assert "배치 1대" in texts["<b>C2</b>"] and "미배치" not in texts["<b>C2</b>"]
    assert not any("가용" in annotation.text for annotation in fab.layout.annotations)

    floors = build_floor_figure(
        _space_equipment(), "C1", unplaced={"2F": 0.5}, occupancy={"1F": 0.0425, "2F": 0.0}
    )
    lines = [annotation.text for annotation in floors.layout.annotations]
    assert "<b>C1 1F</b>　배치 2대　점유율 4.2%" in lines
    # 배치가 없는 층은 점유율을 적지 않는다.
    assert "<b>C1 2F</b>　배치 0대 · 미배치 0.5대" in lines


def test_occupancy_is_box_area_over_canvas_area() -> None:
    placed = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]

    # 15×8 + 15×6 = 210 → 100×60 캔버스의 3.5%.
    assert occupancy_ratio(placed, 100.0, 60.0) == pytest.approx(0.035)
    assert occupancy_ratio(placed.iloc[0:0], 100.0, 60.0) == 0.0
    assert occupancy_ratio(placed, 0.0, 60.0) == 0.0


def test_floor_layout_legend_carries_the_floor_counts() -> None:
    equipment = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]

    counted = build_floor_layout_figure(equipment, "C1", "1F", stage_counts=stage_counts(equipment))
    plain = build_floor_layout_figure(equipment, "C1", "1F")

    assert [trace.name for trace in counted.data if trace.name] == ["셋업 진행중 1대", "가용 1대"]
    # 대수를 주지 않으면 모든 상태의 색 범례만 둔다.
    assert [trace.name for trace in plain.data if trace.name] == list(EQUIPMENT_STAGE_COLORS)


def test_floor_layout_uses_status_colors_and_input_sizes() -> None:
    equipment = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]
    figure = build_floor_layout_figure(equipment, "C1", "1F")

    equipment_shapes = list(figure.layout.shapes)[1:]
    assert equipment_shapes[0].fillcolor == EQUIPMENT_STAGE_COLORS["가용"]
    assert equipment_shapes[1].fillcolor == EQUIPMENT_STAGE_COLORS["셋업 진행중"]
    assert float(equipment_shapes[0].y1) - float(equipment_shapes[0].y0) == pytest.approx(8)
    assert float(equipment_shapes[1].y1) - float(equipment_shapes[1].y0) == pytest.approx(6)


def test_invalid_equipment_rows_detects_out_of_canvas_equipment() -> None:
    equipment = pd.DataFrame(
        [
            {"X좌표": 10, "Y좌표": 10, "Xsize": 20, "Ysize": 10},
            {"X좌표": 95, "Y좌표": 10, "Xsize": 10, "Ysize": 10},
            {"X좌표": 10, "Y좌표": 55, "Xsize": 20, "Ysize": 10},
        ]
    )

    assert invalid_equipment_rows(equipment) == [2, 3]


def test_invalid_equipment_rows_follow_the_floor_canvas() -> None:
    equipment = pd.DataFrame(
        [
            {"X좌표": 10, "Y좌표": 10, "Xsize": 20, "Ysize": 10},
            {"X좌표": 95, "Y좌표": 10, "Xsize": 10, "Ysize": 10},
            {"X좌표": 10, "Y좌표": 30, "Xsize": 20, "Ysize": 10},
        ]
    )

    # 도면을 올린 넓은 층은 2번 호기를 정상으로 보고, 낮아진 높이는 3번을 잡는다.
    assert invalid_equipment_rows(equipment, canvas_width=120.0, canvas_height=37.5) == [3]
    # 도면이 없는 층은 기본 캔버스 그대로다.
    assert invalid_equipment_rows(equipment) == [2]


def test_floor_layout_without_a_drawing_keeps_the_previous_canvas() -> None:
    equipment = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]

    figure = build_floor_layout_figure(equipment, "C1", "1F")

    canvas = figure.layout.shapes[0]
    assert (canvas.x0, canvas.x1, canvas.y0, canvas.y1) == (0, 100, 0, 60)
    assert figure.layout.xaxis.range == (0.0, 100.0)
    assert figure.layout.yaxis.range == (0.0, 60.0)
    assert figure.layout.height == 600
    assert figure.layout.xaxis.dtick == 10
    assert figure.layout.yaxis.dtick == 10
    assert figure.layout.images == ()


def test_floor_layout_draws_the_uploaded_drawing_on_the_floor_canvas() -> None:
    equipment = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]

    figure = build_floor_layout_figure(
        equipment,
        "C1",
        "1F",
        background_image="data:image/png;base64,AAAA",
        canvas_width=100.0,
        canvas_height=37.5,
    )

    image = figure.layout.images[0]
    assert image.source == "data:image/png;base64,AAAA"
    # xref·yref 가 없으면 plotly 가 paper 좌표로 읽어 도면이 화면 밖으로 나간다.
    assert (image.xref, image.yref) == ("x", "y")
    assert (image.x, image.y, image.sizex, image.sizey) == (0, 37.5, 100.0, 37.5)
    canvas = figure.layout.shapes[0]
    assert (canvas.x1, canvas.y1) == (100.0, 37.5)
    assert figure.layout.yaxis.range == (0.0, 37.5)
    assert figure.layout.height == floor_layout_figure_height(100.0, 37.5)
    assert figure.layout.height == 375


def test_the_floor_layout_draws_saved_marks_around_the_equipment() -> None:
    """영역은 호기 아래, 반입구·문·기둥은 호기 위에 그린다. 이름표는 이스케이프한다."""
    equipment = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]
    marks = prepare_floor_layout_marks(
        [
            {"id": "Z", "kind": "zone", "x": 0, "y": 0, "w": 20, "h": 10, "label": "<b>정비</b>"},
            {"id": "K", "kind": "zone", "x": 30, "y": 0, "w": 10, "h": 10, "keepOut": True},
            {"id": "S", "kind": "shutter", "x": 50, "y": 0, "w": 12, "h": 5, "label": "반입"},
            {"id": "D", "kind": "door", "x": 70, "y": 0, "w": 4, "h": 4, "rot": 90},
            {"id": "C", "kind": "column", "x": 80, "y": 20, "w": 1.5, "h": 1.5},
            {"id": "T", "kind": "text", "x": 5, "y": 40, "w": 14, "h": 3, "label": "메모"},
            {"id": "A", "kind": "arrow", "x": 30, "y": 40, "w": 16, "h": 3},
        ],
        (100.0, 60.0),
    )

    plain = build_floor_layout_figure(equipment, "C1", "1F")
    figure = build_floor_layout_figure(equipment, "C1", "1F", marks=marks)

    shapes = list(figure.layout.shapes)
    equipment_count = len(plain.layout.shapes) - 1
    # 캔버스 · 영역 둘(채움·테두리씩 4) · 호기 · 반입구 1 · 문 2 · 기둥 1
    assert len(shapes) == 1 + 4 + equipment_count + 4
    assert all(shape.layer == "below" for shape in shapes[1:5])
    assert shapes[3].fillcolor == keep_out_color()
    assert all(shape.layer == "above" for shape in shapes[5 + equipment_count :])
    texts = [annotation.text for annotation in figure.layout.annotations]
    assert "<b>&lt;b&gt;정비&lt;/b&gt;</b>" in texts
    assert "<b>영역 · 설비 금지</b>" in texts and "<b>메모</b>" in texts and "반입" in texts
    # 반입구·동선 화살표는 글자 없는 화살표 주석이다.
    assert sum(1 for annotation in figure.layout.annotations if annotation.showarrow) == 2


def test_a_rotated_door_keeps_its_hinge_on_the_wall() -> None:
    """편집기와 같은 회전: 0° 는 아래 변이 벽, 90° 는 왼쪽 변이 벽이다(시계 방향)."""
    (door,) = prepare_floor_layout_marks(
        [{"id": "D", "kind": "door", "x": 10, "y": 10, "w": 4, "h": 4, "rot": 90}], (100.0, 60.0)
    )
    figure = build_floor_layout_figure(_space_equipment().iloc[0:0], "C1", "1F", marks=[door])

    leaf = next(shape for shape in figure.layout.shapes if shape.type == "path")
    start, end = (tuple(float(v) for v in point.split()) for point in leaf.path[2:].split(" L "))
    # 경첩은 벽(왼쪽 변 x = 10)의 위 끝이고, 열린 문짝은 벽과 직각으로 윗변을 따라 놓인다.
    assert start == pytest.approx((10, 14)) and end == pytest.approx((14, 14))
