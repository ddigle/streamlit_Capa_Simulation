# Purpose: 단일 공정·주차의 표준 목표 Capa를 제품·WF 속성 Mix로 분해해 설명한다.

"""단일 공정·주차의 표준 목표 Capa를 제품·WF 속성 Mix로 분해해 설명한다."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pandas as pd

from capa_simulation.services.frame_contracts import (
    normalize_demand_basis,
    normalize_demand_basis_value,
    require_columns,
)
from capa_simulation.services.iso_week_calendar import (
    owning_month,
    valid_weeknum,
    weeknum_start_date,
)
from capa_simulation.services.standard_target_capacity import (
    build_weekly_standard_target_capacity,
    prepare_standard_target_required_equipment,
)
from capa_simulation.services.weighted_unit_capacity import effective_process_capacity_long


def build_standard_target_logic_analysis(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    weekly_availability: pd.DataFrame,
    weeknum: str,
    process: str,
    demand_basis: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Explain one process-week target through its product and WF mix."""
    normalized_weeknum = str(weeknum).strip().upper()
    if not valid_weeknum(normalized_weeknum):
        raise ValueError("로직 분석 Weeknum은 YY-W## 형식의 유효한 ISO 주차여야 합니다.")

    normalized_process = str(process).strip()
    if not normalized_process:
        raise ValueError("로직 분석 공정을 선택해야 합니다.")
    normalized_basis = normalize_demand_basis_value(demand_basis)
    if not normalized_basis:
        raise ValueError("로직 분석 소요기준을 선택해야 합니다.")

    week_start = weeknum_start_date(normalized_weeknum)
    # 월 경계 주차의 귀속 달은 `owning_month` 하나가 정한다(일수가 더 많은 달). 여기서
    # 월요일의 달을 다시 계산하면 화면이 제시한 선택지와 서비스가 보는 달이 갈려, 연 5주는
    # "해당하는 데이터가 없습니다" 로 끝난다 — 데이터는 있고 딴 달을 본 것이다.
    production_month = owning_month(week_start)

    required = ["생산계획년월", "공정", "소요기준", "양산구분"]
    require_columns(required_equipment, required, "소요대수 상세")

    source = required_equipment.copy()
    month = pd.to_numeric(source["생산계획년월"], errors="coerce")
    process_values = source["공정"].astype("string").str.strip()
    basis_values = normalize_demand_basis(source["소요기준"])
    source = source.loc[
        month.eq(production_month)
        & process_values.eq(normalized_process)
        & basis_values.eq(normalized_basis)
    ].reset_index(drop=True)
    source = prepare_standard_target_required_equipment(source)
    if source.empty:
        raise ValueError("선택한 주차·공정·소요기준에 해당하는 양산 소요대수 데이터가 없습니다.")

    week_end = week_start + timedelta(days=6)
    target = build_weekly_standard_target_capacity(
        required_equipment=source,
        run_day=run_day,
        weekly_availability=weekly_availability,
        start_date=week_start,
        end_date=week_end,
        detail_level="공정",
    )
    target = target.loc[
        target["Weeknum"].eq(normalized_weeknum)
        & target["공정"].eq(normalized_process)
        & target["소요기준"].eq(normalized_basis)
    ].reset_index(drop=True)
    if len(target) != 1:
        raise ValueError("선택한 조건의 공정 종합 표준 가능량을 하나로 확정할 수 없습니다.")

    contributions = effective_process_capacity_long(source, "WF 구분")
    total_load = float(cast(float, target.at[0, "원수요_부하량"]))
    total_required = float(cast(float, target.at[0, "STEP_소요대수"]))
    contributions = contributions.rename(columns={"공정 유효 Capa": "분류 유효 Capa"})
    contributions["부하량 비중"] = contributions["원수요_부하량"].div(
        total_load if total_load > 0 else float("nan")
    )
    contributions["소요대수 비중"] = contributions["STEP_소요대수"].div(
        total_required if total_required > 0 else float("nan")
    )
    contributions["Capa 역수 기여"] = contributions["부하량 비중"].div(
        contributions["분류 유효 Capa"].where(contributions["분류 유효 Capa"].gt(0))
    )
    contribution_columns = [
        "생산계획년월",
        "공정",
        "소요기준",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
        "원수요_부하량",
        "부하량 비중",
        "STEP_소요대수",
        "소요대수 비중",
        "분류 유효 Capa",
        "Capa 역수 기여",
    ]
    return target, contributions[contribution_columns].reset_index(drop=True)
