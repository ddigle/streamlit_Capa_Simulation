# Purpose: 모든 테스트가 공유하는 자동 복원 장치를 한 곳에 둔다.

"""AppTest 스크립트가 갈아끼운 모듈 속성을 테스트마다 되돌린다.

AppTest 는 같은 프로세스에서 스크립트를 실행하므로 스크립트 안의
`settings.DUCKDB_PATH = ...` 가 그대로 남는다. 되돌리지 않으면 뒤에 도는 테스트가 앞
테스트의 tmp_path DB 를 조용히 보게 된다 — 실제로 네 파일이 그 상태였다. 스크립트마다
`try/finally` 를 넣는 대신 여기서 한 번 복원한다. 스크립트가 도중에 예외로 멈춰도 복원된다.
"""

from collections.abc import Iterator

import pytest

import capa_simulation.settings as settings


@pytest.fixture(autouse=True)
def _restore_settings_paths() -> Iterator[None]:
    original = (settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH)
    yield
    settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH = original
