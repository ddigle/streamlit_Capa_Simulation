# Purpose: 확보·경고 판정 기준(비율)을 화면에 적을 정수 퍼센트 글자로 바꾼다.

"""판정 기준의 **표시** 글자.

기준 109.5%·99.5% 는 아슬아슬하게 모자란 공정도 기준을 채운 것으로 넣으려고 반 칸 낮춘
값이고, 업무의 원래 기준은 110%·100% 다(2026-10-03 사용자 결정). 그래서 화면에 기준을 적는
곳은 모두 소수점에서 **사사오입**(half-up)한 정수 퍼센트를 쓴다 — 파이썬 `round` 와 서식
`:.0%` 는 반을 짝수 쪽으로 가른다(108.5 → 108, 1.085 → 108%). 109.5·99.5 는 짝수가 위라 우연히
맞을 뿐이어서 둘 다 쓰지 않는다.

바뀌는 것은 **글자뿐**이다. 판정(`capacity_status`·`securement_rate`), 저장값, 기준을 고치는
입력 칸, 차트의 기준선 **위치**는 정확한 값을 그대로 쓴다 — 109.7% 확보 막대는 그 선 위에
선다. 값 하나를 받아 글자 하나를 돌려주므로 달마다 다른 기준이 와도 그대로 쓴다.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from math import isfinite

# 값이 아닌 기준(NaN·무한)을 적을 자리표시. 그리는 화면이 기준 한 칸 때문에 멈추면 안 된다.
MISSING_THRESHOLD_LABEL = "—"


def threshold_percent_label(ratio: float) -> str:
    """비율 기준(1.095)을 정수 퍼센트 글자(`"110%"`)로 바꾼다. 반은 올린다.

    `Decimal(repr(ratio))` 로 사람이 적은 십진 값(1.095)을 그대로 잡는다 — `Decimal(1.095)` 는
    이진 근삿값 1.09499… 라 109% 로 내려간다(`1.005 * 100` 도 100.49999… 다).
    """
    value = float(ratio)
    if not isfinite(value):
        return MISSING_THRESHOLD_LABEL
    percent = (Decimal(repr(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(percent)}%"
