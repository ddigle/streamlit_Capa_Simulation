# Purpose: ID 토큰(RS256) 검증과 세션(발급·갱신)·상태 토큰(HS256) — 실패는 사유 코드로.

"""통합인증 토큰.

- **ID 토큰** — IdP 가 form_post 로 보낸 RS256 토큰. 환경변수로 받은 서명 인증서(핀 고정)로 서명을
  보고 `aud == ADFS_CLIENT_ID`(strict) · `iss == ADFS_ISSUER`(정확 일치) · exp/iat/nbf(여유 120초) ·
  nonce · iat 신선도(10분)를 본다. 알고리즘은 RS256 하나로 묶는다(`none` · HS256 혼동을 막는 본
  방어).
- **세션 토큰** — 우리가 발급하는 HS256 토큰. HttpOnly 쿠키에 담는다. 원 id_token · 그룹 · 이메일은
  넣지 않는다. `sid`(갱신해도 그대로인 세션 묶음 id)와 `auth_time`(처음 ADFS 로그인 시각)을 싣는다.
  끝은 `session_end` 하나가 정한다 — `min(유휴 끝, auth_time + 최대)`, 유휴 끝은 `exp` 를 지금 설정
  (`iat + 세션 시간`)으로 한 번 더 깎은 값이다. 시각 판정은 넘겨받은 `now` 로만 한다(PyJWT 의 exp ·
  iat 검사는 끈다 — 시험이 시계를 쥔다).

  갱신(`renew_session`)은 앱 화면에서 사람이 쓰는 동안 갱신 경로가 부른다. 새 `jti` · `iat=지금` ·
  `exp=min(지금 + 세션 시간, auth_time + 최대)` 로 다시 서명하고 loginid · 이름 · 부서 · `sid` ·
  `auth_time` 은 **검증된 클레임에서만** 옮긴다(요청 값을 쓰지 않는다 — 상한 우회를 막는다). 직전
  발급(보낸 토큰의 `iat` 와 갱신 표에 적힌 그 sid 의 마지막 발급 가운데 늦은 것)에서
  `RENEW_MIN_INTERVAL` 안이거나 상한에 닿아 늘 것이 없으면 다시 서명하지 않는다.
- **상태 토큰** — 로그인 시작 때 state · nonce · 돌아갈 자리를 담아 쿠키로 둔다(10분).

세션 · 상태 토큰의 키는 `JWT_SECRET_KEY` 에서 쓰임별로 파생한다 — 서로 바꿔 끼울 수 없다(aud 도
따로). PyJWT 는 함수 안에서 import 한다 — 통합인증이 꺼진 서버는 이 패키지가 없어도 뜬다.

실패는 모두 `SsoReject(code)` 다. 코드는 오류 화면 · 로그가 그대로 쓴다. 진단(`diagnostic`)에는
서명이 통과한 뒤에만 받은 iss · aud · 시각을 담고, 토큰 · state · nonce · 클레임 값은 담지 않는다.
서명 전 머리에서는 인증서 지문(x5t · kid — base64url 64자까지)과 알려진 JWS alg 이름(그 밖은
`other`)만 담는다 — 로그인 없이 보낸 글이 오류 화면에 서지 않게.
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
SESSION_VERSION = 2

ID_TOKEN_LEEWAY = 120
ID_TOKEN_MAX_AGE = 600
SESSION_LEEWAY = 30
STATE_TTL = 600
# 그 sid 의 직전 발급이 이보다 가까우면(초) 갱신해도 다시 서명하지 않는다 — 탭 여럿 · 같은 옛 쿠키의
# 되풀이 요청을 거른다(직전 발급은 보낸 토큰의 `iat` 와 갱신 표의 발급 시각 가운데 늦은 것).
RENEW_MIN_INTERVAL = 60

# 거절한 id_token 머리의 alg 를 진단에 그대로 싣는 이름(RFC 7518 · 8037) — 그 밖은 `other`.
KNOWN_JWS_ALGS = frozenset(
    {
        "none",
        "HS256",
        "HS384",
        "HS512",
        "RS256",
        "RS384",
        "RS512",
        "ES256",
        "ES384",
        "ES512",
        "PS256",
        "PS384",
        "PS512",
        "EdDSA",
    }
)

LOGINID_PATTERN = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
MAX_DISPLAY_LENGTH = 100
MAX_DIAGNOSTIC_LENGTH = 200
MAX_CLAIM_NAMES = 60
_HEADER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_JTI = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


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
    """세션 토큰의 클레임. `sid` · `auth_time` 은 갱신해도 그대로다."""

    loginid: str
    name: str | None
    dept: str | None
    iat: int
    exp: int
    jti: str
    sid: str
    auth_time: int


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


def _alg_diagnostic(alg: object) -> str:
    """서명 전 머리의 alg — 알려진 JWS 이름이면 그대로, 그 밖은 `other`.

    콜백은 로그인 없이 누구나 보낼 수 있고 진단은 id 만 알면 쿠키 없이 오류 화면에 보인다 — 남이
    고른 글이 앱 출처의 화면에 서지 않게 한다.
    """
    if alg is None or alg == "":
        return "-"
    return alg if isinstance(alg, str) and alg in KNOWN_JWS_ALGS else "other"


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
        raise SsoReject("alg_not_allowed", diagnostic={"alg": _alg_diagnostic(alg)})
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


def session_end(
    *, exp: int, iat: int, auth_time: int, cfg: SsoConfig, renewed_exp: int | None = None
) -> int:
    """세션의 끝(초) — `min(유휴 끝, auth_time + 최대)`. 유효는 `now <= 끝 + SESSION_LEEWAY` 다.

    유휴 끝은 토큰 `exp` 를 지금 설정(`iat + 세션 시간`)으로 한 번 더 깎은 값이고 상한도 지금 설정의
    최대로 잰다 — 설정을 줄여 다시 띄우면 곧바로 듣는다. `renewed_exp` 는 핸드셰이크에 묶인 신원만
    넘긴다(프로세스 메모리 갱신 표의 그 sid 최신 exp) — 유휴 끝과 견줘 늦은 것을 쓰되 상한은 넘지
    못한다.
    """
    idle_end = min(exp, iat + cfg.session_seconds)
    if renewed_exp is not None:
        idle_end = max(idle_end, renewed_exp)
    return min(idle_end, auth_time + cfg.session_max_seconds)


def claims_end(claims: SessionClaims, cfg: SsoConfig) -> int:
    """그 토큰 자신의 끝(갱신 표를 보지 않음)."""
    return session_end(exp=claims.exp, iat=claims.iat, auth_time=claims.auth_time, cfg=cfg)


def _encode_session(cfg: SsoConfig, claims: SessionClaims) -> str:
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": SESSION_AUDIENCE,
        "sub": claims.loginid,
        "iat": claims.iat,
        "exp": claims.exp,
        "jti": claims.jti,
        "sid": claims.sid,
        "auth_time": claims.auth_time,
        "v": SESSION_VERSION,
    }
    if claims.name:
        payload["name"] = claims.name
    if claims.dept:
        payload["dept"] = claims.dept
    return _api().encode(payload, session_key(cfg), algorithm="HS256")


def issue_session(
    cfg: SsoConfig, *, loginid: str, name: str | None, dept: str | None, now: int
) -> tuple[str, SessionClaims]:
    """ADFS 로그인 뒤 우리 세션 토큰(HS256)을 만든다 — 새 `sid` · `auth_time = now`."""
    claims = SessionClaims(
        loginid=loginid,
        name=name,
        dept=dept,
        iat=now,
        exp=min(now + cfg.session_seconds, now + cfg.session_max_seconds),
        jti=secrets.token_urlsafe(16),
        sid=secrets.token_urlsafe(16),
        auth_time=now,
    )
    return _encode_session(cfg, claims), claims


def renew_session(
    cfg: SsoConfig, claims: SessionClaims, *, now: int, last_issued: int | None = None
) -> tuple[str, SessionClaims] | None:
    """검증된 세션을 다시 서명한다. 늘릴 것이 없으면 `None`.

    직전 발급(`iat` 와 `last_issued` — 갱신 표에 적힌 그 sid 의 마지막 발급 — 가운데 늦은 것)이
    `RENEW_MIN_INTERVAL` 안이거나, 상한(`auth_time + 최대`)에 닿아 새 끝이 지금 끝보다 늦지 않으면
    `None`. `last_issued` 를 보는 까닭 — 60초 넘은 같은 옛 쿠키를 되풀이해 보내면 그 토큰의 `iat`
    만으로는 요청마다 다시 서명한다. 부르는 쪽은 `verify_session`(엄격)과 폐기 확인을 먼저 마친다.
    """
    issued = claims.iat if last_issued is None else max(claims.iat, last_issued)
    if now - issued < RENEW_MIN_INTERVAL:
        return None
    new_exp = min(now + cfg.session_seconds, claims.auth_time + cfg.session_max_seconds)
    if new_exp <= claims_end(claims, cfg):
        return None
    fresh = SessionClaims(
        loginid=claims.loginid,
        name=claims.name,
        dept=claims.dept,
        iat=now,
        exp=new_exp,
        jti=secrets.token_urlsafe(16),
        sid=claims.sid,
        auth_time=claims.auth_time,
    )
    return _encode_session(cfg, fresh), fresh


def _int_claim(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def decode_session(token: str, cfg: SsoConfig, *, now: int) -> SessionClaims:
    """세션 쿠키 값 → 클레임. 서명 · aud · iss · 꼴만 본다 — **끝 시각은 보지 않는다**.

    로그아웃이 막 끝난 쿠키의 sid 도 폐기하려고 쓴다. 새 요청은 `verify_session` 을 쓴다. 실패는
    모두 `session_invalid`.
    """
    import jwt

    if not token or len(token) > 4096:
        raise SsoReject("session_invalid")
    options: Options = {
        "require": ["exp", "iat", "sub", "jti", "sid", "auth_time"],
        "strict_aud": True,
        "verify_exp": False,
        "verify_iat": False,
    }
    try:
        claims = _api().decode(
            token,
            key=session_key(cfg),
            algorithms=["HS256"],
            audience=SESSION_AUDIENCE,
            issuer=ISSUER,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise SsoReject("session_invalid") from exc
    sub, jti, sid = claims.get("sub"), claims.get("jti"), claims.get("sid")
    iat = _int_claim(claims.get("iat"))
    exp = _int_claim(claims.get("exp"))
    auth_time = _int_claim(claims.get("auth_time"))
    if (
        not isinstance(sub, str)
        or not LOGINID_PATTERN.match(sub)
        or not isinstance(jti, str)
        or not _JTI.match(jti)
        or not isinstance(sid, str)
        or not _SID.match(sid)
        or iat is None
        or exp is None
        or auth_time is None
        or claims.get("v") != SESSION_VERSION
        or iat > now + SESSION_LEEWAY
        or auth_time > iat
    ):
        raise SsoReject("session_invalid")
    name, dept = claims.get("name"), claims.get("dept")
    return SessionClaims(
        loginid=sub,
        name=_display_claim(name) if name is not None else None,
        dept=_display_claim(dept) if dept is not None else None,
        iat=iat,
        exp=exp,
        jti=jti,
        sid=sid,
        auth_time=auth_time,
    )


def verify_session(token: str, cfg: SsoConfig, *, now: int) -> SessionClaims:
    """세션 쿠키 값 → 신원(새 요청용 — 엄격). 그 토큰 자신의 끝 + 여유가 지났으면 `session_expired`,
    그 밖 모든 실패는 `session_invalid`."""
    claims = decode_session(token, cfg, now=now)
    if now > claims_end(claims, cfg) + SESSION_LEEWAY:
        raise SsoReject("session_expired")
    return claims


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
