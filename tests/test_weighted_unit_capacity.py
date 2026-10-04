# Purpose: 공정 유효 Capa 집계가 한 공정 한 소요기준 업무 규칙을 지키는지 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.weighted_unit_capacity import effective_process_capacity_long


def _two_bases_for_one_process() -> pd.DataFrame:
    """같은 공정에 WF·CHIP 두 소요기준이 들어온 소요대수 상세."""
    return pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "공정": ["Process-A", "Process-A"],
            "소요기준": ["WF", "CHIP"],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["C1", "C1"],
            "Customer": ["Customer-A", "Customer-A"],
            "CS": ["MP", "MP"],
            "WF 구분": ["Core", "Core"],
            "부하량": [60.0, 40.0],
            "소요대수": [0.6, 0.2],
        }
    )


def test_effective_capacity_rejects_multiple_bases_for_one_process() -> None:
    """한 공정은 소요기준을 하나만 갖는다. **업무 규칙이다** (2026-09-05 확인).

    한 공정에 들어오는 유닛은 전부 같은 형태다. 환산으로 다른 소요기준의 유효 Capa 나
    재공 값을 만들 수는 있어도 공정 자체가 소요기준을 복수로 갖지는 않는다. 그러므로
    감지되면 멈추고 알리는 것이 맞다 — 조용히 한쪽을 고르면 그 공정의 유효 Capa 와
    소요대수가 통째로 틀린다.

    (표본 감사에서 "`PROCESS_SPECS` 가 공정마다 basis 를 하나씩 적어 둔 우연 아니냐" 고
    의심했으나 사용자 확인으로 업무 규칙임이 확정됐다. 완화하지 말 것.)
    """
    required_equipment = _two_bases_for_one_process()

    with pytest.raises(ValueError, match="공정 하나에 소요기준이 둘 이상"):
        effective_process_capacity_long(required_equipment, "공정")


def test_the_basis_conflict_message_names_the_conflicting_bases() -> None:
    """공정 이름만 알려 주면 기준정보의 어느 행을 고쳐야 하는지 알 수 없다."""
    required_equipment = _two_bases_for_one_process()

    with pytest.raises(ValueError) as caught:
        effective_process_capacity_long(required_equipment, "공정")

    message = str(caught.value)
    assert "Process-A" in message
    assert "CHIP" in message and "WF" in message
    assert "기준정보" in message
