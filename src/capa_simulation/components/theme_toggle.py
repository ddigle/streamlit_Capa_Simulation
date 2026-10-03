# Purpose: 상단 헤더의 Deploy 왼쪽에 밝게/어둡게 전환 버튼(과 넘겨받은 툴바 버튼)을 얹는다.

"""테마 전환 버튼을 Streamlit 헤더 안에 넣는다.

**Streamlit 1.63 에는 앱 안에서 테마를 바꾸는 공개 API 가 없다.** `st.context.theme` 은
읽기 전용이고, 파이썬 쪽에서 우리 토큰만 뒤집으면 Plotly·표만 어두워지고 위젯·사이드바·
알림은 밝은 채로 남는다 — 반쯤 어두운 화면은 안 하느니만 못하다.

그래서 **프론트엔드가 테마를 기억하는 자리**를 그대로 쓴다. Streamlit 은 고른 테마를
`localStorage` 에 `stActiveTheme-<경로>-v2` 로 적고, 값은 `"System"`·`"Light"`·`"Dark"`
셋 중 하나인 JSON 문자열이다. 그 값을 바꾸고 새로고침하면 **Streamlit 크롬과 우리 토큰이
함께** 바뀐다(우리 쪽은 `st.context.theme` 이 새 값을 보고하므로 저절로 따라온다).
브라우저에서 실측으로 확인한 경로다.

## 앱 전체에 한 가지 테마 — 키 규칙

Streamlit 1.63 은 그 키를 **번들을 읽는 순간의 경로**로 한 번만 정하고 한 번만 읽는다. 키가 페이지
경로마다 따로라, 그대로 두면 한 페이지에서 고른 테마가 다른 페이지에 닿지 않는다. 그래서 고른 값의
정본은 **앱 키 하나**(`THEME_APP_KEY`)이고, 경로별 Streamlit 키는 그 사본이다. 규칙은
`THEME_RULE_SCRIPT` 한 벌이고 테마 버튼·Guide·툴바 Summary·입장 화면(`intro_overlay`)이 모두 그것을
쓴다 — 이 넷이 서로 다른 규칙을 보면 입장 화면이 새로고침을 잘못 예측해 끊기거나 10초를 기다린다.

- **경로는 쓰는 순간 읽는다.** 이 iframe 은 앱 안에서 페이지를 옮겨도 남으므로, 처음 실행 때 계산해
  둔 경로는 다른 페이지에서 틀린 키가 된다.
- **열릴 때(`sync`)**: 앱 키가 정한 값을 지금 경로의 Streamlit 키(와 우리 표지가 있는 다른 경로의
  Streamlit 키)에 적는다. 지금 경로의 키를 고쳐 적었거나 주소의 `?theme` 이 다르면 **한 번**
  새로고침한다.
- **우리가 적은 경로만 만진다.** 다른 경로는 표지(`THEME_SYNC_PREFIX` + 경로)가 있는 것, 곧
  이 앱이 한 번이라도 맞춰 적은 경로만 고른다. 한 출처에 다른 Streamlit 앱이 같이 있으면
  (`/proxy/<포트>/`) 그 앱의 키를 덮어쓰거나 그 앱의 메뉴 선택을 받아들이지 않기 위해서다.
- **키 때문에는 탭마다 한 번만 새로고침한다.** Streamlit 은 문서가 열릴 때마다 지금 경로의 키를
  제 값으로 다시 적는다. 그 값이 우리가 적은 것과 어긋나면(판올림·테마 설정 변경) 새로고침이
  끝없이 돈다. 그래서 새로고침 전에 `sessionStorage` 에 표지(`THEME_RELOAD_GUARD_PREFIX` + 경로)를
  남기고, 다음 로드에도 어긋나 있으면 다시 새로고침하지 않고 `?theme` 만 맞춘 채 멈춘다. 키가
  맞는 로드에서 표지를 지운다. 표지를 못 남기면 키 때문에는 새로고침하지 않는다.
- **처음이면 밝게**: 앱 키가 비었으면 지금 경로의 Streamlit 키에 고른 값이 있으면 그것을(예전 판의
  경로별 선택을 한 번 이어받는다), 없으면 `"Light"` 다.
- **⋮ 메뉴로 고른 것도 존중한다.** 그 메뉴는 지금 경로의 Streamlit 키만 고친다. 그래서 경로마다
  「우리가 마지막으로 적은 값」(`THEME_SYNC_PREFIX` + 경로)을 남겨 두고, 열릴 때 어느 경로의
  Streamlit 키가 그 표지와 다르면 **사람이 메뉴로 바꾼 것**으로 보고 앱 키로 받아들인다. 표지가
  없으면(예전 판이 남긴 값) 받아들이지 않고 앱 키가 이긴다. 메뉴의 `"System"` 은 고른 값으로
  치지 않는다(처음 여는 화면은 밝게라는 결정과 같다).
- **버튼을 누르면(`choose`)**: 앱 키·지금 경로와 표지가 있는 경로의 Streamlit 키·표지를 모두 새
  값으로 적고 `?theme` 을 맞춰 한 번 새로고침한다.
- 저장소에 쓰지 못하면 Streamlit 키 때문에는 새로고침하지 않는다(쓰기 실패가 새로고침 반복이 되지
  않게). 그때는 예전처럼 `?theme` 만 밝게로 맞춘다.

**처음 여는 화면은 밝은 테마다.** 고르기 전의 `"System"` 은 브라우저의 `prefers-color-scheme`
을 따르므로, OS 를 어둡게 쓰는 사람에게는 이 앱이 어두운 화면으로 처음 열린다. 그래서 첫
로드에 `"Light"` 를 적어 둔다 — 그 뒤로는 버튼으로 고른 값이 그대로 남는다.

주소에 `?theme=` 가 없는 첫 방문은 한 번 새로고침한다. 그러면 한 탭이 세션 둘을 만들어, 빈 DB
에 시드를 쓰던 첫 세션이 끝나는 순간 두 번째 세션의 연결이 같은 파일을 두고 겹친다(E2E
G1-D0). 그 겹침은 `_sql_helpers.connect` 가 기다려 푼다. OS 가 밝을 때 새로고침을 건너뛰는
방법도 해 봤지만, 세션 도중 OS 테마가 바뀌면 크롬만 어두워지는 반쯤 어두운 화면이 다시
생겨(검토 실측) 되돌렸다(2026-10-01). 버려지는 첫 세션이 덜 돌도록 `app.py` 는 이 iframe 을
입장 화면 바로 뒤, 부트스트랩보다 앞에서 보낸다.

**이 iframe 의 내용은 회차마다 같아야 한다.** 내용이 바뀌면 Streamlit 이 iframe 을 새로
만들고, 옛 iframe 이 만든 툴바 버튼의 `onclick` 은 떨어져 나간 문서의 함수라 브라우저가 더는
부르지 않는다 — 버튼이 눌러도 반응이 없어진다(파이썬의 테마를 실어 보내 보다가 실측했다).

버튼이 앉는 자리는 `[data-testid="stToolbarActions"]` 다 — Deploy 버튼 **바로 왼쪽**의
빈 슬롯이고, React 가 툴바를 다시 그려도 주입한 노드가 살아남는 것을 확인했다.

**비공식 경로임을 분명히 해 둔다.** `data-testid` 와 `localStorage` 키 모양은 Streamlit 이
판올림에서 바꿀 수 있다. 슬롯이 바뀌면 버튼이 **안 생길 뿐**이다 — 스크립트가 슬롯을 못 찾으면
조용히 물러난다. 키 모양이나 Streamlit 이 키에 다시 적는 값이 바뀌면 탭마다 **한 번 더 새로고침한
뒤** 크롬 테마가 고른 값과 어긋난 채 멈춘다(위 「한 번만」 표지 — 새로고침이 끝없이 돌지는 않는다).
`pyproject.toml` 이 마이너를 못박고 있으므로 올릴 때 버튼이 보이고 Dark·Light 가 로드 한 번에
바뀌는지 확인한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.design.theme import THEME_QUERY_PARAM

# Streamlit 과 맞춰야 하는 계약은 저장 키 모양(접두·접미)과 툴바 슬롯이다. 한 곳에 모아 두어야
# 판올림에서 무엇을 확인해야 하는지가 분명하다. 툴바 슬롯과 테마 버튼 id 는 같은 툴바에 단추를
# 얹는 Guide·Summary 스크립트(`page_guide`·`intro_summary`)도 여기서 받아 쓴다.
THEME_STORAGE_PREFIX = "stActiveTheme-"
THEME_STORAGE_SUFFIX = "-v2"
TOOLBAR_SLOT = '[data-testid="stToolbarActions"]'
THEME_BUTTON_ID = "capa-theme-toggle"
# 앱이 고른 테마의 정본(`"Light"`·`"Dark"` 글자 그대로). 경로별 Streamlit 키는 이것의 사본이다.
THEME_APP_KEY = "capa-theme"
# 경로마다 「우리가 그 경로의 Streamlit 키에 마지막으로 적은 값」. 뒤에 경로를 붙인다.
THEME_SYNC_PREFIX = "capa-theme-synced-"
# 탭마다(`sessionStorage`) 「이 경로를 키 때문에 한 번 새로고침했다」는 표지. 뒤에 경로를 붙인다.
THEME_RELOAD_GUARD_PREFIX = "capa-theme-reloaded-"

# 테마 키 규칙 한 벌(모듈 설명의 「키 규칙」). 툴바 iframe 맨 앞 `<script>` 와 입장 화면 등록 JS
# 앞에 그대로 실린다. 모든 함수가 창(`win`)을 받아 **부르는 순간의** `win.location.pathname` 으로
# 키를 만든다 — 경로를 미리 계산해 두지 않는다. `resolve` 는 아무것도 적지 않는 예측이고,
# `sync`·`choose` 만 적는다. 저장소를 못 읽으면 밝게, 새로고침 없음이다.
_THEME_RULE_TEMPLATE = """
var capaTheme = (function () {
  var APP_KEY = "%(app_key)s";
  var SYNC_PREFIX = "%(sync_prefix)s";
  var GUARD_PREFIX = "%(guard_prefix)s";
  var PREFIX = "%(prefix)s";
  var SUFFIX = "%(suffix)s";

  // 사람이 **고른** 값만 값으로 친다. `"System"`·빈 값은 고르지 않은 것이다.
  function pick(value) {
    return value === "Dark" || value === "Light" ? value : null;
  }

  function streamlitKey(path) {
    return PREFIX + path + SUFFIX;
  }

  function streamlitValue(storage, path) {
    try { return pick(JSON.parse(storage.getItem(streamlitKey(path)) || "null")); }
    catch (error) { return null; }
  }

  // 지금 경로와, 우리 표지(`SYNC_PREFIX` + 경로)가 있는 경로 — 이 앱이 맞춰 적은 경로만이다.
  // Streamlit 테마 키 전부를 훑지 않는다: 한 출처에 다른 Streamlit 앱이 같이 있으면
  // (`/proxy/<포트>/`) 그 앱의 키를 덮어쓰고 그 앱의 ⋮ 메뉴 선택을 앱 키로 받아들이게 된다.
  function knownPaths(storage, current) {
    var paths = [current];
    for (var index = 0; index < storage.length; index += 1) {
      var key = storage.key(index);
      if (!key || key.length <= SYNC_PREFIX.length || key.indexOf(SYNC_PREFIX) !== 0) continue;
      var path = key.slice(SYNC_PREFIX.length);
      if (paths.indexOf(path) < 0) paths.push(path);
    }
    return paths;
  }

  // ⋮ 메뉴로 바꾼 값: 우리가 적은 표지가 있고 Streamlit 키가 그와 다른 경로의 값.
  function menuChoice(storage, paths) {
    for (var index = 0; index < paths.length; index += 1) {
      var mark = pick(storage.getItem(SYNC_PREFIX + paths[index]));
      var value = streamlitValue(storage, paths[index]);
      if (mark && value && value !== mark) return value;
    }
    return null;
  }

  // 이 탭에서 이 경로를 키 때문에 이미 한 번 새로고침했는가(`sessionStorage`).
  // 못 읽으면 안 한 것으로 본다.
  function reloadedOnce(win, path) {
    try { return win.sessionStorage.getItem(GUARD_PREFIX + path) !== null; }
    catch (error) { return false; }
  }

  // 이 창이 써야 할 테마와, 지금 경로의 Streamlit 키가 그와 다른지(`stale` — 새로고침해야 한다).
  // 새로고침 뒤에도 여전히 다르면(이 탭의 표지가 남아 있으면) 다시 새로고침하지 않는다 —
  // Streamlit 이 열릴 때마다 그 키를 제 값으로 다시 적으므로, 그 값이 우리가 적은 것과
  // 어긋나기 시작하면(판올림·테마 설정 변경) 새로고침이 끝없이 돈다. 그때는 `?theme` 만 맞춘다.
  function resolve(win) {
    var state = { choice: "Light", stale: false, mismatch: false, paths: [] };
    try {
      var storage = win.localStorage;
      var path = win.location.pathname;
      var here = streamlitValue(storage, path);
      state.paths = knownPaths(storage, path);
      state.choice = menuChoice(storage, state.paths) || pick(storage.getItem(APP_KEY))
        || here || "Light";
      state.mismatch = here !== state.choice;
      state.stale = state.mismatch && !reloadedOnce(win, path);
    } catch (error) { state.stale = false; }
    return state;
  }

  // 앱 키와 경로들의 Streamlit 키·표지를 `choice` 로 적는다. 지금 경로의 Streamlit 키가 실제로
  // 그 값이 됐는지를 돌려준다 — 못 적었는데 새로고침하면 끝없이 새로고침한다.
  function write(win, paths, choice) {
    var storage = win.localStorage;
    var path = win.location.pathname;
    storage.setItem(APP_KEY, choice);
    for (var index = 0; index < paths.length; index += 1) {
      try {
        if (streamlitValue(storage, paths[index]) !== choice) {
          storage.setItem(streamlitKey(paths[index]), JSON.stringify(choice));
        }
        storage.setItem(SYNC_PREFIX + paths[index], choice);
      } catch (error) { /* 다른 경로는 그 경로가 열릴 때 다시 맞춘다 */ }
    }
    return streamlitValue(storage, path) === choice;
  }

  // 페이지가 열릴 때. `stale` 이 참이면 지금 경로의 키를 고쳐 적었으니 새로고침해야 한다.
  // 그 새로고침을 이 탭의 표지로 남기고(못 남기면 새로고침하지 않는다), 키가 맞으면 지운다.
  function sync(win) {
    var state = resolve(win);
    try {
      if (!write(win, state.paths, state.choice)) state.stale = false;
    } catch (error) { state.stale = false; }
    var guard = GUARD_PREFIX + win.location.pathname;
    try {
      if (state.stale) win.sessionStorage.setItem(guard, "1");
      else if (!state.mismatch) win.sessionStorage.removeItem(guard);
    } catch (error) { state.stale = false; }
    return state;
  }

  // 버튼을 눌렀을 때. 못 적으면 예외를 그대로 낸다(부른 쪽이 새로고침하지 않는다).
  function choose(win, choice) {
    var paths = knownPaths(win.localStorage, win.location.pathname);
    if (!write(win, paths, choice)) throw new Error("theme not stored");
  }

  return { resolve: resolve, sync: sync, choose: choose };
})();
"""
THEME_RULE_SCRIPT = _THEME_RULE_TEMPLATE % {
    "app_key": THEME_APP_KEY,
    "sync_prefix": THEME_SYNC_PREFIX,
    "guard_prefix": THEME_RELOAD_GUARD_PREFIX,
    "prefix": THEME_STORAGE_PREFIX,
    "suffix": THEME_STORAGE_SUFFIX,
}

# `st.iframe` 은 높이 0 을 받지 않는다(양수 px·`"stretch"`·`"content"` 만 — 0 이면
# `StreamlitInvalidHeightError` 로 페이지가 선다). 1px 로 띄우고 아래 규칙으로 0 으로 접는다.
# `"content"` 는 스크립트뿐인 문서라도 기본 150px 칸을 잡아 모든 화면을 그만큼 내린다.
_FRAME_HEIGHT_PX = 1
# 이 iframe 과 그것을 감싼 요소 칸을 높이 0 으로 접는다. 칸의 높이는 `height` 가 아니라
# flex 기본 크기(`flex: 0 0 1px`)에서 나오므로 그것까지 덮어야 본문이 1px 내려가지 않는다
# (브라우저 실측: 접기 전 본문 맨 위 113px, 접은 뒤 112px — `components.v1.html` 높이 0 과 같다).
# iframe 은 `srcdoc` 에 든 버튼 id 로 고른다. 스타일만 든 `st.html` 은 본문 자리를 먹지 않는다.
_COLLAPSE_STYLE = (
    "<style>"
    f'[data-testid="stElementContainer"]:has(> iframe[srcdoc*="{THEME_BUTTON_ID}"]),'
    f'iframe[data-testid="stIFrame"][srcdoc*="{THEME_BUTTON_ID}"]'
    "{flex:0 0 0 !important;height:0 !important;min-height:0 !important;}"
    "</style>"
)

_SCRIPT = """
<script>
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  if (typeof capaTheme === "undefined") return;
  var doc = parentWindow.document;

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

    // 키 규칙(`capaTheme`)이 앱 키를 지금 경로의 Streamlit 키에 맞춰 적는다. 그 키를 고쳐
    // 적었으면 Streamlit 크롬은 이미 옛 값으로 떴으므로 새로고침한다. 조회 인자도 같은 왕복에서
    // 맞춘다 — `st.context.theme.type` 은 첫 로드에 틀릴 수 있어 파이썬은 그 인자를 읽는다.
    var state = capaTheme.sync(parentWindow);
    var dark = state.choice === "Dark";
    var paramChanged = syncParam(dark ? "dark" : "light");
    if (state.stale || paramChanged) {
      // 입장 화면 JS 가 이 스크립트보다 늦게 돌면 키가 이미 맞춰져 있어 새로고침을 예측하지 못한다.
      // 이 표지를 보고 인트로를 아낀다(`intro.js` 의 `themeReloadPending`).
      parentWindow.__capaThemeReloading = true;
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
      // 경로는 **누르는 순간** 읽는다(`capaTheme` 안) — 이 iframe 은 페이지를 옮겨도 남는다.
      try { capaTheme.choose(parentWindow, next); } catch (error) { return; }
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


def render_theme_toggle(extra_scripts: Sequence[str] = ()) -> None:
    """헤더에 전환 버튼을 얹는다. `app.py` 가 한 번만 부른다.

    `extra_scripts` 는 같은 툴바에 버튼을 얹는 **다른 스크립트**다(`page_guide` 의 Guide 버튼).
    iframe 을 따로 두지 않고 여기에 함께 싣는다 — 높이 0 iframe 도 본문 맨 위에 요소 간격 한
    칸을 먹어서, 하나 더 두면 모든 화면이 그만큼 내려간다.

    `st.iframe` 하나를 쓰고 높이를 0 으로 접는다(`_COLLAPSE_STYLE`). `st.html` 은 스크립트를
    실행하지 않으므로 iframe 이 아니면 부모 창에 닿을 수 없다. 예전의 `components.v1.html` 은
    회차마다 터미널에 폐기 예고를 찍어 `st.iframe` 으로 옮겼다(2026-10-01). 예전에 옮겼다가
    iframe 이 안 생긴 것은 높이 0 이 오류로 막혔기 때문이다 — 1px 로 띄워 CSS 로 접는다.
    """
    st.html(_COLLAPSE_STYLE)
    st.iframe(
        f"<script>{THEME_RULE_SCRIPT}</script>"
        + _SCRIPT
        % {
            "slot": TOOLBAR_SLOT,
            "id": THEME_BUTTON_ID,
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
        }
        + "".join(f"<script>{script}</script>" for script in extra_scripts),
        height=_FRAME_HEIGHT_PX,
    )
