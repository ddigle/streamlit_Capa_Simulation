# Purpose: 합친 머리에서 등급 동작 · 장부 쓰기의 벽 · 받는 자리가 빠짐없이 덮였는지 가로질러 본다.

"""접속 등급의 가로지르는 그물(2026-11-17 두 차례 답 — 정한 것 「등급 넷마다 단추가 있나 없나」 ·
규칙집 UI-INP-07 예외).

갈래(core · calc · equip · modules)마다 `tests/test_grade_ui_<갈래>.py` 가 자기 화면을 등급 넷으로
그려 단추 유무를 보고, 모듈 수준 `COVERED_ACTIONS` 와 받는 자리 그물
(`grade_support.assert_refusals_caught`)에 넘기는 뿌리 파일을 둔다. 이 파일은 그 넷을 **글로
읽어**(import 하지 않음 — 무거운 화면 시험을 끌어오지 않게) 셋을 본다.

- 네 파일이 모두 있다 — 빠지면 건너뛰지 않고 실패다(한 갈래가 빠지면 그 갈래 화면이 그물 밖).
- `grades.ACTIONS` 의 동작이 모두(`admin.area` 포함) 네 파일의 `COVERED_ACTIONS` 합집합에 있다.
- 쓰기 장부(`tests/test_write_entry_points.py` LEDGER)의 바깥 함수마다 뿌리(위젯 콜백 ·
  `st.dialog` · `st.fragment` — 이름 부름 길로 파일을 넘어 찾음, 없으면 「본문」 — `run_core_page`
  가 받음)가 하나 이상이고, 본문이 아닌 뿌리의 파일은 모두 어느 갈래 파일의
  `assert_refusals_caught` 에 넘겨졌다. 그리고 장부의 쓰기 이름마다 저장소 쪽 벽(`@audited` ·
  `@gated` — `grades.GATE_ATTRIBUTE`)이 닿는다.

갈래를 합치기 전(한 갈래 가지 홀로)에는 다른 갈래 파일 · 벽이 없어 실패한다 — 합친 머리의 그물이다.

**네 갈래 시험이 보지 못하는 것**(새 줄을 더할 때 짝을 단다):

- 운영 진입(`capa_server.py`)을 돌리지 않는다 — AppTest 는 `app.py` 쪽 화면만 그린다.
  진입의 런타임 전 길은 `tests/test_server_pre_runtime_imports.py` 가 진입 파일을 그대로
  import 해 본다.
- 컴포넌트 JS · CSS 를 돌리지 않는다 — 대역이 받은 data 까지만 본다. 컴포넌트 안 단추는 그
  data 를 자산의 node 판정에 그대로 돌리는 줄을 둔다(Space 「호기 정보」 「CSV」 ·
  `test_space_unit_sheet_js.run_csv_hidden`, 시나리오 목록 표 ·
  `test_scenario_list_grid_assets.drawn_list_controls`). 단추 서식이 `[hidden]` 을 덮는 꼴은
  자산 시험이 본다.
- 표에 적은 단추만 본다 — 등급과 상관없어야 하는 단추(공식 세션의 「공식으로 바꾸기」), 오른쪽
  칸 고르기의 칸 하나하나, 팝업 끝 바로 가기처럼 「없어야 할 것」 도 줄로 적어야 잡힌다.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import grade_support

from capa_simulation.auth import grades

ROOT: Final = Path(__file__).resolve().parents[1]
LANES: Final = ("core", "calc", "equip", "modules")
LANE_FILES: Final = tuple(ROOT / "tests" / f"test_grade_ui_{lane}.py" for lane in LANES)
# 저장소 메서드가 아닌 장부 쓰기(감싸개) — 그 안에서 부르는 저장소 쓰기가 벽을 단다. 새 감싸개는
# 안을 읽어 벽이 닿는지 본 뒤 여기 더한다(core 갈래 보고 — 사람이 확인할 둘).
REVIEWED_WRAPPERS: Final = frozenset({"run_auto_official_update", "save_bigdataquery_scenario"})


def _module_assignments(tree: ast.Module) -> dict[str, ast.expr]:
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            found[node.target.id] = node.value
    return found


def _strings(node: ast.expr | None) -> set[str]:
    """글자 상수 모음 — `frozenset({...})` · `frozenset()` · 튜플 · 목록 · 집합."""
    if node is None:
        return set()
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id
        in (
            "frozenset",
            "set",
            "tuple",
        )
    ):
        return _strings(node.args[0]) if node.args else set()
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return {
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    return set()


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def covered_actions(path: Path) -> set[str]:
    assignments = _module_assignments(_parse(path))
    assert "COVERED_ACTIONS" in assignments, f"{path.name} 에 모듈 수준 COVERED_ACTIONS 가 없다"
    return _strings(assignments["COVERED_ACTIONS"])


def passed_root_files(path: Path) -> set[str]:
    """그 파일이 `assert_refusals_caught(…)` 에 넘긴 뿌리 파일(글자 목록 · 모듈 수준 이름)."""
    tree = _parse(path)
    assignments = _module_assignments(tree)
    found: set[str] = set()
    calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "assert_refusals_caught" or not node.args:
            continue
        calls += 1
        argument = node.args[0]
        if isinstance(argument, ast.Name):
            found |= _strings(assignments.get(argument.id))
        else:
            found |= _strings(argument)
    assert calls, f"{path.name} 가 assert_refusals_caught 를 부르지 않는다"
    return found


def test_the_four_lane_ui_test_files_exist() -> None:
    missing = [path.name for path in LANE_FILES if not path.is_file()]
    assert missing == [], f"갈래 등급 화면 시험이 빠졌다: {missing}"


def test_every_action_is_covered_by_some_lane() -> None:
    covered: set[str] = set()
    for path in LANE_FILES:
        if path.is_file():
            covered |= covered_actions(path)
    unknown = sorted(covered - set(grades.ACTIONS))
    missing = sorted(set(grades.ACTIONS) - covered)
    assert unknown == [], f"표에 없는 동작 이름: {unknown}"
    assert missing == [], f"어느 갈래 화면 시험도 덮지 않은 동작: {missing}"


def test_every_ledger_root_file_is_handed_to_a_lane_net() -> None:
    """본문이 아닌 뿌리(콜백 · 팝업 · 프래그먼트)의 파일은 어느 갈래의 받는 자리 그물에 넘겨졌다."""
    handed: set[str] = set()
    for path in LANE_FILES:
        if path.is_file():
            handed |= passed_root_files(path)
    scan = grade_support._scan()
    outers = sorted(grade_support.ledger_outer_functions())
    assert outers, "장부의 바깥 함수를 읽지 못했다 — 그물이 헛돈다"
    orphans: list[str] = []
    for outer in outers:
        roots = grade_support.roots_for(outer, scan)
        assert roots, outer
        orphans.extend(
            f"{root.path}::{root.name}({root.kind}) ← {outer[0]}::{outer[1]}"
            for root in roots
            if root.kind != "body" and root.path not in handed
        )
    assert orphans == [], "받는 자리 그물에 넘기지 않은 뿌리 파일:\n" + "\n".join(orphans)


def test_every_ledger_write_reaches_a_wall() -> None:
    report = grade_support.ledger_wall_report()

    assert report.walled, "벽 판정이 헛돈다 — 벽을 단 쓰기가 하나도 없다"
    assert sorted(report.unwalled) == [], f"벽이 없는 장부 쓰기: {sorted(report.unwalled)}"
    assert sorted(report.wrappers - REVIEWED_WRAPPERS) == [], (
        "안을 확인하지 않은 감싸개 — 안의 저장소 쓰기가 벽을 다는지 보고 "
        "REVIEWED_WRAPPERS 에 더한다"
    )
