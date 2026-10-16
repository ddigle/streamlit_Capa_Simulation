# Purpose: 비교 시트 캔버스 13줄·칸 누름(같은 칸 다시 = 닫기)·프래그먼트 회차를 검사한다.

"""「Static 대비 일정」 비교 시트의 그림과 칸 누름.

`availability_sheet_canvas`(그림)·`availability_gap_panel`(콜백·프래그먼트)을 본다.

- 캔버스: 머리 1 + 구획 제목 3 + 값 9 = 13줄, 표적 `customdata = (YYYYMM, 행 id, 풍선)`, GAP 글자색,
  고른 칸 테두리, 「—」 칸, `layout.meta`(세대·범위 지문).
- 콜백: 같은 칸을 다시 누르면 닫고(닫기 단추 없음), 빈 선택도 닫으며, 닫은 뒤 같은 칸 한 번에 다시
  열린다. 누를 때마다 세대가 오른다.
- 프래그먼트: 칸을 누른 프래그먼트 회차의 그림·근거 카드가 같은 선택의 앱 전체 회차와 같고, 이벤트
  칸에 쓰는 수가 갈래(안 누름·설비 일정·Static·GAP·「—」·한쪽 공정·호기 필터)마다 같다.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import pytest
from fragment_browser import FragmentBrowser, install_fragment_browser
from sheet_reader import chart_spec, open_cell, sheet_text_colors
from streamlit.testing.v1 import AppTest
from test_availability_gap_panel import _panel_app
from test_availability_gap_unit_filter import _filter_app
from test_process_capa_detail_page import _event_slots

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.availability_gap_panel import (
    PROCESS_FILTER_KEY,
    RESULT_VIEW_KEY,
    UNIT_FILTER_COLUMNS_KEY,
    unit_filter_key,
)
from capa_simulation.components.availability_sheet_canvas import (
    GROUP_TITLES,
    build_availability_sheet_canvas,
)
from capa_simulation.components.availability_sheet_keys import (
    GAP_SHEET_CELL_KEY,
    GAP_SHEET_CHART_KEY,
    GAP_SHEET_FRAGMENT_KEY,
    GAP_SHEET_GENERATION_KEY,
)
from capa_simulation.components.month_sheet_canvas import (
    CUSTOMDATA_HOVER,
    CUSTOMDATA_MONTH,
    CUSTOMDATA_ROW,
)
from capa_simulation.design import theme, tokens
from capa_simulation.services.availability_sheet import (
    GAP_ROWS,
    REASON_NO_STATIC_PROCESS,
    ROW_GAP_AVAILABLE,
    ROW_GAP_LENT,
    ROW_SCHEDULE_AVAILABLE,
    ROW_SCHEDULE_LENT,
    ROW_STATIC_AVAILABLE,
    ROW_STATIC_OWNED,
    SHEET_ROWS,
    STATIC_ROWS,
    SheetView,
)

MONTH = 202610
MONTHS = (202610, 202611)


@pytest.fixture(autouse=True)
def _light_and_no_scrollbar(monkeypatch: pytest.MonkeyPatch) -> None:
    """밝은 테마로 그리고, AppTest 에서 등록되지 않는 가로 스크롤바 컴포넌트를 뺀다."""
    theme._LOCAL.mode = "light"
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda **_: None)


# ------------------------------------------------------------------ 캔버스


def _view() -> SheetView:
    values = pd.DataFrame(float("nan"), index=list(SHEET_ROWS), columns=list(MONTHS))
    for month in MONTHS:
        values.loc[[ROW_STATIC_OWNED, "static:lent", ROW_STATIC_AVAILABLE], month] = [
            7.0,
            -1.0,
            7.0,
        ]
        values.loc[["sched:owned", ROW_SCHEDULE_LENT, ROW_SCHEDULE_AVAILABLE], month] = [
            4.5,
            -0.25,
            4.25,
        ]
    values.loc[list(GAP_ROWS), MONTHS[0]] = [-2.5, 0.75, -2.75]
    reasons = {(row, MONTHS[1]): REASON_NO_STATIC_PROCESS for row in (*STATIC_ROWS, *GAP_ROWS)}
    for row in (*STATIC_ROWS, *GAP_ROWS):
        values.loc[row, MONTHS[1]] = float("nan")
    return SheetView(
        months=MONTHS,
        values=values,
        reasons=reasons,
        mismatch=frozenset({MONTHS[0]}),
        baseline=pd.Series([3.0, 3.0], index=list(MONTHS)),
    )


def _canvas_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    canvas = build_availability_sheet_canvas(
        view=_view(), process_label="공정 · 표시", schedule_detail="설비 DB · 환산대수", **kwargs
    )
    return (
        json.loads(canvas.labels.to_json()),
        json.loads(canvas.months.to_json()),
        canvas.row_ids,
    )


def test_the_sheet_has_a_header_three_titles_and_nine_value_rows() -> None:
    labels, months, rows = _canvas_json()
    assert len(rows) == 13
    assert rows[0] == "header"
    assert [row for row in rows if row.startswith("title:")] == [
        "title:static",
        "title:sched",
        "title:gap",
    ]
    assert [row for row in rows if ":" in row and not row.startswith("title:")] == list(SHEET_ROWS)
    texts = " ".join(item["text"] for item in labels["layout"]["annotations"])
    for title in GROUP_TITLES.values():
        assert title in texts
    assert "구분 · 공정 · 표시" in texts
    # 머리 칸은 누를 수 없다 — 표적은 값 아홉 줄 × 달이다.
    targets = months["data"][0]["customdata"]
    assert len(targets) == 9 * len(MONTHS)
    first = targets[0]
    assert (first[CUSTOMDATA_MONTH], first[CUSTOMDATA_ROW]) == (MONTHS[0], ROW_STATIC_OWNED)
    assert "RQ_EQP_OWN" in first[CUSTOMDATA_HOVER]


def test_gap_cells_take_the_delta_colours_and_blank_cells_say_why() -> None:
    _, months, _ = _canvas_json()
    texts: dict[str, str] = {}
    for trace in months["data"][2:]:
        if trace.get("mode") == "text":
            for text in trace["text"]:
                texts[text] = trace["textfont"]["color"]
    assert texts["−2.50"] == tokens.DELTA_DECREASE
    assert texts["+0.75"] == tokens.DELTA_INCREASE
    assert texts["—"] == tokens.TEXT_MUTED
    assert texts["7.00 ⚠"] == tokens.TEXT  # 불일치 달의 Static 가용
    hovers = {
        (item[CUSTOMDATA_MONTH], item[CUSTOMDATA_ROW]): item[CUSTOMDATA_HOVER]
        for item in months["data"][0]["customdata"]
    }
    assert "기준정보(Static)에 없는 공정" in hovers[(MONTHS[1], ROW_GAP_AVAILABLE)]
    assert "보유 4.500 + 대여(비가동) −0.250" in hovers[(MONTHS[0], ROW_SCHEDULE_AVAILABLE)]


def test_the_chosen_cell_gets_a_border_and_meta_carries_generation_and_scope() -> None:
    def borders(figure: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            shape
            for shape in figure["layout"].get("shapes", [])
            if shape.get("line", {}).get("color") == tokens.ACCENT
        ]

    _, plain, _ = _canvas_json()
    assert borders(plain) == []
    assert plain["layout"]["meta"] == {"generation": 0, "scope": ""}
    _, chosen, _ = _canvas_json(selected=(MONTHS[1], ROW_GAP_LENT), generation=4, scope="s")
    (border,) = borders(chosen)
    assert 1 < border["x0"] < border["x1"] < 2
    assert chosen["layout"]["meta"] == {"generation": 4, "scope": "s"}
    # 축 밖 달은 그리지 않는다.
    _, outside, _ = _canvas_json(selected=(199901, ROW_GAP_LENT))
    assert borders(outside) == []


# ------------------------------------------------------------------ 콜백


def _callback_script() -> None:
    import streamlit as st

    from capa_simulation.components.availability_gap_panel import pick_gap_sheet_cell
    from capa_simulation.components.availability_sheet_keys import GAP_SHEET_CHART_KEY

    if st.session_state.pop("action", None) == "pick":
        st.session_state[GAP_SHEET_CHART_KEY] = st.session_state.pop("selection")
        pick_gap_sheet_cell(str(st.session_state.pop("scope", "scope-a")), (202610, 202611))


def _point(month: int, row: str) -> dict[str, Any]:
    return {"selection": {"points": [{"customdata": [month, row, "풍선"]}]}}


EMPTY: dict[str, Any] = {"selection": {"points": []}}


def test_clicking_the_same_cell_again_closes_it_and_one_click_reopens_it() -> None:
    """같은 칸 다시 누르기 = 닫기(닫기 단추 없음). 빈 선택도 닫는다. 닫은 뒤 같은 칸은 한 번에 다시
    열린다. 머리·축 밖의 점은 무시한다. 세대는 누를 때마다 오른다."""
    app = AppTest.from_function(_callback_script, default_timeout=60).run()
    opened = ("scope-a", 202610, ROW_SCHEDULE_AVAILABLE)
    steps: list[tuple[dict[str, Any], tuple[str, int, str] | None, str]] = [
        (_point(202610, ROW_SCHEDULE_AVAILABLE), opened, "scope-a"),
        (_point(202610, ROW_SCHEDULE_AVAILABLE), None, "scope-a"),
        (_point(202610, ROW_SCHEDULE_AVAILABLE), opened, "scope-a"),
        (EMPTY, None, "scope-a"),
        (_point(202610, ROW_SCHEDULE_AVAILABLE), opened, "scope-a"),
        (_point(202611, ROW_GAP_LENT), ("scope-a", 202611, ROW_GAP_LENT), "scope-a"),
        (_point(202611, "header"), ("scope-a", 202611, ROW_GAP_LENT), "scope-a"),
        (_point(199901, ROW_GAP_LENT), ("scope-a", 202611, ROW_GAP_LENT), "scope-a"),
        # 다른 범위의 같은 자리 칸은 닫지 않고 새로 연다.
        (_point(202611, ROW_GAP_LENT), ("scope-b", 202611, ROW_GAP_LENT), "scope-b"),
    ]
    for generation, (selection, expected, scope) in enumerate(steps, start=1):
        app.session_state["action"] = "pick"
        app.session_state["selection"] = selection
        app.session_state["scope"] = scope
        app.run()
        assert not app.exception, [element.message for element in app.exception]
        assert app.session_state[GAP_SHEET_CELL_KEY] == expected, (generation, selection)
        assert app.session_state[GAP_SHEET_GENERATION_KEY] == generation


# ------------------------------------------------------------------ 프래그먼트


def _open_sheet(browser: FragmentBrowser, **state: object) -> AppTest:
    app = AppTest.from_function(_panel_app, default_timeout=60)
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    app.selectbox(key=PROCESS_FILTER_KEY).select(str(state.get("process", "Die Attach"))).run()
    app.segmented_control(key=RESULT_VIEW_KEY).set_value("분류별 내역").run()
    assert not app.exception, [element.message for element in app.exception]
    assert browser.started == [[]]
    return app


def _shown(app: AppTest) -> tuple[str, list[str], list[str]]:
    """그림 spec 과 근거 카드(글자·표). 프래그먼트 회차의 요소 트리는 그 회차 델타뿐이다 — 앱 전체
    회차와 견줄 때는 글자를 프래그먼트 쪽 차례로 맞춰 본다."""
    texts = [
        str(item.value) for elements in (app.markdown, app.caption, app.info) for item in elements
    ]
    frames = [element.value.to_json(force_ascii=False) for element in app.dataframe]
    return json.dumps(chart_spec(app), sort_keys=True), texts, frames


@pytest.mark.parametrize(
    ("process", "row"),
    [
        ("Die Attach", None),
        ("Die Attach", ROW_SCHEDULE_AVAILABLE),
        ("Die Attach", ROW_SCHEDULE_LENT),
        ("Die Attach", ROW_STATIC_OWNED),
        ("Die Attach", ROW_GAP_LENT),
        # 기준정보에만 있는 공정 — 설비 일정 기준 칸이 「—」 다.
        ("Probe", ROW_SCHEDULE_AVAILABLE),
    ],
)
def test_a_clicked_cell_reruns_only_the_sheet_with_the_full_run_output(
    process: str, row: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """칸 누름은 시트 프래그먼트만 돈다. 그 회차의 그림·근거 카드는 같은 선택의 앱 전체 회차와
    같고, 이벤트 칸에는 늘 스타일만 든 `st.html` 셋 — 앱 전체 회차의 그 프래그먼트와 같은 자리 —
    만 쓴다."""
    browser = install_fragment_browser(monkeypatch)
    app = _open_sheet(browser, process=process)
    sheet = browser.fragment_keyed(GAP_SHEET_FRAGMENT_KEY)
    full_slots = {slot for slot, owner in _event_slots(browser.messages).items() if owner == sheet}
    assert len(full_slots) == 3
    # 조건 카드(공정)와 보기 전환은 프래그먼트 밖이다.
    assert browser.fragment_of(GAP_SHEET_CHART_KEY) == sheet

    browser.fragment_queue = [sheet]
    if row is not None:
        open_cell(app, MONTH, row)
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    assert browser.started == [[sheet]]
    assert set(_event_slots(browser.messages)) == full_slots
    spec, texts, frames = _shown(app)
    assert texts

    browser.fragment_queue = []
    app.run()
    assert not app.exception
    assert browser.started == [[]]
    full_spec, full_texts, full_frames = _shown(app)
    assert (full_spec, full_frames) == (spec, frames)
    assert [text for text in full_texts if text in set(texts)] == texts
    owned = {slot for slot, owner in _event_slots(browser.messages).items() if owner == sheet}
    assert owned == full_slots


def test_a_unit_filter_is_a_full_run_and_writes_the_same_event_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """호기 필터(조건 카드)는 앱 전체 회차다. 필터 중 시트의 칸 누름도 프래그먼트 회차이고 이벤트 칸
    수가 같다. Static·GAP 칸은 「—」 이고 설비 일정 기준 칸은 걸린 호기만이다."""
    browser = install_fragment_browser(monkeypatch)
    app = AppTest.from_function(_filter_app, default_timeout=60).run()
    app.segmented_control(key=RESULT_VIEW_KEY).set_value("분류별 내역").run()
    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value(["공정구분"]).run()
    app.multiselect(key=unit_filter_key("공정구분")).set_value(["Line-A"]).run()
    assert not app.exception
    assert browser.started == [[]]
    sheet = browser.fragment_keyed(GAP_SHEET_FRAGMENT_KEY)
    full_slots = {slot for slot, owner in _event_slots(browser.messages).items() if owner == sheet}
    assert len(full_slots) == 3
    colors = sheet_text_colors(app)
    assert colors[(MONTH, ROW_GAP_AVAILABLE)] == tokens.TEXT_MUTED

    browser.fragment_queue = [sheet]
    open_cell(app, MONTH, ROW_SCHEDULE_AVAILABLE)
    app.run()
    assert not app.exception
    assert browser.started == [[sheet]]
    assert set(_event_slots(browser.messages)) == full_slots
    (lines,) = [element.value for element in app.dataframe]
    units = lines.loc[lines["구분"].astype(str).ne("합계")]
    assert sorted(units["설비명"]) == ["EQ-1", "EQ-3"]

    browser.fragment_queue = [sheet]
    open_cell(app, MONTH, ROW_STATIC_AVAILABLE)
    app.run()
    assert set(_event_slots(browser.messages)) == full_slots
    assert "호기 필터 중에는" in " ".join(str(item.value) for item in app.info)
