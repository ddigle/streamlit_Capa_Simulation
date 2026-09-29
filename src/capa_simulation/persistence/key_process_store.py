# Purpose: 시나리오와 분리된 공용 주요공정 프리셋의 조회·교체 SQL을 담당한다.

"""시나리오와 분리된 공용 주요공정 프리셋의 조회·교체 SQL.

헤더는 0024 의 `global_key_process`(version)이고 프리셋은 0028 의 두 표다. 0024 의 단일 목록
표(`global_key_process_item`)는 0028 이 「기본」 프리셋으로 옮긴 뒤로 읽지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import duckdb
import pandas as pd

from capa_simulation.persistence._sql_helpers import (
    insert_by_name,
    insert_profile_header,
    load_profile_header,
    reset_profile,
)
from capa_simulation.persistence.models import GlobalKeyProcess
from capa_simulation.services.key_process import Preset, normalize_key_processes

_PRESET_TABLE = "global_key_process_preset"
_PRESET_ITEM_TABLE = "global_key_process_preset_item"


def load_global_key_process_presets(connection: duckdb.DuckDBPyConnection) -> tuple[Preset, ...]:
    """저장된 차례 그대로 `(이름, 공정들)` 을 돌려준다. 공정 차례가 곧 히트맵 행 순서다."""
    names = connection.execute(
        f"""
        SELECT "프리셋"
        FROM app_meta.{_PRESET_TABLE}
        WHERE profile_id = 1
        ORDER BY "프리셋순서", "프리셋"
        """
    ).fetchall()
    rows = connection.execute(
        f"""
        SELECT "프리셋", "공정"
        FROM app_meta.{_PRESET_ITEM_TABLE}
        WHERE profile_id = 1
        ORDER BY "프리셋", "표시순서", "공정"
        """
    ).fetchall()
    members: dict[str, list[str]] = {}
    for preset, process in rows:
        members.setdefault(str(preset), []).append(str(process))
    return tuple(
        (str(name), normalize_key_processes(members.get(str(name), []))) for (name,) in names
    )


def insert_global_key_process_presets(
    connection: duckdb.DuckDBPyConnection,
    presets: Sequence[Preset],
    *,
    version: int,
    source: str,
) -> None:
    """헤더 한 행과 프리셋·공정 행을 넣는다. 프리셋이 0개여도 헤더는 기록한다.

    캐시 키가 version 을 보므로 「모두 지움」도 버전이 올라야 다른 세션이 무효화된다.
    """
    insert_profile_header(connection, "global_key_process", version=version, source=source)
    if not presets:
        return
    insert_by_name(
        connection,
        schema="app_meta",
        table_name=_PRESET_TABLE,
        frame=pd.DataFrame(
            {
                "profile_id": 1,
                "프리셋": [name for name, _ in presets],
                "프리셋순서": range(len(presets)),
            }
        ),
    )
    insert_by_name(
        connection,
        schema="app_meta",
        table_name=_PRESET_ITEM_TABLE,
        frame=pd.DataFrame(
            [
                {"profile_id": 1, "프리셋": name, "공정": process, "표시순서": order}
                for name, processes in presets
                for order, process in enumerate(processes)
            ]
        ),
    )


def load_global_key_process(connection: duckdb.DuckDBPyConnection) -> GlobalKeyProcess:
    """열린 연결에서 공용 프로필과 미저장 기본값을 복원한다."""
    metadata = load_profile_header(connection, "global_key_process")
    if metadata is None:
        return GlobalKeyProcess(version=0, source="", updated_at=None, presets=())
    return GlobalKeyProcess(
        version=metadata[0],
        source=metadata[1],
        updated_at=metadata[2],
        presets=load_global_key_process_presets(connection),
    )


def replace_global_key_process_presets(
    connection: duckdb.DuckDBPyConnection, normalized: Sequence[Preset], *, source: str
) -> None:
    """검증된 프리셋 묶음 전체를 교체한다. 호출자가 잠금과 트랜잭션을 소유한다."""
    version = reset_profile(connection, "global_key_process", _PRESET_ITEM_TABLE, _PRESET_TABLE)
    insert_global_key_process_presets(connection, normalized, version=version, source=source)
