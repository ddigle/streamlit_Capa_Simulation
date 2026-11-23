# Purpose: 시뮬레이션 DB 를 CUSTOM 칸과 0039 기록을 걷은 0039 전 사본으로 베끼는 시험 도우미다.

"""0039 전 DB 사본 — 확인 스크립트가 마이그레이션 없이 읽는 옛 사본 꼴.

`0039` 는 리비전 표 여덟과 그 데이터셋 짝 표 여덟의 끝에 `CUSTOM` 칸을 붙이고 옛 행을 모두 빈 값
표지로 두었다. 저장소로 만든 DB 를 베낀 뒤 그 열여섯 칸을 걷고 마이그레이션 기록에서 `0039` 와 그
뒤 번호를 지운다. 원천(`raw_data.core_data`)의 `CUSTOM` 은 원천 78컬럼이라 그대로 둔다.

걷는 것은 `0039` 가 만든 칸뿐이다. 코드에 `0039` 뒤 마이그레이션이 생기면 그 번호가 만든
물체(표 · 칸)도 걷어야 실제 0038 사본과 같은 꼴이 된다 — 그대로 두면 뒤 번호의 물체를 가진 채
최고 번호만 38 인 사본이 되어, 「그 표가 없으면」 갈래를 시험이 타지 않는다. 그래서 걷는 번호를
`KNOWN_LATER_MIGRATIONS` 에 적고, 코드의 0039 뒤 번호와 다르면
`tests/test_before_custom_copy.py` 가 먼저 깨진다 — 번호를 더할 때 이 도우미가 그 물체를 걷게
넓힌다.

걷기 전 칸의 값은 모두 표지여야 한다 — 그래야 0039 를 다시 건 뜻(모든 행 표지)과 걷기 전 DB 가
같아, 「0039 전 사본의 출력 = 걷기 전 DB 의 출력」 을 견줄 수 있다.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

import duckdb

from capa_simulation.persistence.migration_runner import load_migrations
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.revision_compatibility import (
    CUSTOM_COLUMN,
    CUSTOM_MIGRATION,
    custom_keyed_tables,
)

# 이 도우미가 물체를 걷는 0039 와 그 뒤 마이그레이션 번호 — 코드의 0039 뒤 번호와 같아야 한다.
KNOWN_LATER_MIGRATIONS: Final = (CUSTOM_MIGRATION,)


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
        connection.execute(
            "DELETE FROM app_meta.schema_migration WHERE version >= ?", [CUSTOM_MIGRATION]
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
