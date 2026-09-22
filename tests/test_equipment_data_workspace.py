# Purpose: 설비 입력의 두 단계 저장과 재검토·오류 복구·다른 표 보존을 실제 임시 리비전으로 검사한다.

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from capa_simulation.components.equipment_data_workspace import (
    CLIPBOARD_KEY,
    EQUIPMENT_EDITOR_KEY,
    IMPORT_SAVE_BUTTON_KEY,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    TARGET_KEY,
    build_import_review,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    empty_downtime_schedule,
    empty_equipment_baseline,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_baseline,
    prepare_equipment_master,
)


def _master(ids: list[str]) -> pd.DataFrame:
    return prepare_equipment_master(
        pd.DataFrame(
            {
                "호기": ids,
                "공정소분류": ["Die Attach"] * len(ids),
                "장기보관여부": ["N"] * len(ids),
                "기존설비여부": ["Y"] * len(ids),
                "레이아웃표시": ["N"] * len(ids),
            }
        ).reindex(columns=EQUIPMENT_COLUMNS)
    )


def _repository(path: Path) -> DuckDBEquipmentRepository:
    repository = DuckDBEquipmentRepository(path)
    repository.initialize()
    return repository


def _app(path: Path) -> AppTest:
    # 실제 페이지와 동일하게 최신 리비전만 읽는다. 운영 DB와 전역 settings를 변경하지 않는다.
    return AppTest.from_string(
        f"""
from pathlib import Path
import streamlit as st
from capa_simulation.components.equipment_data_workspace import render_equipment_data_workspace
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_equipment_baseline, empty_equipment_master, empty_downtime_schedule,
)
repository = DuckDBEquipmentRepository(Path({str(path)!r}))
repository.initialize()
revision_id = repository.latest_revision_id()
snapshot = repository.load_snapshot(revision_id) if revision_id else None
render_equipment_data_workspace(
    repository=repository, latest_snapshot=snapshot,
    baseline=snapshot.baseline if snapshot else empty_equipment_baseline(),
    equipment=snapshot.equipment if snapshot else empty_equipment_master(),
    downtime=snapshot.downtime if snapshot else empty_downtime_schedule(),
    floor_canvases={{}}, max_extent=(100.0, 60.0),
)
""",
        default_timeout=20,
    ).run()


def _preview(app: AppTest, text: str, target: str = "호기 마스터") -> None:
    app.selectbox(TARGET_KEY).set_value(target)
    app.text_area(CLIPBOARD_KEY).set_value(text)
    app.button(PREVIEW_BUTTON_KEY).click().run()
    assert not app.exception
    assert not app.error


def test_thirty_rows_are_reviewed_then_saved_once_with_other_tables_preserved(
    tmp_path: Path,
) -> None:
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    baseline = prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": ["Other Process"],
                "분류": ["전체"],
                "기존보유대수": [8],
                "비고": ["보존"],
            }
        )
    )
    equipment = _master(["OLD-001"])
    downtime = prepare_downtime_schedule(
        pd.DataFrame(
            {
                "호기": ["OLD-001"],
                "비가동유형": ["고장"],
                "시작일": ["2026-10-01"],
                "종료일": ["2026-10-03"],
                "상세사유": ["수리"],
            }
        ).reindex(columns=DOWNTIME_COLUMNS),
        equipment=equipment,
    )
    original = repository.save_snapshot(baseline, equipment, downtime)
    app = _app(path)
    assert not app.exception
    incoming = _master([f"NEW-{index:03}" for index in range(30)])
    _preview(app, incoming.to_csv(index=False, sep="\t"))
    assert len(repository.list_revisions()) == 1
    assert len(app.session_state[PREVIEW_KEY].changes) == 30
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception
    assert not app.error
    revisions = repository.list_revisions()
    assert len(revisions) == 2
    saved = repository.load_snapshot(revisions[0].revision_id)
    assert len(saved.equipment) == 31
    assert_frame_equal(saved.baseline, original.baseline)
    assert_frame_equal(saved.downtime, original.downtime)
    assert_frame_equal(
        repository.load_snapshot(original.revision.revision_id).equipment, original.equipment
    )


def test_changed_input_and_target_cannot_save_the_previous_review(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _preview(app, _master(["FIRST"]).to_csv(index=False, sep="\t"))
    app.text_area(CLIPBOARD_KEY).set_value(_master(["SECOND"]).to_csv(index=False, sep="\t"))
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    repository = _repository(path)
    assert not repository.list_revisions()
    assert app.session_state[PREVIEW_KEY].candidate[1]["호기"].tolist() == ["SECOND"]
    assert any("미리보기를 갱신" in info.value for info in app.info)
    app.selectbox(TARGET_KEY).set_value("기존 보유대수")
    app.text_area(CLIPBOARD_KEY).set_value("공정\t분류\t기존보유대수\t비고\nP\t전체\t7\t사용자 값")
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    assert not repository.list_revisions()
    assert app.session_state[PREVIEW_KEY].target == "기존 보유대수"
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception
    saved = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    assert saved.equipment.empty
    assert saved.baseline["기존보유대수"].tolist() == [7.0]


def test_invalid_input_remains_editable_and_successful_retry_creates_one_revision(
    tmp_path: Path,
) -> None:
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    malformed = "호기\t공정소분류\nEQ-BAD\tDie Attach"
    app.text_area(CLIPBOARD_KEY).set_value(malformed)
    app.button(PREVIEW_BUTTON_KEY).click().run()
    assert app.error
    assert not app.exception
    assert app.text_area(CLIPBOARD_KEY).value == malformed
    repository = _repository(path)
    assert not repository.list_revisions()
    _preview(app, _master(["CORRECTED"]).to_csv(index=False, sep="\t"))
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception
    assert not app.error
    assert len(repository.list_revisions()) == 1


def test_editor_change_after_review_requires_review_again(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_snapshot(
        empty_equipment_baseline(), _master(["EXISTING"]), empty_downtime_schedule()
    )
    app = _app(path)
    _preview(app, _master(["NEW"]).to_csv(index=False, sep="\t"))
    app.session_state[EQUIPMENT_EDITOR_KEY] = {
        "edited_rows": {0: {"비고": "검토 뒤 수정"}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception
    assert len(repository.list_revisions()) == 1
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    saved = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    assert saved.equipment.set_index("호기").loc["EXISTING", "비고"] == "검토 뒤 수정"


def test_csv_review_and_future_open_downtime_history(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    equipment = _master(["EQ-FUTURE"])
    future = date.today() + timedelta(days=60)
    downtime = prepare_downtime_schedule(
        pd.DataFrame(
            {
                "호기": ["EQ-FUTURE"],
                "비가동유형": ["고장"],
                "시작일": [future],
                "종료일": [None],
            }
        ).reindex(columns=DOWNTIME_COLUMNS),
        equipment=equipment,
    )
    source = (empty_equipment_baseline(), equipment, downtime)
    review = build_import_review(
        "호기 마스터", equipment.to_csv(index=False).encode("utf-8-sig"), source, floor_canvases={}
    )
    assert review.changes["Import구분"].tolist() == ["대체"]
    repository = _repository(path)
    repository.save_snapshot(*review.candidate)
    app = _app(path)
    assert not app.exception
    assert not app.error
    start, end = app.date_input("equipment_history_event_range_v3").value
    assert start == future
    assert end >= start
