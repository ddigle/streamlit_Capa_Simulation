# Purpose: 앱 스크립트 쪽 통합인증 — 매 회차 쿠키로 신원 · 접속 등급을 다시 판정하고 멈춤 화면·카드
# 줄을 낸다.

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

**접속 등급**(`auth/grades.py`)도 여기서 정한다 — 판정 셋이다.

- **실제 등급**(`real_caller` — 쓰는 순간의 벽이 꽂아 쓰는 판정기, `components/grade_ui.install`):
  운영 아님(개발 `app.py` · 사내 WebIDE · 사내 PC) → 제한 없음, 앱 자신의 쓰기
  (`audit.recorder.as_system` · 예약 · 일꾼 스레드) → 제한 없음, 운영 + 통합인증 꺼짐 →
  관리자(개발자 몫만 막힘 — 지금 동작 그대로), 실행 문맥 없는 낯선 스레드 → 열람, 운영 + 켜짐 →
  쿠키를 지금 다시 검증한 신원의 등급(`grade_store.grade_of`), 신원이 없으면 로그인 끝남. 세션 칸을
  읽지 않는다(잠금 안 쓰기에서도 불린다).
- **화면 등급**(`screen_grade` · `viewer_can` — 숨김 · 값만 · 탭 목록 · 카드 표지 · 사람 몫 자동
  쓰기의 판정): 실제 등급이 개발자이고 운영 + 켜짐일 때만 「이 등급으로 보기」(`GRADE_PREVIEW_KEY` —
  그 창의 세션 칸)를 따른다. 저장은 늘 실제 등급이다.
- **실제 개발자**(`viewer_is_developer` — 환경변수 개발자 ∪ 명단 `admin`, 켜짐이 아니면 늘 거짓):
  Admin 의 두 번째 벽(공지 · BigDataQuery · 동기화 · 공용 표 붙여넣기)과 「이 등급으로 보기」 의
  자격.

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
from typing import Final, NoReturn
from urllib.parse import urlencode, urlsplit

import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.auth import access_store, grade_store, grades, names, runtime
from capa_simulation.auth.config import SsoConfig, SsoMode
from capa_simulation.auth.gate import ended_reason
from capa_simulation.auth.identity import (
    Identity,
    IdentityProblem,
    identity_from_cookies,
    session_end_of,
)
from capa_simulation.auth.web import (
    LIST_UNREAD,
    LIST_UNREAD_TEXT,
    NOT_ON_LIST,
    NOT_ON_LIST_TEXT,
    REGISTER_LABEL,
    public_link,
    sanitize_next,
)
from capa_simulation.components.app_header import render_shell_style
from capa_simulation.components.intro_overlay import SUMMARY_LABEL_ID
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.stop_panel import (
    AdminFold,
    primary_link,
    render_stop_footer,
)
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
# 계정 바뀜 경고의 꼬리 — 앞에 새 계정의 표시 이름(「…」)이 선다(`account_changed_notice`).
ACCOUNT_CHANGED_TAIL = " 계정으로 바뀌었습니다"
# 문지기 없이 뜬 앱(카드 p2-config) — 누구나 읽는 경고 한 줄. 실행 명령 · 환경변수 이름 · 문서
# 경로는 개발자 몫에만 서는 접힌 「개발자용 진단」 의 `NO_GATE_DIAGNOSTIC` 에만 둔다.
NO_GATE_NOTICE = "지금은 앱을 열 수 없습니다(서버 시작 설정)"
NO_GATE_DIAGNOSTIC = (
    f"통합인증을 켜는 설정(`{names.ENV_CLIENT_ID}`)인데 문지기 없이 앱이 시작됐습니다. "
    "`streamlit run capa_server.py` 로 띄워야 합니다(C-DEP 은 시작 스크립트가 그렇게 띄웁니다)."
)
NO_GATE_PROBLEMS_CAPTION = "설정을 마치지 못한 환경변수"
# 참고 줄의 사유 낱말(새 번호 체계 없음 — 앱 안 멈춤 판의 갈래 키).
NO_GATE_REFERENCE = "sso_no_gate"
# 로그인 끝남 · 계정 바뀜 멈춤의 사유 낱말. 명단 밖 · 명단 못 읽음은 거절 화면의 바닥 참고 줄과 같은
# 낱말(`web.NOT_ON_LIST` · `web.LIST_UNREAD`)이고, 쿠키 없음 · 위조는 글이 같아 한 낱말이다.
ACCOUNT_CHANGED_REFERENCE = "sso_account_changed"
NO_GATE_DIAGNOSTIC_KEY = "sso_no_gate_diagnostic"
NO_GATE_DIAGNOSTIC_TITLE = "문지기 없이 시작됨 진단"
NO_GATE_COPY_KEY = "sso_no_gate"
LOGIN_AGAIN_LABEL = "다시 로그인"
REFRESH_LABEL = "새로고침"
# 「새로고침」 을 누르기 전에 알아야 하는 되돌릴 수 없는 결과(설계 규칙 UI-NTF-09) — 풍선.
REFRESH_TIP = "이 탭에서 저장하지 않은 편집은 사라집니다"
LOGOUT_LABEL = "로그아웃"

_PROBLEM_NOTICES: Mapping[IdentityProblem, str] = {
    IdentityProblem.EXPIRED: EXPIRED_NOTICE,
    IdentityProblem.REVOKED: REVOKED_NOTICE,
    IdentityProblem.MISSING: MISSING_NOTICE,
    IdentityProblem.INVALID: MISSING_NOTICE,
    IdentityProblem.DENIED: NOT_ON_LIST_TEXT,
}
_PROBLEM_REFERENCES: Mapping[IdentityProblem, str] = {
    IdentityProblem.EXPIRED: "sso_expired",
    IdentityProblem.REVOKED: "sso_revoked",
    IdentityProblem.MISSING: "sso_missing",
    IdentityProblem.INVALID: "sso_missing",
    IdentityProblem.DENIED: NOT_ON_LIST,
}

# 멈춤 화면이 감추는 툴바 단추 — 툴바 iframe 이 세운 Guide · Print · 테마. 앞 회차의 iframe 이 부모
# 문서에 세운 단추는 iframe 이 걷힌 뒤에도 남지만 듣개가 함께 죽어 눌러도 아무 일도 하지 않는다
# (브라우저 실측). 알림 칸이 세운 변경 칩 · Alarm 은 그 칸이 걷혀도 듣개가 살아 판이 열리므로 둔다 —
# 변경 칩은 새로고침하면 비는 이 세션의 변경 목록을 볼 마지막 자리다. 알림 칸의 공정 칩 · 합성 샘플
# 표지 · 「정본 아님」 표지 · 공지 칩은 감춘다 — 멈춤 화면에는 걸 공정도 볼 샘플도 읽을 데이터도
# 없고 공지는 앱 안의 사람에게 보낸 글이다.
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


def login_url(cfg: SsoConfig) -> str:
    """다시 로그인 주소 — 로그인 경로 + 돌아올 자리(`return_path`). 바탕은 `CAPA_PUBLIC_URL`."""
    return public_link(cfg, f"{names.LOGIN_PATH}?{urlencode({'next': return_path(cfg)})}")


def account_changed_notice(display_name: str) -> str:
    """계정 바뀜 경고 — 새 계정(지금 쿠키 — 이 브라우저의 값)의 표시 이름을 막아 싣는다."""
    return f"「{literal_markdown(display_name)}」{ACCOUNT_CHANGED_TAIL}"


def _render_stop_chrome() -> None:
    """멈춤 화면의 머리 — 정상 회차와 같은 껍데기 스타일(⋮ 메뉴 · Deploy 감춤 · 인쇄 규칙)과 앞
    회차가 남긴 죽은 툴바 단추 · 사이드바 앱 이름 라벨 감춤. 멈춤은 `app.py` 가 껍데기 스타일을
    보내기 전이라 여기서 보낸다(스타일만 든 `st.html` 이라 자리를 먹지 않는다)."""
    render_shell_style()
    st.html(_STOP_TOOLBAR_STYLE)


def no_gate_diagnostic_lines(cfg: SsoConfig) -> list[str]:
    """문지기 없이 뜬 앱의 관리자용 진단 줄(마크다운) — 까닭 · 실행 명령, 설정 문제(이름 — 까닭),
    안내 문서. 값은 싣지 않는다."""
    lines = [NO_GATE_DIAGNOSTIC]
    if cfg.problems:
        problems = [f"`{problem.env}` — {problem.reason}" for problem in cfg.problems]
        lines.append(f"{NO_GATE_PROBLEMS_CAPTION}  \n" + "  \n".join(problems))
    lines.append(f"안내 문서 `{names.SETUP_DOC}`")
    return lines


def _stop_without_gate(cfg: SsoConfig) -> NoReturn:
    """문지기 없이 뜬 앱 — 앱 안 멈춤 판(경고 한 줄 · 문의 줄 · 참고 줄 · 접힌 진단). 다시 열어도
    같아 주 단추가 없다 — 운영자가 진입 파일로 다시 띄워야 풀린다.

    접힌 진단(실행 명령 · 설정 문제 이름 · 안내 문서)은 관리자 몫에만 선다
    (`stop_panel.admin_fold_visible`) — 앱 안 판의 「관리자용 진단」 은 앱 시작 실패 판 · 코어 화면
    오류 카드와 한 판정이다. 다른 사람에게는 참고 줄의 사유 낱말(`NO_GATE_REFERENCE`)만이다.
    """
    _render_stop_chrome()
    st.error(NO_GATE_NOTICE, icon=":material/gpp_bad:")
    fold = AdminFold(
        NO_GATE_DIAGNOSTIC_TITLE,
        NO_GATE_DIAGNOSTIC_KEY,
        NO_GATE_COPY_KEY,
        notes=tuple(no_gate_diagnostic_lines(cfg)),
    )
    render_stop_footer(NO_GATE_REFERENCE, access_contact=cfg.access.contact, fold=fold)
    st.stop()


def signed_out_notice(cfg: SsoConfig, problem: IdentityProblem) -> str:
    """멈춤 화면 글. 명단 밖(`DENIED`)이어도 S3 명단을 아직 못 읽은 동안이면 「확인하지 못했습니다」
    다 — 재시작 뒤 S3 를 못 읽은 서버에서는 명단에 든 사람의 열린 탭도 여기서 멈춘다(거절 화면과
    같은 글 — `auth/web.LIST_UNREAD_TEXT`)."""
    if problem is IdentityProblem.DENIED and access_store.is_unread(cfg):
        return LIST_UNREAD_TEXT
    return _PROBLEM_NOTICES[problem]


def signed_out_reference(cfg: SsoConfig, problem: IdentityProblem) -> str:
    """로그인 끝남 멈춤의 참고 줄 사유 낱말 — 명단 밖이어도 S3 명단을 아직 못 읽은 동안이면 거절
    화면과 같은 `list_unread` 다(`signed_out_notice` 와 같은 가름)."""
    if problem is IdentityProblem.DENIED and access_store.is_unread(cfg):
        return LIST_UNREAD
    return _PROBLEM_REFERENCES[problem]


def _stop_signed_out(cfg: SsoConfig, problem: IdentityProblem) -> NoReturn:
    """로그인 끝남 멈춤 — 앱 안 멈춤 판(`stop_panel`): 경고 한 줄 · 주 단추 · 문의 줄 · 참고 줄.

    단추는 까닭으로 가른다(「다시 로그인」 띠와 같은 낱말 — `gate.ended_reason`): 명단에서 빠짐은
    「접속 권한 신청」, 명단 못 읽음은 끊긴 구름 아이콘 + 「다시 로그인」, 그 밖은 「다시 로그인」.
    셋 다 같은 로그인 경로다. 사이드바 카드가 서지 않아 문의처(문의 메일 · 접속 요청 창구 글)는 단추
    아래 줄로 싣는다. 접힌 진단은 없다 — 이 회차에는 검증된 신원이 없어 관리자 몫이 서지 않는다.
    """
    _render_stop_chrome()
    reason = ended_reason(problem, cfg)
    icon = ":material/cloud_off:" if reason == names.REASON_UNREAD else ":material/lock_clock:"
    st.warning(signed_out_notice(cfg, problem), icon=icon)
    # 명단에서 빠진 사람의 단추는 거절 화면의 신청 단추 이름 그대로다(`web.REGISTER_LABEL` — 설계
    # 규칙 UI-CON-02). 같은 로그인 경로라 통합인증을 거쳐 콜백의 거절 화면으로 간다.
    label = REGISTER_LABEL if reason == names.REASON_DENIED else LOGIN_AGAIN_LABEL
    st.markdown(primary_link(login_url(cfg), label), unsafe_allow_html=True)
    render_stop_footer(signed_out_reference(cfg, problem), access_contact=cfg.access.contact)
    st.stop()


def _stop_account_changed(cfg: SsoConfig, identity: Identity) -> NoReturn:
    """계정 바뀜 멈춤 — 새 계정 이름 + 주 단추 「새로고침」(같은 탭 새 문서 — 새 세션이 새 계정으로
    선다. `st.rerun` 은 같은 세션이라 앞 계정의 세션 상태가 남는다) + 되돌릴 수 없는 결과 풍선 ·
    문의 줄 · 참고 줄(앱 안 멈춤 판 `stop_panel`)."""
    _render_stop_chrome()
    st.warning(account_changed_notice(identity.display_name), icon=":material/switch_account:")
    refresh = public_link(cfg, return_path(cfg))
    st.markdown(primary_link(refresh, REFRESH_LABEL, title=REFRESH_TIP), unsafe_allow_html=True)
    render_stop_footer(ACCOUNT_CHANGED_REFERENCE, access_contact=cfg.access.contact)
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
        _stop_account_changed(cfg, found)
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


# 「이 등급으로 보기」 — 개발자 자기 창(세션)만 · 화면만. 값은 열람 · 실무자 · 관리자 가운데 하나다.
GRADE_PREVIEW_KEY: Final = "grade_preview"
PREVIEW_GRADES: Final = (grades.VIEWER, grades.EDITOR, grades.MANAGER)
_UNRESTRICTED: Final = grades.Caller(grades.DEVELOPER, unrestricted=True)


def script_context_present() -> bool:
    """지금 스레드에 Streamlit 실행 문맥이 있는가(본문 · 콜백 · 프래그먼트). 시험이 바꿔 끼운다."""
    return get_script_run_ctx(suppress_warning=True) is not None


def _judged(*, thread_check: bool) -> grades.Caller:
    """실제 등급 판정 한 벌. `thread_check` 면 실행 문맥 없는 낯선 스레드를 열람으로 본다(쓰는
    순간의 벽 — 화면 판정은 늘 실행 문맥 안이라 보지 않는다)."""
    cfg = runtime.config()
    if not cfg.operational:
        return _UNRESTRICTED
    if audit_recorder.system_actor() is not None:
        return _UNRESTRICTED
    if cfg.mode is not SsoMode.ON:
        return grades.Caller(grades.MANAGER)
    if thread_check and not script_context_present():
        return grades.Caller(grades.VIEWER)
    found = identity_from_cookies(session_cookies(), cfg, _now(), renewals=True)
    if isinstance(found, IdentityProblem):
        return grades.Caller(grades.VIEWER, ended=found.value)
    return grades.Caller(grade_store.grade_of(cfg, found.loginid))


def real_caller() -> grades.Caller:
    """쓰는 순간의 실제 등급(모듈 설명 「접속 등급」) — 미리 보기를 따르지 않고 세션 칸을 읽지
    않는다. 쓰는 순간의 벽이 꽂아 쓰는 판정기다(`grade_ui.install`)."""
    return _judged(thread_check=True)


def viewer_is_developer() -> bool:
    """이 연결의 쿠키를 지금 다시 검증한 신원이 개발자인가(환경변수 개발자 ∪ 명단 `admin`).
    통합인증이 켜짐이 아니면 늘 거짓이다 — 「이 등급으로 보기」 를 따르지 않는 실제 판정이다.

    Admin 의 두 번째 벽(BigDataQuery · 동기화 · 공지)과 미리 보기의 자격이 이것을 부른다.
    """
    identity = verified_identity()
    return identity is not None and access_store.is_admin(runtime.config(), identity.loginid)


def preview_grade() -> str | None:
    """「이 등급으로 보기」 중이면 그 등급 — 운영 + 켜짐의 실제 개발자 회차에만 있다."""
    cfg = runtime.config()
    if not (cfg.operational and cfg.mode is SsoMode.ON):
        return None
    value = st.session_state.get(GRADE_PREVIEW_KEY)
    if value not in PREVIEW_GRADES or not viewer_is_developer():
        return None
    return str(value)


def end_preview() -> None:
    """「이 등급으로 보기」 를 끝낸다(앱 정보 카드 「끝내기」 콜백)."""
    st.session_state.pop(GRADE_PREVIEW_KEY, None)


def screen_grade() -> str:
    """화면 등급 — 제한 없음은 개발자, 로그인 끝남은 열람, 실제 개발자는 미리 보기를 따른다."""
    who = _judged(thread_check=False)
    if who.unrestricted:
        return grades.DEVELOPER
    if who.ended is not None:
        return grades.VIEWER
    if who.grade == grades.DEVELOPER:
        preview = preview_grade()
        if preview is not None:
            return preview
    return who.grade


def viewer_can(action: str) -> bool:
    """이 화면에 그 동작을 세우나(화면 판정 — 미리 보기를 따른다). 숨김 · 값만 · 탭 목록 · 사람 몫
    자동 쓰기가 부른다. 쓰는 순간의 벽은 따로 실제 등급으로 다시 본다."""
    need = grades.need_of(action)
    return grades.at_least(screen_grade(), need)


ADMIN_ONLY_NOTICE = grades.stop_text("admin.area", place="page")
HOME_LINK_LABEL = "HOME 으로"


def admin_area_locked() -> bool:
    """Admin Area 를 이 회차에 닫는가 — 화면 등급으로 개발자 몫(`admin.area`)을 할 수 없다.

    판정은 이것 하나다 — 사이드바 링크를 빼는 `app.py` 와 주소로 연 회차를 멈추는 Admin Area 가 같이
    부른다(2026-11-13 보드 D11 · 2026-11-18 접속 등급). 개발 `app.py` · 사내 WebIDE · 사내 PC(운영
    아님)는 지금처럼 연다. 통합인증이 꺼진 운영 서버는 관리자까지라 잠긴 채다. 「이 등급으로 보기」
    동안은 잠긴다(끄는 자리는 앱 정보 카드의 「끝내기」).
    """
    return not viewer_can("admin.area")


def developer_wall_locked() -> bool:
    """쓰는 순간의 두 번째 벽 — 운영 서버이고 실제 개발자가 아니다(미리 보기를 따르지 않는다).

    Admin 의 쓰기 콜백(공지 · 공용 표시순서 · 공정 표시명 붙여넣기)이 누른 순간 다시 본다.
    """
    return runtime.config().operational and not viewer_is_developer()


def viewer_can_audit() -> bool:
    """접속 · 작업 기록을 볼 수 있는가 — 감사 기록을 남기는 서버(`audit.recorder.enabled()` —
    통합인증 켜짐 기동)이고 보는 사람이 실제 개발자(`viewer_is_developer`)이며 미리 보기 중이
    아니다."""
    return audit_recorder.enabled() and viewer_is_developer() and preview_grade() is None


def logout_url(cfg: SsoConfig) -> str:
    """로그아웃 주소 — 지금 화면(`return_path`)이 `/` 가 아니면 `?next=` 로 싣는다. 로그아웃 화면의
    「다시 들어가기」 가 로그아웃 전에 보던 화면으로 간다(카드 p1-logout — 그쪽이 다시 정화한다)."""
    back = return_path(cfg)
    query = "" if back == "/" else f"?{urlencode({'next': back})}"
    return public_link(cfg, f"{names.LOGOUT_PATH}{query}")


# 앱 정보 카드 셋째 줄의 등급 표지 — 열람 · 실무자만(등급 때문에 단추가 없는 사람에게만 까닭을
# 보인다
# — 설계 규칙 UI-TXT-05 예외). 미리 보기 동안은 보는 등급을 싣는다.
CARD_GRADES: Final = (grades.VIEWER, grades.EDITOR)
PREVIEW_MARK = "{grade} 화면으로 보는 중"
PREVIEW_END_LABEL = "끝내기"
PREVIEW_END_KEY = "grade_preview_end"


def card_grade_mark(identity: Identity) -> str | None:
    """카드 셋째 줄의 등급 표지 글 — 미리 보기 중이면 「실무자 화면으로 보는 중」, 열람 · 실무자면
    등급 이름, 관리자 · 개발자 · 운영 아님은 없음."""
    preview = preview_grade()
    if preview is not None:
        return PREVIEW_MARK.format(grade=grades.label_of(preview))
    cfg = runtime.config()
    if not (cfg.operational and cfg.mode is SsoMode.ON):
        return None
    grade = grade_store.grade_of(cfg, identity.loginid)
    return grades.label_of(grade) if grade in CARD_GRADES else None


def sso_credit_line(identity: Identity | None, *, now: int | None = None) -> str | None:
    """앱 정보 카드 셋째 줄 — 「이름 · 부서 · (등급) · 로그아웃」. 꺼짐(신원 없음)이면 `None`.

    이름이 없으면 loginid 를 싣고, 부서가 없으면 뺀다. 등급은 열람 · 실무자만 싣고(미리 보기 동안은
    「<등급> 화면으로 보는 중」 — 그 곁 「끝내기」 단추는 카드가 그린다), 관리자 · 개발자는 싣지
    않는다. 실제로 끝나는 시각(갱신 표까지 견준 `session_end_of`) 30분 전부터 끝에 남은 시간을
    붙인다 —
    최대 시간이 정한 끝이면 `CAP_WARNING_SUFFIX`, 마지막 사용 뒤 유지 시간이 정한 끝이면
    `IDLE_WARNING_SUFFIX`. 이름 · 부서는 IdP 가 준 사람 글이라 `literal_markdown` 으로 막는다. 이
    줄은
    원문 HTML 을 허락한 캡션으로 그린다(로그아웃 링크를 같은 탭에서 열려고).
    """
    if identity is None:
        return None
    cfg = runtime.config()
    parts = [literal_markdown(identity.display_name)]
    if identity.dept:
        parts.append(literal_markdown(identity.dept))
    mark = card_grade_mark(identity)
    if mark is not None:
        parts.append(mark)
    parts.append(_same_tab_link(logout_url(cfg), LOGOUT_LABEL))
    line = " · ".join(parts)
    moment = _now() if now is None else now
    end, capped = session_end_of(identity, cfg, moment)
    left = end - moment
    if left <= EXPIRY_WARNING_SECONDS:
        minutes = max(1, math.ceil(left / 60))
        suffix = CAP_WARNING_SUFFIX if capped else IDLE_WARNING_SUFFIX
        line += suffix.format(minutes=minutes)
    return line
