"""Display-only load-weighted summaries of detailed unit capacity."""

import pandas as pd

WEIGHTED_CAPACITY_HIERARCHY = ["공정", "양산구분", "제품정보", "Stack", "WF 구분"]


def weighted_unit_capacity_to_month_table(
    required_equipment: pd.DataFrame,
    detail_level: str,
) -> pd.DataFrame:
    """Build a process-route load-weighted unit capacity table for display only."""
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 대당 Capa 집계 수준입니다: {detail_level}")

    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    required = [
        "생산계획년월",
        *WEIGHTED_CAPACITY_HIERARCHY,
        "소요기준",
        "부하량",
        "대당 Capa",
    ]
    _require_columns(required_equipment, required)
    if required_equipment.empty:
        return pd.DataFrame(columns=display_dimensions)

    result = required_equipment[required].copy()
    _normalize_month(result)
    _normalize_text(result, WEIGHTED_CAPACITY_HIERARCHY)
    result["소요기준"] = (
        result["소요기준"].astype("string").str.strip().str.upper().replace({"WAFER": "WF"})
    )
    _assert_complete_keys(
        result,
        ["생산계획년월", *WEIGHTED_CAPACITY_HIERARCHY, "소요기준"],
    )

    process_basis_counts = result.groupby("공정", dropna=False)["소요기준"].nunique()
    multiple_basis_processes = process_basis_counts.loc[process_basis_counts.gt(1)].index.tolist()
    if multiple_basis_processes:
        raise ValueError(f"공정별 소요기준이 둘 이상입니다: {multiple_basis_processes[:5]}")

    result["부하량"] = _numeric(result["부하량"], "부하량")
    result["대당 Capa"] = _numeric(result["대당 Capa"], "대당 Capa")
    if result["부하량"].lt(0).any():
        raise ValueError("소요대수 상세의 부하량 값은 0 이상이어야 합니다.")
    if result["대당 Capa"].le(0).any():
        raise ValueError("소요대수 상세의 대당 Capa 값은 0보다 커야 합니다.")

    result["__weighted_capacity"] = result["부하량"] * result["대당 Capa"]
    group_keys = ["생산계획년월", *display_dimensions]
    grouped = result.groupby(group_keys, as_index=False, dropna=False).agg(
        부하량=("부하량", "sum"),
        가중_Capa=("__weighted_capacity", "sum"),
    )
    grouped["대당 Capa"] = grouped["가중_Capa"].div(
        grouped["부하량"].where(grouped["부하량"].gt(0))
    )

    table = grouped.pivot(
        index=display_dimensions,
        columns="생산계획년월",
        values="대당 Capa",
    ).reset_index()
    table.columns.name = None
    raw_month_columns = [column for column in table.columns if column not in display_dimensions]
    table = table.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(column for column in table.columns if column not in display_dimensions)
    return table[[*display_dimensions, *month_columns]]


def _normalize_month(data: pd.DataFrame) -> None:
    numeric = pd.to_numeric(data["생산계획년월"], errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    if not valid.all():
        raise ValueError("소요대수 상세의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    integer_month = numeric.astype("int64")
    if not integer_month.mod(100).between(1, 12).all():
        raise ValueError("소요대수 상세의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    data["생산계획년월"] = integer_month


def _normalize_text(data: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()


def _assert_complete_keys(data: pd.DataFrame, columns: list[str]) -> None:
    has_missing = any(data[column].isna().any() for column in columns)
    has_blank = any(data[column].eq("").any() for column in columns)
    if has_missing or has_blank:
        raise ValueError("소요대수 상세의 연결 키에 누락값이 있습니다.")


def _numeric(series: pd.Series, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"소요대수 상세의 {label} 컬럼에 숫자가 아닌 값이 있습니다.")
    return numeric.astype("float64")


def _require_columns(data: pd.DataFrame, required: list[str]) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"소요대수 상세 필수 컬럼이 없습니다: {', '.join(missing)}")
