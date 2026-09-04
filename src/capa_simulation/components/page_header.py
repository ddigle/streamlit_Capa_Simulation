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

from capa_simulation.navigation import IMPLEMENTING_SUFFIX

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
