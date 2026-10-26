# Purpose: Space 동·층 사용 상태 프로필(설비 DB 0029)의 머리·층 행을 읽고 바뀐 층만 갈아 쓰는 SQL.

"""Space 동·층 사용 상태의 SQL.

연결은 부르는 쪽(`DuckDBEquipmentRepository`)이 열고 쓰기는 그 쓰기 트랜잭션 안에서만 부른다
(`shortening_baseline_store.py`·`equipment_scenario_store.py` 와 같은 꼴). 모델과 값 규칙은
`services/floor_state.py` 다.

쓰기는 **바뀐 층만** 고친다 — 다시 켠 층은 DELETE, 사유만 바꾼 층은 키 아닌 칸 UPDATE, 새로 끈 층은
INSERT 다. 층마다 셋 가운데 하나만 내므로 한 트랜잭션에서 같은 키(동, 층)를 지웠다 다시 넣지 않는다
(0029 의 PK). 다른 층 행의 `updated_at` 은 그대로다.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name
from capa_simulation.services.fab_layout import FLOOR_KEYS
from capa_simulation.services.floor_state import FloorStates

__all__ = ["read_floor_states", "write_floor_states"]

_FLOOR_ORDER = {key: index for index, key in enumerate(FLOOR_KEYS)}


def read_floor_states(connection: duckdb.DuckDBPyConnection) -> FloorStates:
    """머리와 비활성 층 행. 머리가 없으면 version 0 이다 — 머리 없이 층 행만 있는 DB(손으로 넣은
    행)도 version 0 으로 읽고 행은 그대로 싣는다. FAB 의 30개 층 밖 행은 버린다(그릴 자리가 없다).
    사유는 저장된 글 그대로다(옛 코드든 적은 글이든 — 화면 글은 `inactive_label`)."""
    header = connection.execute(
        """
        SELECT version, source, updated_at
        FROM equipment_ops.floor_state_profile
        WHERE profile_id = 1
        """
    ).fetchone()
    rows = connection.execute(
        "SELECT building, floor_name, reason FROM equipment_ops.floor_state"
    ).fetchall()
    known = sorted(
        (
            (str(building), str(floor), str(reason))
            for building, floor, reason in rows
            if (str(building), str(floor)) in _FLOOR_ORDER
        ),
        key=lambda row: _FLOOR_ORDER[(row[0], row[1])],
    )
    if header is None:
        return FloorStates(rows=tuple(known))
    return FloorStates(
        rows=tuple(known),
        version=int(header[0]),
        source=str(header[1]),
        updated_at=header[2],
    )


def write_floor_states(
    connection: duckdb.DuckDBPyConnection,
    current: FloorStates,
    rows: tuple[tuple[str, str, str], ...],
    *,
    source: str,
) -> None:
    """`current`(같은 트랜잭션에서 읽은 저장본)와 견줘 바뀐 층만 고치고 머리를 다음 version 으로
    쓴다. `rows` 는 `services/floor_state.prepare_floor_states` 를 지난 값이다."""
    before = current.inactive
    after = {(building, floor): reason for building, floor, reason in rows}
    for key in [key for key in before if key not in after]:
        connection.execute(
            "DELETE FROM equipment_ops.floor_state WHERE building = ? AND floor_name = ?",
            [key[0], key[1]],
        )
    for key, reason in after.items():
        if key in before and before[key] != reason:
            connection.execute(
                """
                UPDATE equipment_ops.floor_state
                SET reason = ?, updated_at = current_timestamp
                WHERE building = ? AND floor_name = ?
                """,
                [reason, key[0], key[1]],
            )
    added = [(key, reason) for key, reason in after.items() if key not in before]
    if added:
        insert_by_name(
            connection,
            schema="equipment_ops",
            table_name="floor_state",
            frame=pd.DataFrame(
                {
                    "building": [key[0] for key, _ in added],
                    "floor_name": [key[1] for key, _ in added],
                    "reason": [reason for _, reason in added],
                }
            ),
        )
    _write_header(connection, current, source)


def _write_header(connection: duckdb.DuckDBPyConnection, current: FloorStates, source: str) -> None:
    """머리 한 행을 다음 version 으로. 행이 없으면(version 0) 넣고, 있으면 키 아닌 칸만 고친다
    (`_write_shortening_filter_header` 와 같은 꼴)."""
    if current.version == 0:
        connection.execute(
            """
            INSERT INTO equipment_ops.floor_state_profile (profile_id, version, source)
            VALUES (1, 1, ?)
            """,
            [source],
        )
        return
    connection.execute(
        """
        UPDATE equipment_ops.floor_state_profile
        SET version = ?, source = ?, updated_at = current_timestamp
        WHERE profile_id = 1
        """,
        [current.version + 1, source],
    )
