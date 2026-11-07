# Purpose: Admin Area 의 「통합인증 점검」 펼침과 「서버 시작 점검」 표의 통합인증 줄을 짓는다.

"""통합인증 점검.

C-DEP 서버에는 셸도 로그도 없어 통합인증의 설정 판정 · 서명 인증서 · 최근 사건을 Admin Area 에서
읽는다. **값은 싣지 않는다** — 환경변수는 이름과 있음/없음 · 까닭만, 비밀값(`JWT_SECRET_KEY`)은
「있음 · 검사 통과」 같은 사실만, client id 는 「있음」 만, 접속 명단은 개수만, 클레임은 이름만,
계정은 앞 두 글자만(`mask_account`)이다.
redirect_uri · issuer 는 비밀이 아니고 포털 등록값과 한 글자씩 대 봐야 하므로 글자 그대로 싣는다.

- 꺼짐이고 운영(`APP_ENV=prod`)이 아니면 아무것도 그리지 않는다 — 개발 PC · 사내 WebIDE 화면 그대로.
- 꺼짐(운영)이면 「주소를 아는 사람은 누구나 들어옵니다」 경고와 「켜면 막힐 문제」(`readiness`) —
  첫 배포에서 client id 를 넣기 전에 나머지 값이 맞는지 미리 본다(`docs/sso_setup.md`).
- 막힘이면 문지기가 앱을 열지 않으므로 이 펼침에 닿지 않는다(설정 화면이 진단 창구다). 닿았다면
  문지기 없이 뜬 것이고 `app.py` 가 먼저 멈춘다 — 그래도 판정은 그대로 그린다.

설정은 프로세스가 기동 때 한 번 읽은 것(`auth.runtime.config`)이고, 최근 사건은 프로세스 메모리의
고리(재시작하면 비워진다)다. 명단 밖 로그인은 그 고리를 밀어내지 못하게 계정별 표로 따로 그린다.
켜짐이면 로그인 유지 시간(마지막 사용 뒤 · 최대) 사실 줄 아래에 로그인 갱신
(`POST /auth/sso/refresh`) 결과 누계 한 줄을 싣는다 — 갱신은 사건 고리에 적지 않는다(5분마다
사람마다 한 줄이면 고리가 갱신으로만 찬다). 그 아래 마지막 로그인의 클레임 이름 한 줄은 ADFS 가 그룹
클레임을 주는지 보는 길이다(재시작하면 비워진다). DB 를 열지 않는다.

S3 명단 줄(`access_s3_line`)은 「C-DEP 에서 S3 로 닿는가」 의 답이다 — 키 · 서명 · 명단 값 ·
주소를 싣지 않아 리뷰 압축본에 그대로 옮길 수 있다. 쓰기 권한은 저장해 보기 전에는 모른다(GET ·
HEAD 가 되어도).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.auth import access_store, names, runtime
from capa_simulation.auth.access import SourceProblem
from capa_simulation.auth.config import SsoConfig, SsoMode, SsoProblem
from capa_simulation.components import sso_identity
from capa_simulation.components.diagnostic_copy import (
    diagnostic_text,
    plain_lines,
    render_diagnostic_copy,
    table_lines,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.io import s3_small
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
COPY_KEY = "sso_status"
START_STEP_LABEL = "통합인증"
RECENT_EVENT_LIMIT = 20
ANONYMOUS_EVENT_LIMIT = 10
ANONYMOUS_COUNT_LIMIT = 8
DENIED_ACCOUNT_LIMIT = 20
CERT_WARNING_DAYS = 30

# 비밀값 줄의 까닭 — 값은 싣지 않고 검사를 지났다는 사실만. 사람이 고른 문장인지는 가리지 못한다.
SECRET_CHECKS_PASSED = "길이 · 글자 가짓수 · 자리표 · 되풀이 · 차례 검사 통과(무작위 값인지는 모름)"

VERDICT_ON = "켜짐"
VERDICT_OFF = "꺼짐"
VERDICT_OFF_PROD = "꺼짐(운영)"
VERDICT_BROKEN = "막힘"

# 로그인 갱신 결과 누계의 화면 이름(`runtime.REFRESH_OUTCOMES` 차례).
REFRESH_OUTCOME_LABELS: dict[str, str] = {
    "renewed": "다시 발급",
    "skipped": "건너뜀",
    "unauthorized": "로그인 없음",
    "forbidden": "출처·머리 거절",
    "bad_request": "꼴 거절",
}
# 로그인 갱신 누계 줄의 풍선 — 범위와 「출처·머리 거절」 을 읽는 법(설계 규칙 UI-TXT-01).
REFRESH_HELP = (
    "앱을 쓰는 동안 로그인을 늘린 횟수의 기동 뒤 누계입니다 — 재시작하면 0 입니다. 「출처·머리 "
    f"거절」 만 늘고 「다시 발급」 이 0 이면 접속 주소가 `{names.ENV_PUBLIC_URL}` 과 같은지 봅니다."
)
# redirect_uri 줄의 풍선 — 포털 등록값과 대 보는 법.
REDIRECT_HELP = "redirect\\_uri 는 포털 Endpoint URL 과 한 글자도 같아야 합니다."
ANONYMOUS_HELP = "로그인하지 않은 누구나 보낼 수 있는 요청이라 따로 셉니다."

# S3 명단을 읽거나 쓰지 못한 까닭의 화면 이름(`io/s3_small` · `auth/access_store` 분류).
ACCESS_PROBLEM_LABELS: dict[str, str] = {
    s3_small.KIND_UNREACHABLE: "주소에 닿지 못함",
    s3_small.KIND_TIMEOUT: "시간 초과",
    s3_small.KIND_TLS: "인증서 확인 실패",
    s3_small.KIND_AUTH: "인증 거절",
    s3_small.KIND_NO_BUCKET: "버킷 없음",
    s3_small.KIND_TOO_LARGE: "파일이 너무 큼",
    s3_small.KIND_OTHER: "그 밖의 응답",
    access_store.KIND_CORRUPT: "파일 깨짐",
    access_store.KIND_UNKNOWN_FORMAT: "모르는 파일 판",
    access_store.KIND_CONFIG: "설정 값 빠짐 · 틀림",
    access_store.KIND_FILE_GONE: "파일 없음",
}

ON_CAPTION_LISTED = "통합인증이 켜져 있습니다 — 로그인하고 접속 명단에 있는 사람만 앱에 들어옵니다."
ON_CAPTION_UNLISTED = (
    "통합인증이 켜져 있습니다 — 접속 명단이 꺼져 있어 로그인한 사람은 모두 들어옵니다."
)
OFF_IN_PRODUCTION_CONCLUSION = (
    "운영 서버인데 통합인증이 꺼져 있습니다 — 주소를 아는 사람은 누구나 들어옵니다."
)
OFF_IN_PRODUCTION_HELP = (
    f"포털 승인 메일의 Client ID 를 환경변수(`{names.ENV_CLIENT_ID}`)에 넣으면 켜집니다."
)
OFF_IN_PRODUCTION_WARNING = f"{OFF_IN_PRODUCTION_CONCLUSION} {OFF_IN_PRODUCTION_HELP}"
BROKEN_CONCLUSION = "통합인증 설정을 마치지 못했습니다"


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
        # 파일이 없는 동안 이 목록은 첫 판이다 — 「쓰지 않음」 이 아니다.
        if notice.code == "s3_users_ignored" and not access_store.holds_a_file():
            continue
        notices.setdefault(notice.env, []).append(notice)
    rows: list[tuple[str, str, str]] = []
    for name in names.SSO_ENVIRONMENT:
        present = cfg.env_presence.get(name, False)
        found = issues.pop(name, [])
        if found:
            status = "틀림" if present else "없음"
            reason = _problem_text(found)
        elif name == names.ENV_SECRET and present:
            status, reason = "있음", SECRET_CHECKS_PASSED
        else:
            status, reason = ("있음" if present else "없음"), ""
        extra = _problem_text(notices.pop(name, []))
        rows.append((name, status, " · ".join(part for part in (reason, extra) if part)))
    for env, found in issues.items():
        rows.append((env, "틀림", _problem_text(found)))
    return pd.DataFrame(rows, columns=["환경변수", "상태", "까닭"])


def _days_left(now: datetime, not_after: datetime) -> int:
    return (not_after - now).days


def access_line(cfg: SsoConfig) -> str:
    """접속 명단 사실 한 줄 — 개수만. 통합인증이 켜져 있지 않으면 명단은 아직 듣지 않는다."""
    access = runtime.current_access(cfg)
    if not access.enforced:
        return "접속 명단: 꺼짐(인증된 사람 전부)"
    state = "켜짐" if cfg.mode is SsoMode.ON else "통합인증이 켜지면 적용"
    return (
        f"접속 명단: {state} · 관리자 {access.admin_count} · 사용자 {access.user_count} · "
        f"읽지 못함 {access.unreadable_count}"
    )


def access_problem_text(problem: SourceProblem) -> str:
    """까닭 한 조각 — 분류 이름과 HTTP 상태 · 저장소 오류 코드. 값 · 키는 어디에도 없다."""
    label = ACCESS_PROBLEM_LABELS.get(problem.kind, problem.kind)
    details = [f"HTTP {problem.status}" if problem.status else "", literal_markdown(problem.code)]
    details = [item for item in details if item]
    return f"{label}({' · '.join(details)})" if details else label


def _write_text(saved_at: int | None, problem: SourceProblem | None) -> str:
    if problem is not None:
        verdict = "결과 모름" if problem.unconfirmed else "실패"
        return f"쓰기: {verdict} · {access_problem_text(problem)}"
    if saved_at is not None:
        return f"쓰기: 정상 · {_clock_text(saved_at)}"
    return "쓰기: 저장할 때 알게 됨"


def access_s3_line(cfg: SsoConfig) -> str:
    """S3 명단 한 줄 — 꺼짐 · 정상 · 실패와 그 까닭. 키 · 서명 · 주소 · 명단 값을 싣지 않는다."""
    if not cfg.access_s3_requested:
        return "S3 명단: 꺼짐"
    if cfg.mode is not SsoMode.ON:
        return "S3 명단: 통합인증이 켜지면 적용"
    source = runtime.access_source()
    if source is None:
        return "S3 명단: 실패 · 아직 읽지 않음 · 관리자만 들어옴"
    parts = ["S3 명단: 정상" if source.problem is None else "S3 명단: 실패"]
    if source.problem is not None:
        parts.append(access_problem_text(source.problem))
        if source.attempted_at is not None:
            parts.append(f"시도 {_clock_text(source.attempted_at)}")
        retries = runtime.access_retry_failures()
        if retries:
            parts.append(f"자가 회복 실패 {retries}")
    document = source.document
    if document is None or source.read_at is None:
        parts.append("마지막 읽기 없음 · 관리자만 들어옴")
    else:
        parts += [
            f"마지막 읽기 {_clock_text(source.read_at)}",
            f"사용자 {len(document.entries)}",
            f"판 {document.revision}",
        ]
        if source.seeded:
            parts.append("환경변수 첫 판 · 파일 없음")
        if document.demoted:
            parts.append(f"등급을 사용자로 읽음 {document.demoted}")
    parts.append(_write_text(source.saved_at, source.save_problem))
    return " · ".join(parts)


def fact_lines(
    cfg: SsoConfig, *, now: datetime | None = None, shareable: bool = False
) -> list[str]:
    """표 아래 한 줄씩 — redirect_uri · issuer · 인증서 · 유지 시간 · 쿠키 이름 · 문지기 · 명단.

    첫 줄은 redirect_uri 다 — 화면이 그 풍선을 그 줄에 단다(`render_sso_status`).

    `shareable` 이면 포털 등록값 셋(redirect_uri · issuer · 인증서 지문)을 글자 그대로 싣지 않는다 —
    화면에서는 포털과 한 글자씩 대 보지만 리뷰에는 옮기지 않는 값이고(Guide), 복사 글은 리뷰로
    나간다(`status_text`).
    """
    moment = now or datetime.now(timezone.utc)
    redirect = literal_markdown(cfg.redirect_uri) if cfg.redirect_uri else "계산하지 못함"
    issuer = literal_markdown(cfg.issuer) if cfg.issuer else "없음"
    if shareable:
        redirect = "있음" if cfg.redirect_uri else redirect
        issuer = "있음" if cfg.issuer else issuer
    lines = [
        f"redirect\\_uri: {redirect}",
        f"`{names.ENV_ISSUER}`: {issuer}",
        f"`{names.ENV_CLIENT_ID}`: {'있음' if cfg.client_id else '없음'}",
    ]
    for cert in cfg.signing_certs:
        days = _days_left(moment, cert.not_after)
        thumbprint = (
            ""
            if shareable
            else f"x5t {literal_markdown(cert.x5t)} · SHA-256 {cert.sha256[:16]}… · "
        )
        lines.append(
            f"서명 인증서 {thumbprint}만료 {cert.not_after.strftime('%Y-%m-%d')}"
            f"(남은 날 {days}) · RSA {cert.key_bits}비트"
        )
    lines += [
        f"로그인 유지: 마지막 사용 뒤 {cfg.session_hours}시간 · 최대 {cfg.session_max_hours}시간 · "
        f"세션 쿠키 이름: {literal_markdown(cfg.session_cookie)}",
        f"문지기: {'있음' if runtime.gate_installed() else '없음(app.py 로 뜸)'} · "
        f"잠금(`{names.ENV_SSO}=required`): {'예' if cfg.locked else '아니오'}",
        access_line(cfg),
        access_s3_line(cfg),
    ]
    return lines


def last_claims_line() -> str:
    """마지막 로그인의 클레임 이름 한 줄 — 값은 없다. 그룹 클레임이 있는지 여기서 본다."""
    claim_names = runtime.last_login_claims()
    listed = " · ".join(literal_markdown(name) for name in claim_names) or "아직 없음"
    return f"마지막 로그인의 클레임 이름: {listed}"


def refresh_count_line() -> str:
    """로그인 갱신 결과 누계 한 줄(기동 뒤 — 재시작하면 0).

    「출처·머리 거절」 이 있는데 「다시 발급」 이 0 이면 앞단이 갱신 머리 · `Origin` 을 버리거나
    접속 주소가 `CAPA_PUBLIC_URL` 과 다른 것이다 — 읽는 법은 풍선(`REFRESH_HELP`)과 Guide 가 말한다.
    """
    counts = runtime.refresh_counts()
    items = " · ".join(
        f"{REFRESH_OUTCOME_LABELS[outcome]} {counts[outcome]}"
        for outcome in runtime.REFRESH_OUTCOMES
    )
    return f"로그인 갱신(기동 뒤 누계): {items}"


def readiness_line(cfg: SsoConfig) -> str:
    """꺼짐 때 「켜면 막힐 문제」 한 줄 — client id 를 넣기 전에 나머지 값을 미리 본다."""
    if not cfg.readiness:
        return "켜면 막힐 문제: 없음"
    items = " · ".join(f"`{problem.env}` — {problem.reason}" for problem in cfg.readiness)
    return f"켜면 막힐 문제: {items}"


def _event_code(fields: dict[str, str]) -> str:
    """사건 표의 「사유 코드」 칸 — 실패 사유 · IdP 오류 · 설정 문제 이름 · 인증서 남은 날 차례.

    만료로 닫힌 열린 탭(`session_closed`)은 끝난 까닭 `end`(idle · max)를 붙인다 — C-DEP 에는 서버
    로그 창구가 없어 「쓰는 중인데 끊겼다」 문의를 하루 상한인지 유휴인지 이 칸으로 가른다.
    """
    for key in ("reason", "error", "problems", "mode"):
        value = fields.get(key, "")
        if value and value != "-":
            end = fields.get("end", "")
            return f"{value} · {end}" if end and end != "-" else value
    days = fields.get("days", "")
    return f"남은 날 {days}" if days else "-"


def _clock_text(at: int) -> str:
    return datetime.fromtimestamp(at).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def recent_event_table(limit: int = RECENT_EVENT_LIMIT, *, anonymous: bool = False) -> pd.DataFrame:
    """최근 사건(새것 먼저) — 시각 | 사건 | 사유 코드 | 계정(앞 두 글자).

    기본은 무인증 실패를 뺀 고리(설정 · 로그인 · 로그아웃 · 연결 닫음 · 서명이 통과한 뒤의 실패)다 —
    로그인하지 않은 누구나 남길 수 있는 실패가 이 표를 밀어내지 못한다. `anonymous=True` 면 그
    실패만 따로 본다. IdP 의 오류 설명(`error_description`)은 싣지 않는다.
    """
    rows = []
    for event in runtime.recent_events(limit, anonymous=anonymous):
        fields = dict(event.fields)
        loginid = fields.get("loginid", "-")
        rows.append(
            (
                _clock_text(event.at),
                event.event,
                _event_code(fields),
                mask_account(loginid) if loginid and loginid != "-" else "-",
            )
        )
    return pd.DataFrame(rows, columns=["시각", "사건", "사유 코드", "계정"])


def denied_account_line() -> str | None:
    """명단 밖 로그인 누계 한 줄(기동 뒤 — 재시작하면 0). 아무도 막히지 않았으면 `None`."""
    total = runtime.denied_total()
    if not total:
        return None
    return f"명단 밖 로그인(기동 뒤 누계 {total} · 계정 {len(runtime.denied_accounts())})"


def denied_account_table(limit: int = DENIED_ACCOUNT_LIMIT) -> pd.DataFrame:
    """명단 밖 로그인(최근에 막힌 사람 먼저) — 마지막 시각 | 계정(앞 두 글자) | 횟수."""
    rows = [
        (_clock_text(item.last_at), mask_account(item.loginid), item.count)
        for item in runtime.denied_accounts(limit)
    ]
    return pd.DataFrame(rows, columns=["마지막 시각", "계정", "횟수"])


def anonymous_failure_line(limit: int = ANONYMOUS_COUNT_LIMIT) -> str | None:
    """무인증 실패 누계 한 줄(기동 뒤 · 사유별 · 많은 것 먼저). 없으면 `None`."""
    counts = runtime.anonymous_failure_counts()
    if not counts:
        return None
    total = sum(counts.values())
    items = list(counts.items())
    shown = " · ".join(f"{literal_markdown(key)} {count}" for key, count in items[:limit])
    rest = f" · 그 밖 {len(items) - limit}가지" if len(items) > limit else ""
    return f"로그인 전 실패: 누계 {total} · {shown}{rest}"


def _cert_warning() -> str:
    return (
        f"서명 인증서 만료가 {CERT_WARNING_DAYS}일 안입니다 — 새 인증서를 "
        f"`{names.ENV_SIGNING_CERT}` 에 쉼표로 더해 두세요(`{names.SETUP_DOC}`)."
    )


def _expiring_certs(cfg: SsoConfig, now: datetime) -> list[str]:
    return [
        cert.x5t
        for cert in cfg.signing_certs
        if _days_left(now, cert.not_after) <= CERT_WARNING_DAYS
    ]


def _viewer_is_admin(cfg: SsoConfig) -> bool:
    identity = sso_identity.verified_identity()
    return identity is not None and access_store.is_admin(cfg, identity.loginid)


def _access_read_alert(cfg: SsoConfig) -> None:
    """상태 알림 `AD-08` — 못 읽은 동안은 관리자만 들어오고, 읽어 둔 뒤의 실패는 지난 명단이다.

    조치 알림이고 그 자리(「다시 읽기」)가 관리자에게만 있어 관리자 회차에만 세운다. 다른 사람의
    회차는 해소로 부른다 — 사실은 「통합인증 점검」 의 「S3 명단」 줄이 그대로 말한다.
    """
    source = runtime.access_source()
    problem = None if source is None else source.problem
    unread = access_store.is_unread(cfg)
    active = (problem is not None or unread) and _viewer_is_admin(cfg)
    effect = "관리자만 들어옵니다" if unread else "지난 명단으로 판정합니다"
    alerts.state(
        "AD-08",
        scope=None,
        content=(problem, unread) if active else None,
        active=active,
        text=f"접속 명단을 S3 에서 읽지 못했습니다 — {effect}",
        full=(
            f"접속 명단을 S3 에서 읽지 못했습니다"
            f"{f'({access_problem_text(problem)})' if problem is not None else ''} — {effect}. "
            "Admin 「접속 명단」 의 「다시 읽기」 로 다시 읽습니다."
        ),
    )


def _access_seed_alert(cfg: SsoConfig) -> None:
    """상태 알림 `AD-09` — 파일이 없어 환경변수 목록으로 판정하는 동안. 첫 저장이 쓰면 풀린다.

    `AD-08` 과 같이 그 자리(「접속 명단」)가 있는 관리자 회차에만 세운다.
    """
    source = runtime.access_source()
    seeded = source is not None and source.seeded and _viewer_is_admin(cfg)
    alerts.state(
        "AD-09",
        scope=None,
        content=None,
        active=seeded,
        text="접속 명단이 환경변수 첫 판입니다 — S3 파일 없음",
        full=(
            "S3 명단 파일이 아직 없어 CAPA_ACCESS_USERS 를 첫 판으로 씁니다. Admin 「접속 명단」 "
            "에서 첫 저장을 하면 파일이 생기고, 그 뒤에는 환경변수를 듣지 않습니다."
        ),
    )


def _conclusion(cfg: SsoConfig) -> str:
    if cfg.mode is SsoMode.ON:
        return ON_CAPTION_LISTED if cfg.access.enforced else ON_CAPTION_UNLISTED
    return OFF_IN_PRODUCTION_CONCLUSION if cfg.mode is SsoMode.OFF else BROKEN_CONCLUSION


def status_text(title: str, cfg: SsoConfig, *, now: datetime) -> str:
    """「복사」 글 — 펼침과 같은 차례의 결론 · 표 · 사실 · 사건. 복사 글은 리뷰로 나가므로 포털
    등록값 셋은 있음 · 없음으로만 싣는다(`fact_lines` 의 `shareable`). 그 밖의 줄에는 원래 비밀값 ·
    주소 · 명단 값이 없고 계정은 앞 두 글자뿐이다(모듈 설명)."""
    head = [_conclusion(cfg)]
    if cfg.mode is SsoMode.OFF:
        head.append(readiness_line(cfg))
    facts = fact_lines(cfg, now=now, shareable=True)
    if cfg.mode is SsoMode.ON:
        facts += [refresh_count_line(), last_claims_line()]
    events = recent_event_table()
    denied = denied_account_line()
    anonymous = anonymous_failure_line()
    return diagnostic_text(
        title,
        plain_lines(head),
        table_lines(environment_table(cfg)),
        plain_lines(facts),
        ["최근 사건 없음"] if events.empty else ["최근 사건(새것 먼저)", *table_lines(events)],
        [] if denied is None else [denied, *table_lines(denied_account_table())],
        (
            []
            if anonymous is None
            else [
                *plain_lines([anonymous]),
                *table_lines(recent_event_table(ANONYMOUS_EVENT_LIMIT, anonymous=True)),
            ]
        ),
    )


def render_sso_status() -> None:
    """Admin Area 「통합인증 점검」 펼침. 꺼짐이고 운영이 아니면 그리지 않는다.

    알릴 조건 둘(운영인데 꺼짐 `AD-02` · 서명 인증서 만료 임박 `AD-03`)은 상태 알림이다(알림창 ·
    Alarm — 그리지 않는 회차에도 부른다, 해소). S3 명단을 읽지 못함(`AD-08`)은 그 명단을 쓰는
    서버에서만 부르고(설정은 재시작 전에 바뀌지 않으니 해소할 것이 없다 — 꺼진 서버의 요소 순번은
    그대로다) 관리자 회차에만 세운다. 펼침 안의 결론은 값 한 줄이고 하는 법 · 보관 범위는 풍선 ·
    Guide 가 말한다 — 인증서 만료 임박은 `AD-03` 과 표 까닭 칸이 말하므로 줄을 따로 세우지 않는다
    (설계 규칙 UI-TXT-01 · 04 · UI-NTF-02)."""
    cfg = runtime.config()
    now = datetime.now(timezone.utc)
    expiring = _expiring_certs(cfg, now)
    off_in_production = cfg.mode is SsoMode.OFF and cfg.prod
    alerts.state(
        "AD-02",
        scope=None,
        content=off_in_production or None,
        active=off_in_production,
        text="운영 서버인데 통합인증이 꺼져 있습니다 — Client ID 환경변수를 넣으세요",
        full=alerts.plain_text(OFF_IN_PRODUCTION_WARNING),
    )
    alerts.state(
        "AD-03",
        scope=None,
        content=sorted(expiring) or None,
        active=bool(expiring),
        text=f"통합인증 서명 인증서 만료가 {CERT_WARNING_DAYS}일 안입니다 — 새 인증서를 더하세요",
        full=alerts.plain_text(_cert_warning()),
    )
    if access_store.is_on(cfg):
        _access_read_alert(cfg)
        _access_seed_alert(cfg)
    if cfg.mode is SsoMode.OFF and not cfg.prod:
        return
    title = f"통합인증 점검 · {sso_verdict(cfg)}"
    with remembered_expander(title, icon=":material/verified_user:", key=EXPANDER_KEY):
        render_diagnostic_copy(status_text(title, cfg, now=now), key=COPY_KEY)
        if cfg.mode is SsoMode.ON:
            st.caption(ON_CAPTION_LISTED if cfg.access.enforced else ON_CAPTION_UNLISTED)
        elif cfg.mode is SsoMode.OFF:
            st.caption(
                f":material/lock_open: {OFF_IN_PRODUCTION_CONCLUSION}",
                help=OFF_IN_PRODUCTION_HELP,
            )
            st.caption(readiness_line(cfg))
        else:
            st.error(BROKEN_CONCLUSION, icon=":material/gpp_bad:")
        st.dataframe(environment_table(cfg), hide_index=True, width="stretch")
        redirect, *facts = fact_lines(cfg, now=now)
        st.caption(redirect, help=REDIRECT_HELP)
        st.caption("  \n".join(facts))
        if cfg.mode is SsoMode.ON:
            # 꺼짐(운영)은 갱신 경로가 404 라 누계가 늘 0 이고 로그인도 없다 — 켜짐에서만 싣는다.
            st.caption(refresh_count_line(), help=REFRESH_HELP)
            st.caption(last_claims_line())
        events = recent_event_table()
        if events.empty:
            st.caption("최근 사건 없음")
        else:
            st.caption("최근 사건(새것 먼저)")
            st.dataframe(events, hide_index=True, width="stretch")
        denied = denied_account_line()
        if denied is not None:
            st.caption(denied)
            st.dataframe(denied_account_table(), hide_index=True, width="stretch")
        anonymous = anonymous_failure_line()
        if anonymous is not None:
            st.caption(anonymous, help=ANONYMOUS_HELP)
            st.dataframe(
                recent_event_table(ANONYMOUS_EVENT_LIMIT, anonymous=True),
                hide_index=True,
                width="stretch",
            )
