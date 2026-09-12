# Purpose: BigDataQuery 시뮬레이션 코드 조회와 시나리오 등록을 두 단계로 제공한다.

"""기간으로 시뮬레이션 코드를 찾고, 고른 코드로 시나리오를 등록하는 화면.

1단계는 기간 조회와 스크롤 목록, 2단계는 자동 입력된 등록 폼이다. 저장 경로는 예전과
같다 — `fetch_core_data_dataset → 충돌보고 → 프리셋 → create_scenario → 활성화 → flash`.

이 파일에서 순서가 계약인 곳이 하나 있다. 목록(선택 이벤트)이 등록 폼보다 **위**에
그려져야 프리필의 `st.session_state[...] = ...` 대입이 위젯 생성 전이 된다. 이미 만든
위젯 key 에 같은 런에서 대입하면 `StreamlitAPIException` 이라, 순서를 바꾸면 행을 고를
때마다 페이지 전체가 죽는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final, cast

import pandas as pd
import streamlit as st

from capa_simulation.components.process_labels import PROCESS_COLUMN, get_process_labels
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import tokens
from capa_simulation.io.bigdataquery_catalog import (
    fetch_simulation_catalog,
    is_bigdataquery_catalog_configured,
)
from capa_simulation.io.company_bigdataquery_adapter import (
    BigDataQueryCoreDataProvider,
    QueryWindow,
    is_bigdataquery_adapter_configured,
    is_bigdataquery_package_available,
    resolve_detail_window,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import load_global_display_order
from capa_simulation.persistence.models import ScenarioCreate
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import activate_persisted_snapshot
from capa_simulation.scenario_preset_state import capture_full_data_scenario_preset
from capa_simulation.services.bigdataquery_catalog_view import (
    SCOPE_ALL,
    SCOPE_OPTIONS,
    UNSAVABLE_REASON,
    CatalogRow,
    build_display_frame,
    catalog_row_at,
    filter_catalog,
    normalize_catalog,
    registration_prefill,
    row_position,
    view_token,
)
from capa_simulation.services.core_data_pipeline import (
    fetch_core_data_dataset,
    reference_conflicts_to_csv,
    summarize_reference_conflicts,
)

PIPELINE_VERSION = "bigdataquery-core-data-v4"
CONFLICT_REPORT_STATE_KEY = "bigdataquery_reference_conflict_report"
REGISTRATION_FLASH_KEY = "bigdataquery_registration_flash"

CATALOG_RESULT_KEY = "bigdataquery_catalog_result"
CATALOG_PICK_KEY = "bigdataquery_catalog_pick"
CATALOG_APPLIED_KEY = "bigdataquery_catalog_applied_signature"
CATALOG_FORM_WINDOW_KEY = "bigdataquery_catalog_form_window"
CATALOG_LIST_NONCE_KEY = "bigdataquery_catalog_list_nonce"
CATALOG_LAST_LIST_KEY = "bigdataquery_catalog_last_list_key"
CATALOG_RESET_REQUEST_KEY = "bigdataquery_catalog_reset_request"
CATALOG_START_DATE_KEY = "bigdataquery_catalog_start_date"
CATALOG_END_DATE_KEY = "bigdataquery_catalog_end_date"
CATALOG_KEYWORD_KEY = "bigdataquery_catalog_keyword"
CATALOG_SCOPE_KEY = "bigdataquery_catalog_scope"
CATALOG_LIST_KEY_PREFIX = "bigdataquery_catalog_rows_"

FORM_CODE_KEY = "bigdataquery_form_simulation_code"
FORM_SOURCE_NAME_KEY = "bigdataquery_form_source_name"
FORM_SCENARIO_NAME_KEY = "bigdataquery_form_scenario_name"
FORM_REVISION_NAME_KEY = "bigdataquery_form_revision_name"
FORM_REGISTERED_AT_KEY = "bigdataquery_form_registered_at"
FORM_NOTE_KEY = "bigdataquery_form_note"
FORM_DEFAULTS: Final[dict[str, str]] = {
    FORM_CODE_KEY: "",
    FORM_SOURCE_NAME_KEY: "",
    FORM_SCENARIO_NAME_KEY: "",
    FORM_REVISION_NAME_KEY: "초기 리비전",
    FORM_REGISTERED_AT_KEY: "",
    FORM_NOTE_KEY: "",
}

# 기본 조회 기간. 종료일은 오늘이고 시작일은 그 30일 전이다.
DEFAULT_CATALOG_DAYS: Final = 30
# 이보다 많으면 표 조작이 느려진다는 안내만 띄운다(자르지 않는다).
CATALOG_BUSY_ROWS: Final = 3000
CATALOG_LIST_HEIGHT_PX: Final = tokens.CATALOG_LIST_ROW_HEIGHT_PX * (
    tokens.CATALOG_LIST_VISIBLE_ROWS + 1
)


@dataclass(frozen=True)
class CatalogResult:
    """한 번의 목록 조회 결과. 세션에 담아 rerun 을 건너 산다."""

    frame: pd.DataFrame
    window: QueryWindow
    queried_at: datetime
    token: str


@dataclass(frozen=True)
class CatalogPick:
    """목록에서 고른 행과, 그 행을 찾아낸 조회 기간."""

    row: CatalogRow
    window: QueryWindow


def render_bigdataquery_registration(
    repository: DuckDBScenarioRepository,
    database_path: str,
) -> None:
    # 리셋 소비는 반드시 첫 줄이다. 위젯을 만든 뒤에는 그 key 를 지울 수 없다.
    _consume_reset_request()
    st.subheader("BigDataQuery 시나리오 등록")
    st.caption(
        "① 기간으로 시뮬레이션 코드를 찾고 ② 고른 코드의 등록 정보를 확인·수정해 저장합니다. "
        "저장은 CSV 파일 없이 typed raw 와 RQ 16개를 한 트랜잭션으로 넣고, 내려받은 전체 "
        "생산계획년월과 전체 B/N 공정을 활성화합니다."
    )
    flash = st.session_state.pop(REGISTRATION_FLASH_KEY, None)
    if isinstance(flash, str) and flash:
        st.success(flash)

    catalog_ready = is_bigdataquery_catalog_configured()
    detail_ready = is_bigdataquery_adapter_configured()
    _render_configuration_banner(
        catalog_ready=catalog_ready,
        detail_ready=detail_ready,
        package_ready=is_bigdataquery_package_available(),
    )
    registered_codes, existing_names = _registered_scenarios(repository)
    _render_catalog_form(configured=catalog_ready)
    _render_catalog_list(registered_codes=registered_codes)
    _render_registration_form(
        repository,
        database_path,
        configured=detail_ready,
        existing_names=existing_names,
    )
    # 충돌 보고서는 한 런에 딱 한 번만 그린다. 저장 실패 분기에서 한 번 더 부르면
    # 같은 다운로드 key 가 두 번 나와 `StreamlitDuplicateElementKey` 로 탭이 죽는다.
    _render_reference_conflict_report()


def catalog_list_key(token: str, nonce: int, keyword: str, scope: str) -> str:
    """목록 위젯 key. 보이는 행 집합이 바뀌면 key 도 바뀐다.

    key 를 고정하면 Streamlit 이 dataframe 정체성을 key 로만 계산해서, 검색으로 행 수가
    달라져도 옛 위치 인덱스가 그대로 돌아와 조용히 다른 행이 선택된다. key 를 갈면 낡은
    선택이 존재할 수 없고, 직전 선택은 행 서명으로 위치를 다시 찾아 복원한다.
    """
    return CATALOG_LIST_KEY_PREFIX + view_token(token, str(nonce), keyword, scope)


def first_selected_row(event: object) -> int | None:
    """선택 이벤트에서 첫 행 위치만 방어적으로 읽는다."""
    if not isinstance(event, dict):
        return None
    selection = event.get("selection")
    if not isinstance(selection, dict):
        return None
    rows = selection.get("rows")
    if isinstance(rows, str) or not isinstance(rows, (list, tuple)):
        return None
    if not rows:
        return None
    first = rows[0]
    if isinstance(first, bool) or not isinstance(first, int):
        return None
    return int(first)


def _render_configuration_banner(
    *,
    catalog_ready: bool,
    detail_ready: bool,
    package_ready: bool,
) -> None:
    missing: list[str] = []
    if not catalog_ready:
        missing.append("목록 조회 SQL(bigdataquery_catalog.py의 CATALOG_QUERY_TEMPLATE)")
    if not detail_ready:
        missing.append("상세 조회 SQL(company_bigdataquery_adapter.py의 QUERY_TEMPLATE)")
    if missing:
        st.warning("사내 " + " 과 ".join(missing) + " 이(가) 아직 설정되지 않았습니다.")
        return
    if not package_ready:
        st.warning(
            "SQL 설정은 확인했습니다. 다만 현재 PC 에는 bigdataquery 패키지가 없어 "
            "실제 조회는 사내 PC 에서만 성공합니다."
        )
        return
    st.success("사내 BigDataQuery 목록·상세 조회 SQL 과 패키지를 확인했습니다.")


def _registered_scenarios(
    repository: DuckDBScenarioRepository,
) -> tuple[frozenset[str], frozenset[str]]:
    """(이미 등록된 원천 코드, 이미 쓰인 시나리오명).

    매 렌더 다시 계산한다. 세션 프레임에 구워 두면 저장 직후 목록의 `등록여부` 가 낡는다.
    """
    try:
        scenarios = repository.list_scenarios()
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return frozenset(), frozenset()
    return (
        frozenset(str(scenario.source_simulation_code) for scenario in scenarios),
        frozenset(str(scenario.scenario_name) for scenario in scenarios),
    )


def _render_catalog_form(*, configured: bool) -> None:
    today = datetime.now().date()
    st.session_state.setdefault(
        CATALOG_START_DATE_KEY, today - timedelta(days=DEFAULT_CATALOG_DAYS)
    )
    st.session_state.setdefault(CATALOG_END_DATE_KEY, today)
    with st.form("bigdataquery_catalog_form"):
        with st.container(horizontal=True, gap="small"):
            st.date_input("시작일", key=CATALOG_START_DATE_KEY, width=180)
            st.date_input("종료일", key=CATALOG_END_DATE_KEY, width=180)
        submitted = st.form_submit_button(
            "시뮬레이션 코드 조회",
            icon=":material/search:",
            type="primary",
            disabled=not configured,
        )
    if not submitted:
        return
    window = _submitted_window()
    if window is not None:
        _run_catalog_query(window)


def _submitted_window() -> QueryWindow | None:
    """제출된 두 날짜를 조회 기간으로 만든다. 조용한 기본값 대체를 하지 않는다."""
    start = st.session_state.get(CATALOG_START_DATE_KEY)
    end = st.session_state.get(CATALOG_END_DATE_KEY)
    if not isinstance(start, date) or not isinstance(end, date):
        st.error("시작일과 종료일을 모두 지정하세요.")
        return None
    if start > end:
        st.error("시작일은 종료일보다 늦을 수 없습니다.")
        return None
    return QueryWindow(start_date=start, end_date=end)


def _run_catalog_query(window: QueryWindow) -> None:
    try:
        with st.spinner(
            f"사내 DB에서 {window.label()} 구간의 시뮬레이션 코드를 조회하는 중입니다..."
        ):
            frame = fetch_simulation_catalog(window)
            catalog = normalize_catalog(frame)
            queried_at = datetime.now()
            # 세션 대입을 spinner 블록 안에서 끝낸다. 블록을 빠져나가는 첫 `st` 호출이
            # 탭 전환 rerun 으로 터지면 조회 결과가 통째로 버려진다.
            st.session_state[CATALOG_RESULT_KEY] = CatalogResult(
                frame=catalog,
                window=window,
                queried_at=queried_at,
                token=view_token(window.label(), queried_at.isoformat(timespec="microseconds")),
            )
            # 결과셋이 바뀌었으니 선택만 버린다. 폼에 적힌 값은 건드리지 않는다.
            _clear_pick()
    except BOOTSTRAP_ERRORS as exc:
        # 실패해도 직전 목록은 지우지 않는다.
        st.error(bootstrap_error_message(exc))


def _render_catalog_list(*, registered_codes: frozenset[str]) -> None:
    result = _stored_result()
    if result is None:
        st.info("기간을 지정하고 조회하면 시뮬레이션 코드 목록이 여기 표시됩니다.")
        return
    st.caption(
        f"{result.window.label()} · {result.queried_at:%H:%M:%S} 조회 · "
        f"코드·PLAN 기준 {len(result.frame):,}건"
    )
    if result.frame.empty:
        st.warning("이 기간에는 시뮬레이션 코드가 없습니다. 기간을 넓혀 다시 조회하세요.")
        return

    with st.container(horizontal=True, gap="small"):
        keyword = st.text_input(
            "검색",
            key=CATALOG_KEYWORD_KEY,
            # 목록을 좁히는 필터 전용이다. 검색 칸으로 선언하면 값이 있을 때 지우기 버튼이
            # 붙어, 전체 목록으로 되돌리는 조작이 한 번에 끝난다.
            type="search",
            width=360,
            placeholder="시뮬레이션명·코드·PLAN 부분 일치(공백은 AND)",
        )
        scope = st.segmented_control(
            "표시 범위",
            SCOPE_OPTIONS,
            default=SCOPE_ALL,
            key=CATALOG_SCOPE_KEY,
            width="content",
        )
    keyword_text = keyword or ""
    scope_text = scope or SCOPE_ALL
    visible = filter_catalog(
        result.frame,
        keyword=keyword_text,
        scope=scope_text,
        registered_codes=registered_codes,
    )
    if visible.empty:
        st.warning("검색 조건에 맞는 코드가 없습니다.")
        return
    if len(visible) > CATALOG_BUSY_ROWS:
        st.caption("행이 많아 표 조작이 느릴 수 있습니다. 검색어로 좁히세요.")

    pick = _stored_pick()
    position = row_position(visible, pick.row.signature) if pick is not None else None
    selection_default: dict[str, Any] | None = None
    if position is not None:
        selection_default = {"selection": {"rows": [position], "columns": []}}
    elif pick is not None:
        st.caption("선택한 행이 현재 검색 결과에 없습니다. 아래 등록 폼의 값은 그대로 유지됩니다.")

    list_key = catalog_list_key(
        result.token,
        int(st.session_state.get(CATALOG_LIST_NONCE_KEY, 0)),
        keyword_text,
        scope_text,
    )
    event = st.dataframe(
        build_display_frame(visible, registered_codes=registered_codes),
        key=list_key,
        on_select="rerun",
        selection_mode="single-row",
        selection_default=cast(Any, selection_default),
        hide_index=True,
        height=CATALOG_LIST_HEIGHT_PX,
        row_height=tokens.CATALOG_LIST_ROW_HEIGHT_PX,
        width="stretch",
    )

    selected = first_selected_row(event)
    last_key = st.session_state.get(CATALOG_LAST_LIST_KEY)
    if selected is not None:
        row = catalog_row_at(visible, selected)
        if row is not None:
            _apply_pick(CatalogPick(row=row, window=result.window))
    elif last_key == list_key:
        # 위젯 key 가 그대로인데 선택이 비었다 = 같은 행을 다시 눌러 해제했다.
        # key 가 바뀐 런의 빈 선택은 검색 변경이므로 선택을 유지한다.
        _clear_pick()
    st.session_state[CATALOG_LAST_LIST_KEY] = list_key

    if st.button(
        "선택 해제 · 폼 초기화",
        key="bigdataquery_catalog_reset",
        icon=":material/undo:",
    ):
        _request_reset()
        st.rerun()


def _apply_pick(pick: CatalogPick) -> None:
    st.session_state[CATALOG_PICK_KEY] = pick
    if st.session_state.get(CATALOG_APPLIED_KEY) == pick.row.signature:
        # 같은 행이 계속 선택돼 있을 뿐이다. 사용자가 고친 값을 덮지 않는다.
        return
    prefill = registration_prefill(
        pick.row,
        catalog_window_label=pick.window.label(),
        detail_window_label=resolve_detail_window(pick.window).label(),
    )
    st.session_state[CATALOG_APPLIED_KEY] = pick.row.signature
    st.session_state[CATALOG_FORM_WINDOW_KEY] = pick.window
    st.session_state[FORM_CODE_KEY] = prefill.simulation_code
    st.session_state[FORM_SOURCE_NAME_KEY] = prefill.source_name
    st.session_state[FORM_SCENARIO_NAME_KEY] = prefill.scenario_name
    st.session_state[FORM_REVISION_NAME_KEY] = prefill.revision_name
    st.session_state[FORM_REGISTERED_AT_KEY] = prefill.registered_at
    st.session_state[FORM_NOTE_KEY] = prefill.note


def _clear_pick() -> None:
    """선택만 버린다. 폼 값과 상세 조회 창은 남긴다."""
    st.session_state.pop(CATALOG_PICK_KEY, None)
    st.session_state.pop(CATALOG_APPLIED_KEY, None)


def _request_reset() -> None:
    """다음 런에서 선택·폼을 비우도록 예약한다.

    같은 런에서 지울 수 없다. 리셋 버튼은 목록보다 아래라 이미 그 런의 선택이 보고된 뒤이고,
    이미 만든 폼 위젯 key 를 그 런에서 삭제하면 다음 런이 깨진다. nonce 를 올려 목록 위젯
    정체성을 갈아 두고 다음 런 첫 줄에서 지운다.
    """
    st.session_state[CATALOG_RESET_REQUEST_KEY] = True
    st.session_state[CATALOG_LIST_NONCE_KEY] = (
        int(st.session_state.get(CATALOG_LIST_NONCE_KEY, 0)) + 1
    )


def _consume_reset_request() -> None:
    if not st.session_state.pop(CATALOG_RESET_REQUEST_KEY, False):
        return
    for key in (
        CATALOG_PICK_KEY,
        CATALOG_APPLIED_KEY,
        CATALOG_FORM_WINDOW_KEY,
        *FORM_DEFAULTS,
    ):
        st.session_state.pop(key, None)


def _render_registration_form(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    configured: bool,
    existing_names: frozenset[str],
) -> None:
    for key, value in FORM_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    pick = _stored_pick()
    unsavable = pick is not None and not pick.row.savable
    if unsavable:
        st.error(UNSAVABLE_REASON)
    detail_window = resolve_detail_window(_form_detail_window())
    st.caption(
        f"상세 조회 기간: {detail_window.label()} — 목록 기간으로 좁히지 않고 "
        "기본 창과 합쳐 사용합니다."
    )
    with st.form("bigdataquery_registration_form"):
        st.text_input("조회할 시뮬레이션 코드", key=FORM_CODE_KEY)
        st.text_input("원천 시뮬레이션명", key=FORM_SOURCE_NAME_KEY)
        st.text_input("저장할 시나리오명", key=FORM_SCENARIO_NAME_KEY)
        st.text_input("초기 리비전명", key=FORM_REVISION_NAME_KEY)
        st.text_input(
            "원천 DB 등록시점 (선택)",
            key=FORM_REGISTERED_AT_KEY,
            placeholder="2026-08-29 14:30:00",
            # 빈 값은 검증을 건너뛰므로 (선택) 의미가 그대로다. 앞뒤 공백을 허용하는 것은
            # 원천 DB 값을 붙여넣는 칸이고 `_optional_datetime` 이 `strip()` 하기 때문이다.
            # 브라우저에서 우회할 수 있으므로 서버의 파싱은 최종 방어선으로 남긴다.
            validate=(
                r"^\s*\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?\s*$",
                "등록시점은 YYYY-MM-DD HH:MM:SS 형식으로 입력하세요.",
            ),
        )
        st.text_area("등록 메모", key=FORM_NOTE_KEY, height=90)
        submitted = st.form_submit_button(
            "DB 조회 후 시나리오 저장",
            icon=":material/cloud_download:",
            type="primary",
            width="stretch",
            disabled=not configured or unsavable,
        )
    if submitted:
        _save_scenario(repository, database_path, existing_names=existing_names)


def _save_scenario(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    existing_names: frozenset[str],
) -> None:
    st.session_state.pop(CONFLICT_REPORT_STATE_KEY, None)
    scenario_name = str(st.session_state.get(FORM_SCENARIO_NAME_KEY, "")).strip()
    if scenario_name in existing_names:
        # 같은 이름이 둘이면 사이드바에서 구분되지 않는다. 사내 조회 한 번을 아끼려고
        # 조회 전에 막는다.
        st.error("같은 이름의 시나리오가 이미 있습니다. 이름을 바꿔 저장하세요.")
        return
    simulation_code = str(st.session_state.get(FORM_CODE_KEY, ""))
    source_name = str(st.session_state.get(FORM_SOURCE_NAME_KEY, ""))
    revision_name = str(st.session_state.get(FORM_REVISION_NAME_KEY, "")) or "초기 리비전"
    note = str(st.session_state.get(FORM_NOTE_KEY, ""))
    try:
        registered_at = _optional_datetime(str(st.session_state.get(FORM_REGISTERED_AT_KEY, "")))
        display_order = load_global_display_order(database_path).rules
        provider = BigDataQueryCoreDataProvider(
            simulation_name=source_name,
            source_registered_at=registered_at,
            window=resolve_detail_window(_form_detail_window()),
        )
        with st.spinner("사내 DB에서 Core Data를 조회하고 검증하는 중입니다..."):
            prepared = fetch_core_data_dataset(provider, simulation_code, display_order)
            _store_reference_conflict_report(
                prepared.reference_conflicts,
                prepared.batch.simulation_code,
            )
            preset = capture_full_data_scenario_preset(prepared.reference_tables)
            snapshot = repository.create_scenario(
                ScenarioCreate(
                    scenario_name=scenario_name,
                    source_simulation_code=prepared.batch.simulation_code,
                    source_simulation_name=prepared.batch.simulation_name,
                    source_type=prepared.batch.source_type,
                    pipeline_version=PIPELINE_VERSION,
                    source_registered_at=prepared.batch.source_registered_at,
                ),
                prepared.reference_tables,
                preset,
                source_data=prepared.source_data,
                revision_name=revision_name,
                note=note.strip() or None,
            )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    activate_persisted_snapshot(snapshot)
    # 목록은 남긴다. 선택과 폼만 비워 다음 코드를 이어서 등록할 수 있게 한다.
    _request_reset()
    st.session_state[REGISTRATION_FLASH_KEY] = (
        f"{snapshot.scenario.scenario_name}을 저장하고 r{snapshot.revision.revision_no}을 "
        "활성화했습니다."
    )
    st.rerun()


def _stored_result() -> CatalogResult | None:
    stored = st.session_state.get(CATALOG_RESULT_KEY)
    return stored if isinstance(stored, CatalogResult) else None


def _stored_pick() -> CatalogPick | None:
    stored = st.session_state.get(CATALOG_PICK_KEY)
    return stored if isinstance(stored, CatalogPick) else None


def _form_detail_window() -> QueryWindow | None:
    """폼에 들어 있는 코드를 찾아낸 목록 조회 기간.

    현재 선택이 아니라 폼 내용을 따라간다 — 재조회로 선택이 풀려도 폼에 남은 코드는
    그 코드를 찾아낸 기간으로 조회되어야 한다.
    """
    stored = st.session_state.get(CATALOG_FORM_WINDOW_KEY)
    return stored if isinstance(stored, QueryWindow) else None


def _store_reference_conflict_report(conflicts: pd.DataFrame, simulation_code: str) -> None:
    if conflicts.empty:
        return
    safe_code = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", simulation_code).strip("._")
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    st.session_state[CONFLICT_REPORT_STATE_KEY] = {
        "report": conflicts.copy(),
        "file_name": f"RQ_업무키_충돌_{safe_code or 'query'}_{timestamp}.csv",
    }


def _render_reference_conflict_report() -> None:
    payload = st.session_state.get(CONFLICT_REPORT_STATE_KEY)
    if not isinstance(payload, dict):
        return
    report = payload.get("report")
    file_name = payload.get("file_name")
    if not isinstance(report, pd.DataFrame) or report.empty or not isinstance(file_name, str):
        return
    summary = summarize_reference_conflicts(report)
    st.warning(
        f"{len(report):,}개 업무 키 그룹에서 값 충돌을 확인했습니다. "
        "등록은 중단하지 않고 각 그룹의 원천 첫 행을 임시 적용했습니다."
    )
    st.dataframe(summary, hide_index=True, width="stretch")
    render_csv_download(
        data=reference_conflicts_to_csv(report),
        file_name=file_name,
        key="reference_conflicts_download",
        label="RQ 업무 키 충돌 CSV 다운로드",
    )
    with st.expander("충돌 상세 미리보기"):
        # `report` 는 세션에 담아 둔 보고서이고 바로 위 CSV 가 같은 객체를 내보낸다.
        # 화면 복사본에만 표시명을 입혀야 파일이 원본 공정명으로 남는다.
        displayed = report.copy()
        if PROCESS_COLUMN in displayed.columns:
            displayed[PROCESS_COLUMN] = get_process_labels().series(displayed[PROCESS_COLUMN])
        st.dataframe(displayed, hide_index=True, width="stretch")


def _optional_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("원천 DB 등록시점은 YYYY-MM-DD HH:MM:SS 형식이어야 합니다.") from exc
