# Purpose: 원천 CSV 시험이 쓰는 합성 견본(계약 78열 + 남는 열 셋의 행 · CSV 바이트)을 짓는다.

"""원천 CSV 합성 견본 — 실제 값 없이 `DEMO_*` 만.

행은 내장 합성 시드(`build_builtin_core_data` — 지금 파이프라인을 끝까지 지나는 값)에서 시뮬레이션
ID 만 한 코드로 바꿔 글자로 옮긴다. 숫자는 `repr` 글자(최단 표기)로 적는다. 남는 열 셋은 계약 차례
가운데(그 열 바로 뒤)와 끝에 끼워, 파일 칸 차례와 계약 차례가 다른 꼴을 시험이 지나게 한다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from numbers import Integral, Real

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.io.source_csv import SOURCE_CSV_EXTRA_COLUMNS
from capa_simulation.services.builtin_seed import build_builtin_core_data

DEMO_CODE = "DEMO-SIM-1"
# 남는 열 셋을 놓는 자리 — 그 계약 열 바로 뒤(없으면 끝).
EXTRA_AFTER: Mapping[str, str | None] = {
    "설비대수변화관리여부": "설비대수변화관리",
    "설비대여평가여부": "설비대여평가",
    "공식여부": None,
}
EXTRA_VALUES: Mapping[str, str] = {
    "설비대수변화관리여부": "N",
    "설비대여평가여부": "N",
    "공식여부": "Y",
}
DEFAULT_QUOTED_HEADERS = ("Capa Code", "PLAN ID")


def contract_names() -> list[str]:
    return [column.name for column in load_core_data_contract().columns]


def file_columns(*, extra_columns: bool = True) -> list[str]:
    """파일 칸 차례 — 계약 78열에 남는 열 셋을 끼운 꼴."""
    names = contract_names()
    if not extra_columns:
        return names
    columns: list[str] = []
    for name in names:
        columns.append(name)
        columns.extend(extra for extra, after in EXTRA_AFTER.items() if after == name)
    columns.extend(extra for extra, after in EXTRA_AFTER.items() if after is None)
    assert sorted(columns) == sorted([*names, *SOURCE_CSV_EXTRA_COLUMNS])
    return columns


def cell_text(value: object) -> str:
    """시드 값 하나를 CSV 글자로 — 빈 값은 빈칸, 실수는 `repr`(최단 표기)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        number = float(value)
        return "" if math.isnan(number) else repr(number)
    return str(value)


def demo_core_rows(n: int | None = None, *, code: str = DEMO_CODE) -> list[dict[str, str]]:
    """계약 78열 글자 행 `n` 개(없으면 시드 전부) — 시뮬레이션 ID 는 모두 `code`."""
    frame = build_builtin_core_data()
    if n is not None:
        frame = frame.head(n)
    names = contract_names()
    rows: list[dict[str, str]] = []
    for record in frame.to_dict("records"):
        row = {name: cell_text(record[name]) for name in names}
        row["시뮬레이션 ID"] = code
        rows.append(row)
    return rows


def _field(text: str, *, delimiter: str = ",", force: bool = False) -> str:
    if force or any(mark in text for mark in (delimiter, '"', "\r", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def row_line(
    row: Mapping[str, str],
    *,
    extra_columns: bool = True,
    trailing_comma: bool = False,
) -> str:
    """행 하나를 파일에 적힐 한 줄 글자로(줄 끝 없음) — 날 줄을 지을 때 쓴다."""
    fields = [
        _field(row.get(column, EXTRA_VALUES.get(column, "")))
        for column in file_columns(extra_columns=extra_columns)
    ]
    return ",".join(fields) + ("," if trailing_comma else "")


def header_line(
    *,
    extra_columns: bool = True,
    quoted_headers: Sequence[str] = DEFAULT_QUOTED_HEADERS,
    header_override: Mapping[str, str] | None = None,
    trailing_comma: bool = False,
) -> str:
    """머리 한 줄 — `quoted_headers` 는 따옴표로 감싸고 `header_override` 는 그 머리 글을 바꾼다."""
    override = header_override or {}
    fields = [
        _field(override.get(column, column), force=column in quoted_headers)
        for column in file_columns(extra_columns=extra_columns)
    ]
    return ",".join(fields) + ("," if trailing_comma else "")


def source_csv_bytes(
    rows: Sequence[Mapping[str, str]],
    *,
    encoding: str = "cp949",
    line_end: str = "\r\n",
    quoted_headers: Sequence[str] = DEFAULT_QUOTED_HEADERS,
    extra_columns: bool = True,
    header_override: Mapping[str, str] | None = None,
    trailing_comma: bool = False,
    raw_lines: Mapping[int, str] | None = None,
) -> bytes:
    """견본 CSV 바이트 — 원천 웹 꼴(CP949 · 쉼표 · CRLF · 머리 일부만 따옴표 · 쉼표 든 칸만 따옴표).

    `raw_lines` 는 {데이터 줄 자리: 날 줄 글자} 다 — 그 자리 행 앞에 끼운다(`len(rows)` 면 끝).
    """
    lines = [
        header_line(
            extra_columns=extra_columns,
            quoted_headers=quoted_headers,
            header_override=header_override,
            trailing_comma=trailing_comma,
        )
    ]
    inserted = raw_lines or {}
    for index, row in enumerate(rows):
        if index in inserted:
            lines.append(inserted[index])
        lines.append(row_line(row, extra_columns=extra_columns, trailing_comma=trailing_comma))
    if len(rows) in inserted:
        lines.append(inserted[len(rows)])
    return "".join(line + line_end for line in lines).encode(encoding)
