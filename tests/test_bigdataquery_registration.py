# Purpose: bigdataquery registration 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date

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


def _run(**session: object) -> AppTest:
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
    memo = app.text_area[0].value
    assert memo is not None and "PLAN 알파(DEMO-PLAN-1)" in memo


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
    assert app.date_input(key=registration.FORM_DETAIL_START_KEY).value is None
    assert app.date_input(key=registration.FORM_DETAIL_END_KEY).value is None


def test_picking_a_code_fills_the_detail_window_around_its_registration_date() -> None:
    """고른 코드의 원천 등록일 7일 전 ~ 3일 뒤로 두 칸을 채운다(2026-09-29 사용자 결정 A+B)."""
    app = _run(__pick_row__=0)

    assert app.date_input(key=registration.FORM_DETAIL_START_KEY).value == date(2026, 8, 26)
    assert app.date_input(key=registration.FORM_DETAIL_END_KEY).value == date(2026, 9, 5)
    captions = " ".join(item.value for item in app.caption)
    assert "고른 코드의 원천 등록일: 2026-09-02." in captions


def test_a_widened_detail_window_survives_the_same_pick() -> None:
    """등록 뒤에도 계속 수정된 코드는 사용자가 넓힌다.

    같은 행이 선택된 채 도는 다음 런이 넓힌 기간을 기본값으로 되돌리지 않는다.
    """
    app = _run(__pick_row__=0)
    app.date_input(key=registration.FORM_DETAIL_END_KEY).set_value(date(2026, 9, 20)).run()

    assert not app.exception
    assert app.session_state[registration.FORM_DETAIL_END_KEY] == date(2026, 9, 20)


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


OLD_CODE_SCRIPT = (
    STEP_SCRIPT.replace(
        '"regist_data": ["2026-09-02 03:04:05", "2026-09-01 01:02:03"],',
        '"regist_data": ["2025-11-02 03:04:05", "2026-09-01 01:02:03"],',
    )
    .replace(
        """        token="demo-token",
    ),
)""",
        """        token="demo-token",
        first_registered={("DEMO-A-001", "DEMO-PLAN-1"): date(2025, 10, 1)},
    ),
)""",
    )
    .replace(
        "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW))",
        "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW, "
        "first_registered_on=date(2025, 10, 1)))",
    )
)


def test_an_old_code_seen_on_several_days_gets_a_window_across_all_of_them() -> None:
    """목록 기간이 최근 일주일이어도 상세 기본 창은 그 코드의 등록일에 맞춰진다.

    목록 정리는 최신 행(2025-11-02)만 남기고 가장 이른 등록일(2025-10-01)은 따로 들고 온다.
    기본 창이 그 사이를 자르면 이미 목록에 보인 적재분이 오류 없이 빠진다.
    """
    app = AppTest.from_string(OLD_CODE_SCRIPT)
    # 목록은 최신 등록순이라 2025-11-02 에 등록된 DEMO-A 가 둘째 행이다.
    app.session_state["__pick_row__"] = 1
    app.run()
    assert not app.exception

    assert app.session_state[registration.FORM_CODE_KEY] == "DEMO-A-001"
    assert app.date_input(key=registration.FORM_DETAIL_START_KEY).value == date(2025, 9, 24)
    assert app.date_input(key=registration.FORM_DETAIL_END_KEY).value == date(2025, 11, 5)
    captions = " ".join(item.value for item in app.caption)
    assert "고른 코드의 원천 등록일: 2025-10-01 ~ 2025-11-02." in captions
    # 메모의 상세 조회기간은 저장할 때 실제로 조회한 기간으로 붙는다(칸을 고칠 수 있어서).
    memo = app.text_area[0].value
    assert memo is not None and "상세 조회기간" not in memo


SUBMIT_SCRIPT = """
from datetime import date, datetime

import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration

registered = st.session_state.get("__registered_at__")
window = registration._submitted_detail_window(
    registered, simulation_code=st.session_state.get("__code__", "")
)
st.session_state["__window__"] = None if window is None else window.label()
"""


@pytest.mark.parametrize(
    ("start", "end", "registered_at", "expected", "error"),
    [
        # 두 칸이 우선이다 — 등록 뒤 계속 수정된 코드는 사용자가 넓힌 기간 그대로 조회한다.
        (date(2025, 1, 1), date(2025, 12, 31), None, "2025-01-01 ~ 2025-12-31", None),
        # 둘 다 비었으면 원천 DB 등록시점 7일 전 ~ 3일 뒤(코드를 직접 적은 경우).
        (None, None, "2025-06-10", "2025-06-03 ~ 2025-06-13", None),
        # 기간을 모르는 채로 넓은 기본 창을 조용히 쓰지 않는다.
        (None, None, None, None, "원천 DB 등록시점"),
        (date(2025, 1, 1), None, "2025-06-10", None, "둘 다 비우세요"),
        (date(2025, 2, 1), date(2025, 1, 1), None, None, "늦을 수 없습니다"),
    ],
)
def test_the_submitted_detail_window(
    start: date | None,
    end: date | None,
    registered_at: str | None,
    expected: str | None,
    error: str | None,
) -> None:
    from datetime import datetime

    app = AppTest.from_string(SUBMIT_SCRIPT)
    app.session_state[registration.FORM_DETAIL_START_KEY] = start
    app.session_state[registration.FORM_DETAIL_END_KEY] = end
    app.session_state["__registered_at__"] = (
        None if registered_at is None else datetime.fromisoformat(registered_at)
    )
    app.run()

    assert not app.exception
    assert app.session_state["__window__"] == expected
    errors = " ".join(item.value for item in app.error)
    if error is None:
        assert not errors
    else:
        assert error in errors


PICKED_A = registration.PickedFields(
    code="DEMO-A-001",
    start=date(2026, 8, 26),
    end=date(2026, 9, 5),
    registered_at="2026-09-02 03:04:05",
)


@pytest.mark.parametrize(
    ("code", "start", "end", "registered_text", "blocked"),
    [
        # 목록에서 고른 코드 그대로면 그 창을 쓴다.
        ("DEMO-A-001", date(2026, 8, 26), date(2026, 9, 5), "2026-09-02 03:04:05", None),
        # 코드만 바꿔 적고 날짜는 손대지 않았다 — 남의 등록일 창이라 막는다.
        ("DEMO-Z-999", date(2026, 8, 26), date(2026, 9, 5), "", "원천 등록일로 채워진"),
        # 코드를 바꾸고 날짜도 고쳤다 — 사용자가 정한 기간을 믿는다.
        ("DEMO-Z-999", date(2026, 8, 26), date(2026, 9, 20), "", None),
        # 날짜를 고쳤어도 등록시점이 남의 값 그대로면 막는다 — 저장 메타데이터가 된다.
        ("DEMO-Z-999", date(2026, 8, 26), date(2026, 9, 20), "2026-09-02 03:04:05", "등록시점"),
        # 안내대로 두 칸을 비웠는데 등록시점이 남의 값이면, 같은 남의 창이 다시 만들어진다 — 막는다.
        ("DEMO-Z-999", None, None, "2026-09-02 03:04:05", "등록시점"),
        # 두 칸을 비우고 이 코드의 등록시점을 적으면 그 기준으로 조회한다.
        ("DEMO-Z-999", None, None, "2026-06-10 00:00:00", None),
    ],
)
def test_a_picked_window_is_not_reused_silently_for_another_code(
    code: str,
    start: date | None,
    end: date | None,
    registered_text: str,
    blocked: str | None,
) -> None:
    """목록에서 고른 뒤 코드 칸만 고쳐 적으면 앞 코드의 등록일 창으로 오류 없이 조회됐다.

    2026-09-29 리뷰 — 손대지 않은 남의 기본 창만 막고, 사용자가 고친 기간은 믿는다.
    """
    from datetime import datetime

    app = AppTest.from_string(SUBMIT_SCRIPT)
    app.session_state[registration.CATALOG_FORM_PICKED_WINDOW_KEY] = PICKED_A
    app.session_state[registration.FORM_DETAIL_START_KEY] = start
    app.session_state[registration.FORM_DETAIL_END_KEY] = end
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = registered_text
    app.session_state["__registered_at__"] = (
        datetime.fromisoformat(registered_text) if registered_text else None
    )
    app.session_state["__code__"] = code
    app.run()

    assert not app.exception
    errors = " ".join(item.value for item in app.error)
    if blocked is None:
        assert not errors
        assert app.session_state["__window__"] is not None
    else:
        assert "다른 코드" in errors and blocked in errors
        assert app.session_state["__window__"] is None


MULTI_PLAN_SCRIPT = STEP_SCRIPT.replace(
    "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW))",
    "registration._apply_pick(registration.CatalogPick(row=row, window=WINDOW, "
    "first_registered_on=date(2026, 7, 1), last_registered_on=date(2026, 9, 10)))",
)


def test_a_pick_covers_every_plan_row_of_the_same_code() -> None:
    """고른 줄의 등록일이 아니라 그 코드의 모든 PLAN 줄 등록일 범위로 기본 창을 채운다."""
    app = AppTest.from_string(MULTI_PLAN_SCRIPT)
    app.session_state["__pick_row__"] = 0
    app.run()

    assert not app.exception
    assert app.date_input(key=registration.FORM_DETAIL_START_KEY).value == date(2026, 6, 24)
    assert app.date_input(key=registration.FORM_DETAIL_END_KEY).value == date(2026, 9, 13)
    assert app.session_state[registration.CATALOG_FORM_PICKED_WINDOW_KEY] == (
        registration.PickedFields(
            code="DEMO-A-001",
            start=date(2026, 6, 24),
            end=date(2026, 9, 13),
            registered_at="2026-09-02 03:04:05",
        )
    )


def test_the_detail_dates_stay_clearable_after_a_pick() -> None:
    """고른 뒤에도 두 칸을 비울 수 있어야 등록시점 규칙으로 돌아간다.

    Streamlit 은 처음 값(`value`)이 None 인 날짜 칸에만 지우기 단추를 준다 — `proto.default` 가
    비어 있어야 한다. `value=None` 을 빼면 값은 같아 보여도 칸을 비울 수 없게 된다.
    """
    app = _run(__pick_row__=0)

    for key, expected in (
        (registration.FORM_DETAIL_START_KEY, date(2026, 8, 26)),
        (registration.FORM_DETAIL_END_KEY, date(2026, 9, 5)),
    ):
        widget = app.date_input(key=key)
        assert widget.value == expected
        assert list(widget.proto.default) == []


def test_the_selection_builds_the_span_from_every_plan_row_of_the_whole_catalog() -> None:
    """목록 선택은 정리된 목록 전체의 같은 코드 줄로 등록일 범위를 낸다.

    검색으로 좁힌 행(`visible`)으로 구하면 필터가 범위를 줄인다.
    """
    from datetime import datetime

    import pandas as pd

    from capa_simulation.io.company_bigdataquery_adapter import QueryWindow
    from capa_simulation.services.bigdataquery_catalog_view import (
        catalog_row_at,
        filter_catalog,
        normalize_catalog,
    )

    catalog = normalize_catalog(
        pd.DataFrame(
            {
                "simulation_name": ["알파", "알파", "베타"],
                "simulation_code": ["DEMO-A-001", "DEMO-A-001", "DEMO-B-002"],
                "plan_name": ["PLAN 하나", "PLAN 둘", "PLAN 셋"],
                "plan_code": ["DEMO-PLAN-1", "DEMO-PLAN-2", "DEMO-PLAN-3"],
                "regist_data": [
                    "2026-09-02 03:04:05",
                    "2026-07-15 00:00:00",
                    "2026-09-01 01:02:03",
                ],
            }
        )
    )
    result = registration.CatalogResult(
        frame=catalog,
        window=QueryWindow(start_date=date(2026, 6, 1), end_date=date(2026, 9, 8)),
        queried_at=datetime(2026, 9, 8, 10, 0, 0),
        token="demo",
        first_registered={("DEMO-A-001", "DEMO-PLAN-2"): date(2026, 7, 1)},
    )
    visible = filter_catalog(catalog, keyword="하나", scope="전체", registered_codes=frozenset())
    row = catalog_row_at(visible, 0)
    assert row is not None and row.plan_code == "DEMO-PLAN-1"

    pick = registration.catalog_pick(result, row)

    assert (pick.first_registered_on, pick.last_registered_on) == (
        date(2026, 7, 1),
        date(2026, 9, 2),
    )
