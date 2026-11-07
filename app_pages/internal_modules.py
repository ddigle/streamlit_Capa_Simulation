# Purpose: 사이드바 「모듈」 상자의 머리 화면 — 켜진 모듈과 화면 링크, 꺼짐·실패 수를 보인다.

"""모듈 색인(현황 요약).

코어 화면이라 늘 등록되고(주소로는 열린다) 켜진 모듈이 있을 때만 사이드바 상자의 머리로 선다. 링크는
`st.page_link` 가 아니라 `render_page_link` 다 — 등록되지 않은 페이지를 `st.page_link` 로 걸면 단독
실행(`tests/test_all_pages_render.py`)에서 화면 전체가 죽는다. DB 를 열지 않는다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.page_link import render_page_link
from capa_simulation.module_registry import MATURITY_LABELS
from capa_simulation.navigation import module_page_specs, module_scan

OFF_FAILED_HELP = "꺼지거나 실패한 모듈의 까닭은 Admin Area 「모듈 상태」 에서 봅니다."

render_page_header("모듈")
render_page_guide("internal_modules", title="모듈")

scan = module_scan()
pages_by_module: dict[str, list[tuple[str, str, str | None]]] = {}
for spec in module_page_specs():
    pages_by_module.setdefault(spec.module or "", []).append((spec.path, spec.title, spec.icon))

if not scan.active:
    st.caption("켜진 모듈이 없습니다.")
for record in scan.active:
    manifest = record.manifest
    if manifest is None:
        continue
    with st.container(border=True):
        st.markdown(
            f"**{literal_markdown(manifest.name)}** · {MATURITY_LABELS[manifest.maturity]} · "
            f"담당 {literal_markdown(manifest.owner)}"
        )
        if manifest.description:
            st.caption(literal_markdown(manifest.description))
        for path, title, icon in pages_by_module.get(manifest.id, []):
            render_page_link(path, label=title, icon=icon)

off = sum(1 for record in scan.records if record.state == "off")
failed = sum(1 for record in scan.records if record.state == "failed")
# 수만 자리에 두고 까닭을 보는 곳은 풍선이 말한다 — 길 안내 글도 바로 가기도 두지 않는다(설계 규칙
# UI-TXT-03 · UI-TXT-04).
if off or failed:
    st.caption(f"꺼짐 {off} · 실패 {failed}", help=OFF_FAILED_HELP)
