# Purpose: bigdataquery 카탈로그 조회의 SQL 렌더·검증 순서·계약 컬럼을 검증한다.

from __future__ import annotations

import importlib
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from capa_simulation.io import bigdataquery_catalog as catalog
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow

WINDOW = QueryWindow(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8))


def _catalog_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "simulation_name": ["DEMO 시뮬레이션"],
            "simulation_code": ["DEMO-A-001"],
            "plan_name": ["DEMO PLAN"],
            "plan_code": ["DEMO-PLAN-001"],
            "regist_data": ["2026-09-02 03:04:05"],
        }
    )


def test_catalog_sql_keeps_the_given_statement_verbatim() -> None:
    """별칭 5개가 곧 사내 결과 계약이다. 상수를 손보면 화면 자동 입력이 통째로 어긋난다."""
    for column in catalog.CATALOG_COLUMNS:
        assert f"AS {column}" in catalog.CATALOG_QUERY_TEMPLATE
    assert "SELECT DISTINCT" in catalog.CATALOG_QUERY_TEMPLATE
    assert "camp_tsp.campavp_catb_sim_rslt_report" in catalog.CATALOG_QUERY_TEMPLATE


def test_catalog_query_renders_only_the_two_date_slots() -> None:
    query = catalog.build_catalog_query(WINDOW)

    # 상한은 종료일 다음 날이다(종료일 포함).
    assert "'2026-09-01'" in query
    assert "'2026-09-09'" in query
    assert "{" not in query


def test_unconfigured_catalog_sql_is_rejected_before_package_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = False

    def fake_import(_: str) -> object:
        nonlocal imported
        imported = True
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import)

    with pytest.raises(RuntimeError, match="목록 조회 SQL이 아직 설정되지 않았습니다"):
        catalog.fetch_simulation_catalog(
            WINDOW,
            query_template=f"SELECT {adapter.UNCONFIGURED_MARKER}",
        )

    assert not imported


def test_missing_date_slot_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\{end_date\} 조건 자리"):
        catalog.build_catalog_query(WINDOW, query_template="SELECT 1 WHERE a >= '{start_date}'")


def test_window_longer_than_the_limit_is_rejected_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = False

    def fake_import(_: str) -> object:
        nonlocal imported
        imported = True
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import)
    too_wide = QueryWindow(start_date=date(2025, 1, 1), end_date=date(2026, 9, 8))

    with pytest.raises(ValueError, match="최대 366일"):
        catalog.fetch_simulation_catalog(too_wide)

    assert not imported


def test_catalog_result_keeps_contract_columns_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """여분 컬럼·뒤섞인 순서에서도 5컬럼·0..n-1 인덱스로 정렬한다.

    화면 선택이 위치 인덱스로 돌아오므로 여기서 컬럼·인덱스를 고정하지 않으면 라벨과
    위치가 어긋나 다른 코드가 선택된다.
    """
    frame = _catalog_frame()[["regist_data", "plan_code", "plan_name", "simulation_code"]].copy()
    frame["simulation_name"] = ["DEMO 시뮬레이션"]
    frame["여분"] = ["버릴 값"]
    frame.index = [7]

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=lambda **_kwargs: frame),
    )

    result = catalog.fetch_simulation_catalog(WINDOW)

    assert result.columns.tolist() == list(catalog.CATALOG_COLUMNS)
    assert result.index.tolist() == [0]


def test_non_dataframe_result_raises_type_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=lambda **_kwargs: [1, 2, 3]),
    )

    with pytest.raises(TypeError, match="pandas DataFrame"):
        catalog.fetch_simulation_catalog(WINDOW)


def test_missing_alias_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _catalog_frame().drop(columns=["plan_code"])
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=lambda **_kwargs: frame),
    )

    with pytest.raises(ValueError, match="plan_code"):
        catalog.fetch_simulation_catalog(WINDOW)


def test_get_data_is_called_with_the_shared_keyword_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_get_data(*, param: str, convert_type: bool, verbose: bool) -> pd.DataFrame:
        captured.update(param=param, convert_type=convert_type, verbose=verbose)
        return _catalog_frame()

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda _: SimpleNamespace(getData=fake_get_data),
    )

    catalog.fetch_simulation_catalog(WINDOW)

    assert captured["convert_type"] is True
    assert captured["verbose"] is True
    assert "SELECT DISTINCT" in str(captured["param"])


def test_catalog_configuration_is_independent_of_the_detail_sql() -> None:
    """어느 SQL 이 비었는지 화면 문구가 갈려야 하므로 판정이 분리돼 있어야 한다."""
    assert catalog.is_bigdataquery_catalog_configured() is True
    assert catalog.is_bigdataquery_catalog_configured("SELECT 1") is False
    assert adapter.is_bigdataquery_adapter_configured() is True
