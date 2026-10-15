# Purpose: 가상제품 복제 이력을 변환하고 충돌 없이 합쳐 머지 결과에 맞추거나 새 리비전으로 물려준다.

from collections.abc import Mapping, Sequence
from typing import NamedTuple

import pandas as pd

from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.korean_particle import with_direction_particle
from capa_simulation.services.virtual_product import (
    PRODUCT_KEY_COLUMNS,
    VirtualProductRecord,
    clone_table_names,
)

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
                    f"{record.source_product} · "
                    f"{with_direction_particle(record.source_stack)} 다릅니다. "
                    "복제 원본이 일치하는 리비전을 선택하세요."
                )
        else:
            merged[key] = record
    return tuple(merged.values())


class MergedVirtualProducts(NamedTuple):
    """월 머지 결과에 남길 이력과, 빼거나 알릴 것."""

    records: tuple[VirtualProductRecord, ...]
    # 결과 표 어디에도 그 제품 키가 없어 뺀 이력.
    dropped: tuple[VirtualProductRecord, ...]
    # 한쪽에선 가상 제품인데 다른 쪽에선 이력 없이 표에 있는(실제 제품인) 키. 결과에서 두 값이
    # 섞인다 — 달마다 그 달 원본의 행, 월 없는 표는 베이스 값.
    mixed: tuple[VirtualProductRecord, ...]


def _product_keys(tables: Mapping[str, pd.DataFrame]) -> set[tuple[str, str]]:
    return {
        (str(product).strip(), str(stack).strip())
        for name in clone_table_names(tables)
        for product, stack in tables[name]
        .loc[:, list(PRODUCT_KEY_COLUMNS)]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    }


def merge_result_virtual_products(
    base: Sequence[VirtualProductRecord],
    donor: Sequence[VirtualProductRecord],
    *,
    base_tables: Mapping[str, pd.DataFrame],
    donor_tables: Mapping[str, pd.DataFrame],
    result_tables: Mapping[str, pd.DataFrame],
) -> MergedVirtualProducts:
    """월 머지가 새 시나리오에 남길 가상제품 이력. 두 리비전의 이력을 합친 뒤 결과 표를 본다.

    복제 원본이 다른 같은 키는 막는다(`merge_virtual_product_records`). 남기는 것은 결과 표에 그
    제품 키가 남은 이력뿐이다 — 리비전 저장이 물려받는 규칙(`inherit_virtual_product_records`)과
    같다. 한쪽에서만 가상 제품이고 다른 쪽 표에는 이력 없이 있는 키는 남기되 알린다. 이력은 남겨야
    공식버전 지정 때 확인을 받는다.
    """
    merged = merge_virtual_product_records(base, donor)
    kept = inherit_virtual_product_records(merged, (), result_tables)
    base_virtual = {(record.product, record.stack) for record in base}
    donor_virtual = {(record.product, record.stack) for record in donor}
    base_keys, donor_keys = _product_keys(base_tables), _product_keys(donor_tables)
    mixed = tuple(
        record
        for record in kept
        if (key := (record.product, record.stack)) not in base_virtual & donor_virtual
        and (
            (key in donor_virtual and key in base_keys)
            or (key in base_virtual and key in donor_keys)
        )
    )
    return MergedVirtualProducts(
        records=kept,
        dropped=tuple(record for record in merged if record not in kept),
        mixed=mixed,
    )


def inherit_virtual_product_records(
    parent: Sequence[VirtualProductRecord],
    session: Sequence[VirtualProductRecord],
    saved_tables: Mapping[str, pd.DataFrame],
) -> tuple[VirtualProductRecord, ...]:
    """부모 리비전의 이력을 새 리비전으로 물려주고 이 세션의 등록을 더한다.

    물려받는 행은 저장할 표에 그 `제품정보 + Stack` 이 아직 남아 있을 때만 남긴다. 제품 키를
    가진 복제 대상 표(`clone_table_names`) 중 **한 곳이라도** 그 키가 있으면 남기고, 모두에서
    사라졌을 때만 버린다 — 계획만 지운 제품은 기준정보가 남아 있어 계속 이력에 든다. 저장할 표에
    제품 키를 가진 표가 하나도 없으면 남았는지 판단할 근거가 없으므로 모두 물려받는다.

    이 세션의 등록은 거르지 않는다(지금까지와 같다). 같은 키가 양쪽에 있으면 세션 쪽이 이긴다 —
    등록은 표에 없는 키만 받으므로, 겹친다면 부모의 제품이 표에서 사라진 뒤 다시 등록한 것이고
    그때의 복제 원본이 지금 표의 출처다. 월 머지처럼 충돌을 막지 않는 까닭이 이것이다.
    """
    names = clone_table_names(saved_tables)
    if parent and names:
        # 물려받을 키를 다 찾으면 남은 표는 읽지 않는다. 보통 첫 표(계획)에서 끝난다.
        missing = {(record.product, record.stack) for record in parent}
        for name in names:
            missing -= {
                (str(product).strip(), str(stack).strip())
                for product, stack in saved_tables[name]
                .loc[:, list(PRODUCT_KEY_COLUMNS)]
                .drop_duplicates()
                .itertuples(index=False, name=None)
            }
            if not missing:
                break
        parent = [record for record in parent if (record.product, record.stack) not in missing]
    merged: dict[tuple[str, str], VirtualProductRecord] = {}
    for record in (*parent, *session):
        merged[(record.product, record.stack)] = record
    return tuple(merged.values())
