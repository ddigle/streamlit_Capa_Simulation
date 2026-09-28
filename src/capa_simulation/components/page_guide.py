# Purpose: 헤더 테마 버튼 옆 Guide 버튼과 화면별 사용 안내 대화상자를 그린다.

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
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from capa_simulation.design import tokens

GUIDE_TRIGGER_KEY = "page_guide_trigger"
BUTTON_ID = "capa-guide-button"
GUIDE_DIR = Path(__file__).resolve().parents[1] / "guides"
# 툴바 버튼이 누를 숨은 버튼. Streamlit 은 `key` 를 `st-key-<key>` 클래스로 단다.
_TRIGGER_SELECTOR = f".st-key-{GUIDE_TRIGGER_KEY} button"

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;

  function dark() {
    try {
      var key = "stActiveTheme-" + parentWindow.location.pathname + "-v2";
      return JSON.parse(parentWindow.localStorage.getItem(key) || '"Light"') === "Dark";
    } catch (error) { return false; }
  }

  function place() {
    var slot = doc.querySelector('[data-testid="stToolbarActions"]');
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
    button.onclick = function () {
      var trigger = doc.querySelector('%(trigger)s');
      if (trigger) trigger.click();
    };
    // 테마 버튼 **바로 왼쪽**에 선다. 테마 버튼이 아직 없으면 슬롯 맨 앞에 둔다.
    var theme = doc.getElementById("capa-theme-toggle");
    slot.insertBefore(button, theme || slot.firstChild);
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
# 언제나 감춘다 — 본문에 「Guide」 버튼이 하나 더 보이면 안 된다.
_BASE_STYLE = f"""
<style>
#{BUTTON_ID} {{ display: none !important; }}
.st-key-{GUIDE_TRIGGER_KEY} {{ display: none !important; }}
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
        "trigger": _TRIGGER_SELECTOR,
        "light_border": tokens.palette_value("light", "BORDER"),
        "dark_border": tokens.palette_value("dark", "BORDER"),
        "light_ink": tokens.palette_value("light", "TEXT"),
        "dark_ink": tokens.palette_value("dark", "TEXT"),
    }


def render_guide_base_style() -> None:
    """모든 화면에 까는 기본 규칙. `app.py` 가 매 회차 한 번 부른다."""
    st.html(_BASE_STYLE)


def load_guide(page: str) -> str:
    """`guides/<page>.md` 원문. 없으면 `FileNotFoundError` — 페이지가 가이드를 약속했는데
    파일이 없으면 조용히 빈 대화상자를 여는 것보다 테스트에서 터지는 편이 낫다."""
    return (GUIDE_DIR / f"{page}.md").read_text(encoding="utf-8")


def render_page_guide(page: str, *, title: str) -> None:
    """이 화면의 Guide 를 단다. 페이지 본문 맨 앞에서 한 번 부른다.

    툴바 버튼을 보이게 하는 규칙과 그 버튼이 누를 숨은 버튼을 그린다. 숨은 버튼이 눌린
    회차에 대화상자를 연다.
    """
    body = load_guide(page)
    st.html(_SHOW_STYLE)
    if st.button("Guide", key=GUIDE_TRIGGER_KEY):
        _open_guide(title, body)


def _open_guide(title: str, body: str) -> None:
    @st.dialog(f"Guide · {title}", width="large")
    def _guide() -> None:
        st.markdown(body)

    _guide()
