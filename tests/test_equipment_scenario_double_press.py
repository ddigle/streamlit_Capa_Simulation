# Purpose: 설비 시나리오 구획 쓰기의 겹친 더블클릭이 제 쓰기를 남의 쓰기로 거절하지 않는지 본다.

"""시나리오 관리 › 설비 시나리오 구획의 비교 후 쓰기 다섯 — 「공식으로 발행」(2026-10-26 E2E, 고부하
간헐 1/7)과 같은 꼴의 이름 바꾸기·리비전명·배치 차이 지우기·되돌리기.

Streamlit 1.63 `runner.fastReruns` 는 둘째 누름에서 돌던 회차에 멈춤을 걸고 곧바로 새 회차를 세워
두 회차가 겹쳐 돈다. 둘째 회차가 첫 쓰기 **전** 목록(낡은 확인 글)으로 끝까지 돌아 저장소에 가면
첫 쓰기에 거부되는데, 첫 회차가 제 저장 짝을 쓰기 잠금이 풀린 **뒤**에 적어 그 사이에 짝을 보면
없었다 — 제 발행을 「확인 글을 본 뒤 공식이 바뀌어 발행하지 않았습니다」 로 알렸다(데이터는 맞다).
쓰기와 짝 적기를 세션의 잠금 안에서 함께 하면(`write_guard.save_remembered`) 둘째 회차는 그 뒤에야
저장소에 가 짝을 본다.

시험은 그 겹침을 정해진 차례로 만든다(`_raced`). 둘째 회차는 첫 쓰기 전에 다른 스레드에서 같은
누른 화면으로 돌아 쓰기 바로 앞(`own_save_marks`)에서 기다리고, 첫 회차가 쓴 뒤 놓인다. 첫 회차는
둘째 회차를 2초까지 기다린 뒤 짝을 적고 잇는다 — 옛 코드는 그 사이 둘째 회차가 짝 없는 거부로
끝나고, 고친 코드는 둘째 회차가 세션의 잠금에서 기다린다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from streamlit.runtime import Runtime
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_layout_management import _moved_setup, _section
from test_equipment_scenario_repository import OPERATIONS, _clone, _seeded
from test_equipment_scenario_screens import _moved_on, _restore_confirm, _revision_id

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components import equipment_scenario_management as section
from capa_simulation.components.equipment_scenario_management import (
    CLEAR_LAYOUT_BUTTON_KEY,
    CLEAR_LAYOUT_CONFIRM_KEY,
    PUBLISH_BUTTON_KEY,
    RENAME_BUTTON_KEY,
    RENAME_KEY,
    RESTORE_BUTTON_KEY,
    REVISION_KEY,
    REVISION_NAME_BUTTON_KEY,
    REVISION_NAME_KEY,
    SCENARIO_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


class Outcome(NamedTuple):
    """두 회차가 낸 알림 — 성공(`_written`)과 거절(`_refused`) 글."""

    written: list[str]
    refused: list[str]


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _opened(tmp_path: Path, scenario_id: str) -> AppTest:
    app = _ok(_section(tmp_path, scenario_id).run())
    app.selectbox(key=SCENARIO_KEY).set_value(scenario_id)
    return _ok(app.run())


def _raced(app: AppTest, monkeypatch: pytest.MonkeyPatch, write: str) -> Outcome:
    """누른 화면(지금 위젯 값)의 같은 누름 둘을 겹쳐 돌린다.

    둘째 회차는 첫 회차가 저장소 `write` 에 닿을 때 다른 스레드에서 같은 화면으로 돌기
    시작해(첫 쓰기 전 목록으로 그린다) 쓰기 바로 앞(`own_save_marks`)에서 기다리고, 첫 쓰기가
    끝나면 놓인다. 첫 회차는 그 뒤 둘째 회차를 2초까지 기다리고서야 저장소 호출에서 돌아온다 —
    옛 코드는 그 사이 둘째 회차가 짝 없는 거부를 받고, 고친 코드는 둘째 회차가 세션의 잠금에서
    기다린다. 첫 회차는 알림을 내기 전에 둘째 회차가 끝나기를 기다린다 — 두 `app._run` 이 겹치면
    먼저 끝난 쪽이 런타임을 비우므로(`Runtime._instance = None`) 첫 회차가 마지막에 끝나게 하고
    그 런타임을 되살린다.
    """
    pressed = app._tree.get_widget_states()
    outcome = Outcome([], [])
    second_errors: list[BaseException] = []
    started = threading.Event()
    reached = threading.Event()
    released = threading.Event()
    first: dict[str, Any] = {}

    def run_second() -> None:
        try:
            app._run(widget_state=pressed)
        except BaseException as exc:  # 스레드 예외는 시험이 받아 본다.
            second_errors.append(exc)

    second = threading.Thread(target=run_second)

    def after_second() -> None:
        """첫 회차의 알림 자리 — 둘째 회차가 끝나기를 기다리고 첫 회차의 런타임을 되살린다."""
        if first.get("thread") is threading.current_thread():
            second.join(timeout=180)
            Runtime._instance = first["runtime"]

    original_written = section._written
    original_refused = section._refused

    def written(message: str, **kwargs: Any) -> None:
        after_second()
        outcome.written.append(message)
        original_written(message, **kwargs)

    def refused(message: str) -> None:
        after_second()
        outcome.refused.append(message)
        original_refused(message)

    monkeypatch.setattr(section, "_written", written)
    monkeypatch.setattr(section, "_refused", refused)
    original_marks: Callable[[], Any] = write_guard.own_save_marks

    def marks() -> Any:
        if started.is_set() and first.get("thread") is not threading.current_thread():
            # 둘째 회차 — 쓰기 바로 앞에서 첫 쓰기를 기다린다.
            reached.set()
            released.wait(timeout=180)
        return original_marks()

    monkeypatch.setattr(section, "own_save_marks", marks)
    original_write = getattr(DuckDBEquipmentRepository, write)

    def racing(self: DuckDBEquipmentRepository, *args: Any, **kwargs: Any) -> Any:
        if started.is_set():
            return original_write(self, *args, **kwargs)
        first.update(thread=threading.current_thread(), runtime=Runtime._instance)
        started.set()
        second.start()
        while not reached.is_set() and second.is_alive():
            reached.wait(timeout=0.05)
        assert reached.is_set(), "둘째 회차가 쓰기 앞에 닿지 않았습니다"
        try:
            return original_write(self, *args, **kwargs)
        finally:
            released.set()
            second.join(timeout=2.0)

    monkeypatch.setattr(DuckDBEquipmentRepository, write, racing)
    app._run(widget_state=pressed)
    second.join(timeout=180)
    assert started.is_set(), "첫 누름이 저장소에 닿지 않았습니다"
    assert not second.is_alive()
    assert second_errors == []
    assert not app.exception, [item.message for item in app.exception]
    return outcome


def _said(outcome: Outcome, text: str) -> bool:
    return any(text in message for message in outcome.written)


def test_a_double_press_of_the_publish_publishes_once_and_never_says_it_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「공식으로 발행」 — 둘째 회차가 낡은 목록(v1)으로 발행에 가 첫 발행(v2)에 거부되고 짝이 없어
    「확인 글을 본 뒤 공식이 바뀌어(v1 → 지금 v2) 발행하지 않았습니다」 가 남았다(E2E 3/3 재현)."""
    repository = _seeded(tmp_path)
    setup = _clone(repository).equipment_scenario_id
    app = _opened(tmp_path, setup)
    app.button(key=PUBLISH_BUTTON_KEY).click()

    outcome = _raced(app, monkeypatch, "publish_equipment_release")

    assert outcome.refused == []
    assert _said(outcome, "공식 v2로 발행했습니다"), outcome
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 2
    assert release.equipment_scenario_id == setup


def test_a_double_press_of_the_scenario_rename_never_says_someone_else_renamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 꼴 — 「이름 바꾸기」 의 둘째 회차가 짝을 적기 전에 거부되면 「다른 사용자가 먼저 이름을
    바꿨습니다(지금: 내 새 이름)」 로 알렸다."""
    repository = _seeded(tmp_path)
    app = _opened(tmp_path, OPERATIONS)
    app.text_input(key=f"{RENAME_KEY}__{OPERATIONS}").input("겹친 이름")
    app.button(key=RENAME_BUTTON_KEY).click()

    outcome = _raced(app, monkeypatch, "rename_equipment_scenario")

    assert outcome.refused == []
    assert _said(outcome, "설비 시나리오 이름을 「겹친 이름」으로 했습니다."), outcome
    assert [item.scenario_name for item in repository.list_equipment_scenarios()] == ["겹친 이름"]


def test_a_double_press_of_the_revision_name_never_says_someone_else_renamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    first = _revision_id(repository, 1)
    app = _opened(tmp_path, OPERATIONS)
    app.text_input(key=f"{REVISION_NAME_KEY}__{first}").input("겹친 리비전")
    app.button(key=REVISION_NAME_BUTTON_KEY).click()

    outcome = _raced(app, monkeypatch, "rename_schedule_revision")

    assert outcome.refused == []
    assert _said(outcome, "리비전명을 저장했습니다."), outcome
    (revision,) = repository.list_schedule_revisions(OPERATIONS)
    assert revision.revision_name == "겹친 리비전"


def test_a_double_press_of_the_layout_clear_never_says_someone_else_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, setup, _ = _moved_setup(tmp_path)
    app = _opened(tmp_path, setup)
    (confirm,) = [box for box in app.checkbox if str(box.key).startswith(CLEAR_LAYOUT_CONFIRM_KEY)]
    _ok(confirm.check().run())
    app.button(key=CLEAR_LAYOUT_BUTTON_KEY).click()

    outcome = _raced(app, monkeypatch, "clear_layout_overlay")

    assert outcome.refused == []
    assert _said(outcome, "배치 차이를 모두 지운 r3을 저장했습니다"), outcome
    assert [item.revision_no for item in repository.list_schedule_revisions(setup)] == [3, 2, 1]


def test_a_double_press_of_the_restore_never_says_someone_else_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _seeded(tmp_path)
    _moved_on(repository)
    first = _revision_id(repository, 1)
    app = _opened(tmp_path, OPERATIONS)
    app.selectbox(key=REVISION_KEY).set_value(first)
    _ok(app.run())
    _ok(_restore_confirm(app).check().run())
    app.button(key=RESTORE_BUTTON_KEY).click()

    outcome = _raced(app, monkeypatch, "restore_schedule_revision")

    assert outcome.refused == []
    assert _said(outcome, "r1의 일정으로 되돌려 r3을 저장했습니다"), outcome
    assert [item.revision_no for item in repository.list_schedule_revisions(OPERATIONS)] == [
        3,
        2,
        1,
    ]
