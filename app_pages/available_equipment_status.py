# Purpose: 가용설비 현황 두 탭(설비 마스터·Summary)과 설정·엑셀·CSV 팝업을 잇고 데모 경계를 둔다.

"""가용설비 현황 — 탭 둘(2026-10-24 사용자 결정 — 두 탭 개편).

- ① **설비 마스터**(처음 여는 탭) — 설비 마스터 표(불러오기·칸 고치기·붙여넣기·한꺼번에 고치기)·
  작은 편집표 둘(기존 보유대수·비가동 일정)·오른쪽 칸(호기 상세·저장 전 변경·저장 이력) —
  `components/equipment_master_tab.py`. **열린 회차에만 그린다**(개편 B1 — 표 편집은 세션 칸에 산다,
  AGENTS 9장 「숨은 탭에서도 입력 위젯은 그린다」 의 예외). 그 모듈은 표 컴포넌트를 등록하므로 열린
  회차에만 불러온다. 작은 편집표 제출은 그 탭의 모든 위젯을 그린 뒤 `st.rerun()` 으로 끝나므로
  **코드 차례는 Summary 블록 뒤**다 — 화면 차례는 `stateful_tabs` 목록이 정해 ① 이 먼저다.
- ② **Summary** — 안쪽 탭 「Main」(설비 조회)·「Static 대비 일정」(월별 비교). 안쪽 탭은 바깥
  Summary 블록 안에서 늘 부르고(위젯 값이 남아 사이드바가 읽는다), 본문 갈래는 바깥·안쪽이 함께
  열렸을 때만 돈다(`NestedTab`) — ① 을 보는 회차에 Main 탐색·Static 대비 일정 계산이 돌지 않는다.
- 머리 끝 「설정」 단추 → 공정별 Cut-off 팝업(`equipment_settings_dialog`), 탭 ① 「엑셀·CSV로
  한꺼번에」 → 붙여넣기·CSV 팝업(`equipment_import_dialog` — 「편집본에 넣기」 까지). 두 팝업은 한
  열림 칸·한 호스트다. Static 대비 일정은 Cut-off 를 캐시 경계(`load_process_cutoff`)에서 직접
  읽는다.
- Qual 마감 계산기는 필요 단축 일정 머리의 팝업, 설비 시나리오 목록·발행은 시나리오 관리 › 설비
  시나리오다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

# 테스트가 공정 표시명 조회를 모듈 속성으로 갈아 끼운다 — 이름을 직접 들이면 그 교체를 못 본다.
import capa_simulation.components.process_labels as process_labels_module
from capa_simulation.components.availability_gap_panel import render_availability_gap_panel
from capa_simulation.components.equipment_data_workspace import (
    BASELINE_DRAFT_KEY,
    DOWNTIME_DRAFT_KEY,
    EQUIPMENT_DRAFT_KEY,
    FLASH_KEY,
    _official_places_by_name,
    calculation_drafts,
    draft_unscheduled_units,
    effective_floor_canvases,
    ensure_equipment_drafts,
    has_unsaved_equipment_edits,
    live_layout_role,
    pending_fab_layout,
    pop_discarded_notice,
    pop_drafts_replaced,
    settle_grid_toasts,
    small_editor_edits,
)
from capa_simulation.components.equipment_explorer import (
    render_equipment_explorer,
    render_equipment_period,
)
from capa_simulation.components.equipment_import_dialog import (
    ImportContext,
    open_equipment_import,
    render_import_dialog,
    withdraw_preview_on_new_visit,
)
from capa_simulation.components.equipment_scenario_status import (
    PREFERENCE_LOCK_MESSAGE,
    render_equipment_scenario_row,
    render_legacy_trace_warning,
    unscheduled_notice,
)
from capa_simulation.components.equipment_settings_dialog import (
    open_equipment_settings,
    render_equipment_dialog_host,
    render_equipment_settings_button,
)
from capa_simulation.components.literal_markdown import markdown_safe_tildes
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY, render_sample_switch
from capa_simulation.components.tab_marks import mark_pending_tabs
from capa_simulation.components.tab_state import NestedTab, stateful_tabs, tab_is_hidden
from capa_simulation.equipment_scenario_activation import (
    official_snapshot_for,
    resolve_equipment_session,
    space_edit_mode,
)
from capa_simulation.navigation import (
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_SUMMARY_TAB_KEY,
    EQUIPMENT_SUMMARY_TABS,
    EQUIPMENT_TAB_KEY,
    EQUIPMENT_TABS,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
    no_demand_message,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_floor_layout_canvases,
    load_process_cutoff,
)
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.monthly_equipment_availability import processes_in, span_date_range
from capa_simulation.services.simulation_cache import (
    ScenarioCacheKey,
    check_scenario_capacity,
    equipment_span_cache_key,
    get_equipment_lifecycle_spans,
    scenario_cache_key,
    scenario_required_equipment,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

# 가정 설비 시나리오의 미확인 알림 꼬리표 — 미확인은 공식 시나리오 일정 기준이다(결정).
OFFICIAL_CONFIRMATION_BASIS = "공식 일정 기준"


def _months_between(start: date, end: date) -> list[int]:
    if start > end:
        return []
    months: list[int] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _open_master_import() -> None:
    """설비 입력으로 가는 콜백 — 탭 ① 「설비 마스터」 를 기억하고 「엑셀·CSV로 한꺼번에」 팝업을
    연다(첫 데이터도 그 팝업으로 넣고 「저장 전 변경」 에서 저장한다 — 한 길)."""
    st.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    open_equipment_import()


def _render_first_data_checklist(counts: tuple[int, int, int]) -> None:
    """저장된 것이 무엇인지 건수로 짚고 각각 갈 곳을 준다. **대수는 적지 않는다** — Main 의
    총대수는 데모 fleet 을 섞은 다른 산식이라, 두 수가 첫 화면에 나란히 서면 어느 쪽이
    맞는지부터 따져야 한다. Cut-off 는 저장본이 없는 이 자리에서만 한 번 더 읽는다.
    """
    steps = (
        ("설비 마스터", "설비 마스터 탭에서 붙여넣기", _open_master_import),
        ("운영 비가동 일정", "설비 마스터 탭에서 붙여넣기", _open_master_import),
        ("공정별 Cut-off", "설정에서 보기", open_equipment_settings),
    )
    keys = (
        "equipment_first_data_master_v1",
        "equipment_first_data_down_v1",
        "equipment_first_data_cut_v1",
    )
    for (title, action, callback), key, count in zip(steps, keys, counts, strict=True):
        with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
            st.markdown(f"{'✓' if count else '✗'} **{title}** {count:,}건")
            st.button(action, icon=":material/arrow_forward:", key=key, on_click=callback)


render_page_header("가용설비 현황", trailing=render_equipment_settings_button)
render_page_guide("available_equipment_status", title="가용설비 현황")
# 저장 알림·버림 알림은 **늘 서 있는 한 칸** 안에 그린다. 알림이 생기거나 사라질 때 아래 탭
# 묶음의 자리가 한 칸 밀리면, `st.rerun()` 으로 끊긴 저장 회차와 그다음 회차 사이에서 key 가
# 있는 탭 묶음이 옛 자리에 회색 사본으로 남아 다른 페이지까지 따라왔다(2026-10-05 E2E — 두
# 번째 설비 마스터 저장마다). 자리를 고정하면 탭 묶음은 늘 같은 자리다.
notices = st.container()
flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    notices.success(flash)

today = date.today()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    repository = get_equipment_repository(equipment_database_path)
    # 세션이 든 설비 시나리오(새 세션은 공식) — 공통 최신 + 고른 일정 리비전의 합친 스냅샷.
    equipment_session = resolve_equipment_session(equipment_database_path)
    latest_snapshot = equipment_session.snapshot
    # 가정 설비 시나리오면 미확인(Main·설비 마스터 일정 확인 목록)을 공식 일정으로 본다 — 공통은 늘
    # 최신이라 공식 스냅샷의 공통이 곧 지금 공통이다. 공식 시나리오 세션은 읽지 않는다.
    official_snapshot = (
        official_snapshot_for(equipment_database_path, equipment_session)
        if equipment_session.is_assumption
        else None
    )
    stored_floor_canvases = load_floor_layout_canvases(equipment_database_path)
except BOOTSTRAP_ERRORS as exc:
    st.error(
        "설비 현황을 준비하지 못했습니다. "
        + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
    )
    st.stop()
# 설비 DB 가 이 코드보다 새 버전이면(예전 배포로 되돌린 상태) 경고 한 줄. 막지 않는다.
with notices:
    render_schema_ahead_warning(repository.schema_ahead)
    # 옛 배포로 저장한 설비 리비전이 있으면 설비 저장이 막힌다 — 맨 위에 까닭과 빠져나갈 길.
    render_legacy_trace_warning(equipment_session)

# 저장본 사본과 미저장 편집본을 한 곳에서 세운다 — Space 현황이 먼저 세웠어도 같은 토큰이다.
ensure_equipment_drafts(latest_snapshot)
# 배치 편집 권한(Space 와 한 판정 — 찍힌 역할은 편집본을 세운 뒤에 읽는다).
layout_mode = space_edit_mode(equipment_session, stamped_role=live_layout_role())
drafts_replaced = pop_drafts_replaced()
discarded_notice = pop_discarded_notice()
if discarded_notice:
    notices.warning(discarded_notice, icon=":material/sync_problem:")
# Space 에서 넓혀 두고 아직 저장하지 않은 캔버스도 본다 — 칸 검증·미리보기 검증이 그 캔버스에
# 놓은 호기를 「밖」으로 막지 않게. 새 리비전이 생겨 대기분이 버려진 뒤에 읽는다.
floor_canvases = effective_floor_canvases(stored_floor_canvases)
# 사이드바 「설비 시나리오」 줄 — 이 회차 목록으로 그린다(칸이 없는 탭·회차는 그리지 않는다).
render_equipment_scenario_row(equipment_session)
# 저장본 사본 그대로(편집·설비 마스터·CSV 견주기 — 39칸 전체)와 계산에 넘길 사본(이 설비 시나리오에
# 일정이 없는 호기와 그 비가동을 뺀 것 — F4).
baseline = st.session_state[BASELINE_DRAFT_KEY].copy()
saved_equipment = st.session_state[EQUIPMENT_DRAFT_KEY].copy()
saved_downtime = st.session_state[DOWNTIME_DRAFT_KEY].copy()
_, equipment, downtime = calculation_drafts()
using_dashboard_sample = saved_equipment.empty
# 이 설비 시나리오에 일정이 없는 호기(함께 넣기를 끄고 넣은 호기) — 계산에 들지 않는다는 한 줄.
unscheduled_line = unscheduled_notice(len(draft_unscheduled_units()))
if unscheduled_line is not None:
    notices.info(unscheduled_line, icon=":material/event_busy:")
# 공정 표시명(Admin Area `Proc Rename`)은 **보이는 글자에만** 쓴다(2026-10-10 사용자 결정 — Main·
# Static 대비 일정·설정 팝업의 표 보기 필터). 선택값·저장값·CSV·설비 마스터 입력은 원본이다.
# 표시명은 시뮬레이션 DB 의 공용 프로필이라 그 DB 를 연다(앱에서는 부트스트랩이 이미 열어 둔
# 캐시다). 못 읽으면 원본 공정명 그대로 그린다(`get_process_labels` 가 삼킨다) — 설비 화면을 표시명
# 때문에 막지 않는다. 계산 캐시 결과의 복사본에만 입히므로 캐시 키에 넣지 않는다. Admin 에서 고치면
# 프로필 캐시가 비워져 다음 회차에 그대로 보인다.
process_labels = process_labels_module.get_process_labels()

first_action = st.empty()
sample_notice = st.empty()
# 탭 둘(2026-10-24 사용자 결정): ① 설비 마스터(처음 여는 탭) ② Summary(안쪽 Main·Static 대비 일정).
# 필요 단축 일정은 실행 관리 아래 별도 페이지(2026-10-18), Qual 마감 계산기는 그 화면 머리의 팝업,
# 설비 시나리오는 시나리오 관리 › 설비 시나리오다.
master_tab, summary_tab = stateful_tabs(EQUIPMENT_TABS, key=EQUIPMENT_TAB_KEY)
with summary_tab:
    # 안쪽 탭은 바깥이 숨어도 늘 부른다 — 위젯 값이 남아 사이드바(`app.active_condition_tab`)가
    # 읽는다.
    main_tab, gap_tab = stateful_tabs(EQUIPMENT_SUMMARY_TABS, key=EQUIPMENT_SUMMARY_TAB_KEY)
# 바깥 Summary 가 숨으면 안쪽 고른 탭의 `open` 도 거짓으로 본다(① 을 보는 회차에 Summary 계산을 하지
# 않는다). 본문 갈래와 두 부품의 `owner_tab` 은 이것을 본다.
main_view = NestedTab(summary_tab, main_tab)
gap_view = NestedTab(summary_tab, gap_tab)
# 저장하지 않은 설비 편집(편집본·Space FAB 배치 대기)이 있으면 ① 탭 이름 옆에 점(라벨 글자는 그대로
# — 탭 위젯 id). 화면 탭 줄의 점과 같은 판정이다. 찍을 것이 없어도 빈 규칙을 매 회차 그린다.
# 작은 편집표(기존 보유대수·비가동 일정)의 적용 전 편집도 같은 점이다 — 그 편집은 탭을 옮기면
# 사라진다
# (화면 탭 줄 떠나기 확인도 이것으로 묻는다 — `page_tabs.leave_notice`).
mark_pending_tabs(
    EQUIPMENT_TAB_KEY,
    EQUIPMENT_TABS,
    {EQUIPMENT_MASTER_TAB}
    if has_unsaved_equipment_edits() or pending_fab_layout() is not None or small_editor_edits()
    else set(),
)
# 조회 결과를 그리는 탭(설비 조건 카드·샘플 스위치가 서는 탭) — Summary 의 두 안쪽 탭.
viewing_tab_open = not tab_is_hidden(main_view) or not tab_is_hidden(gap_view)
if latest_snapshot is None and not tab_is_hidden(main_view):
    with first_action.container():
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**처음 사용하시나요?** 설비 마스터를 붙여넣어 첫 데이터를 저장하세요.")
            st.button(
                "설비 데이터 입력",
                icon=":material/add:",
                type="primary",
                on_click=_open_master_import,
            )
        cutoff = load_process_cutoff(equipment_database_path)
        # 이 안내는 저장본이 없을 때만 선다 — 저장된 호기·비가동은 0건이다.
        _render_first_data_checklist((0, 0, len(cutoff)))
show_sample_fleet = bool(st.session_state.get(SAMPLE_TOGGLE_KEY, True))
if using_dashboard_sample and viewing_tab_open:
    with sample_notice.container():
        show_sample_fleet = render_sample_switch(
            key="equipment_sample_switch", source="설비 운영 DB"
        )

# 합성값은 조회에만 사용한다. 첫 편집본에 샘플을 섞으면 실제 첫 저장을 막는다.
dashboard_equipment = (
    sample_equipment_master(anchor_date=today)
    if using_dashboard_sample and show_sample_fleet
    else equipment
)
dashboard_downtime = (
    sample_downtime_schedule(anchor_date=today)
    if using_dashboard_sample and show_sample_fleet
    else downtime
)
dashboard_baseline = (
    sample_equipment_baseline()
    if latest_snapshot is None and baseline.empty and using_dashboard_sample and show_sample_fleet
    else baseline
)
# 「설정」 팝업(공정별 Cut-off — Preference 탭이던 것). 이벤트 칸에 늘 한 자리를 쓴다. 「Cut-off 를
# 적지 않은 공정」 경고는 지금처럼 화면 호기의 공정으로 낸다. Cut-off 는 모든 설비 시나리오 공용이라
# 가정 설비 시나리오에서는 읽기 전용(E3)이고, 공식 시나리오의 발행 안 한 리비전에서는 열린다.
# 「엑셀·CSV로 한꺼번에」 팝업도 같은 열림 칸·같은 호스트다(한 실행에 팝업 하나). 새 방문 회차에는
# 미리보기를 거둔다(입력 칸은 비어 돌아온다).
withdraw_preview_on_new_visit()
render_equipment_dialog_host(
    repository,
    equipment_processes=processes_in(dashboard_equipment, dashboard_baseline),
    process_labels=process_labels,
    locked_reason=PREFERENCE_LOCK_MESSAGE if equipment_session.is_assumption else None,
    import_dialog=partial(
        render_import_dialog,
        ImportContext(
            floor_canvases=floor_canvases,
            basis=equipment_session.save_basis(),
            layout_mode=layout_mode.layout,
            layout_lock_reason=layout_mode.master_tab_lock_reason,
            official_places=(
                _official_places_by_name(latest_snapshot) if layout_mode.layout == "overlay" else {}
            ),
        ),
    ),
)

# 조회 조건은 사이드바 조건 카드 `설비 조회 조건` 이다(2026-09-29 사용자 결정). Summary 의 Main·
# Static 대비 일정이 **한 카드**를 쓰고 안의 내용만 열린 탭 것이다 — 한 번 편 카드는
# 탭을 옮겨도 편 채로 남는다(카드를 세우는 탭은 `navigation` 의 `card_labels` 선언과 같아야 한다).
# 설비 마스터의 표 보기 설정은 그 표의 입력 폼과 한 몸이라 본문에 둔다.
conditions_card = condition_card("설비 조회 조건", name="equipment") if viewing_tab_open else None
# 호기가 없고 샘플도 끈 Main 에는 고를 조건이 없다. 빈 카드 대신 까닭을 한 줄 적는다 — 카드를
# 아예 빼면 사이드바에서 이 화면의 조건 자리가 통째로 사라져 까닭을 알 수 없다.
if (
    conditions_card is not None
    and not tab_is_hidden(main_view)
    and using_dashboard_sample
    and not show_sample_fleet
):
    with conditions_card:
        st.caption("조회할 호기가 없습니다. 설비 마스터 탭에서 입력하거나 샘플 데이터를 켜세요.")

with main_tab:
    if not tab_is_hidden(main_view):
        if using_dashboard_sample and not show_sample_fleet:
            st.info(
                "등록된 호기가 없습니다. 설비 마스터 탭에서 설비 마스터를 입력하거나 "
                "샘플 데이터를 켜서 화면을 살펴보세요."
            )
        else:
            # 가정 설비 시나리오면 미확인은 공식 일정 기준(공식 스냅샷 그대로를 화면 호기로 좁힘).
            render_equipment_explorer(
                baseline=dashboard_baseline,
                equipment=dashboard_equipment,
                downtime=dashboard_downtime,
                today=today,
                owner_tab=main_view,
                conditions=conditions_card,
                process_labels=process_labels,
                confirmation_equipment=(
                    official_snapshot.equipment
                    if official_snapshot is not None and not using_dashboard_sample
                    else None
                ),
                confirmation_basis=(
                    OFFICIAL_CONFIRMATION_BASIS if official_snapshot is not None else None
                ),
            )

with gap_tab:
    if not tab_is_hidden(gap_view):
        assert conditions_card is not None
        with conditions_card:
            start_date, end_date = render_equipment_period(today=today, width="stretch")
        # 저장된 Cut-off 는 캐시 경계에서 직접 읽는다(필요 단축 일정과 같다 — 「설정」 팝업이
        # 저장하면 그 캐시를 비우고 앱 전체를 다시 돌린다). 저장되지 않은 팝업 표 편집으로 숫자를
        # 내지 않는다.
        stored_cutoff = load_process_cutoff(equipment_database_path)
        # **Static 은 시뮬레이션 DB 에 있다.** 이 페이지의 나머지 탭은 설비 DB 만 열고 활성
        # 시나리오가 없어도 열린다. 그래서 여기서만 예외를 잡아 이 탭 안에서 알리고, 다른
        # 탭을 막지 않는다 — 페이지가 통째로 죽으면 Cut-off 를 적으러 들어올 수도 없다.
        static_availability: pd.DataFrame | None = None
        # 비교 시트의 Static 보유·대여. 가용과 같은 저장 리비전에서, 계산 확인보다 **먼저** 읽는다 —
        # 계산이 멈춘 회차에도 이미 읽은 Static 세 표를 시트에 그대로 쓴다(아래 고정 동작과 같다).
        static_owned: pd.DataFrame | None = None
        static_lent: pd.DataFrame | None = None
        # 소요대수는 확보율 교차검증만 쓴다 — 프레임 대신 로더를 넘겨 그 보기의 캐시가 빗나갈 때만
        # 푼다. 로더와 시나리오 키는 계산이 서는 회차에만 선다(키는 교차검증 캐시 키에 실린다).
        gap_required_equipment: Callable[[], pd.DataFrame] | None = None
        gap_required_key: ScenarioCacheKey | None = None
        # 조회기간에 소요대수가 없을 때의 안내(데이터 범위). 그 갈래에서만 원천 범위를 재도록
        # 함수로 넘긴다.
        gap_no_demand_message: Callable[[], str] | None = None
        static_error: str | None = None
        try:
            gap_context = load_page_context()
            static_availability = gap_context.reference_tables["RQ_EQP_AVBL"]
            static_owned = gap_context.reference_tables["RQ_EQP_OWN"]
            static_lent = gap_context.reference_tables["RQ_EQP_LENT"]
            gap_scenario_key = scenario_cache_key(
                gap_context.reference_version,
                gap_context.active_scenario,
                gap_context.selected_start_month,
                gap_context.selected_end_month,
            )
            # 로더는 키를 낸 바로 그 표 묶음으로 만든다. 오류 확인과 교차검증이 이 로더 하나를
            # 나눠, 두 캐시가 함께 빗나가는 회차에도 소요대수를 한 번만 푼다.
            gap_demand = scenario_required_equipment(
                gap_scenario_key,
                scenario_tables=gap_context.active_scenario["tables"],
                reference_tables=gap_context.reference_tables,
            )
            # 계산이 서는지는 모든 보기에서 본다 — 기준정보 오류(조회기간 안이든 밖이든)를 어느
            # 보기에서나 같은 문구로 알린다. 적중이면 프레임을 풀지 않고, 실패는 캐시되지 않아
            # 고치거나 DB 가 돌아오면 다음 회차에 풀린다.
            check_scenario_capacity(
                gap_scenario_key,
                _scenario_tables=gap_context.active_scenario["tables"],
                _reference_tables=gap_context.reference_tables,
                _required_equipment=gap_demand,
            )
            gap_required_equipment = gap_demand
            gap_required_key = gap_scenario_key
            gap_no_demand_message = partial(no_demand_message, gap_context)
        except BOOTSTRAP_ERRORS as exc:
            # 계산이 멈춘 오류도 이 문구로 알린다. 그때도 이미 읽은 Static 은 비교에 그대로 쓴다 —
            # 「Static 을 읽지 못해」 문구와 맞지 않는 이 동작은 테스트가 고정한다
            # (`tests/test_equipment_scenario_demand.py`).
            static_error = bootstrap_error_message(
                exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
            )

        gap_months = _months_between(start_date, end_date)
        # Cut-off 가 크면 그 달의 W/D 구간이 앞으로 밀린다. 조회기간만큼만 구간을 만들면 첫 달이
        # 조용히 모자라게 세어지므로, 필요한 만큼 앞에서부터 다시 만든다.
        required_span = span_date_range(gap_months, stored_cutoff)
        span_start = min(start_date, required_span[0]) if required_span else start_date
        span_end = max(end_date, required_span[1]) if required_span else end_date
        try:
            # 지분이 바뀌는 날에도 구간을 끊는다. 대수 축이 모듈 행을 설비 한 대로 센다. 보기·위젯을
            # 바꾸는 rerun 마다 다시 만들지 않도록 마스터·비가동 내용 지문과 범위로 캐시한다 —
            # 필요 단축 일정 화면과 같은 캐시라 범위가 같으면 한 벌을 나눈다.
            gap_spans = get_equipment_lifecycle_spans(
                equipment_span_cache_key(
                    equipment=dashboard_equipment,
                    downtime=dashboard_downtime,
                    start_date=span_start,
                    end_date=span_end,
                ),
                _equipment=dashboard_equipment,
                _downtime=dashboard_downtime,
            )
        except ValueError as exc:
            st.error(markdown_safe_tildes(exc))
        else:
            # 비교 시트의 반사실 — 같은 마스터·같은 범위에서 비가동만 비운 구간. 같은 구간 캐시에
            # 빈 비가동으로 받는다(새 캐시 경계 없음). 시트를 그리는 회차에만 패널이 부른다.
            free_downtime = dashboard_downtime.iloc[0:0]

            def gap_counterfactual_spans() -> pd.DataFrame:
                return get_equipment_lifecycle_spans(
                    equipment_span_cache_key(
                        equipment=dashboard_equipment,
                        downtime=free_downtime,
                        start_date=span_start,
                        end_date=span_end,
                    ),
                    _equipment=dashboard_equipment,
                    _downtime=free_downtime,
                )

            # 호기별 환산비. 월 Total Capa 축(`환산대수`)만 이 값을 곱한다 — 대수를 세는
            # 축은 그대로다. 값이 없는 호기는 기준 모델과 같다고 보고 1.0 이다.
            gap_ratios = {
                str(unit).strip(): float(ratio)
                for unit, ratio in zip(
                    dashboard_equipment.get(EQUIPMENT_ID_COLUMN, []),
                    dashboard_equipment.get("환산비", []),
                    strict=False,
                )
                if pd.notna(ratio)
            }
            render_availability_gap_panel(
                spans=gap_spans,
                baseline=dashboard_baseline,
                cutoff=stored_cutoff,
                months=gap_months,
                static_availability=static_availability,
                static_owned=static_owned,
                static_lent=static_lent,
                static_error=static_error,
                span_bounds=(span_start, span_end),
                conversion_ratios=gap_ratios,
                required_equipment=gap_required_equipment,
                required_equipment_key=gap_required_key,
                no_demand_message=gap_no_demand_message,
                owner_tab=gap_view,
                conditions=conditions_card,
                # 분류별 내역의 `호기 필터` 가 이 표의 컬럼으로 호기를 좁힌다. 구간과 같은 표다.
                units=dashboard_equipment,
                process_labels=process_labels,
                downtime=dashboard_downtime,
                counterfactual_spans=gap_counterfactual_spans,
            )


with master_tab:
    # 열린 회차에만 그린다(개편 B1 — 표 편집은 세션 칸에 산다). 그 모듈은 표 컴포넌트를 등록하므로
    # 여기서만 불러온다. 작은 편집표 제출은 그 안에서 모든 위젯을 그린 뒤 `st.rerun()` 으로 끝난다.
    if not tab_is_hidden(master_tab):
        from capa_simulation.components.equipment_master_tab import render_equipment_master_tab

        render_equipment_master_tab(
            repository=repository,
            session=equipment_session,
            latest_snapshot=latest_snapshot,
            floor_canvases=floor_canvases,
            # 배치 일곱 칸은 Space 와 같은 판정이다(설계 8-4·10장) — 공식 시나리오면 공식 배치,
            # 가정이면 그 시나리오의 배치 차이, 잠긴 회차면 있던 호기 배치 칸이 잠긴다.
            layout_mode=layout_mode,
            today=today,
            confirmation_official=official_snapshot,
            drafts_replaced=drafts_replaced,
        )
    else:
        # 표 마운트가 사라진 회차 — 실어 보낸 토스트를 거둔다(돌아왔을 때 닫은 토스트가 되살아나지
        # 않게, `settle_grid_toasts`).
        settle_grid_toasts(())
