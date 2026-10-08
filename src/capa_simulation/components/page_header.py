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

from capa_simulation.navigation import DATA_PENDING_SUFFIX, IMPLEMENTING_SUFFIX

# 진행 표시 자리(`render_page_header_with_status`)의 컨테이너 키. Streamlit 은 이것을 `st-key-<키>`
# 클래스로 달고, 머리 띠 CSS(`app_header`)가 그 자리를 화면 맨 위 띠 안에 고정한다.
STATUS_SLOT_KEY = "page_header_status"

# 화면이 어느 단계인지 알려주는 배지. 본문이 이미 쓰던 어휘를 그대로 쓴다.
# 사이드바 접미는 둘(`(구현중)`·`(Data확보중)`)이고 본문 성숙도는 여기서 더 잘게 나눈다
# (docs/TODO.md 3-1 [결정]).
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
    show_status: bool = True,
) -> None:
    """페이지 제목과 설명을 그린다.

    `title` 에 `(구현중)` 이 붙어 있으면 제목에서 떼어 배지로 보여준다. 제목 줄이
    짧아지고 미구현 여부가 색으로 먼저 읽힌다. `show_status=False` 면 배지를 그리지 않는다 —
    `title` 은 그대로 사이드바 라벨과 같게 넘긴다(두 제목이 같다는 계약은 표기 유무와 무관하다).
    Space 현황이 그렇다(2026-10-01 사용자 결정 — 본문은 배치도가 쓸 자리다).
    """
    heading, status_badge = _split_status_suffix(title)
    st.title(heading)
    _render_marks(status_badge if show_status else None, badges, description)


def render_page_header_with_status(
    title: str,
    *,
    description: str | None = None,
    badges: str | None = None,
) -> DeltaGenerator:
    """진행 표시 자리를 둔 머리말. 그 자리를 쓸 `st.empty()` 를 돌려준다.

    그 자리는 본문이 아니라 **화면 맨 위 띠**(Streamlit 헤더, 왼쪽에 시나리오 두 줄·오른쪽에 툴바
    단추)에 앉는다 — 툴바 단추 바로 왼쪽이다(2026-10-08 사용자 결정). 자리를 잡는 CSS 는 띠의
    다른 규칙과 함께 `app_header` 가 보낸다(키 `STATUS_SLOT_KEY`).

    진행 막대를 본문 흐름에 그대로 두면 뜨고 질 때마다 아래의 모든 것이 그만큼 위아래로 밀린다.
    여기서는 컨테이너를 본문 흐름에서 빼서(`position: fixed`) 띠 위에 얹으므로, 막대가 뜨고 져도
    본문은 한 픽셀도 움직이지 않는다. 고정 배치된 칸은 flex 항목이 아니라 요소 간격도 먹지 않는다.
    제목은 다른 페이지와 같은 `st.title` 이다 — 자리가 본문 흐름 밖이라 제목 줄을 나눌 일이 없다.
    """
    heading, status_badge = _split_status_suffix(title)
    st.title(heading)
    with st.container(key=STATUS_SLOT_KEY):
        slot = st.empty()
    _render_marks(status_badge, badges, description)
    return slot


def _render_marks(status_badge: str | None, badges: str | None, description: str | None) -> None:
    marks = [mark for mark in (status_badge or "", badges) if mark]
    if marks:
        st.markdown(" ".join(marks))
    if description:
        st.caption(description)


def _split_status_suffix(title: str) -> tuple[str, str | None]:
    """사이드바 라벨의 상태 접미를 제목에서 떼어 배지 글자로 돌려준다.

    접미는 둘이다 — `(구현중)` 은 아직 못 만든 화면, `(Data확보중)` 은 화면은 다 만들었고
    연결할 데이터만 기다리는 화면이다. 사용자에게 뜻이 다르므로 배지 색도 가른다.
    """
    for suffix, badge in (
        (IMPLEMENTING_SUFFIX, ":orange-badge[구현중]"),
        (DATA_PENDING_SUFFIX, ":blue-badge[Data확보중]"),
    ):
        spaced = f" {suffix}"
        if title.endswith(spaced):
            return title[: -len(spaced)], badge
    return title, None
