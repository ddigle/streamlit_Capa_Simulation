# Purpose: Company-only BigDataQuery adapter for the shared Core Data pipeline.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

"""Company-only BigDataQuery adapter for the shared Core Data pipeline.

This module intentionally contains no CSV export.  Configure the SQL and source
column mapping in the marked section, then the Streamlit scenario page will pass
the returned DataFrame directly to the normalizer and DuckDB repository.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import ModuleType
from typing import Protocol, cast

import pandas as pd

from capa_simulation.io.core_data_source import CoreDataBatch

_SIMULATION_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_UNCONFIGURED_MARKER = "__TODO_CONFIGURE_BIGDATAQUERY__"

# ---------------------------------------------------------------------------
# 사내 환경 설정 영역
#
# 1) 아래 SQL을 실제 조회문으로 교체합니다.
# 2) 조건절의 {simulation_code}는 유지합니다.
# 3) DB 컬럼명이 Core Data 78컬럼명과 다르면 SOURCE_COLUMN_MAPPING에 등록합니다.
# ---------------------------------------------------------------------------
QUERY_TEMPLATE = f"""
SELECT {_UNCONFIGURED_MARKER}
FROM source_schema.source_table
WHERE simulation_code = '{{simulation_code}}'
"""

SOURCE_COLUMN_MAPPING: dict[str, str] = {
    # "db컬럼명": "Core Data 컬럼명",
}


class _BigDataQueryModule(Protocol):
    def getData(
        self,
        *,
        param: str,
        convert_type: bool,
        verbose: bool,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class BigDataQueryCoreDataProvider:
    """Fetch one simulation code and return a DataFrame without local files."""

    simulation_name: str
    source_registered_at: datetime | None = None
    query_template: str = QUERY_TEMPLATE
    column_mapping: Mapping[str, str] = field(default_factory=lambda: SOURCE_COLUMN_MAPPING.copy())

    def fetch(self, simulation_code: str) -> CoreDataBatch:
        code = _validated_simulation_code(simulation_code)
        query = build_query(self.query_template, code)
        module = cast(_BigDataQueryModule, _load_bigdataquery_module())
        frame = module.getData(
            param=query,
            convert_type=True,
            verbose=True,
        )
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("bigdataquery.getData() 반환값은 pandas DataFrame이어야 합니다.")
        renamed = frame.rename(columns=dict(self.column_mapping)).copy()
        return CoreDataBatch(
            simulation_code=code,
            simulation_name=self.simulation_name,
            source_type="BIGDATAQUERY",
            frame=renamed,
            source_registered_at=self.source_registered_at,
        )


def build_query(query_template: str, simulation_code: str) -> str:
    """Validate the local adapter configuration and render one safe query."""
    if _UNCONFIGURED_MARKER in query_template:
        raise RuntimeError(
            "BigDataQuery SQL이 아직 설정되지 않았습니다. "
            "company_bigdataquery_adapter.py의 QUERY_TEMPLATE을 실제 SQL로 교체하세요."
        )
    if "{simulation_code}" not in query_template:
        raise ValueError("BigDataQuery SQL에는 {simulation_code} 조건 자리가 필요합니다.")
    code = _validated_simulation_code(simulation_code)
    return query_template.format(simulation_code=code)


def is_bigdataquery_adapter_configured() -> bool:
    return _UNCONFIGURED_MARKER not in QUERY_TEMPLATE and "{simulation_code}" in QUERY_TEMPLATE


def _validated_simulation_code(value: str) -> str:
    code = value.strip()
    if not code:
        raise ValueError("시뮬레이션 코드는 비어 있을 수 없습니다.")
    if _SIMULATION_CODE_PATTERN.fullmatch(code) is None:
        raise ValueError("시뮬레이션 코드는 영문·숫자와 '.', '_', '-'만 사용할 수 있습니다.")
    return code


def _load_bigdataquery_module() -> ModuleType:
    try:
        return importlib.import_module("bigdataquery")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "현재 환경에 bigdataquery 패키지가 없습니다. "
            "사내 전용 가상환경에서 실행하거나 사내 requirements를 적용하세요."
        ) from exc
