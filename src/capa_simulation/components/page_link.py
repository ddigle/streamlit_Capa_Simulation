# Purpose: 단독 실행에도 죽지 않는 페이지 링크와 꺼진 링크에 aria-disabled 를 다는 스크립트를 둔다.

"""막힌 화면에서 다음 화면으로 건너가는 링크.

`st.page_link` 는 `st.navigation` 에 등록된 페이지만 받는다. 페이지를 단독 실행하는
테스트에는 네비게이션이 없어 그대로 두면 화면 전체가 예외로 죽는다. 링크가 없다고 화면이
멎을 이유는 없으므로 문구로 물러선다.

라벨을 인자로 받는 것은 이 링크가 카드 안뿐 아니라 안내문 뒤에도 놓이기 때문이다. 카드
안에서는 제목이 목적지를 말해 주므로 「열기」로 충분하지만, 문단 뒤에서는 그것만으로 어디를
여는지 알 수 없다.

**꺼진 링크의 `aria-disabled`.** Streamlit 1.63 은 `disabled` 링크를 `<a disabled>` 로 그린다 —
`<a>` 의 `disabled` 는 HTML 속성이 아니어서 읽기 도구가 꺼졌다고 읽지 않는다(공정 Capa 상세 「이
공정 제약 시뮬레이션」 — E2E r3 #115). `disabled_link_aria_script` 가 부모 문서의 화면 링크
(`stPageLink-NavLink`)마다 `disabled` 를 `aria-disabled="true"` 로 옮겨 달고 다시 켜지면 뗀다.
테마 버튼 iframe 에 다른 툴바 스크립트와 함께 싣는다(`theme_toggle.render_theme_toggle` 의
`extra_scripts`) — iframe 내용은 회차마다 같아야 하므로 고정 문자열이다. 듣개는 `disabled` 속성
바뀜과 새로 붙은 칸만 보고(Plotly 그림 SVG 안은 건너뛴다), iframe 이 다시 만들어지면 옛 듣개를
뗀다. **비공식 경로다** — Streamlit 이 링크를 다르게 그리면 표지가 붙지 않을 뿐 화면은 그대로다.
"""

from __future__ import annotations

from collections.abc import Mapping

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

# 부모 창에 남기는 지금 듣개(MutationObserver)의 이름. iframe 이 다시 만들어지면 이것으로 옛 것을
# 뗀다.
DISABLED_LINK_ARIA_HANDLER = "__capaDisabledLinkAria"

_DISABLED_LINK_ARIA_SCRIPT = """
(function () {
  var parentWindow = window.parent;
  if (!parentWindow || parentWindow === window) return;
  var doc = parentWindow.document;
  var body = doc && doc.body;
  if (!body || typeof body.querySelectorAll !== "function") return;
  var SELECTOR = 'a[data-testid="stPageLink-NavLink"]';
  var SVG = "http://www.w3.org/2000/svg";

  // `<a disabled>` 를 읽기 도구가 읽는 꼴로 옮긴다 — 켜지면 뗀다.
  function mark(link) {
    if (link.hasAttribute("disabled")) {
      if (link.getAttribute("aria-disabled") !== "true") link.setAttribute("aria-disabled", "true");
    } else if (link.hasAttribute("aria-disabled")) {
      link.removeAttribute("aria-disabled");
    }
  }
  function scan(node) {
    if (!node || node.nodeType !== 1 || node.namespaceURI === SVG) return;
    if (node.matches(SELECTOR)) mark(node);
    var links = node.querySelectorAll(SELECTOR);
    for (var i = 0; i < links.length; i++) mark(links[i]);
  }

  var previous = parentWindow.%(handler)s;
  if (previous && typeof previous.disconnect === "function") previous.disconnect();
  var observer = new parentWindow.MutationObserver(function (records) {
    for (var i = 0; i < records.length; i++) {
      var record = records[i];
      if (record.type === "attributes") {
        if (record.target.matches && record.target.matches(SELECTOR)) mark(record.target);
      } else {
        for (var j = 0; j < record.addedNodes.length; j++) scan(record.addedNodes[j]);
      }
    }
  });
  observer.observe(body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["disabled"],
  });
  parentWindow.%(handler)s = observer;
  scan(body);
})();
"""


def disabled_link_aria_script() -> str:
    """꺼진 화면 링크에 `aria-disabled="true"` 를 다는 스크립트. 테마 버튼 iframe 에 싣는다."""
    return _DISABLED_LINK_ARIA_SCRIPT % {"handler": DISABLED_LINK_ARIA_HANDLER}


def render_page_link(
    page_path: str,
    *,
    label: str,
    icon: str | None = None,
    query_params: Mapping[str, str] | None = None,
    disabled: bool = False,
    help: str | None = None,
    fallback: str | None = None,
) -> None:
    """`query_params` 를 주면 그 인자를 실은 주소로 연다 — 받는 페이지가 그 인자만 읽는다.

    `disabled` 면 링크가 꺼진 채 자리를 지키고(생겼다 사라지지 않는다), `help` 가 그 까닭을 풍선으로
    말한다(`st.page_link` 가 받는 인자 그대로). `fallback` 은 네비게이션이 없을 때 물러선
    글이다(없으면 「사이드바에서 <라벨>」 — 라벨이 동사구라 어색하면 준다).
    """
    try:
        if query_params is None:
            st.page_link(page_path, label=label, icon=icon, disabled=disabled, help=help)
        else:
            st.page_link(
                page_path,
                label=label,
                icon=icon,
                query_params=dict(query_params),
                disabled=disabled,
                help=help,
            )
    except StreamlitPageNotFoundError:
        st.caption(fallback or f"사이드바에서 {label}")
