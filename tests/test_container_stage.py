# Purpose: 시작 스크립트의 임시 응답이 상태 검사에 답하고 값 없이 안내만 보이는지 고정한다.

"""임시 응답(`scripts/container_stage.py`).

C-DEP 상태 검사가 무엇을 묻는지 모른다 — TCP · `/` · `/_stcore/health` 를 다 통과해야 한다. 로그인
전 화면이라 환경의 주소 · 버킷 · 키가 본문에 없어야 한다. 쪽의 JS 는 `tests/js_runner.py` 로 돌린다.
"""

from __future__ import annotations

import html
import http.client
import json
import re
import socket
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from dataclasses import replace
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


def test_a_failure_of_unknown_cause_does_not_say_the_store_was_not_reached(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """원인을 모르는 실패(`other` — 알아보지 못한 aws 오류 · 로컬 OSError · 시작 줄을 읽지
    못함)는 제목 · 상태 줄 · 열어 둔 탭의 띠 어디에도 「저장소에 잠시 닿지 못함」 을 말하지 않는다
    — 닿지 못함 · 시간 초과일 때만 그 말이다(UI-DAT-11)."""
    opened, port = stage

    opened.fail(1, "other", wait_seconds=5)
    other = _status(port)
    other_page = _ask(port, "GET", "/")[2].decode("utf-8")
    opened.fail(2, "unreachable", wait_seconds=5)
    reached = _status(port)

    assert other[0] == container_stage.TITLE_TRANSIENT_UNKNOWN == "데이터를 잠시 받지 못했습니다"
    assert json.loads(other[2])["band"] == "데이터를 잠시 받지 못함 · 다시 시도 중"
    assert "닿지 못" not in other_page.split("<script", 1)[0]
    assert reached[0] == container_stage.TITLE_TRANSIENT == "저장소에 잠시 닿지 못했습니다"
    assert json.loads(reached[2])["band"] == "저장소에 잠시 닿지 못함 · 다시 시도 중"


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


def _return_ways(cases: list[list[str]]) -> list[str]:
    driver = (
        container_stage.PAGE_SCRIPT
        + "\nconsole.log(JSON.stringify("
        + json.dumps(cases)
        + ".map(([mode, target, current]) => returnWay(mode, target, current))));"
    )
    result = json.loads(run_js(driver, what="앱으로 갈 길").stdout)
    assert isinstance(result, list)
    return result


def test_going_back_to_the_same_address_reloads_the_page() -> None:
    """`#…` 가 붙은 주소에 replace 는 조각 이동만 해 쪽을 다시 받지 않는다 — 같은 주소면 다시
    읽는다. 쪽의 `goTo` 가 이 판정을 쓴다."""
    same = "https://capa.example.invalid/spkg/capa/Space#floor"

    assert _return_ways([["here", same, same], ["here", "/spkg/capa/", same]]) == [
        "reload",
        "replace",
    ]
    assert "returnWay(body.dataset.return, url, window.location.href)" in (
        container_stage.PAGE_SCRIPT
    )


def test_a_lost_access_request_is_opened_again_without_sending_it() -> None:
    """재시작 틈에 받은 「접속 권한 신청」 은 앱이 뜨면 같은 주소를 GET 으로 연다(앱이 거절 화면으로
    보낸다) — 다시 읽으면(reload) 브라우저가 POST 를 다시 보낸다."""
    opened = "https://capa.example.invalid/spkg/capa/auth/sso/register"
    result = _tick([{"ok": True, "mark": False}], "/spkg/capa/", mode="resend", href=opened)

    assert result == {"more": False, "went": [opened], "shown": [], "updated": []}
    assert _return_ways([["resend", opened, opened]]) == ["replace"]


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


def test_the_diagnostics_fold_has_the_app_admin_diagnostic_name() -> None:
    """접힌 진단의 이름은 앱 안 판(코어 화면 오류 카드 · 앱 시작 실패 판)과 같은 글이다 — 시작
    화면은 Streamlit 을 부르지 않아 로그인 화면 틀의 낱말을 쓰고, 그 글이 앱 안 판의 글과 같은지
    여기서 맞댄다(설계 규칙 UI-CON-02)."""
    from capa_simulation.components.diagnostic_copy import ADMIN_DIAGNOSTIC_LABEL

    assert container_stage.DIAGNOSTICS_SUMMARY == ADMIN_DIAGNOSTIC_LABEL


def _css_variables(css: str) -> dict[str, dict[str, str]]:
    """`:root` 의 밝은 변수와 `prefers-color-scheme: dark` 안의 어두운 변수."""
    light_part, _, dark_part = css.partition("@media (prefers-color-scheme: dark)")

    def found(part: str) -> dict[str, str]:
        return dict(re.findall(r"--([a-z-]+):\s*([^;]+);", part))

    return {"light": found(light_part), "dark": found(dark_part)}


def test_the_stage_chips_are_the_login_frame_table() -> None:
    """2026-11-14 보드 decided 8 — 시작 임시 화면의 표지 낱말과 색은 로그인 화면 틀
    (`auth/page_frame`)과 한 표다. 결마다 틀의 같은 표지 키의 낱말이 서고, 그 색 변수는 두 테마
    모두 틀이 그리는 값과 같다(시작 중 · 점검 중 · 다시 시도 — 셋 다)."""
    from capa_simulation.auth import page_frame
    from capa_simulation.design import tokens

    views = {
        "start": container_stage.stage_view(_state()),
        "retry": container_stage.stage_view(_state(attempt=1, kind="unreachable")),
        "check": container_stage.stage_view(_state(attempt=1, kind="remote_empty")),
    }
    stage_css = _css_variables(container_stage.page_css())
    frame_css = _css_variables(page_frame.palette_css())
    page = container_stage.page_css()

    assert set(views) == set(container_stage.TONE_CHIPS)
    for tone, view in views.items():
        chip = container_stage.TONE_CHIPS[tone]
        assert view.tone == tone
        assert view.chip == page_frame.CHIP_WORDS[chip]
        assert f".tone-{tone} {{ color: var(--chip-{chip}); }}" in page
        for mode in ("light", "dark"):
            role = page_frame.CHIP_ROLES[chip]
            assert stage_css[mode][f"chip-{chip}"] == tokens.palette_value(mode, role), (tone, mode)
            assert stage_css[mode][f"chip-{chip}"] == frame_css[mode][f"chip-{chip}"], (tone, mode)


def test_the_frame_words_are_the_login_frame_words() -> None:
    """접힌 진단 · 문의 줄 · 참고 줄의 머리 낱말도 로그인 화면 틀의 낱말이다 — 앱 안 멈춤 판
    (`components/stop_panel.py`)도 같은 낱말이다(UI-CON-02)."""
    from capa_simulation.auth import page_frame
    from capa_simulation.components import stop_panel

    contact = container_stage.StageContact(email="demo@example.com")
    view = container_stage.stage_view(_state(attempt=1, kind="timeout", failed_at=1100.0))
    page = container_stage.render_main(view, now=1100.0, version=0, contact=contact)

    assert container_stage.DIAGNOSTICS_SUMMARY == page_frame.DIAGNOSTIC_LABEL
    assert f"<summary>{page_frame.DIAGNOSTIC_LABEL}</summary>" in page
    assert _line_text(page, "contact").startswith(f"{page_frame.CONTACT_LABEL} ")
    assert _line_text(page, "ref").startswith(f"{page_frame.REFERENCE_LABEL} ")
    assert (stop_panel.CONTACT_PREFIX, stop_panel.REFERENCE_PREFIX) == (
        page_frame.CONTACT_LABEL,
        page_frame.REFERENCE_LABEL,
    )


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

    assert container_stage.value_text(pulling, 1130.0) == "1번째 받기 · 지난 시간 2분 10초"
    assert container_stage.value_text(waiting, 1100.5) == "다음 시도 12초 뒤"
    assert (waiting.chip, waiting.title) == (
        container_stage.CHIP_RETRY,
        "저장소에 잠시 닿지 못했습니다",
    )


def test_a_retry_that_is_pulling_shows_the_clock_and_the_pull_notes() -> None:
    """잠시 닿지 못한 뒤 다시 받는 몇 분은 멈춘 것처럼 보이지 않는다 — 값 줄이 지난 시간과 함께
    흐르고, 첫 받기의 두 노트(몇 분 · CI/CD 다시 누르지 않기)가 서며, 열어 둔 탭의 띠는 「데이터
    받는 중 · n번째 받기」 다. 기다리는 동안에는 노트 없이 다음 시도까지 센다."""
    waiting = container_stage.stage_view(
        _state(attempt=2, kind="unreachable", failed_at=1100.0, next_at=1112.0)
    )
    again = container_stage.stage_view(
        _state(attempt=3, trying=True, kind="unreachable", failed_at=1100.0)
    )
    page = container_stage.render_main(
        again, now=1200.0, version=1, contact=container_stage.StageContact()
    )

    assert container_stage.value_text(again, 1200.0) == "3번째 받는 중 · 지난 시간 3분 20초"
    assert 'data-since="1000000" data-progress="3번째 받는 중"' in page
    assert again.notes == (container_stage.NOTE_MINUTES, container_stage.NOTE_NO_CICD)
    assert again.band == "데이터 받는 중 · 3번째 받기"
    assert waiting.notes == () and waiting.band == "저장소에 잠시 닿지 못함 · 다시 시도 중"


# 「다시 시도」 판으로 오는 갈래 — 원격이 비어 있음 · 사람 갈래가 아닌 낱말 표의 키 전부.
RETRY_KINDS = sorted(kind for kind in FAILURE_LABELS if container_stage.retry_kind(kind))


@pytest.mark.parametrize("kind", RETRY_KINDS)
def test_only_a_store_not_reached_is_titled_so(kind: str) -> None:
    """표지는 일어난 것만 말한다(UI-DAT-11) — 「저장소에 잠시 닿지 못했습니다」 · 띠 「저장소에
    잠시 닿지 못함 · …」 는 닿지 못함 · 시간 초과(닿지 못함의 한 꼴)일 때만이다. 원인을 모르는
    실패(`other`)와 그 밖에 이 판으로 오는 갈래는 원인을 말하지 않는 「데이터를 잠시 받지
    못했습니다」 · 「데이터를 잠시 받지 못함 · 다시 시도 중」 이고, 표지 · 까닭 · 10분 문의 줄 ·
    값 줄 · 진단 할 일은 같다(제목 낱말은 같은 화면의 「데이터를 받는 중입니다」 · 「데이터를
    처음 올리는 중입니다」 와 짝)."""
    state = _state(attempt=2, kind=kind, failed_at=1100.0, failing_since=1000.0, next_at=1112.0)
    view = container_stage.stage_view(state)
    reached_view = container_stage.stage_view(replace(state, kind="unreachable"))
    reached = kind in ("unreachable", "timeout")

    assert view.title == (
        "저장소에 잠시 닿지 못했습니다" if reached else "데이터를 잠시 받지 못했습니다"
    )
    assert view.band == (
        "저장소에 잠시 닿지 못함 · 다시 시도 중"
        if reached
        else "데이터를 잠시 받지 못함 · 다시 시도 중"
    )
    assert (view.tone, view.chip) == ("retry", container_stage.CHIP_RETRY)
    assert view.reasons == (container_stage.REASON_TRANSIENT,)
    assert (view.late_note, view.late_after) == (container_stage.NOTE_LONG_RETRY, 1600.0)
    assert container_stage.value_text(view, 1100.0) == "다음 시도 12초 뒤"
    assert view.diagnostics[1:] == reached_view.diagnostics[1:]
    assert view.diagnostics[0] == FAILURE_LABELS[kind]


def test_the_retry_screen_takes_the_store_pair_and_the_unknown_cause() -> None:
    """닿지 못함 · 시간 초과 · 원인 모름은 늘 「다시 시도」 판이다 — 갈래 표가 바뀌어 빠지면 위
    시험이 그 갈래를 보지 않게 되므로 여기서 잡는다."""
    assert {"unreachable", "timeout", "other"} <= set(RETRY_KINDS)


def test_the_ten_minute_line_counts_only_the_unbroken_retry_run(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """10분 문의 줄은 잠시 닿지 못함이 끊김 없이 이어진 시간으로 센다 — 이관 전 · 사람 갈래에 오래
    머문 뒤의 첫 잠시 닿지 못함에 곧바로 서지 않는다."""
    moments = iter((1000.0, 1300.0, 4000.0, 4030.0, 4100.0))
    opened, _port = stage
    assert opened._server is not None
    opened._server.display.clock = lambda: next(moments)

    opened.fail(1, "unreachable", wait_seconds=5)
    opened.fail(2, "remote_empty", wait_seconds=60)
    opened.fail(3, "timeout", wait_seconds=5)
    opened.fail(4, "other", wait_seconds=5)
    first = container_stage.stage_view(opened._server.display.read())
    opened.fail(5, "denied", wait_seconds=300)
    human = opened._server.display.read()

    assert first.late_after == 4000.0 + container_stage.LONG_RETRY_SECONDS
    assert human.failing_since == 4100.0


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


@pytest.mark.parametrize("kind", ["remote_empty", "corrupt", "forked"])
def test_a_pull_after_init_or_rollback_shows_the_clock_and_the_pull_notes(kind: str) -> None:
    """관리자가 처음 올리기(init) · 되돌리기(rollback)를 한 직후의 다음 확인은 그대로 몇 분 받기다 —
    실제 내려받기로 넘어간 뒤는 잠시 닿지 못한 뒤의 다시 받기와 같은 값 줄(「n번째 받는 중 · 지난
    시간」, 서버 시작부터)과 첫 받기의 두 노트가 선다. 표지 · 제목은 그 갈래 그대로이고, 열어 둔
    탭의 재시작 띠도 같은 때 같은 말 「데이터 받는 중 · n번째 받기」 다(다시 받기와 한 글)."""
    waiting = container_stage.stage_view(
        _state(attempt=4, kind=kind, failed_at=1100.0, next_at=1160.0)
    )
    again = container_stage.stage_view(
        _state(attempt=5, trying=True, downloading=True, kind=kind, failed_at=1100.0)
    )
    page = container_stage.render_main(
        again, now=1200.0, version=1, contact=container_stage.StageContact()
    )

    assert container_stage.value_text(again, 1200.0) == "5번째 받는 중 · 지난 시간 3분 20초"
    assert 'data-since="1000000" data-progress="5번째 받는 중"' in page
    assert again.notes == (container_stage.NOTE_MINUTES, container_stage.NOTE_NO_CICD)
    assert container_stage.NOTE_NO_CICD in page
    assert (again.chip, again.title) == (waiting.chip, waiting.title)
    assert again.band == "데이터 받는 중 · 5번째 받기"
    retry = container_stage.stage_view(
        _state(attempt=5, trying=True, kind="unreachable", failed_at=1100.0)
    )
    assert again.band == retry.band
    assert waiting.band.startswith("점검 중 · ")
    assert waiting.notes == () and container_stage.value_text(waiting, 1100.0).startswith("다음 ")


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("remote_empty", "확인하는 중"),
        ("corrupt", "다시 확인하는 중"),
        ("forked", "다시 확인하는 중"),
    ],
)
def test_a_check_before_init_or_rollback_is_not_a_pull(kind: str, value: str) -> None:
    """처음 올리기 · 되돌리기 전의 짧은 확인(1분 · 300초)은 받기가 아니다 — 실제 내려받기로 넘어가기
    전에는 「n번째 받는 중 · 지난 시간」 도 받는 동안의 두 노트도 서지 않는다(UI-DAT-11)."""
    waiting = container_stage.stage_view(
        _state(attempt=4, kind=kind, failed_at=1100.0, next_at=1160.0)
    )
    checking = container_stage.stage_view(
        _state(attempt=5, trying=True, kind=kind, failed_at=1100.0)
    )
    page = container_stage.render_main(
        checking, now=1200.0, version=1, contact=container_stage.StageContact()
    )

    assert container_stage.value_text(checking, 1200.0) == value
    assert checking.notes == () and checking.since is None
    assert "받는 중" not in page and container_stage.NOTE_NO_CICD not in page
    assert (checking.chip, checking.title, checking.band) == (
        waiting.chip,
        waiting.title,
        waiting.band,
    )


def test_the_stage_shows_a_pull_only_once_the_download_is_seen() -> None:
    """받기는 하위 프로세스라 시작 스크립트는 그 순간을 모른다 — 임시 응답이 상태를 읽을 때
    물음(`download_seen` — 받기가 남기는 표지)을 묻고, 넘어갔으면 판을 한 번 올린다(열어 둔 쪽이
    본문을 갈아 끼운다). 시도가 돌지 않는 동안은 앞 시도의 표지가 남았어도 묻지 않고, 다음 시도는
    새로 센다."""
    port = _free_port()
    seen = [False]
    opened = container_stage.open_stage(port, download_seen=lambda: seen[0])
    assert opened.bound
    try:
        opened.begin(managed=True)
        opened.step(container_stage.STEP_PULL)
        opened.attempt(1)
        opened.fail(1, "remote_empty", wait_seconds=60)
        failed = json.loads(_status(port)[2])["v"]
        seen[0] = True
        waiting = _status(port)
        assert waiting[1].startswith("다음 확인 ")
        assert json.loads(waiting[2])["v"] == failed

        seen[0] = False
        opened.attempt(2)
        checking = _status(port)
        assert checking[1] == "확인하는 중"
        assert json.loads(checking[2])["band"] == "점검 중 · 데이터를 처음 올리는 중"
        assert container_stage.NOTE_NO_CICD not in _ask(port, "GET", "/")[2].decode("utf-8")

        seen[0] = True
        pulling = _status(port)
        again = _status(port)
        assert pulling[1].startswith("2번째 받는 중 · 지난 시간 ")
        assert json.loads(pulling[2])["band"] == "데이터 받는 중 · 2번째 받기"
        assert json.loads(pulling[2])["v"] == json.loads(checking[2])["v"] + 1
        assert json.loads(again[2])["v"] == json.loads(pulling[2])["v"]
        assert container_stage.NOTE_NO_CICD in _ask(port, "GET", "/")[2].decode("utf-8")

        opened.fail(2, "corrupt", wait_seconds=300)
        seen[0] = False
        opened.attempt(3)
        assert _status(port)[1] == "다시 확인하는 중"
    finally:
        opened.close()


def _checking(state: container_stage.StageState) -> container_stage.StageState:
    return replace(
        state,
        managed=True,
        step=container_stage.STEP_PULL,
        kind="remote_empty",
        attempt=5,
        trying=True,
    )


def test_a_question_that_fails_or_races_leaves_the_short_check() -> None:
    """물음이 예외를 내면 받지 않는 것으로 본다(쪽은 그대로 답한다). 묻는 사이 시작 스크립트가
    상태를 바꿨으면(그 시도를 실패로 닫음) 올리지 않는다 — 끝난 시도를 「받는 중」 으로 되살리지
    않는다."""

    def broken() -> bool:
        raise OSError(5, "표지를 못 읽음")

    unread = container_stage._Display(lambda: 1000.0, broken)
    unread.change(_checking)
    assert unread.read().downloading is False

    holder: list[container_stage._Display] = []

    def racing() -> bool:
        holder[0].change(lambda state: replace(state, trying=False, next_at=1060.0))
        return True

    racy = container_stage._Display(lambda: 1000.0, racing)
    holder.append(racy)
    racy.change(_checking)
    state = racy.read()

    assert (state.trying, state.downloading) == (False, False)
    assert container_stage.value_text(container_stage.stage_view(state), 1000.0) == (
        "다음 확인 60초 뒤"
    )


@pytest.mark.parametrize(
    "kind", ["config", "cli_missing", "denied", "no_bucket", "disk_full", "diverged"]
)
def test_a_recheck_fixed_by_ci_cd_keeps_its_short_value(kind: str) -> None:
    """CI/CD 로 고치는 사람 갈래의 다시 확인은 「다시 확인하는 중」 그대로다 — 「받는 동안 CI/CD 를
    다시 누르면 …」 노트가 그 갈래의 할 일(CI/CD)과 어긋나지 않게."""
    again = container_stage.stage_view(_state(attempt=5, trying=True, kind=kind, failed_at=1100.0))

    assert container_stage.value_text(again, 1200.0) == "다시 확인하는 중"
    assert again.notes == () and again.since is None


@pytest.mark.parametrize(
    ("method", "path", "back"),
    [
        ("GET", "/", "here"),
        ("GET", "/Space?tab=1", "here"),
        ("GET", "/auth/sso/logout", "here"),
        ("GET", "/auth/callback?code=FAKE-code-0002", "base"),
        ("POST", "/auth/callback", "base"),
        ("POST", "/auth/sso/request", "base"),
        ("POST", "/auth/sso/register", "resend"),
        ("GET", "/auth/sso/register", "here"),
    ],
)
def test_the_page_marks_where_to_return_without_the_path(
    stage: tuple[container_stage.Stage, int], method: str, path: str, back: str
) -> None:
    _opened, port = stage

    page = _ask(port, method, path)[2].decode("utf-8")

    assert f'data-return="{back}"' in page
    assert "FAKE-code-0002" not in page


def test_a_lost_access_request_asks_to_press_again(
    stage: tuple[container_stage.Stage, int],
) -> None:
    """재시작 틈에 누른 「접속 권한 신청」(POST)은 앱에 닿지 않았다 — 그 쪽에만 「다시 눌러 주세요」
    한 줄이 선다. 다른 POST · 같은 경로의 GET 에는 없다. 공개 주소 바탕 아래 경로도 같다."""
    _opened, port = stage
    line = f'<p class="lost" data-keep>{html.escape(container_stage.NOTE_REGISTER_LOST)}</p>'

    lost = _ask(port, "POST", "/auth/sso/register", body=b"t=FAKE-mark-0003")[2].decode("utf-8")
    other = _ask(port, "POST", "/auth/callback", body=b"code=FAKE-code-0002")[2].decode("utf-8")
    shown = _ask(port, "GET", "/auth/sso/register")[2].decode("utf-8")

    assert line in lost and "FAKE-mark-0003" not in lost
    assert line not in other and line not in shown
    assert container_stage.return_mode("POST", "/spkg/capa/auth/sso/register") == "resend"
    assert container_stage.return_mode("POST", "/spkg/capa/auth/sso/registered") == "base"
    # 제목 · 까닭 바로 아래 — 단계 줄 · 값 줄보다 먼저 읽힌다.
    assert lost.index("</h1>") < lost.index(line) < lost.index('class="steps"')


def test_the_lost_request_line_names_the_button_of_the_denied_screen() -> None:
    """한 개념 한 이름(UI-CON-02) — 거절 화면 단추 이름 그대로다. 시작 화면은 `auth/web` 을
    불러오지 않아 글을 따로 들고 여기서 맞댄다."""
    from capa_simulation.auth import web

    assert container_stage.NOTE_REGISTER_LOST.startswith(f"「{web.REGISTER_LABEL}」 ")


CARRY_DRIVER = textwrap.dedent(
    """
    const data = JSON.parse(require("fs").readFileSync(0, "utf-8"));
    const log = [];
    const node = (name) => ({ name, after: (moved) => log.push([name, moved.name]) });
    const fresh = {
      querySelector: (selector) =>
        selector === "[data-keep]" && data.freshHasLine ? node("line") : null,
      querySelectorAll: (selector) =>
        selector === "h1, .reason" ? data.marks.map((name) => node(name)) : [],
    };
    carryKept(fresh, data.kept ? node("kept") : null);
    console.log(JSON.stringify(log));
    """
)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ({"kept": True, "freshHasLine": False, "marks": ["h1"]}, [["h1", "kept"]]),
        (
            {"kept": True, "freshHasLine": False, "marks": ["h1", "reason"]},
            [["reason", "kept"]],
        ),
        ({"kept": True, "freshHasLine": True, "marks": ["h1"]}, []),
        ({"kept": False, "freshHasLine": False, "marks": ["h1"]}, []),
    ],
)
def test_the_press_again_line_survives_a_new_stage(
    case: dict[str, object], expected: list[list[str]]
) -> None:
    """판이 바뀌면 쪽은 바탕 주소 GET 으로 받은 새 `<main>` 으로 갈아 끼운다 — 그 판은 잃은 신청을
    모르므로 「다시 눌러 주세요」 한 줄을 옛 판에서 옮겨 제목 · 까닭 바로 아래에 단다(한 번만)."""
    completed = run_js(
        container_stage.PAGE_SCRIPT + CARRY_DRIVER,
        what="다시 눌러 주세요 한 줄 옮기기",
        stdin=json.dumps(case),
    )

    assert json.loads(completed.stdout) == expected
    assert 'carryKept(fresh, main().querySelector("[data-keep]"))' in (container_stage.PAGE_SCRIPT)


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


def _line_text(page: str, css_class: str) -> str:
    """그 칸(`<p class=…>`) 하나의 글 — 태그를 걷고 HTML 이스케이프를 푼다."""
    found = re.search(rf'<p class="{css_class}">(?P<body>.*?)</p>', page)
    assert found is not None, css_class
    return html.unescape(re.sub(r"<[^>]+>", "", found["body"]))


def test_the_contact_and_reference_lines_read_like_the_in_app_stop_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """시작 임시 화면(Streamlit 을 부르지 않는다)과 앱 안 멈춤 판(`components/stop_panel.py`)은 문의
    줄 · 참고 줄을 따로 짓는다 — 태그를 걷은 글자가 같은 꼴이다(「문의 <메일> · <창구 글>」 ·
    「참고 <갈래 키> · <YYYY-MM-DD HH:MM> UTC」).

    창구 글(`CAPA_ACCESS_CONTACT`)을 싣는 정책은 일부러 다르다. 시작 임시 화면은 앱 밖 화면의
    공통 틀(보드 카드 frame — 문의 줄은 메일 + 창구 글)이라 늘 싣고, 앱 안 판은 로그인 · 접속
    멈춤만 넘기며 앱 시작 실패 판은 메일만이다 — 접속 요청 창구는 데이터를 열지 못한 실패의
    연락처가 아니다(P1 session 리뷰 고침 · 보드 d7 (가) 「기존 두 칸을 다시 씀」, 앱 시작 실패 판
    쪽은 `tests/test_boot_stop.py` 가 본다)."""
    from capa_simulation.components import stop_panel

    monkeypatch.setenv("CAPA_APP_CONTACT_EMAIL", "demo@example.com")
    contact = container_stage.contact_of(
        {"CAPA_APP_CONTACT_EMAIL": "demo@example.com", "CAPA_ACCESS_CONTACT": "데모 창구"}
    )
    view = container_stage.stage_view(
        _state(attempt=2, kind="timeout", failed_at=1100.0, next_at=1112.0)
    )
    assert view.reference and view.reference_at is not None

    page = container_stage.render_main(view, now=1100.0, version=0, contact=contact)

    assert _line_text(page, "contact") == stop_panel.contact_caption("데모 창구")
    assert _line_text(page, "ref") == stop_panel.reference_line(
        view.reference, now=view.reference_at
    )
    assert _line_text(page, "contact").startswith(f"{stop_panel.CONTACT_PREFIX} ")
    assert _line_text(page, "ref").startswith(f"{stop_panel.REFERENCE_PREFIX} ")
    # 메일만 있으면 두 곳 다 메일만이다 — 앱 시작 실패 판이 넘기는 꼴(창구 글 없음).
    mail_only = container_stage.render_main(
        view, now=1100.0, version=0, contact=container_stage.StageContact(email="demo@example.com")
    )
    assert _line_text(mail_only, "contact") == stop_panel.contact_caption()
    assert stop_panel.contact_caption() == "문의 demo@example.com"


@pytest.mark.parametrize(
    ("email", "text", "expected"),
    [
        ("demo@example.com", "데모 창구", "문의 demo@example.com · 데모 창구"),
        ("demo@example.com", "", "문의 demo@example.com"),
        ("", "데모 창구", "문의 데모 창구"),
    ],
    ids=["mail-and-counter", "mail-only", "counter-only"],
)
def test_the_three_contact_lines_carry_the_same_letters(
    monkeypatch: pytest.MonkeyPatch, email: str, text: str, expected: str
) -> None:
    """문의 줄을 짓는 세 함수는 태그를 걷은 글자가 같다 — 「문의 <메일> · <창구 글>」(설계 규칙
    UI-CON-04). 앱 밖 공통 틀(`auth/page_frame.contact_line` — 거절 · 포털 거절 · 로그인 실패 셋 ·
    되풀이 · 로그아웃 · 설정 막힘 · 등록 · 저장 실패), 시작 임시 화면(Streamlit 을 부르지 않는다),
    앱 안 멈춤 판(`components/stop_panel.contact_caption`)이다.

    메일만인 꼴은 앱 시작 실패 판의 꼴이기도 하다 — 그 판은 `CAPA_ACCESS_CONTACT` 가 있어도 창구
    글을 넘기지 않는다(접속 요청 창구는 데이터를 열지 못한 실패의 연락처가 아니다 — 판 쪽은
    `tests/test_boot_stop.py`)."""
    from capa_simulation.auth import page_frame
    from capa_simulation.components import stop_panel

    monkeypatch.setenv("CAPA_APP_CONTACT_EMAIL", email)
    view = container_stage.stage_view(_state())
    contact = container_stage.StageContact(email=email, text=text)
    stage_page = container_stage.render_main(view, now=1000.0, version=0, contact=contact)

    assert _line_text(page_frame.contact_line(email, text), "muted") == expected
    assert _line_text(stage_page, "contact") == expected
    assert stop_panel.contact_caption(text) == expected


def test_no_contact_line_anywhere_when_both_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from capa_simulation.auth import page_frame
    from capa_simulation.components import stop_panel

    monkeypatch.delenv("CAPA_APP_CONTACT_EMAIL", raising=False)
    view = container_stage.stage_view(_state())
    stage_page = container_stage.render_main(
        view, now=1000.0, version=0, contact=container_stage.StageContact()
    )

    assert page_frame.contact_line("", "") == ""
    assert 'class="contact"' not in stage_page
    assert stop_panel.contact_caption() is None


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


def _body_rule(css: str) -> dict[str, str]:
    """맨 앞 `body { … }` 규칙의 선언(이름 → 값)."""
    found = re.search(r"(?m)^body \{([^}]*)\}", css)
    assert found is not None
    return dict(re.findall(r"([a-z-]+):\s*([^;]+);", found.group(1)))


def test_the_page_breaks_only_between_words_like_the_login_frame() -> None:
    """좁은 창(390)에서 「시작하지 못했습니 / 다」 처럼 한국어 낱말을 가운데서 가르지 않는다 — 띄어
    쓰기에서만 줄을 바꾸고 띄어쓰기 없는 긴 메일 · 주소만 아무 데서나 접는다. 앱 밖 화면 묶음
    (로그인 화면 틀 · 열어 둔 탭의 띠 — `tests/test_sso_reconnect.py`)과 같은 두 선언이고, 본문
    규칙에 두어 제목 · 까닭 · 노트 · 잃은 신청 줄 · 펼친 진단이 모두 물려받는다(UI-ACC-02)."""
    from capa_simulation.auth import page_frame

    frame_page = page_frame.render(
        page_frame.Frame(title="t", chip=None, lead=(), primary=page_frame.Link("a", "/")), now=0
    )
    stage_body = _body_rule(container_stage.page_css())
    frame_body = _body_rule(frame_page.split("<style>", 1)[1].split("</style>", 1)[0])

    for name, value in (("word-break", "keep-all"), ("overflow-wrap", "anywhere")):
        assert stage_body.get(name) == value, name
        assert frame_body.get(name) == value, name


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


@pytest.mark.parametrize("kind", sorted(FAILURE_LABELS))
def test_the_folded_diagnostics_carry_no_server_path(kind: str) -> None:
    """공개 화면의 접힌 진단은 이름 · 수만 — 서버 경로(`/…`)는 이름도 수도 아니다(보드 D9)."""
    view = container_stage.stage_view(_state(attempt=1, kind=kind))

    for line in view.diagnostics:
        assert re.search(r"(?:^|[\s(])/[A-Za-z]", line) is None, line


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
