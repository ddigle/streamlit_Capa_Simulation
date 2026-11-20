# Purpose: 목록 관리 두 칸의 구역 회차(올리기 · ack · 알약 · 이벤트 칸 자리 · 숨은 탭 · DB 핀 · 읽기
# 실패)를 잰다.

"""목록 관리 두 칸(`components/scenario_management._render_list_scope`)의 편집기 구역 회차.

`tests/fragment_browser.py` 대역으로 브라우저처럼 구역 안 부품(목록 표 Components v2)의 상태 값을 그
구역만 도는 요청으로 보낸다(AGENTS 9장 「구역 회차 규칙」).

- **줄 고르기**는 구역 회차 하나다 — 오른쪽 칸이 새 시나리오로 서고 ack 가 남는다. 구역
  밖(사이드바 · 머리 · 다른 탭)은 다시 그려지지 않는다.
- **첫 고침**은 화면 탭 점 · 변경 칩이 바뀌어 콜백 끝에서 앱 전체로 올라가고(ack 가 남는다), 다음
  고침은 구역 회차로 「저장 전 변경 n건」 알약의 수만 고친다(구역이 바깥 칸에 쓴다).
- **오른쪽 칸 바꿈 · 불러오기 · 저장**은 앱 전체로 올라가고, **「공식으로 지정…」** 은 구역 회차의
  누름이어도 팝업 호스트만 돈다(2026-11-08 U5).
- **구역 회차의 목록 읽기 실패**는 올리지 않고 코어 화면 카드(R6)로 멈춘다 — 서버 세션에 출납
  상태 값이 남는다(대역은 브라우저가 그 구역의 다시 그리지 않은 마운트를 걷는 것을 흉내 내지
  않는다).
- **이벤트 칸 자리 수(R5)** — 오른쪽 칸 다섯이 같은 수를 쓰고, 구역 회차는 앱 전체 회차에 구역이
  쓴 자리만 다시 쓴다. 결과 칸(`render_flash`)이 서지 않는 갈래는 빈 스타일로 채운다.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import pytest
import streamlit as st
from fragment_browser import FragmentBrowser, install_fragment_browser
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script

import capa_simulation.persistence._sql_helpers as sql_helpers
import capa_simulation.settings as settings
from capa_simulation.components import fragment_scope, scenario_list_grid
from capa_simulation.components.page_failure_card import CARD_KEY
from capa_simulation.components.scenario_list_state import (
    CHECKS_KEY,
    DRAFT_KEY,
    LIST_SCOPE,
    REVISIONS_KEY,
    SIDE_CHECK,
    TABLE_KEY,
)
from capa_simulation.components.scenario_management import (
    CARD_LOAD_KEY,
    CARD_OFFICIAL_KEY,
    OFFICIAL_DIALOG_KEY,
    OFFICIAL_HOST,
    SIDE_CHANGES,
    SIDE_KEY,
    SIDES,
)
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_SCENARIO_ID_KEY

PAGE_PATH = "app_pages/scenario_management.py"


def _event_slot_count(messages: Sequence[ForwardMsg]) -> int:
    """그 회차가 이벤트 칸(본문 밖 최상위 칸)에 쓴 자리 수."""
    count = 0
    for message in messages:
        if message.WhichOneof("type") != "delta":
            continue
        path = list(message.metadata.delta_path)
        if len(path) == 2 and path[0] == RootContainer.EVENT:
            count = max(count, path[1] + 1)
    return count


def test_every_side_writes_the_same_event_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """오른쪽 칸 다섯(상세 · 점검 · 저장 전 변경 · 공식 이력 · 보관함)이 이벤트 칸에 같은 수의
    자리를 쓴다 — 결과 칸이 없는 공식 이력 · 보관함도 빈 스타일 한 자리다."""
    browser = install_fragment_browser(monkeypatch)
    script = _page_script(PAGE_PATH, tmp_path / "scenario.duckdb", tmp_path / "equipment.duckdb")
    app = AppTest.from_string(script, default_timeout=120)
    counts: dict[str, int] = {}
    for side in SIDES:
        app.session_state[SIDE_KEY] = side
        app.run()
        assert not app.exception, [element.message for element in app.exception]
        counts[side] = _event_slot_count(browser.messages)

    assert len(set(counts.values())) == 1, counts


# ------------------------------------------------------------------ 구역 회차


_SEQ = itertools.count(1)


def _live_list_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """목록 표를 이 AppTest 회차 **안에서** 등록해 진짜 상태 값 칸을 세운다 — 모듈을 읽을 때 등록한
    것은 AppTest 실행 밖이라 그 실행에서 「미등록」이다."""
    assets = scenario_list_grid._ASSETS

    def live(**kwargs: Any) -> Any:
        component = st.components.v2.component(
            "capa_scenario_list_grid",
            html=(assets / "grid.html").read_text(encoding="utf-8"),
            css=scenario_list_grid.registered_css(),
            js=scenario_list_grid.registered_js(),
        )
        return component(**kwargs)

    monkeypatch.setattr(scenario_list_grid, "_GRID", live)


def _second_scenario(database_path: Path) -> str:
    """내장 시드 공식 리비전을 그대로 복제한 둘째 시나리오 — 리비전 둘(「점검」 칸에서 고른다)."""
    repository = DuckDBScenarioRepository(database_path)
    release = repository.latest_official_release()
    assert release is not None
    official = repository.load_revision(release.revision_id)
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="둘째 시나리오",
            source_simulation_code="SECOND-1",
            source_simulation_name="둘째 시나리오",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="test-v1",
        ),
        official.tables,
        official.preset,
    )
    repository.save_revision(
        created.scenario.scenario_id,
        official.tables,
        official.preset,
        revision_name="둘째 리비전",
        parent_revision_id=created.revision.revision_id,
    )
    return created.scenario.scenario_id


def _scope_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AppTest, FragmentBrowser, str, str]:
    """시나리오 둘(내장 시드 · 복제)을 든 시나리오 관리 화면 — (앱, 대역, 구역 id, 둘째 시나리오).
    앱 전체 회차의 실행 표지(`app.py` 처럼)를 달아 팝업 여는 콜백이 호스트만 돌릴 수 있다."""
    database_path = tmp_path / "scenario.duckdb"
    script = (
        "from capa_simulation.sidebar_status import begin_app_run\n"
        "app_run = begin_app_run()\n"
        + _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
        + "app_run.finish()\n"
    )
    assert not AppTest.from_string(script, default_timeout=120).run().exception
    second = _second_scenario(database_path)
    # 구역만 도는 회차는 페이지 대본(시험 DB 자리로 바꿔 끼우는 `_page_script`)을 지나지 않는다 —
    # 시험 동안 DB 자리를 시험 DB 로 둔다.
    monkeypatch.setattr(settings, "DUCKDB_PATH", database_path)
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    browser = install_fragment_browser(monkeypatch)
    _live_list_grid(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception, [element.message for element in app.exception]
    return app, browser, browser.fragment_keyed(LIST_SCOPE), second


def _send(app: AppTest, browser: FragmentBrowser, key: str, *ops: dict[str, Any]) -> int:
    """그 마운트에서 op 들을 보낸다(구역 안 부품이라 구역만 도는 요청) — 마지막 seq."""
    base = browser.bidi_data(key)["base"]
    numbered = [{"seq": next(_SEQ), "at": 0, "base": base, **op} for op in ops]
    browser.send_state(app, key, {"outbox": {"mount": f"m-{key}", "ops": numbered}})
    assert not app.exception, [element.message for element in app.exception]
    return int(numbered[-1]["seq"])


def _ack(browser: FragmentBrowser, key: str) -> Any:
    return browser.bidi_data(key).get("ack")


def _deltas(messages: Sequence[ForwardMsg]) -> list[ForwardMsg]:
    return [message for message in messages if message.WhichOneof("type") == "delta"]


def _scope_event_slots(messages: Sequence[ForwardMsg], scope: str) -> set[int]:
    """구역이 이벤트 칸에 쓴 자리."""
    return {
        list(message.metadata.delta_path)[1]
        for message in _deltas(messages)
        if message.delta.fragment_id == scope
        and len(message.metadata.delta_path) == 2
        and message.metadata.delta_path[0] == RootContainer.EVENT
    }


def _badges(messages: Sequence[ForwardMsg]) -> list[tuple[str, str]]:
    """그 회차가 쓴 「저장 전 변경 n건」 알약 — (글, 쓴 프래그먼트)."""
    found = []
    for message in _deltas(messages):
        delta = message.delta
        if delta.WhichOneof("type") != "new_element":
            continue
        if delta.new_element.WhichOneof("type") != "markdown":
            continue
        body = delta.new_element.markdown.body
        if "저장 전 변경" in body and "-badge[" in body:
            found.append((body, delta.fragment_id))
    return found


def test_a_row_pick_is_one_scope_run_that_keeps_its_ack_and_leaves_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """줄 고르기(`open`)는 구역 회차 하나다 — 오른쪽 칸 리비전 표가 새 시나리오로 서고 표는 보낸
    op 의 ack 를 받는다. 그 회차의 델타는 모두 구역 것이다 — 사이드바 · 머리 · 숨은 탭(설비 시나리오
    · DB 등록 · 자동 갱신)은 돌지 않는다. 구역이 이벤트 칸에 쓰는 자리는 앱 전체 회차와 같다(R5)."""
    app, browser, scope, second = _scope_app(tmp_path, monkeypatch)
    app_slots = _scope_event_slots(browser.messages, scope)
    assert app_slots, "구역이 이벤트 칸에 쓴 자리가 없다"

    seq = _send(app, browser, TABLE_KEY, {"op": "open", "id": second})

    assert browser.started == [[scope]]
    assert _ack(browser, TABLE_KEY) == {"mount": f"m-{TABLE_KEY}", "seq": seq}
    assert browser.bidi_data(REVISIONS_KEY)["owner"] == second
    assert all(message.delta.fragment_id == scope for message in _deltas(browser.messages))
    assert _scope_event_slots(browser.messages, scope) == app_slots


def test_a_scope_run_reads_the_database_under_one_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """구역 회차는 `app.py` 의 실행 핀 밖에서 돈다 — 구역 본문이 핀(`pinned_connections`)을 스스로
    잡아 줄 고르기 한 번의 읽기(목록 · 공식 이력 · 리비전 …)가 DuckDB 인스턴스 하나를 나눠 쓴다.
    핀이 없으면 연결마다 인스턴스를 새로 만들고 닫을 때 체크포인트를 돈다."""
    app, browser, scope, second = _scope_app(tmp_path, monkeypatch)
    key = sql_helpers._pin_key(tmp_path / "scenario.duckdb")
    under_pin: list[bool] = []
    take_pin = sql_helpers._take_pin

    def watched(database_path: Path) -> None:
        if sql_helpers._pin_key(database_path) == key:
            under_pin.append(key in sql_helpers._PIN_TARGETS.slots)
        take_pin(database_path)

    monkeypatch.setattr(sql_helpers, "_take_pin", watched)
    _send(app, browser, TABLE_KEY, {"op": "open", "id": second})

    assert browser.started == [[scope]]
    assert len(under_pin) >= 2, under_pin
    assert all(under_pin), under_pin


def test_a_scope_run_that_cannot_read_the_list_stops_on_the_card_and_keeps_the_outbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """구역 회차에 목록을 읽지 못하면(`BOOTSTRAP_ERRORS` — 다른 프로세스가 잠깐 쥔 잠금) 그 구역
    자리에 코어 화면 카드(R6)가 서고 회차는 멈춤으로 끝난다 — 구역 위젯을 그리기 전에 앱 전체로
    올리지 않는다(R1). 멈춘 회차는 서버 세션에서 그리지 못한 구역 위젯의 상태 값을 지우지 않으므로
    보낸 op 의 출납이 세션에 남는다. 이 시험은 서버 몫까지만 본다 — 브라우저는 그 구역에서 다시
    그리지 않은 목록 마운트를 걷어 다음 회차에 새 마운트로 세우므로 옛 마운트 op 의 ack 가 닿는다고
    기대지 않는다(AGENTS 9장 R6)."""
    app, browser, scope, second = _scope_app(tmp_path, monkeypatch)
    list_scenarios = DuckDBScenarioRepository.list_scenarios

    def locked(self: DuckDBScenarioRepository, *args: Any, **kwargs: Any) -> Any:
        if fragment_scope.fragment_only_run():
            raise duckdb.IOException("잠김")
        return list_scenarios(self, *args, **kwargs)

    monkeypatch.setattr(DuckDBScenarioRepository, "list_scenarios", locked)
    seq = _send(app, browser, TABLE_KEY, {"op": "open", "id": second})

    outbox = app.session_state[TABLE_KEY].get("outbox") or {}
    assert [op["seq"] for op in outbox.get("ops", [])] == [seq], "출납 상태 값이 남는다"
    assert browser.started == [[scope]], "본문 앞에서 앱 전체로 올리지 않는다"
    blocks = [
        message.delta.add_block.id
        for message in _deltas(browser.emitted)
        if message.delta.WhichOneof("type") == "add_block"
    ]
    assert any(CARD_KEY in block for block in blocks), blocks


def test_the_first_rename_rises_and_the_next_counts_the_badge_in_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 이름 고침은 화면 탭 점 · 변경 칩(구역 밖)을 바꿔 콜백 끝에서 앱 전체로 올라간다 — 표는
    그 op 의 ack 를 받고 알약이 선다. 다음 고침은 구역 회차 하나이고 알약의 수는 구역이 「시나리오
    작업」 줄 바깥 칸에 다시 쓴다. 마지막 고침을 되돌리면 다시 올라가 알약이 걷힌다."""
    app, browser, scope, second = _scope_app(tmp_path, monkeypatch)
    first = app.session_state[DRAFT_KEY].opened
    seed = next(row["name"] for row in browser.bidi_data(TABLE_KEY)["rows"] if row["id"] == first)
    assert browser.bidi_data(TABLE_KEY)["clean"] is True

    seq = _send(
        app,
        browser,
        TABLE_KEY,
        {
            "op": "name",
            "kind": "scenario",
            "id": second,
            "text": "새 둘째",
            "seen": "둘째 시나리오",
        },
    )
    assert browser.started == [[scope], []]
    assert _ack(browser, TABLE_KEY) == {"mount": f"m-{TABLE_KEY}", "seq": seq}
    assert browser.bidi_data(TABLE_KEY)["clean"] is False
    assert [body for body, _ in _badges(browser.messages)] == [
        ":orange-badge[:material/edit_note: 저장 전 변경 1건]"
    ]

    seq = _send(
        app,
        browser,
        TABLE_KEY,
        {"op": "name", "kind": "scenario", "id": first, "text": "새 첫째", "seen": seed},
    )
    assert browser.started == [[scope]]
    assert _ack(browser, TABLE_KEY) == {"mount": f"m-{TABLE_KEY}", "seq": seq}
    (badge,) = _badges(browser.messages)
    assert "저장 전 변경 2건" in badge[0] and badge[1] == scope

    _send(app, browser, TABLE_KEY, {"op": "revert", "kind": "scenario", "id": first})
    assert browser.started == [[scope]]
    _send(app, browser, TABLE_KEY, {"op": "revert", "kind": "scenario", "id": second})
    assert browser.started == [[scope], []]
    assert _badges(browser.messages) == []
    assert browser.bidi_data(TABLE_KEY)["clean"] is True


def test_changing_the_side_panel_rises_after_the_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """오른쪽 칸 바꿈은 맨 위 칸이 대신 내는 결과 알림의 갈래(`_notices_without_a_place`)를 바꿔
    본문 뒤에서 앱 전체로 올라간다."""
    app, browser, scope, _ = _scope_app(tmp_path, monkeypatch)

    browser.fragment_queue = [scope]
    app.button_group(key=SIDE_KEY).set_value(SIDE_CHANGES).run()
    browser.fragment_queue = []

    assert not app.exception, [element.message for element in app.exception]
    assert browser.started == [[scope], []]
    assert app.session_state[SIDE_KEY] == SIDE_CHANGES


def test_loading_a_revision_from_the_scope_rises_to_the_app_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「선택한 리비전 불러오기」 는 올라와 있는 시나리오(머리 띠 · 사이드바 — 구역 밖)를 바꿔 콜백
    끝에서 앱 전체로 올라간다."""
    app, browser, scope, second = _scope_app(tmp_path, monkeypatch)
    _send(app, browser, TABLE_KEY, {"op": "open", "id": second})
    app.run()
    assert not app.exception

    browser.fragment_queue = [scope]
    app.button(key=f"{CARD_LOAD_KEY}_{second}").click().run()
    browser.fragment_queue = []

    assert not app.exception, [element.message for element in app.exception]
    assert browser.started == [[scope], []]
    assert app.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY] == second


def test_the_official_popup_opened_from_the_scope_runs_only_its_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「공식으로 지정…」 은 구역 안 단추라 그 누름은 구역 회차 요청이다 — 여는 콜백은
    팝업 호스트만 다시 돌린다(2026-11-08 U5 · UI-PRF-01). 호스트는 구역 밖이지만 구역도 페이지도
    다시 돌지 않는다."""
    app, browser, scope, _ = _scope_app(tmp_path, monkeypatch)
    opened = app.session_state[DRAFT_KEY].opened
    host = browser.fragment_keyed(OFFICIAL_HOST.key)

    browser.fragment_queue = [scope]
    app.button(key=f"{CARD_OFFICIAL_KEY}_{opened}").click().run()
    browser.fragment_queue = []

    assert not app.exception, [element.message for element in app.exception]
    assert browser.started == [[scope], [host]]
    assert app.session_state[OFFICIAL_DIALOG_KEY][0] == opened


def test_the_check_side_stays_in_the_scope_with_the_same_event_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「점검」 칸에서 다른 줄을 열고 리비전을 고르는 것은 같은 칸 안 조작이라 구역 회차 하나이고,
    구역이 이벤트 칸에 쓰는 자리는 앱 전체 회차와 같다(R5 — 묶음 줄 · 펼친 표 · 「행 보기」 도
    이벤트 칸을 쓰지 않는다. 내장 시드는 펼칠 행이 없어 「행 보기」 는 실제 브라우저로 본다)."""
    app, browser, scope, second = _scope_app(tmp_path, monkeypatch)
    app.session_state[SIDE_KEY] = SIDE_CHECK
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    app_slots = _scope_event_slots(browser.messages, scope)

    _send(app, browser, TABLE_KEY, {"op": "open", "id": second})
    assert browser.started == [[scope]], "다른 줄을 열어도 「점검」 칸은 그대로다"
    assert _scope_event_slots(browser.messages, scope) == app_slots
    data = browser.bidi_data(CHECKS_KEY)
    assert data["owner"] == second
    other = next(row["id"] for row in data["rows"] if row["id"] != data["picked"])

    _send(app, browser, CHECKS_KEY, {"op": "pick", "owner": data["owner"], "id": other})
    assert browser.started == [[scope]]
    assert browser.bidi_data(CHECKS_KEY)["picked"] == other
    assert _scope_event_slots(browser.messages, scope) == app_slots
