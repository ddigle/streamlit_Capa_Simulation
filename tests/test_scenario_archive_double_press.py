# Purpose: 보관·되돌리기·영구 삭제의 빠른 두 번 누름과 남이 먼저 처리한 시나리오의 누름을 본다.

"""시나리오 관리 › 목록 관리 › 「보관된 시나리오」(2026-10-27 E2E r6 static).

- 「되돌리기」 를 0.2초 간격으로 두 번 누르면 둘째 누름의 회차가 고른 보관본(이미 되돌렸다)을 다음
  보관본으로 바꾼 채(`prune_choice`) 같은 key 의 단추 누름을 받아 고르지 않은 보관본까지 되돌렸다.
  남이 먼저 되돌린 보관본에서 누른 것도 같았다. 브라우저는 고른 글자를 들고 다니므로 `BrowserChoice`
  로 그 글자를 그대로 보낸다.
- 「영구 삭제 실행」 을 빠르게 두 번 누르면 둘째 회차가 첫 삭제 전 목록을 그리고 저장소에 다시 가 날
  KeyError(「'시나리오를 찾을 수 없습니다: …'」)를 세웠고, 첫 회차가 쓴 뒤 끊기면 성공 알림이 하나도
  남지 않았다. 겹쳐 온 둘째 회차(첫 쓰기 전 목록)는 그 회차의 목록 읽기를 쓰기 전 목록으로 돌려
  만든다. 카드 「보관 실행」 도 같은 꼴이다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
from streamlit.testing.v1 import AppTest
from test_all_pages_render import _page_script
from test_scenario_management_page import PAGE_PATH, _clone_official
from widget_browser import BrowserChoice

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.pick_edit_table import TableDraft, draft_session_key
from capa_simulation.components.scenario_management import (
    ACTION_KEY,
    ARCHIVE_CONFIRM_KEY,
    ARCHIVED_GONE_MESSAGE,
    ARCHIVED_SELECT_KEY,
    DELETE_BUTTON_KEY,
    DELETE_CONFIRM_KEY,
    LIST_EDITOR_KEY,
)
from capa_simulation.persistence.models import ScenarioSummary
from capa_simulation.persistence.repository import DuckDBScenarioRepository

RESTORE_KEY = "scenario_archived_restore"
NAMES = ("보관 가", "보관 나", "보관 다")


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _archives(tmp_path: Path) -> tuple[str, DuckDBScenarioRepository]:
    """보관본 셋을 둔 페이지 대본과 저장소."""
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    _ok(AppTest.from_string(script, default_timeout=120).run())
    repository = DuckDBScenarioRepository(database_path)
    for index, name in enumerate(NAMES, start=1):
        archived = _clone_official(database_path, name, f"ARCHIVE-{index}")
        repository.archive_scenario(archived.scenario.scenario_id)
    return script, repository


def _statuses(repository: DuckDBScenarioRepository) -> dict[str, str]:
    return {
        item.scenario_name: item.status
        for item in repository.list_scenarios(include_archived=True)
        if item.scenario_name in NAMES
    }


def _texts(items: Any) -> list[str]:
    return [str(item.value) for item in items]


def _picked(script: str, middle: bool = True) -> tuple[AppTest, BrowserChoice, str]:
    """보관함 상자에서 가운데(또는 첫) 보관본을 고른 화면."""
    app = AppTest.from_string(script, default_timeout=120)
    browser = BrowserChoice(app, "selectbox", ARCHIVED_SELECT_KEY)
    _ok(browser.start())
    shown = browser.options()
    assert sorted(shown) == sorted(NAMES)
    target = shown[1] if middle else shown[0]
    browser.pick(target)
    _ok(browser.run())
    return app, browser, target


def test_a_second_restore_press_does_not_restore_an_archive_nobody_picked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """둘째 누름은 브라우저가 아직 든 옛 글자(이미 되돌린 보관본)로 온다 — 고르지 않은 보관본을
    되돌리지 않고, 첫 누름의 성공 알림이 남는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    script, repository = _archives(tmp_path)
    app, browser, target = _picked(script)

    app.button(key=RESTORE_KEY).click()
    _ok(browser.run())
    assert _statuses(repository)[target] == "ACTIVE"

    # 둘째 누름 — 브라우저는 아직 되돌리기 전 화면의 글자를 든 채 같은 단추를 누른다.
    browser.wire = target
    app.button(key=RESTORE_KEY).click()
    _ok(browser.run())
    statuses = _statuses(repository)
    assert [name for name, status in statuses.items() if status == "ACTIVE"] == [target], statuses
    assert any(f"{target}" in text and "되돌렸습니다" in text for text in _texts(app.success))
    assert ARCHIVED_GONE_MESSAGE not in _texts(app.warning)


def test_a_restore_press_right_after_the_pick_moved_is_not_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """둘째 누름이 바뀐 고름(다음 보관본)을 받은 화면에 곧바로 닿아도 그 보관본을 되돌리지 않는다 —
    사람이 바뀐 고름을 보고 누른 것이 아니다. 창이 지난 뒤의 누름은 되돌린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    script, repository = _archives(tmp_path)
    app, browser, target = _picked(script)

    app.button(key=RESTORE_KEY).click()
    _ok(browser.run())
    moved_to = str(browser.wire)
    assert moved_to != target and browser.last_set_value

    app.button(key=RESTORE_KEY).click()
    _ok(browser.run())
    assert _statuses(repository)[moved_to] == "ARCHIVED"
    assert any(f"{target}" in text and "되돌렸습니다" in text for text in _texts(app.success))

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app.button(key=RESTORE_KEY).click()
    _ok(browser.run())
    assert _statuses(repository)[moved_to] == "ACTIVE"


def test_restoring_an_archive_restored_elsewhere_writes_nothing_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """두 세션이 같은 보관본을 골랐고 다른 세션이 먼저 되돌렸다 — 이 세션의 「되돌리기」 는 다른
    보관본을 되돌리지 않고 이미 빠졌다고 알린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    script, repository = _archives(tmp_path)
    app, browser, target = _picked(script)
    target_id = next(
        item.scenario_id
        for item in repository.list_scenarios(include_archived=True)
        if item.scenario_name == target
    )
    repository.restore_scenario(target_id)

    app.button(key=RESTORE_KEY).click()
    _ok(browser.run())
    statuses = _statuses(repository)
    assert [name for name, status in statuses.items() if status == "ACTIVE"] == [target], statuses
    assert ARCHIVED_GONE_MESSAGE in _texts(app.warning)
    assert not any("되돌렸습니다" in text for text in _texts(app.success))


def _stale_archive_reads(
    monkeypatch: pytest.MonkeyPatch, snapshot: list[ScenarioSummary], reads: int
) -> None:
    """보관함의 다음 목록 읽기 `reads` 번을 `snapshot`(첫 쓰기 전 목록)으로 돌린다.

    겹쳐 온 둘째 누름의 회차는 첫 쓰기 전에 목록을 읽어 처리할 보관본이 아직 있는 화면을 그리고, 그
    회차의 상자 글자는 첫 누름 전 화면 그대로 풀린다. 첫 누름의 회차·그 뒤 다시 도는 회차·둘째
    회차의 읽기를 돌려 그 겹침을 정해진 차례로 만든다.
    """
    original = DuckDBScenarioRepository.list_scenarios
    left = {"reads": reads}

    def listing(self: DuckDBScenarioRepository, *args: Any, **kwargs: Any) -> Any:
        caller = sys._getframe(1).f_code.co_name
        if left["reads"] and caller == "_render_archived_scenarios":
            left["reads"] -= 1
            return list(snapshot)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(DuckDBScenarioRepository, "list_scenarios", listing)


@pytest.mark.parametrize("action", ["restore", "delete"])
def test_an_overlapping_second_press_drawn_before_the_first_write_reports_the_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    """겹쳐 온 둘째 누름의 회차는 첫 쓰기 전 목록(고른 보관본이 아직 있다)을 그리고 같은 보관본에
    다시 쓰러 간다. 저장소에 가면 날 KeyError(따옴표째 글)가 서고 그 회차는 처리한 보관본을 보관함에
    그대로 보였다 — 같은 보관본의 둘째 누름은 저장소에 가지 않고 첫 쓰기의 성공을 알린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    script, repository = _archives(tmp_path)
    app, browser, target = _picked(script)
    before = repository.list_scenarios(include_archived=True)
    if action == "delete":
        app.text_input(key=DELETE_CONFIRM_KEY).set_value(target)
        _ok(browser.run())
        button = app.button(key=DELETE_BUTTON_KEY)
        done = "영구 삭제했습니다"
    else:
        button = app.button(key=RESTORE_KEY)
        done = "되돌렸습니다"
    button.click()
    pressed = browser._states()
    _stale_archive_reads(monkeypatch, before, reads=3)
    _ok(browser.run())

    app._run(widget_state=pressed)
    assert not app.exception, [item.message for item in app.exception]
    assert not any("찾을 수 없습니다" in text for text in _texts(app.error)), _texts(app.error)
    assert any(target in text and done in text for text in _texts(app.success))
    statuses = _statuses(repository)
    if action == "delete":
        assert target not in statuses
        assert sorted(statuses.values()) == ["ARCHIVED", "ARCHIVED"]
    else:
        assert [name for name, status in statuses.items() if status == "ACTIVE"] == [target]


def test_a_delete_cut_right_after_writing_still_leaves_its_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """둘째 누름이 첫 회차를 삭제 직후에 끊으면 그 회차는 알림을 담지 못한다. 둘째 회차는 지운
    보관본이 빠진 목록이라 아무것도 하지 않는데, 옛 코드는 성공 알림이 하나도 남지 않았다 — 쓰기
    직후 적어 둔 알림 표지로 그 회차가 성공을 다시 그린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    script, repository = _archives(tmp_path)
    app, browser, target = _picked(script)
    original = DuckDBScenarioRepository.delete_scenario

    def cut(self: DuckDBScenarioRepository, scenario_id: str) -> None:
        original(self, scenario_id)
        context = get_script_run_ctx()
        assert context is not None and context.script_requests is not None
        context.script_requests.request_stop()

    monkeypatch.setattr(DuckDBScenarioRepository, "delete_scenario", cut)
    app.text_input(key=DELETE_CONFIRM_KEY).set_value(target)
    _ok(browser.run())
    app.button(key=DELETE_BUTTON_KEY).click()
    pressed = browser._states()
    browser.run()

    app._run(widget_state=pressed)
    assert not app.exception, [item.message for item in app.exception]
    assert target not in _statuses(repository)
    assert any(target in text and "영구 삭제했습니다" in text for text in _texts(app.success))


def test_an_overlapping_second_archive_press_reports_the_first_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """카드 「보관 실행」 도 같다 — 둘째 누름이 첫 회차를 보관 직후에 끊고 첫 보관 전 목록(고른
    시나리오가 아직 활성)을 그리면 옛 코드는 저장소에 다시 가 날 KeyError(「'활성 시나리오를 찾을 수
    없습니다: …'」)를 세웠다. 같은 시나리오의 둘째 누름은 첫 보관의 뒷정리·성공 알림을 잇는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    database_path = tmp_path / "scenario.duckdb"
    script = _page_script(PAGE_PATH, database_path, tmp_path / "equipment.duckdb")
    _ok(AppTest.from_string(script, default_timeout=120).run())
    repository = DuckDBScenarioRepository(database_path)
    target = _clone_official(database_path, "보관할 시나리오", "ARCHIVE-CARD").scenario
    before = repository.list_scenarios()

    app = AppTest.from_string(script, default_timeout=120)
    app.session_state[draft_session_key(LIST_EDITOR_KEY)] = TableDraft(picked=target.scenario_id)
    _ok(app.run())
    _ok(app.button(key=f"{ACTION_KEY}_archive").click().run())
    next(widget for widget in app.checkbox if widget.key == ARCHIVE_CONFIRM_KEY).check()
    _ok(app.run())

    original = DuckDBScenarioRepository.archive_scenario

    def cut(self: DuckDBScenarioRepository, scenario_id: str) -> None:
        original(self, scenario_id)
        context = get_script_run_ctx()
        assert context is not None and context.script_requests is not None
        context.script_requests.request_stop()

    monkeypatch.setattr(DuckDBScenarioRepository, "archive_scenario", cut)
    next(button for button in app.button if button.label == "보관 실행").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert target.scenario_id not in {item.scenario_id for item in repository.list_scenarios()}

    listing = DuckDBScenarioRepository.list_scenarios
    left = {"reads": 1}

    def stale(self: DuckDBScenarioRepository, *args: Any, **kwargs: Any) -> Any:
        if left["reads"] and not kwargs.get("include_archived"):
            left["reads"] -= 1
            return list(before)
        return listing(self, *args, **kwargs)

    monkeypatch.setattr(DuckDBScenarioRepository, "list_scenarios", stale)
    app._run(widget_state=pressed)
    assert not app.exception, [item.message for item in app.exception]
    assert not any("찾을 수 없습니다" in text for text in _texts(app.error)), _texts(app.error)
    assert any("보관했습니다" in text for text in _texts(app.success))
    archived = {
        item.scenario_id: item.status for item in repository.list_scenarios(include_archived=True)
    }
    assert archived[target.scenario_id] == "ARCHIVED"
