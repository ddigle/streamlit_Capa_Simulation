# Purpose: Per-session active scenario built from editable reference tables.

"""Per-session active scenario built from editable reference tables."""

from typing import TypedDict, cast
from uuid import uuid4

import pandas as pd
import streamlit as st

ACTIVE_SCENARIO_KEY = "active_scenario"
# 이 세션에서 복제 등록한 가상 제품 목록. 리비전을 저장할 때 함께 기록해
# 공식버전 발행 시 실적과 대조할 수 없는 데이터가 섞였는지 알 수 있게 한다.
VIRTUAL_PRODUCTS_KEY = "session_virtual_products"
EDITABLE_SCENARIO_TABLES = (
    "RQ_PKG_PLAN",
    "RQ_YLD",
    # 가상 제품(기존 제품 복제 등록)이 행을 추가해야 하므로 편집 대상이다.
    # 월 축이 없어 scenario_month_table 이 아니라 scenario_table 로 읽는다.
    "RQ_CHIP_QTY",
    "RQ_CHIP_EQ",
    "RQ_UPEH",
    "RQ_RUN_RATE",
    "RQ_VITAL",
    "RQ_RUN_DAY",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
    "RQ_REQB",
    "RQ_EQP_OWN",
    "RQ_EQP_LENT",
    "RQ_EQP_AVBL",
)


class ActiveScenario(TypedDict):
    reference_version: int
    revision: int
    # 테이블 내용이 바뀔 때마다 새로 발급하는 식별자다. `revision` 은 저장본과 비교해
    # 미저장 변경을 감지하는 카운터여서 서로 다른 내용이 같은 번호를 가질 수 있다.
    # (세션 편집은 0,1,2... 로 올라가고 저장 리비전을 불러오면 그 번호가 그대로 들어온다.)
    # 계산 캐시 키에는 반드시 이 토큰을 쓴다.
    content_token: str
    tables: dict[str, pd.DataFrame]


def _new_content_token() -> str:
    return uuid4().hex


def ensure_active_scenario(
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
) -> ActiveScenario:
    """Return the current session scenario, initializing it from DuckDB if needed."""
    saved = st.session_state.get(ACTIVE_SCENARIO_KEY)
    if _is_current_scenario(saved, reference_version):
        scenario = cast(ActiveScenario, saved)
        # 이 필드를 도입하기 전에 만들어진 세션 상태에는 토큰이 없다. 편집 중인 표를
        # 버리지 않도록 폐기하지 않고 채워 넣는다.
        if not isinstance(scenario.get("content_token"), str):
            scenario["content_token"] = _new_content_token()
            st.session_state[ACTIVE_SCENARIO_KEY] = scenario
        return scenario
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
        "content_token": _new_content_token(),
        "tables": {
            name: reference_tables[name].copy(deep=True) for name in EDITABLE_SCENARIO_TABLES
        },
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = scenario
    # 시나리오 자체가 바뀌므로 이 세션의 가상 제품 등록 이력도 함께 버린다.
    clear_virtual_products()
    return scenario


def session_virtual_products() -> tuple[object, ...]:
    """이 세션이 복제 등록한 가상 제품 목록을 돌려준다."""
    saved = st.session_state.get(VIRTUAL_PRODUCTS_KEY)
    return tuple(saved) if isinstance(saved, tuple | list) else ()


def remember_virtual_product(record: object) -> None:
    """복제 등록 한 건을 세션 목록에 더한다."""
    st.session_state[VIRTUAL_PRODUCTS_KEY] = (*session_virtual_products(), record)


def clear_virtual_products() -> None:
    """시나리오를 원본이나 저장 리비전으로 갈아끼울 때 목록을 비운다."""
    st.session_state.pop(VIRTUAL_PRODUCTS_KEY, None)


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
        "content_token": _new_content_token(),
        "tables": {
            name: reference_tables[name].copy(deep=True) for name in EDITABLE_SCENARIO_TABLES
        },
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = scenario
    # 시나리오 자체가 바뀌므로 이 세션의 가상 제품 등록 이력도 함께 버린다.
    clear_virtual_products()
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
        "content_token": _new_content_token(),
        "tables": tables,
    }
    st.session_state[ACTIVE_SCENARIO_KEY] = updated
    return updated


def apply_table_updates(
    scenario: ActiveScenario,
    replacements: dict[str, pd.DataFrame],
) -> ActiveScenario:
    """월 범위를 가리지 않고 테이블 전체를 원자적으로 교체하고 새 토큰을 발급한다.

    `apply_month_updates` 는 선택 월 구간만 갈아끼우므로 `생산계획년월` 이 없는 테이블
    (`RQ_CHIP_QTY`·`RQ_CHIP_EQ`)에는 쓸 수 없다. 가상 제품 복제처럼 완성된 테이블을
    통째로 넘기는 경우를 위한 경로다.
    """
    tables = dict(scenario["tables"])
    for table_name, replacement in replacements.items():
        if table_name not in tables:
            raise KeyError(f"활성 시나리오 테이블이 없습니다: {table_name}")
        tables[table_name] = replacement.reset_index(drop=True)

    updated: ActiveScenario = {
        "reference_version": scenario["reference_version"],
        "revision": scenario["revision"] + 1,
        "content_token": _new_content_token(),
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
