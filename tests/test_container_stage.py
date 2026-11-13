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
from typing import Any

import pytest
from js_runner import run_js

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import container_stage  # noqa: E402

from capa_simulation.services.object_storage_manifest import FAILURE_LABELS  # noqa: E402

FAKE_ENDPOINT = "http://s3.example.invalid:9020"
FAKE_BUCKET = "Demo_ops_bucket"
FAKE_KEY = "FAKE-s3-access-key-0001"


def _ipv6_loopback_works() -> bool:
    """IPv6 를 끈 PC · 컨테이너가 있다. 임시 응답은 그때 IPv4 로 물러난다(`open_stage`)."""
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
    except OSError:
        return False
    return True


NEEDS_IPV6 = pytest.mark.skipif(not _ipv6_loopback_works(), reason="IPv6 루프백이 없다")


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


def _status(port: int) -> list[str]:
    return _ask(port, "GET", "/_capa_stage")[2].decode("utf-8").split("\n")


def test_the_status_line_follows_what_the_start_script_shows(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """첫 두 줄(제목 · 값 한 줄)은 옛 쪽 스크립트가 읽는 꼴이고, 셋째 줄은 판 번호 · 띠 글 ·
    서버 시각이다."""
    opened, port = stage
    first = _status(port)
    assert first[0] == container_stage.TITLE_STARTING
    assert first[1].startswith("지난 시간 ")
    info = json.loads(first[2])
    assert set(info) == {"v", "band", "tone", "now"}

    opened.begin(managed=True)
    opened.step(container_stage.STEP_INSTALL)
    opened.step(container_stage.STEP_PULL)
    opened.attempt(1)
    pulling = _status(port)
    assert pulling[0] == container_stage.TITLE_PULLING
    assert pulling[1].startswith("1번째 받기 · 지난 시간 ")
    assert json.loads(pulling[2])["v"] > info["v"]
    assert json.loads(pulling[2])["band"] == "데이터 받는 중 · 1번째 받기"
    assert container_stage.TITLE_PULLING in _ask(port, "GET", "/")[2].decode("utf-8")

    opened.fail(1, "remote_empty", wait_seconds=5)
    page = _ask(port, "GET", "/")[2].decode("utf-8")
    assert container_stage.TITLE_REMOTE_EMPTY in page
    assert "다음 확인 5초 뒤" in page and "원격이 비어 있음" in page


def test_an_unknown_failure_word_never_reaches_the_screen(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """갈래 칸은 고정 낱말 표를 지난다 — 서버 글이 끼어들 자리가 없다(참고 줄 · 진단 포함)."""
    opened, port = stage

    opened.fail(1, f"{FAKE_ENDPOINT} {FAKE_BUCKET}", wait_seconds=5)

    for path in ("/", "/_capa_stage"):
        text = _ask(port, "GET", path)[2].decode("utf-8")
        assert FAKE_BUCKET not in text and FAKE_ENDPOINT not in text
    assert FAILURE_LABELS["other"] in _ask(port, "GET", "/")[2].decode("utf-8")


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
        opened.begin(managed=True)
        opened.fail(2, "denied", wait_seconds=300)
        for path in ("/", "/_stcore/health", "/_capa_stage", "/Space?tab=FAKE-query-0001"):
            status, headers, body = _ask(port, "GET", path)
            text = body.decode("utf-8") + json.dumps(headers)
            assert status == 200
            for value in (FAKE_ENDPOINT, FAKE_BUCKET, FAKE_KEY, "capa.example.invalid"):
                assert value not in text
            # 요청 경로 · 질의는 HTML 에 싣지 않는다 — 돌아갈 자리는 표지(`data-return`)뿐이다.
            assert "FAKE-query-0001" not in text and "/Space" not in text
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


@NEEDS_IPV6
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="임시 응답은 Linux 이미지에서만 선다 — Windows 는 남이 쥔 듀얼 스택 포트를 다시 잡는다",
)
def test_a_port_taken_by_someone_else_leaves_an_empty_stage() -> None:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as holder:
        holder.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        holder.bind(("::", 0))
        holder.listen()
        port = int(holder.getsockname()[1])

        opened = container_stage.open_stage(port)

    assert not opened.bound
    opened.begin(managed=True)
    opened.step(container_stage.STEP_PULL)
    opened.attempt(1)
    opened.fail(1, "denied", wait_seconds=300)
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


@NEEDS_IPV6
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
    const seen = { went: [], shown: [], updated: [] };
    const deps = {
      base: data.base,
      mode: data.mode,
      href: data.href,
      fetch: async (url) => {
        const next = answers.shift();
        if (next === "throw") throw new Error("틈");
        const headers = new Set(next.mark ? ["X-Capa-Stage"] : []);
        return { ok: next.ok, headers: { has: (name) => headers.has(name) },
                 text: async () => next.text || "" };
      },
      goTo: (url) => seen.went.push(url),
      show: (headline, detail) => seen.shown.push([headline, detail]),
      update: async (info) => seen.updated.push(info),
    };
    stageTick(deps).then((more) => {
      console.log(JSON.stringify({ more, went: seen.went, shown: seen.shown,
                                   updated: seen.updated }));
    });
    """
)


def _tick(
    answers: list[object], base: str = "/", *, mode: str = "here", href: str = ""
) -> dict[str, object]:
    completed = run_js(
        container_stage.PAGE_SCRIPT + STAGE_TICK_DRIVER,
        what="임시 응답 쪽의 되풀이",
        stdin=json.dumps({"answers": answers, "base": base, "mode": mode, "href": href}),
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_the_page_goes_back_to_the_address_it_was_opened_at() -> None:
    """앱이 뜨면 처음 연 주소를 다시 읽는다 — 재시작 중에 누른 로그아웃 · 로그인 경로가 이어진다."""
    opened = "https://capa.example.invalid/spkg/capa/auth/sso/logout"
    result = _tick([{"ok": True, "mark": False}], "/spkg/capa/", href=opened)

    assert result == {"more": False, "went": [opened], "shown": [], "updated": []}


def test_going_back_to_the_same_address_reloads_the_page() -> None:
    """`#…` 가 붙은 주소에 replace 는 조각 이동만 해 쪽을 다시 받지 않는다 — 같은 주소면 다시
    읽는다."""
    script = container_stage.PAGE_SCRIPT
    assert "url === window.location.href ? window.location.reload()" in script


def test_a_posted_or_callback_page_goes_to_the_base_instead() -> None:
    """POST 로 받은 쪽 · 콜백 경로는 다시 읽으면 다시 보내거나 쓴 코드를 되풀이한다."""
    result = _tick(
        [{"ok": True, "mark": False}], "/spkg/capa/", mode="base", href="https://x.invalid/a"
    )

    assert result["went"] == ["/spkg/capa/"]


def test_the_page_waits_through_a_front_proxy_error() -> None:
    """앞단의 502 · Streamlit 준비 전 503 은 표가 없어도 앱의 답이 아니다."""
    result = _tick([{"ok": False, "mark": False}, {"ok": False, "mark": False}])

    assert result == {"more": True, "went": [], "shown": [], "updated": []}


def test_the_page_waits_through_the_gap_while_the_port_changes_hands() -> None:
    assert _tick(["throw"]) == {"more": True, "went": [], "shown": [], "updated": []}


def test_the_page_takes_the_new_status_while_waiting() -> None:
    line = json.dumps({"v": 3, "band": "앱 시작 중", "tone": "start", "now": 1000})
    result = _tick(
        [{"ok": True, "mark": True}, {"ok": True, "mark": True, "text": f"제목\n값\n{line}"}]
    )

    assert result["updated"] == [{"v": 3, "band": "앱 시작 중", "tone": "start", "now": 1000}]
    assert result["more"] is True and result["shown"] == []


def test_an_older_stage_answer_still_shows_its_two_lines() -> None:
    """셋째 줄이 없는 옛 임시 응답(되돌린 배포)도 두 줄은 보인다."""
    result = _tick(
        [{"ok": True, "mark": True}, {"ok": True, "mark": True, "text": "받는 중\n다시 시도 2회"}]
    )

    assert result["shown"] == [["받는 중", "다시 시도 2회"]]


def test_the_home_guide_names_the_stage_headlines() -> None:
    """HOME Guide 「배포 서버(C-DEP)의 저장」(배포 전 미리 확인 8, 2026-11-12 — 모두가
    보는 자리)은 임시 화면의 제목 셋을 글자 그대로 적는다 — 제목을 바꾸면 Guide 도 같이
    고친다."""
    guide = (
        Path(__file__).resolve().parents[1] / "src" / "capa_simulation" / "guides" / "home.md"
    ).read_text(encoding="utf-8")
    section = guide.partition("#### 배포 서버(C-DEP)의 저장")[2].partition("\n#### ")[0]

    assert section
    for title in (
        container_stage.TITLE_STARTING,
        container_stage.TITLE_PULLING,
        container_stage.TITLE_REMOTE_EMPTY,
    ):
        assert f"`{title}`" in section, title
    assert "DB 동기화" in section and "켜는 날은 앱 관리자가 알립니다" in section


# --------------------------------------------------------------------------- 꼴 · 보기
ROOT = Path(__file__).resolve().parents[1]


def test_the_two_palettes_match_the_app_tokens() -> None:
    """시작 화면은 tokens 를 불러오지 않는다 — 상수가 토큰과 갈라지면 여기서 잡는다."""
    from capa_simulation.design import tokens

    for mode, palette in container_stage.PALETTES.items():
        for _variable, role in container_stage.PALETTE_ROLES:
            assert palette[role] == tokens.palette_value(mode, role), (mode, role)
    assert container_stage.FONT_FAMILY == tokens.FONT_FAMILY


def test_the_mark_is_the_app_mark() -> None:
    svg = (ROOT / "static" / "icons" / "capa_mark.svg").read_text(encoding="utf-8")

    assert f'd="{container_stage.MARK_RING_PATH}"' in svg
    for y in container_stage.MARK_DIE_ORIGINS:
        for x in container_stage.MARK_DIE_ORIGINS:
            assert f'x="{x}" y="{y}" width="12" height="12"' in svg


def test_the_start_scripts_load_neither_streamlit_nor_the_tokens() -> None:
    """포트를 잡는 첫 순간이라 무거운 꾸러미를 끌고 오지 않는다(팔레트는 상수)."""
    code = textwrap.dedent(
        f"""
        import sys
        sys.path[:0] = [{str(ROOT / "scripts")!r}, {str(ROOT / "src")!r}]
        import container_stage, container_start
        names = ("streamlit", "capa_simulation.design.tokens")
        heavy = [name for name in names if name in sys.modules]
        print(",".join(heavy))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == ""


def test_the_clock_words_are_the_same_on_both_sides() -> None:
    seconds = [0, 1, 59, 60, 61, 130, 3599, 3600, 3725, -5]
    driver = (
        container_stage.PAGE_SCRIPT
        + "\nconsole.log(JSON.stringify("
        + json.dumps(seconds)
        + ".map((s) => clockText(s))));"
    )
    from_js = json.loads(run_js(driver, what="지난 시간 글").stdout)

    assert from_js == [container_stage.clock_text(value) for value in seconds]
    assert container_stage.clock_text(130) == "2분 10초"


def _state(**changes: Any) -> container_stage.StageState:
    return container_stage.StageState(started_at=1000.0, **changes)


def test_the_step_line_has_the_pull_cell_only_on_a_pulling_server() -> None:
    plain = container_stage.stage_view(_state(step=container_stage.STEP_INSTALL))
    managed = container_stage.stage_view(_state(managed=True, step=container_stage.STEP_PULL))

    assert plain.steps == (("준비 · 점검", False), ("설치", True), ("앱", False))
    assert managed.steps == (
        ("준비 · 점검", False),
        ("설치", False),
        ("데이터 받기", True),
        ("앱", False),
    )
    assert (plain.chip, plain.title) == (container_stage.CHIP_STARTING, "앱을 시작하는 중입니다")
    assert (managed.chip, managed.title) == (
        container_stage.CHIP_STARTING,
        "데이터를 받는 중입니다",
    )


def test_a_pulling_server_says_starting_until_the_pull_begins() -> None:
    """설치 단계에 「데이터 받는 중」 이라 하지 않는다 — 머리글은 단계를 따른다."""
    view = container_stage.stage_view(_state(managed=True, step=container_stage.STEP_INSTALL))

    assert view.title == container_stage.TITLE_STARTING


def test_the_value_line_counts_the_time_and_the_next_try() -> None:
    pulling = container_stage.stage_view(
        _state(managed=True, step=container_stage.STEP_PULL, attempt=1, trying=True)
    )
    waiting = container_stage.stage_view(
        _state(attempt=2, kind="unreachable", failed_at=1100.0, next_at=1112.0)
    )
    again = container_stage.stage_view(
        _state(attempt=3, trying=True, kind="unreachable", failed_at=1100.0)
    )

    assert container_stage.value_text(pulling, 1130.0) == "1번째 받기 · 지난 시간 2분 10초"
    assert container_stage.value_text(waiting, 1100.5) == "다음 시도 12초 뒤"
    assert container_stage.value_text(again, 1200.0) == "3번째 받는 중"
    assert (waiting.chip, waiting.title) == (
        container_stage.CHIP_RETRY,
        "저장소에 잠시 닿지 못했습니다",
    )


def test_an_empty_remote_is_shown_as_maintenance_not_failure() -> None:
    view = container_stage.stage_view(
        _state(attempt=4, kind="remote_empty", failed_at=1100.0, next_at=1160.0)
    )

    assert (view.chip, view.tone) == (container_stage.CHIP_MAINTENANCE, "check")
    assert view.title == "데이터를 처음 올리는 중입니다"
    assert container_stage.value_text(view, 1100.0) == "다음 확인 60초 뒤"
    assert "원격이 비어 있음" in view.diagnostics and "시도 4회" in view.diagnostics


def test_a_long_retry_adds_the_contact_line_after_ten_minutes() -> None:
    state = _state(attempt=9, kind="timeout", failed_at=1590.0, failing_since=1000.0, next_at=1650)
    view = container_stage.stage_view(state)
    contact = container_stage.StageContact()

    early = container_stage.render_main(view, now=1500.0, version=1, contact=contact)
    late = container_stage.render_main(view, now=1601.0, version=1, contact=contact)

    assert view.late_after == 1600.0
    assert 'data-after="1600000" hidden>계속되면 문의처에 알려 주세요.' in early
    assert 'data-after="1600000">계속되면 문의처에 알려 주세요.' in late


@pytest.mark.parametrize(
    ("method", "path", "back"),
    [
        ("GET", "/", "here"),
        ("GET", "/Space?tab=1", "here"),
        ("GET", "/auth/sso/logout", "here"),
        ("GET", "/auth/callback?code=FAKE-code-0002", "base"),
        ("POST", "/auth/callback", "base"),
        ("POST", "/auth/sso/request", "base"),
    ],
)
def test_the_page_marks_where_to_return_without_the_path(
    stage: tuple[container_stage.Stage, int], method: str, path: str, back: str
) -> None:
    _opened, port = stage

    page = _ask(port, method, path)[2].decode("utf-8")

    assert f'data-return="{back}"' in page
    assert "FAKE-code-0002" not in page


def test_the_contact_line_takes_only_the_mail_shape_and_plain_text() -> None:
    both = container_stage.contact_of(
        {"CAPA_APP_CONTACT_EMAIL": "demo@example.com", "CAPA_ACCESS_CONTACT": "데모 창구 <1>"}
    )
    bad = container_stage.contact_of(
        {"CAPA_APP_CONTACT_EMAIL": "not a mail", "CAPA_ACCESS_CONTACT": "줄\nbreak"}
    )
    view = container_stage.stage_view(_state())

    page = container_stage.render_main(view, now=1000.0, version=0, contact=both)
    empty = container_stage.render_main(view, now=1000.0, version=0, contact=bad)

    assert bad == container_stage.StageContact()
    assert '<p class="contact">문의 <a href="mailto:demo@example.com">demo@example.com</a>' in page
    assert "데모 창구 &lt;1&gt;" in page
    assert 'class="contact"' not in empty


def test_the_page_carries_the_frame_parts_and_both_themes(
    stage: tuple[container_stage.Stage, int],
) -> None:
    _opened, port = stage

    page = _ask(port, "GET", "/")[2].decode("utf-8")

    assert "<title>앱을 시작하는 중입니다 · S.PKG CAPA</title>" in page
    assert "<strong>S.PKG CAPA</strong><span>AX Management</span>" in page
    assert '<p class="chip tone-start">시작 중</p>' in page
    assert '<li class="now">준비 · 점검 <b>지금</b></li>' in page
    assert "@media (prefers-color-scheme: dark)" in page
    assert "<noscript>" in page and container_stage.NOSCRIPT_NOTE in page
    assert "border-top: 4px solid var(--accent)" in page
    assert "#f7f8fa" not in page


# --------------------------------------------------------------------------- 사람이 고쳐야 풀림
@pytest.mark.parametrize(
    ("kind", "title"),
    [
        ("config", "서버 설정 때문에 시작하지 못했습니다"),
        ("cli_missing", "서버 설정 때문에 시작하지 못했습니다"),
        ("denied", "서버 설정 때문에 시작하지 못했습니다"),
        ("no_bucket", "서버 설정 때문에 시작하지 못했습니다"),
        ("disk_full", "서버 디스크가 모자라 시작하지 못했습니다"),
        ("corrupt", "데이터를 되돌려야 열립니다"),
        ("forked", "데이터를 되돌려야 열립니다"),
        ("diverged", "서버 데이터가 정본과 달라 멈췄습니다"),
        ("schema_newer", "앱 판이 데이터보다 오래됐습니다"),
    ],
)
def test_what_a_person_must_fix_says_maintenance_and_who(kind: str, title: str) -> None:
    """「다시 시도 n회」 처럼 기다리면 될 것으로 보이지 않게 — 「점검 중」 · 경우별 쉬운 말."""
    view = container_stage.stage_view(
        _state(attempt=2, kind=kind, failed_at=1100.0, next_at=1400.0)
    )

    assert (view.chip, view.tone, view.title) == (container_stage.CHIP_MAINTENANCE, "check", title)
    assert view.diagnostics[0] == FAILURE_LABELS[kind]
    assert view.diagnostics[1] == container_stage.HUMAN_ACTIONS[kind]
    assert view.diagnostics[-1] == "시도 2회"
    assert "다시 시도" not in view.title + " ".join(view.reasons)
    if kind == "schema_newer":
        assert container_stage.value_text(view, 1100.0) == ""
        assert "문의처" not in view.reasons[0]
    else:
        assert container_stage.value_text(view, 1100.0) == "다음 확인 300초 뒤"
        assert view.reasons[0].endswith("문의처에 알려 주세요.")


@pytest.mark.parametrize(
    ("kind", "facts", "line"),
    [
        (
            "config",
            container_stage.StageFacts(missing_environment=("CAPA_S3_BUCKET", "CAPA_S3_PROFILE")),
            "비어 있는 환경변수: CAPA_S3_BUCKET · CAPA_S3_PROFILE",
        ),
        (
            "disk_full",
            container_stage.StageFacts(needed_bytes=300 * 1024 * 1024, free_bytes=120_000_000),
            "필요 300 MB · 남음 115 MB",
        ),
        ("corrupt", container_stage.StageFacts(seq=41), "멈춘 세대 41"),
        (
            "diverged",
            container_stage.StageFacts(datasets=("simulation", "equipment")),
            "바뀐 DB: 시뮬레이션 · 가용설비",
        ),
        (
            "schema_newer",
            container_stage.StageFacts(datasets=("equipment",), file_version=40, code_version=38),
            "가용설비 판 40 · 코드 판 38",
        ),
    ],
)
def test_the_folded_diagnostics_carry_names_and_numbers(
    stage: tuple[container_stage.Stage, int],
    kind: str,
    facts: container_stage.StageFacts,
    line: str,
) -> None:
    """2026-11-14 보드 D9 — 접힌 「관리자용 진단」 에 이름 · 수(값 · 주소 · 키 · 버킷 이름 아님)."""
    opened, port = stage

    opened.fail(1, kind, wait_seconds=300, facts=facts)

    page = _ask(port, "GET", "/")[2].decode("utf-8")
    folded = page.partition("<summary>관리자용 진단</summary>")[2]
    assert f"<li>{line}</li>" in folded


def test_unknown_numbers_leave_their_line_out() -> None:
    """모르는 수는 짐작하지 않는다 — 받는 도중의 디스크 참 · 세대를 모르는 깨짐."""
    disk = container_stage.stage_view(_state(attempt=1, kind="disk_full"))
    corrupt = container_stage.stage_view(_state(attempt=1, kind="corrupt"))

    assert not any("MB" in line for line in disk.diagnostics)
    assert not any("세대" in line and line[-1].isdigit() for line in corrupt.diagnostics)


def test_a_fact_that_is_not_a_name_or_number_never_reaches_the_screen(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """사실 칸도 닫힌 꼴이다 — 환경변수 이름 꼴 · 아는 DB 이름 · 0 이상의 정수만 지난다."""
    opened, port = stage
    facts = container_stage.StageFacts(
        missing_environment=(FAKE_ENDPOINT, FAKE_BUCKET, "CAPA_S3_BUCKET"),
        datasets=(FAKE_BUCKET, "simulation"),
        seq=-3,
    )

    opened.fail(1, "config", wait_seconds=300, facts=facts)
    opened.fail(2, "diverged", wait_seconds=300, facts=facts)

    page = _ask(port, "GET", "/")[2].decode("utf-8")
    status = _ask(port, "GET", "/_capa_stage")[2].decode("utf-8")
    for text in (page, status):
        assert FAKE_BUCKET not in text and FAKE_ENDPOINT not in text
    assert "바뀐 DB: 시뮬레이션" in page
    assert opened._server is not None
    kept = opened._server.display.read().facts
    assert kept.missing_environment == ("CAPA_S3_BUCKET",) and kept.seq is None
