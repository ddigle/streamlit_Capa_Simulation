# Purpose: Main `표현`(차트·표) 프래그먼트 회차의 결과를 같은 표현의 앱 전체 회차와 견준다.

"""Main 의 `표현` 과 결과 상자는 프래그먼트다(`equipment_explorer._render_expressed_result`).

`표현` 은 머리 줄(볼 내용·보기를 앱 전체 회차가 그린 줄) 끝에 프래그먼트가 쓴다 — Streamlit 1.63 의
바깥 컨테이너 쓰기. 브라우저 대역(`tests/fragment_browser.py`)으로 **진짜 프래그먼트
회차**를 돌려 본다(호스트는 `test_equipment_explorer._render_fixture`).

- 같은 숫자: `표현` 을 바꾼 프래그먼트 회차의 표·차트가 같은 표현의 앱 전체 회차와
  같다 — 표현이 있는 네 보기 모두.
- 무효화: 공정(조건)·볼 내용·보기는 프래그먼트 밖이라 앱 전체 회차이고, 그다음 프래그먼트 회차는
  그 회차의 거른 표로 그린다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fragment_browser import FragmentBrowser
from streamlit.testing.v1 import AppTest
from test_equipment_explorer import _render_fixture
from test_shortening_view_fragment import _fragment_of, _runner

from capa_simulation.components.equipment_explorer import (
    AS_OF_KEY,
    EXPRESSION_VIEWS,
    QUESTION_KEY,
    SMALL_PROCESS_KEY,
    START_DATE_KEY,
    TRANSITION_VIEW_KEY,
)

# 보기 → (볼 내용, 보기 상자 키). `주차별 추이` 는 `가용대수` 의 첫 보기라 따로 고르지 않는다.
_VIEWS = {
    "주차별 추이": ("가용대수", None),
    "상태 분포": ("호기 현황", "equipment_explorer_unit_view"),
    "Qual상태 분포": ("Qual 일정", "equipment_explorer_qual_view"),
    "단계별 건수": ("단계 전환", TRANSITION_VIEW_KEY),
}


def _expression_key(view: str) -> str:
    return f"equipment_explorer_expression_{view}"


def _result(app: AppTest) -> list[Any]:
    """결과 상자의 표 값과 차트 명세 — 같은 숫자를 견주는 꼴."""
    frames = [element.value.to_dict("split") for element in app.dataframe]
    charts = [element.proto.SerializeToString() for element in app.get("vega_lite_chart")]
    return [frames, charts]


def _open(runner: FragmentBrowser, view: str) -> AppTest:
    app = AppTest.from_function(_render_fixture, default_timeout=60).run()
    assert not app.exception
    question, view_key = _VIEWS[view]
    app.segmented_control(QUESTION_KEY).set_value(question).run()
    if view_key is not None:
        app.selectbox(view_key).set_value(view).run()
    assert not app.exception
    assert runner.started == [[]]
    return app


def test_the_four_expression_views_are_the_ones_the_fragment_draws() -> None:
    assert set(_VIEWS) == set(EXPRESSION_VIEWS)


@pytest.mark.parametrize("view", list(_VIEWS))
def test_switching_the_expression_reruns_only_the_result_with_the_full_run_numbers(
    view: str, request: pytest.FixtureRequest
) -> None:
    runner = _runner(request)
    app = _open(runner, view)
    result = _fragment_of(runner, _expression_key(view))
    assert result, "표현은 결과 프래그먼트가 그린다"
    # 볼 내용·보기·조건은 프래그먼트 밖이다 — 바꾸면 앱 전체 회차다.
    for key in (QUESTION_KEY, SMALL_PROCESS_KEY):
        assert _fragment_of(runner, key) == "", key
    chart = _result(app)

    for expression in ("표", "차트"):
        runner.fragment_queue = [result]
        app.segmented_control(_expression_key(view)).set_value(expression).run()
        assert not app.exception and not app.error
        assert runner.started == [[result]], expression
        in_fragment = _result(app)
        # 결과는 하나(표 하나 또는 차트 하나)다 — 앞 표현의 결과가 남지 않는다.
        assert sum(len(part) for part in in_fragment) == 1, expression

        runner.fragment_queue = []
        app.run()
        assert not app.exception
        assert runner.started == [[]]
        assert _result(app) == in_fragment, expression
    # 차트로 돌아오면 처음 차트와 같다.
    assert _result(app) == chart


def test_a_condition_is_a_full_run_and_the_next_expression_run_uses_it(
    request: pytest.FixtureRequest,
) -> None:
    runner = _runner(request)
    app = _open(runner, "상태 분포")
    result = _fragment_of(runner, _expression_key("상태 분포"))
    runner.fragment_queue = [result]
    app.segmented_control(_expression_key("상태 분포")).set_value("표").run()
    every = app.dataframe[0].value
    assert every["설비대수"].sum() == pytest.approx(4.0)

    # 공정은 조건 카드다 — 브라우저는 앱 전체 회차를 청한다. 프래그먼트 회차의 트리에는 카드가 없어
    # 앱 전체 회차를 한 번 돌려 카드를 다시 세운 뒤 고른다.
    runner.fragment_queue = []
    app.run()
    app.multiselect(SMALL_PROCESS_KEY).set_value(["Other"]).run()
    assert runner.started == [[]]
    assert app.dataframe[0].value["설비대수"].sum() == pytest.approx(1.0)

    # 차트로 갔다가 표로 돌아오는 프래그먼트 회차도 그 공정만 센다.
    result = _fragment_of(runner, _expression_key("상태 분포"))
    for expression in ("차트", "표"):
        runner.fragment_queue = [result]
        app.segmented_control(_expression_key("상태 분포")).set_value(expression).run()
        assert runner.started == [[result]]
    assert app.dataframe[0].value["설비대수"].sum() == pytest.approx(1.0)


def test_the_date_widgets_stay_outside_the_result_fragment(
    request: pytest.FixtureRequest,
) -> None:
    """기간·기준일은 조건(본문 상자나 카드)이다 — 표현 프래그먼트에 들지 않는다."""
    runner = _runner(request)
    _open(runner, "단계별 건수")
    for key in (START_DATE_KEY, AS_OF_KEY):
        assert _fragment_of(runner, key) == "", key
