# Purpose: 페이지 제목·상자 제목·큰 숫자에 Archivo 부분 글꼴을 거는 앱 전체 서체 스타일을 보낸다.

"""앱 전체 서체 — B 균형형(2026-10-06 사용자 결정).

입장 화면·Summary 가 쓰는 「영문·숫자는 Archivo, 한글은 Noto Sans KR」 짝을 본문 화면의 **세 자리**
에만 넓힌다. 나머지(본문 한글, 표·차트 숫자 `FONT_FAMILY_NUMERIC`, 사이드바 메뉴, Plotly 안 글꼴)는
그대로다. 자리 → 서체 표는 `docs/design_system.md` 1-1 절이다.

- 페이지 제목(`st.title` 의 `h1`) — Archivo 800 · 폭 100%, 자간 -0.01em.
- 상자·구획 제목(`####` 꼴 `h4` 와 `h2`·`h3`, HOME 구획 제목 `section_title_markup`, HOME `Summary`
  접힘 제목) — 같은 짝 700. 크기는 지금 그대로다.
- 큰 숫자(`st.metric` 값, HOME 결론 줄의 확보율) — Archivo 700 · 숫자 폭 고정(`tabular-nums`).

한글은 Archivo 에 없어 `tokens.FONT_FAMILY_DISPLAY` 스택의 다음 글꼴(Noto Sans KR → 맑은 고딕)로
떨어진다. 선택자는 모두 본문(`stMain`) 안으로 묶어 사이드바·입장 화면 덮개(`body` 직속)에 닿지
않는다.

**글꼴 파일.** 사내 PC 는 외부 글꼴 서버에 나가지 못한다. 그래서 Google Fonts 를 부르지 않고
Archivo 의 인쇄 가능한 ASCII(`FONT_SUBSET_TEXT`)만 담은 woff2 둘(700·800, 폭 100%, 각 8KB 남짓)을
저장소 `static/fonts/` 에 두고(SIL OFL 1.1 — 같은 폴더 `OFL.txt`) **Streamlit 정적 파일 서빙**
(`.streamlit/config.toml` 의 `[server] enableStaticServing = true`)으로 보낸다. 주소는 상대 경로
`app/static/fonts/…` 다 — Streamlit 자신의 `[[theme.fontFaces]]` 안내와 같은 형식이고, 문서 주소
기준으로 풀리므로 사내 WebIDE 처럼 앞에 접두 경로(`/proxy/<포트>/`)가 붙어도 맞는다. 글꼴이 늦게
오면 시스템 글꼴로 먼저 그리고 바꾼다(`font-display: swap`). `unicode-range` 를 ASCII 로 묶어 한글만
든 글자에는 파일을 받지 않는다.

data URI 로 스타일에 싣는 길(파일 둘 base64 약 22KB)은 쓰지 않는다. 이 스타일은 매 회차 보내야
하는 요소라(빠지면 그 회차에 규칙이 사라진다) 회차마다 22KB 를 직렬화·해시하게 되고, 정적 파일은
브라우저가 한 번 받아 캐시한다(실측 비교는 `docs/design_system.md` 1-1 절).

**부분 글꼴을 다시 받는 법.** 글자 목록은 `FONT_SUBSET_TEXT` 다. Google Fonts
`css2?family=Archivo:wdth,wght@100,<굵기>&text=<FONT_SUBSET_TEXT 를 URL 인코딩>` 을 최신 Chrome
User-Agent 로 받아(그래야 woff2 주소를 준다) 응답 CSS 의 `src: url(…)` 파일을 그대로
`static/fonts/archivo-<굵기>.woff2` 로 저장한다(굵기 700·800). 입장 화면의 부분 글꼴
(`intro_overlay_assets/` 의 `CapaIntroDisplay` 75%·800, `CapaIntroNumber`)과는 파일·이름을 나눈다 —
그쪽은 입장 화면 JS 가 `FontFace` 로 등록하고 워커 캔버스에도 넘기는 따로 된 한 벌이다.

스타일은 색이 없어 테마와 무관한 고정 문자열이다. `app.py` 가 부트스트랩보다 앞에서 매 회차 보낸다.
"""

from __future__ import annotations

from typing import Final

import streamlit as st

from capa_simulation.design import tokens

# `@font-face` 이름. 입장 화면이 등록하는 `CapaIntroDisplay`·`CapaIntroNumber` 와 다른 이름이어야
# 한다 — 같은 이름이면 굵기·폭이 다른 두 벌이 한 이름 아래 섞인다.
DISPLAY_FAMILY: Final = "CapaDisplay"
# 정적 서빙 주소(문서 기준 상대 경로)와 저장소 위치. `static/` 은 `app.py` 옆이어야 한다.
FONT_URL_PREFIX: Final = "app/static/fonts/"
FONT_DIR: Final = "static/fonts"
FONT_FILES: Final = {700: "archivo-700.woff2", 800: "archivo-800.woff2"}
# 부분 글꼴에 든 글자 — 인쇄 가능한 ASCII 전부(U+0020–U+007E). `unicode-range` 와 같은 범위다.
FONT_SUBSET_TEXT: Final = "".join(chr(code) for code in range(0x20, 0x7F))
UNICODE_RANGE: Final = "U+20-7E"
# 큰 숫자 자리에 붙이는 클래스. `st.metric` 밖에서 큰 값을 그리는 마크업(HOME 결론 줄)이 단다.
FIGURE_CLASS: Final = "capa-figure"


def _font_face(weight: int) -> str:
    return (
        "@font-face {"
        f" font-family: {DISPLAY_FAMILY};"
        f' src: url("{FONT_URL_PREFIX}{FONT_FILES[weight]}") format("woff2");'
        f" font-weight: {weight}; font-style: normal; font-display: swap;"
        f" unicode-range: {UNICODE_RANGE};"
        " }"
    )


# 선택자의 구체성은 Streamlit 의 emotion 규칙(클래스 하나 + 태그)과 같거나 높고, 이 스타일은 `body`
# 안에 있어 `head` 의 emotion 규칙보다 뒤에 온다 — 같으면 뒤가 이긴다.
_RULES = f"""
[data-testid="stMain"] h1 {{
  font-family: {tokens.FONT_FAMILY_DISPLAY};
  font-weight: 800;
  letter-spacing: -0.01em;
}}
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4,
[data-testid="stMain"] [role="heading"][aria-level="2"] {{
  font-family: {tokens.FONT_FAMILY_DISPLAY};
  font-weight: 700;
}}
[data-testid="stMain"] [data-testid="stMetricValue"],
[data-testid="stMain"] .{FIGURE_CLASS} {{
  font-family: {tokens.FONT_FAMILY_DISPLAY};
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
"""

TYPOGRAPHY_STYLE: Final = (
    "<style>\n" + "\n".join(_font_face(weight) for weight in FONT_FILES) + _RULES + "</style>"
)


def render_typography_style() -> None:
    """서체 스타일을 보낸다. `app.py` 가 부트스트랩보다 앞에서 매 회차 한 번 부른다.

    스타일만 든 `st.html` 이라 본문 자리를 먹지 않는다. 고정 문자열이라 회차마다 같다.
    """
    st.html(TYPOGRAPHY_STYLE)
