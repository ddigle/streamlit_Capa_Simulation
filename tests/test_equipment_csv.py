# Purpose: equipment csv 관련 정상·예외·회귀 동작을 검증한다.

from io import BytesIO

import pandas as pd
from test_equipment_availability import _downtime, _equipment

from capa_simulation.services.equipment_contract import QUAL_CONFIRMATION_STATUSES
from capa_simulation.services.equipment_csv import (
    EQUIPMENT_CHOICE_ROWS,
    SAMPLE_DOWNTIME_NOTE,
    SAMPLE_EQUIPMENT_ID,
    SAMPLE_EQUIPMENT_MANAGER,
    SAMPLE_EQUIPMENT_NOTE,
    build_downtime_import_preview,
    build_equipment_import_preview,
    downtime_csv_template,
    equipment_csv_template,
    merge_downtime_rows,
    merge_equipment_rows,
    read_downtime_clipboard,
    read_downtime_csv,
    read_equipment_clipboard,
    read_equipment_csv,
)


def test_equipment_csv_template_round_trips_with_30_columns() -> None:
    result = read_equipment_csv(equipment_csv_template())

    assert len(result.columns) == 30
    assert "사업부" not in result.columns
    assert result.columns.tolist()[5:7] == ["투자기준", "담당자"]
    assert len(result) == 1
    assert result.loc[0, "호기"] == SAMPLE_EQUIPMENT_ID
    assert result.loc[0, "담당자"] == SAMPLE_EQUIPMENT_MANAGER
    assert result.loc[0, "비고"] == SAMPLE_EQUIPMENT_NOTE
    assert result.loc[0, "확정상태"] == "계획"


def test_equipment_csv_template_lists_choice_rows_without_equipment_id() -> None:
    raw = pd.read_csv(BytesIO(equipment_csv_template()), dtype="object")

    assert len(raw) == 1 + len(EQUIPMENT_CHOICE_ROWS)
    choices = raw.loc[raw["호기"].isna()]
    assert len(choices) == len(EQUIPMENT_CHOICE_ROWS)
    assert choices["활용구분"].tolist() == ["WLP", "2.5D", "HCB"]
    assert set(raw["확정상태"]) == set(QUAL_CONFIRMATION_STATUSES)


def test_downtime_csv_template_has_no_id_and_round_trips() -> None:
    equipment = read_equipment_csv(equipment_csv_template())
    result = read_downtime_csv(downtime_csv_template(), equipment=equipment)

    assert len(downtime_csv_template().decode("utf-8-sig").splitlines()) == 2
    assert "비가동ID" not in result.columns
    assert result.loc[0, "호기"] == SAMPLE_EQUIPMENT_ID
    assert result.loc[0, "비고"] == SAMPLE_DOWNTIME_NOTE


def test_equipment_templates_round_trip_through_excel_clipboard() -> None:
    equipment_text = pd.read_csv(BytesIO(equipment_csv_template())).to_csv(
        index=False,
        sep="\t",
    )
    equipment = read_equipment_clipboard(equipment_text)
    downtime_text = pd.read_csv(BytesIO(downtime_csv_template())).to_csv(
        index=False,
        sep="\t",
    )
    downtime = read_downtime_clipboard(downtime_text, equipment=equipment)

    assert len(equipment) == 1
    assert equipment.loc[0, "호기"] == SAMPLE_EQUIPMENT_ID
    assert equipment.loc[0, "담당자"] == SAMPLE_EQUIPMENT_MANAGER
    assert downtime.loc[0, "호기"] == SAMPLE_EQUIPMENT_ID


def test_equipment_csv_merge_and_preview_replace_by_equipment_id() -> None:
    current = _equipment()
    incoming = current.iloc[[0]].copy()
    incoming.loc[incoming.index[0], "공정소분류"] = "Changed"

    preview = build_equipment_import_preview(current, incoming)
    result = merge_equipment_rows(current, incoming)

    assert preview.loc[0, "Import구분"] == "대체"
    assert "공정소분류" in preview.loc[0, "변경컬럼"]
    assert "Process-A → Changed" in preview.loc[0, "변경내용"]
    assert len(result) == 2
    assert result.loc[result["호기"].eq("EQ-01"), "공정소분류"].item() == "Changed"


def test_downtime_merge_and_preview_use_natural_key() -> None:
    current = _downtime()
    incoming = current.copy()
    incoming.loc[0, "상세사유"] = "교체 사유 변경"

    preview = build_downtime_import_preview(current, incoming)
    result = merge_downtime_rows(current, incoming, equipment=_equipment())

    assert preview.loc[0, "Import구분"] == "대체"
    assert preview.loc[0, "변경컬럼"] == "상세사유"
    assert len(result) == 1
    assert result.loc[0, "상세사유"] == "교체 사유 변경"


def test_import_preview_marks_new_rows() -> None:
    incoming = _equipment().iloc[[0]].copy()
    incoming.loc[incoming.index[0], "호기"] = "EQ-NEW"

    preview = build_equipment_import_preview(_equipment(), incoming)

    assert preview["Import구분"].tolist() == ["신규"]
    assert preview["변경컬럼"].tolist() == ["-"]
