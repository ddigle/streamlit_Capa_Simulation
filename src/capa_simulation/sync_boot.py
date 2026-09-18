# Purpose: managed 모드일 때만 동기화 사이드카 기록을 켠다.

"""앱 기동에서 한 번 부르는 동기화 등록.

`sync_state` 는 등록된 경로에만 파일을 쓴다. 그 등록을 여기서 한다 — `sync_state` 자체가
설정을 읽으면 저장 경로가 `io` 와 설정 파일에 묶이고, 그 모듈은 COMMIT 직후에 불리는
자리라 그런 의존을 둘 수 없다.

설정을 읽지 못하면 조용히 끈다. 동기화 표시 때문에 앱이 뜨지 못하는 일은 없어야 한다.
"""

from __future__ import annotations

from uuid import uuid4

from capa_simulation.io.object_storage import load_settings
from capa_simulation.persistence import sync_state
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

# 이 파이썬 프로세스 하나를 가리키는 값. 앱 서버가 살아 있는 동안 바뀌지 않고, 다시 켜면
# 새로 생긴다. 사람에게 보여 줄 이름이 아니라 "같은 인스턴스인가" 만 가리는 표식이다.
INSTANCE_ID = uuid4().hex[:12]

MANAGED_PATHS = {DUCKDB_PATH: "simulation", EQUIPMENT_DUCKDB_PATH: "equipment"}


def enable_sync_state_if_managed() -> bool:
    """`mode` 가 managed 일 때만 등록하고 그 여부를 돌려준다."""
    try:
        settings = load_settings()
    except (OSError, ValueError):
        return False
    if settings.mode != "managed":
        return False
    sync_state.enable(MANAGED_PATHS)  # type: ignore[arg-type]
    return True


def heartbeat_if_managed() -> None:
    """앱이 이 PC 에서 돌고 있다는 표시를 사이드카에 남긴다.

    DuckDB 파일은 프로세스 배타 잠금이라, 앱이 떠 있는 동안 `sync_object_storage.py` 의
    pull·push 는 DB 를 열지 못하고 `duckdb.IOException` 으로 끝난다. 그 메시지만으로는
    원인이 "앱이 켜져 있다" 라는 것을 알 수 없다. 심장박동이 있으면 스크립트가 DB 를 열기
    전에 그 사실을 읽어 사람 말로 알릴 수 있다.

    `touch_heartbeat` 이 10초에 한 번만 실제로 쓰므로 rerun 마다 불러도 된다. 등록되지
    않은(=managed 가 아닌) 환경에서는 그 안에서 곧바로 돌아가 파일을 만들지 않는다.
    """
    for path in MANAGED_PATHS:
        sync_state.touch_heartbeat(path, instance_id=INSTANCE_ID)
