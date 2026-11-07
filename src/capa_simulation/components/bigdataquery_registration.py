# Purpose: BigDataQuery 시뮬레이션 코드 조회와 시나리오 등록을 두 단계로 제공한다.

"""기간으로 시뮬레이션 코드를 찾고, 고른 코드로 시나리오를 등록하는 화면.

1단계는 기간 조회와 스크롤 목록, 2단계는 자동 입력된 등록 폼이다. 저장 경로는
`fetch_core_data_dataset → 프리셋 → save_bigdataquery_scenario → 활성화 → flash(충돌 보고 포함)` 다.
저장 자체(원천 메타데이터·파이프라인 버전·메모의 상세 조회기간)는 세션을 모르는
`scenario_registration` 이 맡는다 — 공식버전 자동 갱신이 같은 길로 저장한다.

이 파일에서 순서가 계약인 곳이 하나 있다. 목록(선택 이벤트)이 등록 폼보다 **위**에
그려져야 프리필의 `st.session_state[...] = ...` 대입이 위젯 생성 전이 된다. 이미 만든
위젯 key 에 같은 런에서 대입하면 `StreamlitAPIException` 이라, 순서를 바꾸면 행을 고를
때마다 페이지 전체가 죽는다.

폼 글자 칸의 key 는 세대를 단다(`form_field_key`). 폼 안 칸에 친 글자는 제출 전까지 브라우저만
들고 있어, 같은 칸에 서버가 값을 써 넣으면 화면만 바뀌고 친 글자가 그대로 제출된다. 그래서 서버가
칸을 채우거나 비울 때마다(행 고름 · 폼 초기화) 세대를 올려 새 위젯으로 세운다.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Final, cast

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation import alerts
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.date_panel import date_range_field, optional_date_range_field
from capa_simulation.components.flash import (
    BESIDE_KINDS,
    FlashNote,
    pending_flash,
    queue_flash,
    render_flash,
)
from capa_simulation.components.literal_markdown import markdown_safe_tildes
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.scenario_list_state import follow_created_scenario
from capa_simulation.components.scenario_management_tabs import QUERY_TAB_NAME
from capa_simulation.components.state_alerts import alarm_table_place, alert_table
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.components.widget_generation import bump, widget_key
from capa_simulation.design import tokens
from capa_simulation.io.bigdataquery_catalog import (
    fetch_simulation_catalog,
    is_bigdataquery_catalog_configured,
)
from capa_simulation.io.company_bigdataquery_adapter import (
    DETAIL_WINDOW_DAYS_AFTER,
    DETAIL_WINDOW_DAYS_BEFORE,
    BigDataQueryCoreDataProvider,
    QueryWindow,
    is_bigdataquery_adapter_configured,
    is_bigdataquery_package_available,
    registration_detail_window,
)
from capa_simulation.io.container_start_report import STEP_INSTALL, start_check_hint
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import load_global_display_order
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import activate_persisted_snapshot
from capa_simulation.scenario_preset_state import capture_full_data_scenario_preset
from capa_simulation.scenario_registration import registration_note, save_bigdataquery_scenario
from capa_simulation.services.bigdataquery_catalog_view import (
    SCOPE_ALL,
    SCOPE_OPTIONS,
    UNSAVABLE_REASON,
    CatalogRow,
    build_display_frame,
    catalog_row_at,
    code_registration_span,
    filter_catalog,
    first_registration_dates,
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
from capa_simulation.services.korean_particle import with_object_particle

# Alarm 줄에 싣기에 큰 충돌 상세만 이 칸에 남아 탭 맨 아래 CSV 단추로 내려받는다.
CONFLICT_REPORT_STATE_KEY = "bigdataquery_reference_conflict_report"
REGISTRATION_FLASH_KEY = "bigdataquery_registration_flash"
# 저장은 됐지만 업무 키 값이 갈린 그룹이 있을 때의 경고 — 알림창 · Alarm 에만(성공 알림 바로 뒤).
# 요약 · 상세는 그 Alarm 줄의 표다(`_queue_reference_conflict_report`).
REGISTRATION_CONFLICT_FLASH_KEY = "bigdataquery_registration_conflict_flash"
CONFLICT_SUMMARY_TITLE: Final = "충돌 요약"
CONFLICT_DETAIL_TITLE: Final = "충돌 상세"
CONFLICT_CSV_LABEL: Final = "기준정보 업무 키 충돌 CSV 다운로드"
# 저장은 됐지만 CS 가 비어 표에서 뺀 행이 있을 때의 경고 — 알림창 · Alarm 에만(성공 알림 뒤).
REGISTRATION_DROP_FLASH_KEY = "bigdataquery_registration_drop_flash"
# 저장은 됐지만 그 리비전의 대당 Capa 계산이 멈출 때의 경고(`RegistrationCapacityCheck`) — 알림창 ·
# Alarm 에만(맨 뒤). 푸는 길은 그 전문(Alarm)이 말한다.
REGISTRATION_CAPACITY_FLASH_KEY = "bigdataquery_registration_capacity_flash"
REGISTRATION_FLASH_KEYS: Final = (
    REGISTRATION_FLASH_KEY,
    REGISTRATION_CONFLICT_FLASH_KEY,
    REGISTRATION_DROP_FLASH_KEY,
    REGISTRATION_CAPACITY_FLASH_KEY,
)
# 저장 결과 칸(저장 단추 바로 아래)이 화면 밖이면 마지막 알림이 화면 아래에 닿게 본문을 옮기는
# 스크립트 — 이미 보이면 움직이지 않는다(`block: "nearest"`). 단추를 화면 맨 아래에 두고 누르면 그
# 아래 칸이 화면 밖이라 칸의 글이 보이지 않았다(2026-11-01 E2E — 1920×1080). 글은 칸에 알림(저장하지
# 못한 까닭)을 그린 회차에만 그 칸 끝에 서고, 앞머리의 일회 표지가 회차마다 달라 같은 자리에서도
# 다시 돈다(Streamlit 은 같은 글의 스크립트를 다시 돌리지 않는다).
REVEAL_NOTICE_SCRIPT: Final = """<script>/* {nonce} */
(() => {{
  const me = document.currentScript;
  const slot = me && me.closest('[data-testid="stVerticalBlock"]');
  const notes = slot ? slot.querySelectorAll('[data-testid="stAlert"]') : [];
  const last = notes[notes.length - 1];
  if (last) requestAnimationFrame(() => last.scrollIntoView({{block: "nearest"}}));
}})();
</script>"""

# 설정 띠 — 값 줄의 라벨과, 목록 · 상세 조회 SQL 과 패키지가 모두 준비됐을 때의 값 줄.
BANNER_LABEL: Final = "**BigDataQuery 설정**"
BANNER_READY_LINE: Final = f"{BANNER_LABEL} · 목록 · 상세 조회 SQL · 패키지 확인됨"
# 목록 검색 칸 풍선 — 행이 많을 때 좁히는 법(자리에는 행 수 표지만 선다).
CATALOG_KEYWORD_HELP: Final = (
    "시뮬레이션명 · 코드 · PLAN 의 부분 일치로 목록을 좁힙니다(공백은 AND). 행이 많으면 표 조작이 "
    "느릴 수 있어 검색어로 좁힙니다."
)
# 상세 조회 기간 칸 풍선 — 채우는 규칙과 넓히는 때.
DETAIL_WINDOW_HELP: Final = (
    f"목록에서 코드를 고르면 원천 등록일 {DETAIL_WINDOW_DAYS_BEFORE}일 전 ~ "
    f"{DETAIL_WINDOW_DAYS_AFTER}일 뒤로 채웁니다. 칸을 비우면 「원천 DB 등록시점」으로 같은 "
    "규칙을 씁니다. 등록 뒤에도 원천이 계속 수정·재적재됐으면 끝 날을 늘립니다 — 기간이 길수록 "
    "조회가 오래 걸립니다."
)
# 빈 필수 칸을 모아 알릴 때 기간 자리의 이름 — 둘 가운데 하나만 있으면 된다.
DETAIL_WINDOW_FIELDS: Final = "상세 조회 기간 또는 원천 DB 등록시점"
# 조회 SQL 이 없어 잠긴 두 단추의 풍선 — 잠긴 동안만 까닭을 말한다(설계 규칙 UI-INP-07). 채울 자리는
# 상태 알림 `AD-04` 전문(Alarm)이 적는다.
CATALOG_LOCKED_HELP: Final = (
    "목록 조회 SQL 이 설정되지 않아 조회할 수 없습니다 — 채울 자리는 Alarm 그 줄이 적습니다."
)
DETAIL_LOCKED_HELP: Final = (
    "상세 조회 SQL 이 설정되지 않아 조회 · 저장할 수 없습니다 — 채울 자리는 Alarm 그 줄이 적습니다."
)
# 고른 행이 검색에 가려졌을 때의 표지 풍선.
PICK_HIDDEN_HELP: Final = (
    "고른 행이 지금 검색 결과에 없습니다 — 아래 등록 폼의 값은 그대로 유지됩니다."
)

CATALOG_RESULT_KEY = "bigdataquery_catalog_result"
CATALOG_PICK_KEY = "bigdataquery_catalog_pick"
CATALOG_APPLIED_KEY = "bigdataquery_catalog_applied_signature"
# 폼의 코드를 목록에서 골랐을 때 그 코드가 목록에 보인 (가장 이른, 가장 늦은) 원천 등록일.
# 상세 조회 기간 칸의 기본값을 정한 근거로 안내에 적는다.
CATALOG_FORM_REGISTERED_SPAN_KEY = "bigdataquery_catalog_form_registered_span"
# 목록에서 골라 폼에 채운 코드·상세 조회 기간·원천 등록시점(`PickedFields`). 코드만 바꿔 적은 채
# 앞 코드의 값으로 조회·저장하는 것을 막는다.
CATALOG_FORM_PICKED_WINDOW_KEY = "bigdataquery_catalog_form_picked_window"
CATALOG_LIST_NONCE_KEY = "bigdataquery_catalog_list_nonce"
CATALOG_LAST_LIST_KEY = "bigdataquery_catalog_last_list_key"
CATALOG_RESET_REQUEST_KEY = "bigdataquery_catalog_reset_request"
CATALOG_START_DATE_KEY = "bigdataquery_catalog_start_date"
CATALOG_END_DATE_KEY = "bigdataquery_catalog_end_date"
CATALOG_QUERY_BUTTON_KEY = "bigdataquery_catalog_query"
DATE_FIELD_WIDTH_PX: Final = 300
CATALOG_TOOLBAR_KEY = "bigdataquery_catalog_toolbar"
# 표 위 한 줄의 전환 단추는 이웃 칸 · 단추와 같은 높이다 — 기본 28px 이면 라벨과 윗선이 7px 어긋난다
# (설계 규칙 UI-CON-01).
CATALOG_TOOLBAR_STYLE: Final = (
    f'<style>.st-key-{CATALOG_TOOLBAR_KEY} [data-testid="stButtonGroup"] button '
    "{ min-height: 2.5rem; }</style>"
)
CATALOG_KEYWORD_KEY = "bigdataquery_catalog_keyword"
CATALOG_SCOPE_KEY = "bigdataquery_catalog_scope"
CATALOG_LIST_KEY_PREFIX = "bigdataquery_catalog_rows_"

FORM_CODE_KEY = "bigdataquery_form_simulation_code"
FORM_SOURCE_NAME_KEY = "bigdataquery_form_source_name"
FORM_SCENARIO_NAME_KEY = "bigdataquery_form_scenario_name"
FORM_REVISION_NAME_KEY = "bigdataquery_form_revision_name"
FORM_REGISTERED_AT_KEY = "bigdataquery_form_registered_at"
FORM_NOTE_KEY = "bigdataquery_form_note"
# 상세 조회 기간(포함). 둘 다 비면 「원천 DB 등록시점」으로 기본 창을 정한다.
FORM_DETAIL_START_KEY = "bigdataquery_form_detail_start"
FORM_DETAIL_END_KEY = "bigdataquery_form_detail_end"
# 폼 글자 칸의 세대(`form_field_key`).
FORM_GENERATION_KEY = "bigdataquery_form_generation"
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
    # (코드, PLAN) 마다 목록에 보인 가장 이른 원천 등록일. 상세 조회 기본 창의 시작을 정한다.
    first_registered: Mapping[tuple[str, str], date] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogPick:
    """목록에서 고른 행과, 그 행을 찾아낸 조회 기간과, 그 **코드**가 목록에 보인 원천 등록일 범위.

    등록일 범위는 PLAN 을 가리지 않는다 — 상세 조회가 코드 전체를 받기 때문이다.
    """

    row: CatalogRow
    window: QueryWindow
    first_registered_on: date | None = None
    last_registered_on: date | None = None


@dataclass(frozen=True)
class PickedFields:
    """목록에서 고른 행이 폼에 채운, **그 코드에 딸린** 값. 코드 칸만 바뀌면 남의 값이 된다."""

    code: str
    start: date | None
    end: date | None
    registered_at: str


def render_bigdataquery_registration(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    alert_tab: str | None = "",
) -> None:
    """「DB 등록」 탭 본문. `alert_tab` 은 이 탭 이름(상태 알림 `AD-04` 의 「그
    화면으로」 — `state_alerts.open_tab_name`)이고 None 이면 닫힌 탭이라 그 회차에는 알리지
    않는다."""
    # 리셋 소비는 반드시 첫 줄이다. 위젯을 만든 뒤에는 그 key 를 지울 수 없다.
    _consume_reset_request()
    # 같은 까닭으로 위젯 앞이다. 리셋이 선택을 지운 뒤라 초기화한 폼은 되살리지 않는다.
    _restore_dropped_prefill()
    # 두 단계(① 기간으로 코드 찾기 ② 등록 정보 확인·저장)와 저장이 하는 일은 Guide 가 말한다.
    catalog_ready = is_bigdataquery_catalog_configured()
    detail_ready = is_bigdataquery_adapter_configured()
    _render_configuration_banner(
        catalog_ready=catalog_ready,
        detail_ready=detail_ready,
        package_ready=is_bigdataquery_package_available(),
        alert_tab=alert_tab,
    )
    registered_codes, existing_names = _registered_scenarios(repository)
    # 찾기 칸과 그 표의 작업은 표 위 한 줄이다 — 기준 창보다 좁으면 줄이 내려앉는다(설계 규칙
    # UI-LAY-11 · UI-ACC-02). 조회의 거부 · 스피너와 조회 결과 줄은 이 줄 바로 아래 · 표 바로 위다.
    st.html(CATALOG_TOOLBAR_STYLE)
    toolbar = st.container(
        key=CATALOG_TOOLBAR_KEY, horizontal=True, gap="small", vertical_alignment="bottom"
    )
    _render_catalog_form(toolbar, configured=catalog_ready)
    _render_catalog_list(toolbar, registered_codes=registered_codes)
    _render_registration_form(
        repository,
        database_path,
        configured=detail_ready,
        existing_names=existing_names,
    )
    # 큰 충돌 상세의 CSV 단추는 한 런에 딱 한 번만 그린다. 저장 실패 분기에서 한 번 더 부르면
    # 같은 다운로드 key 가 두 번 나와 `StreamlitDuplicateElementKey` 로 탭이 죽는다.
    _render_oversized_conflict_download()


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


def missing_query_notice(*, catalog_ready: bool, detail_ready: bool) -> str | None:
    """설정하지 않은 사내 조회 SQL 알림. 둘 다 설정했으면 None.

    조사는 고정 낱말 「SQL」 에 붙이고 빠진 자리는 줄표 뒤에 늘어놓는다 — 자리 이름 끝(템플릿
    상수 이름) 뒤에 조사를 두면 갈래 꼴 「… 이(가)」 이었다(E2E, 개선 거리 I8).
    """
    missing: list[str] = []
    if not catalog_ready:
        missing.append("목록 조회 SQL(bigdataquery_catalog.py의 CATALOG_QUERY_TEMPLATE)")
    if not detail_ready:
        missing.append("상세 조회 SQL(company_bigdataquery_adapter.py의 QUERY_TEMPLATE)")
    if not missing:
        return None
    return "조회 SQL이 아직 설정되지 않았습니다 — " + "·".join(missing) + "."


def banner_line(*, catalog_ready: bool, detail_ready: bool, package_ready: bool) -> str:
    """설정 띠 값 줄 — 「**BigDataQuery 설정** · …」. 준비 안 된 칸은 주황 표지 한 마디다(설계 규칙
    UI-TXT-04 — 값 · 표지만). 무엇이 빠졌고 어디를 채우는지(SQL 자리 · 패키지 · CD 서버 시작 점검)는
    상태 알림 `AD-04` 의 전문이 말한다(UI-NTF-02 — 상태 경고는 자리에 세우지 않는다)."""
    if catalog_ready and detail_ready:
        if package_ready:
            return BANNER_READY_LINE
        return f"{BANNER_LABEL} · 목록 · 상세 조회 SQL 확인됨 · :orange[패키지 없음]"
    missing = [
        f":orange[{name} 미설정]"
        for name, ready in (("목록 조회 SQL", catalog_ready), ("상세 조회 SQL", detail_ready))
        if not ready
    ]
    return f"{BANNER_LABEL} · " + " · ".join(missing)


def _render_configuration_banner(
    *,
    catalog_ready: bool,
    detail_ready: bool,
    package_ready: bool,
    alert_tab: str | None = "",
) -> None:
    """설정 값 줄(`banner_line`) — 준비가 안 됐으면 그 내역을 상태 알림(`AD-04` — 알림창 ·
    Alarm)으로 낸다. 자리에는 값 줄만 둔다(점검 결론 — 「**라벨** · 값」 평문, 경고 · 초록 상자
    아님). 회차마다 한 번 부른다(해소 · 이벤트 칸 한 자리) — 닫힌 탭(`alert_tab` None)이면 알리지
    않는다."""
    notice = missing_query_notice(catalog_ready=catalog_ready, detail_ready=detail_ready)
    if notice is None and not package_ready:
        notice = (
            "SQL 설정은 확인했습니다. 다만 현재 PC 에는 bigdataquery 패키지가 없어 "
            "실제 조회는 패키지를 깐 PC 에서만 성공합니다."
        )
        # C-DEP CD 컨테이너에서는 시작 스크립트가 남긴 설치 단계 결과와 넣을 환경변수를 잇는다.
        hint = start_check_hint(STEP_INSTALL)
        if hint:
            notice = f"{notice}\n\n{hint}"
    if alert_tab is not None:
        alerts.state(
            "AD-04",
            scope=None,
            content=notice,
            active=notice is not None,
            text=(
                "BigDataQuery 조회 SQL 이 설정되지 않았습니다 — 조회 · 등록이 막힘"
                if notice is not None and not (catalog_ready and detail_ready)
                else "bigdataquery 패키지가 없어 실제 조회가 실패합니다 — 패키지를 깐 PC 에서"
            ),
            full=alerts.plain_text(notice) if notice else None,
            tab=alert_tab,
        )
    line = banner_line(
        catalog_ready=catalog_ready, detail_ready=detail_ready, package_ready=package_ready
    )
    st.caption(line if notice is None else f":material/settings_alert: {line}")


def _registered_scenarios(
    repository: DuckDBScenarioRepository,
) -> tuple[frozenset[str], frozenset[str]]:
    """(이미 등록된 원천 코드, 이미 쓰인 시나리오명).

    매 렌더 다시 계산한다. 세션 프레임에 구워 두면 저장 직후 목록의 `등록여부` 가 낡는다.
    """
    try:
        # 보관본까지 본다. 숨은 시나리오를 못 보면 같은 원천 코드로 하나가 더 생긴다.
        scenarios = repository.list_scenarios(include_archived=True)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            bootstrap_error_message(exc),
            code="SC-02",
            tab=QUERY_TAB_NAME,
            text="등록된 시나리오를 읽지 못했습니다",
        )
        return frozenset(), frozenset()
    return (
        frozenset(str(scenario.source_simulation_code) for scenario in scenarios),
        frozenset(str(scenario.scenario_name) for scenario in scenarios),
    )


def _render_catalog_form(toolbar: DeltaGenerator, *, configured: bool) -> None:
    today = datetime.now().date()
    st.session_state.setdefault(
        CATALOG_START_DATE_KEY, today - timedelta(days=DEFAULT_CATALOG_DAYS)
    )
    st.session_state.setdefault(CATALOG_END_DATE_KEY, today)
    with toolbar:
        # 칸이 「적용」 때만 서버로 보내므로 폼이 없어도 고르는 동안 회차가 돌지 않는다.
        date_range_field(
            "조회일",
            start_key=CATALOG_START_DATE_KEY,
            end_key=CATALOG_END_DATE_KEY,
            default=(today - timedelta(days=DEFAULT_CATALOG_DAYS), today),
            width=DATE_FIELD_WIDTH_PX,
        )
        clicked = st.button(
            "시뮬레이션 코드 조회",
            key=CATALOG_QUERY_BUTTON_KEY,
            icon=":material/search:",
            type="primary",
            disabled=not configured,
            help=None if configured else CATALOG_LOCKED_HELP,
        )
    if not clicked:
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
        with st.spinner(f"DB에서 {window.label()} 구간의 시뮬레이션 코드를 조회하는 중입니다..."):
            frame = fetch_simulation_catalog(window)
            catalog = normalize_catalog(frame)
            first_registered = first_registration_dates(frame)
            queried_at = datetime.now()
            # 세션 대입을 spinner 블록 안에서 끝낸다. 블록을 빠져나가는 첫 `st` 호출이
            # 탭 전환 rerun 으로 터지면 조회 결과가 통째로 버려진다.
            st.session_state[CATALOG_RESULT_KEY] = CatalogResult(
                frame=catalog,
                window=window,
                queried_at=queried_at,
                token=view_token(window.label(), queried_at.isoformat(timespec="microseconds")),
                first_registered=first_registered,
            )
            # 결과셋이 바뀌었으니 선택만 버린다. 폼에 적힌 값은 건드리지 않는다.
            _clear_pick()
    except BOOTSTRAP_ERRORS as exc:
        # 실패해도 직전 목록은 지우지 않는다.
        st.error(bootstrap_error_message(exc))


def _render_catalog_list(toolbar: DeltaGenerator, *, registered_codes: frozenset[str]) -> None:
    result = _stored_result()
    if result is None:
        st.caption("조회한 시뮬레이션 코드 목록이 없습니다.")
        return
    st.caption(
        f"{result.window.label()} · {result.queried_at:%H:%M:%S} 조회 · "
        f"코드·PLAN 기준 {len(result.frame):,}건"
    )
    if result.frame.empty:
        st.caption("이 기간에는 시뮬레이션 코드가 없습니다.")
        return

    with toolbar:
        keyword = st.text_input(
            "검색",
            key=CATALOG_KEYWORD_KEY,
            persist_state="session",
            # 목록을 좁히는 필터 전용이다. 검색 칸으로 선언하면 값이 있을 때 지우기 버튼이
            # 붙어, 전체 목록으로 되돌리는 조작이 한 번에 끝난다.
            type="search",
            width=360,
            # 빈 글자라야 칸이 빈다 — None 이면 `type="search"` 기본 글 「Search」 가 선다.
            placeholder="",
            help=CATALOG_KEYWORD_HELP,
        )
        scope = st.segmented_control(
            "표시 범위",
            SCOPE_OPTIONS,
            default=SCOPE_ALL,
            key=CATALOG_SCOPE_KEY,
            persist_state="session",
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
        st.caption("검색 조건에 맞는 코드가 없습니다.")
        return
    # 행이 많아 표 조작이 느릴 수 있다는 말과 좁히는 법은 검색 칸 풍선(`CATALOG_KEYWORD_HELP`)이
    # 말한다 — 자리에는 행 수 표지만(설계 규칙 UI-TXT-01 · UI-TXT-04).
    if len(visible) > CATALOG_BUSY_ROWS:
        st.caption(f"**표시 행** · :orange[{len(visible):,}행 — 많음]")

    pick = _stored_pick()
    position = row_position(visible, pick.row.signature) if pick is not None else None
    selection_default: dict[str, Any] | None = None
    if position is not None:
        selection_default = {"selection": {"rows": [position], "columns": []}}
    elif pick is not None:
        # 숨은 선택 안내는 표지 + 풍선이다(설계 규칙 UI-TXT-04).
        st.caption("**선택한 행** · 검색 결과 밖", help=PICK_HIDDEN_HELP)

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
            _apply_pick(catalog_pick(result, row))
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


def catalog_pick(result: CatalogResult, row: CatalogRow) -> CatalogPick:
    """목록에서 고른 행을 폼에 채울 선택으로 만든다.

    등록일 범위는 **정리된 목록 전체**(`result.frame`)에서 그 코드의 모든 PLAN 줄로 구한다 — 검색·
    표시 범위로 좁힌 `visible` 로 구하면 필터가 범위를 줄인다. 상세 조회는 PLAN 을 가리지 않는다.
    """
    span = code_registration_span(result.frame, result.first_registered, row.simulation_code)
    return CatalogPick(
        row=row,
        window=result.window,
        first_registered_on=None if span is None else span[0],
        last_registered_on=None if span is None else span[1],
    )


def _apply_pick(pick: CatalogPick) -> None:
    st.session_state[CATALOG_PICK_KEY] = pick
    if st.session_state.get(CATALOG_APPLIED_KEY) == pick.row.signature:
        # 같은 행이 계속 선택돼 있을 뿐이다. 사용자가 고친 값을 덮지 않는다.
        return
    prefill = registration_prefill(pick.row, catalog_window_label=pick.window.label())
    # 목록 정리는 (코드, PLAN) 의 최신 행만 남기므로 행의 등록일이 가장 늦은 날이고, 가장 이른
    # 날은 정리 전에 따로 구해 둔 것이다. 둘 사이가 벌어졌으면 등록 뒤에도 적재가 이어진 코드다.
    last = pick.last_registered_on or _registered_day(pick.row.registered_at)
    first = pick.first_registered_on or last
    span = None if first is None else (first, last or first)
    window = None if span is None else registration_detail_window(*span)
    st.session_state[CATALOG_APPLIED_KEY] = pick.row.signature
    st.session_state[CATALOG_FORM_REGISTERED_SPAN_KEY] = span
    st.session_state[CATALOG_FORM_PICKED_WINDOW_KEY] = PickedFields(
        code=pick.row.simulation_code,
        start=None if window is None else window.start_date,
        end=None if window is None else window.end_date,
        registered_at=prefill.registered_at,
    )
    st.session_state[FORM_DETAIL_START_KEY] = None if window is None else window.start_date
    st.session_state[FORM_DETAIL_END_KEY] = None if window is None else window.end_date
    _write_form_prefill(pick)


def form_field_key(field: str) -> str:
    """폼 글자 칸(`FORM_DEFAULTS` 의 이름)의 지금 세대 key. 세대 0 은 이름 그대로다."""
    return widget_key(field, FORM_GENERATION_KEY)


def _write_form_prefill(pick: CatalogPick) -> None:
    """고른 행의 값으로 등록 폼 글자 칸 여섯(`FORM_DEFAULTS`)을 채운다. 상세 조회 기간은 뺀다.

    새 세대의 칸에 쓴다 — 칸에 친 채 제출하지 않은 글자가 고른 행의 값과 함께 남지 않게 한다."""
    prefill = registration_prefill(pick.row, catalog_window_label=pick.window.label())
    bump(FORM_GENERATION_KEY)
    st.session_state[form_field_key(FORM_CODE_KEY)] = prefill.simulation_code
    st.session_state[form_field_key(FORM_SOURCE_NAME_KEY)] = prefill.source_name
    st.session_state[form_field_key(FORM_SCENARIO_NAME_KEY)] = prefill.scenario_name
    st.session_state[form_field_key(FORM_REVISION_NAME_KEY)] = prefill.revision_name
    st.session_state[form_field_key(FORM_REGISTERED_AT_KEY)] = prefill.registered_at
    st.session_state[form_field_key(FORM_NOTE_KEY)] = prefill.note


def _restore_dropped_prefill() -> None:
    """선택은 남았는데 폼 글자 칸만 버려졌으면 그 선택의 값으로 다시 채운다.

    선택·적용 서명은 위젯이 아닌 칸이라 남지만, 글자 칸은 입력 초안이라 `persist_state` 가 없어
    등록 폼을 그리지 않은 회차(다른 화면을 다녀옴, 다른 탭의 `st.rerun()`)에 Streamlit 이 버린다.
    목록 표는 같은 행을 다시 고를 뿐이라 `_apply_pick` 이 같은 서명을 보고 채우지 않으므로, 행은
    선택된 채 코드·이름이 비어 저장이 막힌다. 상세 조회 기간은 세션에 남아 사용자가 넓힌 값이므로
    건드리지 않는다. 위젯을 만들기 전에 불러야 한다.
    """
    pick = _stored_pick()
    if pick is None or form_field_key(FORM_CODE_KEY) in st.session_state:
        return
    if st.session_state.get(CATALOG_APPLIED_KEY) != pick.row.signature:
        return
    _write_form_prefill(pick)


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
        CATALOG_FORM_REGISTERED_SPAN_KEY,
        CATALOG_FORM_PICKED_WINDOW_KEY,
        FORM_DETAIL_START_KEY,
        FORM_DETAIL_END_KEY,
    ):
        st.session_state.pop(key, None)
    bump(FORM_GENERATION_KEY)


def _render_registration_form(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    configured: bool,
    existing_names: frozenset[str],
) -> None:
    for key, value in FORM_DEFAULTS.items():
        st.session_state.setdefault(form_field_key(key), value)
    st.session_state.setdefault(FORM_DETAIL_START_KEY, None)
    st.session_state.setdefault(FORM_DETAIL_END_KEY, None)
    pick = _stored_pick()
    # 저장 불가는 목록 표 「저장가능」 칸이 값으로, 까닭은 잠긴 저장 단추 풍선이 말한다(설계 규칙
    # UI-INP-07 — 막힘을 상자로 세우지 않는다).
    unsavable = pick is not None and not pick.row.savable
    # 상세 조회 기간을 채우는 규칙은 칸 풍선(`DETAIL_WINDOW_HELP`)이 말하고, 자리에는 고른 코드의
    # 원천 등록일 값 줄만 둔다(설계 규칙 UI-TXT-01 · UI-TXT-04). 늘 서 있는 칸 안이라 값 줄이 생기고
    # 빠져도 아래 폼의 자리가 밀리지 않는다. 날짜 칸은 「적용」 트리거를 바로 받아야 해 폼 밖이다 —
    # 폼 안 트리거는 제출 때까지 서버에 오지 않는다(`components/date_panel.py`).
    with st.container():
        registered_line = _registered_span_line()
        if registered_line is not None:
            st.caption(registered_line)
    optional_date_range_field(
        "상세 조회 기간",
        start_key=FORM_DETAIL_START_KEY,
        end_key=FORM_DETAIL_END_KEY,
        max_date=datetime.now().date(),
        help=DETAIL_WINDOW_HELP,
        width=DATE_FIELD_WIDTH_PX,
    )
    with st.form("bigdataquery_registration_form"):
        st.text_input("조회할 시뮬레이션 코드", key=form_field_key(FORM_CODE_KEY))
        st.text_input("원천 시뮬레이션명", key=form_field_key(FORM_SOURCE_NAME_KEY))
        st.text_input("저장할 시나리오명", key=form_field_key(FORM_SCENARIO_NAME_KEY))
        st.text_input("초기 리비전명", key=form_field_key(FORM_REVISION_NAME_KEY))
        st.text_input(
            "원천 DB 등록시점 (선택)",
            key=form_field_key(FORM_REGISTERED_AT_KEY),
            placeholder="2026-08-29 14:30:00",
            # 빈 값은 검증을 건너뛰므로 (선택) 의미가 그대로다. 앞뒤 공백을 허용하는 것은
            # 원천 DB 값을 붙여넣는 칸이고 `_optional_datetime` 이 `strip()` 하기 때문이다.
            # 브라우저에서 우회할 수 있으므로 서버의 파싱은 최종 방어선으로 남긴다.
            validate=(
                r"^\s*\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?\s*$",
                "등록시점은 YYYY-MM-DD HH:MM:SS 형식으로 입력하세요.",
            ),
        )
        st.text_area("등록 메모", key=form_field_key(FORM_NOTE_KEY), height=90)
        submitted = st.form_submit_button(
            "DB 조회 후 시나리오 저장",
            icon=":material/cloud_download:",
            type="primary",
            width="stretch",
            disabled=not configured or unsavable,
            help=DETAIL_LOCKED_HELP if not configured else UNSAVABLE_REASON if unsavable else None,
        )
    # 저장 결과 칸은 누른 단추 바로 아래 늘 서 있는 한 칸이다(`flash` — 버튼과 같은 상자, VOC 글
    # 올리기와 같은 꼴). 성공 · 저장 뒤 경고(업무 키 충돌 · CS 빈 행 · 대당 Capa 멈춤)는 알림창 ·
    # Alarm 으로만 가고, 이 칸에는 저장하지 못한 까닭(거부 · 실패)이 선다 — 탭 맨 위에 두면 단추가
    # 폼 맨 아래라 스크롤한 화면에서 보이지 않았다(2026-11-01 E2E — 1500×950). 칸은 알림이 없어도
    # 서서 아래 칸의 자리가 밀리지 않는다. 칸에 글을 그린 회차에는 칸 끝의
    # 스크립트(`REVEAL_NOTICE_SCRIPT`)가 칸이 화면 밖일 때만 본문을 옮긴다.
    queued = any(_drawn_beside(pending_flash(key)) for key in REGISTRATION_FLASH_KEYS)
    notice = render_flash(*REGISTRATION_FLASH_KEYS)
    if queued:
        _reveal_notice(notice)
    if submitted:
        with notice:
            _save_scenario(repository, database_path, existing_names=existing_names)
        # 저장하면 다음 회차로 넘어가므로(`st.rerun`) 여기까지 오면 칸에 저장하지 못한 까닭이 섰다.
        _reveal_notice(notice)


def _drawn_beside(note: FlashNote | None) -> bool:
    """담아 둔 알림이 칸 안에도 그려지나(경고 · 오류이고 알림창으로만이 아님 — `flash`)."""
    return note is not None and note.kind in BESIDE_KINDS and not note.popup_only


def _reveal_notice(slot: DeltaGenerator) -> None:
    """저장 결과 칸 끝에 칸이 화면 밖일 때만 본문을 옮기는 스크립트를 세운다
    (`REVEAL_NOTICE_SCRIPT`)."""
    slot.html(REVEAL_NOTICE_SCRIPT.format(nonce=uuid.uuid4().hex), unsafe_allow_javascript=True)


def _save_scenario(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    existing_names: frozenset[str],
) -> None:
    st.session_state.pop(CONFLICT_REPORT_STATE_KEY, None)
    scenario_name = str(st.session_state.get(form_field_key(FORM_SCENARIO_NAME_KEY), "")).strip()
    if scenario_name in existing_names:
        # 같은 이름이 둘이면 사이드바에서 구분되지 않는다. 사내 조회 한 번을 아끼려고
        # 조회 전에 막는다.
        st.error("같은 이름의 시나리오가 이미 있습니다. 이름을 바꿔 저장하세요.")
        return
    simulation_code = str(st.session_state.get(form_field_key(FORM_CODE_KEY), ""))
    source_name = str(st.session_state.get(form_field_key(FORM_SOURCE_NAME_KEY), ""))
    revision_name = (
        str(st.session_state.get(form_field_key(FORM_REVISION_NAME_KEY), "")) or "초기 리비전"
    )
    note = str(st.session_state.get(form_field_key(FORM_NOTE_KEY), ""))
    try:
        registered_at = _optional_datetime(
            str(st.session_state.get(form_field_key(FORM_REGISTERED_AT_KEY), ""))
        )
    except ValueError as exc:
        st.error(bootstrap_error_message(exc))
        return
    # 빈 칸을 **한 번에** 모두 알린다 — 사내 조회 앞에서 막아 조회 한 번을 아끼고, 한 칸씩 말해 여러
    # 번 누르지 않게 한다(복제 폼과 같은 꼴). 기간만 빈 회차는 `_submitted_detail_window` 가 말한다.
    missing = [
        label
        for label, value in (
            ("조회할 시뮬레이션 코드", simulation_code),
            ("원천 시뮬레이션명", source_name),
            ("저장할 시나리오명", scenario_name),
        )
        if not value.strip()
    ]
    if missing:
        if registered_at is None and _detail_window_is_empty():
            missing.append(DETAIL_WINDOW_FIELDS)
        st.error(f"필수 칸이 비어 있습니다: {', '.join(missing)}")
        return
    window = _submitted_detail_window(registered_at, simulation_code=simulation_code)
    if window is None:
        return
    note = registration_note(note, window)
    try:
        display_order = load_global_display_order(database_path).rules
        provider = BigDataQueryCoreDataProvider(
            simulation_name=source_name,
            source_registered_at=registered_at,
            window=window,
        )
        with st.spinner(
            f"DB에서 Core Data를 조회하고 검증하는 중입니다 — 상세 조회 {window.label()}"
            f"({window.days}일)..."
        ):
            prepared = fetch_core_data_dataset(provider, simulation_code, display_order)
            preset = capture_full_data_scenario_preset(prepared.reference_tables)
            registration = save_bigdataquery_scenario(
                repository,
                prepared,
                preset,
                scenario_name=scenario_name,
                revision_name=revision_name,
                note=note,
            )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    snapshot = registration.snapshot
    activate_persisted_snapshot(snapshot)
    follow_created_scenario(repository, snapshot.scenario.scenario_id)
    # 목록은 남긴다. 선택과 폼만 비워 다음 코드를 이어서 등록할 수 있게 한다.
    _request_reset()
    queue_flash(
        REGISTRATION_FLASH_KEY,
        f"{with_object_particle(snapshot.scenario.scenario_name)} 저장하고 "
        f"{with_object_particle(f'r{snapshot.revision.revision_no}')} "
        "올렸습니다.",
    )
    # 아래 세 경고는 저장이 끝났고 그 자리에 고칠 입력이 없어 알림창 · Alarm 에만 낸다(설계 규칙
    # UI-NTF-03 · AMB-05 (나) — 저장 단추 밑에는 그리지 않는다).
    _queue_reference_conflict_report(prepared.reference_conflicts, prepared.batch.simulation_code)
    if prepared.blank_cs.dropped:
        # 저장은 됐다 — 막지 않고 알린다. 같은 수가 리비전 메모에도 남는다.
        queue_flash(
            REGISTRATION_DROP_FLASH_KEY,
            prepared.blank_cs.notice(),
            kind="warning",
            icon=":material/warning:",
            popup_only=True,
        )
    if registration.capacity.stopped:
        # 저장은 됐다 — 막지 않고 무엇이 멈췄는지와 푸는 길을 알린다(2026-11-01 사용자 결정 —
        # 알림창 짧은 글이 무엇이 멈췄는지, Alarm 전문이 푸는 길). 꼴·개수는 리비전 메모에도 남는다.
        queue_flash(
            REGISTRATION_CAPACITY_FLASH_KEY,
            markdown_safe_tildes(registration.capacity.notice(snapshot.revision.revision_no)),
            kind="warning",
            icon=":material/warning:",
            popup_only=True,
        )
    st.rerun()


def _stored_result() -> CatalogResult | None:
    stored = st.session_state.get(CATALOG_RESULT_KEY)
    return stored if isinstance(stored, CatalogResult) else None


def _stored_pick() -> CatalogPick | None:
    stored = st.session_state.get(CATALOG_PICK_KEY)
    return stored if isinstance(stored, CatalogPick) else None


def _registered_day(text: str) -> date | None:
    """폼·목록의 원천 등록시각 문자열에서 날짜만. 못 읽으면 None — 저장 경로가 따로 검증한다."""
    try:
        parsed = _optional_datetime(text)
    except ValueError:
        return None
    return parsed.date() if parsed is not None else None


def _picked_for_another_code(simulation_code: str) -> PickedFields | None:
    """폼의 코드가 목록에서 고른 코드와 다르면 그때 채운 값을 돌려준다(같거나 고른 적 없으면 None).

    고른 뒤 코드 칸만 고쳐 적으면 앞 코드의 등록일 창·등록시점으로 오류 없이 조회돼, 창 밖
    적재분이 빠진 원천이 남의 등록시점을 달고 저장됐다(2026-09-29·30 리뷰). 사용자가 고친 값은
    믿는다 — 막는 것은 「손대지 않은 남의 값」뿐이다.
    """
    picked = st.session_state.get(CATALOG_FORM_PICKED_WINDOW_KEY)
    if not isinstance(picked, PickedFields):
        return None
    typed = simulation_code.strip()
    return picked if typed and typed != picked.code else None


def _registered_span_line() -> str | None:
    """상세 조회 기간 칸 위의 값 줄 — 「**고른 코드의 원천 등록일** · 2026-09-02」(목록에서 고른
    코드가 없으면 None). 고른 값은 그 칸이 말하므로 이 줄은 채운 근거를 적는다 — 채우는 규칙은 칸
    풍선(`DETAIL_WINDOW_HELP`)이 말한다."""
    span = st.session_state.get(CATALOG_FORM_REGISTERED_SPAN_KEY)
    if not isinstance(span, tuple) or len(span) != 2:
        return None
    first, last = span
    seen = f"{first:%Y-%m-%d}" if first == last else f"{first:%Y-%m-%d} ~ {last:%Y-%m-%d}"
    return f"**고른 코드의 원천 등록일** · {seen}"


def _detail_window_is_empty() -> bool:
    """상세 조회 기간 두 칸이 모두 비었는가."""
    start = st.session_state.get(FORM_DETAIL_START_KEY)
    end = st.session_state.get(FORM_DETAIL_END_KEY)
    return not isinstance(start, date) and not isinstance(end, date)


def _submitted_detail_window(
    registered_at: datetime | None, *, simulation_code: str = ""
) -> QueryWindow | None:
    """저장 때 조회할 상세 기간. 칸의 값이 우선이고, 비었으면 원천 DB 등록시점으로 정한다.

    예전에는 기본 90일 ∪ 목록 기간 ∪ 등록일 7일 전~오늘을 모두 덮어, 옛 코드일수록 창이 길어져
    조회가 오래 걸렸다(2026-09-29 사용자 결정 A+B — 기본은 등록일 앞뒤로 좁게, 필요하면 넓힌다).
    기간을 모르는 채로 넓은 기본 창을 조용히 쓰지 않는다 — 둘 다 없으면 막고 무엇을 채울지 알린다.
    """
    start = st.session_state.get(FORM_DETAIL_START_KEY)
    end = st.session_state.get(FORM_DETAIL_END_KEY)
    other = _picked_for_another_code(simulation_code)
    if other is not None:
        typed_at = str(st.session_state.get(form_field_key(FORM_REGISTERED_AT_KEY), "")).strip()
        if other.registered_at.strip() and typed_at == other.registered_at.strip():
            # 등록시점은 저장 메타데이터(`source_registered_at`)이기도 하다. 기간을 고쳤어도
            # 남의 등록시점이 이 코드의 원천 등록시점으로 저장되면 안 된다.
            st.error(
                "「원천 DB 등록시점」이 목록에서 고른 **다른 코드**의 값 그대로입니다. 코드를 "
                "바꿨으면 이 코드의 등록시점으로 고치거나 비우세요."
            )
            return None
    if isinstance(start, date) and isinstance(end, date):
        if start > end:
            st.error("상세 조회 시작일은 종료일보다 늦을 수 없습니다.")
            return None
        if other is not None and (start, end) == (other.start, other.end):
            st.error(
                "상세 조회 기간이 목록에서 고른 **다른 코드**의 원천 등록일로 채워진 그대로입니다. "
                "코드를 바꿨으면 기간을 이 코드에 맞는 날짜로 고치거나, 기간을 비우고 「원천 DB "
                "등록시점」을 이 코드의 값으로 적으세요."
            )
            return None
        return QueryWindow(start_date=start, end_date=end)
    if isinstance(start, date) or isinstance(end, date):
        st.error("상세 조회 시작일과 종료일을 모두 지정하거나 둘 다 비우세요.")
        return None
    if registered_at is None:
        st.error("상세 조회 기간을 지정하거나 「원천 DB 등록시점」을 적으세요.")
        return None
    return registration_detail_window(registered_at.date())


def _queue_reference_conflict_report(conflicts: pd.DataFrame, simulation_code: str) -> None:
    """저장한 등록의 「기준정보 업무 키 충돌」 보고 — 자리에 그리지 않고 사건 알림 `SC-04` 와 그
    Alarm 줄의 표(요약 · 상세, 표마다 CSV)로 낸다. 상세의 공정 칸은 화면에서만 표시명이고 CSV 는
    원본이다.

    상세가 커서 Alarm 줄에 싣지 못하면(`alert_table` 이 None) 그 표만 탭 맨 아래 CSV 단추로 남기고
    알림 글이 그 자리를 부른다(`_render_oversized_conflict_download`)."""
    if conflicts.empty:
        return
    safe_code = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", simulation_code).strip("._") or "query"
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    file_name = f"RQ_업무키_충돌_{safe_code}_{timestamp}.csv"
    summary = alert_table(
        summarize_reference_conflicts(conflicts),
        title=CONFLICT_SUMMARY_TITLE,
        file_name=f"RQ_업무키_충돌_요약_{safe_code}_{timestamp}.csv",
    )
    detail = alert_table(
        conflicts,
        title=CONFLICT_DETAIL_TITLE,
        file_name=file_name,
        labels=get_process_labels(),
    )
    detail_place = alarm_table_place(CONFLICT_DETAIL_TITLE)
    if detail is None:
        st.session_state[CONFLICT_REPORT_STATE_KEY] = {
            "report": conflicts.copy(),
            "file_name": file_name,
        }
        detail_place = f"이 탭 「{CONFLICT_CSV_LABEL}」"
    # 앞 60자가 결과를 말한다(알림창 짧은 글). 승자는 표마다 「값이 있는 첫 행」 이라 원천 첫
    # 행이라고 적지 않는다 — 규칙은 요약 표 「임시처리」 칸(`conflict_resolution` 한 곳)이 말한다.
    queue_flash(
        REGISTRATION_CONFLICT_FLASH_KEY,
        f"기준정보 업무 키 충돌 {len(conflicts):,}개 그룹 — 표 「임시처리」 규칙대로 한 행씩 임시 "
        f"적용하고 등록했습니다. 규칙: {alarm_table_place(CONFLICT_SUMMARY_TITLE)} · 행마다의 값: "
        f"{detail_place}",
        kind="warning",
        icon=":material/warning:",
        alert="SC-04",
        popup_only=True,
        tables=(summary, detail),
    )


def _render_oversized_conflict_download() -> None:
    """Alarm 줄에 싣기에 큰 충돌 상세의 CSV 단추 — 칸이 비면 아무것도 그리지 않는다."""
    payload = st.session_state.get(CONFLICT_REPORT_STATE_KEY)
    if not isinstance(payload, dict):
        return
    report = payload.get("report")
    file_name = payload.get("file_name")
    if not isinstance(report, pd.DataFrame) or report.empty or not isinstance(file_name, str):
        return
    render_csv_download(
        data=reference_conflicts_to_csv(report),
        file_name=file_name,
        key="reference_conflicts_download",
        label=CONFLICT_CSV_LABEL,
    )


def _optional_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("원천 DB 등록시점은 YYYY-MM-DD HH:MM:SS 형식이어야 합니다.") from exc
