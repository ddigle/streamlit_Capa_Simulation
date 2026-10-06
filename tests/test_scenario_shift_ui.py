# Purpose: 연도 Shift 화면의 전후 미리보기·저장 차단과 원본 및 활성 편집본 보존을 검증한다.

from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.persistence.models import ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    ACTIVE_PERSISTED_REVISION_ID_KEY,
    ACTIVE_PERSISTED_SCENARIO_ID_KEY,
)
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY
from capa_simulation.services.scenario_transform import MONTHLY_TABLES, NON_MONTHLY_TABLES
from capa_simulation.services.virtual_product import VirtualProductRecord, records_to_frame

Source = tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot]


@pytest.fixture
def source(tmp_path: Path) -> Source:
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
    repository.replace_global_display_order(
        tables["RQ_DISPLAY_ORDER"].assign(분류값="현재 공용값"), source="UI 검증"
    )
    return repository, database, snapshot


def _app(
    database: Path, source: ScenarioSnapshot, *, active_revision: ScenarioSnapshot | None = None
) -> AppTest:
    script = f"""
from capa_simulation.components.scenario_year_shift import render_scenario_year_shift
from capa_simulation.persistence.cache import get_scenario_repository

database_path = {str(database)!r}
render_scenario_year_shift(get_scenario_repository(database_path), database_path)
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    if active_revision is not None:
        app.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY] = active_revision.scenario.scenario_id
        app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] = active_revision.revision.revision_id
    app.selectbox(key="shift_source_scenario").set_value(source.scenario.scenario_id).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _save_button(app: AppTest) -> Button:
    return next(button for button in app.button if button.label == "새 시나리오로 저장")


def _ranges(app: AppTest) -> dict[str, str]:
    return {item.label: item.value for item in app.metric}


def test_shift_preserves_selected_revision_history_and_can_shift_it_again(source: Source) -> None:
    repository, database, original = source
    record = VirtualProductRecord("Product-A", "8H", "복제 원본", "12H")
    original = repository.save_revision(
        original.scenario.scenario_id,
        original.tables,
        original.preset,
        revision_name="복제 이력 포함",
        parent_revision_id=original.revision.revision_id,
        virtual_products=[asdict(record)],
    )
    expected = repository.list_virtual_products(original.revision.revision_id)
    app = _app(database, original)
    app.number_input(key="scenario_shift_years").set_value(1).run()
    preview = next(item.value for item in app.dataframe if "원본 제품정보" in item.value)
    pd.testing.assert_frame_equal(preview, records_to_frame((record,)))
    app.text_input(key="scenario_shift_name").set_value("이력 보존 Shift")
    _save_button(app).click().run()
    assert not app.exception, [item.message for item in app.exception]
    created = next(
        item for item in repository.list_scenarios() if item.scenario_name == "이력 보존 Shift"
    )
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(created.active_revision_id), expected
    )
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(original.revision.revision_id), expected
    )
    assert len(repository.list_revisions(original.scenario.scenario_id)) == 2

    app.selectbox(key="shift_source_scenario").set_value(created.scenario_id).run()
    app.number_input(key="scenario_shift_years").set_value(-2).run()
    app.text_input(key="scenario_shift_name").set_value("이력 재보존 Shift")
    _save_button(app).click().run()
    assert not app.exception, [item.message for item in app.exception]
    shifted_again = next(
        item for item in repository.list_scenarios() if item.scenario_name == "이력 재보존 Shift"
    )
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(shifted_again.active_revision_id), expected
    )


def test_zero_shift_has_preview_but_no_save_and_invalid_shift_recovers(source: Source) -> None:
    repository, database, snapshot = source
    app = _app(database, snapshot)

    assert app.number_input(key="scenario_shift_years").value == 0
    assert _ranges(app) == {
        "이동 전 월 범위": "2027-01 ~ 2027-12",
        "이동 후 월 범위": "2027-01 ~ 2027-12",
    }
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    assert any("월 없는 RQ_CHIP_EQ" in item.value for item in app.info)
    assert len(repository.list_scenarios()) == 1

    app.number_input(key="scenario_shift_years").set_value(9998).run()
    assert not app.exception
    assert any("YYYYMM" in item.value for item in app.error)
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    assert len(repository.list_scenarios()) == 1

    app.number_input(key="scenario_shift_years").set_value(-2).run()
    assert not app.exception
    assert not app.error
    assert _ranges(app)["이동 후 월 범위"] == "2025-01 ~ 2025-12"
    assert not _save_button(app).disabled


def test_save_keeps_source_and_draft_and_changed_years_refresh_the_preview(source: Source) -> None:
    repository, database, original = source
    app = _app(database, original)
    sentinel = {"revision": 9, "content_token": "편집 토큰", "tables": {"편집값": 123}}
    app.session_state[ACTIVE_SCENARIO_KEY] = sentinel
    app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] = "별개 활성 리비전"
    app.number_input(key="scenario_shift_years").set_value(1).run()
    app.text_input(key="scenario_shift_name").set_value("이동 결과 2028")
    app.text_area(key="scenario_shift_note").set_value("직접 선택한 연도")

    _save_button(app).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[ACTIVE_SCENARIO_KEY] == sentinel
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == "별개 활성 리비전"
    assert len(repository.list_scenarios()) == 2
    created = next(
        item for item in repository.list_scenarios() if item.scenario_name == "이동 결과 2028"
    )
    shifted = repository.load_revision(created.active_revision_id, apply_global_display_order=False)
    assert len(shifted.tables) == 16
    assert (shifted.preset.start_month, shifted.preset.end_month) == (202801, 202812)
    note = shifted.revision.note
    assert note is not None
    assert original.revision.revision_id in note
    assert "+1년" in note
    assert "직접 선택한 연도" in note
    for name in MONTHLY_TABLES:
        expected = original.tables[name].assign(
            생산계획년월=pd.Series(
                [202801, 202812], dtype=original.tables[name]["생산계획년월"].dtype
            )
        )
        pd.testing.assert_frame_equal(shifted.tables[name], expected)
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(shifted.tables[name], original.tables[name])
    reloaded = repository.load_revision(
        original.revision.revision_id, apply_global_display_order=False
    )
    assert len(repository.list_revisions(original.scenario.scenario_id)) == 1
    for name, frame in original.tables.items():
        pd.testing.assert_frame_equal(reloaded.tables[name], frame)
    assert repository.load_global_display_order().rules["분류값"].tolist() == ["현재 공용값"]
    assert _save_button(app).disabled

    app.run()
    assert not app.exception
    assert _save_button(app).disabled
    assert len(repository.list_scenarios()) == 2

    app.number_input(key="scenario_shift_years").set_value(2).run()
    assert not app.exception
    assert _ranges(app)["이동 후 월 범위"] == "2029-01 ~ 2029-12"
    assert set(app.dataframe[0].value["이동 후 월 범위"]) == {"2029-01 ~ 2029-12"}
    assert not _save_button(app).disabled
    assert len(repository.list_scenarios()) == 2

    app.text_input(key="scenario_shift_name").set_value("이동 결과 2029")
    _save_button(app).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert len(repository.list_scenarios()) == 3
    changed = next(
        item for item in repository.list_scenarios() if item.scenario_name == "이동 결과 2029"
    )
    changed_result = repository.load_revision(
        changed.active_revision_id, apply_global_display_order=False
    )
    assert len(changed_result.tables) == 16
    assert (changed_result.preset.start_month, changed_result.preset.end_month) == (202901, 202912)
    for name in MONTHLY_TABLES:
        expected = original.tables[name].assign(
            생산계획년월=pd.Series(
                [202901, 202912], dtype=original.tables[name]["생산계획년월"].dtype
            )
        )
        pd.testing.assert_frame_equal(changed_result.tables[name], expected)
        assert set(changed_result.tables[name]["생산계획년월"]) == {202901, 202912}
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(changed_result.tables[name], original.tables[name])
    for previous in (original, shifted):
        reloaded = repository.load_revision(
            previous.revision.revision_id, apply_global_display_order=False
        )
        for name, frame in previous.tables.items():
            pd.testing.assert_frame_equal(reloaded.tables[name], frame)
    assert app.session_state[ACTIVE_SCENARIO_KEY] == sentinel
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == "별개 활성 리비전"
    assert _save_button(app).disabled


def test_source_defaults_to_active_revision_and_preserves_explicit_selection(
    source: Source,
) -> None:
    repository, database, original = source
    latest = repository.save_revision(
        original.scenario.scenario_id,
        original.tables,
        original.preset,
        revision_name="최신 r2",
        parent_revision_id=original.revision.revision_id,
    )
    revision_key = f"shift_source_revision_{original.scenario.scenario_id}"

    inactive_app = _app(database, original)
    assert inactive_app.selectbox(key=revision_key).value == latest.revision.revision_id

    # 최신 r2가 있어도 현재 사용 중인 r1을 초기값으로 삼고 명시적인 변경은 보존한다.
    app = _app(database, original, active_revision=original)
    assert app.selectbox(key=revision_key).value == original.revision.revision_id
    app.selectbox(key=revision_key).set_value(latest.revision.revision_id).run()
    app.number_input(key="scenario_shift_years").set_value(1).run()
    assert not app.exception
    assert app.selectbox(key=revision_key).value == latest.revision.revision_id

    app.selectbox(key="shift_source_scenario").set_value(None).run()
    app.selectbox(key="shift_source_scenario").set_value(original.scenario.scenario_id).run()
    assert not app.exception
    assert app.selectbox(key=revision_key).value == latest.revision.revision_id
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == original.revision.revision_id
    assert len(repository.list_scenarios()) == 1
    assert len(repository.list_revisions(original.scenario.scenario_id)) == 2
