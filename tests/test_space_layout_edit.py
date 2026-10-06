# Purpose: Space 배치 편집기의 입력 선정·적용값 검증·편집본 반영·경고·변경 목록을 검사한다.

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest
from test_equipment_availability import _downtime, _equipment

from capa_simulation.services.equipment_availability import build_space_equipment_status
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.floor_layout_mark import prepare_floor_layout_marks
from capa_simulation.services.space_layout_edit import (
    NEW_UNIT_HISTORY,
    EditorApply,
    apply_layout_edits,
    editor_inputs,
    layout_changes,
    layout_warnings,
    new_unit_options,
    other_change_count,
    parse_editor_apply,
    table_changed,
    viewer_items,
)

FLOOR = ("C1", "1F")
OTHER = ("C2", "2F")
CANVAS = (100.0, 60.0)
AS_OF = date(2026, 9, 1)


def _master(*extra: dict[str, Any]) -> pd.DataFrame:
    """EQ-01·EQ-02(C1 1F 배치) 와 덧붙인 행. 덧붙인 행은 EQ-01 을 바탕으로 값만 바꾼다."""
    base = _equipment()
    records = base.to_dict(orient="records")
    records += [{**records[0], **values} for values in extra]
    return pd.DataFrame(records, columns=base.columns)


def _status(master: pd.DataFrame) -> pd.DataFrame:
    return build_space_equipment_status(master, _downtime(), as_of=AS_OF)


def _ids(items: tuple[dict[str, Any], ...], *, placed: bool) -> list[str]:
    return [item["id"] for item in items if item["placed"] is placed]


def _parse(payload: dict[str, Any], master: pd.DataFrame, **overrides: Any) -> EditorApply:
    ids = set(master["설비명"].astype(str))
    options: dict[str, Any] = {
        "editor_ids": ids,
        "master_ids": ids,
        "floor": FLOOR,
        "floors": [FLOOR, OTHER],
        "canvas": CANVAS,
        "unit_options": new_unit_options(master),
    }
    options.update(overrides)
    return parse_editor_apply(payload, **options)


def test_inputs_split_the_floor_into_drawing_and_tray() -> None:
    master = _master(
        {"설비명": "EQ-TRAY", "X좌표": None, "Y좌표": None},
        {"설비명": "EQ-FLOORLESS", "동": None, "층": None, "X좌표": None, "Y좌표": None},
        {
            "설비명": "EQ-N",
            "레이아웃표시": "N",
            "X좌표": 90.0,
            "Y좌표": 50.0,
            "Xsize": 5,
            "Ysize": 5,
        },
        {"설비명": "EQ-ELSEWHERE", "동": "C2", "층": "2F", "X좌표": None, "Y좌표": None},
        {"설비명": "EQ-GONE", "반출일정": "2026-08-20", "X좌표": 70.0},
    )

    inputs = editor_inputs(_status(master), floor=FLOOR)

    assert _ids(inputs.items, placed=True) == ["EQ-01", "EQ-02"]
    # 층 미정 호기는 어느 층 편집기에도 트레이로 뜬다. 다른 층 호기·N·반출 완료는 빠진다.
    assert sorted(_ids(inputs.items, placed=False)) == ["EQ-FLOORLESS", "EQ-TRAY"]
    assert inputs.unplaced_floorless == 1
    # 편집기에 없는 N·반출 완료 호기가 차지한 범위 밑으로는 영역을 줄이지 못한다.
    assert inputs.reserved_extent == (95.0, 55.0)
    assert inputs.default_size == (12.0, 7.0)


def test_a_module_group_standing_on_the_floor_keeps_its_coordless_siblings_off_the_tray() -> None:
    master = _master(
        {"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0},
        {"설비명": "M-2", "Main 설비": "BIG", "X좌표": None, "Y좌표": None},
    )

    inputs = editor_inputs(_status(master), floor=FLOOR)

    by_id = {item["id"]: item for item in inputs.items}
    assert by_id["M-1"]["group"] == "BIG"
    assert "M-2" not in by_id


def test_arrivals_from_another_floor_are_drawn_last() -> None:
    inputs = editor_inputs(_status(_master()), floor=FLOOR, arrived_ids={"EQ-01"})

    assert [item["id"] for item in inputs.items] == ["EQ-02", "EQ-01"]
    assert inputs.items[-1]["arrived"] is True


def test_apply_places_moves_unplaces_and_keeps_the_size() -> None:
    master = _master({"설비명": "EQ-TRAY", "X좌표": None, "Y좌표": None, "Xsize": 4, "Ysize": 3})
    apply = _parse(
        {
            "changes": [
                {"id": "EQ-01", "placed": True, "x": 40.04, "y": 20, "w": 12, "h": 7},
                {"id": "EQ-02", "placed": False, "w": 12, "h": 7},
                {"id": "EQ-TRAY", "placed": True, "x": 0, "y": 0, "w": 4, "h": 3},
            ]
        },
        master,
    )

    result = apply_layout_edits(master, apply, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    by_id = result.set_index("설비명")

    assert (by_id.loc["EQ-01", "X좌표"], by_id.loc["EQ-01", "Y좌표"]) == (40.0, 20.0)
    # 트레이로 빼면 X·Y 만 비우고 크기는 남긴다.
    assert pd.isna(by_id.loc["EQ-02", "X좌표"]) and by_id.loc["EQ-02", "Xsize"] == 12
    assert (by_id.loc["EQ-TRAY", "동"], by_id.loc["EQ-TRAY", "X좌표"]) == ("C1", 0.0)
    # 원본 편집본은 그대로다.
    assert master.loc[0, "X좌표"] == 10
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})


def test_a_unit_sent_to_a_smaller_floor_is_pushed_inside_its_canvas() -> None:
    master = _master()
    apply = _parse(
        {
            "changes": [
                {
                    "id": "EQ-01",
                    "placed": True,
                    "x": 85,
                    "y": 50,
                    "w": 12,
                    "h": 7,
                    "moveTo": "C2 2F",
                }
            ]
        },
        master,
    )

    result = apply_layout_edits(
        master, apply, floor=FLOOR, canvases={OTHER: (60.0, 40.0)}, default_canvas=CANVAS
    )
    row = result.set_index("설비명").loc["EQ-01"]

    assert (row["동"], row["층"], row["X좌표"], row["Y좌표"]) == ("C2", "2F", 48.0, 33.0)


def test_a_unit_bigger_than_the_target_floor_lands_in_its_tray() -> None:
    master = _master()
    apply = _parse(
        {
            "changes": [
                {"id": "EQ-01", "placed": True, "x": 0, "y": 0, "w": 12, "h": 7, "moveTo": "C2 2F"}
            ]
        },
        master,
    )

    result = apply_layout_edits(
        master, apply, floor=FLOOR, canvases={OTHER: (10.0, 10.0)}, default_canvas=CANVAS
    )
    row = result.set_index("설비명").loc["EQ-01"]

    assert row["동"] == "C2" and pd.isna(row["X좌표"]) and row["Xsize"] == 12


def test_moving_one_module_moves_the_whole_group_to_the_floor() -> None:
    master = _master(
        {"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0},
        {"설비명": "M-2", "Main 설비": "BIG", "X좌표": None, "Y좌표": None},
    )
    apply = _parse(
        {
            "changes": [
                {"id": "M-1", "placed": True, "x": 5, "y": 5, "w": 12, "h": 7, "moveTo": "C2 2F"}
            ]
        },
        master,
    )

    result = apply_layout_edits(master, apply, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    floors = result.set_index("설비명").loc[["M-1", "M-2"], ["동", "층"]]

    # 모듈 행은 동·층이 같아야 저장된다. 편집기에 없던 형제도 같이 옮긴다.
    assert floors.drop_duplicates().values.tolist() == [["C2", "2F"]]
    prepare_equipment_master(result)


def test_a_created_unit_fills_only_what_the_form_asked() -> None:
    master = _master()
    apply = _parse(
        {
            "changes": [
                {
                    "id": "NEW-1",
                    "placed": True,
                    "x": 60,
                    "y": 40,
                    "w": 8,
                    "h": 5,
                    "created": {
                        "process": "Process-A",
                        "use": "양산",
                        "arrival": "2026-10-01",
                        "qual": "2026-10-10",
                        "confirm": "계획",
                    },
                }
            ]
        },
        master,
    )

    result = apply_layout_edits(master, apply, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    row = result.set_index("설비명").loc["NEW-1"]

    assert (row["공정대분류"], row["투자구분"], row["확정상태"]) == ("B/N", "양산", "계획")
    assert row["호기이력"] == NEW_UNIT_HISTORY and pd.isna(row["담당자"])
    assert (row["동"], row["X좌표"], row["Xsize"]) == ("C1", 60.0, 8.0)
    prepare_equipment_master(result, floor_canvases={FLOOR: CANVAS})
    assert layout_changes(master, result)["변경"].tolist() == ["새 호기"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "NOPE", "placed": True, "x": 0, "y": 0, "w": 1, "h": 1}, "없는 호기"),
        ({"id": "EQ-01", "placed": True, "x": 95, "y": 0, "w": 12, "h": 7}, "벗어났습니다"),
        ({"id": "EQ-01", "placed": True, "x": -1, "y": 0, "w": 12, "h": 7}, "0 이상"),
        ({"id": "EQ-01", "placed": True, "x": 0, "y": 0, "w": 0, "h": 7}, "0 보다 큰"),
        ({"id": "EQ-01", "placed": True, "x": "a", "y": 0, "w": 1, "h": 1}, "읽지 못했습니다"),
        ({"id": "EQ-01", "placed": False, "w": 3}, "둘 다"),
        (
            {"id": "EQ-01", "placed": True, "x": 0, "y": 0, "w": 1, "h": 1, "moveTo": "C9 9F"},
            "보낼 층",
        ),
        (
            {"id": "EQ-02", "placed": False, "w": 1, "h": 1, "created": {"process": "Process-A"}},
            "이미 있는 호기",
        ),
        (
            {"id": "NEW", "placed": False, "w": 1, "h": 1, "created": {"process": "Process-A"}},
            "반입일정과 Qual일정",
        ),
        (
            {"id": "NEW", "placed": False, "w": 1, "h": 1, "created": {"process": "X"}},
            "공정소분류",
        ),
    ],
)
def test_one_bad_change_rejects_the_whole_apply(change: dict[str, Any], message: str) -> None:
    good = {"id": "EQ-02", "placed": True, "x": 0, "y": 0, "w": 12, "h": 7}
    changes = [change] if change["id"] == "EQ-02" else [good, change]
    with pytest.raises(ValueError, match=message):
        _parse({"changes": changes}, _master())


def test_the_bounds_follow_the_canvas_sent_in_the_same_apply() -> None:
    apply = _parse(
        {
            "canvas": {"width": 130, "height": 60},
            "changes": [{"id": "EQ-01", "placed": True, "x": 110, "y": 0, "w": 12, "h": 7}],
            "marks": [{"id": "D1", "kind": "door", "x": 120, "y": 0, "w": 5, "h": 2}],
        },
        _master(),
    )

    assert apply.canvas == (130.0, 60.0)
    assert apply.marks is not None and apply.marks[0].mark_id == "D1"


def test_an_unknown_mark_rejects_instead_of_vanishing() -> None:
    with pytest.raises(ValueError, match="종류를 알 수 없습니다"):
        _parse(
            {"marks": [{"id": "Q", "kind": "window", "x": 0, "y": 0, "w": 1, "h": 1}]}, _master()
        )


def test_warnings_name_overlaps_and_covered_marks_but_skip_exited_units() -> None:
    master = _master(
        {"설비명": "EQ-OVER", "X좌표": 15.0, "Y좌표": 12.0},
        {"설비명": "EQ-GONE", "반출일정": "2026-08-20", "X좌표": 12.0},
    )
    marks = prepare_floor_layout_marks(
        [{"id": "D1", "kind": "door", "x": 33, "y": 12, "w": 3, "h": 2}], CANVAS
    )

    warnings = layout_warnings(_status(master), {FLOOR: marks})

    assert len(warnings) == 2
    assert "EQ-01 ↔ EQ-OVER (C1 1F)" in warnings[0] and "EQ-GONE" not in warnings[0]
    assert "EQ-02 → 문 (C1 1F)" in warnings[1]


def test_changes_list_layout_edits_and_count_the_rest_apart() -> None:
    saved = _master()
    buffer = saved.copy()
    buffer.loc[0, ["X좌표", "Y좌표"]] = [None, None]
    buffer.loc[1, "동"] = "C2"
    buffer.loc[1, "층"] = "2F"
    buffer.loc[1, "담당자"] = "담당B"

    changes = layout_changes(saved, buffer)

    assert changes["변경"].tolist() == ["트레이로 빼기(크기 유지)", "층 이동"]
    assert changes.loc[0, "새"] == "C1 1F · 미배치 12×7"
    assert other_change_count(saved, buffer) == 1
    assert other_change_count(saved, saved.iloc[[0]]) == 1


def test_table_changed_ignores_value_types_but_sees_edits_and_row_counts() -> None:
    saved = pd.DataFrame({"공정": ["DA", "WB"], "기존보유대수": [3, 4]})

    assert not table_changed(saved, saved.astype({"기존보유대수": "float64"}))
    edited = saved.copy()
    edited.loc[1, "기존보유대수"] = 5
    assert table_changed(saved, edited)
    assert table_changed(saved, saved.iloc[[0]])
    assert table_changed(saved, saved.rename(columns={"공정": "공정명"}))


def test_a_created_unit_does_not_make_every_other_row_look_edited() -> None:
    """새 호기의 빈 날짜 칸이 NaT 라도 다른 호기는 「RawData 의 다른 편집」이 아니다."""
    master = prepare_equipment_master(_master())
    apply = _parse(
        {
            "changes": [
                {
                    "id": "NEW-1",
                    "placed": False,
                    "w": 8,
                    "h": 5,
                    "created": {"process": "Process-A", "existing": True},
                }
            ]
        },
        master,
    )

    result = apply_layout_edits(master, apply, floor=FLOOR, canvases={}, default_canvas=CANVAS)

    assert other_change_count(master, result) == 0
    assert result["반입일정"].dtype == master["반입일정"].dtype


def test_hidden_siblings_leave_their_old_coordinates_behind_when_the_group_moves() -> None:
    """편집기에 없던 형제(반출 완료)가 옛 층 좌표를 지닌 채 따라가면 새 층에서 거부된다."""
    master = _master(
        {"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0},
        {
            "설비명": "M-2",
            "Main 설비": "BIG",
            "X좌표": 80.0,
            "Y좌표": 50.0,
            "반출일정": "2026-08-20",
        },
    )
    apply = _parse(
        {
            "changes": [
                {"id": "M-1", "placed": True, "x": 5, "y": 5, "w": 12, "h": 7, "moveTo": "C2 2F"}
            ]
        },
        master,
    )

    result = apply_layout_edits(
        master, apply, floor=FLOOR, canvases={OTHER: (40.0, 30.0)}, default_canvas=CANVAS
    )
    sibling = result.set_index("설비명").loc["M-2"]

    assert (sibling["동"], sibling["층"]) == ("C2", "2F")
    assert pd.isna(sibling["X좌표"]) and sibling["Xsize"] == 12
    prepare_equipment_master(result, floor_canvases={OTHER: (40.0, 30.0)})


def test_units_placed_edge_to_edge_are_not_an_overlap() -> None:
    master = _master(
        {"설비명": "EQ-A", "X좌표": 8.1, "Y좌표": 40.0, "Xsize": 1.2, "Ysize": 1.0},
        {"설비명": "EQ-B", "X좌표": 9.3, "Y좌표": 40.0, "Xsize": 1.0, "Ysize": 1.0},
    )

    assert layout_warnings(_status(master), {}) == []


def test_a_floorless_unit_given_a_floor_is_listed_as_such() -> None:
    saved = _master({"설비명": "EQ-F", "동": None, "층": None, "X좌표": None, "Y좌표": None})
    buffer = saved.copy()
    buffer.loc[buffer["설비명"].eq("EQ-F"), ["동", "층"]] = ["C2", "2F"]

    assert layout_changes(saved, buffer)["변경"].tolist() == ["층 지정(미배치)"]


@pytest.mark.parametrize(
    ("unit_id", "message"),
    [("BIG", "Main 설비로 쓰는 이름"), ("APW\xa0101", "특수 공백")],
)
def test_a_new_unit_name_is_refused_with_its_real_reason(unit_id: str, message: str) -> None:
    master = _master({"설비명": "M-1", "Main 설비": "BIG"})
    with pytest.raises(ValueError, match=message):
        _parse(
            {
                "changes": [
                    {
                        "id": unit_id,
                        "placed": False,
                        "w": 1,
                        "h": 1,
                        "created": {"process": "Process-A", "existing": True},
                    }
                ]
            },
            master,
        )
    assert "BIG" in new_unit_options(master)["existingIds"]


def test_the_viewer_gets_saved_units_with_process_and_downtime_detail() -> None:
    master = _master({"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0})
    status = _status(master)
    located = status.loc[status["동"].eq("C1") & status["X좌표"].notna()]

    items = {item["id"]: item for item in viewer_items(located)}

    assert set(items) == {"EQ-01", "EQ-02", "M-1"}
    assert items["M-1"]["group"] == "BIG" and items["EQ-01"]["group"] is None
    assert items["EQ-01"]["detail"].startswith("Process-A")
    assert (items["EQ-02"]["x"], items["EQ-02"]["w"]) == (30.0, 12.0)
    assert all(item["placed"] for item in items.values())
