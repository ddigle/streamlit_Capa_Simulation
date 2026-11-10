# Purpose: 시험이 xlsx 통을 표준 라이브러리만으로 열어 시트 칸 값 · 서식을 읽는 도우미.

"""xlsx 읽기 도우미(`capa_simulation.io.xlsx_small` 이 쓴 통).

저장소 의존성에 openpyxl 이 없다 — 시험도 표준 라이브러리로 읽는다. 칸마다 값(글자 · 숫자 · 빈 칸),
글자 셀인지 숫자 셀인지, 서식 번호가 가리키는 숫자 꼴 · 칠 · 굵기 · 테두리(「꼴:색」)를 돌려준다.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REF = re.compile(r"^([A-Z]+)(\d+)$")


@dataclass(frozen=True)
class ReadCell:
    value: str | float | None
    numeric: bool
    number_format: str
    fill: str | None
    bold: bool
    color: str | None
    left: str | None = None
    right: str | None = None
    top: str | None = None
    bottom: str | None = None


@dataclass(frozen=True)
class ReadSheet:
    name: str
    cells: dict[tuple[int, int], ReadCell]
    """(줄, 열) — 0부터."""

    freeze: tuple[int, int] | None
    widths: dict[int, float]

    def row(self, index: int) -> list[str | float | None]:
        columns = [column for row, column in self.cells if row == index]
        if not columns:
            return []
        return [
            self.cells[(index, column)].value if (index, column) in self.cells else None
            for column in range(max(columns) + 1)
        ]

    def column(self, index: int) -> list[str | float | None]:
        rows = max((row for row, _ in self.cells), default=-1)
        return [
            self.cells[(row, index)].value if (row, index) in self.cells else None
            for row in range(rows + 1)
        ]

    def find_row(self, label: str, column: int = 0) -> int:
        for (row, col), cell in sorted(self.cells.items()):
            if col == column and cell.value == label:
                return row
        raise AssertionError(f"{label!r} 줄이 없다")


def column_index(letters: str) -> int:
    number = 0
    for letter in letters:
        number = number * 26 + (ord(letter) - ord("A") + 1)
    return number - 1


def read_workbook(data: bytes) -> dict[str, ReadSheet]:
    """통 바이트 → 시트 이름 → 읽은 시트."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    strings = [
        "".join(text.text or "" for text in item.iter(f"{{{NS['m']}}}t"))
        for item in _xml(archive, "xl/sharedStrings.xml").findall("m:si", NS)
    ]
    styles = _xml(archive, "xl/styles.xml")
    formats = {
        int(item.get("numFmtId", "0")): item.get("formatCode", "")
        for item in styles.findall("m:numFmts/m:numFmt", NS)
    }
    fonts = styles.findall("m:fonts/m:font", NS)
    fills = styles.findall("m:fills/m:fill", NS)
    borders = styles.findall("m:borders/m:border", NS)
    xfs = styles.findall("m:cellXfs/m:xf", NS)
    workbook = _xml(archive, "xl/workbook.xml")
    names = [item.get("name", "") for item in workbook.findall("m:sheets/m:sheet", NS)]
    sheets: dict[str, ReadSheet] = {}
    for number, name in enumerate(names, start=1):
        root = _xml(archive, f"xl/worksheets/sheet{number}.xml")
        cells: dict[tuple[int, int], ReadCell] = {}
        for cell in root.findall("m:sheetData/m:row/m:c", NS):
            matched = _REF.match(cell.get("r", ""))
            assert matched is not None
            position = (int(matched.group(2)) - 1, column_index(matched.group(1)))
            xf = xfs[int(cell.get("s", "0"))]
            font = fonts[int(xf.get("fontId", "0"))]
            fill = fills[int(xf.get("fillId", "0"))].find("m:patternFill/m:fgColor", NS)
            color = font.find("m:color", NS)
            edges = _edges(borders[int(xf.get("borderId", "0"))])
            raw = cell.find("m:v", NS)
            kind = cell.get("t")
            value: str | float | None
            if raw is None or raw.text is None:
                value = None
            elif kind == "s":
                value = strings[int(raw.text)]
            else:
                value = float(raw.text)
            cells[position] = ReadCell(
                value=value,
                numeric=raw is not None and kind is None,
                number_format=formats.get(int(xf.get("numFmtId", "0")), "General"),
                fill=fill.get("rgb") if fill is not None else None,
                bold=font.find("m:b", NS) is not None,
                color=color.get("rgb") if color is not None else None,
                **edges,
            )
        pane = root.find("m:sheetViews/m:sheetView/m:pane", NS)
        freeze = (
            (int(float(pane.get("ySplit", "0"))), int(float(pane.get("xSplit", "0"))))
            if pane is not None
            else None
        )
        widths = {
            int(item.get("min", "1")) - 1: float(item.get("width", "0"))
            for item in root.findall("m:cols/m:col", NS)
        }
        sheets[name] = ReadSheet(name=name, cells=cells, freeze=freeze, widths=widths)
    return sheets


def _edges(border: ElementTree.Element) -> dict[str, str | None]:
    """테두리 한 벌 → 변마다 「꼴:색」(없으면 None)."""
    edges: dict[str, str | None] = {}
    for side in ("left", "right", "top", "bottom"):
        element = border.find(f"m:{side}", NS)
        style = element.get("style") if element is not None else None
        color = element.find("m:color", NS) if element is not None else None
        edges[side] = f"{style}:{color.get('rgb') if color is not None else ''}" if style else None
    return edges


def _xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    return ElementTree.fromstring(archive.read(name))
