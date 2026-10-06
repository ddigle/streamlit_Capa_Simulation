# Purpose: space layout 관련 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.components.space_layout import (
    floor_block_stats,
    floor_placements,
    invalid_equipment_rows,
    occupancy_ratio,
    stage_counts,
    stage_legend_markup,
)
from capa_simulation.design.tokens import EQUIPMENT_STAGE_COLORS
from capa_simulation.services.fab_layout import (
    BUILDINGS,
    FAB_BLOCK_KIND,
    FLOOR_KEYS,
    default_fab_layout,
    fab_layout_fingerprint,
    floor_from_label,
    floor_from_param,
    floor_param,
    floors_for,
)
from capa_simulation.services.floor_layout_profile import MAX_CANVAS_EXTENT, MIN_CANVAS_EXTENT


def _space_equipment() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "설비명": "EQ-01",
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
                "설비명": "EQ-02",
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
                "설비명": "EQ-03",
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


def test_the_default_fab_layout_has_one_linked_block_per_floor() -> None:
    """기본 FAB 도면: 30개 층마다 층 블록 하나(연결 필수), 동마다 6F 가 위·1F 가 아래, C5 는 떨어져
    있고 C1~C4 는 맞붙는다. 동 이름·「독립동」·「연결 구간」은 연결 없는 꾸밈(영역·글자)이다."""
    canvas, marks = default_fab_layout()
    blocks = [mark for mark in marks if mark.kind == FAB_BLOCK_KIND]

    assert sorted(block.link for block in blocks if block.link) == sorted(FLOOR_KEYS)
    assert len(blocks) == len(FLOOR_KEYS) == 30
    assert all(mark.link is None for mark in marks if mark.kind != FAB_BLOCK_KIND)
    assert {"독립동", "C1 · C2 · C3 · C4 연결 구간", "C1", "C5"} <= {
        mark.label for mark in marks if mark.kind != FAB_BLOCK_KIND
    }
    assert MIN_CANVAS_EXTENT <= min(canvas) and max(canvas) <= MAX_CANVAS_EXTENT
    for mark in marks:
        assert mark.x >= 0 and mark.y >= 0
        assert mark.x + mark.w <= canvas[0] + 1e-9 and mark.y + mark.h <= canvas[1] + 1e-9

    by_floor = {block.link: block for block in blocks}
    for building in BUILDINGS:
        bottoms = [by_floor[(building.name, spec.floor)].y for spec in floors_for(building.name)]
        assert bottoms == sorted(bottoms, reverse=True), building.name

    def edges(name: str) -> tuple[float, float]:
        column = [block for block in blocks if block.link and block.link[0] == name]
        return min(block.x for block in column), max(block.x + block.w for block in column)

    assert edges("C5")[1] < edges("C1")[0] - 5
    for left, right in (("C1", "C2"), ("C2", "C3"), ("C3", "C4")):
        assert edges(right)[0] - edges(left)[1] < 1

    payload = by_floor[("C1", "1F")].editor_payload()
    assert payload["kind"] == "block" and payload["link"] == "C1 1F" and payload["color"] == ""
    # 지문은 같은 도면이면 같다(뷰어 epoch).
    assert fab_layout_fingerprint(*default_fab_layout()) == fab_layout_fingerprint(canvas, marks)


def test_floor_blocks_count_placement_not_state() -> None:
    """층 블록 글자는 상태가 아니라 배치를 센다 — 상태는 층 상세의 색과 범례가 말한다
    (2026-10-01 결정). 동·층이 빈 미배치는 어느 층에도 들지 않는다."""
    equipment = _space_equipment()
    unplaced = pd.DataFrame({"동": ["C1", "C1", None], "층": ["2F", "2F", None]})

    placements = floor_placements(equipment, unplaced, equipment, lambda key: (100.0, 60.0))
    stats = floor_block_stats(placements)

    assert [placement.key for placement in placements] == list(FLOOR_KEYS)
    # 15×8 + 15×6 = 210 → 100×60 캔버스의 3.5%. 점유율은 블록이 아니라 풍선에 들어간다.
    assert stats["C1 1F"] == {"placed": "배치 2대", "unplaced": None, "occupancy": "점유율 3.5%"}
    assert stats["C1 2F"] == {"placed": "배치 0대", "unplaced": "미배치 2대", "occupancy": None}
    assert stats["C2 2F"]["placed"] == "배치 1대"
    assert sum(placement.unplaced for placement in placements) == 2
    assert not any(
        "가용" in str(value) or "비가동" in str(value)
        for floor in stats.values()
        for value in floor.values()
    )


def test_floor_names_round_trip_through_the_address_and_the_block_link() -> None:
    """주소 인자는 「C1-1F」, 블록 연결은 「C1 1F」. FAB 의 층이 아니면 None(조용히 FAB)."""
    assert floor_param(("C2", "3F")) == "C2-3F"
    assert floor_from_param("C2-3F") == ("C2", "3F")
    assert floor_from_label("C2 3F") == ("C2", "3F")
    for bad in ("C9-1F", "C1-7F", "C1 1F", "", "C1-", None, ["C1", "1F"]):
        assert floor_from_param(bad) is None, bad
    for bad in ("C2-3F", "C2  3F", "C6 1F", None):
        assert floor_from_label(bad) is None, bad


def test_occupancy_is_box_area_over_canvas_area() -> None:
    placed = _space_equipment().loc[lambda frame: frame["동"].eq("C1")]

    # 15×8 + 15×6 = 210 → 100×60 캔버스의 3.5%.
    assert occupancy_ratio(placed, 100.0, 60.0) == pytest.approx(0.035)
    assert occupancy_ratio(placed.iloc[0:0], 100.0, 60.0) == 0.0
    assert occupancy_ratio(placed, 0.0, 60.0) == 0.0


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


def test_the_floor_legend_names_only_the_states_on_the_floor_with_counts() -> None:
    """층 상세 범례는 머리 줄 오른쪽의 HTML 칩이다. 그 층에 있는 상태만 대수와 함께, 편집 중
    (`None`)에는 모든 상태의 색 뜻만 보인다."""
    counted = stage_legend_markup({"가용": 5.0, "운영 비가동": 0.75})
    plain = stage_legend_markup(None, exclude=("반출 완료", "이설 완료"))

    assert "가용 5대" in counted and "운영 비가동 0.75대" in counted
    assert "셋업 진행중" not in counted
    assert EQUIPMENT_STAGE_COLORS["가용"] in counted
    # 편집 중 범례는 편집기에 나오지 않는 퇴장 상태를 뺀다.
    assert all(
        (status in plain) != (status in ("반출 완료", "이설 완료"))
        for status in EQUIPMENT_STAGE_COLORS
    )
    assert "대<" not in plain
