# Purpose: 계산 페이지 공통의 리비전·표시순서·조회기간 준비, Capa 계산 호출, 위젯·팝업 상태 정규화.

"""Shared entry sequence for the calculation pages.

Static Capa 하위 5개 페이지가 같은 40여 줄을 각자 재구현하면서 조금씩 갈라져 있었다.
특히 잡는 예외가 페이지마다 달라 어떤 페이지는 친절한 안내를, 어떤 페이지는 스택
트레이스를 보여줬다. 준비 절차를 여기 한 곳에 둔다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import duckdb
import pandas as pd
import streamlit as st

# 페이지 테스트가 이 두 모듈의 속성을 교체해 활성 리비전을 흉내낸다. 이름을 직접
# import 하면 여기서 잡은 바인딩이 교체를 무시하므로 호출 시점에 모듈에서 찾는다.
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.scenario_state import ActiveScenario
from capa_simulation.services.display_order import (
    PreparedDisplayOrder,
    prepare_display_order,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.settings import (
    DUCKDB_PATH,
    MONTH_SELECTION_END,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import (
    show_applied_month_range,
    show_calculation_stopped,
    show_month_range_unavailable,
)

# 페이지 준비 단계에서 실제로 나올 수 있는 예외다. 활성 리비전이 없으면 RuntimeError,
# 기준정보 컬럼이 비면 KeyError·ValueError·TypeError 다. **DuckDB 실패는 OSError 가
# 아니다** — `duckdb.IOException` 의 MRO 는 OperationalError → DatabaseError → duckdb.Error
# → Exception 이라 표준 예외 어느 것에도 걸리지 않는다. 그래서 파일 잠금(다른 프로세스가
# 열어 둔 DB)이나 스키마 오류가 원문 트레이스백으로, Windows 에서는 한글까지 깨진 채
# 그대로 노출됐다. 페이지·컴포넌트는 각자 튜플을 만들지 말고 이것을 쓴다.
BOOTSTRAP_ERRORS = (KeyError, OSError, RuntimeError, TypeError, ValueError, duckdb.Error)

# 페이지가 연 팝업(`st.dialog`)의 열림 상태 키는 이 접미어로 끝난다. 팝업은 열림 상태가 세션에
# 있는 동안 매 회차 다시 그리는데, 닫지 않은 채(브라우저 뒤로 가기 등) 페이지를 떠나면
# `on_dismiss` 가 불리지 않아 상태가 남고, 돌아왔을 때 요청하지 않은 팝업이 뜬다. 그래서
# 페이지가 바뀐 회차에 `app.py` 가 이 접미어의 키를 모두 버린다(`forget_page_dialogs`).
PAGE_DIALOG_SUFFIX = "_open_dialog"


def forget_page_dialogs() -> None:
    """페이지가 바뀐 회차에 부른다. 떠난 페이지의 팝업 열림 상태를 버린다."""
    for key in [key for key in st.session_state if str(key).endswith(PAGE_DIALOG_SUFFIX)]:
        st.session_state.pop(key, None)


def bootstrap_error_message(
    exc: BaseException, *, database_paths: Sequence[Path] = (DUCKDB_PATH,)
) -> str:
    """화면에 보여 줄 오류 문구.

    DuckDB 예외는 원문이 사용자에게 아무 도움이 안 된다(잠금 경로와 영어 문장, Windows
    로캘에서는 한글이 깨진다). 원인이 거의 항상 "이미 다른 창에서 실행 중" 이므로 그 안내로
    바꾼다. 나머지 예외는 서비스 계층이 이미 한국어로 만든 문장이라 그대로 쓴다.

    **어느 파일이 잠겼는지는 부르는 쪽만 안다.** 이 앱은 DB 가 둘이고(시뮬레이션·설비) 한
    `try` 가 둘 다 받는 자리도 있다. 경로를 여기에 박아 두면 설비 DB 가 잠겼을 때 사용자가
    멀쩡한 시뮬레이션 파일을 들여다보게 된다.
    """
    if isinstance(exc, duckdb.Error):
        files = "\n".join(f"- 파일: `{path}`" for path in database_paths)
        return (
            "데이터베이스를 열지 못했습니다.\n\n"
            f"{files}\n"
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


def date_range_value(value: object, default: tuple[date, date]) -> tuple[date, date]:
    """범위 모드 `st.date_input` 의 반환값을 시작·종료 두 날짜로 읽는다.

    같은 위젯이 세 가지를 돌려준다 — 두 날짜가 다 정해지면 길이 2 튜플, 사용자가 시작일만
    누른 중간 상태에서는 길이 1 튜플, 단일 날짜 모드에서는 `date` 하나다. 페이지마다 이
    세 갈래를 다시 적으면 한쪽만 고쳐져 화면끼리 기간 해석이 갈린다.
    """
    if isinstance(value, tuple) and len(value) == 2:
        return cast("tuple[date, date]", value)
    if isinstance(value, date):
        return value, value
    return default


def prune_list_selection(
    key: str, options: Sequence[str], *, default: Sequence[str] = ()
) -> list[str]:
    """저장된 다중 선택에서 지금 옵션에 없는 값을 떨어내고 세션에 되쓴다.

    옵션이 계산 결과라 시나리오·조회기간이 바뀌면 목록이 통째로 달라진다. 옛 선택을
    그대로 두면 `st.multiselect` 가 옵션에 없는 기본값을 받아 오류를 내거나 조용히 빈
    화면을 그린다. 아직 아무것도 고르지 않은 세션에는 `default` 를 심는다.
    """
    allowed = set(options)
    saved = st.session_state.get(key)
    if not isinstance(saved, list):
        saved = list(default)
    pruned = [str(value) for value in saved if str(value) in allowed]
    st.session_state[key] = pruned
    return pruned


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
            f"{empty_message} (데이터 범위 {month_label(source_start_month)}–"
            f"{month_label(source_end_month)})"
        )
    show_applied_month_range(effective_start_month, effective_end_month)
    return effective_start_month, effective_end_month


def scenario_capacity_and_demand(
    cache_key: simulation_cache.ScenarioCacheKey,
    *,
    scenario_tables: Mapping[str, pd.DataFrame],
    reference_tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """활성 시나리오의 대당 Capa·소요대수. 계산이 멈추면 사이드바의 「✓ 적용」을 거둔다.

    `resolve_effective_months` 가 먼저 「✓ 적용」을 쓴 뒤에 부르는 자리다. 계산은 시나리오 전체
    기간으로 하므로 조회기간 밖 달의 기준정보 오류로도 멈추는데(ValueError), 그때 사이드바가
    「✓ 적용」인 채로 남으면 본문 「계산을 멈췄습니다」와 어긋난다. 예외는 그대로 다시 던진다 —
    본문에 무엇을 보일지는 페이지가 정한다.

    계산 함수는 **부를 때** 모듈에서 찾는다. 페이지 테스트가 그 속성을 바꿔 계산을 흉내 낸다.
    """
    try:
        return simulation_cache.get_scenario_capacity_and_demand(
            cache_key,
            _scenario_tables=scenario_tables,
            _reference_tables=reference_tables,
        )
    except ValueError:
        show_calculation_stopped()
        raise
