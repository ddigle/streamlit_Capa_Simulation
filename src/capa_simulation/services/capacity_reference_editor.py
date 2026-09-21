# Purpose: Capa 기준정보를 월별 Wide 편집 표와 Long 계산 테이블 사이에서 변환한다.

import pandas as pd

from capa_simulation.services.frame_checks import assert_unique_keys, strip_text_columns
from capa_simulation.services.frame_contracts import (
    assert_complete,
    normalize_area_name,
    require_columns,
)

PERFORMANCE_EDITOR_DIMENSIONS = [
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


def reference_to_edit_table(
    data: pd.DataFrame,
    dimensions: list[str],
    value_column: str,
    table_name: str,
) -> pd.DataFrame:
    """Pivot a monthly reference table into editable month columns."""
    required = ["생산계획년월", *dimensions, value_column]
    require_columns(data, required, table_name)
    prepared = data[required].copy()
    prepared["생산계획년월"] = _month_values(prepared["생산계획년월"], table_name)
    strip_text_columns(prepared, dimensions)
    assert_complete(prepared, ["생산계획년월", *dimensions], table_name)
    assert_unique_keys(prepared, ["생산계획년월", *dimensions], f"{table_name}의 월별 연결 키가")
    prepared[value_column] = pd.to_numeric(prepared[value_column], errors="coerce")

    result = prepared.pivot(
        index=dimensions,
        columns="생산계획년월",
        values=value_column,
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [column for column in result.columns if column not in dimensions]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted([column for column in result.columns if column not in dimensions])
    return result[[*dimensions, *month_columns]]


def reference_from_edit_table(
    edit_table: pd.DataFrame,
    dimensions: list[str],
    value_column: str,
    table_name: str,
) -> pd.DataFrame:
    """Restore an edited month-column table to its monthly Long format."""
    require_columns(edit_table, dimensions, table_name)
    month_columns = [column for column in edit_table.columns if column not in dimensions]
    invalid_months = [
        column for column in month_columns if not str(column).isdigit() or len(str(column)) != 6
    ]
    if invalid_months:
        raise ValueError(f"{table_name}의 월 컬럼은 YYYYMM 형식이어야 합니다: {invalid_months}")

    prepared = edit_table.copy()
    strip_text_columns(prepared, dimensions)
    result = prepared.melt(
        id_vars=dimensions,
        value_vars=month_columns,
        var_name="생산계획년월",
        value_name=value_column,
    )
    result["생산계획년월"] = pd.to_numeric(result["생산계획년월"], errors="raise").astype("int64")
    result[value_column] = pd.to_numeric(result[value_column], errors="coerce")
    return result.dropna(subset=[value_column]).reset_index(drop=True)


def performance_to_edit_table(data: pd.DataFrame) -> pd.DataFrame:
    """Expose UPEH for Main rows and ST for MI rows as one editable value."""
    required = [
        "생산계획년월",
        *PERFORMANCE_EDITOR_DIMENSIONS,
        "UPEH",
        "ST",
    ]
    require_columns(data, required, "RQ_UPEH")
    prepared = data[required].copy()
    prepared["Area_Name"] = normalize_area_name(prepared["Area_Name"], "RQ_UPEH")
    prepared["기준값"] = pd.to_numeric(prepared["UPEH"], errors="coerce")
    mi_rows = prepared["Area_Name"].eq("MI")
    prepared.loc[mi_rows, "기준값"] = pd.to_numeric(prepared.loc[mi_rows, "ST"], errors="coerce")
    return reference_to_edit_table(
        prepared,
        PERFORMANCE_EDITOR_DIMENSIONS,
        "기준값",
        "RQ_UPEH",
    )


def performance_from_edit_table(edit_table: pd.DataFrame) -> pd.DataFrame:
    """Restore the shared performance editor value into UPEH and ST columns."""
    result = reference_from_edit_table(
        edit_table,
        PERFORMANCE_EDITOR_DIMENSIONS,
        "기준값",
        "RQ_UPEH 편집값",
    )
    main_rows = result["Area_Name"].eq("Main")
    result["UPEH"] = result["기준값"].where(main_rows)
    result["ST"] = result["기준값"].where(~main_rows)
    columns = ["생산계획년월", *PERFORMANCE_EDITOR_DIMENSIONS, "UPEH", "ST"]
    return result[columns]


def _month_values(values: pd.Series, table_name: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    if not valid.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    result = numeric.astype("int64")
    if not result.mod(100).between(1, 12).all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    return result
