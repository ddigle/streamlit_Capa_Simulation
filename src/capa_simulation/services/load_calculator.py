"""PKG and wafer monthly volume calculations."""

from typing import Literal

import pandas as pd

DemandBasis = Literal["PKG", "Chip", "Wafer"]

CLASSIFICATION_COLUMNS = ["양산구분", "제품정보", "Stack"]
PLAN_EDITOR_DIMENSIONS = [
    "양산구분",
    "CS",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
]
PLAN_REQUIRED_COLUMNS = [
    "생산계획년월",
    *CLASSIFICATION_COLUMNS,
    "생산수량",
]
YIELD_KEYS = ["생산계획년월", "제품정보", "Stack", "WF 구분"]
YIELD_REQUIRED_COLUMNS = [*YIELD_KEYS, "EDS_수율", "BE_수율"]
CHIP_KEYS = ["제품정보", "Stack", "WF 구분"]
CHIP_REQUIRED_COLUMNS = [*CHIP_KEYS, "구분_Chip", "Net Die"]


def plan_to_edit_table(plan: pd.DataFrame) -> pd.DataFrame:
    """Pivot the default Long PKG plan into an editable month-column table."""
    required = ["생산계획년월", *PLAN_EDITOR_DIMENSIONS, "생산수량"]
    _require_columns(plan, required, "RQ_PKG_PLAN")
    prepared = _normalize_text(plan[required], PLAN_EDITOR_DIMENSIONS)
    prepared["생산계획년월"] = pd.to_numeric(
        prepared["생산계획년월"], errors="coerce"
    ).astype("Int64")
    prepared = _to_numeric(prepared, ["생산수량"], "RQ_PKG_PLAN")

    if prepared[["생산계획년월", *PLAN_EDITOR_DIMENSIONS]].isna().any(axis=None):
        raise ValueError("RQ_PKG_PLAN의 편집 테이블 식별 컬럼에 누락값이 있습니다.")
    if prepared["생산수량"].isna().any():
        raise ValueError("RQ_PKG_PLAN.생산수량에 누락값이 있습니다.")

    duplicate_keys = [*PLAN_EDITOR_DIMENSIONS, "생산계획년월"]
    duplicated = prepared.duplicated(duplicate_keys, keep=False)
    if duplicated.any():
        example = (
            prepared.loc[duplicated, duplicate_keys]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_PKG_PLAN의 월별 계획 키가 중복되었습니다: {example}")

    result = prepared.pivot(
        index=PLAN_EDITOR_DIMENSIONS,
        columns="생산계획년월",
        values="생산수량",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in PLAN_EDITOR_DIMENSIONS]
    )
    return result[[*PLAN_EDITOR_DIMENSIONS, *month_columns]]


def plan_from_edit_table(plan_table: pd.DataFrame) -> pd.DataFrame:
    """Convert the edited month-column plan back to the calculation Long format."""
    _require_columns(plan_table, PLAN_EDITOR_DIMENSIONS, "PKG PLAN 편집값")
    month_columns = [
        column for column in plan_table.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    invalid_months = [
        column
        for column in month_columns
        if not str(column).isdigit() or len(str(column)) != 6
    ]
    if invalid_months:
        raise ValueError(f"PKG PLAN의 월 컬럼은 YYYYMM 형식이어야 합니다: {invalid_months}")

    long_plan = plan_table.melt(
        id_vars=PLAN_EDITOR_DIMENSIONS,
        value_vars=month_columns,
        var_name="생산계획년월",
        value_name="생산수량",
    )
    long_plan["생산계획년월"] = pd.to_numeric(
        long_plan["생산계획년월"], errors="raise"
    ).astype("Int64")
    long_plan = _to_numeric(long_plan, ["생산수량"], "PKG PLAN 편집값")
    if long_plan["생산수량"].isna().any():
        raise ValueError("PKG PLAN에 비어 있는 생산수량이 있습니다.")
    if long_plan["생산수량"].lt(0).any():
        raise ValueError("PKG PLAN 생산수량은 0 이상이어야 합니다.")
    return long_plan.sort_values(["생산계획년월", *PLAN_EDITOR_DIMENSIONS]).reset_index(
        drop=True
    )


def _require_columns(data: pd.DataFrame, required: list[str], table_name: str) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"{table_name} 필수 컬럼이 없습니다: {', '.join(missing)}")


def _normalize_text(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    normalized = data.copy()
    for column in columns:
        normalized[column] = normalized[column].astype("string").str.strip()
    return normalized


def _to_numeric(data: pd.DataFrame, columns: list[str], table_name: str) -> pd.DataFrame:
    converted = data.copy()
    for column in columns:
        original = converted[column]
        converted[column] = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & converted[column].isna()
        if invalid.any():
            raise ValueError(f"{table_name}.{column}에 숫자가 아닌 값이 있습니다.")
    return converted


def _assert_unique(data: pd.DataFrame, keys: list[str], table_name: str) -> None:
    duplicated = data.duplicated(keys, keep=False)
    if duplicated.any():
        example = data.loc[duplicated, keys].drop_duplicates().head(5).to_dict("records")
        raise ValueError(f"{table_name} 연결 키가 중복되었습니다: {example}")


def _prepare_plan(plan: pd.DataFrame) -> pd.DataFrame:
    _require_columns(plan, PLAN_REQUIRED_COLUMNS, "RQ_PKG_PLAN")
    prepared = _normalize_text(plan[PLAN_REQUIRED_COLUMNS], CLASSIFICATION_COLUMNS)
    prepared["생산계획년월"] = pd.to_numeric(
        prepared["생산계획년월"], errors="coerce"
    ).astype("Int64")
    prepared = _to_numeric(prepared, ["생산수량"], "RQ_PKG_PLAN")

    missing_keys = prepared[["생산계획년월", *CLASSIFICATION_COLUMNS]].isna().any(axis=1)
    if missing_keys.any():
        raise ValueError("RQ_PKG_PLAN에 월별 물량 분류 키가 누락된 행이 있습니다.")
    return prepared


def _prepare_load_base(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Expand each plan by WF type and attach the matching yield and chip standards."""
    prepared_plan = _prepare_plan(plan)
    _require_columns(yield_data, YIELD_REQUIRED_COLUMNS, "RQ_YLD")
    _require_columns(chip_qty, CHIP_REQUIRED_COLUMNS, "RQ_CHIP_QTY")

    prepared_yield = _normalize_text(yield_data[YIELD_REQUIRED_COLUMNS], YIELD_KEYS[1:])
    prepared_yield["생산계획년월"] = pd.to_numeric(
        prepared_yield["생산계획년월"], errors="coerce"
    ).astype("Int64")
    prepared_yield = _to_numeric(
        prepared_yield, ["EDS_수율", "BE_수율"], "RQ_YLD"
    )

    prepared_chip = _normalize_text(chip_qty[CHIP_REQUIRED_COLUMNS], CHIP_KEYS)
    prepared_chip = _to_numeric(
        prepared_chip, ["구분_Chip", "Net Die"], "RQ_CHIP_QTY"
    )

    _assert_unique(prepared_yield, YIELD_KEYS, "RQ_YLD")
    _assert_unique(prepared_chip, CHIP_KEYS, "RQ_CHIP_QTY")

    expanded = prepared_plan.merge(
        prepared_chip,
        on=["제품정보", "Stack"],
        how="left",
        validate="many_to_many",
        indicator="_chip_merge",
    )
    if (expanded["_chip_merge"] != "both").any():
        missing = (
            expanded.loc[expanded["_chip_merge"] != "both", ["제품정보", "Stack"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_CHIP_QTY가 연결되지 않는 제품이 있습니다: {missing}")
    expanded = expanded.drop(columns="_chip_merge")

    calculation = expanded.merge(
        prepared_yield,
        on=YIELD_KEYS,
        how="left",
        validate="many_to_one",
        indicator="_yield_merge",
    )
    if (calculation["_yield_merge"] != "both").any():
        missing = (
            calculation.loc[calculation["_yield_merge"] != "both", YIELD_KEYS]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_YLD가 연결되지 않는 기준이 있습니다: {missing}")
    calculation = calculation.drop(columns="_yield_merge")

    invalid_rate = (
        calculation["EDS_수율"].le(0)
        | calculation["EDS_수율"].gt(1)
        | calculation["BE_수율"].le(0)
        | calculation["BE_수율"].gt(1)
    )
    if invalid_rate.any():
        raise ValueError("EDS_수율 또는 BE_수율이 0 초과 1 이하 범위를 벗어났습니다.")
    if calculation["Net Die"].le(0).any():
        raise ValueError("Net Die는 0보다 커야 합니다.")
    if calculation["구분_Chip"].lt(0).any():
        raise ValueError("구분_Chip은 0 이상이어야 합니다.")

    return calculation


def calculate_chip_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate Top/Core/Buffer/Slave/Master and Dummy chip volume in Kea."""
    calculation = _prepare_load_base(plan, yield_data, chip_qty)
    calculation["물량"] = (
        calculation["생산수량"] * calculation["구분_Chip"] / calculation["BE_수율"]
    )
    is_dummy = calculation["WF 구분"].eq("Dummy")
    calculation.loc[is_dummy, "물량"] = (
        calculation.loc[is_dummy, "생산수량"]
        * calculation.loc[is_dummy, "구분_Chip"]
        / calculation.loc[is_dummy, "EDS_수율"]
        / calculation.loc[is_dummy, "BE_수율"]
        * (1 - calculation.loc[is_dummy, "EDS_수율"])
    )
    return calculation


def calculate_wafer_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate regular and Dummy wafer volume in sheets."""
    calculation = _prepare_load_base(plan, yield_data, chip_qty)
    calculation["물량"] = (
        calculation["생산수량"]
        * 1_000
        * calculation["구분_Chip"]
        / calculation["EDS_수율"]
        / calculation["BE_수율"]
        / calculation["Net Die"]
    )
    is_dummy = calculation["WF 구분"].eq("Dummy")
    calculation.loc[is_dummy, "물량"] *= 1 - calculation.loc[is_dummy, "EDS_수율"]
    return calculation


def _pivot_monthly(data: pd.DataFrame, detailed: bool) -> pd.DataFrame:
    classification_columns = [*CLASSIFICATION_COLUMNS]
    if detailed:
        classification_columns.append("WF 구분")
    grouped = (
        data.groupby(["생산계획년월", *classification_columns], as_index=False, dropna=False)[
            "물량"
        ]
        .sum()
        .sort_values([*classification_columns, "생산계획년월"])
    )
    pivoted = grouped.pivot(
        index=classification_columns,
        columns="생산계획년월",
        values="물량",
    ).fillna(0)
    pivoted.columns = [str(int(month)) for month in pivoted.columns]
    return pivoted.reset_index()


def build_monthly_volume(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    demand_basis: DemandBasis,
    detailed: bool = False,
) -> pd.DataFrame:
    """Return a monthly matrix grouped by production class, product, and stack."""
    prepared_plan = _prepare_plan(plan)
    if demand_basis == "PKG":
        volume = prepared_plan.rename(columns={"생산수량": "물량"})
        if detailed:
            volume["WF 구분"] = "PKG"
        return _pivot_monthly(volume, detailed)
    if demand_basis == "Chip":
        return _pivot_monthly(
            calculate_chip_load(prepared_plan, yield_data, chip_qty), detailed
        )
    if demand_basis == "Wafer":
        return _pivot_monthly(
            calculate_wafer_load(prepared_plan, yield_data, chip_qty), detailed
        )
    raise ValueError(f"지원하지 않는 소요기준입니다: {demand_basis}")
