# Purpose: S.PKG FAB 전체 도면에서 층 상세 배치로 이어지는 Space 현황 2단 탐색 화면을 렌더링한다.

from __future__ import annotations

import hashlib
from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    Frames,
    effective_floor_canvases,
    ensure_equipment_drafts,
    equipment_buffer_generation,
    pending_fab_layout,
    pending_floor_canvases,
    pending_floor_marks,
    pop_discarded_notice,
    pop_drafts_replaced,
    replace_equipment_buffer,
    reset_equipment_drafts,
    revision_token,
    save_equipment_buffer,
    stage_fab_layout,
    stage_floor_canvas,
    stage_floor_marks,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.floor_layout_upload import (
    render_fab_layout_drawing_editor,
    render_floor_layout_editor,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.sample_data import (
    render_pending_source,
    render_sample_switch,
)
from capa_simulation.components.space_layout import (
    equipment_unit_total,
    floor_block_stats,
    floor_placements,
    invalid_equipment_rows,
    occupancy_ratio,
    stage_counts,
    stage_legend_markup,
)
from capa_simulation.components.space_layout_editor import (
    render_fab_layout_editor,
    render_fab_layout_viewer,
    render_space_layout_editor,
    render_space_layout_viewer,
)
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_fab_layout,
    load_floor_layout_canvases,
    load_floor_layout_marks,
    load_floor_layout_profile,
    load_floor_layout_summaries,
    load_latest_equipment_snapshot,
)
from capa_simulation.services.equipment_bulk_delete import BASELINE_TARGET, DOWNTIME_TARGET
from capa_simulation.services.equipment_contract import (
    DATE_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)
from capa_simulation.services.equipment_units import format_unit_count, placed_unit_rows
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.fab_layout import (
    FLOOR_KEYS,
    FabLayoutMark,
    duplicate_block_links,
    effective_fab_layout,
    fab_layout_fingerprint,
    fab_marks_fingerprint,
    floor_from_label,
    floor_from_param,
    floor_label,
    floor_param,
    parse_fab_editor_apply,
    prepare_fab_layout_marks,
    require_fab_layout_fits,
)
from capa_simulation.services.floor_layout_mark import FloorLayoutMark, marks_fingerprint
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    FloorKey,
    FloorLayoutProfile,
)
from capa_simulation.services.simulation_cache import get_space_equipment_status
from capa_simulation.services.space_layout_edit import (
    apply_layout_edits,
    editor_inputs,
    layout_changes,
    layout_warnings,
    new_unit_options,
    other_change_count,
    parse_editor_apply,
    table_changed,
    unsaved_unit_ids,
    viewer_items,
)
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

# 연 층. 두 키는 한 묶음이다 — 둘 다 있고 FAB 의 층이면 층 상세, 아니면 FAB 전체.
SELECTED_BUILDING_KEY = "space_status_selected_building"
SELECTED_FLOOR_KEY = "space_status_selected_floor"
# 주소의 조회 인자(`?floor=C1-1F`). 새로고침해도 보던 층에 머문다. 이 키만 넣고 지운다 —
# `st.query_params.clear()` 는 테마 인자(`theme`)까지 지워 테마 스크립트가 첫 방문으로 보고 다시
# 새로고침한다.
FLOOR_PARAM = "floor"
# 층 목록 표·층 바로 가기의 위젯 키. 층을 열면 FAB 화면은 그려지지 않아 표 선택은 그 회차에
# 버려진다(그리지 않은 위젯 상태는 버려진다). 바로 가기는 지금 자리(FAB·층)마다 키를 갈라 그
# 자리의 값으로 선다.
FLOOR_TABLE_KEY = "space_status_floor_table"
FLOOR_JUMP_KEY = "space_status_floor_jump"
FAB_VIEWER_KEY = "space_fab_viewer"
FAB_EDITOR_KEY = "space_fab_editor"
# 배치 편집. 저장 알림·메모는 가용설비 현황의 키(`FLASH_KEY`·`_NOTE_KEY`)를 쓰지 않는다 — 그쪽
# 페이지가 소비해 엉뚱한 화면에 뜬다. 메모 칸은 저장할 때마다 키를 바꿔 비운다.
SPACE_FLASH_KEY = "space_status_flash"
EDIT_MODE_KEY = "space_layout_edit_mode"
# FAB 배치 편집 토글은 층의 것과 따로다 — 같은 키면 FAB 편집에서 [열기] 로 연 층이 곧장 편집 모드로
# 선다.
FAB_EDIT_MODE_KEY = "space_fab_edit_mode"
SAVE_NOTE_KEY = "space_layout_save_note"
SAVE_NOTE_NONCE_KEY = "space_layout_save_note_nonce"
SAVE_ERROR_KEY = "space_layout_save_error"
SAVE_BUTTON_KEY = "space_layout_save"
DISCARD_BUTTON_KEY = "space_layout_discard"
DISCARD_FAB_BUTTON_KEY = "space_layout_discard_fab"
# 설비 샘플 화면에서 FAB 대기분 저장을 막은 까닭(상자 안내와 단추 풍선).
SAMPLE_SAVE_BLOCKED = (
    "설비 샘플을 보는 동안에는 FAB 전체 배치를 저장할 수 없습니다 — 샘플 스위치를 끄면 "
    "저장할 수 있습니다."
)
# 반출·이설을 마친 호기는 더 이상 공간에 없다. 배치·미배치·제외 어디에도 세지 않는다.
EXITED_STATUSES = ("반출 완료", "이설 완료")


def _show_fab_overview() -> None:
    """FAB 전체로 돌아간다(콜백). 주소의 `floor` 인자만 지운다."""
    st.session_state.pop(SELECTED_BUILDING_KEY, None)
    st.session_state.pop(SELECTED_FLOOR_KEY, None)
    if FLOOR_PARAM in st.query_params:
        del st.query_params[FLOOR_PARAM]


def _open_floor(key: FloorKey) -> None:
    """그 층을 연다. 블록 누르기·층 바로 가기·층 목록 표가 모두 이것을 **콜백**에서 부른다 — 콜백은
    본문보다 먼저 돌아 재실행 한 번으로 층 상세가 서고, 본문에서 `st.rerun()` 할 때처럼 아직 안 그린
    위젯 상태가 버려지지 않는다. 주소에는 `floor` 인자만 적는다(다른 인자는 그대로)."""
    st.session_state[SELECTED_BUILDING_KEY], st.session_state[SELECTED_FLOOR_KEY] = key
    if st.query_params.get(FLOOR_PARAM) != floor_param(key):
        st.query_params[FLOOR_PARAM] = floor_param(key)


def _jump_to_floor(widget_key: str) -> None:
    """`층 바로 가기` 콜백."""
    key = floor_from_label(st.session_state.get(widget_key))
    if key is not None:
        _open_floor(key)


def _open_from_table(keys: tuple[FloorKey, ...]) -> None:
    """층 목록 표의 행 고르기 콜백. 키보드로 층을 여는 길이기도 하다."""
    state = st.session_state.get(FLOOR_TABLE_KEY)
    if state is None:
        return
    try:
        rows = list(state["selection"]["rows"])
    except (KeyError, TypeError):
        return
    if rows and 0 <= int(rows[0]) < len(keys):
        _open_floor(keys[int(rows[0])])


def _units(value: float) -> str:
    return f"{format_unit_count(value)}대"


_PLACED_HELP = "도면에 그린 설비입니다. Main 설비로 묶은 모듈 행은 합쳐 1대입니다."
_UNPLACED_HELP = "레이아웃표시 Y 인데 좌표가 없어 도면에 그리지 못한 설비입니다."
_OCCUPANCY_HELP = (
    "도면에 그린 호기 사각형 면적 합 ÷ 캔버스 면적. 캔버스 단위의 상대값이며 "
    "겹친 자리는 두 번 셉니다."
)
_DRAWING_HELP = "그 층에 배경 도면 이미지를 올렸는지입니다."
# 층 목록 표의 대수·비율 칸. 대수는 설비지분 합이라 모듈 설비가 있으면 소수가 나온다.
_TABLE_COLUMNS = {
    "배치대수": st.column_config.NumberColumn(format="localized", help=_PLACED_HELP),
    "미배치대수": st.column_config.NumberColumn(format="localized", help=_UNPLACED_HELP),
    "점유율": st.column_config.NumberColumn(format="percent", help=_OCCUPANCY_HELP),
    "배치 도면": st.column_config.TextColumn(help=_DRAWING_HELP),
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
    # 저장된 FAB 전체 도면(캔버스·배경 도면 행, 요소). 요소가 없으면 기본 배치를 그린다.
    fab_profile, fab_stored_marks = load_fab_layout(equipment_database_path)
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

valid_location_pairs = set(FLOOR_KEYS)
# 연 층: 세션이 먼저다. 세션에 층이 없을 때만 주소(`?floor=`)를 읽는다 — 새로고침·주소로 들어온 첫
# 회차가 그 층을 연다. 잘못된 값은 조용히 FAB 이고 그 인자만 지운다. 세션에 층이 있는데 주소가
# 다르면 주소를 세션에 맞춘다.
selected: FloorKey | None = None
session_building = st.session_state.get(SELECTED_BUILDING_KEY)
session_floor = st.session_state.get(SELECTED_FLOOR_KEY)
if (
    isinstance(session_building, str)
    and isinstance(session_floor, str)
    and (session_building, session_floor) in valid_location_pairs
):
    selected = (session_building, session_floor)
    if st.query_params.get(FLOOR_PARAM) != floor_param(selected):
        st.query_params[FLOOR_PARAM] = floor_param(selected)
else:
    st.session_state.pop(SELECTED_BUILDING_KEY, None)
    st.session_state.pop(SELECTED_FLOOR_KEY, None)
    if FLOOR_PARAM in st.query_params:
        selected = floor_from_param(st.query_params.get(FLOOR_PARAM))
        if selected is None:
            del st.query_params[FLOOR_PARAM]
        else:
            st.session_state[SELECTED_BUILDING_KEY], st.session_state[SELECTED_FLOOR_KEY] = selected

# 본문 머리에는 상태 배지(「Data확보중」)도 적용 이력 줄도 두지 않는다 — 배치도가 쓸 자리다
# (2026-10-01 사용자 결정). 사이드바 메뉴 이름은 그대로다.
render_page_header("Space 현황 (Data확보중)", show_status=False)
render_page_guide("space_status", title="Space 현황")
# 저장 알림·버림 알림은 늘 서 있는 한 칸 안에 그린다 — 알림이 생기고 사라질 때 아래 key 있는
# 묶음의 자리가 밀리면 `st.rerun()` 으로 끊긴 회차의 사본이 남는다(가용설비 현황과 같은 까닭).
notices = st.container()
with notices:
    render_flash(SPACE_FLASH_KEY)
    # 설비 DB 가 이 코드보다 새 버전이면(예전 배포로 되돌린 상태) 경고 한 줄. 막지 않는다.
    render_schema_ahead_warning(get_equipment_repository(equipment_database_path).schema_ahead)
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
        notices.warning(discarded_notice, icon=":material/sync_problem:")
# 설비 샘플 화면(호기 마스터가 비어 샘플 스위치를 켠 상태)인가. 이때는 FAB 편집도 끈다 — 합성 fleet
# 위에서 고친 FAB 가 실제 저장소에 들어간다(2026-10-03 사용자 결정 2).
showing_sample = False
# 호기가 없고 샘플을 끈 상태. 조건 카드에 까닭 한 줄만 두고, 빈 fleet 으로 FAB·층 목록을 그린다 —
# FAB 배치는 설비 리비전과 무관한 현행값이라 설비 저장본이 없어도 고치고 저장한다(결정 2).
no_fleet = False
if using_sample_equipment:
    # 스위치는 호기 마스터가 비었을 때만 뜻이 있다. 실데이터가 있으면 끌 것이 없다.
    if render_sample_switch(key="space_sample_switch", source="설비 운영 DB"):
        showing_sample = True
        st.caption("호기 마스터가 비어 있어 데모 fleet 을 표시합니다.")
    else:
        no_fleet = True
        # 카드를 세우고 까닭을 적는다. 카드 없이 지나가면 사이드바 CSS 가 홀로 남은 「조회 조건」
        # 제목까지 감춰 이 화면의 조건 자리가 통째로 사라지고, 왜 고를 것이 없는지 알 길이 없다.
        # 가용설비 현황의 같은 자리와 같은 모양이다.
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
        st.caption(
            "호기가 없어도 아래 S.PKG FAB 전체 배치(층 블록·영역·글자)는 고치고 저장할 수 있습니다."
        )
        equipment = empty_equipment_master()
        downtime = empty_downtime_schedule()
fab_editable = not showing_sample

if no_fleet:
    # 고를 호기가 없어 조건 위젯을 세우지 않는다(카드에는 위의 까닭 한 줄).
    as_of = today
    all_status = get_space_equipment_status(equipment, downtime, as_of=as_of)
    selected_processes: list[str] = []
    selected_stages: list[str] = []
else:
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
        all_status = get_space_equipment_status(equipment, downtime, as_of=as_of)
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
# 동·층이 정해지지 않은(또는 FAB 의 층이 아닌) 미배치는 층 집계에 들어갈 자리가 없다. FAB
# 요약의 미배치 = 층 목록 표 미배치 합 + 미정이 되도록 FAB 요약에서 따로 말한다(층 요약에 더하면
# 여러 층에서 거듭 세어진다).
location_unknown = pd.Series(
    [
        (building, floor) not in valid_location_pairs
        for building, floor in zip(unplaced_equipment["동"], unplaced_equipment["층"], strict=False)
    ],
    index=unplaced_equipment.index,
    dtype=bool,
)


def _canvas_of(key: FloorKey) -> tuple[float, float]:
    return floor_canvases.get(key, (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT))


def _canvas_text(key: FloorKey) -> str:
    width, height = _canvas_of(key)
    return f"{width:g} × {height:g}"


# 「다른 층으로 보내기」 목록 순서 — C1 1F, C1 2F, … (도면의 동·층 배치 순서가 아니라 이름 순).
ALL_FLOORS: tuple[FloorKey, ...] = FLOOR_KEYS


def _render_unsaved_layout_panel(frames: Frames | None) -> None:
    """저장 안 한 배치 변경(호기 배치·편집 영역·도면 요소·FAB 전체 배치)과 저장·버리기. 어느 단계
    화면에서나 뜬다.

    저장은 가용설비 RawData 와 같은 `save_equipment_buffer` 다 — 편집본 전체를 저장하므로 RawData
    의 저장 안 한 다른 편집도 함께 들어간다. 그 사실을 건수로 말한다. FAB 전체 배치는 설비 리비전과
    무관한 별도 쓰기라 `frames` 가 None(설비 저장본이 없는 화면)이어도 상자가 서고 FAB 만 저장한다.
    """
    # 저장 오류는 상자를 그리지 않는 회차에도 한 번만 보이고 버린다(남의 저장으로 편집이 버려진
    # 회차에는 상자가 없다). 남겨 두면 나중의 상관없는 적용 옆에 다시 뜬다.
    error = st.session_state.pop(SAVE_ERROR_KEY, None)
    fab_pending = pending_fab_layout()
    if frames is not None:
        assert latest_snapshot is not None
        changes = layout_changes(latest_snapshot.equipment, frames[1])
        canvases = pending_floor_canvases()
        marks = pending_floor_marks()
        others = other_change_count(latest_snapshot.equipment, frames[1])
        # 저장은 세 표를 다 견준다. 호기 마스터 밖의 편집도 리비전을 만드니 따로 말한다.
        side_tables = [
            label
            for label, saved, buffer in (
                (BASELINE_TARGET, latest_snapshot.baseline, frames[0]),
                (DOWNTIME_TARGET, latest_snapshot.downtime, frames[2]),
            )
            if table_changed(saved, buffer)
        ]
    else:
        changes, canvases, marks, others, side_tables = pd.DataFrame(), {}, {}, 0, []
    if changes.empty and not canvases and not marks and fab_pending is None:
        if isinstance(error, str):
            st.error(f"배치를 저장하지 못했습니다: {error}")
        return
    parts = [f"호기 배치 {len(changes)}건"] if not changes.empty else []
    if canvases:
        parts.append(f"편집 영역 {len(canvases)}개 층")
    if marks:
        parts.append(f"도면 요소 {len(marks)}개 층")
    if fab_pending is not None:
        parts.append("S.PKG FAB 전체 배치")
    with st.container(border=True, key="space_unsaved_layout_panel"):
        st.markdown(f"**:material/edit_note: 저장 안 한 배치 변경** — {' · '.join(parts)}")
        st.caption(
            "적용한 변경은 이 화면(세션)에만 있습니다. 저장해야 도면·요약과 다른 사람 화면에 "
            "반영됩니다."
            + (
                f" 가용설비 현황 RawData 의 저장 안 한 다른 편집 {others}건도 함께 저장됩니다."
                if others
                else ""
            )
            + (
                f" 가용설비 현황 RawData 의 {'·'.join(side_tables)} 표 편집도 함께 저장됩니다."
                if side_tables
                else ""
            )
            + (
                " FAB 전체 배치는 설비 리비전을 만들지 않고 따로 저장합니다."
                if fab_pending is not None
                else ""
            )
            + (f" {SAMPLE_SAVE_BLOCKED}" if not fab_editable else "")
        )
        if not changes.empty:
            with st.expander(f"바뀐 호기 {len(changes)}건"):
                st.dataframe(changes, hide_index=True, width="stretch")
        if fab_pending is not None and fab_pending.marks is not None:
            for label in duplicate_block_links(fab_pending.marks):
                st.caption(
                    f":material/warning: FAB 의 층 블록 둘 이상이 {label} 을 가리킵니다(저장은 됨)."
                )
        if frames is not None:
            _render_layout_warnings(frames, marks)
        if isinstance(error, str):
            st.error(f"저장하지 못했습니다: {error}")
        note_key = f"{SAVE_NOTE_KEY}_{int(st.session_state.get(SAVE_NOTE_NONCE_KEY, 0))}"
        # 메모는 설비 리비전에만 남는다. 설비 쪽 차이가 하나도 없는(FAB 만 바뀐) 저장은 리비전을
        # 만들지 않으니 칸을 두지 않는다.
        fab_only = changes.empty and not canvases and not marks and not others and not side_tables
        # 저장·버리기는 **콜백**이다. 본문에서 저장하고 `st.rerun()` 하면 이 상자 아래 위젯
        # (층 상세의 `배치 편집` 토글 등)이 그 회차에 그려지지 않은 것으로 끝나 상태가 버려진다 —
        # 저장하자마자 편집기가 꺼졌다(2026-10-01 브라우저 확인). 콜백은 다음 회차 전에 돈다.
        with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
            if not fab_only:
                st.text_input(
                    "변경 메모", key=note_key, placeholder="예: C1 1F 반입구 앞 정리", width=360
                )
            # 설비 샘플 화면에서는 FAB 편집이 꺼진다(결정 2). 그 전에 적용한 FAB 대기분도 저장하지
            # 않는다 — 대기분은 두고, 스위치를 끄면 저장할 수 있다. 버리기는 그대로 된다.
            st.button(
                "배치 저장",
                type="primary",
                icon=":material/save:",
                key=SAVE_BUTTON_KEY,
                on_click=_save_space_layout,
                args=(frames, note_key, equipment_database_path),
                disabled=not fab_editable,
                help=None if fab_editable else SAMPLE_SAVE_BLOCKED,
            )
            with st.popover("버리기", icon=":material/undo:"):
                st.caption(
                    "저장 안 한 설비 편집을 모두 버리고 최신 저장본으로 돌아갑니다. 가용설비 "
                    "RawData 의 저장 안 한 편집과 FAB 전체 배치도 함께 버려집니다."
                    if frames is not None
                    else "저장 안 한 S.PKG FAB 전체 배치를 버리고 저장본(없으면 기본 배치)으로 "
                    "돌아갑니다."
                )
                st.button(
                    "모두 버리기",
                    key=DISCARD_BUTTON_KEY,
                    on_click=_discard_space_layout,
                    args=(frames is not None,),
                )
                if frames is not None and fab_pending is not None:
                    # FAB 는 별도 쓰기라 따로 버릴 수 있어야 한다 — 남이 먼저 FAB 를 저장해 거부된
                    # 대기분을 설비·층 편집까지 버리지 않고 치운다.
                    st.button(
                        "FAB 배치만 버리기",
                        key=DISCARD_FAB_BUTTON_KEY,
                        on_click=_discard_space_layout,
                        args=(False,),
                        help="설비·층 배치 편집은 두고 S.PKG FAB 전체 배치 대기분만 버립니다.",
                    )


def _render_layout_warnings(
    frames: Frames, marks: dict[FloorKey, tuple[FloorLayoutMark, ...]]
) -> None:
    """편집본의 겹침·가림 경고. RawData 의 검증 실패 편집이 남아 있으면 경고만 건너뛴다."""
    try:
        status = get_space_equipment_status(frames[1], frames[2], as_of=as_of)
    except ValueError as exc:
        # 저장·버리기는 둔다(저장하면 같은 까닭으로 막히고, 버리면 풀린다).
        st.caption(
            ":material/error: 가용설비 현황 RawData 에 검증을 통과하지 못한 저장 안 한 편집이 "
            f"있어 겹침 경고를 계산하지 못했습니다: {exc}"
        )
        return
    for warning in layout_warnings(status, {**_stored_marks_for(status, set(marks)), **marks}):
        st.caption(f":material/warning: {warning}")


def _discard_space_layout(with_equipment: bool) -> None:
    """`모두 버리기`·`FAB 배치만 버리기` 콜백. 편집본·대기분(FAB 포함)과 남은 저장 오류를 버린다.
    `with_equipment` 가 거짓이면(설비 저장본이 없는 화면, 또는 `FAB 배치만 버리기`) FAB 대기분만
    버린다."""
    st.session_state.pop(SAVE_ERROR_KEY, None)
    if with_equipment:
        reset_equipment_drafts()
    else:
        stage_fab_layout(None, None, base=(None, ""))


def _save_space_layout(frames: Frames | None, note_key: str, database_path: str) -> None:
    """`배치 저장` 콜백. 편집본(세 표)과 미저장 층 배치를 한 번에 쓰고 알림을 남긴다. FAB 전체
    배치는 그 앞에 따로 쓴다(설비 리비전 없음). `frames` 가 None 이면 FAB 만 쓴다."""
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
        status = get_space_equipment_status(frames[1], frames[2], as_of=as_of)
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
            master_ids=set(frames[1][EQUIPMENT_ID_COLUMN].dropna().astype(str).str.strip()),
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


def _render_fab_editor(
    link_stats: dict[str, dict[str, str | None]], background_image: str | None
) -> None:
    """FAB 전체 배치 편집기. 대기분(없으면 저장본, 그것도 없으면 기본 배치)을 그리고, `적용` 이
    오면 검증해 세션 대기분에 얹는다(저장 전). 설비 편집본과 무관하다."""
    pending = pending_fab_layout()
    stored_canvas, stored_marks = effective_fab_layout(fab_profile, fab_stored_marks)
    canvas = pending.canvas if pending is not None and pending.canvas else stored_canvas
    marks: tuple[FabLayoutMark, ...] = (
        pending.marks if pending is not None and pending.marks is not None else stored_marks
    )
    st.caption(
        "층 블록·영역·글자를 끌어 놓아 고치고 **적용**을 누르면 이 세션에 들어갑니다(저장 전). "
        "층 블록을 고르면 선택 칸에서 연결 층·색을 바꾸고 [열기] 로 그 층을 엽니다. S.PKG 가 "
        "아닌 자리는 블록 대신 색을 고른 영역과 글자로 그립니다."
    )
    # epoch: 그리는 도면(대기분 또는 저장본)과 저장본. 적용하면 대기분이, 남이 저장하면 저장본이
    # 바뀌어 브라우저가 새 값으로 다시 선다. 블록 대수는 epoch 밖이다.
    epoch = "|".join(
        (
            "fab-edit",
            fab_layout_fingerprint(canvas, marks),
            fab_layout_fingerprint(stored_canvas, stored_marks),
        )
    )
    submission = render_fab_layout_editor(
        key=FAB_EDITOR_KEY,
        epoch=epoch,
        canvas=canvas,
        marks=marks,
        link_stats=link_stats,
        on_open=_open_floor,
        background_image=background_image,
    )
    if submission is None:
        return
    if submission.stale:
        st.warning(
            "그 사이 FAB 도면이 바뀌어(예: 다른 화면에서 저장) 편집기를 새 값으로 다시 "
            "불러왔습니다. 방금 누른 적용은 반영하지 않았으니 다시 고친 뒤 적용하세요."
        )
        return
    try:
        applied = parse_fab_editor_apply(submission.payload, canvas)
        next_canvas = applied.canvas or canvas
        next_marks = applied.marks if applied.marks is not None else marks
        if applied.marks is None:
            # 영역만 바꿨다 — 지금 요소가 새 영역 안인지 저장 때와 같은 검사를 지금 한다.
            prepare_fab_layout_marks([mark.editor_payload() for mark in next_marks], next_canvas)
        # 요소를 모두 지웠으면 기본 배치를 그린다 — 그것도 영역 안이어야 한다(저장 때와 같은 검사).
        require_fab_layout_fits(next_canvas, next_marks)
    except ValueError as exc:
        st.error(f"적용하지 못했습니다: {exc}")
        return
    # 저장값과 같아진 쪽은 대기분에서 뺀다. 견주는 기준은 그리는 저장값(요소가 없으면 기본
    # 배치)이고, 저장 때 대조할 본 값은 실제 저장 행이다(캔버스 행이 없으면 None, 요소가 없으면 빈
    # 목록의 지문).
    base = (
        fab_profile.canvas_size if fab_profile is not None else None,
        fab_marks_fingerprint(fab_stored_marks),
    )
    stage_fab_layout(
        None if next_canvas == stored_canvas else next_canvas,
        None
        if fab_marks_fingerprint(next_marks) == fab_marks_fingerprint(stored_marks)
        else next_marks,
        base=base,
    )
    doubled = duplicate_block_links(next_marks)
    queue_flash(
        SPACE_FLASH_KEY,
        "S.PKG FAB 전체 배치를 이 세션에 적용했습니다. 저장해야 다른 사람 화면에 반영됩니다."
        + (f" 같은 층을 가리키는 블록이 있습니다: {', '.join(doubled)}." if doubled else ""),
    )
    st.rerun()


# 경로 줄은 두 칸이다: `S.PKG FAB 전체` › `층 바로 가기`(30개 층). FAB 에서는 둘째 칸이 비어 있고,
# 층을 고르면 그 층이 열린다. 자리를 옮기는 것은 모두 콜백이다(재실행 한 번).
with st.container(horizontal=True, gap="small", vertical_alignment="center", key="space_path"):
    st.button(
        "S.PKG FAB 전체",
        icon=":material/domain:",
        type="primary" if selected is None else "secondary",
        key="space_status_fab_breadcrumb",
        on_click=_show_fab_overview,
    )
    st.markdown(":material/chevron_right:", width="content")
    floor_labels = [floor_label(key) for key in FLOOR_KEYS]
    jump_key = f"{FLOOR_JUMP_KEY}_{floor_param(selected) if selected is not None else 'fab'}"
    st.selectbox(
        "층 바로 가기",
        options=floor_labels,
        index=floor_labels.index(floor_label(selected)) if selected is not None else None,
        placeholder="층 바로 가기",
        key=jump_key,
        on_change=_jump_to_floor,
        args=(jump_key,),
        label_visibility="collapsed",
        width=170,
    )

# 저장 안 한 배치 상자의 자리는 늘 서 있다(내용만 비었다 찼다). 상자가 첫 적용에 새로
# 서거나 저장·버리기로 사라질 때 아래 층 상세·FAB 상자의 순번이 밀리면, Streamlit 은 요소를
# key 가 아니라 순번으로 갈아 끼우므로 편집기를 새로 마운트한다. 그 사이 본문 높이가 화면
# 높이로 무너져 스크롤이 맨 위로 튀고, 브라우저에 둔 편집기 상태(서랍·배율)도 잃는다.
with st.container(key="space_unsaved_layout_slot"):
    if editable or pending_fab_layout() is not None:
        _render_unsaved_layout_panel(buffer_frames if editable else None)

if selected is None:
    placements = floor_placements(
        counted_equipment, unplaced_equipment, located_equipment, _canvas_of
    )
    # FAB 전체는 층 도면과 같은 편집기의 보기 전용이다(scope="fab"). 카드 없이 배치·미배치·
    # 레이아웃 제외가 뷰어 도구 줄 오른쪽 한 줄 요약이다. 층 미정 미배치는 층 목록 표 어디에도
    # 들지 않아 따로 단다.
    fab_summary = (
        f"배치 {_units(equipment_unit_total(counted_equipment))} · "
        f"미배치 {_units(equipment_unit_total(unplaced_equipment))} · "
        f"레이아웃 제외 {_units(equipment_unit_total(excluded_equipment))}"
    )
    if location_unknown.any():
        fab_summary += (
            " · 미배치 중 동·층 미정 "
            f"{_units(equipment_unit_total(unplaced_equipment.loc[location_unknown]))}"
        )
    # 보기는 저장본이다(저장된 요소가 없으면 기본 배치). 저장 안 한 FAB 편집은 편집기와 상자가
    # 말한다.
    fab_canvas, fab_marks = effective_fab_layout(fab_profile, fab_stored_marks)
    fab_background = fab_profile.image_data_uri if fab_profile is not None else None
    block_stats = floor_block_stats(placements)
    with st.container(border=True):
        # 머리 줄은 층 상세와 같은 구조다(제목 · 도면·캔버스 편집 · 배치 편집 · 오른쪽 범례 자리).
        # FAB 범례 자리는 비워 둔다 — 블록 색의 뜻은 사용자가 도면 글자로 적는다.
        with st.container(
            horizontal=True, gap="small", vertical_alignment="center", key="space_fab_head"
        ):
            st.markdown("#### :material/domain: S.PKG FAB 전체 배치", width="content")
            render_fab_layout_drawing_editor(
                database_path=equipment_database_path, disabled=not fab_editable
            )
            # 설비 저장본이 없어도 켠다(FAB 는 설비 리비전과 무관한 현행값, 결정 2). 샘플 화면에서는
            # 끈다. 잠글 때는 **값도 끈다** — 켜 둔 채 잠그면 스위치는 켜짐인데 보기 전용 도면이
            # 그려져 화면이 서로 다른 말을 했다(2026-10-05 E2E). 적용해 둔 대기분은 그대로다.
            if not fab_editable:
                st.session_state[FAB_EDIT_MODE_KEY] = False
            fab_editing = (
                st.toggle(
                    "배치 편집",
                    key=FAB_EDIT_MODE_KEY,
                    disabled=not fab_editable,
                    help=(
                        "샘플 데이터를 보는 중에는 FAB 배치를 고치지 않습니다."
                        if not fab_editable
                        else "층 블록·영역·글자를 끌어 놓아 자리·크기를 고치고, 층 블록의 "
                        "연결 층과 색을 고릅니다. 적용한 변경은 저장하기 전까지 이 세션에만 "
                        "있습니다."
                    ),
                )
                and fab_editable
            )
            st.space("stretch")
        if fab_editing:
            _render_fab_editor(block_stats, fab_background)
        else:
            render_fab_layout_viewer(
                key=FAB_VIEWER_KEY,
                # 도면(캔버스·요소)이 바뀔 때만 새로 선다. 블록 대수는 epoch 밖이라 기준일·필터가
                # 바뀌면 블록 글자만 다시 쓰고 보던 배율을 지킨다.
                epoch="|".join(("fab", fab_layout_fingerprint(fab_canvas, fab_marks))),
                canvas=fab_canvas,
                marks=fab_marks,
                link_stats=block_stats,
                summary=fab_summary,
                on_open=_open_floor,
                background_image=fab_background,
            )
    if exited_count > 0:
        st.caption(f"반출·이설을 마친 {_units(exited_count)}는 공간에 없어 세지 않습니다.")

    # 층 목록 표. 층마다 배치·미배치·점유율을 견주는 자리이고, 층 바로 가기와 함께 키보드로 층을
    # 여는 길이다(행에 초점을 두고 Shift+Space). 행을 고르면 그 층이 열린다.
    floor_rows = [
        {
            "동": placement.key[0],
            "층": placement.key[1],
            "배치대수": placement.placed,
            "미배치대수": placement.unplaced,
            "점유율": placement.occupancy,
            "배치 도면": "등록" if placement.key in floors_with_layout_image else "미등록",
            "캔버스": _canvas_text(placement.key),
        }
        for placement in placements
    ]
    st.dataframe(
        pd.DataFrame(floor_rows),
        hide_index=True,
        width="stretch",
        column_config=_TABLE_COLUMNS,
        key=FLOOR_TABLE_KEY,
        on_select=partial(_open_from_table, tuple(placement.key for placement in placements)),
        selection_mode="single-row",
    )

else:
    selected_building, selected_floor = selected
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
    # 경고 자리도 늘 서 있다 — 저장으로 경고가 생기거나 사라질 때 아래 층 상세가 밀리지 않게(위 상자
    # 자리와 같은 까닭).
    with st.container(key="space_floor_canvas_warning_slot"):
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
            for column in DATE_COLUMNS
        },
    )
    # 층별 호기 목록은 현장 배치 검토에 그대로 쓰인다.
    render_csv_download(
        data=floor_equipment.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"space_{selected_building}_{selected_floor}.csv",
        key=f"space_floor_download_{selected_building}_{selected_floor}",
    )
