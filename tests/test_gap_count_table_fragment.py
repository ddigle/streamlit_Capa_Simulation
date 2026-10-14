# Purpose: Static/Dynamic 분류별 대수 표의 칸 누름 프래그먼트 회차를 앱 전체 회차와 견준다.

"""분류별 대수 표와 누른 칸의 호기는 프래그먼트다(`availability_gap_panel._render_count_table`).

`test_shortening_view_fragment` 처럼 브라우저 대역(`tests/fragment_browser.py`)으로
**진짜 프래그먼트 회차**를 돌린다. 패널은 `test_availability_gap_unit_filter` 의 호스트(호기 셋·두
라인, 조건은 사이드바)를 쓴다.

- 같은 숫자: 칸을 누른 프래그먼트 회차의 표·칸의 호기가, 같은 선택의 앱 전체 회차와
  같다.
- 무효화: 호기 필터(조건 카드)는 프래그먼트 밖이라 앱 전체 회차로 표를 다시 더하고, 그다음
  프래그먼트 회차의 칸 호기는 걸러진 호기만이다.

AppTest 는 표의 칸 선택을 위젯 상태로 들고 다니지 않는다 — 브라우저는 고른 칸을 회차마다 보내므로
앱 전체 회차 앞에도 같은 선택을 세션에 다시 적는다.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fragment_browser import FragmentBrowser
from streamlit.testing.v1 import AppTest
from test_availability_gap_unit_filter import _filter_app
from test_shortening_view_fragment import _fragment_of, _runner

from capa_simulation.components.availability_gap_panel import (
    PROCESS_FILTER_KEY,
    RESULT_VIEW_KEY,
    UNIT_FILTER_COLUMNS_KEY,
    matrix_table_key,
    unit_filter_key,
)
from capa_simulation.services.availability_gap import DYNAMIC_SUBTOTAL_ROW


def _open(runner: FragmentBrowser) -> AppTest:
    app = AppTest.from_function(_filter_app, default_timeout=60).run()
    assert not app.exception
    app.segmented_control(key=RESULT_VIEW_KEY).set_value("분류별 내역").run()
    assert not app.exception
    assert runner.started == [[]]
    return app


def _frames(app: AppTest) -> list[pd.DataFrame]:
    return [element.value for element in app.dataframe]


def _click(app: AppTest, key: str, rows: list[str], row: str) -> None:
    app.session_state[key] = {
        "selection": {"rows": [], "columns": [], "cells": [[rows.index(row), "26.10"]]}
    }


def _assert_same(left: list[pd.DataFrame], right: list[pd.DataFrame]) -> None:
    assert len(left) == len(right)
    for one, other in zip(left, right, strict=True):
        pd.testing.assert_frame_equal(one, other)


def test_a_clicked_cell_reruns_only_the_table_with_the_full_run_units(
    request: pytest.FixtureRequest,
) -> None:
    runner = _runner(request)
    app = _open(runner)
    rows = [str(row) for row in app.dataframe[0].value.index]
    key = matrix_table_key(None, [202610], rows)
    table = _fragment_of(runner, key)
    assert table, "분류별 대수 표는 프래그먼트 안이다"
    # 조건 카드(공정·호기 필터)와 보기 전환은 프래그먼트 밖이다.
    for widget in (PROCESS_FILTER_KEY, UNIT_FILTER_COLUMNS_KEY, RESULT_VIEW_KEY):
        assert _fragment_of(runner, widget) == "", widget

    for row in ("가용", DYNAMIC_SUBTOTAL_ROW):
        runner.fragment_queue = [table]
        _click(app, key, rows, row)
        app.run()
        assert not app.exception
        assert runner.started == [[table]], row
        in_fragment = _frames(app)
        # 표 + 그 칸의 호기. 칸의 호기를 더하면 표의 값이다.
        assert len(in_fragment) == 2, row
        assert in_fragment[1]["대수"].sum() == pytest.approx(in_fragment[0].loc[row, "26.10"])

        # 같은 선택의 앱 전체 회차 — 표와 호기가 같다.
        runner.fragment_queue = []
        _click(app, key, rows, row)
        app.run()
        assert not app.exception
        assert runner.started == [[]]
        _assert_same(_frames(app), in_fragment)


def test_the_unit_filter_is_a_full_run_and_the_next_click_lists_only_its_units(
    request: pytest.FixtureRequest,
) -> None:
    runner = _runner(request)
    app = _open(runner)

    # 호기 필터는 조건 카드다 — 브라우저는 앱 전체 회차를 청한다.
    runner.fragment_queue = []
    app.multiselect(key=UNIT_FILTER_COLUMNS_KEY).set_value(["공정구분"]).run()
    app.multiselect(key=unit_filter_key("공정구분")).set_value(["Line-A"]).run()
    assert not app.exception
    assert runner.started == [[]]
    rows = [str(row) for row in app.dataframe[0].value.index]
    key = matrix_table_key(None, [202610], rows)
    table = _fragment_of(runner, key)
    assert table

    runner.fragment_queue = [table]
    _click(app, key, rows, "가용")
    app.run()
    assert not app.exception
    assert runner.started == [[table]]
    in_fragment = _frames(app)
    assert sorted(in_fragment[1]["설비명"]) == ["EQ-1", "EQ-3"]
    assert in_fragment[1]["대수"].sum() == pytest.approx(in_fragment[0].loc["가용", "26.10"])

    runner.fragment_queue = []
    _click(app, key, rows, "가용")
    app.run()
    assert not app.exception
    _assert_same(_frames(app), in_fragment)


def test_a_process_card_change_is_a_full_run_and_the_next_click_lists_only_that_process(
    request: pytest.FixtureRequest,
) -> None:
    runner = _runner(request)
    app = _open(runner)
    rows_all = [str(row) for row in app.dataframe[0].value.index]
    key_all = matrix_table_key(None, [202610], rows_all)
    table_all = _fragment_of(runner, key_all)

    # 공정 전체에서 칸을 누른 뒤(프래그먼트 회차) 공정 카드를 바꾼다(앱 전체 회차).
    runner.fragment_queue = [table_all]
    _click(app, key_all, rows_all, "가용")
    app.run()
    assert sorted(_frames(app)[1]["설비명"]) == ["EQ-1", "EQ-2", "EQ-3"]
    # 프래그먼트 회차의 요소 트리는 그 회차 델타뿐이다 — 카드를 누르려면 앱 전체 회차를 돈다.
    runner.fragment_queue = []
    _click(app, key_all, rows_all, "가용")
    app.run()
    assert len(_frames(app)) == 2
    app.selectbox(key=PROCESS_FILTER_KEY).set_value("Etch").run()
    assert not app.exception
    assert runner.started == [[]]
    # 표 키에 공정이 들어 있어 새 표다 — 앞에서 누른 칸이 따라오지 않는다.
    assert len(_frames(app)) == 1
    rows = [str(row) for row in app.dataframe[0].value.index]
    key = matrix_table_key("Etch", [202610], rows)
    assert key != key_all

    # 다음 칸 누름 프래그먼트 회차는 그 공정의 호기만 보이고, 합계가 표의 칸 값과 같다.
    table = _fragment_of(runner, key)
    runner.fragment_queue = [table]
    _click(app, key, rows, "가용")
    app.run()
    assert not app.exception
    assert runner.started == [[table]]
    in_fragment = _frames(app)
    assert sorted(in_fragment[1]["설비명"]) == ["EQ-3"]
    assert in_fragment[1]["대수"].sum() == pytest.approx(in_fragment[0].loc["가용", "26.10"])

    runner.fragment_queue = []
    _click(app, key, rows, "가용")
    app.run()
    assert not app.exception
    _assert_same(_frames(app), in_fragment)
