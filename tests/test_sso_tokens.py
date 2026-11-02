# Purpose: ID 토큰(RS256) 거절 사유와 세션·상태 토큰(HS256) 발급·검증·바꿔 끼우기를 본다.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import jwt
import pytest
from sso_support import (
    CLIENT_ID,
    ISSUER,
    LOGINID,
    id_token_claims,
    make_id_token,
    other_signing,
    renewed_session,
    signing,
    sso_environ,
    tamper_signature,
    use_config,
    weak_signing,
)

from capa_simulation.auth import names
from capa_simulation.auth.config import SsoConfig, load_config
from capa_simulation.auth.tokens import (
    ISSUER as SESSION_ISSUER,
)
from capa_simulation.auth.tokens import (
    RENEW_MIN_INTERVAL,
    SESSION_AUDIENCE,
    SESSION_LEEWAY,
    STATE_AUDIENCE,
    SsoReject,
    decode_session,
    derive_key,
    issue_session,
    issue_state,
    pick_certs,
    renew_session,
    session_end,
    session_key,
    state_key,
    verify_id_token,
    verify_session,
    verify_state,
)

NONCE = "nonce-value-for-tests-0123456789"


@pytest.fixture
def cfg() -> SsoConfig:
    return use_config()


def reject_code(token: str, cfg: SsoConfig, *, nonce: str = NONCE, now: int | None = None) -> str:
    with pytest.raises(SsoReject) as caught:
        verify_id_token(token, cfg, expected_nonce=nonce, now=now or int(time.time()))
    return caught.value.code


def _unsigned(header: dict[str, object], payload: dict[str, object]) -> str:
    def part(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{part(header)}.{part(payload)}."


def test_a_good_token_yields_the_identity(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE))

    login = verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert login.loginid == LOGINID
    assert login.name == "개발 사용자"
    assert login.dept == "개발부서"
    assert "loginid" in login.claim_names and "nonce" in login.claim_names


def test_alg_none_is_refused(cfg: SsoConfig) -> None:
    token = _unsigned({"alg": "none", "typ": "JWT"}, id_token_claims(NONCE))

    assert reject_code(token, cfg) == "alg_not_allowed"


def test_hs256_header_is_refused(cfg: SsoConfig) -> None:
    token = jwt.encode(id_token_claims(NONCE), "x" * 64, algorithm="HS256")

    assert reject_code(token, cfg) == "alg_not_allowed"


def test_hs256_confusion_with_the_public_key_as_secret_is_refused(cfg: SsoConfig) -> None:
    """공개키 PEM 을 HMAC 비밀로 쓴 위조 — 헤더를 RS256 으로 속여도 서명이 맞지 않는다."""
    payload = id_token_claims(NONCE)
    header: dict[str, object] = {"alg": "RS256", "typ": "JWT", "x5t": signing().x5t}

    def part(value: dict[str, object]) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

    signing_input = part(header) + b"." + part(payload)
    forged = hmac.new(signing().public_pem, signing_input, hashlib.sha256).digest()
    token = (signing_input + b"." + base64.urlsafe_b64encode(forged).rstrip(b"=")).decode()

    assert reject_code(token, cfg) == "signature_invalid"
    honest_header = part({"alg": "HS256", "typ": "JWT"}) + b"." + part(payload)
    mac = hmac.new(signing().public_pem, honest_header, hashlib.sha256).digest()
    plain = (honest_header + b"." + base64.urlsafe_b64encode(mac).rstrip(b"=")).decode()
    assert reject_code(plain, cfg) == "alg_not_allowed"


def test_a_different_rsa_key_is_refused(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE), material=other_signing())

    assert reject_code(token, cfg) == "signing_key_unknown"


def test_a_different_key_claiming_our_thumbprint_is_a_bad_signature(cfg: SsoConfig) -> None:
    token = make_id_token(
        id_token_claims(NONCE),
        material=other_signing(),
        headers={"x5t": signing().x5t, "kid": signing().x5t},
    )

    assert reject_code(token, cfg) == "signature_invalid"


def test_a_tampered_signature_is_refused(cfg: SsoConfig) -> None:
    token = tamper_signature(make_id_token(id_token_claims(NONCE)))

    assert reject_code(token, cfg) == "signature_invalid"


def test_signature_failure_diagnostic_shows_thumbprints_not_claims(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE), material=other_signing())

    with pytest.raises(SsoReject) as caught:
        verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    diagnostic = caught.value.diagnostic
    assert diagnostic["token_x5t"] == other_signing().x5t
    assert diagnostic["configured_x5t"] == signing().x5t
    assert "got_iss" not in diagnostic and "got_aud" not in diagnostic
    assert caught.value.loginid is None


def test_audience_mismatch_reports_expected_and_received(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE, aud="someone-else"))

    with pytest.raises(SsoReject) as caught:
        verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert caught.value.code == "aud_mismatch"
    assert caught.value.diagnostic["expected_aud"] == CLIENT_ID
    assert caught.value.diagnostic["got_aud"] == "someone-else"
    assert caught.value.loginid == LOGINID


def test_audience_list_is_refused_even_if_it_contains_us(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE, aud=[CLIENT_ID, "other"]))

    assert reject_code(token, cfg) == "aud_mismatch"


def test_missing_audience_is_refused(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE), drop=["aud"])

    assert reject_code(token, cfg) == "aud_mismatch"


@pytest.mark.parametrize(
    "issuer",
    [
        "https://idp.example.invalid/adfs/",
        "https://IDP.example.invalid/adfs",
        "https://idp.example.invalid/adfs/extra",
        "https://idp.example.invalid/ad",
    ],
)
def test_issuer_must_match_exactly(cfg: SsoConfig, issuer: str) -> None:
    token = make_id_token(id_token_claims(NONCE, iss=issuer))

    with pytest.raises(SsoReject) as caught:
        verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert caught.value.code == "iss_mismatch"
    assert caught.value.diagnostic["expected_iss"] == ISSUER
    assert caught.value.diagnostic["got_iss"] == issuer


def test_expired_token_is_refused(cfg: SsoConfig) -> None:
    now = int(time.time())
    token = make_id_token(id_token_claims(NONCE, now=now - 7200, exp=now - 3600))

    with pytest.raises(SsoReject) as caught:
        verify_id_token(token, cfg, expected_nonce=NONCE, now=now)

    assert caught.value.code == "token_expired"
    assert "server_time" in caught.value.diagnostic and "exp" in caught.value.diagnostic


def test_expiry_inside_the_leeway_is_accepted(cfg: SsoConfig) -> None:
    now = int(time.time())
    token = make_id_token(id_token_claims(NONCE, now=now - 300, exp=now - 60))

    login = verify_id_token(token, cfg, expected_nonce=NONCE, now=now)

    assert login.loginid == LOGINID


def test_future_iat_beyond_the_leeway_is_refused(cfg: SsoConfig) -> None:
    now = int(time.time())
    token = make_id_token(id_token_claims(NONCE, now=now + 600))

    assert reject_code(token, cfg, now=now) == "token_not_yet_valid"


def test_old_iat_is_stale(cfg: SsoConfig) -> None:
    now = int(time.time())
    token = make_id_token(id_token_claims(NONCE, now=now - 1800, exp=now + 3600))

    assert reject_code(token, cfg, now=now) == "token_stale"


def test_missing_nonce_is_refused(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE), drop=["nonce"])

    assert reject_code(token, cfg) == "nonce_missing"


def test_other_nonce_is_refused(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims("a-different-nonce"))

    assert reject_code(token, cfg) == "nonce_mismatch"


def test_missing_exp_or_iat_is_malformed(cfg: SsoConfig) -> None:
    assert (
        reject_code(make_id_token(id_token_claims(NONCE), drop=["exp"]), cfg) == "token_malformed"
    )
    assert (
        reject_code(make_id_token(id_token_claims(NONCE), drop=["iat"]), cfg) == "token_malformed"
    )


def test_garbage_and_missing_tokens(cfg: SsoConfig) -> None:
    assert reject_code("", cfg) == "token_missing"
    assert reject_code("not-a-token", cfg) == "token_malformed"
    assert reject_code("a.b.c", cfg) == "token_malformed"


def test_missing_loginid_names_the_received_claims(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE), drop=["loginid"])

    with pytest.raises(SsoReject) as caught:
        verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert caught.value.code == "claim_missing:loginid"
    assert "username" in caught.value.diagnostic["claim_names"]
    # 값은 담지 않는다.
    assert "개발 사용자" not in json.dumps(caught.value.diagnostic, ensure_ascii=False)


@pytest.mark.parametrize("value", [["dev.user"], "dev user", "x" * 65, "<script>", 12345, ""])
def test_invalid_loginid_is_refused(cfg: SsoConfig, value: object) -> None:
    token = make_id_token(id_token_claims(NONCE, loginid=value))

    assert reject_code(token, cfg) == "claim_invalid:loginid"


def test_loginid_is_trimmed(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE, loginid="  dev.user@example  "))

    login = verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert login.loginid == "dev.user@example"


def test_display_claims_take_a_one_item_list_and_drop_control_characters(cfg: SsoConfig) -> None:
    token = make_id_token(
        id_token_claims(NONCE, username=["홍길동"], deptname="생산​기술\x07팀" + "가" * 200)
    )

    login = verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert login.name == "홍길동"
    assert login.dept is not None
    assert login.dept.startswith("생산기술팀")
    assert len(login.dept) == 100


def test_missing_or_odd_display_claims_become_none(cfg: SsoConfig) -> None:
    token = make_id_token(id_token_claims(NONCE, username=["a", "b"]), drop=["deptname"])

    login = verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert login.name is None
    assert login.dept is None


def test_renamed_claims_are_read() -> None:
    cfg = use_config({names.ENV_CLAIM_LOGINID: "upn", names.ENV_CLAIM_USERNAME: "display"})
    token = make_id_token(id_token_claims(NONCE, upn="renamed.user", display="이름"))

    login = verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert login.loginid == "renamed.user"
    assert login.name == "이름"


def test_unknown_thumbprint_still_tries_every_configured_certificate() -> None:
    cfg = use_config({names.ENV_SIGNING_CERT: f"{other_signing().der_b64},{signing().der_b64}"})
    token = make_id_token(id_token_claims(NONCE), headers={"x5t": "unknown", "kid": "unknown"})

    login = verify_id_token(token, cfg, expected_nonce=NONCE, now=int(time.time()))

    assert login.loginid == LOGINID


def test_pick_certs_puts_the_matching_thumbprint_first() -> None:
    cfg = load_config(
        sso_environ({names.ENV_SIGNING_CERT: f"{other_signing().der_b64},{signing().der_b64}"})
    )

    ordered, matched = pick_certs(cfg.signing_certs, signing().x5t, "")
    unknown, none_matched = pick_certs(cfg.signing_certs, "nope", "")

    assert matched and [cert.x5t for cert in ordered] == [signing().x5t, other_signing().x5t]
    assert not none_matched and len(unknown) == 2


def test_minimum_key_length_is_enforced_by_the_verifier() -> None:
    """설정이 1024비트를 거르지만, 검증기 자체도 짧은 키를 거절하게 묶어 둔다."""
    from capa_simulation.auth.tokens import _api

    with pytest.warns(jwt.InsecureKeyLengthWarning):
        token = jwt.encode({"a": 1}, weak_signing().private_key, algorithm="RS256")

    with pytest.raises(jwt.InvalidKeyError):
        _api().decode(token, key=weak_signing().private_key.public_key(), algorithms=["RS256"])


def test_session_round_trip(cfg: SsoConfig) -> None:
    now = int(time.time())

    token, issued = issue_session(cfg, loginid="dev.user", name="이름", dept=None, now=now)
    claims = verify_session(token, cfg, now=now)

    assert claims == issued
    assert claims.auth_time == claims.iat == now
    assert claims.exp == now + 6 * 3600 == now + cfg.session_seconds
    assert 16 <= len(claims.sid) <= 64 and claims.sid != claims.jti
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["aud"] == SESSION_AUDIENCE
    assert payload["v"] == 2
    assert (payload["sid"], payload["auth_time"]) == (claims.sid, now)
    assert "dept" not in payload
    assert set(payload) <= {
        "iss",
        "aud",
        "sub",
        "name",
        "dept",
        "iat",
        "exp",
        "jti",
        "sid",
        "auth_time",
        "v",
    }


def test_session_expiry_follows_the_given_clock(cfg: SsoConfig) -> None:
    now = int(time.time())
    token, issued = issue_session(cfg, loginid="dev.user", name=None, dept=None, now=now)

    with pytest.raises(SsoReject) as caught:
        verify_session(token, cfg, now=issued.exp + 31)

    assert caught.value.code == "session_expired"
    assert verify_session(token, cfg, now=issued.exp + 29).loginid == "dev.user"


def test_session_from_the_wall_clock_past_is_expired(cfg: SsoConfig) -> None:
    past = int(time.time()) - cfg.session_seconds - 120
    token, _ = issue_session(cfg, loginid="dev.user", name=None, dept=None, now=past)

    with pytest.raises(SsoReject) as caught:
        verify_session(token, cfg, now=int(time.time()))

    assert caught.value.code == "session_expired"


def test_session_signed_with_another_secret_is_invalid(cfg: SsoConfig) -> None:
    now = int(time.time())
    other = use_config({names.ENV_SECRET: "another-q7Lm2Xp9Rt4Vb8Nc3Kd6Hf1Js5Gw"})
    token, _ = issue_session(other, loginid="dev.user", name=None, dept=None, now=now)

    with pytest.raises(SsoReject) as caught:
        verify_session(token, cfg, now=now)

    assert caught.value.code == "session_invalid"


def test_state_token_cannot_be_used_as_a_session(cfg: SsoConfig) -> None:
    now = int(time.time())
    state_token = issue_state(cfg, state="s" * 43, nonce="n" * 43, next_path="/", now=now)

    with pytest.raises(SsoReject):
        verify_session(state_token, cfg, now=now)
    # 키를 같게 맞춰도 aud 가 달라 거절한다.
    forged = jwt.encode(
        {
            "iss": "capa-simulation",
            "aud": STATE_AUDIENCE,
            "sub": "dev.user",
            "iat": now,
            "exp": now + 60,
            "jti": "abcdefghij",
            "sid": "s" * 22,
            "auth_time": now,
            "v": 2,
        },
        session_key(cfg),
        algorithm="HS256",
    )
    with pytest.raises(SsoReject):
        verify_session(forged, cfg, now=now)


def test_session_token_cannot_be_used_as_a_state(cfg: SsoConfig) -> None:
    now = int(time.time())
    token, _ = issue_session(cfg, loginid="dev.user", name=None, dept=None, now=now)

    with pytest.raises(SsoReject) as caught:
        verify_state(token, cfg, now=now)

    assert caught.value.code == "state_invalid"


def test_state_round_trip_and_expiry(cfg: SsoConfig) -> None:
    now = int(time.time())
    token = issue_state(cfg, state="s" * 43, nonce="n" * 43, next_path="/?theme=dark", now=now)

    claims = verify_state(token, cfg, now=now)

    assert (claims.state, claims.nonce, claims.next_path) == ("s" * 43, "n" * 43, "/?theme=dark")
    assert claims.exp - claims.iat == 600
    with pytest.raises(SsoReject):
        verify_state(token, cfg, now=now + 601)
    old = issue_state(cfg, state="s" * 43, nonce="n" * 43, next_path="/", now=now - 700)
    with pytest.raises(SsoReject):
        verify_state(old, cfg, now=now)


def test_derived_keys_differ_by_purpose(cfg: SsoConfig) -> None:
    assert session_key(cfg) != state_key(cfg)
    assert session_key(cfg) != cfg.secret
    assert len(session_key(cfg)) == 32
    assert derive_key(b"a", b"x") != derive_key(b"a", b"y")


def test_keys_need_a_secret() -> None:
    cfg = load_config({})

    with pytest.raises(SsoReject) as caught:
        session_key(cfg)

    assert caught.value.code == "config_broken"


# --- 세션 갱신 · 끝 시각 ---------------------------------------------------------------------

HOUR = 3600
LOGIN_AT = 1_800_000_000


def _session_payload(cfg: SsoConfig, now: int, **changes: Any) -> dict[str, Any]:
    """손으로 서명할 세션 페이로드 — `changes` 로 바꾸고 값이 None 이면 뺀다."""
    payload: dict[str, Any] = {
        "iss": SESSION_ISSUER,
        "aud": SESSION_AUDIENCE,
        "sub": LOGINID,
        "iat": now,
        "exp": now + cfg.session_seconds,
        "jti": "j" * 22,
        "sid": "s" * 22,
        "auth_time": now,
        "v": 2,
    }
    for key, value in changes.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    return payload


def _signed(cfg: SsoConfig, payload: dict[str, Any]) -> str:
    return jwt.encode(payload, session_key(cfg), algorithm="HS256")


def _session_code(token: str, cfg: SsoConfig, *, now: int) -> str:
    with pytest.raises(SsoReject) as caught:
        verify_session(token, cfg, now=now)
    return caught.value.code


def test_renew_keeps_the_person_and_session_but_moves_the_clock(cfg: SsoConfig) -> None:
    _, issued = issue_session(cfg, loginid=LOGINID, name="이름", dept="부서", now=LOGIN_AT)
    now = LOGIN_AT + 2 * HOUR

    renewed = renew_session(cfg, issued, now=now)

    assert renewed is not None
    token, fresh = renewed
    assert (fresh.loginid, fresh.name, fresh.dept) == (LOGINID, "이름", "부서")
    assert (fresh.sid, fresh.auth_time) == (issued.sid, LOGIN_AT)
    assert fresh.jti != issued.jti
    assert (fresh.iat, fresh.exp) == (now, now + 6 * HOUR)
    assert verify_session(token, cfg, now=now) == fresh


def test_renew_within_a_minute_returns_none(cfg: SsoConfig) -> None:
    _, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=LOGIN_AT)

    assert renew_session(cfg, issued, now=LOGIN_AT + RENEW_MIN_INTERVAL - 1) is None
    assert renew_session(cfg, issued, now=LOGIN_AT + RENEW_MIN_INTERVAL) is not None
    assert renew_session(cfg, issued, now=LOGIN_AT - 5) is None, "시계가 뒤로 가도 다시 서명 안 함"


def test_renew_stops_at_the_maximum(cfg: SsoConfig) -> None:
    hours = [5, 10, 15, 20]
    _, claims = renewed_session(
        cfg, login_at=LOGIN_AT, renew_at=[LOGIN_AT + hour * HOUR for hour in hours]
    )

    assert claims.auth_time == LOGIN_AT
    assert claims.exp == LOGIN_AT + 24 * HOUR == claims.auth_time + cfg.session_max_seconds
    assert renew_session(cfg, claims, now=LOGIN_AT + 21 * HOUR) is None
    assert renew_session(cfg, claims, now=LOGIN_AT + 23 * HOUR) is None


def test_session_end_takes_the_earliest(cfg: SsoConfig) -> None:
    iat = LOGIN_AT + 10 * HOUR

    def end(exp: int, auth_time: int, renewed: int | None = None) -> int:
        return session_end(exp=exp, iat=iat, auth_time=auth_time, cfg=cfg, renewed_exp=renewed)

    assert end(iat + 6 * HOUR, iat) == iat + 6 * HOUR
    assert end(iat + 12 * HOUR, iat) == iat + 6 * HOUR, "exp 를 지금 설정의 유휴로 깎는다"
    assert end(iat + 6 * HOUR, iat - 20 * HOUR) == iat + 4 * HOUR, "상한(auth_time + 24h)"
    assert end(iat + 6 * HOUR, iat, iat + 8 * HOUR) == iat + 8 * HOUR, "갱신 표가 늦으면 그것"
    assert end(iat + 6 * HOUR, iat, iat + 2 * HOUR) == iat + 6 * HOUR, "갱신 표가 이르면 토큰"
    assert end(iat + 6 * HOUR, iat, iat + 30 * HOUR) == iat + 24 * HOUR, "갱신 표도 상한까지"
    assert end(iat + 6 * HOUR, iat - 20 * HOUR, iat + 6 * HOUR) == iat + 4 * HOUR


def test_lowering_the_setting_takes_effect_at_once() -> None:
    longer = load_config(sso_environ({names.ENV_SESSION_HOURS: "12"}))
    default = load_config(sso_environ())
    token, issued = issue_session(longer, loginid=LOGINID, name=None, dept=None, now=LOGIN_AT)
    assert issued.exp == LOGIN_AT + 12 * HOUR

    edge = LOGIN_AT + 6 * HOUR + SESSION_LEEWAY
    assert verify_session(token, default, now=edge).sid == issued.sid
    assert _session_code(token, default, now=edge + 1) == "session_expired"
    assert verify_session(token, longer, now=edge + 1).sid == issued.sid

    wide = load_config(sso_environ({names.ENV_SESSION_MAX_HOURS: "24"}))
    narrow = load_config(sso_environ({names.ENV_SESSION_MAX_HOURS: "8"}))
    token, claims = renewed_session(wide, login_at=LOGIN_AT, renew_at=[LOGIN_AT + 5 * HOUR])
    assert claims.exp == LOGIN_AT + 11 * HOUR
    cap = LOGIN_AT + 8 * HOUR + SESSION_LEEWAY
    assert verify_session(token, narrow, now=cap).sid == claims.sid
    assert _session_code(token, narrow, now=cap + 1) == "session_expired"
    assert verify_session(token, wide, now=cap + 1).sid == claims.sid


@pytest.mark.parametrize("dropped", ["sid", "auth_time"])
def test_session_without_sid_or_auth_time_is_invalid(cfg: SsoConfig, dropped: str) -> None:
    now = int(time.time())
    token = _signed(cfg, _session_payload(cfg, now, **{dropped: None}))

    assert _session_code(token, cfg, now=now) == "session_invalid"
    assert verify_session(_signed(cfg, _session_payload(cfg, now)), cfg, now=now).sid == "s" * 22


@pytest.mark.parametrize(
    "changes",
    [
        {"v": 1},
        {"v": 1, "sid": None, "auth_time": None},
        {"v": None},
        {"sid": "short"},
        {"sid": "s" * 21 + "!"},
        {"auth_time": "1800000000"},
        {"auth_time": True},
        {"iat": 1.5},
    ],
)
def test_version_one_session_is_invalid(cfg: SsoConfig, changes: dict[str, Any]) -> None:
    """v1(배포 전 꼴) · 꼴이 틀린 sid · 정수가 아닌 시각은 받지 않는다."""
    now = int(time.time())

    token = _signed(cfg, _session_payload(cfg, now, **changes))

    assert _session_code(token, cfg, now=now) == "session_invalid"


def test_auth_time_after_iat_or_future_iat_is_invalid(cfg: SsoConfig) -> None:
    now = LOGIN_AT
    later_login = _signed(cfg, _session_payload(cfg, now, auth_time=now + 1))
    future = _signed(cfg, _session_payload(cfg, now + SESSION_LEEWAY + 1))
    edge = _signed(cfg, _session_payload(cfg, now + SESSION_LEEWAY))

    assert _session_code(later_login, cfg, now=now) == "session_invalid"
    assert _session_code(future, cfg, now=now) == "session_invalid"
    assert verify_session(edge, cfg, now=now).iat == now + SESSION_LEEWAY


def test_decode_session_ignores_the_end_but_not_the_signature(cfg: SsoConfig) -> None:
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=LOGIN_AT)
    long_after = LOGIN_AT + 30 * HOUR

    assert decode_session(token, cfg, now=long_after) == issued
    assert _session_code(token, cfg, now=long_after) == "session_expired"
    other = load_config(sso_environ({names.ENV_SECRET: "another-q7Lm2Xp9Rt4Vb8Nc3Kd6Hf1Js5Gw"}))
    forged, _ = issue_session(other, loginid=LOGINID, name=None, dept=None, now=LOGIN_AT)
    with pytest.raises(SsoReject) as caught:
        decode_session(forged, cfg, now=LOGIN_AT)
    assert caught.value.code == "session_invalid"
    assert _session_code(forged, cfg, now=LOGIN_AT) == "session_invalid"
