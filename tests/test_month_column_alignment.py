# Purpose: 월 컬럼 Figure 의 컬럼 수와 폭이 항상 같은 근거에서 나오는지 고정한다.

import pandas as pd
import plotly.graph_objects as go

from capa_simulation.components.home_figures import build_plan_detail_figures
from capa_simulation.design import tokens

# 사용자 보고: 월 컬럼 헤더(년월)가 input 데이터가 바뀔 때 가끔 셀 가운데가 아니라
# 구석으로 밀린다. 원인은 컬럼 수와 Figure 폭을 서로 다른 목록에서 계산한 것이었다.
# 세부 데이터에 없는 달을 컬럼에서 빼면서 폭은 조회 범위 전체로 잡아, 컬럼 폭이
# 100px 그리드보다 넓어지고 뒤로 갈수록 헤더가 밀렸다.

MONTH_LABELS = ["26.01", "26.02", "26.03", "26.04", "26.05", "26.06"]


def _detail(months: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "제품정보": ["DEMO_A", "DEMO_B"],
            "Stack": ["8H", "12H"],
            **{month: [100.0, 200.0] for month in months},
        }
    )


def _month_table(figure: go.Figure) -> go.Table:
    tables = [trace for trace in figure.data if trace.type == "table"]
    assert tables, "표 trace 가 없습니다."
    return tables[0]


def _assert_grid_is_consistent(figure: go.Figure) -> None:
    """컬럼 수 × 월 컬럼 폭 == Figure 폭 이어야 헤더가 셀 가운데에 온다."""
    table = _month_table(figure)
    column_count = len(table.columnwidth)
    assert figure.layout.width == column_count * tokens.MONTH_COLUMN_WIDTH_PX, (
        f"컬럼 {column_count}개인데 폭이 {figure.layout.width}px 입니다. "
        f"{column_count * tokens.MONTH_COLUMN_WIDTH_PX}px 여야 헤더가 어긋나지 않습니다."
    )
    assert len(table.header.values) == column_count
    assert len(table.cells.values) == column_count


def test_detail_grid_is_consistent_when_every_month_has_data() -> None:
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(MONTH_LABELS), month_labels=MONTH_LABELS
    )

    _assert_grid_is_consistent(month_figure)


def test_detail_grid_is_consistent_when_some_months_have_no_data() -> None:
    """사용자가 겪은 상황이다. 계획이 없는 달이 있으면 예전에는 컬럼이 사라졌다."""
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(["26.01", "26.03", "26.06"]), month_labels=MONTH_LABELS
    )

    _assert_grid_is_consistent(month_figure)


def test_missing_months_stay_as_empty_columns() -> None:
    """컬럼을 지우지 않고 빈 칸으로 둬야 요약표와 월이 세로로 맞는다."""
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(["26.01", "26.03"]), month_labels=MONTH_LABELS
    )

    table = _month_table(month_figure)
    assert [str(value) for value in table.header.values] == [
        f"<b>{month}</b>" for month in MONTH_LABELS
    ]
    # 데이터가 없는 26.02 는 두 번째 컬럼이고 전부 빈 칸이어야 한다.
    assert list(table.cells.values[1]) == ["", ""]
    assert list(table.cells.values[0]) == ["100K", "200K"]


def test_headers_are_centered() -> None:
    """정렬 설정 자체도 함께 고정한다."""
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(MONTH_LABELS), month_labels=MONTH_LABELS
    )

    table = _month_table(month_figure)
    assert table.header.align == ("center",) or table.header.align == "center"
    assert table.cells.align == ("center",) or table.cells.align == "center"
