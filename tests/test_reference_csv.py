# Purpose: reference csv 관련 정상·예외·회귀 동작을 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.equipment_count import (
    equipment_count_from_edit_table,
    equipment_count_to_edit_table,
)
from capa_simulation.services.reference_csv import (
    parse_reference_edit_clipboard,
    parse_reference_edit_csv,
    reference_edit_csv_bytes,
)


def _template() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Process-B", "Process-A"],
            "양산구분": ["양산", "ER"],
            "202608": [0.9, 0.8],
            "202609": [0.91, 0.81],
        }
    )


def test_reference_csv_round_trip_preserves_template_row_order() -> None:
    template = _template()
    modified = template.iloc[::-1].reset_index(drop=True)
    modified.loc[modified["공정"].eq("Process-A"), "202608"] = 0.75

    result = parse_reference_edit_csv(
        reference_edit_csv_bytes(modified),
        template,
        ["공정", "양산구분"],
        "RQ_RUN_RATE",
    )

    assert result["공정"].tolist() == ["Process-B", "Process-A"]
    assert float(result.loc[1, "202608"]) == pytest.approx(0.75)


def test_reference_clipboard_round_trip_preserves_template_row_order() -> None:
    template = _template()
    modified = template.iloc[::-1].reset_index(drop=True)
    modified.loc[modified["공정"].eq("Process-A"), "202608"] = 0.75

    result = parse_reference_edit_clipboard(
        modified.to_csv(index=False, sep="\t"),
        template,
        ["공정", "양산구분"],
        "RQ_RUN_RATE",
    )

    assert result["공정"].tolist() == ["Process-B", "Process-A"]
    assert float(result.loc[1, "202608"]) == pytest.approx(0.75)


def test_reference_csv_rejects_changed_classification_rows() -> None:
    template = _template()
    changed = template.copy()
    changed.loc[0, "공정"] = "Unknown"

    with pytest.raises(ValueError, match="분류 행"):
        parse_reference_edit_csv(
            reference_edit_csv_bytes(changed),
            template,
            ["공정", "양산구분"],
            "RQ_RUN_RATE",
        )


def test_equipment_count_csv_round_trip_validates_nonnegative_values() -> None:
    source = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Process-A", "Process-A"],
            "가용대수": [2.0, 3.0],
        }
    )
    edit = equipment_count_to_edit_table(source, "가용", "가용대수")
    edit.loc[0, "202609"] = 4.0

    restored = equipment_count_from_edit_table(edit, "가용", "가용대수")

    assert restored["가용대수"].tolist() == [2.0, 4.0]
    edit.loc[0, "202609"] = -1.0
    with pytest.raises(ValueError, match="0 이상"):
        equipment_count_from_edit_table(edit, "가용", "가용대수")
