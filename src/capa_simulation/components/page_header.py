# Purpose: 모든 페이지가 같은 모양의 제목·설명·상태 배지를 그리도록 한다.

"""One page header for every screen.

제목 다음에 설명 한 줄이 오는 형태는 14개 페이지 중 11개가 이미 쓰고 있었지만 나머지는
설명이 없거나 곧바로 탭이 이어져 페이지마다 첫인상이 달랐다. 여기로 모아 간격과 배지
표기를 한 번에 정한다.

`(구현중)` 은 제목 문자열에 섞어 두지 않고 배지로 뽑는다. 사이드바 라벨은 여전히
`navigation.py` 가 소유하며 그쪽 표기와 어긋나면 테스트가 잡는다.

**큰 제목은 화면에서 숨고 인쇄·읽기 도구에 남는다**(2026-10-24 사용자 결정). 머리 띠 아래 화면 탭
줄(`components/page_tabs.py`)이 지금 화면의 이름을 말한다. 제목은 그대로 `st.title` 로 내보내되 키
컨테이너(`PAGE_TITLE_KEY`)에 담고, 껍데기 스타일(`app_header.SHELL_STYLE`)이 화면에서만 그 칸을
시각적으로 숨긴다(sr-only — `display: none` 이 아니라 h1 이 읽기 도구에 남는다). 인쇄에는 보인다.
배지·설명 줄은 화면에 그대로 둔다.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.navigation import IMPLEMENTING_SUFFIX

# 진행 표시 자리(`render_page_header_with_status`)의 컨테이너 키. Streamlit 은 이것을 `st-key-<키>`
# 클래스로 달고, 머리 띠 CSS(`app_header`)가 그 자리를 화면 맨 위 띠 안에 고정한다.
STATUS_SLOT_KEY = "page_header_status"
# 큰 제목(`st.title`)을 담는 컨테이너의 키. 껍데기 스타일이 이 키로 화면에서만 제목을 숨긴다 — CSS
# 로 고르는 컨테이너 key 는 계약이다(AGENTS 9장). 한 회차에 한 번만 그린다.
PAGE_TITLE_KEY = "page_header_title"
# 제목 칸과 그 끝 칸(`trailing` — HOME 의 주요 Case 칩 셋)을 든 컨테이너의 키. 두 칸의 폭은 비율이
# 아니라 글자에서 나온다(`_title_row_style`).
TITLE_ROW_KEY = "page_header_title_row"

# 화면이 어느 단계인지 알려주는 배지. 본문이 이미 쓰던 어휘를 그대로 쓴다.
# 사이드바 접미는 `(구현중)` 하나이고 본문 성숙도는 여기서 더 잘게 나눈다
# (docs/TODO.md 결정 기록, 옛 3-1).
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
    trailing: Callable[[], None] | None = None,
) -> None:
    """페이지 제목과 설명을 그린다.

    `title` 에 `(구현중)` 이 붙어 있으면 제목에서 떼어 배지로 보여준다. 제목 줄이
    짧아지고 미구현 여부가 색으로 먼저 읽힌다. `show_status=False` 면 배지를 그리지 않는다 —
    `title` 은 그대로 사이드바 라벨과 같게 넘긴다(두 제목이 같다는 계약은 표기 유무와 무관하다).
    Space 현황이 그렇다(2026-10-01 사용자 결정 — 본문은 배치도가 쓸 자리다).

    `trailing` 을 주면 제목 줄 끝 칸에 그것을 그린다 — 가용설비 현황 「설정」·필요 단축 일정
    「Qual 마감 계산기」 단추. 칸 나누기·폭은 `render_page_header_with_status` 의 끝 칸과 같다
    (`_render_title_row`).

    제목은 화면에서 숨고(탭 줄이 이름을 말한다) 인쇄·읽기 도구에 남는다(모듈 설명).
    """
    heading, status_badge = _split_status_suffix(title)
    _render_title_row(heading, trailing)
    _render_marks(status_badge if show_status else None, badges, description)


def render_page_header_with_status(
    title: str,
    *,
    description: str | None = None,
    badges: str | None = None,
    trailing: Callable[[], None] | None = None,
) -> DeltaGenerator:
    """진행 표시 자리를 둔 머리말. 그 자리를 쓸 `st.empty()` 를 돌려준다.

    `trailing` 을 주면 제목 줄 끝 칸에 그것을 그린다(HOME 의 주요 Case 칩 —
    `home_main_case_chips`). 제목과 끝 칸은 가로 컨테이너가 아니라 `st.columns` 로 나눈다 —
    가로 컨테이너 안의 `st.title` 은 Streamlit 이 `h1` 위아래 여백을 지워 제목이 머리 띠에
    올라붙는다(AGENTS 9장). 칼럼은 여백을 그대로 둬 제목 줄 높이가 다른 페이지와 같다. 두 칸의
    폭은 비율이 아니라 글자 폭이다(`_title_row_style`). 화면에서는 제목이 숨어(흐름에서 빠진다)
    끝 칸만 오른쪽 끝에 선다. 제목이 보이는 인쇄에서는 둘이 한 줄에 들면 끝 칸이 오른쪽 끝에
    붙고, 안 들면 끝 칸이 통째로 제목 밑 오른쪽으로 내려간다. 비율로 나누면 사이드바를 편 좁은
    화면에서 제목이 두 줄로 접히고 칩 줄이 끝 칸을 넘쳐 제목 쪽으로 밀려 들었다.

    그 자리는 본문이 아니라 **화면 맨 위 띠**(Streamlit 헤더, 왼쪽에 시나리오 두 줄·오른쪽에 툴바
    단추)에 앉는다 — 툴바 단추 바로 왼쪽이다(2026-10-08 사용자 결정). 자리를 잡는 CSS 는 띠의
    다른 규칙과 함께 `app_header` 가 보낸다(키 `STATUS_SLOT_KEY`).

    진행 막대를 본문 흐름에 그대로 두면 뜨고 질 때마다 아래의 모든 것이 그만큼 위아래로 밀린다.
    여기서는 컨테이너를 본문 흐름에서 빼서(`position: fixed`) 띠 위에 얹으므로, 막대가 뜨고 져도
    본문은 한 픽셀도 움직이지 않는다. 고정 배치된 칸은 flex 항목이 아니라 요소 간격도 먹지 않는다.
    제목은 다른 페이지와 같은 `st.title` 이다 — 진행 자리가 본문 흐름 밖이라 그것 때문에 제목 줄을
    나누지는 않는다(나누는 것은 `trailing` 뿐이다).

    제목은 화면에서 숨고(탭 줄이 이름을 말한다) 인쇄·읽기 도구에 남는다 — 제목 줄에서는 끝 칸만
    오른쪽 끝에 보인다(모듈 설명).
    """
    heading, status_badge = _split_status_suffix(title)
    _render_title_row(heading, trailing)
    with st.container(key=STATUS_SLOT_KEY):
        slot = st.empty()
    _render_marks(status_badge, badges, description)
    return slot


def _render_title_row(heading: str, trailing: Callable[[], None] | None) -> None:
    """큰 제목, 또는 제목과 끝 칸(`trailing`)을 나눈 제목 줄. 끝 칸이 있으면 늘 같은 꼴로 그린다
    (스타일만 든 `st.html` 하나 — 이벤트 칸 자리 수가 회차마다 같다)."""
    if trailing is None:
        _render_title(heading)
        return
    with st.container(key=TITLE_ROW_KEY):
        st.html(_title_row_style())
        title_column, trailing_column = st.columns(2, vertical_alignment="center")
        with title_column:
            _render_title(heading)
        with trailing_column:
            trailing()


def _title_row_style() -> str:
    """제목 칸·끝 칸의 폭을 글자에서 낸다 — 비율(`st.columns` 의 칸 폭)을 덮는다.

    제목 칸은 글자 폭에서 자라기만 하고(`flex: 1 1 auto`), 끝 칸은 내용 폭 그대로 오른쪽 끝에 붙는다
    (`margin-left: auto`). 화면에서는 제목이 sr-only 로 흐름에서 빠져 제목 칸이 비고 끝 칸만
    오른쪽 끝에 선다 — 아래 줄 바꿈은 제목이 보이는 인쇄의 이야기다. 칸 묶음은 Streamlit 이 이미
    `flex-wrap: wrap` 이라 두 칸이 한 줄에 안 들면 끝 칸이 통째로 다음 줄로 내려가고, 그때도
    오른쪽 끝이다 — 640px 미만에서 Streamlit 이 칸을 쌓을 때와 같은 꼴이다. 줄을 나누는 기준은 두
    칸의 글자 폭이라 제목은 접히지 않는다(제목 칸만으로도 좁은 화면이면 그때만 접힌다 —
    `min-width: 0`, 가로 넘침이 없다). 고르는 것은 이 컨테이너 바로 밑 칸 묶음뿐이다(`>` — 끝 칸
    안의 다른 가로 묶음은 건드리지 않는다). 스타일만 든 `st.html` 이라 본문 자리를 먹지 않는다.
    """
    columns = (
        f'.st-key-{TITLE_ROW_KEY} > [data-testid="stLayoutWrapper"]'
        ' > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]'
    )
    return (
        "<style>"
        f"{columns}:first-child {{ flex: 1 1 auto; width: auto; min-width: 0; }}\n"
        f"{columns}:last-child {{ flex: 0 1 auto; width: auto; min-width: 0; margin-left: auto; }}"
        "</style>"
    )


def _render_title(heading: str) -> None:
    """큰 제목. 키 칸 안에 담아 화면에서만 숨긴다(`app_header.SHELL_STYLE`, 인쇄에는 보인다)."""
    with st.container(key=PAGE_TITLE_KEY):
        st.title(heading)


def _render_marks(status_badge: str | None, badges: str | None, description: str | None) -> None:
    marks = [mark for mark in (status_badge or "", badges) if mark]
    if marks:
        st.markdown(" ".join(marks))
    if description:
        st.caption(description)


def _split_status_suffix(title: str) -> tuple[str, str | None]:
    """사이드바 라벨의 상태 접미 `(구현중)` 을 제목에서 떼어 배지 글자로 돌려준다.

    접미는 아직 못 만든 화면에만 단다. 데이터만 기다리던 화면의 `(Data확보중)` 은 걷었다 —
    운영 화면이라 딱지가 오히려 덜 된 화면처럼 읽혔다(2026-10-19 사용자 요청).
    """
    spaced = f" {IMPLEMENTING_SUFFIX}"
    if title.endswith(spaced):
        return title[: -len(spaced)], ":orange-badge[구현중]"
    return title, None
