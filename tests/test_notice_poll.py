# Purpose: 운영 서버의 공지 물음 경로(문지기·모드·응답 머리)와 틱 스크립트의 물음 갈래를 시험한다.

"""공지 물음 — 경로 `GET /capa/notice`(`auth/notice_poll.py`)와 툴바 iframe 틱 스크립트의 물음
갈래(`components/sso_reconnect.py` 의 `_NOTICE_POLL`). 2026-11-17 공지 보드 답 q-speed(운영 서버는
10초마다 묻기). 값은 모두 합성이고 공지 저장은 시험마다 비운다(`conftest`).

- 경로는 공개 목록 밖이라 켜짐이면 문지기가 쿠키를 본다(없으면 401 — 탐색으로 보지 않음), 막힘은
  문지기의 503, 꺼짐은 앱이 열린 모드라 처리기가 그대로 낸다. 응답은 `notice_board.payload()`
  그대로 · `no-store`.
- 스크립트는 문지기가 있는 서버에만 그 갈래를 싣고(`app.py` 실행에는 없음), 붙어 있는 동안 10초마다
  묻고, 판이 바뀐 꼴만 알림 칸 입구에 넘기며, 첫 401 에서 멈춘다. 판정 구획은 node 로 떼어 돌리고,
  틱 · 물음 · 넘김은 스크립트 전체를 가짜 창에서 돌린다.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from asgi_driver import App, AsgiResponse, http
from child_env import narrow_child_env
from js_runner import run_js_json
from sso_support import LOGINID, PUBLIC_URL, use_config
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from capa_simulation import notice_board
from capa_simulation.auth import gate, names, runtime
from capa_simulation.auth.config import SsoConfig
from capa_simulation.auth.gate import SsoGate
from capa_simulation.auth.notice_poll import UNAVAILABLE
from capa_simulation.auth.server import sso_routes
from capa_simulation.auth.tokens import SESSION_LEEWAY, issue_session
from capa_simulation.components.sso_reconnect import (
    NOTICE_PATH,
    NOTICE_POLL_MS,
    reconnect_script,
    restart_script,
    sso_reconnect_scripts,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORS = {"sec-fetch-mode": "cors", "sec-fetch-dest": "empty", "sec-fetch-site": "same-origin"}
NAVIGATE = {"sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "sec-fetch-site": "none"}


async def _inner(request: Request) -> Response:
    return PlainTextResponse(f"inner {request.url.path}")


def _gated() -> App:
    """문지기 + 우리 경로 + 앱 자리(모든 GET 경로 — Streamlit 정적 마운트 자리)."""
    inner = Starlette(routes=[*sso_routes(), Route("/{rest:path}", _inner, methods=["GET"])])
    return SsoGate(inner)


def _bare() -> App:
    """문지기 없이 경로만 — 처리기가 스스로 보는 모드 판정."""
    return Starlette(routes=sso_routes())


def _cookie(cfg: SsoConfig, *, now: int | None = None) -> dict[str, str]:
    token, _ = issue_session(
        cfg, loginid=LOGINID, name=None, dept=None, now=now or int(time.time())
    )
    return {"cookie": f"{cfg.session_cookie}={token}"}


def _send_notice() -> notice_board.Notice:
    return notice_board.send("오늘 18:20 합성 점검", notice_board.now_kst() + timedelta(hours=1))


def _expected_body() -> Any:
    """지금 공지 꼴을 JSON 으로 한 번 오간 값(응답 본문과 견준다)."""
    return json.loads(json.dumps(notice_board.payload()))


def _assert_payload_response(response: AsgiResponse) -> Any:
    assert response.status == 200, response.text
    assert response.header("cache-control") == "no-store"
    assert response.header("x-content-type-options") == "nosniff"
    assert (response.header("content-type") or "").startswith("application/json")
    body = json.loads(response.text)
    assert body == _expected_body()
    return body


# --- 경로 · 문지기 ---------------------------------------------------------------------------


def test_the_notice_path_is_outside_the_public_list() -> None:
    """공개 목록에 넣으면 문지기가 쿠키를 보지 않고 넘긴다 — 정확 일치 목록 밖이어야 한다."""
    assert names.NOTICE_PATH == NOTICE_PATH == "/capa/notice"
    assert names.NOTICE_PATH not in names.SSO_PATHS
    for method in ("GET", "HEAD"):
        assert not gate._is_public(names.NOTICE_PATH, method)
    routes = [
        (route.path, sorted(route.methods or []))
        for route in sso_routes()
        if isinstance(route, Route)
    ]
    assert (names.NOTICE_PATH, ["GET", "HEAD"]) in routes


def test_without_a_session_cookie_the_gate_refuses_before_the_handler() -> None:
    """켜짐: 쿠키 없는 물음은 401 + 까닭 머리(본문에 공지 없음). 이 경로는 탐색으로 보지 않는다 —
    주소창 탐색 꼴이어도, 앞단이 Sec-Fetch-* 를 뗀 fetch(문지기가 비브라우저 탐색으로 보던 꼴)여도
    401 이고 로그인 시작(IdP 302 · 상태 · 시도 쿠키 · 되풀이 경고)을 내지 않는다. 만료된 채 놀고
    있는 탭이 10초마다 물어도 로그인이 늘지 않는다."""
    use_config()
    _send_notice()

    refused = http(_gated(), "GET", names.NOTICE_PATH, headers=CORS)

    assert refused.status == 401
    assert refused.header(names.REASON_HEADER) == names.REASON_OTHER
    assert "합성 점검" not in refused.text and "mark" not in refused.text
    for headers in (NAVIGATE, {}, {}, {}, {}, {}):
        bare = http(_gated(), "GET", names.NOTICE_PATH, headers=headers)
        assert bare.status == 401, (headers, bare.status)
        assert bare.header(names.REASON_HEADER) == names.REASON_OTHER
        assert bare.set_cookies == [] and bare.header("location") is None
        assert "합성 점검" not in bare.text
    assert not [event for event in runtime.recent_events() if event.event == "login_fail"]
    other = http(_gated(), "GET", "/space", headers={})
    assert other.status == 302, "다른 경로의 비브라우저 탐색은 그대로 로그인으로 간다"


def test_a_signed_in_tab_gets_the_payload_as_uncached_json() -> None:
    """켜짐 + 유효한 쿠키: 200, 본문은 `notice_board.payload()` 그대로(프로세스 표지 포함) ·
    no-store."""
    cfg = use_config()

    empty = _assert_payload_response(
        http(_gated(), "GET", names.NOTICE_PATH, headers={**CORS, **_cookie(cfg)})
    )
    assert empty["notice"] is None and empty["note"]["active"] is False
    assert empty["mark"] == notice_board.PROCESS_MARK

    sent = _send_notice()
    standing = _assert_payload_response(
        http(_gated(), "GET", names.NOTICE_PATH, headers={**CORS, **_cookie(cfg)})
    )
    assert standing["notice"]["id"] == sent.id and standing["note"]["active"] is True
    assert standing["rev"] == empty["rev"] + 1

    assert notice_board.withdraw(sent.id)
    gone = _assert_payload_response(
        http(_gated(), "GET", names.NOTICE_PATH, headers={**CORS, **_cookie(cfg)})
    )
    assert gone["notice"] is None and gone["rev"] == standing["rev"] + 1


def test_an_expired_or_revoked_cookie_is_refused_like_a_missing_one() -> None:
    cfg = use_config()
    _send_notice()
    old = int(time.time()) - cfg.session_seconds - 120
    token, issued = issue_session(cfg, loginid=LOGINID, name=None, dept=None, now=int(time.time()))
    runtime.revoke_session(
        issued.sid, until=issued.auth_time + cfg.session_max_seconds + SESSION_LEEWAY
    )

    for cookie in (_cookie(cfg, now=old), {"cookie": f"{cfg.session_cookie}={token}"}):
        refused = http(_gated(), "GET", names.NOTICE_PATH, headers={**CORS, **cookie})
        assert refused.status == 401 and "합성 점검" not in refused.text


def test_a_broken_setup_answers_503_at_the_gate() -> None:
    use_config(drop=[names.ENV_ISSUER])
    _send_notice()

    refused = http(_gated(), "GET", names.NOTICE_PATH, headers=CORS)

    assert refused.status == 503 and "합성 점검" not in refused.text


def test_off_mode_hands_the_payload_to_anyone_like_the_open_app() -> None:
    """꺼짐: 문지기가 모두 넘기고 앱 자체가 열려 있다 — 처리기가 공지를 그대로 낸다(꺼짐 서버를
    `capa_server.py` 로 띄운 개발 PC · WebIDE 도 10초 물음을 쓴다)."""
    runtime.reset()
    _send_notice()

    _assert_payload_response(http(_gated(), "GET", names.NOTICE_PATH, headers=CORS))


def test_the_handler_judges_the_mode_itself() -> None:
    """문지기 없이 경로만 붙었을 때: 꺼짐은 낸다, 켜짐인데 문지기가 없으면 503(쿠키를 보지 않은
    요청에 공지를 내지 않는다), 막힘도 503."""
    runtime.reset()
    _send_notice()
    _assert_payload_response(http(_bare(), "GET", names.NOTICE_PATH))

    use_config()
    assert not runtime.gate_installed()
    refused = http(_bare(), "GET", names.NOTICE_PATH)
    assert (refused.status, refused.text) == (503, UNAVAILABLE)
    assert refused.header("cache-control") == "no-store"
    runtime.mark_gate_installed()
    _assert_payload_response(http(_bare(), "GET", names.NOTICE_PATH))

    use_config(drop=[names.ENV_ISSUER])
    runtime.mark_gate_installed()
    assert http(_bare(), "GET", names.NOTICE_PATH).status == 503


def test_importing_the_route_does_not_bring_streamlit() -> None:
    """문지기 · 기동 쪽이 경로 창구를 들여도 Streamlit 이 딸려 오지 않는다 — 등록부는 처리기가
    공지 꼴을 지을 때만."""
    code = (
        "import sys\n"
        "import capa_simulation.auth.server\n"
        "import capa_simulation.auth.notice_poll\n"
        "print(sorted({'streamlit', 'jwt', 'duckdb'} & set(sys.modules)))\n"
    )
    found = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env=narrow_child_env({"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": ""}),
    )

    assert found.stdout.strip() == "[]"


# --- 스크립트에 싣는 갈래 --------------------------------------------------------------------


def test_the_poll_rides_only_on_a_server_with_the_gate() -> None:
    """`app.py` 로 띄운 서버(문지기 없음)의 툴바 스크립트에는 물음이 없다. `capa_server.py`
    (문지기 있음)면 켜짐 · 꺼짐 모두 경로 · 간격이 실리고, 회차마다 글이 같다."""
    cfg = use_config()
    assert not runtime.gate_installed()
    for script in (reconnect_script(cfg), restart_script(), *sso_reconnect_scripts(None)):
        assert json.dumps(NOTICE_PATH) not in script
        assert "noticeTick = function" not in script

    runtime.mark_gate_installed()
    for script in (reconnect_script(cfg), restart_script()):
        assert f"ask({json.dumps(NOTICE_PATH)}, true)" in script
        assert f"now, {NOTICE_POLL_MS})" in script
        assert "noticeTick = function" in script
        assert "parentWindow.__capaAlerts" in script
        assert "__capaAlertQueue" not in script, "사건 알림 대기열은 raise 꼴이다"
        assert 'credentials: "same-origin"' in script and 'cache: "no-store"' in script
    assert reconnect_script(cfg) == reconnect_script(cfg)
    assert restart_script() == restart_script()
    assert NOTICE_POLL_MS == 10_000


# --- 판정 구획(node) -------------------------------------------------------------------------


def _rule(runner: str) -> Any:
    script = reconnect_script(use_config())
    match = re.search(
        r"// <sso-reconnect-rule>\n(?P<body>.*?)\n// </sso-reconnect-rule>", script, re.S
    )
    assert match, "틱 스크립트에 // <sso-reconnect-rule> 구획이 없습니다"
    return run_js_json(match.group("body") + "\n" + runner, what="공지 물음 JS 구획 시험")


def test_only_a_connected_tab_counts_for_the_poll() -> None:
    result = _rule(
        "process.stdout.write(JSON.stringify(["
        "'CONNECTED', 'STATIC_CONNECTED', 'INITIAL', 'CONNECTING', 'DISCONNECTED_FOREVER', '', null"
        "].map(noticeConnected)));"
    )

    assert result == [True, False, False, False, False, False, False]


def test_the_poll_waits_a_gap_and_never_overlaps_or_runs_after_a_stop() -> None:
    result = _rule(
        "process.stdout.write(JSON.stringify(["
        "noticeDue(null, false, false, 50000, 10000),"
        "noticeDue(1000, false, false, 10999, 10000),"
        "noticeDue(1000, false, false, 11000, 10000),"
        "noticeDue(1000, true, false, 99000, 10000),"
        "noticeDue(1000, false, true, 99000, 10000)"
        "]));"
    )

    assert result == [False, False, True, False, False]


def test_an_answer_status_picks_stop_read_or_next() -> None:
    result = _rule(
        "process.stdout.write(JSON.stringify("
        "[401, 200, 299, 204, 403, 404, 500, 503, 302, null].map(noticeStep)));"
    )

    assert result == [
        "stop",
        "read",
        "read",
        "read",
        "next",
        "next",
        "next",
        "next",
        "next",
        "next",
    ]


def test_only_a_marked_json_payload_is_read() -> None:
    texts = [
        json.dumps({"mark": "ab12cd34", "rev": 3, "notice": None, "note": {}}),
        json.dumps({"mark": "ab12cd34", "rev": "3"}),
        json.dumps({"rev": 3}),
        json.dumps([1, 2]),
        "null",
        "<!doctype html><html></html>",
        "",
    ]
    result = _rule(
        f"const texts = {json.dumps(texts)};"
        "process.stdout.write(JSON.stringify(texts.map((text) => {"
        "  const read = noticeRead(text); return read && read.key; })));"
    )

    assert result == ["ab12cd34:3", None, None, None, None, None, None]


# --- 스크립트 통째(가짜 창) ------------------------------------------------------------------

# 틱 스크립트 전체를 가짜 부모 창에서 돌린다. `PLAN` 의 걸음마다 연결 표지를 바꾸고(`state` — null
# 이면 표지 없음) · 알림 칸 입구를 세우고(`center`) · 시계를 밀고(`advance`) · 틱을 한 번
# 돈다(`tick`). 공지 경로의 답은 `ANSWERS` 차례로(마지막 것은 되풀이 — `null` 은 닿지 못함,
# `hang` 은 답이 오지 않음), 그 밖의 물음(끊긴 탭의 host-config 등)은 200 이다. 걸음마다 공지 물음
# 수를 적는다.
_POLL_RUNNER = """
const SCRIPT = %(script)s;
const ANSWERS = %(answers)s;
const PLAN = %(plan)s;
const LOCATION = %(location)s;
const NOTICE_PATH = %(notice_path)s;
let now = 1000000;
Date.now = () => now;
const attrs = { "data-test-connection-state": "CONNECTED" };
const root = {
  getAttribute: (name) => (name in attrs && attrs[name] !== null ? attrs[name] : null),
};
function element() {
  return {
    style: { setProperty() {}, removeProperty() {} }, children: [],
    setAttribute() {}, getAttribute() { return null; }, hasAttribute() { return false; },
    removeAttribute() {}, appendChild(child) { return child; }, remove() {},
  };
}
const doc = {
  body: { appendChild(child) { return child; } },
  createElement: element,
  getElementById: () => null,
  querySelector: (selector) => (selector.includes("stApp") ? root : null),
  querySelectorAll: () => [],
};
const parentWindow = { document: doc, location: LOCATION };
const asked = [];
const delivered = [];
globalThis.fetch = (url, options) => {
  const text = String(url);
  if (!text.endsWith(NOTICE_PATH)) return Promise.resolve(new Response("", { status: 200 }));
  asked.push({ url: text, credentials: options.credentials, cache: options.cache });
  const answer = ANSWERS.length > 1 ? ANSWERS.shift() : ANSWERS[0];
  if (answer === null) return Promise.reject(new Error("down"));
  if (answer.hang) return new Promise(() => {});
  return Promise.resolve(new Response(answer.body, { status: answer.status }));
};
let tick = null;
globalThis.window = {
  parent: parentWindow,
  setInterval(fn) { tick = fn; return 1; },
  setTimeout() { return 2; },
  clearTimeout() {},
};
new Function(SCRIPT)();
(async () => {
  const settle = async () => {
    for (let i = 0; i < 20; i++) await new Promise((done) => setImmediate(done));
  };
  const counts = [];
  for (const step of PLAN) {
    if ("state" in step) attrs["data-test-connection-state"] = step.state;
    if (step.center) {
      parentWindow.__capaAlerts = {
        notice: (payload) => delivered.push(payload.mark + ":" + payload.rev),
      };
    }
    if (step.advance) now += step.advance;
    if (step.tick) {
      tick();
      await settle();
    }
    counts.push(asked.length);
  }
  process.stdout.write(JSON.stringify({ asked, delivered, counts }));
})();
"""

_HERE = {
    "origin": PUBLIC_URL,
    "href": PUBLIC_URL + "/Space?tab=1",
    "pathname": "/Space",
    "search": "?tab=1",
}
GAP = NOTICE_POLL_MS


def _run_poll(
    script: str,
    answers: Sequence[object],
    plan: Sequence[object],
    *,
    location: dict[str, str] | None = None,
) -> Any:
    runner = _POLL_RUNNER % {
        "script": json.dumps(script),
        "answers": json.dumps(answers),
        "plan": json.dumps(plan),
        "location": json.dumps(location or _HERE),
        "notice_path": json.dumps(NOTICE_PATH),
    }
    return run_js_json(runner, what="공지 물음 스크립트 통째 시험")


def _gate_script() -> str:
    cfg = use_config()
    runtime.mark_gate_installed()
    return reconnect_script(cfg)


def _ok(mark: str, rev: int) -> dict[str, Any]:
    return {"status": 200, "body": json.dumps({"mark": mark, "rev": rev, "notice": None})}


def test_a_connected_tab_asks_every_ten_seconds_and_hands_only_new_revisions() -> None:
    """붙은 지 10초 뒤 첫 물음, 그 뒤 10초마다. 판이 같으면 넘기지 않고, 5xx · HTML 은 버리고 다음
    차례에 다시 묻는다. 재시작(표지 바뀜)은 판이 낮아도 넘긴다(알림 칸이 표지로 가른다)."""
    script = _gate_script()
    _send_notice()
    real = {"status": 200, "body": json.dumps(notice_board.payload())}
    answers = [
        _ok("m1", 1),
        _ok("m1", 1),
        _ok("m1", 2),
        {"status": 500, "body": "boom"},
        {"status": 200, "body": "<!doctype html><title>app</title>"},
        _ok("m2", 0),
        real,
    ]
    plan = [
        {"center": True, "tick": True},
        {"advance": GAP - 1, "tick": True},
        {"advance": 1, "tick": True},
        *({"advance": GAP, "tick": True} for _ in range(6)),
    ]

    result = _run_poll(script, answers, plan)

    assert result["counts"] == [0, 0, 1, 2, 3, 4, 5, 6, 7]
    assert result["delivered"] == [
        "m1:1",
        "m1:2",
        "m2:0",
        f"{notice_board.PROCESS_MARK}:{notice_board.revision()}",
    ]
    for asked in result["asked"]:
        assert asked == {
            "url": PUBLIC_URL + NOTICE_PATH,
            "credentials": "same-origin",
            "cache": "no-store",
        }


def test_a_401_stops_the_poll_until_the_tab_reconnects() -> None:
    """첫 401 에서 멈춘다(만료 탭이 10초마다 문지기를 두드리지 않음). 끊겼다가 다시 붙으면 붙은
    지 10초 뒤 다시 묻는다."""
    script = _gate_script()
    plan = [
        {"center": True, "tick": True},
        {"advance": GAP, "tick": True},
        {"advance": GAP, "tick": True},
        {"advance": GAP * 5, "tick": True},
        {"state": "DISCONNECTED_FOREVER", "advance": GAP, "tick": True},
        {"advance": GAP * 3, "tick": True},
        {"state": "CONNECTED", "advance": 1000, "tick": True},
        {"advance": GAP, "tick": True},
    ]

    result = _run_poll(script, [{"status": 401, "body": "login required"}, _ok("m1", 4)], plan)

    assert result["counts"] == [0, 1, 1, 1, 1, 1, 1, 2]
    assert result["delivered"] == ["m1:4"]


def test_a_tab_that_is_not_connected_never_asks() -> None:
    """끊김 · 처음 · 표지 없음(판올림)은 묻지 않는다 — 끊긴 탭의 물음은 띠 갈래(host-config)
    뿐이다."""
    script = _gate_script()
    for state in ("DISCONNECTED_FOREVER", "CONNECTING", "INITIAL", None):
        plan = [
            {"state": state, "center": True, "tick": True},
            *({"advance": GAP, "tick": True} for _ in range(4)),
        ]

        result = _run_poll(script, [_ok("m1", 1)], plan)

        assert result["counts"] == [0, 0, 0, 0, 0], state
        assert result["delivered"] == [], state


def test_a_payload_waits_for_the_alert_center_to_stand() -> None:
    """알림 칸이 아직 서지 않았으면 받은 꼴을 쥐고 있다가 칸이 선 다음 틱에 한 번 넘긴다."""
    script = _gate_script()
    plan = [
        {"tick": True},
        {"advance": GAP, "tick": True},
        {"advance": 1000, "tick": True},
        {"center": True, "advance": 1000, "tick": True},
        {"advance": 1000, "tick": True},
        {"advance": GAP, "tick": True},
    ]

    result = _run_poll(script, [_ok("m1", 1)], plan)

    assert result["counts"] == [0, 1, 1, 1, 1, 2]
    assert result["delivered"] == ["m1:1"]


def test_a_held_payload_is_dropped_when_the_tab_disconnects() -> None:
    """칸이 서기 전에 쥔 꼴은 끊기면 버린다 — 서버가 다시 시작한 뒤 다시 붙은 탭에 옛 표지의 꼴을
    넘기면 알림 칸은 표지가 달라 받아 버린다(다시 붙은 회차의 data 가 정본)."""
    script = _gate_script()
    plan = [
        {"tick": True},
        {"advance": GAP, "tick": True},
        {"state": "DISCONNECTED_FOREVER", "advance": 1000, "tick": True},
        {"state": "CONNECTED", "center": True, "advance": 1000, "tick": True},
        {"advance": 1000, "tick": True},
    ]

    result = _run_poll(script, [_ok("old", 7)], plan)

    assert result["counts"] == [0, 1, 1, 1, 1]
    assert result["delivered"] == []


def test_an_unanswered_ask_is_not_stacked_and_failures_retry_next_turn() -> None:
    """답을 기다리는 동안은 다시 묻지 않는다. 닿지 못함은 다음 차례에 다시 묻는다."""
    script = _gate_script()
    plan = [{"center": True, "tick": True}, *({"advance": GAP, "tick": True} for _ in range(4))]

    hanging = _run_poll(script, [{"hang": True}], plan)
    failing = _run_poll(script, [None, None, _ok("m1", 1)], plan)

    assert hanging["counts"] == [0, 1, 1, 1, 1]
    assert failing["counts"] == [0, 1, 2, 3, 4]
    assert failing["delivered"] == ["m1:1"]


def test_an_off_mode_gate_server_asks_under_the_page_folder() -> None:
    """꺼짐 서버를 `capa_server.py` 로 띄웠으면(WebIDE `/proxy/<포트>/` 등) 물음은 지금 주소의
    폴더 아래로 간다 — 띠 물음과 같은 뿌리."""
    runtime.reset()
    runtime.mark_gate_installed()
    here = {
        "origin": "https://webide.example.invalid",
        "href": "https://webide.example.invalid/proxy/8080/Space?tab=1",
        "pathname": "/proxy/8080/Space",
        "search": "?tab=1",
    }

    result = _run_poll(
        restart_script(),
        [_ok("m1", 1)],
        [{"center": True, "tick": True}, {"advance": GAP, "tick": True}],
        location=here,
    )

    assert [asked["url"] for asked in result["asked"]] == [
        "https://webide.example.invalid/proxy/8080" + NOTICE_PATH
    ]
    assert result["delivered"] == ["m1:1"]
