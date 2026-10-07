# Purpose: 계획 증감 글자(선행 B/O 전후·비교 GAP)의 형식과 0 근처를 적지 않는 규칙을 한 곳에 둔다.

"""계획 증감 글자.

HOME `Capa LOB 현황` 의 Density·Wafer 계획 칸은 값 위에 선행 B/O 증감을, 값 아래에 비교 시나리오와의
GAP 을 적는다. 입장 화면 Summary 도 같은 두 증감을 적는다 — **같은 부호·형식·숨김 규칙**이어야 두
화면의 숫자가 같은 말을 한다. 그래서 규칙을 그림 모듈(`components/home_lob_figures.py`)에서 이
순수 모듈로 옮겨 두 곳이 함께 쓴다.

- 증감이 `GAP_EPSILON` 보다 작으면 적지 않는다. 화면에 보이는 자릿수에서 달라지지 않은 칸까지
  `+0.00` 을 달면 무엇이 움직였는지 오히려 안 읽힌다.
- 형식 자릿수에서 0 으로 보이는 글자(`+0.0K`·`-0.00`)도 적지 않는다(`visible_gap`).
"""

from __future__ import annotations

import math

import pandas as pd

# 증감이 이 값보다 작으면 적지 않는다(소수 둘째 자리 형식에 맞춘 값).
GAP_EPSILON = 5e-3
# Density(억Gb) 증감의 글자.
DENSITY_GAP_FORMAT = "{:+,.2f}"
# Wafer 계획 증감의 글자(천 매 단위). 값 칸(`2K`)과 같은 0 자리로 쓰면 5~499 매가 `+0K`·`-0K` 로
# 찍혀 0 이 아닌 증감이 0 으로 읽혔다(2026-10-01 브라우저 점검). 한 자리를 더 쓰고, 그 자리에서도
# 0 으로 보이는 증감(50 매 미만)은 `visible_gap` 이 적지 않는다.
WAFER_GAP_FORMAT = "{:+,.1f}K"
# Wafer 증감은 매 단위 차이를 이만큼 나눠 천 매로 적는다.
WAFER_GAP_SCALE = 1_000


def visible_gap(text: str) -> str:
    """증감 글자 하나. 형식 자릿수에서 0 으로 보이면(`+0.0K`·`-0.00`) 적지 않는다.

    `GAP_EPSILON` 은 소수 둘째 자리 형식에 맞춘 값이라 자릿수가 다른 형식에는 맞지 않는다.
    글자로 판정하면 형식이 무엇이든 「0 이 아닌 증감이 0 으로 찍히는」 칸이 생기지 않는다.
    """
    return text if any(character in "123456789" for character in text) else ""


def format_gap(difference: float | None, number_format: str, *, scale: float = 1.0) -> str:
    """증감 하나의 글자. 값이 없거나 0 으로 보이면 빈 글자다."""
    if difference is None:
        return ""
    value = float(difference) / scale
    if math.isnan(value) or abs(value) < GAP_EPSILON:
        return ""
    return visible_gap(number_format.format(value))


def plan_gap_texts(
    current: pd.DataFrame,
    baseline: pd.DataFrame | None,
    column: str,
    number_format: str,
    *,
    scale: float = 1.0,
) -> list[str] | None:
    """칸마다 적을 증감 문구. 기준이 없거나 달라진 칸이 없으면 `None` 이다.

    두 프레임은 같은 칸 차례로 맞춰 둔 것이어야 한다(행 차례로 뺀다).
    """
    if baseline is None or column not in current.columns or column not in baseline.columns:
        return None
    differences = (
        pd.to_numeric(current[column], errors="coerce").to_numpy()
        - pd.to_numeric(baseline[column], errors="coerce").to_numpy()
    )
    gaps = [format_gap(float(value), number_format, scale=scale) for value in differences]
    return gaps if any(gaps) else None
