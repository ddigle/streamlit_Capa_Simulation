# Purpose: 산출 결과가 열린 탭의 표만 만들고, 닫힌 탭을 건너도 제외 상자 펼침을 지키는지 검증한다.

"""산출 결과는 열린 탭 하나의 몫만 만든다.

소요대수 월 표(정렬·컬럼 재배치 포함)와 확보율 표를 모든 탭·모든 조작에서 만들고 있었다(합성
표본에서 대당 Capa 탭 재실행의 약 27%, 샘플 관측). 그 표를 쓰는 탭이 열린 회차에만 캐시에서
꺼낸다. 대당 Capa 탭의 제외 안내도 그 탭이 열린 회차에만 그리므로, 「제외 기준정보 확인」 상자는
기억 칸(`remembered_expander`)으로 편 상태를 지킨다 — key 없는 상자는 돌아올 때 새로 만들어져
접힌다.
"""

from collections.abc import Callable
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    EXCLUSION_PROCESS_TEST_SCRIPT,
    REQUIRED_TAB,
    SECUREMENT_TAB,
    TWO_PROCESS_RESULT_SCRIPT,
    _open_calc_tab,
)

import capa_simulation.services.simulation_cache as simulation_cache

UNIT_CAPACITY_TAB = ":material/insights: 대당 Capa"
EXCLUSIONS_EXPANDER_KEY = "unit_capacity_exclusions_expander"


def _record(monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...]) -> list[str]:
    """캐시 래퍼를 부른 차례를 적는다(계산은 그대로 한다). 페이지는 exec 때 모듈 속성을 집는다."""
    calls: list[str] = []
    for name in names:
        original: Callable[..., Any] = getattr(simulation_cache, name)

        def recording(
            *args: Any, _name: str = name, _original: Callable[..., Any] = original, **kwargs: Any
        ) -> Any:
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(simulation_cache, name, recording)
    return calls


def test_only_the_open_tab_builds_its_month_table(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch, ("get_required_month_table", "get_scenario_securement_rate"))

    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60).run()
    assert not app.exception
    assert calls == []

    _open_calc_tab(app, REQUIRED_TAB)
    assert calls == ["get_required_month_table"]
    assert "captured_dimensions::required_equipment_summary_table" in app.session_state

    calls.clear()
    _open_calc_tab(app, SECUREMENT_TAB)
    assert calls == ["get_scenario_securement_rate"]
    assert "captured_dimensions::securement_rate_monthly_table" in app.session_state


def _exclusion_boxes(app: AppTest) -> list[bool]:
    return [
        bool(box.proto.expanded)
        for box in app.expander
        if str(box.proto.id).endswith(f"-{EXCLUSIONS_EXPANDER_KEY}")
    ]


def test_an_opened_exclusion_box_stays_open_after_a_trip_to_another_tab() -> None:
    app = AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception
    assert _exclusion_boxes(app) == [False]

    app.session_state[EXCLUSIONS_EXPANDER_KEY] = True  # 사용자가 상자를 편다
    app.run()
    assert _exclusion_boxes(app) == [True]

    _open_calc_tab(app, REQUIRED_TAB)
    # 닫힌 탭의 제외 안내는 그리지 않는다.
    assert _exclusion_boxes(app) == []
    assert "대당 Capa 산출에서 2개 기준을 제외했습니다." not in {
        warning.value for warning in app.warning
    }
    _open_calc_tab(app, UNIT_CAPACITY_TAB)

    assert _exclusion_boxes(app) == [True]


def test_a_month_table_error_stays_in_its_own_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """표 하나의 오류(표시순서 규칙 충돌 등)는 그 표의 탭에만 뜬다. 다른 탭은 그대로 쓴다."""

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("RQ_DISPLAY_ORDER의 컬럼 정렬 규칙이 충돌합니다: ['공정']")

    monkeypatch.setattr(simulation_cache, "get_required_month_table", broken)

    app = AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60).run()
    assert not app.exception
    assert [element.value for element in app.error] == []

    _open_calc_tab(app, REQUIRED_TAB)
    assert [element.value for element in app.error] == [
        "RQ_DISPLAY_ORDER의 컬럼 정렬 규칙이 충돌합니다: ['공정']"
    ]

    _open_calc_tab(app, SECUREMENT_TAB)
    assert [element.value for element in app.error] == []
