# Purpose: 보유·대여·가용 설비대수를 월별 조회 표로 결합한다.

import pandas as pd

from capa_simulation.services.capacity_reference_editor import (
    reference_from_edit_table,
    reference_to_edit_table,
)
from capa_simulation.services.frame_contracts import normalize_month_column, require_columns

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
    """Pivot one validated equipment-count RQ into editable month columns.

    **원천에 없는 `(공정, 월)` 은 0 대다**(2026-09-23 사내 실데이터로 확인, 09-29 버그 보고). 원천은
    값이 비어 있는 것이 아니라 그 행 자체가 없다. 피벗하면 그 자리가 빈칸으로 뜨고, 적용할 때 표
    전체(필터로 안 보이는 행 포함)를 숫자로 다시 검사하므로 아무것도 안 고쳐도 적용이 막혔다.

    보유·대여·가용 세 표에만 채운다. 공용 `reference_to_edit_table` 을 쓰는 UPEH·효율·여유율·
    측정률·일수는 「빈칸 = 0」이 안전하지 않다 — UPEH 0 은 대당 Capa 나눗셈을, 비율 0 은 하류
    계산을 죽인다. 원천 변환에서 미리 0 으로 채우지도 않는다 — 그러면 `securement_rate` 의
    「소요대수는 있지만 가용대수가 없는 공정」 안전장치가 영구히 꺼진다. 편집기를 거쳐 저장된 0
    만이 「확인된 0 대」다.
    """
    prepared = _prepare_source(data, category, value_column).rename(columns={"대수": value_column})
    table = reference_to_edit_table(
        prepared,
        EQUIPMENT_DIMENSIONS,
        value_column,
        f"{category} 설비대수",
    )
    month_columns = [column for column in table.columns if column not in EQUIPMENT_DIMENSIONS]
    table[month_columns] = table[month_columns].fillna(0.0)
    return table


def equipment_count_from_edit_table(
    edit_table: pd.DataFrame,
    category: str,
    value_column: str,
) -> pd.DataFrame:
    """Restore and validate one equipment-count CSV/editor table.

    **빈칸은 0 대다**(`equipment_count_to_edit_table` 과 같은 규칙). 편집표에서 값을 지운 칸도,
    붙여넣은 표의 빈칸도 0 으로 저장한다. 숫자로 못 읽는 **글자**는 여전히 막는다 — 그것까지 0 으로
    받으면 오타가 말없이 0 대가 된다.
    """
    month_columns = [column for column in edit_table.columns if column not in EQUIPMENT_DIMENSIONS]
    raw = edit_table[month_columns]
    blank = raw.isna() | raw.apply(lambda column: column.astype("string").str.strip().eq(""))
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    if (numeric.isna() & ~blank.fillna(False).astype(bool)).any(axis=None):
        raise ValueError(f"{category} 설비대수의 월별 값에는 숫자를 입력해야 합니다.")
    numeric = numeric.fillna(0.0)
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
    require_columns(data, required, f"{category} 설비대수")
    result = data[required].copy().rename(columns={value_column: "대수"})
    normalize_month_column(result, f"{category} 설비대수")
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
