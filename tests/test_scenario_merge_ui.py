# Purpose: 월 머지의 출처 미리보기·겹침 선택과 원본을 보존하는 신규 저장 흐름을 검증한다.

from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button
from test_duckdb_repository import _metadata, _reference_tables

from capa_simulation.persistence.models import ScenarioPreset, ScenarioSnapshot
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_REVISION_ID_KEY
from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY
from capa_simulation.services.scenario_transform import MONTHLY_TABLES, NON_MONTHLY_TABLES
from capa_simulation.services.virtual_product import VirtualProductRecord, records_to_frame


def _monthly_tables(months: list[int]) -> dict[str, pd.DataFrame]:
    tables = _reference_tables()
    for name in MONTHLY_TABLES:
        tables[name] = pd.concat(
            [tables[name].assign(생산계획년월=month) for month in months], ignore_index=True
        )
    return tables


Sources = tuple[DuckDBScenarioRepository, Path, ScenarioSnapshot, ScenarioSnapshot]


@pytest.fixture
def sources(tmp_path: Path) -> Sources:
    database = tmp_path / "merge.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    base_tables = _monthly_tables([202701])
    donor_tables = _monthly_tables([202801, 202802])
    donor_tables["RQ_CHIP_EQ"] = pd.concat(
        [donor_tables["RQ_CHIP_EQ"], donor_tables["RQ_CHIP_EQ"].assign(Stack="12H")],
        ignore_index=True,
    )
    donor_tables["RQ_DISPLAY_ORDER"] = donor_tables["RQ_DISPLAY_ORDER"].assign(분류값="Donor")
    base = repository.create_scenario(
        _metadata("베이스 2027"), base_tables, ScenarioPreset(202701, 202701, ("Process-A",))
    )
    donor = repository.create_scenario(
        _metadata("덧붙일 2028"), donor_tables, ScenarioPreset(202801, 202802, ("Process-A",))
    )
    repository.initialize_global_display_order(base_tables["RQ_DISPLAY_ORDER"])
    repository.replace_global_display_order(
        base_tables["RQ_DISPLAY_ORDER"].assign(분류값="공용 표시순서"), source="UI 검증"
    )
    return repository, database, base, donor


def _app(database: Path, base: ScenarioSnapshot, donor: ScenarioSnapshot) -> AppTest:
    script = f"""
from capa_simulation.components.scenario_month_merge import render_scenario_month_merge
from capa_simulation.persistence.cache import get_scenario_repository

database_path = {str(database)!r}
render_scenario_month_merge(get_scenario_repository(database_path), database_path)
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    app.selectbox(key="merge_base_scenario").set_value(base.scenario.scenario_id).run()
    app.selectbox(key="merge_donor_scenario").set_value(donor.scenario.scenario_id).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _save_button(app: AppTest) -> Button:
    return next(button for button in app.button if button.label == "새 시나리오로 저장")


def _preview(app: AppTest) -> pd.DataFrame:
    return next(item.value for item in app.dataframe if "결과 월 수" in item.value.columns)


def _with_history(
    repository: DuckDBScenarioRepository,
    source: ScenarioSnapshot,
    records: Iterable[VirtualProductRecord],
) -> ScenarioSnapshot:
    return repository.save_revision(
        source.scenario.scenario_id,
        source.tables,
        source.preset,
        revision_name="복제 이력 포함",
        parent_revision_id=source.revision.revision_id,
        virtual_products=[asdict(record) for record in records],
    )


def test_merge_preserves_both_histories_and_deduplicates_same_origin(sources: Sources) -> None:
    repository, database, base, donor = sources
    shared = VirtualProductRecord("Product-A", "8H", "원본 A", "8H")
    extra = VirtualProductRecord("Product-A", "12H", "원본 B", "8H")
    base = _with_history(repository, base, (shared,))
    donor = _with_history(repository, donor, (shared, extra))
    base_history = repository.list_virtual_products(base.revision.revision_id)
    donor_history = repository.list_virtual_products(donor.revision.revision_id)
    app = _app(database, base, donor)
    app.selectbox(key=f"merge_start_{donor.revision.revision_id}").set_value(202802).run()
    preview = next(item.value for item in app.dataframe if "원본 제품정보" in item.value.columns)
    pd.testing.assert_frame_equal(preview, records_to_frame((shared, extra)))
    app.text_input(key="scenario_merge_name").set_value("이력 포함 머지")
    _save_button(app).click().run()
    assert not app.exception, [item.message for item in app.exception]
    created = next(s for s in repository.list_scenarios() if s.scenario_name == "이력 포함 머지")
    expected = (
        records_to_frame((shared, extra)).sort_values(["제품정보", "Stack"]).reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(created.active_revision_id), expected
    )
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(base.revision.revision_id), base_history
    )
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(donor.revision.revision_id), donor_history
    )
    assert len(repository.list_revisions(base.scenario.scenario_id)) == 2
    assert len(repository.list_revisions(donor.scenario.scenario_id)) == 2


@pytest.mark.parametrize("origin", [("다른 제품", "8H"), ("원본 A", "12H")])
def test_history_conflict_blocks_save_and_revision_change_recovers(
    sources: Sources, origin: tuple[str, str]
) -> None:
    repository, database, base, donor = sources
    base_record = VirtualProductRecord("Product-A", "8H", "원본 A", "8H")
    base = _with_history(repository, base, (base_record,))
    conflicting = _with_history(
        repository, donor, (VirtualProductRecord("Product-A", "8H", *origin),)
    )
    app = _app(database, base, conflicting)
    assert any("가상제품 복제 이력이 충돌" in error.value for error in app.error)
    assert any("Product-A · 8H" in error.value for error in app.error)
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    assert len(repository.list_scenarios()) == 2
    app.selectbox(key=f"merge_start_{conflicting.revision.revision_id}").set_value(202802).run()
    assert any("가상제품 복제 이력이 충돌" in error.value for error in app.error)
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    app.selectbox(key=f"merge_donor_revision_{donor.scenario.scenario_id}").set_value(
        donor.revision.revision_id
    ).run()
    assert not app.exception
    assert not app.error
    app.text_input(key="scenario_merge_name").set_value("충돌 없는 리비전 머지")
    _save_button(app).click().run()
    assert not app.exception
    created = next(
        s for s in repository.list_scenarios() if s.scenario_name == "충돌 없는 리비전 머지"
    )
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(created.active_revision_id),
        records_to_frame((base_record,)),
    )


def test_preview_reports_monthless_differences_and_does_not_save(sources: Sources) -> None:
    repository, database, base, donor = sources
    app = _app(database, base, donor)

    comparison = app.dataframe[0].value.set_index("표")
    assert set(comparison.index) == set(NON_MONTHLY_TABLES)
    assert comparison.loc["RQ_CHIP_EQ", "베이스 행 수"] == 1
    assert comparison.loc["RQ_CHIP_EQ", "덧붙일 쪽 행 수"] == 2
    assert comparison.loc["RQ_DISPLAY_ORDER", "비교"] == "다름 · 베이스 유지"
    assert any("베이스 값만" in warning.value for warning in app.warning)
    assert set(_preview(app)["결과 월 수"]) == {3}
    assert set(_preview(app)["행 수 증감"]) == {2}
    assert len(repository.list_scenarios()) == 2
    assert not _save_button(app).disabled


def test_overlapping_months_block_save_until_the_source_changes(sources: Sources) -> None:
    repository, database, base, donor = sources
    app = _app(database, base, donor)

    app.selectbox(key="merge_donor_scenario").set_value(base.scenario.scenario_id).run()

    assert not app.exception
    assert any("겹쳐 저장할 수 없습니다" in error.value for error in app.error)
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    assert len(repository.list_scenarios()) == 2

    app.selectbox(key="merge_donor_scenario").set_value(donor.scenario.scenario_id).run()
    assert not app.exception
    assert not app.error
    assert set(_preview(app)["결과 월 수"]) == {3}


def _overlapping_donor(
    repository: DuckDBScenarioRepository, donor: ScenarioSnapshot
) -> ScenarioSnapshot:
    tables = dict(donor.tables)
    tables.update(
        {
            name: frame
            for name, frame in _monthly_tables([202701, 202801, 202802]).items()
            if name in MONTHLY_TABLES
        }
    )
    tables["RQ_PKG_PLAN"] = tables["RQ_PKG_PLAN"].assign(생산수량=900.0)
    saved = repository.save_revision(
        donor.scenario.scenario_id,
        tables,
        donor.preset,
        revision_name="2027 겹침",
        parent_revision_id=donor.revision.revision_id,
    )
    return repository.load_revision(saved.revision.revision_id, apply_global_display_order=False)


def _source_rows(app: AppTest) -> pd.DataFrame:
    return next(
        item.value for item in app.dataframe if "사용할 시나리오" in item.value.columns
    ).set_index("월")


def test_overlap_choice_changes_preview_saved_values_and_resets_with_range(
    sources: Sources,
) -> None:
    repository, database, base, donor = sources
    donor = _overlapping_donor(repository, donor)
    app = _app(database, base, donor)
    sentinel = {"revision": 17, "content_token": "편집 유지", "tables": {"사용자 값": 42}}
    app.session_state[ACTIVE_SCENARIO_KEY] = sentinel
    assert app.segmented_control[0].value == "reject"
    assert _source_rows(app).loc["2027-01", "겹침"] == "겹침"
    assert _source_rows(app).loc["2027-01", "선택 출처"] == "미선택 · 저장 차단"
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)

    for policy, label, quantity in (("base", "베이스", 100.0), ("donor", "덧붙일 쪽", 900.0)):
        app.segmented_control[0].set_value(policy).run()
        assert not app.exception, [item.message for item in app.exception]
        assert not app.error
        assert not _save_button(app).disabled
        preview = _source_rows(app)
        assert preview.loc["2027-01", "선택 출처"] == label
        assert preview.loc["2028-01", "선택 출처"] == "덧붙일 쪽"
        assert (
            preview.loc["2027-01", "사용할 시나리오"]
            == (base if policy == "base" else donor).scenario.scenario_name
        )
        app.text_input(key="scenario_merge_name").set_value(f"겹침 {policy} 결과")
        _save_button(app).click().run()
        assert not app.exception, [item.message for item in app.exception]
        created = next(
            s for s in repository.list_scenarios() if s.scenario_name == f"겹침 {policy} 결과"
        )
        saved = repository.load_revision(
            created.active_revision_id, apply_global_display_order=False
        )
        assert (
            saved.tables["RQ_PKG_PLAN"].set_index("생산계획년월").loc[202701, "생산수량"]
            == quantity
        )
        assert saved.revision.note is not None
        assert f"2027-01: {label}" in saved.revision.note
        for name in MONTHLY_TABLES:
            expected = (
                donor.tables[name]
                if policy == "donor"
                else pd.concat(
                    [
                        base.tables[name],
                        donor.tables[name].loc[donor.tables[name]["생산계획년월"].ne(202701)],
                    ],
                    ignore_index=True,
                )
            )
            pd.testing.assert_frame_equal(
                saved.tables[name].sort_values("생산계획년월").reset_index(drop=True),
                expected.sort_values("생산계획년월").reset_index(drop=True),
            )
        for name in NON_MONTHLY_TABLES:
            pd.testing.assert_frame_equal(saved.tables[name], base.tables[name])
        assert _save_button(app).disabled
        assert app.session_state[ACTIVE_SCENARIO_KEY] == sentinel

    # 같은 월 범위에서도 처리 기준을 바꾸면 새 저장이 가능하고 차단으로 되돌릴 수도 있다.
    app.segmented_control[0].set_value("reject").run()
    assert app.error
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    app.segmented_control[0].set_value("donor").run()
    app.selectbox(key=f"merge_end_{donor.revision.revision_id}").set_value(202801).run()
    assert app.segmented_control[0].value == "reject"
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    assert len(repository.list_scenarios()) == 4
    for source in (base, donor):
        reloaded = repository.load_revision(
            source.revision.revision_id, apply_global_display_order=False
        )
        for name, frame in source.tables.items():
            pd.testing.assert_frame_equal(reloaded.tables[name], frame)


def test_overlap_choice_never_overrides_virtual_history_conflict(sources: Sources) -> None:
    repository, database, base, donor = sources
    donor = _overlapping_donor(repository, donor)
    base = _with_history(repository, base, (VirtualProductRecord("Product-A", "8H", "A", "8H"),))
    donor = _with_history(repository, donor, (VirtualProductRecord("Product-A", "8H", "B", "8H"),))
    app = _app(database, base, donor)
    for policy in ("base", "donor"):
        app.segmented_control[0].set_value(policy).run()
        assert not app.exception
        assert any("가상제품 복제 이력이 충돌" in item.value for item in app.error)
        assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    assert len(repository.list_scenarios()) == 2


def test_save_keeps_originals_and_active_draft_and_refreshes_changed_range(
    sources: Sources,
) -> None:
    repository, database, base, donor = sources
    app = _app(database, base, donor)
    sentinel = {"revision": 17, "content_token": "미저장 편집 토큰", "tables": {"사용자 값": 42}}
    app.session_state[ACTIVE_SCENARIO_KEY] = sentinel
    app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] = "활성 리비전 유지"
    app.text_input(key="scenario_merge_name").set_value("합친 결과")
    app.text_area(key="scenario_merge_note").set_value("UI 저장 검증")

    _save_button(app).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[ACTIVE_SCENARIO_KEY] == sentinel
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == "활성 리비전 유지"
    assert len(repository.list_scenarios()) == 3
    created = next(
        item for item in repository.list_scenarios() if item.scenario_name == "합친 결과"
    )
    merged = repository.load_revision(created.active_revision_id, apply_global_display_order=False)
    assert len(merged.tables) == 16
    assert (merged.preset.start_month, merged.preset.end_month) == (202701, 202802)
    note = merged.revision.note
    assert note is not None
    assert base.revision.revision_id in note
    assert donor.revision.revision_id in note
    assert "UI 저장 검증" in note
    for name in MONTHLY_TABLES:
        expected = pd.concat([base.tables[name], donor.tables[name]], ignore_index=True)
        pd.testing.assert_frame_equal(merged.tables[name], expected)
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(merged.tables[name], base.tables[name])
    for source in (base, donor):
        reloaded = repository.load_revision(
            source.revision.revision_id, apply_global_display_order=False
        )
        assert len(repository.list_revisions(source.scenario.scenario_id)) == 1
        for name, frame in source.tables.items():
            pd.testing.assert_frame_equal(reloaded.tables[name], frame)
    assert repository.load_global_display_order().rules["분류값"].tolist() == ["공용 표시순서"]
    assert _save_button(app).disabled

    # 같은 조건으로 다시 그려도 저장은 한 번뿐이며 제출 버튼은 계속 잠긴다.
    app.run()
    assert not app.exception
    assert _save_button(app).disabled
    assert len(repository.list_scenarios()) == 3

    app.selectbox(key=f"merge_start_{donor.revision.revision_id}").set_value(202802).run()
    assert not app.exception
    assert set(_preview(app)["결과 월 수"]) == {2}
    assert set(_preview(app)["행 수 증감"]) == {1}
    assert not _save_button(app).disabled
    assert len(repository.list_scenarios()) == 3

    app.text_input(key="scenario_merge_name").set_value("범위를 바꾼 결과")
    _save_button(app).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert len(repository.list_scenarios()) == 4
    changed = next(
        item for item in repository.list_scenarios() if item.scenario_name == "범위를 바꾼 결과"
    )
    changed_result = repository.load_revision(
        changed.active_revision_id, apply_global_display_order=False
    )
    assert len(changed_result.tables) == 16
    assert (changed_result.preset.start_month, changed_result.preset.end_month) == (202701, 202802)
    for name in MONTHLY_TABLES:
        donor_slice = donor.tables[name].loc[donor.tables[name]["생산계획년월"].eq(202802)]
        expected = pd.concat([base.tables[name], donor_slice], ignore_index=True)
        pd.testing.assert_frame_equal(changed_result.tables[name], expected)
        assert set(changed_result.tables[name]["생산계획년월"]) == {202701, 202802}
    for name in NON_MONTHLY_TABLES:
        pd.testing.assert_frame_equal(changed_result.tables[name], base.tables[name])
    for previous in (base, donor, merged):
        reloaded = repository.load_revision(
            previous.revision.revision_id, apply_global_display_order=False
        )
        for name, frame in previous.tables.items():
            pd.testing.assert_frame_equal(reloaded.tables[name], frame)
    assert app.session_state[ACTIVE_SCENARIO_KEY] == sentinel
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == "활성 리비전 유지"
    assert _save_button(app).disabled
