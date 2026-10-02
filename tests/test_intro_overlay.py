# Purpose: 첫 접속 입장 화면의 등록 내용(틀·스타일·부분 글꼴)과 회차마다 같은 페이로드를 검증한다.

from __future__ import annotations

import base64
import json
import re
from typing import Any

import pytest

import capa_simulation.components.intro_overlay as intro_overlay
from capa_simulation.components.home_rendering import HOME_LOADING_STAGES
from capa_simulation.design import tokens

ASSETS = intro_overlay._ASSETS


def _prelude_constant(js: str, name: str) -> str:
    match = re.search(rf"^const {name} = (.+);$", js, flags=re.MULTILINE)
    assert match, f"등록 JS 앞에 {name} 상수가 없습니다."
    return str(json.loads(match.group(1)))


def test_bundled_font_is_a_woff2_shipped_with_its_license() -> None:
    """사내망에는 외부 글꼴이 없다. 부분 글꼴이 저장소에 있고 OFL 라이선스가 곁에 있어야 한다."""
    font = (ASSETS / "archivo-capa.woff2").read_bytes()
    license_text = (ASSETS / "OFL.txt").read_text(encoding="utf-8")

    assert font[:4] == b"wOF2"
    assert "SIL Open Font License, Version 1.1" in license_text
    # 예약 글꼴 이름(Reserved Font Name)이 있으면 부분 글꼴에 원래 이름을 쓸 수 없다.
    copyright_line = license_text.splitlines()[0]
    assert "Reserved Font Name" not in copyright_line


def test_registered_js_carries_the_assets_verbatim() -> None:
    """화면 틀·스타일·글꼴은 등록 JS 앞의 상수로 실린다 — 파일과 한 글자도 달라지면 안 된다."""
    js = intro_overlay._registered_js()

    assert _prelude_constant(js, "OVERLAY_HTML") == (ASSETS / "intro.html").read_text(
        encoding="utf-8"
    )
    assert _prelude_constant(js, "OVERLAY_CSS") == (ASSETS / "intro.css").read_text(
        encoding="utf-8"
    )
    assert (
        base64.b64decode(_prelude_constant(js, "FONT_DATA"))
        == (ASSETS / "archivo-capa.woff2").read_bytes()
    )
    assert js.endswith((ASSETS / "intro.js").read_text(encoding="utf-8"))
    # 한 줄짜리 문자열은 Components v2 가 파일 경로로 읽는다.
    assert "\n" in js


def test_every_display_string_is_covered_by_the_font_subset() -> None:
    """부분 글꼴에 없는 글자는 조용히 본문 글꼴로 떨어진다. 타이틀은 CSS 가 대문자로 바꾼다."""
    covered = set(intro_overlay.FONT_SUBSET_TEXT)
    shown = intro_overlay.BRAND + intro_overlay.ENTER_LABEL
    shown += "".join(line + line.upper() for line in intro_overlay.TITLE_LINES)

    assert set(shown) <= covered, sorted(set(shown) - covered)


def test_steps_follow_the_home_loading_stages() -> None:
    """가운데 세 단계는 HOME 진행 막대의 누적 퍼센트를 문턱으로 쓴다. 다섯 칸은 CSS 격자와 같다."""
    steps = intro_overlay._steps()
    thresholds = [step["until"] for step in steps if step["until"] is not None]

    assert len(steps) == 5
    assert "repeat(5," in (ASSETS / "intro.css").read_text(encoding="utf-8")
    assert steps[0]["until"] is None and steps[-1]["until"] is None
    assert thresholds == sorted(thresholds)
    assert set(thresholds) <= {stage.percent for stage in HOME_LOADING_STAGES}


def test_render_sends_the_hide_rule_first_and_an_unchanging_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """칸을 접는 규칙이 컴포넌트보다 먼저 가고, 페이로드는 회차마다 같다.

    같아야 Streamlit 이 큰 등록 메시지를 다시 보내지 않고 JS 도 다시 불리지 않는다.
    """
    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(intro_overlay.st, "html", lambda body: calls.append(("html", body)))
    monkeypatch.setattr(intro_overlay, "_INTRO", lambda **kwargs: calls.append(("intro", kwargs)))

    intro_overlay.render_intro_overlay()
    intro_overlay.render_intro_overlay()

    assert [kind for kind, _ in calls] == ["html", "intro", "html", "intro"]
    hide = calls[0][1]
    assert f".st-key-{intro_overlay.INTRO_OVERLAY_KEY}" in hide
    assert "display:none" in hide
    first, second = calls[1][1], calls[3][1]
    assert first["key"] == intro_overlay.INTRO_OVERLAY_KEY
    assert json.dumps(first["data"], sort_keys=True) == json.dumps(second["data"], sort_keys=True)
    assert first["data"]["palette"] == dict(tokens.INTRO_PALETTE)
    assert first["data"]["brand"] == intro_overlay.BRAND


def test_theme_reload_is_predicted_with_the_toggle_scripts_own_keys() -> None:
    """테마 새로고침을 미리 알아채는 규칙은 theme_toggle 과 같은 저장 키·버튼 id 를 쓴다.

    다르면 새로고침이 올 때 인트로가 이미 돌고 있어 끊겼다가 처음부터 다시 돈다.
    """
    from capa_simulation.components import theme_toggle
    from capa_simulation.design.theme import THEME_QUERY_PARAM

    theme = intro_overlay._data()["theme"]
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")

    assert theme == {
        "param": THEME_QUERY_PARAM,
        "storage_prefix": theme_toggle.THEME_STORAGE_PREFIX,
        "storage_suffix": theme_toggle.THEME_STORAGE_SUFFIX,
        "button_id": theme_toggle.THEME_BUTTON_ID,
    }
    for name in ("theme.storage_prefix", "theme.storage_suffix", "theme.button_id"):
        assert name in js


def test_the_intro_artwork_stays_hidden_until_the_intro_begins() -> None:
    """기다리는 동안에는 바탕 한 장만 — 심볼·워드마크는 인트로가 시작해야 보인다."""
    css = (ASSETS / "intro.css").read_text(encoding="utf-8")
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")

    intro_rule = re.search(r"^\.intro \{(.*?)\}", css, flags=re.MULTILINE | re.DOTALL)
    assert intro_rule and "visibility: hidden" in intro_rule.group(1)
    assert ".stage.begun .intro" in css
    assert 'stage.classList.add("begun")' in js


def test_intro_never_talks_back_to_python() -> None:
    """Enter 는 브라우저 안에서 끝난다. 값을 보내면 rerun 이 걸려 첫 실행을 끊는다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")

    assert not re.search(r"set(State|Trigger)Value\s*\(", js)
