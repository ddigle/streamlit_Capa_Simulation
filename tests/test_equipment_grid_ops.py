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
from capa_simulation.services.equipment_contract import SCENARIO_LAYOUT_COLUMNS
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.space_layout_edit import PendingRenames, buffer_matches_saved

ANCHOR = date(2026, 10, 1)
BASE = "tok#1"
CONTEXT = eg.GridContext(base=BASE, scenario_name="운영")
# 배치 편집이 잠긴 가정 세션(설비 시나리오 2단계 S3 — `space_edit_mode(...).layout == "locked"`)과
# 잠기지 않은 가정 세션(`"overlay"` — 그 시나리오의 배치 차이를 고친다).
LOCKED = eg.GridContext(
    base=BASE, scenario_name="가정", official=False, layout_lock="배치 편집 잠금"
)
OVERLAY = eg.GridContext(base=BASE, scenario_name="가정", official=False)
STALE = eg.GridContext(base=BASE, stale_lock="낡음", delete_lock="낡음 — 지우기 잠금")
PLACE = ("동", "층", "X좌표", "Y좌표")


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


def _unplaced(state: eg.GridState, name: str, **changes: Any) -> eg.GridState:
    """자리 없는 새 호기(묶음 밖) 한 줄을 끝에 더한 상태(가정 설비 시나리오 붙여넣기가 넣는 꼴)."""
    state = _with_new(state, name, **changes)
    master = state.frames[1]
    for column in (*PLACE, "Main 설비"):
        master.loc[master.index[-1], column] = None
    return state


def _grouped(saved: eg.Frames) -> eg.Frames:
    """앞 두 호기를 모듈 묶음 GRP-1(같은 공정, C1 1F)로 둔 저장본."""
    master = saved[1].copy()
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    return (saved[0], master, saved[2])


def _place_texts(frame: pd.DataFrame) -> list[list[str]]:
    return [[eg.cell_text(value) for value in row] for row in frame[list(SCENARIO)].values]


SCENARIO = ("동", "층", "X좌표", "Y좌표", "Xsize", "Ysize", "레이아웃표시")


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


def test_the_dropped_toast_does_not_blame_another_user() -> None:
    """base 는 내 저장·모두 버리기·시나리오 불러오기 때도 바뀐다 — 남 탓으로 적지 않는다."""
    state = _state()
    op = {**_op("cell", 1, id=_id(state, 0), col="담당자", text="X"), "base": "tok#0"}
    result = _apply(state, op)
    assert result.toast == eg.DROPPED_TOAST.format(count=1)
    assert "다른 사용자의 저장으로" not in result.toast and "리비전 저장" in result.toast


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


# ------------------------------------------------------------------ 배치 편집이 잠긴 회차(S3)


def test_a_locked_layout_keeps_a_new_units_place_empty() -> None:
    """배치 편집이 잠긴 회차 — 새 호기는 자리 없이. 동·층·X좌표·Y좌표는 어느 길(칸·붙여넣기·값
    넣기)로도 막는다."""
    saved = _saved()
    state = _unplaced(_state(saved), "NEWX-01")
    new = "n:NEWX-01"
    texts = {"동": "C2", "층": "3F", "X좌표": "10", "Y좌표": "20"}
    cells = [_op("cell", k + 1, id=new, col=c, text=t) for k, (c, t) in enumerate(texts.items())]
    result = _apply(state, *cells, context=LOCKED)
    assert result.refused == 4 and not result.changed
    pasted = _apply(
        state,
        _op("paste", 1, ids=[new], cols=list(texts), rows=[list(texts.values())]),
        _op("set", 2, ids=[new], col="동", text="C2"),
        context=LOCKED,
    )
    assert not pasted.changed and pasted.refused == 1
    row = pasted.state.frames[1].iloc[-1]
    assert [eg.cell_text(row[c]) for c in PLACE] == ["", "", "", ""]
    sized = _apply(state, _op("cell", 1, id=new, col="Xsize", text="9"), context=LOCKED)
    assert sized.changed and sized.state.frames[1].iloc[-1]["Xsize"] == 9.0, "크기는 받는다"
    saved_row = _id(state, 2)
    blocked = _apply(state, _op("cell", 1, id=saved_row, col="Xsize", text="9"), context=LOCKED)
    assert blocked.refused == 1, "있던 호기는 배치 일곱 칸 모두"


def test_joining_a_group_in_a_locked_layout_takes_the_groups_spot() -> None:
    """배치 편집이 잠긴 회차에 새 호기·동·층 미정 호기가 있는 묶음에 들면 그 묶음의 동·층(X·Y 비움)
    — 설비 마스터 탭 제출과 같은 판정(`layout_edits(...).apply`)이고, 되돌리면 함께 돌아간다."""
    from capa_simulation.components.equipment_data_workspace import layout_edits

    saved = _grouped(_saved())
    undecided = 5
    master = saved[1].copy()
    for column in PLACE:
        master.loc[undecided, column] = None
    saved = (saved[0], master, saved[2])
    state = _unplaced(_state(saved), "NEWX-01")
    joiner = _id(state, undecided)
    ops = (
        _op("cell", 1, id="n:NEWX-01", col="Main 설비", text="GRP-1"),
        _op("cell", 2, id=joiner, col="Main 설비", text="GRP-1"),
    )
    result = _apply(state, *ops, context=LOCKED)
    frame = result.state.frames[1]
    group_spot = [eg.cell_text(saved[1].iloc[0][c]) for c in ("동", "층")]
    for position in (undecided, len(frame) - 1):
        assert [eg.cell_text(frame.iloc[position][c]) for c in PLACE] == [*group_spot, "", ""]
    assert result.toast is not None and result.toast.startswith("배치 편집이 잠겨 있어 1대의 자리")
    assert result.toast_step == eg.undo_top(result.state.undo)
    assert list(frame.dtypes) == list(state.frames[1].dtypes)
    edited = state.frames[1].copy()
    edited.loc[edited.index[-1], "Main 설비"] = "GRP-1"
    edited.loc[undecided, "Main 설비"] = "GRP-1"
    expected = layout_edits(edited, saved[1], {}).apply(edited, saved[1])
    assert _place_texts(frame) == _place_texts(expected), "탭 제출과 같은 판정"
    for context in (CONTEXT, OVERLAY):
        opened = _apply(state, *ops, context=context)
        assert eg.cell_text(opened.state.frames[1].iloc[-1]["동"]) == "", (
            "잠기지 않은 회차(공식·가정)는 맞추지 않는다"
        )
    back = result.state
    for seq in (3, 4):
        back = _apply(back, _op("undo", seq), context=LOCKED).state
    assert back.frames[1].equals(state.frames[1])


def test_an_overlay_session_edits_the_layout_of_saved_and_new_units() -> None:
    """가정 설비 시나리오도 배치 편집이 잠기지 않은 회차(`"overlay"`)면 있던 호기의 배치 칸과 새
    호기의 자리를 고친다(설비 시나리오 2단계 S3 — 그 시나리오의 배치 차이로 저장된다)."""
    saved = _saved()
    state = _unplaced(_state(saved), "NEWX-01")
    saved_row = _id(state, 2)
    shown = eg.cell_text(state.frames[1].iloc[2]["레이아웃표시"])
    flipped = "N" if shown == "Y" else "Y"
    result = _apply(
        state,
        _op("cell", 1, id="n:NEWX-01", col="X좌표", text="10"),
        _op("cell", 2, id=saved_row, col="레이아웃표시", text=flipped),
        context=OVERLAY,
    )
    assert result.changed and result.refused == 0
    frame = result.state.frames[1]
    assert frame.iloc[-1]["X좌표"] == 10.0
    assert eg.cell_text(frame.iloc[2]["레이아웃표시"]) == flipped
    assert result.toast is None or "자리를 맞췄습니다" not in result.toast


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


def test_set_counts_only_changed_cells_and_refuses_locked_ones() -> None:
    """값 넣기 — 같은 값은 바뀐 칸이 아니고, 잠긴 칸(모듈 좌표)은 파이썬도 넣지 않고 센다."""
    saved = _grouped(_saved())
    state = _state(saved)
    module, plain, same = _id(state, 0), _id(state, 3), _id(state, 4)
    value = eg.cell_text(_value(state, 4, "X좌표"))
    result = _apply(state, _op("set", 1, ids=[module, plain, same], col="X좌표", text=value))
    assert result.refused == 1, "모듈 묶음 좌표"
    assert result.toast == "값 넣기 — 1칸 바뀜" and result.toast_undo
    assert _value(result.state, 0, "X좌표") == _value(state, 0, "X좌표")
    assert eg.cell_text(_value(result.state, 3, "X좌표")) == value
    none = _apply(state, _op("set", 1, ids=[same], col="X좌표", text=value))
    assert not none.changed and none.toast == "값 넣기 — 0칸 바뀜" and not none.toast_undo


# ------------------------------------------------------------------ 토스트 되돌리기


def test_a_toast_undo_reverts_its_own_step_or_nothing() -> None:
    """토스트 「되돌리기」 는 그 토스트의 단계를 가리킨다 — 그 뒤 칸 고침이 쌓였으면(같은 출납 안의
    경합도) 다른 단계를 되돌리지 않고 알린다."""
    state = _state()
    ids = [_id(state, k) for k in range(3)]
    put = _apply(state, _op("set", 1, ids=ids, col="담당자", text="담당B"))
    step = put.toast_step
    assert step is not None and step == eg.undo_top(put.state.undo)
    edited = _apply(put.state, _op("cell", 2, id=ids[0], col="메모1", text="m"))
    assert edited.toast is None and eg.undo_top(edited.state.undo) != step
    stale = _apply(edited.state, _op("undo", 3, step=step))
    assert stale.refused == 1 and stale.toast == eg.UNDO_STALE_TOAST and not stale.changed
    assert _value(stale.state, 0, "메모1") == "m"
    assert set(stale.state.frames[1].iloc[:3]["담당자"]) == {"담당B"}
    raced = _apply(
        put.state,
        _op("cell", 2, id=ids[0], col="메모1", text="m"),
        _op("undo", 3, step=step),
    )
    assert raced.refused == 1 and _value(raced.state, 0, "메모1") == "m"
    undone = _apply(put.state, _op("undo", 2, step=step))
    assert undone.state.frames[1].equals(state.frames[1]) and not undone.state.undo
    assert undone.toast == "되돌림: 값 넣기" and undone.toast_step is None
    plain = _apply(edited.state, _op("undo", 3))
    assert eg.cell_text(_value(plain.state, 0, "메모1")) == eg.cell_text(
        _value(state, 0, "메모1")
    ), "표지 없으면 맨 위"
    assert _apply(state, _op("undo", 1)).toast == eg.UNDO_EMPTY_TOAST


def test_step_tokens_are_the_op_mount_and_seq() -> None:
    state = _state()
    ops, _ = eg.pending_ops(
        [{"mount": "m-g", "ops": [_op("cell", 7, id=_id(state, 0), col="메모1", text="x")]}], {}
    )
    result = _apply(state, *ops)
    assert eg.undo_top(result.state.undo) == "m-g#7"
    assert eg.undo_from_state(eg.undo_to_state(result.state.undo))[0].token == "m-g#7"


# ------------------------------------------------------------------ 칸·호기 되돌리기


def test_a_stale_session_can_revert_scenario_cells_back_to_the_saved_values() -> None:
    """낡은 세션은 시나리오 칸 저장이 거부된다 — 저장본 값으로 돌리는 칸·호기 되돌리기는 잠그지
    않는다(토스트로 알린다). 고치기는 그대로 막는다."""
    saved = _saved()
    state = _state(saved)
    row_id = _id(state, 0)
    moved = _apply(
        state,
        _op("cell", 1, id=row_id, col="반입일정", text="2027-01-05"),
        _op("cell", 2, id=row_id, col="담당자", text="X"),
    ).state
    cell = _apply(moved, _op("revert", 3, id=row_id, col="반입일정"), context=STALE)
    assert cell.changed and cell.refused == 0
    assert _value(cell.state, 0, "반입일정") == saved[1].iloc[0]["반입일정"]
    assert cell.toast is not None and cell.toast.startswith("저장본 값으로 되돌림")
    assert cell.toast_step == eg.undo_top(cell.state.undo)
    unit = _apply(moved, _op("revert", 3, id=row_id, col=None), context=STALE)
    assert buffer_matches_saved(saved, unit.state.frames)
    again = _apply(cell.state, _op("cell", 4, id=row_id, col="반입일정", text="2027-02-01"))
    refused = _apply(cell.state, _op("cell", 4, id=row_id, col="반입일정", text="x"), context=STALE)
    assert again.changed and refused.refused == 1


def test_a_module_coordinate_is_kept_and_told_when_a_unit_is_reverted() -> None:
    saved = _grouped(_saved())
    master = saved[1].copy()
    master.loc[0, "X좌표"] = 99.0
    master.loc[0, "담당자"] = "X"
    state = eg.GridState(frames=(saved[0], master, saved[2]), saved=saved)
    result = _apply(state, _op("revert", 1, id=_id(state, 0), col=None))
    assert _value(result.state, 0, "X좌표") == 99.0 and _value(result.state, 0, "담당자") != "X"
    assert result.toast is not None and eg.MODULE_LOCK_REASON in result.toast


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


def test_undoing_a_delete_puts_the_new_unit_back_without_a_list_snapshot() -> None:
    """불러온 목록은 화면 조작으로도 바뀐다 — 되돌리기가 옛 목록 사진으로 덮어 그 뒤 불러온 호기를
    빼거나 뺀 호기를 다시 세우지 않는다."""
    saved = _saved()
    names = ["s:" + str(name) for name in saved[1]["설비명"].iloc[:4]]
    state = _with_new(_state(saved), "NEW-1", loaded=("n:NEW-1", names[0], names[1]))
    deleted = _apply(state, _op("delete", 1, ids=["n:NEW-1"]))
    assert deleted.state.loaded == (names[0], names[1])
    later = eg.GridState(
        frames=deleted.state.frames,
        saved=saved,
        undo=deleted.state.undo,
        loaded=(names[2], names[3], names[0]),
    )
    undone = _apply(later, _op("undo", 2))
    assert undone.state.loaded == ("n:NEW-1", names[2], names[3], names[0])
    assert undone.state.frames[1].equals(state.frames[1])


def test_a_saved_unit_named_with_a_tilde_comes_back_with_its_downtime() -> None:
    saved = _saved()
    owner = _owner_with_downtime(saved)
    name = str(saved[1].iloc[owner]["설비명"])
    master, downtime = saved[1].copy(), saved[2].copy()
    master.loc[owner, "설비명"] = name + "~A"
    downtime.loc[downtime["설비명"].eq(name), "설비명"] = name + "~A"
    saved = (saved[0], master, downtime)
    state = _state(saved)
    row_id = "s:" + name + "~A"
    assert _id(state, owner) == row_id
    gone = _apply(state, _op("delete", 1, ids=[row_id])).state
    back = _apply(gone, _op("restore", 2, ids=[row_id]))
    assert back.toast == "1대를 되살렸습니다"
    assert buffer_matches_saved(saved, back.state.frames), "비가동까지 되살린다"


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


def test_undoing_a_new_units_rename_brings_its_draft_list_place_and_id_back() -> None:
    """이름 바꿈의 칸 초안 열쇠 옮김도 역 patch 에 든다 — 되돌리면 초안이 사라진 id 에 남지 않고,
    브라우저에 옮김을 거꾸로 알린다."""
    saved = _saved()
    other = "s:" + str(saved[1].iloc[3]["설비명"])
    draft = eg.overlay_key("n:NEWX-01", "반입일정")
    state = _with_new(
        _state(saved), "NEWX-01", overlay={draft: "2026-13-45"}, loaded=("n:NEWX-01", other)
    )
    renamed = _apply(state, _op("cell", 1, id="n:NEWX-01", col="설비명", text="NEWX-03"))
    assert renamed.moved == {"n:NEWX-01": "n:NEWX-03"}
    undone = _apply(renamed.state, _op("undo", 2))
    assert undone.state.overlay == {draft: "2026-13-45"}
    assert undone.moved == {"n:NEWX-03": "n:NEWX-01"}
    assert undone.state.loaded == ("n:NEWX-01", other)
    assert undone.renamed == {"NEWX-03": "NEWX-01"}
    view = eg.build_grid_view(
        eg.GridSource(frames=undone.state.frames, saved=saved, overlay=undone.state.overlay),
        CONTEXT,
    )
    assert eg.change_counts(view).errors == 1, "초안 오류가 그대로 보인다"


def test_undoing_a_saved_units_rename_tells_the_screen_the_old_name() -> None:
    state = _state()
    row_id = _id(state, 2)
    old = eg.cell_text(_value(state, 2, "설비명"))
    renamed = _apply(state, _op("cell", 1, id=row_id, col="설비명", text="RENAMED-2"))
    assert renamed.renamed == {old: "RENAMED-2"}
    undone = _apply(renamed.state, _op("undo", 2))
    assert undone.renamed == {"RENAMED-2": old} and undone.state.renames.units == {}


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


def test_undo_keeps_at_most_the_limit() -> None:
    state = _state()
    row_id = _id(state, 0)
    for seq in range(eg.UNDO_LIMIT + 5):
        state = _apply(state, _op("cell", seq + 1, id=row_id, col="메모1", text=str(seq))).state
    assert len(state.undo) == eg.UNDO_LIMIT
    whole = eg.whole_step("붙여넣기로 넣음", state)
    assert eg.push_undo(state.undo, whole) == (whole,), "통째 단계는 앞 단계를 모두 버린다"


def test_a_whole_step_brings_back_the_three_tables_drafts_names_and_list() -> None:
    """엑셀·CSV 「편집본에 넣기」 뒤에 칸을 고치고 둘 다 되돌리면 넣기 전 세 표·칸 초안·이름 지도·
    불러온 목록이 그대로 돌아온다."""
    saved = _saved()
    state = _state(saved)
    first, second = _id(state, 0), _id(state, 3)
    state = _apply(
        state,
        _op("cell", 1, id=first, col="설비명", text="RENAMED-0"),
        _op("cell", 2, id=second, col="반입일정", text="2026-13-45"),
    ).state
    before = eg.GridState(
        frames=state.frames,
        saved=saved,
        renames=state.renames,
        overlay=state.overlay,
        undo=state.undo,
        loaded=(first, second),
    )
    whole = eg.whole_step("엑셀·CSV 넣기", before, token="whole#1")
    pasted = saved[1].copy().iloc[2:].reset_index(drop=True)
    pasted.loc[:, "메모2"] = "넣음"
    after = eg.GridState(
        frames=(saved[0].copy(), pasted, saved[2].copy()),
        saved=saved,
        overlay={eg.overlay_key(_id(state, 5), "Qual일정"): "x"},
        undo=eg.push_undo(before.undo, whole),
        loaded=(_id(state, 5),),
    )
    edited = _apply(
        after, _op("cell", 3, id="s:" + str(pasted.iloc[0]["설비명"]), col="메모1", text="y")
    )
    back = _apply(edited.state, _op("undo", 4), _op("undo", 5, step="whole#1"))
    assert back.refused == 0 and not back.state.undo
    for mine, theirs in zip(back.state.frames, before.frames, strict=True):
        assert mine.equals(theirs)
    assert back.state.overlay == dict(before.overlay)
    assert back.state.renames == before.renames and back.state.loaded == before.loaded


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


# ------------------------------------------------------- 공식 자리로 되돌리기(설계 13-1)


def _overlay_with_official(
    saved: eg.Frames, position: int
) -> tuple[eg.GridContext, eg.Frames, Any]:
    """그 줄을 공식과 다른 자리(가정 배치)로 본 가정 편집 회차 — 공식 일곱 칸은 저장본 값을 옮긴
    것으로 둔다(저장본 = 가정 배치를 얹은 것)."""
    from capa_simulation.services.layout_overlay import place_of

    row = saved[1].iloc[position]
    official = place_of(row)
    moved = (official[0], official[1], 99.0, 77.0, official[4], official[5], official[6])
    name = str(row["설비명"]).strip()
    master = saved[1].copy()
    master.loc[master.index[position], "X좌표"] = 99.0
    master.loc[master.index[position], "Y좌표"] = 77.0
    context = eg.GridContext(
        base=BASE, scenario_name="가정", official=False, official_places={name: official}
    )
    return context, (saved[0], master, saved[2]), moved


def test_official_place_revert_writes_the_official_seven_cells() -> None:
    saved = _saved()
    context, overlay_saved, _ = _overlay_with_official(saved, 2)
    state = _state(overlay_saved)
    row_id = _id(state, 2)
    view = eg.build_grid_view(eg.GridSource(frames=state.frames, saved=state.saved), context)
    unit = eg.detail_data(view, row_id)["unit"]
    assert unit["official"]["text"].startswith("공식: ")
    assert unit["official"]["count"] == 1
    result = _apply(state, _op("official", id=row_id), context=context)
    assert result.changed
    assert _value(result.state, 2, "X좌표") == saved[1].iloc[2]["X좌표"]
    assert _value(result.state, 2, "Y좌표") == saved[1].iloc[2]["Y좌표"]
    assert result.toast is not None and result.toast.startswith("공식 자리로 되돌렸습니다 — 1대")
    assert result.toast_step is not None
    # 한 단계 되돌리기로 가정 자리가 돌아온다.
    undone = _apply(result.state, _op("undo", seq=2), context=context)
    assert _value(undone.state, 2, "X좌표") == 99.0


def test_official_place_revert_is_refused_without_official_places() -> None:
    state = _state()
    result = _apply(state, _op("official", id=_id(state, 0)), context=OVERLAY)
    assert not result.changed
    assert result.refused == 1
    view = eg.build_grid_view(eg.GridSource(frames=state.frames, saved=state.saved), OVERLAY)
    assert "official" not in eg.detail_data(view, _id(state, 0))["unit"]


def _module_group_overlay(
    saved: eg.Frames,
) -> tuple[eg.GridContext, eg.Frames, list[str], list[tuple[object, ...]]]:
    """첫 층의 세 호기를 Main 설비 MOD-G 한 묶음(공식 X 0·12.25·24.5, Xsize 12.25 — 소수 둘째
    자리)으로 두고, 가정 배치는 셋 다 X 를 50 옮긴 것. 공식 일곱 칸 원래 값과 견줄 꼴을 함께
    준다."""
    from capa_simulation.services.layout_overlay import place_of

    master = saved[1].copy()
    positions = [0, 1, 2]
    floor = master.iloc[0][["동", "층"]].tolist()
    names = [str(master.iloc[k]["설비명"]).strip() for k in positions]
    official_cells: list[tuple[object, ...]] = []
    for step, position in enumerate(positions):
        index = master.index[position]
        master.loc[index, ["동", "층"]] = floor
        master.loc[index, "Main 설비"] = "MOD-G"
        master.loc[index, ["X좌표", "Y좌표", "Xsize", "Ysize"]] = [step * 12.25, 5.0, 12.25, 8.0]
        row = master.iloc[position]
        official_cells.append(tuple(row[column] for column in SCENARIO_LAYOUT_COLUMNS))
    official_frames = (saved[0], master.copy(), saved[2])
    moved = master.copy()
    for position in positions:
        moved.loc[moved.index[position], "X좌표"] += 50.0
    context = eg.GridContext(
        base=BASE,
        scenario_name="가정",
        official=False,
        official_places={
            name: place_of(official_frames[1].iloc[position])
            for name, position in zip(names, positions, strict=True)
        },
        official_cells=dict(zip(names, official_cells, strict=True)),
    )
    return context, (saved[0], moved, saved[2]), names, official_cells


def test_official_place_revert_writes_the_original_cells_not_the_rounded_place() -> None:
    """견줄 꼴(`official_places`)은 소수 첫째 자리 반올림이다 — 「공식 자리로 되돌리기」 는 공식
    원래 값(12.25)을 적어 모듈 묶음 바둑판이 어긋나지 않게 한다(리뷰 rs-b1y)."""
    context, overlay_saved, names, cells = _module_group_overlay(_saved())
    state = _state(overlay_saved)
    result = _apply(state, _op("official", id=_id(state, 1)), context=context)
    assert result.changed
    for position, official in enumerate(cells):
        assert _value(result.state, position, "X좌표") == official[2]
    assert _value(result.state, 1, "X좌표") == 12.25
    assert _value(result.state, 1, "Xsize") == 12.25
    # 원래 값이 없으면(낡은 세션 등) 견줄 꼴을 적는다.
    rounded = eg.GridContext(
        base=BASE, official=False, official_places=dict(context.official_places)
    )
    fallback = _apply(state, _op("official", id=_id(state, 1)), context=rounded)
    assert _value(fallback.state, 1, "X좌표") == context.official_places[names[1]][2]


def test_official_place_revert_moves_the_whole_module_group() -> None:
    """모듈이면 Main 설비 묶음 통째로 돌린다(하나만 돌리면 바둑판 검사에 걸린다 — 설계 13-1 검토
    L10). 상세의 「공식: …」 줄이 묶음 수를 알린다."""
    context, overlay_saved, names, _ = _module_group_overlay(_saved())
    state = _state(overlay_saved)
    view = eg.build_grid_view(eg.GridSource(frames=state.frames, saved=state.saved), context)
    unit = eg.detail_data(view, _id(state, 0))["unit"]
    assert unit["official"]["count"] == 3
    result = _apply(state, _op("official", id=_id(state, 0)), context=context)
    assert result.toast is not None and result.toast.startswith("공식 자리로 되돌렸습니다 — 3대")
    assert [_value(result.state, k, "X좌표") for k in range(3)] == [0.0, 12.25, 24.5]
    # 묶음 밖 호기는 그대로다.
    assert _value(result.state, 3, "X좌표") == _value(state, 3, "X좌표")
    # 되돌리기 한 단계로 셋이 함께 가정 자리로 돌아온다.
    undone = _apply(result.state, _op("undo", seq=2), context=context)
    assert [_value(undone.state, k, "X좌표") for k in range(3)] == [50.0, 62.25, 74.5]
