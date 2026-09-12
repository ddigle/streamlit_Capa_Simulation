# Purpose: 생산계획·Wafer Capa·Bottleneck 요약과 상세표를 결합한 HOME 대시보드를 렌더링한다.


from typing import Any

import pandas as pd
import streamlit as st

from capa_simulation.components.home_figures import (
    BOTTLENECK_DETAIL_RANK_LIMIT,
    build_bottleneck_detail_figures,
    build_lob_summary_figures,
    build_plan_detail_figures,
)
from capa_simulation.components.home_preference import (
    ADVANCE_TOGGLE_KEY,
    COMPARISON_REVISION_KEY,
    COMPARISON_SCENARIO_KEY,
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
    render_home_preference,
    render_lob_title_row,
)
from capa_simulation.components.home_rendering import (
    HOME_FIGURE_SCHEMA_VERSION,
    HOME_LOADING_STAGES,
    HomeFigureCacheKey,
    render_home_figures,
    render_home_performance,
    store_home_figures,
    take_home_figures,
)
from capa_simulation.components.loading_progress import LoadingProgress
from capa_simulation.components.page_header import render_page_header_with_status
from capa_simulation.components.past_data_management import render_past_data_management
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.tab_state import stateful_tabs
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
    load_global_past_data,
    load_scenario_plan,
)
from capa_simulation.scenario_activation import active_persisted_scenario_id
from capa_simulation.scenario_preset_state import (
    DEFAULT_SECURE_THRESHOLD_PERCENT,
    DEFAULT_WARNING_THRESHOLD_PERCENT,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
)
from capa_simulation.scenario_state import (
    ensure_active_scenario,
)
from capa_simulation.services.advance_load import (
    apply_advance_to_density,
    apply_advance_to_securement,
    apply_advance_to_wafer,
    build_advance_load_ratio,
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
from capa_simulation.services.month_columns import build_month_axis, month_label
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.past_data import (
    merge_past_frame,
    merge_past_months,
    past_plan_detail_to_wide,
)
from capa_simulation.services.simulation_cache import (
    build_home_simulation_cache_key,
    get_home_comparison_plan,
    get_home_lob_without_edp,
    get_home_plan_detail,
    get_home_simulation,
)
from capa_simulation.settings import DUCKDB_PATH
from capa_simulation.sidebar_status import (
    show_applied_month_range,
    show_month_range_unavailable,
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
show_home_performance = st.sidebar.toggle(
    "HOME 성능 진단",
    value=False,
    key="dashboard_show_performance",
    persist_state="session",
)
home_trace = PerformanceTrace()
# 두 토글의 위젯은 아래 탭 안에서 그리지만 값은 계산보다 먼저 필요하다. 위젯이 `key` 로
# 쓰는 자리를 그대로 읽는다 — 사용자가 토글을 누르면 다음 실행의 이 줄에 새 값이 들어온다.
include_edp = bool(st.session_state.get(EDP_TOGGLE_KEY, False))
show_advance = bool(st.session_state.get(ADVANCE_TOGGLE_KEY, False))
plan_detail_customer = bool(st.session_state.get(PLAN_DETAIL_CUSTOMER_KEY, False))
comparison_scenario_id = st.session_state.get(COMPARISON_SCENARIO_KEY)
comparison_revision_id = st.session_state.get(COMPARISON_REVISION_KEY)
show_comparison = bool(st.session_state.get(COMPARISON_TOGGLE_KEY, False)) and bool(
    comparison_scenario_id and comparison_revision_id
)
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
    past_profile = load_global_past_data(str(DUCKDB_PATH.resolve()))
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
    if not past_detail.empty:
        production_detail = (
            pd.concat([production_detail, past_detail], ignore_index=True)
            .groupby(plan_detail_dimensions, as_index=False, dropna=False)
            .sum(numeric_only=True)
            .reset_index(drop=True)
        )
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
process_selection_key = "dashboard_bottleneck_process_selection"
process_dialog_draft_key = "dashboard_bottleneck_process_dialog_draft"
process_dialog_editor_key = "dashboard_bottleneck_process_dialog_editor"
process_seen_key = "dashboard_bottleneck_process_seen"
if process_selection_key not in st.session_state:
    # 예전 사이드바 토글 키(dashboard_bottleneck_process_{공정})를 읽던 이관 코드였다.
    # 그 토글은 70ad6d0 에서 지워져 항상 기본값 True — 곧 전체 목록이다.
    st.session_state[process_selection_key] = list(process_options)
else:
    saved_processes = st.session_state[process_selection_key]
    if isinstance(saved_processes, list):
        # 저장된 것은 **포함 목록**이라 "사용자가 끈 공정" 과 "처음 보는 공정" 이 구분되지
        # 않는다. 직전 실행의 옵션 집합을 함께 들고 있다가, 그때 없던 공정만 새 공정으로
        # 보아 포함한다. 시나리오를 바꾸거나 과거 구간을 넣어 공정이 늘었을 때 그것들이
        # 조용히 빠지면 B/N 이 틀린다.
        seen_processes = set(st.session_state.get(process_seen_key, []))
        kept = {process for process in saved_processes if process in process_options}
        st.session_state[process_selection_key] = [
            process
            for process in process_options
            if process in kept or process not in seen_processes
        ]
st.session_state[process_seen_key] = list(process_options)


def set_process_dialog_selection(processes: list[str]) -> None:
    st.session_state[process_dialog_draft_key] = list(processes)
    st.session_state.pop(process_dialog_editor_key, None)


@st.dialog(
    "B/N 집계 공정 선택",
    width="large",
    icon=":material/filter_alt:",
    on_dismiss="rerun",
)
def show_process_filter_dialog(options: list[str]) -> None:
    draft_selection = st.session_state.get(process_dialog_draft_key, [])
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
            args=(list(st.session_state[process_selection_key]),),
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
            key=process_dialog_editor_key,
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
        st.session_state[process_selection_key] = (
            edited_selection.loc[included_mask, "공정"].astype(str).tolist()
        )
        st.session_state.pop(process_dialog_draft_key, None)
        st.rerun()


included_processes = list(st.session_state[process_selection_key])
# 키와 기본값은 리비전 프리셋 소유다. Static Capa 본문의 같은 컨트롤과 세션 상태를
# 공유하므로 여기서 문자열을 다시 적으면 조용히 끊어진다.
secure_threshold_key = SECURE_THRESHOLD_KEY
warning_threshold_key = WARNING_THRESHOLD_KEY
if secure_threshold_key not in st.session_state:
    st.session_state[secure_threshold_key] = DEFAULT_SECURE_THRESHOLD_PERCENT
if warning_threshold_key not in st.session_state:
    st.session_state[warning_threshold_key] = DEFAULT_WARNING_THRESHOLD_PERCENT
with st.sidebar.container(border=True):
    st.markdown("#### :material/filter_alt: B/N 집계 공정")
    with st.form("dashboard_bottleneck_filter_form", border=False):
        st.markdown("**판정 기준**")
        secure_threshold_percent = st.number_input(
            "확보 기준 (%)",
            min_value=0.0,
            step=0.1,
            key=secure_threshold_key,
            persist_state="session",
        )
        warning_threshold_percent = st.number_input(
            "경고 기준 (%)",
            min_value=0.0,
            step=0.1,
            key=warning_threshold_key,
            persist_state="session",
        )
        st.form_submit_button("판정 기준 적용", width="stretch")
    st.caption(f"공정 선택 · {len(included_processes)} / {len(process_options)}개 포함")
    if st.button(
        "공정 선택창 열기",
        icon=":material/filter_list:",
        width="stretch",
        disabled=not process_options,
        key="dashboard_bottleneck_process_dialog_open",
    ):
        set_process_dialog_selection(included_processes)
        show_process_filter_dialog(process_options)
    if warning_threshold_percent > secure_threshold_percent:
        st.warning("경고 기준은 확보 기준보다 클 수 없습니다.")
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
figure_cache_key: HomeFigureCacheKey = (
    HOME_FIGURE_SCHEMA_VERSION,
    process_labels.version,
    reference_version,
    active_scenario["content_token"],
    effective_start,
    effective_end,
    home_simulation_cache_key[-1],
    tuple(included_processes),
    float(secure_threshold_percent),
    float(warning_threshold_percent),
    include_edp,
    plan_detail_customer,
    show_comparison,
    str(comparison_revision_id or ""),
    show_advance,
    advance_profile.version if show_advance else 0,
    past_profile.version,
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
    # 선행 전후를 한 그림에 함께 그리려면 기존값이 있어야 한다. 순위는 선행에 따라 바뀌지
    # 않으므로(월마다 같은 수를 곱한다) B/N 공정은 그대로 두고 확보율만 되돌린다.
    baseline_lob_summary: pd.DataFrame | None = None
    if advance_ratio is not None:
        baseline_bottlenecks = monthly_bottlenecks.copy()
        baseline_bottlenecks["확보율"] = monthly_bottlenecks["확보율"] / baseline_bottlenecks[
            "생산계획년월"
        ].map(advance_ratio.set_index("생산계획년월")["변동률"])
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
    )
    cached_figures = (
        label_figure,
        month_figure,
        detail_label_figure,
        detail_month_figure,
        bottleneck_detail_label_figure,
        bottleneck_detail_month_figure,
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
    render_lob_title_row(
        unapplied_months=unapplied_advance_months,
        comparison_ready=bool(comparison_scenario_id and comparison_revision_id),
    )
    render_home_figures(
        cached_figures,
        month_labels,
        applied_plan_detail_customer=plan_detail_customer,
        owner_tab=main_tab,
    )
with past_tab:
    render_past_data_management(str(DUCKDB_PATH.resolve()), past_profile)
with preference_tab:
    # 선행 물량은 실제 달에만 넣는다. 화면 축에 끼운 연간 Total 칸은 입력할 자리가 아니다.
    advance_months = [int(value) for value in baseline_density["생산계획년월"]]
    render_home_preference(
        months=advance_months,
        month_labels=[month_label(value) for value in advance_months],
        advance_profile=advance_profile,
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
