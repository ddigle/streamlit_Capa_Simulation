# Purpose: 부품을 갈라 보이는 다섯 화면이 한 제품의 부품을 같은 이름표 집합으로 내는지 본다.

"""다섯 화면의 부품 이름표 — 한 판정 · 한 이름표(UI-CON-02 · PRC-01).

견본은 `custom_key_tables.two_part_tables`(내장 시드의 한 제품을 두 부품으로 가른 RQ 표)다. 부품을
가르는 제품은 다섯 화면(HOME 도넛 · 입장 화면 Summary · HOME 계획 세부수량 · 공정 Capa 상세
「제품별 소요대수」 · 제약 시뮬레이션 「제약 제품」) 모두 그 두 이름표(「제품 (부품)」)로만 서고,
제약 고르기만 이름만 쓴 제품 전체 한 줄을 더한다(2026-11-23 보드 답 D3 (나)). 부품이 하나뿐인
제품은 화면마다 제품 이름 그대로다. 화면마다 범위가 달라(도넛은 칸 수 · 공정은 그 공정에 소요가
있는 제품) 전체 집합이 아니라 제품마다 견준다. 한 값 데이터(내장 시드)는 다섯 화면 어디에도 괄호
이름표가 없다.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

import pandas as pd
import pytest
from custom_key_tables import PART_A, PART_B, TWO_PART_PRODUCT, two_part_tables

from capa_simulation.components.intro_summary import summary_payload
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.constraint_simulation import constraint_product_choices
from capa_simulation.services.dashboard import PRODUCTION_DETAIL_DIMENSIONS
from capa_simulation.services.official_summary import build_official_summary
from capa_simulation.services.process_capa_detail import build_process_product_demand
from capa_simulation.services.product_parts import (
    multi_part_products,
    part_merged_columns,
    product_part_label,
)
from capa_simulation.services.product_share import OTHER_PRODUCT_LABEL, assign_product_slots
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.simulation_cache import get_capacity_and_demand

PROCESSES = ("DEMO_Chip_Attach", "DEMO_Wafer_Inspect")
PART_LABELS = frozenset(product_part_label(TWO_PART_PRODUCT, part) for part in (PART_A, PART_B))


def _months(tables: Mapping[str, pd.DataFrame]) -> list[int]:
    return sorted({int(month) for month in pd.to_numeric(tables["RQ_PKG_PLAN"]["생산계획년월"])})


def _screen_labels(tables: Mapping[str, pd.DataFrame]) -> dict[str, set[str]]:
    """화면 → 그 화면이 제품 이름으로 쓰는 글자들. 공정 · 제약 화면은 공정마다 한 화면으로 센다.

    HOME 캐시는 프로세스 전역이라 부를 때마다 토큰을 새로 짓는다."""
    months = _months(tables)
    display_order = tables["RQ_DISPLAY_ORDER"]
    key = sc.build_home_simulation_cache_key(
        reference_version=1,
        scenario_token=f"product-parts-screens-{uuid4().hex}",
        start_month=months[0],
        end_month=months[-1],
        display_order=display_order,
    )
    simulation = sc.get_home_simulation(key, tables, display_order, tables)
    without_edp = sc.get_home_lob_without_edp(key, tables, display_order)
    _, detail, monthly_wafer, _, _, slot_volume = simulation

    slots = assign_product_slots(slot_volume, display_order)
    screens: dict[str, set[str]] = {"HOME 도넛": {*slots.order, *slots.folded}}

    thresholds = SecurementThresholds(1.095, 0.995)
    summary = build_official_summary(
        months=months,
        monthly_density=pd.DataFrame({"생산계획년월": months, "부하량": [10.0] * len(months)}),
        monthly_wafer=monthly_wafer,
        securement_rate=pd.DataFrame(
            [(month, "P-A", 1.2, 30.0, 25.0) for month in months],
            columns=["생산계획년월", "공정", "확보율", "가용대수", "소요대수"],
        ),
        product_volume=without_edp[3],
        slot_volume=slot_volume,
        display_order=display_order,
        included_processes=["P-A"],
        thresholds=thresholds,
    )
    payload = summary_payload(
        summary,
        release_name="공식 v1",
        scenario_name="DEMO",
        thresholds=thresholds,
        process_label=str,
    )
    screens["입장 화면 Summary"] = {str(entry["name"]) for entry in payload["products"]}

    visible, merged = part_merged_columns(detail, PRODUCTION_DETAIL_DIMENSIONS)
    assert "CUSTOM" not in visible
    screens["HOME 계획 세부수량"] = {str(name) for name in merged["제품정보"].dropna()}

    _, required = get_capacity_and_demand(tables)
    multi_part = multi_part_products(tables["RQ_PKG_PLAN"])
    for process in PROCESSES:
        table = build_process_product_demand(
            required,
            process=process,
            split="제품정보",
            months=months,
            limit=10_000,
            multi_part=multi_part,
        )
        screens[f"공정 Capa 상세 {process}"] = {str(label) for label in table["분류"]}
        screens[f"제약 시뮬레이션 {process}"] = set(constraint_product_choices(table))
    return screens


def _of_product(labels: set[str], product: str) -> set[str]:
    return {label for label in labels if label == product or label.startswith(f"{product} (")}


def test_every_screen_names_the_two_parts_with_the_same_labels() -> None:
    """부품을 가르는 제품은 화면마다 같은 두 이름표다 — 이름만으로는 제약 고르기에서만 선다."""
    screens = _screen_labels(two_part_tables())

    assert len(screens) == 3 + 2 * len(PROCESSES)
    for screen, labels in screens.items():
        expected = set(PART_LABELS)
        if screen.startswith("제약 시뮬레이션"):
            expected.add(TWO_PART_PRODUCT)
        assert _of_product(labels, TWO_PART_PRODUCT) == expected, screen


def test_the_single_part_products_keep_their_names_on_every_screen() -> None:
    """부품이 하나뿐인 제품은 다섯 화면 모두 제품 이름 그대로다 — 화면이 쓰는 이름이 계획의
    제품정보 글자 그대로다. 시드의 그 제품은 ER 이라 양산만 싣는 계획 세부수량에는 없다."""
    tables = two_part_tables()
    products = {str(name).strip() for name in tables["RQ_PKG_PLAN"]["제품정보"].dropna()} - {
        TWO_PART_PRODUCT
    }
    screens = _screen_labels(tables)

    shown: set[str] = set()
    for screen, labels in screens.items():
        others = labels - _of_product(labels, TWO_PART_PRODUCT) - {OTHER_PRODUCT_LABEL}
        assert others <= products, screen
        shown |= others
    assert shown == products


def test_one_value_data_shows_no_part_label_on_any_screen() -> None:
    """한 제품에 CUSTOM 이 한 값인 데이터(내장 시드)는 다섯 화면 어디에도 괄호 이름표가 없다 —
    제약 고르기도 제품 이름 줄뿐이다."""
    tables = build_builtin_seed_dataset().reference_tables
    assert multi_part_products(tables["RQ_PKG_PLAN"]) == frozenset()
    products = {str(name).strip() for name in tables["RQ_PKG_PLAN"]["제품정보"].dropna()}

    for screen, labels in _screen_labels(tables).items():
        assert labels - {OTHER_PRODUCT_LABEL} <= products, screen


@pytest.mark.parametrize("process", PROCESSES)
def test_the_constraint_whole_line_and_part_lines_cover_the_process_rows(process: str) -> None:
    """제약 고르기의 부품 줄은 공정 Capa 상세 분류 행의 부품 이름표와 같은 글이고, 이름만 쓴 줄은
    그 제품의 분류 행이 없는 화면 값이다(제품 전체)."""
    tables = two_part_tables()
    months = _months(tables)
    _, required = get_capacity_and_demand(tables)
    table = build_process_product_demand(
        required,
        process=process,
        split="제품정보",
        months=months,
        limit=10_000,
        multi_part=multi_part_products(tables["RQ_PKG_PLAN"]),
    )
    choices = constraint_product_choices(table)

    rows = set(table["분류"])
    assert TWO_PART_PRODUCT not in rows and choices[TWO_PART_PRODUCT].part is None
    assert {label for label, choice in choices.items() if choice.part is not None} == PART_LABELS
    assert set(choices) - {TWO_PART_PRODUCT} == rows
