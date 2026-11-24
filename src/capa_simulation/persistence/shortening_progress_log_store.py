# Purpose: 누적 진척(설비 0036)의 손 기록 · 최종 목표를 읽고 한 줄씩 넣고 고치고 지우는 SQL.

"""누적 진척 기록 · 최종 목표의 SQL.

연결은 부르는 쪽(`DuckDBEquipmentRepository`)이 열고 쓰기는 그 쓰기 트랜잭션 안에서만 부른다
(`manual_downtime_store.py` 와 같은 꼴). 모델과 값 규칙은 `services/shortening_progress_log.py` 다.

기록은 주 한 줄만 고친다 — 있으면 키 아닌 칸 UPDATE, 없으면 INSERT, 지우기는 DELETE 다. 한
트랜잭션에서 같은 키를 지웠다 다시 넣지 않는다(0036 의 PK). 목표는 머리 한 행을 다음 version 으로
갈아 쓴다(지우기는 칸을 비운 채 행을 남긴다).
"""

from __future__ import annotations

from datetime import datetime

import duckdb

from capa_simulation.services.shortening_progress_log import (
    ProgressEntry,
    ProgressGoal,
    ProgressGoalState,
    ProgressLog,
    ProgressWeek,
)

__all__ = [
    "delete_progress_entry",
    "read_progress_log",
    "stored_progress_days",
    "stored_progress_stamp",
    "write_progress_entry",
    "write_progress_goal",
]


def read_progress_log(connection: duckdb.DuckDBPyConnection) -> ProgressLog:
    """기록 전부와 목표 머리. 머리가 없으면 목표 없음 · version 0 이다. 그 해에 없는 주차의
    행(손으로 넣은 53주차)은 버린다 — 그릴 자리가 없다."""
    rows = connection.execute(
        """
        SELECT iso_year, iso_week, shortening_days, recorded_by, updated_at
        FROM equipment_ops.shortening_progress_log
        ORDER BY iso_year, iso_week
        """
    ).fetchall()
    entries: list[ProgressEntry] = []
    for year, week, days, recorded_by, updated_at in rows:
        try:
            progress_week = ProgressWeek(int(year), int(week))
        except ValueError:
            continue
        entries.append(
            ProgressEntry(
                week=progress_week,
                days=int(days),
                recorded_by=str(recorded_by or ""),
                updated_at=updated_at,
            )
        )
    header = connection.execute(
        """
        SELECT goal_days, goal_year, goal_week, version, saved_by, updated_at
        FROM equipment_ops.shortening_progress_goal
        WHERE profile_id = 1
        """
    ).fetchone()
    if header is None:
        return ProgressLog(entries=tuple(entries))
    goal_days, goal_year, goal_week, version, saved_by, updated_at = header
    goal: ProgressGoal | None = None
    if goal_days is not None and goal_year is not None and goal_week is not None:
        try:
            goal = ProgressGoal(int(goal_days), ProgressWeek(int(goal_year), int(goal_week)))
        except ValueError:
            goal = None
    return ProgressLog(
        entries=tuple(entries),
        goal=ProgressGoalState(
            goal=goal,
            version=int(version),
            saved_by=str(saved_by or ""),
            updated_at=updated_at,
        ),
    )


def stored_progress_days(connection: duckdb.DuckDBPyConnection, week: ProgressWeek) -> int | None:
    """그 주의 저장된 일수(없으면 None) — 쓰기 트랜잭션 안에서 화면이 본 값과 대조한다."""
    row = connection.execute(
        """
        SELECT shortening_days
        FROM equipment_ops.shortening_progress_log
        WHERE iso_year = ? AND iso_week = ?
        """,
        [week.year, week.week],
    ).fetchone()
    return None if row is None else int(row[0])


def stored_progress_stamp(
    connection: duckdb.DuckDBPyConnection, week: ProgressWeek
) -> datetime | None:
    """그 주 기록 줄의 저장 시각(없으면 None) — 넣기 스냅숏(0037)이 그 줄과 같은 쓰기에서 섰는지
    가른다."""
    row = connection.execute(
        """
        SELECT updated_at
        FROM equipment_ops.shortening_progress_log
        WHERE iso_year = ? AND iso_week = ?
        """,
        [week.year, week.week],
    ).fetchone()
    return None if row is None else row[0]


def write_progress_entry(
    connection: duckdb.DuckDBPyConnection,
    week: ProgressWeek,
    days: int,
    *,
    recorded_by: str,
    exists: bool,
) -> None:
    """그 주 한 줄을 넣거나(`exists` 거짓) 고친다."""
    if exists:
        connection.execute(
            """
            UPDATE equipment_ops.shortening_progress_log
            SET shortening_days = ?, recorded_by = ?, updated_at = current_timestamp
            WHERE iso_year = ? AND iso_week = ?
            """,
            [days, recorded_by or None, week.year, week.week],
        )
        return
    connection.execute(
        """
        INSERT INTO equipment_ops.shortening_progress_log
            (iso_year, iso_week, shortening_days, recorded_by)
        VALUES (?, ?, ?, ?)
        """,
        [week.year, week.week, days, recorded_by or None],
    )


def delete_progress_entry(connection: duckdb.DuckDBPyConnection, week: ProgressWeek) -> None:
    connection.execute(
        """
        DELETE FROM equipment_ops.shortening_progress_log
        WHERE iso_year = ? AND iso_week = ?
        """,
        [week.year, week.week],
    )


def write_progress_goal(
    connection: duckdb.DuckDBPyConnection,
    goal: ProgressGoal | None,
    *,
    version: int,
    saved_by: str,
) -> None:
    """목표 머리를 `version` 으로 갈아 쓴다(행이 없으면 넣는다). `goal` 이 None 이면 세 칸을
    비운다."""
    values = [
        None if goal is None else goal.days,
        None if goal is None else goal.week.year,
        None if goal is None else goal.week.week,
        version,
        saved_by or None,
    ]
    updated = connection.execute(
        """
        UPDATE equipment_ops.shortening_progress_goal
        SET goal_days = ?, goal_year = ?, goal_week = ?, version = ?, saved_by = ?,
            updated_at = current_timestamp
        WHERE profile_id = 1
        RETURNING profile_id
        """,
        values,
    ).fetchall()
    if updated:
        return
    connection.execute(
        """
        INSERT INTO equipment_ops.shortening_progress_goal
            (profile_id, goal_days, goal_year, goal_week, version, saved_by)
        VALUES (1, ?, ?, ?, ?, ?)
        """,
        values,
    )
