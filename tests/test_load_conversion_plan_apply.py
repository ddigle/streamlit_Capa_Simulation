# Purpose: PKG PLAN 붙여넣기는 탭에만, 변경사항 적용만 전역 계획값에 반영되는지 고정한다.

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker

PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "load_conversion.py"

# 사용자 요청: 붙여넣기 일괄 적용 후 변경사항 적용을 또 눌러야 하는지 헷갈린다.
# 붙여넣기는 PKG PLAN 탭에만 반영하고, 전역 반영은 변경사항 적용 버튼으로만 한다.


def _script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

exec(
    compile(Path({str(PAGE)!r}).read_text(encoding="utf-8"), {str(PAGE)!r}, "exec"),
    {{"__name__": "__main__"}},
)
"""


@pytest.fixture(autouse=True)
def _isolated_custom_renderers() -> Iterator[None]:
    """사용자 조작의 callback과 모든 rerun 동안 대역을 유지하고 테스트 뒤 원본을 복원한다."""
    original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
    original_month_picker = month_range_picker.render_month_range_picker
    try:
        with (
            patch.object(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None),
            patch.object(
                month_range_picker,
                "render_month_range_picker",
                lambda *, start, end, min_month, max_month, key: (start, end),
            ),
        ):
            yield
    finally:
        assert horizontal_scrollbar.render_horizontal_scrollbar is original_scrollbar
        assert month_range_picker.render_month_range_picker is original_month_picker


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


def test_virtual_product_registration_adds_the_key_to_every_clone_table(
    seeded_database: Path,
) -> None:
    """제품 등록 탭이 8개 기준정보에 새 제품 키를 넣고 계획은 0으로 시작해야 한다."""
    from capa_simulation.services.virtual_product import (
        available_source_products,
        clone_table_names,
    )

    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    assert not list(app.exception)
    tables = app.session_state["active_scenario"]["tables"]
    before_token = app.session_state["active_scenario"]["content_token"]
    source = available_source_products(tables).iloc[0]
    clone_tables = clone_table_names(tables)

    app.text_input(key="virtual_product_name").set_value("DEMO_VIRTUAL_X")
    app.text_input(key="virtual_product_stack").set_value(str(source["Stack"]))
    for button in app.button:
        if "가상 제품 등록" in str(button.label):
            button.click().run()
            break
    assert not list(app.exception)

    updated = app.session_state["active_scenario"]
    assert updated["content_token"] != before_token
    for name in clone_tables:
        assert "DEMO_VIRTUAL_X" in set(updated["tables"][name]["제품정보"]), name

    plan = updated["tables"]["RQ_PKG_PLAN"]
    cloned_plan = plan.loc[plan["제품정보"].eq("DEMO_VIRTUAL_X")]
    assert not cloned_plan.empty
    assert cloned_plan["생산수량"].astype(float).sum() == 0.0


def test_registered_virtual_product_appears_in_the_plan_editor(
    seeded_database: Path,
) -> None:
    """계획 수량 0 행을 보존하므로 등록 직후 편집 격자에 바로 나타나야 한다."""
    from capa_simulation.scenario_state import scenario_month_table
    from capa_simulation.services.load_calculator import plan_to_edit_table
    from capa_simulation.services.virtual_product import available_source_products

    app = AppTest.from_string(_script(seeded_database), default_timeout=300).run()
    source = available_source_products(app.session_state["active_scenario"]["tables"]).iloc[0]

    app.text_input(key="virtual_product_name").set_value("DEMO_VIRTUAL_Y")
    app.text_input(key="virtual_product_stack").set_value(str(source["Stack"]))
    for button in app.button:
        if "가상 제품 등록" in str(button.label):
            button.click().run()
            break
    assert not list(app.exception)

    scenario = app.session_state["active_scenario"]
    start_label, end_label = app.session_state["production_month_range_v2"]
    grid = plan_to_edit_table(
        scenario_month_table(
            scenario,
            "RQ_PKG_PLAN",
            int(str(start_label).replace("-", "")),
            int(str(end_label).replace("-", "")),
        )
    )

    assert "DEMO_VIRTUAL_Y" in set(grid["제품정보"])
