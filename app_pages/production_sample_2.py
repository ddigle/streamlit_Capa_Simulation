# Purpose: 생산 진도 「샘플 페이지 2」 에 모듈 화면 자리를 데이터를 읽지 않고 임시로 그린다.

"""생산 진도 샘플 페이지 2(임시).

2026-11-04 검수 의견 prog-01 · prog-02 — 「생산진도 상자 내에 샘플 페이지 1,2,3 넣고 펼치는
상자로 반영」 · 「샘플페이지 1,2,3 화면에 이대로 임시 반영」. 생산 진도 머리 화면과 이름만 다르고
같은 꼴(머리말 + 점선 「모듈 화면 자리」)이다 — 그리는 것은 `components/module_slot.py` 한 벌이다.
모듈이 이 자리에 그리는 길이 생기면 바꾼다(`docs/TODO.md` 2장 「생산 진도 화면 내용」).
"""

from __future__ import annotations

from capa_simulation.components.module_slot import render_module_slot_page

render_module_slot_page("샘플 페이지 2")
