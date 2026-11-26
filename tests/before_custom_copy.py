# Purpose: 시뮬레이션 DB 를 0039 전 · 0040 전 사본(칸 · 뒤 번호 표와 그 기록을 걷음)과 부하 예외
# 선언을 저장한 사본으로 베끼는 시험 도우미다.

"""0039 전 DB 사본 — 확인 스크립트가 마이그레이션 없이 읽는 옛 사본 꼴.

`0039` 는 리비전 표 여덟과 그 데이터셋 짝 표 여덟의 끝에 `CUSTOM` 칸을 붙이고 옛 행을 모두 빈 값
표지로 두었다. 저장소로 만든 DB 를 베낀 뒤 그 열여섯 칸을 걷고 마이그레이션 기록에서 `0039` 와 그
뒤 번호를 지운다. 원천(`raw_data.core_data`)의 `CUSTOM` 은 원천 78컬럼이라 그대로 둔다. `0040` 이
만든 부하 예외 선언 판 이력 표(`app_meta.route_load_exception_version`)와 `0041` 이 만든 공정 그룹
두 표(`app_meta.global_process_group` · `_item`)도 걷는다 — 0038 사본에는 그 표들이 없다.

걷는 것은 `0039` 와 그 뒤 번호가 만든 물체뿐이다. 코드에 뒤 마이그레이션이 더 생기면 그 번호가
만든 물체(표 · 칸)도 걷어야 실제 0038 사본과 같은 꼴이 된다 — 그대로 두면 뒤 번호의 물체를 가진 채
최고 번호만 38 인 사본이 되어, 「그 표가 없으면」 갈래를 시험이 타지 않는다. 그래서 걷는 번호를
`KNOWN_LATER_MIGRATIONS` 에 적고, 코드의 0039 뒤 번호와 다르면
`tests/test_before_custom_copy.py` 가 먼저 깨진다 — 번호를 더할 때 이 도우미가 그 물체를 걷게
넓힌다.

걷기 전 칸의 값은 모두 표지여야 하고 부하 예외 선언은 비어 있어야 한다(판이 없거나 마지막 판이
비움) — 그래야 0039 를 다시 건 뜻(모든 행 표지)과 선언 없는 계산이 걷기 전 DB 와 같아, 「0039 전
사본의 출력 = 걷기 전 DB 의 출력」 을 견줄 수 있다.

`database_before_route_exceptions` 는 0039 뒤 · 0040 전 사본 — CUSTOM 칸은 두고 `0040` 의 선언 표 ·
`0041` 의 공정 그룹 표와 그 기록만 걷는다. 확인 스크립트는 그 사본을 빈 선언으로
센다(`사본 0040 전`).
`database_with_route_exceptions` 는 거꾸로 선언 판 하나를 저장한 사본이다 — 확인 스크립트가 그 판을
읽어 넘기는지 본다. 선언은 내장 합성 시드의 WF Core 경로 공정 하나(`seed_route_declaration`)다.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import duckdb

from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.persistence.process_group_store import (
    PROCESS_GROUP_HEADER_TABLE,
    PROCESS_GROUP_ITEM_TABLE,
    PROCESS_GROUP_MIGRATION,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.persistence.route_load_exception_store import (
    ROUTE_LOAD_EXCEPTION_MIGRATION,
    ROUTE_LOAD_EXCEPTION_SCHEMA,
    ROUTE_LOAD_EXCEPTION_TABLE,
)
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.revision_compatibility import (
    CUSTOM_COLUMN,
    CUSTOM_MIGRATION,
    custom_keyed_tables,
)
from capa_simulation.services.route_load_exceptions import BUFFER_X_CORE_CHIP

# 이 도우미가 물체를 걷는 0039 와 그 뒤 마이그레이션 번호 — 코드의 0039 뒤 번호와 같아야 한다.
KNOWN_LATER_MIGRATIONS: Final = (
    CUSTOM_MIGRATION,
    ROUTE_LOAD_EXCEPTION_MIGRATION,
    PROCESS_GROUP_MIGRATION,
)


def database_before_custom(source: Path, target: Path) -> Path:
    """`source` 를 `target` 으로 베끼고 0039 전 사본으로 되감는다. `source` 는 건드리지 않는다."""
    shutil.copyfile(source, target)
    with duckdb.connect(str(target)) as connection:
        placed = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.columns "
            "WHERE column_name = ? AND table_schema IN ('rev_data', 'ref_data') ORDER BY 1, 2",
            [CUSTOM_COLUMN],
        ).fetchall()
        assert len(placed) == 2 * len(custom_keyed_tables()), placed
        for schema, table in placed:
            values = {
                row[0]
                for row in connection.execute(
                    f'SELECT DISTINCT "{CUSTOM_COLUMN}" FROM {schema}.{table}'
                ).fetchall()
            }
            assert values <= {CUSTOM_BLANK}, (schema, table, values)
            connection.execute(f'ALTER TABLE {schema}.{table} DROP COLUMN "{CUSTOM_COLUMN}"')
        _drop_route_exception_table(connection)
        _drop_process_group_tables(connection)
        connection.execute(
            "DELETE FROM app_meta.schema_migration WHERE version >= ?", [CUSTOM_MIGRATION]
        )
    return target


def _drop_route_exception_table(connection: duckdb.DuckDBPyConnection) -> None:
    """선언 표를 걷는다 — 걷기 전 선언은 비어 있어야 한다(판이 없거나 마지막 판이 비움)."""
    declaration = connection.execute(
        f"SELECT digest FROM {ROUTE_LOAD_EXCEPTION_SCHEMA}.{ROUTE_LOAD_EXCEPTION_TABLE} "
        "ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    assert declaration is None or declaration[0] == "", declaration
    connection.execute(f"DROP TABLE {ROUTE_LOAD_EXCEPTION_SCHEMA}.{ROUTE_LOAD_EXCEPTION_TABLE}")


def _drop_process_group_tables(connection: duckdb.DuckDBPyConnection) -> None:
    """`0041` 의 공정 그룹 두 표를 걷는다 — 계산 밖 보기 보조라 걷기 전 값은 묻지 않는다."""
    for table in (PROCESS_GROUP_ITEM_TABLE, PROCESS_GROUP_HEADER_TABLE):
        connection.execute(f"DROP TABLE app_meta.{table}")


def database_before_route_exceptions(source: Path, target: Path) -> Path:
    """`source` 를 `target` 으로 베끼고 0039 뒤 · 0040 전 사본으로 되감는다 — 선언 표 · 공정 그룹
    표와 `0040` 및 그 뒤 기록만 걷는다. `source` 는 건드리지 않는다."""
    shutil.copyfile(source, target)
    with duckdb.connect(str(target)) as connection:
        _drop_route_exception_table(connection)
        _drop_process_group_tables(connection)
        connection.execute(
            "DELETE FROM app_meta.schema_migration WHERE version >= ?",
            [ROUTE_LOAD_EXCEPTION_MIGRATION],
        )
    return target


def database_marked_after_custom(source: Path, target: Path) -> Path:
    """0039 전 사본에 0039 와 그 뒤 기록만 다시 적은 사본 — 「0039 뒤로 적혔는데 칸이 없는」 꼴.

    확인 스크립트는 채우기 · 손 SQL 조건을 마이그레이션 번호로만 가른다. 이 사본은 채우지 않고 칸
    없음으로 멈춰야 한다(칸이 없어진 0039 뒤 DB 를 조용히 표지로 덮지 않는다).
    """
    database_before_custom(source, target)
    with duckdb.connect(str(target)) as connection:
        for migration in load_migrations():
            if migration.version >= CUSTOM_MIGRATION:
                connection.execute(
                    "INSERT INTO app_meta.schema_migration (version, name, checksum) "
                    "VALUES (?, ?, ?)",
                    [migration.version, migration.name, migration.checksum],
                )
    return target


def seed_route_declaration() -> dict[str, str]:
    """내장 합성 시드의 소요기준 WF · `WF 구분` Core 경로를 가진 첫 공정 하나의 선언 — 시드에는
    Buffer 경로가 없어 그 Core 줄이 「부하 예외 바탕 없음」 으로 빠진다(선언이 결과를 바꾼다)."""
    reqb = build_builtin_seed_dataset().reference_tables["RQ_REQB"]
    wafer = reqb["소요기준"].astype("string").str.strip().str.upper().eq("WF")
    core = reqb["WF 구분"].astype("string").str.strip().str.casefold().eq("core")
    processes = sorted(set(reqb.loc[wafer & core, "공정"].astype(str)))
    assert processes, "시드에 WF Core 경로가 없다 — 견본이 바뀌었다"
    return {processes[0]: BUFFER_X_CORE_CHIP}


def database_with_route_exceptions(
    source: Path, target: Path, declaration: Mapping[str, str]
) -> Path:
    """`source` 를 `target` 으로 베끼고 부하 예외 선언 판 하나를 저장한다(첫 판). `source` 는
    건드리지 않는다."""
    shutil.copyfile(source, target)
    DuckDBScenarioRepository(target).append_route_load_exceptions(
        expected_seq=0, entries=declaration, applied_by=None, source_place="test"
    )
    return target
