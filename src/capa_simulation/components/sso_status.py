# Purpose: Admin Area 의 「통합인증 점검」 펼침과 「서버 시작 점검」 표의 통합인증 줄을 짓는다.

"""통합인증 점검.

C-DEP 서버에는 셸도 로그도 없어 통합인증의 설정 판정 · 서명 인증서 · 최근 사건을 Admin Area 에서
읽는다. **값은 싣지 않는다** — 환경변수는 이름과 있음/없음 · 까닭만, 비밀값(`JWT_SECRET_KEY`)은
「있음 · 검사 통과」 같은 사실만, client id 는 「있음」 만, 계정은 앞 두 글자만(`mask_account`)이다.
redirect_uri · issuer 는 비밀이 아니고 포털 등록값과 한 글자씩 대 봐야 하므로 글자 그대로 싣는다.

- 꺼짐이고 운영(`APP_ENV=prod`)이 아니면 아무것도 그리지 않는다 — 개발 PC · 사내 WebIDE 화면 그대로.
- 꺼짐(운영)이면 「주소를 아는 사람은 누구나 들어옵니다」 경고와 「켜면 막힐 문제」(`readiness`) —
  첫 배포에서 client id 를 넣기 전에 나머지 값이 맞는지 미리 본다(`docs/sso_setup.md`).
- 막힘이면 문지기가 앱을 열지 않으므로 이 펼침에 닿지 않는다(설정 화면이 진단 창구다). 닿았다면
  문지기 없이 뜬 것이고 `app.py` 가 먼저 멈춘다 — 그래도 판정은 그대로 그린다.

설정은 프로세스가 기동 때 한 번 읽은 것(`auth.runtime.config`)이고, 최근 사건은 프로세스 메모리의
고리(재시작하면 비워진다)다. DB 를 열지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig, SsoMode, SsoProblem
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.io.container_start_report import (
    STATUS_FAILED,
    STATUS_LABELS,
    STATUS_OK,
    STATUS_SKIPPED,
    mask_account,
)
from capa_simulation.sidebar_status import remembered_expander

# 펼침 key. 「서버 시작 점검」 바로 뒤 · 탭 묶음 위에 서므로 자리를 key 로 고정한다.
EXPANDER_KEY = "admin_area_sso_status"
START_STEP_LABEL = "통합인증"
RECENT_EVENT_LIMIT = 20
CERT_WARNING_DAYS = 30

VERDICT_ON = "켜짐"
VERDICT_OFF = "꺼짐"
VERDICT_OFF_PROD = "꺼짐(운영)"
VERDICT_BROKEN = "막힘"

OFF_IN_PRODUCTION_WARNING = (
    "운영 서버인데 통합인증이 꺼져 있습니다 — 주소를 아는 사람은 누구나 들어옵니다. "
    f"포털 승인 메일의 Client ID 를 환경변수(`{names.ENV_CLIENT_ID}`)에 넣으면 켜집니다."
)


def sso_verdict(cfg: SsoConfig) -> str:
    if cfg.mode is SsoMode.ON:
        return VERDICT_ON
    if cfg.mode is SsoMode.BROKEN:
        return VERDICT_BROKEN
    return VERDICT_OFF_PROD if cfg.prod else VERDICT_OFF


def sso_start_step(cfg: SsoConfig | None = None) -> tuple[str, str, str]:
    """「서버 시작 점검」 표의 넷째 줄 `(단계, 결과, 까닭)` — 결과 파일이 아니라 지금 설정에서."""
    current = runtime.config() if cfg is None else cfg
    if current.mode is SsoMode.ON:
        return START_STEP_LABEL, STATUS_LABELS[STATUS_OK], ""
    if current.mode is SsoMode.OFF:
        return START_STEP_LABEL, STATUS_LABELS[STATUS_SKIPPED], f"{names.ENV_CLIENT_ID} 없음"
    problem_names = " · ".join(dict.fromkeys(problem.env for problem in current.problems))
    return START_STEP_LABEL, STATUS_LABELS[STATUS_FAILED], problem_names


def started_environment_caption(presence: dict[str, bool] | None) -> str | None:
    """결과 파일에 남은 「시작 때 있던 통합인증 환경변수」 한 줄. 그 칸이 없는 옛 파일은 `None`."""
    if presence is None:
        return None
    present = [name for name in names.SSO_ENVIRONMENT if presence.get(name)]
    listed = " · ".join(f"`{name}`" for name in present) if present else "없음"
    return f"시작 때 있던 통합인증 환경변수: {listed}"


def _problem_text(problems: list[SsoProblem]) -> str:
    return " · ".join(problem.reason for problem in problems)


def environment_table(cfg: SsoConfig) -> pd.DataFrame:
    """환경변수 이름 | 상태 | 까닭. 값은 싣지 않는다.

    켜짐 · 막힘은 `problems`, 꺼짐은 「켜면 막힐 문제」(`readiness`)를 까닭으로 싣는다. 알림
    (`notices` — 인증서 만료 가까움 등)은 막지 않으므로 상태를 바꾸지 않고 까닭에만 붙인다.
    """
    issues: dict[str, list[SsoProblem]] = {}
    for problem in cfg.problems if cfg.mode is not SsoMode.OFF else cfg.readiness:
        issues.setdefault(problem.env, []).append(problem)
    notices: dict[str, list[SsoProblem]] = {}
    for notice in cfg.notices:
        notices.setdefault(notice.env, []).append(notice)
    rows: list[tuple[str, str, str]] = []
    for name in names.SSO_ENVIRONMENT:
        present = cfg.env_presence.get(name, False)
        found = issues.pop(name, [])
        if found:
            status = "틀림" if present else "없음"
            reason = _problem_text(found)
        elif name == names.ENV_SECRET and present:
            status, reason = "있음", "길이 · 글자 수 검사 통과"
        else:
            status, reason = ("있음" if present else "없음"), ""
        extra = _problem_text(notices.pop(name, []))
        rows.append((name, status, " · ".join(part for part in (reason, extra) if part)))
    for env, found in issues.items():
        rows.append((env, "틀림", _problem_text(found)))
    return pd.DataFrame(rows, columns=["환경변수", "상태", "까닭"])


def _days_left(now: datetime, not_after: datetime) -> int:
    return (not_after - now).days


def fact_lines(cfg: SsoConfig, *, now: datetime | None = None) -> list[str]:
    """표 아래 한 줄씩 — redirect_uri · issuer · 인증서 지문 · 세션 시간 · 쿠키 이름 · 문지기."""
    moment = now or datetime.now(timezone.utc)
    redirect = literal_markdown(cfg.redirect_uri) if cfg.redirect_uri else "계산하지 못함"
    issuer = literal_markdown(cfg.issuer) if cfg.issuer else "없음"
    lines = [
        f"redirect\\_uri(포털 Endpoint URL 과 한 글자도 같아야 함): {redirect}",
        f"`{names.ENV_ISSUER}`: {issuer}",
        f"`{names.ENV_CLIENT_ID}`: {'있음' if cfg.client_id else '없음'}",
    ]
    for cert in cfg.signing_certs:
        days = _days_left(moment, cert.not_after)
        lines.append(
            f"서명 인증서 x5t {literal_markdown(cert.x5t)} · SHA-256 {cert.sha256[:16]}… · "
            f"만료 {cert.not_after.strftime('%Y-%m-%d')}(남은 날 {days}) · RSA {cert.key_bits}비트"
        )
    lines += [
        f"세션 시간: {cfg.session_hours}시간 · "
        f"세션 쿠키 이름: {literal_markdown(cfg.session_cookie)}",
        f"문지기: {'있음' if runtime.gate_installed() else '없음(app.py 로 뜸)'} · "
        f"잠금(`{names.ENV_SSO}=required`): {'예' if cfg.locked else '아니오'}",
    ]
    return lines


def readiness_line(cfg: SsoConfig) -> str:
    """꺼짐 때 「켜면 막힐 문제」 한 줄 — client id 를 넣기 전에 나머지 값을 미리 본다."""
    if not cfg.readiness:
        return "켜면 막힐 문제: 없음"
    items = " · ".join(f"`{problem.env}` — {problem.reason}" for problem in cfg.readiness)
    return f"켜면 막힐 문제: {items}"


def _event_code(fields: dict[str, str]) -> str:
    for key in ("reason", "error", "problems", "mode"):
        value = fields.get(key, "")
        if value and value != "-":
            return value
    return "-"


def recent_event_table(limit: int = RECENT_EVENT_LIMIT) -> pd.DataFrame:
    """최근 사건(새것 먼저) — 시각 | 사건 | 사유 코드 | 계정(앞 두 글자).

    IdP 의 오류 설명(`error_description`)은 싣지 않는다.
    """
    rows = []
    for event in runtime.recent_events(limit):
        fields = dict(event.fields)
        loginid = fields.get("loginid", "-")
        rows.append(
            (
                datetime.fromtimestamp(event.at).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                event.event,
                _event_code(fields),
                mask_account(loginid) if loginid and loginid != "-" else "-",
            )
        )
    return pd.DataFrame(rows, columns=["시각", "사건", "사유 코드", "계정"])


def _expiring_certs(cfg: SsoConfig, now: datetime) -> list[str]:
    return [
        cert.x5t
        for cert in cfg.signing_certs
        if _days_left(now, cert.not_after) <= CERT_WARNING_DAYS
    ]


def render_sso_status() -> None:
    """Admin Area 「통합인증 점검」 펼침. 꺼짐이고 운영이 아니면 그리지 않는다."""
    cfg = runtime.config()
    if cfg.mode is SsoMode.OFF and not cfg.prod:
        return
    verdict = sso_verdict(cfg)
    now = datetime.now(timezone.utc)
    with remembered_expander(
        f"통합인증 점검 · {verdict}", icon=":material/verified_user:", key=EXPANDER_KEY
    ):
        if cfg.mode is SsoMode.ON:
            st.caption("통합인증이 켜져 있습니다 — 로그인한 사람만 앱에 들어옵니다.")
        elif cfg.mode is SsoMode.OFF:
            st.warning(OFF_IN_PRODUCTION_WARNING, icon=":material/lock_open:")
            st.caption(readiness_line(cfg))
        else:
            st.error(
                "통합인증 설정을 마치지 못했습니다 — 아래 까닭을 고친 뒤 CI/CD 를 다시 돌리세요.",
                icon=":material/gpp_bad:",
            )
        expiring = _expiring_certs(cfg, now)
        if expiring:
            st.warning(
                f"서명 인증서 만료가 {CERT_WARNING_DAYS}일 안입니다 — 새 인증서를 "
                f"`{names.ENV_SIGNING_CERT}` 에 쉼표로 더해 두세요(`{names.SETUP_DOC}`).",
                icon=":material/event_busy:",
            )
        st.dataframe(environment_table(cfg), hide_index=True, width="stretch")
        st.caption("  \n".join(fact_lines(cfg, now=now)))
        events = recent_event_table()
        if events.empty:
            st.caption("최근 사건 없음(프로세스 메모리 — 재시작하면 비워진다)")
        else:
            st.caption("최근 사건(새것 먼저 · 재시작하면 비워진다)")
            st.dataframe(events, hide_index=True, width="stretch")
