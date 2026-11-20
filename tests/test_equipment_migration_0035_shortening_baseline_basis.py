# Purpose: 설비 DB 0035(기준선 현재 일정 기준 칸)의 스키마 · 옛 기준선 읽기 · 저장 왕복을 검증한다.

"""설비 DB 마이그레이션 `0035_shortening_baseline_basis`.

기준선 머리 `shortening_baseline` 에 NULL 허용 칸 `schedule_basis` 하나를 더하고 아무것도 옮기지
않는다. 0034 DB 에 저장된 옛 기준선은 NULL 로 읽혀 「설비 마스터」 이고, 새로 저장하는 기준선은
그때 계획의 기준(Static · 설비 마스터)을 남긴다(2026-11-20 사용자 보드 답 Q14 (가)).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd
from test_equipment_migration_0027_scenarios import build_legacy_database
from test_equipment_migration_0029_floor_state import _apply_through, _table_counts

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.shortening_baseline import ShorteningBaselineDraft
from capa_simulation.services.static_qual_schedule import BASIS_MASTER, BASIS_STATIC

MIGRATION_VERSION = 35


def _basis_column(path: Path) -> list[tuple[str, str, bool]]:
    with duckdb.connect(str(path), read_only=True) as connection:
        return [
            (str(name), str(kind), bool(nullable))
            for name, kind, nullable in connection.execute(
                """
                SELECT column_name, data_type, is_nullable = 'YES'
                FROM information_schema.columns
                WHERE table_schema = 'equipment_ops' AND table_name = 'shortening_baseline'
                  AND column_name = 'schedule_basis'
                """
            ).fetchall()
        ]


def _draft(name: str, basis: str) -> ShorteningBaselineDraft:
    return ShorteningBaselineDraft(
        name=name,
        plan_today=date(2026, 11, 20),
        start_month=202701,
        end_month=202703,
        processes=("DEMO-A",),
        cutoff_days={"DEMO-A": 10},
        units=pd.DataFrame(),
        schedule_basis=basis,
    )


def test_a_new_database_gets_the_nullable_basis_column(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    assert MIGRATION_VERSION in DuckDBEquipmentRepository(path).initialize()

    assert _basis_column(path) == [("schedule_basis", "VARCHAR", True)]


def test_old_baselines_read_as_master_and_new_ones_keep_their_basis(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    build_legacy_database(path)
    _apply_through(path, 34)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.shortening_baseline (
                baseline_id, baseline_name, saved_at, plan_today, start_month, end_month
            ) VALUES ('old-1', '옛 기준선', ?, ?, 202701, 202703)
            """,
            [datetime(2026, 11, 1, 9, 0), date(2026, 11, 1)],
        )
    before = _table_counts(path)

    repository = DuckDBEquipmentRepository(path)
    assert repository.initialize() == (MIGRATION_VERSION, 36)
    # 뒤 번호 0036(누적 진척 빈 표 둘)도 함께 걸린다 — 이 번호의 표가 아니라 셈에서 뺀다.
    later = ("shortening_progress_log", "shortening_progress_goal")
    after = _table_counts(path)
    assert {table: after[table] for table in later} == dict.fromkeys(later, 0)
    assert {table: count for table, count in after.items() if table not in later} == before

    (old,) = repository.list_shortening_baselines()
    assert old.schedule_basis == BASIS_MASTER
    repository.save_shortening_baseline(_draft("Static 기준선", BASIS_STATIC))
    repository.save_shortening_baseline(_draft("마스터 기준선", BASIS_MASTER))
    saved = {item.name: item.schedule_basis for item in repository.list_shortening_baselines()}
    assert saved == {
        "옛 기준선": BASIS_MASTER,
        "Static 기준선": BASIS_STATIC,
        "마스터 기준선": BASIS_MASTER,
    }
    static_id = next(
        item.baseline_id
        for item in repository.list_shortening_baselines()
        if item.name == "Static 기준선"
    )
    assert repository.load_shortening_baseline(static_id).summary.schedule_basis == BASIS_STATIC
    assert repository.initialize() == ()
