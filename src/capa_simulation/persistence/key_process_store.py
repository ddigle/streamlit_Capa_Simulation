# Purpose: 시나리오와 분리된 공용 주요공정 목록의 조회·삽입 SQL을 담당한다.

"""시나리오와 분리된 공용 주요공정 목록의 조회·삽입 SQL."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import quote


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
    connection.execute(
        """
        INSERT INTO app_meta.global_key_process (profile_id, version, source)
        VALUES (1, ?, ?)
        """,
        [version, source],
    )
    if not processes:
        return
    payload = pd.DataFrame(
        {
            "profile_id": 1,
            "공정": list(processes),
            "표시순서": range(len(processes)),
        }
    )
    view_name = f"_incoming_global_key_process_{uuid4().hex}"
    connection.register(view_name, payload)
    try:
        connection.execute(
            f"INSERT INTO app_meta.global_key_process_item BY NAME SELECT * FROM {quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
