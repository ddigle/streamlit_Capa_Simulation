# Purpose: 화면 조작 상자가 바닥 카드에 걸린 채 서면 사이드바를 굴려 보이는 스크립트를 만든다.

"""화면 조작 상자 보이기.

화면 조작 상자(`sidebar_status.PAGE_BOX_PREFIX` — Space 현황 「Space 도면」)는 조회 조건 패널 바로
밑에 서고, 그 화면의 그룹은 늘 펼친 채 열린다(`app.py`). 1283×911 창에서 「실행 관리」 가 펼쳐지면
상자가 y 772 ~ 954 에 서는데 바닥 앱 정보 카드 윗선은 y 865 다 — 「도면」 줄이 카드에 잘리고 그 아래
줄은 카드 밑 · 창 밖이다. 통합인증 카드(세 줄)는 윗선이 y 834 라 「자리」 줄까지 걸린다. 스크롤로
닿고 초점 이동도 카드 위로 올라오지만(`sidebar_style.APP_CREDITS_SCROLL_ROOM`) 처음 그려지는 자리는
그대로 잘린다.

한 화면의 공간 때문에 그룹 접힘 · 상자 차례를 달리하지 않는다(설계 규칙 UI-CON-03 — 길면 사이드바가
굴린다). 그래서 자리는 그대로 두고 **사이드바가 스스로 굴린다.** 회차가 끝났을 때 상자의 줄 수가
달라졌으면(없던 상자가 섰거나 — 화면 진입 — 가정 설비 시나리오로 줄이 늘었거나) 상자가 다 보일
만큼만 굴린다. 줄 수가 그대로인 회차 · 상자 여닫기 · 폭 끌기에서는 움직이지 않아 사용자가 보던
스크롤 자리가 남는다(UI-PRF-03). 카드에 걸리지 않으면 움직이지 않고, 위로는 굴리지 않으며, 접은
사이드바는 건드리지 않는다 — 폭 0 인 칸에서 줄이 접혀 상자가 부풀어 재면 펼칠 때 엉뚱한 자리에 선다.

상자가 서는 회차에는 줄이 차는 동안 칸 높이가 흔들리고(지난 화면 칸이 회차 끝에 걷힌다) 탭 ·
뒤로가기로 그룹이 저절로 펴지는 움직임이 회차보다 늦게 끝난다 — 회차가 끝난 다음 프레임에 재고, 그
뒤 `SETTLE_MS` 간격으로 `SETTLE_LOOKS` 번 더 잰다. **먼저 쓴 스크롤은 사라질 수 있다.** Streamlit 은
펴는 동안 그룹 `details` 에 시작 높이(35px)를 인라인으로 두고 500ms 애니메이션으로 덮는데, 효과가
끝난 프레임에는 `finish` 처리기가 그 값을 지우기 전이라 시작 높이가 되살아난다. 그 한 프레임에
내용이 짧아져 브라우저가 `scrollTop` 을 깎는다(실측 `scrollHeight` 911 — 0 까지도, 다른 그룹이 펴
있으면 65 처럼 중간까지도). 느린 PC 에서는 그 끝이 회차 끝 + 600ms 보다 늦어(CPU 4배 제한 실측 약
630ms) 다시 쓴 값까지 깎이므로 한 번으로 모자란다. 깎임은 값으로는 사람이 굴린 것과 가르지 못한다 —
재기를 멈추는 것은 그 사이 사람이 사이드바에 손을 댄 입력 사건(휠 · 터치 · 스크롤 막대 누름 · 키)
뿐이다.

프런트가 심하게 밀리면 회차 하나가 한 번에 그려져 회차 표지 속성이 아예 바뀌지 않는다(CPU 10배 제한
실측 — 뒤로가기 5번 중 4번). 그래서 그룹이 펴질 때(`details` 의 `open`)도 잰다.

접힌 사이드바에 선 상자는 세지 않는다. 사이드바가 펼쳐지면(`aria-expanded`) 폭이 다 돌아온
`SETTLE_MS` 뒤에 다시 잰다 — 줄 수가 같은 뒤 회차로는 알 수 없고, 움직이는 동안 재면 부푼 상자를
잰다.

테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`) — iframe 내용은 회차마다 같아야 하므로 고정 문자열이고, iframe 이 다시 만들어지면
옛 듣개를 뗀다. 듣개는 회차 표지 · 그룹 펼침 · 사이드바 펼침 속성 바뀜만 본다(칸이 붙고 떨어지는
것은 보지 않는다). 굴림 양 판정은 DOM 을 모르는 순수 구획(`// <page-box-reveal>`)이라 node 시험이
떼어 돌린다(`tests/test_page_box_reveal.py`).

**비공식 경로다.** Streamlit 의 회차 표지(`data-test-script-state`) · `st-key-` 칸 · 사이드바
`data-testid` 에 기댄다. 판올림에서 바뀌면 사이드바가 스스로 굴리지 않을 뿐 화면은 그대로다.
"""

from __future__ import annotations

from capa_simulation.components.app_credits import APP_CREDITS_KEY
from capa_simulation.sidebar_status import PAGE_BOX_PREFIX

# 부모 창에 남기는 지금 듣개의 이름. iframe 이 다시 만들어지면 이것으로 옛 듣개를 뗀다.
HANDLER_NAME = "__capaPageBoxReveal"
# 사람의 입력을 듣는 문서 듣개의 이름. 쓰임은 위와 같다.
INPUT_HANDLER_NAME = "__capaPageBoxRevealInput"
# 상자와 카드 윗선 · 머리칸 사이에 남기는 틈. 사이드바 상자 사이 간격과 비슷한 값이다.
REVEAL_GAP_PX = 8
# 그룹을 펴는 움직임(Streamlit 500ms) · 사이드바가 펼쳐지는 움직임이 끝난 뒤 다시 재는 간격.
SETTLE_MS = 600
# 첫 재기 뒤 다시 재는 횟수. 끝나는 시각이 PC 빠르기에 달려 마지막 재기가 그 뒤에 오도록 둔다.
SETTLE_LOOKS = 3

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;
  var body = doc && doc.body;
  if (!body || typeof doc.querySelector !== "function") return;
  var RUN_STATE = "data-test-script-state";
  var OPENED = "open";
  var EXPANDED = "aria-expanded";
  var INPUTS = ["wheel", "touchmove", "pointerdown", "keydown"];
  var BOX = '[class*="st-key-%(prefix)s"]';
  var CARD = '[data-testid="stLayoutWrapper"]:has(> .st-key-%(card)s)';
  var HEADER = '[data-testid="stSidebarHeader"]';
  var SIDEBAR = '[data-testid="stSidebar"]';
  var SIDE = '[data-testid="stSidebarContent"]';
  var GAP = %(gap)d;
  var SETTLE_MS = %(settle)d;
  var SETTLE_LOOKS = %(looks)d;

  // <page-box-reveal>
  function revealScroll(boxTop, boxBottom, viewTop, viewBottom, gap) {
    if (boxBottom <= viewBottom) return 0;
    return Math.max(0, Math.min(boxBottom + gap - viewBottom, boxTop - viewTop - gap));
  }
  // </page-box-reveal>

  function reveal(box) {
    var side = box.closest(SIDE);
    var sidebar = box.closest(SIDEBAR);
    if (!side || (sidebar && sidebar.getAttribute(EXPANDED) === "false")) return false;
    var card = doc.querySelector(CARD);
    var head = doc.querySelector(HEADER);
    var view = side.getBoundingClientRect();
    var rect = box.getBoundingClientRect();
    side.scrollTop += revealScroll(
      rect.top,
      rect.bottom,
      head ? head.getBoundingClientRect().bottom : view.top,
      card ? card.getBoundingClientRect().top : view.bottom,
      GAP
    );
    return true;
  }

  // 접힌 사이드바에 선 상자는 세지 않아 펼칠 때 다시 잰다.
  var seen = 0;
  var touched = false;

  function settle(box, looks) {
    window.setTimeout(function () {
      if (!box.isConnected || touched) return;
      if (!reveal(box)) seen = 0;
      else if (looks > 1) settle(box, looks - 1);
    }, SETTLE_MS);
  }

  function check() {
    var app = doc.querySelector(".stApp[" + RUN_STATE + "]");
    if (app && app.getAttribute(RUN_STATE) !== "notRunning") return;
    var box = doc.querySelector(BOX);
    var count = box ? box.children.length : 0;
    if (count === seen) return;
    if (box && !reveal(box)) return;
    seen = count;
    if (!box) return;
    touched = false;
    settle(box, SETTLE_LOOKS);
  }

  function nextFrame() {
    parentWindow.requestAnimationFrame(check);
  }

  function onChange(records) {
    for (var index = 0; index < records.length; index += 1) {
      if (records[index].attributeName !== EXPANDED) nextFrame();
      else if (records[index].target.matches(SIDEBAR)) window.setTimeout(nextFrame, SETTLE_MS);
    }
  }

  function onInput(event) {
    var target = event.target;
    if (target && target.closest && target.closest(SIDE)) touched = true;
  }

  var previous = parentWindow.%(handler)s;
  if (previous && typeof previous.disconnect === "function") previous.disconnect();
  var previousInput = parentWindow.%(input_handler)s;
  var observer = new parentWindow.MutationObserver(onChange);
  observer.observe(body, {
    subtree: true,
    attributes: true,
    attributeFilter: [RUN_STATE, OPENED, EXPANDED],
  });
  parentWindow.%(handler)s = observer;
  parentWindow.%(input_handler)s = onInput;
  INPUTS.forEach(function (name) {
    if (previousInput) doc.removeEventListener(name, previousInput, true);
    doc.addEventListener(name, onInput, { capture: true, passive: true });
  });
  nextFrame();
})();
"""


def page_box_reveal_script() -> str:
    """화면 조작 상자를 보이는 스크립트(고정 문자열 — `render_theme_toggle` 의 `extra_scripts`)."""
    return _SCRIPT % {
        "prefix": PAGE_BOX_PREFIX,
        "card": APP_CREDITS_KEY,
        "gap": REVEAL_GAP_PX,
        "settle": SETTLE_MS,
        "looks": SETTLE_LOOKS,
        "handler": HANDLER_NAME,
        "input_handler": INPUT_HANDLER_NAME,
    }
