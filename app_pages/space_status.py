# Purpose: FAB 전체에서 동·층·설비 배치로 이어지는 Space 현황 탐색 화면을 렌더링한다.

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    Frames,
    effective_floor_canvases,
    ensure_equipment_drafts,
    equipment_buffer_generation,
    pending_floor_canvases,
    pending_floor_marks,
    pop_discarded_notice,
    pop_drafts_replaced,
    replace_equipment_buffer,
    reset_equipment_drafts,
    revision_token,
    save_equipment_buffer,
    stage_floor_canvas,
    stage_floor_marks,
)
from capa_simulation.components.flash import queue_flash, render_flash
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
    equipment_unit_total,
    first_selected_customdata,
    floors_for,
    invalid_equipment_rows,
    occupancy_ratio,
    stage_counts,
    stage_legend_markup,
)
from capa_simulation.components.space_layout_editor import (
    render_space_layout_editor,
    render_space_layout_viewer,
)
from capa_simulation.components.status_metric import metric_row
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_floor_layout_canvases,
    load_floor_layout_marks,
    load_floor_layout_profile,
    load_floor_layout_summaries,
    load_latest_equipment_snapshot,
)
from capa_simulation.services.equipment_availability import build_space_equipment_status
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)
from capa_simulation.services.equipment_units import format_unit_count, placed_unit_rows
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.floor_layout_mark import FloorLayoutMark, marks_fingerprint
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    FloorKey,
    FloorLayoutProfile,
)
from capa_simulation.services.space_layout_edit import (
    apply_layout_edits,
    editor_inputs,
    layout_changes,
    layout_warnings,
    new_unit_options,
    other_change_count,
    parse_editor_apply,
    unsaved_unit_ids,
    viewer_items,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

SELECTED_BUILDING_KEY = "space_status_selected_building"
SELECTED_FLOOR_KEY = "space_status_selected_floor"
# 아래 두 표의 위젯 키는 **고정이다.** 화면을 되돌렸을 때 옛 선택이 다시 읽혀 도로 끌려가는
# 덫은 이 버전에 없다 — Streamlit 은 그 회차에 그려지지 않은 위젯의 상태를 버리고(이
# 저장소의 탭·필터 초기화 문제가 바로 그 동작이다), 위 단계로 올라가면 아래 표는 그려지지
# 않는다. 예외는 **같은 분기 안에서 대상만 바뀌는** 층 표 하나라, 그것만 동 이름으로 키를
# 가른다(층 도면과 같은 이유다).
BUILDING_TABLE_KEY = "space_status_building_table"
# 배치 편집. 저장 알림·메모는 가용설비 현황의 키(`FLASH_KEY`·`_NOTE_KEY`)를 쓰지 않는다 — 그쪽
# 페이지가 소비해 엉뚱한 화면에 뜬다. 메모 칸은 저장할 때마다 키를 바꿔 비운다.
SPACE_FLASH_KEY = "space_status_flash"
EDIT_MODE_KEY = "space_layout_edit_mode"
SAVE_NOTE_KEY = "space_layout_save_note"
SAVE_NOTE_NONCE_KEY = "space_layout_save_note_nonce"
SAVE_ERROR_KEY = "space_layout_save_error"
SAVE_BUTTON_KEY = "space_layout_save"
DISCARD_BUTTON_KEY = "space_layout_discard"
# 반출·이설을 마친 호기는 더 이상 공간에 없다. 배치·미배치·제외 어디에도 세지 않는다.
EXITED_STATUSES = ("반출 완료", "이설 완료")


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


def _units_by(frame: pd.DataFrame, column: str) -> dict[str, float]:
    """`column` 값마다 설비 대수(설비지분 합). 값이 빈 행은 세지 않는다."""
    rows = frame.dropna(subset=[column])
    return {str(name): equipment_unit_total(group) for name, group in rows.groupby(column)}


def _render_placement_cards(cards: Sequence[tuple[str, str, str | None]], *, key: str) -> None:
    """세 단계 화면이 공통으로 쓰는 배치 카드 줄. 대수는 설비지분 합이라 모듈 설비가 있으면
    소수가 나온다(`%,d` 서식은 0.75 를 0 으로 자른다) — 값은 모두 `format_unit_count` 로 만든다."""
    with metric_row(key=key):
        for label, value, help_text in cards:
            st.metric(label, value, border=True, help=help_text)


_PLACED_HELP = "도면에 그린 설비입니다. 모체호기로 묶은 모듈 행은 합쳐 1대입니다."
_UNPLACED_HELP = "레이아웃표시 Y 인데 좌표가 없어 도면에 그리지 못한 설비입니다."
_EXCLUDED_HELP = "레이아웃표시 N — 도면 대상이 아닌 설비입니다."
_OCCUPANCY_HELP = (
    "도면에 그린 호기 사각형 면적 합 ÷ 캔버스 면적. 캔버스 단위의 상대값이며 "
    "겹친 자리는 두 번 셉니다."
)
_DRAWINGS_HELP = "배경 도면 이미지를 올린 층 수입니다."
# 동·층 표의 대수·비율 칸. 대수는 설비지분 합이라 모듈 설비가 있으면 소수가 나온다.
_TABLE_COLUMNS = {
    "배치대수": st.column_config.NumberColumn(format="localized", help=_PLACED_HELP),
    "미배치대수": st.column_config.NumberColumn(format="localized", help=_UNPLACED_HELP),
    "점유율": st.column_config.NumberColumn(format="percent", help=_OCCUPANCY_HELP),
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

# 본문 머리에는 상태 배지(「Data확보중」)도 적용 이력 줄도 두지 않는다 — 배치도가 쓸 자리다
# (2026-10-01 사용자 결정). 사이드바 메뉴 이름은 그대로다.
render_page_header("Space 현황 (Data확보중)", show_status=False)
render_page_guide("space_status", title="Space 현황")
render_flash(SPACE_FLASH_KEY)
# 배치 편집은 실제 저장본이 있을 때만 — 합성 데모 fleet 을 편집본에 섞으면 첫 실제 저장이 막힌다.
editable = not using_sample_equipment and latest_snapshot is not None
if editable:
    # 가용설비 RawData 와 **같은 편집본**이다. 어느 페이지를 먼저 열어도 같은 저장본 토큰으로 선다.
    buffer_frames: Frames = ensure_equipment_drafts(latest_snapshot)
    # 이 화면에는 RawData 제출이 없지만 표시를 여기서 읽어 버린다 — 남기면 가용설비 현황의 다음
    # 회차가 정상 제출까지 막는다.
    pop_drafts_replaced()
    discarded_notice = pop_discarded_notice()
    if discarded_notice:
        st.warning(discarded_notice, icon=":material/sync_problem:")
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

# 기준일·필터는 사이드바 조건 카드 `Space 조건` 이다(2026-09-29 사용자 결정). 기준일이 먼저다 —
# 공정·단계 선택지가 그 날의 상태에서 나온다. 이 화면은 배치·공간만 본다 — 기간별 단계 전환은
# 가용설비 현황 Main 의 「단계 전환」이다(2026-10-01 사용자 결정).
with condition_card(SPACE_CARD_LABEL, name=SPACE_CARD_NAME):
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
# 도면에 서지 않은 설비는 둘로 가른다. 레이아웃표시 Y 면 「미배치」(좌표를 넣으면 설 자리가 있다),
# N 이면 「레이아웃 제외」. 반출·이설을 마친 호기는 공간에 없으니 어디에도 세지 않는다.
exited = space_equipment["상태"].isin(EXITED_STATUSES)
not_placed = space_equipment.loc[~space_equipment.index.isin(counted_equipment.index) & ~exited]
wants_layout = not_placed["레이아웃표시"].eq("Y").fillna(False)
unplaced_equipment = not_placed.loc[wants_layout]
excluded_equipment = not_placed.loc[~wants_layout]
exited_count = equipment_unit_total(space_equipment.loc[exited])
# 동·층이 정해지지 않은 미배치는 동·층 집계에 들어갈 자리가 없다. 위 단계 카드 = 아래 단계 합 +
# 미정이 되도록 단계마다 따로 말한다(층 화면 카드에 더하면 여러 층에서 거듭 세어진다).
building_unknown = unplaced_equipment["동"].isna()


def _canvas_of(building: str, floor: str) -> tuple[float, float]:
    return floor_canvases.get((building, floor), (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT))


# 「다른 층으로 보내기」 목록 순서 — C1 1F, C1 2F, … (그림의 동·층 배치 순서가 아니라 이름 순).
ALL_FLOORS: tuple[FloorKey, ...] = tuple(
    sorted(
        (building.name, floor.floor)
        for building in BUILDINGS
        for floor in floors_for(building.name)
    )
)


def _render_unsaved_layout_panel(frames: Frames) -> None:
    """저장 안 한 배치 변경(호기 배치·편집 영역·도면 요소)과 저장·버리기. 어느 단계 화면에서나 뜬다.

    저장은 가용설비 RawData 와 같은 `save_equipment_buffer` 다 — 편집본 전체를 저장하므로 RawData
    의 저장 안 한 다른 편집도 함께 들어간다. 그 사실을 건수로 말한다.
    """
    assert latest_snapshot is not None
    # 저장 오류는 상자를 그리지 않는 회차에도 한 번만 보이고 버린다(남의 저장으로 편집이 버려진
    # 회차에는 상자가 없다). 남겨 두면 나중의 상관없는 적용 옆에 다시 뜬다.
    error = st.session_state.pop(SAVE_ERROR_KEY, None)
    changes = layout_changes(latest_snapshot.equipment, frames[1])
    canvases = pending_floor_canvases()
    marks = pending_floor_marks()
    if changes.empty and not canvases and not marks:
        if isinstance(error, str):
            st.error(f"배치를 저장하지 못했습니다: {error}")
        return
    parts = [f"호기 배치 {len(changes)}건"] if not changes.empty else []
    if canvases:
        parts.append(f"편집 영역 {len(canvases)}개 층")
    if marks:
        parts.append(f"도면 요소 {len(marks)}개 층")
    others = other_change_count(latest_snapshot.equipment, frames[1])
    with st.container(border=True, key="space_unsaved_layout_panel"):
        st.markdown(f"**:material/edit_note: 저장 안 한 배치 변경** — {' · '.join(parts)}")
        st.caption(
            "적용한 변경은 이 화면(세션)에만 있습니다. 저장해야 위 카드·도면과 다른 사람 화면에 "
            "반영됩니다."
            + (
                f" 가용설비 현황 RawData 의 저장 안 한 다른 편집 {others}건도 함께 저장됩니다."
                if others
                else ""
            )
        )
        if not changes.empty:
            with st.expander(f"바뀐 호기 {len(changes)}건"):
                st.dataframe(changes, hide_index=True, width="stretch")
        try:
            status = build_space_equipment_status(frames[1], frames[2], as_of=as_of)
        except ValueError as exc:
            # RawData 의 검증 실패 편집이 편집본에 남아 있다. 경고만 건너뛰고 저장·버리기는 둔다
            # (저장하면 같은 까닭으로 막히고, 버리면 풀린다).
            st.caption(
                ":material/error: 가용설비 현황 RawData 에 검증을 통과하지 못한 저장 안 한 편집이 "
                f"있어 겹침 경고를 계산하지 못했습니다: {exc}"
            )
        else:
            warnings = layout_warnings(status, {**_stored_marks_for(status, set(marks)), **marks})
            for warning in warnings:
                st.caption(f":material/warning: {warning}")
        if isinstance(error, str):
            st.error(f"저장하지 못했습니다: {error}")
        note_key = f"{SAVE_NOTE_KEY}_{int(st.session_state.get(SAVE_NOTE_NONCE_KEY, 0))}"
        # 저장·버리기는 **콜백**이다. 본문에서 저장하고 `st.rerun()` 하면 이 상자 아래 위젯
        # (층 상세의 `배치 편집` 토글 등)이 그 회차에 그려지지 않은 것으로 끝나 상태가 버려진다 —
        # 저장하자마자 편집기가 꺼졌다(2026-10-01 브라우저 확인). 콜백은 다음 회차 전에 돈다.
        with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
            st.text_input(
                "변경 메모", key=note_key, placeholder="예: C1 1F 반입구 앞 정리", width=360
            )
            st.button(
                "배치 저장",
                type="primary",
                icon=":material/save:",
                key=SAVE_BUTTON_KEY,
                on_click=_save_space_layout,
                args=(frames, note_key, equipment_database_path),
            )
            with st.popover("버리기", icon=":material/undo:"):
                st.caption(
                    "저장 안 한 설비 편집을 모두 버리고 최신 저장본으로 돌아갑니다. 가용설비 "
                    "RawData 의 저장 안 한 편집도 함께 버려집니다."
                )
                st.button("모두 버리기", key=DISCARD_BUTTON_KEY, on_click=_discard_space_layout)


def _discard_space_layout() -> None:
    """`모두 버리기` 콜백. 편집본·대기분과 함께 남은 저장 오류도 버린다."""
    st.session_state.pop(SAVE_ERROR_KEY, None)
    reset_equipment_drafts()


def _save_space_layout(frames: Frames, note_key: str, database_path: str) -> None:
    """`배치 저장` 콜백. 편집본(세 표)과 미저장 층 배치를 한 번에 쓰고 알림을 남긴다."""
    note = st.session_state.get(note_key)
    try:
        message = save_equipment_buffer(
            get_equipment_repository(database_path),
            frames,
            note if isinstance(note, str) else "",
            revision_optional=True,
        )
    except BOOTSTRAP_ERRORS as exc:
        # 검증·충돌(ValueError)만이 아니라 DuckDB 잠금 같은 저장 실패도 문구로 남긴다 — 콜백에서
        # 터지면 화면 전체가 오류 상자가 된다.
        st.session_state[SAVE_ERROR_KEY] = bootstrap_error_message(
            exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)
        )
        return
    st.session_state[SAVE_NOTE_NONCE_KEY] = int(st.session_state.get(SAVE_NOTE_NONCE_KEY, 0)) + 1
    queue_flash(SPACE_FLASH_KEY, message)


def _stored_marks_for(
    status: pd.DataFrame, pending: set[FloorKey]
) -> dict[FloorKey, tuple[FloorLayoutMark, ...]]:
    """경고에 필요한 층의 저장된 도면 요소 — 편집본에 좌표가 선 호기가 있고 대기 요소가 없는 층만.
    모든 층(30개)을 읽으면 회차마다 느려지고 요소 캐시(층 단위 항목)가 밀려난다."""
    placed = status.loc[status[["X좌표", "Y좌표"]].notna().all(axis=1), ["동", "층"]].dropna()
    floors = {(str(building), str(floor)) for building, floor in placed.itertuples(index=False)}
    return {
        key: load_floor_layout_marks(equipment_database_path, *key)
        for key in sorted(floors & set(ALL_FLOORS))
        if key not in pending
    }


def _render_layout_editor(
    frames: Frames, building: str, floor: str, profile: FloorLayoutProfile | None
) -> None:
    """한 층 배치 편집기. 편집본을 그리고, `적용` 이 오면 검증해 편집본·대기분에 얹는다."""
    assert latest_snapshot is not None
    key: FloorKey = (building, floor)
    canvases = effective_floor_canvases(floor_canvases)
    canvas = canvases.get(key, (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT))
    stored_marks = load_floor_layout_marks(equipment_database_path, building, floor)
    marks = pending_floor_marks().get(key, stored_marks)
    try:
        status = build_space_equipment_status(frames[1], frames[2], as_of=as_of)
    except ValueError as exc:
        st.error(
            "가용설비 현황 RawData 에 검증을 통과하지 못한 저장 안 한 편집이 있어 배치 편집기를 "
            f"열 수 없습니다. RawData 에서 고치거나 버린 뒤 여세요: {exc}"
        )
        return
    new_ids, arrived_ids = unsaved_unit_ids(latest_snapshot.equipment, frames[1], key)
    inputs = editor_inputs(status, floor=key, new_ids=new_ids, arrived_ids=arrived_ids)
    options = new_unit_options(frames[1])
    st.caption(
        "끌어 놓아 자리·크기를 고치고 **적용**을 누르면 이 세션의 편집본에 들어갑니다(저장 전). "
        "조건 카드의 공정·단계 필터와 상관없이 이 층의 도면 대상 호기를 모두 보입니다. "
        "층이 정해지지 않은 미배치 호기는 트레이에 함께 뜹니다. 기준일을 바꿔 편집 대상 호기가 "
        "달라지면 적용하지 않은 편집은 버려집니다."
    )
    # epoch: 층·저장본·편집본 세대·이 층 캔버스·요소·**편집 대상 호기 목록**. 하나라도 바뀌면
    # 브라우저가 새 값으로 다시 선다. 같으면 진행 중인 편집과 확대 배율을 지킨다. 호기 목록은
    # 기준일로도 바뀐다(반출·이설을 마친 호기가 빠진다) — 빠뜨리면 브라우저가 옛 목록을 쥔 채
    # 「이 편집기에 없는 호기」로 적용 전체가 거부된다.
    roster = hashlib.sha256(
        "|".join(f"{item['id']}:{int(bool(item['placed']))}" for item in inputs.items).encode()
    ).hexdigest()[:16]
    epoch = "|".join(
        (
            building,
            floor,
            revision_token(latest_snapshot),
            str(equipment_buffer_generation()),
            f"{canvas[0]:g}x{canvas[1]:g}",
            marks_fingerprint(marks),
            roster,
        )
    )
    submission = render_space_layout_editor(
        key=f"space_layout_editor_{building}_{floor}",
        epoch=epoch,
        title=f"{building} {floor}",
        inputs=inputs,
        canvas=canvas,
        floor=key,
        floors=ALL_FLOORS,
        marks=marks,
        new_unit=options,
        background_image=profile.image_data_uri if profile is not None else None,
    )
    if submission is None:
        return
    if submission.stale:
        st.warning("편집기가 새 값으로 다시 서는 사이에 누른 적용이라 반영하지 않았습니다.")
        return
    try:
        applied = parse_editor_apply(
            submission.payload,
            editor_ids={str(item["id"]) for item in inputs.items},
            master_ids=set(frames[1]["호기"].dropna().astype(str).str.strip()),
            floor=key,
            floors=ALL_FLOORS,
            canvas=canvas,
            unit_options=options,
        )
        next_canvases = {**canvases, **({key: applied.canvas} if applied.canvas else {})}
        master = apply_layout_edits(
            frames[1],
            applied,
            floor=key,
            canvases=next_canvases,
            default_canvas=(DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT),
        )
        # 저장 때와 같은 검사를 지금 한다 — 저장 단추에서야 막히면 무엇이 문제인지 멀어진다.
        prepare_equipment_master(master, floor_canvases=next_canvases)
    except ValueError as exc:
        st.error(f"적용하지 못했습니다: {exc}")
        return
    stored_canvas = floor_canvases.get(key)
    base = (stored_canvas, marks_fingerprint(stored_marks))
    replace_equipment_buffer((frames[0], master, frames[2]))
    if applied.canvas is not None:
        unchanged = applied.canvas == (
            stored_canvas or (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
        )
        stage_floor_canvas(key, None if unchanged else applied.canvas, base=base)
    if applied.marks is not None:
        unchanged = marks_fingerprint(applied.marks) == marks_fingerprint(stored_marks)
        stage_floor_marks(key, None if unchanged else applied.marks, base=base)
    queue_flash(
        SPACE_FLASH_KEY,
        f"{building} {floor} 배치를 편집본에 적용했습니다. 저장해야 다른 사람 화면에 반영됩니다.",
    )
    st.rerun()


def _floor_occupancy(building: str, floor: str) -> float:
    rows = located_equipment.loc[
        located_equipment["동"].eq(building) & located_equipment["층"].eq(floor)
    ]
    return occupancy_ratio(rows, *_canvas_of(building, floor))


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

if editable:
    _render_unsaved_layout_panel(buffer_frames)

if selected_building is None:
    _render_placement_cards(
        (
            ("배치 설비", _units(equipment_unit_total(counted_equipment)), _PLACED_HELP),
            ("미배치", _units(equipment_unit_total(unplaced_equipment)), _UNPLACED_HELP),
            ("레이아웃 제외", _units(equipment_unit_total(excluded_equipment)), _EXCLUDED_HELP),
        ),
        key="space_fab_counts",
    )
    if exited_count > 0:
        st.caption(f"반출·이설을 마친 {_units(exited_count)}는 공간에 없어 세지 않습니다.")
    if building_unknown.any():
        st.caption(
            f"동이 정해지지 않은 미배치 "
            f"{_units(equipment_unit_total(unplaced_equipment.loc[building_unknown]))}는 "
            "동별 집계에 들어가지 않습니다 — 어느 층 배치 편집기에서나 트레이에 보입니다."
        )

    unplaced_by_building = _units_by(unplaced_equipment, "동")
    with st.container(border=True):
        st.markdown("#### :material/domain: S.PKG FAB 전체 배치")
        building_event = st.plotly_chart(
            build_fab_figure(counted_equipment, unplaced=unplaced_by_building),
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
        building_floors = floors_for(building.name)
        drawings = sum(
            (building.name, floor.floor) in floors_with_layout_image for floor in building_floors
        )
        overview_rows.append(
            {
                "동": building.name,
                "층수": len(building_floors),
                "배치대수": equipment_unit_total(
                    counted_equipment.loc[counted_equipment["동"].eq(building.name)]
                ),
                "미배치대수": unplaced_by_building.get(building.name, 0.0),
                "배치 도면": f"{drawings} / {len(building_floors)}층",
            }
        )
    # 도면의 표적은 Plotly SVG 마커라 포커스를 받지 못한다. 아래 동으로 내려가는 키보드
    # 길은 이 표다(행에 포커스를 두고 Shift+Space). 도면 클릭과 같은 자리로 이어진다.
    building_table = st.dataframe(
        pd.DataFrame(overview_rows),
        hide_index=True,
        width="stretch",
        column_config=_TABLE_COLUMNS,
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
    building_unplaced = unplaced_equipment.loc[unplaced_equipment["동"].eq(selected_building)]
    building_floors = floors_for(selected_building)
    drawings = sum(
        (selected_building, floor.floor) in floors_with_layout_image for floor in building_floors
    )
    _render_placement_cards(
        (
            ("선택 동", selected_building, None),
            ("배치 설비", _units(equipment_unit_total(building_equipment)), _PLACED_HELP),
            ("미배치", _units(equipment_unit_total(building_unplaced)), _UNPLACED_HELP),
            ("배치 도면", f"{drawings} / {len(building_floors)}층", _DRAWINGS_HELP),
        ),
        key="space_building_counts",
    )
    floor_unknown = building_unplaced["층"].isna()
    if floor_unknown.any():
        st.caption(
            f"층이 정해지지 않은 미배치 "
            f"{_units(equipment_unit_total(building_unplaced.loc[floor_unknown]))}는 층별 "
            f"집계에 들어가지 않습니다 — {selected_building}동 어느 층 배치 편집기에서나 "
            "트레이에 보입니다."
        )

    unplaced_by_floor = _units_by(building_unplaced, "층")
    occupancy_by_floor = {
        floor.floor: _floor_occupancy(selected_building, floor.floor) for floor in building_floors
    }
    with st.container(border=True):
        st.markdown(f"#### :material/apartment: {selected_building}동 층별 배치")
        floor_event = st.plotly_chart(
            build_floor_figure(
                counted_equipment,
                selected_building,
                unplaced=unplaced_by_floor,
                occupancy=occupancy_by_floor,
            ),
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
        canvas = _canvas_of(selected_building, floor.floor)
        floor_rows.append(
            {
                "층": floor.floor,
                "배치대수": equipment_unit_total(
                    building_equipment.loc[building_equipment["층"].eq(floor.floor)]
                ),
                "미배치대수": unplaced_by_floor.get(floor.floor, 0.0),
                "점유율": occupancy_by_floor[floor.floor],
                "배치 도면": (
                    "등록"
                    if (selected_building, floor.floor) in floors_with_layout_image
                    else "미등록"
                ),
                "캔버스": f"{canvas[0]:g} × {canvas[1]:g}",
            }
        )
    # 층 도면도 같은 이유로 키보드 길이 없다. 위와 같은 표로 잇는다.
    floor_table = st.dataframe(
        pd.DataFrame(floor_rows),
        hide_index=True,
        width="stretch",
        column_config=_TABLE_COLUMNS,
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

    floor_counted = counted_equipment.loc[
        counted_equipment["동"].eq(selected_building) & counted_equipment["층"].eq(selected_floor)
    ]
    floor_unplaced = unplaced_equipment.loc[
        unplaced_equipment["동"].eq(selected_building) & unplaced_equipment["층"].eq(selected_floor)
    ]
    occupancy = occupancy_ratio(floor_equipment, canvas_width, canvas_height)
    floor_unknown_here = unplaced_equipment["동"].isna() | (
        unplaced_equipment["동"].eq(selected_building).fillna(False)
        & unplaced_equipment["층"].isna()
    )
    # 층 화면은 카드 없이 배치도가 화면을 쓴다(2026-10-01 사용자 결정). 배치·미배치·점유율은 뷰어
    # 도구 줄 오른쪽 한 줄 요약이다. 층 미정 미배치는 이 층 미배치에 세지 않고 따로 말한다.
    summary = (
        f"배치 {_units(equipment_unit_total(floor_counted))} · "
        f"미배치 {_units(equipment_unit_total(floor_unplaced))} · 점유율 {occupancy:.1%}"
    )
    if floor_unknown_here.any():
        summary += (
            f" · 층 미정 미배치 "
            f"{_units(equipment_unit_total(unplaced_equipment.loc[floor_unknown_here]))}"
            "는 배치 편집 트레이에"
        )

    with st.container(border=True):
        # 머리 줄 하나에 제목·도면·캔버스 편집·배치 편집·상태 범례를 세운다. 배치도 Figure 의 제목과
        # 범례가 도면 위 한 띠를 따로 먹던 것을 걷었다 — 도면이 테두리 안을 다 쓴다.
        editing_requested = bool(st.session_state.get(EDIT_MODE_KEY, False))
        with st.container(
            horizontal=True, gap="small", vertical_alignment="center", key="space_floor_head"
        ):
            st.markdown(
                f"#### :material/map: {selected_building} {selected_floor} 상세 레이아웃",
                width="content",
            )
            render_floor_layout_editor(
                database_path=equipment_database_path,
                building=selected_building,
                floor=selected_floor,
                floor_equipment=floor_equipment,
            )
            editing = editable and st.toggle(
                "배치 편집",
                key=EDIT_MODE_KEY,
                help=(
                    "호기·반입구·문·영역을 끌어 놓아 자리와 크기를 고칩니다. 적용한 변경은 "
                    "저장하기 전까지 이 세션에만 있습니다."
                ),
            )
            st.space("stretch")
            # 편집 중에는 편집본을 그리므로 저장본의 대수를 달지 않고 색 뜻만 보인다. 반출·이설을
            # 마친 호기는 편집기에 나오지 않으니 그 색도 뺀다.
            st.markdown(
                stage_legend_markup(None, exclude=EXITED_STATUSES)
                if editable and editing_requested
                else stage_legend_markup(stage_counts(floor_counted)),
                unsafe_allow_html=True,
                width="content",
            )
        if editing:
            _render_layout_editor(buffer_frames, selected_building, selected_floor, layout_profile)
        else:
            marks = load_floor_layout_marks(
                equipment_database_path, selected_building, selected_floor
            )
            items = viewer_items(floor_equipment)
            roster = hashlib.sha256(
                "|".join(str(item["id"]) for item in items).encode()
            ).hexdigest()[:16]
            render_space_layout_viewer(
                key=f"space_layout_viewer_{selected_building}_{selected_floor}",
                # 저장본·캔버스·요소·그리는 호기(조건 카드 필터)가 바뀌면 새로 선다. 기준일로 단계만
                # 바뀌면 같은 epoch 로 색만 다시 칠하고 보던 배율을 지킨다.
                epoch="|".join(
                    (
                        "view",
                        selected_building,
                        selected_floor,
                        revision_token(latest_snapshot) if editable else "sample",
                        f"{canvas_width:g}x{canvas_height:g}",
                        marks_fingerprint(marks),
                        roster,
                    )
                ),
                items=items,
                canvas=(canvas_width, canvas_height),
                floor=(selected_building, selected_floor),
                marks=marks,
                summary=summary,
                background_image=(
                    layout_profile.image_data_uri if layout_profile is not None else None
                ),
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
