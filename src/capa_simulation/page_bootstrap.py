# Purpose: 계산 페이지 공통의 리비전·표시순서·조회기간 준비, Capa 계산 호출, 위젯·팝업 상태 정규화.

"""Shared entry sequence for the calculation pages.

계산 페이지(Static Capa 와 그 하위, 공정 Capa 상세·가용설비 현황)가 같은 40여 줄을 각자
재구현하면서 조금씩 갈라져 있었다.
특히 잡는 예외가 페이지마다 달라 어떤 페이지는 친절한 안내를, 어떤 페이지는 스택
트레이스를 보여줬다. 준비 절차를 여기 한 곳에 둔다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import ParamSpec, TypeVar, cast, overload

import duckdb
import pandas as pd
import streamlit as st

# 페이지 테스트가 이 두 모듈의 속성을 교체해 활성 리비전을 흉내낸다. 이름을 직접
# import 하면 여기서 잡은 바인딩이 교체를 무시하므로 호출 시점에 모듈에서 찾는다.
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.persistence._sql_helpers import is_own_process_lock, lock_holder_pid
from capa_simulation.persistence.cache import load_global_securement_threshold
from capa_simulation.persistence.migration_runner import SchemaAheadOfCode
from capa_simulation.scenario_preset_state import MONTH_RANGE_KEY
from capa_simulation.scenario_state import ActiveScenario
from capa_simulation.services.display_order import PreparedDisplayOrder
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_SECUREMENT
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.securement_threshold import SecurementThresholds
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

_P = ParamSpec("_P")
_T = TypeVar("_T")

# 페이지가 연 팝업(`st.dialog`)의 열림 상태 키는 이 접미어로 끝난다. 팝업은 열림 상태가 세션에
# 있는 동안 매 회차 다시 그리는데, 닫지 않은 채(브라우저 뒤로 가기 등) 페이지를 떠나면
# `on_dismiss` 가 불리지 않아 상태가 남고, 돌아왔을 때 요청하지 않은 팝업이 뜬다. 그래서
# 페이지가 바뀐 회차에 `app.py` 가 이 접미어의 키를 모두 버린다(`forget_page_dialogs`).
PAGE_DIALOG_SUFFIX = "_open_dialog"


def forget_page_dialogs() -> None:
    """페이지가 바뀐 회차에 부른다. 떠난 페이지의 팝업 열림 상태를 버린다."""
    for key in [key for key in st.session_state if str(key).endswith(PAGE_DIALOG_SUFFIX)]:
        st.session_state.pop(key, None)


# 페이지가 바뀐 회차마다 하나씩 오르는 수(`count_page_visit`). Streamlit 은 그 회차에 그리지 않은
# 위젯의 값을 버리는데, 서버만 보면 「다른 화면을 다녀와 입력 칸이 비었다」와 「같은 화면의
# `st.rerun()` 이 본문을 건너뛰었다(브라우저가 입력을 다시 보낸다)」가 똑같다. 위젯 값에서 나온
# 위젯 아닌 칸(미리보기 등)을 두는 화면은 이 수가 바뀐 회차에만 그 칸을 거둔다.
PAGE_VISIT_KEY = "page_visit_count"


def page_visit() -> int:
    """지금 페이지에 들어온 차례. 같은 페이지에 머무는 동안은 그대로다."""
    value = st.session_state.get(PAGE_VISIT_KEY, 0)
    return value if isinstance(value, int) else 0


def count_page_visit() -> None:
    """페이지가 바뀐 회차에 `app.py` 가 부른다. 팝업 콜백의 `forget_page_dialogs` 와 달리 같은
    페이지 안에서는 부르지 않는다."""
    st.session_state[PAGE_VISIT_KEY] = page_visit() + 1


# DuckDB 가 파일에 쓰다 실패할 때 내는 영문 고정 문구 — 파일 쓰기(「Could not write
# file」·「Could not write to file」)와 커밋(「Failed to commit」)이다. 디스크 가득·파일
# 크기 한도·쓰기 권한이 여기로 온다. 뒤에 붙는 OS 문구는 로캘을 타지만(Windows 에서는
# 한글) 이 낱말은 DuckDB 가 영문으로 박아 둔 것이다.
_WRITE_FAILURE_MARKERS = ("Could not write", "Failed to commit")
# 파일을 열거나 잠그다 실패한 `IOException` 의 영문 고정 문구 — 없는 폴더·권한·쥔
# 프로세스를 적지 않은 공유 위반이다. 쥔 프로세스가 적힌 잠금은 그 앞에서 따로 가른다.
_OPEN_FAILURE_MARKERS = ("Cannot open", "Could not set lock")
# 화면에 옮기는 원문 길이. DuckDB 문구에는 SQL 줄과 위치 표시가 붙어 길어진다.
_ORIGINAL_TEXT_LIMIT = 300
_BACKTICK_RUN = re.compile(r"`+")


def _original_line(exc: BaseException) -> str:
    """오류 문구 끝에 붙이는 원문 한 줄 — 종류 이름과 문구 앞 `_ORIGINAL_TEXT_LIMIT` 자.

    마크다운으로 그려도 글자 그대로 보이게 코드 표기로 싼다(`$`·`*` 가 수식·강조가 되지 않는다).
    줄바꿈은 빈칸으로 접는다 — 코드 표기 안이라도 줄 머리의 `#`·`-` 는 제목·목록으로 먼저 읽힌다.
    울타리는 원문의 가장 긴 역따옴표 줄보다 하나 길게 한다 — 같은 길이면 코드 표기가 중간에 닫힌다.
    """
    text = " ".join(str(exc).split())
    if len(text) > _ORIGINAL_TEXT_LIMIT:
        text = text[:_ORIGINAL_TEXT_LIMIT] + " …"
    body = f"{type(exc).__name__}: {text or '(문구 없음)'}"
    fence = "`" * (max((len(run) for run in _BACKTICK_RUN.findall(body)), default=0) + 1)
    return f"- 원문: {fence} {body} {fence}"


def bootstrap_error_message(
    exc: BaseException, *, database_paths: Sequence[Path] = (DUCKDB_PATH,)
) -> str:
    """화면에 보여 줄 오류 문구.

    DuckDB 예외는 원문만으로는 사용자에게 도움이 안 된다(잠금 경로와 영어 문장, Windows
    로캘에서는 한글이 깨진다). 그래서 갈래마다 맞는 조치로 바꾼다 — 잠금은 **잠금을 쥔
    쪽**에, 쓰기 실패(`_WRITE_FAILURE_MARKERS`)는 「저장되지 않았다·디스크 공간과 쓰기
    권한」에, 그 밖의 열기 실패(`_OPEN_FAILURE_MARKERS`)는 「다른 프로그램·파일 권한과
    경로」에 맞춘다. 어느 갈래도 아니면 「작업이 실패했다」만 말한다. 쓰기 실패와 그 밖은
    조치가 원인을 다 짚지 못하므로 원문(`_original_line`)을 붙인다. 나머지 예외는 서비스
    계층이 이미 한국어로 만든 문장이라 그대로 쓴다. 서명은 그대로 둔다 — 화면 수십 곳과
    동기화 스크립트가 같은 꼴로 부른다.

    잠금을 쥔 것이 **이 앱 자신**이면 닫을 것이 없다(2026-10-01, E2E G1-D0). 한 서버가
    모든 브라우저 창·탭을 받으므로 창을 닫는 것은 조치가 아니다 — 예전 문구가 「다른 창을
    닫으라」고 해 빈 DB 첫 방문에서 틀린 조치를 권했다. 자기 잠금은 `connect()` 가 이미
    기다렸다 다시 연 뒤에도 남은 경우라 새로고침을 권한다.

    **어느 파일이 잠겼는지는 부르는 쪽만 안다.** 이 앱은 DB 가 둘이고(시뮬레이션·설비) 한
    `try` 가 둘 다 받는 자리도 있다. 경로를 여기에 박아 두면 설비 DB 가 잠겼을 때 사용자가
    멀쩡한 시뮬레이션 파일을 들여다보게 된다.
    """
    if not isinstance(exc, duckdb.Error):
        return str(exc)
    files = "\n".join(f"- 파일: `{path}`" for path in database_paths)
    if is_own_process_lock(exc):
        return (
            "데이터베이스를 열지 못했습니다 — 이 앱이 같은 파일을 정리하는 동안 연결이 "
            "겹쳤습니다.\n\n"
            f"{files}\n"
            "- 잠시 뒤 화면을 새로고침(F5)하면 이어집니다. 다른 창이나 프로그램을 닫을 필요는 "
            "없습니다."
        )
    holder = lock_holder_pid(exc)
    if holder is not None:
        return (
            "데이터베이스를 열지 못했습니다 — 다른 프로그램이 파일을 열어 두었습니다.\n\n"
            f"{files}\n"
            f"- 파일을 연 프로세스: PID {holder}. DuckDB 는 한 번에 한 프로세스만 파일을 "
            "엽니다. 이 앱을 한 번 더 띄운 서버나 DB 도구·동기화 스크립트라면 그것을 닫고 "
            "새로고침하세요.\n"
            "- 같은 서버를 브라우저 창·탭 여러 개로 여는 것은 원인이 아닙니다."
        )
    text = str(exc)
    if any(marker in text for marker in _WRITE_FAILURE_MARKERS):
        return (
            "데이터베이스에 쓰지 못했습니다 — 저장되지 않았습니다. 디스크 공간과 쓰기 권한을 "
            "확인하세요.\n\n"
            f"{files}\n"
            f"{_original_line(exc)}"
        )
    if not (
        isinstance(exc, duckdb.IOException)
        and any(marker in text for marker in _OPEN_FAILURE_MARKERS)
    ):
        return (
            "데이터베이스 작업이 실패했습니다.\n\n"
            f"{files}\n"
            "- 같은 실패가 이어지면 아래 원문을 관리자에게 알려 주세요.\n"
            f"{_original_line(exc)}"
        )
    return (
        "데이터베이스를 열지 못했습니다.\n\n"
        f"{files}\n"
        "- 같은 파일을 연 다른 프로그램(이 앱을 한 번 더 띄운 서버, DB 도구, 동기화 "
        "스크립트)이 있으면 닫고 새로고침하세요. DuckDB 는 한 번에 한 프로세스만 파일을 "
        "엽니다.\n"
        "- 그래도 같은 오류가 나면 파일 권한과 경로(네트워크 드라이브 여부)를 확인하세요."
    )


def schema_ahead_message(notice: SchemaAheadOfCode) -> str:
    """DB 가 이 코드보다 새 버전일 때 화면에 띄울 문구. 어느 DB 인지와 두 버전을 적는다."""
    return (
        f"{notice.database_name} 가 이 코드보다 새 버전입니다"
        f"(DB {notice.database_version} · 코드 {notice.code_version}). "
        "예전 배포로 되돌린 상태일 수 있습니다. 화면은 그대로 쓸 수 있지만, 새 버전이 더한 "
        "표·열은 이 코드가 읽지도 쓰지도 않습니다. 되돌린 것이 아니라면 최신 배포를 다시 "
        "적용하세요."
    )


def render_schema_ahead_warning(notice: SchemaAheadOfCode | None) -> None:
    """DB 가 코드보다 새 것이면 경고 한 줄을 그린다. 아니면 아무것도 그리지 않는다.

    막지 않는다(2026-10-05 사용자 결정) — 막으면 예전 배포로 되돌릴 때 DB 를 먼저 복원해야
    한다. `notice` 는 캐시된 저장소의 `schema_ahead` 속성이라 rerun 마다 DB 를 열지 않는다.
    """
    if notice is not None:
        st.warning(schema_ahead_message(notice), icon=":material/history:")


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

    **위젯 앞에서 매 회차 부른다.** 세션에 새로 적은 값만 브라우저에 간다(`set_value`). 선택지의
    보이는 글자가 회차마다 바뀔 수 있는 상자(공정 표시명의 「표시명 (원본)」 가르기)는 적지 않으면
    브라우저가 옛 글자를 들고 있다가 다음 조작에 되보내 다른 값으로 바뀐다(2026-10-10 재검증).
    """
    allowed = set(options)
    saved = st.session_state.get(key)
    if not isinstance(saved, list):
        saved = list(default)
    pruned = [str(value) for value in saved if str(value) in allowed]
    st.session_state[key] = pruned
    return pruned


@overload
def prune_choice(key: str, options: Sequence[str], *, default: str) -> str: ...


@overload
def prune_choice(key: str, options: Sequence[str], *, default: None) -> str | None: ...


def prune_choice(key: str, options: Sequence[str], *, default: str | None) -> str | None:
    """`prune_list_selection` 의 단일 선택(`st.selectbox`) 짝.

    저장된 값이 지금 옵션에 있으면 그대로, 없거나 아직 없으면 `default` 를 세션에 **되쓴다** —
    지우지(`pop`) 않는다(AGENTS 9장 「pop 하지 말고 새 값을 적는다」). 위젯 앞에서 매 회차 부른다.
    적은 값만 브라우저에 가므로, 선택지 글자가 바뀌어도 브라우저가 새 글자를 받는다.
    `default=None` 은 고른 것이 없는 상자(`index=None`)의 빈 선택이다.
    """
    saved = st.session_state.get(key)
    value = str(saved) if saved is not None and str(saved) in set(options) else default
    st.session_state[key] = value
    return value


def load_page_context() -> PageContext:
    """활성 리비전·표시순서·활성 시나리오와 선택 조회기간을 한 번에 준비한다."""
    reference_version = reference_cache.get_effective_reference_version()
    reference_tables = reference_cache.get_effective_reference_tables()
    display_order = simulation_cache.get_prepared_display_order(
        reference_tables["RQ_DISPLAY_ORDER"]
    )
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


# 조회기간에 소요대수가 없을 때의 첫 문장 — 계산 화면들이 `resolve_effective_months` 에 넘기는
# 글자와 같다.
NO_DEMAND_MESSAGE = "선택 범위에 소요대수 산출 기준이 없습니다."


def no_demand_message(context: PageContext) -> str:
    """조회기간에 소요대수가 없을 때의 안내 — 다른 계산 화면(`resolve_effective_months`)의 문구.

    `resolve_effective_months` 를 거치지 않고 소요대수가 빈 것으로 그 사실을 아는 화면(필요 단축
    일정, Static 대비 일정의 확보율 교차검증)이 쓴다. 데이터 범위는 그 화면들과 같은 원천(활성
    시나리오 `RQ_REQB`)에서 잰다. 그 범위가 조회기간과 겹치거나 원천을 못 읽으면 범위를 붙이지
    않는다 — 옮겨 갈 곳을 틀리게 알리지 않도록.
    """
    try:
        first, last = available_month_range(context.active_scenario["tables"]["RQ_REQB"], "RQ_REQB")
    except (KeyError, ValueError):
        return NO_DEMAND_MESSAGE
    if first <= context.selected_end_month and context.selected_start_month <= last:
        return NO_DEMAND_MESSAGE
    return f"{NO_DEMAND_MESSAGE} (데이터 범위 {month_label(first)}–{month_label(last)})"


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
    return stop_calculation_on_error(
        simulation_cache.get_scenario_capacity_and_demand,
        cache_key,
        _scenario_tables=scenario_tables,
        _reference_tables=reference_tables,
    )


def stop_calculation_on_error(
    function: Callable[_P, _T], /, *args: _P.args, **kwargs: _P.kwargs
) -> _T:
    """시나리오 계산을 거치는 캐시 호출. 계산이 멈추면(ValueError) 사이드바의 「✓ 적용」을 거둔다.

    `scenario_capacity_and_demand` 와 같은 처리를 키 전용 파생 캐시(`check_scenario_capacity`·
    `get_scenario_result_summary` 등)에 건다 — 그 캐시들은 적중하면 큰 프레임을 풀지 않고,
    빗나가면 안에서 `get_scenario_capacity_and_demand` 를 불러 같은 오류를 던진다(실패는
    캐시되지 않는다). 시나리오 수준의 오류만 나는 호출에만 쓴다 — 입력 표 하나의 검증 오류까지
    「계산 멈춤」으로 바꾸지 않도록. 예외는 그대로 다시 던진다.
    """
    try:
        return function(*args, **kwargs)
    except ValueError:
        show_calculation_stopped()
        raise


@dataclass(frozen=True)
class ProcessPageInputs:
    """공정 하나를 보는 화면(공정 Capa 상세·제약 시뮬레이션)의 공통 진입 결과.

    두 화면이 **글자 하나까지 같은 차례**로 낸 값이라 계획 캐시 키(시나리오 키·달)가 같다 — 상세에서
    링크로 넘어오면 확보율·계획이 적중한다.
    """

    thresholds: SecurementThresholds
    context: PageContext
    effective_start: int
    effective_end: int
    capacity_cache_key: simulation_cache.ScenarioCacheKey
    securement_rate: pd.DataFrame
    months: tuple[int, ...]
    """확보율 프레임의 달 가운데 유효 기간 안(오름차순)."""

    order_key: str
    process_options: list[str]
    """공정 선택지 — 공용 표시순서(산출 결과 · 확보율)."""


def process_page_inputs(database_path: str) -> ProcessPageInputs:
    """판정 기준 → 공통 진입 → 유효 기간(`RQ_REQB`) → 시나리오 키 → 확보율 → 달·공정 선택지.

    `database_path` 는 시뮬레이션 DB 경로 글자다(페이지가 `settings.DUCKDB_PATH` 를 그 회차에 읽어
    넘긴다 — 시험이 설정을 바꾼다). 확보율 계산이 멈추면 「계산 멈춤」 과 함께 그 오류를 먼저
    낸다(Static Capa 와 같은 길). 예외는 모두 `BOOTSTRAP_ERRORS` 이고 카드 캡션·`st.error`·`st.stop`
    은 부르는 페이지가 쥔다. 계산 함수는 **부를 때** 모듈에서 찾는다(페이지 시험이 그 속성을 바꿔
    계산을 흉내 낸다).
    """
    # 판정 기준은 HOME → Preference 의 공용 프로필이다(기본값 + 월별 예외).
    thresholds = load_global_securement_threshold(database_path).thresholds
    context = load_page_context()
    active = context.active_scenario
    reference_tables = context.reference_tables
    # 유효 기간은 산출 결과와 같이 RQ_REQB 원천에서 잡는다 — 같은 시나리오 키를 나눠 쓴다.
    effective_start, effective_end = resolve_effective_months(
        context,
        active["tables"]["RQ_REQB"],
        "RQ_REQB",
        empty_message=NO_DEMAND_MESSAGE,
    )
    capacity_cache_key = simulation_cache.scenario_cache_key(
        context.reference_version, active, effective_start, effective_end
    )
    try:
        securement_rate = simulation_cache.get_scenario_securement_rate(
            capacity_cache_key,
            _scenario_tables=active["tables"],
            _reference_tables=reference_tables,
            _available_equipment=scenario_state.scenario_month_table(
                active, "RQ_EQP_AVBL", effective_start, effective_end
            ),
        )
    except BOOTSTRAP_ERRORS:
        # 대당 Capa·소요대수 계산이 멈춘 것이면 「계산 멈춤」과 함께 그 오류를 먼저 낸다. 계산은
        # 섰는데 가용대수·확보율에서 난 오류면 그 오류를 그대로 낸다.
        stop_calculation_on_error(
            simulation_cache.check_scenario_capacity,
            capacity_cache_key,
            _scenario_tables=active["tables"],
            _reference_tables=reference_tables,
        )
        raise
    months = tuple(
        sorted(
            {
                int(month)
                for month in securement_rate["생산계획년월"]
                if effective_start <= int(month) <= effective_end
            }
        )
    )
    order_key = simulation_cache.display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])
    # 공정 차례는 산출 결과 확보율 탭·HOME 공정 필터와 같은 공용 표시순서 범위다.
    process_column = securement_rate["공정"].astype("string").str.strip()
    process_options = simulation_cache.get_display_ordered_values(
        pd.DataFrame({"공정": sorted(process_column.dropna().unique().tolist())}),
        order_key,
        PAGE_CALCULATION,
        TAB_SECUREMENT,
        _display_order=context.display_order,
    )
    return ProcessPageInputs(
        thresholds=thresholds,
        context=context,
        effective_start=effective_start,
        effective_end=effective_end,
        capacity_cache_key=capacity_cache_key,
        securement_rate=securement_rate,
        months=months,
        order_key=order_key,
        process_options=list(process_options),
    )
