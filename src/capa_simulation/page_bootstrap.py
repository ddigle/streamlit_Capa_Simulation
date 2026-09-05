# Purpose: 계산 페이지가 공통으로 거치는 활성 리비전·표시순서·조회기간 준비를 제공한다.

"""Shared entry sequence for the calculation pages.

Static Capa 하위 5개 페이지가 같은 40여 줄을 각자 재구현하면서 조금씩 갈라져 있었다.
특히 잡는 예외가 페이지마다 달라 어떤 페이지는 친절한 안내를, 어떤 페이지는 스택
트레이스를 보여줬다. 준비 절차를 여기 한 곳에 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd
import streamlit as st

# 페이지 테스트가 이 두 모듈의 속성을 교체해 활성 리비전을 흉내낸다. 이름을 직접
# import 하면 여기서 잡은 바인딩이 교체를 무시하므로 호출 시점에 모듈에서 찾는다.
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.scenario_state as scenario_state
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.scenario_state import ActiveScenario
from capa_simulation.services.display_order import (
    PreparedDisplayOrder,
    prepare_display_order,
)
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.settings import (
    DUCKDB_PATH,
    MONTH_SELECTION_END,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import (
    format_short_month,
    show_applied_month_range,
    show_month_range_unavailable,
)

# 페이지 준비 단계에서 실제로 나올 수 있는 예외다. 활성 리비전이 없으면 RuntimeError,
# 기준정보 컬럼이 비면 KeyError·ValueError·TypeError 다. **DuckDB 실패는 OSError 가
# 아니다** — `duckdb.IOException` 의 MRO 는 OperationalError → DatabaseError → duckdb.Error
# → Exception 이라 표준 예외 어느 것에도 걸리지 않는다. 그래서 파일 잠금(다른 프로세스가
# 열어 둔 DB)이나 스키마 오류가 원문 트레이스백으로, Windows 에서는 한글까지 깨진 채
# 그대로 노출됐다. 페이지·컴포넌트는 각자 튜플을 만들지 말고 이것을 쓴다.
BOOTSTRAP_ERRORS = (KeyError, OSError, RuntimeError, TypeError, ValueError, duckdb.Error)


def bootstrap_error_message(exc: BaseException) -> str:
    """화면에 보여 줄 오류 문구.

    DuckDB 예외는 원문이 사용자에게 아무 도움이 안 된다(잠금 경로와 영어 문장, Windows
    로캘에서는 한글이 깨진다). 원인이 거의 항상 "이미 다른 창에서 실행 중" 이므로 그 안내로
    바꾼다. 나머지 예외는 서비스 계층이 이미 한국어로 만든 문장이라 그대로 쓴다.
    """
    if isinstance(exc, duckdb.Error):
        return (
            "시나리오 데이터베이스를 열지 못했습니다.\n\n"
            f"- 파일: `{DUCKDB_PATH}`\n"
            "- 이 앱이 이미 다른 창에서 실행 중이면 그 창을 닫고 다시 시작하세요. "
            "DuckDB 는 한 번에 한 프로세스만 파일을 엽니다.\n"
            "- 그래도 같은 오류가 나면 파일 권한과 경로(네트워크 드라이브 여부)를 확인하세요."
        )
    return str(exc)


@dataclass(frozen=True)
class PageContext:
    """계산 페이지가 시작할 때 필요한 활성 상태 묶음."""

    reference_version: int
    reference_tables: dict[str, pd.DataFrame]
    display_order: PreparedDisplayOrder | None
    active_scenario: ActiveScenario
    selected_start_month: int
    selected_end_month: int


def selected_month_range() -> tuple[int, int]:
    """사이드바 조회기간을 정수 `YYYYMM` 두 개로 읽는다.

    위젯이 아직 만들어지기 전이거나 상태가 깨져 있어도 기본 범위로 되돌아간다.
    """
    default = (format_month(MONTH_SELECTION_START), format_month(MONTH_SELECTION_END))
    value = st.session_state.get(MONTH_RANGE_KEY, default)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        value = default
    start_label, end_label = (str(value[0]), str(value[1]))
    return int(start_label.replace("-", "")), int(end_label.replace("-", ""))


def load_page_context() -> PageContext:
    """활성 리비전·표시순서·활성 시나리오와 선택 조회기간을 한 번에 준비한다."""
    reference_version = reference_cache.get_effective_reference_version()
    reference_tables = reference_cache.get_effective_reference_tables()
    display_order = prepare_display_order(reference_tables["RQ_DISPLAY_ORDER"])
    active_scenario = scenario_state.ensure_active_scenario(reference_tables, reference_version)
    selected_start_month, selected_end_month = selected_month_range()
    return PageContext(
        reference_version=reference_version,
        reference_tables=reference_tables,
        display_order=display_order,
        active_scenario=active_scenario,
        selected_start_month=selected_start_month,
        selected_end_month=selected_end_month,
    )


def resolve_effective_months(
    context: PageContext,
    source: pd.DataFrame,
    table_name: str,
    *,
    empty_message: str,
) -> tuple[int, int]:
    """선택 조회기간과 원천 데이터가 겹치는 구간을 확정하고 사이드바에 표시한다."""
    source_start_month, source_end_month = available_month_range(source, table_name)
    effective_start_month = max(context.selected_start_month, source_start_month)
    effective_end_month = min(context.selected_end_month, source_end_month)
    if effective_start_month > effective_end_month:
        # 사이드바 자리표시자를 비워 두면 직전 rerun 의 "적용 · 26.01–26.12" 가 본문의
        # "데이터가 없습니다" 옆에 그대로 남는다. 데이터가 있는 범위를 같이 알려 줘야
        # 사용자가 어디로 옮겨야 하는지 안다.
        show_month_range_unavailable()
        raise ValueError(
            f"{empty_message} (데이터 범위 {format_short_month(source_start_month)}–"
            f"{format_short_month(source_end_month)})"
        )
    show_applied_month_range(effective_start_month, effective_end_month)
    return effective_start_month, effective_end_month
