# Purpose: 기준 정보로 산출한 대당 Capa·소요대수·확보율을 탭 셋과 제외 표로 보여 준다.

"""산출 결과 — 표를 보는 조건은 사이드바 `표 조건` 카드, 설명은 Guide(2026-09-29 사용자 결정).

세 탭이 **한 카드**를 쓰고 안의 내용만 열린 탭 것으로 바뀐다(대당 Capa: 표시 방식·집계
수준·공정 필터 / 소요대수: 상세·필터 / 확보율: 필터·히트맵 주요 공정). 카드는 열린 탭 하나의
것만 서므로 닫힌 탭의 선택은 `persist_state` 가 지킨다. 본문에는 결과·제외 알림·표만 남는다.
"""

import pandas as pd
import streamlit as st

from capa_simulation.components.capacity_assumption_notice import (
    render_capacity_assumption_notice,
)
from capa_simulation.components.column_filter import render_column_filter_controls
from capa_simulation.components.exclusion_table import render_exclusion_table
from capa_simulation.components.exclusion_waterfall import render_exclusion_waterfall
from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.securement_heatmap import (
    render_securement_heatmap,
    shortage_summary,
)
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.components.table_toolbar import render_table_heading
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
    prune_list_selection,
    resolve_effective_months,
    scenario_capacity_and_demand,
)
from capa_simulation.scenario_preset_state import (
    DEFAULT_SECURE_THRESHOLD_PERCENT,
    DEFAULT_WARNING_THRESHOLD_PERCENT,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
    session_threshold,
)
from capa_simulation.scenario_state import scenario_month_table
from capa_simulation.services.display_order import (
    apply_display_order,
    reorder_display_columns,
)
from capa_simulation.services.display_order_scopes import (
    PAGE_CALCULATION,
    TAB_REQUIRED,
    TAB_SECUREMENT,
    TAB_UNIT_CAPACITY,
)
from capa_simulation.services.required_equipment import (
    PKG_UNCOUNTED_REASON,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    RESULT_DIMENSIONS,
    required_equipment_to_month_table,
)
from capa_simulation.services.securement_rate import (
    SECUREMENT_DIMENSIONS,
    securement_rate_to_month_table,
)
from capa_simulation.services.simulation_cache import (
    get_effective_process_capacity_table,
    get_securement_rate,
    scenario_cache_key,
)
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    UNIT_CAPACITY_DIMENSIONS,
    capacity_assumptions,
    unit_capacity_to_month_table,
)
from capa_simulation.services.weighted_unit_capacity import WEIGHTED_CAPACITY_HIERARCHY
from capa_simulation.sidebar_status import table_card

KEY_PROCESS_FILTER_KEY = "securement_heatmap_key_processes"
# 사이드바 `표 조건` 카드 이름. 세 탭이 한 카드를 쓴다.
CARD_NAME = "calculation_result"
# STEP 뷰에서 공정을 고르지 않았을 때. 필터가 사이드바 카드에 있으므로 자리를 말한다.
STEP_VIEW_HINT = (
    "STEP별 대당 Capa는 선택한 공정만 그립니다. 사이드바 「표 조건」의 공정 필터에서 공정을 "
    "선택하세요. 전체 공정을 한 번에 보려면 공정별을 사용하세요."
)

CAPACITY_LEVEL_LABELS = {
    "공정": "공정",
    "양산구분": "양산",
    "제품정보": "제품",
    "Stack": "Stack",
    "WF 구분": "WF 속성",
}

# 계산 순서 그대로다 — 대당 Capa 로 소요대수를 내고, 가용대수와 나눠 확보율을 낸다.
TAB_NAMES = (
    ":material/insights: 대당 Capa",
    ":material/precision_manufacturing: 소요대수",
    ":material/monitoring: 확보율",
)


render_page_header("산출 결과")
render_page_guide("calculation_result", title="산출 결과")
# 공정 표시명은 화면 표기 전용 라벨이다. 계산·저장값·왕복 CSV 는 원본 공정명을 쓴다.
process_labels = get_process_labels()
# 언패킹은 **위치 순서**다. `TAB_NAMES` 를 바꾸면 여기도 같이 바꾼다 — 어긋나도 예외가
# 나지 않고 표가 다른 탭에 조용히 그려진다.
unit_capacity_tab, required_tab, availability_tab = stateful_tabs(
    TAB_NAMES,
    key="calculation_result_active_tab",
)

try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    display_order = context.display_order
    active_scenario = context.active_scenario
    effective_start, effective_end = resolve_effective_months(
        context,
        active_scenario["tables"]["RQ_REQB"],
        "RQ_REQB",
        empty_message="선택 범위에 소요대수 산출 기준이 없습니다.",
    )

    # 계산 입력의 월 슬라이스는 캐시 래퍼 안에서 한다. 여기서 자르는 것은 확보율의 분모인
    # 가용대수 하나뿐이다 — 설비대수 **편집**은 `기준 정보` 페이지가 갖는다.
    available_equipment = scenario_month_table(
        active_scenario,
        "RQ_EQP_AVBL",
        effective_start,
        effective_end,
    )

    capacity_cache_key = scenario_cache_key(
        reference_version, active_scenario, effective_start, effective_end
    )
    unit_capacity, required_equipment = scenario_capacity_and_demand(
        capacity_cache_key,
        scenario_tables=active_scenario["tables"],
        reference_tables=reference_tables,
    )
    capacity_exclusions = unit_capacity.attrs.get(CAPACITY_EXCLUSIONS_ATTR, pd.DataFrame())
    assumptions = capacity_assumptions(unit_capacity)
    required_exclusions = required_equipment.attrs.get(
        REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR, pd.DataFrame()
    )
    required_table = required_equipment_to_month_table(required_equipment)
    required_table = apply_display_order(
        required_table,
        display_order,
        PAGE_CALCULATION,
        TAB_REQUIRED,
    )
    required_table, required_detail_dimensions = reorder_display_columns(
        required_table,
        RESULT_DIMENSIONS,
        display_order,
        PAGE_CALCULATION,
        TAB_REQUIRED,
    )
    securement_rate = get_securement_rate(
        capacity_cache_key,
        available_equipment,
        required_equipment,
    )
    securement_table = securement_rate_to_month_table(securement_rate)
    securement_table = apply_display_order(
        securement_table,
        display_order,
        PAGE_CALCULATION,
        TAB_SECUREMENT,
    )
except BOOTSTRAP_ERRORS as exc:
    # 원인 하나를 세 탭에 같이 보여 준다. 문구는 한 번만 만든다.
    bootstrap_message = bootstrap_error_message(exc)
    for error_tab in (unit_capacity_tab, required_tab, availability_tab):
        with error_tab:
            st.error(bootstrap_message)
else:
    # 대당 Capa **계산**은 게이트하지 않는다 — 소요대수·확보율 두 탭이 같은 `unit_capacity`
    # 를 쓰므로 이 페이지에서는 어차피 돈다. 탭마다의 몫은 월별 표로 펼치는 일과 그 뒤의 CSV
    # 인코딩·Plotly 조립이고, 그것만 열린 탭에서 한다.
    #
    # 조건 카드는 **열린 탭 하나의 것만** 선다. 세 탭이 같은 카드 key 를 쓰므로 한 회차에 둘을
    # 세우면 위젯 id 가 겹친다. 닫힌 탭의 선택은 `persist_state` 가 지킨다.
    open_tab = next(
        (
            tab
            for tab in (unit_capacity_tab, required_tab, availability_tab)
            if not tab_is_hidden(tab)
        ),
        unit_capacity_tab,
    )
    process_filter_key = "unit_capacity_process_filter"
    process_order = required_equipment[["공정"]].drop_duplicates()
    # 표시순서 스코프 문자열은 DB 공용 프로필의 행 키다. 페이지 이름이 바뀌어도 **이 인자는
    # 그대로 둔다** — 안 맞으면 예외가 아니라 정렬이 조용히 사라진다.
    process_order = apply_display_order(
        process_order,
        display_order,
        PAGE_CALCULATION,
        TAB_UNIT_CAPACITY,
    )
    process_options = process_order["공정"].astype(str).tolist()
    prune_list_selection(process_filter_key, process_options)
    key_process_options = securement_table[SECUREMENT_DIMENSIONS[0]].astype(str).tolist()
    prune_list_selection(KEY_PROCESS_FILTER_KEY, key_process_options)

    with unit_capacity_tab:
        render_capacity_assumption_notice(assumptions)
        if not capacity_exclusions.empty:
            st.warning(f"대당 Capa 산출에서 {len(capacity_exclusions):,}개 기준을 제외했습니다.")
            # 표는 「무엇이 빠졌나」를 답하고 워터폴은 「얼마나·어디서 빠졌나」를 답한다.
            # 확보율이 낮을 때 설비 부족인지 기준정보 결손인지를 가르는 것이 이 그림이다.
            render_exclusion_waterfall(
                capacity_exclusions,
                remaining_rows=len(unit_capacity),
                key="unit_capacity_exclusion_waterfall",
                owner_tab=unit_capacity_tab,
            )
            with st.expander("제외 기준정보 확인", expanded=False):
                render_exclusion_table(
                    capacity_exclusions,
                    dimensions=UNIT_CAPACITY_DIMENSIONS,
                    display_order=display_order,
                    page=PAGE_CALCULATION,
                    tab=TAB_UNIT_CAPACITY,
                    labels=process_labels,
                    file_name=(
                        f"Capa_Unit_Capacity_Exclusions_{effective_start}_{effective_end}.csv"
                    ),
                    key="download_unit_capacity_exclusions_csv",
                )

    if open_tab is unit_capacity_tab:
        with table_card(CARD_NAME):
            # 탭 이름이 이미 `대당 Capa` 라 선택지에서는 그 낱말을 뺀다. 두 값은 집계 단위가
            # 다른 것이지 다른 지표가 아니다.
            capacity_view = st.segmented_control(
                "표시 방식",
                options=["공정별", "STEP별"],
                default="공정별",
                key="unit_capacity_view_mode",
                persist_state="page",
            )
            selected_level_label = st.selectbox(
                "집계 수준",
                options=list(CAPACITY_LEVEL_LABELS.values()),
                index=0,
                key="unit_capacity_detail_level",
                persist_state="session",
                disabled=capacity_view == "STEP별",
            )
            selected_processes = st.multiselect(
                "공정 필터",
                options=process_options,
                placeholder=(
                    "공정을 선택하세요" if capacity_view == "STEP별" else "미선택 시 전체 공정"
                ),
                key=process_filter_key,
                persist_state="session",
                # 표시만 바꾼다. 선택값은 원본이어야 아래 `isin` 이 원본 컬럼과 맞는다.
                format_func=process_labels.format_func(),
            )
        selected_level = next(
            level for level, label in CAPACITY_LEVEL_LABELS.items() if label == selected_level_label
        )
        with unit_capacity_tab:
            # STEP 뷰는 경로 하나하나가 행이라 전 공정을 그리면 Plotly 표가 수천 행이 된다.
            # 미선택이면 표를 만들지도 CSV 로 인코딩하지도 않고 안내만 남긴다. 선택 해제를
            # 허용하는 컨트롤이라 `capacity_view` 는 None 일 수 있으므로 명시 비교로 판단한다.
            if capacity_view == "STEP별" and not selected_processes:
                st.info(STEP_VIEW_HINT)
            else:
                if capacity_view == "STEP별":
                    unit_capacity_table = unit_capacity_to_month_table(unit_capacity)
                    classification_columns = list(UNIT_CAPACITY_DIMENSIONS)
                    output_title = "STEP별 대당 Capa"
                    file_prefix = "Capa_Step_Unit_Capacity"
                else:
                    unit_capacity_table = get_effective_process_capacity_table(
                        capacity_cache_key,
                        required_equipment,
                        selected_level,
                    )
                    classification_columns = [
                        column
                        for column in ["공정", "소요기준", *WEIGHTED_CAPACITY_HIERARCHY[1:]]
                        if column in unit_capacity_table.columns
                    ]
                    output_title = "공정별 대당 Capa"
                    file_prefix = "Capa_Effective_Process_Capacity"
                unit_capacity_table = apply_display_order(
                    unit_capacity_table,
                    display_order,
                    PAGE_CALCULATION,
                    TAB_UNIT_CAPACITY,
                )
                unit_capacity_table, classification_columns = reorder_display_columns(
                    unit_capacity_table,
                    classification_columns,
                    display_order,
                    PAGE_CALCULATION,
                    TAB_UNIT_CAPACITY,
                )
                if selected_processes:
                    unit_capacity_table = unit_capacity_table.loc[
                        unit_capacity_table["공정"].isin(selected_processes)
                    ].reset_index(drop=True)

                capacity_export = build_hierarchical_monthly_export(
                    unit_capacity_table,
                    classification_columns=classification_columns,
                    column_labels=COLUMN_LABELS,
                    decimal_places=0,
                )
                capacity_csv = capacity_export.to_csv(index=False, float_format="%.0f").encode(
                    "utf-8-sig"
                )
                render_table_heading(
                    output_title,
                    csv=capacity_csv,
                    file_name=(
                        f"{file_prefix}_{selected_level}_{effective_start}_{effective_end}.csv"
                    ),
                    key="download_unit_capacity_csv",
                )
                render_hierarchical_monthly_table(
                    unit_capacity_table,
                    classification_columns=classification_columns,
                    column_labels=COLUMN_LABELS,
                    decimal_places=0,
                    key="unit_capacity_monthly_table",
                    value_labels=process_labels.value_labels(),
                    owner_tab=unit_capacity_tab,
                )

    if open_tab is required_tab:
        all_month_columns = [
            column for column in required_table.columns if column not in RESULT_DIMENSIONS
        ]
        with table_card(CARD_NAME):
            show_detail = st.toggle(
                "상세",
                key="required_equipment_detail",
                persist_state="session",
            )
            if show_detail:
                table_dimensions = required_detail_dimensions
                view_table = required_table.copy()
            else:
                table_dimensions = ["Area_Name", "공정"]
                view_table = required_table.groupby(table_dimensions, as_index=False, sort=False)[
                    all_month_columns
                ].sum(min_count=1)
            filtered_required_table = render_column_filter_controls(
                view_table,
                table_dimensions,
                key_prefix="required_equipment_filter",
                column_labels=COLUMN_LABELS,
                value_labels=process_labels.value_labels(),
            )
        with required_tab:
            # 대당 Capa 제외 표는 **대당 Capa 탭**이 그린다. 두 탭이 한 페이지에 있게 된
            # 뒤로는 같은 표를 같은 파일명으로 두 번 내리는 것이라 여기서는 걷어냈다.
            if not required_exclusions.empty:
                # 사유가 둘이다. 대당 Capa 가 없는 것은 기준정보를 고칠 일이고, PKG 의 Buffer
                # 외 행은 규칙대로 세지 않은 것이다 — 한 문장에 섞으면 고칠 것이 없는데 고치러
                # 간다.
                uncounted_pkg = required_exclusions["제외사유"].eq(PKG_UNCOUNTED_REASON)
                capacity_missing = required_exclusions.loc[~uncounted_pkg]
                if not capacity_missing.empty:
                    positive_load_exclusions = capacity_missing.loc[
                        capacity_missing["부하량"].gt(0)
                    ]
                    st.warning(
                        "대당 Capa가 없어 소요대수 산출에서 "
                        f"{len(capacity_missing):,}건을 제외했습니다"
                        f" (부하량 발생 {len(positive_load_exclusions):,}건)."
                    )
                if uncounted_pkg.any():
                    st.info(
                        "소요기준 PKG 는 Buffer 로만 셉니다. Core·Top·Dummy 등 "
                        f"{int(uncounted_pkg.sum()):,}건은 Buffer 에 쌓여 있어 소요대수에 넣지 "
                        "않았습니다."
                    )
                with st.expander("소요대수 제외 기준정보", expanded=False):
                    render_exclusion_table(
                        required_exclusions,
                        dimensions=RESULT_DIMENSIONS,
                        display_order=display_order,
                        page=PAGE_CALCULATION,
                        tab=TAB_REQUIRED,
                        labels=process_labels,
                        file_name=(
                            "Capa_Required_Equipment_Exclusions_"
                            f"{effective_start}_{effective_end}.csv"
                        ),
                        key="download_required_exclusions_csv",
                    )
            required_export = build_hierarchical_monthly_export(
                filtered_required_table,
                classification_columns=table_dimensions,
                column_labels=COLUMN_LABELS,
                decimal_places=2,
            )
            required_csv = required_export.to_csv(index=False, float_format="%.2f").encode(
                "utf-8-sig"
            )
            required_view_name = "Detail" if show_detail else "Summary"
            render_table_heading(
                "소요대수",
                csv=required_csv,
                file_name=(
                    "Capa_Required_Equipment_"
                    f"{required_view_name}_{effective_start}_{effective_end}.csv"
                ),
                key=(
                    "download_required_equipment_detail_csv"
                    if show_detail
                    else "download_required_equipment_summary_csv"
                ),
            )
            render_hierarchical_monthly_table(
                filtered_required_table,
                classification_columns=table_dimensions,
                column_labels=COLUMN_LABELS,
                decimal_places=2,
                key=(
                    "required_equipment_detail_table"
                    if show_detail
                    else "required_equipment_summary_table"
                ),
                value_labels=process_labels.value_labels(),
                page_size=60 if show_detail else None,
                owner_tab=required_tab,
            )

    if open_tab is availability_tab:
        # 판정 기준은 리비전 프리셋이 소유하는 **세션 공용 값**이다. 이 페이지는 위젯을 두지
        # 않고 HOME·Static Capa 가 정한 경계를 그대로 읽는다 — 같은 확보율이 화면마다 다른 색으로
        # 보이면 안 된다.
        secure_threshold = session_threshold(SECURE_THRESHOLD_KEY, DEFAULT_SECURE_THRESHOLD_PERCENT)
        warning_threshold = session_threshold(
            WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD_PERCENT
        )
        with table_card(CARD_NAME):
            displayed_securement_table = render_column_filter_controls(
                securement_table,
                SECUREMENT_DIMENSIONS,
                key_prefix="securement_filter",
                value_labels=process_labels.value_labels(),
            )
            # 히트맵 대상은 위 표 필터와 따로 둔다 — 표는 값을 뒤지는 화면이고 히트맵은 관리
            # 대상만 남겨 두고 보는 화면이라 쓰임이 다르다.
            selected_key_processes = st.multiselect(
                "히트맵 주요 공정",
                options=key_process_options,
                placeholder="전체 공정",
                key=KEY_PROCESS_FILTER_KEY,
                persist_state="session",
                format_func=process_labels.format_func(),
            )
        with availability_tab:
            securement_export = build_hierarchical_monthly_export(
                displayed_securement_table,
                classification_columns=SECUREMENT_DIMENSIONS,
                column_labels=COLUMN_LABELS,
                decimal_places=2,
                value_format="percent",
            )
            securement_csv = securement_export.to_csv(index=False).encode("utf-8-sig")
            render_table_heading(
                "확보율",
                csv=securement_csv,
                file_name=f"Capa_Securement_Rate_{effective_start}_{effective_end}.csv",
                key="download_securement_rate_csv",
            )
            render_hierarchical_monthly_table(
                displayed_securement_table,
                classification_columns=SECUREMENT_DIMENSIONS,
                column_labels=COLUMN_LABELS,
                decimal_places=2,
                value_format="percent",
                key="securement_rate_monthly_table",
                value_labels=process_labels.value_labels(),
                owner_tab=availability_tab,
            )
            # 표는 숫자를 답하고 히트맵은 모양을 답한다. 「주요 공정이 **언제** 무너지나」는
            # 66행을 훑어서 알 것이 아니다.
            with st.expander("주요 공정 × 월 히트맵", expanded=False):
                heatmap_table = securement_table
                if selected_key_processes:
                    heatmap_table = securement_table.loc[
                        securement_table[SECUREMENT_DIMENSIONS[0]]
                        .astype(str)
                        .isin(selected_key_processes)
                    ]
                shortages = shortage_summary(
                    heatmap_table,
                    dimension_columns=SECUREMENT_DIMENSIONS,
                    warning_threshold=warning_threshold,
                    labels=process_labels,
                )
                if shortages.empty:
                    st.success("선택한 공정은 조회 기간에 부족 구간이 없습니다.")
                else:
                    # 「언제」가 이 화면의 요점이다. 빨간 칸을 세는 것보다 숫자가 빠르다.
                    st.warning(
                        f"{len(shortages):,}개 공정에 부족 구간이 있습니다. "
                        f"가장 이른 부족은 {shortages['최초 부족'].iloc[0]} 입니다."
                    )
                    st.dataframe(
                        shortages,
                        hide_index=True,
                        width="content",
                        key="securement_shortage_summary",
                    )
                render_securement_heatmap(
                    heatmap_table,
                    dimension_columns=SECUREMENT_DIMENSIONS,
                    secure_threshold=secure_threshold,
                    warning_threshold=warning_threshold,
                    key="securement_rate_heatmap",
                    labels=process_labels,
                    owner_tab=availability_tab,
                )
