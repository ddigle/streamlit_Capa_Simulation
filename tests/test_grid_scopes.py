# Purpose: 생산 계획 · 기준 정보 편집 그리드의 편집기 구역 회차(칸 고치기 · 올리기 · ack 지킴 ·
# 작업 줄 단추)를 프래그먼트 회차 대역으로 본다.

"""그리드 셋 가운데 생산 계획(PKG PLAN · 수율)과 기준 정보 그리드는 작업 줄 칸 · 그리드 칸을 키 붙은
프래그먼트(편집기 구역 — AGENTS 9장 「구역 회차 규칙」)로 돈다. AppTest 는 프래그먼트만 도는 회차를
만들지 못해 `tests/fragment_browser.py` 대역으로 브라우저처럼 그 구역의 회차를 청한다. 그리드 부품은
이 실행 **안에서** 등록한다(모듈을 읽을 때 등록한 것은 그 실행에서 「미등록」 — 대역 부품은 JS 없이
상태 값만 받는다).

- 표 초안 있음 · 없음이 바뀌는 조작(첫 칸 · 되돌려 0칸 · 편집 취소 · 적용)은 앱 전체 회차로 올라가고
  그 회차의 feed 가 보낸 op 의 ack 를 싣는다(`[[구역], []]`).
- 초안이 그대로 있는 칸 고치기는 구역 회차 하나다(`[[구역]]`).
- 생산 계획은 출납 콜백 · 단추 콜백 끝에서 올린다 — 그 구역 회차는 본문을 돌지 않아 그리드를 앱
  전체 회차에 한 번만 보낸다(`_grid_draws`). 기준 정보 「변경사항 적용」 은 본문이 누른 회차에
  판정하는 단추라 출납 콜백은 올리지 않고 본문 뒤에서 올린다 — 같은 상호작용의 첫 칸 고침과 적용
  누름이 함께 와도 누름이 버려지지 않는다.
- 팝업(붙여넣기 · 가상 제품)은 구역 밖이라 여는 콜백 뒤에 팝업이 선다.
- 구역 회차는 `app.py` 의 실행 핀 밖이라 PKG PLAN 구역 본문이 시나리오 DB 핀을 스스로 잡는다 — 적용
  알림 창 안의 칸 고치기가 공정 표시명을 DB 에서 읽어도 그 핀 안이다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from edit_grid_fake import shell_key
from fragment_browser import FragmentBrowser, install_fragment_browser
from streamlit.errors import StreamlitAPIException
from streamlit.proto.WidgetStates_pb2 import WidgetState, WidgetStates
from streamlit.testing.v1 import AppTest
from test_load_conversion_plan_apply import _script
from test_reference_data_page import DATASET, REAL_APPLY_TEST_SCRIPT

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.components.month_range_picker as month_range_picker
import capa_simulation.persistence._sql_helpers as sql_helpers
from capa_simulation import settings, sidebar_status
from capa_simulation.components import edit_grid, fragment_scope, grid_shared, write_guard
from capa_simulation.persistence.cache import clear_global_process_rename_cache
from capa_simulation.plan_grid_keys import HOSTS, PLAN_TABLE, YIELD_TABLE
from capa_simulation.plan_grid_keys import cells_key as plan_cells_key
from capa_simulation.reference_grid_keys import DATASET_KEY, GRID_HOST
from capa_simulation.reference_grid_keys import cells_key as reference_cells_key

PLAN_SCOPE = "load_conversion_plan_scope"
YIELD_SCOPE = "load_conversion_yield_scope"
REFERENCE_SCOPE = "reference_data_grid_scope"
TAB_KEY = "load_conversion_active_tab"
TABS = {PLAN_TABLE: ":material/edit_calendar: PKG PLAN", YIELD_TABLE: ":material/percent: 수율"}
SCOPES = {PLAN_TABLE: PLAN_SCOPE, YIELD_TABLE: YIELD_SCOPE}
# 표마다 고칠 칸(줄 0 · 달)과 두 값.
CELLS = {PLAN_TABLE: ("202602", "200", "300"), YIELD_TABLE: ("202603", "0.9", "0.8")}
RUN_DAY = ("Process-A", "202608")
REFERENCE_APPLY = "capa_run_day_editor_apply"
REFERENCE_PASTE = "capa_run_day_editor_open_paste"


@pytest.fixture(autouse=True)
def _quiet_custom_renderers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """화면의 다른 Components v2 그림(가로 스크롤 막대 · 조회기간 단추)은 이 시험 밖이다."""
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(
        month_range_picker,
        "render_month_range_apply",
        lambda *, start, end, min_month, max_month, key, this_month=None: None,
    )
    yield


def _live_grids(monkeypatch: pytest.MonkeyPatch) -> None:
    """범용 편집 그리드 세 등록을 이 실행 안에서 등록한다(JS 없음 — 상태 값 `outbox` 만 받는다)."""

    def live(name: str) -> Any:
        def mount(**kwargs: Any) -> Any:
            return st.components.v2.component(name, js="export default function () {}")(**kwargs)

        return mount

    monkeypatch.setattr(edit_grid, "_GRID", live(edit_grid.GRID_COMPONENT))
    monkeypatch.setattr(edit_grid, "_GRID_ROWS", live(edit_grid.ROWS_COMPONENT))
    monkeypatch.setattr(edit_grid, "_FEED", live(edit_grid.FEED_COMPONENT))


def _ok(app: AppTest) -> AppTest:
    assert not list(app.exception), [element.message for element in app.exception]
    return app


class _Page:
    """한 세션의 화면과 브라우저 대역 — 브라우저처럼 늘 모든 위젯 값을 실어 보낸다.

    대역의 요소 트리는 구역 회차 뒤에는 그 회차가 보낸 델타뿐이라 구역 밖 위젯 값(화면 탭 · 종류
    단추)이 빠진다. 진짜 브라우저는 아는 위젯 값을 다 싣는다 — 마지막 앱 전체 회차의 값에 그 뒤
    회차의 값을 덮어 보낸다. AppTest 트리가 위젯 값으로 싣지 못하는 칸(화면 안 탭 `st.tabs` 의
    고른 탭)은 `keep` 의 세션 값을 회차마다 다시 적는다."""

    def __init__(
        self, app: AppTest, browser: FragmentBrowser, keep: dict[str, Any] | None = None
    ) -> None:
        self.app = app
        self.browser = browser
        self.keep = dict(keep or {})
        self.full = app._tree.get_widget_states()

    def _states(self, changed: list[WidgetState]) -> WidgetStates:
        merged = {state.id: state for state in self.full.widgets}
        merged.update({state.id: state for state in self.app._tree.get_widget_states().widgets})
        for state in changed:
            merged[state.id] = state
        states = WidgetStates()
        states.widgets.extend(merged.values())
        return states

    def send(self, scope: str, *changed: WidgetState) -> AppTest:
        """구역 안 위젯이 바뀐 회차를 청한다(브라우저는 그 구역의 fragment id 로 청한다)."""
        for key, value in self.keep.items():
            self.app.session_state[key] = value
        self.browser.fragment_queue = [scope]
        _ok(self.app._run(widget_state=self._states(list(changed))))
        if self.browser.started and self.browser.started[-1] == []:
            self.full = self.app._tree.get_widget_states()
        return self.app

    def outbox(self, scope: str, host: str, value: dict[str, Any]) -> AppTest:
        widget_id = self.browser.widget_id_of(host)
        return self.send(scope, WidgetState(id=widget_id, json_value=json.dumps(value)))

    def press(self, scope: str, key: str) -> AppTest:
        widget_id = self.browser.widget_id_of(key)
        return self.send(scope, WidgetState(id=widget_id, trigger_value=True))


def _ops(
    browser: FragmentBrowser, host: str, *ops: dict[str, Any], mount: str = "m1"
) -> dict[str, Any]:
    """그 그리드 마운트 `mount` 의 출납 — op 마다 seq(1 부터) · 표 · `gen`(지금 feed)을 붙인다."""
    feed = browser.bidi_data(edit_grid.feed_key(host))
    numbered = [
        {**op, "seq": seq, "at": seq, "table": feed["table"], "gen": feed["gen"]}
        for seq, op in enumerate(ops, start=1)
    ]
    return {"outbox": {"mount": mount, "ops": numbered}}


def _write(row: str, month: str, text: str) -> dict[str, Any]:
    return {"op": "write", "rows": [row], "cols": [month], "values": [[text]]}


def _revert(row: str, month: str) -> dict[str, Any]:
    return {"op": "revert", "rows": [row], "cols": [month]}


def _ack(browser: FragmentBrowser, host: str, mount: str = "m1") -> int:
    return int(browser.bidi_data(edit_grid.feed_key(host))["acks"].get(mount, 0))


def _grid_draws(browser: FragmentBrowser, host: str) -> int:
    """마지막 `run()` 안의 모든 회차가 그 그리드 마운트를 보낸 수 — 구역 회차에 본문이 돌았는지
    본다(콜백 끝에서 올라가면 구역 회차는 본문 전에 끝나 앱 전체 회차의 한 번뿐이다)."""
    drawn = 0
    for message in browser.emitted:
        if message.WhichOneof("type") != "delta":
            continue
        delta = message.delta
        if delta.WhichOneof("type") != "new_element":
            continue
        if delta.new_element.WhichOneof("type") != "bidi_component":
            continue
        if str(delta.new_element.bidi_component.id).endswith(f"-{host}"):
            drawn += 1
    return drawn


def _has(app: AppTest, key: str) -> bool:
    """세션 칸에 값이 있는가(없거나 None 이면 거짓)."""
    return key in app.session_state and app.session_state[key] is not None


def _dialog_drawn(browser: FragmentBrowser) -> bool:
    try:
        browser.dialog_widget_id()
    except AssertionError:
        return False
    return True


# ------------------------------------------------------------------ 생산 계획(PKG PLAN · 수율)


@pytest.fixture(scope="module")
def plan_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("grid_scopes") / "scenario.duckdb"


def _plan_page(monkeypatch: pytest.MonkeyPatch, database: Path, table: str) -> tuple[_Page, str]:
    browser = install_fragment_browser(monkeypatch)
    _live_grids(monkeypatch)
    app = _ok(AppTest.from_string(_script(database), default_timeout=300).run())
    app.session_state[TAB_KEY] = TABS[table]
    _ok(app.run())
    return _Page(app, browser, {TAB_KEY: TABS[table]}), browser.fragment_keyed(SCOPES[table])


def _plan_cell(page: _Page, table: str) -> tuple[str, str]:
    """줄 0 의 업무 키와 고칠 달."""
    return shell_key(page.browser.bidi_data(HOSTS[table]), 0), CELLS[table][0]


@pytest.mark.parametrize("table", [PLAN_TABLE, YIELD_TABLE], ids=["pkg-plan", "yield"])
def test_a_plan_grid_edit_runs_its_scope_and_rises_only_when_the_draft_set_changes(
    monkeypatch: pytest.MonkeyPatch, plan_database: Path, table: str
) -> None:
    """첫 칸은 초안 칸이 서서 출납 콜백 끝에서 앱 전체로 올라가고, 그 회차의 feed 가 ack 를 싣는다.
    초안이 있는 둘째 칸은 구역 회차 하나다. 되돌려 초안이 비면 본문 뒤에서 올라간다."""
    page, scope = _plan_page(monkeypatch, plan_database, table)
    host = HOSTS[table]
    row, month = _plan_cell(page, table)
    _, first, second = CELLS[table]
    edits = [_write(row, month, first)]

    page.outbox(scope, host, _ops(page.browser, host, *edits))
    assert page.browser.started == [[scope], []]
    assert _grid_draws(page.browser, host) == 1, "출납 콜백 끝에서 올라 구역 본문은 돌지 않는다"
    assert _ack(page.browser, host) == 1
    assert page.app.session_state[plan_cells_key(table)]["cells"]

    edits.append(_write(row, month, second))
    page.outbox(scope, host, _ops(page.browser, host, *edits))
    assert page.browser.started == [[scope]], "초안이 그대로면 구역 회차 하나"
    assert _grid_draws(page.browser, host) == 1
    assert _ack(page.browser, host) == 2

    edits.append(_revert(row, month))
    page.outbox(scope, host, _ops(page.browser, host, *edits))
    assert page.browser.started == [[scope], []], "초안이 비면 본문 뒤에서 앱 전체로"
    assert _grid_draws(page.browser, host) == 2, "구역 본문이 반영한 뒤 올라간다"
    assert _ack(page.browser, host) == 3
    assert not _has(page.app, plan_cells_key(table))


def test_plan_scope_buttons_rise_at_the_callback_end(
    monkeypatch: pytest.MonkeyPatch, plan_database: Path
) -> None:
    """작업 줄 단추 — 「Excel 붙여넣기」 는 구역 밖 팝업을 그리러, 「편집 취소」 ·
    「변경사항 적용」 은 초안 · 원본이 바뀌어 콜백 끝에서 앱 전체로 올라간다."""
    page, scope = _plan_page(monkeypatch, plan_database, PLAN_TABLE)
    host = HOSTS[PLAN_TABLE]
    row, month = _plan_cell(page, PLAN_TABLE)
    _, first, _ = CELLS[PLAN_TABLE]

    page.press(scope, "open_plan_paste")
    assert page.browser.started == [[scope], []]
    assert _grid_draws(page.browser, host) == 1
    assert _dialog_drawn(page.browser)
    page.app.session_state["load_conversion_open_dialog"] = None
    _ok(page.app.run())
    page.full = page.app._tree.get_widget_states()

    page.outbox(scope, host, _ops(page.browser, host, _write(row, month, first)))
    page.press(scope, "discard_pkg_plan_edits")
    assert page.browser.started == [[scope], []]
    assert _grid_draws(page.browser, host) == 1
    assert not _has(page.app, plan_cells_key(PLAN_TABLE))

    token = page.app.session_state["active_scenario"]["content_token"]
    page.outbox(scope, host, _ops(page.browser, host, _write(row, month, first), mount="m2"))
    assert _ack(page.browser, host, "m2") == 1
    page.press(scope, "apply_pkg_plan_changes")
    assert page.browser.started == [[scope], []]
    assert _grid_draws(page.browser, host) == 1
    assert page.app.session_state["active_scenario"]["content_token"] != token
    assert not _has(page.app, plan_cells_key(PLAN_TABLE))


def test_a_plan_first_edit_and_an_apply_press_in_one_request_still_apply(
    monkeypatch: pytest.MonkeyPatch, plan_database: Path
) -> None:
    """같은 상호작용에 초안 없던 표의 첫 op(출납)와 「변경사항 적용」 누름이 함께 와도 적용된다 —
    단추 콜백이 출납 콜백보다 먼저 돌아 그 표 출납을 받아 적용하고(`settle_inbox`), 두 콜백 끝
    올리기는 앱 전체 회차 하나다."""
    page, scope = _plan_page(monkeypatch, plan_database, PLAN_TABLE)
    host = HOSTS[PLAN_TABLE]
    row, month = _plan_cell(page, PLAN_TABLE)
    token = page.app.session_state["active_scenario"]["content_token"]
    value = _ops(page.browser, host, _write(row, month, CELLS[PLAN_TABLE][1]))

    page.send(
        scope,
        WidgetState(id=page.browser.widget_id_of(host), json_value=json.dumps(value)),
        WidgetState(id=page.browser.widget_id_of("apply_pkg_plan_changes"), trigger_value=True),
    )

    assert page.browser.started == [[scope], []]
    assert _grid_draws(page.browser, host) == 1
    assert page.app.session_state["active_scenario"]["content_token"] != token
    assert not _has(page.app, plan_cells_key(PLAN_TABLE))
    assert _ack(page.browser, host) == 1


def test_a_plan_scope_run_reads_the_database_under_its_own_pin(
    monkeypatch: pytest.MonkeyPatch, plan_database: Path
) -> None:
    """구역 회차는 `app.py` 의 실행 핀 밖에서 돈다 — PKG PLAN 구역 본문이 시나리오 DB
    핀(`pinned_connections`)을 스스로 잡는다. 적용 알림 창 안의 칸 고치기는 구역 본문이 소요대수에
    들지 않은 수요를 다시 알리고, 공정 표시명 캐시가 비었으면 그 읽기가 DB 를 연다. 창은 시험 동안
    넉넉히 늘린다(AppTest 회차는 사람 손보다 느리다)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 600.0)
    page, scope = _plan_page(monkeypatch, plan_database, PLAN_TABLE)
    host = HOSTS[PLAN_TABLE]
    row, month = _plan_cell(page, PLAN_TABLE)
    _, first, second = CELLS[PLAN_TABLE]
    page.outbox(scope, host, _ops(page.browser, host, _write(row, month, first)))
    page.press(scope, "apply_pkg_plan_changes")
    edits = [_write(row, month, second)]
    page.outbox(scope, host, _ops(page.browser, host, *edits, mount="m2"))
    key = sql_helpers._pin_key(plan_database)
    under_pin: list[bool] = []
    take_pin = sql_helpers._take_pin

    def watched(database_path: Path) -> None:
        if sql_helpers._pin_key(database_path) == key and fragment_scope.fragment_only_run():
            under_pin.append(key in sql_helpers._PIN_TARGETS.slots)
        take_pin(database_path)

    monkeypatch.setattr(sql_helpers, "_take_pin", watched)
    clear_global_process_rename_cache()
    edits.append(_write(row, month, "777"))
    page.outbox(scope, host, _ops(page.browser, host, *edits, mount="m2"))

    assert page.browser.started == [[scope]]
    assert under_pin, "적용 알림 창 안의 구역 회차가 DB 를 열지 않았다"
    assert all(under_pin), under_pin


# ------------------------------------------------------------------ 기준 정보


def _reference_page(monkeypatch: pytest.MonkeyPatch) -> tuple[_Page, str]:
    browser = install_fragment_browser(monkeypatch)
    _live_grids(monkeypatch)
    app = AppTest.from_string(REAL_APPLY_TEST_SCRIPT, default_timeout=120)
    app.session_state[DATASET_KEY] = DATASET["일수"]
    _ok(app.run())
    return _Page(app, browser), browser.fragment_keyed(REFERENCE_SCOPE)


def _run_day(app: AppTest) -> list[float]:
    table = app.session_state["active_scenario"]["tables"]["RQ_RUN_DAY"]
    return [float(value) for value in table["RUN_DAY"]]


def test_a_reference_grid_edit_rises_after_the_body_only_when_the_draft_set_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """첫 칸은 구역 본문이 반영한 뒤 본문 뒤에서 앱 전체로 올라가고(출납 콜백은 올리지 않는다)
    ack 가 남는다. 둘째 칸은 구역 회차 하나다."""
    page, scope = _reference_page(monkeypatch)
    edits = [_write(*RUN_DAY, "20")]

    page.outbox(scope, GRID_HOST, _ops(page.browser, GRID_HOST, *edits))
    assert page.browser.started == [[scope], []]
    assert _ack(page.browser, GRID_HOST) == 1
    assert page.app.session_state[reference_cells_key("RQ_RUN_DAY")]["cells"]

    edits.append(_write(*RUN_DAY, "21"))
    page.outbox(scope, GRID_HOST, _ops(page.browser, GRID_HOST, *edits))
    assert page.browser.started == [[scope]]
    assert _ack(page.browser, GRID_HOST) == 2


def test_a_reference_apply_in_the_scope_applies_and_rises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """구역 회차의 「변경사항 적용」 은 본문이 적용하고 머리 표지(활성 시나리오 내용)가 본문
    뒤에서 앱 전체로 올린다 — 그 회차는 새 원본으로 그리고 초안이 없다."""
    page, scope = _reference_page(monkeypatch)
    page.outbox(scope, GRID_HOST, _ops(page.browser, GRID_HOST, _write(*RUN_DAY, "20")))

    page.press(scope, REFERENCE_APPLY)

    assert page.browser.started == [[scope], []]
    assert _run_day(page.app) == [20.0]
    assert not _has(page.app, reference_cells_key("RQ_RUN_DAY"))


def test_a_first_edit_and_an_apply_press_in_one_request_still_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """같은 상호작용에 초안 없던 표의 첫 op(출납)와 「변경사항 적용」 누름이 함께 와도 누름이
    산다 — 출납 콜백이 콜백 끝에서 올리면(`st.rerun()`) 본문이 보는 단추 누름이 버려진다."""
    page, scope = _reference_page(monkeypatch)
    value = _ops(page.browser, GRID_HOST, _write(*RUN_DAY, "20"))

    page.send(
        scope,
        WidgetState(id=page.browser.widget_id_of(GRID_HOST), json_value=json.dumps(value)),
        WidgetState(id=page.browser.widget_id_of(REFERENCE_APPLY), trigger_value=True),
    )

    assert page.browser.started == [[scope], []]
    assert _run_day(page.app) == [20.0]
    assert _ack(page.browser, GRID_HOST) == 1


@pytest.mark.parametrize("alone", [True, False], ids=["host-only", "app-run"])
def test_the_reference_paste_popup_opens_from_inside_the_scope(
    monkeypatch: pytest.MonkeyPatch, alone: bool
) -> None:
    """구역 안 「Excel 붙여넣기」 — 여는 콜백이 호스트만 다시 돌리고(`rerun_fragment_if_alone` —
    `[[구역], [호스트]]`), 그러지 못하면(직전 앱 전체 회차가 끝나지 않음 · 다른 위젯도 바뀜 등)
    열림 칸이 바뀐 머리 표지가 콜백 끝에서 앱 전체로 올린다(`[[구역], []]`). 어느 길이든 팝업이
    선다. AppTest 는 판정(`fragment_rerun_is_safe`)을 넘지 못해 호스트 길은 판정을 대역으로 연다."""
    if alone:
        monkeypatch.setattr(sidebar_status, "fragment_rerun_is_safe", lambda key: True)
        monkeypatch.setattr(sidebar_status, "_would_stop_periodic_fragments", lambda: False)
    page, scope = _reference_page(monkeypatch)
    host = page.browser.fragment_keyed("reference_data_dialog_host")

    page.press(scope, REFERENCE_PASTE)

    assert page.browser.started == ([[scope], [host]] if alone else [[scope], []])
    assert _dialog_drawn(page.browser)


# ------------------------------------------------------------------ 끄개(구역 없이 앱 전체 회차)


def _send_app_run(page: _Page, host: str, value: dict[str, Any]) -> AppTest:
    """그리드 출납을 앱 전체 회차로 보낸다 — 끄개를 끄면 부품이 구역 밖에 그려져 브라우저가 앱 전체
    회차를 청한다."""
    for key, kept in page.keep.items():
        page.app.session_state[key] = kept
    page.browser.fragment_queue = []
    changed = WidgetState(id=page.browser.widget_id_of(host), json_value=json.dumps(value))
    return _ok(page.app._run(widget_state=page._states([changed])))


@pytest.mark.parametrize("grid", ["pkg-plan", "reference"])
def test_with_scopes_off_a_grid_edit_runs_the_whole_app(
    monkeypatch: pytest.MonkeyPatch, plan_database: Path, grid: str
) -> None:
    """끄개(`CAPA_EDITOR_SCOPES=off`)면 생산 계획 · 기준 정보 그리드는 구역을 세우지 않는다 — 초안이
    서는 첫 칸도, 초안이 그대로인 둘째 칸도 앱 전체 회차 하나(`[[]]`)이고 그 회차의 feed 가 ack 를
    싣는다. 묶음 쉼은 지난 판 값(`grid_shared.ORDINARY_SEND_MS`)이다."""
    monkeypatch.setenv(settings.EDITOR_SCOPES_ENV, "off")
    browser = install_fragment_browser(monkeypatch)
    _live_grids(monkeypatch)
    if grid == "pkg-plan":
        app = _ok(AppTest.from_string(_script(plan_database), default_timeout=300).run())
        app.session_state[TAB_KEY] = TABS[PLAN_TABLE]
        _ok(app.run())
        page = _Page(app, browser, {TAB_KEY: TABS[PLAN_TABLE]})
        host, scope, cells = HOSTS[PLAN_TABLE], PLAN_SCOPE, plan_cells_key(PLAN_TABLE)
        row, (month, first, second) = shell_key(browser.bidi_data(host), 0), CELLS[PLAN_TABLE]
    else:
        app = AppTest.from_string(REAL_APPLY_TEST_SCRIPT, default_timeout=120)
        app.session_state[DATASET_KEY] = DATASET["일수"]
        _ok(app.run())
        page = _Page(app, browser)
        host, scope, cells = GRID_HOST, REFERENCE_SCOPE, reference_cells_key("RQ_RUN_DAY")
        (row, month), first, second = RUN_DAY, "20", "21"
    with pytest.raises(StreamlitAPIException):
        browser.fragment_keyed(scope)
    assert browser.bidi_data(host)["limits"]["sendMs"] == grid_shared.ORDINARY_SEND_MS

    edits = [_write(row, month, first)]
    _send_app_run(page, host, _ops(browser, host, *edits))
    assert browser.started == [[]]
    assert _ack(browser, host) == 1
    assert page.app.session_state[cells]["cells"]

    edits.append(_write(row, month, second))
    _send_app_run(page, host, _ops(browser, host, *edits))
    assert browser.started == [[]], "초안이 그대로인 칸도 앱 전체 회차"
    assert _ack(browser, host) == 2
