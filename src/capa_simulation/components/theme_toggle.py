# Purpose: 상단 헤더의 Deploy 왼쪽에 밝게/어둡게 전환 버튼을 얹는다.

"""테마 전환 버튼을 Streamlit 헤더 안에 넣는다.

**Streamlit 1.63 에는 앱 안에서 테마를 바꾸는 공개 API 가 없다.** `st.context.theme` 은
읽기 전용이고, 파이썬 쪽에서 우리 토큰만 뒤집으면 Plotly·표만 어두워지고 위젯·사이드바·
알림은 밝은 채로 남는다 — 반쯤 어두운 화면은 안 하느니만 못하다.

그래서 **프론트엔드가 테마를 기억하는 자리**를 그대로 쓴다. Streamlit 은 고른 테마를
`localStorage` 에 `stActiveTheme-<경로>-v2` 로 적고, 값은 `"System"`·`"Light"`·`"Dark"`
셋 중 하나인 JSON 문자열이다. 그 값을 바꾸고 새로고침하면 **Streamlit 크롬과 우리 토큰이
함께** 바뀐다(우리 쪽은 `st.context.theme` 이 새 값을 보고하므로 저절로 따라온다).
브라우저에서 실측으로 확인한 경로다.

버튼이 앉는 자리는 `[data-testid="stToolbarActions"]` 다 — Deploy 버튼 **바로 왼쪽**의
빈 슬롯이고, React 가 툴바를 다시 그려도 주입한 노드가 살아남는 것을 확인했다.

**비공식 경로임을 분명히 해 둔다.** `data-testid` 와 `localStorage` 키 모양은 Streamlit 이
판올림에서 바꿀 수 있다. 바뀌면 버튼이 **안 생길 뿐** 화면은 멀쩡하다 — 그렇게 되도록
스크립트가 슬롯을 못 찾으면 조용히 물러난다. `pyproject.toml` 이 마이너를 못박고 있으므로
올릴 때 이 버튼이 보이는지 확인한다.
"""

from __future__ import annotations

import streamlit as st

# 이 셋이 Streamlit 과 맞춰야 하는 계약 전부다. 한 곳에 모아 두어야 판올림에서 무엇을
# 확인해야 하는지가 분명하다.
_STORAGE_PREFIX = "stActiveTheme-"
_STORAGE_SUFFIX = "-v2"
_TOOLBAR_SLOT = '[data-testid="stToolbarActions"]'
_BUTTON_ID = "capa-theme-toggle"

_SCRIPT = """
<script>
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;
  var KEY = "%(prefix)s" + parentWindow.location.pathname + "%(suffix)s";

  function stored() {
    try { return JSON.parse(parentWindow.localStorage.getItem(KEY) || '"System"'); }
    catch (error) { return "System"; }
  }

  function isDark() {
    var value = stored();
    if (value === "Dark") return true;
    if (value === "Light") return false;
    return parentWindow.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function place() {
    var slot = doc.querySelector('%(slot)s');
    if (!slot) return false;            // 슬롯이 없으면 조용히 물러난다
    if (doc.getElementById("%(id)s")) return true;

    var dark = isDark();
    var button = doc.createElement("button");
    button.id = "%(id)s";
    button.type = "button";
    button.textContent = dark ? "%(to_light)s" : "%(to_dark)s";
    button.title = dark ? "%(tip_light)s" : "%(tip_dark)s";
    button.setAttribute("aria-label", button.title);
    button.style.cssText = [
      "font:inherit", "font-size:13px", "line-height:1", "padding:6px 11px",
      "margin-right:6px", "border:1px solid currentColor", "border-radius:8px",
      "background:transparent", "color:inherit", "opacity:.7", "cursor:pointer",
      "white-space:nowrap"
    ].join(";");
    button.onmouseenter = function () { button.style.opacity = "1"; };
    button.onmouseleave = function () { button.style.opacity = ".7"; };
    button.onclick = function () {
      try {
        parentWindow.localStorage.setItem(KEY, JSON.stringify(dark ? "Light" : "Dark"));
      } catch (error) { return; }
      parentWindow.location.reload();
    };
    slot.appendChild(button);
    return true;
  }

  if (place()) return;
  // 툴바가 아직 안 그려졌을 수 있다. 잠깐만 지켜보고 그만둔다 — 영영 붙어 있으면
  // 화면을 옮겨 다닐 때마다 헛돈다.
  var observer = new parentWindow.MutationObserver(function () {
    if (place()) observer.disconnect();
  });
  observer.observe(doc.body, { childList: true, subtree: true });
  parentWindow.setTimeout(function () { observer.disconnect(); }, 8000);
})();
</script>
"""


def render_theme_toggle() -> None:
    """헤더에 전환 버튼을 얹는다. `app.py` 가 한 번만 부른다.

    높이 0 의 iframe 하나를 쓴다. `st.html` 은 스크립트를 실행하지 않으므로 이 경로가
    아니면 부모 창에 닿을 수 없다. `st.iframe` 은 HTML 문자열을 받으면 **스크립트 실행과
    앱에 대한 동일 출처 접근을 허용**한다고 공식 문서가 적는다 — 그것이 이 버튼이 부모 창의
    `localStorage` 에 닿는 근거다. (`st.components.v1.html` 은 2026-06-01 제거 예정이라
    옮겼다.)
    """
    st.iframe(
        _SCRIPT
        % {
            "prefix": _STORAGE_PREFIX,
            "suffix": _STORAGE_SUFFIX,
            "slot": _TOOLBAR_SLOT,
            "id": _BUTTON_ID,
            "to_light": "Light",
            "to_dark": "Dark",
            "tip_light": "밝은 테마로 바꿉니다",
            "tip_dark": "어두운 테마로 바꿉니다",
        },
        # `st.iframe` 은 0 을 받지 않는다(양수·`stretch`·`content` 만). `content` 로 두면
        # srcdoc 문서의 기본 body margin 까지 재어 눈에 띄는 틈이 생기므로 1px 로 못박는다.
        height=1,
    )
