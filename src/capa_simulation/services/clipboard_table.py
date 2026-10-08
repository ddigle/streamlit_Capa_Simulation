# Purpose: Parse tabular text copied from Excel without using uploaded files.

"""Parse tabular text copied from Excel without using uploaded files."""

from __future__ import annotations

import csv
import re
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

# 머리글이 빈 열의 이름. pandas 가 빈 머리글에 「Unnamed: 3」을 붙이고, 공백뿐인 머리글은
# 앞뒤 공백을 떼면 빈 글자가 된다(같은 것이 둘이면 pandas 가 「.1」을 붙인다).
_UNNAMED_HEADER = re.compile(r"(?:Unnamed: \d+|\.\d+)?")


def is_unnamed_header(header: object) -> bool:
    """머리글이 비었는가(빈 칸·공백뿐·pandas 가 붙인 「Unnamed: n」)."""
    return _UNNAMED_HEADER.fullmatch(str(header).strip()) is not None


def drop_empty_unnamed_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """머리글도 값도 빈 열을 뺀다 — Excel 이 복사 범위 끝에 딸려 보낸 빈 열이다.

    머리글만 비고 값이 있는 열은 남기고 이름을 「Unnamed: 위치」로 맞춘다(공백뿐인 머리글도 같다).
    받는 쪽이 모르는 열로 다룬다. 붙여넣기와 CSV 가 같은 열을 같게 다루도록 두 입구가 함께 쓴다.
    """
    keep: list[int] = []
    names: list[str] = []
    for position, header in enumerate(frame.columns):
        if is_unnamed_header(header):
            values = frame.iloc[:, position].astype("string").str.strip().fillna("")
            if values.eq("").all():
                continue
            names.append(f"Unnamed: {position}")
        else:
            names.append(str(header))
        keep.append(position)
    if len(keep) == len(frame.columns) and names == [str(column) for column in frame.columns]:
        return frame
    result = frame.iloc[:, keep].copy()
    result.columns = names
    return result


def parse_clipboard_table(content: str, label: str) -> pd.DataFrame:
    """Return a DataFrame from a header-inclusive tab-delimited clipboard block."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{label} 붙여넣기 내용이 비어 있습니다.")

    normalized = content.lstrip("\ufeff").strip("\r\n")
    raw_columns = next(csv.reader([normalized.partition("\n")[0]], delimiter="\t"))
    normalized_columns = [column.strip() for column in raw_columns]
    # 빈 머리글은 중복으로 세지 않는다. 세면 Excel 범위 끝에 빈 열이 둘 이상 딸려 온 붙여넣기가
    # 모두 빈 글자라 「컬럼명이 중복」으로 막힌다. 빈 열은 아래 `drop_empty_unnamed_columns` 가
    # 다룬다.
    duplicate_columns = sorted(
        {column for column in normalized_columns if column and normalized_columns.count(column) > 1}
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
        raise ValueError(
            f"{label} 붙여넣기는 Excel에서 헤더를 포함한 여러 셀을 복사해 넣어야 합니다."
        )
    return drop_empty_unnamed_columns(result.dropna(how="all")).reset_index(drop=True)
