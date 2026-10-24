# Purpose: 가정 시나리오 RawData 배치 칸 잠금·다른 시나리오 일정 호기 삭제 확인·공식 판정을 본다.

"""설비 시나리오 2단계 S1 — RawData 쪽 셋.

- **가정 세션의 있던 호기 배치 칸 고침은 되돌린다**(설계 10장 「S1 부터 임시 잠금」). 이 판에서 배치
  일곱 칸은 공통이라 가정 세션에서 고치면 공식 배치가 바뀐다. 칸을 잠그지 않고 제출 검사·붙여넣기
  미리보기에서 막는다 — 같은 제출의 다른 편집과 새 호기의 배치 값은 받는다.
- **다른 설비 시나리오에 일정이 있는 호기를 지우는 저장은 확인 체크 뒤에**(11-2 6단계). 호기 목록은
  공통 하나라 지우면 그 시나리오들의 일정도 빠진다.
- **공식 판정 대체 규칙**(검토 L13) — 발행이 없을 때 화면도 저장소처럼 「운영 일정」 → 목록 첫
  시나리오로 본다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import _clone, _seeded, _session, _with_unit
from widget_browser import BrowserTables

from capa_simulation.components.equipment_data_workspace import (
    ASSUMPTION_LAYOUT_LOCK,
    BUFFER_GENERATION_KEY,
    BUFFER_KEY,
    CLIPBOARD_KEY,
    EDIT_SAVE_BUTTON_KEY,
    EQUIPMENT_EDITOR_KEY,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    REMOVAL_CONFIRM_KEY,
    TARGET_KEY,
    VIEW_APPLY_BUTTON_KEY,
    ImportReview,
    assumption_paste_refusal,
)
from capa_simulation.equipment_scenario_activation import EquipmentSession, _default_selection
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRelease,
    EquipmentScenarioCatalog,
    EquipmentScenarioSummary,
)
from capa_simulation.services.space_layout_edit import existing_layout_edits, keep_layout_cells

OPERATIONS = "operations"


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


def _workspace(path: Path, scenario_id: str) -> AppTest:
    """세션 설비 시나리오 `scenario_id` 의 최신을 보는 RawData — 페이지와 같은 저장 출발점."""
    return AppTest.from_string(
        f"""
from pathlib import Path
from capa_simulation.components.equipment_data_workspace import render_equipment_data_workspace
from capa_simulation.components.equipment_save_fields import EquipmentSaveBasis
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
repository = DuckDBEquipmentRepository(Path({str(path)!r}))
repository.initialize()
scenario = next(
    item for item in repository.list_equipment_scenarios()
    if item.equipment_scenario_id == {scenario_id!r}
)
snapshot = repository.load_merged_snapshot(
    repository.latest_revision_id(), scenario.latest_schedule_revision_id
)
release = repository.latest_equipment_release()
basis = EquipmentSaveBasis(
    equipment_scenario_id=scenario.equipment_scenario_id,
    scenario_name=scenario.scenario_name,
    release_no=release.release_no if release is not None else 0,
    revision_no=scenario.latest_revision_no,
    latest_revision_no=scenario.latest_revision_no,
    official_scenario=repository.official_scenario_id() == scenario.equipment_scenario_id,
)
render_equipment_data_workspace(
    repository=repository, latest_snapshot=snapshot, baseline=snapshot.baseline,
    equipment=snapshot.equipment, downtime=snapshot.downtime,
    floor_canvases={{}}, max_extent=(100.0, 60.0), basis=basis,
)
""",
        default_timeout=60,
    )


def _two_scenarios(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, str]:
    """「운영 일정」 r1(공식 v1) + 그것을 복제한 「셋업 실무」 r1 — 둘 다 EQ-01·EQ-02 일정."""
    repository = _seeded(tmp_path)
    return repository, _clone(repository).equipment_scenario_id


def _editor_key(app: AppTest) -> str:
    generation_key = f"{EQUIPMENT_EDITOR_KEY}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return f"{EQUIPMENT_EDITOR_KEY}__g{generation}" if generation else EQUIPMENT_EDITOR_KEY


def _store(app: AppTest, frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> None:
    """화면 밖(앞선 제출·Space 적용)에서 바뀐 편집본 — 편집표가 옛 보기 프레임을 그리지 않게 그
    보기도 버린다(`replace_equipment_buffer` 와 같은 뒷정리)."""
    app.session_state[BUFFER_KEY] = frames
    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    del app.session_state[f"{EQUIPMENT_EDITOR_KEY}_applied_view"]


def _buffer_value(app: AppTest, name: str, column: str) -> Any:
    return app.session_state[BUFFER_KEY][1].set_index("설비명").loc[name, column]


def _texts(app: AppTest, kind: str) -> list[str]:
    return [str(item.value) for item in getattr(app, kind)]


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


# ------------------------------------------------------------------ 배치 칸 임시 잠금


def test_an_assumption_reverts_layout_edits_of_saved_units_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    _, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    assert any(ASSUMPTION_LAYOUT_LOCK in text for text in _texts(app, "caption"))
    tables = BrowserTables(app)
    key = _editor_key(app)
    tables.edit(key, 0, "X좌표", 50.0)
    tables.edit(key, 0, "설비이력", "고치는 중")
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    assert _buffer_value(app, "EQ-01", "X좌표") == 10
    assert _buffer_value(app, "EQ-01", "설비이력") == "고치는 중"
    assert any(
        "「셋업 실무」 은 가정 설비 시나리오라 있던 호기 1대(EQ-01)의 배치 칸 고침은 되돌리고 "
        "나머지 편집은 반영했습니다" in text
        for text in _texts(app, "error")
    )


def test_an_assumption_save_with_a_layout_edit_saves_nothing(tmp_path: Path) -> None:
    repository, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    tables = BrowserTables(app)
    tables.edit(_editor_key(app), 1, "층", "2F")
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(tables.run())

    assert len(repository.list_revisions()) == 1
    assert _buffer_value(app, "EQ-02", "층") == "1F"
    assert any("있던 호기 1대(EQ-02)" in text for text in _texts(app, "error"))


def test_a_new_unit_keeps_its_layout_cells_in_an_assumption(tmp_path: Path) -> None:
    _, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    _store(app, (baseline, _with_unit(equipment, "EQ-NEW", 70.0), downtime))
    _ok(app.run())
    tables = BrowserTables(app)
    tables.edit(_editor_key(app), 2, "X좌표", 80.0)
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    assert _buffer_value(app, "EQ-NEW", "X좌표") == 80.0
    assert not app.error


def test_the_official_scenario_edits_layout_cells_as_before(tmp_path: Path) -> None:
    _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", OPERATIONS).run())
    assert not any(ASSUMPTION_LAYOUT_LOCK in text for text in _texts(app, "caption"))
    tables = BrowserTables(app)
    tables.edit(_editor_key(app), 0, "X좌표", 50.0)
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    assert _buffer_value(app, "EQ-01", "X좌표") == 50.0
    assert not app.error


def test_an_assumption_paste_that_moves_a_saved_unit_is_refused_before_preview(
    tmp_path: Path,
) -> None:
    _, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    app.selectbox(TARGET_KEY).set_value("설비 마스터")
    app.text_area(CLIPBOARD_KEY).set_value("설비명\tX좌표\nEQ-01\t55")
    app.button(PREVIEW_BUTTON_KEY).click()
    _ok(app.run())

    assert PREVIEW_KEY not in app.session_state
    assert any(
        "붙여넣기가 있던 호기 1대(EQ-01)의 배치 칸을 바꿉니다" in text
        for text in _texts(app, "error")
    )
    # 배치 칸이 아닌 칸만 바꾸는 붙여넣기는 미리본다.
    app.text_area(CLIPBOARD_KEY).set_value("설비명\t설비이력\nEQ-01\t붙여넣은 이력")
    app.button(PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    assert isinstance(app.session_state[PREVIEW_KEY], ImportReview)
    assert not app.error


def test_the_paste_check_takes_new_units_and_unchanged_layout_cells(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    current = _session(repository)
    frames = (current.baseline, current.equipment, current.downtime)
    existing = frozenset({"EQ-01", "EQ-02"})

    def review(master: pd.DataFrame) -> ImportReview:
        candidate = (current.baseline, master, current.downtime)
        return ImportReview("설비 마스터", "붙여넣기", frames, candidate, pd.DataFrame())

    added = _with_unit(current.equipment, "EQ-NEW", 70.0, 층="2F")
    assert (
        assumption_paste_refusal(
            review(added), frames, existing=existing, scenario_name="셋업 실무"
        )
        is None
    )
    same = current.equipment.copy()
    assert (
        assumption_paste_refusal(review(same), frames, existing=existing, scenario_name="셋업 실무")
        is None
    )
    shown = current.equipment.assign(레이아웃표시=["N", "Y"])
    refusal = assumption_paste_refusal(
        review(shown), frames, existing=existing, scenario_name="셋업 실무"
    )
    assert refusal is not None and "있던 호기 1대(EQ-01)" in refusal
    # 다른 표의 붙여넣기는 보지 않는다.
    downtime = ImportReview("비가동 일정", "붙여넣기", frames, frames, pd.DataFrame())
    assert assumption_paste_refusal(downtime, frames, existing=existing, scenario_name=None) is None


def test_layout_edits_are_read_by_name_and_kept_cells_come_from_before() -> None:
    from test_equipment_availability import _equipment

    before = _equipment()
    after = before.assign(설비이력=["a", "b"])
    after.loc[1, "Xsize"] = 20
    after.loc[0, "동"] = "C2"

    touched = existing_layout_edits(before, after, existing={"EQ-01", "EQ-02"})
    kept = keep_layout_cells(after, before, touched)

    assert touched == ["EQ-01", "EQ-02"]
    assert existing_layout_edits(before, after, existing={"EQ-02"}) == ["EQ-02"]
    assert kept["동"].tolist() == ["C1", "C1"] and kept["Xsize"].tolist() == [12, 12]
    assert kept["설비이력"].tolist() == ["a", "b"]


# ------------------------------------------------------------------ 다른 시나리오 일정 호기 삭제


def _without(app: AppTest, name: str) -> None:
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    kept = equipment.loc[equipment["설비명"].ne(name)].reset_index(drop=True)
    _store(app, (baseline, kept, downtime))


def _removal_box(app: AppTest) -> Any:
    boxes = [box for box in app.checkbox if str(box.key).startswith(REMOVAL_CONFIRM_KEY)]
    return boxes[0] if boxes else None


def test_removing_a_unit_scheduled_in_another_scenario_needs_the_confirm(tmp_path: Path) -> None:
    repository, setup = _two_scenarios(tmp_path)
    path = tmp_path / "equipment.duckdb"
    app = _ok(_workspace(path, OPERATIONS).run())
    assert _removal_box(app) is None
    _without(app, "EQ-02")
    _ok(app.run())

    assert any(
        "지우는 호기 1대(EQ-02)는 다른 설비 시나리오 1개(「셋업 실무」)에도 일정이 있습니다" in text
        for text in _texts(app, "warning")
    )
    box = _removal_box(app)
    assert box is not None
    assert box.label == "다른 설비 시나리오 1개에서 1대의 일정이 빠지는 것을 알고 저장합니다"

    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(app.run())
    assert len(repository.list_revisions()) == 1
    assert any(
        "저장하려면 가용설비 현황 RawData 저장 칸의" in text for text in _texts(app, "error")
    )

    box = _removal_box(app)
    assert box is not None
    box.check()
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(app.run())
    assert len(repository.list_revisions()) == 2
    assert "EQ-02" not in set(_session(repository).equipment["설비명"])
    assert "EQ-02" not in set(_session(repository, setup).equipment["설비명"])
    assert not app.error


def test_removing_a_unit_only_this_scenario_schedules_needs_no_confirm(tmp_path: Path) -> None:
    repository = _seeded(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", OPERATIONS).run())
    _without(app, "EQ-02")
    _ok(app.run())
    assert _removal_box(app) is None

    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(app.run())
    assert len(repository.list_revisions()) == 2


def test_the_store_lists_units_scheduled_in_other_active_scenarios(tmp_path: Path) -> None:
    repository, setup = _two_scenarios(tmp_path)

    others = dict(repository.units_scheduled_elsewhere(OPERATIONS))
    everywhere = dict(repository.units_scheduled_elsewhere(None))

    assert len(others) == 2 and set(others.values()) == {("셋업 실무",)}
    assert set(everywhere.values()) == {("운영 일정", "셋업 실무")}
    assert set(dict(repository.units_scheduled_elsewhere(setup)).values()) == {("운영 일정",)}


# ------------------------------------------------------------------ 공식 판정 대체 규칙(L13)


def _summary(scenario_id: str, name: str, order: int) -> EquipmentScenarioSummary:
    return EquipmentScenarioSummary(
        scenario_id,
        name,
        "ACTIVE",
        list_order=order,
        latest_schedule_revision_id=f"{scenario_id}-r1",
        latest_revision_no=1,
        revision_count=1,
    )


def test_without_a_release_the_screens_take_operations_like_the_store() -> None:
    reordered = EquipmentScenarioCatalog(
        scenarios=(_summary("setup", "셋업 실무", 0), _summary(OPERATIONS, "운영 일정", 1))
    )
    no_operations = EquipmentScenarioCatalog(
        scenarios=(_summary("setup", "셋업 실무", 0), _summary("plan", "계획", 1))
    )
    released = EquipmentScenarioCatalog(
        scenarios=reordered.scenarios,
        latest_release=EquipmentRelease(2, "setup", "setup-r1", datetime(2026, 10, 25)),
    )

    assert reordered.effective_official_scenario_id == OPERATIONS
    assert no_operations.effective_official_scenario_id == "setup"
    assert released.effective_official_scenario_id == "setup"
    assert EquipmentScenarioCatalog().effective_official_scenario_id is None
    official = EquipmentSession(reordered, reordered.scenario(OPERATIONS), "operations-r1")
    setup = EquipmentSession(reordered, reordered.scenario("setup"), "setup-r1")
    assert official.is_official_scenario and not official.is_assumption
    assert setup.is_assumption and not setup.is_official_pair
    assert _default_selection(reordered) == (OPERATIONS, "operations-r1")
    assert _default_selection(no_operations) == ("setup", "setup-r1")


def test_the_catalog_rule_matches_the_store_on_a_real_database(tmp_path: Path) -> None:
    repository, _ = _two_scenarios(tmp_path)

    assert (
        repository.load_scenario_catalog().effective_official_scenario_id
        == repository.official_scenario_id()
        == OPERATIONS
    )
