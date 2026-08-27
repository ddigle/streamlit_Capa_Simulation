from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.space_layout import (
    BUILDINGS,
    FLOORS,
    build_fab_figure,
    build_floor_figure,
    build_floor_layout_figure,
    building_counts,
    default_equipment,
    fab_counts,
    first_selected_customdata,
    floors_for,
    invalid_equipment_rows,
)

SELECTED_BUILDING_KEY = "space_status_selected_building"
SELECTED_FLOOR_KEY = "space_status_selected_floor"


def _show_fab_overview() -> None:
    st.session_state.pop(SELECTED_BUILDING_KEY, None)
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


def _show_building(building: str) -> None:
    st.session_state[SELECTED_BUILDING_KEY] = building
    st.session_state.pop(SELECTED_FLOOR_KEY, None)


building_names = {building.name for building in BUILDINGS}
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
    "S.PKG FAB의 동·층·설비 배치를 단계적으로 탐색하고, 위치별 가동·셋업 설비와 "
    "향후 Space Capa를 확인하는 화면입니다."
)
st.markdown(":gray-badge[인터랙티브 초안] :blue-badge[레이아웃·Capa 데이터 미연결]")
st.info(
    "현재 수량과 설비 좌표는 화면 동작 검토용 데모입니다. 추후 제공할 층별 레이아웃 "
    "이미지를 100×60 좌표계의 배경으로 넣고 실제 설비 목록·크기·좌표로 교체합니다.",
    icon=":material/info:",
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
    active_count, setup_count = fab_counts()
    with st.container(horizontal=True):
        st.metric("FAB 동", f"{len(BUILDINGS)}개", border=True)
        st.metric("전체 층", f"{len(FLOORS)}개", border=True)
        st.metric("가동 설비", f"{active_count}대", border=True)
        st.metric("셋업중 설비", f"{setup_count}대", border=True)
        st.metric("Space Capa", "—", border=True)

    with st.container(border=True):
        st.markdown("#### :material/domain: S.PKG FAB 전체 배치")
        st.caption("C5는 독립 배치되고 C1·C2·C3·C4는 좌측부터 서로 연결된 구조입니다.")
        building_event = st.plotly_chart(
            build_fab_figure(),
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
        building_active, building_setup = building_counts(building.name)
        overview_rows.append(
            {
                "동": building.name,
                "층수": len(floors_for(building.name)),
                "가동대수": building_active,
                "셋업중대수": building_setup,
                "Space Capa": None,
            }
        )
    st.dataframe(
        pd.DataFrame(overview_rows),
        hide_index=True,
        width="stretch",
        column_config={
            "동": st.column_config.TextColumn(pinned=True),
            "층수": st.column_config.NumberColumn(format="%d개 층"),
            "가동대수": st.column_config.NumberColumn(format="%d대"),
            "셋업중대수": st.column_config.NumberColumn(format="%d대"),
            "Space Capa": st.column_config.NumberColumn(format="%.2f"),
        },
    )

elif selected_floor is None:
    active_count, setup_count = building_counts(selected_building)
    building_floors = floors_for(selected_building)
    with st.container(horizontal=True):
        st.metric("선택 동", selected_building, border=True)
        st.metric("층수", f"{len(building_floors)}개", border=True)
        st.metric("가동 설비", f"{active_count}대", border=True)
        st.metric("셋업중 설비", f"{setup_count}대", border=True)
        st.metric("동 Capa", "—", border=True)

    with st.container(border=True):
        st.markdown(f"#### :material/apartment: {selected_building}동 층별 현황")
        st.caption("층 영역을 클릭하면 해당 층의 설비 배치도로 이동합니다.")
        floor_event = st.plotly_chart(
            build_floor_figure(selected_building),
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

    floor_rows = [
        {
            "층": floor.floor,
            "가동대수": floor.active_count,
            "셋업중대수": floor.setup_count,
            "Space Capa": None,
        }
        for floor in building_floors
    ]
    st.dataframe(
        pd.DataFrame(floor_rows),
        hide_index=True,
        width="stretch",
        column_config={
            "층": st.column_config.TextColumn(pinned=True),
            "가동대수": st.column_config.NumberColumn(format="%d대"),
            "셋업중대수": st.column_config.NumberColumn(format="%d대"),
            "Space Capa": st.column_config.NumberColumn(format="%.2f"),
        },
    )

else:
    equipment_state_key = f"space_status_equipment_{selected_building}_{selected_floor}"
    stored_equipment = st.session_state.get(equipment_state_key)
    if not isinstance(stored_equipment, pd.DataFrame):
        stored_equipment = default_equipment(selected_building, selected_floor)
        st.session_state[equipment_state_key] = stored_equipment

    layout_slot = st.container(border=True)
    with st.expander(
        "설비 좌표·크기 목록",
        icon=":material/edit_location_alt:",
        expanded=False,
    ):
        st.caption(
            "X·Y는 설비 좌측 하단 좌표이고, 너비·높이는 동일 좌표계의 크기입니다. "
            "값을 수정하면 위 배치도가 즉시 갱신됩니다."
        )
        edited_equipment = st.data_editor(
            stored_equipment,
            key=f"space_status_equipment_editor_{selected_building}_{selected_floor}",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "설비 ID": st.column_config.TextColumn(required=True, pinned=True),
                "공정": st.column_config.TextColumn(required=True),
                "X": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
                "Y": st.column_config.NumberColumn(min_value=0.0, max_value=60.0, step=1.0),
                "너비": st.column_config.NumberColumn(min_value=1.0, max_value=100.0, step=1.0),
                "높이": st.column_config.NumberColumn(min_value=1.0, max_value=60.0, step=1.0),
                "상태": st.column_config.SelectboxColumn(
                    options=["가동", "셋업중", "비가동"],
                    required=True,
                ),
            },
        )
        st.session_state[equipment_state_key] = edited_equipment.copy()
        if st.button(
            "데모 배치 초기화",
            icon=":material/restart_alt:",
            key=f"space_status_reset_{selected_building}_{selected_floor}",
        ):
            st.session_state[equipment_state_key] = default_equipment(
                selected_building,
                selected_floor,
            )
            st.session_state.pop(
                f"space_status_equipment_editor_{selected_building}_{selected_floor}",
                None,
            )
            st.rerun()

    invalid_rows = invalid_equipment_rows(edited_equipment)
    if invalid_rows:
        st.warning(
            "배치 영역을 벗어나거나 좌표·크기가 올바르지 않은 행이 있습니다: "
            + ", ".join(str(row) for row in invalid_rows)
        )

    active_count = int(edited_equipment["상태"].eq("가동").sum())
    setup_count = int(edited_equipment["상태"].eq("셋업중").sum())
    inactive_count = int(edited_equipment["상태"].eq("비가동").sum())
    with st.container(horizontal=True):
        st.metric("선택 Space", f"{selected_building} {selected_floor}", border=True)
        st.metric("가동", f"{active_count}대", border=True)
        st.metric("셋업중", f"{setup_count}대", border=True)
        st.metric("비가동", f"{inactive_count}대", border=True)
        st.metric("Space Capa", "—", border=True)

    with layout_slot:
        st.markdown(f"#### :material/map: {selected_building} {selected_floor} 상세 레이아웃")
        st.caption(
            "배경 이미지 미등록 · 현재는 100×60 좌표 캔버스입니다. 설비 객체에 마우스를 "
            "올리면 ID·공정·상태·좌표를 확인할 수 있습니다."
        )
        st.plotly_chart(
            build_floor_layout_figure(
                edited_equipment,
                selected_building,
                selected_floor,
            ),
            key=f"space_status_layout_chart_{selected_building}_{selected_floor}",
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": False},
        )
