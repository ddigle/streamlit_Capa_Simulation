# Purpose: 헤더 테마 버튼 바로 오른쪽에 화면을 인쇄하는 Print 버튼을 얹는 툴바 스크립트를 만든다.

"""툴바 `Print` 버튼.

Streamlit 의 ⋮ 메뉴는 감춘다(2026-10-05 사용자 결정 — `app_header.py` 의 전역 규칙). 메뉴에
있던 것 중 사용자에게 남길 것은 **인쇄**와 **테마** 둘이고, 테마는 툴바 Light/Dark 버튼이 이미
맡는다. 그래서 인쇄만 툴바 단추로 새로 세운다. 최소 모드(`client.toolbarMode = "minimal"`)로는
메뉴가 사라지지 않는다 — Streamlit 1.63 은 최소 모드에서도 테마 항목을 남겨 메뉴가 비지 않는다.

**동작은 Streamlit 메뉴의 Print 와 같다.** 그 콜백은 스크립트가 도는 중이면 500ms 뒤에 다시
보고, 멈춰 있을 때 앱 창의 `print()` 를 부른다 — 반쯤 그려진 화면을 찍지 않기 위해서다. 여기서는
실행 상태를 `.stApp` 의 `data-test-script-state` 로 읽고, 도는 중(`running`·`rerunRequested`·
`stopRequested`)일 때만 기다린다. Streamlit 은 `notRunning` 이 아니면 모두 기다려 컴파일 오류
상태(`compilationError`)에서는 끝없이 기다리는데, 여기서는 그때도 지금 화면을 인쇄한다. 인쇄 모양은
Streamlit 의 인쇄용 CSS 가 정한다(헤더·사이드바 접기 버튼 등을 감춘다).

**어두운 테마에서는 먼저 묻는다**(2026-10-06 사용자 결정). 인쇄는 화면 색 그대로라 검은 바탕까지
찍힌다. 테마 버튼이 저장하지 않은 편집을 묻는 것과 같은 네이티브 `confirm` 으로 묻고, 확인이면 위
기다림을 거쳐 인쇄하고 취소면 아무것도 하지 않는다. 밝은 테마는 묻지 않는다. 테마는 단추를
세울 때 같은 키 규칙(`capaTheme.resolve`)으로 읽어 단추 색과 함께 쓴다 — 테마 버튼 글자와 같은
값이다. 누르는 순간 다시 읽지 않는 것은, 다른 탭에서 테마를 바꾸면 저장소 값만 바뀌고 이 탭은
새로 읽기 전까지 옛 테마로 그려져 있기 때문이다(인쇄되는 것은 이 탭의 화면이다). 이 탭의 테마는
새로 읽기로만 바뀌고, 그때 단추도 다시 선다. 브라우저 인쇄(Ctrl+P)는 가로채지 않는다.

다른 툴바 단추처럼 테마 버튼 iframe 에 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`). 모양은 Guide 와 같은 윤곽 단추이고, 색은 같은 키 규칙(`capaTheme`)으로 고른다 —
iframe 내용은 회차마다 같아야 하므로 지금 테마의 토큰을 싣지 않고 두 테마 값을 모두 싣는다.

**비공식 경로다.** 툴바 슬롯과 `data-test-script-state` 는 판올림에서 바뀔 수 있다. 슬롯이
바뀌면 버튼이 안 생길 뿐이고, 실행 상태 표지가 없어지면 기다리지 않고 바로 인쇄한다.
"""

from __future__ import annotations

from capa_simulation.components.theme_toggle import THEME_BUTTON_ID, TOOLBAR_SLOT
from capa_simulation.design import tokens

BUTTON_ID = "capa-print-button"
# 어두운 테마에서 Print 를 누르면 먼저 묻는 말. 스크립트의 JS 문자열에 그대로 들어가므로 큰따옴표·
# 역슬래시·줄바꿈을 넣지 않는다.
DARK_PRINT_CONFIRM = (
    "어두운 테마로 인쇄합니다. 밝은 테마(Light)로 바꾼 뒤 인쇄하면 잉크가 덜 듭니다. "
    "그대로 인쇄할까요?"
)
# 인쇄를 미루는 실행 상태 표지. Streamlit 이 `.stApp` 에 단다.
_RUN_STATE_SELECTOR = ".stApp[data-test-script-state]"

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;

  // 테마는 테마 버튼과 같은 키 규칙(같은 iframe 맨 앞의 `capaTheme`)으로 읽는다.
  function dark() {
    return typeof capaTheme !== "undefined" && capaTheme.resolve(parentWindow).choice === "Dark";
  }

  // 스크립트가 도는 동안은 500ms 마다 다시 본다 — Streamlit 메뉴의 Print 와 같은 규칙이다.
  // 기다리는 중에 다시 눌러도 기다림을 하나 더 걸지 않는다.
  var waiting = false;
  function printWhenIdle() {
    var app = doc.querySelector('%(run_state)s');
    var state = app ? app.getAttribute("data-test-script-state") : "notRunning";
    if (state === "running" || state === "rerunRequested" || state === "stopRequested") {
      waiting = true;
      parentWindow.setTimeout(printWhenIdle, 500);
      return;
    }
    waiting = false;
    try { parentWindow.print(); } catch (error) { /* 인쇄를 막은 브라우저면 아무 일도 없다 */ }
  }

  function place() {
    var slot = doc.querySelector('%(slot)s');
    if (!slot) return false;
    if (doc.getElementById("%(id)s")) return true;
    // 테마 버튼 **바로 오른쪽**에 선다. 테마 버튼이 서기 전이면 기다린다 — 먼저 서면 뒤에 오는
    // 테마 버튼이 슬롯 끝에 붙어 차례가 뒤집힌다.
    var theme = doc.getElementById("%(theme)s");
    if (!theme) return false;
    var isDark = dark();
    var button = doc.createElement("button");
    button.id = "%(id)s";
    button.type = "button";
    button.textContent = "Print";
    button.title = "%(title)s";
    button.setAttribute("aria-label", "%(label)s");
    // Guide 와 같은 윤곽 단추(13px/600 · 모서리 8px · 높이 27px).
    button.style.cssText = [
      "font:inherit", "font-size:13px", "font-weight:600", "line-height:1",
      "padding:6px 12px", "margin-right:6px", "border-radius:8px", "cursor:pointer",
      "white-space:nowrap", "background:transparent",
      "border:1px solid " + (isDark ? "%(dark_border)s" : "%(light_border)s"),
      "color:" + (isDark ? "%(dark_ink)s" : "%(light_ink)s")
    ].join(";");
    button.onclick = function () {
      if (waiting) return;
      // 어두운 테마는 `print-color-adjust: exact` 로 검은 바탕까지 찍혀 잉크가 많이 든다. 먼저
      // 묻고, 취소하면 아무것도 하지 않는다(2026-10-06 사용자 결정). 테마는 단추를 세울 때
      // 읽은 값(`isDark` — 테마 버튼 글자와 같은 값)이다. 누르는 순간 저장소를 다시 읽으면
      // 다른 탭에서 바꾼 테마를 이 탭 화면의 테마로 착각한다. 밝은 테마는 묻지 않고 바로
      // 인쇄한다. Ctrl+P 는 가로채지 않는다.
      if (isDark && !parentWindow.confirm("%(dark_confirm)s")) return;
      printWhenIdle();
    };
    slot.insertBefore(button, theme.nextSibling);
    return true;
  }

  if (place()) return;
  var observer = new parentWindow.MutationObserver(function () {
    if (place()) observer.disconnect();
  });
  observer.observe(doc.body, { childList: true, subtree: true });
  parentWindow.setTimeout(function () { observer.disconnect(); }, 8000);
})();
"""


def print_toolbar_script() -> str:
    """툴바에 `Print` 버튼을 얹는 스크립트. 테마 버튼 iframe 에 Guide·Summary 와 함께 싣는다."""
    return _SCRIPT % {
        "id": BUTTON_ID,
        "label": "인쇄",
        "title": "이 화면을 인쇄합니다",
        "run_state": _RUN_STATE_SELECTOR,
        "dark_confirm": DARK_PRINT_CONFIRM,
        "light_border": tokens.palette_value("light", "BORDER"),
        "dark_border": tokens.palette_value("dark", "BORDER"),
        "light_ink": tokens.palette_value("light", "TEXT"),
        "dark_ink": tokens.palette_value("dark", "TEXT"),
        "slot": TOOLBAR_SLOT,
        "theme": THEME_BUTTON_ID,
    }
