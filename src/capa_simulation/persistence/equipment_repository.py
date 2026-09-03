# Purpose: Immutable DuckDB snapshots for unified equipment operations input.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 캐시용 최신 ID 조회를 분리하고 저장·로드 시 설비 마스터 이중 정규화를 제거함.

"""Immutable DuckDB snapshots for unified equipment operations input."""

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
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    empty_equipment_master,
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.standard_target_capacity import prepare_weekly_availability

_WRITE_LOCK = threading.RLock()


@dataclass(frozen=True)
class EquipmentRevisionSummary:
    revision_id: str
    revision_no: int
    note: str | None
    baseline_row_count: int
    equipment_row_count: int
    downtime_row_count: int
    created_at: datetime


@dataclass(frozen=True)
class EquipmentSnapshot:
    revision: EquipmentRevisionSummary
    baseline: pd.DataFrame
    equipment: pd.DataFrame
    downtime: pd.DataFrame


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
        equipment: pd.DataFrame,
        downtime: pd.DataFrame,
        *,
        note: str | None = None,
    ) -> EquipmentSnapshot:
        prepared_baseline = prepare_equipment_baseline(baseline)
        prepared_equipment = prepare_equipment_master(equipment)
        prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared_equipment)
        normalized_note = note.strip() if note and note.strip() else None
        baseline_hash = _frame_hash(prepared_baseline)
        equipment_hash = _frame_hash(prepared_equipment)
        downtime_hash = _frame_hash(prepared_downtime)
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
                    revision_id, revision_no, note, baseline_hash, schedule_hash,
                    equipment_hash, downtime_hash, equipment_contract_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 3)
                """,
                [
                    revision_id,
                    revision_no,
                    normalized_note,
                    baseline_hash,
                    equipment_hash,
                    equipment_hash,
                    downtime_hash,
                ],
            )
            _insert_baseline(connection, revision_id, prepared_baseline)
            _insert_equipment(connection, revision_id, prepared_equipment)
            _insert_downtime(connection, revision_id, prepared_downtime)
        return self.load_snapshot(revision_id)

    def load_latest_snapshot(self) -> EquipmentSnapshot | None:
        revision_id = self.latest_revision_id()
        if revision_id is None:
            return None
        return self.load_snapshot(revision_id)

    def latest_revision_id(self) -> str | None:
        """Return the newest immutable revision id without loading its frames."""
        with self._connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT revision_id FROM equipment_ops.revision ORDER BY revision_no DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def load_snapshot(self, revision_id: str) -> EquipmentSnapshot:
        with self._connect(read_only=True) as connection:
            revision_row = connection.execute(
                """
                SELECT r.revision_id, r.revision_no, r.note,
                       (SELECT COUNT(*) FROM equipment_ops.baseline_snapshot b
                        WHERE b.revision_id = r.revision_id),
                       CASE
                           WHEN r.equipment_contract_version = 3
                           THEN (SELECT COUNT(*) FROM equipment_ops.equipment_master_snapshot e
                                 WHERE e.revision_id = r.revision_id)
                           WHEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
                                 WHERE e.revision_id = r.revision_id) > 0
                           THEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
                                 WHERE e.revision_id = r.revision_id)
                           ELSE (SELECT COUNT(*) FROM equipment_ops.schedule_snapshot s
                                 WHERE s.revision_id = r.revision_id)
                       END,
                       CASE
                           WHEN r.equipment_contract_version = 3
                           THEN (SELECT COUNT(*) FROM equipment_ops.downtime_schedule_snapshot d
                                 WHERE d.revision_id = r.revision_id)
                           ELSE (SELECT COUNT(*) FROM equipment_ops.downtime_snapshot d
                                 WHERE d.revision_id = r.revision_id)
                       END,
                       r.created_at, r.equipment_contract_version
                FROM equipment_ops.revision r
                WHERE r.revision_id = ?
                """,
                [revision_id],
            ).fetchone()
            if revision_row is None:
                raise KeyError(f"설비 이력을 찾을 수 없습니다: {revision_id}")
            baseline = _load_baseline(connection, revision_id)
            contract_version = int(revision_row[7])
            if contract_version == 3:
                equipment = _load_equipment_master(connection, revision_id)
                downtime = _load_downtime_schedule(connection, revision_id)
            else:
                equipment = _load_legacy_equipment(connection, revision_id)
                if equipment.empty:
                    equipment = _load_legacy_schedule(connection, revision_id)
                downtime = _load_legacy_downtime(connection, revision_id)
        prepared_equipment = prepare_equipment_master(equipment.reindex(columns=EQUIPMENT_COLUMNS))
        return EquipmentSnapshot(
            revision=_revision_summary(revision_row),
            baseline=prepare_equipment_baseline(baseline.reindex(columns=BASELINE_COLUMNS)),
            equipment=prepared_equipment,
            downtime=prepare_downtime_for_prepared_equipment(
                downtime.reindex(columns=DOWNTIME_COLUMNS), prepared_equipment
            ),
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
                       CASE
                           WHEN r.equipment_contract_version = 3
                           THEN (SELECT COUNT(*) FROM equipment_ops.equipment_master_snapshot e
                                 WHERE e.revision_id = r.revision_id)
                           WHEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
                                 WHERE e.revision_id = r.revision_id) > 0
                           THEN (SELECT COUNT(*) FROM equipment_ops.equipment_snapshot e
                                 WHERE e.revision_id = r.revision_id)
                           ELSE (SELECT COUNT(*) FROM equipment_ops.schedule_snapshot s
                                 WHERE s.revision_id = r.revision_id)
                       END,
                       CASE
                           WHEN r.equipment_contract_version = 3
                           THEN (SELECT COUNT(*) FROM equipment_ops.downtime_schedule_snapshot d
                                 WHERE d.revision_id = r.revision_id)
                           ELSE (SELECT COUNT(*) FROM equipment_ops.downtime_snapshot d
                                 WHERE d.revision_id = r.revision_id)
                       END,
                       r.created_at
                FROM equipment_ops.revision r
                ORDER BY r.revision_no DESC LIMIT ?
                """,
                [limit],
            ).fetchall()
        return [_revision_summary(row) for row in rows]

    def save_standard_target_availability(self, data: pd.DataFrame) -> pd.DataFrame:
        """Upsert the unversioned current weekly availability used by target Capa."""
        prepared = prepare_weekly_availability(data)
        incoming = prepared.rename(
            columns={
                "공정": "process_name",
                "Weeknum": "weeknum",
                "가용대수": "available_count",
            }
        )
        view_name = f"_incoming_{uuid4().hex}"
        with self._write_transaction() as connection:
            connection.register(view_name, incoming)
            try:
                connection.execute(
                    f"""
                    DELETE FROM equipment_ops.standard_target_weekly_availability AS target
                    USING {view_name} AS incoming
                    WHERE target.process_name = incoming.process_name
                      AND target.weeknum = incoming.weeknum
                    """
                )
                connection.execute(
                    f"""
                    INSERT INTO equipment_ops.standard_target_weekly_availability (
                        process_name, weeknum, available_count
                    )
                    SELECT process_name, weeknum, available_count
                    FROM {view_name}
                    """
                )
            finally:
                connection.unregister(view_name)
        return self.load_standard_target_availability()

    def load_standard_target_availability(self) -> pd.DataFrame:
        """Load the current non-versioned process-week availability."""
        with self._connect(read_only=True) as connection:
            result = connection.execute(
                """
                SELECT process_name AS "공정", weeknum AS "Weeknum",
                       available_count AS "가용대수"
                FROM equipment_ops.standard_target_weekly_availability
                ORDER BY process_name, weeknum
                """
            ).fetchdf()
        if result.empty:
            return pd.DataFrame(columns=["공정", "Weeknum", "가용대수"])
        return prepare_weekly_availability(result)

    def clear_standard_target_availability(self) -> None:
        """Delete the current weekly availability without creating a revision."""
        with self._write_transaction() as connection:
            connection.execute("DELETE FROM equipment_ops.standard_target_weekly_availability")

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


def _load_baseline(connection: duckdb.DuckDBPyConnection, revision_id: str) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT process_name AS "공정", classification AS "분류",
               base_count AS "기존보유대수", note AS "비고"
        FROM equipment_ops.baseline_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()


def _load_equipment_master(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT equipment_id AS "호기", process_large AS "공정대분류",
               process_small AS "공정소분류", line_type AS "라인구분",
               utilization_type AS "활용구분", business_unit AS "사업부",
               investment_basis AS "투자기준", maker AS "Maker",
               model_name AS "모델", classification_1 AS "분류1",
               classification_2 AS "분류2", classification_3 AS "분류3",
               building AS "동", floor_name AS "층",
               x_coordinate AS "X좌표", y_coordinate AS "Y좌표",
               x_size AS "Xsize", y_size AS "Ysize",
               vibration_table_date AS "제진대일정",
               logistics_date AS "물류일정", arrival_date AS "입고일정",
               qual_date AS "Qual일정",
               qual_confirmation_status AS "확정상태",
               removal_date AS "반출일정",
               relocation_date AS "이설일",
               long_term_storage_flag AS "장기보관여부",
               existing_equipment_flag AS "기존설비여부",
               equipment_history AS "호기이력", note AS "비고",
               layout_display_flag AS "레이아웃표시"
        FROM equipment_ops.equipment_master_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()


def _load_legacy_equipment(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    legacy = connection.execute(
        """
        SELECT equipment_id AS "호기", process_name AS "공정",
               classification AS "분류", building AS "동", floor_name AS "층",
               x_coordinate AS "X", y_coordinate AS "Y", width_value AS "너비",
               infrastructure_complete_date AS "사전인프라완료일",
               arrival_date AS "입고일", hookup_complete_date AS "Hookup완료일",
               hardware_setup_complete_date AS "하드웨어셋업완료일",
               qual_complete_date AS "Qual완료일", tttm_complete_date AS "TTTM완료일",
               production_transition_date AS "양산전환일", note AS "비고"
        FROM equipment_ops.equipment_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    if legacy.empty:
        return empty_equipment_master()
    return _convert_legacy_equipment(legacy)


def _load_legacy_schedule(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    legacy = connection.execute(
        """
        SELECT equipment_id AS "호기", process_name AS "공정",
               classification AS "분류", arrival_date AS "입고일",
               setup_start_date AS "하드웨어셋업완료일",
               setup_complete_date AS "양산전환일", note AS "비고"
        FROM equipment_ops.schedule_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    if legacy.empty:
        return empty_equipment_master()
    return _convert_legacy_equipment(legacy)


def _load_downtime_schedule(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT equipment_id AS "호기", downtime_type AS "비가동유형",
               start_date AS "시작일", end_date AS "종료일",
               detail AS "상세사유", note AS "비고"
        FROM equipment_ops.downtime_schedule_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()


def _load_legacy_downtime(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> pd.DataFrame:
    legacy = connection.execute(
        """
        SELECT equipment_id AS "호기", downtime_type AS "비가동유형", start_date AS "시작일",
               end_date AS "종료일", detail AS "상세사유", note AS "비고"
        FROM equipment_ops.downtime_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    return legacy.drop_duplicates(["호기", "비가동유형", "시작일"], keep="last")


def _convert_legacy_equipment(legacy: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=legacy.index, columns=EQUIPMENT_COLUMNS)
    result["호기"] = legacy["호기"]
    result["공정대분류"] = legacy["공정"]
    result["공정소분류"] = legacy["공정"]
    result["분류1"] = legacy["분류"]
    result["동"] = legacy.get("동")
    result["층"] = legacy.get("층")
    result["X좌표"] = legacy.get("X")
    result["Y좌표"] = legacy.get("Y")
    result["Xsize"] = legacy.get("너비")
    has_coordinates = result[["X좌표", "Y좌표", "Xsize"]].notna().all(axis=1)
    result["Ysize"] = has_coordinates.map({True: 7.0, False: None})
    legacy_qual = legacy.get("양산전환일")
    legacy_arrival = legacy.get("입고일")
    if isinstance(legacy_arrival, pd.Series) and isinstance(legacy_qual, pd.Series):
        result["입고일정"] = legacy_arrival.fillna(legacy_qual)
    else:
        result["입고일정"] = legacy_arrival
    if isinstance(legacy_qual, pd.Series):
        result["Qual일정"] = legacy_qual.fillna(pd.Timestamp("2262-04-11"))
    else:
        result["Qual일정"] = pd.Timestamp("2262-04-11")
    result["장기보관여부"] = "N"
    has_legacy_schedule = result["입고일정"].notna()
    result["기존설비여부"] = has_legacy_schedule.map({True: "N", False: "Y"})
    result["확정상태"] = has_legacy_schedule.map({True: "계획", False: None})
    result["비고"] = legacy.get("비고")
    result["레이아웃표시"] = has_coordinates.map({True: "Y", False: "N"})
    return result


def _insert_baseline(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    incoming = frame.rename(
        columns={
            "공정": "process_name",
            "분류": "classification",
            "기존보유대수": "base_count",
            "비고": "note",
        }
    )
    _insert_snapshot(connection, "equipment_ops.baseline_snapshot", revision_id, incoming)


def _insert_equipment(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    incoming = frame.rename(
        columns={
            "호기": "equipment_id",
            "공정대분류": "process_large",
            "공정소분류": "process_small",
            "라인구분": "line_type",
            "활용구분": "utilization_type",
            "사업부": "business_unit",
            "투자기준": "investment_basis",
            "Maker": "maker",
            "모델": "model_name",
            "분류1": "classification_1",
            "분류2": "classification_2",
            "분류3": "classification_3",
            "동": "building",
            "층": "floor_name",
            "X좌표": "x_coordinate",
            "Y좌표": "y_coordinate",
            "Xsize": "x_size",
            "Ysize": "y_size",
            "제진대일정": "vibration_table_date",
            "물류일정": "logistics_date",
            "입고일정": "arrival_date",
            "Qual일정": "qual_date",
            "확정상태": "qual_confirmation_status",
            "반출일정": "removal_date",
            "이설일": "relocation_date",
            "장기보관여부": "long_term_storage_flag",
            "기존설비여부": "existing_equipment_flag",
            "호기이력": "equipment_history",
            "비고": "note",
            "레이아웃표시": "layout_display_flag",
        }
    )
    _insert_snapshot(
        connection,
        "equipment_ops.equipment_master_snapshot",
        revision_id,
        incoming,
    )


def _insert_downtime(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    incoming = frame.rename(
        columns={
            "호기": "equipment_id",
            "비가동유형": "downtime_type",
            "시작일": "start_date",
            "종료일": "end_date",
            "상세사유": "detail",
            "비고": "note",
        }
    )
    _insert_snapshot(
        connection,
        "equipment_ops.downtime_schedule_snapshot",
        revision_id,
        incoming,
    )


def _insert_snapshot(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        return
    incoming = frame.copy()
    incoming.insert(0, "source_row_no", range(1, len(incoming) + 1))
    incoming.insert(0, "revision_id", revision_id)
    view_name = f"_incoming_{uuid4().hex}"
    connection.register(view_name, incoming)
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
    created_at = row[6]
    if not isinstance(created_at, datetime):
        raise TypeError("DuckDB 설비 이력 시각이 datetime이 아닙니다.")
    return EquipmentRevisionSummary(
        revision_id=str(row[0]),
        revision_no=_as_int(row[1], "리비전 번호"),
        note=str(row[2]) if row[2] is not None else None,
        baseline_row_count=_as_int(row[3], "기존 보유대수 행 수"),
        equipment_row_count=_as_int(row[4], "호기 마스터 행 수"),
        downtime_row_count=_as_int(row[5], "비가동 일정 행 수"),
        created_at=created_at,
    )


def _as_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"DuckDB {label}가 정수가 아닙니다.")
    return value
