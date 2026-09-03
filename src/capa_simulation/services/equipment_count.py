# Purpose: 보유·대여·가용 설비대수를 월별 조회 표로 결합한다.

import pandas as pd

from capa_simulation.services.capacity_reference_editor import (
    reference_from_edit_table,
    reference_to_edit_table,
)

EQUIPMENT_DIMENSIONS = ["공정"]
DETAILED_EQUIPMENT_DIMENSIONS = ["공정", "구분"]
EQUIPMENT_SOURCES = (
    ("보유", "설비보유"),
    ("대여", "설비대여평가"),
    ("가용", "가용대수"),
)


def equipment_count_to_edit_table(
    data: pd.DataFrame,
    category: str,
    value_column: str,
) -> pd.DataFrame:
    """Pivot one validated equipment-count RQ into editable month columns."""
    prepared = _prepare_source(data, category, value_column).rename(columns={"대수": value_column})
    return reference_to_edit_table(
        prepared,
        EQUIPMENT_DIMENSIONS,
        value_column,
        f"{category} 설비대수",
    )


def equipment_count_from_edit_table(
    edit_table: pd.DataFrame,
    category: str,
    value_column: str,
) -> pd.DataFrame:
    """Restore and validate one equipment-count CSV/editor table."""
    month_columns = [column for column in edit_table.columns if column not in EQUIPMENT_DIMENSIONS]
    numeric = edit_table[month_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any(axis=None):
        raise ValueError(f"{category} 설비대수의 월별 값에는 숫자를 입력해야 합니다.")
    if numeric.lt(0).any(axis=None):
        raise ValueError(f"{category} 설비대수는 0 이상이어야 합니다.")
    prepared = edit_table.copy()
    prepared[month_columns] = numeric
    restored = reference_from_edit_table(
        prepared,
        EQUIPMENT_DIMENSIONS,
        value_column,
        f"{category} 설비대수 편집값",
    )
    validated = _prepare_source(restored, category, value_column)
    return validated.rename(columns={"대수": value_column})[["생산계획년월", "공정", value_column]]


def build_equipment_count_table(
    own: pd.DataFrame,
    lent: pd.DataFrame,
    available: pd.DataFrame,
    *,
    detailed: bool,
) -> pd.DataFrame:
    """Build a monthly equipment-count table from the three equipment queries."""
    sources = zip((own, lent, available), EQUIPMENT_SOURCES, strict=True)
    prepared = [
        _prepare_source(data, category, value_column) for data, (category, value_column) in sources
    ]
    if detailed:
        long_table = pd.concat(prepared, ignore_index=True)
        dimensions = DETAILED_EQUIPMENT_DIMENSIONS
    else:
        long_table = prepared[2].drop(columns="구분")
        dimensions = EQUIPMENT_DIMENSIONS

    grouped = long_table.groupby(["생산계획년월", *dimensions], as_index=False, dropna=False)[
        "대수"
    ].sum()
    result: pd.DataFrame = grouped.pivot(
        index=dimensions,
        columns="생산계획년월",
        values="대수",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [column for column in result.columns if column not in dimensions]
    result = result.rename(columns={month: str(int(month)) for month in raw_month_columns})
    month_columns = sorted(str(int(month)) for month in raw_month_columns)
    result = result.reindex(columns=[*dimensions, *month_columns])
    if detailed:
        category_order = {category: index for index, (category, _) in enumerate(EQUIPMENT_SOURCES)}
        result["_category_order"] = result["구분"].map(category_order)
        result = (
            result.sort_values(["공정", "_category_order"], kind="stable")
            .drop(columns="_category_order")
            .reset_index(drop=True)
        )
    return result


def _prepare_source(data: pd.DataFrame, category: str, value_column: str) -> pd.DataFrame:
    required = ["생산계획년월", "공정", value_column]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"{category} 설비대수 필수 컬럼이 없습니다: {', '.join(missing)}")
    result = data[required].copy().rename(columns={value_column: "대수"})
    months = pd.to_numeric(result["생산계획년월"], errors="coerce")
    valid_months = months.notna() & months.mod(1).eq(0)
    integer_months = months.fillna(0).astype("int64")
    valid_months &= integer_months.mod(100).between(1, 12)
    if not valid_months.all():
        raise ValueError(f"{category} 설비대수의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    result["생산계획년월"] = integer_months
    result["공정"] = result["공정"].astype("string").str.strip()
    if result["공정"].isna().any() or result["공정"].eq("").any():
        raise ValueError(f"{category} 설비대수의 공정에 누락값이 있습니다.")
    result["대수"] = pd.to_numeric(result["대수"], errors="coerce")
    if result["대수"].isna().any():
        raise ValueError(f"{category} 설비대수에 숫자가 아닌 값 또는 누락값이 있습니다.")
    if result["대수"].lt(0).any():
        raise ValueError(f"{category} 설비대수는 0 이상이어야 합니다.")
    result["구분"] = category
    return result[["생산계획년월", "공정", "구분", "대수"]]
