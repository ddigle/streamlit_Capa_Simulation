# Purpose: 입장 화면 등록 내용(틀·스타일·부분 글꼴)·같은 페이로드·Summary·사이드바 라벨을 검증한다.

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
    # 입장 화면 심볼과 같은 노치 링 + 3×3 다이.
    assert script.count("<rect ") == 9
    assert "M53 93.9 A44 44 0 1 0 47 93.9 L50 90.6 Z" in script
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    assert "M53 93.9 A44 44 0 1 0 47 93.9 L50 90.6 Z" in js
    # 키보드로 닿고(실제 단추) 읽는 이름이 있다.
    assert 'label = doc.createElement("button");' in script
    assert intro_overlay.SUMMARY_LABEL_ARIA in script
    assert intro_overlay.SUMMARY_LABEL_ARIA == "S.PKG CAPA — Summary 열기"


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
    구간마다 단다(2026-10-06 사용자 결정).
    """
    js = (ASSETS / "intro.js").read_text(encoding="utf-8")
    scene = js[js.index("function drawBars(") : js.index("function drawSheets(")]

    assert "[sum.warning || [], sum.warning_label || []," in scene
    assert "[sum.secure || [], sum.secure_label || []," in scene
    assert "L.yBar(run.v)" in scene and "last.v === v" in scene
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
