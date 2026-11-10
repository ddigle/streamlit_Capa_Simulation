# Purpose: 값 · 서식 · 열 너비 · 고정을 든 작은 xlsx 통을 표준 라이브러리만으로 쓴다.

"""작은 xlsx 작성기.

화면 표 하나를 서식째 엑셀로 내려받게 하는 자리다(공정 Capa 상세 「시트 엑셀」). 새 의존성을 넣지
않는다 — 사내 이미지 · WebIDE 가 새 패키지를 받는지 따로 확인해야 하므로 `io/s3_small.py` 처럼
표준 라이브러리(`zipfile` · 글자 XML)만 쓴다.

- **순수 함수다.** Streamlit · 토큰 · 도메인을 모른다 — 색은 `#RRGGBB` 글자, 숫자 꼴은 Excel 꼴
  글자로 받는다. 화면의 무엇을 어떤 칸으로 옮길지는 부르는 쪽(`components/process_capa_workbook.py`)
  몫이다.
- **Excel 이 「복구」 창 없이 여는 꼴**을 지킨다 — 요소 차례는 ECMA-376 차례(worksheet:
  `dimension` · `sheetViews` · `sheetFormatPr` · `cols` · `sheetData` · `pageMargins`, styles:
  `numFmts` · `fonts` · `fills` · `borders` · `cellStyleXfs` · `cellXfs` · `cellStyles`), `fills` 의
  첫 둘은 `none` · `gray125`, 사용자 숫자 꼴 번호는 164 부터, 색은 `FFRRGGBB`, `[Content_Types].xml`
  · `_rels/.rels` · `xl/_rels/workbook.xml.rels` · `docProps` 를 갖춘다. 뼈대는 xlsxwriter 출력과
  같다(테마 파트만 없다 — 글꼴이 테마를 가리키지 않는다).
- **글자는 sharedStrings** 이고 XML 1.0 이 받지 않는 제어 문자는 걷는다. 앞뒤 빈칸은
  `xml:space="preserve"` 로 지킨다.
- **숫자 칸은 숫자 셀**이다. NaN · 무한은 빈 칸이다(그대로 쓰면 Excel 이 복구 창을 띄운다).
  `bool` 은 글자다.
- **통이 늘 같다** — zip 항목 시각과 문서 속성 시각은 넘긴 값(없으면 고정 값)이라 같은 입력은 같은
  바이트다.
"""

from __future__ import annotations

import io
import math
import numbers
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final
from xml.sax.saxutils import escape

__all__ = [
    "Edge",
    "Sheet",
    "Style",
    "XlsxCell",
    "column_letter",
    "workbook_bytes",
]

# 문서 속성 · zip 항목 시각(넘기지 않으면). 같은 입력이 같은 바이트가 되게 한다.
_FIXED_TIME: Final = datetime(2026, 1, 1)
# Excel 기본 글꼴 · 크기. 한글 화면이라 맑은 고딕이다.
DEFAULT_FONT: Final = "맑은 고딕"
DEFAULT_FONT_SIZE: Final = 10.0
# 시트 이름 — Excel 은 31자까지, 이 글자들을 받지 않는다.
_SHEET_NAME_MAX: Final = 31
_SHEET_NAME_FORBIDDEN: Final = frozenset("[]:*?/\\")
# 사용자 숫자 꼴의 첫 번호(그 앞은 Excel 내장 꼴이다).
_FIRST_CUSTOM_FORMAT_ID: Final = 164
# XML 1.0 이 받지 않는 문자(탭 · 줄바꿈 · 캐리지 리턴 밖의 제어 문자, 대리 쌍 반쪽, FFFE · FFFF).
_ILLEGAL_XML: Final = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_HORIZONTAL: Final = frozenset({"left", "center", "right"})
_VERTICAL: Final = frozenset({"top", "center", "bottom"})
_EDGE_STYLES: Final = frozenset({"thin", "medium", "thick", "dashed", "dotted", "hair"})

_NS_MAIN: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PACKAGE_REL: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_XML_HEAD: Final = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


@dataclass(frozen=True)
class Edge:
    """테두리 한 변 — `style` 은 `thin` · `medium` · `thick` · `dashed` · `dotted` · `hair`."""

    style: str
    color: str

    def __post_init__(self) -> None:
        if self.style not in _EDGE_STYLES:
            raise ValueError(f"테두리 꼴을 모릅니다: {self.style}")
        _argb(self.color)


@dataclass(frozen=True)
class Style:
    """칸 하나의 서식. 비운 칸은 Excel 기본(글꼴 `DEFAULT_FONT` · 칠 없음 · 일반 꼴)이다."""

    bold: bool = False
    color: str | None = None
    """글자색 `#RRGGBB`."""

    size: float | None = None
    """글자 크기(pt). None 이면 `DEFAULT_FONT_SIZE`."""

    fill: str | None = None
    """칠 `#RRGGBB`(단색)."""

    number_format: str | None = None
    """Excel 숫자 꼴 글자(`+#,##0.0;"−"#,##0.0;0.0` 꼴). None 이면 일반."""

    horizontal: str | None = None
    vertical: str | None = "center"
    indent: int = 0
    wrap: bool = False
    left: Edge | None = None
    right: Edge | None = None
    top: Edge | None = None
    bottom: Edge | None = None

    def __post_init__(self) -> None:
        if self.horizontal is not None and self.horizontal not in _HORIZONTAL:
            raise ValueError(f"가로 정렬을 모릅니다: {self.horizontal}")
        if self.vertical is not None and self.vertical not in _VERTICAL:
            raise ValueError(f"세로 정렬을 모릅니다: {self.vertical}")
        for color in (self.color, self.fill):
            if color is not None:
                _argb(color)


PLAIN: Final = Style()

CellValue = str | int | float | None


@dataclass(frozen=True)
class XlsxCell:
    """칸 하나 — 값(글자 · 숫자 · 빈 칸)과 서식."""

    value: CellValue = None
    style: Style = PLAIN


@dataclass(frozen=True)
class Sheet:
    """시트 하나.

    `rows` 는 위에서 아래로 줄, 줄마다 왼쪽부터 칸이다(None 은 아무것도 없는 칸). `widths` 는 열
    번호(0부터) → Excel 열 너비, `heights` 는 줄 번호(0부터) → 줄 높이(pt), `freeze` 는 (위에 고정할
    줄 수, 왼쪽에 고정할 열 수)다.
    """

    name: str
    rows: Sequence[Sequence[XlsxCell | None]]
    widths: Mapping[int, float] = field(default_factory=dict)
    heights: Mapping[int, float] = field(default_factory=dict)
    freeze: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > _SHEET_NAME_MAX:
            raise ValueError(f"시트 이름은 1~{_SHEET_NAME_MAX}자입니다: {self.name!r}")
        if set(self.name) & _SHEET_NAME_FORBIDDEN or self.name.startswith("'"):
            raise ValueError(f"시트 이름에 쓸 수 없는 글자가 있습니다: {self.name!r}")
        if self.freeze is not None and (self.freeze[0] < 0 or self.freeze[1] < 0):
            raise ValueError("고정 줄 · 열 수는 0 이상입니다.")


def column_letter(index: int) -> str:
    """열 번호(0부터) → Excel 열 이름(A · Z · AA · …)."""
    if index < 0:
        raise ValueError("열 번호는 0 이상입니다.")
    letters = ""
    number = index + 1
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def workbook_bytes(sheets: Sequence[Sheet], *, created: datetime | None = None) -> bytes:
    """시트들을 xlsx 통 하나의 바이트로 낸다. 첫 시트가 열린 시트다."""
    if not sheets:
        raise ValueError("시트가 하나는 있어야 합니다.")
    names = [sheet.name for sheet in sheets]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError(f"시트 이름이 겹칩니다: {names}")
    moment = created or _FIXED_TIME
    styles = _StyleBook()
    strings = _StringTable()
    sheet_parts = [
        _sheet_xml(sheet, styles, strings, selected=position == 0)
        for position, sheet in enumerate(sheets)
    ]
    parts: list[tuple[str, str]] = [
        ("[Content_Types].xml", _content_types_xml(len(sheets))),
        ("_rels/.rels", _root_rels_xml()),
        ("docProps/app.xml", _app_xml(names)),
        ("docProps/core.xml", _core_xml(moment)),
        ("xl/workbook.xml", _workbook_xml(names)),
        ("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets))),
        ("xl/styles.xml", styles.xml()),
        ("xl/sharedStrings.xml", strings.xml()),
    ]
    parts += [
        (f"xl/worksheets/sheet{number}.xml", part)
        for number, part in enumerate(sheet_parts, start=1)
    ]
    buffer = io.BytesIO()
    stamp = (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in parts:
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body.encode("utf-8"))
    return buffer.getvalue()


# ================================================================== 시트


def _sheet_xml(sheet: Sheet, styles: _StyleBook, strings: _StringTable, *, selected: bool) -> str:
    width = max((len(row) for row in sheet.rows), default=0)
    height = len(sheet.rows)
    dimension = f"A1:{column_letter(width - 1)}{height}" if width and height else "A1"
    parts = [
        _XML_HEAD,
        f'<worksheet xmlns="{_NS_MAIN}" xmlns:r="{_NS_REL}">',
        f'<dimension ref="{dimension}"/>',
        _sheet_views_xml(sheet.freeze, selected=selected),
        '<sheetFormatPr defaultRowHeight="15"/>',
    ]
    if sheet.widths:
        parts.append("<cols>")
        for column in sorted(sheet.widths):
            value = _width(sheet.widths[column])
            parts.append(
                f'<col min="{column + 1}" max="{column + 1}" width="{value}" customWidth="1"/>'
            )
        parts.append("</cols>")
    parts.append("<sheetData>")
    for row_index, row in enumerate(sheet.rows):
        cells = [
            _cell_xml(cell, f"{column_letter(column)}{row_index + 1}", styles, strings)
            for column, cell in enumerate(row)
            if cell is not None
        ]
        cells = [cell for cell in cells if cell]
        row_height = sheet.heights.get(row_index)
        attributes = f' r="{row_index + 1}"'
        if row_height is not None:
            attributes += f' ht="{_number_text(float(row_height))}" customHeight="1"'
        if cells:
            parts.append(f"<row{attributes}>" + "".join(cells) + "</row>")
        elif row_height is not None:
            parts.append(f"<row{attributes}/>")
    parts.append("</sheetData>")
    parts.append(
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
    )
    parts.append("</worksheet>")
    return "".join(parts)


def _sheet_views_xml(freeze: tuple[int, int] | None, *, selected: bool) -> str:
    view = '<sheetView workbookViewId="0"' + (' tabSelected="1"' if selected else "")
    if freeze is None or freeze == (0, 0):
        return f"<sheetViews>{view}/></sheetViews>"
    rows, columns = freeze
    top_left = f"{column_letter(columns)}{rows + 1}"
    if rows and columns:
        pane = (
            f'<pane xSplit="{columns}" ySplit="{rows}" topLeftCell="{top_left}" '
            'activePane="bottomRight" state="frozen"/>'
            f'<selection pane="topRight" activeCell="{column_letter(columns)}1" '
            f'sqref="{column_letter(columns)}1"/>'
            f'<selection pane="bottomLeft" activeCell="A{rows + 1}" sqref="A{rows + 1}"/>'
            f'<selection pane="bottomRight" activeCell="{top_left}" sqref="{top_left}"/>'
        )
    elif rows:
        pane = (
            f'<pane ySplit="{rows}" topLeftCell="{top_left}" activePane="bottomLeft" '
            'state="frozen"/>'
            f'<selection pane="bottomLeft" activeCell="{top_left}" sqref="{top_left}"/>'
        )
    else:
        pane = (
            f'<pane xSplit="{columns}" topLeftCell="{top_left}" activePane="topRight" '
            'state="frozen"/>'
            f'<selection pane="topRight" activeCell="{top_left}" sqref="{top_left}"/>'
        )
    return f"<sheetViews>{view}>{pane}</sheetView></sheetViews>"


def _cell_xml(cell: XlsxCell, ref: str, styles: _StyleBook, strings: _StringTable) -> str:
    style_id = styles.index(cell.style)
    style = f' s="{style_id}"' if style_id else ""
    value = cell.value
    # 흔한 꼴(파이썬 실수 · 글자)은 추상 기반 검사 없이 먼저 — 큰 표(5만 칸)에서 칸마다 든다.
    if type(value) is float:
        if not math.isfinite(value):
            return f'<c r="{ref}"{style}/>' if style_id else ""
        return f'<c r="{ref}"{style}><v>{_number_text(value)}</v></c>'
    if type(value) is str and value:
        text = _clean(value)
        if text:
            return f'<c r="{ref}"{style} t="s"><v>{strings.index(text)}</v></c>'
        return f'<c r="{ref}"{style}/>' if style_id else ""
    if isinstance(value, bool):
        value = "TRUE" if value else "FALSE"
    if isinstance(value, numbers.Integral):
        return f'<c r="{ref}"{style}><v>{int(value)}</v></c>'
    if isinstance(value, numbers.Real):
        number = float(value)
        if not math.isfinite(number):
            return f'<c r="{ref}"{style}/>' if style_id else ""
        return f'<c r="{ref}"{style}><v>{_number_text(number)}</v></c>'
    if value is None:
        return f'<c r="{ref}"{style}/>' if style_id else ""
    text = _clean(str(value))
    if not text:
        return f'<c r="{ref}"{style}/>' if style_id else ""
    return f'<c r="{ref}"{style} t="s"><v>{strings.index(text)}</v></c>'


def _number_text(value: int | float) -> str:
    """숫자 칸 글자 — 정수는 그대로, 실수는 되읽어 같은 가장 짧은 글자(`repr`)."""
    if isinstance(value, int):
        return str(value)
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def _width(value: float) -> str:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"열 너비는 양수입니다: {value}")
    return _number_text(round(float(value), 4))


def _clean(text: str) -> str:
    return _ILLEGAL_XML.sub("", text)


# ================================================================== 글자 표


class _StringTable:
    def __init__(self) -> None:
        self._order: list[str] = []
        self._index: dict[str, int] = {}
        self._count = 0

    def index(self, text: str) -> int:
        self._count += 1
        found = self._index.get(text)
        if found is None:
            found = len(self._order)
            self._index[text] = found
            self._order.append(text)
        return found

    def xml(self) -> str:
        items = []
        for text in self._order:
            preserve = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
            items.append(f"<si><t{preserve}>{escape(text)}</t></si>")
        return (
            _XML_HEAD
            + f'<sst xmlns="{_NS_MAIN}" count="{self._count}" uniqueCount="{len(self._order)}">'
            + "".join(items)
            + "</sst>"
        )


# ================================================================== 서식 표


@dataclass(frozen=True)
class _Font:
    bold: bool
    color: str | None
    size: float


@dataclass(frozen=True)
class _Border:
    left: Edge | None
    right: Edge | None
    top: Edge | None
    bottom: Edge | None


@dataclass(frozen=True)
class _Xf:
    format_id: int
    font_id: int
    fill_id: int
    border_id: int
    horizontal: str | None
    vertical: str | None
    indent: int
    wrap: bool


class _StyleBook:
    """서식 → `cellXfs` 번호. 글꼴 · 칠 · 테두리 · 숫자 꼴은 같은 값을 한 번만 싣는다."""

    def __init__(self) -> None:
        self._formats: dict[str, int] = {}
        self._fonts: dict[_Font, int] = {_Font(False, None, DEFAULT_FONT_SIZE): 0}
        # 첫 둘은 Excel 이 늘 기대하는 자리(none · gray125)다 — 다른 값을 두면 복구 창이 뜬다.
        self._fills: dict[str | None, int] = {None: 0}
        self._borders: dict[_Border, int] = {_Border(None, None, None, None): 0}
        default = _Xf(0, 0, 0, 0, None, None, 0, False)
        self._xfs: dict[_Xf, int] = {default: 0}
        self._cache: dict[Style, int] = {}
        # 같은 서식 객체를 여러 칸이 나눠 쓰는 표(부르는 쪽이 서식을 한 번 지어 돌려씀)는 객체 값
        # 해시 없이 찾는다. 객체를 함께 쥐어 두므로 그 id 가 이 통을 짓는 동안 다른 객체로 바뀌지
        # 않는다.
        self._by_identity: dict[int, tuple[Style, int]] = {}

    def index(self, style: Style) -> int:
        known = self._by_identity.get(id(style))
        if known is not None and known[0] is style:
            return known[1]
        found = self._value_index(style)
        self._by_identity[id(style)] = (style, found)
        return found

    def _value_index(self, style: Style) -> int:
        cached = self._cache.get(style)
        if cached is not None:
            return cached
        if style == PLAIN:
            self._cache[style] = 0
            return 0
        format_id = 0
        if style.number_format:
            format_id = self._formats.setdefault(
                style.number_format, _FIRST_CUSTOM_FORMAT_ID + len(self._formats)
            )
        font = _Font(
            style.bold,
            style.color.upper() if style.color else None,
            DEFAULT_FONT_SIZE if style.size is None else float(style.size),
        )
        font_id = self._fonts.setdefault(font, len(self._fonts))
        fill_key = style.fill.upper() if style.fill else None
        fill_id = self._fills.setdefault(fill_key, len(self._fills) + 1)
        border = _Border(style.left, style.right, style.top, style.bottom)
        border_id = self._borders.setdefault(border, len(self._borders))
        xf = _Xf(
            format_id,
            font_id,
            fill_id,
            border_id,
            style.horizontal,
            style.vertical,
            max(0, int(style.indent)),
            style.wrap,
        )
        xf_id = self._xfs.setdefault(xf, len(self._xfs))
        self._cache[style] = xf_id
        return xf_id

    def xml(self) -> str:
        parts = [_XML_HEAD, f'<styleSheet xmlns="{_NS_MAIN}">']
        if self._formats:
            parts.append(f'<numFmts count="{len(self._formats)}">')
            for code, number in sorted(self._formats.items(), key=lambda item: item[1]):
                parts.append(f'<numFmt numFmtId="{number}" formatCode="{_attribute(code)}"/>')
            parts.append("</numFmts>")
        parts.append(f'<fonts count="{len(self._fonts)}">')
        for font in sorted(self._fonts, key=self._fonts.__getitem__):
            parts.append(
                "<font>"
                + ("<b/>" if font.bold else "")
                + f'<sz val="{_number_text(font.size)}"/>'
                + (f'<color rgb="{_argb(font.color)}"/>' if font.color else "")
                + f'<name val="{_attribute(DEFAULT_FONT)}"/><family val="2"/><charset val="129"/>'
                + "</font>"
            )
        parts.append("</fonts>")
        fills = sorted(self._fills, key=lambda key: self._fills[key])
        parts.append(f'<fills count="{len(fills) + 1}">')
        parts.append('<fill><patternFill patternType="none"/></fill>')
        parts.append('<fill><patternFill patternType="gray125"/></fill>')
        for color in fills:
            if color is None:
                continue
            parts.append(
                '<fill><patternFill patternType="solid">'
                f'<fgColor rgb="{_argb(color)}"/><bgColor indexed="64"/>'
                "</patternFill></fill>"
            )
        parts.append("</fills>")
        parts.append(f'<borders count="{len(self._borders)}">')
        for border in sorted(self._borders, key=self._borders.__getitem__):
            parts.append(
                "<border>"
                + _edge_xml("left", border.left)
                + _edge_xml("right", border.right)
                + _edge_xml("top", border.top)
                + _edge_xml("bottom", border.bottom)
                + "<diagonal/></border>"
            )
        parts.append("</borders>")
        parts.append(
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
            "</cellStyleXfs>"
        )
        parts.append(f'<cellXfs count="{len(self._xfs)}">')
        for xf in sorted(self._xfs, key=self._xfs.__getitem__):
            parts.append(_xf_xml(xf))
        parts.append("</cellXfs>")
        parts.append(
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        )
        parts.append('<dxfs count="0"/>')
        parts.append(
            '<tableStyles count="0" defaultTableStyle="TableStyleMedium9" '
            'defaultPivotStyle="PivotStyleLight16"/>'
        )
        parts.append("</styleSheet>")
        return "".join(parts)


def _xf_xml(xf: _Xf) -> str:
    if xf == _Xf(0, 0, 0, 0, None, None, 0, False):
        return '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    alignment = ""
    if xf.horizontal:
        alignment += f' horizontal="{xf.horizontal}"'
    if xf.vertical:
        alignment += f' vertical="{xf.vertical}"'
    if xf.wrap:
        alignment += ' wrapText="1"'
    if xf.indent:
        alignment += f' indent="{xf.indent}"'
    applied = (
        (' applyNumberFormat="1"' if xf.format_id else "")
        + (' applyFont="1"' if xf.font_id else "")
        + (' applyFill="1"' if xf.fill_id else "")
        + (' applyBorder="1"' if xf.border_id else "")
        + (' applyAlignment="1"' if alignment else "")
    )
    head = (
        f'<xf numFmtId="{xf.format_id}" fontId="{xf.font_id}" fillId="{xf.fill_id}" '
        f'borderId="{xf.border_id}" xfId="0"{applied}'
    )
    if not alignment:
        return head + "/>"
    return head + f"><alignment{alignment}/></xf>"


def _edge_xml(side: str, edge: Edge | None) -> str:
    if edge is None:
        return f"<{side}/>"
    return f'<{side} style="{edge.style}"><color rgb="{_argb(edge.color)}"/></{side}>'


def _argb(color: str) -> str:
    """`#RRGGBB` → `FFRRGGBB`. 다른 꼴(이름 · rgba)은 받지 않는다 — 알파는 부르는 쪽이 섞어 온다."""
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise ValueError(f"색은 #RRGGBB 꼴입니다: {color!r}")
    return "FF" + color[1:].upper()


def _attribute(text: str) -> str:
    return escape(_clean(text), {'"': "&quot;"})


# ================================================================== 통 파트


def _content_types_xml(sheet_count: int) -> str:
    overrides = [
        (
            "/docProps/app.xml",
            "application/vnd.openxmlformats-officedocument.extended-properties+xml",
        ),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        (
            "/xl/styles.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml",
        ),
        (
            "/xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        ),
    ]
    overrides += [
        (
            f"/xl/worksheets/sheet{number}.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
        )
        for number in range(1, sheet_count + 1)
    ]
    overrides.append(
        (
            "/xl/sharedStrings.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
        )
    )
    return (
        _XML_HEAD
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(f'<Override PartName="{name}" ContentType="{kind}"/>' for name, kind in overrides)
        + "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        _XML_HEAD
        + f'<Relationships xmlns="{_NS_PACKAGE_REL}">'
        + f'<Relationship Id="rId1" Type="{_NS_REL}/officeDocument" Target="xl/workbook.xml"/>'
        + '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
        'core-properties" Target="docProps/core.xml"/>'
        + f'<Relationship Id="rId3" Type="{_NS_REL}/extended-properties" '
        'Target="docProps/app.xml"/>' + "</Relationships>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    items = [
        f'<Relationship Id="rId{number}" Type="{_NS_REL}/worksheet" '
        f'Target="worksheets/sheet{number}.xml"/>'
        for number in range(1, sheet_count + 1)
    ]
    items.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="{_NS_REL}/styles" Target="styles.xml"/>'
    )
    items.append(
        f'<Relationship Id="rId{sheet_count + 2}" Type="{_NS_REL}/sharedStrings" '
        'Target="sharedStrings.xml"/>'
    )
    return (
        _XML_HEAD
        + f'<Relationships xmlns="{_NS_PACKAGE_REL}">'
        + "".join(items)
        + "</Relationships>"
    )


def _workbook_xml(names: Sequence[str]) -> str:
    sheets = "".join(
        f'<sheet name="{_attribute(name)}" sheetId="{number}" r:id="rId{number}"/>'
        for number, name in enumerate(names, start=1)
    )
    return (
        _XML_HEAD
        + f'<workbook xmlns="{_NS_MAIN}" xmlns:r="{_NS_REL}">'
        + '<fileVersion appName="xl" lastEdited="4" lowestEdited="4" rupBuild="4505"/>'
        + "<workbookPr/>"
        + '<bookViews><workbookView xWindow="240" yWindow="15" windowWidth="16095" '
        'windowHeight="9660"/></bookViews>'
        + f"<sheets>{sheets}</sheets>"
        + '<calcPr calcId="124519"/>'
        + "</workbook>"
    )


def _core_xml(moment: datetime) -> str:
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        _XML_HEAD
        + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
        'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        + "<dc:creator></dc:creator><cp:lastModifiedBy></cp:lastModifiedBy>"
        + f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
        + f'<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>'
        + "</cp:coreProperties>"
    )


def _app_xml(names: Sequence[str]) -> str:
    titles = "".join(f"<vt:lpstr>{escape(_clean(name))}</vt:lpstr>" for name in names)
    return (
        _XML_HEAD + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        'extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
        'docPropsVTypes">'
        + "<Application>Microsoft Excel</Application><DocSecurity>0</DocSecurity>"
        + "<ScaleCrop>false</ScaleCrop>"
        + '<HeadingPairs><vt:vector size="2" baseType="variant">'
        + "<vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>"
        + f"<vt:variant><vt:i4>{len(names)}</vt:i4></vt:variant></vt:vector></HeadingPairs>"
        + f'<TitlesOfParts><vt:vector size="{len(names)}" baseType="lpstr">{titles}'
        + "</vt:vector></TitlesOfParts>"
        + "<LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>"
        + "<HyperlinksChanged>false</HyperlinksChanged><AppVersion>12.0000</AppVersion>"
        + "</Properties>"
    )
