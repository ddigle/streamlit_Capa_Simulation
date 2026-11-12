# Purpose: 표 위 줄을 합친 세 자리(기준 정보 · 큰 월 표 · 표시순서)가 그 꼴을 지키는지 본다.

"""표 위 줄 합침(검수 물음 table-top, 답 「줄을 합친다 — 기준 정보 두 줄을 한 줄로, 표시 범위 ·
고르기 칸을 표 제목 줄 곁으로」, 설계 규칙 UI-LAY-11).

줄 수 자체는 브라우저 배치라 AppTest 로 잴 수 없고 화면 확인 항목은 이번 점검에서 늘리지 않았다 —
이 그물은 줄을 합친 **꼴**을 소스로 본다.

1. 큰 월 표(`render_hierarchical_monthly_table`)에 `page_size` 를 넘기는 자리는 `page_slot` 도
   넘기고, 그 칸은 같은 모듈의 `with table_heading_row(…)` 안에서 만든다 — 「표시 범위」 가 제목
   줄 곁에 선다.
2. 기준 정보 편집 그리드는 한 줄 서식(`reference_grid.ONE_LINE_STYLE`)을 `page_style=` 로 받고,
   그 서식이 고르는 key 셋(작업 줄 칸 · 단추 줄 · 그리드 칸)이 화면에서 그 이름의 칸으로 선다.
   생산 계획 PKG PLAN · 수율 그리드도 표마다 같은 꼴이다(`plan_grid.LAYOUTS` — 단추 줄이 작업 줄
   칸의 끝 자식인지는 `tests/test_load_conversion_plan_apply.py` 가 화면으로 본다).
3. 표시순서 범위 고르기는 「직접 편집」 제목 줄 곁이다 — 배치는
   `tests/test_display_order_management.py` 의 `test_the_scope_pickers_stand_on_the_heading_line`
   이 본다.
4. 세 그리드 공용 찾기 칸은 140px 이고 한 줄 문턱이 사내 보고 창 1283 이하다(2026-11-12 남은 물음
   보드 ③-10 (가)).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from capa_simulation.components import plan_grid, reference_grid

ROOT = Path(__file__).resolve().parents[1]


def _sources() -> list[Path]:
    return [
        *sorted((ROOT / "app_pages").glob("*.py")),
        *sorted((ROOT / "src" / "capa_simulation").rglob("*.py")),
    ]


def _call_name(node: ast.Call) -> str:
    return str(getattr(node.func, "id", getattr(node.func, "attr", "")))


def _heading_slots(tree: ast.AST) -> set[str]:
    """`with table_heading_row(…):` 안에서 이름에 담은 칸."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        if not any(
            isinstance(item.context_expr, ast.Call)
            and _call_name(item.context_expr) == "table_heading_row"
            for item in node.items
        ):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign):
                names.update(t.id for t in inner.targets if isinstance(t, ast.Name))
    return names


def _paged_table_calls() -> list[tuple[str, ast.Call, set[str]]]:
    found: list[tuple[str, ast.Call, set[str]]] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        slots = _heading_slots(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and _call_name(node) == "render_hierarchical_monthly_table"
                and any(keyword.arg == "page_size" for keyword in node.keywords)
            ):
                found.append((path.relative_to(ROOT).as_posix(), node, slots))
    return found


def test_a_paged_month_table_puts_its_range_on_the_heading_line() -> None:
    calls = _paged_table_calls()
    assert calls, "큰 월 표를 쪽으로 나누는 자리가 없어졌다 — 그물을 다시 본다"
    problems: list[str] = []
    for where, call, slots in calls:
        slot = next((kw.value for kw in call.keywords if kw.arg == "page_slot"), None)
        if not isinstance(slot, ast.Name) or slot.id not in slots:
            problems.append(f"{where}:{call.lineno}")
    assert not problems, (
        "「표시 범위」 칸을 표 제목 줄(`table_heading_row`) 안에서 만들어 `page_slot` 으로 넘기세요"
        " — 제목 줄과 표 사이에 줄을 더 세우지 않습니다(UI-LAY-11): " + ", ".join(problems)
    )


def test_the_reference_grid_takes_the_one_line_style() -> None:
    tree = ast.parse((ROOT / "src/capa_simulation/components/reference_grid.py").read_text("utf-8"))
    grid_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "render_edit_grid"
    ]
    assert grid_calls
    for call in grid_calls:
        style = next((kw.value for kw in call.keywords if kw.arg == "page_style"), None)
        assert isinstance(style, ast.Name) and style.id == "ONE_LINE_STYLE", call.lineno


def test_the_one_line_style_picks_the_boxes_the_page_draws() -> None:
    style = reference_grid.ONE_LINE_STYLE
    for key in (reference_grid.ACTIONS_BOX, reference_grid.ACTION_ROW, reference_grid.GRID_BOX):
        assert f".st-key-{key}" in style, key
    assert f"min-width: {reference_grid.ONE_LINE_MIN_WINDOW_PX}px" in style
    page = (ROOT / "app_pages/reference_data.py").read_text(encoding="utf-8")
    assert "st.container(key=reference_grid.ACTIONS_BOX)" in page
    assert "st.container(key=reference_grid.GRID_BOX)" in page
    module = (ROOT / "src/capa_simulation/components/reference_grid.py").read_text("utf-8")
    assert "st.container(key=ACTION_ROW," in module


def test_the_plan_grids_take_their_own_one_line_style() -> None:
    """생산 계획 두 그리드는 표마다 한 줄 서식(`plan_grid.LAYOUTS[table].style`)을 받고 — 문턱 ·
    왼쪽 비움은 표마다 고친 뒤 단추 줄 폭으로 잰 값이다 — 그 서식이 고르는 key 셋이 화면에서 그
    이름의 칸으로 선다(2026-11-12 보드 답 k-a1 · q1)."""
    assert set(plan_grid.LAYOUTS) == {"RQ_PKG_PLAN", "RQ_YLD"}
    keys = [
        key
        for layout in plan_grid.LAYOUTS.values()
        for key in (layout.actions_box, layout.action_row, layout.grid_box)
    ]
    assert len(set(keys)) == len(keys)
    for layout in plan_grid.LAYOUTS.values():
        style = layout.style
        for key in (layout.actions_box, layout.action_row, layout.grid_box):
            assert f".st-key-{key}" in style, key
        assert (
            f"> .st-key-{layout.actions_box} > :last-child > .st-key-{layout.action_row}" in style
        )
        assert f"min-width: {layout.min_window_px}px" in style
        assert f"--eg-toolbar-reserve: {layout.reserve_px}px" in style
    module = (ROOT / "src/capa_simulation/components/plan_grid.py").read_text("utf-8")
    assert "page_style=LAYOUTS[table].style" in module
    assert "key=LAYOUTS[table].action_row," in module
    page = (ROOT / "app_pages/load_conversion.py").read_text(encoding="utf-8")
    for name in ("plan_layout", "yield_layout"):
        assert f"st.container(key={name}.actions_box)" in page, name
        assert f"st.container(key={name}.grid_box)" in page, name


def test_the_shared_search_box_lets_all_three_grids_stand_on_one_line_in_the_report_window() -> (
    None
):
    """찾기 칸은 세 그리드(기준 정보 · PKG PLAN · 수율) 공용 140px 이고, 고친 뒤 단추 줄로 잰 한 줄
    문턱이 모두 사내 보고 창 1283 이하다 — PKG PLAN 도 그 창에서 한 줄이다(2026-11-12 남은 물음
    보드 ③-10 (가), 문턱은 샘플 관측)."""
    css = (ROOT / "src/capa_simulation/components/edit_grid_assets/eg_toolbar.css").read_text(
        "utf-8"
    )
    assert re.search(r"\.eg-tb-q \{[^}]*\bwidth: 140px;", css)
    windows = [
        reference_grid.ONE_LINE_MIN_WINDOW_PX,
        *(layout.min_window_px for layout in plan_grid.LAYOUTS.values()),
    ]
    assert max(windows) <= 1283
