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
from capa_simulation.scenario_activation import (
    ACTIVE_PERSISTED_REVISION_ID_KEY,
    ACTIVE_PERSISTED_SCENARIO_ID_KEY,
)
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
# 이 칸이 참인 회차는 화면을 그리지 않는다 — 모드 전환·페이지 이동으로 상자가 사라진 회차와 같다.
HIDE_KEY = "test_merge_hidden"


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
import streamlit as st

from capa_simulation.components.scenario_month_merge import render_scenario_month_merge
from capa_simulation.persistence.cache import get_scenario_repository

database_path = {str(database)!r}
if not st.session_state.get({HIDE_KEY!r}):
    render_scenario_month_merge(get_scenario_repository(database_path), database_path)
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    app.selectbox(key="merge_base_scenario").set_value(base.scenario.scenario_id).run()
    app.selectbox(key="merge_donor_scenario").set_value(donor.scenario.scenario_id).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _save_button(app: AppTest) -> Button:
    return next(button for button in app.button if button.label == "새 시나리오로 저장")


def _expected_non_monthly(
    base: ScenarioSnapshot, donor: ScenarioSnapshot
) -> dict[str, pd.DataFrame]:
    """월 없는 표의 기대값. 덧붙일 쪽에만 있는 제품(Product-A · 12H)의 Chip 기준만 보충된다."""
    expected = {name: base.tables[name] for name in NON_MONTHLY_TABLES}
    density = donor.tables["RQ_CHIP_EQ"]
    expected["RQ_CHIP_EQ"] = pd.concat(
        [base.tables["RQ_CHIP_EQ"], density.loc[density["Stack"].eq("12H")]], ignore_index=True
    )
    return expected


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
    assert comparison.loc["RQ_CHIP_EQ", "보충 행 수"] == 1
    assert comparison.loc["RQ_DISPLAY_ORDER", "비교"] == "다름 · 베이스 유지"
    assert any("베이스에 없는 제품" in warning.value for warning in app.warning)
    assert set(_preview(app)["결과 월 수"]) == {3}
    assert set(_preview(app)["행 수 증감"]) == {2}
    assert len(repository.list_scenarios()) == 2
    assert not _save_button(app).disabled


def test_default_name_follows_the_changed_base(sources: Sources) -> None:
    repository, database, base, donor = sources
    other = repository.create_scenario(
        _metadata("다른 베이스 2026"),
        _monthly_tables([202601]),
        ScenarioPreset(202601, 202601, ("Process-A",)),
    )
    app = _app(database, base, donor)
    assert app.text_input(key="scenario_merge_name").value == "베이스 2027 · 월 머지"

    app.selectbox(key="merge_base_scenario").set_value(other.scenario.scenario_id).run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.text_input(key="scenario_merge_name").value == "다른 베이스 2026 · 월 머지"
    _save_button(app).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert any(
        item.scenario_name == "다른 베이스 2026 · 월 머지" for item in repository.list_scenarios()
    )


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
        for name, expected in _expected_non_monthly(base, donor).items():
            pd.testing.assert_frame_equal(saved.tables[name], expected)
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
    for name, expected in _expected_non_monthly(base, donor).items():
        pd.testing.assert_frame_equal(merged.tables[name], expected)
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
    for name, expected in _expected_non_monthly(base, donor).items():
        pd.testing.assert_frame_equal(changed_result.tables[name], expected)
    for previous in (base, donor, merged):
        reloaded = repository.load_revision(
            previous.revision.revision_id, apply_global_display_order=False
        )
        for name, frame in previous.tables.items():
            pd.testing.assert_frame_equal(reloaded.tables[name], frame)
    assert app.session_state[ACTIVE_SCENARIO_KEY] == sentinel
    assert app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] == "활성 리비전 유지"
    assert _save_button(app).disabled


def test_a_module_gap_blocks_the_save_with_examples(sources: Sources) -> None:
    """사내 머지 ①: 모듈수(RQ_MODULE)가 어느 쪽에도 없는 공정은 계산을 멈춘다 — 저장 전에 막는다.

    RQ_MODULE 은 앱에서 고칠 수 없어 저장해 두면 그 시나리오는 영구히 발행할 수 없다(감사 D2).
    """
    repository, database, base, donor = sources
    tables = dict(donor.tables)
    upeh = tables["RQ_UPEH"]
    tables["RQ_UPEH"] = pd.concat([upeh, upeh.assign(공정="Process-Z")], ignore_index=True)
    no_module = repository.save_revision(
        donor.scenario.scenario_id,
        tables,
        donor.preset,
        revision_name="모듈수 없는 공정",
        parent_revision_id=donor.revision.revision_id,
    )

    app = _app(database, base, no_module)

    blocked = [item.value for item in app.error if "RQ_MODULE" in item.value]
    assert blocked and "Process-Z" in blocked[0] and "2028-01~2028-02" in blocked[0]
    assert not any(button.label == "새 시나리오로 저장" for button in app.button)
    assert len(repository.list_scenarios()) == 2


def test_empty_calendar_months_between_the_sources_are_warned(sources: Sources) -> None:
    """감사 D6: 결과 월 사이의 빈 달은 막지 않고 알린다 — 계획·설비가 없는 달로 보인다."""
    _, database, base, donor = sources

    app = _app(database, base, donor)

    gaps = [item.value for item in app.warning if "빈 달" in item.value]
    assert gaps and "11개월" in gaps[0] and "2027-02~2027-12" in gaps[0]
    assert not _save_button(app).disabled


def test_virtual_history_follows_the_result_and_a_clash_is_warned(sources: Sources) -> None:
    """감사 D1·D4: 이력은 결과 표에 남은 제품만 적고, 다른 쪽에선 실제 제품인 키를 알린다.

    메모의 「가상제품 복제 이력 N건 보존」은 결과에 실제로 남은 건수다.
    """
    repository, database, base, donor = sources
    clash = VirtualProductRecord("Product-A", "8H", "원본 A", "8H")
    gone = VirtualProductRecord("Product-Gone", "8H", "원본 A", "8H")
    donor = _with_history(repository, donor, (clash, gone))

    app = _app(database, base, donor)

    warnings = [item.value for item in app.warning]
    assert any("Product-A · 8H" in item and "실제 제품" in item for item in warnings)
    assert any("Product-Gone · 8H" in item for item in warnings)
    app.text_input(key="scenario_merge_name").set_value("이력 정리 머지")
    _save_button(app).click().run()
    assert not app.exception, [item.message for item in app.exception]
    created = next(s for s in repository.list_scenarios() if s.scenario_name == "이력 정리 머지")
    pd.testing.assert_frame_equal(
        repository.list_virtual_products(created.active_revision_id), records_to_frame((clash,))
    )
    note = repository.load_revision(created.active_revision_id).revision.note
    assert note is not None
    assert "가상제품 복제 이력: 1건 보존" in note
    assert "결과 표에 없어 뺀 이력 1건" in note


def test_a_refused_derived_save_writes_nothing(
    sources: Sources, monkeypatch: pytest.MonkeyPatch
) -> None:
    """감사 D3: 결과의 계산 검사에 막히면 저장하지 않고, 허락하며 경고하면 저장 뒤에도 보인다."""
    import capa_simulation.components.scenario_transform as scenario_transform
    from capa_simulation.components.capacity_gate import GateVerdict

    repository, database, base, donor = sources
    monkeypatch.setattr(
        scenario_transform,
        "derived_save_verdict",
        lambda *args: GateVerdict(False, "이번 머지가 깨뜨린 것입니다"),
    )
    app = _app(database, base, donor)
    app.text_input(key="scenario_merge_name").set_value("막힐 머지")
    _save_button(app).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("이번 머지가 깨뜨린" in item.value for item in app.error)
    assert len(repository.list_scenarios()) == 2
    assert not _save_button(app).disabled

    monkeypatch.setattr(
        scenario_transform,
        "derived_save_verdict",
        lambda *args: GateVerdict(True, "원본부터 있던 오류가 남아 있습니다"),
    )
    _save_button(app).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert len(repository.list_scenarios()) == 3
    assert any("원본부터 있던 오류" in item.value for item in app.warning)


def _activate(app: AppTest, snapshot: ScenarioSnapshot) -> None:
    app.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY] = snapshot.scenario.scenario_id
    app.session_state[ACTIVE_PERSISTED_REVISION_ID_KEY] = snapshot.revision.revision_id


def test_source_revisions_follow_a_changed_active_revision_in_both_roles(
    sources: Sources,
) -> None:
    """활성 리비전이 바뀌면 그 시나리오를 고른 상자(베이스·덧붙일)가 새 활성 리비전으로 다시 선다.

    일부러 고른 리비전은 활성이 그대로인 동안 남고, 상자가 사라졌던 회차를 지나도 따라온다.
    """
    repository, database, base, donor = sources
    base_key = f"merge_base_revision_{base.scenario.scenario_id}"
    donor_key = f"merge_donor_revision_{donor.scenario.scenario_id}"

    def save(parent: ScenarioSnapshot, name: str) -> ScenarioSnapshot:
        return repository.save_revision(
            parent.scenario.scenario_id,
            parent.tables,
            parent.preset,
            revision_name=name,
            parent_revision_id=parent.revision.revision_id,
        )

    app = _app(database, base, donor)
    _activate(app, base)
    app.run()
    assert app.selectbox(key=base_key).value == base.revision.revision_id

    base_r2 = save(base, "베이스 r2")
    _activate(app, base_r2)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.selectbox(key=base_key).value == base_r2.revision.revision_id

    app.selectbox(key=base_key).set_value(base.revision.revision_id).run()
    app.run()
    assert app.selectbox(key=base_key).value == base.revision.revision_id

    donor_r2 = save(donor, "덧붙일 r2")
    _activate(app, donor_r2)
    app.run()
    assert app.selectbox(key=donor_key).value == donor_r2.revision.revision_id
    assert app.selectbox(key=base_key).value == base.revision.revision_id

    app.session_state[HIDE_KEY] = True
    app.run()
    donor_r3 = save(donor_r2, "덧붙일 r3")
    _activate(app, donor_r3)
    app.session_state[HIDE_KEY] = False
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.selectbox(key=donor_key).value == donor_r3.revision.revision_id

    # 활성이 다른 시나리오로 갔다가 같은 리비전으로 돌아오면 상자가 그 리비전으로 다시 선다.
    _activate(app, base_r2)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.selectbox(key=base_key).value == base_r2.revision.revision_id
    assert app.selectbox(key=donor_key).value == donor_r3.revision.revision_id
