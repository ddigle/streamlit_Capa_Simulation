# Purpose: Space 층 사용 상태 규칙(검증·동 머리·끄기 대상·층 거르기·호기 셈·경고)을 검증한다.

from __future__ import annotations

import pandas as pd
import pytest

from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    LAYOUT_EXITED_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
)
from capa_simulation.services.fab_layout import FLOOR_KEYS
from capa_simulation.services.floor_state import (
    ACTIVE_STATE,
    FloorStates,
    building_active_count,
    building_state,
    floor_states_fingerprint,
    floor_unit_counts,
    floors_by_building,
    inactive_floor_summary,
    inactive_floor_warnings,
    inactive_label,
    master_location_options,
    newly_inactive,
    prepare_floor_states,
    selectable_floor_keys,
    with_building,
)


def _states(*rows: tuple[str, str, str], version: int = 1) -> FloorStates:
    return FloorStates(rows=prepare_floor_states({(b, f): r for b, f, r in rows}), version=version)


def test_prepare_keeps_floor_key_order_and_reads_blank_as_in_use() -> None:
    rows = prepare_floor_states(
        {("C5", "6F"): "NOT_LINE", ("C1", "3F"): "UNUSED", ("C2", "1F"): "", ("C2", "2F"): None}
    )
    assert rows == (("C1", "3F", "UNUSED"), ("C5", "6F", "NOT_LINE"))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({("C6", "1F"): "UNUSED"}, "FAB 의 층이 아닙니다"),
        ({("C1", "7F"): "UNUSED"}, "FAB 의 층이 아닙니다"),
        ({("C1", "1F"): "OFFICE"}, "사용 안 함·생산라인 아님"),
        ({("C1", "1F"): 3}, "사용 안 함·생산라인 아님"),
    ],
)
def test_prepare_refuses_unknown_floors_and_reasons(
    raw: dict[tuple[str, str], object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_floor_states(raw)


def test_states_read_helpers() -> None:
    states = _states(("C1", "3F", "UNUSED"), ("C2", "1F", "NOT_LINE"))
    assert states.reason_of(("C1", "3F")) == "UNUSED"
    assert states.reason_of(("C1", "1F")) is None
    assert not states.is_active(("C2", "1F")) and states.is_active(("C2", "2F"))
    assert len(states.active_keys) == len(FLOOR_KEYS) - 2
    assert states.inactive == {("C1", "3F"): "UNUSED", ("C2", "1F"): "NOT_LINE"}


def test_building_head_value_and_count() -> None:
    draft = {("C1", floor): "NOT_LINE" for floor in ("1F", "2F", "3F", "4F", "5F", "6F")}
    draft[("C2", "3F")] = "UNUSED"
    assert building_state(draft, "C1") == "NOT_LINE"
    assert building_state(draft, "C3") == ACTIVE_STATE
    assert building_state(draft, "C2") is None
    assert building_active_count(draft, "C2") == (5, 6)
    mixed = {**draft, ("C1", "1F"): "UNUSED"}
    assert building_state(mixed, "C1") is None


def test_with_building_sets_or_clears_one_building_only() -> None:
    draft = {("C1", "3F"): "UNUSED", ("C5", "1F"): "UNUSED"}
    turned_off = with_building(draft, "C5", "NOT_LINE")
    assert {key for key in turned_off if key[0] == "C5"} == {
        key for key in FLOOR_KEYS if key[0] == "C5"
    }
    assert set(turned_off.values()) == {"UNUSED", "NOT_LINE"}
    assert turned_off[("C1", "3F")] == "UNUSED"
    assert with_building(draft, "C5", None) == {("C1", "3F"): "UNUSED"}
    assert with_building(draft, "C5", ACTIVE_STATE) == {("C1", "3F"): "UNUSED"}


def test_newly_inactive_skips_reason_changes() -> None:
    before = _states(("C1", "3F", "UNUSED"))
    draft = {("C1", "3F"): "NOT_LINE", ("C2", "1F"): "UNUSED"}
    assert newly_inactive(before, draft) == (("C2", "1F"),)


def test_fingerprint_follows_content_not_version() -> None:
    one = _states(("C1", "3F", "UNUSED"), version=1)
    two = _states(("C1", "3F", "UNUSED"), version=7)
    other = _states(("C1", "3F", "NOT_LINE"))
    assert floor_states_fingerprint(one) == floor_states_fingerprint(two)
    assert floor_states_fingerprint(one) != floor_states_fingerprint(other)
    assert floor_states_fingerprint(FloorStates()) != floor_states_fingerprint(one)


def test_selectable_floor_keys_keeps_the_open_floor() -> None:
    states = _states(("C1", "3F", "UNUSED"), ("C2", "1F", "UNUSED"))
    keys = selectable_floor_keys(states)
    assert ("C1", "3F") not in keys and len(keys) == len(FLOOR_KEYS) - 2
    kept = selectable_floor_keys(states, keep=("C1", "3F"))
    assert ("C1", "3F") in kept and ("C2", "1F") not in kept
    assert list(kept) == [key for key in FLOOR_KEYS if key in set(kept)]


def test_master_location_options_drop_only_fully_inactive_values_but_keep_present_ones() -> None:
    whole_c5 = [("C5", floor, "NOT_LINE") for floor in ("1F", "2F", "3F", "4F", "5F", "6F")]
    every_6f = [(building, "6F", "UNUSED") for building in ("C1", "C2", "C3", "C4")]
    states = _states(*whole_c5, *every_6f, ("C1", "3F", "UNUSED"))
    buildings, floors = master_location_options(states, pd.DataFrame({"동": [], "층": []}))
    assert buildings == ["C1", "C2", "C3", "C4"]
    assert floors == ["1F", "2F", "3F", "4F", "5F"]  # 3F 는 짝(C1 3F)만 꺼져 남는다

    present = pd.DataFrame({"동": ["C5", None, "X9"], "층": ["6F", "1F", None]})
    buildings, floors = master_location_options(states, present)
    assert buildings == ["C1", "C2", "C3", "C4", "C5"]
    assert floors == ["1F", "2F", "3F", "4F", "5F", "6F"]


def test_floors_by_building_lists_active_floors() -> None:
    states = _states(("C1", "3F", "UNUSED"))
    by_building = floors_by_building(states)
    assert by_building["C1"] == ("1F", "2F", "4F", "5F", "6F")
    assert by_building["C2"] == ("1F", "2F", "3F", "4F", "5F", "6F")


def test_floor_unit_counts_count_units_not_rows() -> None:
    status = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: ["M-1", "M-2", "M-3", "M-4", "S-1", "S-2", "GONE", "OUT"],
            PARENT_EQUIPMENT_COLUMN: ["MAIN", "MAIN", "MAIN", "MAIN", None, None, None, None],
            "동": ["C1", "C1", "C1", "C1", "C1", "C1", "C1", "C9"],
            "층": ["3F"] * 7 + ["1F"],
            "레이아웃표시": ["Y", "Y", "Y", "Y", "N", "Y", "Y", "Y"],
            LAYOUT_EXITED_COLUMN: [False, False, False, False, False, False, True, False],
        }
    )
    assert floor_unit_counts(status) == {("C1", "3F"): 3}
    assert floor_unit_counts(status.iloc[0:0]) == {}


def test_inactive_floor_warnings_count_moved_and_new_rows_only() -> None:
    states = _states(("C1", "3F", "UNUSED"))
    saved = pd.DataFrame(
        {EQUIPMENT_ID_COLUMN: ["STAY", "MOVE"], "동": ["C1", "C2"], "층": ["3F", "1F"]}
    )
    master = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: ["STAY", "MOVE", "NEW", "ELSE"],
            "동": ["C1", "C1", "C1", "C2"],
            "층": ["3F", "3F", "3F", "2F"],
        }
    )
    (warning,) = inactive_floor_warnings(master, saved, states)
    assert warning.startswith("비활성 층으로 옮긴 호기 2대")
    assert "C1 3F 사용 안 함" in warning and "MOVE, NEW" in warning and "STAY" not in warning
    assert inactive_floor_warnings(saved, saved, states) == []
    assert inactive_floor_warnings(master, saved, FloorStates()) == []


def test_labels_and_summary() -> None:
    assert inactive_label("UNUSED") == "사용 안 함"
    assert inactive_label("NOT_LINE") == "생산라인 아님"
    assert inactive_label("FUTURE") == "비활성"
    whole_c5 = [("C5", floor, "NOT_LINE") for floor in ("1F", "2F", "3F", "4F", "5F", "6F")]
    states = _states(
        ("C1", "3F", "UNUSED"), ("C1", "5F", "UNUSED"), ("C1", "6F", "UNUSED"), *whole_c5
    )
    assert inactive_floor_summary(states) == "C1 3F·5F~6F(사용 안 함) · C5 1F~6F(생산라인 아님)"
    assert inactive_floor_summary(FloorStates()) == ""
