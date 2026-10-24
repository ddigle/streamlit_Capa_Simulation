# Purpose: 설비 마스터 39컬럼 계약·저장 매핑·0015·0023 마이그레이션·옛 머리 변환을 검증한다.

from pathlib import Path

import duckdb
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_equipment_availability import _baseline, _downtime, _equipment
from test_equipment_csv import _read_whole_master

from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import (
    DOWNTIME_DB_COLUMNS,
    EQUIPMENT_MASTER_DB_COLUMNS,
    DuckDBEquipmentRepository,
)
from capa_simulation.services.equipment_contract import (
    AREA_CODE_COLUMN,
    ARRIVAL_ACTUAL_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    DATE_COLUMNS,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    EQUIPMENT_KEY_COLUMNS,
    EXIT_SCHEDULE_COLUMNS,
    FLAG_COLUMNS,
    LEGACY_DOWNTIME_HEADER_ALIASES,
    LEGACY_EQUIPMENT_HEADER_ALIASES,
    OBSOLETE_EQUIPMENT_COLUMNS,
    OPTIONAL_EQUIPMENT_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_ACTUAL_COLUMN,
    QUAL_STATUS_COLUMN,
    REFERENCE_TEXT_COLUMNS,
    RELOCATION_DATE_COLUMN,
    SCHEDULE_STAGES,
    STOP_DATE_COLUMN,
    TRANSITION_EVENT_COLUMNS,
    UNIT_CONSISTENT_COLUMNS,
    rename_legacy_headers,
)
from capa_simulation.services.equipment_csv import (
    equipment_csv_bytes,
    read_downtime_clipboard,
    read_downtime_csv,
    read_equipment_update,
)
from capa_simulation.services.equipment_validation import prepare_equipment_master

# 2026-10-16 사용자 결정의 순서 그대로다.
SPEC_ORDER = (
    "Area Code",
    "공정대분류",
    "공정소분류",
    "Maker",
    "Model",
    "설비명",
    "공정구분",
    "투자Capa",
    "투자구분",
    "사용기준",
    "동",
    "층",
    "담당자",
    "X좌표",
    "Y좌표",
    "Xsize",
    "Ysize",
    "제진대일정",
    "물류일정",
    "반입일정",
    "반입실적",
    "반입상태",
    "Qual일정",
    "Qual실적",
    "Qual상태",
    "정지일정",
    "반출/이설일정",
    "시나리오 메모",
    "반입/Qual 이력",
    "호기이력",
    "설비이력",
    "보관유무",
    "기존설비여부",
    "레이아웃표시",
    "환산비",
    "Main 설비",
    "메모1",
    "메모2",
    "메모3",
)

# 2026-10-06 개편이 더한 선택 컬럼(0015)과 2026-10-16 개편이 더한 선택 컬럼(0023).
NEW_COLUMNS = ("투자Capa", "반입/Qual 이력", "메모1", "메모2", "메모3")
ACTUAL_COLUMNS = ("반입실적", "반입상태", "Qual실적")

# 개편 전 32컬럼 계약의 이름과 차례. 사내에 이 머리로 적은 파일이 남아 있다.
OLD_ORDER = (
    "호기",
    "공정대분류",
    "공정소분류",
    "라인구분",
    "활용구분",
    "투자기준",
    "담당자",
    "Maker",
    "모델",
    "분류1",
    "분류2",
    "분류3",
    "동",
    "층",
    "X좌표",
    "Y좌표",
    "Xsize",
    "Ysize",
    "제진대일정",
    "물류일정",
    "입고일정",
    "Qual일정",
    "확정상태",
    "반출일정",
    "이설일",
    "장기보관여부",
    "기존설비여부",
    "호기이력",
    "비고",
    "레이아웃표시",
    "환산비",
    "모체호기",
)

# 2026-10-06 개편의 36컬럼 계약. 사내에 이 머리로 적은 파일도 남아 있다.
OLD36_ORDER = (
    "구분",
    "공정대분류",
    "공정소분류",
    "Maker",
    "Model",
    "설비명",
    "공정구분",
    "투자Capa",
    "투자구분",
    "사용기준",
    "동",
    "층",
    "담당자",
    "설비가동현황",
    "X좌표",
    "Y좌표",
    "Xsize",
    "Ysize",
    "제진대일정",
    "물류일정",
    "반입일정",
    "Qual일정",
    "확정상태",
    "반출일정",
    "이설일정",
    "반입/Qual 이력",
    "호기이력",
    "설비이력",
    "보관유무",
    "기존설비여부",
    "레이아웃표시",
    "환산비",
    "Main 설비",
    "메모1",
    "메모2",
    "메모3",
)

# 새 이름 → 그 세대의 옛 이름. 같은 새 이름을 두 세대가 다른 옛 이름으로 불러(Area Code ←
# 분류1·구분, 반출/이설일정 ← 이설일·이설일정) 별칭표를 거꾸로 뒤집어서는 만들 수 없다.
TO_OLD32 = {
    "설비명": "호기",
    "공정구분": "라인구분",
    "투자구분": "활용구분",
    "Area Code": "분류1",
    "사용기준": "분류2",
    "Model": "모델",
    "반입일정": "입고일정",
    "Qual상태": "확정상태",
    "정지일정": "반출일정",
    "반출/이설일정": "이설일",
    "설비이력": "비고",
    "보관유무": "장기보관여부",
    "Main 설비": "모체호기",
}
TO_OLD36 = {
    "Area Code": "구분",
    "Qual상태": "확정상태",
    "정지일정": "반출일정",
    "반출/이설일정": "이설일정",
}


def _old_layout(frame: pd.DataFrame) -> pd.DataFrame:
    """새 계약 표를 옛 32컬럼 머리로 되돌린다. 새 컬럼은 버리고 투자기준·분류3 에 옛 값을 적는다."""
    old = frame.drop(columns=[*NEW_COLUMNS, *ACTUAL_COLUMNS]).rename(columns=TO_OLD32)
    old["투자기준"] = "322K"
    old["분류3"] = "가동"
    return old.loc[:, list(OLD_ORDER)]


def _old36_layout(frame: pd.DataFrame) -> pd.DataFrame:
    """새 계약 표를 10-06 개편의 36컬럼 머리로 되돌린다. 실적 컬럼은 빼고 설비가동현황을 적는다."""
    old = frame.drop(columns=list(ACTUAL_COLUMNS)).rename(columns=TO_OLD36)
    old["설비가동현황"] = "가동"
    return old.loc[:, list(OLD36_ORDER)]


def _text_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """비어 있는 새 컬럼은 float 로 만들어진다. 글자를 넣기 전에 글자 칸으로 바꾼다."""
    return frame.astype({column: "object" for column in (*NEW_COLUMNS, *ACTUAL_COLUMNS)})


# ------------------------------------------------------------------------------- 계약


def test_equipment_contract_follows_the_decided_order() -> None:
    assert EQUIPMENT_COLUMNS == SPEC_ORDER
    assert len(set(EQUIPMENT_COLUMNS)) == 39
    assert "투자기준" not in EQUIPMENT_COLUMNS
    assert "설비가동현황" not in EQUIPMENT_COLUMNS
    assert OBSOLETE_EQUIPMENT_COLUMNS == ("투자기준", "설비가동현황", "분류3")


def test_derived_constants_use_the_new_names() -> None:
    assert EQUIPMENT_ID_COLUMN == "설비명"
    assert EQUIPMENT_KEY_COLUMNS == ("설비명",)
    assert DOWNTIME_COLUMNS == ("설비명", "비가동유형", "시작일", "종료일", "상세사유", "비고")
    assert DOWNTIME_KEY_COLUMNS == ("설비명", "비가동유형", "시작일")
    assert TRANSITION_EVENT_COLUMNS[0] == "설비명"
    assert "Qual상태" in TRANSITION_EVENT_COLUMNS and "확정상태" not in TRANSITION_EVENT_COLUMNS
    assert PARENT_EQUIPMENT_COLUMN == "Main 설비"
    assert FLAG_COLUMNS == ("보관유무", "기존설비여부", "레이아웃표시")
    assert "반입일정" in DATE_COLUMNS and "입고일정" not in DATE_COLUMNS
    assert (AREA_CODE_COLUMN, STOP_DATE_COLUMN, RELOCATION_DATE_COLUMN) == (
        "Area Code",
        "정지일정",
        "반출/이설일정",
    )
    assert (ARRIVAL_ACTUAL_COLUMN, ARRIVAL_STATUS_COLUMN, QUAL_ACTUAL_COLUMN) == ACTUAL_COLUMNS
    assert QUAL_STATUS_COLUMN == "Qual상태"
    assert EXIT_SCHEDULE_COLUMNS == ("정지일정", "반출/이설일정")
    # 입고 단계 이름은 컬럼 이름과 따로 움직인다. 정지·반출/이설은 컬럼 이름을 따른다.
    assert ("반입일정", "입고") in SCHEDULE_STAGES
    assert ("정지일정", "정지") in SCHEDULE_STAGES
    assert ("반출/이설일정", "반출/이설") in SCHEDULE_STAGES
    for old in ("이설일정", "이설일", "반출일정"):
        assert old not in DATE_COLUMNS
    # 실적은 날짜 칸이지만 단계 전환이 아니다 — 넣으면 전환 이벤트가 늘어난다.
    assert {"반입실적", "Qual실적"} <= set(DATE_COLUMNS)
    assert not {"반입실적", "Qual실적"} & {column for column, _ in SCHEDULE_STAGES}
    assert UNIT_CONSISTENT_COLUMNS == (
        "공정소분류",
        "공정대분류",
        "공정구분",
        "투자구분",
        "동",
        "층",
    )
    # Area Code 는 모듈 일치 컬럼이 아니다 — 넣으면 모듈 행끼리 값이 다른 옛 리비전이 열리지 않는다.
    assert AREA_CODE_COLUMN not in UNIT_CONSISTENT_COLUMNS
    assert set(OPTIONAL_EQUIPMENT_COLUMNS) == {
        *NEW_COLUMNS,
        *ACTUAL_COLUMNS,
        "Main 설비",
        "시나리오 메모",
    }
    assert set(NEW_COLUMNS) <= set(REFERENCE_TEXT_COLUMNS)
    assert AREA_CODE_COLUMN in REFERENCE_TEXT_COLUMNS
    contract_columns = {*EQUIPMENT_COLUMNS, *DOWNTIME_COLUMNS}
    for derived in (DATE_COLUMNS, FLAG_COLUMNS, REFERENCE_TEXT_COLUMNS, UNIT_CONSISTENT_COLUMNS):
        assert set(derived) <= contract_columns


def test_legacy_alias_maps_land_on_contract_columns() -> None:
    assert set(LEGACY_EQUIPMENT_HEADER_ALIASES.values()) <= set(EQUIPMENT_COLUMNS)
    assert not set(LEGACY_EQUIPMENT_HEADER_ALIASES) & set(EQUIPMENT_COLUMNS)
    assert not set(LEGACY_EQUIPMENT_HEADER_ALIASES) & set(OBSOLETE_EQUIPMENT_COLUMNS)
    assert LEGACY_DOWNTIME_HEADER_ALIASES == {"호기": "설비명"}
    # 두 세대 옛 계약의 모든 컬럼은 그대로이거나, 새 이름이 있거나, 빠진 컬럼이다.
    for column in (*OLD_ORDER, *OLD36_ORDER):
        assert (
            column in EQUIPMENT_COLUMNS
            or column in LEGACY_EQUIPMENT_HEADER_ALIASES
            or column in OBSOLETE_EQUIPMENT_COLUMNS
        ), column
    # 시험이 옛 양식을 만드는 표와 별칭표가 같은 말을 한다.
    for new, old in (*TO_OLD32.items(), *TO_OLD36.items()):
        assert LEGACY_EQUIPMENT_HEADER_ALIASES[old] == new, old


def test_prepared_master_has_the_new_columns_in_order() -> None:
    prepared = prepare_equipment_master(_equipment())

    assert prepared.columns.tolist() == list(EQUIPMENT_COLUMNS)


# -------------------------------------------------------------------------- 옛 머리 변환


def test_old_csv_reads_into_the_new_columns_and_drops_obsolete_ones() -> None:
    current = prepare_equipment_master(_equipment())
    payload = _old_layout(current).to_csv(index=False).encode("utf-8-sig")
    notices: list[str] = []

    result = _read_whole_master(payload, notices=notices)

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert result.loc[1, "설비이력"] == "셋업 중"
    assert result.loc[0, "반입일정"] == pd.Timestamp("2026-08-04")
    assert result.loc[0, "투자구분"] == "양산"
    assert result["Qual상태"].tolist() == ["확정", "확정"]
    assert result["보관유무"].tolist() == ["N", "N"]
    # 옛 투자기준 값은 새 컬럼 투자Capa 로 넘어가지 않는다 — 별개의 컬럼이다.
    for column in (*NEW_COLUMNS, *ACTUAL_COLUMNS):
        assert result[column].isna().all(), column
    # 알림은 둘: 빠진 투자기준·분류3 한 줄씩. 옛 양식에 없는 새 열·실적 열은 붙여넣지 않은 열이라
    # 알림 없이 새 호기는 빈 칸이다(기존 호기는 그 값을 지킨다 — 아래 시험).
    assert len(notices) == 2
    assert "투자기준" in notices[0]
    assert "「분류3」" in notices[1] and "메모1" in notices[1]


def test_old_36_column_csv_reads_into_the_new_names_and_drops_the_status_column() -> None:
    """10-06 개편 양식(구분·설비가동현황·확정상태·반출일정·이설일정)도 값을 그대로 옮겨 읽는다."""
    raw = _text_columns(_equipment())
    raw[AREA_CODE_COLUMN] = "MI"
    raw.loc[0, STOP_DATE_COLUMN] = "2026-11-01"
    raw.loc[1, RELOCATION_DATE_COLUMN] = "2026-12-01"
    raw.loc[1, "메모1"] = "남길 메모"
    current = prepare_equipment_master(raw)
    old = _old36_layout(current)
    assert "설비가동현황" in old.columns and "Area Code" not in old.columns
    notices: list[str] = []

    result = _read_whole_master(old.to_csv(index=False).encode("utf-8-sig"), notices=notices)

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result[AREA_CODE_COLUMN].tolist() == ["MI", "MI"]
    assert result.loc[0, STOP_DATE_COLUMN] == pd.Timestamp("2026-11-01")
    assert result.loc[1, RELOCATION_DATE_COLUMN] == pd.Timestamp("2026-12-01")
    assert result[QUAL_STATUS_COLUMN].tolist() == ["확정", "확정"]
    assert result.loc[1, "메모1"] == "남길 메모"
    assert result.loc[:, list(ACTUAL_COLUMNS)].isna().all().all()
    # 알림은 하나: 빠진 설비가동현황(메모 열로 옮기라는 말과 함께). 실적 세 열은 알림 없이 빈 칸.
    assert len(notices) == 1
    assert "「설비가동현황」" in notices[0] and "메모1·메모2·메모3" in notices[0]


def test_old_clipboard_paste_converts_the_same_way() -> None:
    current = prepare_equipment_master(_equipment())
    for old in (_old_layout(current), _old36_layout(current)):
        csv_notices: list[str] = []
        notices: list[str] = []

        from_csv = _read_whole_master(
            old.to_csv(index=False).encode("utf-8-sig"), notices=csv_notices
        )
        result = _read_whole_master(old.to_csv(index=False, sep="\t"), notices=notices)

        assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
        assert result["설비명"].tolist() == ["EQ-01", "EQ-02"]
        assert_frame_equal(result, from_csv)
        assert notices and notices == csv_notices


def test_old_file_without_obsolete_columns_reads_without_notices_and_keeps_stored_values() -> None:
    """빠진 옛 컬럼만 지운 옛 양식은 알림 없이 읽힌다. 옛 양식에 없는 새 열·실적 열은 붙여넣지
    않은 열이라 새 호기는 빈 칸이고, 편집본에 있는 호기는 저장된 값을 그대로 지킨다."""
    current = prepare_equipment_master(_equipment())
    payload = (
        _old_layout(current)
        .drop(columns=["투자기준", "분류3"])
        .to_csv(index=False)
        .encode("utf-8-sig")
    )
    notices: list[str] = []

    result = _read_whole_master(payload, notices=notices)

    assert notices == []
    assert result["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert result.loc[:, list(NEW_COLUMNS)].isna().all().all()

    stored = _text_columns(current)
    stored.loc[0, "투자Capa"] = "322K"
    stored.loc[1, "메모1"] = "남길 메모"
    stored.loc[0, ARRIVAL_ACTUAL_COLUMN] = pd.Timestamp("2026-08-04")
    stored.loc[0, ARRIVAL_STATUS_COLUMN] = "완료"

    kept = read_equipment_update(payload, stored)

    assert kept.cleared_cells == 0
    assert kept.rows.loc[0, "투자Capa"] == "322K"
    assert kept.rows.loc[1, "메모1"] == "남길 메모"
    assert kept.rows.loc[0, ARRIVAL_ACTUAL_COLUMN] == pd.Timestamp("2026-08-04")
    assert kept.rows.loc[0, ARRIVAL_STATUS_COLUMN] == "완료"


def test_old_module_parent_column_keeps_grouping_modules() -> None:
    """옛 「모체호기」 열이 빈 칸으로 사라지면 모듈 행이 모두 따로 세어진다."""
    current = prepare_equipment_master(_equipment())
    current["Main 설비"] = "EQ-UNIT"
    old = _old_layout(current)

    result = _read_whole_master(old.to_csv(index=False).encode("utf-8-sig"))

    assert result["Main 설비"].tolist() == ["EQ-UNIT", "EQ-UNIT"]


@pytest.mark.parametrize("old_header", ["이설일", "이설일정"])
def test_relocation_date_from_an_old_header_keeps_its_value(old_header: str) -> None:
    """개편 전(이설일)·10-06 개편(이설일정) 머리의 값이 그대로 「반출/이설일정」으로 온다."""
    current = prepare_equipment_master(_equipment())
    current.loc[0, RELOCATION_DATE_COLUMN] = pd.Timestamp("2026-12-01")
    text = equipment_csv_bytes(current).decode("utf-8-sig")
    header, _, body = text.partition("\n")
    notices: list[str] = []

    result = _read_whole_master(
        f"{header.replace(RELOCATION_DATE_COLUMN, old_header)}\n{body}".encode("utf-8-sig"),
        notices=notices,
    )

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result.loc[0, RELOCATION_DATE_COLUMN] == pd.Timestamp("2026-12-01")
    assert pd.isna(result.loc[1, RELOCATION_DATE_COLUMN])
    # 이름만 바뀐 것이라 알림은 없다(빠진 컬럼·없는 선택 컬럼이 없다).
    assert notices == []


def test_relocation_old_header_also_converts_on_paste_and_in_the_old_layout() -> None:
    current = prepare_equipment_master(_equipment())
    current.loc[1, RELOCATION_DATE_COLUMN] = pd.Timestamp("2027-01-04")
    old = _old_layout(current)
    assert "이설일" in old.columns and RELOCATION_DATE_COLUMN not in old.columns

    pasted = _read_whole_master(old.to_csv(index=False, sep="\t"))

    assert pasted.loc[1, RELOCATION_DATE_COLUMN] == pd.Timestamp("2027-01-04")


def test_old_and_new_relocation_headers_together_are_rejected() -> None:
    current = prepare_equipment_master(_equipment())
    both = current.assign(이설일=current[RELOCATION_DATE_COLUMN])

    with pytest.raises(
        ValueError, match=r"옛 이름과 새 이름이 함께.*반출/이설일정 ← 반출/이설일정 · 이설일"
    ):
        _read_whole_master(both.to_csv(index=False).encode("utf-8-sig"))


@pytest.mark.parametrize(
    ("old", "new"),
    [("구분", "Area Code"), ("반출일정", "정지일정"), ("확정상태", "Qual상태")],
)
def test_a_36_column_name_next_to_its_new_name_is_rejected(old: str, new: str) -> None:
    current = prepare_equipment_master(_equipment())
    both = current.assign(**{old: current[new]})

    with pytest.raises(ValueError, match=rf"옛 이름과 새 이름이 함께.*{new} ← {new} · {old}"):
        _read_whole_master(both.to_csv(index=False).encode("utf-8-sig"))


def test_spacing_variants_of_new_and_old_names_are_accepted() -> None:
    current = prepare_equipment_master(_equipment())
    spaced = equipment_csv_bytes(current).decode("utf-8-sig")
    header, _, body = spaced.partition("\n")
    header = header.replace("Main 설비", "Main설비").replace("반입/Qual 이력", "반입/Qual이력")
    header = header.replace("Area Code", "AreaCode")

    result = _read_whole_master(f"{header}\n{body}".encode("utf-8-sig"))

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)


@pytest.mark.parametrize(
    ("contract", "variant"),
    [
        ("Main 설비", "MAIN 설비"),
        ("Main 설비", "main설비"),
        ("투자Capa", "투자CAPA"),
        ("투자Capa", "투자capa"),
        ("반입/Qual 이력", "반입/QUAL 이력"),
        ("Model", "MODEL"),
        ("Area Code", "AREA CODE"),
        ("Qual상태", "QUAL상태"),
    ],
)
def test_case_variants_of_latin_headers_keep_their_values(contract: str, variant: str) -> None:
    """영문이 든 선택 컬럼이 대소문자만 달라 버려지면 빈 칸으로 조용히 읽힌다."""
    current = _text_columns(prepare_equipment_master(_equipment()))
    current["Main 설비"] = "EQ-UNIT"
    current["투자Capa"] = "322K"
    current["반입/Qual 이력"] = "1차 반입"
    current["Model"] = "DEMO-M1"
    current["Area Code"] = "Main"
    text = equipment_csv_bytes(current).decode("utf-8-sig")
    header, _, body = text.partition("\n")
    header = header.replace(contract, variant)

    result = _read_whole_master(f"{header}\n{body}".encode("utf-8-sig"))

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result[contract].notna().all()
    assert result[contract].tolist() == current[contract].tolist()


def test_case_variant_lookalike_of_parent_column_is_named_instead_of_blanked() -> None:
    current = prepare_equipment_master(_equipment())
    renamed = current.rename(columns={"Main 설비": "MAIN 설비(선택)"})

    with pytest.raises(ValueError, match="Main 설비 열 이름이 다릅니다"):
        _read_whole_master(renamed.to_csv(index=False).encode("utf-8-sig"))


def test_misspelled_old_parent_column_is_named_instead_of_blanked() -> None:
    current = prepare_equipment_master(_equipment())
    old = _old_layout(current).rename(columns={"모체호기": "모체호기(선택)"})

    with pytest.raises(ValueError, match="Main 설비 열 이름이 다릅니다"):
        _read_whole_master(old.to_csv(index=False).encode("utf-8-sig"))


def test_old_and_new_name_for_the_same_column_together_are_rejected() -> None:
    frame = pd.DataFrame({"호기": ["A"], "설비명": ["B"]})

    with pytest.raises(ValueError, match="옛 이름과 새 이름이 함께"):
        rename_legacy_headers(
            frame, EQUIPMENT_COLUMNS, LEGACY_EQUIPMENT_HEADER_ALIASES, "설비 마스터"
        )


def test_downtime_alias_renames_the_id_but_keeps_its_note() -> None:
    equipment = prepare_equipment_master(_equipment())
    old = _downtime().rename(columns={"설비명": "호기"})
    old.loc[0, "비고"] = "비가동 메모"

    from_csv = read_downtime_csv(old.to_csv(index=False).encode("utf-8-sig"), equipment=equipment)
    from_paste = read_downtime_clipboard(old.to_csv(index=False, sep="\t"), equipment=equipment)

    for result in (from_csv, from_paste):
        assert result.columns.tolist() == list(DOWNTIME_COLUMNS)
        assert result.loc[0, "설비명"] == "EQ-01"
        assert result.loc[0, "비고"] == "비가동 메모"


def test_export_uses_the_new_header_and_round_trips_new_values() -> None:
    current = _text_columns(prepare_equipment_master(_equipment()))
    current.loc[0, "투자Capa"] = "322K"
    current.loc[0, "반입/Qual 이력"] = "8/4 반입 · 8/9 Qual"
    current.loc[1, "메모3"] = "메모"
    current.loc[0, "반입실적"] = pd.Timestamp("2026-08-05")
    current.loc[0, "반입상태"] = "완료"
    current.loc[0, "Qual실적"] = pd.Timestamp("2026-08-10")

    payload = equipment_csv_bytes(current)
    header = payload.decode("utf-8-sig").splitlines()[0]
    result = _read_whole_master(payload)

    assert header.split(",") == list(EQUIPMENT_COLUMNS)
    assert result.loc[0, "투자Capa"] == "322K"
    assert result.loc[0, "반입/Qual 이력"] == "8/4 반입 · 8/9 Qual"
    assert result.loc[1, "메모3"] == "메모"
    assert result.loc[0, "반입실적"] == pd.Timestamp("2026-08-05")
    assert result.loc[0, "반입상태"] == "완료"
    assert result.loc[0, "Qual실적"] == pd.Timestamp("2026-08-10")


# ------------------------------------------------------------------------------- 저장


def test_repository_mapping_covers_the_contract_one_to_one() -> None:
    # 시나리오 메모는 설비 마스터 표가 아니라 설비 시나리오 일정 표의 칸이다(설비 DB 0027).
    master_columns = tuple(column for column in EQUIPMENT_COLUMNS if column != "시나리오 메모")
    assert tuple(EQUIPMENT_MASTER_DB_COLUMNS) == master_columns
    assert len(set(EQUIPMENT_MASTER_DB_COLUMNS.values())) == len(master_columns)
    # 빠진 컬럼의 DB 칸은 남겨 두되 읽지도 쓰지도 않는다.
    assert "investment_basis" not in EQUIPMENT_MASTER_DB_COLUMNS.values()
    assert "classification_3" not in EQUIPMENT_MASTER_DB_COLUMNS.values()
    # 이름만 바뀐 컬럼은 DB 칸이 그대로다 — 마이그레이션 없이 옛 리비전이 이어진다.
    assert EQUIPMENT_MASTER_DB_COLUMNS["Area Code"] == "classification_1"
    assert EQUIPMENT_MASTER_DB_COLUMNS["정지일정"] == "removal_date"
    assert EQUIPMENT_MASTER_DB_COLUMNS["반출/이설일정"] == "relocation_date"
    assert EQUIPMENT_MASTER_DB_COLUMNS["Qual상태"] == "qual_confirmation_status"
    assert tuple(DOWNTIME_DB_COLUMNS) == DOWNTIME_COLUMNS


def test_new_columns_round_trip_through_a_revision(tmp_path: Path) -> None:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    equipment = _text_columns(_equipment())
    equipment.loc[0, "투자Capa"] = "322K"
    equipment.loc[0, "반입/Qual 이력"] = "반입 지연 1회"
    equipment.loc[1, "메모1"] = "하나"
    equipment.loc[1, "메모2"] = "둘"
    equipment.loc[1, "메모3"] = "셋"
    equipment.loc[0, "반입실적"] = "2026-08-05"
    equipment.loc[0, "반입상태"] = "완료"
    equipment.loc[0, "Qual실적"] = "2026-08-10"
    equipment.loc[1, "반입상태"] = "지연"

    saved = repository.save_snapshot(_baseline(), equipment, _downtime(), note="새 컬럼")
    loaded = repository.load_snapshot(saved.revision.revision_id)

    assert loaded.equipment.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert loaded.equipment.loc[0, "투자Capa"] == "322K"
    assert loaded.equipment.loc[0, "반입/Qual 이력"] == "반입 지연 1회"
    memos = [loaded.equipment.at[1, column] for column in ("메모1", "메모2", "메모3")]
    assert memos == ["하나", "둘", "셋"]
    assert loaded.equipment.loc[0, "반입실적"] == pd.Timestamp("2026-08-05")
    assert loaded.equipment.loc[0, "Qual실적"] == pd.Timestamp("2026-08-10")
    assert loaded.equipment["반입상태"].tolist() == ["완료", "지연"]
    assert loaded.equipment.loc[1, "설비이력"] == "셋업 중"
    assert loaded.downtime.loc[0, "설비명"] == "EQ-01"
    pd.testing.assert_frame_equal(loaded.equipment, saved.equipment)


def test_only_a_new_column_change_makes_a_new_revision(tmp_path: Path) -> None:
    """내용 해시가 새 컬럼까지 본다. 메모·실적만 고친 저장이 「변경 없음」으로 버려지면 안 된다."""
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    first = repository.save_snapshot(_baseline(), _equipment(), _downtime())
    assert repository.save_space_layout(_baseline(), _equipment(), _downtime()) is None
    changed = _text_columns(_equipment())
    changed.loc[0, "메모1"] = "고침"

    second = repository.save_space_layout(_baseline(), changed, _downtime())

    assert second is not None
    assert second.revision.revision_no == first.revision.revision_no + 1
    assert second.equipment.loc[0, "메모1"] == "고침"
    actual = _text_columns(changed)
    actual.loc[0, "Qual실적"] = "2026-08-09"
    third = repository.save_space_layout(_baseline(), actual, _downtime())
    assert third is not None and third.revision.revision_no == second.revision.revision_no + 1


def _database_before(path: Path, version: int) -> None:
    """`version` 까지의 설비 마이그레이션만 적용한 DB 를 만든다."""
    before = [
        migration for migration in load_equipment_migrations() if migration.version <= version
    ]
    with duckdb.connect(str(path)) as connection:
        for migration in before:
            connection.execute(migration.sql)
            connection.execute(
                "INSERT INTO equipment_meta.schema_migration (version, name, checksum) "
                "VALUES (?, ?, ?)",
                [migration.version, migration.name, migration.checksum],
            )


def _nullable_columns(path: Path) -> dict[str, str]:
    with duckdb.connect(str(path)) as connection:
        return {
            str(row[0]): str(row[1])
            for row in connection.execute(
                """
                SELECT column_name, is_nullable FROM information_schema.columns
                WHERE table_schema = 'equipment_ops'
                  AND table_name = 'equipment_master_snapshot'
                """
            ).fetchall()
        }


def test_migration_0015_adds_nullable_columns_and_keeps_investment_basis(tmp_path: Path) -> None:
    """0013 까지 적용된 DB 의 리비전이 0015 뒤에도 열리고, 옛 투자기준 값은 지워지지 않는다."""
    database_path = tmp_path / "before-0015.duckdb"
    _database_before(database_path, 13)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash,
                equipment_hash, downtime_hash, equipment_contract_version
            ) VALUES ('r-old', 1, 'old', 'b', 's', 'e', 'd', 3)
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.equipment_master_snapshot (
                revision_id, source_row_no, equipment_id, process_large, process_small,
                line_type, utilization_type, investment_basis, model_name, classification_1,
                arrival_date, qual_date, qual_confirmation_status, long_term_storage_flag,
                existing_equipment_flag, note, layout_display_flag, parent_equipment_id
            ) VALUES (
                'r-old', 1, 'EQ-OLD', 'B/N', 'Process-A', 'FRONT', 'HBM', '299K',
                'KT-1', '임시', DATE '2026-08-01', DATE '2026-08-05', '확정', 'N', 'N',
                '옛 비고', 'N', NULL
            )
            """
        )

    repository = DuckDBEquipmentRepository(database_path)
    assert repository.initialize() == (15, 17, 19, 21, 23, 25, 27, 29)
    old = repository.load_snapshot("r-old").equipment

    assert old.loc[0, "설비명"] == "EQ-OLD"
    assert old.loc[0, "공정구분"] == "FRONT"
    assert old.loc[0, "투자구분"] == "HBM"
    assert old.loc[0, "Model"] == "KT-1"
    assert old.loc[0, "Area Code"] == "임시"
    assert old.loc[0, "Qual상태"] == "확정"
    assert old.loc[0, "설비이력"] == "옛 비고"
    assert old.loc[0, "반입일정"] == pd.Timestamp("2026-08-01")
    assert old[[*NEW_COLUMNS, *ACTUAL_COLUMNS]].loc[0].isna().all()

    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="0015 뒤")
    columns = _nullable_columns(database_path)
    with duckdb.connect(str(database_path)) as connection:
        basis = connection.execute(
            """
            SELECT revision_id, investment_basis FROM equipment_ops.equipment_master_snapshot
            ORDER BY revision_id = 'r-old' DESC, source_row_no
            """
        ).fetchall()

    for column in ("investment_capa", "arrival_qual_history", "memo_1", "memo_2", "memo_3"):
        assert columns[column] == "YES", column
    assert "investment_basis" in columns
    # 옛 리비전의 값은 그대로이고, 새 리비전은 그 컬럼에 쓰지 않는다.
    assert basis[0] == ("r-old", "299K")
    assert all(value is None for _, value in basis[1:])


def test_migration_0023_adds_actual_columns_and_keeps_the_dropped_status_column(
    tmp_path: Path,
) -> None:
    """0021 까지 적용된 DB 의 리비전이 0023 뒤에도 열린다.

    - 이름만 바뀐 컬럼(구분·반출일정·이설일정·확정상태)은 같은 DB 칸에서 새 이름으로 읽힌다.
    - 새 실적 칸 셋은 빈칸으로 읽히고, 손대지 않은 저장은 리비전을 만들지 않는다(「바뀐 것 없음」은
      최신 리비전을 새 계약으로 다시 정규화해 견준다).
    - 계약에서 빠진 설비가동현황(`classification_3`)의 옛 값은 지우지 않고, 새 리비전은 쓰지 않는다.
    """
    database_path = tmp_path / "before-0023.duckdb"
    _database_before(database_path, 21)
    equipment = _equipment()
    equipment.loc[0, "정지일정"] = "2026-11-01"
    equipment.loc[1, "반출/이설일정"] = "2026-12-01"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO equipment_ops.revision (
                revision_id, revision_no, note, baseline_hash, schedule_hash,
                equipment_hash, downtime_hash, equipment_contract_version
            ) VALUES ('r-36', 1, 'old', 'b', 's', 'e', 'd', 3)
            """
        )
        connection.execute(
            """
            INSERT INTO equipment_ops.baseline_snapshot (
                revision_id, source_row_no, process_name, classification, base_count, note
            ) VALUES ('r-36', 1, 'Process-A', '전체', 2, NULL)
            """
        )
        for row_no, (_, row) in enumerate(prepare_equipment_master(equipment).iterrows(), 1):
            connection.execute(
                """
                INSERT INTO equipment_ops.equipment_master_snapshot (
                    revision_id, source_row_no, equipment_id, process_large, process_small,
                    utilization_type, classification_1, classification_2, classification_3,
                    manager_name, building, floor_name, x_coordinate, y_coordinate, x_size,
                    y_size, vibration_table_date, logistics_date, arrival_date, qual_date,
                    qual_confirmation_status, removal_date, relocation_date, note,
                    long_term_storage_flag, existing_equipment_flag, layout_display_flag,
                    conversion_ratio
                ) VALUES (
                    'r-36', ?, ?, 'B/N', 'Process-A', '양산', 'main', 'HBM', '가동',
                    '담당A', 'C1', '1F', ?, 10, 12, 7, ?, ?, ?, ?, '확정', ?, ?, ?,
                    'N', 'N', 'Y', 1.0
                )
                """,
                [
                    row_no,
                    row["설비명"],
                    row["X좌표"],
                    row["제진대일정"],
                    row["물류일정"],
                    row["반입일정"],
                    row["Qual일정"],
                    row["정지일정"] if pd.notna(row["정지일정"]) else None,
                    row["반출/이설일정"] if pd.notna(row["반출/이설일정"]) else None,
                    row["설비이력"] if pd.notna(row["설비이력"]) else None,
                ],
            )
        connection.execute(
            """
            INSERT INTO equipment_ops.downtime_schedule_snapshot (
                revision_id, source_row_no, equipment_id, downtime_type, start_date, end_date,
                detail, note
            ) VALUES ('r-36', 1, 'EQ-01', '고장', DATE '2026-08-10', DATE '2026-08-20',
                      '부품 교체', NULL)
            """
        )

    repository = DuckDBEquipmentRepository(database_path)
    assert repository.initialize() == (23, 25, 27, 29)
    columns = _nullable_columns(database_path)
    for column in ("arrival_actual_date", "arrival_status", "qual_actual_date"):
        assert columns[column] == "YES", column
    assert "classification_3" in columns
    old = repository.load_snapshot("r-36")

    # Area Code 의 Main 은 대소문자를 맞춰 읽는다(저장할 때와 같은 정규화).
    assert old.equipment["Area Code"].tolist() == ["Main", "Main"]
    assert old.equipment.loc[0, "정지일정"] == pd.Timestamp("2026-11-01")
    assert old.equipment.loc[1, "반출/이설일정"] == pd.Timestamp("2026-12-01")
    assert old.equipment["Qual상태"].tolist() == ["확정", "확정"]
    assert old.equipment.loc[:, list(ACTUAL_COLUMNS)].isna().all().all()
    # 같은 세 표를 다시 저장하면 리비전이 생기지 않는다.
    assert (
        repository.save_space_layout(old.baseline, old.equipment, old.downtime, note="그대로")
        is None
    )

    changed = old.equipment.copy()
    changed.loc[0, "설비이력"] = "고침"
    saved = repository.save_snapshot(old.baseline, changed, old.downtime, note="0023 뒤")
    assert saved.revision.revision_no == 2
    with duckdb.connect(str(database_path)) as connection:
        status = connection.execute(
            """
            SELECT revision_id, classification_3 FROM equipment_ops.equipment_master_snapshot
            ORDER BY revision_id = 'r-36' DESC, source_row_no
            """
        ).fetchall()
    assert status[:2] == [("r-36", "가동"), ("r-36", "가동")]
    assert all(value is None for _, value in status[2:])


def test_import_review_carries_the_dropped_column_notice() -> None:
    """옛 양식에는 새 선택 컬럼이 없다. RawData 붙여넣기는 붙여넣은 열만 바꾸므로 그 칸의 저장된
    값을 지키고(2026-10-08 일부 열 붙여넣기), 그대로 둔 열을 알림 한 줄로 말한다."""
    from capa_simulation.components.equipment_data_workspace import (
        ImportReview,
        build_import_review,
    )
    from capa_simulation.services.equipment_contract import empty_equipment_baseline
    from capa_simulation.services.equipment_validation import prepare_downtime_schedule

    raw = _text_columns(_equipment())
    raw["투자Capa"] = "322K"
    raw.loc[1, "메모2"] = "지킬 메모"
    raw.loc[0, "반입상태"] = "완료"
    raw.loc[0, "반입실적"] = "2026-08-04"
    equipment = prepare_equipment_master(raw)
    downtime = prepare_downtime_schedule(_downtime(), equipment=equipment)
    source = (empty_equipment_baseline(), equipment, downtime)

    def review(payload: str | bytes) -> ImportReview:
        return build_import_review("설비 마스터", payload, source, floor_canvases={})

    old32 = _old_layout(equipment)
    old36 = _old36_layout(equipment)
    reviews = {
        "32 파일": (review(old32.to_csv(index=False).encode("utf-8-sig")), 9),
        "32 붙여넣기": (review(old32.to_csv(index=False, sep="\t")), 9),
        "36 파일": (review(old36.to_csv(index=False).encode("utf-8-sig")), 4),
        "36 붙여넣기": (review(old36.to_csv(index=False, sep="\t")), 4),
    }
    fresh = review(equipment_csv_bytes(equipment))

    for name, (result, kept) in reviews.items():
        dropped = ("투자기준", "분류3") if name.startswith("32") else ("설비가동현황",)
        assert len(result.notices) == len(dropped) + 1, name
        for notice, column in zip(result.notices, dropped, strict=False):
            assert f"「{column}」" in notice, name
        assert f"붙여넣지 않은 {kept}개 열" in result.notices[-1], name
        assert "그대로 둡니다" in result.notices[-1], name
        assert result.cautions == (), name
        assert result.changes["Import구분"].tolist() == ["대체", "대체"], name
        assert result.changes["변경컬럼"].tolist() == ["변경 없음", "변경 없음"], name
        saved = result.candidate[1].set_index("설비명")
        assert saved["투자Capa"].tolist() == ["322K", "322K"], name
        assert saved.loc["EQ-02", "메모2"] == "지킬 메모", name
        assert saved.loc["EQ-01", "반입상태"] == "완료", name
        assert saved.loc["EQ-01", "반입실적"] == pd.Timestamp("2026-08-04"), name
    assert fresh.notices == ()
