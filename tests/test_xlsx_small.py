# Purpose: 작은 xlsx 작성기가 Excel 이 복구 창 없이 여는 꼴을 지키는지 본다.

"""`capa_simulation.io.xlsx_small` — 표준 라이브러리만으로 읽어 본다(저장소에 openpyxl 이 없다).

Excel 은 꼴이 어긋난 통을 「복구」 창으로 연다. 그 꼴을 그물로 둔다 — 잘 짜인 XML, 파트와
`[Content_Types].xml` · 관계 파일의 짝, worksheet · styles 요소 차례(ECMA-376), `fills` 첫 둘
(`none` · `gray125`), 사용자 숫자 꼴 번호 164 부터, 숫자 칸은 숫자 셀 · NaN 은 빈 칸, XML 이 받지
않는 제어 문자 걷기, 숫자처럼 보이는 글자 칸만 덮는 「오류 무시」 표지(`ignoredErrors` — 초록
삼각형), 같은 입력은 같은 바이트. 실제 Excel 로 여는 확인은 저장소 밖 견본으로 한다.
"""

from __future__ import annotations

import io
import math
import zipfile
from xml.etree import ElementTree

import pytest
from xlsx_read import NS, read_workbook

from capa_simulation.io.xlsx_small import (
    Edge,
    Sheet,
    Style,
    XlsxCell,
    column_letter,
    workbook_bytes,
)

MAIN = NS["m"]
# worksheet 자식의 ECMA-376 차례(CT_Worksheet) — 이 작성기가 쓰는 것과 그 앞뒤.
WORKSHEET_ORDER = (
    "sheetPr",
    "dimension",
    "sheetViews",
    "sheetFormatPr",
    "cols",
    "sheetData",
    "sheetCalcPr",
    "sheetProtection",
    "protectedRanges",
    "scenarios",
    "autoFilter",
    "sortState",
    "dataConsolidate",
    "customSheetViews",
    "mergeCells",
    "phoneticPr",
    "conditionalFormatting",
    "dataValidations",
    "hyperlinks",
    "printOptions",
    "pageMargins",
    "pageSetup",
    "headerFooter",
    "rowBreaks",
    "colBreaks",
    "customProperties",
    "cellWatches",
    "ignoredErrors",
    "smartTags",
    "drawing",
    "legacyDrawing",
    "legacyDrawingHF",
    "drawingHF",
    "picture",
    "oleObjects",
    "controls",
    "webPublishItems",
    "tableParts",
    "extLst",
)
STYLES_ORDER = (
    "numFmts",
    "fonts",
    "fills",
    "borders",
    "cellStyleXfs",
    "cellXfs",
    "cellStyles",
    "dxfs",
    "tableStyles",
    "colors",
    "extLst",
)
SIGNED = '+#,##0.0;"−"#,##0.0;#,##0.0'


def _book() -> bytes:
    rows: list[list[XlsxCell | None]] = [
        [XlsxCell("구분", Style(bold=True, fill="#E4E7EB")), XlsxCell("26.11"), None],
        [
            XlsxCell("확보율"),
            XlsxCell(1.26, Style(number_format="#,##0%", fill="#F43F5E", bold=True)),
            XlsxCell(-2.5, Style(number_format=SIGNED, bottom=Edge("thick", "#F43F5E"))),
        ],
        [XlsxCell(" 앞뒤 빈칸 "), XlsxCell(math.nan), XlsxCell(math.inf, Style(bold=True))],
        [XlsxCell("제어\x01문자\x0b"), XlsxCell(7), XlsxCell(None, Style(fill="#FFFFFF"))],
    ]
    first = Sheet(
        name="상세 Capa",
        rows=rows,
        widths={0: 34.0, 1: 13.0},
        heights={2: 30.0},
        freeze=(1, 1),
    )
    second = Sheet(name="단축 일정", rows=[[XlsxCell("호기")], [XlsxCell("U-1")]], freeze=(1, 0))
    return workbook_bytes([first, second])


def _parts(data: bytes) -> dict[str, ElementTree.Element]:
    archive = zipfile.ZipFile(io.BytesIO(data))
    return {name: ElementTree.fromstring(archive.read(name)) for name in archive.namelist()}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _in_order(children: list[str], order: tuple[str, ...]) -> bool:
    positions = [order.index(name) for name in children]
    return positions == sorted(positions)


def test_every_part_is_well_formed_and_declared() -> None:
    parts = _parts(_book())
    assert set(parts) == {
        "[Content_Types].xml",
        "_rels/.rels",
        "docProps/app.xml",
        "docProps/core.xml",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        "xl/styles.xml",
        "xl/sharedStrings.xml",
        "xl/worksheets/sheet1.xml",
        "xl/worksheets/sheet2.xml",
    }
    overrides = {
        item.get("PartName", "").lstrip("/")
        for item in parts["[Content_Types].xml"]
        if _local(item.tag) == "Override"
    }
    assert overrides == {name for name in parts if not name.endswith(".rels")} - {
        "[Content_Types].xml"
    }
    targets = {item.get("Target") for item in parts["xl/_rels/workbook.xml.rels"]}
    assert targets == {
        "worksheets/sheet1.xml",
        "worksheets/sheet2.xml",
        "styles.xml",
        "sharedStrings.xml",
    }
    root_targets = {item.get("Target") for item in parts["_rels/.rels"]}
    assert root_targets == {"xl/workbook.xml", "docProps/core.xml", "docProps/app.xml"}
    sheets = parts["xl/workbook.xml"].findall("m:sheets/m:sheet", NS)
    assert [sheet.get("name") for sheet in sheets] == ["상세 Capa", "단축 일정"]


def test_worksheet_and_styles_children_keep_the_ecma_order() -> None:
    parts = _parts(_book())
    # 첫 시트는 글자 달 머리 「26.11」 이 있어 `ignoredErrors` 가 맨 끝(`pageMargins` 바로 뒤),
    # 둘째 시트는 숫자처럼 보이는 글자가 없어 그 요소가 없다(빈 요소는 Excel 이 받지 않는다).
    for name, last in (
        ("xl/worksheets/sheet1.xml", ("pageMargins", "ignoredErrors")),
        ("xl/worksheets/sheet2.xml", ("sheetData", "pageMargins")),
    ):
        children = [_local(child.tag) for child in parts[name]]
        assert _in_order(children, WORKSHEET_ORDER), children
        assert children[0] == "dimension" and tuple(children[-2:]) == last, children
    styles = [_local(child.tag) for child in parts["xl/styles.xml"]]
    assert _in_order(styles, STYLES_ORDER), styles
    # 글꼴 · 칠 · 테두리의 자식도 차례가 있다.
    for border in parts["xl/styles.xml"].findall("m:borders/m:border", NS):
        assert [_local(child.tag) for child in border] == [
            "left",
            "right",
            "top",
            "bottom",
            "diagonal",
        ]


def test_the_style_tables_keep_the_slots_excel_expects() -> None:
    styles = _parts(_book())["xl/styles.xml"]
    fills = styles.findall("m:fills/m:fill/m:patternFill", NS)
    assert [fill.get("patternType") for fill in fills[:2]] == ["none", "gray125"]
    assert all(fill.get("patternType") == "solid" for fill in fills[2:])
    assert int(styles.find("m:fills", NS).get("count", "0")) == len(fills)  # type: ignore[union-attr]
    for table, item in (("fonts", "font"), ("borders", "border"), ("cellXfs", "xf")):
        element = styles.find(f"m:{table}", NS)
        assert element is not None
        assert int(element.get("count", "0")) == len(element.findall(f"m:{item}", NS))
    numbers = [int(item.get("numFmtId", "0")) for item in styles.findall("m:numFmts/m:numFmt", NS)]
    assert numbers and min(numbers) >= 164
    codes = {item.get("formatCode") for item in styles.findall("m:numFmts/m:numFmt", NS)}
    assert SIGNED in codes
    colors = [item.get("rgb") for item in styles.iter(f"{{{MAIN}}}fgColor")]
    assert all(color is not None and len(color) == 8 and color.startswith("FF") for color in colors)
    xfs = styles.findall("m:cellXfs/m:xf", NS)
    fonts = styles.findall("m:fonts/m:font", NS)
    borders = styles.findall("m:borders/m:border", NS)
    for xf in xfs:
        assert int(xf.get("fontId", "0")) < len(fonts)
        assert int(xf.get("fillId", "0")) < len(fills)
        assert int(xf.get("borderId", "0")) < len(borders)
        format_id = int(xf.get("numFmtId", "0"))
        assert format_id == 0 or format_id in numbers


def test_numbers_are_number_cells_and_strings_are_shared() -> None:
    data = _book()
    parts = _parts(data)
    sheet = parts["xl/worksheets/sheet1.xml"]
    strings = parts["xl/sharedStrings.xml"].findall("m:si", NS)
    for cell in sheet.findall("m:sheetData/m:row/m:c", NS):
        value = cell.find("m:v", NS)
        if cell.get("t") == "s":
            assert value is not None and int(value.text or "") < len(strings)
        elif value is not None:
            float(value.text or "")
    book = read_workbook(data)["상세 Capa"]
    rate = book.cells[(1, 1)]
    assert rate.numeric and rate.value == 1.26 and rate.number_format == "#,##0%"
    assert rate.fill == "FFF43F5E" and rate.bold
    signed = book.cells[(1, 2)]
    assert signed.numeric and signed.value == -2.5 and signed.number_format == SIGNED
    assert book.cells[(3, 1)].value == 7.0 and book.cells[(3, 1)].numeric
    # NaN · 무한은 값 없는 칸이다(서식만 있으면 칸만 남는다).
    assert (2, 1) not in book.cells
    assert book.cells[(2, 2)].value is None and not book.cells[(2, 2)].numeric
    assert book.cells[(0, 0)].value == "구분" and not book.cells[(0, 0)].numeric


def test_text_keeps_its_spaces_and_drops_what_xml_cannot_carry() -> None:
    data = _book()
    archive = zipfile.ZipFile(io.BytesIO(data))
    raw = archive.read("xl/sharedStrings.xml").decode("utf-8")
    assert '<t xml:space="preserve"> 앞뒤 빈칸 </t>' in raw
    book = read_workbook(data)["상세 Capa"]
    assert book.cells[(3, 0)].value == "제어문자"


def test_freeze_widths_and_heights_land_in_the_sheet() -> None:
    data = _book()
    parts = _parts(data)
    pane = parts["xl/worksheets/sheet1.xml"].find("m:sheetViews/m:sheetView/m:pane", NS)
    assert pane is not None
    assert (pane.get("xSplit"), pane.get("ySplit"), pane.get("topLeftCell")) == ("1", "1", "B2")
    assert pane.get("state") == "frozen" and pane.get("activePane") == "bottomRight"
    second = parts["xl/worksheets/sheet2.xml"].find("m:sheetViews/m:sheetView/m:pane", NS)
    assert second is not None and second.get("xSplit") is None
    assert (second.get("ySplit"), second.get("activePane")) == ("1", "bottomLeft")
    book = read_workbook(data)
    assert book["상세 Capa"].widths == {0: 34.0, 1: 13.0}
    assert book["상세 Capa"].freeze == (1, 1)
    row = parts["xl/worksheets/sheet1.xml"].findall("m:sheetData/m:row", NS)[2]
    assert (row.get("ht"), row.get("customHeight")) == ("30", "1")
    views = [
        sheet.find("m:sheetViews/m:sheetView", NS)
        for sheet in (parts["xl/worksheets/sheet1.xml"], parts["xl/worksheets/sheet2.xml"])
    ]
    assert [view.get("tabSelected") for view in views if view is not None] == ["1", None]


def test_number_like_text_cells_and_only_those_get_the_ignore_mark() -> None:
    """글자로 넘긴 숫자 꼴(달 머리 「26.11」 · 해 「2026」 · 쉼표 · % · 지수 · 앞뒤 빈칸)만 「텍스트
    형식으로 저장된 숫자」 경고를 끈다 — 숫자 칸 · 「—」 · 기간 글 · 호기 이름 · U+2212 부호 · nan ·
    참거짓은 덮지 않는다. 이웃 칸은 가로 범위, 같은 가로 범위가 이어진 줄은 한 네모다."""
    rows: list[list[XlsxCell | None]] = [
        [XlsxCell("구분"), XlsxCell("26.11"), XlsxCell("26.12"), XlsxCell("27.01"), None],
        [
            XlsxCell("확보율"),
            XlsxCell(1.26),
            XlsxCell("—"),
            XlsxCell("26.11–27.06"),
            XlsxCell("U-1"),
        ],
        [XlsxCell("2026"), XlsxCell("1,234"), XlsxCell("12%"), XlsxCell("−2"), XlsxCell(" 7 ")],
        [XlsxCell("001"), XlsxCell("nan"), XlsxCell("inf"), XlsxCell("1e3"), XlsxCell(True)],
        [XlsxCell("002"), XlsxCell(5), XlsxCell(""), XlsxCell("26.11.5"), XlsxCell(7)],
        [XlsxCell("003"), XlsxCell(6)],
    ]
    data = workbook_bytes([Sheet(name="표", rows=rows)])
    root = _parts(data)["xl/worksheets/sheet1.xml"]
    marks = root.findall("m:ignoredErrors/m:ignoredError", NS)
    assert len(marks) == 1 and marks[0].get("numberStoredAsText") == "1"
    assert marks[0].get("sqref") == "B1:D1 A3:C3 E3 A4:A6 D4"
    sheet = read_workbook(data)["표"]
    covered = sheet.number_text_ignored
    assert covered <= set(sheet.cells)
    assert not any(sheet.cells[at].numeric for at in covered)
    assert {sheet.cells[at].value for at in covered} == {
        "26.11",
        "26.12",
        "27.01",
        "2026",
        "1,234",
        "12%",
        " 7 ",
        "001",
        "002",
        "003",
        "1e3",
    }
    for at in ((0, 0), (1, 2), (1, 3), (1, 4), (2, 3), (3, 1), (3, 2), (3, 4), (4, 3)):
        assert at not in covered, at


def test_a_sheet_without_number_like_text_has_no_ignore_mark() -> None:
    data = workbook_bytes(
        [
            Sheet(
                name="표",
                rows=[[XlsxCell("호기"), XlsxCell("기간")], [XlsxCell("U-1"), XlsxCell(3)]],
            )
        ]
    )
    root = _parts(data)["xl/worksheets/sheet1.xml"]
    assert root.find("m:ignoredErrors", NS) is None
    assert read_workbook(data)["표"].number_text_ignored == frozenset()


def test_the_same_input_is_the_same_bytes() -> None:
    assert _book() == _book()


@pytest.mark.parametrize(
    ("index", "letters"),
    [(0, "A"), (25, "Z"), (26, "AA"), (51, "AZ"), (52, "BA"), (701, "ZZ"), (702, "AAA")],
)
def test_column_letters(index: int, letters: str) -> None:
    assert column_letter(index) == letters


@pytest.mark.parametrize("name", ["", "a" * 32, "상세[1]", "a/b", "'시트"])
def test_a_sheet_name_excel_refuses_is_refused(name: str) -> None:
    with pytest.raises(ValueError):
        Sheet(name=name, rows=[])


def test_colors_must_be_opaque_hex() -> None:
    with pytest.raises(ValueError):
        Style(fill="rgba(244,63,94,0.12)")
    with pytest.raises(ValueError):
        Edge("thin", "red")


def test_duplicate_sheet_names_are_refused() -> None:
    with pytest.raises(ValueError):
        workbook_bytes([Sheet(name="표", rows=[]), Sheet(name="표", rows=[])])
