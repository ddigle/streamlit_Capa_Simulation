# Purpose: 버전 대조가 없는 Preference 공용 저장 폼이 같은 입력의 두 번 누름에 한 번만 쓰는지 잰다.

"""Summary 공지·Top5 구간·주요공정 프리셋·선행 B/O(`components/home_preference.py`).

저장소가 편집 시작 version 을 대조하지 않는 공용 저장이라, 같은 내용을 0.15~0.4초 간격으로 두 번
누르면 공용 버전이 두 번 올랐다(2026-10-25 E2E — Summary v5→v7·프리셋 v3→v5, 개선 거리 I6). 둘째
누름은 `write_guard.save_once` 가 같은 입력으로 알아보고 쓰지 않은 채 첫 저장을 알린다.

- **느린 누름** — 둘째 누름이 첫 저장 뒤 새로 그린 화면에 닿는다. 누른 화면의 위젯 값을 한 번 더
  보낸다(`AppTest._run(widget_state=...)`). 창(`TRAILING_PRESS_SECONDS`)은 시험이 길게 잡는다.
- **겹친 누름** — 첫 회차가 저장소 쓰기를 마치는 순간 둘째 누름이 닿아 첫 회차가 끊긴다
  (`test_write_guard_cas._press_twice`).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from test_write_guard_cas import _press_twice

import capa_simulation.components.write_guard as write_guard
from capa_simulation.persistence.cache import (
    clear_global_advance_load_cache,
    clear_global_key_process_cache,
    clear_global_summary_note_cache,
    clear_global_top5_band_cache,
    clear_scenario_repository,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository


@pytest.fixture
def repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DuckDBScenarioRepository]:
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    store = DuckDBScenarioRepository(tmp_path / "scenario.duckdb")
    store.initialize()
    clear_scenario_repository()
    for clear in (
        clear_global_summary_note_cache,
        clear_global_top5_band_cache,
        clear_global_key_process_cache,
        clear_global_advance_load_cache,
    ):
        clear()
    yield store
    clear_scenario_repository()


def _script(database: Path, body: str) -> str:
    return f"""
from capa_simulation.components import home_preference as preference
from capa_simulation.persistence.cache import (
    load_global_advance_load,
    load_global_summary_note,
    load_global_top5_band,
)

database_path = {str(database)!r}
{body}
"""


_SUMMARY = """
preference._render_summary_note_editor(
    summary_profile=load_global_summary_note(database_path), database_path=database_path
)
"""
_TOP5 = """
preference._render_top5_band_editor(
    top5_band_profile=load_global_top5_band(database_path), database_path=database_path
)
"""
_KEY_PROCESS = """
import pandas as pd

from capa_simulation.components.process_labels import process_labels_from_rules

preference._render_key_process_editor(
    process_options=["DEMO-A", "DEMO-B"],
    process_labels=process_labels_from_rules(pd.DataFrame()),
    database_path=database_path,
)
"""
_ADVANCE = """
preference._render_advance_editor(
    months=[202610, 202611],
    month_labels=["26.10", "26.11"],
    advance_profile=load_global_advance_load(database_path),
    database_path=database_path,
)
"""


def _app(repository: DuckDBScenarioRepository, body: str) -> AppTest:
    app = AppTest.from_string(_script(repository.database_path, body), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _press(app: AppTest, label: str) -> WidgetStates:
    """`label` 저장 단추를 누른 화면의 위젯 값(둘째 누름이 그대로 다시 보낸다)."""
    next(button for button in app.button if button.label == label).click()
    return app._tree.get_widget_states()


def _second_press(app: AppTest, pressed: WidgetStates) -> None:
    app._run(widget_state=pressed)
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [str(item.value) for item in app.error]


def _successes(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.success]


def test_a_slow_double_press_of_the_summary_note_saves_one_version(
    repository: DuckDBScenarioRepository,
) -> None:
    app = _app(repository, _SUMMARY)
    app.text_area[0].set_value("9월 물량 확정 전 잠정 계획")
    pressed = _press(app, "Summary 저장")
    app.run()
    assert repository.load_global_summary_note().version == 1

    _second_press(app, pressed)

    assert repository.load_global_summary_note().version == 1
    assert _successes(app) == ["Summary 공지를 저장했습니다."]


def test_an_overlapping_double_press_of_the_summary_note_saves_one_version(
    repository: DuckDBScenarioRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(repository, _SUMMARY)
    app.text_area[0].set_value("10월 물량 확정")

    _press_twice(
        app,
        monkeypatch,
        _press(app, "Summary 저장"),
        cls=DuckDBScenarioRepository,
        write="replace_global_summary_note",
    )

    stored = repository.load_global_summary_note()
    assert (stored.version, stored.note) == (1, "10월 물량 확정")
    assert not app.error, [str(item.value) for item in app.error]
    assert _successes(app) == ["Summary 공지를 저장했습니다."]


def test_a_slow_double_press_of_the_top5_band_saves_one_version(
    repository: DuckDBScenarioRepository,
) -> None:
    app = _app(repository, _TOP5)
    app.number_input[0].set_value(60.0)
    pressed = _press(app, "확보율 구간 저장")
    app.run()
    assert repository.load_global_top5_band().version == 1

    _second_press(app, pressed)

    assert repository.load_global_top5_band().version == 1
    assert _successes(app) == ["B/N Top5 확보율 구간을 저장했습니다."]


def test_a_slow_double_press_of_a_new_preset_saves_it_once_without_a_name_clash(
    repository: DuckDBScenarioRepository,
) -> None:
    """새 프리셋의 둘째 누름은 아직 「새 프리셋」 인 옛 화면의 입력이다 — 같은 이름을 하나 더
    넣으려다 거절이 방금 한 저장 자리에 섰다."""
    app = _app(repository, _KEY_PROCESS)
    app.text_input[0].set_value("A 그룹")
    app.multiselect[0].set_value(["DEMO-A"])
    pressed = _press(app, "프리셋 저장")
    app.run()
    assert repository.load_global_key_process().version == 1

    _second_press(app, pressed)

    stored = repository.load_global_key_process()
    assert (stored.version, stored.preset_names) == (1, ("A 그룹",))
    assert _successes(app) == ["프리셋 「A 그룹」을 저장했습니다."]


def test_a_slow_double_press_of_the_advance_load_saves_one_version(
    repository: DuckDBScenarioRepository,
) -> None:
    app = _app(repository, _ADVANCE)
    pressed = _press(app, "선행 B/O 저장")
    app.run()
    assert repository.load_global_advance_load().version == 1

    _second_press(app, pressed)

    assert repository.load_global_advance_load().version == 1
    assert _successes(app) == ["선행 B/O 를 공용 설정으로 저장했습니다."]


def test_a_different_input_inside_the_window_still_saves(
    repository: DuckDBScenarioRepository,
) -> None:
    """거름은 같은 입력만 거른다 — 창 안이라도 고친 글은 새로 저장한다."""
    app = _app(repository, _SUMMARY)
    app.text_area[0].set_value("첫 공지")
    _press(app, "Summary 저장")
    app.run()
    app.text_area[0].set_value("고친 공지")
    _press(app, "Summary 저장")
    app.run()

    stored = repository.load_global_summary_note()
    assert (stored.version, stored.note) == (2, "고친 공지")
