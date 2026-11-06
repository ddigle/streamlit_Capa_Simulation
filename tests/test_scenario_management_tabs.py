# Purpose: 시나리오 관리 탭 안의 오류 알림과 Capa 시나리오로 가는 길이 그 탭을 여는지 검증한다.

"""시나리오 관리는 탭 넷이다 — 데려가는 동작은 그 탭까지 연다(설계 규칙 UI-NAV-01).

- 탭 본문이 낸 오류 알림(`SC-02`)의 「그 화면으로」 는 그 탭을 연다. 다른 탭을 보다 Alarm 줄을
  눌러도 오류가 난 탭으로 간다. 페이지 머리의 오류(`app_pages/scenario_management.py` — 탭이 서기
  전)만 탭이 없다.
- Capa 시나리오를 가리키는 길(팝업의 두 단추, 변경 칩의 「목록 편집 저장 안 함」)은 기억된 탭이
  아니라 Capa 시나리오 탭을 연다 — 설비 시나리오 탭에도 「시나리오 이름 바꾸기」 가 있어 다른
  시나리오의 이름을 고치는 곳으로 읽힌다.
"""

from __future__ import annotations

import ast
from pathlib import Path

from alert_marks import events
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

from capa_simulation.components.equipment_scenario_management import (
    CAPA_SCENARIO_TAB,
    EQUIPMENT_SCENARIO_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
)
from capa_simulation.components.tab_state import remembered_tab_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = PROJECT_ROOT / "src" / "capa_simulation" / "components"
# 모듈 → 그 본문이 서는 탭의 이름 상수(`scenario_management_tabs`).
TAB_OF_MODULE = {
    "equipment_scenario_management.py": "EQUIPMENT_SCENARIO_TAB_NAME",
    "scenario_management.py": "CAPA_SCENARIO_TAB_NAME",
    "scenario_month_merge.py": "CAPA_SCENARIO_TAB_NAME",
    "scenario_year_shift.py": "CAPA_SCENARIO_TAB_NAME",
    "bigdataquery_registration.py": "QUERY_TAB_NAME",
    "auto_official_update_tab.py": "AUTO_UPDATE_TAB_NAME",
}


def _tab_arguments(module: str) -> list[tuple[int, str | None]]:
    """(줄, `tab=` 에 준 이름) — 그 모듈의 `render_data_error` 호출마다."""
    tree = ast.parse((COMPONENTS / module).read_text(encoding="utf-8"))
    found: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "render_data_error":
            continue
        tab = next((word.value for word in node.keywords if word.arg == "tab"), None)
        found.append((node.lineno, tab.id if isinstance(tab, ast.Name) else None))
    return found


def test_every_data_error_on_a_scenario_tab_names_that_tab() -> None:
    """탭 본문의 오류 자리는 모두 제 탭 이름을 싣는다. 하나만 빠져도 그 줄의 「그 화면으로」 는 보던
    탭에 그대로 머문다."""
    wrong: list[str] = []
    for module, name in TAB_OF_MODULE.items():
        calls = _tab_arguments(module)
        assert calls, module
        wrong.extend(f"{module}:{line} {tab}" for line, tab in calls if tab != name)
    assert not wrong, "\n".join(wrong)


def test_an_unreadable_equipment_db_names_the_equipment_tab(tmp_path: Path) -> None:
    """설비 DB 를 읽지 못해 그 탭에 선 오류 — 알림 줄이 그 탭 이름을 들고 있어야 자동 갱신 탭을 보다
    눌러도 설비 시나리오 탭이 열린다."""
    equipment = tmp_path / "equipment.duckdb"
    equipment.write_bytes(b"not a database " * 200)
    app = AppTest.from_string(
        _page_script("app_pages/scenario_management.py", tmp_path / "scenario.duckdb", equipment),
        default_timeout=120,
    )
    app.session_state[SCENARIO_MANAGEMENT_TABS_KEY] = EQUIPMENT_SCENARIO_TAB
    app.run()
    assert not app.exception, [item.message for item in app.exception]

    (note,) = events(app, "SC-02")
    assert note["tab"] == "설비 시나리오"


def _capa_tab_that_cannot_read() -> None:
    from types import SimpleNamespace

    from capa_simulation.components.scenario_management import render_scenario_management

    def broken(**_kwargs: object) -> None:
        raise OSError("시험 — 목록을 읽지 못함")

    render_scenario_management(
        SimpleNamespace(list_scenarios=broken),  # type: ignore[arg-type]
        "unused.duckdb",
        alert_tab=None,
    )


def test_a_capa_tab_read_failure_names_the_capa_tab_even_while_it_is_closed() -> None:
    """Capa 시나리오 탭은 닫혀 있어도 그린다. 닫힌 채 난 오류라도 그 줄은 Capa 탭을 연다 — 상태
    알림의 `alert_tab`(닫힌 탭이면 None)과 다르다."""
    app = AppTest.from_function(_capa_tab_that_cannot_read, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    (note,) = events(app, "SC-02")
    assert note["tab"] == "Capa 시나리오"


def test_the_rename_route_opens_the_capa_tab_not_the_remembered_one() -> None:
    """팝업 「시나리오 관리에서 이름 바꾸기」 는 기억된 탭을 덮어 Capa 시나리오 탭으로 간다. 단독
    실행(내비게이션 없음)은 칸만 적고 옮기지 않는다."""
    app = AppTest.from_string(
        "from capa_simulation.components.scenario_status import _render_rename_route\n"
        "_render_rename_route(on_management_page=False)\n"
    )
    remembered = remembered_tab_key(SCENARIO_MANAGEMENT_TABS_KEY)
    app.session_state[remembered] = EQUIPMENT_SCENARIO_TAB
    app.run()
    assert not app.exception, [item.message for item in app.exception]

    route = next(item for item in app.button if item.label == "시나리오 관리에서 이름 바꾸기")
    assert app.session_state[remembered] == EQUIPMENT_SCENARIO_TAB  # 그리기만으로는 적지 않는다
    route.click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[remembered] == CAPA_SCENARIO_TAB


def _changes_with_a_list_edit() -> None:
    import streamlit as st

    from capa_simulation.components.change_summary import session_changes
    from capa_simulation.components.scenario_list_state import store_draft
    from capa_simulation.navigation import SCENARIO_MANAGEMENT
    from capa_simulation.services.scenario_list_edits import ListDraft, NameEdit

    store_draft(ListDraft(scenarios={"scenario-1": NameEdit("DEMO 옛 이름", "DEMO 새 이름")}))
    st.session_state["changes"] = session_changes(
        None, hrefs={SCENARIO_MANAGEMENT.path: "scenario_management"}
    )


def test_the_list_edit_chip_line_opens_the_capa_tab() -> None:
    """변경 칩 「목록 편집 저장 안 함」 은 Capa 시나리오 탭의 표를 가리켜 그 탭을 함께 싣는다."""
    app = AppTest.from_function(_changes_with_a_list_edit, default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]

    (line,) = [item for item in app.session_state["changes"] if item["top"] == "목록 미저장"]
    assert line["href"] == "scenario_management"
    assert line["tab"] == "Capa 시나리오"
