# Purpose: 원천 CUSTOM 을 제품 구분 키 값으로 맞추는 규칙(공백 · 빈 값 표지 · 대소문자)을 고정한다.

"""CUSTOM 키 값 정규화.

원천 `CUSTOM` 은 같은 제품의 부품을 가르는 값이다. 빈 값을 NA 로 두면 조인 · 접기에서 행이 빠지거나
한 줄로 접히므로 파생 경계에서 한 번 `CUSTOM_BLANK` 로 세운다. 시험은 표지 글자를 따로 적지 않는다.
표지는 편집표 붙여넣기 · CSV 왕복에서도 키 값으로 남아야 한다. 끝단 시험(두 부품이 접히지 않음 ·
CUSTOM 이 한 값이면 결과가 지금과 같음)은 RQ 표 · 계산 키에 CUSTOM 을 올리는 커밋에서 더한다.
"""

from __future__ import annotations

import io

import pandas as pd
from test_core_data_pipeline import _core_data_row

from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.core_data_derivation import (
    ACTIVE_CORE_COLUMNS,
    CUSTOM_BLANK,
    build_q_core_data,
    normalize_custom_values,
)
from capa_simulation.services.reference_csv import (
    parse_reference_edit_clipboard,
    reference_edit_csv_bytes,
    strip_excel_text_guard,
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


def test_the_blank_marker_survives_the_real_paste_path() -> None:
    """붙여넣기 입구(`parse_clipboard_table`)는 표지를 빈 값으로 읽지 않는다."""
    content = f"제품정보\tCUSTOM\nDEMO_P1\t{CUSTOM_BLANK}\n"

    assert parse_clipboard_table(content, "RQ_YLD")["CUSTOM"].tolist() == [CUSTOM_BLANK]


def test_the_blank_marker_survives_the_edit_csv_round_trip() -> None:
    """편집표 양식을 내려받아 Excel 로 열었다 다시 붙여넣어도 표지가 키 값으로 남는다.

    표지가 빈 값으로 읽히면 「분류 칸이 비어 있는 행」 으로 붙여넣기가 막힌다(`_normalized_keys`).
    """
    template = pd.DataFrame(
        {
            "제품정보": ["DEMO_P1", "DEMO_P1"],
            "Stack": ["8H", "8H"],
            "CUSTOM": [CUSTOM_BLANK, "DEMO_CUSTOM_A"],
            "202701": [0.9, 0.8],
        }
    )
    key_columns = ["제품정보", "Stack", "CUSTOM"]
    downloaded = reference_edit_csv_bytes(template, key_columns).decode("utf-8-sig")
    # Excel 로 열면 `="…"` 껍데기를 계산해 안의 글자만 보이고, 그 셀을 복사하면 그 글자가 온다.
    opened = pd.read_csv(io.StringIO(downloaded), dtype="object", keep_default_na=False)
    opened["CUSTOM"] = opened["CUSTOM"].map(strip_excel_text_guard)

    result = parse_reference_edit_clipboard(
        opened.to_csv(index=False, sep="\t"), template, key_columns, "RQ_YLD"
    )

    assert result["CUSTOM"].tolist() == [CUSTOM_BLANK, "DEMO_CUSTOM_A"]


def test_the_derivation_boundary_carries_the_normalized_custom() -> None:
    """작업 프레임이 CUSTOM 을 싣고, 빈 원천 값은 표지가 된다."""
    blank = _core_data_row()
    blank["CUSTOM"] = pd.Series(["  "], dtype="string")
    padded = _core_data_row()
    padded["CUSTOM"] = pd.Series([" DEMO_CUSTOM_A "], dtype="string")

    assert "CUSTOM" in ACTIVE_CORE_COLUMNS
    assert build_q_core_data(blank)["CUSTOM"].tolist() == [CUSTOM_BLANK]
    assert build_q_core_data(padded)["CUSTOM"].tolist() == ["DEMO_CUSTOM_A"]
