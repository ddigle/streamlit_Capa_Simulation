# Purpose: 두 DuckDB 의 SQL 마이그레이션을 체크섬 대조와 트랜잭션으로 적용하는 공용 엔진.

"""SQL 마이그레이션 적용 엔진.

시뮬레이션 DB 와 가용설비 DB 는 **물리적으로 분리된 두 파일**이지만 적용 절차는 같다:
버전 순으로 읽고, 이미 적용된 파일의 체크섬이 달라졌으면 거부하고, 남은 것만 한 건씩
트랜잭션으로 넣는다. 그 절차가 두 벌로 갈려 있으면 한쪽만 고쳐도 아무 데서도 드러나지
않는다 — 체크섬 대조는 잘못 고쳐도 조용히 통과하는 종류의 코드다.

패키지 이름과 스키마만 바깥에서 받고, 나머지는 여기 한 벌이다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files

import duckdb


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def load_migrations_from(package: str, *, label: str) -> tuple[Migration, ...]:
    """`<버전>_<이름>.sql` 파일을 버전 순으로 읽는다.

    `label` 은 오류 문구에만 쓴다. 두 DB 를 한 화면에서 다루므로 어느 쪽이 잘못됐는지
    메시지가 말해야 한다.
    """
    migrations: list[Migration] = []
    for resource in files(package).iterdir():
        if not resource.name.endswith(".sql"):
            continue
        prefix, separator, _ = resource.name.partition("_")
        if not separator or not prefix.isdigit():
            raise ValueError(f"{label} 마이그레이션 파일명 형식이 잘못되었습니다: {resource.name}")
        sql = resource.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=int(prefix),
                name=resource.name,
                sql=sql,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError(f"{label} 마이그레이션 버전이 중복되었습니다.")
    return tuple(sorted(migrations, key=lambda migration: migration.version))


def apply_migrations_to(
    connection: duckdb.DuckDBPyConnection,
    *,
    package: str,
    schema: str,
    label: str,
) -> tuple[int, ...]:
    """대기 중인 마이그레이션을 적용하고, 이미 적용된 파일의 변경을 거부한다.

    체크섬이 달라졌다는 것은 적용이 끝난 SQL 을 누가 고쳤다는 뜻이다. 그대로 다시 돌리면
    이미 그 SQL 로 만들어진 DB 와 어긋나므로 여기서 멈춘다.
    """
    connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.schema_migration (
            version INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            checksum VARCHAR NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    applied_rows = connection.execute(
        f"SELECT version, checksum FROM {schema}.schema_migration ORDER BY version"
    ).fetchall()
    applied = {int(version): str(checksum) for version, checksum in applied_rows}
    newly_applied: list[int] = []

    for migration in load_migrations_from(package, label=label):
        existing_checksum = applied.get(migration.version)
        if existing_checksum is not None:
            if existing_checksum != migration.checksum:
                raise RuntimeError(
                    f"이미 적용된 {label} 마이그레이션이 변경되었습니다: {migration.name}"
                )
            continue

        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute(migration.sql)
            connection.execute(
                f"""
                INSERT INTO {schema}.schema_migration (version, name, checksum)
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
