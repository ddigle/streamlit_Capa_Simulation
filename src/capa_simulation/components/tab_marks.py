# Purpose: 적용하지 않은 편집이 남은 탭·종류 단추의 이름 옆에 점을 찍는다.

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

**탭 이름 곁 수 표지도 같은 길이다**(`mark_tab_counts` — Admin 「알림 모음」 의 알림 수, 2026-11-09
사용자 보드 T7 — 탭 안 「알림 n건」 줄 대신). 0 이면 표지를 찍지 않는다. 수는 글자라 색만으로 뜻을
나르지 않는다(설계 규칙 UI-ACC-03).

**종류 단추(`st.segmented_control`)에도 같은 점을 찍는다**(`mark_pending_segments` — 기준 정보 종류
단추, 2026-11-02 편집 표 횡전개). 단추 글도 위젯 값이라 점은 CSS 로 얹는다. 1.63 의 segmented
control 은 key 칸(`st-key-<key>`) 아래 `[data-testid="stButtonGroup"]` 안에 단추(`role="radio"`)를
형제로 늘어놓으므로 그 n 번째 단추에 `::after` 를 건다. 이것도 비공식 경로라 판올림에서 바뀌면 점이
안 보일 뿐이다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

import streamlit as st

from capa_simulation.design import tokens


def _dot_rule(selectors: str) -> str:
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


def pending_tabs_style(key: str, labels: Sequence[str], pending: Collection[str]) -> str:
    """점을 찍을 탭의 CSS. 찍을 탭이 없으면 빈 문자열이다."""
    positions = [index + 1 for index, label in enumerate(labels) if label in pending]
    if not positions:
        return ""
    root = f".st-key-{key}"
    return _dot_rule(
        ",\n".join(
            f'{root} [data-testid="stTab"]:nth-child({position})'
            f':not({root} [data-testid="stTabPanel"] *)::after'
            for position in positions
        )
    )


def pending_segments_style(key: str, options: Sequence[str], pending: Collection[str]) -> str:
    """점을 찍을 종류 단추의 CSS(`options` 는 단추 차례의 선택지 값). 찍을 단추가 없으면 빈 글자."""
    positions = [index + 1 for index, option in enumerate(options) if option in pending]
    if not positions:
        return ""
    root = f'.st-key-{key} [data-testid="stButtonGroup"]'
    return _dot_rule(
        ",\n".join(
            f'{root} [role="radio"]:nth-of-type({position})::after' for position in positions
        )
    )


def tab_counts_style(
    key: str, labels: Sequence[str], counts: Mapping[str, int], *, color: str
) -> str:
    """탭 이름 곁 수 표지의 CSS — `counts` 의 수가 1 이상인 탭만. 찍을 탭이 없으면 빈 글자."""
    root = f".st-key-{key}"
    shown = [
        (index + 1, counts[label]) for index, label in enumerate(labels) if counts.get(label, 0) > 0
    ]
    if not shown:
        return ""

    def tab(position: int) -> str:
        return (
            f'{root} [data-testid="stTab"]:nth-child({position})'
            f':not({root} [data-testid="stTabPanel"] *)::after'
        )

    selectors = ",\n".join(tab(position) for position, _ in shown)
    numbers = "\n".join(f'{tab(position)} {{ content: "{count:d}"; }}' for position, count in shown)
    return f"""
<style>
{selectors} {{
    display: inline-block;
    flex: none;
    min-width: 1.25rem;
    margin-left: 6px;
    padding: 0 6px;
    border: 1px solid {color};
    border-radius: 999px;
    color: {color};
    font-size: 0.75rem;
    font-weight: 600;
    line-height: 1.125rem;
    text-align: center;
}}
{numbers}
</style>
"""


def mark_tab_counts(
    key: str, labels: Sequence[str], counts: Mapping[str, int], *, color: str
) -> None:
    """`stateful_tabs(labels, key=key)` 의 탭 이름 곁에 수 표지를 찍는다(0 이면 없음).

    점과 같은 까닭으로 찍을 것이 없어도 빈 규칙을 매 회차 그린다(`mark_pending_tabs`)."""
    st.html(tab_counts_style(key, labels, counts, color=color) or "<style></style>")


def mark_pending_segments(key: str, options: Sequence[str], pending: Collection[str]) -> None:
    """`st.segmented_control(options, key=key)` 의 단추 가운데 `pending` 에 든 단추 옆에 점을
    찍는다.

    탭 점과 같은 까닭으로 찍을 것이 없어도 빈 규칙을 매 회차 그린다(`mark_pending_tabs`)."""
    st.html(pending_segments_style(key, options, pending) or "<style></style>")


def mark_pending_tabs(key: str, labels: Sequence[str], pending: Collection[str]) -> None:
    """`stateful_tabs(labels, key=key)` 의 탭 가운데 `pending` 에 든 탭 이름 옆에 점을 찍는다.

    **찍을 것이 없어도 빈 규칙을 매 회차 그린다.** 스타일만 든 `st.html` 은 본문이 아니라
    이벤트 칸에 들어가 자리를 차지하지 않는데, 같은 자리에 늘 무언가를 그려 두어야 편집을
    적용하거나 버린 다음 회차에 앞 회차의 점이 확실히 덮인다.
    """
    st.html(pending_tabs_style(key, labels, pending) or "<style></style>")
