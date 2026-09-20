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

import streamlit.components.v1 as components

from capa_simulation.design import tokens
from capa_simulation.design.theme import THEME_QUERY_PARAM

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

  // 주소의 조회 인자를 고친다. **`location.replace` 를 쓰지 않는다** — 이 iframe 의
  // 샌드박스에 `allow-top-navigation` 이 없어서 다른 주소로 옮기는 것은 조용히 막힌다.
  // 버튼이 아무 반응도 없던 이유가 그것이다. `history.replaceState` 는 이동이 아니라
  // 주소만 고쳐 쓰는 것이라 같은 출처면 허용되고, 그다음 `reload()` 는 같은 주소를
  // 다시 읽는 것이라 통한다.
  function syncParam(mode) {
    try {
      var url = new parentWindow.URL(parentWindow.location.href);
      if (url.searchParams.get("%(param)s") === mode) return false;
      url.searchParams.set("%(param)s", mode);
      parentWindow.history.replaceState(null, "", url.toString());
      return true;
    } catch (error) { return false; }
  }

  function paint(button, dark) {
    // 버튼이 **가려는 쪽**의 옷을 입는다. 밝은 테마에서는 `Dark` 가 검은 알약에 흰 글자,
    // 어두운 테마에서는 `Light` 가 흰 알약에 검은 글자다. 서로 반대라 어느 쪽에서도
    // 배경과 붙지 않는다.
    var fill = dark ? "%(dark_fill)s" : "%(light_fill)s";
    var ink = dark ? "%(dark_ink)s" : "%(light_ink)s";
    button.style.cssText = [
      "font:inherit", "font-size:13px", "font-weight:600", "line-height:1",
      "padding:6px 12px", "margin-right:6px", "border:1px solid " + fill,
      "border-radius:8px", "background:" + fill, "color:" + ink,
      "opacity:.92", "cursor:pointer", "white-space:nowrap"
    ].join(";");
  }

  function place() {
    var slot = doc.querySelector('%(slot)s');
    if (!slot) return false;            // 슬롯이 없으면 조용히 물러난다
    if (doc.getElementById("%(id)s")) return true;

    var dark = isDark();
    // 파이썬이 읽는 값과 화면이 쓰는 값을 처음부터 맞춘다. `st.context.theme.type` 은
    // 첫 로드에 틀릴 수 있어서, 여기서 한 번 맞춰 두면 그 뒤로는 어긋나지 않는다.
    if (syncParam(dark ? "dark" : "light")) {
      parentWindow.location.reload();
      return true;
    }

    var button = doc.createElement("button");
    button.id = "%(id)s";
    button.type = "button";
    button.textContent = dark ? "%(to_light)s" : "%(to_dark)s";
    button.title = dark ? "%(tip_light)s" : "%(tip_dark)s";
    button.setAttribute("aria-label", button.title);
    paint(button, dark);
    button.onmouseenter = function () { button.style.opacity = "1"; };
    button.onmouseleave = function () { button.style.opacity = ".92"; };
    button.onclick = function () {
      var next = dark ? "Light" : "Dark";
      try {
        parentWindow.localStorage.setItem(KEY, JSON.stringify(next));
      } catch (error) { return; }
      // `localStorage` 는 Streamlit 크롬이 읽고 조회 인자는 파이썬이 읽는다. 같은 선택을
      // 두 곳에 적어야 화면과 그림이 같은 테마를 본다.
      syncParam(next.toLowerCase());
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
    아니면 부모 창에 닿을 수 없다.

    **`st.iframe` 으로 옮기지 않는다.** 권고는 그쪽이지만(`components.v1.html` 은
    2026-06-01 제거 예정) 실제로 바꿔 띄워 보니 **iframe 이 DOM 에 아예 생기지 않아**
    버튼이 사라졌다. 브라우저에서 `document.querySelectorAll('iframe').length === 0` 으로
    확인했다. 옮기려면 그때 다시 띄워 보고 버튼이 실제로 붙는지 눈으로 봐야 한다.
    """
    components.html(
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
            "param": THEME_QUERY_PARAM,
            # 버튼은 **반대 테마의 옷**을 입는다. 어두운 화면에서는 밝은 팔레트의 면과
            # 글자색을, 밝은 화면에서는 어두운 팔레트의 것을 쓴다.
            "dark_fill": tokens.palette_value("light", "SURFACE"),
            "dark_ink": tokens.palette_value("light", "TEXT"),
            "light_fill": tokens.palette_value("dark", "SURFACE"),
            "light_ink": tokens.palette_value("dark", "TEXT"),
        },
        height=0,
    )
