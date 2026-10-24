# Purpose: 가정 설비 시나리오 배치 차이의 얹기·나누기·정규화·요소/이름표 합치기 규칙을 검증한다.

"""`services/layout_overlay.py` — 설비 시나리오 2단계 설계 5장·6-1 의 순수 규칙.

공식(공통) 배치 위에 「공식과 다른 것만」 을 얹고(`apply_unit_overlay` — 예외 없음), 편집본을 공통
쪽과 차이로 나누고(`split_layout`), 같아진 차이를 지운다(`normalize_layout_overlay`). 모듈 묶음은
묶음 통째이고, 공식에서 묶음 소속이 바뀐 모듈은 그 가정 배치에서 동·층만 맞추고 X·Y 를 비운다.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.layout_overlay import (
    EMPTY_LAYOUT_DIGEST,
    LayoutOverlay,
    MarkChange,
    Place,
    UnitChange,
    apply_unit_overlay,
    common_with_places,
    effective_floor_marks,
    effective_group_labels,
    label_changes,
    layout_base,
    layout_counts_words,
    make_layout_overlay,
    mark_changes,
    normalize_layout_overlay,
    overlay_unit_count,
    place_of,
    split_layout,
)

_DEFAULTS: dict[str, object] = {
    "공정대분류": "B/N",
    "공정소분류": "Process-A",
    "투자구분": "양산",
    "사용기준": "HBM",
    "동": "C1",
    "층": "1F",
    "Xsize": 12.0,
    "Ysize": 7.0,
    "보관유무": "N",
    "기존설비여부": "Y",
    "레이아웃표시": "Y",
}


def _master(*rows: dict[str, object]) -> pd.DataFrame:
    records = [{**_DEFAULTS, **row} for row in rows]
    return prepare_equipment_master(pd.DataFrame(records).reindex(columns=EQUIPMENT_COLUMNS))


def _pairs(master: pd.DataFrame) -> list[tuple[str, str]]:
    return [(str(name), f"k-{name}") for name in master["설비명"]]


def _keys(master: pd.DataFrame) -> list[str]:
    return [key for _, key in _pairs(master)]


def _places(master: pd.DataFrame) -> dict[str, Place]:
    return {f"k-{row['설비명']}": place_of(row) for _, row in master.iterrows()}


def _place(
    building: str | None,
    floor: str | None,
    x: float | None,
    y: float | None,
    w: float | None = 12.0,
    h: float | None = 7.0,
    flag: str = "Y",
) -> Place:
    return (building, floor, x, y, w, h, flag)


def _set(frame: pd.DataFrame, row: int, **values: str | float | None) -> None:
    for column, value in values.items():
        frame.at[row, column] = value


def _apply(master: pd.DataFrame, units: tuple[UnitChange, ...]) -> pd.DataFrame:
    applied = apply_unit_overlay(master, _pairs(master), units).equipment
    return prepare_equipment_master(applied)


# ------------------------------------------------------------------ 얹기


def test_an_empty_overlay_returns_an_equal_copy() -> None:
    master = _master({"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0})
    applied = apply_unit_overlay(master, _pairs(master), ())

    assert applied.equipment is not master
    pd.testing.assert_frame_equal(applied.equipment, master)
    assert (applied.official_places, applied.orphans, applied.regrouped) == ((), 0, ())


def test_a_unit_change_replaces_all_seven_cells_and_records_the_official_place() -> None:
    master = _master(
        {"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0},
        {"설비명": "B", "X좌표": 20.0, "Y좌표": 1.0},
    )
    moved = _place("C2", "3F", 5.0, 6.0, 8.0, 9.0, "N")
    applied = apply_unit_overlay(master, _pairs(master), (("k-A", None, moved),))

    row = applied.equipment.iloc[0]
    assert place_of(row) == moved
    assert place_of(applied.equipment.iloc[1]) == _place("C1", "1F", 20.0, 1.0)
    assert applied.official_places == (("k-A", _place("C1", "1F", 1.0, 1.0)),)
    prepare_equipment_master(applied.equipment)


def test_a_change_for_a_unit_gone_from_the_common_ledger_is_dropped_and_counted() -> None:
    master = _master({"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0})
    applied = apply_unit_overlay(
        master, _pairs(master), (("k-GONE", None, _place("C2", "2F", 1.0, 1.0)),)
    )

    assert applied.orphans == 1
    assert applied.official_places == ()


def test_a_change_equal_to_the_official_place_is_not_reported_as_different() -> None:
    master = _master({"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0})
    applied = apply_unit_overlay(
        master, _pairs(master), (("k-A", None, _place("C1", "1F", 1.0, 1.0)),)
    )

    assert applied.official_places == ()


def _group(
    *names: str, parent: str = "G", spot: tuple[str, str] = ("C1", "1F")
) -> list[dict[str, object]]:
    return [
        {
            "설비명": name,
            "Main 설비": parent,
            "동": spot[0],
            "층": spot[1],
            "X좌표": 10.0 * index,
            "Y좌표": 0.0,
            "Xsize": 10.0,
            "Ysize": 7.0,
        }
        for index, name in enumerate(names)
    ]


def test_a_module_added_officially_to_a_moved_group_joins_its_hypothetical_floor_unplaced() -> None:
    """공식에서 묶음에 모듈이 늘면, 가정에서 옮긴 묶음의 그 모듈은 가정 층으로 맞추고 X·Y 를
    비운다."""
    master = _master(*_group("M1", "M2", "M3"))
    moved = tuple(
        (f"k-{name}", "G", _place("C2", "3F", 10.0 * index, 5.0, 10.0, 7.0))
        for index, name in enumerate(("M1", "M2"))
    )
    applied = apply_unit_overlay(master, _pairs(master), moved)

    places = [place_of(row) for _, row in applied.equipment.iterrows()]
    assert places[2] == _place("C2", "3F", None, None, 10.0, 7.0)
    assert applied.regrouped == ("G",)
    prepare_equipment_master(applied.equipment)


def test_stayed_members_on_two_floors_take_the_majority_floor() -> None:
    master = _master(*_group("M1", "M2", "M3"))
    changes = (
        ("k-M1", "G", _place("C2", "3F", 0.0, 0.0, 10.0, 7.0)),
        ("k-M2", "G", _place("C2", "3F", 10.0, 0.0, 10.0, 7.0)),
        ("k-M3", "G", _place("C4", "4F", 20.0, 0.0, 10.0, 7.0)),
    )
    applied = apply_unit_overlay(master, _pairs(master), changes)

    places = [place_of(row) for _, row in applied.equipment.iterrows()]
    assert places[2] == _place("C2", "3F", None, None, 10.0, 7.0)
    prepare_equipment_master(applied.equipment)


def test_a_changed_single_unit_put_officially_into_an_unchanged_group_alone_is_unplaced() -> None:
    """검토 F3 — 차이 있는 단독 A 를 공식에서 차이 없는 묶음 G(B, C)에 넣으면 B·C 는 공식 자리
    그대로, A 만 G 층의 자리 없음이다(옛 규칙은 B·C 를 A 의 가정 층으로 끌고 갔다)."""
    master = _master(
        {**_group("A")[0], "Main 설비": "G", "동": "C1", "층": "1F"},
        *_group("B", "C"),
    )
    changes = (("k-A", None, _place("C5", "5F", 3.0, 3.0)),)
    applied = apply_unit_overlay(master, _pairs(master), changes)

    places = [place_of(row) for _, row in applied.equipment.iterrows()]
    assert places[0] == _place("C1", "1F", None, None)
    assert places[1:] == [place_of(row) for _, row in master.iloc[1:].iterrows()]
    assert applied.regrouped == ("G",)
    prepare_equipment_master(applied.equipment)


def test_a_group_renamed_officially_keeps_its_hypothetical_places() -> None:
    master = _master(*_group("M1", "M2", parent="NEW"))
    changes = tuple(
        (f"k-{name}", "OLD", _place("C2", "3F", 10.0 * index, 5.0, 10.0, 7.0))
        for index, name in enumerate(("M1", "M2"))
    )
    applied = apply_unit_overlay(master, _pairs(master), changes)

    assert [place_of(row) for _, row in applied.equipment.iterrows()] == [
        change[2] for change in changes
    ]
    assert applied.regrouped == ()


def test_merging_two_groups_officially_leaves_only_the_moved_in_side_unplaced() -> None:
    """공식에서 묶음 H 의 모듈을 G 로 합침 — G 쪽 차이가 머물고 H 에서 온 모듈만 자리 없음."""
    master = _master(*_group("G1", "G2"), *_group("H1", "H2", parent="G"))
    changes = (
        ("k-G1", "G", _place("C3", "2F", 0.0, 0.0, 10.0, 7.0)),
        ("k-G2", "G", _place("C3", "2F", 10.0, 0.0, 10.0, 7.0)),
        ("k-H1", "H", _place("C4", "6F", 0.0, 0.0, 10.0, 7.0)),
        ("k-H2", "H", _place("C4", "6F", 10.0, 0.0, 10.0, 7.0)),
    )
    applied = apply_unit_overlay(master, _pairs(master), changes)

    places = [place_of(row) for _, row in applied.equipment.iterrows()]
    assert places[:2] == [changes[0][2], changes[1][2]]
    assert places[2:] == [_place("C3", "2F", None, None, 10.0, 7.0)] * 2
    prepare_equipment_master(applied.equipment)


def test_a_module_that_left_its_group_is_a_single_unit_change() -> None:
    master = _master(*_group("M1", "M2", "M3"), {"설비명": "X", "X좌표": 50.0, "Y좌표": 50.0})
    # M3 의 차이는 G 로 기록됐지만 지금 공식에서 G 에는 M1·M2 만 남았다(아래에서 M3 를 떼어냄).
    master.loc[2, "Main 설비"] = None
    changes = (("k-M3", "G", _place("C2", "2F", 1.0, 1.0, 10.0, 7.0)),)
    applied = apply_unit_overlay(master, _pairs(master), changes)

    assert place_of(applied.equipment.iloc[2]) == changes[0][2]
    assert applied.regrouped == ()


def _random_master(rng: random.Random) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    spots = [("C1", "1F"), ("C2", "2F"), ("C3", "3F")]
    for group in range(rng.randint(1, 3)):
        spot = rng.choice(spots)
        rows += _group(
            *(f"G{group}-M{index}" for index in range(rng.randint(2, 4))),
            parent=f"G{group}",
            spot=spot,
        )
    for index in range(rng.randint(1, 4)):
        spot = rng.choice(spots)
        rows.append(
            {
                "설비명": f"S{index}",
                "동": spot[0],
                "층": spot[1],
                "X좌표": float(rng.randint(0, 50)),
                "Y좌표": float(rng.randint(0, 30)),
            }
        )
    return _master(*rows)


def test_applying_random_changes_never_raises_and_always_passes_the_read_check() -> None:
    """성질 — 공식 소속과 무관한 아무 차이를 얹어도 읽기 검증(모듈 행 동·층 같음)을 지난다(I4)."""
    rng = random.Random(20261025)
    spots = [("C1", "1F"), ("C2", "2F"), ("C4", "5F"), (None, None)]
    for _ in range(60):
        master = _random_master(rng)
        keys = _keys(master)
        groups = ["G0", "G1", "G2", "OLD", None]
        changes: list[UnitChange] = []
        for key in rng.sample(keys, rng.randint(1, len(keys))):
            spot = rng.choice(spots)
            placed = spot[0] is not None and rng.random() < 0.7
            changes.append(
                (
                    key,
                    rng.choice(groups),
                    _place(
                        spot[0],
                        spot[1],
                        float(rng.randint(0, 40)) if placed else None,
                        float(rng.randint(0, 20)) if placed else None,
                        10.0,
                        7.0,
                        rng.choice(["Y", "N"]),
                    ),
                )
            )
        changes.append(("k-GONE", None, _place("C1", "1F", 1.0, 1.0)))
        applied = apply_unit_overlay(master, _pairs(master), tuple(changes))
        prepare_equipment_master(applied.equipment)
        assert applied.orphans == 1


# ------------------------------------------------------------------ 나누기


def test_an_official_split_writes_only_moved_units_to_the_common_ledger() -> None:
    master = _master(
        {"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0},
        {"설비명": "B", "X좌표": 20.0, "Y좌표": 1.0},
    )
    edited = master.copy()
    edited.loc[0, "X좌표"] = 40.0
    official = layout_base(master, _keys(master))
    split = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=official.places,
        role="official",
        overlay_present=False,
    )

    assert split.refusal is None and split.units == ()
    assert split.common_places["k-A"] == _place("C1", "1F", 40.0, 1.0)
    assert split.common_places["k-B"] == official.places["k-B"]


def test_an_official_split_from_a_revision_with_differences_refuses_layout_edits_only() -> None:
    master = _master({"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0})
    official = layout_base(master, _keys(master))
    started = {"k-A": _place("C2", "2F", 5.0, 5.0)}
    edited = master.copy()
    _set(edited, 0, 동="C2", 층="2F", X좌표=5.0, Y좌표=5.0)
    same = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=started,
        role="official",
        overlay_present=True,
    )
    assert same.refusal is None
    # 날짜만 고친 저장 — 공통 쪽은 공식 값 그대로다(가정이던 때의 자리가 공식으로 새지 않는다).
    assert same.common_places["k-A"] == official.places["k-A"]

    edited.loc[0, "X좌표"] = 7.0
    moved = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=started,
        role="official",
        overlay_present=True,
    )
    assert moved.refusal is not None and "가정이던 때" in moved.refusal


def test_an_overlay_split_keeps_the_common_ledger_and_records_the_difference() -> None:
    master = _master(
        {"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0},
        {"설비명": "B", "X좌표": 20.0, "Y좌표": 1.0},
    )
    official = layout_base(master, _keys(master))
    edited = master.copy()
    _set(edited, 0, 동="C3", 층="4F", X좌표=9.0)
    split = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=official.places,
        role="overlay",
        overlay_present=False,
    )

    assert split.common_places == official.places
    assert split.units == (("k-A", None, _place("C3", "4F", 9.0, 1.0)),)


def test_a_new_unit_in_an_overlay_split_has_no_official_place_but_keeps_its_size() -> None:
    master = _master({"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0})
    official = layout_base(master, _keys(master))
    edited = _master(
        {"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0},
        {"설비명": "NEW", "동": "C2", "층": "2F", "X좌표": 3.0, "Y좌표": 3.0, "Xsize": 5.0},
    )
    split = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=official.places,
        role="overlay",
        overlay_present=False,
    )

    assert split.common_places["k-NEW"] == _place(None, None, None, None, 5.0, 7.0)
    assert split.units == (("k-NEW", None, _place("C2", "2F", 3.0, 3.0, 5.0, 7.0)),)


def test_a_new_module_in_an_existing_group_takes_the_groups_official_floor() -> None:
    """검토 F2a — 공식 묶음이 「동·층 없음」 과 「C1 1F」 로 갈리지 않게."""
    master = _master(*_group("M1", "M2"))
    official = layout_base(master, _keys(master))
    edited = _master(*_group("M1", "M2", "M3", spot=("C1", "1F")))
    split = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=official.places,
        role="overlay",
        overlay_present=False,
    )

    assert split.refusal is None
    assert split.common_places["k-M3"] == _place("C1", "1F", None, None, 10.0, 7.0)
    # 묶음 통째 — M3 가 공통과 달라 묶음의 모든 모듈이 차이에 든다.
    assert {key for key, _, _ in split.units} == {"k-M1", "k-M2", "k-M3"}
    assert {parent for _, parent, _ in split.units} == {"G"}


def test_an_overlay_split_refuses_grouping_units_on_different_official_floors() -> None:
    """검토 F2b — 공식 층이 다른 호기를 한 묶음으로 묶는 고침은 공식 설비 시나리오에서."""
    master = _master(*_group("M1", "M2"), {"설비명": "X", "동": "C2", "층": "3F"})
    official = layout_base(master, _keys(master))
    edited = master.copy()
    _set(edited, 2, 동="C1", 층="1F", X좌표=None, Y좌표=None)
    edited.loc[2, "Main 설비"] = "G"
    split = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=official.places,
        role="overlay",
        overlay_present=False,
    )

    assert split.refusal is not None
    assert "X 은 공식 C2 3F" in split.refusal and "묶음 G 은 C1 1F" in split.refusal


def test_grouping_units_on_the_same_official_floor_is_accepted_in_an_overlay_split() -> None:
    master = _master(*_group("M1", "M2"), {"설비명": "X", "X좌표": 40.0, "Y좌표": 0.0})
    official = layout_base(master, _keys(master))
    edited = master.copy()
    edited.loc[2, "Main 설비"] = "G"
    split = split_layout(
        layout_base(edited, _keys(edited)),
        official=official,
        started=official.places,
        role="overlay",
        overlay_present=False,
    )

    assert split.refusal is None


def test_splitting_then_applying_gives_back_the_edited_places() -> None:
    """왕복 성질(검토 F20) — 무작위 편집본을 가정 역할로 나눈 뒤 공통 쪽에 차이를 얹으면 편집본의
    일곱 칸이 그대로 돌아오고, 공통 쪽은 늘 읽기 검증을 지난다(I7)."""
    rng = random.Random(1025)
    spots = [("C1", "1F"), ("C2", "2F"), ("C3", "3F")]
    for _ in range(40):
        master = _random_master(rng)
        official = layout_base(master, _keys(master))
        edited = master.copy()
        groups = edited["Main 설비"].dropna().unique().tolist()
        for group in groups:
            if rng.random() < 0.5:
                spot = rng.choice(spots)
                rows = edited["Main 설비"].eq(group).fillna(False).to_numpy(dtype=bool)
                edited.loc[rows, "동"] = spot[0]
                edited.loc[rows, "층"] = spot[1]
                edited.loc[rows, "X좌표"] = [
                    float(rng.randint(0, 40)) for _ in range(int(rows.sum()))
                ]
        for index in edited.index[edited["Main 설비"].isna()]:
            if rng.random() < 0.5:
                spot = rng.choice(spots)
                _set(edited, int(index), 동=spot[0], 층=spot[1], Y좌표=9.0)
        if groups and rng.random() < 0.5:
            spot = rng.choice(spots)
            members = edited.index[edited["Main 설비"].eq(groups[0]).fillna(False)]
            same = edited.loc[members[0]]
            edited = pd.concat(
                [
                    edited,
                    pd.DataFrame(
                        [
                            {
                                **same.to_dict(),
                                "설비명": "NEW-MOD",
                                "X좌표": 33.0,
                                "Y좌표": 3.0,
                            },
                            {
                                **same.to_dict(),
                                "설비명": "NEW-S",
                                "Main 설비": None,
                                "동": spot[0],
                                "층": spot[1],
                                "X좌표": 1.0,
                                "Y좌표": 2.0,
                            },
                        ]
                    ),
                ],
                ignore_index=True,
            )
        edited = prepare_equipment_master(edited)
        keys = _keys(edited)
        split = split_layout(
            layout_base(edited, keys),
            official=official,
            started=official.places,
            role="overlay",
            overlay_present=False,
        )
        assert split.refusal is None
        common = common_with_places(edited, keys, split.common_places)
        prepare_equipment_master(common)
        back = apply_unit_overlay(
            common, list(zip(edited["설비명"], keys, strict=True)), split.units
        )
        assert [place_of(row) for _, row in back.equipment.iterrows()] == [
            place_of(row) for _, row in edited.iterrows()
        ]


# ------------------------------------------------------------------ 정규화


def test_normalizing_drops_unit_changes_equal_to_the_official_place() -> None:
    master = _master(
        {"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0},
        {"설비명": "B", "X좌표": 20.0, "Y좌표": 1.0},
    )
    base = layout_base(master, _keys(master))
    overlay = make_layout_overlay(
        [
            ("k-A", None, _place("C1", "1F", 1.0, 1.0)),
            ("k-B", None, _place("C2", "2F", 3.0, 3.0)),
            ("k-GONE", None, _place("C2", "2F", 3.0, 3.0)),
        ]
    )
    normalized = normalize_layout_overlay(overlay, base, {})

    assert normalized.units == (("k-B", None, _place("C2", "2F", 3.0, 3.0)),)


def test_normalizing_keeps_a_group_whole_until_every_module_matches() -> None:
    master = _master(*_group("M1", "M2"))
    base = layout_base(master, _keys(master))
    official = base.places
    one_moved = make_layout_overlay(
        [
            ("k-M1", "G", official["k-M1"]),
            ("k-M2", "G", _place("C1", "1F", 30.0, 30.0, 10.0, 7.0)),
        ]
    )
    assert {key for key, _, _ in normalize_layout_overlay(one_moved, base, {}).units} == {
        "k-M1",
        "k-M2",
    }
    same = make_layout_overlay([("k-M1", "G", official["k-M1"]), ("k-M2", "G", official["k-M2"])])
    assert normalize_layout_overlay(same, base, {}).units == ()


def _mark(mark_id: str, *, x: float = 1.0, label: str = "") -> FloorLayoutMark:
    return FloorLayoutMark(
        mark_id=mark_id,
        kind="column",
        x=x,
        y=1.0,
        w=2.0,
        h=2.0,
        rotation=0,
        label=label,
        color="",
        hatch=False,
        keep_out=False,
    )


def test_marks_merge_drops_and_replacements_in_official_order_then_new_marks() -> None:
    official = (_mark("A"), _mark("B"), _mark("C"))
    changes = (
        MarkChange("B", "drop"),
        MarkChange("NEW", "set", _mark("NEW", x=9.0)),
        MarkChange("A", "set", _mark("A", x=5.0)),
    )
    merged = effective_floor_marks(official, changes)

    assert [(mark.mark_id, mark.x) for mark in merged] == [("A", 5.0), ("C", 1.0), ("NEW", 9.0)]
    assert mark_changes(merged, official) == (
        MarkChange("B", "drop"),
        MarkChange("A", "set", _mark("A", x=5.0)),
        MarkChange("NEW", "set", _mark("NEW", x=9.0)),
    )


def test_a_mark_the_official_deleted_but_the_overlay_edited_stays_as_a_new_mark() -> None:
    merged = effective_floor_marks((_mark("B"),), (MarkChange("A", "set", _mark("A", x=4.0)),))

    assert [mark.mark_id for mark in merged] == ["B", "A"]


def test_reordering_official_marks_is_not_a_difference() -> None:
    official = (_mark("A"), _mark("B"))
    assert mark_changes((_mark("B"), _mark("A")), official) == ()


def test_labels_merge_cover_and_remove_and_diff_back() -> None:
    official = {"G": "top", "H": "center"}
    merged = effective_group_labels(official, (("G", "bottom"), ("H", None), ("K", "top")))

    assert merged == {"G": "bottom", "K": "top"}
    assert label_changes(merged, official) == (("G", "bottom"), ("H", None), ("K", "top"))


def test_normalizing_floors_drops_marks_and_labels_equal_to_the_official_floor() -> None:
    master = _master({"설비명": "A", "X좌표": 1.0, "Y좌표": 1.0})
    base = layout_base(master, _keys(master))
    floor = ("C1", "1F")
    overlay = make_layout_overlay(
        marks={
            floor: (
                MarkChange("A", "set", _mark("A")),
                MarkChange("ZZ", "drop"),
                MarkChange("B", "set", _mark("B", x=8.0)),
            )
        },
        labels={floor: (("G", "top"), ("NONE", None), ("H", "bottom"))},
    )
    normalized = normalize_layout_overlay(
        overlay, base, {floor: ((_mark("A"), _mark("B")), {"G": "top"})}
    )

    assert normalized.marks_for(floor) == (MarkChange("B", "set", _mark("B", x=8.0)),)
    assert normalized.labels_for(floor) == (("H", "bottom"),)


def test_the_digest_is_stable_and_empty_overlays_share_one_constant() -> None:
    overlay = make_layout_overlay(
        [("k-B", "G", _place("C1", "1F", 1.0, 2.0)), ("k-A", None, _place(None, None, None, None))],
        {("C1", "1F"): (MarkChange("X", "drop"),)},
        {("C1", "1F"): (("G", None),)},
    )
    again = make_layout_overlay(
        [("k-A", None, _place(None, None, None, None)), ("k-B", "G", _place("C1", "1F", 1.0, 2.0))],
        {("C1", "1F"): (MarkChange("X", "drop"),)},
        {("C1", "1F"): (("G", None),)},
    )

    assert overlay.digest() == again.digest() != EMPTY_LAYOUT_DIGEST
    assert LayoutOverlay().digest() == make_layout_overlay().digest() == EMPTY_LAYOUT_DIGEST
    assert not make_layout_overlay(marks={("C1", "1F"): ()})


def test_the_payload_is_plain_values_and_round_trips_to_the_current_classes() -> None:
    overlay = make_layout_overlay(
        [("k-A", "G", _place("C1", "1F", 1.0, 2.0))],
        {("C1", "1F"): (MarkChange("M", "set", _mark("M", label="문")), MarkChange("D", "drop"))},
        {("C2", "3F"): (("G", "bottom"),)},
    )
    payload = overlay.to_payload()

    def plain(value: Any) -> bool:
        if isinstance(value, (tuple, list)):
            return all(plain(item) for item in value)
        if isinstance(value, dict):
            return all(isinstance(key, str) and plain(item) for key, item in value.items())
        return value is None or isinstance(value, (str, int, float, bool))

    assert plain(payload)
    back = LayoutOverlay.from_payload(payload)
    assert back == overlay
    assert type(back.marks_for(("C1", "1F"))[0].mark) is FloorLayoutMark
    # JSON 목록으로 돌아와도 같은 값이다(지문이 JSON 으로 잰다).
    assert LayoutOverlay.from_payload(json.loads(json.dumps(payload))) == overlay


def test_unit_counts_treat_a_module_group_as_one_unit() -> None:
    master = _master(*_group("M1", "M2", "M3"), {"설비명": "S", "X좌표": 50.0, "Y좌표": 1.0})
    base = layout_base(master, _keys(master))
    overlay = make_layout_overlay(
        [(f"k-{name}", "G", _place("C2", "2F", 1.0, 1.0)) for name in ("M1", "M2", "M3", "S")]
    )

    assert overlay_unit_count(overlay, base) == 2
    assert layout_counts_words(2, 1, 0) == "호기 2대·요소 1개"
    assert layout_counts_words(0, 0, 0) == ""


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, "  "])
def test_blank_cells_read_as_none(value: object) -> None:
    row = {"동": value, "층": "1F", "X좌표": value, "Y좌표": 2.04, "Xsize": 1, "Ysize": 1}
    assert place_of({**row, "레이아웃표시": " y "}) == (None, "1F", None, 2.0, 1.0, 1.0, "Y")
