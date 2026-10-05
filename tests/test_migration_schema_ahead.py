# Purpose: DB 가 코드보다 새 버전이면 마이그레이션이 막지 않고 경고와 그 사실을 남기는지 검증한다.

"""예전 배포로 되돌린 상태 — DB 에 이 코드가 모르는 더 높은 버전이 적용돼 있다.

러너는 그 DB 를 막지 않는다(2026-10-05 사용자 결정). 막으면 DB 를 복원하기 전에는 되돌릴 수
없다. 대신 경고 로그를 남기고 저장소의 `schema_ahead` 로 그 사실을 화면에 넘긴다. 가짜로
더 높은 번호의 적용 기록 한 줄을 넣어 그 상태를 만든다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest

from capa_simulation.page_bootstrap import schema_ahead_message
from capa_simulation.persistence._migration_core import Migration, find_schema_ahead
from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.migration_runner import SchemaAheadOfCode, load_migrations
from capa_simulation.persistence.repository import DuckDBScenarioRepository

# 코드가 아는 최고 번호보다 이만큼 높은 가짜 적용 기록을 넣는다. 실제 다음 번호와 겹치지 않게
# 넉넉히 띄운다.
_AHEAD_BY = 90


def _migration(version: int) -> Migration:
    return Migration(version=version, name=f"{version:04d}_x.sql", sql="", checksum="")


def test_equal_or_lower_database_versions_are_not_reported() -> None:
    migrations = [_migration(1), _migration(4), _migration(5)]

    assert find_schema_ahead([1, 4, 5], migrations, database_name="시뮬레이션 DB") is None
    # 결번 2·3 처럼 파일이 사라지고 적용 기록만 남은 번호는 코드 최고 번호 아래라 알리지 않는다.
    assert find_schema_ahead([1, 2, 3, 4], migrations, database_name="시뮬레이션 DB") is None
    assert find_schema_ahead([], migrations, database_name="시뮬레이션 DB") is None


def test_a_higher_database_version_is_reported_with_both_versions() -> None:
    notice = find_schema_ahead(
        [1, 4, 5, 7], [_migration(1), _migration(4), _migration(5)], database_name="설비 DB"
    )

    assert notice == SchemaAheadOfCode(database_name="설비 DB", database_version=7, code_version=5)


def _plant_newer_version(path: Path, schema: str, version: int) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            f"INSERT INTO {schema}.schema_migration (version, name, checksum) VALUES (?, ?, ?)",
            [version, f"{version:04d}_from_a_newer_deploy.sql", "newer"],
        )


@pytest.mark.parametrize(
    ("make_repository", "schema", "code_version", "database_name"),
    [
        (
            DuckDBScenarioRepository,
            "app_meta",
            max(migration.version for migration in load_migrations()),
            "시뮬레이션 DB",
        ),
        (
            DuckDBEquipmentRepository,
            "equipment_meta",
            max(migration.version for migration in load_equipment_migrations()),
            "설비 DB",
        ),
    ],
    ids=["simulation", "equipment"],
)
def test_a_newer_database_keeps_running_and_reports_itself(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    make_repository: Callable[[Path], DuckDBScenarioRepository | DuckDBEquipmentRepository],
    schema: str,
    code_version: int,
    database_name: str,
) -> None:
    database_path = tmp_path / "rolled_back.duckdb"
    current = make_repository(database_path)
    assert current.initialize()
    assert current.schema_ahead is None
    _plant_newer_version(database_path, schema, code_version + _AHEAD_BY)

    rolled_back = make_repository(database_path)
    with caplog.at_level(logging.WARNING, logger="capa_simulation.persistence._migration_core"):
        # 막지 않는다 — 예외 없이 지나가고 새로 적용할 것이 없다.
        assert rolled_back.initialize() == ()

    expected = SchemaAheadOfCode(
        database_name=database_name,
        database_version=code_version + _AHEAD_BY,
        code_version=code_version,
    )
    assert rolled_back.schema_ahead == expected
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    logged = warnings[0].getMessage()
    assert database_name in logged
    assert f"DB {code_version + _AHEAD_BY} · 코드 {code_version}" in logged


def test_the_screen_message_names_the_database_and_both_versions() -> None:
    message = schema_ahead_message(
        SchemaAheadOfCode(database_name="설비 DB", database_version=13, code_version=11)
    )

    assert message.startswith("설비 DB 가 이 코드보다 새 버전입니다(DB 13 · 코드 11).")
    assert "예전 배포로 되돌린 상태일 수 있습니다" in message
