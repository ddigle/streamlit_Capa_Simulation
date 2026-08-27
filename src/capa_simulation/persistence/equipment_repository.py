"""Immutable DuckDB snapshots for equipment baselines and unit schedules."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.persistence.equipment_migration_runner import apply_equipment_migrations
from capa_simulation.services.equipment_availability import (
    BASELINE_COLUMNS,
    SCHEDULE_COLUMNS,
    prepare_equipment_baseline,
    prepare_equipment_schedule,
)

_WRITE_LOCK = threading.RLock()


@dataclass(frozen=True)
class EquipmentRevisionSummary:
    revision_id: str
    revision_no: int
    note: str | None
    baseline_row_count: int
    schedule_row_count: int
    created_at: datetime


@dataclass(frozen=True)
class EquipmentSnapshot:
    revision: EquipmentRevisionSummary
    baseline: pd.DataFrame
    schedule: pd.DataFrame


class DuckDBEquipmentRepository:
    """Persist full equipment input snapshots without changing past revisions."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def initialize(self) -> tuple[int, ...]:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, self._connect() as connection:
            return apply_equipment_migrations(connection)

    def save_snapshot(
        self,
        baseline: pd.DataFrame,
        schedule: pd.DataFrame,
        *,
        note: str | None = None,
    ) -> EquipmentSnapshot:
        prepared_baseline = prepare_equipment_baseline(baseline)
        prepared_schedule = prepare_equipment_schedule(schedule)
        normalized_note = note.strip() if note and note.strip() else None
        revision_id = str(uuid4())
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM equipment_ops.revision"
            ).fetchone()
            if row is None:
                raise RuntimeError("설비 이력 번호를 생성하지 못했습니다.")
            revision_no = int(row[0])
            connection.execute(
                """
                INSERT INTO equipment_ops.revision (
                    revision_id, revision_no, note, baseline_hash, schedule_hash
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    revision_id,
                    revision_no,
                    normalized_note,
                    _frame_hash(prepared_baseline),
                    _frame_hash(prepared_schedule),
                ],
            )
            _insert_baseline(connection, revision_id, prepared_baseline)
            _insert_schedule(connection, revision_id, prepared_schedule)
        return self.load_snapshot(revision_id)

    def load_latest_snapshot(self) -> EquipmentSnapshot | None:
        with self._connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT revision_id FROM equipment_ops.revision ORDER BY revision_no DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self.load_snapshot(str(row[0]))

    def load_snapshot(self, revision_id: str) -> EquipmentSnapshot:
        with self._connect(read_only=True) as connection:
            revision_row = connection.execute(
                """
                SELECT r.revision_id, r.revision_no, r.note,
                       (SELECT COUNT(*) FROM equipment_ops.baseline_snapshot b
                        WHERE b.revision_id = r.revision_id),
                       (SELECT COUNT(*) FROM equipment_ops.schedule_snapshot s
                        WHERE s.revision_id = r.revision_id),
                       r.created_at
                FROM equipment_ops.revision r
                WHERE r.revision_id = ?
                """,
                [revision_id],
            ).fetchone()
            if revision_row is None:
                raise KeyError(f"설비 이력을 찾을 수 없습니다: {revision_id}")
            baseline = connection.execute(
                """
                SELECT process_name AS "공정", classification AS "분류",
                       base_count AS "기존보유대수", note AS "비고"
                FROM equipment_ops.baseline_snapshot
                WHERE revision_id = ? ORDER BY source_row_no
                """,
                [revision_id],
            ).fetchdf()
            schedule = connection.execute(
                """
                SELECT equipment_id AS "호기", process_name AS "공정",
                       classification AS "분류", arrival_date AS "입고일",
                       setup_start_date AS "셋업시작일",
                       setup_complete_date AS "셋업완료일", note AS "비고"
                FROM equipment_ops.schedule_snapshot
                WHERE revision_id = ? ORDER BY source_row_no
                """,
                [revision_id],
            ).fetchdf()
        return EquipmentSnapshot(
            revision=_revision_summary(revision_row),
            baseline=prepare_equipment_baseline(baseline.reindex(columns=BASELINE_COLUMNS)),
            schedule=prepare_equipment_schedule(schedule.reindex(columns=SCHEDULE_COLUMNS)),
        )

    def list_revisions(self, *, limit: int = 50) -> list[EquipmentRevisionSummary]:
        if limit <= 0:
            raise ValueError("설비 이력 조회 건수는 1 이상이어야 합니다.")
        with self._connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT r.revision_id, r.revision_no, r.note,
                       (SELECT COUNT(*) FROM equipment_ops.baseline_snapshot b
                        WHERE b.revision_id = r.revision_id),
                       (SELECT COUNT(*) FROM equipment_ops.schedule_snapshot s
                        WHERE s.revision_id = r.revision_id),
                       r.created_at
                FROM equipment_ops.revision r
                ORDER BY r.revision_no DESC LIMIT ?
                """,
                [limit],
            ).fetchall()
        return [_revision_summary(row) for row in rows]

    @contextmanager
    def _write_transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with _WRITE_LOCK, self._connect() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                yield connection
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _connect(self, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._database_path), read_only=read_only)


def _insert_baseline(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        return
    incoming = frame.rename(
        columns={
            "공정": "process_name",
            "분류": "classification",
            "기존보유대수": "base_count",
            "비고": "note",
        }
    ).copy()
    incoming.insert(0, "source_row_no", range(1, len(incoming) + 1))
    incoming.insert(0, "revision_id", revision_id)
    _insert_registered(connection, "equipment_ops.baseline_snapshot", incoming)


def _insert_schedule(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        return
    incoming = frame.rename(
        columns={
            "호기": "equipment_id",
            "공정": "process_name",
            "분류": "classification",
            "입고일": "arrival_date",
            "셋업시작일": "setup_start_date",
            "셋업완료일": "setup_complete_date",
            "비고": "note",
        }
    ).copy()
    incoming.insert(0, "source_row_no", range(1, len(incoming) + 1))
    incoming.insert(0, "revision_id", revision_id)
    _insert_registered(connection, "equipment_ops.schedule_snapshot", incoming)


def _insert_registered(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    frame: pd.DataFrame,
) -> None:
    view_name = f"_incoming_{uuid4().hex}"
    connection.register(view_name, frame)
    try:
        connection.execute(f"INSERT INTO {table_name} BY NAME SELECT * FROM {view_name}")
    finally:
        connection.unregister(view_name)


def _frame_hash(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update("\x1f".join(str(column) for column in frame.columns).encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(frame, index=False).to_numpy(dtype="uint64").tobytes())
    return digest.hexdigest()


def _revision_summary(row: Sequence[object]) -> EquipmentRevisionSummary:
    created_at = row[5]
    if not isinstance(created_at, datetime):
        raise TypeError("DuckDB 설비 이력 시각이 datetime이 아닙니다.")
    return EquipmentRevisionSummary(
        revision_id=str(row[0]),
        revision_no=_as_int(row[1], "리비전 번호"),
        note=str(row[2]) if row[2] is not None else None,
        baseline_row_count=_as_int(row[3], "기존 보유대수 행 수"),
        schedule_row_count=_as_int(row[4], "설비호기 일정 행 수"),
        created_at=created_at,
    )


def _as_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"DuckDB {label}가 정수가 아닙니다.")
    return value
