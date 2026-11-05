# Purpose: 개발·시험용 가짜 S3 — 서명을 검증하며 작은 객체 GET·PUT·HEAD 를 메모리로 받는다.

"""가짜 S3(개발 · 시험 전용).

실제 저장소 없이 S3 명단(`auth/access_store`)을 끝까지 돌려 본다. 시험은 `start_mock` 으로 띄우고,
손으로 볼 때는 창 하나에서 띄워 앱의 환경변수 표에 같은 값을 넣는다.

    python scripts/s3_mock_store.py --port 8607 --env-out ~/s3-dev.env

- **거절**: `--host` 가 루프백이 아니면, `--env-out` 이 git 작업 트리 안이면 종료 코드 2. 객체는
  메모리에만 있고 끄면 사라진다.
- 서명은 받은 요청 그대로 다시 지어 본다(경로 · 서명한 머리 · 본문 지문) — 어긋나면 403
  `SignatureDoesNotMatch`, 모르는 키는 403 `InvalidAccessKeyId`, 다른 버킷은 404 `NoSuchBucket`,
  없는 키는 404 `NoSuchKey` 다. `Content-MD5` 가 있으면 본문과 견준다.
- 실패 흉내(시험): `force` — 메서드별 강제 응답, `delay_seconds` — 답 늦추기, `omit_etag` — ETag
  빼기. 받은 요청은 `requests` 에 쌓인다(판정이 S3 에 가지 않는 것을 시험이 본다).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import re
import shlex
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.auth import names  # noqa: E402
from capa_simulation.auth.config import is_loopback_host  # noqa: E402
from capa_simulation.io.s3_small import (  # noqa: E402
    ALGORITHM,
    canonical_request,
    credential_scope,
    signature_v4,
)

DEFAULT_ACCESS_KEY = "demo-access-key"
DEFAULT_SECRET_KEY = "demo-secret-key-for-the-mock-store"
DEFAULT_BUCKET = "Demo_bucket"
DEFAULT_REGION = "us-east-1"
REFUSED = 2

_AUTHORIZATION = re.compile(
    rf"^{ALGORITHM} Credential=(?P<key>[^/]+)/(?P<scope>[^,]+), "
    r"SignedHeaders=(?P<signed>[^,]+), Signature=(?P<signature>[0-9a-f]{64})$"
)


@dataclass
class MockStore:
    """가짜 저장소 한 벌의 상태. 시험이 바로 들여다보고 고친다."""

    access_key: str = DEFAULT_ACCESS_KEY
    secret_key: str = DEFAULT_SECRET_KEY
    bucket: str = DEFAULT_BUCKET
    region: str = DEFAULT_REGION
    objects: dict[str, bytes] = field(default_factory=dict)
    requests: list[tuple[str, str]] = field(default_factory=list)
    force: dict[str, tuple[int, str]] = field(default_factory=dict)
    delay_seconds: float = 0.0
    omit_etag: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def put(self, key: str, body: bytes) -> None:
        with self.lock:
            self.objects[key] = body


def etag_of(body: bytes) -> str:
    return hashlib.md5(body, usedforsecurity=False).hexdigest()


class _Handler(BaseHTTPRequestHandler):
    server_version = "s3-mock"
    protocol_version = "HTTP/1.1"
    store: MockStore

    def log_message(self, format: str, *args: object) -> None:
        """요청 줄을 찍지 않는다 — 객체 키가 표준 오류에 쌓일 까닭이 없다."""

    def _answer(
        self,
        status: int,
        body: bytes = b"",
        *,
        etag: str = "",
        length: int | None = None,
    ) -> None:
        self.send_response(status)
        if etag and not self.store.omit_etag:
            self.send_header("ETag", f'"{etag}"')
        self.send_header("Content-Length", str(len(body) if length is None else length))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _error(self, status: int, code: str) -> None:
        body = f"<?xml version='1.0'?><Error><Code>{code}</Code></Error>".encode()
        self._answer(status, body)

    def _signature_problem(self, body: bytes) -> str:
        """서명을 받은 요청 그대로 다시 짓는다. 맞으면 빈 글, 틀리면 저장소 오류 코드."""
        match = _AUTHORIZATION.match(self.headers.get("Authorization", ""))
        if match is None:
            return "AccessDenied"
        if match["key"] != self.store.access_key:
            return "InvalidAccessKeyId"
        amz_date = self.headers.get("x-amz-date", "")
        if match["scope"] != credential_scope(amz_date, self.store.region):
            return "SignatureDoesNotMatch"
        payload = self.headers.get("x-amz-content-sha256", "")
        if payload != hashlib.sha256(body).hexdigest():
            return "XAmzContentSHA256Mismatch"
        signed = match["signed"].split(";")
        headers = {name: self.headers.get(name, "") for name in signed}
        if "host" not in headers or "x-amz-date" not in headers:
            return "SignatureDoesNotMatch"
        canonical = canonical_request(self.command, urlsplit(self.path).path, "", headers, payload)
        expected = signature_v4(
            canonical,
            amz_date=amz_date,
            region=self.store.region,
            secret_key=self.store.secret_key,
        )
        return "" if hmac.compare_digest(expected, match["signature"]) else "SignatureDoesNotMatch"

    def _handle(self) -> None:
        store = self.store
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        store.requests.append((self.command, self.path))
        if store.delay_seconds:
            time.sleep(store.delay_seconds)
        forced = store.force.get(self.command)
        if forced is not None:
            self._error(*forced)
            return
        problem = self._signature_problem(body)
        if problem:
            self._error(403, problem)
            return
        bucket, _, key = unquote(urlsplit(self.path).path).lstrip("/").partition("/")
        if bucket != store.bucket:
            self._error(404, "NoSuchBucket")
            return
        if self.command == "PUT":
            self._handle_put(key, body)
            return
        with store.lock:
            found = store.objects.get(key)
        if found is None:
            self._error(404, "NoSuchKey")
        elif self.command == "HEAD":
            self._answer(200, b"", etag=etag_of(found), length=len(found))
        else:
            self._answer(200, found, etag=etag_of(found))

    def _handle_put(self, key: str, body: bytes) -> None:
        sent_md5 = self.headers.get("Content-MD5")
        digest = hashlib.md5(body, usedforsecurity=False).digest()
        if sent_md5 and sent_md5 != base64.b64encode(digest).decode("ascii"):
            self._error(400, "BadDigest")
            return
        self.store.put(key, body)
        self._answer(200, b"", etag=etag_of(body))

    do_GET = _handle
    do_HEAD = _handle
    do_PUT = _handle


def start_mock(store: MockStore, *, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """시험 · 손 확인용 — 데몬 스레드로 띄우고 `(서버, 주소)` 를 돌려준다."""
    handler = type("Handler", (_Handler,), {"store": store})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def env_lines(store: MockStore, endpoint: str) -> list[str]:
    """앱 환경변수 줄(`set -a; . 파일; set +a` 로 읽는다). 값은 모두 합성이다."""
    values = {
        names.ENV_S3_ACCESS_KEY: store.access_key,
        names.ENV_S3_SECRET_KEY: store.secret_key,
        names.ENV_S3_ENDPOINT: endpoint,
        names.ENV_S3_BUCKET: store.bucket,
        names.ENV_S3_REGION: store.region,
    }
    return [f"{name}={shlex.quote(value)}" for name, value in values.items()]


def _inside_git_worktree(path: Path) -> bool:
    folder = path.parent if path.parent.exists() else Path.cwd()
    found = subprocess.run(
        ["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return found.returncode == 0 and found.stdout.strip() == "true"


def write_env_file(path: Path, lines: list[str]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="개발용 가짜 S3(메모리 · 서명 검증)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8607)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--env-out", type=Path, default=None)
    options = parser.parse_args(argv)
    if not is_loopback_host(options.host):
        print("--host 는 루프백만 받습니다.", file=sys.stderr)
        return REFUSED
    env_out: Path | None = options.env_out
    if env_out is not None:
        env_out = env_out.expanduser()
        if _inside_git_worktree(env_out):
            print("--env-out 은 git 작업 트리 밖에 둡니다.", file=sys.stderr)
            return REFUSED
    store = MockStore(bucket=options.bucket)
    server, endpoint = start_mock(store, port=options.port)
    if env_out is not None:
        write_env_file(env_out, env_lines(store, endpoint))
    print(f"가짜 S3: {endpoint} · 버킷 {store.bucket}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
