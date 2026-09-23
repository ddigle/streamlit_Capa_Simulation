# Purpose: 생산계획·Wafer Capa·Bottleneck 요약과 상세표를 결합한 HOME 대시보드를 렌더링한다.


from dataclasses import replace
from typing import Any

import pandas as pd
import streamlit as st

from capa_simulation.components.decision_summary import render_home_capacity_decision
from capa_simulation.components.home_figures import (
    BOTTLENECK_DETAIL_RANK_LIMIT,
    build_bottleneck_detail_figures,
    build_key_process_heatmap_figures,
    build_lob_summary_figures,
    build_plan_detail_figures,
)
from capa_simulation.components.home_preference import (
    COMPARISON_REVISION_KEY,
    COMPARISON_SCENARIO_KEY,
    render_home_preference,
    render_lob_title_row,
    seed_comparison_selection,
)
from capa_simulation.components.home_rendering import (
    HOME_FIGURE_SCHEMA_VERSION,
    HOME_LOADING_STAGES,
    HOME_PERFORMANCE_KEY,
    HomeFigureCacheKey,
    HomeFigureSet,
    home_dashboard_panel,
    render_home_figures,
    render_home_performance,
    render_summary_notice,
    store_home_figures,
    take_home_figures,
)
from capa_simulation.components.loading_progress import LoadingProgress
from capa_simulation.components.page_header import render_page_header_with_status
from capa_simulation.components.past_data_management import render_past_data_management
from capa_simulation.components.plan_comparison_dumbbell import (
    render_plan_comparison_dumbbell,
)
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.tab_state import stateful_tabs
from capa_simulation.home_state import (
    ADVANCE_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    HOME_TOGGLE_DEFAULTS,
    PAST_DATA_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    selected_month_range,
)
from capa_simulation.performance import PerformanceTrace
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_global_advance_load,
    load_global_execution_capacity,
    load_global_key_process,
    load_global_past_data,
    load_global_summary_note,
    load_global_top5_band,
    load_scenario_plan,
)
from capa_simulation.scenario_activation import active_persisted_scenario_id
from capa_simulation.scenario_preset_state import (
    PROCESS_SELECTION_KEY,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
    seed_threshold_defaults,
)
from capa_simulation.scenario_state import (
    ensure_active_scenario,
)
from capa_simulation.services.advance_load import (
    apply_advance_to_density,
    apply_advance_to_securement,
    apply_advance_to_wafer,
    build_advance_load_ratio,
    revert_advance_from_securement,
    unapplicable_advance_months,
)
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    PRODUCTION_DETAIL_DIMENSIONS,
    add_detail_year_totals,
    align_detail_with_comparison,
    build_bottleneck_capacity,
    build_monthly_bottleneck_details_from_ranking,
    build_monthly_bottleneck_ranking,
    build_monthly_bottleneck_top5_from_ranking,
    build_monthly_bottlenecks_from_ranking,
    build_production_lob_summary,
    build_year_totals,
)
from capa_simulation.services.execution_capacity import (
    apply_execution_adjustment,
    clamped_execution_adjustments,
    empty_execution_capacity,
    unmatched_execution_adjustments,
)
from capa_simulation.services.home_decision import build_capacity_decision
from capa_simulation.services.month_columns import (
    build_month_axis,
    build_past_month_labels,
    leading_past_column_count,
    month_label,
)
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.past_data import (
    merge_past_frame,
    merge_past_months,
    merge_past_plan_detail,
    past_plan_detail_to_wide,
)
from capa_simulation.services.process_selection import resolve_included_processes
from capa_simulation.services.simulation_cache import (
    build_home_simulation_cache_key,
    get_home_comparison_plan,
    get_home_lob_without_edp,
    get_home_plan_detail,
    get_home_simulation,
)
from capa_simulation.settings import DUCKDB_PATH
from capa_simulation.sidebar_status import (
    BOTTLENECK_BOX_KEY,
    show_applied_month_range,
    show_month_range_unavailable,
    show_past_months_outside_range,
    sidebar_expander,
)


def _owned_comparison_revision(
    database_path: str,
    scenario_id: str,
    revision_id: str,
) -> str | None:
    """고른 리비전이 아직 그 시나리오 것인지 확인한다.

    세션에 남은 값은 그 사이 시나리오가 지워졌거나 리비전이 사라졌을 수 있다. 그대로
    불러오면 화면 전체가 오류로 멈춘다. 확인해서 아니면 조용히 비교를 끈다.
    """
    try:
        revisions = get_scenario_repository(database_path).list_revisions(scenario_id)
    except BOOTSTRAP_ERRORS:
        return None
    return revision_id if any(item.revision_id == revision_id for item in revisions) else None


# 진행 표시는 제목 줄 안에 둔다. 본문 흐름에 두면 막대가 뜨고 질 때마다 아래 차트가 그만큼
# 밀려 보던 자리가 흔들린다. 줄 높이는 제목이 잡으므로 막대가 사라져도 아래가 움직이지 않고,
# 어느 탭을 보고 있든 같은 자리에서 읽힌다.
loading = LoadingProgress(render_page_header_with_status("Capa LOB Summary"), HOME_LOADING_STAGES)
# 성능 진단은 **위젯이 아니라 세션 스위치**다. 사이드바에 토글을 두면 모든 사용자가 늘
# 보는 자리를 개발용 계측 하나가 차지한다. 단계별 소요 시간은 `scripts/benchmark_home.py`
# 로 재는 것이 정본이고, 화면에서 봐야 할 때만 이 키를 세션에 직접 넣는다.
show_home_performance = bool(st.session_state.get(HOME_PERFORMANCE_KEY, False))
home_trace = PerformanceTrace()
# 두 토글의 위젯은 아래 탭 안에서 그리지만 값은 계산보다 먼저 필요하다. 위젯이 `key` 로
# 쓰는 자리를 그대로 읽는다 — 사용자가 토글을 누르면 다음 실행의 이 줄에 새 값이 들어온다.
include_edp = bool(st.session_state.get(EDP_TOGGLE_KEY, HOME_TOGGLE_DEFAULTS[EDP_TOGGLE_KEY]))
# 기본은 **켬**이다. 끄면 과거 구간을 화면에서 빼고 활성 시나리오의 계산 결과만 남긴다.
# 토글도 `home_state` 의 같은 기본값을 읽어 첫 계산과 첫 위젯 표시를 맞춘다.
include_past = bool(
    st.session_state.get(PAST_DATA_TOGGLE_KEY, HOME_TOGGLE_DEFAULTS[PAST_DATA_TOGGLE_KEY])
)
show_advance = bool(
    st.session_state.get(ADVANCE_TOGGLE_KEY, HOME_TOGGLE_DEFAULTS[ADVANCE_TOGGLE_KEY])
)
show_execution = bool(
    st.session_state.get(EXECUTION_TOGGLE_KEY, HOME_TOGGLE_DEFAULTS[EXECUTION_TOGGLE_KEY])
)
plan_detail_customer = bool(
    st.session_state.get(PLAN_DETAIL_CUSTOMER_KEY, HOME_TOGGLE_DEFAULTS[PLAN_DETAIL_CUSTOMER_KEY])
)
# 비교 대상은 공용 프로필이라 새 브라우저 세션에도 남아 있다. 세션 키를 읽기 **전에**
# 심어야 첫 화면부터 「GAP」 토글이 켜진다 — 심는 자리가 Preference 피커 안에만 있으면
# 탭을 한 번 다녀와야 켜진다.
seed_comparison_selection(str(DUCKDB_PATH.resolve()))
comparison_scenario_id = st.session_state.get(COMPARISON_SCENARIO_KEY)
comparison_revision_id = st.session_state.get(COMPARISON_REVISION_KEY)
show_comparison = bool(
    st.session_state.get(COMPARISON_TOGGLE_KEY, HOME_TOGGLE_DEFAULTS[COMPARISON_TOGGLE_KEY])
) and bool(comparison_scenario_id and comparison_revision_id)
plan_detail_dimensions = (
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS if plan_detail_customer else PRODUCTION_DETAIL_DIMENSIONS
)
# 공정 표시명은 화면 라벨일 뿐이라 계산 입력이 아니다. `content_token` 을 다시
# 발급하지 않고 Figure 캐시 키에 버전 정수만 접어 넣는다.
process_labels = get_process_labels()

try:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
    selected_start, selected_end = selected_month_range()
    source_start, source_end = available_month_range(reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN")
    # 과거 구간은 계산 원천의 월 범위 밖에 있다. 원천 범위로만 자르면 넣어 둔 과거가 절대
    # 조회 범위에 들어오지 못한다. 볼 수 있는 범위를 과거 구간만큼 넓힌다.
    # **저장된 것**과 **화면에 그릴 것**을 갈라 둔다. 아래 토글은 대시보드에서 과거를 빼는
    # 표시 설정일 뿐 데이터를 지우는 뜻이 아닌데, 비운 프로필 하나만 들고 다니면 Past Data
    # 탭이 그것을 「저장된 값」으로 읽어 저장할 때 덮어쓴다.
    stored_past_profile = load_global_past_data(str(DUCKDB_PATH.resolve()))
    past_profile = stored_past_profile
    if not include_past:
        # 행만 비우고 **컬럼과 dtype 은 그대로 둔다.** 아래 병합·와이드 변환이 컬럼을 보고
        # 돌기 때문에 빈 프레임을 새로 만들면 그 자리에서 깨진다. 이렇게 두면 병합이 전부
        # 무동작이 되어, 과거를 빼는 분기를 화면 코드 곳곳에 심지 않아도 된다.
        #
        # `version` 도 0 이 되어 Figure 캐시 키가 갈린다 — 켠 화면과 끈 화면이 같은 칸을
        # 나눠 쓰지 않는다.
        past_profile = replace(
            stored_past_profile,
            version=0,
            monthly=past_profile.monthly.iloc[:0],
            plan_detail=past_profile.plan_detail.iloc[:0],
            securement=past_profile.securement.iloc[:0],
        )
    past_months = [int(value) for value in past_profile.monthly["생산계획년월"]]
    available_start = min([source_start, *past_months])
    available_end = max([source_end, *past_months])
    effective_start = max(selected_start, available_start)
    effective_end = min(selected_end, available_end)
    if effective_start > effective_end:
        show_month_range_unavailable()
        raise ValueError(
            "선택 범위에 생산계획 데이터가 없습니다 "
            f"(데이터 범위 {month_label(available_start)}–"
            f"{month_label(available_end)})"
        )
    # 고른 범위 밖의 과거 구간은 표에 들어오지 못한다. 넣어 둔 값이 사라진 것처럼 보이므로
    # 시작월을 어디까지 내려야 하는지 알린다. 적용 범위 표시와 같은 자리를 쓴다.
    hidden_past_months = [month for month in past_months if month < effective_start]
    if hidden_past_months:
        show_past_months_outside_range(min(hidden_past_months))
    else:
        show_applied_month_range(effective_start, effective_end)
    home_trace.mark("기준정보·시나리오")
    loading.advance()

    home_simulation_cache_key = build_home_simulation_cache_key(
        reference_version=reference_version,
        scenario_token=active_scenario["content_token"],
        start_month=effective_start,
        end_month=effective_end,
        display_order=reference_tables["RQ_DISPLAY_ORDER"],
    )
    home_trace.mark("캐시 키 생성")
    (
        monthly_density,
        production_detail,
        monthly_wafer,
        securement_rate,
    ) = get_home_simulation(
        cache_key=home_simulation_cache_key,
        _tables=active_scenario["tables"],
        _display_order=reference_tables["RQ_DISPLAY_ORDER"],
        _reference_tables=reference_tables,
    )
    if not include_edp:
        # LOB 로 표현되는 값만 EDP 를 뺀다. 확보율과 B/N 공정 순위는 설비가 받는 전체
        # 부하 기준이라 그대로 둔다.
        monthly_density, production_detail, monthly_wafer = get_home_lob_without_edp(
            cache_key=home_simulation_cache_key,
            _tables=active_scenario["tables"],
            _display_order=reference_tables["RQ_DISPLAY_ORDER"],
        )
    if plan_detail_customer:
        # 기본 조합의 세부수량은 위에서 이미 나왔다. 분류를 바꾼 사람만 다시 만든다.
        production_detail = get_home_plan_detail(
            cache_key=home_simulation_cache_key,
            _tables=active_scenario["tables"],
            _display_order=reference_tables["RQ_DISPLAY_ORDER"],
            include_edp=include_edp,
            include_customer=True,
        )
    comparison_density: pd.DataFrame | None = None
    comparison_wafer: pd.DataFrame | None = None
    comparison_detail: pd.DataFrame | None = None
    # **Figure 캐시 키가 보는 것은 이 값이다.** 고른 리비전이 아니라 실제로 붙은 리비전이다 —
    # 토글은 켜져 있어도 그 리비전이 지워졌거나 DB 를 잠깐 못 읽으면 비교 없이 그린다.
    # 요청한 값을 키에 적으면 그렇게 GAP 없이 그려진 그림이 「GAP 켜짐」 키로 저장되고,
    # 다음 실행에서 DB 가 멀쩡해져도 그 그림이 그대로 나와 GAP 이 조용히 사라진 채로 남는다.
    applied_comparison_revision_id: str | None = None
    if show_comparison:
        owned_revision_id = _owned_comparison_revision(
            str(DUCKDB_PATH.resolve()),
            str(comparison_scenario_id),
            str(comparison_revision_id),
        )
        if owned_revision_id is not None:
            # 비교는 계획 한 장만 쓴다. 16표 스냅샷을 풀면 적중하는 실행마다 그 값을
            # 다시 역직렬화한다.
            comparison_plan = load_scenario_plan(str(DUCKDB_PATH.resolve()), owned_revision_id)
            (
                comparison_density,
                comparison_wafer,
                comparison_detail,
            ) = get_home_comparison_plan(
                cache_key=home_simulation_cache_key,
                _tables=active_scenario["tables"],
                _comparison_plan=comparison_plan,
                _display_order=reference_tables["RQ_DISPLAY_ORDER"],
                comparison_revision_id=owned_revision_id,
                include_edp=include_edp,
                detail_dimensions=tuple(plan_detail_dimensions),
            )
            applied_comparison_revision_id = owned_revision_id
    # 과거 구간은 계산에 없는 달만 채운다. 계산 결과가 있는 달은 계산이 이긴다.
    calculated_months = {int(value) for value in monthly_density["생산계획년월"]}
    monthly_density = merge_past_months(
        monthly_density,
        past_profile.monthly,
        value_columns={"Density": "부하량"},
        start_month=effective_start,
        end_month=effective_end,
    )
    monthly_wafer = merge_past_months(
        monthly_wafer,
        past_profile.monthly,
        value_columns={"Wafer Total": "Wafer 부하량"},
        start_month=effective_start,
        end_month=effective_end,
    )
    securement_rate = merge_past_frame(
        securement_rate,
        past_profile.securement,
        start_month=effective_start,
        end_month=effective_end,
    )
    # 상세 B/N 이 요구하는 두 칸은 과거 입력에 없다. 컬럼 자체가 없으면 그 화면이 죽으므로
    # 결측으로 자리만 만든다 — 화면은 빈 칸으로 그린다.
    for equipment_column in ("가용대수", "소요대수"):
        if equipment_column not in securement_rate.columns:
            securement_rate[equipment_column] = pd.NA
    past_detail = past_plan_detail_to_wide(
        past_profile.plan_detail,
        plan_detail_dimensions,
        start_month=effective_start,
        end_month=effective_end,
        exclude_months=calculated_months,
    )
    production_detail = merge_past_plan_detail(
        production_detail,
        past_detail,
        plan_detail_dimensions,
        reference_tables["RQ_DISPLAY_ORDER"],
    )
    # 실행 Capa 반영은 **원데이터 기준**이다. 기준정보 밖에서 생긴 변수(비가동·UPEH·
    # 재공)를 원 확보율에 퍼센트포인트로 얹은 뒤, 선행은 그렇게 조정된 값 위에 변동률을
    # 곱한다. 조정이 없어도 부른다 — `기준 확보율`·`확보율 증감`·`실행 비고` 세 컬럼이
    # 항상 있어야 뒤의 순위·Figure 가 컬럼 유무로 갈라지지 않는다.
    execution_profile = load_global_execution_capacity(str(DUCKDB_PATH.resolve()))
    top5_band_profile = load_global_top5_band(str(DUCKDB_PATH.resolve()))
    key_process_profile = load_global_key_process(str(DUCKDB_PATH.resolve()))
    # 공지는 계산에 들어가지 않는 화면 문구다. 그래서 Figure 캐시 키에도 넣지 않는다 —
    # 넣으면 문구 한 줄을 고칠 때마다 여섯 Figure 를 다시 그린다.
    summary_profile = load_global_summary_note(str(DUCKDB_PATH.resolve()))
    execution_rows = execution_profile.rows if show_execution else empty_execution_capacity()
    unmatched_execution = unmatched_execution_adjustments(securement_rate, execution_rows)
    securement_rate = apply_execution_adjustment(securement_rate, execution_rows)
    clamped_execution = clamped_execution_adjustments(securement_rate)
    advance_profile = load_global_advance_load(str(DUCKDB_PATH.resolve()))
    baseline_density = monthly_density
    baseline_wafer = monthly_wafer
    advance_ratio: pd.DataFrame | None = None
    unapplied_advance_months: list[int] = []
    if show_advance:
        # 변동률은 **화면이 지금 쓰는 계획** 기준이다. EDP 를 뺀 화면이면 뺀 계획이
        # 기준이라야 어느 상태에서든 Capa 가 그대로이고 Density 증감이 입력값과 같다.
        advance_ratio = build_advance_load_ratio(monthly_density, advance_profile.rows)
        unapplied_advance_months = unapplicable_advance_months(advance_ratio)
        monthly_density = apply_advance_to_density(monthly_density, advance_ratio)
        monthly_wafer = apply_advance_to_wafer(monthly_wafer, advance_ratio)
        securement_rate = apply_advance_to_securement(securement_rate, advance_ratio)
    home_trace.mark("HOME 계산 파이프라인")
    loading.advance()
except BOOTSTRAP_ERRORS as exc:
    # 막대를 남긴 채 멈추면 오류 문구 위에 멈춰 선 진행률이 함께 보인다.
    loading.close()
    st.error(bootstrap_error_message(exc))
    st.stop()

process_options = sorted(
    securement_rate["공정"].astype("string").str.strip().dropna().unique().tolist()
)
# 히트맵이 **실제로 그릴** 목록. 고른 공정이 이 시나리오·조회기간에 없으면 건너뛰되
# 프로필에서 지우지는 않는다 — 공용 설정이라 다른 시나리오에는 그 공정이 있다.
# `resolve_included_processes` 를 쓰지 않는다. 그쪽의 「직전 옵션에 없던 공정은 새 공정
# 이니 포함」 규칙은 B/N 집계용이고, 주요공정은 명시적 선택이라 자동으로 들어오면 안 된다.
applied_key_processes = [
    process for process in key_process_profile.processes if process in set(process_options)
]
PROCESS_DIALOG_DRAFT_KEY = "dashboard_bottleneck_process_dialog_draft"
PROCESS_DIALOG_EDITOR_KEY = "dashboard_bottleneck_process_dialog_editor"
PROCESS_SEEN_KEY = "dashboard_bottleneck_process_seen"
if PROCESS_SELECTION_KEY not in st.session_state:
    # 예전 사이드바 토글 키(dashboard_bottleneck_process_{공정})를 읽던 이관 코드였다.
    # 그 토글은 70ad6d0 에서 지워져 항상 기본값 True — 곧 전체 목록이다.
    st.session_state[PROCESS_SELECTION_KEY] = list(process_options)
else:
    saved_processes = st.session_state[PROCESS_SELECTION_KEY]
    if isinstance(saved_processes, list):
        # 저장된 것은 **포함 목록**이라 "사용자가 끈 공정" 과 "처음 보는 공정" 이 구분되지
        # 않는다. 직전 실행의 옵션 집합을 함께 들고 있다가, 그때 없던 공정만 새 공정으로
        # 보아 포함한다. 시나리오를 바꾸거나 과거 구간을 넣어 공정이 늘었을 때 그것들이
        # 조용히 빠지면 B/N 이 틀린다.
        st.session_state[PROCESS_SELECTION_KEY] = resolve_included_processes(
            saved_processes,
            process_options,
            st.session_state.get(PROCESS_SEEN_KEY),
        )
st.session_state[PROCESS_SEEN_KEY] = list(process_options)


def set_process_dialog_selection(processes: list[str]) -> None:
    st.session_state[PROCESS_DIALOG_DRAFT_KEY] = list(processes)
    st.session_state.pop(PROCESS_DIALOG_EDITOR_KEY, None)


@st.dialog(
    "B/N 집계 공정 선택",
    width="large",
    icon=":material/filter_alt:",
    on_dismiss="rerun",
)
def show_process_filter_dialog(options: list[str]) -> None:
    draft_selection = st.session_state.get(PROCESS_DIALOG_DRAFT_KEY, [])
    if not isinstance(draft_selection, list):
        draft_selection = []
    selected_set = {str(process) for process in draft_selection if process in options}

    st.caption(
        "B/N 공정과 Capa 집계에 포함할 공정을 선택합니다. 표의 검색 기능으로 공정명을 "
        "찾을 수 있으며, 적용 전까지 기존 대시보드 조건은 유지됩니다."
    )
    with st.container(horizontal=True, gap="small"):
        st.button(
            "전체 ON",
            icon=":material/select_all:",
            on_click=set_process_dialog_selection,
            args=(options,),
            key="dashboard_bottleneck_process_all_on",
        )
        st.button(
            "전체 OFF",
            icon=":material/deselect:",
            on_click=set_process_dialog_selection,
            args=([],),
            key="dashboard_bottleneck_process_all_off",
        )
        st.button(
            "적용값 복원",
            icon=":material/undo:",
            on_click=set_process_dialog_selection,
            args=(list(st.session_state[PROCESS_SELECTION_KEY]),),
            key="dashboard_bottleneck_process_restore",
        )

    # 분류 컬럼은 월별 편집기와 같은 모양이다 — `SelectboxColumn` 이 옵션의 `value` 와
    # `label` 을 나눠 가져 셀에 보이는 글자만 표시명이 된다. 값은 반드시 원본 `공정` 이다.
    # 값을 표시명으로 바꾸면 아래 세션 되쓰기가 옵션에 없는 값을 만들어 대시보드가 오류
    # 없이 텅 빈다.
    selection_frame = pd.DataFrame(
        {
            "포함": [process in selected_set for process in options],
            "공정": list(options),
        }
    )
    column_config: dict[str, Any] = {
        "포함": st.column_config.CheckboxColumn(
            "포함",
            help="B/N 집계에 포함하려면 선택합니다.",
            width="small",
        ),
        "공정": st.column_config.TextColumn("공정", width="large"),
    }
    if process_labels:
        # 옵션에 없는 값은 셀이 빈칸으로 그려진다. 표의 값 전체를 옵션에 넣는다.
        column_config["공정"] = st.column_config.SelectboxColumn(
            "공정",
            options=list(options),
            format_func=process_labels.format_func(),
            width="large",
        )
    with st.form("dashboard_bottleneck_process_dialog_form", border=False):
        edited_selection = st.data_editor(
            selection_frame,
            key=PROCESS_DIALOG_EDITOR_KEY,
            hide_index=True,
            disabled=[column for column in selection_frame.columns if column != "포함"],
            num_rows="fixed",
            width="stretch",
            height=520,
            row_height=34,
            column_config=column_config,
        )
        apply_selection = st.form_submit_button(
            "선택 공정 적용",
            type="primary",
            icon=":material/check:",
            width="stretch",
        )
    if apply_selection:
        included_mask = edited_selection["포함"].fillna(False).astype(bool)
        st.session_state[PROCESS_SELECTION_KEY] = (
            edited_selection.loc[included_mask, "공정"].astype(str).tolist()
        )
        st.session_state.pop(PROCESS_DIALOG_DRAFT_KEY, None)
        st.rerun()


included_processes = list(st.session_state[PROCESS_SELECTION_KEY])
# 키와 기본값은 리비전 프리셋 소유다. Static Capa 본문의 같은 컨트롤과 세션 상태를
# 공유하므로 여기서 문자열을 다시 적으면 조용히 끊어진다.
seed_threshold_defaults()
# 이 상자만 **기본이 펼침**이다. B/N 기준은 HOME 에서만 쓰고 이 상자도 HOME 에만
# 있으니, 들어오자마자 보이는 것이 자연스럽다. 접으면 세션 동안 접힌 채로 남는다 —
# 다른 페이지에 갔다 오면 그 회차에 만들어지지 않은 위젯이라 값이 버려지므로
# `sidebar_expander` 가 위젯이 아닌 칸에 적어 둔 것을 되돌린다.
with sidebar_expander(
    "B/N 집계 공정",
    key=BOTTLENECK_BOX_KEY,
    icon=":material/filter_alt:",
    default=True,
):
    with st.form("dashboard_bottleneck_filter_form", border=False):
        # 칸 위 글자 세 줄(`판정 기준`·`확보 기준 (%)`·`경고 기준 (%)`)을 지우고 두 칸을
        # 한 줄에 반씩 놓는다. 사이드바에서 네 줄을 먹던 자리가 한 줄이 된다. 어느 칸이
        # 무엇인지는 왼쪽이 확보·오른쪽이 경고라는 **화면 전체의 차례**(범례·색 순서와
        # 같다)와 `help` 툴팁이 말한다. `collapsed` 는 글자만 감추고 접근성 이름은 남긴다.
        secure_column, warning_column = st.columns(2, gap="small")
        with secure_column:
            secure_threshold_percent = st.number_input(
                "확보 기준 (%)",
                label_visibility="collapsed",
                min_value=0.0,
                step=0.1,
                key=SECURE_THRESHOLD_KEY,
                persist_state="session",
                help=(
                    "확보 기준 (%) — 이 값을 넘으면 확보, 경고 기준과 이 값 사이는 "
                    "경고로 판정합니다."
                ),
            )
        with warning_column:
            warning_threshold_percent = st.number_input(
                "경고 기준 (%)",
                label_visibility="collapsed",
                min_value=0.0,
                step=0.1,
                key=WARNING_THRESHOLD_KEY,
                persist_state="session",
                help=(
                    "경고 기준 (%) — 이 값 미만은 부족, 이 값과 확보 기준 사이는 경고로 판정합니다."
                ),
            )
        st.form_submit_button("기준 적용", width="stretch", key="dashboard_threshold_apply")
    # 고른 수를 버튼 안에 넣어 캡션 한 줄을 없앤다. 버튼을 누를지 말지 정하는 데 필요한
    # 숫자라 버튼과 떨어져 있을 이유가 없다.
    if st.button(
        f"공정 선택 · {len(included_processes)} / {len(process_options)}",
        icon=":material/filter_list:",
        width="stretch",
        disabled=not process_options,
        key="dashboard_bottleneck_process_dialog_open",
    ):
        set_process_dialog_selection(included_processes)
        show_process_filter_dialog(process_options)
    if warning_threshold_percent > secure_threshold_percent:
        st.warning(
            f"경고 기준({warning_threshold_percent:g}%)이 확보 기준"
            f"({secure_threshold_percent:g}%)보다 큽니다. 경고 기준을 확보 기준 이하로 "
            "낮추고 「기준 적용」을 다시 누르세요."
        )
    if not process_options:
        st.caption("집계 가능한 공정이 없습니다.")

secure_threshold = secure_threshold_percent / 100.0
warning_threshold = warning_threshold_percent / 100.0
# 월 축에 완전한 해의 연간 Total 칸을 끼운다. 표·차트·가로 스크롤 폭이 모두 이 축 하나를
# 본다 — 축을 두 벌로 만들면 칸이 어긋난다.
month_labels, year_total_labels = build_month_axis(
    [int(value) for value in monthly_density["생산계획년월"]]
)
year_totals = build_year_totals(monthly_density, monthly_wafer, year_total_labels)
# GAP 은 DB 계산 구간에서만 뜻을 갖는다. 과거 구간은 시나리오와 분리된 공용 프로필
# (`app_meta.global_past_*`)에서 오므로 현재와 비교 시나리오가 같은 값을 받는다 — 그
# 구간의 차이는 언제나 0 이고, 비교 프레임에는 과거가 병합되지 않아 그대로 두면 과거
# 입력 전액이 거짓 증감으로 찍힌다. `calculated_months` 는 과거 병합 **직전**에 잡은
# 집합이라 그 경계가 그대로다.
gap_month_labels = {month_label(month) for month in calculated_months}
# 같은 경계가 면색도 정한다. 과거 구간 열은 한 단계 눌러 지난 이력임을 알린다 — 값은
# 그대로 읽히되 DB 계산 구간과 한눈에 갈린다.
past_month_labels = build_past_month_labels(month_labels, year_total_labels, gap_month_labels)
# 가로 스크롤의 시작 위치도 같은 경계를 본다. 앞머리의 과거 칸을 지나야 DB 계산 구간의
# 첫 달이 화면 왼쪽에 선다.
leading_past_months = leading_past_column_count(month_labels, past_month_labels)
figure_cache_key = HomeFigureCacheKey(
    schema_version=HOME_FIGURE_SCHEMA_VERSION,
    process_label_version=process_labels.version,
    reference_version=reference_version,
    content_token=active_scenario["content_token"],
    start_month=effective_start,
    end_month=effective_end,
    display_order_digest=home_simulation_cache_key[-1],
    included_processes=tuple(included_processes),
    secure_threshold_percent=float(secure_threshold_percent),
    warning_threshold_percent=float(warning_threshold_percent),
    include_edp=include_edp,
    plan_detail_customer=plan_detail_customer,
    # 비교는 이 한 값으로 충분하다. 「껐다」와 「켰지만 못 붙였다」는 그림이 똑같으므로
    # 같은 키를 나눠 쓰는 것이 맞다.
    comparison_revision_id=str(applied_comparison_revision_id or ""),
    show_advance=show_advance,
    advance_profile_version=advance_profile.version if show_advance else 0,
    show_execution=show_execution,
    execution_profile_version=execution_profile.version if show_execution else 0,
    top5_band_version=top5_band_profile.version,
    top5_min_rate=top5_band_profile.min_rate,
    top5_max_rate=top5_band_profile.max_rate,
    past_profile_version=past_profile.version,
    key_processes=tuple(applied_key_processes),
    key_process_profile_version=key_process_profile.version,
)
# 결론 요약은 **캐시 밖**에서 낸다. 아래 순위 집계는 캐시가 맞으면 건너뛰지만 이 집계는
# 같은 프레임 위의 마스크 한 번이라 건너뛸 값이 없다 — 대신 캐시 적중·미적중에서 늘 같은
# 값이 나온다.
capacity_decision = build_capacity_decision(
    securement_rate,
    included_processes=included_processes,
    secure_threshold=secure_threshold,
    warning_threshold=warning_threshold,
)
cached_figures = take_home_figures(figure_cache_key)
figure_cache_hit = cached_figures is not None
if cached_figures is None:
    bottleneck_ranking = build_monthly_bottleneck_ranking(
        securement_rate,
        included_processes=included_processes,
    )
    monthly_bottlenecks = build_monthly_bottlenecks_from_ranking(bottleneck_ranking)
    bottleneck_capacity = build_bottleneck_capacity(monthly_density, monthly_bottlenecks)
    monthly_top5 = build_monthly_bottleneck_top5_from_ranking(
        bottleneck_ranking,
        monthly_density,
        monthly_wafer=monthly_wafer,
    )
    monthly_bottleneck_details = build_monthly_bottleneck_details_from_ranking(
        bottleneck_ranking,
        monthly_wafer,
        rank_limit=BOTTLENECK_DETAIL_RANK_LIMIT,
    )
    lob_summary = build_production_lob_summary(
        monthly_density,
        monthly_wafer,
        monthly_bottlenecks,
    )
    baseline_lob_summary: pd.DataFrame | None = None
    if advance_ratio is not None:
        baseline_bottlenecks = revert_advance_from_securement(monthly_bottlenecks, advance_ratio)
        baseline_lob_summary = build_production_lob_summary(
            baseline_density,
            baseline_wafer,
            baseline_bottlenecks,
        )
    home_trace.mark("B/N 단일 순위·파생")
    loading.advance()
    label_figure, month_figure = build_lob_summary_figures(
        monthly_density=monthly_density,
        monthly_top5=monthly_top5,
        bottleneck_capacity=bottleneck_capacity,
        lob_summary=lob_summary,
        month_labels=month_labels,
        secure_threshold=secure_threshold,
        warning_threshold=warning_threshold,
        process_labels=process_labels,
        baseline_lob_summary=baseline_lob_summary,
        comparison_density=comparison_density,
        comparison_wafer=comparison_wafer,
        year_totals=year_totals,
        top5_rate_band=top5_band_profile.band,
        past_month_labels=past_month_labels,
    )
    displayed_detail = production_detail
    aligned_comparison_detail: pd.DataFrame | None = None
    if comparison_detail is not None:
        # 비교 시나리오에만 있는 분류 조합도 행으로 남긴다. 빠진 제품을 화면에서 보이게
        # 하는 것이 비교의 목적이다.
        displayed_detail, aligned_comparison_detail = align_detail_with_comparison(
            production_detail,
            comparison_detail,
            plan_detail_dimensions,
            reference_tables["RQ_DISPLAY_ORDER"],
        )
    detail_label_figure, detail_month_figure = build_plan_detail_figures(
        production_detail=add_detail_year_totals(
            displayed_detail, plan_detail_dimensions, year_total_labels
        ),
        month_labels=month_labels,
        detail_dimensions=plan_detail_dimensions,
        comparison_detail=aligned_comparison_detail,
        year_total_labels=year_total_labels,
        gap_month_labels=gap_month_labels,
        past_month_labels=past_month_labels,
    )
    (
        bottleneck_detail_label_figure,
        bottleneck_detail_month_figure,
    ) = build_bottleneck_detail_figures(
        monthly_bottleneck_details=monthly_bottleneck_details,
        month_labels=month_labels,
        secure_threshold=secure_threshold,
        warning_threshold=warning_threshold,
        process_labels=process_labels,
        year_total_labels=year_total_labels,
        past_month_labels=past_month_labels,
    )
    (
        key_process_label_figure,
        key_process_month_figure,
    ) = build_key_process_heatmap_figures(
        securement_rate=securement_rate,
        key_processes=applied_key_processes,
        month_labels=month_labels,
        secure_threshold=secure_threshold,
        warning_threshold=warning_threshold,
        process_labels=process_labels,
        year_total_labels=year_total_labels,
        past_month_labels=past_month_labels,
    )
    # 순서가 곧 화면 순서다. 주요공정 히트맵은 계획 세부수량과 상세 B/N 사이 구획이다.
    cached_figures = HomeFigureSet(
        lob_labels=label_figure,
        lob_months=month_figure,
        plan_detail_labels=detail_label_figure,
        plan_detail_months=detail_month_figure,
        key_process_labels=key_process_label_figure,
        key_process_months=key_process_month_figure,
        bottleneck_labels=bottleneck_detail_label_figure,
        bottleneck_months=bottleneck_detail_month_figure,
    )
    store_home_figures(figure_cache_key, cached_figures)
    home_trace.mark("Figure 생성")
else:
    home_trace.mark("Figure 캐시 조회")
    # 캐시가 맞으면 순위 집계와 차트 생성을 건너뛴다. 건너뛴 단계만큼 막대도 함께 넘겨야
    # 두 경로의 진행 단계 수가 같아지고 끝이 100% 로 맞는다.
    loading.advance()
loading.advance()

# 차트가 든 탭은 `stateful_tabs` 로 만든다. `key` 와 `on_change="rerun"` 이 있어야 서버가
# 어느 탭이 열렸는지 알고, 숨은 채로 그려 머리글이 밀리는 것을 막을 수 있다.
main_tab, preference_tab, past_tab = stateful_tabs(
    [
        ":material/dashboard: Main",
        ":material/tune: Preference",
        ":material/history: Past Data",
    ],
    key="home_active_tab",
)
with main_tab:
    # 공지는 대시보드 상자 **밖**, 화면 맨 위다. 상자 안에 두면 스크롤되는 월 영역과 폭을
    # 나눠 가져 문구가 월 칸 너비에 갇힌다.
    render_summary_notice(summary_profile.note)
    # 결론이 표보다 **먼저** 온다. 아래 Figure 와 같은 `securement_rate`·`included_processes`
    # 를 읽으므로 공정 필터를 바꾸면 요약도 같이 따라온다.
    render_home_capacity_decision(
        capacity_decision,
        secure_threshold=secure_threshold,
        warning_threshold=warning_threshold,
        # 화면 이름만 바꾼다. 저장 키는 원본 공정명 그대로다.
        process_label=(
            process_labels.label(capacity_decision.process) if capacity_decision.process else None
        ),
        filtered=len(included_processes) < len(process_options),
    )
    # 제목 줄과 여덟 Figure 는 한 상자 안이다. 제목 옆 토글은 숨은 탭에서도 그려야 하므로
    # Figure 를 건너뛰는 `render_home_figures` 안으로 넣지 않고 상자만 여기서 연다.
    with home_dashboard_panel():
        # 범례는 이 제목 줄 **안** 오른쪽 끝이다. 제목과 Figure 사이에 독립 블록으로
        # 두면 월 영역 위에 얹힌 가로 스크롤바와 겹친다.
        render_lob_title_row(
            unapplied_months=unapplied_advance_months,
            comparison_ready=bool(comparison_scenario_id and comparison_revision_id),
            secure_threshold=secure_threshold,
            warning_threshold=warning_threshold,
            has_past=bool(past_month_labels),
        )
        render_home_figures(
            cached_figures,
            month_labels,
            applied_plan_detail_customer=plan_detail_customer,
            leading_past_month_count=leading_past_months,
            owner_tab=main_tab,
        )
    if comparison_detail is not None:
        # 표의 칸마다 붙는 증감은 「이 달 이 분류가 얼마나 달랐나」를 답하지만 「무엇이 가장
        # 크게 달라졌나」는 답하지 못한다. 순서를 만드는 것이 덤벨의 몫이다.
        with st.expander("시나리오 비교 · 차이 큰 분류", expanded=False):
            render_plan_comparison_dumbbell(
                production_detail,
                comparison_detail,
                dimensions=plan_detail_dimensions,
                key="home_plan_comparison_dumbbell",
                owner_tab=main_tab,
            )
with past_tab:
    # 관리 탭은 **저장된** 프로필을 받는다. 표시용으로 비운 것을 주면 화면이
    # 「저장 0행」으로 보이고, 저장이 그 빈 값을 DB 에 되쓴다.
    render_past_data_management(str(DUCKDB_PATH.resolve()), stored_past_profile)
with preference_tab:
    # 선행 물량은 실제 달에만 넣는다. 화면 축에 끼운 연간 Total 칸은 입력할 자리가 아니다.
    advance_months = [int(value) for value in baseline_density["생산계획년월"]]
    render_home_preference(
        months=advance_months,
        month_labels=[month_label(value) for value in advance_months],
        advance_profile=advance_profile,
        execution_profile=execution_profile,
        top5_band_profile=top5_band_profile,
        key_process_profile=key_process_profile,
        summary_profile=summary_profile,
        # 실행 Capa 는 **원본 공정명** 기준이다. 표시명은 고르는 화면에서만 보인다.
        process_options=process_options,
        process_labels=process_labels,
        unmatched_execution=unmatched_execution,
        clamped_execution=clamped_execution,
        database_path=str(DUCKDB_PATH.resolve()),
        active_scenario_id=active_persisted_scenario_id(),
    )
home_trace.mark("Plotly 전달")
loading.close()
render_home_performance(
    home_trace,
    cache_hit=figure_cache_hit,
    enabled=show_home_performance,
)
