# Purpose: 설비 마스터 표 순수 모델의 칸 정의·묶음·행 id·칸 글자·data 꼴·잠금·차이를 검증한다.

"""`services/equipment_grid` 의 모양 쪽(개편 명세 4-2·4-4·6-3·7-1·11장 「서비스(순수)」).

표본은 합성 fleet(`sample_equipment_master`)이다 — 줄 수·공정 이름을 계약으로 보지 않고 표본 값에서
고른다.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from capa_simulation.services import equipment_grid as eg
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_COLUMNS,
    SCENARIO_LAYOUT_COLUMNS,
    SCENARIO_SCHEDULE_COLUMNS,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.equipment_validation import (
    MasterIssue,
    equipment_master_issues,
)
from capa_simulation.services.space_layout_edit import PendingRenames

ANCHOR = date(2026, 10, 1)


def _saved() -> eg.Frames:
    return (
        sample_equipment_baseline(),
        sample_equipment_master(anchor_date=ANCHOR),
        sample_downtime_schedule(anchor_date=ANCHOR),
    )


def _copy(frames: eg.Frames) -> eg.Frames:
    return frames[0].copy(), frames[1].copy(), frames[2].copy()


def _view(
    frames: eg.Frames,
    saved: eg.Frames,
    *,
    renames: PendingRenames | None = None,
    overlay: dict[str, str] | None = None,
    issues: tuple[MasterIssue, ...] = (),
    context: eg.GridContext | None = None,
    alerts: dict[str, str] | None = None,
) -> eg.GridView:
    source = eg.GridSource(
        frames=frames,
        saved=saved,
        renames=renames or PendingRenames(),
        overlay=overlay or {},
        issues=issues,
        alerts=alerts or {},
    )
    return eg.build_grid_view(source, context or eg.GridContext(base="t#1", scenario_name="운영"))


# ------------------------------------------------------------------ 칸 정의


def test_the_grid_columns_are_the_39_contract_columns_in_contract_order() -> None:
    assert [column.name for column in eg.GRID_COLUMNS] == list(EQUIPMENT_COLUMNS)
    assert len(eg.GRID_COLUMNS) == 39
    assert eg.NAME_INDEX == EQUIPMENT_COLUMNS.index("설비명")


def test_positions_in_the_data_contract_example_match_the_contract_order() -> None:
    """명세 6-3 검토 줄의 자리 번호(반입일정 19 · Qual일정 22 · Qual상태 24 …)."""
    expected = {
        "Area Code": 0,
        "공정소분류": 2,
        "Model": 4,
        "설비명": 5,
        "동": 10,
        "층": 11,
        "담당자": 12,
        "X좌표": 13,
        "Ysize": 16,
        "물류일정": 18,
        "반입일정": 19,
        "반입실적": 20,
        "반입상태": 21,
        "Qual일정": 22,
        "Qual실적": 23,
        "Qual상태": 24,
        "환산비": 34,
        "Main 설비": 35,
    }
    assert {name: eg.COLUMN_INDEX[name] for name in expected} == expected


def test_scopes_split_the_columns_as_the_scenario_contract_does() -> None:
    by_scope: dict[str, set[str]] = {}
    for column in eg.GRID_COLUMNS:
        by_scope.setdefault(column.scope, set()).add(column.name)
    assert by_scope["scenario"] == set(SCENARIO_SCHEDULE_COLUMNS)
    assert by_scope["status"] == {"반입상태", "Qual상태"}


def test_column_kinds_follow_the_save_normalisation() -> None:
    kinds = {column.name: column for column in eg.GRID_COLUMNS}
    assert kinds["설비명"].kind == "name"
    assert {name for name, c in kinds.items() if c.kind == "date"} == {
        "제진대일정",
        "물류일정",
        "반입일정",
        "반입실적",
        "Qual일정",
        "Qual실적",
        "정지일정",
        "반출/이설일정",
    }
    assert {name for name, c in kinds.items() if c.kind == "number"} == {
        "X좌표",
        "Y좌표",
        "Xsize",
        "Ysize",
        "환산비",
    }
    assert kinds["동"].options == ("C1", "C2", "C3", "C4", "C5") and kinds["동"].blank
    assert kinds["Qual상태"].options == ("계획", "확정", "완료", "지연")
    for flag in ("보관유무", "기존설비여부", "레이아웃표시"):
        assert kinds[flag].kind == "choice" and kinds[flag].options == ("Y", "N")
        assert not kinds[flag].blank, "Y/N 은 비울 수 없는 칸이라 「(비움)」 이 없다"
    assert kinds["Area Code"].kind == "text" and kinds["Area Code"].suggest == (
        "Main",
        "MI",
        "부대",
    )
    assert kinds["시나리오 메모"].kind == "memo" and kinds["메모1"].kind == "memo"


def test_column_sets_are_five_and_never_carry_the_pinned_name_column() -> None:
    assert [item.key for item in eg.COLUMN_SETS] == ["basic", "schedule", "place", "memo", "all"]
    for item in eg.COLUMN_SETS:
        assert "설비명" not in item.columns
        assert set(item.columns) <= set(EQUIPMENT_COLUMNS)
        assert len(item.columns) == len(set(item.columns))
    everything = eg.COLUMN_SETS[-1]
    assert everything.label == "전체 39칸"
    assert everything.columns == tuple(c for c in EQUIPMENT_COLUMNS if c != "설비명")


def test_detail_groups_cover_every_column_exactly_once() -> None:
    seen = [column for group in eg.DETAIL_GROUPS for column in group.columns]
    assert sorted(seen) == sorted(EQUIPMENT_COLUMNS)
    assert len(seen) == len(set(seen)) == 39
    scenario = next(group for group in eg.DETAIL_GROUPS if group.scope == "scenario")
    assert set(scenario.columns) == set(SCENARIO_SCHEDULE_COLUMNS)


def test_lock_sets_name_contract_columns() -> None:
    assert set(eg.LOCK_SETS["layout"]) == set(SCENARIO_LAYOUT_COLUMNS)
    assert set(eg.LOCK_SETS["stale"]) == set(SCENARIO_SCHEDULE_COLUMNS)
    assert eg.LOCK_SETS["module"] == ("X좌표", "Y좌표", "Xsize", "Ysize")


def test_scenario_column_help_keeps_its_words() -> None:
    assert eg.scenario_column_help("Qual일정", "셋업 실무") == "시나리오 — 「셋업 실무」 에만 저장"
    assert eg.scenario_column_help("반입상태", None) == eg.STATUS_COLUMN_HELP
    assert eg.scenario_column_help("Maker", None) == eg.COMMON_COLUMN_HELP


# ------------------------------------------------------------------ 칸 글자


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, ""),
        (pd.NA, ""),
        (pd.NaT, ""),
        (float("nan"), ""),
        (np.nan, ""),
        (pd.Timestamp("2026-11-09 00:00:00"), "2026-11-09"),
        (np.datetime64("2026-11-09"), "2026-11-09"),
        (date(2026, 1, 2), "2026-01-02"),
        (datetime(2026, 1, 2, 13, 0), "2026-01-02"),
        (12.0, "12"),
        (0.25, "0.25"),
        (-0.0, "0"),
        (1e-5, "0.00001"),
        (np.float64(7.5), "7.5"),
        (3, "3"),
        ("  WBA-09 ", "WBA-09"),
        (math.inf, "inf"),
    ],
)
def test_cell_text_is_the_screen_and_comparison_text(value: object, text: str) -> None:
    assert eg.cell_text(value) == text


def test_text_matrix_matches_cell_text_value_by_value() -> None:
    master = sample_equipment_master(anchor_date=ANCHOR).head(6)
    matrix = eg.text_matrix(master)
    assert len(matrix) == 6 and all(len(row) == 39 for row in matrix)
    for position, row in enumerate(matrix):
        for k, column in enumerate(EQUIPMENT_COLUMNS):
            assert row[k] == eg.cell_text(master.iloc[position][column])


# ------------------------------------------------------------------ 행 id


def test_row_ids_keep_the_saved_name_through_a_rename_and_mark_new_units() -> None:
    saved = sample_equipment_master(anchor_date=ANCHOR).head(4).reset_index(drop=True)
    names = saved["설비명"].tolist()
    master = saved.copy()
    master.loc[1, "설비명"] = "RENAMED"
    master = pd.concat([master.drop(index=2), saved.iloc[[0]].assign(설비명="NEW-1")])
    index = eg.grid_index(master.reset_index(drop=True), saved, {"RENAMED": names[1]})
    assert index.ids == (
        "s:" + names[0],
        "s:" + names[1],
        "s:" + names[3],
        "n:NEW-1",
    )
    assert index.deleted == ("s:" + names[2],)
    assert index.saved["s:" + names[2]] == 2
    assert index.is_new("n:NEW-1") and not index.is_new("s:" + names[0])
    assert index.saved_name("s:" + names[1]) == names[1]
    assert index.saved_name("s:" + names[2]) == names[2], "지운 표시 호기도"
    assert index.saved_name("n:NEW-1") is None


def test_duplicate_names_get_unique_ids() -> None:
    saved = sample_equipment_master(anchor_date=ANCHOR).head(2).reset_index(drop=True)
    master = pd.concat([saved, saved.iloc[[0]]], ignore_index=True)
    index = eg.grid_index(master, saved, {})
    first = "s:" + str(saved.loc[0, "설비명"])
    assert index.ids[0] == first and index.ids[2] == first + eg.DUPLICATE_MARK + "2"
    assert len(set(index.ids)) == 3
    assert index.is_new(index.ids[2]) and index.saved_name(index.ids[2]) is None


def test_a_saved_name_with_a_tilde_is_a_saved_unit() -> None:
    """설비명 규칙은 「~」 를 받는다 — id 꼬리와 헷갈려 저장본 호기를 새 호기로 보지 않는다."""
    saved = _saved()
    master = saved[1].copy()
    master.loc[3, "설비명"] = "WB~01"
    named = (saved[0], master, saved[2])
    frames = _copy(named)
    frames[1].loc[3, "담당자"] = "고침"
    view = _view(frames, named)
    row_id = "s:WB~01"
    assert view.index.saved_name(row_id) == "WB~01" and not view.index.is_new(row_id)
    assert view.tags.get(row_id) is None
    assert view.marks[row_id].changed == {eg.COLUMN_INDEX["담당자"]: "샘플 담당자"}
    counts = eg.change_counts(view)
    assert (counts.cells, counts.new) == (1, 0)


def test_a_duplicate_tail_never_takes_a_saved_units_id() -> None:
    """겹친 이름의 둘째 줄 id 가 다른 저장본 호기 id(「A~2」 꼴 이름)와 겹쳐 한 줄을 덮지 않는다."""
    saved = sample_equipment_master(anchor_date=ANCHOR).head(3).reset_index(drop=True)
    saved.loc[1, "설비명"] = "A"
    saved.loc[2, "설비명"] = "A" + eg.DUPLICATE_MARK + "2"
    master = pd.concat([saved, saved.iloc[[1]]], ignore_index=True)
    index = eg.grid_index(master, saved, {})
    assert len(set(index.ids)) == len(index.ids) == 4
    assert index.live["s:A" + eg.DUPLICATE_MARK + "2"] == 2
    assert index.is_new(index.ids[3])


def test_save_id_map_follows_renames_new_units_and_deletions() -> None:
    saved = sample_equipment_master(anchor_date=ANCHOR).head(3).reset_index(drop=True)
    names = saved["설비명"].tolist()
    master = saved.copy()
    master.loc[0, "설비명"] = "RENAMED"
    master = pd.concat([master.drop(index=2), saved.iloc[[1]].assign(설비명="NEW-1")])
    master = master.reset_index(drop=True)
    index = eg.grid_index(master, saved, {"RENAMED": names[0]})
    moved = eg.save_id_map(index, master)
    assert moved["s:" + names[0]] == "s:RENAMED"
    assert moved["n:NEW-1"] == "s:NEW-1"
    assert moved["s:" + names[2]] is None
    assert eg.move_ids(["s:" + names[2], "s:" + names[0], "n:NEW-1"], moved) == (
        "s:RENAMED",
        "s:NEW-1",
    )


# ------------------------------------------------------------------ 불러온 목록


def test_loading_puts_new_ids_on_top_keeps_present_ones_and_cuts_at_the_limit() -> None:
    result = eg.load_ids(("a", "b"), ["c", "a", "d"], limit=10)
    assert result.loaded == ("c", "d", "a", "b") and result.added == 2 and result.already == 1
    capped = eg.load_ids(("a",), ["b", "c", "d"], limit=3)
    assert capped.loaded == ("b", "c", "a") and capped.cut == 1


def test_all_load_ids_take_the_natural_name_order_only_over_the_limit() -> None:
    saved = _saved()
    master = saved[1]
    index = eg.grid_index(master, master, {})
    assert eg.all_load_ids(master, index, limit=10_000) == list(index.live)
    head = eg.all_load_ids(master, index, limit=5)
    names = sorted(master["설비명"].astype(str))[:5]
    assert [index.saved_name(row_id) for row_id in head] == names


def test_prune_loaded_keeps_deleted_marks_and_drops_unknown_ids() -> None:
    saved = _saved()
    frames = _copy(saved)
    gone = frames[1].iloc[0]["설비명"]
    frames = (frames[0], frames[1].iloc[1:].reset_index(drop=True), frames[2])
    view = _view(frames, saved)
    loaded = ("s:" + gone, "s:" + frames[1].iloc[0]["설비명"], "s:NOPE")
    assert eg.prune_loaded(loaded, view.index) == loaded[:2]


# ------------------------------------------------------------------ 표 모양·data


def test_changed_cells_carry_the_saved_text_and_new_rows_are_tagged() -> None:
    saved = _saved()
    frames = _copy(saved)
    master = frames[1]
    master.loc[0, "담당자"] = "담당B"
    master.loc[0, "반입일정"] = pd.Timestamp("2026-12-01")
    extra = master.iloc[[1]].assign(설비명="NEW-1")
    frames = (frames[0], pd.concat([master, extra], ignore_index=True), frames[2])
    view = _view(frames, saved)
    first = view.index.ids[0]
    saved_row = eg.text_matrix(saved[1])[0]
    assert view.marks[first].changed == {
        eg.COLUMN_INDEX["담당자"]: saved_row[eg.COLUMN_INDEX["담당자"]],
        eg.COLUMN_INDEX["반입일정"]: saved_row[eg.COLUMN_INDEX["반입일정"]],
    }
    assert view.tags["n:NEW-1"] == "new" and not view.marks["n:NEW-1"].changed
    counts = eg.change_counts(view)
    assert (counts.cells, counts.new, counts.deleted) == (2, 1, 0)


def test_deleted_units_show_their_saved_values_and_lock_every_cell() -> None:
    saved = _saved()
    frames = _copy(saved)
    gone = frames[1].iloc[3]
    frames = (frames[0], frames[1].drop(index=3).reset_index(drop=True), frames[2])
    view = _view(frames, saved)
    row_id = "s:" + gone["설비명"]
    assert view.tags[row_id] == "deleted"
    assert view.values[row_id] == eg.text_matrix(saved[1])[3]
    assert eg.lock_of(view, row_id, "메모1") == "deleted"
    payload = eg.grid_data(view, [row_id])["rows"][0]
    assert payload["tag"] == "deleted" and "locks" not in payload


def test_issues_become_errors_and_warnings_on_their_cells() -> None:
    saved = _saved()
    frames = _copy(saved)
    master = frames[1].astype(object)
    master.loc[2, "Area Code"] = "Main2"
    master.loc[4, "공정소분류"] = None
    frames = (frames[0], master, frames[2])
    issues = equipment_master_issues(master)
    view = _view(frames, saved, issues=issues)
    warned, broken = view.index.ids[2], view.index.ids[4]
    assert eg.COLUMN_INDEX["Area Code"] in view.marks[warned].warns
    assert view.marks[broken].errors[eg.COLUMN_INDEX["공정소분류"]] == (
        "설비 마스터의 공정소분류에 누락값이 있습니다"
    )
    assert any(item[0] == broken and item[2] == "공정소분류" for item in view.errors)
    assert not any(item[0] == warned for item in view.errors), "경고는 고칠 것 목록에 들지 않는다"


def test_a_cell_draft_replaces_the_value_and_reports_the_save_rule_message() -> None:
    saved = _saved()
    view = _view(_copy(saved), saved, overlay={eg.overlay_key("s:X", "반입일정"): "x"})
    assert not view.errors, "편집본에 없는 행의 초안은 걷는다"
    row_id = view.index.ids[0]
    view = _view(_copy(saved), saved, overlay={eg.overlay_key(row_id, "반입일정"): "2026-13-40"})
    position = eg.COLUMN_INDEX["반입일정"]
    assert view.values[row_id][position] == "2026-13-40"
    assert view.marks[row_id].errors[position] == "반입일정은 날짜 형식이어야 합니다"
    assert eg.change_counts(view).errors == 1


def test_a_cell_draft_hides_the_rule_result_of_the_old_value_in_that_cell() -> None:
    """초안이 있는 칸에는 초안 글이 보인다 — 편집본 옛 값의 규칙 오류를 같은 칸에 두 번 세지
    않는다."""
    saved = _saved()
    frames = _copy(saved)
    master = frames[1].astype(object)
    master.loc[0, "Qual상태"] = None
    frames = (frames[0], master, frames[2])
    issues = equipment_master_issues(master)
    row_id = eg.grid_index(master, saved[1], {}).ids[0]
    assert any(item.position == 0 and item.column == "Qual상태" for item in issues)
    view = _view(frames, saved, issues=issues, overlay={eg.overlay_key(row_id, "Qual상태"): "모름"})
    same_cell = [item for item in view.errors if item[0] == row_id and item[2] == "Qual상태"]
    assert len(same_cell) == 1 and "모름" not in same_cell[0][3]
    assert view.marks[row_id].errors[eg.COLUMN_INDEX["Qual상태"]] == same_cell[0][3]
    assert eg.change_counts(view).errors == len(view.errors)
    plain = _view(frames, saved, issues=issues)
    assert eg.change_counts(view).errors == eg.change_counts(plain).errors, (
        "규칙 오류 대신 초안 오류"
    )


def test_locks_follow_module_groups_stale_sessions_and_assumption_layout() -> None:
    saved = _saved()
    frames = _copy(saved)
    master = frames[1]
    master.loc[[0, 1], "Main 설비"] = "GRP-1"
    master.loc[1, "공정소분류"] = master.loc[0, "공정소분류"]
    extra = master.iloc[[5]].assign(설비명="NEW-1")
    frames = (frames[0], pd.concat([master, extra], ignore_index=True), frames[2])
    context = eg.GridContext(base="t", stale_lock="낡음", layout_lock="가정 배치")
    view = _view(frames, saved, context=context)
    module_row, plain_row = view.index.ids[0], view.index.ids[3]
    assert view.locks[module_row] == ("stale", "layout", "module")
    assert view.locks[plain_row] == ("stale", "layout")
    assert view.locks["n:NEW-1"] == ("stale", "place"), "새 호기는 자리 없이(S2)"
    assert eg.lock_of(view, module_row, "X좌표") == "layout"
    assert eg.lock_of(view, plain_row, "반입일정") == "stale"
    for column in ("동", "층", "X좌표", "Y좌표"):
        assert eg.lock_of(view, "n:NEW-1", column) == "place", column
    for column in ("Xsize", "Ysize", "레이아웃표시"):
        assert eg.lock_of(view, "n:NEW-1", column) is None, "크기·레이아웃표시는 받는다"
    assert context.lock_reasons()["stale"] == "낡음"
    assert context.lock_reasons()["place"] == context.lock_reasons()["layout"] == "가정 배치"


def test_grid_data_is_plain_json_in_loaded_order() -> None:
    saved = _saved()
    view = _view(_copy(saved), saved, alerts={saved[1].iloc[1]["설비명"]: "Qual 미확인"})
    loaded = list(view.index.ids[:3])[::-1] + ["s:NOPE"]
    data = eg.grid_data(
        view, loaded, toast={"id": 1, "text": "t", "undo": "m#3"}, undo_top="m#3", open_id=loaded[1]
    )
    json.dumps(data, allow_nan=False)
    assert data["toast"] == {"id": 1, "text": "t", "undo": "m#3"}
    assert data["open"] == loaded[1], "상세에 연 줄(띠)"
    assert eg.grid_data(view, loaded, open_id="s:NOPE")["open"] is None
    assert [row["id"] for row in data["rows"]] == loaded[:3]
    assert data["view"] == eg.view_token(loaded[:3])
    assert data["counts"] == {"loaded": 3, "total": len(saved[1]), "limit": eg.GRID_ROW_LIMIT}
    assert [column["name"] for column in data["columns"]] == list(EQUIPMENT_COLUMNS)
    assert data["rows"][1]["alert"] == "Qual 미확인"
    assert all(len(row["values"]) == 39 for row in data["rows"])
    assert data["colSets"][0][3] == [eg.COLUMN_INDEX[c] for c in eg.COLUMN_SETS[0].columns]
    assert eg.grid_data(view, loaded) == eg.grid_data(view, loaded), "같은 입력이면 같은 data"


def test_a_toast_keeps_its_undo_only_while_its_step_is_on_top() -> None:
    """토스트 뒤에 토스트 없는 조작(칸 고침)이 쌓이면 「되돌리기」 를 거둔다 — 누르면 다른 단계가
    되돌아간다."""
    toast = {"id": 4, "text": "값 넣기 — 3칸 바뀜", "undo": "m#7"}
    assert eg.toast_payload(toast, "m#7") == toast
    assert eg.toast_payload(toast, "m#8") == {**toast, "undo": None}
    assert eg.toast_payload(toast, None) == {**toast, "undo": None}
    assert eg.toast_payload({**toast, "undo": True}, "m#7") == {**toast, "undo": None}, "표지만"
    assert eg.toast_payload(None, "m#7") is None


def test_view_token_changes_with_order() -> None:
    assert eg.view_token(["a", "b"]) != eg.view_token(["b", "a"])
    assert eg.view_token(["a", "b"]) == eg.view_token(["a", "b"])


def test_loader_data_encodes_names_conditions_and_processes() -> None:
    saved = _saved()
    frames = _copy(saved)
    master = frames[1]
    master.loc[0, "공정소분류"] = None
    master.loc[0, "설비명"] = "RENAMED"
    view = _view(
        frames, saved, renames=PendingRenames(units={"RENAMED": saved[1].iloc[0]["설비명"]})
    )
    data = eg.loader_data(view, [view.index.ids[1]], alert_ids=[view.index.ids[2], "s:NOPE"])
    json.dumps(data, allow_nan=False)
    assert data["names"][0] == "RENAMED"
    assert data["ids"] == {"0": view.index.ids[0]}, "id 가 s:+이름 이 아닌 자리만 싣는다"
    assert data["alertIds"] == [view.index.ids[2]]
    conditions = data["conditions"]
    assert conditions["columns"] == list(eg.CONDITION_COLUMNS)
    for k, column in enumerate(eg.CONDITION_COLUMNS):
        values = conditions["values"][k]
        width = conditions["widths"][k]
        text = conditions["codes"][k]
        assert len(text) == width * len(data["names"])
        decoded = [values[_decode(text[at : at + width])] for at in range(0, len(text), width)]
        position = eg.COLUMN_INDEX[column]
        assert decoded == [view.values[row_id][position] for row_id in view.index.live]
    assert data["processes"][-1] == [eg.BLANK_LABEL, 1]
    assert sum(count for _, count in data["processes"]) == len(data["names"])


def _decode(text: str) -> int:
    code = 0
    for char in text:
        code = code * len(eg.CODE_ALPHABET) + eg.CODE_ALPHABET.index(char)
    return code


def test_code_width_grows_past_sixty_four_values() -> None:
    assert eg.code_width(1) == 1 and eg.code_width(64) == 1 and eg.code_width(65) == 2
    assert eg.encode_codes([0, 63, 64], 2) == "00" + "0_" + "10"


def test_detail_data_carries_meta_downtime_and_the_delete_lock() -> None:
    saved = _saved()
    downtime = saved[2]
    owner = str(downtime.iloc[0]["설비명"])
    view = _view(_copy(saved), saved, context=eg.GridContext(base="t", delete_lock="낡음"))
    row_id = "s:" + owner
    data = eg.detail_data(view, row_id)
    json.dumps(data, allow_nan=False)
    unit = data["unit"]
    assert unit["id"] == row_id
    assert unit["downtime"][0][0] == eg.cell_text(downtime.iloc[0]["비가동유형"])
    assert unit["deletable"] is False and unit["deleteLock"] == "낡음"
    assert data["groups"][0][4][0] == eg.NAME_INDEX
    assert eg.detail_data(view, "s:NOPE")["unit"] is None


def test_side_mounts_carry_their_own_ack_and_toast() -> None:
    """오른쪽 칸도 출납을 보낸다 — ack 가 없으면 반영된 op 를 들고 있다가 다시 보내고, 상세 「이
    호기 지우기」 토스트·되돌리기를 그릴 자리가 없다."""
    saved = _saved()
    view = _view(_copy(saved), saved)
    ack = {"mount": "m-side", "seq": 4}
    toast = {"id": 2, "text": "1대를 지울 목록에 넣었습니다", "undo": "m-side#4"}
    for data in (
        eg.detail_data(view, view.index.ids[0], ack=ack, toast=toast, undo_top="m-side#4"),
        eg.changes_data(view, ack=ack, toast=toast, undo_top="m-side#4"),
    ):
        json.dumps(data, allow_nan=False)
        assert data["ack"] == ack and data["toast"] == toast
    assert eg.detail_data(view, None)["ack"] == {} and eg.changes_data(view)["toast"] is None
    stale = eg.changes_data(view, ack=ack, toast=toast, undo_top="other#1")
    assert stale["toast"]["undo"] is None


def test_changes_data_counts_and_caps_lines() -> None:
    saved = _saved()
    frames = _copy(saved)
    frames[1].loc[:, "메모1"] = "x"
    frames = (frames[0], frames[1].drop(index=0).reset_index(drop=True), frames[2])
    view = _view(frames, saved, overlay={})
    data = eg.changes_data(view)
    json.dumps(data, allow_nan=False)
    total = len(saved[1]) - 1
    assert data["counts"] == {"cells": total, "new": 0, "deleted": 1, "errors": 0}
    shown = sum(len(unit["lines"]) for unit in data["units"])
    assert shown == min(total, eg.CHANGE_LINE_LIMIT) and data["moreLines"] == total - shown
    assert data["units"][-1]["tag"] == "deleted"
    line = data["units"][0]["lines"][0]
    assert line[0] == "메모1" and line[1] == "common" and line[3] == "x"
