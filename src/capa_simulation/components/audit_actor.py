# Purpose: 감사 기록의 앱 쪽 — 스크립트 스레드 행위자 해석기 · 세션 시작 한 줄 · 회차 비우기를 둔다.

"""감사 기록기와 Streamlit 사이(`capa_server.py` · `app.py` 가 부른다).

- **해석기**(`resolve`) — 저장소 쓰기 · 위젯 콜백이 기록할 때 이 연결의 쿠키를 **지금** 다시
  검증한 loginid 를 행위자로 준다(`sso_identity.verified_identity`). 콜백은 `app.py` 본문보다 먼저
  돌아 회차 앞에서 정한 값을 믿지 않는다. 실행 문맥이 없는 스레드면 `None`(기록기가 빈 행위자로
  남긴다 — 예약 · 일꾼은 스레드 이름으로 먼저 가른다).
- **세션 시작**(`note_session`) — `require_signed_in()` 을 지난 뒤 그 Streamlit 세션의 첫 회차에만
  `session_created` 한 줄(세션 칸 표지 하나).
- **비우기**(`drain`) — 부트스트랩 바로 뒤. 큐가 비었으면 파일 IO 가 없다.

통합인증이 꺼진 곳에서는 `app.py` 가 이 모듈을 부르지 않는다(신원이 없으면 부르지 않는다).
"""

from __future__ import annotations

import hashlib
import logging

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation.audit import recorder, spool
from capa_simulation.auth.identity import Identity

_LOGGER = logging.getLogger(__name__)

# 이 Streamlit 세션의 `session_created` 를 남겼다는 표지(값 없음).
SESSION_NOTED_KEY = "audit_session_noted"


def tab_tag(session_id: str) -> str:
    """Streamlit 세션 id 의 SHA-256 앞 8자 — 세션 id 원문은 싣지 않는다."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]


def resolve() -> recorder.Actor | None:
    """지금 이 스레드의 인증 신원. 실행 문맥이 없거나 신원이 없으면 `None`."""
    if get_script_run_ctx(suppress_warning=True) is None:
        return None
    from capa_simulation.components import sso_identity

    identity = sso_identity.verified_identity()
    if identity is None:
        return None
    loginid = recorder.normalize_actor(identity.loginid)
    return recorder.Actor(loginid, True, recorder.grade_of(loginid))


def install() -> None:
    """기록기가 켜졌으면 해석기를 꽂는다(진입 파일이 기동 때 한 번)."""
    if recorder.enabled():
        recorder.set_resolver(resolve)


def note_session(identity: Identity) -> None:
    """이 Streamlit 세션의 첫 회차에만 `session_created` 한 줄."""
    if not recorder.enabled() or st.session_state.get(SESSION_NOTED_KEY):
        return
    st.session_state[SESSION_NOTED_KEY] = True
    ctx = get_script_run_ctx(suppress_warning=True)
    recorder.record(
        "session_created",
        actor=identity.loginid,
        verified=True,
        sid8=identity.sid[:8],
        tab8=None if ctx is None else tab_tag(ctx.session_id),
        ip="",
    )


def drain() -> None:
    """큐에 쌓인 것을 스풀에 적는다(대개 0 — 파일 IO 없음). 실패해도 화면을 멈추지 않는다."""
    if not recorder.enabled():
        return
    try:
        spool.drain()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("감사 기록을 스풀에 비우지 못했습니다.")
