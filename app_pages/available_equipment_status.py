# Purpose: 설비 조회·월별 비교·Cut-off 설정·입력 작업을 연결하고 저장본과 데모의 경계를 관리한다.

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.components.availability_gap_panel import render_availability_gap_panel
from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.components.equipment_data_workspace import (
    BASELINE_DRAFT_KEY,
    BASELINE_IMPORT_KEY,
    DOWNTIME_DRAFT_KEY,
    DOWNTIME_IMPORT_KEY,
    DRAFT_REVISION_KEY,
    EQUIPMENT_DRAFT_KEY,
    EQUIPMENT_IMPORT_KEY,
    FLASH_KEY,
    render_equipment_data_workspace,
)
from capa_simulation.components.equipment_explorer import (
    render_equipment_explorer,
    render_equipment_period,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY, render_sample_switch
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.navigation import EQUIPMENT_GAP_TAB, EQUIPMENT_MAIN_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_floor_layout_canvases,
    load_latest_equipment_snapshot,
)
from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.floor_layout_profile import max_canvas_extent
from capa_simulation.services.monthly_equipment_availability import processes_in, span_date_range
from capa_simulation.services.simulation_cache import (
    get_scenario_capacity_and_demand,
    scenario_cache_key,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

TAB_PREFERENCE = ":material/tune: Preference"
TAB_RAWDATA = ":material/table_rows: RawData"


def _months_between(start: date, end: date) -> list[int]:
    if start > end:
        return []
    months: list[int] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _open_tab(label: str) -> None:
    st.session_state[EQUIPMENT_TAB_KEY] = label


def _open_input() -> None:
    _open_tab(TAB_RAWDATA)


def _render_first_data_checklist(counts: tuple[int, int, int]) -> None:
    """저장된 것이 무엇인지 건수로 짚고 각각 갈 곳을 준다. **대수는 적지 않는다** — Main 의
    총대수는 데모 fleet 을 섞은 다른 산식이라, 두 수가 첫 화면에 나란히 서면 어느 쪽이
    맞는지부터 따져야 한다. Cut-off 는 저장본이 없는 이 자리에서만 한 번 더 읽는다.
    """
    steps = (
        ("호기 마스터", "RawData 에서 붙여넣기", TAB_RAWDATA, "equipment_first_data_master_v1"),
        ("운영 비가동 일정", "RawData 에서 붙여넣기", TAB_RAWDATA, "equipment_first_data_down_v1"),
        ("공정별 Cut-off", "Preference 에서 보기", TAB_PREFERENCE, "equipment_first_data_cut_v1"),
    )
    for (title, action, label, key), count in zip(steps, counts, strict=True):
        with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
            st.markdown(f"{'✓' if count else '✗'} **{title}** {count:,}건")
            st.button(
                action, icon=":material/arrow_forward:", key=key, on_click=_open_tab, args=(label,)
            )


render_page_header("가용설비 현황 (Data확보중)")
render_page_guide("available_equipment_status", title="가용설비 현황")
flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    st.success(flash)

today = date.today()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    repository = get_equipment_repository(equipment_database_path)
    floor_canvases = load_floor_layout_canvases(equipment_database_path)
    max_extent = max_canvas_extent(floor_canvases)
    latest_snapshot = load_latest_equipment_snapshot(equipment_database_path)
    if latest_snapshot is None:
        saved_baseline = empty_equipment_baseline()
        saved_equipment = empty_equipment_master()
        saved_downtime = empty_downtime_schedule()
        revision_token = "empty"
    else:
        saved_baseline = latest_snapshot.baseline
        saved_equipment = latest_snapshot.equipment
        saved_downtime = latest_snapshot.downtime
        revision_token = latest_snapshot.revision.revision_id
except BOOTSTRAP_ERRORS as exc:
    st.error(
        "설비 현황을 준비하지 못했습니다. "
        + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
    )
    st.stop()

if st.session_state.get(DRAFT_REVISION_KEY) != revision_token:
    st.session_state[BASELINE_DRAFT_KEY] = saved_baseline.copy()
    st.session_state[EQUIPMENT_DRAFT_KEY] = saved_equipment.copy()
    st.session_state[DOWNTIME_DRAFT_KEY] = saved_downtime.copy()
    st.session_state[DRAFT_REVISION_KEY] = revision_token
    for preview_key in (BASELINE_IMPORT_KEY, EQUIPMENT_IMPORT_KEY, DOWNTIME_IMPORT_KEY):
        st.session_state.pop(preview_key, None)
baseline = st.session_state[BASELINE_DRAFT_KEY].copy()
equipment = st.session_state[EQUIPMENT_DRAFT_KEY].copy()
downtime = st.session_state[DOWNTIME_DRAFT_KEY].copy()
using_dashboard_sample = equipment.empty

first_action = st.empty()
sample_notice = st.empty()
main_tab, gap_tab, preference_tab, rawdata_tab = stateful_tabs(
    [
        EQUIPMENT_MAIN_TAB,
        EQUIPMENT_GAP_TAB,
        TAB_PREFERENCE,
        TAB_RAWDATA,
    ],
    key=EQUIPMENT_TAB_KEY,
)
if latest_snapshot is None and not tab_is_hidden(main_tab):
    with first_action.container():
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**처음 사용하시나요?** 호기 마스터를 붙여넣어 첫 데이터를 저장하세요.")
            st.button(
                "설비 데이터 입력", icon=":material/add:", type="primary", on_click=_open_input
            )
        cutoff = repository.load_process_cutoff()
        _render_first_data_checklist((len(saved_equipment), len(saved_downtime), len(cutoff)))
show_sample_fleet = bool(st.session_state.get(SAMPLE_TOGGLE_KEY, True))
if using_dashboard_sample and (not tab_is_hidden(main_tab) or not tab_is_hidden(gap_tab)):
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

# 조회 조건은 사이드바 조건 카드 `설비 조회 조건` 이다(2026-09-29 사용자 결정). Main·
# Static/Dynamic 두 탭이 **한 카드**를 쓰고 안의 내용만 열린 탭 것이다 — 한 번 편 카드는 탭을
# 옮겨도 편 채로 남는다(카드를 세우는 탭은 `navigation` 의 `card_labels` 선언과 같아야 한다).
# Preference(Cut-off)·RawData 의 표 보기 설정은 그 표의 입력 폼과 한 몸이라 본문에 둔다.
conditions_card = (
    condition_card("설비 조회 조건", name="equipment")
    if not tab_is_hidden(main_tab) or not tab_is_hidden(gap_tab)
    else None
)

with main_tab:
    if not tab_is_hidden(main_tab):
        if using_dashboard_sample and not show_sample_fleet:
            st.info(
                "등록된 호기가 없습니다. RawData에서 호기 마스터를 입력하거나 "
                "샘플 데이터를 켜서 화면을 살펴보세요."
            )
        else:
            render_equipment_explorer(
                baseline=dashboard_baseline,
                equipment=dashboard_equipment,
                downtime=dashboard_downtime,
                today=today,
                owner_tab=main_tab,
                conditions=conditions_card,
            )

with preference_tab:
    # 입력 폼을 계속 생성해 탭 왕복 중 미제출 편집을 보존한다.
    render_cutoff_management(
        repository, equipment_processes=processes_in(dashboard_equipment, dashboard_baseline)
    )

with gap_tab:
    if not tab_is_hidden(gap_tab):
        assert conditions_card is not None
        with conditions_card:
            start_date, end_date = render_equipment_period(today=today, width="stretch")
        stored_cutoff = repository.load_process_cutoff()
        # **Static 은 시뮬레이션 DB 에 있다.** 이 페이지의 나머지 탭은 설비 DB 만 열고 활성
        # 시나리오가 없어도 열린다. 그래서 여기서만 예외를 잡아 이 탭 안에서 알리고, 다른
        # 탭을 막지 않는다 — 페이지가 통째로 죽으면 Cut-off 를 적으러 들어올 수도 없다.
        static_availability: pd.DataFrame | None = None
        gap_required_equipment: pd.DataFrame | None = None
        static_error: str | None = None
        try:
            gap_context = load_page_context()
            static_availability = gap_context.reference_tables["RQ_EQP_AVBL"]
            # 소요대수는 확보율을 맞대려고 받는다. 다섯 페이지가 같은 키로 한 번만 계산하므로
            # 여기서 다시 계산되지 않는다.
            _, gap_required_equipment = get_scenario_capacity_and_demand(
                scenario_cache_key(
                    gap_context.reference_version,
                    gap_context.active_scenario,
                    gap_context.selected_start_month,
                    gap_context.selected_end_month,
                ),
                _scenario_tables=gap_context.active_scenario["tables"],
                _reference_tables=gap_context.reference_tables,
            )
        except BOOTSTRAP_ERRORS as exc:
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
            # 지분이 바뀌는 날에도 구간을 끊는다. 대수 축이 모듈 행을 설비 한 대로 센다.
            gap_spans = build_equipment_lifecycle_spans(
                dashboard_equipment,
                dashboard_downtime,
                start_date=span_start,
                end_date=span_end,
                with_unit_share=True,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            # 호기별 환산비. 월 Total Capa 축(`환산대수`)만 이 값을 곱한다 — 대수를 세는
            # 축은 그대로다. 값이 없는 호기는 기준 모델과 같다고 보고 1.0 이다.
            gap_ratios = {
                str(unit).strip(): float(ratio)
                for unit, ratio in zip(
                    dashboard_equipment.get("호기", []),
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
                static_error=static_error,
                span_bounds=(span_start, span_end),
                conversion_ratios=gap_ratios,
                required_equipment=gap_required_equipment,
                owner_tab=gap_tab,
                conditions=conditions_card,
            )


with rawdata_tab:
    # 입력 위젯은 숨은 탭에서도 유지한다. editor delta가 사라지면 안 된다.
    render_equipment_data_workspace(
        repository=repository,
        latest_snapshot=latest_snapshot,
        baseline=baseline,
        equipment=equipment,
        downtime=downtime,
        floor_canvases=floor_canvases,
        max_extent=max_extent,
    )
