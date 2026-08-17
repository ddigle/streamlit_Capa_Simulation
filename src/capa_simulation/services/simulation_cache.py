"""Shared content-addressed caches for simulation calculations."""

import pandas as pd
import streamlit as st

from capa_simulation.services.dashboard import (
    build_monthly_wafer_load,
    build_production_dashboard,
)
from capa_simulation.services.load_calculator import DemandBasis, build_monthly_volume
from capa_simulation.services.required_equipment import calculate_required_equipment
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.unit_capacity import calculate_unit_capacity


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
def get_monthly_volume(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    demand_basis: DemandBasis,
    detailed: bool,
    density_data: pd.DataFrame,
    display_order: pd.DataFrame,
) -> pd.DataFrame:
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
    return build_monthly_wafer_load(plan, yield_data, chip_qty)


def clear_simulation_caches() -> None:
    """Clear every shared calculation cache after an explicit source refresh."""
    get_unit_capacity.clear()
    get_required_equipment.clear()
    get_securement_rate.clear()
    get_monthly_volume.clear()
    get_production_dashboard.clear()
    get_monthly_wafer_load.clear()
