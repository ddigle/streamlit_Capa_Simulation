# Purpose: 쓰는 순간의 등급 벽 — 판정 셋 · 거절 감사 · 깊이 · 앱 자신의 쓰기 · 받는 자리를 지킨다.

"""쓰는 순간의 벽(`auth/grades.py` · `audit/work.py` · `components/grade_ui.py` ·
`page_failure_card.run_core_page` — 2026-11-18 접속 등급).

모든 등급 시험은 「운영 + 통합인증 켜짐」 판정을 거친다(`grade_support.operational_grades` 가
단언하고 `judge_spy` 가 판정이 실제로 섰는지 본다). 운영 아님 · 운영 + 통합인증 꺼짐은 지금 동작을
그대로 고정한다(결정 3 · 4).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest
from alert_marks import flashed
from grade_support import (
    GRADE_ACCOUNTS,
    GRADE_PARAMS,
    as_account,
    as_grade,
    grade_page_script,
    judge_spy,
    ledger_outer_functions,
    ledger_wall_report,
    operational_grades,
    operational_sso_off,
    preview,
    roots_for,
    unrestricted,
)
from streamlit.runtime.scriptrunner_utils.exceptions import StopException
from streamlit.testing.v1 import AppTest

from capa_simulation.audit import recorder
from capa_simulation.audit.work import audited
from capa_simulation.auth import grades
from capa_simulation.components import sso_identity


def _write_spy() -> tuple[list[str], Callable[..., str]]:
    """표지를 단 가짜 쓰기 — 본문이 돌았는지 적는다(사건은 실제 바닥 표의 것)."""
    ran: list[str] = []

    @audited("data_scenario_create")
    def create(name: str) -> str:
        ran.append(name)
        return name

    return ran, create


@GRADE_PARAMS
def test_each_action_follows_the_need_and_have_table(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    assert grades.caller() == grades.Caller(grade)
    for key, action in grades.ACTIONS.items():
        assert grades.allowed(key) is grades.at_least(grade, action.need), (grade, key)


def test_off_the_operational_server_everything_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    unrestricted(monkeypatch)
    assert grades.caller_source() is sso_identity.real_caller
    assert grades.caller().unrestricted
    for key in grades.ACTIONS:
        grades.require(key)
        assert sso_identity.viewer_can(key)
    assert not sso_identity.admin_area_locked()


def test_operational_with_sso_off_allows_up_to_manager_without_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operational_sso_off(monkeypatch)
    assert grades.caller() == grades.Caller(grades.MANAGER)
    grades.require("official.publish")
    grades.require("equipment.save")
    grades.require("scenario.delete")
    with pytest.raises(grades.GradeDenied):
        grades.require("admin.area")
    with pytest.raises(grades.GradeDenied):
        grades.require("auto_update.edit")
    assert not recorder.enabled() and recorder.take_pending() == []
    assert sso_identity.admin_area_locked()


def test_an_ended_sign_in_is_refused_apart_from_the_grade(monkeypatch: pytest.MonkeyPatch) -> None:
    operational_grades(monkeypatch)
    as_account(monkeypatch, None)
    recorder.start(env="cdep", version="test", inst="i-test")
    with pytest.raises(grades.SignInEnded) as caught:
        grades.require("scenario.create")
    assert caught.value.reason == "missing"
    (line,) = recorder.take_pending()
    assert line["ev"] == "authz_fail_signin" and line["out"] == "denied"
    assert line["det"] == {"action": "scenario.create", "reason": "missing"}


def test_a_refusal_leaves_one_audit_line_with_need_and_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_grade(monkeypatch, grades.EDITOR)
    recorder.start(env="cdep", version="test", inst="i-test")
    with pytest.raises(grades.GradeDenied):
        grades.require("official.publish")
    (line,) = recorder.take_pending()
    assert line["ev"] == "authz_fail_grade"
    assert line["det"] == {"action": "official.publish", "need": "manager", "have": "editor"}


def test_the_app_writing_itself_is_not_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.VIEWER)
    with recorder.as_system("system:app"):
        assert grades.caller().unrestricted
        grades.require("admin.area")
    with pytest.raises(grades.GradeDenied):
        grades.require("admin.area")


def test_an_unknown_thread_without_a_script_context_reads_as_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_grade(monkeypatch, grades.DEVELOPER)
    monkeypatch.setattr(sso_identity, "script_context_present", lambda: False)
    seen: list[grades.Caller] = []
    thread = threading.Thread(target=lambda: seen.append(grades.caller()), name="stranger")
    thread.start()
    thread.join()
    assert seen == [grades.Caller(grades.VIEWER)]


def test_a_system_thread_name_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.VIEWER)
    seen: list[grades.Caller] = []
    thread = threading.Thread(
        target=lambda: seen.append(grades.caller()), name="capa-auto-official-update"
    )
    thread.start()
    thread.join()
    assert seen and seen[0].unrestricted


def test_the_preview_changes_the_screen_but_never_the_wall(monkeypatch: pytest.MonkeyPatch) -> None:
    preview(monkeypatch, grades.EDITOR)
    assert sso_identity.screen_grade() == grades.EDITOR
    assert not sso_identity.viewer_can("official.publish")
    assert sso_identity.admin_area_locked()
    assert grades.allowed("admin.area"), "저장은 실제 등급"
    assert sso_identity.viewer_is_developer()
    assert not sso_identity.developer_wall_locked()


def test_the_wall_stands_even_while_the_recorder_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.VIEWER)
    ran, create = _write_spy()
    assert not recorder.enabled()
    with judge_spy() as seen, pytest.raises(grades.GradeDenied):
        create("x")
    assert ran == [], "본문이 돌지 않는다"
    assert seen == [("scenario.create", grades.VIEWER)]


def test_only_the_outer_write_is_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.EDITOR)
    ran, create = _write_spy()

    @audited("data_revision_save")
    def outer() -> str:
        return create("inner")

    with judge_spy() as seen:
        outer()
    assert seen == [("scenario.revision_save", grades.EDITOR)]
    assert ran == ["inner"]


def test_the_depth_comes_back_after_a_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.EDITOR)

    @audited("data_scenario_create")
    def stopping() -> None:
        raise StopException()

    with pytest.raises(StopException):
        stopping()
    assert grades.depth() == 0
    _, create = _write_spy()
    with judge_spy() as seen:
        create("next")
    assert seen == [("scenario.create", grades.EDITOR)], "다음 쓰기도 판정된다"


def test_an_inner_refusal_is_one_audit_line_without_a_failed_work_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_grade(monkeypatch, grades.EDITOR)
    recorder.start(env="cdep", version="test", inst="i-test")

    @audited("data_equipment_save")
    def save() -> None:
        grades.require("equipment.save")

    with pytest.raises(grades.GradeDenied):
        save()
    lines = recorder.take_pending()
    assert [line["ev"] for line in lines] == ["authz_fail_grade"]
    assert lines[0]["det"] == {"action": "equipment.save", "need": "manager", "have": "editor"}


def test_the_marked_action_is_readable_by_the_nets() -> None:
    @audited("data_profile_save", action="admin.area")
    def higher() -> None:
        return None

    @grades.gated("auto_update.edit")
    def gated() -> None:
        return None

    assert getattr(higher, grades.GATE_ATTRIBUTE) == "admin.area"
    assert getattr(gated, grades.GATE_ATTRIBUTE) == "auto_update.edit"
    _, create = _write_spy()
    assert getattr(create, grades.GATE_ATTRIBUTE) == "scenario.create"


def test_gated_walls_a_write_without_an_audit_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.MANAGER)
    ran: list[int] = []

    @grades.gated("auto_update.edit")
    def save() -> None:
        ran.append(1)

    with pytest.raises(grades.GradeDenied):
        save()
    assert ran == []


# ------------------------------------------------------------------ 받는 자리
REFUSING_PAGE = """
import streamlit as st
from capa_simulation.auth import grades

st.session_state["runs"] = st.session_state.get("runs", 0) + 1
grades.require("official.publish")
st.write("never")
"""

PRESS_PAGE = """
import streamlit as st
from capa_simulation.auth import grades
from capa_simulation.components import grade_ui


@grade_ui.on_press
def _publish() -> None:
    st.session_state["pressed"] = True
    grades.require("official.publish")
    st.session_state["written"] = True


st.button("공식 지정", key="publish", on_click=_publish)
"""

DIALOG_PAGE = """
import streamlit as st
from capa_simulation.auth import grades
from capa_simulation.components import grade_ui


@st.dialog("지정")
@grade_ui.in_fragment
def _dialog() -> None:
    if st.button("지정", key="inside"):
        grades.require("official.publish")
        st.session_state["written"] = True


if st.button("열기", key="open"):
    st.session_state["opened"] = True
if st.session_state.get("opened"):
    _dialog()
"""


@pytest.mark.page_failure_card
def test_a_body_refusal_is_one_notice_without_an_error_card_and_does_not_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_grade(monkeypatch, grades.EDITOR)
    app = AppTest.from_string(grade_page_script(REFUSING_PAGE)).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), "오류 카드(AD-22)가 서지 않는다"
    refusals = [item.value for item in flashed(app, "error")]
    assert refusals == [grades.refusal_text("official.publish")]
    assert app.session_state["runs"] == 2, "한 번만 다시 그리고 멈춘다"


@pytest.mark.page_failure_card
def test_a_pressed_callback_refusal_writes_nothing_and_notifies_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = AppTest.from_string(grade_page_script(PRESS_PAGE))
    as_grade(monkeypatch, grades.MANAGER)
    app.run(timeout=60)
    as_grade(monkeypatch, grades.EDITOR)
    app.button(key="publish").click().run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["pressed"] is True
    assert "written" not in app.session_state
    assert [item.value for item in flashed(app, "error")] == [
        grades.refusal_text("official.publish")
    ]


@pytest.mark.page_failure_card
def test_a_dialog_refusal_reruns_the_whole_app_to_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.EDITOR)
    app = AppTest.from_string(grade_page_script(DIALOG_PAGE)).run(timeout=60)
    app.button(key="open").click().run(timeout=60)
    app.button(key="inside").click().run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert "written" not in app.session_state
    assert [item.value for item in flashed(app, "error")] == [
        grades.refusal_text("official.publish")
    ]


@pytest.mark.page_failure_card
def test_an_ended_sign_in_notice_is_not_a_grade_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    operational_grades(monkeypatch)
    as_account(monkeypatch, None)
    app = AppTest.from_string(grade_page_script(REFUSING_PAGE)).run(timeout=60)
    assert [item.value for item in flashed(app, "error")] == [grades.SIGNED_OUT_TEXT]


# ------------------------------------------------------------------ 장부 뿌리 찾기(그물 재료)
def test_the_ledger_reader_finds_the_outer_write_functions() -> None:
    """가로지르는 그물(`tests/test_grade_coverage.py` — 갈래를 합친 머리)이 쓰는 재료가 장부를
    읽는다.

    「장부의 모든 쓰기가 표지 벽에 닿는다」 단언은 calc · equip 이 벽을 단 뒤 합친 머리에서 선다
    (core 가지에서는 그 둘의 벽이 아직 없다)."""
    outers = ledger_outer_functions()
    assert ("app.py", "<module>") in outers
    assert ("src/capa_simulation/components/scenario_status.py", "_render_revision_save") in outers
    assert len(outers) >= 50


def test_roots_are_found_across_files_and_a_body_write_is_its_own_root() -> None:
    kinds = {root.kind for root in roots_for("_save_global_display_order")}
    assert kinds & {"callback", "dialog", "fragment"}, kinds
    (body,) = roots_for("bootstrap_never_called_from_a_callback_xyz")
    assert body.kind == "body"


def test_the_ledger_wall_report_sees_walled_and_system_writes() -> None:
    """장부 ↔ 벽 대조 재료 — 표지를 단 저장소 쓰기는 벽이 있고, 첫 시드는 앱 자신의 길이다.
    「벽 없는 장부 쓰기가 없다」 단언은 갈래를 합친 머리(`tests/test_grade_coverage.py`)가 한다."""
    report = ledger_wall_report()
    assert {"save_revision", "create_scenario", "publish_official_revision"} <= report.walled
    assert report.system == {"bootstrap_latest_official_scenario"}
    assert not (report.walled & report.unwalled)


def test_every_grade_has_a_demo_account() -> None:
    assert set(GRADE_ACCOUNTS) == set(grades.GRADES)
    assert all(account.startswith("demo.") for account in GRADE_ACCOUNTS.values())


def _unused(*_: Any) -> None:
    return None
