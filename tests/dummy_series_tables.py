# Purpose: Dummy 계열(Dummy · Top_Dummy) 시험들이 함께 쓰는 합성 시나리오 표 다섯 장을 만든다.

"""Dummy 계열 시험의 합성 시나리오 표.

제품 셋, 달 둘이다. 값은 모두 이 파일의 리터럴이다(실데이터 아님).

- `DEMO-HBM` (HBM): Buffer · Core · Top · Dummy · Top_Dummy 다섯 경로. `Top_Dummy` 는 원천 표기처럼
  대문자(`TOP_DUMMY`)로 둔다 — 대소문자를 가리지 않는지 함께 본다.
- `DEMO-EDP` (EDP-TSV): Master · Slave 와 이름만 `Dummy` 인 경로. EDP 에는 Dummy 계열이 없어 빠지면
  안 된다.
- `DEMO-DONLY` (HBM): Dummy · Top_Dummy 경로만 있는 제품. 이 제품의 Wafer 는 HOME 집계에서 통째로
  빠지고, Density 기준정보도 없다 — 이 제품만 다른 두 계획은 HOME Wafer · Density 가 같다.
"""

from __future__ import annotations

import pandas as pd
from custom_key_tables import with_blank_custom

from capa_simulation.services.display_order_editor import DISPLAY_ORDER_COLUMNS
from capa_simulation.services.simulation_cache import HomeSimulationCacheKey

MONTHS = (202601, 202602)
HBM = "DEMO-HBM"
EDP = "DEMO-EDP"
DUMMY_ONLY = "DEMO-DONLY"

# (제품정보, Stack, 제품타입, 달마다 생산수량)
_PLAN_ROWS = (
    (HBM, "12H", "HBM", (100.0, 120.0)),
    (EDP, "8H", "EDP-TSV", (40.0, 50.0)),
    (DUMMY_ONLY, "12H", "HBM", (30.0, 30.0)),
)
# (제품정보, Stack, WF 구분, 구분_Chip, Net Die, EDS_수율, BE_수율)
_ROUTE_ROWS = (
    (HBM, "12H", "Buffer", 1.0, 400.0, 0.9, 0.95),
    (HBM, "12H", "Core", 12.0, 800.0, 0.8, 0.95),
    (HBM, "12H", "Top", 1.0, 800.0, 0.85, 0.95),
    (HBM, "12H", "Dummy", 1.0, 800.0, 0.8, 0.95),
    (HBM, "12H", "TOP_DUMMY", 1.0, 800.0, 0.85, 0.95),
    (EDP, "8H", "Master", 1.0, 600.0, 0.9, 0.97),
    (EDP, "8H", "Slave", 7.0, 600.0, 0.9, 0.97),
    (EDP, "8H", "Dummy", 1.0, 600.0, 0.9, 0.97),
    (DUMMY_ONLY, "12H", "Dummy", 1.0, 800.0, 0.8, 0.95),
    (DUMMY_ONLY, "12H", "Top_Dummy", 1.0, 800.0, 0.85, 0.95),
)


def plan(*, without: tuple[str, ...] = ()) -> pd.DataFrame:
    """`RQ_PKG_PLAN`. `without` 에 든 제품은 뺀다(비교 계획용)."""
    rows = [
        {
            "생산계획년월": month,
            "양산구분": "양산",
            "제품정보": product,
            "Stack": stack,
            "Capa Code": f"{product}-CC",
            "Customer": "DEMO-CUST",
            "CS": "MP",
            "Pack Code": "DEMO-PACK",
            "제품타입": product_type,
            "생산수량": quantity,
        }
        for product, stack, product_type, quantities in _PLAN_ROWS
        if product not in without
        for month, quantity in zip(MONTHS, quantities, strict=True)
    ]
    return with_blank_custom(pd.DataFrame(rows), "RQ_PKG_PLAN")


def yields() -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "생산계획년월": month,
                "제품정보": product,
                "Stack": stack,
                "WF 구분": division,
                "EDS_수율": eds,
                "BE_수율": be,
            }
            for product, stack, division, _chip, _die, eds, be in _ROUTE_ROWS
            for month in MONTHS
        ]
    )
    return with_blank_custom(frame, "RQ_YLD")


def chip_qty() -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "제품정보": product,
                "Stack": stack,
                "WF 구분": division,
                "구분_Chip": chip,
                "Net Die": die,
            }
            for product, stack, division, chip, die, _eds, _be in _ROUTE_ROWS
        ]
    )
    return with_blank_custom(frame, "RQ_CHIP_QTY")


def chip_eq() -> pd.DataFrame:
    """Density 기준정보. Dummy 계열만 있는 제품은 두지 않는다(용량을 내지 않는 경로)."""
    frame = pd.DataFrame(
        {
            "제품정보": [HBM, EDP],
            "Stack": ["12H", "8H"],
            "WF 구분": ["Core", "Master"],
            "구분_Chip": [12.0, 8.0],
            "구분_EQ": [24.0, 16.0],
        }
    )
    return with_blank_custom(frame, "RQ_CHIP_EQ")


def display_order() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DISPLAY_ORDER_COLUMNS))


def tables(*, plan_frame: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """HOME 계산 함수가 읽는 시나리오 표."""
    return {
        "RQ_PKG_PLAN": plan() if plan_frame is None else plan_frame,
        "RQ_YLD": yields(),
        "RQ_CHIP_QTY": chip_qty(),
        "RQ_CHIP_EQ": chip_eq(),
        "RQ_EQP_AVBL": pd.DataFrame({"생산계획년월": list(MONTHS)}),
        "RQ_DISPLAY_ORDER": display_order(),
    }


def home_key(tag: str) -> HomeSimulationCacheKey:
    """HOME 계산 키 꼴 `(기준정보 판, 내용 토큰, 시작 달, 끝 달, 표시순서 지문)`."""
    return (0, f"dummy-series-{tag}", MONTHS[0], MONTHS[-1], "order")
