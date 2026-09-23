# Purpose: 저장 리비전의 가상제품 복제 이력을 변환하고 원본 충돌 없이 합친다.

from collections.abc import Sequence

import pandas as pd

from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.virtual_product import VirtualProductRecord

HISTORY_COLUMNS = ("제품정보", "Stack", "원본 제품정보", "원본 Stack")


def virtual_product_records(frame: pd.DataFrame) -> tuple[VirtualProductRecord, ...]:
    """저장된 이력의 제품 키와 복제 원본을 값 변경 없이 옮긴다."""
    require_columns(frame, HISTORY_COLUMNS, "가상제품 복제 이력")
    return tuple(
        VirtualProductRecord(*(str(value) for value in row))
        for row in frame.loc[:, list(HISTORY_COLUMNS)].itertuples(index=False, name=None)
    )


def merge_virtual_product_records(
    base: Sequence[VirtualProductRecord], donor: Sequence[VirtualProductRecord]
) -> tuple[VirtualProductRecord, ...]:
    """월 없는 이력 전체를 합치되 같은 제품 키의 복제 원본이 다르면 차단한다."""
    merged: dict[tuple[str, str], VirtualProductRecord] = {}
    for record in (*base, *donor):
        key = (record.product, record.stack)
        previous = merged.get(key)
        if previous is not None:
            if (previous.source_product, previous.source_stack) != (
                record.source_product,
                record.source_stack,
            ):
                raise ValueError(
                    f"가상제품 복제 이력이 충돌하여 저장할 수 없습니다: "
                    f"{record.product} · {record.stack}의 복제 원본이 "
                    f"{previous.source_product} · {previous.source_stack} / "
                    f"{record.source_product} · {record.source_stack}으로 다릅니다. "
                    "복제 원본이 일치하는 리비전을 선택하세요."
                )
        else:
            merged[key] = record
    return tuple(merged.values())
