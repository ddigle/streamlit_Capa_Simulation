# Purpose: AppTest 의 끝남 판정이 SHUTDOWN 이벤트의 데이터가 들어온 뒤에만 참이 되는지 검증한다.

from types import SimpleNamespace
from typing import Any, cast

from conftest import script_stopped_with_its_data
from streamlit.runtime.scriptrunner import ScriptRunnerEvent
from streamlit.testing.v1.local_script_runner import LocalScriptRunner


def _runner(events: list[ScriptRunnerEvent], data: list[dict[str, Any]]) -> LocalScriptRunner:
    return cast(LocalScriptRunner, SimpleNamespace(events=events, event_data=data))


def test_shutdown_without_its_data_is_not_finished_yet() -> None:
    """기록기가 SHUTDOWN 을 `events` 에만 넣고 데이터는 아직 못 넣은 순간이다."""
    events = [ScriptRunnerEvent.SCRIPT_STARTED, ScriptRunnerEvent.SHUTDOWN]
    assert not script_stopped_with_its_data(_runner(events, [{}]))


def test_shutdown_with_its_data_is_finished() -> None:
    events = [ScriptRunnerEvent.SCRIPT_STARTED, ScriptRunnerEvent.SHUTDOWN]
    assert script_stopped_with_its_data(_runner(events, [{}, {"client_state": object()}]))


def test_the_guard_is_installed_on_every_apptest_runner() -> None:
    assert LocalScriptRunner.script_stopped is script_stopped_with_its_data
