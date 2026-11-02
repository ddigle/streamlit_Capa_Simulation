# Purpose: 다시 붙지 못한 탭의 「다시 로그인」 띠 스크립트를 판정 구획(node)과 글자로 고정한다.

"""「다시 로그인」 띠(`components/sso_reconnect.py`).

만료 · 로그아웃한 탭은 문지기가 websocket 을 닫은 뒤 다시 붙지 못하고, Streamlit 프런트는 영어
「Connection failed with status 401.」 과 CONNECTING 만 보인다(검토 실측). 띠 스크립트가 연결 상태
표지를 보고 host-config 가 401 이면 한국어 안내와 링크를 세운다. DOM 을 모르는 판정 구획 (`//
<sso-reconnect-rule>`)은 node(없으면 bun)로 떼어 돌리고, 나머지는 글자로 붙잡는다. 브라우저 동작은
사본 앱으로 본다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any

import pytest
from sso_support import LOGINID, PUBLIC_URL, use_config

from capa_simulation.auth import names
from capa_simulation.auth.identity import Identity
from capa_simulation.components.sso_identity import LOGIN_AGAIN_LABEL
from capa_simulation.components.sso_reconnect import (
    BANNER_ID,
    HOST_CONFIG_PATH,
    PROBE_GAP_MS,
    PROBE_WAIT_MS,
    RECONNECT_NOTICE,
    reconnect_script,
    sso_reconnect_scripts,
)


def _identity() -> Identity:
    now = int(time.time())
    return Identity(
        loginid=LOGINID, name=None, dept=None, iat=now, exp=now + 3600, jti="jti-0000-0000"
    )


def _node(script: str, runner: str) -> Any:
    match = re.search(
        r"// <sso-reconnect-rule>\n(?P<body>.*?)\n// </sso-reconnect-rule>", script, re.S
    )
    assert match, "띠 스크립트에 // <sso-reconnect-rule> 구획이 없습니다"
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 다시 로그인 띠 JS 구획 시험을 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", match.group("body") + "\n" + runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_off_mode_adds_nothing_to_the_toolbar_iframe() -> None:
    use_config(drop=[names.ENV_CLIENT_ID])

    assert sso_reconnect_scripts(None) == ()


def test_on_mode_adds_one_fixed_script() -> None:
    cfg = use_config()

    scripts = sso_reconnect_scripts(_identity())

    assert scripts == (reconnect_script(cfg),)
    # 회차마다 같아야 한다 — 내용이 바뀌면 Streamlit 이 툴바 iframe 을 새로 만든다.
    assert sso_reconnect_scripts(_identity()) == scripts


def test_script_watches_the_connection_marker_and_asks_host_config() -> None:
    script = reconnect_script(use_config())

    assert '[data-testid="stApp"]' in script
    assert '"data-test-connection-state"' in script
    assert json.dumps(HOST_CONFIG_PATH) in script
    assert "response.status === 401" in script
    assert 'credentials: "same-origin"' in script
    assert json.dumps(BANNER_ID) in script
    assert json.dumps(RECONNECT_NOTICE, ensure_ascii=False) in script
    assert json.dumps(LOGIN_AGAIN_LABEL, ensure_ascii=False) in script
    assert json.dumps(PUBLIC_URL) in script
    assert json.dumps(names.LOGIN_PATH) in script
    # 띠는 사람이 누른다 — 스크립트가 스스로 IdP · 로그인 경로로 옮기지 않는다.
    assert "location.assign" not in script and "location.replace" not in script
    assert "location.href =" not in script and "top.location" not in script
    # 띠는 Streamlit 의 연결 오류 창(모달 배경)보다 위에 선다.
    assert "z-index:2147483647" in script
    # 그 창(react-aria 모달)은 바깥을 inert 로 만든다 — 띠는 react-aria 의 제외 표지를 단다.
    assert 'box.setAttribute("data-react-aria-top-layer", "")' in script
    assert 'link.target = "_self"' in script


def test_script_text_cannot_break_out_of_its_script_tag() -> None:
    cfg = use_config({names.ENV_PUBLIC_URL: "https://capa.example.invalid/x</script>y"})

    assert "</script>" not in reconnect_script(cfg)


def test_connection_states_that_count_as_disconnected() -> None:
    script = reconnect_script(use_config())
    states = [
        "CONNECTED",
        "STATIC_CONNECTED",
        "INITIAL",
        "",
        None,
        "PINGING_SERVER",
        "CONNECTING",
        "DISCONNECTED_FOREVER",
    ]
    runner = f"""
const states = {json.dumps(states)};
process.stdout.write(JSON.stringify(states.map(disconnected)));
"""
    assert _node(script, runner) == [False, False, False, False, False, True, True, True]


def test_probe_waits_then_repeats_at_the_gap() -> None:
    script = reconnect_script(use_config())
    runner = f"""
const W = {PROBE_WAIT_MS}, G = {PROBE_GAP_MS};
process.stdout.write(JSON.stringify([
  probeDue(null, null, 100000, W, G),
  probeDue(100000, null, 100000 + W - 1, W, G),
  probeDue(100000, null, 100000 + W, W, G),
  probeDue(100000, 100000 + W, 100000 + W + G - 1, W, G),
  probeDue(100000, 100000 + W, 100000 + W + G, W, G),
]));
"""
    assert _node(script, runner) == [False, False, True, False, True]


def test_login_link_keeps_the_page_and_query_and_strips_the_public_prefix() -> None:
    script = reconnect_script(use_config())
    base = "https://capa.example.invalid"
    runner = f"""
const L = {json.dumps(names.LOGIN_PATH)};
process.stdout.write(JSON.stringify([
  loginHref({json.dumps(base)}, "", L, "/space_layout", "?floor=2&theme=dark"),
  loginHref({json.dumps(base)}, "", L, "/", ""),
  loginHref({json.dumps(base + "/proxy/8581")}, "/proxy/8581", L, "/proxy/8581/home", "?a=1"),
  loginHref({json.dumps(base + "/proxy/8581")}, "/proxy/8581", L, "/proxy/8581", ""),
  loginHref({json.dumps(base)}, "", L, "", ""),
]));
"""
    assert _node(script, runner) == [
        f"{base}{names.LOGIN_PATH}?next=%2Fspace_layout%3Ffloor%3D2%26theme%3Ddark",
        f"{base}{names.LOGIN_PATH}?next=%2F",
        f"{base}/proxy/8581{names.LOGIN_PATH}?next=%2Fhome%3Fa%3D1",
        f"{base}/proxy/8581{names.LOGIN_PATH}?next=%2F",
        f"{base}{names.LOGIN_PATH}?next=%2F",
    ]
