# Purpose: 확보·경고 판정 기준(비율)과 칸에 친 퍼센트를 사사오입 정수 퍼센트(값과 글자)로 바꾼다.

"""판정 기준의 정수 퍼센트.

판정 기준은 **정수 퍼센트**다(2026-11-01 사용자 결정 — 「기준확보율 입력을 110% 정수 기준으로」).
저장된 비율은 모두 소수점에서 **사사오입**(half-up)한 정수 T 로 읽는다 — 옛 관례로 반 칸 낮춰 적은
1.095·0.995 도 110·100 이다. 판정이 그 T 를 어떻게 쓰는지(확보율을 사사오입한 정수 % 가 T 이상)는
`securement_threshold` 가 정하고, 이 모듈은 비율 하나를 정수 하나(`threshold_percent`)와 글자 하나
(`threshold_percent_label` — 「110%」)로, 칸에 친 퍼센트 하나를 정수 하나(`whole_percent` — 109.5 →
110)로 바꿀 뿐이다.

파이썬 `round` 와 서식 `:.0%` 는 반을 짝수 쪽으로 가른다(108.5 → 108, 1.085 → 108%). 109.5·99.5 는
짝수가 위라 우연히 맞을 뿐이어서 둘 다 쓰지 않는다. 값 하나를 받아 하나를 돌려주므로 달마다 다른
기준이 와도 그대로 쓴다.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from math import isfinite

# 값이 아닌 기준(NaN·무한)을 적을 자리표시. 그리는 화면이 기준 한 칸 때문에 멈추면 안 된다.
MISSING_THRESHOLD_LABEL = "—"


def threshold_percent(ratio: float) -> int:
    """비율 기준(1.095)을 사사오입 정수 퍼센트(110)로 바꾼다. 값이 아니면(NaN·무한) `ValueError`.

    `Decimal(repr(ratio))` 로 사람이 적은 십진 값(1.095)을 그대로 잡는다 — `Decimal(1.095)` 는
    이진 근삿값 1.09499… 라 109 로 내려간다(`1.005 * 100` 도 100.49999… 다).
    """
    value = float(ratio)
    if not isfinite(value):
        raise ValueError(f"판정 기준이 숫자가 아닙니다: {ratio!r}")
    percent = (Decimal(repr(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(percent)


def whole_percent(percent: float) -> int:
    """칸에 친 퍼센트(109.5)를 사사오입한 정수 퍼센트(110)로 바꾼다. 값이 아니면 `ValueError`.

    판정 기준 숫자 칸(HOME 설정 › Preference 기본 두 칸 · 월별 표, 제약 시뮬레이션 · 개조 일정의
    기준 확보율)은 소수를 받아 이 한 규칙으로 읽는다(2026-11-01 사용자 결정 — 109.5 → 110, 99.5 →
    100). 정수 숫자 칸은 브라우저가 친 글을 `parseInt` 로 읽어 109.5 를 말없이 109 로 버렸다. 반은
    올린다 (`round` 의 짝수 쪽 가르기가 아니다 — 108.5 → 109).
    """
    value = float(percent)
    if not isfinite(value):
        raise ValueError(f"판정 기준이 숫자가 아닙니다: {percent!r}")
    return int(Decimal(repr(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def threshold_percent_label(ratio: float) -> str:
    """비율 기준(1.095)을 정수 퍼센트 글자(`"110%"`)로 바꾼다. 반은 올린다(`threshold_percent`)."""
    value = float(ratio)
    if not isfinite(value):
        return MISSING_THRESHOLD_LABEL
    return f"{threshold_percent(value)}%"


def boundary_percent_label(ratio: float) -> str:
    """기준 T% 의 판정 경계 글자(110% → 「109.5%」) — 사사오입해 T 가 되는 가장 작은 확보율.

    판정에 맞춰 대수를 셈한 식 줄(「가용 − 소요 × 109.5%」)이 곱한 값을 그대로 적을 때만 쓴다. 기준
    자체는 늘 `threshold_percent_label` 의 정수다.
    """
    value = float(ratio)
    if not isfinite(value):
        return MISSING_THRESHOLD_LABEL
    return f"{threshold_percent(value) - 0.5:g}%"
