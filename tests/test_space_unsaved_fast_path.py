# Purpose: Space 미저장 배치 상자의 셀 비교 생략(빠른 길)이 셀 비교와 같은 답을 내는지 검사한다.

"""편집본이 저장본과 내용까지 같고 이름 바꿈이 없으면 셀 비교(`layout_changes`·`name_changes`·
`other_change_count`·`table_changed`·`unsaved_unit_ids`)를 건너뛴다. 이 파일은 둘을 지킨다.

1. 같은 숫자 — 빠른 길이 참이면 셀 비교도 모두 빈 값이다.
2. 무효화 — 한 칸·한 행·형 하나·이름 바꿈 지도 하나만 달라도 빠른 길을 쓰지 않는다. 특히 편집본
   세대를 올리지 않는 편집(일괄 삭제 확정·되살리기)도 내용으로 잡는다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import space_layout_editor
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_GENERATION_KEY,
    BUFFER_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import space_layout_edit
from capa_simulation.services.space_layout_edit import (
    PendingRenames,
    buffer_matches_saved,
    downtime_with_renames,
    layout_changes,
    name_changes,
    other_change_count,
    table_changed,
    unsaved_unit_ids,
)

Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
FLOOR = ("C1", "1F")
OTHER = ("C2", "2F")
PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"


def _master() -> pd.DataFrame:
    """EQ-01·EQ-02(C1 1F 배치) 에 미배치 호기와 Main 설비 묶음을 더한 마스터."""
    base = _equipment()
    records = base.to_dict(orient="records")
    records += [
        records[0] | {"설비명": "EQ-03", "동": "C2", "층": "2F", "X좌표": None, "Y좌표": None},
        records[0] | {"설비명": "M-1", "Main 설비": "BIG", "X좌표": 50.0, "Y좌표": 30.0},
        records[0] | {"설비명": "M-2", "Main 설비": "BIG", "X좌표": 62.0, "Y좌표": 30.0},
    ]
    return pd.DataFrame(records, columns=base.columns)


def _saved_frames(tmp_path: Path) -> Frames:
    """DB 에 한 번 저장했다 읽은 세 표 — 편집본이 세워지는 저장본과 같은 형이다."""
    repository = DuckDBEquipmentRepository(tmp_path / "fast_path.duckdb")
    repository.initialize()
    snapshot = repository.save_snapshot(_baseline(), _master(), _downtime(), note="r1")
    return snapshot.baseline, snapshot.equipment, snapshot.downtime


def _copy(frames: Frames) -> Frames:
    return frames[0].copy(), frames[1].copy(), frames[2].copy()


def _full_comparison(
    saved: Frames, buffer: Frames, renames: PendingRenames | None = None
) -> dict[str, Any]:
    """빠른 길이 건너뛰는 셀 비교를 모두 돌린 결과."""
    renamed_downtime = downtime_with_renames(saved[2], renames, saved=saved[1], buffer=buffer[1])
    return {
        "layout": layout_changes(saved[1], buffer[1], renames).to_dict(orient="records"),
        "names": name_changes(saved[1], buffer[1], renames).to_dict(orient="records"),
        "others": other_change_count(saved[1], buffer[1], renames),
        "baseline": table_changed(saved[0], buffer[0]),
        "downtime": table_changed(renamed_downtime, buffer[2]),
        "units": {
            floor: unsaved_unit_ids(saved[1], buffer[1], floor, renames) for floor in (FLOOR, OTHER)
        },
    }


NOTHING_CHANGED: dict[str, Any] = {
    "layout": [],
    "names": [],
    "others": 0,
    "baseline": False,
    "downtime": False,
    "units": {FLOOR: (set(), set()), OTHER: (set(), set())},
}


def test_the_fast_path_says_unchanged_only_where_the_full_comparison_finds_nothing(
    tmp_path: Path,
) -> None:
    saved = _saved_frames(tmp_path)
    # 편집본은 저장본 사본으로 선다(`ensure_equipment_drafts`).
    buffer = _copy(saved)

    assert buffer_matches_saved(saved, buffer)
    assert _full_comparison(saved, buffer) == NOTHING_CHANGED
    # 이름 바꿈 지도가 남아 있으면(셀 비교에서는 빈 값이어도) 빠른 길을 쓰지 않는다.
    stale = PendingRenames(units={"EQ-09": "EQ-01"})
    assert not buffer_matches_saved(saved, buffer, stale)
    assert _full_comparison(saved, buffer, stale) == NOTHING_CHANGED


def _drop_unit(frames: Frames, unit_id: str) -> Frames:
    master = frames[1]
    return frames[0], master.loc[master["설비명"].ne(unit_id)].reset_index(drop=True), frames[2]


def _set_cell(frames: Frames, table: int, column: str, value: Any) -> Frames:
    edited = list(_copy(frames))
    edited[table].loc[0, column] = value
    return edited[0], edited[1], edited[2]


EDITS: dict[str, Callable[[Frames], Frames]] = {
    # 일괄 삭제 확정·되살리기는 편집본 세대를 올리지 않는다 — 그래도 내용으로 잡는다.
    "bulk-delete": lambda frames: _drop_unit(frames, "EQ-02"),
    "layout-cell": lambda frames: _set_cell(frames, 1, "X좌표", 41.0),
    "other-cell": lambda frames: _set_cell(frames, 1, "담당자", "담당B"),
    "baseline": lambda frames: _set_cell(frames, 0, "기존보유대수", 3),
    "downtime": lambda frames: _set_cell(frames, 2, "상세사유", "교체"),
    "dtype-only": lambda frames: (frames[0], frames[1].astype({"Xsize": "object"}), frames[2]),
}


@pytest.mark.parametrize("name", list(EDITS))
def test_any_buffer_edit_leaves_the_fast_path(tmp_path: Path, name: str) -> None:
    """한 칸·한 행·형 하나만 달라도 빠른 길을 쓰지 않고 셀 비교로 넘어간다. 셀 비교는 형만 다른
    편집본을 편집으로 세지 않는다(안전한 쪽 — 지금과 같은 답)."""
    saved = _saved_frames(tmp_path)
    buffer = EDITS[name](_copy(saved))

    assert not buffer_matches_saved(saved, buffer)
    result = _full_comparison(saved, buffer)
    expected_changed = {
        "bulk-delete": result["others"] == 1,
        "layout-cell": result["layout"] != [],
        "other-cell": result["others"] == 1,
        "baseline": result["baseline"],
        "downtime": result["downtime"],
        "dtype-only": result == NOTHING_CHANGED,
    }
    assert expected_changed[name], result


# ---------------------------------------------------------------- 화면


@pytest.fixture
def comparisons(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """화면이 부른 셀 비교 함수 이름을 차례로 적는다. 편집기 컴포넌트는 대역이다."""
    calls: list[str] = []
    for name in ("layout_changes", "name_changes", "other_change_count", "unsaved_unit_ids"):
        original = getattr(space_layout_edit, name)

        def counting(*args: Any, _name: str = name, _f: Any = original, **kwargs: Any) -> Any:
            calls.append(_name)
            return _f(*args, **kwargs)

        monkeypatch.setattr(space_layout_edit, name, counting)
    monkeypatch.setattr(
        space_layout_editor, "_EDITOR", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return calls


def _open_floor(tmp_path: Path, *, edit_mode: bool = False) -> AppTest:
    database = tmp_path / "space_fast.duckdb"
    repository = DuckDBEquipmentRepository(database)
    repository.initialize()
    repository.save_snapshot(_baseline(), _master(), _downtime(), note="r1")
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, database), default_timeout=60)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.session_state["space_layout_edit_mode"] = edit_mode
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _panel_text(app: AppTest) -> list[str]:
    texts = [item.value for item in app.markdown if "저장 안 한 배치 변경" in item.value]
    texts += [item.value for item in app.caption if "함께 저장됩니다" in item.value]
    return texts


def test_an_untouched_buffer_runs_no_cell_comparison(
    tmp_path: Path, comparisons: list[str]
) -> None:
    app = _open_floor(tmp_path, edit_mode=True)
    comparisons.clear()
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert comparisons == []
    assert _panel_text(app) == []
    clear_equipment_repository()


def test_a_bulk_delete_without_a_generation_bump_still_reaches_the_panel(
    tmp_path: Path, comparisons: list[str]
) -> None:
    """일괄 삭제 확정처럼 세대를 올리지 않고 편집본만 바꿔도 상자는 지금과 같은 건수를 말한다."""
    app = _open_floor(tmp_path)
    frames = app.session_state[BUFFER_KEY]
    generation = app.session_state[BUFFER_GENERATION_KEY]
    deleted = _drop_unit(frames, "EQ-03")
    moved = deleted[1].copy()
    moved.loc[moved["설비명"].eq("EQ-01"), "X좌표"] = 41.0
    app.session_state[BUFFER_KEY] = (deleted[0], moved, deleted[2])
    comparisons.clear()
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[BUFFER_GENERATION_KEY] == generation
    assert "layout_changes" in comparisons and "other_change_count" in comparisons
    texts = _panel_text(app)
    assert any("호기 배치 1건" in text for text in texts), texts
    assert any("저장 안 한 다른 편집 1건" in text for text in texts), texts
    clear_equipment_repository()


def test_a_rawdata_only_edit_counts_nothing_it_does_not_show(
    tmp_path: Path, comparisons: list[str]
) -> None:
    """배치 변경이 없으면 상자가 서지 않으니 RawData 다른 편집 건수·곁표 비교는 하지 않는다."""
    app = _open_floor(tmp_path)
    app.session_state[BUFFER_KEY] = _set_cell(app.session_state[BUFFER_KEY], 1, "담당자", "담당B")
    comparisons.clear()
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert comparisons == ["layout_changes", "name_changes"]
    assert _panel_text(app) == []
    clear_equipment_repository()
