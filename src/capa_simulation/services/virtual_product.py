# Purpose: 기존 제품의 기준정보를 새 제품 키로 복제해 가상 제품을 등록한다.

"""Clone an existing product's reference rows into a new virtual product.

신규 제품을 계획에만 넣으면 환산·Capa 가 참조할 기준정보가 없어 계산에서 빠진다.
필요한 기준정보를 손으로 다 채우는 대신, 기존 제품의 행을 새 키로 통째로 복제하고
달라지는 값만 고치게 한다. 완결성이 구조적으로 보장되고 입력량이 최소가 된다.

제품 키(`제품정보` + `Stack`)를 가진 테이블만 복제 대상이다. 공정 기준 테이블
(`RQ_RUN_RATE`·`RQ_VITAL`·`RQ_RUN_DAY`·설비대수)은 제품과 무관하므로 건드리지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

PRODUCT_KEY_COLUMNS = ("제품정보", "Stack")

# 복제 대상 후보. 실제로 어떤 테이블을 복제할지는 활성 시나리오가 가진 컬럼으로 정한다.
CLONE_TABLE_CANDIDATES = (
    "RQ_PKG_PLAN",
    "RQ_YLD",
    "RQ_CHIP_QTY",
    "RQ_CHIP_EQ",
    "RQ_UPEH",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
    "RQ_REQB",
)


@dataclass(frozen=True)
class VirtualProductRequest:
    """복제 원본과 새로 만들 제품 키."""

    source_product: str
    source_stack: str
    product: str
    stack: str

    def normalized(self) -> VirtualProductRequest:
        return VirtualProductRequest(
            source_product=str(self.source_product).strip(),
            source_stack=str(self.source_stack).strip(),
            product=str(self.product).strip(),
            stack=str(self.stack).strip(),
        )


def clone_table_names(tables: Mapping[str, pd.DataFrame]) -> tuple[str, ...]:
    """활성 시나리오에서 제품 키를 가진 복제 대상 테이블 이름을 돌려준다."""
    return tuple(
        name
        for name in CLONE_TABLE_CANDIDATES
        if name in tables and all(column in tables[name].columns for column in PRODUCT_KEY_COLUMNS)
    )


def available_source_products(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """복제 원본으로 고를 수 있는 제품 키 목록을 만든다.

    기준정보가 완결된 제품만 원본이 될 수 있으므로, 복제 대상 테이블 전부에 존재하는
    키만 남긴다. 한 곳이라도 비어 있는 제품을 복제하면 그 구멍이 그대로 따라온다.
    """
    names = clone_table_names(tables)
    if not names:
        return pd.DataFrame(columns=list(PRODUCT_KEY_COLUMNS))

    common: set[tuple[str, str]] | None = None
    for name in names:
        keys = {
            (str(product).strip(), str(stack).strip())
            for product, stack in zip(tables[name]["제품정보"], tables[name]["Stack"], strict=True)
        }
        common = keys if common is None else (common & keys)
    if not common:
        return pd.DataFrame(columns=list(PRODUCT_KEY_COLUMNS))
    return pd.DataFrame(sorted(common), columns=list(PRODUCT_KEY_COLUMNS))


def validate_request(
    tables: Mapping[str, pd.DataFrame], request: VirtualProductRequest
) -> VirtualProductRequest:
    """복제를 시작하기 전에 원본과 새 키를 검증한다."""
    normalized = request.normalized()
    if not normalized.product or not normalized.stack:
        raise ValueError("새 제품의 제품정보와 Stack을 모두 입력하세요.")

    sources = available_source_products(tables)
    source_key = (normalized.source_product, normalized.source_stack)
    if source_key not in set(map(tuple, sources.to_numpy().tolist())):
        raise ValueError(
            f"복제 원본 제품을 찾을 수 없습니다: {normalized.source_product} · "
            f"{normalized.source_stack}. 기준정보가 완결된 제품만 원본이 될 수 있습니다."
        )

    new_key = (normalized.product, normalized.stack)
    if new_key == source_key:
        raise ValueError("새 제품 키가 원본과 같습니다. 다른 제품정보 또는 Stack을 쓰세요.")

    existing = _existing_product_keys(tables)
    if new_key in existing:
        raise ValueError(
            f"이미 있는 제품입니다: {normalized.product} · {normalized.stack}. "
            "다른 제품정보 또는 Stack을 쓰세요."
        )
    return normalized


def clone_product(
    tables: Mapping[str, pd.DataFrame], request: VirtualProductRequest
) -> dict[str, pd.DataFrame]:
    """원본 제품의 행을 새 키로 복제한 테이블 전체를 돌려준다.

    `RQ_PKG_PLAN` 만 생산수량을 0 으로 둔다. 원본 계획을 그대로 복제하면 총 수요가
    조용히 두 배가 된다. 사용자가 PKG PLAN 편집 격자에서 직접 넣게 한다. 수량 0 행도
    격자에 남으므로 바로 입력할 수 있다.
    """
    normalized = validate_request(tables, request)
    updates: dict[str, pd.DataFrame] = {}
    for name in clone_table_names(tables):
        source = tables[name]
        matched = source.loc[
            source["제품정보"].astype("string").str.strip().eq(normalized.source_product)
            & source["Stack"].astype("string").str.strip().eq(normalized.source_stack)
        ]
        if matched.empty:
            continue
        cloned = matched.copy()
        cloned["제품정보"] = normalized.product
        cloned["Stack"] = normalized.stack
        if name == "RQ_PKG_PLAN" and "생산수량" in cloned.columns:
            cloned["생산수량"] = 0.0
        updates[name] = pd.concat([source, cloned], ignore_index=True)
    if not updates:
        raise ValueError("복제할 기준정보 행을 찾지 못했습니다.")
    return updates


def _existing_product_keys(tables: Mapping[str, pd.DataFrame]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for name in clone_table_names(tables):
        frame = tables[name]
        keys |= {
            (str(product).strip(), str(stack).strip())
            for product, stack in zip(frame["제품정보"], frame["Stack"], strict=True)
        }
    return keys


@dataclass(frozen=True)
class VirtualProductRecord:
    """리비전에 기록할 가상 제품 한 건."""

    product: str
    stack: str
    source_product: str
    source_stack: str

    @classmethod
    def from_request(cls, request: VirtualProductRequest) -> VirtualProductRecord:
        normalized = request.normalized()
        return cls(
            product=normalized.product,
            stack=normalized.stack,
            source_product=normalized.source_product,
            source_stack=normalized.source_stack,
        )


def records_to_frame(records: tuple[VirtualProductRecord, ...]) -> pd.DataFrame:
    """가상 제품 목록을 화면과 저장에 쓸 표로 만든다."""
    return pd.DataFrame(
        [
            {
                "제품정보": record.product,
                "Stack": record.stack,
                "원본 제품정보": record.source_product,
                "원본 Stack": record.source_stack,
            }
            for record in records
        ],
        columns=["제품정보", "Stack", "원본 제품정보", "원본 Stack"],
    )
