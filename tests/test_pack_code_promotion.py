# Purpose: Pack Code 업무 키 승격이 저장은 행 분리로, 계산은 합산으로 갈라 놓는지 끝까지 고정한다.

"""Pack Code 승격의 끝단 계약.

사내 실데이터에서 같은 7키에 `Pack Code` 만 다른 계획 두 행이 "값 충돌" 로 보고되고 둘째
행이 버려졌다. 고침의 방향은 **저장 계층은 행을 나누고, 합산은 계산 계층이 한다** 이다.
한 층만 고치면 다른 층에서 조용히 되돌아오므로 원천에서 화면까지 한 줄로 이어서 고정한다.
"""

from datetime import date

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.load_calculator import (
    PLAN_EDITOR_DIMENSIONS,
    attach_plan_attributes,
    build_monthly_volume,
    plan_from_edit_table,
    plan_to_edit_table,
)
from capa_simulation.services.reference_conflicts import validated_distinct
from capa_simulation.services.standard_target_capacity import (
    PKG_EQUIVALENT_COLUMN,
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
)

_BASE_PLAN = {
    "생산계획년월": 202608,
    "양산구분": "양산",
    "CS": "MP",
    "제품정보": "Product-A",
    "Stack": "8H",
    "Capa Code": "C1",
    "Customer": "Customer-A",
    "제품타입": "HBM",
}


def _plan_frame() -> pd.DataFrame:
    """7키가 같고 `Pack Code` 만 다른 계획 두 행. 실데이터 결함을 그대로 옮긴 것이다."""
    return pd.DataFrame(
        [
            {**_BASE_PLAN, "Pack Code": "PK-5JK", "생산수량": 119.93},
            {**_BASE_PLAN, "Pack Code": "PK-5WC", "생산수량": 72.51},
        ]
    )


def _required_equipment() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "생산계획년월": 202608,
                "공정": "Process-A",
                "소요기준": "WF",
                "양산구분": "양산",
                "제품정보": "Product-A",
                "Stack": "8H",
                "Capa Code": "C1",
                "Customer": "Customer-A",
                "CS": "MP",
                "WF 구분": "Core",
                "부하량": 100.0,
                "소요대수": 1.0,
                "STEP_SEQ": step_seq,
            }
            for step_seq in ("S1", "S2")
        ]
    )


def test_pack_code_rows_survive_registration_and_are_summed_in_calculation() -> None:
    """원천 두 행 → 저장 두 행 → 격자 두 행 → 부하량 한 행(합) → PKG 환산 한 행(합)."""
    contract = load_core_data_contract()
    conflicts: list[dict[str, object]] = []

    # 1. 등록: 두 행이 살아남고 충돌로 보고되지 않는다.
    stored = validated_distinct(_plan_frame(), "RQ_PKG_PLAN", contract, conflicts)
    assert len(stored) == 2
    assert conflicts == []

    # 2. 편집 격자: Pack Code 가 행 차원이라 두 줄로 보인다.
    grid = plan_to_edit_table(stored)
    assert len(grid) == 2
    assert "Pack Code" in PLAN_EDITOR_DIMENSIONS
    assert sorted(grid["Pack Code"]) == ["PK-5JK", "PK-5WC"]

    # 3. 적용 왕복: 격자가 들고 있지 않은 `제품타입` 만 되붙는다.
    applied = attach_plan_attributes(plan_from_edit_table(grid), stored)
    assert sorted(applied["Pack Code"]) == ["PK-5JK", "PK-5WC"]
    assert set(applied["제품타입"]) == {"HBM"}
    assert applied["생산수량"].sum() == pytest.approx(192.44)

    # 4. 부하량 표: 화면 집계 단위에는 Pack Code 가 없으므로 한 행으로 합쳐진다.
    volume = build_monthly_volume(
        applied,
        yield_data=pd.DataFrame(),
        chip_qty=pd.DataFrame(),
        demand_basis="PKG",
    )
    assert len(volume) == 1
    assert volume.loc[0, "202608"] == pytest.approx(192.44)

    # 5. PKG 환산: 소요대수 상세에는 Pack Code 가 없어 7키 합계로 연결된다.
    required_equipment = _required_equipment()
    weekly_target = build_weekly_standard_target_capacity(
        required_equipment=required_equipment,
        run_day=pd.DataFrame({"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [10.0]}),
        weekly_availability=pd.DataFrame(
            {"공정": ["Process-A"], "Weeknum": ["26-W32"], "가용대수": [2.0]}
        ),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 9),
        detail_level="공정",
    )
    equivalent = add_pkg_equivalent_standard_target(
        weekly_target=weekly_target,
        required_equipment=required_equipment,
        plan=applied,
        detail_level="공정",
    )
    assert len(equivalent) == 1
    ratio = 192.44 / float(equivalent.loc[0, "원수요_부하량"])
    assert equivalent.loc[0, PKG_EQUIVALENT_COLUMN] == pytest.approx(
        float(equivalent.loc[0, "일 표준 가능량"]) * ratio
    )
