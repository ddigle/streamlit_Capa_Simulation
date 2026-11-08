# Purpose: 가용설비 현황 Preference 탭의 저장·다시 그리기·남의 먼저 저장 거부를 AppTest 로 검증한다.

"""가용설비 현황 ③ 「Preference」(`components/manual_downtime_tab.py`).

탭 조각만 띄운 AppTest 둘(두 세션)이 같은 설비 DB 를 본다 — 칸을 고쳐 저장하면 다시 그린 표가 그
값이고, v0 에서 편집을 시작한 다른 세션의 저장은 거부되며 DB 는 그대로다. 실제 화면에서는 탭 셋이
서고 Preference 가 조회기간 줄만 세운다(`navigation`).

편집표 key 는 표가 출발한 version 을 든다(`manual_editor_key`) — 남이 저장한 뒤의 회차·거부 뒤
회차는 새 key 로 최신을 그린다(보내지 않은 편집이 남의 칸을 가린 채 본 version 만 오르던 결함 —
2026-10-27 리뷰). 남의 저장에 거부된 누름의 둘째 누름 회차도 최신 key 로 그려 그 뒤 친 칸이 다음
누름에 닿는다. 같은 입력의 꼬리 누름은 「바뀐 칸이 없어」 가 아니라 성공으로 다시 알린다.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import pytest
from alert_marks import infos, successes
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import TextInput

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.manual_downtime_tab import (
    MANUAL_BASE_VERSION_KEY,
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
from capa_simulation.components.profile_caption import HEADING_BASELINE_STYLE
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


def _memo(app: AppTest) -> TextInput:
    """변경 메모 칸 — 저장에 성공해도 key 가 그대로다(재시작 뒤 앞 세션 탭의 칸이 남는다)."""
    return app.text_input(key=MANUAL_NOTE_KEY)


def _save(app: AppTest, *, saved_by: str | None = None, note: str | None = None) -> AppTest:
    if saved_by is not None:
        app.session_state[MANUAL_SAVED_BY_KEY] = saved_by
    if note is not None:
        _memo(app).set_value(note)
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


def _drawn_version(app: AppTest) -> int:
    """이 회차가 그린 편집표 key 의 version — 브라우저에서 사용자가 칸을 치는 위젯이다."""
    found = re.search(r"__v(\d+)", _editor_id(app))
    assert found is not None, _editor_id(app)
    return int(found.group(1))


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
    assert any("입력 비가동 대수를 저장했습니다" in item.value for item in successes(app))

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
    # 버전 줄은 제목 옆 한 줄이다(g18 — `render_profile_heading`, 글자 밑줄 맞춤 규칙이 끝에
    # 붙는다).
    captions = [
        item.value.removesuffix(HEADING_BASELINE_STYLE)
        for item in app.caption
        if item.value.startswith("공용 버전 ")
    ]
    assert stored.updated_at is not None
    assert captions == [f"공용 버전 v1 · {stored.updated_at:%Y-%m-%d %H:%M}"]


def test_a_saved_note_leaves_the_field_and_only_the_saver_stays_for_the_next_save(
    tmp_path: Path,
) -> None:
    """저장에 성공하면 변경 메모 칸이 빈다 — 다시 적지 않은 메모가 값만 고친 다음 저장의 기록에
    실렸다. 저장자 칸은 같은 화면의 다음 저장에 이어 쓰도록 남는다."""
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    row_a = _editor_values(app)["공정"].index("WM")
    _edit(app, {(row_a, "202607"): 1.0})
    app = _save(app, saved_by="홍길동", note="첫 메모")
    assert _memo(app).value == ""
    assert app.session_state[MANUAL_SAVED_BY_KEY] == "홍길동"

    _edit(app, {(row_a, "202607"): 2.0}, version=1)
    app = _save(app)

    saves = DuckDBEquipmentRepository(path).load_manual_downtime_saves()
    assert [(save.version, save.saved_by, save.note) for save in saves] == [
        (2, "홍길동", ""),
        (1, "홍길동", "첫 메모"),
    ]


def test_a_refused_or_unchanged_save_keeps_the_typed_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """쓰지 않은 저장은 적은 메모를 지우지 않는다 — 까닭을 고쳐 다시 누르면 그 메모가 실린다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    path = tmp_path / "equipment.duckdb"
    first, second = _app(path), _app(path)
    row_a = _editor_values(first)["공정"].index("WM")

    second = _save(second, note="그대로")
    assert any("바뀐 칸이 없어" in item.value for item in infos(second))
    assert _memo(second).value == "그대로"

    _edit(first, {(row_a, "202607"): 1.0})
    _save(first)
    _edit(second, {(row_a, "202607"): 9.0})
    second = _save(second, note="거부될 메모")
    assert any("다른 사용자가 먼저" in item.value for item in second.error)
    assert _memo(second).value == "거부될 메모"


def test_a_double_press_that_cut_the_first_run_still_empties_the_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """둘째 누름이 첫 저장의 뒷정리를 끊으면 칸을 비울 표지가 없다 — 제 저장임을 알아본 둘째 회차가
    칸을 비운다. AppTest 는 두 요청을 겹칠 수 없어 누른 화면의 위젯 값과 끊긴 회차가 남긴 본
    version 을 되살려 한 번 더 보낸다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    row_a = _editor_values(app)["공정"].index("WM")
    _edit(app, {(row_a, "202607"): 1.0})
    _memo(app).set_value("첫 메모")
    next(button for button in app.button if button.label == MANUAL_SAVE_BUTTON).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1

    app.session_state[MANUAL_BASE_VERSION_KEY] = 0
    app._run(widget_state=pressed)

    assert not app.exception, [element.message for element in app.exception]
    assert any("입력 비가동 대수를 저장했습니다" in item.value for item in successes(app))
    assert _memo(app).value == ""
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1


@pytest.mark.parametrize(
    ("window", "seen_version"),
    [(60.0, 0), (60.0, 1), (0.0, 0)],
    ids=[
        "same-cells-from-the-screen-before-the-save",
        "same-cells-from-the-redrawn-screen",
        "refused-by-the-version-check",
    ],
)
def test_a_second_press_with_another_note_keeps_the_note_it_did_not_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: float, seen_version: int
) -> None:
    """첫 저장의 둘째 누름으로 판정된 누름은 쓰지 않으니 메모도 기록에 들지 않는다 — 다른 메모면
    칸에 남긴다. 같은 칸의 꼬리 누름(`save_once` 가 첫 결과를 돌려준다)과 버전 대조 거부 두
    갈래다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", window)
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    row_a = _editor_values(app)["공정"].index("WM")
    _edit(app, {(row_a, "202607"): 1.0})
    app = _save(app, note="첫 메모")
    assert _memo(app).value == ""

    app.session_state[MANUAL_BASE_VERSION_KEY] = seen_version
    _edit(app, {(row_a, "202607"): 1.0}, version=seen_version)
    app = _save(app, note="둘째 메모")

    assert any("입력 비가동 대수를 저장했습니다" in item.value for item in successes(app))
    assert _memo(app).value == "둘째 메모"
    saves = DuckDBEquipmentRepository(path).load_manual_downtime_saves()
    assert [(save.version, save.note) for save in saves] == [(1, "첫 메모")]


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


def test_a_value_typed_after_a_held_second_press_reaches_the_next_press(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남의 저장에 거부된 누름의 둘째 누름(held) 회차는 최신 저장본으로 표를 그리고, 그 표에 친 값은
    다음 누름에 닿는다.

    둘째 누름이 거부 뒤 회차를 본 version 을 적기 전에 끊으면 본 값이 옛 version 이다. 그 회차가 옛
    key 로 표를 그리면 거부된 제 값이 남의 값 자리에 보이고, 본 version 은 최신으로 적혀 다음 누름의
    표가 다른 위젯이 되므로 그 사이 친 값이 버려져 「바뀐 칸이 없어」 가 섰다(2026-11-02 사본 앱 두
    세션 — 0.15초 더블클릭). 끊긴 회차는 본 version 을 옛 값으로 되살려 흉내 낸다.
    """
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    path = tmp_path / "equipment.duckdb"
    first, second = _app(path), _app(path)
    row_a = _editor_values(first)["공정"].index("WM")
    _edit(first, {(row_a, "202607"): 1.0})
    _save(first)

    _edit(second, {(row_a, "202607"): 9.0})
    next(button for button in second.button if button.label == MANUAL_SAVE_BUTTON).click()
    pressed = second._tree.get_widget_states()
    second.run()
    assert any("다른 사용자가 먼저" in item.value for item in second.error)
    second.session_state[MANUAL_BASE_VERSION_KEY] = 0
    second._run(widget_state=pressed)
    assert not second.exception, [element.message for element in second.exception]
    assert any("다른 사용자가 먼저" in item.value for item in second.error)
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1
    # 그 회차의 표는 거부된 9.0 이 아니라 남이 저장한 1.0 이다.
    assert _drawn_version(second) == 1
    assert _editor_values(second)["202607"][row_a] == pytest.approx(1.0)

    # 거부 표지의 창이 지났다 — 그 표에 새 값을 치고 한 번 누른 저장이다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    _edit(second, {(1 - row_a, "202608"): 0.5}, version=_drawn_version(second))
    second = _save(second)

    assert not any("바뀐 칸이 없어" in item.value for item in second.info)
    stored = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert (stored.rows, stored.version) == (((B, 202608, 0.5), (A, 202607, 1.0)), 2)


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


def test_the_second_press_of_a_refused_press_redraws_the_latest_so_the_next_press_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남의 저장에 거부된 누름의 둘째 누름(held)이 거부 뒤 회차를 끊었을 때 — 그 회차는 본
    version 을 최신으로 적으므로 칸도 최신 key 로 그린다. 옛 key(본 값 v0)로 그리면 거부된 옛 편집이
    선 채 남고, 그 위에 친 칸은 다음 누름의 최신 key 위젯에 닿지 않아 「바뀐 칸이 없어」 로
    버려졌다(2026-11-02 E2E — 둘째 누름 간격 0.13 ~ 0.23초)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    path = tmp_path / "equipment.duckdb"
    app, other = _app(path), _app(path)
    row_a = _editor_values(app)["공정"].index("WM")
    # 남이 v0 위에서 다른 칸을 저장한다(v1).
    _edit(other, {(1 - row_a, "202608"): 0.5})
    _save(other)
    # 이 화면은 v0 표에 적어 둔 칸(보내지 않음)으로 누른다 — 거부된다.
    _edit(app, {(row_a, "202607"): 9.0})
    app = _save(app)
    assert any("다른 사용자가 먼저" in item.value for item in app.error)

    # 둘째 누름이 거부 뒤 회차를 본 값을 적기 전에 끊었다 — 본 값은 v0 그대로이고, 브라우저는 옛 v0
    # 표의 편집을 든 채 보낸다.
    app.session_state[MANUAL_BASE_VERSION_KEY] = 0
    _edit(app, {(row_a, "202607"): 9.0})
    app = _save(app)
    errors = [item.value for item in app.error]
    assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
    assert manual_editor_key(1) in _editor_id(app)
    values = _editor_values(app)
    assert bool(pd.Series(values["202607"], dtype="object").isna().iloc[row_a])
    assert values["202608"][1 - row_a] == pytest.approx(0.5)
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1

    # 창이 지난 뒤 보이는 표에 새로 친 칸으로 누르면 그 칸이 든다 — 남의 칸도 그대로다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    _edit(app, {(row_a, "202608"): 1.25}, version=_drawn_version(app))
    app = _save(app)
    assert not any("바뀐 칸이 없어" in item.value for item in infos(app))
    stored = DuckDBEquipmentRepository(path).load_manual_downtime()
    assert (stored.rows, stored.version) == (((B, 202608, 0.5), (A, 202608, 1.25)), 2)


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
    assert any("입력 비가동 대수를 저장했습니다" in item.value for item in successes(app))
    assert not any("바뀐 칸이 없어" in item.value for item in infos(app))

    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    app = _save(app)
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 1
    assert any("바뀐 칸이 없어" in item.value for item in infos(app))


def test_an_unchanged_save_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    app = _save(_app(path))
    assert DuckDBEquipmentRepository(path).load_manual_downtime().version == 0
    assert any("바뀐 칸이 없어" in item.value for item in infos(app))


def test_a_locked_tab_shows_the_reason_and_cannot_save(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    script = _script(path).replace("owner_tab=None,", "owner_tab=None, locked_reason='잠금'")
    app = AppTest.from_string(script, default_timeout=60).run()
    assert not app.exception
    # 자리에는 표지 한 마디, 까닭은 풍선이다 — 표지 풍선과 꺼진 저장 단추(검수표 11/02 equip-44 와
    # 같은 꼴).
    assert not any(item.value == "잠금" for item in infos(app))
    assert any(item.proto.help == "잠금" for item in app.caption)
    save = next(button for button in app.button if button.label == MANUAL_SAVE_BUTTON)
    assert save.disabled and save.help == "잠금"


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
