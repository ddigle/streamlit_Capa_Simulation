# Purpose: 입장 Summary GAP 몫이 적중 때 공식 스냅샷을 꺼내지 않고 빗나갈 때 같은 값을 내는지 본다.

"""입장 Summary GAP 몫(`intro_summary._comparison_part`)의 공식 스냅샷 늦게 꺼내기.

비교 계획 환산(`get_home_comparison_plan`)은 (HOME 키, 비교 리비전, EDP, 세부 분류)로 캐시된다.
적중하면 공식 리비전의 기준정보 표가 쓰이지 않으므로 꺼내지 않는다. 빗나가면 바로 그 공식 리비전의
표와, 요약 키(`home_key`)의 표시순서 지문을 만든 바로 그 표시순서로 환산한다 — 늦게 꺼내도 값은
미리 꺼낸 것과 같다.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import pandas as pd
import pytest

from capa_simulation import settings
from capa_simulation.components import intro_summary
from capa_simulation.persistence import cache as scenario_cache
from capa_simulation.persistence.models import (
    OfficialReleaseSummary,
    ScenarioCreate,
    ScenarioSnapshot,
)
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.services.dashboard import PRODUCTION_DETAIL_DIMENSIONS
from capa_simulation.services.simulation_cache import get_home_comparison_plan


@dataclass(frozen=True)
class _Seeded:
    database_path: Path
    scenario_id: str
    halved_revision_id: str
    quarter_scenario_id: str
    quarter_revision_id: str


def _scaled(tables: dict[str, pd.DataFrame], factor: float) -> dict[str, pd.DataFrame]:
    scaled = dict(tables)
    plan = scaled["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce") * factor
    scaled["RQ_PKG_PLAN"] = plan
    return scaled


def _with_other_conversion(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """환산 기준정보(Chip 환산·수율)도 공식과 다르게 — 다른 리비전의 표로 환산하면 값이 갈린다."""
    changed = dict(tables)
    chip_eq = changed["RQ_CHIP_EQ"].copy()
    chip_eq["구분_EQ"] = pd.to_numeric(chip_eq["구분_EQ"], errors="coerce") * 2
    changed["RQ_CHIP_EQ"] = chip_eq
    yields = changed["RQ_YLD"].copy()
    yields["BE_수율"] = pd.to_numeric(yields["BE_수율"], errors="coerce") * 0.8
    changed["RQ_YLD"] = yields
    return changed


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> _Seeded:
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    database_path = tmp_path_factory.mktemp("intro-gap") / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    release = ensure_initial_scenario(repository).release
    assert release is not None
    base = repository.load_revision(release.revision_id)
    halved = repository.save_revision(
        release.scenario_id,
        _scaled({name: base.tables[name] for name in REVISION_TABLES}, 0.5),
        base.preset,
        revision_name="계획 절반",
    )
    quarter = repository.create_scenario(
        ScenarioCreate(
            scenario_name="계획 4분의 1",
            source_simulation_code="CLONE-QUARTER",
            source_simulation_name="계획 4분의 1",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        _with_other_conversion(_scaled(dict(base.tables), 0.25)),
        base.preset,
    )
    return _Seeded(
        database_path,
        release.scenario_id,
        halved.revision.revision_id,
        quarter.scenario.scenario_id,
        quarter.revision.revision_id,
    )


@pytest.fixture(autouse=True)
def _settings_point_at_the_seeded_database(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    """요약 만들기의 공정 표시명(`get_process_labels`)은 `settings.DUCKDB_PATH` 를 연다 — 저장소
    DB 가 아니라 이 시험의 DB 를 보게 한다."""
    monkeypatch.setattr(settings, "DUCKDB_PATH", seeded.database_path)


@pytest.fixture(autouse=True)
def _empty_caches() -> Iterator[None]:
    scenario_cache.clear_scenario_repository()
    get_home_comparison_plan.clear()
    yield
    scenario_cache.clear_scenario_repository()
    get_home_comparison_plan.clear()


def _summary(seeded: _Seeded) -> tuple[OfficialReleaseSummary, dict[str, Any]]:
    database_path = str(seeded.database_path)
    release = scenario_cache.get_scenario_repository(database_path).latest_official_release()
    assert release is not None
    thresholds = scenario_cache.load_global_securement_threshold(database_path).thresholds
    payload = intro_summary._build(database_path, release, thresholds)
    context = payload[intro_summary._CONTEXT]
    assert isinstance(context, dict)
    return release, context


def _profile(scenario_id: str, revision_id: str) -> Any:
    return SimpleNamespace(version=1, scenario_id=scenario_id, revision_id=revision_id)


def _eager_frames(
    database_path: str, release: OfficialReleaseSummary, context: dict[str, Any], revision_id: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """공식 스냅샷과 그 표시순서를 미리 꺼내 넘기는 환산(늦게 꺼내기의 기준)."""
    tables = scenario_cache.load_scenario_snapshot(database_path, release.revision_id).tables
    return get_home_comparison_plan(
        cache_key=context["home_key"],
        _tables=tables,
        _comparison_plan=scenario_cache.load_scenario_plan(database_path, revision_id),
        _display_order=tables["RQ_DISPLAY_ORDER"],
        comparison_revision_id=revision_id,
        include_edp=False,
        detail_dimensions=tuple(PRODUCTION_DETAIL_DIMENSIONS),
    )


def test_the_lazy_gap_is_the_same_as_the_eager_gap(seeded: _Seeded) -> None:
    """늦게 꺼낸 표로 환산한 GAP 몫·환산 프레임이 미리 꺼낸 표로 환산한 것과 같다."""
    database_path = str(seeded.database_path)
    release, context = _summary(seeded)
    for scenario_id, revision_id in (
        (seeded.scenario_id, seeded.halved_revision_id),
        (seeded.quarter_scenario_id, seeded.quarter_revision_id),
    ):
        get_home_comparison_plan.clear()
        eager = _eager_frames(database_path, release, context, revision_id)

        def eager_plan(
            _revision_id: str, frames: tuple[pd.DataFrame, ...] = eager
        ) -> tuple[pd.DataFrame, pd.DataFrame]:
            return frames[0], frames[1]

        expected = intro_summary.comparison_part(
            database_path,
            release,
            _profile(scenario_id, revision_id),
            months=list(context["months"]),
            monthly_density=context["density"],
            monthly_wafer=context["wafer"],
            load_plan=eager_plan,
        )

        get_home_comparison_plan.clear()
        lazy = intro_summary._comparison_part(
            database_path, release, _profile(scenario_id, revision_id), context
        )
        assert lazy == expected
        assert lazy["available"] is True
        # 늦게 꺼내 환산한 뒤 캐시에 든 프레임이 미리 꺼내 환산한 프레임과 같다.
        cached = _eager_frames(database_path, release, context, revision_id)
        for actual, wanted in zip(cached, eager, strict=True):
            pd.testing.assert_frame_equal(actual, wanted, check_exact=True)


def test_the_context_display_order_is_the_one_in_the_summary_key(seeded: _Seeded) -> None:
    database_path = str(seeded.database_path)
    release, context = _summary(seeded)
    official = scenario_cache.load_scenario_snapshot(database_path, release.revision_id)
    pd.testing.assert_frame_equal(
        context["display_order"], official.tables["RQ_DISPLAY_ORDER"], check_exact=True
    )


def test_a_hit_does_not_take_out_the_official_snapshot(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    """환산 캐시가 적중하면 공식 스냅샷을 꺼내지 않는다. 빗나가면 공식 리비전을 한 번만 꺼낸다."""
    database_path = str(seeded.database_path)
    release, context = _summary(seeded)
    original = scenario_cache.load_scenario_snapshot
    calls: list[str] = []

    def counted(path: str, revision_id: str) -> ScenarioSnapshot:
        calls.append(revision_id)
        return original(path, revision_id)

    monkeypatch.setattr(intro_summary, "load_scenario_snapshot", counted)
    halved = _profile(seeded.scenario_id, seeded.halved_revision_id)
    first = intro_summary._comparison_part(database_path, release, halved, context)
    assert calls == [release.revision_id]
    again = intro_summary._comparison_part(database_path, release, halved, context)
    assert calls == [release.revision_id]
    assert again == first

    # 키의 비교 리비전 하나만 달라도 새로 환산한다 — 값도 다르다.
    quarter = intro_summary._comparison_part(
        database_path,
        release,
        _profile(seeded.quarter_scenario_id, seeded.quarter_revision_id),
        context,
    )
    assert calls == [release.revision_id, release.revision_id]
    assert quarter["available"] is True
    assert quarter["density"] != first["density"]


def test_a_transient_failure_while_taking_out_the_snapshot_stays_pending(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    """빗나간 환산 안에서 늦게 꺼내다 DB 가 잠기면 그대로 올라간다(「준비 중」) — 남지 않는다."""
    database_path = str(seeded.database_path)
    release, context = _summary(seeded)
    halved = _profile(seeded.scenario_id, seeded.halved_revision_id)
    expected = intro_summary._comparison_part(database_path, release, halved, context)
    get_home_comparison_plan.clear()

    def locked(_path: str, _revision_id: str) -> ScenarioSnapshot:
        raise duckdb.IOException("잠김")

    with monkeypatch.context() as patched:
        patched.setattr(intro_summary, "load_scenario_snapshot", locked)
        with pytest.raises(duckdb.IOException):
            intro_summary._guarded(
                "GAP",
                lambda: intro_summary._comparison_part(database_path, release, halved, context),
            )
    assert intro_summary._comparison_part(database_path, release, halved, context) == expected


def test_a_summary_without_the_display_order_material_still_converts(seeded: _Seeded) -> None:
    """재료에 표시순서가 없는 요약(그 재료를 싣기 전에 서버 캐시에 든 값)도 같은 GAP 을 낸다."""
    database_path = str(seeded.database_path)
    release, context = _summary(seeded)
    halved = _profile(seeded.scenario_id, seeded.halved_revision_id)
    expected = intro_summary._comparison_part(database_path, release, halved, context)
    get_home_comparison_plan.clear()
    older = {key: value for key, value in context.items() if key != "display_order"}
    assert intro_summary._comparison_part(database_path, release, halved, older) == expected
