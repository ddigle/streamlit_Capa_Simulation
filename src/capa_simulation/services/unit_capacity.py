import pandas as pd

PERFORMANCE_KEYS = [
    "생산계획년월",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
]
UNIT_CAPACITY_DIMENSIONS = [
    "공정",
    "Area_Name",
    "소요기준",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "STEP_SEQ",
    "MCP_SEQ",
]
UNIMPLEMENTED_BASES = {"BOX", "PCB"}
CAPACITY_EXCLUSIONS_ATTR = "excluded_capacity_rows"


def calculate_unit_capacity(
    upeh: pd.DataFrame,
    run_rate: pd.DataFrame,
    vital: pd.DataFrame,
    module: pd.DataFrame,
    run_day: pd.DataFrame,
    lot_ratio: pd.DataFrame,
    wf_ratio: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate monthly per-equipment capacity for Main and MI process rows."""
    performance = _prepare_performance(upeh)
    if performance.empty:
        empty_result = pd.DataFrame(
            columns=[
                "생산계획년월",
                *UNIT_CAPACITY_DIMENSIONS,
                "환산_UPEH",
                "대당 Capa",
            ]
        )
        empty_result.attrs[CAPACITY_EXCLUSIONS_ATTR] = pd.DataFrame()
        return empty_result

    result = performance
    result = _join_reference(
        result,
        run_rate,
        ["생산계획년월", "공정", "양산구분"],
        "CAPA_RUN_RATE",
        "RQ_RUN_RATE",
    )
    result = _join_reference(
        result,
        vital,
        ["생산계획년월", "공정", "양산구분"],
        "편중률",
        "RQ_VITAL",
    )
    result = _join_reference(result, module, ["공정"], "모듈수", "RQ_MODULE")
    result = _join_reference(
        result,
        run_day,
        ["생산계획년월", "공정"],
        "RUN_DAY",
        "RQ_RUN_DAY",
    )
    result = _join_reference(
        result,
        lot_ratio,
        PERFORMANCE_KEYS,
        "Lot 측정률",
        "RQ_LOT_RATIO",
        missing_value_default=1.0,
    )
    result = _join_reference(
        result,
        wf_ratio,
        PERFORMANCE_KEYS,
        "WF측정률",
        "RQ_WF_RATIO",
        missing_value_default=1.0,
    )

    for column, table_name in (
        ("편중률", "RQ_VITAL"),
        ("모듈수", "RQ_MODULE"),
        ("RUN_DAY", "RQ_RUN_DAY"),
        ("Lot 측정률", "RQ_LOT_RATIO"),
    ):
        _assert_positive(result, column, table_name)

    nonpositive_wf_ratio = result["WF측정률"].le(0)
    excluded_frames = [_exclusion_rows(result, nonpositive_wf_ratio, "WF측정률 0 이하")]
    result = result.loc[~nonpositive_wf_ratio].copy()

    result["대당 Capa"] = (
        result["환산_UPEH"]
        * 24.0
        * result["CAPA_RUN_RATE"]
        / result["편중률"]
        * result["모듈수"]
        * result["RUN_DAY"]
        / result["Lot 측정률"]
        / result["WF측정률"]
    )
    nonpositive_capacity = result["대당 Capa"].le(0)
    excluded_frames.append(_exclusion_rows(result, nonpositive_capacity, "대당 Capa 0 이하"))
    result = result.loc[~nonpositive_capacity].copy()
    columns = ["생산계획년월", *UNIT_CAPACITY_DIMENSIONS, "환산_UPEH", "대당 Capa"]
    output = (
        result[columns]
        .sort_values(["생산계획년월", *UNIT_CAPACITY_DIMENSIONS])
        .reset_index(drop=True)
    )
    output.attrs[CAPACITY_EXCLUSIONS_ATTR] = pd.concat(excluded_frames, ignore_index=True)
    return output


def unit_capacity_to_month_table(unit_capacity: pd.DataFrame) -> pd.DataFrame:
    """Pivot calculated unit capacity into month columns for display."""
    required = ["생산계획년월", *UNIT_CAPACITY_DIMENSIONS, "대당 Capa"]
    _require_columns(unit_capacity, required, "대당 Capa")
    if unit_capacity.empty:
        return pd.DataFrame(columns=UNIT_CAPACITY_DIMENSIONS)
    result = unit_capacity.pivot(
        index=UNIT_CAPACITY_DIMENSIONS,
        columns="생산계획년월",
        values="대당 Capa",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in UNIT_CAPACITY_DIMENSIONS
    ]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in UNIT_CAPACITY_DIMENSIONS]
    )
    return result[[*UNIT_CAPACITY_DIMENSIONS, *month_columns]]


def _prepare_performance(data: pd.DataFrame) -> pd.DataFrame:
    table_name = "RQ_UPEH"
    required = [*PERFORMANCE_KEYS, "소요기준", "UPEH", "ST"]
    _require_columns(data, required, table_name)
    result = data[required].copy()
    if result.empty:
        result["환산_UPEH"] = pd.Series(dtype="float64")
        return result
    _normalize_month(result, table_name)
    _normalize_keys(result, [key for key in PERFORMANCE_KEYS if key != "생산계획년월"])
    result["Area_Name"] = result["Area_Name"].astype("string").str.strip()
    result["소요기준"] = result["소요기준"].astype("string").str.strip().str.upper()
    result = result.loc[~result["소요기준"].isin(UNIMPLEMENTED_BASES)].copy()
    if result.empty:
        result["환산_UPEH"] = pd.Series(dtype="float64")
        return result
    _assert_complete_keys(result, [*PERFORMANCE_KEYS, "소요기준"], table_name)
    _normalize_area_name(result, table_name)
    _assert_unique(result, [*PERFORMANCE_KEYS, "소요기준"], table_name)

    upeh_values = pd.to_numeric(result["UPEH"], errors="coerce")
    st_values = pd.to_numeric(result["ST"], errors="coerce")
    main_rows = result["Area_Name"].eq("Main")
    mi_rows = result["Area_Name"].eq("MI")
    if upeh_values.loc[main_rows].isna().any():
        raise ValueError("RQ_UPEH의 Main 행에 UPEH 누락값 또는 숫자가 아닌 값이 있습니다.")
    if st_values.loc[mi_rows].isna().any():
        raise ValueError("RQ_UPEH의 MI 행에 ST 누락값 또는 숫자가 아닌 값이 있습니다.")
    if st_values.loc[mi_rows].le(0).any():
        raise ValueError("RQ_UPEH의 MI 행 ST 값은 0보다 커야 합니다.")

    result["환산_UPEH"] = upeh_values
    result.loc[mi_rows, "환산_UPEH"] = 3600.0 / st_values.loc[mi_rows]
    kea_rows = result["소요기준"].isin(["CHIP", "PKG"])
    result.loc[kea_rows, "환산_UPEH"] = result.loc[kea_rows, "환산_UPEH"] / 1000.0
    return result


def _join_reference(
    base: pd.DataFrame,
    reference: pd.DataFrame,
    keys: list[str],
    value_column: str,
    table_name: str,
    *,
    missing_value_default: float | None = None,
) -> pd.DataFrame:
    _require_columns(reference, [*keys, value_column], table_name)
    prepared = reference[[*keys, value_column]].copy()
    if "생산계획년월" in keys:
        _normalize_month(prepared, table_name)
    _normalize_keys(prepared, [key for key in keys if key != "생산계획년월"])
    _assert_complete_keys(prepared, keys, table_name)
    if "Area_Name" in keys:
        _normalize_area_name(prepared, table_name)
    _assert_unique(prepared, keys, table_name)
    prepared[value_column] = _numeric_column(
        prepared,
        value_column,
        table_name,
        missing_value_default=missing_value_default,
    )
    result = base.merge(prepared, on=keys, how="left", validate="many_to_one")
    missing = result[value_column].isna()
    if missing.any():
        examples = result.loc[missing, keys].drop_duplicates().head(5).to_dict("records")
        raise ValueError(f"{table_name} 연결값이 없는 대당 Capa 기준이 있습니다: {examples}")
    return result


def _normalize_keys(data: pd.DataFrame, keys: list[str]) -> None:
    for key in keys:
        data[key] = data[key].astype("string").str.strip()


def _normalize_area_name(data: pd.DataFrame, table_name: str) -> None:
    area_names = data["Area_Name"].astype("string").str.strip().str.casefold()
    invalid_area = ~area_names.isin(["main", "mi"])
    if invalid_area.any():
        examples = data.loc[invalid_area, "Area_Name"].drop_duplicates().head(5).tolist()
        raise ValueError(f"{table_name}의 Area_Name은 Main 또는 MI여야 합니다: {examples}")
    data["Area_Name"] = area_names.map({"main": "Main", "mi": "MI"})


def _normalize_month(data: pd.DataFrame, table_name: str) -> None:
    numeric = pd.to_numeric(data["생산계획년월"], errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    if not valid.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    integer_month = numeric.astype("int64")
    if not integer_month.mod(100).between(1, 12).all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    data["생산계획년월"] = integer_month


def _assert_complete_keys(data: pd.DataFrame, keys: list[str], table_name: str) -> None:
    has_missing = any(data[key].isna().any() for key in keys)
    has_blank = any(data[key].eq("").any() for key in keys)
    if has_missing or has_blank:
        raise ValueError(f"{table_name}의 연결 키에 누락값이 있습니다.")


def _assert_unique(data: pd.DataFrame, keys: list[str], table_name: str) -> None:
    duplicated = data.duplicated(keys, keep=False)
    if duplicated.any():
        examples = data.loc[duplicated, keys].drop_duplicates().head(5).to_dict("records")
        raise ValueError(f"{table_name}의 연결 키가 중복되었습니다: {examples}")


def _numeric_column(
    data: pd.DataFrame,
    column: str,
    table_name: str,
    *,
    missing_value_default: float | None = None,
) -> pd.Series:
    values = data[column]
    if missing_value_default is not None:
        blank = values.isna() | values.astype("string").str.strip().eq("").fillna(False)
        values = values.mask(blank, missing_value_default)
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{table_name}의 {column} 컬럼에 숫자가 아닌 값이 있습니다.")
    return numeric.astype("float64")


def _assert_positive(data: pd.DataFrame, column: str, table_name: str) -> None:
    if data[column].le(0).any():
        raise ValueError(f"{table_name}의 {column} 값은 0보다 커야 합니다.")


def _exclusion_rows(data: pd.DataFrame, mask: pd.Series, reason: str) -> pd.DataFrame:
    """Keep the joined reference values used by an excluded capacity row."""
    excluded = data.loc[mask].copy()
    excluded["제외사유"] = reason
    return excluded


def _require_columns(data: pd.DataFrame, required: list[str], table_name: str) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"{table_name} 필수 컬럼이 없습니다: {', '.join(missing)}")
