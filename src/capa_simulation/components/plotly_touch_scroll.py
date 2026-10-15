# Purpose: 칸 선택을 켠 Plotly 그림 위에서 시작한 터치가 화면을 스크롤하게 하는 스크립트를 만든다.

"""칸 선택을 켠 Plotly 그림의 터치 스크롤 막이.

`st.plotly_chart(on_select=…)` 를 켜면 Streamlit 1.63 프런트엔드가 그림의 `dragmode` 가 거짓값
(`False`)일 때 `pan` 으로 덮는다(참값이면 그대로 둔다 — 어느 참값이든 아래와 같다). Plotly 의
끌기 층(`dragElement`)은 `dragmode !== false` 이면 `touchstart` 에서 `preventDefault()` 를 부르므로,
손가락이 그 그림 위에서 움직이기 시작하면 본문 세로 스크롤도 월 캔버스 가로 스와이프도 먹히지
않는다. 축이 `fixedrange` 라 끌어도 그림은 움직이지 않으니 손가락만 묶이는 셈이다(2026-10-15 검토,
터치 Chrome 실측 — 선택을 켠 두 그림 위 스와이프에서 본문 `scrollTop` 이 그대로였다).

그래서 부모 문서에 **캡처 단계** `touchstart` 듣개를 하나 달아, 이름 붙인 그림 안에서 시작한 터치는
Plotly 까지 내려보내지 않는다(`stopPropagation`). `preventDefault` 를 부르는 쪽이 없으니 스와이프는
브라우저가 스크롤한다. 칸 누르기는 그대로 된다 — 막지 않은 탭에는 브라우저가 호환 마우스 사건
(`mousemove`·`mousedown`·`mouseup`)을 이어 보내고, Plotly 는 그것을 마우스 클릭으로 받아 선택을 낸다
(같은 실측: 탭 한 번에 공정 Capa 상세로 옮겼다). 듣개는 `passive` 라 스크롤을 기다리게 하지 않는다.

그림은 Streamlit 이 key 로 다는 `st-key-<key>` 칸 안의 `.js-plotly-plot` 으로 고른다. **칸 선택을 켠
그림은 그 key 를 이 막이 목록에 더한다**(`app.py` 가 넘기는 key 묶음). 목록에 없으면 그 그림 위에서
시작한 터치 스크롤이 다시 막힌다.

테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`). iframe 내용은 회차마다 같아야 하므로 스크립트는 고정 문자열이다. iframe 이 다시
만들어지면 옛 iframe 의 함수는 브라우저가 부르지 않으므로, 창에 남긴 옛 듣개를 떼고 새로 단다.

**비공식 경로다.** Streamlit 의 `dragmode` 덮기·`st-key-` 칸 이름과 Plotly 의 터치 처리가 판올림에서
바뀔 수 있다. 바뀌어도 화면은 멀쩡하고 터치 스크롤이 다시 막히거나 막이가 할 일이 없어질 뿐이다.
올릴 때 터치 화면(또는 터치를 켠 브라우저)에서 그 그림 위 스와이프와 탭을 한 번 본다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

# 부모 창에 남기는 지금 듣개의 이름. iframe 이 다시 만들어지면 이것으로 옛 듣개를 뗀다.
HANDLER_NAME = "__capaPlotlyTouchScroll"
# key 는 CSS 선택자에 그대로 들어간다. Streamlit 이 `st-key-` 칸 이름에 쓰는 글자만 받는다.
_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]+")

_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;
  var selector = %(selector)s;

  // 이름 붙인 그림 안에서 시작한 터치는 Plotly 끌기 층까지 내려보내지 않는다. 그쪽이
  // `preventDefault` 로 스크롤을 막기 때문이다. 탭은 브라우저의 호환 마우스 사건으로 클릭이 된다.
  function guard(event) {
    var target = event.target;
    if (target && typeof target.closest === "function" && target.closest(selector)) {
      event.stopPropagation();
    }
  }

  var previous = parentWindow.%(handler)s;
  if (previous) doc.removeEventListener("touchstart", previous, true);
  parentWindow.%(handler)s = guard;
  doc.addEventListener("touchstart", guard, { capture: true, passive: true });
})();
"""


def touch_scroll_selector(chart_keys: Sequence[str]) -> str:
    """막이가 고르는 그림들 — 각 key 칸 안의 Plotly 그림."""
    keys = tuple(dict.fromkeys(chart_keys))
    if not keys:
        raise ValueError("터치 스크롤 막이에 넘긴 그림 key 가 없습니다.")
    for key in keys:
        if not _KEY_PATTERN.fullmatch(key):
            raise ValueError(f"터치 스크롤 막이의 그림 key 는 영문·숫자·_·- 만 씁니다: {key!r}")
    return ", ".join(f".st-key-{key} .js-plotly-plot" for key in keys)


def plotly_touch_scroll_script(chart_keys: Sequence[str]) -> str:
    """칸 선택을 켠 그림 위 터치가 화면을 스크롤하게 하는 스크립트. 테마 버튼 iframe 에 싣는다."""
    return _SCRIPT % {
        "selector": json.dumps(touch_scroll_selector(chart_keys)),
        "handler": HANDLER_NAME,
    }
