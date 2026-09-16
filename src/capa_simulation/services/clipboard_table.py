# Purpose: Parse tabular text copied from Excel without using uploaded files.

"""Parse tabular text copied from Excel without using uploaded files."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

import pandas as pd

# 표를 **글자 그대로** 읽는 옵션. pandas 기본값은 `NA`·`NULL`·`None`·`N/A`·`NaN` 을 결측으로
# 바꾸는데, 이것들은 업무 값일 수 있다 — 지역 코드 `NA`(North America) 가 결측이 되면 그
# 행의 식별이 통째로 사라진다. 빈 칸만 결측으로 본다.
#
# **붙여넣기와 파일 업로드가 같은 값을 같게 읽어야 한다.** 한쪽만 고치면 같은 파일이 경로에
# 따라 다르게 읽히므로 옵션을 여기 한 군데 두고 양쪽이 이것을 쓴다.
TEXT_TABLE_READ_OPTIONS: dict[str, Any] = {
    "dtype": "object",
    "keep_default_na": False,
    "na_values": [""],
}


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
        # 옵션 묶음이 `Any` 라 반환 타입이 풀린다. 받는 쪽에서 다시 묶는다.
        result: pd.DataFrame = pd.read_csv(
            StringIO(normalized), sep="\t", **TEXT_TABLE_READ_OPTIONS
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
