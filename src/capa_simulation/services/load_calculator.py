"""PKG and wafer monthly volume calculations."""

from typing import Literal

import pandas as pd

DemandBasis = Literal["PKG", "Chip", "Wafer", "Density"]

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
YIELD_EDITOR_DIMENSIONS = ["제품정보", "Stack", "WF 구분", "수율 구분"]
YIELD_VALUE_COLUMNS = ["EDS_수율", "BE_수율"]
CHIP_KEYS = ["제품정보", "Stack", "WF 구분"]
CHIP_REQUIRED_COLUMNS = [*CHIP_KEYS, "구분_Chip", "Net Die"]
DENSITY_KEYS = ["제품정보", "Stack", "WF 구분"]
DENSITY_REQUIRED_COLUMNS = [*DENSITY_KEYS, "구분_Chip", "구분_EQ"]


def plan_to_edit_table(plan: pd.DataFrame) -> pd.DataFrame:
    """Pivot the default Long PKG plan into an editable month-column table."""
    required = ["생산계획년월", *PLAN_EDITOR_DIMENSIONS, "생산수량"]
    _require_columns(plan, required, "RQ_PKG_PLAN")
    prepared = _normalize_text(plan[required], PLAN_EDITOR_DIMENSIONS)
    prepared["생산계획년월"] = pd.to_numeric(
        prepared["생산계획년월"], errors="coerce"
    ).astype("Int64")
    prepared = _to_numeric(prepared, ["생산수량"], "RQ_PKG_PLAN")
    prepared["생산수량"] = prepared["생산수량"].fillna(0.0)

    if prepared[["생산계획년월", *PLAN_EDITOR_DIMENSIONS]].isna().any(axis=None):
        raise ValueError("RQ_PKG_PLAN의 편집 테이블 식별 컬럼에 누락값이 있습니다.")

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
    result[raw_month_columns] = result[raw_month_columns].fillna(0.0)
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
    long_plan["생산수량"] = long_plan["생산수량"].fillna(0.0)
    if long_plan["생산수량"].lt(0).any():
        raise ValueError("PKG PLAN 생산수량은 0 이상이어야 합니다.")
    long_plan = long_plan.loc[long_plan["생산수량"].gt(0)]
    return long_plan.sort_values(["생산계획년월", *PLAN_EDITOR_DIMENSIONS]).reset_index(
        drop=True
    )


def yield_to_edit_table(yield_data: pd.DataFrame) -> pd.DataFrame:
    """Pivot Long yield data into editable EDS/BE rows with month columns."""
    _require_columns(yield_data, YIELD_REQUIRED_COLUMNS, "RQ_YLD")
    prepared = _normalize_text(yield_data[YIELD_REQUIRED_COLUMNS], YIELD_KEYS[1:])
    prepared["생산계획년월"] = pd.to_numeric(
        prepared["생산계획년월"], errors="coerce"
    ).astype("Int64")
    prepared = _to_numeric(prepared, YIELD_VALUE_COLUMNS, "RQ_YLD")

    if prepared[YIELD_KEYS].isna().any(axis=None):
        raise ValueError("RQ_YLD의 연결 키에 누락값이 있습니다.")
    if prepared[YIELD_VALUE_COLUMNS].isna().any(axis=None):
        raise ValueError("RQ_YLD의 EDS_수율 또는 BE_수율에 누락값이 있습니다.")
    _assert_unique(prepared, YIELD_KEYS, "RQ_YLD")
    _validate_yield_range(prepared, "RQ_YLD")

    long_yield = prepared.melt(
        id_vars=YIELD_KEYS,
        value_vars=YIELD_VALUE_COLUMNS,
        var_name="수율 구분",
        value_name="수율",
    )
    result = long_yield.pivot(
        index=YIELD_EDITOR_DIMENSIONS,
        columns="생산계획년월",
        values="수율",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in YIELD_EDITOR_DIMENSIONS
    ]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in YIELD_EDITOR_DIMENSIONS]
    )
    return result[[*YIELD_EDITOR_DIMENSIONS, *month_columns]]


def yield_from_edit_table(yield_table: pd.DataFrame) -> pd.DataFrame:
    """Convert edited month-column yields back to the RQ_YLD Long format."""
    _require_columns(yield_table, YIELD_EDITOR_DIMENSIONS, "수율 편집값")
    month_columns = [
        column for column in yield_table.columns if column not in YIELD_EDITOR_DIMENSIONS
    ]
    invalid_months = [
        column
        for column in month_columns
        if not str(column).isdigit() or len(str(column)) != 6
    ]
    if invalid_months:
        raise ValueError(f"수율의 월 컬럼은 YYYYMM 형식이어야 합니다: {invalid_months}")

    prepared = _normalize_text(yield_table, YIELD_EDITOR_DIMENSIONS)
    invalid_types = sorted(
        set(prepared["수율 구분"].dropna()) - set(YIELD_VALUE_COLUMNS)
    )
    if invalid_types:
        raise ValueError(f"지원하지 않는 수율 구분이 있습니다: {invalid_types}")

    long_yield = prepared.melt(
        id_vars=YIELD_EDITOR_DIMENSIONS,
        value_vars=month_columns,
        var_name="생산계획년월",
        value_name="수율",
    )
    long_yield["생산계획년월"] = pd.to_numeric(
        long_yield["생산계획년월"], errors="raise"
    ).astype("Int64")
    long_yield = _to_numeric(long_yield, ["수율"], "수율 편집값")
    long_yield = long_yield.dropna(subset=["수율"])

    duplicated = long_yield.duplicated(
        ["생산계획년월", *YIELD_EDITOR_DIMENSIONS], keep=False
    )
    if duplicated.any():
        raise ValueError("수율 편집값의 월별 연결 키가 중복되었습니다.")

    result = long_yield.pivot(
        index=YIELD_KEYS,
        columns="수율 구분",
        values="수율",
    ).reset_index()
    result.columns.name = None
    _require_columns(result, YIELD_REQUIRED_COLUMNS, "수율 편집값")
    if result[YIELD_VALUE_COLUMNS].isna().any(axis=None):
        raise ValueError("동일한 기준에는 EDS_수율과 BE_수율이 모두 필요합니다.")
    _validate_yield_range(result, "수율 편집값")
    return result[YIELD_REQUIRED_COLUMNS].sort_values(YIELD_KEYS).reset_index(drop=True)


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


def _validate_yield_range(data: pd.DataFrame, table_name: str) -> None:
    invalid_rate = (
        data["EDS_수율"].le(0)
        | data["EDS_수율"].gt(1)
        | data["BE_수율"].le(0)
        | data["BE_수율"].gt(1)
    )
    if invalid_rate.any():
        raise ValueError(f"{table_name}의 수율은 0 초과 100% 이하여야 합니다.")


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

    _validate_yield_range(calculation, "RQ_YLD")
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


def calculate_density_load(plan: pd.DataFrame, density_data: pd.DataFrame) -> pd.DataFrame:
    """Calculate product density by capacity-bearing WF type in 100M Gb."""
    prepared_plan = _prepare_plan(plan)
    _require_columns(density_data, DENSITY_REQUIRED_COLUMNS, "RQ_CHIP_EQ")

    prepared_density = _normalize_text(
        density_data[DENSITY_REQUIRED_COLUMNS], DENSITY_KEYS
    )
    prepared_density = _to_numeric(
        prepared_density, ["구분_Chip", "구분_EQ"], "RQ_CHIP_EQ"
    )

    if prepared_density[DENSITY_KEYS].isna().any(axis=None):
        raise ValueError("RQ_CHIP_EQ의 연결 키에 누락값이 있습니다.")
    if prepared_density[["구분_Chip", "구분_EQ"]].isna().any(axis=None):
        raise ValueError("RQ_CHIP_EQ의 구분_Chip 또는 구분_EQ에 누락값이 있습니다.")
    _assert_unique(prepared_density, DENSITY_KEYS, "RQ_CHIP_EQ")

    if prepared_density["구분_Chip"].le(0).any():
        raise ValueError("RQ_CHIP_EQ.구분_Chip은 0보다 커야 합니다.")
    if prepared_density["구분_EQ"].le(0).any():
        raise ValueError("RQ_CHIP_EQ.구분_EQ는 0보다 커야 합니다.")

    calculation = prepared_plan.merge(
        prepared_density,
        on=["제품정보", "Stack"],
        how="left",
        validate="many_to_many",
        indicator="_density_merge",
    )
    if (calculation["_density_merge"] != "both").any():
        missing = (
            calculation.loc[
                calculation["_density_merge"] != "both", ["제품정보", "Stack"]
            ]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"RQ_CHIP_EQ가 연결되지 않는 제품이 있습니다: {missing}")
    calculation = calculation.drop(columns="_density_merge")
    calculation["물량"] = (
        calculation["생산수량"]
        * calculation["구분_Chip"]
        * calculation["구분_EQ"]
        / 100_000
    )
    return calculation


def _pivot_monthly(data: pd.DataFrame, detailed: bool) -> pd.DataFrame:
    classification_columns = [*CLASSIFICATION_COLUMNS]
    if detailed:
        classification_columns.append("WF 구분")
    grouped = (
        data.groupby(["생산계획년월", *classification_columns], as_index=False, dropna=False)[
            ["물량"]
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
    density_data: pd.DataFrame | None = None,
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
    if demand_basis == "Density":
        if density_data is None:
            raise ValueError("Density 계산에 RQ_CHIP_EQ 기준정보가 필요합니다.")
        return _pivot_monthly(
            calculate_density_load(prepared_plan, density_data), detailed
        )
    raise ValueError(f"지원하지 않는 소요기준입니다: {demand_basis}")
