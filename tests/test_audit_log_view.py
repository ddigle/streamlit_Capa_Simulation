# Purpose: 접속 · 작업 기록 탭의 표 꼴과 감사 알림 두 자리(AD-12 · AD-13)를 지킨다.

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from alert_marks import GOTO_PRELUDE, GOTO_PRESS_KEY, active_state, box_expanded, states
from sso_support import use_config
from streamlit.testing.v1 import AppTest

from capa_simulation.audit import events, recorder, shipper, spool
from capa_simulation.audit.boot import grader
from capa_simulation.auth import runtime
from capa_simulation.auth.tokens import issue_session
from capa_simulation.components import audit_log_view as view
from capa_simulation.components import sso_identity
from capa_simulation.navigation import ADMIN_AREA, ADMIN_AREA_LOG_TAB
from capa_simulation.page_tabs_state import tab_label

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


@pytest.mark.parametrize(
    ("det", "shown"),
    [
        ({"rev_from": 1, "rev_to": 2}, "판 전 1 · 판 2"),
        ({"rev_from": 1, "rev_to": 1}, "판 1(그대로)"),
        (
            {"grade_from": "user", "grade_to": "admin", "rev_from": 3, "rev_to": 3},
            "등급 전 user · 등급 admin · 판 3(그대로)",
        ),
        ({"count": 2, "rev_from": 4, "rev_to": 5}, "수 2 · 판 전 4 · 판 5"),
        ({"rev_from": 4}, "판 전 4"),
        ({"version_from": 3, "version_to": 3}, "판 전 3 · 판 3"),
    ],
)
def test_a_failed_list_line_reads_as_the_same_revision(det: dict[str, Any], shown: str) -> None:
    """명단 판(`rev_*`)이 전 = 후인 줄(쓰지 못한 실패)은 「판 n(그대로)」 한 칸이다 — 판이 오른
    것처럼 읽히지 않게. 오른 줄 · 다른 판 칸(`version_*`)은 그대로 둘 다 보인다."""
    line = _line("2026-11-13T00:13:00.000Z", "user_created", det=det)

    assert view.detail_text(line) == shown


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


RECORDS_SCRIPT = """
from datetime import date

from capa_simulation.components import audit_log_view as view

line = {
    "ts": "2026-11-13T00:13:00.000Z",
    "ev": "user_grade_changed",
    "cat": "admin",
    "out": "fail",
    "actor": "demo.admin",
    "verified": True,
    "tgt": {"type": "loginid", "id": "demo.admin"},
    "det": {"grade_from": "admin", "grade_to": "user", "rev_from": 5, "rev_to": 5},
}
session = {
    "ts": "2026-11-13T00:12:00.000Z",
    "ev": "session_created",
    "cat": "access",
    "out": "success",
    "actor": "demo.admin",
    "verified": True,
    "sid8": "ODjEMVcn",
}
day = date(2026, 11, 13)
view.render_audit_log(view.LogConditions(day, day), [session, line], day)
"""


def test_the_record_view_gives_the_detail_and_session_columns_a_width() -> None:
    """기록 표의 상세 · 세션 칸은 자동 폭이 아니라 정한 px 이다(E2E C5-F1). 자동 폭은 앞 줄 몇
    개만 재고 평균의 두 배가 넘는 글을 빼서, 빈 칸이 많은 상세 칸의 긴 글 한 줄(끝의
    「판 n(그대로)」 표지)이 창 1283 에서 잘렸다. 상세를 넓히면 남는 폭 몫이 줄어 세션 칸이 8자
    세션 글보다 좁아지므로 함께 정한다. 대상 칸은 일부러 자동 폭이다 — 정한 폭은 상한이기도 해서
    작업 줄만 있는 표의 「이름 (id)」 를 자른다(E2E 흉내 1283: 자동 344 → 84 로 정하면 91)."""
    app = AppTest.from_string(RECORDS_SCRIPT).run()
    app.session_state[view.VIEW_KEY] = view.VIEW_RECORDS
    app.run()

    assert not list(app.exception), [element.message for element in app.exception]
    [table] = [frame for frame in app.dataframe if "상세" in frame.value.columns]
    assert table.value["상세"].iloc[0] == "등급 전 admin · 등급 user · 판 5(그대로)"
    assert table.value["대상"].iloc[0] == "demo.admin"
    assert table.value["세션"].iloc[1] == "ODjEMVcn"
    widths = {name: config.get("width") for name, config in json.loads(table.proto.columns).items()}
    assert widths["상세"] == view.DETAIL_WIDTH_PX
    assert widths["세션"] == view.SESSION_WIDTH_PX
    assert widths.get("대상") is None
    assert {name for name, width in widths.items() if width is not None} == {"상세", "세션"}
    # 칸 이름을 바꾸고 설정을 그대로 두면 폭이 소리 없이 빠진다 — 설정 칸은 표 칸 안이다.
    assert set(view.record_column_config()) <= set(view.RECORD_COLUMNS)


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
    # 개발 실행은 managed 가 아니라 「동기화 아님」 이 늘 선다(관리자만).
    assert [item["active"] for item in keeping] == [active, active]
    assert [item["active"] for item in late] == [False, False]
    if active:
        # 「그 화면으로」 는 어느 화면에서 떠도 Admin Area 의 「접속 · 작업 기록」 탭이다.
        assert {(item["page"], item["href"], item["tab"]) for item in keeping} == {
            (tab_label(ADMIN_AREA), ADMIN_AREA.href, "접속 · 작업 기록")
        }
        assert ADMIN_AREA_LOG_TAB.endswith(keeping[0]["tab"])
    shipper.reset()


@pytest.mark.parametrize(("loginid", "active"), [("dev.user", True), ("other.user", False)])
def test_a_late_piece_raises_ad_13_for_viewers_only(
    cookies: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loginid: str,
    active: bool,
) -> None:
    cfg = use_config()
    runtime.mark_gate_installed()
    spool.configure(tmp_path)
    recorder.start(env="cdep", version="test", inst="efefefefefef")
    recorder.set_grader(grader(cfg))
    token, _ = issue_session(cfg, loginid=loginid, name=None, dept=None, now=int(time.time()))
    cookies[cfg.session_cookie] = token
    late_key = "audit/v1/seg/2026/10/20/efefefefefef__0000000001-0000000001.jsonl.gz"
    monkeypatch.setattr(shipper, "chain_problems", lambda: (late_key,))

    app = AppTest.from_string(ALERT_SCRIPT).run()

    late = states(app, "AD-13")
    assert [item["active"] for item in late] == [active, active]
    if active:
        assert "1개" in late[0]["short"]
        # 적을 곳은 운영 문서 6장과 같은 이름 — 1판에는 앱 안 「점검 기록」 단추가 없다.
        assert late[0]["full"] == (
            "14일보다 늦게 온 기록 조각이 1개 있습니다. 고치려 하지 않고 날짜를 월 점검 기록(앱 "
            "밖)에 적은 뒤 저장소 관리자 · 보안 담당에 알립니다."
        )
        assert (late[0]["page"], late[0]["href"], late[0]["tab"]) == (
            tab_label(ADMIN_AREA),
            ADMIN_AREA.href,
            "접속 · 작업 기록",
        )


# 다른 화면 ↔ Admin 「DB 동기화」 — 감사 알림과 알림 칸 「그 화면으로」 의 콜백(`GOTO_PRELUDE`).
# 세션 `test_page` 가 `admin` 일 때만 펼침을 그린다.
GOTO_SCRIPT = (
    GOTO_PRELUDE
    + """
import streamlit as st

from capa_simulation.components.object_sync_status import render_object_sync_status
from capa_simulation.components.sso_status import render_audit_alerts

render_audit_alerts()
if st.session_state.get("test_page") == "admin":
    render_object_sync_status()
"""
)


def test_the_keeping_alert_opens_the_db_sync_box_its_text_names(
    cookies: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`AD-12` 전문은 「DB 동기화 칸을 보고 「지금 올리기」 를 누릅니다」 다 — 그 펼침이 서는
    서버(`managed`)에서는 「그 화면으로」 가 다른 화면에서 눌려도 그 펼침까지 연다(설계 규칙
    UI-NAV-01). 펼침이 없는 서버(「동기화 아님」)는 기록 탭 그대로다
    (`test_an_on_server_writes_both_codes_every_call_and_raises_them_for_viewers`)."""
    from capa_simulation import object_sync_worker, sync_boot
    from capa_simulation.components import object_sync_status

    cfg = use_config()
    runtime.mark_gate_installed()
    spool.configure(tmp_path)
    recorder.start(env="cdep", version="test", inst="efefefefefef")
    recorder.set_grader(grader(cfg))
    token, _ = issue_session(cfg, loginid="dev.user", name=None, dept=None, now=int(time.time()))
    cookies[cfg.session_cookie] = token
    monkeypatch.setattr(sync_boot, "is_managed", lambda: True)
    monkeypatch.setattr(shipper, "keeping_problems", lambda **_: ("올리기 밀림",))
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: None)

    app = AppTest.from_string(GOTO_SCRIPT)
    app.session_state["test_page"] = "other"
    app.run()
    note = active_state(app, "AD-12")
    assert note is not None and note["href"] == ADMIN_AREA.href
    assert "tab" not in note, "탭을 실으면 알림 칸이 마지막 칸을 누르지 않고 대상만 보낸다"
    assert note["target"]["kind"] == object_sync_status.SYNC_TARGET_KIND

    app.session_state["test_page"] = "admin"
    app.run()
    assert box_expanded(app, object_sync_status.EXPANDER_KEY) is False
    app.session_state[GOTO_PRESS_KEY] = note["target"]
    app.run()
    assert not list(app.exception), [element.message for element in app.exception]
    assert box_expanded(app, object_sync_status.EXPANDER_KEY) is True
    shipper.reset()


def test_the_operations_doc_names_the_monthly_record_like_the_alerts() -> None:
    """운영 문서의 알림 조치와 월 1회 점검이 같은 이름 하나(「월 점검 기록」)를 쓴다 — 「점검
    결과」 라는 둘째 이름이 남지 않고, 두 알림 줄은 앱 밖에 적는다고 말한다(1판에는 앱 안 단추가
    없다)."""
    doc = (Path(__file__).resolve().parents[1] / "docs" / "audit_log_operations.md").read_text(
        encoding="utf-8"
    )
    rows = [line for line in doc.splitlines() if line.startswith(("| `AD-12` |", "| `AD-13` |"))]

    assert "점검 결과" not in doc
    assert len(rows) == 2
    assert all("월 점검 기록(앱 밖)에 적" in row for row in rows), rows
