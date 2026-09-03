# Purpose: CSV round-trip contract for wide editable RQ tables.

"""CSV round-trip contract for wide editable RQ tables."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from capa_simulation.services.clipboard_table import parse_clipboard_table


def reference_edit_csv_bytes(data: pd.DataFrame) -> bytes:
    """Encode an editable table as an Excel-friendly UTF-8 CSV."""
    return data.to_csv(index=False).encode("utf-8-sig")


def parse_reference_edit_csv(
    content: bytes,
    template: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
) -> pd.DataFrame:
    """Read a wide RQ CSV and require the same columns and classification rows."""
    if not content:
        raise ValueError(f"{table_name} CSV 파일이 비어 있습니다.")

    source: pd.DataFrame | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            source = pd.read_csv(BytesIO(content), encoding=encoding, dtype="object")
            break
        except UnicodeDecodeError:
            continue
    if source is None:
        raise ValueError(f"{table_name} CSV는 UTF-8 또는 CP949 인코딩이어야 합니다.")

    return validate_reference_edit_table(source, template, key_columns, table_name)


def parse_reference_edit_clipboard(
    content: str,
    template: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
) -> pd.DataFrame:
    """Read a header-inclusive Excel clipboard block using the existing table contract."""
    source = parse_clipboard_table(content, table_name)
    return validate_reference_edit_table(source, template, key_columns, table_name)


def validate_reference_edit_table(
    source: pd.DataFrame,
    template: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
) -> pd.DataFrame:
    """Require the same columns and classification rows as the current edit template."""
    source = source.dropna(how="all").reset_index(drop=True)
    expected_columns = [str(column) for column in template.columns]
    source.columns = [str(column).strip() for column in source.columns]
    missing_columns = [column for column in expected_columns if column not in source.columns]
    extra_columns = [column for column in source.columns if column not in expected_columns]
    if missing_columns or extra_columns:
        details: list[str] = []
        if missing_columns:
            details.append(f"누락 {missing_columns}")
        if extra_columns:
            details.append(f"추가 {extra_columns}")
        raise ValueError(
            f"{table_name} 입력 표 컬럼이 다운로드 양식과 다릅니다: {'; '.join(details)}"
        )
    result = source.reindex(columns=expected_columns).copy()

    missing_keys = [column for column in key_columns if column not in result.columns]
    if missing_keys:
        raise ValueError(f"{table_name} 입력 표 식별 컬럼이 없습니다: {', '.join(missing_keys)}")
    expected_keys = _normalized_keys(template, key_columns, table_name, "다운로드 양식")
    uploaded_keys = _normalized_keys(result, key_columns, table_name, "업로드 파일")
    duplicated = uploaded_keys.duplicated(key_columns, keep=False)
    if duplicated.any():
        examples = uploaded_keys.loc[duplicated, key_columns].drop_duplicates().head(5)
        raise ValueError(
            f"{table_name} 입력 표 식별 행이 중복되었습니다: {examples.to_dict('records')}"
        )

    expected_index = pd.MultiIndex.from_frame(expected_keys[key_columns])
    uploaded_index = pd.MultiIndex.from_frame(uploaded_keys[key_columns])
    missing_rows = expected_index.difference(uploaded_index)
    extra_rows = uploaded_index.difference(expected_index)
    if len(missing_rows) or len(extra_rows):
        raise ValueError(
            f"{table_name} 입력 표의 분류 행은 다운로드 양식과 같아야 합니다: "
            f"누락 {len(missing_rows):,}행, 추가 {len(extra_rows):,}행"
        )

    order = expected_keys.copy()
    order["__csv_row_order"] = range(len(order))
    result[key_columns] = uploaded_keys[key_columns]
    result = result.merge(order, on=key_columns, how="left", validate="one_to_one")
    return (
        result.sort_values("__csv_row_order", kind="stable")
        .drop(columns="__csv_row_order")
        .reindex(columns=expected_columns)
        .reset_index(drop=True)
    )


def _normalized_keys(
    data: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
    label: str,
) -> pd.DataFrame:
    result = data[key_columns].copy()
    for column in key_columns:
        result[column] = result[column].astype("string").str.strip()
    has_missing = result.isna().any(axis=None)
    has_blank = any(result[column].eq("").any() for column in key_columns)
    if has_missing or has_blank:
        raise ValueError(f"{table_name} {label}의 식별 컬럼에 누락값이 있습니다.")
    return result
