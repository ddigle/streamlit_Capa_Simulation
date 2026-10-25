# Purpose: 설비 마스터 탭 배치 칸 역할·다른 시나리오 호기 삭제 확인·공식 판정 대체 규칙을 본다.

"""설비 시나리오 2단계 — 설비 마스터 탭(개편 전 RawData) 쪽 셋.

- **배치 칸은 Space 와 같은 판정이다**(S3 — 설계 8-4·10장 `space_edit_mode(...).layout`). 공식 설비
  시나리오에서는 공식 배치(공통 대장), 가정에서는 그 시나리오의 배치 차이(공식은 바뀌지 않는다 —
  새 호기는 공통에 자리 없이, Q1), 잠긴 회차(`locked`)에서는 S1·S2 임시 잠금처럼 있던 호기 배치 칸
  고침을 저장본 값으로 되돌리고 새 호기를 자리 없이 맞춘다. 칸을 `disabled` 로 두지 않는다. 「있던
  호기」 는 저장하면 저장본 호기 키를 잇는 행이고 견주는 값은 **저장본**이다(S1 리뷰). 배치 칸을
  고친 제출은 그때의 역할을 찍는다. 붙여넣기는 가정 세션에서 「배치 칸도 붙여넣기」(기본 끔, Q2).
- **다른 설비 시나리오에 일정이 있는 호기를 지우는 저장은 확인 체크 뒤에**(11-2 6단계). 호기 목록은
  공통 하나라 지우면 그 시나리오들의 일정도 빠진다. 체크는 본 글(호기·그 일정이 든 시나리오)에
  묶이고, 체크가 없는 Space 「배치 저장」·사이드바 팝업 저장도 같은 판정으로 막힌다.
- **공식 판정 대체 규칙**(검토 L13) — 발행이 없을 때 화면도 저장소처럼 「운영 일정」 → 목록 첫
  시나리오로 본다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from streamlit.proto.Dataframe_pb2 import Dataframe as DataframeProto
from streamlit.testing.v1 import AppTest
from test_equipment_scenario_repository import _clone, _seeded, _session, _with_unit
from widget_browser import BrowserTables

from capa_simulation.components.equipment_data_workspace import (
    BUFFER_GENERATION_KEY,
    BUFFER_KEY,
    CLIPBOARD_KEY,
    EDIT_SAVE_BUTTON_KEY,
    EQUIPMENT_EDITOR_KEY,
    FLASH_KEY,
    LAYOUT_ROLE_KEY,
    PASTE_LAYOUT_KEY,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    REMOVAL_CONFIRM_KEY,
    TARGET_KEY,
    VIEW_APPLY_BUTTON_KEY,
    ImportReview,
    LayoutLock,
    RemovalElsewhere,
    layout_edits,
    layout_paste_refusal,
)
from capa_simulation.equipment_scenario_activation import EquipmentSession, _default_selection
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_equipment_scenario_cache,
)
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentRelease,
    EquipmentScenarioCatalog,
    EquipmentScenarioSummary,
)
from capa_simulation.services.space_layout_edit import (
    PLACE_COLUMNS,
    restore_saved_layout,
    saved_layout_drift,
)

OPERATIONS = "operations"


@pytest.fixture(autouse=True)
def _fresh_caches() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


# 잠긴 회차의 까닭(시험용 — 화면은 `space_edit_mode` 의 글을 넘긴다).
LOCK_REASON = "시험 잠금"


def _workspace(path: Path, scenario_id: str, *, layout_mode: str | None = None) -> AppTest:
    """세션 설비 시나리오 `scenario_id` 의 최신을 보는 RawData — 페이지와 같은 저장 출발점.
    `layout_mode` 를 주면 배치 칸 판정을 그것으로(없으면 basis 의 역할)."""
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
    layout_mode={layout_mode!r}, layout_lock_reason={LOCK_REASON!r},
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


# ------------------------------------------------------------------ 배치 칸 — 가정·공식·잠금


def _scenario(repository: DuckDBEquipmentRepository, scenario_id: str) -> Any:
    return next(
        item
        for item in repository.list_equipment_scenarios()
        if item.equipment_scenario_id == scenario_id
    )


def test_an_assumption_keeps_layout_edits_as_its_own_and_stamps_the_role(
    tmp_path: Path,
) -> None:
    """가정 세션의 배치 칸 고침은 편집본에 그대로 들어가고(S3 — 임시 잠금을 걷었다) 그때의 역할
    "overlay" 를 찍는다. 저장하면 그 시나리오 새 리비전의 배치 차이가 되고 공식은 그대로다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    assert any("가정 설비 시나리오 — 배치 칸 고침은" in text for text in _texts(app, "caption"))
    tables = BrowserTables(app)
    key = _editor_key(app)
    tables.edit(key, 0, "X좌표", 50.0)
    tables.edit(key, 0, "설비이력", "고치는 중")
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    assert _buffer_value(app, "EQ-01", "X좌표") == 50.0
    assert _buffer_value(app, "EQ-01", "설비이력") == "고치는 중"
    assert app.session_state[LAYOUT_ROLE_KEY] == "overlay"
    assert not app.error

    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(app.run())
    scenario = _scenario(repository, setup)
    assert scenario.latest_revision_no == 2 and scenario.latest_layout_unit_count == 1
    assert _official(repository, "EQ-01", "X좌표") == 10
    flash = str(app.session_state[FLASH_KEY])
    assert "「셋업 실무」의 가정 배치를 저장했습니다(공식과 다른 호기 1대)" in flash
    assert "Space 현황은 고른 설비 시나리오의 배치입니다" in flash


def test_a_locked_layout_reverts_layout_edits_of_saved_units_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    _, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup, layout_mode="locked").run())
    assert any("배치 편집이 잠겨 있어" in text for text in _texts(app, "caption"))
    tables = BrowserTables(app)
    key = _editor_key(app)
    tables.edit(key, 0, "X좌표", 50.0)
    tables.edit(key, 0, "설비이력", "고치는 중")
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    assert _buffer_value(app, "EQ-01", "X좌표") == 10
    assert _buffer_value(app, "EQ-01", "설비이력") == "고치는 중"
    errors = _texts(app, "error")
    assert any(
        "배치 편집이 잠겨 있어 있던 호기 1대(EQ-01)의 배치 칸 고침은 저장본 값으로 되돌리고 "
        "나머지 편집은 편집본에 반영했습니다"
        in text
        and LOCK_REASON in text
        for text in errors
    )
    # 보기 적용이라 「저장·미리보기를 하지 않았다」 는 말은 없다.
    assert not any("저장·미리보기는 하지 않았습니다" in text for text in errors)
    assert LAYOUT_ROLE_KEY not in app.session_state


def test_a_locked_save_with_a_layout_edit_saves_nothing(tmp_path: Path) -> None:
    repository, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup, layout_mode="locked").run())
    tables = BrowserTables(app)
    tables.edit(_editor_key(app), 1, "층", "2F")
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(tables.run())

    assert len(repository.list_revisions()) == 1
    assert _buffer_value(app, "EQ-02", "층") == "1F"
    assert any(
        "있던 호기 1대(EQ-02)" in text and "이번에 누른 저장·미리보기는 하지 않았습니다" in text
        for text in _texts(app, "error")
    )


def test_a_new_unit_in_an_assumption_keeps_its_place_only_there(tmp_path: Path) -> None:
    """가정 세션에서 넣은 새 호기의 자리는 그 시나리오의 배치 차이다(Q1) — 공통(공식)에는 자리 없이
    들어가고, 그 시나리오는 배치 차이가 있어 공식으로 발행되지 않는다(Q4)."""
    from capa_simulation.persistence.equipment_repository import EquipmentLayoutPublishBlocked

    repository, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    _store(app, (baseline, _with_unit(equipment, "EQ-NEW", 70.0), downtime))
    _ok(app.run())
    tables = BrowserTables(app)
    tables.edit(_editor_key(app), 2, "X좌표", 80.0)
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(tables.run())

    assert not app.error
    scenario = _scenario(repository, setup)
    assert scenario.latest_revision_no == 2 and scenario.latest_layout_unit_count == 1
    official = repository.load_official_snapshot()
    assert official is not None
    official_new = official.equipment.loc[official.equipment["설비명"].eq("EQ-NEW")]
    assert official_new[["동", "X좌표"]].isna().all().all()
    mine = _session(repository, setup).equipment.set_index("설비명")
    assert mine.loc["EQ-NEW", "X좌표"] == 80.0
    release = repository.latest_equipment_release()
    assert release is not None and scenario.latest_schedule_revision_id is not None
    with pytest.raises(EquipmentLayoutPublishBlocked):
        repository.publish_equipment_release(
            scenario.latest_schedule_revision_id,
            released_by=None,
            note=None,
            expected_latest_release_no=release.release_no,
        )


def test_the_official_scenario_edits_layout_cells_as_before(tmp_path: Path) -> None:
    _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", OPERATIONS).run())
    assert not any("배치 편집이 잠겨" in text for text in _texts(app, "caption"))
    assert not any("가정 설비 시나리오 —" in text for text in _texts(app, "caption"))
    tables = BrowserTables(app)
    tables.edit(_editor_key(app), 0, "X좌표", 50.0)
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    assert _buffer_value(app, "EQ-01", "X좌표") == 50.0
    assert app.session_state[LAYOUT_ROLE_KEY] == "official"
    assert not app.error


def test_an_assumption_paste_keeps_saved_layout_unless_asked(tmp_path: Path) -> None:
    """가정 세션 붙여넣기 「배치 칸도 붙여넣기」 는 기본 끔이다(Q2) — 있던 호기의 배치 칸은 지금
    값을 두고 알린다. 켜면 그 시나리오의 가정 배치가 바뀐다고 경고하고 받는다."""
    _, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    assert not app.checkbox(key=PASTE_LAYOUT_KEY).value
    app.selectbox(TARGET_KEY).set_value("설비 마스터")
    app.text_area(CLIPBOARD_KEY).set_value("설비명\tX좌표\nEQ-01\t55")
    app.button(PREVIEW_BUTTON_KEY).click()
    _ok(app.run())

    review = app.session_state[PREVIEW_KEY]
    assert isinstance(review, ImportReview)
    assert review.candidate[1].set_index("설비명").loc["EQ-01", "X좌표"] == 10
    assert any("배치 칸은 붙여넣지 않고 지금 값을 두었습니다" in text for text in review.notices)

    app.checkbox(key=PASTE_LAYOUT_KEY).check()
    app.button(PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    review = app.session_state[PREVIEW_KEY]
    assert review.candidate[1].set_index("설비명").loc["EQ-01", "X좌표"] == 55
    assert any("가정 배치 1대(EQ-01)가 바뀝니다" in text for text in review.cautions)


def test_an_official_paste_warns_it_moves_the_official_layout(tmp_path: Path) -> None:
    _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", OPERATIONS).run())
    app.selectbox(TARGET_KEY).set_value("설비 마스터")
    app.text_area(CLIPBOARD_KEY).set_value("설비명\tX좌표\nEQ-01\t55")
    app.button(PREVIEW_BUTTON_KEY).click()
    _ok(app.run())

    review = app.session_state[PREVIEW_KEY]
    assert review.candidate[1].set_index("설비명").loc["EQ-01", "X좌표"] == 55
    assert any("공식 배치 1칸(호기 1대 — EQ-01)이 바뀝니다" in text for text in review.cautions)


def test_a_locked_paste_that_moves_a_saved_unit_is_refused_before_preview(
    tmp_path: Path,
) -> None:
    _, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup, layout_mode="locked").run())
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


def _row_of(app: AppTest, name: str) -> pd.DataFrame:
    equipment: pd.DataFrame = app.session_state[BUFFER_KEY][1]
    return equipment.loc[equipment["설비명"].eq(name)].reset_index(drop=True)


def _official(repository: DuckDBEquipmentRepository, name: str, column: str) -> Any:
    """공식 설비 시나리오(「운영 일정」 최신 + 공통 최신)가 보는 그 호기 칸."""
    return _session(repository).equipment.set_index("설비명").loc[name, column]


def test_a_removed_unit_pasted_back_with_a_moved_layout_is_refused_when_locked(
    tmp_path: Path,
) -> None:
    """앞 제출에서 지운 저장본 호기를 같은 설비명 한 줄 전체로 다시 붙여넣으면 저장할 때 그 호기
    키를 잇는다 — 잠긴 회차에는 제출 전 편집본에 없던 이름이어도 막는다(S1 리뷰 재현)."""
    repository, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup, layout_mode="locked").run())
    row = _row_of(app, "EQ-01").assign(X좌표=55.0)
    _without(app, "EQ-01")
    _ok(app.run())
    app.selectbox(TARGET_KEY).set_value("설비 마스터")
    app.text_area(CLIPBOARD_KEY).set_value(
        row.to_csv(sep="\t", index=False, date_format="%Y-%m-%d")
    )
    app.button(PREVIEW_BUTTON_KEY).click()
    _ok(app.run())

    assert PREVIEW_KEY not in app.session_state
    assert any(
        "붙여넣기가 있던 호기 1대(EQ-01)의 배치 칸을 바꿉니다" in text
        for text in _texts(app, "error")
    )
    assert len(repository.list_revisions()) == 1
    assert _official(repository, "EQ-01", "X좌표") == 10


def test_a_row_added_back_under_a_removed_name_gets_the_saved_layout_when_locked(
    tmp_path: Path,
) -> None:
    """지운 호기를 편집표 「+」 로 같은 설비명 다시 넣고 배치를 적어 저장을 눌러도, 잠긴 회차에는
    같은 호기라 배치 일곱 칸을 저장본 값으로 되돌리고 그 회차 저장은 하지 않는다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup, layout_mode="locked").run())
    _without(app, "EQ-01")
    _ok(app.run())
    tables = BrowserTables(app)
    tables.add(_editor_key(app), {"설비명": "EQ-01", "공정소분류": "Process-A", "X좌표": 77.0})
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(tables.run())

    assert len(repository.list_revisions()) == 1
    assert _buffer_value(app, "EQ-01", "X좌표") == 10
    assert _buffer_value(app, "EQ-01", "층") == "1F"
    assert any(
        "있던 호기 1대(EQ-01)" in text and "이번에 누른 저장·미리보기는 하지 않았습니다" in text
        for text in _texts(app, "error")
    )
    assert _official(repository, "EQ-01", "X좌표") == 10


def test_an_assumption_layout_save_never_moves_the_official_unit(tmp_path: Path) -> None:
    """가정 세션에서 지운 호기를 같은 이름으로 다시 넣고 배치를 옮겨 저장해도 같은 호기(저장본 키)라
    그 시나리오의 배치 차이로 가고 공식 X좌표는 그대로다(S1 리뷰가 막던 「공식으로 샘」 을 S3 는
    역할 저장으로 막는다)."""
    repository, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    baseline, equipment, downtime = app.session_state[BUFFER_KEY]
    kept = equipment.loc[equipment["설비명"].ne("EQ-01")].reset_index(drop=True)
    readded = _with_unit(kept, "EQ-01", 77.0)
    _store(app, (baseline, readded, downtime))
    _ok(app.run())
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(app.run())

    assert not app.error, _texts(app, "error")
    assert _official(repository, "EQ-01", "X좌표") == 10
    assert _session(repository, setup).equipment.set_index("설비명").loc["EQ-01", "X좌표"] == 77.0


def _master_editor(app: AppTest) -> Any:
    """설비 마스터 편집표 proto(칸 설정 JSON·편집 꼴)."""
    stack = list(app.main.children.values())
    while stack:
        node = stack.pop()
        stack.extend(getattr(node, "children", {}).values())
        proto = getattr(node, "proto", None)
        if getattr(node, "type", None) != "dataframe" or proto is None:
            continue
        if "Qual일정" in json.loads(proto.columns or "{}"):
            return proto
    raise AssertionError("설비 마스터 편집표가 없습니다")


def test_layout_cells_stay_open_and_carry_the_layout_help(tmp_path: Path) -> None:
    """배치 칸은 `disabled` 로 두지 않는다(검토 F12 — 레이아웃표시는 기본값 없는 필수 고르기 칸이라
    잠그면 새 호기 행을 넣을 수 없다). 칸 도움말은 셋째 묶음 「배치」 다(설계 10장)."""
    _, setup = _two_scenarios(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    proto = _master_editor(app)
    columns = json.loads(proto.columns)
    assert not any(columns.get(column, {}).get("disabled") for column in PLACE_COLUMNS)
    assert proto.editing_mode == DataframeProto.EditingMode.DYNAMIC
    assert all(
        str(columns.get(column, {}).get("help", "")).startswith("배치 — ")
        for column in PLACE_COLUMNS
    )

    tables = BrowserTables(app)
    tables.add(
        _editor_key(app),
        {
            "설비명": "EQ-NEW",
            "공정소분류": "Process-A",
            "동": "C1",
            "층": "2F",
            "X좌표": 80.0,
            "Y좌표": 5.0,
            "Xsize": 12.0,
            "Ysize": 6.0,
            "레이아웃표시": "Y",
        },
    )
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    row = _row_of(app, "EQ-NEW").iloc[0]
    assert (row["X좌표"], row["층"]) == (80.0, "2F")
    assert (row["Xsize"], row["Ysize"], row["레이아웃표시"]) == (12.0, 6.0, "Y")
    assert not app.error


def test_the_locked_paste_check_takes_new_units_and_unchanged_layout_cells(
    tmp_path: Path,
) -> None:
    repository = _seeded(tmp_path)
    current = _session(repository)
    saved = current.equipment
    frames = (current.baseline, current.equipment, current.downtime)

    def review(master: pd.DataFrame) -> ImportReview:
        candidate = (current.baseline, master, current.downtime)
        return ImportReview("설비 마스터", "붙여넣기", frames, candidate, pd.DataFrame())

    def refusal(master: pd.DataFrame, renames: dict[str, str] | None = None) -> str | None:
        return layout_paste_refusal(
            review(master), saved=saved, renames=renames or {}, reason=LOCK_REASON
        )

    unplaced = {"동": None, "층": None, "X좌표": None, "Y좌표": None}
    assert refusal(_with_unit(current.equipment, "EQ-NEW", 70.0, **unplaced)) is None
    placed = refusal(_with_unit(current.equipment, "EQ-NEW", 70.0, 층="2F"))
    assert placed is not None
    assert "붙여넣기가 새 호기 1대(EQ-NEW)에 자리(동·층·X좌표·Y좌표)를 넣습니다" in placed
    assert refusal(current.equipment.copy()) is None
    shown = refusal(current.equipment.assign(레이아웃표시=["N", "Y"]))
    assert shown is not None and "있던 호기 1대(EQ-01)" in shown
    # 저장본 이름 그대로 들어온 행은 지운 뒤 다시 넣은 것이어도 같은 호기다(저장하면 그 키를
    # 잇는다).
    readded = _with_unit(
        current.equipment.loc[current.equipment["설비명"].ne("EQ-01")], "EQ-01", 55.0
    )
    moved = refusal(readded)
    assert moved is not None and "있던 호기 1대(EQ-01)" in moved
    # 저장 안 한 이름 바꿈(지금 이름 → 저장본 이름)을 이은 행은 그 저장본 호기와 견준다.
    renamed = current.equipment.assign(설비명=["EQ-101", "EQ-02"])
    assert refusal(renamed, {"EQ-101": "EQ-01"}) is None
    renamed.loc[0, "Y좌표"] = 33.0
    assert "있던 호기 1대(EQ-101)" in str(refusal(renamed, {"EQ-101": "EQ-01"}))
    # 다른 표의 붙여넣기는 보지 않는다.
    downtime = ImportReview("비가동 일정", "붙여넣기", frames, frames, pd.DataFrame())
    assert layout_paste_refusal(downtime, saved=saved, renames={}, reason=None) is None


def test_the_lock_aligns_new_modules_and_undecided_units_to_their_groups_official_floor() -> None:
    """있는 묶음에 드는 새 모듈과 묶음에 넣은 공식 미정 호기는 비우지 않고 그 묶음의 공식 동·층에
    X·Y 를 비운다 — 모듈 행 동·층이 같아야 검증을 지나고 저장이 공통에 쓰는 자리와 같다(배치 차이
    없음). 공식 미정 호기의 동·층 고침은 저장본 값으로 되돌리지 않는다."""
    from test_equipment_availability import _equipment

    saved = _equipment()
    saved["Main 설비"] = "APW1"
    saved = _with_unit(saved, "EQ-U", 70.0, **{"Main 설비": None, "동": None, "층": None})
    saved.loc[saved["설비명"].eq("EQ-U"), ["X좌표", "Y좌표"]] = None
    buffer = _with_unit(saved, "EQ-03", 50.0, **{"Main 설비": "APW1", "동": None, "층": None})
    undecided = buffer.index[buffer["설비명"].eq("EQ-U")][0]
    buffer.at[undecided, "Main 설비"] = "APW1"
    buffer.at[undecided, "동"] = "C1"
    buffer.at[undecided, "층"] = "1F"
    buffer.at[undecided, "X좌표"] = 90.0

    lock = layout_edits(buffer, saved, {})

    assert dict(lock.restore) == {}
    assert set(lock.place) == {"EQ-03", "EQ-U"}
    fixed = lock.apply(buffer, saved)
    rows = fixed.loc[fixed["설비명"].isin(["EQ-03", "EQ-U"])]
    assert rows[["동", "층"]].drop_duplicates().to_numpy().tolist() == [["C1", "1F"]]
    assert rows[["X좌표", "Y좌표"]].isna().all().all()
    assert not layout_edits(lock.apply(buffer, saved), saved, {})
    assert not LayoutLock(restore={}, place={})


def test_layout_drift_is_read_against_the_saved_unit_and_restores_its_cells() -> None:
    from test_equipment_availability import _equipment

    saved = _equipment()
    buffer = saved.assign(설비이력=["a", "b"])
    buffer.loc[1, "Xsize"] = 20
    buffer.loc[0, "동"] = "C2"
    origins = {"EQ-01": "EQ-01", "EQ-02": "EQ-02"}

    drift = saved_layout_drift(saved, buffer, origins)
    restored = restore_saved_layout(buffer, saved, {name: origins[name] for name in drift})

    assert drift == ["EQ-01", "EQ-02"]
    # 새 호기(`origins` 밖)는 보지 않는다.
    assert saved_layout_drift(saved, buffer, {"EQ-02": "EQ-02"}) == ["EQ-02"]
    assert restored["동"].tolist() == ["C1", "C1"] and restored["Xsize"].tolist() == [12, 12]
    assert restored["설비이력"].tolist() == ["a", "b"]
    # 이름을 바꾼 행은 저장본 옛 이름 행의 값으로 되돌린다.
    renamed = buffer.assign(설비명=["EQ-101", "EQ-02"])
    back = restore_saved_layout(renamed, saved, {"EQ-101": "EQ-01"})
    assert back.loc[0, "동"] == "C1" and back.loc[1, "Xsize"] == 20


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
        "저장하려면 가용설비 현황 설비 마스터 탭 저장 칸의" in text for text in _texts(app, "error")
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


def test_the_removal_check_is_for_the_scenarios_its_words_named(tmp_path: Path) -> None:
    """체크를 켠 뒤 남이 그 호기 일정이 든 시나리오를 하나 더 만들면(복제) 경고·체크 글이 「2개」 로
    바뀐다 — 켜 둔 체크로 본 적 없는 글의 저장이 가지 않게 새 칸(풀림)으로 서고 저장을 거부한다(S1
    리뷰: 고치기 전에는 key 꼬리가 호기 이름만이라 체크가 남아 두 시나리오에서 일정이 빠졌다)."""
    repository, _ = _two_scenarios(tmp_path)
    path = tmp_path / "equipment.duckdb"
    app = _ok(_workspace(path, OPERATIONS).run())
    _without(app, "EQ-02")
    _ok(app.run())
    box = _removal_box(app)
    assert box is not None and "1개" in str(box.label)
    box.check()

    _clone(repository, "두 번째 가정")
    clear_equipment_scenario_cache()  # 화면에서 복제하면 부르는 것
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(app.run())

    assert len(repository.list_revisions()) == 1
    assert any("다른 설비 시나리오 2개" in text for text in _texts(app, "error"))
    box = _removal_box(app)
    assert box is not None and "2개" in str(box.label) and not box.value
    box.check()
    app.button(key=EDIT_SAVE_BUTTON_KEY).click()
    _ok(app.run())
    assert len(repository.list_revisions()) == 2
    assert not app.error


def test_the_removal_check_covers_what_it_saw() -> None:
    one = RemovalElsewhere((("EQ-02", ("셋업 실무",)),))
    two = RemovalElsewhere((("EQ-02", ("셋업 실무", "두 번째 가정")),))
    more = RemovalElsewhere((("EQ-01", ("셋업 실무",)), ("EQ-02", ("셋업 실무",))))

    assert one.covered_by(one) and one.covered_by(two) and one.covered_by(more)
    assert not two.covered_by(one) and not more.covered_by(one) and not one.covered_by(None)
    assert len({one.token, two.token, more.token}) == 3
    # 시나리오 차례는 지문을 바꾸지 않는다.
    assert two.token == RemovalElsewhere((("EQ-02", ("두 번째 가정", "셋업 실무")),)).token


def _popup_without_eq02(database: str, page_file: str) -> None:
    """설비 화면 한 회차 + 사이드바 팝업 본문 — 처음 한 번 편집본에서 EQ-02 를 지운다."""
    from pathlib import Path

    import streamlit as st

    from capa_simulation.components.equipment_data_workspace import (
        ensure_equipment_drafts,
        replace_equipment_buffer,
    )
    from capa_simulation.components.equipment_scenario_status import (
        render_equipment_scenario_dialog_body,
    )
    from capa_simulation.equipment_scenario_activation import resolve_equipment_session

    session = resolve_equipment_session(database)
    frames = ensure_equipment_drafts(session.snapshot)
    if not st.session_state.get("removed"):
        kept = frames[1].loc[frames[1]["설비명"].ne("EQ-02")].reset_index(drop=True)
        replace_equipment_buffer((frames[0], kept, frames[2]))
        st.session_state["removed"] = True
    render_equipment_scenario_dialog_body(Path(database), page_file=page_file)


def test_the_popup_save_has_no_check_and_is_refused_the_same_way(tmp_path: Path) -> None:
    """확인 체크가 없는 사이드바 팝업 저장도 같은 판정으로 막힌다 — RawData 저장 칸에서 확인하라고
    알린다(밤사이 결정 「체크 칸이 없는 자리도 막는다」)."""
    from capa_simulation.components.equipment_scenario_status import (
        EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
        SAVE_BUTTON_KEY,
        SAVE_MODE,
    )
    from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS

    repository, _ = _two_scenarios(tmp_path)
    app = AppTest.from_function(
        _popup_without_eq02,
        args=(str(repository.database_path), Path(AVAILABLE_EQUIPMENT_STATUS.path).name),
        default_timeout=60,
    )
    app.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = SAVE_MODE
    _ok(app.run())
    app.button(key=SAVE_BUTTON_KEY).click()
    _ok(app.run())

    assert len(repository.list_revisions()) == 1
    assert any(
        "지우는 호기 1대(EQ-02)는 다른 설비 시나리오 1개(「셋업 실무」)에도 일정이 있습니다" in text
        and "저장하려면 가용설비 현황 설비 마스터 탭 저장 칸의" in text
        for text in _texts(app, "error")
    )


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


# ------------------------------------------------------------------ S3 리뷰 — 묶음·잠금 글·배선


def _grouped_fleet(tmp_path: Path) -> tuple[DuckDBEquipmentRepository, str]:
    """C1 1F 에 Main 설비 MOD-1 모듈 넷, C1 2F 에 EQ-03 — 「운영 일정」 과 그 복제 「셋업 실무」."""
    from test_space_floor_state_page import _fleet

    repository = _seeded(tmp_path, _with_unit(_fleet(), "EQ-03", 40, **{"층": "2F"}))
    return repository, _clone(repository).equipment_scenario_id


def test_the_pure_group_check_says_what_the_store_refuses(tmp_path: Path) -> None:
    """설비 마스터 탭이 미리 쓰는 판정은 저장소(`split_layout`)와 같은 글이다(설계 10장·Q1(c))."""
    from test_equipment_scenario_repository import _request, _set

    from capa_simulation.components.equipment_data_workspace import layout_lock_origins
    from capa_simulation.persistence.equipment_repository import EquipmentLayoutScopeError
    from capa_simulation.services.layout_overlay import assumption_group_refusal

    repository, setup = _grouped_fleet(tmp_path)
    mine = _session(repository, setup)
    edited = _set(_set(mine.equipment, "EQ-03", "Main 설비", "MOD-1"), "EQ-03", "층", "1F")
    found = assumption_group_refusal(
        edited, mine.equipment, layout_lock_origins(edited, mine.equipment, {}), {}
    )
    assert found is not None and found[1] == "EQ-03"
    with pytest.raises(EquipmentLayoutScopeError) as refused:
        repository.save_equipment(_request(mine, setup, equipment=edited))
    assert str(refused.value) == found[0]
    # 같은 층 호기를 묶는 고침은 묻지 않는다.
    same_floor = _set(mine.equipment, "EQ-01", "Main 설비", "MOD-1")
    assert (
        assumption_group_refusal(
            same_floor, mine.equipment, layout_lock_origins(same_floor, mine.equipment, {}), {}
        )
        is None
    )


def test_an_assumption_submit_reverts_a_main_unit_edit_across_official_floors(
    tmp_path: Path,
) -> None:
    """가정 세션 제출이 공식 동·층이 다른 호기를 한 묶음으로 묶으면 그 Main 설비 칸만 제출 전 값으로
    되돌리고 같은 글로 알린다 — 나머지 편집은 반영한다(S3 리뷰, 설계 10장)."""
    _, setup = _grouped_fleet(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    names = list(app.session_state[BUFFER_KEY][1]["설비명"])
    row = names.index("EQ-03")
    tables = BrowserTables(app)
    key = _editor_key(app)
    tables.edit(key, row, "Main 설비", "MOD-1")
    tables.edit(key, row, "층", "1F")
    tables.edit(key, row, "설비이력", "묶는 중")
    app.button(key=VIEW_APPLY_BUTTON_KEY).click()
    _ok(tables.run())

    assert pd.isna(_buffer_value(app, "EQ-03", "Main 설비"))
    assert _buffer_value(app, "EQ-03", "설비이력") == "묶는 중"
    assert any(
        "가정 설비 시나리오에서는 공식 층이 다른 호기를 한 묶음으로 묶지 않습니다(EQ-03 은 공식 "
        "C1 2F, 묶음 MOD-1 은 C1 1F)"
        in text
        and "제출 전 값으로 되돌렸습니다" in text
        for text in _texts(app, "error")
    )


def test_the_submit_check_reverts_only_this_submits_main_unit_edit(tmp_path: Path) -> None:
    """되돌리는 것은 이 제출이 바꾼 Main 설비 칸뿐이다 — 제출 전 편집본이 이미 그렇게 묶였으면 막지
    않는다(되돌릴 고침이 없는데 막으면 저장까지 못 간다 — 저장이 같은 글로 거부한다)."""
    from test_equipment_scenario_repository import _set

    from capa_simulation.components.equipment_data_workspace import refuse_mixed_groups

    repository, setup = _grouped_fleet(tmp_path)
    mine = _session(repository, setup)
    grouped = _set(_set(mine.equipment, "EQ-03", "Main 설비", "MOD-1"), "EQ-03", "층", "1F")
    edited = _set(grouped, "EQ-01", "설비이력", "고침")

    reverted, message = refuse_mixed_groups(
        edited, mine.equipment, saved=mine.equipment, renames={}, official_places={}
    )
    assert message is not None
    rows = reverted.set_index("설비명")
    assert pd.isna(rows.loc["EQ-03", "Main 설비"]) and rows.loc["EQ-01", "설비이력"] == "고침"

    kept, none = refuse_mixed_groups(
        edited, grouped, saved=mine.equipment, renames={}, official_places={}
    )
    assert none is None and kept is edited


def test_an_assumption_paste_grouping_across_official_floors_is_refused_before_preview(
    tmp_path: Path,
) -> None:
    _, setup = _grouped_fleet(tmp_path)
    app = _ok(_workspace(tmp_path / "equipment.duckdb", setup).run())
    app.checkbox(key=PASTE_LAYOUT_KEY).check()
    app.selectbox(TARGET_KEY).set_value("설비 마스터")
    app.text_area(CLIPBOARD_KEY).set_value("설비명\tMain 설비\t층\nEQ-03\tMOD-1\t1F")
    app.button(PREVIEW_BUTTON_KEY).click()
    _ok(app.run())

    assert PREVIEW_KEY not in app.session_state
    assert any(
        "가정 설비 시나리오에서는 공식 층이 다른 호기를 한 묶음으로 묶지 않습니다" in text
        for text in _texts(app, "error")
    )


def _edit_mode_texts(database: str) -> None:
    """한 회차: 세션을 세우고 찍힌 역할이 바뀐(공식으로 찍힘) 판정의 잠금 글 둘을 적는다."""
    import streamlit as st

    from capa_simulation.equipment_scenario_activation import (
        resolve_equipment_session,
        space_edit_mode,
    )

    mode = space_edit_mode(resolve_equipment_session(database), stamped_role="official")
    st.session_state["seen"] = (mode.layout, mode.lock_reason, mode.master_tab_lock_reason)


def test_the_role_changed_lock_points_the_master_tab_at_the_space_box(tmp_path: Path) -> None:
    """찍힌 역할이 바뀐 잠금 글 — Space 현황은 그 자리의 「배치 변경만 버리기」 를, 설비 마스터 탭은
    그 단추가 없으므로 Space 현황 저장 안 한 배치 변경 상자를 가리킨다(S3 리뷰)."""
    from capa_simulation.equipment_scenario_activation import SELECTION_KEY

    repository, setup = _two_scenarios(tmp_path)
    app = AppTest.from_function(
        _edit_mode_texts, args=(str(repository.database_path),), default_timeout=60
    )
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": None}
    _ok(app.run())
    layout, space, master = app.session_state["seen"]
    assert layout == "locked"
    assert "— 「배치 변경만 버리기」 로 버린 뒤" in space
    assert "Space 현황 「저장 안 한 배치 변경」 상자의 「배치 변경만 버리기」 로" in master


def test_the_page_passes_the_space_judgment_to_the_master_tab(tmp_path: Path) -> None:
    """가용설비 현황이 설비 마스터 탭에 넘기는 배치 칸 판정은 `space_edit_mode` 다 — 남이 그
    시나리오에 다른 배치를 저장한 낡은 가정 세션은 탭 머리에 잠금 글이 선다(S3 리뷰 — 하네스가 직접
    넣던 것을 페이지로 본다)."""
    from test_equipment_pages import PROJECT_ROOT, _page_script
    from test_equipment_scenario_repository import _request, _set

    from capa_simulation.equipment_scenario_activation import SELECTION_KEY

    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    clear_equipment_repository()
    page = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
    app = AppTest.from_string(_page_script(page, repository.database_path), default_timeout=90)
    app.session_state[SELECTION_KEY] = {"scenario_id": setup, "schedule_revision_id": pinned}
    _ok(app.run())

    assert any(
        "배치 편집이 잠겨 있어" in text and "r2 에 다른 배치가 저장됐습니다" in text
        for text in _texts(app, "caption")
    )
