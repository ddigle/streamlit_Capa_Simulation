"""Apply immutable SQL migrations to the standalone equipment DuckDB file."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files

import duckdb

EQUIPMENT_MIGRATION_PACKAGE = "capa_simulation.persistence.equipment_migrations"


@dataclass(frozen=True)
class EquipmentMigration:
    version: int
    name: str
    sql: str
    checksum: str


def load_equipment_migrations() -> tuple[EquipmentMigration, ...]:
    migrations: list[EquipmentMigration] = []
    for resource in files(EQUIPMENT_MIGRATION_PACKAGE).iterdir():
        if not resource.name.endswith(".sql"):
            continue
        prefix, separator, _ = resource.name.partition("_")
        if not separator or not prefix.isdigit():
            raise ValueError(f"설비 DB 마이그레이션 파일명 형식이 잘못되었습니다: {resource.name}")
        sql = resource.read_text(encoding="utf-8")
        migrations.append(
            EquipmentMigration(
                version=int(prefix),
                name=resource.name,
                sql=sql,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError("설비 DB 마이그레이션 버전이 중복되었습니다.")
    return tuple(sorted(migrations, key=lambda migration: migration.version))


def apply_equipment_migrations(connection: duckdb.DuckDBPyConnection) -> tuple[int, ...]:
    """Apply every pending equipment migration and reject edited applied files."""
    connection.execute("CREATE SCHEMA IF NOT EXISTS equipment_meta")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment_meta.schema_migration (
            version INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            checksum VARCHAR NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    applied_rows = connection.execute(
        "SELECT version, checksum FROM equipment_meta.schema_migration ORDER BY version"
    ).fetchall()
    applied = {int(version): str(checksum) for version, checksum in applied_rows}
    newly_applied: list[int] = []

    for migration in load_equipment_migrations():
        existing_checksum = applied.get(migration.version)
        if existing_checksum is not None:
            if existing_checksum != migration.checksum:
                raise RuntimeError(
                    f"이미 적용된 설비 DuckDB 마이그레이션이 변경되었습니다: {migration.name}"
                )
            continue

        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute(migration.sql)
            connection.execute(
                """
                INSERT INTO equipment_meta.schema_migration (version, name, checksum)
                VALUES (?, ?, ?)
                """,
                [migration.version, migration.name, migration.checksum],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        newly_applied.append(migration.version)

    return tuple(newly_applied)
