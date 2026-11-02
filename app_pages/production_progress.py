# Purpose: 생산 진도 그룹의 머리 화면 자리를 데이터를 읽지 않는 빈 화면으로 둔다.

"""생산 진도 머리 화면(빈 자리).

사이드바 그룹 「생산 진도」 는 실행 관리와 Dynamic Capa 사이에 선다
(2026-11-02 사용자 요청 — 「실행관리와 Dynamic Capa 페이지모음 사이에
생산 진도 라는 페이지모음추가하고 빈페이지 추가해둬」). 무엇을 보일지는
아직 정하지 않았으므로 이 화면은 머리말과 「준비 중」 한 줄만 그린다.
시나리오·설비 DB 를 열지 않으므로 사이드바 공통 조건 줄도 조건 카드도
없다(`navigation.PRODUCTION_PROGRESS`). 내용이 정해지면 이 선언부터 다시 본다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.components.page_header import MATURITY_BADGES, page_badges, render_page_header

render_page_header(
    "생산 진도",
    description="생산 진도를 보는 화면 묶음의 자리입니다. 보일 내용은 정해지는 대로 채웁니다.",
    badges=page_badges(MATURITY_BADGES["draft"]),
)
st.info("준비 중인 화면입니다.", icon=":material/construction:")
