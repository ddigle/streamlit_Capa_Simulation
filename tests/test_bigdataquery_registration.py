# Purpose: bigdataquery registration 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date
from pathlib import Path

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
if st.session_state.get("__rerun__"):
    # 페이지의 다른 탭(시나리오 관리)이 등록 폼보다 먼저 `st.rerun()` 으로 끊은 회차.
    st.session_state["__rerun__"] = False
    st.rerun()

repository = SimpleNamespace(list_scenarios=lambda: [])
if not st.session_state.get("__skip__"):
    # 건너뛴 회차는 다른 화면을 다녀온 것이다 — 그 회차에 등록 폼이 그려지지 않는다.
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


def test_the_dropped_row_warning_stands_under_the_saved_notice() -> None:
    """저장 뒤 회차에 성공 알림과 CS 빈 행 경고가 같은 알림 칸에 차례로 서고, 한 번만 그린다."""
    from capa_simulation.components.flash import FlashNote

    notice = "CS 가 빈 행 3개(계획 1행)는 양산구분(양산·ER)을 정할 수 없어 빼고 저장했습니다."
    app = _run(
        **{
            registration.REGISTRATION_FLASH_KEY: "「PSM W42」를 저장하고 r1을 올렸습니다.",
            registration.REGISTRATION_DROP_FLASH_KEY: FlashNote(
                "warning", notice, ":material/warning:"
            ),
        }
    )

    assert [item.value for item in app.success] == ["「PSM W42」를 저장하고 r1을 올렸습니다."]
    assert notice in [item.value for item in app.warning]
    assert registration.REGISTRATION_DROP_FLASH_KEY not in app.session_state


CATALOG_FAILURE_SCRIPT = """
import sys
from datetime import date
from types import SimpleNamespace

import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow


class Error(Exception):
    pass


def get_data(**_kwargs):
    raise Error("Read timed out")


st.session_state.setdefault(registration.CATALOG_RESULT_KEY, "직전 목록")
saved = sys.modules.get("bigdataquery")
sys.modules["bigdataquery"] = SimpleNamespace(getData=get_data)
try:
    registration._run_catalog_query(
        QueryWindow(start_date=date(2026, 9, 21), end_date=date(2026, 10, 21))
    )
finally:
    if saved is None:
        sys.modules.pop("bigdataquery", None)
    else:
        sys.modules["bigdataquery"] = saved
"""


def test_a_package_failure_in_the_catalog_query_says_what_to_do_and_keeps_the_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사내 패키지의 `Error` 는 화면이 잡는 예외 튜플 밖이다 — 감싸지 않으면 목록 조회가
    traceback 으로 멈췄다(사내 리뷰 202610200720 요청 2). 안내와 다시 할 길을 내고 직전 목록은
    둔다."""
    monkeypatch.delenv("CAPA_BDQ_USER_NAME", raising=False)
    app = AppTest.from_string(CATALOG_FAILURE_SCRIPT)
    app.run()

    assert not app.exception
    [error] = app.error
    assert "시간 초과" in error.value and "다시" in error.value
    assert app.session_state[registration.CATALOG_RESULT_KEY] == "직전 목록"


IMPORT_FAILURE_SCRIPT = """
import sys
from datetime import date

import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow

st.session_state.setdefault(registration.CATALOG_RESULT_KEY, "직전 목록")
saved = sys.modules.pop("bigdataquery", None)
sys.path.insert(0, PACKAGE_ROOT)
try:
    registration._run_catalog_query(
        QueryWindow(start_date=date(2026, 9, 21), end_date=date(2026, 10, 21))
    )
finally:
    sys.path.remove(PACKAGE_ROOT)
    sys.modules.pop("bigdataquery", None)
    if saved is not None:
        sys.modules["bigdataquery"] = saved
st.write("목록 조회 뒤")
"""


def test_a_package_that_fails_to_import_does_not_stop_the_catalog_query(
    tmp_path: Path,
) -> None:
    """패키지는 깔렸는데 불러오다 깨지면(DLL 등) `ImportError` 가 화면 예외 튜플 밖으로 새어
    목록 조회가 traceback 으로 멈췄다. 원인을 오류 칸에 적고 직전 목록과 뒤 화면은 둔다."""
    package = tmp_path / "bigdataquery"
    package.mkdir()
    (package / "__init__.py").write_text(
        'raise ImportError("DLL load failed while importing _jpype")\n', encoding="utf-8"
    )
    script = IMPORT_FAILURE_SCRIPT.replace("PACKAGE_ROOT", repr(str(tmp_path)))
    app = AppTest.from_string(script)
    app.run()

    assert not app.exception
    [error] = app.error
    assert "불러오지 못했습니다" in error.value and "DLL load failed" in error.value
    assert app.session_state[registration.CATALOG_RESULT_KEY] == "직전 목록"
    assert any(block.value == "목록 조회 뒤" for block in app.markdown)


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


@pytest.mark.parametrize("interruption", ["__skip__", "__rerun__"])
def test_a_picked_form_survives_a_run_that_did_not_draw_it(interruption: str) -> None:
    """목록 선택은 위젯이 아닌 칸이라 남는데, 폼 글자 칸은 그리지 않은 회차에 Streamlit 이 버린다.

    다른 화면을 다녀오거나 시나리오 관리 탭의 `st.rerun()` 이 등록 폼보다 먼저 끊으면 행은 선택된
    채 코드·이름만 비어 저장이 막혔고, 같은 행이 다시 선택될 뿐이라 다시 채워지지도 않았다.
    사용자가 넓힌 상세 조회 기간(세션에 남는 칸)은 기본값으로 되돌리지 않는다.
    """
    app = _run(__pick_row__=0)
    # 이제부터 폼을 다시 채울 길은 목록 표가 같은 행을 다시 고르는 `selection_default` 하나다.
    app.session_state["__pick_row__"] = None
    app.date_input(key=registration.FORM_DETAIL_END_KEY).set_value(date(2026, 9, 20)).run()
    app.session_state[interruption] = True
    app.run()
    app.session_state[interruption] = False
    app.run()

    assert not app.exception
    values = {widget.label: widget.value for widget in app.text_input}
    assert values["조회할 시뮬레이션 코드"] == "DEMO-A-001"
    assert values["원천 시뮬레이션명"] == "알파 시뮬"
    assert values["저장할 시나리오명"] == "알파 시뮬 (DEMO-A-001)"
    assert values["원천 DB 등록시점 (선택)"] == "2026-09-02 03:04:05"
    memo = app.text_area[0].value
    assert memo is not None and "PLAN 알파(DEMO-PLAN-1)" in memo
    assert app.date_input(key=registration.FORM_DETAIL_START_KEY).value == date(2026, 8, 26)
    assert app.date_input(key=registration.FORM_DETAIL_END_KEY).value == date(2026, 9, 20)


def test_a_reset_form_stays_empty_after_a_run_that_did_not_draw_it() -> None:
    """초기화한 폼은 다른 화면을 다녀와도 앞 선택의 값으로 되살아나지 않는다."""
    app = _run(__pick_row__=0)
    app.session_state["__pick_row__"] = None
    app.session_state["__request_reset__"] = True
    app.run()
    app.session_state["__skip__"] = True
    app.run()
    app.session_state["__skip__"] = False
    app.run()

    assert not app.exception
    assert app.text_input(key=registration.FORM_CODE_KEY).value == ""
    assert app.text_input(key=registration.FORM_SCENARIO_NAME_KEY).value == ""
    assert registration.CATALOG_PICK_KEY not in app.session_state


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


SAVE_SCRIPT = """
from pathlib import Path

import streamlit as st

from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.core_data_source import CoreDataBatch
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset


class FakeProvider:
    def __init__(self, *, simulation_name, source_registered_at, window):
        st.session_state["__window__"] = window.label()
        self._name = simulation_name
        self._registered_at = source_registered_at

    def fetch(self, simulation_code):
        frame = build_builtin_seed_dataset().source_data.copy()
        # 시험이 고른 행의 CS 를 비운다(행 번호 → 넣을 값). 사내 원천에 CS 가 빈 행이 온 꼴.
        for index, value in st.session_state.get("__blank_cs__", {}).items():
            frame.loc[int(index), "CS"] = value
        return CoreDataBatch(
            simulation_code=simulation_code,
            simulation_name=self._name,
            source_type="BIGDATAQUERY",
            frame=frame,
            source_registered_at=self._registered_at,
        )


database_path = st.session_state["__database__"]
if not st.session_state.get("__saved__"):
    st.session_state["__saved__"] = True
    original = registration.BigDataQueryCoreDataProvider
    registration.BigDataQueryCoreDataProvider = FakeProvider
    try:
        registration._save_scenario(
            DuckDBScenarioRepository(Path(database_path)),
            database_path,
            existing_names=frozenset(),
        )
    finally:
        registration.BigDataQueryCoreDataProvider = original
"""


def test_the_form_saves_through_the_session_free_registration_path(tmp_path: Path) -> None:
    """화면 저장은 세션 없는 등록 경로(`scenario_registration`)를 지나도 예전과 같은 것을 남긴다.

    폼의 이름·리비전명·등록시점, 메모 뒤의 상세 조회기간, 세션의 레거시 확보·경고 값, 저장 뒤
    활성화와 안내 한 줄이다. 공식버전 자동 갱신이 같은 길로 저장한다.
    """
    from datetime import datetime

    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.scenario_preset_state import SECURE_THRESHOLD_KEY, WARNING_THRESHOLD_KEY
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    database = tmp_path / "registration.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())

    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["__database__"] = str(database)
    app.session_state[registration.FORM_CODE_KEY] = "SIM-W41"
    app.session_state[registration.FORM_SOURCE_NAME_KEY] = "PSM W41"
    app.session_state[registration.FORM_SCENARIO_NAME_KEY] = "PSM W41 (SIM-W41)"
    app.session_state[registration.FORM_REVISION_NAME_KEY] = "초기 리비전"
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = "2026-10-12 09:00:00"
    app.session_state[registration.FORM_NOTE_KEY] = "원천 PLAN 메모"
    app.session_state[registration.FORM_DETAIL_START_KEY] = date(2026, 10, 5)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 10, 15)
    app.session_state[SECURE_THRESHOLD_KEY] = 110.0
    app.session_state[WARNING_THRESHOLD_KEY] = 100.0
    app.run()

    assert not app.exception
    assert not app.error
    assert app.session_state["__window__"] == "2026-10-05 ~ 2026-10-15"
    assert "올렸습니다" in app.session_state[registration.REGISTRATION_FLASH_KEY]
    [scenario] = repository.list_scenarios()
    assert (scenario.scenario_name, scenario.source_simulation_code) == (
        "PSM W41 (SIM-W41)",
        "SIM-W41",
    )
    assert scenario.source_registered_at == datetime(2026, 10, 12, 9, 0)
    snapshot = repository.load_revision(scenario.active_revision_id)
    assert snapshot.revision.revision_name == "초기 리비전"
    assert snapshot.revision.note == "원천 PLAN 메모 · 상세 조회기간 2026-10-05 ~ 2026-10-15"
    assert (snapshot.preset.secure_threshold, snapshot.preset.warning_threshold) == (1.10, 1.00)
    assert snapshot.preset.included_processes == (
        "DEMO_Chip_Attach",
        "DEMO_Final_Test",
        "DEMO_Wafer_Inspect",
    )
    # CS 가 빈 행이 없으면 경고도 메모 조각도 없다.
    assert registration.REGISTRATION_DROP_FLASH_KEY not in app.session_state


def _registration_app(database: Path, blank_cs: dict[int, str | None]) -> AppTest:
    """폼 값을 채우고 원천의 고른 행 CS 를 비운 채 화면 저장 경로를 한 번 돌린다."""
    app = AppTest.from_string(SAVE_SCRIPT, default_timeout=60)
    app.session_state["__database__"] = str(database)
    app.session_state["__blank_cs__"] = blank_cs
    app.session_state[registration.FORM_CODE_KEY] = "SIM-W42"
    app.session_state[registration.FORM_SOURCE_NAME_KEY] = "PSM W42"
    app.session_state[registration.FORM_SCENARIO_NAME_KEY] = "PSM W42 (SIM-W42)"
    app.session_state[registration.FORM_REVISION_NAME_KEY] = "초기 리비전"
    app.session_state[registration.FORM_REGISTERED_AT_KEY] = "2026-10-26 09:00:00"
    app.session_state[registration.FORM_NOTE_KEY] = "원천 PLAN 메모"
    app.session_state[registration.FORM_DETAIL_START_KEY] = date(2026, 10, 19)
    app.session_state[registration.FORM_DETAIL_END_KEY] = date(2026, 10, 27)
    return app.run()


def _registration_database(tmp_path: Path) -> Path:
    """표시순서까지 채운 빈 저장소. 등록은 공용 표시순서를 읽는다."""
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import load_builtin_display_order

    database = tmp_path / "registration.duckdb"
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.initialize_global_display_order(load_builtin_display_order())
    return database


def test_rows_with_a_blank_cs_are_dropped_and_the_registration_still_saves(
    tmp_path: Path,
) -> None:
    """사내 원천에 CS 가 빈 행이 와서 양산구분이 비고 저장이 막혔다(2026-10-27 사용자 결정).

    그 행은 표에서 빼고 저장한다. 저장 알림 밑에 뺀 행 수(계획 행 수)를 경고로 띄우고, 같은 수를
    리비전 메모 끝에 남긴다. 원천 스냅샷에는 받은 96행이 그대로 남는다(합성 시드 — 샘플 관측).
    """
    from capa_simulation.components.flash import FlashNote
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

    database = _registration_database(tmp_path)
    source = build_builtin_seed_dataset().source_data
    plans = source.index[source["계획기초정보여부"].eq("Y")]
    routes = source.index[source["계획기초정보여부"].eq("N")]
    blank = {int(plans[-1]): None, int(routes[-1]): "   ", int(routes[-2]): ""}

    app = _registration_app(database, blank)

    assert not app.exception
    assert not app.error
    assert "올렸습니다" in app.session_state[registration.REGISTRATION_FLASH_KEY]
    note = FlashNote(*app.session_state[registration.REGISTRATION_DROP_FLASH_KEY])
    assert note.kind == "warning"
    assert note.message.startswith(
        "CS 가 빈 행 3개(계획 1행)는 양산구분(양산·ER)을 정할 수 없어 빼고 저장했습니다."
    )
    repository = DuckDBScenarioRepository(database)
    [scenario] = repository.list_scenarios()
    snapshot = repository.load_revision(scenario.active_revision_id)
    assert snapshot.revision.note == (
        "원천 PLAN 메모 · 상세 조회기간 2026-10-19 ~ 2026-10-27 · CS 빈 행 3개(계획 1행) 뺌"
    )
    assert len(snapshot.tables["RQ_PKG_PLAN"]) == len(plans) - 1
    assert snapshot.tables["RQ_PKG_PLAN"]["양산구분"].notna().all()
    assert snapshot.tables["RQ_REQB"]["양산구분"].notna().all()
    assert repository.load_source_row_count(scenario.scenario_id) == len(source)


def test_a_source_whose_cs_is_all_blank_is_refused_instead_of_saving_an_empty_scenario(
    tmp_path: Path,
) -> None:
    from capa_simulation.persistence.repository import DuckDBScenarioRepository
    from capa_simulation.services.builtin_seed import build_builtin_seed_dataset

    database = _registration_database(tmp_path)
    source = build_builtin_seed_dataset().source_data

    app = _registration_app(database, dict.fromkeys(range(len(source))))

    assert not app.exception
    assert app.error and "CS 가 모두 비어" in app.error[0].value
    assert registration.REGISTRATION_FLASH_KEY not in app.session_state
    assert DuckDBScenarioRepository(database).list_scenarios() == []


CD_PACKAGE_MISSING_SCRIPT = """
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

import capa_simulation.settings as settings
from capa_simulation.components import bigdataquery_registration as registration
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow

REPORT = __REPORT__
if REPORT is not None:
    settings.CONTAINER_START_REPORT_PATH = Path(REPORT)
    Path(REPORT).write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-10-24T09:00:00+09:00",
                "steps": {
                    "install": {
                        "status": "skipped",
                        "reason": "CD 환경변수 CAPA_ARTIFACTORY_TOKEN 없음",
                    },
                    "token": {"status": "skipped", "reason": "CD 환경변수 CAPA_BDQ_TOKEN 없음"},
                    "user_name": {"status": "ok", "reason": "있음"},
                },
                "bigdataquery_version": None,
                "token_file": {"exists": False, "modified_at": None},
                "user_name": {"present": True, "masked": "fa***"},
                "missing_environment": ["CAPA_ARTIFACTORY_TOKEN", "CAPA_BDQ_TOKEN"],
                "pip_tail": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

saved = sys.modules.get("bigdataquery")
sys.modules["bigdataquery"] = None
try:
    registration.render_bigdataquery_registration(
        SimpleNamespace(list_scenarios=lambda **_kwargs: []), "demo.duckdb"
    )
    registration._run_catalog_query(
        QueryWindow(start_date=date(2026, 9, 21), end_date=date(2026, 10, 21))
    )
finally:
    if saved is None:
        sys.modules.pop("bigdataquery", None)
    else:
        sys.modules["bigdataquery"] = saved
"""


@pytest.mark.parametrize("with_report", [False, True], ids=["dev-or-company-pc", "cd-container"])
def test_a_missing_package_in_the_cd_container_says_which_variable_to_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_report: bool
) -> None:
    """CD 서버에는 셸이 없어 `uv pip install` 안내를 따를 수 없다. 시작 스크립트가 남긴 결과가
    있으면 목록 조회 오류와 화면 머리 경고에 설치 단계 결과와 넣을 환경변수를 덧붙이고, 없으면
    지금과 같다."""
    monkeypatch.setattr(registration, "is_bigdataquery_package_available", lambda: False)
    report = repr(str(tmp_path / "container_start.json")) if with_report else "None"
    app = AppTest.from_string(CD_PACKAGE_MISSING_SCRIPT.replace("__REPORT__", report))
    app.run(timeout=60)

    assert not app.exception
    [error] = app.error
    assert error.value.startswith("현재 환경에 bigdataquery 패키지가 없습니다.")
    banner = " ".join(warning.value for warning in app.warning)
    assert "bigdataquery 패키지가 없어" in banner
    for text in (error.value, banner):
        assert ("서버 시작 점검" in text) is with_report
        assert ("`CAPA_ARTIFACTORY_TOKEN`" in text) is with_report
