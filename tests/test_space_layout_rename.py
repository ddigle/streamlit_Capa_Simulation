# Purpose: Space 편집기의 호기 이름 바꾸기 검증·반영·비가동 연쇄·미저장 기억을 검사한다.

"""이름 바꾸기는 표시 별칭이 아니라 설비 마스터의 설비명 자체다(2026-10-08 사용자 결정 「가」).

서비스 쪽은 적용값 읽기(`parse_editor_apply` 의 `renames`)·겹침 검사·반영(`apply_name_changes`)·
세션의 저장 안 한 이름 지도(`PendingRenames`)를 본다. 페이지 쪽은 JS 대역으로 적용값을 넣어
편집본·비가동 일정·RawData 선택이 따라가고, `배치 저장` 이 새 리비전에 새 이름을 쓰며 옛 리비전은
옛 이름 그대로인지 본다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import space_layout_editor
from capa_simulation.components.equipment_data_workspace import (
    DOWNTIME_VIEW_PREFIX,
    FOLLOWED_FILTERS_KEY,
    LAST_REMOVED_KEY,
    PENDING_RENAMES_KEY,
    SELECTION_KEY,
)
from capa_simulation.components.table_view_controls import filter_widget_key
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_bulk_delete import DOWNTIME_TARGET, EQUIPMENT_TARGET
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_master,
)
from capa_simulation.services.space_layout_edit import (
    EditorApply,
    NameChange,
    PendingRenames,
    apply_layout_edits,
    apply_name_changes,
    compose_renames,
    downtime_with_renames,
    layout_changes,
    live_renames,
    name_changes,
    new_unit_options,
    other_change_count,
    parse_editor_apply,
    reserved_names,
    table_changed,
    unsaved_unit_ids,
)

FLOOR = ("C1", "1F")
OTHER = ("C2", "2F")
CANVAS = (100.0, 60.0)
PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
FAKE_APPLY_KEY = "test_fake_rename_apply"


def _master(*extra: dict[str, Any]) -> pd.DataFrame:
    """EQ-01·EQ-02(C1 1F 배치)와 덧붙인 행. 덧붙인 행은 EQ-01 을 바탕으로 값만 바꾼다."""
    base = _equipment()
    records = base.to_dict(orient="records")
    records += [records[0] | values for values in extra]
    return prepare_equipment_master(pd.DataFrame(records, columns=base.columns))


def _bundle_master() -> pd.DataFrame:
    """C1 1F 의 모듈 묶음 BIG(M-1·M-2 배치) + 편집기에 없는 형제 M-3(레이아웃표시 N)."""
    return _master(
        {"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0},
        {"설비명": "M-2", "Main 설비": "BIG", "X좌표": 62.0, "Y좌표": 30.0},
        {"설비명": "M-3", "Main 설비": "BIG", "레이아웃표시": "N", "X좌표": None, "Y좌표": None},
    )


def _parse(payload: dict[str, Any], master: pd.DataFrame, **overrides: Any) -> EditorApply:
    """편집기는 레이아웃표시 Y 인 호기만 받는다(M-3 은 편집기에 없다)."""
    shown = master.loc[master["레이아웃표시"].eq("Y")]
    parents = shown["Main 설비"].dropna().astype(str)
    options: dict[str, Any] = {
        "editor_ids": set(shown["설비명"].astype(str)),
        "master_ids": set(master["설비명"].astype(str)),
        "floor": FLOOR,
        "floors": [FLOOR, OTHER],
        "canvas": CANVAS,
        "unit_options": new_unit_options(master),
        "editor_groups": set(parents),
    }
    options.update(overrides)
    return parse_editor_apply(payload, **options)


def _rename(*items: tuple[str, str, str]) -> dict[str, Any]:
    return {"renames": [{"kind": kind, "from": old, "to": new} for kind, old, new in items]}


# ------------------------------------------------------------------ 읽기·겹침 검사


def test_a_unit_rename_is_read_apart_from_the_layout_changes() -> None:
    apply = _parse(_rename(("unit", "EQ-01", " EQ-101 ")), _master())

    assert apply.changes == ()
    assert apply.renames == (NameChange(kind="unit", old="EQ-01", new="EQ-101"),)
    assert apply.unit_renames == {"EQ-01": "EQ-101"} and apply.group_renames == {}


def test_a_rename_to_the_same_name_is_dropped_but_a_case_change_is_kept() -> None:
    assert _parse(_rename(("unit", "EQ-01", "EQ-01")), _master()).renames == ()
    kept = _parse(_rename(("unit", "EQ-01", "eq-01")), _master())
    assert kept.unit_renames == {"EQ-01": "eq-01"}


@pytest.mark.parametrize(
    ("renames", "message"),
    [
        ([("unit", "EQ-01", "   ")], "EQ-01 의 새 이름을 비울 수 없습니다"),
        ([("unit", "EQ-01", "X" * 41)], "1~40자"),
        ([("unit", "EQ-01", "EQ\t101")], "탭·줄바꿈·특수 공백"),
        ([("unit", "EQ-01", "eq-02")], "이미 있는 설비명입니다\\(EQ-02\\)"),
        ([("unit", "EQ-01", " big ")], "이미 Main 설비 이름입니다\\(BIG\\)"),
        # 편집기에 없는 형제(M-3)도 설비 마스터의 이름이다.
        ([("unit", "EQ-01", "m-3")], "이미 있는 설비명입니다\\(M-3\\)"),
        (
            [("group", "BIG", "EQ-02")],
            "Main 설비 BIG 의 새 이름 EQ-02는 쓸 수 없습니다 — 이미 있는 설비명입니다\\(EQ-02\\)",
        ),
        ([("group", "BIG", "m-1")], "이미 있는 설비명입니다\\(M-1\\)"),
        (
            [("unit", "EQ-01", "NEW-9"), ("unit", "EQ-02", "new-9")],
            "이번 적용에서 EQ-02 도 new-9로 바꿉니다",
        ),
        ([("unit", "GHOST", "X")], "이 편집기에 없는 호기"),
        ([("unit", "M-3", "X")], "이 편집기에 없는 호기"),
        ([("group", "NOPE", "X")], "이 편집기에 없는 Main 설비"),
        ([("unit", "EQ-01", "A"), ("unit", "EQ-01", "B")], "두 번 왔습니다"),
        ([("shelf", "EQ-01", "A")], "종류를 알 수 없습니다"),
    ],
)
def test_a_bad_rename_rejects_the_whole_apply(
    renames: list[tuple[str, str, str]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _parse(_rename(*renames), _bundle_master())


def test_a_group_name_may_not_take_another_group_name() -> None:
    master = _master(
        {"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0},
        {"설비명": "S-1", "Main 설비": "SMALL", "X좌표": 70.0, "Y좌표": 40.0},
    )
    with pytest.raises(ValueError, match="이미 Main 설비 이름입니다\\(SMALL\\)"):
        _parse(_rename(("group", "BIG", "small")), master)


def test_a_rename_may_not_take_the_name_of_a_unit_created_in_the_same_apply() -> None:
    payload = {
        "changes": [
            {
                "id": "NEW-1",
                "placed": False,
                "w": 8,
                "h": 5,
                "created": {"process": "Process-A", "existing": True},
            }
        ],
        **_rename(("unit", "EQ-01", "new-1")),
    }
    with pytest.raises(ValueError, match="새로 넣는 호기 이름입니다\\(NEW-1\\)"):
        _parse(payload, _master())


def test_names_freed_in_the_same_apply_may_be_taken() -> None:
    """바꾼 뒤의 상태로 본다 — 두 호기의 이름을 서로 바꿔도 겹치지 않는다."""
    apply = _parse(_rename(("unit", "EQ-01", "EQ-02"), ("unit", "EQ-02", "EQ-01")), _master())

    master, downtime = apply_name_changes(_master(), _downtime(), apply.renames)

    assert master["설비명"].tolist()[:2] == ["EQ-02", "EQ-01"]
    assert downtime["설비명"].tolist() == ["EQ-02"]


# ------------------------------------------------------------------ 반영


def test_a_unit_rename_keeps_the_place_and_takes_its_downtime_along() -> None:
    master = _master()
    apply = _parse(_rename(("unit", "EQ-01", "EQ-101")), master)

    renamed, downtime = apply_name_changes(master, _downtime(), apply.renames)
    row = renamed.set_index("설비명").loc["EQ-101"]

    assert "EQ-01" not in set(renamed["설비명"])
    assert (row["동"], row["층"], row["X좌표"], row["Y좌표"], row["Xsize"]) == (
        "C1",
        "1F",
        10.0,
        10.0,
        12.0,
    )
    assert downtime["설비명"].tolist() == ["EQ-101"]
    prepared = prepare_equipment_master(renamed, floor_canvases={FLOOR: CANVAS})
    prepare_downtime_for_prepared_equipment(downtime, prepared)
    # 원본은 그대로다.
    assert master["설비명"].tolist()[0] == "EQ-01"


def test_a_rename_and_a_move_in_one_apply_both_land() -> None:
    master = _master()
    apply = _parse(
        {
            "changes": [{"id": "EQ-01", "placed": True, "x": 40, "y": 20, "w": 12, "h": 7}],
            **_rename(("unit", "EQ-01", "EQ-101")),
        },
        master,
    )

    moved = apply_layout_edits(master, apply, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    renamed, _ = apply_name_changes(moved, _downtime(), apply.renames)
    row = renamed.set_index("설비명").loc["EQ-101"]

    assert (row["X좌표"], row["Y좌표"]) == (40.0, 20.0)


def test_a_group_rename_reaches_every_module_row_and_leaves_downtime_alone() -> None:
    master = _bundle_master()
    apply = _parse(_rename(("group", "BIG", "BIG-2")), master)

    renamed, downtime = apply_name_changes(master, _downtime(), apply.renames)
    parents = renamed.set_index("설비명")["Main 설비"]

    # 편집기에 없던 형제(M-3)까지 바뀐다 — 모듈 행은 Main 설비 하나로 한 설비다.
    assert parents.loc[["M-1", "M-2", "M-3"]].tolist() == ["BIG-2"] * 3
    assert pd.isna(parents.loc["EQ-01"])
    assert downtime.equals(_downtime())
    prepare_equipment_master(renamed, floor_canvases={FLOOR: CANVAS})


def test_a_self_named_single_row_group_follows_its_unit_name() -> None:
    master = _master({"설비명": "SOLO", "Main 설비": "SOLO", "X좌표": 70.0, "Y좌표": 40.0})
    apply = _parse(_rename(("unit", "SOLO", "SOLO-2")), master)

    renamed, _ = apply_name_changes(master, _downtime(), apply.renames)
    row = renamed.set_index("설비명").loc["SOLO-2"]

    assert row["Main 설비"] == "SOLO-2"
    prepare_equipment_master(renamed, floor_canvases={FLOOR: CANVAS})


# ------------------------------------------------------------------ 저장 안 한 이름 지도


def _apply(*renames: NameChange) -> EditorApply:
    return EditorApply(changes=(), created=(), canvas=None, marks=None, renames=renames)


def test_pending_renames_chain_back_to_the_saved_name_and_vanish_when_undone() -> None:
    saved = _bundle_master()
    first = compose_renames(
        PendingRenames(),
        _apply(NameChange("unit", "EQ-01", "A"), NameChange("group", "BIG", "G")),
        saved=saved,
    )
    second = compose_renames(first, _apply(NameChange("unit", "A", "B")), saved=saved)
    back = compose_renames(second, _apply(NameChange("unit", "B", "EQ-01")), saved=saved)

    assert first.units == {"A": "EQ-01"} and first.groups == {"G": "BIG"}
    assert second.units == {"B": "EQ-01"} and second.groups == {"G": "BIG"}
    assert back.units == {} and back.groups == {"G": "BIG"}


def test_an_unsaved_new_unit_is_not_remembered_as_a_rename() -> None:
    pending = compose_renames(
        PendingRenames(), _apply(NameChange("unit", "NEW-1", "NEW-2")), saved=_master()
    )

    assert not pending


def test_stale_pending_renames_are_ignored() -> None:
    """RawData 에서 그 사이 지우거나 되돌린 이름은 이름 바꿈으로 읽지 않는다."""
    saved = _master()
    buffer, _ = apply_name_changes(saved, _downtime(), [NameChange("unit", "EQ-01", "A")])
    pending = PendingRenames(units={"A": "EQ-01", "GONE": "EQ-02"})

    assert live_renames(pending, saved, buffer).units == {"A": "EQ-01"}
    assert live_renames(pending, saved, saved).units == {}


def test_a_rename_reads_as_a_rename_in_the_unsaved_lists() -> None:
    saved = _bundle_master()
    buffer, _ = apply_name_changes(
        saved,
        _downtime(),
        [NameChange("unit", "EQ-01", "EQ-101"), NameChange("group", "BIG", "BIG-2")],
    )
    buffer.loc[buffer["설비명"].eq("EQ-101"), ["X좌표", "Y좌표"]] = [40.0, 20.0]
    pending = PendingRenames(units={"EQ-101": "EQ-01"}, groups={"BIG-2": "BIG"})

    names = name_changes(saved, buffer, pending)
    changes = layout_changes(saved, buffer, pending)

    assert names.to_dict(orient="records") == [
        {"구분": "설비명", "이전 이름": "EQ-01", "새 이름": "EQ-101"},
        {"구분": "Main 설비(모듈 3행)", "이전 이름": "BIG", "새 이름": "BIG-2"},
    ]
    # 이름과 함께 옮긴 호기는 저장본의 옛 이름 행과 견준 배치 변경으로 선다(지금 이름으로).
    assert changes[["설비명", "변경"]].to_dict(orient="records") == [
        {"설비명": "EQ-101", "변경": "이동·크기"}
    ]
    assert other_change_count(saved, buffer, pending) == 0
    # 지도 없이 보면 「지운 호기 + 새 호기」와 Main 설비가 바뀐 모듈 행이 RawData 편집으로 세어진다.
    assert other_change_count(saved, buffer) == 5
    assert unsaved_unit_ids(saved, buffer, FLOOR, pending) == (set(), set())
    assert unsaved_unit_ids(saved, buffer, FLOOR)[0] == {"EQ-101"}


def test_the_saved_downtime_is_compared_under_the_new_names() -> None:
    saved = _master()
    buffer, downtime = apply_name_changes(saved, _downtime(), [NameChange("unit", "EQ-01", "A")])
    pending = PendingRenames(units={"A": "EQ-01"})

    expected = downtime_with_renames(_downtime(), pending, saved=saved, buffer=buffer)

    assert expected["설비명"].tolist() == downtime["설비명"].tolist() == ["A"]


def test_a_self_named_group_following_its_unit_is_not_another_edit() -> None:
    saved = _master({"설비명": "SOLO", "Main 설비": "SOLO", "X좌표": 70.0, "Y좌표": 40.0})
    buffer, _ = apply_name_changes(saved, _downtime(), [NameChange("unit", "SOLO", "SOLO-2")])

    assert other_change_count(saved, buffer, PendingRenames(units={"SOLO-2": "SOLO"})) == 0


def _downtime_two() -> pd.DataFrame:
    """EQ-01(고장)·EQ-02(공사) 비가동 일정 — 맞바꿈에서 두 호기의 일정이 서로 따라가는지 본다."""
    first = _downtime()
    return pd.concat(
        [first, first.assign(설비명=["EQ-02"], 비가동유형=["공사"])], ignore_index=True
    )


def _apply_in_turn(
    saved: pd.DataFrame, downtime: pd.DataFrame, *applies: tuple[NameChange, ...]
) -> tuple[pd.DataFrame, pd.DataFrame, PendingRenames]:
    """적용을 차례로 얹고 세션의 이름 지도를 잇는다(페이지와 같은 차례)."""
    master, schedule, pending = saved, downtime, PendingRenames()
    for renames in applies:
        master, schedule = apply_name_changes(master, schedule, renames)
        pending = compose_renames(pending, _apply(*renames), saved=saved)
    return master, schedule, pending


SWAP = (NameChange("unit", "EQ-01", "EQ-02"), NameChange("unit", "EQ-02", "EQ-01"))
SWAPPED = {"EQ-01": "EQ-02", "EQ-02": "EQ-01"}
CHAINED = {"EQ-X": "EQ-01", "EQ-01": "EQ-02"}


@pytest.mark.parametrize(
    ("applies", "expected"),
    [
        pytest.param((SWAP,), SWAPPED, id="swap-in-one-apply"),
        pytest.param(
            (
                (NameChange("unit", "EQ-01", "T"),),
                (NameChange("unit", "EQ-02", "EQ-01"),),
                (NameChange("unit", "T", "EQ-02"),),
            ),
            SWAPPED,
            id="swap-over-three-applies",
        ),
        pytest.param(
            ((NameChange("unit", "EQ-01", "EQ-X"), NameChange("unit", "EQ-02", "EQ-01")),),
            CHAINED,
            id="a-to-x-and-b-to-a-in-one-apply",
        ),
        pytest.param(
            ((NameChange("unit", "EQ-01", "EQ-X"),), (NameChange("unit", "EQ-02", "EQ-01"),)),
            CHAINED,
            id="a-to-x-then-b-to-a",
        ),
    ],
)
def test_swaps_and_chains_read_as_renames_in_the_unsaved_lists(
    applies: tuple[tuple[NameChange, ...], ...], expected: dict[str, str]
) -> None:
    """옛 이름이 편집본에 남아 있어도 같은 지도의 다른 항목이 그 이름을 이어받았으면 이름
    바꿈이다."""
    saved, downtime = _master(), _downtime_two()
    buffer, schedule, pending = _apply_in_turn(saved, downtime, *applies)

    names = name_changes(saved, buffer, pending)

    assert live_renames(pending, saved, buffer).units == expected
    assert dict(zip(names["새 이름"], names["이전 이름"], strict=True)) == expected
    # 자리는 그대로이고(저장본의 옛 이름 행과 견준다) RawData 의 다른 편집·새 호기도 아니다.
    assert layout_changes(saved, buffer, pending).empty
    assert other_change_count(saved, buffer, pending) == 0
    assert unsaved_unit_ids(saved, buffer, FLOOR, pending) == (set(), set())
    renamed_saved = downtime_with_renames(downtime, pending, saved=saved, buffer=buffer)
    assert not table_changed(renamed_saved, schedule)


def test_a_group_swap_reads_as_two_group_renames() -> None:
    saved = _master(
        {"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0},
        {"설비명": "S-1", "Main 설비": "SMALL", "X좌표": 70.0, "Y좌표": 40.0},
    )
    swap = (NameChange("group", "BIG", "SMALL"), NameChange("group", "SMALL", "BIG"))
    buffer, _, pending = _apply_in_turn(saved, _downtime(), swap)

    assert live_renames(pending, saved, buffer).groups == {"SMALL": "BIG", "BIG": "SMALL"}
    assert other_change_count(saved, buffer, pending) == 0


def test_a_rawdata_revert_or_a_new_row_on_the_old_name_still_drops_the_entry() -> None:
    saved = _master()
    buffer, _ = apply_name_changes(saved, _downtime(), [NameChange("unit", "EQ-01", "A")])
    pending = PendingRenames(units={"A": "EQ-01"})
    # RawData 에서 A 를 EQ-01 로 되돌렸다 — 지금 이름이 편집본에 없다.
    reverted = buffer.assign(설비명=buffer["설비명"].replace({"A": "EQ-01"}))
    # RawData 에서 옛 이름 EQ-01 로 새 행을 넣었다 — 옛 이름을 이어받은 항목이 지도에 없다.
    reused = pd.concat([buffer, buffer.iloc[[0]].assign(설비명="EQ-01")], ignore_index=True)

    assert live_renames(pending, saved, reverted).units == {}
    assert live_renames(pending, saved, reused).units == {}
    # 이어받은 항목이 죽으면 그것에 기대던 항목도 다시 본다 — A→X·B→A 뒤 RawData 에서 옛 이름 B 로
    # 새 행을 넣으면 A 항목(옛 이름 B 가 편집본에 있고 이어받은 항목 없음)이 죽고, 그러면 X 항목도
    # 옛 이름 A 를 이어받은 항목을 잃는다.
    chained, _, chain = _apply_in_turn(
        saved,
        _downtime(),
        (NameChange("unit", "EQ-01", "EQ-X"), NameChange("unit", "EQ-02", "EQ-01")),
    )
    with_new_b = pd.concat([chained, chained.iloc[[0]].assign(설비명="EQ-02")], ignore_index=True)
    assert live_renames(chain, saved, chained).units == CHAINED
    assert live_renames(chain, saved, with_new_b).units == {}


# ------------------------------------------------------------------ 편집본에 없어도 못 쓰는 이름


def _created(unit_id: str) -> dict[str, Any]:
    return {
        "id": unit_id,
        "placed": False,
        "w": 8,
        "h": 5,
        "created": {"process": "Process-A", "existing": True},
    }


def test_a_name_deleted_in_rawdata_and_not_saved_cannot_be_taken() -> None:
    """옛 EQ-02 를 지우고 다른 호기가 그 이름을 이으면 저장 뒤 두 설비의 이력이 섞인다."""
    saved = _master()
    buffer = saved.loc[saved["설비명"].ne("EQ-02")].reset_index(drop=True)
    reserved = reserved_names(saved, buffer, _downtime(), None)

    assert reserved.deleted == {"EQ-02"} and not reserved.orphan_downtime
    with pytest.raises(ValueError, match="저장본의 EQ-02를 RawData 에서 지우고 아직 저장하지"):
        _parse(_rename(("unit", "EQ-01", "eq-02")), buffer, reserved=reserved)
    with pytest.raises(ValueError, match="새 호기 이름 EQ-02는 쓸 수 없습니다"):
        _parse({"changes": [_created("EQ-02")]}, buffer, reserved=reserved)


def test_a_name_emptied_by_an_unsaved_rename_may_be_taken() -> None:
    saved = _master()
    buffer, schedule = apply_name_changes(saved, _downtime(), [NameChange("unit", "EQ-01", "EQ-X")])
    pending = PendingRenames(units={"EQ-X": "EQ-01"})
    reserved = reserved_names(saved, buffer, schedule, pending)

    assert not reserved.deleted and not reserved.orphan_downtime
    apply = _parse(_rename(("unit", "EQ-02", "EQ-01")), buffer, reserved=reserved)
    assert apply.unit_renames == {"EQ-02": "EQ-01"}


def test_a_name_held_by_orphan_downtime_rows_cannot_be_taken() -> None:
    """설비 마스터에 없는 설비명의 비가동 일정은 그 이름을 쓰는 호기에 말없이 붙는다."""
    saved = _master()
    downtime = pd.concat([_downtime(), _downtime().assign(설비명=["GHOST"])], ignore_index=True)
    reserved = reserved_names(saved, saved, downtime, None)

    assert reserved.orphan_downtime == {"GHOST"} and not reserved.deleted
    with pytest.raises(ValueError, match="설비 마스터에 없는 설비명 GHOST을\\(를\\) 가리키는"):
        _parse(_rename(("unit", "EQ-01", "ghost")), saved, reserved=reserved)
    with pytest.raises(ValueError, match="비가동 일정을 먼저 고치거나 지우세요"):
        _parse({"changes": [_created("GHOST")]}, saved, reserved=reserved)


def test_a_new_unit_name_is_compared_like_a_rename() -> None:
    """새 호기 이름도 대소문자·앞뒤 공백 무시로 겹침을 본다(같은 적용의 다른 새 호기 포함)."""
    with pytest.raises(ValueError, match="이미 있는 호기입니다: eq-01\\(EQ-01\\)"):
        _parse({"changes": [_created("eq-01")]}, _master())
    with pytest.raises(ValueError, match="이미 있는 호기입니다: n-1\\(N-1\\)"):
        _parse({"changes": [_created("N-1"), _created("n-1")]}, _master())
    with pytest.raises(ValueError, match="이미 Main 설비로 쓰는 이름입니다: big\\(BIG\\)"):
        _parse({"changes": [_created("big")]}, _bundle_master())


def test_typed_names_stay_with_the_unit_they_were_typed_for() -> None:
    """이름 칸의 글자는 칸에 들어갈 때 고른 대상의 것이다(2026-10-08 병합 전 리뷰).

    서랍 칩·팔레트는 누를 때 기본 동작을 막아 초점이 이름 칸에 남는다 — 고르는 것을 바꾸기 전에 적던
    글자를 그 대상에 확정하고(`commitTyping`), change 는 칸에 들어갈 때 묶은 대상에만 쓴다. JS 는
    AppTest 가 돌리지 못하므로 글자로 붙잡고 실제 동작은 브라우저로 본다."""
    js = (space_layout_editor._ASSETS / "editor.js").read_text(encoding="utf-8")
    set_selection = js[js.index("function setSelection(") :]
    ghost = js[js.index("function ghostDrag(") :]
    add_form = js[js.index("addForm.onsubmit") :]
    add_form = add_form[: add_form.index("newError.textContent")]

    assert set_selection.splitlines()[1].strip() == "commitTyping()"
    assert "commitTyping()" in ghost[: ghost.index("event.preventDefault()")]
    assert "S.items.get(S.unitLabelFor)" in js and "S.items.get(S.markLabelFor)" in js
    # 새 호기 폼도 지금 이름으로 겹침을 본다(편집기 열쇠는 옛 이름이다).
    assert "nameClash(id" in add_form and "S.items.has(id)" not in add_form


# ------------------------------------------------------------------ 페이지


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop(FAKE_APPLY_KEY, None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def _open_editor(tmp_path: Path, equipment: pd.DataFrame) -> tuple[AppTest, Path]:
    database = tmp_path / "space_rename.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), equipment, _downtime(), note="r1")
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.run()
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    return app, database


def test_a_rename_is_applied_to_the_draft_and_saved_as_a_new_revision(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, database = _open_editor(tmp_path, _equipment())
    epoch = editor_calls[-1]["epoch"]
    # RawData 에서 골라 둔 행(호기·비가동)과 방금 지운 행이 있는 세션.
    app.session_state[SELECTION_KEY] = {
        EQUIPMENT_TARGET: frozenset({("EQ-01",), ("EQ-02",)}),
        DOWNTIME_TARGET: frozenset({("EQ-01", "고장", "2026-08-10")}),
    }
    app.session_state[LAST_REMOVED_KEY] = (_baseline().iloc[:0], _equipment().iloc[:0], _downtime())
    # RawData 비가동 일정 표에서 고른 설비명 필터(이 화면에서는 그리지 않는다).
    downtime_filter = filter_widget_key(DOWNTIME_VIEW_PREFIX, "설비명")
    app.session_state[downtime_filter] = ["EQ-01"]

    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": epoch,
        "changes": [],
        "renames": [{"kind": "unit", "from": "EQ-01", "to": "EQ-101"}],
        "canvas": None,
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("이름 바꿈 1건도 넣었습니다" in item.value for item in app.success)
    assert any("이름 바꿈 1건" in item.value for item in app.markdown)
    # 이름만 바꾼 호기는 배치 변경도, RawData 의 다른 편집도 아니다.
    assert not any("호기 배치" in item.value for item in app.markdown)
    assert not any("다른 편집" in item.value for item in app.caption)
    # 비가동 일정의 설비명이 따라간 것도 RawData 의 비가동 일정 편집이 아니다.
    assert not any("표 편집도" in item.value for item in app.caption)
    assert app.session_state[PENDING_RENAMES_KEY] == {"units": {"EQ-101": "EQ-01"}, "groups": {}}
    assert app.session_state[SELECTION_KEY] == {
        EQUIPMENT_TARGET: frozenset({("EQ-101",), ("EQ-02",)}),
        DOWNTIME_TARGET: frozenset({("EQ-101", "고장", "2026-08-10")}),
    }
    assert LAST_REMOVED_KEY not in app.session_state
    # 편집기는 새 이름으로 다시 선다(자리는 그대로, 「신규」 표시 없음).
    item = next(item for item in editor_calls[-1]["items"] if item["id"] == "EQ-101")
    assert (item["x"], item["y"], item["isNew"]) == (10.0, 10.0, False)

    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("r2" in item.value for item in app.success)
    repository = DuckDBEquipmentRepository(database)
    revisions = repository.list_revisions()
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    assert set(latest.equipment["설비명"]) == {"EQ-101", "EQ-02"}
    assert latest.equipment.set_index("설비명").loc["EQ-101", "X좌표"] == 10.0
    assert latest.downtime["설비명"].tolist() == ["EQ-101"]
    # 지난 리비전은 옛 이름 그대로다(append-only 이력).
    first = repository.load_snapshot(min(revisions, key=lambda r: r.revision_no).revision_id)
    assert set(first.equipment["설비명"]) == {"EQ-01", "EQ-02"}
    assert first.downtime["설비명"].tolist() == ["EQ-01"]
    assert PENDING_RENAMES_KEY not in app.session_state
    # 저장한 이름은 저장본 이름이라 RawData 필터가 따라갈 지도는 저장 뒤에도 남는다(다음 RawData
    # 회차가 얹는다). 편집본과 함께 버리면 옛 이름이 선택지 밖이라 필터가 「전체」 로 돌아간다.
    assert app.session_state[FOLLOWED_FILTERS_KEY][downtime_filter] == {"EQ-01": "EQ-101"}
    assert app.session_state[downtime_filter] == ["EQ-01"]
    clear_equipment_repository()


def test_a_group_rename_is_saved_on_every_module_row(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, database = _open_editor(tmp_path, _bundle_master())
    # RawData 에서 방금 지운 모듈 행(M-3). 묶음 이름을 바꾼 뒤 되살리면 옛 Main 설비 BIG 으로 돌아와
    # 한 설비가 둘로 갈린다(검증은 통과한다) — 그래서 어느 이름 바꿈이든 되돌리기를 버린다.
    removed = _bundle_master().loc[lambda frame: frame["설비명"].eq("M-3")]
    app.session_state[LAST_REMOVED_KEY] = (_baseline().iloc[:0], removed, _downtime().iloc[:0])
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [],
        "renames": [{"kind": "group", "from": "BIG", "to": "BIG-2"}],
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert {item["group"] for item in editor_calls[-1]["items"] if item["id"].startswith("M-")} == {
        "BIG-2"
    }
    assert LAST_REMOVED_KEY not in app.session_state
    # 묶음 이름만 바꾸면 비가동 일정은 따라갈 것이 없다 — 알림도 그렇게 말한다.
    assert any(
        "이름 바꿈 1건도 넣었습니다." in item.value and "비가동" not in item.value
        for item in app.success
    )
    app.button(key="space_layout_save").click().run()

    repository = DuckDBEquipmentRepository(database)
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    parents = latest.equipment.set_index("설비명")["Main 설비"]
    assert parents.loc[["M-1", "M-2", "M-3"]].tolist() == ["BIG-2"] * 3
    clear_equipment_repository()


def test_a_colliding_rename_is_refused_and_leaves_the_draft(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    app, _ = _open_editor(tmp_path, _equipment())
    epoch = editor_calls[-1]["epoch"]
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": epoch,
        "renames": [{"kind": "unit", "from": "EQ-01", "to": "eq-02"}],
    }
    app.run()

    assert not app.exception
    assert any(
        "적용하지 못했습니다" in item.value and "이미 있는 설비명입니다(EQ-02)" in item.value
        for item in app.error
    )
    # 편집기는 그대로(같은 epoch — 브라우저의 편집이 남는다), 편집본도 그대로다.
    assert editor_calls[-1]["epoch"] == epoch
    assert not any("저장 안 한 배치 변경" in item.value for item in app.markdown)
    clear_equipment_repository()


def test_a_swap_shows_the_unsaved_box_and_saves_both_names_with_their_downtime(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """맞바꾼 두 이름은 둘 다 편집본에 있어도 이름 바꿈이다 — 상자·`배치 저장` 이 서야 한다."""
    app, database = _open_editor(tmp_path, _equipment())
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [],
        "renames": [
            {"kind": "unit", "from": "EQ-01", "to": "EQ-02"},
            {"kind": "unit", "from": "EQ-02", "to": "EQ-01"},
        ],
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("이름 바꿈 2건" in item.value for item in app.markdown)
    assert not any("호기 배치" in item.value for item in app.markdown)
    assert not any("다른 편집" in item.value or "표 편집도" in item.value for item in app.caption)
    items = {item["id"]: item for item in editor_calls[-1]["items"]}
    assert (items["EQ-02"]["x"], items["EQ-01"]["x"]) == (10.0, 30.0)
    assert not items["EQ-02"]["isNew"] and not items["EQ-01"]["isNew"]

    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    repository = DuckDBEquipmentRepository(database)
    latest = repository.load_snapshot(str(repository.latest_revision_id()))
    assert latest.equipment.set_index("설비명").loc[["EQ-02", "EQ-01"], "X좌표"].tolist() == [
        10.0,
        30.0,
    ]
    assert latest.downtime["설비명"].tolist() == ["EQ-02"]
    clear_equipment_repository()
