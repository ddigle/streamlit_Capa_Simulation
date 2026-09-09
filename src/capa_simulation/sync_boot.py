# Purpose: managed 모드일 때만 동기화 사이드카 기록을 켠다.

"""앱 기동에서 한 번 부르는 동기화 등록.

`sync_state` 는 등록된 경로에만 파일을 쓴다. 그 등록을 여기서 한다 — `sync_state` 자체가
설정을 읽으면 저장 경로가 `io` 와 설정 파일에 묶이고, 그 모듈은 COMMIT 직후에 불리는
자리라 그런 의존을 둘 수 없다.

설정을 읽지 못하면 조용히 끈다. 동기화 표시 때문에 앱이 뜨지 못하는 일은 없어야 한다.
"""

from __future__ import annotations

from capa_simulation.io.object_storage import load_settings
from capa_simulation.persistence import sync_state
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH


def enable_sync_state_if_managed() -> bool:
    """`mode` 가 managed 일 때만 등록하고 그 여부를 돌려준다."""
    try:
        settings = load_settings()
    except (OSError, ValueError):
        return False
    if settings.mode != "managed":
        return False
    sync_state.enable({DUCKDB_PATH: "simulation", EQUIPMENT_DUCKDB_PATH: "equipment"})
    return True
