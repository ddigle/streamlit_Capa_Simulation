# Purpose: 탭 줄 JS 의 기록 지킴이 구획을 떼어 회차 맨 앞의 입장 화면 JS 가 먼저 걸게 한다.

"""브라우저 기록 지킴이를 입장 화면에도 싣는다.

지킴이는 `page_tabs.js` 의 두 구획(`<tabs-history>`·`<tabs-history-install>`)이다. Streamlit
1.63 프런트는 서버가 주소 인자를 바꿀 때마다 지금 경로로 기록을 한 칸 쌓고, 지킴이가 같은
경로의 쌓기를 칸 바꾸기로 돌린다. 탭 줄이 그것을 걸면 늦는 문서가 있다 — 새 브라우저 탭으로
링크 인자 화면(제약 시뮬레이션·공정 Capa 상세 `?process=`)에 들어오면, 그 화면이 첫 회차에
인자를 지우는 주소 메시지가 탭 줄 JS 가 마운트되기 전에 닿아 기록이 한 칸 더 쌓였다
(2026-10-26 E2E — 뒤로가기 첫 번이 화면은 그대로 둔 채 주소의 인자만 되살렸다).

탭 줄은 페이지 바로 앞에 그리고, 입장 화면(`intro_overlay`)은 부트스트랩보다 앞, 회차 맨
앞에 그린다. 그 JS 가 모듈을 읽는 순간 지킴이를 건다(브라우저 실측: 입장 화면 호스트가 첫
회차의 인자 지우기보다 0.1~1.4초 먼저 선다).

**글은 탭 줄 자산 한 벌이다.** 구획을 여기로 옮기지 않고 `page_tabs.js` 에서 떼어 낸다 — 탭
줄도 같은 함수를 안전망으로 부르고, 두 벌이면 한쪽만 고쳐 문서에 다른 지킴이가 먼저 걸린다.
이 모듈은 컴포넌트를 등록하지 않는다(`page_tabs` 는 `app.py` 에서만 불러온다 — 그 모듈을
읽으면 탭 줄이 등록된다).
"""

from __future__ import annotations

import re
from pathlib import Path

PAGE_TABS_JS = Path(__file__).with_name("page_tabs_assets") / "page_tabs.js"
SECTIONS = ("tabs-history", "tabs-history-install")


def _section(source: str, name: str) -> str:
    match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", source, re.S)
    if match is None:
        raise RuntimeError(f"page_tabs.js 에 // <{name}> 구획이 없습니다")
    return match.group("body")


def history_guard_script() -> str:
    """지킴이 두 구획과 그것을 거는 한 줄 — 모듈 맨 위에서 돌 글이다."""
    source = PAGE_TABS_JS.read_text(encoding="utf-8")
    sections = (_section(source, name) for name in SECTIONS)
    return "\n".join((*sections, "installHistoryGuard()"))
