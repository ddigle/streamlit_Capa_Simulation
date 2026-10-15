# Purpose: Power Query 대조 스크립트가 앱의 등록 보정을 Power Query 결과에도 거는지 검증한다.

"""`scripts/validate_duckdb_persistence.py` 는 Windows·Excel 에서만 끝까지 돈다. 그 가운데 Excel 이
필요 없는 부분 — Power Query 결과에 앱의 보정(빈 대여평가 0 대·표기만 다른 경로 접기)을 거는
`with_app_corrections` — 만 여기서 본다. 보정을 빠뜨리면 원천에 빈 대여평가나 표기만 다른 경로가
있을 때 스크립트가 「Power Query match」에서 실패한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_duckdb_persistence.py"


def _script() -> ModuleType:
    name = "validate_duckdb_persistence_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _monthly(column: str, values: list[float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {"생산계획년월": [202608, 202609], "공정": ["Process-A", "Process-A"], column: values}
    )


def test_power_query_tables_get_the_app_corrections_before_comparison() -> None:
    route = {
        "생산계획년월": 202608,
        "Area_Name": "Main",
        "공정": "Process-A",
        "양산구분": "양산",
        "제품정보": "Product-A",
        "Stack": "12H",
        "Capa Code": "CAPA-A",
        "Customer": "Customer-A",
        "CS": "MP",
        "WF 구분": "Core",
        "STEP_SEQ": "10",
        "MCP_SEQ": "1",
        "소요기준": "WF",
    }
    plan = pd.DataFrame({"생산계획년월": [202608], "생산수량": [100.0]})
    power_query = {
        "RQ_EQP_OWN": _monthly("설비보유", [12.0, 12.0]),
        "RQ_EQP_LENT": _monthly("설비대여평가", [2.0, None]),
        "RQ_EQP_AVBL": _monthly("가용대수", [10.0, None]),
        "RQ_REQB": pd.DataFrame(
            [route, {**route, "소요기준": "Wafer"}, {**route, "공정": "Process-B"}]
        ),
        "RQ_PKG_PLAN": plan,
    }

    corrected = _script().with_app_corrections(power_query)

    assert corrected["RQ_EQP_LENT"]["설비대여평가"].tolist() == pytest.approx([2.0, 0.0])
    assert corrected["RQ_EQP_AVBL"]["가용대수"].tolist() == pytest.approx([10.0, 12.0])
    assert corrected["RQ_REQB"][["공정", "소요기준"]].to_dict("records") == [
        {"공정": "Process-A", "소요기준": "WF"},
        {"공정": "Process-B", "소요기준": "WF"},
    ]
    assert corrected["RQ_PKG_PLAN"] is plan
    assert power_query["RQ_EQP_LENT"]["설비대여평가"].isna().sum() == 1
