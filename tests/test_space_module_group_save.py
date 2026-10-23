# Purpose: 마스터 저장이 모듈 묶음 좌표·크기의 바둑판 아닌 편집은 막고 편집기 결과는 받는지 본다.

"""Space 모듈 묶음 좌표·크기는 배치 편집기에서 묶음 범위로만 고친다(2026-10-23 사용자 답 「막자」).

설비 마스터를 쓰는 길은 RawData 직접 편집·붙여넣기·CSV 업로드·일괄 삭제·Space 배치 저장이고 모두
`equipment_data_workspace.save_equipment_buffer` → `_save_equipment_frames` 한 곳을 지난다. 그
자리의 `saved_master_violations`(`space_layout_edit.module_layout_violations`)가 저장본과 견줘 모듈
좌표·크기가 바뀐 묶음은 묶음 범위의 바둑판(한 눈금 허용 — 편집기 적용의 서버 판정과 같다)이어야
저장한다. 안 바뀐 옛 묶음과 Main 설비 칸만 고친 편집(묶음에 넣기·빼기)은 막지 않고, 배치 편집기가
적용한 묶음은 적용 뒤 모양(`module_layouts`)이 그대로면 통과한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_availability import _baseline, _downtime
from test_equipment_data_workspace import _app as _workspace_app
from test_space_layout_edit import CANVAS, FLOOR, _master, _parse
from test_space_layout_editor_page import FAKE_APPLY_KEY, _open_editor
from test_space_module_group import GROUP_ROWS, _ghost_payload, _hidden_inputs, _relaid, _shape

from capa_simulation.components import space_layout_editor
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    CLIPBOARD_KEY,
    EDIT_SAVE_BUTTON_KEY,
    EDITOR_MODULE_LAYOUTS_KEY,
    EQUIPMENT_EDITOR_KEY,
    IMPORT_SAVE_BUTTON_KEY,
    MODULE_LAYOUT_HELP,
    PREVIEW_BUTTON_KEY,
    TARGET_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.space_layout_edit import (
    apply_layout_edits,
    module_layout_message,
    module_layout_violations,
    module_layouts,
    tile_module_group,
)

G1 = ["G1-A", "G1-B", "G1-C", "G1-D"]
# 모듈 셋 묶음 둘 — GRP-5 는 한 줄(3×1) 바둑판, GRP-6 은 1·2차 규칙(셋도 2×2)으로 놓인 옛 묶음.
THREE_ROWS: list[dict[str, Any]] = [
    {"설비명": "G5-A", "Main 설비": "GRP-5", "X좌표": 20.0, "Y좌표": 5.0, "Xsize": 7, "Ysize": 6},
    {"설비명": "G5-B", "Main 설비": "GRP-5", "X좌표": 27.0, "Y좌표": 5.0, "Xsize": 7, "Ysize": 6},
    {"설비명": "G5-C", "Main 설비": "GRP-5", "X좌표": 34.0, "Y좌표": 5.0, "Xsize": 7, "Ysize": 6},
    {"설비명": "G6-A", "Main 설비": "GRP-6", "X좌표": 45.0, "Y좌표": 12.0, "Xsize": 8, "Ysize": 6},
    {"설비명": "G6-B", "Main 설비": "GRP-6", "X좌표": 53.0, "Y좌표": 12.0, "Xsize": 8, "Ysize": 6},
    {"설비명": "G6-C", "Main 설비": "GRP-6", "X좌표": 45.0, "Y좌표": 6.0, "Xsize": 8, "Ysize": 6},
]


def _saved() -> pd.DataFrame:
    return _master(*GROUP_ROWS, *THREE_ROWS)


def _edited(master: pd.DataFrame, cells: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """설비명 → {칸: 값} 을 얹은 사본."""
    out = master.copy()
    for column in ("X좌표", "Y좌표", "Xsize", "Ysize"):
        out[column] = pd.to_numeric(out[column]).astype("float64")
    for name, values in cells.items():
        mask = out["설비명"].eq(name)
        assert mask.any(), name
        for column, value in values.items():
            out.loc[mask, column] = value
    return out


def _shifted(master: pd.DataFrame, names: list[str], dx: float) -> pd.DataFrame:
    xs = pd.to_numeric(master.set_index("설비명")["X좌표"]).astype("float64").to_dict()
    return _edited(master, {name: {"X좌표": float(xs[name]) + dx} for name in names})


# ---------------------------------------------------------------- 판정(순수 함수)


def test_a_single_module_moved_or_resized_is_refused_and_named() -> None:
    saved = _saved()

    assert module_layout_violations(saved, _edited(saved, {"G1-A": {"X좌표": 52.0}})) == ["GRP-1"]
    assert module_layout_violations(saved, _edited(saved, {"G1-B": {"Xsize": 11}})) == ["GRP-1"]
    assert module_layout_violations(saved, _edited(saved, {"G1-D": {"Y좌표": 31.0}})) == ["GRP-1"]


def test_a_whole_group_moved_to_a_tiling_or_a_tick_off_is_saved() -> None:
    """묶음째 옮긴 값은 바둑판 그대로라 받는다. 한 눈금(0.1) 어긋남은 반올림 끝으로 보고 받는다."""
    saved = _saved()

    assert module_layout_violations(saved, _shifted(saved, G1, 5.0)) == []
    assert module_layout_violations(saved, _edited(saved, {"G1-B": {"Xsize": 10.1}})) == []
    regrown = tile_module_group((50.0, 30.0, 24.0, 16.0), G1)
    resized = _edited(
        saved,
        {
            name: {"X좌표": x, "Y좌표": y, "Xsize": w, "Ysize": h}
            for name, (x, y, w, h) in regrown.items()
        },
    )
    assert module_layout_violations(saved, resized) == []


def test_clearing_a_group_is_fine_only_when_every_module_leaves() -> None:
    """묶음째 좌표를 비우면(미배치) 받는다. 일부 모듈만 비우면 — 남은 모듈이 한 줄로 맞아 보여도 —
    좌표를 잃은 모듈이 있어 거부한다."""
    saved = _saved()
    cleared = {"X좌표": None, "Y좌표": None}

    assert module_layout_violations(saved, _edited(saved, dict.fromkeys(G1, cleared))) == []
    assert module_layout_violations(saved, _edited(saved, {"G1-A": cleared})) == ["GRP-1"]
    assert module_layout_violations(
        saved, _edited(saved, dict.fromkeys(["G1-C", "G1-D"], cleared))
    ) == ["GRP-1"]


def test_an_untouched_old_group_never_blocks_another_edit() -> None:
    """바둑판이 아닌 옛 묶음(GRP-2 제각각·GRP-3 한 모듈에만 상자·GRP-6 옛 2×2 셋)은 손대지 않으면
    다른 칸을 고친 저장을 막지 않는다. 손대면 바둑판이어야 한다."""
    saved = _saved()
    other = _edited(saved, {"EQ-01": {"X좌표": 30.0}, "G2-A": {"담당자": "담당B"}})

    assert module_layout_violations(saved, other) == []
    assert module_layout_violations(saved, _edited(saved, {"G2-A": {"X좌표": 4.0}})) == ["GRP-2"]
    rows = saved.set_index("설비명").loc[
        ["G2-A", "G2-B", "G2-C", "G2-D"], ["X좌표", "Y좌표", "Xsize", "Ysize"]
    ]
    old: dict[str, tuple[float, float, float, float] | None] = {
        str(name): (float(x), float(y), float(w), float(h))
        for name, (x, y, w, h) in zip(
            rows.index, rows.astype("float64").to_numpy().tolist(), strict=True
        )
    }
    laid = _relaid(old, (5.0, 30.0, 20.0, 16.0))
    regridded = _edited(
        saved,
        {
            name: {"X좌표": x, "Y좌표": y, "Xsize": w, "Ysize": h}
            for name, (x, y, w, h) in laid.items()
        },
    )
    assert module_layout_violations(saved, regridded) == []


def test_three_modules_are_judged_as_one_row() -> None:
    """모듈 셋은 한 줄 바둑판이다 — 한 줄 묶음을 통째로 옮기면 받고, 옛 2×2 셋 묶음은 손대지 않으면
    그대로 두되 통째로 옮겨도 이제 바둑판이 아니라 거부한다(배치 편집기에서 한 줄로 다시 놓는다)."""
    saved = _saved()
    six = ["G6-A", "G6-B", "G6-C"]

    assert module_layout_violations(saved, _shifted(saved, ["G5-A", "G5-B", "G5-C"], 2.0)) == []
    assert module_layout_violations(saved, _shifted(saved, six, 2.0)) == ["GRP-6"]
    row = tile_module_group((45.0, 6.0, 24.0, 12.0), six)
    lined = _edited(
        saved,
        {
            name: {"X좌표": x, "Y좌표": y, "Xsize": w, "Ysize": h}
            for name, (x, y, w, h) in row.items()
        },
    )
    assert module_layout_violations(saved, lined) == []


def test_a_one_box_group_keeps_its_box_free_and_its_siblings_on_the_tiling() -> None:
    """한 모듈에만 상자를 그린 옛 묶음(GRP-3)의 그 상자를 옮기는 것은 범위를 옮기는 것과 같아 받는다
    — 좌표 없는 형제는 칸 수에 넣지 않는다(배치 편집기가 처음 옮길 때 놓는다). 형제에 좌표를 넣으면
    넣은 모듈들이 바둑판이어야 한다."""
    saved = _saved()

    assert module_layout_violations(saved, _edited(saved, {"G3-A": {"X좌표": 70.0}})) == []
    sibling = {"X좌표": 60.0, "Y좌표": 10.0, "Xsize": 5, "Ysize": 5}
    assert module_layout_violations(saved, _edited(saved, {"G3-B": sibling})) == ["GRP-3"]
    tiled = tile_module_group((75.0, 40.0, 20.0, 12.0), ["G3-A", "G3-B", "G3-C", "G3-D"])
    placed = _edited(
        saved,
        {
            name: {"X좌표": x, "Y좌표": y, "Xsize": w, "Ysize": h}
            for name, (x, y, w, h) in tiled.items()
        },
    )
    assert module_layout_violations(saved, placed) == []


def test_a_new_group_with_coordinates_must_be_a_tiling() -> None:
    """저장본에 없는 묶음(붙여넣은 새 모듈 행)도 좌표·크기가 있으면 바뀐 것이다. 좌표가 없으면
    받는다(배치 편집기 서랍에서 놓는다). 크기만 있는 행도 받는다."""
    saved = _saved()
    module = {"Main 설비": "GRP-9", "Xsize": 6, "Ysize": 6}
    loose = _master(
        *GROUP_ROWS,
        *THREE_ROWS,
        {**module, "설비명": "G9-A", "X좌표": 80.0, "Y좌표": 5.0},
        {**module, "설비명": "G9-B", "X좌표": 87.0, "Y좌표": 5.0},
    )
    tiled = _master(
        *GROUP_ROWS,
        *THREE_ROWS,
        {**module, "설비명": "G9-A", "X좌표": 80.0, "Y좌표": 5.0},
        {**module, "설비명": "G9-B", "X좌표": 86.0, "Y좌표": 5.0},
    )
    bare = _master(
        *GROUP_ROWS,
        *THREE_ROWS,
        {**module, "설비명": "G9-A", "X좌표": None, "Y좌표": None},
        {**module, "설비명": "G9-B", "X좌표": None, "Y좌표": None},
    )

    assert module_layout_violations(saved, loose) == ["GRP-9"]
    assert module_layout_violations(saved, tiled) == []
    assert module_layout_violations(saved, bare) == []


def test_joining_or_leaving_a_group_is_not_a_coordinate_edit() -> None:
    """Main 설비 칸만 고쳐 행을 묶음에 넣거나 빼는 편집은 이번 범위가 아니다 — 그 행의 좌표·크기가
    그대로면 막지 않는다(2026-10-23 사용자 답 뒤 정한 범위)."""
    saved = _saved()

    assert module_layout_violations(saved, _edited(saved, {"EQ-02": {"Main 설비": "GRP-1"}})) == []
    assert module_layout_violations(saved, _edited(saved, {"G1-D": {"Main 설비": None}})) == []


def test_a_renamed_module_is_not_a_changed_module() -> None:
    """RawData 에서 모듈 설비명만 바꾼 행(저장본에서 사라진 행과 값이 같음)과 Space 에서 바꾼 저장
    안 한 이름(`renames` — 지금 이름 → 저장본 이름)은 좌표·크기를 바꾼 것이 아니다."""
    saved = _saved()
    renamed = _edited(saved, {"G2-A": {"설비명": "G2-A2"}})

    assert module_layout_violations(saved, renamed) == []
    assert module_layout_violations(saved, renamed, renames={"G2-A2": "G2-A"}) == []
    moved = _edited(renamed, {"G2-A2": {"X좌표": 4.0}})
    assert module_layout_violations(saved, moved, renames={"G2-A2": "G2-A"}) == ["GRP-2"]


def test_an_editor_result_passes_as_applied_and_a_later_rawdata_edit_does_not() -> None:
    """배치 편집기가 적용한 묶음은 적용 뒤 모양(`module_layouts`)이 그대로면 통과한다 — 숨은 모듈이
    있는 묶음을 다른 층으로 보내면 숨은 모듈의 좌표가 비고 남은 모듈은 넷짜리 바둑판 칸에 서서
    RawData 규칙으로는 바둑판이 아니지만 편집기 결과다. 그 뒤 RawData 로 고치면 다시 막힌다."""
    master, after = _hidden_inputs(date(2026, 10, 1))
    laid = _relaid(_shape(after), (51.0, 30.0, 24.0, 16.0))
    visible = [name for name in G1 if name != "G1-B"]
    applied = _parse(
        {
            "changes": [
                {
                    "id": name,
                    "placed": True,
                    "x": laid[name][0],
                    "y": laid[name][1],
                    "w": laid[name][2],
                    "h": laid[name][3],
                    "moveTo": "C2 2F",
                }
                for name in visible
            ],
            "ghosts": [],
        },
        master,
        editor_items=after.items,
        editor_ghosts=after.ghosts,
    )
    sent = apply_layout_edits(master, applied, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    approved = module_layouts(sent, {"GRP-1"})

    assert module_layout_violations(master, sent) == ["GRP-1"]
    assert module_layout_violations(master, sent, approved=approved) == []
    later = _edited(sent, {"G1-A": {"X좌표": 52.0}})
    assert module_layout_violations(master, later, approved=approved) == ["GRP-1"]
    # 편집기가 옮긴 묶음(숨은 모듈도 함께)은 승인 없이도 바둑판이라 같은 결과다(이중 검사).
    moved = _parse(
        _ghost_payload(after, laid), master, editor_items=after.items, editor_ghosts=after.ghosts
    )
    result = apply_layout_edits(master, moved, floor=FLOOR, canvases={}, default_canvas=CANVAS)
    assert module_layout_violations(master, result) == []


def test_the_message_names_the_groups_and_the_way_out() -> None:
    one = module_layout_message(["GRP-1"])
    assert one.startswith(
        "Main 설비 GRP-1 의 모듈 좌표·크기는 Space 배치 편집기에서 묶음 범위로 고칩니다"
    )
    assert "`배치 편집`" in one and "저장본대로 되돌리거나" in one
    assert "GRP-1, GRP-2, GRP-3 외 2개" in module_layout_message(
        ["GRP-1", "GRP-2", "GRP-3", "GRP-4", "GRP-5"]
    )


# ---------------------------------------------------------------- 저장 경로(AppTest)


def _seed(path: Path, master: pd.DataFrame) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    repository.save_snapshot(_baseline(), master, _downtime(), note="r1")
    return repository


def _edit_rawdata(app: AppTest, master: pd.DataFrame) -> None:
    """RawData 편집표에서 고친 것처럼 편집본 설비 마스터를 갈고 다시 그린다. 편집표가 쥔 옛 보기
    (`{key}_applied_view`)도 버린다 — `replace_equipment_buffer` 처럼(남기면 다음 제출이 옛 값으로
    되돌린다)."""
    baseline, _, downtime = app.session_state[BUFFER_KEY]
    app.session_state[BUFFER_KEY] = (baseline, master, downtime)
    view = f"{EQUIPMENT_EDITOR_KEY}_applied_view"
    if view in app.session_state:
        del app.session_state[view]
    app.run()


def test_the_rawdata_save_refuses_a_module_edit_and_takes_a_whole_group_move(
    tmp_path: Path,
) -> None:
    """RawData 직접 편집 저장: 모듈 하나를 옮긴 편집본은 저장 전 경고와 저장 거부(어느 묶음인지)로
    막히고 리비전이 생기지 않는다 — 거부된 회차는 그 문구를 오류 하나로만 보이고 다음 회차에 경고가
    돌아온다. 묶음째 옮긴 편집본은 저장된다. 편집표 위에 안내 한 줄이 늘 선다."""
    path = tmp_path / "equipment.duckdb"
    repository = _seed(path, _saved())
    app = _workspace_app(path)
    assert any(MODULE_LAYOUT_HELP in item.value for item in app.caption)
    equipment = app.session_state[BUFFER_KEY][1]
    _edit_rawdata(app, _edited(equipment, {"G1-A": {"X좌표": 52.0}}))

    message = module_layout_message(["GRP-1"])
    assert any(message == item.value for item in app.warning), [w.value for w in app.warning]
    app.button(EDIT_SAVE_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert any(message in str(item.value) for item in app.error), [e.value for e in app.error]
    assert len(repository.list_revisions()) == 1
    # 거부된 회차는 같은 긴 문구를 빨간 오류 하나로만 보인다 — 주황 경고를 거듭 세우지 않는다.
    shown = [item.value for item in (*app.error, *app.warning)]
    assert sum(message in str(value) for value in shown) == 1, shown
    # 다음 회차에는 오류가 사라지고 저장 전 경고가 남는다(편집본은 아직 바둑판이 아니다).
    app.run()
    assert not any(message in str(item.value) for item in app.error), [e.value for e in app.error]
    assert [item.value for item in app.warning].count(message) == 1, [w.value for w in app.warning]

    equipment = app.session_state[BUFFER_KEY][1]
    assert equipment.set_index("설비명").loc["G1-A", "X좌표"] == 52.0
    fixed = _edited(equipment, {"G1-A": {"X좌표": 50.0}})
    _edit_rawdata(app, _shifted(fixed, G1, 5.0))
    assert not any(message == item.value for item in app.warning)
    app.button(EDIT_SAVE_BUTTON_KEY).click().run()

    assert not app.exception and not app.error, [e.value for e in app.error]
    assert len(repository.list_revisions()) == 2
    saved = repository.load_snapshot(str(repository.latest_revision_id())).equipment
    assert saved.set_index("설비명").loc[G1, "X좌표"].tolist() == [55.0, 65.0, 55.0, 65.0]


def test_a_paste_that_moves_one_module_is_flagged_in_review_and_refused_on_save(
    tmp_path: Path,
) -> None:
    """붙여넣기(설비명과 바꿀 열만): 미리보기에서 저장이 막힌다고 알리고, 「확인 후 리비전 저장」은
    거부한다. 안 바뀐 옛 묶음만 있는 붙여넣기는 저장된다."""
    path = tmp_path / "equipment.duckdb"
    repository = _seed(path, _saved())
    app = _workspace_app(path)
    app.selectbox(TARGET_KEY).set_value("설비 마스터")
    app.text_area(CLIPBOARD_KEY).set_value("설비명\tX좌표\nG1-B\t61\n")
    app.button(PREVIEW_BUTTON_KEY).click().run()

    message = module_layout_message(["GRP-1"])
    assert not app.exception and not app.error, [e.value for e in app.error]
    assert any(message == item.value for item in app.warning)
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()

    assert any(message in str(item.value) for item in app.error)
    assert len(repository.list_revisions()) == 1

    app.text_area(CLIPBOARD_KEY).set_value("설비명\t담당자\nG2-A\t담당B\n")
    app.button(PREVIEW_BUTTON_KEY).click().run()
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()

    assert not app.exception and not app.error, [e.value for e in app.error]
    assert len(repository.list_revisions()) == 2


@pytest.fixture
def editor_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """배치 편집기 대역 — `test_space_layout_editor_page` 와 같다(받은 data 를 적고 세션의 적용값을
    돌려준다)."""
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> SimpleNamespace:
        import streamlit as st

        calls.append(kwargs["data"])
        return SimpleNamespace(apply=st.session_state.pop(FAKE_APPLY_KEY, None))

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def test_the_space_save_takes_an_editor_result_even_where_the_rawdata_rule_would_not(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """Space 배치 저장: 숨은 모듈(레이아웃표시 N)이 있는 묶음을 다른 층으로 보낸 적용은 숨은 모듈의
    좌표가 비어 RawData 규칙으로는 바둑판이 아니지만 편집기 결과(적용 뒤 모양)라 저장된다."""
    module = {"Main 설비": "GRP-1", "Xsize": 10, "Ysize": 7}
    master = _master(
        {**module, "설비명": "G1-A", "X좌표": 50.0, "Y좌표": 37.0},
        {**module, "설비명": "G1-B", "X좌표": 60.0, "Y좌표": 37.0, "레이아웃표시": "N"},
        {**module, "설비명": "G1-C", "X좌표": 50.0, "Y좌표": 30.0},
        {**module, "설비명": "G1-D", "X좌표": 60.0, "Y좌표": 30.0},
    )
    app, database = _open_editor(tmp_path, master)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [
            {"id": "G1-A", "placed": True, "x": 50, "y": 37, "w": 10, "h": 7, "moveTo": "C2 2F"},
            {"id": "G1-C", "placed": True, "x": 50, "y": 30, "w": 10, "h": 7, "moveTo": "C2 2F"},
            {"id": "G1-D", "placed": True, "x": 60, "y": 30, "w": 10, "h": 7, "moveTo": "C2 2F"},
        ],
        "ghosts": [],
        "canvas": None,
        "marks": None,
    }
    app.run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    assert "GRP-1" in app.session_state[EDITOR_MODULE_LAYOUTS_KEY]
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 2
    rows = repository.load_snapshot(str(repository.latest_revision_id())).equipment
    rows = rows.set_index("설비명").loc[G1]
    assert set(rows["층"]) == {"2F"} and pd.isna(rows.loc["G1-B", "X좌표"])
    assert EDITOR_MODULE_LAYOUTS_KEY not in app.session_state
    clear_equipment_repository()


def test_the_space_save_refuses_a_rawdata_module_edit_left_in_the_draft(
    tmp_path: Path, editor_calls: list[dict[str, Any]]
) -> None:
    """Space 배치 저장도 편집본 전체를 저장하므로 RawData 에서 모듈 하나만 옮긴 저장 안 한 편집이
    남아 있으면 같은 문구로 거부한다. 배치 편집기에서 그 묶음을 옮겨 다시 놓으면 저장된다."""
    app, database = _open_editor(tmp_path, _saved())
    _edit_rawdata(app, _edited(app.session_state[BUFFER_KEY][1], {"G1-A": {"X좌표": 52.0}}))
    app.button(key="space_layout_save").click().run()

    message = module_layout_message(["GRP-1"])
    assert not app.exception, [item.message for item in app.exception]
    assert any(message in str(item.value) for item in app.error), [e.value for e in app.error]
    repository = DuckDBEquipmentRepository(database)
    assert len(repository.list_revisions()) == 1

    tiles = tile_module_group((52.0, 30.0, 20.0, 14.0), G1)
    app.session_state[FAKE_APPLY_KEY] = {
        "epoch": editor_calls[-1]["epoch"],
        "changes": [
            {"id": name, "placed": True, "x": x, "y": y, "w": w, "h": h}
            for name, (x, y, w, h) in tiles.items()
        ],
        "canvas": None,
        "marks": None,
    }
    app.run()
    assert not app.error, [item.value for item in app.error]
    app.button(key="space_layout_save").click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [item.value for item in app.error]
    assert len(repository.list_revisions()) == 2
    clear_equipment_repository()
