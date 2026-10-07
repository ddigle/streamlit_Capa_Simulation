# Purpose: HOME 공용 Top5 구간·공지·GAP 비교 대상의 조회와 교체 SQL을 담당한다.

"""HOME 공용 단일행 프로필. 연결과 트랜잭션은 Repository가 소유한다."""

from __future__ import annotations

import duckdb

from capa_simulation.persistence._sql_helpers import reset_profile
from capa_simulation.persistence.models import (
    GlobalComparisonScenario,
    GlobalSummaryNote,
    GlobalTop5Band,
)
from capa_simulation.services.top5_band import DEFAULT_TOP5_MAX_RATE, DEFAULT_TOP5_MIN_RATE


def load_global_top5_band(connection: duckdb.DuckDBPyConnection) -> GlobalTop5Band:
    """열린 연결에서 공용 프로필과 미저장 기본값을 복원한다."""
    row = connection.execute(
        """
        SELECT min_rate, max_rate, version, source, updated_at
        FROM app_meta.global_top5_band
        WHERE profile_id = 1
        """
    ).fetchone()
    if row is None:
        return GlobalTop5Band(
            version=0,
            source="",
            updated_at=None,
            min_rate=DEFAULT_TOP5_MIN_RATE,
            max_rate=DEFAULT_TOP5_MAX_RATE,
        )
    return GlobalTop5Band(
        version=int(row[2]),
        source=str(row[3]),
        updated_at=row[4],
        min_rate=float(row[0]),
        max_rate=float(row[1]),
    )


def replace_global_top5_band(
    connection: duckdb.DuckDBPyConnection, min_rate: float, max_rate: float, *, source: str
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(connection, "global_top5_band")
    connection.execute(
        """
        INSERT INTO app_meta.global_top5_band
            (profile_id, min_rate, max_rate, version, source)
        VALUES (1, ?, ?, ?, ?)
        """,
        [min_rate, max_rate, version, source],
    )


def load_global_summary_note(connection: duckdb.DuckDBPyConnection) -> GlobalSummaryNote:
    """열린 연결에서 공용 프로필과 미저장 기본값을 복원한다."""
    row = connection.execute(
        """
        SELECT note, version, source, updated_at
        FROM app_meta.global_summary_note
        WHERE profile_id = 1
        """
    ).fetchone()
    if row is None:
        return GlobalSummaryNote(version=0, source="", updated_at=None, note="")
    return GlobalSummaryNote(
        version=int(row[1]),
        source=str(row[2]),
        updated_at=row[3],
        note=str(row[0]),
    )


def replace_global_summary_note(
    connection: duckdb.DuckDBPyConnection, note: str, *, source: str
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(connection, "global_summary_note")
    connection.execute(
        """
        INSERT INTO app_meta.global_summary_note (profile_id, note, version, source)
        VALUES (1, ?, ?, ?)
        """,
        [note, version, source],
    )


def load_global_comparison_scenario(
    connection: duckdb.DuckDBPyConnection,
) -> GlobalComparisonScenario:
    """열린 연결에서 공용 프로필과 미저장 기본값을 복원한다."""
    row = connection.execute(
        """
        SELECT scenario_id, revision_id, version, source, updated_at
        FROM app_meta.global_comparison_scenario
        WHERE profile_id = 1
        """
    ).fetchone()
    if row is None:
        return GlobalComparisonScenario(
            version=0,
            source="",
            updated_at=None,
            scenario_id=None,
            revision_id=None,
        )
    return GlobalComparisonScenario(
        version=int(row[2]),
        source=str(row[3]),
        updated_at=row[4],
        scenario_id=None if row[0] is None else str(row[0]),
        revision_id=None if row[1] is None else str(row[1]),
    )


def replace_global_comparison_scenario(
    connection: duckdb.DuckDBPyConnection,
    scenario_id: str | None,
    revision_id: str | None,
    *,
    source: str,
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(connection, "global_comparison_scenario")
    connection.execute(
        """
        INSERT INTO app_meta.global_comparison_scenario
            (profile_id, scenario_id, revision_id, version, source)
        VALUES (1, ?, ?, ?, ?)
        """,
        [scenario_id, revision_id, version, source],
    )


def touch_global_comparison_scenario(
    connection: duckdb.DuckDBPyConnection,
    scenario_id: str,
) -> None:
    """공용 GAP 비교 대상이 이 시나리오를 가리키면 `version` 만 올린다(이름을 바꿨을 때).

    입장 화면 Summary 의 GAP 은 비교 시나리오 이름을 풍선에 적고, 그 값은 이 프로필의 `version`
    을 키로 서버에 남는다. 이름만 바뀌면 키가 그대로라 옛 이름이 남았다. 가리키는 대상은 그대로다.
    캐시는 경로 키이므로 호출부가 비운다(`clear_global_comparison_scenario_cache`).
    """
    connection.execute(
        """
        UPDATE app_meta.global_comparison_scenario
        SET version = version + 1
        WHERE scenario_id = ?
        """,
        [scenario_id],
    )


def clear_global_comparison_scenario(
    connection: duckdb.DuckDBPyConnection,
    scenario_id: str,
) -> None:
    """공용 GAP 비교 대상이 이 시나리오를 가리키고 있으면 비운다.

    다른 교체와 같은 결로 `version` 을 올린다. 캐시는 경로 키이므로 다른 세션의 캐시는
    호출부가 명시적으로 비운다(`clear_global_comparison_scenario_cache`). `revision_id` 도 같이
    비운다 — 표의 `CHECK (revision_id IS NULL OR scenario_id IS NOT NULL)` 때문에 한쪽만
    비우면 제약에 걸린다.
    """
    connection.execute(
        """
        UPDATE app_meta.global_comparison_scenario
        SET scenario_id = NULL, revision_id = NULL, version = version + 1
        WHERE scenario_id = ?
        """,
        [scenario_id],
    )
