# Purpose: 설비 직접 편집에서 필터로 고른 호기를 딸린 일정과 함께 지우고 되돌리는 화면을 검증한다.

"""**필터를 적용했든 안 했든, 고른 조건대로 한 번에 지운다.**

AppTest 는 편집표의 칸을 누를 수 없다. 그래서 칸을 누르지 않는 길 — 필터 조건을 고르고
「필터에 맞는 행 모두 선택」을 누르는 길 — 로 선택부터 저장까지 끝에서 끝까지 돈다. 칸을 눌러
고르는 길은 `test_equipment_bulk_delete.py` 가 추출 함수로 본다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    CONFIRM_DELETE_BUTTON_KEY,
    EDIT_SAVE_BUTTON_KEY,
    SELECTION_KEY,
    UNDO_DELETE_BUTTON_KEY,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_bulk_delete import EQUIPMENT_TARGET
from capa_simulation.services.equipment_contract import BASELINE_COLUMNS
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EQUIPMENT_PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
BUILDING_FILTER_KEY = "equipment_master_view_filter_동"
SELECT_MATCHING_KEY = "equipment_master_select_matching_v1"
DELETE_SELECTED_KEY = "equipment_master_delete_selected_v1"


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


def _seeded(tmp_path: Path) -> Path:
    """호기 54대·비가동 14건이 저장된 설비 DB. C4 동에는 호기 9대와 비가동 4건이 있다."""
    database = tmp_path / "bulk_delete.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    today = date.today()
    repository.save_snapshot(
        pd.DataFrame(columns=list(BASELINE_COLUMNS)),
        sample_equipment_master(anchor_date=today),
        sample_downtime_schedule(anchor_date=today),
        note="일괄 삭제 화면 검증",
    )
    return database


def _machines(app: AppTest) -> list[str]:
    return sorted(app.session_state[BUFFER_KEY][1]["호기"].astype(str))


def _downtime_machines(app: AppTest) -> list[str]:
    return sorted(app.session_state[BUFFER_KEY][2]["호기"].astype(str))


def _in_c4(values: list[str]) -> list[str]:
    return [value for value in values if value.startswith("SAMPLE-C4")]


def test_select_by_an_unapplied_filter_then_delete_confirm_and_undo(tmp_path: Path) -> None:
    app = AppTest.from_string(_page_script(_seeded(tmp_path)), default_timeout=120).run()
    assert not app.exception, [item.message for item in app.exception]
    assert len(_machines(app)) == 54 and len(_downtime_machines(app)) == 14

    # 필터만 고르고 「보기 적용」은 누르지 않는다.
    app.multiselect(key=BUILDING_FILTER_KEY).set_value(["C4"])
    app.button(key=SELECT_MATCHING_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert {key[0] for key in app.session_state[SELECTION_KEY][EQUIPMENT_TARGET]} == {
        f"SAMPLE-C42F-{number:02d}" for number in range(1, 10)
    }

    app.button(key=DELETE_SELECTED_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    warning = " ".join(item.value for item in app.warning)
    assert "호기 9대" in warning and "비가동 일정 4건도 함께" in warning
    assert len(_machines(app)) == 54  # 확정 전에는 아무것도 빠지지 않는다

    app.button(key=CONFIRM_DELETE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert len(_machines(app)) == 45 and not _in_c4(_machines(app))
    assert len(_downtime_machines(app)) == 10 and not _in_c4(_downtime_machines(app))

    app.button(key=UNDO_DELETE_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert len(_machines(app)) == 54 and len(_downtime_machines(app)) == 14


def test_a_confirmed_deletion_saves_without_orphaned_downtime(tmp_path: Path) -> None:
    """호기만 지우고 일정을 남기면 저장이 「호기 마스터에 없는 설비의 비가동 일정」으로 막힌다."""
    database = _seeded(tmp_path)
    app = AppTest.from_string(_page_script(database), default_timeout=120).run()
    app.multiselect(key=BUILDING_FILTER_KEY).set_value(["C4"])
    app.button(key=SELECT_MATCHING_KEY).click().run()
    app.button(key=DELETE_SELECTED_KEY).click().run()
    app.button(key=CONFIRM_DELETE_BUTTON_KEY).click().run()

    app.button(key=EDIT_SAVE_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    repository = DuckDBEquipmentRepository(database)
    latest = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    assert len(latest.equipment) == 45 and len(latest.downtime) == 10


def test_deleting_with_nothing_selected_says_so_and_changes_nothing(tmp_path: Path) -> None:
    app = AppTest.from_string(_page_script(_seeded(tmp_path)), default_timeout=120).run()

    app.button(key=DELETE_SELECTED_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any("선택한 행이 없습니다" in item.value for item in app.info)
    assert len(_machines(app)) == 54
