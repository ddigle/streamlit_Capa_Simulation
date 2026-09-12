# Purpose: 모든 페이지가 같은 모양의 제목·설명·상태 배지를 그리도록 한다.

"""One page header for every screen.

제목 다음에 설명 한 줄이 오는 형태는 14개 페이지 중 11개가 이미 쓰고 있었지만 나머지는
설명이 없거나 곧바로 탭이 이어져 페이지마다 첫인상이 달랐다. 여기로 모아 간격과 배지
표기를 한 번에 정한다.

`(구현중)` 은 제목 문자열에 섞어 두지 않고 배지로 뽑는다. 사이드바 라벨은 여전히
`navigation.py` 가 소유하며 그쪽 표기와 어긋나면 테스트가 잡는다.
"""

from __future__ import annotations

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.navigation import IMPLEMENTING_SUFFIX

# 제목 오른쪽 진행 표시 자리의 폭. 단계 이름과 퍼센트가 한 줄에 들어가는 최소치다.
STATUS_SLOT_WIDTH_PX = 320

# 제목 줄을 나누는 비율. 왼쪽 칸이 제목보다 조금 넓어 진행 표시가 제목 바로 옆에서
# 시작한다. 왼쪽을 더 좁히면 제목이 두 줄로 접히고, 더 넓히면 진행 표시가 제목에서
# 멀찍이 떨어진다.
TITLE_STATUS_COLUMN_RATIO = (2, 3)

# 화면이 어느 단계인지 알려주는 배지. 본문이 이미 쓰던 어휘를 그대로 쓴다.
# 사이드바는 `(구현중)` 한 단계만 쓰고 성숙도는 여기서만 나눈다(docs/TODO.md 결정).
MATURITY_BADGES = {
    "draft": ":gray-badge[화면 초안]",
    "prototype": ":green-badge[인터랙티브 프로토타입]",
    "connected": "",
}


def pending_badge(subject: str) -> str:
    """아직 붙지 않은 원천을 알리는 배지.

    같은 뜻인데 화면마다 색이 갈렸다. 세 화면은 파랑, 한 화면은 주황이었다. 미연결은
    고장이 아니라 예정된 상태이므로 알림용 파랑으로 통일한다. 주황은 확보 상태색에서
    "경고" 를 뜻하므로 여기에 쓰면 다른 화면의 주황과 뜻이 어긋난다.
    """
    return f":blue-badge[{subject} 미연결]"


def page_badges(*marks: str) -> str:
    """배지 몇 개를 헤더의 한 줄로 합친다. 빈 배지는 버린다."""
    return " ".join(mark for mark in marks if mark)


def render_page_header(
    title: str,
    *,
    description: str | None = None,
    badges: str | None = None,
) -> None:
    """페이지 제목과 설명을 그린다.

    `title` 에 `(구현중)` 이 붙어 있으면 제목에서 떼어 배지로 보여준다. 제목 줄이
    짧아지고 미구현 여부가 색으로 먼저 읽힌다.
    """
    heading, implementing = _split_implementing(title)
    st.title(heading)
    _render_marks(implementing, badges, description)


def render_page_header_with_status(
    title: str,
    *,
    description: str | None = None,
    badges: str | None = None,
) -> DeltaGenerator:
    """제목 오른쪽에 진행 표시 자리를 둔 머리말. 그 자리를 쓸 `st.empty()` 를 돌려준다.

    진행 막대를 본문 흐름에 그대로 두면 뜨고 질 때마다 아래의 모든 것이 그만큼 위아래로
    밀린다. 차트를 보는 중에 그 움직임이 그대로 보인다. 제목 줄 안에 넣으면 줄 높이를
    제목이 잡고 있으므로 막대가 사라져도 아래가 움직이지 않는다.
    """
    heading, implementing = _split_implementing(title)
    # 가로 컨테이너가 아니라 컬럼으로 나눈다. **가로 컨테이너 안의 `h1` 은 Streamlit 이
    # 위아래 여백을 지운다.** 그러면 이 머리말을 쓰는 페이지만 제목이 그만큼 위로 올라가
    # 앱 헤더에 닿고, 같은 자리에 있어야 할 다른 페이지 제목과 눈높이가 어긋난다.
    # 컬럼은 그 여백을 그대로 두므로 제목 줄 높이가 다른 페이지와 같다.
    #
    # 두 `wrap=False` 가 각각 막는 것이 다르다. 컬럼 쪽은 진행 표시가 제목 아래로 접히는
    # 것을, 제목 쪽은 제목 자체가 두 줄이 되는 것을 막는다. 어느 쪽이든 접히면 막대가
    # 뜨고 질 때마다 아래 차트가 밀린다 — 이 함수가 막으려던 바로 그 움직임이다.
    title_column, status_column = st.columns(
        TITLE_STATUS_COLUMN_RATIO, vertical_alignment="center", wrap=False
    )
    title_column.title(heading, wrap=False)
    with status_column, st.container(width=STATUS_SLOT_WIDTH_PX):
        slot = st.empty()
    _render_marks(implementing, badges, description)
    return slot


def _render_marks(implementing: bool, badges: str | None, description: str | None) -> None:
    marks = [mark for mark in (":orange-badge[구현중]" if implementing else "", badges) if mark]
    if marks:
        st.markdown(" ".join(marks))
    if description:
        st.caption(description)


def _split_implementing(title: str) -> tuple[str, bool]:
    suffix = f" {IMPLEMENTING_SUFFIX}"
    if title.endswith(suffix):
        return title[: -len(suffix)], True
    return title, False
