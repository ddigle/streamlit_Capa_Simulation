# Purpose: 가상제품 복제 이력의 원본 보존·동일 이력 병합·복제 원본 충돌 차단을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.scenario_virtual_products import (
    merge_virtual_product_records,
    virtual_product_records,
)
from capa_simulation.services.virtual_product import VirtualProductRecord, records_to_frame


def test_history_conversion_preserves_values_and_input() -> None:
    records = (VirtualProductRecord("가상 A", "8H", "원본 B", "12H"),)
    frame = records_to_frame(records)
    original = frame.copy(deep=True)
    assert virtual_product_records(frame) == records
    pd.testing.assert_frame_equal(frame, original)
    assert virtual_product_records(records_to_frame(())) == ()


def test_same_history_is_deduplicated_and_different_stacks_are_separate() -> None:
    base = VirtualProductRecord("가상 A", "8H", "원본 B", "8H")
    donor = VirtualProductRecord("가상 A", "12H", "원본 C", "12H")
    assert merge_virtual_product_records((base,), (base, donor)) == (base, donor)
    assert merge_virtual_product_records((), (base,)) == (base,)
    assert merge_virtual_product_records((base,), ()) == (base,)


@pytest.mark.parametrize("source_product,source_stack", [("다른 원본", "8H"), ("원본 B", "12H")])
def test_conflicting_source_product_or_stack_is_rejected(
    source_product: str, source_stack: str
) -> None:
    base = VirtualProductRecord("가상 A", "8H", "원본 B", "8H")
    donor = VirtualProductRecord("가상 A", "8H", source_product, source_stack)
    with pytest.raises(ValueError, match="가상 A · 8H의 복제 원본"):
        merge_virtual_product_records((base,), (donor,))
