# Purpose: 모듈 화면이 들어올 점선 자리와 그 자리만 든 화면 한 벌을 데이터 없이 그린다.

"""모듈 화면 자리.

생산 진도 그룹의 화면은 보일 내용을 모듈이 맡는다 — 2026-11-03 사용자 「생산 진도 화면에는
일단 모듈에 스크립트를 넣으면 반영될 페이지 영역만 표시해둬」. 머리 화면과 그 아래 샘플 페이지
셋(2026-11-04 검수 의견 prog-01 · prog-02 — 「샘플페이지 1,2,3 화면에 이대로 임시 반영」)이 이름만
다르고 같은 꼴이어야 하므로 머리말 · 점선 자리를 여기 한 벌로 둔다. 화면 파일은 제 이름 한 줄만
넘긴다(`render_module_slot_page`).

모듈이 이 자리에 그리는 길(`module_api` · `module.json` 선언 · 모듈 규칙 · 지침서)은 아직 없다 —
`docs/TODO.md` 2장 「생산 진도 화면 내용」. 시나리오 · 설비 DB 를 열지 않으므로 이 자리를 그리는
화면은 사이드바 공통 조건 줄도 조건 카드도 없다(`navigation.PRODUCTION_PROGRESS` ·
`PRODUCTION_PROGRESS_SUBPAGES`).
"""

from __future__ import annotations

import html

import streamlit as st

from capa_simulation.components.page_header import MATURITY_BADGES, page_badges, render_page_header
from capa_simulation.design import tokens

# 머리말 설명 한 줄 — 머리 화면과 샘플 페이지가 같은 글이다(이름만 다르다).
MODULE_SLOT_PAGE_DESCRIPTION = (
    "생산 진도를 보는 화면 묶음입니다. 내용은 아래 자리에 모듈 화면으로 들어옵니다."
)
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


def render_module_slot_page(title: str) -> None:
    """머리말(제목 · 「화면 초안」 배지 · 설명 한 줄)과 그 아래 모듈 화면 자리 하나를 그린다.

    `title` 은 사이드바 라벨과 같은 화면 이름이다(`navigation` 선언 — 시험이 맞댄다)."""
    render_page_header(
        title,
        description=MODULE_SLOT_PAGE_DESCRIPTION,
        badges=page_badges(MATURITY_BADGES["draft"]),
    )
    st.html(module_slot_html())
