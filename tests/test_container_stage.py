# Purpose: 시작 스크립트의 임시 응답이 상태 검사에 답하고 값 없이 안내만 보이는지 고정한다.

"""임시 응답(`scripts/container_stage.py`).

C-DEP 상태 검사가 무엇을 묻는지 모른다 — TCP · `/` · `/_stcore/health` 를 다 통과해야 한다. 로그인
전 화면이라 환경의 주소 · 버킷 · 키가 본문에 없어야 한다. 쪽의 JS 는 `tests/js_runner.py` 로 돌린다.
"""

from __future__ import annotations

import http.client
import json
import socket
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from js_runner import run_js

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import container_stage  # noqa: E402

from capa_simulation.services.object_storage_manifest import FAILURE_LABELS  # noqa: E402

FAKE_ENDPOINT = "http://s3.example.invalid:9020"
FAKE_BUCKET = "Demo_ops_bucket"
FAKE_KEY = "FAKE-s3-access-key-0001"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def stage() -> Iterator[tuple[container_stage.Stage, int]]:
    port = _free_port()
    opened = container_stage.open_stage(port)
    assert opened.bound
    yield opened, port
    opened.close()


def _ask(
    port: int, method: str, path: str, *, host: str = "127.0.0.1", body: bytes | None = None
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(host, port, timeout=5)
    try:
        connection.request(method, path, body=body)
        answer = connection.getresponse()
        return answer.status, dict(answer.getheaders()), answer.read()
    finally:
        connection.close()


def test_the_health_check_passes_on_every_form_it_may_take(
    stage: tuple[container_stage.Stage, int],
) -> None:
    _opened, port = stage

    with socket.create_connection(("127.0.0.1", port), timeout=5):
        pass
    root = _ask(port, "GET", "/")
    health = _ask(port, "GET", "/_stcore/health")
    headed = _ask(port, "HEAD", "/_stcore/health")

    assert root[0] == 200
    assert (health[0], health[2]) == (200, b"ok")
    assert (headed[0], headed[2]) == (200, b"")


@pytest.mark.parametrize("path", ["/", "/auth/callback?code=abc", "/%EC%95%84%EB%AC%B4", "/Space"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_every_page_answers_with_the_stage_mark(
    stage: tuple[container_stage.Stage, int], method: str, path: str
) -> None:
    _opened, port = stage

    status, headers, body = _ask(port, method, path)

    assert status == 200
    assert headers[container_stage.STAGE_HEADER] == "1"
    assert headers["Cache-Control"] == "no-store"
    assert "text/html" in headers["Content-Type"]
    assert body.startswith(b"<!DOCTYPE html>")


def test_streamlit_paths_other_than_health_do_not_get_a_page(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """옛 탭의 재접속이 HTML 을 JSON 으로 읽지 않게."""
    _opened, port = stage

    for path in ("/_stcore/stream", "/_stcore/host-config"):
        status, headers, body = _ask(port, "GET", path)

        assert status == 503
        assert headers[container_stage.STAGE_HEADER] == "1"
        assert body == b""


def test_the_status_line_follows_what_the_start_script_shows(
    stage: tuple[container_stage.Stage, int],
) -> None:
    opened, port = stage
    assert _ask(port, "GET", "/_capa_stage")[2].decode("utf-8") == "준비 중\n"

    opened.show(pulling=True)
    assert _ask(port, "GET", "/_capa_stage")[2].decode("utf-8") == "데이터 받는 중\n"
    assert "데이터 받는 중" in _ask(port, "GET", "/")[2].decode("utf-8")

    opened.show(pulling=True, attempts=3, kind="remote_empty")
    page = _ask(port, "GET", "/")[2].decode("utf-8")
    assert "다시 시도 3회 · 원격이 비어 있음" in page


def test_an_unknown_failure_word_never_reaches_the_screen(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """갈래 칸은 고정 낱말 표를 지난다 — 서버 글이 끼어들 자리가 없다."""
    opened, port = stage

    opened.show(pulling=True, attempts=1, kind=f"{FAKE_ENDPOINT} {FAKE_BUCKET}")

    text = _ask(port, "GET", "/_capa_stage")[2].decode("utf-8")
    assert FAKE_BUCKET not in text and FAKE_ENDPOINT not in text
    assert FAILURE_LABELS["other"] in text


def test_no_value_from_the_environment_is_on_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """로그인 전 화면이다 — 주소 · 버킷 · 키가 들어갈 칸이 없다. 공개 주소도 경로만 쓴다."""
    monkeypatch.setenv("CAPA_S3_ENDPOINT_URL", FAKE_ENDPOINT)
    monkeypatch.setenv("CAPA_S3_BUCKET", FAKE_BUCKET)
    monkeypatch.setenv("CAPA_S3_ACCESS_KEY", FAKE_KEY)
    port = _free_port()
    opened = container_stage.open_stage(
        port, base_path=container_stage.base_path_of("https://capa.example.invalid/spkg/capa")
    )
    try:
        opened.show(pulling=True, attempts=2, kind="denied")
        for path in ("/", "/_stcore/health", "/_capa_stage"):
            status, headers, body = _ask(port, "GET", path)
            text = body.decode("utf-8") + json.dumps(headers)
            assert status == 200
            for value in (FAKE_ENDPOINT, FAKE_BUCKET, FAKE_KEY, "capa.example.invalid"):
                assert value not in text
    finally:
        opened.close()


@pytest.mark.parametrize(
    ("public_url", "base"),
    [
        ("", "/"),
        ("https://capa.example.invalid", "/"),
        ("https://capa.example.invalid/", "/"),
        ("https://capa.example.invalid/spkg/capa", "/spkg/capa/"),
        ("https://capa.example.invalid/spkg/capa/", "/spkg/capa/"),
        ('https://capa.example.invalid/"><script>', "/"),
    ],
)
def test_the_page_returns_under_the_public_path(public_url: str, base: str) -> None:
    assert container_stage.base_path_of(public_url) == base


def test_a_large_form_post_is_read_before_the_answer(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """form_post 본문을 안 읽고 닫으면 보낸 쪽이 `BrokenPipe` 로 끊긴다."""
    _opened, port = stage

    status, _headers, _body = _ask(port, "POST", "/auth/callback", body=b"x" * (512 * 1024))

    assert status == 200


def test_requests_are_not_written_to_the_log(
    stage: tuple[container_stage.Stage, int], capfd: pytest.CaptureFixture[str]
) -> None:
    """질의에 인증 코드가 든다."""
    _opened, port = stage

    _ask(port, "GET", "/auth/callback?code=FAKE-code-0001")

    captured = capfd.readouterr()
    assert "FAKE-code-0001" not in captured.err + captured.out


def test_a_slow_connection_does_not_hold_up_others(
    stage: tuple[container_stage.Stage, int],
) -> None:
    _opened, port = stage

    with socket.create_connection(("127.0.0.1", port), timeout=5):
        assert _ask(port, "GET", "/_stcore/health")[0] == 200


def test_the_same_port_can_be_taken_right_after_closing() -> None:
    port = _free_port()
    opened = container_stage.open_stage(port)
    _ask(port, "GET", "/")

    opened.close()
    opened.close()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as next_owner:
        next_owner.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        next_owner.bind(("127.0.0.1", port))


def test_a_port_taken_by_someone_else_leaves_an_empty_stage() -> None:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as holder:
        holder.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        holder.bind(("::", 0))
        holder.listen()
        port = int(holder.getsockname()[1])

        opened = container_stage.open_stage(port)

    assert not opened.bound
    opened.show(pulling=True, attempts=1, kind="denied")
    opened.close()


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="/proc 가 있는 Linux 만")
def test_children_of_the_start_script_do_not_hold_the_port(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """듣는 소켓이 비상속이어야 pip · aws 가 살아 있어도 앱이 포트를 잡는다."""
    opened, port = stage
    server = opened._server
    assert server is not None
    assert server.socket.get_inheritable() is False

    completed = subprocess.run(
        [sys.executable, "-c", "import os; print(sorted(os.listdir('/proc/self/fd')))"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert str(server.socket.fileno()) not in json.loads(completed.stdout.replace("'", '"'))
    assert port > 0


def test_both_address_families_are_answered(
    stage: tuple[container_stage.Stage, int],
) -> None:
    _opened, port = stage

    assert _ask(port, "GET", "/_stcore/health", host="127.0.0.1")[0] == 200
    assert _ask(port, "GET", "/_stcore/health", host="::1")[0] == 200


STAGE_TICK_DRIVER = textwrap.dedent(
    """
    const data = JSON.parse(require("fs").readFileSync(0, "utf-8"));
    const answers = data.answers.slice();
    const seen = { went: [], shown: [] };
    const deps = {
      base: data.base,
      fetch: async (url) => {
        const next = answers.shift();
        if (next === "throw") throw new Error("틈");
        const headers = new Set(next.mark ? ["X-Capa-Stage"] : []);
        return { ok: next.ok, headers: { has: (name) => headers.has(name) },
                 text: async () => next.text || "" };
      },
      goTo: (url) => seen.went.push(url),
      show: (headline, detail) => seen.shown.push([headline, detail]),
    };
    stageTick(deps).then((more) => {
      console.log(JSON.stringify({ more, went: seen.went, shown: seen.shown }));
    });
    """
)


def _tick(answers: list[object], base: str = "/") -> dict[str, object]:
    completed = run_js(
        container_stage.PAGE_SCRIPT + STAGE_TICK_DRIVER,
        what="임시 응답 쪽의 되풀이",
        stdin=json.dumps({"answers": answers, "base": base}),
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_the_page_goes_to_the_app_only_on_the_apps_own_answer() -> None:
    result = _tick([{"ok": True, "mark": False}], "/spkg/capa/")

    assert result == {"more": False, "went": ["/spkg/capa/"], "shown": []}


def test_the_page_waits_through_a_front_proxy_error() -> None:
    """앞단의 502 · Streamlit 준비 전 503 은 표가 없어도 앱의 답이 아니다."""
    result = _tick([{"ok": False, "mark": False}, {"ok": False, "mark": False}])

    assert result == {"more": True, "went": [], "shown": []}


def test_the_page_waits_through_the_gap_while_the_port_changes_hands() -> None:
    assert _tick(["throw"]) == {"more": True, "went": [], "shown": []}


def test_the_page_shows_the_new_status_while_waiting() -> None:
    result = _tick(
        [{"ok": True, "mark": True}, {"ok": True, "mark": True, "text": "받는 중\n다시 시도 2회"}]
    )

    assert result == {"more": True, "went": [], "shown": [["받는 중", "다시 시도 2회"]]}
