# Purpose: 저장된 리비전이 현재 계산 계약으로 쓸 수 있는지 불러오기 전에 판정한다.

"""리비전 호환성 판정.

리비전은 append-only 라 오래된 저장분이 그대로 남는다. 그 뒤에 계산 계약이 바뀌면 옛
리비전에는 새 계약이 요구하는 값이 없다. 그대로 활성화하면 계산이 첫 줄에서 멈추고,
**활성 시나리오가 이미 바뀐 뒤라 되돌릴 방법이 화면에 없다.**

그래서 불러오기 **전에** 본다. 값을 추정해 채우지 않는다 — 어느 경로의 실적인지는 원천에만
있고, 지어내면 오류 대신 조용히 틀린 Capa 가 나온다.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from capa_simulation.services.display_order import ROUTE_SEQUENCE_COLUMNS

# 마이그레이션 6 이 경로 키를 도입한 표. 그 전에 저장한 리비전은 두 키가 비어 있다.
ROUTE_KEYED_TABLES = ("RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO")


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


def revision_block_reason(tables: Mapping[str, pd.DataFrame]) -> str | None:
    """불러오기를 막을 이유 한 문장. 쓸 수 있으면 `None`."""
    broken = route_key_incompatible_tables(tables)
    if not broken:
        return None
    return (
        f"이 리비전은 STEP·MCP 경로 키가 없어 계산에 쓸 수 없습니다({', '.join(broken)}). "
        "경로 키 계약보다 앞서 저장된 리비전이며, 값을 추정해 채우면 오류 대신 틀린 Capa 가 "
        "나오므로 채우지 않습니다. 같은 원천 코드를 BigDataQuery 로 다시 등록해 새 "
        "시나리오로 저장하세요."
    )
