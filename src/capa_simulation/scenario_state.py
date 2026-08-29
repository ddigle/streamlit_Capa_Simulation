"""Per-session active scenario built from editable reference tables."""

from typing import TypedDict, cast

import pandas as pd
import streamlit as st

ACTIVE_SCENARIO_KEY = "active_scenario"
EDITABLE_SCENARIO_TABLES = (
    "RQ_PKG_PLAN",
    "RQ_YLD",
    "RQ_UPEH",
    "RQ_RUN_RATE",
    "RQ_VITAL",
    "RQ_RUN_DAY",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
)


class ActiveScenario(TypedDict):
    reference_version: int
    revision: int
    tables: dict[str, pd.DataFrame]


def ensure_active_scenario(
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
) -> ActiveScenario:
    """Return the current session scenario, initializing it from DuckDB if needed."""
    saved = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if _is_current_scenario(saved, reference_version):
        return cast(ActiveScenario, saved)
    return reset_active_scenario(reference_tables, reference_version)


def reset_active_scenario(
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
) -> ActiveScenario:
    """Replace every editable table with a fresh copy of the cached source."""
    missing = [name for name in EDITABLE_SCENARIO_TABLES if name not in reference_tables]
    if missing:
        raise KeyError(f"활성 시나리오 기준정보가 없습니다: {', '.join(missing)}")

    saved = st.session_state.get(ACTIVE_SCENARIO_KEY)
    previous_revision = int(saved.get("revision", -1)) if isinstance(saved, dict) else -1
    scenario: ActiveScenario = {
        "reference_version": reference_version,
        "revision": previous_revision + 1,
        "tables": {
            name: reference_tables[name].copy(deep=True) for name in EDITABLE_SCENARIO_TABLES
        },
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = scenario
    return scenario


def clear_active_scenario() -> None:
    """Discard the current session scenario so it reloads from source on next use."""
    st.session_state.pop(ACTIVE_SCENARIO_KEY, None)


def activate_scenario_tables(
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
    revision: int,
) -> ActiveScenario:
    """Replace the active calculation tables with one loaded persistent revision."""
    missing = [name for name in EDITABLE_SCENARIO_TABLES if name not in reference_tables]
    if missing:
        raise KeyError(f"불러온 리비전에 기준정보가 없습니다: {', '.join(missing)}")
    scenario: ActiveScenario = {
        "reference_version": reference_version,
        "revision": revision,
        "tables": {
            name: reference_tables[name].copy(deep=True) for name in EDITABLE_SCENARIO_TABLES
        },
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = scenario
    return scenario


def scenario_table(scenario: ActiveScenario, table_name: str) -> pd.DataFrame:
    """Return an isolated copy of one active scenario table."""
    if table_name not in scenario["tables"]:
        raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
    return scenario["tables"][table_name].copy(deep=True)


def scenario_month_table(
    scenario: ActiveScenario,
    table_name: str,
    start_month: int,
    end_month: int,
) -> pd.DataFrame:
    """Filter an active table first and copy only rows in the selected month range."""
    if table_name not in scenario["tables"]:
        raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
    from capa_simulation.services.month_filter import filter_month_range

    return filter_month_range(
        scenario["tables"][table_name],
        start_month,
        end_month,
        table_name,
    )


def apply_month_updates(
    scenario: ActiveScenario,
    replacements: dict[str, pd.DataFrame],
    start_month: int,
    end_month: int,
) -> ActiveScenario:
    """Atomically replace selected-month rows and publish a new scenario revision."""
    tables = dict(scenario["tables"])
    for table_name, replacement in replacements.items():
        if table_name not in tables:
            raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
        tables[table_name] = replace_month_range(
            tables[table_name],
            replacement,
            start_month,
            end_month,
            table_name,
        )

    updated: ActiveScenario = {
        "reference_version": scenario["reference_version"],
        "revision": scenario["revision"] + 1,
        "tables": tables,
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = updated
    return updated


def replace_month_range(
    current: pd.DataFrame,
    replacement: pd.DataFrame,
    start_month: int,
    end_month: int,
    table_name: str,
) -> pd.DataFrame:
    """Replace only the selected month range while preserving every other month."""
    if start_month > end_month:
        raise ValueError("활성 시나리오 적용 시작월이 종료월보다 늦습니다.")
    for data, label in ((current, "기존값"), (replacement, "편집값")):
        if "생산계획년월" not in data.columns:
            raise ValueError(f"{table_name} {label}에 생산계획년월 컬럼이 없습니다.")

    missing_columns = [column for column in current.columns if column not in replacement]
    if missing_columns:
        raise ValueError(
            f"{table_name} 편집값에 원본 컬럼이 없습니다: {', '.join(missing_columns)}"
        )

    current_months = _normalize_months(current["생산계획년월"], table_name, "기존값")
    replacement_months = _normalize_months(replacement["생산계획년월"], table_name, "편집값")
    outside_replacement = ~replacement_months.between(start_month, end_month)
    if outside_replacement.any():
        raise ValueError(f"{table_name} 편집값에 선택 범위 밖의 년월이 있습니다.")

    preserved = current.loc[~current_months.between(start_month, end_month)].copy()
    selected = replacement.reindex(columns=current.columns).copy()
    concat_frames = [frame.dropna(axis="columns", how="all") for frame in (preserved, selected)]
    result = pd.concat(concat_frames, ignore_index=True).reindex(columns=current.columns)
    result["생산계획년월"] = _normalize_months(result["생산계획년월"], table_name, "통합값")
    return result.sort_values("생산계획년월", kind="stable").reset_index(drop=True)


def _normalize_months(series: pd.Series, table_name: str, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    months = numeric.fillna(0).astype("int64")
    valid &= months.mod(100).between(1, 12)
    if not valid.all():
        raise ValueError(f"{table_name} {label}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    return months


def _is_current_scenario(value: object, reference_version: int) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("reference_version") != reference_version:
        return False
    tables = value.get("tables")
    return isinstance(tables, dict) and all(
        isinstance(tables.get(name), pd.DataFrame) for name in EDITABLE_SCENARIO_TABLES
    )
