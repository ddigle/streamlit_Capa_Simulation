# Purpose: 설비 마스터 「새 호기」 칸 초안의 체크·칸 오류·잠금·가져오기와 「호기 추가」 op 를 본다.

"""`services/equipment_grid` 의 새 호기 쪽(개편 명세 4-6 나·10장 C — 사용자 결정 D8·D12·D13).

표본은 합성 fleet(`sample_equipment_master`)이다. 체크 상자 셋(에러 없이 추가 · 가용대수 · 도면),
저장과 같은 규칙 표에서 나온 칸 오류, Space 새 호기와 같은 이름 규칙, 잠금(낡은 세션·배치 잠금·
모듈 묶음), 가져오기 규칙, 그리고 「호기 추가」 op 가 받은 초안을 다시 보고 편집본 끝·목록 맨 위에
넣는지를 본다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from capa_simulation.services import equipment_grid as eg
from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.space_layout_edit import PendingRenames, buffer_matches_saved

ANCHOR = date(2026, 10, 1)
BASE = "tok#1"
CONTEXT = eg.GridContext(base=BASE, scenario_name="운영", today=ANCHOR)
STALE = eg.GridContext(
    base=BASE, stale_lock="낡은 세션 — 새 호기 잠금", new_rows_locked=True, today=ANCHOR
)
LOCKED = eg.GridContext(
    base=BASE, scenario_name="가정", official=False, layout_lock="배치 편집 잠금", today=ANCHOR
)
OVERLAY = eg.GridContext(base=BASE, scenario_name="가정", official=False, today=ANCHOR)


def _saved() -> eg.Frames:
    return (
        sample_equipment_baseline(),
        sample_equipment_master(anchor_date=ANCHOR),
        sample_downtime_schedule(anchor_date=ANCHOR),
    )


def _state(saved: eg.Frames | None = None) -> eg.GridState:
    saved = saved or _saved()
    return eg.GridState(frames=(saved[0].copy(), saved[1].copy(), saved[2].copy()), saved=saved)


def _draft(**cells: str) -> list[str]:
    values = eg.blank_draft()
    for column, text in cells.items():
        values[eg.COLUMN_INDEX[column]] = text
    return values


def _check(
    draft: list[str], state: eg.GridState | None = None, context: eg.GridContext = CONTEXT
) -> eg.NewUnitCheck:
    state = state or _state()
    return eg.new_unit_check(
        draft,
        frames=state.frames,
        saved_master=state.saved[1],
        renames=state.renames,
        context=context,
    )


def _add(
    state: eg.GridState,
    draft: list[str],
    *,
    context: eg.GridContext = CONTEXT,
    propagate: bool = True,
    seq: int = 1,
) -> eg.GridApplied:
    op = {"seq": seq, "base": BASE, "op": "add", "draftSeq": 3, "draft": draft}
    op["propagate"] = propagate
    return eg.apply_ops(state, [op], context)


def _valid(**cells: str) -> list[str]:
    return _draft(설비명="NEW-01", 공정소분류="TC Bonding", **cells)


# ------------------------------------------------------------------ 체크 상자


def test_a_blank_draft_fills_the_three_required_flags_and_asks_for_name_and_process() -> None:
    draft = eg.blank_draft()
    assert [draft[eg.COLUMN_INDEX[c]] for c in ("보관유무", "기존설비여부", "레이아웃표시")] == [
        "N",
        "N",
        "Y",
    ]
    check = _check(draft)

    assert check.blocked
    assert check.required == (("설비명", False), ("공정소분류", False))
    assert all(done for _, done in check.flags)
    assert check.errors["설비명"] == eg.NEW_UNIT_NAME_REQUIRED
    # 공정소분류 누락은 저장과 같은 규칙 문구다.
    assert check.errors["공정소분류"] == "설비 마스터의 공정소분류에 누락값이 있습니다"
    assert check.hint == "아직 추가할 수 없습니다 — 공정소분류 · 설비명 칸을 확인합니다"
    assert check.row is None


def test_name_and_process_are_enough_to_add_without_errors() -> None:
    check = _check(_valid())

    assert not check.blocked and not check.errors
    assert check.required == (("설비명", True), ("공정소분류", True))
    assert check.name == "NEW-01" and check.row is not None
    assert check.calc == (("반입일정", False), ("Qual일정", False), ("사용기준", False))
    assert check.map == (("동", False), ("층", False))
    assert check.hint.startswith("추가할 수 있습니다 — 반입일정·Qual일정·사용기준 칸이")


def test_the_capacity_tier_needs_dates_and_usage_hbm_or_edp() -> None:
    check = _check(_valid(반입일정="2026-11-02", Qual일정="2026-11-20", 사용기준="hbm"))

    assert check.calc == (("반입일정", True), ("Qual일정", True), ("사용기준", True))
    done = _check(
        _valid(반입일정="2026-11-02", Qual일정="2026-11-20", 사용기준="EDP", Qual상태="계획")
    )
    assert not done.blocked and all(ok for _, ok in done.calc)
    assert done.hint == "추가할 수 있습니다"
    other = _check(_valid(반입일정="2026-11-02", 사용기준="HBM3E"))
    assert dict(other.calc)["사용기준"] is False


def test_a_qual_date_makes_qual_status_required_to_add_without_errors() -> None:
    """Qual일정이 있는 신규 호기(보관 N·기존설비 N)는 Qual상태가 필수다(저장 규칙 그대로) — 「에러
    없이 추가하려면」 줄에 서야 막대가 다 찬 채 「호기 추가」 가 막히지 않는다(사용자 요구)."""
    check = _check(_valid(Qual일정="2026-11-20"))

    assert check.blocked and "Qual상태" in check.errors
    assert check.required == (("설비명", True), ("공정소분류", True), ("Qual상태", False))
    assert "Qual상태" not in dict(check.calc)
    # 채워도 그 줄에 남아 ✓ 로 선다.
    filled = _check(_valid(Qual일정="2026-11-20", Qual상태="계획"))
    assert filled.required[-1] == ("Qual상태", True) and not filled.blocked
    # 기존설비는 Qual상태가 필수가 아니다(저장 규칙의 신규 호기만).
    existing = _check(_valid(Qual일정="2026-11-20", 기존설비여부="Y"))
    assert [column for column, _ in existing.required] == ["설비명", "공정소분류"]
    assert not existing.blocked


def test_an_empty_cell_that_other_values_block_joins_the_required_line() -> None:
    """좌표를 넣었는데 크기가 비면 저장 규칙이 그 빈 칸에 오류를 건다 — 그 칸도 「에러 없이
    추가하려면」 줄에 선다(막는 오류가 숨은 빈 칸에 남지 않게)."""
    check = _check(_valid(동="C1", 층="1F", X좌표="3", Y좌표="4"))

    assert check.blocked and "Xsize" in check.errors
    assert ("Xsize", False) in check.required
    sized = _check(_valid(동="C1", 층="1F", X좌표="3", Y좌표="4", Xsize="12", Ysize="7"))
    assert not sized.blocked
    assert [column for column, _ in sized.required] == ["설비명", "공정소분류"]
    # 값이 있는 칸의 오류(날짜 꼴)는 그 칸에서 보인다 — 줄에 올리지 않는다.
    bad = _check(_valid(반입일정="2026-13-45"))
    assert "반입일정" in bad.errors and "반입일정" not in dict(bad.required)


def test_the_map_tier_is_floor_and_building_and_goes_away_when_not_drawn() -> None:
    placed = _check(_valid(동="C2", 층="3F"))
    assert placed.map == (("동", True), ("층", True))
    hidden = _check(_valid(레이아웃표시="N"))
    assert hidden.map == ()


def test_cell_errors_come_from_the_same_rules_as_saving() -> None:
    draft = _valid(반입일정="2026-12-01", Qual일정="2026-11-01", Qual상태="계획", 환산비="0")
    check = _check(draft)

    assert check.errors["환산비"] == "환산비는 0보다 큰 숫자여야 합니다"
    assert check.errors["Qual일정"] == "제진대·물류·반입·Qual 일정 순서가 올바르지 않습니다"
    bad = _check(_valid(반입일정="2026-13-45", 동="C9"))
    assert bad.errors["반입일정"] == "반입일정은 날짜 형식이어야 합니다"
    assert bad.errors["동"] == "동은 C1~C5, 층은 1F~6F 범위여야 합니다"
    # 같은 글이면 저장도 막는다(같은 규칙).
    row = check.values
    frame = pd.DataFrame([dict(zip(EQUIPMENT_COLUMNS, row, strict=True))])
    try:
        prepare_equipment_master(frame)
    except ValueError:
        pass
    else:  # pragma: no cover - 저장이 받으면 규칙이 갈린 것이다
        raise AssertionError("저장이 받은 초안을 칸 판정이 막았다")


def test_a_name_left_only_in_downtime_cannot_be_a_new_unit_name() -> None:
    """고아 비가동(설비 마스터에 없는 이름의 비가동 줄 — `reserved_names`)의 이름은 새 호기로 쓸 수
    없다(Space 새 호기와 같은 규칙)."""
    state = _state()
    downtime = state.frames[2].copy()
    downtime.loc[0, "설비명"] = "ORPHAN-01"
    orphan = eg.GridState(frames=(state.frames[0], state.frames[1], downtime), saved=state.saved)

    check = _check(_draft(설비명="ORPHAN-01", 공정소분류="TC Bonding"), orphan)

    assert check.blocked and "ORPHAN-01" in check.errors["설비명"]
    assert "비가동" in check.errors["설비명"]


def test_name_rules_follow_space_new_units() -> None:
    state = _state()
    saved_name = str(state.saved[1]["설비명"].iloc[0])

    same = _check(_draft(설비명=saved_name, 공정소분류="TC Bonding"), state)
    assert same.errors["설비명"] == f"이미 있는 호기입니다: {saved_name}"
    case = _check(_draft(설비명=saved_name.lower(), 공정소분류="TC Bonding"), state)
    assert case.errors["설비명"] == f"이미 있는 호기입니다: {saved_name.lower()}({saved_name})"
    # 저장 안 한 지운 이름은 쓸 수 없다.
    master = state.frames[1].iloc[1:].reset_index(drop=True)
    gone = eg.GridState(frames=(state.frames[0], master, state.frames[2]), saved=state.saved)
    reserved = _check(_draft(설비명=saved_name, 공정소분류="TC Bonding"), gone)
    assert "지우고 아직 저장하지" in reserved.errors["설비명"]
    long = _check(_draft(설비명="X" * 200, 공정소분류="TC Bonding"), state)
    assert long.errors["설비명"].startswith("새 호기 이름은 1~")


def test_a_main_equipment_name_cannot_be_a_new_unit_name() -> None:
    saved = _saved()
    master = saved[1].copy()
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    state = _state((saved[0], master, saved[2]))

    check = _check(_draft(설비명="grp-1", 공정소분류="TC Bonding"), state)

    assert check.errors["설비명"] == "이미 Main 설비로 쓰는 이름입니다: grp-1(GRP-1)"


def test_joining_a_module_group_locks_coordinates_and_needs_the_groups_values() -> None:
    saved = _saved()
    master = saved[1].copy()
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    state = _state((saved[0], master, saved[2]))
    group_floor = (str(master.loc[0, "동"]), str(master.loc[0, "층"]))

    wrong = _check(
        _draft(
            설비명="GRP-1E", 공정소분류="TC Bonding", **{"Main 설비": "GRP-1"}, X좌표="3", Y좌표="4"
        ),
        state,
    )
    assert set(wrong.locks) == {"X좌표", "Y좌표", "Xsize", "Ysize"}
    assert wrong.values[eg.COLUMN_INDEX["X좌표"]] == ""
    # 모듈 행끼리 같아야 하는 칸(동·층 등)이 묶음과 다르면 저장 규칙이 막는다.
    assert wrong.errors["동"] == "같은 Main 설비의 모듈 행은 동이 같아야 합니다"
    right = _check(
        _draft(
            설비명="GRP-1E",
            공정소분류=str(master.loc[0, "공정소분류"]),
            공정대분류=str(master.loc[0, "공정대분류"]),
            공정구분=str(master.loc[0, "공정구분"]),
            투자구분=str(master.loc[0, "투자구분"]),
            동=group_floor[0],
            층=group_floor[1],
            **{"Main 설비": "GRP-1"},
        ),
        state,
    )
    assert not right.blocked, right.errors


def test_a_stale_session_locks_the_whole_draft_with_the_reason() -> None:
    check = _check(_valid(), context=STALE)

    assert check.blocked and not check.errors
    assert set(check.locks) == set(EQUIPMENT_COLUMNS)
    assert check.hint == "낡은 세션 — 새 호기 잠금"
    payload = eg.new_unit_data(eg.build_grid_view(_source(), STALE), check, seq=1, propagate=True)
    assert payload["locked"] == "낡은 세션 — 새 호기 잠금"


def test_a_locked_layout_takes_the_place_columns_away() -> None:
    check = _check(_valid(동="C2", 층="3F", X좌표="5", Y좌표="6"), context=LOCKED)

    assert set(check.locks) == {"동", "층", "X좌표", "Y좌표"}
    assert [check.values[eg.COLUMN_INDEX[c]] for c in ("동", "층", "X좌표", "Y좌표")] == [""] * 4
    assert not check.blocked


# ------------------------------------------------------------------ 가져오기


def test_copying_takes_unit_info_and_place_but_not_name_dates_or_coordinates() -> None:
    view = eg.build_grid_view(_source(), CONTEXT)
    first = next(iter(view.index.live))
    source = list(view.values[first])
    source[eg.COLUMN_INDEX["투자구분"]] = "기존"
    source[eg.COLUMN_INDEX["기존설비여부"]] = "Y"
    source[eg.COLUMN_INDEX["Main 설비"]] = "GRP-9"
    base = _draft(설비명="KEEP-01", 반입일정="2026-12-01")

    copied = eg.copied_draft(source, base)

    for column in ("공정소분류", "Model", "사용기준", "동", "층", "레이아웃표시", "Area Code"):
        assert copied[eg.COLUMN_INDEX[column]] == source[eg.COLUMN_INDEX[column]], column
    assert copied[eg.COLUMN_INDEX["기존설비여부"]] == "N"
    assert copied[eg.COLUMN_INDEX["투자구분"]] == "신규"
    assert copied[eg.COLUMN_INDEX["설비명"]] == "KEEP-01"
    assert copied[eg.COLUMN_INDEX["반입일정"]] == "2026-12-01"
    assert copied[eg.COLUMN_INDEX["Main 설비"]] == ""
    assert copied[eg.COLUMN_INDEX["X좌표"]] == ""
    fresh = eg.copied_draft(source)
    assert fresh[eg.COLUMN_INDEX["설비명"]] == "" and fresh[eg.COLUMN_INDEX["반입일정"]] == ""


def test_the_copy_source_is_the_same_name_then_the_first_prefix() -> None:
    names = ["WBA-01", "WBA-10", "wba-1", "DAA-05"]

    assert eg.copy_source(names, "WBA-1") == 2
    assert eg.copy_source(names, "wba") == 0
    assert eg.copy_source(names, " daa ") == 3
    assert eg.copy_source(names, "없는-호기") is None
    assert eg.copy_source(names, "  ") is None
    master = _saved()[1]
    assert eg.unit_texts(master, 0)[eg.NAME_INDEX] == str(master["설비명"].iloc[0])


def test_after_adding_only_process_building_and_floor_stay() -> None:
    kept = eg.kept_draft(_valid(동="C2", 층="3F", 반입일정="2026-11-02"))

    assert kept == _draft(공정소분류="TC Bonding", 동="C2", 층="3F")


# ------------------------------------------------------------------ 「호기 추가」 op


def _source(state: eg.GridState | None = None) -> eg.GridSource:
    state = state or _state()
    return eg.GridSource(frames=state.frames, saved=state.saved)


def test_adding_puts_the_unit_at_the_end_of_the_buffer_and_the_top_of_the_list() -> None:
    state = _state()
    loaded = (eg.grid_index(state.frames[1], state.saved[1], {}).ids[0],)
    state = eg.GridState(frames=state.frames, saved=state.saved, loaded=loaded)

    result = _add(state, _valid(반입일정="2026-11-02"), propagate=False)
    master = result.state.frames[1]

    assert result.changed and result.frames_changed == (False, True, False)
    assert len(master) == len(state.frames[1]) + 1
    assert master.iloc[-1]["설비명"] == "NEW-01"
    assert master.iloc[-1]["반입일정"] == pd.Timestamp("2026-11-02")
    assert master.iloc[-1]["환산비"] == 1.0
    assert master.dtypes.equals(state.frames[1].dtypes)
    assert result.added == (("n:NEW-01", "NEW-01", False),)
    assert result.state.loaded == ("n:NEW-01", *loaded)
    assert result.toast == (
        "NEW-01을 표 맨 위에 넣었습니다 — 다른 설비 시나리오에서는 일정 없음으로 들어갑니다 "
        "(리비전 저장 때 함께 저장)"
    )
    assert result.toast_step is not None
    # 차례만 다른 공통 리비전이 생기지 않는다 — 앞 줄은 저장본 그대로다.
    head = master.iloc[: len(state.frames[1])].reset_index(drop=True)
    assert buffer_matches_saved(
        state.saved, (state.frames[0], head, state.frames[2]), PendingRenames()
    )


def test_adding_is_one_undo_step() -> None:
    state = _state()
    added = _add(state, _valid())

    undone = eg.apply_ops(added.state, [{"seq": 2, "base": BASE, "op": "undo"}], CONTEXT)

    assert undone.state.frames[1].equals(state.frames[1])
    assert undone.toast == "되돌림: 새 호기 NEW-01"


def test_the_add_op_checks_the_draft_it_carries_and_refuses_errors() -> None:
    state = _state()
    saved_name = str(state.saved[1]["설비명"].iloc[0])

    refused = _add(state, _draft(설비명=saved_name, 공정소분류="TC Bonding"))

    assert not refused.changed and refused.refused == 1 and refused.added == ()
    assert refused.toast == "아직 추가할 수 없습니다 — 설비명 칸을 확인합니다"
    broken = eg.apply_ops(state, [{"seq": 1, "base": BASE, "op": "add", "draft": ["x"]}], CONTEXT)
    assert broken.refused == 1 and not broken.changed


def test_a_stale_session_refuses_the_add_op() -> None:
    result = _add(_state(), _valid(), context=STALE)

    assert result.refused == 1 and not result.changed
    assert result.toast == "낡은 세션 — 새 호기 잠금"


def test_an_add_from_an_old_base_is_dropped() -> None:
    op: dict[str, Any] = {"seq": 1, "base": "old#0", "op": "add", "draft": _valid()}
    result = eg.apply_ops(_state(), [op], CONTEXT)

    assert result.dropped == 1 and not result.changed and result.added == ()
    # 같은 op 가 지금 base 면 들어간다 — 버린 것은 base 때문이다.
    fresh = eg.apply_ops(_state(), [{**op, "base": BASE}], CONTEXT)
    assert fresh.dropped == 0 and fresh.added == (("n:NEW-01", "NEW-01", False),)


def test_pressing_add_twice_keeps_the_first_success_toast_and_its_undo() -> None:
    """같은 초안·같은 `draftSeq` 의 「호기 추가」 둘(두 번 누름 — 브라우저 단추는 회차가 돌아올
    때까지 켜져 있다)은 한 번 넣고 둘째는 말없이 버린다(개편 명세 6-4) — 둘째가 이름 겹침으로
    거부되어 성공 토스트·되돌리기를 덮지 않는다."""
    draft = _valid()
    ops = [
        {"seq": seq, "mount": "m", "base": BASE, "op": "add", "draftSeq": 5, "draft": draft}
        for seq in (1, 2)
    ]

    result = eg.apply_ops(_state(), ops, CONTEXT)

    assert result.added == (("n:NEW-01", "NEW-01", False),) and result.refused == 0
    assert result.toast is not None and result.toast.startswith("NEW-01을 표 맨 위에 넣었습니다")
    assert result.toast_step == "m#1"


def test_an_add_behind_the_session_draft_is_dropped_quietly() -> None:
    """세션 초안 번호(`GridState.draft_seq` — 넣은 뒤·가져오기 뒤 오른다)보다 작은 `draftSeq` 의
    「호기 추가」 는 다음 회차에 따로 와도 넣지 않고 알리지도 않는다. 같거나 크면(브라우저가 앞선
    초안) 받는다."""
    state = _state()
    behind = eg.GridState(frames=state.frames, saved=state.saved, draft_seq=6)
    op: dict[str, Any] = {"seq": 1, "base": BASE, "op": "add", "draftSeq": 5, "draft": _valid()}

    dropped = eg.apply_ops(behind, [op], CONTEXT)
    taken = eg.apply_ops(behind, [{**op, "draftSeq": 6}], CONTEXT)

    assert not dropped.changed and dropped.refused == 0 and dropped.toast is None
    assert taken.added == (("n:NEW-01", "NEW-01", False),)


def test_adding_in_an_assumption_session_says_the_official_layout_stays_empty() -> None:
    result = _add(_state(), _valid(동="C2", 층="3F"), context=OVERLAY)

    assert result.toast is not None and result.toast.endswith(eg.ADDED_OVERLAY_NOTE)
    master = result.state.frames[1]
    # 가정 편집 회차는 그 시나리오 배치로 둔다(공식 배치를 비우는 것은 저장소의 몫).
    assert (master.iloc[-1]["동"], master.iloc[-1]["층"]) == ("C2", "3F")


def test_adding_with_a_locked_layout_puts_a_module_into_its_groups_floor() -> None:
    saved = _saved()
    master = saved[1].copy()
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    for column in ("동", "층"):
        master.loc[1, column] = master.loc[0, column]
    state = _state((saved[0], master, saved[2]))
    draft = _draft(
        설비명="GRP-1E",
        공정소분류=str(master.loc[0, "공정소분류"]),
        공정대분류=str(master.loc[0, "공정대분류"]),
        공정구분=str(master.loc[0, "공정구분"]),
        투자구분=str(master.loc[0, "투자구분"]),
        **{"Main 설비": "GRP-1"},
    )

    result = _add(state, draft, context=LOCKED)
    row = result.state.frames[1].iloc[-1]

    assert result.added and (row["동"], row["층"]) == (master.loc[0, "동"], master.loc[0, "층"])
    assert pd.isna(row["X좌표"]) and pd.isna(row["Y좌표"])


def test_the_panel_payload_carries_tiers_errors_and_locks_by_contract_position() -> None:
    state = _state()
    view = eg.build_grid_view(_source(state), CONTEXT)
    check = _check(_valid(Qual일정="2026-11-20"), state)

    payload = eg.new_unit_data(
        view, check, seq=7, propagate=False, notes=("메모",), propagate_warning="경고"
    )

    assert payload["panel"] == "new" and payload["draft"]["seq"] == 7
    assert payload["draft"]["propagate"] is False and payload["checked"] == 7
    assert payload["errors"] == {str(eg.COLUMN_INDEX["Qual상태"]): check.errors["Qual상태"]}
    assert payload["tiers"]["required"] == [
        [eg.COLUMN_INDEX["설비명"], True],
        [eg.COLUMN_INDEX["공정소분류"], True],
        [eg.COLUMN_INDEX["Qual상태"], False],
    ]
    # 늘 필수인 칸(브라우저가 「호기 추가」 를 켜고 만진 표지를 주는 칸)은 그대로다 — 조건부 필수
    # 칸의 오류는 만지지 않아도 보인다.
    assert payload["required"] == [
        eg.COLUMN_INDEX[c]
        for c in ("설비명", "공정소분류", "보관유무", "기존설비여부", "레이아웃표시")
    ]
    assert [k for k, _ in payload["tiers"]["calc"]][-1] == eg.COLUMN_INDEX["사용기준"]
    assert payload["blocked"] is True and payload["locked"] is None
    assert payload["notes"] == ["메모"] and payload["propagateWarning"] == "경고"
    assert len(payload["draft"]["values"]) == len(EQUIPMENT_COLUMNS)
