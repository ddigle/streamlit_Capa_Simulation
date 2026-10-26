# Purpose: 설비 시나리오 구획 쓰기가 남의 쓰기에 거부된 뒤 둘째 누름으로 거부를 덮지 않는지 본다.

"""시나리오 관리 › 설비 시나리오 구획 — 남이 먼저 바꾼 뒤 옛 화면에서 같은 단추를 사람 속도로 두 번
누른 경우(2026-10-27 브라우저 E2E r6).

첫 누름은 대조에 걸려 거부되고(`_refused`) 그 회차가 입력 칸을 지금 값으로 새로 세운다(세대 올림).
단추 key 는 세대가 붙지 않은 고정 key 라 둘째 누름이 그 새 회차에 닿는데, 그 회차의 칸은 남의 이름을
본 값으로 들고 있어 대조를 지나 — 이름 바꾸기·리비전명은 같은 이름을 다시 쓰며(저장소는 쓰지 않는다)
「…으로 했습니다」·「리비전명을 저장했습니다」 로 거부를 덮었고, 공식 발행은 바뀐 확인 글을 보지
않은 채 새 번호로 발행했다. 거부 표지(`write_guard.note_profile_conflict`)를 적고 그 창 안의
둘째 누름은 쓰지 않고 거부를 다시 알린다(AGENTS 9장 「남의 저장에 거부된 누름의 둘째 누름」).

AppTest 의 두 회차 사이는 사람의 두 번 누름보다 길 수 있어 창(`TRAILING_PRESS_SECONDS`)을 넓혀 둔다.
창이 지난 누름은 새 화면을 보고 다시 누른 것이라 평소대로 쓴다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_layout_management import _section
from test_equipment_scenario_repository import OPERATIONS, _clone, _seeded
from test_equipment_scenario_screens import _revision_id

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.equipment_scenario_management import (
    PUBLISH_BUTTON_KEY,
    RENAME_BUTTON_KEY,
    RENAME_KEY,
    REVISION_NAME_BUTTON_KEY,
    REVISION_NAME_KEY,
    SCENARIO_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _opened(tmp_path: Path, scenario_id: str) -> AppTest:
    app = _ok(_section(tmp_path, scenario_id).run())
    app.selectbox(key=SCENARIO_KEY).set_value(scenario_id)
    return _ok(app.run())


def _notices(app: AppTest) -> tuple[list[str], list[str]]:
    """(성공 알림, 거절 알림) — 구획 맨 위 두 칸."""
    return [str(item.value) for item in app.success], [str(item.value) for item in app.error]


def test_a_second_press_after_someone_elses_rename_repeats_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 가 이름을 쳐 둔 사이 B 가 「B 이름」 으로 바꿨다 — A 의 두 번 누름은 둘 다 거부이고, 둘째
    누름이 「설비 시나리오 이름을 「B 이름」으로 했습니다」 로 거부를 덮지 않는다(E2E 3/3)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository = _seeded(tmp_path)
    app = _opened(tmp_path, OPERATIONS)
    app.text_input(key=f"{RENAME_KEY}__{OPERATIONS}").input("A 이름")
    repository.rename_equipment_scenario(OPERATIONS, name="B 이름", expected_name="운영 일정")

    app.button(key=RENAME_BUTTON_KEY).click()
    written, refused = _notices(_ok(app.run()))
    assert written == [] and any("이름을 바꾸지 않았습니다" in text for text in refused), refused

    app.button(key=RENAME_BUTTON_KEY).click()
    written, refused = _notices(_ok(app.run()))

    assert written == [], written
    assert len(refused) == 1 and "이름을 바꾸지 않았습니다" in refused[0], refused
    assert [item.scenario_name for item in repository.list_equipment_scenarios()] == ["B 이름"]


def test_a_rename_pressed_after_the_window_is_a_fresh_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """거부 뒤 새 화면을 보고(창이 지나) 다시 누른 이름 바꾸기는 평소대로 쓴다."""
    repository = _seeded(tmp_path)
    app = _opened(tmp_path, OPERATIONS)
    app.text_input(key=f"{RENAME_KEY}__{OPERATIONS}").input("A 이름")
    repository.rename_equipment_scenario(OPERATIONS, name="B 이름", expected_name="운영 일정")
    app.button(key=RENAME_BUTTON_KEY).click()
    _ok(app.run())

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    (field,) = [item for item in app.text_input if str(item.key).startswith(RENAME_KEY)]
    assert field.value == "B 이름"
    field.input("A 이름")
    app.button(key=RENAME_BUTTON_KEY).click()
    written, refused = _notices(_ok(app.run()))

    assert refused == [] and any("「A 이름」" in text for text in written), written
    assert [item.scenario_name for item in repository.list_equipment_scenarios()] == ["A 이름"]


def test_a_second_press_after_someone_elses_revision_name_repeats_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 꼴 — 「리비전명 저장」 의 둘째 누름이 「r1 · B이름 — 리비전명을 저장했습니다」 로 거부를
    덮었다(E2E 2/2)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository = _seeded(tmp_path)
    first = _revision_id(repository, 1)
    app = _opened(tmp_path, OPERATIONS)
    app.text_input(key=f"{REVISION_NAME_KEY}__{first}").input("A 리비전")
    repository.rename_schedule_revision(first, name="B 리비전", expected_name=None)

    app.button(key=REVISION_NAME_BUTTON_KEY).click()
    written, refused = _notices(_ok(app.run()))
    assert written == [] and any("리비전명을 바꾸지 않았습니다" in text for text in refused)

    app.button(key=REVISION_NAME_BUTTON_KEY).click()
    written, refused = _notices(_ok(app.run()))

    assert written == [], written
    assert len(refused) == 1 and "리비전명을 바꾸지 않았습니다" in refused[0], refused
    (revision,) = repository.list_schedule_revisions(OPERATIONS)
    assert revision.revision_name == "B 리비전"


def test_a_second_press_after_someone_elses_publish_does_not_publish_unseen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 결함류(곁 자리) — 「공식으로 발행」 확인 글(지금 공식 v1 → 새 공식 v2)을 본 사이 B 가
    발행(v2)했다. 첫 누름은 거부되고 그 뒤 회차가 새 확인 글의 값을 본 값으로 적어, 옛 화면의 둘째
    누름이 바뀐 확인 글을 보지 않은 채 v3 을 냈다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    repository = _seeded(tmp_path)
    setup = _clone(repository).equipment_scenario_id
    other = _clone(repository, "다른 가정").equipment_scenario_id
    app = _opened(tmp_path, setup)
    other_latest = next(
        item.latest_schedule_revision_id
        for item in repository.list_equipment_scenarios()
        if item.equipment_scenario_id == other
    )
    assert other_latest is not None
    repository.publish_equipment_release(
        other_latest, released_by=None, note=None, expected_latest_release_no=1
    )

    app.button(key=PUBLISH_BUTTON_KEY).click()
    written, refused = _notices(_ok(app.run()))
    assert written == [] and any("발행하지 않았습니다" in text for text in refused), refused

    app.button(key=PUBLISH_BUTTON_KEY).click()
    written, refused = _notices(_ok(app.run()))

    assert written == [], written
    assert len(refused) == 1 and "발행하지 않았습니다" in refused[0], refused
    release = repository.latest_equipment_release()
    assert release is not None and release.release_no == 2
    assert release.equipment_scenario_id == other
