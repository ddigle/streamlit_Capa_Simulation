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


def stateful_tabs(labels: Sequence[str], *, key: str) -> Sequence[OpenTab]:
    """열린 탭을 서버가 알 수 있는 `st.tabs` 를 만든다.

    `on_change="rerun"` 이 없으면 `key` 를 줘도 `tab.open` 은 계속 `None` 이다. 둘을 함께
    줘야 위젯이 된다. 탭을 누를 때 rerun 이 한 번 도는 대신, 닫힌 탭의 그림을 그리지 않게
    되어 전체로는 하는 일이 줄어든다.
    """
    return st.tabs(list(labels), key=key, on_change="rerun")


def tab_is_hidden(tab: OpenTab | None) -> bool:
    """이 탭이 지금 확실히 안 보이는가.

    `None` 은 "모른다" 다. `st.tabs` 에 `key`·`on_change` 를 주지 않았거나 탭 밖에서
    부른 경우인데, 모를 때 건너뛰면 화면이 비어 버리므로 보이는 쪽으로 판단한다.
    """
    return tab is not None and tab.open is False
