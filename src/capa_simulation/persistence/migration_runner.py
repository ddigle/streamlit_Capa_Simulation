# Purpose: Apply immutable SQL migrations to a DuckDB database file.

"""시뮬레이션 DuckDB 의 마이그레이션 진입점.

적용 절차 자체는 `_migration_core` 한 벌이다. 여기는 그 절차에 이 DB 의 패키지·스키마를
묶어 주는 얇은 겉면이다.
"""

from __future__ import annotations

import duckdb

from capa_simulation.persistence._migration_core import (
    Migration,
    apply_migrations_to,
    load_migrations_from,
)

MIGRATION_PACKAGE = "capa_simulation.persistence.migrations"
_SCHEMA = "app_meta"
_LABEL = "DuckDB"

__all__ = ["MIGRATION_PACKAGE", "Migration", "apply_migrations", "load_migrations"]


def load_migrations() -> tuple[Migration, ...]:
    return load_migrations_from(MIGRATION_PACKAGE, label=_LABEL)


def apply_migrations(connection: duckdb.DuckDBPyConnection) -> tuple[int, ...]:
    """Apply every pending migration and reject edited applied migrations."""
    return apply_migrations_to(
        connection,
        package=MIGRATION_PACKAGE,
        schema=_SCHEMA,
        label=_LABEL,
    )
