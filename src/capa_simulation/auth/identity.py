# Purpose: 세션 쿠키에서 검증된 신원을 꺼내고 그 끝을 판정한다 — 문지기와 앱 스크립트가 같이 쓴다.

"""쿠키 → 신원.

문지기(`gate`)는 요청의 `Cookie` 머리를, 앱 스크립트는 `st.context.cookies` 맵을 넘긴다. 두 쪽이
**같은 검증**(서명 · aud · iss · 끝 시각 · 로그아웃 폐기 목록 · 접속 명단)을 거치게 이 모듈 하나에
둔다. 세션 상태에 신원을 두는 일이 있어도 그것은 매 회차 여기서 다시 검증한 값의 사본일 뿐이다.

**접속 명단 판정은 `session_check` 한 곳이다.** 문지기 http · 새 핸드셰이크 · 열린 연결의 메시지
(`gate._WatchedSocket`) · `app.py` 의 `require_signed_in` 이 모두 이 함수를 지난다. `app.py`
만으로는 위젯 콜백 · 프래그먼트 회차를 막지 못하므로(`gate` 문서) 자리마다 따로 판정을 두지 않는다.
보는 것은 메모리의 지금 한 벌(`runtime.current_access`)이다 — 판정이 S3 에 가지 않는다.

끝 시각을 보는 갈래는 둘이다.

- **새 요청**(문지기 http · 새 핸드셰이크 · 갱신 · 로그인 경로)은 브라우저가 지금 실은 쿠키라 그
  토큰의 끝만 본다(`renewals=False`). 갱신 표를 보면 탈취된 옛 토큰이 피해자의 사용 덕에 살아난다.
- **핸드셰이크에 묶인 신원**(문지기의 열린 연결 · `app.py` 의 `st.context.cookies`)은 그 연결이
  열린 뒤의 갱신을 모르므로 프로세스 메모리 갱신 표(`runtime.renewed_exp`)와 견줘 늦은 것을 본다
  (`renewals=True`). 어느 쪽이든 상한(`auth_time + 최대`)은 넘지 못한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from starlette.requests import cookie_parser

from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.tokens import (
    SESSION_LEEWAY,
    SessionClaims,
    SsoReject,
    decode_session,
    session_end,
)


@dataclass(frozen=True)
class Identity:
    """로그인한 사람. 이름 · 부서는 IdP 가 주지 않았으면 없다.

    `exp` · `iat` 는 이 신원을 꺼낸 토큰의 것이다 — 끝 시각은 설정과 갱신 표가 있어야 알므로
    `session_end_of` 로 잰다.
    """

    loginid: str
    name: str | None
    dept: str | None
    iat: int
    exp: int
    jti: str
    sid: str
    auth_time: int

    @classmethod
    def from_claims(cls, claims: SessionClaims) -> Identity:
        return cls(
            loginid=claims.loginid,
            name=claims.name,
            dept=claims.dept,
            iat=claims.iat,
            exp=claims.exp,
            jti=claims.jti,
            sid=claims.sid,
            auth_time=claims.auth_time,
        )

    @property
    def display_name(self) -> str:
        return self.name or self.loginid


class IdentityProblem(Enum):
    MISSING = "missing"
    INVALID = "invalid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DENIED = "denied"


def parse_cookie_header(header: str | None) -> dict[str, str]:
    """`Cookie` 머리 → 맵. 브라우저처럼 너그럽게 읽는다(`Request.cookies` 와 같은 함수)."""
    if not header:
        return {}
    return cookie_parser(header)


def session_end_of(
    identity: Identity, cfg: SsoConfig, now: int, *, renewals: bool = True
) -> tuple[int, bool]:
    """`(끝, 상한이 정했나)`. `renewals` 면 갱신 표의 그 sid 끝도 견준다(핸드셰이크에 묶인 신원)."""
    renewed = runtime.renewed_exp(identity.sid, now=now) if renewals else None
    end = session_end(
        exp=identity.exp,
        iat=identity.iat,
        auth_time=identity.auth_time,
        cfg=cfg,
        renewed_exp=renewed,
    )
    return end, end == identity.auth_time + cfg.session_max_seconds


def session_check(
    identity: Identity, cfg: SsoConfig, now: int, *, renewals: bool = True
) -> tuple[IdentityProblem | None, int]:
    """`(문제, 끝)` — `session_problem` 과 같은 판정에 그때 잰 끝(`session_end_of`)을 함께 준다.

    문지기의 열린 연결이 그 끝을 기억해 둔다 — 갱신 표 칸은 끝 + 여유가 지나면 지워지므로 닫는
    순간에는 상한으로 끝났는지 다시 알 수 없다. 차례는 폐기 → 명단 → 끝이다.
    """
    end, _ = session_end_of(identity, cfg, now, renewals=renewals)
    if runtime.session_revoked(identity.sid, now=now):
        return IdentityProblem.REVOKED, end
    if not runtime.current_access(cfg).allows(identity.loginid):
        return IdentityProblem.DENIED, end
    if now > end + SESSION_LEEWAY:
        return IdentityProblem.EXPIRED, end
    return None, end


def session_problem(
    identity: Identity, cfg: SsoConfig, now: int, *, renewals: bool = True
) -> IdentityProblem | None:
    """이미 검증한 신원이 지금도 유효한가 — 로그아웃 폐기 목록 · 접속 명단 · 끝(+ 세션 토큰 검증과
    같은 여유).

    문지기가 websocket 핸드셰이크 뒤 메시지마다 부른다(서명은 핸드셰이크 때 이미 봤다 — HMAC 을 다시
    풀지 않는다). 폐기를 먼저 본다 — 둘 다 거절이라 안전성은 같고, 로그아웃이 갱신 표 칸을 지워
    핸드셰이크 토큰의 끝이 이미 지난 열린 탭도 `REVOKED` 로 가른다(갱신 표가 폐기를 되살리지도
    못한다). 유효하면 `None`.
    """
    problem, _ = session_check(identity, cfg, now, renewals=renewals)
    return problem


def identity_from_cookies(
    cookies: Mapping[str, str], cfg: SsoConfig, now: int, *, renewals: bool = False
) -> Identity | IdentityProblem:
    """쿠키 맵 → 신원. 기본(`renewals=False`)은 새 요청 — 그 토큰 자신의 끝만 본다(엄격)."""
    token = cookies.get(cfg.session_cookie)
    if not token:
        return IdentityProblem.MISSING
    try:
        claims = decode_session(token, cfg, now=now)
    except SsoReject:
        return IdentityProblem.INVALID
    identity = Identity.from_claims(claims)
    problem = session_problem(identity, cfg, now, renewals=renewals)
    return identity if problem is None else problem


def identity_from_cookie_header(
    header: str | None, cfg: SsoConfig, now: int
) -> Identity | IdentityProblem:
    """`Cookie` 머리 → 신원(문지기 http · 새 핸드셰이크 — 엄격)."""
    return identity_from_cookies(parse_cookie_header(header), cfg, now)
