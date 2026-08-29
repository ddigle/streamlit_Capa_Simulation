from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.components.space_layout import (
    BUILDINGS,
    build_fab_figure,
    build_floor_figure,
    build_floor_layout_figure,
    building_counts,
    equipment_counts,
    fab_counts,
    first_selected_customdata,
    floors_for,
    invalid_equipment_rows,
)
from capa_simulation.persistence.equipment_cache import get_equipment_repository
from capa_simulation.services.equipment_availability import (
    MILESTONES,
    build_milestone_transition_events,
    build_space_equipment_status,
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

SELECTED_BUILDING_KEY = "space_status_selected_building"
SELECTED_FLOOR_KEY = "space_status_selected_floor"


def _show_fab_overview() -> None:
    st.session_state.pop(SELECTED_BUILDING_KEY, None)
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


def _show_building(building: str) -> None:
    st.session_state[SELECTED_BUILDING_KEY] = building
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


try:
    repository = get_equipment_repository(str(EQUIPMENT_DUCKDB_PATH.resolve()))
    latest_snapshot = repository.load_latest_snapshot()
    if latest_snapshot is None:
        equipment = empty_equipment_master()
        downtime = empty_downtime_schedule()
    else:
        equipment = latest_snapshot.equipment
        downtime = latest_snapshot.downtime
except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
    st.error(f"Space 설비 데이터를 준비하지 못했습니다: {exc}")
    st.stop()

building_names = {building.name for building in BUILDINGS}
valid_location_pairs = {
    (building.name, floor.floor) for building in BUILDINGS for floor in floors_for(building.name)
}
selected_building = st.session_state.get(SELECTED_BUILDING_KEY)
if not isinstance(selected_building, str) or selected_building not in building_names:
    selected_building = None
    _show_fab_overview()

selected_floor = st.session_state.get(SELECTED_FLOOR_KEY)
valid_floor_names = (
    {floor.floor for floor in floors_for(selected_building)} if selected_building else set()
)
if not isinstance(selected_floor, str) or selected_floor not in valid_floor_names:
    selected_floor = None
    st.session_state.pop(SELECTED_FLOOR_KEY, None)

st.title("Space 현황")
st.caption(
    "가용설비 현황과 동일한 설비 전용 DuckDB 리비전에서 호기·설치 단계·비가동 상태와 "
    "Space 좌표를 조회합니다."
)
if latest_snapshot is None:
    st.info(
        "저장된 호기 마스터가 없습니다. 가용설비 현황의 설비 데이터 관리 탭에서 "
        "호기와 동·층·X·Y·너비를 입력하세요.",
        icon=":material/info:",
    )
else:
    st.caption(
        f"적용 이력 r{latest_snapshot.revision.revision_no} · "
        f"{latest_snapshot.revision.created_at:%Y-%m-%d %H:%M}"
    )

with st.container(border=True):
    st.markdown("#### :material/event: Space 기준일·필터")
    with st.container(horizontal=True, gap="small"):
        as_of = st.date_input(
            "기준일",
            value=date.today(),
            key="space_status_as_of",
            persist_state="session",
            width=180,
        )
        all_status = build_space_equipment_status(equipment, downtime, as_of=as_of)
        selected_processes = st.multiselect(
            "공정",
            options=all_status["공정"].dropna().drop_duplicates().tolist(),
            placeholder="전체",
            key="space_status_process_filter",
            persist_state="session",
            width=240,
        )
        selected_stages = st.multiselect(
            "단계",
            options=all_status["상태"].dropna().drop_duplicates().tolist(),
            placeholder="전체",
            key="space_status_stage_filter",
            persist_state="session",
            width=220,
        )

space_equipment = all_status.copy()
if selected_processes:
    space_equipment = space_equipment.loc[space_equipment["공정"].isin(selected_processes)]
if selected_stages:
    space_equipment = space_equipment.loc[space_equipment["상태"].isin(selected_stages)]
has_supported_location = pd.Series(
    [
        (building, floor) in valid_location_pairs
        for building, floor in zip(space_equipment["동"], space_equipment["층"], strict=False)
    ],
    index=space_equipment.index,
)
located_equipment = space_equipment.loc[
    space_equipment["동"].notna()
    & space_equipment["층"].notna()
    & space_equipment[["X", "Y", "너비"]].notna().all(axis=1)
    & has_supported_location
].copy()
unlocated_count = len(space_equipment) - len(located_equipment)

with st.container(border=True):
    st.markdown("#### :material/event_available: 기간 내 설비 단계 전환 현황")
    st.caption(
        "선택 기간에 사전 인프라부터 양산까지 완료일이 등록된 호기를 취합합니다. "
        "Space 기준일 이전 일정은 데이터상 완료, 이후 일정은 예정으로 구분합니다."
    )
    transition_process_options = equipment["공정"].dropna().drop_duplicates().tolist()
    transition_stage_options = [label for _, label in MILESTONES]
    with st.form("space_transition_event_filter_form", border=False):
        with st.container(horizontal=True, gap="small"):
            transition_range = st.date_input(
                "전환 조회기간",
                value=(as_of - timedelta(days=14), as_of + timedelta(days=14)),
                key="space_transition_event_range",
                persist_state="session",
                width=260,
            )
            transition_processes = st.multiselect(
                "공정",
                options=transition_process_options,
                placeholder="전체",
                key="space_transition_process_filter",
                persist_state="session",
                width=240,
            )
            transition_stages = st.multiselect(
                "전환단계",
                options=transition_stage_options,
                placeholder="전체",
                key="space_transition_stage_filter",
                persist_state="session",
                width=230,
            )
            transition_schedule_status = st.selectbox(
                "일정상태",
                options=("전체", "완료", "예정"),
                key="space_transition_status_filter",
                persist_state="session",
                width=150,
            )
            st.form_submit_button("조회", icon=":material/search:", type="primary")

    if isinstance(transition_range, tuple) and len(transition_range) == 2:
        transition_start = transition_range[0]
        transition_end = transition_range[1]
    elif isinstance(transition_range, date):
        transition_start = transition_range
        transition_end = transition_range
    else:
        transition_start = as_of - timedelta(days=14)
        transition_end = as_of + timedelta(days=14)

    try:
        transition_events = build_milestone_transition_events(
            equipment,
            start_date=transition_start,
            end_date=transition_end,
            as_of=as_of,
        )
    except ValueError as exc:
        st.error(str(exc))
        transition_events = pd.DataFrame()

    if transition_processes and not transition_events.empty:
        transition_events = transition_events.loc[
            transition_events["공정"].isin(transition_processes)
        ]
    if transition_stages and not transition_events.empty:
        transition_events = transition_events.loc[
            transition_events["전환단계"].isin(transition_stages)
        ]
    if transition_schedule_status != "전체" and not transition_events.empty:
        transition_events = transition_events.loc[
            transition_events["일정상태"].eq(transition_schedule_status)
        ]

    if transition_events.empty:
        st.info("선택한 조건에 해당하는 설비 단계 전환 일정이 없습니다.")
    else:
        completed_count = int(transition_events["일정상태"].eq("완료").sum())
        planned_count = int(transition_events["일정상태"].eq("예정").sum())
        with st.container(horizontal=True):
            st.metric("전환 일정", f"{len(transition_events):,}건", border=True)
            st.metric("대상 호기", f"{transition_events['호기'].nunique():,}대", border=True)
            st.metric("완료", f"{completed_count:,}건", border=True)
            st.metric("예정", f"{planned_count:,}건", border=True)
            st.metric(
                "양산전환",
                f"{int(transition_events['전환단계'].eq('양산').sum()):,}건",
                border=True,
            )

        transition_summary = (
            transition_events.groupby(["전환단계", "일정상태"], observed=True)
            .size()
            .rename("전환건수")
            .reset_index()
        )
        transition_chart = (
            alt.Chart(transition_summary)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X(
                    "전환단계:N",
                    sort=transition_stage_options,
                    axis=alt.Axis(title=None, labelAngle=0, labelFontSize=12),
                ),
                y=alt.Y("전환건수:Q", axis=alt.Axis(title=None, tickMinStep=1)),
                color=alt.Color(
                    "일정상태:N",
                    scale=alt.Scale(
                        domain=["완료", "예정"],
                        range=["#2E8B57", "#4C78A8"],
                    ),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                tooltip=["전환단계:N", "일정상태:N", "전환건수:Q"],
            )
            .properties(height=210)
        )
        st.altair_chart(transition_chart, width="stretch")
        st.dataframe(
            transition_events,
            hide_index=True,
            width="stretch",
            column_config={
                "호기": st.column_config.TextColumn(pinned=True),
                "전환일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            },
        )
        st.caption(
            "완료 판정은 현재 호기 마스터에 입력된 완료일과 Space 기준일의 비교 결과입니다. "
            "현장 실행이 지연되거나 일정이 변경되면 가용설비 현황에서 날짜를 갱신하세요."
        )

with st.container(horizontal=True, gap="small", vertical_alignment="center"):
    if st.button(
        "S.PKG FAB 전체",
        icon=":material/domain:",
        type="primary" if selected_building is None else "secondary",
        key="space_status_fab_breadcrumb",
    ):
        _show_fab_overview()
        st.rerun()
    if selected_building:
        st.markdown(":material/chevron_right:")
        if st.button(
            f"{selected_building}동",
            type="primary" if selected_floor is None else "secondary",
            key="space_status_building_breadcrumb",
        ):
            _show_building(selected_building)
            st.rerun()
    if selected_building and selected_floor:
        st.markdown(":material/chevron_right:")
        st.button(
            selected_floor,
            type="primary",
            disabled=True,
            key="space_status_floor_breadcrumb",
        )

if selected_building is None:
    production_count, progress_count, inactive_count = fab_counts(located_equipment)
    with st.container(horizontal=True):
        st.metric("배치 호기", f"{len(located_equipment)}대", border=True)
        st.metric("양산", f"{production_count}대", border=True)
        st.metric("설치·전환 진행", f"{progress_count}대", border=True)
        st.metric("비가동", f"{inactive_count}대", border=True)
        st.metric("위치 미지정", f"{unlocated_count}대", border=True)

    with st.container(border=True):
        st.markdown("#### :material/domain: S.PKG FAB 전체 배치")
        building_event = st.plotly_chart(
            build_fab_figure(located_equipment),
            key="space_status_fab_chart",
            on_select="rerun",
            selection_mode="points",
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": False},
        )
        clicked_building = first_selected_customdata(building_event)
        if clicked_building in building_names and clicked_building != selected_building:
            _show_building(clicked_building)
            st.rerun()

    overview_rows = []
    for building in BUILDINGS:
        production, progress, inactive = building_counts(located_equipment, building.name)
        overview_rows.append(
            {
                "동": building.name,
                "층수": len(floors_for(building.name)),
                "양산대수": production,
                "진행대수": progress,
                "비가동대수": inactive,
            }
        )
    st.dataframe(pd.DataFrame(overview_rows), hide_index=True, width="stretch")

elif selected_floor is None:
    building_equipment = located_equipment.loc[located_equipment["동"].eq(selected_building)]
    production_count, progress_count, inactive_count = equipment_counts(building_equipment)
    building_floors = floors_for(selected_building)
    with st.container(horizontal=True):
        st.metric("선택 동", selected_building, border=True)
        st.metric("양산", f"{production_count}대", border=True)
        st.metric("설치·전환 진행", f"{progress_count}대", border=True)
        st.metric("비가동", f"{inactive_count}대", border=True)

    with st.container(border=True):
        st.markdown(f"#### :material/apartment: {selected_building}동 층별 현황")
        floor_event = st.plotly_chart(
            build_floor_figure(located_equipment, selected_building),
            key=f"space_status_floor_chart_{selected_building}",
            on_select="rerun",
            selection_mode="points",
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": False},
        )
        clicked_floor = first_selected_customdata(floor_event)
        if clicked_floor in valid_floor_names and clicked_floor != selected_floor:
            st.session_state[SELECTED_FLOOR_KEY] = clicked_floor
            st.rerun()

    floor_rows = []
    for floor in building_floors:
        floor_equipment = building_equipment.loc[building_equipment["층"].eq(floor.floor)]
        production, progress, inactive = equipment_counts(floor_equipment)
        floor_rows.append(
            {
                "층": floor.floor,
                "양산대수": production,
                "진행대수": progress,
                "비가동대수": inactive,
            }
        )
    st.dataframe(pd.DataFrame(floor_rows), hide_index=True, width="stretch")

else:
    floor_equipment = (
        located_equipment.loc[
            located_equipment["동"].eq(selected_building)
            & located_equipment["층"].eq(selected_floor)
        ]
        .copy()
        .reset_index(drop=True)
    )
    invalid_rows = invalid_equipment_rows(floor_equipment)
    if invalid_rows:
        st.warning("배치 영역을 벗어난 호기가 있습니다: " + ", ".join(map(str, invalid_rows)))

    production_count, progress_count, inactive_count = equipment_counts(floor_equipment)
    with st.container(horizontal=True):
        st.metric("선택 Space", f"{selected_building} {selected_floor}", border=True)
        st.metric("양산", f"{production_count}대", border=True)
        st.metric("설치·전환 진행", f"{progress_count}대", border=True)
        st.metric("비가동", f"{inactive_count}대", border=True)

    with st.container(border=True):
        st.markdown(f"#### :material/map: {selected_building} {selected_floor} 상세 레이아웃")
        st.caption(
            "높이는 고정값이며 사전 인프라부터 양산전환까지의 현재 단계와 운영 비가동을 "
            "색상으로 구분합니다."
        )
        st.plotly_chart(
            build_floor_layout_figure(floor_equipment, selected_building, selected_floor),
            key=f"space_status_layout_chart_{selected_building}_{selected_floor}",
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": False},
        )
    st.dataframe(
        floor_equipment,
        hide_index=True,
        width="stretch",
        column_config={
            column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
            for column in (
                "사전인프라완료일",
                "입고일",
                "Hookup완료일",
                "하드웨어셋업완료일",
                "Qual완료일",
                "TTTM완료일",
                "양산전환일",
            )
        },
    )
