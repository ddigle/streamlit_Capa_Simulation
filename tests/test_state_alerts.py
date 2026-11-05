# Purpose: 화면 상태 알림 조각(범위·딸린 표·화면 오류 표지)과 2단계 a 자리들의 표지 꼴을 시험한다.

"""알림 체계 2단계 a(2026-11-03 결정 보드 D2 (나)) — `components/state_alerts.py` 와 그 조각을 쓰는
자리 가운데 화면 시험이 따로 보지 않는 것(측정률 가정 · 줄 차례 비움 · DB 새 판)을 본다. 화면 자리는
각 화면 시험(`test_calculation_result_tabs` · `test_static_capa_layout` · `test_home_page` …)이
본다."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from alert_marks import alert_notes
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.components import state_alerts
from capa_simulation.components.process_labels import ProcessLabels


def test_an_alert_table_carries_json_values_and_display_names_only_for_the_screen() -> None:
    """딸린 표는 JSON 값(NaN → 빈칸, numpy 수 → 파이썬 수)이고 공정 표시명은 `shown` 에만 — 행 값은
    원본이라 CSV 가 원본이다."""
    frame = pd.DataFrame(
        {
            "공정": ["DEMO-P1", "DEMO-P2"],
            "STEP_SEQ": ["P100", "P200"],
            "UPEH": [np.float64(0.0), np.nan],
            "MCP_SEQ": [np.int64(1), np.int64(2)],
        }
    )
    labels = ProcessLabels(version=1, labels={"DEMO-P1": "가공"})
    table = state_alerts.alert_table(frame, title="제외 기준정보", file_name="x.csv", labels=labels)
    assert table is not None
    assert table["columns"] == ["공정", "STEP_SEQ", "UPEH", "MCP_SEQ"]
    assert table["rows"] == [["DEMO-P1", "P100", 0.0, 1], ["DEMO-P2", "P200", None, 2]]
    assert table["shown"] == {"공정": {"DEMO-P1": "가공"}}
    assert (table["title"], table["file"], table["total"]) == ("제외 기준정보", "x.csv", 2)
    assert state_alerts.alert_table(frame, title="t", file_name="f")["shown"] == {}  # type: ignore[index]


def test_an_alert_table_carries_header_tips_only_for_its_own_columns() -> None:
    """칸 머리 풍선은 그 표에 있는 칸에만 싣는다 — 없는 칸의 글은 뺀다(표시명이 없을 때 등)."""
    frame = pd.DataFrame({"공정": ["DEMO-P1"], "제외사유": ["규칙"]})
    table = state_alerts.alert_table(
        frame,
        title="t",
        file_name="f.csv",
        column_help={"제외사유": "고칠 곳", "없는 칸": "뺀다"},
    )
    assert table is not None and table["help"] == {"제외사유": "고칠 곳"}


def test_a_table_too_large_for_the_alarm_is_left_on_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`alerts.TABLE_ROW_LIMIT` 를 넘는 표는 None — 화면이 본문 목록을 남긴다(탭 저장소 크기)."""
    monkeypatch.setattr(alerts, "TABLE_ROW_LIMIT", 1)
    frame = pd.DataFrame({"공정": ["A", "B"]})
    assert state_alerts.alert_table(frame, title="t", file_name="f.csv") is None


SCOPE = """
import streamlit as st

from capa_simulation.components.state_alerts import simulation_scope
from datetime import date

active = {"content_token": st.session_state.get("token", "pristine-7"), "tables": {}}
st.session_state["full"] = simulation_scope(active)
st.session_state["period"] = simulation_scope(active, (202601, 202612))
st.session_state["dates"] = simulation_scope(active, dates=(date(2026, 1, 5), date(2026, 2, 1)))
"""


def test_the_simulation_scope_is_the_content_token_and_the_period_it_looks_at() -> None:
    """범위 = 활성 리비전 내용 토큰(+ 조회기간 · 조회일). 범위 줄은 기간 말을 붙이고, 저장하지 않은
    편집이 든 토큰이면 그 말을 붙인다."""
    app = AppTest.from_string(SCOPE).run()
    assert not app.exception
    full, period, dates = (app.session_state[name] for name in ("full", "period", "dates"))
    assert full.scope == {"token": "pristine-7"} and full.label == "시나리오 전체 기간"
    assert period.scope == {"token": "pristine-7", "period": [202601, 202612]}
    assert period.label == "26.01–26.12"
    assert dates.scope == {"token": "pristine-7", "dates": ["2026-01-05", "2026-02-01"]}
    assert dates.label == "26.01.05–26.02.01"

    app.session_state["token"] = "0f3c"
    app.run()
    assert app.session_state["period"].label == "미저장 편집 · 26.01–26.12"


PAGE_ERROR = """
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.state_alerts import alert_page_error

alerts.note_page("산출 결과", "calculation_result")
message = st.session_state.get("message", "데이터베이스를 열지 못했습니다.\\n\\n- 원문: lock")
st.error(message)
alert_page_error(message, code="ST-20", tab="소요대수")
"""


def test_a_page_error_alerts_once_per_message_and_stays_in_place() -> None:
    """화면을 그리지 못한 오류는 자리 `st.error` 그대로 + 사건 알림 하나(오류 단계). id 가 글의
    지문이라 회차마다 다시 그려도 같은 글이면 브라우저가 한 번만 띄운다. 알림창 짧은 글은 첫
    문단이다."""
    app = AppTest.from_string(PAGE_ERROR).run()
    assert not app.exception and len(app.error) == 1
    (first,) = alert_notes(app)
    assert (first["code"], first["kind"], first["level"]) == ("ST-20", "event", "error")
    assert first["short"] == "데이터베이스를 열지 못했습니다."
    assert first["full"] == "데이터베이스를 열지 못했습니다. - 원문: lock"
    assert (first["page"], first["tab"]) == ("산출 결과", "소요대수")

    app.run()
    (again,) = alert_notes(app)
    assert again["id"] == first["id"]

    app.session_state["message"] = "계산을 멈췄습니다."
    app.run()
    (other,) = alert_notes(app)
    assert other["id"] != first["id"]


ASSUMPTION = """
import streamlit as st

from capa_simulation.components.capacity_assumption_notice import (
    render_capacity_assumption_notice,
)
from capa_simulation.components.state_alerts import AlertScope
from capa_simulation.services.unit_capacity import CapacityAssumptions

counts = st.session_state.get("counts", {"RQ_LOT_RATIO": 3, "RQ_WF_RATIO": 0})
render_capacity_assumption_notice(
    CapacityAssumptions(counts=counts, months={"RQ_LOT_RATIO": (202601, 202602)}),
    scope=AlertScope({"token": "t1"}, "DEMO · r1 · 시나리오 전체 기간"),
    tab="대당 Capa",
)
"""


def test_the_ratio_assumption_is_a_state_alert_with_where_to_fix_it() -> None:
    """측정률 가정(`HM-02`)은 자리에 그리지 않는다 — 짧은 글이 무엇을(표 · 건수) 어디서(기준 정보)
    고치는지 말하고, 가정이 없으면 「없음」 표지(해소)다."""
    app = AppTest.from_string(ASSUMPTION).run()
    assert not app.exception and not app.warning
    (note,) = alert_notes(app)
    assert (note["code"], note["active"], note["tab"]) == ("HM-02", True, "대당 Capa")
    assert (
        note["short"] == "측정률 빈 경로를 1.0 으로 계산(Lot측정률 3건) — 기준 정보 그 표에서 채움"
    )
    assert "2026-01, 2026-02" in note["full"] and "**" not in note["full"]

    app.session_state["counts"] = {}
    app.run()
    (quiet,) = alert_notes(app)
    assert quiet["active"] is False and quiet["scope"] == note["scope"]


ROW_ORDER = """
import streamlit as st

from capa_simulation.components.scenario_edit_bar import SourceReset, show_row_order_reset

dropped = tuple(st.session_state.get("dropped", ()))
show_row_order_reset(SourceReset(changed=bool(dropped), row_order_dropped=dropped))
st.button("뒤", key="after")
"""


def test_a_row_order_reset_is_an_event_alert_and_writes_one_event_slot_every_run() -> None:
    """줄 차례가 바뀌어 편집을 버린 회차는 사건 알림 `ST-09`(조치 필요)로 한 번 알리고, 자리에는
    그리지 않는다. 버린 것이 없는 회차도 이벤트 칸 한 자리(빈 스타일)를 쓴다."""
    app = AppTest.from_string(ROW_ORDER).run()
    assert not app.exception
    assert [str(element.proto.body) for element in app.get("html")] == ["<style></style>"]

    app.session_state["dropped"] = ("PKG PLAN",)
    app.run()
    assert not app.warning and len(app.get("html")) == 1
    (note,) = alert_notes(app)
    assert (note["code"], note["kind"], note["level"]) == ("ST-09", "event", "action")
    assert "(PKG PLAN)" in note["full"] and note["short"].endswith("다시 입력")


SCHEMA = """
import streamlit as st

from capa_simulation.page_bootstrap import (
    SCHEMA_AHEAD_SIMULATION_CODE,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.migration_runner import SchemaAheadOfCode

ahead = st.session_state.get("ahead", True)
notice = SchemaAheadOfCode("시뮬레이션 DB", 99, 41) if ahead else None
render_schema_ahead_warning(notice, code=SCHEMA_AHEAD_SIMULATION_CODE)
render_schema_ahead_warning(SchemaAheadOfCode("설비 DB", 50, 33) if ahead else None)
"""


def test_a_database_ahead_of_the_code_is_a_state_alert_per_database() -> None:
    """DB 새 판은 DB 마다 코드가 따로다(`GL-02` 시뮬레이션 · `GL-06` 설비 — 한 코드면 화면을 옮길
    때마다 지문이 바뀐다). 자리에는 그리지 않고, 새 판이 아니면 「없음」 표지다."""
    app = AppTest.from_string(SCHEMA).run()
    assert not app.exception and not app.warning
    simulation, equipment = alert_notes(app)
    assert (simulation["code"], equipment["code"]) == ("GL-02", "GL-06")
    assert simulation["active"] and equipment["active"]
    assert (
        simulation["short"]
        == "시뮬레이션 DB가 코드보다 새 버전(DB 99 · 코드 41) — 최신 배포를 다시 적용"
    )
    assert equipment["full"].startswith("설비 DB가 이 코드보다 새 버전입니다(DB 50 · 코드 33)")

    app.session_state["ahead"] = False
    app.run()
    assert [note["active"] for note in alert_notes(app)] == [False, False]


def test_the_area_a_codes_are_registered_with_their_kinds() -> None:
    """2단계 a 의 코드 — 상태(바뀔 때만) · 사건(한 번)이 맞게 등록됐다."""
    states = {"ST-01", "ST-04", "ST-05", "ST-06", "ST-14", "ST-15", "ST-17", "ST-21", "HM-02"}
    states |= {"HM-04", "SB-19", "SB-20", "GL-02", "GL-06"}
    events = {"ST-09", "ST-20", "HM-01", "SB-14"}
    assert {code for code in states if alerts.spec(code).kind == "state"} == states
    assert {code for code in events if alerts.spec(code).kind == "event"} == events
    assert alerts.spec("ST-21").level == "info"
    assert {alerts.spec(code).level for code in ("ST-20", "HM-01")} == {"error"}
