# Purpose: 개발·시험용 가짜 IdP — 실행 때 만든 키로 id_token 을 form_post 로 보낸다.

"""가짜 IdP(개발 · 사내 WebIDE 시험 전용).

실제 ADFS 없이 로그인 흐름(로그인 시작 → authorize → form_post 콜백 → 세션 쿠키)을 끝까지 돌려 본다.

    python scripts/sso_mock_idp.py --port 8591 \
        --app-url http://localhost:8581 --env-out ~/sso-dev.env

창 하나에서 이것을 띄우고, 다른 창에서 `set -a; . ~/sso-dev.env; set +a` 뒤
`python -m streamlit run capa_server.py --server.port 8581` 로 앱을 띄운다.

- **거절**: `APP_ENV` 가 운영으로 풀리면(`prod` · `production` · 모르는 값), `--host` 가 루프백이
  아니면, `--env-out` 이 git 작업 트리 안이면(개발용 비밀값이 든다) 종료 코드 2.
- 서명 키(RSA 2048)와 자체서명 인증서(CN `mock-idp.example.invalid`, 1일)는 **메모리에만** 만든다.
  개인키는 파일 · 출력 어디에도 없다.
- `GET /oauth2/authorize` 는 `client_id` · `response_type=id_token` · `response_mode=form_post` ·
  `redirect_uri` (= `--app-url` + `/auth/callback`) · `nonce` · `state` 를 보고, 맞으면 자동 제출
  폼으로 콜백에 보낸다.
- 실패를 흉내 내는 선택: `--aud`(다른 aud) · `--omit-claim`(클레임 빼기) · `--error`(IdP 오류) ·
  `--submit-delay-ms`(제출 늦추기 — state 만료 · 다른 탭 시험).
- `--app-url` 이 루프백이 아니면(WebIDE 프록시) 앱의 접속 명단이 켜지므로 env 파일에
  `--loginid` 를 관리자 목록으로 적는다. 루프백이면 적지 않아 명단이 꺼진 채로 돈다.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import os
import secrets
import shlex
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.auth import names  # noqa: E402
from capa_simulation.auth.config import app_env_is_production, is_loopback_host  # noqa: E402

AUTHORIZE_PATH = "/oauth2/authorize"
DEFAULT_CLIENT_ID = "capa-dev-client"
DEFAULT_ISSUER = "https://idp.example.invalid/adfs"
REFUSED = 2


@dataclass(frozen=True)
class MockOptions:
    port: int
    app_url: str
    env_out: Path | None = None
    host: str = "127.0.0.1"
    public_url: str = ""
    client_id: str = DEFAULT_CLIENT_ID
    issuer: str = DEFAULT_ISSUER
    loginid: str = "dev.user"
    username: str = "개발사용자"
    deptname: str = "개발부서"
    aud: str = ""
    omit_claims: tuple[str, ...] = ()
    error: str = ""
    lifetime: int = 3600
    submit_delay_ms: int = 0
    tls_cert: Path | None = None
    tls_key: Path | None = None

    @property
    def scheme(self) -> str:
        return "https" if self.tls_cert else "http"

    @property
    def idp_url(self) -> str:
        """브라우저가 여는 IdP 바탕 주소."""
        if self.public_url:
            return self.public_url.rstrip("/")
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}:{self.port}"

    @property
    def authorize_url(self) -> str:
        return f"{self.idp_url}{AUTHORIZE_PATH}"

    @property
    def redirect_uri(self) -> str:
        return f"{self.app_url.rstrip('/')}{names.CALLBACK_PATH}"


@dataclass(frozen=True)
class SigningIdentity:
    """메모리에만 있는 서명 키와 그 인증서."""

    private_key: Any
    certificate_der: bytes
    x5t: str

    @property
    def certificate_b64(self) -> str:
        return base64.b64encode(self.certificate_der).decode("ascii")


def make_signing_identity() -> SigningIdentity:
    """RSA 2048 키와 자체서명 인증서(CN `mock-idp.example.invalid`, 1일)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mock-idp.example.invalid")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    der = cert.public_bytes(serialization.Encoding.DER)
    digest = hashlib.sha1(der, usedforsecurity=False).digest()
    x5t = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return SigningIdentity(private_key=key, certificate_der=der, x5t=x5t)


def id_token_claims(options: MockOptions, *, nonce: str, now: int) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "iss": options.issuer,
        "aud": options.aud or options.client_id,
        "iat": now,
        "nbf": now,
        "exp": now + options.lifetime,
        "nonce": nonce,
        "sub": f"mock-{options.loginid}",
        "loginid": options.loginid,
        "username": options.username,
        "deptname": options.deptname,
    }
    for claim in options.omit_claims:
        claims.pop(claim, None)
    return claims


def issue_id_token(
    identity: SigningIdentity, options: MockOptions, *, nonce: str, now: int | None = None
) -> str:
    """ADFS 꼴 RS256 id_token — 헤더 `kid` = `x5t` = 인증서 SHA-1 지문."""
    import jwt

    moment = int(time.time()) if now is None else now
    claims = id_token_claims(options, nonce=nonce, now=moment)
    headers = {"x5t": identity.x5t, "kid": identity.x5t}
    return jwt.encode(claims, identity.private_key, algorithm="RS256", headers=headers)


def _page(title: str, body: str, *, script: str = "") -> str:
    return (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:40px;}"
        "td,th{border-bottom:1px solid #ccc;padding:4px 8px;text-align:left;}</style>"
        f"</head><body><h1>{html.escape(title)}</h1>{body}{script}</body></html>"
    )


def form_post_page(
    redirect_uri: str,
    fields: Mapping[str, str],
    *,
    claims: Mapping[str, Any] | None = None,
    delay_ms: int = 0,
) -> str:
    """콜백으로 자동 제출하는 폼(form_post). 값은 모두 이스케이프한다."""
    inputs = "".join(
        f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value)}">'
        for key, value in fields.items()
    )
    rows = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in (claims or {}).items()
    )
    table = f"<table>{rows}</table>" if rows else ""
    body = (
        f'<form method="post" action="{html.escape(redirect_uri)}">{inputs}'
        f'<button type="submit">로그인</button></form>{table}'
    )
    script = (
        "<script>setTimeout(function(){document.forms[0].submit();},"
        f"{max(0, int(delay_ms))});</script>"
    )
    return _page("가짜 IdP — 로그인", body, script=script)


def build_app(options: MockOptions, identity: SigningIdentity) -> Starlette:
    """`GET /oauth2/authorize` 하나뿐인 Starlette 앱."""

    async def authorize(request: Request) -> HTMLResponse:
        query = request.query_params
        problems: list[str] = []
        if query.get("client_id") != options.client_id:
            problems.append("client_id")
        if query.get("response_type") != "id_token":
            problems.append("response_type")
        if query.get("response_mode") != "form_post":
            problems.append("response_mode")
        if query.get("redirect_uri") != options.redirect_uri:
            problems.append("redirect_uri")
        for required in ("nonce", "state"):
            if not query.get(required):
                problems.append(required)
        if problems:
            items = "".join(f"<li>{html.escape(name)}</li>" for name in problems)
            body = f"<p>요청 값이 맞지 않습니다(이름만):</p><ul>{items}</ul>"
            return HTMLResponse(_page("가짜 IdP — 잘못된 요청", body), status_code=400)
        state = query["state"]
        if options.error:
            fields = {
                "error": options.error,
                "error_description": "mock idp refused the request",
                "state": state,
            }
            page = form_post_page(options.redirect_uri, fields, delay_ms=options.submit_delay_ms)
            return HTMLResponse(page)
        now = int(time.time())
        token = issue_id_token(identity, options, nonce=query["nonce"], now=now)
        claims = id_token_claims(options, nonce="(요청의 nonce)", now=now)
        page = form_post_page(
            options.redirect_uri,
            {"id_token": token, "state": state},
            claims=claims,
            delay_ms=options.submit_delay_ms,
        )
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    return Starlette(routes=[Route(AUTHORIZE_PATH, authorize, methods=["GET"])])


def env_lines(options: MockOptions, identity: SigningIdentity, secret: str) -> list[str]:
    """앱 창이 `set -a; . <파일>; set +a` 로 읽을 줄들."""
    values = {
        names.ENV_CLIENT_ID: options.client_id,
        names.ENV_AUTHORIZE_URL: options.authorize_url,
        names.ENV_ISSUER: options.issuer,
        names.ENV_SIGNING_CERT: identity.certificate_b64,
        names.ENV_PUBLIC_URL: options.app_url.rstrip("/"),
        names.ENV_SECRET: secret,
        names.ENV_APP_ENV: "dev",
    }
    if not is_loopback_host(urlsplit(options.app_url).hostname):
        values[names.ENV_ACCESS_ADMINS] = options.loginid
    return [f"export {name}={shlex.quote(value)}" for name, value in values.items()]


def inside_git_work_tree(path: Path) -> bool:
    for parent in [path.parent, *path.parent.parents]:
        if (parent / ".git").exists():
            return True
    return False


def refusal(options: MockOptions, environ: Mapping[str, str]) -> str | None:
    """돌지 않을 까닭(사람 말) 또는 None."""
    if app_env_is_production(environ.get(names.ENV_APP_ENV)):
        return "가짜 IdP 는 운영(APP_ENV=prod)에서 돌지 않습니다."
    if not is_loopback_host(options.host):
        return "가짜 IdP 는 루프백(127.0.0.1 · localhost · ::1)에서만 엽니다."
    if options.env_out is not None and inside_git_work_tree(options.env_out.expanduser().resolve()):
        return "--env-out 은 git 작업 트리 밖이어야 합니다(개발용 비밀값이 든다)."
    if options.tls_cert is not None and options.tls_key is None:
        return "--tls-cert 와 --tls-key 를 함께 줍니다."
    app_scheme = urlsplit(options.app_url).scheme
    if app_scheme not in ("http", "https"):
        return "--app-url 은 http(s):// 로 시작합니다."
    return None


def parse_options(argv: Sequence[str] | None = None) -> MockOptions:
    parser = argparse.ArgumentParser(description="개발 · 시험용 가짜 IdP(form_post)")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--app-url", required=True, help="앱의 CAPA_PUBLIC_URL")
    parser.add_argument("--env-out", type=Path, help="앱 창이 읽을 환경변수 파일(저장소 밖)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--public-url", default="", help="브라우저가 여는 IdP 주소")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--issuer", default=DEFAULT_ISSUER)
    parser.add_argument("--loginid", default="dev.user")
    parser.add_argument("--username", default="개발사용자")
    parser.add_argument("--deptname", default="개발부서")
    parser.add_argument("--aud", default="", help="다른 aud 를 실어 aud_mismatch 를 흉내")
    parser.add_argument("--omit-claim", action="append", default=[], help="뺄 클레임(여러 번)")
    parser.add_argument("--error", default="", help="IdP 오류 코드를 보냄(예: access_denied)")
    parser.add_argument("--lifetime", type=int, default=3600)
    parser.add_argument("--submit-delay-ms", type=int, default=0)
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    args = parser.parse_args(argv)
    return MockOptions(
        port=args.port,
        app_url=args.app_url,
        env_out=args.env_out,
        host=args.host,
        public_url=args.public_url,
        client_id=args.client_id,
        issuer=args.issuer,
        loginid=args.loginid,
        username=args.username,
        deptname=args.deptname,
        aud=args.aud,
        omit_claims=tuple(args.omit_claim),
        error=args.error,
        lifetime=args.lifetime,
        submit_delay_ms=args.submit_delay_ms,
        tls_cert=args.tls_cert,
        tls_key=args.tls_key,
    )


def write_env_file(path: Path, lines: Sequence[str]) -> None:
    """0600 으로 쓴다 — 개발용이라도 비밀값이 든다."""
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(target, 0o600)


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    options = parse_options(argv)
    reason = refusal(options, os.environ if environ is None else environ)
    if reason is not None:
        print(reason, file=sys.stderr)
        return REFUSED
    identity = make_signing_identity()
    target = "(쓰지 않음)"
    if options.env_out is not None:
        write_env_file(options.env_out, env_lines(options, identity, secrets.token_urlsafe(48)))
        target = str(options.env_out.expanduser())
    print(f"가짜 IdP — {options.idp_url} · client {options.client_id} · 환경변수 → {target}")
    import uvicorn

    uvicorn.run(
        build_app(options, identity),
        host=options.host,
        port=options.port,
        log_level="warning",
        ssl_certfile=str(options.tls_cert) if options.tls_cert else None,
        ssl_keyfile=str(options.tls_key) if options.tls_key else None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
