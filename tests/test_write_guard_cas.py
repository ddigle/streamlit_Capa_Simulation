# Purpose: 본 값 대조·제 저장 판정이 write_guard 한 길인지 소스 그물과 두 누름 경합으로 본다.

"""비교 후 쓰기(CAS)의 세 규칙(`components/write_guard.py`, AGENTS 9장 「쓰기 콜백은 빠른 두 번
누름을 거른다」).

- **소스 그물(AST).** 화면 모듈에서 충돌 예외 10종을 잡는 자리(그 예외 이름의 `except`, 또는 넓게
  잡은 뒤 `if isinstance(exc, 충돌 예외)` 로 가르는 갈래)는 모두 제 저장을 판정한다(`is_own_save`) —
  빠뜨리면 더블클릭의 둘째 누름이 방금 한 제 저장을 「다른 사용자가 먼저」 로 알린다. 본 값을 지금
  값으로 대체하지 않는다 — `seen(…)`(또는 그것을 받은 이름·BASE·SEEN 칸 읽기)에 상수가 아닌 대체값을
  다는 `… if … else …`·`… or …` 꼴이다. 대체하면 남의 저장 뒤 한 회차만 돌아도 대조가 지나 그 저장을
  덮는다(`expected_*` 에 `.version`·`current` 를 대체로 다는 꼴도 따로 본다). 이름 토막에
  BASE(S)·SEEN 이 든 세션 칸(본 값)은 write_guard 만 적는다 — `[…] =` 대입·`.setdefault(…)`·속성
  대입 모두.
- **두 누름 경합.** 브라우저 더블클릭은 둘째 누름이 닿는 순간 돌던 회차에 멈춤을 건다 — 첫 회차는 DB
  에 쓴 뒤 다음 세션 칸 접근에서 끊긴다(`StopException`). 시험은 첫 회차의 쓰기 직후 그 회차에
  멈춤을 걸고(`ScriptRequests.request_stop` — 브라우저와 같은 자리에서 끊긴다), 같은 누른 화면(위젯
  값)으로 둘째 회차를 다른 스레드의 `app._run` 으로 세운다(`tests/test_voc_page.py` 의 `_race` 꼴).
  네 자리(리비전명 바꾸기·공식 지정·설비 「리비전 저장」·자동 갱신 설정)에서 더블클릭은 한 번만
  쓰고 성공 알림만 남기고(버전 대조 폼 셋 — 표시순서·Proc Rename·판정 기준 — 은 저장소 쓰기 뒤
  뒷정리에서 끊겨도 같다: 제 저장 짝은 뒷정리 앞에 적는다), 남이 먼저 저장한 뒤의 옛 화면
  더블클릭은 둘 다 거절한다. 그 옛 화면 더블클릭은 버전 대조 폼 넷(자동 갱신 설정·판정 기준·확보율
  보정·Proc Rename)에서 모두 거부 표지 창을 0 으로 두고 본 값 대조만으로 거절되는지 본다 — 제출
  회차에 본 값을 올리면(「결과가 무엇이든 올림」) 둘째 누름이 대조를 지나 실패한다.
- **거부 표지 창.** Cut-off 는 충돌 회차가 초안·출발점을 최신으로 다시 세운다(초안을 세우는 자리).
  창 안의 둘째 누름은 저장하지 않고 그 거부를 다시 알린다 — 「저장했습니다」 가 거부를 덮지 않는다.
"""

from __future__ import annotations

import ast
import re
import threading
from collections.abc import Iterator
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, load, send_ops
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
from streamlit.testing.v1 import AppTest
from test_admin_area_page import _rename_component_script
from test_all_pages_render import _page_script as _scenario_page_script
from test_auto_official_update_tab import _field, _tab, _with_w40
from test_display_order_management import _version_check_script as _display_order_script
from test_equipment_master_tab_scenarios import OPERATIONS, _page
from test_equipment_scenario_layout_management import _moved_setup, _section
from test_equipment_scenario_layout_management import _texts as _section_texts
from test_equipment_scenario_repository import _request as _equipment_request
from test_equipment_scenario_repository import _seeded
from test_equipment_scenario_repository import _session as _equipment_session
from test_equipment_scenario_repository import _set as _equipment_set
from test_scenario_management_page import (
    PAGE_PATH,
    _check_row,
    _official_button,
    _open_official,
    _shown_key,
)
from test_threshold_editor import SAVE_LABEL as THRESHOLD_SAVE_LABEL
from test_threshold_editor import _app as _threshold_app
from widget_browser import BrowserTables

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.cutoff_management import (
    CUTOFF_BASE_KEY,
    CUTOFF_DRAFT_KEY,
)
from capa_simulation.components.display_order_management import DISPLAY_ORDER_SAVED_MESSAGE
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
)
from capa_simulation.components.equipment_scenario_management import (
    CLEAR_LAYOUT_BUTTON_KEY,
    CLEAR_LAYOUT_CONFIRM_KEY,
    FLASH_KEY,
    PENDING_REVISION_KEY,
    PUBLISH_BUTTON_KEY,
    REVISION_KEY,
    SCENARIO_KEY,
)
from capa_simulation.components.home_preference import THRESHOLD_SAVED_MESSAGE
from capa_simulation.components.process_rename_management import PROCESS_RENAME_SAVED_MESSAGE
from capa_simulation.components.scenario_management import REVISION_EDITOR_KEY
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.persistence.cache import (
    clear_global_display_order_cache,
    clear_global_execution_capacity_cache,
    clear_global_process_rename_cache,
    clear_global_securement_threshold_cache,
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_process_cutoff_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.auto_official_update import AutoUpdateConfig
from capa_simulation.services.execution_capacity import EXECUTION_CAPACITY_COLUMNS
from capa_simulation.services.securement_threshold import empty_securement_threshold_rows

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_FILES = sorted(
    [
        PROJECT_ROOT / "app.py",
        *(PROJECT_ROOT / "app_pages").rglob("*.py"),
        *(PROJECT_ROOT / "src" / "capa_simulation" / "components").rglob("*.py"),
    ]
)
SOURCE_FILES = sorted(
    [
        PROJECT_ROOT / "app.py",
        *(PROJECT_ROOT / "app_pages").rglob("*.py"),
        *(PROJECT_ROOT / "src" / "capa_simulation").rglob("*.py"),
    ]
)
WRITE_GUARD = PROJECT_ROOT / "src" / "capa_simulation" / "components" / "write_guard.py"

# 비교 후 쓰기가 남의 쓰기로 거부할 때 내는 예외 — 화면이 잡으면 제 저장을 판정해야 한다.
CONFLICTS = frozenset(
    {
        "ProfileVersionConflict",
        "SecurementThresholdConflict",
        "AutoOfficialUpdateSettingsConflict",
        "ProcessCutoffConflict",
        "EquipmentRevisionConflict",
        "EquipmentReleaseMoved",
        "EquipmentScenarioNameMoved",
        "EquipmentScheduleRevisionNameMoved",
        "OfficialReleaseMoved",
        "RevisionNameMoved",
    }
)
OWN_CHECKS = frozenset({"is_own_save", "is_own_profile_save"})
# 제 저장일 수 없는 충돌(모듈 파일 이름 → 예외 이름). 판정을 넣으면 실행될 수 없는 갈래만 는다.
NOT_OWN_SAVE_CONFLICTS = {
    # HOME 주요 Case — 쓰기는 대조 없이(`expected_version` 없이) 하고, 충돌은 「리비전만 고른 쓰기」
    # 의 시나리오 대조(그 Case 의 지금 시나리오 ≠ 고른 짝의 시나리오)뿐이라 지금 짝이 고른 짝일 수
    # 없다. 같은 짝을 겹쳐 고른 둘째 콜백은 쓰기 전 「지금 짝과 같으면 쓰지 않음」 이 거른다.
    "home_main_cases.py": frozenset({"ProfileVersionConflict"}),
}
# 대조 값의 대체로 보는 「지금 값」 — 프로필 version 과 그 회차에 다시 읽은 지금 이름.
CURRENT_ATTRIBUTES = frozenset({"version"})
CURRENT_NAMES = frozenset({"current"})
# 본 값을 이름 토막으로 알아보는 말 — 「bases」 는 여러 층의 본 값 묶음(`PENDING_BASES_KEY`).
SEEN_PARTS = frozenset({"base", "bases", "seen"})
# 이름에 BASE·SEEN 이 들었지만 write_guard 밖에서 적는 세션 칸(모듈 파일 이름, 칸 이름).
NOT_SEEN_TOKENS = {
    # 위젯이 아닌 탐색 표지 — HOME 이 본 공정 목록, 상세·제약 화면이 받은 주소 인자.
    ("home.py", "PROCESS_SEEN_KEY"),
    ("process_detail_state.py", "PROCESS_DETAIL_QUERY_SEEN_KEY"),
    ("constraint_simulation_state.py", "CONSTRAINT_QUERY_SEEN_KEY"),
    # 입장 화면 Summary 를 이 세션이 한 번 본 표지(읽기를 미룰지) — 대조 값이 아니다.
    ("intro_summary.py", "_SEEN_KEY"),
    # Qual 마감 계산기의 「기존 대수」 입력 칸 — 위젯 값이다.
    ("qual_deadline_calculator.py", "BASE_KEY"),
    # 층 배치 대기분이 본 저장값(층마다 첫 대기분의 것) — 비교 후 쓰기 남은 자리로 docs/TODO.md 에
    # 적어 두고 그대로 둔 것이다(대기분과 함께 세우고 버린다 — 충돌 예외는 10종 밖).
    ("equipment_data_workspace.py", "PENDING_BASES_KEY"),
}


# ------------------------------------------------------------------ 소스 그물


def _names(node: ast.expr | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Tuple):
        return set().union(*(_names(item) for item in node.elts))
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def _called(node: ast.AST) -> set[str]:
    called: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                called.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                called.add(child.func.attr)
    return called


def _conflict_test(node: ast.expr, conflicts: frozenset[str]) -> bool:
    """`isinstance(…, 충돌 예외)` 를 담은 조건인가."""
    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "isinstance"
        and len(child.args) == 2
        and bool(_names(child.args[1]) & conflicts)
        for child in ast.walk(node)
    )


def unjudged_conflicts(source: str, exempt: frozenset[str] = frozenset()) -> list[int]:
    """충돌 예외를 잡고도 제 저장을 판정하지 않는 줄 — 그 예외 이름의 except 와, 넓게 잡은 뒤
    `if isinstance(exc, 충돌 예외)` 로 가르는 if. 같은 모듈 함수로 넘겨 판정해도 된다. `exempt` 는
    제 저장일 수 없는 충돌 이름이다(`NOT_OWN_SAVE_CONFLICTS`)."""
    conflicts = CONFLICTS - exempt
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }

    def judges(node: ast.AST, seen: frozenset[str]) -> bool:
        called = _called(node)
        if called & OWN_CHECKS:
            return True
        return any(
            judges(functions[name], seen | {name})
            for name in called
            if name in functions and name not in seen
        )

    found = [
        handler.lineno
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and _names(handler.type) & conflicts
        and not judges(ast.Module(body=handler.body, type_ignores=[]), frozenset())
    ]
    found += [
        branch.lineno
        for branch in ast.walk(tree)
        if isinstance(branch, ast.If)
        and _conflict_test(branch.test, conflicts)
        and not judges(ast.Module(body=branch.body, type_ignores=[]), frozenset())
    ]
    return sorted(found)


def _mentions_current(node: ast.AST) -> bool:
    return any(
        (isinstance(child, ast.Attribute) and child.attr in CURRENT_ATTRIBUTES)
        or (isinstance(child, ast.Name) and child.id in CURRENT_NAMES)
        for child in ast.walk(node)
    )


def current_fallbacks(source: str) -> list[int]:
    """`expected_*` 대조 값을 IfExp·BoolOp 로 지금 값(`.version`·`current`)으로 대체하는 줄."""
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg and node.arg.startswith("expected"):
            value: ast.expr | None = node.value
            line = node.value.lineno
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.startswith("expected")
        ):
            value, line = node.value, node.lineno
        else:
            continue
        if isinstance(value, ast.IfExp | ast.BoolOp) and _mentions_current(value):
            found.append(line)
    return found


def _seen_word(word: str) -> bool:
    return bool({part for part in re.split(r"[^a-z0-9]+", word.lower()) if part} & SEEN_PARTS)


def _session_state(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "session_state"


def _seen_read(node: ast.expr, seen_names: set[str]) -> bool:
    """본 값 읽기 — `seen(…)` 부름, 그것을 받은 이름, BASE·SEEN 세션 칸 읽기(`.get(…)`·`[…]`)."""
    if isinstance(node, ast.Name):
        return node.id in seen_names
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "seen":
            return True
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and _session_state(node.func.value)
            and node.args
        ):
            return any(_seen_word(word) for word in _tokens(node.args[0]))
    if isinstance(node, ast.Subscript) and _session_state(node.value):
        return any(_seen_word(word) for word in _tokens(node.slice))
    return False


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
# 「비었음」 을 만드는 부름 — 대체값이 아니라 「없음을 본 것」 이다.
_EMPTY_MAKERS = frozenset({"frozenset", "dict", "list", "tuple", "set", "str", "int", "float"})


def _scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """한 영역(모듈·함수)의 마디 — 안쪽 함수·클래스로는 내려가지 않는다(이름은 영역마다 따로다)."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def _no_value(node: ast.expr) -> bool:
    """상수·빈 묶음·빈 생성(`frozenset()`) — 지금 값이 아니라 「없음」 이다."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return not node.elts
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _EMPTY_MAKERS
        and not node.args
        and not node.keywords
    )


def seen_fallbacks(source: str) -> list[int]:
    """본 값에 지금 값 같은 대체값을 다는 줄 — `본 값 if … else 다른 값`(또는 거꾸로)·`본 값 or 다른
    값`. 상수·빈 묶음(빈 이름 `""`·None·`frozenset()`)은 대체가 아니라 「없음을 본 것」 이라
    허용한다. 본 값을 받은 이름은 영역(모듈·함수)마다 따로 센다."""
    tree = ast.parse(source)
    found: list[int] = []
    scopes = [tree, *(node for node in ast.walk(tree) if isinstance(node, _SCOPES))]
    for scope in scopes:
        found += _scope_seen_fallbacks(list(_scope_nodes(scope)))
    return sorted(found)


def _scope_seen_fallbacks(nodes: list[ast.AST]) -> list[int]:
    seen_names = {
        target.id
        for node in nodes
        if isinstance(node, ast.Assign) and _seen_read(node.value, set())
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    found: list[int] = []
    for node in nodes:
        if isinstance(node, ast.IfExp):
            pairs = [(node.body, node.orelse), (node.orelse, node.body)]
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            pairs = [
                (value, rest)
                for index, value in enumerate(node.values)
                for rest in node.values[index + 1 :]
            ]
        else:
            continue
        if any(_seen_read(value, seen_names) and not _no_value(other) for value, other in pairs):
            found.append(node.lineno)
    return found


def _tokens(node: ast.AST) -> list[str]:
    words: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            words.append(child.id)
        elif isinstance(child, ast.Attribute):
            words.append(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            words.append(child.value)
    return words


def seen_slot_writes(source: str, module: str) -> list[tuple[int, str]]:
    """세션에 이름(토막)에 BASE(S)·SEEN 이 든 칸을 적는 줄과 그 이름 — `st.session_state[…] =`
    대입, `st.session_state.setdefault(…)`, `st.session_state.이름 =` 속성 대입."""
    found: list[tuple[int, str]] = []

    def note(line: int, words: list[str]) -> None:
        for word in words:
            if _seen_word(word) and (module, word) not in NOT_SEEN_TOKENS:
                found.append((line, word))
                return

    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setdefault"
            and _session_state(node.func.value)
            and node.args
        ):
            note(node.lineno, _tokens(node.args[0]))
            continue
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Subscript) and _session_state(target.value):
                note(node.lineno, _tokens(target.slice))
            elif isinstance(target, ast.Attribute) and _session_state(target.value):
                note(node.lineno, [target.attr])
    return sorted(found)


def _relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def test_every_conflict_handler_in_the_screens_judges_an_own_save() -> None:
    """충돌 예외 10종을 잡는 화면 자리는 모두 `is_own_save` 를 부른다(2026-10-26 E2E — 리비전명·
    공식 지정·설비 이름·Cut-off 저장의 더블클릭이 「다른 사용자가 먼저」 로 끝났다). 제 저장일 수
    없는 충돌만 빼 둔다(`NOT_OWN_SAVE_CONFLICTS`)."""
    missing = [
        f"{_relative(path)}:{line}"
        for path in UI_FILES
        for line in unjudged_conflicts(
            path.read_text(encoding="utf-8"), NOT_OWN_SAVE_CONFLICTS.get(path.name, frozenset())
        )
    ]
    assert missing == []
    exempt = [
        name for name in NOT_OWN_SAVE_CONFLICTS if not any(path.name == name for path in UI_FILES)
    ]
    assert exempt == []


def test_no_expected_argument_falls_back_to_the_value_read_this_run() -> None:
    """`expected_*=` 대조 값이 「본 값이 없으면 지금 값」 으로 대체되지 않는다 — 본 값은
    `write_guard.seen` 이 대체값 없이 돌려준다. 다른 이름을 거친 대체(`base = 본 값 if … else
    settings.version`)와 `.version`·`current` 밖의 지금
    값(`latest.release_no`·`scenario.scenario_name`) 도 본 값 쪽에서 잡는다."""
    found = [
        f"{_relative(path)}:{line}"
        for path in UI_FILES
        for line in sorted(
            {
                *current_fallbacks(path.read_text(encoding="utf-8")),
                *seen_fallbacks(path.read_text(encoding="utf-8")),
            }
        )
    ]
    assert found == []


def test_seen_and_base_slots_are_written_only_through_write_guard() -> None:
    """이름에 BASE·SEEN 이 든 세션 칸(본 값)은 `write_guard.remember_seen` 만 적는다 — 화면마다 따로
    적으면 「제출 회차에도 올림」·「결과와 상관없이 올림」 이 다시 생긴다."""
    found = [
        f"{_relative(path)}:{line} {word}"
        for path in SOURCE_FILES
        if path != WRITE_GUARD
        for line, word in seen_slot_writes(path.read_text(encoding="utf-8"), path.name)
    ]
    assert found == []


def test_the_source_checks_catch_the_old_shapes() -> None:
    """그물이 고치기 전 꼴을 잡는다 — 자동 갱신 설정의 대체·올림과 판정 없는 충돌 처리."""
    old = """
def form(repository, settings):
    submitted_base = st.session_state.get(SETTINGS_BASE_VERSION_KEY)
    if not submitted:
        st.session_state[SETTINGS_BASE_VERSION_KEY] = settings.version
        return
    expected_version = submitted_base if isinstance(submitted_base, int) else settings.version
    try:
        repository.rename(expected_name=seen_name if isinstance(seen_name, str) else current)
    except EquipmentScenarioNameMoved as exc:
        st.error(str(exc))
"""
    assert current_fallbacks(old) == [7, 9]
    assert seen_fallbacks(old) == [7]
    assert unjudged_conflicts(old) == [10]
    assert seen_slot_writes(old, "auto_official_update_tab.py") == [
        (5, "SETTINGS_BASE_VERSION_KEY")
    ]
    assert seen_slot_writes("st.session_state[f'{key}__seen'] = name", "x.py") == [(1, "__seen")]


def test_the_source_checks_catch_the_disguised_shapes() -> None:
    """2026-10-26 리뷰가 그물 함수에 넣어 본 꼴 — 지금 값이 `.version`·`current` 가 아니거나 다른
    이름을 거친 대체, 넓게 잡고 `isinstance` 로 가르는 충돌 처리(고치기 전 자동 갱신 설정·판정
    기준의 꼴), 이름 토막 `bases`·`setdefault`·속성 대입으로 적는 본 값 칸. 상수 대체(「없음을 본
    것」)는 허용한다."""
    disguised = """
def form(repository, settings, scenario, latest):
    expected_no = seen(K) if isinstance(seen(K), int) else latest.release_no
    name = seen(NAME_KEY)
    repository.rename(expected_name=name if isinstance(name, str) else scenario.scenario_name)
    submitted = st.session_state.get(SETTINGS_BASE_VERSION_KEY)
    base = submitted if isinstance(submitted, int) else settings.version
    held = seen(REVISION_KEY)
    shown = held if isinstance(held, str) else ""
    fallback = seen(OTHER_KEY) or settings.version
    try:
        repository.save(expected_version=base)
    except BOOTSTRAP_ERRORS as exc:
        if isinstance(exc, ProfileVersionConflict):
            st.error(str(exc))
        else:
            st.error("x")
    st.session_state[PENDING_BASES_KEY] = {}
    st.session_state.setdefault(SETTINGS_BASE_VERSION_KEY, 0)
    st.session_state.threshold_base_version = 1
"""
    assert current_fallbacks(disguised) == []
    assert seen_fallbacks(disguised) == [3, 5, 7, 10]
    assert unjudged_conflicts(disguised) == [14]
    assert seen_slot_writes(disguised, "x.py") == [
        (18, "PENDING_BASES_KEY"),
        (19, "SETTINGS_BASE_VERSION_KEY"),
        (20, "threshold_base_version"),
    ]
    assert seen_slot_writes(disguised, "equipment_data_workspace.py")[0] == (
        19,
        "SETTINGS_BASE_VERSION_KEY",
    )


# ------------------------------------------------------------------ 도우미


def _session_app(body: str) -> AppTest:
    return AppTest.from_string(
        "import streamlit as st\n"
        "import capa_simulation.components.write_guard as write_guard\n" + body,
        default_timeout=30,
    )


def test_seen_returns_no_fallback_and_own_save_needs_the_exact_pair() -> None:
    """본 값은 대체값 없이 돌려준다(없으면 None). 제 저장은 (본 값, 저장된 값) 짝이 정확히 같을 때만
    — int·str·tuple 어느 토큰이든 같다. 옛 이름은 별칭이다."""
    app = _session_app(
        """
results = st.session_state.setdefault("results", [])
results.append(write_guard.seen("missing"))
write_guard.remember_seen("slot", (3, "a"))
results.append(write_guard.seen("slot"))
st.session_state["weird"] = True
results.append(write_guard.seen("weird"))
write_guard.forget_seen("slot")
results.append(write_guard.seen("slot"))
marks = write_guard.own_save_marks()
write_guard.remember_own_save("v", 1, 2, marks)
write_guard.remember_own_save("name", "옛", "새")
write_guard.remember_own_save("pair", ("c1", "s1"), ("c2", "s1"))
results.append(
    (
        write_guard.is_own_save("v", 1, 2),
        write_guard.is_own_save("v", 1, 3),
        write_guard.is_own_save("v", None, 2),
        write_guard.is_own_save("name", "옛", "새", marks),
        write_guard.is_own_save("name", "옛", "남이 바꾼 이름"),
        write_guard.is_own_save("pair", ("c1", "s1"), ("c2", "s1")),
        write_guard.is_own_save("pair", ("c1", "s1"), ("c3", "s1")),
        write_guard.is_own_profile_save("v", 1, 2),
        write_guard.profile_save_marks() is marks,
    )
)
"""
    ).run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["results"] == [
        None,
        (3, "a"),
        None,
        None,
        (True, False, False, True, False, True, False, True, True),
    ]


def test_a_refusal_is_drawn_once_on_the_next_run() -> None:
    """거부 회차가 담은 알림은 다음 회차에 한 번만 꺼낸다(`queue_refusal`·`take_refusal`)."""
    app = _session_app(
        """
taken = st.session_state.setdefault("taken", [])
if not st.session_state.get("queued"):
    st.session_state["queued"] = True
    write_guard.queue_refusal("form", "다른 사용자가 먼저 저장했습니다.")
taken.append(write_guard.take_refusal("form"))
"""
    )
    app.run()
    app.run()
    assert app.session_state["taken"] == ["다른 사용자가 먼저 저장했습니다.", None]


# ------------------------------------------------------------------ 두 누름 경합


def _press_twice(
    app: AppTest,
    monkeypatch: pytest.MonkeyPatch,
    pressed: WidgetStates,
    *,
    cls: type,
    write: str,
) -> AppTest:
    """누른 화면(`pressed`)의 같은 누름 둘 — 첫 회차가 저장소 `cls.write` 를 마치는(또는 거부받는)
    순간 둘째 누름이 닿아 첫 회차에 멈춤이 걸린다. 첫 회차는 그 뒤 다음 세션 칸 접근에서 끊기고,
    둘째 회차는 다른 스레드의 `app._run` 으로 같은 위젯 값을 보낸다. 화면은 둘째 회차의 것이다."""
    original = getattr(cls, write)

    def interrupted(self: object, *args: Any, **kwargs: Any) -> Any:
        try:
            return original(self, *args, **kwargs)
        finally:
            monkeypatch.setattr(cls, write, original)
            context = get_script_run_ctx()
            assert context is not None and context.script_requests is not None
            context.script_requests.request_stop()

    monkeypatch.setattr(cls, write, interrupted)
    app._run(widget_state=pressed)
    assert getattr(cls, write) is original, "첫 누름이 저장소에 닿지 않았습니다"
    second = threading.Thread(target=lambda: app._run(widget_state=pressed))
    second.start()
    second.join(timeout=180)
    assert not second.is_alive()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest, kind: str) -> list[str]:
    return [str(item.value) for item in getattr(app, kind)]


@pytest.fixture
def no_trailing_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """거부 표지 창(`TRAILING_PRESS_SECONDS`)을 0 으로 — 남의 저장 뒤 둘째 누름이 창이 아니라 본 값
    대조로 거절되는지 본다(창은 첫 회차가 거부를 적기 전에 끊기면 아무것도 막지 못한다)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)


# 자동 갱신 설정 ---------------------------------------------------------------


def _settings_pressed(app: AppTest, keyword: str) -> WidgetStates:
    _field(app.text_input, "시뮬레이션명 키워드").set_value(keyword)  # type: ignore[attr-defined]
    next(button for button in app.button if button.label == "설정 저장").click()
    return app._tree.get_widget_states()


def test_a_double_press_of_the_auto_update_settings_saves_once_and_says_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 누름이 저장한 직후 끊기면 둘째 누름의 대조가 저장 전 version 이라 저장소가 거부했고, 자동
    갱신 설정은 제 저장 판정이 없어 「다른 사용자가 먼저 저장」 을 알렸다."""
    database = tmp_path / "auto.duckdb"
    repository = _with_w40(database)
    app = _tab(database)

    _press_twice(
        app,
        monkeypatch,
        _settings_pressed(app, "PSS"),
        cls=DuckDBScenarioRepository,
        write="replace_auto_official_update_settings",
    )

    assert _texts(app, "error") == []
    assert [text for text in _texts(app, "success") if "자동 갱신 설정을" in text] == [
        "자동 갱신 설정을 저장했습니다 — 키워드 PSM → PSS"
    ]
    stored = repository.load_auto_official_update_settings()
    assert (stored.version, stored.config.keyword) == (1, "PSS")


def test_a_slow_double_press_of_the_auto_update_settings_repeats_the_success(
    tmp_path: Path,
) -> None:
    """느린 더블클릭(0.4초 — 둘째 누름이 첫 저장 뒤 새로 그린 화면에 닿는다)은 같은 값이라
    「바뀐 값이 없습니다」 가 방금 성공 알림을 덮었다(브라우저 확인 2026-10-26). 창 안이면 방금
    성공을 다시 알린다."""
    database = tmp_path / "auto.duckdb"
    repository = _with_w40(database)
    app = _tab(database)
    pressed = _settings_pressed(app, "PSS")
    app.run()
    assert any("자동 갱신 설정을 저장했습니다" in text for text in _texts(app, "success"))

    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    assert "바뀐 값이 없습니다." not in _texts(app, "info")
    assert [text for text in _texts(app, "success") if "자동 갱신 설정을" in text] == [
        "자동 갱신 설정을 저장했습니다 — 키워드 PSM → PSS"
    ]
    assert repository.load_auto_official_update_settings().version == 1


def test_an_old_screen_double_press_after_another_save_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_trailing_window: None
) -> None:
    """3회차 꼴 — 남이 먼저 저장한 뒤 옛 화면에서 「설정 저장」 을 두 번 누른다. 첫 누름의 회차가
    편집 시작 version 을 그 회차가 그린 최신으로 올려(「결과가 무엇이든」), 거부를 적기 전에 끊기면
    둘째 누름이 옛 입력으로 대조를 지나 남의 저장을 덮었다. 충돌·제출 회차는 본 값을 올리지
    않는다."""
    database = tmp_path / "auto.duckdb"
    repository = _with_w40(database)
    app = _tab(database)
    settings = repository.load_auto_official_update_settings()
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(enabled=False, check_time=time(8, 0), keyword="PSM", threshold=0.9),
        expected_version=settings.version,
    )

    _press_twice(
        app,
        monkeypatch,
        _settings_pressed(app, "PSS"),
        cls=DuckDBScenarioRepository,
        write="replace_auto_official_update_settings",
    )

    errors = _texts(app, "error")
    assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
    assert not [text for text in _texts(app, "success") if "자동 갱신 설정을" in text]
    stored = repository.load_auto_official_update_settings()
    assert (stored.version, stored.config.keyword) == (1, "PSM")


def test_a_refused_settings_save_draws_the_latest_and_the_next_press_saves(
    tmp_path: Path, no_trailing_window: None
) -> None:
    """거부 회차는 본 값을 올리지 않고 앱을 다시 돌린다 — 다음 회차가 최신을 그리며 적으므로 새
    화면을 보고 다시 누른 저장은 지난다."""
    database = tmp_path / "auto.duckdb"
    repository = _with_w40(database)
    app = _tab(database)
    settings = repository.load_auto_official_update_settings()
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(enabled=False, check_time=time(8, 0), keyword="PSM", threshold=0.9),
        expected_version=settings.version,
    )
    _settings_pressed(app, "PSS")
    app.run()
    assert any("다른 사용자가 먼저" in text for text in _texts(app, "error"))

    _settings_pressed(app, "PSX")
    app.run()

    assert _texts(app, "error") == []
    stored = repository.load_auto_official_update_settings()
    assert (stored.version, stored.config.keyword) == (2, "PSX")


# 판정 기준·확보율 보정·Proc Rename ---------------------------------------------


def _pressed(app: AppTest, label: str) -> WidgetStates:
    next(button for button in app.button if button.label == label).click()
    return app._tree.get_widget_states()


def test_an_old_screen_double_press_after_another_threshold_save_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_trailing_window: None
) -> None:
    """판정 기준 — 남이 먼저 저장한 뒤 옛 화면의 「판정 기준 저장」 두 번. 첫 회차는 거부를 적기
    전에 끊기고 창도 없으니 둘째 누름은 본 값 대조로만 거절된다. 제출 회차가 본 version 을 그 회차가
    그린 최신으로 올리면 둘째 누름이 대조를 지나 남의 저장을 덮는다."""
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    app = _threshold_app(database)
    repository.replace_global_securement_threshold(
        1.17, 1.0, empty_securement_threshold_rows(), source="다른 세션", expected_version=0
    )
    clear_global_securement_threshold_cache()
    app.number_input[0].set_value(122.0)

    _press_twice(
        app,
        monkeypatch,
        _pressed(app, THRESHOLD_SAVE_LABEL),
        cls=DuckDBScenarioRepository,
        write="replace_global_securement_threshold",
    )

    errors = _texts(app, "error")
    assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
    assert not app.success
    profile = repository.load_global_securement_threshold()
    assert (profile.version, profile.source) == (1, "다른 세션")
    clear_global_securement_threshold_cache()


def _execution_rows(records: list[tuple[int, str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=list(EXECUTION_CAPACITY_COLUMNS))


def test_an_old_screen_double_press_after_another_execution_save_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_trailing_window: None
) -> None:
    """확보율 보정 — 위와 같은 꼴(「확보율 보정 저장」)."""
    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, "")]), source="A 가 본 것"
    )
    clear_global_execution_capacity_cache()
    app = AppTest.from_string(
        f"""
import pandas as pd

from capa_simulation.components.flash import render_flash
from capa_simulation.components.home_preference import _render_execution_editor
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.persistence.cache import load_global_execution_capacity

database_path = {str(database_path)!r}
render_flash("home_execution_flash")
_render_execution_editor(
    months=[202607, 202608],
    execution_profile=load_global_execution_capacity(database_path),
    process_options=["DEMO_A", "DEMO_B"],
    process_labels=process_labels_from_rules(pd.DataFrame()),
    unmatched=pd.DataFrame(),
    clamped=pd.DataFrame(),
    database_path=database_path,
)
""",
        default_timeout=60,
    ).run()
    assert not app.exception
    repository.replace_global_execution_capacity(
        _execution_rows([(202607, "DEMO_A", -10.0, ""), (202608, "DEMO_B", -5.0, "B")]),
        source="B 의 저장",
    )
    clear_global_execution_capacity_cache()

    _press_twice(
        app,
        monkeypatch,
        _pressed(app, "확보율 보정 저장"),
        cls=DuckDBScenarioRepository,
        write="replace_global_execution_capacity",
    )

    errors = _texts(app, "error")
    assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
    assert not app.success
    profile = repository.load_global_execution_capacity()
    assert (profile.version, profile.source) == (2, "B 의 저장")
    clear_global_execution_capacity_cache()


def test_an_old_screen_double_press_after_another_process_rename_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_trailing_window: None
) -> None:
    """Proc Rename 직접 편집 — 위와 같은 꼴(「공용 공정 표시명 저장」)."""
    database_path = tmp_path / "rename.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="A 가 본 것"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path), default_timeout=60).run()
    assert app.text[-1].value == "v1|SAW>절단"
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단"), ("MOLD", "성형")], columns=["공정", "표시명"]),
        source="B 의 저장",
    )
    clear_global_process_rename_cache()

    _press_twice(
        app,
        monkeypatch,
        _pressed(app, "공용 공정 표시명 저장"),
        cls=DuckDBScenarioRepository,
        write="replace_global_process_rename",
    )

    errors = _texts(app, "error")
    assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
    assert not app.success
    assert app.text[-1].value == "v2|SAW>절단;MOLD>성형"
    assert repository.load_global_process_rename().source == "B 의 저장"
    clear_global_process_rename_cache()


# 제 저장 짝은 뒷정리 앞 ---------------------------------------------------------
#
# 첫 회차가 저장소에 쓴 뒤 뒷정리(입장 화면 확인 비우기·세션 표시순서 갈아 끼우기 — 세션 칸
# 접근)에서 끊기면 제 저장 짝이 적히지 않아, 둘째 누름이 방금 한 제 저장을 「다른 사용자가 먼저
# 저장」 으로 알렸다(2026-10-26 E2E — 표시순서 6회 중 5회). 짝은 저장소에 쓴 바로 뒤에 적는다.


def test_a_double_press_of_the_display_order_save_cut_in_its_cleanup_says_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "display-order.duckdb"
    clear_global_display_order_cache()
    app = AppTest.from_string(_display_order_script(database_path), default_timeout=60).run()
    assert app.text[-1].value == "v1|A=1;B=2;C=3"

    _press_twice(
        app,
        monkeypatch,
        _pressed(app, "공용 표시순서 저장"),
        cls=DuckDBScenarioRepository,
        write="replace_global_display_order",
    )

    assert _texts(app, "error") == []
    assert [text for text in _texts(app, "success") if "공용 설정으로" in text] == [
        DISPLAY_ORDER_SAVED_MESSAGE
    ]
    assert app.text[-1].value == "v2|A=1;C=3;B=99"
    clear_global_display_order_cache()


def test_a_double_press_of_the_process_rename_save_cut_in_its_cleanup_says_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "rename.duckdb"
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path), default_timeout=60).run()
    assert app.text[-1].value == "v0|"

    _press_twice(
        app,
        monkeypatch,
        _pressed(app, "공용 공정 표시명 저장"),
        cls=DuckDBScenarioRepository,
        write="replace_global_process_rename",
    )

    assert _texts(app, "error") == []
    assert [text for text in _texts(app, "success") if "공용 설정으로" in text] == [
        PROCESS_RENAME_SAVED_MESSAGE
    ]
    assert app.text[-1].value == "v1|"
    clear_global_process_rename_cache()


def test_a_double_press_of_the_threshold_save_cut_in_its_cleanup_says_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """판정 기준도 같은 꼴이다(뒷정리 = 입장 화면 확인 비우기). 브라우저에서는 재현하지 못했지만
    끊기는 자리가 같다."""
    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    app = _threshold_app(database)
    app.number_input[0].set_value(122.0)

    _press_twice(
        app,
        monkeypatch,
        _pressed(app, THRESHOLD_SAVE_LABEL),
        cls=DuckDBScenarioRepository,
        write="replace_global_securement_threshold",
    )

    assert _texts(app, "error") == []
    assert [text for text in _texts(app, "success") if "공용 설정으로" in text] == [
        THRESHOLD_SAVED_MESSAGE
    ]
    profile = repository.load_global_securement_threshold()
    assert (profile.version, profile.default_secure) == (1, pytest.approx(1.22))
    clear_global_securement_threshold_cache()


# Cut-off -----------------------------------------------------------------------


def test_an_old_screen_double_press_after_another_cutoff_save_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cut-off — A 가 설정 팝업을 연 뒤 B 가 저장했다. A 가 칸을 고쳐 「Cut-off 저장」 을 0.5초
    간격으로 두 번 누르면 첫 누름은 거부되고 그 회차가 초안·출발점을 최신으로 다시 세운다(초안을
    세우는 자리). 둘째 누름은 고친 칸 없이 그 출발점으로 대조를 지나 같은 내용을 다시 썼고, 거부
    알림 대신 「공정별 Cut-off 1건을 저장했습니다.」 만 남아 고친 칸이 말없이 버려졌다(2026-10-26
    리뷰 — 사본 앱 두 세션). 창 안의 둘째 누름은 저장하지 않고 그 거부를 다시 알린다. AppTest 의
    회차 사이 시간이 들쭉날쭉해 창은 시험이 정한다(창이 지난 저장은 `tests/test_cutoff_tabs.py`)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    database_path = tmp_path / "cutoff.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_process_cutoff(pd.DataFrame({"공정": ["Process-A"], "Cutoff일수": [10.0]}))
    clear_equipment_repository()
    app = AppTest.from_string(
        f"""
from pathlib import Path

from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

render_cutoff_management(
    DuckDBEquipmentRepository(Path({str(database_path)!r})),
    equipment_processes=["Process-A"],
)
""",
        default_timeout=60,
    ).run()
    assert not app.exception
    repository.save_process_cutoff(pd.DataFrame({"공정": ["Process-A"], "Cutoff일수": [7.0]}))
    clear_process_cutoff_cache()
    draft = app.session_state[CUTOFF_DRAFT_KEY].copy()
    draft["Cutoff일수"] = 12.0
    app.session_state[CUTOFF_DRAFT_KEY] = draft
    pressed = _pressed(app, "Cut-off 저장")
    app.run()
    assert any("다른 사용자가 먼저" in text for text in _texts(app, "warning"))

    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    refusals = [text for text in _texts(app, "warning") if "다른 사용자가 먼저" in text]
    assert len(refusals) == 1, refusals
    assert not [text for text in _texts(app, "success") if "저장했습니다" in text]
    assert repository.load_process_cutoff()["Cutoff일수"].tolist() == [7.0]
    clear_equipment_repository()


# 리비전명 바꾸기 ---------------------------------------------------------------


def _renaming(tmp_path: Path) -> tuple[AppTest, BrowserTables, DuckDBScenarioRepository, str]:
    database_path = tmp_path / "scenario.duckdb"
    script = _scenario_page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    app = AppTest.from_string(script, default_timeout=120)
    tables = BrowserTables(app)
    _check_row(app, release.scenario_id)
    tables.run()
    return app, tables, repository, release.revision_id


def _rename_pressed(app: AppTest, tables: BrowserTables, name: str) -> WidgetStates:
    tables.edit(_shown_key(app, REVISION_EDITOR_KEY), 0, "리비전명", name)
    tables.run()
    app.button(key="scenario_card_save_names").click()
    return tables._states()


def test_a_double_press_of_the_revision_name_save_renames_once_and_says_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「이름 저장」 더블클릭 — 둘째 누름의 콜백이 첫 누름이 지우기 전의 초안을 들고 와 같은 바꿈을
    다시 보내 「다른 사용자가 먼저 이름을 바꿨습니다(지금: 새 이름)」 이 남았다."""
    app, tables, repository, revision_id = _renaming(tmp_path)

    _press_twice(
        app,
        monkeypatch,
        _rename_pressed(app, tables, "더블클릭 이름"),
        cls=DuckDBScenarioRepository,
        write="rename_revisions",
    )

    assert _texts(app, "error") == []
    assert [text for text in _texts(app, "success") if text.startswith("리비전명을 저장했습니다")]
    assert repository.load_revision(revision_id).revision.revision_name == "더블클릭 이름"


def test_an_old_screen_double_press_after_another_rename_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, tables, repository, revision_id = _renaming(tmp_path)
    shown = repository.load_revision(revision_id).revision.revision_name
    pressed = _rename_pressed(app, tables, "내 이름")
    repository.rename_revision(revision_id, "남이 바꾼 이름", expected_name=shown)

    _press_twice(app, monkeypatch, pressed, cls=DuckDBScenarioRepository, write="rename_revisions")

    assert any("다른 사용자가 먼저 이름을 바꿨습니다" in text for text in _texts(app, "error"))
    assert not [text for text in _texts(app, "success") if text.startswith("리비전명을 저장")]
    assert repository.load_revision(revision_id).revision.revision_name == "남이 바꾼 이름"


# 공식 지정 ---------------------------------------------------------------------


def _official_popup(tmp_path: Path) -> tuple[AppTest, DuckDBScenarioRepository, int]:
    database_path = tmp_path / "scenario.duckdb"
    script = _scenario_page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    app = AppTest.from_string(script, default_timeout=120)
    _open_official(app, release.scenario_id, release.revision_id)
    _official_button(app).click()
    return app, repository, release.release_no


def test_a_double_press_of_the_official_release_publishes_once_and_says_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「공식버전으로 지정」 더블클릭 — 둘째 누름의 회차가 「지금 공식」 을 그 회차에 다시 읽어
    넘기면 대조를 지나 공식이 하나 더 섰고, 팝업이 보인 번호를 넘기면 제 지정을 「다른 사람이 먼저
    지정」 으로 알렸다. 팝업이 지정 단추를 누르지 않은 회차에 보인 번호(본 값)로 대조하고 제 지정을
    알아본다."""
    app, repository, release_no = _official_popup(tmp_path)

    _press_twice(
        app,
        monkeypatch,
        app._tree.get_widget_states(),
        cls=DuckDBScenarioRepository,
        write="publish_official_revision",
    )

    assert _texts(app, "error") == []
    assert any(text.startswith(f"공식 v{release_no + 1} · ") for text in _texts(app, "success"))
    latest = repository.latest_official_release()
    assert latest is not None and latest.release_no == release_no + 1


def test_an_old_popup_double_press_after_another_release_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, repository, release_no = _official_popup(tmp_path)
    pressed = app._tree.get_widget_states()
    latest = repository.latest_official_release()
    assert latest is not None
    repository.publish_official_revision(
        latest.scenario_id, latest.revision_id, release_name="남이 먼저 지정"
    )

    _press_twice(
        app, monkeypatch, pressed, cls=DuckDBScenarioRepository, write="publish_official_revision"
    )

    assert any("먼저 지정해 지정하지 않았습니다" in text for text in _texts(app, "error"))
    newest = repository.latest_official_release()
    assert newest is not None
    assert (newest.release_no, newest.release_name) == (release_no + 1, "남이 먼저 지정")


# 설비 「리비전 저장」 ----------------------------------------------------------


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Iterator[Calls]:
    clear_equipment_repository()
    yield install_fake_grid(monkeypatch)
    clear_equipment_repository()


def _equipment_pressed(app: AppTest, grid: Calls, history: str) -> WidgetStates:
    load(app, [], kind="all")
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "설비이력", "text": history})
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click()
    return app._tree.get_widget_states()


def test_a_double_press_of_the_equipment_revision_save_saves_once_and_says_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grid: Calls
) -> None:
    """설비 마스터 「리비전 저장」 더블클릭 — 둘째 누름이 편집본을 비우기 전의 출발점으로 다시
    저장해 「다른 사용자가 먼저 공통 대장 r2를 저장해 저장하지 않았습니다」 가 남았다."""
    repository = _seeded(tmp_path)
    app = _page(repository, OPERATIONS)
    before = len(repository.list_revisions())

    _press_twice(
        app,
        monkeypatch,
        _equipment_pressed(app, grid, "더블클릭 이력"),
        cls=DuckDBEquipmentRepository,
        write="save_equipment",
    )

    assert _texts(app, "error") == []
    assert any("공통 대장 r2" in text for text in _texts(app, "success")), _texts(app, "success")
    assert len(repository.list_revisions()) == before + 1


def test_an_old_screen_double_press_after_another_equipment_save_keeps_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grid: Calls
) -> None:
    from test_equipment_scenario_repository import _request, _session, _set

    repository = _seeded(tmp_path)
    app = _page(repository, OPERATIONS)
    pressed = _equipment_pressed(app, grid, "내 이력")
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "설비이력", "남의 이력"))
    )
    before = len(repository.list_revisions())

    _press_twice(app, monkeypatch, pressed, cls=DuckDBEquipmentRepository, write="save_equipment")

    assert any("다른 사용자가 먼저" in text for text in _texts(app, "error")), _texts(app, "error")
    assert len(repository.list_revisions()) == before


# 설비 「공식으로 발행」 — 정리 리비전 ------------------------------------------------


def test_a_double_press_of_a_cleaning_publish_moves_like_the_first_press(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공식과 같아진 차이만 남은 최신 rN 의 「공식으로 발행」 은 정리 리비전 rN+1 을 발행하고 리비전
    상자·세션을 그리로 옮긴다. 더블클릭의 첫 회차가 발행 직후(옮기기 전 첫 세션 칸 접근에서) 끊기면
    둘째 회차는 옛 r2 를 고른 채 「최신이 아닌 리비전은 정리해 발행하지 않습니다」 로 단추가 꺼져
    둘째 누름이 버려지고, 성공 알림도 없이 세션·리비전 상자가 옛 r2 에 남았다(「최신 r3 있음」 —
    2026-10-26 리뷰 뒤 재현). 첫 회차가 쓰기 전에 받아 둔 표지에 뒷정리를 적고 다음 회차가 구획 맨
    위에서 잇는다 — 첫 누름처럼 정리 번호를 알리고 옮긴다. 창은 시험이 정한다(회차 사이 시간이
    들쭉날쭉하다)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository, setup, latest = _moved_setup(tmp_path)
    official = _equipment_session(repository)
    repository.save_equipment(
        _equipment_request(
            official, equipment=_equipment_set(official.equipment, "EQ-01", "X좌표", 50.0)
        )
    )
    clear_equipment_repository()
    app = _section(tmp_path, setup).run()
    app.selectbox(key=SCENARIO_KEY).set_value(setup)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.selectbox(key=REVISION_KEY).value == latest
    app.button(key=PUBLISH_BUTTON_KEY).click()

    _press_twice(
        app,
        monkeypatch,
        app._tree.get_widget_states(),
        cls=DuckDBEquipmentRepository,
        write="publish_equipment_release",
    )

    newest = repository.list_schedule_revisions(setup, limit=1)[0]
    assert (newest.revision_no, newest.origin) == (3, "layout_clear")
    release = repository.latest_equipment_release()
    assert release is not None
    assert (release.release_no, release.schedule_revision_id) == (2, newest.schedule_revision_id)
    assert _texts(app, "error") == []
    texts = _section_texts(app)
    assert any(
        "공식 v2로 발행했습니다" in text
        and "정리한 r3." in text
        and "이 세션을 r3으로 옮겼습니다." in text
        for text in texts
    ), texts
    assert app.session_state[SELECTION_KEY]["schedule_revision_id"] == newest.schedule_revision_id
    assert app.selectbox(key=REVISION_KEY).value == newest.schedule_revision_id
    clear_equipment_repository()


def _published_again_page(database: str, scenario_id: str, revision_id: str) -> None:
    """둘째 회차가 첫 쓰기 전 화면을 그려(두 회차가 겹친다) 발행 단추가 살아 제 저장 갈래에 닿은 꼴
    — 그 갈래(`_published_again`)만 한 번 부른다."""
    from pathlib import Path

    import streamlit as st

    import capa_simulation.settings as settings
    from capa_simulation.components import equipment_scenario_management as section
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session
    from capa_simulation.persistence.equipment_cache import load_equipment_schedule_revisions

    settings.EQUIPMENT_DUCKDB_PATH = Path(database)
    if st.session_state.get("called"):
        return
    st.session_state["called"] = True
    session = resolve_equipment_session(database)
    scenario = session.catalog.scenario(scenario_id)
    assert scenario is not None
    revision = next(
        item
        for item in load_equipment_schedule_revisions(database, scenario_id)
        if item.schedule_revision_id == revision_id
    )
    section._published_again(
        database, session, scenario, revision, 2, None, section._follow_marks()
    )


def test_the_own_publish_branch_follows_the_cleaning_revision_and_names_it(
    tmp_path: Path,
) -> None:
    """제 발행 갈래 — 정리 리비전(r3)으로 발행했으면 첫 누름처럼 리비전 상자·세션을 r3 으로 옮기고
    「정리한 r3」 을 알린다. 예전에는 「「셋업 실무」 r2.」 로 알리고 옮기지 않았다(2026-10-26
    리뷰)."""
    repository, setup, latest = _moved_setup(tmp_path)
    official = _equipment_session(repository)
    repository.save_equipment(
        _equipment_request(
            official, equipment=_equipment_set(official.equipment, "EQ-01", "X좌표", 50.0)
        )
    )
    published = repository.publish_equipment_release(
        latest, released_by=None, note=None, expected_latest_release_no=1
    )
    assert published.schedule_revision_id != latest
    clear_equipment_repository()
    app = AppTest.from_function(
        _published_again_page,
        args=(str(repository.database_path), setup, latest),
        default_timeout=60,
    )
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": latest}
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    flash = str(app.session_state[FLASH_KEY])
    assert "공식 v2로 발행했습니다" in flash and "정리한 r3." in flash, flash
    assert "이 세션을 r3으로 옮겼습니다." in flash, flash
    assert app.session_state[PENDING_REVISION_KEY] == published.schedule_revision_id
    assert (
        app.session_state[SELECTION_KEY]["schedule_revision_id"] == published.schedule_revision_id
    )
    clear_equipment_repository()


def test_a_double_press_of_the_layout_clear_moves_like_the_first_press(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「배치 차이 모두 지우기」 더블클릭 — 첫 회차가 새 리비전(r3)을 쓰고 옮기기 전에 끊기면 둘째
    회차에는 지울 차이가 없어 단추가 서지 않아 둘째 누름이 버려지고, 세션·리비전 상자가 옛 r2 에
    남았다. 다음 회차가 표지를 보고 잇는다(위 발행과 같은 꼴)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository, setup, _ = _moved_setup(tmp_path)
    app = _section(tmp_path, setup).run()
    app.selectbox(key=SCENARIO_KEY).set_value(setup)
    app.run()
    (confirm,) = [box for box in app.checkbox if str(box.key).startswith(CLEAR_LAYOUT_CONFIRM_KEY)]
    confirm.check().run()
    app.button(key=CLEAR_LAYOUT_BUTTON_KEY).click()

    _press_twice(
        app,
        monkeypatch,
        app._tree.get_widget_states(),
        cls=DuckDBEquipmentRepository,
        write="clear_layout_overlay",
    )

    revisions = repository.list_schedule_revisions(setup)
    assert [item.origin for item in revisions].count("layout_clear") == 1
    newest = revisions[0]
    assert (newest.revision_no, newest.origin) == (3, "layout_clear")
    assert _texts(app, "error") == []
    texts = _section_texts(app)
    assert any("배치 차이를 모두 지운 r3을 저장했습니다" in text for text in texts), texts
    assert app.session_state[SELECTION_KEY]["schedule_revision_id"] == newest.schedule_revision_id
    assert app.selectbox(key=REVISION_KEY).value == newest.schedule_revision_id
    clear_equipment_repository()


# 짝의 저장된 값은 쓰기 결과 -------------------------------------------------------


def _mine_then_theirs_equipment_save(
    repository: DuckDBEquipmentRepository, monkeypatch: pytest.MonkeyPatch
) -> list[object]:
    """설비 저장마다 제 쓰기 바로 뒤(수 ms) 남이 한 번 더 쓴다 — 남의 저장 결과를 모아 돌려준다."""
    from test_equipment_scenario_repository import _request, _session, _set

    original = DuckDBEquipmentRepository.save_equipment
    theirs_saved: list[object] = []

    def mine_then_theirs(self: DuckDBEquipmentRepository, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        if not theirs_saved:
            theirs = _session(repository)
            theirs_saved.append(
                original(
                    repository,
                    _request(
                        theirs, equipment=_set(theirs.equipment, "EQ-02", "설비이력", "남의 이력")
                    ),
                )
            )
        return result

    monkeypatch.setattr(DuckDBEquipmentRepository, "save_equipment", mine_then_theirs)
    return theirs_saved


def test_another_save_right_after_mine_is_not_taken_for_my_equipment_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grid: Calls, no_trailing_window: None
) -> None:
    """제 저장 짝의 「저장된 값」 을 쓰기 뒤 저장소에서 다시 읽으면, 그 사이(수 ms) 남이 저장했을 때
    남의 값이 짝에 들어가 옛 화면 둘째 누름의 충돌 `(본 값, 남의 값)` 이 짝과 같아졌다 — 「다른
    사용자가 먼저」 대신 성공을 알리고 세션을 남의 리비전으로 옮겼다(2026-10-26 리뷰). 짝은 쓰기
    결과로 만든다. 같은 출발점의 둘째 누름은 창 안이면 `write_guard.save_once` 가 저장소에 가지 않고
    첫 결과를 돌려주므로(아래 시험), 창을 0 으로 두어 둘째 누름이 저장소의 거부와 제 저장 판정에
    닿게 한다."""
    repository = _seeded(tmp_path)
    app = _page(repository, OPERATIONS)
    pressed = _equipment_pressed(app, grid, "내 이력")
    theirs_saved = _mine_then_theirs_equipment_save(repository, monkeypatch)
    before = len(repository.list_revisions())

    _press_twice(app, monkeypatch, pressed, cls=DuckDBEquipmentRepository, write="save_equipment")

    assert theirs_saved
    assert any("다른 사용자가 먼저" in text for text in _texts(app, "error")), _texts(app, "error")
    assert not any("공통 대장 r" in text for text in _texts(app, "success")), _texts(app, "success")
    assert len(repository.list_revisions()) == before + 2


def test_another_save_right_after_mine_leaves_the_window_press_on_my_own_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grid: Calls
) -> None:
    """같은 경합에서 창(`TRAILING_PRESS_SECONDS`) 안의 둘째 누름은 출발점이 같아
    `write_guard.save_once` 가 첫 누름의 결과(제 리비전)를 돌려준다 — 저장소에 다시 가지 않고, 남의
    리비전을 제 저장으로 알리지도 않는다."""
    repository = _seeded(tmp_path)
    app = _page(repository, OPERATIONS)
    pressed = _equipment_pressed(app, grid, "내 이력")
    theirs_saved = _mine_then_theirs_equipment_save(repository, monkeypatch)
    before = len(repository.list_revisions())

    _press_twice(app, monkeypatch, pressed, cls=DuckDBEquipmentRepository, write="save_equipment")

    assert theirs_saved
    assert _texts(app, "error") == []
    successes = _texts(app, "success")
    assert any(f"공통 대장 r{before + 1}" in text for text in successes), successes
    assert not any(f"공통 대장 r{before + 2}" in text for text in successes), successes
    assert len(repository.list_revisions()) == before + 2


def _floor_write_with_another_save(database: str) -> None:
    """층 사용 설정을 한 번 쓰고(본 version 0), 그 쓰기 바로 뒤 남이 한 번 더 쓴다 — 적힌 제 저장
    짝을 세션 칸에 꺼내 둔다."""
    import streamlit as st

    from capa_simulation.components import space_floor_list as floors
    from capa_simulation.components.write_guard import own_save_marks

    floors._write(database, {("C1", "1F"): "UNUSED"}, (0, ()))
    st.session_state["mark"] = own_save_marks().get(floors.FLOOR_STATE_SAVE_NAME)


def test_another_floor_save_right_after_mine_is_not_taken_for_mine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """층 사용 설정도 같다 — 짝의 저장된 version 은 쓰기가 돌려준 값이다(남의 저장 version 이
    아니다)."""
    database = tmp_path / "floors.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    clear_equipment_repository()
    original = DuckDBEquipmentRepository.save_floor_states

    def mine_then_theirs(self: DuckDBEquipmentRepository, *args: Any, **kwargs: Any) -> Any:
        monkeypatch.setattr(DuckDBEquipmentRepository, "save_floor_states", original)
        written = original(self, *args, **kwargs)
        original(self, {("C2", "1F"): "UNUSED"}, expected_version=None, source="남")
        return written

    monkeypatch.setattr(DuckDBEquipmentRepository, "save_floor_states", mine_then_theirs)
    app = AppTest.from_function(
        _floor_write_with_another_save, args=(str(database),), default_timeout=60
    ).run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["mark"] == (0, 1)
    assert repository.load_floor_states().version == 2
    clear_equipment_repository()


# ------------------------------------------------------------------ 일부러 정한 자리


def test_a_cutoff_draft_without_a_base_starts_from_the_stored_table(tmp_path: Path) -> None:
    """Cut-off 는 「지문 없는 옛 세션(초안만 있음)은 지금 저장본을 출발점」 으로 일부러 정했다 — 본
    값이 없다고 저장을 거부하지 않는다(다른 자리는 「다시 불러와」). 출발점은 초안을 세우는 자리가
    `write_guard.remember_seen` 으로 적는다."""
    database_path = tmp_path / "cutoff.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    repository.save_process_cutoff(pd.DataFrame({"공정": ["Process-A"], "Cutoff일수": [10.0]}))
    clear_equipment_repository()
    app = AppTest.from_string(
        f"""
from pathlib import Path

from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

render_cutoff_management(
    DuckDBEquipmentRepository(Path({str(database_path)!r})),
    equipment_processes=["Process-A"],
)
""",
        default_timeout=60,
    )
    app.session_state[CUTOFF_DRAFT_KEY] = pd.DataFrame(
        {"공정": ["Process-A"], "Cutoff일수": [12.0]}
    )
    app.run()
    assert not app.exception
    assert isinstance(app.session_state[CUTOFF_BASE_KEY], str)

    next(button for button in app.button if button.label == "Cut-off 저장").click().run()

    assert not app.exception
    assert any("저장했습니다" in text for text in _texts(app, "success"))
    assert repository.load_process_cutoff()["Cutoff일수"].tolist() == [12.0]
    clear_equipment_repository()


def test_streamlit_session_state_is_the_store_of_seen_values() -> None:
    """본 값 칸은 그 이름의 세션 칸이다 — 옛 세션 칸 이름(`SETTINGS_BASE_VERSION_KEY` 등)을 그대로
    쓰므로 배포 전에 열린 창도 같은 칸을 읽는다."""
    app = _session_app(
        """
write_guard.remember_seen("auto_official_update_settings_base_version", 4)
st.session_state["read"] = st.session_state["auto_official_update_settings_base_version"]
"""
    ).run()
    assert app.session_state["read"] == 4
