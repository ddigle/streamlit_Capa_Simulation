# Purpose: 부대공정 시험이 함께 쓰는 합성 견본 양식(CSV 여섯 장)과 고친 사본 · ZIP 만들기를 둔다.

"""부대공정 시험 도우미 — 견본은 `tests/fixtures/extra_process/` 의 합성 `DEMO_*` 여섯 장이다.

견본은 설계 견본(`template/`)과 같은 값이다: `DEMO_New_Bond`(Main · CHIP · 따라가기 꼴 —
`DEMO_Chip_Attach`)와 `DEMO_New_AOI`(MI · WF · 지정 꼴 — `DEMO PRODUCT A`/8H/Core ·
`DEMO PRODUCT B`/12H/Base). 이름은 내장 합성 시드(`services/builtin_seed.py`)에 맞췄다.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

FIXTURE_DIR: Final = Path(__file__).resolve().parent / "fixtures" / "extra_process"
BOND: Final = "DEMO_New_Bond"
AOI: Final = "DEMO_New_AOI"

Table = list[list[str]]


def template_files() -> dict[str, bytes]:
    """견본 여섯 장(파일 이름 → 바이트)."""
    return {path.name: path.read_bytes() for path in sorted(FIXTURE_DIR.glob("*.csv"))}


def read_table(data: bytes) -> Table:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def write_table(rows: Table) -> bytes:
    text = io.StringIO()
    csv.writer(text, lineterminator="\r\n").writerows(rows)
    return ("﻿" + text.getvalue()).encode("utf-8")


def edited(files: dict[str, bytes], name: str, edit: Callable[[Table], Table]) -> dict[str, bytes]:
    """한 장을 표로 읽어 고친 사본(나머지 장은 그대로)."""
    copy = dict(files)
    copy[name] = write_table(edit(read_table(files[name])))
    return copy


def set_cell(rows: Table, match: Callable[[list[str]], bool], column: str, value: str) -> Table:
    """머리 칸 이름으로 고른 칸을 `match` 가 참인 줄마다 바꾼 표."""
    index = rows[0].index(column)
    return [rows[0]] + [
        [*row[:index], value, *row[index + 1 :]] if match(row) else row for row in rows[1:]
    ]


def bump_version(files: dict[str, bytes], version: int) -> dict[str, bytes]:
    """`00_info.csv` 의 판 번호를 바꾼 사본."""
    return edited(
        files,
        "00_info.csv",
        lambda rows: set_cell(rows, lambda r: r[0] == "판", "값", str(version)),
    )


def zip_files(files: dict[str, bytes], *, folder: str = "") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(f"{folder}{name}", data)
    return buffer.getvalue()


def template_zip_bytes() -> bytes:
    return zip_files(template_files())
