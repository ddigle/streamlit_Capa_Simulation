from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.components.space_layout import (
    BUILDINGS,
    FLOORS,
    build_fab_figure,
    default_equipment,
    invalid_equipment_rows,
)


def test_fab_buildings_keep_c5_separate_and_c1_to_c4_connected() -> None:
    assert [building.name for building in BUILDINGS] == ["C5", "C1", "C2", "C3", "C4"]
    assert BUILDINGS[0].x + BUILDINGS[0].width < BUILDINGS[1].x

    connected_buildings = BUILDINGS[1:]
    for left, right in zip(connected_buildings, connected_buildings[1:], strict=False):
        assert left.x + left.width == pytest.approx(right.x)


def test_fab_figure_has_one_building_shape_per_building() -> None:
    figure = build_fab_figure()

    assert len(figure.layout.shapes) == len(BUILDINGS)


def test_default_equipment_matches_floor_counts() -> None:
    floor = FLOORS[0]

    equipment = default_equipment(floor.building, floor.floor)

    assert len(equipment) == floor.active_count + floor.setup_count
    assert int(equipment["상태"].eq("가동").sum()) == floor.active_count
    assert int(equipment["상태"].eq("셋업중").sum()) == floor.setup_count


def test_invalid_equipment_rows_detects_out_of_canvas_equipment() -> None:
    equipment = pd.DataFrame(
        [
            {"X": 10, "Y": 10, "너비": 20, "높이": 10},
            {"X": 95, "Y": 10, "너비": 10, "높이": 10},
            {"X": 10, "Y": 55, "너비": 20, "높이": 10},
        ]
    )

    assert invalid_equipment_rows(equipment) == [2, 3]
