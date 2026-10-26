# Purpose: HOME 주요공정 프리셋 「기본으로」·「삭제」 알림의 조사와 빠른 두 번 누름 뒤 알림을 본다.

"""프리셋 「기본으로」·「프리셋 삭제」 알림(`components/home_preference.py`).

- 프리셋 이름은 값이 들어가는 자리라 뒤 조사를 `services/korean_particle.py` 로 고른다(AGENTS).
  「기본으로」·「프리셋 삭제」 알림이 「을」을 고정해 받침 없는 이름(「테스트」)에서
  「「테스트」을 …」로 틀렸다(2026-10-26 E2E). 저장 알림은 이미 `object_particle` 을 썼다.
- 「프리셋 삭제」를 0.15초 간격으로 두 번 누르면 둘째 누름은 옛 화면의 단추에 닿는데, 그 회차에는
  고칠 프리셋이 바뀌어 단추가 잠겨 Streamlit 이 누름을 버린다. 그 회차가 앞 회차의 「지웠습니다」를
  지워 아무 알림도 남지 않았다(2026-10-26 E2E r3). 방금 한 동작의 알림은 그 꼬리 회차에도 선다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.persistence.cache import (
    clear_global_key_process_cache,
    clear_scenario_repository,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository


def _script(database_path: Path, target: str) -> str:
    return f"""
from pathlib import Path

from capa_simulation.components.flash import render_flash
from capa_simulation.components.home_preference import _render_key_process_preset_actions
from capa_simulation.persistence.repository import DuckDBScenarioRepository

database_path = {str(database_path)!r}
render_flash("home_key_process_flash")
profile = DuckDBScenarioRepository(Path(database_path)).load_global_key_process()
if {target!r} in profile.preset_names:
    _render_key_process_preset_actions(profile, {target!r}, database_path)
"""


@pytest.mark.parametrize(
    ("target", "moved", "deleted"),
    [
        (
            "테스트",
            "「테스트」를 기본 프리셋으로 옮겼습니다.",
            "프리셋 「테스트」를 지웠습니다.",
        ),
        (
            "앞 그룹",
            "「앞 그룹」을 기본 프리셋으로 옮겼습니다.",
            "프리셋 「앞 그룹」을 지웠습니다.",
        ),
    ],
)
def test_preset_actions_pick_the_object_particle_by_the_name(
    tmp_path: Path, target: str, moved: str, deleted: str
) -> None:
    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_key_process_presets(
        [("맨 앞", ["DEMO-A"]), (target, ["DEMO-B"])], source="시험"
    )
    clear_scenario_repository()
    clear_global_key_process_cache()
    app = AppTest.from_string(_script(database_path, target), default_timeout=60).run()
    assert not app.exception

    app.button(key="home_key_process_preset_default").click().run()

    assert not app.exception
    assert [str(message.value) for message in app.success] == [moved]
    assert repository.load_global_key_process().preset_names == (target, "맨 앞")

    app.checkbox[0].check().run()
    app.button(key="home_key_process_preset_delete").click().run()

    assert not app.exception
    assert [str(message.value) for message in app.success] == [deleted]
    assert repository.load_global_key_process().preset_names == ("맨 앞",)
    clear_global_key_process_cache()


def _editor_script(database_path: Path) -> str:
    """프리셋 편집 카드 한 장(프래그먼트 함수를 앱 전체 회차에서 부른다)."""
    return f"""
import pandas as pd

from capa_simulation.components.home_preference import _render_key_process_editor
from capa_simulation.components.process_labels import process_labels_from_rules

_render_key_process_editor(
    process_options=["DEMO-A", "DEMO-B"],
    process_labels=process_labels_from_rules(pd.DataFrame()),
    database_path={str(database_path)!r},
)
"""


@pytest.mark.parametrize(("window", "trailing"), [(3600.0, True), (0.0, False)])
def test_a_quick_second_press_of_delete_keeps_the_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: float, trailing: bool
) -> None:
    """「프리셋 삭제」의 빠른 둘째 누름은 잠긴 단추에 닿아 아무것도 하지 않는다 — 앞 회차의 알림을
    지우지 않고 다시 그린다. 창(`TRAILING_PRESS_SECONDS`)이 지난 회차는 그리지 않는다. AppTest 는
    누른 화면의 위젯 값을 붙잡아 한 번 더 보낸다(창은 시험이 정한다)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_key_process_presets(
        [("맨 앞", ["DEMO-A"]), ("지울 그룹", ["DEMO-B"])], source="시험"
    )
    clear_scenario_repository()
    clear_global_key_process_cache()
    app = AppTest.from_string(_editor_script(database_path), default_timeout=60).run()
    assert not app.exception
    app.selectbox(key="home_key_process_preset_edit").set_value("지울 그룹").run()
    next(box for box in app.checkbox if box.label == "「지울 그룹」 삭제 확인").check().run()
    app.button(key="home_key_process_preset_delete").click()
    pressed = app._tree.get_widget_states()
    app.run()
    deleted = "프리셋 「지울 그룹」을 지웠습니다."
    assert [str(message.value) for message in app.success] == [deleted]
    assert repository.load_global_key_process().preset_names == ("맨 앞",)

    app._run(widget_state=pressed)

    assert not app.exception, [element.message for element in app.exception]
    assert not app.error, [str(element.value) for element in app.error]
    shown = [str(message.value) for message in app.success]
    assert shown == ([deleted] if trailing else [])
    assert repository.load_global_key_process().preset_names == ("맨 앞",)
    clear_global_key_process_cache()
