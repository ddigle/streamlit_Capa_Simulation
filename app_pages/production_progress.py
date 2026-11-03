# Purpose: 생산 진도 그룹의 머리 화면에 모듈 화면이 들어올 자리를 데이터를 읽지 않고 그린다.

"""생산 진도 머리 화면(모듈 화면 자리).

사이드바 그룹 「생산 진도」 는 실행 관리와 Dynamic Capa 사이에 선다
(2026-11-02 사용자 요청). 보일 내용은 모듈이 맡는다 — 2026-11-03 사용자
「생산 진도 화면에는 일단 모듈에 스크립트를 넣으면 반영될 페이지 영역만
표시해둬」. 그래서 이 화면은 머리말 아래에 모듈 화면이 들어올 넓은 점선
자리 하나만 그린다. 그룹 상자 안에서는 다른 그룹처럼 「현황 요약」 이고 그
아래 샘플 페이지 셋(`app_pages/production_sample_*.py` — 2026-11-04 검수 의견
prog-01 · prog-02, 임시)이 같은 꼴로 선다. 머리말 · 자리는
`components/module_slot.py` 한 벌이다. 시나리오·설비 DB 를 열지 않으므로
사이드바 공통 조건 줄도 조건 카드도 없다(`navigation.PRODUCTION_PROGRESS`).
"""

from __future__ import annotations

from capa_simulation.components.module_slot import render_module_slot_page

render_module_slot_page("생산 진도")
