# Purpose: 설비 마스터 탭의 넣기·저장 두 단계와 재검토·오류 복구·다른 표 보존을 임시 DB 로 본다.

"""가용설비 현황 탭 ① 「설비 마스터」 — 「엑셀·CSV로 한꺼번에」 팝업 → 「편집본에 넣기」 → 「저장 전
변경」 「리비전 저장」 두 단계(개편 명세 4-6 다·4-8).

옛 설비 마스터 탭 폼(입력·직접 편집·저장 이력 — 개편 D 에서 걷음)을 몰던 시험을 새 길로 옮겼다:
붙여넣기 미리보기가 입력·표·편집본이 바뀌면 다시 확인받는지, 막힌 입력이 칸에 남는지, 넣은 것만
저장되고 다른 두 표는 그대로인지, 예시 행 가드, 현재 데이터 내려받기, 저장 이력, 작은 편집표,
Space 층 사용 상태가 동·층 고르는 값을 좁히는지. AppTest 는 표 컴포넌트 JS 를 못 돌려 대역
(`tests/grid_fake.py`)이 표 출납을 보낸다. 설비 DB 는 시험마다 `tmp_path` 의 새 파일이다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, last, load, send_ops
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest
from test_equipment_master_tab import _TAIL, FAKE_SAVE_KEY, FAKE_SAVE_RESULT_KEY
from test_equipment_pages import PROJECT_ROOT, _page_script
from widget_browser import BrowserTables

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    _NOTE_KEY as NOTE_KEY,
)
from capa_simulation.components.equipment_data_workspace import (
    BASELINE_EDITOR_KEY,
    BUFFER_KEY,
    CLIPBOARD_KEY,
    DOWNTIME_EDITOR_KEY,
    DROP_EXAMPLE_ROWS_KEY,
    EXAMPLE_DROP_BUTTON_KEY,
    NOTHING_SAVED_MESSAGE,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    TARGET_KEY,
    build_import_review,
    discarded_notice,
)
from capa_simulation.components.equipment_import_dialog import IMPORT_APPLY_BUTTON_KEY
from capa_simulation.components.equipment_master_tab import (
    NOTHING_TO_SAVE,
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_HISTORY,
    SIDE_KEY,
    TABLE_KEY,
)
from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY
from capa_simulation.navigation import (
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_SUMMARY_TAB,
    EQUIPMENT_TAB_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    LEGACY_EQUIPMENT_HEADER_ALIASES,
    OPTIONAL_EQUIPMENT_COLUMNS,
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
from capa_simulation.services.layout_overlay import ReappliedLayout

PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _master(ids: list[str]) -> pd.DataFrame:
    return prepare_equipment_master(
        pd.DataFrame(
            {
                "설비명": ids,
                "공정소분류": ["Die Attach"] * len(ids),
                "보관유무": ["N"] * len(ids),
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
    """실제 가용설비 현황 페이지의 탭 ① — 운영 DB 와 전역 settings 를 바꾸지 않는다(두 DB 는
    `path` 곁). 꼬리는 사이드바 팝업·Space 와 같은 저장 길(`save_equipment_buffer`)을 부른다
    (`FAKE_SAVE_KEY`)."""
    app = AppTest.from_string(_page_script(PAGE, path) + _TAIL, default_timeout=60)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    return _ok(app.run())


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest, kind: str) -> list[str]:
    return [str(item.value) for item in getattr(app, kind)]


def _open_import(app: AppTest) -> AppTest:
    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    return _ok(app.run())


def _preview(app: AppTest, text: str, target: str = "설비 마스터") -> AppTest:
    """「엑셀·CSV로 한꺼번에」 팝업을 (닫혀 있으면) 열고 붙여넣은 뒤 「변경 미리보기」."""
    if EQUIPMENT_DIALOG_KEY not in app.session_state:
        _open_import(app)
    app.selectbox(key=TARGET_KEY).set_value(target)
    app.text_area(key=CLIPBOARD_KEY).set_value(text)
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    assert not app.error, _texts(app, "error")
    return app


def _put(app: AppTest) -> AppTest:
    """미리본 후보를 「편집본에 넣기」(저장하지 않는다)."""
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click()
    return _ok(app.run())


def _save(app: AppTest) -> AppTest:
    """「저장 전 변경」 의 「리비전 저장」."""
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    app.button(key=SAVE_BUTTON_KEY).click()
    return _ok(app.run())


def test_thirty_rows_are_put_then_saved_once_with_other_tables_preserved(tmp_path: Path) -> None:
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
                "설비명": ["OLD-001"],
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
    incoming = _master([f"NEW-{index:03}" for index in range(30)])
    _preview(app, incoming.to_csv(index=False, sep="\t"))
    assert len(app.session_state[PREVIEW_KEY].changes) == 30
    _put(app)
    # 넣기는 편집본만 바꾼다 — 리비전은 「리비전 저장」 에서 한 번.
    assert len(repository.list_revisions()) == 1
    assert len(app.session_state[BUFFER_KEY][1]) == 31
    _save(app)
    assert not app.error, _texts(app, "error")
    revisions = repository.list_revisions()
    assert len(revisions) == 2
    saved = repository.load_snapshot(revisions[0].revision_id)
    assert len(saved.equipment) == 31
    assert_frame_equal(saved.baseline, original.baseline)
    assert_frame_equal(saved.downtime, original.downtime)
    assert_frame_equal(
        repository.load_snapshot(original.revision.revision_id).equipment, original.equipment
    )


def test_changed_input_and_target_cannot_put_the_previous_review(tmp_path: Path) -> None:
    """미리본 뒤 붙여넣기나 등록할 표를 바꾸고 「편집본에 넣기」 를 누르면 넣지 않고 미리보기를
    새 입력으로 갱신한다(`ImportReview.matches`). 다시 누르면 그때 넣는다."""
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _preview(app, _master(["FIRST"]).to_csv(index=False, sep="\t"))
    app.text_area(key=CLIPBOARD_KEY).set_value(_master(["SECOND"]).to_csv(index=False, sep="\t"))
    _put(app)
    assert app.session_state[BUFFER_KEY][1].empty
    assert app.session_state[PREVIEW_KEY].candidate[1]["설비명"].tolist() == ["SECOND"]
    assert any("미리보기를 갱신" in text for text in _texts(app, "info"))
    app.selectbox(key=TARGET_KEY).set_value("기존 보유대수")
    app.text_area(key=CLIPBOARD_KEY).set_value(
        "공정\t분류\t기존보유대수\t비고\nP\t전체\t7\t사용자 값"
    )
    _put(app)
    assert app.session_state[BUFFER_KEY][0].empty
    assert app.session_state[PREVIEW_KEY].target == "기존 보유대수"
    _put(app)
    assert EQUIPMENT_DIALOG_KEY not in app.session_state
    assert app.session_state[BUFFER_KEY][0]["기존보유대수"].tolist() == [7.0]
    _save(app)
    repository = _repository(path)
    saved = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    assert saved.equipment.empty
    assert saved.baseline["기존보유대수"].tolist() == [7.0]


def test_invalid_input_remains_editable_and_successful_retry_creates_one_revision(
    tmp_path: Path,
) -> None:
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _open_import(app)
    malformed = "호기\t공정소분류\nEQ-BAD\tDie Attach"
    app.text_area(key=CLIPBOARD_KEY).set_value(malformed)
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    assert app.error
    assert app.text_area(key=CLIPBOARD_KEY).value == malformed
    assert PREVIEW_KEY not in app.session_state
    repository = _repository(path)
    assert not repository.list_revisions()
    _preview(app, _master(["CORRECTED"]).to_csv(index=False, sep="\t"))
    _put(app)
    _save(app)
    assert not app.error, _texts(app, "error")
    assert len(repository.list_revisions()) == 1


def test_a_grid_edit_after_review_requires_review_again(tmp_path: Path, grid: Calls) -> None:
    """미리본 뒤 표에서 편집본을 고치면 옛 미리보기는 거둔다 — 「편집본에 넣기」 가 꺼지고, 다시
    미리보면 그 고침 위에 붙여넣기가 얹힌다(옛 후보가 표 고침을 지우지 않는다)."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_snapshot(
        empty_equipment_baseline(), _master(["EXISTING"]), empty_downtime_schedule()
    )
    app = _app(path)
    _preview(app, _master(["NEW"]).to_csv(index=False, sep="\t"))
    load(app, [], kind="all")
    send_ops(app, grid, {"op": "cell", "id": "s:EXISTING", "col": "설비이력", "text": "검토 뒤"})
    assert PREVIEW_KEY not in app.session_state
    assert app.button(key=IMPORT_APPLY_BUTTON_KEY).disabled
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    _put(app)
    _save(app)
    saved = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    assert saved.equipment.set_index("설비명").loc["EXISTING", "설비이력"] == "검토 뒤"
    assert "NEW" in set(saved.equipment["설비명"])


def test_an_old_header_paste_is_renamed_and_the_dropped_column_is_announced(
    tmp_path: Path,
) -> None:
    """사내의 옛 머리 엑셀을 그대로 붙여넣어도 저장되고, 빠진 `투자기준` 은 알림 한 줄로 남는다."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    legacy = (
        _master(["OLD-HEADER"])
        .drop(columns=list(OPTIONAL_EQUIPMENT_COLUMNS))
        .rename(columns={new: old for old, new in LEGACY_EQUIPMENT_HEADER_ALIASES.items()})
        .assign(투자기준="322K")
    )
    app = _app(path)

    _preview(app, legacy.to_csv(index=False, sep="\t"))

    assert any("투자기준" in text for text in _texts(app, "info"))
    _put(app)
    _save(app)
    assert not app.error, _texts(app, "error")
    saved = repository.load_snapshot(repository.list_revisions()[0].revision_id)
    assert saved.equipment["설비명"].tolist() == ["OLD-HEADER"]
    assert list(saved.equipment.columns) == list(EQUIPMENT_COLUMNS)


def test_csv_review_and_future_open_downtime_history(tmp_path: Path) -> None:
    path = tmp_path / "equipment.duckdb"
    equipment = _master(["EQ-FUTURE"])
    future = date.today() + timedelta(days=60)
    downtime = prepare_downtime_schedule(
        pd.DataFrame(
            {
                "설비명": ["EQ-FUTURE"],
                "비가동유형": ["고장"],
                "시작일": [future],
                "종료일": [None],
            }
        ).reindex(columns=DOWNTIME_COLUMNS),
        equipment=equipment,
    )
    source = (empty_equipment_baseline(), equipment, downtime)
    review = build_import_review(
        "설비 마스터", equipment.to_csv(index=False).encode("utf-8-sig"), source, floor_canvases={}
    )
    assert review.changes["Import구분"].tolist() == ["대체"]
    repository = _repository(path)
    repository.save_snapshot(*review.candidate)
    app = _app(path)
    app.session_state[SIDE_KEY] = SIDE_HISTORY
    _ok(app.run())
    assert not app.error
    picked = app.date_input(key="equipment_history_event_range_v3").value
    assert isinstance(picked, tuple) and len(picked) == 2
    start, end = picked
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


def _example_lines(grid: Calls) -> list[str]:
    """「저장 전 변경」 고칠 것 가운데 예시 행 줄(표 단위 줄은 마지막 칸이 글이다)."""
    errors = last(grid, emg.side_key("changes"))["errors"]
    return [str(line[3]) for line in errors if "예시 행" in str(line[3])]


def test_the_template_example_row_is_flagged_before_save_and_cleared_in_one_click(
    tmp_path: Path, grid: Calls
) -> None:
    """저장을 누르기 전에 알리고(「저장 전 변경」 고칠 것 한 줄 · 기존 보유대수 표 위 경고), 한 번
    눌러 지우면 그대로 저장까지 간다. 지운 표지(`DROP_EXAMPLE_ROWS_KEY`)가 남아 다시 미리볼 때도
    예시 줄을 merge 전에 거른다."""
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _preview(app, _baseline_template_text(), target="기존 보유대수")
    _put(app)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    assert _example_lines(grid) and "예시 행 1건" in _example_lines(grid)[0]

    app.session_state[TABLE_KEY] = "기존 보유대수"
    _ok(app.run())
    assert any("예시 행 1건" in text for text in _texts(app, "warning"))
    assert app.button(key=EXAMPLE_DROP_BUTTON_KEY).label == "예시 행 1건 지우기"
    app.button(key=EXAMPLE_DROP_BUTTON_KEY).click()
    _ok(app.run())

    assert not any("예시 행" in text for text in _texts(app, "warning"))
    assert any("예시 행 1건을 편집본에서 뺐습니다" in text for text in _texts(app, "info"))
    assert app.session_state[BUFFER_KEY][0].empty
    assert app.session_state[DROP_EXAMPLE_ROWS_KEY] is True
    assert not _example_lines(grid)
    _save(app)
    # 예시 행을 빼면 저장할 것이 없다 — 빈 저장소에 빈 리비전을 만들지 않는다(결정 모음).
    assert _repository(path).list_revisions() == []
    assert any(NOTHING_TO_SAVE in text for text in _texts(app, "info"))


def test_saving_the_template_example_row_without_dropping_it_is_still_blocked(
    tmp_path: Path,
) -> None:
    """예방형 안내를 더해도 **저장 검증은 그대로다.** 지우지 않고 「리비전 저장」 하면 고칠 것으로
    막히고, 그 줄을 모르는 다른 저장 길(사이드바 팝업·Space — `save_equipment_buffer`)도 막힌다."""
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    _preview(app, _baseline_template_text(), target="기존 보유대수")
    _put(app)
    _save(app)
    assert any("오류 1개를 고쳐야 저장됩니다" in text for text in _texts(app, "error"))
    app.session_state[FAKE_SAVE_KEY] = True
    _ok(app.run())
    assert "예시 행이 1건" in str(app.session_state[FAKE_SAVE_RESULT_KEY])
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
    app.session_state[TABLE_KEY] = "기존 보유대수"
    _ok(app.run())

    assert any(f"예시 행 {len(sample):,}건" in text for text in _texts(app, "warning"))
    app.button(key=EXAMPLE_DROP_BUTTON_KEY).click()
    _ok(app.run())

    assert not any("예시 행" in text for text in _texts(app, "warning"))
    assert app.session_state[BUFFER_KEY][0].empty
    assert app.session_state[DROP_EXAMPLE_ROWS_KEY] is True


def test_dropping_example_rows_withdraws_a_lingering_preview(tmp_path: Path) -> None:
    """「예시 행 n건 지우기」 는 편집본을 바꾸는 표 밖 길이라 다른 길과 같이 남은 붙여넣기
    미리보기를 거둔다(`replace_equipment_buffer`) — 다시 짓지 않는다(개편 D 리뷰 rs-d). 옛 폼은 입력
    탭 미리보기와 이 단추가 한 화면에 함께 서서 그 후보를 다시 지었는데, 그때 팝업이 넘기는 배치
    역할·「배치 칸도 붙여넣기」·공식 자리를 빠뜨려 가정 세션의 「배치 칸 끔」 미리보기가 배치 칸을
    받는 쪽으로 바뀌었다. 미리보기는 「엑셀·CSV로 한꺼번에」 팝업이 열린 동안에만 살고, 넣기 앞
    대조(`ImportReview.matches`)가 바뀐 편집본을 다시 미리보게 하며, 그 미리보기는 지운
    표지(`DROP_EXAMPLE_ROWS_KEY`)로 예시 행을 뺀다."""
    path = tmp_path / "equipment.duckdb"
    app = _app(path)
    frames = app.session_state[BUFFER_KEY]
    sample = sample_equipment_baseline()
    app.session_state[BUFFER_KEY] = (sample, frames[1], frames[2])
    incoming = _master(["NEW-001"])
    review = build_import_review(
        "설비 마스터",
        incoming.to_csv(index=False, sep="\t"),
        app.session_state[BUFFER_KEY],
        floor_canvases={},
        paste_layout=False,
    )
    app.session_state[PREVIEW_KEY] = replace(review, layout_pasted=False)
    app.session_state[TABLE_KEY] = "기존 보유대수"
    _ok(app.run())

    app.button(key=EXAMPLE_DROP_BUTTON_KEY).click()
    _ok(app.run())

    assert app.session_state[BUFFER_KEY][0].empty
    assert PREVIEW_KEY not in app.session_state
    assert app.session_state[DROP_EXAMPLE_ROWS_KEY] is True
    notice = next(text for text in _texts(app, "info") if "예시 행" in text)
    assert notice == (
        f"예시 행 {len(sample):,}건을 편집본에서 뺐습니다. 다음 붙여넣기·CSV 미리보기도 예시 행을 "
        "빼고 검토합니다 — 저장 검증은 그대로 돕니다."
    )


# ------------------------------------------------------------- 현재 데이터 내려받기


def _download_labels(app: AppTest) -> list[str]:
    return [str(button.proto.label) for button in app.get("download_button")]


def test_current_data_downloads_stand_beside_the_templates_and_name_their_basis(
    tmp_path: Path,
) -> None:
    """「내려받기」 팝오버 — 세 표의 「현재 데이터」 단추가 양식 셋 곁에 서고, 캡션과 파일 이름이
    저장본 번호를 말한다.

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

    labels = _download_labels(app)
    assert "설비 마스터 현재 데이터 · 2행" in labels
    assert "기존 보유대수 현재 데이터 · 0행" in labels
    assert "비가동 일정 현재 데이터 · 0행" in labels
    # 양식 단추 셋은 그대로 남는다.
    assert sum(label.endswith("양식") for label in labels) == 3
    captions = " ".join(_texts(app, "caption"))
    assert f"저장본 r{saved.revision.revision_no}" in captions
    assert "저장본과 같음" in captions
    assert "표에서 고친 값은" in captions

    name = current_data_file_name(
        "equipment_master", latest_snapshot=saved, edited=False, today=date(2026, 9, 24)
    )
    # 일정 리비전 번호(r) · 공통 대장 번호(c). 시나리오 이름을 주면 그 앞에 붙는다(빈칸은 `_`).
    assert name == "equipment_master_r1_c1_20260924.csv"
    named = current_data_file_name(
        "equipment_master",
        latest_snapshot=saved,
        edited=False,
        today=date(2026, 9, 24),
        scenario_name="셋업 실무/2차",
    )
    assert named == "equipment_master_셋업_실무_2차_r1_c1_20260924.csv"
    edited_name = current_data_file_name(
        "equipment_master", latest_snapshot=None, edited=True, today=date(2026, 9, 24)
    )
    assert edited_name == "equipment_master_r0_edited_20260924.csv"


def test_pasting_the_exported_current_data_back_round_trips_through_the_tab(
    tmp_path: Path,
) -> None:
    """내려받은 것을 고치지 않고 그대로 붙여넣어도 통과한다 — 이 기능의 합격선이다.

    내보낸 CSV 를 탭 구분 글로 바꿔(Excel 에서 복사하면 그 모양이다) 미리보기까지 돌리면
    「기존 대체」만 나오고 신규가 없다. 넣고 저장해도 저장소가 바뀐 것이 없다고 리비전을 만들지
    않는다.
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

    _put(app)
    _save(app)
    latest_id = repository.latest_revision_id()
    assert latest_id is not None
    latest = repository.load_snapshot(latest_id)
    # 그대로 붙여넣으면 바뀐 것이 없다 — 빈 리비전을 만들지 않는다(결정 모음).
    assert latest.revision.revision_no == 1
    assert NOTHING_SAVED_MESSAGE in _texts(app, "info")
    assert_frame_equal(
        latest.equipment.reset_index(drop=True), master.reset_index(drop=True), check_dtype=False
    )


def test_current_data_downloads_say_when_the_buffer_differs_from_the_saved_revision(
    tmp_path: Path, grid: Calls
) -> None:
    """편집 버퍼가 저장본과 다르면 캡션이 「저장하지 않은 변경 포함」으로 바뀌고 단추 행 수도
    버퍼를 따른다. 내보내는 것이 저장본이 아니라 **지금 보는 편집본**임을 화면이 말한다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(
        empty_equipment_baseline(), _master(["EQ-01"]), empty_downtime_schedule(), note="원본"
    )
    app = _app(tmp_path / "equipment.duckdb")
    assert "저장본과 같음" in " ".join(_texts(app, "caption"))

    _preview(app, _master(["EQ-99"]).to_csv(index=False, sep="\t"))
    _put(app)

    assert "저장하지 않은 변경 포함" in " ".join(_texts(app, "caption"))
    assert "설비 마스터 현재 데이터 · 2행" in _download_labels(app)


def test_current_data_downloads_reuse_the_bytes_until_the_buffer_changes(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """고친 것이 없으면 회차마다 CSV 를 다시 만들지 않는다(점검 A9·개편 명세 8장) — 저장본과 같은
    표는 리비전 캐시의 바이트를 쓰고, 편집본 세대가 같은 동안은 세션 메모다. 고친 표만 한 번
    직렬화한다."""
    from capa_simulation.components import equipment_data_workspace as workspace
    from capa_simulation.components.table_toolbar import render_csv_download as original_download
    from capa_simulation.services.equipment_csv import equipment_csv_bytes as original_bytes

    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    saved_master = _master(["EQ-01", "EQ-02"])
    repository.save_snapshot(
        empty_equipment_baseline(), saved_master, empty_downtime_schedule(), note="원본"
    )
    serialized: list[int] = []
    captured: dict[str, bytes] = {}

    def counting(frame: pd.DataFrame) -> bytes:
        serialized.append(len(frame))
        return original_bytes(frame)

    def capturing(*, data: bytes, file_name: str, key: str | None = None, label: str = "") -> None:
        if key is not None:
            captured[key] = data
        original_download(data=data, file_name=file_name, key=key, label=label)

    monkeypatch.setattr(workspace, "equipment_csv_bytes", counting)
    monkeypatch.setattr(workspace, "render_csv_download", capturing)
    app = _app(path)
    key = "equipment_master_current_download_v1"

    assert serialized == []
    assert captured[key] == original_bytes(saved_master)
    _ok(app.run())
    assert serialized == []

    load(app, [], kind="all")
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "담당자", "text": "담당B"})
    # 고친 표(편집본 설비 마스터) 하나만 한 번 직렬화한다. 견줄 저장본 쪽은 리비전 캐시다.
    assert serialized == [2]
    assert captured[key] == original_bytes(app.session_state[BUFFER_KEY][1])
    assert "저장하지 않은 변경 포함" in " ".join(_texts(app, "caption"))
    _ok(app.run())
    assert serialized == [2]


def test_the_history_list_follows_the_latest_revision_without_rereading(tmp_path: Path) -> None:
    """저장 이력 목록은 최신 리비전 id 를 키로 캐시한다 — 새로 저장하면 새 키라 목록이 는다."""
    from capa_simulation.persistence.equipment_cache import load_equipment_revision_summaries

    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    assert load_equipment_revision_summaries(str(path), None) == ()
    first = repository.save_snapshot(
        empty_equipment_baseline(), _master(["EQ-01"]), empty_downtime_schedule(), note="첫"
    )
    listed = load_equipment_revision_summaries(str(path), first.revision.revision_id)
    assert [item.note for item in listed] == ["첫"]

    second = repository.save_snapshot(
        empty_equipment_baseline(),
        _master(["EQ-01", "EQ-02"]),
        empty_downtime_schedule(),
        note="둘",
    )
    listed = load_equipment_revision_summaries(str(path), second.revision.revision_id)
    assert [item.note for item in listed] == ["둘", "첫"]
    assert [item.revision_no for item in listed] == [2, 1]


def test_pasting_a_unit_row_over_saved_modules_names_both_sides_and_the_way_out(
    tmp_path: Path,
) -> None:
    """저장본에 모듈 행 12A·12B(Main 설비 12)가 있을 때 설비 행 12 를 붙여넣고 미리본다(점검 A3).

    오류는 붙여넣은 설비 행과 저장된 모듈 행을 **출처와 함께** 적고, 붙여넣기로는 저장된 행을 지울
    수 없다고 말한다 — 예전 문구는 「설비 행을 지우고 모듈 행만 남기세요: ['SMP-DAF-12']」라
    붙여넣은 바로 그 행을 가리켰다.
    """
    import csv
    import io

    from capa_simulation.services.equipment_contract import PARENT_EQUIPMENT_COLUMN
    from capa_simulation.services.equipment_csv import equipment_csv_bytes

    repository = _repository(tmp_path / "equipment.duckdb")
    modules = _master(["SMP-DAF-12A", "SMP-DAF-12B"])
    modules[PARENT_EQUIPMENT_COLUMN] = "SMP-DAF-12"
    repository.save_snapshot(
        empty_equipment_baseline(), modules, empty_downtime_schedule(), note="모듈 행"
    )
    app = _open_import(_app(tmp_path / "equipment.duckdb"))
    rows = csv.reader(io.StringIO(equipment_csv_bytes(_master(["SMP-DAF-12"])).decode("utf-8-sig")))
    app.text_area(key=CLIPBOARD_KEY).set_value("\n".join("\t".join(row) for row in rows))
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())

    errors = _texts(app, "error")
    assert len(errors) == 1, errors
    assert "설비 행 SMP-DAF-12(붙여넣기) · 모듈 행 SMP-DAF-12A, SMP-DAF-12B(편집본)" in errors[0], (
        errors[0]
    )
    assert "붙여넣기는 이미 있는(편집본의) 행을 지우지 않습니다" in errors[0]
    assert PREVIEW_KEY not in app.session_state


def _collision_review(buffer: pd.DataFrame, pasted: pd.DataFrame) -> str:
    """붙여넣기 미리보기가 낸 충돌 문구(설비 마스터). 충돌이 없으면 실패한다."""
    from capa_simulation.services.equipment_csv import equipment_csv_bytes

    with pytest.raises(ValueError, match="Main 설비") as raised:
        build_import_review(
            "설비 마스터",
            equipment_csv_bytes(pasted),
            (empty_equipment_baseline(), buffer, empty_downtime_schedule()),
            floor_canvases={},
        )
    return str(raised.value)


def test_paste_review_marks_names_by_where_they_already_are() -> None:
    """출처는 붙여넣기 **전** 편집본과 견준다(리뷰 후속).

    - 편집본에 설비 행 X 와 모듈 행 X-A 가 함께 있고(검증 전 편집본) X 를 다시 붙여넣으면 X 는
      「붙여넣기·편집본」이다 — 붙여넣을 표에서만 빼면 다시 막힌다.
    - 같은 편집본에 무관한 호기만 붙여넣으면 충돌은 편집본 안의 것이다 — 붙여넣기 안내를 붙이지
      않고 편집본에서 고치라고만 한다.
    """
    from capa_simulation.services.equipment_contract import PARENT_EQUIPMENT_COLUMN

    unit = _master(["EQ-X"])
    module = _master(["EQ-X-A"])
    module[PARENT_EQUIPMENT_COLUMN] = "EQ-X"
    other = _master(["EQ-OTHER"])
    buffer = pd.concat([unit, module, other], ignore_index=True)

    again = _collision_review(buffer, unit)
    assert "설비 행 EQ-X(붙여넣기·편집본) · 모듈 행 EQ-X-A(편집본)" in again, again
    assert "두 곳 모두에서 빼야 합니다" in again

    unrelated = _collision_review(buffer, other)
    assert "설비 행 EQ-X(편집본) · 모듈 행 EQ-X-A(편집본)" in unrelated, unrelated
    assert "붙여넣기 전 편집본에 이미 있던 충돌입니다" in unrelated
    assert "붙여넣기는" not in unrelated


def test_the_change_memo_is_cleared_after_a_save_and_not_reused(
    tmp_path: Path, grid: Calls
) -> None:
    """저장한 메모는 칸에서 비워진다. 그대로 남으면 다음 리비전에 말없이 다시 실렸다
    (2026-10-05 E2E — r4 와 r5 가 같은 메모). 저장 콜백이 다음 회차 칸 앞에서 빈 값을 적는다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(
        empty_equipment_baseline(), _master(["EQ-01"]), empty_downtime_schedule(), note="원본"
    )
    app = _app(tmp_path / "equipment.duckdb")
    load(app, [], kind="all")
    # 바뀐 것 없는 저장은 리비전을 만들지 않으므로(결정 모음) 저장마다 공통 칸 하나를 고친다.
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "담당자", "text": "담당 1"})
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    app.text_input(key=NOTE_KEY).input("M1 메모")
    _save(app)
    assert not app.error, _texts(app, "error")

    memo = app.text_input(key=NOTE_KEY)
    assert memo.value == ""
    assert repository.list_revisions()[0].note == "M1 메모"

    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "담당자", "text": "담당 2"})
    _save(app)
    assert not app.error, _texts(app, "error")
    assert repository.list_revisions()[0].note is None


def _small_editor_key(app: AppTest, key: str) -> str:
    generation_key = f"{key}__generation"
    generation = app.session_state[generation_key] if generation_key in app.session_state else 0
    return f"{key}__g{generation}" if generation else key


def test_blank_cells_in_the_small_editors_render_empty_not_none(tmp_path: Path) -> None:
    """결측 칸은 빈칸이다. 기본값(`placeholder=None`)이면 Streamlit 이 "None" 글자를 그린다."""
    repository = _repository(tmp_path / "equipment.duckdb")
    repository.save_snapshot(
        empty_equipment_baseline(), _master(["EQ-01"]), empty_downtime_schedule(), note="원본"
    )
    app = _app(tmp_path / "equipment.duckdb")
    for table, key in (
        ("기존 보유대수", BASELINE_EDITOR_KEY),
        ("비가동 일정", DOWNTIME_EDITOR_KEY),
    ):
        app.session_state[TABLE_KEY] = table
        _ok(app.run())
        widget = _small_editor_key(app, key)
        protos = [
            node.proto
            for node in app._tree
            if str(getattr(getattr(node, "proto", None), "id", "")).endswith(f"-{widget}")
        ]
        assert protos, widget
        for proto in protos:
            assert proto.HasField("placeholder")
            assert proto.placeholder == ""


def test_a_small_editor_apply_on_the_run_that_saw_someone_elses_save_is_not_applied(
    tmp_path: Path,
) -> None:
    """다른 사람이 저장한 직후의 작은 편집표 제출은 옛 편집본 위의 것이다 — 새 저장본에 얹지 않고
    그 사실을 알린다(표 출납은 `base` 대조로 같은 규칙 — `test_equipment_master_tab_scenarios`)."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_snapshot(
        empty_equipment_baseline(), _master(["OLD-001"]), empty_downtime_schedule()
    )
    app = _app(path)
    app.session_state[TABLE_KEY] = "비가동 일정"
    _ok(app.run())
    tables = BrowserTables(app, forms=True)
    tables.add(
        _small_editor_key(app, DOWNTIME_EDITOR_KEY),
        {"설비명": "OLD-001", "비가동유형": "PM", "시작일": "2026-11-03"},
    )
    _ok(tables.run())
    repository.save_snapshot(
        empty_equipment_baseline(),
        _master(["OLD-001", "NEW-002"]),
        empty_downtime_schedule(),
        note="남",
    )
    clear_equipment_repository()

    app.button(key="equipment_downtime_apply_v1").click()
    _ok(tables.run())

    assert any("반영하지 않았습니다" in text for text in _texts(app, "error"))
    assert app.session_state[BUFFER_KEY][2].empty
    assert app.session_state[BUFFER_KEY][1]["설비명"].tolist() == ["OLD-001", "NEW-002"]
    assert len(repository.list_revisions()) == 2


def _location_choices(grid: Calls) -> tuple[list[str], list[str]]:
    """표 data 의 `동`·`층` 칸 고르는 값."""
    columns = {column["name"]: column for column in last(grid, emg.GRID_KEY)["columns"]}
    return list(columns["동"]["options"]), list(columns["층"]["options"])


def _located_master(rows: list[tuple[str, str | None, str | None]]) -> pd.DataFrame:
    frame = _master([name for name, _, _ in rows])
    frame["동"] = [building for _, building, _ in rows]
    frame["층"] = [floor for _, _, floor in rows]
    return frame


def test_inactive_floors_leave_the_location_choices_but_present_values_stay(
    tmp_path: Path, grid: Calls
) -> None:
    """Space 에서 끈 층은 표 `동`·`층` 칸 고르는 값에서 칸 단위로 빠진다 — 6개 층을 다 끈 동, 다섯
    동 모두에서 끈 층. 표에 이미 있는 값은 남는다. 비활성 층으로 옮긴 호기는 탭 머리 경고만 서고
    저장은 된다(저장 검사 그대로, S5)."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_snapshot(
        empty_equipment_baseline(),
        _located_master([("EQ-C4", "C4", "1F"), ("EQ-NONE", None, None)]),
        empty_downtime_schedule(),
    )
    inactive = {("C5", floor): "NOT_LINE" for floor in ("1F", "2F", "3F", "4F", "5F", "6F")}
    inactive |= {(building, "6F"): "UNUSED" for building in ("C1", "C2", "C3", "C4")}
    inactive[("C1", "3F")] = "UNUSED"
    repository.save_floor_states(inactive, expected_version=0, source="test")
    clear_equipment_repository()
    app = _app(path)

    buildings, floors = _location_choices(grid)
    assert buildings == ["C1", "C2", "C3", "C4"]
    assert floors == ["1F", "2F", "3F", "4F", "5F"]

    # 붙여넣기로 C5 6F 에 둔 호기 — 그 값은 고르는 값에 남고, 경고가 서고, 저장은 된다.
    _preview(
        app,
        _located_master([("EQ-C4", "C4", "1F"), ("EQ-NONE", "C5", "6F")]).to_csv(
            index=False, sep="\t"
        ),
    )
    _put(app)
    assert any(
        "비활성 층으로 옮긴 호기 1대" in text and "C5 6F 생산라인 아님" in text
        for text in _texts(app, "warning")
    )
    buildings, floors = _location_choices(grid)
    assert "C5" in buildings and "6F" in floors
    _save(app)
    assert not app.error, _texts(app, "error")
    assert len(repository.list_revisions()) == 2


def test_the_inactive_floor_warning_blocks_the_tildes_of_the_moved_unit(
    tmp_path: Path, grid: Calls
) -> None:
    """비활성 층으로 옮긴 호기 경고는 서비스가 지은 글이라 호기 이름을 날로 담는다 — 경고 상자
    (마크다운)에서 「DA~21~R」 의 가운데가 지움선이 됐다(2026-10-26 E2E r5). 그리는 자리에서
    막는다."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    repository.save_snapshot(
        empty_equipment_baseline(),
        _located_master([("EQ-C4", "C4", "1F"), ("DA~21~R", "C4", "2F")]),
        empty_downtime_schedule(),
    )
    repository.save_floor_states({("C5", "6F"): "NOT_LINE"}, expected_version=0, source="test")
    clear_equipment_repository()
    app = _app(path)

    _preview(
        app,
        _located_master([("EQ-C4", "C4", "1F"), ("DA~21~R", "C5", "6F")]).to_csv(
            index=False, sep="\t"
        ),
    )
    _put(app)

    warnings = [text for text in _texts(app, "warning") if "비활성 층으로 옮긴 호기" in text]
    assert warnings, _texts(app, "warning")
    assert all("DA\\~21\\~R" in text and "DA~21~R" not in text for text in warnings), warnings


def test_the_discarded_notice_blocks_the_tildes_of_the_dropped_units() -> None:
    """남의 저장으로 편집본을 다시 세운 알림(알림 칸 — 마크다운)은 공통 대장에서 빠진 호기 이름을
    날로 실어 「DA~21~R」 의 가운데가 지움선이 됐다(2026-10-26 E2E r5 와 같은 결함류). 막는다."""
    notice = discarded_notice(
        "공통 r3",
        overlay_dropped=0,
        reapplied=ReappliedLayout(equipment=pd.DataFrame(), reapplied=1, dropped=("DA~21~R",)),
    )

    assert "빠진 호기 1대(DA\\~21\\~R)의 편집은 뺐습니다" in notice, notice


def test_the_reapplied_notice_lists_the_dropped_renames() -> None:
    """E2E r6 — 위치는 다시 얹고 그 호기의 Space 이름 바꿈은 버렸는데 알림이 버린 것에 이름 바꿈을
    적지 않아, 이름 바꿈도 남았다고 읽혔다. 버린 편집에 「이름 바꿈 n건」 을 적는다."""
    moved = ReappliedLayout(equipment=pd.DataFrame(), reapplied=1)

    notice = discarded_notice("공통 대장 r8", overlay_dropped=1, reapplied=moved, renames_dropped=1)
    plain = discarded_notice("공통 대장 r8", overlay_dropped=1, reapplied=moved)

    assert "그 위에 다시 얹었습니다" in notice, notice
    assert "(설비 마스터 칸·이름 바꿈 1건·도면 요소·Main 설비명 위치)은 버렸습니다" in notice, (
        notice
    )
    assert "이름 바꿈" not in plain, plain


def test_the_discarded_notice_names_the_dropped_units_when_nothing_was_reapplied() -> None:
    """E2E r6 — 저장 안 한 가정 배치 편집이 남이 지운 호기에만 있었으면 다시 얹은 것은 0대다. 그
    갈래도 빠진 호기와 그 까닭을 적고, 이제 없는 호기를 「최신 위에서 다시 옮기세요」 라 하지
    않는다. 그 밖의 버린 가정 배치 편집(새 호기 자리 등)이 있으면 그 수만 다시 옮기라고 한다."""
    gone = ReappliedLayout(equipment=pd.DataFrame(), reapplied=0, dropped=("샘플1",))

    notice = discarded_notice("공통 대장 r8", overlay_dropped=1, reapplied=gone)

    assert "버리고 최신 저장본으로 다시 열었습니다" in notice, notice
    assert "그 사이 공통 대장에서 빠진 호기 1대(샘플1)의 편집은 뺐습니다" in notice, notice
    assert "다시 옮기세요" not in notice and "1대도 버렸습니다" not in notice, notice

    more = discarded_notice("공통 대장 r8", overlay_dropped=3, reapplied=gone)
    assert "빠진 호기 1대(샘플1)의 편집은 뺐습니다" in more, more
    assert "그 밖의 가정 배치 편집 2대도 버렸습니다 — 최신 위에서 다시 옮기세요." in more, more


def test_history_filters_survive_a_trip_to_summary(tmp_path: Path) -> None:
    """저장 이력의 조회 조건(공정소분류·비가동유형·기간)과 조회 리비전은 보기 조건이다 — 탭 ① 은
    숨은 회차에 그리지 않으므로(개편 명세 2-3) Summary 에 갔다 와도 남는 것은
    `persist_state="session"` 덕이다."""
    path = tmp_path / "equipment.duckdb"
    equipment = _master(["EQ-A", "EQ-B"])
    downtime = prepare_downtime_schedule(
        pd.DataFrame(
            {
                "설비명": ["EQ-A"],
                "비가동유형": ["고장"],
                "시작일": [date(2026, 3, 2)],
                "종료일": [date(2026, 3, 9)],
            }
        ).reindex(columns=DOWNTIME_COLUMNS),
        equipment=equipment,
    )
    _repository(path).save_snapshot(empty_equipment_baseline(), equipment, downtime)
    app = _app(path)
    app.session_state[SIDE_KEY] = SIDE_HISTORY
    _ok(app.run())
    app.multiselect(key="equipment_history_process_filter_v3").set_value(["Die Attach"])
    app.multiselect(key="equipment_history_downtime_type_filter_v3").set_value(["고장"])
    app.date_input(key="equipment_history_event_range_v3").set_value(
        (date(2026, 3, 1), date(2026, 3, 31))
    )
    _ok(app.run())
    revision = app.selectbox(key="equipment_history_revision_id_v4").value

    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_SUMMARY_TAB
    _ok(app.run())
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    _ok(app.run())

    assert app.multiselect(key="equipment_history_process_filter_v3").value == ["Die Attach"]
    assert app.multiselect(key="equipment_history_downtime_type_filter_v3").value == ["고장"]
    assert app.date_input(key="equipment_history_event_range_v3").value == (
        date(2026, 3, 1),
        date(2026, 3, 31),
    )
    assert app.selectbox(key="equipment_history_revision_id_v4").value == revision
