# Purpose: Plotly 검증을 건너뛰는 길이 검증 경로와 같은 Figure JSON 을 내는지 고정한다.

"""검증을 건너뛰는 길 == 고치기 전 경로(전부 검증).

`components/plotly_layout.py` 의 스위치(`plotly_validation()`)를 켜면 고치기 전 경로를 그대로
탄다. 여기서는 같은 입력을 두 경로로 만들어 **Figure JSON 이 한 칸도 다르지 않은지** 본다. 비교는
`json.loads(plotly.io.to_json(fig, validate=False))` — `st.plotly_chart` 가 브라우저로 보내는 것과
같은 dict 다(칸 차례만 다를 수 있고, dict 비교는 차례를 보지 않는다).

검증을 건너뛰는 길은 Plotly 의 비공개 인자 `_validate` 에 기댄다(`plotly>=5.24,<7`). 인자가
사라지면 여기서 먼저 깨진다.
"""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import pytest
from plotly.validator_cache import ValidatorCache
from streamlit.testing.v1 import AppTest
from test_home_figure_cache_equivalence import PRESETS, _prepare_database

from capa_simulation.components import (
    grouped_monthly_table,
    hierarchical_monthly_table,
    plotly_layout,
)
from capa_simulation.components.availability_gap_figure import build_availability_gap_figure
from capa_simulation.components.monthly_table_base import (
    COLUMN_LABELS,
    HEADER_HEIGHT_PX,
    MONTH_COLUMN_WIDTH_PX,
    ROW_HEIGHT_PX,
    build_split_table_figures,
    header_label,
    table_height_px,
)
from capa_simulation.components.plotly_layout import (
    add_figure_outer_border,
    add_fixed_table_row,
    add_quarter_boundaries,
    append_layout_items,
    figure_from_spec,
    flush_layout_items,
    plotly_validation,
    plotly_validation_enabled,
)
from capa_simulation.design import theme, tokens
from capa_simulation.home_state import (
    ADVANCE_SHIPMENT_TOGGLE_KEY,
    ADVANCE_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    PAST_DATA_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
    PRODUCT_SHARE_BASIS_KEY,
)
from capa_simulation.services.availability_gap import DYNAMIC_SUBTOTAL_ROW, GAP_ROW, STATIC_ROW
from capa_simulation.services.monthly_equipment_availability import BASELINE_CATEGORY

HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"
PRESET_KEY = "home_key_process_preset"
THEME_KEY = "spy_theme"
VALIDATE_KEY = "spy_validate"
RANGE_KEY = "production_month_range_v2"
FULL_RANGE = ("2025-11", "2026-12")


def _as_json(figure: go.Figure) -> Any:
    return json.loads(pio.to_json(figure, validate=False))


def _flushed(shapes: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> go.Figure:
    figure = go.Figure()
    append_layout_items(figure, shapes=shapes, annotations=annotations)
    flush_layout_items(figure)
    return figure


def _both(shapes: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> tuple[Any, Any]:
    with plotly_validation():
        checked = _as_json(_flushed(shapes, annotations))
    return checked, _as_json(_flushed(shapes, annotations))


def test_the_switch_is_off_by_default_and_scoped() -> None:
    assert not plotly_validation_enabled()
    with plotly_validation():
        assert plotly_validation_enabled()
    assert not plotly_validation_enabled()


def test_flushed_items_match_what_plotly_validation_leaves() -> None:
    """검증이 바꾸는 것들: 각도(270 → -90), None 칸 빼기, 빈 하위 칸 빼기, 숫자 글자를 str 로,
    축 이름 `x1` → `x`. numpy 수는 그대로 둔다. 모두 검증 경로와 JSON 이 같아야 한다."""
    shapes: list[dict[str, Any]] = [
        {
            "type": "line",
            "x0": 0,
            "x1": 1,
            "y0": np.float64(0.5),
            "y1": 0.5,
            "xref": "x1",
            "yref": "paper",
            "line": {"color": "#123456", "width": 1.5, "dash": "dot"},
            "layer": "above",
        },
        {"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1, "line": {}, "fillcolor": "red"},
        {"type": "rect", "line": {"width": None}, "label": {"text": "a", "textangle": 270}},
        {},
    ]
    annotations: list[dict[str, Any]] = [
        {"text": "a", "hovertext": None, "textangle": 270, "font": {}, "x": np.int64(3)},
        {"text": 5, "textangle": -270, "font": {"size": 12, "color": "red", "family": "Arial"}},
        {"text": "b", "textangle": 180, "showarrow": False, "xanchor": "center", "yshift": -3.5},
        {"text": "c", "textangle": 90.5, "visible": True, "yref": "y2"},
    ]

    checked, fast = _both(shapes, annotations)

    assert fast == checked
    assert fast["layout"]["annotations"][0]["textangle"] == -90
    assert "hovertext" not in fast["layout"]["annotations"][0]
    assert fast["layout"]["shapes"][0]["xref"] == "x"


def test_empty_accumulators_leave_no_empty_lists() -> None:
    checked, fast = _both([], [])

    assert fast == checked
    assert "shapes" not in fast["layout"]
    assert "annotations" not in fast["layout"]


def test_the_figure_does_not_hold_the_callers_dicts() -> None:
    """검증 없이 넣으면 Plotly 는 받은 dict 를 그대로 둔다. 공용 dict 를 나중에 고치면 이미 만든
    그림(나아가 캐시 속 그림)까지 바뀐다. 반영할 때 새 dict 로 옮겨 담아야 한다."""
    shared_line = {"color": "#000000", "width": 1}
    figure = _flushed(
        [{"type": "line", "x0": 0, "x1": 1, "y0": 0, "y1": 0, "line": shared_line}], []
    )

    shared_line["color"] = "#FFFFFF"

    assert figure.layout.shapes[0].line.color == "#000000"


def test_a_misspelled_property_still_raises() -> None:
    """오타가 조용히 통과하면 테두리·라벨이 말없이 사라진 채 캐시에 남는다. 지금처럼 예외다."""
    with pytest.raises(ValueError):
        _flushed([{"type": "line", "fil_color": "red"}], [])
    with pytest.raises(ValueError):
        _flushed([], [{"text": "a", "xanchor": "middle"}])


def test_values_plotly_would_reject_still_raise() -> None:
    """범위를 벗어난 숫자(NaN 굵기)와 모르는 색도 검증 경로로 넘어가 지금처럼 예외가 된다."""
    with pytest.raises(ValueError):
        _flushed([{"type": "line", "line": {"width": math.nan}}], [])
    with pytest.raises(ValueError):
        _flushed([{"type": "rect", "fillcolor": "not-a-color"}], [])


def test_underscore_shorthand_falls_back_to_validation() -> None:
    """밑줄 줄임 키는 검증 경로만 펼친다. 그런 항목이 있으면 그 Figure 는 검증 경로로 넣는다."""
    checked, fast = _both([], [{"text": "a", "font_color": "red"}])

    assert fast == checked
    assert fast["layout"]["annotations"] == [{"text": "a", "font": {"color": "red"}}]


def test_append_after_a_flush_keeps_every_item() -> None:
    """반영한 뒤 누적함을 버린다. 다시 모을 때는 Figure 에 든 항목에서 연다."""
    figure = go.Figure()
    append_layout_items(figure, shapes=[{"type": "line", "x0": 0, "x1": 1}])
    flush_layout_items(figure)
    append_layout_items(figure, shapes=[{"type": "line", "x0": 2, "x1": 3}])
    flush_layout_items(figure)
    flush_layout_items(figure)

    assert [shape.x0 for shape in figure.layout.shapes] == [0, 2]


def test_the_fast_flush_really_skips_plotly_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """빠른 길이 정말 검증을 건너뛰는지. 검증은 항목마다 `layout.Shape`·`layout.Annotation` 객체를
    세운다. Plotly 가 `_validate` 를 끄는 뜻을 바꾸면 JSON 은 그대로라 다른 시험이 못 잡는다 — 그때
    여기서 깨진다."""
    shapes = [{"type": "line", "x0": 0, "x1": 1, "line": {"color": "#000000", "width": 1}}]
    annotations = [{"text": "a", "showarrow": False, "font": {"size": 12}}]
    _flushed(shapes, annotations)  # 규칙·값 기억을 데운다(첫 회에는 검증기를 찾는다).
    built: list[str] = []
    for cls in (go.layout.Shape, go.layout.Annotation):
        original_init = cls.__init__

        def counting_init(
            self: Any, *args: Any, _original: Any = original_init, **kwargs: Any
        ) -> None:
            built.append(type(self).__name__)
            _original(self, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", counting_init)

    figure = go.Figure()
    append_layout_items(figure, shapes=shapes * 50, annotations=annotations * 50)
    flush_layout_items(figure)
    assert built == []

    with plotly_validation():
        _flushed(shapes, annotations)
    assert built  # 검증 경로는 항목 객체를 세운다 — 위 단언이 헛돌지 않는다는 증거.


def test_shared_helpers_match_the_validated_path() -> None:
    """HOME 표 행·테두리·분기 경계 도우미를 두 경로로 그린다."""

    def draw() -> Any:
        figure = go.Figure()
        add_figure_outer_border(figure, y0=0.1, emphasize_bottom=True)
        add_quarter_boundaries(figure, ["26.01", "26.02", "26.03", "26.04", "Total"], y0=0.2)
        add_fixed_table_row(
            figure,
            domain=(0.2, 0.5),
            values=["1,234", "-", "<5>"],
            fill_color=["#FFFFFF", "#EEEEEE", "#FFFFFF"],
            font_size=13,
            bold=True,
            gaps=["+1", "", "-2"],
            lower_gaps=["", "-3", ""],
            corner_notes=[("+1.2", "선행 입고 1.2"), ("", ""), ("-0.5", "선행 입고 -0.5")],
        )
        flush_layout_items(figure)
        return _as_json(figure)

    with plotly_validation():
        checked = draw()
    assert draw() == checked


def _gap_matrix(month_count: int) -> pd.DataFrame:
    months = [str(202601 + index) for index in range(month_count)]
    available = [0.0 if index == 1 else 1.0 for index in range(month_count)]
    return pd.DataFrame(
        [
            [3.0] * month_count,
            available,
            [3.0 + value for value in available],
            [4.0] * month_count,
            [value - 1.0 for value in available],
        ],
        index=[BASELINE_CATEGORY.name, "가용", DYNAMIC_SUBTOTAL_ROW, STATIC_ROW, GAP_ROW],
        columns=months,
    )


@pytest.mark.parametrize("month_count", [1, 4, 12])
def test_the_availability_gap_figure_matches_the_validated_path(month_count: int) -> None:
    matrix = _gap_matrix(month_count)
    with plotly_validation():
        checked = _as_json(build_availability_gap_figure(matrix))
    assert _as_json(build_availability_gap_figure(matrix)) == checked


# ---------------------------------------------------------------- HOME 네 묶음 + 덤벨


def _home_script(database_path: Path) -> str:
    """HOME 을 한 번 돌려 그린 Figure 를 JSON 으로 모은다. Figure 캐시는 꺼서 늘 새로 만든다.

    `spy_validate` 가 켜져 있으면 스위치를 켠 채(고치기 전 경로) 돌린다.
    """
    return f"""
from contextlib import nullcontext
from pathlib import Path

import streamlit as st

import capa_simulation.components.home_rendering as home_rendering
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings
from capa_simulation.components.plotly_layout import plotly_validation
from capa_simulation.design import theme

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

theme._LOCAL.mode = st.session_state.get({THEME_KEY!r}, "light")
st.session_state["spy_figures"] = {{}}
_original_chart = st.plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
_original_take = home_rendering.take_home_figures
_original_store = home_rendering.store_home_figures


def _spy_chart(figure, *args, **kwargs):
    st.session_state["spy_figures"] = {{
        **st.session_state["spy_figures"],
        kwargs.get("key"): figure.to_json(),
    }}
    return _original_chart(figure, *args, **kwargs)


st.plotly_chart = _spy_chart
horizontal_scrollbar.render_horizontal_scrollbar = lambda *_args, **_kwargs: None
home_rendering.take_home_figures = lambda *_args, **_kwargs: None
home_rendering.store_home_figures = lambda *_args, **_kwargs: None
switch = plotly_validation() if st.session_state.get({VALIDATE_KEY!r}) else nullcontext()
try:
    page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
    with switch:
        exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    st.plotly_chart = _original_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
    home_rendering.take_home_figures = _original_take
    home_rendering.store_home_figures = _original_store
    theme._LOCAL.mode = None
"""


@pytest.fixture(scope="module")
def home_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("plotly_fast_path") / "scenario.duckdb"
    _prepare_database(path)
    return path


def _drawn(app: AppTest, *, validate: bool) -> dict[str, Any]:
    app.session_state[VALIDATE_KEY] = validate
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]
    return {key: json.loads(spec) for key, spec in app.session_state["spy_figures"].items()}


# 대표 토글 조합. 레이아웃 항목이 달라지는 조건을 고루 지난다 — GAP(증감 글자)·선행 B/O·선행 입고
# (칸 오른쪽 끝 글자·hover)·실행 Loss·과거 구간·고객 상세·EDP·제품별 비중 단위·빈 주요공정 안내·
# 어두운 테마.
COMBINATIONS: dict[str, dict[str, Any]] = {
    "기본": {},
    "선행·실행·과거 끔": {
        ADVANCE_TOGGLE_KEY: True,
        EXECUTION_TOGGLE_KEY: True,
        PAST_DATA_TOGGLE_KEY: False,
    },
    "GAP·고객 상세·선행 입고": {
        COMPARISON_TOGGLE_KEY: True,
        PLAN_DETAIL_CUSTOMER_KEY: True,
        ADVANCE_SHIPMENT_TOGGLE_KEY: True,
    },
    "빈 주요공정·PKG 비중·EDP": {
        PRESET_KEY: PRESETS[2],
        PRODUCT_SHARE_BASIS_KEY: "PKG",
        EDP_TOGGLE_KEY: True,
    },
    "모두 켬·어두운 테마": {
        ADVANCE_TOGGLE_KEY: True,
        ADVANCE_SHIPMENT_TOGGLE_KEY: True,
        EXECUTION_TOGGLE_KEY: True,
        COMPARISON_TOGGLE_KEY: True,
        PLAN_DETAIL_CUSTOMER_KEY: True,
        EDP_TOGGLE_KEY: True,
        PAST_DATA_TOGGLE_KEY: True,
        THEME_KEY: "dark",
    },
}


@pytest.mark.parametrize("label", list(COMBINATIONS))
def test_home_figures_match_the_validated_path(
    home_database: Path, label: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOME 네 묶음(LOB·계획 세부수량·주요공정·상세 B/N)과 덤벨을 두 경로로 그려 JSON 을 견준다.

    빠른 길이 실제로 쓰였는지도 본다. 옮길 수 없는 항목이 생겨 검증 경로로 넘어가면 값은 맞아도
    느려진다 — 그런 일이 HOME 에서 생기면 여기서 드러난다.
    """
    fallbacks: list[int] = []
    original = plotly_layout._plain_layout_items

    def spy(pending: Any) -> Any:
        plain = original(pending)
        if plain is None:
            fallbacks.append(1)
        return plain

    monkeypatch.setattr(plotly_layout, "_plain_layout_items", spy)
    app = AppTest.from_string(_home_script(home_database), default_timeout=300)
    app.session_state[THEME_KEY] = "light"
    app.run()
    app.session_state[RANGE_KEY] = FULL_RANGE
    for key, value in COMBINATIONS[label].items():
        app.session_state[key] = value

    checked = _drawn(app, validate=True)
    fallbacks.clear()
    fast = _drawn(app, validate=False)

    assert not fallbacks, f"{label}: 검증 경로로 넘어간 Figure 가 {len(fallbacks)}개"

    # 여덟 Figure(+ GAP 이면 덤벨)가 다 그려졌는지 — 빈 화면끼리 같다고 통과하지 않게.
    assert len(checked) >= 8, sorted(checked)
    assert set(fast) == set(checked)
    different = sorted(key for key in checked if fast[key] != checked[key])
    assert not different, f"{label}: 검증을 건너뛴 그림이 검증한 그림과 다르다 — {different}"
    # 레이아웃 항목이 실제로 있는 그림이어야 이 비교가 무엇을 본다.
    assert any(spec["layout"].get("annotations") for spec in fast.values())
    assert any(spec["layout"].get("shapes") for spec in fast.values())


# ---------------------------------------------------------------- 월별 표 두 종류


def _legacy_split_table_figures(
    *,
    classification_headers: list[str],
    classification_values: list[list[str]],
    classification_fill_colors: list[list[str]],
    column_widths: list[int],
    month_headers: list[str],
    month_values: list[list[str]],
    month_row_colors: list[str],
    row_count: int,
) -> tuple[go.Figure, go.Figure]:
    """고치기 전 `build_split_table_figures` 그대로(줄임 키 + 검증 생성자 + `update_layout`)."""
    common_layout: dict[str, Any] = {
        "height": table_height_px(row_count),
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        "paper_bgcolor": tokens.CHART_CANVAS,
        "font": {"color": tokens.TEXT, "family": tokens.FONT_FAMILY},
    }
    header_style: dict[str, Any] = {
        "align": "center",
        "fill_color": tokens.HEADER_BACKGROUND,
        "line_color": tokens.TRANSPARENT,
        "font": {"color": tokens.TEXT, "size": 14, "family": tokens.FONT_FAMILY},
        "height": HEADER_HEIGHT_PX,
    }
    cell_font: dict[str, Any] = {"color": tokens.TEXT, "size": 13, "family": tokens.FONT_FAMILY}
    label_figure = go.Figure(
        go.Table(
            columnwidth=column_widths,
            header={"values": classification_headers, **header_style},
            cells={
                "values": classification_values,
                "align": "center",
                "fill_color": classification_fill_colors,
                "line_color": tokens.TRANSPARENT,
                "font": cell_font,
                "height": ROW_HEIGHT_PX,
            },
        )
    )
    month_figure = go.Figure(
        go.Table(
            columnwidth=[1.0] * len(month_headers),
            header={"values": month_headers, **header_style},
            cells={
                "values": month_values,
                "align": "center",
                "fill_color": [month_row_colors for _ in month_headers],
                "line_color": tokens.TRANSPARENT,
                "font": cell_font,
                "height": ROW_HEIGHT_PX,
            },
        )
    )
    label_figure.update_layout(**common_layout)
    month_figure.update_layout(
        **common_layout,
        width=len(month_headers) * MONTH_COLUMN_WIDTH_PX,
        autosize=False,
    )
    return label_figure, month_figure


def _split_table_input(rows: int, months: int) -> dict[str, Any]:
    return {
        "classification_headers": [header_label("공정"), header_label("WF 구분")],
        "classification_values": [
            [f"P{index // 3}" if index % 3 == 0 else "" for index in range(rows)],
            [f"W {index}" for index in range(rows)],
        ],
        "classification_fill_colors": [
            [tokens.SURFACE_CLASSIFICATION if index % 2 else "#EEF2F6" for index in range(rows)]
        ]
        * 2,
        "column_widths": [120, 90],
        "month_headers": [header_label(f"26.{index + 1:02d}") for index in range(months)],
        "month_values": [
            ["" if (row + month) % 5 == 0 else f"{row * 1.5 + month:,.1f}" for row in range(rows)]
            for month in range(months)
        ],
        "month_row_colors": [
            tokens.SURFACE if row % 2 else tokens.SURFACE_SUBTLE for row in range(rows)
        ],
        "row_count": rows,
    }


SPLIT_TABLE_INPUTS = {
    "작은 표": _split_table_input(4, 3),
    "표준 목표 Weeknum": _split_table_input(70, 131),
    "빈 표": _split_table_input(0, 2),
}


@pytest.mark.parametrize("label", list(SPLIT_TABLE_INPUTS))
@pytest.mark.parametrize("theme_mode", ["light", "dark"])
def test_split_table_figures_match_the_old_validated_builder(label: str, theme_mode: str) -> None:
    """spec 으로 세운 표 한 쌍 == 고치기 전 `go.Table(fill_color=...)` + `update_layout` 경로.

    spec 에 밑줄 줄임 키가 남으면 검증 없이는 펼쳐지지 않아 헤더 배경이 사라진다 — 여기서 걸린다.
    """
    theme._LOCAL.mode = theme_mode
    try:
        kwargs = SPLIT_TABLE_INPUTS[label]
        legacy = [_as_json(figure) for figure in _legacy_split_table_figures(**kwargs)]
        fast = [_as_json(figure) for figure in build_split_table_figures(**kwargs)]
        with plotly_validation():
            checked = [_as_json(figure) for figure in build_split_table_figures(**kwargs)]
    finally:
        theme._LOCAL.mode = None

    assert fast == legacy
    assert checked == legacy
    header_fill = legacy[0]["data"][0]["header"]["fill"]
    assert fast[0]["data"][0]["header"]["fill"] == header_fill == {"color": header_fill["color"]}


def _hierarchical_frame(rows: int, months: list[str], *, percent: bool = False) -> pd.DataFrame:
    data: dict[str, list[Any]] = {
        "공정": [f"P&<{index // 40}>" for index in range(rows)],
        "제품정보": [f"DEMO {index // 7}" for index in range(rows)],
        "WF 구분": ["Core" if index % 2 else "Top" for index in range(rows)],
    }
    for position, month in enumerate(months):
        scale = 100 if percent else 0.3
        data[month] = [
            None if (row + position) % 11 == 0 else ((row * 7 + position) % 97) / scale
            for row in range(rows)
        ]
    return pd.DataFrame(data)


def _months(count: int) -> list[str]:
    return [str(202501 + (index // 12) * 100 + index % 12) for index in range(count)]


def _weeks(count: int) -> list[str]:
    return [f"W{index:03d}" for index in range(count)]


def _drawn_tables(render: Any, **kwargs: Any) -> list[Any]:
    """렌더 함수가 `render_split_scroll_table` 에 넘기는 두 Figure 를 JSON 으로 모은다."""
    drawn: list[Any] = []

    def capture(**captured: Any) -> None:
        drawn.extend(_as_json(captured[name]) for name in ("label_figure", "month_figure"))

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(hierarchical_monthly_table, "render_split_scroll_table", capture)
        patcher.setattr(grouped_monthly_table, "render_split_scroll_table", capture)
        render(**kwargs)
    return drawn


_WEEKS = _weeks(131)

TABLE_CASES: dict[str, tuple[Any, dict[str, Any]]] = {
    "계층 표 · 표준 목표 Weeknum": (
        hierarchical_monthly_table.render_hierarchical_monthly_table,
        {
            "data": _hierarchical_frame(70, _WEEKS)[["공정", "제품정보", *_WEEKS]],
            "classification_columns": ["공정", "제품정보"],
            "column_labels": COLUMN_LABELS,
            "decimal_places": 1,
            "key": "fast_path_weeks",
        },
    ),
    "계층 표 · WF 속성 2,660행": (
        hierarchical_monthly_table.render_hierarchical_monthly_table,
        {
            "data": _hierarchical_frame(2660, _months(30)),
            "classification_columns": ["공정", "제품정보", "WF 구분"],
            "column_labels": COLUMN_LABELS,
            "decimal_places": 2,
            "key": "fast_path_wf",
            "value_labels": {"공정": {"P&<0>": "공정 & 영(0)"}},
        },
    ),
    "계층 표 · 퍼센트": (
        hierarchical_monthly_table.render_hierarchical_monthly_table,
        {
            "data": _hierarchical_frame(30, _months(14), percent=True),
            "classification_columns": ["공정", "제품정보", "WF 구분"],
            "column_labels": COLUMN_LABELS,
            "decimal_places": 1,
            "key": "fast_path_percent",
            "value_format": "percent",
        },
    ),
    "계층 표 · 한 행": (
        hierarchical_monthly_table.render_hierarchical_monthly_table,
        {
            "data": _hierarchical_frame(1, _months(2)),
            "classification_columns": ["공정", "제품정보", "WF 구분"],
            "column_labels": COLUMN_LABELS,
            "decimal_places": 0,
            "key": "fast_path_one",
        },
    ),
    "그룹 표 · 부분합": (
        grouped_monthly_table.render_grouped_monthly_table,
        {
            "data": pd.DataFrame(
                {
                    "양산구분": ["양산"] * 6 + ["ER"] * 3,
                    "제품정보": ["A", "A", "B", "B", "B", "C", "D", "D", "E"],
                    "Stack": ["8H", "12H", "8H", "12H", "16H", "8H", "8H", "12H", "8H"],
                    **{
                        month: [float((row + index) % 4) * 12.5 for row in range(9)]
                        for index, month in enumerate(_months(15))
                    },
                }
            ),
            "classification_columns": ["양산구분", "제품정보", "Stack"],
            "column_labels": COLUMN_LABELS,
            "decimal_places": 0,
            "key": "fast_path_grouped",
        },
    ),
}


@pytest.mark.parametrize("label", list(TABLE_CASES))
def test_monthly_tables_match_the_validated_path(label: str) -> None:
    """표 렌더 함수 전체(spec Figure + 격자 flush)를 두 경로로 돌려 두 Figure 의 JSON 을 견준다."""
    render, kwargs = TABLE_CASES[label]
    with plotly_validation():
        checked = _drawn_tables(render, **kwargs)
    fast = _drawn_tables(render, **kwargs)

    assert len(checked) == 2
    assert fast == checked
    assert fast[1]["layout"]["shapes"], "격자선이 그려진 표여야 비교가 무엇을 본다"


def test_a_spec_typo_or_shorthand_falls_back_to_the_validating_constructor() -> None:
    """spec 키 이름이 Plotly 속성이 아니면 검증 생성자로 세운다. 오타는 예외, 줄임 키는 펼친다."""
    with pytest.raises(ValueError):
        figure_from_spec({"data": [{"type": "table", "header": {"fil": {"color": "#FFFFFF"}}}]})
    with pytest.raises(ValueError):
        figure_from_spec({"data": [], "layout": {"heigth": 10}})

    shorthand = figure_from_spec(
        {"data": [{"type": "table", "header": {"values": ["a"], "fill_color": "#FFFFFF"}}]}
    )
    assert _as_json(shorthand)["data"][0]["header"]["fill"] == {"color": "#FFFFFF"}


def test_a_spec_figure_validates_later_edits_and_holds_no_caller_dicts() -> None:
    """세운 뒤에는 검증이 다시 켜진다. `go.Figure` 가 spec 을 깊은 복사하므로 호출부 dict 를
    고쳐도 그림은 그대로다."""
    header: dict[str, Any] = {"values": ["a"], "fill": {"color": "#FFFFFF"}}
    figure = figure_from_spec({"data": [{"type": "table", "header": header}], "layout": {}})
    header["fill"]["color"] = "#000000"

    assert figure.data[0].header.fill.color == "#FFFFFF"
    with pytest.raises(ValueError):
        figure.update_layout(heigth=10)
    with pytest.raises(ValueError):
        figure.data[0].update(header={"fil": {}})


def test_the_spec_path_really_skips_cell_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """빠른 길이 정말 셀 값 검증을 건너뛰는지. 검증 경로는 `cells.values` 검증기를 부른다."""
    validator = ValidatorCache.get_validator("table.cells", "values")
    calls: list[int] = []
    original = validator.validate_coerce

    def counting(value: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(validator, "validate_coerce", counting)
    kwargs = SPLIT_TABLE_INPUTS["작은 표"]

    build_split_table_figures(**kwargs)
    assert calls == []

    with plotly_validation():
        build_split_table_figures(**kwargs)
    assert calls  # 검증 경로는 부른다 — 위 단언이 헛돌지 않는다는 증거.
