# Purpose: Transactional DuckDB repository for scenario-owned reference snapshots.

"""Transactional DuckDB repository for scenario-owned reference snapshots."""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.io.core_data_source import (
    build_source_column_profile,
    core_data_hash,
    core_data_schema_hash,
    load_core_data_contract,
    normalize_core_data,
)
from capa_simulation.persistence._sql_helpers import (
    connect,
    hash_tables,
    insert_frame,
    load_frame,
    quote,
    require_tables,
    required_text,
)
from capa_simulation.persistence.display_order_store import (
    display_order_frames_equal,
    insert_global_display_order,
    load_existing_display_order,
    load_global_display_order_rules,
    prepare_global_display_order_rules,
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
from capa_simulation.persistence.preset_store import (
    insert_preset,
    load_preset,
    validate_preset_processes,
)
from capa_simulation.persistence.source_data_store import (
    insert_core_data,
    insert_source_profile,
    validate_declared_source_metadata,
    validate_immutable_source_code,
)
from capa_simulation.persistence.summaries import (
    OFFICIAL_RELEASE_SELECT,
    official_release_summary,
    revision_summary,
    scenario_summary,
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
        "RQ_CHIP_QTY",
        "RQ_CHIP_EQ",
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
        prepared_fallback = prepare_global_display_order_rules(fallback)
        with self._write_transaction() as connection:
            existing = connection.execute(
                "SELECT profile_id FROM app_meta.global_display_order WHERE profile_id = 1"
            ).fetchone()
            if existing is None:
                migrated = load_existing_display_order(connection)
                if migrated is None:
                    initial = prepared_fallback
                    source = "초기 표시순서 시드"
                else:
                    initial = prepare_global_display_order_rules(migrated)
                    source = "기존 시나리오 표시순서 이관"
                    if len(initial) < len(prepared_fallback):
                        initial = prepared_fallback
                        source = "초기 표시순서 시드"
                insert_global_display_order(
                    connection,
                    initial,
                    version=1,
                    source=source,
                )
        profile = self.load_global_display_order()
        prepared = prepare_global_display_order_rules(profile.rules)
        if not display_order_frames_equal(profile.rules, prepared):
            return self.replace_global_display_order(
                prepared,
                source="경로 식별 컬럼 하위 배치 자동 보강",
            )
        return profile

    def load_global_display_order(self) -> GlobalDisplayOrder:
        """Load the scenario-independent display-order profile."""
        with self._connect() as connection:
            metadata = connection.execute(
                """
                SELECT version, source, updated_at
                FROM app_meta.global_display_order
                WHERE profile_id = 1
                """
            ).fetchone()
            if metadata is None:
                raise RuntimeError("공용 표시순서가 초기화되지 않았습니다.")
            rules = load_global_display_order_rules(connection)
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
        prepared_rules = prepare_global_display_order_rules(rules)
        source_label = required_text(source, "표시순서 변경 출처")
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT version FROM app_meta.global_display_order WHERE profile_id = 1"
            ).fetchone()
            version = 1 if row is None else int(row[0]) + 1
            connection.execute(
                "DELETE FROM app_meta.global_display_order_rule WHERE profile_id = 1"
            )
            connection.execute("DELETE FROM app_meta.global_display_order WHERE profile_id = 1")
            insert_global_display_order(
                connection,
                prepared_rules,
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
        require_tables(reference_tables, tuple(REFERENCE_TABLES), "기준정보")
        revision_source = dict(reference_tables)
        if revision_tables is not None:
            revision_source.update(revision_tables)
        require_tables(revision_source, tuple(REVISION_TABLES), "리비전")
        validate_preset_processes(preset, revision_source["RQ_REQB"])

        scenario_id = str(uuid4())
        dataset_id = str(uuid4())
        revision_id = str(uuid4())
        revision_label = required_text(revision_name, "리비전명")
        reference_hash = hash_tables(revision_source, tuple(REVISION_TABLES))
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
        validate_declared_source_metadata(
            metadata,
            row_count=source_row_count,
            schema_hash=source_schema_hash,
            data_hash=source_data_hash,
        )

        with self._write_transaction() as connection:
            if source_data_hash is not None:
                validate_immutable_source_code(
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
                insert_core_data(connection, dataset_id, normalized_source)
                insert_source_profile(connection, dataset_id, source_profile)
            for logical_name, table_name in REFERENCE_TABLES.items():
                insert_frame(
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
        with self._connect() as connection:
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
            projection = ", ".join(quote(column) for column in columns)
            return connection.execute(
                f"SELECT {projection} FROM raw_data.core_data "
                "WHERE dataset_id = ? ORDER BY source_row_no",
                [str(dataset[0])],
            ).fetchdf()

    def load_source_profile(self, scenario_id: str) -> pd.DataFrame:
        with self._connect() as connection:
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
        virtual_products: Sequence[Mapping[str, str]] = (),
    ) -> ScenarioSnapshot:
        require_tables(revision_tables, tuple(REVISION_TABLES), "리비전")
        revision_label = required_text(revision_name, "리비전명")
        reference_hash = hash_tables(revision_tables, tuple(REVISION_TABLES))
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
            validate_preset_processes(preset, revision_tables["RQ_REQB"])
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
                virtual_products=virtual_products,
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
        with self._connect() as connection:
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
        return [scenario_summary(row) for row in rows]

    def list_revisions(self, scenario_id: str) -> list[RevisionSummary]:
        with self._connect() as connection:
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
        return [revision_summary(row) for row in rows]

    def rename_scenario(self, scenario_id: str, scenario_name: str) -> ScenarioSummary:
        """Rename mutable scenario metadata without changing immutable revisions."""
        label = required_text(scenario_name, "시나리오명")
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
        release_label = required_text(release_name, "공식버전명")
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
        with self._connect() as connection:
            rows = connection.execute(
                OFFICIAL_RELEASE_SELECT + " ORDER BY o.release_no DESC" + limit_clause,
                parameters,
            ).fetchall()
        return [official_release_summary(row) for row in rows]

    def _official_release(self, official_release_id: str) -> OfficialReleaseSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                OFFICIAL_RELEASE_SELECT + " WHERE o.official_release_id = ?",
                [official_release_id],
            ).fetchone()
        return official_release_summary(row) if row is not None else None

    def load_revision(self, revision_id: str) -> ScenarioSnapshot:
        with self._connect() as connection:
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
            scenario = scenario_summary(scenario_row)
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
            revision = revision_summary(revision_row)
            preset = load_preset(connection, revision_id)

            tables: dict[str, pd.DataFrame] = {}
            for logical_name, table_name in REFERENCE_TABLES.items():
                if logical_name in REVISION_TABLES:
                    tables[logical_name] = load_frame(
                        connection,
                        schema="rev_data",
                        table_name=table_name,
                        owner_column="revision_id",
                        owner_id=revision_id,
                    )
                else:
                    tables[logical_name] = load_frame(
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
                tables["RQ_DISPLAY_ORDER"] = load_global_display_order_rules(connection)
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
        virtual_products: Sequence[Mapping[str, str]] = (),
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
            insert_frame(
                connection,
                schema="rev_data",
                table_name=table_name,
                owner_column="revision_id",
                owner_id=revision_id,
                frame=revision_tables[logical_name],
                logical_name=logical_name,
            )
        insert_preset(connection, revision_id, preset)
        # 가상 제품은 실적과 대조할 수 없다. 어떤 제품이 어느 원본에서 복제됐는지
        # 리비전에 남겨야 공식버전 발행 시 확인할 수 있다.
        for record in virtual_products:
            connection.execute(
                """
                INSERT INTO app_meta.revision_virtual_product (
                    revision_id, "제품정보", "Stack", source_product, source_stack
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    revision_id,
                    record["product"],
                    record["stack"],
                    record["source_product"],
                    record["source_stack"],
                ],
            )

    def list_virtual_products(self, revision_id: str) -> pd.DataFrame:
        """리비전에 기록된 가상 제품 목록을 돌려준다. 공식버전 발행 전 확인용이다."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT "제품정보", "Stack", source_product, source_stack
                FROM app_meta.revision_virtual_product
                WHERE revision_id = ?
                ORDER BY "제품정보", "Stack"
                """,
                [revision_id],
            ).fetchall()
        return pd.DataFrame(rows, columns=["제품정보", "Stack", "원본 제품정보", "원본 Stack"])

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

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return connect(self._database_path)
