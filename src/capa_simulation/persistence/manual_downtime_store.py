# Purpose: 입력 비가동 대수(설비 0032)의 머리·칸·이력을 읽고 바뀐 칸만 갈아 쓰는 SQL.

"""입력 비가동 대수의 SQL.

연결은 부르는 쪽(`DuckDBEquipmentRepository`)이 열고 쓰기는 그 쓰기 트랜잭션 안에서만 부른다
(`floor_state_store.py` 와 같은 꼴). 모델과 값 규칙은 `services/manual_downtime.py` 다.

쓰기는 **바뀐 칸만** 고친다 — 비운 칸은 DELETE, 값만 바꾼 칸은 키 아닌 칸 UPDATE, 새 칸은 INSERT 다.
칸마다 셋 가운데 하나만 내므로 한 트랜잭션에서 같은 키(공정, 달)를 지웠다 다시 넣지 않는다(0032 의
PK). 저장마다 이력 한 행을 더한다.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name
from capa_simulation.services.manual_downtime import (
    ManualDowntime,
    ManualDowntimeSave,
    ManualRow,
    changed_cell_count,
)

__all__ = ["read_manual_downtime", "read_manual_downtime_saves", "write_manual_downtime"]


def read_manual_downtime(connection: duckdb.DuckDBPyConnection) -> ManualDowntime:
    """머리와 칸. 머리가 없으면 version 0 이다 — 머리 없이 칸만 있는 DB(손으로 넣은 행)도 version 0
    으로 읽고 칸은 그대로 싣는다. 0 이하·빈 공정 칸은 버린다(셀 것이 없다)."""
    header = connection.execute(
        """
        SELECT version, saved_by, note, updated_at
        FROM equipment_ops.manual_downtime_profile
        WHERE profile_id = 1
        """
    ).fetchone()
    rows = connection.execute(
        """
        SELECT process_name, production_month, units
        FROM equipment_ops.manual_downtime
        ORDER BY process_name, production_month
        """
    ).fetchall()
    cells = tuple(
        (str(process).strip(), int(month), float(units))
        for process, month, units in rows
        if str(process).strip() and units is not None and float(units) > 0
    )
    if header is None:
        return ManualDowntime(rows=cells)
    return ManualDowntime(
        rows=cells,
        version=int(header[0]),
        saved_by=str(header[1] or ""),
        note=str(header[2] or ""),
        updated_at=header[3],
    )


def read_manual_downtime_saves(
    connection: duckdb.DuckDBPyConnection, *, limit: int
) -> tuple[ManualDowntimeSave, ...]:
    """저장 이력 — 최근 것부터 `limit` 행."""
    rows = connection.execute(
        """
        SELECT version, saved_at, saved_by, note, changed_cells, filled_cells, total_units
        FROM equipment_ops.manual_downtime_save
        ORDER BY version DESC
        LIMIT ?
        """,
        [int(limit)],
    ).fetchall()
    return tuple(
        ManualDowntimeSave(
            version=int(version),
            saved_at=saved_at,
            saved_by=str(saved_by or ""),
            note=str(note or ""),
            changed_cells=int(changed),
            filled_cells=int(filled),
            total_units=float(total),
        )
        for version, saved_at, saved_by, note, changed, filled, total in rows
    )


def write_manual_downtime(
    connection: duckdb.DuckDBPyConnection,
    current: ManualDowntime,
    rows: tuple[ManualRow, ...],
    *,
    saved_by: str,
    note: str,
) -> int:
    """`current`(같은 트랜잭션에서 읽은 저장본)와 견줘 바뀐 칸만 고치고 머리를 다음 version 으로
    쓴 뒤 이력 한 행을 더한다. 새 version 을 돌려준다. `rows` 는 `prepare_manual_downtime` 을 지난
    값이다."""
    before = current.cells
    after = {(process, month): units for process, month, units in rows}
    for key in [key for key in before if key not in after]:
        connection.execute(
            """
            DELETE FROM equipment_ops.manual_downtime
            WHERE process_name = ? AND production_month = ?
            """,
            [key[0], key[1]],
        )
    for key, units in after.items():
        if key in before and before[key] != units:
            connection.execute(
                """
                UPDATE equipment_ops.manual_downtime
                SET units = ?, updated_at = current_timestamp
                WHERE process_name = ? AND production_month = ?
                """,
                [units, key[0], key[1]],
            )
    added = [(key, units) for key, units in after.items() if key not in before]
    if added:
        insert_by_name(
            connection,
            schema="equipment_ops",
            table_name="manual_downtime",
            frame=pd.DataFrame(
                {
                    "process_name": [key[0] for key, _ in added],
                    "production_month": pd.Series([key[1] for key, _ in added], dtype="int64"),
                    "units": pd.Series([units for _, units in added], dtype="float64"),
                }
            ),
        )
    version = current.version + 1
    if current.version == 0:
        connection.execute(
            """
            INSERT INTO equipment_ops.manual_downtime_profile (profile_id, version, saved_by, note)
            VALUES (1, 1, ?, ?)
            """,
            [saved_by or None, note or None],
        )
    else:
        connection.execute(
            """
            UPDATE equipment_ops.manual_downtime_profile
            SET version = ?, saved_by = ?, note = ?, updated_at = current_timestamp
            WHERE profile_id = 1
            """,
            [version, saved_by or None, note or None],
        )
    connection.execute(
        """
        INSERT INTO equipment_ops.manual_downtime_save
            (version, saved_by, note, changed_cells, filled_cells, total_units)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            version,
            saved_by or None,
            note or None,
            changed_cell_count(current.rows, rows),
            len(rows),
            round(sum(units for _, _, units in rows), 6),
        ],
    )
    return version
