"""Non-sensitive deterministic data used to bootstrap an empty source checkout."""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from typing import cast

import pandas as pd

from capa_simulation.io.core_data_source import CoreDataBatch, load_core_data_contract
from capa_simulation.services.core_data_pipeline import (
    PreparedCoreDataset,
    prepare_core_data_dataset,
)
from capa_simulation.services.display_order_editor import validate_display_order
from capa_simulation.settings import PROJECT_ROOT

BUILTIN_DISPLAY_ORDER_PATH = PROJECT_ROOT / "config" / "bootstrap_display_order.json"
BUILTIN_SEED_SCHEMA_VERSION = 1
BUILTIN_SEED_PIPELINE_VERSION = "builtin-synthetic-core-data-v1"
BUILTIN_SEED_SOURCE_CODE = "BUILTIN-GITHUB-SEED-V1"
BUILTIN_SEED_SOURCE_NAME = "GitHub 독립 실행용 합성 Core Data"
BUILTIN_SEED_SCENARIO_NAME = "GitHub 독립 실행 데모"
BUILTIN_SEED_REVISION_NAME = "내장 시드 r1"
BUILTIN_SEED_RELEASE_NAME = "내장 데모 공식버전"
BUILTIN_SEED_MONTHS = tuple(202600 + month for month in range(1, 13))


@dataclass(frozen=True)
class _ProductSeed:
    name: str
    stack: str
    wf_type: str
    cs: str
    capa_code: str
    customer: str
    base_quantity: float
    chip_quantity: int
    eq_quantity: int
    net_die: int
    eds_yield: float
    be_yield: float


@dataclass(frozen=True)
class _ProcessSeed:
    name: str
    area: str
    demand_basis: str
    step_sequence: str
    mcp_sequence: str
    upeh: float | None
    standard_time: float | None
    run_rate: float
    vital: float
    module_count: int
    lot_ratio: float
    wafer_ratio: float
    owned_equipment: float
    lent_equipment: float


_PRODUCTS = (
    _ProductSeed(
        name="DEMO_PRODUCT_A",
        stack="8H",
        wf_type="Core",
        cs="MP",
        capa_code="DEMO_CAPA_A",
        customer="DEMO_CUSTOMER_A",
        base_quantity=120.0,
        chip_quantity=8,
        eq_quantity=24,
        net_die=1_200,
        eds_yield=0.96,
        be_yield=0.98,
    ),
    _ProductSeed(
        name="DEMO_PRODUCT_B",
        stack="12H",
        wf_type="Base",
        cs="ER",
        capa_code="DEMO_CAPA_B",
        customer="DEMO_CUSTOMER_B",
        base_quantity=75.0,
        chip_quantity=12,
        eq_quantity=32,
        net_die=980,
        eds_yield=0.94,
        be_yield=0.97,
    ),
)

_PROCESSES = (
    _ProcessSeed(
        name="DEMO_Chip_Attach",
        area="Main",
        demand_basis="CHIP",
        step_sequence="DEMO-P100",
        mcp_sequence="DEMO-1A",
        upeh=72_000.0,
        standard_time=None,
        run_rate=0.84,
        vital=1.05,
        module_count=4,
        lot_ratio=0.98,
        wafer_ratio=0.99,
        owned_equipment=18.0,
        lent_equipment=2.0,
    ),
    _ProcessSeed(
        name="DEMO_Wafer_Inspect",
        area="Main",
        demand_basis="WF",
        step_sequence="DEMO-P200",
        mcp_sequence="DEMO-2A",
        upeh=38.0,
        standard_time=None,
        run_rate=0.88,
        vital=1.04,
        module_count=2,
        lot_ratio=1.0,
        wafer_ratio=0.97,
        owned_equipment=12.0,
        lent_equipment=1.0,
    ),
    _ProcessSeed(
        name="DEMO_Final_Test",
        area="MI",
        demand_basis="CHIP",
        step_sequence="DEMO-P300",
        mcp_sequence="DEMO-3A",
        upeh=None,
        standard_time=0.055,
        run_rate=0.79,
        vital=1.08,
        module_count=4,
        lot_ratio=0.96,
        wafer_ratio=0.98,
        owned_equipment=22.0,
        lent_equipment=3.0,
    ),
)


def load_builtin_display_order() -> pd.DataFrame:
    """Load and strictly validate the Git-tracked display-order seed."""
    payload = cast(object, json.loads(BUILTIN_DISPLAY_ORDER_PATH.read_text(encoding="utf-8")))
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ValueError("내장 표시순서 시드의 최상위 값은 객체여야 합니다.")
    root = cast(dict[str, object], payload)
    if root.get("schema_version") != BUILTIN_SEED_SCHEMA_VERSION:
        raise ValueError("내장 표시순서 시드 버전이 코드와 일치하지 않습니다.")
    rules = root.get("rules")
    if not isinstance(rules, list) or not all(isinstance(rule, dict) for rule in rules):
        raise ValueError("내장 표시순서 시드의 rules는 객체 목록이어야 합니다.")
    return validate_display_order(pd.DataFrame(cast(list[dict[str, object]], rules)))


def build_builtin_core_data() -> pd.DataFrame:
    """Build deterministic demo-only Core Data with the exact 78-column contract."""
    contract = load_core_data_contract()
    columns = [column.name for column in contract.columns]
    rows: list[dict[str, object]] = []
    for month_index, month in enumerate(BUILTIN_SEED_MONTHS):
        run_days = calendar.monthrange(month // 100, month % 100)[1]
        for product_index, product in enumerate(_PRODUCTS, start=1):
            quantity = product.base_quantity * (1.0 + month_index * 0.015)
            common = _common_product_values(month, product, quantity)
            plan = _blank_core_row(columns)
            plan.update(common)
            plan.update(
                {
                    "시뮬레이션 ID": f"DEMO-PLAN-{month}-{product_index}",
                    "PLAN ID": f"DEMO-PLAN-ID-{month}-{product_index}",
                    "계획기초정보여부": "Y",
                }
            )
            rows.append(plan)

            for process_index, process in enumerate(_PROCESSES, start=1):
                reference = _blank_core_row(columns)
                reference.update(common)
                reference.update(
                    {
                        "시뮬레이션 ID": (f"DEMO-REF-{month}-{product_index}-{process_index}"),
                        "PLAN ID": f"DEMO-PLAN-ID-{month}-{product_index}",
                        "계획기초정보여부": "N",
                        "FAB": "DEMO_FAB",
                        "Area_Name": process.area,
                        "공정": process.name,
                        "메이커": "DEMO_MAKER",
                        "STEP_SEQ": process.step_sequence,
                        "MCP_SEQ": process.mcp_sequence,
                        "모델명": "DEMO_MODEL",
                        "Para": "1",
                        "Step수": "1",
                        "CAPA_RUN_RATE": process.run_rate,
                        "소요기준": process.demand_basis,
                        "RUN_DAY": run_days,
                        "UPEH": process.upeh,
                        "ST": process.standard_time,
                        "Lot 측정률": process.lot_ratio,
                        "WF측정률": process.wafer_ratio,
                        "모듈수": process.module_count,
                        "Side반영률": 1,
                        "편중률": process.vital,
                        "설비보유": process.owned_equipment,
                        "설비대수변화관리": "0",
                        "설비대여평가": process.lent_equipment,
                        "설비대여평가항목": "DEMO",
                        "설비대여평가DESC": "합성 시드 데이터",
                        "MCP_Chip_Ratio": 1,
                        "시뮬레이션 누락여부": "N",
                    }
                )
                rows.append(reference)
    return pd.DataFrame(rows, columns=columns)


def build_builtin_seed_dataset() -> PreparedCoreDataset:
    """Run the built-in source through the same pipeline as CSV and BigDataQuery."""
    return prepare_core_data_dataset(
        CoreDataBatch(
            simulation_code=BUILTIN_SEED_SOURCE_CODE,
            simulation_name=BUILTIN_SEED_SOURCE_NAME,
            source_type="BUILTIN_SYNTHETIC_SEED",
            frame=build_builtin_core_data(),
        ),
        load_builtin_display_order(),
    )


def builtin_seed_processes() -> tuple[str, ...]:
    return tuple(process.name for process in _PROCESSES)


def _blank_core_row(columns: list[str]) -> dict[str, object]:
    return dict.fromkeys(columns, pd.NA)


def _common_product_values(
    month: int,
    product: _ProductSeed,
    quantity: float,
) -> dict[str, object]:
    return {
        "기준정보년월": month,
        "제품타입": "DEMO",
        "U/PKG": "1",
        "PKG1": "DEMO_PKG",
        "LOB Code": "DEMO_LOB",
        "Capa Code": product.capa_code,
        "제품정보": product.name,
        "생산계획년월": month,
        "생산수량": quantity,
        "Stack": product.stack,
        "Customer": product.customer,
        "Pack Code": "DEMO_PACK",
        "CS": product.cs,
        "D_EQ": product.eq_quantity,
        "WF 구분": product.wf_type,
        "구분_Chip": product.chip_quantity,
        "구분_EQ": product.eq_quantity,
        "Plan_Chip(K개)": quantity * product.chip_quantity,
        "CHIP": product.chip_quantity,
        "Net Die": product.net_die,
        "Month": month % 10_000,
        "계획(K개)": quantity,
        "8H 환산 계획(K개)": quantity,
        "WF수(매)": quantity * 1_000 * product.chip_quantity / product.net_die,
        "EQ(억Gb)": quantity * product.chip_quantity * product.eq_quantity / 100_000,
        "누락여부": "N",
        "EDS_수율": product.eds_yield,
        "BE_수율": product.be_yield,
        "CUM_수율": product.eds_yield * product.be_yield,
    }
