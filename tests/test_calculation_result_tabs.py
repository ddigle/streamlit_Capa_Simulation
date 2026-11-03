# Purpose: 산출 결과가 열린 탭 표만 만들고 제외 알림·Alarm 표·큰 목록 펼침과 그림 없음을 검증한다.

"""산출 결과는 열린 탭 하나의 몫만 만든다.

소요대수 월 표(정렬·컬럼 재배치 포함)와 확보율 표를 모든 탭·모든 조작에서 만들고 있었다(합성
표본에서 대당 Capa 탭 재실행의 약 27%, 샘플 관측). 그 표를 쓰는 탭이 열린 회차에만 캐시에서
꺼낸다. 대당 Capa 탭의 제외 알림(`ST-14`)도 그 탭이 열린 회차에만 낸다 — 목록은 본문 펼침이 아니라
그 알림의 표(Alarm 줄 「제외 기준정보 보기」 — 2026-11-02 사용자 요청(검수표))다. 표가 알림에 싣기에
크면 「제외 기준정보 확인」 펼침이 본문에 남고 기억 칸(`remembered_expander`)으로 편 상태를
지킨다 — key 없는 상자는 돌아올 때 새로 만들어져 접힌다.
"""

from collections.abc import Callable
from io import BytesIO
from typing import Any

import pandas as pd
import pytest
from alert_marks import alert_notes
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
from capa_simulation import alerts

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


def _notes(app: AppTest, code: str) -> list[dict[str, Any]]:
    return [note for note in alert_notes(app) if note.get("code") == code]


def test_an_opened_large_exclusion_box_stays_open_after_a_trip_to_another_tab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """알림에 싣기에 큰 제외 목록(`alerts.TABLE_ROW_LIMIT` 초과)은 본문 펼침으로 남는다 — 편 상태는
    다른 탭에 갔다 와도 그대로다. 그때 알림 짧은 글은 그 펼침을 가리킨다."""
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 1)
    app = AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception
    assert _exclusion_boxes(app) == [False]
    (note,) = _notes(app, "ST-14")
    assert "table" not in note and "「제외 기준정보 확인」" in note["short"]

    app.session_state[EXCLUSIONS_EXPANDER_KEY] = True  # 사용자가 상자를 편다
    app.run()
    assert _exclusion_boxes(app) == [True]

    _open_calc_tab(app, REQUIRED_TAB)
    # 닫힌 탭의 제외 알림은 내지 않는다.
    assert _exclusion_boxes(app) == []
    assert _notes(app, "ST-14") == []
    _open_calc_tab(app, UNIT_CAPACITY_TAB)

    assert _exclusion_boxes(app) == [True]


def test_the_unit_capacity_exclusions_ride_on_the_alarm_row_not_the_page() -> None:
    """대당 Capa 의 제외 알림과 「제외 기준정보」 목록은 우하단 알림창 · Alarm 이다(2026-11-02
    사용자 요청(검수표) — 「알림과 제외 기준정보는 우하단 팝업(통일된 양식)으로 뜨고 누적 알람에서
    제외 기준정보를 확인할 수 있게」). 본문에는 경고 상자 · 펼침 · 표 위 그림(옛 제외 워터폴)이
    없다.

    목록은 알림에 딸린 표(원본 공정명 · CSV 파일 이름 · 제외사유 칸)이고 「그 화면으로」 가 이 탭을
    연다."""
    app = AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60).run()
    assert not app.exception

    assert not app.get("plotly_chart")
    assert not app.warning
    assert _exclusion_boxes(app) == []
    (note,) = _notes(app, "ST-14")
    assert note["kind"] == "state" and note["active"] is True and note["level"] == "check"
    assert note["tab"] == "대당 Capa"
    assert note["short"].startswith("대당 Capa 산출에서 기준 2개를 뺐습니다")
    assert "Alarm" in note["short"] and "제외사유" in note["full"]
    table = note["table"]
    assert table["title"] == "제외 기준정보" and table["total"] == len(table["rows"]) == 2
    assert table["file"].startswith("Capa_Unit_Capacity_Exclusions_")
    assert "제외사유" in table["columns"] and table["columns"][0] == "공정"


def test_the_required_tab_alerts_and_keeps_its_lists() -> None:
    """소요대수 탭은 열린 회차마다 경로 쪽(`ST-15` · PKG 규칙 `ST-21`)과 계획 쪽(`ST-01` — Static
    Capa 와 같은 코드 · 같은 범위) 상태 알림을 낸다. 다른 화면이 「산출 결과 → 소요대수 탭」 으로
    가리키는 목록은 본문 펼침에 남는다."""
    app = _open_calc_tab(
        AppTest.from_string(EXCLUSION_PROCESS_TEST_SCRIPT, default_timeout=60), REQUIRED_TAB
    )
    assert not app.exception
    assert not app.warning
    codes = [note["code"] for note in alert_notes(app) if note.get("kind") == "state"]
    assert {"ST-15", "ST-21", "ST-01"} <= set(codes)
    assert all(note["tab"] == "소요대수" for note in alert_notes(app) if note.get("tab"))
    assert "ST-14" not in codes and "HM-02" not in codes


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
    """P2 — 경로에 닿지 않은 계획 부하는 소요대수 탭이 건수(상태 알림 `ST-01`)·목록·CSV 로 알린다.

    알리지 않으면 그 부하는 어느 공정의 소요대수에도 들지 않은 채 사라진다. 고칠 곳은 펼침 안 첫
    줄이 말한다.
    """
    app = _open_calc_tab(
        AppTest.from_string(UNROUTED_PLAN_RESULT_SCRIPT, default_timeout=60), REQUIRED_TAB
    )

    assert not app.warning
    (note,) = _notes(app, "ST-01")
    assert note["active"] is True
    assert "RQ_REQB 경로에 닿지 않은 계획 부하 1건" in note["full"]
    assert "산출 결과 › 소요대수" in note["short"]
    captions = [str(element.value) for element in app.caption]
    assert any("제외사유가" in text and "RQ_REQB" in text for text in captions), captions
    downloads = app.session_state["captured_downloads"]
    exported = pd.read_csv(
        BytesIO(bytes(downloads["download_unrouted_loads_csv"]["data"])),
        encoding="utf-8-sig",
        dtype="object",
    )
    assert exported[["Capa Code", "부하량", "제외사유"]].values.tolist() == [
        ["CAPA-NO-ROUTE", "40.0", "경로 키 어긋남"]
    ]
