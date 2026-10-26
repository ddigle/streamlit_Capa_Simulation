# Purpose: 설비 마스터 일부 열 붙여넣기가 붙여넣은 열만 바꾸고 검증·차단 규칙을 지키는지 검사한다.

"""설비 마스터 일부 열 붙여넣기(2026-10-08 사용자 요청).

`설비명` 은 꼭 있고 나머지 열은 바꿀 것만 넣는다. 기존 호기는 붙여넣은 열만 바뀌고, 새 호기는
지금 필요한 열이 다 있어야 하며, 검증은 병합된 전체 표에서 그대로 돈다. 미리보기 경계
(`build_import_review`)와 실제 화면 왕복(AppTest — 설비 마스터 탭 「엑셀·CSV로 한꺼번에」 →
「편집본에 넣기」 → 「리비전 저장」) 양쪽에서 본다.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from test_equipment_availability import _downtime, _equipment
from test_equipment_data_workspace import _app, _preview, _put, _repository, _save
from test_equipment_master_columns import _old36_layout

from capa_simulation.components.equipment_data_workspace import (
    PREVIEW_KEY,
    ImportReview,
    build_import_review,
)
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_COLUMNS,
    OPTIONAL_EQUIPMENT_COLUMNS,
    empty_downtime_schedule,
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
    """`equipment` 는 붙여넣기 전 편집본이다. 검증을 통과하지 못하는 편집본(겹친 설비명)도 받도록
    그때는 비가동 일정을 비운다 — 비가동 검증이 편집본을 먼저 검증해 버린다."""
    if equipment is None:
        equipment = _current()
        downtime = prepare_downtime_schedule(_downtime(), equipment=equipment)
    else:
        downtime = empty_downtime_schedule()
    return build_import_review(
        "설비 마스터",
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


def _exported(equipment: pd.DataFrame) -> pd.DataFrame:
    """현재 데이터 내려받기를 Excel 에서 연 것과 같은 글자 표(전체 39열)."""
    return pd.read_csv(
        BytesIO(equipment_csv_bytes(equipment)), dtype="object", keep_default_na=False
    )


# ------------------------------------------------------------------- 기존 호기: 붙여넣은 열만


def test_pasting_one_column_changes_only_that_column_of_existing_units() -> None:
    current = _current()

    review = _review(_tab(("설비명", "담당자"), ("EQ-01", "담당B")))

    saved = review.candidate[1]
    # 바꾼 호기는 제자리다 — 행 차례는 공통 대장 내용이라 끝으로 옮기면 공통 리비전이 생긴다.
    assert saved["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert _row(saved, "EQ-01")["담당자"] == "담당B"
    # 붙여넣지 않은 열 37개는 한 칸도 바뀌지 않는다(값과 dtype 모두).
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
        "붙여넣은 열 1개(담당자)만 바꿉니다 — 나머지 37개 열은 기존 호기의 값을 그대로 둡니다.",
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
    # 선택 컬럼 밖 29개 중 붙여넣은 설비명·담당자를 뺀 27개.
    assert "필요한 열 27개" in message and "공정소분류" in message
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
    """반입일정은 붙여넣지 않았다 — 기존 값(2026-08-04)으로 정지일정 순서를 본다."""
    with pytest.raises(ValueError, match=r"정지일정은 반입일정보다 빠를 수 없습니다: \['EQ-01'\]"):
        _review(_tab(("설비명", "정지일정"), ("EQ-01", "2026-08-01")))


def test_a_collision_with_a_kept_value_names_the_edit_buffer_as_a_source() -> None:
    """붙여넣은 표 안의 충돌이라도 붙여넣지 않은 열(Main 설비)은 편집본 값이다.

    EQ-02 는 편집본에서 U1 의 모듈이다. 새 호기 U1 과 EQ-02 를 함께 붙여넣으면(Main 설비 열 없이)
    채운 표에서 부딪힌다 — EQ-02 는 편집본에도 있으니 (붙여넣기·편집본)이어야 한다. (붙여넣기)라고
    적으면 「붙여넣을 표에서 빼라」가 되는데 편집본 쪽 Main 설비 때문에 다시 막힌다.
    """
    raw = _equipment()
    raw["Main 설비"] = [None, "U1"]
    current = prepare_equipment_master(raw)
    exported = _exported(current)
    exported.loc[0, "설비명"] = "U1"
    payload = exported.drop(columns=list(OPTIONAL_EQUIPMENT_COLUMNS)).to_csv(sep="\t", index=False)

    with pytest.raises(ValueError) as raised:
        _review(payload, current)

    message = str(raised.value)
    assert "설비 행 U1(붙여넣기) · 모듈 행 EQ-02(붙여넣기·편집본)" in message, message
    assert "두 곳 모두에서 빼야 합니다" in message


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
    assert "설비 마스터에 없는 열이 있습니다: 「Qual일졍」(「Qual일정」?)" in message
    assert "그 열을 빼고 다시 붙여넣으세요" in message


@pytest.mark.parametrize(
    ("header", "column", "fix"),
    [
        ("반입실적(확인)", "반입실적", "「반입실적」으로"),
        ("Qual실적(확인)", "Qual실적", "「Qual실적」으로"),
        ("반입/Qual 이력(확인)", "반입/Qual 이력", "「반입/Qual 이력」으로"),
        ("메모 3(비고)", "메모3", "「메모3」으로"),
        ("모체호기(선택)", "Main 설비", "「Main 설비」로"),
    ],
)
def test_a_lookalike_optional_header_names_the_fix_with_the_particle_of_that_name(
    header: str, column: str, fix: str
) -> None:
    """이름이 닮은 선택 컬럼 머리글을 막는 글은 고칠 이름 뒤 「으로/로」 를 그 이름의 끝소리로
    고른다 — 「「반입실적」로 고치세요」 가 아니다(브라우저 E2E)."""
    full = _exported(_current()).rename(columns={column: header})

    with pytest.raises(ValueError) as raised:
        _review(full.to_csv(sep="\t", index=False))

    message = str(raised.value)
    assert message.startswith(f"설비 마스터의 {column} 열 이름이 다릅니다: ['{header}']")
    assert message.endswith(f" — 머리글을 {fix} 고치세요.")


def test_an_unknown_header_in_a_full_paste_is_skipped_with_a_notice() -> None:
    """38열이 모두 있으면 모르는 열은 어느 열의 오타일 수 없다 — 읽지 않고 넘기되 알린다."""
    full = _exported(_current())
    full["확인"] = "o"

    review = _review(full.to_csv(sep="\t", index=False))

    assert review.notices == ("설비 마스터에 없는 열 「확인」은 읽지 않았습니다.",)
    assert review.changes["Import구분"].tolist() == ["대체", "대체"]
    assert review.changes["변경컬럼"].tolist() == ["변경 없음", "변경 없음"]


@pytest.mark.parametrize("header", ["메모-1", "Memo1", "메모_1", "메모１"])
def test_a_misspelled_header_is_rejected_even_when_every_other_column_is_pasted(
    header: str,
) -> None:
    """붙여넣지 않은 열은 그대로 남으므로, 전체 열 붙여넣기라도 한 열의 이름이 틀리면 그 열이
    조용히 안 바뀐다 — 막는다. 「Memo1」처럼 글자가 닮지 않은 오타도 이름만으로는 가를 수 없다."""
    full = _exported(_current()).rename(columns={"메모1": header})
    full[header] = "새 메모"

    with pytest.raises(
        ValueError, match=re.escape(f"설비 마스터에 없는 열이 있습니다: 「{header}」")
    ):
        _review(full.to_csv(sep="\t", index=False))


def test_a_full_width_typo_points_at_the_column_it_looks_like() -> None:
    with pytest.raises(ValueError, match=re.escape("「메모１」(「메모1」?)")):
        _review(_tab(("설비명", "메모１"), ("EQ-01", "새 메모")))


def test_an_unrelated_extra_column_blocks_when_any_contract_column_is_missing() -> None:
    """옛 양식처럼 선택 컬럼이 빠진 붙여넣기에 상관없는 보조 열이 있어도 막는다 — 빠진 열의
    오타인지 이름만으로 알 수 없다. 그 열을 빼고 다시 붙여넣으면 된다."""
    full = _exported(_current()).drop(columns=["메모3"])
    full["확인"] = "o"

    with pytest.raises(ValueError, match="39개 열이 모두 있거나, 옛 36열 양식처럼"):
        _review(full.to_csv(sep="\t", index=False))


def test_an_extra_column_on_the_whole_old_36_column_form_is_skipped_with_a_notice() -> None:
    """옛 36열 양식을 통째로 붙여넣으면 빠진 열은 38열 개편이 더한 실적·상태 셋뿐이다. 그 표에 붙은
    보조 열(사내 엑셀의 「No.」)은 막지 않고 알림만 남긴다 — 개편 전에도 그랬다."""
    old = _old36_layout(_exported(_current()))
    old.insert(0, "No.", ["1", "2"])

    review = _review(old.to_csv(sep="\t", index=False))

    assert "설비 마스터에 없는 열 「No.」은 읽지 않았습니다." in review.notices
    assert review.changes["Import구분"].tolist() == ["대체", "대체"]
    assert review.changes["변경컬럼"].tolist() == ["변경 없음", "변경 없음"]


def test_an_extra_column_on_the_whole_old_38_column_form_is_skipped_and_keeps_the_memo() -> None:
    """설비 시나리오 전의 38열 표(시나리오 메모 없음)도 옛 36열 표처럼 보조 열을 알림으로 넘기고,
    붙여넣지 않은 시나리오 메모는 편집본 값 그대로다."""
    current = _current()
    current.loc[0, "시나리오 메모"] = "셋업 메모"
    old = _exported(current).drop(columns=["시나리오 메모"])
    old.insert(0, "No.", ["1", "2"])

    review = _review(old.to_csv(sep="\t", index=False), current)

    assert "설비 마스터에 없는 열 「No.」은 읽지 않았습니다." in review.notices
    assert review.changes["변경컬럼"].tolist() == ["변경 없음", "변경 없음"]
    assert review.candidate[1].set_index("설비명").loc["EQ-01", "시나리오 메모"] == "셋업 메모"


@pytest.mark.parametrize(("header", "column"), [("반입싫적", "반입실적"), ("Qual실젹", "Qual실적")])
def test_a_misspelled_new_column_on_the_old_36_column_form_still_blocks(
    header: str, column: str
) -> None:
    """옛 36열 꼴이어도 모르는 열이 빠진 실적·상태 열과 닮았으면 그 열의 오타다 — 넘기면 적은 실적이
    조용히 사라진다."""
    old = _old36_layout(_exported(_current()))
    old[header] = "2026-08-20"

    with pytest.raises(ValueError, match=re.escape(f"「{header}」(「{column}」?)")):
        _review(old.to_csv(sep="\t", index=False))


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("as_csv", [False, True])
def test_duplicate_headers_are_rejected_on_both_paths(as_csv: bool, partial: bool) -> None:
    """CSV 는 pandas 가 둘째 「담당자」를 「담당자.1」로 바꿔 읽는다. 붙여넣기처럼 막아야 한 열의
    값이 조용히 빠지지 않는다."""
    full = _exported(_current())
    if partial:
        full = full.loc[:, ["설비명", "담당자"]]
    full.insert(len(full.columns), "담당자_둘째", "새 담당")
    text = full.to_csv(index=False, sep="," if as_csv else "\t").replace("담당자_둘째", "담당자")
    entry = "CSV" if as_csv else "붙여넣기"

    with pytest.raises(
        ValueError, match=re.escape(f"설비 마스터 {entry} 컬럼명이 중복되었습니다: ['담당자']")
    ):
        _review(text.encode("utf-8-sig") if as_csv else text)


@pytest.mark.parametrize(
    "payload",
    [
        "설비명\t담당자\t\nEQ-01\t담당B\t\n",
        "설비명\t담당자\t\t\nEQ-01\t담당B\t\t\n",
        "설비명\t담당자\t\t\t\nEQ-01\t담당B\t\t \t\n",
        "설비명\t담당자\t \nEQ-01\t담당B\t\n",
        "설비명,담당자,\nEQ-01,담당B,\n".encode("utf-8-sig"),
        "설비명,담당자,,\nEQ-01,담당B,,\n".encode("utf-8-sig"),
        "설비명,담당자, , \nEQ-01,담당B,, \n".encode("utf-8-sig"),
    ],
    ids=["tab-1", "tab-2", "tab-3-space-cell", "tab-space-header", "csv-1", "csv-2", "csv-spaces"],
)
def test_empty_trailing_columns_from_the_excel_range_are_ignored(payload: str | bytes) -> None:
    """Excel 범위 끝에 딸려 온 빈 열(머리글도 값도 빈 열)은 몇 개든 뺀다 — 붙여넣기·CSV 같게."""
    review = _review(payload)

    assert _row(review.candidate[1], "EQ-01")["담당자"] == "담당B"
    assert review.changes.columns.tolist() == [*INFO_COLUMNS, "설비명", "담당자"]


def test_a_column_with_values_but_no_header_is_rejected() -> None:
    with pytest.raises(ValueError, match=re.escape("「(머리글 없음 · 3번째 열)」")):
        _review("설비명\t담당자\t\nEQ-01\t담당B\t값\n")


# ------------------------------------------------------------------- 편집본의 겹친 설비명


def _duplicated_buffer() -> pd.DataFrame:
    """EQ-01 이 두 행인 편집본(저장 전 편집). 둘째 행은 담당자가 다르다."""
    current = _current()
    second = current.loc[current["설비명"].eq("EQ-01")].copy()
    second["담당자"] = pd.Series("편집 중", index=second.index, dtype="string")
    return pd.concat([current, second], ignore_index=True)


def test_a_partial_paste_onto_a_duplicated_name_in_the_buffer_is_rejected() -> None:
    """두 행 중 어느 쪽 값으로 나머지 열을 채울지 모른다. 한쪽을 고르면 병합이 두 행을 다 바꿔
    중복이 조용히 사라지고 다른 행의 값을 잃는다."""
    with pytest.raises(ValueError) as raised:
        _review(_tab(("설비명", "반입일정"), ("EQ-01", "2026-08-05")), _duplicated_buffer())

    message = str(raised.value)
    assert "편집본(설비 마스터)에 같은 설비명이 둘 이상 있습니다: EQ-01" in message
    assert "설비 마스터 표에서 중복된 행을 먼저 정리한 뒤" in message


def test_a_duplicate_that_the_paste_does_not_touch_still_fails_the_merged_validation() -> None:
    with pytest.raises(ValueError, match=re.escape("설비명은 중복될 수 없습니다: ['EQ-01']")):
        _review(_tab(("설비명", "담당자"), ("EQ-02", "담당C")), _duplicated_buffer())


def test_a_full_paste_still_replaces_both_duplicated_rows() -> None:
    """모든 열을 붙여넣으면 채울 것이 없다 — 붙여넣은 행이 두 행을 대신한다(전체 열 대체)."""
    review = _review(_exported(_current()).to_csv(sep="\t", index=False), _duplicated_buffer())

    saved = review.candidate[1]
    assert saved["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert _row(saved, "EQ-01")["담당자"] == "담당A"


def test_a_partial_paste_onto_a_buffer_name_with_outer_spaces_replaces_that_unit() -> None:
    """편집본(검증 전)의 설비명이 「 EQ-01 」이어도 붙여넣은 「EQ-01」은 그 호기다.

    붙여넣기가 나머지 열을 채울 때는 앞뒤 공백을 떼고 맞췄는데, 병합·미리보기는 글자 그대로
    견주어 옛 행을 남겼다 — 그 둘이 검증에서 같은 이름이 되어 엉뚱한 「설비명 중복」으로 막혔다.
    """
    current = _current().astype({"설비명": "object"})
    current.loc[current["설비명"].eq("EQ-01"), "설비명"] = " EQ-01 "

    review = _review(_tab(("설비명", "담당자"), ("EQ-01", "담당B")), current)

    saved = review.candidate[1]
    assert sorted(saved["설비명"]) == ["EQ-01", "EQ-02"]
    assert _row(saved, "EQ-01")["담당자"] == "담당B"
    assert review.changes["Import구분"].tolist() == ["대체"]
    assert review.changes["변경컬럼"].tolist() == ["담당자"]


def test_a_new_name_that_differs_from_a_unit_only_in_case_is_flagged() -> None:
    """대소문자만 다른 설비명은 새 호기로 더하되 미리보기에서 경고한다 — Space 이름 바꾸기는
    대소문자·앞뒤 공백을 무시하고 겹침을 막으므로 같은 설비일 가능성이 크다."""
    variant = _current().iloc[[0]].copy()
    variant["설비명"] = "eq-01"

    review = _review(_exported(variant).to_csv(sep="\t", index=False))

    assert review.changes["Import구분"].tolist() == ["신규"]
    assert sorted(review.candidate[1]["설비명"]) == ["EQ-01", "EQ-02", "eq-01"]
    flagged = [caution for caution in review.cautions if "대소문자" in caution]
    assert len(flagged) == 1, review.cautions
    assert "eq-01(기존 EQ-01)" in flagged[0]


def test_a_partial_paste_of_a_case_variant_names_the_existing_unit() -> None:
    """일부 열만 붙여넣은 「eq-01」은 새 호기로 세어 막힌다. 그 오류가 대소문자만 다른 기존 호기를
    짚어야 설비명을 고쳐 다시 붙여넣는다."""
    with pytest.raises(ValueError) as raised:
        _review(_tab(("설비명", "담당자"), ("eq-01", "담당B")))

    message = str(raised.value)
    assert "없는 설비명 1건(eq-01)은 새 호기로 추가되는데" in message
    assert "대소문자만 다른 기존 호기: eq-01(기존 EQ-01)" in message


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
    _preview(app, _tab(("설비명", "설비이력"), ("EQ-01", "10월 점검"), ("EQ-02", "셋업 완료")))

    review = app.session_state[PREVIEW_KEY]
    assert review.changes["변경컬럼"].tolist() == ["설비이력", "설비이력"]
    infos = [str(item.value) for item in app.info]
    assert any("붙여넣은 열 1개(설비이력)만 바꿉니다" in text for text in infos), infos

    _put(app)
    _save(app)

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
