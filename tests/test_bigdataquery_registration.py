# Purpose: bigdataquery registration 관련 정상·예외·회귀 동작을 검증한다.

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import bigdataquery_registration as registration

REPORT_SCRIPT = """
import pandas as pd
import streamlit as st

from capa_simulation.components.bigdataquery_registration import (
    CONFLICT_REPORT_STATE_KEY,
    _render_reference_conflict_report,
)

st.session_state.setdefault(
    CONFLICT_REPORT_STATE_KEY,
    {
        "report": pd.DataFrame(
            {
                "RQ테이블": ["RQ_PKG_PLAN"],
                "충돌그룹": ["RQ_PKG_PLAN-0001"],
                "업무키컬럼": ["생산계획년월 | 제품정보"],
                "생산계획년월": [202608],
                "제품정보": ["Product-A"],
                "충돌컬럼": ["생산수량"],
                "후보값": ['[{"생산수량":100.0},{"생산수량":200.0}]'],
                "선택값": ['{"생산수량":100.0}'],
                "충돌행수": [2],
                "임시제외행수": [1],
                "후보원천행번호": ["1 | 2"],
                "선택원천행번호": [1],
                "임시처리": ["원천 행 순서상 첫 번째 행 유지"],
            }
        ),
        "file_name": "RQ_업무키_충돌_SIM-001.csv",
    },
)
_render_reference_conflict_report()
"""


def test_conflict_report_renders_summary_and_download() -> None:
    app = AppTest.from_string(REPORT_SCRIPT).run()

    assert not app.exception
    assert "1개 업무 키 그룹" in app.warning[0].value
    assert app.dataframe[0].value.loc[0, "RQ테이블"] == "RQ_PKG_PLAN"
    assert len(app.get("download_button")) == 1


# 목록 결과를 세션에 심고 컴포넌트를 그리는 스크립트. 사내 패키지·DuckDB 없이 돈다.
STEP_SCRIPT = """
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
from capa_simulation.services.bigdataquery_catalog_view import normalize_catalog

WINDOW = QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8))
CATALOG = normalize_catalog(
    pd.DataFrame(
        {
            "simulation_name": ["알파 시뮬", "베타 시뮬"],
            "simulation_code": ["DEMO-A-001", "DEMO-B-002"],
            "plan_name": ["PLAN 알파", "PLAN 베타"],
            "plan_code": ["DEMO-PLAN-1", "DEMO-PLAN-2"],
            "regist_data": ["2026-09-02 03:04:05", "2026-09-01 01:02:03"],
        }
    )
)
st.session_state.setdefault(
    registration.CATALOG_RESULT_KEY,
    registration.CatalogResult(
        frame=CATALOG,
        window=WINDOW,
        queried_at=datetime(2026, 9, 8, 10, 0, 0),
        token="demo-token",
    ),
)
if st.session_state.get("__pick_row__") is not None:
    row = registration.catalog_row_at(CATALOG, int(st.session_state["__pick_row__"]))
    registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW))
if st.session_state.get("__request_reset__"):
    st.session_state.pop("__request_reset__")
    registration._request_reset()

repository = SimpleNamespace(list_scenarios=lambda: [])
registration.render_bigdataquery_registration(repository, "demo.duckdb")
"""


def _run(**session):
    app = AppTest.from_string(STEP_SCRIPT)
    for key, value in session.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    return app


def test_both_steps_render_in_one_run() -> None:
    """탭을 오갈 때 값이 사라지지 않도록 두 폼을 항상 그린다."""
    app = _run()

    assert {"시작일", "종료일"} <= {widget.label for widget in app.date_input}
    labels = {widget.label for widget in app.button}
    assert "시뮬레이션 코드 조회" in labels
    assert "DB 조회 후 시나리오 저장" in labels
    assert {"조회할 시뮬레이션 코드", "저장할 시나리오명"} <= {
        widget.label for widget in app.text_input
    }


def test_catalog_list_is_drawn_with_a_fixed_height_for_scrolling() -> None:
    app = _run()

    values = [frame.value for frame in app.dataframe]
    assert any("시뮬레이션 코드" in getattr(value, "columns", []) for value in values)
    assert registration.CATALOG_LIST_HEIGHT_PX == 390


def test_selecting_a_row_prefills_the_registration_form() -> None:
    app = _run(__pick_row__=0)

    values = {widget.label: widget.value for widget in app.text_input}
    assert values["조회할 시뮬레이션 코드"] == "DEMO-A-001"
    assert values["원천 시뮬레이션명"] == "알파 시뮬"
    assert values["저장할 시나리오명"] == "알파 시뮬 (DEMO-A-001)"
    assert values["원천 DB 등록시점 (선택)"] == "2026-09-02 03:04:05"
    assert "PLAN 알파(DEMO-PLAN-1)" in app.text_area[0].value


def test_reselecting_the_same_row_keeps_user_edits() -> None:
    """같은 행이 계속 선택돼 있을 뿐인 런에서 사용자가 고친 값을 덮지 않는다."""
    app = _run(__pick_row__=0)
    app.text_input(key=registration.FORM_SCENARIO_NAME_KEY).set_value("내가 고친 이름").run()

    assert not app.exception
    assert app.session_state[registration.FORM_SCENARIO_NAME_KEY] == "내가 고친 이름"


def test_reset_clears_the_pick_and_the_form_on_the_next_run() -> None:
    """이미 만든 위젯 key 는 같은 런에서 지울 수 없어 다음 런 첫 줄에서 비운다."""
    app = _run(__pick_row__=0)
    app.session_state["__pick_row__"] = None
    app.session_state["__request_reset__"] = True
    app.run()

    assert not app.exception
    assert app.session_state[registration.FORM_CODE_KEY] == ""
    assert registration.CATALOG_PICK_KEY not in app.session_state


@pytest.mark.parametrize(
    "event",
    [
        None,
        {},
        {"selection": None},
        {"selection": {"rows": []}},
        {"selection": {"rows": "0"}},
        {"selection": {"rows": [True]}},
        {"selection": {"rows": ["0"]}},
    ],
)
def test_first_selected_row_ignores_broken_events(event: object) -> None:
    assert registration.first_selected_row(event) is None


def test_first_selected_row_reads_the_first_position() -> None:
    assert registration.first_selected_row({"selection": {"rows": [3, 5]}}) == 3


def test_catalog_list_key_changes_with_the_visible_rows() -> None:
    """key 를 고정하면 필터로 행 수가 달라져도 옛 위치가 돌아와 다른 행이 선택된다."""
    base = registration.catalog_list_key("token", 0, "", "전체")

    assert base != registration.catalog_list_key("token", 1, "", "전체")
    assert base != registration.catalog_list_key("token", 0, "알파", "전체")
    assert base != registration.catalog_list_key("token", 0, "", "미등록만")
    assert base != registration.catalog_list_key("other", 0, "", "전체")
    assert base == registration.catalog_list_key("token", 0, "", "전체")
