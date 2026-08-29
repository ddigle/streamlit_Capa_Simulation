from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.components.space_layout import (
    BUILDINGS,
    FIXED_EQUIPMENT_HEIGHT,
    STAGE_COLORS,
    build_fab_figure,
    build_floor_layout_figure,
    equipment_counts,
    invalid_equipment_rows,
)


def _space_equipment() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "호기": "EQ-01",
                "공정": "A",
                "동": "C1",
                "층": "1F",
                "X": 10,
                "Y": 10,
                "너비": 15,
                "단계": "양산",
                "상태": "양산",
                "비가동유형": None,
            },
            {
                "호기": "EQ-02",
                "공정": "A",
                "동": "C1",
                "층": "1F",
                "X": 30,
                "Y": 10,
                "너비": 15,
                "단계": "Qual",
                "상태": "Qual",
                "비가동유형": None,
            },
            {
                "호기": "EQ-03",
                "공정": "B",
                "동": "C2",
                "층": "2F",
                "X": 10,
                "Y": 20,
                "너비": 12,
                "단계": "양산",
                "상태": "비가동",
                "비가동유형": "고장",
            },
        ]
    )


def test_fab_buildings_keep_c5_separate_and_c1_to_c4_connected() -> None:
    assert [building.name for building in BUILDINGS] == ["C5", "C1", "C2", "C3", "C4"]
    assert BUILDINGS[0].x + BUILDINGS[0].width < BUILDINGS[1].x

    connected_buildings = BUILDINGS[1:]
    for left, right in zip(connected_buildings, connected_buildings[1:], strict=False):
        assert left.x + left.width == pytest.approx(right.x)


def test_space_counts_use_production_progress_and_downtime() -> None:
    assert equipment_counts(_space_equipment()) == (1, 1, 1)


def test_fab_figure_has_one_building_shape_per_building() -> None:
    figure = build_fab_figure(_space_equipment())

    assert len(figure.layout.shapes) == len(BUILDINGS)


def test_floor_layout_uses_stage_colors_and_fixed_height() -> None:
    equipment = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]
    figure = build_floor_layout_figure(equipment, "C1", "1F")

    equipment_shapes = list(figure.layout.shapes)[1:]
    assert equipment_shapes[0].fillcolor == STAGE_COLORS["양산"]
    assert equipment_shapes[1].fillcolor == STAGE_COLORS["Qual"]
    assert float(equipment_shapes[0].y1) - float(equipment_shapes[0].y0) == pytest.approx(
        FIXED_EQUIPMENT_HEIGHT
    )


def test_invalid_equipment_rows_detects_out_of_canvas_equipment() -> None:
    equipment = pd.DataFrame(
        [
            {"X": 10, "Y": 10, "너비": 20},
            {"X": 95, "Y": 10, "너비": 10},
            {"X": 10, "Y": 55, "너비": 20},
        ]
    )

    assert invalid_equipment_rows(equipment) == [2, 3]
