# Purpose: 자리에서 걷은 경고마다 등록부 코드 · 보내는 부름 · 그 코드를 단언하는 화면 시험을 맞댄다.

"""걷은 경고 ↔ 알림 짝(설계 규칙 UI-NTF-05 — `docs/design_rules.md` 5-2).

숫자를 믿기 전에 알아야 할 문제는 숨기지 않는다 — 경고를 자리에서 걷어도 알림창 · Alarm 에 남는다
(UI-NTF-05). 이 그물은 자리에서 걷은 경고마다 한 줄(`WITHDRAWN`)을 두고 셋을 맞댄다.

1. 코드가 등록부(`alerts.REGISTRY`)에 있고 갈래가 보내는 길과 맞다 — 동작 뒤 한 번 일어난 경고는
   사건(`flash.queue_flash(…, popup_only=True)` — 버튼 곁에 그리지 않고 알림창 · Alarm 에만),
   조건이 남은 동안의 경고는 상태(`alerts.state`)다.
2. 걷은 자리(파일 · 맨 바깥 함수)가 지금도 그 코드로 보낸다 — `queue_flash` 는 `popup_only=True` 와
   종류(`kind=`)의 기본 코드(`alerts.FLASH_CODES`) 또는 `alert=` 코드, 상태는 `state("코드", …)`.
3. 그 화면 시험이 있고 그 코드를 단언한다 — 시험 함수(와 그 시험이 부르는 같은 파일 도우미 한 겹)의
   본문 글 상수에 코드가 있다(설명 글 밖).

새 경고를 자리에서 걷으면 같은 변경에서 이 표에 한 줄을 더한다(PRC-01). 2026-11-04 설계 규칙 확인
보드 AMB-05 (나)(사이드바 저장 칸 밑 남은 Capa 계산 오류 · HOME 주요 Case 칩 경고 — 둘 다 알림창
· Alarm 으로)와 같은 날 걷은 저장 뒤 경고 · 가용설비 「한쪽에만 있는 공정」 줄이 첫 줄들이다.
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


# Space 「Space 도면」 상자 끝 줄 넷(V-09)을 함께 단언하는 화면 시험 — 가정 설비 시나리오에서 넷
# 모두를 회차마다 부르고(없는 것은 해소) 상자 · 본문에 그 줄이 없음을 본다.
_SPACE_BOX_TEST = (
    "tests/test_space_sidebar_box.py"
    "::test_an_assumption_raises_the_unscheduled_and_layout_alerts_and_keeps_the_box_to_controls"
)

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
        test=_SPACE_BOX_TEST,
    ),
    Withdrawn(
        what="Space 사이드바 「Space 도면」 상자 끝 — 공통 대장에서 지운 호기의 배치 차이 줄",
        why="V-09 · UI-TXT-01 · UI-NTF-02",
        file="src/capa_simulation/components/space_floor_layout.py",
        function="report_layout_notices",
        code="EQ-15",
        route="state",
        test=_SPACE_BOX_TEST,
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


def _body_strings(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """함수 본문의 글 상수 — 맨 앞 설명 글은 뺀다."""
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return {
        node.value
        for statement in body
        for node in ast.walk(statement)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def asserted_strings(test: str) -> set[str] | None:
    """시험 함수와 그 시험이 부르는 같은 파일 도우미(한 겹)의 본문 글 상수. 시험이 없으면 None."""
    relative, _, name = test.partition("::")
    function = _top_function(relative, name)
    if function is None:
        return None
    strings = _body_strings(function)
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            helper = _top_function(relative, node.func.id)
            if helper is not None:
                strings |= _body_strings(helper)
    return strings


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
    strings = asserted_strings(item.test)
    assert strings is not None, f"화면 시험이 없습니다: {item.test}"
    assert item.code in strings, f"{item.test} 이 {item.code} 를 단언하지 않습니다."


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
