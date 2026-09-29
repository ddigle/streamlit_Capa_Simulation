# Purpose: 적용하지 않은 편집이 남은 탭의 이름 옆에 점을 찍는다.

"""탭 이름 옆의 **미적용 점**(2026-09-29 사용자 결정 — 탭 목록 개선안 C).

적용 버튼을 표 위로 올려도, 고친 뒤 다른 탭으로 옮기면 그 탭에 적용하지 않은 값이 남았다는
사실이 화면에서 사라진다. 탭 이름 옆에 사이드바 `미저장 변경` 배지와 같은 주황 점을 찍어
「이 탭에 아직 적용하지 않은 것이 있다」를 어느 탭에서든 보이게 한다.

**라벨이 아니라 CSS 로 찍는다.** 탭 라벨은 `st.tabs` 의 위젯 id 계산에 들어간다 — 라벨에 점을
붙였다 떼면 그때마다 위젯이 새로 만들어져 열린 탭 기억이 흔들린다. `stateful_tabs` 의 `key` 는
`st-key-<key>` 클래스로 탭 묶음(`stTabs`)에 달리므로 그 묶음의 n 번째 탭 단추에 `::after` 로
점을 얹는다. 탭 안에 또 탭이 있으면 안쪽 탭 단추도 같은 묶음의 자손이라, 안쪽 탭 본문
(`stTabPanel`) 아래의 단추는 고르지 않는다.

**비공식 경로다.** `data-testid="stTab"`·`stTabPanel` 이 판올림에서 바뀌면 점이 **안 보일
뿐** 화면과 동작은 그대로다.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

import streamlit as st

from capa_simulation.design import tokens


def pending_tabs_style(key: str, labels: Sequence[str], pending: Collection[str]) -> str:
    """점을 찍을 탭의 CSS. 찍을 탭이 없으면 빈 문자열이다."""
    positions = [index + 1 for index, label in enumerate(labels) if label in pending]
    if not positions:
        return ""
    root = f".st-key-{key}"
    selectors = ",\n".join(
        f'{root} [data-testid="stTab"]:nth-child({position})'
        f':not({root} [data-testid="stTabPanel"] *)::after'
        for position in positions
    )
    return f"""
<style>
{selectors} {{
    content: "";
    display: inline-block;
    flex: none;
    width: 6px;
    height: 6px;
    margin-left: 6px;
    border-radius: 50%;
    background-color: {tokens.PENDING_MARK};
    vertical-align: middle;
}}
</style>
"""


def mark_pending_tabs(key: str, labels: Sequence[str], pending: Collection[str]) -> None:
    """`stateful_tabs(labels, key=key)` 의 탭 가운데 `pending` 에 든 탭 이름 옆에 점을 찍는다.

    **찍을 것이 없어도 빈 규칙을 매 회차 그린다.** 스타일만 든 `st.html` 은 본문이 아니라
    이벤트 칸에 들어가 자리를 차지하지 않는데, 같은 자리에 늘 무언가를 그려 두어야 편집을
    적용하거나 버린 다음 회차에 앞 회차의 점이 확실히 덮인다.
    """
    st.html(pending_tabs_style(key, labels, pending) or "<style></style>")
