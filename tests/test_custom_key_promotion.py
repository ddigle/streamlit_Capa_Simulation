# Purpose: CUSTOM 제품 구분 키의 값 규칙과 두 부품이 계산 끝까지 접히지 않는 끝단 계약을 고정한다.

"""CUSTOM 키 — 값 정규화와 끝단 계약.

원천 `CUSTOM` 은 같은 제품의 부품을 가르는 값이다. 빈 값을 NA 로 두면 조인 · 접기에서 행이 빠지거나
한 줄로 접히므로 파생 경계에서 한 번 `CUSTOM_BLANK` 로 세운다. 시험은 표지 글자를 따로 적지 않는다.
표지는 편집표 붙여넣기 · CSV 왕복에서도 키 값으로 남아야 한다.

끝단 시험은 RQ 여덟 표 · 계산 키에 CUSTOM 이 오른 뒤의 계약이다. CUSTOM 이 한 값이면 결과가 그
값과 상관없이 같고, 한 제품이 두 부품이면 Wafer · 대당 Capa · 소요대수가 부품마다 따로 난다 — 그
합이 부품 하나씩 따로 돌린 값과 같아야 조인이 두 부품 행을 겹쳐 붙이지 않은 것이다. 견본은
`custom_key_tables.two_part_tables`(내장 시드의 한 제품을 두 부품으로 가른 것)다.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from datetime import date
from uuid import uuid4

import pandas as pd
import pytest
from custom_key_tables import (
    PART_A,
    PART_B,
    TWO_PART_PRODUCT,
    custom_keyed_tables,
    single_part_tables,
    two_part_tables,
)
from test_core_data_pipeline import _core_data_row

from capa_simulation.components.exclusion_table import exclusion_export
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.clipboard_table import parse_clipboard_table
from capa_simulation.services.core_data_derivation import (
    ACTIVE_CORE_COLUMNS,
    CUSTOM_BLANK,
    build_q_core_data,
    custom_sort_key,
    normalize_custom_values,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_REQUIRED
from capa_simulation.services.load_calculator import (
    calculate_chip_and_wafer_loads,
    calculate_density_load,
)
from capa_simulation.services.reference_csv import (
    parse_reference_edit_clipboard,
    reference_edit_csv_bytes,
    strip_excel_text_guard,
)
from capa_simulation.services.required_equipment import (
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    RESULT_DIMENSIONS,
    required_equipment_to_month_table,
)
from capa_simulation.services.standard_target_capacity import (
    PKG_EQUIVALENT_COLUMN,
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
)
from capa_simulation.services.weighted_unit_capacity import effective_process_capacity_long


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


def _product_rule(page: str, tab: str) -> pd.DataFrame:
    """제품정보 오름차순 규칙 하나 — 같은 제품의 행은 규칙 열쇠가 같다."""
    return pd.DataFrame(
        {
            "페이지 구분": [page],
            "탭 구분": [tab],
            "정렬우선순위": [1],
            "분류컬럼": ["제품정보"],
            "정렬방식": ["오름차순"],
            "분류값": [None],
            "값표시순서": [None],
            "활성여부": ["Y"],
        }
    )


def test_the_custom_sort_key_puts_the_blank_marker_last() -> None:
    """부품 차례는 대소문자를 접은 글자 → 원문 오름차순이고, 빈 값(표지 · NA · 빈 글자)은 끝이다.
    파이썬 기본 차례는 표지를 글자 앞에 둔다."""
    values = ["b", CUSTOM_BLANK, "A", None, "a", "B", "  "]

    assert sorted(values, key=custom_sort_key)[:4] == ["A", "a", "B", "b"]
    assert all(custom_sort_key(value) == custom_sort_key(CUSTOM_BLANK) for value in (None, "  "))
    assert sorted(["DEMO_CUSTOM_B", CUSTOM_BLANK, "DEMO_CUSTOM_A"], key=custom_sort_key) == [
        "DEMO_CUSTOM_A",
        "DEMO_CUSTOM_B",
        CUSTOM_BLANK,
    ]


def test_display_order_ties_are_broken_by_custom_with_the_marker_last() -> None:
    """규칙 열쇠가 같은 행(같은 제품)은 부품 오름차순, 표지는 끝 — 원래 행 차례와 상관없다."""
    data = pd.DataFrame(
        {
            "제품정보": ["DEMO_P2", "DEMO_P1", "DEMO_P1", "DEMO_P1"],
            "CUSTOM": ["DEMO_CUSTOM_A", CUSTOM_BLANK, "DEMO_CUSTOM_B", "DEMO_CUSTOM_A"],
        }
    )

    result = apply_display_order(data, _product_rule("부하량", "환산"), "부하량", "환산")

    assert result.to_dict("records") == [
        {"제품정보": "DEMO_P1", "CUSTOM": "DEMO_CUSTOM_A"},
        {"제품정보": "DEMO_P1", "CUSTOM": "DEMO_CUSTOM_B"},
        {"제품정보": "DEMO_P1", "CUSTOM": CUSTOM_BLANK},
        {"제품정보": "DEMO_P2", "CUSTOM": "DEMO_CUSTOM_A"},
    ]


def test_display_order_keeps_the_source_order_without_rules_or_parts() -> None:
    """규칙이 없으면 원천 차례 그대로이고(동순위 열쇠도 없음), 부품이 한 값이면 규칙 뒤 차례가
    지금과 같다."""
    parts = pd.DataFrame(
        {"제품정보": ["DEMO_P1", "DEMO_P1"], "CUSTOM": [CUSTOM_BLANK, "DEMO_CUSTOM_A"]}
    )
    no_rules = _product_rule("부하량", "환산").iloc[0:0]
    assert apply_display_order(parts, no_rules, "부하량", "환산") is parts

    single = pd.DataFrame(
        {
            "제품정보": ["DEMO_P2", "DEMO_P1", "DEMO_P1"],
            "Capa Code": ["C3", "C2", "C1"],
            "CUSTOM": [CUSTOM_BLANK] * 3,
        }
    )
    result = apply_display_order(single, _product_rule("부하량", "환산"), "부하량", "환산")
    assert result["Capa Code"].tolist() == ["C2", "C1", "C3"]


def _route_rules() -> pd.DataFrame:
    """산출 결과 소요대수의 공정 → STEP → MCP 오름차순 — 내장 시드 프로필처럼 제품 칸을 정하지 않는
    규칙."""
    return pd.DataFrame(
        {
            "페이지 구분": [PAGE_CALCULATION] * 3,
            "탭 구분": [TAB_REQUIRED] * 3,
            "정렬우선순위": [1, 2, 3],
            "분류컬럼": ["공정", "STEP_SEQ", "MCP_SEQ"],
            "정렬방식": ["오름차순"] * 3,
            "분류값": [None] * 3,
            "값표시순서": [None] * 3,
            "활성여부": ["Y"] * 3,
        }
    )


def _route_rows(products: list[str], customs: list[str]) -> pd.DataFrame:
    """한 공정 · 한 STEP · 한 MCP 의 소요대수 「상세」 꼴 — 규칙 열쇠가 모두 같다."""
    count = len(products)
    return pd.DataFrame(
        {
            "공정": ["DEMO_PROCESS"] * count,
            "제품정보": products,
            "Stack": ["8H"] * count,
            "CUSTOM": customs,
            "STEP_SEQ": ["S0100"] * count,
            "MCP_SEQ": ["M01"] * count,
            "202701": [float(index + 1) for index in range(count)],
        }
    )


def test_display_order_ties_keep_other_products_in_the_source_order() -> None:
    """규칙이 제품 칸을 정하지 않으면 제품마다 CUSTOM 이 달라도 다른 제품의 행은 원래 차례다 —
    CUSTOM 글자 차례로 섞이지 않는다."""
    data = _route_rows(["DEMO_P2", "DEMO_P1"], ["DEMO_CUSTOM_B", "DEMO_CUSTOM_A"])

    result = apply_display_order(data, _route_rules(), PAGE_CALCULATION, TAB_REQUIRED)

    assert result["제품정보"].tolist() == ["DEMO_P2", "DEMO_P1"]


def test_display_order_ties_put_one_products_parts_together_in_part_order() -> None:
    """한 제품의 부품은 그 제품이 원래 차례에서 처음 선 자리에 이웃해 부품 차례로 서고(표지는 끝),
    사이에 있던 다른 제품은 그 뒤로 원래 차례를 지킨다."""
    data = _route_rows(
        ["DEMO_P1", "DEMO_P3", "DEMO_P1", "DEMO_P2", "DEMO_P1"],
        [CUSTOM_BLANK, "DEMO_CUSTOM_A", "DEMO_CUSTOM_B", "DEMO_CUSTOM_B", "DEMO_CUSTOM_A"],
    )

    result = apply_display_order(data, _route_rules(), PAGE_CALCULATION, TAB_REQUIRED)

    assert list(zip(result["제품정보"], result["CUSTOM"], strict=True)) == [
        ("DEMO_P1", "DEMO_CUSTOM_A"),
        ("DEMO_P1", "DEMO_CUSTOM_B"),
        ("DEMO_P1", CUSTOM_BLANK),
        ("DEMO_P3", "DEMO_CUSTOM_A"),
        ("DEMO_P2", "DEMO_CUSTOM_B"),
    ]
    assert result["202701"].tolist() == [5.0, 3.0, 1.0, 2.0, 4.0]


def test_display_order_part_groups_stay_inside_their_rule_tie() -> None:
    """부품 무리는 규칙 열쇠가 같은 행 안에서만 모인다 — 숫자 규칙 칸(STEP_NO)마다 따로 서므로,
    한 제품이 앞 STEP 에서 먼저 섰어도 뒤 STEP 에서는 그 STEP 안 원래 차례를 따른다."""
    rules = _product_rule(PAGE_CALCULATION, TAB_REQUIRED).assign(분류컬럼="STEP_NO")
    data = pd.DataFrame(
        {
            "제품정보": ["DEMO_P1", "DEMO_P1", "DEMO_P2", "DEMO_P1", "DEMO_P1"],
            "CUSTOM": [
                "DEMO_CUSTOM_A",
                "DEMO_CUSTOM_B",
                "DEMO_CUSTOM_A",
                "DEMO_CUSTOM_B",
                "DEMO_CUSTOM_A",
            ],
            "STEP_NO": [10, 10, 20, 20, 20],
        }
    )

    result = apply_display_order(data, rules, PAGE_CALCULATION, TAB_REQUIRED)

    assert list(zip(result["STEP_NO"], result["제품정보"], result["CUSTOM"], strict=True)) == [
        (10, "DEMO_P1", "DEMO_CUSTOM_A"),
        (10, "DEMO_P1", "DEMO_CUSTOM_B"),
        (20, "DEMO_P2", "DEMO_CUSTOM_A"),
        (20, "DEMO_P1", "DEMO_CUSTOM_A"),
        (20, "DEMO_P1", "DEMO_CUSTOM_B"),
    ]


def test_display_order_single_part_rows_stay_put_among_other_parts() -> None:
    """부품이 하나뿐인 제품의 행은 숫자 칸만 다른 같은 제품 행이 떨어져 있어도 제자리다 — 다른
    제품에 부품이 둘이어도 그 제품의 부품만 움직인다."""
    data = pd.DataFrame(
        {
            "공정": ["DEMO_PROCESS"] * 5,
            "제품정보": ["DEMO_P1", "DEMO_P2", "DEMO_P1", "DEMO_P3", "DEMO_P3"],
            "CUSTOM": [
                "DEMO_CUSTOM_A",
                "DEMO_CUSTOM_B",
                "DEMO_CUSTOM_A",
                "DEMO_CUSTOM_B",
                "DEMO_CUSTOM_A",
            ],
            "STEP_NO": [10, 10, 20, 10, 10],
            "202701": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )

    result = apply_display_order(data, _route_rules(), PAGE_CALCULATION, TAB_REQUIRED)

    assert result["202701"].tolist() == [1.0, 2.0, 3.0, 5.0, 4.0]


def test_display_order_part_groups_split_by_the_other_text_columns() -> None:
    """CUSTOM 말고 다른 글자 칸(WF 구분)이 다르면 다른 무리다 — 한 제품의 두 부품 × 두 WF 구분은
    WF 구분마다 두 부품이 이웃한다."""
    data = _route_rows(
        ["DEMO_P1"] * 4, ["DEMO_CUSTOM_B", "DEMO_CUSTOM_B", "DEMO_CUSTOM_A", "DEMO_CUSTOM_A"]
    ).assign(**{"WF 구분": ["DEMO_WF1", "DEMO_WF2", "DEMO_WF1", "DEMO_WF2"]})

    result = apply_display_order(data, _route_rules(), PAGE_CALCULATION, TAB_REQUIRED)

    assert list(zip(result["WF 구분"], result["CUSTOM"], strict=True)) == [
        ("DEMO_WF1", "DEMO_CUSTOM_A"),
        ("DEMO_WF1", "DEMO_CUSTOM_B"),
        ("DEMO_WF2", "DEMO_CUSTOM_A"),
        ("DEMO_WF2", "DEMO_CUSTOM_B"),
    ]


def test_display_order_parts_gather_only_within_one_capa_code() -> None:
    """부품마다 Capa Code 가 다르면(PKG PLAN 꼴) 무리가 Capa Code 마다 갈린다 — 같은 Capa Code 의
    부품만 이웃해 부품 차례(표지 끝)로 서고, 제 Capa Code 를 가진 부품은 원래(피벗) 차례 자리다.
    피벗이 CUSTOM 글자 그대로 세워 표지가 그 부품보다 앞이어도 표지를 끝으로 옮기지 않는다."""
    data = pd.DataFrame(
        {
            "제품정보": ["DEMO_P1", "DEMO_P1", "DEMO_P1"],
            "CUSTOM": [CUSTOM_BLANK, "DEMO_CUSTOM_A", "DEMO_CUSTOM_B"],
            "Capa Code": ["DEMO_CAPA_1", "DEMO_CAPA_2", "DEMO_CAPA_1"],
            "202701": [1.0, 2.0, 3.0],
        }
    )

    rules = _product_rule("생산 계획", "PKG PLAN")
    result = apply_display_order(data, rules, "생산 계획", "PKG PLAN")

    assert list(zip(result["CUSTOM"], result["Capa Code"], strict=True)) == [
        ("DEMO_CUSTOM_B", "DEMO_CAPA_1"),
        (CUSTOM_BLANK, "DEMO_CAPA_1"),
        ("DEMO_CUSTOM_A", "DEMO_CAPA_2"),
    ]


def test_display_order_ties_keep_the_source_order_when_custom_is_one_value() -> None:
    """CUSTOM 이 표 전체에서 한 값이면 규칙 뒤 차례는 원래 차례 그대로다 — 숫자 칸(값 · 숫자 STEP)만
    다른 같은 제품의 행이 떨어져 있어도 모으지 않는다."""
    data = pd.DataFrame(
        {
            "공정": ["DEMO_PROCESS"] * 3,
            "제품정보": ["DEMO_P1", "DEMO_P2", "DEMO_P1"],
            "CUSTOM": ["DEMO_CUSTOM_A"] * 3,
            "STEP_NO": [10, 10, 20],
            "202701": [1.0, 2.0, 3.0],
        }
    )

    result = apply_display_order(data, _route_rules(), PAGE_CALCULATION, TAB_REQUIRED)

    assert result["202701"].tolist() == [1.0, 2.0, 3.0]


def test_display_order_custom_rules_come_before_the_part_order() -> None:
    """사용자지정 규칙이 정한 칸은 규칙이 먼저다. 목록 밖 제품은 규칙 순위가 같아도 제품끼리 원래
    차례이고, 그 안의 부품만 부품 차례로 선다."""
    rules = pd.DataFrame(
        {
            "페이지 구분": [PAGE_CALCULATION] * 2,
            "탭 구분": [TAB_REQUIRED] * 2,
            "정렬우선순위": [1, 1],
            "분류컬럼": ["제품정보", "제품정보"],
            "정렬방식": ["사용자지정", "사용자지정"],
            "분류값": ["DEMO_P2", "DEMO_P1"],
            "값표시순서": [1, 2],
            "활성여부": ["Y", "Y"],
        }
    )
    data = _route_rows(
        ["DEMO_P4", "DEMO_P1", "DEMO_P3", "DEMO_P2", "DEMO_P4"],
        ["DEMO_CUSTOM_B", "DEMO_CUSTOM_A", "DEMO_CUSTOM_A", "DEMO_CUSTOM_B", "DEMO_CUSTOM_A"],
    )

    result = apply_display_order(data, rules, PAGE_CALCULATION, TAB_REQUIRED)

    assert list(zip(result["제품정보"], result["CUSTOM"], strict=True)) == [
        ("DEMO_P2", "DEMO_CUSTOM_B"),
        ("DEMO_P1", "DEMO_CUSTOM_A"),
        ("DEMO_P4", "DEMO_CUSTOM_A"),
        ("DEMO_P4", "DEMO_CUSTOM_B"),
        ("DEMO_P3", "DEMO_CUSTOM_A"),
    ]


def test_display_order_ties_keep_the_source_order_without_text_identity() -> None:
    """CUSTOM 말고 글자 칸이 없어 「CUSTOM 뺀 정체」 를 못 정하는 표는 규칙 뒤 원래 차례만 쓴다."""
    rules = _product_rule(PAGE_CALCULATION, TAB_REQUIRED).assign(분류컬럼="STEP_NO")
    data = pd.DataFrame(
        {
            "STEP_NO": [10, 10],
            "CUSTOM": ["DEMO_CUSTOM_B", "DEMO_CUSTOM_A"],
            "202701": [1.0, 2.0],
        }
    )

    result = apply_display_order(data, rules, PAGE_CALCULATION, TAB_REQUIRED)

    assert result["CUSTOM"].tolist() == ["DEMO_CUSTOM_B", "DEMO_CUSTOM_A"]


# ------------------------------------------------------------------ 끝단 — 한 값 · 두 부품

# 끝단 시험이 맞대는 계산 결과 칸. 대당 Capa · 소요대수 상세는 CUSTOM 칸을 싣는다.
_CUSTOM = "CUSTOM"
# 소요기준 PKG 경로로 바꿔 보는 공정 — 시드에는 PKG 경로가 없다.
_PKG_PROCESS = "DEMO_Final_Test"
# `RQ_UPEH` 행(UPEH · ST)을 빼 대당 Capa 가 없게 만드는 공정.
_NO_CAPACITY_PROCESS = "DEMO_Final_Test"


def _seed() -> dict[str, pd.DataFrame]:
    return dict(build_builtin_seed_dataset().reference_tables)


def _all_custom(tables: Mapping[str, pd.DataFrame], value: str) -> dict[str, pd.DataFrame]:
    """CUSTOM 키 표 여덟의 CUSTOM 을 모두 한 값으로 바꾼 사본."""
    keyed = custom_keyed_tables()
    return {
        name: frame.assign(**{_CUSTOM: value}) if name in keyed else frame.copy()
        for name, frame in tables.items()
    }


def _outcome(tables: Mapping[str, pd.DataFrame]) -> sc.CapacityOutcome:
    """시나리오 전체 기간의 대당 Capa · 소요대수(캐시 없는 순수 코어)."""
    outcome = sc.full_capacity_outcome(tables, tables)
    assert outcome.error is None, outcome.error
    return outcome


def _unit_and_required(tables: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcome = _outcome(tables)
    assert outcome.unit_capacity is not None and outcome.required_equipment is not None
    return outcome.unit_capacity, outcome.required_equipment


def _wafer(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    _, wafer = calculate_chip_and_wafer_loads(
        tables["RQ_PKG_PLAN"], tables["RQ_YLD"], tables["RQ_CHIP_QTY"]
    )
    return wafer


def _density(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    return calculate_density_load(tables["RQ_PKG_PLAN"], tables["RQ_CHIP_EQ"])


def _without_custom(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(columns=[_CUSTOM], errors="ignore").reset_index(drop=True)


def _assert_same_but_custom(left: pd.DataFrame, right: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(_without_custom(left), _without_custom(right))


def _part_rows(frame: pd.DataFrame, part: str) -> pd.DataFrame:
    rows = frame["제품정보"].eq(TWO_PART_PRODUCT) & frame[_CUSTOM].eq(part)
    return frame.loc[rows.fillna(False).astype("bool")].reset_index(drop=True)


def _process_month_sum(frame: pd.DataFrame, value: str) -> pd.Series:
    return frame.groupby(["공정", "생산계획년월"])[value].sum().sort_index()


def _home_results(
    tables: Mapping[str, pd.DataFrame], token: str
) -> tuple[list[pd.DataFrame], pd.DataFrame]:
    """HOME 세 함수(기본 · EDP 뺌 · 세부수량)의 결과 프레임.

    캐시는 프로세스 전역이라 부를 때마다 토큰을 새로 짓는다."""
    months = sorted(int(month) for month in pd.to_numeric(tables["RQ_PKG_PLAN"]["생산계획년월"]))
    display_order = tables["RQ_DISPLAY_ORDER"]
    key = sc.build_home_simulation_cache_key(
        reference_version=1,
        scenario_token=f"custom-end-to-end-{token}-{uuid4().hex}",
        start_month=months[0],
        end_month=months[-1],
        display_order=display_order,
    )
    simulation = sc.get_home_simulation(key, tables, display_order, tables)
    without_edp = sc.get_home_lob_without_edp(key, tables, display_order)
    detail = sc.get_home_plan_detail(
        key, tables, display_order, include_edp=False, include_customer=True
    )
    frames = [item for item in (*simulation, *without_edp) if isinstance(item, pd.DataFrame)]
    return frames, detail


def test_one_custom_value_gives_the_same_results_whatever_the_value() -> None:
    """① 여덟 표의 CUSTOM 이 모두 표지든 `DEMO_CUSTOM_A` 든 전체 기간 계산 · HOME 이 CUSTOM 칸
    말고 같다."""
    seed = _seed()
    renamed = _all_custom(seed, PART_A)

    seed_unit, seed_required = _unit_and_required(seed)
    renamed_unit, renamed_required = _unit_and_required(renamed)

    for before, after in ((seed_unit, renamed_unit), (seed_required, renamed_required)):
        assert set(before[_CUSTOM]) == {CUSTOM_BLANK}
        assert set(after[_CUSTOM]) == {PART_A}
        _assert_same_but_custom(before, after)
    _assert_same_but_custom(_wafer(seed), _wafer(renamed))
    _assert_same_but_custom(_density(seed), _density(renamed))

    seed_home, seed_detail = _home_results(seed, "seed")
    renamed_home, renamed_detail = _home_results(renamed, "renamed")
    assert len(seed_home) == len(renamed_home) > 0
    for before, after in zip(seed_home, renamed_home, strict=True):
        _assert_same_but_custom(before, after)
    _assert_same_but_custom(seed_detail, renamed_detail)


def test_two_parts_of_one_product_are_calculated_apart() -> None:
    """② 한 제품을 두 Capa Code · 두 부품으로 가르고 B 의 수율 · UPEH 만 바꾼다.

    Wafer · 대당 Capa · 소요대수가 부품마다 따로 나고 부품 하나씩 따로 돌린 값과 같다. B 를 바꾸지
    않으면 두 부품의 합이 시드 한 제품과 같다 — 조인이 다른 부품 행을 붙이면(many_to_many) 합이
    불어난다.
    """
    two = two_part_tables()
    two_unit, two_required = _unit_and_required(two)
    two_wafer = _wafer(two)

    for part in (PART_A, PART_B):
        alone = single_part_tables(part)
        alone_unit, alone_required = _unit_and_required(alone)
        for together, apart in (
            (two_unit, alone_unit),
            (two_required, alone_required),
            (two_wafer, _wafer(alone)),
        ):
            rows = _part_rows(together, part)
            assert not rows.empty
            pd.testing.assert_frame_equal(rows, _part_rows(apart, part))
    a_capacity = _part_rows(two_unit, PART_A)["대당 Capa"].astype("float64")
    b_capacity = _part_rows(two_unit, PART_B)["대당 Capa"].astype("float64")
    assert not a_capacity.equals(b_capacity)
    assert not _part_rows(two_wafer, PART_A)["물량"].equals(_part_rows(two_wafer, PART_B)["물량"])

    seed = _seed()
    even = two_part_tables(vary_b=False)
    seed_required = _unit_and_required(seed)[1]
    even_required = _unit_and_required(even)[1]
    pd.testing.assert_series_equal(
        _process_month_sum(even_required, "소요대수"),
        _process_month_sum(seed_required, "소요대수"),
        check_exact=False,
    )
    assert len(even_required) > len(seed_required)
    for load in (_wafer, _density):
        assert float(load(even)["물량"].sum()) == pytest.approx(float(load(seed)["물량"].sum()))


def test_two_parts_with_one_capa_code_are_calculated_apart() -> None:
    """② 의 같은 Capa Code 꼴 — 두 부품이 Capa Code 까지 같으면 부하량 키(`LOAD_KEYS`)는 CUSTOM
    으로만 두 부품을 가른다. 부품 줄이 부품 하나씩 따로 돌린 값과 같고, B 를 바꾸지 않으면 공정 × 월
    소요대수 합이 시드와 같다 — 키에서 CUSTOM 이 빠지면 두 부품 부하가 합쳐져 두 경로에 다 붙어 합이
    불어난다(Capa Code 가 다른 ② 는 그래도 갈라져 통과한다)."""
    two = two_part_tables(split_capa_code=False)
    two_unit, two_required = _unit_and_required(two)
    two_wafer = _wafer(two)
    for part in (PART_A, PART_B):
        alone_unit, alone_required = _unit_and_required(
            single_part_tables(part, split_capa_code=False)
        )
        for together, apart in (
            (two_unit, alone_unit),
            (two_required, alone_required),
            (two_wafer, _wafer(single_part_tables(part, split_capa_code=False))),
        ):
            rows = _part_rows(together, part)
            assert not rows.empty
            pd.testing.assert_frame_equal(rows, _part_rows(apart, part))

    even_required = _unit_and_required(two_part_tables(vary_b=False, split_capa_code=False))[1]
    pd.testing.assert_series_equal(
        _process_month_sum(even_required, "소요대수"),
        _process_month_sum(_unit_and_required(_seed())[1], "소요대수"),
        check_exact=False,
    )


def _standard_target(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """첫 달 주차의 표준 목표(집계 수준 `WF 구분`)와 PKG 환산 — 모든 공정 · 주차 가용대수 1."""
    required = _unit_and_required(tables)[1]
    first = int(pd.to_numeric(tables["RQ_PKG_PLAN"]["생산계획년월"]).min())
    start = date(first // 100, first % 100, 1)
    end = date(first // 100, first % 100, 28)
    weeks = pd.date_range(start, end, freq="W-MON")
    availability = pd.DataFrame(
        [
            {
                "공정": process,
                "Weeknum": f"{week.isocalendar().year % 100:02d}-W{week.isocalendar().week:02d}",
                "가용대수": 1.0,
            }
            for process in sorted(required["공정"].dropna().unique())
            for week in weeks
        ]
    )
    weekly = build_weekly_standard_target_capacity(
        required, tables["RQ_RUN_DAY"], availability, start, end, "WF 구분"
    )
    return add_pkg_equivalent_standard_target(
        weekly, required, tables["RQ_PKG_PLAN"], "WF 구분"
    ).reset_index(drop=True)


def test_the_standard_target_demand_keeps_both_parts_with_one_capa_code() -> None:
    """표준 목표의 원수요 키(`DEMAND_ID_COLUMNS` · PKG 환산 연결 `PKG_PLAN_KEYS`)도 두 부품을
    가른다. 두 부품이 Capa Code 까지 같고 부하가 같으면(B 를 바꾸지 않음) 원수요 키의 CUSTOM 만이 두
    부품 부하를 따로 센다 — 빠지면 한 부품 부하가 겹친 원수요로 지워져 원수요 부하량이 말없이 반이
    된다. 두 부품 견본(수량 반씩)의 공정 유효 Capa 원수요 · STEP 소요대수와 표준 목표 PKG 환산은
    시드와 같다."""
    seed = _seed()
    even = two_part_tables(vary_b=False, split_capa_code=False)

    def demand(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        return effective_process_capacity_long(_unit_and_required(tables)[1], "WF 구분")

    seed_demand = demand(seed)
    product = seed_demand["제품정보"].eq(TWO_PART_PRODUCT)
    assert bool(product.any()) and float(seed_demand.loc[product, "원수요_부하량"].sum()) > 0
    pd.testing.assert_frame_equal(demand(even), seed_demand, check_exact=False)

    seed_target = _standard_target(seed)
    assert seed_target[PKG_EQUIVALENT_COLUMN].notna().any()
    pd.testing.assert_frame_equal(_standard_target(even), seed_target, check_exact=False)


def _with_pkg_route(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """`_PKG_PROCESS` 의 경로 · 실적 표를 소요기준 PKG · `Buffer` 로 바꾼다(모든 제품)."""
    out = dict(tables)
    for name in ("RQ_REQB", "RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO"):
        frame = out[name].copy()
        rows = frame["공정"].eq(_PKG_PROCESS).fillna(False).astype("bool")
        frame.loc[rows, "WF 구분"] = "Buffer"
        if "소요기준" in frame.columns:
            frame.loc[rows, "소요기준"] = "PKG"
        out[name] = frame
    return out


def test_pkg_routes_carry_the_load_of_each_part() -> None:
    """③ 소요기준 PKG 경로도 부품마다 부하가 붙는다 — PKG 부하 줄에 CUSTOM 이 비면 경로에 못 붙어
    그 부품의 PKG 소요대수가 말없이 0 이 된다."""
    two_required = _unit_and_required(_with_pkg_route(two_part_tables()))[1]
    pkg_rows = two_required["공정"].eq(_PKG_PROCESS)
    assert set(two_required.loc[pkg_rows, "소요기준"]) == {"PKG"}

    for part in (PART_A, PART_B):
        alone_required = _unit_and_required(_with_pkg_route(single_part_tables(part)))[1]
        together = _part_rows(two_required.loc[pkg_rows], part)
        apart = _part_rows(alone_required.loc[alone_required["공정"].eq(_PKG_PROCESS)], part)
        assert not together.empty
        assert float(together["부하량"].sum()) > 0
        pd.testing.assert_frame_equal(together, apart)


def test_pkg_routes_carry_the_load_of_each_part_with_one_capa_code() -> None:
    """③ 의 같은 Capa Code 꼴 — PKG 부하 줄도 Capa Code 가 같은 두 부품을 CUSTOM 으로만 가른다.
    부품 줄이 부품 하나씩 따로 돌린 값과 같다."""
    two_required = _unit_and_required(_with_pkg_route(two_part_tables(split_capa_code=False)))[1]
    pkg_rows = two_required["공정"].eq(_PKG_PROCESS)
    for part in (PART_A, PART_B):
        alone_required = _unit_and_required(
            _with_pkg_route(single_part_tables(part, split_capa_code=False))
        )[1]
        together = _part_rows(two_required.loc[pkg_rows], part)
        apart = _part_rows(alone_required.loc[alone_required["공정"].eq(_PKG_PROCESS)], part)
        assert not together.empty
        assert float(together["부하량"].sum()) > 0
        pd.testing.assert_frame_equal(together, apart)


@pytest.mark.parametrize("name", custom_keyed_tables())
def test_a_table_without_the_custom_column_stops_instead_of_folding(name: str) -> None:
    """④ 두 부품 견본에서 한 표의 CUSTOM 칸을 빼면 두 부품이 말없이 한 줄로 접히지 않고 멈춘다."""
    tables = two_part_tables()
    tables[name] = tables[name].drop(columns=[_CUSTOM])

    outcome = sc.full_capacity_outcome(tables, tables)
    messages = [outcome.error or ""]
    try:
        _density(tables)
    except ValueError as error:
        messages.append(str(error))

    assert any(name in message and _CUSTOM in message for message in messages), messages


def _month_table(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """산출 결과 소요대수 탭의 월 표(표시순서 정렬 앞)."""
    return required_equipment_to_month_table(_unit_and_required(tables)[1])


def _process_total(table: pd.DataFrame) -> pd.DataFrame:
    """「상세」 를 끈 소요대수 표 — Area_Name · 공정 단위 합."""
    months = [column for column in table.columns if column not in RESULT_DIMENSIONS]
    return table.groupby(["Area_Name", "공정"])[months].sum(min_count=1)


def test_the_required_month_table_gives_each_part_a_row_with_the_same_process_total() -> None:
    """⑤ 산출 결과 소요대수 표(분류 칸 `RESULT_DIMENSIONS`)도 부품마다 한 줄이다.

    B 를 바꾸지 않은 두 부품 견본은 공정 단위 합(「상세」 끔)이 시드와 같고, 그 제품의 줄은 시드 한
    줄마다 부품 A · B 두 줄이다. B 를 바꾼 견본의 부품 줄은 부품 하나씩 따로 돌린 표의 줄과 같다.
    """
    seed_table = _month_table(_seed())
    even_table = _month_table(two_part_tables(vary_b=False))
    seed_total = _process_total(seed_table)
    assert not seed_total.empty and len(seed_total.columns) > 0
    pd.testing.assert_frame_equal(_process_total(even_table), seed_total, check_exact=False)

    route_keys = [column for column in RESULT_DIMENSIONS if column != _CUSTOM]
    seed_product = seed_table.loc[seed_table["제품정보"].eq(TWO_PART_PRODUCT)]
    assert not seed_product.empty
    assert _CUSTOM in even_table.columns
    product = even_table.loc[even_table["제품정보"].eq(TWO_PART_PRODUCT)]
    parts = product.groupby(route_keys, dropna=False)[_CUSTOM].agg(sorted)
    assert len(parts) == len(seed_product)
    assert parts.tolist() == [[PART_A, PART_B]] * len(seed_product)
    assert len(even_table) == len(seed_table) + len(seed_product)

    two_table = _month_table(two_part_tables())
    months = [column for column in two_table.columns if column not in RESULT_DIMENSIONS]
    for part in (PART_A, PART_B):
        alone = _month_table(single_part_tables(part))
        pd.testing.assert_frame_equal(_part_rows(two_table, part), _part_rows(alone, part))
    assert not _part_rows(two_table, PART_A)[months].equals(_part_rows(two_table, PART_B)[months])


def test_the_required_exclusion_list_carries_the_part_beside_the_stack() -> None:
    """⑥ 소요대수에서 뺀 경로 목록(`ST-15` — 분류 칸 `RESULT_DIMENSIONS`)도 CUSTOM 을 분류 칸 Stack
    바로 뒤에 세운다. 두 부품의 대당 Capa 가 함께 없으면 두 부품 줄이 따로 실린다."""
    tables = two_part_tables()
    upeh = tables["RQ_UPEH"]
    lost = upeh["공정"].eq(_NO_CAPACITY_PROCESS) & upeh["제품정보"].eq(TWO_PART_PRODUCT)
    tables["RQ_UPEH"] = upeh.loc[~lost.fillna(False).astype("bool")].reset_index(drop=True)

    required = _unit_and_required(tables)[1]
    exclusions = required.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR]
    exported = exclusion_export(
        exclusions,
        dimensions=RESULT_DIMENSIONS,
        display_order=tables["RQ_DISPLAY_ORDER"],
        page=PAGE_CALCULATION,
        tab=TAB_REQUIRED,
    )

    columns = list(exported.columns)
    assert columns.index(_CUSTOM) == columns.index("Stack") + 1
    assert set(exported["공정"]) == {_NO_CAPACITY_PROCESS}
    assert set(exported[_CUSTOM]) == {PART_A, PART_B}
