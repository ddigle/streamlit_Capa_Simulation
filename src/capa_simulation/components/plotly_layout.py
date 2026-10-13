# Purpose: Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다.

"""Plotly Figure 의 제목·테두리·분기 경계·고정 행을 그리는 공통 헬퍼를 제공한다."""

from __future__ import annotations

import html
import numbers
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, cast

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


# 앱이 만든 레이아웃 항목을 Plotly 검증 없이 넣을지 정하는 **한 스위치**. 평소에는 꺼져
# 있어(검증을 건너뛴다) 빠르고, 테스트가 `plotly_validation()` 으로 켜면 고치기 전 경로(전부 검증)를
# 그대로 탄다. 두 경로의 Figure JSON 이 같다는 것을 테스트가 늘 두 경로를 다 돌려 확인한다
# (`tests/test_plotly_fast_path.py`). 검증을 건너뛰는 길은 Plotly 의 비공개 인자 `_validate` 에
# 기댄다 — `plotly>=5.24,<7` 고정이 지키고, 인자가 사라지면 그 테스트가 먼저 깨진다.
_PLOTLY_VALIDATION: ContextVar[bool] = ContextVar("capa_plotly_validation", default=False)


@contextmanager
def plotly_validation() -> Iterator[None]:
    """이 블록 안에서는 검증을 건너뛰지 않는다. 고치기 전 경로와 견주는 테스트용 스위치다."""
    token = _PLOTLY_VALIDATION.set(True)
    try:
        yield
    finally:
        _PLOTLY_VALIDATION.reset(token)


def plotly_validation_enabled() -> bool:
    return _PLOTLY_VALIDATION.get()


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

    반영할 때 Plotly 검증을 건너뛴다. 한 번에 넣어도 검증이 항목 수만큼 들어, LOB 월 Figure
    (도형 156·주석 578)에서 67ms 중 61ms 가 검증이었다. 대신 항목을 **Plotly 가 검증 뒤에 남기는
    꼴**(`_plain_layout_item`)로 새 dict 에 옮겨 담는다 — 각도 -180~180, None·빈 하위 칸 빼기,
    `x1`→`x` 같은 축 이름 정리. 새로 담으므로 호출부의 dict 를 Figure 가 붙잡지 않는다(검증 없이
    넣으면 Plotly 는 받은 dict 를 그대로 둔다 — 공용 dict 를 나중에 고치면 캐시 속 그림까지 바뀐다).

    그 꼴로 옮길 수 없는 항목(모르는 속성 이름·밑줄 줄임 키·규칙을 갖추지 않은 속성 종류)이 하나라도
    있으면 그 Figure 는 예전처럼 `update_layout` 으로 검증해 넣는다. 오타는 지금처럼 예외가 된다.
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
    elif kind == "StringValidator":
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
        # Plotly 의 문자열 검증: 글자는 그대로, 숫자는 str 로(엄격하지 않을 때), 빈 글자 금지·
        # 정해진 값은 따로 본다.
        if isinstance(value, str):
            if (detail.no_blank and not value) or (detail.values and value not in detail.values):
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
