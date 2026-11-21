# Purpose: 풍선 1초 지연의 껍데기 CSS · 부품 기본값 · 그림 웜업 · 기대는 프런트 이름을 고정한다.
# 고정한다.

"""풍선은 마우스를 1초 올려 둔 뒤에 뜬다(2026-11-21 사용자 결정 — 설계 규칙 UI-NAV-04).

값은 `components/tip_delay.py` 의 `TIP_DELAY_MS` 하나이고, 껍데기 스타일(`app_header.SHELL_STYLE`)의
`:root` 사용자 정의 속성으로 앱 전체에 간다. 이 시험은 넷을 본다.

- 껍데기 CSS — 값 · 애니메이션(`visibility` 포함)이 `@media` 밖 맨 앞 한 벌이고, 거는 규칙이 화면
  덩어리 안 · 인쇄 덩어리 밖이며 Streamlit 이 이미 기다린 만큼을 뺀다.
- 부품 기본값 — 그림자 DOM · 자체 풍선 부품이 그 값을 읽고, 못 읽을 때의 기본값이 같은 1초다.
- 그림 웜업 스크립트 — 그림에 처음 들어올 때만 기다리고 그 안에서는 곧바로다(가짜 문서로 돌린다).
- 기대는 프런트 이름 — Streamlit 풍선 글 상자 `data-testid` 셋 · JS 지연(200 · 600ms) · Plotly 풍선
  묶음 · Altair 풍선 id 가 설치된 프런트 묶음에 그대로 있다. 판올림으로 바뀌면 화면은 멀쩡한 채
  지연만 조용히 풀리므로 여기서 걸린다.

브라우저에서 종류마다 0.9초에는 안 보이고 1.1초 뒤 보이는지는 사본 앱으로 잰다(갈래 기록).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import streamlit
from js_runner import run_js_json

from capa_simulation.components import tip_delay
from capa_simulation.components.app_header import SHELL_STYLE
from capa_simulation.components.process_picker import tile_tooltip_style

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = PROJECT_ROOT / "src" / "capa_simulation" / "components"
BUNDLE = Path(streamlit.__file__).parent / "static" / "static" / "js"
DELAY = tip_delay.TIP_DELAY_MS


def _bundle_text(prefix: str) -> str:
    found = sorted(BUNDLE.glob(f"{prefix}.*.js"))
    assert found, (
        f"설치된 Streamlit 프런트 묶음에 {prefix}.*.js 가 없다 — 판올림으로 이름이 바뀌었나"
    )
    return "\n".join(path.read_text("utf-8") for path in found)


def _all_bundles() -> list[str]:
    return [path.read_text("utf-8") for path in BUNDLE.glob("*.js")]


def _media_block(css: str, media: str) -> str:
    blocks = re.findall(rf"@media {media} \{{(?:[^{{}}]*\{{[^{{}}]*\}})*[^{{}}]*\}}", css)
    assert len(blocks) == 1, blocks
    return str(blocks[0])


def test_the_delay_is_one_second_and_lives_in_one_custom_property() -> None:
    """사용자가 정한 값은 1초다(「마우스 올리고 1초 지나면 뜨도록해」). 값은 `:root` 사용자 정의
    속성 하나라 그림자 DOM 부품도 상속으로 같은 값을 읽는다."""
    assert DELAY == 1000
    assert tip_delay.TIP_DELAY_VARIABLE == "--capa-tip-delay"
    assert tip_delay.TIP_ROOT_CSS.startswith(f":root {{\n  --capa-tip-delay: {DELAY}ms;\n}}\n")


def test_the_keyframes_hide_the_waiting_tip_with_visibility_too() -> None:
    """기다리는 동안 투명도만 0 이면 상자가 「보임」 이라 화면 확인
    스크립트(`check_deploy_screens.py` 의 「풍선 0」 셈 — Playwright `visible=true`)와 읽기 도구가
    센다. 그래서 `visibility` 를 함께 바꾼다."""
    keyframes = tip_delay.TIP_ROOT_CSS[tip_delay.TIP_ROOT_CSS.index("@keyframes") :]
    assert keyframes.startswith(f"@keyframes {tip_delay.TIP_KEYFRAMES} {{")
    start = re.search(r"from \{([^{}]*)\}", keyframes)
    end = re.search(r"to \{([^{}]*)\}", keyframes)
    assert start is not None and end is not None
    assert {line.strip() for line in start.group(1).split(";") if line.strip()} == {
        "opacity: 0",
        "visibility: hidden",
    }
    assert {line.strip() for line in end.group(1).split(";") if line.strip()} == {
        "opacity: 1",
        "visibility: visible",
    }


def test_the_shell_style_carries_the_value_first_and_the_rules_only_on_screen() -> None:
    """값 · 애니메이션은 `@media` 밖 맨 앞 한 벌이고(그림자 뿌리도 물려받는다), 거는 규칙은 화면
    덩어리 끝에만 있다 — 인쇄에는 풍선이 없다."""
    css = SHELL_STYLE.removeprefix("<style>").removesuffix("</style>")
    assert css.lstrip("\n").startswith(tip_delay.TIP_ROOT_CSS)
    assert css.count(tip_delay.TIP_ROOT_CSS) == 1
    screen = _media_block(css, "screen")
    printed = _media_block(css, "print")
    assert tip_delay.TIP_SCREEN_CSS in screen
    assert screen.rstrip().endswith(tip_delay.TIP_SCREEN_CSS.rstrip() + "\n}")
    assert tip_delay.TIP_KEYFRAMES not in printed
    assert tip_delay.TIP_DELAY_VARIABLE not in printed


def _rules() -> dict[str, str]:
    return {selectors: body for selectors, body in tip_delay.TIP_SCREEN_RULES}


def test_streamlit_tips_wait_only_the_rest_after_their_own_open_delay() -> None:
    """Streamlit 도움말 풍선은 JS 가 200ms 뒤 글 상자를 세우고, 표 칸 풍선은 600ms 뒤 세운다. 상자에
    건 애니메이션은 그 나머지(800 · 400ms)만 기다려 처음 뜨기까지 1초다. emotion 이 단 자기
    애니메이션을 덮어야 해서 `!important` 다."""
    rules = _rules()
    help_selectors = ",\n  ".join(tip_delay.STREAMLIT_TIP_SELECTORS)
    assert rules[help_selectors] == (
        f"animation: {tip_delay.TIP_KEYFRAMES} {tip_delay.TIP_FADE_MS}ms ease-in "
        f"calc(var(--capa-tip-delay) - {tip_delay.STREAMLIT_TIP_OPEN_MS}ms) both !important;"
    )
    assert rules[tip_delay.TABLE_TIP_SELECTOR] == (
        f"animation: {tip_delay.TIP_KEYFRAMES} {tip_delay.TIP_FADE_MS}ms ease-in "
        f"calc(var(--capa-tip-delay) - {tip_delay.STREAMLIT_TABLE_TIP_OPEN_MS}ms) both !important;"
    )
    assert tip_delay.STREAMLIT_TIP_OPEN_MS < DELAY
    assert tip_delay.STREAMLIT_TABLE_TIP_OPEN_MS < DELAY


def test_chart_value_tips_wait_only_while_the_chart_is_cold() -> None:
    """그림 값 풍선(Plotly 점 · 칸 · 「x unified」 상자 · 축 꼬리표, Altair)은 문서 뿌리에 웜업
    표지가 없을 때만 1초를 기다린다 — 그림 안에서 옮기면 곧바로 따라간다. 그림 막대 단추 이름은 단추
    풍선이라 늘 기다린다."""
    rules = _rules()
    chart = ",\n  ".join(
        f":root:not([{tip_delay.CHART_WARM_ATTRIBUTE}]) {selector}"
        for selector in tip_delay.CHART_TIP_SELECTORS
    )
    waiting = (
        f"animation: {tip_delay.TIP_KEYFRAMES} {tip_delay.TIP_FADE_MS}ms ease-in "
        "var(--capa-tip-delay) both;"
    )
    assert rules[chart] == waiting
    assert rules[",\n  ".join(tip_delay.MODEBAR_TIP_SELECTORS)] == waiting
    assert tip_delay.CHART_TIP_SELECTORS == (
        ".js-plotly-plot .hoverlayer > .hovertext",
        ".js-plotly-plot .hoverlayer > .legend",
        ".js-plotly-plot .hoverlayer > .axistext",
        "#vg-tooltip-element.visible",
    )
    assert len(rules) == 4


def test_the_installed_streamlit_still_names_and_times_its_tips_as_we_lean_on() -> None:
    """도움말 풍선 글 상자(보통 · 오류)의 `data-testid` 와 여는 지연 기본값 200ms, 표 칸 풍선 글
    상자와 600ms 타이머, Altair 그림 칸 `data-testid` 가 설치된 1.63 묶음에 그대로 있다."""
    tooltip = _bundle_text("Tooltip")
    for selector in tip_delay.STREAMLIT_TIP_SELECTORS:
        testid = re.fullmatch(r'\[data-testid="(\w+)"\]', selector)
        assert testid is not None
        assert re.search(rf'"data-testid":[^,]*`{testid.group(1)}`', tooltip), selector
    assert re.search(
        rf"delay:[\w$]+\?\?{tip_delay.STREAMLIT_TIP_OPEN_MS},closeDelay:[\w$]+\?\?300", tooltip
    )
    table = _bundle_text("DataFrame")
    assert "`stDataFrameTooltipContent`" in table
    assert re.search(rf"\}},{tip_delay.STREAMLIT_TABLE_TIP_OPEN_MS},\{{autoStart:!1\}}\)", table), (
        "표 칸 풍선의 JS 지연 600ms 타이머가 보이지 않는다"
    )
    assert any("`stVegaLiteChart`" in text for text in _all_bundles())


def test_the_installed_plotly_and_vega_still_name_their_tip_boxes_as_we_lean_on() -> None:
    """Plotly 는 풍선을 `hoverlayer` 아래 `g.hovertext` · `g.legend`(「x unified」) · `g.axistext`
    로 세우고, 그림 막대 단추 이름은 `[data-title]:hover` 가상요소다. Altair(vega-tooltip)는 문서에
    하나뿐인 `#vg-tooltip-element` 에 `visible` 을 붙인다."""
    plotly = _bundle_text("PlotlyChart")
    assert "_hoverlayer" in plotly
    assert "selectAll(`g.hovertext`)" in plotly
    assert "select(`g.legend`)" in plotly
    assert "selectAll(`g.axistext`)" in plotly
    assert (
        '"X [data-title]:hover:before,X [data-title]:hover:after":`display:block;opacity:1;`'
        in (plotly)
    )
    assert any("vg-tooltip-element" in text for text in _all_bundles())


# 부품마다 지연을 읽는 길과 못 읽을 때의 기본값(같은 1초).
_COMPONENT_DEFAULTS = (
    ("grid_shared_assets/cells.css", (f"var(--capa-tip-delay, {DELAY}ms)",)),
    (
        "paste_window_assets/paste_window.css",
        (f"animation: capa-tip-in 120ms ease-in var(--capa-tip-delay, {DELAY}ms) both;",),
    ),
    (
        "edit_grid_assets/eg_core.js",
        (f"const EG_TIP_MS = {DELAY}\n", "const EG_TIP_VARIABLE = '--capa-tip-delay'"),
    ),
    (
        "space_layout_editor_assets/editor.js",
        (f"const TIP_DELAY_MS = {DELAY}\n", "getPropertyValue('--capa-tip-delay')"),
    ),
    (
        "date_panel_assets/date_panel.js",
        (f"const TIP_DELAY_MS = {DELAY}\n", "getPropertyValue('--capa-tip-delay')"),
    ),
    (
        "intro_overlay_assets/intro.js",
        (f"const TIP_DELAY_MS = {DELAY};\n", 'getPropertyValue("--capa-tip-delay")'),
    ),
)


@pytest.mark.parametrize(
    ("relative", "needles"), _COMPONENT_DEFAULTS, ids=[row[0] for row in _COMPONENT_DEFAULTS]
)
def test_each_own_tip_reads_the_app_delay_and_falls_back_to_the_same_second(
    relative: str, needles: tuple[str, ...]
) -> None:
    """그림자 DOM · 자체 풍선 부품은 같은 사용자 정의 속성을 읽고, 껍데기 스타일이 아직 없을 때의
    기본값도 `TIP_DELAY_MS` 와 같다 — 값을 바꾸면 여기서 함께 걸린다."""
    text = (COMPONENTS / relative).read_text(encoding="utf-8")
    for needle in needles:
        assert needle in text, (relative, needle)


def test_the_paste_window_tip_uses_the_shell_keyframes_name() -> None:
    """붙여넣기 창은 그림자 DOM 밖(`isolate_styles=False`)이라 껍데기 스타일의 애니메이션을 그대로
    쓴다 — 창 서식에 제 키프레임을 두지 않는다(서식은 창 이름 아래만 — `test_paste_form`)."""
    text = (COMPONENTS / "paste_window_assets" / "paste_window.css").read_text(encoding="utf-8")
    assert f"animation: {tip_delay.TIP_KEYFRAMES} " in text
    assert "@keyframes" not in text


def test_the_home_process_tile_tip_waits_the_app_delay_and_hides_while_waiting() -> None:
    """HOME 공정 필터 팝업의 공정 단추 풍선(st.html 서식 — 그림자 DOM 밖)도 같은 값을 읽고, 기다리는
    동안 `visibility` 로 숨는다."""
    css = tile_tooltip_style(["데모 공정 A"])
    assert f"ease-out var(--capa-tip-delay, {DELAY}ms) both;" in css
    assert "from { opacity: 0; visibility: hidden; }" in css
    assert "to { opacity: 1; visibility: visible; }" in css


def test_the_equipment_master_tip_waits_on_hover_and_shows_at_once_on_keyboard_focus() -> None:
    """설비 마스터 · 시나리오 목록의 꺼진 단추 까닭 풍선(그림자 DOM `cells.css`)은 마우스로 올리면
    앱 전체 지연 뒤에, 키보드 초점(`:focus-visible`)이면 곧바로 뜬다."""
    css = (COMPONENTS / "grid_shared_assets" / "cells.css").read_text(encoding="utf-8")
    hover = re.search(r"\.emg-tip-host:hover > \.emg-tip \{([^{}]*)\}", css)
    focus = re.search(
        r"\.emg-tip-host:focus-visible > \.emg-tip,\s*"
        r"\.emg-btn:focus-visible \+ \.emg-tip \{([^{}]*)\}",
        css,
    )
    assert hover is not None and focus is not None
    assert "visibility: visible;" in hover.group(1)
    assert f"transition: visibility 0s linear var(--capa-tip-delay, {DELAY}ms);" in hover.group(1)
    assert "visibility: visible;" in focus.group(1) and "transition: none;" in focus.group(1)
    assert css.index(hover.group(0)) < css.index(focus.group(0))


def _date_help_block() -> str:
    text = (COMPONENTS / "date_panel_assets" / "date_panel.js").read_text(encoding="utf-8")
    start = text.index("  if (helpButton) {")
    return text[start : text.index("\n  }\n", start)]


def test_the_date_help_waits_on_hover_and_opens_at_once_on_press_or_focus() -> None:
    """날짜 칸 도움말 풍선은 마우스를 올려 둔 뒤 앱 전체 지연이 지나야 뜨고, 누름 · 키보드 초점은
    곧바로다. 기다림은 단추에 달아 판을 다시 세운 회차의 처리기도 앞 기다림을 걷는다."""
    block = _date_help_block()
    assert "helpButton.capaTipWait = setTimeout(show, tipDelayMs(helpButton))" in block
    assert "helpButton.onfocus = show\n" in block
    assert "helpButton.onpointerleave = hide\n" in block
    assert block.count("stopWaiting()") >= 3


_WARM_RUNNER = r"""
const listeners = {}
const attrs = new Set()
let property = ' 1000ms'
const root = {
  setAttribute(name) { attrs.add(name) },
  removeAttribute(name) { attrs.delete(name) },
  hasAttribute(name) { return attrs.has(name) },
}
const doc = {
  documentElement: root,
  addEventListener(type, fn) { listeners[type] = fn },
  removeEventListener(type, fn) { if (listeners[type] === fn) delete listeners[type] },
}
const timers = []
let now = 0
const parentWindow = {
  document: doc,
  setTimeout(run, ms) { timers.push({ run, at: now + ms }); return timers.length },
  clearTimeout(id) { if (id) timers[id - 1] = null },
  getComputedStyle() { return { getPropertyValue: () => property } },
}
globalThis.window = { parent: parentWindow }
const advance = (ms) => {
  now += ms
  timers.forEach((timer, index) => {
    if (timer && timer.at <= now) { timers[index] = null; timer.run() }
  })
}
// 그림 — 칸 key(`st-key-…`)가 같으면 같은 위젯을 다시 세운 그림이다(없으면 key 없는 칸).
const chart = (name, key) => ({
  isConnected: true,
  name,
  closest: () => ({ className: 'stElementContainer' + (key ? ' st-key-' + key : '') }),
})
const chartA = chart('A', 'a')
const chartB = chart('B', 'b')
const inside = (chart) => ({ closest: () => chart })
let step = 0
const over = (chart, pointerType, at) => listeners.pointerover({
  target: inside(chart), pointerType: pointerType || 'mouse',
  clientX: at ? at[0] : (step += 1), clientY: at ? at[1] : 0,
})
const warm = () => attrs.has(ATTRIBUTE)
const out = {}

eval(SCRIPT)
out.listening = Object.keys(listeners).sort()
over(chartA)
advance(999)
out.coldAt999 = warm()
advance(1)
out.warmAt1000 = warm()
over(chartA)
advance(5000)
out.stillWarmInside = warm()
over(null)
out.coolOutside = warm()
over(chartA)
advance(500)
over(chartB)
advance(600)
out.otherChartRestarts = warm()
advance(400)
out.otherChartWarm = warm()
listeners.pointerout({ relatedTarget: null, pointerType: 'mouse' })
out.leftWindow = warm()
over(chartA, 'touch')
out.touchAtOnce = warm()
listeners.pointerout({ relatedTarget: null, pointerType: 'touch' })
out.touchLiftKeeps = warm()
over(null)
property = '1.5s'
over(chartB)
advance(1499)
out.secondsEarly = warm()
advance(1)
out.secondsLate = warm()
over(null)
property = 'garbage'
over(chartA)
advance(999)
out.fallbackEarly = warm()
advance(1)
out.fallbackLate = warm()
over(null)
over(chartA)
chartA.isConnected = false
advance(1000)
out.goneStaysCold = warm()
chartA.isConnected = true
over(chartB)
advance(1000)
// 데워진 그림이 다시 그려지면(칸 key 가 같은 새 그림) 웜업을 잇는다.
const chartB2 = chart('B2', 'b')
chartB.isConnected = false
over(chartB2)
out.replacedKeepsWarm = warm()
over(chartB2)
advance(5000)
out.replacedStillWarm = warm()
// 데우기 전에 빠진 그림은 잇지 않는다 — 새 그림에서 다시 기다린다.
over(null)
const chartC = chart('C', 'c')
const chartC2 = chart('C2', 'c')
over(chartC)
advance(500)
chartC.isConnected = false
over(chartC2)
advance(999)
out.coldReplacedWaits = warm()
advance(1)
out.coldReplacedWarm = warm()
over(chartB2)
advance(1000)
// 마우스는 그대로인데 밑의 그림이 다시 서는 동안 빈 칸이 닿아도(앱 회차) 웜업을 잇는다.
const chartB3 = chart('B3', 'b')
over(chartB2, 'mouse', [500, 500])
chartB2.isConnected = false
over(null, 'mouse', [500, 500])
out.stillPlaceholderKeepsWarm = warm()
over(chartB3, 'mouse', [500, 500])
out.stillNewChartKeepsWarm = warm()
over(chartB3, 'mouse', [510, 500])
advance(3000)
out.movingInNewChartWarm = warm()
over(null, 'mouse', [900, 900])
out.movedOutCools = warm()
// 식은 채로 멈춘 마우스 밑에 그림이 서면 처음처럼 기다린다.
over(chartB3, 'mouse', [900, 900])
advance(999)
out.stillColdWaits = warm()
advance(1)
out.stillColdWarm = warm()
// 굴림으로 멈춘 마우스 밑에 다른 그림(key 다름)이 오면 처음처럼 기다린다.
const chartD = chart('D', 'd')
over(chartD, 'mouse', [300, 300])
advance(1000)
const chartE = chart('E', 'e')
over(chartE, 'mouse', [300, 300])
out.scrolledOtherWaits = warm()
advance(1000)
out.scrolledOtherWarm = warm()
// 그림을 눌러 다른 화면으로 옮긴 뒤(옛 그림 빠짐) 빈 칸을 지나 닿은 다른 그림도 기다린다.
const chartF = chart('F', 'f')
over(chartF, 'mouse', [200, 200])
advance(1000)
chartF.isConnected = false
over(null, 'mouse', [200, 200])
out.navigatedHold = warm()
const chartG = chart('G', 'g')
over(chartG, 'mouse', [260, 210])
out.navigatedOtherWaits = warm()
advance(1000)
// key 없는 그림은 다시 세워도 같은 그림인지 모르므로 기다린다.
over(null)
const chartU = chart('U', '')
over(chartU)
advance(1000)
chartU.isConnected = false
over(chart('U2', ''))
out.unkeyedWaits = warm()
advance(1000)
out.unkeyedWarm = warm()
const before = listeners.pointerover
eval(SCRIPT)
out.rerunReplaced = listeners.pointerover !== before && Object.keys(listeners).length === 2
out.rerunCools = warm()
process.stdout.write(JSON.stringify(out))
"""


def test_the_chart_warmup_waits_once_per_chart_and_cools_when_the_pointer_leaves() -> None:
    """그림 웜업 스크립트(테마 iframe 이 부모 문서에 거는 처리기)를 가짜 문서로 돌린다. 그림에
    들어온 뒤 지연이 지나야 표지를 달고, 그 그림 안에서는 그대로 두며, 그림 밖 · 다른 그림 · 창
    밖으로 가면 뗀다. 터치는 누른 것이라 곧바로 데운다. 지연은 사용자 정의 속성(`ms` · `s`)을 읽고
    못 읽으면 1초다. 기다리는 동안 그림이 사라지면 데우지 않는다. 데워진 그림이 다시 그려지면(칸을
    눌러 앱이 다시 돎 — 칸 key 가 같은 새 그림, 그 사이 멈춘 마우스 밑에 닿는 빈 칸도 떠난 것이
    아니다) 웜업을 잇고, 데우기 전이면 새 그림에서 다시 기다린다. 굴림 · 화면 옮김으로 밑에 온 다른
    그림(key 다름)과 key 없는 그림은 처음처럼 기다린다. 테마 iframe 이 다시 서면 옛 처리기를 떼고
    표지를 지운다."""
    script = tip_delay.chart_tip_warmup_script()
    runner = (
        f"const SCRIPT = {json.dumps(script)}\n"
        f"const ATTRIBUTE = {json.dumps(tip_delay.CHART_WARM_ATTRIBUTE)}\n" + _WARM_RUNNER
    )
    out = run_js_json(runner, what="그림 풍선 웜업 스크립트")
    assert out["listening"] == ["pointerout", "pointerover"]
    assert out["coldAt999"] is False and out["warmAt1000"] is True
    assert out["stillWarmInside"] is True
    assert out["coolOutside"] is False
    assert out["otherChartRestarts"] is False and out["otherChartWarm"] is True
    assert out["leftWindow"] is False
    assert out["touchAtOnce"] is True and out["touchLiftKeeps"] is True
    assert out["secondsEarly"] is False and out["secondsLate"] is True
    assert out["fallbackEarly"] is False and out["fallbackLate"] is True
    assert out["goneStaysCold"] is False
    assert out["replacedKeepsWarm"] is True and out["replacedStillWarm"] is True
    assert out["coldReplacedWaits"] is False and out["coldReplacedWarm"] is True
    assert out["stillPlaceholderKeepsWarm"] is True and out["stillNewChartKeepsWarm"] is True
    assert out["movingInNewChartWarm"] is True and out["movedOutCools"] is False
    assert out["stillColdWaits"] is False and out["stillColdWarm"] is True
    assert out["scrolledOtherWaits"] is False and out["scrolledOtherWarm"] is True
    assert out["navigatedHold"] is True and out["navigatedOtherWaits"] is False
    assert out["unkeyedWaits"] is False and out["unkeyedWarm"] is True
    assert out["rerunReplaced"] is True and out["rerunCools"] is False


def test_the_warmup_script_is_a_fixed_string_on_the_theme_toolbar() -> None:
    """스크립트는 고정 문자열이라 회차마다 같은 글이 가고(테마 iframe 이 다시 서지 않는다), `app.py`
    가 툴바 스크립트에 싣는다."""
    assert tip_delay.chart_tip_warmup_script() == tip_delay.chart_tip_warmup_script()
    app = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "chart_tip_warmup_script()," in app
    script = tip_delay.chart_tip_warmup_script()
    assert json.dumps(tip_delay.CHART_SELECTOR) in script
    assert f"parentWindow.{tip_delay.HANDLER_NAME}" in script


_INTRO_RUNNER = r"""
const TIP_DELAY_MS = 1000
const handlers = {}
const stage = { addEventListener(type, fn) { handlers[type] = fn } }
const host = {}
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' })
globalThis.window = { innerWidth: 1600, innerHeight: 1000 }
const tip = { style: { opacity: '0' }, offsetWidth: 120, offsetHeight: 40, innerHTML: '' }
const timers = []
let now = 0
globalThis.setTimeout = (run, ms) => { timers.push({ run, at: now + ms }); return timers.length }
globalThis.clearTimeout = (id) => { if (id) timers[id - 1] = null }
const advance = (ms) => {
  now += ms
  timers.forEach((timer, index) => {
    if (timer && timer.at <= now) { timers[index] = null; timer.run() }
  })
}
const mode = 'summary'
const summary = {}
// 막대 둘(100 ~ 140 · 160 ~ 200, 위 300 ~ 500)과 점 하나(800, 400).
const hits = [
  { k: 'bar', i: 0, x: 100, y: 300, w: 40, h: 200 },
  { k: 'bar', i: 1, x: 160, y: 300, w: 40, h: 200 },
  { k: 'line', i: 0, x: 800, y: 400, r: 16 },
]
const hitAt = (x, y) => hits.find((h) => (h.k === 'line'
  ? Math.hypot(x - h.x, y - h.y) <= h.r
  : x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h)) || null
const tipHtml = (h) => h.k + h.i
const move = (x, y) => handlers.pointermove({ clientX: x, clientY: y })
const shown = () => tip.style.opacity === '1'
const out = {}
BLOCK
move(120, 400)
advance(999)
out.coldAt999 = shown()
advance(1)
out.warmAt1000 = [shown(), tip.innerHTML]
move(150, 400)
out.gapHides = shown()
move(180, 400)
out.nextBarAtOnce = [shown(), tip.innerHTML]
move(150, 292)
move(180, 400)
out.nearPadStaysWarm = shown()
move(600, 900)
move(120, 400)
out.outsideCools = shown()
advance(1000)
out.rewarmed = shown()
move(800, 400)
out.otherChartWaits = shown()
advance(1000)
out.otherChartWarm = [shown(), tip.innerHTML]
move(120, 400)
advance(300)
move(600, 900)
advance(1000)
move(120, 400)
out.leftWhileWaitingStaysCold = shown()
handlers.pointerleave()
out.leaveHides = shown()
process.stdout.write(JSON.stringify(out))
"""


def test_the_intro_summary_tip_waits_once_per_chart_and_cools_outside_it() -> None:
    """입장 화면 Summary 그림 말풍선(커서를 따라가는 글)도 앱 그림 값 풍선과 같은 웜업이다 —
    그림(맞힌 것의 종류)에 처음 들어오면 앱 전체 지연 뒤에 뜨고, 그 그림 안(칸 사이 빈 곳 포함)에서
    옮기면 곧바로 따라가며, 그 그림을 품는 상자 밖 · 다른 그림 · 무대 밖으로 가면 다시 기다린다.
    처리기 구획을 떼어 가짜 무대로 돌린다."""
    text = (COMPONENTS / "intro_overlay_assets" / "intro.js").read_text(encoding="utf-8")
    start = text.index("  const TIP_CHART_PAD_PX = ")
    end_marker = '  stage.addEventListener("pointerleave", coolTip);'
    block = text[start : text.index(end_marker, start) + len(end_marker)]
    out = run_js_json(_INTRO_RUNNER.replace("BLOCK", block), what="입장 화면 말풍선 웜업")
    assert out["coldAt999"] is False and out["warmAt1000"] == [True, "bar0"]
    assert out["gapHides"] is False
    assert out["nextBarAtOnce"] == [True, "bar1"]
    assert out["nearPadStaysWarm"] is True
    assert out["outsideCools"] is False and out["rewarmed"] is True
    assert out["otherChartWaits"] is False and out["otherChartWarm"] == [True, "line0"]
    assert out["leftWhileWaitingStaysCold"] is False
    assert out["leaveHides"] is False
    assert f"const TIP_DELAY_MS = {DELAY};" in text
