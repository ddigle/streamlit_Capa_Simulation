"""Display-only load-weighted summaries of detailed unit capacity."""

import pandas as pd

WEIGHTED_CAPACITY_HIERARCHY = ["공정", "양산구분", "제품정보", "Stack", "WF 구분"]
DEMAND_ID_COLUMNS = [
    "생산계획년월",
    "공정",
    "소요기준",
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
    "WF 구분",
]


def effective_process_capacity_to_month_table(
    required_equipment: pd.DataFrame,
    detail_level: str,
) -> pd.DataFrame:
    """Build effective Capa as unique demand load divided by summed STEP needs."""
    grouped = effective_process_capacity_long(required_equipment, detail_level)
    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    if grouped.empty:
        return pd.DataFrame(columns=display_dimensions)

    table = grouped.pivot(
        index=display_dimensions,
        columns="생산계획년월",
        values="공정 유효 Capa",
    ).reset_index()
    table.columns.name = None
    raw_month_columns = [column for column in table.columns if column not in display_dimensions]
    table = table.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(column for column in table.columns if column not in display_dimensions)
    return table[[*display_dimensions, *month_columns]]


def effective_process_capacity_long(
    required_equipment: pd.DataFrame,
    detail_level: str,
) -> pd.DataFrame:
    """Return effective process Capa and its numerator/denominator in long form."""
    if detail_level not in WEIGHTED_CAPACITY_HIERARCHY:
        raise ValueError(f"지원하지 않는 공정 유효 Capa 집계 수준입니다: {detail_level}")

    level_index = WEIGHTED_CAPACITY_HIERARCHY.index(detail_level)
    hierarchy_dimensions = WEIGHTED_CAPACITY_HIERARCHY[: level_index + 1]
    display_dimensions = ["공정", "소요기준", *hierarchy_dimensions[1:]]
    required = [*DEMAND_ID_COLUMNS, "부하량", "소요대수"]
    _require_columns(required_equipment, required)
    if required_equipment.empty:
        return pd.DataFrame(
            columns=[
                "생산계획년월",
                *display_dimensions,
                "원수요_부하량",
                "STEP_소요대수",
                "공정 유효 Capa",
            ]
        )

    result = required_equipment[required].copy()
    _normalize_month(result)
    text_columns = [
        column for column in DEMAND_ID_COLUMNS if column not in {"생산계획년월", "소요기준"}
    ]
    _normalize_text(result, text_columns)
    result["소요기준"] = (
        result["소요기준"].astype("string").str.strip().str.upper().replace({"WAFER": "WF"})
    )
    _assert_complete_keys(result, DEMAND_ID_COLUMNS)
    _assert_one_basis_per_process(result)

    result["부하량"] = _numeric(result["부하량"], "부하량")
    result["소요대수"] = _numeric(result["소요대수"], "소요대수")
    if result["부하량"].lt(0).any():
        raise ValueError("소요대수 상세의 부하량 값은 0 이상이어야 합니다.")
    if result["소요대수"].lt(0).any():
        raise ValueError("소요대수 상세의 소요대수 값은 0 이상이어야 합니다.")

    conflicting_loads = (
        result.groupby(DEMAND_ID_COLUMNS, dropna=False)["부하량"].nunique(dropna=False).gt(1)
    )
    if conflicting_loads.any():
        examples = conflicting_loads.loc[conflicting_loads].index.tolist()[:5]
        raise ValueError(f"동일 원수요 키의 부하량이 서로 다릅니다: {examples}")

    group_keys = ["생산계획년월", *display_dimensions]
    unique_demand = result.drop_duplicates(DEMAND_ID_COLUMNS)
    numerator = unique_demand.groupby(group_keys, as_index=False, dropna=False).agg(
        원수요_부하량=("부하량", "sum")
    )
    denominator = result.groupby(group_keys, as_index=False, dropna=False).agg(
        STEP_소요대수=("소요대수", "sum")
    )
    grouped = numerator.merge(denominator, on=group_keys, validate="one_to_one")
    grouped["공정 유효 Capa"] = grouped["원수요_부하량"].div(
        grouped["STEP_소요대수"].where(grouped["STEP_소요대수"].gt(0))
    )
    return grouped[
        [
            "생산계획년월",
            *display_dimensions,
            "원수요_부하량",
            "STEP_소요대수",
            "공정 유효 Capa",
        ]
    ].sort_values(["생산계획년월", *display_dimensions], ignore_index=True)


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

    _assert_one_basis_per_process(result)

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


def _assert_one_basis_per_process(data: pd.DataFrame) -> None:
    process_basis_counts = data.groupby("공정", dropna=False)["소요기준"].nunique()
    multiple_basis_processes = process_basis_counts.loc[process_basis_counts.gt(1)].index.tolist()
    if multiple_basis_processes:
        raise ValueError(f"공정별 소요기준이 둘 이상입니다: {multiple_basis_processes[:5]}")


def _require_columns(data: pd.DataFrame, required: list[str]) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"소요대수 상세 필수 컬럼이 없습니다: {', '.join(missing)}")
