# Purpose: Parse tabular text copied from Excel without using uploaded files.

"""Parse tabular text copied from Excel without using uploaded files."""

from __future__ import annotations

import csv
from io import StringIO

import pandas as pd


def parse_clipboard_table(content: str, label: str) -> pd.DataFrame:
    """Return a DataFrame from a header-inclusive tab-delimited clipboard block."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{label} 붙여넣기 내용이 비어 있습니다.")

    normalized = content.lstrip("\ufeff").strip("\r\n")
    raw_columns = next(csv.reader([normalized.partition("\n")[0]], delimiter="\t"))
    normalized_columns = [column.strip() for column in raw_columns]
    duplicate_columns = sorted(
        {column for column in normalized_columns if normalized_columns.count(column) > 1}
    )
    if duplicate_columns:
        raise ValueError(f"{label} 붙여넣기 컬럼명이 중복되었습니다: {duplicate_columns[:5]}")
    try:
        result = pd.read_csv(
            StringIO(normalized),
            sep="\t",
            dtype="object",
            keep_default_na=False,
            na_values=[""],
        )
    except pd.errors.ParserError as exc:
        raise ValueError(
            f"{label} 붙여넣기 내용을 표로 읽지 못했습니다. "
            "Excel에서 헤더를 포함한 셀 범위를 다시 복사하세요."
        ) from exc

    result.columns = [str(column).lstrip("\ufeff").strip() for column in result.columns]
    if len(result.columns) == 1 and "\t" not in normalized.partition("\n")[0]:
        raise ValueError(f"{label}은 Excel에서 헤더를 포함한 여러 셀을 복사해 붙여넣어야 합니다.")
    return result.dropna(how="all").reset_index(drop=True)
