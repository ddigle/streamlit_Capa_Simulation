# Purpose: 자리에서 걷은 경고마다 등록부 코드 · 보내는 부름 · 그 코드를 단언하는 화면 시험을 맞댄다.

"""걷은 경고 ↔ 알림 짝(설계 규칙 UI-NTF-05 — `docs/design_rules.md` 5-2).

숫자를 믿기 전에 알아야 할 문제는 숨기지 않는다 — 경고를 자리에서 걷어도 알림창 · Alarm 에 남는다
(UI-NTF-05). 이 그물은 자리에서 걷은 경고마다 한 줄(`WITHDRAWN`)을 두고 셋을 맞댄다.

1. 코드가 등록부(`alerts.REGISTRY`)에 있고 갈래가 보내는 길과 맞다 — 동작 뒤 한 번 일어난 경고는
   사건(`flash.queue_flash(…, popup_only=True)` — 버튼 곁에 그리지 않고 알림창 · Alarm 에만),
   조건이 남은 동안의 경고는 상태(`alerts.state`)다.
2. 걷은 자리(파일 · 맨 바깥 함수)가 지금도 그 코드로 보낸다 — `queue_flash` 는 `popup_only=True` 와
   종류(`kind=`)의 기본 코드(`alerts.FLASH_CODES`) 또는 `alert=` 코드, 상태는 `state("코드", …)`.
3. 그 화면 시험이 있고 그 코드가 **선다고** 단언한다 — 시험 함수(와 그 시험이 부르는 같은 파일
   도우미 한 겹)에서 코드가 같음 · 포함 비교(`==` · `in`)의 값이거나(부름 인자 밖 —
   `note["code"] == "FL-03"`), `active_state(app, "코드")` 의 결과를 `is None` 밖에서 쓴다. 해소만
   보는 단언(`states(app, code)` 의 `active` 가 모두 거짓 · `active_state(…) is None`)이나 설명 글의
   코드는 세지 않는다.

새 경고를 자리에서 걷으면 같은 변경에서 이 표에 한 줄을 더한다(PRC-01). 2026-11-04 설계 규칙 확인
보드 AMB-05 (나)(사이드바 저장 칸 밑 남은 Capa 계산 오류 · HOME 주요 Case 칩 경고 — 둘 다 알림창
· Alarm 으로)와 같은 날 걷은 저장 뒤 경고 · 가용설비 「한쪽에만 있는 공정」 줄이 첫 줄들이다.

걷지 않은 것: 시나리오 관리 설비 시나리오 구획의 「그 사이 바뀌어 …」 거절
(`equipment_scenario_management._refused`)은 확인 체크 · 입력 칸을 새로 세우는 거절이라 구획
맨 위 칸과 알림창 둘에 선다 — UI-NTF-03 의 예외 「확인 칸을 다시 세우는 거절」(2026-11-04 반영
검수표 D3 (가))이고 이 표에 들지 않는다. 시나리오 관리 보관함 · 카드 보관의 「그 사이 빠져 …」
누름은 다시 세울 칸이 없어 알림창에만 간다(아래 `_refuse_gone_press`).
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import pytest

from capa_simulation import alerts

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Withdrawn:
    """자리에서 걷은 경고 하나 — 무엇을 · 왜(규칙 · 답) · 어디서 보내나 · 무엇이 단언하나."""

    what: str
    why: str
    file: str
    function: str
    code: str
    route: Literal["flash", "state"]
    test: str


# Space 「Space 도면」 상자 끝 줄 넷(V-09) 가운데 배치 차이 · 일정 없는 호기를 함께 단언하는 화면
# 시험 — 가정 설비 시나리오에서 둘이 서고 상자 · 본문에 그 줄이 없음을 본다. 모듈 구성 · 지운 호기
# 줄은 그 조건을 만드는 Space 배치 시험이 단언한다.
_SPACE_BOX_TEST = (
    "tests/test_space_sidebar_box.py"
    "::test_an_assumption_raises_the_unscheduled_and_layout_alerts_and_keeps_the_box_to_controls"
)
_SPACE_OVERLAY_TESTS = "tests/test_space_layout_overlay_page.py"

WITHDRAWN: tuple[Withdrawn, ...] = (
    Withdrawn(
        what="사이드바 시나리오 팝업 저장 칸 밑 — 저장 뒤 남은 Capa 계산 오류(공식 지정이 막힘)",
        why="V-14 · AMB-05 (나)",
        file="src/capa_simulation/components/scenario_status.py",
        function="_render_revision_save",
        code="FL-03",
        route="flash",
        test="tests/test_scenario_sidebar.py::test_a_save_with_an_old_error_is_kept_and_warned",
    ),
    Withdrawn(
        what="HOME 「LOB 표시 조건」 주요 Case 칩 줄 밑 — 칩을 눌러 불러오지 못한 까닭",
        why="V-14 · AMB-05 (나)",
        file="src/capa_simulation/components/home_main_case_chips.py",
        function="_notify",
        code="FL-03",
        route="flash",
        test=(
            "tests/test_home_main_case_chips.py"
            "::test_a_revision_the_load_refuses_leaves_the_scenario_and_says_why"
        ),
    ),
    Withdrawn(
        what="시나리오 관리 복제 구획 — 복제 뒤 남은 Capa 계산 오류",
        why="V-14 · AMB-05 (나)",
        file="src/capa_simulation/components/scenario_management.py",
        function="_render_clone",
        code="FL-03",
        route="flash",
        test=(
            "tests/test_scenario_management_page.py"
            "::test_gate_refusals_and_warnings_keep_tildes_in_example_keys"
        ),
    ),
    Withdrawn(
        what="시나리오 관리 공식버전 구획 — 공식 지정 뒤 발행 검사 경고",
        why="V-14 · AMB-05 (나)",
        file="src/capa_simulation/components/scenario_management.py",
        function="_official_published",
        code="FL-03",
        route="flash",
        test=(
            "tests/test_scenario_management_page.py"
            "::test_official_release_with_demand_left_out_of_the_requirement_warns_after_publishing"
        ),
    ),
    Withdrawn(
        what="시나리오 관리 월 머지 · 연도 Shift — 저장 뒤 계산 검사 경고 상자",
        why="V-07 · AMB-05 (나)",
        file="src/capa_simulation/components/scenario_transform.py",
        function="render_derived_save",
        code="FL-03",
        route="flash",
        test="tests/test_scenario_merge_ui.py::test_a_refused_derived_save_writes_nothing",
    ),
    Withdrawn(
        what="Admin 공식버전 자동 갱신 「지금 실행」 — 발행 뒤 소요대수에 들지 않은 수요 경고",
        why="UI-NTF-03 · AMB-05 (나) · home-18",
        file="src/capa_simulation/components/auto_official_update_tab.py",
        function="_hold_run_result",
        code="FL-03",
        route="flash",
        test=(
            "tests/test_auto_official_update_tab.py"
            "::test_run_now_shows_uncounted_demand_as_a_warning_after_the_success"
        ),
    ),
    Withdrawn(
        what="BigDataQuery 등록 저장 단추 밑 — 저장 뒤 CS 빈 행 뺌 · 대당 Capa 계산 멈춤 경고",
        why="UI-NTF-03 · AMB-05 (나)",
        file="src/capa_simulation/components/bigdataquery_registration.py",
        function="_save_scenario",
        code="FL-03",
        route="flash",
        test=(
            "tests/test_bigdataquery_registration.py"
            "::test_the_saved_notices_go_to_the_alert_popup_not_under_the_save_button"
        ),
    ),
    Withdrawn(
        what="시나리오 관리 보관함 · 카드 보관 — 고른 시나리오가 그 사이 빠져 아무것도 하지 않음",
        why="UI-NTF-03",
        file="src/capa_simulation/components/scenario_management.py",
        function="_refuse_gone_press",
        code="FL-03",
        route="flash",
        test=(
            "tests/test_scenario_archive_double_press.py"
            "::test_restoring_an_archive_restored_elsewhere_writes_nothing_and_says_so"
        ),
    ),
    Withdrawn(
        what="시나리오 관리 설비 시나리오 구획 — 옛 판 흔적이 있는 설비 시나리오 이름 · 개수 줄",
        why="UI-TXT-04 · UI-NTF-02",
        file="src/capa_simulation/components/equipment_scenario_management.py",
        function="report_layout_traces",
        code="SC-03",
        route="state",
        test=(
            "tests/test_equipment_scenario_layout_management.py"
            "::test_the_old_code_traces_list_is_a_state_alert_not_a_place_line"
        ),
    ),
    Withdrawn(
        what=(
            "Space 사이드바 「Space 도면」 상자 끝 — 배치 줄(「가정 배치 · 공식과 다른 호기 n대 ·"
            " 도면 요소 m개」 · 「가정이던 때 배치 · …」)"
        ),
        why="V-09 · UI-TXT-01 · UI-NTF-02",
        file="src/capa_simulation/components/space_floor_layout.py",
        function="report_layout_notices",
        code="EQ-13",
        route="state",
        test=_SPACE_BOX_TEST,
    ),
    Withdrawn(
        what="Space 사이드바 「Space 도면」 상자 끝 — 공식에서 모듈 구성이 바뀐 묶음 줄",
        why="V-09 · UI-TXT-01 · UI-NTF-02",
        file="src/capa_simulation/components/space_floor_layout.py",
        function="report_layout_notices",
        code="EQ-14",
        route="state",
        test=(
            f"{_SPACE_OVERLAY_TESTS}"
            "::test_an_official_regroup_raises_the_module_alert_until_the_official_is_drawn"
        ),
    ),
    Withdrawn(
        what="Space 사이드바 「Space 도면」 상자 끝 — 공통 대장에서 지운 호기의 배치 차이 줄",
        why="V-09 · UI-TXT-01 · UI-NTF-02",
        file="src/capa_simulation/components/space_floor_layout.py",
        function="report_layout_notices",
        code="EQ-15",
        route="state",
        test=(
            f"{_SPACE_OVERLAY_TESTS}"
            "::test_a_deleted_units_difference_is_named_once_in_the_space_head"
        ),
    ),
    Withdrawn(
        what=(
            "Space 사이드바 「Space 도면」 상자 끝 — 「일정 없는 호기 n대 · 계산 제외」"
            " · 「공식 일정 없음 n대 · 그리지 않음」 줄(가용설비 현황과 같은 알림)"
        ),
        why="V-09 · UI-TXT-01 · UI-NTF-02",
        file="src/capa_simulation/components/equipment_scenario_status.py",
        function="report_unscheduled_units",
        code="EQ-04",
        route="state",
        test=_SPACE_BOX_TEST,
    ),
    Withdrawn(
        what="공정 Capa 상세 정리 줄 — 「사용기준 제외 n대」(설비 일정이 설 때 늘 서던 내역)",
        why="UI-TXT-04 · UI-NTF-02 · 검수표 11/02 exec-20",
        file="app_pages/process_capa_detail.py",
        function="report_usage_excluded",
        code="PD-04",
        route="state",
        test=(
            "tests/test_process_capa_detail_page.py"
            "::test_units_left_out_by_usage_basis_raise_an_alert_and_leave_the_closing_row_quiet"
        ),
    ),
    Withdrawn(
        what="가용설비 Summary › Static 대비 일정 — 「한쪽에만 있는 공정 n개를 뺐습니다」 캡션",
        why="V-12 · UI-TXT-04",
        file="src/capa_simulation/components/availability_gap_panel.py",
        function="_report_unmatched",
        code="EQ-06",
        route="state",
        test=(
            "tests/test_availability_gap_panel.py"
            "::test_unmatched_processes_stay_out_of_totals_and_fallback_rows"
        ),
    ),
    Withdrawn(
        what=(
            "제약 시뮬레이션 맨 위 — 「설비는 세션의 「…」 기준입니다 — 공정 Capa 상세는 HOME"
            " 칸에서 열어 설비가 공식 고정이었습니다」 안내 상자"
        ),
        why="UI-NTF-02 · 검수표 exec-41",
        file="app_pages/constraint_simulation.py",
        function="report_locked_arrival",
        code="CS-03",
        route="state",
        test=(
            "tests/test_constraint_simulation_page.py"
            "::test_arriving_from_a_home_locked_detail_says_the_equipment_is_the_session_one"
        ),
    ),
)

_IDS = [f"{item.code} {item.file.rsplit('/', 1)[-1]}::{item.function}" for item in WITHDRAWN]


@cache
def _tree(relative: str) -> ast.Module:
    return ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


def _top_function(relative: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    return next(
        (
            node
            for node in _tree(relative).body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
        ),
        None,
    )


def _texts_of(module: ast.Module) -> dict[str, str]:
    """모듈 맨 위 글 상수(이름 → 글) — `state(LAYOUT_ALERT, …)` 처럼 코드를 이름으로 줄 때 푼다."""
    return {
        node.targets[0].id: node.value.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def _module_texts(relative: str) -> dict[str, str]:
    return _texts_of(_tree(relative))


def _text_groups_of(module: ast.Module) -> dict[str, tuple[str, ...]]:
    """모듈 맨 위 글 묶음 상수(이름 → 글들) — `for code in LAYOUT_ALERT_CODES: state(code, …)` 처럼
    코드 묶음을 돌며 보낼 때 푼다. 묶음의 칸은 글 상수이거나 글 상수 이름이다."""
    texts = _texts_of(module)
    groups: dict[str, tuple[str, ...]] = {}
    for node in module.body:
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Tuple | ast.List)
        ):
            continue
        values = [_text(item, texts) for item in node.value.elts]
        if values and all(isinstance(value, str) for value in values):
            groups[node.targets[0].id] = tuple(str(value) for value in values)
    return groups


def _module_text_groups(relative: str) -> dict[str, tuple[str, ...]]:
    return _text_groups_of(_tree(relative))


def _text(node: ast.expr | None, constants: Mapping[str, str]) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _keyword(call: ast.Call, name: str, constants: Mapping[str, str]) -> object:
    return _text(next((item.value for item in call.keywords if item.arg == name), None), constants)


def _called(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def codes_sent_by(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    route: Literal["flash", "state"],
    constants: Mapping[str, str] | None = None,
    groups: Mapping[str, tuple[str, ...]] | None = None,
) -> set[str]:
    """함수가 그 길로 보내는 알림 코드 — 코드 · 종류는 글 상수나 모듈 상수 이름(`constants`)이고,
    상태 코드는 모듈 글 묶음(`groups`)을 도는 `for` 의 이름이어도 된다(묶음 코드를 모두 보낸다)."""
    known = constants or {}
    looped = {
        node.target.id: (groups or {})[node.iter.id]
        for node in ast.walk(function)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and isinstance(node.iter, ast.Name)
        and node.iter.id in (groups or {})
    }
    codes: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if route == "flash" and _called(node) == "queue_flash":
            if _keyword(node, "popup_only", known) is not True:
                continue
            alert = _keyword(node, "alert", known)
            kind = _keyword(node, "kind", known) or "success"
            codes.add(str(alert) if alert else alerts.FLASH_CODES[str(kind)])
        elif route == "state" and _called(node) == "state" and node.args:
            first = _text(node.args[0], known)
            if isinstance(first, str):
                codes.add(first)
            elif isinstance(node.args[0], ast.Name) and node.args[0].id in looped:
                codes.update(looped[node.args[0].id])
    return codes


# 선다고 보는 비교 — 같음 · 포함(`!=` · `not in` · `is not` 은 없음을 보는 단언이다).
_PRESENT_COMPARISONS = (ast.Eq, ast.In, ast.Is)


def _strings_outside_calls(node: ast.AST) -> set[str]:
    """식 안 글 상수 — 부름(`flashed(app, "warning")` · `states(app, "EQ-14")`)의 인자는 뺀다."""
    if isinstance(node, ast.Call):
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    found: set[str] = set()
    for child in ast.iter_child_nodes(node):
        found |= _strings_outside_calls(child)
    return found


def _is_none_check(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Is)
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )


def _present_codes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """함수가 선다고 단언하는 글 — 같음 · 포함 비교의 값(부름 인자 밖)과 `is None` 밖에서 쓴
    `active_state(…, "코드")` 의 코드(모듈 설명 3)."""
    parents = {child: node for node in ast.walk(function) for child in ast.iter_child_nodes(node)}
    found: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Compare):
            if all(isinstance(op, _PRESENT_COMPARISONS) for op in node.ops):
                for operand in (node.left, *node.comparators):
                    found |= _strings_outside_calls(operand)
        elif isinstance(node, ast.Call) and _called(node) == "active_state" and len(node.args) > 1:
            code = node.args[1]
            if (
                isinstance(code, ast.Constant)
                and isinstance(code.value, str)
                and not _is_none_check(parents.get(node))
            ):
                found.add(code.value)
    return found


def asserted_codes(test: str) -> set[str] | None:
    """시험 함수와 그 시험이 부르는 같은 파일 도우미(한 겹)가 선다고 단언하는 글. 시험이 없으면
    None."""
    relative, _, name = test.partition("::")
    function = _top_function(relative, name)
    if function is None:
        return None
    codes = _present_codes(function)
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            helper = _top_function(relative, node.func.id)
            if helper is not None:
                codes |= _present_codes(helper)
    return codes


def test_each_withdrawn_warning_is_listed_once() -> None:
    places = [(item.file, item.function, item.code) for item in WITHDRAWN]
    assert len(places) == len(set(places))
    assert all(item.what and item.why for item in WITHDRAWN)


@pytest.mark.parametrize("item", WITHDRAWN, ids=_IDS)
def test_the_code_is_registered_for_its_route(item: Withdrawn) -> None:
    """사건 길(`queue_flash`)은 사건 코드, 상태 길(`alerts.state`)은 상태 코드다."""
    assert item.code in alerts.REGISTRY, item.code
    expected = "event" if item.route == "flash" else "state"
    assert alerts.REGISTRY[item.code].kind == expected, item.code


@pytest.mark.parametrize("item", WITHDRAWN, ids=_IDS)
def test_the_withdrawn_place_still_sends_that_code(item: Withdrawn) -> None:
    """걷은 자리가 그 코드를 알림창 · Alarm 길로 보낸다 — 경고가 사라지지 않고 옮겨 갔다."""
    function = _top_function(item.file, item.function)
    assert function is not None, f"{item.file} 에 {item.function} 이 없습니다 — 표를 고치세요."
    sent = codes_sent_by(
        function, item.route, _module_texts(item.file), _module_text_groups(item.file)
    )
    assert item.code in sent, (
        f"{item.file} {item.function} 이 {item.code} 를 "
        + ("queue_flash(…, popup_only=True)" if item.route == "flash" else "alerts.state")
        + " 로 보내지 않습니다."
    )


@pytest.mark.parametrize("item", WITHDRAWN, ids=_IDS)
def test_the_screen_test_asserts_that_code(item: Withdrawn) -> None:
    """화면 시험이 그 코드가 **선다고** 단언한다 — 해소로 불린다는 것만 보면 걷은 경고가 사라져도
    모른다(UI-NTF-05)."""
    codes = asserted_codes(item.test)
    assert codes is not None, f"화면 시험이 없습니다: {item.test}"
    assert item.code in codes, (
        f"{item.test} 이 {item.code} 가 선다고 단언하지 않습니다 — 조건을 만들고"
        f' active_state(app, "{item.code}") 나 note["code"] == "{item.code}" 로 봅니다.'
    )


def test_the_route_reader_tells_flash_and_state_codes_apart() -> None:
    """`codes_sent_by` 는 `popup_only` 없는 결과 알림(버튼 곁에도 그림)을 세지 않고, 코드를 모듈
    상수 이름으로 준 상태 알림은 그 상수를, 모듈 코드 묶음을 도는 `for` 이름은 그 묶음을 푼다."""
    (function,) = ast.parse(
        "def f():\n"
        "    queue_flash(KEY, text, kind='warning')\n"
        "    queue_flash(KEY, text, kind='warning', popup_only=True)\n"
        "    queue_flash(KEY, text, kind='warning', alert='EQ-05', popup_only=True)\n"
        "    alerts.state('EQ-06', scope=None, content=None, active=False)\n"
        "    alerts.state(LAYOUT_ALERT, scope=None, content=None, active=False)\n"
        "    for code in LAYOUT_CODES:\n"
        "        alerts.state(code, scope=None, content=None, active=False)\n"
    ).body
    assert isinstance(function, ast.FunctionDef)

    assert codes_sent_by(function, "flash") == {"FL-03", "EQ-05"}
    assert codes_sent_by(function, "state") == {"EQ-06"}
    assert codes_sent_by(function, "state", {"LAYOUT_ALERT": "EQ-13"}) == {"EQ-06", "EQ-13"}
    assert codes_sent_by(function, "state", {}, {"LAYOUT_CODES": ("EQ-14", "EQ-15")}) == {
        "EQ-06",
        "EQ-14",
        "EQ-15",
    }


def test_the_group_reader_resolves_named_codes_in_a_module_tuple() -> None:
    """코드 묶음 상수의 칸은 글 상수 이름이어도 풀고, 못 푸는 칸이 하나라도 있으면 묶음으로 보지
    않는다(모르는 코드를 보낸다고 읽지 않게)."""
    module = ast.parse(
        "FIRST = 'EQ-13'\n"
        "SECOND = 'EQ-14'\n"
        "CODES = (FIRST, SECOND, 'EQ-15')\n"
        "MIXED = (FIRST, unknown)\n"
    )

    assert _text_groups_of(module) == {"CODES": ("EQ-13", "EQ-14", "EQ-15")}


def test_the_assertion_reader_counts_only_codes_that_must_stand() -> None:
    """선다는 단언(같음 · 포함 비교의 값, `is None` 밖에서 쓴 `active_state`)만 세고, 해소만 보는
    단언(`states` 의 `active` 가 거짓 · `active_state(…) is None` · `not in`) · 부름 인자 · 설명
    글의 코드는 세지 않는다."""
    (function,) = ast.parse(
        "def t(app, codes):\n"
        "    '''EQ-01 을 본다.'''\n"
        "    note = active_state(app, 'EQ-02')\n"
        "    assert note['code'] == 'FL-03'\n"
        "    assert all(item.code == 'EQ-05' for item in flashed(app, 'warning'))\n"
        "    assert active_state(app, 'EQ-06') is None\n"
        "    assert [n['active'] for n in states(app, 'EQ-07')] == [False]\n"
        "    for code in ('EQ-08',):\n"
        "        assert not any(n['active'] for n in states(app, code))\n"
        "    assert 'EQ-09' not in codes\n"
    ).body
    assert isinstance(function, ast.FunctionDef)

    assert {code for code in _present_codes(function) if "-" in code} == {
        "EQ-02",
        "FL-03",
        "EQ-05",
    }
