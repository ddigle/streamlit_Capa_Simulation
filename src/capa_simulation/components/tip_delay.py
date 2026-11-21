# Purpose: 풍선 1초 지연 값 하나와 그 값을 거는 껍데기 CSS 조각 · 그림 웜업 스크립트를 둔다.

"""풍선은 마우스를 1초 올려 둔 뒤에 뜬다(2026-11-21 사용자 결정 — 설계 규칙 UI-NAV-04).

**무엇에 거는가.** 마우스를 올리면 뜨는 풍선 전부다 — Streamlit 도움말 풍선(`help=` · 단추 ·
메트릭 · 오류 풍선 · 요소 툴바), 표 칸 풍선(`st.dataframe` · `st.data_editor`), 그림 값 풍선
(Plotly · Altair), Plotly 그림 막대(modebar) 단추 이름, 우리 부품의 풍선(꺼진 단추 까닭 · 편집
그리드 값 칸 머리 · Space 편집기 · 날짜 칸 도움말 · HOME 공정 필터 공정 단추 · 붙여넣기 창 잠긴 칸 ·
입장 화면 Summary 그림). 누르면 여는 팝업(설정 팝업 · Alarm 판 · 달력)과 오른쪽 아래 알림창은
그대로다. 브라우저 기본 풍선(HTML `title` · SVG `<title>`)은 브라우저가 정해 그대로 둔다.

**그림 값 풍선은 그림에 처음 들어올 때만 기다린다.** 그림 안에서 점 · 칸을 옮기면 곧바로 따라간다 —
Plotly 는 점 · 칸마다 풍선 묶음을 새로 세우므로 CSS 만으로는 시트 · 히트맵 칸마다 1초씩 기다린다.
그래서 문서 `pointerover` 하나가 지금 그림을 기억하고, 그림에 들어온 뒤 1초가 지나면 문서 뿌리에
웜업 표지(`CHART_WARM_ATTRIBUTE`)를 단다. 표지가 있는 동안 그림 값 풍선 규칙이 빠진다. 다른 그림 ·
그림 밖으로 옮기거나 창을 떠나면 표지를 뗀다. 칸을 눌러 앱이 다시 돌며 같은 그림을 새로 세우면(칸
key `st-key-…` 가 같음 — 세우는 동안 멈춘 마우스 밑에 닿는 빈 칸도 떠난 것이 아니다) 웜업을 잇고,
굴림 · 화면 옮김으로 밑에 온 다른 그림은 처음처럼 기다린다. Altair
풍선(`#vg-tooltip-element`)은 그림 밖 `body` 끝에 붙으므로 그림 칸에 단 표지로는 고를 수 없어 문서
뿌리에 단다. 터치로 띄운 풍선은 누른 것이라 곧바로 데운다. 스크립트가 없어도(테마 iframe 이 아직
서지 않은 회차) CSS 가 그림 값 풍선을 1초 늦춘다 — 그때는 점마다 기다릴 뿐이다.

**값은 하나다.** 지연은 껍데기 스타일(`app_header.SHELL_STYLE`)의 `:root` 사용자 정의 속성
`TIP_DELAY_VARIABLE` 하나이고, 그림자 DOM 부품(설비 마스터 · 시나리오 목록 · 편집 그리드 · Space
편집기 · 날짜 칸 · 입장 화면)도 상속으로 같은 값을 읽는다 — 전역 규칙은 그림자 뿌리를 넘지 못하지만
사용자 정의 속성은 물려받는다. 부품마다 그 값을 못 읽을 때의 기본값은 `TIP_DELAY_MS` 와 같은
1초다(시험이 맞댄다). 키보드 초점으로 뜨는 우리 부품 풍선은 곧바로 뜬다. Streamlit 기본 풍선은
마우스와 초점을 가를 길이 없어 초점도 같이 늦는다.

**Streamlit 풍선은 JS 지연 뒤에 CSS 로 덧붙인다.** 1.63 도움말 풍선은 마우스를 올리고 200ms
(`STREAMLIT_TIP_OPEN_MS`) 뒤 글 상자를 세우고, 표 칸 풍선은 600ms(`STREAMLIT_TABLE_TIP_OPEN_MS`) 뒤
세운다 — 파이썬 인자로는 바꿀 수 없다. 글 상자는 닫히면 지워지고 열 때 새로 서므로, 그 상자에
「기다렸다 나타나는」 애니메이션(`TIP_KEYFRAMES`)을 걸어 나머지를 기다린다. 대가는 셋이다 — 한 번 뜬
풍선이 닫히고 0.5초 안에 다른 풍선으로 가면 Streamlit 이 JS 지연을 건너뛰어 0.8초에 뜬다. 이미 1초를
기다리는 요소 툴바(표 · 그림 오른쪽 위 전체화면 등) 풍선은 1.8초가 된다. 0.7 ~ 1.0초 사이에 마우스가
지나가면 닫힘 지연(300ms) 동안 잠깐 비친다.

**`visibility` 를 꼭 함께 바꾼다.** 투명도만 바꾸면 기다리는 동안에도 상자가 「보임」 이라 화면 확인
스크립트(`scripts/check_deploy_screens.py` 의 「풍선 0」 셈)와 읽기 도구가 센다.

**비공식 경로다.** Streamlit 의 `data-testid`(풍선 글 상자 셋) · JS 지연(200 · 600ms)과 Plotly 의
풍선 묶음 이름(`hoverlayer` 아래 `hovertext` · `legend` · `axistext`) · Altair 풍선 id 에 기댄다.
판올림으로 바뀌면 화면은 멀쩡한 채 지연만 조용히 풀리므로 `tests/test_tip_delay.py` 가 설치된 프런트
묶음에서 그 이름 · 값을 찾는다.
"""

from __future__ import annotations

import json
from typing import Final

# 앱 전체 풍선 지연(2026-11-21 사용자 결정 「1초」).
TIP_DELAY_MS: Final = 1000
# 그 값을 싣는 사용자 정의 속성 — 껍데기 스타일 `:root` 에 서고 그림자 DOM 부품이 상속으로 읽는다.
TIP_DELAY_VARIABLE: Final = "--capa-tip-delay"
# 기다린 뒤 나타나는 애니메이션 이름 · 나타나는 데 드는 시간.
TIP_KEYFRAMES: Final = "capa-tip-in"
TIP_FADE_MS: Final = 120
# Streamlit 1.63 이 글 상자를 세우기까지의 JS 지연(도움말 풍선 · 표 칸 풍선 — 프런트 묶음 확인).
STREAMLIT_TIP_OPEN_MS: Final = 200
STREAMLIT_TABLE_TIP_OPEN_MS: Final = 600
# 그림에 들어온 뒤 지연이 지나면 문서 뿌리에 다는 웜업 표지.
CHART_WARM_ATTRIBUTE: Final = "data-capa-chart-warm"
# 웜업을 세는 그림 — Plotly 그림 뿌리 · Altair 그림 칸.
CHART_SELECTOR: Final = '.js-plotly-plot, [data-testid="stVegaLiteChart"]'
# 부모 창에 남기는 지금 듣개 · 상태의 이름. 테마 iframe 이 다시 만들어지면 이것으로 옛 듣개를 뗀다.
HANDLER_NAME: Final = "__capaChartTipWarm"

# Streamlit 도움말 풍선의 글 상자(보통 · 오류). 둘 다 `body` 끝 포털이라 어느 칸 것인지 서식으로
# 고를 수 없어 앱 전체에 건다.
STREAMLIT_TIP_SELECTORS: Final = (
    '[data-testid="stTooltipContent"]',
    '[data-testid="stTooltipErrorContent"]',
)
# Streamlit 표 칸 풍선의 글 상자.
TABLE_TIP_SELECTOR: Final = '[data-testid="stDataFrameTooltipContent"]'
# 그림 값 풍선 — Plotly 풍선 묶음 셋(점 · 칸 풍선 · 「x unified」 상자 · 축 꼬리표)과 Altair 풍선.
CHART_TIP_SELECTORS: Final = (
    ".js-plotly-plot .hoverlayer > .hovertext",
    ".js-plotly-plot .hoverlayer > .legend",
    ".js-plotly-plot .hoverlayer > .axistext",
    "#vg-tooltip-element.visible",
)
# Plotly 그림 막대 단추 이름(가상요소 — `display` 가 바뀌는 자리라 transition 이 아니라 animation).
# 단추 풍선이라 그림 웜업과 상관없이 늘 기다린다.
MODEBAR_TIP_SELECTORS: Final = (
    ".js-plotly-plot .modebar [data-title]:hover::before",
    ".js-plotly-plot .modebar [data-title]:hover::after",
)


def _animation(delay: str, *, important: bool = False) -> str:
    tail = " !important" if important else ""
    return f"animation: {TIP_KEYFRAMES} {TIP_FADE_MS}ms ease-in {delay} both{tail};"


def _after_open(open_ms: int) -> str:
    """Streamlit 이 `open_ms` 를 기다린 뒤 세운 상자가 나머지를 기다리는 지연."""
    return f"calc(var({TIP_DELAY_VARIABLE}) - {open_ms}ms)"


def _warm_gated(selector: str) -> str:
    return f":root:not([{CHART_WARM_ATTRIBUTE}]) {selector}"


# 껍데기 스타일 맨 위(`@media` 밖)에 서는 값과 애니메이션. 부품 CSS 의 `var(..., 1000ms)` 기본값과
# 같은 값이다.
TIP_ROOT_CSS: Final = (
    f":root {{\n  {TIP_DELAY_VARIABLE}: {TIP_DELAY_MS}ms;\n}}\n"
    f"@keyframes {TIP_KEYFRAMES} {{\n"
    "  from {\n    opacity: 0;\n    visibility: hidden;\n  }\n"
    "  to {\n    opacity: 1;\n    visibility: visible;\n  }\n"
    "}\n"
)

# 껍데기 스타일 화면 덩어리(`@media screen`) 안에 서는 규칙 넷 — 고른 것 · 선언 짝.
# - Streamlit 도움말 풍선: JS 200ms 뒤 선 상자가 나머지 800ms 를 기다린다. emotion 이 단 자기
#   애니메이션(`fadeIn 120ms ease-in 50ms`)을 덮어야 해서 `!important` 다.
# - 표 칸 풍선: JS 600ms 뒤 선 상자가 나머지 400ms 를 기다린다.
# - 그림 값 풍선: 웜업 표지가 없을 때만 1초를 기다린다(표지는 그림 웜업 스크립트가 단다).
# - 그림 막대 단추 이름: 늘 1초.
TIP_SCREEN_RULES: Final = (
    (
        ",\n  ".join(STREAMLIT_TIP_SELECTORS),
        _animation(_after_open(STREAMLIT_TIP_OPEN_MS), important=True),
    ),
    (TABLE_TIP_SELECTOR, _animation(_after_open(STREAMLIT_TABLE_TIP_OPEN_MS), important=True)),
    (
        ",\n  ".join(_warm_gated(selector) for selector in CHART_TIP_SELECTORS),
        _animation(f"var({TIP_DELAY_VARIABLE})"),
    ),
    (",\n  ".join(MODEBAR_TIP_SELECTORS), _animation(f"var({TIP_DELAY_VARIABLE})")),
)
TIP_SCREEN_CSS: Final = "".join(
    f"  {selectors} {{\n    {body}\n  }}\n" for selectors, body in TIP_SCREEN_RULES
)

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;
  var root = doc.documentElement;
  var charts = %(charts)s;
  var warm = %(attribute)s;
  var variable = %(variable)s;

// <chart-tip-warm>
// 문서 `pointerover` 가 닿은 그림(`chart` — 그림 밖이면 null)과 지금 그림(`current`)으로 할 일을
// 정한다. 같은 그림이면 그대로, 그림 밖이면 식히고, 새 그림이면 지연 뒤 데운다 — 터치는 누른 것이라
// 곧바로 데운다. 데워져 있을 때(`warmNow`) 칸 key 가 같은 그림(`sameKey` — 칸을 눌러 앱이 다시 돌며
// 같은 그림을 새로 세움)은 웜업을 잇고(`adopt`), 마우스가 그 자리 그대로인데(`still`) 그림 밖이
// 닿은 것(새로 세우는 틈)은 식히지 않는다(`hold`). 다른 그림(굴림 · 화면 옮김으로 밑에 온 그림
// 포함)은 처음처럼 기다린다.
function warmAction(current, chart, pointerType, warmNow, still, sameKey) {
  if (chart === current) return "keep";
  if (warmNow && chart && sameKey) return "adopt";
  if (warmNow && still && !chart) return "hold";
  if (!chart) return "cool";
  return pointerType === "touch" ? "warm" : "arm";
}
// 그림 칸 자신의 key 표지(`st-key-…` — 같은 위젯이면 다시 세워도 같다). 없으면 빈 글이다.
function chartKey(chart) {
  var box = chart && typeof chart.closest === "function"
    ? chart.closest('[data-testid="stElementContainer"]') : null;
  var match = box ? /(?:^|\\s)(st-key-\\S+)/.exec(box.className || "") : null;
  return match ? match[1] : "";
}
// 사용자 정의 속성 글(`1000ms` · `1s`)을 ms 로 읽는다. 못 읽으면 기본값이다.
function tipDelayMs(raw, fallback) {
  var match = /^\\s*(\\d+(?:\\.\\d+)?)(ms|s)\\s*$/.exec(raw || "");
  if (!match) return fallback;
  return Math.round(parseFloat(match[1]) * (match[2] === "s" ? 1000 : 1));
}
// </chart-tip-warm>

  var previous = parentWindow.%(handler)s;
  if (previous) {
    doc.removeEventListener("pointerover", previous.over, true);
    doc.removeEventListener("pointerout", previous.out, true);
    parentWindow.clearTimeout(previous.state.timer);
  }
  root.removeAttribute(warm);
  var state = { current: null, key: "", timer: 0, x: NaN, y: NaN };

  function cool() {
    parentWindow.clearTimeout(state.timer);
    state.timer = 0;
    state.current = null;
    state.key = "";
    root.removeAttribute(warm);
  }
  function over(event) {
    var target = event.target;
    var chart = target && typeof target.closest === "function" ? target.closest(charts) : null;
    var still = event.clientX === state.x && event.clientY === state.y;
    state.x = event.clientX;
    state.y = event.clientY;
    var key = chartKey(chart);
    var sameKey = key !== "" && key === state.key;
    var action = warmAction(
      state.current, chart, event.pointerType, root.hasAttribute(warm), still, sameKey
    );
    if (action === "keep" || action === "hold") return;
    if (action === "adopt") {
      state.current = chart;
      return;
    }
    cool();
    if (action === "cool") return;
    state.current = chart;
    state.key = key;
    if (action === "warm") {
      root.setAttribute(warm, "");
      return;
    }
    var raw = parentWindow.getComputedStyle(root).getPropertyValue(variable);
    var wait = tipDelayMs(raw, %(fallback)d);
    state.timer = parentWindow.setTimeout(function () {
      state.timer = 0;
      if (state.current === chart && chart.isConnected) root.setAttribute(warm, "");
    }, wait);
  }
  // 창 밖으로 나가면 식힌다. 터치를 뗀 것(`pointerout` 이 따라온다)은 떠난 것이 아니다.
  function out(event) {
    if (!event.relatedTarget && event.pointerType !== "touch") cool();
  }

  parentWindow.%(handler)s = { over: over, out: out, state: state };
  doc.addEventListener("pointerover", over, { capture: true, passive: true });
  doc.addEventListener("pointerout", out, { capture: true, passive: true });
})();
"""


def chart_tip_warmup_script() -> str:
    """그림에 처음 들어올 때만 값 풍선을 늦추는 웜업 스크립트. 테마 버튼 iframe 에 싣는다(고정
    문자열)."""
    return _SCRIPT % {
        "charts": json.dumps(CHART_SELECTOR),
        "attribute": json.dumps(CHART_WARM_ATTRIBUTE),
        "variable": json.dumps(TIP_DELAY_VARIABLE),
        "handler": HANDLER_NAME,
        "fallback": TIP_DELAY_MS,
    }
