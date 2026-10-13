# Purpose: 재공 격자 Figure 세션 메모가 같은 입력엔 같은 그림, 바뀐 입력엔 새 그림을 주는지 본다.

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import pytest

from capa_simulation.components import wip_status_dashboard as dashboard
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import theme
from capa_simulation.services.wip_status import build_wip_history_demo

START = date(2026, 9, 1)
END = date(2026, 9, 4)
PRODUCTS = ["Product-B", "Product-A"]


def _routes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["T-Process", "P-Process", "T-Process", "P-Process"],
            "STEP_SEQ": ["T100", "P100", "T100", "P100"],
            "제품정보": ["Product-B", "Product-B", "Product-A", "Product-A"],
            "소요기준": ["WF", "CHIP", "WF", "CHIP"],
        }
    )


def _history(routes: pd.DataFrame, *, today: date = date(2026, 9, 2)) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "일자": current,
            "공정": process,
            "소요기준": basis,
            "제품정보": product,
            "일 표준 가능량": 100.0,
        }
        for current in pd.date_range(START, END, freq="D")
        for process, basis in (("P-Process", "CHIP"), ("T-Process", "WF"))
        for product in ("Product-A", "Product-B")
    ]
    return build_wip_history_demo(routes, pd.DataFrame(rows), START, END, today=today)


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """메모가 쓰는 세션 칸을 평범한 사전으로 바꾼다."""
    state: dict[str, Any] = {}
    monkeypatch.setattr(dashboard, "st", SimpleNamespace(session_state=state))
    return state


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """실제 격자 생성 횟수를 센다."""
    calls: list[int] = []
    original = dashboard.build_wip_status_grid_figure

    def counting(*args: Any, **kwargs: Any) -> go.Figure:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(dashboard, "build_wip_status_grid_figure", counting)
    return calls


def _inputs() -> dict[str, Any]:
    routes = _routes()
    return {
        "data": _history(routes),
        "routes": routes,
        "products": list(PRODUCTS),
        "start_date": START,
        "end_date": END,
        "process_labels": ProcessLabels(labels={"P-Process": "P 공정"}),
    }


def _fresh(inputs: dict[str, Any]) -> str:
    """메모를 거치지 않고 새로 만든 Figure 의 JSON."""
    figure: go.Figure = dashboard.build_wip_status_grid_figure(**inputs)
    return str(figure.to_json())


def test_the_same_inputs_reuse_the_figure_with_the_same_json(
    session: dict[str, Any], builds: list[int]
) -> None:
    inputs = _inputs()
    first = dashboard.remembered_wip_status_grid_figure(**inputs)
    expected = _fresh(_inputs())
    builds.clear()

    # 내용이 같은 새 표(사본)라도 다시 쓴다 — 페이지는 회차마다 새 표를 만든다.
    again = dashboard.remembered_wip_status_grid_figure(**_inputs())

    assert again is first
    assert builds == []
    assert again.to_json() == expected


def _with(**changes: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def apply(inputs: dict[str, Any]) -> dict[str, Any]:
        return {**inputs, **changes}

    return apply


def _cell(column: str, value: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def apply(inputs: dict[str, Any]) -> dict[str, Any]:
        data = inputs["data"].copy()
        data.loc[data.index[0], column] = value
        return {**inputs, "data": data}

    return apply


def _drop_route(inputs: dict[str, Any]) -> dict[str, Any]:
    routes = inputs["routes"].iloc[:-1].reset_index(drop=True)
    return {**inputs, "routes": routes}


def _new_today(inputs: dict[str, Any]) -> dict[str, Any]:
    # 날짜가 바뀐 첫 회차 — 실적/전망 구분(시점)이 재공 표 내용으로 들어온다.
    return {**inputs, "data": _history(inputs["routes"], today=date(2026, 9, 3))}


CHANGES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "flow-cell": _cell("Flow량", 9999.0),
    "standard-cell": _cell("일 표준 가능량", 1.5),
    "today": _new_today,
    "dtype-only": lambda inputs: {**inputs, "data": inputs["data"].astype({"Flow량": "object"})},
    "routes": _drop_route,
    "product-order": _with(products=list(reversed(PRODUCTS))),
    "end-date": _with(end_date=date(2026, 9, 5)),
    "process-label": _with(process_labels=ProcessLabels(labels={"P-Process": "새 이름"})),
    "no-labels": _with(process_labels=None),
}


@pytest.mark.parametrize("name", list(CHANGES))
def test_any_input_change_rebuilds_the_figure(
    session: dict[str, Any], builds: list[int], name: str
) -> None:
    dashboard.remembered_wip_status_grid_figure(**_inputs())
    changed = CHANGES[name](_inputs())
    builds.clear()

    figure = dashboard.remembered_wip_status_grid_figure(**changed)

    assert builds == [1]
    assert figure.to_json() == _fresh(changed)


def test_a_theme_change_rebuilds_the_figure_with_the_other_palette(
    session: dict[str, Any], builds: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(theme, "current_mode", lambda: "light")
    light = dashboard.remembered_wip_status_grid_figure(**_inputs())
    monkeypatch.setattr(theme, "current_mode", lambda: "dark")
    builds.clear()

    dark = dashboard.remembered_wip_status_grid_figure(**_inputs())

    assert builds == [1]
    assert dark.to_json() != light.to_json()
    assert dark.to_json() == _fresh(_inputs())


def test_a_failed_build_is_not_remembered(session: dict[str, Any], builds: list[int]) -> None:
    dashboard.remembered_wip_status_grid_figure(**_inputs())
    remembered = session[dashboard.WIP_GRID_FIGURE_MEMO_KEY]

    with pytest.raises(ValueError, match="제품을 선택"):
        dashboard.remembered_wip_status_grid_figure(**{**_inputs(), "products": []})

    assert session[dashboard.WIP_GRID_FIGURE_MEMO_KEY] is remembered
