"""Transactional DuckDB repository for scenario-owned reference snapshots."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.io.core_data_source import (
    build_source_column_profile,
    core_data_hash,
    core_data_row_hashes,
    core_data_schema_hash,
    load_core_data_contract,
    normalize_core_data,
)
from capa_simulation.persistence.migration_runner import apply_migrations
from capa_simulation.persistence.models import (
    GlobalDisplayOrder,
    OfficialReleaseSummary,
    RevisionSummary,
    ScenarioCreate,
    ScenarioPreset,
    ScenarioSnapshot,
    ScenarioSummary,
)

REFERENCE_TABLES: dict[str, str] = {
    "RQ_PKG_PLAN": "rq_pkg_plan",
    "RQ_YLD": "rq_yld",
    "RQ_CHIP_QTY": "rq_chip_qty",
    "RQ_CHIP_EQ": "rq_chip_eq",
    "RQ_DISPLAY_ORDER": "rq_display_order",
    "RQ_EQP_OWN": "rq_eqp_own",
    "RQ_EQP_LENT": "rq_eqp_lent",
    "RQ_EQP_AVBL": "rq_eqp_avbl",
    "RQ_UPEH": "rq_upeh",
    "RQ_RUN_RATE": "rq_run_rate",
    "RQ_VITAL": "rq_vital",
    "RQ_MODULE": "rq_module",
    "RQ_RUN_DAY": "rq_run_day",
    "RQ_LOT_RATIO": "rq_lot_ratio",
    "RQ_WF_RATIO": "rq_wf_ratio",
    "RQ_REQB": "rq_reqb",
}
REVISION_TABLES: dict[str, str] = {
    name: REFERENCE_TABLES[name]
    for name in (
        "RQ_PKG_PLAN",
        "RQ_YLD",
        "RQ_UPEH",
        "RQ_RUN_RATE",
        "RQ_VITAL",
        "RQ_RUN_DAY",
        "RQ_LOT_RATIO",
        "RQ_WF_RATIO",
        "RQ_REQB",
        "RQ_EQP_OWN",
        "RQ_EQP_LENT",
        "RQ_EQP_AVBL",
    )
}
GLOBAL_DISPLAY_ORDER_COLUMNS = (
    "페이지 구분",
    "탭 구분",
    "정렬우선순위",
    "분류컬럼",
    "정렬방식",
    "분류값",
    "값표시순서",
    "활성여부",
)

_WRITE_LOCK = threading.RLock()


class DuckDBScenarioRepository:
    """Persist immutable datasets and full editable-table revision snapshots."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def initialize(self) -> tuple[int, ...]:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, self._connect() as connection:
            return apply_migrations(connection)

    def initialize_global_display_order(
        self,
        fallback: pd.DataFrame,
    ) -> GlobalDisplayOrder:
        """Create the shared profile once, preferring an existing revision's rules."""
        _validate_global_display_order_frame(fallback)
        with self._write_transaction() as connection:
            existing = connection.execute(
                "SELECT profile_id FROM app_meta.global_display_order WHERE profile_id = 1"
            ).fetchone()
            if existing is None:
                migrated = _load_existing_display_order(connection)
                if migrated is None:
                    initial = fallback
                    source = "초기 표시순서 시드"
                else:
                    initial = migrated
                    source = "기존 시나리오 표시순서 이관"
                    if len(initial) < len(fallback):
                        initial = fallback
                        source = "초기 표시순서 시드"
                _insert_global_display_order(
                    connection,
                    initial,
                    version=1,
                    source=source,
                )
        return self.load_global_display_order()

    def load_global_display_order(self) -> GlobalDisplayOrder:
        """Load the scenario-independent display-order profile."""
        with self._connect(read_only=True) as connection:
            metadata = connection.execute(
                """
                SELECT version, source, updated_at
                FROM app_meta.global_display_order
                WHERE profile_id = 1
                """
            ).fetchone()
            if metadata is None:
                raise RuntimeError("공용 표시순서가 초기화되지 않았습니다.")
            rules = _load_global_display_order_rules(connection)
        return GlobalDisplayOrder(
            version=int(metadata[0]),
            source=str(metadata[1]),
            updated_at=metadata[2],
            rules=rules,
        )

    def replace_global_display_order(
        self,
        rules: pd.DataFrame,
        *,
        source: str,
    ) -> GlobalDisplayOrder:
        """Atomically replace the shared profile without creating scenario revisions."""
        _validate_global_display_order_frame(rules)
        source_label = _required_text(source, "표시순서 변경 출처")
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT version FROM app_meta.global_display_order WHERE profile_id = 1"
            ).fetchone()
            version = 1 if row is None else int(row[0]) + 1
            connection.execute(
                "DELETE FROM app_meta.global_display_order_rule WHERE profile_id = 1"
            )
            connection.execute("DELETE FROM app_meta.global_display_order WHERE profile_id = 1")
            _insert_global_display_order(
                connection,
                rules,
                version=version,
                source=source_label,
            )
        return self.load_global_display_order()

    def create_scenario(
        self,
        metadata: ScenarioCreate,
        reference_tables: Mapping[str, pd.DataFrame],
        preset: ScenarioPreset,
        *,
        source_data: pd.DataFrame | None = None,
        revision_tables: Mapping[str, pd.DataFrame] | None = None,
        revision_name: str = "초기 리비전",
        note: str | None = None,
    ) -> ScenarioSnapshot:
        _require_tables(reference_tables, tuple(REFERENCE_TABLES), "기준정보")
        revision_source = dict(reference_tables)
        if revision_tables is not None:
            revision_source.update(revision_tables)
        _require_tables(revision_source, tuple(REVISION_TABLES), "리비전")
        _validate_preset_processes(preset, revision_source["RQ_REQB"])

        scenario_id = str(uuid4())
        dataset_id = str(uuid4())
        revision_id = str(uuid4())
        revision_label = _required_text(revision_name, "리비전명")
        reference_hash = _hash_tables(revision_source, tuple(REVISION_TABLES))
        normalized_source = normalize_core_data(source_data) if source_data is not None else None
        source_profile = (
            build_source_column_profile(normalized_source)
            if normalized_source is not None
            else None
        )
        source_row_count = len(normalized_source) if normalized_source is not None else 0
        source_schema_hash = (
            core_data_schema_hash(normalized_source) if normalized_source is not None else None
        )
        source_data_hash = (
            core_data_hash(normalized_source) if normalized_source is not None else None
        )
        _validate_declared_source_metadata(
            metadata,
            row_count=source_row_count,
            schema_hash=source_schema_hash,
            data_hash=source_data_hash,
        )

        with self._write_transaction() as connection:
            if source_data_hash is not None:
                _validate_immutable_source_code(
                    connection,
                    metadata.source_simulation_code,
                    source_data_hash,
                )
            connection.execute(
                """
                INSERT INTO app_meta.scenario (
                    scenario_id,
                    scenario_name,
                    source_simulation_code,
                    source_simulation_name,
                    status
                )
                VALUES (?, ?, ?, ?, 'ACTIVE')
                """,
                [
                    scenario_id,
                    metadata.scenario_name,
                    metadata.source_simulation_code,
                    metadata.source_simulation_name,
                ],
            )
            connection.execute(
                """
                INSERT INTO app_meta.dataset (
                    dataset_id,
                    scenario_id,
                    source_type,
                    source_registered_at,
                    source_row_count,
                    source_schema_hash,
                    source_data_hash,
                    pipeline_version,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'LOADING')
                """,
                [
                    dataset_id,
                    scenario_id,
                    metadata.source_type,
                    metadata.source_registered_at,
                    source_row_count,
                    source_schema_hash,
                    source_data_hash,
                    metadata.pipeline_version,
                ],
            )
            if normalized_source is not None and source_profile is not None:
                _insert_core_data(connection, dataset_id, normalized_source)
                _insert_source_profile(connection, dataset_id, source_profile)
            for logical_name, table_name in REFERENCE_TABLES.items():
                _insert_frame(
                    connection,
                    schema="ref_data",
                    table_name=table_name,
                    owner_column="dataset_id",
                    owner_id=dataset_id,
                    frame=reference_tables[logical_name],
                    logical_name=logical_name,
                )
            self._insert_revision(
                connection,
                revision_id=revision_id,
                scenario_id=scenario_id,
                revision_no=1,
                revision_name=revision_label,
                parent_revision_id=None,
                note=note,
                reference_hash=reference_hash,
                revision_tables=revision_source,
                preset=preset,
            )
            connection.execute(
                "UPDATE app_meta.dataset SET status = 'READY' WHERE dataset_id = ?",
                [dataset_id],
            )
            connection.execute(
                """
                UPDATE app_meta.scenario
                SET active_revision_id = ?, updated_at = current_timestamp
                WHERE scenario_id = ?
                """,
                [revision_id, scenario_id],
            )

        return self.load_revision(revision_id)

    def load_source_data(self, scenario_id: str) -> pd.DataFrame:
        with self._connect(read_only=True) as connection:
            dataset = connection.execute(
                """
                SELECT d.dataset_id, d.source_row_count
                FROM app_meta.dataset d
                WHERE d.scenario_id = ?
                """,
                [scenario_id],
            ).fetchone()
            if dataset is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            if int(dataset[1]) <= 0:
                raise ValueError("이 시나리오에는 원천 Core Data가 저장되어 있지 않습니다.")
            columns = [column.name for column in load_core_data_contract().columns]
            projection = ", ".join(_quote(column) for column in columns)
            return connection.execute(
                f"SELECT {projection} FROM raw_data.core_data "
                "WHERE dataset_id = ? ORDER BY source_row_no",
                [str(dataset[0])],
            ).fetchdf()

    def load_source_profile(self, scenario_id: str) -> pd.DataFrame:
        with self._connect(read_only=True) as connection:
            dataset = connection.execute(
                "SELECT dataset_id FROM app_meta.dataset WHERE scenario_id = ?",
                [scenario_id],
            ).fetchone()
            if dataset is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            return connection.execute(
                """
                SELECT ordinal_position, column_name, source_dtype, nullable_dtype,
                       null_count, unique_count
                FROM raw_data.source_column_profile
                WHERE dataset_id = ?
                ORDER BY ordinal_position
                """,
                [str(dataset[0])],
            ).fetchdf()

    def save_revision(
        self,
        scenario_id: str,
        revision_tables: Mapping[str, pd.DataFrame],
        preset: ScenarioPreset,
        *,
        revision_name: str,
        parent_revision_id: str | None = None,
        note: str | None = None,
    ) -> ScenarioSnapshot:
        _require_tables(revision_tables, tuple(REVISION_TABLES), "리비전")
        revision_label = _required_text(revision_name, "리비전명")
        reference_hash = _hash_tables(revision_tables, tuple(REVISION_TABLES))
        revision_id = str(uuid4())

        with self._write_transaction() as connection:
            row = connection.execute(
                """
                SELECT s.active_revision_id,
                       COALESCE(MAX(r.revision_no), 0) AS latest_revision_no,
                       s.status
                FROM app_meta.scenario s
                LEFT JOIN app_meta.scenario_revision r ON r.scenario_id = s.scenario_id
                WHERE s.scenario_id = ?
                GROUP BY s.active_revision_id, s.status
                """,
                [scenario_id],
            ).fetchone()
            if row is None:
                raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
            active_revision_id, latest_revision_no, status = row
            if str(status) != "ACTIVE":
                raise ValueError("보관된 시나리오에는 새 리비전을 저장할 수 없습니다.")
            selected_parent_id = parent_revision_id or (
                str(active_revision_id) if active_revision_id else None
            )
            if selected_parent_id is not None:
                parent_owner = connection.execute(
                    """
                    SELECT scenario_id
                    FROM app_meta.scenario_revision
                    WHERE revision_id = ?
                    """,
                    [selected_parent_id],
                ).fetchone()
                if parent_owner is None or str(parent_owner[0]) != scenario_id:
                    raise ValueError(
                        f"상위 리비전이 현재 시나리오에 속하지 않습니다: {selected_parent_id}"
                    )
            _validate_preset_processes(preset, revision_tables["RQ_REQB"])
            self._insert_revision(
                connection,
                revision_id=revision_id,
                scenario_id=scenario_id,
                revision_no=int(latest_revision_no) + 1,
                revision_name=revision_label,
                parent_revision_id=selected_parent_id,
                note=note,
                reference_hash=reference_hash,
                revision_tables=revision_tables,
                preset=preset,
            )
            connection.execute(
                """
                UPDATE app_meta.scenario
                SET active_revision_id = ?, updated_at = current_timestamp
                WHERE scenario_id = ?
                """,
                [revision_id, scenario_id],
            )

        return self.load_revision(revision_id)

    def list_scenarios(self, *, include_archived: bool = False) -> list[ScenarioSummary]:
        where_clause = "" if include_archived else "WHERE s.status = 'ACTIVE'"
        with self._connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT s.scenario_id, d.dataset_id, s.scenario_name,
                       s.source_simulation_code, s.source_simulation_name,
                       d.source_type, s.status, s.active_revision_id,
                       r.revision_no, s.created_at, s.updated_at
                FROM app_meta.scenario s
                JOIN app_meta.dataset d ON d.scenario_id = s.scenario_id
                JOIN app_meta.scenario_revision r ON r.revision_id = s.active_revision_id
                {where_clause}
                ORDER BY s.updated_at DESC, s.scenario_name
                """
            ).fetchall()
        return [_scenario_summary(row) for row in rows]

    def list_revisions(self, scenario_id: str) -> list[RevisionSummary]:
        with self._connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT revision_id, scenario_id, revision_no, revision_name,
                       parent_revision_id, note, reference_hash, created_at
                FROM app_meta.scenario_revision
                WHERE scenario_id = ?
                ORDER BY revision_no DESC
                """,
                [scenario_id],
            ).fetchall()
        return [_revision_summary(row) for row in rows]

    def rename_scenario(self, scenario_id: str, scenario_name: str) -> ScenarioSummary:
        """Rename mutable scenario metadata without changing immutable revisions."""
        label = _required_text(scenario_name, "시나리오명")
        with self._write_transaction() as connection:
            changed = connection.execute(
                """
                UPDATE app_meta.scenario
                SET scenario_name = ?, updated_at = current_timestamp
                WHERE scenario_id = ? AND status = 'ACTIVE'
                RETURNING scenario_id
                """,
                [label, scenario_id],
            ).fetchone()
            if changed is None:
                raise KeyError(f"활성 시나리오를 찾을 수 없습니다: {scenario_id}")
        for scenario in self.list_scenarios():
            if scenario.scenario_id == scenario_id:
                return scenario
        raise KeyError(f"시나리오를 찾을 수 없습니다: {scenario_id}")

    def publish_official_revision(
        self,
        scenario_id: str,
        revision_id: str,
        *,
        release_name: str,
        note: str | None = None,
    ) -> OfficialReleaseSummary:
        """Append an official release pointer to one immutable revision."""
        release_label = _required_text(release_name, "공식버전명")
        official_release_id = str(uuid4())
        with self._write_transaction() as connection:
            owner = connection.execute(
                """
                SELECT s.status
                FROM app_meta.scenario_revision r
                JOIN app_meta.scenario s ON s.scenario_id = r.scenario_id
                WHERE r.revision_id = ? AND r.scenario_id = ?
                """,
                [revision_id, scenario_id],
            ).fetchone()
            if owner is None:
                raise ValueError("공식 지정할 리비전이 선택한 시나리오에 속하지 않습니다.")
            if str(owner[0]) != "ACTIVE":
                raise ValueError("보관된 시나리오는 공식버전으로 지정할 수 없습니다.")
            release_no_row = connection.execute(
                "SELECT COALESCE(MAX(release_no), 0) + 1 FROM app_meta.official_release"
            ).fetchone()
            if release_no_row is None:
                raise RuntimeError("다음 공식버전 번호를 계산하지 못했습니다.")
            release_no = int(release_no_row[0])
            connection.execute(
                """
                INSERT INTO app_meta.official_release (
                    official_release_id, release_no, scenario_id, revision_id,
                    release_name, note
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    official_release_id,
                    release_no,
                    scenario_id,
                    revision_id,
                    release_label,
                    note.strip() if isinstance(note, str) and note.strip() else None,
                ],
            )
        release = self._official_release(official_release_id)
        if release is None:
            raise RuntimeError("저장한 공식버전을 다시 불러오지 못했습니다.")
        return release

    def latest_official_release(self) -> OfficialReleaseSummary | None:
        """Return the latest append-only official release pointer."""
        releases = self.list_official_releases(limit=1)
        return releases[0] if releases else None

    def list_official_releases(self, *, limit: int | None = None) -> list[OfficialReleaseSummary]:
        if limit is not None and limit <= 0:
            raise ValueError("공식버전 조회 건수는 1 이상이어야 합니다.")
        limit_clause = "" if limit is None else " LIMIT ?"
        parameters: list[object] = [] if limit is None else [limit]
        with self._connect(read_only=True) as connection:
            rows = connection.execute(
                _OFFICIAL_RELEASE_SELECT + " ORDER BY o.release_no DESC" + limit_clause,
                parameters,
            ).fetchall()
        return [_official_release_summary(row) for row in rows]

    def _official_release(self, official_release_id: str) -> OfficialReleaseSummary | None:
        with self._connect(read_only=True) as connection:
            row = connection.execute(
                _OFFICIAL_RELEASE_SELECT + " WHERE o.official_release_id = ?",
                [official_release_id],
            ).fetchone()
        return _official_release_summary(row) if row is not None else None

    def load_revision(self, revision_id: str) -> ScenarioSnapshot:
        with self._connect(read_only=True) as connection:
            scenario_row = connection.execute(
                """
                SELECT s.scenario_id, d.dataset_id, s.scenario_name,
                       s.source_simulation_code, s.source_simulation_name,
                       d.source_type, s.status, s.active_revision_id,
                       active_revision.revision_no, s.created_at, s.updated_at
                FROM app_meta.scenario s
                JOIN app_meta.dataset d ON d.scenario_id = s.scenario_id
                JOIN app_meta.scenario_revision active_revision
                  ON active_revision.revision_id = s.active_revision_id
                JOIN app_meta.scenario_revision selected_revision
                  ON selected_revision.scenario_id = s.scenario_id
                WHERE selected_revision.revision_id = ?
                """,
                [revision_id],
            ).fetchone()
            if scenario_row is None:
                raise KeyError(f"리비전을 찾을 수 없습니다: {revision_id}")
            scenario = _scenario_summary(scenario_row)
            revision_row = connection.execute(
                """
                SELECT revision_id, scenario_id, revision_no, revision_name,
                       parent_revision_id, note, reference_hash, created_at
                FROM app_meta.scenario_revision
                WHERE revision_id = ?
                """,
                [revision_id],
            ).fetchone()
            if revision_row is None:
                raise KeyError(f"리비전을 찾을 수 없습니다: {revision_id}")
            revision = _revision_summary(revision_row)
            preset = _load_preset(connection, revision_id)

            tables: dict[str, pd.DataFrame] = {}
            for logical_name, table_name in REFERENCE_TABLES.items():
                if logical_name in REVISION_TABLES:
                    tables[logical_name] = _load_frame(
                        connection,
                        schema="rev_data",
                        table_name=table_name,
                        owner_column="revision_id",
                        owner_id=revision_id,
                    )
                else:
                    tables[logical_name] = _load_frame(
                        connection,
                        schema="ref_data",
                        table_name=table_name,
                        owner_column="dataset_id",
                        owner_id=scenario.dataset_id,
                    )
            global_profile = connection.execute(
                "SELECT profile_id FROM app_meta.global_display_order WHERE profile_id = 1"
            ).fetchone()
            if global_profile is not None:
                tables["RQ_DISPLAY_ORDER"] = _load_global_display_order_rules(connection)
        return ScenarioSnapshot(
            scenario=scenario,
            revision=revision,
            preset=preset,
            tables=tables,
        )

    def archive_scenario(self, scenario_id: str) -> None:
        with self._write_transaction() as connection:
            latest_official = connection.execute(
                """
                SELECT scenario_id
                FROM app_meta.official_release
                ORDER BY release_no DESC
                LIMIT 1
                """
            ).fetchone()
            if latest_official is not None and str(latest_official[0]) == scenario_id:
                raise ValueError(
                    "현재 최신 공식버전의 시나리오는 보관할 수 없습니다. "
                    "다른 공식버전을 먼저 지정하세요."
                )
            changed = connection.execute(
                """
                UPDATE app_meta.scenario
                SET status = 'ARCHIVED', updated_at = current_timestamp
                WHERE scenario_id = ? AND status = 'ACTIVE'
                RETURNING scenario_id
                """,
                [scenario_id],
            ).fetchone()
            if changed is None:
                raise KeyError(f"활성 시나리오를 찾을 수 없습니다: {scenario_id}")
            connection.execute(
                "UPDATE app_meta.dataset SET status = 'ARCHIVED' WHERE scenario_id = ?",
                [scenario_id],
            )

    def _insert_revision(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        revision_id: str,
        scenario_id: str,
        revision_no: int,
        revision_name: str,
        parent_revision_id: str | None,
        note: str | None,
        reference_hash: str,
        revision_tables: Mapping[str, pd.DataFrame],
        preset: ScenarioPreset,
    ) -> None:
        connection.execute(
            """
            INSERT INTO app_meta.scenario_revision (
                revision_id, scenario_id, revision_no, revision_name,
                parent_revision_id, note, reference_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                revision_id,
                scenario_id,
                revision_no,
                revision_name,
                parent_revision_id,
                note,
                reference_hash,
            ],
        )
        for logical_name, table_name in REVISION_TABLES.items():
            _insert_frame(
                connection,
                schema="rev_data",
                table_name=table_name,
                owner_column="revision_id",
                owner_id=revision_id,
                frame=revision_tables[logical_name],
                logical_name=logical_name,
            )
        _insert_preset(connection, revision_id, preset)

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


def _validate_global_display_order_frame(frame: pd.DataFrame) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("공용 표시순서는 pandas DataFrame이어야 합니다.")
    missing = [column for column in GLOBAL_DISPLAY_ORDER_COLUMNS if column not in frame.columns]
    extra = [column for column in frame.columns if column not in GLOBAL_DISPLAY_ORDER_COLUMNS]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(str(column) for column in extra)}")
        raise ValueError(f"공용 표시순서 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")
    if frame.empty:
        raise ValueError("공용 표시순서에는 한 개 이상의 규칙이 필요합니다.")


def _load_existing_display_order(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame | None:
    candidates = (
        (
            """
            SELECT o.revision_id
            FROM app_meta.official_release o
            WHERE EXISTS (
                SELECT 1 FROM rev_data.rq_display_order d
                WHERE d.revision_id = o.revision_id
            )
            ORDER BY o.release_no DESC LIMIT 1
            """,
            "rev_data",
            "revision_id",
        ),
        (
            """
            SELECT ds.dataset_id
            FROM app_meta.official_release o
            JOIN app_meta.scenario_revision r ON r.revision_id = o.revision_id
            JOIN app_meta.dataset ds ON ds.scenario_id = r.scenario_id
            WHERE EXISTS (
                SELECT 1 FROM ref_data.rq_display_order d
                WHERE d.dataset_id = ds.dataset_id
            )
            ORDER BY o.release_no DESC LIMIT 1
            """,
            "ref_data",
            "dataset_id",
        ),
        (
            """
            SELECT r.revision_id
            FROM app_meta.scenario_revision r
            WHERE EXISTS (
                SELECT 1 FROM rev_data.rq_display_order d
                WHERE d.revision_id = r.revision_id
            )
            ORDER BY r.created_at DESC, r.revision_no DESC LIMIT 1
            """,
            "rev_data",
            "revision_id",
        ),
        (
            """
            SELECT ds.dataset_id
            FROM app_meta.scenario s
            JOIN app_meta.dataset ds ON ds.scenario_id = s.scenario_id
            WHERE EXISTS (
                SELECT 1 FROM ref_data.rq_display_order d
                WHERE d.dataset_id = ds.dataset_id
            )
            ORDER BY s.updated_at DESC LIMIT 1
            """,
            "ref_data",
            "dataset_id",
        ),
    )
    for query, schema, owner_column in candidates:
        owner = connection.execute(query).fetchone()
        if owner is None:
            continue
        return _load_frame(
            connection,
            schema=schema,
            table_name="rq_display_order",
            owner_column=owner_column,
            owner_id=str(owner[0]),
        )
    return None


def _load_global_display_order_rules(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    projection = ", ".join(_quote(column) for column in GLOBAL_DISPLAY_ORDER_COLUMNS)
    return connection.execute(
        f"""
        SELECT {projection}
        FROM app_meta.global_display_order_rule
        WHERE profile_id = 1
        ORDER BY source_row_no
        """
    ).fetchdf()


def _insert_global_display_order(
    connection: duckdb.DuckDBPyConnection,
    rules: pd.DataFrame,
    *,
    version: int,
    source: str,
) -> None:
    _validate_global_display_order_frame(rules)
    connection.execute(
        """
        INSERT INTO app_meta.global_display_order (profile_id, version, source)
        VALUES (1, ?, ?)
        """,
        [version, source],
    )
    prepared = rules.loc[:, list(GLOBAL_DISPLAY_ORDER_COLUMNS)].copy()
    prepared.insert(0, "source_row_no", range(1, len(prepared) + 1))
    prepared.insert(0, "profile_id", 1)
    view_name = f"_incoming_global_display_order_{uuid4().hex}"
    connection.register(view_name, prepared)
    try:
        connection.execute(
            f"INSERT INTO app_meta.global_display_order_rule BY NAME "
            f"SELECT * FROM {_quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)


def _validate_declared_source_metadata(
    metadata: ScenarioCreate,
    *,
    row_count: int,
    schema_hash: str | None,
    data_hash: str | None,
) -> None:
    if metadata.source_row_count not in (0, row_count):
        raise ValueError(
            "선언한 원천 행 수가 Core Data와 일치하지 않습니다: "
            f"{metadata.source_row_count:,} != {row_count:,}"
        )
    for declared, computed, label in (
        (metadata.source_schema_hash, schema_hash, "스키마 해시"),
        (metadata.source_data_hash, data_hash, "데이터 해시"),
    ):
        if declared is not None and declared != computed:
            raise ValueError(f"선언한 원천 {label}가 Core Data와 일치하지 않습니다.")


def _validate_immutable_source_code(
    connection: duckdb.DuckDBPyConnection,
    simulation_code: str,
    source_data_hash: str,
) -> None:
    rows = connection.execute(
        """
        SELECT DISTINCT d.source_data_hash
        FROM app_meta.scenario s
        JOIN app_meta.dataset d ON d.scenario_id = s.scenario_id
        WHERE s.source_simulation_code = ?
          AND d.source_data_hash IS NOT NULL
        """,
        [simulation_code],
    ).fetchall()
    existing_hashes = {str(row[0]) for row in rows}
    if existing_hashes and source_data_hash not in existing_hashes:
        raise ValueError(
            "동일 시뮬레이션 코드에 다른 원천 데이터가 이미 저장되어 있습니다. "
            "원천 코드는 불변이므로 기존 시나리오에서 새 리비전을 저장하세요."
        )


def _insert_core_data(
    connection: duckdb.DuckDBPyConnection,
    dataset_id: str,
    frame: pd.DataFrame,
) -> None:
    expected_columns = [column.name for column in load_core_data_contract().columns]
    actual_columns = [str(column) for column in frame.columns]
    if actual_columns != expected_columns:
        raise ValueError("정규화된 Core Data 컬럼 순서가 계약과 일치하지 않습니다.")
    prepared = frame.copy()
    prepared.insert(0, "row_hash", core_data_row_hashes(frame))
    prepared.insert(0, "source_row_no", range(1, len(prepared) + 1))
    prepared.insert(0, "dataset_id", dataset_id)
    view_name = f"_incoming_core_data_{uuid4().hex}"
    connection.register(view_name, prepared)
    try:
        connection.execute(
            f"INSERT INTO raw_data.core_data BY NAME SELECT * FROM {_quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
    stored_count = connection.execute(
        "SELECT COUNT(*) FROM raw_data.core_data WHERE dataset_id = ?",
        [dataset_id],
    ).fetchone()
    if stored_count is None or int(stored_count[0]) != len(frame):
        raise RuntimeError("Core Data 적재 행 수 검증에 실패했습니다.")


def _insert_source_profile(
    connection: duckdb.DuckDBPyConnection,
    dataset_id: str,
    profile: pd.DataFrame,
) -> None:
    prepared = profile.copy()
    prepared.insert(0, "dataset_id", dataset_id)
    view_name = f"_incoming_source_profile_{uuid4().hex}"
    connection.register(view_name, prepared)
    try:
        connection.execute(
            f"INSERT INTO raw_data.source_column_profile BY NAME SELECT * FROM {_quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
    stored_count = connection.execute(
        "SELECT COUNT(*) FROM raw_data.source_column_profile WHERE dataset_id = ?",
        [dataset_id],
    ).fetchone()
    if stored_count is None or int(stored_count[0]) != len(profile):
        raise RuntimeError("Core Data 컬럼 프로파일 적재 검증에 실패했습니다.")


def _insert_preset(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    preset: ScenarioPreset,
) -> None:
    connection.execute(
        """
        INSERT INTO app_meta.scenario_preset (
            revision_id, start_month, end_month, secure_threshold,
            warning_threshold, preset_schema_version, preset_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            revision_id,
            preset.start_month,
            preset.end_month,
            preset.secure_threshold,
            preset.warning_threshold,
            preset.schema_version,
            preset.digest(),
        ],
    )
    if preset.included_processes:
        process_rows = pd.DataFrame(
            {
                "revision_id": revision_id,
                "process_name": preset.included_processes,
                "display_order": range(1, len(preset.included_processes) + 1),
            }
        )
        connection.register("_incoming_preset_process", process_rows)
        try:
            connection.execute(
                """
                INSERT INTO app_meta.scenario_preset_process BY NAME
                SELECT * FROM _incoming_preset_process
                """
            )
        finally:
            connection.unregister("_incoming_preset_process")
    if preset.standard_target_processes:
        standard_target_rows = pd.DataFrame(
            {
                "revision_id": revision_id,
                "process_name": preset.standard_target_processes,
                "display_order": range(1, len(preset.standard_target_processes) + 1),
            }
        )
        connection.register("_incoming_standard_target_process", standard_target_rows)
        try:
            connection.execute(
                """
                INSERT INTO app_meta.scenario_preset_standard_target_process BY NAME
                SELECT * FROM _incoming_standard_target_process
                """
            )
        finally:
            connection.unregister("_incoming_standard_target_process")


def _load_preset(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> ScenarioPreset:
    row = connection.execute(
        """
        SELECT start_month, end_month, secure_threshold,
               warning_threshold, preset_schema_version
        FROM app_meta.scenario_preset
        WHERE revision_id = ?
        """,
        [revision_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"리비전 프리셋을 찾을 수 없습니다: {revision_id}")
    process_rows = connection.execute(
        """
        SELECT process_name
        FROM app_meta.scenario_preset_process
        WHERE revision_id = ?
        ORDER BY display_order
        """,
        [revision_id],
    ).fetchall()
    standard_target_rows = connection.execute(
        """
        SELECT process_name
        FROM app_meta.scenario_preset_standard_target_process
        WHERE revision_id = ?
        ORDER BY display_order
        """,
        [revision_id],
    ).fetchall()
    return ScenarioPreset(
        start_month=int(row[0]),
        end_month=int(row[1]),
        secure_threshold=float(row[2]),
        warning_threshold=float(row[3]),
        schema_version=int(row[4]),
        included_processes=tuple(str(process[0]) for process in process_rows),
        standard_target_processes=tuple(str(process[0]) for process in standard_target_rows),
    )


def _insert_frame(
    connection: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table_name: str,
    owner_column: str,
    owner_id: str,
    frame: pd.DataFrame,
    logical_name: str,
) -> None:
    target_columns = _business_columns(connection, schema, table_name, owner_column)
    actual_columns = [str(column) for column in frame.columns]
    missing = [column for column in target_columns if column not in actual_columns]
    extra = [column for column in actual_columns if column not in target_columns]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"누락: {', '.join(missing)}")
        if extra:
            details.append(f"추가: {', '.join(extra)}")
        raise ValueError(f"{logical_name} 컬럼 계약이 일치하지 않습니다 ({'; '.join(details)}).")

    prepared = frame.reindex(columns=target_columns).copy()
    if "생산계획년월" in prepared.columns:
        prepared["생산계획년월"] = _normalize_months(prepared["생산계획년월"], logical_name)
    prepared.insert(0, "source_row_no", range(1, len(prepared) + 1))
    prepared.insert(0, owner_column, owner_id)
    view_name = f"_incoming_{uuid4().hex}"
    connection.register(view_name, prepared)
    try:
        connection.execute(
            f"INSERT INTO {_quote(schema)}.{_quote(table_name)} BY NAME "
            f"SELECT * FROM {_quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
    stored_count = connection.execute(
        f"SELECT COUNT(*) FROM {_quote(schema)}.{_quote(table_name)} "
        f"WHERE {_quote(owner_column)} = ?",
        [owner_id],
    ).fetchone()
    if stored_count is None or int(stored_count[0]) != len(frame):
        raise RuntimeError(f"{logical_name} 적재 행 수 검증에 실패했습니다.")


def _load_frame(
    connection: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table_name: str,
    owner_column: str,
    owner_id: str,
) -> pd.DataFrame:
    columns = _business_columns(connection, schema, table_name, owner_column)
    projection = ", ".join(_quote(column) for column in columns)
    return connection.execute(
        f"SELECT {projection} FROM {_quote(schema)}.{_quote(table_name)} "
        f"WHERE {_quote(owner_column)} = ? ORDER BY source_row_no",
        [owner_id],
    ).fetchdf()


def _business_columns(
    connection: duckdb.DuckDBPyConnection,
    schema: str,
    table_name: str,
    owner_column: str,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema, table_name],
    ).fetchall()
    excluded = {owner_column, "source_row_no"}
    columns = [str(row[0]) for row in rows if str(row[0]) not in excluded]
    if not columns:
        raise RuntimeError(f"DuckDB 대상 테이블 계약을 찾을 수 없습니다: {schema}.{table_name}")
    return columns


def _normalize_months(series: pd.Series, table_name: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    months = numeric.fillna(0).astype("int64")
    valid &= months.mod(100).between(1, 12)
    if not valid.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    return months


def _validate_preset_processes(preset: ScenarioPreset, reqb: pd.DataFrame) -> None:
    if "공정" not in reqb.columns:
        raise ValueError("RQ_REQB에 공정 컬럼이 없습니다.")
    available = set(reqb["공정"].astype("string").str.strip().dropna().tolist())
    if "양산구분" not in reqb.columns:
        raise ValueError("RQ_REQB에 양산구분 컬럼이 없습니다.")
    production_rows = reqb.loc[~reqb["양산구분"].astype("string").str.strip().str.upper().eq("ER")]
    production_available = set(
        production_rows["공정"].astype("string").str.strip().dropna().tolist()
    )
    for processes, allowed, label in (
        (preset.included_processes, available, "B/N 포함 공정"),
        (
            preset.standard_target_processes,
            production_available,
            "표준 목표 Capa 공정",
        ),
    ):
        missing = [process for process in processes if process not in allowed]
        if missing:
            raise ValueError(f"프리셋 {label}이 RQ_REQB에 없습니다: {', '.join(missing[:5])}")


def _hash_tables(tables: Mapping[str, pd.DataFrame], names: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        frame = tables[name]
        digest.update(name.encode("utf-8"))
        digest.update("\x1f".join(str(column) for column in frame.columns).encode("utf-8"))
        digest.update(
            pd.util.hash_pandas_object(frame, index=False).to_numpy(dtype="uint64").tobytes()
        )
    return digest.hexdigest()


def _require_tables(
    tables: Mapping[str, pd.DataFrame],
    required: Sequence[str],
    label: str,
) -> None:
    missing = [name for name in required if name not in tables]
    if missing:
        raise KeyError(f"{label} 테이블이 없습니다: {', '.join(missing)}")
    invalid = [name for name in required if not isinstance(tables[name], pd.DataFrame)]
    if invalid:
        raise TypeError(f"{label} 값이 DataFrame이 아닙니다: {', '.join(invalid)}")


def _scenario_summary(row: Sequence[object]) -> ScenarioSummary:
    return ScenarioSummary(
        scenario_id=str(row[0]),
        dataset_id=str(row[1]),
        scenario_name=str(row[2]),
        source_simulation_code=str(row[3]),
        source_simulation_name=str(row[4]),
        source_type=str(row[5]),
        status=str(row[6]),
        active_revision_id=str(row[7]),
        active_revision_no=_as_int(row[8], "활성 리비전 번호"),
        created_at=_as_datetime(row[9]),
        updated_at=_as_datetime(row[10]),
    )


_OFFICIAL_RELEASE_SELECT = """
    SELECT o.official_release_id, o.release_no, o.scenario_id, o.revision_id,
           o.release_name, o.note, s.scenario_name, s.source_simulation_code,
           r.revision_no, r.revision_name, o.published_at
    FROM app_meta.official_release o
    JOIN app_meta.scenario s ON s.scenario_id = o.scenario_id
    JOIN app_meta.scenario_revision r ON r.revision_id = o.revision_id
"""


def _official_release_summary(row: Sequence[object]) -> OfficialReleaseSummary:
    return OfficialReleaseSummary(
        official_release_id=str(row[0]),
        release_no=_as_int(row[1], "공식버전 번호"),
        scenario_id=str(row[2]),
        revision_id=str(row[3]),
        release_name=str(row[4]),
        note=str(row[5]) if row[5] is not None else None,
        scenario_name=str(row[6]),
        source_simulation_code=str(row[7]),
        revision_no=_as_int(row[8], "리비전 번호"),
        revision_name=str(row[9]),
        published_at=_as_datetime(row[10]),
    )


def _revision_summary(row: Sequence[object]) -> RevisionSummary:
    return RevisionSummary(
        revision_id=str(row[0]),
        scenario_id=str(row[1]),
        revision_no=_as_int(row[2], "리비전 번호"),
        revision_name=str(row[3]),
        parent_revision_id=str(row[4]) if row[4] is not None else None,
        note=str(row[5]) if row[5] is not None else None,
        reference_hash=str(row[6]),
        created_at=_as_datetime(row[7]),
    )


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("DuckDB TIMESTAMP 결과가 datetime이 아닙니다.")
    return value


def _as_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"DuckDB {label} 결과가 정수가 아닙니다.")
    return value


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")
    return normalized


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
