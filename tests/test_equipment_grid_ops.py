# Purpose: 설비 마스터 표 출납의 반영·차례·잠금·초안·이름 바꿈·지우기·되살리기·되돌리기를 본다.

"""`services/equipment_grid` 의 출납 쪽(개편 명세 4-3~4-5·4-11·5-3·6-4, 11장
「test_equipment_grid_ops」).

표본은 합성 fleet(`sample_equipment_master`)이다. 칸 값은 저장 정규화와 같은 함수로
다듬어지는지(계약 dtype 유지), 못 다듬은 글은 칸 초안으로만 남는지, 되돌리기가 LIFO 로 편집본을
그대로 되돌리는지를 본다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services import equipment_grid as eg
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.space_layout_edit import PendingRenames, buffer_matches_saved

ANCHOR = date(2026, 10, 1)
BASE = "tok#1"
CONTEXT = eg.GridContext(base=BASE, scenario_name="운영")


def _saved() -> eg.Frames:
    return (
        sample_equipment_baseline(),
        sample_equipment_master(anchor_date=ANCHOR),
        sample_downtime_schedule(anchor_date=ANCHOR),
    )


def _state(saved: eg.Frames | None = None, **changes: Any) -> eg.GridState:
    saved = saved or _saved()
    frames = (saved[0].copy(), saved[1].copy(), saved[2].copy())
    return eg.GridState(frames=frames, saved=saved, **changes)


def _id(state: eg.GridState, position: int) -> str:
    return eg.grid_index(state.frames[1], state.saved[1], state.renames.units).ids[position]


def _op(name: str, seq: int = 1, **fields: Any) -> dict[str, Any]:
    return {"seq": seq, "base": BASE, "op": name, **fields}


def _apply(
    state: eg.GridState, *ops: dict[str, Any], context: eg.GridContext = CONTEXT
) -> eg.GridApplied:
    return eg.apply_ops(state, list(ops), context)


def _value(state: eg.GridState, position: int, column: str) -> Any:
    return state.frames[1].iloc[position][column]


def _new_row(saved: eg.Frames, name: str) -> pd.DataFrame:
    """저장본 첫 줄을 본뜬 새 호기 한 줄(칸 형 그대로)."""
    row = saved[1].iloc[[0]].copy()
    row.loc[row.index, "설비명"] = name
    return row


def _with_new(state: eg.GridState, name: str, **changes: Any) -> eg.GridState:
    master = pd.concat([state.frames[1], _new_row(state.saved, name)], ignore_index=True)
    return eg.GridState(
        frames=(state.frames[0], master, state.frames[2]), saved=state.saved, **changes
    )


def _owner_with_downtime(saved: eg.Frames) -> int:
    owners = set(saved[2]["설비명"].astype(str))
    names = saved[1]["설비명"].astype(str).tolist()
    return next(k for k, name in enumerate(names) if name in owners)


# ------------------------------------------------------------------ 출납 고르기


def test_pending_ops_take_only_new_seqs_in_at_mount_seq_order() -> None:
    grid = {"mount": "m-a", "ops": [{"seq": 1, "at": 30}, {"seq": 2, "at": 10}]}
    side = {"mount": "m-b", "ops": [{"seq": 1, "at": 20}]}
    ops, applied = eg.pending_ops([grid, side], {})
    assert [(op["mount"], op["seq"]) for op in ops] == [("m-a", 2), ("m-b", 1), ("m-a", 1)]
    assert applied == {"m-a": 2, "m-b": 1}
    again, _ = eg.pending_ops([side, grid], applied)
    assert again == [], "같은 출납이 다시 와도 한 번이다"
    reversed_order, _ = eg.pending_ops([side, grid], {})
    assert reversed_order == ops, "어느 콜백이 먼저 불려도 같은 차례"


def test_pending_ops_ignore_malformed_outboxes_and_forget_old_mounts() -> None:
    ops, applied = eg.pending_ops(
        [None, "x", {"mount": 3, "ops": []}, {"mount": "m", "ops": [{"seq": "1"}, {"seq": 0}]}],
        {},
    )
    assert ops == [] and applied == {"m": 0}
    memory = {f"m{k}": k for k in range(eg.MOUNT_LIMIT)}
    _, applied = eg.pending_ops([{"mount": "new", "ops": [{"seq": 1}]}], memory)
    assert len(applied) == eg.MOUNT_LIMIT and "m0" not in applied and applied["new"] == 1


def test_a_later_at_wins_whichever_callback_runs_first() -> None:
    state = _state()
    row_id = _id(state, 0)
    grid = {"mount": "g", "ops": [_op("cell", 1, id=row_id, col="담당자", text="표", at=2)]}
    side = {"mount": "s", "ops": [_op("cell", 1, id=row_id, col="담당자", text="상세", at=1)]}
    for order in ([grid, side], [side, grid]):
        ops, _ = eg.pending_ops(order, {})
        result = _apply(state, *ops)
        assert _value(result.state, 0, "담당자") == "표"


# ------------------------------------------------------------------ 칸 고치기


def test_a_cell_is_coerced_by_the_save_rules_and_keeps_the_contract_dtype() -> None:
    state = _state()
    row_id = _id(state, 0)
    result = _apply(
        state,
        _op("cell", 1, id=row_id, col="반입일정", text="2026/11/3"),
        _op("cell", 2, id=row_id, col="환산비", text=""),
        _op("cell", 3, id=row_id, col="보관유무", text="y"),
        _op("cell", 4, id=row_id, col="Area Code", text="mi"),
    )
    frame = result.state.frames[1]
    assert frame["반입일정"].dtype == state.frames[1]["반입일정"].dtype
    assert frame.iloc[0]["반입일정"] == pd.Timestamp("2026-11-03")
    assert frame.iloc[0]["환산비"] == 1.0, "빈 환산비는 저장처럼 1"
    assert frame.iloc[0]["보관유무"] == "Y" and frame.iloc[0]["Area Code"] == "MI"
    assert result.changed and result.frames_changed == (False, True, False)
    assert list(frame.dtypes) == list(state.frames[1].dtypes)


def test_the_same_value_changes_nothing() -> None:
    state = _state()
    row_id = _id(state, 0)
    current = eg.cell_text(_value(state, 0, "담당자"))
    result = _apply(state, _op("cell", 1, id=row_id, col="담당자", text=f"  {current} "))
    assert not result.changed and result.state.frames is state.frames and not result.state.undo


@pytest.mark.parametrize(
    ("column", "text", "message"),
    [
        ("반입일정", "2026-13-40", "반입일정은 날짜 형식이어야 합니다"),
        ("환산비", "1,5", "환산비를 숫자로 읽을 수 없습니다"),
        ("동", "C9", "동은 C1~C5, 층은 1F~6F 범위여야 합니다"),
    ],
)
def test_an_unreadable_text_stays_a_draft_and_never_enters_the_buffer(
    column: str, text: str, message: str
) -> None:
    state = _state()
    row_id = _id(state, 0)
    before = _value(state, 0, column)
    result = _apply(state, _op("cell", 1, id=row_id, col=column, text=text))
    assert eg.cell_text(_value(result.state, 0, column)) == eg.cell_text(before)
    assert result.state.overlay == {eg.overlay_key(row_id, column): text}
    assert result.changed and result.frames_changed == (False, False, False)
    view = eg.build_grid_view(
        eg.GridSource(frames=result.state.frames, saved=state.saved, overlay=result.state.overlay),
        CONTEXT,
    )
    assert view.marks[row_id].errors[eg.COLUMN_INDEX[column]] == message
    fixed = _apply(result.state, _op("cell", 2, id=row_id, col=column, text=eg.cell_text(before)))
    assert fixed.state.overlay == {} and fixed.changed


def test_a_different_base_is_dropped_and_told() -> None:
    state = _state()
    stale = {**_op("cell", 1, id=_id(state, 0), col="담당자", text="X"), "base": "old#1"}
    result = _apply(state, stale)
    assert not result.changed and result.dropped == 1
    assert result.toast == eg.DROPPED_TOAST.format(count=1)


def test_locked_cells_are_refused_by_python_too() -> None:
    saved = _saved()
    master = saved[1].copy()
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    saved = (saved[0], master, saved[2])
    state = _state(saved)
    module, plain = _id(state, 0), _id(state, 5)
    result = _apply(state, _op("cell", 1, id=module, col="X좌표", text="99"))
    assert not result.changed and result.refused == 1
    context = eg.GridContext(base=BASE, stale_lock="낡음", layout_lock="가정")
    for column in ("반입일정", "동"):
        refused = _apply(
            state, _op("cell", 1, id=plain, col=column, text="2026-11-01"), context=context
        )
        assert not refused.changed and refused.refused == 1
    allowed = _apply(
        state, _op("cell", 1, id=plain, col="반입실적", text="2026-09-01"), context=context
    )
    assert allowed.changed, "공통 칸은 낡은 세션에서도 고친다"


# ------------------------------------------------------------------ 붙여넣기·한꺼번에


def test_paste_counts_changed_cells_and_skips_locked_ones() -> None:
    saved = _saved()
    master = saved[1].copy()
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    saved = (saved[0], master, saved[2])
    state = _state(saved)
    ids = [_id(state, k) for k in range(3)]
    keep = eg.cell_text(_value(state, 2, "Y좌표"))
    result = _apply(
        state,
        _op(
            "paste",
            1,
            ids=ids,
            cols=["X좌표", "Y좌표"],
            rows=[["5", "6"], ["7", None], ["9", keep]],
            cut=2,
            skipped=1,
        ),
    )
    assert _value(result.state, 2, "X좌표") == 9.0
    assert _value(result.state, 0, "X좌표") == _value(state, 0, "X좌표"), "모듈 칸은 건너뜀"
    assert result.toast == "붙여넣기 5줄 → 1칸 바뀜 · 표 끝을 넘은 2줄은 버림 · 넣지 못한 칸 4개"
    assert result.toast_undo


def test_set_and_shift_report_their_counts() -> None:
    state = _state()
    ids = [_id(state, k) for k in range(3)]
    result = _apply(state, _op("set", 1, ids=ids, col="담당자", text="담당B"))
    assert result.toast == "값 넣기 — 3칸 바뀜"
    assert set(result.state.frames[1].iloc[:3]["담당자"]) == {"담당B"}
    dated = [
        k
        for k in range(3)
        for column in ("반입일정", "Qual일정")
        if pd.notna(_value(state, k, column))
    ]
    shifted = _apply(state, _op("shift", 1, ids=ids, days="−3"))
    assert shifted.toast == f"날짜 밀기 — {len(dated)}칸 바뀜"
    first = _value(state, 0, "반입일정")
    assert _value(shifted.state, 0, "반입일정") == first - pd.Timedelta(days=3)
    stale = eg.GridContext(base=BASE, stale_lock="낡음")
    refused = _apply(state, _op("shift", 1, ids=ids, days=7), context=stale)
    assert not refused.changed and refused.toast == "날짜 밀기 — 0칸 바뀜"


# ------------------------------------------------------------------ 지우기·되살리기


def test_deleting_a_saved_unit_marks_it_and_takes_its_downtime() -> None:
    saved = _saved()
    state = _state(saved)
    position = _owner_with_downtime(saved)
    row_id = _id(state, position)
    name = saved[1].iloc[position]["설비명"]
    result = _apply(state, _op("delete", 1, ids=[row_id]))
    master, downtime = result.state.frames[1], result.state.frames[2]
    assert name not in set(master["설비명"]) and name not in set(downtime["설비명"])
    assert result.frames_changed == (False, True, True)
    index = eg.grid_index(master, saved[1], {})
    assert row_id in index.deleted
    assert result.toast == eg.DELETE_TOAST.format(count=1)


def test_a_stale_session_refuses_saved_unit_deletes_but_drops_new_ones() -> None:
    state = _state()
    state = _with_new(state, "NEW-1", loaded=("n:NEW-1", _id(state, 0)))
    context = eg.GridContext(base=BASE, delete_lock="낡아서 못 지움")
    result = _apply(state, _op("delete", 1, ids=[_id(state, 0), "n:NEW-1"]), context=context)
    assert len(result.state.frames[1]) == len(state.saved[1])
    assert result.refused == 1 and result.toast is not None and "낡아서 못 지움" in result.toast
    assert result.state.loaded == (_id(state, 0),), "새 호기는 목록에서도 빠진다"


def test_deleting_three_and_restoring_them_in_reverse_gives_the_saved_order_back() -> None:
    saved = _saved()
    state = _state(saved)
    owner = _owner_with_downtime(saved)
    picks = [_id(state, k) for k in (2, owner, 7)]
    for seq, row_id in enumerate(picks, 1):
        state = _apply(state, _op("delete", seq, ids=[row_id])).state
    for seq, row_id in enumerate(reversed(picks), 10):
        result = _apply(state, _op("restore", seq, ids=[row_id]))
        state = result.state
        assert result.toast == "1대를 되살렸습니다"
    assert buffer_matches_saved(saved, state.frames)


def test_restore_skips_a_name_that_came_back() -> None:
    saved = _saved()
    state = _state(saved)
    row_id = _id(state, 1)
    state = _apply(state, _op("delete", 1, ids=[row_id])).state
    again = pd.concat([state.frames[1], saved[1].iloc[[1]]], ignore_index=True)
    state = eg.GridState(frames=(state.frames[0], again, state.frames[2]), saved=saved)
    result = _apply(state, _op("restore", 2, ids=[row_id]))
    assert not result.changed and result.refused == 1


def test_restore_uses_the_renamed_group_name() -> None:
    saved = _saved()
    master = saved[1].copy()
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    saved = (saved[0], master, saved[2])
    state = _state(saved)
    row_id = _id(state, 1)
    state = _apply(state, _op("delete", 1, ids=[row_id])).state
    renamed = state.frames[1].copy()
    renamed.loc[renamed["Main 설비"].eq("GRP-1").fillna(False), "Main 설비"] = "GRP-9"
    state = eg.GridState(
        frames=(state.frames[0], renamed, state.frames[2]),
        saved=saved,
        renames=PendingRenames(groups={"GRP-9": "GRP-1"}),
    )
    result = _apply(state, _op("restore", 2, ids=[row_id]))
    assert set(result.state.frames[1].iloc[:2]["Main 설비"]) == {"GRP-9"}


# ------------------------------------------------------------------ 되돌리기(칸·호기)


def test_revert_a_cell_and_a_whole_unit_back_to_the_saved_values() -> None:
    saved = _saved()
    state = _state(saved)
    row_id = _id(state, 0)
    state = _apply(
        state,
        _op("cell", 1, id=row_id, col="담당자", text="X"),
        _op("cell", 2, id=row_id, col="메모1", text="Y"),
        _op("cell", 3, id=row_id, col="반입일정", text="bad"),
    ).state
    one = _apply(state, _op("revert", 4, id=row_id, col="담당자")).state
    assert eg.cell_text(_value(one, 0, "담당자")) == eg.cell_text(saved[1].iloc[0]["담당자"])
    assert _value(one, 0, "메모1") == "Y"
    whole = _apply(one, _op("revert", 5, id=row_id, col=None)).state
    assert buffer_matches_saved(saved, whole.frames) and whole.overlay == {}


def test_reverting_a_new_unit_removes_it_and_a_deleted_unit_comes_back() -> None:
    saved = _saved()
    state = _with_new(_state(saved), "NEW-1")
    gone = _id(state, 3)
    state = _apply(state, _op("delete", 1, ids=[gone])).state
    state = _apply(state, _op("revert", 2, id="n:NEW-1", col=None)).state
    state = _apply(state, _op("revert", 3, id=gone, col=None)).state
    assert buffer_matches_saved(saved, state.frames)


# ------------------------------------------------------------------ 이름 바꿈(같은 호기)


def test_renaming_a_saved_unit_keeps_its_id_and_moves_its_downtime() -> None:
    saved = _saved()
    state = _state(saved)
    position = _owner_with_downtime(saved)
    row_id = _id(state, position)
    old = saved[1].iloc[position]["설비명"]
    result = _apply(state, _op("cell", 1, id=row_id, col="설비명", text="  RENAMED-1 "))
    after = result.state
    assert _value(after, position, "설비명") == "RENAMED-1"
    assert after.renames.units == {"RENAMED-1": old}
    assert "RENAMED-1" in set(after.frames[2]["설비명"]) and old not in set(
        after.frames[2]["설비명"]
    )
    assert _id(after, position) == row_id and result.moved == {}
    assert result.renamed == {old: "RENAMED-1"}
    back = _apply(after, _op("cell", 2, id=row_id, col="설비명", text=old)).state
    assert back.renames.units == {} and buffer_matches_saved(saved, back.frames)


def test_a_single_row_group_follows_its_own_rename() -> None:
    saved = _saved()
    master = saved[1].copy()
    master.loc[0, "Main 설비"] = master.loc[0, "설비명"]
    saved = (saved[0], master, saved[2])
    state = _state(saved)
    result = _apply(state, _op("cell", 1, id=_id(state, 0), col="설비명", text="SOLO-2"))
    assert _value(result.state, 0, "Main 설비") == "SOLO-2"


@pytest.mark.parametrize("taken", ["exact", "case"])
def test_a_rename_onto_another_unit_stays_a_draft_with_the_space_message(taken: str) -> None:
    saved = _saved()
    state = _state(saved)
    other = saved[1].iloc[1]["설비명"]
    text = other if taken == "exact" else other.lower()
    row_id = _id(state, 0)
    result = _apply(state, _op("cell", 1, id=row_id, col="설비명", text=text))
    assert _value(result.state, 0, "설비명") == saved[1].iloc[0]["설비명"]
    assert result.state.overlay == {eg.overlay_key(row_id, "설비명"): text}
    view = eg.build_grid_view(
        eg.GridSource(frames=result.state.frames, saved=saved, overlay=result.state.overlay),
        CONTEXT,
    )
    message = view.marks[row_id].errors[eg.NAME_INDEX]
    assert "이미 있는 설비명입니다" in message


def test_renaming_a_new_unit_moves_its_id_draft_and_list_place() -> None:
    saved = _saved()
    state = _with_new(
        _state(saved),
        "NEW-1",
        overlay={eg.overlay_key("n:NEW-1", "반입일정"): "bad"},
        loaded=("n:NEW-1",),
    )
    result = _apply(state, _op("cell", 1, id="n:NEW-1", col="설비명", text="NEW-2"))
    assert result.moved == {"n:NEW-1": "n:NEW-2"}
    assert result.state.loaded == ("n:NEW-2",)
    assert result.state.overlay == {eg.overlay_key("n:NEW-2", "반입일정"): "bad"}
    assert result.state.renames.units == {}, "새 호기의 이름 고침은 값 고침이다"


# ------------------------------------------------------------------ 되돌리기(단계)


def test_undo_walks_back_a_mixed_sequence_exactly() -> None:
    saved = _saved()
    state = _state(saved)
    owner = _owner_with_downtime(saved)
    a, b, c = _id(state, 0), _id(state, owner), _id(state, 4)
    steps = [
        _op("cell", 1, id=c, col="설비명", text="RENAMED-C"),
        _op("cell", 2, id=a, col="담당자", text="X"),
        _op(
            "paste",
            3,
            ids=[a, c],
            cols=["메모1", "반입일정"],
            rows=[["m", "bad"], ["n", "2026-01-02"]],
        ),
        _op("delete", 4, ids=[b]),
        _op("set", 5, ids=[a, c], col="메모2", text="z"),
        _op("restore", 6, ids=[b]),
        _op("shift", 7, ids=[a], days=5),
    ]
    for op in steps:
        state = _apply(state, op).state
    for seq in range(len(state.undo)):
        state = _apply(state, _op("undo", 100 + seq)).state
    assert not state.undo
    assert buffer_matches_saved(saved, state.frames)
    assert state.overlay == {} and state.renames.units == {}


def test_a_rename_drops_row_steps_and_everything_before_them() -> None:
    state = _state()
    a, b = _id(state, 0), _id(state, 3)
    for op in (
        _op("cell", 1, id=a, col="담당자", text="X"),
        _op("delete", 2, ids=[b]),
        _op("cell", 3, id=a, col="메모1", text="Y"),
        _op("cell", 4, id=a, col="설비명", text="RENAMED-A"),
    ):
        state = _apply(state, op).state
    assert [step.label for step in state.undo] == ["메모1 고침", "설비명 고침"]


def test_undo_keeps_at_most_the_limit_and_a_whole_step_stands_alone() -> None:
    state = _state()
    row_id = _id(state, 0)
    for seq in range(eg.UNDO_LIMIT + 5):
        state = _apply(state, _op("cell", seq + 1, id=row_id, col="메모1", text=str(seq))).state
    assert len(state.undo) == eg.UNDO_LIMIT
    whole = eg.whole_step("붙여넣기로 넣음", state)
    assert eg.push_undo(state.undo, whole) == (whole,)
    restored = eg.apply_ops(
        eg.GridState(frames=state.frames, saved=state.saved, undo=(whole,)),
        [_op("undo", 1)],
        CONTEXT,
    )
    assert restored.state.frames[1].equals(state.frames[1])


def test_undo_steps_survive_the_session_round_trip() -> None:
    state = _state()
    row_id = _id(state, 0)
    state = _apply(state, _op("cell", 1, id=row_id, col="메모1", text="Y")).state
    state = _apply(state, _op("delete", 2, ids=[_id(state, 2)])).state
    plain = eg.undo_to_state(state.undo)
    assert all(isinstance(item, dict) for item in plain)
    assert eg.undo_from_state(plain)[1].kind == "rows"
    assert eg.undo_from_state(plain)[0].master == state.undo[0].master
    assert eg.undo_from_state("bad") == () and eg.undo_from_state(({"x": 1},)) == ()
