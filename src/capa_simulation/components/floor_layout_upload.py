# Purpose: Space 층·FAB 전체 도면의 배경 도면 업로드·캔버스 치수 편집·삭제 팝업을 렌더링한다.

"""Space 층·FAB 전체 도면의 배경 도면 업로드·캔버스 치수 편집·삭제 UI를 렌더링한다.

가끔 하는 쓰기라 본문을 차지하지 않고 레이아웃 위 작업 줄의 `도면·캔버스 편집` **팝업**이다
(2026-09-29 사용자 결정). 팝업은 fragment 라 저장·삭제가 성공하면 팝업 칸을 비우고 앱 전체를
다시 돌려 레이아웃이 새 도면으로 다시 그려진다.

층과 FAB 전체 도면이 **같은 팝업**을 범위(`_DrawingTarget`)만 바꿔 쓴다. 다른 것은 저장 자리(층 표 /
FAB 표), 기본 캔버스(100 × 60 / `FAB_CANVAS`), 캔버스 밖 검사의 대상(층은 호기와 저장된 도면 요소,
FAB 는
지금 그리는 요소 — 저장된 것이 없으면 기본 배치)과 저장 뒤 정리할 대기분이다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    rebase_fab_canvas,
    rebase_floor_canvas,
    stage_floor_canvas,
)
from capa_simulation.components.space_layout import invalid_equipment_rows
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
)
from capa_simulation.persistence.equipment_cache import (
    clear_floor_layout_cache,
    get_equipment_repository,
    load_fab_layout,
    load_floor_layout_marks,
    load_floor_layout_profile,
)
from capa_simulation.services.fab_layout import FAB_CANVAS, effective_fab_layout
from capa_simulation.services.floor_layout_mark import marks_extent
from capa_simulation.services.floor_layout_profile import (
    ALLOWED_IMAGE_EXTENSIONS,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    MAX_CANVAS_EXTENT,
    MAX_FLOOR_LAYOUT_BYTES,
    MAX_TOTAL_LAYOUT_BYTES,
    MIN_CANVAS_EXTENT,
    RECOMMENDED_FLOOR_LAYOUT_BYTES,
    CanvasSize,
    FloorKey,
    canvas_from_pixel_size,
    format_bytes,
    image_pixel_size,
    normalize_canvas_size,
)

# 이 화면의 위젯 키는 모두 이 접두에서 파생한다. 리터럴 접두를 자리마다 다시
# 적으면 다른 모듈과 겹쳐도 `test_session_key_collisions` 가 볼 축이 없다.
FLOOR_LAYOUT_WIDGET_KEY = "space_floor_layout"
UPLOAD_NONCE_KEY = "space_floor_layout_upload_nonce"
# 지금 열린 도면 팝업의 범위 — 층은 `동|층`, FAB 는 `FAB`. 페이지를 떠나면 `forget_page_dialogs` 가
# 비운다.
FLOOR_LAYOUT_DIALOG_KEY = f"space{PAGE_DIALOG_SUFFIX}"
FAB_DIALOG_SCOPE = "FAB"


class _DrawingProfile(Protocol):
    """팝업이 보는 저장된 도면 — 층(`FloorLayoutProfile`)과 FAB(`FabLayoutProfile`)가 함께
    맞는다."""

    @property
    def canvas_width(self) -> float: ...

    @property
    def canvas_height(self) -> float: ...

    @property
    def image_data_uri(self) -> str | None: ...

    @property
    def image_name(self) -> str | None: ...

    @property
    def image_byte_count(self) -> int: ...

    @property
    def updated_at(self) -> datetime: ...


@dataclass(frozen=True)
class _DrawingTarget:
    """팝업의 범위. `floor` 가 None 이면 FAB 전체 도면이다."""

    floor: FloorKey | None

    @property
    def scope(self) -> str:
        return FAB_DIALOG_SCOPE if self.floor is None else f"{self.floor[0]}|{self.floor[1]}"

    @property
    def key(self) -> str:
        """위젯 키 꼬리 — 층은 `C1_1F`, FAB 는 `FAB`."""
        return FAB_DIALOG_SCOPE if self.floor is None else f"{self.floor[0]}_{self.floor[1]}"

    @property
    def title(self) -> str:
        return "S.PKG FAB 전체" if self.floor is None else f"{self.floor[0]} {self.floor[1]}"

    @property
    def default_canvas(self) -> CanvasSize:
        return FAB_CANVAS if self.floor is None else (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)


# `st.file_uploader` 의 상한은 MB 정수다. 도면당 상한(바이트)을 올림해 넣는다 — 서버 쪽 검사는
# 그대로 바이트로 한다.
UPLOAD_LIMIT_MB = math.ceil(MAX_FLOOR_LAYOUT_BYTES / (1024 * 1024))


def render_floor_layout_editor(
    *,
    database_path: str,
    building: str,
    floor: str,
    floor_equipment: pd.DataFrame,
) -> None:
    """층 상세 작업 줄의 `도면·캔버스 편집` 버튼. 누르면 그 층의 팝업이 열린다."""
    _render_open_button(database_path, _DrawingTarget((building, floor)), floor_equipment)


def render_fab_layout_drawing_editor(*, database_path: str, disabled: bool = False) -> None:
    """FAB 전체 머리 줄의 `도면·캔버스 편집` 버튼. 층 팝업을 FAB 범위로 연다. `disabled` 는 설비
    샘플 화면(합성 fleet 을 보는 중)에서 쓰기를 막는다."""
    _render_open_button(database_path, _DrawingTarget(None), pd.DataFrame(), disabled=disabled)


def _render_open_button(
    database_path: str,
    target: _DrawingTarget,
    floor_equipment: pd.DataFrame,
    *,
    disabled: bool = False,
) -> None:
    st.button(
        "도면·캔버스 편집",
        icon=":material/map:",
        key=f"{FLOOR_LAYOUT_WIDGET_KEY}_open_{target.key}",
        on_click=_open_dialog,
        args=(target.scope,),
        disabled=disabled,
        help="샘플 데이터를 보는 중에는 FAB 도면을 고치지 않습니다." if disabled else None,
    )
    if not disabled and st.session_state.get(FLOOR_LAYOUT_DIALOG_KEY) == target.scope:
        _floor_layout_dialog(
            database_path=database_path, target=target, floor_equipment=floor_equipment
        )


def _open_dialog(scope: str) -> None:
    st.session_state[FLOOR_LAYOUT_DIALOG_KEY] = scope


def _close_dialog() -> None:
    st.session_state.pop(FLOOR_LAYOUT_DIALOG_KEY, None)


def _load_profile(database_path: str, target: _DrawingTarget) -> _DrawingProfile | None:
    if target.floor is None:
        return load_fab_layout(database_path)[0]
    return load_floor_layout_profile(database_path, *target.floor)


def _marks_extent(database_path: str, target: _DrawingTarget) -> CanvasSize:
    """캔버스를 이보다 줄일 수 없는 요소 범위. FAB 는 지금 그리는 요소(저장된 것이 없으면 기본
    배치)."""
    if target.floor is None:
        _, marks = effective_fab_layout(None, load_fab_layout(database_path)[1])
        return marks_extent(marks)
    return marks_extent(load_floor_layout_marks(database_path, *target.floor))


@st.dialog("배치 도면·캔버스", width="large", on_dismiss=_close_dialog)
def _floor_layout_dialog(
    *,
    database_path: str,
    target: _DrawingTarget,
    floor_equipment: pd.DataFrame,
) -> None:
    """한 범위(층·FAB)의 배경 도면과 캔버스 치수를 편집한다. 설비 리비전과 무관한 단일
    저장값이다."""
    profile = _load_profile(database_path, target)
    key = target.key
    default_width, default_height = target.default_canvas
    st.markdown(f"**{target.title}**")
    owner = "FAB 전체 도면의" if target.floor is None else "동·층별"
    st.caption(
        f"도면은 설비 리비전이 아니라 {owner} 단일 저장값입니다. 새로 저장하면 이전 도면을 "
        f"덮어씁니다. {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))} 파일만 받고 도면당 "
        f"{format_bytes(MAX_FLOOR_LAYOUT_BYTES)}, 전 층·FAB 합계 "
        f"{format_bytes(MAX_TOTAL_LAYOUT_BYTES)}까지 저장합니다. 도면 없이 캔버스 치수만 "
        "저장할 수도 있습니다."
    )
    _render_current_state(profile, target.default_canvas)

    nonce = int(st.session_state.get(UPLOAD_NONCE_KEY, 0))
    uploaded = st.file_uploader(
        "배치 도면 이미지",
        type=sorted(ALLOWED_IMAGE_EXTENSIONS),
        key=f"{FLOOR_LAYOUT_WIDGET_KEY}_uploader_{key}_{nonce}",
        # 올리기 칸의 안내(「…MB per file」)와 막는 크기를 도면당 상한에 맞춘다. 빼면 서버 전체
        # 상한(1GB)이 적혀 바로 위 「도면당 2.0MB」 문장과 어긋났다(2026-10-05 E2E).
        max_upload_size=UPLOAD_LIMIT_MB,
    )
    payload = uploaded.getvalue() if uploaded is not None else None
    pixel_size = image_pixel_size(payload) if payload else None
    suggested = (
        canvas_from_pixel_size(*pixel_size)
        if pixel_size is not None
        else (profile.canvas_width, profile.canvas_height)
        if profile is not None
        else target.default_canvas
    )
    if payload is not None and len(payload) > RECOMMENDED_FLOOR_LAYOUT_BYTES:
        st.warning(
            f"도면 용량이 {format_bytes(len(payload))}입니다. 설비 DuckDB는 통째로 "
            "동기화 대상이라 큰 도면을 두면 전송 시간이 함께 늘어납니다.",
            icon=":material/cloud_upload:",
        )

    auto_canvas = st.checkbox(
        "도면 종횡비로 캔버스 자동 계산",
        value=True,
        key=f"{FLOOR_LAYOUT_WIDGET_KEY}_auto_{key}",
        help="끄면 폭·높이를 직접 입력합니다.",
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
            key=f"{FLOOR_LAYOUT_WIDGET_KEY}_width_{key}_{canvas_scope}",
            width=160,
        )
        manual_height = st.number_input(
            "캔버스 높이",
            min_value=MIN_CANVAS_EXTENT,
            max_value=MAX_CANVAS_EXTENT,
            value=suggested[1],
            step=1.0,
            disabled=auto_canvas,
            key=f"{FLOOR_LAYOUT_WIDGET_KEY}_height_{key}_{canvas_scope}",
            width=160,
        )
    target_width = suggested[0] if auto_canvas else float(manual_width)
    target_height = suggested[1] if auto_canvas else float(manual_height)
    st.caption(f"적용될 캔버스: {target_width:g} × {target_height:g}")

    shrink_confirmed = True
    if target.floor is not None:
        outside_rows = invalid_equipment_rows(
            floor_equipment,
            canvas_width=target_width,
            canvas_height=target_height,
        )
        if outside_rows:
            st.warning(
                f"이 캔버스에서는 {target.title} 호기 {len(outside_rows)}행이 범위를 "
                "벗어납니다. 이대로 저장하면 **가용설비 현황**의 호기 마스터 저장이 전부 "
                "막힙니다 — 저장은 마스터 전체를 한 번에 검증하므로 다른 동·층만 고쳐도 같은 "
                "오류가 납니다. 가용설비 현황에서 이 층 좌표를 먼저 고치세요.",
                icon=":material/warning:",
            )
            shrink_confirmed = st.checkbox(
                "이탈 호기를 알고도 이 캔버스로 저장",
                value=False,
                key=f"{FLOOR_LAYOUT_WIDGET_KEY}_shrink_{key}",
            )

    # 도면 요소(반입구·문·영역·층 블록 …)는 호기와 달리 캔버스 밖에 둘 수 없다 — 저장소가 거부한다.
    # 누르기 전에 말하고 단추를 막는다. 지우기는 캔버스가 기본 크기로 돌아가므로 그 크기로 본다.
    mark_right, mark_top = _marks_extent(database_path, target)
    marks_outside = mark_right > target_width + 1e-9 or mark_top > target_height + 1e-9
    if marks_outside:
        st.warning(
            f"이 캔버스에서는 {target.title} 도면 요소가 범위를 벗어나 저장할 수 없습니다"
            f"(필요한 크기 {mark_right:g} × {mark_top:g}). Space 배치 편집에서 요소를 옮기세요.",
            icon=":material/warning:",
        )
    delete_blocked = mark_right > default_width + 1e-9 or mark_top > default_height + 1e-9
    with st.container(horizontal=True, gap="small"):
        save_clicked = st.button(
            "도면·캔버스 저장",
            icon=":material/save:",
            type="primary",
            disabled=not shrink_confirmed or marks_outside,
            key=f"{FLOOR_LAYOUT_WIDGET_KEY}_save_{key}",
        )
        delete_clicked = st.button(
            "도면·캔버스 삭제",
            icon=":material/delete:",
            disabled=profile is None or delete_blocked,
            help=(
                "지우면 캔버스가 기본 "
                f"{default_width:g} × {default_height:g} 로 돌아가는데 그 밖에 도면 "
                "요소가 있어 지울 수 없습니다. 도면 요소는 지워도 남습니다."
                if delete_blocked
                else "배경 도면과 캔버스 치수를 지웁니다. 도면 요소는 남습니다."
            ),
            key=f"{FLOOR_LAYOUT_WIDGET_KEY}_delete_{key}",
        )

    written: CanvasSize | None = None
    if save_clicked:
        if not _save(
            database_path=database_path,
            target=target,
            uploaded_name=uploaded.name if uploaded is not None else None,
            payload=payload,
            canvas_width=target_width,
            canvas_height=target_height,
        ):
            return
        # 저장소가 맞춘 값과 같은 정밀도로(대기분 기준값과 견줄 때 어긋나지 않게).
        written = normalize_canvas_size(target_width, target_height)
    elif delete_clicked and profile is not None:
        try:
            repository = get_equipment_repository(database_path)
            if target.floor is None:
                repository.delete_fab_layout_profile()
            else:
                repository.delete_floor_layout_profile(*target.floor)
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc, database_paths=(Path(database_path),)))
            return
        clear_floor_layout_cache()
    else:
        return
    # 이 범위의 Space 미저장 캔버스는 버린다. 남겨 두면 팝업이 저장한 값을 가리고, 다음 저장이 옛
    # 대기값으로 되돌린다. 미저장 호기 좌표·도면 요소는 그대로 둔다 — 다음 저장이 새 캔버스로 다시
    # 검증해 밖이면 막는다. 이 세션의 대기분이 본 캔버스도 방금 쓴 값으로 바꾼다(남의 변경으로
    # 오인하지 않게).
    if target.floor is None:
        rebase_fab_canvas(written)
    else:
        rebase_floor_canvas(target.floor, written)
        stage_floor_canvas(target.floor, None)
    st.session_state[UPLOAD_NONCE_KEY] = int(st.session_state.get(UPLOAD_NONCE_KEY, 0)) + 1
    _close_dialog()
    st.rerun()


def _save(
    *,
    database_path: str,
    target: _DrawingTarget,
    uploaded_name: str | None,
    payload: bytes | None,
    canvas_width: float,
    canvas_height: float,
) -> bool:
    """저장하고 성공 여부를 돌려준다. 막히면 그 까닭을 팝업 안에 쓴다."""
    repository = get_equipment_repository(database_path)
    try:
        if payload is not None and uploaded_name is not None:
            if target.floor is None:
                repository.save_fab_layout_image(
                    uploaded_name,
                    payload,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                )
            else:
                repository.save_floor_layout_image(
                    *target.floor,
                    uploaded_name,
                    payload,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                )
        elif target.floor is None:
            repository.save_fab_layout_canvas(canvas_width, canvas_height)
        else:
            # 도면 없이 캔버스 치수만 저장한다. 화면에서 확답한 값이 조용히 버려지지 않는다.
            repository.save_floor_layout_canvas(*target.floor, canvas_width, canvas_height)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc, database_paths=(Path(database_path),)))
        return False
    clear_floor_layout_cache()
    return True


def _render_current_state(profile: _DrawingProfile | None, default_canvas: CanvasSize) -> None:
    if profile is None:
        st.info(
            "저장된 도면도 캔버스도 없습니다. 캔버스는 기본값 "
            f"{default_canvas[0]:g} × {default_canvas[1]:g}로 그립니다.",
            icon=":material/image_not_supported:",
        )
        return
    if profile.image_data_uri is None:
        st.info(
            "배경 도면이 없고 캔버스 치수만 저장되어 있습니다. 배치도는 저장된 "
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
