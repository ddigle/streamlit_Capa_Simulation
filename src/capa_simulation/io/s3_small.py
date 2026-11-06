# Purpose: S3 호환 저장소의 작은 객체 하나를 표준 라이브러리만으로 받고·올리고·머리만 본다(SigV4).

"""작은 객체 경계.

DuckDB 스냅샷처럼 큰 파일은 `io/object_storage.py`(`aws` CLI) 몫이고, 여기는 접속 명단 파일처럼 몇
KiB 짜리 객체 하나를 앱 프로세스가 직접 주고받는 자리다. 따로 둔 까닭은 판정을 다시 읽는 콜백
자리에서 `aws` 프로세스를 띄우지 않고, 프로필 없이 환경변수 키로 붙고, 의존성을 늘리지 않으려는
것이다.

- **표준 라이브러리만** 쓴다 — `auth` 가 import 해도 Streamlit · 무거운 모듈이 딸려 오지 않는다.
- **경로 스타일 주소**(`/<버킷>/<키>`) — 버킷 이름에 대문자 · 밑줄이 있어 가상 호스트로 적지 못한다.
- **시간 제한** 연결 3초 · 읽기 5초 · 요청 전체 8초. 소켓 호출마다의 제한만 두면 조금씩 흘리는 답 ·
  주소 여럿이 제한을 곱해 기동 · 콜백을 묶으므로, 연결 · 머리 · 본문 · 100 Continue 를 모두 한
  마감에 맞춘다(`_DeadlineSocket`). **이름 풀기만 끊지 못한다** — 표준 라이브러리에 제한 인자가 없고
  끊으려면 스레드가 필요하다(AGENTS 9장). 풀린 뒤에 마감이 지났으면 더 가지 않는다. 재시도는 없다
  (부르는 쪽 몫).
- **프록시 · 리다이렉트를 따르지 않는다** — 환경변수 프록시를 지나면 명단이 그 프록시에 보이고
  그쪽 403 이 저장소의 인증 거절로 읽힌다. 3xx 는 그 밖 응답으로 올린다.
- **조건부 쓰기(`If-Match`)를 보내지 않는다** — 확인하지 못한 능력은 없는 것으로 본다
  (`docs/objectstore_setup.md` 2단계). 덮어쓰기 막기는 부르는 쪽이 `head_object` 로 한다.
- 실패는 `S3Failure` 하나이고 까닭 분류 · HTTP 상태 · 저장소 오류 코드만 담는다. 키 · 서명 · 주소 ·
  본문은 담지 않고 예외 사슬에도 남기지 않는다 — 처리 블록 밖에서 올린다(`from None` 은
  `__context__` 를 그대로 둔다). 머리를 인코딩하지 못한 `UnicodeEncodeError` 의 글에는 서명 머리가
  통째로 든다.
  `S3Target` 의 두 키는 repr 에 나오지 않는다.

이벤트 루프에서 부르지 않는다(블로킹 소켓). 문지기 · 콜백은 스레드 풀로 넘겨 부른다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import io
import re
import socket
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final
from urllib.parse import SplitResult, quote, urlsplit

ALGORITHM: Final = "AWS4-HMAC-SHA256"
SERVICE: Final = "s3"
EMPTY_SHA256: Final = hashlib.sha256(b"").hexdigest()
CONNECT_TIMEOUT_SECONDS: Final = 3.0
READ_TIMEOUT_SECONDS: Final = 5.0
# 요청 하나의 전체 마감 — 연결 제한 + 읽기 제한이다. 정상 응답이 이 안에 끝나지 않을 까닭이 없다.
REQUEST_DEADLINE_SECONDS: Final = 8.0
# 받는 본문의 상한. 넘으면 읽기를 멈추고 실패다 — 작은 객체 경계가 큰 파일을 메모리에 올리지 않게.
MAX_OBJECT_BYTES: Final = 1024 * 1024

# 까닭 분류(`S3Failure.kind`). 화면 이름은 쓰는 쪽이 정한다.
KIND_UNREACHABLE: Final = "unreachable"
KIND_TIMEOUT: Final = "timeout"
KIND_TLS: Final = "tls"
KIND_AUTH: Final = "auth_rejected"
KIND_NO_BUCKET: Final = "no_bucket"
KIND_TOO_LARGE: Final = "too_large"
KIND_OTHER: Final = "http_other"

_ERROR_CODE = re.compile(r"<Code>([A-Za-z0-9._-]{1,64})</Code>")
_NO_SUCH_KEY: Final = "NoSuchKey"
_NO_SUCH_BUCKET: Final = "NoSuchBucket"
_UNRESERVED: Final = "-_.~"


@dataclass(frozen=True)
class S3Target:
    """닿을 곳과 키 한 벌. 두 키는 repr 에 나오지 않는다."""

    endpoint_url: str
    bucket: str
    region: str
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)


class S3Failure(RuntimeError):
    """이 경계의 모든 실패. 까닭 · 상태 · 저장소 오류 코드만 든다(값 · 주소 · 키 없음)."""

    def __init__(self, kind: str, status: int | None = None, code: str = "") -> None:
        super().__init__(kind)
        self.kind = kind
        self.status = status
        self.code = code


@dataclass(frozen=True)
class S3Object:
    """받은 객체 — 본문과 ETag(따옴표를 뗀 글. 저장소가 주지 않으면 빈 글)."""

    body: bytes = field(repr=False)
    etag: str


def canonical_request(
    method: str,
    canonical_uri: str,
    canonical_query: str,
    headers: Mapping[str, str],
    payload_sha256: str,
) -> str:
    """SigV4 정규 요청. `headers` 는 서명에 넣을 머리 전부다(이름은 소문자로 접어 차례대로)."""
    lowered = sorted((name.lower(), " ".join(value.split())) for name, value in headers.items())
    lines = "".join(f"{name}:{value}\n" for name, value in lowered)
    signed = ";".join(name for name, _ in lowered)
    return "\n".join((method, canonical_uri, canonical_query, lines, signed, payload_sha256))


def credential_scope(amz_date: str, region: str) -> str:
    return f"{amz_date[:8]}/{region}/{SERVICE}/aws4_request"


def signature_v4(canonical: str, *, amz_date: str, region: str, secret_key: str) -> str:
    """정규 요청 → 서명(16진 글)."""
    to_sign = "\n".join(
        (
            ALGORITHM,
            amz_date,
            credential_scope(amz_date, region),
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
    )
    key = f"AWS4{secret_key}".encode()
    for part in (amz_date[:8], region, SERVICE, "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def object_path(bucket: str, key: str) -> str:
    """경로 스타일 주소이자 정규 URI — 구획마다 한 번 인코딩하고 `/` 는 그대로 둔다."""
    return f"/{quote(bucket, safe=_UNRESERVED)}/{quote(key, safe=_UNRESERVED + '/')}"


def signed_headers(
    target: S3Target,
    method: str,
    path: str,
    *,
    host: str,
    payload_sha256: str,
    moment: float,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """요청 머리 한 벌 — `Host` · 내용 지문 · 날짜 · 추가 머리를 모두 서명하고 서명 머리를 단다."""
    amz_date = datetime.fromtimestamp(moment, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    headers = {
        "Host": host,
        "x-amz-content-sha256": payload_sha256,
        "x-amz-date": amz_date,
        **(extra or {}),
    }
    canonical = canonical_request(method, path, "", headers, payload_sha256)
    signature = signature_v4(
        canonical, amz_date=amz_date, region=target.region, secret_key=target.secret_key
    )
    signed = ";".join(sorted(name.lower() for name in headers))
    scope = credential_scope(amz_date, target.region)
    return {
        **headers,
        "Authorization": (
            f"{ALGORITHM} Credential={target.access_key}/{scope}, "
            f"SignedHeaders={signed}, Signature={signature}"
        ),
    }


def _host_of(netloc: str, scheme: str) -> str:
    """보낼 `Host` — 기본 포트는 뗀다(서명한 글과 보낸 글이 같으면 저장소가 맞춰 본다)."""
    default = {"http": ":80", "https": ":443"}.get(scheme, "")
    return netloc[: -len(default)] if default and netloc.endswith(default) else netloc


def _error_code(body: bytes) -> str:
    found = _ERROR_CODE.search(body[:4096].decode("utf-8", errors="replace"))
    return found.group(1) if found else ""


def _time_left(deadline: float, limit: float) -> float:
    """다음 소켓 호출이 기다릴 시간 — `limit` 과 남은 시간 중 짧은 쪽. 지났으면 시간 초과다."""
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError
    return min(left, limit)


class _DeadlineReader(io.RawIOBase):
    """받기 — `recv` 마다 남은 시간만큼만 기다린다. 조금씩 흘리는 답도 마감을 넘지 못한다."""

    def __init__(self, sock: socket.socket, deadline: float) -> None:
        super().__init__()
        self._sock = sock
        self._deadline = deadline

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        self._sock.settimeout(_time_left(self._deadline, READ_TIMEOUT_SECONDS))
        return self._sock.recv_into(buffer)


class _DeadlineSocket:
    """`http.client` 에 건네는 소켓 겉 — 보내기 · 받기를 한 마감에 맞춘다.

    `close` 는 하지 않는다. `http.client` 는 `Connection: close` 답이면 본문을 읽기 전에 소켓을
    닫으므로(진짜 소켓의 `makefile` 은 참조를 세어 미룬다) 닫기는 `_round_trip` 이 끝에 한 번 한다.
    """

    def __init__(self, sock: socket.socket, deadline: float) -> None:
        self._sock = sock
        self._deadline = deadline

    def sendall(self, data: bytes) -> None:
        view = memoryview(data)
        while len(view):
            self._sock.settimeout(_time_left(self._deadline, READ_TIMEOUT_SECONDS))
            view = view[self._sock.send(view) :]

    def makefile(self, *_args: Any, **_kwargs: Any) -> io.BufferedReader:
        return io.BufferedReader(_DeadlineReader(self._sock, self._deadline))

    def close(self) -> None:
        """닫지 않는다(클래스 설명)."""


def _connected_socket(host: str, port: int, deadline: float) -> socket.socket:
    """주소를 차례로 잇는다 — 연결 제한은 주소마다, 모두 합쳐 마감을 넘지 않는다."""
    last: OSError = TimeoutError()
    for family, kind, protocol, _, address in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    ):
        candidate = socket.socket(family, kind, protocol)
        try:
            candidate.settimeout(_time_left(deadline, CONNECT_TIMEOUT_SECONDS))
            candidate.connect(address)
        except OSError as exc:
            candidate.close()
            last = exc
            continue
        return candidate
    raise last


def _open_socket(parts: SplitResult, deadline: float) -> socket.socket:
    """이어 둔 소켓(https 면 TLS 까지) — 이름 풀기 뒤의 모든 단계가 마감 안이다."""
    host = parts.hostname or ""
    secure = parts.scheme == "https"
    plain = _connected_socket(host, parts.port or (443 if secure else 80), deadline)
    if not secure:
        return plain
    try:
        plain.settimeout(_time_left(deadline, READ_TIMEOUT_SECONDS))
        return ssl.create_default_context().wrap_socket(plain, server_hostname=host)
    except BaseException:
        plain.close()
        raise


def _round_trip(
    parts: SplitResult,
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
) -> tuple[int, str, bytes]:
    """요청 하나를 마감 안에서 주고받는다."""
    deadline = time.monotonic() + REQUEST_DEADLINE_SECONDS
    sock = _open_socket(parts, deadline)
    try:
        # 이어 둔 소켓을 건네므로 주소 인자는 쓰이지 않는다(`Host` 머리는 서명한 값을 싣는다).
        connection = http.client.HTTPConnection(parts.hostname or "", parts.port)
        connection.sock = _DeadlineSocket(sock, deadline)
        try:
            connection.request(method, path, body=body or None, headers=dict(headers))
            response = connection.getresponse()
            data = response.read(MAX_OBJECT_BYTES + 1)
            return response.status, (response.getheader("ETag") or "").strip().strip('"'), data
        finally:
            connection.close()
    finally:
        sock.close()


def _failure_of(error: Exception) -> S3Failure:
    """닿지 못한 까닭 하나. `ValueError` — 소켓이 주소 이름을 풀지 못한 경우(IDNA)와 머리 값 꼴."""
    if isinstance(error, ssl.SSLError):
        return S3Failure(KIND_TLS)
    if isinstance(error, TimeoutError):
        return S3Failure(KIND_TIMEOUT)
    return S3Failure(KIND_UNREACHABLE)


def _exchange(
    target: S3Target,
    method: str,
    key: str,
    *,
    body: bytes = b"",
    extra: Mapping[str, str] | None = None,
    moment: float | None = None,
) -> tuple[int, str, bytes]:
    """요청 하나 — `(상태, ETag, 본문)`. 닿지 못한 것만 여기서 `S3Failure` 로 올린다."""
    parts = urlsplit(target.endpoint_url)
    path = object_path(target.bucket, key)
    headers = signed_headers(
        target,
        method,
        path,
        host=_host_of(parts.netloc, parts.scheme),
        payload_sha256=hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256,
        moment=time.time() if moment is None else moment,
        extra=extra,
    )
    try:
        return _round_trip(parts, method, path, body, headers)
    except (OSError, ValueError, http.client.HTTPException) as error:
        failure = _failure_of(error)
    raise failure


def _rejected(status: int, data: bytes, *, bucket_missing: bool = False) -> S3Failure:
    """2xx · 없음 밖의 응답 → 실패 하나."""
    code = _error_code(data)
    if status in (401, 403):
        return S3Failure(KIND_AUTH, status, code)
    if status == 404 and (bucket_missing or code == _NO_SUCH_BUCKET):
        return S3Failure(KIND_NO_BUCKET, status, code)
    return S3Failure(KIND_OTHER, status, code)


def get_object(target: S3Target, key: str, *, moment: float | None = None) -> S3Object | None:
    """객체를 받는다. 키가 없으면(404 · `NoSuchKey`) `None`.

    그 밖의 404 는 실패다 — 버킷이 없거나, 저장소 앞단이 코드 없이 답한 것이다(HTML · 빈 본문).
    그것을 「파일 없음」 으로 읽으면 멀쩡한 파일을 두고 빈 명단으로 선다.
    """
    status, etag, data = _exchange(target, "GET", key, moment=moment)
    if status == 404 and _error_code(data) == _NO_SUCH_KEY:
        return None
    if status != 200:
        raise _rejected(status, data)
    if len(data) > MAX_OBJECT_BYTES:
        raise S3Failure(KIND_TOO_LARGE, status)
    return S3Object(body=data, etag=etag)


def head_object(target: S3Target, key: str, *, moment: float | None = None) -> str | None:
    """머리만 본다 — 있으면 ETag(주지 않으면 빈 글), 없으면 `None`.

    HEAD 는 본문이 없어 키가 없는지 버킷이 없는지 가르지 못한다 — 버킷이 없으면 뒤이은 PUT 이
    가른다.
    """
    status, etag, data = _exchange(target, "HEAD", key, moment=moment)
    if status == 404:
        return None
    if status != 200:
        raise _rejected(status, data)
    return etag


def put_object(
    target: S3Target,
    key: str,
    body: bytes,
    *,
    content_type: str = "application/json",
    moment: float | None = None,
) -> str:
    """객체를 올린다 — 저장소가 준 ETag(주지 않으면 빈 글).

    `Content-MD5` 를 싣는다 — 전송 중 깨진 본문을 저장소가 거절하고, 이 머리를 요구하는 S3 호환
    저장소(`docs/objectstore_setup.md` 「Content-MD5」)에서도 그대로 들어간다.
    """
    if len(body) > MAX_OBJECT_BYTES:
        raise S3Failure(KIND_TOO_LARGE)
    digest = hashlib.md5(body, usedforsecurity=False).digest()
    status, etag, data = _exchange(
        target,
        "PUT",
        key,
        body=body,
        extra={
            "Content-Type": content_type,
            "Content-MD5": base64.b64encode(digest).decode("ascii"),
        },
        moment=moment,
    )
    if not 200 <= status < 300:
        raise _rejected(status, data, bucket_missing=True)
    return etag
