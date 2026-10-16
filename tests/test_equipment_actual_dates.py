# Purpose: 설비 마스터 실적·반입상태·Area Code 의 정규화와 읽을 때·저장할 때 검사·경고를 검증한다.

"""설비 마스터 38열 개편의 새 칸 검사(2026-10-16 사용자 결정).

검사는 둘로 갈린다.

- **읽을 때도 도는 검사**(`prepare_equipment_master`) — 반입상태 값 목록. 새 컬럼이라 옛 리비전에
  값이 없어 리비전을 다시 읽어도 막히지 않는다.
- **저장할 때만 도는 검사**(`today` 를 넘길 때) — 실적이 오늘보다 늦음, 반입실적 > Qual실적. 날짜에
  따라 결과가 바뀌어 읽을 때 돌면 저장 때 통과한 리비전이 시간이 지나 열리지 않는다.

Area Code 목록 밖·실적 누락·상태 갱신 필요는 막지 않고 저장 미리보기에서 경고만 한다.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from test_equipment_availability import _baseline, _downtime, _equipment

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    AREA_CODES,
    LINE_TYPE_GROUPS,
    line_type_group,
    normalize_area_code,
)
from capa_simulation.services.equipment_csv import merge_equipment_rows
from capa_simulation.services.equipment_validation import (
    area_code_warnings,
    equipment_save_warnings,
    prepare_equipment_master,
)

TODAY = date(2026, 10, 16)


def _with_text(frame: pd.DataFrame) -> pd.DataFrame:
    """빈 새 칸은 float 로 만들어진다. 글자·날짜를 넣기 전에 글자 칸으로 바꾼다."""
    return frame.astype({"반입실적": "object", "반입상태": "object", "Qual실적": "object"})


# --------------------------------------------------------------------- 읽을 때도 도는 검사


def test_arrival_status_takes_the_same_four_values_as_the_qual_status() -> None:
    equipment = _with_text(_equipment())
    equipment.loc[0, "반입상태"] = " 지연 "
    equipment.loc[1, "반입상태"] = ""

    prepared = prepare_equipment_master(equipment)

    assert prepared.loc[0, "반입상태"] == "지연"
    # 비워도 저장된다 — 반입상태는 필수가 아니다.
    assert pd.isna(prepared.loc[1, "반입상태"])


def test_an_unknown_arrival_status_is_rejected_even_when_reading() -> None:
    equipment = _with_text(_equipment())
    equipment.loc[1, "반입상태"] = "검토중"

    with pytest.raises(
        ValueError, match=r"반입상태는 계획·확정·완료·지연 중 하나여야 합니다.*EQ-02"
    ):
        prepare_equipment_master(equipment)


def test_actual_dates_are_dates() -> None:
    equipment = _with_text(_equipment())
    equipment.loc[0, "Qual실적"] = "다음 주"

    with pytest.raises(ValueError, match="Qual실적은 날짜 형식이어야 합니다"):
        prepare_equipment_master(equipment)


# --------------------------------------------------------------------- 저장할 때만 도는 검사


@pytest.mark.parametrize("column", ["반입실적", "Qual실적"])
def test_an_actual_later_than_today_is_blocked_only_at_save(column: str) -> None:
    equipment = _with_text(_equipment())
    equipment.loc[0, column] = (TODAY + timedelta(days=1)).isoformat()

    # 리비전을 다시 읽는 길(오늘을 넘기지 않음)은 막지 않는다.
    assert prepare_equipment_master(equipment).loc[0, column] == pd.Timestamp("2026-10-17")
    with pytest.raises(ValueError, match=rf"{column}은 오늘\(2026-10-16\)보다 늦을 수 없습니다"):
        prepare_equipment_master(equipment, today=TODAY)
    equipment.loc[0, column] = TODAY.isoformat()
    assert prepare_equipment_master(equipment, today=TODAY).loc[0, column] == pd.Timestamp(TODAY)


def test_an_arrival_actual_later_than_the_qual_actual_is_blocked_only_at_save() -> None:
    equipment = _with_text(_equipment())
    equipment.loc[1, ["반입실적", "Qual실적"]] = ["2026-08-20", "2026-08-19"]

    prepare_equipment_master(equipment)
    with pytest.raises(ValueError, match=r"반입실적은 Qual실적보다 늦을 수 없습니다.*EQ-02"):
        prepare_equipment_master(equipment, today=TODAY)
    equipment.loc[1, "Qual실적"] = "2026-08-20"
    prepare_equipment_master(equipment, today=TODAY)


def test_the_repository_refuses_to_save_a_future_actual(tmp_path: Path) -> None:
    repository = DuckDBEquipmentRepository(tmp_path / "equipment.duckdb")
    repository.initialize()
    equipment = _with_text(_equipment())
    equipment.loc[0, "반입실적"] = (date.today() + timedelta(days=1)).isoformat()

    with pytest.raises(ValueError, match="반입실적은 오늘"):
        repository.save_snapshot(_baseline(), equipment, _downtime())
    assert repository.latest_revision_id() is None


def test_the_merge_preview_checks_actuals_when_given_today() -> None:
    """붙여넣기 미리보기는 저장 때 막힐 것을 미리 말한다(`merge_equipment_rows(today=)`)."""
    current = prepare_equipment_master(_equipment())
    incoming = _with_text(current.iloc[[0]].copy())
    incoming.loc[incoming.index[0], "Qual실적"] = "2026-10-30"

    merge_equipment_rows(current, incoming)
    with pytest.raises(ValueError, match="Qual실적은 오늘"):
        merge_equipment_rows(current, incoming, today=TODAY)


# ------------------------------------------------------------------------ Area Code


def test_area_codes_are_stored_with_their_own_spelling() -> None:
    equipment = _equipment().astype({"Area Code": "object"})
    equipment["Area Code"] = [" main ", "MI"]

    prepared = prepare_equipment_master(equipment)

    assert prepared["Area Code"].tolist() == ["Main", "MI"]
    values = pd.Series([" mi", "부대 ", "MAIN", "", None, "Other"])
    assert normalize_area_code(values).tolist() == ["MI", "부대", "Main", pd.NA, pd.NA, "Other"]
    assert AREA_CODES == ("Main", "MI", "부대")


def test_an_area_code_outside_the_list_is_saved_with_a_warning() -> None:
    equipment = _equipment().astype({"Area Code": "object"})
    equipment["Area Code"] = ["임시", " main "]

    prepared = prepare_equipment_master(equipment)

    assert prepared["Area Code"].tolist() == ["임시", "Main"]
    messages = area_code_warnings(equipment)
    assert len(messages) == 1
    assert messages[0].startswith("Area Code 가 Main·MI·부대 밖인 호기 1건 — 저장은 되지만")
    assert "(임시)" in messages[0] and "['EQ-01']" in messages[0]
    # 빈 칸은 경고하지 않는다. 컬럼이 없는 옛 편집본도 받는다.
    assert area_code_warnings(_equipment()) == []
    assert area_code_warnings(pd.DataFrame({"설비명": ["A"]})) == []


def test_save_warnings_gather_area_codes_and_actual_records() -> None:
    equipment = _with_text(_equipment()).astype({"Area Code": "object"})
    equipment.loc[0, "Area Code"] = "임시"
    equipment.loc[1, "반입상태"] = "완료"
    equipment.loc[0, "Qual실적"] = "2026-08-09"

    messages = equipment_save_warnings(equipment)

    assert [message.split(" ")[0] for message in messages] == ["Area", "실적", "상태"]
    assert "EQ-02(반입)" in messages[1]
    assert "EQ-01(Qual)" in messages[2]
    assert equipment_save_warnings(_equipment()) == []


def test_line_type_groups_match_without_case_or_spaces() -> None:
    values = pd.Series([" pkg ", "Front", "물류", "fdy", "S.PKG", "", None, "mi", "TEST"])

    assert line_type_group(values).tolist() == [
        "PKG",
        "FRONT",
        "물류",
        "FDY",
        pd.NA,
        pd.NA,
        pd.NA,
        "MI",
        "TEST",
    ]
    assert LINE_TYPE_GROUPS == ("물류", "FRONT", "PKG", "MI", "TEST", "FDY")
