# Purpose: 접속 · 작업 기록 탭의 표 꼴과 감사 알림 두 자리(AD-12 · AD-13)를 지킨다.

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from alert_marks import states
from sso_support import use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.audit import events, recorder, shipper, spool
from capa_simulation.audit.boot import grader
from capa_simulation.auth import runtime
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import audit_log_view as view
from capa_simulation.components import sso_identity

TODAY = date(2026, 11, 13)


def _line(ts: str, ev: str, actor: str = "demo.user", **extra: Any) -> dict[str, Any]:
    spec = {
        "authn_login_success": ("access", "success"),
        "session_created": ("access", "success"),
        "authn_login_fail": ("access", "fail"),
        "authz_fail_access_list": ("access", "denied"),
        "data_scenario_delete": ("data", "success"),
        "data_voc_delete": ("data", "success"),
        "data_official_publish": ("data", "success"),
        "user_created": ("admin", "success"),
    }[ev]
    line = {"ts": ts, "ev": ev, "cat": spec[0], "out": spec[1], "actor": actor, "verified": True}
    line.update(extra)
    return line


LINES = [
    _line("2026-11-11T01:00:00.000Z", "session_created"),
    _line("2026-11-13T00:10:00.000Z", "authn_login_success", name="데모 사용자", sid8="abcd1234"),
    _line("2026-11-13T00:11:00.000Z", "authn_login_fail", "demo.other", det={"reason": "nonce"}),
    _line("2026-11-13T00:12:00.000Z", "authz_fail_access_list", "demo.outsider"),
    _line(
        "2026-11-13T00:20:00.000Z",
        "data_scenario_delete",
        tgt={"type": "scenario", "id": "s-1", "label": "데모 시나리오"},
    ),
    _line("2026-11-13T00:30:00.000Z", "data_official_publish", det={"release_no": 4}),
    _line("2026-11-13T00:40:00.000Z", "user_created", tgt={"type": "loginid", "id": "demo.new"}),
]


def test_the_summary_has_a_blank_row_for_a_day_without_records() -> None:
    frame = view.summary_table(LINES, date(2026, 11, 11), TODAY)

    assert list(frame["날짜"]) == ["2026-11-13", "2026-11-12", "2026-11-11"]
    today = frame.iloc[0]
    assert (today["접속자"], today["로그인"], today["실패"], today["명단 밖"]) == (1, 1, 1, 1)
    assert (today["작업"], today["공식 발행"], today["삭제"], today["관리"]) == (2, 1, 1, 1)
    assert frame.iloc[1].iloc[1:].isna().all(), "조건에 맞는 줄이 없는 날은 0 이 아니라 빈칸"
    assert frame.iloc[2]["접속자"] == 1


def test_a_delete_that_found_nothing_is_not_counted_as_a_delete() -> None:
    lines = [
        _line("2026-11-13T00:20:00.000Z", "data_voc_delete", det={"deleted": False}),
        _line("2026-11-13T00:21:00.000Z", "data_voc_delete", det={"deleted": True}),
        _line("2026-11-13T00:22:00.000Z", "data_scenario_delete"),
    ]

    today = view.summary_table(lines, TODAY, TODAY).iloc[0]

    assert (today["삭제"], today["작업"]) == (2, 3)


def test_today_values_are_the_four_value_cells() -> None:
    assert view.today_values(LINES, TODAY) == (1, 1, 1, 2)
    assert view.today_values(LINES, date(2026, 11, 12)) is None, (
        "줄이 없는 날은 0 이 아니라 값 없음"
    )


def _summary_round(lines: str, start: str, end: str, today: str) -> None:
    """요약 보기 한 회차 — 인자는 글로 받는다(시험 회차 스크립트에는 이 파일의 import 가 없다)."""
    import json
    from datetime import date

    from capa_simulation.components import audit_log_view

    conditions = audit_log_view.LogConditions(date.fromisoformat(start), date.fromisoformat(end))
    audit_log_view.render_audit_log(conditions, json.loads(lines), date.fromisoformat(today))


def _today_cells(start: date, end: date) -> dict[str, str]:
    args = (json.dumps(LINES), start.isoformat(), end.isoformat(), TODAY.isoformat())
    app = AppTest.from_function(_summary_round, args=args).run()
    assert not list(app.exception), [element.message for element in app.exception]
    return {str(metric.label): str(metric.value) for metric in app.main.metric}


def test_a_period_without_today_shows_no_zero_in_the_today_cells() -> None:
    """월간 점검처럼 오늘이 빠진 기간 — 오늘 줄을 읽지 않았으니 0 이 아니라 「—」(UI-DAT-06)."""
    assert _today_cells(date(2026, 11, 7), date(2026, 11, 12)) == dict.fromkeys(
        view.TODAY_LABELS, view.EMPTY_VALUE
    )
    assert _today_cells(date(2026, 11, 7), TODAY) == {
        "오늘 접속자": "1",
        "로그인 실패": "1",
        "명단 밖": "1",
        "작업": "2",
    }


def test_every_detail_key_has_a_korean_label_and_flags_read_in_korean() -> None:
    keys = {key for spec in events.SPECS for key in spec.det_keys} | {"trunc"}

    assert sorted(keys - set(events.DET_LABELS)) == []
    assert all(
        any("가" <= ch <= "힣" for ch in events.DET_LABELS[key])
        for key in keys
        if key != "datasets"
    )
    login = _line(
        "2026-11-13T00:10:00.000Z", "authn_login_success", det={"hours": 12, "max_hours": 12}
    )
    profile = _line(
        "2026-11-13T00:11:00.000Z",
        "data_scenario_delete",
        det={"profile": "display_order", "version_to": 4, "source": "web", "trunc": True},
    )
    voc = _line("2026-11-13T00:12:00.000Z", "data_voc_delete", det={"deleted": False})

    assert view.detail_text(login) == "유지(시간) 12 · 최대 유지(시간) 12"
    assert view.detail_text(profile) == "설정 display_order · 판 4 · 출처 web · 줄임 예"
    assert view.detail_text(voc) == "지움 아니오"


def test_the_record_table_is_newest_first_with_names_targets_and_details() -> None:
    frame = view.record_table(LINES, view.people_names(LINES))

    assert list(frame.columns) == list(view.RECORD_COLUMNS)
    assert frame.iloc[0]["사건"] == "명단 추가"
    assert frame.iloc[-1]["시각(KST)"] == "2026-11-11 10:00:00"
    delete = frame[frame["사건"] == "시나리오 삭제"].iloc[0]
    assert delete["대상"] == "데모 시나리오 (s-1)"
    assert delete["사람"] == "demo.user · 데모 사용자"
    assert frame[frame["사건"] == "로그인 실패"].iloc[0]["상세"] == "사유 nonce"
    assert frame[frame["사건"] == "로그인"].iloc[0]["세션"] == "abcd1234"


def test_conditions_filter_people_categories_and_outcomes() -> None:
    every = view.LogConditions(TODAY, TODAY)
    only = view.LogConditions(TODAY, TODAY, ("demo.other",), ("access",), ("fail",))

    assert len(view.filtered(LINES, every)) == len(LINES)
    assert [line["ev"] for line in view.filtered(LINES, only)] == ["authn_login_fail"]
    assert view.range_text(1284, date(2026, 11, 7), TODAY) == "1,284건 · 11.07–11.13"


ALERT_SCRIPT = """
from capa_simulation.components.sso_status import render_audit_alerts

render_audit_alerts()
render_audit_alerts()
"""


@pytest.fixture()
def cookies(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    jar: dict[str, str] = {}
    monkeypatch.setattr(sso_identity, "session_cookies", lambda: jar)
    yield jar


def test_an_off_server_writes_no_audit_alert(cookies: dict[str, str]) -> None:
    app = AppTest.from_string(ALERT_SCRIPT).run()

    assert not states(app, "AD-12") and not states(app, "AD-13")


@pytest.mark.parametrize(("loginid", "active"), [("dev.user", True), ("other.user", False)])
def test_an_on_server_writes_both_codes_every_call_and_raises_them_for_viewers(
    cookies: dict[str, str], tmp_path: Path, loginid: str, active: bool
) -> None:
    cfg = use_config()
    runtime.mark_gate_installed()
    spool.configure(tmp_path)
    recorder.start(env="cdep", version="test", inst="efefefefefef")
    recorder.set_grader(grader(cfg))
    token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    cookies[cfg.session_cookie] = token

    app = AppTest.from_string(ALERT_SCRIPT).run()

    keeping = states(app, "AD-12")
    late = states(app, "AD-13")
    assert len(keeping) == len(late) == 2, "부를 때마다 두 자리 — 갈래 없이"
    # 개발 실행은 managed 가 아니라 「동기화 아님」 이 늘 선다(관리자 · 점검자만).
    assert [item["active"] for item in keeping] == [active, active]
    assert [item["active"] for item in late] == [False, False]
    shipper.reset()
