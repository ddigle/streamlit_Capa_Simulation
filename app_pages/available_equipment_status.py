from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.persistence.equipment_cache import get_equipment_repository
from capa_simulation.services.equipment_availability import (
    build_inactive_equipment,
    build_weekly_equipment_availability,
    empty_equipment_schedule,
    sample_equipment_baseline,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

FLASH_KEY = "equipment_status_flash"
BASELINE_EDITOR_KEY = "equipment_baseline_editor_v1"
SCHEDULE_EDITOR_KEY = "equipment_schedule_editor_v1"


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


st.title("가용설비 현황")
st.caption(
    "시뮬레이션 시나리오와 분리된 설비 전용 데이터로 주차별 총대수, 가용대수와 "
    "비가동대수를 관리합니다."
)

flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    st.success(flash)

try:
    repository = get_equipment_repository(str(EQUIPMENT_DUCKDB_PATH.resolve()))
    latest_snapshot = repository.load_latest_snapshot()
    if latest_snapshot is None:
        baseline = sample_equipment_baseline()
        schedule = empty_equipment_schedule()
    else:
        baseline = latest_snapshot.baseline
        schedule = latest_snapshot.schedule
except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
    st.error(f"설비 현황을 준비하지 못했습니다: {exc}")
    st.stop()

today = date.today()
default_start_date = date(today.year, today.month, 1)
default_end_date = today + timedelta(weeks=12)
with st.container(border=True):
    st.markdown("#### :material/date_range: 조회기간 설정")
    st.caption(
        "이 페이지의 주차별 설비 현황에만 적용됩니다. 주차는 월요일 시작 ISO Weeknum 기준입니다."
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

dashboard_tab, schedule_tab = st.tabs(["대시보드", "설비호기 일정 관리"])

with dashboard_tab:
    if latest_snapshot is None:
        st.info(
            "아직 저장된 설비 전용 데이터가 없어 개발용 Core Data 샘플의 공정별 "
            "보유대수를 표시합니다. 검토 후 설비호기 일정 관리 탭에서 첫 이력을 저장하세요."
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
        weekly = build_weekly_equipment_availability(
            baseline,
            schedule,
            start_date=start_date,
            end_date=end_date,
        )
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
            weeknum_order = trend["Weeknum"].tolist()
            weekly_chart = (
                alt.Chart(trend_long)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Weeknum:N",
                        sort=weeknum_order,
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

        latest_breakdown = latest_week.loc[
            :,
            [
                "공정",
                "분류",
                "기존보유대수",
                "추가설비대수",
                "총대수",
                "가용대수",
                "비가동대수",
            ],
        ].sort_values(["비가동대수", "공정", "분류"], ascending=[False, True, True])
        with st.container(border=True):
            st.markdown("#### 공정·분류별 현황")
            st.dataframe(
                latest_breakdown,
                hide_index=True,
                width="stretch",
                column_config={
                    column: st.column_config.NumberColumn(column, format="%.1f 대")
                    for column in (
                        "기존보유대수",
                        "추가설비대수",
                        "총대수",
                        "가용대수",
                        "비가동대수",
                    )
                },
            )

        filtered_schedule = _filter_rows(
            schedule,
            selected_processes,
            selected_classifications,
        )
        latest_week_end = latest_week["주차종료일"].max()
        inactive_equipment = build_inactive_equipment(
            filtered_schedule,
            as_of=latest_week_end,
        )
        with st.container(border=True):
            st.markdown("#### 비가동 설비호기")
            st.caption(f"{latest_week_end:%Y-%m-%d}까지 입고되었으나 셋업이 완료되지 않은 호기")
            if inactive_equipment.empty:
                st.success("해당 주차에 비가동 설비호기가 없습니다.")
            else:
                st.dataframe(
                    inactive_equipment,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
                        for column in ("입고일", "셋업시작일", "셋업완료일")
                    },
                )

with schedule_tab:
    if latest_snapshot is None:
        st.info(
            "설비 전용 저장소가 비어 있어 개발용 샘플 보유대수를 입력했습니다. "
            "원본 샘플에 2차 분류가 없으므로 분류는 '전체'이며, "
            "저장 전까지 DB에는 기록되지 않습니다."
        )
    else:
        st.caption(
            f"가장 최근 저장본 r{latest_snapshot.revision.revision_no}을 편집합니다. "
            "저장하면 과거 값은 유지되고 새 이력이 생성됩니다."
        )

    with st.form("equipment_schedule_form", border=True):
        st.markdown("#### 기존 보유대수")
        st.caption("호기별 일정 관리 이전부터 가용한 공정·분류별 기준 대수입니다.")
        edited_baseline = st.data_editor(
            baseline,
            key=BASELINE_EDITOR_KEY,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "공정": st.column_config.TextColumn("공정", required=True, pinned=True),
                "분류": st.column_config.TextColumn("분류", required=True),
                "기존보유대수": st.column_config.NumberColumn(
                    "기존 보유대수",
                    min_value=0,
                    step=0.1,
                    format="%.1f 대",
                    required=True,
                ),
                "비고": st.column_config.TextColumn("비고"),
            },
        )

        st.markdown("#### 설비호기 일정")
        st.caption(
            "입고일부터 총대수, 셋업완료일부터 가용대수에 포함됩니다. "
            "입고 후 셋업완료 전까지는 비가동대수입니다."
        )
        edited_schedule = st.data_editor(
            schedule,
            key=SCHEDULE_EDITOR_KEY,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "호기": st.column_config.TextColumn("호기", required=True, pinned=True),
                "공정": st.column_config.TextColumn("공정", required=True),
                "분류": st.column_config.TextColumn("분류", required=True),
                "입고일": st.column_config.DateColumn(
                    "입고일",
                    format="YYYY-MM-DD",
                    required=True,
                ),
                "셋업시작일": st.column_config.DateColumn(
                    "셋업 시작일",
                    format="YYYY-MM-DD",
                ),
                "셋업완료일": st.column_config.DateColumn(
                    "셋업 완료일",
                    format="YYYY-MM-DD",
                ),
                "비고": st.column_config.TextColumn("비고"),
            },
        )
        revision_note = st.text_input(
            "변경 메모",
            placeholder="예: 8월 셋업 일정 변경 및 신규 2호기 추가",
        )
        submitted = st.form_submit_button(
            "일정 저장",
            icon=":material/save:",
            type="primary",
        )

    if submitted:
        try:
            saved = repository.save_snapshot(
                edited_baseline,
                edited_schedule,
                note=revision_note,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state.pop(BASELINE_EDITOR_KEY, None)
            st.session_state.pop(SCHEDULE_EDITOR_KEY, None)
            st.session_state[FLASH_KEY] = (
                f"설비 현황 r{saved.revision.revision_no}을 저장했습니다. "
                "대시보드 집계에 반영되었습니다."
            )
            st.rerun()

    revisions = repository.list_revisions()
    with st.expander("저장 이력", expanded=False):
        if not revisions:
            st.caption("저장된 설비 현황 이력이 없습니다.")
        else:
            history = pd.DataFrame(
                [
                    {
                        "리비전": f"r{revision.revision_no}",
                        "저장시각": revision.created_at,
                        "기준행": revision.baseline_row_count,
                        "호기행": revision.schedule_row_count,
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
                    "저장시각": st.column_config.DatetimeColumn(
                        "저장 시각",
                        format="YYYY-MM-DD HH:mm",
                    )
                },
            )
            revision_by_id = {revision.revision_id: revision for revision in revisions}
            selected_revision_id = st.selectbox(
                "이력 상세",
                options=list(revision_by_id),
                format_func=lambda value: (
                    f"r{revision_by_id[value].revision_no} · "
                    f"{revision_by_id[value].created_at:%Y-%m-%d %H:%M} · "
                    f"{revision_by_id[value].note or '메모 없음'}"
                ),
                key="equipment_history_revision_id",
            )
            historical = repository.load_snapshot(selected_revision_id)
            st.markdown("**기존 보유대수**")
            st.dataframe(historical.baseline, hide_index=True, width="stretch")
            st.markdown("**설비호기 일정**")
            st.dataframe(
                historical.schedule,
                hide_index=True,
                width="stretch",
                column_config={
                    column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
                    for column in ("입고일", "셋업시작일", "셋업완료일")
                },
            )
