# Purpose: 시험 fixture 에 CUSTOM 키 칸을 계약대로 붙이고 한 제품을 두 부품으로 가른 시드 표를 낸다.

"""CUSTOM 키 시험 도우미.

- `with_blank_custom` — 계약(`derived_keys`)에 CUSTOM 이 든 표에만 빈 값 표지 칸을 붙인다. 리터럴
  RQ fixture 를 손으로 고치지 않고 이것을 지나게 한다 — 한 값이면 계산이 지금과 같다.
- `two_part_tables` — 내장 시드의 한 제품을 두 부품(`DEMO_CUSTOM_A` · `DEMO_CUSTOM_B`)으로 가른 RQ
  16표. 부품마다 Capa Code 가 다르고 계획 수량은 반씩이다. 그래서 B 를 바꾸지 않으면 두 부품의
  합이 시드 한 제품과 같고, 조인이 두 부품 행을 겹쳐 붙이면 그 합이 어긋난다.
  `split_capa_code=False` 면 두 부품이 같은 Capa Code 를 쓴다 — Capa Code 를 실은 키(부하량 · 원수요
  키)는 그때 CUSTOM 으로만 두 부품을 가르므로, 그 키의 CUSTOM 은 이 꼴로만 값이 붙들린다.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Final, overload

import pandas as pd

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK

CUSTOM_COLUMN: Final = "CUSTOM"
TWO_PART_PRODUCT: Final = "DEMO PRODUCT A"
PART_A: Final = "DEMO_CUSTOM_A"
PART_B: Final = "DEMO_CUSTOM_B"
PART_B_CAPA_CODE: Final = "DEMO_CAPA_A2"
# B 부품만 다르게 두는 값 — 부품마다 Wafer · 대당 Capa · 소요대수가 따로 나는지 보려는 것이다.
PART_B_EDS_YIELD_FACTOR: Final = 0.8
PART_B_UPEH_FACTOR: Final = 1.25


def custom_keyed_tables() -> tuple[str, ...]:
    """계약에서 CUSTOM 을 업무 키로 갖는 RQ 표 이름(계약 차례)."""
    return tuple(
        name
        for name, keys in load_core_data_contract().derived_keys.items()
        if CUSTOM_COLUMN in keys
    )


@overload
def with_blank_custom(frame_or_tables: pd.DataFrame, name: str | None = None) -> pd.DataFrame: ...


@overload
def with_blank_custom(
    frame_or_tables: Mapping[str, pd.DataFrame], name: None = None
) -> dict[str, pd.DataFrame]: ...


def with_blank_custom(
    frame_or_tables: pd.DataFrame | Mapping[str, pd.DataFrame], name: str | None = None
) -> pd.DataFrame | dict[str, pd.DataFrame]:
    """CUSTOM 칸이 없는 표에 빈 값 표지 칸을 끝에 붙인 사본. 이미 있는 칸은 그대로 둔다.

    표 묶음(이름 → 표)을 주면 계약상 CUSTOM 키 표에만 붙인다. 표 하나를 주면 `name` 이 그 표 이름일
    때 계약을 보고, `name` 이 없으면(계산 중간 프레임 — 부하량 · 소요대수 상세 등) 그냥 붙인다.
    """
    keyed = custom_keyed_tables()
    if isinstance(frame_or_tables, pd.DataFrame):
        if name is not None and name not in keyed:
            return frame_or_tables.copy()
        return _blank_custom(frame_or_tables)
    return {
        table_name: _blank_custom(frame) if table_name in keyed else frame.copy()
        for table_name, frame in frame_or_tables.items()
    }


def _blank_custom(frame: pd.DataFrame) -> pd.DataFrame:
    if CUSTOM_COLUMN in frame.columns:
        return frame.copy()
    return frame.assign(**{CUSTOM_COLUMN: CUSTOM_BLANK})


@cache
def _seed_tables() -> dict[str, pd.DataFrame]:
    return build_builtin_seed_dataset().reference_tables


def two_part_tables(
    *,
    vary_b: bool = True,
    split_capa_code: bool = True,
    parts: tuple[str, str] = (PART_A, PART_B),
) -> dict[str, pd.DataFrame]:
    """시드 한 제품(`TWO_PART_PRODUCT`)을 두 부품으로 가른 RQ 16표(사본).

    CUSTOM 키 표 여덟에서 그 제품 행을 A · B 두 벌로 둔다. `split_capa_code` 이면 Capa Code 칸이
    있는 표(계획 · 경로)는 B 를 `PART_B_CAPA_CODE` 로 바꿔 부품마다 경로가 따로 붙게 하고, 아니면
    두 부품이 시드의 Capa Code 를 함께 쓴다. 계획 수량은 두 부품이 반씩 나눈다.
    `vary_b` 이면 B 의 EDS 수율과 UPEH 만 바꾼다. 다른 제품과 CUSTOM 키가 없는 표는 시드 그대로다.
    `parts` 는 A · B 자리에 둘 부품 이름이다(부품 이름표 줄임 시험이 끝을 같이 쓰는 이름을 준다).
    """
    tables = {name: frame.copy() for name, frame in _seed_tables().items()}
    for name in custom_keyed_tables():
        frame = tables[name]
        product = frame["제품정보"].astype("string").eq(TWO_PART_PRODUCT).fillna(False)
        if not bool(product.any()):
            raise AssertionError(f"시드 {name} 에 {TWO_PART_PRODUCT} 행이 없습니다.")
        part_a = frame.loc[product].assign(**{CUSTOM_COLUMN: parts[0]})
        part_b = frame.loc[product].assign(**{CUSTOM_COLUMN: parts[1]})
        if split_capa_code and "Capa Code" in frame.columns:
            part_b["Capa Code"] = PART_B_CAPA_CODE
        if name == "RQ_PKG_PLAN":
            part_a["생산수량"] = part_a["생산수량"] / 2
            part_b["생산수량"] = part_b["생산수량"] / 2
        if vary_b and name == "RQ_YLD":
            part_b["EDS_수율"] = part_b["EDS_수율"] * PART_B_EDS_YIELD_FACTOR
        if vary_b and name == "RQ_UPEH":
            part_b["UPEH"] = part_b["UPEH"] * PART_B_UPEH_FACTOR
        tables[name] = pd.concat([frame.loc[~product], part_a, part_b], ignore_index=True).reindex(
            columns=frame.columns
        )
    return tables


def single_part_tables(
    part: str, *, vary_b: bool = True, split_capa_code: bool = True
) -> dict[str, pd.DataFrame]:
    """`two_part_tables` 에서 그 제품의 한 부품만 남긴 표 — 부품 하나씩 따로 돌린 값과 견준다."""
    if part not in (PART_A, PART_B):
        raise ValueError(f"부품은 {PART_A} 또는 {PART_B} 입니다: {part}")
    other = PART_B if part == PART_A else PART_A
    tables = two_part_tables(vary_b=vary_b, split_capa_code=split_capa_code)
    for name in custom_keyed_tables():
        frame = tables[name]
        tables[name] = frame.loc[frame[CUSTOM_COLUMN].ne(other)].reset_index(drop=True)
    return tables
