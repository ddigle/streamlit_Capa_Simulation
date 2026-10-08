# Purpose: Immutable DuckDB snapshots for unified equipment operations input.

"""Immutable DuckDB snapshots for unified equipment operations input."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.persistence import sync_state
from capa_simulation.persistence._sql_helpers import (
    as_datetime,
    as_int,
    connect,
    hash_frame,
    insert_by_name,
    transaction,
)
from capa_simulation.persistence.equipment_migration_runner import (
    SchemaAheadOfCode,
    apply_equipment_migrations,
)
from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    BASELINE_COLUMNS,
    DEFAULT_CONVERSION_RATIO,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    RELOCATION_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_equipment_master,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.fab_layout import (
    FAB_CANVAS,
    FAB_LAYOUT_KEY,
    FabLayoutBase,
    FabLayoutMark,
    FabLayoutProfile,
    fab_marks_fingerprint,
    prepare_fab_layout_marks,
    require_fab_layout_fits,
)
from capa_simulation.services.floor_layout_mark import (
    FloorLayoutMark,
    marks_extent,
    marks_fingerprint,
    prepare_floor_layout_marks,
)
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
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
from capa_simulation.services.korean_particle import with_object_particle
from capa_simulation.services.process_cutoff import (
    empty_process_cutoff,
    prepare_process_cutoff,
)
from capa_simulation.services.shortening_filter_profile import (
    ShorteningFilterProfile,
    merge_filter_processes,
    normalize_filter_month,
    normalize_filter_processes,
)
from capa_simulation.services.weekly_availability_input import prepare_weekly_availability

_WRITE_LOCK = threading.RLock()
# 저장본이 하나도 없을 때의 출발 리비전 표시. 편집본이 「빈 저장소에서 나왔다」는 뜻이다.
EMPTY_REVISION_TOKEN = "empty"
# 한 층 편집을 시작할 때 본 저장값: (저장된 캔버스 — 없으면 None, 저장된 도면 요소의 지문).
FloorLayoutBase = tuple[CanvasSize | None, str]


@dataclass
class _WriteOutcome:
    """쓰기 트랜잭션이 실제로 무엇을 썼는가. 아무것도 안 썼으면 동기화 dirty 표시를 하지 않는다."""

    wrote: bool = True


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


# 설비 마스터 계약(한글) ↔ `equipment_master_snapshot` 컬럼(영문). 읽기 별칭과 쓰기 이름이 모두
# 이 표 하나에서 나온다 — 화면 이름을 바꿔도 이 표의 왼쪽만 바꾸면 기존 리비전이 그대로 이어진다.
# DB 컬럼 이름은 옛 화면 이름에서 온 것이 많다(`line_type` = 공정구분, `classification_1` = 구분).
# `investment_basis`(옛 `투자기준`)는 계약에서 빠졌다. **값은 지우지 않고 읽지도 쓰지도 않는다**
# — 과거 리비전의 이력이라서다. 되살리지 않기로 확정했다(2026-10-07).
# `business_unit` 도 같은 처지다.
EQUIPMENT_MASTER_DB_COLUMNS: Mapping[str, str] = MappingProxyType(
    {
        "구분": "classification_1",
        "공정대분류": "process_large",
        "공정소분류": "process_small",
        "Maker": "maker",
        "Model": "model_name",
        EQUIPMENT_ID_COLUMN: "equipment_id",
        "공정구분": "line_type",
        "투자Capa": "investment_capa",
        "투자구분": "utilization_type",
        "사용기준": "classification_2",
        "동": "building",
        "층": "floor_name",
        "담당자": "manager_name",
        "설비가동현황": "classification_3",
        "X좌표": "x_coordinate",
        "Y좌표": "y_coordinate",
        "Xsize": "x_size",
        "Ysize": "y_size",
        "제진대일정": "vibration_table_date",
        "물류일정": "logistics_date",
        "반입일정": "arrival_date",
        "Qual일정": "qual_date",
        "확정상태": "qual_confirmation_status",
        "반출일정": "removal_date",
        RELOCATION_DATE_COLUMN: "relocation_date",
        "반입/Qual 이력": "arrival_qual_history",
        "호기이력": "equipment_history",
        "설비이력": "note",
        "보관유무": "long_term_storage_flag",
        "기존설비여부": "existing_equipment_flag",
        "레이아웃표시": "layout_display_flag",
        "환산비": "conversion_ratio",
        "Main 설비": "parent_equipment_id",
        "메모1": "memo_1",
        "메모2": "memo_2",
        "메모3": "memo_3",
    }
)

# 0008 이전 리비전은 환산비가 NULL 이다 — 기준 모델(1.0)로 읽는다.
# 반입·Qual 이 필수이던 때 옛 리비전 변환은 빈 Qual 을 먼 미래(`LEGACY_QUAL_PLACEHOLDER`)로
# 채웠고, 그 편집본을 다시 저장한 리비전에는 그 날짜가 남아 있다. 정확히 그 날만 빈 Qual 로
# 읽는다 — 상태는 같고(빈 Qual = 셋업 진행중) 일정 미정 알림에 잡힌다. 그 날짜는 그 변환만 만들었다.
LEGACY_QUAL_PLACEHOLDER = "2262-04-11"
_EQUIPMENT_MASTER_READ_EXPRESSIONS: Mapping[str, str] = MappingProxyType(
    {
        "conversion_ratio": f"COALESCE(conversion_ratio, {DEFAULT_CONVERSION_RATIO!r})",
        "qual_date": f"NULLIF(qual_date, DATE '{LEGACY_QUAL_PLACEHOLDER}')",
    }
)

_EQUIPMENT_MASTER_PROJECTION = ", ".join(
    f'{_EQUIPMENT_MASTER_READ_EXPRESSIONS.get(db_column, db_column)} AS "{column}"'
    for column, db_column in EQUIPMENT_MASTER_DB_COLUMNS.items()
)

DOWNTIME_DB_COLUMNS: Mapping[str, str] = MappingProxyType(
    {
        EQUIPMENT_ID_COLUMN: "equipment_id",
        "비가동유형": "downtime_type",
        "시작일": "start_date",
        "종료일": "end_date",
        "상세사유": "detail",
        "비고": "note",
    }
)

_DOWNTIME_PROJECTION = ", ".join(
    f'{db_column} AS "{column}"' for column, db_column in DOWNTIME_DB_COLUMNS.items()
)


class DuckDBEquipmentRepository:
    """Persist full equipment input snapshots without changing past revisions."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()
        self._schema_ahead: SchemaAheadOfCode | None = None

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def schema_ahead(self) -> SchemaAheadOfCode | None:
        """마지막 `initialize()` 가 본 「설비 DB 가 이 코드보다 새 것」. 아니면 None.

        저장소는 프로세스마다 한 번 만들어 캐시하므로(`equipment_cache`) 화면은 rerun 마다
        이 속성만 읽는다 — DB 를 다시 열지 않는다.
        """
        return self._schema_ahead

    def initialize(self) -> tuple[int, ...]:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, self._connect() as connection:
            outcome = apply_equipment_migrations(connection)
        self._schema_ahead = outcome.schema_ahead
        return outcome.applied

    def save_snapshot(
        self,
        baseline: pd.DataFrame,
        equipment: pd.DataFrame,
        downtime: pd.DataFrame,
        *,
        note: str | None = None,
        floor_canvases: Mapping[FloorKey, CanvasSize] | None = None,
        floor_marks: Mapping[FloorKey, Sequence[Mapping[str, object]]] | None = None,
        base_revision_id: str | None = None,
        floor_layout_bases: Mapping[FloorKey, FloorLayoutBase] | None = None,
    ) -> EquipmentSnapshot:
        """세 표를 새 리비전으로 저장한다.

        미저장 층 캔버스·도면 요소가 있으면 **같은 트랜잭션**에 함께 쓴다(호기는 넓힌 캔버스
        기준으로 검증된다). 캔버스·요소는 리비전이 아니라 층 현행값이다.

        `base_revision_id` 는 편집본이 나온 리비전(저장본이 없었으면 `EMPTY_REVISION_TOKEN`)이다.
        주면 쓰기 잠금 안에서 최신 리비전과 견줘, 그 사이 다른 사람이 저장했으면 거부한다 —
        옛 편집본이 남의 리비전을 조용히 되돌리지 않게. `floor_layout_bases` 는 층마다 편집을
        시작할 때 본 캔버스·요소 지문이고, 저장 직전 값과 다르면 같은 이유로 거부한다.
        """
        revision_id = self._save(
            baseline,
            equipment,
            downtime,
            note=note,
            floor_canvases=floor_canvases,
            floor_marks=floor_marks,
            base_revision_id=base_revision_id,
            floor_layout_bases=floor_layout_bases,
            skip_unchanged=False,
        )
        assert revision_id is not None
        return self.load_snapshot(revision_id)

    def save_space_layout(
        self,
        baseline: pd.DataFrame,
        equipment: pd.DataFrame,
        downtime: pd.DataFrame,
        *,
        note: str | None = None,
        floor_canvases: Mapping[FloorKey, CanvasSize] | None = None,
        floor_marks: Mapping[FloorKey, Sequence[Mapping[str, object]]] | None = None,
        base_revision_id: str | None = None,
        floor_layout_bases: Mapping[FloorKey, FloorLayoutBase] | None = None,
    ) -> EquipmentSnapshot | None:
        """`save_snapshot` 과 같되, 세 표가 최신 리비전과 같으면 **리비전을 만들지 않고**
        캔버스·도면 요소만 쓴다(Space 에서 요소만 고친 저장이 호기 마스터를 복제하지 않게).
        새 리비전을 만들었으면 그 스냅샷, 아니면 None."""
        revision_id = self._save(
            baseline,
            equipment,
            downtime,
            note=note,
            floor_canvases=floor_canvases,
            floor_marks=floor_marks,
            base_revision_id=base_revision_id,
            floor_layout_bases=floor_layout_bases,
            skip_unchanged=True,
        )
        return self.load_snapshot(revision_id) if revision_id is not None else None

    def _save(
        self,
        baseline: pd.DataFrame,
        equipment: pd.DataFrame,
        downtime: pd.DataFrame,
        *,
        note: str | None,
        floor_canvases: Mapping[FloorKey, CanvasSize] | None,
        floor_marks: Mapping[FloorKey, Sequence[Mapping[str, object]]] | None,
        base_revision_id: str | None,
        floor_layout_bases: Mapping[FloorKey, FloorLayoutBase] | None,
        skip_unchanged: bool,
    ) -> str | None:
        """검증·리비전·캔버스·요소를 **연결 하나, 트랜잭션 하나**에서 한다.

        캔버스를 따로 저장(`save_floor_layout_canvas`)한 뒤 `save_snapshot` 을 부르면 트랜잭션이
        둘로 갈려, 호기 검증이 실패해도 캔버스만 바뀐 채 남는다. 저장된 캔버스도 이 연결 안에서
        읽는다 — 밖에서 읽으면 그 사이에 다른 사람이 줄인 캔버스를 놓친다.
        """
        canvases: dict[FloorKey, CanvasSize] = {}
        for (building, floor), size in (floor_canvases or {}).items():
            _require_floor_key(building, floor)
            canvases[(building, floor)] = normalize_canvas_size(*size)
        for building, floor in floor_marks or {}:
            _require_floor_key(building, floor)
        prepared_baseline = prepare_equipment_baseline(baseline)
        normalized_note = note.strip() if note and note.strip() else None
        outcome = _WriteOutcome()
        with self._write_transaction(outcome) as connection:
            # 최신 리비전·저장된 캔버스·요소는 모두 **쓰기 잠금 안에서** 읽는다. 밖에서 읽으면
            # 그 사이 다른 세션의 저장을 놓쳐 옛 편집본이 그것을 되돌린다.
            latest = _latest_revision(connection)
            if base_revision_id is not None:
                current = latest[0] if latest is not None else EMPTY_REVISION_TOKEN
                if current != base_revision_id:
                    newest = f"r{latest[1]}" if latest is not None else "다른 저장"
                    raise ValueError(
                        f"다른 사용자가 먼저 {with_object_particle(newest)} 저장해 저장하지 "
                        "않았습니다. 화면을 다시 불러와 최신 저장본 위에서 고친 뒤 저장하세요."
                    )
            stored_canvases = _stored_floor_canvases(connection)
            _require_floor_layout_bases(
                connection,
                stored_canvases,
                floor_layout_bases or {},
                changed={*canvases, *(floor_marks or {})},
            )
            # 저장 시점에만 층 캔버스 상한을 강제한다. 과거 리비전을 다시 읽을 때는 캔버스를
            # 넘기지 않아, 도면 비율을 줄여도 이미 저장된 리비전이 계속 열린다.
            merged = {**stored_canvases, **canvases}
            prepared_equipment = prepare_equipment_master(equipment, floor_canvases=merged)
            prepared_downtime = prepare_downtime_for_prepared_equipment(
                downtime, prepared_equipment
            )
            default_canvas = (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
            prepared_marks = {
                key: prepare_floor_layout_marks(marks, merged.get(key, default_canvas))
                for key, marks in (floor_marks or {}).items()
            }
            # 캔버스만 바꾸는 층의 **저장된** 요소도 새 캔버스 안이어야 한다.
            for key, size in canvases.items():
                if key not in prepared_marks:
                    _require_marks_fit(connection, key, size)
            hashes = (
                hash_frame(prepared_baseline),
                hash_frame(prepared_equipment),
                hash_frame(prepared_downtime),
            )
            content = (
                _content_hash(prepared_baseline),
                _content_hash(prepared_equipment),
                _content_hash(prepared_downtime),
            )
            # 「세 표가 그대로인가」는 저장 당시 감사 해시가 아니라 **최신 리비전을 다시 정규화한
            # 값**과 내용 해시(`_content_hash`)로 견준다. 감사 해시는 입력의 형(정수 좌표 …)까지
            # 타서, 읽어 온 편집본을 다시 정규화한 값과 늘 달라 「바뀌었다」가 된다. 저장본이
            # 없으면 빈 세 표가 「그대로」다(요소만 저장하면서 빈 r1 을 만들지 않게).
            unchanged = False
            if skip_unchanged:
                if latest is None:
                    unchanged = all(
                        frame.empty
                        for frame in (prepared_baseline, prepared_equipment, prepared_downtime)
                    )
                else:
                    unchanged = _content_hashes(_read_snapshot(connection, latest[0])) == content
            revision_id: str | None = None
            if not unchanged:
                revision_id = _insert_revision(
                    connection,
                    note=normalized_note,
                    hashes=hashes,
                    frames=(prepared_baseline, prepared_equipment, prepared_downtime),
                )
            for (building, floor), (width, height) in canvases.items():
                _upsert_floor_canvas(connection, building, floor, width, height)
            for (building, floor), marks in prepared_marks.items():
                _replace_floor_marks(connection, building, floor, marks)
            outcome.wrote = revision_id is not None or bool(canvases) or bool(prepared_marks)
        return revision_id

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
            return _read_snapshot(connection, revision_id)

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

    def save_process_cutoff(self, data: pd.DataFrame) -> pd.DataFrame:
        """공정별 Cut-off 를 **통째로 갈아 끼운다.** 리비전을 만들지 않는다.

        0005 의 주차별 가용대수는 들어온 키만 지우고 다시 넣는 부분 upsert 인데, 여기는
        전체 삭제 후 삽입이다. **이 표는 목록 자체가 계약**이기 때문이다 — 행을 지우는
        것이 「그 공정을 산출에서 빼라」는 뜻이라 부분 upsert 로는 그 편집을 표현할
        방법이 없다.
        """
        prepared = prepare_process_cutoff(data)
        incoming = prepared.rename(
            columns={
                "공정": "process_name",
                "제품구분": "product_scope",
                "Cutoff일수": "cutoff_days",
                "비고": "note",
            }
        )
        with self._write_transaction() as connection:
            connection.execute("DELETE FROM equipment_ops.process_cutoff")
            if not incoming.empty:
                insert_by_name(
                    connection,
                    schema="equipment_ops",
                    table_name="process_cutoff",
                    frame=incoming,
                )
        return self.load_process_cutoff()

    def load_process_cutoff(self) -> pd.DataFrame:
        """저장된 공정별 Cut-off. 한 번도 저장하지 않았으면 빈 계약 프레임."""
        with self._connect() as connection:
            result = connection.execute(
                """
                SELECT process_name AS "공정", product_scope AS "제품구분",
                       cutoff_days AS "Cutoff일수", note AS "비고"
                FROM equipment_ops.process_cutoff
                ORDER BY process_name, product_scope
                """
            ).fetchdf()
        if result.empty:
            return empty_process_cutoff()
        return prepare_process_cutoff(result)

    def load_shortening_filter_profile(self) -> ShorteningFilterProfile:
        """필요단축일정 공용 조회 조건(0019). 한 번도 저장하지 않았으면 `version` 0 의 빈 값."""
        with self._connect() as connection:
            return _read_shortening_filter(connection)

    def save_shortening_filter_months(
        self, start_month: object, end_month: object, *, source: str
    ) -> bool:
        """공용 조회 조건의 **기간만** 갈아 쓴다. 공정은 그대로다. 썼으면 True.

        Cut-off 처럼 리비전 없는 현행값이라 그 자리에서 고친다. 저장된 값과 같으면 쓰지 않는다 —
        공용 행이라 쓸 때마다 `version` 이 오르고 DB 가 dirty 가 된다. 견주기와 쓰기를 한
        트랜잭션에서 한다(콜백 하나에 연결 하나).
        """
        start, end = normalize_filter_month(start_month), normalize_filter_month(end_month)
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            current = _read_shortening_filter(connection)
            if (current.start_month, current.end_month) == (start, end):
                return False
            _write_shortening_filter_header(connection, current, start, end, source)
            outcome.wrote = True
        return True

    def save_shortening_filter_processes(
        self, selected: Sequence[object], *, visible: Sequence[str], source: str
    ) -> bool:
        """공용 조회 조건의 **공정만** 갈아 쓴다. 기간은 그대로다. 썼으면 True.

        `visible` 은 화면이 보여 준 선택지다 — 그 밖의 저장 공정은 남긴다
        (`services/shortening_filter_profile.merge_filter_processes`). 같으면 쓰지 않는다.
        """
        visible_set = set(normalize_filter_processes(visible))
        outcome = _WriteOutcome(wrote=False)
        with self._write_transaction(outcome) as connection:
            current = _read_shortening_filter(connection)
            merged = merge_filter_processes(current.processes, selected, visible_set)
            if merged == current.processes:
                return False
            _write_shortening_filter_header(
                connection, current, current.start_month, current.end_month, source
            )
            connection.execute(
                "DELETE FROM equipment_ops.shortening_filter_process WHERE profile_id = 1"
            )
            if merged:
                insert_by_name(
                    connection,
                    schema="equipment_ops",
                    table_name="shortening_filter_process",
                    frame=pd.DataFrame(
                        {
                            "profile_id": 1,
                            "process_name": list(merged),
                            "sort_order": range(len(merged)),
                        }
                    ),
                )
            outcome.wrote = True
        return True

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
            _require_marks_fit(connection, (building, floor), (width, height))
            require_total_layout_budget(
                _floor_layout_bytes(connection, excluding=(building, floor))
                + _fab_layout_bytes(connection),
                len(payload),
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
            _require_marks_fit(connection, (building, floor), (width, height))
            _upsert_floor_canvas(connection, building, floor, width, height)
        return self._require_floor_layout_profile(building, floor)

    def load_floor_layout_marks(self, building: str, floor: str) -> tuple[FloorLayoutMark, ...]:
        """한 층의 도면 요소를 그리는 순서(`source_row_no`)대로 읽는다."""
        with self._connect() as connection:
            return _stored_floor_marks(connection, building, floor)

    def replace_floor_layout_marks(
        self,
        building: str,
        floor: str,
        marks: Sequence[Mapping[str, object]],
    ) -> tuple[FloorLayoutMark, ...]:
        """한 층의 도면 요소를 통째로 갈아 끼운다. 리비전을 만들지 않는다. 빈 목록은 모두 지운다."""
        _require_floor_key(building, floor)
        with self._write_transaction() as connection:
            stored = _stored_floor_canvases(connection)
            canvas = stored.get((building, floor), (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT))
            _replace_floor_marks(
                connection, building, floor, prepare_floor_layout_marks(marks, canvas)
            )
        return self.load_floor_layout_marks(building, floor)

    def delete_floor_layout_profile(self, building: str, floor: str) -> None:
        """층 배경 도면과 캔버스를 지운다(리비전 없음). 도면 요소는 남긴다 — 지우면 캔버스가 기본
        크기로 돌아가므로, 그 밖에 요소가 있으면 거부한다(요소가 캔버스 밖에 남으면 그 층 요소를
        다시 저장할 수 없다)."""
        _require_floor_key(building, floor)
        with self._write_transaction() as connection:
            _require_marks_fit(
                connection, (building, floor), (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
            )
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

    def load_fab_layout_profile(self) -> FabLayoutProfile | None:
        """FAB 전체 도면의 캔버스와 배경 도면(data URI). 저장한 적이 없으면 None."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT canvas_width, canvas_height, image_mime, image_name, image_payload,
                       updated_at
                FROM equipment_ops.fab_layout_profile
                WHERE layout_key = ?
                """,
                [FAB_LAYOUT_KEY],
            ).fetchone()
        if row is None:
            return None
        payload = row[4]
        mime = str(row[2]) if row[2] is not None else None
        has_image = isinstance(payload, (bytes, bytearray)) and bool(payload) and mime is not None
        image_bytes = bytes(payload) if has_image else b""
        return FabLayoutProfile(
            canvas_width=float(row[0]),
            canvas_height=float(row[1]),
            image_data_uri=to_data_uri(str(mime), image_bytes) if has_image else None,
            image_name=str(row[3]) if row[3] is not None else None,
            image_byte_count=len(image_bytes),
            updated_at=as_datetime(row[5]),
        )

    def load_fab_layout_marks(self) -> tuple[FabLayoutMark, ...]:
        """저장된 FAB 요소(그리는 순서대로). 하나도 없으면 빈 튜플 — 화면은 기본 배치를 그린다."""
        with self._connect() as connection:
            return _stored_fab_marks(connection)

    def save_fab_layout(
        self,
        *,
        canvas: CanvasSize | None,
        marks: Sequence[Mapping[str, object]] | None,
        base: FabLayoutBase | None,
    ) -> bool:
        """FAB 캔버스·요소를 쓴다. **설비 리비전을 만들지 않는다**(층 도면 요소처럼 현행값이다).

        `base` 는 편집을 시작할 때 본 저장값(캔버스|None, 요소 지문)이다. 쓰기 잠금 안에서 지금
        저장값과 견줘 다르면 거부한다 — 요소는 전체 교체라 옛 목록으로 덮으면 남이 먼저 저장한 FAB
        가 지워진다. 캔버스 행이 없으면(처음 저장) 그 행도 함께 쓴다. 쓴 것이 있으면 True."""
        size = normalize_canvas_size(*canvas) if canvas is not None else None
        if size is None and marks is None:
            return False
        with self._write_transaction() as connection:
            stored_canvas = _stored_fab_canvas(connection)
            if base is not None:
                _require_fab_layout_base(connection, stored_canvas, base)
            target = size or stored_canvas or FAB_CANVAS
            prepared: tuple[FabLayoutMark, ...] | None = None
            if marks is not None:
                prepared = prepare_fab_layout_marks(marks, target)
                # 빈 목록이면 기본 배치를 그린다 — 그 기본 배치도 캔버스 안이어야 한다.
                require_fab_layout_fits(target, prepared)
            else:
                # 캔버스만 바꾼다 — 지금 그리는 요소(저장된 것, 없으면 기본 배치)가 새 캔버스
                # 안이어야 한다.
                _require_fab_marks_fit(connection, target)
            if size is not None or stored_canvas is None:
                _upsert_fab_canvas(connection, *target)
            if prepared is not None:
                _replace_fab_marks(connection, prepared)
        return True

    def save_fab_layout_image(
        self,
        file_name: str,
        payload: bytes,
        *,
        canvas_width: float | None = None,
        canvas_height: float | None = None,
    ) -> FabLayoutProfile:
        """FAB 배경 도면을 올린다(리비전 없음). 층 도면과 같은 용량 규칙이고 합계는 전 층과 함께
        센다."""
        normalized_name, mime = normalize_image_upload(file_name, payload)
        if canvas_width is None or canvas_height is None:
            pixel_size = image_pixel_size(payload)
            if pixel_size is None:
                raise ValueError(f"도면 파일 형식을 읽지 못했습니다: {normalized_name}")
            width, height = canvas_from_pixel_size(*pixel_size)
        else:
            width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            _require_fab_marks_fit(connection, (width, height))
            require_total_layout_budget(
                _floor_layout_bytes(connection), len(payload), subject="FAB 도면"
            )
            row = connection.execute(
                "SELECT sha256(image_payload) FROM equipment_ops.fab_layout_profile "
                "WHERE layout_key = ?",
                [FAB_LAYOUT_KEY],
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO equipment_ops.fab_layout_profile (
                        layout_key, canvas_width, canvas_height, image_mime, image_name,
                        image_payload
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [FAB_LAYOUT_KEY, width, height, mime, normalized_name, payload],
                )
            elif row[0] is not None and str(row[0]) == hashlib.sha256(payload).hexdigest():
                # 같은 도면을 다시 올렸다. BLOB 을 다시 쓰지 않는다(DuckDB 가 옛 페이지를 회수하지
                # 않는다).
                connection.execute(
                    """
                    UPDATE equipment_ops.fab_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        updated_at = current_timestamp
                    WHERE layout_key = ?
                    """,
                    [width, height, mime, normalized_name, FAB_LAYOUT_KEY],
                )
            else:
                connection.execute(
                    """
                    UPDATE equipment_ops.fab_layout_profile
                    SET canvas_width = ?, canvas_height = ?, image_mime = ?, image_name = ?,
                        image_payload = ?, updated_at = current_timestamp
                    WHERE layout_key = ?
                    """,
                    [width, height, mime, normalized_name, payload, FAB_LAYOUT_KEY],
                )
        return self._require_fab_layout_profile()

    def save_fab_layout_canvas(self, canvas_width: float, canvas_height: float) -> FabLayoutProfile:
        """FAB 캔버스 치수만 저장한다(도면은 그대로). 지금 그리는 요소가 새 캔버스 안이어야 한다."""
        width, height = normalize_canvas_size(canvas_width, canvas_height)
        with self._write_transaction() as connection:
            _require_fab_marks_fit(connection, (width, height))
            _upsert_fab_canvas(connection, width, height)
        return self._require_fab_layout_profile()

    def delete_fab_layout_profile(self) -> None:
        """FAB 배경 도면과 캔버스를 지운다(리비전 없음). 캔버스는 기본 `FAB_CANVAS` 로 돌아가고
        요소는 남는다 — 그 밖에 요소가 있으면 거부한다."""
        with self._write_transaction() as connection:
            _require_fab_marks_fit(connection, FAB_CANVAS)
            connection.execute(
                "DELETE FROM equipment_ops.fab_layout_profile WHERE layout_key = ?",
                [FAB_LAYOUT_KEY],
            )

    def _require_fab_layout_profile(self) -> FabLayoutProfile:
        profile = self.load_fab_layout_profile()
        if profile is None:
            raise RuntimeError("FAB 도면 프로필을 저장하지 못했습니다.")
        return profile

    def _require_floor_layout_profile(self, building: str, floor: str) -> FloorLayoutProfile:
        profile = self.load_floor_layout_profile(building, floor)
        if profile is None:
            raise RuntimeError(f"층 도면 프로필을 저장하지 못했습니다: {building} {floor}")
        return profile

    @contextmanager
    def _write_transaction(
        self, outcome: _WriteOutcome | None = None
    ) -> Iterator[duckdb.DuckDBPyConnection]:
        with _WRITE_LOCK, self._connect() as connection, transaction(connection):
            yield connection
        # COMMIT 이 끝나고 연결이 닫힌 뒤에만 표시한다. `sync_state` 는 등록되지 않은
        # 환경에서 아무 파일도 만들지 않으므로 개발 PC·CI 동작은 그대로다. 아무것도 쓰지 않은
        # 저장은 표시하지 않는다 — dirty 가 서면 다른 PC 의 새 세대를 받지 못한다.
        if outcome is None or outcome.wrote:
            sync_state.mark_dirty(self._database_path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return connect(self._database_path)


def _require_floor_key(building: str, floor: str) -> None:
    if building not in VALID_BUILDINGS or floor not in VALID_FLOORS:
        raise ValueError(f"동은 C1~C5, 층은 1F~6F 범위여야 합니다: {building} {floor}")


def _read_shortening_filter(connection: duckdb.DuckDBPyConnection) -> ShorteningFilterProfile:
    """열린 연결에서 필요단축일정 공용 조회 조건을 읽는다. 헤더가 없으면 빈 값(`version` 0)."""
    header = connection.execute(
        """
        SELECT start_month, end_month, version, source, updated_at
        FROM equipment_ops.shortening_filter_profile
        WHERE profile_id = 1
        """
    ).fetchone()
    if header is None:
        return ShorteningFilterProfile()
    processes = connection.execute(
        """
        SELECT process_name
        FROM equipment_ops.shortening_filter_process
        WHERE profile_id = 1
        ORDER BY sort_order, process_name
        """
    ).fetchall()
    return ShorteningFilterProfile(
        start_month=None if header[0] is None else int(header[0]),
        end_month=None if header[1] is None else int(header[1]),
        processes=tuple(str(row[0]) for row in processes),
        version=int(header[2]),
        source=str(header[3]),
        updated_at=header[4],
    )


def _write_shortening_filter_header(
    connection: duckdb.DuckDBPyConnection,
    current: ShorteningFilterProfile,
    start_month: int | None,
    end_month: int | None,
    source: str,
) -> None:
    """헤더 한 행을 다음 `version` 으로 쓴다. 쓰기 트랜잭션 안에서만 부른다.

    행이 있으면 키가 아닌 칸만 UPDATE 하고 없으면 넣는다 — 공정 자식 행은 건드리지 않는다.
    """
    values = [start_month, end_month, current.version + 1, source]
    if current.version == 0:
        connection.execute(
            """
            INSERT INTO equipment_ops.shortening_filter_profile (
                profile_id, start_month, end_month, version, source
            ) VALUES (1, ?, ?, ?, ?)
            """,
            values,
        )
        return
    connection.execute(
        """
        UPDATE equipment_ops.shortening_filter_profile
        SET start_month = ?, end_month = ?, version = ?, source = ?,
            updated_at = current_timestamp
        WHERE profile_id = 1
        """,
        values,
    )


def _latest_revision(connection: duckdb.DuckDBPyConnection) -> tuple[str, int] | None:
    """(최신 리비전 id, 번호). 리비전이 없으면 None."""
    row = connection.execute(
        """
        SELECT revision_id, revision_no FROM equipment_ops.revision
        ORDER BY revision_no DESC LIMIT 1
        """
    ).fetchone()
    return (str(row[0]), int(row[1])) if row is not None else None


def _read_snapshot(connection: duckdb.DuckDBPyConnection, revision_id: str) -> EquipmentSnapshot:
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


def _content_hashes(snapshot: EquipmentSnapshot) -> tuple[str, str, str]:
    """저장본을 다시 정규화한 세 표의 내용 해시. 저장 후보의 `_content_hash` 와 견준다."""
    equipment = prepare_equipment_master(snapshot.equipment)
    return (
        _content_hash(prepare_equipment_baseline(snapshot.baseline)),
        _content_hash(equipment),
        _content_hash(prepare_downtime_for_prepared_equipment(snapshot.downtime, equipment)),
    )


def _require_floor_layout_bases(
    connection: duckdb.DuckDBPyConnection,
    stored_canvases: Mapping[FloorKey, CanvasSize],
    bases: Mapping[FloorKey, FloorLayoutBase],
    *,
    changed: set[FloorKey],
) -> None:
    """바꾸려는 층의 캔버스·요소가 편집을 시작할 때 본 값 그대로인가. 아니면 다른 사람이 먼저
    저장한 것이다 — 요소는 층 전체 교체라 옛 목록으로 덮으면 그 사람의 요소가 지워진다."""
    for key in sorted(changed & set(bases)):
        expected_canvas, expected_marks = bases[key]
        stored_canvas = stored_canvases.get(key)
        if stored_canvas is None or expected_canvas is None:
            same_canvas = stored_canvas is None and expected_canvas is None
        else:
            same_canvas = all(
                abs(a - b) < 1e-9 for a, b in zip(stored_canvas, expected_canvas, strict=True)
            )
        same_marks = marks_fingerprint(_stored_floor_marks(connection, *key)) == expected_marks
        if not (same_canvas and same_marks):
            raise ValueError(
                f"{key[0]} {key[1]} 의 캔버스·도면 요소를 다른 사용자가 먼저 바꿔 저장하지 "
                "않았습니다. 저장 안 한 배치를 버리고 다시 고치세요."
            )


def _require_marks_fit(
    connection: duckdb.DuckDBPyConnection, key: FloorKey, canvas: CanvasSize
) -> None:
    """그 층의 **저장된** 도면 요소가 새 캔버스 안인가. 캔버스를 바꾸는 모든 길이 지킨다 —
    요소가 캔버스 밖에 남으면 그 층 요소를 다시 저장할 때 손대지 않은 요소 때문에 막힌다."""
    width, height = canvas
    right, top = marks_extent(_stored_floor_marks(connection, *key))
    if right > width + 1e-9 or top > height + 1e-9:
        raise ValueError(
            f"{key[0]} {key[1]} 캔버스 {width:g} × {height:g} 밖에 도면 요소가 있습니다(필요한 "
            f"크기 {right:g} × {top:g}). Space 편집기에서 요소를 옮기거나 캔버스를 넓히세요."
        )


def _content_hash(frame: pd.DataFrame) -> str:
    """값만 보는 해시. 모든 칸을 같은 글자 표기로 바꾼 뒤 잰다 — 같은 값이 정수로 들어왔는지
    DB 에서 실수로 읽혔는지, 날짜 단위가 ns 인지 us 인지로 「바뀌었다」고 하지 않게."""
    canonical = pd.DataFrame(index=range(len(frame)))
    for column in frame.columns:
        series = frame[column].reset_index(drop=True)
        if pd.api.types.is_bool_dtype(series):
            text = series.astype("string")
        elif pd.api.types.is_numeric_dtype(series):
            text = series.astype("float64").map(lambda value: "" if pd.isna(value) else repr(value))
        elif pd.api.types.is_datetime64_any_dtype(series):
            text = series.dt.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            text = series.astype("string")
        canonical[str(column)] = text.astype("string").fillna("")
    return hash_frame(canonical)


def _insert_revision(
    connection: duckdb.DuckDBPyConnection,
    *,
    note: str | None,
    hashes: tuple[str, str, str],
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> str:
    """검증을 마친 세 표를 새 리비전 하나로 넣고 그 id 를 돌려준다."""
    baseline_hash, equipment_hash, downtime_hash = hashes
    revision_id = str(uuid4())
    row = connection.execute(
        "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM equipment_ops.revision"
    ).fetchone()
    if row is None:
        raise RuntimeError("설비 이력 번호를 생성하지 못했습니다.")
    connection.execute(
        """
        INSERT INTO equipment_ops.revision (
            revision_id, revision_no, note, baseline_hash, schedule_hash,
            equipment_hash, downtime_hash, equipment_contract_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 3)
        """,
        [
            revision_id,
            int(row[0]),
            note,
            baseline_hash,
            equipment_hash,
            equipment_hash,
            downtime_hash,
        ],
    )
    _insert_baseline(connection, revision_id, frames[0])
    _insert_equipment(connection, revision_id, frames[1])
    _insert_downtime(connection, revision_id, frames[2])
    return revision_id


def _stored_floor_canvases(connection: duckdb.DuckDBPyConnection) -> dict[FloorKey, CanvasSize]:
    """저장된 층 캔버스. 도면 바이트는 읽지 않는다."""
    rows = connection.execute(
        "SELECT building, floor_name, canvas_width, canvas_height "
        "FROM equipment_ops.floor_layout_profile"
    ).fetchall()
    return {(str(row[0]), str(row[1])): (float(row[2]), float(row[3])) for row in rows}


def _upsert_floor_canvas(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
    width: float,
    height: float,
) -> None:
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


def _stored_floor_marks(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
) -> tuple[FloorLayoutMark, ...]:
    rows = connection.execute(
        """
        SELECT mark_id, mark_kind, x_coordinate, y_coordinate, x_size, y_size, rotation_deg,
               label, color_key, hatch, keep_out, font_size, font_color
        FROM equipment_ops.floor_layout_mark
        WHERE building = ? AND floor_name = ?
        ORDER BY source_row_no
        """,
        [building, floor],
    ).fetchall()
    return tuple(
        FloorLayoutMark(
            mark_id=str(row[0]),
            kind=str(row[1]),
            x=float(row[2]),
            y=float(row[3]),
            w=float(row[4]),
            h=float(row[5]),
            rotation=int(row[6]),
            label=str(row[7]) if row[7] is not None else "",
            color=str(row[8]) if row[8] is not None else "",
            hatch=bool(row[9]),
            keep_out=bool(row[10]),
            font_size=int(row[11]) if row[11] is not None else None,
            font_color=str(row[12]) if row[12] is not None else "",
        )
        for row in rows
    )


def _replace_floor_marks(
    connection: duckdb.DuckDBPyConnection,
    building: str,
    floor: str,
    marks: Sequence[FloorLayoutMark],
) -> None:
    """그 층 요소를 지우고 받은 순서대로 다시 넣는다(`source_row_no` 가 그리는 순서)."""
    connection.execute(
        "DELETE FROM equipment_ops.floor_layout_mark WHERE building = ? AND floor_name = ?",
        [building, floor],
    )
    if not marks:
        return
    frame = pd.DataFrame(
        [
            {
                "building": building,
                "floor_name": floor,
                "mark_id": mark.mark_id,
                "source_row_no": index,
                "mark_kind": mark.kind,
                "x_coordinate": mark.x,
                "y_coordinate": mark.y,
                "x_size": mark.w,
                "y_size": mark.h,
                "rotation_deg": mark.rotation,
                "label": mark.label or None,
                "color_key": mark.color or None,
                "hatch": mark.hatch,
                "keep_out": mark.keep_out,
                "font_size": mark.font_size,
                "font_color": mark.font_color or None,
            }
            for index, mark in enumerate(marks, start=1)
        ]
    )
    insert_by_name(
        connection,
        schema="equipment_ops",
        table_name="floor_layout_mark",
        frame=_with_font_size_type(frame),
    )


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


def _floor_layout_bytes(
    connection: duckdb.DuckDBPyConnection, *, excluding: FloorKey | None = None
) -> int:
    """층 도면의 바이트 합계(`excluding` 층은 뺀다 — 그 층 도면을 갈아 끼우는 중이다)."""
    building, floor = excluding if excluding is not None else ("", "")
    row = connection.execute(
        """
        SELECT COALESCE(SUM(octet_length(image_payload)), 0)
        FROM equipment_ops.floor_layout_profile
        WHERE NOT (building = ? AND floor_name = ?)
        """,
        [building, floor],
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _fab_layout_bytes(connection: duckdb.DuckDBPyConnection) -> int:
    """FAB 도면의 바이트. 층 도면을 올릴 때 30MB 합계에 함께 센다(FAB 를 올릴 때는 층 합계를
    센다)."""
    row = connection.execute(
        "SELECT COALESCE(SUM(octet_length(image_payload)), 0) FROM equipment_ops.fab_layout_profile"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _stored_fab_canvas(connection: duckdb.DuckDBPyConnection) -> CanvasSize | None:
    row = connection.execute(
        "SELECT canvas_width, canvas_height FROM equipment_ops.fab_layout_profile "
        "WHERE layout_key = ?",
        [FAB_LAYOUT_KEY],
    ).fetchone()
    return (float(row[0]), float(row[1])) if row is not None else None


def _stored_fab_marks(connection: duckdb.DuckDBPyConnection) -> tuple[FabLayoutMark, ...]:
    rows = connection.execute(
        """
        SELECT mark_id, mark_kind, x_coordinate, y_coordinate, x_size, y_size, rotation_deg,
               label, color_key, hatch, link_building, link_floor, font_size, font_color
        FROM equipment_ops.fab_layout_mark
        ORDER BY source_row_no
        """
    ).fetchall()
    return tuple(
        FabLayoutMark(
            mark_id=str(row[0]),
            kind=str(row[1]),
            x=float(row[2]),
            y=float(row[3]),
            w=float(row[4]),
            h=float(row[5]),
            rotation=int(row[6]),
            label=str(row[7]) if row[7] is not None else "",
            color=str(row[8]) if row[8] is not None else "",
            hatch=bool(row[9]),
            link=(str(row[10]), str(row[11]))
            if row[10] is not None and row[11] is not None
            else None,
            font_size=int(row[12]) if row[12] is not None else None,
            font_color=str(row[13]) if row[13] is not None else "",
        )
        for row in rows
    )


def _require_fab_layout_base(
    connection: duckdb.DuckDBPyConnection,
    stored_canvas: CanvasSize | None,
    base: FabLayoutBase,
) -> None:
    """FAB 캔버스·요소가 편집을 시작할 때 본 값 그대로인가. 아니면 다른 사람이 먼저 저장했다."""
    expected_canvas, expected_marks = base
    if stored_canvas is None or expected_canvas is None:
        same_canvas = stored_canvas is None and expected_canvas is None
    else:
        same_canvas = all(
            abs(a - b) < 1e-9 for a, b in zip(stored_canvas, expected_canvas, strict=True)
        )
    same_marks = fab_marks_fingerprint(_stored_fab_marks(connection)) == expected_marks
    if not (same_canvas and same_marks):
        raise ValueError(
            "S.PKG FAB 전체 배치를 다른 사용자가 먼저 바꿔 저장하지 않았습니다. 저장 안 한 FAB "
            "배치를 버리고 다시 고치세요."
        )


def _require_fab_marks_fit(connection: duckdb.DuckDBPyConnection, canvas: CanvasSize) -> None:
    """지금 그리는 FAB 요소(저장된 것, 하나도 없으면 기본 배치)가 새 캔버스 안인가."""
    require_fab_layout_fits(canvas, _stored_fab_marks(connection))


def _upsert_fab_canvas(connection: duckdb.DuckDBPyConnection, width: float, height: float) -> None:
    # 행이 있으면 숫자 두 개만 UPDATE 한다(도면 BLOB 을 다시 쓰지 않는다).
    updated = connection.execute(
        """
        UPDATE equipment_ops.fab_layout_profile
        SET canvas_width = ?, canvas_height = ?, updated_at = current_timestamp
        WHERE layout_key = ?
        """,
        [width, height, FAB_LAYOUT_KEY],
    ).fetchone()
    if updated is None or int(updated[0]) == 0:
        connection.execute(
            "INSERT INTO equipment_ops.fab_layout_profile (layout_key, canvas_width, "
            "canvas_height) VALUES (?, ?, ?)",
            [FAB_LAYOUT_KEY, width, height],
        )


def _replace_fab_marks(
    connection: duckdb.DuckDBPyConnection, marks: Sequence[FabLayoutMark]
) -> None:
    """FAB 요소를 모두 지우고 받은 순서대로 다시 넣는다(`source_row_no` 가 그리는 순서)."""
    connection.execute("DELETE FROM equipment_ops.fab_layout_mark")
    if not marks:
        return
    frame = pd.DataFrame(
        [
            {
                "mark_id": mark.mark_id,
                "source_row_no": index,
                "mark_kind": mark.kind,
                "x_coordinate": mark.x,
                "y_coordinate": mark.y,
                "x_size": mark.w,
                "y_size": mark.h,
                "rotation_deg": mark.rotation,
                "label": mark.label or None,
                "color_key": mark.color or None,
                "hatch": mark.hatch,
                "keep_out": False,
                "link_building": mark.link[0] if mark.link is not None else None,
                "link_floor": mark.link[1] if mark.link is not None else None,
                "font_size": mark.font_size,
                "font_color": mark.font_color or None,
            }
            for index, mark in enumerate(marks, start=1)
        ]
    )
    insert_by_name(
        connection,
        schema="equipment_ops",
        table_name="fab_layout_mark",
        frame=_with_font_size_type(frame),
    )


def _with_font_size_type(frame: pd.DataFrame) -> pd.DataFrame:
    """글자 크기 칸을 정수(빈 값 허용)로 맞춘다. 정수와 None 이 섞이면 pandas 가 실수(NaN)로,
    모두 None 이면 객체로 만든다 — 어느 쪽이든 INTEGER 칸에 넣기 전에 형을 고정한다."""
    return frame.assign(font_size=frame["font_size"].astype("Int64"))


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
        f"""
        SELECT {_EQUIPMENT_MASTER_PROJECTION}
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
        SELECT equipment_id AS "설비명", process_name AS "공정",
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
        SELECT equipment_id AS "설비명", process_name AS "공정",
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
        f"""
        SELECT {_DOWNTIME_PROJECTION}
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
        f"""
        SELECT {_DOWNTIME_PROJECTION}
        FROM equipment_ops.downtime_snapshot
        WHERE revision_id = ? ORDER BY source_row_no
        """,
        [revision_id],
    ).fetchdf()
    return legacy.drop_duplicates(list(DOWNTIME_KEY_COLUMNS), keep="last")


def _convert_legacy_equipment(legacy: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=legacy.index, columns=EQUIPMENT_COLUMNS)
    result[EQUIPMENT_ID_COLUMN] = legacy[EQUIPMENT_ID_COLUMN]
    result["공정대분류"] = legacy["공정"]
    result["공정소분류"] = legacy["공정"]
    result["구분"] = legacy["분류"]
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
        result[ARRIVAL_DATE_COLUMN] = legacy_arrival.fillna(legacy_qual)
    else:
        result[ARRIVAL_DATE_COLUMN] = legacy_arrival
    # 옛 양산전환일이 없으면 Qual일정도 비운다 — 신규 호기의 빈 Qual 은 「셋업 진행중」에 머문다.
    result["Qual일정"] = legacy_qual if isinstance(legacy_qual, pd.Series) else None
    result[STORAGE_FLAG_COLUMN] = "N"
    has_legacy_schedule = result[ARRIVAL_DATE_COLUMN].notna()
    result["기존설비여부"] = has_legacy_schedule.map({True: "N", False: "Y"})
    # 확정상태는 Qual 일정의 값이라 Qual일정이 있는 신규 호기에만 「계획」을 둔다.
    has_legacy_qual = has_legacy_schedule & result["Qual일정"].notna()
    result["확정상태"] = has_legacy_qual.map({True: "계획", False: None})
    result["설비이력"] = legacy.get("비고")
    result["레이아웃표시"] = has_coordinates.map({True: "Y", False: "N"})
    # 옛 리비전에는 모델별 생산성 구분이 없었다. 전부 기준 모델로 본다.
    result["환산비"] = DEFAULT_CONVERSION_RATIO
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
    _insert_snapshot(
        connection,
        schema="equipment_ops",
        table_name="baseline_snapshot",
        revision_id=revision_id,
        frame=incoming,
    )


def _insert_equipment(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    _insert_snapshot(
        connection,
        schema="equipment_ops",
        table_name="equipment_master_snapshot",
        revision_id=revision_id,
        frame=frame.rename(columns=dict(EQUIPMENT_MASTER_DB_COLUMNS)),
    )


def _insert_downtime(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    _insert_snapshot(
        connection,
        schema="equipment_ops",
        table_name="downtime_schedule_snapshot",
        revision_id=revision_id,
        frame=frame.rename(columns=dict(DOWNTIME_DB_COLUMNS)),
    )


def _insert_snapshot(
    connection: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table_name: str,
    revision_id: str,
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        return
    incoming = frame.copy()
    incoming.insert(0, "source_row_no", range(1, len(incoming) + 1))
    incoming.insert(0, "revision_id", revision_id)
    insert_by_name(connection, schema=schema, table_name=table_name, frame=incoming)


def _revision_summary(row: Sequence[object]) -> EquipmentRevisionSummary:
    return EquipmentRevisionSummary(
        revision_id=str(row[0]),
        revision_no=as_int(row[1], "리비전 번호"),
        note=str(row[2]) if row[2] is not None else None,
        baseline_row_count=as_int(row[3], "기존 보유대수 행 수"),
        equipment_row_count=as_int(row[4], "호기 마스터 행 수"),
        downtime_row_count=as_int(row[5], "비가동 일정 행 수"),
        created_at=as_datetime(row[6]),
    )
