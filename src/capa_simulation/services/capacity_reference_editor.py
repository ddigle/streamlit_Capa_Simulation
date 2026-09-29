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
# `RQ_UPEH` 편집이 돌려주는 컬럼과, 원본 행을 찾는 키.
PERFORMANCE_COLUMNS = ["생산계획년월", *PERFORMANCE_EDITOR_DIMENSIONS, "UPEH", "ST"]
_MATCH_KEYS = ["생산계획년월", *PERFORMANCE_EDITOR_DIMENSIONS]


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


def performance_from_edit_table(
    edit_table: pd.DataFrame,
    source: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Restore the shared performance editor value into UPEH and ST columns.

    `source` 는 편집표를 만든 원본(같은 조회기간의 `RQ_UPEH`)이다. 주면 **고치지 않은 것은 원본
    그대로** 돌려준다(2026-09-29 설비대수 빈칸 버그의 횡전개). 편집표에는 한 경로·월에 값이
    하나(Main 은 UPEH, MI 는 ST)뿐이라 그 값만으로 행을 다시 만들면, 아무것도 안 고친 적용에도
    원천이 바뀌었다.

    1. Main 행의 ST·MI 행의 UPEH 가 NaN 이 됐다 → 원본 행을 쓰고 편집한 칸만 덮는다.
    2. 값이 빈 실재 행(BOX 등 — 계산이 쓰지 않아 비어 있어도 된다)이 지워졌다 → 템플릿에서
       값이 비어 있던 원본 행은 그대로 남긴다. 값이 있던 칸을 비운 것만 행 삭제다.
    3. `Area_Name` 이 표시용 정규화(`MAIN` → `Main`)로 저장돼 `route_step_catalog` 의
       `RQ_REQB` 정확 일치 merge 가 끊기고 STEP 목록이 비었다 → 저장값은 원본 표기를 쓴다.
       정규화는 원본 행을 찾는 키에만 쓴다. 빈 달을 새로 채운 행도 같은 경로의 원본 표기를
       따른다.

    `source` 가 없으면 예전처럼 편집표만으로 복원한다.
    """
    result = reference_from_edit_table(
        edit_table,
        PERFORMANCE_EDITOR_DIMENSIONS,
        "기준값",
        "RQ_UPEH 편집값",
    )
    if source is not None:
        months = [
            int(column)
            for column in edit_table.columns
            if column not in PERFORMANCE_EDITOR_DIMENSIONS
        ]
        return _overlay_on_source(result, source, months)
    main_rows = result["Area_Name"].eq("Main")
    result["UPEH"] = result["기준값"].where(main_rows)
    result["ST"] = result["기준값"].where(~main_rows)
    return result[PERFORMANCE_COLUMNS]


def _overlay_on_source(
    restored: pd.DataFrame,
    source: pd.DataFrame,
    months: list[int],
) -> pd.DataFrame:
    """편집표에서 복원한 값을 원본 행 위에 얹는다. 규칙은 `performance_from_edit_table` 참고."""
    require_columns(source, PERFORMANCE_COLUMNS, "RQ_UPEH")
    original = source[PERFORMANCE_COLUMNS].reset_index(drop=True)
    source_keys = _match_keys(original)
    # 편집표에 없는 달의 원본은 이 적용의 대상이 아니다.
    in_window = source_keys["생산계획년월"].isin(months).to_numpy()
    original = original.loc[in_window].reset_index(drop=True)
    source_keys = source_keys.loc[in_window].reset_index(drop=True)
    assert_unique_keys(source_keys, _MATCH_KEYS, "RQ_UPEH의 월별 연결 키가")
    original["생산계획년월"] = source_keys["생산계획년월"].to_numpy()

    restored = restored.reset_index(drop=True)
    positions = pd.MultiIndex.from_frame(source_keys).get_indexer(
        pd.MultiIndex.from_frame(_match_keys(restored))
    )
    matched = positions >= 0

    # 원본에 있던 행: 원본 행에 편집한 칸(Main 은 UPEH, MI 는 ST)만 덮는다.
    source_mi = source_keys["Area_Name"].eq("MI")
    source_value = pd.to_numeric(original["UPEH"], errors="coerce").where(
        ~source_mi, pd.to_numeric(original["ST"], errors="coerce")
    )
    edited_value = pd.Series(
        restored.loc[matched, "기준값"].to_numpy(dtype="float64"),
        index=positions[matched],
    )
    in_edit = original.index.isin(edited_value.index)
    # 값이 있던 칸을 비운 행만 빠진다. 처음부터 비어 있던 원본 행은 그대로 둔다.
    kept = original.loc[in_edit | source_value.isna().to_numpy()].copy()
    for column, rows in (("UPEH", ~source_mi), ("ST", source_mi)):
        target = edited_value.index[rows.loc[edited_value.index].to_numpy()]
        if target.empty:
            continue
        # 정수 컬럼에 소수를 넣으면 pandas 가 경고한다. 값은 그대로 두고 담는 그릇만 넓힌다.
        if pd.api.types.is_integer_dtype(kept[column]):
            kept[column] = kept[column].astype("float64")
        elif not pd.api.types.is_float_dtype(kept[column]):
            kept[column] = kept[column].astype("object")
        kept.loc[target, column] = edited_value.loc[target].to_numpy()

    # 원본에 없던 행(빈 달을 새로 채움): 값은 편집표, 분류 표기는 같은 경로의 원본.
    added = restored.loc[~matched].reset_index(drop=True)
    main_rows = added["Area_Name"].eq("Main")
    added["UPEH"] = added["기준값"].where(main_rows)
    added["ST"] = added["기준값"].where(~main_rows)
    if not added.empty and not original.empty:
        path_keys = source_keys[PERFORMANCE_EDITOR_DIMENSIONS]
        first = ~path_keys.duplicated().to_numpy()
        path_positions = pd.MultiIndex.from_frame(path_keys.loc[first]).get_indexer(
            pd.MultiIndex.from_frame(_match_keys(added)[PERFORMANCE_EDITOR_DIMENSIONS])
        )
        has_path = path_positions >= 0
        path_notation = original.loc[first, PERFORMANCE_EDITOR_DIMENSIONS].reset_index(drop=True)
        added[PERFORMANCE_EDITOR_DIMENSIONS] = added[PERFORMANCE_EDITOR_DIMENSIONS].astype("object")
        added.loc[has_path, PERFORMANCE_EDITOR_DIMENSIONS] = path_notation.iloc[
            path_positions[has_path]
        ].to_numpy()
    frames = [frame for frame in (kept, added[PERFORMANCE_COLUMNS]) if not frame.empty]
    if not frames:
        return original.head(0)
    return pd.concat(frames, ignore_index=True)[PERFORMANCE_COLUMNS]


def _match_keys(data: pd.DataFrame) -> pd.DataFrame:
    """원본 행을 찾는 키. 편집표를 만들 때와 같이 줄인다(월 정수·공백 제거·Area 정규화)."""
    keys = data[_MATCH_KEYS].copy().reset_index(drop=True)
    keys["생산계획년월"] = _month_values(keys["생산계획년월"], "RQ_UPEH")
    for column in PERFORMANCE_EDITOR_DIMENSIONS:
        keys[column] = keys[column].astype("string").str.strip()
    keys["Area_Name"] = normalize_area_name(keys["Area_Name"], "RQ_UPEH")
    return keys


def _month_values(values: pd.Series, table_name: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    if not valid.all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    result = numeric.astype("int64")
    if not result.mod(100).between(1, 12).all():
        raise ValueError(f"{table_name}의 생산계획년월은 YYYYMM 형식이어야 합니다.")
    return result
