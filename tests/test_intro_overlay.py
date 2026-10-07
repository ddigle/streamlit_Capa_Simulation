# Purpose: 입장 화면 등록 내용(틀·스타일·부분 글꼴)·같은 페이로드·Summary·사이드바 라벨을 검증한다.

from __future__ import annotations

import base64
import json
import math
import re
from typing import Any

import pytest
import streamlit as st

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
    monkeypatch.setattr(st, "html", lambda body: calls.append(("html", body)))
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


def test_the_sidebar_label_and_the_overlay_agree_on_one_id() -> None:
    """사이드바 라벨은 테마 iframe 스크립트가 세우고 입장 화면 JS 가 꾸민다 — 같은 id 다."""
    from capa_simulation.components import intro_summary

    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    script = intro_summary.summary_label_script()

    assert f'const SUMMARY_LABEL_ID = "{intro_overlay.SUMMARY_LABEL_ID}";' in js
    assert f'"{intro_overlay.SUMMARY_LABEL_ID}"' in script
    # 누르면 입장 화면 JS 가 연다. 누를 수 없는 표시면 아무것도 하지 않는다. 스크립트 자체는 상태가
    # 없어 회차마다 같은 문자열이다.
    assert "api.openSummary(label)" in script
    assert 'if (label.getAttribute("aria-disabled") === "true") return;' in script
    assert script == intro_summary.summary_label_script()
    # 툴바 Summary 단추는 걷었다(2026-10-06 사용자 결정 — 툴바는 Guide·테마·Print).
    assert "capa-summary-button" not in js and "SUMMARY_BUTTON_ID" not in js
    assert not hasattr(intro_summary, "summary_toolbar_script")


def test_the_summary_payload_reaches_the_overlay_without_talking_back() -> None:
    """요약 값은 따로 오는 컴포넌트가 창에 두고 오버레이에 넘긴다 — 파이썬으로는 되보내지 않는다."""
    from capa_simulation.components import intro_summary

    assert "window.__capaSummary = data;" in intro_summary._JS
    assert "api.setSummary(data)" in intro_summary._JS
    # 파이썬으로 가는 길은 「준비 중」 몫을 다시 받아 오는 trigger 하나뿐이다(rerun 한 번).
    assert re.findall(r"set(State|Trigger)Value\s*\(", intro_summary._JS) == ["Trigger"]
    assert 'window.__capaSummaryRefresh = () => component.setTriggerValue("refresh"' in (
        intro_summary._JS
    )
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    assert "window.__capaSummary !== undefined" in js


def test_the_summary_hides_its_slot_before_it_is_drawn(monkeypatch: pytest.MonkeyPatch) -> None:
    from capa_simulation.components import intro_summary

    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(st, "html", lambda body: calls.append(("html", body)))
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
    assert calls[1][1]["on_refresh_change"] is intro_summary._refresh_requested


def test_the_sidebar_label_is_the_wordmark_in_the_app_theme() -> None:
    """사이드바 머리칸의 `S.PKG CAPA` 라벨은 입장 화면 심볼·워드마크와 같은 모양이고 색은 앱
    테마를 따른다(2026-10-06 사용자 결정). 두 테마 값을 다 싣고 고르므로 iframe 내용은 테마와
    상관없이 같은 문자열이다. 글꼴은 입장 화면 JS 가 본 문서에 등록한 부분 글꼴을 다시 쓴다(파일을
    두 번 싣지 않는다).
    """
    from capa_simulation.components import intro_summary, theme_toggle

    script = intro_summary.summary_label_script()
    for mode in ("light", "dark"):
        for name in ("TEXT", "TEXT_MUTED", "ACCENT", "SURFACE", "BORDER"):
            assert str(tokens.palette_value(mode, name)) in script, (mode, name)
    # 고르는 규칙은 테마 버튼과 같은 한 벌이다.
    assert "capaTheme.resolve(parentWindow)" in script
    assert f"querySelector('{theme_toggle.SIDEBAR_HEADER_SLOT}')" in script
    # 입장 화면 워드마크와 같은 글꼴(Archivo 800 · 폭 75%)과 글자.
    assert '\\"CapaIntroDisplay\\"' in script
    assert "font-weight: 800; font-stretch: 75%;" in script
    assert intro_overlay.BRAND in script
    assert set(intro_overlay.BRAND) <= set(intro_overlay.FONT_SUBSET_TEXT)
    assert "FontFace" not in script and "woff2" not in script
    # 입장 화면 심볼과 같은 C 링 + 3×3 다이(모양 대조는 아래 메인 심볼 테스트).
    assert script.count("<rect ") == 9
    assert intro_overlay.MARK_RING_PATH in script
    # 키보드로 닿고(실제 단추) 읽는 이름이 있다.
    assert 'label = doc.createElement("button");' in script
    assert intro_overlay.SUMMARY_LABEL_ARIA in script
    assert intro_overlay.SUMMARY_LABEL_ARIA == "S.PKG CAPA — Summary 열기"


_RECT = re.compile(r'<rect [^>]*?x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)" rx="(\d+)"')
_RING = re.compile(r'<path [^>]*?d="([^"]+)"[^>]*>')


def _mark_parts(svg: str) -> tuple[list[str], list[tuple[int, ...]]]:
    """SVG 문자열에서 링 경로(d)와 다이 사각형(x, y, 폭, 높이, 모서리)을 뽑는다. 색은 자리마다 달라
    대조하지 않는다."""
    rings = _RING.findall(svg)
    dies = [tuple(int(value) for value in match) for match in _RECT.findall(svg)]
    return rings, dies


def test_the_main_mark_has_one_geometry_everywhere() -> None:
    """메인 심볼(C 링 + 3×3 다이, 2026-10-07 사용자 결정)은 입장 화면 머리 줄·입장 화면 가운데
    장면·사이드바 라벨·탭 아이콘 네 곳에 그린다. 한 곳만 고치면 서로 다른 심볼이 된다.

    링은 반지름 41 원의 오른쪽 ±35° 를 연 호다 — 위쪽 끝(−35°)에서 큰 호(1)·반시계(0)로 왼쪽을
    돌아 아래쪽 끝(+35°)에 닿는다. 다이는 크기 12 · 모서리 2 를 28 · 44 · 60 의 곱에 둔다.
    """
    from capa_simulation.components import intro_summary
    from capa_simulation.settings import FAVICON_PATH

    radius, opening = 41, math.radians(35)
    x_end = 50 + radius * math.cos(opening)
    y_top, y_bottom = 50 - radius * math.sin(opening), 50 + radius * math.sin(opening)
    ring = f"M{x_end:.2f} {y_top:.2f} A41 41 0 1 0 {x_end:.2f} {y_bottom:.2f}"
    assert intro_overlay.MARK_RING_PATH == ring
    assert intro_overlay.MARK_DIE_ORIGINS == (28, 44, 60)
    dies = [(x, y, 12, 12, 2) for y in (28, 44, 60) for x in (28, 44, 60)]

    # 입장 화면 머리 줄: 상수 둘과 그것을 쓰는 틀.
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    assert _prelude_constant(js, "MARK_RING") == ring
    found = re.search(r"^const MARK_DIES = \[([\d, ]+)\];$", js, flags=re.MULTILINE)
    assert found and tuple(int(v) for v in found.group(1).split(",")) == (28, 44, 60)
    head = _function_source(js, "brandMark")
    assert 'd="${MARK_RING}" pathLength="100" fill="none"' in head
    assert 'stroke-width="9" stroke-linecap="round"' in head
    assert 'x="${x}" y="${y}" width="12" height="12" rx="2"' in head
    assert "MARK_DIES.forEach((y, row) =>" in head and "MARK_DIES.forEach((x, col) =>" in head

    # 가운데 장면(워커라 상수를 못 본다): 같은 호·굵기·다이 중심(28 + 6 = 34 …)·크기.
    scene = _scene_source(js)
    assert "const RIM_OPEN = (35 * Math.PI) / 180;" in scene
    assert "const RIM_LEN = 41 * (TAU - 2 * RIM_OPEN);" in scene
    assert "g.arc(50, 50, 41, -RIM_OPEN, RIM_OPEN, true);" in scene
    assert "g.lineWidth = 9;" in scene
    assert "symbolDies.push({ x: 50 + x * 16, y: 50 + y * 16, order, fill });" in scene
    assert [50 + step * 16 - 6 for step in (-1, 0, 1)] == [28, 44, 60]
    assert "const s = 12 * (0.3 + 0.7 * e);" in scene
    assert "A44" not in js and "93.9" not in js

    # 사이드바 라벨과 탭 아이콘.
    for svg in (intro_summary._label_icon(), FAVICON_PATH.read_text(encoding="utf-8")):
        rings, rects = _mark_parts(svg)
        assert rings == [ring]
        assert sorted(rects, key=lambda r: (r[1], r[0])) == dies
        assert 'stroke-width="9"' in svg and 'stroke-linecap="round"' in svg


def test_the_head_mark_draws_scans_while_loading_then_spins_once() -> None:
    """입장 화면 머리 심볼의 움직임(2026-10-07 사용자 결정 — 모션 시안 넷 중 셋).

    머리가 처음 설 때 「그리며 모이기」, 아직 읽는 동안 「검사 스캔」 반복, 준비되면 그 바퀴를
    마치고 「반동 스핀」 한 번. 앱에서 Summary 를 열 때도 「그리며 모이기」 한 번. 움직임 줄이기면
    아무것도 걸지 않는다(그린 그대로의 심볼). 링은 바깥 `<svg>` 상자째 돌아 합성기가 돌린다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    css = (ASSETS / "intro.css").read_text(encoding="utf-8")

    head = _function_source(js, "brandMark")
    assert head.count("<svg ") == 2
    assert '<svg class="mark-ring"' in head and '<svg class="mark-dies"' in head
    assert ".logo .die {\n  transform-box: fill-box;\n  transform-origin: center;\n}" in css
    assert "grid-area: 1 / 1;" in css

    motion = _function_source(js, "markMotion")
    for name in ("function draw(delay)", "function scan()", "function spin()", "settle(isReady)"):
        assert name in motion, name
    assert 'host.querySelector(".mark-ring")' in motion
    # 그리며 모이기: 대시를 당겨 긋고, 바깥 여덟 다이 뒤에 가운데가 마지막.
    assert "strokeDashoffset" in motion and "MARK_DRAW_ORDER.forEach" in motion
    order = re.search(r"^const MARK_DRAW_ORDER = (\[[\d, ]+\]);$", js, flags=re.MULTILINE)
    assert order and sorted(json.loads(order.group(1))) == [0, 1, 2, 3, 5, 6, 7, 8]
    # 스캔: 다이를 회색(die-idle)에서 제 색으로. 스핀: 회전 키프레임이 시안과 같다.
    assert 'const idle = palette["die-idle"];' in motion
    for frame in ("rotate(-30deg) scale(.94)", "rotate(374deg) scale(1.02)", "rotate(360deg)"):
        assert frame in motion, frame
    settle = motion[motion.index("async function settle(isReady)") :]
    assert settle.index("while (!isReady())") < settle.index("await scan()")
    assert settle.index("await scan()") < settle.index("await spin()")

    # 언제 거는가: 머리가 떠오를 때(움직임 줄이기가 아닐 때만) 그리고, 준비 여부로 이어 간다.
    begin = _function_source(js, "createOverlay")
    begin = begin[begin.index("  function begin() {") :]
    begin = begin[: begin.index("\n  }\n")]
    reduced, moving = begin.split("} else {")
    assert "mark." not in reduced
    assert "mark.draw(REVEAL_AT_MS + TEXT_AFTER_REVEAL_MS)" in moving
    assert "mark.settle(() => ready)" in moving
    opening = js[
        js.index("async function openFromApp(button)") : js.index("async function toDetail()")
    ]
    assert "if (!reduce) mark.draw(MARK_REDRAW_AFTER_MS);" in opening
    summary_from_entry = js[js.index("async function summaryFromEntry()") :]
    summary_from_entry = summary_from_entry[: summary_from_entry.index("\n  }\n")]
    assert "mark." not in summary_from_entry
    hide = js[js.index("  function hide() {") :]
    assert "mark.cancel();" in hide[: hide.index("\n  }\n")]


def _label_css_rules(css: str) -> tuple[str, str]:
    """움직임 줄이기가 아닐 때만 거는 블록과 그 밖을 나눈다."""
    start = css.index("@media (prefers-reduced-motion: no-preference) {")
    end = css.index("\n}\n", start)
    return css[start:end], css[:start] + css[end:]


def test_the_sidebar_label_spins_every_twelve_seconds_and_nudges_on_hover() -> None:
    """사이드바 라벨의 C 링은 12초마다 「반동 스핀」을 한 번 하고(첫 바퀴는 2초 뒤), 올리거나 Tab
    초점이 닿으면 「살짝 감기」를 한다(2026-10-07 사용자 결정). CSS 만으로 돈다 — 타이머·rerun 이
    없다. 두 움직임이 서로의 transform 을 덮지 않게 링을 `<g>` 두 겹(바깥 감기 · 안 스핀)에, 가운데
    다이도 두 겹(바깥 숨 · 안 톡)에 싼다. 다이는 돌지 않는다. 움직임 줄이기면 걸지 않는다."""
    from capa_simulation.components import intro_summary

    icon = intro_summary._label_icon()
    assert '<g class="capa-mark-turn"><g class="capa-mark-spin"><path ' in icon
    assert '<g class="capa-mark-breathe"><rect class="capa-mark-pop" ' in icon
    assert icon.count("<g ") == 3

    for mode in ("light", "dark"):
        css = intro_summary._label_css(mode)
        moving, still = _label_css_rules(css)
        # 움직임은 모두 그 블록 안에서만 건다.
        assert "animation:" not in still
        assert "animation: capa-mark-spin 12s 2s infinite;" in moving
        assert "animation: capa-mark-pop 12s linear 2s infinite;" in moving
        assert "animation: capa-mark-nudge 0.52s;" in moving
        assert "animation: capa-mark-breathe 0.52s linear;" in moving
        assert ':hover:not([aria-disabled="true"]) .capa-mark-turn' in moving
        assert ":focus-visible .capa-mark-turn" in moving
        for name in ("spin", "pop", "nudge", "breathe"):
            assert f"@keyframes capa-mark-{name} {{" in still, name
        # 1.5초 모션을 12초 주기의 앞 12.5% 에 넣었다(시안 15% · 62% · 76% · 88% → ×0.125).
        spin = still[still.index("@keyframes capa-mark-spin {") :]
        for offset, frame in (
            ("1.875%", "rotate(-30deg) scale(.94)"),
            ("7.75%", "rotate(374deg) scale(1.02)"),
            ("9.5%", "rotate(354deg) scale(1)"),
            ("11%", "rotate(364deg) scale(1)"),
            ("12.5%, 100%", "rotate(360deg) scale(1)"),
        ):
            assert re.search(rf"{re.escape(offset)} \{{\s*transform: {re.escape(frame)};", spin)
        # 링은 뷰박스 가운데(50, 50)를 축으로, 가운데 다이는 제 가운데를 축으로 움직인다.
        assert "transform-box: view-box; transform-origin: 50px 50px;" in css
        assert "transform-box: fill-box; transform-origin: center;" in css


def test_the_centre_die_is_the_brand_warm_token_in_both_themes() -> None:
    """가운데 다이는 두 곳 모두 주황이다(2026-10-07 사용자 결정 — 상태색이 아니라 심볼의 고정
    강조색). 사이드바 라벨은 앱 테마 토큰(`BRAND_DIE_WARM`)을, 입장 화면은 자기 팔레트의
    `die-warn` 을 쓴다. 나머지 다이는 앱 강조색 그대로다."""
    from capa_simulation.components import intro_summary

    icon = intro_summary._label_icon()
    assert icon.count('fill="var(--capa-brand-core)"') == 1
    assert icon.count('fill="var(--capa-brand-die)"') == 8
    for mode in ("light", "dark"):
        css = intro_summary._label_css(mode)
        warm = tokens.palette_value(mode, "BRAND_DIE_WARM")
        accent = tokens.palette_value(mode, "ACCENT")
        assert f"--capa-brand-core: {warm};" in css
        assert f"--capa-brand-die: {accent};" in css
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    head = _function_source(js, "brandMark")
    assert 'row === 1 && col === 1 ? palette["die-warn"] : palette.accent' in head


def test_the_sidebar_label_says_why_it_cannot_open_the_summary() -> None:
    """요약이 없으면 라벨은 그대로 보이되 누를 수 없고, 풍선에 까닭을 단다. 라벨은 앱
    이름이기도 해서 감추지 않는다 — 입장 화면 JS 는 `display` 를 만지지 않고 `aria-disabled` 와
    `title` 만 정한다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    sync = js[js.index("function syncToolbar()") : js.index("api.setSummary = (payload) =>")]
    assert 'label.setAttribute("aria-disabled", can ? "false" : "true");' in sync
    assert "reason || text.label_off" in sync and "text.label_waiting" in sync
    assert "style.display" not in sync
    release = js[js.index("function release()") : js.index("function setInert(on)")]
    assert 'label.setAttribute("aria-disabled", "true");' in release
    assert "style.display" not in release
    text = intro_overlay._data()["text"]
    assert text["label_open"] == intro_overlay.SUMMARY_LABEL_OPEN
    assert text["label_waiting"] == intro_overlay.SUMMARY_LABEL_WAITING
    assert text["label_off"] == intro_overlay.SUMMARY_LABEL_OFF


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
    """기준선 이름표는 파이썬이 사사오입한 글자(`*_label`)를 쓰고, 선 자리는 정확한 숫자다.

    기준은 달마다 온다 — 같은 값이 이어지는 달끼리 한 구간으로 묶어 계단으로 긋고, 이름표는
    구간마다 단다(2026-10-06 사용자 결정). 구간과 이름표 자리는 배치(`layoutSummary`)가 한 번 정하고
    `drawBars` 는 그리기만 한다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    scene = js[js.index("function layoutSummary(") : js.index("function drawSheets(")]

    assert "[sum.warning || [], sum.warning_label || []," in scene
    assert "[sum.secure || [], sum.secure_label || []," in scene
    assert "yBar(run.v)" in scene and "last.v === v" in scene
    assert "run.label" in scene


def test_summary_legend_names_three_states_without_numbers() -> None:
    """범례는 「확보 · 경고 · 부족」 세 이름만이고 기준 숫자를 적지 않는다.

    막대 밑 상태 글자(`status`)도 지금은 같은 이름이지만 범례 이름은 따로 보낸다 — 둘은 뜻이
    갈릴 수 있는 자리다(범례는 색의 뜻, 상태 글자는 그 달의 판정).
    """
    text = intro_overlay._data()["text"]
    assert text["legend"] == {"secure": "확보", "warning": "경고", "shortage": "부족"}
    assert text["status"]["secure"] == "확보"
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    labels = js[js.index("function buildLabels(") :]
    labels = labels[: labels.index("const legend =")]
    assert "legendText.secure" in labels and "secure_label" not in labels


def test_summary_axis_and_bar_labels_match_the_point_value_size() -> None:
    """생산계획 달 이름, 막대 밑 공정 이름·상태(부족 대수)는 점 위 값 글자와 같은 14px 다.

    상태 글자는 칸 폭을 넘을 때만(휴대폰 폭) 여섯 칸을 함께 줄인다 — 기본 크기는 14px 그대로다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    scene = js[js.index("function drawLine(") : js.index("function drawSheets(")]
    layout = js[js.index("function layoutSummary(") : js.index("function layoutSheets(")]

    assert "g.font = `700 14px ${numStack}`;" in scene
    assert "sum.months.forEach" in scene
    month_font = scene[: scene.index("sum.months.forEach")].rsplit("g.font = ", 1)[1]
    assert month_font.startswith("`500 14px ")
    assert "fit(b.process" in scene
    process_font = scene[: scene.index("fit(b.process")].rsplit("g.font = ", 1)[1]
    assert process_font.startswith("`500 14px ")
    assert "g.font = `700 ${statusPx}px ${bodyStack}`;" in scene
    assert "fitPx(shown.map(statusText), 700, 14, " in layout
    assert "10.5px" not in scene and "700 13px" not in scene


def _between(js: str, start: str, end: str) -> str:
    return js[js.index(start) : js.index(end, js.index(start))]


def test_summary_sheet_text_is_fitted_once_in_the_layout() -> None:
    """월별 시트의 이름·값·단위는 칸 폭을 재어 겹치지 않게 놓는다.

    재지 않으면 1100px 창에서 값이 「Density」를 덮는다. 배치(`layoutSheets`)가 가장 긴 글자를
    한 번 재어 여섯 칸의 모양을 정하고 `drawSheets` 는 그 값으로 그리기만 한다 — 한 줄(18px) →
    값 줄이기(바닥 14px) → 이름을 값 위 줄로 → 시트 접기 차례다. 재는 글자는 세기가 끝난 마지막
    값이라 움직임을 줄여도(`reduce`) 같은 배치다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    layout = _between(js, "function layoutSheets(", "function drawLine(")
    draw = _between(js, "function drawSheets(", "function drawSummary(")

    assert "const SHEET_VALUE_PX = 18;" in js and "const SHEET_VALUE_FLOOR = 14;" in js
    assert "widest(" in layout and "valueText(v, row.digits)" in layout
    assert "stacked" in layout and "wrap = true" in layout
    assert "cnt" not in layout and "reduce" not in layout
    assert "const sheet = layoutSheets(G, n);" in js
    # 그리기는 배치가 정한 크기·모양만 쓴다 — 고정 18px 값 글자나 프레임마다 재는 일이 없다.
    assert "measureText" not in draw and "700 18px" not in draw
    assert "g.font = `700 ${px}px ${numStack}`;" in draw
    assert "const px = mA > 0 ? K.px + (K.pxA - K.px) * mA : K.px;" in draw
    assert "K.stacked" in draw and "s.kv[r]" in draw
    # 너무 작은 도넛은 그리지 않고, 말풍선 자리도 함께 없앤다.
    assert "fits >= 40 ? fits : 0" in layout
    assert "if (!s.box) return;" in js


def test_summary_labels_pick_a_free_spot_once_in_the_layout() -> None:
    """눈금 글자·기준선 이름표는 점·값·막대·확보율 글자와 겹치지 않는 자리를 배치에서 한 번 고른다.

    자리가 없으면 눈금 글자는 쓰지 않고(값은 점 위에 있다), 기준선 이름표는 바탕을 깔아 기본
    자리에 단다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    layout = _between(js, "function layoutSummary(", "function layoutSheets(")
    draw_line = _between(js, "function drawLine(", "function drawBars(")
    draw_bars = _between(js, "function drawBars(", "function drawSheets(")

    assert layout.count("freeSpot(") == 2
    assert "lineObstacles" in layout and "barObstacles" in layout and "backed: true" in layout
    assert "V.tickLabels" in draw_line and "fillText(`${v.toFixed(" not in draw_line
    assert "spot.backed" in draw_bars and "measureText" not in draw_bars


def test_summary_rows_stand_above_the_charts_on_narrow_screens() -> None:
    """760px 이하에서는 행 이름 칸을 없애고 이름을 각 줄 위 띠에 올린다 — 칸을 남기면 여섯 달 칸이
    30px 로 줄어 달·값·막대 글자가 서로 겹친다(390px). 경계는 intro.css 의 @media 와 같다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    grid = _function_source(js, "summaryGrid")
    place = _between(js, "function placeLabels(", "function scheduleLabels(")

    assert "const narrow = W <= 760;" in grid
    assert "const labelW = narrow ? 0 :" in grid and "head: heads[2]" in grid
    assert "row.y - row.head" in place
    css = (ASSETS / "intro.css").read_text(encoding="utf-8")
    narrow_block = css[css.index("@media (max-width: 760px) {") : css.index("@keyframes slide")]
    assert re.search(r"\.sum-label \{\s*flex-direction: row;", narrow_block)
    # 도넛을 그리지 않는 화면은 제품 범례도 걷는다 — 장면이 돌려준 도넛 말풍선 자리로 안다.
    assert 'labels.classList.toggle("no-mix", !hits.some((h) => h.k === "seg"));' in js
    assert ".sum-labels.no-mix .sum-label:nth-child(3) .legend" in css


def test_closing_the_summary_returns_focus_to_the_sidebar_label() -> None:
    """사이드바 라벨로 연 요약을 Esc·Detail 로 닫으면 포커스가 그 라벨로 돌아간다.

    돌려주지 않으면 body 에 남아 키보드 사용자가 제자리를 잃었다(2026-10-05 E2E — Guide 는
    `#capa-guide-button` 으로 돌려준다). 처음 입장 화면은 연 단추가 없으니 돌려줄 곳도 없다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    opening = js[js.index("async function openFromApp(button)") :]
    assert "opener = button || null;" in opening[: opening.index("snapToSummary()")]
    closing = js[js.index("async function toDetail()") : js.index("function hide()")]
    assert closing.index("hide();") < closing.index("opener.focus(")
    assert "opener = null;" in closing


def test_tab_stays_inside_the_overlay_while_it_is_open() -> None:
    """덮개가 서 있으면 Tab · Shift+Tab 이 덮개 안 단추만 돈다(2026-10-06 E2E).

    아래 앱(#root)은 inert 지만 덮개 호스트가 body 의 마지막이라, Detail 다음 Tab 이 페이지를
    떠나 브라우저 주소창으로 나갔다. Esc 로 닫는 길과 툴바 단추로 포커스를 돌려주는 길은 그대로다.
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    on_key = js[js.index("function onKey(event)") :]
    on_key = on_key[: on_key.index("\n  }\n")]
    assert 'mode !== "hidden" && event.key === "Tab"' in on_key
    assert on_key.index("cycleFocus(event)") < on_key.index('event.key === "Escape"')
    assert 'mode === "summary" && event.key === "Escape") toDetail();' in on_key
    cycle = js[js.index("function cycleFocus(event)") : js.index("function onFocusIn(event)")]
    assert "event.preventDefault();" in cycle
    assert "shadow.activeElement" in cycle
    focusables = js[js.index("function focusables()") : js.index("function cycleFocus(event)")]
    for guard in ("!el.disabled", "!el.hidden", 'visibility !== "hidden"'):
        assert guard in focusables, guard
    assert 'document.addEventListener("focusin", onFocusIn);' in js
    assert 'document.removeEventListener("focusin", onFocusIn);' in js


# --------------------------------------------------------- Summary 토글 셋(선행 B/O·선행 입고·GAP)


def test_summary_toggles_sit_right_after_the_docked_detail() -> None:
    """토글 셋은 머리 줄에서 Detail(도킹 자리) 바로 오른쪽이다 — Tab 차례가 Detail 다음이고, 입장
    화면에서는 보이지 않다가 Summary 가 조립될 때 떠오른다."""
    html = (ASSETS / "intro.html").read_text(encoding="utf-8")
    head = html[html.index('<header class="head">') : html.index("</header>")]
    assert (
        head.index('data-slot="dock"')
        < head.index('data-slot="toggles"')
        < head.index('data-slot="asof"')
    )
    assert 'role="group"' in head
    css = (ASSETS / "intro.css").read_text(encoding="utf-8")
    assert re.search(r"\.toggles \{[^}]*visibility: hidden;", css)
    assert re.search(r"\.stage\.summary \.toggles \{\s*visibility: visible;", css)
    # 휴대폰 폭에서는 머리 줄 밑 둘째 줄로 내린다 — 머리 줄과 Detail 은 움직이지 않는다.
    narrow = css[css.index("@media (max-width: 760px) {") : css.index("@keyframes slide")]
    assert re.search(r"\.toggles \{\s*position: absolute;", narrow)
    # 머리 줄이 빠듯하면 라벨은 한 줄을 지키고 공식버전 칩이 말줄임으로 준다(768px 에서 접혔다).
    assert re.search(r"\.brand \{\s*flex: none;\s*white-space: nowrap;", css)
    assert re.search(r"\.asof \.chip \{\s*flex: 0 1 auto;\s*min-width: 0;", css)
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    entry = _between(js, "async function summaryFromEntry(", "function snapToSummary(")
    assert entry.index("dockDetail(true);") < entry.index("revealToggles(true);")
    snap = _between(js, "function snapToSummary(", "function holeAt(")
    assert "revealToggles(false);" in snap
    # 떠오르는 동안(아직 투명한 동안)은 inert 로 묶어 Tab 이 닿지 않고, 덮개 안 Tab 순환도 건너뛴다.
    # 「summary」 를 거는 그 자리에서 묶는다 — 토글은 그 순간부터 보이는 자리(투명)다.
    assert (
        entry.index('stage.classList.add("summary");')
        < entry.index("if (!reduce) toggleBox.inert = true;")
        < entry.index("dockDetail(true);")
    )
    reveal = _between(
        js, "function revealToggles(", "/* ------------------------------------------------ 상태"
    )
    assert "toggleBox.inert = moving.length > 0;" in reveal
    assert "if (round === revealRound) toggleBox.inert = false;" in reveal
    focusables = _between(js, "function focusables()", "function cycleFocus(event)")
    assert '!el.closest("[inert]")' in focusables


def test_summary_toggles_are_pressed_buttons_with_reasons_when_off() -> None:
    """누름 상태는 `aria-pressed` 이고, 켤 수 없으면 `aria-disabled` 로 두고 풍선에 까닭을 단다 —
    `disabled` 가 아니라 Tab 으로 닿아 까닭을 읽는다. Space · Enter 는 단추가 click 으로 바꾼다."""
    text = intro_overlay._data()["text"]
    assert [item["key"] for item in text["toggles"]] == ["advance", "shipment", "comparison"]
    assert [item["label"] for item in text["toggles"]] == ["선행 B/O", "선행 입고", "GAP"]
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    toggles = _between(js, "const view = api.view ||", "function revealToggles(")
    assert 'aria-pressed="false" aria-disabled="true"' in toggles
    assert 'button.setAttribute("aria-pressed"' in toggles
    # 「준비 중」이면 켜기만 잠근다 — 켜 둔 것은 끌 수 있다.
    assert (
        'button.setAttribute("aria-disabled", can || (pending && view[key]) ? "false" : "true");'
        in (toggles)
    )
    assert "if (!view[key] && !canToggle(key)) return;" in toggles
    assert 'if (button.getAttribute("aria-disabled") === "true") return;' in toggles
    assert "button.title = toggleTitle(spec);" in toggles
    # 켤 수 없다고 정해진 토글만 끈다 — 요약이 잠깐 없거나(일시적 실패) 그 몫이 「준비 중」이면 고른
    # 상태를 지킨다. 상태는 탭이 살아 있는 동안만(창의 `__capaIntro`) 기억한다.
    assert "if (summary && part && !part.available && !pending) view[key] = false;" in toggles
    assert "sessionStorage" not in toggles and "localStorage" not in toggles
    # 라벨은 본문 글꼴이다 — 부분 글꼴에 한글·`B`·`/` 가 없다.
    css = (ASSETS / "intro.css").read_text(encoding="utf-8")
    assert re.search(r"\.tg \{[^}]*font: 600 13px/1 var\(--body\);", css)
    assert not set("B/선행입고") <= set(intro_overlay.FONT_SUBSET_TEXT)


def test_summary_toggles_change_only_the_browser_and_move_from_where_they_are() -> None:
    """토글은 장면에 `view` 메시지만 보낸다(rerun 없음). 장면은 누를 때마다 **지금 값에서** 새
    목표로 트윈을 다시 걸고, 움직임을 줄였으면 바로 바뀐다. 워커가 죽으면 마지막 `view` 를
    되살린다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    assert (
        'sceneHandle.post({ type: "view", view: { ...view }, instant: !!instant, restart });' in js
    )
    # 켜 둔 채 「준비 중」이던 토글에 값이 닿으면 그 토글만 꺼진 자리에서 다시 움직여 들어온다.
    assert "postView(!viewSent, viewSent ? arrived : []);" in js
    assert "for (const key of m.restart || [])" in _scene_source(js)
    assert '"summary-on", "view", "run", "resize"' in js
    scene = _scene_source(js)
    assert "function retarget(ch, want, t, instant)" in scene
    assert "const cur = tweenValue(tw, t, OUT);" in scene
    assert "retarget(ch, want[ch], t, reduce || !!m.instant)" in scene
    # 기본 모습은 토글이 없던 때와 같은 배치다 — 토글 값이 범위 안이면 축을 넓히지 않는다.
    layout = _between(js, "function layoutSummary(", "function layoutSheets(")
    assert "const lineBase = lineLayout(lineCtx, range, sum.density, null, null);" in layout
    assert "return hi === range.hi && lo === range.lo ? range : { lo, hi };" in layout
    draw_line = _between(js, "function drawLine(", "function drawBars(")
    assert "const now = lineNow();" in draw_line and "now.yLine(" in draw_line


def test_reduced_motion_draws_on_messages_instead_of_a_frame_loop() -> None:
    """움직임을 줄였으면 그림이 시간에 따라 바뀌지 않는다 — 프레임 루프를 세우지 않고 그림을 바꾸는
    메시지(토글 포함)를 받을 때만 한 번 그린다(B4: 정지 그림을 매 프레임 다시 그려 CPU 를 썼다)."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    scene = _scene_source(js)
    loop = scene[scene.index("  function loop() {") :]
    loop = loop[: loop.index("\n  }\n")]
    assert (
        loop.index("if (reduce) {") < loop.index("paintOnce();") < loop.index("nextFrame(frame);")
    )
    handler = scene[scene.index("port.onmessage = (event) => {") :]
    for kind in ("begin", "progress", "resize", "summary-on", "view"):
        branch = handler[handler.index(f'm.type === "{kind}"') :]
        branch = branch[: branch.index("} else if")]
        assert "loop();" in branch, kind
    summary_branch = handler[handler.index('m.type === "summary")') :]
    summary_branch = summary_branch[: summary_branch.index("} else if")]
    assert "layoutSummary();" in summary_branch and "loop();" in summary_branch


def test_opening_the_summary_asks_once_for_pending_parts() -> None:
    """「준비 중」 몫(페이지 뒤에서 만드는 GAP)이 있을 때만, 한 번 열 때 한 번만 다시 받아 온다 —
    평소 Summary 열기에는 rerun 이 없다."""
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    ask = _between(js, "function askRefreshIfPending()", "let revealRound = 0;")
    assert "if (refreshAsked || !summary || !summary.toggles) return;" in ask
    assert 'if (!waiting || typeof window.__capaSummaryRefresh !== "function") return;' in ask
    assert ask.index("refreshAsked = true;") < ask.index("window.__capaSummaryRefresh();")
    for opening in ("async function summaryFromEntry(", "async function openFromApp(button)"):
        body = js[js.index(opening) :]
        body = body[: body.index("\n  }\n")]
        assert body.index("refreshAsked = false;") < body.index("askRefreshIfPending();"), opening
    assert js.count("window.__capaSummaryRefresh();") == 1
