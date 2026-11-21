# Purpose: 누적 진척 넣기 스냅숏(설비 0037)의 머리 · 공정 · 호기 행을 읽고 갈아 쓰고 지우는 SQL.

"""누적 진척 넣기 스냅숏의 SQL.

연결은 부르는 쪽(`DuckDBEquipmentRepository`)이 열고 쓰기는 그 쓰기 트랜잭션 안에서만 부른다 — 기록
한 줄(`shortening_progress_log_store.py`)을 쓴 같은 트랜잭션이다. 모델과 가름은
`services/shortening_progress_reasons.py` 다.

- 갈아 쓰기는 새 `snapshot_id` 다 — 머리는 제자리 UPDATE(없으면 INSERT), 새 id 자식을 넣고 옛 id
  자식을 지운다. 한 트랜잭션에서 같은 키를 지웠다 다시 넣지 않는다.
- 머리의 `log_updated_at` 은 늘 지금 기록 줄의 `updated_at` 을 SQL 로 옮겨 적는다(따로 잰 시각을
  쓰지 않는다). 읽기는 그 값이 기록 줄과 같은 머리만 돌려준다.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import insert_by_name
from capa_simulation.services.shortening_baseline import BaselineProvenance
from capa_simulation.services.shortening_progress_log import ProgressWeek
from capa_simulation.services.shortening_progress_reasons import (
    SNAPSHOT_UNIT_COLUMNS,
    ProgressSnapshot,
    ProgressSnapshotDraft,
    empty_snapshot_units,
)

__all__ = [
    "carry_progress_snapshot",
    "delete_progress_snapshot",
    "read_progress_snapshots",
    "same_progress_snapshot",
    "write_progress_snapshot",
]

_PROVENANCE_COLUMNS = (
    "equipment_revision_id",
    "equipment_revision_no",
    "reference_version",
    "scenario_id",
    "scenario_name",
    "scenario_revision_id",
    "scenario_revision_no",
    "scenario_content_token",
    "equipment_schedule_revision_ref",
    "equipment_schedule_revision_no",
    "equipment_scenario_name",
    "equipment_release_no",
)
_HEADER_COLUMNS = (
    "iso_year",
    "iso_week",
    "snapshot_id",
    "log_updated_at",
    "captured_at",
    "captured_by",
    "snapshot_days",
    "target_level",
    "schedule_basis",
    "scope_selected",
    "plan_today",
    "start_month",
    "end_month",
    "content_digest",
    *_PROVENANCE_COLUMNS,
)
_UNIT_DB_COLUMNS = {
    "공정": "process_name",
    "호기": "unit_name",
    "구분": "unit_kind",
    "기존 Qual": "original_qual",
    "목표 Qual": "target_qual",
    "단축일수": "shortening_days",
    "모듈 수": "module_count",
}


def read_progress_snapshots(connection: duckdb.DuckDBPyConnection) -> tuple[ProgressSnapshot, ...]:
    """지금 기록 줄과 같은 쓰기에서 선 스냅숏 전부(주 차례). 기록 줄이 없거나 그 저장 시각이 다른
    머리(옛 코드가 고친 주 · 남은 머리)는 버린다. 그 해에 없는 주차도 버린다."""
    columns = ", ".join(f"s.{column}" for column in _HEADER_COLUMNS)
    headers = connection.execute(
        f"""
        SELECT {columns}
        FROM equipment_ops.shortening_progress_snapshot AS s
        JOIN equipment_ops.shortening_progress_log AS l
          ON l.iso_year = s.iso_year AND l.iso_week = s.iso_week
         AND l.updated_at = s.log_updated_at
        ORDER BY s.iso_year, s.iso_week
        """
    ).fetchall()
    if not headers:
        return ()
    rows = [dict(zip(_HEADER_COLUMNS, header, strict=True)) for header in headers]
    ids = [str(row["snapshot_id"]) for row in rows]
    processes = _processes(connection, ids)
    units = _units(connection, ids)
    out: list[ProgressSnapshot] = []
    for row in rows:
        try:
            week = ProgressWeek(int(row["iso_year"]), int(row["iso_week"]))
        except ValueError:
            continue
        snapshot_id = str(row["snapshot_id"])
        scope = processes.get(snapshot_id, [])
        draft = ProgressSnapshotDraft(
            days=int(row["snapshot_days"]),
            level_percent=int(row["target_level"]),
            basis=str(row["schedule_basis"]),
            selected=bool(row["scope_selected"]),
            today=row["plan_today"],
            months=(int(row["start_month"]), int(row["end_month"])),
            processes=tuple(name for name, _ in scope),
            cutoff_days=tuple(cutoff for _, cutoff in scope),
            units=units.get(snapshot_id, empty_snapshot_units()),
            provenance=BaselineProvenance(
                **{column: row[column] for column in _PROVENANCE_COLUMNS}
            ),
            digest=str(row["content_digest"]),
        )
        out.append(
            ProgressSnapshot(
                week=week,
                draft=draft,
                log_updated_at=row["log_updated_at"],
                captured_at=row["captured_at"],
                captured_by=str(row["captured_by"] or ""),
            )
        )
    return tuple(out)


def same_progress_snapshot(
    connection: duckdb.DuckDBPyConnection, week: ProgressWeek, digest: str
) -> bool:
    """그 주에 지금 기록 줄과 같은 쓰기에서 선 스냅숏이 있고 구성 글이 같은가."""
    row = connection.execute(
        """
        SELECT s.content_digest
        FROM equipment_ops.shortening_progress_snapshot AS s
        JOIN equipment_ops.shortening_progress_log AS l
          ON l.iso_year = s.iso_year AND l.iso_week = s.iso_week
         AND l.updated_at = s.log_updated_at
        WHERE s.iso_year = ? AND s.iso_week = ?
        """,
        [week.year, week.week],
    ).fetchone()
    return row is not None and str(row[0]) == digest


def write_progress_snapshot(
    connection: duckdb.DuckDBPyConnection,
    week: ProgressWeek,
    draft: ProgressSnapshotDraft,
    *,
    captured_by: str,
) -> None:
    """그 주 스냅숏을 갈아 쓴다 — 기록 줄을 쓴 **뒤** 같은 트랜잭션에서 부른다(머리의
    `log_updated_at` 을 그 줄에서 옮겨 적는다)."""
    old = _snapshot_id(connection, week)
    new = uuid4().hex
    provenance = draft.provenance
    values: dict[str, object] = {
        "snapshot_id": new,
        "captured_by": captured_by or None,
        "snapshot_days": int(draft.days),
        "target_level": int(draft.level_percent),
        "schedule_basis": draft.basis,
        "scope_selected": bool(draft.selected),
        "plan_today": draft.today,
        "start_month": int(draft.months[0]),
        "end_month": int(draft.months[1]),
        "content_digest": draft.digest,
        **{column: getattr(provenance, column) for column in _PROVENANCE_COLUMNS},
    }
    names = list(values)
    if old is None:
        connection.execute(
            f"""
            INSERT INTO equipment_ops.shortening_progress_snapshot
                (iso_year, iso_week, log_updated_at, {", ".join(names)})
            SELECT ?, ?, l.updated_at, {", ".join("?" for _ in names)}
            FROM equipment_ops.shortening_progress_log AS l
            WHERE l.iso_year = ? AND l.iso_week = ?
            """,
            [week.year, week.week, *values.values(), week.year, week.week],
        )
    else:
        assignments = ", ".join(f"{name} = ?" for name in names)
        connection.execute(
            f"""
            UPDATE equipment_ops.shortening_progress_snapshot
            SET {assignments}, captured_at = current_timestamp,
                log_updated_at = (
                    SELECT l.updated_at FROM equipment_ops.shortening_progress_log AS l
                    WHERE l.iso_year = ? AND l.iso_week = ?
                )
            WHERE iso_year = ? AND iso_week = ?
            """,
            [*values.values(), week.year, week.week, week.year, week.week],
        )
    if draft.processes:
        insert_by_name(
            connection,
            schema="equipment_ops",
            table_name="shortening_progress_snapshot_process",
            frame=pd.DataFrame(
                {
                    "snapshot_id": new,
                    "process_name": list(draft.processes),
                    "sort_order": range(len(draft.processes)),
                    "cutoff_days": pd.array(list(draft.cutoff_days), dtype="Int64"),
                }
            ),
        )
    if not draft.units.empty:
        frame = draft.units.loc[:, list(SNAPSHOT_UNIT_COLUMNS)].rename(columns=_UNIT_DB_COLUMNS)
        for column in ("original_qual", "target_qual"):
            frame[column] = pd.to_datetime(frame[column])
        frame.insert(0, "sort_order", range(len(frame)))
        frame.insert(0, "snapshot_id", new)
        insert_by_name(
            connection,
            schema="equipment_ops",
            table_name="shortening_progress_snapshot_unit",
            frame=frame.reset_index(drop=True),
        )
    if old is not None:
        _delete_children(connection, old)


def carry_progress_snapshot(
    connection: duckdb.DuckDBPyConnection,
    week: ProgressWeek,
    previous_updated_at: datetime | None,
) -> None:
    """넣기 없이 그 주 기록을 고친 저장 — 기록 줄을 쓴 **뒤** 부른다. 고치기 전 기록 줄과 같은
    쓰기에서 선 스냅숏은 남기고 새 기록 시각으로 옮긴다(넣기 뒤 손으로 고친 몫은 「손 고침」 이다).
    그 밖의 머리 (옛 코드가 남긴 것 · 기록 없이 남은 것)는 지운다 — 엉뚱한 기록에 붙지 않게."""
    row = connection.execute(
        """
        SELECT snapshot_id, log_updated_at FROM equipment_ops.shortening_progress_snapshot
        WHERE iso_year = ? AND iso_week = ?
        """,
        [week.year, week.week],
    ).fetchone()
    if row is None:
        return
    snapshot_id, stamped = row
    if previous_updated_at is not None and stamped == previous_updated_at:
        connection.execute(
            """
            UPDATE equipment_ops.shortening_progress_snapshot
            SET log_updated_at = (
                SELECT l.updated_at FROM equipment_ops.shortening_progress_log AS l
                WHERE l.iso_year = ? AND l.iso_week = ?
            )
            WHERE iso_year = ? AND iso_week = ?
            """,
            [week.year, week.week, week.year, week.week],
        )
        return
    _delete_header(connection, week, str(snapshot_id))


def delete_progress_snapshot(connection: duckdb.DuckDBPyConnection, week: ProgressWeek) -> None:
    """그 주 스냅숏(머리 · 자식)을 지운다 — 기록 지우기와 같은 트랜잭션."""
    snapshot_id = _snapshot_id(connection, week)
    if snapshot_id is not None:
        _delete_header(connection, week, snapshot_id)


def _snapshot_id(connection: duckdb.DuckDBPyConnection, week: ProgressWeek) -> str | None:
    row = connection.execute(
        """
        SELECT snapshot_id FROM equipment_ops.shortening_progress_snapshot
        WHERE iso_year = ? AND iso_week = ?
        """,
        [week.year, week.week],
    ).fetchone()
    return None if row is None else str(row[0])


def _delete_header(
    connection: duckdb.DuckDBPyConnection, week: ProgressWeek, snapshot_id: str
) -> None:
    connection.execute(
        """
        DELETE FROM equipment_ops.shortening_progress_snapshot
        WHERE iso_year = ? AND iso_week = ?
        """,
        [week.year, week.week],
    )
    _delete_children(connection, snapshot_id)


def _delete_children(connection: duckdb.DuckDBPyConnection, snapshot_id: str) -> None:
    for table in ("shortening_progress_snapshot_process", "shortening_progress_snapshot_unit"):
        connection.execute(
            f"DELETE FROM equipment_ops.{table} WHERE snapshot_id = ?", [snapshot_id]
        )


def _processes(
    connection: duckdb.DuckDBPyConnection, ids: list[str]
) -> dict[str, list[tuple[str, int | None]]]:
    rows = connection.execute(
        """
        SELECT snapshot_id, process_name, cutoff_days
        FROM equipment_ops.shortening_progress_snapshot_process
        WHERE list_contains(?, snapshot_id)
        ORDER BY snapshot_id, sort_order, process_name
        """,
        [ids],
    ).fetchall()
    out: dict[str, list[tuple[str, int | None]]] = {}
    for snapshot_id, name, cutoff in rows:
        out.setdefault(str(snapshot_id), []).append(
            (str(name), None if cutoff is None else int(cutoff))
        )
    return out


def _units(connection: duckdb.DuckDBPyConnection, ids: list[str]) -> dict[str, pd.DataFrame]:
    projection = ", ".join(f'{db} AS "{column}"' for column, db in _UNIT_DB_COLUMNS.items())
    frame = connection.execute(
        f"""
        SELECT snapshot_id, {projection}
        FROM equipment_ops.shortening_progress_snapshot_unit
        WHERE list_contains(?, snapshot_id)
        ORDER BY snapshot_id, sort_order
        """,
        [ids],
    ).df()
    out: dict[str, pd.DataFrame] = {}
    for snapshot_id, group in frame.groupby("snapshot_id", sort=False):
        units = group.loc[:, list(SNAPSHOT_UNIT_COLUMNS)].reset_index(drop=True)
        for column in ("기존 Qual", "목표 Qual"):
            units[column] = pd.Series(
                [_as_date(value) for value in units[column]], index=units.index, dtype="object"
            )
        for column in ("단축일수", "모듈 수"):
            units[column] = pd.to_numeric(units[column]).astype("Int64")
        out[str(snapshot_id)] = units
    return out


def _as_date(value: object) -> object:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    return value
