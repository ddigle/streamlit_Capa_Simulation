# Purpose: 앱이 뜨기 전까지 같은 포트에서 상태 검사에 답하고 접속자에게 준비 중 쪽만 보인다.
"""시작 스크립트의 임시 응답.

C-DEP 의 상태 검사는 시작 제한이 1분이고 무엇을 묻는지 모른다(TCP · `/` · `/_stcore/health`). 설치는
240초까지, 두 DB 받기는 그보다 오래 걸릴 수 있어 시작 스크립트가 **맨 앞에서** 앱의 포트를 잡고 그
셋에 다 답한다. 끝나면 소켓을 닫고 앱이 같은 포트를 잡는다.

**로그인 전 화면이다.** 고정 글과 실패 갈래 낱말(`FAILURE_LABELS`)만 싣는다 — 데이터 · 주소 · 키 ·
버킷 이름이 들어갈 칸이 없다. 이 서버에는 셸 · 로그가 없어 낱말이 없으면 머문 까닭을 알 길이 없다.

- 모든 경로의 GET · HEAD · POST 가 200 + 안내 쪽이다. `/_stcore/health` 는 200 `ok` 이고 그 밖의
  `/_stcore/*` 는 503 이다 — 옛 탭의 재접속이 HTML 을 JSON 으로 읽지 않게.
- 답마다 `X-Capa-Stage: 1` 표가 붙는다. 쪽의 JS 는 health 가 `ok` 이고 표가 **없을** 때만(앱의 답)
  앱으로 간다 — 앞단의 502 · Streamlit 준비 전 503 은 표가 없어도 기다린다.
- 질의까지 찍는 기본 요청 기록을 끈다 — `/auth/callback?code=…` 가 표준 오류에 남는다.
- POST 본문은 상한 안에서 읽어 버린다 — 안 읽고 닫으면 보낸 쪽이 `BrokenPipe` 로 끊긴다.
- 듣는 소켓은 비상속이다(Python 기본) — 시작 스크립트의 자식(pip · aws)이 포트를 물지 않는다.
"""

from __future__ import annotations

import html
import re
import socket
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final
from urllib.parse import urlsplit

from capa_simulation.services.object_storage_manifest import FAILURE_LABELS, FAILURE_OTHER
from capa_simulation.settings import APP_LABEL

STAGE_HEADER: Final = "X-Capa-Stage"
HEALTH_SUFFIX: Final = "/_stcore/health"
STREAMLIT_INFIX: Final = "/_stcore/"
STATUS_SUFFIX: Final = "/_capa_stage"
HEADLINE_PREPARING: Final = "준비 중"
HEADLINE_PULLING: Final = "데이터 받는 중"
SOCKET_TIMEOUT_SECONDS: Final = 5
DISCARD_LIMIT_BYTES: Final = 1024 * 1024
_DISCARD_CHUNK: Final = 64 * 1024
_BASE_PATH: Final = re.compile(r"(?:/[A-Za-z0-9._~-]+)*/?")

_PAGE: Final = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
html, body {{ height: 100%; margin: 0; }}
body {{ display: flex; align-items: center; justify-content: center; font-family: sans-serif;
  background: #f7f8fa; color: #1f2933; }}
main {{ text-align: center; }}
h1 {{ font-size: 1.25rem; font-weight: 600; margin: 0 0 0.5rem; }}
p {{ font-size: 0.875rem; margin: 0; min-height: 1.25rem; color: #52606d; }}
</style>
</head>
<body data-base="{base}">
<main>
<h1 id="headline">{headline}</h1>
<p id="detail">{detail}</p>
</main>
<script>
{script}
</script>
</body>
</html>
"""

# 쪽의 되풀이. 틈(소켓을 닫고 앱이 잡기까지)의 실패는 무시하고 다음 번에 다시 본다.
PAGE_SCRIPT: Final = """
async function stageTick(deps) {
  const base = deps.base;
  try {
    const health = await deps.fetch(base + "_stcore/health", { cache: "no-store" });
    if (health.ok && !health.headers.has("X-Capa-Stage")) {
      deps.goTo(base);
      return false;
    }
    const status = await deps.fetch(base + "_capa_stage", { cache: "no-store" });
    if (status.ok && status.headers.has("X-Capa-Stage")) {
      const lines = (await status.text()).split("\\n");
      deps.show(lines[0] || "", lines[1] || "");
    }
  } catch (error) {
    return true;
  }
  return true;
}
if (typeof document !== "undefined") {
  const deps = {
    base: document.body.dataset.base,
    fetch: (url, options) => window.fetch(url, options),
    goTo: (url) => window.location.replace(url),
    show: (headline, detail) => {
      document.getElementById("headline").textContent = headline;
      document.getElementById("detail").textContent = detail;
    },
  };
  const again = () => stageTick(deps).then((more) => more && window.setTimeout(again, 3000));
  window.setTimeout(again, 3000);
}
"""


def stage_detail(attempts: int, kind: str | None) -> str:
    """머무는 까닭 한 줄 — 시도 수와 고정 낱말. 모르는 갈래는 「그 밖의 실패」 다."""
    if kind is None:
        return ""
    label = FAILURE_LABELS.get(kind, FAILURE_LABELS[FAILURE_OTHER])
    return f"다시 시도 {attempts}회 · {label}"


def base_path_of(public_url: str) -> str:
    """공개 주소의 경로만 — 쪽이 앱으로 돌아갈 자리. 호스트는 싣지 않는다. 꼴이 이상하면 `/`."""
    try:
        path = urlsplit(public_url.strip()).path
    except ValueError:
        return "/"
    if not path or _BASE_PATH.fullmatch(path) is None:
        return "/"
    return path.rstrip("/") + "/"


class _Display:
    """지금 보일 두 줄. 시작 스크립트가 쓰고 응답 스레드가 읽는다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._headline: str = HEADLINE_PREPARING
        self._detail: str = ""

    def set(self, headline: str, detail: str) -> None:
        with self._lock:
            self._headline, self._detail = headline, detail

    def read(self) -> tuple[str, str]:
        with self._lock:
            return self._headline, self._detail


class _StageServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    display: _Display
    base_path: str

    def server_bind(self) -> None:
        # 듀얼스택 — Streamlit 과 같게 IPv4 도 받는다. 기본값은 환경마다 다르다.
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        # `HTTPServer.server_bind` 의 `getfqdn` 을 지나지 않는다 — DNS 없는 컨테이너에서 포트를 잡는
        # 첫 순간이 이름 풀이 시간 초과를 기다린다.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "stage", int(self.server_address[1])

    def handle_error(self, request: object, client_address: object) -> None:
        """끊긴 연결은 조용히 버린다 — 표준 오류에 요청 내용이 남지 않게."""


class _V4StageServer(_StageServer):
    address_family = socket.AF_INET


class _V6StageServer(_StageServer):
    address_family = socket.AF_INET6


class _Handler(BaseHTTPRequestHandler):
    server: _StageServer
    server_version = "capa-stage"
    sys_version = ""
    timeout = SOCKET_TIMEOUT_SECONDS

    def log_message(self, format: str, *args: object) -> None:
        """요청 줄을 찍지 않는다 — 질의에 인증 코드가 든다."""

    def _answer(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(STAGE_HEADER, "1")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _page(self) -> bytes:
        headline, detail = self.server.display.read()
        return _PAGE.format(
            title=html.escape(APP_LABEL),
            base=html.escape(self.server.base_path, quote=True),
            headline=html.escape(headline),
            detail=html.escape(detail),
            script=PAGE_SCRIPT,
        ).encode("utf-8")

    def _respond(self) -> None:
        path = urlsplit(self.path).path
        if path.endswith(HEALTH_SUFFIX):
            self._answer(200, b"ok", "text/plain; charset=utf-8")
        elif STREAMLIT_INFIX in path:
            self._answer(503, b"", "text/plain; charset=utf-8")
        elif path.endswith(STATUS_SUFFIX):
            body = "\n".join(self.server.display.read()).encode("utf-8")
            self._answer(200, body, "text/plain; charset=utf-8")
        else:
            self._answer(200, self._page(), "text/html; charset=utf-8")

    def _discard_body(self) -> None:
        try:
            left = min(int(self.headers.get("Content-Length") or 0), DISCARD_LIMIT_BYTES)
        except ValueError:
            return
        while left > 0:
            chunk = self.rfile.read(min(left, _DISCARD_CHUNK))
            if not chunk:
                return
            left -= len(chunk)

    def do_GET(self) -> None:  # noqa: N802
        self._respond()

    def do_HEAD(self) -> None:  # noqa: N802
        self._respond()

    def do_POST(self) -> None:  # noqa: N802
        self._discard_body()
        self._respond()


class Stage:
    """임시 응답 한 벌. 포트를 못 잡았으면 빈 껍데기다 — 시작 차례는 그대로 이어 간다."""

    def __init__(self, server: _StageServer | None) -> None:
        self._server = server
        self._thread: threading.Thread | None = None

    @property
    def bound(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        if self._server is None:
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="capa-start-stage",
            daemon=True,
        )
        self._thread.start()

    def show(self, *, pulling: bool, attempts: int = 0, kind: str | None = None) -> None:
        if self._server is not None:
            headline = HEADLINE_PULLING if pulling else HEADLINE_PREPARING
            self._server.display.set(headline, stage_detail(attempts, kind))

    def close(self) -> None:
        """듣기를 멈추고 소켓을 닫는다. 이 뒤에 앱이 같은 포트를 잡는다. 두 번 불러도 된다."""
        server, self._server = self._server, None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=SOCKET_TIMEOUT_SECONDS)


def open_stage(port: int, *, base_path: str = "/") -> Stage:
    """포트를 잡아 답하기 시작한다. 잡지 못해도 예외를 내지 않는다 — 앱 띄우기가 먼저다."""
    display = _Display()
    choices: tuple[tuple[type[_StageServer], str], ...] = (
        (_V6StageServer, "::"),
        (_V4StageServer, "0.0.0.0"),
    )
    for factory, host in choices:
        try:
            server = factory((host, port), _Handler)
        except OSError:
            continue
        server.display = display
        server.base_path = base_path
        stage = Stage(server)
        stage.start()
        return stage
    return Stage(None)
