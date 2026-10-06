# Purpose: DuckDB 조회 행을 시나리오·리비전·공식버전 요약 모델로 변환한다.

"""DuckDB 조회 행을 시나리오·리비전·공식버전 요약 모델로 변환한다."""

from __future__ import annotations

from collections.abc import Sequence

from capa_simulation.persistence._sql_helpers import as_datetime, as_int
from capa_simulation.persistence.models import (
    OfficialReleaseSummary,
    RevisionSummary,
    ScenarioSummary,
)

SCENARIO_SUMMARY_SELECT = """
    SELECT s.scenario_id, d.dataset_id, s.scenario_name,
           s.source_simulation_code, s.source_simulation_name,
           d.source_type, s.status, s.active_revision_id,
           r.revision_no, s.created_at, s.updated_at, d.source_registered_at
    FROM app_meta.scenario s
    JOIN app_meta.dataset d ON d.scenario_id = s.scenario_id
    JOIN app_meta.scenario_revision r ON r.revision_id = s.active_revision_id
"""


def scenario_summary(row: Sequence[object]) -> ScenarioSummary:
    return ScenarioSummary(
        scenario_id=str(row[0]),
        dataset_id=str(row[1]),
        scenario_name=str(row[2]),
        source_simulation_code=str(row[3]),
        source_simulation_name=str(row[4]),
        source_type=str(row[5]),
        status=str(row[6]),
        active_revision_id=str(row[7]),
        active_revision_no=as_int(row[8], "활성 리비전 번호"),
        created_at=as_datetime(row[9]),
        updated_at=as_datetime(row[10]),
        source_registered_at=as_datetime(row[11]) if row[11] is not None else None,
    )


OFFICIAL_RELEASE_SELECT = """
    SELECT o.official_release_id, o.release_no, o.scenario_id, o.revision_id,
           o.release_name, o.note, s.scenario_name, s.source_simulation_code,
           r.revision_no, r.revision_name, o.published_at
    FROM app_meta.official_release o
    JOIN app_meta.scenario s ON s.scenario_id = o.scenario_id
    JOIN app_meta.scenario_revision r ON r.revision_id = o.revision_id
"""


def official_release_summary(row: Sequence[object]) -> OfficialReleaseSummary:
    return OfficialReleaseSummary(
        official_release_id=str(row[0]),
        release_no=as_int(row[1], "공식버전 번호"),
        scenario_id=str(row[2]),
        revision_id=str(row[3]),
        release_name=str(row[4]),
        note=str(row[5]) if row[5] is not None else None,
        scenario_name=str(row[6]),
        source_simulation_code=str(row[7]),
        revision_no=as_int(row[8], "리비전 번호"),
        revision_name=str(row[9]),
        published_at=as_datetime(row[10]),
    )


REVISION_SUMMARY_SELECT = """
    SELECT revision_id, scenario_id, revision_no, revision_name,
           parent_revision_id, note, reference_hash, created_at
    FROM app_meta.scenario_revision
"""


def revision_summary(row: Sequence[object]) -> RevisionSummary:
    return RevisionSummary(
        revision_id=str(row[0]),
        scenario_id=str(row[1]),
        revision_no=as_int(row[2], "리비전 번호"),
        revision_name=str(row[3]),
        parent_revision_id=str(row[4]) if row[4] is not None else None,
        note=str(row[5]) if row[5] is not None else None,
        reference_hash=str(row[6]),
        created_at=as_datetime(row[7]),
    )
