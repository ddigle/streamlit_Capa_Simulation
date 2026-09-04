# Purpose: PKG PLAN 붙여넣기는 탭에만, 변경사항 적용만 전역 계획값에 반영되는지 고정한다.

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE = Path("app_pages/load_conversion.py").resolve()

# 사용자 요청: 붙여넣기 일괄 적용 후 변경사항 적용을 또 눌러야 하는지 헷갈린다.
# 붙여넣기는 PKG PLAN 탭에만 반영하고, 전역 반영은 변경사항 적용 버튼으로만 한다.


def _script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

horizontal_scrollbar.render_horizontal_scrollbar = lambda *a, **k: None
month_range_picker.render_month_range_picker = (
    lambda *, start, end, min_month, max_month, key: (start, end)
)

exec(
    compile(Path({str(PAGE)!r}).read_text(encoding="utf-8"), {str(PAGE)!r}, "exec"),
    {{"__name__": "__main__"}},
)
"""


@pytest.fixture(scope="module")
def seeded_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("plan_apply") / "scenario.duckdb"


def _plan_total(app: AppTest) -> float:
    plan = app.session_state["active_scenario"]["tables"]["RQ_PKG_PLAN"]
    return float(plan["생산수량"].astype(float).sum())


def _clipboard_text(app: AppTest, *, scale: float) -> str:
    """현재 편집 격자를 CSV 로 만들고 월 값을 배율만큼 바꾼 붙여넣기 문자열을 만든다."""
    from capa_simulation.scenario_state import scenario_month_table
    from capa_simulation.services.load_calculator import (
        PLAN_EDITOR_DIMENSIONS,
        plan_to_edit_table,
    )

    scenario = app.session_state["active_scenario"]
    # 프리셋이 복원한 조회기간("2026-01", "2026-12")을 YYYYMM 으로 바꾼다.
    start_label, end_label = app.session_state["production_month_range_v2"]
    start = int(str(start_label).replace("-", ""))
    end = int(str(end_label).replace("-", ""))
    wide = plan_to_edit_table(scenario_month_table(scenario, "RQ_PKG_PLAN", start, end))
    months = [c for c in wide.columns if c not in PLAN_EDITOR_DIMENSIONS]
    wide[months] = wide[months].astype(float) * scale
    # 클립보드 계약은 Excel 복사와 같은 탭 구분이다.
    return wide.to_csv(index=False, sep="	")


def test_paste_stages_into_the_tab_without_touching_the_global_plan(
    seeded_database: Path,
) -> None:
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    before_total = _plan_total(app)
    before_token = app.session_state["active_scenario"]["content_token"]

    app.text_area(key="rq_pkg_plan_csv_clipboard").set_value(_clipboard_text(app, scale=0.5))
    for button in app.button:
        if "붙여넣기 일괄 적용" in str(button.label):
            button.click().run()
            break
    assert not list(app.exception)

    # 탭에만 반영된다: 전역 계획값과 토큰은 그대로다.
    assert _plan_total(app) == pytest.approx(before_total)
    assert app.session_state["active_scenario"]["content_token"] == before_token
    assert "pkg_plan_staged_paste" in app.session_state


def test_apply_button_publishes_the_staged_plan_globally(seeded_database: Path) -> None:
    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    before_total = _plan_total(app)
    before_token = app.session_state["active_scenario"]["content_token"]

    app.text_area(key="rq_pkg_plan_csv_clipboard").set_value(_clipboard_text(app, scale=0.5))
    for button in app.button:
        if "붙여넣기 일괄 적용" in str(button.label):
            button.click().run()
            break
    for button in app.button:
        if "PKG PLAN 변경사항 적용" in str(button.label):
            button.click().run()
            break
    assert not list(app.exception)

    assert _plan_total(app) == pytest.approx(before_total * 0.5)
    assert app.session_state["active_scenario"]["content_token"] != before_token
    assert "pkg_plan_staged_paste" not in app.session_state
