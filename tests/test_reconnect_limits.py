# Purpose: 다시 붙은 탭의 재연결 회차와 세션 만료 알림이 기대는 Streamlit 동작을 붙든다.

"""2026-11-07 2차 보드 R1 · R2 (가) — 알림 칸이 다시 붙은 탭에 앱 전체 회차를 한 번 부르고 세션이
사라진 탭에 `GL-08` 을 띄우는 까닭과 길이 기대는 Streamlit 동작이다. 앞 세션의 탭이 든 위젯 값을
새 세션에서 가르는 길(`widget_generation.note_session_start`)도 함께 붙든다. 앱의 동작을 정답으로
박는 시험이 아니라 파수다 — Streamlit 을 올려 하나라도 바뀌면 재연결 회차가 아직 필요한지, 표지를
그대로 읽을 수 있는지를 AGENTS 9장 「서버 재시작 알림」 과 함께 다시 본다."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import streamlit
from streamlit import config
from streamlit.proto.ClientState_pb2 import ClientState
from streamlit.proto.WidgetStates_pb2 import WidgetState, WidgetStates
from streamlit.runtime.app_session import AppSession, AppSessionState
from streamlit.runtime.fragment import MemoryFragmentStorage
from streamlit.runtime.state import SafeSessionState, SessionState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TTL_OPTION = "server.disconnectedSessionTTL"


def test_a_press_from_a_fragment_the_new_session_does_not_know_starts_no_run() -> None:
    """새 세션의 프래그먼트 저장소는 비어 있어 앞 세션 프래그먼트의 요청은 회차 없이 돌아간다 —
    콜백이 돌지 않아 저장이 버려진다. 재연결 회차가 앱 전체 요청으로 부르는 까닭이다(아래 줄의
    빈 `ClientState` 는 회차가 선다)."""
    started: list[object] = []
    session = SimpleNamespace(
        _state=AppSessionState.APP_NOT_RUNNING,
        _fragment_storage=MemoryFragmentStorage(),
        _client_state=ClientState(),
        _scriptrunner=None,
        _create_scriptrunner=started.append,
    )

    AppSession.request_rerun(cast(AppSession, session), ClientState(fragment_id="앞 세션의 칸"))
    assert started == []

    AppSession.request_rerun(cast(AppSession, session), ClientState())
    assert len(started) == 1


def test_a_reconnected_tab_asks_for_a_run_only_after_a_fragment_run() -> None:
    """Streamlit 프런트는 회차가 돌던 탭 · 마지막 회차가 프래그먼트였던 탭 · `run_every`
    프래그먼트가 있는 탭에만 스스로 회차를 요청한다. 마지막이 앱 전체였던 탭은 요청하지 않아 알림
    칸이 부르고, 스스로 요청하는 탭과 겹치지 않게 약 300ms 기다린다(`RECONNECT_WAIT_MS`)."""
    bundles = Path(streamlit.__file__).parent.glob("static/static/js/index.*.js")
    rule = [
        text
        for path in bundles
        if "Requesting a script run" in (text := path.read_text(encoding="utf-8"))
    ]
    assert len(rule) == 1
    assert "this.state.fragmentIdsThisRun.length>0||this.autoRerunIntervals.size>0" in rule[0]


def test_the_front_writes_the_two_marks_the_alert_center_watches() -> None:
    """알림 칸은 앱 뿌리의 두 표지를 관찰자 하나로 본다 — 비공식 표지다. 사라지면 재연결 회차가 서지
    않을 뿐 앱은 돈다(그 탭은 앞의 조용한 저장 버림으로 돌아간다)."""
    bundles = Path(streamlit.__file__).parent.glob("static/static/js/index.*.js")
    rule = [
        text
        for path in bundles
        if "Requesting a script run" in (text := path.read_text(encoding="utf-8"))
    ]
    assert len(rule) == 1
    assert '"data-testid":`stApp`,"data-test-script-state":' in rule[0]
    assert '"data-test-connection-state":' in rule[0]
    assert "CONNECTED=`CONNECTED`" in rule[0]


def test_a_reconnected_page_reports_the_socket_opening_as_its_own_state() -> None:
    """알림 칸은 프런트 회차의 표지가 닿을 왕복 시간을 소켓이 붙는 시간으로 어림한다 — 연결 표지가
    `CONNECTING` 을 지나야 잰다. 사라지면 300ms 만 기다릴 뿐 앱은 돈다."""
    bundles = Path(streamlit.__file__).parent.glob("static/static/js/index.*.js")
    rule = [
        text
        for path in bundles
        if "Requesting a script run" in (text := path.read_text(encoding="utf-8"))
    ]
    assert len(rule) == 1
    assert "CONNECTING=`CONNECTING`" in rule[0]


def test_the_first_run_of_a_session_can_read_what_the_browser_kept() -> None:
    """브라우저는 새 세션에도 든 위젯 값을 그대로 보낸다 — 회차가 서기 전에 세션 상태에 실려, 첫
    회차 맨 앞에서 어떤 위젯도 그리기 전에 읽힌다(`note_session_start`). 값이 없는 새 탭 ·
    새로고침과 가르는 유일한 길이다. 사라지면 편집표의 앞 세션 고침이 다시 되살아난다."""
    fresh = SafeSessionState(SessionState(), lambda: None)
    fresh.on_script_will_rerun(WidgetStates())
    assert fresh.get_widget_states() == []

    sent = WidgetStates(widgets=[WidgetState(id="$$ID-앞세션-표", string_value="고침")])
    rejoined = SafeSessionState(SessionState(), lambda: None)
    rejoined.on_script_will_rerun(sent)
    assert [state.id for state in rejoined.get_widget_states()] == ["$$ID-앞세션-표"]


def test_a_disconnected_session_is_kept_for_the_default_two_minutes() -> None:
    """끊긴 세션은 2분까지만 남는다 — 그 뒤 다시 붙으면 서버가 그대로여도 새 세션이고 미저장 고침이
    사라져 `GL-08` 이 뜬다. 값을 바꾸면 Guide 「2분」 글과 AGENTS 9장을 같이 고친다."""
    assert config.get_option(TTL_OPTION) == 120
    assert "disconnectedSessionTTL" not in (PROJECT_ROOT / ".streamlit/config.toml").read_text(
        encoding="utf-8"
    )
