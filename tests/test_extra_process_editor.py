# Purpose: 부대공정 판 편집기 순수 몸통의 불변식 I1 ~ I7 과 반박 검토 반례를 합성 DEMO 판 여러 벌 ·
# 계획 창 여러 개로 본다.

"""부대공정 판 편집기(`services/extra_process_editor.py`).

판은 견본(`tests/fixtures/extra_process/`)을 고친 합성 `DEMO_*` 사본이다. 견본 그대로는 두 공정이
모두 통째 옮김이다 — `DEMO_New_Bond` 는 WF측정률 0.99, `DEMO_New_AOI` 는 지정 꼴 경로 둘. 그래서
편집기 몫 판은 Bond 의 측정률을 1 로 고친 사본에서 시작하고, MI 따라가기 공정(`DEMO_New_Test`)을
더한 사본으로 ST ↔ UPEH 를 본다. 반례 번호(E1 ~ E15 · probe3)는 반박 검토(critique-correct)의 것을
범위 줄임(편집기 몫 · 통째 옮김) · 절대 달 점 고침 아래에서 다시 세운 것이다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import pytest
from extra_process_fixtures import AOI, BOND, Table, edited, set_cell, template_files

from capa_simulation.services.extra_process_editor import (
    CARRY_OTHER_KEY,
    CARRY_PRODUCT_ROWS,
    CARRY_RATIO,
    CARRY_ROUTES,
    CARRY_RUN_DAY,
    CARRY_SPECIFIED,
    EQUIPMENT,
    LENT_COLUMN,
    OWNED_COLUMN,
    PRODUCTIVITY,
    RATE,
    RUN_RATE_COLUMN,
    UPEH_COLUMN,
    VITAL_COLUMN,
    CellInput,
    CellKey,
    EditorModel,
    LineFields,
    Onward,
    RowKey,
    canonical,
    carried_processes,
    effective_edits,
    fold,
    ignored_cells,
    locate,
    model_from_pack,
    month_view,
    redundant_cells,
    same_body,
    value_rows,
    with_cells,
    with_lines,
)
from capa_simulation.services.extra_process_pack import (
    CLASS_EXPANSION,
    ENGINEERING,
    FORMAT_VERSION,
    MASS,
    ExtraProcessPack,
    PackInfo,
    pack_changes,
    pack_to_zip,
    read_pack_files,
)

Files = dict[str, bytes]
P01, P02, P03, P04, P05 = (
    "01_process.csv",
    "02_route.csv",
    "03_productivity.csv",
    "04_equipment_days.csv",
    "05_rate_vital.csv",
)
MI_NAME = "DEMO_New_Test"
NEW_NAME = "DEMO_New_Sort"
YEAR_2026 = tuple(range(202601, 202613))
WINDOWS: dict[str, tuple[int, ...]] = {
    "A 2026": YEAR_2026,
    "B 05-08": (202605, 202606, 202607, 202608),
    "C 07-12": (202607, 202608, 202609, 202610, 202611, 202612),
    "D 01-04": (202601, 202602, 202603, 202604),
    "E 2027": tuple(range(202701, 202713)),
    "F 없음": (),
}
INFO = PackInfo(FORMAT_VERSION, 2, "2026-11-27T09:00:00+09:00", "", "편집기 시험")


# --------------------------------------------------------------------------- 판 만들기


def _pack(files: Files) -> ExtraProcessPack:
    reading = read_pack_files(files)
    assert reading.pack is not None, [problem.text() for problem in reading.problems]
    return reading.pack


def _rows_of(name: str) -> Callable[[Table], Table]:
    def keep_others(rows: Table) -> Table:
        return [rows[0], *(row for row in rows[1:] if row[0] != name)]

    return keep_others


def _replace_rows(files: Files, file: str, name: str, new_rows: Sequence[list[str]]) -> Files:
    """그 공정의 줄을 새 줄로 갈아 끼운 사본(첫 원 줄 자리)."""

    def edit(rows: Table) -> Table:
        out: Table = [rows[0]]
        placed = False
        for row in rows[1:]:
            if row[0] != name:
                out.append(row)
            elif not placed:
                out.extend(list(item) for item in new_rows)
                placed = True
        if not placed:
            out.extend(list(item) for item in new_rows)
        return out

    return edited(files, file, edit)


def _append(files: Files, file: str, new_rows: Sequence[list[str]]) -> Files:
    return edited(files, file, lambda rows: [*rows, *(list(item) for item in new_rows)])


def _editor_files() -> Files:
    """Bond 를 편집기 몫으로(WF측정률 0.99 → 1). AOI 는 통째 옮김(지정 꼴 경로 둘)."""
    return edited(
        template_files(),
        P03,
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "WF측정률", "1"),
    )


def _with_mi(files: Files) -> Files:
    """MI 따라가기 공정 하나를 더한 사본 — ST 1.8(보인 UPEH 33.33) · 1.5, 측정률 빈칸, 대여 빈칸."""
    files = _append(files, P01, [[MI_NAME, "MI", "CHIP", "1", "MI 견본"]])
    files = _append(
        files,
        P02,
        [[MI_NAME, "DEMO_Final_Test", "", "", "", "DEMO-P300", "DEMO-3A", "202601", ""]],
    )
    files = _append(
        files,
        P03,
        [
            [
                MI_NAME,
                "",
                "",
                "",
                "DEMO-P300",
                "DEMO-3A",
                "모두",
                "202601",
                "202606",
                "",
                "1.8",
                "",
                "",
            ],
            [MI_NAME, "", "", "", "DEMO-P300", "DEMO-3A", "모두", "202607", "", "", "1.5", "", ""],
        ],
    )
    files = _append(files, P04, [[MI_NAME, "202601", "", "달력", "4", ""]])
    return _append(files, P05, [[MI_NAME, "모두", "202601", "", "0.9", "1"]])


def _noncanonical(files: Files) -> Files:
    """사람이 쓴 꼴(E1 · E1b) — 같은 값 양산 · ER 두 줄, 04 를 달 차례로 섞음, 02 를 AOI 먼저."""
    bond03 = [
        [BOND, "", "", "", "DEMO-P150", "DEMO-1A", cls, start, end, value, "", "1", "1"]
        for start, end, value in (("202601", "202606", "54000"), ("202607", "", "58000"))
        for cls in ("ER", "양산")
    ]
    files = _replace_rows(files, P03, BOND, bond03)

    def by_month(rows: Table) -> Table:
        return [rows[0], *sorted(rows[1:], key=lambda row: row[1])]

    def aoi_first(rows: Table) -> Table:
        body = rows[1:]
        return [rows[0], *(r for r in body if r[0] != BOND), *(r for r in body if r[0] == BOND)]

    return edited(edited(files, P04, by_month), P02, aoi_first)


def _outside_window(files: Files) -> Files:
    """경계가 계획 창 밖인 판 — 경로 202511 시작, 03 경계 202704, 04 경계 202703."""
    files = edited(
        files, P02, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "시작월", "202511")
    )
    files = _replace_rows(
        files,
        P03,
        BOND,
        [
            [
                BOND,
                "",
                "",
                "",
                "DEMO-P150",
                "DEMO-1A",
                "모두",
                "202511",
                "202606",
                "54000",
                "",
                "1",
                "",
            ],
            [
                BOND,
                "",
                "",
                "",
                "DEMO-P150",
                "DEMO-1A",
                "모두",
                "202607",
                "202703",
                "58000",
                "",
                "1",
                "",
            ],
            [BOND, "", "", "", "DEMO-P150", "DEMO-1A", "모두", "202704", "", "59000", "", "1", ""],
        ],
    )
    files = _replace_rows(
        files,
        P04,
        BOND,
        [[BOND, "202511", "202702", "달력", "6", "0"], [BOND, "202703", "", "달력", "8", "0"]],
    )
    return edited(
        files, P05, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "시작월", "202511")
    )


def _closed(files: Files) -> Files:
    """경로 끝월 202612 로 닫고 값 표도 202612 에서 닫은 판."""
    files = edited(
        files, P02, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "끝월", "202612")
    )
    for name in (P03, P04, P05):
        files = edited(
            files,
            name,
            lambda rows: set_cell(
                rows,
                lambda r: r[0] == BOND and r[rows[0].index("끝월")] == "",
                "끝월",
                "202612",
            ),
        )
    return files


def _longer_values(files: Files) -> Files:
    """경로는 202612 에서 닫았는데 값 기간은 열린 판(E5 — 관문이 받는다)."""
    return edited(files, P02, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "끝월", "202612"))


def _neutral_ratios(files: Files) -> Files:
    """측정률 빈칸 · 0(1 과 같은 뜻), 대여 빈칸."""
    files = edited(
        files, P03, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "Lot 측정률", "")
    )
    files = edited(files, P03, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "WF측정률", "0"))
    return edited(
        files,
        P04,
        lambda rows: set_cell(
            rows, lambda r: r[0] == BOND and r[1] == "202607", "설비대여평가", ""
        ),
    )


def _carried_variants() -> dict[str, Files]:
    """Bond 를 통째 옮김으로 만드는 사본 다섯 — 관문은 모두 받는다."""
    editor = _editor_files()
    two_follow = _append(
        editor, P02, [[BOND, "DEMO_Wire_Bond", "", "", "", "DEMO-P150", "DEMO-1A", "202601", ""]]
    )
    specified_only = _replace_rows(
        _replace_rows(
            editor,
            P02,
            BOND,
            [[BOND, "", "DEMO PRODUCT A", "8H", "Core", "DEMO-P150", "DEMO-1A", "202601", ""]],
        ),
        P03,
        BOND,
        [
            [
                BOND,
                "DEMO PRODUCT A",
                "8H",
                "Core",
                "DEMO-P150",
                "DEMO-1A",
                "모두",
                "202601",
                "",
                "54000",
                "",
                "1",
                "1",
            ]
        ],
    )
    orphan = _append(
        editor,
        P03,
        [[BOND, "", "", "", "DEMO-P999", "DEMO-9Z", "모두", "202601", "", "1000", "", "1", "1"]],
    )
    product_orphan = _append(
        editor,
        P03,
        [
            [
                BOND,
                "DEMO PRODUCT A",
                "8H",
                "Core",
                "DEMO-P999",
                "DEMO-9Z",
                "모두",
                "202601",
                "",
                "1000",
                "",
                "1",
                "1",
            ]
        ],
    )
    run_day = edited(
        editor, P04, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "RUN_DAY", "25")
    )

    return {
        "따라가기 둘 E7": two_follow,
        "지정 꼴 하나": specified_only,
        "고아 03 E2": orphan,
        "제품 행 고아 03": product_orphan,
        "숫자 RUN_DAY E9": run_day,
    }


def _new_line_fields(
    name: str = NEW_NAME, *, start: object = 202601, end: object = None
) -> LineFields:
    return LineFields(
        name=name,
        area="Main",
        basis="CHIP",
        modules=2,
        memo="새 공정",
        reference="DEMO_Chip_Attach",
        step="DEMO-P110",
        mcp="DEMO-1B",
        start=start,  # type: ignore[arg-type]
        end=end,  # type: ignore[arg-type]
    )


def _fill(
    line_id: str, months: Sequence[int], values: Mapping[str, float]
) -> dict[CellKey, CellInput]:
    """새 줄 양산 칸(03 · 05)과 보유 칸을 달마다 채운 그리드 입력."""
    cells: dict[CellKey, CellInput] = {}
    for month in months:
        cells[((line_id, PRODUCTIVITY, MASS, UPEH_COLUMN), month)] = values["upeh"]
        cells[((line_id, EQUIPMENT, "", OWNED_COLUMN), month)] = values["owned"]
        cells[((line_id, RATE, MASS, RUN_RATE_COLUMN), month)] = values["rate"]
        cells[((line_id, RATE, MASS, VITAL_COLUMN), month)] = values["vital"]
    return cells


def _editor_made() -> ExtraProcessPack:
    """편집기가 빈 시작에서 만든 판(새 공정 하나)."""
    model = with_lines(model_from_pack(None), [("n1", _new_line_fields())])
    model = with_cells(
        model, _fill("n1", YEAR_2026, {"upeh": 30000.0, "owned": 5.0, "rate": 0.8, "vital": 1.1})
    )
    result = canonical(fold(model, PackInfo(FORMAT_VERSION, 1)).rows)
    assert result.reading.pack is not None
    return result.reading.pack


def _packs() -> dict[str, ExtraProcessPack]:
    editor = _editor_files()
    return {
        "견본(모두 통째 옮김)": _pack(template_files()),
        "편집기 몫 Bond": _pack(editor),
        "MI 더함": _pack(_with_mi(editor)),
        "사람 꼴 E1": _pack(_noncanonical(_with_mi(editor))),
        "경계가 창 밖": _pack(_outside_window(editor)),
        "닫힌 경로": _pack(_closed(editor)),
        "값이 경로보다 김 E5": _pack(_longer_values(editor)),
        "측정률 빈칸 · 0": _pack(_neutral_ratios(editor)),
        "편집기가 만든 판": _editor_made(),
        **{f"통째 옮김 {name}": _pack(files) for name, files in _carried_variants().items()},
    }


PACKS = _packs()


def _made(model: EditorModel, info: PackInfo = INFO) -> ExtraProcessPack:
    result = canonical(fold(model, info).rows)
    assert result.reading.pack is not None, [problem.text() for problem in result.reading.problems]
    assert result.fixed
    return result.reading.pack


def _line_id(model: EditorModel, name: str) -> str:
    return next(line.line_id for line in model.lines if line.base_name == name)


def _value_at(pack: ExtraProcessPack, process: str, row: RowKey, month: int) -> CellInput:
    """판에서 그 공정 · 그 줄 · 그 달 값(판 꼴 — MI 생산성은 ST)."""
    _, table, mass_class, column = row
    if table == PRODUCTIVITY:
        area = next(item.area for item in pack.processes if item.name == process)
        for item in pack.productivity:
            if (
                item.process == process
                and mass_class in CLASS_EXPANSION[item.mass_class]
                and item.period.covers(month)
            ):
                return item.upeh if area == "Main" else item.st
    elif table == EQUIPMENT:
        for equipment in pack.equipment:
            if equipment.process == process and equipment.period.covers(month):
                return equipment.owned if column == OWNED_COLUMN else equipment.lent
    else:
        for rate in pack.rate_vital:
            if (
                rate.process == process
                and mass_class in CLASS_EXPANSION[rate.mass_class]
                and rate.period.covers(month)
            ):
                return rate.run_rate if column == RUN_RATE_COLUMN else rate.vital
    raise AssertionError(f"값 없음 {process} {row} {month}")


def _shown(pack: ExtraProcessPack, process: str, row: RowKey, month: int) -> CellInput:
    value = _value_at(pack, process, row, month)
    area = next(item.area for item in pack.processes if item.name == process)
    if row[1] == PRODUCTIVITY and area == "MI" and isinstance(value, float):
        return round(60 / value, 2)
    if row[3] == LENT_COLUMN and value is None:
        return 0.0
    return value


def _visible_inputs(model: EditorModel, months: Sequence[int]) -> dict[CellKey, CellInput]:
    """보이는 고칠 수 있는 칸의 값을 모두 그리드 입력으로(사람이 보인 값을 다시 적음)."""
    cells: dict[CellKey, CellInput] = {}
    for view in month_view(model, months).values():
        for row, by_month in view.months.items():
            for month, cell in by_month.items():
                cells[(row, month)] = cell.value
        for row, cell in view.after.items():
            if cell.editable and not cell.multiple and isinstance(cell.key, Onward):
                cells[(row, cell.key)] = cell.value
    return cells


# --------------------------------------------------------------------------- 가름(결정 A)


def test_the_stock_template_is_all_carried_and_neutral_ratios_stay_editable() -> None:
    assert carried_processes(PACKS["견본(모두 통째 옮김)"]) == {
        BOND: CARRY_RATIO,
        AOI: CARRY_ROUTES,
    }
    assert carried_processes(PACKS["편집기 몫 Bond"]) == {AOI: CARRY_ROUTES}
    # 빈칸은 합치기가, 0 은 대당 Capa 가 1.0 으로 읽는다 — 편집기 몫이다.
    assert carried_processes(PACKS["측정률 빈칸 · 0"]) == {AOI: CARRY_ROUTES}
    assert MI_NAME not in carried_processes(PACKS["MI 더함"])


def test_routes_product_rows_other_keys_and_numeric_run_days_are_carried() -> None:
    variants = _carried_variants()

    assert {name: carried_processes(_pack(files))[BOND] for name, files in variants.items()} == {
        "따라가기 둘 E7": CARRY_ROUTES,
        "지정 꼴 하나": CARRY_SPECIFIED,
        "고아 03 E2": CARRY_OTHER_KEY,
        "제품 행 고아 03": CARRY_PRODUCT_ROWS,
        "숫자 RUN_DAY E9": CARRY_RUN_DAY,
    }


# --------------------------------------------------------------------------- I1 · I2 · I7


@pytest.mark.parametrize("window", list(WINDOWS), ids=list(WINDOWS))
@pytest.mark.parametrize("name", list(PACKS), ids=list(PACKS))
def test_an_untouched_pack_and_its_shown_values_rewritten_give_the_same_body(
    name: str, window: str
) -> None:
    """I1 · I2 · I7 — 고치지 않거나 보인 값을 모두 다시 적으면 00 을 고정한 본문 바이트가 같다."""
    base = PACKS[name]
    model = model_from_pack(base)

    untouched = canonical(fold(model, INFO).rows)
    rewritten = with_cells(model, _visible_inputs(model, WINDOWS[window]))
    again = canonical(fold(rewritten, INFO).rows)

    for result in (untouched, again):
        assert result.reading.pack is not None
        assert result.fixed
        assert same_body(result.reading.pack, base)
        assert pack_changes(result.reading.pack, base).changed_cells == 0
    assert effective_edits(rewritten) == {}
    assert untouched.data == again.data


def test_same_body_without_a_base_is_a_new_pack() -> None:
    assert same_body(PACKS["편집기 몫 Bond"], None) is False


def test_mi_shows_rounded_upeh_and_keeps_the_raw_st_when_the_shown_text_is_rewritten() -> None:
    """결정1 · C2 · S2 — 화면은 UPEH, 판은 ST = 60 / UPEH. 보인 글을 다시 적으면 ST 원값."""
    base = PACKS["MI 더함"]
    model = model_from_pack(base)
    line = _line_id(model, MI_NAME)
    row = (line, PRODUCTIVITY, MASS, UPEH_COLUMN)

    view = month_view(model, YEAR_2026)[line]
    edited_once = _made(with_cells(model, {(row, 202603): 40.0}))
    back = with_cells(model, {(row, 202603): 33.33})
    copied = with_cells(model, {(row, 202609): 33.33})

    assert view.months[row][202603].value == 33.33
    assert view.months[row][202609].value == 40.0
    assert _value_at(edited_once, MI_NAME, row, 202603) == 1.5
    assert _value_at(edited_once, MI_NAME, row, 202602) == 1.8
    assert same_body(_made(back), base)
    # 다른 달의 보인 값을 옮겨 적으면 그 바탕 ST 원값(1.8)을 쓴다 — 60 / 33.33 이 아니다.
    assert _value_at(_made(copied), MI_NAME, row, 202609) == 1.8


def test_a_lent_blank_and_zero_are_the_same() -> None:
    base = PACKS["측정률 빈칸 · 0"]
    model = model_from_pack(base)
    row = (_line_id(model, BOND), EQUIPMENT, "", LENT_COLUMN)

    assert same_body(_made(with_cells(model, {(row, 202609): 0.0})), base)


# --------------------------------------------------------------------------- I3 · I4 · I5


def test_the_same_point_edits_in_two_windows_give_the_same_bytes() -> None:
    """I3 — 두 창 모두에 보인 달만 고치면 같은 바이트(모형이 절대 달이라 창을 담지 않는다)."""
    base = PACKS["경계가 창 밖"]
    model = model_from_pack(base)
    line = _line_id(model, BOND)
    edits: dict[CellKey, CellInput] = {
        ((line, PRODUCTIVITY, MASS, UPEH_COLUMN), 202606): 61000.0,
        ((line, EQUIPMENT, "", OWNED_COLUMN), 202607): 9.0,
        ((line, RATE, ENGINEERING, RUN_RATE_COLUMN), 202608): 0.7,
    }
    made: dict[str, bytes] = {}
    for window in ("A 2026", "B 05-08"):
        view = month_view(model, WINDOWS[window])[line]
        for row, month in edits:
            assert isinstance(month, int)
            assert view.months[row][month].editable
        # 그 창에서 보인 값을 모두 다시 적고 같은 칸을 고친 그리드 — 창마다 입력 칸이 다르다.
        cells = {**_visible_inputs(model, WINDOWS[window]), **edits}
        made[window] = canonical(fold(with_cells(model, cells), INFO).rows).data
        changed = with_cells(model, edits)
        cell = month_view(changed, WINDOWS[window])[line].months[
            (line, PRODUCTIVITY, MASS, UPEH_COLUMN)
        ][202606]
        assert (cell.value, cell.default, cell.edited) == (61000.0, 54000.0, True)

    assert made["A 2026"] == made["B 05-08"]


def test_months_that_are_not_edited_keep_their_values() -> None:
    """I4 — 이전 칸 · 여러 값 이후 칸 · 창 밖 달은 바뀌지 않는다(점 고침)."""
    base = PACKS["경계가 창 밖"]
    model = model_from_pack(base)
    line = _line_id(model, BOND)
    edits: dict[CellKey, CellInput] = {
        ((line, PRODUCTIVITY, MASS, UPEH_COLUMN), 202606): 61000.0,
        ((line, EQUIPMENT, "", OWNED_COLUMN), 202605): 7.0,
    }
    view = month_view(model, WINDOWS["B 05-08"])[line]
    made = _made(with_cells(model, edits))

    production = (line, PRODUCTIVITY, MASS, UPEH_COLUMN)
    assert view.before[production].editable is False
    # 이후 칸(202609 ~)은 바탕 값이 58000 · 59000 둘이라 읽기 전용 — 그 칸 입력은 판에 들지 않는다.
    assert view.after[production].multiple and not view.after[production].editable
    refused = with_cells(model, {**edits, (production, Onward(202609)): 1.0})
    assert ignored_cells(refused) == ((production, Onward(202609)),)
    assert (
        canonical(fold(refused, INFO).rows).data
        == canonical(fold(with_cells(model, edits), INFO).rows).data
    )
    for row in value_rows(line):
        for month in range(202511, 202513), range(202601, 202613), range(202701, 202713):
            for value in month:
                if (row, value) in edits:
                    continue
                assert _value_at(made, BOND, row, value) == _value_at(base, BOND, row, value)


def test_rows_keep_their_places_rebuilt_rows_take_the_first_place_and_new_lines_go_last() -> None:
    """I5 · E1 — 손대지 않은 줄은 제자리, 고친 표의 새 줄은 그 공정 첫 원 줄 자리, 새 공정은 끝."""
    base = PACKS["사람 꼴 E1"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    lines = [(line.line_id, line.fields) for line in model.lines]
    model = with_lines(model, [*lines, ("n1", _new_line_fields())])
    model = with_cells(
        model,
        {
            ((bond, EQUIPMENT, "", OWNED_COLUMN), 202609): 9.0,
            **_fill("n1", YEAR_2026, {"upeh": 1000.0, "owned": 1.0, "rate": 1.0, "vital": 1.0}),
        },
    )

    folded = fold(model, INFO)
    made = _made(model)

    base_04 = [(row.process, row.period.start) for row in base.equipment]
    made_04 = [(row.process, row.period.start) for row in made.equipment]
    # 사람이 시작월 차례로 쓴 04 — Bond · MI · AOI · Bond.
    assert base_04 == [(BOND, 202601), (MI_NAME, 202601), (AOI, 202603), (BOND, 202607)]
    # Bond 의 새 줄 넷이 Bond 첫 원 줄 자리에, MI · AOI 는 그 뒤 제자리, 새 공정은 끝.
    assert made_04 == [
        (BOND, 202601),
        (BOND, 202607),
        (BOND, 202609),
        (BOND, 202610),
        (MI_NAME, 202601),
        (AOI, 202603),
        (NEW_NAME, 202601),
    ]
    # 손대지 않은 표(02 · 03)는 사람이 쓴 차례 · 꼴 그대로다.
    assert [row.process for row in made.routes] == [route.process for route in base.routes] + [
        NEW_NAME
    ]
    assert [(row.process, row.mass_class) for row in made.productivity[:4]] == [
        (row.process, row.mass_class) for row in base.productivity[:4]
    ]
    assert made.process_names() == (*base.process_names(), NEW_NAME)
    assert folded.rows[P01][-1][0] == NEW_NAME


def test_the_process_order_follows_the_editor_lines() -> None:
    base = PACKS["MI 더함"]
    model = model_from_pack(base)
    reordered = with_lines(model, [(line.line_id, line.fields) for line in reversed(model.lines)])

    made = _made(reordered)

    assert made.process_names() == tuple(reversed(base.process_names()))
    assert not same_body(made, base)


# --------------------------------------------------------------------------- I6


@pytest.mark.parametrize("value", [0.0, -5.0, None, "abc", "1,000", float("inf")])
def test_human_input_never_raises_and_the_gate_points_back_to_the_cell(value: CellInput) -> None:
    """I6 · C3 — 0 · 음수 · 빈칸 · 글은 예외 없이 관문 거절로 끝나고 되짚기가 그 칸을 가리킨다."""
    base = PACKS["MI 더함"]
    model = model_from_pack(base)
    mi = _line_id(model, MI_NAME)
    cells: dict[CellKey, CellInput] = {((mi, PRODUCTIVITY, MASS, UPEH_COLUMN), 202605): value}

    folded = fold(with_cells(model, cells), INFO)
    result = canonical(folded.rows)

    assert result.reading.pack is None and result.fixed is False
    places = [locate(problem, folded) for problem in result.reading.problems]
    hits = [place for place in places if place is not None and place.line_id == mi]
    assert hits, [problem.text() for problem in result.reading.problems]
    if value is not None:
        assert any(
            place.table == PRODUCTIVITY and place.column == UPEH_COLUMN and place.start == 202605
            for place in hits
        )


@pytest.mark.parametrize("column", [OWNED_COLUMN, LENT_COLUMN, RUN_RATE_COLUMN, VITAL_COLUMN])
@pytest.mark.parametrize("value", [-1.0, "x"])
def test_every_value_column_takes_bad_input_without_raising(column: str, value: CellInput) -> None:
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    table = EQUIPMENT if column in (OWNED_COLUMN, LENT_COLUMN) else RATE
    row = (bond, table, "" if table == EQUIPMENT else ENGINEERING, column)

    result = canonical(fold(with_cells(model, {(row, 202603): value}), INFO).rows)

    assert result.reading.pack is None


def test_bad_line_fields_never_raise() -> None:
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    broken = LineFields(
        name="  ",
        area="X",
        basis="BOX",
        modules=0,
        reference="",
        step="",
        mcp="",
        start="abc",
        end="2026-13",
    )
    rows = [(line.line_id, broken if line.line_id == bond else line.fields) for line in model.lines]

    folded = fold(with_lines(model, rows), INFO)
    result = canonical(folded.rows)

    assert result.reading.pack is None
    codes = {problem.code for problem in result.reading.problems}
    assert {"V-03", "V-06", "V-07"} <= codes


def test_an_empty_start_without_processes_is_refused_by_v03() -> None:
    """E12 — 판 없음(주 길)에서 공정 없이 판을 만들면 관문 V-03."""
    result = canonical(fold(model_from_pack(None), PackInfo(FORMAT_VERSION, 1)).rows)

    assert [problem.text() for problem in result.reading.problems] == [
        "V-03 01_process.csv 공정 — 공정이 하나도 없음"
    ]


# --------------------------------------------------------------------------- 보기 = 판(K1 · probe3)


def _months(first: int, last: int) -> list[int]:
    found = [first]
    while found[-1] < last:
        month = found[-1]
        found.append(month + 1 if month % 100 < 12 else (month // 100 + 1) * 100 + 1)
    return found


def _plus_two_years(month: int) -> int:
    return month + 200


def _norm(row: RowKey, value: CellInput) -> CellInput:
    return 0.0 if row[3] == LENT_COLUMN and value is None else value


def _assert_view_matches_pack(model: EditorModel, months: Sequence[int]) -> None:
    """보이는 모든 칸(창 달 · 이전 · 이후)의 값 = 만든 판이 그 달(들)에 쓰는 값."""
    made = _made(model)
    for line_id, view in month_view(model, months).items():
        line = model.line(line_id)
        assert line is not None and view.axis is not None
        name = line.fields.name
        for row, by_month in view.months.items():
            for month, cell in by_month.items():
                assert _norm(row, cell.value) == _shown(made, name, row, month), (row, month)
        ranges = [(view.before, view.axis.before), (view.after, view.axis.after)]
        for cells, span in ranges:
            if span is None:
                continue
            first, last = span
            covered = _months(first, last if last is not None else _plus_two_years(first))
            for row, cell in cells.items():
                values = {_shown(made, name, row, month) for month in covered}
                if cell.multiple:
                    assert len(values) > 1, (row, span)
                else:
                    assert values == {_norm(row, cell.value)}, (row, span)


@pytest.mark.parametrize("window", ["A 2026", "B 05-08", "C 07-12", "D 01-04"])
def test_every_visible_value_is_the_value_written_even_after_the_route_end_moves(
    window: str,
) -> None:
    """K1 · probe3 — 창이 넓어지거나 줄어도 보이는 모든 칸 = 판에 쓰이는 값. 「계속」 표지는
    없다."""
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    owned = (bond, EQUIPMENT, "", OWNED_COLUMN)
    closed = [
        (line.line_id, line.fields if line.line_id != bond else _with_end(line.fields, 202609))
        for line in model.lines
    ]
    edited_model = with_cells(with_lines(model, closed), {(owned, 202609): 10.0})
    reopened = with_lines(edited_model, [(line.line_id, line.fields) for line in model.lines])

    for state in (edited_model, reopened):
        _assert_view_matches_pack(state, WINDOWS[window])
    made = _made(reopened)
    # 202609 만 고쳤다 — 경로를 다시 열어도 202610 뒤는 바탕 8 그대로다.
    assert [_value_at(made, BOND, owned, month) for month in (202608, 202609, 202610, 202612)] == [
        8.0,
        10.0,
        8.0,
        8.0,
    ]


def _with_end(fields: LineFields, end: int | None) -> LineFields:
    return LineFields(
        name=fields.name,
        area=fields.area,
        basis=fields.basis,
        modules=fields.modules,
        memo=fields.memo,
        reference=fields.reference,
        step=fields.step,
        mcp=fields.mcp,
        start=fields.start,
        end=end,
    )


def test_the_after_cell_is_one_onward_edit_and_the_last_month_alone_does_not_continue() -> None:
    """E11 · 결정 B — 끝 달만 고치면 그 달만, 이후 칸도 고치면 꼬리까지(그리드 채우기가 함께
    덮음)."""
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    row = (bond, PRODUCTIVITY, MASS, UPEH_COLUMN)
    view = month_view(model, YEAR_2026)[bond]
    after_key = view.after[row].key
    assert after_key == Onward(202701) and view.after[row].editable

    last_only = _made(with_cells(model, {(row, 202612): 60000.0}))
    with_tail = _made(with_cells(model, {(row, 202612): 60000.0, (row, after_key): 60000.0}))

    assert _value_at(last_only, BOND, row, 202701) == 58000.0
    assert _value_at(with_tail, BOND, row, 202612) == 60000.0
    assert _value_at(with_tail, BOND, row, 203001) == 60000.0
    # 그 Onward 고침은 다른 창에서도 같은 절대 달(202701 ~)을 뜻한다.
    tailed = with_cells(model, {(row, after_key): 60000.0})
    narrow = month_view(tailed, WINDOWS["B 05-08"])[bond]
    assert narrow.after[row].multiple and narrow.after[row].key == Onward(202609)
    # 그 범위에 다른 창의 고침이 있어 한 값이 될 수 없으므로 잠근다(모형은 그 Onward 를 둔다).
    assert not narrow.after[row].editable
    assert (row, Onward(202701)) in effective_edits(tailed)
    _assert_view_matches_pack(tailed, WINDOWS["B 05-08"])


def test_a_point_edit_from_a_wider_window_locks_the_after_cell_of_a_narrower_one() -> None:
    """결정 B · K1 — 넓은 창에서 202703 을 고치면 2026 창의 이후 칸(202701 ~)은 여러 값이라
    잠긴다."""
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    row = (bond, PRODUCTIVITY, MASS, UPEH_COLUMN)
    wide = tuple(range(202601, 202613)) + tuple(range(202701, 202707))
    assert month_view(model, wide)[bond].months[row][202703].editable

    edited_model = with_cells(model, {(row, 202703): 61000.0})
    narrow = month_view(edited_model, YEAR_2026)[bond]

    assert narrow.after[row].multiple and not narrow.after[row].editable
    _assert_view_matches_pack(edited_model, YEAR_2026)
    _assert_view_matches_pack(edited_model, wide)


def test_redundant_inputs_are_named_so_the_grid_can_drop_them_before_they_revive() -> None:
    """화면 계약 — 걷은 칸(빼도 그대로인 입력)을 그리드 초안에서 지우지 않으면, 다른 창에서 고친
    칸 때문에 그 칸의 「고치지 않았을 때 값」 이 바뀌어 보이지 않던 옛 입력이 되살아난다."""
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    lent = (_line_id(model, BOND), EQUIPMENT, "", LENT_COLUMN)
    stale: dict[CellKey, CellInput] = {(lent, Onward(202701)): 0.0}
    written: dict[CellKey, CellInput] = {(lent, Onward(202601)): 0.5}
    assert month_view(model, WINDOWS["C 07-12"])[lent[0]].after[lent].key == Onward(202701)

    redundant = redundant_cells(with_cells(model, stale))
    revived = with_cells(model, {**stale, **written})
    pruned = with_cells(model, written)

    assert redundant == ((lent, Onward(202701)),)
    assert month_view(revived, WINDOWS["F 없음"])[lent[0]].after[lent].multiple
    after = month_view(pruned, WINDOWS["F 없음"])[lent[0]].after[lent]
    assert (after.value, after.multiple, after.edited) == (0.5, False, True)
    _assert_view_matches_pack(pruned, WINDOWS["F 없음"])


# --------------------------------------------------------------------------- 새 공정 · 빈 시작


def test_a_new_process_from_an_empty_start_passes_the_gate_and_its_tail_takes_the_last_month() -> (
    None
):
    """brief · 결정 B — 빈 시작 → 판 1. 「이후」 기본은 마지막 창 달 값이고 그 값이 판에
    들어간다."""
    model = with_lines(model_from_pack(None), [("n1", _new_line_fields())])
    cells = _fill("n1", YEAR_2026, {"upeh": 30000.0, "owned": 5.0, "rate": 0.8, "vital": 1.1})
    cells[(("n1", PRODUCTIVITY, MASS, UPEH_COLUMN), 202612)] = 32000.0
    model = with_cells(model, cells)
    view = month_view(model, YEAR_2026)["n1"]
    production = ("n1", PRODUCTIVITY, MASS, UPEH_COLUMN)

    made = _made(model, PackInfo(FORMAT_VERSION, 1))

    assert made.info.version_no == 1 and made.process_names() == (NEW_NAME,)
    assert view.after[production].value == 32000.0 and not view.after[production].edited
    assert _value_at(made, NEW_NAME, production, 202701) == 32000.0
    # ER 은 양산을 따르고 대여는 0 에서 시작한다 — 양산 = ER 이라 「모두」 한 줄씩.
    assert {row.mass_class for row in made.productivity} == {"모두"}
    assert [row.lent for row in made.equipment] == [0.0]
    assert made.routes[0].period.end is None and made.productivity[-1].period.end is None


def test_a_new_process_starting_before_the_plan_fills_the_before_cell_from_the_first_month() -> (
    None
):
    model = with_lines(model_from_pack(None), [("n1", _new_line_fields(start=202510))])
    model = with_cells(
        model,
        _fill("n1", WINDOWS["B 05-08"], {"upeh": 100.0, "owned": 1.0, "rate": 1.0, "vital": 1.0}),
    )
    view = month_view(model, WINDOWS["B 05-08"])["n1"]
    production = ("n1", PRODUCTIVITY, MASS, UPEH_COLUMN)

    made = _made(model)

    assert view.before[production].value == 100.0 and not view.before[production].editable
    assert _value_at(made, NEW_NAME, production, 202510) == 100.0
    assert made.productivity[0].period.start == 202510


def test_dropping_a_process_drops_its_routes_and_value_rows() -> None:
    """brief(연쇄) · E7 — 통째 옮김 공정도 지우면 02 ~ 05 가 함께 빠지고 관문을 지난다."""
    base = PACKS["MI 더함"]
    model = model_from_pack(base)
    aoi = _line_id(model, AOI)
    kept = [(line.line_id, line.fields) for line in model.lines if line.line_id != aoi]
    cells: dict[CellKey, CellInput] = {
        (("b2", PRODUCTIVITY, MASS, UPEH_COLUMN), 202605): 1.0,
    }

    dropped = with_cells(with_lines(model, kept), cells)
    made = _made(dropped)

    assert made.process_names() == (BOND, MI_NAME)
    assert AOI not in {row.process for row in made.routes}
    assert AOI not in {row.process for row in made.productivity}
    assert AOI not in {row.process for row in made.equipment}
    assert ignored_cells(dropped) == tuple(cells)
    assert pack_changes(made, base).removed == (AOI,)


def test_carried_processes_take_no_field_edits() -> None:
    """E6 · C4 — 지정 꼴 공정(AOI)은 이름 · Area 를 고칠 수 없다(공정째 지우기만)."""
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    aoi = _line_id(model, AOI)
    renamed = [
        (line.line_id, _with_area(line.fields, "Main") if line.line_id == aoi else line.fields)
        for line in model.lines
    ]

    assert same_body(_made(with_lines(model, renamed)), base)


def _with_area(fields: LineFields, area: str) -> LineFields:
    return LineFields(
        name=fields.name,
        area=area,
        basis=fields.basis,
        modules=fields.modules,
        memo=fields.memo,
        reference=fields.reference,
        step=fields.step,
        mcp=fields.mcp,
        start=fields.start,
        end=fields.end,
    )


# --------------------------------------------------------------------------- 모형 값 고침(결정 F)


def _change(model: EditorModel, process: str, /, **changes: object) -> EditorModel:
    rows = []
    for line in model.lines:
        fields = line.fields
        if line.base_name == process:
            values = {key: getattr(fields, key) for key in LineFields.__dataclass_fields__}
            values.update(changes)
            fields = LineFields(**values)
        rows.append((line.line_id, fields))
    return with_lines(model, rows)


def test_renaming_rewrites_every_row_of_the_process() -> None:
    """E13 · C5 — 이름을 바꾸면 02 ~ 05 의 그 공정 칸이 함께 바뀌어 관문을 지난다."""
    base = PACKS["편집기 몫 Bond"]

    made = _made(_change(model_from_pack(base), BOND, name="DEMO_New_Bond2"))

    assert made.process_names() == ("DEMO_New_Bond2", AOI)
    assert {row.process for row in made.productivity} == {"DEMO_New_Bond2", AOI}
    assert pack_changes(made, base).added == ("DEMO_New_Bond2",)


def test_switching_area_moves_the_productivity_by_upeh() -> None:
    """E6 · F — Main ↔ MI 는 03 을 UPEH 기준으로 옮긴다(ST = 60 / UPEH, 왕복은 1 ulp 안)."""
    base = PACKS["MI 더함"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    row = (bond, PRODUCTIVITY, MASS, UPEH_COLUMN)

    to_mi = _change(model, BOND, area="MI")
    made = _made(to_mi)
    view = month_view(to_mi, YEAR_2026)[bond]
    back = _made(_change(to_mi, BOND, area="Main"))

    assert _value_at(made, BOND, row, 202601) == pytest.approx(60 / 54000)
    assert made.productivity[0].upeh is None
    assert view.months[row][202601].value == 54000.0
    assert same_body(back, base)


def test_changing_step_moves_the_productivity_key() -> None:
    """E14 · C8 — STEP · MCP 를 바꾸면 03 키도 따라가 관문을 지난다."""
    made = _made(_change(model_from_pack(PACKS["편집기 몫 Bond"]), BOND, step="DEMO-P151"))

    assert {row.step for row in made.productivity if row.process == BOND} == {"DEMO-P151"}


def test_shortening_and_extending_the_route_rebuild_the_value_tables() -> None:
    """E8 · E9 · C7 · C9 — 경로 하나라 줄이면 세 표가 그 기간으로, 늘리면 끝 달 값(대여 0.5 ·
    측정률 빈칸 · 달력)을 그대로 잇는다 — 기본값(대여 0 · 측정률 1)으로 바꾸지 않는다."""
    files = _closed(_editor_files())
    files = edited(
        files,
        P04,
        lambda rows: set_cell(
            rows, lambda r: r[0] == BOND and r[1] == "202607", "설비대여평가", "0.5"
        ),
    )
    files = edited(
        files, P03, lambda rows: set_cell(rows, lambda r: r[0] == BOND, "Lot 측정률", "")
    )
    base = _pack(files)
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    owned = (bond, EQUIPMENT, "", OWNED_COLUMN)
    lent = (bond, EQUIPMENT, "", LENT_COLUMN)

    shorter = _made(_change(model, BOND, end=202609))
    longer_model = _change(model, BOND, end=None)
    longer = _made(longer_model)
    view = month_view(longer_model, YEAR_2026)[bond]

    assert {row.period.end for row in shorter.equipment if row.process == BOND} == {202606, 202609}
    periods = [row.period for row in shorter.productivity if row.process == BOND]
    periods += [row.period for row in shorter.rate_vital if row.process == BOND]
    assert all(period.end is not None and period.end <= 202609 for period in periods)
    assert _value_at(longer, BOND, owned, 202801) == 8.0
    assert _value_at(longer, BOND, lent, 202801) == 0.5
    assert all(row.run_day is None for row in longer.equipment)
    tail = [row for row in longer.productivity if row.process == BOND][-1]
    assert (tail.period.end, tail.lot_ratio, tail.wf_ratio) == (None, None, 1.0)
    assert view.after[owned].value == 8.0 and view.after[owned].editable


def test_a_rebuilt_table_covers_exactly_the_route() -> None:
    """E5 — 값 기간이 경로보다 긴 판도 받지만, 고친 표는 경로 기간만 덮고(첫 시작 = 경로 시작,
    마지막 끝 = 경로 끝) 손대지 않은 표는 긴 그대로다."""
    base = PACKS["값이 경로보다 김 E5"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)

    made = _made(with_cells(model, {((bond, EQUIPMENT, "", OWNED_COLUMN), 202603): 7.0}))

    equipment = [row.period for row in made.equipment if row.process == BOND]
    productivity = [row.period for row in made.productivity if row.process == BOND]
    assert equipment[0].start == 202601 and equipment[-1].end == 202612
    assert productivity[-1].end is None


def test_a_one_month_edit_on_separate_mass_and_er_rows_does_not_overlap() -> None:
    """E15 · C10 — 따로 쓴 양산 · ER 바탕에서 양산 · ER 같은 달 고침은 「모두」 한 줄이고
    겹치지 않는다."""
    base = PACKS["사람 꼴 E1"]
    model = model_from_pack(base)
    bond = _line_id(model, BOND)
    cells: dict[CellKey, CellInput] = {
        ((bond, PRODUCTIVITY, MASS, UPEH_COLUMN), 202609): 60000.0,
        ((bond, PRODUCTIVITY, ENGINEERING, UPEH_COLUMN), 202609): 60000.0,
    }

    made = _made(with_cells(model, cells))

    bond_rows = [
        (row.mass_class, row.period.start, row.period.end)
        for row in made.productivity
        if row.process == BOND
    ]
    assert bond_rows == [
        ("모두", 202601, 202606),
        ("모두", 202607, 202608),
        ("모두", 202609, 202609),
        ("모두", 202610, None),
    ]


def test_rewriting_the_same_value_keeps_the_row_whole() -> None:
    """E10 · C2 — 같은 값을 다시 적은 칸은 고침이 아니다(쪼개지 않는다)."""
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    row = (_line_id(model, BOND), PRODUCTIVITY, MASS, UPEH_COLUMN)

    rewritten = with_cells(model, {(row, 202609): 58000.0, (row, 202610): 60000.0})
    undone = with_cells(model, {(row, 202609): 58000.0})

    assert list(effective_edits(rewritten)) == [(row, 202610)]
    assert same_body(_made(undone), base)


# --------------------------------------------------------------------------- 정규 바이트 · 되짚기


@pytest.mark.parametrize("name", ["DEMO_X", "010", "=DEMO", 'A"B', '="="DEMO_X""'])
def test_canonical_bytes_reach_a_fixed_point_for_odd_text(name: str) -> None:
    """E4 · S3 — 겹친 가드처럼 한 번에 닿지 않는 글도 고정점까지 되풀이한다."""
    model = with_lines(model_from_pack(None), [("n1", _new_line_fields(name))])
    model = with_cells(
        model, _fill("n1", YEAR_2026, {"upeh": 10.0, "owned": 1.0, "rate": 1.0, "vital": 1.0})
    )

    result = canonical(fold(model, PackInfo(FORMAT_VERSION, 1)).rows)

    assert result.reading.pack is not None and result.fixed
    assert pack_to_zip(result.reading.pack) == result.data


def test_problems_on_carried_rows_point_back_as_carried() -> None:
    """G — 거절이 통째 옮김 줄에 서면 되짚기가 「옮긴 줄」 로 가리킨다."""
    base = PACKS["편집기 몫 Bond"]
    model = model_from_pack(base)
    aoi = _line_id(model, AOI)
    clash = _change(model, BOND, name=AOI.lower())

    folded = fold(clash, INFO)
    result = canonical(folded.rows)

    duplicate = next(problem for problem in result.reading.problems if problem.code == "V-03")
    place = locate(duplicate, folded)
    assert place is not None
    assert (place.line_id, place.table, place.carried) == (aoi, "01", True)
