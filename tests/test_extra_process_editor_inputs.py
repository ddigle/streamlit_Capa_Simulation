# Purpose: 부대공정 판 편집기의 기준 데이터 도우미(참조공정 후보 · 기본값 · 따라가기 미리보기)와
# 입력 문제 · 알림을 내장 합성 시드와 합성 DEMO 판으로 본다.

"""부대공정 판 편집기 — 입력 돕기(`services/extra_process_editor.py` 의 `editor_context` ·
`reference_choices` · `line_defaults` · `follow_preview` · `input_problems` · `editor_warnings`).

기준 데이터는 내장 합성 시드(`services/builtin_seed.py` — 공정 셋 · 2026년 12달)에 소요기준이 섞인
공정 · BOX 공정 · 옛 판 공정 줄을 더한 사본이다. 입력 문제는 창을 받지 않는다 — 같은 모형이면 어느
시나리오에서든 같은 목록이다.
"""

from __future__ import annotations

import pandas as pd
from extra_process_fixtures import AOI, BOND, edited, set_cell, template_files

from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.extra_process_editor import (
    EQUIPMENT,
    LENT_COLUMN,
    OWNED_COLUMN,
    PROCESS_TABLE,
    PRODUCTIVITY,
    RATE,
    RUN_RATE_COLUMN,
    UPEH_COLUMN,
    VITAL_COLUMN,
    CellInput,
    CellKey,
    EditorContext,
    LineFields,
    Onward,
    canonical,
    editor_context,
    editor_warnings,
    fold,
    follow_preview,
    input_problems,
    line_defaults,
    line_form,
    model_from_pack,
    reference_choices,
    same_body,
    with_cells,
    with_lines,
)
from capa_simulation.services.extra_process_merge import RULE_REFERENCE, follow_routes
from capa_simulation.services.extra_process_pack import (
    ENGINEERING,
    FORMAT_VERSION,
    MASS,
    ExtraProcessPack,
    PackInfo,
    Period,
    read_pack_files,
)

Tables = dict[str, pd.DataFrame]
YEAR_2026 = tuple(range(202601, 202613))


def _seed() -> Tables:
    return {
        name: frame.copy() for name, frame in build_builtin_seed_dataset().reference_tables.items()
    }


def _with_extra_rows(seed: Tables) -> Tables:
    """시드 `RQ_REQB` 에 소요기준이 섞인 공정 · BOX 공정 · 옛 판 공정(대소문자 다른 BDQ 행 포함)."""
    reqb = seed["RQ_REQB"]
    chip = reqb.loc[reqb["공정"].eq("DEMO_Chip_Attach")]
    mixed = pd.concat(
        [chip.assign(공정="DEMO_Mixed"), chip.assign(공정="DEMO_Mixed", 소요기준="PKG")]
    )
    box = chip.assign(공정="DEMO_Boxing", 소요기준="BOX")
    old = chip.assign(공정="DEMO_Old_Extra ", STEP_SEQ="DEMO-P900")
    old_bdq = chip.head(1).assign(공정="demo_old_extra")
    tables = dict(seed)
    tables["RQ_REQB"] = pd.concat([reqb, mixed, box, old, old_bdq], ignore_index=True)
    return tables


def _context() -> EditorContext:
    return editor_context(_with_extra_rows(_seed()), ("DEMO_Old_Extra",))


def _editor_pack() -> ExtraProcessPack:
    files = edited(
        template_files(),
        "03_productivity.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "WF측정률", "1"),
    )
    reading = read_pack_files(files)
    assert reading.pack is not None
    return reading.pack


# --------------------------------------------------------------------------- 기준 데이터 도우미


def test_reference_choices_leave_out_mixed_box_stripped_and_extra_processes() -> None:
    """R-02 · V-06 — 후보는 소요기준이 정확히 하나(PKG · CHIP · WF)인 공정, 옛 판 줄과 지금 편집기
    줄 이름(대소문자 무시)은 뺀다."""
    tables = _with_extra_rows(_seed())
    before = {name: frame.copy() for name, frame in tables.items()}
    context = editor_context(tables, ("DEMO_Old_Extra",))
    clash = with_lines(model_from_pack(None), [("n1", LineFields(name="demo_final_test"))])

    names = [choice.name for choice in reference_choices(context, clash)]
    chips = [choice.name for choice in reference_choices(context, clash, basis="chip")]

    assert set(context.references) == {
        "DEMO_Chip_Attach",
        "DEMO_Wafer_Inspect",
        "DEMO_Final_Test",
        "demo_old_extra",
    }
    assert names == ["DEMO_Chip_Attach", "DEMO_Wafer_Inspect", "demo_old_extra"]
    assert chips == ["DEMO_Chip_Attach", "demo_old_extra"]
    # 걷기는 대소문자를 가른다 — 대소문자만 다른 BDQ 행은 남아 R-01 이름에도 선다.
    assert "demo_old_extra" in context.bdq_names
    assert context.months == YEAR_2026
    for name, frame in tables.items():
        pd.testing.assert_frame_equal(frame, before[name])


def test_a_reference_brings_its_basis_area_modules_and_unique_step_pairs() -> None:
    """결정3 · 제안 e · f — 고유 (STEP, MCP) 조합, Area 기본값, 모듈수 기본값, 시작월 = 첫 계획
    월."""
    seed = _seed()
    reqb = seed["RQ_REQB"]
    second = reqb.loc[reqb["공정"].eq("DEMO_Chip_Attach")].assign(STEP_SEQ="DEMO-P101")
    seed["RQ_REQB"] = pd.concat([reqb, second], ignore_index=True)
    context = editor_context(seed)

    choice = context.references["DEMO_Chip_Attach"]
    defaults = line_defaults(context, "DEMO_Chip_Attach")
    unknown = line_defaults(context, "DEMO_Nowhere")

    assert (choice.basis, choice.area, choice.modules) == ("CHIP", "Main", 4.0)
    assert choice.steps == (("DEMO-P100", "DEMO-1A"), ("DEMO-P101", "DEMO-1A"))
    assert defaults == LineFields(
        area="Main",
        basis="CHIP",
        modules=4.0,
        reference="DEMO_Chip_Attach",
        step="DEMO-P100",
        mcp="DEMO-1A",
        start=202601,
    )
    assert context.references["DEMO_Final_Test"].area == "MI"
    assert unknown == LineFields(reference="DEMO_Nowhere", start=202601)


def test_the_line_form_follows_the_reference_and_fills_a_lone_step_pair() -> None:
    """R3 — 공정 표 줄의 양식은 그 줄의 지금 참조공정 글을 따른다. STEP · MCP 는 고유 조합이 하나일
    때만 채우고 둘 이상 · 후보 밖이면 빈칸이다(입력 문제로 고른다). 참조공정 칸 자체는 펼친 값(새
    줄은 빈칸) — 고른 참조는 초안이라 양식에 굽지 않는다. 펼친 줄은 참조가 같으면 펼친 값 그대로,
    바뀌면 소요기준 · STEP · MCP 만 바뀐다."""
    seed = _seed()
    reqb = seed["RQ_REQB"]
    second = reqb.loc[reqb["공정"].eq("DEMO_Chip_Attach")].assign(STEP_SEQ="DEMO-P101")
    seed["RQ_REQB"] = pd.concat([reqb, second], ignore_index=True)
    context = editor_context(seed)
    opened = LineFields(
        name="DEMO_Opened",
        area="MI",
        basis="CHIP",
        modules=3.0,
        memo="DEMO 메모",
        reference="DEMO_Off_List",
        step="DEMO-P900",
        mcp="DEMO-9A",
        start=202603,
        end=None,
    )

    assert line_form(context, "") == LineFields(start=202601)
    assert line_form(context, "DEMO_Nowhere") == LineFields(start=202601)
    assert line_form(context, " DEMO_Final_Test ") == LineFields(
        area="MI", basis="CHIP", modules=4.0, step="DEMO-P300", mcp="DEMO-3A", start=202601
    )
    assert line_form(context, "DEMO_Chip_Attach") == LineFields(
        area="Main", basis="CHIP", modules=4.0, start=202601
    ), "조합이 둘이면 STEP · MCP 빈칸"

    assert line_form(context, "DEMO_Off_List", opened) is opened, "펼친 참조(후보 밖도) 그대로"
    assert line_form(context, "DEMO_Wafer_Inspect", opened) == LineFields(
        **{**vars(opened), "basis": "WF", "step": "DEMO-P200", "mcp": "DEMO-2A"}
    )
    assert line_form(context, "DEMO_Chip_Attach", opened) == LineFields(
        **{**vars(opened), "step": "", "mcp": ""}
    )
    assert line_form(context, "DEMO_Elsewhere", opened) == LineFields(
        **{**vars(opened), "step": "", "mcp": ""}
    ), "후보 밖 참조로 바꾸면 소요기준은 펼친 값, 조합은 빈칸"


def test_the_follow_preview_counts_match_the_merge_body() -> None:
    """결정2 — 미리보기 수는 합치기와 같은 몸통(`follow_routes`)에서 온다. PKG 의 Buffer 밖 줄은
    숨기지 않고 셈 밖 표지를 단다."""
    seed = _seed()
    chip = seed["RQ_REQB"].loc[seed["RQ_REQB"]["공정"].eq("DEMO_Chip_Attach")]
    pkg = chip.assign(공정="DEMO_Pack", 소요기준="PKG", STEP_SEQ="DEMO-P400")
    pkg.loc[pkg["제품정보"].eq("DEMO PRODUCT A"), "WF 구분"] = "BUFFER"
    seed["RQ_REQB"] = pd.concat([seed["RQ_REQB"], pkg], ignore_index=True)
    period = Period(202604, None)

    preview = follow_preview(seed, "DEMO_Pack", "pkg", period)
    body = follow_routes(seed, "DEMO_Pack", "PKG", period)
    refused = follow_preview(seed, "DEMO_Chip_Attach", "WF", period)

    assert (preview.rows, preview.uncounted, preview.refused) == (
        len(body.rows),
        body.uncounted,
        None,
    )
    assert sum(group.rows for group in preview.groups) == preview.rows
    assert sum(group.rows for group in preview.groups if not group.counted) == preview.uncounted
    assert {group.first for group in preview.groups} == {202604}
    assert preview.products == 2
    assert refused.refused is not None and refused.refused[0] == RULE_REFERENCE
    assert refused.groups == () and refused.rows == 0


# --------------------------------------------------------------------------- 입력 문제(I6)


def test_an_empty_editor_says_there_is_no_process() -> None:
    problems = input_problems(model_from_pack(None))

    assert [(problem.table, problem.reason) for problem in problems] == [("", "공정이 하나도 없음")]


def test_input_problems_name_the_cells_the_gate_would_refuse_whatever_the_window() -> None:
    """I6 — 빈칸 · 0 이하 · 글 · 대여 > 보유 · 01 · 02 칸을 예외 없이 줄 · 칸 · 달로 모은다."""
    line = LineFields(
        name="DEMO_New_Sort",
        area="main",
        basis="CHIP",
        modules=0,
        reference="DEMO_New_Bond",
        step="DEMO-P110",
        mcp="",
        start=202601,
        end=202606,
    )
    base = _editor_pack()
    model = model_from_pack(base)
    rows = [(item.line_id, item.fields) for item in model.lines]
    model = with_lines(model, [*rows, ("n1", line)])
    cells: dict[CellKey, CellInput] = {}
    for month in range(202601, 202607):
        cells[(("n1", PRODUCTIVITY, MASS, UPEH_COLUMN), month)] = 100.0
        cells[(("n1", EQUIPMENT, "", OWNED_COLUMN), month)] = 2.0
        cells[(("n1", RATE, MASS, RUN_RATE_COLUMN), month)] = 0.9
        cells[(("n1", RATE, MASS, VITAL_COLUMN), month)] = 1.0
    cells[(("n1", PRODUCTIVITY, ENGINEERING, UPEH_COLUMN), 202603)] = 0.0
    cells[(("n1", EQUIPMENT, "", LENT_COLUMN), 202604)] = 3.0
    cells[(("n1", RATE, MASS, VITAL_COLUMN), 202605)] = "x"
    model = with_cells(model, cells)

    problems = {
        (problem.table, problem.column, problem.reason, problem.months)
        for problem in input_problems(model)
        if problem.line_id == "n1"
    }

    assert problems == {
        (PROCESS_TABLE, "모듈수", "모듈수는 0 보다 커야 함", ()),
        (PROCESS_TABLE, "참조공정", "부대공정끼리는 참조하지 않음", ()),
        (PROCESS_TABLE, "STEP_SEQ", "STEP_SEQ · MCP_SEQ 빈칸", ()),
        (PRODUCTIVITY, UPEH_COLUMN, "0 보다 커야 함", (202603,)),
        # 대여는 고친 달부터 앞 달 값을 이어 쓴다(바탕 없는 새 줄) — 202604 ~ 202606.
        (EQUIPMENT, LENT_COLUMN, "대여 > 보유", (202604, 202605, 202606)),
        (RATE, VITAL_COLUMN, "수가 아님", (202605,)),
    }
    # 관문도 같은 칸들을 거절한다(입력 문제는 돕기만 한다).
    result = canonical(fold(model, PackInfo(FORMAT_VERSION, 2)).rows)
    assert result.reading.pack is None
    assert {"V-03", "V-06", "V-10", "V-11", "V-14"} <= {
        problem.code for problem in result.reading.problems
    }


def test_duplicate_names_and_unreadable_months_are_input_problems() -> None:
    model = with_lines(
        model_from_pack(None),
        [
            ("n1", LineFields(name="DEMO_A", start="2026-01")),
            ("n2", LineFields(name="demo_a", start=202603, end=202601)),
        ],
    )

    reasons = {(problem.line_id, problem.reason) for problem in input_problems(model)}

    assert ("n1", "월 꼴(YYYYMM)이 아님") in reasons
    assert ("n2", "공정 중복(대소문자 무시)") in reasons
    assert ("n2", "끝월이 시작월보다 앞") in reasons


# --------------------------------------------------------------------------- 알림


def test_warnings_tell_r01_r02_closed_ends_windows_rates_and_ignored_cells() -> None:
    base = _editor_pack()
    model = model_from_pack(base)
    bond, aoi = (line.line_id for line in model.lines)
    lines = [
        (
            bond,
            LineFields(
                name=BOND,
                area="Main",
                basis="CHIP",
                modules=2,
                reference="DEMO_Nowhere",
                step="DEMO-P150",
                mcp="DEMO-1A",
                start=202601,
                end=202609,
            ),
        ),
        (aoi, model.lines[1].fields),
        (
            "n1",
            LineFields(
                name="DEMO_Wafer_Inspect",
                area="Main",
                basis="CHIP",
                modules=1,
                reference="DEMO_Wafer_Inspect",
                step="DEMO-P210",
                mcp="DEMO-2B",
                start=202801,
            ),
        ),
    ]
    model = with_lines(model, lines)
    model = with_cells(
        model,
        {
            ((bond, RATE, MASS, RUN_RATE_COLUMN), 202603): 1.2,
            ((bond, PRODUCTIVITY, MASS, UPEH_COLUMN), 202611): 1.0,
            (("gone", EQUIPMENT, "", OWNED_COLUMN), 202601): 1.0,
        },
    )

    warnings = {(item.line_id, item.code) for item in editor_warnings(model, _context())}
    texts = {item.text for item in editor_warnings(model, _context())}

    assert warnings == {
        (bond, "R-02"),
        (bond, "끝월"),
        (bond, "효율"),
        ("n1", "R-01"),
        ("n1", "R-02"),
        ("n1", "조합"),
        ("n1", "창"),
        (None, "고침"),
    }
    assert "경로 끝월 202609 뒤 계획 달은 계산에 들지 않음" in texts
    assert "판에 안 든 칸 입력 2칸" in texts


def test_a_step_mcp_pair_outside_the_reference_combos_is_a_warning_not_a_block() -> None:
    """STEP · MCP 를 칸마다 따로 고르면 두 칸이 다른 조합에서 온 짝(MIXED)이 되고, 참조를 바꾼
    뒤 친 짝이 남으면 새 참조 조합에 없는 짝(STALE)이 된다 — 둘 다 「조합」 알림이다(막지 않음,
    직접 적는 조합도 받는다). 참조 · STEP · MCP 가 펼친 값 그대로인 줄(`b1` — 펼친 짝이 지금
    조합에 없음)은 이 편집기에서 고른 짝이 아니라 빼고, 그 줄도 짝 한 칸을 바꾸면 선다."""
    seed = _seed()
    reqb = seed["RQ_REQB"]
    second = reqb.loc[reqb["공정"].eq("DEMO_Chip_Attach")].assign(
        STEP_SEQ="DEMO-P101", MCP_SEQ="DEMO-1B"
    )
    seed["RQ_REQB"] = pd.concat([reqb, second], ignore_index=True)
    context = editor_context(seed)
    model = model_from_pack(_editor_pack())
    bond, aoi = model.lines

    def line(reference: str, step: str, mcp: str, name: str) -> LineFields:
        return LineFields(
            name=name,
            area="Main",
            basis="CHIP",
            modules=1,
            reference=reference,
            step=step,
            mcp=mcp,
            start=202601,
        )

    def pairs(*rows: tuple[str, LineFields]) -> set[str | None]:
        found = editor_warnings(with_lines(model, [*rows, (aoi.line_id, aoi.fields)]), context)
        return {item.line_id for item in found if item.code == "조합"}

    untouched = (bond.line_id, bond.fields)
    mixed = ("n1", line("DEMO_Chip_Attach", "DEMO-P100", "DEMO-1B", "DEMO_Mixed_Pair"))
    whole = ("n2", line("DEMO_Chip_Attach", "DEMO-P101", "DEMO-1B", "DEMO_Whole_Pair"))
    stale = ("n3", line("DEMO_Final_Test", "DEMO-P101", "DEMO-1B", "DEMO_Stale_Pair"))
    half = ("n4", line("DEMO_Final_Test", "DEMO-P101", "", "DEMO_Half_Pair"))
    moved = (bond.line_id, LineFields(**{**vars(bond.fields), "mcp": "DEMO-1B"}))

    assert bond.fields.step == "DEMO-P150", "펼친 짝은 지금 조합 밖"
    assert pairs(untouched, mixed, whole, stale, half) == {"n1", "n3"}
    assert pairs(moved) == {bond.line_id}
    texts = {item.text for item in editor_warnings(with_lines(model, [mixed]), context)}
    assert "STEP · MCP 가 참조공정 조합에 없음 — 직접 적은 조합인지 확인" in texts


def test_a_reference_missing_from_the_scenario_still_folds_back_untouched() -> None:
    """C12 — 바탕 참조공정이 지금 시나리오에 없어도 모형이 그 글을 들고 있어 안 고친 판은 같다."""
    base = _editor_pack()
    seed = _seed()
    reqb = seed["RQ_REQB"]
    seed["RQ_REQB"] = reqb.loc[~reqb["공정"].eq("DEMO_Chip_Attach")].reset_index(drop=True)
    context = editor_context(seed)
    model = model_from_pack(base)

    result = canonical(fold(model, PackInfo(FORMAT_VERSION, 2)).rows)

    assert result.reading.pack is not None and same_body(result.reading.pack, base)
    assert ("b1", "R-02") in {(item.line_id, item.code) for item in editor_warnings(model, context)}
    assert AOI not in {item.line_id for item in editor_warnings(model, context)}


def test_an_onward_cell_for_a_new_line_is_editable_from_the_first_after_month() -> None:
    """결정 B — 바탕 없는 새 줄의 이후 칸은 한 값이라 고칠 수 있고, 고치면 그 달부터 끝까지다."""
    model = with_lines(
        model_from_pack(None),
        [
            (
                "n1",
                LineFields(
                    name="DEMO_New_Sort",
                    area="Main",
                    basis="CHIP",
                    modules=1,
                    reference="DEMO_Chip_Attach",
                    step="DEMO-P110",
                    mcp="DEMO-1B",
                    start=202601,
                ),
            )
        ],
    )
    cells: dict[CellKey, CellInput] = {}
    for month in YEAR_2026:
        cells[(("n1", PRODUCTIVITY, MASS, UPEH_COLUMN), month)] = 100.0
        cells[(("n1", EQUIPMENT, "", OWNED_COLUMN), month)] = 1.0
        cells[(("n1", RATE, MASS, RUN_RATE_COLUMN), month)] = 1.0
        cells[(("n1", RATE, MASS, VITAL_COLUMN), month)] = 1.0
    cells[(("n1", PRODUCTIVITY, MASS, UPEH_COLUMN), Onward(202701))] = 120.0
    model = with_cells(model, cells)

    assert input_problems(model) == ()
    result = canonical(fold(model, PackInfo(FORMAT_VERSION, 1)).rows)
    assert result.reading.pack is not None
    rows = [
        (row.mass_class, row.period.start, row.period.end)
        for row in result.reading.pack.productivity
    ]
    # ER 은 같은 달 양산을 따르므로 이후 칸 고침도 「모두」 한 줄이다.
    assert rows == [("모두", 202601, 202612), ("모두", 202701, None)]
