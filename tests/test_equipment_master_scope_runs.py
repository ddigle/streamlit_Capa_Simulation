# Purpose: 설비 마스터 탭 ① 의 편집기 구역 회차(칸 고치기 · 올리기 · ack 지킴 · 남의 저장 · 작은
# 편집표 제출 · 등급 거절 · DB 핀 · 제 저장 이음)를 프래그먼트 회차 대역으로 본다.

"""가용설비 현황 탭 ① 「설비 마스터」 본문은 키 붙은 프래그먼트(편집기 구역 — AGENTS 9장 「구역 회차
규칙」)로 돈다. AppTest 는 프래그먼트만 도는 회차를 만들지 못해 `tests/fragment_browser.py` 대역으로
브라우저처럼 그 구역의 회차를 청한다. 표 부품은 이 실행 **안에서** 등록한다(JS 없이 상태 값 ·
트리거만 받는다).

- 미저장 편집이 서는 첫 칸은 출납 콜백 끝에서 앱 전체로 올라가고 그 회차의 feed 가 ack 를 싣는다
  (`[[구역], []]`). 미저장 표시가 그대로인 다음 칸은 구역 회차 하나다(구역 밖 델타 없음 · 이벤트 칸
  자리 같음).
- 「목록 비우기」 · 「조건별」 불러오기 · 표 고르기 · 오른쪽 칸 바꿈은 구역 회차 하나다 — 열두
  갈래가 이벤트 칸에 같은 자리를 쓴다(R5). 「비가동 일정 표에서 고치기」 · 가져오기(표 고르기 ·
  오른쪽 칸을 바꾸는 콜백) · 「새 호기」 초안 · 미저장 표시가 그대로인 「한 단계 되돌리기」 도 구역
  회차 하나다. 작은 편집표에 적용하지 않은 편집이 서거나 걷히면 편집표 콜백 끝에서 올라간다 — 같은
  요청에 「편집본에 적용」 누름이 실리면 그 누름을 버리지 않게 본문이 판정한 뒤 올라간다.
- 「리비전 저장」 · 「모두 버리기」 · 팝업 열기 · 세션을 옮긴 「최신 rN 불러오기」 · 등급 밖 출납
  거절은 콜백 끝에서 앱 전체로 올라간다.
- 남이 공통 대장을 저장한 뒤의 칸 고침은 구역 본문을 그린 뒤 올라가고(R4), 그 앱 전체 회차가
  편집본을 다시 세운다. 페이지가 편집본을 세운 뒤 · 저장 토큰을 찍기 전에 든 남의 저장도 다음
  구역 회차가 알아본다. 한 번만 쓰는 표지 `drafts_replaced` 는 구역 회차에서 꺼지고, 남의 저장을 본
  구역 회차의 작은 편집표 제출은 구역 안에서 다시 판정해 거절한다(제 저장의 뒷정리 대기는 남의
  저장이 아니다).
- 구역 회차의 설비 DB 읽기(저장 토큰 · 본문)는 핀 하나 안이다.
- 제 「리비전 저장」 이 쓰기 뒤 끊긴 뒤 닿은 칸은 콜백 끝에서 올라가 다시 세운 편집본에 얹힌다 —
  저장이 새 일정 리비전을 썼어도. 저장이 쓰는 사이 다른 회차의 콜백이 옛 편집본에 얹은 칸도 남는다.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from alert_marks import alert_notes
from fragment_browser import FragmentBrowser, install_fragment_browser
from grade_support import as_grade, grade_page_script, preview
from grid_fake import install_fake_grid, load, send_ops
from streamlit.components.v2.bidi_component.main import _make_trigger_id
from streamlit.errors import StreamlitAPIException
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.proto.WidgetStates_pb2 import WidgetState, WidgetStates
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _two_scenarios
from test_equipment_master_save_race import _app, _no_foreign_blame, _value
from test_equipment_master_tab import RUN_HEAD_KEY
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import _request, _seeded, _session, _set
from test_scenario_save_double_press import _first_callback

import capa_simulation.components.write_guard as write_guard
import capa_simulation.persistence._sql_helpers as sql_helpers
import capa_simulation.settings as settings
from capa_simulation.auth import grades
from capa_simulation.components import equipment_data_workspace as edw
from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components import equipment_master_tab as emt
from capa_simulation.components import grade_ui, grid_shared
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    OWN_SAVE_CARRY_KEY,
    TABLE_ACTIONS,
)
from capa_simulation.components.equipment_master_tab import (
    DISCARD_CONFIRM_KEY,
    LOAD_LATEST_BUTTON_KEY,
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_DETAIL,
    SIDE_KEY,
    SIDE_NEW,
    UNDO_BUTTON_KEY,
)
from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY
from capa_simulation.components.flash import queue_flash
from capa_simulation.components.table_view_controls import filter_widget_key
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_bulk_delete import BASELINE_TARGET, DOWNTIME_TARGET
from capa_simulation.services.equipment_contract import EQUIPMENT_COLUMNS, EQUIPMENT_ID_COLUMN

PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
SCOPE = emt.MASTER_SCOPE
MOUNT = "m-scope"
# 기존 보유대수 작은 편집표의 「편집본에 적용」 단추 key.
BASELINE_APPLY = "equipment_baseline_apply_v1"
# 작은 편집표 제출을 남의 저장으로 거절한 글(결과 알림 칸 `_ERROR_KEY`).
REFUSED_SUBMIT = "이번 제출은 반영하지 않았습니다"
_SEQ = itertools.count(1)


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    yield
    clear_equipment_repository()


def _live_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """표 · feed 등록을 이 실행 안에서 한다(JS 없음 — 상태 값 · 트리거만 받는다)."""

    def live(name: str) -> Any:
        def mount(**kwargs: Any) -> Any:
            return st.components.v2.component(name, js="export default function () {}")(**kwargs)

        return mount

    monkeypatch.setattr(emg, "_GRID", live("capa_equipment_master_grid"))
    monkeypatch.setattr(emg, "_FEED", live("capa_equipment_master_grid_feed"))


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [element.message for element in app.exception]
    return app


class _Page:
    """한 세션의 화면과 브라우저 대역 — 브라우저처럼 화면에 서 있는 위젯 값을 다 실어 보낸다. 구역
    밖 위젯 값은 마지막 앱 전체 회차의 것이고, 구역 안 위젯 값은 마지막 회차가 그린 것이다(구역
    회차가 거둔 위젯은 싣지 않는다). AppTest 트리가 위젯 값으로 싣지 못하는 칸(바깥 탭)은 세션 값을
    회차마다 다시 적는다."""

    def __init__(self, app: AppTest, browser: FragmentBrowser) -> None:
        self.app = app
        self.browser = browser
        self.scope = browser.fragment_keyed(SCOPE)
        self.outside = self._outside_states()

    def _outside_states(self) -> list[WidgetState]:
        """앱 전체 회차 트리의 위젯 값 가운데 구역 밖 것."""
        inside = {
            str(getattr(getattr(m.delta.new_element, kind), "id", ""))
            for m in self.browser.messages
            if m.WhichOneof("type") == "delta"
            and m.delta.WhichOneof("type") == "new_element"
            and m.delta.fragment_id == self.scope
            and (kind := m.delta.new_element.WhichOneof("type"))
        }
        return [s for s in self.app._tree.get_widget_states().widgets if s.id not in inside]

    def _states(self, changed: list[WidgetState]) -> WidgetStates:
        merged = {state.id: state for state in self.outside}
        merged.update({state.id: state for state in self.app._tree.get_widget_states().widgets})
        for state in changed:
            merged[state.id] = state
        states = WidgetStates()
        states.widgets.extend(merged.values())
        return states

    def send(self, *changed: WidgetState, scope: bool = True) -> AppTest:
        """구역 안 위젯이 바뀐 회차를 청한다(브라우저는 그 구역의 fragment id 로 청한다)."""
        self.app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
        self.browser.fragment_queue = [self.scope] if scope else []
        _ok(self.app._run(widget_state=self._states(list(changed))))
        if self.browser.started and self.browser.started[-1] == []:
            self.scope = self.browser.fragment_keyed(SCOPE)
            self.outside = self._outside_states()
        return self.app

    def base(self) -> str:
        return str(self.browser.bidi_data(emg.GRID_KEY)["base"])

    def ack(self) -> Any:
        return self.browser.bidi_data(emg.feed_key())["ack"]

    def outbox(self, *ops: dict[str, Any], key: str = emg.GRID_KEY) -> int:
        """그 마운트에서 op 들을 보낸다 — 마지막 seq."""
        base = self.base()
        numbered = [{"seq": next(_SEQ), "at": 0, "base": base, **op} for op in ops]
        widget_id = self.browser.widget_id_of(key)
        value = {"outbox": {"mount": MOUNT, "ops": numbered}}
        self.send(WidgetState(id=widget_id, json_value=json.dumps(value)))
        return int(numbered[-1]["seq"])

    def trigger(self, key: str, event: str, value: object) -> AppTest:
        """그 마운트의 트리거 하나(Components v2 트리거 모음 위젯). 브라우저는 마운트의 상태 값(빈
        사전이라도)을 함께 싣는다 — 받기 쪽이 트리거 값을 그 상태 값 위에서 읽는다."""
        widget_id = self.browser.widget_id_of(key)
        aggregator = _make_trigger_id(widget_id, "events")
        payload = json.dumps([{"event": event, "value": value}])
        known = {state.id for state in self._states([]).widgets if state.WhichOneof("value")}
        changed = [WidgetState(id=aggregator, json_trigger_value=payload)]
        if widget_id not in known:
            changed.append(WidgetState(id=widget_id, json_value="{}"))
        return self.send(*changed)

    def press(self, key: str) -> AppTest:
        return self.send(WidgetState(id=self.browser.widget_id_of(key), trigger_value=True))


def _scope_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[_Page, Path]:
    """호기 둘(DA-01 · DA-02)을 저장한 설비 DB 로 연 탭 ① — 구역 회차를 청하는 대역 위."""
    path = tmp_path / "equipment.duckdb"
    browser = install_fragment_browser(monkeypatch)
    _live_grid(monkeypatch)
    app = _app(path)
    # 구역만 도는 회차는 페이지 대본(시험 DB 자리를 적는 `_page_script`)을 지나지 않는다.
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", path)
    monkeypatch.setattr(settings, "DUCKDB_PATH", path.with_name(f"{path.stem}_simulation.duckdb"))
    _ok(app.run())
    return _Page(app, browser), path


def _cell(name: str, column: str, text: str) -> dict[str, Any]:
    return {"op": "cell", "id": f"s:{name}", "col": column, "text": text}


def _deltas(page: _Page) -> list[Any]:
    return [m for m in page.browser.messages if m.WhichOneof("type") == "delta"]


def _scope_event_slots(page: _Page) -> set[int]:
    """구역이 이벤트 칸에 쓴 자리."""
    return {
        list(message.metadata.delta_path)[1]
        for message in _deltas(page)
        if message.delta.fragment_id == page.scope
        and len(message.metadata.delta_path) == 2
        and message.metadata.delta_path[0] == RootContainer.EVENT
    }


def _grid_draws(page: _Page) -> int:
    """마지막 `run()` 안의 모든 회차가 표 마운트를 보낸 수 — 구역 회차에 본문이 돌았는지 본다."""
    drawn = 0
    for message in page.browser.emitted:
        if message.WhichOneof("type") != "delta":
            continue
        element = message.delta.new_element
        if message.delta.WhichOneof("type") != "new_element":
            continue
        if element.WhichOneof("type") != "bidi_component":
            continue
        if str(element.bidi_component.id).endswith(f"-{emg.GRID_KEY}"):
            drawn += 1
    return drawn


# ------------------------------------------------------------------ 칸 고치기


def test_a_first_edit_rises_at_the_callback_end_and_the_next_edit_stays_in_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """깨끗한 편집본의 첫 칸은 미저장 표시(머리 띠 칩 · 탭 점 · 떠나기 확인)를 세워 출납 콜백 끝에서
    앱 전체로 올라가고 그 회차의 feed 가 ack 를 싣는다. 다음 칸은 구역 회차 하나다 — 그 회차의
    델타는 모두 구역 것이고 이벤트 칸 자리는 앱 전체 회차와 같다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    app_slots = _scope_event_slots(page)
    assert app_slots, "구역이 이벤트 칸에 쓴 자리가 없다"

    seq = page.outbox(_cell("DA-01", "담당자", "첫 값"))
    assert page.browser.started == [[page.scope], []]
    assert _grid_draws(page) == 1, "출납 콜백 끝에서 올라 구역 본문은 돌지 않는다"
    assert page.ack() == {"mount": MOUNT, "seq": seq}
    assert _value(page.app, "DA-01", "담당자") == "첫 값"

    seq = page.outbox(_cell("DA-02", "담당자", "둘째 값"))
    assert page.browser.started == [[page.scope]]
    assert page.ack() == {"mount": MOUNT, "seq": seq}
    assert _value(page.app, "DA-02", "담당자") == "둘째 값"
    assert all(message.delta.fragment_id == page.scope for message in _deltas(page))
    assert _scope_event_slots(page) == app_slots


def test_with_scopes_off_a_cell_edit_runs_the_whole_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """끄개(`CAPA_EDITOR_SCOPES=off`)면 탭 ① 은 구역을 세우지 않는다 — 미저장이 서는 첫 칸도 미저장
    표시가 그대로인 다음 칸도 앱 전체 회차 하나(`[[]]`)이고 그 회차의 feed 가 ack 를 싣는다. 묶음
    쉼은 지난 판 값(`grid_shared.ORDINARY_SEND_MS`)이다."""
    monkeypatch.setenv(settings.EDITOR_SCOPES_ENV, "off")
    path = tmp_path / "equipment.duckdb"
    browser = install_fragment_browser(monkeypatch)
    _live_grid(monkeypatch)
    app = _app(path)
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", path)
    monkeypatch.setattr(settings, "DUCKDB_PATH", path.with_name(f"{path.stem}_simulation.duckdb"))
    _ok(app.run())
    with pytest.raises(StreamlitAPIException):
        browser.fragment_keyed(SCOPE)
    assert browser.bidi_data(emg.GRID_KEY)["sendMs"] == grid_shared.ORDINARY_SEND_MS

    for name, text in (("DA-01", "첫 값"), ("DA-02", "둘째 값")):
        base = str(browser.bidi_data(emg.GRID_KEY)["base"])
        seq = next(_SEQ)
        op = {"seq": seq, "at": 0, "base": base, **_cell(name, "담당자", text)}
        app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
        _ok(browser.send_state(app, emg.GRID_KEY, {"outbox": {"mount": MOUNT, "ops": [op]}}))
        assert browser.started == [[]], name
        assert browser.bidi_data(emg.feed_key())["ack"] == {"mount": MOUNT, "seq": seq}
        assert _value(app, name, "담당자") == text


def test_clearing_and_a_conditions_load_stay_in_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「목록 비우기」 · 「조건별」 불러오기(트리거 `clear` · `load`)는 구역 회차 하나씩이다 —
    불러온 목록 · 결과 알림은 구역 안이다. 표 칸 정렬은 브라우저 몫이라 서버 회차가 없다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.trigger(emg.LOADER_KEY, "clear", {})
    assert page.browser.started == [[page.scope]]
    assert page.browser.bidi_data(emg.GRID_KEY)["rows"] == []

    page.trigger(
        emg.LOADER_KEY, "load", {"kind": "conditions", "ids": ["s:DA-02"], "label": "조건"}
    )
    assert page.browser.started == [[page.scope]]
    assert [row["id"] for row in page.browser.bidi_data(emg.GRID_KEY)["rows"]] == ["s:DA-02"]
    assert all(message.delta.fragment_id == page.scope for message in _deltas(page))


def test_every_table_and_side_writes_the_same_event_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표 고르기(설비 마스터 · 기존 보유대수 · 비가동 일정) × 오른쪽 칸(호기 상세 · 새 호기 · 저장
    전 변경 · 저장 이력) 열두 갈래가 이벤트 칸에 같은 자리를 쓴다(R5) — 그리지 않은 갈래(작은
    편집표 · 저장 구획) 몫은 빈 서식이 채운다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    slots: dict[tuple[str, str], frozenset[int]] = {}
    for table in emt.TABLES:
        for side in emt.SIDES:
            page.app.session_state[emt.TABLE_KEY] = table
            page.app.session_state[SIDE_KEY] = side
            page.send(scope=False)
            slots[(table, side)] = frozenset(_scope_event_slots(page))
    assert len(set(slots.values())) == 1, slots


def _slot_matrix(app: AppTest, browser: FragmentBrowser) -> dict[tuple[str, str], frozenset[int]]:
    """표 셋 × 오른쪽 칸 넷 — 앱 전체 회차마다 구역이 이벤트 칸에 쓴 자리."""
    slots: dict[tuple[str, str], frozenset[int]] = {}
    for table in emt.TABLES:
        for side in emt.SIDES:
            app.session_state[emt.TABLE_KEY] = table
            app.session_state[SIDE_KEY] = side
            app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
            _ok(app.run())
            scope = browser.fragment_keyed(SCOPE)
            slots[(table, side)] = frozenset(
                list(m.metadata.delta_path)[1]
                for m in browser.messages
                if m.WhichOneof("type") == "delta"
                and m.delta.fragment_id == scope
                and len(m.metadata.delta_path) == 2
                and m.metadata.delta_path[0] == RootContainer.EVENT
            )
    return slots


@pytest.mark.parametrize("grade", [grades.VIEWER, grades.EDITOR, grades.MANAGER])
def test_every_grade_writes_the_same_number_of_event_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    """열람 · 실무자 · 관리자 — 저장 구획 · 메뉴 · 작은 편집표 작업 줄이 등급마다 갈려도 열두 갈래가
    이벤트 칸에 같은 수의 자리를 쓴다(그리지 않은 몫은 빈 서식)."""
    browser = install_fragment_browser(monkeypatch)
    install_fake_grid(monkeypatch)
    repository = _seeded(tmp_path)
    as_grade(monkeypatch, grade)
    script = grade_page_script(_page_script(PAGE, repository.database_path))
    app = AppTest.from_string(script, default_timeout=90)
    slots = _slot_matrix(app, browser)
    assert len({len(value) for value in slots.values()}) == 1, slots
    assert len(set(slots.values())) == 1, slots


def test_a_stale_session_with_a_refused_edit_writes_the_same_event_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """낡은 세션의 낡기 전 편집이 저장을 막으면 저장 구획 단추 아래에 「최신 rN 불러오기(변경
    버림)」 와 그 실패 칸이 선다 — 그 칸이 서는 「저장 전 변경」 도 다른 갈래와 같은 자리를 쓴다."""
    from capa_simulation.components.equipment_master_tab import LOAD_LATEST_BUTTON_KEY

    browser = install_fragment_browser(monkeypatch)
    grid = install_fake_grid(monkeypatch)
    repository, setup = _two_scenarios(tmp_path)
    app = AppTest.from_string(_page_script(PAGE, repository.database_path), default_timeout=90)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": None}
    _ok(app.run())
    load(app, [], kind="all")
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "시나리오 메모", "text": "낡기 전"})
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    slots = _slot_matrix(app, browser)
    app.session_state[emt.TABLE_KEY] = emt.TABLE_MASTER
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    assert any(item.key == LOAD_LATEST_BUTTON_KEY for item in app.button)
    assert len(set(slots.values())) == 1, slots


def _editor_id(page: _Page, key: str) -> str:
    """작은 편집표(세대를 붙인 위젯 key 가 `key` 로 시작)를 그린 마지막 메시지의 위젯 id."""
    for message in reversed(page.browser.emitted or page.browser.messages):
        if message.WhichOneof("type") != "delta":
            continue
        if message.delta.WhichOneof("type") != "new_element":
            continue
        kind = message.delta.new_element.WhichOneof("type")
        widget_id = str(getattr(getattr(message.delta.new_element, kind), "id", "")) if kind else ""
        if f"-{key}__" in widget_id:
            return widget_id
    raise AssertionError(f"{key} 편집표를 그린 메시지가 없다")


def _editor_draws(page: _Page, key: str) -> int:
    """마지막 `run()` 안의 모든 회차가 작은 편집표(세대를 붙인 위젯 key 가 `key` 로 시작)를 그린
    수 — 구역 회차에 본문이 돌았는지 본다."""
    drawn = 0
    for message in page.browser.emitted:
        if message.WhichOneof("type") != "delta":
            continue
        if message.delta.WhichOneof("type") != "new_element":
            continue
        kind = message.delta.new_element.WhichOneof("type")
        widget_id = str(getattr(getattr(message.delta.new_element, kind), "id", "")) if kind else ""
        if f"-{key}__" in widget_id:
            drawn += 1
    return drawn


def _editor_rows(widget_id: str, added: list[dict[str, Any]]) -> WidgetState:
    """작은 편집표 위젯 값 — 더한 줄만(빈 목록이면 편집 없음)."""
    edit = {"edited_rows": {}, "added_rows": added, "deleted_rows": []}
    return WidgetState(id=widget_id, string_value=json.dumps(edit))


def test_switching_the_table_or_the_side_stays_in_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표 고르기 · 오른쪽 칸을 바꾸는 누름은 구역 회차 하나다 — 구역이 이벤트 칸에 쓰는 자리는 앱
    전체 회차와 같다. 작은 편집표에 적용하지 않은 편집이 생기거나 걷히면(탭 점 · 떠나기 확인) 편집표
    콜백 끝에서 올라간다 — 구역 본문은 돌지 않고 올라간 앱 전체 회차가 편집표를 한 번 그린다(AGENTS
    9장 R8 — 편집표는 떠나기 명부 밖이다)."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    app_slots = _scope_event_slots(page)

    page.app.segmented_control(key=SIDE_KEY).set_value(SIDE_CHANGES)
    page.send()
    assert page.browser.started == [[page.scope]]
    assert _scope_event_slots(page) == app_slots

    page.app.segmented_control(key=emt.TABLE_KEY).set_value(BASELINE_TARGET)
    page.send()
    assert page.browser.started == [[page.scope]]
    assert _scope_event_slots(page) == app_slots
    assert all(message.delta.fragment_id == page.scope for message in _deltas(page))

    row = {"공정": "DEMO-P", "분류": "DEMO-K", "기존보유대수": 3}
    page.send(_editor_rows(_editor_id(page, edw.BASELINE_EDITOR_KEY), [row]))
    assert page.browser.started == [[page.scope], []], "적용하지 않은 편집이 서면 올라간다"
    assert _editor_draws(page, edw.BASELINE_EDITOR_KEY) == 1, "콜백 끝에서 올라간다"
    page.send(_editor_rows(_editor_id(page, edw.BASELINE_EDITOR_KEY), []))
    assert page.browser.started == [[page.scope], []], "그 편집이 걷히면 올라간다"
    assert _editor_draws(page, edw.BASELINE_EDITOR_KEY) == 1, "콜백 끝에서 올라간다"

    page.app.segmented_control(key=emt.TABLE_KEY).set_value(emt.TABLE_MASTER)
    page.send()
    assert page.browser.started == [[page.scope]]
    assert _scope_event_slots(page) == app_slots


def test_a_small_editor_first_edit_with_the_apply_press_in_one_request_is_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """작은 편집표의 첫 칸과 「편집본에 적용」 누름이 한 요청에 실리면 편집표 콜백 끝에서 올리지
    않는다 — 그 올리기는 같은 상호작용의 누름을 버린다. 구역 본문이 누름을 판정해 편집을 편집본에
    넣고 앱 전체 회차로 끝난다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.app.segmented_control(key=emt.TABLE_KEY).set_value(BASELINE_TARGET)
    page.send()
    row = {"공정": "DEMO-P", "분류": "DEMO-K", "기존보유대수": 3}

    page.send(
        _editor_rows(_editor_id(page, edw.BASELINE_EDITOR_KEY), [row]),
        WidgetState(id=page.browser.widget_id_of(BASELINE_APPLY), trigger_value=True),
    )

    assert page.browser.started == [[page.scope], []]
    assert "DEMO-P" in set(page.app.session_state[BUFFER_KEY][0]["공정"]), "누름이 버려졌다"


def _detail_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Page:
    """오른쪽 칸 「호기 상세」 를 연 탭 ①."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_DETAIL
    page.send(scope=False)
    return page


def test_going_to_the_downtime_table_stays_in_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「비가동 일정 표에서 고치기」(트리거 `goto`)는 표 고르기를 비가동 일정으로, 그 표 설비명
    거르기를 그 호기로 바꾸는 구역 회차 하나다 — 그 회차가 비가동 일정 작은 편집표를 그린다."""
    page = _detail_page(tmp_path, monkeypatch)
    app_slots = _scope_event_slots(page)
    page.trigger(emg.side_key("detail"), "goto", {"table": DOWNTIME_TARGET, "unit": "DA-01"})

    assert page.browser.started == [[page.scope]]
    assert page.app.session_state[emt.TABLE_KEY] == DOWNTIME_TARGET
    unit_filter = filter_widget_key(edw.DOWNTIME_VIEW_PREFIX, EQUIPMENT_ID_COLUMN)
    assert page.app.session_state[unit_filter] == ["DA-01"]
    assert _editor_id(page, edw.DOWNTIME_EDITOR_KEY)
    assert _scope_event_slots(page) == app_slots


def test_copying_a_unit_into_a_new_one_stays_in_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「이 호기로 새 호기 만들기」(트리거 `copy`)는 그 호기 값을 「새 호기」 초안에 담고 오른쪽
    칸을 「새 호기」 로 여는 구역 회차 하나다."""
    page = _detail_page(tmp_path, monkeypatch)
    app_slots = _scope_event_slots(page)
    page.trigger(emg.side_key("detail"), "copy", {"id": "s:DA-01"})

    assert page.browser.started == [[page.scope]]
    assert page.app.session_state[SIDE_KEY] == SIDE_NEW
    assert page.app.session_state[edw.NEW_UNIT_DRAFT_KEY]["seq"] == 1
    assert page.browser.widget_id_of(emg.side_key("new"))
    assert _scope_event_slots(page) == app_slots


# ------------------------------------------------------------------ 앱 전체로 오르는 조작


def test_save_discard_and_the_import_popup_rise_at_the_callback_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「리비전 저장」 · 「모두 버리기」 · 「엑셀·CSV로 한꺼번에」 팝업 열기는 하는 일이 탭
    밖(페이지가 세우는 세션 · 편집본, 팝업 호스트)에 닿아 콜백 끝에서 앱 전체로 올라간다."""
    page, path = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_CHANGES
    page.send(scope=False)
    page.outbox(_cell("DA-01", "담당자", "저장할 값"))
    revisions = len(DuckDBEquipmentRepository(path).list_revisions())

    page.press(SAVE_BUTTON_KEY)
    assert page.browser.started == [[page.scope], []]
    assert len(DuckDBEquipmentRepository(path).list_revisions()) == revisions + 1
    assert not has_unsaved_equipment_edits_after(page)

    page.outbox(_cell("DA-02", "담당자", "버릴 값"))
    page.press(DISCARD_CONFIRM_KEY)
    assert page.browser.started == [[page.scope], []]
    assert str(_value(page.app, "DA-02", "담당자")) != "버릴 값"

    page.trigger(emg.LOADER_KEY, "dialog", {"name": "import"})
    assert page.browser.started == [[page.scope], []]
    assert page.app.session_state[EQUIPMENT_DIALOG_KEY] == "import"


def has_unsaved_equipment_edits_after(page: _Page) -> bool:
    """세운 세대보다 편집본 세대가 오르고 저장본으로 돌아온 세대가 아닌가(미저장 표시 판정)."""
    seeded = page.app.session_state["equipment_workspace_seeded_generation_v1"]
    generation = page.app.session_state["equipment_workspace_buffer_generation_v1"]
    return bool(generation > seeded)


def _theirs_common_save(path: Path) -> None:
    """다른 사용자가 공통 칸(담당자)을 고쳐 공통 대장을 저장한다(이 프로세스의 쓰기 세대는 그대로 —
    다른 앱 프로세스처럼 DB stat 이 바뀐다)."""
    repository = DuckDBEquipmentRepository(path)
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "DA-01", "담당자", "남의 값"))
    )


def test_a_save_by_someone_else_rises_after_the_body_and_the_one_shot_mark_goes_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남이 공통 대장을 저장한 뒤의 칸 고침은 미저장 표시가 그대로여도 구역 본문을 그린 뒤 앱
    전체로 올라간다(저장 토큰 — R4). 그 구역 회차는 편집본이 낡았다고 본문에 넘기고(작은 편집표
    제출 거절), 앱 전체 회차의 편집본 세우기가 새 저장본으로 다시 세운다(머리가 센 편집을 버려 한
    번 더 돈다). 그 앱 전체 회차가 넘긴 한 번만 쓰는 표지(`drafts_replaced`)는 다음 구역 회차에서
    꺼진다."""
    page, path = _scope_page(tmp_path, monkeypatch)
    seen: list[bool] = []
    draw = emt.render_equipment_master_tab

    def recorded(**kwargs: Any) -> None:
        seen.append(bool(kwargs["drafts_replaced"]))
        draw(**kwargs)

    monkeypatch.setattr(emt, "render_equipment_master_tab", recorded)
    page.outbox(_cell("DA-02", "담당자", "내 값"))
    _theirs_common_save(path)
    seen.clear()

    page.outbox(_cell("DA-02", "메모1", "남의 저장 뒤 값"))
    assert page.browser.started[:2] == [[page.scope], []]
    assert seen[:2] == [True, True], "구역 본문을 그린 뒤 앱 전체 회차가 편집본을 다시 세웠다"
    assert _value(page.app, "DA-01", "담당자") == "남의 값"

    seen.clear()
    page.outbox(_cell("DA-01", "메모1", "다시 세운 뒤 값"))
    assert page.browser.started[0] == [page.scope]
    assert seen[0] is False, "한 번만 쓰는 표지는 구역 회차에서 꺼진다"


def test_a_scope_run_reads_the_equipment_database_under_one_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """구역 회차는 `app.py` 의 실행 핀 밖에서 돈다 — 저장 토큰 읽기와 본문의 설비 DB 읽기가 핀 하나
    안이다(캐시를 비운 회차라 둘 다 DB 를 연다)."""
    page, path = _scope_page(tmp_path, monkeypatch)
    page.outbox(_cell("DA-01", "담당자", "첫 값"))
    key = sql_helpers._pin_key(path)
    taken: list[bool] = []
    take = sql_helpers._take_pin

    def watched(database_path: Path) -> None:
        if sql_helpers._pin_key(database_path) == key:
            taken.append(key in sql_helpers._PIN_TARGETS.slots)
        take(database_path)

    monkeypatch.setattr(sql_helpers, "_take_pin", watched)
    st.cache_data.clear()
    page.outbox(_cell("DA-02", "담당자", "둘째 값"))
    assert page.browser.started == [[page.scope]]
    assert taken, "구역 회차가 설비 DB 를 열지 않았다"
    assert all(taken), taken


def test_a_save_by_someone_else_before_the_stamp_is_seen_by_the_next_scope_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱 전체 회차 안에서 페이지가 세션 · 편집본을 세운 뒤 · 탭 본문이 저장 토큰을 찍기 전에 남이
    공통 대장을 저장한다. 그 회차는 편집본을 세운 쌍(페이지가 본 값)을 찍으므로 다음 구역 회차가
    남의 저장을 알아보고 본문 뒤에서 올라가 그 앱 전체 회차가 편집본을 다시 세운다 — 낡은 편집본에
    칸이 쌓이지 않는다."""
    page, path = _scope_page(tmp_path, monkeypatch)
    fired: list[bool] = []
    give = emt._Handoff.give

    def racing(self: emt._Handoff, materials: emt.MasterMaterials) -> None:
        if not fired:
            fired.append(True)
            _theirs_common_save(path)
        give(self, materials)

    monkeypatch.setattr(emt._Handoff, "give", racing)
    page.outbox(_cell("DA-02", "담당자", "첫 값"))
    assert fired and page.browser.started == [[page.scope], []]
    monkeypatch.setattr(emt._Handoff, "give", give)

    page.outbox(_cell("DA-02", "메모1", "둘째 값"))
    assert page.browser.started[:2] == [[page.scope], []]
    assert _value(page.app, "DA-01", "담당자") == "남의 값"


def _small_editor_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[_Page, Path]:
    """기존 보유대수 작은 편집표를 연 탭 ①."""
    page, path = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[emt.TABLE_KEY] = BASELINE_TARGET
    page.send(scope=False)
    return page, path


def _queued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """작은 편집표가 담는 알림 (칸, 글)."""
    queued: list[tuple[str, str]] = []

    def spy(key: str, message: str, **kwargs: Any) -> None:
        queued.append((key, message))
        queue_flash(key, message, **kwargs)

    monkeypatch.setattr(edw, "queue_flash", spy)
    return queued


@pytest.mark.parametrize("scope", [True, False], ids=["scope", "app"])
def test_a_small_editor_submit_after_someone_elses_save_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: bool
) -> None:
    """남이 저장한 뒤 누른 작은 편집표 「편집본에 적용」 은 낡은 편집본에 넣지 않고 거절한다 — 앱
    전체 회차는 페이지의 편집본 세우기가 넘긴 표지로, 구역 회차는 그 표지가 꺼지므로 구역 안에서
    다시 판정해서. 거절 글은 다시 세운 편집본 위의 작은 편집표 자리에 선다."""
    page, path = _small_editor_page(tmp_path, monkeypatch)
    queued = _queued(monkeypatch)
    applied: list[bool] = []
    remember = edw._remember_edits

    def recorded(*args: Any, **kwargs: Any) -> None:
        applied.append(True)
        remember(*args, **kwargs)

    monkeypatch.setattr(edw, "_remember_edits", recorded)
    _theirs_common_save(path)
    page.send(
        WidgetState(id=page.browser.widget_id_of(BASELINE_APPLY), trigger_value=True), scope=scope
    )

    assert page.browser.started[0] == ([page.scope] if scope else [])
    assert not applied, "낡은 편집본에 제출을 넣었다"
    assert [key for key, text in queued if REFUSED_SUBMIT in text] == [edw._ERROR_KEY]
    assert any(REFUSED_SUBMIT in str(item.value) for item in page.app.error)
    assert _value(page.app, "DA-01", "담당자") == "남의 값"


def test_a_small_editor_submit_after_my_cut_save_blames_no_one_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """제 「리비전 저장」 이 쓰기 뒤 끊긴 사이(뒷정리 대기)에 누른 작은 편집표 제출은 구역 회차의
    저장 토큰이 달라도 남의 저장으로 거절하지 않는다 — 올라간 앱 전체 회차가 끊긴 제 저장을
    잇는다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_CHANGES
    page.send(scope=False)
    page.outbox(_cell("DA-01", "담당자", "저장할 값"))
    page.app.session_state[emt.TABLE_KEY] = BASELINE_TARGET
    page.send(scope=False)
    queued = _queued(monkeypatch)
    _first_callback(
        page.app,
        monkeypatch,
        "_save_revision",
        cut_after=(DuckDBEquipmentRepository, "save_equipment"),
    )
    page.press(BASELINE_APPLY)

    assert page.browser.started[0] == [page.scope]
    assert not [text for _key, text in queued if REFUSED_SUBMIT in text]
    _no_foreign_blame(page.app)
    assert _value(page.app, "DA-01", "담당자") == "저장할 값"


# ------------------------------------------------------------------ 구역 회차의 다른 조작


def test_a_new_unit_draft_stays_in_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「새 호기」 칸 초안(상태 값 `draft`)은 구역 회차 하나다 — 세션 초안에 적는다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_NEW
    page.send(scope=False)
    values = [""] * len(EQUIPMENT_COLUMNS)
    values[0] = "NEW-01"
    draft = {"draft": {"seq": 5, "values": values}}
    key = emg.side_key("new")
    page.send(WidgetState(id=page.browser.widget_id_of(key), json_value=json.dumps(draft)))

    assert page.browser.started == [[page.scope]]
    assert page.app.session_state[edw.NEW_UNIT_DRAFT_KEY] == {"seq": 5, "values": values}


def test_an_undo_rises_only_when_it_returns_to_the_saved_buffer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「한 단계 되돌리기」 는 미저장 표시가 그대로면 구역 회차 하나이고, 저장본으로 돌아오면(탭
    점 · 변경 칩이 걷힘) 콜백 끝에서 앱 전체로 올라간다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_CHANGES
    page.send(scope=False)
    before = [str(_value(page.app, name, "담당자")) for name in ("DA-01", "DA-02")]
    page.outbox(_cell("DA-01", "담당자", "첫 값"))
    page.outbox(_cell("DA-02", "담당자", "둘째 값"))
    assert page.browser.started == [[page.scope]]

    page.press(UNDO_BUTTON_KEY)
    assert page.browser.started == [[page.scope]]
    assert _value(page.app, "DA-01", "담당자") == "첫 값"
    assert str(_value(page.app, "DA-02", "담당자")) == before[1]

    page.press(UNDO_BUTTON_KEY)
    assert page.browser.started == [[page.scope], []]
    assert str(_value(page.app, "DA-01", "담당자")) == before[0]


def test_an_outbox_refused_by_the_grade_rises_and_raises_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설비 마스터를 고칠 수 없는 등급(열람)의 표 출납은 받지 않고 거절을 담는다 — 받기 콜백 끝에서
    앱 전체로 올라가 그 회차가 거절 알림을 낸다(구역 회차에는 낼 자리가 없다)."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    preview(monkeypatch, grades.VIEWER)
    page.send(scope=False)
    before = str(_value(page.app, "DA-01", "담당자"))
    page.app.session_state[RUN_HEAD_KEY] = grade_ui.emit
    page.outbox(_cell("DA-01", "담당자", "막힐 값"))

    assert page.browser.started == [[page.scope], []]
    assert str(_value(page.app, "DA-01", "담당자")) == before
    assert grade_ui.PENDING_KEY not in page.app.session_state
    refusals = [
        str(note.get("full"))
        for note in alert_notes(page.app, again=True)
        if note.get("origin") == grade_ui.GRADE_FLASH_KEY
    ]
    assert refusals == [grades.refusal_text(TABLE_ACTIONS[emt.TABLE_MASTER])]


def test_loading_the_latest_revision_in_a_scope_run_rises_at_the_callback_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """낡은 세션의 낡기 전 편집이 저장을 막아 선 「최신 rN 불러오기(변경 버림)」 를 구역 회차에서
    누르면 세션을 옮기고 콜백 끝에서 앱 전체로 올라간다(구역 본문은 돌지 않는다) — 그 회차가 옮긴
    리비전으로 편집본을 다시 세운다."""
    page, path = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_CHANGES
    page.send(scope=False)
    page.outbox(_cell("DA-01", "반입일정", "2026-12-01"))
    repository = DuckDBEquipmentRepository(path)
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "DA-02", "반입일정", "2026-11-30"))
    )
    latest = next(
        item.latest_schedule_revision_id
        for item in repository.list_equipment_scenarios()
        if item.equipment_scenario_id == page.app.session_state[SELECTION_KEY]["scenario_id"]
    )
    page.send(scope=False)
    assert page.app.session_state[SELECTION_KEY]["schedule_revision_id"] != latest

    page.press(LOAD_LATEST_BUTTON_KEY)
    assert page.browser.started[:2] == [[page.scope], []]
    assert _grid_draws(page) == len(page.browser.started) - 1, "구역 본문은 돌지 않는다"
    assert page.app.session_state[SELECTION_KEY]["schedule_revision_id"] == latest


# ------------------------------------------------------------------ 제 저장 이음


@pytest.mark.parametrize(
    "first",
    [("담당자", "저장 전 값"), ("반입일정", "2026-12-01")],
    ids=["common", "schedule"],
)
def test_a_cell_after_my_cut_save_rises_and_lands_on_the_rebuilt_buffer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first: tuple[str, str]
) -> None:
    """제 「리비전 저장」 이 DB 에 쓴 뒤 끊기고(fastReruns) 다음 칸이 구역 회차로 닿는다 — 받기
    콜백은 옛 편집본에 얹지 않고 미루며, 뒷정리 대기(`own_save_unsettled`)가 머리 표지를 바꿔 콜백
    끝에서 앱 전체로 올라간다. 그 회차가 끊긴 제 저장을 이어 다시 세운 편집본(새 일정 리비전을
    썼으면 세션을 옮긴 뒤)에 그 칸을 얹고 ack 를 싣는다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_CHANGES
    page.send(scope=False)
    page.outbox(
        {"op": "paste", "ids": ["s:DA-01"], "cols": [first[0]], "rows": [[first[1]]]}
        | {"cut": 0, "skipped": 0}
    )
    page.send(scope=False)
    _first_callback(
        page.app,
        monkeypatch,
        "_save_revision",
        cut_after=(DuckDBEquipmentRepository, "save_equipment"),
    )
    seq = page.outbox(_cell("DA-02", "담당자", "저장 직후 값"))

    assert page.browser.started[:2] == [[page.scope], []]
    app_runs = len(page.browser.started) - 1
    assert _grid_draws(page) == app_runs, "콜백 끝에서 올라 구역 본문은 돌지 않는다"
    assert page.ack() == {"mount": MOUNT, "seq": seq}
    assert str(_value(page.app, "DA-01", first[0]))[: len(first[1])] == first[1]
    assert _value(page.app, "DA-02", "담당자") == "저장 직후 값"
    page.send(scope=False)
    assert _value(page.app, "DA-02", "담당자") == "저장 직후 값"


def test_a_cell_landing_while_my_scope_save_writes_is_taken_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """구역 회차의 「리비전 저장」 이 DB 에 쓰는 사이 다른 회차의 받기 콜백이 옛 편집본에 칸을 얹고
    ack 를 그린다(Streamlit 1.63 은 그 회차를 다른 스레드로 세운다 — 여기서는 쓰기 안에서 그 콜백을
    부른다). 저장 콜백 끝에서 앱 전체로 올라가 다시 세운 편집본에 그 칸을 다시 얹는다."""
    page, _ = _scope_page(tmp_path, monkeypatch)
    page.app.session_state[SIDE_KEY] = SIDE_CHANGES
    page.send(scope=False)
    page.outbox(_cell("DA-01", "담당자", "저장 전 값"))
    base = page.base()
    late = {"seq": next(_SEQ), "at": 0, "base": base, **_cell("DA-02", "담당자", "쓰는 사이 값")}
    metadata = page.app.session_state._state._new_widget_state.widget_metadata
    callbacks = metadata[page.browser.widget_id_of(emg.GRID_KEY)].callbacks or {}
    on_outbox = callbacks["outbox"]
    original = DuckDBEquipmentRepository.save_equipment
    fired: list[bool] = []

    def writing(self: DuckDBEquipmentRepository, *args: Any, **kwargs: Any) -> Any:
        if not fired:
            fired.append(True)
            st.session_state[emg.GRID_KEY] = {"outbox": {"mount": MOUNT, "ops": [late]}}
            on_outbox()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(DuckDBEquipmentRepository, "save_equipment", writing)
    page.press(SAVE_BUTTON_KEY)

    assert fired
    assert page.browser.started[:2] == [[page.scope], []]
    assert _value(page.app, "DA-01", "담당자") == "저장 전 값"
    assert _value(page.app, "DA-02", "담당자") == "쓰는 사이 값"
    assert OWN_SAVE_CARRY_KEY in page.app.session_state
    assert isinstance(page.app.session_state[BUFFER_KEY], tuple)


@pytest.mark.parametrize("moved", [True, False], ids=["moved", "refused"])
def test_loading_the_latest_revision_rises_only_when_the_session_moved(
    monkeypatch: pytest.MonkeyPatch, moved: bool
) -> None:
    """「최신 rN 불러오기(변경 버림)」 콜백은 세션을 옮겼을 때만 그 상호작용을 앱 전체 회차로 한다 —
    세션 · 편집본은 페이지 회차가 세운다. 옮기지 못한 까닭은 단추 아래 칸(구역 안)이 말한다."""
    from capa_simulation.components import equipment_scenario_status, fragment_scope

    rises: list[bool] = []
    monkeypatch.setattr(equipment_scenario_status, "_move_to_latest", lambda *args: moved)
    monkeypatch.setattr(fragment_scope, "escalate", lambda: rises.append(True))
    equipment_scenario_status._load_latest("equipment.duckdb", "s1", "r2", "가정", 2)
    assert rises == ([True] if moved else [])
