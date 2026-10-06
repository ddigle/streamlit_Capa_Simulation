# Purpose: equipment repository 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_equipment_snapshot_cache,
    get_equipment_repository,
    load_equipment_snapshot,
    load_latest_equipment_snapshot,
)
from capa_simulation.persistence.equipment_migration_runner import (
    load_equipment_migrations,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentSnapshot,
)
from capa_simulation.services.process_cutoff import empty_process_cutoff
from capa_simulation.services.weekly_availability_input import (
    build_weekly_availability_template,
    parse_weekly_availability_clipboard,
)


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    assert repository.initialize() == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15)
    assert repository.initialize() == ()
    return repository


def test_equipment_snapshots_are_immutable_revisions(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")

    first = repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="최초 저장")
    changed = _equipment()
    changed.loc[1, "Qual일정"] = "2026-08-22"
    second = repository.save_snapshot(_baseline(), changed, _downtime(), note="일정 변경")

    assert first.revision.revision_no == 1
    assert second.revision.revision_no == 2
    latest_revision_id = repository.latest_revision_id()
    assert latest_revision_id is not None
    latest = repository.load_snapshot(latest_revision_id)
    assert latest.revision == second.revision
    pd.testing.assert_frame_equal(latest.equipment, second.equipment)
    pd.testing.assert_frame_equal(latest.downtime, second.downtime)
    loaded_first = repository.load_snapshot(first.revision.revision_id)
    assert loaded_first.equipment.loc[1, "Qual일정"] == pd.Timestamp("2026-08-21")
    assert loaded_first.equipment.loc[1, "확정상태"] == "확정"
    assert loaded_first.equipment.loc[1, "담당자"] == "담당A"
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


def test_equipment_snapshot_cache_reuses_immutable_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = str((tmp_path / "cached-equipment.duckdb").resolve())
    clear_equipment_repository()
    repository = get_equipment_repository(database_path)
    saved = repository.save_snapshot(_baseline(), _equipment(), _downtime())
    clear_equipment_snapshot_cache()
    original_load = DuckDBEquipmentRepository.load_snapshot
    load_calls = 0

    def counted_load(instance: DuckDBEquipmentRepository, revision_id: str) -> EquipmentSnapshot:
        nonlocal load_calls
        load_calls += 1
        return original_load(instance, revision_id)

    monkeypatch.setattr(DuckDBEquipmentRepository, "load_snapshot", counted_load)

    latest = load_latest_equipment_snapshot(database_path)
    loaded_again = load_equipment_snapshot(database_path, saved.revision.revision_id)

    assert latest is not None
    assert latest.revision.revision_id == loaded_again.revision.revision_id
    assert load_calls == 1
    clear_equipment_repository()


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


def test_standard_target_availability_keeps_only_latest_unversioned_copy(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "equipment.duckdb")
    first = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-B"],
            "Weeknum": ["26-W32", "26-W32"],
            "가용대수": [2.0, 1.0],
        }
    )
    second = pd.DataFrame({"공정": ["Process-A"], "Weeknum": ["26-W32"], "가용대수": [3.0]})

    repository.save_standard_target_availability(first)
    saved = repository.save_standard_target_availability(second)

    assert saved["가용대수"].tolist() == [3.0, 1.0]
    assert len(repository.list_revisions()) == 0
    repository.clear_standard_target_availability()
    assert repository.load_standard_target_availability().empty


def test_pasting_a_template_edited_for_one_process_keeps_the_other_saved_process(
    tmp_path: Path,
) -> None:
    """양식을 받아 한 공정만 채워 통째로 붙여넣어도 다른 공정의 저장값은 그대로다.

    예전 양식은 모든 칸을 0.0 으로 내려 줘서, 이 흐름에서 이미 넣어 둔 Process-A 가 0 대로
    덮였다(2026-09-29 버그 보고). 지금 양식은 저장값을 싣고 나머지는 빈칸이며, 붙여넣기는
    빈칸 행을 떨어뜨려 upsert 가 그 키를 건드리지 않는다.
    """
    repository = _repository(tmp_path / "equipment.duckdb")
    processes = ["Process-A", "Process-B", "Process-C"]
    repository.save_standard_target_availability(
        pd.DataFrame(
            {
                "공정": ["Process-A", "Process-A"],
                "Weeknum": ["26-W02", "26-W03"],
                "가용대수": [5.0, 4.0],
            }
        )
    )

    template = build_weekly_availability_template(
        processes,
        date(2026, 1, 5),
        date(2026, 1, 18),
        saved=repository.load_standard_target_availability(),
    )
    edited = template.copy()
    edited.loc[edited["공정"].eq("Process-B"), "가용대수"] = 3.0
    repository.save_standard_target_availability(
        parse_weekly_availability_clipboard(
            edited.to_csv(sep="\t", index=False), known_processes=processes
        )
    )

    stored = repository.load_standard_target_availability()
    assert stored.to_dict("records") == [
        {"공정": "Process-A", "Weeknum": "26-W02", "가용대수": 5.0},
        {"공정": "Process-A", "Weeknum": "26-W03", "가용대수": 4.0},
        {"공정": "Process-B", "Weeknum": "26-W02", "가용대수": 3.0},
        {"공정": "Process-B", "Weeknum": "26-W03", "가용대수": 3.0},
    ]
    # 아무도 적지 않은 Process-C 는 0 대가 아니라 미설정(행 없음)으로 남는다.
    assert "Process-C" not in set(stored["공정"])


def test_legacy_revision_loads_after_contract_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.duckdb"
    migrations = load_equipment_migrations()
    with duckdb.connect(str(database_path)) as connection:
        for migration in migrations[:2]:
            connection.execute(migration.sql)
            connection.execute(
                """
                INSERT INTO equipment_meta.schema_migration (version, name, checksum)
                VALUES (?, ?, ?)
                """,
                [migration.version, migration.name, migration.checksum],
            )
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash,
                equipment_hash, downtime_hash
            ) VALUES ('legacy-r1', 1, 'legacy', 'b', 's', 'e', 'd')
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.baseline_snapshot
            VALUES ('legacy-r1', 1, 'Process-A', '전체', 2, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_snapshot (
                revision_id, source_row_no, equipment_id, process_name,
                classification, building, floor_name, x_coordinate, y_coordinate,
                width_value, arrival_date, production_transition_date
            ) VALUES (
                'legacy-r1', 1, 'EQ-LEGACY', 'Process-A', '전체',
                'C1', '1F', 10, 10, 12, DATE '2026-08-01', DATE '2026-08-10'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.downtime_snapshot (
                revision_id, source_row_no, downtime_id, equipment_id,
                downtime_type, start_date
            ) VALUES (
                'legacy-r1', 1, 'DOWN-LEGACY', 'EQ-LEGACY', '고장', DATE '2026-08-11'
            )
            """
        )

    repository = DuckDBEquipmentRepository(database_path)
    assert repository.initialize() == (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15)
    snapshot = repository.load_snapshot("legacy-r1")

    assert snapshot.equipment.loc[0, "설비명"] == "EQ-LEGACY"
    assert snapshot.equipment.loc[0, "공정소분류"] == "Process-A"
    assert snapshot.equipment.loc[0, "Qual일정"] == pd.Timestamp("2026-08-10")
    assert snapshot.equipment.loc[0, "확정상태"] == "계획"
    assert snapshot.downtime.columns.tolist() == [
        "설비명",
        "비가동유형",
        "시작일",
        "종료일",
        "상세사유",
        "비고",
    ]


def test_legacy_revision_without_production_date_keeps_qual_blank(tmp_path: Path) -> None:
    """옛 양산전환일이 없으면 Qual일정도 비운다(먼 미래 날짜로 채우지 않는다). 확정상태는 Qual 이
    있는 행에만 「계획」이다."""
    database_path = tmp_path / "legacy-no-qual.duckdb"
    migrations = load_equipment_migrations()
    with duckdb.connect(str(database_path)) as connection:
        for migration in migrations[:2]:
            connection.execute(migration.sql)
            connection.execute(
                """
                INSERT INTO equipment_meta.schema_migration (version, name, checksum)
                VALUES (?, ?, ?)
                """,
                [migration.version, migration.name, migration.checksum],
            )
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash,
                equipment_hash, downtime_hash
            ) VALUES ('legacy-r1', 1, 'legacy', 'b', 's', 'e', 'd')
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_snapshot (
                revision_id, source_row_no, equipment_id, process_name,
                classification, arrival_date, production_transition_date
            ) VALUES
                ('legacy-r1', 1, 'EQ-NOQUAL', 'Process-A', '전체', DATE '2026-08-01', NULL),
                ('legacy-r1', 2, 'EQ-QUAL', 'Process-A', '전체', DATE '2026-08-01',
                 DATE '2026-08-10'),
                ('legacy-r1', 3, 'EQ-OLD', 'Process-A', '전체', NULL, NULL)
            """
        )

    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    equipment = repository.load_snapshot("legacy-r1").equipment.set_index("설비명")

    assert pd.isna(equipment.loc["EQ-NOQUAL", "Qual일정"])
    assert pd.isna(equipment.loc["EQ-NOQUAL", "확정상태"])
    assert equipment.loc["EQ-NOQUAL", "기존설비여부"] == "N"
    assert equipment.loc["EQ-QUAL", "확정상태"] == "계획"
    assert pd.isna(equipment.loc["EQ-OLD", "Qual일정"])
    assert equipment.loc["EQ-OLD", "기존설비여부"] == "Y"


def test_process_cutoff_round_trips_and_replaces_the_whole_table(tmp_path: Path) -> None:
    """Cut-off 는 통째로 갈아 끼운다 — 행을 지우는 것이 「산출에서 빼라」는 뜻이다."""
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()

    assert repository.load_process_cutoff().empty

    saved = repository.save_process_cutoff(
        pd.DataFrame(
            {
                "공정": ["DEMO_ATTACH", "DEMO_MOLD"],
                "Cutoff일수": [15.0, 7.5],
                "비고": ["표준", None],
            }
        )
    )
    assert list(saved["공정"]) == ["DEMO_ATTACH", "DEMO_MOLD"]
    assert list(saved["Cutoff일수"]) == [15.0, 7.5]
    assert set(saved["제품구분"]) == {"*"}

    # 한 행만 다시 저장하면 나머지는 사라져야 한다(부분 upsert 가 아니다).
    replaced = repository.save_process_cutoff(
        pd.DataFrame({"공정": ["DEMO_MOLD"], "Cutoff일수": [9.0], "비고": [None]})
    )
    assert list(replaced["공정"]) == ["DEMO_MOLD"]
    assert list(replaced["Cutoff일수"]) == [9.0]

    repository.save_process_cutoff(empty_process_cutoff())
    assert repository.load_process_cutoff().empty


def test_process_cutoff_refuses_a_negative_value(tmp_path: Path) -> None:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()

    with pytest.raises(ValueError, match="음수"):
        repository.save_process_cutoff(
            pd.DataFrame({"공정": ["DEMO_ATTACH"], "Cutoff일수": [-1.0], "비고": [None]})
        )
