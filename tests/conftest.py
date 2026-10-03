# Purpose: 모든 테스트가 공유하는 자동 복원 장치와 Space 편집기 컴포넌트 대역을 한 곳에 둔다.

"""AppTest 스크립트가 갈아끼운 모듈 속성을 테스트마다 되돌린다.

AppTest 는 같은 프로세스에서 스크립트를 실행하므로 스크립트 안의
`settings.DUCKDB_PATH = ...` 가 그대로 남는다. 되돌리지 않으면 뒤에 도는 테스트가 앞
테스트의 tmp_path DB 를 조용히 보게 된다 — 실제로 네 파일이 그 상태였다. 스크립트마다
`try/finally` 를 넣는 대신 여기서 한 번 복원한다. 스크립트가 도중에 예외로 멈춰도 복원된다.
"""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

import capa_simulation.settings as settings
from capa_simulation.components import space_layout_editor


@pytest.fixture(autouse=True)
def _restore_settings_paths() -> Iterator[None]:
    original = (settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH)
    yield
    settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH = original


@pytest.fixture(autouse=True)
def _stub_space_layout_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Space 편집기 컴포넌트(`_EDITOR`)를 아무것도 보내지 않는 대역으로 바꾼다.

    Space 첫 화면(FAB 전체)부터 이 컴포넌트다. AppTest 는 그 JS 를 못 돌리고, 한 프로세스의 두
    번째 AppTest 에서 진짜 컴포넌트를 부르면 「not registered」로 죽는다 — 페이지를 그리기만 하는
    테스트(전 페이지 렌더·내비게이션)도 그래서 대역이 필요하다. 받은 값을 보는 테스트는 제
    `monkeypatch.setattr` 로 이 위에 다시 덮는다."""

    def _silent(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(apply=None, navigate=None)

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _silent)
