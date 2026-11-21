# Purpose: 비교 GAP 의 계획 증감 글자 규칙과 비교 계획 CUSTOM 다시 짝짓기를 한 곳에 둔다.

"""계획 증감 글자.

HOME `Capa LOB 현황` 의 Density·Wafer 계획 칸은 값 위에 선행 B/O 증감을, 값 아래에 비교 시나리오와의
GAP 을 적는다. 입장 화면 Summary 도 같은 두 증감을 적는다 — **같은 부호·형식·숨김 규칙**이어야 두
화면의 숫자가 같은 말을 한다. 그래서 규칙을 그림 모듈(`components/home_lob_figures.py`)에서 이
순수 모듈로 옮겨 두 곳이 함께 쓴다.

- 증감이 `GAP_EPSILON` 보다 작으면 적지 않는다. 화면에 보이는 자릿수에서 달라지지 않은 칸까지
  `+0.00` 을 달면 무엇이 움직였는지 오히려 안 읽힌다.
- 형식 자릿수에서 0 으로 보이는 글자(`+0.0K`·`-0.00`)도 적지 않는다(`visible_gap`).
- 비교 계획은 현재 수율 · Chip 표로 환산하므로, 그 전에 계획 행의 CUSTOM 을 현재 표에 다시
  짝짓는다(`repair_comparison_plan_custom`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

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


# 비교 계획 행을 다시 짝짓는 두 단계의 키. 첫째는 현재 계획의 같은 Capa Code, 둘째는 현재 표의 제품.
CUSTOM_REPAIR_CODE_KEYS: Final = ("제품정보", "Stack", "Capa Code")
CUSTOM_REPAIR_PRODUCT_KEYS: Final = ("제품정보", "Stack")
_CUSTOM: Final = "CUSTOM"


def repair_comparison_plan_custom(
    comparison_plan: pd.DataFrame,
    current_plan: pd.DataFrame,
    current_tables: Sequence[pd.DataFrame],
) -> pd.DataFrame:
    """비교 계획 행의 CUSTOM 을 현재 표에 맞춰 다시 정한다 — 행 수 · 다른 칸은 그대로다.

    비교 계획(다른 리비전)은 현재 수율 · Chip 표로 환산한다. CUSTOM 을 싣기 전 리비전은 모든 행이
    빈 값 표지라 그대로는 현재 표와 짝이 없다. 그래서 행마다 늘 아래 차례로 다시 정한다.

    1. 현재 계획의 같은 (제품정보, Stack, Capa Code)에서 CUSTOM 이 하나로 정해지면 그 값.
    2. 아니면 현재 표(`current_tables` — 환산에 쓰는 수율 · Chip 표)에서 그 (제품정보, Stack)의
       CUSTOM 이 하나뿐이면 그 값.
    3. 아니면 원래 값. 그래도 현재 표와 짝이 없는 행은 환산의 제외 목록이 센다.

    CUSTOM 칸이 없는 계획은 그대로 돌려준다.
    """
    if _CUSTOM not in comparison_plan.columns or comparison_plan.empty:
        return comparison_plan
    by_code = _single_custom([current_plan], CUSTOM_REPAIR_CODE_KEYS)
    by_product = _single_custom(current_tables, CUSTOM_REPAIR_PRODUCT_KEYS)
    original = comparison_plan[_CUSTOM]
    chosen = (
        _looked_up(comparison_plan, by_code, CUSTOM_REPAIR_CODE_KEYS)
        .fillna(_looked_up(comparison_plan, by_product, CUSTOM_REPAIR_PRODUCT_KEYS))
        .fillna(original)
    )
    chosen = chosen.astype(original.dtype)
    if chosen.equals(original):
        return comparison_plan
    repaired = comparison_plan.copy()
    repaired[_CUSTOM] = chosen
    return repaired


def _single_custom(frames: Sequence[pd.DataFrame], keys: tuple[str, ...]) -> pd.DataFrame:
    """키마다 CUSTOM 이 하나뿐인 짝. 둘 이상이면 고르지 않고 뺀다."""
    columns = [*keys, _CUSTOM]
    parts = [
        frame.loc[:, columns].astype("string")
        for frame in frames
        if set(columns).issubset(frame.columns)
    ]
    if not parts:
        return pd.DataFrame({column: pd.Series(dtype="string") for column in columns})
    pairs = pd.concat(parts, ignore_index=True).dropna().drop_duplicates()
    counts = pairs.groupby(list(keys))[_CUSTOM].transform("nunique")
    return pairs.loc[counts.eq(1)].drop_duplicates(list(keys)).reset_index(drop=True)


def _looked_up(plan: pd.DataFrame, pairs: pd.DataFrame, keys: tuple[str, ...]) -> pd.Series:
    """계획 행마다 짝의 CUSTOM(없으면 NA). 계획의 행 차례 · 인덱스를 그대로 쓴다."""
    if not set(keys).issubset(plan.columns):
        return pd.Series(pd.NA, index=plan.index, dtype="string")
    matched = (
        plan.loc[:, list(keys)]
        .astype("string")
        .merge(pairs, how="left", on=list(keys), validate="many_to_one")
    )
    return pd.Series(matched[_CUSTOM].to_numpy(), index=plan.index, dtype="string")
