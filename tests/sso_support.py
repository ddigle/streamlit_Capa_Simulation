# Purpose: 통합인증 시험 도우미 — 실행 때 만든 키·인증서로 환경변수·id_token·갱신 세션을 짓는다.

"""통합인증 시험 재료.

키 · 인증서는 **실행 때** 만든다(세션당 한 번, `functools.cache`). 저장소에 키 파일을 두지 않는다 —
공개 저장소이고, 감시 시험(`test_public_repo_hygiene.py`)이 개인키 표지 · 키 파일 확장자를 막는다.
비밀값도 실행 때 무작위로 만든다. 호스트는 모두 `*.example.invalid`(문서용 예약 도메인)다.
"""

from __future__ import annotations

import base64
import datetime as dt
import functools
import html
import re
import secrets
import shlex
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import SsoConfig, x5t_of
from capa_simulation.auth.tokens import SessionClaims, issue_session, renew_session

CLIENT_ID = "capa-test-client"
ISSUER = "https://idp.example.invalid/adfs"
AUTHORIZE_URL = "https://idp.example.invalid/adfs/oauth2/authorize/"
PUBLIC_URL = "https://capa.example.invalid"
LOGINID = "dev.user"
# 같은 탭이 다른 계정으로 이어지는 시험의 계정 — 명단 안이어야 「계정 바뀜」 까지 간다.
OTHER_LOGINID = "other.user"


@dataclass(frozen=True)
class SigningMaterial:
    """시험용 서명 재료 — 개인키는 메모리에만."""

    private_key: rsa.RSAPrivateKey
    der: bytes

    @property
    def der_b64(self) -> str:
        return base64.b64encode(self.der).decode("ascii")

    @property
    def pem(self) -> str:
        cert = x509.load_der_x509_certificate(self.der)
        return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    @property
    def x5t(self) -> str:
        return x5t_of(self.der)

    @property
    def public_pem(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )


def _certificate(key: Any, *, valid_days: int, start_days_ago: int = 1) -> bytes:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "token-signing.example.invalid")])
    now = dt.datetime.now(dt.timezone.utc)
    not_before = now - dt.timedelta(days=start_days_ago)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(now + dt.timedelta(days=valid_days))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


def _material(bits: int, *, valid_days: int = 365, start_days_ago: int = 1) -> SigningMaterial:
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    der = _certificate(key, valid_days=valid_days, start_days_ago=start_days_ago)
    return SigningMaterial(private_key=key, der=der)


@functools.cache
def signing() -> SigningMaterial:
    return _material(2048)


@functools.cache
def other_signing() -> SigningMaterial:
    return _material(2048)


@functools.cache
def third_signing() -> SigningMaterial:
    return _material(2048)


@functools.cache
def weak_signing() -> SigningMaterial:
    return _material(1024)


@functools.cache
def expired_signing() -> SigningMaterial:
    return _material(2048, valid_days=-1, start_days_ago=30)


@functools.cache
def expiring_signing() -> SigningMaterial:
    return _material(2048, valid_days=10)


@functools.cache
def ec_certificate_b64() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return base64.b64encode(_certificate(key, valid_days=30)).decode("ascii")


@functools.cache
def sso_secret() -> str:
    """세션당 한 번 만든 무작위 비밀값(48바이트 urlsafe)."""
    return secrets.token_urlsafe(48)


def sso_environ(
    overrides: Mapping[str, str] | None = None, *, drop: Iterable[str] = ()
) -> dict[str, str]:
    """켜짐이 되는 운영(`APP_ENV=prod`) 환경변수 한 벌. `overrides` 로 바꾸고 `drop` 으로 뺀다."""
    environ = {
        names.ENV_CLIENT_ID: CLIENT_ID,
        names.ENV_SECRET: sso_secret(),
        names.ENV_APP_ENV: "prod",
        names.ENV_AUTHORIZE_URL: AUTHORIZE_URL,
        names.ENV_ISSUER: ISSUER,
        names.ENV_SIGNING_CERT: signing().der_b64,
        names.ENV_PUBLIC_URL: PUBLIC_URL,
        names.ENV_ACCESS_ADMINS: LOGINID,
        names.ENV_ACCESS_USERS: OTHER_LOGINID,
    }
    environ.update(overrides or {})
    for name in drop:
        environ.pop(name, None)
    return environ


def use_config(
    overrides: Mapping[str, str] | None = None, *, drop: Iterable[str] = ()
) -> SsoConfig:
    """프로세스 상태를 비우고 이 환경으로 기동한 것처럼 만든다(비밀값은 넘긴 사전에서만 빠진다)."""
    runtime.reset()
    return runtime.start(sso_environ(overrides, drop=drop))


def id_token_claims(nonce: str, *, now: int | None = None, **extra: Any) -> dict[str, Any]:
    moment = int(time.time()) if now is None else now
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "iat": moment,
        "nbf": moment,
        "exp": moment + 3600,
        "nonce": nonce,
        "sub": "subject-0001",
        "loginid": LOGINID,
        "username": "개발 사용자",
        "deptname": "개발부서",
    }
    claims.update(extra)
    return claims


def make_id_token(
    claims: Mapping[str, Any],
    *,
    material: SigningMaterial | None = None,
    drop: Iterable[str] = (),
    headers: Mapping[str, Any] | None = None,
) -> str:
    """RS256 id_token. 헤더 `x5t` · `kid` 는 인증서 지문(ADFS 꼴)."""
    signer = material or signing()
    payload = {key: value for key, value in claims.items() if key not in set(drop)}
    header: dict[str, Any] = {"x5t": signer.x5t, "kid": signer.x5t}
    header.update(headers or {})
    return jwt.encode(payload, signer.private_key, algorithm="RS256", headers=header)


def tamper_signature(token: str) -> str:
    """서명의 한 글자를 바꾼다(base64url 디코딩은 여전히 된다)."""
    head, payload, signature = token.split(".")
    middle = len(signature) // 2
    swapped = "A" if signature[middle] != "A" else "B"
    return f"{head}.{payload}.{signature[:middle]}{swapped}{signature[middle + 1 :]}"


def environ_from_lines(lines: Iterable[str]) -> dict[str, str]:
    """가짜 IdP 가 쓴 `export NAME='값'` 줄 → 환경 사전."""
    environ: dict[str, str] = {}
    for line in lines:
        assert line.startswith("export "), line
        name, _, quoted = line[len("export ") :].partition("=")
        (value,) = shlex.split(quoted)
        environ[name] = value
    return environ


def hidden_field(page: str, name: str) -> str:
    """자동 제출 폼의 숨은 칸 값."""
    match = re.search(rf'name="{re.escape(name)}" value="([^"]*)"', page)
    assert match is not None, name
    return html.unescape(match.group(1))


def renewed_session(
    cfg: SsoConfig,
    *,
    login_at: int,
    renew_at: Sequence[int],
    loginid: str = LOGINID,
    name: str | None = None,
    dept: str | None = None,
) -> tuple[str, SessionClaims]:
    """`login_at` 에 발급하고 `renew_at` 시각마다 차례로 갱신한 마지막 토큰 · 클레임.

    갱신이 `None`(60초 안 · 상한)이면 시험 차림이 틀린 것이라 단언으로 멈춘다.
    """
    token, claims = issue_session(cfg, loginid=loginid, name=name, dept=dept, now=login_at)
    for moment in renew_at:
        renewed = renew_session(cfg, claims, now=moment)
        assert renewed is not None, moment
        token, claims = renewed
    return token, claims


def refresh_headers(cfg: SsoConfig, token: str | None, **overrides: str | None) -> dict[str, str]:
    """갱신 경로(`POST /auth/sso/refresh`)에 브라우저가 싣는 머리 한 벌.

    세션 쿠키(`token` 이 None 이면 없음) · Origin(공개 주소) · `Sec-Fetch-Site: same-origin` ·
    `Sec-Fetch-Mode: cors` · 갱신 머리. `overrides` 의 이름은 밑줄을 줄표로 바꿔 머리 이름이 되고
    (`sec_fetch_site` → `sec-fetch-site`), 값을 None 으로 주면 그 머리를 뺀다.
    """
    headers: dict[str, str] = {
        "origin": PUBLIC_URL,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        names.REFRESH_HEADER.lower(): names.REFRESH_HEADER_VALUE,
    }
    if token is not None:
        headers["cookie"] = f"{cfg.session_cookie}={token}"
    for key, value in overrides.items():
        name = key.replace("_", "-").lower()
        if value is None:
            headers.pop(name, None)
        else:
            headers[name] = value
    return headers
