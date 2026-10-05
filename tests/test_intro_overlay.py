# Purpose: 입장 화면의 등록 내용(틀·스타일·부분 글꼴)·같은 페이로드·Summary 연결을 검증한다.

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


def test_bundled_fonts_are_woff2_shipped_with_their_license() -> None:
    """사내망에는 외부 글꼴이 없다. 부분 글꼴 둘이 저장소에 있고 OFL 라이선스가 곁에 있어야 한다."""
    license_text = (ASSETS / "OFL.txt").read_text(encoding="utf-8")

    for name in ("archivo-capa.woff2", "archivo-capa-number.woff2"):
        assert (ASSETS / name).read_bytes()[:4] == b"wOF2", name
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
    assert (
        base64.b64decode(_prelude_constant(js, "NUMBER_FONT_DATA"))
        == (ASSETS / "archivo-capa-number.woff2").read_bytes()
    )
    assert js.endswith((ASSETS / "intro.js").read_text(encoding="utf-8"))
    # 한 줄짜리 문자열은 Components v2 가 파일 경로로 읽는다.
    assert "\n" in js


def test_every_display_string_is_covered_by_the_font_subset() -> None:
    """부분 글꼴에 없는 글자는 조용히 본문 글꼴로 떨어진다. 타이틀은 CSS 가 대문자로 바꾼다.

    시트의 달(`26.10`)은 표시 글꼴, 차트 숫자·단위는 숫자 글꼴이다.
    """
    covered = set(intro_overlay.FONT_SUBSET_TEXT)
    shown = intro_overlay.BRAND + intro_overlay.DETAIL_LABEL + intro_overlay.SUMMARY_LABEL
    shown += "".join(line + line.upper() for line in intro_overlay.TITLE_LINES)
    shown += "0123456789."

    assert set(shown) <= covered, sorted(set(shown) - covered)
    assert set("0123456789.%K") <= set(intro_overlay.NUMBER_FONT_SUBSET_TEXT)


def test_steps_follow_the_order_they_actually_finish() -> None:
    """요약은 부트스트랩 뒤·페이지 앞에서 보내 HOME 막대보다 먼저 찬다. 여섯 칸은 CSS 격자와 같다.

    `reach` 는 앞에서부터 끝난 만큼 채운다 — 늦게 끝나는 단계가 앞에 서면 그 뒤가 한꺼번에 찬다.
    """
    steps = intro_overlay._steps()
    thresholds = [step["until"] for step in steps if "until" in step]

    assert len(steps) == 6
    assert "repeat(6," in (ASSETS / "intro.css").read_text(encoding="utf-8")
    assert [step.get("signal") for step in steps] == ["boot", "summary", None, None, None, "end"]
    assert thresholds == sorted(thresholds)
    assert set(thresholds) <= {stage.percent for stage in HOME_LOADING_STAGES}
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    for signal in ("boot", "summary"):
        assert f'step.signal === "{signal}"' in js


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


def test_theme_reload_is_predicted_with_the_toggle_scripts_own_rule() -> None:
    """테마 새로고침을 미리 알아채는 규칙은 theme_toggle 과 **같은 규칙 문자열**이다.

    다르면 새로고침이 올 때 인트로가 이미 돌고 있어 끊겼다가 처음부터 다시 돌거나, 오지 않을
    새로고침을 10초 기다린다. 입장 화면은 예측만 하고 아무것도 적지 않는다.
    """
    from capa_simulation.components import theme_toggle
    from capa_simulation.design.theme import THEME_QUERY_PARAM

    theme = intro_overlay._data()["theme"]
    registered = intro_overlay._registered_js()
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")

    assert theme == {"param": THEME_QUERY_PARAM, "button_id": theme_toggle.THEME_BUTTON_ID}
    assert theme_toggle.THEME_RULE_SCRIPT in registered
    assert registered.index(theme_toggle.THEME_RULE_SCRIPT) < registered.index(js)
    pending = _function_source(js, "themeReloadPending")
    assert "capaTheme.resolve(window)" in pending
    assert "state.stale" in pending and "theme.param" in pending
    # 테마 스크립트가 먼저 돌아 이미 새로고침을 걸었으면 그 표지로 안다.
    assert "window.__capaThemeReloading === true" in pending
    assert "parentWindow.__capaThemeReloading = true;" in theme_toggle._SCRIPT
    # 저장 키를 따로 만들지 않고, 저장소에 쓰지 않는다.
    assert "stActiveTheme" not in js and "storage_prefix" not in js
    assert not re.search(r"(capaTheme\.(sync|choose)|localStorage\.setItem)", js)
    assert "theme.button_id" in js


def _scene_source(js: str) -> str:
    start = js.index("function scene(port, gridOf) {")
    end = js.index("\n}\n", start)
    return js[start : end + 2]


def test_the_scene_runs_in_a_worker_with_a_main_thread_fallback() -> None:
    """움직임은 워커의 OffscreenCanvas 에서 돈다 — 첫 로딩 동안 메인 스레드가 막혀도 끊기지 않는다.

    워커·OffscreenCanvas 를 못 쓰거나 워커가 죽으면 같은 장면을 메인 스레드에서 돌린다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")

    assert "transferControlToOffscreen" in js
    assert "new Worker(" in js
    assert "scene.toString()" in js
    assert "runOnMain(" in js and "worker.onerror" in js
    # 덮개를 걷을 때 장면을 멈추고 워커를 닫는다.
    assert "sceneHandle.stop()" in js and "worker.terminate()" in js


def _function_source(js: str, name: str) -> str:
    start = js.index(f"function {name}(")
    end = js.index("\n}\n", start)
    return js[start : end + 2]


def test_the_scene_uses_no_name_from_outside_itself() -> None:
    """`scene()` 과 그와 함께 실어 보내는 `summaryGrid()` 는 문자열로 바뀌어 워커에서 돈다 —
    이 파일의 다른 이름을 쓰면 워커에서 죽는다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    top_level = set(re.findall(r"^(?:const|let|function|async function) (\w+)", js, re.MULTILINE))
    for name in ("scene", "summaryGrid"):
        body = _function_source(js, name)
        own = set(re.findall(r"\b(?:const|let|function) (\w+)", body))
        outside = {item for item in top_level - own - {name} if re.search(rf"\b{item}\b", body)}
        assert not outside, (name, sorted(outside))
    assert "(${scene.toString()})(self, ${summaryGrid.toString()})" in js


def test_the_scene_and_the_page_share_one_timeline() -> None:
    """원형 펼침 시각은 장면(워커)과 입장 화면 글자(메인)가 따로 들고 있다 — 같아야 맞물린다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    body = _scene_source(js)

    def value(pattern: str, text: str) -> int:
        found = re.search(pattern, text)
        assert found, pattern
        return int(found.group(1))

    assert value(r"const REVEAL_AT_MS = (\d+);", js) == value(r"const REVEAL_AT = (\d+);", body)
    assert value(r"const REVEAL_MS = (\d+);", js) == value(r"const REVEAL_MS = (\d+);", body)


def test_nothing_is_drawn_until_the_intro_begins() -> None:
    """테마 새로고침을 기다리는 동안 장면은 비워 두고 HTML 바탕(앱 바탕색) 한 장만 보인다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    html = (ASSETS / "intro.html").read_text(encoding="utf-8")

    assert "if (!beginAt) return;" in _scene_source(js)
    assert (
        html.index('class="intro-bg"') < html.index('class="scene"') < html.index('class="entry"')
    )


def test_intro_never_talks_back_to_python() -> None:
    """Enter 는 브라우저 안에서 끝난다. 값을 보내면 rerun 이 걸려 첫 실행을 끊는다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")

    assert not re.search(r"set(State|Trigger)Value\s*\(", js)


def test_the_toolbar_button_and_the_overlay_agree_on_one_id() -> None:
    """툴바 단추는 테마 iframe 스크립트가 세우고 입장 화면 JS 가 꾸민다 — 같은 id 를 봐야 한다."""
    from capa_simulation.components import intro_summary

    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    script = intro_summary.summary_toolbar_script()

    assert f'const SUMMARY_BUTTON_ID = "{intro_summary.SUMMARY_BUTTON_ID}";' in js
    assert f'"{intro_summary.SUMMARY_BUTTON_ID}"' in script
    # 누르면 입장 화면 JS 가 연다. 스크립트 자체는 상태가 없어 회차마다 같은 문자열이다.
    assert "api.openSummary(button)" in script
    assert script == intro_summary.summary_toolbar_script()


def test_the_summary_payload_reaches_the_overlay_without_talking_back() -> None:
    """요약 값은 따로 오는 컴포넌트가 창에 두고 오버레이에 넘긴다 — 파이썬으로는 되보내지 않는다."""
    from capa_simulation.components import intro_summary

    assert "window.__capaSummary = data;" in intro_summary._JS
    assert "api.setSummary(data)" in intro_summary._JS
    assert not re.search(r"set(State|Trigger)Value\s*\(", intro_summary._JS)
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    assert "window.__capaSummary !== undefined" in js


def test_the_summary_hides_its_slot_before_it_is_drawn(monkeypatch: pytest.MonkeyPatch) -> None:
    from capa_simulation.components import intro_summary

    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(intro_summary.st, "html", lambda body: calls.append(("html", body)))
    monkeypatch.setattr(
        intro_summary, "_SUMMARY", lambda **kwargs: calls.append(("summary", kwargs))
    )
    monkeypatch.setattr(
        intro_summary, "official_summary_data", lambda path: {"available": False, "reason": "x"}
    )

    intro_summary.render_intro_summary("db")

    assert [kind for kind, _ in calls] == ["html", "summary"]
    assert f".st-key-{intro_summary.INTRO_SUMMARY_KEY}" in calls[0][1]
    assert calls[1][1]["key"] == intro_summary.INTRO_SUMMARY_KEY


def test_the_toolbar_summary_button_is_a_sibling_of_guide() -> None:
    """툴바 Summary 는 Guide 와 같은 윤곽 단추에 앱 색 16px 웨이퍼다(2026-10-03 사용자 결정).

    입장 화면 옷(검은 알약·압축 글꼴·떠오르는 움직임)을 입으면 툴바와 결이 어긋난다. 두 테마 값을 다
    싣고 고르므로 iframe 내용은 테마와 상관없이 같은 문자열이다.
    """
    from capa_simulation.components import intro_summary, page_guide

    script = intro_summary.summary_toolbar_script()
    for mode in ("light", "dark"):
        for name in ("BORDER", "TEXT", "TEXT_MUTED", "ACCENT"):
            assert str(tokens.palette_value(mode, name)) in script, (mode, name)
    for rule in ('"border-radius:8px"', '"font-size:13px"', '"font-weight:600"', '"line-height:1"'):
        assert rule in script and rule in page_guide._SCRIPT, rule
    assert "999px" not in script and "CapaIntroDisplay" not in script and "translate" not in script
    # 꾸밈은 툴바 스크립트 한 곳이다. 입장 화면 JS 는 보임만 정한다.
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    assert "TOOLBAR_STYLE_ID" not in js and "capa-mini" not in js


def test_summary_rows_keep_only_the_production_caption() -> None:
    """행 이름 아래 설명은 단위가 필요한 생산계획만 남긴다(2026-10-03 사용자 결정).

    B/N 확보율·월별 시트는 범례가 뜻을 나른다. 설명이 없는 행은 빈 줄도 만들지 않는다 — 빈 줄의
    음수 여백이 범례를 행 이름 쪽으로 끌어올린다.
    """
    rows = intro_overlay._data()["text"]["rows"]

    assert [row["title"] for row in rows] == ["생산계획", "B/N 확보율", "월별 시트"]
    assert [row.get("sub") for row in rows] == ["Density · 억Gb", None, None]
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    assert '${row.sub ? `<div class="s">' in js
    css = (ASSETS / "intro.css").read_text(encoding="utf-8")
    assert re.search(r"\.sum-label \.t \{\s*font: 800 20px/", css)


def test_summary_threshold_text_is_the_rounded_label_and_the_line_stays_exact() -> None:
    """범례·기준선 이름표는 파이썬이 사사오입한 글자(`*_label`)를 쓰고, 선 자리는 정확한 숫자다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")

    assert "summary.secure_label" in js and "summary.warning_label" in js
    assert "[sum.warning, sum.warning_label," in js and "[sum.secure, sum.secure_label," in js
    assert "L.yBar(v)" in js
    assert not re.search(r">\$\{summary\.secure\}%`\]", js)


def test_summary_axis_and_bar_labels_match_the_point_value_size() -> None:
    """생산계획 달 이름, 막대 밑 공정 이름·상태(부족 대수)는 점 위 값 글자와 같은 14px 다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    scene = js[js.index("function drawLine(") : js.index("function drawSheets(")]

    assert "g.font = `700 14px ${numStack}`;" in scene
    assert "sum.months.forEach" in scene
    month_font = scene[: scene.index("sum.months.forEach")].rsplit("g.font = ", 1)[1]
    assert month_font.startswith("`500 14px ")
    assert "fit(b.process" in scene
    process_font = scene[: scene.index("fit(b.process")].rsplit("g.font = ", 1)[1]
    assert process_font.startswith("`500 14px ")
    assert "g.font = `700 14px ${bodyStack}`;" in scene
    assert "10.5px" not in scene and "700 13px" not in scene


def test_closing_the_toolbar_summary_returns_focus_to_its_button() -> None:
    """툴바 Summary 로 연 요약을 Esc·Detail 로 닫으면 포커스가 그 단추로 돌아간다.

    돌려주지 않으면 body 에 남아 키보드 사용자가 제자리를 잃었다(2026-10-05 E2E — Guide 는
    `#capa-guide-button` 으로 돌려준다). 처음 입장 화면은 연 단추가 없으니 돌려줄 곳도 없다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    opening = js[js.index("async function openFromApp(button)") :]
    assert "opener = button || null;" in opening[: opening.index("snapToSummary()")]
    closing = js[js.index("async function toDetail()") : js.index("function hide()")]
    assert closing.index("hide();") < closing.index("opener.focus(")
    assert "opener = null;" in closing
