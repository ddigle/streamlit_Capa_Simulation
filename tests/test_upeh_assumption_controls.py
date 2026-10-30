# Purpose: UPEH 가정 입력의 비활성·되돌리기·선택지·역산 단추와 화면 사이 이어짐을 본다.

"""「UPEH 가정」 입력 — `components/upeh_assumption_controls.py`.

컴포넌트만 띄운 AppTest 로 칸의 규칙을 보고(오늘은 고정), 앱 전체(`app.py`)를 띄워 **공정 Capa
상세에서 둔 값이 필요 단축 일정의 첫 회차에도 그대로인지** 본다 — 위젯 id 에 페이지가 들어가
`carry_shared_widget_value` 가 없으면 옮긴 첫 회차에 기본값(100)으로 선다(`shared_widget_state`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.upeh_assumption_controls import (
    UPEH_RESET_BUTTON_KEY,
    assumption_month_options,
)
from capa_simulation.navigation import PROCESS_CAPA_DETAIL, REQUIRED_SHORTENING
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_END_KEY,
    UPEH_ASSUMPTION_PERCENT_KEY,
    UPEH_ASSUMPTION_START_KEY,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
INVERSE_KEY = "test_upeh_inverse"


def _controls_script() -> None:
    from datetime import date

    import streamlit as st

    from capa_simulation.components.upeh_assumption_controls import (
        render_inverse,
        render_upeh_assumption_controls,
    )
    from capa_simulation.services.upeh_assumption import INVERSE_OK, InversePercent

    span = st.session_state.get("span", (202601, 202612))
    result = render_upeh_assumption_controls(
        owner=st.session_state.get("owner", "a"),
        start_month=span[0],
        end_month=span[1],
        today=date(2026, 6, 15),
    )
    st.session_state["result"] = (
        None if result is None else (result.percent, result.start, result.end, result.active)
    )
    render_inverse(
        InversePercent(INVERSE_OK, 118),
        goal="구간 안 단축 0",
        key="test_upeh_inverse",
        current=None if result is None else result.percent,
    )


def _app() -> AppTest:
    return AppTest.from_function(_controls_script, default_timeout=60)


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


def test_the_options_are_the_period_months_from_this_month() -> None:
    assert assumption_month_options(202601, 202604, today=date(2026, 2, 20)) == [
        202602,
        202603,
        202604,
    ]
    assert assumption_month_options(202611, 202702, today=date(2026, 6, 1)) == [
        202611,
        202612,
        202701,
        202702,
    ]
    assert assumption_month_options(202601, 202603, today=date(2026, 6, 1)) == []


def test_at_100_percent_the_span_is_disabled_and_the_assumption_is_off() -> None:
    app = _ok(_app().run())
    percent = app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY)
    assert percent.value == 100
    assert app.selectbox(key=UPEH_ASSUMPTION_START_KEY).disabled
    assert app.selectbox(key=UPEH_ASSUMPTION_END_KEY).disabled
    assert app.selectbox(key=UPEH_ASSUMPTION_START_KEY).options == [
        "26.06",
        "26.07",
        "26.08",
        "26.09",
        "26.10",
        "26.11",
        "26.12",
    ]
    assert app.session_state["result"] == (100, 202606, 202612, False)
    assert UPEH_RESET_BUTTON_KEY not in {str(button.key) for button in app.button}
    assert any("이 세션만" in str(caption.value) for caption in app.caption)


def test_a_percent_enables_the_span_and_back_to_100_turns_it_off() -> None:
    app = _ok(_app().run())
    app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).set_value(110)
    _ok(app.run())
    assert not app.selectbox(key=UPEH_ASSUMPTION_START_KEY).disabled
    app.selectbox(key=UPEH_ASSUMPTION_START_KEY).set_value(202608)
    _ok(app.run())
    assert app.session_state["result"] == (110, 202608, 202612, True)

    app.button(key=UPEH_RESET_BUTTON_KEY).click()
    _ok(app.run())
    assert app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).value == 100
    # 구간은 그대로 둔다.
    assert app.session_state["result"] == (100, 202608, 202612, False)


def test_the_inverse_button_writes_the_value_into_the_percent_box() -> None:
    app = _ok(_app().run())
    assert any("구간 안 단축 0 → UPEH ≥ 118%" in str(caption.value) for caption in app.caption)
    app.button(key=INVERSE_KEY).click()
    _ok(app.run())
    assert app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).value == 118
    # 지금 값과 같으면 단추를 두지 않는다.
    assert INVERSE_KEY not in {str(button.key) for button in app.button}


def test_clearing_the_percent_box_turns_the_assumption_off_at_100() -> None:
    """칸을 비우고 Enter 하면 100%(꺼짐)다 — 최소값 80% 가 아니다(2026-10-27 표적 E2E).

    1.63 숫자 칸은 빈 칸을 위젯 기본값으로 보내고(브라우저) 서버도 빈 값을 기본값으로 읽는다.
    기본값이 최소값이면 가정을 끄려던 사람에게 가장 강한 악화 가정이 걸렸다.
    """
    app = _ok(_app().run())
    app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).set_value(120)
    _ok(app.run())
    assert app.session_state["result"][0] == 120

    app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).set_value(None)
    _ok(app.run())
    box = app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY)
    assert app.session_state["result"] == (100, 202606, 202612, False)
    # 칸에도 100 이 다시 선다(서버가 값을 적어 브라우저에 알린다).
    assert box.value == 100
    assert (box.proto.value, box.proto.set_value) == (100, True)
    assert UPEH_RESET_BUTTON_KEY not in {str(button.key) for button in app.button}


@pytest.mark.parametrize(("typed", "applied"), [(151, 150), (79, 80), (1000, 150), (0, 80)])
def test_a_percent_outside_the_range_is_clamped_and_shown_in_the_box(
    typed: int, applied: int
) -> None:
    """범위 밖 값은 가까운 끝으로 깎아 칸과 적용값이 같다 — 칸에 79 가 남은 채 적용값은 앞 값이던
    어긋남(2026-10-27 표적 E2E)이 없다."""
    app = _ok(_app().run())
    app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).set_value(120)
    _ok(app.run())

    app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).set_value(typed)
    _ok(app.run())
    box = app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY)
    assert box.value == applied
    assert app.session_state["result"][0] == applied
    assert (box.proto.value, box.proto.set_value) == (applied, True)


def test_the_browser_box_neither_fills_a_cleared_value_nor_holds_an_out_of_range_one() -> None:
    """브라우저 쪽 계약 — 칸에 위젯 기본값도 범위도 싣지 않는다.

    1.63 프런트는 빈 칸을 확정할 때 위젯 기본값(`default`)을 보내고, 범위(`has_min`·`has_max`)
    밖 글은 확정하지 않고 쥔 채 서버가 보낸 값도 받지 않는다. 둘 다 서버(콜백)가 정한다.
    """
    app = _ok(_app().run())
    proto = app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).proto
    assert not proto.HasField("default")
    assert not proto.has_min
    assert not proto.has_max


def test_a_month_outside_the_new_options_gets_a_new_value_written() -> None:
    """조회기간이 바뀌어 고른 달이 선택지 밖이면 지우지 않고 새 값을 적는다."""
    app = _ok(_app().run())
    app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).set_value(120)
    _ok(app.run())
    app.session_state["span"] = (202609, 202611)
    _ok(app.run())
    assert app.session_state[UPEH_ASSUMPTION_START_KEY] == 202609
    assert app.session_state[UPEH_ASSUMPTION_END_KEY] == 202611
    assert app.session_state["result"] == (120, 202609, 202611, True)


def test_a_period_without_future_months_draws_only_the_percent_box() -> None:
    app = _app()
    app.session_state["span"] = (202601, 202603)
    _ok(app.run())
    assert app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).value == 100
    assert app.session_state["result"] is None
    assert any("이번 달 이후의 달이 없어" in str(caption.value) for caption in app.caption)


# ------------------------------------------------------------------ 두 화면 사이(앱 전체)


@pytest.fixture
def _full_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 시뮬레이션 DB(내장 시드)와, 샘플 fleet 공정에 Cut-off 만 적은 설비 DB 를 보는 `app.py`.

    필요 단축 일정은 Cut-off 가 있어야 조건 카드 끝(UPEH 가정)까지 그린다.
    """
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    equipment_path = tmp_path / "equipment.duckdb"
    repository = DuckDBEquipmentRepository(equipment_path)
    repository.initialize()
    processes = sorted(set(sample_equipment_master()["공정소분류"]))
    repository.save_process_cutoff(
        pd.DataFrame(
            {
                "공정": processes,
                "Cutoff일수": [10.0] * len(processes),
                "비고": [None] * len(processes),
            }
        )
    )
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", equipment_path)
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    clear_equipment_repository()
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


def test_the_percent_set_on_the_detail_page_holds_on_the_first_shortening_run(
    _full_app: AppTest,
) -> None:
    app = _full_app.run()
    app.switch_page(PROCESS_CAPA_DETAIL.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).set_value(110).run()
    assert app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).value == 110

    app.switch_page(REQUIRED_SHORTENING.path).run()
    assert not list(app.exception), [element.message for element in app.exception]
    box = app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY)
    # 옮긴 첫 회차에 서버가 값을 다시 적어 브라우저에 알린다(`set_value`).
    assert (box.proto.value, box.proto.set_value) == (110, True)
    app.run()
    assert app.number_input(key=UPEH_ASSUMPTION_PERCENT_KEY).value == 110
    clear_equipment_repository()
