# Purpose: space layout 관련 정상·예외·회귀 동작을 검증한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.components.space_layout import (
    BUILDINGS,
    STAGE_COLORS,
    build_fab_figure,
    build_floor_layout_figure,
    equipment_counts,
    floors_for,
    invalid_equipment_rows,
)


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


def test_space_counts_use_available_progress_and_inactive() -> None:
    assert equipment_counts(_space_equipment()) == (1, 1, 1)


def test_fab_figure_has_one_building_shape_per_building() -> None:
    figure = build_fab_figure(_space_equipment())

    assert len(figure.layout.shapes) == len(BUILDINGS)


def test_floor_layout_uses_status_colors_and_input_sizes() -> None:
    equipment = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]
    figure = build_floor_layout_figure(equipment, "C1", "1F")

    equipment_shapes = list(figure.layout.shapes)[1:]
    assert equipment_shapes[0].fillcolor == STAGE_COLORS["가용"]
    assert equipment_shapes[1].fillcolor == STAGE_COLORS["셋업 진행중"]
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
