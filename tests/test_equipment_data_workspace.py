# Purpose: 설비 입력의 두 단계 저장과 재검토·오류 복구·다른 표 보존을 실제 임시 리비전으로 검사한다.

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    CLIPBOARD_KEY,
    DROP_EXAMPLE_ROWS_KEY,
    EQUIPMENT_EDITOR_KEY,
    EXAMPLE_DROP_BUTTON_KEY,
    IMPORT_SAVE_BUTTON_KEY,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    TARGET_KEY,
    build_import_review,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    empty_downtime_schedule,
    empty_equipment_baseline,
)
from capa_simulation.services.equipment_csv import (
    SAMPLE_BASELINE_CATEGORY,
    SAMPLE_BASELINE_COUNT,
    SAMPLE_BASELINE_PROCESS,
    SAMPLE_BASELINE_TEMPLATE_NOTE,
)
from capa_simulation.services.equipment_samples import sample_equipment_baseline
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
    # 편집표는 저장본을 처음 읽은 회차에 새 세대로 섰다(`editor_state.discard_editor`). 브라우저가
    # 그 키로 편집을 보내므로 테스트도 지금 세대의 키에 넣는다.
    generation_key = f"{EQUIPMENT_EDITOR_KEY}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    widget_key = f"{EQUIPMENT_EDITOR_KEY}__g{generation}" if generation else EQUIPMENT_EDITOR_KEY
    app.session_state[widget_key] = {
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


def _baseline_template_text() -> str:
    """양식을 Excel 로 열어 헤더째 복사한 것과 같은 탭 구분 텍스트. 예시 한 줄만 들어 있다."""
    row = (
        SAMPLE_BASELINE_PROCESS,
        SAMPLE_BASELINE_CATEGORY,
        str(SAMPLE_BASELINE_COUNT),
        SAMPLE_BASELINE_TEMPLATE_NOTE,
    )
    return "\t".join(BASELINE_COLUMNS) + "\n" + "\t".join(row)


def test_the_template_example_row_is_flagged_before_save_and_cleared_in_one_click(
    tmp_path: Path,
) -> None:
    """저장을 누르기 전에 알리고, 한 번 눌러 지우면 그대로 저장까지 간다.

    **지운 것이 되돌아오면 안 된다.** 후보에서만 빼면 재검토가 원문을 다시 읽어 예시 줄을
    또 넣는다. 세션 플래그가 `build_import_review` 를 merge 전에 거르게 만든다.
    """
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _preview(app, _baseline_template_text(), target="기존 보유대수")

    assert any("예시 행 1건" in warning.value for warning in app.warning)
    assert app.button(EXAMPLE_DROP_BUTTON_KEY).label == "예시 행 1건 지우기"
    app.button(EXAMPLE_DROP_BUTTON_KEY).click().run()

    assert not app.exception
    assert not any("예시 행" in warning.value for warning in app.warning)
    assert any("예시 행 1건을 빼고" in info.value for info in app.info)
    assert app.session_state[PREVIEW_KEY].candidate[0].empty
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()

    assert not app.exception
    assert not app.error
    repository = _repository(path)
    revisions = repository.list_revisions()
    assert len(revisions) == 1
    assert repository.load_snapshot(revisions[0].revision_id).baseline.empty


def test_saving_the_template_example_row_without_dropping_it_is_still_blocked(
    tmp_path: Path,
) -> None:
    """예방형 안내를 더해도 **저장 검증은 그대로다.** 지우지 않고 저장하면 막힌다."""
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _preview(app, _baseline_template_text(), target="기존 보유대수")
    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()

    assert not app.exception
    assert any("예시 행이 1건" in error.value for error in app.error)
    assert not _repository(path).list_revisions()


def test_a_sample_row_left_in_the_edit_buffer_is_flagged_and_cleared(tmp_path: Path) -> None:
    """붙여넣기가 아니라 편집 버퍼에 남은 개발용 샘플도 같은 두 함수가 잡는다.

    빈 DB 로 처음 연 사람은 화면이 채워 준 샘플을 자기 값으로 오해한 채 저장을 누른다.
    """
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _, equipment, downtime = app.session_state[BUFFER_KEY]
    sample = sample_equipment_baseline()
    app.session_state[BUFFER_KEY] = (sample, equipment, downtime)
    app.run()

    assert not app.exception
    assert any(f"예시 행 {len(sample):,}건" in warning.value for warning in app.warning)
    app.button(EXAMPLE_DROP_BUTTON_KEY).click().run()

    assert not app.exception
    assert not any("예시 행" in warning.value for warning in app.warning)
    assert app.session_state[BUFFER_KEY][0].empty
    assert app.session_state[DROP_EXAMPLE_ROWS_KEY] is True


# ------------------------------------------------------------- 현재 데이터 내려받기


def test_current_data_downloads_stand_beside_the_templates_and_name_their_basis(
    tmp_path: Path,
) -> None:
    """세 표의 「현재 데이터」 버튼이 양식 옆에 서고, 파일 이름이 저장본 번호를 말한다.

    저장본과 같은 편집본이면 캡션이 「저장본과 같음」이고 이름에 `_edited` 가 없다. 빈 표도
    막지 않는다 — 헤더만 든 파일이 곧 정확한 컬럼 차례의 양식이다.
    """
    from capa_simulation.components.equipment_data_workspace import current_data_file_name

    repository = _repository(tmp_path / "equipment.duckdb")
    saved = repository.save_snapshot(
        empty_equipment_baseline(),
        _master(["EQ-01", "EQ-02"]),
        empty_downtime_schedule(),
        note="현재 데이터 내보내기 검사",
    )
    app = _app(tmp_path / "equipment.duckdb")

    labels = [button.label for button in app.download_button]
    assert "호기 마스터 현재 데이터 · 2행" in labels
    assert "기존 보유대수 현재 데이터 · 0행" in labels
    assert "비가동 일정 현재 데이터 · 0행" in labels
    # 양식 버튼 셋은 그대로 남는다.
    assert sum(label.endswith("양식") for label in labels) == 3
    captions = " ".join(str(item.value) for item in app.caption)
    assert f"저장본 r{saved.revision.revision_no}" in captions
    assert "저장본과 같음" in captions

    name = current_data_file_name(
        "equipment_master", latest_snapshot=saved, edited=False, today=date(2026, 9, 24)
    )
    assert name == f"equipment_master_r{saved.revision.revision_no}_20260924.csv"
    edited_name = current_data_file_name(
        "equipment_master", latest_snapshot=None, edited=True, today=date(2026, 9, 24)
    )
    assert edited_name == "equipment_master_r0_edited_20260924.csv"


def test_pasting_the_exported_current_data_back_round_trips_through_the_workspace(
    tmp_path: Path,
) -> None:
    """내려받은 것을 고치지 않고 그대로 붙여넣어도 통과한다 — 이 기능의 합격선이다.

    내보낸 CSV 를 탭 구분 글로 바꿔(Excel 에서 복사하면 그 모양이다) 미리보기까지 돌리면
    「기존 대체」만 나오고 신규가 없다. 저장 후 표도 그대로다.
    """
    import csv
    import io

    from capa_simulation.services.equipment_csv import equipment_csv_bytes

    repository = _repository(tmp_path / "equipment.duckdb")
    master = _master(["EQ-01", "EQ-02", "EQ-03"])
    repository.save_snapshot(
        empty_equipment_baseline(), master, empty_downtime_schedule(), note="원본"
    )
    app = _app(tmp_path / "equipment.duckdb")

    rows = list(csv.reader(io.StringIO(equipment_csv_bytes(master).decode("utf-8-sig"))))
    pasted = "\n".join("\t".join(row) for row in rows)
    _preview(app, pasted)
    review = app.session_state[PREVIEW_KEY]
    assert review.changes["Import구분"].eq("대체").sum() == 3
    assert review.changes["Import구분"].eq("신규").sum() == 0

    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()
    assert not app.exception
    latest = repository.load_snapshot(repository.latest_revision_id())
    assert latest.revision.revision_no == 2
    assert_frame_equal(
        latest.equipment.reset_index(drop=True), master.reset_index(drop=True), check_dtype=False
    )


def test_current_data_downloads_say_when_the_buffer_differs_from_the_saved_revision(
    tmp_path: Path,
) -> None:
    """편집 버퍼가 저장본과 다르면 캡션이 「저장하지 않은 변경 포함」으로 바뀌고 버튼 행 수도
    버퍼를 따른다. 내보내는 것이 저장본이 아니라 **지금 보는 편집본**임을 화면이 말한다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(
        empty_equipment_baseline(), _master(["EQ-01"]), empty_downtime_schedule(), note="원본"
    )
    app = _app(tmp_path / "equipment.duckdb")
    assert "저장본과 같음" in " ".join(str(item.value) for item in app.caption)

    baseline, _equipment_frame, downtime = app.session_state[BUFFER_KEY]
    app.session_state[BUFFER_KEY] = (baseline, _master(["EQ-01", "EQ-99"]), downtime)
    app.run()
    assert not app.exception

    captions = " ".join(str(item.value) for item in app.caption)
    assert "저장하지 않은 변경 포함" in captions
    assert "호기 마스터 현재 데이터 · 2행" in [button.label for button in app.download_button]
