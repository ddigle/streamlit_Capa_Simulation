# Purpose: FAB 전체에서 동·층·설비 배치로 이어지는 Space 현황 탐색 화면을 렌더링한다.

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.components.floor_layout_upload import render_floor_layout_editor
from capa_simulation.components.page_guide import render_page_guide
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
    equipment_unit_total,
    fab_counts,
    first_selected_customdata,
    floors_for,
    invalid_equipment_rows,
)
from capa_simulation.components.status_metric import metric_row
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    date_range_value,
)
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
from capa_simulation.services.equipment_units import (
    UNIT_COUNT_DECIMALS,
    UNIT_KEY_COLUMN,
    format_unit_count,
    placed_unit_rows,
    unit_transitions,
)
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

SELECTED_BUILDING_KEY = "space_status_selected_building"
SELECTED_FLOOR_KEY = "space_status_selected_floor"
# 아래 두 표의 위젯 키는 **고정이다.** 화면을 되돌렸을 때 옛 선택이 다시 읽혀 도로 끌려가는
# 덫은 이 버전에 없다 — Streamlit 은 그 회차에 그려지지 않은 위젯의 상태를 버리고(이
# 저장소의 탭·필터 초기화 문제가 바로 그 동작이다), 위 단계로 올라가면 아래 표는 그려지지
# 않는다. 예외는 **같은 분기 안에서 대상만 바뀌는** 층 표 하나라, 그것만 동 이름으로 키를
# 가른다(:439 의 층 도면과 같은 이유다).
BUILDING_TABLE_KEY = "space_status_building_table"
# 전환 단계 차트의 막대 폭(px). 단계는 여섯이 전부라 좁은 창에서도 칸이 이보다 넓다.
_TRANSITION_BAR_SIZE_PX = 70


def _show_fab_overview() -> None:
    st.session_state.pop(SELECTED_BUILDING_KEY, None)
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


def _show_building(building: str) -> None:
    st.session_state[SELECTED_BUILDING_KEY] = building
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


def _show_floor(floor: str) -> None:
    st.session_state[SELECTED_FLOOR_KEY] = floor


def _units(value: float) -> str:
    return f"{format_unit_count(value)}대"


def _render_space_counts(
    counts: tuple[float, float, float],
    *,
    key: str,
    leading: Sequence[tuple[str, str]] = (),
) -> None:
    """세 단계 화면이 공통으로 쓰는 `가용 / 설치·전환 진행 / 비가동` 카드 줄.

    앞에 화면별 카드를 끼울 수 있다. 대수는 설비지분 합이라 모듈 설비가 있으면 소수가
    나온다(`%,d` 서식은 0.75 를 0 으로 자른다). 그래서 카드 값은 모두 `format_unit_count`
    한 곳에서 만든 문자열이다 — 천단위 구분도 그 함수가 똑같이 붙인다.
    """
    production, progress, inactive = counts
    with metric_row(key=key):
        for label, value in leading:
            st.metric(label, value, border=True)
        st.metric("가용", _units(production), border=True)
        st.metric("설치·전환 진행", _units(progress), border=True)
        st.metric("비가동", _units(inactive), border=True)


# 동·층 표의 대수 칸. 설비지분 합이라 모듈 설비가 있으면 소수가 나온다.
_UNIT_COUNT_COLUMNS = {
    column: st.column_config.NumberColumn(format="localized")
    for column in ("가용대수", "진행대수", "비가동대수")
}


SPACE_CARD_LABEL = "Space 조건"
SPACE_CARD_NAME = "space"

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

render_page_header("Space 현황 (Data확보중)")
render_page_guide("space_status", title="Space 현황")
if using_sample_equipment:
    # 스위치는 호기 마스터가 비었을 때만 뜻이 있다. 실데이터가 있으면 끌 것이 없다.
    if not render_sample_switch(key="space_sample_switch", source="설비 운영 DB"):
        # 멈추기 **전에** 카드를 세우고 까닭을 적는다. 사이드바 「조회 조건」 제목은 페이지보다
        # 먼저 선언으로 서므로, 카드 없이 멈추면 제목만 덩그러니 남았다(2026-10-01 브라우저
        # 실측). 가용설비 현황의 같은 자리와 같은 모양이다.
        with condition_card(SPACE_CARD_LABEL, name=SPACE_CARD_NAME):
            st.caption("조회할 호기가 없습니다. 가용설비 현황에서 입력하거나 샘플 데이터를 켜세요.")
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
    st.caption("호기 마스터가 비어 있어 데모 fleet 을 표시합니다.")
elif latest_snapshot is not None:
    st.caption(
        f"적용 이력 r{latest_snapshot.revision.revision_no} · "
        f"{latest_snapshot.revision.created_at:%Y-%m-%d %H:%M}"
    )

# 기준일·필터와 단계 전환 조회 조건은 사이드바 조건 카드 `Space 조건` 이다(2026-09-29 사용자
# 결정). 기준일이 먼저다 — 공정·단계 선택지와 전환 조회기간의 기본값이 그 날에서 나온다.
space_card = condition_card(SPACE_CARD_LABEL, name=SPACE_CARD_NAME)
with space_card:
    as_of = st.date_input(
        "기준일",
        value=today,
        key="space_status_as_of",
        persist_state="session",
    )
    all_status = build_space_equipment_status(equipment, downtime, as_of=as_of)
    selected_processes = st.multiselect(
        "공정소분류",
        options=all_status["공정소분류"].dropna().drop_duplicates().tolist(),
        placeholder="전체",
        key="space_status_process_filter",
        persist_state="session",
    )
    selected_stages = st.multiselect(
        "단계",
        options=all_status["상태"].dropna().drop_duplicates().tolist(),
        placeholder="전체",
        key="space_status_stage_filter",
        persist_state="session",
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
# 그리는 행(located)과 세는 행(counted)을 가른다 — 배치는 설비 단위다. 상태·단계 필터는
# 일부러 설비를 쪼갠다(모듈 하나가 PM 이면 0.75). 여기서 되돌리지 않는다.
counted_equipment = placed_unit_rows(space_equipment, located_equipment)
unlocated_count = (
    round(
        equipment_unit_total(space_equipment) - equipment_unit_total(counted_equipment),
        UNIT_COUNT_DECIMALS,
    )
    + 0.0
)

transition_process_options = equipment["공정소분류"].dropna().drop_duplicates().tolist()
transition_stage_options = [label for _, label in MILESTONES]
with space_card:
    st.caption("단계 전환 현황")
    # 다섯 조건을 한 번에 바꿔 보는 조회라 폼으로 묶는다 — 칸마다 다시 그리지 않는다.
    with st.form("space_transition_event_filter_form", border=False):
        transition_range = st.date_input(
            "전환 조회기간",
            value=(as_of - timedelta(days=14), as_of + timedelta(days=14)),
            key="space_transition_event_range",
            persist_state="session",
        )
        transition_processes = st.multiselect(
            "공정소분류",
            options=transition_process_options,
            placeholder="전체",
            key="space_transition_process_filter",
            persist_state="session",
        )
        transition_stages = st.multiselect(
            "전환단계",
            options=transition_stage_options,
            placeholder="전체",
            key="space_transition_stage_filter",
            persist_state="session",
        )
        transition_schedule_status = st.selectbox(
            "일정상태",
            options=("전체", "완료", "예정"),
            key="space_transition_status_filter",
            persist_state="session",
        )
        transition_confirmation_statuses = st.multiselect(
            "Qual 확정상태",
            options=list(QUAL_CONFIRMATION_STATUSES),
            placeholder="전체",
            key="space_transition_confirmation_filter",
            persist_state="session",
        )
        st.form_submit_button("조회", icon=":material/search:", type="primary", width="stretch")

with st.container(border=True):
    st.markdown("#### :material/event_available: 기간 내 설비 단계 전환 현황")

    transition_start, transition_end = date_range_value(
        transition_range, (as_of - timedelta(days=14), as_of + timedelta(days=14))
    )

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
        # 건수는 **설비 단위**로 센다(`unit_transitions`). 아래 목록은 행 그대로 둔다.
        unit_events = unit_transitions(transition_events)
        completed_count = int(unit_events["일정상태"].eq("완료").sum())
        planned_count = int(unit_events["일정상태"].eq("예정").sum())
        confirmed_count = int(unit_events["Qual확정"].sum())
        with metric_row(key="space_transition_metrics"):
            st.metric("전환 일정", f"{len(unit_events):,}건", border=True)
            st.metric("대상 설비", f"{unit_events[UNIT_KEY_COLUMN].nunique():,}대", border=True)
            st.metric("완료", f"{completed_count:,}건", border=True)
            st.metric("예정", f"{planned_count:,}건", border=True)
            st.metric("Qual 확정·완료", f"{confirmed_count:,}건", border=True)

        transition_summary = (
            unit_events.groupby(["전환단계", "일정상태"], observed=True)
            .size()
            .rename("전환건수")
            .reset_index()
        )
        transition_chart = (
            alt.Chart(transition_summary)
            # 단계가 여섯뿐이라 폭을 두지 않으면 막대 하나가 400px 이 넘게 퍼져 둥근 머리가
            # 보이지 않는다. HOME 생산계획 LOB 막대와 같은 70px 로 세운다(단계 여섯이면 좁은
            # 창에서도 칸이 그보다 넓다). 굵기가 넓음 등급이라 반경 8px. 쌓인 막대는 Vega-Lite 가
            # 막대 전체를 잘라 둥글리므로 이음매는 네모로 남는다(브라우저 실측).
            .mark_bar(
                size=_TRANSITION_BAR_SIZE_PX,
                cornerRadiusTopLeft=tokens.BAR_CORNER_RADIUS_WIDE_PX,
                cornerRadiusTopRight=tokens.BAR_CORNER_RADIUS_WIDE_PX,
            )
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
        # 설비키는 모듈 행이 있을 때만 보인다. 비모듈 행은 호기와 같은 값이라 칸만 는다.
        has_modules = bool(transition_events[UNIT_KEY_COLUMN].ne(transition_events["호기"]).any())
        st.dataframe(
            transition_events,
            hide_index=True,
            width="stretch",
            column_config={
                "호기": st.column_config.TextColumn(pinned=True),
                "전환일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                UNIT_KEY_COLUMN: st.column_config.TextColumn("설비") if has_modules else None,
            },
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
    production_count, progress_count, inactive_count = fab_counts(counted_equipment)
    _render_space_counts(
        (production_count, progress_count, inactive_count),
        key="space_fab_counts",
        leading=(("배치 설비", _units(equipment_unit_total(counted_equipment))),),
    )
    st.metric("레이아웃 제외·미지정", _units(unlocated_count), border=True)

    with st.container(border=True):
        st.markdown("#### :material/domain: S.PKG FAB 전체 배치")
        building_event = st.plotly_chart(
            build_fab_figure(counted_equipment),
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
        production, progress, inactive = building_counts(counted_equipment, building.name)
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
        column_config=_UNIT_COUNT_COLUMNS,
        key=BUILDING_TABLE_KEY,
        on_select="rerun",
        selection_mode="single-row",
    )
    picked_building_rows = building_table.selection.rows
    if picked_building_rows:
        _show_building(str(overview_rows[picked_building_rows[0]]["동"]))
        st.rerun()

elif selected_floor is None:
    building_equipment = counted_equipment.loc[counted_equipment["동"].eq(selected_building)]
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
            build_floor_figure(counted_equipment, selected_building),
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
        column_config=_UNIT_COUNT_COLUMNS,
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

    production_count, progress_count, inactive_count = equipment_counts(
        counted_equipment.loc[
            counted_equipment["동"].eq(selected_building)
            & counted_equipment["층"].eq(selected_floor)
        ]
    )
    _render_space_counts(
        (production_count, progress_count, inactive_count),
        key="space_floor_counts",
        leading=(("선택 Space", f"{selected_building} {selected_floor}"),),
    )

    with st.container(border=True):
        st.markdown(f"#### :material/map: {selected_building} {selected_floor} 상세 레이아웃")
        # 작업 줄은 레이아웃 **위**다. 도면·캔버스 편집은 가끔 하는 쓰기라 팝업이다.
        render_floor_layout_editor(
            database_path=equipment_database_path,
            building=selected_building,
            floor=selected_floor,
            floor_equipment=floor_equipment,
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
