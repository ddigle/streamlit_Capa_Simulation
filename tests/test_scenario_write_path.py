# Purpose: 리비전을 만드는 조립 계층이 Repository 가 받는 형태를 내놓는지 지킨다.

"""시나리오 쓰기 경로의 조립 단계를 고정한다.

`components/scenario_management.py` 는 불변 리비전을 만들고 공식버전을 발행하는 유일한
쓰기 진입점이다. 아래 Repository 계층(`test_duckdb_repository.py`)은 잘 덮여 있는데,
그 Repository 에 넘길 payload 를 **조립하는** 이 층은 어떤 테스트도 import 하지 않았다
(실측 커버리지 43%). 조립이 깨지면 잘못된 스냅샷이 영구 기록되고, 리비전은 불변이라
지우고 다시 만들 수 없다.

`test_all_pages_render.py` 는 페이지를 열기만 하고 폼을 제출하지 않아 이 경로에 닿지 않는다.
여기서는 폼을 흉내 내는 대신 **조립 결과가 Repository 계약을 통과하는지**를 본다.
"""

from pathlib import Path

import pandas as pd
import pytest
from test_duckdb_repository import _reference_tables

from capa_simulation.components.scenario_management import (
    _compatible_preset,
    revision_tables_for_save,
)
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.scenario_state import ActiveScenario


def _preset(**overrides: object) -> ScenarioPreset:
    """저장 경로가 요구하는 최소 프리셋. 월 범위는 필수 인자다."""
    base: dict[str, object] = {
        "start_month": 202608,
        "end_month": 202608,
        "included_processes": ("Process-A",),
    }
    base.update(overrides)
    return ScenarioPreset(**base)  # type: ignore[arg-type]


def _active(tables: dict[str, pd.DataFrame]) -> ActiveScenario:
    return ActiveScenario(
        reference_version=1,
        revision=0,
        content_token="test-token",
        tables=dict(tables),
    )


def _repository(path: Path) -> DuckDBScenarioRepository:
    repository = DuckDBScenarioRepository(path)
    repository.initialize()
    return repository


def test_assembled_tables_cover_every_revision_owned_table() -> None:
    """하나라도 빠지면 `save_revision` 이 거부한다. 조용히 빠지는 일이 없어야 한다."""
    tables = _reference_tables()

    assembled = revision_tables_for_save(_active(tables), tables)

    assert set(assembled) == set(REVISION_TABLES)


def test_assembly_takes_the_edited_frame_not_the_reference_one() -> None:
    """편집본을 저장해야 한다. 기준정보를 그대로 저장하면 사용자의 수정이 사라진다."""
    tables = _reference_tables()
    edited = {name: frame.copy() for name, frame in tables.items()}
    edited["RQ_PKG_PLAN"] = edited["RQ_PKG_PLAN"].assign(생산수량=999.0)

    assembled = revision_tables_for_save(_active(edited), tables)

    assert assembled["RQ_PKG_PLAN"]["생산수량"].eq(999.0).all()


def test_a_missing_table_is_reported_instead_of_written(tmp_path: Path) -> None:
    """조립이 한 테이블을 놓치면 Repository 가 막아야 한다. 조용히 저장되면 안 된다."""
    tables = _reference_tables()
    repository = _repository(tmp_path / "scenario.duckdb")
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name="쓰기 경로",
            source_simulation_code="TEST",
            source_simulation_name="테스트",
            source_type="test",
            pipeline_version="test-v1",
        ),
        tables,
        _preset(),
    )
    incomplete = dict(revision_tables_for_save(_active(tables), tables))
    incomplete.pop("RQ_REQB")

    # `require_tables` 는 KeyError 를 던진다. 화면의 except 절이 그것을 잡고 있어야
    # 사용자에게 오류로 보인다(`_render_revision_save` 는 KeyError·TypeError·ValueError 를 잡는다).
    with pytest.raises(KeyError, match="RQ_REQB"):
        repository.save_revision(
            snapshot.scenario.scenario_id,
            incomplete,
            _preset(),
            revision_name="불완전",
        )


def test_assembled_payload_round_trips_through_the_repository(tmp_path: Path) -> None:
    """조립 → 저장 → 복원이 같은 값을 돌려주는지 본다. 이 층의 실제 계약이다."""
    tables = _reference_tables()
    repository = _repository(tmp_path / "scenario.duckdb")
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="쓰기 경로",
            source_simulation_code="TEST",
            source_simulation_name="테스트",
            source_type="test",
            pipeline_version="test-v1",
        ),
        tables,
        _preset(),
    )
    edited = {name: frame.copy() for name, frame in tables.items()}
    edited["RQ_PKG_PLAN"] = edited["RQ_PKG_PLAN"].assign(생산수량=777.0)

    saved = repository.save_revision(
        created.scenario.scenario_id,
        revision_tables_for_save(_active(edited), tables),
        _preset(),
        revision_name="편집본",
        parent_revision_id=created.revision.revision_id,
    )
    restored = repository.load_revision(saved.revision.revision_id)

    assert restored.tables["RQ_PKG_PLAN"]["생산수량"].eq(777.0).all()
    assert set(restored.tables) >= set(REVISION_TABLES)


def test_preset_drops_processes_that_the_revision_no_longer_has() -> None:
    """공정이 사라진 리비전에 옛 프리셋을 얹으면 없는 공정이 필터에 남는다."""
    tables = _reference_tables()
    present = tables["RQ_REQB"]["공정"].astype("string").str.strip().dropna().unique().tolist()
    preset = _preset(included_processes=(*present[:1], "사라진 공정"))

    compatible = _compatible_preset(preset, tables)

    assert "사라진 공정" not in compatible.included_processes
    assert compatible.included_processes == (present[0],)
