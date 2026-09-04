# Purpose: Shared content-addressed caches for simulation calculations.

"""Shared content-addressed caches for simulation calculations."""

import hashlib
from collections.abc import Mapping
from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.services.dashboard import (
    build_monthly_wafer_load_from_load,
    build_production_dashboard,
)
from capa_simulation.services.equipment_availability import (
    build_weekly_equipment_availability,
)
from capa_simulation.services.load_calculator import (
    DemandBasis,
    build_monthly_volume,
    calculate_chip_and_wafer_loads,
)
from capa_simulation.services.required_equipment import (
    calculate_required_equipment,
    calculate_required_equipment_from_loads,
)
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.standard_target_capacity import (
    build_weekly_standard_target_capacity,
)
from capa_simulation.services.unit_capacity import calculate_unit_capacity

HomeSimulationCacheKey = tuple[int, str, int, int, str]


def build_home_simulation_cache_key(
    *,
    reference_version: int,
    scenario_token: str,
    start_month: int,
    end_month: int,
    display_order: pd.DataFrame,
) -> HomeSimulationCacheKey:
    """Build a small key covering every mutable HOME calculation input boundary.

    `get_home_simulation` 은 프레임 인자를 `_` 로 시작하게 두어 내용 해시를 건너뛴다.
    따라서 이 키가 입력 동일성을 혼자 책임진다. 예전에는 시나리오 편집 카운터
    (`revision`)를 넣었는데, 그 번호는 서로 다른 내용에서도 겹친다. 세션 편집은
    0,1,2... 로 올라가고 저장 리비전을 불러오면 그 번호가 그대로 들어오기 때문이다.
    `st.cache_data` 는 프로세스 전역이라 다른 브라우저 세션과도 겹쳤다.
    시나리오 내용이 바뀔 때마다 새로 발급되는 `content_token` 을 쓴다.
    """
    digest = hashlib.sha256()
    digest.update("\x1f".join(map(str, display_order.columns)).encode("utf-8"))
    digest.update("\x1f".join(map(str, display_order.dtypes)).encode("utf-8"))
    digest.update(
        pd.util.hash_pandas_object(display_order, index=True, categorize=True)
        .to_numpy(dtype="uint64")
        .tobytes()
    )
    return (
        reference_version,
        scenario_token,
        start_month,
        end_month,
        digest.hexdigest(),
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_unit_capacity(
    upeh: pd.DataFrame,
    run_rate: pd.DataFrame,
    vital: pd.DataFrame,
    module: pd.DataFrame,
    run_day: pd.DataFrame,
    lot_ratio: pd.DataFrame,
    wf_ratio: pd.DataFrame,
) -> pd.DataFrame:
    return calculate_unit_capacity(
        upeh=upeh,
        run_rate=run_rate,
        vital=vital,
        module=module,
        run_day=run_day,
        lot_ratio=lot_ratio,
        wf_ratio=wf_ratio,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_required_equipment(
    reqb: pd.DataFrame,
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    unit_capacity: pd.DataFrame,
) -> pd.DataFrame:
    # Load-calculation cache schema v2: normalize WF type before Dummy detection.
    return calculate_required_equipment(
        reqb=reqb,
        plan=plan,
        yield_data=yield_data,
        chip_qty=chip_qty,
        unit_capacity=unit_capacity,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_securement_rate(
    available_equipment: pd.DataFrame,
    required_equipment: pd.DataFrame,
) -> pd.DataFrame:
    return calculate_securement_rate(available_equipment, required_equipment)


@st.cache_data(show_spinner=False, max_entries=32)
def get_weekly_standard_target_capacity(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    weekly_availability: pd.DataFrame,
    start_date: date,
    end_date: date,
    detail_level: str,
) -> pd.DataFrame:
    """Cache the weekly standard target Capa for one active scenario and CSV input."""
    return build_weekly_standard_target_capacity(
        required_equipment=required_equipment,
        run_day=run_day,
        weekly_availability=weekly_availability,
        start_date=start_date,
        end_date=end_date,
        detail_level=detail_level,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_monthly_volume(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    demand_basis: DemandBasis,
    detailed: bool,
    density_data: pd.DataFrame,
    display_order: pd.DataFrame,
) -> pd.DataFrame:
    # Load-calculation cache schema v2: normalize WF type before Dummy detection.
    return build_monthly_volume(
        plan=plan,
        yield_data=yield_data,
        chip_qty=chip_qty,
        demand_basis=demand_basis,
        detailed=detailed,
        density_data=density_data,
        display_order=display_order,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def get_production_dashboard(
    plan: pd.DataFrame,
    density_data: pd.DataFrame,
    display_order: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return build_production_dashboard(plan, density_data, display_order)


@st.cache_data(show_spinner=False, max_entries=32)
def get_home_equipment_demand(
    reqb: pd.DataFrame,
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    unit_capacity: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build HOME Wafer totals and required equipment from one shared load join."""
    # Load-calculation cache schema v2: normalize WF type before Dummy detection.
    chip_load, wafer_load = calculate_chip_and_wafer_loads(plan, yield_data, chip_qty)
    monthly_wafer = build_monthly_wafer_load_from_load(wafer_load)
    required_equipment = calculate_required_equipment_from_loads(
        reqb=reqb,
        plan=plan,
        unit_capacity=unit_capacity,
        chip_load=chip_load,
        wafer_load=wafer_load,
    )
    return monthly_wafer, required_equipment


@st.cache_data(show_spinner=False, max_entries=16)
def get_home_simulation(
    cache_key: HomeSimulationCacheKey,
    _plan: pd.DataFrame,
    _yield_data: pd.DataFrame,
    _density_data: pd.DataFrame,
    _display_order: pd.DataFrame,
    _upeh: pd.DataFrame,
    _run_rate: pd.DataFrame,
    _vital: pd.DataFrame,
    _module: pd.DataFrame,
    _run_day: pd.DataFrame,
    _lot_ratio: pd.DataFrame,
    _wf_ratio: pd.DataFrame,
    _reqb: pd.DataFrame,
    _chip_qty: pd.DataFrame,
    _available_equipment: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Reuse HOME results while hashing only ``cache_key`` on warm reruns."""
    del cache_key
    # Load-calculation cache schema v2: normalize WF type before Dummy detection.
    monthly_density, production_detail = get_production_dashboard(
        _plan,
        _density_data,
        _display_order,
    )
    unit_capacity = get_unit_capacity(
        upeh=_upeh,
        run_rate=_run_rate,
        vital=_vital,
        module=_module,
        run_day=_run_day,
        lot_ratio=_lot_ratio,
        wf_ratio=_wf_ratio,
    )
    monthly_wafer, required_equipment = get_home_equipment_demand(
        reqb=_reqb,
        plan=_plan,
        yield_data=_yield_data,
        chip_qty=_chip_qty,
        unit_capacity=unit_capacity,
    )
    securement_rate = get_securement_rate(_available_equipment, required_equipment)
    return monthly_density, production_detail, monthly_wafer, securement_rate


@st.cache_data(show_spinner=False, max_entries=16)
def get_weekly_equipment_availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Reuse the weekly availability aggregation across reruns of the equipment page.

    가용설비 현황 페이지에는 fragment 가 없어 위젯 하나를 건드릴 때마다 페이지 전체가
    다시 실행된다. 이 집계는 조회기간 주차 수에 비례해 13주 300ms · 52주 1.5s 가 든다.
    세 프레임은 이미 리비전과 4개 필터가 반영된 결과라서 내용 해시가 곧 올바른 키다.
    """
    return build_weekly_equipment_availability(
        baseline,
        equipment,
        downtime,
        start_date=start_date,
        end_date=end_date,
    )


CAPACITY_INPUT_TABLES = (
    "RQ_UPEH",
    "RQ_RUN_RATE",
    "RQ_VITAL",
    "RQ_MODULE",
    "RQ_RUN_DAY",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
)

DEMAND_INPUT_TABLES = ("RQ_REQB", "RQ_PKG_PLAN", "RQ_YLD", "RQ_CHIP_QTY")

# 월 축이 없는 입력은 두 갈래다.
# - REFERENCE_INPUT_TABLES: 시나리오가 소유하지 않아 활성 리비전에서 그대로 읽는다.
# - SCENARIO_MONTHLESS_TABLES: 시나리오가 소유하지만 월 축이 없어 월 슬라이스를 하지
#   않는다. 가상 제품 복제 등록이 여기에 행을 추가한다.
REFERENCE_INPUT_TABLES = ("RQ_MODULE",)
SCENARIO_MONTHLESS_TABLES = ("RQ_CHIP_QTY",)
MONTHLESS_INPUT_TABLES = (*REFERENCE_INPUT_TABLES, *SCENARIO_MONTHLESS_TABLES)


def get_capacity_and_demand(
    tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """대당 Capa 와 그에 따른 소요대수를 한 번에 만든다.

    다섯 페이지가 같은 두 호출을 이어 붙이면서 RQ 이름 11개를 각자 손으로 적고 있었다.
    프레임을 어디서 가져오는지는 페이지마다 다르므로(활성 시나리오 · 월 필터 결과 ·
    사용자 편집본) 매핑만 받고 출처는 호출자에게 남긴다.

    두 하위 함수가 이미 캐시되어 있어 여기에는 캐시를 걸지 않는다.
    """
    unit_capacity = get_unit_capacity(
        upeh=tables["RQ_UPEH"],
        run_rate=tables["RQ_RUN_RATE"],
        vital=tables["RQ_VITAL"],
        module=tables["RQ_MODULE"],
        run_day=tables["RQ_RUN_DAY"],
        lot_ratio=tables["RQ_LOT_RATIO"],
        wf_ratio=tables["RQ_WF_RATIO"],
    )
    required_equipment = get_required_equipment(
        reqb=tables["RQ_REQB"],
        plan=tables["RQ_PKG_PLAN"],
        yield_data=tables["RQ_YLD"],
        chip_qty=tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    return unit_capacity, required_equipment


def clear_simulation_caches() -> None:
    """Clear every shared calculation cache after an explicit source refresh."""
    get_home_simulation.clear()
    get_unit_capacity.clear()
    get_required_equipment.clear()
    get_securement_rate.clear()
    get_monthly_volume.clear()
    get_production_dashboard.clear()
    get_home_equipment_demand.clear()
    get_weekly_standard_target_capacity.clear()
    get_weekly_equipment_availability.clear()
