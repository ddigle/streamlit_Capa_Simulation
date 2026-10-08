# Purpose: 설비 마스터 36컬럼 계약·저장 매핑·0015 마이그레이션·옛 머리 이름 자동 변환을 검증한다.

from pathlib import Path

import duckdb
import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_migration_runner import load_equipment_migrations
from capa_simulation.persistence.equipment_repository import (
    DOWNTIME_DB_COLUMNS,
    EQUIPMENT_MASTER_DB_COLUMNS,
    DuckDBEquipmentRepository,
)
from capa_simulation.services.equipment_contract import (
    DATE_COLUMNS,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    EQUIPMENT_KEY_COLUMNS,
    FLAG_COLUMNS,
    LEGACY_DOWNTIME_HEADER_ALIASES,
    LEGACY_EQUIPMENT_HEADER_ALIASES,
    OBSOLETE_EQUIPMENT_COLUMNS,
    OPTIONAL_EQUIPMENT_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    REFERENCE_TEXT_COLUMNS,
    RELOCATION_DATE_COLUMN,
    SCHEDULE_STAGES,
    TRANSITION_EVENT_COLUMNS,
    UNIT_CONSISTENT_COLUMNS,
    rename_legacy_headers,
)
from capa_simulation.services.equipment_csv import (
    equipment_csv_bytes,
    read_downtime_clipboard,
    read_downtime_csv,
    read_equipment_clipboard,
    read_equipment_csv,
)
from capa_simulation.services.equipment_validation import prepare_equipment_master

# 2026-10-06 사용자 결정의 순서 그대로다.
SPEC_ORDER = (
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

NEW_COLUMNS = ("투자Capa", "반입/Qual 이력", "메모1", "메모2", "메모3")

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


def _old_layout(frame: pd.DataFrame) -> pd.DataFrame:
    """새 계약 표를 옛 32컬럼 머리로 되돌린다. 새 컬럼은 버리고 투자기준에는 옛 값을 적는다."""
    back = {new: old for old, new in LEGACY_EQUIPMENT_HEADER_ALIASES.items()}
    old = frame.drop(columns=list(NEW_COLUMNS)).rename(columns=back)
    old["투자기준"] = "322K"
    return old.loc[:, list(OLD_ORDER)]


def _text_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """비어 있는 새 컬럼은 float 로 만들어진다. 글자를 넣기 전에 글자 칸으로 바꾼다."""
    return frame.astype({column: "object" for column in NEW_COLUMNS})


# ------------------------------------------------------------------------------- 계약


def test_equipment_contract_follows_the_decided_order() -> None:
    assert EQUIPMENT_COLUMNS == SPEC_ORDER
    assert len(set(EQUIPMENT_COLUMNS)) == 36
    assert "투자기준" not in EQUIPMENT_COLUMNS
    assert OBSOLETE_EQUIPMENT_COLUMNS == ("투자기준",)


def test_derived_constants_use_the_new_names() -> None:
    assert EQUIPMENT_ID_COLUMN == "설비명"
    assert EQUIPMENT_KEY_COLUMNS == ("설비명",)
    assert DOWNTIME_COLUMNS == ("설비명", "비가동유형", "시작일", "종료일", "상세사유", "비고")
    assert DOWNTIME_KEY_COLUMNS == ("설비명", "비가동유형", "시작일")
    assert TRANSITION_EVENT_COLUMNS[0] == "설비명"
    assert PARENT_EQUIPMENT_COLUMN == "Main 설비"
    assert FLAG_COLUMNS == ("보관유무", "기존설비여부", "레이아웃표시")
    assert "반입일정" in DATE_COLUMNS and "입고일정" not in DATE_COLUMNS
    # 단계 이름은 바꾸지 않는다 — 컬럼 이름만 바뀐다.
    assert ("반입일정", "입고") in SCHEDULE_STAGES
    assert RELOCATION_DATE_COLUMN == "이설일정"
    assert ("이설일정", "이설") in SCHEDULE_STAGES
    assert "이설일정" in DATE_COLUMNS and "이설일" not in DATE_COLUMNS
    assert UNIT_CONSISTENT_COLUMNS == (
        "공정소분류",
        "공정대분류",
        "공정구분",
        "투자구분",
        "동",
        "층",
    )
    assert set(OPTIONAL_EQUIPMENT_COLUMNS) == {*NEW_COLUMNS, "Main 설비"}
    assert set(NEW_COLUMNS) <= set(REFERENCE_TEXT_COLUMNS)
    contract_columns = {*EQUIPMENT_COLUMNS, *DOWNTIME_COLUMNS}
    for derived in (DATE_COLUMNS, FLAG_COLUMNS, REFERENCE_TEXT_COLUMNS, UNIT_CONSISTENT_COLUMNS):
        assert set(derived) <= contract_columns


def test_legacy_alias_maps_land_on_contract_columns() -> None:
    assert set(LEGACY_EQUIPMENT_HEADER_ALIASES.values()) <= set(EQUIPMENT_COLUMNS)
    assert not set(LEGACY_EQUIPMENT_HEADER_ALIASES) & set(EQUIPMENT_COLUMNS)
    assert LEGACY_DOWNTIME_HEADER_ALIASES == {"호기": "설비명"}
    # 옛 계약의 모든 컬럼은 그대로이거나, 새 이름이 있거나, 빠진 컬럼이다.
    for column in OLD_ORDER:
        assert (
            column in EQUIPMENT_COLUMNS
            or column in LEGACY_EQUIPMENT_HEADER_ALIASES
            or column in OBSOLETE_EQUIPMENT_COLUMNS
        ), column


def test_prepared_master_has_the_new_columns_in_order() -> None:
    prepared = prepare_equipment_master(_equipment())

    assert prepared.columns.tolist() == list(EQUIPMENT_COLUMNS)


# -------------------------------------------------------------------------- 옛 머리 변환


def test_old_csv_reads_into_the_new_columns_and_drops_investment_basis() -> None:
    current = prepare_equipment_master(_equipment())
    payload = _old_layout(current).to_csv(index=False).encode("utf-8-sig")
    notices: list[str] = []

    result = read_equipment_csv(payload, notices=notices)

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert result.loc[1, "설비이력"] == "셋업 중"
    assert result.loc[0, "반입일정"] == pd.Timestamp("2026-08-04")
    assert result.loc[0, "투자구분"] == "양산"
    assert result["보관유무"].tolist() == ["N", "N"]
    # 옛 투자기준 값은 새 컬럼 투자Capa 로 넘어가지 않는다 — 별개의 컬럼이다.
    for column in NEW_COLUMNS:
        assert result[column].isna().all(), column
    # 알림은 둘: 빠진 투자기준 한 줄, 새 컬럼이 없어 대체 행의 그 칸이 비워진다는 한 줄.
    assert len(notices) == 2
    assert "투자기준" in notices[0]
    assert "열이 없어 빈칸으로 읽었습니다" in notices[1] and "메모1" in notices[1]


def test_old_clipboard_paste_converts_the_same_way() -> None:
    current = prepare_equipment_master(_equipment())
    text = _old_layout(current).to_csv(index=False, sep="\t")
    notices: list[str] = []

    result = read_equipment_clipboard(text, notices=notices)

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert len(notices) == 2


def test_old_file_without_investment_basis_only_warns_about_the_missing_new_columns() -> None:
    current = prepare_equipment_master(_equipment())
    old = _old_layout(current).drop(columns=["투자기준"])
    notices: list[str] = []

    result = read_equipment_csv(old.to_csv(index=False).encode("utf-8-sig"), notices=notices)

    assert len(notices) == 1
    assert "투자기준" not in notices[0] and "빈칸으로 읽었습니다" in notices[0]
    assert result["설비명"].tolist() == ["EQ-01", "EQ-02"]
    assert result.loc[:, list(NEW_COLUMNS)].isna().all().all()


def test_old_module_parent_column_keeps_grouping_modules() -> None:
    """옛 「모체호기」 열이 빈 칸으로 사라지면 모듈 행이 모두 따로 세어진다."""
    current = prepare_equipment_master(_equipment())
    current["Main 설비"] = "EQ-UNIT"
    old = _old_layout(current)

    result = read_equipment_csv(old.to_csv(index=False).encode("utf-8-sig"))

    assert result["Main 설비"].tolist() == ["EQ-UNIT", "EQ-UNIT"]


def test_relocation_date_from_an_old_header_keeps_its_value() -> None:
    """10-06 첫 개편(36컬럼) 양식은 머리가 「이설일」이다. 값이 그대로 「이설일정」으로 온다."""
    current = prepare_equipment_master(_equipment())
    current.loc[0, RELOCATION_DATE_COLUMN] = pd.Timestamp("2026-12-01")
    text = equipment_csv_bytes(current).decode("utf-8-sig")
    header, _, body = text.partition("\n")
    notices: list[str] = []

    result = read_equipment_csv(
        f"{header.replace('이설일정', '이설일')}\n{body}".encode("utf-8-sig"), notices=notices
    )

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result.loc[0, "이설일정"] == pd.Timestamp("2026-12-01")
    assert pd.isna(result.loc[1, "이설일정"])
    # 이름만 바뀐 것이라 알림은 없다(빠진 컬럼·없는 선택 컬럼이 없다).
    assert notices == []


def test_relocation_old_header_also_converts_on_paste_and_in_the_old_layout() -> None:
    current = prepare_equipment_master(_equipment())
    current.loc[1, RELOCATION_DATE_COLUMN] = pd.Timestamp("2027-01-04")
    old = _old_layout(current)
    assert "이설일" in old.columns and "이설일정" not in old.columns

    pasted = read_equipment_clipboard(old.to_csv(index=False, sep="\t"))

    assert pasted.loc[1, "이설일정"] == pd.Timestamp("2027-01-04")


def test_old_and_new_relocation_headers_together_are_rejected() -> None:
    current = prepare_equipment_master(_equipment())
    both = current.assign(이설일=current[RELOCATION_DATE_COLUMN])

    with pytest.raises(ValueError, match=r"옛 이름과 새 이름이 함께.*이설일정 ← 이설일정 · 이설일"):
        read_equipment_csv(both.to_csv(index=False).encode("utf-8-sig"))


def test_spacing_variants_of_new_and_old_names_are_accepted() -> None:
    current = prepare_equipment_master(_equipment())
    spaced = equipment_csv_bytes(current).decode("utf-8-sig")
    header, _, body = spaced.partition("\n")
    header = header.replace("Main 설비", "Main설비").replace("반입/Qual 이력", "반입/Qual이력")

    result = read_equipment_csv(f"{header}\n{body}".encode("utf-8-sig"))

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
    ],
)
def test_case_variants_of_latin_headers_keep_their_values(contract: str, variant: str) -> None:
    """영문이 든 선택 컬럼이 대소문자만 달라 버려지면 빈 칸으로 조용히 읽힌다."""
    current = _text_columns(prepare_equipment_master(_equipment()))
    current["Main 설비"] = "EQ-UNIT"
    current["투자Capa"] = "322K"
    current["반입/Qual 이력"] = "1차 반입"
    current["Model"] = "DEMO-M1"
    text = equipment_csv_bytes(current).decode("utf-8-sig")
    header, _, body = text.partition("\n")
    header = header.replace(contract, variant)

    result = read_equipment_csv(f"{header}\n{body}".encode("utf-8-sig"))

    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert result[contract].notna().all()
    assert result[contract].tolist() == current[contract].tolist()


def test_case_variant_lookalike_of_parent_column_is_named_instead_of_blanked() -> None:
    current = prepare_equipment_master(_equipment())
    renamed = current.rename(columns={"Main 설비": "MAIN 설비(선택)"})

    with pytest.raises(ValueError, match="Main 설비 열 이름이 다릅니다"):
        read_equipment_csv(renamed.to_csv(index=False).encode("utf-8-sig"))


def test_misspelled_old_parent_column_is_named_instead_of_blanked() -> None:
    current = prepare_equipment_master(_equipment())
    old = _old_layout(current).rename(columns={"모체호기": "모체호기(선택)"})

    with pytest.raises(ValueError, match="Main 설비 열 이름이 다릅니다"):
        read_equipment_csv(old.to_csv(index=False).encode("utf-8-sig"))


def test_old_and_new_name_for_the_same_column_together_are_rejected() -> None:
    frame = pd.DataFrame({"호기": ["A"], "설비명": ["B"]})

    with pytest.raises(ValueError, match="옛 이름과 새 이름이 함께"):
        rename_legacy_headers(
            frame, EQUIPMENT_COLUMNS, LEGACY_EQUIPMENT_HEADER_ALIASES, "호기 마스터"
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
    current = prepare_equipment_master(_equipment())
    current.loc[0, "투자Capa"] = "322K"
    current.loc[0, "반입/Qual 이력"] = "8/4 반입 · 8/9 Qual"
    current.loc[1, "메모3"] = "메모"

    payload = equipment_csv_bytes(current)
    header = payload.decode("utf-8-sig").splitlines()[0]
    result = read_equipment_csv(payload)

    assert header.split(",") == list(EQUIPMENT_COLUMNS)
    assert result.loc[0, "투자Capa"] == "322K"
    assert result.loc[0, "반입/Qual 이력"] == "8/4 반입 · 8/9 Qual"
    assert result.loc[1, "메모3"] == "메모"


# ------------------------------------------------------------------------------- 저장


def test_repository_mapping_covers_the_contract_one_to_one() -> None:
    assert tuple(EQUIPMENT_MASTER_DB_COLUMNS) == EQUIPMENT_COLUMNS
    assert len(set(EQUIPMENT_MASTER_DB_COLUMNS.values())) == len(EQUIPMENT_COLUMNS)
    assert "investment_basis" not in EQUIPMENT_MASTER_DB_COLUMNS.values()
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

    saved = repository.save_snapshot(_baseline(), equipment, _downtime(), note="새 컬럼")
    loaded = repository.load_snapshot(saved.revision.revision_id)

    assert loaded.equipment.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert loaded.equipment.loc[0, "투자Capa"] == "322K"
    assert loaded.equipment.loc[0, "반입/Qual 이력"] == "반입 지연 1회"
    memos = [loaded.equipment.at[1, column] for column in ("메모1", "메모2", "메모3")]
    assert memos == ["하나", "둘", "셋"]
    assert loaded.equipment.loc[1, "설비이력"] == "셋업 중"
    assert loaded.downtime.loc[0, "설비명"] == "EQ-01"
    pd.testing.assert_frame_equal(loaded.equipment, saved.equipment)


def test_only_a_new_column_change_makes_a_new_revision(tmp_path: Path) -> None:
    """내용 해시가 새 컬럼까지 본다. 메모만 고친 저장이 「변경 없음」으로 버려지면 안 된다."""
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


def test_migration_0015_adds_nullable_columns_and_keeps_investment_basis(tmp_path: Path) -> None:
    """0013 까지 적용된 DB 의 리비전이 0015 뒤에도 열리고, 옛 투자기준 값은 지워지지 않는다."""
    database_path = tmp_path / "before-0015.duckdb"
    before = [migration for migration in load_equipment_migrations() if migration.version <= 13]
    with duckdb.connect(str(database_path)) as connection:
        for migration in before:
            connection.execute(migration.sql)
            connection.execute(
                "INSERT INTO equipment_meta.schema_migration (version, name, checksum) "
                "VALUES (?, ?, ?)",
                [migration.version, migration.name, migration.checksum],
            )
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
    assert repository.initialize() == (15, 17, 19)
    old = repository.load_snapshot("r-old").equipment

    assert old.loc[0, "설비명"] == "EQ-OLD"
    assert old.loc[0, "공정구분"] == "FRONT"
    assert old.loc[0, "투자구분"] == "HBM"
    assert old.loc[0, "Model"] == "KT-1"
    assert old.loc[0, "구분"] == "임시"
    assert old.loc[0, "설비이력"] == "옛 비고"
    assert old.loc[0, "반입일정"] == pd.Timestamp("2026-08-01")
    assert old[list(NEW_COLUMNS)].loc[0].isna().all()

    repository.save_snapshot(_baseline(), _equipment(), _downtime(), note="0015 뒤")
    with duckdb.connect(str(database_path)) as connection:
        columns = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT column_name, is_nullable FROM information_schema.columns
                WHERE table_schema = 'equipment_ops'
                  AND table_name = 'equipment_master_snapshot'
                """
            ).fetchall()
        }
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


def test_import_review_carries_the_dropped_column_notice() -> None:
    from capa_simulation.components.equipment_data_workspace import build_import_review
    from capa_simulation.services.equipment_contract import empty_equipment_baseline
    from capa_simulation.services.equipment_validation import prepare_downtime_schedule

    equipment = prepare_equipment_master(_equipment())
    downtime = prepare_downtime_schedule(_downtime(), equipment=equipment)
    source = (empty_equipment_baseline(), equipment, downtime)
    old = _old_layout(equipment).to_csv(index=False)

    from_file = build_import_review(
        "호기 마스터", old.encode("utf-8-sig"), source, floor_canvases={}
    )
    from_paste = build_import_review(
        "호기 마스터",
        _old_layout(equipment).to_csv(index=False, sep="\t"),
        source,
        floor_canvases={},
    )
    fresh = build_import_review(
        "호기 마스터", equipment_csv_bytes(equipment), source, floor_canvases={}
    )

    for review in (from_file, from_paste):
        assert len(review.notices) == 2 and "투자기준" in review.notices[0]
        assert "빈칸으로 읽었습니다" in review.notices[1]
        assert review.changes["Import구분"].tolist() == ["대체", "대체"]
    assert fresh.notices == ()
