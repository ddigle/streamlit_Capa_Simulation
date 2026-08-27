from pathlib import Path

import duckdb
import pandas as pd

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


def _baseline(count: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Process-A"],
            "분류": ["기존 보유"],
            "기존보유대수": [count],
            "비고": [None],
        }
    )


def _schedule(complete_date: str = "2026-08-15") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "호기": ["EQ-01"],
            "공정": ["Process-A"],
            "분류": ["신규 도입"],
            "입고일": ["2026-08-01"],
            "셋업시작일": ["2026-08-03"],
            "셋업완료일": [complete_date],
            "비고": ["신규"],
        }
    )


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    assert repository.initialize() == (1,)
    assert repository.initialize() == ()
    return repository


def test_equipment_snapshots_are_immutable_revisions(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    first = repository.save_snapshot(_baseline(), _schedule(), note="최초 저장")
    second = repository.save_snapshot(
        _baseline(3),
        _schedule("2026-08-20"),
        note="일정 변경",
    )

    assert first.revision.revision_no == 1
    assert second.revision.revision_no == 2
    latest = repository.load_latest_snapshot()
    assert latest is not None
    assert latest.revision == second.revision
    pd.testing.assert_frame_equal(latest.baseline, second.baseline)
    pd.testing.assert_frame_equal(latest.schedule, second.schedule)
    loaded_first = repository.load_snapshot(first.revision.revision_id)
    assert loaded_first.baseline.loc[0, "기존보유대수"] == 2
    assert loaded_first.schedule.loc[0, "셋업완료일"] == pd.Timestamp("2026-08-15")
    assert [revision.revision_no for revision in repository.list_revisions()] == [2, 1]


def test_equipment_snapshot_allows_an_empty_schedule(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    empty_schedule = _schedule().iloc[0:0]

    snapshot = repository.save_snapshot(_baseline(), empty_schedule)

    assert snapshot.schedule.empty
    assert snapshot.revision.schedule_row_count == 0


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
