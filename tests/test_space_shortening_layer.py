# Purpose: Space 「필요 단축」 보기의 구간·배지·흐림·층 대수·추가N·링크 층 규칙을 검사한다.

"""`services/space_shortening_layer.py`(명세 10-1 T-U1~T-U10).

계획은 손으로 만든 `ShorteningPlan`(호기 표·공정 x 월·마스터 속성)이고 상태 행은 Space 상태 표의 칸
(설비명·설비키·공정소분류·동·층)만 둔다 — 계산은 돌리지 않는다. 같은 날 낸 계획은 목표 Qual 을 오늘
아래로 당기지 않으므로 기한 지남 줄은 손으로 만든다(결정 D1).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from capa_simulation.services.equipment_units import UNIT_KEY_COLUMN
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    PROCESS_MONTH_COLUMNS,
    STATUS_EXPIRED,
    STATUS_MET,
    STATUS_NEW_LIMIT,
    UNIT_MASTER_COLUMNS,
    UNIT_PLAN_COLUMNS,
    LevelPlan,
    ShorteningPlan,
)
from capa_simulation.services.space_shortening_layer import (
    BUCKET_EXPIRED,
    BUCKET_LARGE,
    BUCKET_MEDIUM,
    BUCKET_SMALL,
    bucket_of,
    build_shortening_layer,
    day_text,
    fab_floor_counts,
    fab_layer_summary,
    floor_layer,
    floor_short_line,
    shortening_space_floors,
)

TODAY = date(2026, 10, 24)


def _unit(
    process: str,
    unit: str,
    *,
    days: int | None,
    left: int,
    kind: str = KIND_SHORTENED,
    month: int | None = 202611,
    modules: int = 1,
) -> dict[str, object]:
    target = TODAY + timedelta(days=left)
    return {
        "공정": process,
        "호기": unit,
        "구분": kind,
        "기존 Qual": None if days is None else target + timedelta(days=days),
        "목표 Qual": target,
        "기여 시작": target + timedelta(days=1),
        "단축일수": days,
        "늘어난 환산대수": 0.5,
        "대상 월": month,
        "해소 기여 월": "202611",
        "모듈 수": modules,
    }


def _master_row(
    unit: str, process: str, building: str | None, floor: str | None
) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(UNIT_MASTER_COLUMNS)
    row.update(
        {
            "호기": unit,
            "공정소분류": process,
            "동": building,
            "층": floor,
            "Model": f"MODEL-{unit}",
            "담당자": f"담당-{unit}",
            "모듈 수": 1,
            "환산비": 1.0,
        }
    )
    return row


def _plan(
    levels: dict[float, list[dict[str, object]]],
    master: list[dict[str, object]],
    *,
    months: list[dict[str, object]] | None = None,
) -> ShorteningPlan:
    month_frame = pd.DataFrame(months or [], columns=list(PROCESS_MONTH_COLUMNS))
    return ShorteningPlan(
        months=(202611, 202612),
        today=TODAY,
        processes=("D/A", "W/B"),
        cutoff_days={"D/A": 10, "W/B": 10},
        levels=tuple(
            LevelPlan(
                level=level,
                process_months=month_frame,
                units=pd.DataFrame(rows, columns=list(UNIT_PLAN_COLUMNS)),
            )
            for level, rows in levels.items()
        ),
        required_only=("X/X",),
        unit_master=pd.DataFrame(master, columns=list(UNIT_MASTER_COLUMNS)),
    )


def _rows(entries: list[tuple[str, str | None, str, str, str]]) -> pd.DataFrame:
    """(설비명, Main 설비, 공정소분류, 동, 층) → 상태 행. 설비키는 Main 설비, 없으면 설비명."""
    return pd.DataFrame(
        {
            "설비명": [name for name, *_ in entries],
            "Main 설비": [parent for _, parent, *_ in entries],
            UNIT_KEY_COLUMN: [parent or name for name, parent, *_ in entries],
            "공정소분류": [process for *_, process, _, _ in entries],
            "동": [building for *_, building, _ in entries],
            "층": [floor for *_, floor in entries],
        }
    )


EMPTY_ROWS = _rows([])


# ------------------------------------------------------------------ T-U1 구간 경계


def test_buckets_follow_the_day_bands_and_a_past_target_is_expired() -> None:
    later = TODAY + timedelta(days=3)
    assert [bucket_of(days, later, TODAY) for days in (1, 7, 8, 14, 15, 40)] == [
        BUCKET_SMALL,
        BUCKET_SMALL,
        BUCKET_MEDIUM,
        BUCKET_MEDIUM,
        BUCKET_LARGE,
        BUCKET_LARGE,
    ]
    earlier = TODAY - timedelta(days=1)
    assert {bucket_of(days, earlier, TODAY) for days in (1, 8, 30)} == {BUCKET_EXPIRED}
    assert bucket_of(3, TODAY, TODAY) == BUCKET_SMALL
    assert (day_text(0), day_text(5), day_text(-3)) == ("오늘", "D-5", "기한 지남")


# ------------------------------------------------------------------ T-U2 계획 → 표시


def test_the_layer_marks_only_shortened_units_of_the_chosen_target() -> None:
    plan = _plan(
        {
            1.1: [
                _unit("W/B", "WB01", days=12, left=5),
                _unit("W/B", "추가1", days=None, left=20, kind=KIND_NEW),
            ],
            1.2: [_unit("W/B", "WB02", days=3, left=40)],
        },
        [_master_row("WB01", "W/B", "C1", "2F"), _master_row("WB02", "W/B", "C1", "3F")],
    )
    layer = build_shortening_layer(plan, 1.1, today=plan.today, imminent_days=30)
    assert set(layer.marks) == {"WB01"}
    mark = layer.marks["WB01"]
    assert (mark.days, mark.left, mark.bucket, mark.imminent) == (12, 5, BUCKET_MEDIUM, True)
    assert (mark.manager, mark.model, mark.modules) == ("담당-WB01", "MODEL-WB01", 1)
    assert (mark.main_text, mark.sub_text) == ("−12일", "D-5")
    assert "기존 Qual" in mark.tip and "대상 월 2026-11" in mark.tip
    assert [unit.name for unit in layer.virtuals] == ["추가1"]
    assert layer.unmatched == 1
    other = build_shortening_layer(plan, 1.2, today=plan.today, imminent_days=30)
    assert set(other.marks) == {"WB02"} and not other.virtuals
    assert not other.marks["WB02"].imminent
    # 임박 날수는 받은 값이다(필요 단축 일정 「기한 임박」 과 같은 칸).
    narrow = build_shortening_layer(plan, 1.1, today=plan.today, imminent_days=3)
    assert not narrow.marks["WB01"].imminent


# ------------------------------------------------------------------ T-U3 모듈 묶음 배지 하나


def _module_plan() -> ShorteningPlan:
    return _plan(
        {
            1.1: [
                _unit("W/B", "APW02", days=9, left=4, modules=4),
                _unit("W/B", "WB10", days=2, left=10),
                _unit("W/B", "WB03", days=2, left=10),
                _unit("D/A", "DA01", days=20, left=1),
            ]
        },
        [
            _master_row("APW02", "W/B", "C1", "2F"),
            _master_row("WB10", "W/B", "C1", "2F"),
            _master_row("WB03", "W/B", "C1", "2F"),
            _master_row("DA01", "D/A", "C1", "2F"),
        ],
    )


def test_a_module_group_gets_one_badge_over_its_drawn_modules() -> None:
    layer = build_shortening_layer(_module_plan(), 1.1, today=TODAY, imminent_days=30)
    rows = _rows(
        [(f"APW02{suffix}", "APW02", "W/B", "C1", "2F") for suffix in "ABCD"]
        + [
            ("WB10", None, "W/B", "C1", "2F"),
            ("WB03", None, "W/B", "C1", "2F"),
            ("DA01", None, "D/A", "C1", "2F"),
        ]
    )
    result = floor_layer(layer, rows, EMPTY_ROWS, focus=None, dim_others=True)
    badges = {badge["key"]: badge for badge in result.badges}
    assert badges["APW02"]["ids"] == ["APW02A", "APW02B", "APW02C", "APW02D"]
    assert {result.looks[f"APW02{suffix}"]["layer"] for suffix in "ABCD"} == {BUCKET_MEDIUM}
    # 차례는 결정적이다 — 남은 날 짧은 순, 같으면 호기 번호.
    assert [badge["key"] for badge in result.badges] == ["DA01", "APW02", "WB03", "WB10"]
    assert result.pick_ids == ["DA01", "APW02A", "WB03", "WB10"]
    assert result.counts == {BUCKET_LARGE: 1, BUCKET_MEDIUM: 1, BUCKET_SMALL: 2}
    # 모듈 둘만 그렸으면 배지의 ids 도 둘이다.
    two = floor_layer(layer, rows.iloc[[0, 1]], EMPTY_ROWS, focus=None, dim_others=True)
    assert [badge["ids"] for badge in two.badges] == [["APW02A", "APW02B"]]


# ------------------------------------------------------------------ T-U4 흐림


def test_unmarked_units_dim_only_when_asked_and_a_focus_dims_other_processes() -> None:
    layer = build_shortening_layer(_module_plan(), 1.1, today=TODAY, imminent_days=30)
    rows = _rows(
        [
            ("WB10", None, "W/B", "C1", "2F"),
            ("DA01", None, "D/A", "C1", "2F"),
            ("WB99", None, "W/B", "C1", "2F"),
        ]
    )
    dim = floor_layer(layer, rows, EMPTY_ROWS, focus=None, dim_others=True)
    assert dim.looks["WB99"] == {"dim": True}
    assert dim.looks["WB10"] == {"layer": BUCKET_SMALL, "dim": False}
    plain = floor_layer(layer, rows, EMPTY_ROWS, focus=None, dim_others=False)
    assert "WB99" not in plain.looks
    focused = floor_layer(layer, rows, EMPTY_ROWS, focus="W/B", dim_others=False)
    assert focused.looks["DA01"] == {"layer": BUCKET_LARGE, "dim": True}
    assert focused.looks["WB10"]["dim"] is False
    assert {badge["key"]: badge["dim"] for badge in focused.badges} == {"WB10": False, "DA01": True}


# ------------------------------------------------------------------ T-U5 추가N


def test_virtual_units_show_on_every_drawn_floor_and_count_once_in_the_fab_summary() -> None:
    plan = _plan(
        {
            1.1: [
                _unit("W/B", "추가1", days=None, left=20, kind=KIND_NEW),
                _unit("W/B", "추가2", days=None, left=25, kind=KIND_NEW),
                _unit("D/A", "추가1", days=None, left=25, kind=KIND_NEW),
            ]
        },
        [],
    )
    layer = build_shortening_layer(plan, 1.1, today=TODAY, imminent_days=30)
    counted = _rows([("WB01", None, "W/B", "C1", "2F"), ("WB02", None, "W/B", "C1", "3F")])
    counts = fab_floor_counts(layer, counted, EMPTY_ROWS)
    assert counts[("C1", "2F")].virtual == 2 and counts[("C1", "3F")].virtual == 2
    second = floor_layer(layer, counted.iloc[[0]], EMPTY_ROWS, focus=None, dim_others=True)
    assert [unit.name for unit in second.virtuals] == ["추가1", "추가2"]
    summary = fab_layer_summary(layer, counted)
    assert summary.virtual == 3 and summary.total == 0
    # 그 공정 호기가 도면에 없으면(D/A) 층에는 없고 FAB 요약에만 든다.
    assert all(unit.process == "W/B" for unit in second.virtuals)
    # 비활성 층에는 추가N 을 붙이지 않는다.
    off = fab_floor_counts(layer, counted, EMPTY_ROWS, inactive={("C1", "3F")})
    assert ("C1", "3F") not in off and off[("C1", "2F")].virtual == 2


# ------------------------------------------------------------------ T-U6 좌표 없는 단축 호기


def test_a_shortened_unit_without_coordinates_is_listed_on_its_floor_or_only_in_the_fab() -> None:
    plan = _plan(
        {1.1: [_unit("W/B", "WB05", days=4, left=8), _unit("W/B", "WB06", days=4, left=9)]},
        [_master_row("WB05", "W/B", "C1", "2F"), _master_row("WB06", "W/B", None, None)],
    )
    layer = build_shortening_layer(plan, 1.1, today=TODAY, imminent_days=30)
    drawn = _rows([("WB01", None, "W/B", "C1", "2F")])
    loose = _rows([("WB05", None, "W/B", "C1", "2F")])
    here = floor_layer(layer, drawn, loose, focus=None, dim_others=True)
    assert [mark.unit for mark in here.unplaced] == ["WB05"] and not here.badges
    counts = fab_floor_counts(layer, drawn, loose)
    assert counts[("C1", "2F")].units == 1 and counts[("C1", "2F")].unplaced == 1
    summary = fab_layer_summary(layer, drawn)
    assert (summary.total, summary.drawn, summary.unplaced) == (2, 0, 2)


# ------------------------------------------------------------------ T-U7 기한 지남


def test_an_expired_target_is_the_expired_bucket_and_late_months_are_counted() -> None:
    plan = _plan(
        {1.1: [_unit("W/B", "WB07", days=5, left=-3)]},
        [_master_row("WB07", "W/B", "C1", "2F")],
        months=[
            dict.fromkeys(PROCESS_MONTH_COLUMNS)
            | {"공정": "W/B", "생산계획년월": 202611, "상태": STATUS_EXPIRED},
            dict.fromkeys(PROCESS_MONTH_COLUMNS)
            | {"공정": "W/B", "생산계획년월": 202612, "상태": STATUS_NEW_LIMIT},
            dict.fromkeys(PROCESS_MONTH_COLUMNS)
            | {"공정": "D/A", "생산계획년월": 202611, "상태": STATUS_MET},
        ],
    )
    layer = build_shortening_layer(plan, 1.1, today=TODAY, imminent_days=30)
    mark = layer.marks["WB07"]
    assert (mark.bucket, mark.sub_text, mark.imminent) == (BUCKET_EXPIRED, "기한 지남", False)
    assert layer.expired_months == {"W/B": (202611, 202612)}
    drawn = _rows([("WB07", None, "W/B", "C1", "2F")])
    result = floor_layer(layer, drawn, EMPTY_ROWS, focus=None, dim_others=True)
    assert "기한 지남 달 2" in result.chips["W/B"]
    summary = fab_layer_summary(layer, drawn)
    assert (summary.expired, summary.expired_months) == (1, 2)


# ------------------------------------------------------------------ T-U8 층 대수


def test_floor_counts_follow_the_process_filter_and_skip_inactive_floors() -> None:
    layer = build_shortening_layer(_module_plan(), 1.1, today=TODAY, imminent_days=30)
    counted = _rows(
        [
            ("APW02A", "APW02", "W/B", "C1", "2F"),
            ("APW02B", "APW02", "W/B", "C1", "2F"),
            ("WB10", None, "W/B", "C1", "2F"),
            ("WB03", None, "W/B", "C1", "3F"),
            ("DA01", None, "D/A", "C1", "2F"),
        ]
    )
    counts = fab_floor_counts(layer, counted, EMPTY_ROWS)
    assert counts[("C1", "2F")].units == 3 and counts[("C1", "2F")].max_days == 20
    assert counts[("C1", "3F")].units == 1
    assert floor_short_line(counts[("C1", "2F")]) == "단축 3대 · 최대 −20일"
    assert floor_short_line(None) is None
    filtered = fab_floor_counts(layer, counted, EMPTY_ROWS, processes={"W/B"})
    assert filtered[("C1", "2F")].units == 2 and filtered[("C1", "2F")].max_days == 9
    summary = fab_layer_summary(layer, counted, processes={"W/B"})
    assert (summary.total, summary.filtered_out) == (3, 1)
    off = fab_floor_counts(layer, counted, EMPTY_ROWS, inactive={("C1", "3F")})
    assert ("C1", "3F") not in off
    assert fab_layer_summary(layer, counted, inactive={("C1", "3F")}).inactive == 1


# ------------------------------------------------------------------ T-U9 링크 층


def test_the_link_floor_is_the_most_shortened_active_floor_then_the_most_drawn() -> None:
    level_plan = _plan(
        {
            1.1: [
                _unit("W/B", "WB01", days=3, left=10),
                _unit("W/B", "WB02", days=3, left=10),
                _unit("W/B", "WB03", days=3, left=10),
                _unit("D/A", "DA01", days=3, left=10),
                _unit("D/A", "DA02", days=3, left=10),
                _unit("F/C", "추가1", days=None, left=10, kind=KIND_NEW),
                _unit("Z/Z", "추가1", days=None, left=10, kind=KIND_NEW),
            ]
        },
        [
            _master_row("WB01", "W/B", "C1", "3F"),
            _master_row("WB02", "W/B", "C1", "3F"),
            _master_row("WB03", "W/B", "C1", "2F"),
            _master_row("DA01", "D/A", "C2", "1F"),
            _master_row("DA02", "D/A", "C1", "5F"),
        ],
    ).at(1.1)
    unit_master = _plan(
        {1.1: []},
        [
            _master_row("WB01", "W/B", "C1", "3F"),
            _master_row("WB02", "W/B", "C1", "3F"),
            _master_row("WB03", "W/B", "C1", "2F"),
            _master_row("DA01", "D/A", "C2", "1F"),
            _master_row("DA02", "D/A", "C1", "5F"),
        ],
    ).unit_master
    equipment = pd.DataFrame(
        {
            "설비명": ["FC01A", "FC01B", "FC02", "FC03", "FC04"],
            "Main 설비": ["FC01", "FC01", None, None, None],
            "공정소분류": ["F/C"] * 5,
            "레이아웃표시": ["Y", "Y", "Y", "Y", "N"],
            "동": ["C2", "C2", "C3", "C3", "C2"],
            "층": ["1F", "1F", "1F", "1F", "1F"],
            "X좌표": [1.0, 2.0, 1.0, None, 1.0],
            "Y좌표": [1.0, 1.0, 1.0, 1.0, 1.0],
            "Xsize": [1.0, 1.0, 1.0, 1.0, 1.0],
            "Ysize": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    floors = shortening_space_floors(level_plan, unit_master, equipment)
    assert floors["W/B"] == ("C1", "3F")
    # 같으면 FAB 층 차례(C1 5F 가 C2 1F 앞).
    assert floors["D/A"] == ("C1", "5F")
    # 추가N 만이면 그려지는 설비키 수 — 모듈 둘은 한 대, 좌표 없는 FC03·레이아웃표시 N 은 세지
    # 않는다.
    assert floors["F/C"] == ("C2", "1F")
    assert "Z/Z" not in floors
    # 비활성 층은 고르지 않는다 — 고를 층이 없으면 표에 없다.
    blocked = shortening_space_floors(
        level_plan, unit_master, equipment, inactive={("C1", "3F"), ("C2", "1F"), ("C3", "1F")}
    )
    assert blocked["W/B"] == ("C1", "2F")
    assert "F/C" not in blocked


# ------------------------------------------------------------------ T-U10 공정 칩 좁히기


def test_a_focus_narrows_the_list_the_loose_units_and_the_virtuals() -> None:
    plan = _plan(
        {
            1.1: [
                _unit("W/B", "WB10", days=2, left=10),
                _unit("D/A", "DA01", days=20, left=1),
                _unit("D/A", "DA05", days=4, left=5),
                _unit("W/B", "추가1", days=None, left=20, kind=KIND_NEW),
                _unit("D/A", "추가1", days=None, left=20, kind=KIND_NEW),
            ]
        },
        [_master_row("DA05", "D/A", "C1", "2F")],
    )
    layer = build_shortening_layer(plan, 1.1, today=TODAY, imminent_days=30)
    rows = _rows([("WB10", None, "W/B", "C1", "2F"), ("DA01", None, "D/A", "C1", "2F")])
    loose = _rows([("DA05", None, "D/A", "C1", "2F")])
    both = floor_layer(layer, rows, loose, focus=None, dim_others=True)
    assert [mark.unit for mark in both.rows] == ["DA01", "WB10"]
    assert len(both.virtuals) == 2 and [mark.unit for mark in both.unplaced] == ["DA05"]
    assert both.chips["W/B"] == "W/B · 1대 최대 −2일 · 추가 1"
    only = floor_layer(layer, rows, loose, focus="W/B", dim_others=True)
    assert [mark.unit for mark in only.rows] == ["WB10"] and not only.unplaced
    assert [unit.process for unit in only.virtuals] == ["W/B"]
    assert {badge["key"] for badge in only.badges} == {"WB10", "DA01"}
    assert only.counts == {BUCKET_SMALL: 1}


@pytest.mark.parametrize("level", [0.9, 1.3])
def test_a_target_without_shortening_draws_nothing(level: float) -> None:
    plan = _plan({level: []}, [])
    layer = build_shortening_layer(plan, level, today=TODAY, imminent_days=30)
    result = floor_layer(
        layer, _rows([("WB01", None, "W/B", "C1", "2F")]), EMPTY_ROWS, focus=None, dim_others=False
    )
    assert not result.badges and not result.rows and result.chips == {"W/B": "W/B · 단축 없음"}
