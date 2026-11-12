# Purpose: Space 「호기 정보」 창 칸 고치기의 잠금 · 다듬기 · 같이 쓰기 · 규칙 판정을 본다.

"""배치 편집기 「호기 정보」 창에서 고친 칸(2026-11-12 Space 시안 보드 답 5-4 ~ 5-6)은 설비
마스터 표와 같은 칸 · 같은 잠금 · 같은 규칙으로 판정한다(`services/space_sheet_edit`). 규칙은 받은
칸을 모두 얹은 마지막 상태와 고치기 앞을 견줘 **새로** 생긴 막는 결과만 그 칸에 짚는다 — 입력
차례를 타지 않고 다른 호기의 기존 오류로 막히지 않는다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest
from test_space_layout_edit import _master

from capa_simulation.components.space_layout import FLOOR_TABLE_COLUMNS
from capa_simulation.services import equipment_grid as eg
from capa_simulation.services import space_sheet_edit
from capa_simulation.services.equipment_validation import (
    CellParseError,
    coerce_master_cell,
    equipment_master_issues,
    prepare_equipment_master,
)
from capa_simulation.services.space_layout_edit import PendingRenames
from capa_simulation.services.space_sheet_edit import (
    RULE_FIXED,
    RULE_SIBLING_LOCKED,
    RULE_SPLIT,
    SHEET_FIXED_LOCKS,
    SheetCell,
    blocked_line,
    changed_cell_count,
    check_sheet_cells,
    editable_columns,
    parse_sheet_cells,
    sheet_edit_data,
    unit_lock_kinds,
    verdict_payload,
)
from capa_simulation.services.space_unit_sheet import MAX_TEXT_LENGTH, unit_sheet

TODAY = date(2026, 11, 13)
COLUMNS = FLOOR_TABLE_COLUMNS


def _fleet() -> pd.DataFrame:
    """EQ-01 · EQ-02(C1 1F) + 모듈 묶음 M 셋(C1 1F — 셋째는 레이아웃표시 N 인 숨은 모듈) + 한
    줄 묶음 LONE."""
    return prepare_equipment_master(
        _master(
            {"설비명": "M-A", "Main 설비": "M", "X좌표": 50, "Y좌표": 30, "Xsize": 6, "Ysize": 3.5},
            {"설비명": "M-B", "Main 설비": "M", "X좌표": 56, "Y좌표": 30, "Xsize": 6, "Ysize": 3.5},
            {
                "설비명": "M-C",
                "Main 설비": "M",
                "레이아웃표시": "N",
                "X좌표": 50,
                "Y좌표": 33.5,
                "Xsize": 6,
                "Ysize": 3.5,
            },
            {"설비명": "L-A", "Main 설비": "LONE", "X좌표": 70, "Y좌표": 40},
        )
    )


def _check(
    master: pd.DataFrame,
    *cells: tuple[str, str, str],
    context: eg.GridContext | None = None,
    today: date | None = TODAY,
) -> space_sheet_edit.SheetCheck:
    context = context or eg.GridContext(base="t")
    locks = unit_lock_kinds(context, master, master, PendingRenames())
    return check_sheet_cells(
        master,
        [SheetCell(*cell) for cell in cells],
        columns=COLUMNS,
        context=context,
        locks=locks,
        today=today,
    )


def _rules(check: space_sheet_edit.SheetCheck) -> list[str]:
    return [verdict.rule for verdict in check.verdicts]


def _cell(frame: pd.DataFrame, unit: str, column: str) -> str:
    row = frame.loc[frame["설비명"].eq(unit)].iloc[0]
    return eg.cell_text(row[column])


# ------------------------------------------------------------------ 일정 차례(5-6 시안 원인)


def test_an_arrival_before_logistics_is_blocked_and_the_draft_is_untouched() -> None:
    master = _fleet()
    before = master.copy()

    check = _check(master, ("EQ-01", "반입일정", "2026-08-01"))

    assert _rules(check) == ["schedule_order"]
    assert "일정 순서가 올바르지 않습니다" in check.blocked[0].message
    assert not check.ok and check.written == ()
    pd.testing.assert_frame_equal(master, before)
    good = _check(master, ("EQ-01", "반입일정", "2026-08-05"))
    assert good.ok
    assert _cell(good.master, "EQ-01", "반입일정") == "2026-08-05"
    assert good.written == (("EQ-01", "반입일정"),)


def test_the_order_of_typing_does_not_matter_only_the_last_state() -> None:
    """물류 · 반입을 함께 뒤로 미룰 때 물류를 먼저 넣어도 마지막 조합이 맞으면 막지 않는다."""
    master = _fleet()

    both = _check(
        master,
        ("EQ-01", "물류일정", "2026-08-05"),
        ("EQ-01", "반입일정", "2026-08-06"),
    )
    assert both.ok

    alone = _check(master, ("EQ-01", "물류일정", "2026-08-05"))
    # 결과 칸은 반입일정이어도 고친 물류 칸을 짚는다.
    assert _rules(alone) == ["schedule_order"]
    assert alone.blocked[0].cell.column == "물류일정"
    assert alone.blocked[0].message.startswith("EQ-01 반입일정 — ")


def test_an_actual_after_today_is_blocked_like_the_save() -> None:
    """구멍 1 — 창 판정은 표와 같은 인자(오늘)로 돈다. 오늘 없이 돌면 받는다(읽기 규칙만)."""
    master = _fleet()

    check = _check(master, ("EQ-01", "반입실적", "2026-12-12"))
    assert _rules(check) == ["actual_future"]
    assert _check(master, ("EQ-01", "반입실적", "2026-12-12"), today=None).ok


def test_another_units_old_error_does_not_block_this_cell() -> None:
    """구멍 2 — 다른 호기의 기존 오류(빈 공정소분류)는 앞뒤 차이로 가려 이 칸을 막지 않는다."""
    master = _fleet()
    master.loc[master["설비명"].eq("EQ-02"), "공정소분류"] = pd.NA
    assert any(
        issue.unit == "EQ-02" and issue.blocking
        for issue in equipment_master_issues(master, today=TODAY)
    )

    assert _check(master, ("EQ-01", "반입상태", "확정")).ok


def test_the_window_blocks_the_same_rule_the_master_grid_shows() -> None:
    """같은 판정 — 칸을 얹은 표에 표와 같은 인자로 규칙 표를 돌린 결과가 그 칸의 막음과 같다."""
    master = _fleet()
    cases = [
        ("EQ-01", "반입일정", "2026-08-01"),
        ("EQ-01", "반입실적", "2026-12-12"),
        ("EQ-02", "공정소분류", ""),
        ("EQ-01", "Qual상태", ""),
    ]
    for unit, column, text in cases:
        check = _check(master, (unit, column, text))
        after = master.copy()
        value = coerce_master_cell(column, text)
        position = int(after.index[after["설비명"].eq(unit)][0])
        eg.store_cell(after, position, column, value)
        before_keys = {
            (issue.position, issue.column, issue.rule)
            for issue in equipment_master_issues(master, today=TODAY)
        }
        fresh = {
            issue.rule
            for issue in equipment_master_issues(after, today=TODAY)
            if issue.blocking
            and issue.position == position
            and (issue.position, issue.column, issue.rule) not in before_keys
        }
        assert fresh, (unit, column)
        assert {verdict.rule for verdict in check.blocked} <= fresh, (unit, column)
        assert check.blocked, (unit, column)


# ------------------------------------------------------------------ 잠금 · 다듬기


@pytest.mark.parametrize("column", ["설비명", "동", "층", "단계", "도면"])
def test_window_only_locks_are_refused_by_the_server(column: str) -> None:
    """동 · 층은 배치 잠금이 없어도 서버가 막는다(표의 `_locked` 는 받는다)."""
    check = _check(_fleet(), ("EQ-01", column, "X"))
    assert _rules(check) == [RULE_FIXED]
    assert check.blocked[0].message == SHEET_FIXED_LOCKS[column]


def test_a_stale_session_locks_the_schedule_cells_like_the_grid() -> None:
    master = _fleet()
    context = eg.GridContext(base="t", stale_lock="낡은 세션 — 일정은 최신에서")
    check = _check(
        master,
        ("EQ-01", "반입일정", "2026-08-05"),
        ("EQ-01", "반입상태", "확정"),
        context=context,
    )
    assert [verdict.blocked for verdict in check.verdicts] == [True, False]
    assert check.blocked[0].message == "낡은 세션 — 일정은 최신에서"
    # 표 모양의 잠금 갈래와 같다.
    view = eg.build_grid_view(
        eg.GridSource(
            frames=(pd.DataFrame(), master, pd.DataFrame()),
            saved=(pd.DataFrame(), master, pd.DataFrame()),
        ),
        context,
    )
    row_id = next(row_id for row_id, name in view.names.items() if name == "EQ-01")
    assert eg.lock_of(view, row_id, "반입일정") == "stale"
    assert eg.lock_of(view, row_id, "반입상태") is None


def test_an_unreadable_date_is_blocked_with_the_master_draft_message() -> None:
    check = _check(_fleet(), ("EQ-01", "반입일정", "2027-13-40"))
    parsed = coerce_master_cell("반입일정", "2027-13-40")
    assert isinstance(parsed, CellParseError)
    assert check.blocked[0].message == parsed.message
    assert check.blocked[0].rule == parsed.rule


def test_unknown_columns_and_units_are_refused_not_raised() -> None:
    check = _check(
        _fleet(),
        ("EQ-01", "Maker", "X"),  # 창에 없는 칸
        ("EQ-01", "없는 칸", "X"),
        ("EQ-99", "반입상태", "확정"),
    )
    assert _rules(check) == ["sheet_column", "sheet_column", "sheet_unit"]


# ------------------------------------------------------------------ 묶음 같이 쓰기(답 3-5)


def test_a_shared_cell_follows_every_sibling_even_a_hidden_one() -> None:
    master = _fleet()

    check = _check(master, ("M-A", "공정구분", "PKG"))

    assert check.ok
    assert check.written == (("M-A", "공정구분"), ("M-B", "공정구분"), ("M-C", "공정구분"))
    assert check.followers == (("M-B", "공정구분", "PKG"), ("M-C", "공정구분", "PKG"))
    assert {_cell(check.master, unit, "공정구분") for unit in ("M-A", "M-B", "M-C")} == {"PKG"}
    # 같이 바뀌지 않는 칸 · 한 줄 묶음은 그 줄 하나다.
    single = _check(master, ("M-A", "사용기준", "EDP"), ("L-A", "공정구분", "PKG"))
    assert single.ok and single.followers == ()


def test_different_values_in_one_group_are_blocked_not_picked() -> None:
    check = _check(_fleet(), ("M-A", "공정구분", "PKG"), ("M-B", "공정구분", "TEST"))
    assert _rules(check) == [RULE_SPLIT, RULE_SPLIT]


def test_a_locked_sibling_refuses_the_whole_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """형제 하나라도 잠긴 칸이면 그 쓰기를 통째로 막는다(창에 있는 같이 바뀌는 칸에 걸리는 잠금은
    지금 없어 잠금 표를 바꿔 본다)."""
    monkeypatch.setattr(space_sheet_edit, "LOCK_SETS", {**eg.LOCK_SETS, "test": ("공정구분",)})
    master = _fleet()
    check = check_sheet_cells(
        master,
        [SheetCell("M-A", "공정구분", "PKG")],
        columns=COLUMNS,
        context=eg.GridContext(base="t"),
        locks={"M-C": ("test",)},
        today=TODAY,
    )
    assert _rules(check) == [RULE_SIBLING_LOCKED]
    assert "M 묶음 — 형제 2줄의 공정구분 칸이 잠겨" in check.blocked[0].message
    assert check.written == ()


# ------------------------------------------------------------------ 꼴 · data · 셈


def test_parse_reads_the_cells_and_refuses_bad_shapes() -> None:
    ids = {"EQ-01", "EQ-02"}
    cells = parse_sheet_cells(
        [
            {"id": " EQ-01 ", "col": "반입상태", "text": "계획"},
            {"id": "EQ-02", "col": "투자구분", "text": "양산"},
            {"id": "EQ-01", "col": "반입상태", "text": "확정"},
        ],
        sheet_ids=ids,
    )
    assert cells == (
        SheetCell("EQ-01", "반입상태", "확정"),
        SheetCell("EQ-02", "투자구분", "양산"),
    )
    assert parse_sheet_cells(None, sheet_ids=ids) == ()
    for bad in (
        "x",
        [1],
        [{"id": "EQ-01", "col": "반입상태"}],
        [{"id": "EQ-09", "col": "a", "text": ""}],
    ):
        with pytest.raises(ValueError):
            parse_sheet_cells(bad, sheet_ids=ids)


def test_the_edit_data_carries_full_texts_kinds_locks_and_groups() -> None:
    master = _fleet()
    long_memo = "가" * (MAX_TEXT_LENGTH + 50)
    master.loc[master["설비명"].eq("M-A"), "반입/Qual 이력"] = long_memo
    context = eg.GridContext(base="t", stale_lock="낡음")
    shown = master.loc[master["레이아웃표시"].eq("Y")]
    sheet = unit_sheet(shown, columns=COLUMNS, place_of={})

    data = sheet_edit_data(
        sheet,
        master,
        context=context,
        locks=unit_lock_kinds(context, master, master, PendingRenames()),
    )

    assert data["cols"] == list(editable_columns([c["name"] for c in sheet["columns"]]))
    assert "설비명" in data["fixed"] and "동" in data["fixed"] and "도면" in data["fixed"]
    assert data["kinds"]["반입상태"]["kind"] == "choice"
    assert data["kinds"]["반입일정"]["kind"] == "date"
    assert data["locks"] == {"stale": [c for c in eg.LOCK_SETS["stale"] if c in data["cols"]]}
    assert data["reasons"] == {"stale": "낡음"}
    row = data["rows"]["M-A"]
    assert row["t"][data["cols"].index("반입/Qual 이력")] == long_memo
    assert row["g"] == "M" and row["k"] == ["stale"]
    # 묶음 줄 수는 편집본 전체(숨은 모듈 포함)다.
    assert data["groups"] == {"M": 3}
    assert data["shared"] == ["Area Code", "공정소분류", "공정구분", "투자Capa", "투자구분"]


def test_the_changed_count_follows_renames_and_drops_cells_back_to_saved() -> None:
    saved = _fleet()
    buffer = saved.copy()
    buffer.loc[buffer["설비명"].eq("EQ-01"), "반입상태"] = "확정"
    buffer.loc[buffer["설비명"].eq("EQ-02"), "설비명"] = "EQ-02N"
    buffer.loc[buffer["설비명"].eq("EQ-02N"), "투자구분"] = "개발"
    cells = {("EQ-01", "반입상태"), ("EQ-02N", "투자구분"), ("M-A", "공정구분")}

    assert changed_cell_count(cells, buffer, saved, {"EQ-02N": "EQ-02"}) == 2
    assert changed_cell_count(set(), buffer, saved, {}) == 0


def test_the_payload_and_alert_line_name_what_and_where() -> None:
    check = _check(_fleet(), ("EQ-01", "반입일정", "2026-08-01"), ("M-A", "공정구분", "PKG"))
    payload: dict[str, Any] = verdict_payload(check)
    assert payload["blocked"][0]["id"] == "EQ-01" and payload["blocked"][0]["col"] == "반입일정"
    assert blocked_line(check.blocked[0]).startswith("EQ-01 반입일정 2026-08-01 — ")


# ------------------------------------------------------------------ 잠금 판정 한 벌


@pytest.mark.parametrize(
    "context",
    [
        eg.GridContext(base="t"),
        eg.GridContext(base="t", stale_lock="낡음"),
        eg.GridContext(base="t", layout_lock="배치 잠김"),
        eg.GridContext(base="t", stale_lock="낡음", layout_lock="배치 잠김"),
    ],
)
def test_row_lock_kinds_is_the_one_lock_judgement(context: eg.GridContext) -> None:
    """표 모양 · 출납의 칸 잠금 · 창이 한 판정을 쓴다 — 저장본 호기는 `layout`, 새 호기는 `place`,
    모듈 묶음은 `module`."""
    saved = _fleet()
    buffer = pd.concat(
        [saved, saved.loc[saved["설비명"].eq("EQ-01")].assign(설비명="EQ-NEW")], ignore_index=True
    )
    index = eg.grid_index(buffer, saved, {})
    kinds = eg.row_lock_kinds(context, index, buffer)
    view = eg.build_grid_view(
        eg.GridSource(
            frames=(pd.DataFrame(), buffer, pd.DataFrame()),
            saved=(pd.DataFrame(), saved, pd.DataFrame()),
        ),
        context,
    )
    assert dict(view.locks) == kinds
    new_id = next(row_id for row_id in index.live if row_id.endswith("EQ-NEW"))
    module_id = next(row_id for row_id in index.live if row_id.endswith("M-A"))
    if context.layout_lock:
        assert "place" in kinds[new_id]
        assert "layout" in kinds[module_id]
    assert "module" in kinds[module_id]
    by_name = unit_lock_kinds(context, buffer, saved, PendingRenames())
    assert by_name["M-A"] == kinds[module_id]
