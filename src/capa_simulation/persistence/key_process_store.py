# Purpose: 시나리오와 분리된 공용 주요공정 목록의 조회·교체 SQL을 담당한다.

"""시나리오와 분리된 공용 주요공정 목록의 조회·교체 SQL."""

from __future__ import annotations

from collections.abc import Sequence

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import (
    insert_by_name,
    insert_profile_header,
    load_profile_header,
    reset_profile,
)
from capa_simulation.persistence.models import GlobalKeyProcess
from capa_simulation.services.key_process import normalize_key_processes


def load_global_key_process_rows(connection: duckdb.DuckDBPyConnection) -> list[str]:
    """저장된 차례 그대로 공정명을 돌려준다. 그 차례가 곧 히트맵 행 순서다."""
    rows = connection.execute(
        """
        SELECT "공정"
        FROM app_meta.global_key_process_item
        WHERE profile_id = 1
        ORDER BY "표시순서", "공정"
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def insert_global_key_process(
    connection: duckdb.DuckDBPyConnection,
    processes: Sequence[str],
    *,
    version: int,
    source: str,
) -> None:
    """헤더 한 행과 공정 N행을 넣는다. 공정이 0건이어도 헤더는 기록한다.

    캐시 키가 version 을 보므로 '전체 해제' 도 버전이 올라야 무효화된다.
    """
    insert_profile_header(connection, "global_key_process", version=version, source=source)
    if not processes:
        return
    payload = pd.DataFrame(
        {
            "profile_id": 1,
            "공정": list(processes),
            "표시순서": range(len(processes)),
        }
    )
    insert_by_name(
        connection,
        schema="app_meta",
        table_name="global_key_process_item",
        frame=payload,
    )


def load_global_key_process(connection: duckdb.DuckDBPyConnection) -> GlobalKeyProcess:
    """열린 연결에서 공용 프로필과 미저장 기본값을 복원한다."""
    metadata = load_profile_header(connection, "global_key_process")
    if metadata is None:
        return GlobalKeyProcess(version=0, source="", updated_at=None, processes=())
    processes = load_global_key_process_rows(connection)
    return GlobalKeyProcess(
        version=metadata[0],
        source=metadata[1],
        updated_at=metadata[2],
        processes=normalize_key_processes(processes),
    )


def replace_global_key_process(
    connection: duckdb.DuckDBPyConnection, normalized: Sequence[str], *, source: str
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(connection, "global_key_process", "global_key_process_item")
    insert_global_key_process(connection, normalized, version=version, source=source)
