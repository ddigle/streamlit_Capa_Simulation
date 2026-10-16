# Purpose: AppTest 가 그린 비교 시트 그림에서 칸 글자·풍선·범위 지문을 읽는 시험 도우미다.

"""비교 시트 읽기(시험 도우미).

시트는 Plotly 그림이라 `app.dataframe` 으로 읽을 수 없다. 월 Figure 의 표적 막대(trace 0)는 칸마다
`customdata = (YYYYMM, 행 id, 풍선)` 이고, 글자 trace 는 칸 가운데(`x = 열 + 0.5`, 같은 `y`)에 선다
— 둘을 자리로 맞대 (달, 행 id) → 칸 글자를 만든다. 칸을 누른 것은 콜백이 세션에 적는 값
(`GAP_SHEET_CELL_KEY` = (범위 지문, 달, 행 id))을 바로 넣어 흉내 낸다 — 범위 지문은 그림
`layout.meta.scope` 에 있다. 콜백 자체는 `tests/test_availability_sheet_panel.py` 가 따로 본다.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
from streamlit.testing.v1 import AppTest

from capa_simulation.components.availability_sheet_keys import (
    GAP_SHEET_CELL_KEY,
    GAP_SHEET_CHART_KEY,
)
from capa_simulation.services.availability_sheet import (
    ROW_GAP_AVAILABLE,
    ROW_SCHEDULE_AVAILABLE,
    ROW_STATIC_AVAILABLE,
    SHEET_ROWS,
    SheetView,
)

_TAGS = re.compile(r"</?b>")


def chart_spec(app: AppTest, key: str = GAP_SHEET_CHART_KEY) -> dict[str, Any]:
    """그 key 의 그림 spec. 없으면 실패한다."""
    for chart in app.get("plotly_chart"):
        if str(chart.proto.id).endswith(f"-{key}"):
            spec: dict[str, Any] = json.loads(chart.proto.spec)
            return spec
    raise AssertionError(f"{key} 그림이 없다")


def has_sheet(app: AppTest) -> bool:
    return any(
        str(chart.proto.id).endswith(f"-{GAP_SHEET_CHART_KEY}") for chart in app.get("plotly_chart")
    )


def _targets(spec: dict[str, Any]) -> dict[tuple[float, float], tuple[int, str, str]]:
    target = spec["data"][0]
    return {
        (round(float(base) + 0.5, 6), round(float(y), 6)): (
            int(data[0]),
            str(data[1]),
            str(data[2]),
        )
        for base, y, data in zip(target["base"], target["y"], target["customdata"], strict=True)
    }


def sheet_cells(app: AppTest) -> dict[tuple[int, str], str]:
    """(달, 행 id) → 칸 글자(굵게 표시 뗌)."""
    spec = chart_spec(app)
    targets = _targets(spec)
    cells: dict[tuple[int, str], str] = {}
    for trace in spec["data"][1:]:
        if trace.get("mode") != "text":
            continue
        for x, y, text in zip(trace["x"], trace["y"], trace["text"], strict=True):
            found = targets.get((round(float(x), 6), round(float(y), 6)))
            if found is not None:
                cells[(found[0], found[1])] = _TAGS.sub("", str(text))
    return cells


def sheet_hovers(app: AppTest) -> dict[tuple[int, str], str]:
    """(달, 행 id) → 풍선 글."""
    return {(month, row): hover for month, row, hover in _targets(chart_spec(app)).values()}


def sheet_text_colors(app: AppTest) -> dict[tuple[int, str], str]:
    """(달, 행 id) → 글자색."""
    spec = chart_spec(app)
    targets = _targets(spec)
    colors: dict[tuple[int, str], str] = {}
    for trace in spec["data"][1:]:
        if trace.get("mode") != "text":
            continue
        for x, y in zip(trace["x"], trace["y"], strict=True):
            found = targets.get((round(float(x), 6), round(float(y), 6)))
            if found is not None:
                colors[(found[0], found[1])] = str(trace["textfont"]["color"])
    return colors


def sheet_value(app: AppTest, month: int, row: str) -> float | None:
    """칸 글자를 수로(「—」 면 None, ⚠·쉼표·부호 문자 정리)."""
    text = sheet_cells(app)[(month, row)].replace("⚠", "").strip()
    if text == "—":
        return None
    return float(text.replace(",", "").replace("−", "-").replace("+", ""))


def sheet_scope(app: AppTest) -> str:
    """그림 `layout.meta.scope` — 지금 범위 지문."""
    return str(chart_spec(app)["layout"]["meta"]["scope"])


def open_cell(app: AppTest, month: int, row: str) -> None:
    """칸을 누른 뒤 콜백이 세션에 남기는 값을 적는다(다음 `run()` 에 근거 카드가 선다)."""
    app.session_state[GAP_SHEET_CELL_KEY] = (sheet_scope(app), month, row)


def gap_view(month_count: int, *, empty_available_month: int | None = None) -> SheetView:
    """「가용대수 비교」 그림 시험의 9행 — 기존보유 3, 가용 1(빈 달 0), Static 4, GAP = 가용 − 1."""
    months = tuple((2026 + index // 12) * 100 + index % 12 + 1 for index in range(month_count))
    available = [0.0 if index == empty_available_month else 1.0 for index in range(month_count)]
    values = pd.DataFrame(float("nan"), index=list(SHEET_ROWS), columns=list(months))
    for month, value in zip(months, available, strict=True):
        values.loc[ROW_SCHEDULE_AVAILABLE, month] = 3.0 + value
        values.loc[ROW_STATIC_AVAILABLE, month] = 4.0
        values.loc[ROW_GAP_AVAILABLE, month] = value - 1.0
    return SheetView(months=months, values=values, baseline=pd.Series(3.0, index=list(months)))
