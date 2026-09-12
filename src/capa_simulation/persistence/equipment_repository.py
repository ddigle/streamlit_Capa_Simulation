# Purpose: Immutable DuckDB snapshots for unified equipment operations input.

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

from capa_simulation.persistence import sync_state
from capa_simulation.persistence._sql_helpers import as_datetime, connect
from capa_simulation.persistence.equipment_migration_runner import apply_equipment_migrations
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_equipment_master,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.floor_layout_profile import (
    CanvasSize,
    FloorKey,
    FloorLayoutCanvas,
    FloorLayoutProfile,
    canvas_from_pixel_size,
    image_pixel_size,
    normalize_canvas_size,
    normalize_image_upload,
    require_total_layout_budget,
    to_data_uri,
)
from capa_simulation.services.weekly_availability_input import prepare_weekly_availability

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


# 리비전 요약 한 줄을 만드는 투영. 계약 버전 3 을 기준으로 표가 갈려 CASE 가 길고, 두 조회
# (스냅샷 하나 · 목록)가 **같은 열 순서**로 읽어야 모델 생성이 맞는다.
_REVISION_SUMMARY_PROJECTION = """
                r.revision_id, r.revision_no, r.note,
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
"""


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
        # 저장 시점에만 층 캔버스 상한을 강제한다. 과거 리비전을 다시 읽을 때는 캔버스를
        # 넘기지 않아, 도면 비율을 줄여도 이미 저장된 리비전이 계속 열린다.
        prepared_equipment = prepare_equipment_master(
            equipment, floor_canvases=self.load_floor_layout_canvases()
        )
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision_id FROM equipment_ops.revision ORDER BY revision_no DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def load_snapshot(self, revision_id: str) -> EquipmentSnapshot:
        with self._connect() as connection:
            revision_row = connection.execute(
                f"""
                SELECT {_REVISION_SUMMARY_PROJECTION}, r.equipment_contract_version
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
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {_REVISION_SUMMARY_PROJECTION}
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
        with self._connect() as connection:
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

    def save_floor_layout_image(
        self,
        building: str,
        floor: str,
        file_name: str,
        payload: bytes,
        *,
        canvas_width: float | None = None,
        canvas_height: float | None = None,
    ) -> FloorLayoutProfile:
        """Upsert one floor's background drawing without creating a revision."""
        _require_floor_key(building, floor)
        normalized_name, mime = normalize_image_upload(file_name, payload)
        if canvas_width is None or canvas_height is None:
            pixel_size = image_pixel_size(payload)
            if pixel_size is None:
                raise ValueError(f"도면 파일 형식을 읽지 못했습니다: {normalized_name}")
            width, height = canvas_from_pixel_size(*pixel_size)
        else:
            width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            require_total_layout_budget(
                _other_floors_layout_bytes(connection, building, floor), len(payload)
            )
            row_exists, stored_digest = _stored_image_digest(connection, building, floor)
            if not row_exists:
                _insert_floor_layout(
                    connection, building, floor, width, height, (mime, normalized_name, payload)
                )
            elif stored_digest == hashlib.sha256(payload).hexdigest():
                # 같은 도면을 다시 올렸다. BLOB 을 다시 쓰면 DuckDB 가 이전 페이지를
                # 회수하지 않아 파일만 커지므로 나머지 컬럼만 고친다.
                connection.execute(
                    """
                    UPDATE equipment_ops.floor_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        updated_at = current_timestamp
                    WHERE building = ? AND floor_name = ?
                    """,
                    [width, height, mime, normalized_name, building, floor],
                )
            else:
                connection.execute(
                    """
                    UPDATE equipment_ops.floor_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        image_payload = ?, updated_at = current_timestamp
                    WHERE building = ? AND floor_name = ?
                    """,
                    [width, height, mime, normalized_name, payload, building, floor],
                )
        return self._require_floor_layout_profile(building, floor)

    def save_floor_layout_canvas(
        self,
        building: str,
        floor: str,
        canvas_width: float,
        canvas_height: float,
    ) -> FloorLayoutProfile:
        """Upsert one floor's canvas size and keep the stored drawing as is."""
        _require_floor_key(building, floor)
        width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            # 행이 이미 있으면 숫자 두 개만 UPDATE 한다. DELETE+INSERT 로 행을 다시 쓰면
            # 도면 BLOB 이 통째로 다시 기록되고 DuckDB 는 지운 페이지를 회수하지 않는다.
            updated = connection.execute(
                """
                UPDATE equipment_ops.floor_layout_profile
                SET canvas_width = ?, canvas_height = ?, updated_at = current_timestamp
                WHERE building = ? AND floor_name = ?
                """,
                [width, height, building, floor],
            ).fetchone()
            if updated is None or int(updated[0]) == 0:
                _insert_floor_layout(connection, building, floor, width, height, None)
        return self._require_floor_layout_profile(building, floor)

    def delete_floor_layout_profile(self, building: str, floor: str) -> None:
        """Delete one floor's drawing and canvas without creating a revision."""
        _require_floor_key(building, floor)
        with self._write_transaction() as connection:
            connection.execute(
                """
                DELETE FROM equipment_ops.floor_layout_profile
                WHERE building = ? AND floor_name = ?
                """,
                [building, floor],
            )

    def load_floor_layout_summaries(self) -> tuple[FloorLayoutCanvas, ...]:
        """Load every floor's canvas size without reading the drawing bytes."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT building, floor_name, canvas_width, canvas_height, image_name,
                       COALESCE(octet_length(image_payload), 0), updated_at
                FROM equipment_ops.floor_layout_profile
                ORDER BY building, floor_name
                """
            ).fetchall()
        return tuple(
            FloorLayoutCanvas(
                building=str(row[0]),
                floor=str(row[1]),
                canvas_width=float(row[2]),
                canvas_height=float(row[3]),
                image_name=str(row[4]) if row[4] is not None else None,
                image_byte_count=int(row[5]),
                updated_at=as_datetime(row[6]),
            )
            for row in rows
        )

    def load_floor_layout_canvases(self) -> dict[FloorKey, CanvasSize]:
        """Map (동, 층) to its canvas size for coordinate validation."""
        return {
            (summary.building, summary.floor): summary.canvas_size
            for summary in self.load_floor_layout_summaries()
        }

    def load_floor_layout_profile(self, building: str, floor: str) -> FloorLayoutProfile | None:
        """Load one floor's canvas size and its drawing as a plotly data URI."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT canvas_width, canvas_height, image_mime, image_name, image_payload,
                       updated_at
                FROM equipment_ops.floor_layout_profile
                WHERE building = ? AND floor_name = ?
                """,
                [building, floor],
            ).fetchone()
        if row is None:
            return None
        payload = row[4]
        mime = str(row[2]) if row[2] is not None else None
        has_image = isinstance(payload, (bytes, bytearray)) and bool(payload) and mime is not None
        image_bytes = bytes(payload) if has_image else b""
        return FloorLayoutProfile(
            building=building,
            floor=floor,
            canvas_width=float(row[0]),
            canvas_height=float(row[1]),
            image_data_uri=to_data_uri(str(mime), image_bytes) if has_image else None,
            image_name=str(row[3]) if row[3] is not None else None,
            image_byte_count=len(image_bytes),
            updated_at=as_datetime(row[5]),
        )

    def _require_floor_layout_profile(self, building: str, floor: str) -> FloorLayoutProfile:
        profile = self.load_floor_layout_profile(building, floor)
        if profile is None:
            raise RuntimeError(f"층 도면 프로필을 저장하지 못했습니다: {building} {floor}")
        return profile

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
        # COMMIT 이 끝나고 연결이 닫힌 뒤에만 표시한다. `sync_state` 는 등록되지 않은
        # 환경에서 아무 파일도 만들지 않으므로 개발 PC·CI 동작은 그대로다.
        sync_state.mark_dirty(self._database_path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return connect(self._database_path)


def _require_floor_key(building: str, floor: str) -> None:
    if building not in VALID_BUILDINGS or floor not in VALID_FLOORS:
        raise ValueError(f"동은 C1~C5, 층은 1F~6F 범위여야 합니다: {building} {floor}")


def _stored_image_digest(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
) -> tuple[bool, str | None]:
    """(행이 있는지, 저장된 도면의 sha256) 을 돌려준다. BLOB 을 파이썬으로 읽지 않는다."""
    row = connection.execute(
        """
        SELECT sha256(image_payload)
        FROM equipment_ops.floor_layout_profile
        WHERE building = ? AND floor_name = ?
        """,
        [building, floor],
    ).fetchone()
    if row is None:
        return False, None
    return True, str(row[0]) if row[0] is not None else None


def _other_floors_layout_bytes(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
) -> int:
    """이 층을 뺀 나머지 층 도면의 바이트 합계."""
    row = connection.execute(
        """
        SELECT COALESCE(SUM(octet_length(image_payload)), 0)
        FROM equipment_ops.floor_layout_profile
        WHERE NOT (building = ? AND floor_name = ?)
        """,
        [building, floor],
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _insert_floor_layout(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
    canvas_width: float,
    canvas_height: float,
    image: tuple[str, str, bytes] | None,
) -> None:
    mime, name, payload = image if image is not None else (None, None, None)
    connection.execute(
        """
        INSERT INTO equipment_ops.floor_layout_profile (
            building, floor_name, canvas_width, canvas_height,
            image_mime, image_name, image_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [building, floor, canvas_width, canvas_height, mime, name, payload],
    )


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
               utilization_type AS "활용구분",
               investment_basis AS "투자기준", manager_name AS "담당자",
               maker AS "Maker",
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
            "투자기준": "investment_basis",
            "담당자": "manager_name",
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
