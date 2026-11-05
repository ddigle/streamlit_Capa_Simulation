# Purpose: 앱 화면 입력으로 로그인을 늘리는 갱신 스크립트를 판정 구획(node)과 글자로 고정한다.

"""로그인 갱신 스크립트(`components/sso_refresh.py`).

사람이 앱을 쓰는 동안(입력) 5분에 한 번 `POST /auth/sso/refresh` 를 보내 세션 쿠키와 열린 연결의
갱신 표를 늘린다. DOM 을 모르는 판정 구획(`// <sso-refresh-rule>`)은 node(없으면 bun)로 떼어
돌리고, 나머지(듣는 사건 · 요청 꼴 · 타이머 없음 · 로그아웃 링크 제외)는 글자로 붙잡는다. 실제
브라우저 동작(204 · 쿠키 jti · exp 가 바뀌고 sid 는 같음)은 사본 앱으로 본다.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from js_runner import run_js_json
from sso_support import LOGINID, use_config

from capa_simulation.auth import names
from capa_simulation.auth.identity import Identity
from capa_simulation.components.sso_refresh import (
    HANDLER_NAME,
    LOGOUT_SELECTOR,
    REFRESH_GAP_MS,
    RETRY_GAP_MS,
    STALE_SEND_MS,
    STATE_NAME,
    USE_EVENTS,
    refresh_script,
    sso_refresh_scripts,
)


def _identity(loginid: str = LOGINID, sid: str = "sid-0000-0000-0000-00") -> Identity:
    now = int(time.time())
    return Identity(
        loginid=loginid,
        name=None,
        dept=None,
        iat=now,
        exp=now + 3600,
        jti=f"jti-{loginid}",
        sid=sid,
        auth_time=now,
    )


def _node(script: str, runner: str) -> Any:
    match = re.search(r"// <sso-refresh-rule>\n(?P<body>.*?)\n// </sso-refresh-rule>", script, re.S)
    assert match, "갱신 스크립트에 // <sso-refresh-rule> 구획이 없습니다"
    return run_js_json(match.group("body") + "\n" + runner, what="로그인 갱신 JS 구획 시험")


def test_off_mode_adds_no_refresh_script() -> None:
    use_config(drop=[names.ENV_CLIENT_ID])

    assert sso_refresh_scripts(None) == ()


def test_on_mode_adds_one_fixed_script() -> None:
    """회차 · 사람마다 같아야 한다 — 내용이 바뀌면 Streamlit 이 툴바 iframe 을 새로 만든다."""
    cfg = use_config()

    first = sso_refresh_scripts(_identity())
    other = sso_refresh_scripts(_identity("other.user", "sid-1111-1111-1111-11"))

    assert first == other == (refresh_script(cfg),)
    assert LOGINID not in first[0] and "other.user" not in first[0]


def test_script_listens_to_human_input_in_the_capture_phase() -> None:
    script = refresh_script(use_config())

    assert USE_EVENTS == ("pointerdown", "keydown", "wheel", "touchstart")
    assert json.dumps(list(USE_EVENTS)) in script
    assert "doc.addEventListener(events[index], onUse, { capture: true, passive: true })" in script
    assert "doc.removeEventListener(events[index], previous, true)" in script
    assert "countsAsUse(event.isTrusted, onLogout)" in script
    # 듣개 · 차례 상태는 부모 창에 남겨 iframe 이 다시 만들어져도 옛 듣개를 떼고 차례를 잇는다.
    assert f"parentWindow[{json.dumps(HANDLER_NAME)}] = onUse" in script
    assert f"parentWindow[{json.dumps(STATE_NAME)}] = state" in script
    # 보기만 · 지나가기만 하는 사건은 「사용」 이 아니다.
    for passive_event in ("pointermove", "mousemove", "focus", "visibilitychange", "scroll"):
        assert f'"{passive_event}"' not in script


def test_script_has_no_timer() -> None:
    """쓰지 않으면 끝나야 한다(사용자 결정) — 저절로 갱신하는 타이머가 없다."""
    script = refresh_script(use_config())

    for timer in ("setInterval", "setTimeout", "requestAnimationFrame", "requestIdleCallback"):
        assert timer not in script, timer


def test_script_posts_to_the_refresh_path_with_the_header() -> None:
    cfg = use_config({names.ENV_PUBLIC_URL: "https://capa.example.invalid/proxy/8510"})
    script = refresh_script(cfg)

    assert 'method: "POST"' in script
    assert 'credentials: "same-origin"' in script
    assert 'redirect: "error"' in script
    assert 'cache: "no-store"' in script
    assert "body:" not in script, "본문을 싣지 않는다(서버가 400 으로 거절)"
    header = names.REFRESH_HEADER
    assert f"headers[{json.dumps(header)}] = {json.dumps(names.REFRESH_HEADER_VALUE)};" in script
    assert (
        f"parentWindow.location.origin + {json.dumps('/proxy/8510')} + "
        f"{json.dumps(names.REFRESH_PATH)}"
    ) in script
    # 요청 · 시계는 부모 창의 것 — iframe 이 다시 만들어져도 요청이 이어지고 가짜 시계가 앱과 같다.
    assert "parentWindow.fetch(url" in script and "parentWindow.Date.now()" in script
    # 공개 주소 원문(호스트)은 싣지 않는다 — 지금 창의 출처로 보낸다.
    assert "capa.example.invalid" not in script
    # 앞단이 밑줄 머리를 버린다 — 머리 이름에 밑줄이 없다.
    assert "_" not in names.REFRESH_HEADER


def test_script_without_a_path_prefix_posts_to_the_root() -> None:
    script = refresh_script(use_config())

    assert f'parentWindow.location.origin + "" + {json.dumps(names.REFRESH_PATH)}' in script


def test_script_skips_the_logout_link() -> None:
    script = refresh_script(use_config())

    assert names.LOGOUT_PATH in LOGOUT_SELECTOR
    assert f"target.closest({json.dumps(LOGOUT_SELECTOR)})" in script


def test_script_text_cannot_break_out_of_its_script_tag() -> None:
    cfg = use_config({names.ENV_PUBLIC_URL: "https://capa.example.invalid/x</script>y"})

    assert "</script" not in refresh_script(cfg).lower()


def test_counts_as_use() -> None:
    script = refresh_script(use_config())
    runner = """
process.stdout.write(JSON.stringify([
  countsAsUse(true, false),
  countsAsUse(false, false),
  countsAsUse(true, true),
  countsAsUse(undefined, false),
  countsAsUse("true", false),
]));
"""
    assert _node(script, runner) == [True, False, False, False, False]


def test_refresh_due() -> None:
    script = refresh_script(use_config())
    runner = f"""
const G = {REFRESH_GAP_MS}, S = {STALE_SEND_MS}, T = 1000000;
process.stdout.write(JSON.stringify([
  refreshDue(null, null, T, G, S),
  refreshDue(null, T - 10000, T, G, S),
  refreshDue(null, T - S - 1000, T, G, S),
  refreshDue(T + 1000, null, T, G, S),
  refreshDue(T, null, T, G, S),
  refreshDue(T - 1, null, T, G, S),
  refreshDue(T + G + 1, null, T, G, S),
  refreshDue(T + G, null, T, G, S),
  refreshDue(null, T + 5000, T, G, S),
]));
"""
    assert _node(script, runner) == [
        True,  # 처음
        False,  # 보낸 지 10초 — 답을 기다림
        True,  # 보낸 지 31초 — 낡은 「보내는 중」
        False,  # 다음 차례 전
        True,  # 다음 차례가 됨
        True,  # 다음 차례가 지남
        True,  # 시계가 gap 넘게 뒤로 감 — 기다리지 않음
        False,  # gap 만큼 앞(정상 범위) — 기다림
        True,  # 보낸 시각이 미래(시계가 뒤로 감) — 막지 않음
    ]


def test_next_refresh_at() -> None:
    script = refresh_script(use_config())
    statuses = [204, 200, 400, 401, 403, 405, 0, 500, 503]
    runner = f"""
const statuses = {json.dumps(statuses)};
const G = {REFRESH_GAP_MS}, R = {RETRY_GAP_MS};
process.stdout.write(JSON.stringify(
  statuses.map(function (status) {{ return nextRefreshAt(status, 0, G, R); }})
));
"""
    gap, retry = REFRESH_GAP_MS, RETRY_GAP_MS
    assert _node(script, runner) == [gap, gap, gap, gap, gap, gap, retry, retry, retry]
