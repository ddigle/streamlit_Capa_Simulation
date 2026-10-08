# Purpose: 호기 마스터 일부 열 붙여넣기가 붙여넣은 열만 바꾸고 검증·차단 규칙을 지키는지 검사한다.

"""호기 마스터 일부 열 붙여넣기(2026-10-08 사용자 요청).

`설비명` 은 꼭 있고 나머지 열은 바꿀 것만 넣는다. 기존 호기는 붙여넣은 열만 바뀌고, 새 호기는
지금 필요한 열이 다 있어야 하며, 검증은 병합된 전체 표에서 그대로 돈다. 미리보기 경계
(`build_import_review`)와 실제 화면 왕복(AppTest) 양쪽에서 본다.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from test_equipment_availability import _downtime, _equipment
from test_equipment_data_workspace import _app, _repository

from capa_simulation.components.equipment_data_workspace import (
    CLIPBOARD_KEY,
    IMPORT_SAVE_BUTTON_KEY,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    TARGET_KEY,
    ImportReview,
    build_import_review,
)
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_COLUMNS,
    OPTIONAL_EQUIPMENT_COLUMNS,
    empty_equipment_baseline,
)
from capa_simulation.services.equipment_csv import equipment_csv_bytes, read_equipment_update
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)

# 붙여넣기 미리보기의 맨 앞 세 칸.
INFO_COLUMNS = ["Import구분", "변경컬럼", "변경내용"]


def _current() -> pd.DataFrame:
    """EQ-01(환산비 1.5, 반입 2026-08-04)·EQ-02(설비이력 「셋업 중」) 두 호기."""
    raw = _equipment()
    raw.loc[0, "환산비"] = 1.5
    return prepare_equipment_master(raw)


def _review(payload: str | bytes, equipment: pd.DataFrame | None = None) -> ImportReview:
    equipment = _current() if equipment is None else equipment
    downtime = prepare_downtime_schedule(_downtime(), equipment=equipment)
    return build_import_review(
        "호기 마스터",
        payload,
        (empty_equipment_baseline(), equipment, downtime),
        floor_canvases={},
    )


def _row(frame: pd.DataFrame, name: str) -> pd.Series:
    row = frame.set_index("설비명").loc[name]
    assert isinstance(row, pd.Series)
    return row


def _tab(*rows: tuple[str, ...]) -> str:
    return "\n".join("\t".join(row) for row in rows)


# ------------------------------------------------------------------- 기존 호기: 붙여넣은 열만


def test_pasting_one_column_changes_only_that_column_of_existing_units() -> None:
    current = _current()

    review = _review(_tab(("설비명", "담당자"), ("EQ-01", "담당B")))

    saved = review.candidate[1]
    assert saved["설비명"].tolist() == ["EQ-02", "EQ-01"]
    assert _row(saved, "EQ-01")["담당자"] == "담당B"
    # 붙여넣지 않은 열 34개는 한 칸도 바뀌지 않는다(값과 dtype 모두).
    others = [column for column in EQUIPMENT_COLUMNS if column not in ("설비명", "담당자")]
    assert_frame_equal(
        saved.set_index("설비명").loc[["EQ-01", "EQ-02"], others],
        current.set_index("설비명").loc[["EQ-01", "EQ-02"], others],
    )
    # 미리보기는 붙여넣은 열만 견주고 보여 준다.
    assert review.changes.columns.tolist() == [*INFO_COLUMNS, "설비명", "담당자"]
    assert review.changes["Import구분"].tolist() == ["대체"]
    assert review.changes["변경컬럼"].tolist() == ["담당자"]
    assert review.changes["변경내용"].tolist() == ["담당자: 담당A → 담당B"]
    assert review.notices == (
        "붙여넣은 열 1개(담당자)만 바꿉니다 — 나머지 34개 열은 기존 호기의 값을 그대로 둡니다.",
    )
    assert review.cautions == ()


def test_unnormalized_buffer_values_in_kept_columns_are_not_reported_as_changes() -> None:
    """붙여넣지 않은 열은 견주지 않는다. 편집본(검증 전)의 「 hbm 」이 검증을 거쳐 「hbm」이
    되어도 그것은 붙여넣기가 바꾼 것이 아니다."""
    current = _current().astype({"사용기준": "object"})
    current.loc[0, "사용기준"] = " hbm "

    review = _review(_tab(("설비명", "Qual일정"), ("EQ-01", "2026-08-09")), current)

    assert review.changes["변경컬럼"].tolist() == ["변경 없음"]


def test_blank_cells_in_pasted_columns_clear_values_and_are_counted() -> None:
    review = _review(_tab(("설비명", "설비이력", "담당자"), ("EQ-02", "", "담당A")))

    assert pd.isna(_row(review.candidate[1], "EQ-02")["설비이력"])
    assert review.changes["변경내용"].tolist() == ["설비이력: 셋업 중 → (빈 값)"]
    assert len(review.cautions) == 1
    assert "기존 값 1칸을 지웁니다" in review.cautions[0]


def test_blank_conversion_ratio_falls_back_to_one_and_is_not_a_cleared_cell() -> None:
    review = _review(_tab(("설비명", "환산비"), ("EQ-01", "")))

    assert _row(review.candidate[1], "EQ-01")["환산비"] == 1.0
    assert review.changes["변경내용"].tolist() == ["환산비: 1.5 → 1.0"]
    assert review.cautions == ()


def test_csv_upload_takes_the_same_partial_path() -> None:
    current = _current()

    review = _review("설비명,담당자\nEQ-02,담당C\n".encode("utf-8-sig"))

    saved = review.candidate[1]
    assert _row(saved, "EQ-02")["담당자"] == "담당C"
    assert _row(saved, "EQ-02")["설비이력"] == "셋업 중"
    assert_series_equal(
        _row(saved, "EQ-01"), _row(current, "EQ-01"), check_names=False, check_dtype=False
    )
    assert "붙여넣은 열 1개(담당자)만 바꿉니다" in review.notices[0]


def test_old_header_names_still_map_in_a_partial_paste() -> None:
    """옛 이름 「호기」·「비고」는 설비명·설비이력이다."""
    review = _review(_tab(("호기", "비고"), ("EQ-01", "새 이력")))

    saved = review.candidate[1]
    assert _row(saved, "EQ-01")["설비이력"] == "새 이력"
    assert _row(saved, "EQ-01")["담당자"] == "담당A"
    assert review.changes.columns.tolist() == [*INFO_COLUMNS, "설비명", "설비이력"]


# ----------------------------------------------------------------------- 새 호기: 반만은 막는다


def test_a_new_unit_without_the_columns_a_new_unit_needs_blocks_the_whole_paste() -> None:
    payload = _tab(("설비명", "담당자"), ("EQ-01", "담당B"), ("EQ-NEW", "담당C"))

    with pytest.raises(ValueError) as raised:
        _review(payload)

    message = str(raised.value)
    assert "없는 설비명 1건(EQ-NEW)은 새 호기로 추가되는데" in message
    # 선택 컬럼 밖 30개 중 붙여넣은 설비명·담당자를 뺀 28개.
    assert "필요한 열 28개" in message and "공정소분류" in message
    assert "양식(전체 열)으로 따로 붙여넣으세요" in message
    assert "설비명이 맞는지 확인하세요" in message


def test_a_new_unit_with_every_required_column_is_added_and_optional_columns_stay_blank() -> None:
    new = _current().iloc[[0]].copy()
    new["설비명"] = "EQ-NEW"
    full = pd.read_csv(BytesIO(equipment_csv_bytes(new)), dtype="object", keep_default_na=False)
    payload = full.drop(columns=list(OPTIONAL_EQUIPMENT_COLUMNS)).to_csv(sep="\t", index=False)

    review = _review(payload)

    assert review.changes["Import구분"].tolist() == ["신규"]
    added = _row(review.candidate[1], "EQ-NEW")
    assert added["공정소분류"] == "Process-A"
    assert all(pd.isna(added[column]) for column in OPTIONAL_EQUIPMENT_COLUMNS)
    assert "새 호기 1건은 그 열이 빈칸입니다" in review.notices[0]


# ------------------------------------------------------------- 병합된 전체 표에서 검증이 돈다


def test_validation_uses_the_kept_values_of_the_existing_unit() -> None:
    """반입일정은 붙여넣지 않았다 — 기존 값(2026-08-04)으로 반출일정 순서를 본다."""
    with pytest.raises(ValueError, match=r"반출일정은 반입일정보다 빠를 수 없습니다: \['EQ-01'\]"):
        _review(_tab(("설비명", "반출일정"), ("EQ-01", "2026-08-01")))


def test_a_rule_broken_only_in_the_merged_table_still_blocks() -> None:
    """EQ-02 를 EQ-01 의 모듈로 붙여넣는다. 붙여넣은 표만 보면 EQ-01 이 없어 문제가 없고,
    편집본과 합친 표에서야 설비 행 EQ-01 과 그 모듈 행이 함께 있다."""
    with pytest.raises(ValueError) as raised:
        _review(_tab(("설비명", "Main 설비"), ("EQ-02", "EQ-01")))

    message = str(raised.value)
    assert "Main 설비는 다른 행의 설비명과 같을 수 없습니다" in message
    assert "설비 행 EQ-01(편집본) · 모듈 행 EQ-02(붙여넣기·편집본)" in message


def test_invalid_values_in_pasted_columns_are_rejected_as_in_a_full_paste() -> None:
    with pytest.raises(ValueError, match="보관유무는 Y 또는 N이어야 합니다"):
        _review(_tab(("설비명", "보관유무"), ("EQ-01", "예")))


# ------------------------------------------------------------------------------ 머리글


def test_the_equipment_name_column_is_required() -> None:
    with pytest.raises(ValueError, match="설비명 열이 꼭 있어야 합니다"):
        _review(_tab(("공정소분류", "담당자"), ("Process-A", "담당B")))


def test_a_paste_with_nothing_but_the_equipment_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="설비명 말고 바꿀 열이 없습니다"):
        _review("설비명\nEQ-01\n".encode("utf-8-sig"))


def test_a_misspelled_header_in_a_partial_paste_is_rejected_with_a_hint() -> None:
    """일부 열만 붙여넣을 때 이름이 틀린 열을 빼고 읽으면 그 열이 바뀌지 않는다 — 막는다."""
    payload = _tab(("설비명", "반입일정", "Qual일졍"), ("EQ-01", "2026-08-05", "2026-08-10"))

    with pytest.raises(ValueError) as raised:
        _review(payload)

    message = str(raised.value)
    assert "호기 마스터에 없는 열이 있습니다: 「Qual일졍」(「Qual일정」?)" in message
    assert "그 열을 빼고 다시 붙여넣으세요" in message


def test_an_unknown_header_in_a_full_paste_is_skipped_with_a_notice() -> None:
    """필수 열이 다 있으면 모르는 열은 읽지 않고 넘긴다 — 다만 알린다."""
    current = _current()
    full = pd.read_csv(BytesIO(equipment_csv_bytes(current)), dtype="object", keep_default_na=False)
    full["확인"] = "o"

    review = _review(full.to_csv(sep="\t", index=False))

    assert review.notices == ("호기 마스터에 없는 열 「확인」은 읽지 않았습니다.",)
    assert review.changes["Import구분"].tolist() == ["대체", "대체"]
    assert review.changes["변경컬럼"].tolist() == ["변경 없음", "변경 없음"]


def test_an_empty_trailing_column_from_the_excel_range_is_ignored() -> None:
    review = _review("설비명\t담당자\t\nEQ-01\t담당B\t\n")

    assert _row(review.candidate[1], "EQ-01")["담당자"] == "담당B"
    assert review.changes.columns.tolist() == [*INFO_COLUMNS, "설비명", "담당자"]


def test_rows_without_an_equipment_name_are_dropped_like_in_a_full_paste() -> None:
    paste = read_equipment_update(
        _tab(("설비명", "담당자"), ("EQ-01", "담당B"), ("", "안내 행")), _current()
    )

    assert paste.rows["설비명"].tolist() == ["EQ-01"]
    assert paste.columns == ("설비명", "담당자")
    assert len(paste.kept_columns) == len(EQUIPMENT_COLUMNS) - 2


# ------------------------------------------------------------------------- 화면 왕복(AppTest)


def test_a_partial_paste_is_previewed_and_saved_leaving_the_other_columns_alone(
    tmp_path: Path,
) -> None:
    """저장본 위에 「설비명 + 설비이력」만 붙여넣고 저장하면, 새 리비전의 나머지 열은 저장본과
    같다 — 이 기능의 합격선이다."""
    path = tmp_path / "equipment.duckdb"
    repository = _repository(path)
    original = repository.save_snapshot(
        empty_equipment_baseline(),
        _current(),
        prepare_downtime_schedule(_downtime(), equipment=_current()),
        note="원본",
    )
    app = _app(path)
    app.selectbox(TARGET_KEY).set_value("호기 마스터")
    app.text_area(CLIPBOARD_KEY).set_value(
        _tab(("설비명", "설비이력"), ("EQ-01", "10월 점검"), ("EQ-02", "셋업 완료"))
    )
    app.button(PREVIEW_BUTTON_KEY).click().run()

    assert not app.exception
    assert not app.error
    review = app.session_state[PREVIEW_KEY]
    assert review.changes["변경컬럼"].tolist() == ["설비이력", "설비이력"]
    infos = [str(item.value) for item in app.info]
    assert any("붙여넣은 열 1개(설비이력)만 바꿉니다" in text for text in infos), infos

    app.button(IMPORT_SAVE_BUTTON_KEY).click().run()

    assert not app.exception
    assert not app.error
    latest_id = repository.latest_revision_id()
    assert latest_id is not None and latest_id != original.revision.revision_id
    saved = repository.load_snapshot(latest_id).equipment.set_index("설비명").sort_index()
    before = (
        repository.load_snapshot(original.revision.revision_id)
        .equipment.set_index("설비명")
        .sort_index()
    )
    assert saved["설비이력"].tolist() == ["10월 점검", "셋업 완료"]
    assert_frame_equal(saved.drop(columns=["설비이력"]), before.drop(columns=["설비이력"]))
