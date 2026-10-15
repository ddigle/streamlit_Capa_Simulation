# Purpose: 기준선 저장·지우기의 두 번 누름, 저장 뒤 팝오버, 이미 지워진 기준선 지우기를 검사한다.

"""기준선 저장·지우기의 겹친 조작(2026-10-15 브라우저 확인에서 찾은 것).

- 저장에 쓰인 폼의 제출이 한 번 더 들어오면(빠른 두 번 누름) 쓰지도 알리지도 않는다.
  AppTest 는 같은 순간의 두 요청을 합칠 수 없어, 저장 단추를 누른 화면의 위젯 값을 붙잡아
  두었다가 저장 뒤에 한 번 더 보낸다(`AppTest._run(widget_state=...)` — 브라우저에 남은 옛
  화면의 누름과 같다). 잇단 알림이 이벤트 칸의 다른 자리에 서는 것은
  `tests/test_shortening_baseline_notice.py` 가 본다.
- 저장에 성공하면 「기준선 저장」 팝오버가 새 블록(key 세대)으로 선다 — 브라우저가 닫힌 채
  그린다.
- 지우기를 끝낸 기준선의 누름이 한 번 더 들어와도 쓰지도 알리지도 않는다.
- 다른 세션이 먼저 지운 기준선을 지우면 경고 아이콘으로 알리고 프래그먼트 회차만 돈다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_required_shortening_tab import _run as _run_page
from test_shortening_progress_tab import _name_input, _save_button, _saved_database, _toasts
from test_shortening_view_fragment import (
    FULL_RUNS_KEY,
    _fragment_of,
    _install,
    _open,
    _run,
    _runner,
)

from capa_simulation.components.required_shortening_panel import SHORTENING_LEVEL_KEY
from capa_simulation.components.shortening_progress_panel import (
    NO_COMPARISON,
    SHORTENING_COMPARE_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository


def _names(database_path: Path) -> list[str]:
    return [
        baseline.name
        for baseline in DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    ]


def _save_popover_id(app: AppTest) -> str:
    return next(
        str(node.proto.id)
        for node in app.main
        if getattr(node, "type", "") == "popover" and node.proto.popover.label == "기준선 저장"
    )


def test_a_second_submit_of_the_saved_form_neither_saves_nor_overrides_the_notice(
    tmp_path: Path,
) -> None:
    database_path, _ = _saved_database(tmp_path)
    app = _run_page(database_path)
    app = _name_input(app).set_value("첫 저장").run()
    _save_button(app).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert "기준선을 저장했습니다 — 「첫 저장」" in _toasts(app)

    app._run(widget_state=pressed)

    assert not app.exception
    assert _names(database_path) == ["첫 저장"]
    # 거절 알림(같은 이름·빈 이름)도 내지 않는다 — 내면 앞 저장의 성공 알림을 덮는다.
    assert not list(app.toast), _toasts(app)
    clear_equipment_repository()


def test_a_saved_form_comes_back_as_a_new_popover_and_a_refused_one_does_not(
    tmp_path: Path,
) -> None:
    database_path, _ = _saved_database(tmp_path)
    app = _run_page(database_path)
    before = _save_popover_id(app)
    app = _name_input(app).set_value("첫 저장").run()
    app = _save_button(app).click().run()
    saved = _save_popover_id(app)
    assert saved != before
    app = _name_input(app).set_value("첫 저장").run()
    app = _save_button(app).click().run()
    assert "같은 이름" in _toasts(app)
    assert _save_popover_id(app) == saved
    clear_equipment_repository()


def test_a_second_press_of_a_finished_delete_neither_writes_nor_notifies(tmp_path: Path) -> None:
    """옛 화면은 그 기준선을 고른 비교 칸 값·체크한 확인 칸을 함께 보낸다 — 그래도 거른다."""
    database_path, _ = _saved_database(tmp_path)
    app = _run_page(database_path)
    app = _name_input(app).set_value("지울 것").run()
    app = _save_button(app).click().run()
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    confirm = next(box for box in app.checkbox if box.label == "정말 지웁니다")
    app = confirm.check().run()
    app.button(key="equipment_shortening_baseline_delete").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert "기준선을 지웠습니다 — 「지울 것」" in _toasts(app)

    app._run(widget_state=pressed)

    assert not app.exception
    assert _names(database_path) == []
    assert not list(app.toast), _toasts(app)
    clear_equipment_repository()


def test_deleting_a_baseline_another_session_deleted_warns_and_reruns_only_the_view(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(request)
    database_path, _ = _saved_database(tmp_path)
    world = _install(monkeypatch, database_path)
    app = _open(runner)
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    runner.fragment_queue = [view]
    _run(app, world, lambda app: _save_button(app).click())
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    view = _fragment_of(runner, SHORTENING_LEVEL_KEY)
    runner.fragment_queue = [view]
    _run(
        app,
        world,
        lambda app: app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id),
    )
    confirm = next(box for box in app.checkbox if box.label == "정말 지웁니다")
    runner.fragment_queue = [view]
    _run(app, world, lambda app: confirm.check())

    # 다른 세션이 먼저 지웠다(이 세션의 목록 캐시는 아직 그 기준선을 보인다).
    DuckDBEquipmentRepository(database_path).delete_shortening_baseline(stored.baseline_id)
    full_runs = app.session_state[FULL_RUNS_KEY]
    runner.fragment_queue = [view]
    _run(app, world, lambda app: app.button(key="equipment_shortening_baseline_delete").click())

    assert runner.started == [[view]]
    assert app.session_state[FULL_RUNS_KEY] == full_runs
    (toast,) = app.toast
    assert "이미 지워진 기준선입니다" in toast.value
    assert toast.proto.icon == ":material/block:"
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert picker.value == NO_COMPARISON and list(picker.options) == ["비교 안 함"]
    clear_equipment_repository()
