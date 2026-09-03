# Purpose: 공정 제품 Mix와 주차별 가용대수로 일 표준 가능량을 산출·분석·다운로드한다.

from __future__ import annotations

from calendar import monthrange
from datetime import date
from math import isfinite
from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    load_page_context,
    resolve_effective_months,
)
from capa_simulation.persistence.equipment_cache import get_equipment_repository
from capa_simulation.scenario_preset_state import (
    STANDARD_TARGET_PROCESS_DEFAULT_KEY,
    STANDARD_TARGET_PROCESS_SELECTION_KEY,
)
from capa_simulation.scenario_state import (
    scenario_month_table,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.frame_contracts import normalize_demand_basis
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.simulation_cache import (
    get_required_equipment,
    get_unit_capacity,
    get_weekly_standard_target_capacity,
)
from capa_simulation.services.standard_target_capacity import (
    PKG_EQUIVALENT_COLUMN,
    STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES,
    add_pkg_equivalent_standard_target,
    prepare_standard_target_required_equipment,
    standard_target_exception_row_count,
    weekly_standard_target_to_wide,
)
from capa_simulation.services.standard_target_logic import (
    build_standard_target_logic_analysis,
)
from capa_simulation.services.weekly_availability_input import (
    build_weekly_availability_template,
    parse_weekly_availability_clipboard,
)
from capa_simulation.services.weighted_unit_capacity import WEIGHTED_CAPACITY_HIERARCHY
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

START_DATE_KEY = "standard_target_start_date"
END_DATE_KEY = "standard_target_end_date"
PROCESS_FILTER_KEY = STANDARD_TARGET_PROCESS_SELECTION_KEY
SHOW_DETAIL_KEY = "standard_target_show_detail"
DETAIL_LEVEL_KEY = "standard_target_detail_level"
OUTPUT_METRIC_KEY = "standard_target_output_metric"
PKG_BASIS_KEY = "standard_target_pkg_basis"

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
OUTPUT_OPTIONS = [*OUTPUT_METRICS, "로직 분석"]
DISPLAY_COLUMN_LABELS = {
    "양산구분": "양산",
    "제품정보": "제품",
    "WF 구분": "속성",
}
LOGIC_FILTER_KEYS = {
    "Weeknum": "standard_target_logic_weeknum",
    "공정": "standard_target_logic_process",
    "소요기준": "standard_target_logic_basis",
    "양산구분": "standard_target_logic_production_type",
    "제품정보": "standard_target_logic_product",
    "Stack": "standard_target_logic_stack",
    "WF 구분": "standard_target_logic_wf_type",
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


def _ordered_text_options(values: pd.Series) -> list[str]:
    normalized = values.astype("string").str.strip().dropna()
    normalized = normalized.loc[normalized.ne("")]
    return normalized.drop_duplicates().astype(str).tolist()


def _required_selectbox(
    label: str,
    options: list[str],
    key: str,
    *,
    disabled: bool = False,
) -> str | None:
    saved = st.session_state.get(key)
    if saved not in options:
        st.session_state[key] = None
    selected = st.selectbox(
        label,
        options=options,
        index=None,
        placeholder=f"{label} 선택",
        key=key,
        disabled=disabled,
        width=190,
    )
    return selected


def _format_metric(value: object, decimal_places: int = 2) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or not isfinite(float(numeric)):
        return "-"
    return f"{float(numeric):,.{decimal_places}f}"


def _render_logic_analysis(
    required_equipment: pd.DataFrame,
    run_day: pd.DataFrame,
    availability: pd.DataFrame,
    start_date: date,
    end_date: date,
    process_order: list[str],
) -> None:
    st.subheader("일 표준 가능량 로직 분석")
    st.caption(
        "필터를 순서대로 모두 선택하면 공정·주차 한 건의 종합값과 이를 구성한 "
        "제품·Stack·WF 속성별 부하 Mix를 계산합니다. 다른 공정·주차의 분석값은 만들지 않습니다."
    )

    calendar = build_iso_week_calendar(start_date, end_date)
    source_months = pd.to_numeric(required_equipment["생산계획년월"], errors="coerce")
    available_months = set(source_months.dropna().astype("int64").tolist())
    week_options = (
        calendar.loc[calendar["생산계획년월"].isin(available_months), "Weeknum"]
        .astype(str)
        .tolist()
    )

    filter_row = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
    with filter_row:
        weeknum = _required_selectbox(
            "Weeknum",
            week_options,
            LOGIC_FILTER_KEYS["Weeknum"],
        )
        selected_month: int | None = None
        if weeknum is not None:
            selected_month = int(
                calendar.loc[calendar["Weeknum"].eq(weeknum), "생산계획년월"].iloc[0]
            )

        month_source = required_equipment.iloc[0:0].copy()
        if selected_month is not None:
            month_source = required_equipment.loc[source_months.eq(selected_month)].copy()
        source_processes = set(_ordered_text_options(month_source["공정"]))
        process_options = [process for process in process_order if process in source_processes]
        process = _required_selectbox(
            "공정",
            process_options,
            LOGIC_FILTER_KEYS["공정"],
            disabled=weeknum is None,
        )

        process_source = month_source.iloc[0:0].copy()
        if process is not None:
            process_source = month_source.loc[
                month_source["공정"].astype("string").str.strip().eq(process)
            ].copy()
        normalized_basis = normalize_demand_basis(process_source["소요기준"])
        basis_options = _ordered_text_options(normalized_basis)
        demand_basis = _required_selectbox(
            "소요기준",
            basis_options,
            LOGIC_FILTER_KEYS["소요기준"],
            disabled=process is None,
        )

        basis_source = process_source.iloc[0:0].copy()
        if demand_basis is not None:
            basis_source = process_source.loc[normalized_basis.eq(demand_basis)].copy()
        production_options = _ordered_text_options(basis_source["양산구분"])
        production_type = _required_selectbox(
            "양산",
            production_options,
            LOGIC_FILTER_KEYS["양산구분"],
            disabled=demand_basis is None,
        )

        production_source = basis_source.iloc[0:0].copy()
        if production_type is not None:
            production_source = basis_source.loc[
                basis_source["양산구분"].astype("string").str.strip().eq(production_type)
            ].copy()
        product_options = _ordered_text_options(production_source["제품정보"])
        product = _required_selectbox(
            "제품",
            product_options,
            LOGIC_FILTER_KEYS["제품정보"],
            disabled=production_type is None,
        )

        product_source = production_source.iloc[0:0].copy()
        if product is not None:
            product_source = production_source.loc[
                production_source["제품정보"].astype("string").str.strip().eq(product)
            ].copy()
        stack_options = _ordered_text_options(product_source["Stack"])
        stack = _required_selectbox(
            "Stack",
            stack_options,
            LOGIC_FILTER_KEYS["Stack"],
            disabled=product is None,
        )

        stack_source = product_source.iloc[0:0].copy()
        if stack is not None:
            stack_source = product_source.loc[
                product_source["Stack"].astype("string").str.strip().eq(stack)
            ].copy()
        wf_type_options = _ordered_text_options(stack_source["WF 구분"])
        wf_type = _required_selectbox(
            "WF 속성",
            wf_type_options,
            LOGIC_FILTER_KEYS["WF 구분"],
            disabled=stack is None,
        )

    selected_values = [
        weeknum,
        process,
        demand_basis,
        production_type,
        product,
        stack,
        wf_type,
    ]
    if any(value is None for value in selected_values):
        st.info("Weeknum부터 WF 속성까지 모든 필터를 선택하면 단일 결과의 산출 근거가 표시됩니다.")
        return

    selected_weeknum = cast(str, weeknum)
    selected_process = cast(str, process)
    selected_basis = cast(str, demand_basis)
    selected_production = cast(str, production_type)
    selected_product = cast(str, product)
    selected_stack = cast(str, stack)
    selected_wf_type = cast(str, wf_type)
    try:
        target, contributions = build_standard_target_logic_analysis(
            required_equipment=required_equipment,
            run_day=run_day,
            weekly_availability=availability,
            weeknum=selected_weeknum,
            process=selected_process,
            demand_basis=selected_basis,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    selected_mask = (
        contributions["양산구분"].astype("string").str.strip().eq(selected_production)
        & contributions["제품정보"].astype("string").str.strip().eq(selected_product)
        & contributions["Stack"].astype("string").str.strip().eq(selected_stack)
        & contributions["WF 구분"].astype("string").str.strip().eq(selected_wf_type)
    )
    selected_contribution = contributions.loc[selected_mask].reset_index(drop=True)
    if len(selected_contribution) != 1:
        st.error("선택한 제품·Stack·WF 속성의 Mix 기여 행을 하나로 확정할 수 없습니다.")
        return

    target_row = target.iloc[0]
    contribution_row = selected_contribution.iloc[0]
    unit_label = "매" if selected_basis == "WF" else "Kea"

    st.markdown("#### 선택 결과")
    metric_row = st.container(horizontal=True, vertical_alignment="center", gap="small")
    with metric_row:
        st.metric(
            f"원수요 부하량 ({unit_label})",
            _format_metric(target_row["원수요_부하량"]),
            width=180,
        )
        st.metric("STEP 소요대수", _format_metric(target_row["STEP_소요대수"]), width=170)
        st.metric("공정 유효 Capa", _format_metric(target_row["공정 유효 Capa"]), width=170)
        st.metric("RUN_DAY", _format_metric(target_row["RUN_DAY"], 1), width=130)
        st.metric("대당 일 Capa", _format_metric(target_row["대당 일 Capa"]), width=160)
        st.metric("가용대수", _format_metric(target_row["가용대수"], 1), width=130)
        st.metric(
            f"일 표준 가능량 ({unit_label})",
            _format_metric(target_row["일 표준 가능량"]),
            width=190,
        )

    st.code(
        "공정 유효 Capa = 원수요 부하량 합 ÷ STEP 소요대수 합\n"
        f"                 = {_format_metric(target_row['원수요_부하량'])} ÷ "
        f"{_format_metric(target_row['STEP_소요대수'])} = "
        f"{_format_metric(target_row['공정 유효 Capa'])}\n"
        "대당 일 Capa   = 공정 유효 Capa ÷ RUN_DAY\n"
        f"                 = {_format_metric(target_row['공정 유효 Capa'])} ÷ "
        f"{_format_metric(target_row['RUN_DAY'], 1)} = "
        f"{_format_metric(target_row['대당 일 Capa'])}\n"
        "일 표준 가능량 = 대당 일 Capa × 가용대수\n"
        f"                 = {_format_metric(target_row['대당 일 Capa'])} × "
        f"{_format_metric(target_row['가용대수'], 1)} = "
        f"{_format_metric(target_row['일 표준 가능량'])}",
        language=None,
    )

    selected_metric_row = st.container(
        horizontal=True,
        vertical_alignment="center",
        gap="small",
    )
    with selected_metric_row:
        st.metric(
            "선택 분류 부하량 비중",
            f"{float(contribution_row['부하량 비중']):.2%}",
            width=190,
        )
        st.metric(
            "선택 분류 소요대수 비중",
            f"{float(contribution_row['소요대수 비중']):.2%}",
            width=210,
        )
        st.metric(
            "선택 분류 유효 Capa",
            _format_metric(contribution_row["분류 유효 Capa"]),
            width=190,
        )

    st.markdown("#### 제품·WF 속성별 Mix 산출 근거")
    st.caption(
        "공정 유효 Capa는 분류별 Capa의 단순 평균이 아닙니다. 각 분류의 부하량 비중을 "
        "유효 Capa의 역수에 적용한 조화가중 결과이며, 이는 전체 부하량을 STEP 소요대수 "
        "합으로 나눈 값과 같습니다. 선택한 분류는 `●`로 표시합니다."
    )
    contribution_display = contributions.copy()
    contribution_display.insert(0, "선택", selected_mask.map({True: "●", False: ""}))
    contribution_display["부하량 비중"] *= 100
    contribution_display["소요대수 비중"] *= 100
    contribution_display = contribution_display.rename(
        columns={
            "양산구분": "양산",
            "제품정보": "제품",
            "WF 구분": "속성",
            "원수요_부하량": f"원수요 부하량 ({unit_label})",
            "부하량 비중": "부하량 비중 (%)",
            "STEP_소요대수": "STEP 소요대수",
            "소요대수 비중": "소요대수 비중 (%)",
        }
    )
    st.dataframe(
        contribution_display,
        column_order=[
            "선택",
            "양산",
            "제품",
            "Stack",
            "속성",
            f"원수요 부하량 ({unit_label})",
            "부하량 비중 (%)",
            "STEP 소요대수",
            "소요대수 비중 (%)",
            "분류 유효 Capa",
            "Capa 역수 기여",
        ],
        column_config={
            "선택": st.column_config.TextColumn(width="small"),
            f"원수요 부하량 ({unit_label})": st.column_config.NumberColumn(format="%.2f"),
            "부하량 비중 (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "STEP 소요대수": st.column_config.NumberColumn(format="%.4f"),
            "소요대수 비중 (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "분류 유효 Capa": st.column_config.NumberColumn(format="%.2f"),
            "Capa 역수 기여": st.column_config.NumberColumn(format="%.8f"),
        },
        hide_index=True,
        width="stretch",
        height=min(520, 38 + len(contribution_display) * 35),
    )


def _render_standard_target_exceptions(excluded_row_count: int) -> None:
    with st.expander("예외 처리 공정", expanded=False):
        st.caption(
            "아래 규칙은 표준 목표 Capa의 공정 유효 Capa와 로직 분석에만 적용됩니다. "
            "부하량·소요대수·확보율 원본 계산 결과는 변경하지 않습니다."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "공정": process,
                        "제외 대상": "WF 구분 = Dummy",
                        "적용 내용": (
                            "Dummy 부하량과 STEP 소요대수를 제품 Mix 가중 분자·분모에서 제외"
                        ),
                        "현재 조회범위 제외 행": excluded_row_count,
                    }
                    for process in STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES
                ]
            ),
            hide_index=True,
            width="stretch",
        )


st.title("표준 목표 Capa")
st.caption(
    "공정·제품 분류별 월간 부하 Mix를 반영한 공정 유효 Capa를 일 단위로 환산하고, "
    "주차별 가용설비를 곱해 투입 Unit 기준의 일 표준 가능량을 산출합니다."
)

try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    display_order = context.display_order
    active_scenario = context.active_scenario
    selected_start_month = context.selected_start_month
    selected_end_month = context.selected_end_month
    effective_start_month, effective_end_month = resolve_effective_months(
        context,
        active_scenario["tables"]["RQ_UPEH"],
        "RQ_UPEH",
        empty_message="선택 범위에 표준 목표 Capa 기준정보가 없습니다.",
    )
    equipment_repository = get_equipment_repository(str(EQUIPMENT_DUCKDB_PATH.resolve()))
    availability = equipment_repository.load_standard_target_availability()
except BOOTSTRAP_ERRORS as exc:
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
    standard_target_exception_rows = standard_target_exception_row_count(required_equipment)
    required_equipment = prepare_standard_target_required_equipment(required_equipment)
    full_reqb = active_scenario["tables"]["RQ_REQB"]
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
    display_order,
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
    st.subheader("주차별 가용설비 입력")
    st.caption(
        "CSV 양식을 내려받아 Excel에서 `공정`, `Weeknum`, `가용대수`를 수정하세요. "
        "헤더를 포함한 전체 표를 복사해 아래에 붙여넣으면 파일 업로드 없이 적용합니다. "
        "적용값은 설비 DuckDB에 저장되며 별도 버전은 생성하지 않습니다."
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

    with st.form("standard_target_availability_clipboard", border=False):
        clipboard_text = st.text_area(
            "가용설비 표 붙여넣기",
            key="standard_target_availability_clipboard_text",
            height=180,
            placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
        )
        import_submitted = st.form_submit_button(
            ":material/content_paste: 붙여넣기 적용",
            type="primary",
        )
    if import_submitted:
        if not clipboard_text.strip():
            st.error("적용할 가용설비 표를 Excel에서 복사해 붙여넣으세요.")
        else:
            try:
                availability = equipment_repository.save_standard_target_availability(
                    parse_weekly_availability_clipboard(clipboard_text)
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("주차별 가용설비 최신본을 저장했습니다. 서버를 재시작해도 유지됩니다.")

_render_standard_target_exceptions(standard_target_exception_rows)

if availability.empty:
    with weekly_output_container:
        st.subheader("주차별 일 표준 가능량")
        st.info("주차별 일 표준 가능량을 보려면 가용설비 입력값을 적용하세요.")
    st.stop()

filtered_required_equipment = required_equipment
if selected_processes:
    filtered_required_equipment = required_equipment.loc[
        required_equipment["공정"].isin(selected_processes)
    ].reset_index(drop=True)

if st.session_state.get(OUTPUT_METRIC_KEY) == "일 최대 투입 가능량":
    st.session_state[OUTPUT_METRIC_KEY] = "일 표준 가능량"
with weekly_output_container:
    output_metric = st.segmented_control(
        "표시 항목",
        options=OUTPUT_OPTIONS,
        default="일 표준 가능량",
        key=OUTPUT_METRIC_KEY,
        persist_state="session",
    )
    if output_metric is None:
        output_metric = "일 표준 가능량"

if output_metric == "로직 분석":
    with weekly_output_container:
        _render_logic_analysis(
            required_equipment=filtered_required_equipment,
            run_day=filtered_tables["RQ_RUN_DAY"],
            availability=availability,
            start_date=start_date,
            end_date=end_date,
            process_order=target_processes,
        )
else:
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
    pkg_basis = output_metric == "일 표준 가능량" and bool(
        st.session_state.get(PKG_BASIS_KEY, False)
    )
    output_value_column = output_metric
    output_title = output_metric
    decimal_places = OUTPUT_METRICS[output_metric]
    output_file_metric = output_metric
    if pkg_basis:
        try:
            weekly_target = add_pkg_equivalent_standard_target(
                weekly_target=weekly_target,
                required_equipment=filtered_required_equipment,
                plan=filtered_tables["RQ_PKG_PLAN"],
                detail_level=detail_level,
            )
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        output_value_column = PKG_EQUIVALENT_COLUMN
        output_title = "일 표준 가능량 (PKG Kea)"
        decimal_places = 2
        output_file_metric = "일_표준_가능량_PKG"

    with weekly_output_container:
        output_table = weekly_standard_target_to_wide(
            weekly_target,
            classification_columns,
            value_column=output_value_column,
        )
        output_table = apply_display_order(
            output_table,
            display_order,
            "표준 목표 Capa",
            "목표 Capa",
        )
        output_export = build_hierarchical_monthly_export(
            output_table,
            classification_columns=classification_columns,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=decimal_places,
        )
        output_csv = output_export.to_csv(index=False).encode("utf-8-sig")

        metric_row = st.container(horizontal=True, vertical_alignment="center", gap="small")
        with metric_row:
            st.subheader(f"주차별 {output_title}", width="content")
            st.download_button(
                ":material/download: CSV 다운로드",
                data=output_csv,
                file_name=(
                    f"Standard_Target_Capa_{output_file_metric}_"
                    f"{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv"
                ),
                mime="text/csv;charset=utf-8",
                key="download_standard_target_result",
                on_click="ignore",
                width="content",
            )
            if output_metric == "일 표준 가능량":
                st.toggle(
                    "PKG 기준",
                    key=PKG_BASIS_KEY,
                    help=(
                        "현재 공정·제품 Mix의 PKG PLAN 대비 투입 Unit 부하량 비율로 "
                        "일 표준 가능량을 PKG Kea로 역산합니다."
                    ),
                    persist_state="session",
                    width=110,
                )
        calculation_caption = (
            "대당 일 Capa = 월간 공정 유효 Capa ÷ RUN_DAY · "
            "일 표준 가능량 = 대당 일 Capa × 주차별 가용대수 · "
        )
        if pkg_basis:
            calculation_caption += (
                "PKG 환산 = 일 표준 가능량 × 동일 Mix PKG PLAN ÷ 원수요 부하량 · "
            )
        calculation_caption += (
            "ER은 항상 제외하며 상세 OFF는 공정별 제품 Mix 가중 단일값을 표시합니다. · "
            "월 경계 주차는 월요일이 속한 달의 기준을 적용합니다."
        )
        st.caption(calculation_caption)
        render_hierarchical_monthly_table(
            output_table,
            classification_columns=classification_columns,
            column_labels=DISPLAY_COLUMN_LABELS,
            decimal_places=decimal_places,
            key="standard_target_weekly_table",
            page_size=80,
        )
