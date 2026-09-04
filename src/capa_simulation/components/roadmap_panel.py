# Purpose: 화면의 업무 활용 목적과 부서별 Action Item, 로드맵을 같은 모양으로 그린다.

"""Shared "업무 활용 목적 및 로드맵" panel.

Static Capa 와 Dynamic Capa 가 같은 구조를 각자 복제하고 있었다. 제목·아이콘·중첩
카드 배치가 같고 문구만 달랐다. 한 화면에서 배치를 고치면 다른 쪽도 따라와야 하므로
여기로 합친다.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st


def render_roadmap_panel(
    *,
    purpose: str,
    owners: Sequence[tuple[str, str]],
    roadmap: str,
) -> None:
    """업무 활용 목적 · 담당 부서별 Action Item · 로드맵 한 줄을 카드로 그린다.

    `owners` 는 (부서 역할, 하는 일) 쌍이다. 부서 수가 늘어도 같은 줄에 이어 붙는다.
    """
    with st.container(border=True):
        st.markdown("#### :material/route: 업무 활용 목적 및 로드맵")
        st.caption(purpose)
        with st.container(horizontal=True, gap="small"):
            for owner, action in owners:
                with st.container(border=True):
                    st.markdown(f"**{owner}**")
                    st.write(action)
        st.caption(f"로드맵 · {roadmap}")
