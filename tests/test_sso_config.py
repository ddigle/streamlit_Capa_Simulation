# Purpose: 통합인증 환경변수 → 모드·문제·쿠키 이름 판정과 기동 때 비밀값 빼기를 검증한다.

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sso_support import (
    PUBLIC_URL,
    ec_certificate_b64,
    expired_signing,
    expiring_signing,
    other_signing,
    signing,
    sso_environ,
    sso_secret,
    third_signing,
    weak_signing,
)

from capa_simulation.auth import names, runtime
from capa_simulation.auth.config import (
    SsoMode,
    SsoProblem,
    app_env_is_production,
    load_config,
    url_origin,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def codes(problems: Iterable[SsoProblem]) -> set[str]:
    return {item.log_text() for item in problems}


def test_empty_environment_is_off_with_readiness_listing_what_turning_on_needs() -> None:
    cfg = load_config({})

    assert cfg.mode is SsoMode.OFF
    assert cfg.problems == ()
    assert not cfg.prod
    assert {
        "JWT_SECRET_KEY:missing",
        "ADFS_AUTHORIZE_URL:missing",
        "ADFS_ISSUER:missing",
        "ADFS_SIGNING_CERT:missing",
        "CAPA_PUBLIC_URL:missing",
    } <= codes(cfg.readiness)
    assert cfg.notices == ()


def test_full_environment_is_on() -> None:
    cfg = load_config(sso_environ())

    assert cfg.mode is SsoMode.ON, cfg.problems
    assert cfg.enabled
    assert cfg.prod
    assert cfg.redirect_uri == f"{PUBLIC_URL}/auth/callback"
    assert cfg.session_hours == 12
    assert cfg.scope == "openid"
    assert (cfg.claim_loginid, cfg.claim_username, cfg.claim_deptname) == (
        "loginid",
        "username",
        "deptname",
    )
    assert [cert.x5t for cert in cfg.signing_certs] == [signing().x5t]


def test_client_id_without_the_rest_is_broken_and_names_each_missing_value() -> None:
    cfg = load_config({names.ENV_CLIENT_ID: "capa-test-client"})

    assert cfg.mode is SsoMode.BROKEN
    assert {
        "JWT_SECRET_KEY:missing",
        "ADFS_AUTHORIZE_URL:missing",
        "ADFS_ISSUER:missing",
        "ADFS_SIGNING_CERT:missing",
        "CAPA_PUBLIC_URL:missing",
    } <= codes(cfg.problems)
    assert cfg.readiness == ()


def test_one_missing_value_breaks_an_otherwise_full_setup() -> None:
    cfg = load_config(sso_environ(drop=[names.ENV_ISSUER]))

    assert cfg.mode is SsoMode.BROKEN
    assert codes(cfg.problems) == {"ADFS_ISSUER:missing"}
    # 짐작하지 않는다 — 후보만 보인다.
    assert cfg.issuer == ""
    assert cfg.issuer_candidate == "https://idp.example.invalid/adfs"


@pytest.mark.parametrize(
    ("flag", "client_id", "mode"),
    [
        ("", "", SsoMode.OFF),
        ("auto", "", SsoMode.OFF),
        ("AUTO", "", SsoMode.OFF),
        ("required", "", SsoMode.BROKEN),
        ("required", "capa-test-client", SsoMode.ON),
        ("off", "", SsoMode.BROKEN),
        ("yes", "capa-test-client", SsoMode.BROKEN),
    ],
)
def test_capa_sso_flag_values(flag: str, client_id: str, mode: SsoMode) -> None:
    environ = sso_environ({names.ENV_SSO: flag, names.ENV_CLIENT_ID: client_id})

    cfg = load_config(environ)

    assert cfg.mode is mode, cfg.problems
    assert cfg.locked == (flag == "required")


def test_required_lock_reports_the_missing_client_id() -> None:
    cfg = load_config(sso_environ({names.ENV_SSO: "required"}, drop=[names.ENV_CLIENT_ID]))

    assert "ADFS_CLIENT_ID:missing" in codes(cfg.problems)


def test_unknown_flag_is_named() -> None:
    cfg = load_config({names.ENV_SSO: "off"})

    assert codes(cfg.problems) >= {"CAPA_SSO:unknown_value"}


@pytest.mark.parametrize(
    ("value", "prod"),
    [
        ("", False),
        ("dev", False),
        ("local", False),
        ("TEST", False),
        ("prod", True),
        ("production", True),
        ("staging", True),
    ],
)
def test_app_env_reading(value: str, prod: bool) -> None:
    assert app_env_is_production(value) is prod
    assert load_config({names.ENV_APP_ENV: value}).prod is prod


def test_unknown_app_env_is_treated_as_production_with_a_notice() -> None:
    cfg = load_config({names.ENV_APP_ENV: "staging"})

    assert cfg.prod
    assert "APP_ENV:unknown_app_env" in codes(cfg.notices)


def test_production_with_sso_off_gets_a_notice() -> None:
    cfg = load_config({names.ENV_APP_ENV: "prod"})

    assert cfg.mode is SsoMode.OFF
    assert "ADFS_CLIENT_ID:off_in_production" in codes(cfg.notices)


@pytest.mark.parametrize(
    ("name", "value", "code"),
    [
        (names.ENV_PUBLIC_URL, "http://capa.example.invalid", "not_https"),
        (names.ENV_AUTHORIZE_URL, "http://idp.example.invalid/adfs/oauth2/authorize/", "not_https"),
        (names.ENV_ISSUER, "http://idp.example.invalid/adfs", "not_https"),
        (names.ENV_PUBLIC_URL, "https://user:pw@capa.example.invalid", "has_userinfo"),
        (names.ENV_PUBLIC_URL, "https://capa.example.invalid/#top", "has_fragment"),
        (names.ENV_PUBLIC_URL, "https://capa.example.invalid/?a=1", "has_query"),
        (names.ENV_ISSUER, "https://idp.example.invalid/adfs?x=1", "has_query"),
        (names.ENV_PUBLIC_URL, "capa.example.invalid", "bad_url"),
        (names.ENV_PUBLIC_URL, "ftp://capa.example.invalid", "bad_url"),
        (names.ENV_PUBLIC_URL, "https://capa.example.invalid:99999", "bad_url"),
        (names.ENV_PUBLIC_URL, "https://capa example.invalid", "bad_url"),
        (names.ENV_LOGOUT_URL, "http://idp.example.invalid/adfs/oauth2/logout", "not_https"),
    ],
)
def test_url_rules_in_production(name: str, value: str, code: str) -> None:
    cfg = load_config(sso_environ({name: value}))

    assert cfg.mode is SsoMode.BROKEN
    assert f"{name}:{code}" in codes(cfg.problems)


def test_development_takes_http_only_on_loopback() -> None:
    loopback = load_config(
        sso_environ({names.ENV_APP_ENV: "dev", names.ENV_PUBLIC_URL: "http://localhost:8581"})
    )
    remote = load_config(
        sso_environ(
            {names.ENV_APP_ENV: "dev", names.ENV_PUBLIC_URL: "http://capa.example.invalid:8581"}
        )
    )
    ipv6 = load_config(
        sso_environ({names.ENV_APP_ENV: "dev", names.ENV_PUBLIC_URL: "http://[::1]:8581"})
    )

    assert loopback.mode is SsoMode.ON
    assert not loopback.secure_cookies
    assert loopback.session_cookie == "capa_session"
    assert remote.mode is SsoMode.BROKEN
    assert "CAPA_PUBLIC_URL:http_not_loopback" in codes(remote.problems)
    assert ipv6.mode is SsoMode.ON


def test_authorize_url_may_carry_a_query() -> None:
    cfg = load_config(
        sso_environ(
            {names.ENV_AUTHORIZE_URL: "https://idp.example.invalid/adfs/oauth2/authorize?x=1"}
        )
    )

    assert cfg.mode is SsoMode.ON


def test_public_url_path_prefix_is_kept_and_suffixes_cookie_names() -> None:
    cfg = load_config(
        sso_environ({names.ENV_PUBLIC_URL: "https://capa.example.invalid/proxy/8581/"})
    )

    assert cfg.mode is SsoMode.ON
    assert cfg.public_url == "https://capa.example.invalid/proxy/8581"
    assert cfg.redirect_uri == "https://capa.example.invalid/proxy/8581/auth/callback"
    assert cfg.cookie_suffix.startswith("_") and len(cfg.cookie_suffix) == 9
    assert cfg.session_cookie == f"__Host-capa_session{cfg.cookie_suffix}"
    assert cfg.public_origin == "https://capa.example.invalid"


def test_production_cookie_names_use_the_host_prefix() -> None:
    cfg = load_config(sso_environ())

    assert cfg.secure_cookies
    assert cfg.cookie_suffix == ""
    assert cfg.session_cookie == "__Host-capa_session"
    assert cfg.attempt_cookie == "__Host-capa_sso_attempt"
    assert (
        cfg.state_cookie("abcdefghijklmnopqrstuvwxyz") == "__Host-capa_sso_state_abcdefghijklmnop"
    )
    for name in (cfg.session_cookie, cfg.attempt_cookie, cfg.state_cookie_prefix):
        assert not name.startswith("_streamlit_")


def test_trailing_slash_is_dropped_from_the_public_url_only() -> None:
    cfg = load_config(
        sso_environ(
            {
                names.ENV_PUBLIC_URL: "https://capa.example.invalid/",
                names.ENV_ISSUER: "https://idp.example.invalid/adfs/",
            }
        )
    )

    assert cfg.public_url == "https://capa.example.invalid"
    # 이슈어는 토큰의 iss 와 정확히 맞춰야 하므로 끝 `/` 를 지킨다.
    assert cfg.issuer == "https://idp.example.invalid/adfs/"


def test_url_origin_drops_default_ports() -> None:
    assert url_origin("https://capa.example.invalid:443/x") == "https://capa.example.invalid"
    assert url_origin("https://Capa.Example.Invalid:8581") == "https://capa.example.invalid:8581"
    assert url_origin("http://localhost:80") == "http://localhost"
    assert url_origin("not a url") == ""


def test_signing_certificate_accepts_base64_der() -> None:
    cfg = load_config(sso_environ({names.ENV_SIGNING_CERT: signing().der_b64}))

    assert cfg.mode is SsoMode.ON
    assert cfg.signing_certs[0].x5t == signing().x5t
    assert cfg.signing_certs[0].key_bits == 2048
    assert len(cfg.signing_certs[0].sha256) == 64


def test_signing_certificate_accepts_base64_of_a_pem_file() -> None:
    import base64

    wrapped = base64.b64encode(signing().pem.encode("ascii")).decode("ascii")
    cfg = load_config(sso_environ({names.ENV_SIGNING_CERT: wrapped}))

    assert cfg.mode is SsoMode.ON
    assert cfg.signing_certs[0].x5t == signing().x5t


def test_signing_certificate_accepts_pem_text_even_on_one_line() -> None:
    multi = load_config(sso_environ({names.ENV_SIGNING_CERT: signing().pem}))
    one_line = load_config(
        sso_environ({names.ENV_SIGNING_CERT: signing().pem.replace("\n", "\\n")})
    )
    spaced = load_config(sso_environ({names.ENV_SIGNING_CERT: signing().pem.replace("\n", " ")}))

    for cfg in (multi, one_line, spaced):
        assert cfg.mode is SsoMode.ON, cfg.problems
        assert cfg.signing_certs[0].x5t == signing().x5t


def test_two_certificates_separated_by_a_comma() -> None:
    value = f"{signing().der_b64}, {other_signing().der_b64}"

    cfg = load_config(sso_environ({names.ENV_SIGNING_CERT: value}))

    assert [cert.x5t for cert in cfg.signing_certs] == [signing().x5t, other_signing().x5t]


def test_more_than_three_certificates_is_a_problem() -> None:
    value = ",".join(
        item.der_b64 for item in (signing(), other_signing(), third_signing(), signing())
    )

    cfg = load_config(sso_environ({names.ENV_SIGNING_CERT: value}))

    assert "ADFS_SIGNING_CERT:too_many" in codes(cfg.problems)


@pytest.mark.parametrize(
    ("value_factory", "code"),
    [
        (lambda: weak_signing().der_b64, "cert_too_small"),
        (lambda: "bm90IGEgY2VydGlmaWNhdGU=", "cert_unreadable"),
        (lambda: "%%%not-base64%%%", "cert_unreadable"),
        (ec_certificate_b64, "cert_not_rsa"),
    ],
)
def test_bad_signing_certificates(value_factory: Callable[[], str], code: str) -> None:
    value = value_factory()

    cfg = load_config(sso_environ({names.ENV_SIGNING_CERT: value}))

    assert cfg.mode is SsoMode.BROKEN
    assert f"ADFS_SIGNING_CERT:{code}" in codes(cfg.problems)


def test_expired_or_expiring_certificate_warns_but_does_not_block() -> None:
    expired = load_config(sso_environ({names.ENV_SIGNING_CERT: expired_signing().der_b64}))
    expiring = load_config(sso_environ({names.ENV_SIGNING_CERT: expiring_signing().der_b64}))

    assert expired.mode is SsoMode.ON
    assert "ADFS_SIGNING_CERT:cert_expired" in codes(expired.notices)
    assert expiring.mode is SsoMode.ON
    assert "ADFS_SIGNING_CERT:cert_expiring" in codes(expiring.notices)
    now = datetime.now(timezone.utc)
    assert 0 <= expiring.signing_certs[0].days_left(now) <= 10


@pytest.mark.parametrize(
    ("secret", "code"),
    [
        ("x" * 31, "too_short"),
        ("ab" * 20, "low_variety"),
        ("ChangeMe-0123456789-ABCDEFGHIJKLMN", "placeholder"),
        ("my-jwt-SECRET-0123456789abcdefghij", "placeholder"),
        ("0123456789abcdefghijk\x01lmnopqrstuvwxyz", "control_chars"),
    ],
)
def test_weak_secrets_block(secret: str, code: str) -> None:
    cfg = load_config(sso_environ({names.ENV_SECRET: secret}))

    assert cfg.mode is SsoMode.BROKEN
    assert codes(cfg.problems) == {f"JWT_SECRET_KEY:{code}"}


def test_secret_equal_to_the_client_id_blocks() -> None:
    same = "0123456789-abcdefghij-ABCDEFGHIJ-klmn"

    cfg = load_config(sso_environ({names.ENV_SECRET: same, names.ENV_CLIENT_ID: same}))

    assert "JWT_SECRET_KEY:same_as_client_id" in codes(cfg.problems)


def test_a_32_byte_varied_secret_is_enough() -> None:
    cfg = load_config(sso_environ({names.ENV_SECRET: "0123456789abcdefghijklmnopqrstuv"}))

    assert cfg.mode is SsoMode.ON


@pytest.mark.parametrize(
    ("value", "hours", "code"),
    [
        ("", 12, None),
        ("1", 1, None),
        ("24", 24, None),
        ("0", 12, "out_of_range"),
        ("25", 12, "out_of_range"),
        ("-3", 12, "not_integer"),
        ("twelve", 12, "not_integer"),
        ("1.5", 12, "not_integer"),
    ],
)
def test_session_hours(value: str, hours: int, code: str | None) -> None:
    cfg = load_config(sso_environ({names.ENV_SESSION_HOURS: value}))

    assert cfg.session_hours == hours
    if code is None:
        assert cfg.mode is SsoMode.ON
        assert cfg.session_seconds == hours * 3600
    else:
        assert f"CAPA_SSO_SESSION_HOURS:{code}" in codes(cfg.problems)


def test_scope_must_keep_openid() -> None:
    good = load_config(sso_environ({names.ENV_SCOPE: "openid  allatclaims"}))
    bad = load_config(sso_environ({names.ENV_SCOPE: "profile"}))

    assert good.mode is SsoMode.ON
    assert good.scope == "openid allatclaims"
    assert "ADFS_SCOPE:no_openid" in codes(bad.problems)


def test_claim_names_can_be_renamed() -> None:
    cfg = load_config(
        sso_environ(
            {
                names.ENV_CLAIM_LOGINID: "upn",
                names.ENV_CLAIM_USERNAME: "display_name",
                names.ENV_CLAIM_DEPTNAME: "http://schemas.example.invalid/claims/department",
            }
        )
    )
    bad = load_config(sso_environ({names.ENV_CLAIM_LOGINID: "login id"}))

    assert cfg.mode is SsoMode.ON
    assert cfg.claim_loginid == "upn"
    assert cfg.claim_deptname == "http://schemas.example.invalid/claims/department"
    assert "ADFS_CLAIM_LOGINID:bad_claim_name" in codes(bad.problems)


def test_resource_and_logout_url_are_optional() -> None:
    cfg = load_config(
        sso_environ(
            {
                names.ENV_RESOURCE: "urn:example:capa",
                names.ENV_LOGOUT_URL: "https://idp.example.invalid/adfs/oauth2/logout",
            }
        )
    )

    assert cfg.mode is SsoMode.ON
    assert cfg.resource == "urn:example:capa"
    assert cfg.logout_url == "https://idp.example.invalid/adfs/oauth2/logout"


def test_readiness_previews_problems_while_off() -> None:
    environ = sso_environ({names.ENV_SECRET: "short"}, drop=[names.ENV_CLIENT_ID])

    cfg = load_config(environ)

    assert cfg.mode is SsoMode.OFF
    assert codes(cfg.readiness) == {"JWT_SECRET_KEY:too_short"}
    assert cfg.problems == ()


def test_env_presence_reports_names_only() -> None:
    cfg = load_config(sso_environ({names.ENV_SCOPE: "  "}))

    assert cfg.env_presence[names.ENV_CLIENT_ID] is True
    assert cfg.env_presence[names.ENV_SCOPE] is False
    assert set(cfg.env_presence) == set(names.SSO_ENVIRONMENT)


def test_repr_never_shows_the_secret() -> None:
    cfg = load_config(sso_environ())

    assert sso_secret() not in repr(cfg)
    assert sso_secret() not in str(cfg)
    assert cfg.secret == sso_secret().encode("utf-8")


def test_start_removes_the_secret_from_the_environment_and_reads_once() -> None:
    environ = sso_environ()

    cfg = runtime.start(environ)
    again = runtime.start(sso_environ({names.ENV_CLIENT_ID: "another-client"}))

    assert names.ENV_SECRET not in environ
    assert cfg.mode is SsoMode.ON
    assert again is cfg
    assert runtime.config() is cfg
    assert runtime.started()
    events = runtime.recent_events()
    assert events[0].event == "config"
    assert events[0].value("mode") == "on"
    assert sso_secret() not in repr(events)


def test_config_without_start_reads_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in sso_environ().items():
        monkeypatch.setenv(name, value)

    cfg = runtime.config()

    assert cfg.mode is SsoMode.ON
    # 시작 없이 읽을 때는 환경에서 빼지 않는다(개발 실행).
    assert os.environ.get(names.ENV_SECRET) == sso_secret()
    assert not runtime.started()


def test_broken_start_logs_problem_names_only() -> None:
    environ = sso_environ({names.ENV_SECRET: "short-but-secret-looking"})

    runtime.start(environ)

    event = runtime.recent_events()[0]
    assert event.value("mode") == "broken"
    assert event.value("problems") == "JWT_SECRET_KEY:too_short"


def test_off_mode_does_not_import_pyjwt() -> None:
    """꺼짐은 PyJWT 없이도 뜬다 — 진입 창구를 불러 설정을 읽어도 jwt 가 import 되지 않는다."""
    code = (
        "import sys\n"
        "from capa_simulation.auth import server, runtime\n"
        "cfg = runtime.config()\n"
        "assert cfg.mode.value == 'off', cfg\n"
        "assert 'jwt' not in sys.modules, 'jwt imported'\n"
        "print('ok')\n"
    )
    environ = {key: value for key, value in os.environ.items() if key not in names.SSO_ENVIRONMENT}
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=environ,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
