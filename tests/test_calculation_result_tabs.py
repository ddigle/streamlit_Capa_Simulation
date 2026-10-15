# Purpose: 산출 결과가 열린 탭의 표만 만들고, 닫힌 탭을 건너도 제외 상자 펼침을 지키는지 검증한다.

"""산출 결과는 열린 탭 하나의 몫만 만든다.

소요대수 월 표(정렬·컬럼 재배치 포함)와 확보율 표를 모든 탭·모든 조작에서 만들고 있었다(합성
표본에서 대당 Capa 탭 재실행의 약 27%, 샘플 관측). 그 표를 쓰는 탭이 열린 회차에만 캐시에서
꺼낸다. 대당 Capa 탭의 제외 안내도 그 탭이 열린 회차에만 그리므로, 「제외 기준정보 확인」 상자는
기억 칸(`remembered_expander`)으로 편 상태를 지킨다 — key 없는 상자는 돌아올 때 새로 만들어져
접힌다.
"""

from collections.abc import Callable
from io import BytesIO
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    EXCLUSION_PROCESS_TEST_SCRIPT,
    REQUIRED_TAB,
    SECUREMENT_TAB,
    TEST_SCRIPT,
    TWO_PROCESS_RESULT_SCRIPT,
    _open_calc_tab,
)

import capa_simulation.services.simulation_cache as simulation_cache

UNIT_CAPACITY_TAB = ":material/insights: 대당 Capa"
EXCLUSIONS_EXPANDER_KEY = "unit_capacity_exclusions_expander"
# 경로에 닿지 않는 계획 한 줄을 더한 시나리오. 계산을 실제로 돌려야 attrs 가 생긴다.
UNROUTED_PLAN_RESULT_SCRIPT = (
    TEST_SCRIPT.replace('PAGE_NAME = "reference_data.py"', 'PAGE_NAME = "calculation_result.py"')
    .replace("ADD_UNROUTED_PLAN = False", "ADD_UNROUTED_PLAN = True")
    .replace("STUB_CALCULATIONS = True", "STUB_CALCULATIONS = False")
    .replace('"test-capacity-standards-page"', '"test-capacity-unrouted-plan-page"')
)
assert "ADD_UNROUTED_PLAN = True" in UNROUTED_PLAN_RESULT_SCRIPT


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


def _required_csv(app: AppTest) -> pd.DataFrame:
    downloads = app.session_state["captured_downloads"]
    data = downloads["download_required_equipment_summary_csv"]["data"]
    return pd.read_csv(BytesIO(bytes(data)), encoding="utf-8-sig", dtype="object")


def test_the_required_csv_follows_the_table_filter() -> None:
    """소요대수 CSV 바이트는 표 내용 지문 키 캐시다. 필터로 표가 바뀌면 파일도 그 표를 싣는다."""
    app = _open_calc_tab(
        AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60), REQUIRED_TAB
    )
    both = _required_csv(app)
    assert set(both["공정"]) == {"Process-A", "Process-B"}

    app.multiselect(key="required_equipment_filter_공정").set_value(["Process-B"]).run()
    assert not app.exception
    assert set(_required_csv(app)["공정"]) == {"Process-B"}

    app.multiselect(key="required_equipment_filter_공정").set_value([]).run()
    assert not app.exception
    pd.testing.assert_frame_equal(_required_csv(app), both)


def test_the_required_tab_lists_plan_load_that_reaches_no_route() -> None:
    """P2 — 경로에 닿지 않은 계획 부하는 소요대수 탭이 건수·목록·CSV 로 알린다.

    알리지 않으면 그 부하는 어느 공정의 소요대수에도 들지 않은 채 사라진다.
    """
    app = _open_calc_tab(
        AppTest.from_string(UNROUTED_PLAN_RESULT_SCRIPT, default_timeout=60), REQUIRED_TAB
    )

    warnings = [element.value for element in app.warning]
    assert any("RQ_REQB 경로에 닿지 않은 계획 부하가 1건" in text for text in warnings), warnings
    downloads = app.session_state["captured_downloads"]
    exported = pd.read_csv(
        BytesIO(bytes(downloads["download_unrouted_loads_csv"]["data"])),
        encoding="utf-8-sig",
        dtype="object",
    )
    assert exported[["Capa Code", "부하량", "제외사유"]].values.tolist() == [
        ["CAPA-NO-ROUTE", "40.0", "경로 키 어긋남"]
    ]
