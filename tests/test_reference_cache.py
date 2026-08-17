from pathlib import Path

import pandas as pd

from capa_simulation.io import reference_cache


def test_reference_tables_are_loaded_once_until_explicit_clear(monkeypatch) -> None:
    calls: list[Path] = []

    def fake_loader(workbook_path: Path) -> dict[str, pd.DataFrame]:
        calls.append(workbook_path)
        return {"RQ_TEST": pd.DataFrame({"value": [1]})}

    monkeypatch.setattr(reference_cache, "load_reference_tables", fake_loader)
    reference_cache.get_reference_tables.clear()

    first = reference_cache.get_reference_tables("C:/test/structure_template.xlsb")
    second = reference_cache.get_reference_tables("C:/test/structure_template.xlsb")

    assert first["RQ_TEST"].equals(second["RQ_TEST"])
    assert calls == [Path("C:/test/structure_template.xlsb")]

    reference_cache.get_reference_tables.clear()
    reference_cache.get_reference_tables("C:/test/structure_template.xlsb")

    assert calls == [
        Path("C:/test/structure_template.xlsb"),
        Path("C:/test/structure_template.xlsb"),
    ]
    reference_cache.get_reference_tables.clear()
