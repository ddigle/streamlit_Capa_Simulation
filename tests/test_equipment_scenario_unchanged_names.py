# Purpose: 설비 시나리오 이름·리비전명을 지금 이름 그대로 누르면 바뀐 것이 없다고만 알리는지 본다.

"""시나리오 관리 › 설비 시나리오 구획 「이름 바꾸기」·「리비전명 저장」 — 2026-11-01 개선 I5.

저장소는 같은 이름이면 쓰지 않았는데 화면은 성공 알림(「설비 시나리오 이름을 바꿨습니다 — 새 이름
…」 · 「… — 리비전명을 저장했습니다.」)을 띄웠다(E2E #60 · #96). 이제 단추 아래에 「바뀐 것이
없습니다」 를 적는다. 같은 단추의 느린 둘째 누름(첫 누름 뒤 새로 세운 칸에 닿아 새 이름을 든다)은 그
창 안이면 방금 성공을 다시 낸다 — 「바뀐 것이 없습니다」 로 덮지 않는다(write_guard.held_notice).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_name_fields import _named_revisions, _section
from test_equipment_scenario_repository import OPERATIONS, _seeded

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.equipment_scenario_management import (
    RENAME_BUTTON_KEY,
    RENAME_KEY,
    REVISION_KEY,
    REVISION_NAME_BUTTON_KEY,
    REVISION_NAME_KEY,
    REVISION_NAME_UNCHANGED_MESSAGE,
    SCENARIO_NAME_UNCHANGED_MESSAGE,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest, kind: str) -> list[str]:
    return [str(item.value) for item in getattr(app, kind)]


def test_renaming_a_scenario_to_its_current_name_says_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    repository = _seeded(tmp_path)
    app = _ok(_section(repository.database_path).run())
    # 앞뒤 공백은 저장소가 뗀다 — 지금 이름 그대로다.
    app.text_input(key=f"{RENAME_KEY}__{OPERATIONS}").input(" 운영 일정 ")
    app.button(key=RENAME_BUTTON_KEY).click()
    _ok(app.run())

    assert _texts(app, "info") == [SCENARIO_NAME_UNCHANGED_MESSAGE]
    assert not app.success and not app.error
    assert [item.scenario_name for item in repository.list_equipment_scenarios()] == ["운영 일정"]


def test_saving_a_revision_name_unchanged_says_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이름표가 있는 r1(「u2 이름」)과 이름표가 없는 r2(빈 칸 그대로) 둘 다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    repository, numbers = _named_revisions(tmp_path)
    app = _ok(_section(repository.database_path).run())
    for number in (1, 2):
        app.selectbox(key=REVISION_KEY).set_value(numbers[number])
        _ok(app.run())
        app.button(key=REVISION_NAME_BUTTON_KEY).click()
        _ok(app.run())

        assert _texts(app, "info") == [REVISION_NAME_UNCHANGED_MESSAGE], number
        assert not app.success and not app.error
    names = {
        item.revision_no: item.revision_name
        for item in repository.list_schedule_revisions(OPERATIONS)
    }
    assert names == {1: "u2 이름", 2: None}


def test_a_changed_name_is_still_saved(tmp_path: Path) -> None:
    repository, numbers = _named_revisions(tmp_path)
    app = _ok(_section(repository.database_path).run())
    app.selectbox(key=REVISION_KEY).set_value(numbers[1])
    _ok(app.run())
    app.text_input(key=f"{REVISION_NAME_KEY}__{numbers[1]}").input("새 이름표")
    app.button(key=REVISION_NAME_BUTTON_KEY).click()
    _ok(app.run())

    assert not app.info
    assert any("리비전명을 저장했습니다" in text for text in _texts(app, "success"))
    names = {
        item.revision_no: item.revision_name
        for item in repository.list_schedule_revisions(OPERATIONS)
    }
    assert names[1] == "새 이름표"


def test_a_slow_second_rename_press_repeats_the_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """첫 누름 뒤 칸은 새 이름으로 다시 선다 — 그 칸에 닿은 둘째 누름은 같은 이름이라 쓰지 않지만,
    창 안이면 첫 누름의 성공을 다시 낸다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository = _seeded(tmp_path)
    app = _ok(_section(repository.database_path).run())
    app.text_input(key=f"{RENAME_KEY}__{OPERATIONS}").input("운영 일정 B")
    app.button(key=RENAME_BUTTON_KEY).click()
    _ok(app.run())
    saved = "설비 시나리오 이름을 바꿨습니다 — 새 이름 「운영 일정 B」."
    assert saved in _texts(app, "success")

    app.button(key=RENAME_BUTTON_KEY).click()
    _ok(app.run())

    assert not app.info, _texts(app, "info")
    assert saved in _texts(app, "success")
    assert [item.scenario_name for item in repository.list_equipment_scenarios()] == ["운영 일정 B"]
