# Purpose: 본 값 대조·제 저장 판정이 write_guard 한 길인지 소스 그물과 두 누름 경합으로 본다.

"""비교 후 쓰기(CAS)의 세 규칙(`components/write_guard.py`, AGENTS 9장 「쓰기 콜백은 빠른 두 번
누름을 거른다」).

- **소스 그물(AST).** 화면 모듈에서 충돌 예외 10종을 잡는 자리는 모두 제 저장을 판정한다
  (`is_own_save`) — 빠뜨리면 더블클릭의 둘째 누름이 방금 한 제 저장을 「다른 사용자가 먼저」 로
  알린다. 저장소에 넘기는 `expected_*` 대조 값을 `… if … else 지금 값` 꼴로 대체하지 않는다 —
  대체하면 남의 저장 뒤 한 회차만 돌아도 대조가 지나 그 저장을 덮는다. 이름에 BASE·SEEN 이 든 세션
  칸(본 값)은 write_guard 만 적는다.
- **두 누름 경합.** 브라우저 더블클릭은 둘째 누름이 닿는 순간 돌던 회차에 멈춤을 건다 — 첫 회차는 DB
  에 쓴 뒤 다음 세션 칸 접근에서 끊긴다(`StopException`). 시험은 첫 회차의 쓰기 직후 그 회차에
  멈춤을 걸고(`ScriptRequests.request_stop` — 브라우저와 같은 자리에서 끊긴다), 같은 누른 화면(위젯
  값)으로 둘째 회차를 다른 스레드의 `app._run` 으로 세운다(`tests/test_voc_page.py` 의 `_race` 꼴).
  네 자리(리비전명 바꾸기·공식 지정·설비 「리비전 저장」·자동 갱신 설정)에서 더블클릭은 한 번만
  쓰고 성공 알림만 남기고, 남이 먼저 저장한 뒤의 옛 화면 더블클릭은 둘 다 거절한다.
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
from test_all_pages_render import _page_script as _scenario_page_script
from test_auto_official_update_tab import _field, _tab, _with_w40
from test_equipment_master_tab_scenarios import OPERATIONS, _page
from test_equipment_scenario_repository import _seeded
from test_scenario_management_page import (
    PAGE_PATH,
    _check_row,
    _official_button,
    _open_official,
    _shown_key,
)
from widget_browser import BrowserTables

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.cutoff_management import (
    CUTOFF_BASE_KEY,
    CUTOFF_DRAFT_KEY,
)
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
)
from capa_simulation.components.scenario_management import REVISION_EDITOR_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.auto_official_update import AutoUpdateConfig

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
# 대조 값의 대체로 보는 「지금 값」 — 프로필 version 과 그 회차에 다시 읽은 지금 이름.
CURRENT_ATTRIBUTES = frozenset({"version"})
CURRENT_NAMES = frozenset({"current"})
# 이름에 BASE·SEEN 이 들었지만 대조 값이 아닌 세션 칸(모듈 파일 이름, 칸 이름).
NOT_SEEN_TOKENS = {
    # 위젯이 아닌 탐색 표지 — HOME 이 본 공정 목록, 상세·제약 화면이 받은 주소 인자.
    ("home.py", "PROCESS_SEEN_KEY"),
    ("process_detail_state.py", "PROCESS_DETAIL_QUERY_SEEN_KEY"),
    ("constraint_simulation_state.py", "CONSTRAINT_QUERY_SEEN_KEY"),
    # 입장 화면 Summary 를 이 세션이 한 번 본 표지(읽기를 미룰지) — 대조 값이 아니다.
    ("intro_summary.py", "_SEEN_KEY"),
    # Qual 마감 계산기의 「기존 대수」 입력 칸 — 위젯 값이다.
    ("qual_deadline_calculator.py", "BASE_KEY"),
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


def unjudged_conflicts(source: str) -> list[int]:
    """충돌 예외를 잡고도 제 저장을 판정하지 않는 except 줄. 같은 모듈 함수로 넘겨 판정해도 된다."""
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

    return [
        handler.lineno
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and _names(handler.type) & CONFLICTS
        and not judges(ast.Module(body=handler.body, type_ignores=[]), frozenset())
    ]


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
    """`st.session_state[…]` 에 이름(토막)에 BASE·SEEN 이 든 칸을 대입하는 줄과 그 이름."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if not (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Attribute)
                and target.value.attr == "session_state"
            ):
                continue
            for word in _tokens(target.slice):
                parts = {part for part in re.split(r"[^a-z0-9]+", word.lower()) if part}
                if parts & {"base", "seen"} and (module, word) not in NOT_SEEN_TOKENS:
                    found.append((node.lineno, word))
                    break
    return found


def _relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def test_every_conflict_handler_in_the_screens_judges_an_own_save() -> None:
    """충돌 예외 10종을 잡는 화면 자리는 모두 `is_own_save` 를 부른다(2026-10-26 E2E — 리비전명·
    공식 지정·설비 이름·Cut-off 저장의 더블클릭이 「다른 사용자가 먼저」 로 끝났다)."""
    missing = [
        f"{_relative(path)}:{line}"
        for path in UI_FILES
        for line in unjudged_conflicts(path.read_text(encoding="utf-8"))
    ]
    assert missing == []


def test_no_expected_argument_falls_back_to_the_value_read_this_run() -> None:
    """`expected_*=` 대조 값이 「본 값이 없으면 지금 값」 으로 대체되지 않는다 — 본 값은
    `write_guard.seen` 이 대체값 없이 돌려준다."""
    found = [
        f"{_relative(path)}:{line}"
        for path in UI_FILES
        for line in current_fallbacks(path.read_text(encoding="utf-8"))
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
    assert unjudged_conflicts(old) == [10]
    assert seen_slot_writes(old, "auto_official_update_tab.py") == [
        (5, "SETTINGS_BASE_VERSION_KEY")
    ]
    assert seen_slot_writes("st.session_state[f'{key}__seen'] = name", "x.py") == [(1, "__seen")]


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
