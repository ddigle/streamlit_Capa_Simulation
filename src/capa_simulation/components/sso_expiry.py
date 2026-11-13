# Purpose: 로그인 최대 시간 10분 전 첫 회차에 「저장해 두세요」 사건 알림(AD-20)을 한 번 담는다.

"""로그인 최대 시간 10분 전 알림(2026-11-13 「앱 대신 뜨는 화면」 보드 카드 p1-expiry).

통합인증 로그인은 쓰는 동안 늘지만(마지막 사용 뒤 유지 시간) 처음 로그인에서 최대 시간
(`CAPA_SSO_SESSION_MAX_HOURS`, 기본 24시간)을 넘지 못한다. 앱 정보 카드 셋째 줄은 30분 전부터 남은
시간을 값으로 싣는다(`sso_identity.sso_credit_line` — 값만 두는 꼴을 지킨다). 그 줄은 사이드바 맨
아래 작은 글이라 놓치기 쉬워, 최대 시간이 정한 끝이 `ALERT_SECONDS` 안으로 들어온 첫 회차에 사건
알림 `AD-20` 을 **한 번** 담는다.

- 쓰지 않아 끝나는 끝(유휴)은 쓰는 동안 늘어 알림이 필요 없다 — 최대 시간이 정한 끝일 때만이다.
- 「지금 다시 로그인」 단추는 두지 않는다 — 로그인 경로는 이미 로그인한 사람의 처음 로그인 시각을
  새로 만들지 않아 눌러도 끝이 늘지 않는다.
- 한 번: 세션 칸(`ALERTED_KEY` — 그 로그인 묶음 sid)이 같은 세션의 다음 회차를 막고, 고정 id(sid 의
  지문)가 같은 브라우저 탭의 새 세션(새로고침 · 테마 전환)을 막는다(`alerts.event` 의 `alert_id`).
- 짧은 글의 분은 그 회차의 남은 분(올림)이다 — 회차는 사람이 누를 때 돌아 10분 창 안 어느 때나 첫
  회차가 될 수 있다.

꺼짐(신원 없음)이면 부르지 않는다 — `app.py` 가 신원이 있을 때만 부른다. 담기만 하므로 이벤트 칸을
쓰지 않는다(요소 순번 그대로). 어느 화면의 일도 아니라 화면 · 주소를 싣지 않는다(`pageless` — 이
회차의 화면은 `app.py` 가 이 뒤에야 적으므로 실으면 앞 회차의 화면이 된다).
"""

from __future__ import annotations

import math
import time

import streamlit as st

from capa_simulation import alerts
from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.identity import Identity, session_end_of

ALERT_CODE = "AD-20"
# 최대 시간이 정한 끝이 이 안으로 들어오면 알린다(초).
ALERT_SECONDS = 10 * 60
# 이 세션이 알린 로그인 묶음(sid) — 같은 묶음이면 다시 담지 않는다.
ALERTED_KEY = "sso_expiry_alerted_sid"
SHORT_TEXT = "로그인 최대 시간까지 {minutes}분 — 저장해 두세요"
FULL_TEXT = (
    "{period} 통합인증을 다시 확인합니다. 끝나면 다시 로그인해야 하고 저장하지 않은 편집은 "
    "사라집니다."
)


def _period(cfg: SsoConfig) -> str:
    """최대 시간을 사람 말로 — 기본 24시간은 「하루 한 번」, 그 밖은 「n시간에 한 번」."""
    hours = cfg.session_max_seconds // 3600
    return "하루 한 번" if hours == 24 else f"{hours}시간에 한 번"


def expiry_alert_id(identity: Identity) -> str:
    """그 로그인 묶음의 고정 알림 id — 같은 브라우저 탭이 한 번만 띄운다."""
    return f"{ALERT_CODE}-{alerts.fingerprint(ALERT_CODE, None, identity.sid)}"


def minutes_to_cap(identity: Identity, cfg: SsoConfig, now: int) -> int | None:
    """최대 시간이 정한 끝까지 남은 분(올림, 1 이상). 그 끝이 아니거나 `ALERT_SECONDS` 밖이면
    `None`."""
    end, capped = session_end_of(identity, cfg, now)
    left = end - now
    if not capped or left > ALERT_SECONDS or left <= 0:
        return None
    return max(1, math.ceil(left / 60))


def note_expiry_alert(identity: Identity, *, now: int | None = None) -> None:
    """최대 시간 10분 전 첫 회차에 `AD-20` 을 한 번 담는다(그리지 않는다)."""
    if st.session_state.get(ALERTED_KEY) == identity.sid:
        return
    cfg = runtime.config()
    minutes = minutes_to_cap(identity, cfg, int(time.time()) if now is None else now)
    if minutes is None:
        return
    st.session_state[ALERTED_KEY] = identity.sid
    alerts.event(
        ALERT_CODE,
        text=SHORT_TEXT.format(minutes=minutes),
        full=FULL_TEXT.format(period=_period(cfg)),
        alert_id=expiry_alert_id(identity),
        pageless=True,
    )
