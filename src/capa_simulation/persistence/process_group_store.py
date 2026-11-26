# Purpose: 공용 공정 그룹 프로필(0041)의 조회 · 교체 SQL 이다.

"""공용 공정 그룹 프로필(0041)의 조회 · 교체 SQL.

머리는 `global_process_group`(`profile_id = 1` 한 행 — version · 출처 · 갱신시각), 행은
`global_process_group_item`(열쇠 `(profile_id, "공정")` — 한 공정은 한 그룹에만 든다)이다. 검증은
저장소 앞에서 `services.process_group.normalize_process_groups` 가 끝내고 여기는 받은 대응을 그대로
쓴다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import (
    insert_by_name,
    insert_profile_header,
    load_profile_header,
    require_profile_version,
    reset_profile,
)
from capa_simulation.persistence.models import GlobalProcessGroup
from capa_simulation.services.process_group import PROCESS_GROUP_COLUMNS, PROCESS_GROUP_LABEL

# 이 표를 만든 시뮬레이션 마이그레이션 번호와 두 표 이름(스키마 `app_meta`).
PROCESS_GROUP_MIGRATION: Final = 41
PROCESS_GROUP_HEADER_TABLE: Final = "global_process_group"
PROCESS_GROUP_ITEM_TABLE: Final = "global_process_group_item"


def load_global_process_group_assignments(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[tuple[str, str], ...]:
    """저장된 (원본 공정, 공정 그룹) — 공정 글자순."""
    process_column, group_column = PROCESS_GROUP_COLUMNS
    rows = connection.execute(
        f"""
        SELECT "{process_column}", "{group_column}"
        FROM app_meta.{PROCESS_GROUP_ITEM_TABLE}
        WHERE profile_id = 1
        ORDER BY "{process_column}"
        """
    ).fetchall()
    return tuple((str(process), str(group)) for process, group in rows)


def load_global_process_group(connection: duckdb.DuckDBPyConnection) -> GlobalProcessGroup:
    """열린 연결에서 공용 프로필을 읽는다. 머리가 없으면 미저장 기본값(version 0 · 빈 대응)이다."""
    metadata = load_profile_header(connection, PROCESS_GROUP_HEADER_TABLE)
    if metadata is None:
        return GlobalProcessGroup(version=0, source="", updated_at=None, assignments=())
    return GlobalProcessGroup(
        version=metadata[0],
        source=metadata[1],
        updated_at=metadata[2],
        assignments=load_global_process_group_assignments(connection),
    )


def replace_global_process_group(
    connection: duckdb.DuckDBPyConnection,
    assignments: Sequence[tuple[str, str]],
    *,
    source: str,
    expected_version: int | None = None,
) -> None:
    """검증된 대응 전체를 교체한다. 호출자가 잠금과 트랜잭션을 소유한다.

    `assignments` 는 `normalize_process_groups` 를 거친 값이다. `expected_version`(편집을 시작할 때
    본 version)이 지금 저장본과 다르면 아무것도 쓰지 않고 `ProfileVersionConflict` 를 올린다. None
    이면 대조하지 않는다. 대응 0행 저장도 머리를 써 version 이 오른다.
    """
    require_profile_version(
        connection, PROCESS_GROUP_HEADER_TABLE, expected_version, label=PROCESS_GROUP_LABEL
    )
    version = reset_profile(connection, PROCESS_GROUP_HEADER_TABLE, PROCESS_GROUP_ITEM_TABLE)
    insert_profile_header(connection, PROCESS_GROUP_HEADER_TABLE, version=version, source=source)
    if not assignments:
        return
    process_column, group_column = PROCESS_GROUP_COLUMNS
    insert_by_name(
        connection,
        schema="app_meta",
        table_name=PROCESS_GROUP_ITEM_TABLE,
        frame=pd.DataFrame(
            {
                "profile_id": [1] * len(assignments),
                process_column: [process for process, _ in assignments],
                group_column: [group for _, group in assignments],
            }
        ),
    )
