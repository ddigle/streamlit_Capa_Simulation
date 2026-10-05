# Purpose: Apply immutable SQL migrations to a DuckDB database file.

"""시뮬레이션 DuckDB 의 마이그레이션 진입점.

적용 절차 자체는 `_migration_core` 한 벌이다. 여기는 그 절차에 이 DB 의 패키지·스키마를
묶어 주는 얇은 겉면이다.
"""

from __future__ import annotations

import duckdb

from capa_simulation.persistence._migration_core import (
    Migration,
    MigrationOutcome,
    SchemaAheadOfCode,
    apply_migrations_to,
    load_migrations_from,
)

MIGRATION_PACKAGE = "capa_simulation.persistence.migrations"
_SCHEMA = "app_meta"
_LABEL = "DuckDB"
_DATABASE_NAME = "시뮬레이션 DB"

__all__ = [
    "MIGRATION_PACKAGE",
    "Migration",
    "MigrationOutcome",
    "SchemaAheadOfCode",
    "apply_migrations",
    "load_migrations",
]


def load_migrations() -> tuple[Migration, ...]:
    return load_migrations_from(MIGRATION_PACKAGE, label=_LABEL)


def apply_migrations(connection: duckdb.DuckDBPyConnection) -> MigrationOutcome:
    """대기 중인 마이그레이션을 적용하고, 적용된 파일의 변경을 거부한다.

    DB 가 이 코드보다 새 것이면 막지 않고 결과의 `schema_ahead` 에 싣는다.
    """
    return apply_migrations_to(
        connection,
        package=MIGRATION_PACKAGE,
        schema=_SCHEMA,
        label=_LABEL,
        database_name=_DATABASE_NAME,
    )
