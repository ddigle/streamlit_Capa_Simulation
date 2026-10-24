# Purpose: 이름 바꾸기 공용 함수 넷과 RawData 이름 바꿈 목록·저장 결과 꼬리를 검사한다.

"""G4·R2 — 이름 바꾸기는 같은 호기다(설비 시나리오 2단계 S1).

Space 편집기·설비 마스터 호기 상세(개편)가 같은 함수 넷을 쓴다: `check_unit_rename`(Space 거부
문구 그대로), `compose_unit_renames`(저장 안 한 이름 지도), `rename_followers`(비가동 설비명·자기
이름 한 행 묶음의 Main 설비), `follow_unit_renames`(RawData 선택·삭제 대기·목록 필터·되돌리기
기억). RawData 는
Space 에서 바꾼 저장 안 한 이름을 같은 목록 꼴로 보이고, 지운 + 새 호기 저장 결과는 이름 바꾸기 길을
알린다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _downtime
from test_space_layout_rename import _bundle_master, _master, _parse, _rename

from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    DOWNTIME_VIEW_PREFIX,
    LAST_REMOVED_KEY,
    MASTER_VIEW_PREFIX,
    NAME_CHANGES_CAPTION,
    PENDING_DELETE_KEY,
    PENDING_RENAMES_KEY,
    RENAME_INSTEAD_HINT,
    SELECTION_KEY,
    save_result_message,
)
from capa_simulation.components.table_view_controls import filter_widget_key
from capa_simulation.persistence.equipment_repository import (
    EquipmentRevisionSummary,
    EquipmentSaveResult,
)
from capa_simulation.services.equipment_bulk_delete import (
    BASELINE_TARGET,
    DOWNTIME_TARGET,
    EQUIPMENT_TARGET,
)
from capa_simulation.services.space_layout_edit import (
    NameChange,
    PendingRenames,
    ReservedNames,
    apply_name_changes,
    check_unit_rename,
    compose_renames,
    compose_unit_renames,
    rename_followers,
    reserved_names,
)

# ------------------------------------------------------------------ check_unit_rename


def _space_refusal(master: pd.DataFrame, old: str, new: str, **overrides: Any) -> str:
    """같은 바꿈을 Space 편집기 적용값으로 보냈을 때의 거부 문구."""
    with pytest.raises(ValueError) as caught:
        _parse(_rename(("unit", old, new)), master, **overrides)
    return str(caught.value)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("EQ-01", "eq-02"),  # 다른 호기와 대소문자만 다름
        ("EQ-01", " big "),  # 다른 묶음의 Main 설비 이름
        ("EQ-01", "m-3"),  # 편집기에 없는 형제도 설비 마스터의 이름
        ("EQ-01", "   "),  # 비울 수 없음
        ("EQ-01", "X" * 41),  # 글자 수
        ("EQ-01", "EQ\t101"),  # 탭·특수 공백
    ],
)
def test_check_unit_rename_refuses_with_the_space_words(old: str, new: str) -> None:
    master = _bundle_master()

    refusal = check_unit_rename(old, new, master=master)

    assert refusal is not None
    assert refusal == _space_refusal(master, old, new)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("EQ-01", "EQ-101"),
        ("EQ-01", "eq-01"),  # 자기 이름 대소문자만
        ("EQ-01", " EQ-01 "),  # 앞뒤 공백만 — 바꿀 것이 없다
    ],
)
def test_check_unit_rename_takes_a_free_name_and_a_case_only_change(old: str, new: str) -> None:
    assert check_unit_rename(old, new, master=_bundle_master()) is None


def test_check_unit_rename_lets_a_self_named_single_row_group_follow() -> None:
    master = _master({"설비명": "SOLO", "Main 설비": "SOLO", "X좌표": 70.0, "Y좌표": 40.0})

    assert check_unit_rename("SOLO", "SOLO-2", master=master) is None


def test_check_unit_rename_reads_swaps_chains_and_clashes_in_one_submit() -> None:
    master = _master()
    # 맞바꿈 A↔B — 서로의 옛 이름이 비워진다.
    assert check_unit_rename("EQ-01", "EQ-02", master=master, renaming={"EQ-02": "EQ-01"}) is None
    # 사슬 A→B·B→C.
    assert check_unit_rename("EQ-01", "EQ-02", master=master, renaming={"EQ-02": "EQ-03"}) is None
    # 두 호기를 같은 새 이름으로.
    clash = check_unit_rename("EQ-01", "NEW-9", master=master, renaming={"EQ-02": "new-9"})
    assert clash is not None and "이번 적용에서 EQ-02 도 new-9로 바꿉니다" in clash
    with pytest.raises(ValueError) as caught:
        _parse(_rename(("unit", "EQ-01", "NEW-9"), ("unit", "EQ-02", "new-9")), master)
    assert clash == str(caught.value)
    # 다른 바꿈이 걸려도 이 바꿈의 판정만 낸다.
    assert check_unit_rename("EQ-01", "EQ-101", master=master, renaming={"EQ-02": "  "}) is None


def test_check_unit_rename_keeps_the_reserved_names_out() -> None:
    saved = _master()
    buffer = saved.loc[saved["설비명"].ne("EQ-02")].reset_index(drop=True)
    reserved = reserved_names(saved, buffer, _downtime(), None)

    refusal = check_unit_rename("EQ-01", "eq-02", master=buffer, reserved=reserved)

    assert refusal is not None and "RawData 에서 지우고 아직 저장하지" in refusal
    assert refusal == _space_refusal(buffer, "EQ-01", "eq-02", reserved=reserved)
    orphan = ReservedNames(orphan_downtime=frozenset({"GHOST"}))
    assert "비가동 일정을 먼저 고치거나" in str(
        check_unit_rename("EQ-01", "ghost", master=saved, reserved=orphan)
    )


def _renamed(master: pd.DataFrame, renames: dict[str, str]) -> pd.DataFrame:
    """설비명을 바꾼 **제출 뒤** 마스터(Main 설비는 그대로) — 설비 마스터 호기 상세가 넘기는 꼴."""
    after = master.copy()
    after["설비명"] = after["설비명"].map(lambda name: renames.get(name, name))
    return after


def test_check_unit_rename_also_reads_a_master_after_the_submit() -> None:
    """설계 11-2 4단계는 제출 뒤 마스터를 넘긴다(S1 리뷰) — 새 이름이 그 행에 이미 들어 있어도 자기
    행으로 읽어 정상 바꿈을 받고, 겹침은 그대로 막는다."""
    master = _bundle_master()
    assert (
        check_unit_rename("EQ-01", "EQ-101", master=_renamed(master, {"EQ-01": "EQ-101"})) is None
    )
    # 맞바꿈·사슬도 뒤 마스터로 받는다.
    swapped = _renamed(master, {"EQ-01": "EQ-02", "EQ-02": "EQ-01"})
    assert check_unit_rename("EQ-01", "EQ-02", master=swapped, renaming={"EQ-02": "EQ-01"}) is None
    chained = _renamed(master, {"EQ-01": "EQ-02", "EQ-02": "EQ-03"})
    assert check_unit_rename("EQ-01", "EQ-02", master=chained, renaming={"EQ-02": "EQ-03"}) is None
    # 자기 설비명을 Main 설비로 적은 한 행 묶음 — Main 설비가 따라갔든 아니든.
    solo = _master({"설비명": "SOLO", "Main 설비": "SOLO", "X좌표": 70.0, "Y좌표": 40.0})
    followed, _ = rename_followers(
        _renamed(solo, {"SOLO": "SOLO-2"}), _downtime(), {"SOLO": "SOLO-2"}
    )
    assert check_unit_rename("SOLO", "SOLO-2", master=followed) is None
    assert check_unit_rename("SOLO", "SOLO-2", master=_renamed(solo, {"SOLO": "SOLO-2"})) is None


def test_a_master_after_the_submit_still_refuses_clashes() -> None:
    master = _bundle_master()
    # 다른 행도 같은 새 이름(대소문자만 다름 포함)이면 겹친다.
    doubled = _renamed(master, {"EQ-01": "EQ-02"})
    clash = check_unit_rename("EQ-01", "EQ-02", master=doubled)
    assert clash is not None and "이미 있는 설비명입니다(EQ-02)" in clash
    lower = _renamed(master, {"EQ-01": "eq-02"})
    assert "이미 있는 설비명입니다(EQ-02)" in str(check_unit_rename("EQ-01", "eq-02", master=lower))
    # 다른 묶음의 Main 설비 이름과 겹친 새 이름.
    grouped = _renamed(master, {"EQ-01": "BIG"})
    assert "이미 Main 설비 이름입니다(BIG)" in str(
        check_unit_rename("EQ-01", "BIG", master=grouped)
    )


def test_the_space_editor_calls_the_shared_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Space 적용(`parse_editor_apply`)의 설비명 바꿈 판정은 공용 `check_unit_rename` 을 지난다 — 그
    함수에 규칙을 더하면 Space 도 따라간다(S1 리뷰 · 개편 B0)."""
    import capa_simulation.services.space_layout_edit as space_layout_edit

    seen: list[tuple[str, str, dict[str, str]]] = []

    def spy(old: str, new: str, **kwargs: Any) -> str | None:
        seen.append((old, new, dict(kwargs.get("renaming") or {})))
        return "공용 판정이 막았습니다" if new == "BLOCKED" else None

    monkeypatch.setattr(space_layout_edit, "check_unit_rename", spy)
    master = _master()
    _parse(_rename(("unit", "EQ-01", "EQ-101"), ("unit", "EQ-02", "EQ-102")), master)
    assert seen == [
        ("EQ-01", "EQ-101", {"EQ-02": "EQ-102"}),
        ("EQ-02", "EQ-102", {"EQ-01": "EQ-101"}),
    ]
    with pytest.raises(ValueError, match="공용 판정이 막았습니다"):
        _parse(_rename(("unit", "EQ-01", "BLOCKED")), master)


# ------------------------------------------------------------------ compose_unit_renames


def test_compose_unit_renames_chains_back_and_leaves_groups_alone() -> None:
    saved_names = {"EQ-01", "EQ-02"}
    first = compose_unit_renames(
        PendingRenames(groups={"G": "BIG"}), {"EQ-01": "A"}, saved_names=saved_names
    )
    second = compose_unit_renames(first, {"A": "B"}, saved_names=saved_names)
    back = compose_unit_renames(second, {"B": "EQ-01"}, saved_names=saved_names)
    new_unit = compose_unit_renames(PendingRenames(), {"NEW-1": "NEW-2"}, saved_names=saved_names)

    assert first.units == {"A": "EQ-01"} and first.groups == {"G": "BIG"}
    assert second.units == {"B": "EQ-01"}
    assert back.units == {} and back.groups == {"G": "BIG"}
    assert not new_unit


def test_compose_renames_is_compose_unit_renames_plus_the_group_side() -> None:
    saved = _bundle_master()
    from capa_simulation.services.space_layout_edit import EditorApply

    apply = EditorApply(
        changes=(),
        created=(),
        canvas=None,
        marks=None,
        renames=(NameChange("unit", "EQ-01", "A"), NameChange("group", "BIG", "G")),
    )
    composed = compose_renames(PendingRenames(), apply, saved=saved)
    units_only = compose_unit_renames(
        PendingRenames(), {"EQ-01": "A"}, saved_names=set(saved["설비명"])
    )

    assert composed.units == units_only.units == {"A": "EQ-01"}
    assert composed.groups == {"G": "BIG"}


# ------------------------------------------------------------------ rename_followers


def _downtime_two() -> pd.DataFrame:
    first = _downtime()
    return pd.concat(
        [first, first.assign(설비명=["EQ-02"], 비가동유형=["공사"])], ignore_index=True
    )


def test_rename_followers_moves_downtime_names_at_once_for_a_swap() -> None:
    master = _master()
    swapped = master.assign(설비명=master["설비명"].replace({"EQ-01": "EQ-02", "EQ-02": "EQ-01"}))

    _, downtime = rename_followers(swapped, _downtime_two(), {"EQ-01": "EQ-02", "EQ-02": "EQ-01"})

    assert downtime["설비명"].tolist() == ["EQ-02", "EQ-01"]


def test_rename_followers_takes_a_self_named_single_row_group_along() -> None:
    saved = _master({"설비명": "SOLO", "Main 설비": "SOLO", "X좌표": 70.0, "Y좌표": 40.0})
    typed = saved.assign(설비명=saved["설비명"].replace({"SOLO": "SOLO-2"}))

    master, _ = rename_followers(typed, _downtime(), {"SOLO": "SOLO-2"})

    assert master.set_index("설비명").loc["SOLO-2", "Main 설비"] == "SOLO-2"
    # 같은 결과를 Space 의 반영(`apply_name_changes`)도 낸다 — 한 함수를 지난다.
    spaced, _ = apply_name_changes(saved, _downtime(), [NameChange("unit", "SOLO", "SOLO-2")])
    assert spaced["Main 설비"].tolist() == master["Main 설비"].tolist()


def test_rename_followers_leaves_the_cells_the_user_touched_in_the_same_submit() -> None:
    saved = _master({"설비명": "SOLO", "Main 설비": "SOLO", "X좌표": 70.0, "Y좌표": 40.0})
    typed = saved.assign(설비명=saved["설비명"].replace({"SOLO": "SOLO-2", "EQ-01": "EQ-101"}))
    solo_row = typed.index[typed["설비명"].eq("SOLO-2")][0]
    downtime = _downtime_two().assign(설비명=["EQ-01", "EQ-01"])

    master, schedule = rename_followers(
        typed,
        downtime,
        {"SOLO": "SOLO-2", "EQ-01": "EQ-101"},
        touched_parent_rows={solo_row},
        touched_downtime_rows={1},
    )

    assert master.loc[solo_row, "Main 설비"] == "SOLO"
    assert schedule["설비명"].tolist() == ["EQ-101", "EQ-01"]
    # 원본은 그대로다.
    assert downtime["설비명"].tolist() == ["EQ-01", "EQ-01"]


def test_rename_followers_without_renames_returns_the_frames_untouched() -> None:
    master, downtime = _master(), _downtime()

    assert rename_followers(master, downtime, {"EQ-01": "EQ-01"}) == (master, downtime)


# ------------------------------------------------------------------ follow_unit_renames


def _follow_app() -> None:
    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        _apply_followed_filters,
        follow_unit_renames,
    )

    step = st.session_state.get("test_step")
    if step == "rename":
        follow_unit_renames({"EQ-01": "EQ-101"}, {"BIG": "BIG-2"})
        follow_unit_renames({"EQ-101": "EQ-201"}, {})
    elif step == "draw":
        _apply_followed_filters()
    st.session_state["test_step"] = None


MASTER_FILTER = filter_widget_key(MASTER_VIEW_PREFIX, "Main 설비")
DOWNTIME_FILTER = filter_widget_key(DOWNTIME_VIEW_PREFIX, "설비명")


def test_follow_moves_the_selection_the_pending_delete_and_the_list_filters() -> None:
    """선택·삭제 확인 대기의 키와 목록 필터의 고른 값이 새 이름으로 옮겨 가고, 되돌리기 기억은
    버린다. 필터는 그 위젯을 그리기 전에만 고칠 수 있어 다음 그리기에서 얹힌다."""
    app = AppTest.from_function(_follow_app)
    app.session_state[SELECTION_KEY] = {
        EQUIPMENT_TARGET: frozenset({("EQ-01",), ("EQ-02",)}),
        DOWNTIME_TARGET: frozenset({("EQ-01", "고장", "2026-08-10")}),
        BASELINE_TARGET: frozenset({("EQ-01", "양산")}),
    }
    app.session_state[PENDING_DELETE_KEY] = (EQUIPMENT_TARGET, frozenset({("EQ-01",)}))
    app.session_state[LAST_REMOVED_KEY] = ("anything",)
    app.session_state[MASTER_FILTER] = ["BIG", "SMALL"]
    app.session_state[DOWNTIME_FILTER] = ["EQ-01", "EQ-02"]
    app.session_state["test_step"] = "rename"
    app.run()

    assert not app.exception
    assert app.session_state[SELECTION_KEY] == {
        EQUIPMENT_TARGET: frozenset({("EQ-201",), ("EQ-02",)}),
        DOWNTIME_TARGET: frozenset({("EQ-201", "고장", "2026-08-10")}),
        # 기존 보유대수 키의 첫 칸은 공정이다 — 건드리지 않는다.
        BASELINE_TARGET: frozenset({("EQ-01", "양산")}),
    }
    assert app.session_state[PENDING_DELETE_KEY] == (EQUIPMENT_TARGET, frozenset({("EQ-201",)}))
    assert LAST_REMOVED_KEY not in app.session_state
    # 아직 그리기 전 — 필터 값은 그대로다.
    assert app.session_state[DOWNTIME_FILTER] == ["EQ-01", "EQ-02"]

    app.session_state["test_step"] = "draw"
    app.run()

    assert app.session_state[MASTER_FILTER] == ["BIG-2", "SMALL"]
    assert app.session_state[DOWNTIME_FILTER] == ["EQ-201", "EQ-02"]


# ------------------------------------------------------------------ RawData 목록·결과 꼬리


def _workspace_app(path: Path) -> AppTest:
    return AppTest.from_string(
        f"""
from pathlib import Path
from capa_simulation.components.equipment_data_workspace import render_equipment_data_workspace
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
repository = DuckDBEquipmentRepository(Path({str(path)!r}))
repository.initialize()
snapshot = repository.load_snapshot(repository.latest_revision_id())
render_equipment_data_workspace(
    repository=repository, latest_snapshot=snapshot, baseline=snapshot.baseline,
    equipment=snapshot.equipment, downtime=snapshot.downtime,
    floor_canvases={{}}, max_extent=(100.0, 60.0),
)
""",
        default_timeout=30,
    )


def test_rawdata_lists_the_unsaved_renames_made_in_space(tmp_path: Path) -> None:
    from test_equipment_availability import _baseline, _equipment

    from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

    path = tmp_path / "rename.duckdb"
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="r1")
    app = _workspace_app(path).run()
    assert not app.exception
    assert not any(item.label.startswith("이름 바꿈") for item in app.expander)

    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    renamed, followed = apply_name_changes(
        equipment, downtime, [NameChange("unit", "EQ-01", "EQ-101")]
    )
    app.session_state[BUFFER_KEY] = (baseline, renamed, followed)
    app.session_state[PENDING_RENAMES_KEY] = {"units": {"EQ-101": "EQ-01"}, "groups": {}}
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert [item.label for item in app.expander].count("이름 바꿈 1건") == 1
    table = next(frame.value for frame in app.dataframe if "이전 이름" in frame.value.columns)
    assert table.to_dict(orient="records") == [
        {"구분": "설비명", "이전 이름": "EQ-01", "새 이름": "EQ-101"}
    ]
    assert any(NAME_CHANGES_CAPTION in str(item.value) for item in app.caption)


def test_a_save_that_removes_and_adds_units_points_at_the_rename_tool() -> None:
    common = EquipmentRevisionSummary("c3", 3, None, 0, 2, 0, datetime(2026, 10, 25))
    both = save_result_message(
        EquipmentSaveResult(common=common, schedule=None, new_units=("B",), removed_units=("A",)),
        scenario_name="운영 일정",
    )
    removed_only = save_result_message(
        EquipmentSaveResult(common=common, schedule=None, removed_units=("A",)),
        scenario_name="운영 일정",
    )

    assert RENAME_INSTEAD_HINT in both
    assert "다른 설비 시나리오의 그 호기 일정이 빠집니다" in both
    assert RENAME_INSTEAD_HINT not in removed_only
