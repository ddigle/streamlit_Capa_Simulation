# Purpose: 공정 Capa 상세 진입 계약(HOME 칸 이동 꼬리·전달 칸·주소 인자·출처 띠·기본값)을 고정한다.

"""HOME 칸을 누르면 그 공정·그 달로 공정 Capa 상세가 열린다(2026-10-15 사용자 결정).

AppTest 에는 Plotly 요소가 없어 차트 클릭을 재현하지 못한다. 그래서 둘로 나눈다.

- 순수 부분 — 그림의 `customdata` 꼬리를 만들고 읽는 함수, 출처 띠 문구, 기본 공정·달.
- 세션 부분 — 콜백(`open_clicked_home_cell`)은 선택 상태를 세션에 **주입**해 단추로 부르고,
  `st.switch_page` 는 기록용 대역으로 바꾼다. 콜백은 이동 대기 칸만 적고 옮기는 것은 본문 첫 줄
  (`switch_to_queued_process_detail`)이다 — 진짜 프래그먼트 회차(`tests/fragment_browser.py`)에서
  이동이 콜백 밖인지도 본다. 클릭 시험의 앱은 그 함수를 스스로 부르는 대역이라, 실제
  `render_home_figures` 가 조기 반환보다 앞에서 부르는지는 따로 돌려 본다. AppTest 에는
  등록된 페이지가 없어 대역 없이 옮기면 갈 곳이 없다 — 실제 서버는 세션의 페이지 목록이
  회차를 넘어 남는다. 받는 쪽(`resolve_process_and_month`)은 주소 인자·전달 칸을 넣고 돌린다.
"""

from __future__ import annotations

from typing import Any

import pytest
import streamlit
from fragment_browser import install_fragment_browser
from streamlit.runtime.scriptrunner_utils.script_run_context import ThreadState
from streamlit.testing.v1 import AppTest

from capa_simulation.home_state import ADVANCE_TOGGLE_KEY, EXECUTION_TOGGLE_KEY
from capa_simulation.navigation import PROCESS_CAPA_DETAIL
from capa_simulation.process_detail_state import (
    FROM_HOME,
    HOME_CELL_LINK_FIELDS,
    HOME_KEY_PROCESS_SECTION,
    PROCESS_DETAIL_MONTH_KEY,
    PROCESS_DETAIL_ORIGIN_KEY,
    PROCESS_DETAIL_PROCESS_KEY,
    PROCESS_DETAIL_QUERY_SEEN_KEY,
    PROCESS_DETAIL_QUEUED_KEY,
    PROCESS_DETAIL_REQUEST_KEY,
    HomeCellLink,
    ProcessDetailEntry,
    ProcessDetailRequest,
    first_home_cell_link,
    first_shortfall_month,
    home_cell_link_values,
    lowest_rate_process,
    origin_band_text,
    parse_home_cell_link,
    request_query_params,
)
from capa_simulation.services.process_picker import ProcessPickerItem
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.sidebar_status import APP_RUN_STATE_KEY

HOVER = ["26.03", "DEMO-A", "103.0%", "9.8대", "10.0대", ""]


def _link_row(
    *,
    process: object = "DEMO-A",
    month: object = 202603,
    displayed_rate: object = 1.03,
    available: object = 9.8,
    required: object = 10.0,
    execution_delta: object = 5.0,
) -> list[object]:
    return [
        *HOVER,
        *home_cell_link_values(
            process=process,
            month=month,
            displayed_rate=displayed_rate,
            available=available,
            required=required,
            execution_delta=execution_delta,
        ),
    ]


# ------------------------------------------------------------------ 순수 부분


def test_the_link_tail_round_trips_through_the_selected_point() -> None:
    link = parse_home_cell_link(_link_row())

    assert link is not None
    assert link.raw_rate == pytest.approx(0.98)
    assert link == HomeCellLink(
        process="DEMO-A",
        month=202603,
        displayed_rate=1.03,
        raw_rate=link.raw_rate,
        available=9.8,
        required=10.0,
        execution_delta=5.0,
    )


def test_the_tail_is_counted_from_the_end_so_hover_columns_can_grow() -> None:
    """hover 칸 수는 그림마다 다르다(상세 B/N 은 Wafer Capa 하나가 더 있다)."""
    longer = ["26.03", "DEMO-A", "103.0%", "9.8대", "10.0대", "1K", "", *_link_row()[len(HOVER) :]]

    assert parse_home_cell_link(longer) == parse_home_cell_link(_link_row())


def test_an_unlinked_cell_and_a_broken_tail_are_ignored() -> None:
    unlinked = [
        *HOVER,
        *home_cell_link_values(
            process="DEMO-A",
            month=202603,
            displayed_rate=1.0,
            available=1.0,
            required=1.0,
            execution_delta=0.0,
            linked=False,
        ),
    ]

    assert unlinked[-len(HOME_CELL_LINK_FIELDS) :] == [None] * len(HOME_CELL_LINK_FIELDS)
    assert parse_home_cell_link(unlinked) is None
    assert parse_home_cell_link(_link_row(month=202613)) is None
    assert parse_home_cell_link(_link_row(process="  ")) is None
    assert parse_home_cell_link(HOVER) is None
    assert parse_home_cell_link("DEMO-A") is None
    assert parse_home_cell_link(None) is None


def test_missing_numbers_become_none_and_zero_demand_has_no_raw_rate() -> None:
    link = parse_home_cell_link(
        _link_row(displayed_rate=float("nan"), required=0.0, execution_delta=None)
    )

    assert link is not None
    assert link.displayed_rate is None
    assert link.raw_rate is None
    assert link.execution_delta == 0.0


def test_the_first_linked_point_of_a_selection_wins() -> None:
    """빈 선택(같은 칸 다시 누르기·더블클릭)과 공정 없는 점은 건너뛴다."""
    past = [*HOVER, *[None] * len(HOME_CELL_LINK_FIELDS)]
    state = {"selection": {"points": [{"customdata": past}, {"customdata": _link_row()}]}}

    link = first_home_cell_link(state)
    assert link is not None and link.process == "DEMO-A"
    assert first_home_cell_link({"selection": {"points": []}}) is None
    assert first_home_cell_link({"selection": {"points": [{"customdata": past}]}}) is None
    assert first_home_cell_link(None) is None
    assert first_home_cell_link({"selection": None}) is None


def test_the_address_carries_process_month_source_and_the_current_theme() -> None:
    """`st.switch_page` 는 주소를 통째로 바꾼다 — 테마 인자를 함께 싣지 않으면 지워진다."""
    request = ProcessDetailRequest(process="DEMO-A", month=202603)

    assert request_query_params(request, theme="dark") == {
        "process": "DEMO-A",
        "month": "202603",
        "from": FROM_HOME,
        "theme": "dark",
    }
    assert request_query_params(ProcessDetailRequest(process="DEMO-A", month=None), theme=None) == {
        "process": "DEMO-A",
        "from": FROM_HOME,
    }


def test_the_origin_band_explains_how_home_differs_from_the_raw_rate() -> None:
    base = ProcessDetailRequest(
        process="DEMO-A",
        month=202603,
        section=HOME_KEY_PROCESS_SECTION,
        displayed_rate=1.03,
        raw_rate=0.98,
        execution_delta=5.0,
    )

    assert origin_band_text(base, month_text="26.03") == (
        "HOME 주요공정 확보율 · 26.03 칸에서 열었습니다 · 표시 103% = 원 확보율 98% "
        "+ 확보율 보정 +5.0%p · 아래는 원 확보율"
    )
    advanced = ProcessDetailRequest(
        process="DEMO-A",
        month=202603,
        section=HOME_KEY_PROCESS_SECTION,
        displayed_rate=1.05,
        raw_rate=0.98,
        show_advance=True,
    )
    assert "표시 105% = 원 확보율 98% (선행 B/O 반영)" in origin_band_text(
        advanced, month_text="26.03"
    )
    plain = ProcessDetailRequest(
        process="DEMO-A", month=202603, section="상세 B/N 공정", displayed_rate=0.98, raw_rate=0.98
    )
    assert origin_band_text(plain, month_text="26.03") == (
        "HOME 상세 B/N 공정 · 26.03 칸에서 열었습니다 · 표시 98% = 원 확보율(아래 표와 같은 값)"
    )


def test_the_default_process_is_the_one_with_the_lowest_period_rate() -> None:
    items = (
        ProcessPickerItem("DEMO-A", 0.95, 202602, 3, "shortfall"),
        ProcessPickerItem("DEMO-B", None, None, 0, "unavailable"),
        ProcessPickerItem("DEMO-C", 0.90, 202601, 3, "shortfall"),
        ProcessPickerItem("DEMO-D", 0.90, 202603, 3, "shortfall"),
    )

    # 같은 최저값이면 목록 차례가 앞선 공정이다.
    assert lowest_rate_process(items) == "DEMO-C"
    assert lowest_rate_process(items[1:2]) == "DEMO-B"
    assert lowest_rate_process(()) is None


def test_the_default_month_is_the_first_month_below_that_months_threshold() -> None:
    """판정은 달마다 그 달의 기준이다 — 월별 예외가 높은 달은 같은 확보율도 미달이다."""
    thresholds = SecurementThresholds(1.0, 0.9, monthly=((202602, 1.2, None),))
    rates = [(202603, 0.95), (202601, 1.1), (202602, 1.1), (202604, float("nan"))]

    assert first_shortfall_month(rates, thresholds) == 202602
    assert first_shortfall_month([(202601, 1.1)], thresholds) is None


# ------------------------------------------------------------------ HOME 콜백


def _home_click_app() -> None:
    import streamlit as st

    from capa_simulation.components.home_rendering import open_clicked_home_cell
    from capa_simulation.process_detail_state import switch_to_queued_process_detail

    switch_to_queued_process_detail()
    st.button(
        "칸 누름",
        key="test_home_cell_click",
        on_click=open_clicked_home_cell,
        args=("test_home_chart", "주요공정 확보율"),
    )


@pytest.fixture
def switched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, str]]]:
    """`st.switch_page` 기록 대역. 콜백 안 이동은 실제 서버에서만 등록된 페이지를 찾는다."""
    calls: list[tuple[str, dict[str, str]]] = []

    def record(page: str, *, query_params: dict[str, str] | None = None) -> None:
        calls.append((page, dict(query_params or {})))

    monkeypatch.setattr(streamlit, "switch_page", record)
    return calls


def _clicked(selection: object, **session: object) -> AppTest:
    app = AppTest.from_function(_home_click_app)
    app.query_params["theme"] = "dark"
    for key, value in session.items():
        app.session_state[key] = value
    app.session_state["test_home_chart"] = selection
    app.run()
    app.button(key="test_home_cell_click").click().run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def test_a_cell_click_writes_the_transfer_slot_and_switches_with_the_theme(
    switched: list[tuple[str, dict[str, str]]],
) -> None:
    app = _clicked(
        {"selection": {"points": [{"customdata": _link_row()}]}},
        **{ADVANCE_TOGGLE_KEY: True, EXECUTION_TOGGLE_KEY: True},
    )

    assert switched == [
        (
            PROCESS_CAPA_DETAIL.path,
            {"process": "DEMO-A", "month": "202603", "from": "home", "theme": "dark"},
        )
    ]
    request = app.session_state[PROCESS_DETAIL_REQUEST_KEY]
    assert isinstance(request, ProcessDetailRequest)
    assert (request.process, request.month, request.section) == (
        "DEMO-A",
        202603,
        HOME_KEY_PROCESS_SECTION,
    )
    assert request.execution_delta == 5.0
    assert request.raw_rate == pytest.approx(0.98)
    # 누른 그림과 같은 보기 조건 — HOME 토글을 그대로 읽는다.
    assert (request.show_advance, request.show_execution, request.include_edp) == (
        True,
        True,
        False,
    )


@pytest.mark.parametrize(
    "selection",
    [
        {"selection": {"points": []}},
        {"selection": {"points": [{"customdata": [*HOVER, *[None] * 7]}]}},
        None,
    ],
)
def test_an_empty_or_past_cell_selection_does_nothing(
    switched: list[tuple[str, dict[str, str]]], selection: object
) -> None:
    app = _clicked(selection)

    assert switched == []
    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state


def test_a_click_that_cannot_switch_leaves_no_transfer_slot() -> None:
    """갈 곳이 없으면(내비게이션 없는 실행) 화면을 오류로 멈추지 않고, 적은 전달 칸도 거둔다 —
    남기면 나중에 사이드바로 들어온 방문이 이 클릭의 출처 띠를 단다."""
    app = _clicked({"selection": {"points": [{"customdata": _link_row()}]}})

    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state


def _home_fragment_click_app() -> None:
    import streamlit as st

    from capa_simulation.components.home_rendering import open_clicked_home_cell
    from capa_simulation.process_detail_state import (
        HOME_KEY_PROCESS_SECTION,
        switch_to_queued_process_detail,
    )

    @st.fragment
    def figures() -> None:
        switch_to_queued_process_detail()
        st.button(
            "칸 누름",
            key="test_home_cell_click",
            on_click=open_clicked_home_cell,
            args=("test_home_chart", HOME_KEY_PROCESS_SECTION),
        )

    figures()


def test_a_cell_click_in_the_home_fragment_switches_outside_the_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamlit 1.63 의 `st.switch_page` 는 끝에 `st.empty()` 를 그려, 프래그먼트 콜백 안에서
    부르면 「A fragment rerun was triggered with a callback that displays one or more elements」
    경고를 남긴다(사내 리뷰 202610182227 — 칸을 누를 때마다 한 줄). 진짜 프래그먼트 회차에서
    콜백은 대기 칸만 적고, 이동은 같은 회차의 프래그먼트 본문에서 일어난다."""
    runner = install_fragment_browser(monkeypatch)
    in_callback: list[bool] = []

    def record(page: str, *, query_params: dict[str, str] | None = None) -> None:
        in_callback.append(ThreadState.get().in_fragment_callback)

    monkeypatch.setattr(streamlit, "switch_page", record)
    app = AppTest.from_function(_home_fragment_click_app)
    app.session_state["test_home_chart"] = {"selection": {"points": [{"customdata": _link_row()}]}}
    app.run()
    assert in_callback == []
    fragment = runner.fragment_of("test_home_cell_click")

    runner.fragment_queue = [fragment]
    app.button(key="test_home_cell_click").click().run()

    assert not app.exception, [element.message for element in app.exception]
    assert runner.started == [[fragment]]
    assert in_callback == [False]
    assert PROCESS_DETAIL_QUEUED_KEY not in app.session_state
    assert app.session_state[PROCESS_DETAIL_REQUEST_KEY].process == "DEMO-A"


def _real_home_figures_app() -> None:
    from capa_simulation.components.home_rendering import render_home_figures

    # 그림 없음(None)은 Main 이 숨은 회차의 조기 반환 갈래다.
    render_home_figures(None, [])


def test_the_real_home_figures_fragment_switches_a_queued_cell_before_its_early_return(
    switched: list[tuple[str, dict[str, str]]],
) -> None:
    """위 대역 앱들은 이동 함수를 스스로 부른다. 실제 HOME 프래그먼트(`render_home_figures`)가
    본문 첫 줄에서, 숨은 탭·그림 없음 조기 반환보다 **앞에서** 대기 칸을 꺼내 옮기는지는 여기서
    지킨다 — 빠지거나 반환 뒤로 밀리면 칸 클릭이 아무 일도 하지 않고 대기 칸이 남는다."""
    request = ProcessDetailRequest(process="DEMO-A", month=202603)
    app = AppTest.from_function(_real_home_figures_app)
    app.query_params["theme"] = "dark"
    app.session_state[PROCESS_DETAIL_QUEUED_KEY] = request
    app.run(timeout=30)

    assert not app.exception, [element.message for element in app.exception]
    assert switched == [(PROCESS_CAPA_DETAIL.path, request_query_params(request, theme="dark"))]
    assert PROCESS_DETAIL_QUEUED_KEY not in app.session_state
    assert app.session_state[PROCESS_DETAIL_REQUEST_KEY] == request

    # 대기 칸은 한 번만 꺼낸다 — 다음 회차는 다시 옮기지 않는다.
    app.run()
    assert switched == [(PROCESS_CAPA_DETAIL.path, request_query_params(request, theme="dark"))]


def _take_app() -> None:
    import streamlit as st

    from capa_simulation.process_detail_state import take_process_detail_request

    st.session_state["test_taken"] = take_process_detail_request()


def test_taking_the_transfer_slot_empties_it_and_drops_a_foreign_value() -> None:
    app = AppTest.from_function(_take_app)
    request = ProcessDetailRequest(process="DEMO-A", month=202603)
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = request
    app.run()
    assert app.session_state["test_taken"] == request
    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state

    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = {"process": "DEMO-A"}
    app.run()
    assert app.session_state["test_taken"] is None
    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state


# ------------------------------------------------------------------ 받는 쪽


def _detail_entry_app() -> None:
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    from capa_simulation.process_detail_state import (
        PROCESS_DETAIL_PROCESS_KEY,
        resolve_process_and_month,
        take_process_detail_request,
    )

    def default_process() -> str:
        # 기본 공정 요약은 비싸다 — 필요한 회차에만 불리는지 센다.
        st.session_state["test_default_calls"] = st.session_state.get("test_default_calls", 0) + 1
        return "DEMO-B"

    entry = resolve_process_and_month(
        ["DEMO-A", "DEMO-B", "DEMO-C"],
        [202601, 202602, 202603],
        request=take_process_detail_request(),
        default_process=default_process,
        default_month=lambda process: {"DEMO-A": 202602, "DEMO-C": 202603}.get(process or ""),
    )
    st.session_state["test_entry"] = entry
    ctx = get_script_run_ctx()
    st.session_state["test_page_hash"] = None if ctx is None else ctx.page_script_hash
    st.selectbox(
        "공정",
        ["DEMO-A", "DEMO-B", "DEMO-C"],
        key=PROCESS_DETAIL_PROCESS_KEY,
        persist_state="session",
    )


def _entry(app: AppTest) -> ProcessDetailEntry:
    entry = app.session_state["test_entry"]
    assert isinstance(entry, ProcessDetailEntry)
    return entry


def _query(app: AppTest) -> dict[str, Any]:
    return dict(app.query_params)


def test_a_fresh_visit_opens_the_default_process_and_its_default_month() -> None:
    app = AppTest.from_function(_detail_entry_app).run()

    assert not app.exception
    assert (_entry(app).process, _entry(app).month) == ("DEMO-B", 202601)
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == "DEMO-B"


def test_the_default_process_is_computed_only_when_nothing_else_chose_one() -> None:
    """기본 공정(공정별 요약·달마다 판정)은 세션·전달 칸·주소로 공정이 정해진 회차에 만들지
    않는다."""
    app = AppTest.from_function(_detail_entry_app).run()
    assert app.session_state["test_default_calls"] == 1

    app.run()
    app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).set_value("DEMO-A").run()
    app.query_params.update({"process": "DEMO-C"})
    app.run()
    assert _entry(app).process == "DEMO-C"
    assert app.session_state["test_default_calls"] == 1

    # 넘겨받은 공정이 목록에 없으면 그때 기본 공정을 낸다.
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-GONE", month=None
    )
    app.run()
    assert _entry(app).process == "DEMO-B"
    assert app.session_state["test_default_calls"] == 2


def test_the_address_opens_its_process_and_month_once_and_only_its_keys_are_removed() -> None:
    app = AppTest.from_function(_detail_entry_app)
    app.query_params.update({"process": "DEMO-C", "month": "202602", "from": "home"})
    app.query_params["theme"] = "dark"
    app.run()

    assert not app.exception
    assert (_entry(app).process, _entry(app).month) == ("DEMO-C", 202602)
    assert app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).value == "DEMO-C"
    # `clear()` 가 아니다 — 테마 인자는 남는다.
    assert _query(app) == {"theme": ["dark"]}
    assert app.session_state[PROCESS_DETAIL_QUERY_SEEN_KEY] == (
        ("process", "DEMO-C"),
        ("month", "202602"),
        ("from", "home"),
    )

    # 사용자가 고른 뒤 브라우저가 옛 주소를 되보내도 덮지 않는다.
    app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).set_value("DEMO-A")
    app.query_params.update({"process": "DEMO-C", "month": "202602", "from": "home"})
    app.run()
    assert _entry(app).process == "DEMO-A"
    assert "process" not in _query(app)


def test_the_same_link_applies_again_after_the_address_was_cleared() -> None:
    """옛 주소가 되돌아오는 것만 막는다. 인자가 걷힌 뒤 같은 링크로 다시 오면 다시 연다."""
    app = AppTest.from_function(_detail_entry_app)
    app.query_params.update({"process": "DEMO-C"})
    app.run()
    app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).set_value("DEMO-A")
    app.run()
    assert _entry(app).process == "DEMO-A"
    assert PROCESS_DETAIL_QUERY_SEEN_KEY not in app.session_state

    app.query_params.update({"process": "DEMO-C"})
    app.run()
    assert _entry(app).process == "DEMO-C"


def test_an_address_process_without_a_month_opens_that_process_default_month() -> None:
    app = AppTest.from_function(_detail_entry_app).run()
    app.query_params.update({"process": "DEMO-A"})
    app.run()

    assert (_entry(app).process, _entry(app).month) == ("DEMO-A", 202602)


def test_the_transfer_slot_wins_is_consumed_and_starts_the_origin_band() -> None:
    app = AppTest.from_function(_detail_entry_app).run()
    request = ProcessDetailRequest(
        process="DEMO-C", month=202603, section=HOME_KEY_PROCESS_SECTION, displayed_rate=1.0
    )
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = request
    # HOME 콜백이 함께 바꾼 주소 — 전달 칸과 같은 값이라 다시 적용하지 않고 지우기만 한다.
    app.query_params.update({"process": "DEMO-C", "month": "202603", "from": "home"})
    app.run()

    entry = _entry(app)
    assert (entry.process, entry.month, entry.origin) == ("DEMO-C", 202603, request)
    assert PROCESS_DETAIL_REQUEST_KEY not in app.session_state
    assert "process" not in _query(app)
    assert app.session_state[PROCESS_DETAIL_MONTH_KEY] == 202603


def test_the_origin_band_lasts_for_the_visit_and_the_process() -> None:
    """같은 화면에서 다시 도는 동안은 남고, 공정을 바꾸거나 새로 들어오면 걷힌다."""
    app = AppTest.from_function(_detail_entry_app).run()
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-C", month=202603
    )
    app.run()
    assert _entry(app).origin is not None

    # 직전에 끝까지 돈 실행이 이 페이지였다 — `app.py` 의 실행 표지를 흉내 낸다.
    app.session_state[APP_RUN_STATE_KEY] = {"page": app.session_state["test_page_hash"]}
    app.run()
    assert _entry(app).origin is not None

    app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).set_value("DEMO-A")
    app.run()
    assert _entry(app).origin is None
    assert PROCESS_DETAIL_ORIGIN_KEY not in app.session_state


def test_a_new_visit_drops_the_origin_band() -> None:
    app = AppTest.from_function(_detail_entry_app).run()
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-C", month=202603
    )
    app.run()
    app.session_state[APP_RUN_STATE_KEY] = {"page": "다른 화면"}
    app.run()

    assert _entry(app).origin is None
    assert _entry(app).process == "DEMO-C"


def test_a_missing_process_or_an_outside_month_falls_back_and_says_so() -> None:
    app = AppTest.from_function(_detail_entry_app).run()
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-GONE", month=202603
    )
    app.run()
    assert (_entry(app).process, _entry(app).missing_process) == ("DEMO-B", "DEMO-GONE")

    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-A", month=202512
    )
    app.run()
    entry = _entry(app)
    assert (entry.process, entry.month, entry.month_outside) == ("DEMO-A", 202602, 202512)


def test_the_session_month_survives_a_rerun() -> None:
    app = AppTest.from_function(_detail_entry_app).run()
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = 202603
    app.run()

    assert _entry(app).month == 202603


def test_changing_the_process_keeps_the_month_being_viewed() -> None:
    """공정을 바꿔도 보던 달은 그대로다 — 새 공정의 첫 미달 달로 옮기지 않는다(Guide 와 같은 말)."""
    app = AppTest.from_function(_detail_entry_app).run()
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = 202603
    app.run()
    app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).set_value("DEMO-A").run()

    assert (_entry(app).process, _entry(app).month) == ("DEMO-A", 202603)


def test_the_scroll_start_stays_while_the_viewed_month_moves() -> None:
    """스크롤 시작 달은 새 방문·밖에서 들어옴·공정을 바꾼 회차에만 다시 정한다 — 칸을 눌러 달을
    옮긴 뒤 다른 조건으로 앱 전체가 돌아도 그대로라 보던 가로 위치를 그 달로 되돌리지 않는다."""
    app = AppTest.from_function(_detail_entry_app).run()
    assert _entry(app).scroll_month == 202601
    app.session_state[APP_RUN_STATE_KEY] = {"page": app.session_state["test_page_hash"]}

    # 칸 누름(프래그먼트 콜백)이 세션 달만 옮긴 뒤의 앱 전체 회차.
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = 202603
    app.run()
    assert (_entry(app).month, _entry(app).scroll_month) == (202603, 202601)

    # 공정을 바꾸면 그 회차의 달로 다시 정한다.
    app.selectbox(key=PROCESS_DETAIL_PROCESS_KEY).set_value("DEMO-A").run()
    assert (_entry(app).month, _entry(app).scroll_month) == (202603, 202603)

    # 밖에서 들어오면(전달 칸) 넘겨받은 달이다.
    app.session_state[PROCESS_DETAIL_REQUEST_KEY] = ProcessDetailRequest(
        process="DEMO-A", month=202602
    )
    app.run()
    assert _entry(app).scroll_month == 202602

    # 다른 화면에 다녀오면 새 방문 — 지금 달로 다시 정한다.
    app.session_state[PROCESS_DETAIL_MONTH_KEY] = 202603
    app.session_state[APP_RUN_STATE_KEY] = {"page": "다른 화면"}
    app.run()
    assert _entry(app).scroll_month == 202603
