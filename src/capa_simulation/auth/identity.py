# Purpose: 세션 쿠키에서 검증된 신원을 꺼낸다 — 문지기와 앱 스크립트가 같이 쓴다.

"""쿠키 → 신원.

문지기(`gate`)는 요청의 `Cookie` 머리를, 앱 스크립트는 `st.context.cookies` 맵을 넘긴다. 두 쪽이
**같은 검증**(서명 · aud · iss · exp · 로그아웃 폐기 목록)을 거치게 이 모듈 하나에 둔다. 세션 상태에
신원을 두는 일이 있어도 그것은 매 회차 여기서 다시 검증한 값의 사본일 뿐이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from starlette.requests import cookie_parser

from capa_simulation.auth import runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.tokens import SsoReject, verify_session


@dataclass(frozen=True)
class Identity:
    """로그인한 사람. 이름 · 부서는 IdP 가 주지 않았으면 없다."""

    loginid: str
    name: str | None
    dept: str | None
    iat: int
    exp: int
    jti: str

    @property
    def display_name(self) -> str:
        return self.name or self.loginid

    def seconds_left(self, now: int) -> int:
        return self.exp - now


class IdentityProblem(Enum):
    MISSING = "missing"
    INVALID = "invalid"
    EXPIRED = "expired"
    REVOKED = "revoked"


def parse_cookie_header(header: str | None) -> dict[str, str]:
    """`Cookie` 머리 → 맵. 브라우저처럼 너그럽게 읽는다(`Request.cookies` 와 같은 함수)."""
    if not header:
        return {}
    return cookie_parser(header)


def identity_from_cookies(
    cookies: Mapping[str, str], cfg: SsoConfig, now: int
) -> Identity | IdentityProblem:
    token = cookies.get(cfg.session_cookie)
    if not token:
        return IdentityProblem.MISSING
    try:
        claims = verify_session(token, cfg, now=now)
    except SsoReject as exc:
        return IdentityProblem.EXPIRED if exc.code == "session_expired" else IdentityProblem.INVALID
    if runtime.is_revoked(claims.jti):
        return IdentityProblem.REVOKED
    return Identity(
        loginid=claims.loginid,
        name=claims.name,
        dept=claims.dept,
        iat=claims.iat,
        exp=claims.exp,
        jti=claims.jti,
    )


def identity_from_cookie_header(
    header: str | None, cfg: SsoConfig, now: int
) -> Identity | IdentityProblem:
    return identity_from_cookies(parse_cookie_header(header), cfg, now)
