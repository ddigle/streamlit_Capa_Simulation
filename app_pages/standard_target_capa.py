from __future__ import annotations

from calendar import monthrange
from datetime import date

import streamlit as st

from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.persistence.equipment_cache import get_equipment_repository
from capa_simulation.scenario_preset_state import (
    STANDARD_TARGET_PROCESS_DEFAULT_KEY,
    STANDARD_TARGET_PROCESS_SELECTION_KEY,
)
from capa_simulation.scenario_state import (
    ensure_active_scenario,
    scenario_month_table,
    scenario_table,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.simulation_cache import (
    get_required_equipment,
    get_unit_capacity,
    get_weekly_standard_target_capacity,
)
from capa_simulation.services.standard_target_capacity import (
    build_weekly_availability_template,
    exclude_er_required_equipment,
    parse_weekly_availability_csv,
    weekly_standard_target_to_wide,
)
from capa_simulation.services.weighted_unit_capacity import WEIGHTED_CAPACITY_HIERARCHY
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

START_DATE_KEY = "standard_target_start_date"
END_DATE_KEY = "standard_target_end_date"
PROCESS_FILTER_KEY = STANDARD_TARGET_PROCESS_SELECTION_KEY
SHOW_DETAIL_KEY = "standard_target_show_detail"
DETAIL_LEVEL_KEY = "standard_target_detail_level"
OUTPUT_METRIC_KEY = "standard_target_output_metric"

DETAIL_LEVEL_LABELS = {
    "제품정보": "제품",
    "Stack": "제품 · Stack",
    "WF 구분": "제품 · Stack · WF 속성",
}
OUTPUT_METRICS = {
    "일 표준 가능량": 0,
    "대당 일 Capa": 2,
    "가용대수": 1,
}
DISPLAY_COLUMN_LABELS = {
    "양산구분": "양산",
    "제품정보": "제품",
    "WF 구분": "속성",
}


def _selected_month_range() -> tuple[int, int]:
    start_label, end_label = st.session_state["production_month_range_v2"]
    return int(start_label.replace("-", "")), int(end_label.replace("-", ""))


def _first_day(month: int) -> date:
    return date(month // 100, month % 100, 1)


def _last_day(month: int) -> date:
    year, month_number = divmod(month, 100)
    return date(year, month_number, monthrange(year, month_number)[1])


def _initialize_date_state(key: str, default: date, lower: date, upper: date) -> None:
    saved = st.session_state.get(key)
    if not isinstance(saved, date):
        st.session_state[key] = default
        return
    st.session_state[key] = min(max(saved, lower), upper)


st.title("표준 목표 Capa")
st.caption(
    "공정·제품 분류별 월간 부하 Mix를 반영한 공정 유효 Capa를 일 단위로 환산하고, "
    "주차별 가용설비를 곱해 투입 Unit 기준의 일 표준 가능량을 산출합니다."
)

try:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
    selected_start_month, selected_end_month = _selected_month_range()
    source_start_month, source_end_month = available_month_range(
        scenario_table(active_scenario, "RQ_UPEH"),
        "RQ_UPEH",
    )
    effective_start_month = max(selected_start_month, source_start_month)
    effective_end_month = min(selected_end_month, source_end_month)
    if effective_start_month > effective_end_month:
        raise ValueError("선택 범위에 표준 목표 Capa 기준정보가 없습니다.")
    equipment_repository = get_equipment_repository(str(EQUIPMENT_DUCKDB_PATH.resolve()))
    availability = equipment_repository.load_standard_target_availability()
except (KeyError, OSError, RuntimeError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

minimum_date = _first_day(effective_start_month)
maximum_date = _last_day(effective_end_month)
default_start_date = _first_day(effective_start_month)
default_end_date = _last_day(effective_end_month)
_initialize_date_state(START_DATE_KEY, default_start_date, minimum_date, maximum_date)
_initialize_date_state(END_DATE_KEY, default_end_date, minimum_date, maximum_date)
if st.session_state[START_DATE_KEY] > st.session_state[END_DATE_KEY]:
    st.session_state[END_DATE_KEY] = st.session_state[START_DATE_KEY]

with st.container(border=True):
    st.subheader("조회·집계 설정")
    date_row = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
    with date_row:
        start_date = st.date_input(
            "시작일",
            min_value=minimum_date,
            max_value=maximum_date,
            key=START_DATE_KEY,
            persist_state="session",
            width=180,
        )
        end_date = st.date_input(
            "종료일",
            min_value=minimum_date,
            max_value=maximum_date,
            key=END_DATE_KEY,
            persist_state="session",
            width=180,
        )
        show_detail = st.toggle(
            "상세",
            help="켜면 제품 분류별로 표시하고, 끄면 공정별 제품 Mix 가중 단일값을 표시합니다.",
            key=SHOW_DETAIL_KEY,
            persist_state="session",
            width=90,
        )
        if show_detail:
            detail_level = st.selectbox(
                "제품 분류 수준",
                options=list(DETAIL_LEVEL_LABELS),
                format_func=lambda value: DETAIL_LEVEL_LABELS[value],
                key=DETAIL_LEVEL_KEY,
                persist_state="session",
                width=230,
            )
        else:
            detail_level = "공정"
    if start_date > end_date:
        st.error("시작일은 종료일보다 늦을 수 없습니다.")
        st.stop()

start_month = start_date.year * 100 + start_date.month
end_month = end_date.year * 100 + end_date.month

try:
    filtered_tables = {
        name: scenario_month_table(active_scenario, name, start_month, end_month)
        for name in (
            "RQ_UPEH",
            "RQ_RUN_RATE",
            "RQ_VITAL",
            "RQ_RUN_DAY",
            "RQ_LOT_RATIO",
            "RQ_WF_RATIO",
            "RQ_PKG_PLAN",
            "RQ_YLD",
            "RQ_REQB",
        )
    }
    unit_capacity = get_unit_capacity(
        upeh=filtered_tables["RQ_UPEH"],
        run_rate=filtered_tables["RQ_RUN_RATE"],
        vital=filtered_tables["RQ_VITAL"],
        module=reference_tables["RQ_MODULE"],
        run_day=filtered_tables["RQ_RUN_DAY"],
        lot_ratio=filtered_tables["RQ_LOT_RATIO"],
        wf_ratio=filtered_tables["RQ_WF_RATIO"],
    )
    required_equipment = get_required_equipment(
        reqb=filtered_tables["RQ_REQB"],
        plan=filtered_tables["RQ_PKG_PLAN"],
        yield_data=filtered_tables["RQ_YLD"],
        chip_qty=reference_tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    required_equipment = exclude_er_required_equipment(required_equipment)
    full_reqb = scenario_table(active_scenario, "RQ_REQB")
    if "양산구분" not in full_reqb.columns:
        raise ValueError("RQ_REQB에 양산구분 컬럼이 없습니다.")
    production_reqb = full_reqb.loc[
        ~full_reqb["양산구분"].astype("string").str.strip().str.upper().eq("ER")
    ].reset_index(drop=True)
except (KeyError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

process_order = production_reqb[["공정"]].drop_duplicates()
process_order = apply_display_order(
    process_order,
    reference_tables["RQ_DISPLAY_ORDER"],
    "표준 목표 Capa",
    "목표 Capa",
)
process_options = process_order["공정"].astype(str).tolist()
public_default = st.session_state.get(STANDARD_TARGET_PROCESS_DEFAULT_KEY, [])
if not isinstance(public_default, list):
    public_default = []
public_default = [process for process in public_default if process in process_options]
st.session_state[STANDARD_TARGET_PROCESS_DEFAULT_KEY] = public_default

saved_processes = st.session_state.get(PROCESS_FILTER_KEY)
if not isinstance(saved_processes, list):
    saved_processes = public_default.copy()
st.session_state[PROCESS_FILTER_KEY] = [
    process for process in saved_processes if process in process_options
]


def _restore_public_process_default() -> None:
    st.session_state[PROCESS_FILTER_KEY] = public_default.copy()


with st.container(border=True):
    selected_processes = st.multiselect(
        "공정 필터",
        options=process_options,
        placeholder="미선택 시 전체 공정",
        key=PROCESS_FILTER_KEY,
        persist_state="session",
    )
    effective_public_default = set(public_default or process_options)
    effective_selection = set(selected_processes or process_options)
    has_temporary_override = effective_selection != effective_public_default
    filter_status = st.container(horizontal=True, vertical_alignment="center", gap="small")
    with filter_status:
        default_label = "전체 공정" if not public_default else f"{len(public_default):,}개 공정"
        st.caption(f"리비전 공용 기본값 · {default_label}", width="content")
        if has_temporary_override:
            st.markdown(":orange-badge[개인 임시 변경]")
            st.button(
                "공용 기본값으로 복원",
                icon=":material/restart_alt:",
                key="restore_standard_target_process_default",
                on_click=_restore_public_process_default,
                width="content",
            )
        else:
            st.markdown(":green-badge[공용 기본값 적용]")
    st.caption(
        "공정 필터 변경은 현재 사용자 세션에만 적용됩니다. 현재 선택값은 신규 리비전을 "
        "저장할 때 다음 공용 기본값으로 보존됩니다."
    )

target_processes = selected_processes or process_options
template = build_weekly_availability_template(target_processes, start_date, end_date)
template_csv = template.to_csv(index=False).encode("utf-8-sig")
weekly_output_container = st.container(border=True)

with st.container(border=True):
    st.subheader("주차별 가용설비 CSV")
    st.caption(
        "필수 입력은 `공정`, `Weeknum`, `가용대수`입니다. 템플릿의 가용대수를 입력한 뒤 "
        "업로드하세요. 적용한 최신본은 설비 DuckDB에 저장되며 별도 버전은 생성하지 않습니다."
    )
    action_row = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
    with action_row:
        st.download_button(
            ":material/download: CSV 양식 다운로드",
            data=template_csv,
            file_name=f"Weekly_Available_Equipment_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv",
            mime="text/csv;charset=utf-8",
            key="download_standard_target_availability_template",
            on_click="ignore",
            width="content",
        )
        if st.button(
            ":material/delete: 입력 초기화",
            key="clear_standard_target_availability",
            width="content",
        ):
            equipment_repository.clear_standard_target_availability()
            st.rerun()

    with st.form("standard_target_availability_import", border=False):
        uploaded_file = st.file_uploader(
            "가용설비 CSV 선택",
            type=["csv"],
            key="standard_target_availability_file",
        )
        import_submitted = st.form_submit_button(
            ":material/upload: CSV 적용",
            type="primary",
        )
    if import_submitted:
        if uploaded_file is None:
            st.error("적용할 가용설비 CSV 파일을 선택하세요.")
        else:
            try:
                availability = equipment_repository.save_standard_target_availability(
                    parse_weekly_availability_csv(uploaded_file.getvalue())
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("주차별 가용설비 최신본을 저장했습니다. 서버를 재시작해도 유지됩니다.")

if availability.empty:
    with weekly_output_container:
        st.subheader("주차별 일 표준 가능량")
        st.info("주차별 일 표준 가능량을 보려면 가용설비 CSV 최신본을 적용하세요.")
    st.stop()

filtered_required_equipment = required_equipment
if selected_processes:
    filtered_required_equipment = required_equipment.loc[
        required_equipment["공정"].isin(selected_processes)
    ].reset_index(drop=True)

try:
    weekly_target = get_weekly_standard_target_capacity(
        required_equipment=filtered_required_equipment,
        run_day=filtered_tables["RQ_RUN_DAY"],
        weekly_availability=availability,
        start_date=start_date,
        end_date=end_date,
        detail_level=detail_level,
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

missing_availability = (
    weekly_target.loc[weekly_target["가용대수"].isna(), ["공정", "Weeknum"]]
    .drop_duplicates()
    .reset_index(drop=True)
)
if not missing_availability.empty:
    st.warning(
        f"선택 범위의 공정·주차 중 {len(missing_availability):,}건에 가용대수가 없어 "
        "결과를 빈칸으로 표시합니다."
    )
    with st.expander("누락 공정·주차 확인", expanded=False):
        st.dataframe(missing_availability, hide_index=True, width="stretch")

classification_columns = [
    "공정",
    "소요기준",
    *WEIGHTED_CAPACITY_HIERARCHY[1 : WEIGHTED_CAPACITY_HIERARCHY.index(detail_level) + 1],
]
if st.session_state.get(OUTPUT_METRIC_KEY) == "일 최대 투입 가능량":
    st.session_state[OUTPUT_METRIC_KEY] = "일 표준 가능량"
with weekly_output_container:
    output_metric = st.segmented_control(
        "표시 항목",
        options=list(OUTPUT_METRICS),
        default="일 표준 가능량",
        key=OUTPUT_METRIC_KEY,
        persist_state="session",
    )
    if output_metric is None:
        output_metric = "일 표준 가능량"
    output_table = weekly_standard_target_to_wide(
        weekly_target,
        classification_columns,
        value_column=output_metric,
    )
    output_table = apply_display_order(
        output_table,
        reference_tables["RQ_DISPLAY_ORDER"],
        "표준 목표 Capa",
        "목표 Capa",
    )
    decimal_places = OUTPUT_METRICS[output_metric]
    output_export = build_hierarchical_monthly_export(
        output_table,
        classification_columns=classification_columns,
        column_labels=DISPLAY_COLUMN_LABELS,
        decimal_places=decimal_places,
    )
    output_csv = output_export.to_csv(index=False).encode("utf-8-sig")

    metric_row = st.container(horizontal=True, vertical_alignment="center", gap="small")
    with metric_row:
        st.subheader(f"주차별 {output_metric}", width="content")
        st.download_button(
            ":material/download: CSV 다운로드",
            data=output_csv,
            file_name=(
                f"Standard_Target_Capa_{output_metric}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv"
            ),
            mime="text/csv;charset=utf-8",
            key="download_standard_target_result",
            on_click="ignore",
            width="content",
        )
    st.caption(
        "대당 일 Capa = 월간 공정 유효 Capa ÷ RUN_DAY · "
        "일 표준 가능량 = 대당 일 Capa × 주차별 가용대수 · "
        "ER은 항상 제외하며 상세 OFF는 공정별 제품 Mix 가중 단일값을 표시합니다. · "
        "월 경계 주차는 월요일이 속한 달의 기준을 적용합니다."
    )
    render_hierarchical_monthly_table(
        output_table,
        classification_columns=classification_columns,
        column_labels=DISPLAY_COLUMN_LABELS,
        decimal_places=decimal_places,
        key="standard_target_weekly_table",
        page_size=80,
    )
