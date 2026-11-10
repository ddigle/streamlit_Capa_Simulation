# Purpose: 기준 정보로 산출한 대당 Capa·소요대수·확보율을 탭 셋과 제외 표로 보여 준다.

"""산출 결과 — 표를 보는 조건은 사이드바 `표 조건` 카드, 설명은 Guide(2026-09-29 사용자 결정).

세 탭이 **한 카드**를 쓰고 안의 내용만 열린 탭 것으로 바뀐다(대당 Capa: 표시 방식·집계
수준 / 소요대수: 상세·필터 / 확보율: 카드 없음). 카드는 열린 탭 하나의 것만 서므로 닫힌
탭의 선택은 `persist_state` 가 지킨다. 본문에는 결과·표만 남는다.

**공정은 세 탭 모두 조회 조건 패널의 공용 공정 칸이다**(2026-11-08 사용자 답 P1 — 공정 공유 1차,
`components/process_field.py`). HOME 에서 좁힌 공정 · 다른 화면에서 고른 공정을 그대로 따라가고,
여기서 고른 공정도 다른 화면이 따라간다. 좁혀진 채 내려받는 CSV 에는 그 공정만 담기고 파일 이름은
그대로다(보드 답 「지금대로」) — 좁혀졌다는 사실은 값 칸 강조와 머리 띠 공정 칩이 알린다.

제외 · 가정 알림은 자리에 그리지 않고 상태 알림으로 낸다(2026-11-03 결정 보드 D2 (나)) — 바뀔 때만
오른쪽 아래 알림창, 쌓이는 곳은 머리 `Alarm`. 제외 목록(대당 Capa `제외 기준정보` · 소요대수 탭의
경로 쪽 둘 · 계획 쪽 둘)은 본문 펼침이 아니라 그 알림 줄의 표다(2026-11-02 사용자 요청(검수표) —
「알림과 제외 기준정보는 우하단 팝업(통일된 양식)으로 뜨고 누적 알람에서 제외 기준정보를 확인할 수
있게」, 2026-11-05 같은 검수표 — 「Alarm 안 표로 이동」). 표가 알림에 싣기에 크면
(`alerts.TABLE_ROW_LIMIT`) 그 목록만 본문 펼침으로 남긴다.

대당 Capa · 소요대수 표 제목 줄의 CSV 곁에 「시트 엑셀」 이 선다(TODO 2장 「계산 결과 Excel
다운로드」 첫 넓히기 — 공정 Capa 상세 선례 그대로). 지금 화면 상태(보기 · 집계 수준 · 공정 거름 ·
표 조건 거름 · 조회기간의 달 · 공정 표시명)의 표를 화면 서식째 xlsx 로 낸다
(`components/monthly_table_workbook.py`). 통은 조건 키로 세션에 몇 벌 기억한다
(`sheet_download.remembered_bytes` — 새 `st.cache_*` 없음). 파일 이름은 곁 CSV 와 같고 확장자만
`.xlsx` 다. 소요대수 상세의 「표시 범위」(60줄씩)는 화면 보기만 나누고 시트에는 CSV 처럼 거른 줄
전부가 든다.

확보율 탭의 `히트맵` 은 **표와 같은 행**을 그린다 — 조회 조건의 공정이 히트맵에도 걸린다
(2026-10-06 사용자 결정). HOME 주요공정 프리셋과는 무관하다.
"""

from functools import partial

import pandas as pd
import streamlit as st

from capa_simulation import shared_process
from capa_simulation.components.capacity_assumption_notice import (
    render_capacity_assumption_notice,
)
from capa_simulation.components.column_filter import (
    column_filter_key,
    render_column_filter_controls,
    render_shared_process_filter,
)
from capa_simulation.components.data_error_mark import render_data_error, render_data_error_mark
from capa_simulation.components.exclusion_table import exclusion_export, render_exclusion_table
from capa_simulation.components.hierarchical_monthly_table import (
    build_hierarchical_monthly_export,
    render_hierarchical_monthly_table,
)
from capa_simulation.components.monthly_table_base import COLUMN_LABELS
from capa_simulation.components.monthly_table_workbook import (
    MonthlySheetRequest,
    monthly_table_workbook,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_field import (
    render_process_filter,
    render_stopped_process_field,
)
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.required_exclusion_notice import (
    CAPACITY_EXCLUSION_TITLE,
    PERIOD_SCOPE,
    alert_capacity_exclusions,
    alert_required_exclusions,
    alert_uncounted_demand,
    plan_exclusion_lists,
    plan_side_counts,
    render_oversized_lists,
)
from capa_simulation.components.securement_heatmap import render_securement_heatmap
from capa_simulation.components.sheet_download import (
    process_filter_text,
    remembered_bytes,
    scenario_period_rows,
)
from capa_simulation.components.state_alerts import alert_page_error, alert_table, simulation_scope
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.components.table_toolbar import (
    SheetFile,
    render_table_heading,
    table_heading_row,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    calculation_stop_notice,
    load_page_context,
    resolve_effective_months,
    stop_calculation_on_error,
)
from capa_simulation.persistence.cache import load_global_securement_threshold
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
    RESULT_DIMENSIONS,
    count_required_exclusions,
)
from capa_simulation.services.securement_rate import (
    SECUREMENT_DIMENSIONS,
    securement_rate_to_month_table,
)
from capa_simulation.services.simulation_cache import (
    csv_export_key,
    display_order_digest,
    get_display_ordered_values,
    get_effective_process_capacity_table,
    get_export_csv,
    get_required_month_table,
    get_scenario_result_summary,
    get_scenario_securement_rate,
    get_step_unit_capacity_table,
    scenario_cache_key,
)
from capa_simulation.services.unit_capacity import UNIT_CAPACITY_DIMENSIONS
from capa_simulation.services.weighted_unit_capacity import WEIGHTED_CAPACITY_HIERARCHY
from capa_simulation.settings import DUCKDB_PATH
from capa_simulation.sidebar_status import remembered_expander, table_card

HEATMAP_EXPANDER_KEY = "securement_heatmap_expander"
CAPACITY_EXCLUSIONS_EXPANDER_KEY = "unit_capacity_exclusions_expander"
# 사이드바 `표 조건` 카드 이름. 세 탭이 한 카드를 쓴다.
CARD_NAME = "calculation_result"
# 공용 공정 칸의 출처 이름(다른 화면 칩 · 이름 줄의 「산출 결과 에서」).
SCREEN = "산출 결과"
# STEP 뷰에서 공정을 고르지 않았을 때의 빈 결과 한 줄(값 — 설계 규칙 UI-TXT-04). 고르는 법은
# 공정 값 칸의 글자 · `표시 방식` 풍선 · Guide 가 말한다(UI-TXT-01 · 02).
STEP_VIEW_EMPTY = "STEP별로 그릴 공정이 없습니다."
# STEP 뷰에서 공정이 걸리지 않았을 때 공정 값 칸의 글자(지금처럼 고르라고 한다).
STEP_VIEW_PROCESS_EMPTY = "공정을 선택하세요"
# `표시 방식` 풍선 — 두 값의 뜻과 STEP별이 공정을 골라야 하는 까닭.
VIEW_MODE_HELP = (
    "공정별은 공정 단위 대당 Capa(집계 수준으로 나눠 봄), STEP별은 MCP_SEQ · STEP_SEQ 경로마다 "
    "한 줄이라 조회 조건 「공정」 에서 고른 공정만 그립니다."
)
# STEP별에서 잠긴 `집계 수준` 의 까닭 풍선(UI-INP-07 — 잠근 칸에만 단다).
LEVEL_LOCKED_HELP = "STEP별은 경로마다 한 줄이라 집계 수준을 쓰지 않습니다."

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
# 알림이 「그 화면으로」 로 열 탭 이름(아이콘 없이 — 탭 단추 글의 끝과 맞댄다).
UNIT_CAPACITY_TAB = "대당 Capa"
REQUIRED_TAB = "소요대수"
AVAILABILITY_TAB = "확보율"
# 「시트 엑셀」 — 대당 Capa · 소요대수 표를 지금 화면 상태 · 서식 그대로. 통은 이 세션 칸에 조건
# 키로 몇 벌 기억한다(두 탭이 같이 쓴다). 시트 꼴이 바뀌면 판을 올린다 — 같은 조건의 옛 통이 세션에
# 남아 있어도 다시 짓는다.
SHEET_MEMO_KEY = "calculation_result_sheet_memo"
SHEET_SCHEMA_VERSION = 1
UNIT_CAPACITY_XLSX_KEY = "download_unit_capacity_xlsx"
REQUIRED_DETAIL_XLSX_KEY = "download_required_equipment_detail_xlsx"
REQUIRED_SUMMARY_XLSX_KEY = "download_required_equipment_summary_xlsx"
# 소요대수 탭 `표 조건` 카드 거름의 key 앞부분(`column_filter_key`).
REQUIRED_FILTER_PREFIX = "required_equipment_filter"


def _required_export_csv(table: pd.DataFrame, classification_columns: list[str]) -> bytes:
    """소요대수 표의 내려받기 CSV 바이트(소수 둘째 자리). 화면 표와 같은 분류로 만든다."""
    export = build_hierarchical_monthly_export(
        table,
        classification_columns=classification_columns,
        column_labels=COLUMN_LABELS,
        decimal_places=2,
    )
    return export.to_csv(index=False, float_format="%.2f").encode("utf-8-sig")


def _required_filter_rows(
    view_table: pd.DataFrame, dimensions: list[str], labels: ProcessLabels
) -> tuple[tuple[str, str], ...]:
    """소요대수 시트 머리 값의 거름 줄 — 공용 공정 칸(늘 한 줄, 걸리지 않으면 「전체」)과 `표 조건`
    카드에서 값을 고른 칸마다 한 줄(사이드바에 보이는 글자 그대로)."""
    rows: list[tuple[str, str]] = []
    if "공정" in view_table.columns:
        applied = shared_process.applied(view_table["공정"].dropna().drop_duplicates())
        rows.append(("공정", process_filter_text(applied, labels.label)))
    for column in dimensions:
        if column == "공정":
            continue
        chosen = st.session_state.get(column_filter_key(REQUIRED_FILTER_PREFIX, column))
        if isinstance(chosen, list) and chosen:
            rows.append((COLUMN_LABELS.get(column, column), " · ".join(str(v) for v in chosen)))
    return tuple(rows)


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
    # 대당 Capa·소요대수 프레임(pickle 약 11MB, 합성 표본의 샘플 관측)은 풀지 않는다. 탭과 무관하게
    # 쓰는 작은 값은 요약 캐시에서, 표는 키 전용 캐시에서 꺼낸다 — 빗나갈 때만 그 캐시가 안에서
    # 프레임을 받는다. 계산 오류는 요약 캐시가 이 자리에서 「계산 멈춤」과 함께 먼저 드러낸다.
    display_order_key = display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])
    summary = stop_calculation_on_error(
        get_scenario_result_summary,
        capacity_cache_key,
        _scenario_tables=active_scenario["tables"],
        _reference_tables=reference_tables,
    )
    capacity_exclusions = summary.capacity_exclusions
    assumptions = summary.capacity_assumptions
    required_exclusions = summary.required_exclusions
    # 판정 기준은 HOME 설정 → 판정 기준 탭의 **공용 프로필**이다. 이 페이지는 위젯을 두지 않고
    # HOME·Static Capa 와 같은 기준을 읽는다 — 같은 확보율이 화면마다 다른 색으로 보이면 안 된다.
    threshold_profile = load_global_securement_threshold(str(DUCKDB_PATH.resolve()))
except BOOTSTRAP_ERRORS as exc:
    # 패널의 공정 줄은 계산 뒤에야 채워진다. 멈춘 회차에도 잠긴 줄로 자리를 지켜 패널 높이가
    # 회차마다 흔들리지 않게 한다(HOME 과 같은 꼴 — 검수 보드 p-stop-row).
    render_stopped_process_field()
    # 원인 하나의 마크를 세 탭에 같이 세우고, 글은 탭 밖에서 알림으로 한 번 보낸다.
    for error_tab in (unit_capacity_tab, required_tab, availability_tab):
        with error_tab:
            render_data_error_mark()
    stop = calculation_stop_notice(exc)
    alert_page_error(
        bootstrap_error_message(exc) if stop is None else stop.message,
        code="ST-20",
        text=None if stop is None else stop.text,
        goto=None if stop is None else stop.goto,
    )
else:
    # 상태 알림의 범위 — 이 화면의 결과는 유효 조회기간 키로 계산한 것이다(측정률 가정만 시나리오
    # 전체 기준이라 기간을 넣지 않는다 — HOME 과 같은 범위).
    period_scope = simulation_scope(active_scenario, (effective_start, effective_end))
    # 탭마다의 몫(월별 표·제외 안내·CSV·Plotly)은 **열린 탭에서만** 만든다. 소요대수 월 표와
    # 확보율 표도 그 탭이 열린 회차에만 캐시에서 꺼낸다 — 다른 탭을 보는 동안에는 쓰지 않는다.
    # 그 표의 오류는 그 탭에만 뜬다(시나리오 계산 오류는 위 요약 캐시가 세 탭에 낸다).
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
    # 표시순서 스코프 문자열은 DB 공용 프로필의 행 키다. 페이지 이름이 바뀌어도 **이 인자는
    # 그대로 둔다** — 안 맞으면 예외가 아니라 정렬이 조용히 사라진다.
    process_options = get_display_ordered_values(
        summary.processes,
        display_order_key,
        PAGE_CALCULATION,
        TAB_UNIT_CAPACITY,
        _display_order=display_order,
    )

    if open_tab is unit_capacity_tab:
        with table_card(CARD_NAME):
            # 표시 방식은 탭 안의 하위 보기지만 사용자 요청으로 카드 첫 칸이다(2026-11-02 사용자
            # 요청(검수표) — 「하위 보기 전환은 본문」 의 예외, AGENTS 9장). 아래 칸과 공정 값 칸이
            # 이 값을 따라 바뀌므로(집계 수준 잠금·공정 칸 글자) 그 위에 둔다. 탭 이름이 이미 `대당
            # Capa` 라 선택지에서는 그 낱말을 뺀다. 두 값은 집계 단위가 다른 것이지 다른 지표가
            # 아니다. 같은 카드의 「집계 수준」 처럼 다른 화면(탭)에 갔다 와도 남는다 — 하위 보기
            # 전환도 보기 조건이다(2026-10-24 사용자 결정).
            capacity_view = st.segmented_control(
                "표시 방식",
                options=["공정별", "STEP별"],
                default="공정별",
                key="unit_capacity_view_mode",
                persist_state="session",
                help=VIEW_MODE_HELP,
            )
            step_view = capacity_view == "STEP별"
            selected_level_label = st.selectbox(
                "집계 수준",
                options=list(CAPACITY_LEVEL_LABELS.values()),
                index=0,
                key="unit_capacity_detail_level",
                persist_state="session",
                disabled=step_view,
                # 칸 정체성은 key 라(Streamlit 1.63) 풍선이 바뀌어도 고른 값은 그대로다.
                help=LEVEL_LOCKED_HELP if step_view else None,
            )
        # 공용 공정 칸 — 값은 원본이라 아래 `isin` 이 원본 컬럼과 맞고, 글자만 표시명이다.
        selected_processes = render_process_filter(
            process_options,
            screen=SCREEN,
            labels=process_labels,
            empty=STEP_VIEW_PROCESS_EMPTY if step_view else None,
        )
        selected_level = next(
            level for level, label in CAPACITY_LEVEL_LABELS.items() if label == selected_level_label
        )
        with unit_capacity_tab:
            render_capacity_assumption_notice(
                assumptions, scope=simulation_scope(active_scenario), tab=UNIT_CAPACITY_TAB
            )
            exclusion_file = f"Capa_Unit_Capacity_Exclusions_{effective_start}_{effective_end}.csv"
            exclusion_table = (
                alert_table(
                    exclusion_export(
                        capacity_exclusions,
                        dimensions=UNIT_CAPACITY_DIMENSIONS,
                        display_order=display_order,
                        page=PAGE_CALCULATION,
                        tab=TAB_UNIT_CAPACITY,
                    ),
                    title=CAPACITY_EXCLUSION_TITLE,
                    file_name=exclusion_file,
                    labels=process_labels,
                )
                if not capacity_exclusions.empty
                else None
            )
            alert_capacity_exclusions(
                capacity_exclusions,
                scope=period_scope,
                tab=UNIT_CAPACITY_TAB,
                table=exclusion_table,
            )
            if exclusion_table is None and not capacity_exclusions.empty:
                # 알림에 싣기에 큰 목록만 본문 펼침으로 남는다. 닫힌 탭에서는 그리지 않으므로 편
                # 상태는 기억 칸이 지킨다(히트맵 상자와 같다).
                with remembered_expander(
                    f"{CAPACITY_EXCLUSION_TITLE} 확인", key=CAPACITY_EXCLUSIONS_EXPANDER_KEY
                ):
                    render_exclusion_table(
                        capacity_exclusions,
                        dimensions=UNIT_CAPACITY_DIMENSIONS,
                        display_order=display_order,
                        page=PAGE_CALCULATION,
                        tab=TAB_UNIT_CAPACITY,
                        labels=process_labels,
                        file_name=exclusion_file,
                        key="download_unit_capacity_exclusions_csv",
                    )
            # STEP 뷰는 경로 하나하나가 행이라 전 공정을 그리면 Plotly 표가 수천 행이 된다.
            # 미선택이면 표를 만들지도 CSV 로 인코딩하지도 않고 빈 결과 한 줄만 남긴다. 선택 해제를
            # 허용하는 컨트롤이라 `capacity_view` 는 None 일 수 있으므로 명시 비교로 판단한다.
            if step_view and not selected_processes:
                st.caption(STEP_VIEW_EMPTY)
            else:
                if step_view:
                    # 전 공정 STEP 월표(피벗·정렬·재배치)는 키 캐시다 — 공정 필터만 아래에서 건다.
                    unit_capacity_table, classification_columns = get_step_unit_capacity_table(
                        capacity_cache_key,
                        display_order_key,
                        PAGE_CALCULATION,
                        TAB_UNIT_CAPACITY,
                        _scenario_tables=active_scenario["tables"],
                        _reference_tables=reference_tables,
                        _display_order=display_order,
                    )
                    output_title = "STEP별 대당 Capa"
                    file_prefix = "Capa_Step_Unit_Capacity"
                else:
                    unit_capacity_table = get_effective_process_capacity_table(
                        capacity_cache_key,
                        _scenario_tables=active_scenario["tables"],
                        _reference_tables=reference_tables,
                        detail_level=selected_level,
                    )
                    classification_columns = [
                        column
                        for column in ["공정", "소요기준", *WEIGHTED_CAPACITY_HIERARCHY[1:]]
                        if column in unit_capacity_table.columns
                    ]
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
                    output_title = "공정별 대당 Capa"
                    file_prefix = "Capa_Effective_Process_Capacity"
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
                capacity_file = f"{file_prefix}_{selected_level}_{effective_start}_{effective_end}"
                # 시트 머리 값 — 머리 띠 시나리오 · 조회기간, 카드의 보기 · 수준, 공용 공정 거름.
                capacity_heading = (
                    *scenario_period_rows(
                        selected=(context.selected_start_month, context.selected_end_month),
                        applied=(effective_start, effective_end),
                    ),
                    ("표시 방식", "STEP별" if step_view else "공정별"),
                    *(() if step_view else (("집계 수준", selected_level_label),)),
                    ("공정", process_filter_text(selected_processes, process_labels.label)),
                )
                # 표는 (내용 토큰 · 기간 키, 표시순서 지문, 보기, 수준, 공정)이 정한다 — 큰 표는
                # 키에 넣지 않는다. 표시명 판 · 머리 값도 시트 글자를 바꾼다.
                capacity_sheet = SheetFile(
                    data=remembered_bytes(
                        SHEET_MEMO_KEY,
                        (
                            SHEET_SCHEMA_VERSION,
                            UNIT_CAPACITY_TAB,
                            capacity_cache_key,
                            display_order_key,
                            step_view,
                            selected_level,
                            tuple(selected_processes),
                            process_labels.version,
                            capacity_heading,
                        ),
                        partial(
                            monthly_table_workbook,
                            MonthlySheetRequest(
                                sheet_name=UNIT_CAPACITY_TAB,
                                title=output_title,
                                data=unit_capacity_table,
                                classification_columns=tuple(classification_columns),
                                column_labels=COLUMN_LABELS,
                                decimal_places=0,
                                heading=capacity_heading,
                                value_labels=process_labels.value_labels(),
                            ),
                        ),
                    ),
                    file_name=f"{capacity_file}.xlsx",
                    key=UNIT_CAPACITY_XLSX_KEY,
                )
                render_table_heading(
                    output_title,
                    csv=capacity_csv,
                    file_name=f"{capacity_file}.csv",
                    key="download_unit_capacity_csv",
                    sheet=capacity_sheet,
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
        try:
            required_table, required_detail_dimensions = get_required_month_table(
                capacity_cache_key,
                display_order_key,
                PAGE_CALCULATION,
                TAB_REQUIRED,
                _scenario_tables=active_scenario["tables"],
                _reference_tables=reference_tables,
                _display_order=display_order,
            )
        except BOOTSTRAP_ERRORS as exc:
            # 이 탭의 공정 칸은 표 뒤에 서므로 멈춘 회차에는 잠긴 줄로 자리를 지킨다(p-stop-row).
            render_stopped_process_field()
            with required_tab:
                render_data_error(bootstrap_error_message(exc), code="ST-20", tab=REQUIRED_TAB)
            st.stop()
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
                shared_screen=SCREEN,
            )
        with required_tab:
            # 대당 Capa 제외 표는 **대당 Capa 탭**의 알림이 든다. 두 탭이 한 페이지에 있게 된
            # 뒤로는 같은 표를 같은 파일명으로 두 번 내리는 것이라 여기서는 걷어냈다.
            # 사유가 둘이다 — 대당 Capa 가 없는 것(ST-15)은 기준정보를 고칠 일이고, PKG 의 Buffer
            # 밖 행(ST-21)은 규칙대로 세지 않은 것이다. 계획 쪽(ST-01)은 Static Capa 와 같은 코드 ·
            # 같은 범위다 — 어느 경로에도 붙지 못해 경로 쪽 목록에 없다. 셋 다 이 탭이 열린 회차마다
            # 부르고 목록은 각 줄의 표다. 싣기에 큰 목록만 본문 펼침으로 남는다.
            period_suffix = f"{effective_start}_{effective_end}"
            route_lists = alert_required_exclusions(
                required_exclusions,
                scope=period_scope,
                tab=REQUIRED_TAB,
                display_order=display_order,
                labels=process_labels,
                file_suffix=period_suffix,
            )
            plan_lists = plan_exclusion_lists(
                summary.load_exclusions,
                summary.unrouted_loads,
                display_order=display_order,
                labels=process_labels,
                file_suffix=period_suffix,
            )
            alert_uncounted_demand(
                plan_side_counts(
                    count_required_exclusions(
                        summary.load_exclusions, summary.unrouted_loads, required_exclusions
                    )
                ),
                code="ST-01",
                scope=period_scope,
                scope_name=PERIOD_SCOPE,
                lists=plan_lists,
                tab=REQUIRED_TAB,
            )
            render_oversized_lists(
                (*route_lists, *plan_lists), display_order=display_order, labels=process_labels
            )
            # 내보내기 표 조립·직렬화(합성 표본 상세 2,660행에서 약 70ms, 샘플 관측)는 표 내용
            # 지문 키 캐시다 — 내려받기를 누르지 않은 회차마다 다시 만들지 않는다. 필터·상세가
            # 바뀌면 키가 바뀐다.
            required_csv_key = csv_export_key(
                "required_equipment", filtered_required_table, table_dimensions, "2"
            )
            required_csv = get_export_csv(
                required_csv_key,
                _build=partial(_required_export_csv, filtered_required_table, table_dimensions),
            )
            required_view_name = "Detail" if show_detail else "Summary"
            required_file = (
                f"Capa_Required_Equipment_{required_view_name}_{effective_start}_{effective_end}"
            )
            required_heading = (
                *scenario_period_rows(
                    selected=(context.selected_start_month, context.selected_end_month),
                    applied=(effective_start, effective_end),
                ),
                ("상세", "켬" if show_detail else "끔"),
                *_required_filter_rows(view_table, table_dimensions, process_labels),
            )
            # 표는 CSV 키의 내용 지문(거름 · 상세 · 표시순서가 다 든다)이 정한다.
            required_sheet = SheetFile(
                data=remembered_bytes(
                    SHEET_MEMO_KEY,
                    (
                        SHEET_SCHEMA_VERSION,
                        REQUIRED_TAB,
                        required_csv_key,
                        process_labels.version,
                        required_heading,
                    ),
                    partial(
                        monthly_table_workbook,
                        MonthlySheetRequest(
                            sheet_name=REQUIRED_TAB,
                            title="소요대수",
                            data=filtered_required_table,
                            classification_columns=tuple(table_dimensions),
                            column_labels=COLUMN_LABELS,
                            decimal_places=2,
                            heading=required_heading,
                            value_labels=process_labels.value_labels(),
                        ),
                    ),
                ),
                file_name=f"{required_file}.xlsx",
                key=REQUIRED_DETAIL_XLSX_KEY if show_detail else REQUIRED_SUMMARY_XLSX_KEY,
            )
            with table_heading_row(
                "소요대수",
                csv=required_csv,
                file_name=f"{required_file}.csv",
                key=(
                    "download_required_equipment_detail_csv"
                    if show_detail
                    else "download_required_equipment_summary_csv"
                ),
                sheet=required_sheet,
            ):
                page_slot = st.container(width="content")
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
                page_slot=page_slot,
                owner_tab=required_tab,
            )

    if open_tab is availability_tab:
        try:
            securement_rate = get_scenario_securement_rate(
                capacity_cache_key,
                _scenario_tables=active_scenario["tables"],
                _reference_tables=reference_tables,
                _available_equipment=available_equipment,
            )
            securement_table = apply_display_order(
                securement_rate_to_month_table(securement_rate),
                display_order,
                PAGE_CALCULATION,
                TAB_SECUREMENT,
            )
        except BOOTSTRAP_ERRORS as exc:
            render_stopped_process_field()
            with availability_tab:
                render_data_error(bootstrap_error_message(exc), code="ST-20", tab=AVAILABILITY_TAB)
            st.stop()
        # 히트맵은 칸마다 **그 달의** 실효 기준으로 판정한다(월별 예외가 없으면 기본값).
        thresholds = threshold_profile.thresholds
        # 거르는 칸이 공정 하나라 카드를 세우지 않는다 — 공정은 조회 조건 패널의 공용 공정 칸이다.
        displayed_securement_table = render_shared_process_filter(
            securement_table, screen=SCREEN, labels=process_labels
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
            # 표는 숫자를 답하고 히트맵은 모양을 답한다. 「어느 공정이 **언제** 무너지나」는
            # 66행을 훑어서 알 것이 아니다. 행은 **위 표와 같다**(조회 조건의 공정) — 따로 고르는
            # 목록을 두지 않는다(2026-10-06 사용자 결정).
            # 편 상자는 다른 탭에 갔다 와도 편 채다. 닫힌 탭의 본문은 그리지 않으므로 `key` 없는
            # 상자는 돌아올 때 새로 만들어져 접혔다(2026-10-01 브라우저 점검).
            with remembered_expander("히트맵", key=HEATMAP_EXPANDER_KEY):
                render_securement_heatmap(
                    displayed_securement_table,
                    dimension_columns=SECUREMENT_DIMENSIONS,
                    thresholds=thresholds,
                    key="securement_rate_heatmap",
                    labels=process_labels,
                    owner_tab=availability_tab,
                )
