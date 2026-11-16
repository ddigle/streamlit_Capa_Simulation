# Purpose: Admin 서버 시작 점검의 지금 토큰 줄 · 토큰 넣기 팝업 · 토큰 만료 관리자 알림을 둔다.

"""BigDataQuery 토큰 넣기(2026-11-12 사용자 결정 — 「Admin 「토큰 넣기」 + 만료 1시간 전 관리자
알림 먼저, REST 자동 갱신은 조사만」).

**자리.** C-DEP 서버(시작 점검 결과 파일이 있는 서버)의 Admin 「서버 시작 점검」 펼침 안, 표 아래
사실 줄 뒤 한 줄이다 — 「지금 토큰」 값 줄(누구에게나)과 그 앞 「토큰 넣기」 단추(관리자 회차에만
— 권한 기능은 접속 명단처럼 숨긴다). 패키지가 토큰 파일보다 먼저 읽는 환경변수가 있거나 계정이
없어 넣을 수 없으면 단추를 잠그고 까닭을 풍선에 단다(설계 규칙 UI-INP-07). WebIDE · 사내 PC ·
개발은 통합인증이 꺼져 관리자가 없으니 단추가 서지 않는다.

**팝업.** 비밀 칸 하나와 「넣기」 뿐이다(설명 글 없음 — UI-TXT-01). 칸은 폼 안이라 「넣기」 를
누를 때만 서버로 가고, 받은 회차에 세션 칸에서 곧바로 지운다(폼은 제출 뒤 칸을 비운다). 쓰기는
누른 회차의 신원을 다시 검증해 관리자일 때만 한다 — 그려진 단추를 믿지 않는다. 거절(빈 값 · 짧음 ·
base64 · 쓰기 실패)은 칸 아래 한 줄이고(폼 검증 — UI-NTF-03) 토큰 글 · 길이를 싣지 않는다. 넣으면
알림창에 결과를 내고 팝업을 닫는다(`DialogHost.finish` — 앱 전체 회차라 지금 토큰 줄이 바로
바뀐다).

**만료 알림(`AD-11`).** `container_start_check.render_token_alert` 가 결과 파일이 있는 서버에서
회차마다 부른다(`AD-10` 곁). 토큰에서 만료 시각을 읽었고 지금이 그 1시간 앞 이후면(지난 것 포함)
관리자 회차에 조치 알림이 선다. 지문은 만료 시각 하나라 토큰마다 알림창이 한 번이다. 만료를 읽지
못하면(지금 아는 꼴은 JWT `exp` 하나 — `io/bdq_token.py`) 서지 않고 조회 실패 알림 `AD-10` 이
뒷벽이다. 회차가 돌 때만 선다 — 배경 스레드를 더하지 않는다(AGENTS 9장).

**물러서기.** 이 알림은 `app.py` 가 모든 화면 회차에 부르는 자리라, 지금 토큰을 읽다 무엇이 나도
(`read_current`) 값 줄은 「확인하지 못함」, 알림은 해소로 물러서고 시각을 못 옮기면 「알 수 없음」
이다 — 덧붙은 보기가 화면을 멈추지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

import streamlit as st

from capa_simulation import alerts
from capa_simulation.audit import recorder as audit_recorder
from capa_simulation.components import sso_identity
from capa_simulation.components.admin_dialog import ADMIN_DIALOG_KEY
from capa_simulation.components.dialog_host import DialogHost
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.sso_status import CLOCK_FORMAT
from capa_simulation.io import bdq_token
from capa_simulation.io.container_start_report import BDQ_LOGIN_LABEL, BDQ_TOKEN_ENV
from capa_simulation.korea_time import kst_clock
from capa_simulation.navigation import ADMIN_AREA
from capa_simulation.page_tabs_state import tab_label
from capa_simulation.sidebar_status import keeps_app_run_open

TOKEN_DIALOG: Final = "bdq_token"
# 팝업 호스트 — 열림 칸은 Admin Area 한 칸(`admin_dialog`)을 접속 명단 「추가」 와 함께
# 쓴다(값이 가른다).
HOST: Final = DialogHost("admin_area_bdq_token_dialog_host", ADMIN_DIALOG_KEY)
OPEN_KEY: Final = "admin_area_bdq_token_open"
FORM_KEY: Final = "admin_area_bdq_token_form"
INPUT_KEY: Final = "admin_area_bdq_token_input"
FLASH_KEY: Final = "admin_area_bdq_token_flash"
EXPIRY_ALERT_CODE: Final = "AD-11"

OPEN_LABEL: Final = "토큰 넣기"
DIALOG_TITLE: Final = "BigDataQuery 토큰 넣기"
# 칸 라벨은 접는다(접근성 이름으로 남는다) — 창 제목과 거듭되는 말이다.
INPUT_LABEL: Final = "로그인 토큰"
APPLY_LABEL: Final = "넣기"
# 누르기 전에 알아야 할 것 — 덮어쓰기와 다시 띄우면 돌아감(설계 규칙 UI-NTF-09).
OPEN_HELP: Final = (
    "패키지가 다음 조회부터 읽는 토큰 파일을 이 값으로 바꿉니다. 컨테이너를 다시 띄우면 "
    f"CD 환경변수 {BDQ_TOKEN_ENV} 값으로 돌아갑니다."
)
NOT_ADMIN_MESSAGE: Final = "관리자만 토큰을 넣을 수 있습니다"
TOKEN_LINE_LABEL: Final = "**지금 토큰**"
# 알림창 짧은 글의 만료 시각 꼴(KST) — 전문은 펼침과 같은 `CLOCK_FORMAT`.
SHORT_CLOCK_FORMAT: Final = "%m-%d %H:%M"
UNKNOWN_CLOCK: Final = "알 수 없음"
# 알림 전문의 할 일 — 패키지가 읽는 자리마다(`AD-10` 조회 실패 · `AD-11` 이 함께 쓴다). 평문이다
# (알림창 · Alarm 은 `textContent` 로 넣는다).
ENVIRONMENT_FIX: Final = (
    f"패키지가 환경변수 {bdq_token.LOGIN_TOKEN_ENV} 의 토큰을 씁니다 — 그 값을 새 토큰으로 "
    "바꾸고 CI/CD 를 다시 누르세요."
)
INSTALL_FIX: Final = (
    "Admin 「서버 시작 점검」 의 「토큰 넣기」 로 새 토큰을 넣으면 다음 조회부터 쓰입니다 — "
    f"컨테이너를 다시 띄우면 CD 환경변수 {BDQ_TOKEN_ENV} 값으로 돌아가니 그 값도 새 토큰으로 "
    "바꿔 두세요."
)
# 자동 로그인이 켜졌는데(`managed` + 키) 저장된 계정이 없는 서버의 할 일(`AD-10`) — 계정을 넣으면
# 그 자리에서 로그인해 새 토큰을 받고, 뒤로 토큰이 죽으면 앱이 스스로 다시 로그인한다.
AUTO_LOGIN_FIX: Final = (
    f"Admin Area 「{BDQ_LOGIN_LABEL}」 에 BigDataQuery 계정을 넣으면 앱이 로그인해 새 토큰을 받고, "
    "뒤로 토큰이 죽으면 스스로 다시 로그인합니다. 이 알림은 그 뒤 조회가 한 번 성공하면 풀립니다."
)


def _utc_text(moment: datetime | None) -> str:
    """감사 줄의 만료 시각 — UTC(서버 시각대에 기대지 않는다). 없거나 넘치면 빈 글."""
    if moment is None:
        return ""
    try:
        return audit_recorder.ts_text(moment)
    except (OverflowError, OSError, ValueError):
        return ""


def _clock(moment: datetime, layout: str = CLOCK_FORMAT) -> str:
    """KST 시각 글(`korea_time`). KST 로 옮기지 못하면(넘침 · 시각대 없음) 「알 수 없음」."""
    try:
        return kst_clock(moment, layout)
    except (OverflowError, OSError, ValueError):
        return UNKNOWN_CLOCK


def read_current() -> bdq_token.TokenState:
    """지금 토큰 — 읽다 무엇이 나도 「확인하지 못함」(`unknown`)으로 물러선다(모듈 설명
    「물러서기」). 스크립트 멈춤 · 다시 돌기는 `Exception` 이 아니라 지나간다."""
    try:
        return bdq_token.current_token()
    except Exception:
        return bdq_token.TokenState("unknown")


def _expiry_text(state: bdq_token.TokenState) -> str:
    if state.expires_at is None:
        return "만료 모름"
    gone = " · 지남" if state.expires_at <= datetime.now(timezone.utc) else ""
    return f"만료 {_clock(state.expires_at)}{gone}"


def token_line(state: bdq_token.TokenState | None = None) -> str:
    """「지금 토큰」 값 줄 — 패키지가 다음 조회에 읽을 토큰의 자리 · 바뀐 때 · 만료. 토큰 글은
    없다."""
    current = read_current() if state is None else state
    if current.source == "environment":
        body = f"환경변수 `{bdq_token.LOGIN_TOKEN_ENV}` · {_expiry_text(current)}"
    elif current.source == "file":
        modified = _clock(current.modified_at) if current.modified_at else UNKNOWN_CLOCK
        body = f"파일 · 수정 {modified} · {_expiry_text(current)}"
    elif current.source == "missing":
        body = "파일 없음"
    else:
        body = "확인하지 못함(계정을 모르거나 자리에 들어갈 수 없음)"
    return f"{TOKEN_LINE_LABEL} · {body}"


def render_token_row(line: str) -> bool:
    """펼침 안 한 줄 — 관리자면 「토큰 넣기」 단추 + 값 줄, 아니면 값 줄만. 단추를 그렸으면 참 —
    그 회차는 펼침 뒤에서 팝업 호스트(`render_token_dialog`)를 부른다."""
    if not sso_identity.viewer_is_admin():
        st.caption(line)
        return False
    blocked = bdq_token.blocked_reason()
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.button(
            OPEN_LABEL,
            icon=":material/key:",
            key=OPEN_KEY,
            disabled=blocked is not None,
            help=blocked if blocked is not None else OPEN_HELP,
            on_click=HOST.open,
            args=(TOKEN_DIALOG, OPEN_KEY),
        )
        st.caption(line, width="content")
    render_flash(FLASH_KEY)
    return True


def render_token_dialog() -> None:
    """팝업 호스트 — 「토큰 넣기」 단추가 서는 회차(관리자)마다 단추를 그린 뒤 부른다."""
    HOST.render({TOKEN_DIALOG: _token_dialog}, widget_keys={TOKEN_DIALOG: (INPUT_KEY,)})


def install_from_dialog(raw: str) -> str | None:
    """누른 회차의 넣기 — 거절 글(칸 아래 한 줄) 또는 `None`(넣음 · 같음 — 알림창에 담았다). 신원을
    이 회차의 쿠키에서 다시 검증한다."""
    if not sso_identity.viewer_is_admin():
        audit_recorder.record("admin_token_set", out="denied", det={"result": "not_admin"})
        return NOT_ADMIN_MESSAGE
    outcome = bdq_token.install_token(raw)
    if outcome.status == "refused":
        audit_recorder.record("admin_token_set", out="fail", det={"result": "refused"})
        return f"넣지 않았습니다 — {outcome.reason}"
    if outcome.status == "same":
        audit_recorder.record("admin_token_set", det={"result": "same"})
        queue_flash(FLASH_KEY, "같은 토큰이 이미 들어 있습니다 — 바뀐 것이 없습니다", kind="info")
        return None
    # 알림창 짧은 글 안에 들게 만료는 짧은 시각 꼴이다(다음 조회부터 쓰인다는 말은 단추 풍선 ·
    # Guide). 파일은 이미 썼다 — 만료 읽기가 무엇을 내도 넣음으로 끝낸다(`read_current`).
    expires = read_current().expires_at
    # 감사 줄에는 결과와 만료일만 — 토큰 값 · 지문은 싣지 않는다.
    audit_recorder.record(
        "admin_token_set",
        det={"result": "installed", "expires": _utc_text(expires)},
    )
    when = "모름" if expires is None else _clock(expires, SHORT_CLOCK_FORMAT)
    queue_flash(FLASH_KEY, f"BigDataQuery 토큰을 넣었습니다 · 만료 {when}")
    return None


@st.dialog(DIALOG_TITLE, on_dismiss=HOST.close)
@keeps_app_run_open
def _token_dialog() -> None:
    with st.form(FORM_KEY, clear_on_submit=True, border=False):
        st.text_input(
            INPUT_LABEL,
            key=INPUT_KEY,
            type="password",
            autocomplete="new-password",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(APPLY_LABEL, icon=":material/key:")
    if not submitted:
        return
    # 받은 회차에 세션 칸에서 곧바로 뗀다 — 거절로 팝업이 남아도 토큰이 세션에 머물지 않는다.
    refusal = install_from_dialog(str(st.session_state.pop(INPUT_KEY, "") or ""))
    if refusal is not None:
        st.error(refusal, icon=":material/block:")
        return
    HOST.finish()


def render_expiry_alert(*, standing: bool = False) -> None:
    """토큰 만료 1시간 전 관리자 알림(`AD-11`). 결과 파일이 있는 서버에서 회차마다 조건 없이 부른다
    (이벤트 칸 한 자리 — 토큰을 읽지 못해도 해소로 그 자리를 쓴다). 지문은 만료 시각 하나다 —
    회차마다 바뀌는 지금 시각을 싣지 않는다. 자동 로그인이 서 있는 동안(`standing` —
    `bdq_login.current_view`)은 해소로 부른다 — 토큰이 죽으면 앱이 다시 로그인한다."""
    state = read_current()
    expires = state.expires_at
    active = (
        not standing
        and expires is not None
        and bdq_token.expiry_is_near(state)
        and sso_identity.viewer_is_admin()
    )
    alerts.state(
        EXPIRY_ALERT_CODE,
        scope=None,
        content=expires.isoformat() if active and expires is not None else None,
        active=active,
        text=(
            f"BigDataQuery 로그인 토큰 만료 {_clock(expires, SHORT_CLOCK_FORMAT)} — "
            "새 토큰을 넣으세요"
            if active and expires is not None
            else None
        ),
        full=_expiry_alert_text(state) if active else None,
        goto=(tab_label(ADMIN_AREA), ADMIN_AREA.href),
    )


def _expiry_alert_text(state: bdq_token.TokenState) -> str:
    """전문(평문) — 언제 만료이고 무엇을 하면 풀리나."""
    expires = state.expires_at
    when = _clock(expires) if expires is not None else UNKNOWN_CLOCK
    head = f"BigDataQuery 로그인 토큰의 만료 시각은 {when} 입니다(1시간 전부터 알립니다). "
    return head + (ENVIRONMENT_FIX if state.source == "environment" else INSTALL_FIX)
