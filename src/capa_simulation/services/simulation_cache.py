# Purpose: Shared content-addressed caches for simulation calculations.

"""Shared content-addressed caches for simulation calculations."""

import hashlib
from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.services.dashboard import (
    build_monthly_wafer_load,
    build_monthly_wafer_load_from_load,
    build_production_dashboard,
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

HomeSimulationCacheKey = tuple[int, int, int, int, str]


def build_home_simulation_cache_key(
    *,
    reference_version: int,
    scenario_revision: int,
    start_month: int,
    end_month: int,
    display_order: pd.DataFrame,
) -> HomeSimulationCacheKey:
    """Build a small key covering every mutable HOME calculation input boundary."""
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
        scenario_revision,
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
def get_monthly_wafer_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    # Load-calculation cache schema v2: normalize WF type before Dummy detection.
    return build_monthly_wafer_load(plan, yield_data, chip_qty)


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


def clear_simulation_caches() -> None:
    """Clear every shared calculation cache after an explicit source refresh."""
    get_home_simulation.clear()
    get_unit_capacity.clear()
    get_required_equipment.clear()
    get_securement_rate.clear()
    get_monthly_volume.clear()
    get_production_dashboard.clear()
    get_monthly_wafer_load.clear()
    get_home_equipment_demand.clear()
    get_weekly_standard_target_capacity.clear()
