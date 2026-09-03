# Purpose: 시나리오 데이터셋이 소유한 원천 Core Data raw 와 컬럼 프로파일을 저장한다.

"""시나리오 데이터셋이 소유한 원천 Core Data raw 와 컬럼 프로파일을 저장한다."""

from __future__ import annotations

from uuid import uuid4

import duckdb
import pandas as pd

from capa_simulation.io.core_data_source import (
    core_data_row_hashes,
    load_core_data_contract,
)
from capa_simulation.persistence._sql_helpers import quote
from capa_simulation.persistence.models import ScenarioCreate


def validate_declared_source_metadata(
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


def validate_immutable_source_code(
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


def insert_core_data(
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
            f"INSERT INTO raw_data.core_data BY NAME SELECT * FROM {quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
    stored_count = connection.execute(
        "SELECT COUNT(*) FROM raw_data.core_data WHERE dataset_id = ?",
        [dataset_id],
    ).fetchone()
    if stored_count is None or int(stored_count[0]) != len(frame):
        raise RuntimeError("Core Data 적재 행 수 검증에 실패했습니다.")


def insert_source_profile(
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
            f"INSERT INTO raw_data.source_column_profile BY NAME SELECT * FROM {quote(view_name)}"
        )
    finally:
        connection.unregister(view_name)
    stored_count = connection.execute(
        "SELECT COUNT(*) FROM raw_data.source_column_profile WHERE dataset_id = ?",
        [dataset_id],
    ).fetchone()
    if stored_count is None or int(stored_count[0]) != len(profile):
        raise RuntimeError("Core Data 컬럼 프로파일 적재 검증에 실패했습니다.")
