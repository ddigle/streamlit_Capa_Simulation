# Purpose: 설비 시나리오 여섯 표의 SQL 을 열린 연결 위에서만 둔다(트랜잭션·신호는 저장소 몫).

"""설비 시나리오 표의 SQL.

연결은 늘 받는다 — 열고 닫기·트랜잭션·쓰기 잠금·동기화 표시는 `DuckDBEquipmentRepository` 몫이다
(`shortening_baseline_store.py` 와 같은 꼴). 여기서는 값을 계약 이름(한글 칸·모델 필드
이름)으로 돌려줄 뿐 모델을 만들지 않는다 — 모델은 `equipment_repository.py` 에 있고 그 모듈이
이 모듈을 부른다.

표에는 외래 키가 없다(설비 DB `0027`). 소유·정합은 저장소가 같은 트랜잭션에서 지킨다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name
from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    QUAL_DATE_COLUMN,
    RELOCATION_DATE_COLUMN,
    SCENARIO_MEMO_COLUMN,
    STOP_DATE_COLUMN,
)
from capa_simulation.services.equipment_scenario import (
    SCHEDULE_DOWNTIME_COLUMNS,
    SCHEDULE_FRAME_COLUMNS,
    UNIT_KEY_COLUMN,
)

# 일정 일곱 칸(한글) ↔ `equipment_schedule_snapshot` 칸(영문). 날짜 여섯의 DB 이름은 설비 마스터
# 표(`EQUIPMENT_MASTER_DB_COLUMNS`)와 같다 — 정지일정 `removal_date`,
# 반출/이설일정 `relocation_date`.
SCENARIO_SCHEDULE_DB_COLUMNS: Mapping[str, str] = MappingProxyType(
    {
        "제진대일정": "vibration_table_date",
        "물류일정": "logistics_date",
        ARRIVAL_DATE_COLUMN: "arrival_date",
        QUAL_DATE_COLUMN: "qual_date",
        STOP_DATE_COLUMN: "removal_date",
        RELOCATION_DATE_COLUMN: "relocation_date",
        SCENARIO_MEMO_COLUMN: "scenario_memo",
    }
)

# 시나리오 쪽 비가동 다섯 칸(한글) ↔ `equipment_schedule_downtime_snapshot` 칸.
SCHEDULE_DOWNTIME_DB_COLUMNS: Mapping[str, str] = MappingProxyType(
    {
        "비가동유형": "downtime_type",
        "시작일": "start_date",
        "종료일": "end_date",
        "상세사유": "detail",
        "비고": "note",
    }
)

# 이관(0027)이 넣는 「운영 일정」 시나리오의 결정적 id. 동기화로 받은 DB 를 다른 PC 가 다시 이관해도
# 같은 행이 나온다.
OPERATIONS_SCENARIO_ID = "operations"

# 시나리오 일정 리비전 한 줄의 투영 — 별칭이 곧 `EquipmentScheduleRevisionSummary` 필드 이름이다.
# 이관 리비전(`legacy_revision_id`)은 옛 마스터·비가동 표의 행 수를 센다 — 공통 리비전
# 요약과 같은 표다.
_SCHEDULE_REVISION_PROJECTION = """
    s.schedule_revision_id AS schedule_revision_id,
    s.equipment_scenario_id AS equipment_scenario_id,
    s.revision_no AS revision_no,
    s.origin AS origin,
    s.created_at AS created_at,
    s.revision_name AS revision_name,
    s.note AS note,
    s.saved_by AS saved_by,
    s.common_revision_id AS common_revision_id,
    s.legacy_revision_id AS legacy_revision_id,
    CASE
        WHEN s.legacy_revision_id IS NULL
        THEN (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_snapshot x
              WHERE x.schedule_revision_id = s.schedule_revision_id)
        WHEN (SELECT COALESCE(MAX(r.equipment_contract_version), 2) FROM equipment_ops.revision r
              WHERE r.revision_id = s.legacy_revision_id) = 3
        THEN (SELECT COUNT(*) FROM equipment_ops.equipment_master_snapshot e
              WHERE e.revision_id = s.legacy_revision_id)
        WHEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
              WHERE e.revision_id = s.legacy_revision_id) > 0
        THEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
              WHERE e.revision_id = s.legacy_revision_id)
        ELSE (SELECT COUNT(*) FROM equipment_ops.schedule_snapshot e
              WHERE e.revision_id = s.legacy_revision_id)
    END AS unit_row_count,
    CASE
        WHEN s.legacy_revision_id IS NULL
        THEN (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_downtime_snapshot x
              WHERE x.schedule_revision_id = s.schedule_revision_id)
        WHEN (SELECT COALESCE(MAX(r.equipment_contract_version), 2) FROM equipment_ops.revision r
              WHERE r.revision_id = s.legacy_revision_id) = 3
        THEN (SELECT COUNT(*) FROM equipment_ops.downtime_schedule_snapshot d
              WHERE d.revision_id = s.legacy_revision_id)
        ELSE (SELECT COUNT(*) FROM equipment_ops.downtime_snapshot d
              WHERE d.revision_id = s.legacy_revision_id)
    END AS downtime_row_count
"""

_RELEASE_PROJECTION = """
    release_no, equipment_scenario_id, schedule_revision_id, released_at, released_by, note
"""


def _rows(
    connection: duckdb.DuckDBPyConnection, sql: str, parameters: Sequence[object] = ()
) -> list[dict[str, object]]:
    """한 조회의 행을 (칸 이름 → 값) 으로 돌려준다."""
    cursor = connection.execute(sql, list(parameters))
    names = [str(column[0]) for column in cursor.description or ()]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def schedule_revision_row(
    connection: duckdb.DuckDBPyConnection, schedule_revision_id: str
) -> dict[str, object] | None:
    """일정 리비전 한 줄(요약 필드 이름). 없으면 None."""
    found = _rows(
        connection,
        f"""
        SELECT {_SCHEDULE_REVISION_PROJECTION}
        FROM equipment_ops.equipment_schedule_revision s
        WHERE s.schedule_revision_id = ?
        """,
        [schedule_revision_id],
    )
    return found[0] if found else None


def schedule_revision_rows(
    connection: duckdb.DuckDBPyConnection, equipment_scenario_id: str, *, limit: int
) -> list[dict[str, object]]:
    """한 시나리오의 일정 리비전, 번호 큰 것부터."""
    return _rows(
        connection,
        f"""
        SELECT {_SCHEDULE_REVISION_PROJECTION}
        FROM equipment_ops.equipment_schedule_revision s
        WHERE s.equipment_scenario_id = ?
        ORDER BY s.revision_no DESC
        LIMIT ?
        """,
        [equipment_scenario_id, limit],
    )


def scenario_rows(connection: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    """설비 시나리오 목록 — 각 최신(`MAX(revision_no)`)·리비전 수와 함께, `list_order`·이름 차례."""
    return _rows(
        connection,
        """
        SELECT c.equipment_scenario_id AS equipment_scenario_id,
               c.scenario_name AS scenario_name,
               c.status AS status,
               c.list_order AS list_order,
               (SELECT s.schedule_revision_id FROM equipment_ops.equipment_schedule_revision s
                WHERE s.equipment_scenario_id = c.equipment_scenario_id
                ORDER BY s.revision_no DESC LIMIT 1) AS latest_schedule_revision_id,
               (SELECT MAX(s.revision_no) FROM equipment_ops.equipment_schedule_revision s
                WHERE s.equipment_scenario_id = c.equipment_scenario_id) AS latest_revision_no,
               (SELECT COUNT(*) FROM equipment_ops.equipment_schedule_revision s
                WHERE s.equipment_scenario_id = c.equipment_scenario_id) AS revision_count
        FROM equipment_ops.equipment_scenario c
        ORDER BY c.list_order NULLS LAST, c.scenario_name, c.equipment_scenario_id
        """,
    )


def scenario_name(connection: duckdb.DuckDBPyConnection, equipment_scenario_id: str) -> str | None:
    row = connection.execute(
        "SELECT scenario_name FROM equipment_ops.equipment_scenario "
        "WHERE equipment_scenario_id = ?",
        [equipment_scenario_id],
    ).fetchone()
    return str(row[0]) if row is not None else None


def latest_release_row(connection: duckdb.DuckDBPyConnection) -> dict[str, object] | None:
    """최신 공식 발행 한 줄(`release_no` 가 가장 큰 것). 발행이 없으면 None."""
    found = _rows(
        connection,
        f"""
        SELECT {_RELEASE_PROJECTION}
        FROM equipment_ops.equipment_official_release
        ORDER BY release_no DESC LIMIT 1
        """,
    )
    return found[0] if found else None


def legacy_trace_count(connection: duckdb.DuckDBPyConnection) -> int:
    """이관 경계 뒤에 쌓인 계약 v3 이하 공통 리비전 수 — 옛 배포로 저장한 흔적이다.

    경계는 마지막 경계 행(`boundary_no` 가 가장 큰 것)의 `through_revision_no` 다. 차례는 번호로만
    정하고 시각(`created_at`)으로 정하지 않는다 — PC 시계에 흔들린다. 경계 행이 없으면 0 으로 본다.
    """
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM equipment_ops.revision r
        WHERE COALESCE(r.equipment_contract_version, 2) <= 3
          AND r.revision_no > COALESCE(
              (SELECT b.through_revision_no FROM equipment_ops.equipment_legacy_boundary b
               ORDER BY b.boundary_no DESC LIMIT 1),
              0
          )
        """
    ).fetchone()
    return int(row[0]) if row is not None else 0


def official_scenario_id(connection: duckdb.DuckDBPyConnection) -> str | None:
    """공식 설비 시나리오 — 최신 발행의 시나리오. 발행이 없으면 「운영 일정」(있으면), 그것도
    없으면 목록 첫 시나리오. 시나리오가 하나도 없으면 None."""
    release = latest_release_row(connection)
    if release is not None:
        return str(release["equipment_scenario_id"])
    rows = scenario_rows(connection)
    ids = [str(row["equipment_scenario_id"]) for row in rows]
    if OPERATIONS_SCENARIO_ID in ids:
        return OPERATIONS_SCENARIO_ID
    return ids[0] if ids else None


def paired_schedule_revision_id(
    connection: duckdb.DuckDBPyConnection, equipment_scenario_id: str, common_revision_id: str
) -> str | None:
    """그 시나리오에서 저장 때 이 공통 리비전을 함께 본 일정 리비전 가운데 번호가 가장 큰 것."""
    row = connection.execute(
        """
        SELECT schedule_revision_id
        FROM equipment_ops.equipment_schedule_revision
        WHERE equipment_scenario_id = ? AND common_revision_id = ?
        ORDER BY revision_no DESC
        LIMIT 1
        """,
        [equipment_scenario_id, common_revision_id],
    ).fetchone()
    return str(row[0]) if row is not None else None


def scenario_name_taken(
    connection: duckdb.DuckDBPyConnection, name: str, *, except_scenario_id: str | None = None
) -> bool:
    """같은 이름의 설비 시나리오가 있는가(보관본까지 — 앞뒤 공백을 뗀 값의 완전 일치)."""
    row = connection.execute(
        """
        SELECT 1 FROM equipment_ops.equipment_scenario
        WHERE scenario_name = ? AND equipment_scenario_id IS DISTINCT FROM ?
        LIMIT 1
        """,
        [name, except_scenario_id],
    ).fetchone()
    return row is not None


def insert_scenario(
    connection: duckdb.DuckDBPyConnection,
    *,
    equipment_scenario_id: str,
    name: str,
    source_schedule_revision_id: str | None,
    created_by: str | None,
) -> None:
    """설비 시나리오 한 행 — 목록 차례는 지금 끝 다음."""
    connection.execute(
        """
        INSERT INTO equipment_ops.equipment_scenario (
            equipment_scenario_id, scenario_name, list_order, source_schedule_revision_id,
            created_by
        )
        SELECT ?, ?, COALESCE(MAX(list_order), -1) + 1, ?, ?
        FROM equipment_ops.equipment_scenario
        """,
        [equipment_scenario_id, name, source_schedule_revision_id, created_by],
    )


def rename_scenario(
    connection: duckdb.DuckDBPyConnection, equipment_scenario_id: str, name: str
) -> None:
    connection.execute(
        """
        UPDATE equipment_ops.equipment_scenario
        SET scenario_name = ?, updated_at = current_timestamp
        WHERE equipment_scenario_id = ?
        """,
        [name, equipment_scenario_id],
    )


def insert_schedule_revision(
    connection: duckdb.DuckDBPyConnection,
    *,
    equipment_scenario_id: str,
    origin: str,
    common_revision_id: str | None,
    note: str | None,
    saved_by: str | None,
    schedule: pd.DataFrame,
    downtime: pd.DataFrame,
    schedule_hash: str,
    downtime_hash: str,
    revision_name: str | None = None,
) -> str:
    """일정 리비전 하나(머리 + 키별 일곱 칸 + 비가동)를 넣고 id 를 돌려준다.

    번호는 그 시나리오의 `MAX(revision_no) + 1` 이다(E6 — 시나리오마다 r1 부터). `schedule` 은
    키 + 일곱 칸(`SCHEDULE_FRAME_COLUMNS`), `downtime` 은 키 + 다섯 칸이고 검증을 마친 값이다.
    리비전명(이름표, E7)은 넣을 때 함께 적는다 — 같은 트랜잭션에서 넣은 행을 다시 고치지 않는다.
    """
    schedule_revision_id = uuid4().hex
    connection.execute(
        """
        INSERT INTO equipment_ops.equipment_schedule_revision (
            schedule_revision_id, equipment_scenario_id, revision_no, revision_name, note,
            saved_by, origin, common_revision_id, schedule_hash, downtime_hash
        )
        SELECT ?, ?, COALESCE(MAX(revision_no), 0) + 1, ?, ?, ?, ?, ?, ?, ?
        FROM equipment_ops.equipment_schedule_revision
        WHERE equipment_scenario_id = ?
        """,
        [
            schedule_revision_id,
            equipment_scenario_id,
            revision_name,
            note,
            saved_by,
            origin,
            common_revision_id,
            schedule_hash,
            downtime_hash,
            equipment_scenario_id,
        ],
    )
    if not schedule.empty:
        rows = schedule.loc[:, list(SCHEDULE_FRAME_COLUMNS)].rename(
            columns={
                UNIT_KEY_COLUMN: "unit_key",
                **dict(SCENARIO_SCHEDULE_DB_COLUMNS),
            }
        )
        rows.insert(0, "schedule_revision_id", schedule_revision_id)
        insert_by_name(
            connection,
            schema="equipment_ops",
            table_name="equipment_schedule_snapshot",
            frame=rows,
        )
    if not downtime.empty:
        events = downtime.loc[:, list(SCHEDULE_DOWNTIME_COLUMNS)].rename(
            columns={
                UNIT_KEY_COLUMN: "unit_key",
                **dict(SCHEDULE_DOWNTIME_DB_COLUMNS),
            }
        )
        events.insert(0, "source_row_no", range(1, len(events) + 1))
        events.insert(0, "schedule_revision_id", schedule_revision_id)
        insert_by_name(
            connection,
            schema="equipment_ops",
            table_name="equipment_schedule_downtime_snapshot",
            frame=events,
        )
    return schedule_revision_id


def rename_schedule_revision(
    connection: duckdb.DuckDBPyConnection, schedule_revision_id: str, name: str | None
) -> None:
    """일정 리비전의 이름표(`revision_name`)만 고친다(None 이면 지운다). 내용·번호·메모·저장자·
    시각은 그대로다 — 리비전 내용은 append-only 다(AGENTS 5장 8)."""
    connection.execute(
        """
        UPDATE equipment_ops.equipment_schedule_revision
        SET revision_name = ?
        WHERE schedule_revision_id = ?
        """,
        [name, schedule_revision_id],
    )


def insert_release(
    connection: duckdb.DuckDBPyConnection,
    *,
    equipment_scenario_id: str,
    schedule_revision_id: str,
    released_by: str | None,
    note: str | None,
) -> int:
    """공식 발행 한 행(append-only)을 넣고 그 번호(`MAX(release_no) + 1`)를 돌려준다."""
    row = connection.execute(
        "SELECT COALESCE(MAX(release_no), 0) + 1 FROM equipment_ops.equipment_official_release"
    ).fetchone()
    if row is None:
        raise RuntimeError("공식 발행 번호를 만들지 못했습니다.")
    release_no = int(row[0])
    connection.execute(
        """
        INSERT INTO equipment_ops.equipment_official_release (
            release_id, release_no, equipment_scenario_id, schedule_revision_id, released_by,
            note
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [uuid4().hex, release_no, equipment_scenario_id, schedule_revision_id, released_by, note],
    )
    return release_no


def latest_boundary_no(connection: duckdb.DuckDBPyConnection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(boundary_no), 0) FROM equipment_ops.equipment_legacy_boundary"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def insert_boundary(
    connection: duckdb.DuckDBPyConnection, *, through_revision_no: int, note: str | None
) -> int:
    """이관 경계 한 행을 덧붙이고 그 번호를 돌려준다."""
    boundary_no = latest_boundary_no(connection) + 1
    connection.execute(
        """
        INSERT INTO equipment_ops.equipment_legacy_boundary (
            boundary_no, through_revision_no, note
        ) VALUES (?, ?, ?)
        """,
        [boundary_no, through_revision_no, note],
    )
    return boundary_no


def schedule_frame(
    connection: duckdb.DuckDBPyConnection, schedule_revision_id: str
) -> pd.DataFrame:
    """새 표의 일정 행(키 + 일곱 칸), 키 차례. 형은 맞추지 않는다(`normalize_schedule_frame`)."""
    projection = ", ".join(
        [f'unit_key AS "{UNIT_KEY_COLUMN}"']
        + [f'{db} AS "{column}"' for column, db in SCENARIO_SCHEDULE_DB_COLUMNS.items()]
    )
    frame = connection.execute(
        f"""
        SELECT {projection}
        FROM equipment_ops.equipment_schedule_snapshot
        WHERE schedule_revision_id = ?
        ORDER BY unit_key
        """,
        [schedule_revision_id],
    ).fetchdf()
    return frame.reindex(columns=list(SCHEDULE_FRAME_COLUMNS))


def schedule_downtime_frame(
    connection: duckdb.DuckDBPyConnection, schedule_revision_id: str
) -> pd.DataFrame:
    """새 표의 비가동 행(키 + 다섯 칸), 저장 차례(`source_row_no`)."""
    projection = ", ".join(
        [f'unit_key AS "{UNIT_KEY_COLUMN}"']
        + [f'{db} AS "{column}"' for column, db in SCHEDULE_DOWNTIME_DB_COLUMNS.items()]
    )
    frame = connection.execute(
        f"""
        SELECT {projection}
        FROM equipment_ops.equipment_schedule_downtime_snapshot
        WHERE schedule_revision_id = ?
        ORDER BY source_row_no
        """,
        [schedule_revision_id],
    ).fetchdf()
    return frame.reindex(columns=list(SCHEDULE_DOWNTIME_COLUMNS))
