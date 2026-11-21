# Purpose: 원천 CUSTOM 을 제품 구분 키 값으로 맞추는 파생 경계(공백 · 빈 값 · 대소문자)를 고정한다.

"""CUSTOM 키 값 정규화.

원천 `CUSTOM` 은 같은 제품의 부품을 가르는 값이다. 빈 값을 NA 로 두면 조인 · 접기에서 행이 빠지거나
한 줄로 접히므로 파생 경계에서 한 번 `CUSTOM_BLANK` 로 세운다. 시험은 표지 글자를 따로 적지 않는다.
"""

from __future__ import annotations

import pandas as pd
from test_core_data_pipeline import _core_data_row

from capa_simulation.services.core_data_derivation import (
    ACTIVE_CORE_COLUMNS,
    CUSTOM_BLANK,
    build_q_core_data,
    normalize_custom_values,
)


def test_blank_custom_values_become_the_blank_marker() -> None:
    """NULL · 빈 글자 · 공백뿐인 값은 모두 같은 표지 하나가 된다."""
    values = pd.Series([None, "", "   ", pd.NA], dtype="object")

    assert normalize_custom_values(values).tolist() == [CUSTOM_BLANK] * 4


def test_surrounding_whitespace_is_stripped_and_values_are_kept() -> None:
    """앞뒤 공백만 떼고 값은 원천 글자 그대로다."""
    values = pd.Series([" DEMO_CUSTOM_A ", "DEMO_CUSTOM_B"], dtype="string")

    assert normalize_custom_values(values).tolist() == ["DEMO_CUSTOM_A", "DEMO_CUSTOM_B"]


def test_case_variants_are_unified_to_the_most_used_spelling() -> None:
    """대소문자만 다른 표기는 가장 많이 쓰인 표기로 모인다 — 한 부품이 두 키로 갈리지 않는다."""
    values = pd.Series(["DEMO_CUSTOM_A", "demo_custom_a", "DEMO_CUSTOM_A"], dtype="string")

    assert normalize_custom_values(values).tolist() == ["DEMO_CUSTOM_A"] * 3


def test_the_blank_marker_is_not_a_pandas_default_missing_value() -> None:
    """표지가 CSV · 붙여넣기 왕복에서 빈 값으로 읽히지 않는다."""
    import io

    read = pd.read_csv(io.StringIO(f"CUSTOM\n{CUSTOM_BLANK}\n"), na_values=[""], dtype="string")

    assert read["CUSTOM"].tolist() == [CUSTOM_BLANK]


def test_the_derivation_boundary_carries_the_normalized_custom() -> None:
    """작업 프레임이 CUSTOM 을 싣고, 빈 원천 값은 표지가 된다."""
    blank = _core_data_row()
    blank["CUSTOM"] = pd.Series(["  "], dtype="string")
    padded = _core_data_row()
    padded["CUSTOM"] = pd.Series([" DEMO_CUSTOM_A "], dtype="string")

    assert "CUSTOM" in ACTIVE_CORE_COLUMNS
    assert build_q_core_data(blank)["CUSTOM"].tolist() == [CUSTOM_BLANK]
    assert build_q_core_data(padded)["CUSTOM"].tolist() == ["DEMO_CUSTOM_A"]
