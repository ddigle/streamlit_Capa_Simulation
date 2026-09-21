# Purpose: 층 배치 도면 업로드·캔버스 치수 편집·삭제 UI를 렌더링한다.

"""층 배치 도면 업로드·캔버스 치수 편집·삭제 UI를 렌더링한다."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.space_layout import invalid_equipment_rows
from capa_simulation.persistence.equipment_cache import (
    clear_floor_layout_cache,
    get_equipment_repository,
    load_floor_layout_profile,
)
from capa_simulation.services.floor_layout_profile import (
    ALLOWED_IMAGE_EXTENSIONS,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    MAX_CANVAS_EXTENT,
    MAX_FLOOR_LAYOUT_BYTES,
    MAX_TOTAL_LAYOUT_BYTES,
    MIN_CANVAS_EXTENT,
    RECOMMENDED_FLOOR_LAYOUT_BYTES,
    FloorLayoutProfile,
    canvas_from_pixel_size,
    format_bytes,
    image_pixel_size,
)

# 이 화면의 위젯 키는 모두 이 접두에서 파생한다. 리터럴 접두를 자리마다 다시
# 적으면 다른 모듈과 겹쳐도 `test_session_key_collisions` 가 볼 축이 없다.
FLOOR_LAYOUT_WIDGET_KEY = "space_floor_layout"
UPLOAD_NONCE_KEY = "space_floor_layout_upload_nonce"


def render_floor_layout_editor(
    *,
    database_path: str,
    building: str,
    floor: str,
    floor_equipment: pd.DataFrame,
) -> None:
    """한 층의 배경 도면과 캔버스 치수를 편집한다. 설비 리비전과 무관한 단일 저장값이다."""
    profile = load_floor_layout_profile(database_path, building, floor)
    with st.expander(f"{building} {floor} 배치 도면·캔버스", expanded=profile is None):
        st.caption(
            "도면은 설비 리비전이 아니라 동·층별 단일 저장값입니다. 새로 저장하면 이전 도면을 "
            f"덮어씁니다. {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))} 파일만 받고 층당 "
            f"{format_bytes(MAX_FLOOR_LAYOUT_BYTES)}, 전 층 합계 "
            f"{format_bytes(MAX_TOTAL_LAYOUT_BYTES)}까지 저장합니다. 도면 없이 캔버스 치수만 "
            "저장할 수도 있습니다."
        )
        _render_current_state(profile)

        nonce = int(st.session_state.get(UPLOAD_NONCE_KEY, 0))
        uploaded = st.file_uploader(
            "배치 도면 이미지",
            type=sorted(ALLOWED_IMAGE_EXTENSIONS),
            key=f"{FLOOR_LAYOUT_WIDGET_KEY}_uploader_{building}_{floor}_{nonce}",
        )
        payload = uploaded.getvalue() if uploaded is not None else None
        pixel_size = image_pixel_size(payload) if payload else None
        suggested = (
            canvas_from_pixel_size(*pixel_size)
            if pixel_size is not None
            else _current_canvas(profile)
        )
        if payload is not None and len(payload) > RECOMMENDED_FLOOR_LAYOUT_BYTES:
            st.warning(
                f"도면 용량이 {format_bytes(len(payload))}입니다. 설비 DuckDB는 통째로 "
                "동기화 대상이라 층마다 큰 도면을 두면 전송 시간이 함께 늘어납니다.",
                icon=":material/cloud_upload:",
            )

        auto_canvas = st.checkbox(
            "도면 종횡비로 캔버스 자동 계산",
            value=True,
            key=f"{FLOOR_LAYOUT_WIDGET_KEY}_auto_{building}_{floor}",
            help="끄면 폭·높이를 이 층에 맞게 직접 입력합니다.",
        )
        # 자동 계산이 켜져 있거나 새 도면이 올라오면 위젯 key 를 바꿔 계산값을 그대로 보여준다.
        canvas_scope = f"{'auto' if auto_canvas else 'manual'}_{suggested[0]:g}x{suggested[1]:g}"
        with st.container(horizontal=True, gap="small"):
            manual_width = st.number_input(
                "캔버스 폭",
                min_value=MIN_CANVAS_EXTENT,
                max_value=MAX_CANVAS_EXTENT,
                value=suggested[0],
                step=1.0,
                disabled=auto_canvas,
                key=f"{FLOOR_LAYOUT_WIDGET_KEY}_width_{building}_{floor}_{canvas_scope}",
                width=160,
            )
            manual_height = st.number_input(
                "캔버스 높이",
                min_value=MIN_CANVAS_EXTENT,
                max_value=MAX_CANVAS_EXTENT,
                value=suggested[1],
                step=1.0,
                disabled=auto_canvas,
                key=f"{FLOOR_LAYOUT_WIDGET_KEY}_height_{building}_{floor}_{canvas_scope}",
                width=160,
            )
        target_width = suggested[0] if auto_canvas else float(manual_width)
        target_height = suggested[1] if auto_canvas else float(manual_height)
        st.caption(f"적용될 캔버스: {target_width:g} × {target_height:g}")

        outside_rows = invalid_equipment_rows(
            floor_equipment,
            canvas_width=target_width,
            canvas_height=target_height,
        )
        shrink_confirmed = True
        if outside_rows:
            st.warning(
                f"이 캔버스에서는 {building} {floor} 호기 {len(outside_rows)}대가 범위를 "
                "벗어납니다. 이대로 저장하면 **가용설비 현황**의 호기 마스터 저장이 전부 "
                "막힙니다 — 저장은 마스터 전체를 한 번에 검증하므로 다른 동·층만 고쳐도 같은 "
                "오류가 납니다. 가용설비 현황에서 이 층 좌표를 먼저 고치세요.",
                icon=":material/warning:",
            )
            shrink_confirmed = st.checkbox(
                "이탈 호기를 알고도 이 캔버스로 저장",
                value=False,
                key=f"{FLOOR_LAYOUT_WIDGET_KEY}_shrink_{building}_{floor}",
            )

        with st.container(horizontal=True, gap="small"):
            save_clicked = st.button(
                "도면·캔버스 저장",
                icon=":material/save:",
                type="primary",
                disabled=not shrink_confirmed,
                key=f"{FLOOR_LAYOUT_WIDGET_KEY}_save_{building}_{floor}",
            )
            delete_clicked = st.button(
                "도면·캔버스 삭제",
                icon=":material/delete:",
                disabled=profile is None,
                key=f"{FLOOR_LAYOUT_WIDGET_KEY}_delete_{building}_{floor}",
            )

    if save_clicked:
        _save(
            database_path=database_path,
            building=building,
            floor=floor,
            uploaded_name=uploaded.name if uploaded is not None else None,
            payload=payload,
            canvas_width=target_width,
            canvas_height=target_height,
        )
    elif delete_clicked and profile is not None:
        get_equipment_repository(database_path).delete_floor_layout_profile(building, floor)
        clear_floor_layout_cache()
        st.session_state[UPLOAD_NONCE_KEY] = int(st.session_state.get(UPLOAD_NONCE_KEY, 0)) + 1
        st.rerun()


def _save(
    *,
    database_path: str,
    building: str,
    floor: str,
    uploaded_name: str | None,
    payload: bytes | None,
    canvas_width: float,
    canvas_height: float,
) -> None:
    repository = get_equipment_repository(database_path)
    try:
        if payload is not None and uploaded_name is not None:
            repository.save_floor_layout_image(
                building,
                floor,
                uploaded_name,
                payload,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
        else:
            # 도면 없이 캔버스 치수만 저장한다. 화면에서 확답한 값이 조용히 버려지지 않는다.
            repository.save_floor_layout_canvas(building, floor, canvas_width, canvas_height)
    except ValueError as exc:
        st.error(str(exc))
        return
    clear_floor_layout_cache()
    st.session_state[UPLOAD_NONCE_KEY] = int(st.session_state.get(UPLOAD_NONCE_KEY, 0)) + 1
    st.rerun()


def _render_current_state(profile: FloorLayoutProfile | None) -> None:
    if profile is None:
        st.info(
            "이 층에는 저장된 도면도 캔버스도 없습니다. 캔버스는 기본값 "
            f"{DEFAULT_CANVAS_WIDTH:g} × {DEFAULT_CANVAS_HEIGHT:g}로 그립니다.",
            icon=":material/image_not_supported:",
        )
        return
    if profile.image_data_uri is None:
        st.info(
            "이 층에는 배경 도면이 없고 캔버스 치수만 저장되어 있습니다. 배치도는 저장된 "
            f"{profile.canvas_width:g} × {profile.canvas_height:g}로 그립니다.",
            icon=":material/grid_on:",
        )
        return
    st.success(
        f"저장된 도면: {profile.image_name or '이름 없음'} · "
        f"{format_bytes(profile.image_byte_count)} · 캔버스 "
        f"{profile.canvas_width:g} × {profile.canvas_height:g} · "
        f"{profile.updated_at:%Y-%m-%d %H:%M}",
        icon=":material/map:",
    )


def _current_canvas(profile: FloorLayoutProfile | None) -> tuple[float, float]:
    if profile is None:
        return DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT
    return profile.canvas_size
