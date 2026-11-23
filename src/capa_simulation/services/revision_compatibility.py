# Purpose: 저장된 리비전이 현재 계산 계약으로 쓸 수 있는지 불러오기 전에 판정한다.

"""리비전 호환성 판정.

리비전은 append-only 라 오래된 저장분이 그대로 남는다. 그 뒤에 계산 계약이 바뀌면 옛
리비전에는 새 계약이 요구하는 값이 없다. 그대로 활성화하면 계산이 첫 줄에서 멈추고,
**활성 시나리오가 이미 바뀐 뒤라 되돌릴 방법이 화면에 없다.**

그래서 불러오기 **전에** 본다. 값을 추정해 채우지 않는다 — 어느 경로의 실적인지는 원천에만
있고, 지어내면 오류 대신 조용히 틀린 Capa 가 나온다.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping

import pandas as pd

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.display_order import ROUTE_SEQUENCE_COLUMNS

# 마이그레이션 6 이 경로 키를 도입한 표. 그 전에 저장한 리비전은 두 키가 비어 있다.
ROUTE_KEYED_TABLES = ("RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO")
# 한 제품의 부품을 가르는 업무 키 칸 — 마이그레이션 0039 가 옛 행에 빈 값 표지를 넣었다.
CUSTOM_COLUMN = "CUSTOM"


@functools.cache
def custom_keyed_tables() -> tuple[str, ...]:
    """계약(`derived_keys`)에서 `CUSTOM` 을 업무 키로 갖는 RQ 표 이름(계약 차례) — 0039 가 칸을
    더한 표다. 새 상수로 적지 않고 계약에서 낸다(표가 늘면 저절로 따라온다)."""
    return tuple(
        name
        for name, keys in load_core_data_contract().derived_keys.items()
        if CUSTOM_COLUMN in keys
    )


def route_key_incompatible_tables(tables: Mapping[str, pd.DataFrame]) -> list[str]:
    """경로 키가 비어 있어 계산에 쓸 수 없는 표 이름."""
    broken: list[str] = []
    for name in ROUTE_KEYED_TABLES:
        frame = tables.get(name)
        if frame is None or frame.empty:
            continue
        missing_column = any(column not in frame.columns for column in ROUTE_SEQUENCE_COLUMNS)
        if missing_column or any(
            frame[column].isna().any() or frame[column].astype("string").fillna("").eq("").any()
            for column in ROUTE_SEQUENCE_COLUMNS
        ):
            broken.append(name)
    return broken


def custom_incompatible_tables(tables: Mapping[str, pd.DataFrame]) -> list[str]:
    """`CUSTOM` 칸이 없거나 빈 값(NULL · 빈 글자 · 공백뿐)이 있어 계산에 쓸 수 없는 표 이름.

    빈 값 표지(`CUSTOM_BLANK`)는 값이다 — 통과한다. 마이그레이션 0039 뒤 저장분은 걸리지 않는
    안전망이다. 고유값만 보므로 큰 표(`RQ_REQB`)도 칸 전체를 글자로 바꾸지 않는다.
    """
    broken: list[str] = []
    for name in custom_keyed_tables():
        frame = tables.get(name)
        if frame is None or frame.empty:
            continue
        if CUSTOM_COLUMN not in frame.columns or any(
            _blank(value) for value in pd.unique(frame[CUSTOM_COLUMN])
        ):
            broken.append(name)
    return broken


def _blank(value: object) -> bool:
    if isinstance(value, str):
        return not value.strip()
    return value is None or value is pd.NA or value != value


def revision_block_reason(tables: Mapping[str, pd.DataFrame]) -> str | None:
    """불러오기를 막을 이유(한 문장씩). 쓸 수 있으면 `None`."""
    reasons: list[str] = []
    broken = route_key_incompatible_tables(tables)
    if broken:
        reasons.append(
            f"이 리비전은 STEP·MCP 경로 키가 없어 계산에 쓸 수 없습니다({', '.join(broken)}). "
            "경로 키 계약보다 앞서 저장된 리비전이며, 값을 추정해 채우면 오류 대신 틀린 Capa 가 "
            "나오므로 채우지 않습니다. 같은 원천 코드를 BigDataQuery 로 다시 등록해 새 "
            "시나리오로 저장하세요."
        )
    custom_broken = custom_incompatible_tables(tables)
    if custom_broken:
        reasons.append(
            f"이 리비전은 CUSTOM 칸이 없거나 비어 있어 계산에 쓸 수 없습니다"
            f"({', '.join(custom_broken)}). 빈 칸을 추정해 채우면 CUSTOM 이 다른 행이 한 줄로 "
            "접혀 오류 대신 틀린 Capa 가 나오므로 채우지 않습니다. 같은 원천 코드를 "
            "BigDataQuery 로 다시 등록해 새 시나리오로 저장하세요."
        )
    return " ".join(reasons) if reasons else None
