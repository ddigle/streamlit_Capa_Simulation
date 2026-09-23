# Purpose: 저장된 월이 기본 조회기간 밖에 있어도 선택·재선택과 페이지 왕복이 가능한지 검증한다.

from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.application_bootstrap import ensure_initial_scenario
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.services.scenario_month_bounds import scenario_month_bounds

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.mark.parametrize(
    ("months", "expected"),
    [
        ([], (202501, 203012)),
        ([202601, 202612], (202501, 203012)),
        ([203101, 203112], (202501, 203112)),
        ([202401, 203112], (202401, 203112)),
        ([101, 999912], (101, 999912)),
    ],
)
def test_month_bounds_keep_defaults_and_include_actual_months(
    months: list[int], expected: tuple[int, int]
) -> None:
    tables = {"RQ_PKG_PLAN": pd.DataFrame({"생산계획년월": months})}

    assert scenario_month_bounds(tables, 202501, 203012) == expected


def test_month_bounds_use_every_monthly_table_without_mutating_input() -> None:
    tables = {
        "RQ_PKG_PLAN": pd.DataFrame({"생산계획년월": [202601]}),
        "RQ_UPEH": pd.DataFrame({"생산계획년월": [203112]}),
        "RQ_YLD": pd.DataFrame({"생산계획년월": [202402]}),
        "RQ_CHIP_QTY": pd.DataFrame({"분류": ["203501"]}),
    }
    originals = {name: frame.copy(deep=True) for name, frame in tables.items()}

    assert scenario_month_bounds(tables, 202501, 203012) == (202402, 203112)
    for name, frame in tables.items():
        pd.testing.assert_frame_equal(frame, originals[name])


def test_missing_or_invalid_months_do_not_block_the_management_page() -> None:
    assert scenario_month_bounds({}, 202501, 203012) == (202501, 203012)
    tables = {"RQ_PKG_PLAN": pd.DataFrame({"생산계획년월": [None, 203013, "invalid"]})}

    assert scenario_month_bounds(tables, 202501, 203012) == (202501, 203012)


def test_shifted_months_remain_selectable_after_narrowing_and_page_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.components.scenario_status as scenario_status
    import capa_simulation.settings as settings

    database = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    bootstrap = ensure_initial_scenario(repository)
    assert bootstrap.release is not None
    original = repository.load_revision(bootstrap.release.revision_id)
    shifted_tables = {name: frame.copy(deep=True) for name, frame in original.tables.items()}
    for frame in shifted_tables.values():
        if "생산계획년월" in frame.columns:
            frame["생산계획년월"] = 203100 + frame["생산계획년월"] % 100
    shifted = repository.create_scenario(
        ScenarioCreate("조회범위 검증", "QA_MONTH_RANGE", "합성 검증", "TEST", "test-v1"),
        shifted_tables,
        replace(original.preset, start_month=203101, end_month=203112),
    )
    repository.publish_official_revision(
        shifted.scenario.scenario_id, shifted.revision.revision_id, release_name="조회범위 검증"
    )
    monkeypatch.setattr(settings, "DUCKDB_PATH", database)
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(
        scenario_status,
        "render_scenario_controls",
        partial(scenario_status.render_scenario_controls, database_path=database),
    )
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    # JS 전송만 대신하고 범위 밖 값을 버리는 실제 Python 선택기 검증은 그대로 실행한다.
    monkeypatch.setattr(
        month_range_picker,
        "_MONTH_RANGE_PICKER",
        lambda **kwargs: SimpleNamespace(value=kwargs["data"]["value"]),
    )
    app = AppTest.from_file(str(APP_PATH), default_timeout=120).run()
    assert not list(app.exception), [item.message for item in app.exception]
    assert app.session_state[MONTH_RANGE_KEY] == ("2031-01", "2031-12")

    app.session_state[MONTH_RANGE_KEY] = ("2027-01", "2027-12")
    app.run()
    assert not list(app.exception), [item.message for item in app.exception]
    assert app.session_state[MONTH_RANGE_KEY] == ("2027-01", "2027-12")

    app.switch_page("app_pages/scenario_management.py").run()
    assert not list(app.exception), [item.message for item in app.exception]
    app.session_state[MONTH_RANGE_KEY] = ("2031-01", "2031-12")
    app.run()
    assert not list(app.exception), [item.message for item in app.exception]
    assert app.session_state[MONTH_RANGE_KEY] == ("2031-01", "2031-12")

    app.switch_page("app_pages/home.py").run()
    assert not list(app.exception), [item.message for item in app.exception]
    assert app.session_state[MONTH_RANGE_KEY] == ("2031-01", "2031-12")
