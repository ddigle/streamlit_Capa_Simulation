# Purpose: S3 접속 명단의 서명·경계·파일 꼴·합성·장애·자가 회복·저장·Admin 화면·값 비노출을 지킨다.

"""S3 명단(`io/s3_small` · `auth/access_store` · `components/access_list_admin`).

앱 시작에 받아 메모리에 올리고, 판정은 메모리로, 고침은 S3 저장 뒤 메모리로 간다. 저장소는 서명을
검증하는 가짜 S3(`scripts/s3_mock_store.py`)이고 값은 모두 합성(`demo.*`)이다. 서명은 AWS 문서의
알려진 벡터로 고정한 뒤, 가짜 S3 가 받은 요청 그대로 다시 지어 본다(주소 인코딩 · 서명한 머리 ·
본문 지문).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from alert_marks import active_state, alert_notes, states
from asgi_driver import http, websocket_talk
from sso_support import sso_environ, use_config
from streamlit.testing.v1 import AppTest
from test_sso_access import (
    ECHO_DISCONNECTS,
    FETCH,
    NAVIGATE,
    ORIGIN,
    assert_absent,
    cookie_of,
    error_code_of,
    events_named,
    gated_app,
    has_live_session,
    passed,
    session_token,
    sign_in,
)

from capa_simulation.auth import access_store, names, runtime, server
from capa_simulation.auth.access import (
    GRADE_ADMIN,
    GRADE_USER,
    ListChange,
    ListDocument,
    ListEntry,
)
from capa_simulation.auth.config import SsoConfig, SsoMode, SsoProblem, load_config
from capa_simulation.auth.identity import Identity, IdentityProblem, session_check
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import access_list_admin, sso_identity, sso_status
from capa_simulation.io import s3_small
from capa_simulation.io.s3_small import S3Failure, S3Target

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import s3_mock_store  # noqa: E402
from s3_mock_store import MockStore, etag_of, start_mock  # noqa: E402

ADMIN = "demo.admin"
USER = "demo.user"
OTHER = "demo.other"
GONE = "demo.gone"
OBJECT = names.DEFAULT_ACCESS_OBJECT
EXAMPLE_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
EXAMPLE_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
EXAMPLE_HOST = "examplebucket.s3.amazonaws.com"
EXAMPLE_DATE = "20130524T000000Z"


@pytest.fixture()
def mock_s3() -> Iterator[tuple[MockStore, str]]:
    store = MockStore()
    server, endpoint = start_mock(store)
    yield store, endpoint
    server.shutdown()
    server.server_close()


def target_of(store: MockStore, endpoint: str, *, secret: str | None = None) -> S3Target:
    return S3Target(
        endpoint_url=endpoint,
        bucket=store.bucket,
        region=store.region,
        access_key=store.access_key,
        secret_key=store.secret_key if secret is None else secret,
    )


def s3_environ(store: MockStore, endpoint: str, **overrides: str) -> dict[str, str]:
    return {
        names.ENV_ACCESS_ADMINS: ADMIN,
        names.ENV_ACCESS_USERS: "",
        names.ENV_S3_ACCESS_KEY: store.access_key,
        names.ENV_S3_SECRET_KEY: store.secret_key,
        names.ENV_S3_ENDPOINT: endpoint,
        names.ENV_S3_BUCKET: store.bucket,
        names.ENV_S3_REGION: store.region,
        **overrides,
    }


def file_body(*loginids: str, revision: int = 1, **extra: Any) -> bytes:
    users = [
        {
            "loginid": loginid,
            "grade": GRADE_USER,
            "added_by": ADMIN,
            "added_at": "2026-11-05T00:00:00Z",
        }
        for loginid in loginids
    ]
    return json.dumps(
        {"format": access_store.OBJECT_FORMAT, "revision": revision, "users": users, **extra}
    ).encode("utf-8")


def s3_config(store: MockStore, endpoint: str, **overrides: str) -> SsoConfig:
    """기동까지 — 아직 읽지 않는다."""
    return use_config(s3_environ(store, endpoint, **overrides))


def started(store: MockStore, endpoint: str, *loginids: str, **overrides: str) -> SsoConfig:
    """명단 파일을 두고 진입 파일처럼 기동한다(읽기까지)."""
    if loginids:
        store.put(OBJECT, file_body(*loginids))
    cfg = s3_config(store, endpoint, **overrides)
    access_store.read_at_start(cfg)
    return cfg


def identity_of(cfg: SsoConfig, loginid: str) -> Identity:
    _, claims = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    return Identity.from_claims(claims)


def problem_of(cfg: SsoConfig, loginid: str) -> IdentityProblem | None:
    problem, _ = session_check(identity_of(cfg, loginid), cfg, int(time.time()))
    return problem


def rewind_attempt(seconds: int) -> None:
    source = runtime.access_source()
    assert source is not None and source.attempted_at is not None
    runtime.publish_access_source(replace(source, attempted_at=source.attempted_at - seconds))


def requests_named(store: MockStore, method: str) -> int:
    return sum(1 for item, _ in store.requests if item == method)


# --- 서명 --------------------------------------------------------------------------------------


def test_the_signature_matches_the_published_get_vector() -> None:
    """AWS 문서 「Signature Calculations」 의 GET 예시 그대로."""
    canonical = s3_small.canonical_request(
        "GET",
        "/test.txt",
        "",
        {
            "Host": EXAMPLE_HOST,
            "Range": "bytes=0-9",
            "x-amz-content-sha256": s3_small.EMPTY_SHA256,
            "x-amz-date": EXAMPLE_DATE,
        },
        s3_small.EMPTY_SHA256,
    )

    assert hashlib.sha256(canonical.encode()).hexdigest() == (
        "7344ae5b7ee6c3e7e6b0fe0640412a37625d1fbfff95c48bbb2dc43964946972"
    )
    assert s3_small.signature_v4(
        canonical, amz_date=EXAMPLE_DATE, region="us-east-1", secret_key=EXAMPLE_SECRET_KEY
    ) == ("f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


def test_the_signature_matches_the_published_put_vector() -> None:
    """같은 문서의 PUT 예시 — 인코딩한 경로와 추가 머리까지."""
    payload = hashlib.sha256(b"Welcome to Amazon S3.").hexdigest()
    canonical = s3_small.canonical_request(
        "PUT",
        "/test%24file.text",
        "",
        {
            "Date": "Fri, 24 May 2013 00:00:00 GMT",
            "Host": EXAMPLE_HOST,
            "x-amz-content-sha256": payload,
            "x-amz-date": EXAMPLE_DATE,
            "x-amz-storage-class": "REDUCED_REDUNDANCY",
        },
        payload,
    )

    assert s3_small.signature_v4(
        canonical, amz_date=EXAMPLE_DATE, region="us-east-1", secret_key=EXAMPLE_SECRET_KEY
    ) == ("98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd")


def test_the_authorization_header_is_built_from_the_same_parts() -> None:
    target = S3Target(
        endpoint_url=f"https://{EXAMPLE_HOST}",
        bucket="examplebucket",
        region="us-east-1",
        access_key=EXAMPLE_ACCESS_KEY,
        secret_key=EXAMPLE_SECRET_KEY,
    )

    headers = s3_small.signed_headers(
        target,
        "GET",
        "/test.txt",
        host=EXAMPLE_HOST,
        payload_sha256=s3_small.EMPTY_SHA256,
        moment=1369353600,
        extra={"Range": "bytes=0-9"},
    )

    assert headers["x-amz-date"] == EXAMPLE_DATE
    assert headers["Authorization"] == (
        f"AWS4-HMAC-SHA256 Credential={EXAMPLE_ACCESS_KEY}/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


def test_the_address_is_path_style_and_each_part_is_encoded_once() -> None:
    assert s3_small.object_path("Capa_Bucket", "access/a b+c.json") == (
        "/Capa_Bucket/access/a%20b%2Bc.json"
    )


def test_the_default_port_is_left_out_of_the_signed_host() -> None:
    assert s3_small._host_of("store.example.invalid:443", "https") == "store.example.invalid"
    assert s3_small._host_of("store.example.invalid:80", "http") == "store.example.invalid"
    assert s3_small._host_of("store.example.invalid:9020", "http") == "store.example.invalid:9020"


# --- 작은 객체 경계 ------------------------------------------------------------------------------


def test_put_get_head_go_round_with_a_verified_signature(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    target = target_of(store, endpoint)
    key = "access/a b+c.json"

    etag = s3_small.put_object(target, key, b'{"a": 1}')

    assert etag == etag_of(b'{"a": 1}')
    found = s3_small.get_object(target, key)
    assert found is not None and found.body == b'{"a": 1}' and found.etag == etag
    assert s3_small.head_object(target, key) == etag
    assert store.objects[key] == b'{"a": 1}'
    assert [item for item, _ in store.requests] == ["PUT", "GET", "HEAD"]


def test_a_missing_key_is_none_not_a_failure(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    target = target_of(store, endpoint)

    assert s3_small.get_object(target, "none.json") is None
    assert s3_small.head_object(target, "none.json") is None


def test_a_wrong_secret_is_an_auth_rejection_with_its_status(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint, secret="wrong-secret"), OBJECT)

    assert caught.value.kind == s3_small.KIND_AUTH
    assert caught.value.status == 403
    assert caught.value.code == "SignatureDoesNotMatch"


@pytest.mark.parametrize("status", [401, 403])
def test_both_auth_statuses_are_rejections(status: int, mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (status, "AccessDenied")

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert (caught.value.kind, caught.value.status) == (s3_small.KIND_AUTH, status)


def test_a_missing_bucket_is_a_failure_on_get_and_put(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    target = replace(target_of(store, endpoint), bucket="Other_bucket")

    for call in (
        lambda: s3_small.get_object(target, OBJECT),
        lambda: s3_small.put_object(target, OBJECT, b"{}"),
    ):
        with pytest.raises(S3Failure) as caught:
            call()
        assert (caught.value.kind, caught.value.status) == (s3_small.KIND_NO_BUCKET, 404)


def test_a_slow_answer_is_a_timeout(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    store.delay_seconds = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.1)

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert caught.value.kind == s3_small.KIND_TIMEOUT
    assert caught.value.status is None


def test_a_closed_port_is_unreachable(mock_s3: tuple[MockStore, str]) -> None:
    store, _ = mock_s3
    server, endpoint = start_mock(store)
    server.shutdown()
    server.server_close()

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert caught.value.kind == s3_small.KIND_UNREACHABLE


def test_a_big_object_stops_at_the_limit(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.put(OBJECT, b"x" * (s3_small.MAX_OBJECT_BYTES + 10))

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert caught.value.kind == s3_small.KIND_TOO_LARGE


def test_another_server_answer_is_kept_as_its_status(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert (caught.value.kind, caught.value.status, caught.value.code) == (
        s3_small.KIND_OTHER,
        503,
        "SlowDown",
    )


def test_the_keys_are_not_in_a_repr_or_a_failure(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    target = target_of(store, endpoint)
    store.force["GET"] = (403, "AccessDenied")

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target, OBJECT)

    for text in (repr(target), str(caught.value), repr(caught.value)):
        assert store.access_key not in text
        assert store.secret_key not in text


def test_the_light_import_does_not_bring_streamlit() -> None:
    """문지기 · 기동 쪽이 이 경계를 불러도 Streamlit · PyJWT 가 딸려 오지 않는다."""
    code = (
        "import sys\n"
        "import capa_simulation.io.s3_small\n"
        "import capa_simulation.auth.access_store\n"
        "print(sorted({'streamlit', 'jwt'} & set(sys.modules)))\n"
    )
    found = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": ""},
    )

    assert found.stdout.strip() == "[]"


# --- 파일 꼴 -------------------------------------------------------------------------------------


def test_the_file_goes_round() -> None:
    document = ListDocument(
        revision=7,
        entries=(ListEntry(USER, ADMIN, "2026-11-05T00:00:00Z"),),
        changes=(ListChange(ADMIN, "2026-11-05T00:00:00Z", "add", USER),),
    )

    parsed = access_store.parse_document(access_store.render_document(document))

    assert parsed == document
    payload = json.loads(access_store.render_document(document))
    assert payload["format"] == access_store.OBJECT_FORMAT
    assert payload["users"][0]["grade"] == GRADE_USER


@pytest.mark.parametrize(
    ("body", "kind"),
    [
        (b"\xff\xfe", access_store.KIND_CORRUPT),
        (b"not json", access_store.KIND_CORRUPT),
        (b"[]", access_store.KIND_CORRUPT),
        (json.dumps({"format": 1, "users": []}).encode(), access_store.KIND_CORRUPT),
        (
            json.dumps({"format": 1, "revision": True, "users": []}).encode(),
            access_store.KIND_CORRUPT,
        ),
        (
            json.dumps({"format": 1, "revision": -1, "users": []}).encode(),
            access_store.KIND_CORRUPT,
        ),
        (json.dumps({"format": 1, "revision": 1, "users": {}}).encode(), access_store.KIND_CORRUPT),
        (
            json.dumps({"format": 2, "revision": 1, "users": []}).encode(),
            access_store.KIND_UNKNOWN_FORMAT,
        ),
        (json.dumps({"revision": 1, "users": []}).encode(), access_store.KIND_UNKNOWN_FORMAT),
    ],
)
def test_a_broken_file_is_a_failure_with_no_value_in_it(body: bytes, kind: str) -> None:
    with pytest.raises(S3Failure) as caught:
        access_store.parse_document(body)

    assert caught.value.kind == kind
    assert str(caught.value) == kind


def test_entries_go_through_the_same_shape_check() -> None:
    body = json.dumps(
        {
            "format": 1,
            "revision": 3,
            "users": [
                {"loginid": "  Demo.User "},
                {"loginid": r"DOMAIN\demo.x"},
                {"loginid": "-"},
                {"loginid": 7},
                "demo.text",
                {"name": "no id"},
            ],
        }
    ).encode()

    parsed = access_store.parse_document(body)

    assert [entry.loginid for entry in parsed.entries] == [USER]
    assert parsed.unreadable == 5


def test_a_grade_in_the_file_never_makes_an_admin(mock_s3: tuple[MockStore, str]) -> None:
    """파일에 `admin` 을 적어도 그 사람은 사용자다 — S3 쓰기 권한이 관리자 권한이 되지 않는다."""
    store, endpoint = mock_s3
    store.put(
        OBJECT,
        json.dumps(
            {
                "format": 1,
                "revision": 1,
                "users": [{"loginid": OTHER, "grade": GRADE_ADMIN}, {"loginid": USER}],
            }
        ).encode(),
    )

    cfg = started(store, endpoint)

    access = runtime.current_access(cfg)
    assert access.grade_of(OTHER) == GRADE_USER
    assert access.admin_count == 1
    assert not access_store.is_admin(cfg, OTHER)
    source = runtime.access_source()
    assert source is not None and source.document is not None
    assert source.document.demoted == 1


def test_the_change_log_is_capped_when_read_and_when_written() -> None:
    changes = [{"by": ADMIN, "at": "t", "what": "add", "loginid": f"demo.{n}"} for n in range(250)]
    body = json.dumps({"format": 1, "revision": 1, "users": [], "changes": changes}).encode()

    parsed = access_store.parse_document(body)

    assert len(parsed.changes) == access_store.MAX_CHANGES
    assert parsed.changes[-1].loginid == "demo.249"
    assert len(json.loads(access_store.render_document(parsed))["changes"]) == 200


# --- 설정과 합성 --------------------------------------------------------------------------------


def _notice_codes(cfg: SsoConfig, env: str) -> list[str]:
    return [item.code for item in cfg.notices if item.env == env]


def test_without_keys_the_environment_list_works_as_before(mock_s3: tuple[MockStore, str]) -> None:
    store, _ = mock_s3
    cfg = use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})

    access_store.read_at_start(cfg)

    assert not cfg.access_s3_requested and cfg.access_s3 is None
    assert runtime.access_source() is None
    assert runtime.current_access(cfg) is cfg.access
    assert problem_of(cfg, USER) is None
    assert store.requests == []


def test_with_keys_the_user_list_is_ignored_and_noticed(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3

    cfg = s3_config(store, endpoint, **{names.ENV_ACCESS_USERS: USER})

    assert cfg.access.grade_of(USER) is None
    assert cfg.access.user_count == 0
    assert cfg.access_s3 is not None
    assert _notice_codes(cfg, names.ENV_ACCESS_USERS) == ["s3_users_ignored"]
    assert cfg.env_presence[names.ENV_ACCESS_USERS]


def test_keys_alone_switch_the_list_on_and_admins_stay_required(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3

    cfg = use_config(s3_environ(store, endpoint), drop=[names.ENV_ACCESS_ADMINS])

    assert cfg.mode is SsoMode.BROKEN
    assert SsoProblem(names.ENV_ACCESS_ADMINS, "missing") in cfg.problems


@pytest.mark.parametrize(
    ("drop", "env"),
    [
        (names.ENV_S3_SECRET_KEY, names.ENV_S3_SECRET_KEY),
        (names.ENV_S3_ACCESS_KEY, names.ENV_S3_ACCESS_KEY),
        (names.ENV_S3_ENDPOINT, names.ENV_S3_ENDPOINT),
        (names.ENV_S3_BUCKET, names.ENV_S3_BUCKET),
    ],
)
def test_a_missing_piece_is_a_notice_and_only_admins_get_in(
    drop: str, env: str, mock_s3: tuple[MockStore, str]
) -> None:
    """앱은 뜬다 — 막힘이 아니고, 열림도 아니다."""
    store, endpoint = mock_s3

    cfg = use_config(s3_environ(store, endpoint), drop=[drop])
    access_store.read_at_start(cfg)

    assert cfg.mode is SsoMode.ON
    assert cfg.access_s3_requested and cfg.access_s3 is None
    assert _notice_codes(cfg, env) == ["s3_needed"]
    assert problem_of(cfg, ADMIN) is None
    assert problem_of(cfg, USER) is IdentityProblem.DENIED
    source = runtime.access_source()
    assert source is not None and source.problem is not None
    assert source.problem.kind == access_store.KIND_CONFIG
    assert store.requests == []


@pytest.mark.parametrize(
    "value",
    [
        "ftp://store.example.invalid",
        "http://user@store.example.invalid",
        "http://store.example.invalid/prefix",
        "http://store.example.invalid?x=1",
        "http://store.example.invalid:port",
        "store.example.invalid",
    ],
)
def test_a_bad_endpoint_is_a_notice_without_its_value(value: str) -> None:
    cfg = load_config(
        {names.ENV_S3_ACCESS_KEY: "k", names.ENV_S3_SECRET_KEY: "s", names.ENV_S3_ENDPOINT: value}
    )

    assert cfg.access_s3 is None
    assert _notice_codes(cfg, names.ENV_S3_ENDPOINT) == ["s3_bad"]


def test_a_plain_http_address_is_accepted_and_noticed_outside_loopback() -> None:
    base = {
        names.ENV_S3_ACCESS_KEY: "k",
        names.ENV_S3_SECRET_KEY: "s",
        names.ENV_S3_BUCKET: "b",
        names.ENV_APP_ENV: "prod",
    }

    plain = load_config({**base, names.ENV_S3_ENDPOINT: "http://store.example.invalid:9020"})
    secure = load_config({**base, names.ENV_S3_ENDPOINT: "https://store.example.invalid:9021/"})
    loopback = load_config({**base, names.ENV_S3_ENDPOINT: "http://127.0.0.1:8607"})

    assert plain.access_s3 is not None
    assert _notice_codes(plain, names.ENV_S3_ENDPOINT) == ["s3_plain_http"]
    assert secure.access_s3 is not None
    assert secure.access_s3.endpoint_url == "https://store.example.invalid:9021"
    assert not _notice_codes(secure, names.ENV_S3_ENDPOINT)
    assert not _notice_codes(loopback, names.ENV_S3_ENDPOINT)


def test_region_and_object_have_defaults_and_can_be_changed() -> None:
    base = {
        names.ENV_S3_ACCESS_KEY: "k",
        names.ENV_S3_SECRET_KEY: "s",
        names.ENV_S3_ENDPOINT: "http://127.0.0.1:8607",
        names.ENV_S3_BUCKET: "b",
    }

    default = load_config(base)
    changed = load_config(
        {**base, names.ENV_S3_REGION: "ap-demo-1", names.ENV_ACCESS_OBJECT: "demo/list.json"}
    )
    bad = load_config({**base, names.ENV_ACCESS_OBJECT: "/leading.json"})

    assert default.access_s3 is not None and default.access_s3.region == "us-east-1"
    assert default.access_object_key == names.DEFAULT_ACCESS_OBJECT
    assert changed.access_s3 is not None and changed.access_s3.region == "ap-demo-1"
    assert changed.access_object_key == "demo/list.json"
    assert bad.access_s3 is None


def test_the_keys_leave_the_environment_and_every_repr(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    environ = s3_environ(store, endpoint)
    runtime.reset()

    full = sso_environ(environ)
    cfg = runtime.start(full)

    assert names.ENV_S3_ACCESS_KEY not in full and names.ENV_S3_SECRET_KEY not in full
    assert names.ENV_S3_ACCESS_KEY in names.SECRET_ENVIRONMENT
    assert names.ENV_S3_SECRET_KEY in names.SECRET_ENVIRONMENT
    assert names.ENV_S3_SECRET_KEY in names.WITHHELD_ENVIRONMENT
    assert cfg.env_presence[names.ENV_S3_SECRET_KEY]
    for text in (repr(cfg), str(cfg)):
        assert store.secret_key not in text and store.access_key not in text


def test_the_names_are_kept_with_the_others() -> None:
    for name in (
        names.ENV_S3_ACCESS_KEY,
        names.ENV_S3_SECRET_KEY,
        names.ENV_S3_ENDPOINT,
        names.ENV_S3_BUCKET,
        names.ENV_S3_REGION,
        names.ENV_ACCESS_OBJECT,
    ):
        assert name in names.SSO_ENVIRONMENT
    assert names.ENV_S3_ENDPOINT == "CAPA_S3_ENDPOINT_URL", "object_storage 와 같은 이름"
    assert names.ENV_S3_BUCKET == "CAPA_S3_BUCKET"
    assert names.ENV_S3_REGION == "CAPA_S3_REGION"


# --- 시작 · 판정 · 장애 --------------------------------------------------------------------------


def test_the_list_read_at_start_decides_without_going_to_s3(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    before = list(store.requests)

    assert problem_of(cfg, USER) is None
    assert problem_of(cfg, ADMIN) is None
    assert problem_of(cfg, GONE) is IdentityProblem.DENIED
    assert store.requests == before, "판정은 메모리로 한다"
    assert before == [("GET", f"/{store.bucket}/{OBJECT}")]


def test_a_missing_file_is_an_empty_list_not_a_failure(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3

    cfg = started(store, endpoint)

    source = runtime.access_source()
    assert source is not None
    assert source.problem is None and source.document == ListDocument()
    assert not access_store.is_unread(cfg)
    assert problem_of(cfg, ADMIN) is None
    assert problem_of(cfg, USER) is IdentityProblem.DENIED


@pytest.mark.parametrize(
    ("body", "force", "kind"),
    [
        (None, (403, "AccessDenied"), s3_small.KIND_AUTH),
        (None, (503, "SlowDown"), s3_small.KIND_OTHER),
        (b"not json", None, access_store.KIND_CORRUPT),
        (
            json.dumps({"format": 9, "revision": 1, "users": []}).encode(),
            None,
            access_store.KIND_UNKNOWN_FORMAT,
        ),
    ],
)
def test_when_the_read_fails_only_admins_get_in(
    body: bytes | None,
    force: tuple[int, str] | None,
    kind: str,
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    if body is not None:
        store.put(OBJECT, body)
    if force is not None:
        store.force["GET"] = force

    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)

    assert access_store.is_unread(cfg)
    source = runtime.access_source()
    assert source is not None and source.problem is not None and source.problem.kind == kind
    assert problem_of(cfg, ADMIN) is None
    assert problem_of(cfg, USER) is IdentityProblem.DENIED
    assert runtime.current_access(cfg).enforced, "열림으로 떨어지지 않는다"
    [event] = events_named("access_read")
    assert event.value("reason") == kind


def test_a_timeout_at_start_leaves_the_app_up_for_admins(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    store.delay_seconds = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.1)

    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)

    source = runtime.access_source()
    assert source is not None and source.problem is not None
    assert source.problem.kind == s3_small.KIND_TIMEOUT
    assert problem_of(cfg, ADMIN) is None
    assert problem_of(cfg, USER) is IdentityProblem.DENIED


def test_after_a_good_read_a_blocked_s3_does_not_stop_the_list(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.force["GET"] = (503, "SlowDown")
    identity = identity_of(cfg, ADMIN)

    problem = access_store.reread(cfg, identity)

    assert problem is not None and problem.status == 503
    assert problem_of(cfg, USER) is None, "메모리 명단으로 판정이 이어진다"
    assert problem_of(cfg, GONE) is IdentityProblem.DENIED
    assert not access_store.is_unread(cfg)


def test_a_server_with_sso_off_does_not_go_to_s3(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    runtime.reset()
    cfg = runtime.start(s3_environ(store, endpoint))

    access_store.read_at_start(cfg)

    assert cfg.mode is SsoMode.OFF
    assert not access_store.is_on(cfg)
    assert store.requests == []


def test_the_entry_point_reads_once_at_start(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    store.put(OBJECT, file_body(USER))
    runtime.reset()
    for name, value in sso_environ(s3_environ(store, endpoint)).items():
        monkeypatch.setenv(name, value)

    cfg = server.start_sso()

    assert requests_named(store, "GET") == 1
    assert runtime.current_access(cfg).allows(USER)
    assert names.ENV_S3_SECRET_KEY not in os.environ


# --- 자가 회복 -----------------------------------------------------------------------------------


def test_the_callback_reads_again_just_before_denying(mock_s3: tuple[MockStore, str]) -> None:
    """못 읽은 채로 뜬 서버 — S3 가 돌아온 뒤 사용자가 로그인하면 재시작 없이 들어온다."""
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    store.put(OBJECT, file_body(USER))
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    assert access_store.is_unread(cfg)
    store.force.clear()
    rewind_attempt(access_store.RETRY_SECONDS)

    response = sign_in(gated_app(), {}, USER)

    assert has_live_session(cfg, response), response.text
    assert not access_store.is_unread(cfg)
    assert requests_named(store, "GET") == 2


def test_the_retry_runs_at_most_once_a_minute(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    app = gated_app()

    denied_now = sign_in(app, {}, USER)

    assert error_code_of(denied_now) == "not_on_list"
    assert requests_named(store, "GET") == 1, "방금 시도했으니 다시 가지 않는다"

    rewind_attempt(access_store.RETRY_SECONDS - 1)
    assert error_code_of(sign_in(app, {}, USER)) == "not_on_list"
    assert requests_named(store, "GET") == 1

    rewind_attempt(1)
    assert error_code_of(sign_in(app, {}, USER)) == "not_on_list"
    assert requests_named(store, "GET") == 2, "60초가 지나면 한 번 더"

    assert error_code_of(sign_in(app, {}, OTHER)) == "not_on_list"
    assert requests_named(store, "GET") == 2


def test_the_retry_does_not_run_on_the_event_loop(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    store.force.clear()
    rewind_attempt(access_store.RETRY_SECONDS)
    seen: list[bool] = []
    real_get = s3_small.get_object

    def watched(*args: Any, **kwargs: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            seen.append(False)
        else:
            seen.append(True)
        return real_get(*args, **kwargs)

    monkeypatch.setattr(access_store, "get_object", watched)

    sign_in(gated_app(), {}, USER)

    assert seen == [False], "거절 직전의 다시 읽기는 스레드 풀에서 돈다"


def test_no_retry_once_the_list_was_read(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    before = requests_named(store, "GET")

    response = sign_in(gated_app(), {}, GONE)

    assert not has_live_session(cfg, response)
    assert requests_named(store, "GET") == before


def test_no_retry_on_the_environment_list(mock_s3: tuple[MockStore, str]) -> None:
    store, _ = mock_s3
    cfg = use_config({names.ENV_ACCESS_ADMINS: ADMIN})

    response = sign_in(gated_app(), {}, GONE)

    assert not has_live_session(cfg, response)
    assert store.requests == []


def test_a_listed_person_never_waits_for_the_retry(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    rewind_attempt(access_store.RETRY_SECONDS)

    response = sign_in(gated_app(), {}, ADMIN)

    assert has_live_session(cfg, response), "관리자는 못 읽어도 들어온다"
    assert requests_named(store, "GET") == 1


# --- 저장 ----------------------------------------------------------------------------------------


def test_adding_saves_first_and_takes_effect_without_a_restart(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    assert problem_of(cfg, USER) is IdentityProblem.DENIED

    result = access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[USER, OTHER, USER])

    assert (result.added, result.removed, result.revision) == (2, 0, 1)
    assert problem_of(cfg, USER) is None
    saved = json.loads(store.objects[OBJECT])
    assert saved["revision"] == 1
    assert [item["loginid"] for item in saved["users"]] == [OTHER, USER]
    assert saved["users"][0]["added_by"] == ADMIN
    assert saved["users"][0]["grade"] == GRADE_USER
    assert [(item["by"], item["what"], item["loginid"]) for item in saved["changes"]] == [
        (ADMIN, "add", USER),
        (ADMIN, "add", OTHER),
    ]
    source = runtime.access_source()
    assert source is not None and source.saved_at is not None and source.save_problem is None


def test_removing_closes_the_door_for_that_person(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    gate = gated_app()
    assert passed(http(gate, "GET", "/", headers={**NAVIGATE, **cookie_of(cfg, USER)}))

    result = access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=[USER, GONE])

    assert (result.removed, result.absent) == (1, 1)
    assert problem_of(cfg, USER) is IdentityProblem.DENIED, "session_check 가 거절한다"
    assert problem_of(cfg, OTHER) is None
    denied = http(gate, "GET", "/_stcore/host-config", headers={**FETCH, **cookie_of(cfg, USER)})
    assert denied.status == 401


def test_an_open_tab_closes_at_the_next_message_after_removal(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    token = session_token(cfg, USER)
    ECHO_DISCONNECTS.clear()

    def remove_at_the_second_frame(index: int) -> None:
        if index == 1:
            access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=[USER])

    sent = websocket_talk(
        gated_app(),
        "/_stcore/stream",
        headers={**ORIGIN, "cookie": f"{cfg.session_cookie}={token}"},
        frames=[b"before", b"after"],
        before_frame=remove_at_the_second_frame,
    )

    echoed = [message["bytes"] for message in sent if message["type"] == "websocket.send"]
    assert echoed == [b"echo:before"]
    assert sent[-1]["type"] == "websocket.close" and sent[-1]["code"] == 1008


def test_a_failed_put_keeps_the_memory_as_it_was(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.force["PUT"] = (403, "AccessDenied")

    with pytest.raises(S3Failure) as caught:
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER], remove=[USER])

    assert caught.value.kind == s3_small.KIND_AUTH
    assert problem_of(cfg, OTHER) is IdentityProblem.DENIED, "저장이 실패하면 메모리는 그대로"
    assert problem_of(cfg, USER) is None
    source = runtime.access_source()
    assert source is not None and source.save_problem is not None
    assert source.save_problem.status == 403
    [event] = events_named("access_save_failed")
    assert (event.value("reason"), event.value("status")) == (s3_small.KIND_AUTH, "403")
    assert_absent(str(event.fields), USER, OTHER)


def test_a_timed_out_put_keeps_the_memory_as_it_was(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    identity = identity_of(cfg, ADMIN)
    store.delay_seconds = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.1)

    with pytest.raises(S3Failure) as caught:
        access_store.save_changes(cfg, identity, add=[USER])

    assert caught.value.kind == s3_small.KIND_TIMEOUT
    assert problem_of(cfg, USER) is IdentityProblem.DENIED


def test_a_file_changed_elsewhere_is_not_overwritten(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    elsewhere = file_body(USER, GONE, revision=9)
    store.put(OBJECT, elsewhere)

    with pytest.raises(access_store.StoreConflictError):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])

    assert store.objects[OBJECT] == elsewhere
    assert requests_named(store, "PUT") == 0
    assert problem_of(cfg, OTHER) is IdentityProblem.DENIED
    assert [item.value("reason") for item in events_named("access_save_failed")] == ["conflict"]

    assert access_store.reread(cfg, identity_of(cfg, ADMIN)) is None

    assert problem_of(cfg, GONE) is None, "다시 읽으면 그 사이 바뀐 것이 보인다"
    result = access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])
    assert result.revision == 10


def test_a_file_that_appeared_after_reading_nothing_is_not_overwritten(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    store.put(OBJECT, file_body(GONE))

    with pytest.raises(access_store.StoreConflictError):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[USER])


def test_a_file_deleted_after_reading_is_not_recreated(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    del store.objects[OBJECT]

    with pytest.raises(access_store.StoreConflictError):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])

    assert OBJECT not in store.objects


def test_a_store_without_etags_is_compared_by_revision(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.omit_etag = True
    cfg = started(store, endpoint, USER)

    first = access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])
    assert first.revision == 2
    second = access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[GONE])
    assert second.revision == 3

    store.put(OBJECT, file_body(USER, revision=8))
    with pytest.raises(access_store.StoreConflictError):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=[OTHER])


def test_nothing_to_change_does_not_write(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    before = list(store.requests)

    result = access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[USER], remove=[GONE])

    assert not result.changed
    assert (result.already, result.absent, result.revision) == (1, 1, 1)
    assert store.requests == before


def test_saves_at_the_same_time_are_put_in_a_line(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    identity = identity_of(cfg, ADMIN)
    people = [f"demo.p{index}" for index in range(6)]
    failures: list[BaseException] = []

    def add(loginid: str) -> None:
        try:
            access_store.save_changes(cfg, identity, add=[loginid])
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=add, args=(person,)) for person in people]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures
    saved = json.loads(store.objects[OBJECT])
    assert saved["revision"] == len(people)
    assert sorted(item["loginid"] for item in saved["users"]) == sorted(people)
    for person in people:
        assert problem_of(cfg, person) is None


def test_the_file_keeps_only_the_last_changes(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    changes = [
        {"by": ADMIN, "at": "t", "what": "add", "loginid": f"demo.{n}"}
        for n in range(access_store.MAX_CHANGES)
    ]
    store.put(OBJECT, file_body(revision=5, changes=changes))
    cfg = started(store, endpoint)

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[USER])

    saved = json.loads(store.objects[OBJECT])
    assert len(saved["changes"]) == access_store.MAX_CHANGES
    assert saved["changes"][-1]["loginid"] == USER
    assert saved["changes"][0]["loginid"] == "demo.1"


def test_unreadable_entries_lost_on_save_are_counted_in_the_change_log(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    store.put(
        OBJECT,
        json.dumps({"format": 1, "revision": 1, "users": [{"loginid": "-"}, "x"]}).encode(),
    )
    cfg = started(store, endpoint)
    assert runtime.current_access(cfg).unreadable_count == 2

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[USER])

    saved = json.loads(store.objects[OBJECT])
    assert [item["what"] for item in saved["changes"]] == ["add", "drop_unreadable"]
    assert saved["changes"][-1]["loginid"] == "2"


def test_saving_before_a_good_read_is_refused(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    store.force.clear()

    with pytest.raises(access_store.StoreUnreadError):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[USER])

    assert requests_named(store, "PUT") == 0


# --- 관리자 아닌 사람의 쓰기 --------------------------------------------------------------------


def test_someone_who_is_not_an_admin_cannot_write(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    before = list(store.requests)

    for identity in (identity_of(cfg, USER), identity_of(cfg, GONE), None):
        with pytest.raises(access_store.NotAdminError):
            access_store.save_changes(cfg, identity, add=[OTHER])
        with pytest.raises(access_store.NotAdminError):
            access_store.reread(cfg, identity)

    assert store.requests == before, "S3 에 가기 전에 막힌다"


def test_a_logged_out_admin_session_cannot_write(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    identity = identity_of(cfg, ADMIN)
    runtime.revoke_session(identity.sid, until=int(time.time()) + 3600)

    with pytest.raises(access_store.NotAdminError):
        access_store.save_changes(cfg, identity, add=[USER])


def test_a_grade_in_the_file_cannot_write_either(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.put(
        OBJECT,
        json.dumps(
            {"format": 1, "revision": 1, "users": [{"loginid": OTHER, "grade": GRADE_ADMIN}]}
        ).encode(),
    )
    cfg = started(store, endpoint)

    with pytest.raises(access_store.NotAdminError):
        access_store.save_changes(cfg, identity_of(cfg, OTHER), add=[USER])


# --- Admin 화면 ----------------------------------------------------------------------------------

ADMIN_SCRIPT = """
from capa_simulation.components.access_list_admin import render_access_list_admin

render_access_list_admin()
"""
STATUS_SCRIPT = """
from capa_simulation.components.sso_status import render_sso_status

render_sso_status()
"""
PAGE_SCRIPT = """
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({database!r})

source = Path({page!r})
exec(
    compile(source.read_text(encoding="utf-8"), str(source), "exec"),
    {{"__name__": "__main__"}},
)
"""


def _labels(app: AppTest) -> list[str]:
    """펼침 제목. 아이콘이 달린 펼침을 AppTest 는 `status` 로 센다."""
    return [item.label for item in app.expander] + [item.label for item in app.status]


def _as_person(cfg: SsoConfig, loginid: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    cookies = {} if loginid is None else {cfg.session_cookie: session_token(cfg, loginid)}
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: cookies)


def _admin_app(cfg: SsoConfig, monkeypatch: pytest.MonkeyPatch, loginid: str = ADMIN) -> AppTest:
    _as_person(cfg, loginid, monkeypatch)
    return AppTest.from_string(ADMIN_SCRIPT, default_timeout=30).run()


def _flash_text(app: AppTest) -> str:
    """이번 회차에 표지로 나간 알림 글(알림창 · Alarm)."""
    return " | ".join(str(note.get("full") or note.get("short")) for note in alert_notes(app))


def _button(app: AppTest, key: str) -> Any:
    return app.button(key=key)


def test_with_sso_off_nothing_changes_on_screen(mock_s3: tuple[MockStore, str]) -> None:
    """꺼짐 — 키가 있어도 그리지 않고 S3 에도 가지 않는다(사내 PC · 개발)."""
    store, endpoint = mock_s3
    runtime.reset()
    runtime.start(s3_environ(store, endpoint))

    app = AppTest.from_string(ADMIN_SCRIPT, default_timeout=30).run()

    assert not list(app.exception)
    assert _labels(app) == []
    assert not list(app.main.children.values())
    assert store.requests == []


def test_with_sso_off_the_status_has_no_new_mark() -> None:
    app = AppTest.from_string(STATUS_SCRIPT, default_timeout=30).run()

    assert not list(app.exception)
    assert states(app, "AD-08") == []
    assert _labels(app) == []


def test_with_s3_off_the_admin_box_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = use_config({names.ENV_ACCESS_ADMINS: ADMIN, names.ENV_ACCESS_USERS: USER})

    app = _admin_app(cfg, monkeypatch)

    assert not list(app.exception)
    assert not list(app.main.children.values())


def test_the_admin_page_stays_as_it_was_with_sso_off(tmp_path: Path) -> None:
    script = PAGE_SCRIPT.format(
        database=str(tmp_path / "scenario.duckdb"),
        page=str(PROJECT_ROOT / "app_pages/admin_area.py"),
    )

    app = AppTest.from_string(script).run(timeout=120)

    assert not list(app.exception), [element.message for element in app.exception]
    assert "접속 명단" not in _labels(app)
    assert not any(
        item.key and item.key.startswith("admin_area_access_list") for item in app.button
    )


@pytest.mark.parametrize("loginid", [USER, None], ids=["user", "signed-out"])
def test_someone_who_is_not_an_admin_has_no_place(
    loginid: str | None, mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    _as_person(cfg, loginid, monkeypatch)

    app = AppTest.from_string(ADMIN_SCRIPT, default_timeout=30).run()

    assert not list(app.exception)
    assert not list(app.main.children.values())


def test_the_admin_sees_the_list(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)

    app = _admin_app(cfg, monkeypatch)

    assert not list(app.exception)
    assert _labels(app) == ["접속 명단"]
    frame = app.dataframe[0].value
    assert list(frame.columns) == ["loginid", "넣은 때", "넣은 사람"]
    assert sorted(frame["loginid"].tolist()) == [OTHER, USER]
    assert frame["넣은 사람"].tolist() == [ADMIN, ADMIN]
    assert app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).options
    assert any("판 1 · 사용자 2 · 관리자 1" in str(item.value) for item in app.caption)


def test_an_empty_list_says_so(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)

    app = _admin_app(cfg, monkeypatch)

    assert not list(app.dataframe)
    assert any(item.value == "명단에 사람이 없습니다" for item in app.caption)


def test_the_paste_window_adds_people(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app = _admin_app(cfg, monkeypatch)

    app = _button(app, "admin_area_access_list_open_add").click().run()
    assert any(area.key == access_list_admin.ADD_TEXT_KEY for area in app.text_area)
    app.text_area(key=access_list_admin.ADD_TEXT_KEY).set_value(
        f"loginid\n{OTHER}\t{USER}\n bad\\one \n{GONE}"
    ).run()
    app = next(item for item in app.button if item.label == "명단에 넣기").click().run()

    assert not list(app.exception), [item.message for item in app.exception]
    saved = json.loads(store.objects[OBJECT])
    assert sorted(item["loginid"] for item in saved["users"]) == [GONE, OTHER, USER]
    assert problem_of(cfg, GONE) is None, "재시작 없이 바로 들어온다"
    assert not any(area.key == access_list_admin.ADD_TEXT_KEY for area in app.text_area)
    text = _flash_text(app)
    assert "2명을 넣었습니다" in text and "이미 있음 1" in text and "꼴이 아니라 뺌 1" in text
    assert_absent(text, OTHER, GONE, "bad")


def test_the_paste_window_refuses_nothing_readable(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    app = _admin_app(cfg, monkeypatch)
    app = _button(app, "admin_area_access_list_open_add").click().run()
    app.text_area(key=access_list_admin.ADD_TEXT_KEY).set_value(r"DOMAIN\only").run()

    app = next(item for item in app.button if item.label == "명단에 넣기").click().run()

    assert OBJECT not in store.objects
    assert any(area.key == access_list_admin.ADD_TEXT_KEY for area in app.text_area), "창이 남는다"
    assert "넣을 loginid 가 없습니다" in _flash_text(app)


def test_a_failed_save_in_the_window_tells_why_and_keeps_the_memory(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    store.force["PUT"] = (403, "AccessDenied")
    app = _admin_app(cfg, monkeypatch)
    app = _button(app, "admin_area_access_list_open_add").click().run()
    app.text_area(key=access_list_admin.ADD_TEXT_KEY).set_value(USER).run()

    app = next(item for item in app.button if item.label == "명단에 넣기").click().run()

    assert "인증 거절(HTTP 403 · AccessDenied)" in _flash_text(app)
    assert "명단은 그대로입니다" in _flash_text(app)
    assert problem_of(cfg, USER) is IdentityProblem.DENIED


def test_removing_from_the_screen(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    app = _admin_app(cfg, monkeypatch)

    app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).set_value([USER]).run()
    app = _button(app, "admin_area_access_list_remove_button").click().run()

    assert not list(app.exception), [item.message for item in app.exception]
    assert problem_of(cfg, USER) is IdentityProblem.DENIED
    assert problem_of(cfg, OTHER) is None
    assert app.dataframe[0].value["loginid"].tolist() == [OTHER]
    assert app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).value == []
    assert "1명을 뺐습니다" in _flash_text(app)
    assert_absent(_flash_text(app), USER, OTHER)


def test_removing_with_nothing_chosen_writes_nothing(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app = _admin_app(cfg, monkeypatch)
    before = list(store.requests)

    app = _button(app, "admin_area_access_list_remove_button").click().run()

    assert store.requests == before
    assert "지울 사람을 고르세요" in _flash_text(app)


def test_a_stale_button_of_someone_who_lost_the_right_writes_nothing(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """보인 회차에는 관리자였어도 누른 회차의 쿠키로 다시 본다 — 위젯 콜백이 그 자리에서 막힌다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app = _admin_app(cfg, monkeypatch)
    app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).set_value([USER]).run()
    _as_person(cfg, USER, monkeypatch)
    before = requests_named(store, "PUT")

    app = _button(app, "admin_area_access_list_remove_button").click().run()

    assert not list(app.exception)
    assert requests_named(store, "PUT") == before
    assert problem_of(cfg, USER) is None
    assert "접속 명단" not in _labels(app)


def test_reading_again_from_the_screen(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app = _admin_app(cfg, monkeypatch)
    store.put(OBJECT, file_body(USER, OTHER, revision=4))

    app = _button(app, "admin_area_access_list_reread").click().run()

    assert sorted(app.dataframe[0].value["loginid"].tolist()) == [OTHER, USER]
    assert problem_of(cfg, OTHER) is None
    assert "사용자 2 · 판 4" in _flash_text(app)

    store.force["GET"] = (403, "AccessDenied")
    app = _button(app, "admin_area_access_list_reread").click().run()

    assert "인증 거절(HTTP 403 · AccessDenied)" in _flash_text(app)
    assert sorted(app.dataframe[0].value["loginid"].tolist()) == [OTHER, USER]
    assert problem_of(cfg, OTHER) is None


def test_a_list_that_shrinks_on_reading_again_leaves_no_stale_choice(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    app = _admin_app(cfg, monkeypatch)
    app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).set_value([USER]).run()
    store.put(OBJECT, file_body(OTHER, revision=2))

    app = _button(app, "admin_area_access_list_reread").click().run()

    assert not list(app.exception), [item.message for item in app.exception]
    assert app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).value == []


def test_unread_locks_adding_and_warns_on_the_admin_area(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (403, "AccessDenied")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)

    app = _admin_app(cfg, monkeypatch)

    assert _button(app, "admin_area_access_list_open_add").disabled
    assert any(item.value == "접속 명단 읽지 못함" for item in app.caption)
    status = AppTest.from_string(STATUS_SCRIPT, default_timeout=30).run()
    note = active_state(status, "AD-08")
    assert note is not None
    assert "관리자만 들어옵니다" in note["short"]
    assert "인증 거절(HTTP 403 · AccessDenied)" in note["full"]

    store.force.clear()
    app = _button(app, "admin_area_access_list_reread").click().run()

    assert not _button(app, "admin_area_access_list_open_add").disabled
    status = AppTest.from_string(STATUS_SCRIPT, default_timeout=30).run()
    assert active_state(status, "AD-08") is None
    assert [item["active"] for item in states(status, "AD-08")] == [False]


# --- 점검 줄 -------------------------------------------------------------------------------------


def test_the_check_line_says_off_when_there_is_no_key() -> None:
    cfg = use_config({names.ENV_ACCESS_ADMINS: ADMIN})

    assert sso_status.access_s3_line(cfg) == "S3 명단: 꺼짐"


def test_the_check_line_when_it_can_read(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)

    line = sso_status.access_s3_line(cfg)

    assert line.startswith("S3 명단: 정상 · 마지막 읽기 ")
    assert "사용자 2 · 판 1 · 쓰기: 저장할 때 알게 됨" in line
    assert_absent(line, USER, OTHER, store.access_key, store.secret_key, endpoint, store.bucket)

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[GONE])
    assert "사용자 3 · 판 2 · 쓰기: 정상 · " in sso_status.access_s3_line(cfg)

    store.force["PUT"] = (403, "AccessDenied")
    with pytest.raises(S3Failure):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=[GONE])
    assert "쓰기: 실패 · 인증 거절(HTTP 403 · AccessDenied)" in sso_status.access_s3_line(cfg)


@pytest.mark.parametrize(
    ("force", "text"),
    [
        ((403, "AccessDenied"), "인증 거절(HTTP 403 · AccessDenied)"),
        ((401, "Unauthorized"), "인증 거절(HTTP 401 · Unauthorized)"),
        ((404, "NoSuchBucket"), "버킷 없음(HTTP 404 · NoSuchBucket)"),
        ((503, "SlowDown"), "그 밖의 응답(HTTP 503 · SlowDown)"),
    ],
)
def test_the_check_line_names_each_answer(
    force: tuple[int, str], text: str, mock_s3: tuple[MockStore, str]
) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = force
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)

    line = sso_status.access_s3_line(cfg)

    assert line.startswith(f"S3 명단: 실패 · {text} · 시도 ")
    assert "마지막 읽기 없음 · 관리자만 들어옴" in line
    assert_absent(line, store.access_key, store.secret_key, endpoint)


def test_the_check_line_for_a_timeout_a_closed_port_and_a_broken_file(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    store.delay_seconds = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.1)
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    assert sso_status.access_s3_line(cfg).startswith("S3 명단: 실패 · 시간 초과 · ")

    store.delay_seconds = 0.0
    store.put(OBJECT, b"not json")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    assert sso_status.access_s3_line(cfg).startswith("S3 명단: 실패 · 파일 깨짐 · ")

    closed, closed_endpoint = start_mock(store)
    closed.shutdown()
    closed.server_close()
    cfg = s3_config(store, closed_endpoint)
    access_store.read_at_start(cfg)
    assert sso_status.access_s3_line(cfg).startswith("S3 명단: 실패 · 주소에 닿지 못함 · ")


def test_the_check_line_keeps_the_last_good_read_after_a_failure(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.force["GET"] = (503, "SlowDown")

    access_store.reread(cfg, identity_of(cfg, ADMIN))

    line = sso_status.access_s3_line(cfg)
    assert line.startswith("S3 명단: 실패 · 그 밖의 응답(HTTP 503 · SlowDown) · 시도 ")
    assert " · 마지막 읽기 " in line and "사용자 1 · 판 1" in line


def test_the_check_line_says_it_waits_for_sso(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    runtime.reset()
    cfg = runtime.start(s3_environ(store, endpoint))

    assert sso_status.access_s3_line(cfg) == "S3 명단: 통합인증이 켜지면 적용"


def test_the_status_panel_shows_the_line_and_only_names(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])
    runtime.mark_gate_installed()

    app = AppTest.from_string(STATUS_SCRIPT, default_timeout=30).run()

    assert not list(app.exception)
    captions = "\n".join(str(item.value) for item in app.caption)
    assert "S3 명단: 정상" in captions
    assert "접속 명단: 켜짐 · 관리자 1 · 사용자 2 · 읽지 못함 0" in captions
    table = app.dataframe[0].value.set_index("환경변수")
    assert table.loc[names.ENV_S3_SECRET_KEY, "상태"] == "있음"
    frames = "\n".join(frame.value.to_csv() for frame in app.dataframe)
    assert_absent(
        captions + frames,
        USER,
        OTHER,
        store.access_key,
        store.secret_key,
        endpoint,
    )


# --- 값 비노출 -----------------------------------------------------------------------------------


def test_no_value_leaves_through_events_logs_or_a_repr(
    mock_s3: tuple[MockStore, str], capsys: pytest.CaptureFixture[str]
) -> None:
    store, endpoint = mock_s3
    runtime.reset()
    store.put(OBJECT, file_body(USER))
    from sso_support import sso_environ

    cfg = runtime.start(sso_environ(s3_environ(store, endpoint)))
    access_store.read_at_start(cfg)
    identity = identity_of(cfg, ADMIN)
    access_store.save_changes(cfg, identity, add=[OTHER])
    store.force["PUT"] = (403, "AccessDenied")
    with pytest.raises(S3Failure):
        access_store.save_changes(cfg, identity, remove=[OTHER])

    logged = capsys.readouterr().out
    fields = " ".join(str(item.fields) for item in runtime.recent_events())
    source = runtime.access_source()
    assert source is not None
    texts = logged + fields + repr(source) + repr(source.document) + repr(cfg)
    assert_absent(texts, USER, OTHER, store.access_key, store.secret_key)
    assert "access_read" in logged and "access_saved" in logged
    assert "access_save_failed" in logged


# --- 가짜 S3 의 문 ------------------------------------------------------------------------------


def test_the_mock_store_refuses_outside_loopback(capsys: pytest.CaptureFixture[str]) -> None:
    assert s3_mock_store.main(["--host", "0.0.0.0"]) == s3_mock_store.REFUSED
    assert "루프백" in capsys.readouterr().err


def test_the_mock_store_refuses_an_env_file_inside_the_tree(
    capsys: pytest.CaptureFixture[str],
) -> None:
    inside = PROJECT_ROOT / "s3-dev.env"

    assert s3_mock_store.main(["--env-out", str(inside)]) == s3_mock_store.REFUSED
    assert not inside.exists()


def test_the_mock_store_gives_env_lines_the_config_accepts() -> None:
    store = MockStore()
    lines = s3_mock_store.env_lines(store, "http://127.0.0.1:8607")

    values = dict(line.split("=", 1) for line in lines)
    cfg = load_config(
        {name: value.strip("'") for name, value in values.items()}
        | {names.ENV_ACCESS_ADMINS: ADMIN}
    )

    assert cfg.access_s3 is not None
    assert cfg.access_s3.bucket == store.bucket
