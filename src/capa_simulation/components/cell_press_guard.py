# Purpose: 화면을 옮기는 HOME 칸 그림의 빠른 둘째 누름을 옮기는 동안 거르는 스크립트를 만든다.

"""HOME 칸 그림의 둘째 누름 거름.

HOME 의 세 월 그림(`Capa LOB 현황`·`주요공정 확보율`·`상세 B/N 공정`)은 프래그먼트
(`home_rendering.render_home_figures`) 안의 칸 선택 위젯이다. 칸을 누르면 그 프래그먼트 회차가 공정
Capa 상세로 옮긴다(`st.switch_page`). 칸을 사람 속도로 더블클릭하면(0.08~0.15초) 둘째 누름이 아직
떠 있는 HOME 그림에 닿아 Plotly 가 선택을 바꾸고(빈 선택·같은 점), Streamlit 프런트가 **HOME
프래그먼트의 회차**를 청한다. 그 요청은 떠나는 화면(HOME) 주소를 싣고 옮긴 화면 회차가 끝난 뒤에
돈다 — 서버는 그 회차에서 화면이 바뀌었다고 새 세션 메시지를 보내고, 프런트는 지금 화면(공정 Capa
상세)과 다른 화면의 회차라 본문을 비운다(1.63 `handleNewSession` 의 `clearAppState`). 그
프래그먼트는 이제 없어(로그 「Couldn't find fragment with id …」) 아무것도 그리지 않아, 탭·주소는
공정 Capa 상세인데 본문이 빈 채 남았다(2026-10-27 E2E — 9번 중 7번).

서버는 그 회차를 거를 자리가 없다 — 프래그먼트 회차에서는 앱 스크립트가 돌지 않는다. 그래서
브라우저에서 막는다. 부모 문서에 캡처 단계 듣개를 달아, 이 그림들 위에서 누름(`mousedown`)을 받으면
그 뒤 `HOLD_MIN_MS` 동안, 그리고 앱 회차가 도는 동안(`stApp` 의 `data-test-script-state` — 옮기는
회차·옮긴 화면 회차) 이 그림들 위의 다음 누름(`pointerdown`·`mousedown`·`dblclick`)을 Plotly 까지
내려보내지 않는다(`stopPropagation`). 첫 누름은 그대로 간다 — 첫 누름의 `mouseup`·`click` 은
건드리지 않는다(Plotly 는 문서의 `mouseup` 으로 클릭을 끝낸다). 기다림은 `HOLD_MAX_MS` 를 넘지
않는다. 판정은 DOM 을 모르는 순수 구획(`// <cell-press-hold>`)이라 node 시험이 떼어
돌린다(`tests/test_cell_press_guard.py`).

옮기지 않는 누름(과거 실적 칸·연간 Total 칸·같은 칸 다시 누름)도 같은 창에 걸린다 — 그 프래그먼트
회차가 끝나면(짧다) 풀린다. 이 그림들은 더블클릭으로 할 일이 없어 잃는 조작이 없다.

테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`). iframe 내용은 회차마다 같아야 하므로 스크립트는 고정 문자열이다. iframe 이 다시
만들어지면 옛 iframe 의 함수는 브라우저가 부르지 않으므로, 창에 남긴 옛 듣개를 떼고 새로
단다(`plotly_touch_scroll` 과 같은 꼴). 그림은 Streamlit 이 key 로 다는 `st-key-<key>` 칸 안의
`.js-plotly-plot` 으로 고른다(같은 선택자 규칙).

**비공식 경로다.** Streamlit 의 회차 표지(`data-test-script-state`)·`st-key-` 칸 이름과 Plotly 의
`mousedown` 처리에 기댄다. 판올림에서 바뀌면 거름이 할 일을 잃을 뿐 화면은 그대로다 — 올릴 때 HOME
칸 더블클릭을 브라우저로 한 번 본다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from capa_simulation.components.plotly_touch_scroll import touch_scroll_selector

# 부모 창에 남기는 지금 듣개의 이름. iframe 이 다시 만들어지면 이것으로 옛 듣개를 뗀다.
HANDLER_NAME = "__capaCellPressGuard"
# 누름 뒤 이만큼은 회차가 서기 전이라도 다음 누름을 거른다 — 클릭이 끝나 선택이 회차 요청이
# 되기까지와 더블클릭 간격(Windows 기본 0.5초)을 덮는다. 탭 줄의 더블클릭 창(`page_tabs.js` 의
# `DOUBLE_PRESS_MS`)과 같다.
HOLD_MIN_MS = 500
# 회차가 끝나지 않아도 이만큼 지나면 거르지 않는다(탭 줄의 `BUSY_MS` 와 같다).
HOLD_MAX_MS = 10_000
# 거르는 누름 사건. 첫 누름을 끝내는 `mouseup`·`click` 은 넣지 않는다.
HELD_EVENTS = ("pointerdown", "mousedown", "dblclick")

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;
  var selector = %(selector)s;
  var events = %(events)s;

// <cell-press-hold>
// 앞 누름(`armedAt`) 뒤에 온 누름을 거르는가 — `minMs` 안이거나 앱 회차가 도는 동안이다. `maxMs`
// 가 지나면 거르지 않는다. 앞 누름이 없으면(`null`) 거르지 않는다.
function pressHeld(armedAt, now, running, minMs, maxMs) {
  if (armedAt === null) return false;
  var elapsed = now - armedAt;
  if (elapsed < 0 || elapsed >= maxMs) return false;
  return elapsed < minMs || running;
}
// </cell-press-hold>

  var armedAt = null;
  function running() {
    var root = doc.querySelector('[data-testid="stApp"]');
    var run = root ? root.getAttribute("data-test-script-state") : null;
    return run === "running" || run === "rerunRequested";
  }
  // 이 그림들 위의 누름만 본다. 걸린 누름은 Plotly 까지 내려보내지 않고, 지나간 `mousedown` 이
  // 창을 연다.
  function guard(event) {
    var target = event.target;
    if (!target || typeof target.closest !== "function" || !target.closest(selector)) return;
    var now = Date.now();
    if (pressHeld(armedAt, now, running(), %(min_ms)d, %(max_ms)d)) {
      event.stopPropagation();
      return;
    }
    if (event.type === "mousedown") armedAt = now;
  }

  var previous = parentWindow.%(handler)s;
  var index;
  if (previous) {
    for (index = 0; index < events.length; index += 1) {
      doc.removeEventListener(events[index], previous, true);
    }
  }
  parentWindow.%(handler)s = guard;
  for (index = 0; index < events.length; index += 1) {
    doc.addEventListener(events[index], guard, true);
  }
})();
"""


def cell_press_guard_script(chart_keys: Sequence[str]) -> str:
    """화면을 옮기는 칸 선택 그림의 빠른 둘째 누름을 거르는 스크립트. 테마 버튼 iframe 에 싣는다."""
    return _SCRIPT % {
        "selector": json.dumps(touch_scroll_selector(chart_keys)),
        "events": json.dumps(list(HELD_EVENTS)),
        "handler": HANDLER_NAME,
        "min_ms": HOLD_MIN_MS,
        "max_ms": HOLD_MAX_MS,
    }
