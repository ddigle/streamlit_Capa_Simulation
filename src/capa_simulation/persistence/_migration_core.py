# Purpose: 두 DuckDB 의 마이그레이션을 체크섬 대조·트랜잭션으로 적용하고 DB 가 앞선 것을 알린다.

"""SQL 마이그레이션 적용 엔진.

시뮬레이션 DB 와 가용설비 DB 는 **물리적으로 분리된 두 파일**이지만 적용 절차는 같다:
버전 순으로 읽고, 이미 적용된 파일의 체크섬이 달라졌으면 거부하고, 남은 것만 한 건씩
트랜잭션으로 넣는다. 그 절차가 두 벌로 갈려 있으면 한쪽만 고쳐도 아무 데서도 드러나지
않는다 — 체크섬 대조는 잘못 고쳐도 조용히 통과하는 종류의 코드다.

패키지 이름과 스키마만 바깥에서 받고, 나머지는 여기 한 벌이다.

**DB 가 코드보다 새 것이면 막지 않고 알린다**(2026-10-05 사용자 결정). 예전 배포 ZIP 으로
되돌리면 DB 에는 그 코드가 모르는 더 높은 버전이 적용돼 있다. 여기서 멈추면 DB 를 복원하기
전에는 되돌릴 수 없으므로 그대로 진행하고, 경고 로그를 남기며 그 사실(`SchemaAheadOfCode`)을
호출자에게 돌려준다. 화면 경고는 UI 계층이 그린다 — 이 모듈은 Streamlit 을 모른다.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files

import duckdb

from capa_simulation.persistence._sql_helpers import transaction

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


@dataclass(frozen=True)
class SchemaAheadOfCode:
    """DB 에 적용된 최고 버전이 이 코드가 아는 최고 버전보다 높다는 사실.

    `database_name` 은 화면·로그에 그대로 쓰는 DB 이름(「시뮬레이션 DB」·「설비 DB」)이다.
    """

    database_name: str
    database_version: int
    code_version: int


def find_schema_ahead(
    applied_versions: Iterable[int],
    migrations: Iterable[Migration],
    *,
    database_name: str,
) -> SchemaAheadOfCode | None:
    """적용 기록과 코드의 마이그레이션 목록을 견줘, DB 가 더 새 것이면 그 사실을 돌려준다.

    **최고 버전끼리만** 견준다. 코드에 없는 번호라도 코드의 최고 번호 아래면 알리지 않는다 —
    시뮬레이션 DB 의 결번 2·3 처럼 파일만 사라지고 적용 기록이 남은 번호가 있어서다.
    """
    code_version = max((migration.version for migration in migrations), default=0)
    database_version = max(applied_versions, default=0)
    if database_version <= code_version:
        return None
    return SchemaAheadOfCode(
        database_name=database_name,
        database_version=database_version,
        code_version=code_version,
    )


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


@dataclass(frozen=True)
class MigrationOutcome:
    """한 번의 적용 결과. 새로 적용한 버전과, DB 가 코드보다 새 것이면 그 사실."""

    applied: tuple[int, ...]
    schema_ahead: SchemaAheadOfCode | None


def apply_migrations_to(
    connection: duckdb.DuckDBPyConnection,
    *,
    package: str,
    schema: str,
    label: str,
    database_name: str,
) -> MigrationOutcome:
    """대기 중인 마이그레이션을 적용하고, 이미 적용된 파일의 변경을 거부한다.

    체크섬이 달라졌다는 것은 적용이 끝난 SQL 을 누가 고쳤다는 뜻이다. 그대로 다시 돌리면
    이미 그 SQL 로 만들어진 DB 와 어긋나므로 여기서 멈춘다. 반대로 DB 가 코드보다 새 것인
    것은 멈추지 않는다 — 경고 로그를 남기고 결과에 실어 돌려준다(모듈 설명).
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
    migrations = load_migrations_from(package, label=label)
    schema_ahead = find_schema_ahead(applied, migrations, database_name=database_name)
    if schema_ahead is not None:
        _LOGGER.warning(
            "%s 가 이 코드보다 새 버전입니다(DB %d · 코드 %d). 예전 배포로 되돌린 상태일 수 "
            "있습니다. 막지 않고 계속합니다.",
            schema_ahead.database_name,
            schema_ahead.database_version,
            schema_ahead.code_version,
        )
    newly_applied: list[int] = []

    for migration in migrations:
        existing_checksum = applied.get(migration.version)
        if existing_checksum is not None:
            if existing_checksum != migration.checksum:
                raise RuntimeError(
                    f"이미 적용된 {label} 마이그레이션이 변경되었습니다: {migration.name}"
                )
            continue

        with transaction(connection):
            connection.execute(migration.sql)
            connection.execute(
                f"""
                INSERT INTO {schema}.schema_migration (version, name, checksum)
                VALUES (?, ?, ?)
                """,
                [migration.version, migration.name, migration.checksum],
            )
        newly_applied.append(migration.version)

    return MigrationOutcome(applied=tuple(newly_applied), schema_ahead=schema_ahead)
