# Purpose: 화면의 업무 활용 목적과 부서별 Action Item, 로드맵을 같은 모양으로 그린다.

"""Shared "업무 활용 목적 및 로드맵" panel.

그룹 머리 화면이 업무 활용 목적·부서별 Action Item·로드맵 한 줄을 같은 제목·아이콘·카드
배치로 그리는 자리다. 지금은 Execution Management(실행관리) 머리가 부서별 Gap·A/Item 을
여기에 싣는다. 머리를 더 두게 되면 문구만 넘기고 배치는 이 한 곳을 고친다.

**기본으로 접어 둔다.** 이 패널은 제목 바로 아래 첫 블록이라, 펼쳐 두면 답을 보러 온
사람이 매번 바뀌지 않는 설명을 먼저 지나야 한다. 접어 두면 필요한 사람만 편다.
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
    """업무 활용 목적 · 담당 부서별 Action Item · 로드맵 한 줄을 접어 둔 상자에 그린다.

    `owners` 는 (부서 역할, 하는 일) 쌍이다. 부서 수가 늘어도 같은 줄에 이어 붙는다.
    """
    with st.expander("업무 활용 목적 및 로드맵", icon=":material/route:", expanded=False):
        st.caption(purpose)
        # 부서 카드에는 테두리를 두르지 않는다. 이미 접힌 상자 안이라 선을 한 겹 더 그어도
        # 층이 생기지 않고 — `st.container(border=True)` 는 면을 채우지 않고 선만 긋는다 —
        # 같은 굵기의 선 두 겹만 남는다. 카드를 가르는 일은 `gap` 이 한다.
        with st.container(horizontal=True, gap="medium"):
            for owner, action in owners:
                with st.container():
                    st.markdown(f"**{owner}**")
                    st.write(action)
        st.caption(f"로드맵 · {roadmap}")
