# Purpose: 설비 조회·월별 비교·필요단축일정·Cut-off·입력을 연결하고 저장본과 데모의 경계를 관리한다.

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.components.availability_gap_panel import render_availability_gap_panel
from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.components.equipment_data_workspace import (
    BASELINE_DRAFT_KEY,
    DOWNTIME_DRAFT_KEY,
    EQUIPMENT_DRAFT_KEY,
    FLASH_KEY,
    effective_floor_canvases,
    ensure_equipment_drafts,
    pop_discarded_notice,
    pop_drafts_replaced,
    render_equipment_data_workspace,
)
from capa_simulation.components.equipment_explorer import (
    render_equipment_explorer,
    render_equipment_period,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.required_shortening_panel import render_required_shortening_tab
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY, render_sample_switch
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.navigation import (
    EQUIPMENT_GAP_TAB,
    EQUIPMENT_MAIN_TAB,
    EQUIPMENT_SHORTENING_TAB,
    EQUIPMENT_TAB_KEY,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PageContext,
    bootstrap_error_message,
    load_page_context,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_floor_layout_canvases,
    load_latest_equipment_snapshot,
)
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.floor_layout_profile import max_canvas_extent
from capa_simulation.services.monthly_equipment_availability import processes_in, span_date_range
from capa_simulation.services.simulation_cache import (
    equipment_span_cache_key,
    get_equipment_lifecycle_spans,
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
# 저장 알림·버림 알림은 **늘 서 있는 한 칸** 안에 그린다. 알림이 생기거나 사라질 때 아래 탭
# 묶음의 자리가 한 칸 밀리면, `st.rerun()` 으로 끊긴 저장 회차와 그다음 회차 사이에서 key 가
# 있는 탭 묶음이 옛 자리에 회색 사본으로 남아 다른 페이지까지 따라왔다(2026-10-05 E2E — 두
# 번째 RawData 저장마다). 자리를 고정하면 탭 묶음은 늘 같은 자리다.
notices = st.container()
flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    notices.success(flash)

today = date.today()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    repository = get_equipment_repository(equipment_database_path)
    latest_snapshot = load_latest_equipment_snapshot(equipment_database_path)
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

# 저장본 사본과 미저장 편집본을 한 곳에서 세운다 — Space 현황이 먼저 세웠어도 같은 토큰이다.
ensure_equipment_drafts(latest_snapshot)
drafts_replaced = pop_drafts_replaced()
discarded_notice = pop_discarded_notice()
if discarded_notice:
    notices.warning(discarded_notice, icon=":material/sync_problem:")
# Space 에서 넓혀 두고 아직 저장하지 않은 캔버스도 본다 — 편집표 상한·미리보기 검증이 그
# 캔버스에 놓은 호기를 「밖」으로 막지 않게. 새 리비전이 생겨 대기분이 버려진 뒤에 읽는다.
floor_canvases = effective_floor_canvases(stored_floor_canvases)
max_extent = max_canvas_extent(floor_canvases)
baseline = st.session_state[BASELINE_DRAFT_KEY].copy()
equipment = st.session_state[EQUIPMENT_DRAFT_KEY].copy()
downtime = st.session_state[DOWNTIME_DRAFT_KEY].copy()
using_dashboard_sample = equipment.empty

first_action = st.empty()
sample_notice = st.empty()
main_tab, gap_tab, preference_tab, rawdata_tab, shortening_tab = stateful_tabs(
    [
        EQUIPMENT_MAIN_TAB,
        EQUIPMENT_GAP_TAB,
        TAB_PREFERENCE,
        TAB_RAWDATA,
        EQUIPMENT_SHORTENING_TAB,
    ],
    key=EQUIPMENT_TAB_KEY,
)
# 조회 결과를 그리는 탭(설비 조건 카드·샘플 스위치가 서는 탭). Preference·RawData 는 입력 폼이다.
viewing_tab_open = any(not tab_is_hidden(tab) for tab in (main_tab, gap_tab, shortening_tab))
if latest_snapshot is None and not tab_is_hidden(main_tab):
    with first_action.container():
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**처음 사용하시나요?** 호기 마스터를 붙여넣어 첫 데이터를 저장하세요.")
            st.button(
                "설비 데이터 입력", icon=":material/add:", type="primary", on_click=_open_input
            )
        cutoff = repository.load_process_cutoff()
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

# 조회 조건은 사이드바 조건 카드 `설비 조회 조건` 이다(2026-09-29 사용자 결정). Main·
# Static/Dynamic·필요단축일정이 **한 카드**를 쓰고 안의 내용만 열린 탭 것이다 — 한 번 편 카드는
# 탭을 옮겨도 편 채로 남는다(카드를 세우는 탭은 `navigation` 의 `card_labels` 선언과 같아야 한다).
# Preference(Cut-off)·RawData 의 표 보기 설정은 그 표의 입력 폼과 한 몸이라 본문에 둔다.
conditions_card = condition_card("설비 조회 조건", name="equipment") if viewing_tab_open else None
# 호기가 없고 샘플도 끈 Main·필요단축일정에는 고를 조건이 없다. 빈 카드 대신 까닭을 한 줄 적는다
# — 카드를 아예 빼면 사이드바에서 이 화면의 조건 자리가 통째로 사라져 까닭을 알 수 없다.
if (
    conditions_card is not None
    and (not tab_is_hidden(main_tab) or not tab_is_hidden(shortening_tab))
    and using_dashboard_sample
    and not show_sample_fleet
):
    with conditions_card:
        st.caption("조회할 호기가 없습니다. RawData 에서 입력하거나 샘플 데이터를 켜세요.")

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
    # 입력 폼을 계속 생성해 탭 왕복 중 미제출 편집을 보존한다. 돌려받는 **저장된** Cut-off 를
    # Static/Dynamic·필요단축일정이 그대로 쓴다 — 탭마다 다시 읽으면 rerun 마다 DB 를 세 번 열었다.
    # 저장은 그 자리에서 `st.rerun()` 하므로 이 회차에 낡은 값이 남지 않는다.
    stored_cutoff = render_cutoff_management(
        repository, equipment_processes=processes_in(dashboard_equipment, dashboard_baseline)
    )

with gap_tab:
    if not tab_is_hidden(gap_tab):
        assert conditions_card is not None
        with conditions_card:
            start_date, end_date = render_equipment_period(today=today, width="stretch")
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
            # 지분이 바뀌는 날에도 구간을 끊는다. 대수 축이 모듈 행을 설비 한 대로 센다. 보기·위젯을
            # 바꾸는 rerun 마다 다시 만들지 않도록 마스터·비가동 내용 지문과 범위로 캐시한다 —
            # 필요단축일정과 같은 캐시라 범위가 같으면 한 벌을 나눈다.
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
            st.error(str(exc))
        else:
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
                static_error=static_error,
                span_bounds=(span_start, span_end),
                conversion_ratios=gap_ratios,
                required_equipment=gap_required_equipment,
                owner_tab=gap_tab,
                conditions=conditions_card,
                # 분류별 내역의 `호기 필터` 가 이 표의 컬럼으로 호기를 좁힌다. 구간과 같은 표다.
                units=dashboard_equipment,
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
        drafts_replaced=drafts_replaced,
    )


with shortening_tab:
    if not tab_is_hidden(shortening_tab):
        if using_dashboard_sample and not show_sample_fleet:
            st.info(
                "등록된 호기가 없습니다. RawData에서 호기 마스터를 입력하거나 "
                "샘플 데이터를 켜서 화면을 살펴보세요."
            )
        else:
            # Static/Dynamic 과 같은 입력을 같은 길로 모은다. 소요대수는 활성 시나리오에 있으므로
            # **이 탭 안에서만** 예외를 잡아 알린다 — 다른 탭과 Cut-off 입력은 막지 않는다.
            # 호기 구간(`span_date_range` 로 넓힌 `build_equipment_lifecycle_spans`)과 환산비는
            # 고른 달이 정해진 뒤 `get_required_shortening` 이 같은 함수로 만든다.
            shortening_context: PageContext | None = None
            shortening_required: pd.DataFrame | None = None
            shortening_error: str | None = None
            try:
                shortening_context = load_page_context()
                _, shortening_required = get_scenario_capacity_and_demand(
                    scenario_cache_key(
                        shortening_context.reference_version,
                        shortening_context.active_scenario,
                        shortening_context.selected_start_month,
                        shortening_context.selected_end_month,
                    ),
                    _scenario_tables=shortening_context.active_scenario["tables"],
                    _reference_tables=shortening_context.reference_tables,
                )
            except BOOTSTRAP_ERRORS as exc:
                shortening_error = bootstrap_error_message(
                    exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
                )
            render_required_shortening_tab(
                equipment=dashboard_equipment,
                downtime=dashboard_downtime,
                baseline=dashboard_baseline,
                cutoff=stored_cutoff,
                today=today,
                context=shortening_context,
                required_equipment=shortening_required,
                scenario_error=shortening_error,
                owner_tab=shortening_tab,
                conditions=conditions_card,
                # 거르는 조건(기간·공정)은 이 DB 의 공용 프로필이다(0019).
                equipment_database_path=equipment_database_path,
            )
