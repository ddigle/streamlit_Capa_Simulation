# Purpose: 첫 로딩을 입장 화면으로 덮고, 다 그려지면 Detail(원래 화면)·Summary(요약)로 들인다.

"""첫 접속 입장 화면(인트로 오버레이)과 Summary 요약 화면.

HOME 첫 로딩은 몇 초가 걸린다. 그동안 빈 화면이 반쯤 그려지는 대신 웨이퍼 심볼과 `S.PKG CAPA`
워드마크가 나타나 원형으로 화면 전체로 펼쳐지고, 입장 화면이 단계 막대로 진행을 보여 준다. 앱이
다 그려지면 단추 둘이 켜진다.

- **Detail** — 원래 화면(HOME 등)으로 들어간다. 누른 단추에서 원이 퍼지며 앱이 드러난다.
- **Summary** — 같은 오버레이 안에서 **최신 공식버전의 여섯 달 요약**을 모션으로 그린다(역할
  분리: 앱 안은 상세, 이 화면은 요약 — 2026-10-02 사용자 결정). 타이틀·로딩 막대가 위로 빠지고,
  Summary 는 Detail 밑으로 접히고, Detail 은 심볼·라벨 옆으로 옮겨 라벨과 같은 글자가 되며, 웨이퍼는
  제자리·같은 속도로 돌면서 20% 무채색으로 흐려진다. 그 위에 생산계획 선·B/N 확보율 막대(부족
  대수)·월별 시트(Density·Wafer 계획·제품 비중 도넛)가 차례로 조립된다. 값은
  `components/intro_summary.py` 가 따로 보낸다.

원래 화면으로 들어간 뒤에는 툴바의 `Summary` 단추(`intro_summary.summary_toolbar_script`)가 같은
요약을 다시 연다 — 화면이 그 단추 속으로 접히며 요약이 드러난다. 오버레이는 걷지 않고 감춰 둔다
(워커는 멈추고 캔버스는 1px 로 줄인다).

**어떻게 덮는가.** Components v2 하나를 `app.py` 맨 앞(부트스트랩 전)에 그린다. 그 JS 가
`document.body` 에 자기 호스트를 붙여 거기에 그린다 — 컴포넌트 칸 안에 그리면 Streamlit 머리말·
사이드바의 쌓임 맥락 아래에 깔린다. 칸 자체는 `_HIDE_STYLE` 로 접어 본문에 틈을 남기지 않는다.

**로딩에 끊기지 않게.** 첫 로딩 동안 메인 스레드는 Streamlit 이 HOME 의 표·그림을 그리느라
수백 ms 씩 막힌다(8514 실측 최대 0.5초). 그래서 심볼·워드마크·원형 펼침·웨이퍼 맵과 **Summary 의
차트(선·막대·시트·도넛·숫자 세기)** 는 JS 의 `scene()` 이 **워커의 OffscreenCanvas** 에 그린다.
HTML 로 둔 글자·단추·행 이름은 합성기가 돌리는 투명도·이동만 쓰고 시작 시각을 미리 예약한다(같은
부하에서 장면 프레임 최대 간격 0.48초 → 66ms). 요약 값은 로딩 중에 미리 받아 워커가 글꼴·배치까지
마쳐 둔다 — 누른 뒤에는 그리기만 한다. 워커를 못 쓰면 같은 장면을 메인 스레드에서 돌린다.

**언제 켜는가.** 파이썬은 「다 그렸다」를 알릴 수 없다. `st.stop()` 뒤로는 어떤 요소도 브라우저에
닿지 않고(13개 화면이 멈춘다), 오류로 끝난 실행도 마찬가지다. 그래서 JS 가 앱 뿌리의
`data-test-script-state` 가 `notRunning` 이 되는 것을 본다. 단계 막대는 요약 데이터가 닿은 것과
HOME 본문의 `LoadingProgress` 막대 퍼센트를 읽어 채운다(`_steps`). 둘 다 비공식 화면 속성이라
Streamlit 을 올릴 때 브라우저로 확인한다 — 속성이 사라져도 인트로 뒤 바로 단추가 켜질 뿐 앱을
가두지 않는다.

**한 탭에 한 번.** Detail 로 들어가면 `sessionStorage` 에 적는다. 테마 버튼·새로고침은 새 세션을
만들지만 같은 탭이라 다시 띄우지 않는다. 주소의 테마 인자가 고른 테마와 다르거나 없을 때(첫 방문·옛
북마크·남이 보낸 링크)와 지금 경로의 Streamlit 테마 키가 앱 키와 다를 때 `theme_toggle` 이 한 번
새로고침한다. JS 가 그 스크립트와 **같은 규칙**(등록 JS 앞에 붙인 `THEME_RULE_SCRIPT`)으로 미리
알아채고 — 그 스크립트가 먼저 돌아 이미 새로고침을 걸었으면 창에 남긴 표지(`__capaThemeReloading`)로
알아챈다 — 그 사이에는 앱 바탕색 한 장만 보여 주며 인트로를 아낀다. 끊겨 보이지 않게. 헤더에 테마
버튼이 서면(새로고침이 없다는 뜻) 바로, 실행이 끝나고 2초가 조용하거나 10초가 지나도 시작한다.

**회차마다 같은 것을 보낸다.** 등록한 HTML·CSS·JS(글꼴 포함)와 `data` 가 매 회차 같아야 Streamlit
이 같은 메시지를 다시 보내지 않고, JS 도 다시 불리지 않는다. 색은 테마와 무관한
`tokens.INTRO_PALETTE` 한 벌이고, 첫 프레임만 브라우저가 칠한 앱 바탕색을 쓴다.

**글꼴.** 워드마크·타이틀·단추·시트의 달은 Archivo 800·폭 75%, 차트 숫자는 Archivo 700·폭 100% 다.
사내망에는 외부 글꼴이 없어 이 화면이 쓰는 글자만 담은 부분 글꼴 둘(`archivo-capa.woff2`·
`archivo-capa-number.woff2`, SIL OFL 1.1 — 같은 폴더 `OFL.txt`)을 저장소에 두고, 등록 때 base64 로
JS 에 싣는다. **`BRAND`·`TITLE_LINES`·단추 이름의 글자를 바꾸면 그 글자가 부분 글꼴에 있는지
확인한다** — 없으면 그 글자만 본문 글꼴로 떨어진다. 한글(단계·상태·차트 이름표)은 본문
글꼴(`tokens.FONT_FAMILY`)이고, 워커 캔버스도 같은 시스템 글꼴로 그린다.

HTML·CSS·JS 는 `intro_overlay_assets/` 의 파일이다(파이썬 문자열에 넣으면 줄 길이 검사와
이스케이프가 JS 를 망가뜨린다). AppTest 는 JS 를 돌리지 못하고, 모듈 로드 때 등록한 컴포넌트는
AppTest 인스턴스마다 살아 있지 않아 `app.py` 를 여는 테스트는 `render_intro_overlay` 와
`render_intro_summary` 를 바꿔 끼운다.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import streamlit as st

from capa_simulation.components.home_rendering import HOME_LOADING_STAGES
from capa_simulation.components.theme_toggle import THEME_BUTTON_ID, THEME_RULE_SCRIPT
from capa_simulation.design import tokens
from capa_simulation.design.theme import THEME_QUERY_PARAM

_ASSETS = Path(__file__).with_name("intro_overlay_assets")

# 컴포넌트 칸의 key 이자 숨김 규칙의 훅(`st-key-…`).
INTRO_OVERLAY_KEY = "capa_intro_overlay"

BRAND = "S.PKG CAPA"
TITLE_LINES = ("S.PKG Capa", "Simulation")
DETAIL_LABEL = "Detail"
SUMMARY_LABEL = "Summary"
# `archivo-capa.woff2` 를 만든 글자 목록. Google Fonts 의 `css2?family=Archivo:wdth,wght@75,800`
# 에 `text=` 로 이 글자를 넘겨 받은 부분 글꼴이다. 위 넷과 시트의 달(`26.10`)에 새 글자를 쓰면 이
# 목록으로 다시 받고 여기를 고친다(`tests/test_intro_overlay.py` 가 빠진 글자를 잡는다). 타이틀은
# CSS 가 대문자로 바꾸므로 대문자도 들어 있어야 한다.
FONT_SUBSET_TEXT = "S.PKG CAPA SIMULATION Capa Simulation Detail Summary 0123456789."
# `archivo-capa-number.woff2`(`wdth,wght@100,700`) — Summary 차트의 숫자·단위. 한글(`억`)은 이
# 글꼴에 없어 본문 글꼴로 그린다.
NUMBER_FONT_SUBSET_TEXT = "0123456789.,%+-–KGb"


def _asset_text(name: str) -> str:
    return (_ASSETS / name).read_text(encoding="utf-8")


def _registered_js() -> str:
    """intro.js 앞에 화면 틀·스타일·글꼴과 테마 키 규칙을 붙인다. 등록 때 한 번만 만든다.

    테마 키 규칙(`theme_toggle.THEME_RULE_SCRIPT`)은 테마 버튼이 쓰는 것과 **같은 문자열**이다 —
    새로고침할지를 같은 규칙으로 미리 보려는 것이고, 입장 화면의 색과는 상관이 없다.
    """
    font = base64.b64encode((_ASSETS / "archivo-capa.woff2").read_bytes()).decode("ascii")
    number = base64.b64encode((_ASSETS / "archivo-capa-number.woff2").read_bytes()).decode("ascii")
    prelude = (
        f"const OVERLAY_HTML = {json.dumps(_asset_text('intro.html'))};",
        f"const OVERLAY_CSS = {json.dumps(_asset_text('intro.css'))};",
        f'const FONT_DATA = "{font}";',
        f'const NUMBER_FONT_DATA = "{number}";',
        THEME_RULE_SCRIPT,
    )
    return "\n".join((*prelude, _asset_text("intro.js")))


_INTRO = st.components.v2.component("capa_intro_overlay", js=_registered_js())

# 컴포넌트 칸을 접는다. 스타일만 든 `st.html` 은 본문 자리를 먹지 않는다. 칸이 그려지기 **전**에
# 보내야 한 프레임이라도 틈이 생기지 않는다.
_HIDE_STYLE = (
    "<style>"
    f'[data-testid="stLayoutWrapper"]:has(> .st-key-{INTRO_OVERLAY_KEY}),'
    f".st-key-{INTRO_OVERLAY_KEY}"
    "{display:none !important;}"
    "</style>"
)


def _steps() -> list[dict[str, Any]]:
    """입장 화면의 여섯 단계와 각 단계를 끝냈다고 볼 신호.

    차례는 실제로 끝나는 차례다. `app.py` 는 부트스트랩 뒤·페이지 앞에서 요약을 보내므로 요약이
    HOME 계산보다 먼저 닿는다.

    - `boot` — 앱이 부트스트랩을 지나 무언가를 보냈다(요약 데이터나 HOME 막대가 보였다).
    - `summary` — 요약 데이터가 닿았다(만들지 못했다는 값도 닿은 것이다).
    - `until` — HOME `LoadingProgress` 막대의 누적 퍼센트(`HOME_LOADING_STAGES`)가 이 값을 넘었다.
      기준정보 확인(0번), Capa 계산(1번), B/N 집계·차트(2·3번 → 3번까지).
    - `end` — 실행이 끝났다. HOME 이 아닌 화면에는 막대가 없으므로 남은 단계가 이때 한꺼번에 찬다.
    """
    return [
        {"label": "시나리오", "signal": "boot"},
        {"label": "요약", "signal": "summary"},
        {"label": "기준정보", "until": HOME_LOADING_STAGES[0].percent},
        {"label": "부하량·Capa", "until": HOME_LOADING_STAGES[1].percent},
        {"label": "확보율", "until": HOME_LOADING_STAGES[3].percent},
        {"label": "HOME", "signal": "end"},
    ]


def _data() -> dict[str, Any]:
    return {
        "palette": dict(tokens.INTRO_PALETTE),
        "font_body": tokens.FONT_FAMILY,
        "brand": BRAND,
        "title": list(TITLE_LINES),
        # theme_toggle 이 새로고침할지를 같은 규칙으로 미리 보려고 넘긴다(그 모듈의 상수 그대로).
        # 저장 키는 등록 JS 앞에 붙인 `capaTheme` 규칙이 안다.
        "theme": {
            "param": THEME_QUERY_PARAM,
            "button_id": THEME_BUTTON_ID,
        },
        "steps": _steps(),
        "text": {
            "boot": "시나리오와 기준정보를 불러오는 중",
            "waiting": "준비 중",
            "detail": DETAIL_LABEL,
            "summary": SUMMARY_LABEL,
            "detail_title": "원래 화면으로 들어갑니다",
            "summary_title": "공식버전 요약을 봅니다",
            "ready": "준비 완료",
            "hint": "처음 접속하면 계산 결과를 새로 만드느라 조금 더 걸립니다.",
            "slow": "계산이 길어지고 있습니다. 들어가면 HOME 진행 막대로 이어서 볼 수 있습니다.",
            "months": "시작월부터 {n}개월",
            # 행 이름 아래 설명은 단위가 필요한 생산계획 하나만 둔다. 나머지 둘은 범례가
            # 뜻을 나른다(2026-10-03 사용자 결정 — 설명 문구를 뺐다).
            "rows": [
                {"title": "생산계획", "sub": "Density · 억Gb"},
                {"title": "B/N 확보율"},
                {"title": "월별 시트"},
            ],
            "status": {"secure": "확보", "warning": "경고", "shortage": "부족"},
            "lowest": "최저",
        },
    }


def render_intro_overlay() -> None:
    """입장 화면을 건다. `app.py` 가 **매 회차**, 부트스트랩보다 먼저 한 번 부른다.

    매 회차 같은 자리에 같은 내용으로 그려야 첫 실행 도중의 rerun 에도 덮개가 내려가지 않는다.
    이미 들어간 탭이면 JS 가 아무것도 하지 않는다.
    """
    st.html(_HIDE_STYLE)
    _INTRO(key=INTRO_OVERLAY_KEY, data=_data())
