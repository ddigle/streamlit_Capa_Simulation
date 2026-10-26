# Purpose: 설비 마스터 표에서 고른 호기를 딸린 일정과 함께 지우고 되돌려 저장하는 화면을 검증한다.

"""**고른 호기를 한 번에 지운다 — 딸린 비가동 일정도 함께.**

옛 설비 마스터 편집표의 「필터에 맞는 행 모두 선택」·「선택 행 삭제」·「삭제 확정」 길은 설비
마스터 표(개편 B1)의 불러오기(조건) → 고르기 → 「선택 n대 지우기」(출납 `delete` — 확인 없이 바로,
토스트 「되돌리기」) 로 바뀌었다. AppTest 는 표 JS 를 못 돌리므로 대역(`tests/grid_fake.py`)이
브라우저가 보낼 불러오기·출납을 보낸다. 비가동 일정 작은 편집표의 일괄 삭제(옛 길 그대로)는 마지막
시험이 본다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, last, load, send_ops
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_GENERATION_KEY,
    BUFFER_KEY,
    CONFIRM_DELETE_BUTTON_KEY,
    SELECTION_KEY,
    UNDO_DELETE_BUTTON_KEY,
)
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
    TABLE_KEY,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_bulk_delete import DOWNTIME_TARGET
from capa_simulation.services.equipment_contract import BASELINE_COLUMNS
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EQUIPMENT_PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
DOWNTIME_FILTER_KEY = "equipment_downtime_view_filter_설비명"
DOWNTIME_SELECT_MATCHING_KEY = "equipment_downtime_select_matching_v1"
DOWNTIME_DELETE_SELECTED_KEY = "equipment_downtime_delete_selected_v1"


@pytest.fixture(autouse=True)
def _release_repository() -> object:
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _page_script(database_path: Path) -> str:
    """두 DB 경로를 임시 폴더로 격리해 화면을 실행한다. 이 파일 혼자 성립해야 한다."""
    simulation_database_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    return f"""
from pathlib import Path

import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
settings.DUCKDB_PATH = Path({str(simulation_database_path)!r})
page_source = Path({str(EQUIPMENT_PAGE)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(EQUIPMENT_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
"""


@dataclass(frozen=True)
class _Seed:
    """저장한 샘플에서 계산한 기대값. 표본의 대수·건수를 테스트에 적지 않으려고 둔다."""

    database: Path
    machines: frozenset[str]
    downtime_count: int
    building: str
    building_machines: frozenset[str]
    building_downtime_count: int


def _seeded(tmp_path: Path) -> _Seed:
    """샘플 호기·비가동 일정을 저장한 설비 DB 와, 그 프레임에서 계산한 기대값.

    지울 동은 비가동 일정이 딸린 첫 동이다 — 일정이 없는 동을 고르면 「함께 지운다」 경로를
    밟지 않는다.
    """
    database = tmp_path / "bulk_delete.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    today = date.today()
    equipment = sample_equipment_master(anchor_date=today)
    downtime = sample_downtime_schedule(anchor_date=today)
    repository.save_snapshot(
        pd.DataFrame(columns=list(BASELINE_COLUMNS)),
        equipment,
        downtime,
        note="일괄 삭제 화면 검증",
    )

    building_of = dict(
        zip(equipment["설비명"].astype(str), equipment["동"].astype(str), strict=True)
    )
    downtime_buildings = downtime["설비명"].astype(str).map(building_of)
    building = sorted(set(downtime_buildings.dropna()))[0]
    building_machines = frozenset(
        machine for machine, owner in building_of.items() if owner == building
    )
    seed = _Seed(
        database=database,
        machines=frozenset(building_of),
        downtime_count=len(downtime),
        building=building,
        building_machines=building_machines,
        building_downtime_count=int((downtime_buildings == building).sum()),
    )
    # 전제: 고른 동은 일부만 차지하고, 딸린 일정이 있다. 깨지면 아래 검사가 아무것도 말하지 않는다.
    assert 0 < len(seed.building_machines) < len(seed.machines)
    assert 0 < seed.building_downtime_count < seed.downtime_count
    return seed


def _app(seed: _Seed) -> AppTest:
    app = AppTest.from_string(_page_script(seed.database), default_timeout=120)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _machines(app: AppTest) -> list[str]:
    return sorted(app.session_state[BUFFER_KEY][1]["설비명"].astype(str))


def _downtime_machines(app: AppTest) -> list[str]:
    return sorted(app.session_state[BUFFER_KEY][2]["설비명"].astype(str))


def _delete_building(app: AppTest, grid: Calls, seed: _Seed) -> list[str]:
    """그 동 호기를 불러와(조건으로 불러오기 — 브라우저가 고른 id) 모두 고르고 지운다."""
    ids = [f"s:{name}" for name in sorted(seed.building_machines)]
    load(app, ids, kind="conditions", label=f"동 {seed.building}")
    assert [row["id"] for row in last(grid, emg.GRID_KEY)["rows"]] == ids
    send_ops(app, grid, {"op": "delete", "ids": ids})
    return ids


def test_deleting_loaded_units_takes_their_downtime_and_undo_brings_both_back(
    tmp_path: Path, grid: Calls
) -> None:
    seed = _seeded(tmp_path)
    total = len(seed.machines)
    app = _app(seed)
    assert _machines(app) == sorted(seed.machines)
    ids = _delete_building(app, grid, seed)

    assert len(_machines(app)) == total - len(seed.building_machines)
    assert not seed.building_machines & set(_machines(app))
    assert len(_downtime_machines(app)) == seed.downtime_count - seed.building_downtime_count
    # 지운 저장본 호기는 목록에 남아 지운 표시(되살리기 자리)로 선다.
    table = last(grid, emg.GRID_KEY)
    assert {row["id"]: row.get("tag") for row in table["rows"]} == dict.fromkeys(ids, "deleted")
    toast = table["toast"]
    assert toast["text"].startswith(f"{len(ids)}대를 지울 목록에 넣었습니다")
    assert isinstance(toast["undo"], str) and toast["undo"]

    send_ops(app, grid, {"op": "undo", "step": toast["undo"]})
    assert _machines(app) == sorted(seed.machines)
    assert len(_downtime_machines(app)) == seed.downtime_count


def test_a_deletion_saves_without_orphaned_downtime(tmp_path: Path, grid: Calls) -> None:
    """호기만 지우고 일정을 남기면 저장이 「설비 마스터에 없는 설비의 비가동 일정」으로 막힌다."""
    seed = _seeded(tmp_path)
    app = _app(seed)
    _delete_building(app, grid, seed)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    repository = DuckDBEquipmentRepository(seed.database)
    latest = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    assert len(latest.equipment) == len(seed.machines) - len(seed.building_machines)
    assert len(latest.downtime) == seed.downtime_count - seed.building_downtime_count


def test_a_delete_op_with_nothing_chosen_changes_nothing(tmp_path: Path, grid: Calls) -> None:
    seed = _seeded(tmp_path)
    app = _app(seed)
    before = int(app.session_state[BUFFER_GENERATION_KEY])
    send_ops(app, grid, {"op": "delete", "ids": []})
    assert _machines(app) == sorted(seed.machines)
    assert int(app.session_state[BUFFER_GENERATION_KEY]) == before


_SEEDED_GENERATION_KEY = "equipment_workspace_seeded_generation_v1"


def _has_unsaved_edits(app: AppTest) -> bool:
    """`has_unsaved_equipment_edits()` 와 같은 판정(편집본 세대 > 세운 세대)을 세션 값으로 본다."""
    return int(app.session_state[BUFFER_GENERATION_KEY]) > int(
        app.session_state[_SEEDED_GENERATION_KEY]
    )


def test_a_deletion_alone_counts_as_an_unsaved_edit(tmp_path: Path, grid: Calls) -> None:
    """다른 칸은 고치지 않고 지우기만 한 편집본도 「저장하지 않은 편집」이다.

    세대가 오르지 않으면 테마 단추가 묻지 않고 새로고침하고, 다른 사람이 저장했을 때 삭제가
    말없이 사라진다(버렸다는 알림이 서지 않는다).
    """
    seed = _seeded(tmp_path)
    app = _app(seed)
    assert not _has_unsaved_edits(app)
    _delete_building(app, grid, seed)
    assert len(_machines(app)) == len(seed.machines) - len(seed.building_machines)
    assert _has_unsaved_edits(app)

    # 다른 사람이 새 리비전을 저장하면 이 삭제를 버렸다고 알린다.
    repository = DuckDBEquipmentRepository(seed.database)
    latest = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    repository.save_snapshot(
        latest.baseline, latest.equipment, latest.downtime, note="다른 사용자 저장"
    )
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    warning = " ".join(item.value for item in app.warning)
    assert "다른 사용자가 공통 대장 r2" in warning and "버리고" in warning
    assert _machines(app) == sorted(seed.machines)


def test_restoring_a_deleted_unit_raises_the_buffer_generation_again(
    tmp_path: Path, grid: Calls
) -> None:
    """되살리기도 편집본을 바꾼다 — 세대가 올라야 그 세대를 보는 쪽이 새 편집본을 본다."""
    seed = _seeded(tmp_path)
    app = _app(seed)
    ids = _delete_building(app, grid, seed)
    after_delete = int(app.session_state[BUFFER_GENERATION_KEY])

    send_ops(app, grid, {"op": "restore", "ids": ids})

    assert _machines(app) == sorted(seed.machines)
    assert int(app.session_state[BUFFER_GENERATION_KEY]) > after_delete
    # 되살린 자리는 저장본 차례다 — 차례만 다른 공통 리비전을 만들지 않는다.
    saved = DuckDBEquipmentRepository(seed.database)
    latest = saved.load_snapshot(saved.list_revisions()[0].revision_id)
    assert (
        app.session_state[BUFFER_KEY][1]["설비명"].tolist() == latest.equipment["설비명"].tolist()
    )


def test_the_downtime_small_editor_keeps_the_old_bulk_delete(tmp_path: Path, grid: Calls) -> None:
    """비가동 일정 작은 편집표 — 필터로 고르고 「선택 행 삭제」·「삭제 확정」·「방금 삭제
    되돌리기」. 확인 글과 확정 알림이 무엇을 얼마나 지우는지와 지금 저장 단추를 말한다."""
    seed = _seeded(tmp_path)
    app = _app(seed)
    app.session_state[TABLE_KEY] = DOWNTIME_TARGET
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    machine = sorted(set(_downtime_machines(app)))[0]
    count = _downtime_machines(app).count(machine)
    app.multiselect(key=DOWNTIME_FILTER_KEY).set_value([machine])
    app.button(key=DOWNTIME_SELECT_MATCHING_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert {key[0] for key in app.session_state[SELECTION_KEY][DOWNTIME_TARGET]} == {machine}
    app.button(key=DOWNTIME_DELETE_SELECTED_KEY).click().run()
    # 확인 글 끝은 지금 저장 단추를 가리킨다 — 옛 「설비 데이터 저장」(옛 폼 단추)이 아니라 「저장
    # 전 변경」 의 「리비전 저장」 이다(개편 D — 런북 7-21·Guide 의 글과 같다).
    tail = "확정해도 「저장 전 변경」 의 「리비전 저장」 을 눌러야 새 리비전에 반영됩니다."
    warning = next(str(item.value) for item in app.warning if "지웁니다" in str(item.value))
    assert warning.startswith(
        f"비가동 일정 {count:,}건을 편집본에서 지웁니다. 대상: {literal_markdown(machine)}"
    )
    assert warning.endswith(tail) and "설비 데이터 저장" not in warning
    app.button(key=CONFIRM_DELETE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    done = next(str(item.value) for item in app.info if "지웠습니다. 대상" in str(item.value))
    assert done == warning.replace("지웁니다", "지웠습니다", 1)
    assert len(_downtime_machines(app)) == seed.downtime_count - count
    assert _machines(app) == sorted(seed.machines)  # 비가동만 지운다
    app.button(key=UNDO_DELETE_BUTTON_KEY).click().run()
    assert len(_downtime_machines(app)) == seed.downtime_count


def _infos(app: AppTest, needle: str) -> list[str]:
    return [str(item.value) for item in app.info if needle in str(item.value)]


@pytest.mark.parametrize(("window", "kept"), [(3600.0, True), (0.0, False)])
def test_a_double_press_on_confirm_and_undo_keeps_their_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grid: Calls, window: float, kept: bool
) -> None:
    """작은 편집표 「삭제 확정」 을 사람 속도(0.2초)로 두 번 누르면 둘째 누름은 첫 회차가 꺼낸 확인
    대기의 단추에 닿아 아무것도 하지 않는 회차가 되는데, 첫 회차가 꺼내 그린 「…편집본에서
    지웠습니다」 를 그 회차가 지웠다(2026-10-27 E2E 5/9 — 행은 한 번만 지워짐). 「방금 삭제
    되돌리기」 도 같다. 쓰기 알림 표지가 창 안이면 같은 info 꼴로 다시 그린다 — 창이 0 이면 옛
    동작이다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    seed = _seeded(tmp_path)
    app = _app(seed)
    app.session_state[TABLE_KEY] = DOWNTIME_TARGET
    app.run()
    machine = sorted(set(_downtime_machines(app)))[0]
    count = _downtime_machines(app).count(machine)
    app.multiselect(key=DOWNTIME_FILTER_KEY).set_value([machine])
    app.button(key=DOWNTIME_SELECT_MATCHING_KEY).click().run()
    app.button(key=DOWNTIME_DELETE_SELECTED_KEY).click().run()
    app.button(key=CONFIRM_DELETE_BUTTON_KEY).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert len(_infos(app, "편집본에서 지웠습니다")) == 1

    app._run(widget_state=pressed)

    assert not app.exception, [item.message for item in app.exception]
    assert len(_infos(app, "편집본에서 지웠습니다")) == (1 if kept else 0)
    assert len(_downtime_machines(app)) == seed.downtime_count - count
    assert _infos(app, "저장하기 전까지 되돌릴 수 있습니다")

    app.button(key=UNDO_DELETE_BUTTON_KEY).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert len(_infos(app, "방금 지운 행을 편집본에 되살렸습니다")) == 1
    app._run(widget_state=pressed)
    assert not app.exception, [item.message for item in app.exception]
    assert len(_infos(app, "방금 지운 행을 편집본에 되살렸습니다")) == (1 if kept else 0)
    assert len(_downtime_machines(app)) == seed.downtime_count
