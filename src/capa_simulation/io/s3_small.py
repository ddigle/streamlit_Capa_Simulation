# Purpose: S3 호환 저장소의 작은 객체 하나를 표준 라이브러리만으로 받고·올리고·머리만 본다(SigV4).

"""작은 객체 경계.

DuckDB 스냅샷처럼 큰 파일은 `io/object_storage.py`(`aws` CLI) 몫이고, 여기는 접속 명단 파일처럼 몇
KiB 짜리 객체 하나를 앱 프로세스가 직접 주고받는 자리다. 따로 둔 까닭은 C-DEP 이미지에 `aws` 가
있다는 보장이 없고(셸이 없어 확인도 못 한다) 의존성을 늘리지 않기 위해서다.

- **표준 라이브러리만** 쓴다 — `auth` 가 import 해도 Streamlit · 무거운 모듈이 딸려 오지 않는다.
- **경로 스타일 주소**(`/<버킷>/<키>`) — 버킷 이름에 대문자 · 밑줄이 있어 가상 호스트로 적지 못한다.
- **시간 제한** 연결 3초 · 읽기 5초(`http.client` 로 둘을 나눈다). 재시도는 없다(부르는 쪽 몫).
- **프록시 · 리다이렉트를 따르지 않는다** — 환경변수 프록시를 지나면 명단이 그 프록시에 보이고
  그쪽 403 이 저장소의 인증 거절로 읽힌다. 3xx 는 그 밖 응답으로 올린다.
- **조건부 쓰기(`If-Match`)를 보내지 않는다** — 확인하지 못한 능력은 없는 것으로 본다
  (`docs/objectstore_setup.md` 2단계). 덮어쓰기 막기는 부르는 쪽이 `head_object` 로 한다.
- 실패는 `S3Failure` 하나이고 까닭 분류 · HTTP 상태 · 저장소 오류 코드만 담는다. 키 · 서명 · 주소 ·
  본문은 담지 않는다. `S3Target` 의 두 키는 repr 에 나오지 않는다.

이벤트 루프에서 부르지 않는다(블로킹 소켓). 문지기 · 콜백은 스레드 풀로 넘겨 부른다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import re
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final
from urllib.parse import quote, urlsplit

ALGORITHM: Final = "AWS4-HMAC-SHA256"
SERVICE: Final = "s3"
EMPTY_SHA256: Final = hashlib.sha256(b"").hexdigest()
CONNECT_TIMEOUT_SECONDS: Final = 3.0
READ_TIMEOUT_SECONDS: Final = 5.0
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
    connection: http.client.HTTPConnection | None = None
    try:
        if parts.scheme == "https":
            connection = http.client.HTTPSConnection(
                parts.hostname or "",
                parts.port,
                timeout=CONNECT_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        else:
            connection = http.client.HTTPConnection(
                parts.hostname or "", parts.port, timeout=CONNECT_TIMEOUT_SECONDS
            )
        connection.connect()
        connection.sock.settimeout(READ_TIMEOUT_SECONDS)
        connection.request(method, path, body=body or None, headers=headers)
        response = connection.getresponse()
        data = response.read(MAX_OBJECT_BYTES + 1)
        return response.status, (response.getheader("ETag") or "").strip().strip('"'), data
    except ssl.SSLError as exc:
        raise S3Failure(KIND_TLS) from exc
    except TimeoutError as exc:
        raise S3Failure(KIND_TIMEOUT) from exc
    except (OSError, ValueError, http.client.HTTPException) as exc:
        # `ValueError` — 소켓이 주소 이름을 풀지 못한 경우(IDNA 인코딩)와 머리 값 꼴.
        raise S3Failure(KIND_UNREACHABLE) from exc
    finally:
        if connection is not None:
            connection.close()


def _rejected(status: int, data: bytes, *, bucket_missing: bool = False) -> S3Failure:
    """2xx · 없음 밖의 응답 → 실패 하나."""
    code = _error_code(data)
    if status in (401, 403):
        return S3Failure(KIND_AUTH, status, code)
    if status == 404 and (bucket_missing or code == _NO_SUCH_BUCKET):
        return S3Failure(KIND_NO_BUCKET, status, code)
    return S3Failure(KIND_OTHER, status, code)


def get_object(target: S3Target, key: str, *, moment: float | None = None) -> S3Object | None:
    """객체를 받는다. 키가 없으면(404) `None` — 버킷이 없는 404 는 실패다."""
    status, etag, data = _exchange(target, "GET", key, moment=moment)
    if status == 404 and _error_code(data) != _NO_SUCH_BUCKET:
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
