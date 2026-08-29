from pathlib import Path

import duckdb
import pandas as pd

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from tests.test_equipment_availability import _baseline, _downtime, _equipment


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    assert repository.initialize() == (1, 2)
    assert repository.initialize() == ()
    return repository


def test_equipment_snapshots_are_immutable_revisions(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    first = repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="최초 저장")
    changed = _equipment()
    changed.loc[1, "양산전환일"] = "2026-08-21"
    second = repository.save_snapshot(_baseline(), changed, _downtime(), note="일정 변경")

    assert first.revision.revision_no == 1
    assert second.revision.revision_no == 2
    latest = repository.load_latest_snapshot()
    assert latest is not None
    assert latest.revision == second.revision
    pd.testing.assert_frame_equal(latest.equipment, second.equipment)
    pd.testing.assert_frame_equal(latest.downtime, second.downtime)
    loaded_first = repository.load_snapshot(first.revision.revision_id)
    assert pd.isna(loaded_first.equipment.loc[1, "양산전환일"])
    assert [revision.revision_no for revision in repository.list_revisions()] == [2, 1]


def test_equipment_snapshot_allows_empty_unit_inputs(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    snapshot = repository.save_snapshot(
        _baseline(),
        _equipment().iloc[0:0],
        _downtime().iloc[0:0],
    )

    assert snapshot.equipment.empty
    assert snapshot.downtime.empty
    assert snapshot.revision.equipment_row_count == 0


def test_equipment_database_has_no_simulation_schemas(tmp_path: Path) -> None:
    database_path = tmp_path / "equipment.duckdb"
    _repository(database_path)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        schemas = {
            str(row[0])
            for row in connection.execute(
                "SELECT schema_name FROM information_schema.schemata"
            ).fetchall()
        }

    assert {"equipment_meta", "equipment_ops"}.issubset(schemas)
    assert "app_meta" not in schemas
    assert "ref_data" not in schemas
    assert "rev_data" not in schemas
