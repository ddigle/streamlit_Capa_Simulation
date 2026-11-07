# Purpose: 개발·시험용 가짜 S3 — 서명을 검증하며 객체 GET·PUT·HEAD·DELETE·목록을 메모리로 받는다.

"""가짜 S3(개발 · 시험 전용).

실제 저장소 없이 S3 명단(`auth/access_store`)과 DB 동기화(`aws` CLI — 시험 판 1.46.3)를 끝까지 돌려
본다. 시험은 `start_mock` 으로 띄우고, 손으로 볼 때는 창 하나에서 띄워 앱의 환경변수 표에 같은 값을
넣는다.

    python scripts/s3_mock_store.py --port 8607 --env-out ~/s3-dev.env

- **거절**: `--host` 가 루프백이 아니면, `--env-out` 이 git 작업 트리 안이면, `--seed-loginid` 가
  합성(`demo.`)이 아니면 종료 코드 2. 객체는 메모리에만 있고 끄면 사라진다 — 띄울 때 명단을 심어
  두려면 `--seed-loginid demo.user`(되풀이 가능).
- 서명은 받은 요청 그대로 다시 지어 본다(경로 · 질의 · 서명한 머리 · 본문 지문) — 어긋나면 403
  `SignatureDoesNotMatch`, 모르는 키는 403 `InvalidAccessKeyId`, 다른 버킷은 404 `NoSuchBucket`,
  없는 키는 404 `NoSuchKey` 다. `Content-MD5` 가 있으면 본문과 견준다. 메타데이터(`x-amz-meta-*`)는
  객체에 담아 HEAD · GET 머리로 돌려준다. `If-None-Match: *` 은 키가 있으면 412 다
  (`ignore_if_none_match` 로 무시하는 저장소를 흉내 낸다). 목록은 `ListObjectsV2` 꼴이고 키 차례 ·
  이어받기 토큰을 지킨다.
- 실패 흉내(시험): `force` — 메서드별 강제 응답(저장소 오류 XML), `raw` — 메서드별 강제 응답(본문
  그대로 — 저장소 앞단의 HTML · 빈 본문), `delay_seconds` — 답 늦추기, `answer_delay` — 일은 마치고
  답만 늦추기, `omit_etag` — ETag 빼기, `force_on` — 키 접두 + 메서드로 n 번째 요청부터 실패(저장
  전) · `Fault.stored` 는 **저장하고 답을 끊는다**. 받은 요청은 `requests` 에 쌓인다(판정이 S3 에
  가지 않는 것을 시험이 본다). `modified` 로 객체 시각을 시험이 정한다(`clock` 이 새 객체의 시각).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import os
import re
import shlex
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit
from xml.sax.saxutils import escape

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.auth import names  # noqa: E402
from capa_simulation.auth.access import ListDocument, ListEntry, entry_key  # noqa: E402
from capa_simulation.auth.access_store import render_document  # noqa: E402
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
SEED_PREFIX = "demo."

_AUTHORIZATION = re.compile(
    rf"^{ALGORITHM} Credential=(?P<key>[^/]+)/(?P<scope>[^,]+), "
    r"SignedHeaders=(?P<signed>[^,]+), Signature=(?P<signature>[0-9a-f]{64})$"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Fault:
    """키 접두 + 메서드가 맞는 요청을 실패시킨다. `after` 번 지나간 뒤부터 `times` 번이다.

    `stored` 는 일을 마치고 답을 끊는다 — 들어갔는데 실패로 끝나는 길이다. 저장 전 실패만 흉내 내면
    그 길을 시험하지 못한다.
    """

    method: str
    prefix: str = ""
    after: int = 0
    times: int = 1
    status: int = 500
    code: str = "InternalError"
    stored: bool = False


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
    raw: dict[str, tuple[int, bytes]] = field(default_factory=dict)
    delay_seconds: float = 0.0
    answer_delay: dict[str, float] = field(default_factory=dict)
    omit_etag: bool = False
    faults: list[Fault] = field(default_factory=list)
    metadata: dict[str, dict[str, str]] = field(default_factory=dict)
    modified: dict[str, datetime] = field(default_factory=dict)
    clock: Callable[[], datetime] = _utc_now
    ignore_if_none_match: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def put(self, key: str, body: bytes) -> None:
        with self.lock:
            self.objects[key] = body
            self.modified[key] = self.clock()

    def force_on(
        self, method: str, prefix: str = "", *, after: int = 0, times: int = 1, **fault: object
    ) -> Fault:
        """실패 하나를 건다(`Fault`). 돌려준 값을 시험이 들여다본다."""
        item = Fault(method, prefix, after, times, **fault)  # type: ignore[arg-type]
        self.faults.append(item)
        return item

    def _take_fault(self, method: str, key: str) -> Fault | None:
        with self.lock:
            for fault in self.faults:
                if fault.method != method or not key.startswith(fault.prefix):
                    continue
                if fault.after > 0:
                    fault.after -= 1
                    continue
                if fault.times > 0:
                    fault.times -= 1
                    return fault
        return None


def etag_of(body: bytes) -> str:
    return hashlib.md5(body, usedforsecurity=False).hexdigest()


def _canonical_query(query: str) -> str:
    """SigV4 정규 질의 — 받은 그대로 값을 다시 인코딩해 이름 차례로 늘어놓는다."""
    pairs = sorted(parse_qsl(query, keep_blank_values=True))
    return "&".join(
        f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}" for name, value in pairs
    )


class _Discard(io.BytesIO):
    """답을 버리는 자리. 쓴 바이트가 소켓에 닿지 않아 받는 쪽은 답 없이 끊긴다."""

    def flush(self) -> None:
        return None


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
        headers: dict[str, str] | None = None,
    ) -> None:
        late = self.store.answer_delay.get(self.command, 0.0)
        if late:
            time.sleep(late)
        self.send_response(status)
        if etag and not self.store.omit_etag:
            self.send_header("ETag", f'"{etag}"')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body) if length is None else length))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _error(self, status: int, code: str) -> None:
        body = f"<?xml version='1.0'?><Error><Code>{code}</Code></Error>".encode()
        self._answer(status, body, headers={"Content-Type": "application/xml"})

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
        if payload != hashlib.sha256(body).hexdigest() and payload != "UNSIGNED-PAYLOAD":
            return "XAmzContentSHA256Mismatch"
        signed = match["signed"].split(";")
        headers = {name: self.headers.get(name, "") for name in signed}
        if "host" not in headers or "x-amz-date" not in headers:
            return "SignatureDoesNotMatch"
        parts = urlsplit(self.path)
        canonical = canonical_request(
            self.command, parts.path, _canonical_query(parts.query), headers, payload
        )
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
        raw = store.raw.get(self.command)
        if raw is not None:
            self._answer(*raw)
            return
        problem = self._signature_problem(body)
        if problem:
            self._error(403, problem)
            return
        parts = urlsplit(self.path)
        bucket, _, key = unquote(parts.path).lstrip("/").partition("/")
        if bucket != store.bucket:
            self._error(404, "NoSuchBucket")
            return
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        fault = store._take_fault(self.command, key or query.get("prefix", ""))
        if fault is not None and not fault.stored:
            self._error(fault.status, fault.code)
            return
        if fault is not None:
            # 일은 마치고 답 없이 끊는다 — `aws` 는 연결 오류로 본다.
            self.wfile = _Discard()
        self._dispatch(key, query, body)

    def _dispatch(self, key: str, query: dict[str, str], body: bytes) -> None:
        if self.command == "PUT":
            self._handle_put(key, body)
            return
        if self.command == "DELETE":
            with self.store.lock:
                self.store.objects.pop(key, None)
                self.store.metadata.pop(key, None)
                self.store.modified.pop(key, None)
            self._answer(204)
            return
        if not key and self.command == "GET":
            self._handle_list(query)
            return
        with self.store.lock:
            found = self.store.objects.get(key)
            extra = self._object_headers(key)
        if found is None:
            self._error(404, "NoSuchKey")
        elif self.command == "HEAD":
            self._answer(200, b"", etag=etag_of(found), length=len(found), headers=extra)
        else:
            self._answer(200, found, etag=etag_of(found), headers=extra)

    def _object_headers(self, key: str) -> dict[str, str]:
        moment = self.store.modified.get(key)
        headers = {"Content-Type": "application/octet-stream"}
        if moment is not None:
            headers["Last-Modified"] = format_datetime(moment.astimezone(timezone.utc), usegmt=True)
        for name, value in self.store.metadata.get(key, {}).items():
            headers[f"x-amz-meta-{name}"] = value
        return headers

    def _handle_list(self, query: dict[str, str]) -> None:
        """`ListObjectsV2` — 키 차례, 이어받기 토큰은 다음 시작 번호다."""
        prefix = query.get("prefix", "")
        size = int(query.get("max-keys", "1000"))
        start = int(query.get("continuation-token", "0"))
        encode = query.get("encoding-type") == "url"
        with self.store.lock:
            names = sorted(key for key in self.store.objects if key.startswith(prefix))
            page = names[start : start + size]
            rows = [
                (
                    key,
                    len(self.store.objects[key]),
                    etag_of(self.store.objects[key]),
                    self.store.modified.get(key, self.store.clock()),
                )
                for key in page
            ]
        truncated = start + size < len(names)
        contents = "".join(
            "<Contents>"
            f"<Key>{escape(quote(key, safe='/') if encode else key)}</Key>"
            f"<LastModified>{moment.strftime('%Y-%m-%dT%H:%M:%S.000Z')}</LastModified>"
            f'<ETag>"{tag}"</ETag><Size>{size_bytes}</Size><StorageClass>STANDARD</StorageClass>'
            "</Contents>"
            for key, size_bytes, tag, moment in rows
        )
        following = f"<NextContinuationToken>{start + size}</NextContinuationToken>"
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<Name>{escape(self.store.bucket)}</Name><Prefix>{escape(prefix)}</Prefix>"
            f"<KeyCount>{len(rows)}</KeyCount><MaxKeys>{size}</MaxKeys>"
            f"<IsTruncated>{'true' if truncated else 'false'}</IsTruncated>"
            f"{following if truncated else ''}{contents}</ListBucketResult>"
        ).encode()
        self._answer(200, body, headers={"Content-Type": "application/xml"})

    def _handle_put(self, key: str, body: bytes) -> None:
        sent_md5 = self.headers.get("Content-MD5")
        digest = hashlib.md5(body, usedforsecurity=False).digest()
        if sent_md5 and sent_md5 != base64.b64encode(digest).decode("ascii"):
            self._error(400, "BadDigest")
            return
        with self.store.lock:
            exists = key in self.store.objects
        condition = self.headers.get("If-None-Match")
        if condition == "*" and exists and not self.store.ignore_if_none_match:
            self._error(412, "PreconditionFailed")
            return
        self.store.put(key, body)
        with self.store.lock:
            self.store.metadata[key] = {
                name[len("x-amz-meta-") :].lower(): value
                for name, value in self.headers.items()
                if name.lower().startswith("x-amz-meta-")
            }
        self._answer(200, b"", etag=etag_of(body))

    do_GET = _handle
    do_HEAD = _handle
    do_PUT = _handle
    do_DELETE = _handle


class _Server(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: object) -> None:
        """끊긴 연결은 넘기고, 그 밖의 예외는 ASCII 한 줄로 알린다.

        시험의 클라이언트는 상한 · 제한 시간에서 답을 덜 읽고 끊는다. 기본 구현은 그때마다
        traceback 을 표준 오류에 찍는데, Windows 의 소켓 오류 글은 현지 언어라(`WinError 10053` 은
        한글) 그 줄이 터미널 인코딩으로 나간다.
        """
        error = sys.exc_info()[1]
        if isinstance(error, ConnectionError):
            return
        print(f"s3-mock: {type(error).__name__} {ascii(str(error))}", file=sys.stderr)


def start_mock(store: MockStore, *, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """시험 · 손 확인용 — 데몬 스레드로 띄우고 `(서버, 주소)` 를 돌려준다."""
    handler = type("Handler", (_Handler,), {"store": store})
    server = _Server(("127.0.0.1", port), handler)
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


def seed_body(loginids: list[str]) -> bytes:
    """합성 사람들을 든 명단 파일 바이트(판 1)."""
    entries = tuple(ListEntry(loginid) for loginid in sorted(set(loginids)))
    return render_document(ListDocument(revision=1, entries=entries))


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
    parser.add_argument("--seed-loginid", action="append", default=[], help="합성 값(demo.*)만")
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
    seeds: list[str] = options.seed_loginid
    if any(not item.startswith(SEED_PREFIX) or entry_key(item) != item for item in seeds):
        print(f"--seed-loginid 는 합성 값({SEED_PREFIX}*)만 받습니다.", file=sys.stderr)
        return REFUSED
    store = MockStore(bucket=options.bucket)
    if seeds:
        store.put(names.DEFAULT_ACCESS_OBJECT, seed_body(seeds))
    server, endpoint = start_mock(store, port=options.port)
    if env_out is not None:
        write_env_file(env_out, env_lines(store, endpoint))
    print(f"가짜 S3: {endpoint} · 버킷 {store.bucket} · 심은 사람 {len(set(seeds))}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
