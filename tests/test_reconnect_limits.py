# Purpose: 재시작 · 세션 만료 뒤 열어 둔 탭의 남은 한계가 기대는 Streamlit 동작을 붙든다.

"""`docs/TODO.md` 4장의 두 물음(「프래그먼트 · 대화상자 안 저장이 조용히 버려진다」 · 「세션만
사라진 탭」)이 기대는 Streamlit 동작이다. 앱의 동작을 정답으로 박는 시험이 아니라 파수다 —
Streamlit 을 올려 하나라도 바뀌면 두 물음과 AGENTS 9장 「서버 재시작 알림」 의 사실부터 본다."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import streamlit
from streamlit import config
from streamlit.proto.ClientState_pb2 import ClientState
from streamlit.runtime.app_session import AppSession, AppSessionState
from streamlit.runtime.fragment import MemoryFragmentStorage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TTL_OPTION = "server.disconnectedSessionTTL"


def test_a_press_from_a_fragment_the_new_session_does_not_know_starts_no_run() -> None:
    """새 세션의 프래그먼트 저장소는 비어 있어 앞 세션 프래그먼트의 요청은 회차 없이 돌아간다 —
    콜백이 돌지 않으니 저장 실패 글도 `GL-07` 도 나올 자리가 없다. 저장이 버려지는 밑바닥이다."""
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
    """다시 붙은 탭의 회차는 Streamlit 프런트가 정한다 — 마지막 회차가 프래그먼트였거나 `run_every`
    프래그먼트가 있을 때만 요청한다. 마지막이 앱 전체였던 탭은 다음 조작까지 옛 화면이라 위 시험의
    길에 들어선다."""
    bundles = Path(streamlit.__file__).parent.glob("static/static/js/index.*.js")
    rule = [
        text
        for path in bundles
        if "Requesting a script run" in (text := path.read_text(encoding="utf-8"))
    ]
    assert len(rule) == 1
    assert "this.state.fragmentIdsThisRun.length>0||this.autoRerunIntervals.size>0" in rule[0]


def test_a_disconnected_session_is_kept_for_the_default_two_minutes() -> None:
    """끊긴 세션은 2분까지만 남는다 — 그 뒤 다시 붙으면 서버가 그대로여도 새 세션이고 미저장 고침이
    사라진다. 값을 바꾸면 4장 「세션만 사라진 탭」 의 고르기도 같이 고친다."""
    assert config.get_option(TTL_OPTION) == 120
    assert "disconnectedSessionTTL" not in (PROJECT_ROOT / ".streamlit/config.toml").read_text(
        encoding="utf-8"
    )
