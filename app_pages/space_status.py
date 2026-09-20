# Purpose: FAB 전체에서 동·층·설비 배치로 이어지는 Space 현황 탐색 화면을 렌더링한다.

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.components.floor_layout_upload import render_floor_layout_editor
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.sample_data import (
    render_pending_source,
    render_sample_switch,
)
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
from capa_simulation.components.status_metric import metric_row
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.equipment_cache import (
    load_floor_layout_canvases,
    load_floor_layout_profile,
    load_floor_layout_summaries,
    load_latest_equipment_snapshot,
)
from capa_simulation.services.equipment_availability import (
    build_milestone_transition_events,
    build_space_equipment_status,
)
from capa_simulation.services.equipment_contract import (
    MILESTONES,
    QUAL_CONFIRMATION_STATUSES,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

SELECTED_BUILDING_KEY = "space_status_selected_building"
SELECTED_FLOOR_KEY = "space_status_selected_floor"
# 아래 두 표의 위젯 키는 **고정이다.** 화면을 되돌렸을 때 옛 선택이 다시 읽혀 도로 끌려가는
# 덫은 이 버전에 없다 — Streamlit 은 그 회차에 그려지지 않은 위젯의 상태를 버리고(이
# 저장소의 탭·필터 초기화 문제가 바로 그 동작이다), 위 단계로 올라가면 아래 표는 그려지지
# 않는다. 예외는 **같은 분기 안에서 대상만 바뀌는** 층 표 하나라, 그것만 동 이름으로 키를
# 가른다(:439 의 층 도면과 같은 이유다).
BUILDING_TABLE_KEY = "space_status_building_table"


def _show_fab_overview() -> None:
    st.session_state.pop(SELECTED_BUILDING_KEY, None)
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


def _show_building(building: str) -> None:
    st.session_state[SELECTED_BUILDING_KEY] = building
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


def _show_floor(floor: str) -> None:
    st.session_state[SELECTED_FLOOR_KEY] = floor


def _render_space_counts(
    counts: tuple[int, int, int],
    *,
    key: str,
    leading: Sequence[tuple[str, int | str]] = (),
) -> None:
    """세 단계 화면이 공통으로 쓰는 `가용 / 설치·전환 진행 / 비가동` 카드 줄.

    앞에 화면별 카드를 끼울 수 있다. 세 장은 정수를 그대로 넘기고 서식은 `format` 에
    맡긴다 — 문자열을 미리 만들면 천단위 구분이 자리마다 갈린다.
    """
    production, progress, inactive = counts
    with metric_row(key=key):
        for label, value in leading:
            st.metric(label, value, border=True)
        st.metric("가용", production, format="%,d대", border=True)
        st.metric("설치·전환 진행", progress, format="%,d대", border=True)
        st.metric("비가동", inactive, format="%,d대", border=True)


today = date.today()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    latest_snapshot = load_latest_equipment_snapshot(equipment_database_path)
    floor_canvases = load_floor_layout_canvases(equipment_database_path)
    floors_with_layout_image = {
        (summary.building, summary.floor)
        for summary in load_floor_layout_summaries(equipment_database_path)
        if summary.has_image
    }
    if latest_snapshot is None or latest_snapshot.equipment.empty:
        equipment = sample_equipment_master(anchor_date=today)
        downtime = sample_downtime_schedule(anchor_date=today)
        using_sample_equipment = True
    else:
        equipment = latest_snapshot.equipment
        downtime = latest_snapshot.downtime
        using_sample_equipment = False
except BOOTSTRAP_ERRORS as exc:
    st.error(
        "Space 설비 데이터를 준비하지 못했습니다: "
        + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
    )
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

render_page_header(
    "Space 현황 (Data확보중)",
    description=(
        "가용설비 현황과 동일한 설비 전용 DuckDB 리비전에서 호기 생애주기·비가동 상태와 "
        "Space 좌표를 조회합니다."
    ),
)
if using_sample_equipment:
    # 스위치는 호기 마스터가 비었을 때만 뜻이 있다. 실데이터가 있으면 끌 것이 없다.
    if not render_sample_switch(key="space_sample_switch", source="설비 운영 DB"):
        render_pending_source(
            subject="Space 현황",
            source="설비 운영 DB",
            expects=(
                "호기별 **동 · 층 · X좌표 · Y좌표 · Xsize · Ysize** — 배치도의 사각형 하나가 "
                "이 여섯 값입니다",
                "**레이아웃표시** 플래그 — 도면에 올릴 호기를 가릅니다",
                "동·층별 배경 도면 이미지와 캔버스 치수",
                "생애주기 상태를 만드는 일정 여섯 개와 운영 비가동 일정",
            ),
        )
        st.stop()
    st.caption(
        "호기 마스터가 비어 있어 생애주기·가용·운영 비가동 상태를 덮는 데모 fleet 을 "
        "표시합니다. 샘플은 DuckDB에 저장되지 않으며 실제 호기 리비전이 저장되면 자동으로 "
        "대체됩니다."
    )
elif latest_snapshot is not None:
    st.caption(
        f"적용 이력 r{latest_snapshot.revision.revision_no} · "
        f"{latest_snapshot.revision.created_at:%Y-%m-%d %H:%M}"
    )

with st.container(border=True):
    st.markdown("#### :material/event: Space 기준일·필터")
    with st.container(horizontal=True, gap="small"):
        as_of = st.date_input(
            "기준일",
            value=today,
            key="space_status_as_of",
            persist_state="session",
            width=180,
        )
        all_status = build_space_equipment_status(equipment, downtime, as_of=as_of)
        selected_processes = st.multiselect(
            "공정소분류",
            options=all_status["공정소분류"].dropna().drop_duplicates().tolist(),
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
    space_equipment = space_equipment.loc[space_equipment["공정소분류"].isin(selected_processes)]
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
    space_equipment["레이아웃반영여부"].fillna(False)
    & space_equipment["동"].notna()
    & space_equipment["층"].notna()
    & space_equipment[["X좌표", "Y좌표", "Xsize", "Ysize"]].notna().all(axis=1)
    & has_supported_location
].copy()
unlocated_count = len(space_equipment) - len(located_equipment)

with st.container(border=True):
    st.markdown("#### :material/event_available: 기간 내 설비 단계 전환 현황")
    st.caption(
        "선택 기간에 제진대·물류·입고·Qual·반출·이설 일정이 등록된 호기를 취합합니다. "
        "Space 기준일 이전 일정은 데이터상 완료, 이후 일정은 예정으로 구분합니다."
    )
    transition_process_options = equipment["공정소분류"].dropna().drop_duplicates().tolist()
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
                "공정소분류",
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
            transition_confirmation_statuses = st.multiselect(
                "Qual 확정상태",
                options=list(QUAL_CONFIRMATION_STATUSES),
                placeholder="전체",
                key="space_transition_confirmation_filter",
                persist_state="session",
                width=210,
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
            transition_events["공정소분류"].isin(transition_processes)
        ]
    if transition_stages and not transition_events.empty:
        transition_events = transition_events.loc[
            transition_events["전환단계"].isin(transition_stages)
        ]
    if transition_schedule_status != "전체" and not transition_events.empty:
        transition_events = transition_events.loc[
            transition_events["일정상태"].eq(transition_schedule_status)
        ]
    if transition_confirmation_statuses and not transition_events.empty:
        transition_events = transition_events.loc[
            transition_events["전환단계"].eq("Qual")
            & transition_events["확정상태"].isin(transition_confirmation_statuses)
        ]

    if transition_events.empty:
        st.info("선택한 조건에 해당하는 설비 단계 전환 일정이 없습니다.")
    else:
        completed_count = int(transition_events["일정상태"].eq("완료").sum())
        planned_count = int(transition_events["일정상태"].eq("예정").sum())
        with metric_row(key="space_transition_metrics"):
            st.metric("전환 일정", f"{len(transition_events):,}건", border=True)
            st.metric("대상 호기", f"{transition_events['호기'].nunique():,}대", border=True)
            st.metric("완료", f"{completed_count:,}건", border=True)
            st.metric("예정", f"{planned_count:,}건", border=True)
            st.metric(
                "Qual 확정·완료",
                (f"{int(transition_events['확정상태'].isin(['확정', '완료']).sum()):,}건"),
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
                        range=[tokens.SCHEDULE_DONE, tokens.SCHEDULE_PLANNED],
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
    _render_space_counts(
        (production_count, progress_count, inactive_count),
        key="space_fab_counts",
        leading=(("배치 호기", len(located_equipment)),),
    )
    st.metric("레이아웃 제외·미지정", unlocated_count, format="%,d대", border=True)

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
                "가용대수": production,
                "진행대수": progress,
                "비가동대수": inactive,
            }
        )
    # 도면의 표적은 Plotly SVG 마커라 포커스를 받지 못한다. 아래 동으로 내려가는 키보드
    # 길은 이 표다(행에 포커스를 두고 Shift+Space). 도면 클릭과 같은 자리로 이어진다.
    building_table = st.dataframe(
        pd.DataFrame(overview_rows),
        hide_index=True,
        width="stretch",
        key=BUILDING_TABLE_KEY,
        on_select="rerun",
        selection_mode="single-row",
    )
    picked_building_rows = building_table.selection.rows
    if picked_building_rows:
        _show_building(str(overview_rows[picked_building_rows[0]]["동"]))
        st.rerun()

elif selected_floor is None:
    building_equipment = located_equipment.loc[located_equipment["동"].eq(selected_building)]
    production_count, progress_count, inactive_count = equipment_counts(building_equipment)
    building_floors = floors_for(selected_building)
    _render_space_counts(
        (production_count, progress_count, inactive_count),
        key="space_building_counts",
        leading=(("선택 동", selected_building),),
    )

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
            _show_floor(clicked_floor)
            st.rerun()

    floor_rows = []
    for floor in building_floors:
        floor_equipment = building_equipment.loc[building_equipment["층"].eq(floor.floor)]
        production, progress, inactive = equipment_counts(floor_equipment)
        canvas = floor_canvases.get((selected_building, floor.floor))
        has_layout_image = (selected_building, floor.floor) in floors_with_layout_image
        floor_rows.append(
            {
                "층": floor.floor,
                "가용대수": production,
                "진행대수": progress,
                "비가동대수": inactive,
                "배치 도면": "등록" if has_layout_image else "미등록",
                "캔버스": (
                    f"{canvas[0]:g} × {canvas[1]:g}"
                    if canvas
                    else f"{DEFAULT_CANVAS_WIDTH:g} × {DEFAULT_CANVAS_HEIGHT:g}"
                ),
            }
        )
    # 층 도면도 같은 이유로 키보드 길이 없다. 위와 같은 표로 잇는다.
    floor_table = st.dataframe(
        pd.DataFrame(floor_rows),
        hide_index=True,
        width="stretch",
        key=f"space_status_floor_table_{selected_building}",
        on_select="rerun",
        selection_mode="single-row",
    )
    picked_floor_rows = floor_table.selection.rows
    if picked_floor_rows:
        _show_floor(str(floor_rows[picked_floor_rows[0]]["층"]))
        st.rerun()

else:
    floor_equipment = (
        located_equipment.loc[
            located_equipment["동"].eq(selected_building)
            & located_equipment["층"].eq(selected_floor)
        ]
        .copy()
        .reset_index(drop=True)
    )
    layout_profile = load_floor_layout_profile(
        equipment_database_path, selected_building, selected_floor
    )
    canvas_width, canvas_height = (
        layout_profile.canvas_size
        if layout_profile is not None
        else (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
    )
    invalid_rows = invalid_equipment_rows(
        floor_equipment, canvas_width=canvas_width, canvas_height=canvas_height
    )
    if invalid_rows:
        st.warning(
            f"캔버스 {canvas_width:g} × {canvas_height:g}를 벗어난 호기가 있습니다: "
            + ", ".join(map(str, invalid_rows))
        )

    production_count, progress_count, inactive_count = equipment_counts(floor_equipment)
    _render_space_counts(
        (production_count, progress_count, inactive_count),
        key="space_floor_counts",
        leading=(("선택 Space", f"{selected_building} {selected_floor}"),),
    )

    with st.container(border=True):
        st.markdown(f"#### :material/map: {selected_building} {selected_floor} 상세 레이아웃")
        st.caption(
            "Xsize·Ysize로 블럭 크기를 반영하고 호기의 입고·셋업·가용·반출·이설·보관·"
            "운영 비가동 상태를 색상으로 구분합니다."
        )
        st.plotly_chart(
            build_floor_layout_figure(
                floor_equipment,
                selected_building,
                selected_floor,
                background_image=(
                    layout_profile.image_data_uri if layout_profile is not None else None
                ),
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            ),
            key=f"space_status_layout_chart_{selected_building}_{selected_floor}",
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": False},
        )
        render_floor_layout_editor(
            database_path=equipment_database_path,
            building=selected_building,
            floor=selected_floor,
            floor_equipment=floor_equipment,
        )
    st.dataframe(
        floor_equipment,
        hide_index=True,
        width="stretch",
        # 아직 잡히지 않은 일정·메모 칸에 리터럴 "None" 이 찍혔다. 비워 두는 편이 맞다.
        placeholder="",
        column_config={
            column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
            for column in (
                "제진대일정",
                "물류일정",
                "입고일정",
                "Qual일정",
                "반출일정",
                "이설일",
            )
        },
    )
    # 층별 호기 목록은 현장 배치 검토에 그대로 쓰인다.
    render_csv_download(
        data=floor_equipment.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"space_{selected_building}_{selected_floor}.csv",
        key=f"space_floor_download_{selected_building}_{selected_floor}",
    )
