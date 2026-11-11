# Purpose: 시험 공용 설정이 루프백 요청을 창의 프록시 밖으로 돌리고 하위 프로세스까지 잇는지 본다.

"""`tests/conftest.py` 의 `_loopback_skips_proxy`.

사내 PC 창에는 프록시 환경변수가 있다. 시험이 127.0.0.1 에 띄운 가짜 서버로 가는 요청이
프록시로 가면 서버 대신 프록시가 답한다(가짜 S3 시험이 403 을 받는다).
닿지 않는 프록시를 창에 세워 두고 루프백이 곧장 가는지 본다.
"""

from __future__ import annotations

import http.server
import os
import subprocess
import sys
import threading
import urllib.request
from collections.abc import Iterator

import pytest
from conftest import LOOPBACK_NO_PROXY, with_loopback_no_proxy

UNREACHABLE_PROXY = "http://proxy.invalid:3128"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("", "127.0.0.1,[::1],localhost"),
        ("corp.example", "corp.example,127.0.0.1,[::1],localhost"),
        ("localhost,.corp.example,", "localhost,.corp.example,127.0.0.1,[::1]"),
        ("*", "*"),
        (" * ", "*,127.0.0.1,[::1],localhost"),
    ],
    ids=["empty", "kept", "only-missing", "all", "padded-star"],
)
def test_the_loopback_names_go_after_what_was_there(before: str, after: str) -> None:
    assert with_loopback_no_proxy(before) == after


@pytest.fixture()
def behind_a_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(name, UNREACHABLE_PROXY)


@pytest.mark.parametrize("host", ["127.0.0.1:9000", "[::1]:9000", "localhost:9000"])
@pytest.mark.usefixtures("behind_a_proxy")
def test_every_loopback_name_skips_the_proxy(host: str) -> None:
    assert urllib.request.proxy_bypass(host)


class _NoContent(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def loopback_port() -> Iterator[int]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _NoContent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()


@pytest.mark.usefixtures("behind_a_proxy")
def test_a_request_that_follows_the_environment_reaches_the_loopback_server(
    loopback_port: int,
) -> None:
    """환경을 따르는 기본 요청기다 — 프록시로 갔다면 닿지 않는 주소라 실패한다."""
    opener = urllib.request.build_opener()

    with opener.open(f"http://127.0.0.1:{loopback_port}/", timeout=5) as answer:
        assert answer.status == 204


CHILD_PROBE = """
import os, sys, urllib.request
print(os.environ.get("no_proxy", ""))
print(sum(bool(urllib.request.proxy_bypass(host)) for host in sys.argv[1:]))
"""


@pytest.mark.usefixtures("behind_a_proxy")
def test_child_processes_inherit_the_loopback_names() -> None:
    """하위 프로세스가 같은 값을 받고, 그 안에서도 루프백 셋이 프록시를 비켜 간다.

    이름을 글자로 찾지 않고 우회 판정으로 본다 — 창의 값이 `*`(모두 우회)면 덧붙이지 않는다.
    """
    hosts = [f"{name}:9000" for name in LOOPBACK_NO_PROXY]
    completed = subprocess.run(
        [sys.executable, "-c", CHILD_PROBE, *hosts],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )

    inherited, bypassed = completed.stdout.splitlines()
    assert inherited == os.environ["no_proxy"]
    assert bypassed == str(len(hosts))
