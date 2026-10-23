# Purpose: space layout 관련 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from capa_simulation.components.space_layout import (
    LEGEND_DEFAULT,
    LEGEND_DELAY,
    LEGEND_EXIT_PLANNED,
    LEGEND_OFFLINE,
    LEGEND_PRE_ARRIVAL,
    LEGEND_STOPPED,
    LEGEND_STORAGE,
    LEGEND_UNCONFIRMED,
    ColorChoice,
    FloorPlacement,
    default_color_choice,
    equipment_unit_total,
    floor_block_stats,
    floor_placements,
    invalid_equipment_rows,
    occupancy_ratio,
    space_legend_counts,
    space_legend_markup,
    unit_appearance,
)
from capa_simulation.design import tokens
from capa_simulation.services.equipment_contract import LINE_TYPE_GROUPS
from capa_simulation.services.equipment_units import UNIT_SHARE_COLUMN
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
from capa_simulation.services.floor_layout_profile import (
    MAX_CANVAS_EXTENT,
    MIN_CANVAS_EXTENT,
    CanvasSize,
    FloorKey,
)
from capa_simulation.services.space_color_basis import (
    CAPA_LEVELS,
    COLOR_BASIS_CAPA,
    capa_group_of,
    capa_groups,
    capa_number,
)
from capa_simulation.services.space_unit_state import unit_boundaries


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


def _floor_placements_one_floor_at_a_time(
    counted: pd.DataFrame,
    unplaced: pd.DataFrame,
    located: pd.DataFrame,
    canvas_of: Callable[[FloorKey], CanvasSize],
) -> tuple[FloorPlacement, ...]:
    """맞대기 기준 — 층마다 그 층 행을 잘라 `equipment_unit_total`·`occupancy_ratio` 로 센다."""

    def by_floor(frame: pd.DataFrame) -> dict[FloorKey, pd.DataFrame]:
        rows = frame.dropna(subset=["동", "층"])
        return {
            (str(building), str(floor)): group
            for (building, floor), group in rows.groupby(["동", "층"], sort=False)
        }

    counted_by, unplaced_by, located_by = by_floor(counted), by_floor(unplaced), by_floor(located)
    return tuple(
        FloorPlacement(
            key=key,
            placed=equipment_unit_total(counted_by.get(key, counted.iloc[0:0])),
            unplaced=equipment_unit_total(unplaced_by.get(key, unplaced.iloc[0:0])),
            occupancy=occupancy_ratio(located_by.get(key, located.iloc[0:0]), *canvas_of(key)),
        )
        for key in FLOOR_KEYS
    )


# FAB 의 층, FAB 밖의 층, 동·층이 빈 자리. 앞쪽 몇 층에 몰아 넣는 판도 둔다(한 층 수백 행).
_RANDOM_PLACES: list[tuple[str | None, str | None]] = [
    *FLOOR_KEYS,
    ("C9", "1F"),
    ("C1", "9F"),
    (None, "1F"),
    ("C1", None),
    (None, None),
]
_RANDOM_SHARES: list[float | None] = [None, 1 / 3, 0.25, 1.0, 0.0, 0.1]
_RANDOM_SIZES: list[object] = [None, "12", "x", 7, 0.1, 15.5, 1 / 3, "2.5"]


def _random_floor_rows(
    rng: np.random.Generator, count: int, *, crowded: bool, shares: bool, sizes: bool
) -> pd.DataFrame:
    places = _RANDOM_PLACES[:3] if crowded else _RANDOM_PLACES
    picks = rng.integers(0, len(places), size=count)
    buildings = [places[pick][0] for pick in picks]
    floors = [places[pick][1] for pick in picks]
    columns: dict[str, object] = (
        {"동": pd.array(buildings, dtype="string"), "층": pd.array(floors, dtype="string")}
        if rng.random() < 0.5
        else {"동": buildings, "층": floors}
    )
    if shares:
        columns[UNIT_SHARE_COLUMN] = [
            _RANDOM_SHARES[pick] for pick in rng.integers(0, len(_RANDOM_SHARES), size=count)
        ]
    if sizes:
        for column in ("Xsize", "Ysize"):
            columns[column] = [
                _RANDOM_SIZES[pick] for pick in rng.integers(0, len(_RANDOM_SIZES), size=count)
            ]
    # 겹치는 인덱스 — 앞선 표에서 행을 골라 온 표처럼.
    return pd.DataFrame(columns, index=rng.integers(0, max(count // 2, 1), size=count))


def test_floor_placements_match_counting_each_floor_separately() -> None:
    """표마다 (동, 층) 묶음을 한 번만 내도 층마다 잘라 세던 값과 비트까지 같다 — 설비지분 결측·
    1/3, 지분 칸 없는 표, 숫자 아닌 크기, 겹치는 인덱스, FAB 밖 층, 면적 0 캔버스를 섞는다."""
    rng = np.random.default_rng(20261021)
    for trial in range(24):
        crowded = trial % 4 == 0
        count = int(rng.integers(0, 600 if crowded else 300))
        counted = _random_floor_rows(rng, count, crowded=crowded, shares=True, sizes=True)
        unplaced = _random_floor_rows(
            rng, count // 3, crowded=crowded, shares=bool(trial % 2), sizes=False
        )
        located = (
            counted
            if trial % 3
            else _random_floor_rows(rng, count, crowded=crowded, shares=False, sizes=True)
        )
        canvases = {
            key: (0.0, 60.0) if pick == 0 else (float(rng.integers(50, 400)), 123.4)
            for key, pick in zip(FLOOR_KEYS, rng.integers(0, 5, size=len(FLOOR_KEYS)), strict=True)
        }
        placements = floor_placements(counted, unplaced, located, canvases.__getitem__)
        assert placements == _floor_placements_one_floor_at_a_time(
            counted, unplaced, located, canvases.__getitem__
        ), trial


def test_floor_placements_do_not_read_sizes_of_an_empty_located_frame() -> None:
    """도면에 그린 행이 없으면 Xsize·Ysize 칸이 없는 표여도 점유율은 0 이다."""
    counted = pd.DataFrame({"동": ["C1"], "층": ["1F"]})
    located = pd.DataFrame({"동": pd.Series(dtype="string"), "층": pd.Series(dtype="string")})

    placements = floor_placements(counted, counted.iloc[0:0], located, lambda key: (100.0, 60.0))

    assert placements[FLOOR_KEYS.index(("C1", "1F"))] == FloorPlacement(("C1", "1F"), 1.0, 0.0, 0.0)
    assert all(placement.occupancy == 0.0 for placement in placements)


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


# ------------------------------------------------------------------ 호기 상자 색·범례
TODAY = date(2026, 10, 16)


def _legend_floor() -> tuple[pd.DataFrame, pd.DataFrame]:
    """한 층의 호기 여덟과 비가동 일정 하나. 판정은 `services/space_unit_state` 규칙을 따른다."""
    base: dict[str, object] = {
        "공정소분류": "P",
        "투자Capa": None,
        "반입일정": None,
        "반입실적": None,
        "반입상태": None,
        "Qual일정": None,
        "Qual실적": None,
        "Qual상태": None,
        "정지일정": None,
        "반출/이설일정": None,
        "보관유무": "N",
        "기존설비여부": "Y",
    }
    rows = [
        {"설비명": "U1", "공정구분": "PKG"},
        # 반입 전(반입일정이 기준일 뒤).
        {"설비명": "U2", "공정구분": " pkg ", "기존설비여부": "N", "반입일정": "2026-12-01"},
        {"설비명": "U3", "공정구분": "MI", "반출/이설일정": "2027-01-01"},
        {"설비명": "U4", "공정구분": "TEST", "보관유무": "Y"},
        # 반입 지연 — 실적이 들어올 때까지 반입 전이고 빨강이다.
        {"설비명": "U5", "공정구분": "S.PKG", "반입일정": "2026-09-01", "반입상태": "지연"},
        {
            "설비명": "U6",
            "공정구분": "FDY",
            "정지일정": "2026-10-01",
            "반출/이설일정": "2026-11-01",
        },
        # 일정이 지났는데 실적이 비고 확정 — 미확인.
        {"설비명": "U7", "공정구분": "물류", "반입일정": "2026-09-01", "반입상태": "확정"},
        # 도면 이탈일이 지나 도면에 없다.
        {"설비명": "U8", "공정구분": "FRONT", "반출/이설일정": "2026-10-01"},
    ]
    equipment = pd.DataFrame([{**base, **row} for row in rows])
    downtime = pd.DataFrame(
        [{"설비명": "U1", "비가동유형": "고장", "시작일": "2026-10-10", "종료일": "2026-10-20"}]
    )
    return equipment, downtime


def _counts(
    equipment: pd.DataFrame, downtime: pd.DataFrame, choice: ColorChoice, as_of: date = TODAY
) -> dict[str, float]:
    """화면처럼 경계 날짜를 한 번 구해(오늘 = `TODAY`) 기준일 `as_of` 의 범례 대수를 센다."""
    boundaries = unit_boundaries(equipment, downtime, today=TODAY)
    return space_legend_counts(equipment, boundaries, choice=choice, as_of=as_of)


def _looks(
    equipment: pd.DataFrame, downtime: pd.DataFrame, choice: ColorChoice
) -> dict[str, dict[str, object]]:
    return unit_appearance(
        equipment, unit_boundaries(equipment, downtime, today=TODAY), choice=choice
    )


def test_the_floor_legend_counts_fills_and_marks_at_the_as_of_date() -> None:
    """채우기 칸은 지연 → 보관 → 체크한 그룹 → 그 밖이 이기고 합이 도면에 선 대수다. 테·덧표시
    칸은 따로 센다 — 반입 전, (실물이 있는) 반출/이설 예정, 정지 중, 운영 비가동, 미확인(설비 수).
    도면 이탈일이 지난 호기는 어디에도 세지 않는다."""
    equipment, downtime = _legend_floor()
    choice = default_color_choice()

    counts = _counts(equipment, downtime, choice)

    assert counts == {
        "PKG": 2.0,
        "MI": 1.0,
        LEGEND_STORAGE: 1.0,
        LEGEND_DELAY: 1.0,
        "FDY": 1.0,
        "물류": 1.0,
        LEGEND_PRE_ARRIVAL: 2.0,
        LEGEND_EXIT_PLANNED: 2.0,
        LEGEND_STOPPED: 1.0,
        LEGEND_OFFLINE: 1.0,
        LEGEND_UNCONFIRMED: 1.0,
    }
    # 체크를 끈 그룹은 그 밖(기본 회색)이다. 보관·지연은 체크와 무관하다.
    unchecked = ColorChoice(choice.basis, (), frozenset(LINE_TYPE_GROUPS) - {"PKG", "TEST"})
    partial_counts = _counts(equipment, downtime, unchecked)
    assert partial_counts[LEGEND_DEFAULT] == 2.0 and "PKG" not in partial_counts
    assert partial_counts[LEGEND_STORAGE] == 1.0
    # 기준일을 옮기면 테·덧표시가 따라간다 — 반입일정이 지나 실물, 반출/이설을 마쳐 도면에서 빠짐.
    later = _counts(equipment, downtime, choice, as_of=date(2027, 1, 2))
    assert later.get(LEGEND_PRE_ARRIVAL) == 1.0  # U5 는 실적이 들어올 때까지 반입 전
    assert "MI" not in later and "FDY" not in later and LEGEND_STOPPED not in later
    assert LEGEND_OFFLINE not in later


def test_the_floor_legend_shows_counts_when_viewing_and_only_fill_meanings_when_editing() -> None:
    """보기 범례는 대수가 있는 칸만 「PKG 2대」로 세우고 끝에 기준일을 단다. 편집 중(`None`)에는
    채우기 뜻(체크한 그룹·그 밖·보관·지연)만 — 편집 화면은 테·덧표시를 그리지 않는다."""
    equipment, downtime = _legend_floor()
    choice = default_color_choice()
    counts = _counts(equipment, downtime, choice)

    viewing = space_legend_markup(counts, choice=choice, as_of=TODAY)
    editing = space_legend_markup(None, choice=choice)

    assert "PKG 2대" in viewing and "반입 전 2대" in viewing and "미확인 1대" in viewing
    assert "TEST" not in viewing  # 대수가 없는 그룹은 세우지 않는다
    assert "기준 2026-10-16" in viewing
    assert tokens.SPACE_LINE_TYPE_FILLS["PKG"] in viewing
    assert tokens.SPACE_RING_PRE_ARRIVAL in viewing and tokens.SPACE_FLAG_FILL in viewing
    # 반입 예정 견본 점선은 도면 테처럼 굵다(3px — 2026-10-23 사용자 요청).
    assert f"border:3px dashed {tokens.SPACE_RING_PRE_ARRIVAL}" in viewing
    for label in (*LINE_TYPE_GROUPS, LEGEND_DEFAULT, LEGEND_STORAGE, LEGEND_DELAY):
        assert f"</span>{label}</span>" in editing
    for label in (LEGEND_PRE_ARRIVAL, LEGEND_EXIT_PLANNED, LEGEND_STOPPED, LEGEND_UNCONFIRMED):
        assert label not in editing
    assert "대<" not in editing and "기준" not in editing


def test_unit_appearance_carries_the_checked_group_colour_and_the_boundary_dates() -> None:
    """호기마다 체크한 그룹 색(아니면 기본 회색)과 경계 날짜를 싣는다. 지연·보관 면은 브라우저가
    기준일로 덮으므로 여기의 면은 색 기준만 반영한다."""
    equipment, downtime = _legend_floor()
    choice = ColorChoice(default_color_choice().basis, (), frozenset({"MI"}))

    looks = _looks(equipment, downtime, choice)

    assert looks["U3"]["fill"] == tokens.SPACE_LINE_TYPE_FILLS["MI"]
    assert looks["U3"]["ink"] == tokens.SPACE_LINE_TYPE_INKS["MI"]
    assert looks["U1"]["fill"] == tokens.SPACE_UNIT_DEFAULT_FILL  # PKG 는 체크를 껐다
    assert looks["U4"]["storage"] is True
    assert looks["U4"]["fill"] == tokens.SPACE_UNIT_DEFAULT_FILL
    assert looks["U1"]["offline"] == [["2026-10-10", "2026-10-20"]]
    assert looks["U5"]["delays"] == [["2026-09-01", None]] and looks["U5"]["realFrom"] is None
    assert looks["U6"]["stopOn"] == "2026-10-01" and looks["U6"]["exitOn"] == "2026-11-01"
    assert looks["U7"]["flag"] is True


def test_capa_groups_take_the_teal_ramp_by_number() -> None:
    """투자Capa 색 기준은 숫자 차례로 청록 단을 받는다 — 가장 작은 그룹이 1단(가장 옅은 단)이고
    하나씩 짙어진다(시안 `capaLevel` 과 같다). 숫자로 못 읽는 값과 빈 칸은 기본 회색이다."""
    equipment, downtime = _legend_floor()
    equipment["투자Capa"] = ["322K", "322K", "180K", "400K", "x", None, "180K", "520K"]
    capa = capa_groups(equipment["투자Capa"])
    choice = ColorChoice(COLOR_BASIS_CAPA, capa, frozenset(group.label for group in capa))

    looks = _looks(equipment, downtime, choice)

    assert [(group.label, group.level) for group in capa] == [
        ("180K", 0),
        ("322K", 1),
        ("400K", 2),
        ("520K", 3),
    ]
    assert looks["U3"]["fill"] == tokens.SPACE_CAPA_RAMP[0]
    assert looks["U1"]["fill"] == tokens.SPACE_CAPA_RAMP[1]
    assert looks["U8"]["fill"] == tokens.SPACE_CAPA_RAMP[3]
    assert looks["U5"]["fill"] == tokens.SPACE_UNIT_DEFAULT_FILL
    assert looks["U6"]["fill"] == tokens.SPACE_UNIT_DEFAULT_FILL


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("322K", 322_000.0),
        ("322 k", 322_000.0),
        (" 322k ", 322_000.0),
        ("322,000", 322_000.0),
        ("1.5M", 1_500_000.0),
        ("280", 280.0),
        (5, 5.0),
        (2.5, 2.5),
        (None, None),
        ("", None),
        ("x", None),
        ("-5K", None),
        ("1e3", None),
        ("322KB", None),
        ("K", None),
        (True, None),
        (float("nan"), None),
    ],
)
def test_capa_number_reads_thousands_and_millions_only(text: object, number: float | None) -> None:
    """투자Capa 는 자유 글이다 — 숫자(쉼표 허용)와 K·M 단위만 읽고 나머지는 못 읽는 값(회색)이다."""
    assert capa_number(text) == number


def test_capa_groups_merge_same_numbers_and_bin_more_than_seven_kinds_into_seven_ranges() -> None:
    """같은 수로 읽히는 글자는 한 그룹(이름은 가장 많이 쓴 글자)이고, 종류가 7을 넘으면 작은 수부터
    7구간에 고르게 나눠 「앞~뒤」로 묶는다. 단은 구간 차례(0~6)다."""
    same = capa_groups(pd.Series(["322K", "322,000", "322K", "180K"]))
    assert [(group.label, group.low, group.high) for group in same] == [
        ("180K", 180_000.0, 180_000.0),
        ("322K", 322_000.0, 322_000.0),
    ]

    kinds = [f"{value}K" for value in (100, 110, 120, 130, 140, 150, 160, 170, 180, 190)]
    values = pd.Series([*kinds, "x", None, "150K"])
    groups = capa_groups(values)

    assert len(groups) == CAPA_LEVELS
    assert [group.label for group in groups] == [
        "100K~110K",
        "120K~130K",
        "140K~150K",
        "160K",
        "170K",
        "180K",
        "190K",
    ]
    assert [group.level for group in groups] == list(range(CAPA_LEVELS))
    assert capa_group_of(values, groups).tolist() == [
        "100K~110K",
        "100K~110K",
        "120K~130K",
        "120K~130K",
        "140K~150K",
        "140K~150K",
        "160K",
        "170K",
        "180K",
        "190K",
        pd.NA,
        pd.NA,
        "140K~150K",
    ]
    assert capa_groups(pd.Series(["x", None, ""])) == ()
