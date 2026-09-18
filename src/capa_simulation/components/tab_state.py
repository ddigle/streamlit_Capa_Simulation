# Purpose: 탭이 지금 화면에 보이는지를 서버가 알 수 있게 만들고, 그 판정을 한 곳에 둔다.

"""Server-side knowledge of which tab is currently open.

`st.tabs` 는 기본적으로 **모든 탭의 본문을 한 번에 그려 두고** 비활성 탭만
`display: none` 으로 감춘다. 서버는 어느 탭이 열렸는지 모르고 `tab.open` 도 `None` 이다.
`key` 와 `on_change="rerun"` 을 함께 주면 탭이 위젯이 되어, **첫 렌더부터** `tab.open` 이
`True`/`False` 로 확정되고 탭을 누를 때 rerun 이 돈다. 실측으로 확인한 동작이다.

이것이 필요한 이유는 Plotly 때문이다. 숨겨진 요소 안에서는 SVG 글자 폭 측정이 0 이라
`go.Table` 이 가운데 정렬 보정을 못 하고, 헤더가 셀 중앙에서 글자 폭의 절반만큼 밀린다.
`staticPlot` 이라 나중에 보이게 되어도 다시 그리지 않아 그대로 남는다. 사용자가 신고한
"년월 헤더가 셀 구석에 처박힌다" 가 이것이다.

**숨은 탭에서는 위젯이 아니라 그림만 건너뛴다.** 본문을 통째로 건너뛰면 그 안의
`multiselect` 같은 위젯이 렌더되지 않아 Streamlit 이 선택값을 버린다. 탭을 오갈 때마다
필터가 초기화되는 것이 그 결과다.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol

import streamlit as st


class OpenTab(Protocol):
    """`st.tabs` 가 돌려주는 탭 컨테이너 중 이 모듈이 쓰는 부분만."""

    @property
    def open(self) -> bool | None: ...

    def __enter__(self) -> OpenTab: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


def remembered_tab_key(key: str) -> str:
    """탭 위젯 키에 딸린 **위젯이 아닌** 기억 칸의 이름."""
    return f"{key}__remembered"


def stateful_tabs(labels: Sequence[str], *, key: str) -> Sequence[OpenTab]:
    """열린 탭을 서버가 알 수 있는 `st.tabs` 를 만들고, 그 선택을 기억한다.

    `on_change="rerun"` 이 없으면 `key` 를 줘도 `tab.open` 은 계속 `None` 이다. 둘을 함께
    줘야 위젯이 된다. 탭을 누를 때 rerun 이 한 번 도는 대신, 닫힌 탭의 그림을 그리지 않게
    되어 전체로는 하는 일이 줄어든다.

    **기억이 필요한 이유는 사이드바다.** 「불러오기」는 사이드바에서 `st.rerun()` 을 부르고,
    그 호출은 그 자리에서 실행을 끊는다 — 페이지 본문은 그 회차에 아예 돌지 않는다.
    Streamlit 은 한 회차에 만들어지지 않은 위젯의 값을 버리므로, 효율 탭을 보고 있다가
    시나리오를 바꾸면 첫 탭으로 돌아간다. 실측으로 확인한 동작이다.

    위젯이 아닌 칸에 열린 탭을 적어 두고, 위젯 값이 사라졌을 때만 되돌려 놓는다.
    `st.tabs` 의 `default` 인자는 쓰지 않는다 — 그 값이 위젯 id 계산에 들어가서, 탭을
    옮길 때마다 id 가 바뀌어 위젯이 통째로 새로 만들어진다(그래서 선택이 또 사라진다).

    드는 비용은 rerun 한 번에 딕셔너리 조회 한 번과 문자열 쓰기 한 번이다. 오히려 줄어드는
    쪽이 크다 — 돌아간 첫 탭을 그린 뒤 사용자가 제 탭을 다시 누르면 무거운 그림을 두 번
    그리게 되는데, 기억하면 한 번만 그린다.
    """
    memory = remembered_tab_key(key)
    remembered = st.session_state.get(memory)
    if key not in st.session_state and isinstance(remembered, str) and remembered in labels:
        st.session_state[key] = remembered
    tabs = st.tabs(list(labels), key=key, on_change="rerun")
    for label, tab in zip(labels, tabs, strict=True):
        if tab.open:
            st.session_state[memory] = label
            break
    return tabs


def tab_is_hidden(tab: OpenTab | None) -> bool:
    """이 탭이 지금 확실히 안 보이는가.

    `None` 은 "모른다" 다. `st.tabs` 에 `key`·`on_change` 를 주지 않았거나 탭 밖에서
    부른 경우인데, 모를 때 건너뛰면 화면이 비어 버리므로 보이는 쪽으로 판단한다.
    """
    return tab is not None and tab.open is False
