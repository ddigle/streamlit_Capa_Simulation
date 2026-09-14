# Purpose: equipment csv 관련 정상·예외·회귀 동작을 검증한다.

from io import BytesIO

import pandas as pd
import pytest
from test_equipment_availability import _downtime, _equipment

from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    QUAL_CONFIRMATION_STATUSES,
)
from capa_simulation.services.equipment_csv import (
    EQUIPMENT_CHOICE_ROWS,
    SAMPLE_BASELINE_CATEGORY,
    SAMPLE_BASELINE_COUNT,
    SAMPLE_BASELINE_PROCESS,
    SAMPLE_BASELINE_TEMPLATE_NOTE,
    SAMPLE_DOWNTIME_NOTE,
    SAMPLE_EQUIPMENT_ID,
    SAMPLE_EQUIPMENT_MANAGER,
    SAMPLE_EQUIPMENT_NOTE,
    baseline_csv_template,
    build_baseline_import_preview,
    build_downtime_import_preview,
    build_equipment_import_preview,
    downtime_csv_template,
    equipment_csv_template,
    merge_baseline_rows,
    merge_downtime_rows,
    merge_equipment_rows,
    read_baseline_clipboard,
    read_baseline_csv,
    read_downtime_clipboard,
    read_downtime_csv,
    read_equipment_clipboard,
    read_equipment_csv,
)
from capa_simulation.services.equipment_validation import prepare_equipment_baseline

BASELINE_HEADER = "\t".join(BASELINE_COLUMNS)


def _baseline_rows() -> pd.DataFrame:
    """같은 공정에 분류가 둘인 표. 자연키가 `공정` 단독이 아님을 드러낸다."""
    return prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": ["Process-A", "Process-A", "Process-B"],
                "분류": ["전체", "임대", "전체"],
                "기존보유대수": [2.0, 3.0, 5.0],
                "비고": [None, None, None],
            }
        )
    )


def _incoming_baseline(process: str, category: str, count: float, note: str) -> pd.DataFrame:
    return prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": [process],
                "분류": [category],
                "기존보유대수": [count],
                "비고": [note],
            }
        )
    )


def test_equipment_csv_template_round_trips_with_31_columns() -> None:
    result = read_equipment_csv(equipment_csv_template())

    assert len(result.columns) == 31
    assert "사업부" not in result.columns
    assert result.columns.tolist()[5:7] == ["투자기준", "담당자"]
    # 환산비는 **맨 끝**이다. 중간에 끼우면 기존 붙여넣기 표의 열이 통째로 한 칸씩 밀린다.
    assert result.columns.tolist()[-1] == "환산비"
    assert len(result) == 1
    assert result.loc[0, "호기"] == SAMPLE_EQUIPMENT_ID
    assert result.loc[0, "담당자"] == SAMPLE_EQUIPMENT_MANAGER
    assert result.loc[0, "비고"] == SAMPLE_EQUIPMENT_NOTE
    assert result.loc[0, "확정상태"] == "계획"
    assert result.loc[0, "환산비"] == 1.0


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


def test_baseline_csv_template_round_trips_with_the_contract_columns() -> None:
    raw = pd.read_csv(BytesIO(baseline_csv_template()), dtype="object")
    result = read_baseline_csv(baseline_csv_template())

    assert raw.columns.tolist() == list(BASELINE_COLUMNS)
    assert len(result) == 1
    assert result.loc[0, "공정"] == SAMPLE_BASELINE_PROCESS
    assert result.loc[0, "분류"] == SAMPLE_BASELINE_CATEGORY
    assert result.loc[0, "기존보유대수"] == float(SAMPLE_BASELINE_COUNT)
    assert result.loc[0, "비고"] == SAMPLE_BASELINE_TEMPLATE_NOTE


def test_baseline_csv_template_carries_no_choice_rows() -> None:
    """공정·분류·기존보유대수 중 하나만 채워도 행이 남으므로 안내 행을 둘 수 없다."""
    assert len(baseline_csv_template().decode("utf-8-sig").splitlines()) == 2

    with pytest.raises(ValueError, match="기존 보유대수의 공정에 누락값이 있습니다."):
        read_baseline_clipboard(f"{BASELINE_HEADER}\n\t전체\t\t\n")


def test_baseline_template_round_trips_through_excel_clipboard() -> None:
    text = pd.read_csv(BytesIO(baseline_csv_template())).to_csv(index=False, sep="\t")

    result = read_baseline_clipboard(text)

    assert result.loc[0, "공정"] == SAMPLE_BASELINE_PROCESS
    assert result["기존보유대수"].dtype == "float64"


def test_baseline_merge_and_preview_replace_by_process_and_category() -> None:
    current = _baseline_rows()
    incoming = _incoming_baseline("Process-A", "전체", 9.0, "증설 반영")

    preview = build_baseline_import_preview(current, incoming)
    result = merge_baseline_rows(current, incoming)

    assert preview.loc[0, "Import구분"] == "대체"
    assert "기존보유대수" in preview.loc[0, "변경컬럼"]
    assert "2.0 → 9.0" in preview.loc[0, "변경내용"]
    assert len(result) == 3
    replaced = result.loc[result["공정"].eq("Process-A") & result["분류"].eq("전체")]
    assert replaced["기존보유대수"].item() == 9.0
    # 같은 공정의 다른 분류는 Import 대상이 아니므로 그대로 남아야 한다.
    kept = result.loc[result["공정"].eq("Process-A") & result["분류"].eq("임대")]
    assert kept["기존보유대수"].item() == 3.0


def test_baseline_import_preview_marks_a_new_category_as_new() -> None:
    current = _baseline_rows()
    incoming = _incoming_baseline("Process-B", "임대", 4.0, "신규 임대")

    preview = build_baseline_import_preview(current, incoming)
    result = merge_baseline_rows(current, incoming)

    assert preview["Import구분"].tolist() == ["신규"]
    assert preview["변경컬럼"].tolist() == ["-"]
    assert preview["변경내용"].tolist() == ["-"]
    assert len(result) == 4


def test_baseline_clipboard_takes_the_same_number_rule_as_the_editor() -> None:
    result = read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t1.5\t\n")

    assert result.loc[0, "기존보유대수"] == 1.5
    assert pd.isna(result.loc[0, "비고"])

    with pytest.raises(ValueError, match="기존보유대수는 0 이상의 숫자여야 합니다."):
        read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t1,200\t\n")
    with pytest.raises(ValueError, match="기존보유대수는 0 이상의 숫자여야 합니다."):
        read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t-1\t\n")


def test_baseline_clipboard_names_the_missing_contract_column() -> None:
    with pytest.raises(ValueError, match="기존 보유대수 필수 컬럼이 없습니다: 기존보유대수"):
        read_baseline_clipboard("공정\t분류\t비고\nProcess-A\t전체\t\n")


def test_baseline_clipboard_rejects_a_duplicated_natural_key() -> None:
    with pytest.raises(ValueError, match="기존 보유대수의 공정·분류가 중복되었습니다"):
        read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t1\t\nProcess-A\t전체\t2\t\n")


def test_out_of_canvas_coordinates_are_rejected_at_paste_and_import_time() -> None:
    """붙여넣기·CSV·병합 세 경로가 층 캔버스 상한을 그 자리에서 막는다."""
    # C1 1F 를 폭 40 으로 줄이면 EQ-02(30+12=42)가 캔버스를 벗어난다.
    canvases = {("C1", "1F"): (40.0, 60.0)}
    clipboard = _equipment().to_csv(index=False, sep="	")
    payload = _equipment().to_csv(index=False).encode("utf-8-sig")

    # 상한을 넘기지 않으면 예전처럼 통과한다. 과거 리비전이 계속 열려야 하기 때문이다.
    assert len(read_equipment_clipboard(clipboard)) == 2

    with pytest.raises(ValueError, match="층 캔버스"):
        read_equipment_clipboard(clipboard, floor_canvases=canvases)
    with pytest.raises(ValueError, match="층 캔버스"):
        read_equipment_csv(payload, floor_canvases=canvases)
    with pytest.raises(ValueError, match="층 캔버스"):
        merge_equipment_rows(
            _equipment().iloc[:1],
            _equipment().iloc[1:],
            floor_canvases=canvases,
        )
