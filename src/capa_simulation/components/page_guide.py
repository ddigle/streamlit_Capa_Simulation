# Purpose: 헤더 툴바 맨 왼쪽 Guide 버튼과 화면별 사용 안내 대화상자를 그린다.

"""화면 설명은 본문이 아니라 **Guide** 에 둔다(2026-09-28 사용자 결정).

본문에는 결과와 그 결과에 대한 행동(적용·붙여넣기·등록)만 남기고, 「이 설정은 무엇이고 어떤
순서로 쓰나」는 헤더의 `Guide` 버튼을 누르면 뜨는 대화상자가 말한다. 설명이 본문을 차지하면
볼 것이 밀리고, 익숙해진 사람에게는 매번 읽지 않는 글이 된다.

## 버튼이 두 개인 이유

`Guide` 버튼은 테마 버튼(`theme_toggle.py`)처럼 Streamlit 툴바에 **스크립트로 끼워 넣은**
버튼이다. 그 자리에 선 버튼은 누른 신호를 파이썬으로 보내지 못한다. 그래서 페이지가
본문에 **숨긴 Streamlit 버튼**(`GUIDE_TRIGGER_KEY`)을 하나 두고, 툴바 버튼은 그 숨은 버튼을
대신 누른다. 파이썬은 평소처럼 버튼 값을 읽어 `st.dialog` 를 연다 — 대화상자 안은
Streamlit 이 그리므로 표·강조를 그대로 쓴다.

**가이드가 없는 화면에서는 툴바 버튼이 보이지 않는다.** 기본 CSS 가 감추고, 가이드를 단
페이지만 보이게 하는 규칙을 더한다. 그 규칙은 그 페이지가 그린 요소라 다른 페이지로 옮기면
Streamlit 이 걷어 간다.

**비공식 경로다.** 툴바 슬롯의 `data-testid` 와 숨은 버튼을 찾는 선택자가 Streamlit
판올림에서 바뀌면 버튼이 **안 생기거나 눌러도 반응이 없을 뿐** 화면은 멀쩡하다. 올릴 때 이
버튼이 뜨고 눌리는지 본다.

가이드 원문은 `guides/<페이지 파일 이름>.md` 다. 코드 밖 글이라 설명을 고칠 때 코드를 건드리지
않는다.

## 따라하기 가이드(옆 창)

따라하기 가이드(`guides/howto/` 뼈대로 만든 한 파일 HTML)가 있는 화면은 `Guide` 가 대화상자가
아니라 **앱 옆의 작은 창**을 연다 — 앱 화면을 덮지 않고 번호대로 따라 하게 하려는 것이다. 고르는
차례는 `find_howto_guide` 한 곳이다.

1. `static/guides/local/<가이드>.html` — 사내판. 사내가 실화면으로 만들어 손으로 복사한다(git 무시).
2. `static/guides/howto/<가이드>.html` — 합성 예시판. 사외가 만들어 추적한다.
3. 둘 다 없으면 지금의 md 대화상자.

창은 Streamlit 정적 서빙(`.streamlit/config.toml` 의 `enableStaticServing`)이 보내는 파일을 연다.
Streamlit 1.63 은 `app/static/…` 을 확장자대로(`.html` 은 `text/html`) 내보내므로 브라우저가 그대로
그린다. 주소는 문서 기준 상대 경로 `app/static/guides/…` 다 — 사내 WebIDE 처럼 앞에 접두 경로
(`/proxy/<포트>/`)가 붙어도 맞는다(글꼴 `typography.FONT_URL_PREFIX` 와 같은 길).

창은 누르는 순간 열어야 팝업 막이에 걸리지 않는다. 파이썬 회차를 거치면 사용자 몸짓이 사라지므로
툴바 버튼이 **스스로** 연다. 어느 파일을 열지는 파이썬이 정해 툴바 버튼을 보이게 하는 규칙에 CSS
변수(`GUIDE_HREF_VARIABLE`)로 싣고, 버튼은 누를 때 그 값을 읽는다 — 변수가 없으면(가이드 없음)
지금처럼 숨은 버튼을 눌러 대화상자를 연다. 팝업이 막히면 대화상자로 물러선다. 같은 이름의 창이
이미 열려 있으면 그 창을 앞으로 부를 뿐 다시 읽지 않는다(보던 단계가 남는다).

md 원문은 창 머리의 「설정 사전」 단추로 남는다. 창은 `window.opener`(앱 창)의 숨은 버튼을 같은
방법으로 눌러 앱 창에 대화상자를 연다 — 그 선택자는 틀(`guides/howto/template.html`)이 사본으로
들고 있고 `tests/test_page_guide.py` 가 맞대 본다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import streamlit as st

from capa_simulation.components.theme_toggle import GUIDE_BUTTON_ID, TOOLBAR_SLOT
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import forget_page_dialogs
from capa_simulation.settings import PROJECT_ROOT

GUIDE_TRIGGER_KEY = "page_guide_trigger"
# 대화상자 본문 칸. 좁은 창(390px)에서 넓은 표가 칸을 넘어 대화상자 전체를 옆으로 밀고 오른쪽 칸이
# 잘렸다 — 이 칸 안의 표만 제 폭 안에서 옆으로 굴린다(`_BASE_STYLE`).
GUIDE_BODY_KEY = "page_guide_body"
# id 와 툴바 차례는 다른 툴바 단추와 함께 `theme_toggle` 한 곳에 있다(`TOOLBAR_BUTTON_ORDER`).
BUTTON_ID = GUIDE_BUTTON_ID
GUIDE_DIR = Path(__file__).resolve().parents[1] / "guides"
# 툴바 버튼이 누를 숨은 버튼. Streamlit 은 `key` 를 `st-key-<key>` 클래스로 단다. 따라하기 창의
# 「설정 사전」 단추도 같은 선택자로 앱 창의 숨은 버튼을 누른다(틀 `guides/howto/template.html`).
TRIGGER_SELECTOR: Final = f".st-key-{GUIDE_TRIGGER_KEY} button"

# 따라하기 가이드 자리. Streamlit 정적 서빙은 `app.py` 옆 `static/` 을 `app/static/…` 으로 보낸다.
STATIC_DIR: Final = PROJECT_ROOT / "static"
STATIC_URL_PREFIX: Final = "app/static/"
# 고르는 차례 그대로다 — 사내판(git 무시, 사내가 복사) → 합성 예시판(추적).
HOWTO_FOLDERS: Final[tuple[tuple[Literal["local", "example"], str], ...]] = (
    ("local", "guides/local"),
    ("example", "guides/howto"),
)
# 툴바 버튼이 누르는 순간 읽는 CSS 변수(값은 따옴표 친 상대 주소). 없으면 대화상자를 연다.
GUIDE_HREF_VARIABLE: Final = "--capa-guide-href"
# 옆 창 이름과 폭. 같은 이름이면 브라우저가 창을 하나만 둔다. 폭은 틀이 가이드만 세우는 좁은
# 꼴(1100px 미만)이고 그림이 읽히는 폭이다.
GUIDE_WINDOW_NAME: Final = "capa-guide"
GUIDE_WINDOW_WIDTH: Final = 520
# 가이드 이름은 파일 이름이자 CSS 문자열 안에 들어간다 — 따옴표 · 경로 글자를 받지 않는다.
_HOWTO_NAME = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class HowtoGuide:
    """옆 창으로 열 따라하기 가이드 한 벌."""

    kind: Literal["local", "example"]
    path: Path
    # 문서 기준 상대 주소(`app/static/guides/…`).
    url: str


def find_howto_guide(name: str, *, static_dir: Path = STATIC_DIR) -> HowtoGuide | None:
    """`name` 가이드의 사내판 → 예시판 차례로 처음 있는 것. 둘 다 없으면 None(md 대화상자).

    회차마다 파일 둘을 볼 뿐이라 캐시하지 않는다 — 사내가 사내판을 복사한 뒤 앱을 다시 띄우지
    않아도 다음 회차부터 그것을 연다.
    """
    if not _HOWTO_NAME.fullmatch(name):
        raise ValueError(f"따라하기 가이드 이름이 아닙니다: {name!r}")
    for kind, folder in HOWTO_FOLDERS:
        relative = f"{folder}/{name}.html"
        path = static_dir / relative
        if path.is_file():
            return HowtoGuide(kind=kind, path=path, url=STATIC_URL_PREFIX + relative)
    return None


_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;

  // 테마는 테마 버튼과 같은 키 규칙(`theme_toggle.THEME_RULE_SCRIPT` 의 `capaTheme`)으로 읽는다.
  // 그 규칙은 같은 iframe 의 맨 앞 스크립트가 정의한다.
  function dark() {
    return typeof capaTheme !== "undefined" && capaTheme.resolve(parentWindow).choice === "Dark";
  }

  // 페이지가 그린 규칙이 버튼에 싣는 가이드 주소(따옴표 친 상대 주소). 이 iframe 은 페이지를
  // 옮겨도 남으므로 **누르는 순간** 읽는다.
  function guideHref(button) {
    var raw = parentWindow.getComputedStyle(button).getPropertyValue("%(href_var)s").trim();
    return raw.replace(/^["']|["']$/g, "");
  }

  // 앱 옆(화면 오른쪽 끝)에 좁은 창을 연다. 같은 이름의 창이 이미 있으면 다시 읽지 않고 앞으로
  // 부른다 — 빈 주소로 열면 있는 창을 그대로 돌려받는다. 새로 생긴 빈 창만 가이드로 보낸다.
  function openGuideWindow(href) {
    if (!href) return false;
    var url;
    try { url = new parentWindow.URL(href, doc.baseURI).href; } catch (error) { return false; }
    var screen = parentWindow.screen;
    var width = %(width)d;
    var availWidth = screen.availWidth || width;
    var height = Math.max(480, (screen.availHeight || 900) - 24);
    var left = (screen.availLeft || 0) + Math.max(0, availWidth - width);
    var top = screen.availTop || 0;
    var features = "popup=yes,width=" + width + ",height=" + height +
      ",left=" + left + ",top=" + top;
    var win = parentWindow.open("", "%(window)s", features);
    if (!win) return false;
    try {
      if (win.location.href.split("#")[0] !== url) win.location.replace(url);
    } catch (error) {
      // 다른 출처(이전 앱 주소 등)의 창이면 주소를 읽지 못한다 — 가이드로 다시 보낸다.
      win = parentWindow.open(url, "%(window)s", features) || win;
    }
    try { win.focus(); } catch (error) { /* 막혀도 창은 열렸다 */ }
    return true;
  }

  function place() {
    var slot = doc.querySelector('%(slot)s');
    if (!slot) return false;
    if (doc.getElementById("%(id)s")) return true;
    var isDark = dark();
    var button = doc.createElement("button");
    button.id = "%(id)s";
    button.type = "button";
    button.textContent = "Guide";
    button.title = "이 화면의 설정과 쓰는 법";
    button.setAttribute("aria-label", button.title);
    // 테마 버튼과 같은 알약이되 면을 칠하지 않는다 — 테마 버튼은 「바꾸는」 행동이라 채운
    // 알약이고, 이쪽은 「읽는」 것이라 윤곽만 둔다. 표시 여부(`display`)는 적지 않는다 —
    // 그것은 페이지가 CSS 로 정한다.
    button.style.cssText = [
      "font:inherit", "font-size:13px", "font-weight:600", "line-height:1",
      "padding:6px 12px", "margin-right:6px", "border-radius:8px", "cursor:pointer",
      "white-space:nowrap", "background:transparent",
      "border:1px solid " + (isDark ? "%(dark_border)s" : "%(light_border)s"),
      "color:" + (isDark ? "%(dark_ink)s" : "%(light_ink)s")
    ].join(";");
    // 숨은 버튼을 `trigger.click()` 으로 누르지 않는다(2026-10-01, E2E G1-S4b·G2-D2). 그 click 은
    // `detail=0` 이라 대화상자의 react-aria 가 입력을 화면 낭독기(`virtual`)로 보고 포커스를 미뤄
    // 두었다가 놓쳤다 — 대화상자가 떠도 포커스가 BODY 에 남아 곧바로 누른 Esc 가 닿지 않았다.
    // 사람이 누른 click 처럼 `detail=1` 로 보내면 본문 버튼으로 연 팝업과 같이 대화상자가 포커스를
    // 받는다(브라우저 실측).
    button.onclick = function () {
      // 따라하기 가이드가 있는 화면이면 옆 창을 연다. 열지 못하면(가이드 없음 · 팝업 막힘)
      // 대화상자로 간다.
      if (openGuideWindow(guideHref(button))) return;
      var trigger = doc.querySelector('%(trigger)s');
      if (!trigger) return;
      trigger.dispatchEvent(new parentWindow.MouseEvent("click", {
        bubbles: true, cancelable: true, view: parentWindow, detail: 1
      }));
    };
    // 툴바 **맨 왼쪽**이다(차례 규칙 `capaToolbar` — Guide · Print · 테마). 다른 단추가 먼저
    // 섰든 아직이든 같은 자리에 선다.
    if (typeof capaToolbar !== "undefined") capaToolbar.place(slot, button);
    else slot.insertBefore(button, slot.firstChild);
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

# 기본은 감춘다. 가이드를 단 페이지만 `render_page_guide` 가 보이게 한다. 숨은 트리거 버튼은
# 언제나 감춘다 — 본문에 「Guide」 버튼이 하나 더 보이면 안 된다. 대화상자 본문의 표는 제 칸 폭을
# 넘으면 그 표만 옆으로 굴린다(넘침이 대화상자를 밀어 오른쪽 열이 잘리고 가로 바퀴로도 못 본다).
# 마크다운 표 한 벌의 넘침이라 고정 폭 캔버스를 여는 `scroll_shell` 셸이 아니다 — 높이는 내용대로라
# `overflow: auto` 는 옆으로만 굴린다.
_BASE_STYLE = f"""
<style>
#{BUTTON_ID} {{ display: none !important; }}
.st-key-{GUIDE_TRIGGER_KEY} {{ display: none !important; }}
.st-key-{GUIDE_BODY_KEY} table {{ display: block; max-width: 100%; overflow: auto; }}
</style>
"""
_SHOW_STYLE = f"<style>html body #{BUTTON_ID} {{ display: inline-block !important; }}</style>"


def guide_toolbar_script() -> str:
    """툴바에 `Guide` 버튼을 얹는 스크립트. 테마 버튼 iframe 에 함께 싣는다.

    iframe 을 따로 두지 않는 것은 높이 0 iframe 도 본문 맨 위에 요소 간격 한 칸을 먹기
    때문이다 — 하나 더 두면 모든 화면이 그만큼 내려간다.
    """
    return _SCRIPT % {
        "id": BUTTON_ID,
        "trigger": TRIGGER_SELECTOR,
        "href_var": GUIDE_HREF_VARIABLE,
        "window": GUIDE_WINDOW_NAME,
        "width": GUIDE_WINDOW_WIDTH,
        "light_border": tokens.palette_value("light", "BORDER"),
        "dark_border": tokens.palette_value("dark", "BORDER"),
        "light_ink": tokens.palette_value("light", "TEXT"),
        "dark_ink": tokens.palette_value("dark", "TEXT"),
        "slot": TOOLBAR_SLOT,
    }


def render_guide_base_style() -> None:
    """모든 화면에 까는 기본 규칙. `app.py` 가 매 회차 한 번 부른다."""
    st.html(_BASE_STYLE)


def load_guide(page: str) -> str:
    """`guides/<page>.md` 원문. 없으면 `FileNotFoundError` — 페이지가 가이드를 약속했는데
    파일이 없으면 조용히 빈 대화상자를 여는 것보다 테스트에서 터지는 편이 낫다."""
    return (GUIDE_DIR / f"{page}.md").read_text(encoding="utf-8")


def guide_show_style(guide: HowtoGuide | None) -> str:
    """툴바 버튼을 보이게 하는 규칙. 따라하기 가이드가 있으면 그 주소를 CSS 변수로 함께 싣는다.

    스타일만 든 `st.html` 이라 본문 자리를 먹지 않고, 페이지를 옮기면 Streamlit 이 걷어 간다 —
    주소도 그 화면에 있는 동안만 산다.
    """
    if guide is None:
        return _SHOW_STYLE
    return (
        f"<style>html body #{BUTTON_ID} {{ display: inline-block !important;"
        f' {GUIDE_HREF_VARIABLE}: "{guide.url}"; }}</style>'
    )


def render_page_guide(page: str, *, title: str, howto: str | None = None) -> None:
    """이 화면의 Guide 를 단다. 페이지 본문 맨 앞에서 한 번 부른다.

    툴바 버튼을 보이게 하는 규칙과 그 버튼이 누를 숨은 버튼을 그린다. 숨은 버튼이 눌린
    회차에 대화상자를 연다. `howto` 는 이 화면의 따라하기 가이드 이름이다 — 그 HTML 이 있으면
    툴바 버튼이 옆 창을 열고, 대화상자는 창 안 「설정 사전」 단추가 연다.
    """
    body = load_guide(page)
    st.html(guide_show_style(find_howto_guide(howto) if howto else None))
    # 누르면 이 화면에 열려 있던 팝업 칸을 먼저 비운다 — 팝업은 한 회차에 하나뿐이라, 붙여넣기
    # 팝업이 열린 채 Guide 를 열면 Streamlit 이 멈춘다. 콜백은 스크립트보다 먼저 돈다.
    if st.button("Guide", key=GUIDE_TRIGGER_KEY, on_click=forget_page_dialogs):
        _open_guide(title, body)


def _open_guide(title: str, body: str) -> None:
    @st.dialog(f"Guide · {title}", width="large")
    def _guide() -> None:
        with st.container(key=GUIDE_BODY_KEY):
            st.markdown(body)

    _guide()
