# Purpose: 실적 화면이 닫힌 요약·개선과제 탭을 건너뛰고 열린 탭은 같은 값을 그리는지 본다.

from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import performance_actual_screen as screen
from capa_simulation.services.performance_actuals import (
    EFFICIENCY_METRIC,
    build_monthly_actual_demo,
    build_priority_table,
)

TAB_KEY = "tabs_test_active_tab"


def _app() -> None:
    from capa_simulation.components.performance_actual_screen import (
        render_performance_actual_screen,
    )
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.services.performance_actuals import EFFICIENCY_METRIC

    render_performance_actual_screen(
        EFFICIENCY_METRIC, key_prefix="tabs_test", process_labels=ProcessLabels()
    )


@pytest.fixture
def priority_builds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return build_priority_table(*args, **kwargs)

    monkeypatch.setattr(screen, "build_priority_table", counting)
    return calls


def _open(label: str) -> AppTest:
    app = AppTest.from_function(_app, default_timeout=60)
    app.session_state[TAB_KEY] = label
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _tab(app: AppTest, label: str) -> Any:
    return next(tab for tab in app.tabs if tab.label == label)


def _expected_priority() -> Any:
    return build_priority_table(build_monthly_actual_demo(), EFFICIENCY_METRIC, ["공정"])


@pytest.mark.parametrize(("label", "builds"), [("요약", 1), ("상세 분석", 0), ("개선과제", 1)])
def test_the_priority_table_is_built_once_and_only_for_an_open_tab_that_uses_it(
    priority_builds: list[int], label: str, builds: int
) -> None:
    app = _open(label)
    priority_builds.clear()

    app.run()

    assert len(priority_builds) == builds


def test_closed_summary_and_action_tabs_draw_nothing() -> None:
    app = _open("상세 분석")

    assert not _tab(app, "요약").get("metric")
    assert not _tab(app, "요약").get("plotly_chart")
    assert not _tab(app, "개선과제").get("dataframe")
    # 상세 분석의 조회 조건 위젯은 그대로다.
    assert _tab(app, "상세 분석").get("multiselect")


def test_the_open_summary_shows_the_same_numbers() -> None:
    app = _open("요약")
    priority = _expected_priority()

    metrics = {metric.label: metric.value for metric in _tab(app, "요약").get("metric")}
    assert metrics["개선 필요 공정"] == f"{int(priority['상태'].eq('개선 필요').sum()):,}개"
    assert metrics["관찰 공정"] == f"{int(priority['상태'].eq('관찰').sum()):,}개"
    assert metrics["분석 공정"] == f"{priority['공정'].nunique():,}개"
    assert len(_tab(app, "요약").get("plotly_chart")) == 2
    assert not _tab(app, "개선과제").get("dataframe")


def test_the_open_action_tab_shows_the_priority_table() -> None:
    app = _open("개선과제")
    priority = _expected_priority()

    tables = _tab(app, "개선과제").get("dataframe")
    shown = tables[0].value
    assert shown["우선순위"].tolist() == priority["우선순위"].tolist()
    assert shown["점수"].tolist() == priority["점수"].tolist()
    assert shown["상태"].tolist() == priority["상태"].tolist()
    assert not _tab(app, "요약").get("metric")


def test_opening_a_tab_draws_it_in_that_run() -> None:
    app = _open("상세 분석")
    assert not _tab(app, "개선과제").get("dataframe")

    app.session_state[TAB_KEY] = "개선과제"
    app.run()

    assert not app.exception
    assert _tab(app, "개선과제").get("dataframe")
    assert not _tab(app, "상세 분석").get("plotly_chart")
