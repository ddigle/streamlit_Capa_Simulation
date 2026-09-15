# Purpose: 설비 마스터·비가동 이력을 편집하고 주차별 가용설비 및 변경 리비전 대시보드를 제공한다.

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_lifecycle_gantt import (
    render_equipment_lifecycle_gantt,
)
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.status_metric import (
    metric_row,
    render_status_metric,
    shortage_tone,
)
from capa_simulation.components.table_toolbar import CSV_TEMPLATE_LABEL, render_csv_download
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_snapshot_cache,
    get_equipment_repository,
    load_equipment_snapshot,
    load_floor_layout_canvases,
    load_latest_equipment_snapshot,
)
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_inactive_equipment,
)
from capa_simulation.services.equipment_contract import (
    DATE_COLUMNS,
    DOWNTIME_TYPES,
    EQUIPMENT_STATUSES,
    QUAL_CONFIRMATION_STATUSES,
    STATUS_COUNT_COLUMNS,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.services.equipment_csv import (
    baseline_csv_template,
    build_baseline_import_preview,
    build_downtime_import_preview,
    build_equipment_import_preview,
    downtime_csv_template,
    equipment_csv_template,
    merge_baseline_rows,
    merge_downtime_rows,
    merge_equipment_rows,
    read_baseline_clipboard,
    read_downtime_clipboard,
    read_equipment_clipboard,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
    untouched_sample_baseline_rows,
)
from capa_simulation.services.floor_layout_profile import max_canvas_extent
from capa_simulation.services.simulation_cache import get_weekly_equipment_availability
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

FLASH_KEY = "equipment_status_flash"
BASELINE_EDITOR_KEY = "equipment_baseline_editor_v3"
EQUIPMENT_EDITOR_KEY = "equipment_master_editor_v3"
DOWNTIME_EDITOR_KEY = "equipment_downtime_editor_v3"
BASELINE_DRAFT_KEY = "equipment_baseline_draft_v3"
EQUIPMENT_DRAFT_KEY = "equipment_master_draft_v3"
DOWNTIME_DRAFT_KEY = "equipment_downtime_draft_v3"
DRAFT_REVISION_KEY = "equipment_draft_revision_v4"
BASELINE_IMPORT_KEY = "baseline_import_preview_rows_v3"
EQUIPMENT_IMPORT_KEY = "equipment_import_preview_rows_v3"
DOWNTIME_IMPORT_KEY = "downtime_import_preview_rows_v3"


def _filter_equipment(
    data: pd.DataFrame,
    *,
    line_types: list[str],
    utilization_types: list[str],
    large_processes: list[str],
    small_processes: list[str],
) -> pd.DataFrame:
    filtered = data
    for column, selected_values in (
        ("라인구분", line_types),
        ("활용구분", utilization_types),
        ("공정대분류", large_processes),
        ("공정소분류", small_processes),
    ):
        if selected_values:
            filtered = filtered.loc[filtered[column].isin(selected_values)]
    return filtered.copy()


def _filter_options(data: pd.DataFrame, column: str) -> list[str]:
    return sorted(data[column].dropna().astype(str).unique().tolist())


def _downtime_for_equipment(downtime: pd.DataFrame, equipment: pd.DataFrame) -> pd.DataFrame:
    return downtime.loc[downtime["호기"].isin(equipment["호기"])].copy()


def _reset_drafts() -> None:
    for key in (
        BASELINE_EDITOR_KEY,
        EQUIPMENT_EDITOR_KEY,
        DOWNTIME_EDITOR_KEY,
        BASELINE_DRAFT_KEY,
        EQUIPMENT_DRAFT_KEY,
        DOWNTIME_DRAFT_KEY,
        DRAFT_REVISION_KEY,
        BASELINE_IMPORT_KEY,
        EQUIPMENT_IMPORT_KEY,
        DOWNTIME_IMPORT_KEY,
    ):
        st.session_state.pop(key, None)


def _import_summary(preview: pd.DataFrame) -> None:
    with st.container(horizontal=True):
        st.metric("Import 행", f"{len(preview):,}건", border=True)
        st.metric("신규", f"{int(preview['Import구분'].eq('신규').sum()):,}건", border=True)
        st.metric(
            "기존 대체",
            f"{int(preview['Import구분'].eq('대체').sum()):,}건",
            border=True,
        )


def _equipment_status_scale() -> alt.Scale:
    """설비 상태 9종에 고정 색을 준다.

    scale 을 생략하면 Altair 가 config.toml 의 chartCategoricalColors 4색을 순환해
    5~9번째 상태가 앞의 것과 같은 색으로 그려진다.
    """
    return alt.Scale(
        domain=list(tokens.EQUIPMENT_STAGE_COLORS),
        range=list(tokens.EQUIPMENT_STAGE_COLORS.values()),
    )


def _qual_status_scale() -> alt.Scale:
    """Qual 확정상태 4종에 고정 색을 준다."""
    return alt.Scale(
        domain=list(tokens.QUAL_CONFIRMATION_COLORS),
        range=list(tokens.QUAL_CONFIRMATION_COLORS.values()),
    )


def _format_equipment_count(value: float) -> str:
    """대수를 적는다. 주중에 상태가 바뀌면 소수가 나오므로 정수일 때만 소수점을 뗀다.

    설비 751대를 "751.0대" 로 적으면 계산이 어긋난 것처럼 읽힌다.
    """
    return f"{value:,.0f}대" if float(value).is_integer() else f"{value:,.1f}대"


render_page_header(
    "가용설비 현황 (Data확보중)",
    description=(
        "기존 보유대수와 31개 컬럼 호기 마스터, 운영 비가동 일정을 설비 전용 DuckDB "
        "불변 리비전으로 관리합니다."
    ),
)
flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    st.success(flash)

today = date.today()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    repository = get_equipment_repository(equipment_database_path)
    # 층마다 캔버스가 달라 편집기 상한은 전 층 최댓값으로 열어 두고, 층별 범위는 붙여넣기·
    # 저장 시점에 호기 마스터 검증이 잡는다.
    floor_canvases = load_floor_layout_canvases(equipment_database_path)
    max_canvas_width, max_canvas_height = max_canvas_extent(floor_canvases)
    latest_snapshot = load_latest_equipment_snapshot(equipment_database_path)
    if latest_snapshot is None:
        saved_baseline = sample_equipment_baseline()
        saved_equipment = empty_equipment_master()
        saved_downtime = empty_downtime_schedule()
        revision_token = "empty"
    else:
        saved_baseline = latest_snapshot.baseline
        saved_equipment = latest_snapshot.equipment
        saved_downtime = latest_snapshot.downtime
        revision_token = latest_snapshot.revision.revision_id
except BOOTSTRAP_ERRORS as exc:
    st.error(f"설비 현황을 준비하지 못했습니다: {bootstrap_error_message(exc)}")
    st.stop()

if st.session_state.get(DRAFT_REVISION_KEY) != revision_token:
    st.session_state[BASELINE_DRAFT_KEY] = saved_baseline.copy()
    st.session_state[EQUIPMENT_DRAFT_KEY] = saved_equipment.copy()
    st.session_state[DOWNTIME_DRAFT_KEY] = saved_downtime.copy()
    st.session_state[DRAFT_REVISION_KEY] = revision_token
    st.session_state.pop(BASELINE_IMPORT_KEY, None)
    st.session_state.pop(EQUIPMENT_IMPORT_KEY, None)
    st.session_state.pop(DOWNTIME_IMPORT_KEY, None)
# 세 표 모두 편집본을 본다. 대시보드가 저장본만 보면 붙여넣기 직후 기존 보유대수만
# 옛 값으로 남아 총대수·가용률이 호기 마스터와 어긋난다.
baseline = st.session_state[BASELINE_DRAFT_KEY].copy()
equipment = st.session_state[EQUIPMENT_DRAFT_KEY].copy()
downtime = st.session_state[DOWNTIME_DRAFT_KEY].copy()
using_dashboard_sample = equipment.empty
dashboard_equipment = (
    sample_equipment_master(anchor_date=today) if using_dashboard_sample else equipment
)
dashboard_downtime = (
    sample_downtime_schedule(anchor_date=today) if using_dashboard_sample else downtime
)

with st.container(border=True):
    st.markdown("#### :material/date_range: 조회기간 설정")
    st.caption(
        "가용설비 현황에만 적용되는 월요일 시작 ISO Weeknum 조회기간입니다. "
        "주차 값은 각 주 일요일 종료 시점의 상태입니다."
    )
    with st.container(horizontal=True, gap="small"):
        start_date = st.date_input(
            "시작일",
            value=date(today.year, today.month, 1),
            key="equipment_dashboard_start_date",
            persist_state="session",
            width=180,
        )
        end_date = st.date_input(
            "종료일",
            value=today + timedelta(weeks=12),
            key="equipment_dashboard_end_date",
            persist_state="session",
            width=180,
        )

dashboard_tab, management_tab = st.tabs(["대시보드", "설비 데이터·이력 관리"])

with dashboard_tab:
    if using_dashboard_sample:
        st.info(
            "호기 마스터가 비어 있어 입고 예정부터 운영 비가동까지 상태별 임시 샘플 "
            "7대를 표시합니다. 샘플은 DuckDB에 저장되지 않습니다.",
            icon=":material/science:",
        )
    elif latest_snapshot is not None:
        st.caption(
            f"현재 적용 이력: r{latest_snapshot.revision.revision_no} · "
            f"{latest_snapshot.revision.created_at:%Y-%m-%d %H:%M}"
        )

    small_process_options = sorted(
        set(_filter_options(dashboard_equipment, "공정소분류"))
        | set(baseline["공정"].dropna().astype(str).unique().tolist())
    )
    with st.container(border=True):
        st.markdown("#### :material/filter_alt: 조회 조건")
        with st.container(horizontal=True, gap="small"):
            selected_line_types = st.multiselect(
                "라인구분",
                options=_filter_options(dashboard_equipment, "라인구분"),
                placeholder="전체",
                key="equipment_dashboard_line_types",
                persist_state="session",
                width=220,
            )
            selected_utilization_types = st.multiselect(
                "활용구분",
                options=_filter_options(dashboard_equipment, "활용구분"),
                placeholder="전체",
                key="equipment_dashboard_utilization_types",
                persist_state="session",
                width=220,
            )
            selected_large_processes = st.multiselect(
                "공정대분류",
                options=_filter_options(dashboard_equipment, "공정대분류"),
                placeholder="전체",
                key="equipment_dashboard_large_processes",
                persist_state="session",
                width=260,
            )
            selected_small_processes = st.multiselect(
                "공정소분류",
                options=small_process_options,
                placeholder="전체",
                key="equipment_dashboard_small_processes",
                persist_state="session",
                width=300,
            )
        st.caption(
            "기존 보유대수에는 라인·활용·공정대분류 정보가 없으므로 공정소분류 조건만 "
            "적용되고, 나머지 조건은 호기 마스터 설비에 적용됩니다."
        )

    filtered_equipment = _filter_equipment(
        dashboard_equipment,
        line_types=selected_line_types,
        utilization_types=selected_utilization_types,
        large_processes=selected_large_processes,
        small_processes=selected_small_processes,
    )
    filtered_downtime = _downtime_for_equipment(dashboard_downtime, filtered_equipment)
    filtered_baseline = baseline.copy()
    if selected_small_processes:
        filtered_baseline = filtered_baseline.loc[
            filtered_baseline["공정"].isin(selected_small_processes)
        ].copy()

    if start_date > end_date:
        st.error("설비 대시보드 시작일은 종료일보다 늦을 수 없습니다.")
        weekly = pd.DataFrame()
    else:
        try:
            weekly = get_weekly_equipment_availability(
                filtered_baseline,
                filtered_equipment,
                filtered_downtime,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError as exc:
            st.error(str(exc))
            weekly = pd.DataFrame()

    if weekly.empty and start_date <= end_date:
        st.info("집계할 기존 보유대수 또는 호기 마스터가 없습니다.")
    elif not weekly.empty:
        filtered_weekly = weekly.copy()
        latest_week_start = filtered_weekly["주차시작일"].max()
        latest_week = filtered_weekly.loc[filtered_weekly["주차시작일"].eq(latest_week_start)]
        latest_week_end = latest_week["주차종료일"].max()
        total_count = float(latest_week["총대수"].sum())
        available_count = float(latest_week["가용대수"].sum())
        inactive_count = float(latest_week["비가동대수"].sum())
        trend = (
            filtered_weekly.groupby(["주차시작일", "Weeknum"], as_index=False)[
                ["가용대수", "비가동대수"]
            ]
            .sum()
            .sort_values("주차시작일")
        )
        # 카드마다 자기 주차 추이를 스파크라인으로 함께 보여준다. 마지막 주 값만으로는
        # 늘고 있는지 줄고 있는지 알 수 없어 아래 차트를 열어야 했다. 네 장 모두에 넣어야
        # 카드 높이가 어긋나지 않는다.
        weekly_total = trend["가용대수"] + trend["비가동대수"]
        weekly_rate = (trend["가용대수"] / weekly_total.where(weekly_total.ne(0))).fillna(0.0)
        st.caption(f"조회 마지막 주 기준 · {latest_week['Weeknum'].iloc[0]}")
        with metric_row(key="equipment_weekly_metrics"):
            st.metric(
                "총대수",
                _format_equipment_count(total_count),
                chart_data=weekly_total,
                chart_type="area",
                border=True,
            )
            st.metric(
                "가용대수",
                _format_equipment_count(available_count),
                chart_data=trend["가용대수"],
                chart_type="area",
                border=True,
            )
            render_status_metric(
                "비가동대수",
                _format_equipment_count(inactive_count),
                key="equipment_inactive_count",
                tone=shortage_tone(int(inactive_count > 0)),
                chart_data=trend["비가동대수"],
            )
            st.metric(
                "가용률",
                f"{available_count / total_count if total_count else 0:.1%}",
                chart_data=weekly_rate,
                chart_type="area",
                border=True,
            )
        trend_long = trend.melt(
            id_vars=["주차시작일", "Weeknum"],
            value_vars=["가용대수", "비가동대수"],
            var_name="상태",
            value_name="대수",
        )
        with st.container(border=True):
            st.markdown("#### 주차별 설비 현황")
            chart = (
                alt.Chart(trend_long)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Weeknum:N",
                        sort=trend["Weeknum"].tolist(),
                        axis=alt.Axis(title=None, labelAngle=0, labelFontSize=14),
                    ),
                    y=alt.Y(
                        "sum(대수):Q",
                        stack="zero",
                        axis=alt.Axis(title=None, labelFontSize=14),
                    ),
                    color=alt.Color(
                        "상태:N",
                        scale=_equipment_status_scale(),
                        legend=alt.Legend(title=None, labelFontSize=14),
                    ),
                    tooltip=(
                        alt.Tooltip("Weeknum:N", title="Weeknum"),
                        alt.Tooltip("상태:N", title="상태"),
                        alt.Tooltip("대수:Q", title="대수", format=".1f"),
                    ),
                )
                .properties(height=360)
            )
            st.altair_chart(chart, width="stretch")

        unit_status = build_equipment_status_as_of(
            filtered_equipment, filtered_downtime, as_of=latest_week_end
        )
        status_counts = (
            unit_status["상태"]
            .value_counts()
            .reindex(EQUIPMENT_STATUSES, fill_value=0)
            .rename_axis("상태")
            .rename("호기대수")
            .reset_index()
        )
        with st.container(border=True):
            st.markdown("#### 호기 생애주기 상태 모니터링")
            st.caption(
                "상태는 호기별로 하나만 부여합니다. 반출·이설 예정 호기는 실행일 전까지 "
                "보유·가용 산정에 포함되며, 기존 보유대수 집계는 호기 상태에서 제외됩니다."
            )
            status_chart = (
                alt.Chart(status_counts)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    y=alt.Y(
                        "상태:N",
                        sort=list(EQUIPMENT_STATUSES),
                        axis=alt.Axis(title=None, labelFontSize=13),
                    ),
                    x=alt.X(
                        "호기대수:Q",
                        axis=alt.Axis(title=None, tickMinStep=1, labelFontSize=13),
                    ),
                    color=alt.Color("상태:N", scale=_equipment_status_scale(), legend=None),
                    tooltip=("상태:N", "호기대수:Q"),
                )
                .properties(height=300)
            )
            st.altair_chart(status_chart, width="stretch")
            st.dataframe(status_counts, hide_index=True, width="stretch")

        with st.container(border=True):
            st.markdown("#### 호기별 생애주기 일정")
            st.caption(
                "위 막대가 「지금 몇 대가 어느 상태인가」를 답한다면 이 그림은 「언제 몇 "
                "대가 쓸 수 있게 되는가」를 답합니다. 날짜 컬럼은 점이라 표로는 그 사이 "
                "간격이 보이지 않습니다. 구간 판정은 상태 막대와 같은 규칙입니다."
            )
            try:
                lifecycle_spans = build_equipment_lifecycle_spans(
                    filtered_equipment,
                    filtered_downtime,
                    start_date=start_date,
                    end_date=end_date,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                render_equipment_lifecycle_gantt(
                    lifecycle_spans,
                    key="equipment_lifecycle_gantt",
                    today=today,
                )

        qual_execution = unit_status.loc[unit_status["Qual일정"].notna()].copy()
        confirmation_counts = (
            qual_execution["확정상태"]
            .value_counts()
            .reindex(QUAL_CONFIRMATION_STATUSES, fill_value=0)
            .rename_axis("확정상태")
            .rename("호기대수")
            .reset_index()
        )
        with st.container(border=True):
            st.markdown("#### Qual 확정상태 실행관리")
            st.caption(
                "확정상태는 Qual 일정의 계획·확정·완료·지연만 관리합니다. "
                "가용대수는 기존 규칙대로 Qual일정을 기준으로 계산합니다."
            )
            with metric_row(key="equipment_qual_confirmation_metrics"):
                st.metric("Qual 대상", f"{len(qual_execution):,}대", border=True)
                for confirmation_status in QUAL_CONFIRMATION_STATUSES:
                    count = int(
                        confirmation_counts.loc[
                            confirmation_counts["확정상태"].eq(confirmation_status),
                            "호기대수",
                        ].sum()
                    )
                    st.metric(confirmation_status, f"{count:,}대", border=True)
            confirmation_chart = (
                alt.Chart(confirmation_counts)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    y=alt.Y(
                        "확정상태:N",
                        sort=list(QUAL_CONFIRMATION_STATUSES),
                        axis=alt.Axis(title=None, labelFontSize=13),
                    ),
                    x=alt.X(
                        "호기대수:Q",
                        axis=alt.Axis(title=None, tickMinStep=1, labelFontSize=13),
                    ),
                    color=alt.Color("확정상태:N", scale=_qual_status_scale(), legend=None),
                    tooltip=("확정상태:N", "호기대수:Q"),
                )
                .properties(height=180)
            )
            st.altair_chart(confirmation_chart, width="stretch")
            if not qual_execution.empty:
                st.dataframe(
                    qual_execution.loc[
                        :,
                        [
                            "호기",
                            "공정대분류",
                            "공정소분류",
                            "Qual일정",
                            "확정상태",
                            "상태",
                        ],
                    ].sort_values(["Qual일정", "호기"]),
                    hide_index=True,
                    width="stretch",
                    column_config={"Qual일정": st.column_config.DateColumn(format="YYYY-MM-DD")},
                )

        breakdown_columns = (
            "공정소분류",
            "기존보유대수",
            "추가설비대수",
            "총대수",
            "가용대수",
            "비가동대수",
            *STATUS_COUNT_COLUMNS.values(),
        )
        with st.container(border=True):
            st.markdown("#### 공정소분류별 현황")
            st.dataframe(
                latest_week.loc[:, breakdown_columns].sort_values(
                    ["비가동대수", "공정소분류"], ascending=[False, True]
                ),
                hide_index=True,
                width="stretch",
            )

        inactive_equipment = build_inactive_equipment(
            filtered_equipment, filtered_downtime, as_of=latest_week_end
        )
        with st.container(border=True):
            st.markdown("#### 비가동 설비호기")
            st.caption(
                f"{latest_week_end:%Y-%m-%d} 기준 보유 중이지만 가용이 아닌 "
                "셋업·보관·운영 비가동 호기입니다."
            )
            if inactive_equipment.empty:
                st.success("해당 주차에 비가동 설비호기가 없습니다.")
            else:
                st.dataframe(
                    inactive_equipment,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
                        for column in DATE_COLUMNS
                    },
                )

with management_tab:
    if latest_snapshot is None:
        st.info(
            "기존 보유대수 샘플은 유지하고 호기 마스터·비가동 일정은 빈 상태입니다. "
            "웹에서 행을 추가하거나 Excel 표를 붙여넣은 뒤 첫 리비전을 저장하세요."
        )
    else:
        st.caption(
            f"최근 저장본 r{latest_snapshot.revision.revision_no}을 편집합니다. "
            "저장하면 세 입력 전체가 새 불변 리비전으로 보관됩니다."
        )

    with st.expander("운영 지침", icon=":material/menu_book:", expanded=False):
        st.markdown(
            """
#### 입력 데이터 구분

- **기존 보유대수**: 호기별 일정·상태를 관리할 필요가 없는 오래된 가동설비를
  `공정소분류별 집계 대수`로 관리합니다. 전 조회기간에 보유·가용 설비로 반영됩니다.
- **호기 마스터**: 입고·Qual 일정, Qual 확정상태, 반출·이설, 개별 비가동 또는
  Space 배치를 관리할 설비를 호기별로 등록합니다. 오래된 설비라도 개별 관리가 필요하면
  호기 마스터에 등록하고 `기존설비여부=Y`로 지정합니다.
- **비가동 일정**: 호기 마스터에 등록된 설비의 개발대여·공사·고장·이설 기간을
  호기별로 관리합니다.

#### 운영 절차

1. 웹에서 직접 행을 편집하거나 기존 보유대수·호기 마스터·비가동 일정 Excel 표를
   붙여넣습니다.
2. 붙여넣기 Import 시 신규·대체 행과 변경 컬럼을 미리 확인합니다.
3. `확인 후 편집본에 적용`으로 현재 편집본에 반영합니다.
4. 하단의 `설비 데이터 저장`을 눌러야 DuckDB에 새 불변 리비전으로 영구 저장됩니다.

#### 적용 시 유의사항

- 기존 보유대수에는 호기명이 없으므로 개별 비가동 일정과 Space 배치를 적용할 수 없습니다.
- 일반 신규 설비는 입고일정·Qual일정·확정상태가 필요합니다.
- 가용대수는 Qual일정을 기준으로 계산하며, 확정상태는 Qual 실행 모니터링에만 사용합니다.
- Space 표시는 `레이아웃표시=Y`와 동·층·X/Y좌표·X/Ysize 입력이 필요합니다.
- 설비 운영 가용대수는 현재 시뮬레이션 Capa 산출 데이터와 분리되어 있습니다.
            """
        )

    with st.expander("상태 판정 기준", icon=":material/rule:", expanded=False):
        st.markdown(
            """
- **입고 예정**: 입고일정 전이며, 제진대·물류 일정도 이 상태의 선행 일정으로 관리
- **셋업 진행중**: 입고일정 이상, Qual일정 미만
- **가용**: Qual일정 이상 또는 기존설비 Y
- **확정상태**: Qual 일정만 계획·확정·완료·지연으로 실행관리하며 가용 판정에는 미사용
- **반출 예정 / 이설 예정**: 일정이 등록됐고 실행일 전
- **보관 설비**: 장기보관여부 Y
- **운영 비가동**: 개발대여·공사·고장·이설 등 비가동 일정 활성
- **반출 완료 / 이설 완료**: 실행일부터 보유·가용·레이아웃에서 제외
            """
        )

    with st.container(border=True):
        st.markdown("#### :material/content_paste: Excel 붙여넣기 Import 미리보기")
        st.caption(
            "기존 보유대수는 공정 + 분류, 호기 마스터는 호기, 비가동 일정은 호기 + "
            "비가동유형 + 시작일을 중복 구분자로 사용합니다. CSV 양식을 Excel에서 열어 "
            "수정한 뒤 헤더를 포함한 전체 표를 복사해 붙여넣으세요. 화면 표시 이름이 아니라 "
            "양식의 헤더를 그대로 써야 하며, 기존 보유대수는 쉼표 없는 숫자로 적습니다. "
            "신규/대체 행과 변경 컬럼을 확인한 뒤 편집본에 적용하며, 실제 DuckDB 저장은 "
            "아래 저장 버튼에서 한 번 더 수행합니다."
        )
        baseline_import_col, equipment_import_col, downtime_import_col = st.columns(3)
        with baseline_import_col:
            baseline_clipboard = st.text_area(
                "기존 보유대수 표 붙여넣기",
                key="equipment_baseline_clipboard_v4",
                height=220,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
            )
            with st.container(horizontal=True):
                render_csv_download(
                    data=baseline_csv_template(),
                    file_name="equipment_baseline_template.csv",
                    key="equipment_baseline_template_download_v3",
                    label=CSV_TEMPLATE_LABEL,
                )
                preview_baseline_import = st.button(
                    "미리보기",
                    icon=":material/preview:",
                    disabled=not baseline_clipboard.strip(),
                    key="equipment_baseline_clipboard_preview_v4",
                )
        with equipment_import_col:
            equipment_clipboard = st.text_area(
                "호기 마스터 표 붙여넣기",
                key="equipment_master_clipboard_v4",
                height=220,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
            )
            with st.container(horizontal=True):
                render_csv_download(
                    data=equipment_csv_template(),
                    file_name="equipment_master_template.csv",
                    key="equipment_master_template_download_v3",
                    label=CSV_TEMPLATE_LABEL,
                )
                preview_equipment_import = st.button(
                    "미리보기",
                    icon=":material/preview:",
                    disabled=not equipment_clipboard.strip(),
                    key="equipment_master_clipboard_preview_v4",
                )
        with downtime_import_col:
            downtime_clipboard = st.text_area(
                "비가동 일정 표 붙여넣기",
                key="equipment_downtime_clipboard_v4",
                height=220,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
            )
            with st.container(horizontal=True):
                render_csv_download(
                    data=downtime_csv_template(),
                    file_name="equipment_downtime_template.csv",
                    key="equipment_downtime_template_download_v3",
                    label=CSV_TEMPLATE_LABEL,
                )
                preview_downtime_import = st.button(
                    "미리보기",
                    icon=":material/preview:",
                    disabled=not downtime_clipboard.strip(),
                    key="equipment_downtime_clipboard_preview_v4",
                )

        if preview_baseline_import:
            try:
                incoming = read_baseline_clipboard(baseline_clipboard)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[BASELINE_IMPORT_KEY] = incoming
                st.session_state.pop(EQUIPMENT_IMPORT_KEY, None)
                st.session_state.pop(DOWNTIME_IMPORT_KEY, None)
                st.rerun()
        if preview_equipment_import:
            try:
                incoming = read_equipment_clipboard(
                    equipment_clipboard, floor_canvases=floor_canvases
                )
                merged = merge_equipment_rows(equipment, incoming, floor_canvases=floor_canvases)
                merge_downtime_rows(downtime, empty_downtime_schedule(), equipment=merged)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[EQUIPMENT_IMPORT_KEY] = incoming
                st.session_state.pop(BASELINE_IMPORT_KEY, None)
                st.session_state.pop(DOWNTIME_IMPORT_KEY, None)
                st.rerun()
        if preview_downtime_import:
            try:
                incoming = read_downtime_clipboard(downtime_clipboard, equipment=equipment)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[DOWNTIME_IMPORT_KEY] = incoming
                st.session_state.pop(BASELINE_IMPORT_KEY, None)
                st.session_state.pop(EQUIPMENT_IMPORT_KEY, None)
                st.rerun()

        incoming_baseline = st.session_state.get(BASELINE_IMPORT_KEY)
        if isinstance(incoming_baseline, pd.DataFrame):
            st.markdown("**기존 보유대수 Import 확인**")
            baseline_preview = build_baseline_import_preview(baseline, incoming_baseline)
            _import_summary(baseline_preview)
            st.dataframe(baseline_preview, hide_index=True, width="stretch")
            with st.container(horizontal=True):
                confirm = st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_baseline_import_v3",
                )
                cancel = st.button("취소", icon=":material/close:", key="cancel_baseline_import_v3")
            if confirm:
                try:
                    merged_baseline = merge_baseline_rows(baseline, incoming_baseline)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state[BASELINE_DRAFT_KEY] = merged_baseline
                    st.session_state.pop(BASELINE_EDITOR_KEY, None)
                    st.session_state.pop(BASELINE_IMPORT_KEY, None)
                    st.session_state[FLASH_KEY] = (
                        f"기존 보유대수 붙여넣기 데이터 {len(incoming_baseline):,}행을 편집본에 "
                        "적용했습니다. 아직 DuckDB에는 저장되지 않았습니다. 손대지 않은 개발 "
                        "샘플 행이 남아 있으면 저장 전에 고치거나 지워야 합니다."
                    )
                    st.rerun()
            if cancel:
                st.session_state.pop(BASELINE_IMPORT_KEY, None)
                st.rerun()

        incoming_equipment = st.session_state.get(EQUIPMENT_IMPORT_KEY)
        if isinstance(incoming_equipment, pd.DataFrame):
            st.markdown("**호기 마스터 Import 확인**")
            equipment_preview = build_equipment_import_preview(equipment, incoming_equipment)
            _import_summary(equipment_preview)
            st.dataframe(equipment_preview, hide_index=True, width="stretch")
            with st.container(horizontal=True):
                confirm = st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_equipment_import_v3",
                )
                cancel = st.button(
                    "취소", icon=":material/close:", key="cancel_equipment_import_v3"
                )
            if confirm:
                try:
                    merged_equipment = merge_equipment_rows(
                        equipment, incoming_equipment, floor_canvases=floor_canvases
                    )
                    merged_downtime = merge_downtime_rows(
                        downtime,
                        empty_downtime_schedule(),
                        equipment=merged_equipment,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state[EQUIPMENT_DRAFT_KEY] = merged_equipment
                    st.session_state[DOWNTIME_DRAFT_KEY] = merged_downtime
                    st.session_state.pop(EQUIPMENT_EDITOR_KEY, None)
                    st.session_state.pop(DOWNTIME_EDITOR_KEY, None)
                    st.session_state.pop(EQUIPMENT_IMPORT_KEY, None)
                    st.session_state[FLASH_KEY] = (
                        f"호기 마스터 붙여넣기 데이터 {len(incoming_equipment):,}행을 편집본에 "
                        "적용했습니다. 아직 DuckDB에는 저장되지 않았습니다."
                    )
                    st.rerun()
            if cancel:
                st.session_state.pop(EQUIPMENT_IMPORT_KEY, None)
                st.rerun()

        incoming_downtime = st.session_state.get(DOWNTIME_IMPORT_KEY)
        if isinstance(incoming_downtime, pd.DataFrame):
            st.markdown("**비가동 일정 Import 확인**")
            downtime_preview = build_downtime_import_preview(downtime, incoming_downtime)
            _import_summary(downtime_preview)
            st.dataframe(downtime_preview, hide_index=True, width="stretch")
            with st.container(horizontal=True):
                confirm = st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_downtime_import_v3",
                )
                cancel = st.button("취소", icon=":material/close:", key="cancel_downtime_import_v3")
            if confirm:
                try:
                    merged_downtime = merge_downtime_rows(
                        downtime, incoming_downtime, equipment=equipment
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state[DOWNTIME_DRAFT_KEY] = merged_downtime
                    st.session_state.pop(DOWNTIME_EDITOR_KEY, None)
                    st.session_state.pop(DOWNTIME_IMPORT_KEY, None)
                    st.session_state[FLASH_KEY] = (
                        f"비가동 일정 붙여넣기 데이터 {len(incoming_downtime):,}행을 편집본에 "
                        "적용했습니다. 아직 DuckDB에는 저장되지 않았습니다."
                    )
                    st.rerun()
            if cancel:
                st.session_state.pop(DOWNTIME_IMPORT_KEY, None)
                st.rerun()

    downtime_type_options = sorted(
        set(DOWNTIME_TYPES) | set(downtime["비가동유형"].dropna().astype(str).tolist())
    )
    with st.form("equipment_operations_form_v3", border=True):
        st.markdown("#### 기존 보유대수")
        st.caption(
            "호기·Qual 이력을 관리할 실익이 없는 기존 가동설비를 공정·분류별 집계로 "
            "유지합니다. 공정 값은 호기 마스터의 공정소분류와 연결됩니다."
        )
        edited_baseline = st.data_editor(
            baseline,
            key=BASELINE_EDITOR_KEY,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "공정": st.column_config.TextColumn(required=True, pinned=True),
                "분류": st.column_config.TextColumn(required=True),
                "기존보유대수": st.column_config.NumberColumn(
                    "기존 보유대수",
                    min_value=0,
                    step=0.1,
                    format="%.1f 대",
                    required=True,
                ),
                "비고": st.column_config.TextColumn(),
            },
        )

        st.markdown("#### 호기 마스터")
        st.caption(
            "일반 신규 호기는 입고일정·Qual일정이 필수입니다. 장기보관 또는 기존설비 Y는 "
            "두 일정이 없어도 됩니다. 확정상태는 Qual 실행관리 전용이며, 레이아웃표시 Y는 "
            "위치와 좌표·크기가 모두 필요합니다. 환산비는 같은 공정에 생산성이 다른 모델이 "
            "섞일 때 **한 대가 몇 대 몫을 하는지**입니다 — 기준 모델이 1이고 비우면 1로 "
            "채워집니다. 아직 Capa 가용대수에는 반영되지 않고 이력으로만 쌓입니다."
        )
        equipment_column_config: dict[str, Any] = {
            "호기": st.column_config.TextColumn(required=True, pinned=True),
            "공정소분류": st.column_config.TextColumn(required=True),
            "동": st.column_config.SelectboxColumn(options=list(VALID_BUILDINGS)),
            "층": st.column_config.SelectboxColumn(options=list(VALID_FLOORS)),
            "X좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_canvas_width, step=1.0
            ),
            "Y좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_canvas_height, step=1.0
            ),
            "Xsize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_canvas_width, step=1.0
            ),
            "Ysize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_canvas_height, step=1.0
            ),
            "확정상태": st.column_config.SelectboxColumn(options=list(QUAL_CONFIRMATION_STATUSES)),
            "장기보관여부": st.column_config.SelectboxColumn(options=["N", "Y"], required=True),
            "기존설비여부": st.column_config.SelectboxColumn(options=["N", "Y"], required=True),
            "레이아웃표시": st.column_config.SelectboxColumn(options=["Y", "N"], required=True),
            # 하한을 0 이 아니라 그 위로 둔다. 0 은 「이 설비는 없는 셈」이라는 뜻이 되는데
            # 그것은 비가동 일정이 맡는 일이다. 비워 두면 기준 모델(1.0)로 채워진다.
            "환산비": st.column_config.NumberColumn(min_value=0.01, step=0.1, format="%.2f"),
        }
        equipment_column_config.update(
            {column: st.column_config.DateColumn(format="YYYY-MM-DD") for column in DATE_COLUMNS}
        )
        edited_equipment = st.data_editor(
            equipment,
            key=EQUIPMENT_EDITOR_KEY,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config=equipment_column_config,
        )

        st.markdown("#### 운영 비가동 일정")
        st.caption(
            "비가동ID 없이 호기·비가동유형·시작일 조합을 일정의 고유 기준으로 사용합니다. "
            "종료일이 없으면 진행 중입니다."
        )
        edited_downtime = st.data_editor(
            downtime,
            key=DOWNTIME_EDITOR_KEY,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "호기": st.column_config.TextColumn(required=True, pinned=True),
                "비가동유형": st.column_config.SelectboxColumn(
                    options=downtime_type_options, required=True
                ),
                "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
                "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "상세사유": st.column_config.TextColumn(),
                "비고": st.column_config.TextColumn(),
            },
        )
        revision_note = st.text_input(
            "변경 메모",
            placeholder="예: 신규 호기 Qual 일정 및 8월 고장 일정 반영",
        )
        submitted = st.form_submit_button(
            "설비 데이터 저장", icon=":material/save:", type="primary"
        )

    if submitted:
        # 화면을 채우려고 넣어 준 샘플이 그대로 불변 리비전에 들어가면 되돌릴 수 없다.
        # 실제 공정명과 다르면 호기 마스터에 붙지 않는 유령 공정이 총대수에 영원히 남는다.
        leftover_samples = untouched_sample_baseline_rows(edited_baseline)
    if submitted and not leftover_samples.empty:
        st.error(
            f"기존 보유대수에 개발 샘플 행이 {len(leftover_samples)}건 그대로 남아 있습니다. "
            "실제 값으로 고치거나 지운 뒤 저장하세요. 이 숫자는 개발용 Core Data 샘플에서 "
            "복사한 것이라 실제 설비와 맞지 않고, 저장하면 리비전에서 지울 수 없습니다."
        )
    elif submitted:
        try:
            saved = repository.save_snapshot(
                edited_baseline,
                edited_equipment,
                edited_downtime,
                note=revision_note,
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc))
        else:
            clear_equipment_snapshot_cache()
            _reset_drafts()
            st.session_state[FLASH_KEY] = (
                f"설비 운영 데이터 r{saved.revision.revision_no}을 저장했습니다. "
                "가용설비와 Space 현황에 반영됩니다."
            )
            st.rerun()

    try:
        revisions = repository.list_revisions()
    except BOOTSTRAP_ERRORS as exc:
        st.error(f"저장 이력을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        st.stop()
    with st.expander("저장 이력 및 필터 조회", icon=":material/history:", expanded=False):
        if not revisions:
            st.caption("저장된 설비 운영 이력이 없습니다.")
        else:
            history = pd.DataFrame(
                [
                    {
                        "리비전": f"r{revision.revision_no}",
                        "저장시각": revision.created_at,
                        "기존대수행": revision.baseline_row_count,
                        "호기행": revision.equipment_row_count,
                        "비가동행": revision.downtime_row_count,
                        "변경메모": revision.note,
                    }
                    for revision in revisions
                ]
            )
            st.dataframe(
                history,
                hide_index=True,
                width="stretch",
                # 메모 없는 리비전에 리터럴 "None" 이 찍혔다. 같은 화면의 선택 상자는
                # 이미 "메모 없음" 을 쓴다.
                placeholder="메모 없음",
                column_config={
                    "저장시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")
                },
            )
            revision_by_id = {revision.revision_id: revision for revision in revisions}
            selected_revision_id = st.selectbox(
                "조회 리비전",
                options=list(revision_by_id),
                format_func=lambda value: (
                    f"r{revision_by_id[value].revision_no} · "
                    f"{revision_by_id[value].created_at:%Y-%m-%d %H:%M} · "
                    f"{revision_by_id[value].note or '메모 없음'}"
                ),
                key="equipment_history_revision_id_v3",
            )
            try:
                historical = load_equipment_snapshot(equipment_database_path, selected_revision_id)
            except BOOTSTRAP_ERRORS as exc:
                st.error(f"선택한 이력을 읽지 못했습니다: {bootstrap_error_message(exc)}")
                st.stop()
            historical_equipment = historical.equipment
            with st.container(horizontal=True, gap="small"):
                history_processes = st.multiselect(
                    "공정소분류",
                    historical_equipment["공정소분류"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_process_filter_v3",
                )
                history_buildings = st.multiselect(
                    "동",
                    historical_equipment["동"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_building_filter_v3",
                )
                history_floors = st.multiselect(
                    "층",
                    historical_equipment["층"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_floor_filter_v3",
                )
                history_equipment_ids = st.multiselect(
                    "호기",
                    historical_equipment["호기"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_id_filter_v3",
                )
                history_downtime_types = st.multiselect(
                    "비가동유형",
                    historical.downtime["비가동유형"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_downtime_type_filter_v3",
                )
            filtered_history_equipment = historical_equipment.copy()
            for column, selected in (
                ("공정소분류", history_processes),
                ("동", history_buildings),
                ("층", history_floors),
                ("호기", history_equipment_ids),
            ):
                if selected:
                    filtered_history_equipment = filtered_history_equipment.loc[
                        filtered_history_equipment[column].isin(selected)
                    ]
            filtered_history_downtime = historical.downtime.copy()
            if history_equipment_ids:
                filtered_history_downtime = filtered_history_downtime.loc[
                    filtered_history_downtime["호기"].isin(history_equipment_ids)
                ]
            elif history_processes or history_buildings or history_floors:
                filtered_history_downtime = _downtime_for_equipment(
                    filtered_history_downtime, filtered_history_equipment
                )
            if history_downtime_types:
                filtered_history_downtime = filtered_history_downtime.loc[
                    filtered_history_downtime["비가동유형"].isin(history_downtime_types)
                ]
            event_range = st.date_input(
                "비가동 일정 기간",
                value=(start_date, end_date),
                key="equipment_history_event_range_v3",
            )
            if isinstance(event_range, tuple) and len(event_range) == 2:
                event_start, event_end = event_range
            elif isinstance(event_range, date):
                event_start = event_range
                event_end = event_range
            else:
                event_start = start_date
                event_end = end_date
            if event_start <= event_end and not filtered_history_downtime.empty:
                overlaps = filtered_history_downtime["시작일"].dt.date.le(event_end) & (
                    filtered_history_downtime["종료일"].isna()
                    | filtered_history_downtime["종료일"].dt.date.ge(event_start)
                )
                filtered_history_downtime = filtered_history_downtime.loc[overlaps]
            st.markdown("**기존 보유대수**")
            st.dataframe(historical.baseline, hide_index=True, width="stretch")
            st.markdown("**호기 마스터**")
            st.dataframe(filtered_history_equipment, hide_index=True, width="stretch")
            st.markdown("**비가동 일정**")
            st.dataframe(filtered_history_downtime, hide_index=True, width="stretch")
