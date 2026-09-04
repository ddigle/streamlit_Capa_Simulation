# Purpose: 조치가 필요한 지표를 한눈에 가려내도록 metric 카드에 상태색 띠를 붙인다.

"""Metric cards that carry their own severity.

지표 카드 80장이 전부 같은 흰 상자였다. "오늘 Flow 부족 3개" 와 "선택 경로 15개" 가
똑같이 생겨서, 봐야 할 숫자를 찾으려면 라벨을 하나씩 읽어야 했다.

카드 전체를 칠하지 않고 왼쪽에 상태색 띠만 세운다. 값 자체는 그대로 검은 글자로 남아
읽기 쉽고, 밀도 높은 화면에서 색면이 여러 장 겹쳐 시끄러워지는 것도 피한다. 색은 확보
상태색과 같은 토큰을 써서 표·차트와 같은 뜻으로 읽힌다.

`shortage_tone` 을 쓰면 "문제 건수" 라는 뜻이 숫자에서 바로 나온다. 0 이면 평상,
1 이상이면 경고다. 기준값을 새로 만들지 않고 "셌더니 있더라" 만 표시한다.
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

from capa_simulation.design import tokens

MetricTone = Literal["neutral", "good", "attention", "critical"]

# 확보 → 경고 → 부족 과 같은 토큰을 쓴다. 표의 셀 색과 카드의 띠가 같은 뜻이어야 한다.
TONE_COLORS: dict[str, str] = {
    "good": tokens.ACCENT,
    "attention": tokens.STATUS_WARNING,
    "critical": tokens.STATUS_SHORTAGE,
}

STRIPE_WIDTH_PX = 4


def shortage_tone(count: int) -> MetricTone:
    """문제 건수를 색으로 옮긴다. 0 이면 평상, 1 건이라도 있으면 경고다."""
    return "attention" if count > 0 else "neutral"


def render_status_metric(
    label: str,
    value: str,
    *,
    key: str,
    tone: MetricTone = "neutral",
    help: str | None = None,
) -> None:
    """상태색 띠가 붙은 metric 카드 하나를 그린다.

    `tone="neutral"` 은 기존 카드와 완전히 같은 모양이다. 색을 붙일 이유가 없는 지표에
    굳이 색을 붙이지 않기 위해 기본값으로 둔다.
    """
    color = TONE_COLORS.get(tone)
    if color is None:
        st.metric(label, value, border=True, help=help)
        return
    st.html(
        "\n".join(
            [
                "<style>",
                f'.st-key-{key} [data-testid="stMetric"] {{',
                f"    border-left: {STRIPE_WIDTH_PX}px solid {color} !important;",
                "}",
                "</style>",
            ]
        )
    )
    with st.container(key=key):
        st.metric(label, value, border=True, help=help)
