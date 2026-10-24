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
from streamlit.runtime.scriptrunner import ScriptRunnerEvent
from streamlit.testing.v1.local_script_runner import LocalScriptRunner

import capa_simulation.settings as settings
from capa_simulation.components import space_layout_editor


def script_stopped_with_its_data(self: LocalScriptRunner) -> bool:
    """SHUTDOWN 이 목록에 들어오고 **그 이벤트의 데이터까지** 들어온 뒤에만 끝났다고 본다.

    Streamlit 1.63 AppTest 의 경쟁 상태를 막는다. 스크립트 스레드의 기록기는 `events` 에 먼저 넣고
    `event_data` 에 나중에 넣는데, 기다리는 쪽(`require_widgets_deltas`)은 `events` 에 SHUTDOWN 이
    보이는 순간 돌아가 `event_data[-1]["client_state"]` 를 읽는다. 그 사이에 데이터가 아직 안
    들어왔으면 직전 이벤트의 데이터를 읽어 `KeyError: 'client_state'` 로 죽는다 — 바쁜 PC 에서만
    드물게 난다(사내 202610061748 리뷰, `test_scenario_shift_ui`). 두 목록 길이가 같아질 때까지
    기다리게 바꾼다. Streamlit 을 올리면 이 대역이 아직 필요한지 다시 본다.
    """
    events = list(self.events)
    return ScriptRunnerEvent.SHUTDOWN in events and len(self.event_data) >= len(events)


# AppTest 가 쓰는 확인 함수를 위 판정으로 바꿔 끼운다. 모든 AppTest 가 같은 클래스를 쓰므로
# 한 번이면 된다.
LocalScriptRunner.script_stopped = script_stopped_with_its_data  # type: ignore[method-assign]


# 공식버전 자동 갱신 예약의 실행 줄 허락(`auto_update_scheduler.ENV_VAR`). 그 모듈을 여기서 읽으면
# 모든 시험이 수집 단계에서 러너·저장소까지 불러오므로 이름만 적는다 —
# `tests/test_auto_update_scheduler.py` 가 같은 이름인지 본다.
AUTO_UPDATE_ENV_VAR = "CAPA_AUTO_OFFICIAL_UPDATE"

# 저장소의 실제 DB 자리. 테스트가 경로를 갈아끼우기 **전** 값을 잡아 둔다.
_REPOSITORY_DATABASES = (settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH)
_EXISTED_AT_START: dict[str, bool] = {}


def pytest_sessionstart(session: pytest.Session) -> None:
    for path in _REPOSITORY_DATABASES:
        _EXISTED_AT_START[str(path)] = path.exists()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """테스트가 저장소의 `data/*.duckdb` 를 **새로 만들었으면** 실패로 끝낸다.

    격리를 빠뜨린 AppTest 스크립트는 오류 없이 저장소 DB 를 열고 마이그레이션까지 건다. 앱이 떠
    있는 main 에서는 잠금 오류로, 꺼진 main 에서는 실제 DB 변경으로 나타나 어느 쪽도 원인을
    가리키지 않는다. 처음에 없던 파일이 생겼을 때만 잡을 수 있으므로 DB 가 없는 작업 폴더·CI
    에서 걸린다. 만든 파일은 지워 다음 실행도 같은 조건에서 보게 한다.
    """
    created = [
        path
        for path in _REPOSITORY_DATABASES
        if not _EXISTED_AT_START.get(str(path), True) and path.exists()
    ]
    if not created:
        return
    for path in created:
        for leftover in (path, path.with_name(path.name + ".wal")):
            leftover.unlink(missing_ok=True)
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        names = ", ".join(str(path) for path in created)
        reporter.write_line(f"테스트가 저장소 DB 를 만들었습니다(지웠음): {names}", red=True)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def _without_auto_update_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """공식버전 자동 갱신 예약의 실행 줄 허락(`CAPA_AUTO_OFFICIAL_UPDATE`)을 뺀다.

    사내 런북은 앱을 띄운 창에 이 환경변수를 넣는다. 같은 창에서 pytest 를 돌리면 `app.py` 를 도는
    AppTest 가 tmp DB 로 예약 스레드를 세우고(시험이 끝나도 남는다), 「꺼짐」 안내를 보는 시험이
    실패한다. 허락이 필요한 시험은 `environ=` 를 따로 넘긴다.
    """
    monkeypatch.delenv(AUTO_UPDATE_ENV_VAR, raising=False)


@pytest.fixture(autouse=True)
def _without_container_start_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """CD 컨테이너 시작 점검 결과(`settings.CONTAINER_START_REPORT_PATH`)를 없는 자리로 돌린다.

    그 파일이 있으면 BigDataQuery 안내에 한 단락이 붙고 Admin Area 에 펼침이 선다. 작업 트리에서
    `scripts/container_start.py` 를 한 번 돌려 `data/temp/` 에 남으면 「지금 문구 그대로」를 보는
    시험이 그 트리에서만 깨진다. 결과 파일이 필요한 시험은 자리를 따로 옮긴다.
    """
    absent = tmp_path_factory.getbasetemp() / "absent-container-start.json"
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", absent)


@pytest.fixture(autouse=True)
def _restore_settings_paths() -> Iterator[None]:
    original = (settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH)
    yield
    settings.DUCKDB_PATH, settings.EQUIPMENT_DUCKDB_PATH = original


@pytest.fixture(autouse=True)
def _fresh_standard_target_availability() -> None:
    """주차별 가용대수 읽기 캐시(`equipment_cache.load_standard_target_availability`)를 테스트마다
    비운다.

    표준 목표·재공 현황 화면 대본 여럿이 설비 저장소를 가짜로 갈아끼우되 DB 경로는 저장소의 실제
    자리 그대로다. 캐시 키(경로·stat·쓰기 세대)가 테스트 사이에 같아, 비우지 않으면 앞 테스트의 가짜
    가용대수가 뒤 테스트에 적중한다(빈 표 안내를 보는 시험이 채운 표를 받는다). 모듈은 여기서 읽어
    수집 단계에 저장소까지 불러오지 않는다.
    """
    from capa_simulation.persistence import equipment_cache

    equipment_cache.clear_standard_target_availability_cache()


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
