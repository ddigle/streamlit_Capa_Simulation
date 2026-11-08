# Purpose: 앱 스크립트 쪽 통합인증 — 매 회차 쿠키로 신원을 다시 검증하고 멈춤 화면·카드 줄을 낸다.

"""통합인증의 두 번째 벽(`app.py`).

문지기(`auth/gate.py`)가 첫 벽이다 — 쿠키 없는 요청은 앱에 닿지 않는다. 그래도 앱 스크립트가 매
회차 다시 본다. 문지기는 websocket 핸드셰이크 때 한 번 보고, 세션은 그 뒤로 몇 시간이고 이어진다:

- **만료** — 마지막 사용 뒤 유지 시간이 지났거나 최대 시간에 닿아도 열린 탭은 그대로 돈다. 열린
  탭의 쿠키는 핸드셰이크 때 것이라 갱신 표(`runtime.renewed_exp`)와 견준다.
- **로그아웃** — 다른 탭에서 로그아웃하면 그 세션 묶음(sid)이 폐기 목록에 오른다
  (`runtime.revoke_session`).
- **계정 바뀜** — 같은 Streamlit 세션이 다른 계정의 쿠키로 다시 이어질 수 있다.
- **명단 밖** — 접속 명단에서 빠진 사람의 쿠키는 서명이 맞아도 신원이 아니다
  (`identity.session_check` — 「다시 로그인」 은 콜백의 거절 화면으로 간다).
- **문지기 없음** — 통합인증을 켜는 설정인데 `streamlit run app.py` 로 떴다(진입점이 아님).

신원은 세션 상태가 아니라 `st.context.cookies` 의 HttpOnly 세션 쿠키에서 **매 회차** 다시
검증한다(서명 · aud · iss · 끝 시각 · 폐기 목록 · 접속 명단 — 문지기와 같은
`identity_from_cookies`). 세션 상태의 `SSO_LOGINID_KEY` 는 계정 바뀜을 가르려는 사본일 뿐이다.
쿠키는 websocket 연결 때 찍혀 그 연결 끝까지 같다 — 같은 Streamlit 세션이 다시 붙으면(재시작 · 망
끊김 뒤) 새 연결의 쿠키(갱신된 쿠키)를 보고, 테마 단추의 새로고침(`location.reload`)이 만든 새
세션도 쿠키를 다시 본다(실측). 재시작으로 갱신 표가 비어도 열린 탭이 사는 까닭이 이것이다. `?token=`
이나 질의 인자를 쓰지 않고 지우지도 않는다(`query_params.clear` 금지).

꺼짐(`ADFS_CLIENT_ID` 없음)이면 Streamlit 호출을 하나도 하지 않는다 — 개발 PC · 사내 WebIDE · 시험의
화면과 요소 순번이 지금과 같다.

멈춤 화면의 「다시 로그인」 · 앱 정보 카드의 「로그아웃」 은 같은 탭에서 열리게 원문 HTML 링크
(`target="_self"`)로 싣는다 — Streamlit 마크다운 링크는 늘 새 탭이다. 링크 주소의 바탕은
`CAPA_PUBLIC_URL` 이고 끼우는 사람 글(이름 · 부서)은 `literal_markdown` 으로 막는다(백슬래시로 막은
`<` 는 원문 HTML 이 되지 않는다).
"""

from __future__ import annotations

import html
import math
import time
from collections.abc import Mapping
from typing import NoReturn
from urllib.parse import urlencode, urlsplit

import streamlit as st

from capa_simulation.auth import access_store, names, runtime
from capa_simulation.auth.config import SsoConfig, SsoMode
from capa_simulation.auth.identity import (
    Identity,
    IdentityProblem,
    identity_from_cookies,
    session_end_of,
)
from capa_simulation.auth.web import (
    LIST_UNREAD_TEXT,
    NOT_ON_LIST_TEXT,
    public_link,
    sanitize_next,
)
from capa_simulation.components.app_header import render_shell_style
from capa_simulation.components.intro_overlay import SUMMARY_LABEL_ID
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.theme_toggle import (
    ALARM_BUTTON_ID,
    CHANGES_CHIP_ID,
    TOOLBAR_BUTTON_ORDER,
)

# 이 세션이 처음 본 계정(loginid). 매 회차 쿠키에서 다시 검증한 값과 견주어 계정 바뀜을 가른다 —
# 신원의 근거가 아니다.
SSO_LOGINID_KEY = "sso_signed_in_loginid"
# 앱 정보 카드에 남은 시간을 붙이기 시작하는 때(초) — 실제로 끝나는 시각 기준.
EXPIRY_WARNING_SECONDS = 30 * 60

# 앱 정보 카드 셋째 줄 끝의 남은 시간 — 쓰는 동안은 유휴 끝이 늘 멀어서 사실상 최대 시간 앞에만
# 선다. 유휴 끝 경고는 오래 쉬다 돌아온 첫 회차에 잠깐 보일 수 있다(그 글도 사실이다). 값(남은
# 시간)만 적고 하는 법(끝나기 전에 저장)은 HOME Guide 가 말한다(2026-11-08 사용자 답 b3).
CAP_WARNING_SUFFIX = " · 로그인 최대 시간까지 {minutes}분"
IDLE_WARNING_SUFFIX = " · 로그인 {minutes}분 남음"

EXPIRED_NOTICE = (
    "통합인증 로그인 시간이 끝났습니다(오래 쓰지 않았거나 로그인 최대 시간이 지났습니다). "
    "다시 로그인하면 이 탭에서 저장하지 않은 편집은 사라집니다."
)
REVOKED_NOTICE = "이 브라우저에서 로그아웃했습니다."
MISSING_NOTICE = "로그인 정보가 없습니다."
ACCOUNT_CHANGED_NOTICE = "다른 계정으로 바뀌었습니다 — 새로고침하세요."
NO_GATE_NOTICE = (
    f"통합인증을 켜는 설정(`{names.ENV_CLIENT_ID}`)인데 문지기 없이 앱이 시작됐습니다. "
    "`streamlit run capa_server.py` 로 띄워야 합니다(C-DEP 은 시작 스크립트가 그렇게 띄웁니다)."
)
LOGIN_AGAIN_LABEL = "다시 로그인"
LOGOUT_LABEL = "로그아웃"

_PROBLEM_NOTICES: Mapping[IdentityProblem, str] = {
    IdentityProblem.EXPIRED: EXPIRED_NOTICE,
    IdentityProblem.REVOKED: REVOKED_NOTICE,
    IdentityProblem.MISSING: MISSING_NOTICE,
    IdentityProblem.INVALID: MISSING_NOTICE,
    IdentityProblem.DENIED: NOT_ON_LIST_TEXT,
}

# 멈춤 화면이 감추는 툴바 단추 — 툴바 iframe 이 세운 Guide · Print · 테마. 앞 회차의 iframe 이 부모
# 문서에 세운 단추는 iframe 이 걷힌 뒤에도 남지만 듣개가 함께 죽어 눌러도 아무 일도 하지 않는다
# (브라우저 실측). 알림 칸이 세운 변경 칩 · Alarm 은 그 칸이 걷혀도 듣개가 살아 판이 열리므로 둔다 —
# 변경 칩은 새로고침하면 비는 이 세션의 변경 목록을 볼 마지막 자리다.
_STOP_HIDDEN_TOOLBAR_BUTTONS = tuple(
    button_id
    for button_id in TOOLBAR_BUTTON_ORDER
    if button_id not in (CHANGES_CHIP_ID, ALARM_BUTTON_ID)
)
# 같은 iframe 이 사이드바 머리칸에 세운 앱 이름 라벨(누르면 Summary)도 듣개가 함께 죽어 눌러도
# 반응이 없다 — 멈춤 화면에서 함께 감춘다(2026-11-08 사용자 답 b6).
_STOP_HIDDEN_IDS = (*_STOP_HIDDEN_TOOLBAR_BUTTONS, SUMMARY_LABEL_ID)
_STOP_TOOLBAR_STYLE = (
    "<style>"
    + ", ".join(f"#{element_id}" for element_id in _STOP_HIDDEN_IDS)
    + " { display: none !important; }</style>"
)


def session_cookies() -> Mapping[str, str]:
    """이 연결의 쿠키(websocket 연결 때 찍힌 값 — 다시 붙으면 새 연결의 값). 시험이 바꿔 끼운다."""
    return st.context.cookies


def current_page_url() -> str | None:
    """브라우저가 연 이 화면의 주소(질의 인자 없음). 시험이 바꿔 끼운다."""
    return st.context.url


def _now() -> int:
    return int(time.time())


def _same_tab_link(url: str, label: str) -> str:
    """같은 탭에서 여는 링크. 마크다운 링크는 Streamlit 이 늘 새 탭(`_blank`)으로 연다."""
    return f'<a href="{html.escape(url, quote=True)}" target="_self">{label}</a>'


def return_path(cfg: SsoConfig) -> str:
    """다시 로그인한 뒤 돌아올 앱 안 경로 — 지금 화면 경로와 질의 인자(테마 · 공정 같은 앱 인자).

    브라우저 주소에서 `CAPA_PUBLIC_URL` 의 경로 접두(WebIDE `/proxy/<포트>`)를 뗀다. 콜백이 그
    접두를 다시 붙인다. 정화(`sanitize_next`)를 지나지 못하면 `/` 다.
    """
    path = urlsplit(current_page_url() or "").path or "/"
    prefix = urlsplit(cfg.public_url).path.rstrip("/")
    if prefix and (path == prefix or path.startswith(prefix + "/")):
        path = path[len(prefix) :] or "/"
    pairs = [(key, value) for key in st.query_params for value in st.query_params.get_all(key)]
    query = urlencode(pairs)
    return sanitize_next(path + (f"?{query}" if query else ""))


def login_again_link(cfg: SsoConfig) -> str:
    target = f"{names.LOGIN_PATH}?{urlencode({'next': return_path(cfg)})}"
    return _same_tab_link(public_link(cfg, target), LOGIN_AGAIN_LABEL)


def _render_stop_chrome() -> None:
    """멈춤 화면의 머리 — 정상 회차와 같은 껍데기 스타일(⋮ 메뉴 · Deploy 감춤 · 인쇄 규칙)과 앞
    회차가 남긴 죽은 툴바 단추 · 사이드바 앱 이름 라벨 감춤. 멈춤은 `app.py` 가 껍데기 스타일을
    보내기 전이라 여기서 보낸다(스타일만 든 `st.html` 이라 자리를 먹지 않는다)."""
    render_shell_style()
    st.html(_STOP_TOOLBAR_STYLE)


def _stop_without_gate(cfg: SsoConfig) -> NoReturn:
    _render_stop_chrome()
    st.error(NO_GATE_NOTICE, icon=":material/gpp_bad:")
    if cfg.problems:
        lines = [f"`{problem.env}` — {problem.reason}" for problem in cfg.problems]
        st.caption("설정을 마치지 못한 환경변수  \n" + "  \n".join(lines))
    st.caption(f"안내 문서 `{names.SETUP_DOC}`")
    st.stop()


def signed_out_notice(cfg: SsoConfig, problem: IdentityProblem) -> str:
    """멈춤 화면 글. 명단 밖(`DENIED`)이어도 S3 명단을 아직 못 읽은 동안이면 「확인하지 못했습니다」
    다 — 재시작 뒤 S3 를 못 읽은 서버에서는 명단에 든 사람의 열린 탭도 여기서 멈춘다(거절 화면과
    같은 글 — `auth/web.LIST_UNREAD_TEXT`)."""
    if problem is IdentityProblem.DENIED and access_store.is_unread(cfg):
        return LIST_UNREAD_TEXT
    return _PROBLEM_NOTICES[problem]


def _stop_signed_out(cfg: SsoConfig, problem: IdentityProblem) -> NoReturn:
    _render_stop_chrome()
    st.warning(signed_out_notice(cfg, problem), icon=":material/lock_clock:")
    st.markdown(login_again_link(cfg), unsafe_allow_html=True)
    st.stop()


def _stop_account_changed() -> NoReturn:
    _render_stop_chrome()
    st.warning(ACCOUNT_CHANGED_NOTICE, icon=":material/switch_account:")
    st.stop()


def require_signed_in() -> Identity | None:
    """`app.py` 의 통합인증 확인. 꺼짐이면 `None`(아무것도 그리지 않는다), 켜짐이면 검증된 신원.

    로그인하지 않았거나 · 만료됐거나 · 로그아웃했거나 · 명단 밖이거나 · 계정이 바뀌었거나 · 문지기
    없이 떴으면 멈춤 화면을 그리고 `st.stop()` 한다 — 그 세션에는 입장 화면 · DB · 예약 스레드가
    돌지 않는다.
    """
    cfg = runtime.config()
    if cfg.mode is SsoMode.OFF:
        return None
    if not runtime.gate_installed() or cfg.mode is SsoMode.BROKEN:
        # 막힘이면 문지기가 websocket 을 닫아 여기에 닿지 않는다 — 닿았다면 문지기가 없는 것이다.
        _stop_without_gate(cfg)
    # 핸드셰이크 때 찍힌 쿠키라 그 뒤의 갱신은 갱신 표에 있다.
    found = identity_from_cookies(session_cookies(), cfg, _now(), renewals=True)
    if isinstance(found, IdentityProblem):
        _stop_signed_out(cfg, found)
    seen = st.session_state.get(SSO_LOGINID_KEY)
    if isinstance(seen, str) and seen != found.loginid:
        _stop_account_changed()
    st.session_state[SSO_LOGINID_KEY] = found.loginid
    return found


def verified_identity() -> Identity | None:
    """이 연결의 쿠키를 **지금** 다시 검증한 신원. 켜짐이 아니거나 유효하지 않으면 `None`.

    멈춤 화면을 그리지 않는다 — 쓰기 함수 · 위젯 콜백이 세션 상태를 믿지 않고 부른다.
    """
    cfg = runtime.config()
    if cfg.mode is not SsoMode.ON:
        return None
    found = identity_from_cookies(session_cookies(), cfg, _now(), renewals=True)
    return None if isinstance(found, IdentityProblem) else found


def sso_credit_line(identity: Identity | None, *, now: int | None = None) -> str | None:
    """앱 정보 카드 셋째 줄 — 「이름 · 부서 · 로그아웃」. 꺼짐(신원 없음)이면 `None`.

    이름이 없으면 loginid 를 싣고, 부서가 없으면 뺀다. 실제로 끝나는 시각(갱신 표까지 견준
    `session_end_of`) 30분 전부터 끝에 남은 시간을 붙인다 — 최대 시간이 정한 끝이면
    `CAP_WARNING_SUFFIX`, 마지막 사용 뒤 유지 시간이 정한 끝이면 `IDLE_WARNING_SUFFIX`. 이름 ·
    부서는 IdP 가 준 사람 글이라 `literal_markdown` 으로 막는다. 이 줄은 원문 HTML 을 허락한
    캡션으로 그린다(로그아웃 링크를 같은 탭에서 열려고).
    """
    if identity is None:
        return None
    cfg = runtime.config()
    parts = [literal_markdown(identity.display_name)]
    if identity.dept:
        parts.append(literal_markdown(identity.dept))
    parts.append(_same_tab_link(public_link(cfg, names.LOGOUT_PATH), LOGOUT_LABEL))
    line = " · ".join(parts)
    moment = _now() if now is None else now
    end, capped = session_end_of(identity, cfg, moment)
    left = end - moment
    if left <= EXPIRY_WARNING_SECONDS:
        minutes = max(1, math.ceil(left / 60))
        suffix = CAP_WARNING_SUFFIX if capped else IDLE_WARNING_SUFFIX
        line += suffix.format(minutes=minutes)
    return line
