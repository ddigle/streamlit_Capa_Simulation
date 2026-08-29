from capa_simulation.services.equipment_csv import (
    equipment_csv_template,
    merge_equipment_rows,
    read_equipment_csv,
)
from tests.test_equipment_availability import _equipment


def test_equipment_csv_template_round_trips() -> None:
    result = read_equipment_csv(equipment_csv_template())

    assert result.empty


def test_equipment_csv_merge_updates_by_equipment_id() -> None:
    current = _equipment()
    incoming = current.iloc[[0]].copy()
    incoming.loc[incoming.index[0], "공정"] = "Changed"

    result = merge_equipment_rows(current, incoming)

    assert len(result) == 2
    assert result.loc[result["호기"].eq("EQ-01"), "공정"].item() == "Changed"
