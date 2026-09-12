# Purpose: Apply immutable SQL migrations to the standalone equipment DuckDB file.

"""가용설비 DuckDB 의 마이그레이션 진입점.

시뮬레이션 DB 와 파일이 분리돼 있을 뿐 적용 절차는 같다. 그 절차는 `_migration_core` 에
한 벌로 있고, 여기는 이 DB 의 패키지·스키마를 묶어 주는 얇은 겉면이다.
"""

from __future__ import annotations

import duckdb

from capa_simulation.persistence._migration_core import (
    Migration as EquipmentMigration,
)
from capa_simulation.persistence._migration_core import (
    apply_migrations_to,
    load_migrations_from,
)

EQUIPMENT_MIGRATION_PACKAGE = "capa_simulation.persistence.equipment_migrations"
_SCHEMA = "equipment_meta"
_LABEL = "설비 DB"

__all__ = [
    "EQUIPMENT_MIGRATION_PACKAGE",
    "EquipmentMigration",
    "apply_equipment_migrations",
    "load_equipment_migrations",
]


def load_equipment_migrations() -> tuple[EquipmentMigration, ...]:
    return load_migrations_from(EQUIPMENT_MIGRATION_PACKAGE, label=_LABEL)


def apply_equipment_migrations(connection: duckdb.DuckDBPyConnection) -> tuple[int, ...]:
    """Apply every pending equipment migration and reject edited applied files."""
    return apply_migrations_to(
        connection,
        package=EQUIPMENT_MIGRATION_PACKAGE,
        schema=_SCHEMA,
        label=_LABEL,
    )
