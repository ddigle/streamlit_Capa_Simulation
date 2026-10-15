# Purpose: 공식버전 자동 갱신(0035)의 설정 프로필·변경 기록·실행 기록·자동 off 기록 SQL을 담당한다.

"""공식버전 자동 갱신(0035)의 SQL. 잠금·트랜잭션은 Repository 가 소유하고 여기는 연결만 받는다.

- **설정**은 다른 공용 프로필처럼 헤더 한 행이고 저장마다 version 이 오른다. 저장은 **버전
  대조**를 한다 — 편집을 시작할 때 본 version 과 저장본이 다르면 다른 사람이 먼저 바꾼 것이라
  덮지 않는다. 저장마다 변경 기록 한 행을 같은 version 으로 남긴다(헤더는 현재본만 남는다).
- **실행 기록**은 회차 하나가 한 행이다. `run_key` 가 유일해 같은 회차를 두 번 잡지 못한다.
  단계가 진행될 때마다 정해진 칸만 고쳐 쓴다(`RUN_UPDATABLE_COLUMNS`).
- **자동 off 기록**은 회차·공정마다 한 행이다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import fields
from datetime import date, datetime, time
from typing import cast

import duckdb

from capa_simulation.persistence._sql_helpers import quote, reset_profile
from capa_simulation.persistence.models import (
    AutoOfficialUpdateExclusion,
    AutoOfficialUpdateRun,
    AutoOfficialUpdateSettingChange,
    AutoOfficialUpdateSettings,
)
from capa_simulation.services.auto_official_update import (
    DEFAULT_CONFIG,
    STATUS_RUNNING,
    AutoUpdateConfig,
    ExclusionKind,
    RunStatus,
    TriggerKind,
)

_HEADER_TABLE = "global_auto_official_update"
_SETTING_LOG_TABLE = "auto_official_update_setting_log"
_RUN_TABLE = "auto_official_update_run"
_EXCLUSION_TABLE = "auto_official_update_exclusion"

# 실행 기록의 칸 차례 = 모델 필드 차례. 이름도 같다.
RUN_COLUMNS: tuple[str, ...] = tuple(field.name for field in fields(AutoOfficialUpdateRun))
# 회차를 잡은 뒤 고쳐 쓸 수 있는 칸. 식별·선점·시작 칸(`run_id`·`run_key`·`trigger_kind`·`run_date`·
# `started_at`)과 그 회차가 읽은 설정(`keyword`·`threshold`·`settings_version`)은 고치지 않는다.
RUN_UPDATABLE_COLUMNS: frozenset[str] = frozenset(RUN_COLUMNS) - {
    "run_id",
    "run_key",
    "trigger_kind",
    "run_date",
    "started_at",
    "keyword",
    "threshold",
    "settings_version",
}


class AutoOfficialUpdateSettingsConflict(ValueError):
    """편집을 시작한 뒤 다른 사람이 자동 갱신 설정을 먼저 저장했다. 저장하지 않고 알린다."""


def load_settings(connection: duckdb.DuckDBPyConnection) -> AutoOfficialUpdateSettings:
    """저장된 설정. 한 번도 저장하지 않았으면 version 0 의 코드 기본값이다(DB 에 쓰지 않는다)."""
    row = connection.execute(
        f"""
        SELECT version, source, updated_at, enabled, check_time, keyword, threshold
        FROM app_meta.{_HEADER_TABLE}
        WHERE profile_id = 1
        """
    ).fetchone()
    if row is None:
        return AutoOfficialUpdateSettings(
            version=0, source="", updated_at=None, config=DEFAULT_CONFIG
        )
    return AutoOfficialUpdateSettings(
        version=int(row[0]),
        source=str(row[1]),
        updated_at=row[2],
        config=AutoUpdateConfig(
            enabled=bool(row[3]),
            check_time=cast(time, row[4]),
            keyword=str(row[5]),
            threshold=float(row[6]),
        ),
    )


def stored_settings_version(connection: duckdb.DuckDBPyConnection) -> int:
    row = connection.execute(
        f"SELECT version FROM app_meta.{_HEADER_TABLE} WHERE profile_id = 1"
    ).fetchone()
    return 0 if row is None else int(row[0])


def replace_settings(
    connection: duckdb.DuckDBPyConnection,
    *,
    config: AutoUpdateConfig,
    source: str,
    changed_by: str | None,
    change_text: str,
    expected_version: int,
) -> int:
    """설정을 교체하고 변경 기록을 남긴다. 새 version 을 돌려준다. 잠금·트랜잭션은 호출자 몫이다."""
    stored = stored_settings_version(connection)
    if stored != int(expected_version):
        raise AutoOfficialUpdateSettingsConflict(
            "다른 사용자가 먼저 자동 갱신 설정을 저장해 이번 저장은 반영하지 않았습니다"
            f"(편집 시작 v{int(expected_version)} · 지금 v{stored}). 최신 설정을 확인한 뒤 다시 "
            "저장하세요."
        )
    version = reset_profile(connection, _HEADER_TABLE)
    connection.execute(
        f"""
        INSERT INTO app_meta.{_HEADER_TABLE}
            (profile_id, version, source, enabled, check_time, keyword, threshold)
        VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        [
            version,
            source,
            config.enabled,
            config.check_time,
            config.keyword,
            config.threshold,
        ],
    )
    connection.execute(
        f"""
        INSERT INTO app_meta.{_SETTING_LOG_TABLE} (version, changed_by, change_text)
        VALUES (?, ?, ?)
        """,
        [version, changed_by, change_text],
    )
    return version


def load_setting_changes(
    connection: duckdb.DuckDBPyConnection, *, limit: int | None = None
) -> list[AutoOfficialUpdateSettingChange]:
    """설정 변경 기록. 최근 것이 위다."""
    limit_clause = "" if limit is None else " LIMIT ?"
    rows = connection.execute(
        f"""
        SELECT version, changed_at, changed_by, change_text
        FROM app_meta.{_SETTING_LOG_TABLE}
        ORDER BY version DESC
        """
        + limit_clause,
        [] if limit is None else [limit],
    ).fetchall()
    return [
        AutoOfficialUpdateSettingChange(
            version=int(row[0]),
            changed_at=row[1],
            changed_by=None if row[2] is None else str(row[2]),
            change_text=str(row[3]),
        )
        for row in rows
    ]


def run_key_exists(connection: duckdb.DuckDBPyConnection, run_key: str) -> bool:
    return (
        connection.execute(
            f"SELECT 1 FROM app_meta.{_RUN_TABLE} WHERE run_key = ?", [run_key]
        ).fetchone()
        is not None
    )


def insert_run(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    run_key: str,
    trigger_kind: TriggerKind,
    run_date: date,
    started_at: datetime,
    keyword: str,
    threshold: float,
    settings_version: int,
) -> None:
    """회차를 「실행 중」으로 잡는다."""
    connection.execute(
        f"""
        INSERT INTO app_meta.{_RUN_TABLE} (
            run_id, run_key, trigger_kind, run_date, status, stage, started_at,
            keyword, threshold, settings_version
        )
        VALUES (?, ?, ?, ?, ?, 'claim', ?, ?, ?, ?)
        """,
        [
            run_id,
            run_key,
            trigger_kind,
            run_date,
            STATUS_RUNNING,
            started_at,
            keyword,
            threshold,
            settings_version,
        ],
    )


def update_run(
    connection: duckdb.DuckDBPyConnection,
    run_id: str,
    values: Mapping[str, object],
) -> None:
    """회차 행의 정해진 칸을 고쳐 쓴다. 없는 회차나 고칠 수 없는 칸이면 예외다."""
    if not values:
        return
    unknown = sorted(set(values) - RUN_UPDATABLE_COLUMNS)
    if unknown:
        raise KeyError(f"자동 갱신 실행 기록에서 고칠 수 없는 칸입니다: {', '.join(unknown)}")
    names = list(values)
    assignments = ", ".join(f"{quote(name)} = ?" for name in names)
    changed = connection.execute(
        f"UPDATE app_meta.{_RUN_TABLE} SET {assignments} WHERE run_id = ? RETURNING run_id",
        [*(values[name] for name in names), run_id],
    ).fetchone()
    if changed is None:
        raise KeyError(f"자동 갱신 실행 기록을 찾을 수 없습니다: {run_id}")


def load_runs(
    connection: duckdb.DuckDBPyConnection,
    *,
    limit: int | None = None,
    run_id: str | None = None,
) -> list[AutoOfficialUpdateRun]:
    """실행 기록. 최근에 시작한 것이 위다."""
    projection = ", ".join(quote(column) for column in RUN_COLUMNS)
    where_clause = "" if run_id is None else " WHERE run_id = ?"
    limit_clause = "" if limit is None else " LIMIT ?"
    parameters: list[object] = []
    if run_id is not None:
        parameters.append(run_id)
    if limit is not None:
        parameters.append(limit)
    rows = connection.execute(
        f"SELECT {projection} FROM app_meta.{_RUN_TABLE}"
        + where_clause
        + " ORDER BY started_at DESC, run_id DESC"
        + limit_clause,
        parameters,
    ).fetchall()
    return [_run_from_row(row) for row in rows]


def _run_from_row(row: Sequence[object]) -> AutoOfficialUpdateRun:
    record = dict(zip(RUN_COLUMNS, row, strict=True))
    record["trigger_kind"] = cast(TriggerKind, str(record["trigger_kind"]))
    record["status"] = cast(RunStatus, str(record["status"]))
    record["threshold"] = float(cast(float, record["threshold"]))
    return AutoOfficialUpdateRun(**record)  # type: ignore[arg-type]


def abandon_running_runs(
    connection: duckdb.DuckDBPyConnection,
    *,
    started_before: datetime,
    finished_at: datetime,
    reason: str,
) -> int:
    """`started_before` 전에 시작해 아직 「실행 중」인 회차를 오류로 닫는다. 닫은 건수를 돌려준다.

    앱이 회차 도중에 꺼지면 그 행은 영영 「실행 중」으로 남는다. 다음 기동이 제 기동 시각을 넘겨
    부른다.
    """
    rows = connection.execute(
        f"""
        UPDATE app_meta.{_RUN_TABLE}
        SET status = 'ERROR', finished_at = ?, reason = ?
        WHERE status = ? AND started_at < ?
        RETURNING run_id
        """,
        [finished_at, reason, STATUS_RUNNING, started_before],
    ).fetchall()
    return len(rows)


def insert_exclusions(
    connection: duckdb.DuckDBPyConnection,
    exclusions: Sequence[AutoOfficialUpdateExclusion],
) -> None:
    for exclusion in exclusions:
        connection.execute(
            f"""
            INSERT INTO app_meta.{_EXCLUSION_TABLE}
                (run_id, filtered_revision_id, "공정", kind, min_rate, min_month)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                exclusion.run_id,
                exclusion.filtered_revision_id,
                exclusion.process,
                exclusion.kind,
                exclusion.min_rate,
                exclusion.min_month,
            ],
        )


def load_exclusions(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_ids: Collection[str] | None = None,
    filtered_revision_ids: Collection[str] | None = None,
) -> list[AutoOfficialUpdateExclusion]:
    """자동 off 기록. 조건을 주지 않으면 전부다. 회차 → 종류(자동 먼저) → 공정 이름 차례."""
    clauses: list[str] = []
    parameters: list[object] = []
    for column, values in (
        ("run_id", run_ids),
        ("filtered_revision_id", filtered_revision_ids),
    ):
        if values is None:
            continue
        listed = [str(value) for value in values]
        if not listed:
            return []
        clauses.append(f"{column} IN ({', '.join('?' for _ in listed)})")
        parameters.extend(listed)
    where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""
        SELECT run_id, filtered_revision_id, "공정", kind, min_rate, min_month
        FROM app_meta.{_EXCLUSION_TABLE}
        """
        + where_clause
        + ' ORDER BY run_id, kind, "공정"',
        parameters,
    ).fetchall()
    return [
        AutoOfficialUpdateExclusion(
            run_id=str(row[0]),
            filtered_revision_id=None if row[1] is None else str(row[1]),
            process=str(row[2]),
            kind=cast(ExclusionKind, str(row[3])),
            min_rate=None if row[4] is None else float(cast(float, row[4])),
            min_month=None if row[5] is None else int(cast(int, row[5])),
        )
        for row in rows
    ]
