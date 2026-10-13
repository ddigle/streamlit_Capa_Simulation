# Purpose: 리비전 표 한 장 읽기·스냅샷 캐시가 전체 스냅샷과 같은 값을 내고 무효화되는지 본다.

"""리비전 표 한 장 읽기(`load_revision_table`·`load_scenario_plan`)의 동등성과 무효화.

합성 시드(`ensure_initial_scenario`) 위에 계획만 바꾼 리비전과 시나리오를 더해 쓴다. 비교 GAP 은
`RQ_PKG_PLAN` 한 장만 읽으므로, 그 한 장이 전체 스냅샷의 같은 표와 컬럼·dtype·값까지 같아야 하고,
지운 리비전에서는 빈 계획을 조용히 돌려주지 않고 전체 스냅샷과 같은 `KeyError` 를 내야 한다.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.persistence import cache as scenario_cache
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import (
    REFERENCE_TABLES,
    DuckDBScenarioRepository,
)


@dataclass(frozen=True)
class _Seeded:
    database_path: Path
    official_revision_id: str
    halved_revision_id: str


def _repository(database_path: Path) -> DuckDBScenarioRepository:
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    return repository


def _scaled_plan(tables: dict[str, pd.DataFrame], factor: float) -> dict[str, pd.DataFrame]:
    scaled = dict(tables)
    plan = scaled["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce") * factor
    scaled["RQ_PKG_PLAN"] = plan
    return scaled


def _create_clone(
    repository: DuckDBScenarioRepository, revision_id: str, name: str, factor: float
) -> tuple[str, str]:
    base = repository.load_revision(revision_id)
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=f"CLONE-{name}",
            source_simulation_name=name,
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        _scaled_plan(dict(base.tables), factor),
        base.preset,
    )
    return created.scenario.scenario_id, created.revision.revision_id


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> _Seeded:
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.repository import REVISION_TABLES

    database_path = tmp_path_factory.mktemp("revision-snapshot") / "scenario.duckdb"
    repository = _repository(database_path)
    release = ensure_initial_scenario(repository).release
    assert release is not None
    base = repository.load_revision(release.revision_id)
    halved = repository.save_revision(
        release.scenario_id,
        _scaled_plan(
            {name: base.tables[name] for name in REVISION_TABLES if name in base.tables}, 0.5
        ),
        base.preset,
        revision_name="계획 절반",
    )
    return _Seeded(database_path, release.revision_id, halved.revision.revision_id)


@pytest.fixture(autouse=True)
def _empty_caches() -> Iterator[None]:
    scenario_cache.clear_scenario_repository()
    yield
    scenario_cache.clear_scenario_repository()


def _assert_same_frame(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    assert list(actual.columns) == list(expected.columns)
    assert actual.dtypes.astype(str).tolist() == expected.dtypes.astype(str).tolist()
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)


# --------------------------------------------------------------- 표 한 장 = 전체 스냅샷의 그 표


@pytest.mark.parametrize("logical_name", list(REFERENCE_TABLES))
@pytest.mark.parametrize("apply_global_display_order", [True, False])
def test_one_revision_table_is_the_same_frame_as_in_the_whole_snapshot(
    seeded: _Seeded, logical_name: str, apply_global_display_order: bool
) -> None:
    """리비전 표(`rev_data`)·데이터셋 표(`ref_data`)·공용 표시순서 모두 전체 읽기와 같다."""
    repository = DuckDBScenarioRepository(seeded.database_path)
    for revision_id in (seeded.official_revision_id, seeded.halved_revision_id):
        whole = repository.load_revision(
            revision_id, apply_global_display_order=apply_global_display_order
        )
        one = repository.load_revision_table(
            revision_id, logical_name, apply_global_display_order=apply_global_display_order
        )
        _assert_same_frame(one, whole.tables[logical_name])


def test_an_unknown_table_name_is_not_mistaken_for_a_missing_revision(seeded: _Seeded) -> None:
    repository = DuckDBScenarioRepository(seeded.database_path)
    with pytest.raises(ValueError, match="RQ_NOT_A_TABLE"):
        repository.load_revision_table(seeded.official_revision_id, "RQ_NOT_A_TABLE")


def test_the_cached_comparison_plan_is_the_snapshot_plan_of_that_revision(
    seeded: _Seeded,
) -> None:
    """캐시 키의 리비전 id 하나만 달라도 그 리비전의 계획이 나온다(두 계획은 수량이 다르다)."""
    repository = DuckDBScenarioRepository(seeded.database_path)
    database_path = str(seeded.database_path)
    plans = {}
    for revision_id in (seeded.official_revision_id, seeded.halved_revision_id):
        plans[revision_id] = scenario_cache.load_scenario_plan(database_path, revision_id)
        _assert_same_frame(
            plans[revision_id], repository.load_revision(revision_id).tables["RQ_PKG_PLAN"]
        )
        # 적중해도 같은 값이다.
        _assert_same_frame(
            scenario_cache.load_scenario_plan(database_path, revision_id), plans[revision_id]
        )
    official = pd.to_numeric(plans[seeded.official_revision_id]["생산수량"])
    halved = pd.to_numeric(plans[seeded.halved_revision_id]["생산수량"])
    assert not official.equals(halved)
    pd.testing.assert_series_equal(halved, official * 0.5, check_names=False)


def test_the_comparison_plan_does_not_unpack_the_whole_snapshot(
    seeded: _Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    """비교 계획은 표 한 장만 읽는다 — 16표 스냅샷을 DB 에서 읽거나 캐시에 올리지 않는다."""

    def whole_snapshot(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("비교 계획이 리비전 16표를 읽었다")

    monkeypatch.setattr(DuckDBScenarioRepository, "load_revision", whole_snapshot)
    plan = scenario_cache.load_scenario_plan(str(seeded.database_path), seeded.halved_revision_id)
    assert not plan.empty


# --------------------------------------------------------------- 지운 리비전


def test_a_deleted_revision_raises_instead_of_reading_an_empty_plan(seeded: _Seeded) -> None:
    """확인과 읽기 사이에 다른 세션이 지운 리비전은 빈 계획(전액 감소 GAP)이 아니라 KeyError 다.

    리비전 표를 `revision_id` 로 바로 읽으면 행 0개 프레임이 예외 없이 돌아온다. 그것이 캐시에
    남으면 GAP 이 전부 감소로 그려진다. 지운 뒤 비우기(`clear_scenario_snapshot_cache`)를 거치면
    캐시된 계획도 남지 않는다.
    """
    repository = DuckDBScenarioRepository(seeded.database_path)
    database_path = str(seeded.database_path)
    scenario_id, revision_id = _create_clone(
        repository, seeded.official_revision_id, "지울 비교", 0.25
    )
    assert not scenario_cache.load_scenario_plan(database_path, revision_id).empty

    repository.delete_scenario(scenario_id)
    scenario_cache.clear_scenario_snapshot_cache()

    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.load_revision(revision_id)
    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.load_revision_table(revision_id, "RQ_PKG_PLAN")
    # 실패는 캐시에 남지 않는다 — 다시 불러도 빈 프레임이 아니라 같은 KeyError 다.
    for _ in range(2):
        with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
            scenario_cache.load_scenario_plan(database_path, revision_id)
    with pytest.raises(KeyError, match="리비전을 찾을 수 없습니다"):
        repository.load_revision_table("없는-리비전", "RQ_DISPLAY_ORDER")
