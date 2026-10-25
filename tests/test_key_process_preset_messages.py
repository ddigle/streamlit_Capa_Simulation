# Purpose: HOME 주요공정 프리셋 「기본으로」·「삭제」 알림이 이름 받침에 맞는 조사를 쓰는지 본다.

"""프리셋 이름은 값이 들어가는 자리라 뒤 조사를 `services/korean_particle.py` 로 고른다(AGENTS).

「기본으로」·「프리셋 삭제」 알림이 「을」을 고정해 받침 없는 이름(「테스트」)에서
「「테스트」을 …」로 틀렸다(2026-10-26 E2E). 저장 알림은 이미 `object_particle` 을 썼다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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
