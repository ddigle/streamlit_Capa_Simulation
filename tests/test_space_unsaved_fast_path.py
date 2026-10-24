# Purpose: Space 미저장 배치 상자의 셀 비교 생략(빠른 길)이 셀 비교와 같은 답을 내는지 검사한다.

"""편집본이 저장본과 내용까지 같고 이름 바꿈이 없으면 셀 비교(`layout_changes`·`name_changes`·
`other_change_count`·`table_changed`·`unsaved_unit_ids`)를 건너뛴다. 이 파일은 둘을 지킨다.

1. 같은 숫자 — 빠른 길이 참이면 셀 비교도 모두 빈 값이다.
2. 무효화 — 한 칸·한 행·형 하나·이름 바꿈 지도 하나만 달라도 빠른 길을 쓰지 않는다. 특히 편집본
   세대를 올리지 않는 편집(일괄 삭제 확정·되살리기)도 내용으로 잡는다.

화면은 두 곳이 빠른 길을 쓴다 — 미저장 배치 상자와 편집 모드 편집기의 「옮겨 온 호기·새 호기」
표지. 두 곳 모두 셀 비교를 모두 돌린 결과(빠른 길이 없던 기준 코드의 출력)와 같은지 본다.
"""

from __future__ import annotations

import re
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
    PENDING_RENAMES_KEY,
)
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services import space_layout_edit
from capa_simulation.services.equipment_bulk_delete import (
    BASELINE_TARGET,
    DOWNTIME_TARGET,
    EQUIPMENT_TARGET,
    apply_deletion,
    plan_deletion,
    restore_rows,
    row_keys,
)
from capa_simulation.services.space_layout_edit import (
    NEW_UNIT_HISTORY,
    NameChange,
    PendingRenames,
    apply_name_changes,
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


# ---------------------------------- 화면: 셀 비교를 모두 돌린 결과(기준 코드)와 같은가


def _expected_panel(saved: Frames, buffer: Frames, renames: PendingRenames | None = None) -> Any:
    """빠른 길이 없던 기준 코드처럼 셀 비교를 모두 돌려 상자 머리 항목·다른 편집 건수·곁표를 낸다.
    배치·이름 변경이 없으면 상자가 서지 않는다(캔버스·요소·FAB 대기분이 없는 이 시험에서)."""
    changes = layout_changes(saved[1], buffer[1], renames)
    names = name_changes(saved[1], buffer[1], renames)
    parts = [f"호기 배치 {len(changes)}건"] if not changes.empty else []
    if not names.empty:
        parts.append(f"이름 바꿈 {len(names)}건")
    if not parts:
        return None
    renamed_downtime = downtime_with_renames(saved[2], renames, saved=saved[1], buffer=buffer[1])
    side = [
        label
        for label, before, after in (
            (BASELINE_TARGET, saved[0], buffer[0]),
            (DOWNTIME_TARGET, renamed_downtime, buffer[2]),
        )
        if table_changed(before, after)
    ]
    return parts, other_change_count(saved[1], buffer[1], renames), side


def _shown_panel(app: AppTest) -> Any:
    """화면 상자의 머리 항목·다른 편집 건수·곁표. 상자가 없으면 None."""
    heads = [item.value for item in app.markdown if "저장 안 한 배치 변경" in item.value]
    if not heads:
        return None
    assert len(heads) == 1, heads
    caption = next(item.value for item in app.caption if "적용한 변경은 이 화면" in item.value)
    others = re.search(r"다른 편집 (\d+)건", caption)
    side = re.search(r"RawData 의 ([^.]+?) 표 편집도", caption)
    return (
        heads[0].split(" — ", 1)[1].split(" · "),
        int(others.group(1)) if others else 0,
        side.group(1).split("·") if side else [],
    )


@pytest.fixture
def editor_items(
    comparisons: list[str], monkeypatch: pytest.MonkeyPatch
) -> list[list[dict[str, Any]]]:
    """편집 모드 편집기 대역이 받은 호기 목록(그린 회차마다 하나). `comparisons` 의 대역을
    덮는다."""
    received: list[list[dict[str, Any]]] = []

    def capturing(**kwargs: Any) -> SimpleNamespace:
        if str(kwargs.get("key", "")).startswith("space_layout_editor_"):
            received.append(list(kwargs["data"]["items"]))
        return SimpleNamespace(apply=None)

    monkeypatch.setattr(space_layout_editor, "_EDITOR", capturing)
    return received


def _flags(items: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """편집기 호기 목록의 (새 호기, 옮겨 온 호기)."""
    return (
        {str(item["id"]) for item in items if item["isNew"]},
        {str(item["id"]) for item in items if item["arrived"]},
    )


def _rerun_with(
    app: AppTest, buffer: Frames, renames: PendingRenames | None = None
) -> tuple[AppTest, int]:
    """편집본(과 이름 바꿈 지도)만 바꾸고 세대는 올리지 않은 채 다시 돌린다."""
    generation = app.session_state[BUFFER_GENERATION_KEY]
    app.session_state[BUFFER_KEY] = buffer
    if renames is not None:
        app.session_state[PENDING_RENAMES_KEY] = {
            "units": dict(renames.units),
            "groups": dict(renames.groups),
        }
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app, generation


def test_the_editor_marks_arrived_and_new_units_from_an_edit_without_a_generation_bump(
    tmp_path: Path, comparisons: list[str], editor_items: list[list[dict[str, Any]]]
) -> None:
    """편집 모드에서 세대를 올리지 않고 편집본만 바꿔도 편집기는 다른 층에서 옮겨 온 호기와 새 호기
    표지를 받는다 — 빠른 길은 편집본이 저장본과 같을 때만 쓴다."""
    app = _open_floor(tmp_path, edit_mode=True)
    saved = _copy(app.session_state[BUFFER_KEY])
    assert _flags(editor_items[-1]) == (set(), set())
    master = saved[1].copy()
    moved = master["설비명"].eq("EQ-03")
    master.loc[moved, ["동", "층"]] = ["C1", "1F"]
    master.loc[moved, ["X좌표", "Y좌표"]] = [70.0, 10.0]
    new_unit = master.loc[master["설비명"].eq("EQ-01")].copy()
    new_unit[["설비명", "호기이력"]] = ["EQ-NEW", NEW_UNIT_HISTORY]
    new_unit[["X좌표", "Y좌표"]] = [80.0, 30.0]
    buffer = (saved[0], pd.concat([master, new_unit], ignore_index=True), saved[2])
    comparisons.clear()
    editor_items.clear()

    app, generation = _rerun_with(app, buffer)

    assert app.session_state[BUFFER_GENERATION_KEY] == generation
    assert "unsaved_unit_ids" in comparisons
    assert _flags(editor_items[-1]) == ({"EQ-NEW"}, {"EQ-03"})
    assert _flags(editor_items[-1]) == unsaved_unit_ids(saved[1], buffer[1], FLOOR)
    assert _shown_panel(app) == _expected_panel(saved, buffer)
    clear_equipment_repository()


def test_a_pending_swap_on_an_unchanged_buffer_reaches_the_panel_and_the_editor(
    tmp_path: Path, comparisons: list[str], editor_items: list[list[dict[str, Any]]]
) -> None:
    """이름 바꿈 지도는 편집본이 저장본과 같아도 빠른 길을 막는다(상자·편집기 둘 다). 다른 층 호기와
    이름을 맞바꾼 지도면 이 층 호기는 「옮겨 온 호기」이고 상자는 배치·이름 바꿈을 센다."""
    app = _open_floor(tmp_path, edit_mode=True)
    saved = _copy(app.session_state[BUFFER_KEY])
    swap = PendingRenames(units={"EQ-01": "EQ-03", "EQ-03": "EQ-01"})
    comparisons.clear()
    editor_items.clear()

    app, _ = _rerun_with(app, _copy(saved), swap)

    assert buffer_matches_saved(saved, app.session_state[BUFFER_KEY])
    assert "unsaved_unit_ids" in comparisons and "layout_changes" in comparisons
    assert _flags(editor_items[-1]) == unsaved_unit_ids(saved[1], saved[1], FLOOR, swap)
    assert _flags(editor_items[-1]) == (set(), {"EQ-01"})
    expected = _expected_panel(saved, saved, swap)
    assert expected is not None and "이름 바꿈 2건" in expected[0]
    assert _shown_panel(app) == expected
    clear_equipment_repository()


def test_a_rename_only_buffer_shows_the_same_panel_as_the_full_comparison(
    tmp_path: Path, comparisons: list[str], editor_items: list[list[dict[str, Any]]]
) -> None:
    """이름만 바꾼 편집본(설비명·비가동 일정이 따라감 + 지도): 상자는 이름 바꿈만 말하고, 편집기는
    바꾼 이름을 새 호기로 읽지 않는다."""
    app = _open_floor(tmp_path, edit_mode=True)
    saved = _copy(app.session_state[BUFFER_KEY])
    master, downtime = apply_name_changes(
        saved[1], saved[2], [NameChange(kind="unit", old="EQ-01", new="EQ-101")]
    )
    buffer = (saved[0], master, downtime)
    renames = PendingRenames(units={"EQ-101": "EQ-01"})
    editor_items.clear()

    app, _ = _rerun_with(app, buffer, renames)

    assert _shown_panel(app) == _expected_panel(saved, buffer, renames)
    assert _shown_panel(app) == (["이름 바꿈 1건"], 0, [])
    assert _flags(editor_items[-1]) == unsaved_unit_ids(saved[1], buffer[1], FLOOR, renames)
    assert _flags(editor_items[-1]) == (set(), set())
    clear_equipment_repository()


def test_a_bulk_delete_and_its_restore_show_the_same_panel_as_the_full_comparison(
    tmp_path: Path, comparisons: list[str]
) -> None:
    """일괄 삭제 확정과 되살리기는 둘 다 세대를 올리지 않는다. 배치를 하나 옮긴 편집본에서 호기를
    지우면 상자가 다른 편집 1건을 더 말하고, 되살리면 그 건수가 빠진다 — 셀 비교를 모두 돌린 결과와
    같다."""
    app = _open_floor(tmp_path)
    saved = _copy(app.session_state[BUFFER_KEY])
    moved = _set_cell(saved, 1, "X좌표", 41.0)
    doomed = row_keys(moved[1].loc[moved[1]["설비명"].eq("EQ-02")], EQUIPMENT_TARGET)
    plan = plan_deletion(moved, EQUIPMENT_TARGET, doomed)
    deleted = apply_deletion(moved, plan)

    app, generation = _rerun_with(app, deleted)
    assert _shown_panel(app) == _expected_panel(saved, deleted)
    assert _shown_panel(app) == (["호기 배치 1건"], 1, [])

    restored, skipped = restore_rows(deleted, plan.removed)
    assert skipped == 0
    app, _ = _rerun_with(app, restored)

    assert app.session_state[BUFFER_GENERATION_KEY] == generation
    assert _shown_panel(app) == _expected_panel(saved, restored)
    assert _shown_panel(app) == (["호기 배치 1건"], 0, [])
    clear_equipment_repository()


def test_restoring_the_only_deletion_returns_to_the_fast_path(
    tmp_path: Path, comparisons: list[str]
) -> None:
    """다른 편집 없이 지웠다 되살리면 편집본은 지우기 전 차례 그대로라 저장본과 같다 — 그 회차부터
    셀 비교를 건너뛴다. 지운 회차는 셀 비교로 넘어간다(배치 변경이 없어 상자는 서지 않는다)."""
    app = _open_floor(tmp_path)
    saved = _copy(app.session_state[BUFFER_KEY])
    doomed = row_keys(saved[1].loc[saved[1]["설비명"].eq("EQ-02")], EQUIPMENT_TARGET)
    plan = plan_deletion(saved, EQUIPMENT_TARGET, doomed)
    deleted = apply_deletion(saved, plan)
    comparisons.clear()

    app, generation = _rerun_with(app, deleted)
    assert comparisons == ["layout_changes", "name_changes"]
    assert _shown_panel(app) is None and _expected_panel(saved, deleted) is None

    restored, _ = restore_rows(deleted, plan.removed)
    comparisons.clear()
    app, _ = _rerun_with(app, restored)

    assert app.session_state[BUFFER_GENERATION_KEY] == generation
    assert buffer_matches_saved(saved, restored)
    assert comparisons == []
    assert _shown_panel(app) is None
    clear_equipment_repository()


@pytest.mark.parametrize("edited", [False, True])
def test_the_first_run_after_someone_elses_save_compares_against_the_new_revision(
    tmp_path: Path, comparisons: list[str], edited: bool
) -> None:
    """남이 새 리비전을 저장한 뒤 이 세션이 공식으로 옮겨 온 첫 회차: 편집본은 새 저장본으로 다시
    서고(미저장 편집은 버려짐) 상자는 서지 않는다 — 셀 비교를 모두 돌린 결과와 같다.

    세션은 고른 설비 시나리오 리비전을 고정해 든다(E5). 남의 저장(래퍼는 공식으로 발행한다)
    뒤에는 그 세션이 공식 발행 쌍이 아니라 Space 배치 편집이 잠기고 편집본을 건드리지 않는다 —
    사이드바에서 최신을 불러온 것(선택을 새 공식으로 옮김)을 시험이 대신한다.
    """
    app = _open_floor(tmp_path)
    if edited:
        frames = app.session_state[BUFFER_KEY]
        app, _ = _rerun_with(app, _set_cell(frames, 1, "X좌표", 41.0))
        assert _shown_panel(app) is not None
    other = _master()
    other.loc[other["설비명"].eq("EQ-02"), "X좌표"] = 77.0
    database = tmp_path / "space_fast.duckdb"
    latest = DuckDBEquipmentRepository(database).save_snapshot(
        _baseline(), other, _downtime(), note="r2-other"
    )
    clear_equipment_repository()
    comparisons.clear()
    app.run()
    # 고정한 세션은 공식이 아니게 됐다 — 편집이 잠기고 편집본은 그대로다.
    assert not app.exception, [item.message for item in app.exception]
    assert _shown_panel(app) is None
    assert latest.schedule is not None
    app.session_state[SELECTION_KEY] = {
        "scenario_id": latest.schedule.equipment_scenario_id,
        "schedule_revision_id": latest.schedule.schedule_revision_id,
    }
    comparisons.clear()
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    newest: Frames = (latest.baseline, latest.equipment, latest.downtime)
    buffer = app.session_state[BUFFER_KEY]
    assert buffer[1].loc[buffer[1]["설비명"].eq("EQ-02"), "X좌표"].tolist() == [77.0]
    assert _expected_panel(newest, buffer) is None
    assert _shown_panel(app) is None
    assert comparisons == []
    clear_equipment_repository()
