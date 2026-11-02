# Purpose: ID 토큰(RS256) 검증과 세션·상태 토큰(HS256) 발급·검증 — 실패는 사유 코드로.

"""통합인증 토큰.

- **ID 토큰** — IdP 가 form_post 로 보낸 RS256 토큰. 환경변수로 받은 서명 인증서(핀 고정)로 서명을
  보고 `aud == ADFS_CLIENT_ID`(strict) · `iss == ADFS_ISSUER`(정확 일치) · exp/iat/nbf(여유 120초) ·
  nonce · iat 신선도(10분)를 본다. 알고리즘은 RS256 하나로 묶는다(`none` · HS256 혼동을 막는 본
  방어).
- **세션 토큰** — 우리가 발급하는 HS256 토큰. HttpOnly 쿠키에 담는다. 원 id_token · 그룹 · 이메일은
  넣지 않는다.
- **상태 토큰** — 로그인 시작 때 state · nonce · 돌아갈 자리를 담아 쿠키로 둔다(10분).

세션 · 상태 토큰의 키는 `JWT_SECRET_KEY` 에서 쓰임별로 파생한다 — 서로 바꿔 끼울 수 없다(aud 도
따로). PyJWT 는 함수 안에서 import 한다 — 통합인증이 꺼진 서버는 이 패키지가 없어도 뜬다.

실패는 모두 `SsoReject(code)` 다. 코드는 오류 화면 · 로그가 그대로 쓴다. 진단(`diagnostic`)에는
서명이 통과한 뒤에만 받은 iss · aud · 시각을 담고, 토큰 · state · nonce · 클레임 값은 담지 않는다.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from capa_simulation.auth.config import SigningCert, SsoConfig

if TYPE_CHECKING:
    from jwt import PyJWT
    from jwt.types import Options

ISSUER = "capa-simulation"
SESSION_AUDIENCE = "capa-simulation:session"
STATE_AUDIENCE = "capa-simulation:sso-state"
SESSION_PURPOSE = b"capa-sso/session/v1"
STATE_PURPOSE = b"capa-sso/state/v1"
SESSION_VERSION = 1

ID_TOKEN_LEEWAY = 120
ID_TOKEN_MAX_AGE = 600
SESSION_LEEWAY = 30
STATE_TTL = 600

LOGINID_PATTERN = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
MAX_DISPLAY_LENGTH = 100
MAX_DIAGNOSTIC_LENGTH = 200
MAX_CLAIM_NAMES = 60
_HEADER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_JTI = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class SsoReject(Exception):
    """로그인 거절.

    `code` 는 사유 코드(오류 화면 · 로그), `loginid` 는 서명이 통과했을 때만 채운다(로그용).
    """

    def __init__(
        self,
        code: str,
        *,
        diagnostic: Mapping[str, str] | None = None,
        loginid: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostic: dict[str, str] = dict(diagnostic or {})
        self.loginid = loginid


@dataclass(frozen=True)
class VerifiedLogin:
    """검증을 마친 ID 토큰에서 꺼낸 신원. 이름 · 부서는 없을 수 있다."""

    loginid: str
    name: str | None
    dept: str | None
    claim_names: tuple[str, ...]


@dataclass(frozen=True)
class SessionClaims:
    loginid: str
    name: str | None
    dept: str | None
    iat: int
    exp: int
    jti: str


@dataclass(frozen=True)
class StateClaims:
    state: str
    nonce: str
    next_path: str
    iat: int
    exp: int


def derive_key(secret: bytes, purpose: bytes) -> bytes:
    """`HMAC-SHA256(secret, purpose)` — 쓰임마다 다른 키."""
    return hmac.new(secret, purpose, hashlib.sha256).digest()


def session_key(cfg: SsoConfig) -> bytes:
    if not cfg.secret:
        raise SsoReject("config_broken")
    return derive_key(cfg.secret, SESSION_PURPOSE)


def state_key(cfg: SsoConfig) -> bytes:
    if not cfg.secret:
        raise SsoReject("config_broken")
    return derive_key(cfg.secret, STATE_PURPOSE)


@functools.cache
def _api() -> PyJWT:
    import jwt

    # 짧은 키를 경고가 아니라 거절로 — RSA 2048 · HMAC 32바이트 미만.
    return jwt.PyJWT(options={"enforce_minimum_key_length": True})


def clean_text(value: object, limit: int) -> str:
    """진단 · 표시용 글자 — 제어 · 서식 문자(Cc · Cf)를 빼고 자른다."""
    text = value if isinstance(value, str) else str(value)
    kept = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf"))
    return kept.strip()[:limit]


def _display_claim(value: object) -> str | None:
    """이름 · 부서 클레임 — 문자열 또는 원소 하나인 목록만. 비면 None."""
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, str):
        return None
    text = clean_text(value, MAX_DISPLAY_LENGTH)
    return text or None


def _utc_text(seconds: object) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return clean_text(seconds, 40)
    try:
        moment = datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return clean_text(seconds, 40)
    return f"{int(seconds)} ({moment.strftime('%Y-%m-%d %H:%M:%S')} UTC)"


def _header_id(value: object) -> str:
    return value if isinstance(value, str) and _HEADER_ID.match(value) else ""


def pick_certs(certs: Sequence[SigningCert], x5t: str, kid: str) -> tuple[list[SigningCert], bool]:
    """(시도할 차례, 헤더 지문이 맞은 것이 있었나). 맞는 것 먼저, 나머지도 뒤에 붙인다."""
    hints = {item for item in (x5t, kid) if item}
    matched = [cert for cert in certs if cert.x5t in hints]
    rest = [cert for cert in certs if cert not in matched]
    return matched + rest, bool(matched)


def _claims_diagnostic(cfg: SsoConfig, claims: Mapping[str, Any], now: int) -> dict[str, str]:
    aud = claims.get("aud")
    got_aud = ", ".join(str(item) for item in aud) if isinstance(aud, list) else aud
    return {
        "expected_iss": cfg.issuer,
        "got_iss": clean_text(claims.get("iss", "-"), MAX_DIAGNOSTIC_LENGTH),
        "expected_aud": cfg.client_id,
        "got_aud": clean_text(got_aud if got_aud is not None else "-", MAX_DIAGNOSTIC_LENGTH),
        "iat": _utc_text(claims.get("iat", "-")),
        "exp": _utc_text(claims.get("exp", "-")),
        "server_time": _utc_text(now),
    }


def _signed_claims_without_checks(token: str, cert: SigningCert) -> dict[str, Any] | None:
    """서명 검증은 켠 채 클레임 검사만 끈 두 번째 읽기 — 진단에만 쓴다."""
    import jwt

    options: Options = {
        "verify_signature": True,
        "verify_aud": False,
        "verify_iss": False,
        "verify_exp": False,
        "verify_iat": False,
        "verify_nbf": False,
        "verify_sub": False,
        "verify_jti": False,
        "require": [],
    }
    try:
        return _api().decode(token, key=cert.public_key, algorithms=["RS256"], options=options)
    except jwt.PyJWTError:
        return None


def _loginid_of(claims: Mapping[str, Any] | None, cfg: SsoConfig) -> str | None:
    if claims is None:
        return None
    value = claims.get(cfg.claim_loginid)
    if isinstance(value, str) and LOGINID_PATTERN.match(value.strip()):
        return value.strip()
    return None


def _reject_after_signature(
    exc: Exception, token: str, cert: SigningCert, cfg: SsoConfig, now: int
) -> SsoReject:
    import jwt

    if isinstance(exc, jwt.MissingRequiredClaimError):
        claim = exc.claim
        code = {
            "nonce": "nonce_missing",
            "aud": "aud_mismatch",
            "iss": "iss_mismatch",
        }.get(claim, "token_malformed")
    elif isinstance(exc, jwt.ExpiredSignatureError):
        code = "token_expired"
    elif isinstance(exc, jwt.ImmatureSignatureError):
        code = "token_not_yet_valid"
    elif isinstance(exc, jwt.InvalidAudienceError):
        code = "aud_mismatch"
    elif isinstance(exc, jwt.InvalidIssuerError):
        code = "iss_mismatch"
    elif isinstance(exc, jwt.InvalidAlgorithmError):
        code = "alg_not_allowed"
    else:
        code = "token_malformed"
    diagnostic: dict[str, str] = {"server_time": _utc_text(now)}
    claims: dict[str, Any] | None = None
    if code in ("token_expired", "token_not_yet_valid", "aud_mismatch", "iss_mismatch"):
        claims = _signed_claims_without_checks(token, cert)
        if claims is not None:
            diagnostic = _claims_diagnostic(cfg, claims, now)
    return SsoReject(code, diagnostic=diagnostic, loginid=_loginid_of(claims, cfg))


def _signature_diagnostic(cfg: SsoConfig, x5t: str, kid: str) -> dict[str, str]:
    return {
        "token_x5t": x5t or "-",
        "token_kid": kid or "-",
        "configured_x5t": ", ".join(cert.x5t for cert in cfg.signing_certs) or "-",
    }


def verify_id_token(token: str, cfg: SsoConfig, *, expected_nonce: str, now: int) -> VerifiedLogin:
    """IdP 가 보낸 id_token 을 끝까지 검증해 신원을 꺼낸다. 실패는 `SsoReject`."""
    import jwt

    if not token:
        raise SsoReject("token_missing")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise SsoReject("token_malformed") from exc
    alg = header.get("alg")
    if alg != "RS256":
        raise SsoReject("alg_not_allowed", diagnostic={"alg": clean_text(alg, 20) or "-"})
    x5t = _header_id(header.get("x5t"))
    kid = _header_id(header.get("kid"))
    ordered, matched = pick_certs(cfg.signing_certs, x5t, kid)
    options: Options = {"require": ["exp", "iat", "aud", "iss", "nonce"], "strict_aud": True}
    claims: dict[str, Any] | None = None
    for cert in ordered[:3]:
        try:
            claims = _api().decode(
                token,
                key=cert.public_key,
                algorithms=["RS256"],
                audience=cfg.client_id,
                issuer=cfg.issuer,
                leeway=ID_TOKEN_LEEWAY,
                options=options,
            )
            break
        except (jwt.InvalidSignatureError, jwt.InvalidKeyError):
            continue
        except jwt.DecodeError as exc:
            raise SsoReject("token_malformed") from exc
        except jwt.PyJWTError as exc:
            raise _reject_after_signature(exc, token, cert, cfg, now) from exc
    if claims is None:
        code = "signing_key_unknown" if (x5t or kid) and not matched else "signature_invalid"
        raise SsoReject(code, diagnostic=_signature_diagnostic(cfg, x5t, kid))

    loginid_hint = _loginid_of(claims, cfg)
    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not hmac.compare_digest(
        nonce.encode("utf-8"), expected_nonce.encode("utf-8")
    ):
        raise SsoReject("nonce_mismatch", loginid=loginid_hint)
    iat = claims.get("iat")
    if isinstance(iat, bool) or not isinstance(iat, (int, float)):
        raise SsoReject("token_malformed", loginid=loginid_hint)
    if now - int(iat) > ID_TOKEN_MAX_AGE + ID_TOKEN_LEEWAY:
        raise SsoReject(
            "token_stale",
            diagnostic={"iat": _utc_text(iat), "server_time": _utc_text(now)},
            loginid=loginid_hint,
        )

    claim_names = tuple(sorted(clean_text(name, MAX_DISPLAY_LENGTH) for name in claims))[
        :MAX_CLAIM_NAMES
    ]
    names_text = ", ".join(claim_names)
    raw_loginid = claims.get(cfg.claim_loginid)
    if raw_loginid is None:
        raise SsoReject(
            f"claim_missing:{cfg.claim_loginid}", diagnostic={"claim_names": names_text}
        )
    if not isinstance(raw_loginid, str) or not LOGINID_PATTERN.match(raw_loginid.strip()):
        raise SsoReject(
            f"claim_invalid:{cfg.claim_loginid}", diagnostic={"claim_names": names_text}
        )
    return VerifiedLogin(
        loginid=raw_loginid.strip(),
        name=_display_claim(claims.get(cfg.claim_username)),
        dept=_display_claim(claims.get(cfg.claim_deptname)),
        claim_names=claim_names,
    )


def issue_session(
    cfg: SsoConfig, *, loginid: str, name: str | None, dept: str | None, now: int
) -> tuple[str, SessionClaims]:
    """우리 세션 토큰(HS256)을 만든다."""
    jti = secrets.token_urlsafe(16)
    exp = now + cfg.session_seconds
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": SESSION_AUDIENCE,
        "sub": loginid,
        "iat": now,
        "exp": exp,
        "jti": jti,
        "v": SESSION_VERSION,
    }
    if name:
        payload["name"] = name
    if dept:
        payload["dept"] = dept
    token = _api().encode(payload, session_key(cfg), algorithm="HS256")
    return token, SessionClaims(loginid=loginid, name=name, dept=dept, iat=now, exp=exp, jti=jti)


def verify_session(token: str, cfg: SsoConfig, *, now: int) -> SessionClaims:
    """세션 쿠키 값 → 신원. 만료는 `session_expired`, 그 밖 모든 실패는 `session_invalid`."""
    import jwt

    if not token or len(token) > 4096:
        raise SsoReject("session_invalid")
    options: Options = {"require": ["exp", "iat", "sub", "jti"], "strict_aud": True}
    try:
        claims = _api().decode(
            token,
            key=session_key(cfg),
            algorithms=["HS256"],
            audience=SESSION_AUDIENCE,
            issuer=ISSUER,
            leeway=SESSION_LEEWAY,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise SsoReject("session_expired") from exc
    except jwt.PyJWTError as exc:
        raise SsoReject("session_invalid") from exc
    sub, jti, iat, exp = claims.get("sub"), claims.get("jti"), claims.get("iat"), claims.get("exp")
    if (
        not isinstance(sub, str)
        or not LOGINID_PATTERN.match(sub)
        or not isinstance(jti, str)
        or not _JTI.match(jti)
        or isinstance(iat, bool)
        or not isinstance(iat, int)
        or isinstance(exp, bool)
        or not isinstance(exp, int)
        or claims.get("v") != SESSION_VERSION
    ):
        raise SsoReject("session_invalid")
    if now > exp + SESSION_LEEWAY:
        raise SsoReject("session_expired")
    name, dept = claims.get("name"), claims.get("dept")
    return SessionClaims(
        loginid=sub,
        name=_display_claim(name) if name is not None else None,
        dept=_display_claim(dept) if dept is not None else None,
        iat=iat,
        exp=exp,
        jti=jti,
    )


def issue_state(cfg: SsoConfig, *, state: str, nonce: str, next_path: str, now: int) -> str:
    payload = {
        "iss": ISSUER,
        "aud": STATE_AUDIENCE,
        "st": state,
        "nonce": nonce,
        "next": next_path,
        "iat": now,
        "exp": now + STATE_TTL,
    }
    return _api().encode(payload, state_key(cfg), algorithm="HS256")


def verify_state(token: str, cfg: SsoConfig, *, now: int) -> StateClaims:
    """상태 쿠키 값 → state · nonce · 돌아갈 자리. 서명 · 만료 · 꼴이 틀리면 `state_invalid`."""
    import jwt

    if not token or len(token) > 4096:
        raise SsoReject("state_invalid")
    options: Options = {"require": ["exp", "iat", "st", "nonce"], "strict_aud": True}
    try:
        claims = _api().decode(
            token,
            key=state_key(cfg),
            algorithms=["HS256"],
            audience=STATE_AUDIENCE,
            issuer=ISSUER,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise SsoReject("state_invalid") from exc
    state, nonce, next_path = claims.get("st"), claims.get("nonce"), claims.get("next", "/")
    iat, exp = claims.get("iat"), claims.get("exp")
    if (
        not isinstance(state, str)
        or not isinstance(nonce, str)
        or not isinstance(next_path, str)
        or isinstance(iat, bool)
        or not isinstance(iat, int)
        or isinstance(exp, bool)
        or not isinstance(exp, int)
    ):
        raise SsoReject("state_invalid")
    if now > exp:
        raise SsoReject("state_invalid")
    return StateClaims(state=state, nonce=nonce, next_path=next_path, iat=iat, exp=exp)
