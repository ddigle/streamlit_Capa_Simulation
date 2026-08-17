import pandas as pd

SECUREMENT_DIMENSIONS = ["공정"]


def calculate_securement_rate(
    available_equipment: pd.DataFrame,
    required_equipment: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate monthly process securement rate as available / required."""
    available_required = ["생산계획년월", "공정", "가용대수"]
    required_required = ["생산계획년월", "공정", "소요대수"]
    _require_columns(available_equipment, available_required, "RQ_EQP_AVBL")
    _require_columns(required_equipment, required_required, "소요대수")

    available = available_equipment[available_required].copy()
    required = required_equipment[required_required].copy()
    _prepare_keys_and_value(available, "가용대수", "RQ_EQP_AVBL")
    _prepare_keys_and_value(required, "소요대수", "소요대수")

    available = available.groupby(["생산계획년월", "공정"], as_index=False, dropna=False)[
        ["가용대수"]
    ].sum()
    required = required.groupby(["생산계획년월", "공정"], as_index=False, dropna=False)[
        ["소요대수"]
    ].sum()

    positive_required = required.loc[required["소요대수"].gt(0)]
    availability_check = positive_required.merge(
        available[["생산계획년월", "공정"]],
        on=["생산계획년월", "공정"],
        how="left",
        indicator=True,
    )
    missing_available = availability_check["_merge"].ne("both")
    if missing_available.any():
        examples = (
            availability_check.loc[missing_available, ["생산계획년월", "공정"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"소요대수는 있지만 가용대수가 없는 공정이 있습니다: {examples}")

    result = available.merge(
        required,
        on=["생산계획년월", "공정"],
        how="left",
        validate="one_to_one",
    )
    result["소요대수"] = result["소요대수"].fillna(0.0)
    result["확보율"] = result["가용대수"] / result["소요대수"].where(result["소요대수"].gt(0))
    return result


def securement_rate_to_month_table(data: pd.DataFrame) -> pd.DataFrame:
    """Pivot monthly process securement rates for display."""
    required = ["생산계획년월", "공정", "확보율"]
    _require_columns(data, required, "확보율")
    result = data.pivot(
        index=SECUREMENT_DIMENSIONS,
        columns="생산계획년월",
        values="확보율",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [column for column in result.columns if column not in SECUREMENT_DIMENSIONS]
    result = result.rename(columns={month: str(int(month)) for month in raw_month_columns})
    month_columns = sorted(str(int(month)) for month in raw_month_columns)
    return result[[*SECUREMENT_DIMENSIONS, *month_columns]]


def _prepare_keys_and_value(data: pd.DataFrame, value_column: str, table_name: str) -> None:
    months = pd.to_numeric(data["생산계획년월"], errors="coerce")
    valid_months = months.notna() & months.mod(1).eq(0)
    integer_months = months.fillna(0).astype("int64")
    valid_months &= integer_months.mod(100).between(1, 12)
    if not valid_months.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    data["생산계획년월"] = integer_months
    data["공정"] = data["공정"].astype("string").str.strip()
    if data["공정"].isna().any() or data["공정"].eq("").any():
        raise ValueError(f"{table_name}의 공정에 누락값이 있습니다.")
    data[value_column] = pd.to_numeric(data[value_column], errors="coerce")
    if data[value_column].isna().any():
        raise ValueError(f"{table_name}.{value_column}에 숫자가 아닌 값이 있습니다.")
    if data[value_column].lt(0).any():
        raise ValueError(f"{table_name}.{value_column}은 0 이상이어야 합니다.")


def _require_columns(data: pd.DataFrame, required: list[str], table_name: str) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"{table_name} 필수 컬럼이 없습니다: {', '.join(missing)}")
