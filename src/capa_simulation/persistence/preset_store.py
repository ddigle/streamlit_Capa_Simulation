# Purpose: 리비전이 소유한 조회·판정 프리셋의 저장과 복원을 담당한다.

"""리비전이 소유한 조회·판정 프리셋의 저장과 복원을 담당한다."""

from __future__ import annotations

from datetime import date, datetime

import duckdb
import pandas as pd

from capa_simulation.persistence.models import (
    DEFAULT_STANDARD_TARGET_DETAIL_LEVEL,
    DEFAULT_STANDARD_TARGET_OUTPUT_METRIC,
    ScenarioPreset,
)


def _optional_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def insert_preset(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
    preset: ScenarioPreset,
) -> None:
    connection.execute(
        """
        INSERT INTO app_meta.scenario_preset (
            revision_id, start_month, end_month, secure_threshold,
            warning_threshold, preset_schema_version, preset_hash,
            standard_target_start_date, standard_target_end_date,
            standard_target_show_detail, standard_target_detail_level,
            standard_target_output_metric
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            revision_id,
            preset.start_month,
            preset.end_month,
            preset.secure_threshold,
            preset.warning_threshold,
            preset.schema_version,
            preset.digest(),
            preset.standard_target_start_date,
            preset.standard_target_end_date,
            preset.standard_target_show_detail,
            preset.standard_target_detail_level,
            preset.standard_target_output_metric,
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


def load_preset(
    connection: duckdb.DuckDBPyConnection,
    revision_id: str,
) -> ScenarioPreset:
    row = connection.execute(
        """
        SELECT start_month, end_month, secure_threshold,
               warning_threshold, preset_schema_version,
               standard_target_start_date, standard_target_end_date,
               standard_target_show_detail, standard_target_detail_level,
               standard_target_output_metric
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
        # 조회·집계 설정 컬럼이 없던 과거 리비전은 NULL 로 읽히고 기본값으로 열린다.
        standard_target_start_date=_optional_date(row[5]),
        standard_target_end_date=_optional_date(row[6]),
        standard_target_show_detail=bool(row[7]),
        standard_target_detail_level=(
            str(row[8]) if row[8] else DEFAULT_STANDARD_TARGET_DETAIL_LEVEL
        ),
        standard_target_output_metric=(
            str(row[9]) if row[9] else DEFAULT_STANDARD_TARGET_OUTPUT_METRIC
        ),
    )


def validate_preset_processes(preset: ScenarioPreset, reqb: pd.DataFrame) -> None:
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
