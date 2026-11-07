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
from alert_marks import infos, place_errors
from grid_fake import Calls, grid_results, install_fake_grid, last, load, send_ops
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_GENERATION_KEY,
    BUFFER_KEY,
    CONFIRM_DELETE_BUTTON_KEY,
    DELETE_CONFIRM_HELP,
    DOWNTIME_EDITOR_KEY,
    GRID_DETAIL_KEY,
    GRID_UNDO_KEY,
    LAST_REMOVED_KEY,
    SELECTION_KEY,
)
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_KEY,
    TABLE_KEY,
    TABLE_MASTER,
    UNDO_BUTTON_KEY,
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


def _press_undo(app: AppTest) -> None:
    """「저장 전 변경」 의 「한 단계 되돌리기」 — 그 칸을 열고 누른다."""
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=UNDO_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]


def _delete_downtime(app: AppTest, machine: str) -> None:
    """비가동 일정 작은 편집표에서 그 호기 일정을 골라 「선택 행 삭제」 · 「삭제 확정」."""
    app.session_state[TABLE_KEY] = DOWNTIME_TARGET
    app.run()
    app.multiselect(key=DOWNTIME_FILTER_KEY).set_value([machine])
    app.button(key=DOWNTIME_SELECT_MATCHING_KEY).click().run()
    app.button(key=DOWNTIME_DELETE_SELECTED_KEY).click().run()
    app.button(key=CONFIRM_DELETE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]


def _memo(app: AppTest, machine: str) -> object:
    master = app.session_state[BUFFER_KEY][1].set_index("설비명")
    return master.loc[machine, "메모1"]


def _delete_building(app: AppTest, grid: Calls, seed: _Seed) -> list[str]:
    """그 동 호기를 불러와(조건별 — 브라우저가 고른 id) 모두 고르고 지운다."""
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
    assert grid_results(app, "success") == [f"{len(ids):,}대 지울 목록에 넣음"]

    _press_undo(app)
    assert grid_results(app, "success") == ["되돌림: 호기 지움"]
    assert _machines(app) == sorted(seed.machines)
    assert len(_downtime_machines(app)) == seed.downtime_count


def test_the_detail_delete_result_is_one_value_line_in_the_alert_popup(
    tmp_path: Path, grid: Calls
) -> None:
    """호기 상세 「이 호기 지우기」 의 결과는 알림창 값 한 줄이다 — 저장해야 지워진다 · 모든 설비
    시나리오에서 빠진다는 말은 단추 풍선 · Guide 다(2026-11-05 사용자 답)."""
    seed = _seeded(tmp_path)
    app = _app(seed)
    name = sorted(seed.building_machines)[0]
    app.session_state[GRID_DETAIL_KEY] = f"s:{name}"
    app.run()

    send_ops(app, grid, {"op": "delete", "ids": [f"s:{name}"]}, key=emg.side_key("detail"))

    assert grid_results(app, "success") == ["1대 지울 목록에 넣음"]
    assert last(grid, emg.side_key("detail"))["toast"] is None


def test_a_deletion_saves_without_orphaned_downtime(tmp_path: Path, grid: Calls) -> None:
    """호기만 지우고 일정을 남기면 저장이 「설비 마스터에 없는 설비의 비가동 일정」으로 막힌다."""
    seed = _seeded(tmp_path)
    app = _app(seed)
    _delete_building(app, grid, seed)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=SAVE_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not place_errors(app), [item.value for item in app.error]
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
_CLEAN_GENERATION_KEY = "equipment_workspace_clean_generation_v1"


def _has_unsaved_edits(app: AppTest) -> bool:
    """`has_unsaved_equipment_edits()` 와 같은 판정(편집본 세대 > 세운 세대, 저장본으로 돌아온 세대
    빼고)을 세션 값으로 본다."""
    generation = int(app.session_state[BUFFER_GENERATION_KEY])
    clean = (
        app.session_state[_CLEAN_GENERATION_KEY]
        if _CLEAN_GENERATION_KEY in app.session_state
        else None
    )
    return generation > int(app.session_state[_SEEDED_GENERATION_KEY]) and generation != clean


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
    # 다 되살리면 저장할 것이 없다 — 표시는 걷힌다(`test_equipment_unsaved_mark.py`).
    assert not _has_unsaved_edits(app)
    # 되살린 자리는 저장본 차례다 — 차례만 다른 공통 리비전을 만들지 않는다.
    saved = DuckDBEquipmentRepository(seed.database)
    latest = saved.load_snapshot(saved.list_revisions()[0].revision_id)
    assert (
        app.session_state[BUFFER_KEY][1]["설비명"].tolist() == latest.equipment["설비명"].tolist()
    )


def test_the_downtime_small_editor_keeps_the_old_bulk_delete(tmp_path: Path, grid: Calls) -> None:
    """비가동 일정 작은 편집표 — 필터로 고르고 「선택 행 삭제」·「삭제 확정」, 되살리기는 「저장 전
    변경」 의 「한 단계 되돌리기」. 확인은 값 한 줄과 「삭제 확정」 풍선이고(설계 규칙 UI-NTF-09 —
    상자 · 대상 목록을 늘어놓지 않는다), 확정 알림이 무엇을 얼마나 지웠는지와 저장 · 되살리기 단추를
    말한다. 표 위에는 상자도 단추도 남지 않는다(설계 규칙 UI-NTF-03)."""
    seed = _seeded(tmp_path)
    app = _app(seed)
    app.session_state[TABLE_KEY] = DOWNTIME_TARGET
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    machine = sorted(set(_downtime_machines(app)))[0]
    count = _downtime_machines(app).count(machine)
    # 이름은 짧게, 뜻은 풍선에(설계 규칙 UI-LAY-11 — 표 위 작업 줄 한 줄).
    assert app.button(key=DOWNTIME_SELECT_MATCHING_KEY).label == "모두 선택"
    assert "필터에 맞는 행" in str(app.button(key=DOWNTIME_SELECT_MATCHING_KEY).help)
    app.multiselect(key=DOWNTIME_FILTER_KEY).set_value([machine])
    app.button(key=DOWNTIME_SELECT_MATCHING_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert {key[0] for key in app.session_state[SELECTION_KEY][DOWNTIME_TARGET]} == {machine}
    app.button(key=DOWNTIME_DELETE_SELECTED_KEY).click().run()
    assert f"비가동 일정 {count:,}건 지움" in [item.value for item in app.caption]
    assert not [item for item in app.warning if "지움" in str(item.value)]
    # 풍선 끝은 지금 저장 단추를 가리킨다 — 옛 「설비 데이터 저장」(옛 폼 단추)이 아니라 「저장
    # 전 변경」 의 「리비전 저장」 이다(개편 D — Guide 의 글과 같다).
    tail = DELETE_CONFIRM_HELP
    assert "「리비전 저장」" in tail and "「한 단계 되돌리기」" in tail
    assert app.button(key=CONFIRM_DELETE_BUTTON_KEY).help == tail
    app.button(key=CONFIRM_DELETE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    done = next(str(item.value) for item in infos(app) if "지웠습니다. 대상" in str(item.value))
    assert done.startswith(
        f"비가동 일정 {count:,}건을 편집본에서 지웠습니다. 대상: {literal_markdown(machine)}"
    )
    assert done.endswith(tail) and "설비 데이터 저장" not in done
    assert len(_downtime_machines(app)) == seed.downtime_count - count
    assert _machines(app) == sorted(seed.machines)  # 비가동만 지운다
    assert not app.info, [item.value for item in app.info]
    assert not [item for item in app.button if "되돌리기" in str(item.label)]
    _press_undo(app)
    assert grid_results(app, "info") == ["방금 지운 행을 편집본에 되살렸습니다."]
    assert len(_downtime_machines(app)) == seed.downtime_count
    assert LAST_REMOVED_KEY not in app.session_state


def test_one_step_undo_takes_table_steps_first_and_the_bulk_delete_under_them(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """표 조작 → 일괄 삭제 → 표 조작 뒤 — 일괄 삭제가 그 앞 표 단계를 비워 삭제가 맨 위이고, 그 뒤
    쌓인 표 조작부터 되돌린 다음 삭제를 되살린다. 그 앞 고침은 값이 남고 되돌리지 않는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    seed = _seeded(tmp_path)
    app = _app(seed)
    machine = sorted(set(_downtime_machines(app)))[0]
    unit = f"s:{machine}"
    load(app, [unit], kind="names", label=machine)
    send_ops(app, grid, {"op": "cell", "id": unit, "col": "메모1", "text": "삭제 전"})
    assert GRID_UNDO_KEY in app.session_state
    count = _downtime_machines(app).count(machine)

    _delete_downtime(app, machine)
    assert GRID_UNDO_KEY not in app.session_state
    assert grid_results(app, "info")[-1].startswith("표 밖에서 편집본을 바꿔")

    app.session_state[TABLE_KEY] = TABLE_MASTER
    app.run()
    send_ops(app, grid, {"op": "cell", "id": unit, "col": "메모1", "text": "삭제 뒤"})
    assert _memo(app, machine) == "삭제 뒤"

    _press_undo(app)
    assert grid_results(app, "success") == ["되돌림: 메모1 고침"]
    assert _memo(app, machine) == "삭제 전"
    assert len(_downtime_machines(app)) == seed.downtime_count - count

    _press_undo(app)
    assert grid_results(app, "info") == ["방금 지운 행을 편집본에 되살렸습니다."]
    assert len(_downtime_machines(app)) == seed.downtime_count
    assert _memo(app, machine) == "삭제 전"

    _press_undo(app)
    assert grid_results(app, "info") == ["되돌릴 고침이 없습니다"]
    assert _memo(app, machine) == "삭제 전"


def test_renaming_after_a_bulk_delete_leaves_nothing_for_one_step_undo_to_bring_back(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이름을 바꾸면 지운 행은 옛 이름을 지녀 되살릴 수 없다(`follow_unit_renames`) — 이름 바꿈은
    되돌려도 삭제는 돌아오지 않는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    seed = _seeded(tmp_path)
    app = _app(seed)
    machine = sorted(set(_downtime_machines(app)))[0]
    unit = f"s:{machine}"
    load(app, [unit], kind="names", label=machine)
    _delete_downtime(app, machine)
    left = len(_downtime_machines(app))
    app.session_state[TABLE_KEY] = TABLE_MASTER
    app.run()

    send_ops(app, grid, {"op": "cell", "id": unit, "col": "설비명", "text": "NEW-NAME"})
    assert LAST_REMOVED_KEY not in app.session_state

    _press_undo(app)
    assert grid_results(app, "success") == ["되돌림: 설비명 고침"]
    _press_undo(app)
    assert grid_results(app, "info") == ["되돌릴 고침이 없습니다"]
    assert len(_downtime_machines(app)) == left


def test_restoring_a_bulk_delete_stands_that_table_editor_up_anew(
    tmp_path: Path, grid: Calls
) -> None:
    """되살리기는 콜백이라 편집표 위젯이 서기 전이다 — 그 표의 줄 번호 delta 가 되살린 표 위에
    얹히지 않게 새 위젯으로 세운다."""
    seed = _seeded(tmp_path)
    app = _app(seed)
    machine = sorted(set(_downtime_machines(app)))[0]
    _delete_downtime(app, machine)
    generation = f"{DOWNTIME_EDITOR_KEY}__generation"
    before = app.session_state[generation] if generation in app.session_state else 0

    _press_undo(app)

    assert app.session_state[generation] > before
    assert len(_downtime_machines(app)) == seed.downtime_count


def _infos(app: AppTest, needle: str) -> list[str]:
    return [str(item.value) for item in infos(app) if needle in str(item.value)]


@pytest.mark.parametrize(("window", "kept"), [(3600.0, True), (0.0, False)])
def test_a_double_press_on_confirm_and_undo_keeps_their_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grid: Calls, window: float, kept: bool
) -> None:
    """작은 편집표 「삭제 확정」 을 사람 속도(0.2초)로 두 번 누르면 둘째 누름은 첫 회차가 꺼낸 확인
    대기의 단추에 닿아 아무것도 하지 않는 회차가 되는데, 첫 회차가 꺼내 그린 「…편집본에서
    지웠습니다」 를 그 회차가 지웠다(2026-10-27 E2E 5/9 — 행은 한 번만 지워짐). 삭제를 되살리는
    「한 단계 되돌리기」 도 같다. 쓰기 알림 표지가 창 안이면 같은 info 꼴로 다시 그린다 — 창이 0
    이면 옛 동작이다."""
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

    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    app.button(key=UNDO_BUTTON_KEY).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert len(_infos(app, "방금 지운 행을 편집본에 되살렸습니다")) == 1
    app._run(widget_state=pressed)
    assert not app.exception, [item.message for item in app.exception]
    assert len(_infos(app, "방금 지운 행을 편집본에 되살렸습니다")) == (1 if kept else 0)
    assert len(_downtime_machines(app)) == seed.downtime_count
