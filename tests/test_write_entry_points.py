# Purpose: 화면의 저장소 쓰기 호출마다 두 번 누름을 무엇으로 거르는지 장부로 묶고 겹친 저장을 잰다.

"""화면 쓰기 장부와 겹친 저장(2026-10-26 쓰기 단추 세대 정리).

**장부** — 화면 모듈(`app.py`·`app_pages/`·`components/`)이 부르는 저장소 쓰기를 (파일, 바깥 함수,
쓰기 이름)마다 그 쓰기가 빠른 두 번 누름을 무엇으로 거르는지 하나로 적는다. 쓰기 이름은 저장소
클래스에서 쓰기 트랜잭션(`_write_transaction`)을 여는 메서드와, 화면 밖 모듈에서 그것을 부르는 공개
함수다. 장부에 없는 쓰기 호출이 생기면 실패한다 — 새 쓰기마다 한 줄을 요구하는 일부러 둔 마찰이다.
세대 대조 없이 덧붙이기만 하는 쓰기가 남지 않게 한다(AGENTS 9장 「쓰기 콜백은 빠른 두 번 누름을
거른다」).

**겹친 저장** — 스피너 도는 저장 중 둘째 누름이 닿으면 Streamlit 은 돌던 회차에 멈춤을 걸고 둘째
회차를 세운다. 첫 회차는 쓰기를 마친 뒤 다음 세션 칸 접근에서 끊겨 알림·세대 올리기를 하지
못하고, 둘째 회차는 같은 세대·같은 입력으로 다시 쓴다 — 같은 리비전이 두 건 서거나, 같은 이름이라
거절되어 방금 한 저장 자리에 오류가 섰다. 여기서는 쓰기가 끝나는 순간 그 회차에 멈춤을 걸고
(`_SecondPress`) 누른 화면의 위젯 값을 그대로 한 번 더 보낸다(`AppTest._run(widget_state=...)`).
옛 코드는 둘째 회차가 다시 썼고, 지금은 한 번만 쓰고 성공 알림이 하나 선다.
"""

from __future__ import annotations

import ast
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest
import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button
from test_all_pages_render import _page_script
from test_duckdb_repository import _metadata, _reference_tables
from test_equipment_scenario_repository import _seeded
from test_required_shortening_tab import _run as _run_shortening_page
from test_scenario_sidebar import TEST_SCRIPT as SIDEBAR_SCRIPT
from test_scenario_sidebar import FakeRepository, _open_save, sidebar_replacements
from test_shortening_progress_tab import _name_input, _save_button, _saved_database, _toasts
from test_standard_target_capa_page import TEST_SCRIPT as STANDARD_TARGET_SCRIPT

import capa_simulation.components.scenario_status as scenario_status
from capa_simulation.components.equipment_scenario_management import (
    CLONE_BUTTON_KEY,
    CLONE_NAME_KEY,
    GENERATION_KEY,
)
from capa_simulation.components.scenario_management import (
    CLONE_FORM_GENERATION_KEY,
    CLONE_MODE,
    MODE_KEY,
)
from capa_simulation.components.shortening_progress_panel import (
    _BASELINE_FORM_GENERATION_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.models import ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.scenario_transform import MONTHLY_TABLES

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "capa_simulation"

# ------------------------------------------------------------------ 장부

WRITE_ONCE = "write_once — 그린 회차의 세대마다 한 번"
VERSION_CHECK = "버전 대조 — 편집 시작에 본 version·이름·지문·차례와 견줘 다르면 거부(T3)"
SAME_REPLACE = "같은 내용 교체 — 공용 행·도면을 통째로 바꿔 두 번 써도 같은 상태"
SELF_FILTER = "자체 거름 — 설비 마스터 편집본 지문"
STATE_CHANGE = "대상 하나의 상태 바꾸기 — 지우기·보관·되살리기·비우기(지운 id 거름 포함)"
NAME_UNIQUE = "이름 유일 — 저장소가 같은 이름을 거절한다"
BOOTSTRAP = "부트스트랩 — 빈 저장소의 첫 시드·세션 첫 활성화"
RUN_CLAIM = "실행 잠금 — 저장소가 한 실행만 받는다"

_PAGES = "app_pages"
_PARTS = "src/capa_simulation/components"

LEDGER: dict[tuple[str, str, str], str] = {
    ("app.py", "<module>", "bootstrap_latest_official_scenario"): BOOTSTRAP,
    (f"{_PAGES}/standard_target_capa.py", "_paste_dialog", "save_standard_target_availability"): (
        WRITE_ONCE
    ),
    (f"{_PAGES}/standard_target_capa.py", "_clear_dialog", "clear_standard_target_availability"): (
        STATE_CHANGE
    ),
    (f"{_PAGES}/voc.py", "_submit_post", "create_voc_post"): WRITE_ONCE,
    (f"{_PAGES}/voc.py", "_submit_reply", "create_voc_reply"): WRITE_ONCE,
    (f"{_PAGES}/voc.py", "_set_resolved", "set_voc_post_resolved"): WRITE_ONCE,
    (f"{_PAGES}/voc.py", "_delete_post", "remove_voc_post"): STATE_CHANGE,
    (
        f"{_PARTS}/auto_official_update_tab.py",
        "_render_settings_form",
        "replace_auto_official_update_settings",
    ): VERSION_CHECK,
    (f"{_PARTS}/auto_official_update_tab.py", "_render_run_now", "run_auto_official_update"): (
        RUN_CLAIM
    ),
    (f"{_PARTS}/bigdataquery_registration.py", "_save_scenario", "save_bigdataquery_scenario"): (
        NAME_UNIQUE
    ),
    (f"{_PARTS}/cutoff_management.py", "render_cutoff_management", "save_process_cutoff"): (
        VERSION_CHECK
    ),
    (
        f"{_PARTS}/display_order_management.py",
        "_save_global_display_order",
        "replace_global_display_order",
    ): SAME_REPLACE,
    (f"{_PARTS}/equipment_data_workspace.py", "save_pending_fab_layout", "save_fab_layout"): (
        VERSION_CHECK
    ),
    (f"{_PARTS}/equipment_data_workspace.py", "_save_equipment_frames", "save_equipment"): (
        SELF_FILTER
    ),
    (
        f"{_PARTS}/equipment_scenario_management.py",
        "_render_restore",
        "restore_schedule_revision",
    ): VERSION_CHECK,
    (
        f"{_PARTS}/equipment_scenario_management.py",
        "_render_branch",
        "clone_equipment_scenario",
    ): WRITE_ONCE,
    (
        f"{_PARTS}/equipment_scenario_management.py",
        "_render_revision_name",
        "rename_schedule_revision",
    ): VERSION_CHECK,
    (
        f"{_PARTS}/equipment_scenario_management.py",
        "_render_rename",
        "rename_equipment_scenario",
    ): VERSION_CHECK,
    (
        f"{_PARTS}/equipment_scenario_management.py",
        "_render_clear_layout",
        "clear_layout_overlay",
    ): VERSION_CHECK,
    (
        f"{_PARTS}/equipment_scenario_management.py",
        "_render_publish",
        "publish_equipment_release",
    ): VERSION_CHECK,
    (
        f"{_PARTS}/equipment_scenario_management.py",
        "_render_legacy_trace",
        "acknowledge_legacy_trace",
    ): VERSION_CHECK,
    (f"{_PARTS}/floor_layout_upload.py", "_floor_layout_dialog", "delete_fab_layout_profile"): (
        STATE_CHANGE
    ),
    (f"{_PARTS}/floor_layout_upload.py", "_floor_layout_dialog", "delete_floor_layout_profile"): (
        STATE_CHANGE
    ),
    (f"{_PARTS}/floor_layout_upload.py", "_save", "save_fab_layout_image"): SAME_REPLACE,
    (f"{_PARTS}/floor_layout_upload.py", "_save", "save_floor_layout_image"): SAME_REPLACE,
    (f"{_PARTS}/floor_layout_upload.py", "_save", "save_fab_layout_canvas"): SAME_REPLACE,
    (f"{_PARTS}/floor_layout_upload.py", "_save", "save_floor_layout_canvas"): SAME_REPLACE,
    (
        f"{_PARTS}/home_main_cases.py",
        "_drop_vanished_scenarios",
        "clear_global_main_case_scenario",
    ): STATE_CHANGE,
    (f"{_PARTS}/home_main_cases.py", "_plan_case", "replace_global_main_case"): VERSION_CHECK,
    (f"{_PARTS}/home_main_cases.py", "_replace_case", "replace_global_main_case"): VERSION_CHECK,
    (
        f"{_PARTS}/home_preference.py",
        "_persist_comparison_choice",
        "replace_global_comparison_scenario",
    ): SAME_REPLACE,
    (
        f"{_PARTS}/home_preference.py",
        "_replace_comparison_profile",
        "replace_global_comparison_scenario",
    ): SAME_REPLACE,
    (f"{_PARTS}/home_preference.py", "_save_thresholds", "replace_global_securement_threshold"): (
        VERSION_CHECK
    ),
    (f"{_PARTS}/home_preference.py", "_render_advance_editor", "replace_global_advance_load"): (
        SAME_REPLACE
    ),
    (
        f"{_PARTS}/home_preference.py",
        "render_advance_shipment_editor",
        "replace_global_advance_shipment",
    ): SAME_REPLACE,
    (
        f"{_PARTS}/home_preference.py",
        "_render_summary_note_editor",
        "replace_global_summary_note",
    ): SAME_REPLACE,
    (f"{_PARTS}/home_preference.py", "_render_top5_band_editor", "replace_global_top5_band"): (
        SAME_REPLACE
    ),
    (
        f"{_PARTS}/home_preference.py",
        "_render_key_process_editor",
        "replace_global_key_process_presets",
    ): SAME_REPLACE,
    (
        f"{_PARTS}/home_preference.py",
        "_render_key_process_preset_actions",
        "replace_global_key_process_presets",
    ): SAME_REPLACE,
    (
        f"{_PARTS}/home_preference.py",
        "_save_execution_capacity",
        "replace_global_execution_capacity",
    ): VERSION_CHECK,
    (f"{_PARTS}/past_data_management.py", "_render_save", "replace_global_past_data"): (
        SAME_REPLACE
    ),
    (
        f"{_PARTS}/process_rename_management.py",
        "_save_process_rename",
        "replace_global_process_rename",
    ): VERSION_CHECK,
    (
        f"{_PARTS}/required_shortening_panel.py",
        "_save_month_range",
        "save_shortening_filter_months",
    ): SAME_REPLACE,
    (
        f"{_PARTS}/required_shortening_panel.py",
        "_save_processes",
        "save_shortening_filter_processes",
    ): SAME_REPLACE,
    (f"{_PARTS}/scenario_management.py", "_save_list_edits", "apply_scenario_list_edits"): (
        VERSION_CHECK
    ),
    (f"{_PARTS}/scenario_management.py", "save_revision_name", "rename_revision"): VERSION_CHECK,
    (f"{_PARTS}/scenario_management.py", "save_revision_names", "rename_revisions"): (
        VERSION_CHECK
    ),
    (f"{_PARTS}/scenario_management.py", "_render_official", "publish_official_revision"): (
        VERSION_CHECK
    ),
    (f"{_PARTS}/scenario_management.py", "_render_archive", "archive_scenario"): STATE_CHANGE,
    (f"{_PARTS}/scenario_management.py", "_restore_scenario", "restore_scenario"): STATE_CHANGE,
    (f"{_PARTS}/scenario_management.py", "_render_delete", "delete_scenario"): STATE_CHANGE,
    (f"{_PARTS}/scenario_management.py", "_render_clone", "create_scenario"): WRITE_ONCE,
    (f"{_PARTS}/scenario_status.py", "_render_revision_save", "save_revision"): WRITE_ONCE,
    (f"{_PARTS}/scenario_transform.py", "render_derived_save", "create_scenario"): WRITE_ONCE,
    (f"{_PARTS}/shortening_progress_panel.py", "_save_baseline", "save_shortening_baseline"): (
        WRITE_ONCE
    ),
    (
        f"{_PARTS}/shortening_progress_panel.py",
        "_delete_baseline",
        "delete_shortening_baseline",
    ): STATE_CHANGE,
    (f"{_PARTS}/space_floor_list.py", "_write", "save_floor_states"): VERSION_CHECK,
}


def _parse(path: Path) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(path.read_text(encoding="utf-8"))


def _called(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Attribute):
            names.add(call.func.attr)
        elif isinstance(call.func, ast.Name):
            names.add(call.func.id)
    return names


def _repository_writes() -> set[str]:
    """저장소 클래스의 쓰기 메서드 — 쓰기 트랜잭션을 열거나, 그런 메서드를 부르는 메서드."""
    methods: dict[str, list[tuple[bool, set[str]]]] = {}
    for path in sorted((SOURCE / "persistence").glob("*.py")):
        for cls in _parse(path).body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for function in cls.body:
                if isinstance(function, ast.FunctionDef):
                    opens = "_write_transaction" in _called(function)
                    methods.setdefault(function.name, []).append((opens, _called(function)))
    writes = {name for name, found in methods.items() if any(opens for opens, _ in found)}
    grown = True
    while grown:
        grown = False
        for name, found in methods.items():
            if name not in writes and any(calls & writes for _, calls in found):
                writes.add(name)
                grown = True
    return {name for name in writes if not name.startswith("_")}


def _ui_paths() -> list[Path]:
    return [
        ROOT / "app.py",
        *sorted((ROOT / "app_pages").glob("*.py")),
        *sorted((SOURCE / "components").rglob("*.py")),
    ]


def _write_names() -> set[str]:
    """저장소 쓰기 메서드와, 화면 밖 모듈에서 그것을 부르는 모듈 함수(공개 이름만 화면이 부른다)."""
    writes = _repository_writes()
    ui = set(_ui_paths())
    functions: list[tuple[str, set[str]]] = []
    for path in sorted(SOURCE.rglob("*.py")):
        if "persistence" in path.parts or path in ui:
            continue
        for node in _parse(path).body:
            if isinstance(node, ast.FunctionDef):
                functions.append((node.name, _called(node)))
    wrappers: set[str] = set()
    grown = True
    while grown:
        grown = False
        for name, calls in functions:
            if name not in wrappers and calls & (writes | wrappers):
                wrappers.add(name)
                grown = True
    return writes | {name for name in wrappers if not name.startswith("_")}


def _write_calls() -> dict[tuple[str, str, str], ast.AST]:
    """화면 모듈의 쓰기 호출 — (파일, 바깥 함수, 쓰기 이름) → 그 바깥 함수(모듈 단이면 모듈)."""
    names = _write_names()
    found: dict[tuple[str, str, str], ast.AST] = {}

    def visit(node: ast.AST, path: str, outer: ast.AST, label: str) -> None:
        for child in ast.iter_child_nodes(node):
            scope, scope_label = outer, label
            if label == "<module>" and isinstance(child, ast.FunctionDef):
                scope, scope_label = child, child.name
            if isinstance(child, ast.Call):
                func = child.func
                name = (
                    func.attr
                    if isinstance(func, ast.Attribute)
                    else func.id
                    if isinstance(func, ast.Name)
                    else None
                )
                if name in names:
                    found[(path, scope_label, str(name))] = scope
            visit(child, path, scope, scope_label)

    for path in _ui_paths():
        tree = _parse(path)
        visit(tree, str(path.relative_to(ROOT)), tree, "<module>")
    return found


def test_the_write_name_scan_finds_the_repository_writes() -> None:
    """이름 찾기가 실제로 저장소 쓰기를 잡는다 — 잡지 못하는 장부는 아무것도 지키지 않는다."""
    names = _write_names()
    for expected in (
        "save_revision",
        "create_scenario",
        "clone_equipment_scenario",
        "save_standard_target_availability",
        "save_shortening_baseline",
        "create_voc_post",
        "replace_global_process_rename",
        "save_bigdataquery_scenario",
    ):
        assert expected in names, expected
    assert "list_scenarios" not in names
    assert "load_standard_target_availability" not in names


def test_every_ui_write_call_is_in_the_ledger() -> None:
    """화면의 쓰기 호출마다 두 번 누름을 무엇으로 거르는지 장부에 한 줄이 있다 — 빠진 줄·남은
    줄이 없다."""
    found = set(_write_calls())
    missing = sorted(found - set(LEDGER))
    stale = sorted(set(LEDGER) - found)
    assert not missing, (
        "장부에 없는 쓰기 호출 — 두 번 누름을 무엇으로 거르는지 정해 LEDGER 에 한 줄 더한다"
        f"(덧붙이기 쓰기라면 widget_generation.write_once_value 로 감싼다): {missing}"
    )
    assert not stale, f"이제 없는 쓰기 호출이 장부에 남았다: {stale}"


def test_write_once_entries_go_through_the_generation_guard() -> None:
    """`write_once` 줄은 그 바깥 함수가 세대 거름을 지나고, 세대 거름을 지나는 쓰기는 그 줄이다."""
    calls = _write_calls()
    for key, scope in calls.items():
        guarded = bool(_called(scope) & {"write_once", "write_once_value"})
        if LEDGER.get(key) == WRITE_ONCE:
            assert guarded, f"{key} 는 write_once 줄인데 세대 거름을 지나지 않는다"
        elif guarded and key[1] != "<module>":
            assert LEDGER.get(key) == WRITE_ONCE, f"{key} 는 세대 거름을 지난다 — 장부를 고친다"


# ------------------------------------------------------------------ 겹친 저장


class _SecondPress:
    """쓰기가 끝나는 순간 그 회차에 멈춤을 건다 — 같은 단추의 둘째 누름이 닿은 것과 같다.

    `tries` 는 쓰기를 부른 수, `writes` 는 끝까지 쓴 수다. 첫 쓰기의 회차만 멈춘다.
    """

    def __init__(self) -> None:
        self.tries = 0
        self.writes = 0

    def wrap(self, original: Callable[..., Any]) -> Callable[..., Any]:
        def racing(*args: Any, **kwargs: Any) -> Any:
            self.tries += 1
            result = original(*args, **kwargs)
            self.writes += 1
            if self.writes == 1:
                context = get_script_run_ctx()
                assert context is not None and context.script_requests is not None
                context.script_requests.request_stop()
            return result

        return racing


def _press_twice(app: AppTest, button: Button) -> None:
    """`button` 을 누른 화면의 위젯 값으로 두 회차를 돌린다 — 첫 회차는 쓰기 뒤 멈추고 둘째가 같은
    누름이다."""
    button.click()
    pressed = app._tree.get_widget_states()
    app.run()
    app._run(widget_state=pressed)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _successes(app: AppTest, text: str) -> int:
    return sum(text in str(item.value) for item in app.success)


@pytest.fixture
def sidebar_app() -> Iterator[AppTest]:
    with patch.multiple(scenario_status, **sidebar_replacements()):
        yield AppTest.from_string(SIDEBAR_SCRIPT)


def test_a_second_press_of_the_sidebar_revision_save_saves_once(
    sidebar_app: AppTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사이드바 「신규 리비전 저장」(스피너 몇 초) — 옛 코드는 같은 리비전을 두 건 남겼다."""
    press = _SecondPress()
    monkeypatch.setattr(FakeRepository, "save_revision", press.wrap(FakeRepository.save_revision))
    app = _open_save(sidebar_app.run())
    app.text_input(key=scenario_status.SAVE_REVISION_NAME_KEY).set_value("겹친 저장안")
    app = _ok(app.run())
    button = next(item for item in app.button if item.label == "신규 리비전 저장")

    _press_twice(app, button)

    _ok(app)
    assert press.tries == 1
    assert app.session_state["test_saved_revision_name"] == "겹친 저장안"
    assert app.session_state["test_activation_path"] == "저장"
    assert app.session_state[scenario_status.SAVE_FORM_GENERATION_KEY] == 1
    assert _successes(app, "저장했습니다") == 1


def test_a_second_press_of_create_scenario_creates_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """시나리오 관리 「신규 시나리오 저장」 — 옛 코드는 둘째 회차가 같은 이름으로 거절돼 방금 만든
    시나리오 자리에 「같은 이름의 시나리오가 이미 있습니다」 가 섰다."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script("app_pages/scenario_management.py", database_path, tmp_path / "eq.duckdb")
    app = _ok(AppTest.from_string(script, default_timeout=120).run())
    app = _ok(app.segmented_control(key=MODE_KEY).set_value(CLONE_MODE).run())
    for widget in app.text_input:
        if not str(widget.key or "").startswith("scenario_create_"):
            continue
        value = {"시나리오명": "겹친 복제", "원천 시뮬레이션 코드": "RACE-1"}.get(widget.label)
        widget.set_value(value if value is not None else "겹친 원천")
    press = _SecondPress()
    monkeypatch.setattr(
        DuckDBScenarioRepository,
        "create_scenario",
        press.wrap(DuckDBScenarioRepository.create_scenario),
    )

    _press_twice(app, next(item for item in app.button if item.label == "신규 시나리오 저장"))

    _ok(app)
    assert press.tries == 1
    names = [
        item.scenario_name
        for item in DuckDBScenarioRepository(database_path).list_scenarios(include_archived=True)
    ]
    assert names.count("겹친 복제") == 1
    assert not app.error, [item.value for item in app.error]
    assert _successes(app, "겹친 복제") == 1
    assert _successes(app, "저장했습니다") == 1
    assert app.session_state[CLONE_FORM_GENERATION_KEY] == 1


def _shift_source(tmp_path: Path) -> tuple[Path, ScenarioSnapshot]:
    """연도 Shift 원본 — `tests/test_scenario_shift_ui.py` 의 `source` 와 같은 꼴."""
    database = tmp_path / "shift.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    tables = _reference_tables()
    for name in MONTHLY_TABLES:
        tables[name] = pd.concat(
            [tables[name].assign(생산계획년월=month) for month in (202701, 202712)],
            ignore_index=True,
        )
    snapshot = repository.create_scenario(
        _metadata("이동할 2027"), tables, ScenarioPreset(202701, 202712, ("Process-A",))
    )
    repository.initialize_global_display_order(tables["RQ_DISPLAY_ORDER"])
    return database, snapshot


def test_a_second_press_of_a_derived_save_creates_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """파생 「새 시나리오로 저장」(연도 Shift) — 옛 코드는 둘째 회차가 같은 이름으로 거절됐다."""
    database, source = _shift_source(tmp_path)
    script = f"""
from capa_simulation.components.scenario_year_shift import render_scenario_year_shift
from capa_simulation.persistence.cache import get_scenario_repository

render_scenario_year_shift(get_scenario_repository({str(database)!r}), {str(database)!r})
"""
    app = _ok(AppTest.from_string(script, default_timeout=60).run())
    app = _ok(
        app.selectbox(key="shift_source_scenario").set_value(source.scenario.scenario_id).run()
    )
    app = _ok(app.number_input(key="scenario_shift_years").set_value(1).run())
    app.text_input(key="scenario_shift_name").set_value("겹친 Shift")
    press = _SecondPress()
    monkeypatch.setattr(
        DuckDBScenarioRepository,
        "create_scenario",
        press.wrap(DuckDBScenarioRepository.create_scenario),
    )

    _press_twice(app, next(item for item in app.button if item.label == "새 시나리오로 저장"))

    _ok(app)
    assert press.tries == 1
    names = [item.scenario_name for item in DuckDBScenarioRepository(database).list_scenarios()]
    assert names.count("겹친 Shift") == 1
    assert not app.error, [item.value for item in app.error]
    assert _successes(app, "‘겹친 Shift’") == 1


@pytest.fixture
def _fresh_equipment_repository() -> Iterator[None]:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.mark.usefixtures("_fresh_equipment_repository")
def test_a_second_press_of_an_equipment_scenario_branch_creates_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비 시나리오 「새 시나리오 만들기」 — 옛 코드는 둘째 회차가 같은 이름으로 거절됐다."""
    repository = _seeded(tmp_path)
    path = str(repository.database_path)
    script = f"""
from capa_simulation.components.equipment_scenario_management import (
    render_equipment_scenario_management,
)
from capa_simulation.equipment_scenario_activation import resolve_equipment_session

render_equipment_scenario_management({path!r}, resolve_equipment_session({path!r}))
"""
    app = _ok(AppTest.from_string(script, default_timeout=60).run())
    app.text_input(key=CLONE_NAME_KEY).input("겹친 가지")
    press = _SecondPress()
    monkeypatch.setattr(
        DuckDBEquipmentRepository,
        "clone_equipment_scenario",
        press.wrap(DuckDBEquipmentRepository.clone_equipment_scenario),
    )

    _press_twice(app, app.button(key=CLONE_BUTTON_KEY))

    _ok(app)
    assert press.tries == 1
    names = [item.scenario_name for item in repository.list_equipment_scenarios()]
    assert names.count("겹친 가지") == 1
    assert not app.error, [item.value for item in app.error]
    assert _successes(app, "「겹친 가지」 r1 을 만들었습니다") == 1
    assert app.session_state[GENERATION_KEY] == 1


# 표준 목표 화면의 가짜 설비 저장소(시험 스크립트 안)가 쓰기를 마친 순간 그 회차에 멈춤을 건다.
_AVAILABILITY_SAVE = '        st.session_state["captured_saved_availability"] = data.copy()\n'
_AVAILABILITY_RACE = (
    _AVAILABILITY_SAVE
    + "        from streamlit.runtime.scriptrunner_utils.script_run_context import "
    "get_script_run_ctx\n"
    + '        st.session_state["race_writes"] = st.session_state.get("race_writes", 0) + 1\n'
    + '        if st.session_state["race_writes"] == 1:\n'
    + "            get_script_run_ctx().script_requests.request_stop()\n"
)


def test_a_second_press_of_the_availability_paste_saves_once() -> None:
    """표준 목표 「붙여넣기 적용」 — 옛 코드는 둘째 회차가 같은 표를 한 번 더 썼다."""
    assert STANDARD_TARGET_SCRIPT.count(_AVAILABILITY_SAVE) == 1
    st.cache_data.clear()
    script = STANDARD_TARGET_SCRIPT.replace(_AVAILABILITY_SAVE, _AVAILABILITY_RACE)
    app = _ok(AppTest.from_string(script, default_timeout=60).run())
    app = _ok(app.button(key="open_standard_target_availability_paste").click().run())
    app.text_area(key="standard_target_availability_clipboard_text").set_value(
        "공정\tWeeknum\t가용대수\nProcess-B\t26-W32\t3\n"
    )

    _press_twice(app, next(item for item in app.button if item.label == "붙여넣기 적용"))

    _ok(app)
    assert app.session_state["race_writes"] == 1
    assert _successes(app, "주차별 가용설비 최신본을 저장했습니다") == 1
    st.cache_data.clear()


@pytest.mark.usefixtures("_fresh_equipment_repository")
def test_a_second_press_of_the_baseline_save_saves_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「기준선 저장」(콜백) — 옛 코드는 둘째 회차가 같은 이름으로 거절돼 성공 대신 거절이 섰다."""
    database_path, _ = _saved_database(tmp_path)
    app = _run_shortening_page(database_path)
    app = _ok(_name_input(app).set_value("겹친 기준선").run())
    press = _SecondPress()
    monkeypatch.setattr(
        DuckDBEquipmentRepository,
        "save_shortening_baseline",
        press.wrap(DuckDBEquipmentRepository.save_shortening_baseline),
    )

    _press_twice(app, _save_button(app))

    _ok(app)
    assert press.tries == 1
    names = [
        item.name for item in DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    ]
    assert names == ["겹친 기준선"]
    assert "기준선을 저장했습니다 — 「겹친 기준선」" in _toasts(app)
    assert "저장하지 않았습니다" not in _toasts(app)
    assert app.session_state[_BASELINE_FORM_GENERATION_KEY] == 1
