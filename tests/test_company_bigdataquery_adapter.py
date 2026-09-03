# Purpose: company bigdataquery adapter 관련 정상·예외·회귀 동작을 검증한다.

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from capa_simulation.io import company_bigdataquery_adapter as adapter


def test_unconfigured_query_is_rejected_before_package_import(monkeypatch) -> None:
    imported = False

    def fake_import(_: str) -> object:
        nonlocal imported
        imported = True
        return object()

    monkeypatch.setattr(adapter.importlib, "import_module", fake_import)
    provider = adapter.BigDataQueryCoreDataProvider("사내 조회")

    with pytest.raises(RuntimeError, match="SQL이 아직 설정되지 않았습니다"):
        provider.fetch("SIM-001")

    assert not imported


def test_provider_returns_renamed_dataframe_without_csv(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get_data(*, param: str, convert_type: bool, verbose: bool) -> pd.DataFrame:
        captured.update(
            param=param,
            convert_type=convert_type,
            verbose=verbose,
        )
        return pd.DataFrame({"db_product": ["Product*_A"]})

    monkeypatch.setattr(
        adapter.importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=fake_get_data),
    )
    provider = adapter.BigDataQueryCoreDataProvider(
        "사내 조회",
        query_template="SELECT * FROM source WHERE simulation_code = '{simulation_code}'",
        column_mapping={"db_product": "제품정보"},
    )

    batch = provider.fetch("SIM-001")

    assert batch.source_type == "BIGDATAQUERY"
    assert batch.frame.columns.tolist() == ["제품정보"]
    assert captured == {
        "param": "SELECT * FROM source WHERE simulation_code = 'SIM-001'",
        "convert_type": True,
        "verbose": True,
    }


@pytest.mark.parametrize("code", ["SIM 001", "SIM'001", "한글코드"])
def test_provider_rejects_unsafe_simulation_code(code: str) -> None:
    with pytest.raises(ValueError, match="영문·숫자"):
        adapter.build_query("SELECT '{simulation_code}'", code)
