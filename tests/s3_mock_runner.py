# Purpose: `aws s3api` 인자 배열을 가짜 S3 에 서명한 HTTP 요청으로 옮기는 시험 실행기.

"""시험용 실행기 — `ObjectStorageClient` 를 `aws` 없이 가짜 S3 위로 끝까지 태운다.

`tests/object_store_fakes.FakeStore` 는 인자를 메모리로 해석할 뿐이다. 여기서는 같은 인자
배열을 SigV4 로 서명한 요청으로 바꿔 가짜 S3(`scripts/s3_mock_store.py`)에 보낸다 — 가짜 S3 가
서명 · `If-None-Match` · 목록 이어받기를 실제로 검사한다. 응답은 `aws` 가 내는 꼴(JSON 표준
출력 · `An error occurred (코드)` 표준 오류)로 되돌려 `ObjectStorageClient` 의 판정(없음 · 선점
실패 · 재시도)이 그대로 돈다.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

from capa_simulation.io import s3_small
from capa_simulation.io.object_storage import CommandResult, ObjectStorageClient, StorageSettings

_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_OPERATIONS = {
    "put-object": "PutObject",
    "get-object": "GetObject",
    "head-object": "HeadObject",
    "list-objects-v2": "ListObjectsV2",
    "delete-object": "DeleteObject",
}


def _canonical_query(pairs: Sequence[tuple[str, str]]) -> str:
    return "&".join(
        f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}" for name, value in sorted(pairs)
    )


@dataclass
class MockStoreRunner:
    """`CommandRunner` — 가짜 S3 주소 · 키로 서명해 보낸다. 받은 인자는 `calls` 에 쌓인다."""

    endpoint: str
    bucket: str
    region: str
    access_key: str
    secret_key: str
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self, argv: Sequence[str], env: Mapping[str, str], *, timeout_seconds: float
    ) -> CommandResult:
        args = list(argv)
        self.calls.append(tuple(args))
        operation = args[2]
        options = {
            token: args[index + 1]
            for index, token in enumerate(args)
            if token.startswith("--") and index + 1 < len(args)
        }
        key = options.get("--key", "")
        if operation == "list-objects-v2":
            query = [("list-type", "2"), ("prefix", options.get("--prefix", ""))]
            query.append(("max-keys", options.get("--max-keys", "1000")))
            if "--continuation-token" in options:
                query.append(("continuation-token", options["--continuation-token"]))
            status, headers, body = self._send("GET", "", query=query)
            if status != 200:
                return self._failed(operation, status, body)
            return self._ok(self._listing(body))
        if operation == "put-object":
            payload = Path(options["--body"]).read_bytes()
            extra = {"Content-Type": "application/octet-stream"}
            if "--content-md5" in options:
                extra["Content-MD5"] = options["--content-md5"]
            if "--if-none-match" in args:
                extra["If-None-Match"] = options["--if-none-match"]
            status, headers, body = self._send("PUT", key, body=payload, extra=extra)
            if status != 200:
                return self._failed(operation, status, body)
            return self._ok({"ETag": headers.get("etag", "")})
        method = {"get-object": "GET", "head-object": "HEAD", "delete-object": "DELETE"}[operation]
        status, headers, body = self._send(method, key)
        if status not in (200, 204):
            return self._failed(operation, status, body)
        payload_json: dict[str, object] = {
            "ContentLength": int(headers.get("content-length", len(body)) or 0),
            "ETag": headers.get("etag", ""),
        }
        if "last-modified" in headers:
            moment = parsedate_to_datetime(headers["last-modified"]).astimezone(timezone.utc)
            payload_json["LastModified"] = moment.isoformat()
        if operation == "get-object":
            Path(args[-1]).write_bytes(body)
            payload_json["ContentLength"] = len(body)
        return self._ok(payload_json if operation != "delete-object" else {})

    # ------------------------------------------------------------------ 요청
    def _send(
        self,
        method: str,
        key: str,
        *,
        query: Sequence[tuple[str, str]] = (),
        body: bytes = b"",
        extra: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        parts = urlsplit(self.endpoint)
        path = s3_small.object_path(self.bucket, key) if key else f"/{quote(self.bucket)}"
        canonical_query = _canonical_query(query)
        payload_sha = hashlib.sha256(body).hexdigest() if body else s3_small.EMPTY_SHA256
        amz_date = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        headers = {
            "Host": parts.netloc,
            "x-amz-content-sha256": payload_sha,
            "x-amz-date": amz_date,
            **(extra or {}),
        }
        canonical = s3_small.canonical_request(method, path, canonical_query, headers, payload_sha)
        signature = s3_small.signature_v4(
            canonical, amz_date=amz_date, region=self.region, secret_key=self.secret_key
        )
        signed = ";".join(sorted(name.lower() for name in headers))
        scope = s3_small.credential_scope(amz_date, self.region)
        headers["Authorization"] = (
            f"{s3_small.ALGORITHM} Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed}, Signature={signature}"
        )
        target = path + (f"?{canonical_query}" if canonical_query else "")
        connection = http.client.HTTPConnection(
            parts.hostname or "127.0.0.1", parts.port, timeout=10
        )
        try:
            connection.request(method, target, body=body or None, headers=headers)
            response = connection.getresponse()
            data = response.read()
            answered = {name.lower(): value for name, value in response.getheaders()}
            return response.status, answered, data
        finally:
            connection.close()

    # ------------------------------------------------------------------ 답
    @staticmethod
    def _ok(payload: Mapping[str, object]) -> CommandResult:
        return CommandResult((), 0, json.dumps(payload), "", 0.0)

    @staticmethod
    def _failed(operation: str, status: int, body: bytes) -> CommandResult:
        code = str(status)
        if body:
            try:
                found = ElementTree.fromstring(body).findtext("Code")
            except ElementTree.ParseError:
                found = None
            code = found or code
        if status == 404 and operation == "head-object":
            code = "404"
        stderr = f"An error occurred ({code}) when calling the {_OPERATIONS[operation]} operation"
        return CommandResult((), 254, "", stderr, 0.0)

    @staticmethod
    def _listing(body: bytes) -> dict[str, object]:
        root = ElementTree.fromstring(body)
        contents = []
        for item in root.findall(f"{_NS}Contents"):
            contents.append(
                {
                    "Key": item.findtext(f"{_NS}Key") or "",
                    "Size": int(item.findtext(f"{_NS}Size") or 0),
                    "ETag": item.findtext(f"{_NS}ETag") or "",
                    "LastModified": item.findtext(f"{_NS}LastModified") or "",
                }
            )
        payload: dict[str, object] = {"Contents": contents} if contents else {}
        if (root.findtext(f"{_NS}IsTruncated") or "") == "true":
            payload["IsTruncated"] = True
            payload["NextContinuationToken"] = root.findtext(f"{_NS}NextContinuationToken") or ""
        return payload


def mock_client(runner: MockStoreRunner, *, conditional_put: bool = True) -> ObjectStorageClient:
    """가짜 S3 위의 실제 클라이언트. 조건부 쓰기 능력을 켜거나 끈다."""
    settings = StorageSettings(
        mode="managed",
        endpoint_url=runner.endpoint,
        bucket=runner.bucket,
        profile="demo-profile",
        region=runner.region,
        capabilities={"conditional_put_if_none_match_star": conditional_put},
    )
    return ObjectStorageClient(settings=settings, runner=runner, sleep=lambda _seconds: None)
