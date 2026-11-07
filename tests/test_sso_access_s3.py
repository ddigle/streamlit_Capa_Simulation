# Purpose: S3 접속 명단의 서명·경계·파일 꼴·합성·장애·자가 회복·저장·Admin 화면·값 비노출을 지킨다.

"""S3 명단(`io/s3_small` · `auth/access_store` · `components/access_list_admin`).

앱 시작에 받아 메모리에 올리고, 판정은 메모리로, 고침은 S3 저장 뒤 메모리로 간다. 저장소는 서명을
검증하는 가짜 S3(`scripts/s3_mock_store.py`)이고 값은 모두 합성(`demo.*`)이다. 서명은 AWS 문서의
알려진 벡터로 고정한 뒤, 가짜 S3 가 받은 요청 그대로 다시 지어 본다(주소 인코딩 · 서명한 머리 ·
본문 지문).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from alert_marks import active_state, alert_notes, states
from asgi_driver import http, websocket_talk
from child_env import narrow_child_env
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
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
# AWS 문서 「Signature Calculations」 의 예시 값이다(실제 키가 아니다). 비밀 탐지기의 오탐으로
# 푸시가 막히지 않게 나눠 적는다.
EXAMPLE_ACCESS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
EXAMPLE_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfi" + "CYEXAMPLEKEY"
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
    """명단 파일을 두고 진입 파일처럼 기동한다(읽기까지). 파일이 있으면 표지도 있는 평상 꼴이다."""
    if loginids:
        store.put(OBJECT, file_body(*loginids))
        store.put(names.ACCESS_SEEDED_OBJECT, b'{"format": 1}')
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


def reads_of_the_list(store: MockStore) -> int:
    return store.requests.count(("GET", f"/{store.bucket}/{OBJECT}"))


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
        env=narrow_child_env({"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": ""}),
    )

    assert found.stdout.strip() == "[]"


@pytest.fixture()
def tls_s3(tmp_path: Path) -> Iterator[tuple[MockStore, str, Path]]:
    """TLS 로 받는 가짜 S3 — (저장소, 주소, 합성 자체서명 인증서 파일)."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "store.example.invalid")])
    now = dt.datetime.now(dt.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "store-cert.pem"
    key_path = tmp_path / "store-key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    store = MockStore()
    server, endpoint = start_mock(store)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    yield store, endpoint.replace("http://", "https://"), cert_path
    server.shutdown()
    server.server_close()


def test_the_https_path_goes_round_with_a_trusted_certificate(
    tls_s3: tuple[MockStore, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """소켓 겉은 TLS 소켓에서도 같다 — `Connection: close` 답의 본문까지 받는다."""
    store, endpoint, certificate = tls_s3
    monkeypatch.setenv("SSL_CERT_FILE", str(certificate))
    target = target_of(store, endpoint)

    etag = s3_small.put_object(target, OBJECT, file_body(USER))

    found = s3_small.get_object(target, OBJECT)
    assert found is not None and found.body == file_body(USER) and found.etag == etag
    assert s3_small.head_object(target, OBJECT) == etag


def test_an_untrusted_certificate_is_a_tls_failure(tls_s3: tuple[MockStore, str, Path]) -> None:
    store, endpoint, _ = tls_s3

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert caught.value.kind == s3_small.KIND_TLS
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert store.requests == []


@contextmanager
def drip_store(pieces: list[bytes], interval: float) -> Iterator[S3Target]:
    """요청을 받으면 `pieces` 를 조금씩 흘리는 저장소 — 소켓 호출마다의 제한은 넘지 않는다."""
    listener = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()

    def serve() -> None:
        connection, _ = listener.accept()
        with connection:
            connection.recv(65536)
            for piece in pieces:
                if stop.wait(interval):
                    return
                try:
                    connection.sendall(piece)
                except OSError:
                    return

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield S3Target(
            endpoint_url=f"http://127.0.0.1:{listener.getsockname()[1]}",
            bucket="b",
            region="us-east-1",
            access_key="k",
            secret_key="s",
        )
    finally:
        stop.set()
        listener.close()
        worker.join(timeout=5)


@pytest.mark.parametrize(
    "pieces",
    [
        [b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n"] + [b"x"] * 200,
        [b"HTTP/1.1 200 OK\r\n"] + [b"X-Drip: 1\r\n"] * 200,
        [b"HTTP/1.1 100 Continue\r\n\r\n"] * 200,
    ],
    ids=["body", "head", "continue"],
)
def test_an_answer_dripping_below_the_read_limit_stops_at_the_deadline(
    pieces: list[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """재는 것은 요청 전체다 — 5초 안쪽으로 조금씩 흘려도 기동 · 콜백을 묶지 못한다."""
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(s3_small, "REQUEST_DEADLINE_SECONDS", 0.5)

    with drip_store(pieces, 0.05) as target:
        begun = time.monotonic()
        with pytest.raises(S3Failure) as caught:
            s3_small.get_object(target, OBJECT)
        spent = time.monotonic() - begun

    assert caught.value.kind == s3_small.KIND_TIMEOUT
    assert spent < 1.5


def test_every_address_shares_one_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """이름이 주소 여럿으로 풀려도 연결 제한이 주소 수만큼 곱해지지 않는다."""

    class Silent:
        """연결 제한까지 답이 없는 소켓."""

        def __init__(self, *_args: Any) -> None:
            self.limit = 0.0

        def settimeout(self, value: float) -> None:
            self.limit = value

        def connect(self, _address: Any) -> None:
            time.sleep(self.limit)
            raise TimeoutError

        def close(self) -> None:
            pass

    address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 9020))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [address] * 6)
    monkeypatch.setattr(socket, "socket", Silent)
    monkeypatch.setattr(s3_small, "CONNECT_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(s3_small, "REQUEST_DEADLINE_SECONDS", 0.5)
    target = S3Target(
        endpoint_url="http://store.example.invalid:9020",
        bucket="b",
        region="us-east-1",
        access_key="k",
        secret_key="s",
    )

    begun = time.monotonic()
    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target, OBJECT)

    assert caught.value.kind == s3_small.KIND_TIMEOUT
    assert time.monotonic() - begun < 0.9


def test_a_name_that_took_past_the_deadline_goes_no_further(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """이름 풀기 자체는 끊지 못해도(표준 라이브러리에 제한이 없다) 그 뒤로 더 쓰지 않는다."""
    store, endpoint = mock_s3
    real = socket.getaddrinfo

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", slow)
    monkeypatch.setattr(s3_small, "REQUEST_DEADLINE_SECONDS", 0.2)

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert caught.value.kind == s3_small.KIND_TIMEOUT
    assert store.requests == []


def test_a_failure_carries_no_chain_back_to_the_signed_header() -> None:
    """머리 글이 예외 사슬에 남지 않는다 — 인코딩 오류의 글에는 키 · 서명 자리가 그대로 있다."""
    target = S3Target(
        endpoint_url="http://127.0.0.1:9",
        bucket="b",
        region="서울",
        access_key="DEMO-ACCESS-KEY-0001",
        secret_key="s",
    )

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target, OBJECT)

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_a_broken_file_carries_no_chain_back_to_its_text() -> None:
    """JSON 오류는 문서 전체(`doc` — 실제 loginid)를 든다 — 사슬에 남기지 않는다."""
    with pytest.raises(S3Failure) as caught:
        access_store.parse_document(b'{"users": ["demo.user"')

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "answer",
    [
        (404, b"<html><body>Not Found</body></html>"),
        (404, b""),
        (404, b"<?xml version='1.0'?><Error><Code>NoSuchThing</Code></Error>"),
    ],
    ids=["html", "empty", "other-code"],
)
def test_a_404_that_does_not_say_no_such_key_is_a_failure(
    answer: tuple[int, bytes], mock_s3: tuple[MockStore, str]
) -> None:
    """저장소 앞단의 404 는 「파일 없음」 이 아니다."""
    store, endpoint = mock_s3
    store.raw["GET"] = answer

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target_of(store, endpoint), OBJECT)

    assert (caught.value.kind, caught.value.status) == (s3_small.KIND_OTHER, 404)


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


def test_a_number_too_long_to_read_is_a_broken_file() -> None:
    """`json.loads` 가 `JSONDecodeError` 아닌 `ValueError` 를 내는 값 — 정수 자릿수 상한."""
    body = b'{"format": 1, "revision": ' + b"1" * 5000 + b', "users": []}'

    with pytest.raises(S3Failure) as caught:
        access_store.parse_document(body)

    assert caught.value.kind == access_store.KIND_CORRUPT


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
        "http://저장소.example.invalid",
    ],
)
def test_a_bad_endpoint_is_a_notice_without_its_value(value: str) -> None:
    cfg = load_config(
        {names.ENV_S3_ACCESS_KEY: "k", names.ENV_S3_SECRET_KEY: "s", names.ENV_S3_ENDPOINT: value}
    )

    assert cfg.access_s3 is None
    assert _notice_codes(cfg, names.ENV_S3_ENDPOINT) == ["s3_bad"]


@pytest.mark.parametrize("value", ["한글키", "with space", "tab\tkey"])
@pytest.mark.parametrize("name", [names.ENV_S3_ACCESS_KEY, names.ENV_S3_SECRET_KEY])
def test_a_key_of_another_shape_is_a_notice_without_its_value(name: str, value: str) -> None:
    base = {
        names.ENV_S3_ACCESS_KEY: "k",
        names.ENV_S3_SECRET_KEY: "s",
        names.ENV_S3_ENDPOINT: "http://127.0.0.1:8607",
        names.ENV_S3_BUCKET: "b",
    }

    cfg = load_config({**base, name: value})

    assert cfg.access_s3_requested and cfg.access_s3 is None
    assert _notice_codes(cfg, name) == ["s3_bad"]
    assert value not in repr(cfg)


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


@pytest.mark.parametrize("region", ["서울", "ap demo 1"])
def test_a_region_that_cannot_go_in_a_header_is_a_notice_without_its_value(region: str) -> None:
    """영역은 서명 머리에 그대로 들어간다 — 요청도 나가기 전에 「주소에 닿지 못함」 이 되지 않게."""
    cfg = load_config(
        {
            names.ENV_S3_ACCESS_KEY: "k",
            names.ENV_S3_SECRET_KEY: "s",
            names.ENV_S3_ENDPOINT: "http://127.0.0.1:8607",
            names.ENV_S3_BUCKET: "b",
            names.ENV_S3_REGION: region,
        }
    )

    assert cfg.access_s3_requested and cfg.access_s3 is None
    assert _notice_codes(cfg, names.ENV_S3_REGION) == ["s3_bad"]
    assert region not in repr(cfg)


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
    assert before == [
        ("GET", f"/{store.bucket}/{OBJECT}"),
        ("GET", f"/{store.bucket}/{names.ACCESS_SEEDED_OBJECT}"),
    ]


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


def test_a_file_nested_too_deep_is_broken_not_a_crash() -> None:
    with pytest.raises(S3Failure) as caught:
        access_store.parse_document(b"[" * 200_000)

    assert caught.value.kind == access_store.KIND_CORRUPT


def test_an_address_that_cannot_be_encoded_is_unreachable_not_a_crash() -> None:
    target = S3Target(
        endpoint_url=f"http://{'a' * 70}.example.invalid",
        bucket="b",
        region="us-east-1",
        access_key="k",
        secret_key="s",
    )

    with pytest.raises(S3Failure) as caught:
        s3_small.get_object(target, OBJECT)

    assert caught.value.kind == s3_small.KIND_UNREACHABLE


def test_no_failure_of_the_read_can_stop_the_start(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = s3_config(store, endpoint)

    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise LookupError("예상하지 못한 실패")

    monkeypatch.setattr(access_store, "get_object", explode)

    access_store.read_at_start(cfg)

    source = runtime.access_source()
    assert source is not None and source.problem is not None
    assert (source.problem.kind, source.problem.code) == (s3_small.KIND_OTHER, "LookupError")
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


@pytest.mark.parametrize(
    "answer",
    [
        (404, b"<?xml version='1.0'?><Error><Code>NoSuchKey</Code></Error>"),
        (404, b"<html><body>Not Found</body></html>"),
        (404, b""),
    ],
    ids=["no-such-key", "html", "empty"],
)
def test_a_404_after_a_good_read_does_not_empty_the_list(
    answer: tuple[int, bytes], mock_s3: tuple[MockStore, str]
) -> None:
    """읽어 둔 파일이 404 로 보여도 메모리 명단을 지우지 않는다 — 그것이 마지막 사본일 수 있다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.raw["GET"] = answer
    identity = identity_of(cfg, ADMIN)

    problem = access_store.reread(cfg, identity)

    assert problem is not None and problem.status == 404
    assert problem_of(cfg, USER) is None, "메모리 명단으로 판정이 이어진다"
    source = runtime.access_source()
    assert source is not None and source.document is not None
    assert source.document.revision == 1
    assert sso_status.access_s3_line(cfg).startswith("S3 명단: 실패 · ")

    store.raw.clear()
    assert access_store.reread(cfg, identity) is None
    assert sso_status.access_s3_line(cfg).startswith("S3 명단: 정상 · ")


def test_a_file_really_deleted_after_a_good_read_says_so_and_keeps_the_list(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    del store.objects[OBJECT]

    problem = access_store.reread(cfg, identity_of(cfg, ADMIN))

    assert problem is not None and problem.kind == access_store.KIND_FILE_GONE
    assert problem_of(cfg, USER) is None
    assert "파일 없음(HTTP 404 · NoSuchKey)" in sso_status.access_s3_line(cfg)


def test_a_file_saved_after_starting_empty_is_kept_the_same_way(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    identity = identity_of(cfg, ADMIN)
    access_store.save_changes(cfg, identity, add=[USER])
    del store.objects[OBJECT]

    assert access_store.reread(cfg, identity) is not None

    assert problem_of(cfg, USER) is None


def test_reading_again_with_still_no_file_stays_an_empty_list(
    mock_s3: tuple[MockStore, str],
) -> None:
    """받아 둔 파일이 없었으면 404 는 그대로 빈 명단이다 — 첫 파일을 올리기 전의 서버."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint)

    assert access_store.reread(cfg, identity_of(cfg, ADMIN)) is None

    source = runtime.access_source()
    assert source is not None and source.problem is None
    assert not access_store.is_unread(cfg)


@pytest.mark.parametrize(
    "answer",
    [(404, b"<html><body>Not Found</body></html>"), (404, b"")],
    ids=["html", "empty"],
)
def test_a_404_from_the_front_at_start_is_unread_and_heals_by_itself(
    answer: tuple[int, bytes], mock_s3: tuple[MockStore, str]
) -> None:
    """기동 때 앞단의 404 — 정상 · 사용자 0 으로 서지 않고 「못 읽음」 이라 스스로 회복한다."""
    store, endpoint = mock_s3
    store.put(OBJECT, file_body(USER))
    store.raw["GET"] = answer
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)

    assert access_store.is_unread(cfg)
    assert sso_status.access_s3_line(cfg).startswith("S3 명단: 실패 · 그 밖의 응답(HTTP 404")
    assert problem_of(cfg, USER) is IdentityProblem.DENIED

    store.raw.clear()
    rewind_attempt(access_store.RETRY_SECONDS)

    assert has_live_session(cfg, sign_in(gated_app(), {}, USER))
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

    assert reads_of_the_list(store) == 1
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
    assert reads_of_the_list(store) == 2


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


def test_retries_of_someone_denied_do_not_push_out_the_audit_ring(
    mock_s3: tuple[MockStore, str],
) -> None:
    """못 읽은 동안 거절이 되풀이돼도 유일한 감사 창이 자가 회복 실패로 차지 않는다."""
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)
    runtime.record_event("login_ok", loginid=ADMIN)
    app = gated_app()

    for _ in range(3):
        rewind_attempt(access_store.RETRY_SECONDS)
        assert error_code_of(sign_in(app, {}, USER)) == "not_on_list"
    begun = int(time.time())
    for step in range(runtime.MAX_EVENTS + 10):
        access_store.retry_unread(cfg, now=begun + (step + 1) * access_store.RETRY_SECONDS)

    assert requests_named(store, "GET") == 1 + 3 + runtime.MAX_EVENTS + 10
    assert events_named("login_ok"), "앞선 사건이 남는다"
    assert len(events_named("access_read")) == 1, "기동 때의 한 줄만"
    assert f"자가 회복 실패 {3 + runtime.MAX_EVENTS + 10}" in sso_status.access_s3_line(cfg)


def test_reading_again_by_hand_and_a_good_retry_stay_in_the_ring(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    store.force["GET"] = (503, "SlowDown")
    store.put(OBJECT, file_body(USER))
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)

    assert access_store.reread(cfg, identity_of(cfg, ADMIN)) is not None
    assert len(events_named("access_read")) == 2, "관리자의 다시 읽기는 고리에 남는다"

    store.force.clear()
    rewind_attempt(access_store.RETRY_SECONDS)
    access_store.retry_unread(cfg)

    assert not access_store.is_unread(cfg)
    assert events_named("access_read")[0].value("users") == "1"
    assert "자가 회복 실패" not in sso_status.access_s3_line(cfg)


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

    assert seen and not any(seen), "거절 직전의 다시 읽기는 스레드 풀에서 돈다"


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


def test_a_put_with_no_answer_is_unconfirmed_and_a_refused_one_is_not(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """답을 받지 못한 PUT 은 저장소에 들어갔는지 모른다 — 거절된 PUT 과 가른다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    identity = identity_of(cfg, ADMIN)
    store.answer_delay["PUT"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(access_store.SaveUnconfirmedError) as caught:
        access_store.save_changes(cfg, identity, add=[OTHER])

    assert caught.value.kind == s3_small.KIND_TIMEOUT
    assert OTHER in store.objects[OBJECT].decode(), "저장소에는 들어갔다"
    assert problem_of(cfg, OTHER) is IdentityProblem.DENIED, "메모리는 그대로다"
    assert "쓰기: 결과 모름 · 시간 초과" in sso_status.access_s3_line(cfg)

    store.answer_delay.clear()
    with pytest.raises(access_store.StoreConflictError):
        access_store.save_changes(cfg, identity, add=[GONE])
    assert access_store.reread(cfg, identity) is None
    assert problem_of(cfg, OTHER) is None, "다시 읽으면 들어간 것이 보인다"
    assert "결과 모름" not in sso_status.access_s3_line(cfg)

    store.force["PUT"] = (403, "AccessDenied")
    with pytest.raises(S3Failure) as refused:
        access_store.save_changes(cfg, identity, add=[GONE])
    assert not isinstance(refused.value, access_store.SaveUnconfirmedError)
    assert "쓰기: 실패 · 인증 거절" in sso_status.access_s3_line(cfg)


def test_a_check_that_timed_out_before_the_put_left_the_file_alone(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """저장 전 대조에서 끊겼으면 PUT 은 나가지 않았다 — 「모른다」 가 아니다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    identity = identity_of(cfg, ADMIN)
    store.answer_delay["HEAD"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(S3Failure) as caught:
        access_store.save_changes(cfg, identity, add=[OTHER])

    assert caught.value.kind == s3_small.KIND_TIMEOUT
    assert not isinstance(caught.value, access_store.SaveUnconfirmedError)
    assert requests_named(store, "PUT") == 0


def test_a_good_save_clears_the_read_failure(mock_s3: tuple[MockStore, str]) -> None:
    """방금 쓴 명단인데 「읽지 못했다 · 지난 명단」 이 남지 않는다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    identity = identity_of(cfg, ADMIN)
    store.force["GET"] = (503, "SlowDown")
    assert access_store.reread(cfg, identity) is not None
    store.force.clear()

    access_store.save_changes(cfg, identity, add=[OTHER])

    source = runtime.access_source()
    assert source is not None and source.problem is None
    line = sso_status.access_s3_line(cfg)
    assert line.startswith("S3 명단: 정상 · 마지막 읽기 ")
    assert "판 2 · 쓰기: 정상" in line


def test_a_failed_save_leaves_the_read_failure_where_it_was(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    identity = identity_of(cfg, ADMIN)
    store.force["GET"] = (503, "SlowDown")
    access_store.reread(cfg, identity)
    store.force["PUT"] = (403, "AccessDenied")

    with pytest.raises(S3Failure):
        access_store.save_changes(cfg, identity, add=[OTHER])

    source = runtime.access_source()
    assert source is not None and source.problem is not None
    assert source.problem.status == 503


def test_a_number_too_long_on_the_check_before_saving_is_a_failure_not_a_crash(
    mock_s3: tuple[MockStore, str],
) -> None:
    """ETag 를 주지 않는 저장소 — 저장 전 대조가 본문을 읽는 길."""
    store, endpoint = mock_s3
    store.omit_etag = True
    cfg = started(store, endpoint, USER)
    store.put(OBJECT, b'{"format": 1, "revision": ' + b"1" * 5000 + b', "users": []}')

    with pytest.raises(S3Failure) as caught:
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])

    assert caught.value.kind == access_store.KIND_CORRUPT
    assert problem_of(cfg, OTHER) is IdentityProblem.DENIED


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
    assert [item["what"] for item in saved["changes"]] == ["add", "drop_unreadable 2"]


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
        f"loginid\n{OTHER}\n{USER}\n bad\\one \n{GONE}"
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


def test_a_put_with_no_answer_tells_the_admin_to_read_again(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app = _admin_app(cfg, monkeypatch)
    store.answer_delay["PUT"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.2)
    app = _button(app, "admin_area_access_list_open_add").click().run()
    app.text_area(key=access_list_admin.ADD_TEXT_KEY).set_value(OTHER).run()

    app = next(item for item in app.button if item.label == "명단에 넣기").click().run()

    assert not list(app.exception), [item.message for item in app.exception]
    text = _flash_text(app)
    assert "저장됐는지 알 수 없습니다" in text and "시간 초과" in text and "다시 읽기" in text
    assert "그대로입니다" not in text
    assert_absent(text, OTHER)


@pytest.mark.parametrize(
    "kind", [s3_small.KIND_TIMEOUT, s3_small.KIND_UNREACHABLE, s3_small.KIND_TLS]
)
def test_every_failure_without_an_answer_is_unconfirmed(
    kind: str, mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)

    def no_answer(*_args: Any, **_kwargs: Any) -> str:
        raise S3Failure(kind)

    monkeypatch.setattr(access_store, "put_object", no_answer)

    with pytest.raises(access_store.SaveUnconfirmedError) as caught:
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])

    assert "저장됐는지 알 수 없습니다" in access_list_admin.save_failure_message(caught.value)


def test_a_file_too_big_to_send_is_a_plain_failure(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """보내기 전에 멈춘 것 — 저장소는 그대로다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    monkeypatch.setattr(s3_small, "MAX_OBJECT_BYTES", 8)

    with pytest.raises(S3Failure) as caught:
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=[OTHER])

    assert caught.value.kind == s3_small.KIND_TOO_LARGE
    assert "명단은 그대로입니다" in access_list_admin.save_failure_message(caught.value)


def _paste_and_apply(app: AppTest, text: str) -> AppTest:
    app = _button(app, "admin_area_access_list_open_add").click().run()
    app.text_area(key=access_list_admin.ADD_TEXT_KEY).set_value(text).run()
    return next(item for item in app.button if item.label == "명단에 넣기").click().run()


@pytest.mark.parametrize(
    "text",
    [
        f"loginid\t넣은 때\t넣은 사람\n{OTHER}\t11-05 18:15\t{ADMIN}\n{GONE}\t2026-11-05\t{ADMIN}",
        f"넣은 때\tLoginID\n2026-11-05\t{OTHER}\n2026-11-05\t{GONE}",
        f"loginid,넣은 때,넣은 사람\n{OTHER},2026-11-05 18:15,{ADMIN}\n{GONE},2026-11-05,{ADMIN}",
    ],
    ids=["tab", "column-moved", "comma"],
)
def test_a_pasted_table_adds_only_its_loginid_column(
    text: str, mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """다른 칸의 값이 명단에 들어가면 그 값을 가진 사람에게 접속이 열린다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    app = _admin_app(cfg, monkeypatch)

    app = _paste_and_apply(app, text)

    assert not list(app.exception), [item.message for item in app.exception]
    saved = json.loads(store.objects[OBJECT])
    assert sorted(item["loginid"] for item in saved["users"]) == [GONE, OTHER]
    assert "2명을 넣었습니다" in _flash_text(app)


@pytest.mark.parametrize(
    "text",
    [f"{OTHER}\t2026-11-05\t{USER}", f"loginid\n{OTHER}\t{USER}"],
    ids=["no-header", "header-without-cells"],
)
def test_a_table_without_a_loginid_column_is_refused(
    text: str, mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """어느 칸이 사람인지 모르면 넣지 않고 까닭을 알린다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    app = _admin_app(cfg, monkeypatch)

    app = _paste_and_apply(app, text)

    assert OBJECT not in store.objects
    assert problem_of(cfg, OTHER) is IdentityProblem.DENIED
    assert any(area.key == access_list_admin.ADD_TEXT_KEY for area in app.text_area), "창이 남는다"
    assert "loginid 칸" in _flash_text(app)
    assert_absent(_flash_text(app), OTHER, USER)


def test_a_list_with_separators_still_reads_every_entry() -> None:
    assert access_list_admin.pasted_entries(f"loginid\n{OTHER}, {USER};{GONE} bad\\one") == (
        (OTHER, USER, GONE),
        1,
    )


def test_a_short_table_row_is_counted_as_unreadable() -> None:
    assert access_list_admin.pasted_entries(
        f"넣은 때\tloginid\n2026-11-05\n2026-11-05\t{OTHER}"
    ) == (
        (OTHER,),
        1,
    )


@pytest.mark.parametrize(
    "value",
    [
        "0001-01-01T00:00:00+14:00",
        "9999-12-31T23:59:59-14:00",
    ],
)
def test_a_time_past_the_calendar_comes_back_as_it_was(value: str) -> None:
    assert access_list_admin._when_text(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "0001-01-01T00:00:00",
        "0001-01-01T00:00:00+14:00",
        "9999-12-31T23:59:59-14:00",
        "9999-12-31T23:59:59Z",
    ],
)
def test_a_hand_written_time_at_the_edge_does_not_stop_the_admin_screen(
    value: str, mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    store.put(
        OBJECT,
        json.dumps(
            {
                "format": 1,
                "revision": 1,
                "users": [{"loginid": USER, "added_at": value, "added_by": ADMIN}],
            }
        ).encode(),
    )
    cfg = started(store, endpoint)

    app = _admin_app(cfg, monkeypatch)

    assert not list(app.exception), [item.message for item in app.exception]
    assert app.dataframe[0].value["loginid"].tolist() == [USER]


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


def test_a_failed_action_of_the_list_goes_to_the_alert_popup_only(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """다시 읽기 · 지우기의 실패는 곁에 고칠 입력이 없다 — 곁 상자 없이 알림창에만 뜬다(UI-NTF-03).
    고를 사람을 고르지 않은 누름만 곁 칸을 고치는 말이라 곁에 선다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app = _admin_app(cfg, monkeypatch)
    app = _button(app, "admin_area_access_list_remove_button").click().run()
    assert [item.value for item in app.warning] == ["지울 사람을 고르세요"]

    store.force["GET"] = (403, "AccessDenied")
    app = _button(app, "admin_area_access_list_reread").click().run()

    assert not list(app.error), [item.value for item in app.error]
    assert "인증 거절(HTTP 403 · AccessDenied)" in _flash_text(app)

    store.force.clear()
    store.force["PUT"] = (403, "AccessDenied")
    app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).set_value([USER]).run()
    app = _button(app, "admin_area_access_list_remove_button").click().run()

    assert not list(app.error), [item.value for item in app.error]
    assert "S3 에 저장하지 못했습니다" in _flash_text(app)


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


def test_the_read_alert_goes_only_to_those_who_can_act(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """「다시 읽기」 자리가 없는 사람에게 그 단추를 가리키는 조치 알림을 내지 않는다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    store.force["GET"] = (503, "SlowDown")
    access_store.reread(cfg, identity_of(cfg, ADMIN))

    _as_person(cfg, USER, monkeypatch)
    status = AppTest.from_string(STATUS_SCRIPT, default_timeout=30).run()

    assert not list(status.exception)
    assert active_state(status, "AD-08") is None
    assert [item["active"] for item in states(status, "AD-08")] == [False]
    captions = "\n".join(str(item.value) for item in status.caption)
    assert "S3 명단: 실패 · 그 밖의 응답(HTTP 503 · SlowDown)" in captions, "점검 줄은 그대로다"

    _as_person(cfg, ADMIN, monkeypatch)
    status = AppTest.from_string(STATUS_SCRIPT, default_timeout=30).run()

    note = active_state(status, "AD-08")
    assert note is not None and "지난 명단으로 판정합니다" in note["short"]


def test_the_read_alert_is_gone_after_a_good_save(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    identity = identity_of(cfg, ADMIN)
    store.force["GET"] = (503, "SlowDown")
    access_store.reread(cfg, identity)
    store.force.clear()
    access_store.save_changes(cfg, identity, add=[OTHER])

    _as_person(cfg, ADMIN, monkeypatch)
    status = AppTest.from_string(STATUS_SCRIPT, default_timeout=30).run()

    assert active_state(status, "AD-08") is None


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


def test_the_mock_store_refuses_a_seed_that_is_not_synthetic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = s3_mock_store.main(["--port", "0", "--seed-loginid", "real.person"])

    assert code == s3_mock_store.REFUSED
    assert "demo." in capsys.readouterr().err


def test_a_seeded_file_is_read_as_the_list(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.put(OBJECT, s3_mock_store.seed_body([USER, OTHER]))

    cfg = started(store, endpoint)

    assert problem_of(cfg, USER) is None and problem_of(cfg, OTHER) is None
    assert not access_store.is_unread(cfg)


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


# --- 첫 판 --------------------------------------------------------------------------------------


def _seeded(store: MockStore, endpoint: str, *people: str) -> SsoConfig:
    """명단 파일이 없는 저장소에서 시작한 서버 — 환경변수 목록이 첫 판이다."""
    cfg = s3_config(store, endpoint, **{names.ENV_ACCESS_USERS: ",".join(people)})
    access_store.read_at_start(cfg)
    return cfg


def _new_process(store: MockStore, endpoint: str, *people: str) -> SsoConfig:
    """재시작 — 메모리가 비고 환경변수는 그대로다."""
    return _seeded(store, endpoint, *people)


def test_a_missing_file_takes_the_environment_list_as_the_first_version(
    mock_s3: tuple[MockStore, str],
) -> None:
    """키를 넣는 순간 사용자가 모두 막히지 않는다."""
    store, endpoint = mock_s3

    cfg = _seeded(store, endpoint, USER)

    assert problem_of(cfg, USER) is None
    source = runtime.access_source()
    assert source is not None and source.seeded is True
    assert source.problem is None
    assert access_store.holds_a_file() is False


def test_no_environment_list_is_an_empty_list_as_before(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3

    cfg = _seeded(store, endpoint)

    source = runtime.access_source()
    assert source is not None and source.seeded is False
    assert source.problem is None
    assert problem_of(cfg, USER) is not None


def test_the_first_save_writes_the_list_and_the_mark(mock_s3: tuple[MockStore, str]) -> None:
    """첫 판 + 고침이 판 1 이고, 환경변수에서 온 사람은 고친 기록에 수로 남는다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)

    result = access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.added",))

    assert result.revision == 1
    document = access_store.parse_document(store.objects[names.DEFAULT_ACCESS_OBJECT])
    assert {entry.loginid for entry in document.entries} == {USER, "demo.added"}
    assert [change.what for change in document.changes] == ["seed_users 1", "add"]
    assert names.ACCESS_SEEDED_OBJECT in store.objects
    source = runtime.access_source()
    assert source is not None and source.seeded is False
    assert access_store.holds_a_file() is True


def test_after_the_file_exists_the_environment_is_not_listened_to(
    mock_s3: tuple[MockStore, str],
) -> None:
    """Admin 에서 뺀 사람이 환경변수에 남아 있어도 다시 들어오지 못한다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER, "demo.other")
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=(USER,))

    restarted = _new_process(store, endpoint, USER, "demo.other")

    assert problem_of(restarted, USER) is not None
    assert problem_of(restarted, "demo.other") is None


def test_a_file_that_disappears_does_not_bring_the_old_list_back(
    mock_s3: tuple[MockStore, str],
) -> None:
    """새 프로세스는 받아 둔 파일이 메모리에 없다. 표지가 없으면 닫힘이 열림으로 바뀐다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.added",))
    del store.objects[names.DEFAULT_ACCESS_OBJECT]

    restarted = _new_process(store, endpoint, USER)

    assert problem_of(restarted, USER) is not None
    assert problem_of(restarted, ADMIN) is None
    source = runtime.access_source()
    assert source is not None and source.problem is not None
    assert source.problem.kind == access_store.KIND_FILE_GONE


def test_a_list_that_cannot_be_read_still_admits_only_admins(
    mock_s3: tuple[MockStore, str],
) -> None:
    """못 읽은 것은 없는 것이 아니다 — 첫 판을 쓰지 않는다."""
    store, endpoint = mock_s3
    store.force["GET"] = (403, "AccessDenied")

    cfg = _seeded(store, endpoint, USER)

    assert problem_of(cfg, USER) is not None
    assert problem_of(cfg, ADMIN) is None


def test_a_404_without_no_such_key_is_not_a_first_version(mock_s3: tuple[MockStore, str]) -> None:
    """저장소 앞단의 HTML 404 를 「파일 없음」 으로 읽으면 멀쩡한 파일을 두고 첫 판으로 선다."""
    store, endpoint = mock_s3
    store.raw["GET"] = (404, b"<html>not found</html>")

    cfg = _seeded(store, endpoint, USER)

    assert problem_of(cfg, USER) is not None


def test_a_broken_file_is_not_a_first_version(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    store.objects[names.DEFAULT_ACCESS_OBJECT] = b"{ broken"

    cfg = _seeded(store, endpoint, USER)

    assert problem_of(cfg, USER) is not None


def test_a_failed_mark_is_written_by_the_next_save(mock_s3: tuple[MockStore, str]) -> None:
    """명단은 이미 들어갔다 — 저장 실패가 아니다. 표지만 다음 저장이 다시 쓴다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)
    target = cfg.access_s3
    assert target is not None
    original = s3_small.put_object
    calls: list[str] = []

    def refuse_the_mark(where: S3Target, key: str, body: bytes, *, moment: float) -> str:
        calls.append(key)
        if key == names.ACCESS_SEEDED_OBJECT and len(calls) == 2:
            raise S3Failure(s3_small.KIND_TIMEOUT)
        return original(where, key, body, moment=moment)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(access_store, "put_object", refuse_the_mark)
        result = access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.added",))
        assert result.revision == 1
        assert names.ACCESS_SEEDED_OBJECT not in store.objects
        source = runtime.access_source()
        assert source is not None and source.seed_mark_pending is True

        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.more",))

    assert names.ACCESS_SEEDED_OBJECT in store.objects
    source = runtime.access_source()
    assert source is not None and source.seed_mark_pending is False


def _file_is_gone_after_restart(store: MockStore, endpoint: str, *people: str) -> SsoConfig:
    """파일이 사라진 뒤 재시작한 서버. 빠진 사람이 환경변수에 남아 있어도 첫 판이면 안 된다."""
    del store.objects[names.DEFAULT_ACCESS_OBJECT]
    restarted = _new_process(store, endpoint, *people)
    source = runtime.access_source()
    assert source is not None and source.seeded is False
    assert source.problem is not None
    assert source.problem.kind == access_store.KIND_FILE_GONE
    return restarted


def test_a_first_save_with_no_answer_leaves_the_mark_once_read_again(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """파일은 들어갔는데 답이 끊겼다. 다시 읽은 뒤에는 첫 판이 아니다 — 표지도 있어야 한다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER, OTHER)
    identity = identity_of(cfg, ADMIN)
    store.answer_delay["PUT"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(access_store.SaveUnconfirmedError):
        access_store.save_changes(cfg, identity, remove=[OTHER])
    store.answer_delay.clear()
    assert access_store.reread(cfg, identity) is None

    assert names.ACCESS_SEEDED_OBJECT in store.objects
    restarted = _file_is_gone_after_restart(store, endpoint, USER, OTHER)
    assert problem_of(restarted, OTHER) is not None


def test_a_mark_that_failed_is_left_by_the_next_start(mock_s3: tuple[MockStore, str]) -> None:
    """남은 표지는 메모리뿐이라 재시작에 사라진다. 파일을 받은 읽기가 다시 쓴다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER, OTHER)
    store.force_on("PUT", names.ACCESS_SEEDED_OBJECT)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=[OTHER])
    assert names.ACCESS_SEEDED_OBJECT not in store.objects

    _new_process(store, endpoint, USER, OTHER)

    assert names.ACCESS_SEEDED_OBJECT in store.objects
    restarted = _file_is_gone_after_restart(store, endpoint, USER, OTHER)
    assert problem_of(restarted, OTHER) is not None


def test_a_first_file_made_without_an_environment_list_leaves_the_mark(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint)

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=(USER,))

    assert names.ACCESS_SEEDED_OBJECT in store.objects
    _file_is_gone_after_restart(store, endpoint, USER)


def test_a_file_without_a_mark_gets_one_when_it_is_read(mock_s3: tuple[MockStore, str]) -> None:
    """앞 코드가 만든 파일 · 옮긴 버킷의 파일 — 「파일이 있으면 표지도 있다」 로 맞춘다."""
    store, endpoint = mock_s3
    store.put(OBJECT, file_body(USER))
    cfg = s3_config(store, endpoint)

    access_store.read_at_start(cfg)

    assert names.ACCESS_SEEDED_OBJECT in store.objects
    assert problem_of(cfg, USER) is None
    source = runtime.access_source()
    assert source is not None and source.seed_mark_pending is False


def test_a_mark_that_cannot_be_written_on_reading_does_not_fail_the_read(
    mock_s3: tuple[MockStore, str],
) -> None:
    """표지는 판정을 막지 못한다. 쓰기 권한이 없는 키로도 명단은 읽힌다."""
    store, endpoint = mock_s3
    store.put(OBJECT, file_body(USER))
    store.force["PUT"] = (403, "AccessDenied")
    cfg = s3_config(store, endpoint)

    access_store.read_at_start(cfg)

    assert problem_of(cfg, USER) is None
    source = runtime.access_source()
    assert source is not None and source.problem is None
    assert source.seed_mark_pending is True


def test_a_file_that_already_has_a_mark_writes_nothing_on_reading(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3

    started(store, endpoint, USER)

    assert requests_named(store, "PUT") == 0


def test_a_bare_404_on_a_head_does_not_open_the_first_version(
    mock_s3: tuple[MockStore, str],
) -> None:
    """HEAD 는 본문이 없어 `NoSuchKey` 를 가르지 못한다. 표지는 GET 으로 본다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER, OTHER)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), remove=[OTHER])
    store.raw["HEAD"] = (404, b"")

    restarted = _file_is_gone_after_restart(store, endpoint, USER, OTHER)

    assert problem_of(restarted, OTHER) is not None


def test_a_404_from_the_front_on_the_mark_is_not_a_first_version(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    store.force_on("GET", names.ACCESS_SEEDED_OBJECT, status=404, code="NotThere")

    cfg = _seeded(store, endpoint, USER)

    assert problem_of(cfg, USER) is not None
    source = runtime.access_source()
    assert source is not None and source.seeded is False and source.problem is not None


def test_a_server_that_dropped_the_environment_list_still_sees_the_file_gone(
    mock_s3: tuple[MockStore, str],
) -> None:
    """권장대로 환경변수를 지운 뒤 — 「정상 · 판 0」 으로 조용히 전원 거절이면 까닭을 못 찾는다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.added",))

    restarted = _file_is_gone_after_restart(store, endpoint)

    assert "실패 · 파일 없음" in sso_status.access_s3_line(restarted)
    assert problem_of(restarted, ADMIN) is None


def test_a_failed_save_leaves_the_first_version_in_place(mock_s3: tuple[MockStore, str]) -> None:
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)
    store.force["PUT"] = (403, "AccessDenied")

    with pytest.raises(S3Failure):
        access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.added",))

    assert problem_of(cfg, USER) is None
    assert problem_of(cfg, "demo.added") is not None
    source = runtime.access_source()
    assert source is not None and source.seeded is True
    assert names.ACCESS_SEEDED_OBJECT not in store.objects


def test_the_first_version_shows_in_the_line_and_the_notice_stays_away(
    mock_s3: tuple[MockStore, str],
) -> None:
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)

    assert "환경변수 첫 판 · 파일 없음" in sso_status.access_s3_line(cfg)
    assert "쓰지 않음" not in sso_status.environment_table(cfg).to_csv()

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.added",))

    assert "환경변수 첫 판" not in sso_status.access_s3_line(cfg)
    assert "쓰지 않음" in sso_status.environment_table(cfg).to_csv()


def test_the_seed_never_reaches_a_repr(mock_s3: tuple[MockStore, str]) -> None:
    """명단 값은 사람을 가리킨다 — repr · 로그에 실리지 않는다."""
    store, endpoint = mock_s3
    cfg = s3_config(store, endpoint, **{names.ENV_ACCESS_USERS: USER})

    assert cfg.access_seed_users == (USER,)
    assert USER not in repr(cfg)
    assert USER not in repr(access_store._seed_document(cfg))


def test_the_first_version_raises_a_check_alert(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """파일이 없는 동안은 환경변수로 판정한다 — 첫 저장 전까지 그 사실을 알린다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)
    _as_person(cfg, ADMIN, monkeypatch)

    app = AppTest.from_string(STATUS_SCRIPT).run()
    assert active_state(app, "AD-09")

    access_store.save_changes(cfg, identity_of(cfg, ADMIN), add=("demo.added",))

    app.run()
    assert not active_state(app, "AD-09")


def test_the_first_version_alert_goes_only_to_those_who_can_act(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """「접속 명단」 펼침은 관리자에게만 있다. 사실은 「S3 명단」 줄이 그대로 말한다."""
    store, endpoint = mock_s3
    cfg = _seeded(store, endpoint, USER)
    _as_person(cfg, USER, monkeypatch)

    app = AppTest.from_string(STATUS_SCRIPT).run()

    assert not active_state(app, "AD-09")
