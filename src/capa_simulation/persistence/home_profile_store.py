# Purpose: HOME 공용 Top5 구간·공지·GAP 비교 대상·주요 Case 의 조회와 교체 SQL을 담당한다.

"""HOME 공용 단일행 프로필. 연결과 트랜잭션은 Repository가 소유한다."""

from __future__ import annotations

import duckdb

from capa_simulation.persistence._sql_helpers import (
    ProfileVersionConflict,
    require_profile_version,
    reset_profile,
)
from capa_simulation.persistence.models import (
    GlobalComparisonScenario,
    GlobalMainCases,
    GlobalSummaryNote,
    GlobalTop5Band,
)
from capa_simulation.services.top5_band import DEFAULT_TOP5_MAX_RATE, DEFAULT_TOP5_MIN_RATE

# 주요 Case 를 비운 까닭 — 비우기가 출처 칸에 「Case2 지정 비움 — <까닭>」 으로 남겨 상자 아래
# 버전 캡션이 보인다(`clear_global_main_cases`).
MAIN_CASE_CLEARED_ARCHIVED = "시나리오 보관"
MAIN_CASE_CLEARED_DELETED = "시나리오 영구 삭제"
MAIN_CASE_CLEARED_VANISHED = "목록에 없는 시나리오"


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
    connection: duckdb.DuckDBPyConnection,
    min_rate: float,
    max_rate: float,
    *,
    source: str,
    expected_version: int | None = None,
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다.

    `expected_version`(편집을 시작할 때 본 version)이 지금 저장본과 다르면 아무것도 쓰지 않고
    `ProfileVersionConflict` 를 올린다. None 이면 대조하지 않는다.
    """
    require_profile_version(
        connection, "global_top5_band", expected_version, label="Top5 확보율 구간"
    )
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
    connection: duckdb.DuckDBPyConnection,
    note: str,
    *,
    source: str,
    expected_version: int | None = None,
) -> None:
    """검증된 프로필을 교체한다. 호출자가 잠금과 트랜잭션을 소유한다.

    `expected_version` 은 Top5 구간과 같다 — 다르면 쓰지 않고 `ProfileVersionConflict` 다.
    """
    require_profile_version(
        connection, "global_summary_note", expected_version, label="Summary 공지"
    )
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


def load_global_main_cases(connection: duckdb.DuckDBPyConnection) -> GlobalMainCases:
    """열린 연결에서 주요 Case 공용 프로필과 미저장 기본값(네 칸 모두 비움)을 복원한다."""
    row = connection.execute(
        """
        SELECT case1_scenario_id, case1_revision_id, case2_scenario_id, case2_revision_id,
               version, source, updated_at
        FROM app_meta.global_main_cases
        WHERE profile_id = 1
        """
    ).fetchone()
    if row is None:
        return GlobalMainCases(version=0, source="", updated_at=None)
    return GlobalMainCases(
        version=int(row[4]),
        source=str(row[5]),
        updated_at=row[6],
        case1_scenario_id=None if row[0] is None else str(row[0]),
        case1_revision_id=None if row[1] is None else str(row[1]),
        case2_scenario_id=None if row[2] is None else str(row[2]),
        case2_revision_id=None if row[3] is None else str(row[3]),
    )


def replace_global_main_case(
    connection: duckdb.DuckDBPyConnection,
    case_no: int,
    scenario_id: str | None,
    revision_id: str | None,
    *,
    source: str,
    expected_version: int | None = None,
    expected_scenario_id: str | None = None,
) -> None:
    """Case 하나(1·2)의 짝만 바꾸고 다른 Case 는 지금 행 그대로 둔다. 호출자가 쓰기 트랜잭션을 쥔다.

    두 Case 를 한 행에 두므로 통째 교체면 남이 방금 고른 다른 Case 를 이쪽 화면의 옛 값으로 덮는다.
    지금 행을 **같은 쓰기 트랜잭션 안에서** 읽어 나머지 Case 를 옮겨 적는다. 대조 둘은 맞지 않으면
    아무것도 쓰지 않고 `ProfileVersionConflict` 를 올린다.

    - `expected_version` — 프로필 전체 version(화면이 스스로 메우는 쓰기 — 그 사이 남이 고른 값을
      덮지 않게).
    - `expected_scenario_id` — 그 Case 의 지금 시나리오(리비전만 고른 쓰기). 리비전 상자는 화면이 본
      시나리오의 리비전이라, 그 사이 남이 그 Case 의 시나리오를 바꿨으면 이쪽 짝으로 통째 덮어 남의
      시나리오 고름을 되돌리게 된다. 다른 Case 나 이름 바꾸기로 오른 version 은 막지 않는다. `None`
      이면 대조하지 않는다.
    """
    require_profile_version(connection, "global_main_cases", expected_version, label="주요 Case")
    current = load_global_main_cases(connection)
    if expected_scenario_id is not None and current.case(case_no)[0] != expected_scenario_id:
        raise ProfileVersionConflict(
            f"다른 사용자가 먼저 Case{case_no} 의 시나리오를 바꿔 고른 리비전은 저장하지 "
            "않았습니다. 지금 지정을 확인한 뒤 다시 고르세요."
        )
    pairs = {number: current.case(number) for number in (1, 2)}
    pairs[case_no] = (scenario_id, revision_id)
    version = reset_profile(connection, "global_main_cases")
    connection.execute(
        """
        INSERT INTO app_meta.global_main_cases
            (profile_id, case1_scenario_id, case1_revision_id,
             case2_scenario_id, case2_revision_id, version, source)
        VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        [*pairs[1], *pairs[2], version, source],
    )


def touch_global_main_cases(connection: duckdb.DuckDBPyConnection, scenario_id: str) -> None:
    """어느 Case 든 이 시나리오를 가리키면 `version` 만 올린다(시나리오 이름을 바꿨을 때).

    가리키는 대상은 그대로다. 슬롯 글자(`services/main_cases.case_slot_label`)는 시나리오 이름을
    쓰므로 이 version 을 키로 삼는 캐시가 옛 이름을 들고 있지 않게 한다. 캐시는 경로 키라 호출부가
    비운다(`clear_global_main_cases_cache`).
    """
    connection.execute(
        """
        UPDATE app_meta.global_main_cases
        SET version = version + 1
        WHERE case1_scenario_id = ? OR case2_scenario_id = ?
        """,
        [scenario_id, scenario_id],
    )


def touch_global_main_cases_revision(
    connection: duckdb.DuckDBPyConnection, revision_id: str
) -> None:
    """어느 Case 든 이 리비전을 가리키면 `version` 만 올린다(리비전명을 바꿨을 때).

    슬롯 글자는 「시나리오명 · r{번호} · 리비전명」 이라 리비전명도 싣는다 — 시나리오 이름 바꾸기
    (`touch_global_main_cases`)와 같은 까닭이다. 가리키는 대상은 그대로이고 캐시는 호출부가 비운다.
    """
    connection.execute(
        """
        UPDATE app_meta.global_main_cases
        SET version = version + 1
        WHERE case1_revision_id = ? OR case2_revision_id = ?
        """,
        [revision_id, revision_id],
    )


def clear_global_main_cases(
    connection: duckdb.DuckDBPyConnection, scenario_id: str, *, reason: str
) -> None:
    """이 시나리오를 가리키는 Case 만 비운다(보관·영구 삭제·목록에 없는 시나리오).

    다른 Case 는 그대로이고, 가리키는 Case 가 없으면 쓰지 않는다. 시나리오와 리비전 칸을 함께
    비운다 — 표의 `CHECK (caseN_revision_id IS NULL OR caseN_scenario_id IS NOT NULL)` 때문에
    한쪽만 비우면 제약에 걸린다. 다른 교체와 같은 결로 `version` 을 올리고 **출처·저장 시각도 이
    비우기로 적는다**(「Case2 지정 비움 — 시나리오 보관」) — 공용 지정이라 비운 화면을 보지 못한
    사람도 상자 아래 버전 캡션에서 까닭을 읽는다. 캐시는 호출부가 비운다
    (`clear_global_main_cases_cache`).
    """
    current = load_global_main_cases(connection)
    hits = [number for number in (1, 2) if current.case(number)[0] == scenario_id]
    if not hits:
        return
    pairs = {number: (None, None) if number in hits else current.case(number) for number in (1, 2)}
    cases = "·".join(f"Case{number}" for number in hits)
    connection.execute(
        """
        UPDATE app_meta.global_main_cases
        SET case1_scenario_id = ?, case1_revision_id = ?,
            case2_scenario_id = ?, case2_revision_id = ?,
            version = version + 1, source = ?, updated_at = current_timestamp
        WHERE profile_id = 1
        """,
        [*pairs[1], *pairs[2], f"{cases} 지정 비움 — {reason}"],
    )
