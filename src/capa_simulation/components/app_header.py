# Purpose: 상단 띠의 면을 칠하고 앱 이름·개발자·인증 정보를 모든 페이지에 표시한다.

"""App name, developer, and clearance info pinned to the top bars.

Streamlit 은 헤더(`stHeader`)에 위젯을 넣는 공식 API 를 주지 않는다. 대신 그 요소의
가상요소 두 개에 글을 얹는다. 헤더는 `position: absolute` 라 자기 자신이 포함 블록이고
왼쪽 끝이 사이드바 오른쪽에 붙어 있으므로, 사이드바를 접거나 폭을 끌어 바꿔도 글이 따라
움직인다 — 좌표를 손으로 계산하는 `position: fixed` 배너와 갈리는 지점이다.

사이드바 머리칸(`stSidebarHeader`)도 같은 높이라 같은 방법으로 앱 이름과 버전을 얹는다.
두 글이 같은 선에 놓여 한 줄의 띠처럼 읽힌다. 오른쪽 끝은 접기 버튼 자리라 비워 둔다.

대가는 가상요소의 한계다. 줄마다 글 한 덩어리와 스타일 하나뿐이라 한 줄 안에서 굵기나
색을 섞지 못하고, 링크·버튼처럼 누를 수 있는 것도 못 넣는다. 그래서 두 줄로 나눠 위는
개발 정보, 아래는 인증 정보를 싣는다. 값은 `settings.py` 가 단일 근거이고 ⋮ 메뉴의
About 과 같은 상수를 본다.

띠의 면은 페이지 바탕보다 한 단계만 눌러(`tokens.HEADER_BAR`) 앱 머리와 본문을 나눈다.
글자색은 본문과 같다 — 면이 밝아 뒤집을 이유가 없다.

`data-testid` 는 emotion 클래스와 달리 판올림 사이에 비교적 안정적이지만 어디까지나
비공식 경로다. Streamlit 을 올린 뒤에는 글이 헤더에 남아 있는지 눈으로 확인한다.
"""

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.settings import (
    APP_AUTH_CODE,
    APP_BUILD_DATE,
    APP_CONTACT_EMAIL,
    APP_HANDLING_NOTE,
    APP_NAME,
    APP_OWNER_TEAM,
    APP_SECURITY_LEVEL,
    APP_VERSION,
)

_TOP_LINE = f"{APP_OWNER_TEAM} · {APP_CONTACT_EMAIL}"
_BOTTOM_LINE = (
    f"v{APP_VERSION} ({APP_BUILD_DATE}) · {APP_SECURITY_LEVEL}"
    f" · 인증번호 {APP_AUTH_CODE} · {APP_HANDLING_NOTE}"
)

# CSS 는 중괄호가 많아 f-string 으로 두면 전부 이스케이프해야 한다. 색·글자 자리에
# 센티넬을 두고 모듈 로드 시 한 번만 치환한다.
_HEADER_CSS = (
    """
[data-testid="stHeader"] {
  background: __BAR__ !important;
  border-bottom: 1px solid __BAR_BORDER__;
}

/* `stHeader` 는 본문 너비만 덮는다. 사이드바 위쪽에도 같은 띠를 이어 붙이지 않으면 색이
   화면 중간에서 끊겨, 같은 줄에 놓인 두 글이 서로 다른 면 위에 앉는다. 띠는 스크롤하지
   않는 사이드바 겉면에 붙여 사이드바를 내려도 제자리에 남기고, 내용은 그 아래로 지나간다. */
[data-testid="stSidebar"]::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3.75rem;
  background: __BAR__;
  border-bottom: 1px solid __BAR_BORDER__;
  z-index: 10;
}

[data-testid="stHeader"]::before,
[data-testid="stHeader"]::after {
  position: absolute;
  line-height: 1.1rem;
  left: 1.5rem;
  /* 오른쪽 툴바(실행 표시·Stop·Deploy·⋮)가 쓰는 폭은 비워 둔다. 창이 좁아지면
     글자를 밀어내지 않고 말줄임으로 끊는다. */
  max-width: calc(100% - 16rem);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  padding-left: 0.55rem;
  border-left: 3px solid __ACCENT__;
  font-family: __FONT_FAMILY__;
  /* 헤더 위에 얹히므로 툴바 클릭을 가로채지 않게 한다. */
  pointer-events: none;
}

/* 두 줄의 줄높이를 같게 두면 묶음 높이가 정확히 2.2rem 이고, 윗줄을 가운데에서 한 줄
   위로 올리고 아랫줄을 가운데에 두는 것만으로 띠 한가운데에 정렬된다. 띠 높이가 바뀌어도
   따라간다 — 위에서부터 잰 고정값은 띠 높이를 바꾸는 순간 어긋난다. */
[data-testid="stHeader"]::before {
  content: "__TOP_LINE__";
  top: calc(50% - 1.1rem);
  font-size: 0.78rem;
  font-weight: 600;
  color: __TEXT__;
}

[data-testid="stHeader"]::after {
  content: "__BOTTOM_LINE__";
  top: 50%;
  font-size: 0.72rem;
  color: __TEXT_MUTED__;
}

/* 사이드바 머리칸. 기본이 `position: static` 이라 기준 상자로 삼으려면 지정해야 한다.
   접기 버튼은 흐름 배치라 이 지정에 움직이지 않는다. */
[data-testid="stSidebarHeader"] {
  position: relative;
  /* 띠 위로 올린다. 띠에 가리면 앱 이름도 접기 버튼도 묻힌다. */
  z-index: 11;
}

[data-testid="stSidebarHeader"]::before,
[data-testid="stSidebarHeader"]::after {
  position: absolute;
  line-height: 1.1rem;
  left: 0;
  /* 오른쪽 끝 접기 버튼 자리는 비운다. 사이드바를 좁게 끌면 말줄임으로 끊는다. */
  max-width: calc(100% - 3rem);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  padding-left: 0.55rem;
  border-left: 3px solid __ACCENT__;
  font-family: __FONT_FAMILY__;
  pointer-events: none;
}

[data-testid="stSidebarHeader"]::before {
  content: "__APP_NAME__";
  top: calc(50% - 1.1rem);
  font-size: 0.78rem;
  font-weight: 600;
  color: __TEXT__;
}

[data-testid="stSidebarHeader"]::after {
  content: "__APP_VERSION__";
  top: 50%;
  font-size: 0.72rem;
  color: __TEXT_MUTED__;
}

/* 사이드바를 접으면 헤더 왼쪽 끝에 펼침 버튼이 나타나 첫 글자와 겹친다. 그 자리만큼 민다.
   사이드바와 헤더는 부모가 달라 형제 선택자가 닿지 않으므로 접힘 상태를 `:has()` 로 본다.
   `:has()` 를 모르는 브라우저는 이 규칙만 버리고 접었을 때만 겹친다. */
[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
  [data-testid="stHeader"]::before,
[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"])
  [data-testid="stHeader"]::after {
  left: 4rem;
}
""".replace("__ACCENT__", tokens.ACCENT)
    .replace("__BAR_BORDER__", tokens.BORDER)
    .replace("__BAR__", tokens.HEADER_BAR)
    .replace("__APP_NAME__", APP_NAME)
    .replace("__APP_VERSION__", f"v{APP_VERSION}")
    .replace("__FONT_FAMILY__", tokens.FONT_FAMILY)
    .replace("__TEXT_MUTED__", tokens.TEXT_MUTED)
    .replace("__TEXT__", tokens.TEXT)
    .replace("__TOP_LINE__", _TOP_LINE)
    .replace("__BOTTOM_LINE__", _BOTTOM_LINE)
)


def render_app_header() -> None:
    """헤더 글을 그린다. 페이지마다 부르지 말고 `app.py` 에서 한 번만 부른다."""
    st.html(f"<style>{_HEADER_CSS}</style>")
