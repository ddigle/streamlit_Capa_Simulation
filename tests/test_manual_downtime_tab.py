# Purpose: 가용설비 현황 Preference 탭의 저장·다시 그리기·남의 먼저 저장 거부를 AppTest 로 검증한다.

"""가용설비 현황 ③ 「Preference」(`components/manual_downtime_tab.py`).

탭 조각만 띄운 AppTest 둘(두 세션)이 같은 설비 DB 를 본다 — 칸을 고쳐 저장하면 다시 그린 표가 그
값이고, v0 에서 편집을 시작한 다른 세션의 저장은 거부되며 DB 는 그대로다. 실제 화면에서는 탭 셋이
서고 Preference 가 조회기간 줄만 세운다(`navigation`).

편집표 key 는 표가 출발한 version 을 든다(`manual_editor_key`) — 남이 저장한 뒤의 회차·거부 뒤
회차는 새 key 로 최신을 그린다(보내지 않은 편집이 남의 칸을 가린 채 본 version 만 오르던 결함 —
2026-10-27 리뷰). 같은 입력의 꼬리 누름은 「바뀐 칸이 없어」 가 아니라 성공으로 다시 알린다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.manual_downtime_tab import (
    MANUAL_EDITOR_KEY,
    MANUAL_NOTE_KEY,
    MANUAL_SAVE_BUTTON,
    MANUAL_SAVED_BY_KEY,
    edited_cells,
    manual_editor_frame,
    manual_editor_key,
    manual_tab_processes,
)
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.write_guard import TRAILING_PRESS_SECONDS
from capa_simulation.navigation import (
    AVAILABLE_EQUIPMENT_STATUS,
    EQUIPMENT_GAP_TAB,
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_PREFERENCE_TAB,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.manual_downtime import ManualDowntime

A, B = "Wafer Mount", "Final Test"
MONTHS = (202607, 202608)


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    clear_equipment_repository()


def _script(database_path: Path) -> str:
    return f"""
from capa_simulation.components.manual_downtime_tab import render_manual_downtime_tab
from capa_simulation.components.process_labels import ProcessLabels

render_manual_downtime_tab(
    database_path={str(database_path)!r},
    snapshot_processes=[{A!r}, {B!r}],
    months={list(MONTHS)!r},
    process_labels=ProcessLabels(version=1, labels={{{A!r}: "WM"}}),
    owner_tab=None,
)
"""


def _app(database_path: Path) -> AppTest:
    app = AppTest.from_string(_script(database_path), default_timeout=60).run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _edit(app: AppTest, cells: dict[tuple[int, str], float | None], *, version: int = 0) -> None:
    """편집표 칸을 고친다 — 행 위치(표의 공정 차례 A, B)와 달 칸 이름. `version` 은 그 표가 출발한
    저장본 version 이다(편집표 key 가 그것을 든다)."""
    edited: dict[int, dict[str, float | None]] = {}
    for (row, column), value in cells.items():
        edited.setdefault(row, {})[column] = value
    app.session_state[manual_editor_key(version)] = {
        "edited_rows": edited,
        "added_rows": [],
        "deleted_rows": [],
    }


def _save(app: AppTest, *, saved_by: str = "", note: str = "") -> AppTest:
    app.session_state[MANUAL_SAVED_BY_KEY] = saved_by
    app.session_state[MANUAL_NOTE_KEY] = note
    next(button for button in app.button if button.label == MANUAL_SAVE_BUTTON).click()
    app.run()
    assert not app.exception, [element.message for element in app.exception]
    return app


def _editor_values(app: AppTest) -> dict[str, list[object]]:
    frame = next(frame for frame in app.dataframe if MANUAL_EDITOR_KEY in frame.proto.id)
    data = frame.value
    return {column: data[column].tolist() for column in data.columns}


def _editor_id(app: AppTest) -> str:
    return str(
        next(frame for frame in app.dataframe if MANUAL_EDITOR_KEY in frame.proto.id).proto.id
    )


def test_edit_save_and_the_table_redraws_the_saved_values(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    values = _editor_values(app)
    # 첫 칸은 공정 표시명, 달마다 한 칸 — 빈칸으로 시작한다.
    # 행은 원본 공정명 차례(Final Test < Wafer Mount)이고 보이는 글자는 표시명이다.
    assert values["공정"] == [B, "WM"]
    assert bool(pd.Series(values["202607"] + values["202608"], dtype="object").isna().all())

    row_a = values["공정"].index("WM")
    _edit(app, {(row_a, "202607"): 1.5, (1 - row_a, "202608"): 0.25})
    app = _save(app, saved_by="홍길동", note="26.07 PM")

    stored = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert stored.rows == ((B, 202608, 0.25), (A, 202607, 1.5))
    assert (stored.version, stored.saved_by, stored.note) == (1, "홍길동", "26.07 PM")
    assert any("입력 비가동 대수를 저장했습니다" in item.value for item in app.success)

    # 다시 그린 표(새 세션 — 위젯 편집 없이)는 저장한 값이다.
    fresh = _editor_values(_app(path))
    row_a = fresh["공정"].index("WM")
    assert fresh["202607"][row_a] == pytest.approx(1.5)
    assert fresh["202608"][1 - row_a] == pytest.approx(0.25)
    saves = DuckDBEquipmentRepository(path).load_manual_downtime_saves()
    assert [(save.version, save.changed_cells, save.filled_cells) for save in saves] == [(1, 2, 2)]


def test_a_save_without_saver_and_memo_shows_a_caption_without_doubled_separators(
    tmp_path: Path,
) -> None:
    """저장자·변경 메모는 선택이다 — 둘 다 비운 저장의 버전 캡션은 출처 자리를 건너뛴
    `공용 버전 v1 · <저장 시각>` 이다(2026-10-27 E2E — `v1 · · 2026-…` 처럼 구분자가 겹쳤다)."""
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    row_a = _editor_values(app)["공정"].index("WM")
    _edit(app, {(row_a, "202607"): 1.0})
    app = _save(app)

    stored = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert (stored.version, stored.saved_by, stored.note) == (1, "", "")
    captions = [item.value for item in app.caption if item.value.startswith("공용 버전 ")]
    assert stored.updated_at is not None
    assert captions == [f"공용 버전 v1 · {stored.updated_at:%Y-%m-%d %H:%M}"]


def test_a_second_session_that_started_from_the_old_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    first, second = _app(path), _app(path)
    row_a = _editor_values(first)["공정"].index("WM")

    _edit(first, {(row_a, "202607"): 1.0})
    _save(first)
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1

    # 둘째 세션은 v0 화면에서 편집했다 — 거부되고 DB 는 첫 세션의 값 그대로다.
    _edit(second, {(row_a, "202607"): 9.0})
    second = _save(second)
    assert any("다른 사용자가 먼저" in item.value for item in second.error)
    stored = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert (stored.rows, stored.version) == (((A, 202607, 1.0),), 1)

    # 거부 뒤 회차는 새 key(v1)로 최신을 그린다 — 거부된 9.0 이 아니라 첫 세션의 1.0 이다.
    assert manual_editor_key(1) in _editor_id(second)
    assert _editor_values(second)["202607"][row_a] == pytest.approx(1.0)

    # 거부 뒤 최신을 본 화면에서 다시 누른 저장(겹친 누름 창이 지난 뒤)은 저장된다.
    time.sleep(TRAILING_PRESS_SECONDS + 0.1)
    _edit(second, {(row_a, "202607"): 2.0}, version=1)
    _save(second)
    stored = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert (stored.rows, stored.version) == (((A, 202607, 2.0),), 2)


def test_another_sessions_save_redraws_the_table_from_the_new_version(tmp_path: Path) -> None:
    """남이 저장하면 다음 회차(제출 아님)는 새 key 로 그 저장본을 그린다 — 보내지 않은 편집이 남의
    칸을 가린 채 본 version 만 최신으로 오르지 않는다(2026-10-27 리뷰 samecell)."""
    path = tmp_path / "equipment.duckdb"
    first, second = _app(path), _app(path)
    assert manual_editor_key(0) in _editor_id(second)
    row_a = _editor_values(first)["공정"].index("WM")

    _edit(first, {(row_a, "202607"): 12.0})
    _save(first)
    # 둘째 세션은 v0 표에 적어 둔 칸이 있었다(보내지 않음). 탭 왕복 같은 회차 한 번이 돈다.
    _edit(second, {(row_a, "202607"): 1.0})
    second.run()
    assert not second.exception
    assert manual_editor_key(1) in _editor_id(second)
    assert _editor_values(second)["202607"][row_a] == pytest.approx(12.0)
    assert any("공용 버전 v1" in item.value for item in second.caption)

    # 그 화면에서 누른 저장은 v1 위에서 새로 적은 것만 싣는다 — 첫 세션의 칸을 몰래 덮지 않는다.
    _edit(second, {(1 - row_a, "202608"): 0.5}, version=1)
    _save(second)
    stored = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert (stored.rows, stored.version) == (((B, 202608, 0.5), (A, 202607, 12.0)), 2)


def test_a_trailing_press_of_the_same_input_repeats_the_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """저장 뒤 새로 그린 표에서 온 같은 입력의 둘째 누름은 「바뀐 칸이 없어」 가 아니라 성공을 다시
    알린다(2026-10-27 리뷰 dblclick). 창이 지난 같은 입력은 전처럼 「바뀐 칸이 없어」 다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 60.0)
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    row_a = _editor_values(app)["공정"].index("WM")
    _edit(app, {(row_a, "202607"): 1.5})
    _save(app)
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1

    app = _save(app)
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1
    assert any("입력 비가동 대수를 저장했습니다" in item.value for item in app.success)
    assert not any("바뀐 칸이 없어" in item.value for item in app.info)

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = _save(app)
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1
    assert any("바뀐 칸이 없어" in item.value for item in app.info)


def test_an_unchanged_save_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    app = _save(_app(path))
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 0
    assert any("바뀐 칸이 없어" in item.value for item in app.info)


def test_a_locked_tab_shows_the_reason_and_cannot_save(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    script = _script(path).replace("owner_tab=None,", "owner_tab=None, locked_reason='잠금'")
    app = AppTest.from_string(script, default_timeout=60).run()
    assert not app.exception
    assert any(item.value == "잠금" for item in app.info)
    assert next(button for button in app.button if button.label == MANUAL_SAVE_BUTTON).disabled


# ------------------------------------------------------------------ 표 재료(순수)


def test_the_editor_frame_lists_snapshot_processes_then_stored_only_ones() -> None:
    profile = ManualDowntime(rows=(("Gone", 202607, 1.0), (A, 202608, 0.5)), version=2)
    processes, absent = manual_tab_processes([A, B, " ", A], profile)
    assert processes == (B, A, "Gone") and absent == frozenset({"Gone"})
    frame = manual_editor_frame(profile, processes, MONTHS, ProcessLabels(), absent=absent)
    assert frame["공정"].tolist() == [B, A, "Gone (설비 마스터에 없음)"]
    assert frame.loc["Gone", "202607"] == 1.0 and pd.isna(frame.loc[B, "202607"])
    cells = edited_cells(frame, processes, MONTHS)
    assert cells[("Gone", 202607)] == 1.0 and cells[(B, 202608)] is None
    assert len(cells) == len(processes) * len(MONTHS)


def test_the_preference_tab_reads_only_the_period_on_the_sidebar() -> None:
    """Preference 는 조회기간 줄만 세운다 — 시나리오 줄은 Static 대비 일정 탭에서만 선다."""
    spec = AVAILABLE_EQUIPMENT_STATUS
    assert spec.reads_period_only_on(EQUIPMENT_PREFERENCE_TAB)
    assert not spec.reads_common_conditions_on(EQUIPMENT_PREFERENCE_TAB)
    assert not spec.reads_period_only_on(EQUIPMENT_MASTER_TAB)
    assert spec.reads_common_conditions_on(EQUIPMENT_GAP_TAB)
    assert not spec.has_cards_on(EQUIPMENT_PREFERENCE_TAB)


def test_the_month_columns_are_numbers_with_two_decimals(tmp_path: Path) -> None:
    app = _app(tmp_path / "equipment.duckdb")
    frame = next(frame for frame in app.dataframe if MANUAL_EDITOR_KEY in frame.proto.id)
    columns = json.loads(frame.proto.columns)
    assert columns["202607"]["label"] == "26.07"
    assert columns["202607"]["type_config"]["min_value"] == 0
    assert columns["202607"]["type_config"]["format"] == "%.2f"
