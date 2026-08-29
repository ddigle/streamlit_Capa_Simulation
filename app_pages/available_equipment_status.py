from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.persistence.equipment_cache import get_equipment_repository
from capa_simulation.services.equipment_availability import (
    DOWNTIME_TYPES,
    build_inactive_equipment,
    build_weekly_equipment_availability,
    empty_downtime_schedule,
    empty_equipment_master,
    sample_equipment_baseline,
)
from capa_simulation.services.equipment_csv import (
    downtime_csv_template,
    equipment_csv_template,
    merge_downtime_rows,
    merge_equipment_rows,
    read_downtime_csv,
    read_equipment_csv,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

FLASH_KEY = "equipment_status_flash"
BASELINE_EDITOR_KEY = "equipment_baseline_editor_v2"
EQUIPMENT_EDITOR_KEY = "equipment_master_editor_v2"
DOWNTIME_EDITOR_KEY = "equipment_downtime_editor_v2"
EQUIPMENT_DRAFT_KEY = "equipment_master_draft_v2"
DOWNTIME_DRAFT_KEY = "equipment_downtime_draft_v2"
DRAFT_REVISION_KEY = "equipment_draft_revision_v2"


def _filter_rows(
    data: pd.DataFrame,
    processes: list[str],
    classifications: list[str],
) -> pd.DataFrame:
    result = data.copy()
    if processes:
        result = result.loc[result["공정"].isin(processes)]
    if classifications:
        result = result.loc[result["분류"].isin(classifications)]
    return result


def _downtime_for_equipment(downtime: pd.DataFrame, equipment: pd.DataFrame) -> pd.DataFrame:
    return downtime.loc[downtime["호기"].isin(equipment["호기"])].copy()


def _reset_drafts() -> None:
    for key in (
        BASELINE_EDITOR_KEY,
        EQUIPMENT_EDITOR_KEY,
        DOWNTIME_EDITOR_KEY,
        EQUIPMENT_DRAFT_KEY,
        DOWNTIME_DRAFT_KEY,
        DRAFT_REVISION_KEY,
    ):
        st.session_state.pop(key, None)


st.title("가용설비 현황")
st.caption(
    "기존 보유대수, 호기별 설치·양산전환 일정과 운영 비가동 일정을 하나의 설비 전용 "
    "리비전으로 관리합니다."
)

flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    st.success(flash)

try:
    repository = get_equipment_repository(str(EQUIPMENT_DUCKDB_PATH.resolve()))
    latest_snapshot = repository.load_latest_snapshot()
    if latest_snapshot is None:
        baseline = sample_equipment_baseline()
        saved_equipment = empty_equipment_master()
        saved_downtime = empty_downtime_schedule()
        revision_token = "empty"
    else:
        baseline = latest_snapshot.baseline
        saved_equipment = latest_snapshot.equipment
        saved_downtime = latest_snapshot.downtime
        revision_token = latest_snapshot.revision.revision_id
except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
    st.error(f"설비 현황을 준비하지 못했습니다: {exc}")
    st.stop()

if st.session_state.get(DRAFT_REVISION_KEY) != revision_token:
    st.session_state[EQUIPMENT_DRAFT_KEY] = saved_equipment.copy()
    st.session_state[DOWNTIME_DRAFT_KEY] = saved_downtime.copy()
    st.session_state[DRAFT_REVISION_KEY] = revision_token
equipment = st.session_state[EQUIPMENT_DRAFT_KEY].copy()
downtime = st.session_state[DOWNTIME_DRAFT_KEY].copy()

today = date.today()
default_start_date = date(today.year, today.month, 1)
default_end_date = today + timedelta(weeks=12)
with st.container(border=True):
    st.markdown("#### :material/date_range: 조회기간 설정")
    st.caption(
        "가용설비 현황에만 적용되는 월요일 시작 ISO Weeknum 조회기간입니다. "
        "주차 값은 각 주 일요일 종료 시점의 상태입니다."
    )
    with st.container(horizontal=True, gap="small"):
        start_date = st.date_input(
            "시작일",
            value=default_start_date,
            key="equipment_dashboard_start_date",
            persist_state="session",
            width=180,
        )
        end_date = st.date_input(
            "종료일",
            value=default_end_date,
            key="equipment_dashboard_end_date",
            persist_state="session",
            width=180,
        )

dashboard_tab, management_tab = st.tabs(["대시보드", "설비 데이터·이력 관리"])

with dashboard_tab:
    if latest_snapshot is None:
        st.info(
            "저장된 설비 리비전이 없어 개발용 공정별 기존 보유대수만 표시합니다. "
            "관리 탭에서 호기 마스터와 비가동 일정을 입력해 첫 리비전을 저장하세요."
        )
    else:
        st.caption(
            f"현재 적용 이력: r{latest_snapshot.revision.revision_no} · "
            f"{latest_snapshot.revision.created_at:%Y-%m-%d %H:%M}"
        )

    if start_date > end_date:
        st.error("설비 대시보드 시작일은 종료일보다 늦을 수 없습니다.")
        weekly = pd.DataFrame()
    else:
        try:
            weekly = build_weekly_equipment_availability(
                baseline,
                equipment,
                downtime,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError as exc:
            st.error(str(exc))
            weekly = pd.DataFrame()
    if weekly.empty and start_date <= end_date:
        st.info("집계할 설비 기준이나 호기 일정이 없습니다.")
    elif not weekly.empty:
        process_filter_options = weekly["공정"].drop_duplicates().tolist()
        classification_filter_options = weekly["분류"].drop_duplicates().tolist()
        with st.container(border=True):
            st.markdown("#### :material/filter_alt: 조회 조건")
            with st.container(horizontal=True, gap="small"):
                selected_processes = st.multiselect(
                    "공정",
                    options=process_filter_options,
                    placeholder="전체",
                    key="equipment_dashboard_processes",
                    persist_state="session",
                    width=260,
                )
                selected_classifications = st.multiselect(
                    "분류",
                    options=classification_filter_options,
                    placeholder="전체",
                    key="equipment_dashboard_classifications",
                    persist_state="session",
                    width=220,
                )

        filtered_weekly = _filter_rows(
            weekly,
            selected_processes,
            selected_classifications,
        )
        latest_week_start = filtered_weekly["주차시작일"].max()
        latest_week = filtered_weekly.loc[filtered_weekly["주차시작일"].eq(latest_week_start)]
        total_count = float(latest_week["총대수"].sum())
        available_count = float(latest_week["가용대수"].sum())
        inactive_count = float(latest_week["비가동대수"].sum())
        availability_rate = available_count / total_count if total_count else 0.0
        latest_week_label = str(latest_week["Weeknum"].iloc[0])

        st.caption(f"조회 마지막 주 기준 · {latest_week_label}")
        with st.container(horizontal=True):
            st.metric("총대수", f"{total_count:,.1f}대", border=True)
            st.metric("가용대수", f"{available_count:,.1f}대", border=True)
            st.metric("비가동대수", f"{inactive_count:,.1f}대", border=True)
            st.metric("가용률", f"{availability_rate:.1%}", border=True)

        trend = (
            filtered_weekly.groupby(["주차시작일", "Weeknum"], as_index=False)[
                ["가용대수", "비가동대수"]
            ]
            .sum()
            .sort_values("주차시작일")
        )
        trend_long = trend.melt(
            id_vars=["주차시작일", "Weeknum"],
            value_vars=["가용대수", "비가동대수"],
            var_name="상태",
            value_name="대수",
        )
        with st.container(border=True):
            st.markdown("#### 주차별 설비 현황")
            weekly_chart = (
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
            st.altair_chart(weekly_chart, width="stretch")

        breakdown_columns = (
            "공정",
            "분류",
            "기존보유대수",
            "추가설비대수",
            "총대수",
            "셋업중대수",
            "운영비가동대수",
            "가용대수",
            "비가동대수",
        )
        latest_breakdown = latest_week.loc[:, breakdown_columns].sort_values(
            ["비가동대수", "공정", "분류"],
            ascending=[False, True, True],
        )
        with st.container(border=True):
            st.markdown("#### 공정·분류별 현황")
            st.dataframe(
                latest_breakdown,
                hide_index=True,
                width="stretch",
                column_config={
                    column: st.column_config.NumberColumn(column, format="%.1f 대")
                    for column in breakdown_columns[2:]
                },
            )

        filtered_equipment = _filter_rows(
            equipment,
            selected_processes,
            selected_classifications,
        )
        filtered_downtime = _downtime_for_equipment(downtime, filtered_equipment)
        latest_week_end = latest_week["주차종료일"].max()
        inactive_equipment = build_inactive_equipment(
            filtered_equipment,
            filtered_downtime,
            as_of=latest_week_end,
        )
        with st.container(border=True):
            st.markdown("#### 비가동 설비호기")
            st.caption(f"{latest_week_end:%Y-%m-%d} 기준 양산 준비 중이거나 운영 비가동인 호기")
            if inactive_equipment.empty:
                st.success("해당 주차에 비가동 설비호기가 없습니다.")
            else:
                st.dataframe(
                    inactive_equipment,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
                        for column in (
                            "입고일",
                            "Hookup완료일",
                            "하드웨어셋업완료일",
                            "Qual완료일",
                            "TTTM완료일",
                            "양산전환일",
                        )
                    },
                )

with management_tab:
    if latest_snapshot is None:
        st.info(
            "기존 보유대수 샘플은 유지하고 호기 마스터·비가동 일정은 빈 상태입니다. "
            "웹에서 행을 추가하거나 CSV를 가져온 뒤 첫 리비전을 저장하세요."
        )
    else:
        st.caption(
            f"최근 저장본 r{latest_snapshot.revision.revision_no}을 편집합니다. "
            "저장하면 세 입력 전체가 새 불변 리비전으로 보관됩니다."
        )

    with st.container(border=True):
        st.markdown("#### :material/upload_file: CSV Import")
        st.caption(
            "UTF-8 또는 CP949 CSV를 ID 기준으로 추가·수정합니다. 현재 웹 편집값보다 "
            "CSV Import를 먼저 적용하세요."
        )
        equipment_import_col, downtime_import_col = st.columns(2)
        with equipment_import_col:
            equipment_upload = st.file_uploader(
                "호기 마스터 CSV",
                type="csv",
                key="equipment_master_csv_upload",
            )
            with st.container(horizontal=True):
                st.download_button(
                    "양식 다운로드",
                    data=equipment_csv_template(),
                    file_name="equipment_master_template.csv",
                    mime="text/csv",
                    icon=":material/download:",
                    key="equipment_master_template_download",
                )
                apply_equipment_csv = st.button(
                    "호기 CSV 적용",
                    icon=":material/playlist_add:",
                    disabled=equipment_upload is None,
                    key="equipment_master_csv_apply",
                )
        with downtime_import_col:
            downtime_upload = st.file_uploader(
                "비가동 일정 CSV",
                type="csv",
                key="equipment_downtime_csv_upload",
            )
            with st.container(horizontal=True):
                st.download_button(
                    "양식 다운로드",
                    data=downtime_csv_template(),
                    file_name="equipment_downtime_template.csv",
                    mime="text/csv",
                    icon=":material/download:",
                    key="equipment_downtime_template_download",
                )
                apply_downtime_csv = st.button(
                    "비가동 CSV 적용",
                    icon=":material/playlist_add:",
                    disabled=downtime_upload is None,
                    key="equipment_downtime_csv_apply",
                )

        if apply_equipment_csv and equipment_upload is not None:
            try:
                imported_equipment = read_equipment_csv(equipment_upload.getvalue())
                merged_equipment = merge_equipment_rows(equipment, imported_equipment)
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
                st.session_state[FLASH_KEY] = (
                    f"호기 마스터 CSV {len(imported_equipment):,}행을 편집본에 적용했습니다."
                )
                st.rerun()

        if apply_downtime_csv and downtime_upload is not None:
            try:
                imported_downtime = read_downtime_csv(
                    downtime_upload.getvalue(),
                    equipment=equipment,
                )
                merged_downtime = merge_downtime_rows(
                    downtime,
                    imported_downtime,
                    equipment=equipment,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[DOWNTIME_DRAFT_KEY] = merged_downtime
                st.session_state.pop(DOWNTIME_EDITOR_KEY, None)
                st.session_state[FLASH_KEY] = (
                    f"비가동 일정 CSV {len(imported_downtime):,}행을 편집본에 적용했습니다."
                )
                st.rerun()

    downtime_type_options = sorted(
        set(DOWNTIME_TYPES) | set(downtime["비가동유형"].dropna().astype(str).tolist())
    )
    with st.form("equipment_operations_form", border=True):
        st.markdown("#### 기존 보유대수")
        st.caption(
            "호기·양산전환 이력을 관리할 실익이 없는 기존 가동설비를 공정·분류별 집계로 유지합니다."
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
            "양산전환일부터 가용대수에 포함됩니다. Space 높이는 고정이며 X·Y·너비만 입력합니다."
        )
        date_columns = (
            "사전인프라완료일",
            "입고일",
            "Hookup완료일",
            "하드웨어셋업완료일",
            "Qual완료일",
            "TTTM완료일",
            "양산전환일",
        )
        equipment_column_config: dict[str, Any] = {
            "호기": st.column_config.TextColumn(required=True, pinned=True),
            "공정": st.column_config.TextColumn(required=True),
            "분류": st.column_config.TextColumn(required=True),
            "동": st.column_config.TextColumn(),
            "층": st.column_config.TextColumn(),
            "X": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
            "Y": st.column_config.NumberColumn(min_value=0.0, max_value=60.0, step=1.0),
            "너비": st.column_config.NumberColumn(min_value=0.1, max_value=100.0, step=1.0),
            "비고": st.column_config.TextColumn(),
        }
        equipment_column_config.update(
            {column: st.column_config.DateColumn(format="YYYY-MM-DD") for column in date_columns}
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
            "개발대여·공사·고장·이설 등의 시작일과 종료일을 입력합니다. "
            "종료일이 없으면 진행 중입니다."
        )
        edited_downtime = st.data_editor(
            downtime,
            key=DOWNTIME_EDITOR_KEY,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "비가동ID": st.column_config.TextColumn(required=True, pinned=True),
                "호기": st.column_config.TextColumn(required=True),
                "비가동유형": st.column_config.SelectboxColumn(
                    options=downtime_type_options,
                    required=True,
                ),
                "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
                "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "상세사유": st.column_config.TextColumn(),
                "비고": st.column_config.TextColumn(),
            },
        )
        revision_note = st.text_input(
            "변경 메모",
            placeholder="예: 신규 호기 설치 일정 및 8월 고장 일정 반영",
        )
        submitted = st.form_submit_button(
            "설비 데이터 저장",
            icon=":material/save:",
            type="primary",
        )

    if submitted:
        try:
            saved = repository.save_snapshot(
                edited_baseline,
                edited_equipment,
                edited_downtime,
                note=revision_note,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            st.error(str(exc))
        else:
            _reset_drafts()
            st.session_state[FLASH_KEY] = (
                f"설비 운영 데이터 r{saved.revision.revision_no}을 저장했습니다. "
                "가용설비와 Space 현황에 반영됩니다."
            )
            st.rerun()

    revisions = repository.list_revisions()
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
                key="equipment_history_revision_id",
            )
            historical = repository.load_snapshot(selected_revision_id)
            historical_equipment = historical.equipment
            process_options = historical_equipment["공정"].dropna().drop_duplicates().tolist()
            building_options = historical_equipment["동"].dropna().drop_duplicates().tolist()
            floor_options = historical_equipment["층"].dropna().drop_duplicates().tolist()
            equipment_options = historical_equipment["호기"].dropna().drop_duplicates().tolist()
            downtime_type_history = (
                historical.downtime["비가동유형"].dropna().drop_duplicates().tolist()
            )
            with st.container(horizontal=True, gap="small"):
                history_processes = st.multiselect(
                    "공정", process_options, key="equipment_history_process_filter"
                )
                history_buildings = st.multiselect(
                    "동", building_options, key="equipment_history_building_filter"
                )
                history_floors = st.multiselect(
                    "층", floor_options, key="equipment_history_floor_filter"
                )
                history_equipment_ids = st.multiselect(
                    "호기", equipment_options, key="equipment_history_id_filter"
                )
                history_downtime_types = st.multiselect(
                    "비가동유형",
                    downtime_type_history,
                    key="equipment_history_downtime_type_filter",
                )

            filtered_history_equipment = historical_equipment.copy()
            for column, selected in (
                ("공정", history_processes),
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
                    filtered_history_downtime,
                    filtered_history_equipment,
                )
            if history_downtime_types:
                filtered_history_downtime = filtered_history_downtime.loc[
                    filtered_history_downtime["비가동유형"].isin(history_downtime_types)
                ]
            event_range = st.date_input(
                "비가동 일정 기간",
                value=(start_date, end_date),
                key="equipment_history_event_range",
            )
            if isinstance(event_range, tuple) and len(event_range) == 2:
                event_start = event_range[0]
                event_end = event_range[1]
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
