# Purpose: 필요단축일정 기준선(설비 DB 0021)의 머리·공정·호기 행을 읽고 넣고 지우는 SQL 을 둔다.

"""필요단축일정 기준선의 SQL.

연결은 부르는 쪽(`DuckDBEquipmentRepository`)이 열고 쓰기는 그 쓰기 트랜잭션 안에서만 부른다.
기준선은 고칠 수 없으므로 UPDATE 가 없다 — 넣기·읽기·지우기뿐이다. 모델과 값 규칙은
`services/shortening_baseline.py` 다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from types import MappingProxyType

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name
from capa_simulation.services.equipment_contract import (
    CONVERSION_RATIO_COLUMN,
    EQUIPMENT_ID_COLUMN,
)
from capa_simulation.services.required_shortening import LEVEL_COLUMN
from capa_simulation.services.shortening_baseline import (
    BASELINE_UNIT_COLUMNS,
    ShorteningBaseline,
    ShorteningBaselineDraft,
    ShorteningBaselineSummary,
    normalize_baseline_units,
)

__all__ = [
    "BASELINE_UNIT_DB_COLUMNS",
    "baseline_name_exists",
    "delete_baseline",
    "insert_baseline",
    "list_baselines",
    "load_baseline",
]

BASELINE_UNIT_DB_COLUMNS: Mapping[str, str] = MappingProxyType(
    {
        LEVEL_COLUMN: "target_level",
        "공정": "process_name",
        "호기": "unit_name",
        "구분": "unit_kind",
        EQUIPMENT_ID_COLUMN: "equipment_ids",
        "모듈 수": "module_count",
        CONVERSION_RATIO_COLUMN: "conversion_ratio",
        "기존 Qual": "original_qual",
        "목표 Qual": "target_qual",
        "단축일수": "shortening_days",
        "늘어난 환산대수": "gained_units",
        "대상 월": "target_month",
        "해소 기여 월": "contributed_months",
    }
)
"""얼린 호기 표의 칸 ↔ `shortening_baseline_unit` 컬럼."""

_UNIT_PROJECTION = ", ".join(
    f'{db_column} AS "{column}"' for column, db_column in BASELINE_UNIT_DB_COLUMNS.items()
)
_SUMMARY_PROJECTION = """
    baseline_id, baseline_name, saved_at, plan_today, start_month, end_month, saved_by,
    equipment_revision_id, equipment_revision_no, reference_version, scenario_id, scenario_name,
    scenario_revision_id, scenario_revision_no, scenario_content_token
"""


def baseline_name_exists(connection: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM equipment_ops.shortening_baseline WHERE baseline_name = ?", [name]
    ).fetchone()
    return row is not None


def insert_baseline(
    connection: duckdb.DuckDBPyConnection,
    *,
    baseline_id: str,
    draft: ShorteningBaselineDraft,
    saved_at: datetime,
) -> None:
    """머리·공정·호기 행을 넣는다. 이름 중복은 부르는 쪽이 먼저 거절한다(UNIQUE 가 뒷받침)."""
    source = draft.provenance
    connection.execute(
        """
        INSERT INTO equipment_ops.shortening_baseline (
            baseline_id, baseline_name, saved_at, saved_by, plan_today, start_month, end_month,
            equipment_revision_id, equipment_revision_no, reference_version, scenario_id,
            scenario_name, scenario_revision_id, scenario_revision_no, scenario_content_token
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            baseline_id,
            draft.name,
            saved_at,
            source.saved_by,
            draft.plan_today,
            draft.start_month,
            draft.end_month,
            source.equipment_revision_id,
            source.equipment_revision_no,
            source.reference_version,
            source.scenario_id,
            source.scenario_name,
            source.scenario_revision_id,
            source.scenario_revision_no,
            source.scenario_content_token,
        ],
    )
    if draft.processes:
        insert_by_name(
            connection,
            schema="equipment_ops",
            table_name="shortening_baseline_process",
            frame=pd.DataFrame(
                {
                    "baseline_id": baseline_id,
                    "process_name": list(draft.processes),
                    "sort_order": range(len(draft.processes)),
                    "cutoff_days": pd.array(
                        [draft.cutoff_days.get(process) for process in draft.processes],
                        dtype="Int64",
                    ),
                }
            ),
        )
    units = normalize_baseline_units(draft.units)
    if units.empty:
        return
    incoming = units.rename(columns=dict(BASELINE_UNIT_DB_COLUMNS))
    for column in ("original_qual", "target_qual"):
        incoming[column] = pd.to_datetime(incoming[column])
    incoming.insert(0, "sort_order", range(len(incoming)))
    incoming.insert(0, "baseline_id", baseline_id)
    insert_by_name(
        connection,
        schema="equipment_ops",
        table_name="shortening_baseline_unit",
        frame=incoming,
    )


def list_baselines(connection: duckdb.DuckDBPyConnection) -> list[ShorteningBaselineSummary]:
    """모든 기준선 머리. 최근에 저장한 것이 위다."""
    rows = connection.execute(
        f"""
        SELECT {_SUMMARY_PROJECTION}
        FROM equipment_ops.shortening_baseline
        ORDER BY saved_at DESC, baseline_name
        """
    ).fetchall()
    return [_summary(row) for row in rows]


def load_baseline(
    connection: duckdb.DuckDBPyConnection, baseline_id: str
) -> ShorteningBaseline | None:
    """기준선 한 벌. 없으면 None."""
    header = connection.execute(
        f"""
        SELECT {_SUMMARY_PROJECTION}
        FROM equipment_ops.shortening_baseline
        WHERE baseline_id = ?
        """,
        [baseline_id],
    ).fetchone()
    if header is None:
        return None
    processes = connection.execute(
        """
        SELECT process_name, cutoff_days
        FROM equipment_ops.shortening_baseline_process
        WHERE baseline_id = ?
        ORDER BY sort_order, process_name
        """,
        [baseline_id],
    ).fetchall()
    units = connection.execute(
        f"""
        SELECT {_UNIT_PROJECTION}
        FROM equipment_ops.shortening_baseline_unit
        WHERE baseline_id = ?
        ORDER BY target_level, sort_order
        """,
        [baseline_id],
    ).fetchdf()
    return ShorteningBaseline(
        summary=_summary(header),
        processes=tuple(str(row[0]) for row in processes),
        cutoff_days={str(row[0]): int(row[1]) for row in processes if row[1] is not None},
        units=normalize_baseline_units(units.loc[:, list(BASELINE_UNIT_COLUMNS)]),
    )


def delete_baseline(connection: duckdb.DuckDBPyConnection, baseline_id: str) -> bool:
    """기준선 한 벌을 지운다(자식 행 먼저). 없었으면 False."""
    found = connection.execute(
        "SELECT 1 FROM equipment_ops.shortening_baseline WHERE baseline_id = ?", [baseline_id]
    ).fetchone()
    if found is None:
        return False
    for table in ("shortening_baseline_unit", "shortening_baseline_process"):
        connection.execute(
            f"DELETE FROM equipment_ops.{table} WHERE baseline_id = ?", [baseline_id]
        )
    connection.execute(
        "DELETE FROM equipment_ops.shortening_baseline WHERE baseline_id = ?", [baseline_id]
    )
    return True


def _summary(row: Sequence[object]) -> ShorteningBaselineSummary:
    saved_at, plan_today = row[2], row[3]
    assert isinstance(saved_at, datetime) and isinstance(plan_today, date)
    return ShorteningBaselineSummary(
        baseline_id=str(row[0]),
        name=str(row[1]),
        saved_at=saved_at,
        plan_today=plan_today,
        start_month=int(str(row[4])),
        end_month=int(str(row[5])),
        saved_by=_text(row[6]),
        equipment_revision_id=_text(row[7]),
        equipment_revision_no=_integer(row[8]),
        reference_version=_integer(row[9]),
        scenario_id=_text(row[10]),
        scenario_name=_text(row[11]),
        scenario_revision_id=_text(row[12]),
        scenario_revision_no=_integer(row[13]),
        scenario_content_token=_text(row[14]),
    )


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _integer(value: object) -> int | None:
    return None if value is None else int(str(value))
