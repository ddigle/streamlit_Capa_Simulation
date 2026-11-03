# Purpose: 생산 진도 그룹의 머리 화면에 모듈 화면이 들어올 자리를 데이터를 읽지 않고 그린다.

"""생산 진도 머리 화면(모듈 화면 자리).

사이드바 그룹 「생산 진도」 는 실행 관리와 Dynamic Capa 사이에 선다
(2026-11-02 사용자 요청). 보일 내용은 모듈이 맡는다 — 2026-11-03 사용자
「생산 진도 화면에는 일단 모듈에 스크립트를 넣으면 반영될 페이지 영역만
표시해둬」. 그래서 이 화면은 머리말 아래에 모듈 화면이 들어올 넓은 점선
자리 하나만 그린다. 모듈이 이 자리에 그리는 길(`module_api` · `module.json`
선언 · 모듈 규칙 · 지침서)은 아직 없다 — `docs/TODO.md` 2장 「생산 진도 화면
내용」. 시나리오·설비 DB 를 열지 않으므로 사이드바 공통 조건 줄도 조건 카드도
없다(`navigation.PRODUCTION_PROGRESS`).
"""

from __future__ import annotations

import html

import streamlit as st

from capa_simulation.components.page_header import MATURITY_BADGES, page_badges, render_page_header
from capa_simulation.design import tokens

# 자리 글 — 제목 한 줄과 안내 한 줄. 화면 확인·따라하기 가이드가 이 글을 보지 않는다.
MODULE_SLOT_TITLE = "모듈 화면 자리"
MODULE_SLOT_TEXT = "모듈에 스크립트를 넣으면 이 자리에 표시됩니다."
# 머리말 아래를 거의 채우는 높이 — 창이 낮아도 360px 은 선다.
MODULE_SLOT_MIN_HEIGHT = "max(360px, calc(100vh - 340px))"


def module_slot_html() -> str:
    """모듈 화면 자리 — 점선 테두리 넓은 상자 하나(색은 지금 테마의 토큰).

    `st.html` 은 SVG 를 걸러 내므로 그림 없이 글 두 줄만 둔다."""
    style = (
        ".pp-module-slot{display:flex;flex-direction:column;align-items:center;"
        "justify-content:center;gap:8px;box-sizing:border-box;width:100%;"
        f"min-height:{MODULE_SLOT_MIN_HEIGHT};padding:24px;"
        f"border:2px dashed {tokens.BORDER_STRONG};border-radius:10px;"
        f"background:{tokens.SURFACE_SUBTLE};color:{tokens.TEXT_MUTED};text-align:center}}"
        f".pp-module-slot strong{{color:{tokens.TEXT};font-size:1.05rem;font-weight:600}}"
        "@media print{.pp-module-slot{min-height:240px}}"
    )
    title = html.escape(MODULE_SLOT_TITLE)
    return (
        f"<style>{style}</style>"
        f'<section class="pp-module-slot" role="region" aria-label="{title}">'
        f"<strong>{title}</strong>"
        f"<span>{html.escape(MODULE_SLOT_TEXT)}</span>"
        "</section>"
    )


render_page_header(
    "생산 진도",
    description="생산 진도를 보는 화면 묶음입니다. 내용은 아래 자리에 모듈 화면으로 들어옵니다.",
    badges=page_badges(MATURITY_BADGES["draft"]),
)
st.html(module_slot_html())
