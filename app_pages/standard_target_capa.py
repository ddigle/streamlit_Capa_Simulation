# Purpose: 공정 제품 Mix와 주차별 가용대수로 일 표준 가능량을 산출·분석·다운로드한다.

"""표준 목표 — 조건 카드·Guide·작업 줄 양식(2026-09-29 사용자 결정, 생산 계획이 샘플).

- 표시 항목·기간·공정 필터·상세·PKG 기준(로직 분석이면 고르는 일곱 칸)은 사이드바 조건 카드
  `표준 목표 조건` 이다. 카드는 계산이 멈추는 회차에도 먼저 선다.
- 주차별 가용설비 입력은 결과 상자 위 작업 줄이다 — 붙여넣기·입력 초기화는 팝업, 양식은 내려받기.
- 설명(산식·세션 적용 범위·예외 처리 규칙)은 Guide(`guides/standard_target_capa.md`)다.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable
from datetime import date
from math import isfinite
from typing import cast

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import (
    ProcessLabels,
    get_process_labels,
)
from capa_simulation.components.table_toolbar import (
    CSV_TEMPLATE_LABEL,
    render_csv_download,
    render_table_heading,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    load_page_context,
    prune_list_selection,
    resolve_effective_months,
    scenario_capacity_and_demand,
)
from capa_simulation.persistence.equipment_cache import get_equipment_repository
from capa_simulation.persistence.models import (
    DEFAULT_STANDARD_TARGET_DETAIL_LEVEL,
    DEFAULT_STANDARD_TARGET_OUTPUT_METRIC,
)
from capa_simulation.scenario_preset_state import (
    STANDARD_TARGET_DETAIL_LEVEL_KEY,
    STANDARD_TARGET_END_DATE_KEY,
    STANDARD_TARGET_OUTPUT_METRIC_KEY,
    STANDARD_TARGET_PROCESS_DEFAULT_KEY,
    STANDARD_TARGET_PROCESS_SELECTION_KEY,
    STANDARD_TARGET_SHOW_DETAIL_KEY,
    STANDARD_TARGET_START_DATE_KEY,
)
from capa_simulation.scenario_state import (
    scenario_month_table,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_scopes import (
    PAGE_STANDARD_TARGET,
    TAB_TARGET_CAPACITY,
)
from capa_simulation.services.frame_contracts import normalize_demand_basis
from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.simulation_cache import (
    get_pkg_equivalent_standard_target,
    get_weekly_standard_target_capacity,
    scenario_cache_key,
)
from capa_simulation.services.standard_target_capacity import (
    PKG_EQUIVALENT_COLUMN,
    STANDARD_TARGET_DUMMY_EXCLUDED_PROCESSES,
    exclude_er_required_equipment,
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
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

START_DATE_KEY = STANDARD_TARGET_START_DATE_KEY
END_DATE_KEY = STANDARD_TARGET_END_DATE_KEY
PROCESS_FILTER_KEY = STANDARD_TARGET_PROCESS_SELECTION_KEY
SHOW_DETAIL_KEY = STANDARD_TARGET_SHOW_DETAIL_KEY
DETAIL_LEVEL_KEY = STANDARD_TARGET_DETAIL_LEVEL_KEY
OUTPUT_METRIC_KEY = STANDARD_TARGET_OUTPUT_METRIC_KEY
PKG_BASIS_KEY = "standard_target_pkg_basis"
# 사이드바 조건 카드와 팝업. 팝업은 한 칸이라 한 회차에 하나다.
CARD_NAME = "standard_target"
DIALOG_KEY = f"standard_target{PAGE_DIALOG_SUFFIX}"
PASTE_DIALOG = "availability_paste"
CLEAR_DIALOG = "availability_clear"
AVAILABILITY_FLASH_KEY = "standard_target_availability_flash"

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
# 주차별 가용대수를 곱해 구하는 지표. 가용대수 입력이 없으면 이 둘만 빈칸이 된다.
AVAILABILITY_BASED_METRICS = frozenset({"일 표준 가능량", "가용대수"})
LOGIC_FILTER_KEYS = {
    "Weeknum": "standard_target_logic_weeknum",
    "공정": "standard_target_logic_process",
    "소요기준": "standard_target_logic_basis",
    "양산구분": "standard_target_logic_production_type",
    "제품정보": "standard_target_logic_product",
    "Stack": "standard_target_logic_stack",
    "WF 구분": "standard_target_logic_wf_type",
}


def _first_day(month: int) -> date:
    return date(month // 100, month % 100, 1)


def _last_day(month: int) -> date:
    year, month_number = divmod(month, 100)
    return date(year, month_number, monthrange(year, month_number)[1])


def _initialize_date_state(key: str, default: date, lower: date, upper: date) -> bool:
    """리비전이 저장한 조회일을 현재 조회기간 안으로 맞추고 조정 여부를 알린다.

    사이드바 조회기간을 좁힌 뒤 과거 리비전을 열면 저장된 날짜가 범위 밖이 된다.
    그대로 두면 `st.date_input` 이 예외를 던져 페이지가 열리지 않으므로 잘라 넣는다.
    """
    saved = st.session_state.get(key)
    if not isinstance(saved, date):
        st.session_state[key] = default
        return False
    clamped = min(max(saved, lower), upper)
    st.session_state[key] = clamped
    return clamped != saved


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
    format_func: Callable[[object], str] = str,
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
        # 표시만 바꾼다. 아래 필터가 원본 컬럼과 문자열로 대조하므로 값은 원본이어야 한다.
        format_func=format_func,
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
    process_labels: ProcessLabels,
    *,
    filters: DeltaGenerator,
) -> None:
    """한 공정·주차의 산출 근거. 고르는 칸(`filters`)은 사이드바 조건 카드 안이다."""
    st.subheader("일 표준 가능량 로직 분석")

    calendar = build_iso_week_calendar(start_date, end_date)
    source_months = pd.to_numeric(required_equipment["생산계획년월"], errors="coerce")
    available_months = set(source_months.dropna().astype("int64").tolist())
    week_options = (
        calendar.loc[calendar["생산계획년월"].isin(available_months), "Weeknum"]
        .astype(str)
        .tolist()
    )

    with filters:
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
            format_func=process_labels.format_func(),
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
    # 고정 px 7개를 한 줄에 두면 1,130px 를 넘겨 좁은 화면에서 잘린다.
    # st.columns 는 남는 폭을 나눠 갖고 화면이 줄면 함께 줄어든다.
    first_row = st.columns(4, vertical_alignment="center")
    with first_row[0]:
        st.metric(
            f"원수요 부하량 ({unit_label})",
            _format_metric(target_row["원수요_부하량"]),
            border=True,
        )
    with first_row[1]:
        st.metric("STEP 소요대수", _format_metric(target_row["STEP_소요대수"]), border=True)
    with first_row[2]:
        st.metric(
            "공정별 대당 Capa",
            _format_metric(target_row["공정 유효 Capa"]),
            border=True,
        )
    with first_row[3]:
        st.metric("RUN_DAY", _format_metric(target_row["RUN_DAY"], 1), border=True)
    second_row = st.columns(4, vertical_alignment="center")
    with second_row[0]:
        st.metric("대당 일 Capa", _format_metric(target_row["대당 일 Capa"]), border=True)
    with second_row[1]:
        st.metric("가용대수", _format_metric(target_row["가용대수"], 1), border=True)
    with second_row[2]:
        st.metric(
            f"일 표준 가능량 ({unit_label})",
            _format_metric(target_row["일 표준 가능량"]),
            border=True,
        )

    st.code(
        "공정별 대당 Capa = 원수요 부하량 합 ÷ STEP 소요대수 합\n"
        f"                 = {_format_metric(target_row['원수요_부하량'])} ÷ "
        f"{_format_metric(target_row['STEP_소요대수'])} = "
        f"{_format_metric(target_row['공정 유효 Capa'])}\n"
        "대당 일 Capa     = 공정별 대당 Capa ÷ RUN_DAY\n"
        f"                 = {_format_metric(target_row['공정 유효 Capa'])} ÷ "
        f"{_format_metric(target_row['RUN_DAY'], 1)} = "
        f"{_format_metric(target_row['대당 일 Capa'])}\n"
        "일 표준 가능량   = 대당 일 Capa × 가용대수\n"
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
            border=True,
        )
        st.metric(
            "선택 분류 소요대수 비중",
            f"{float(contribution_row['소요대수 비중']):.2%}",
            border=True,
        )
        st.metric(
            "선택 분류 유효 Capa",
            _format_metric(contribution_row["분류 유효 Capa"]),
            border=True,
        )

    st.markdown("#### 제품·WF 속성별 Mix 산출 근거")
    # 조화가중(부하량 비중 × 유효 Capa 역수)이라는 읽는 법은 Guide 가 말한다. `●` 가 무엇인지는
    # 표를 보는 그 자리에서 알아야 해 한 줄로 남긴다.
    st.caption("`●` 선택한 분류")
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


def _render_standard_target_exceptions(excluded_row_count: int, labels: ProcessLabels) -> None:
    # 순수 표시 상수를 그리는 안내 표다. CSV 출구가 없어 표시명을 바로 입힌다.
    with st.expander("예외 처리 공정", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "공정": labels.label(process),
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


render_page_header("표준 목표")
render_page_guide("standard_target_capa", title="표준 목표")
# 공정 표시명은 화면 표기 전용 라벨이다. 계산·저장값·왕복 CSV 는 원본 공정명을 쓴다.
process_labels = get_process_labels()

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
        empty_message="선택 범위에 표준 목표 기준정보가 없습니다.",
    )
    equipment_repository = get_equipment_repository(str(EQUIPMENT_DUCKDB_PATH.resolve()))
    availability = equipment_repository.load_standard_target_availability()
except BOOTSTRAP_ERRORS as exc:
    # 이 `try` 는 시뮬레이션 DB 와 설비 DB 를 다 연다. 어느 쪽이 잠겼는지 예외로는 가릴 수
    # 없으므로 두 경로를 다 적는다.
    st.error(bootstrap_error_message(exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)))
    st.stop()

minimum_date = _first_day(effective_start_month)
maximum_date = _last_day(effective_end_month)
default_start_date = _first_day(effective_start_month)
default_end_date = _last_day(effective_end_month)
date_clamped = _initialize_date_state(
    START_DATE_KEY, default_start_date, minimum_date, maximum_date
)
date_clamped |= _initialize_date_state(END_DATE_KEY, default_end_date, minimum_date, maximum_date)
date_reordered = False
if st.session_state[START_DATE_KEY] > st.session_state[END_DATE_KEY]:
    st.session_state[END_DATE_KEY] = st.session_state[START_DATE_KEY]
    date_reordered = True

# 저장된 선택지 문자열이 현재 옵션에 없으면 위젯 생성이 실패한다. 옵션은 화면이 소유하므로
# 검증도 여기서 한다. 상세 토글이 꺼져 위젯이 없는 실행에서도 세션값을 정상으로 유지한다.
if st.session_state.get(OUTPUT_METRIC_KEY) == "일 최대 투입 가능량":
    st.session_state[OUTPUT_METRIC_KEY] = DEFAULT_STANDARD_TARGET_OUTPUT_METRIC
if st.session_state.get(OUTPUT_METRIC_KEY) not in (*OUTPUT_OPTIONS, None):
    st.session_state[OUTPUT_METRIC_KEY] = DEFAULT_STANDARD_TARGET_OUTPUT_METRIC
if OUTPUT_METRIC_KEY not in st.session_state:
    # 위젯에 `default=` 를 함께 주면 세션 키와 충돌해 Streamlit 이 경고를 내고
    # 리비전에서 복원한 값을 첫 렌더에 되돌린다. 기본값은 여기서만 심는다.
    st.session_state[OUTPUT_METRIC_KEY] = DEFAULT_STANDARD_TARGET_OUTPUT_METRIC
if st.session_state.get(DETAIL_LEVEL_KEY) not in DETAIL_LEVEL_LABELS:
    st.session_state[DETAIL_LEVEL_KEY] = DEFAULT_STANDARD_TARGET_DETAIL_LEVEL
if not isinstance(st.session_state.get(SHOW_DETAIL_KEY), bool):
    st.session_state[SHOW_DETAIL_KEY] = False

# 조건 카드는 한 번 만들고 두 번 들어간다 — 공정 필터의 선택지는 계산이 끝나야 나온다. 카드
# 안의 차례가 곧 보는 순서다(언제 → 어느 공정 → 어떻게 나눠 볼지). 무엇을 볼지(`표시 항목`)는
# 본문 결과 상자 맨 위다.
card = condition_card("표준 목표 조건", name=CARD_NAME)
with card:
    with st.container(horizontal=True, gap="small"):
        start_date = st.date_input(
            "시작일",
            min_value=minimum_date,
            max_value=maximum_date,
            key=START_DATE_KEY,
            persist_state="session",
        )
        end_date = st.date_input(
            "종료일",
            min_value=minimum_date,
            max_value=maximum_date,
            key=END_DATE_KEY,
            persist_state="session",
        )
# 날짜를 맞춘 사실은 본문에 알린다. 카드는 기본으로 접혀 있어 그 안에 두면 저장된 날짜가
# 바뀐 줄 모른다.
if date_clamped:
    st.caption(
        ":orange-badge[조정됨] 조회일이 현재 조회기간 밖이라 "
        f"{minimum_date:%Y-%m-%d} ~ {maximum_date:%Y-%m-%d} 안으로 맞췄습니다."
    )
if date_reordered:
    st.caption(":orange-badge[조정됨] 시작일이 종료일보다 늦어 종료일을 시작일에 맞췄습니다.")
if start_date > end_date:
    st.error("시작일은 종료일보다 늦을 수 없습니다.")
    st.stop()

# 주차 계산의 월 슬라이스는 조회일이 아니라 **달력 주차의 귀속 달**이 정한다. 월 경계 주차는
# 조회 시작·종료 달 바깥 달에 귀속될 수 있고(`iso_week_calendar.owning_month` — 일수가 더
# 많은 달), 그 달을 슬라이스에서 빼면 사용자가 요청한 날이 든 주가 inner 조인에서 통째로
# 사라진다. 경고도 남지 않는다 — 행 자체가 없어 결측 검사에 걸리지 않는다.
#
# 형제 화면 `app_pages/wip_status.py` 가 이미 이렇게 한다. 여기만 역이식이 안 됐었다.
page_calendar = build_iso_week_calendar(start_date, end_date)
start_month = int(page_calendar["생산계획년월"].min())
end_month = int(page_calendar["생산계획년월"].max())

try:
    # 계산 입력의 월 슬라이스는 캐시 래퍼 안에서 한다. 뒤의 주차 계산이 쓰는 두 표만 자른다.
    filtered_tables = {
        name: scenario_month_table(active_scenario, name, start_month, end_month)
        for name in ("RQ_RUN_DAY", "RQ_PKG_PLAN")
    }
    unit_capacity, required_equipment = scenario_capacity_and_demand(
        scenario_cache_key(reference_version, active_scenario, start_month, end_month),
        scenario_tables=active_scenario["tables"],
        reference_tables=reference_tables,
    )
    standard_target_exception_rows = standard_target_exception_row_count(required_equipment)
    required_equipment = prepare_standard_target_required_equipment(required_equipment)
    production_reqb = exclude_er_required_equipment(active_scenario["tables"]["RQ_REQB"])
except (KeyError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

process_order = production_reqb[["공정"]].drop_duplicates()
process_order = apply_display_order(
    process_order,
    display_order,
    PAGE_STANDARD_TARGET,
    TAB_TARGET_CAPACITY,
)
process_options = process_order["공정"].astype(str).tolist()
public_default = prune_list_selection(STANDARD_TARGET_PROCESS_DEFAULT_KEY, process_options)
prune_list_selection(PROCESS_FILTER_KEY, process_options, default=public_default)


def _restore_public_process_default() -> None:
    st.session_state[PROCESS_FILTER_KEY] = public_default.copy()


# 결과 상자. 맨 위가 작업 줄(아래에서 채운다)이고 그 아래가 **무엇을 볼지**(`표시 항목`)다 —
# 로직 분석까지 결과를 통째로 바꾸는 전환이라 하위 탭과 같은 것이고, 카드가 아니라 본문이다
# (2026-09-29 사용자 결정). 카드의 상세·PKG 기준이 이 값을 보므로 카드보다 먼저 그린다.
weekly_output_container = st.container(border=True)
with weekly_output_container:
    action_row = st.container()
    output_metric = st.segmented_control(
        "표시 항목",
        options=OUTPUT_OPTIONS,
        key=OUTPUT_METRIC_KEY,
        persist_state="session",
    )
    if output_metric is None:
        output_metric = DEFAULT_STANDARD_TARGET_OUTPUT_METRIC

with card:
    selected_processes = st.multiselect(
        "공정 필터",
        options=process_options,
        placeholder="미선택 시 전체 공정",
        key=PROCESS_FILTER_KEY,
        persist_state="session",
        # 표시만 바꾼다. 이 선택값은 리비전 프리셋으로 저장되므로 원본이어야 한다.
        format_func=process_labels.format_func(),
    )
    effective_public_default = set(public_default or process_options)
    effective_selection = set(selected_processes or process_options)
    has_temporary_override = effective_selection != effective_public_default
    # 지금 선택이 리비전 공용 기본값인지 개인 임시 변경인지 한 줄로 말한다. 카드 폭이 좁아
    # 배지와 글을 따로 세우면 두 줄로 흩어진다.
    default_label = "전체 공정" if not public_default else f"{len(public_default):,}개 공정"
    status_badge = (
        ":orange-badge[개인 임시 변경]"
        if has_temporary_override
        else ":green-badge[공용 기본값 적용]"
    )
    st.caption(f"{status_badge} 리비전 공용 기본값 · {default_label}")
    if has_temporary_override:
        st.button(
            "공용 기본값으로 복원",
            icon=":material/restart_alt:",
            key="restore_standard_target_process_default",
            on_click=_restore_public_process_default,
            width="stretch",
        )
    # 로직 분석은 한 건을 고르는 화면이라 상세·분류 수준·PKG 기준이 뜻이 없다. 세우지 않은
    # 회차에도 값은 `persist_state` 와 리비전 프리셋이 지킨다.
    detail_level = "공정"
    pkg_basis = False
    if output_metric != "로직 분석":
        show_detail = st.toggle(
            "상세",
            key=SHOW_DETAIL_KEY,
            persist_state="session",
        )
        if show_detail:
            detail_level = st.selectbox(
                "제품 분류 수준",
                options=list(DETAIL_LEVEL_LABELS),
                format_func=lambda value: DETAIL_LEVEL_LABELS[value],
                key=DETAIL_LEVEL_KEY,
                persist_state="session",
            )
        if output_metric == "일 표준 가능량":
            pkg_basis = st.toggle(
                "PKG 기준",
                key=PKG_BASIS_KEY,
                persist_state="session",
            )
    logic_filters = st.container()

target_processes = selected_processes or process_options
template = build_weekly_availability_template(target_processes, start_date, end_date)
template_csv = template.to_csv(index=False).encode("utf-8-sig")


def _close_dialog() -> None:
    st.session_state.pop(DIALOG_KEY, None)


def _open_dialog(name: str) -> None:
    st.session_state[DIALOG_KEY] = name


@st.dialog("가용설비 붙여넣기", width="large", on_dismiss=_close_dialog)
def _paste_dialog() -> None:
    """주차별 가용설비 표를 붙여넣어 설비 DB 최신본으로 저장한다(리비전은 만들지 않는다)."""
    render_csv_download(
        data=template_csv,
        file_name=f"Weekly_Available_Equipment_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv",
        key="dialog_standard_target_availability_template",
        label=CSV_TEMPLATE_LABEL,
    )
    # 덮어쓰기라는 것은 누르기 전에 알아야 한다 — Guide 로만 보내지 않는다(2026-09-29 2차 리뷰).
    st.caption(
        "같은 공정·Weeknum 의 가용대수는 붙여넣은 값으로 덮어씁니다. 설비 DB 에 최신본 하나만 "
        "남아 이전 값으로 되돌릴 수 없습니다."
    )
    with st.form("standard_target_availability_clipboard", border=False):
        clipboard_text = st.text_area(
            "가용설비 표 붙여넣기",
            key="standard_target_availability_clipboard_text",
            height=180,
            placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
        )
        import_submitted = st.form_submit_button(
            "붙여넣기 적용",
            icon=":material/content_paste:",
            type="primary",
        )
    if not import_submitted:
        return
    if not clipboard_text.strip():
        st.error("적용할 가용설비 표를 Excel에서 복사해 붙여넣으세요.")
        return
    try:
        equipment_repository.save_standard_target_availability(
            # 보유 공정 목록은 이 화면이 소유한다. 표시명을 그대로 적어 붙여넣거나 오타가 난
            # 공정은 여기서 막지 않으면 아무 계산에도 붙지 않는 행으로 조용히 저장된다. 필터와
            # 무관하게 전체 공정을 허용한다.
            parse_weekly_availability_clipboard(clipboard_text, known_processes=process_options)
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)))
        return
    queue_flash(
        AVAILABILITY_FLASH_KEY,
        "주차별 가용설비 최신본을 저장했습니다. 서버를 재시작해도 유지됩니다.",
    )
    _close_dialog()
    st.rerun()


@st.dialog("입력 초기화", width="small", on_dismiss=_close_dialog)
def _clear_dialog() -> None:
    """저장된 주차별 가용설비를 모두 지운다. 되돌릴 수 없어 한 번 더 묻는다."""
    st.warning("저장된 주차별 가용설비를 모두 지웁니다. 되돌릴 수 없습니다.")
    confirmed = st.checkbox("지우는 것을 확인합니다.", key="standard_target_clear_confirm")
    if not st.button(
        "입력 초기화",
        icon=":material/delete:",
        key="clear_standard_target_availability",
        type="primary",
        disabled=not confirmed,
    ):
        return
    try:
        equipment_repository.clear_standard_target_availability()
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)))
        return
    queue_flash(AVAILABILITY_FLASH_KEY, "주차별 가용설비 입력을 비웠습니다.")
    _close_dialog()
    st.rerun()


with action_row:
    # 결과 상자 맨 위 작업 줄. 결과를 만드는 입력(주차별 가용설비)이 여기서 들어간다. 붙여넣기와
    # 초기화는 가끔 하는 쓰기라 팝업이고, 여는 버튼은 콜백으로 연다 — 한 회차에 팝업이 둘 뜨지
    # 않는다.
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.button(
            "가용설비 붙여넣기",
            icon=":material/content_paste:",
            key="open_standard_target_availability_paste",
            type="primary",
            on_click=_open_dialog,
            args=(PASTE_DIALOG,),
        )
        render_csv_download(
            data=template_csv,
            file_name=f"Weekly_Available_Equipment_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv",
            key="download_standard_target_availability_template",
            label=CSV_TEMPLATE_LABEL,
        )
        st.button(
            "입력 초기화",
            icon=":material/delete:",
            key="open_standard_target_availability_clear",
            on_click=_open_dialog,
            args=(CLEAR_DIALOG,),
            disabled=availability.empty,
        )
    render_flash(AVAILABILITY_FLASH_KEY)
if st.session_state.get(DIALOG_KEY) == PASTE_DIALOG:
    _paste_dialog()
elif st.session_state.get(DIALOG_KEY) == CLEAR_DIALOG:
    _clear_dialog()

_render_standard_target_exceptions(standard_target_exception_rows, process_labels)

if availability.empty:
    with weekly_output_container:
        st.subheader("주차별 일 표준 가능량")
        st.info("주차별 일 표준 가능량을 보려면 위 「가용설비 붙여넣기」로 가용설비를 입력하세요.")
    st.stop()

filtered_required_equipment = required_equipment
if selected_processes:
    filtered_required_equipment = required_equipment.loc[
        required_equipment["공정"].isin(selected_processes)
    ].reset_index(drop=True)

if output_metric == "로직 분석":
    with weekly_output_container:
        _render_logic_analysis(
            required_equipment=filtered_required_equipment,
            run_day=filtered_tables["RQ_RUN_DAY"],
            availability=availability,
            start_date=start_date,
            end_date=end_date,
            process_order=target_processes,
            process_labels=process_labels,
            filters=logic_filters,
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
    # 가용대수를 곱해 구하는 지표에서만 뜻이 있다. 대당 일 Capa 는 가용대수 이전 단계라
    # 입력이 없어도 값이 다 나오는데, 여기서 함께 경고하면 없는 문제를 알리는 셈이 된다.
    # 표에서 멀리 떨어져 있으면 빈칸을 보고도 이 안내를 못 찾으므로 결과 상자 안에 넣는다.
    if not missing_availability.empty and output_metric in AVAILABILITY_BASED_METRICS:
        with weekly_output_container:
            st.warning(
                f"선택 범위의 공정·주차 중 {len(missing_availability):,}건에 가용대수가 없어 "
                "결과를 빈칸으로 표시합니다."
            )
            with st.expander("누락 공정·주차 확인", expanded=False):
                displayed_missing = missing_availability.copy()
                displayed_missing["공정"] = process_labels.series(displayed_missing["공정"])
                if process_labels:
                    # 이 표가 가리키는 입력은 작업 줄의 `주차별 가용설비 CSV 양식`이고 그 양식과
                    # 붙여넣기 파서는 원본 공정명을 요구한다. 화면 이름을 그대로 적어
                    # 붙여넣지 않도록 여기서 알린다.
                    st.caption(
                        "공정은 화면 표시명입니다. 붙여넣기에 쓸 원본 공정명은 작업 줄의 "
                        "「CSV 양식 다운로드」에서 확인하세요."
                    )
                st.dataframe(displayed_missing, hide_index=True, width="stretch")

    classification_columns = [
        "공정",
        "소요기준",
        *WEIGHTED_CAPACITY_HIERARCHY[1 : WEIGHTED_CAPACITY_HIERARCHY.index(detail_level) + 1],
    ]
    output_value_column = output_metric
    output_title = output_metric
    decimal_places = OUTPUT_METRICS[output_metric]
    output_file_metric = output_metric
    if pkg_basis:
        try:
            weekly_target = get_pkg_equivalent_standard_target(
                required_equipment=filtered_required_equipment,
                run_day=filtered_tables["RQ_RUN_DAY"],
                weekly_availability=availability,
                start_date=start_date,
                end_date=end_date,
                detail_level=detail_level,
                plan=filtered_tables["RQ_PKG_PLAN"],
                # 바로 위에서 같은 인자로 만든 것이다. 넘기지 않으면 한 실행에서 같은
                # 프레임을 한 번 더 해시한다.
                _weekly_target=weekly_target,
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
            PAGE_STANDARD_TARGET,
            TAB_TARGET_CAPACITY,
        )
        output_export = build_hierarchical_monthly_export(
            output_table,
            classification_columns=classification_columns,
            column_labels=COLUMN_LABELS,
            decimal_places=decimal_places,
        )
        output_csv = output_export.to_csv(index=False).encode("utf-8-sig")
        render_table_heading(
            f"주차별 {output_title}",
            csv=output_csv,
            file_name=(
                f"Standard_Target_Capa_{output_file_metric}_"
                f"{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv"
            ),
            key="download_standard_target_result",
        )
        render_hierarchical_monthly_table(
            output_table,
            classification_columns=classification_columns,
            column_labels=COLUMN_LABELS,
            decimal_places=decimal_places,
            key="standard_target_weekly_table",
            value_labels=process_labels.value_labels(),
            page_size=80,
        )
