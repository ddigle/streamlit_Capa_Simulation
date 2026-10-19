# Purpose: Plotly 테두리·고정 행·표 밖 칸 글자 층 헬퍼와 검증 없는 spec 빠른 길을 제공한다.

"""Plotly Figure 의 제목·테두리·분기 경계·고정 행과 `go.Table` 밖 칸 글자 층을 그리는 공통
헬퍼와 검증 없는 spec 빠른 길을 제공한다."""

from __future__ import annotations

import html
import math
import numbers
import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Final, cast

import plotly.graph_objects as go
from plotly.validator_cache import ValidatorCache

from capa_simulation.components.home_dimensions import (
    CORNER_NOTE_RIGHT_PADDING_PX,
    delta_ink_yshift_px,
    delta_line_shift_px,
    value_ink_yshift_px,
)
from capa_simulation.design import tokens

TRANSPARENT_COLOR = tokens.TRANSPARENT


# Figure 에 붙여 두는 누적함. 이름은 Plotly 속성과 겹치지 않아야 한다.
_PENDING_LAYOUT_ITEMS = "_capa_pending_layout_items"


# 앱이 만든 레이아웃 항목·표 spec 을 Plotly 검증 없이 넣을지 정하는 **한 스위치**. 평소에는 꺼져
# 있어(검증을 건너뛴다) 빠르고, 테스트가 `plotly_validation()` 으로 켜면 전부 검증하는 경로를
# 그대로 탄다. 두 경로의 Figure JSON 이 같다는 것을 테스트가 늘 두 경로를 다 돌려 확인한다
# (`tests/test_plotly_fast_path.py`). 검증을 건너뛰는 길은 Plotly 의 비공개 인자 `_validate` 에
# 기댄다 — `plotly>=5.24,<7` 고정이 지키고, 인자가 사라지면 그 테스트가 먼저 깨진다.
_PLOTLY_VALIDATION: ContextVar[bool] = ContextVar("capa_plotly_validation", default=False)


@contextmanager
def plotly_validation() -> Iterator[None]:
    """이 블록 안에서는 검증을 건너뛰지 않는다. 전부 검증하는 경로와 견주는 테스트용 스위치다."""
    token = _PLOTLY_VALIDATION.set(True)
    try:
        yield
    finally:
        _PLOTLY_VALIDATION.reset(token)


def plotly_validation_enabled() -> bool:
    return _PLOTLY_VALIDATION.get()


# spec 으로 세울 수 있는 trace 종류. 여기 없는 종류는 검증 생성자로 세운다.
_SPEC_TRACE_CLASSES: dict[str, Any] = {"table": go.Table, "scatter": go.Scatter}


def figure_from_spec(spec: Mapping[str, Any]) -> go.Figure:
    """평범한 dict(`{"data": [...], "layout": {...}}`) 로 조립한 Figure 를 세운다.

    평소에는 `go.Figure(spec, _validate=False)` 로 검증 생성자를 건너뛴다. 검증 생성자는 표 하나에
    셀 수만 개를 다시 검사한다(합성 표본 2,660행 월별 표에서 약 1초, 샘플 관측). 그래서 **spec 은
    Plotly 정규형으로 적어야 한다** — 밑줄 줄임 키(`fill_color`)는 검증 없이는 펼쳐지지 않고 글자
    그대로 남아 Plotly.js 가 무시한다. `{"fill": {"color": ...}}` 처럼 중첩 dict 로 쓴다.

    세우기 전에 spec 의 **키 이름**을 Plotly 속성 목록에 대 본다(하위 dict 로는 내려가고, 값
    배열은 보지 않는다. 번호 붙은 축 `xaxis2` 는 `xaxis` 로 본다). 모르는 이름·밑줄 줄임 키가
    하나라도 있으면 검증 생성자로 세운다 — 오타는 지금처럼 예외가 되고 줄임 키는 펼쳐진다.
    **dict 의 목록을 받는 속성**
    (`layout.shapes`·`annotations` 등)은 원소를 보지 않으므로 있기만 해도 검증 생성자로 세운다.
    도형·주석은 spec 에 넣지 말고 `append_layout_items`·`flush_layout_items` 로 넣는다.
    값(색 글자·숫자 범위)은 보지 않는다. 같은지는 스위치를 켠 경로와 JSON 을 견주는 테스트가 본다.

    세운 뒤에는 검증을 다시 켠다. 그 뒤에 이 Figure 를 고치는 코드는 지금처럼 검증을 거친다.
    `go.Figure` 가 spec 을 깊은 복사하므로 Figure 가 호출부 dict 를 붙잡지 않는다.
    """
    if plotly_validation_enabled() or not _spec_keys_known(spec):
        return go.Figure(spec)
    figure = go.Figure(spec, _validate=False)
    figure._validate = True
    figure.layout._validate = True
    for trace in figure.data:
        trace._validate = True
    return figure


def _spec_keys_known(spec: Mapping[str, Any]) -> bool:
    if set(spec) - {"data", "layout"}:
        return False
    for trace in spec.get("data", ()):
        if not isinstance(trace, Mapping):
            return False
        trace_class = _SPEC_TRACE_CLASSES.get(trace.get("type", ""))
        if trace_class is None or not _keys_known(trace_class, trace):
            return False
    layout = spec.get("layout", {})
    return isinstance(layout, Mapping) and _keys_known(go.Layout, layout)


def _keys_known(owner: Any, item: Mapping[str, Any]) -> bool:
    """키 이름이 모두 Plotly 속성인지. 하위 dict 는 그 속성의 클래스로 내려가 본다.

    하위 칸이 있는 속성(`data_class` 를 가진 검증기)에 dict 가 아닌 값이 오면 False 다 — dict 의
    **목록**을 받는 배열 속성(`layout.shapes`·`annotations`·`images`)도 여기 걸린다. 목록 속 원소는
    보지 않기 때문이다. 템플릿 이름 글자처럼 검증 없이는 풀리지 않는 값도 같다. 하위 칸이 없는
    속성에 dict 가 와도 False 다. 모두 검증 생성자로 세운다.
    """
    for prop, value in item.items():
        name = _validator_prop_name(owner, prop)
        if name is None:
            return False
        child = getattr(ValidatorCache.get_validator(owner._path_str, name), "data_class", None)
        if child is None:
            if isinstance(value, Mapping):
                return False
        elif not isinstance(value, Mapping) or not _keys_known(child, value):
            return False
    return True


def _validator_prop_name(owner: Any, prop: str) -> str | None:
    """검증기를 찾을 속성 이름. 모르는 이름은 None 이다.

    번호 붙은 축(`xaxis2`)은 레이아웃만 받고 `xaxis` 의 검증기를 쓴다. Plotly 가 이름을 바꿔
    담는 꼴(`xaxis1`·`xaxis02`)은 모르는 이름으로 보아 검증 생성자에 맡긴다.
    """
    if prop in owner._valid_props:
        return prop
    pattern = getattr(owner, "_subplotid_prop_re", None)
    match = pattern.match(prop) if pattern is not None else None
    if match is None:
        return None
    number = match.group(2)
    if number != str(int(number)) or int(number) < 2:
        return None
    return str(match.group(1))


def static_chart_config() -> dict[str, Any]:
    """조작이 없는 그림의 `st.plotly_chart` config. 결과표·라벨 Figure 가 쓴다.

    부를 때마다 새 dict 를 만든다. 모듈 상수 하나를 돌려주면 호출부가 그것을 고칠 때
    다른 화면까지 같이 바뀐다.
    """
    return {"displayModeBar": False, "staticPlot": True}


def hover_chart_config() -> dict[str, Any]:
    """hover 는 살리고 나머지 조작만 끄는 config.

    `staticPlot` 은 hover 까지 함께 끈다. 빼면 `displayModeBar` 기본값이 "hover" 로,
    `doubleClick`·`showAxisDragHandles` 는 켜짐으로 돌아가므로 셋을 직접 끈다. 드래그
    확대는 Figure 축의 `fixedrange` 가 막는다.
    """
    return {"displayModeBar": False, "doubleClick": False, "showAxisDragHandles": False}


def chart_canvas_layout(*, font_size: int) -> dict[str, Any]:
    """캔버스 두 배경색과 기본 서체. **토큰은 부를 때 읽는다.**

    모듈 상수나 기본 인자로 굳히면 그 값만 프로세스가 처음 읽은 테마에 남는다
    (`tests/test_theme_tokens_follow_the_run.py`).
    """
    return {
        "paper_bgcolor": tokens.CHART_CANVAS,
        "plot_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": font_size},
    }


# ---------------------------------------------------------------- 표 칸 글자를 표 밖에서 그리기
#
# `go.Table` 은 칸 글자에 마크업(`<b>`·`<br>`)이 있으면 칸마다 "그린 다음 재서 옮기는" 길로
# 간다. 칸 하나를 옮기고 다음 칸을 재는 사이마다 브라우저가 스타일을 새로 계산하므로 비용이
# 칸 수에 비례한다(합성 표본 표준 목표 131주 표에서 화면 하나에 1초 남짓, 샘플 관측). 그래서
# 마크업 글자는 같은 Figure 의 숨긴 축 위 scatter 글자 trace 로 옮겨 그린다 — scatter 글자는
# 재지 않고 자리를 셈으로 잡는다.
#
# Plotly 는 표를 카테시안 trace **위에** 그린다. 그래서 글자를 옮긴 칸의 표 면은 투명이어야
# 하고, 그 자리 면색은 `layer: below` 도형으로 깐다(머리글 띠는 `table_header_band`).

# plotly.js `table` 의 `cellPad`. `go.Table` 은 칸 글자의 줄 상자를 칸 위 모서리에서 이만큼
# 띄워 놓는다 — 마크업이 있든 없든 같다.
TABLE_CELL_PAD_PX = 8

# `go.Table` 은 열마다 그 열 폭에 선 굵기 반(올림 1px)씩을 양옆으로 더한 사각형으로 칸 글자를
# 자른다(plotly.js `columnBoundaryClippath`). 글자를 자르는 축도 열 경계 밖으로 이만큼 나간다.
TABLE_COLUMN_CLIP_OVERHANG_PX = 1

# 마크업 칸 글자의 점을 칸 위 모서리에서 `cellPad + 이 값 em` 에 둔다. 기준선은 그보다 0.25em
# 아래인 `cellPad + 1.08em` — 맑은 고딕의 어센트다. `table_text_y` 를 보라.
TABLE_MARKUP_TEXT_EM = 0.83


def table_text_y(top_px: float, font_size: float, *, markup: bool) -> float:
    """`go.Table` 이 칸 글자를 놓던 자리에 scatter 글자를 세우는 y(그림 위에서 잰 px).

    scatter 글자(`middle center`)는 기준선을 점보다 글자 크기의 0.25 배 아래에 놓는다.
    `go.Table` 은 두 갈래다.

    - 마크업이 없는 칸은 기준선이 칸 위 모서리에서 `cellPad + 0.75em` 이다. 서체와 무관하므로
      점을 `cellPad + 0.5em` 에 두면 화소까지 같다.
    - 마크업이 있는 칸은 그린 뒤 재서 줄 상자 윗변을 `cellPad` 에 맞추므로 기준선이
      `cellPad + 어센트` 다(Chrome 은 어센트를 정수 px 로 반올림한다). 어센트는 서체마다 달라 한
      값으로 모두를 맞출 수 없으니 사용자가 실제로 보는 서체에 맞춘다. 앱 서체 스택
      (`tokens.FONT_FAMILY`)은 `Noto Sans KR` 이 먼저지만 앱이 그 글꼴 파일을 보내지 않으므로
      (`@font-face` 는 Archivo 부분 글꼴뿐, `components/typography.py`) PC 에 깔린 글꼴이 정한다.
      서피스는 맑은 고딕으로 그리고(사내 런북 7-16 B), 사내 Windows 도 Noto Sans KR 을 따로 깔지
      않았다면 같다. 맑은 고딕 어센트는 약 1.08em 이다 — `monthly_table_base.header_label` 설명의
      실측(굵기 속성만 준 머리글이 `<b>` 머리글보다 4.5px 위, 14px)이
      `round(1.08 × 14) − 0.75 × 14 = 4.5` 와 맞고, DejaVu Sans(0.93em)면 2.5px, Noto Sans
      KR(1.16em)이면 5.5px 라 맑은 고딕으로만 맞는다.
      그래서 기준선을 `cellPad + 1.08em`(점 `cellPad + 0.83em`)에 둔다 — 맑은 고딕에서 14px 0.1px,
      15px 0.2px 아래로 셈된다. Noto Sans KR 이 깔린 PC 에서는 약 0.9px 위, 사용자가 보지 않는
      헤드리스 리눅스의 DejaVu Sans 에서는 약 2.1px 아래다(Chrome 실측이 이 셈과 같다).

    소수 셋째 자리로 반올림한다 — 부동소수 찌꺼기(`19.619999999999997`)가 글자마다 그림 JSON 에
    실린다(131주 표 머리글에서 1.8KB).
    """
    offset_em = TABLE_MARKUP_TEXT_EM if markup else 0.5
    return round(top_px + TABLE_CELL_PAD_PX + font_size * offset_em, 3)


# 칸 글자가 제 칸 폭을 넘을 수 있는지 가르는 글자 너비의 위 한계(글자 크기 배수). 넓게 잡으면
# 넘치지 않는 글자에도 자르는 축이 하나 붙을 뿐이고, 좁게 잡으면 넘친 글자가 옆 칸으로 번진다.
#
# 인쇄 가능한 ASCII 는 글자마다 Chrome 캔버스로 DejaVu Sans·Noto Sans CJK KR·Liberation Sans·
# Ubuntu Sans 의 보통·굵은 꼴을 재어 가장 넓은 값에 10% 를 얹고 0.1 단위로 올렸다(2026-10-20).
# 맑은 고딕은 이 환경에 없어 재지 못했고 그 넉넉함에 기댄다. 한글·전각은 같은 실측 최대 1.00 에
# 10% 를 얹는다. 그 밖의 글자는 대체 글꼴(기호·이모지)로 그려질 수 있어 더 넓게 본다.
_ASCII_WIDTH_EM_CLASSES: Final = (
    (0.4, "'ijl "),
    (0.5, "|I,.:;-/\\f"),
    (0.6, "!()[]tr*"),
    (0.7, '_J"zcs?`'),
    (0.8, "LxvykaeTEFo$0123456789hnu{}bdgpqSYZ"),
    (0.9, "PCBRXAVKU"),
    (1.0, "GDHN#+<=>^~OQ&"),
    (1.1, "wM"),
    (1.2, "%@m"),
    (1.3, "W"),
)
_CHARACTER_WIDTH_EM: Final = {
    character: width for width, characters in _ASCII_WIDTH_EM_CLASSES for character in characters
} | {"\u00a0": 0.4}
_WIDE_CHARACTER_WIDTH_EM = 1.1
_OTHER_CHARACTER_WIDTH_EM = 1.3
_MARKUP_TAG = re.compile(r"<[^>]*>")
_LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)


def table_text_max_width_px(text: str, font_size: float) -> float:
    """칸 글자가 그려질 때 차지할 수 있는 가장 넓은 폭(px). 실제 폭은 이보다 크지 않다.

    Plotly 글자 마크업(`<b>`·`<br>`·`&amp;`)을 풀어 줄마다 재고 가장 긴 줄을 돌려준다.
    """
    widest = 0.0
    for line in _LINE_BREAK.split(text):
        units = sum(
            _character_width_em(character) for character in html.unescape(_MARKUP_TAG.sub("", line))
        )
        widest = max(widest, units)
    return widest * font_size


def _character_width_em(character: str) -> float:
    known = _CHARACTER_WIDTH_EM.get(character)
    if known is not None:
        return known
    if unicodedata.east_asian_width(character) in {"F", "W"}:
        return _WIDE_CHARACTER_WIDTH_EM
    return _OTHER_CHARACTER_WIDTH_EM


@dataclass(frozen=True)
class TableText:
    """같은 글꼴로 그리는 칸 글자 한 벌. `cells` 는 글자마다 (열 번호, y, 글자)다.

    y 는 그림 위에서 잰 px 다(`table_text_y`).
    """

    cells: Sequence[tuple[int, float, str]]
    font: Mapping[str, Any]


def table_text_layer(
    texts: Sequence[TableText],
    *,
    column_widths: Sequence[float],
    width_px: float,
    height_px: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """`go.Table` 밖으로 옮긴 칸 글자의 scatter spec 들과 그 축(레이아웃 칸)을 돌려준다.

    spec 은 `figure_from_spec` 정규형이다. x 축은 칸 폭 단위(0 ~ 폭 합), y 축은 **그림 위에서 잰
    px** 다(뒤집힌 축). 여백이 0 이라 그림 전체가 그대로 축 영역이다. 글자는 칸 가운데 점에 가운데로
    선다(`text-anchor: middle`) — 칸 가운데 정렬과 같다. `<b>` 같은 마크업은 표 칸과 같은 규칙으로
    풀린다. 빈 글자는 그리지 않는다.

    **넘친 글자는 제 칸 경계에서 자른다** — `go.Table` 이 열마다 하던 것이다. 자르는 단위는 축
    영역이라, 넘칠 수 있는 글자(`table_text_max_width_px` 가 칸 폭을 넘는 것)만 그 열 하나를
    덮는 축(`xaxis2`…, 영역 = 열 구간 ± `TABLE_COLUMN_CLIP_OVERHANG_PX`)에 따로 얹고
    `cliponaxis` 를 켠다. 그 축의 범위는 영역에 맞춰 잡아 같은 x 가 같은 자리에 선다. 나머지
    글자는 자를 일이 없어 벌마다 한 trace(`cliponaxis` 끔)에 남는다 — 넘칠 수 없는 글자뿐인
    그림(월 칸·짧은 머리글)은 축도 trace 도 늘지 않는다. 축 하나·trace 하나가 그대로 노드와
    전송 바이트라 모든 열에 축을 두지 않는다 — 131주·300행 합성 표 실험에서 열마다 축을 두면 그림
    JSON 이 20%, 그리기가 9% 늘었다.

    돌려준 목록의 i 번째는 늘 `texts[i]` 의 자르지 않는 trace 다(글자가 다 빠져도 있다). 자르는
    trace 는 그 뒤에 열 차례로, 한 열 안에서는 `texts` 차례로 온다.

    `width_px` 는 그림이 실제로 그려지는 폭(px)이다 — 칸 폭을 px 로 바꿔 넘칠 수 있는지를 가른다.

    축 영역 바탕(`plot_bgcolor`)은 종이 바탕과 같은 색(`tokens.CHART_CANVAS`)이라 Plotly 가 바탕을
    따로 그리지 않는다. 자르는 축이 있으면 투명으로 바꾼다 — 그 축의 영역은 앞 축의 영역과 겹쳐
    Plotly 가 그 바탕을 자기 층 맨 아래, 곧 `layer: below` 도형(머리글 띠·칸 면색) **위**에 깐다.
    그때 바탕은 종이 색과 아래층 도형이 맡는다.
    """
    width_units = sum(column_widths) or 1
    starts = [sum(column_widths[:index]) for index in range(len(column_widths))]
    centers = [start + width / 2 for start, width in zip(starts, column_widths, strict=True)]
    px_per_unit = width_px / width_units
    # 폭을 모르는(0) 그림은 자를 자리도 없다. 모두 자르지 않는 trace 에 둔다.
    limit_px = [width * px_per_unit if px_per_unit > 0 else math.inf for width in column_widths]
    kept: list[list[tuple[float, float, str]]] = []
    clipped: dict[int, list[list[tuple[float, float, str]]]] = {}
    for set_index, text_set in enumerate(texts):
        font_size = float(text_set.font.get("size", 12))
        own: list[tuple[float, float, str]] = []
        for column, y, text in text_set.cells:
            if not text:
                continue
            cell = (centers[column], y, text)
            if table_text_max_width_px(text, font_size) <= limit_px[column]:
                own.append(cell)
            else:
                clipped.setdefault(column, [[] for _ in texts])[set_index].append(cell)
        kept.append(own)

    hidden: dict[str, Any] = {"visible": False, "fixedrange": True}
    layout: dict[str, Any] = {
        "xaxis": {**hidden, "range": [0, width_units]},
        "yaxis": {**hidden, "range": [height_px, 0]},
        "plot_bgcolor": TRANSPARENT_COLOR if clipped else tokens.CHART_CANVAS,
    }
    traces = [
        _table_text_trace(cells, text_set.font) for cells, text_set in zip(kept, texts, strict=True)
    ]
    for axis_number, column in enumerate(sorted(clipped), start=2):
        overhang = TABLE_COLUMN_CLIP_OVERHANG_PX / px_per_unit
        low = max(0.0, starts[column] - overhang)
        high = min(float(width_units), starts[column] + column_widths[column] + overhang)
        layout[f"xaxis{axis_number}"] = {
            **hidden,
            "range": [low, high],
            "domain": [low / width_units, high / width_units],
            "anchor": "y",
        }
        for cells, text_set in zip(clipped[column], texts, strict=True):
            if cells:
                traces.append(_table_text_trace(cells, text_set.font, xaxis=f"x{axis_number}"))
    return traces, layout


def _table_text_trace(
    cells: Sequence[tuple[float, float, str]],
    font: Mapping[str, Any],
    *,
    xaxis: str | None = None,
) -> dict[str, Any]:
    """칸 글자 한 벌의 scatter spec. `xaxis` 를 주면 그 축 영역에서 자른다."""
    trace: dict[str, Any] = {
        "type": "scatter",
        "mode": "text",
        "x": [x for x, _, _ in cells],
        "y": [y for _, y, _ in cells],
        "text": [text for _, _, text in cells],
        "textposition": "middle center",
        "textfont": dict(font),
        "hoverinfo": "skip",
        "showlegend": False,
        "cliponaxis": xaxis is not None,
    }
    if xaxis is not None:
        trace["xaxis"] = xaxis
    return trace


def table_header_band(*, header_bottom_y: float) -> dict[str, Any]:
    """머리글 띠 도형. `header_bottom_y` 는 머리글 아랫변(paper y)이다.

    표 머리글 면을 투명하게 둔 자리나 표 없이 그리는 격자에 같은 색을 글자 아래(`layer: below`)로
    깐다.
    """
    return {
        "type": "rect",
        "x0": 0,
        "x1": 1,
        "y0": header_bottom_y,
        "y1": 1,
        "xref": "paper",
        "yref": "paper",
        "fillcolor": tokens.HEADER_BACKGROUND,
        "line": {"width": 0},
        "layer": "below",
    }


def _pending_layout_items(figure: go.Figure) -> dict[str, list[dict[str, Any]]]:
    """그 Figure 의 누적함. 처음 열 때 이미 들어 있던 항목을 평범한 dict 로 옮겨 온다."""
    pending = getattr(figure, _PENDING_LAYOUT_ITEMS, None)
    if pending is None:
        pending = {
            "shapes": [item.to_plotly_json() for item in (figure.layout.shapes or ())],
            "annotations": [item.to_plotly_json() for item in (figure.layout.annotations or ())],
        }
        setattr(figure, _PENDING_LAYOUT_ITEMS, pending)
    return pending


def append_layout_items(
    figure: go.Figure,
    *,
    shapes: list[dict[str, Any]] | None = None,
    annotations: list[dict[str, Any]] | None = None,
) -> None:
    """레이아웃 항목을 모아만 둔다. 실제 반영은 `flush_layout_items` 가 한 번에 한다.

    부를 때마다 `update_layout` 하면 Plotly 가 **그때까지 쌓인 항목 전부를 다시 검증**한다.
    항목이 수백 개인 화면에서 그 재검증이 O(n²) 로 불어나 Figure 하나에 7 초가 들었다.
    같은 항목을 마지막에 한 번만 넣으면 0.1 초다.

    그래서 Figure 를 돌려주는 쪽이 **반드시 `flush_layout_items` 를 불러야 한다.** 잊으면
    테두리·격자·라벨이 통째로 사라져 화면에서 바로 드러난다.
    """
    pending = _pending_layout_items(figure)
    if shapes:
        pending["shapes"].extend(shapes)
    if annotations:
        pending["annotations"].extend(annotations)


def flush_layout_items(*figures: go.Figure) -> None:
    """모아 둔 항목을 Figure 마다 한 번에 반영한다. 여러 번 불러도 결과가 같다.

    반영할 때 Plotly 검증을 건너뛴다. 한 번에 넣어도 검증이 항목 수만큼 든다(합성 표본 LOB 월
    Figure 도형 156·주석 578 에서 67ms 중 61ms, 샘플 관측). 대신 항목을 **Plotly 가 검증 뒤에 남기는
    꼴**(`_plain_layout_item`)로 새 dict 에 옮겨 담는다 — 각도 -180~180, None·빈 하위 칸 빼기,
    `x1`→`x` 같은 축 이름 정리. 새로 담으므로 호출부의 dict 를 Figure 가 붙잡지 않는다(검증 없이
    넣으면 Plotly 는 받은 dict 를 그대로 둔다 — 공용 dict 를 나중에 고치면 캐시 속 그림까지 바뀐다).

    그 꼴로 옮길 수 없는 항목(모르는 속성 이름·밑줄 줄임 키·규칙을 갖추지 않은 속성 종류)이 하나라도
    있으면 그 Figure 는 `update_layout` 으로 검증해 넣는다. 오타는 예외가 된다.
    반영한 뒤에는 누적함을 버린다. 그 뒤의 `append_layout_items` 는 Figure 에 든 항목에서 다시 연다.
    """
    validate = plotly_validation_enabled()
    for figure in figures:
        pending = getattr(figure, _PENDING_LAYOUT_ITEMS, None)
        if pending is None:
            continue
        plain = None if validate else _plain_layout_items(pending)
        if plain is None:
            figure.update_layout(
                shapes=pending["shapes"],
                annotations=pending["annotations"],
            )
        else:
            layout = figure.layout
            previous = layout._validate
            layout._validate = False
            try:
                for prop, items in plain.items():
                    if items:
                        layout[prop] = items
            finally:
                layout._validate = previous
        delattr(figure, _PENDING_LAYOUT_ITEMS)


class _NotPlain(Exception):
    """검증 없이 옮길 수 없는 항목. 그 Figure 는 검증 경로로 넣는다."""


# 레이아웃 항목의 Plotly 클래스. `_valid_props`·`_path_str` 로 속성 이름과 검증기를 찾는다.
_LAYOUT_ITEM_CLASSES: dict[str, Any] = {
    "shapes": go.layout.Shape,
    "annotations": go.layout.Annotation,
}

# (클래스, 속성) → 옮기는 규칙. 검증기를 한 번만 찾아 둔다.
_PROP_RULES: dict[tuple[Any, str], tuple[str, Any]] = {}

# 글자 값이 몇 갈래뿐인 검증기(열거·색·점선·플래그·참/거짓)의 (경로, 속성, 값) → 검증한 값. 값마다
# 한 번만 Plotly 로 검증하고 그 결과를 쓴다. 잘못된 값은 여기서 예외가 되어 검증 경로로 넘어간다.
_COERCED_VALUES: dict[tuple[str, str, object], object] = {}
_COERCED_VALUES_LIMIT = 4096
_NOT_SEEN = object()

_MEMO_VALIDATORS = frozenset(
    {
        "EnumeratedValidator",
        "ColorValidator",
        "DashValidator",
        "FlaglistValidator",
        "BooleanValidator",
        "SubplotidValidator",
    }
)


def _prop_rule(owner: Any, prop: str) -> tuple[str, Any]:
    key = (owner, prop)
    rule = _PROP_RULES.get(key)
    if rule is not None:
        return rule
    if prop not in owner._valid_props:
        raise _NotPlain(prop)
    validator = ValidatorCache.get_validator(owner._path_str, prop)
    kind = type(validator).__name__
    if kind == "CompoundValidator":
        rule = ("compound", validator.data_class)
    elif kind == "AngleValidator":
        rule = ("angle", None)
    elif kind == "StringValidator" and not validator.values:
        # 정해진 값 목록이 있는 문자열 속성은 도형·주석에 없다. 생기면 아래 else 로 검증 경로다.
        rule = ("string", validator)
    elif kind == "AnyValidator":
        rule = ("any", None)
    elif kind == "NumberValidator":
        rule = ("number", validator)
    elif kind == "IntegerValidator":
        rule = ("integer", validator)
    elif kind in _MEMO_VALIDATORS:
        rule = ("memo", validator)
    else:
        raise _NotPlain(prop)
    _PROP_RULES[key] = rule
    return rule


def _plain_value(owner: Any, prop: str, value: Any) -> Any:
    kind, detail = _prop_rule(owner, prop)
    if kind == "compound":
        if not isinstance(value, Mapping):
            raise _NotPlain(prop)
        return _plain_layout_item(detail, value)
    if kind == "any":
        if isinstance(value, (str, numbers.Number)):
            return value
        raise _NotPlain(prop)
    if kind in ("number", "integer"):
        # 값은 그대로 둔다. 종류와 범위(NaN 은 범위 밖)만 Plotly 와 같게 본다.
        numeric_type = numbers.Number if kind == "number" else int
        if isinstance(value, numeric_type) and (
            not detail.has_min_max or detail.min_val <= value <= detail.max_val
        ):
            return value
        raise _NotPlain(prop)
    if kind == "angle":
        if isinstance(value, numbers.Real) and not isinstance(value, bool):
            return (cast(float, value) + 180) % 360 - 180
        raise _NotPlain(prop)
    if kind == "string":
        # Plotly 의 문자열 검증: 글자는 그대로, 숫자는 str 로(엄격하지 않을 때), 빈 글자 금지는
        # 따로 본다.
        if isinstance(value, str):
            if detail.no_blank and not value:
                raise _NotPlain(prop)
            return value
        if isinstance(value, (int, float)) and not detail.strict:
            return _plain_value(owner, prop, str(value))
        raise _NotPlain(prop)
    # memo: 글자·참거짓 값만 기억한다. 숫자는 갈래가 끝없어 기억하지 않는다.
    if not isinstance(value, (str, bool)):
        raise _NotPlain(prop)
    memo_key = (owner._path_str, prop, value)
    # 세션 스레드가 함께 쓰는 dict 다. `in` 뒤에 꺼내면 그 사이 다른 스레드가 비울 수 있어
    # 한 번에 꺼낸다.
    known = _COERCED_VALUES.get(memo_key, _NOT_SEEN)
    if known is not _NOT_SEEN:
        return known
    try:
        coerced = detail.validate_coerce(value)
    except ValueError as error:
        raise _NotPlain(prop) from error
    if len(_COERCED_VALUES) >= _COERCED_VALUES_LIMIT:
        _COERCED_VALUES.clear()
    _COERCED_VALUES[memo_key] = coerced
    return coerced


def _plain_layout_item(owner: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    """항목 하나를 Plotly 가 검증 뒤에 남기는 꼴의 **새** dict 로 옮긴다."""
    if not isinstance(item, Mapping):
        raise _NotPlain(type(item).__name__)
    plain: dict[str, Any] = {}
    for prop, value in item.items():
        if value is None:
            continue
        converted = _plain_value(owner, prop, value)
        if converted is None or (isinstance(converted, dict) and not converted):
            continue
        plain[prop] = converted
    return plain


def _plain_layout_items(
    pending: Mapping[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]] | None:
    """누적함 전부를 옮긴다. 하나라도 옮길 수 없으면 None(그 Figure 는 검증 경로)."""
    try:
        return {
            prop: [_plain_layout_item(_LAYOUT_ITEM_CLASSES[prop], item) for item in pending[prop]]
            for prop in ("shapes", "annotations")
        }
    except _NotPlain:
        return None


def add_figure_outer_border(
    figure: go.Figure,
    *,
    y0: float = 0.0,
    emphasize_left: bool = True,
    emphasize_bottom: bool = False,
) -> None:
    shapes: list[dict[str, Any]] = []
    if emphasize_left:
        shapes.append(
            {
                "type": "rect",
                "x0": 0,
                "x1": 1,
                "y0": y0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "fillcolor": TRANSPARENT_COLOR,
                "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
                "layer": "above",
            }
        )
    # 위 테두리. paper y=1 은 캔버스의 맨 윗줄이라 획의 절반이 밖으로 나가 잘린다. 좌·우·
    # 아래와 같이 두 배로 그려 보이는 굵기를 맞춘다 — 그렇지 않으면 위만 절반으로 얇다.
    shapes.append(
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": 1,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX * 2},
            "layer": "above",
        }
    )
    if emphasize_left:
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 0,
                "y0": y0,
                "y1": 1,
                "xref": "paper",
                "yref": "paper",
                "line": {
                    "color": tokens.BORDER_STRONG,
                    "width": tokens.OUTER_BORDER_WIDTH_PX * 2,
                },
                "layer": "above",
            }
        )
    shapes.append(
        {
            "type": "line",
            "x0": 1,
            "x1": 1,
            "y0": y0,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX * 2},
            "layer": "above",
        }
    )
    if emphasize_bottom:
        shapes.append(
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "y0": y0,
                "y1": y0,
                "xref": "paper",
                "yref": "paper",
                "line": {
                    "color": tokens.BORDER_STRONG,
                    "width": tokens.OUTER_BORDER_WIDTH_PX * 2,
                },
                "layer": "above",
            }
        )
    append_layout_items(figure, shapes=shapes)


def add_quarter_boundaries(
    figure: go.Figure,
    month_labels: list[str],
    *,
    y0: float = 0.0,
) -> None:
    # 월 축에는 `YY.MM` 이 아닌 칸도 섞인다(연간 Total). 분기를 셀 수 없으므로 그 칸은
    # 자기만의 칸으로 두어 양옆에 경계가 서게 한다 — 합계 칸이 분기에 묻히면 안 된다.
    quarter_keys: list[tuple[int, int] | str] = []
    for month in month_labels:
        year, _, month_number = month.partition(".")
        if month_number.isdigit() and year.isdigit():
            quarter_keys.append((int(year), (int(month_number) - 1) // 3))
        else:
            quarter_keys.append(month)
    shapes = [
        {
            "type": "line",
            "x0": month_index / len(quarter_keys),
            "x1": month_index / len(quarter_keys),
            "y0": y0,
            "y1": 1,
            "xref": "paper",
            "yref": "paper",
            "line": {"color": tokens.BORDER_STRONG, "width": tokens.OUTER_BORDER_WIDTH_PX},
            "layer": "above",
        }
        for month_index in range(1, len(quarter_keys))
        if quarter_keys[month_index] != quarter_keys[month_index - 1]
    ]
    append_layout_items(figure, shapes=shapes)


def fixed_row_domains(
    domain_bottom: float,
    domain_top: float,
    row_heights: tuple[int, ...],
) -> list[tuple[float, float]]:
    total_height = sum(row_heights)
    current_top = domain_top
    domains: list[tuple[float, float]] = []
    for row_height in row_heights:
        row_bottom = current_top - (row_height / total_height * (domain_top - domain_bottom))
        domains.append((row_bottom, current_top))
        current_top = row_bottom
    return domains


# GAP 을 함께 적을 때 값 글자를 줄이는 정도와 줄을 벌리는 거리. 행 높이는 그대로 두고
# 이 둘만 조인다. 행마다 높이가 달라지면 왼쪽 라벨 칸과 월 칸의 행이 어긋난다.
#
# 위·아래 GAP 이 함께 붙으면 한 칸이 세 줄이 된다. 그때만 값을 한 단계 더 줄이고 간격을
# 넓혀 36px 안에 들어가게 한다.


def _gap_texts(gaps: list[str] | None, count: int) -> list[str]:
    if gaps is None:
        return [""] * count
    if len(gaps) != count:
        raise ValueError("GAP 개수가 값 개수와 다릅니다.")
    return list(gaps)


def delta_color(text: str) -> str:
    """증감 문구의 색. 부호만 본다 — 좋고 나쁨이 아니라 방향이다."""
    return tokens.DELTA_DECREASE if text.strip().startswith("-") else tokens.DELTA_INCREASE


def add_fixed_table_row(
    figure: go.Figure,
    *,
    domain: tuple[float, float],
    values: list[str],
    fill_color: str | Sequence[str],
    font_size: int,
    bold: bool,
    gaps: list[str] | None = None,
    lower_gaps: list[str] | None = None,
    corner_notes: Sequence[tuple[str, str]] | None = None,
) -> None:
    """Draw a fixed-height row without Plotly Table's internal scroll layer.

    `gaps` 는 값 **위**, `lower_gaps` 는 값 **아래**에 적을 증감 문구다. 빈 문자열이면 그
    칸에는 아무것도 적지 않는다.

    `corner_notes` 는 칸 **오른쪽 끝, 값과 같은 높이**에 적을 `(글자, hover 글자)` 다(선행 입고
    실적). 글리프 가운데가 값의 글리프 가운데와 같은 높이이고 오른쪽 끝
    (`CORNER_NOTE_RIGHT_PADDING_PX`)에 붙는다. 값이 길면 값과 겹칠 수 있다(2026-10-07 사용자
    결정 — 「모두 가운데, 겹침 허용」). 값보다 뒤에 그려 겹치면 위에 선다. 값·증감·칸 경계 어느
    것도 움직이거나 줄이지 않는다. 크기는 증감과 같은 `DELTA_FONT_SIZE_PX` 로 고정이고 색은
    `ADVANCE_SHIPMENT_TEXT` 다 — 값과는 크기·자리로만 갈린다. hover 글자는 그 주석에 직접
    단다(trace 를 더하지 않는다).

    **값은 증감이 있든 없든 같은 크기로 칸 한가운데에 선다.** 증감을 끼우려고 값을 줄이거나
    밀면 토글 하나에 표 전체의 숫자가 흔들린다. 두 줄이 들어갈 자리는 행 높이가 미리 비워
    두며(`row_height_with_deltas`), 여기서는 그 자리에 놓기만 한다.
    """
    value_count = max(len(values), 1)
    upper_texts = _gap_texts(gaps, len(values))
    lower_texts = _gap_texts(lower_gaps, len(values))
    if corner_notes is not None and len(corner_notes) != len(values):
        raise ValueError("칸 오른쪽 끝 글자 개수가 값 개수와 다릅니다.")
    middle = (domain[0] + domain[1]) / 2
    # 세 글자를 **글리프 가운데** 기준으로 고르게 벌린다. 상자 기준으로 놓으면 같은 거리를
    # 주어도 위쪽 틈이 아래쪽보다 넓어 보인다.
    shift = delta_line_shift_px(font_size)
    value_shift = value_ink_yshift_px(font_size)
    delta_shift = delta_ink_yshift_px()
    annotations = []
    for value_index, (value, upper, lower) in enumerate(
        zip(values, upper_texts, lower_texts, strict=True)
    ):
        escaped_value = html.escape(value)
        position = (value_index + 0.5) / value_count
        annotations.append(
            {
                "x": position,
                "y": middle,
                "xref": "paper",
                "yref": "paper",
                "text": f"<b>{escaped_value}</b>" if bold else escaped_value,
                "showarrow": False,
                "xanchor": "center",
                "yanchor": "middle",
                "yshift": value_shift,
                "font": {
                    "color": tokens.TEXT,
                    "size": font_size,
                    "family": tokens.FONT_FAMILY,
                },
            }
        )
        for gap_text, gap_shift in (
            (upper, shift + delta_shift),
            (lower, -shift + delta_shift),
        ):
            if not gap_text:
                continue
            annotations.append(
                {
                    "x": position,
                    "y": middle,
                    "xref": "paper",
                    "yref": "paper",
                    "text": html.escape(gap_text),
                    "showarrow": False,
                    "xanchor": "center",
                    "yanchor": "middle",
                    "yshift": gap_shift,
                    "font": {
                        "color": delta_color(gap_text),
                        "size": tokens.DELTA_FONT_SIZE_PX,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
        note, note_hover = corner_notes[value_index] if corner_notes is not None else ("", "")
        if note:
            annotations.append(
                {
                    "x": (value_index + 1) / value_count,
                    "y": middle,
                    "xref": "paper",
                    "yref": "paper",
                    "text": html.escape(note),
                    "hovertext": html.escape(note_hover),
                    "showarrow": False,
                    "xanchor": "right",
                    "yanchor": "middle",
                    "xshift": -CORNER_NOTE_RIGHT_PADDING_PX,
                    # 값과 **같은 높이**다. 값의 `yshift`(`value_shift`)를 그대로 쓰지 않는다 —
                    # 그것은 값 서체·크기의 내림 보정이라, 숫자 서체 12px 에 걸면 글리프 가운데가
                    # 모형상 2.2px 위로 뜬다. 값 글리프 가운데는 `value_shift` 로 칸
                    # 한가운데(`middle`)에 서도록 잡혀 있으므로, 이 글자도 제 서체·크기의
                    # 보정(`delta_shift`)으로 같은 자리에 세운다.
                    "yshift": delta_shift,
                    "font": {
                        "color": tokens.ADVANCE_SHIPMENT_TEXT,
                        "size": tokens.DELTA_FONT_SIZE_PX,
                        "family": tokens.FONT_FAMILY_NUMERIC,
                    },
                }
            )
    # 칸마다 다른 면색을 받으면 칸 단위로 사각형을 그린다. 연간 Total 열만 살짝 어둡게
    # 하려고 행 전체를 다시 그리지 않는다.
    if isinstance(fill_color, str) or len(set(fill_color)) <= 1:
        single = fill_color if isinstance(fill_color, str) else next(iter(fill_color), "")
        fills = [{"x0": 0.0, "x1": 1.0, "color": single}]
    else:
        if len(fill_color) != len(values):
            raise ValueError("면색 개수가 값 개수와 다릅니다.")
        fills = [
            {
                "x0": index / value_count,
                "x1": (index + 1) / value_count,
                "color": color,
            }
            for index, color in enumerate(fill_color)
        ]
    append_layout_items(
        figure,
        shapes=[
            {
                "type": "rect",
                "x0": fill["x0"],
                "x1": fill["x1"],
                "y0": domain[0],
                "y1": domain[1],
                "xref": "paper",
                "yref": "paper",
                "fillcolor": fill["color"],
                "line": {"width": 0},
                "layer": "below",
            }
            for fill in fills
        ],
        annotations=annotations,
    )
