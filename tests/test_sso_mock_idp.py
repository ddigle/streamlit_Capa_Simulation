# Purpose: 가짜 IdP 의 거절 조건·낸 토큰의 검증·폼 이스케이프를 검증한다.

from __future__ import annotations

import secrets
import stat
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
from asgi_driver import http
from sso_support import environ_from_lines, hidden_field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from sso_mock_idp import (  # noqa: E402
    MockOptions,
    build_app,
    env_lines,
    form_post_page,
    issue_id_token,
    main,
    make_signing_identity,
    parse_options,
)

from capa_simulation.auth import names  # noqa: E402
from capa_simulation.auth.config import SsoMode, load_config  # noqa: E402
from capa_simulation.auth.tokens import SsoReject, verify_id_token  # noqa: E402

APP_URL = "https://app.example.test:8581"
# 개발용 비밀값도 실행 때 만든다(자리표 검사에 걸리는 글자를 쓰지 않는다).
DEV_SECRET = secrets.token_urlsafe(48)


def options(**changes: Any) -> MockOptions:
    return replace(MockOptions(port=8591, app_url=APP_URL), **changes)


def test_refuses_production(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["--port", "8591", "--app-url", APP_URL, "--env-out", str(tmp_path / "a.env")],
        environ={names.ENV_APP_ENV: "prod"},
    )

    assert code == 2
    assert "운영" in capsys.readouterr().err
    assert not (tmp_path / "a.env").exists()


@pytest.mark.parametrize("value", ["production", "staging"])
def test_refuses_any_production_like_app_env(value: str, tmp_path: Path) -> None:
    code = main(["--port", "8591", "--app-url", APP_URL], environ={names.ENV_APP_ENV: value})

    assert code == 2


def test_refuses_a_non_loopback_host() -> None:
    code = main(["--port", "8591", "--app-url", APP_URL, "--host", "0.0.0.0"], environ={})

    assert code == 2


def test_refuses_an_env_file_inside_the_work_tree(capsys: pytest.CaptureFixture[str]) -> None:
    target = PROJECT_ROOT / "data" / "temp" / "mock-idp-should-not-exist.env"

    code = main(["--port", "8591", "--app-url", APP_URL, "--env-out", str(target)], environ={})

    assert code == 2
    assert not target.exists()
    assert "git 작업 트리 밖" in capsys.readouterr().err


def test_env_lines_build_a_config_that_verifies_the_issued_token() -> None:
    identity = make_signing_identity()
    opts = options()
    environ = environ_from_lines(env_lines(opts, identity, DEV_SECRET))

    cfg = load_config(environ)
    token = issue_id_token(identity, opts, nonce="nonce-1")
    login = verify_id_token(token, cfg, expected_nonce="nonce-1", now=int(time.time()))

    assert cfg.mode is SsoMode.ON, cfg.problems
    assert not cfg.prod
    assert cfg.public_url == APP_URL
    assert cfg.authorize_url == "http://127.0.0.1:8591/oauth2/authorize"
    assert login.loginid == "dev.user" and login.name == "개발사용자" and login.dept == "개발부서"


def test_env_file_is_private(tmp_path: Path, keeps_permission_bits: bool) -> None:
    """비밀값이 든 env 파일은 0600 이다. 비트를 담지 못하는 파일 체계(Windows)에서는 쓰기만 본다."""
    from sso_mock_idp import write_env_file

    target = tmp_path / "dev.env"
    write_env_file(target, ["export A='1'"])

    assert target.read_text(encoding="utf-8").strip() == "export A='1'"
    if keeps_permission_bits:
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_public_url_and_tls_change_the_authorize_address() -> None:
    tls = options(tls_cert=Path("c.pem"), tls_key=Path("k.pem"))
    public = options(public_url="https://idp.other.test:8591/")

    assert tls.authorize_url == "https://127.0.0.1:8591/oauth2/authorize"
    assert public.authorize_url == "https://idp.other.test:8591/oauth2/authorize"


def test_aud_and_omitted_claims_are_reflected() -> None:
    identity = make_signing_identity()
    environ = environ_from_lines(env_lines(options(), identity, DEV_SECRET))
    cfg = load_config(environ)

    wrong_aud = issue_id_token(identity, options(aud="someone-else"), nonce="n")
    no_loginid = issue_id_token(identity, options(omit_claims=("loginid",)), nonce="n")

    with pytest.raises(SsoReject) as aud:
        verify_id_token(wrong_aud, cfg, expected_nonce="n", now=int(time.time()))
    with pytest.raises(SsoReject) as missing:
        verify_id_token(no_loginid, cfg, expected_nonce="n", now=int(time.time()))
    assert aud.value.code == "aud_mismatch"
    assert missing.value.code == "claim_missing:loginid"


def test_form_post_page_escapes_values() -> None:
    page = form_post_page(
        'https://app.example.test/auth/callback"><script>',
        {"id_token": "a<b>", "state": '"quoted"'},
        claims={"<k>": "<v>"},
        delay_ms=250,
    )

    assert "<script>setTimeout" in page
    assert "<b>" not in page and "&lt;b&gt;" in page
    assert "&quot;quoted&quot;" in page
    assert "&lt;k&gt;" in page and "&lt;v&gt;" in page
    assert '"><script>' not in page.split("<script>setTimeout")[0]
    assert "},250);" in page


def test_authorize_endpoint_answers_with_a_form_post() -> None:
    identity = make_signing_identity()
    opts = options()
    query = urlencode(
        {
            "client_id": opts.client_id,
            "response_type": "id_token",
            "response_mode": "form_post",
            "redirect_uri": f"{APP_URL}/auth/callback",
            "scope": "openid",
            "nonce": "nonce-xyz",
            "state": "state-xyz",
        }
    )

    response = http(build_app(opts, identity), "GET", f"/oauth2/authorize?{query}")

    assert response.status == 200
    assert f'action="{APP_URL}/auth/callback"' in response.text
    assert hidden_field(response.text, "state") == "state-xyz"
    token = hidden_field(response.text, "id_token")
    cfg = load_config(environ_from_lines(env_lines(opts, identity, DEV_SECRET)))
    assert verify_id_token(token, cfg, expected_nonce="nonce-xyz", now=int(time.time()))


def test_authorize_endpoint_rejects_a_wrong_redirect_uri_by_name_only() -> None:
    opts = options()
    query = urlencode(
        {
            "client_id": opts.client_id,
            "response_type": "id_token",
            "response_mode": "form_post",
            "redirect_uri": "https://app.example.test/auth/callback",
            "nonce": "n",
            "state": "s",
        }
    )

    response = http(build_app(opts, make_signing_identity()), "GET", f"/oauth2/authorize?{query}")

    assert response.status == 400
    assert "redirect_uri" in response.text
    assert "https://app.example.test/auth/callback" not in response.text


def test_error_option_posts_an_idp_error() -> None:
    opts = options(error="access_denied")
    query = urlencode(
        {
            "client_id": opts.client_id,
            "response_type": "id_token",
            "response_mode": "form_post",
            "redirect_uri": f"{APP_URL}/auth/callback",
            "nonce": "n",
            "state": "s",
        }
    )

    response = http(build_app(opts, make_signing_identity()), "GET", f"/oauth2/authorize?{query}")

    assert hidden_field(response.text, "error") == "access_denied"
    assert 'name="id_token"' not in response.text


def test_parse_options_reads_repeatable_omissions() -> None:
    parsed = parse_options(
        ["--port", "8592", "--app-url", APP_URL, "--omit-claim", "loginid", "--omit-claim", "x"]
    )

    assert parsed.omit_claims == ("loginid", "x")
    assert parsed.host == "127.0.0.1"
