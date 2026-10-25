# Purpose: S.PKG FAB 전체에서 층 상세로 이어지는 Space 현황 2단 화면과 필요 단축 보기를 렌더링한다.

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import date
from functools import partial
from typing import Any

import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    Frames,
    discard_layout_edits,
    effective_floor_canvases,
    ensure_equipment_drafts,
    equipment_buffer_generation,
    follow_unit_renames,
    has_unsaved_equipment_edits,
    live_layout_role,
    new_unit_choice_line,
    official_confirmation_master,
    pending_fab_layout,
    pending_floor_canvases,
    pending_floor_group_labels,
    pending_floor_marks,
    pending_unit_renames,
    pop_discarded_notice,
    pop_drafts_replaced,
    prune_new_unit_propagation,
    render_name_changes,
    replace_equipment_buffer,
    reset_equipment_drafts,
    revision_token,
    save_equipment_buffer,
    stage_editor_module_layouts,
    stage_fab_layout,
    stage_floor_canvas,
    stage_floor_group_labels,
    stage_floor_marks,
    stage_unit_renames,
    stamp_layout_role,
)
from capa_simulation.components.equipment_save_fields import (
    EquipmentSaveBasis,
    render_equipment_save_fields,
    save_fields_from_state,
)
from capa_simulation.components.equipment_scenario_status import (
    equipment_value_label,
    render_equipment_scenario_row,
    render_legacy_trace_warning,
    unscheduled_notice,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.floor_layout_upload import (
    render_fab_layout_drawing_editor,
    render_floor_layout_editor,
)
from capa_simulation.components.literal_markdown import markdown_safe_tildes
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.sample_data import (
    render_pending_source,
    render_sample_switch,
)
from capa_simulation.components.shortening_source import ShorteningStop
from capa_simulation.components.space_floor_layout import (
    compare_payload,
    effective_floor_layout,
    floor_layout_differences,
    floor_unit_differences,
    space_layout_notices,
)
from capa_simulation.components.space_floor_list import (
    FloorListColumn,
    discard_floor_state_draft,
    layer_columns,
    render_space_floor_list,
)
from capa_simulation.components.space_layout import (
    ColorChoice,
    apply_layer_looks,
    color_check_style,
    default_color_choice,
    equipment_unit_total,
    floor_block_stats,
    floor_placements,
    floor_table,
    invalid_equipment_rows,
    occupancy_ratio,
    picked_unit_rows,
    row_unit_shares,
    shortening_legend_markup,
    space_legend_counts,
    space_legend_markup,
    unit_appearance,
)
from capa_simulation.components.space_layout_editor import (
    render_fab_layout_editor,
    render_fab_layout_viewer,
    render_space_layout_editor,
    render_space_layout_viewer,
)
from capa_simulation.components.space_shortening_view import (
    PINNED_NOTE,
    SpaceLayer,
    consume_layer_link,
    forget_arrival_note,
    layer_table_columns,
    load_space_layer,
    render_arrival_filter_note,
    render_fab_layer_summary,
    render_floor_layer_panel,
    render_layer_basis,
    render_layer_controls,
    render_layer_stop,
    switch_to_queued_shortening,
    unit_keys_by_name,
    valid_focus,
)
from capa_simulation.components.table_toolbar import TABLE_TOOLBAR_CLEARANCE, render_csv_download
from capa_simulation.equipment_scenario_activation import (
    CANVAS_LOCK_REASON,
    FAB_LOCK_REASON,
    FLOOR_STATE_LOCK_REASON,
    EquipmentSession,
    official_snapshot_for,
    resolve_equipment_session,
    select_equipment_scenario,
    space_edit_mode,
)
from capa_simulation.navigation import SPACE_COLOR_BASIS_KEY
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_fab_layout,
    load_floor_layout_canvases,
    load_floor_layout_profile,
    load_floor_layout_summaries,
    load_floor_states,
)
from capa_simulation.services.equipment_bulk_delete import BASELINE_TARGET, DOWNTIME_TARGET
from capa_simulation.services.equipment_contract import (
    DATE_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    INVESTMENT_CAPA_COLUMN,
    LAYOUT_EXITED_COLUMN,
    LAYOUT_REFLECTED_COLUMN,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)
from capa_simulation.services.equipment_units import (
    format_unit_count,
    placed_unit_rows,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_master,
)
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
from capa_simulation.services.floor_layout_mark import (
    FloorLayoutMark,
    floor_layout_fingerprint,
    marks_fingerprint,
)
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    FloorKey,
    FloorLayoutProfile,
)
from capa_simulation.services.floor_state import (
    floor_states_fingerprint,
    floor_unit_counts,
    inactive_label,
    selectable_floor_keys,
)
from capa_simulation.services.korean_particle import object_particle, with_direction_particle
from capa_simulation.services.layout_overlay import EMPTY_LAYOUT_DIGEST
from capa_simulation.services.schedule_confirmation import UNCONFIRMED, confirmation_counts
from capa_simulation.services.simulation_cache import (
    get_schedule_confirmation_issues,
    get_space_equipment_status,
    get_space_unit_boundaries,
)
from capa_simulation.services.space_color_basis import (
    COLOR_BASES,
    COLOR_BASIS_CAPA,
    COLOR_BASIS_LINE_TYPE,
    COLOR_BASIS_SHORTENING,
    capa_groups,
    color_basis_groups,
)
from capa_simulation.services.space_layout_edit import (
    apply_layout_edits,
    apply_name_changes,
    buffer_matches_saved,
    compose_renames,
    downtime_with_renames,
    editor_inputs,
    layout_changes,
    layout_warnings,
    module_group_sizes,
    module_layouts,
    name_changes,
    new_unit_options,
    next_group_labels,
    other_change_count,
    parse_editor_apply,
    reserved_names,
    table_changed,
    unsaved_unit_ids,
    viewer_items,
)
from capa_simulation.services.space_shortening_layer import (
    FabSummary,
    FloorLayer,
    fab_floor_counts,
    fab_layer_summary,
    floor_layer,
    floor_short_line,
)
from capa_simulation.services.space_unit_state import (
    as_of_range,
    clamp_as_of,
    drawn_in_range,
    unit_boundaries,
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
# 층 바로 가기의 위젯 키. 지금 자리(FAB·층)마다 키를 갈라 그 자리의 값으로 선다. 층 목록 표의
# 키는 `components/space_floor_list.py` 가 갖는다.
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
# 「공식으로 바꾸기」·「최신 rM 불러오기」 실패 글 — 저장 오류와 따로 둔다(저장 안 한 상자가
# 「배치를 저장하지 못했습니다」 머리로 꺼내 보이지 않게). 잠금 줄 자리에 한 번 보이고 버린다.
SWITCH_ERROR_KEY = "space_scenario_switch_error"
SAVE_BUTTON_KEY = "space_layout_save"
DISCARD_BUTTON_KEY = "space_layout_discard"
DISCARD_FAB_BUTTON_KEY = "space_layout_discard_fab"
# 설비 샘플 화면에서 FAB 대기분 저장을 막은 까닭(상자 안내와 단추 풍선).
SAMPLE_SAVE_BLOCKED = (
    "설비 샘플을 보는 동안에는 FAB 전체 배치를 저장할 수 없습니다 — 샘플 스위치를 끄면 "
    "저장할 수 있습니다."
)
# 배치 저장의 저장 칸(저장자·함께 넣기·공식 발행 — `equipment_save_fields`). 가용설비 설비 마스터의
# 칸과 key 를 가른다.
SPACE_SAVE_FIELDS_PREFIX = "space_layout_save_fields"
# 가정 설비 시나리오에서 FAB 전체 배치 자리의 「공식으로 바꾸기」(G5 — FAB 은 공식에서만 고친다).
SWITCH_TO_OFFICIAL_KEY = "space_switch_to_official"
# 층 배치 편집이 잠긴 회차(남이 그 시나리오에 다른 배치를 저장·가정이던 때 리비전)의 「최신 rM
# 불러오기」, 꺼진 「배치 편집」 토글, 저장 안 한 상자의 「배치 변경만 버리기」.
LOAD_LATEST_KEY = "space_load_latest"
LOCKED_EDIT_TOGGLE_KEY = "space_layout_edit_mode_locked"
DISCARD_LAYOUT_BUTTON_KEY = "space_layout_discard_layout"
# 도면 「색 기준」(공정구분 | 투자Capa | 필요 단축)과 그 기준의 그룹 체크(2026-10-16 사용자 결정).
# 체크 key 는 `space_color_<line|capa>_<그룹>` 이다 — 기준마다 따로라 기준을 바꿔도 다른 쪽 체크가
# 남는다. 필요 단축은 그룹이 없다(2026-10-24 — 색은 단축 일수 구간). 칸 이름은 사이드바가 먼저 읽어
# `navigation` 에 있다(그 값이 필요 단축일 때만 시나리오·조회기간 줄이 선다).
COLOR_BASIS_KEY = SPACE_COLOR_BASIS_KEY
_COLOR_KEY_PARTS = {COLOR_BASIS_LINE_TYPE: "line", COLOR_BASIS_CAPA: "capa"}
# 세션 기준일(T). 층 상세 도면 맨 위의 페이더를 놓을 때·FAB 의 「오늘로」가 바꾼다(2026-10-16
# 사용자 결정). 세션에 든 날짜는 범위 안으로 맞춰 쓰고, 값이 없는 세션은 늘 오늘이다.
# `space_status_stage_filter` 키는 읽지 않는다.
SPACE_AS_OF_KEY = "space_status_as_of"
# 층 상세 도면에서 누른 호기(동, 층, 설비명) — 아래 호기 표를 그 설비 줄만으로 좁힌다
# (2026-10-23 사용자 결정). 뷰어의 `on_pick_change` 콜백이 쓰고 「층 전체 보기」 단추가 지운다.
# 연 층이 바뀌면(다른 층·FAB) 풀린다.
SPACE_PICKED_KEY = "space_status_picked_unit"
# 「공식과 견주기」(설계 8-3) — 경로 줄 끝에 늘 선다. 해당 없는 회차(공식 배치·호기 차이 없음·배치
# 편집 중·샘플)에는 다른 key 의 끈 채 잠근 토글을 같은 자리에 세운다 — 조건부로 생겼다 사라지면 아래
# 뷰어 순번이 밀려 다시 마운트되고 배율을 잃는다(검토 L11). 켠 값은 세션에 남는다(층·화면을 옮겨도).
COMPARE_KEY = "space_compare_official_v1"
COMPARE_LOCKED_KEY = "space_compare_official_locked_v1"
COMPARE_LABEL = "공식과 견주기"
COMPARE_HELP = (
    "옮긴 호기의 공식 자리를 점선으로 그립니다 — 같은 층 안에서 옮겼으면 가는 선으로 잇고, 다른 "
    "층으로 보냈거나 다른 층에서 왔으면 꼬리표를 답니다. FAB 전체에서는 층 목록에 「공식과 다름」 "
    "칸과 층 블록 풍선 한 줄이 섭니다. 도면 요소·Main 설비명 위치 차이는 머리 알림의 수만 봅니다."
)
COMPARE_COLUMN = "공식과 다름"
COMPARE_COLUMN_HELP = (
    "이 층에서 나갔거나 들어왔거나 이 층 안에서 옮긴, 공식과 자리가 다른 설비 수입니다(Main 설비로 "
    "묶은 모듈은 합쳐 1대, 이 설비 시나리오에 일정이 없는 호기는 세지 않음)."
)


def color_group_key(basis: str, group: str) -> str:
    """색 기준 그룹 체크박스의 위젯 key."""
    return f"space_color_{_COLOR_KEY_PARTS[basis]}_{group}"


def _set_space_as_of(chosen: date) -> None:
    """페이더·「오늘로」의 기준일 콜백(`on_asOf_change`). 본문보다 먼저 돌아 그 회차의 범례·
    요약·호기 표가 새 기준일이다. 범위 밖이면 가까운 끝으로 맞춘다."""
    st.session_state[SPACE_AS_OF_KEY] = clamp_as_of(chosen, date.today())


def _pick_unit(key: FloorKey, unit_id: str | None) -> None:
    """층 상세 뷰어의 호기 누르기 콜백(`on_pick_change`). 누른 호기를 그 층과 함께 쥔다 —
    아래 호기 표가 그 설비 줄만이다. None(도면 요소·빈 곳·Esc)이면 풀어 층 전체로 돌아간다."""
    if unit_id is None:
        st.session_state.pop(SPACE_PICKED_KEY, None)
    else:
        st.session_state[SPACE_PICKED_KEY] = (key[0], key[1], unit_id)


def _show_whole_floor() -> None:
    """「층 전체 보기」 콜백 — 누른 호기를 풀어 아래 표가 층 전체로 돌아간다(도면의 고르기도
    풀린다)."""
    st.session_state.pop(SPACE_PICKED_KEY, None)


def _markdown_text(value: str) -> str:
    """설비명을 마크다운 글자 그대로 — ASCII 문장부호 앞에 `\\` 를 붙인다(`*`·`_`·`$` 등이 서식이
    되지 않게)."""
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", value)


def _picked_unit(key: FloorKey) -> str | None:
    """이 층에서 누른 호기의 설비명. 다른 층에서 누른 값이면 지우고 None 이다(층을 바꾸면
    풀린다)."""
    stored = st.session_state.get(SPACE_PICKED_KEY)
    if (
        isinstance(stored, tuple)
        and len(stored) == 3
        and (stored[0], stored[1]) == key
        and isinstance(stored[2], str)
        and stored[2]
    ):
        return stored[2]
    st.session_state.pop(SPACE_PICKED_KEY, None)
    return None


def _show_fab_overview() -> None:
    """FAB 전체로 돌아간다(콜백). 주소의 `floor` 인자만 지운다."""
    st.session_state.pop(SELECTED_BUILDING_KEY, None)
    st.session_state.pop(SELECTED_FLOOR_KEY, None)
    if FLOOR_PARAM in st.query_params:
        del st.query_params[FLOOR_PARAM]


def _open_floor(key: FloorKey) -> None:
    """그 층을 연다. 블록 누르기·층 바로 가기·층 목록 표가 모두 이것을 **콜백**에서 부른다 — 콜백은
    본문보다 먼저 돌아 재실행 한 번으로 층 상세가 서고, 본문에서 `st.rerun()` 할 때처럼 아직 안 그린
    위젯 상태가 버려지지 않는다. 주소에는 `floor` 인자만 적는다(다른 인자는 그대로).

    층 목록의 `사용 편집` 초안은 여기서 버린다(「저장하지 않고 층을 열면 고친 것은 버려집니다」) —
    토글이 위젯 상태로 남은 채 이 회차를 맞으면 페이지보다 먼저 도는 `app.py` 의 탭 점·떠나기
    확인·테마 단추 확인이 이미 버린 초안을 한 회차 더 센다."""
    discard_floor_state_draft()
    st.session_state[SELECTED_BUILDING_KEY], st.session_state[SELECTED_FLOOR_KEY] = key
    if st.query_params.get(FLOOR_PARAM) != floor_param(key):
        st.query_params[FLOOR_PARAM] = floor_param(key)


def _open_unless_inactive(inactive: frozenset[FloorKey], key: FloorKey) -> None:
    """FAB 도면 블록 누르기(뷰어·편집기 [열기])의 서버 쪽 거름 — 그린 회차의 비활성 층이면
    아무것도 하지 않는다. 브라우저도 비활성 블록을 열지 않지만 옛 브라우저·같은 epoch 안의 경합
    대비 두 겹이다. 층 목록 표·층 바로 가기·주소는 이 거름을 지나지 않는다(비활성 층도 연다)."""
    if key in inactive:
        return
    _open_floor(key)


def _jump_to_floor(widget_key: str) -> None:
    """`층 바로 가기` 콜백."""
    key = floor_from_label(st.session_state.get(widget_key))
    if key is not None:
        _open_floor(key)


def _compare_lock_reason(editing: bool) -> str | None:
    """「공식과 견주기」 를 켤 수 없는 까닭(켤 수 있으면 None). 견줄 것은 그리는 스냅샷의 호기
    차이다(머리 알림과 같은 재료 — 역할이 아니라 그리는 한 벌로 정한다)."""
    if using_sample_equipment:
        return "샘플 데이터에는 공식과 견줄 배치가 없습니다."
    if equipment_session.unmerged or latest_snapshot is None:
        return "일정 없이 연 세션이라 공식과 견줄 배치가 없습니다."
    if not latest_snapshot.layout_official_places:
        if equipment_session.is_assumption:
            return "이 설비 시나리오의 호기 배치는 공식과 같습니다."
        return "공식 배치를 보는 중입니다 — 가정 설비 시나리오를 고르면 공식과 견줍니다."
    if editing:
        return "배치 편집 중에는 견주지 않습니다 — 편집을 끄면 다시 켤 수 있습니다."
    return None


def _units(value: float) -> str:
    return f"{format_unit_count(value)}대"


SPACE_CARD_LABEL = "Space 조건"
# 사이드바 `Space 조건` 카드의 공정소분류 필터 칸(세션에 남는 보기 조건).
PROCESS_FILTER_KEY = "space_status_process_filter"
# 배치 편집 토글 도움말 끝 — 켜기 전에 필요 단축 보기가 쉰다는 것을 알 수 있게(결정 D7·명세 4-4).
LAYER_REST_HELP = (
    "색 기준이 「필요 단축」 이면 편집하는 동안 그 보기를 쉬고, 편집을 끄면 다시 보입니다."
)
SPACE_CARD_NAME = "space"


def _render_layer_rest_caption(*, pinned_today: bool = False) -> None:
    """필요 단축 보기가 배치 편집 중 쉰다는 한 줄(결정 D7·명세 4-4). 한 화면에 한 번만 적는다 — 층
    상세는 편집기 위(`_render_layout_editor`), FAB 편집은 편집기 캡션이 없어 본문 조작 줄이 적는다.
    `pinned_today` 면 보기는 오늘 기준이었다고 덧붙인다(편집기는 세션 기준일이다)."""
    st.caption(
        ":material/pause_circle: 배치 편집 중에는 필요 단축 보기를 쉽니다 — 편집을 끄면 다시 "
        "보입니다" + (" (필요 단축 보기는 오늘 기준이었습니다)." if pinned_today else "."),
        width="stretch",
    )


today = date.today()
# 필요 단축 보기의 「필요 단축 일정에서 이 공정 보기」 대기 — 본문 맨 앞에서 옮긴다(콜백 안
# switch_page 금지).
switch_to_queued_shortening()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    # 사이드바에서 고른 설비 시나리오(새 세션은 공식)의 배치를 그린다(설비 시나리오 2단계 LY3) —
    # 세션 쌍(공통 최신, 고른 일정 리비전)을 합친 스냅샷 하나다. 가정 설비 시나리오면 그 리비전의
    # 배치 차이가 얹혀 있다. 상태 색·일정 없음·층 목록 대수·FAB 블록 대수도 모두 세션 쌍이다.
    equipment_session = resolve_equipment_session(equipment_database_path)
    latest_snapshot = equipment_session.snapshot
    floor_canvases = load_floor_layout_canvases(equipment_database_path)
    floors_with_layout_image = {
        (summary.building, summary.floor)
        for summary in load_floor_layout_summaries(equipment_database_path)
        if summary.has_image
    }
    # 저장된 FAB 전체 도면(캔버스·배경 도면 행, 요소). 요소가 없으면 기본 배치를 그린다.
    fab_profile, fab_stored_marks = load_fab_layout(equipment_database_path)
    # 동·층 사용 상태(설비 0029, 공용 현행값 — 설비 시나리오와 무관). 비활성 층은 층 목록 표 맨
    # 아래로 내려가고 FAB 도면에서 회색 빗금으로 흐려지며, 층 고르기(바로 가기·「다른 층으로
    # 보내기」)에서 빠진다. 샘플 fleet 화면에서도 저장된 상태를 그대로 그린다.
    floor_states = load_floor_states(equipment_database_path)
    inactive_floors = floor_states.inactive
    # 이 설비 시나리오에 일정이 없는 호기는 그리지 않는다(G2 — 계산 프레임).
    unscheduled_count = 0
    # 필요 단축 보기가 계획에 넘길 계산 세 표 — 샘플로 덮기 **전**의 것이다(필요 단축 일정과 같은
    # 길로 `shortening_frames` 가 샘플 세 표를 다시 낸다 — 같은 계획 키).
    shortening_saved: Frames = (
        latest_snapshot.calculation_frames()
        if latest_snapshot is not None
        else (empty_equipment_baseline(), empty_equipment_master(), empty_downtime_schedule())
    )
    if latest_snapshot is None or latest_snapshot.equipment.empty:
        equipment = sample_equipment_master(anchor_date=today)
        downtime = sample_downtime_schedule(anchor_date=today)
        using_sample_equipment = True
    else:
        _, equipment, downtime = latest_snapshot.calculation_frames()
        unscheduled_count = len(latest_snapshot.unscheduled_units)
        using_sample_equipment = False
    # 머리 알림의 도면 요소·Main 설비명 위치 실효 차이(가정 리비전만 질의한다).
    floor_differences = floor_layout_differences(equipment_database_path, equipment_session)
except BOOTSTRAP_ERRORS as exc:
    st.error(
        "Space 설비 데이터를 준비하지 못했습니다: "
        + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
    )
    st.stop()

# 필요 단축 일정 「도면에서 보기」 로 온 회차 — 색 기준·목표·공정 칩·층을 한 번 받고 주소 인자를
# 거둔다. 그 층은 세션 층을 덮는다(링크만 예외). 받았으면 회차를 한 번 더 돈다 —
# 사이드바(시나리오·조회기간 줄)는 페이지보다 먼저 그려져 이 회차에는 옛 색 기준으로 섰다. 아직 그린
# 편집기가 없는 자리다.
if consume_layer_link(
    basis_key=COLOR_BASIS_KEY,
    location_keys=(SELECTED_BUILDING_KEY, SELECTED_FLOOR_KEY),
    floor_param_name=FLOOR_PARAM,
    clear_keys=(SPACE_PICKED_KEY,),
    edit_keys=(EDIT_MODE_KEY, FAB_EDIT_MODE_KEY),
    inactive=frozenset(inactive_floors),
    filter_key=PROCESS_FILTER_KEY,
):
    st.rerun()

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

# 본문 머리에는 적용 이력 줄을 두지 않는다 — 배치도가 쓸 자리다
# (2026-10-01 사용자 결정). 사이드바 메뉴 이름은 그대로다.
render_page_header("Space 현황", show_status=False)
render_page_guide("space_status", title="Space 현황")
# 저장 알림·버림 알림은 늘 서 있는 한 칸 안에 그린다 — 알림이 생기고 사라질 때 아래 key 있는
# 묶음의 자리가 밀리면 `st.rerun()` 으로 끊긴 회차의 사본이 남는다(가용설비 현황과 같은 까닭).
notices = st.container()
with notices:
    render_flash(SPACE_FLASH_KEY)
    # 설비 DB 가 이 코드보다 새 버전이면(예전 배포로 되돌린 상태) 경고 한 줄. 막지 않는다.
    render_schema_ahead_warning(get_equipment_repository(equipment_database_path).schema_ahead)
    render_legacy_trace_warning(equipment_session)
    if not using_sample_equipment:
        for line, kind in space_layout_notices(equipment_session, floor_differences):
            # 줄은 설비 시나리오 이름·Main 설비명을 싣는다 — 물결표를 막는다(지움선 짝이 되지 않게).
            if kind == "info":
                st.info(markdown_safe_tildes(line), icon=":material/compare:")
            else:
                st.caption(f":material/layers: {markdown_safe_tildes(line)}")
    unscheduled_line = unscheduled_notice(
        unscheduled_count, official=equipment_session.is_official_pair
    )
    if unscheduled_line is not None:
        st.caption(f":material/event_busy: {unscheduled_line}")
# 편집본은 실제 저장본이 있을 때만 세운다 — 합성 데모 fleet 을 편집본에 섞으면 첫 실제 저장이
# 막힌다. 가용설비 설비 마스터와 **같은 편집본**이고 세션 토큰 하나라 어느 화면을 먼저 열어도 같다.
buffer_frames: Frames | None = None
if not using_sample_equipment and latest_snapshot is not None:
    buffer_frames = ensure_equipment_drafts(latest_snapshot)
    # 이 화면에는 설비 마스터 제출이 없지만 표시를 여기서 읽어 버린다 — 남기면 가용설비 현황의 다음
    # 회차가 정상 제출까지 막는다.
    pop_drafts_replaced()
    discarded_notice = pop_discarded_notice()
    if discarded_notice:
        notices.warning(discarded_notice, icon=":material/sync_problem:")
# 사이드바 「설비 시나리오」 줄 — 고를 수 있는 줄(팝업은 「불러오기」 만 — 배치 저장은 본문 상자).
# 편집본을 세운 **뒤에** 그린다 — 남의 저장으로 편집본을 버린 회차에 배지·머리 띠 꼬리가 「미저장
# 변경」 을 한 회차 늦게 말하지 않게(가용설비 현황·필요 단축 일정과 같은 차례).
render_equipment_scenario_row(equipment_session)
# 편집 권한(설계 8-4 — 설비 마스터 탭 배치 칸과 같은 판정). 찍힌 역할은 편집본을 세운 뒤에 읽는다
# (새 토큰이면 지워진다).
edit_mode = space_edit_mode(equipment_session, stamped_role=live_layout_role())
# 층 배치 편집(호기·도면 요소·Main 설비명 위치)을 열 수 있는가. 잠긴 회차에도 편집본은 그대로다 —
# 잠기기 전에 쌓은 변경은 저장 안 한 상자가 말한다(「배치 변경만 버리기」).
editable = buffer_frames is not None and edit_mode.layout_editable
# 설비 샘플 화면(설비 마스터가 비어 샘플 스위치를 켠 상태)인가. 이때는 FAB 편집도 끈다 — 합성 fleet
# 위에서 고친 FAB 가 실제 저장소에 들어간다(2026-10-03 사용자 결정 2).
showing_sample = False
# 호기가 없고 샘플을 끈 상태. 조건 카드에 까닭 한 줄만 두고, 빈 fleet 으로 FAB·층 목록을 그린다 —
# FAB 배치는 설비 리비전과 무관한 현행값이라 설비 저장본이 없어도 고치고 저장한다(결정 2).
no_fleet = False
if using_sample_equipment:
    # 스위치는 설비 마스터가 비었을 때만 뜻이 있다. 실데이터가 있으면 끌 것이 없다.
    if render_sample_switch(key="space_sample_switch", source="설비 운영 DB"):
        showing_sample = True
        st.caption("설비 마스터가 비어 있어 데모 fleet 을 표시합니다.")
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
# FAB 전체 배치 편집은 공식 설비 시나리오에서만(G5 — 건물은 가정 시나리오가 없다). FAB 대기분 저장은
# 어느 세션에서나 된다(대기분은 공식 세션에서만 생기고 FAB 은 시나리오 없는 공용 값이다 — 설계 8-5).
# 샘플 화면에서는 둘 다 막는다.
fab_editable = not showing_sample and edit_mode.fab
fab_save_blocked = showing_sample

# 색 기준 「필요 단축」(2026-10-24 결정). 고른 회차(`layer_requested`)라도 배치 편집 중이면
# 쉰다(결정 D7 — 라디오 값은 그대로, 편집기는 공정구분 기본 색). 둘 다 위젯보다 먼저 세션에서
# 읽는다(`editing_requested` 와 같은 꼴). FAB 편집 토글은 `fab_editable` 이 거짓이면 아래가 값을
# 끄므로 그 조건도 함께 본다. 비활성 층 상세에서도 보기는 선다(층 사용 명세 8-2 — 배너 아래, 그
# 층에 남은 호기를 열어 보여 준다). 그 층에는 추가N 을 붙이지 않는다(새 호기를 들일 자리가 아니다).
layer_requested = st.session_state.get(COLOR_BASIS_KEY) == COLOR_BASIS_SHORTENING
# 호기가 없는 화면은 색 기준 라디오를 세우지 않는다 — 세션에 남은(또는 링크가 적은) 「필요 단축」
# 이면 사이드바가 시나리오·조회기간 줄을 세우는데 끌 길이 없다. 기본 값으로 적고 회차 끝에 한 번
# 더 돈다(그 회차의 위젯을 모두 그린 뒤 — `st.rerun()` 규칙).
sidebar_rows_stale = no_fleet and layer_requested
if sidebar_rows_stale:
    st.session_state[COLOR_BASIS_KEY] = COLOR_BASIS_LINE_TYPE
    layer_requested = False
layer_editing = (
    bool(st.session_state.get(EDIT_MODE_KEY, False)) and editable
    if selected is not None
    else bool(st.session_state.get(FAB_EDIT_MODE_KEY, False)) and fab_editable
)
layer_active = layer_requested and not no_fleet and not layer_editing

# 세션 기준일(T)은 페이더 범위(오늘 ±12개월) 안이다. 날이 지나 범위를 벗어난 값은 가까운 끝으로
# 맞춰 둔다. 값이 없으면(페이더를 아직 건드리지 않은 세션) 오늘이고 세션에 적지 않는다 — 날이
# 바뀌면 새 오늘을 따른다. 필요 단축 보기가 켠 회차는 오늘로 고정한다(결정 D2 — 계획이 오늘
# 기준이다). 세션 기준일은 지우지도 쓰지도 않는다 — 색 기준을 되돌리면 보던 날로 돌아온다.
as_of_bounds = as_of_range(today)
stored_as_of = st.session_state.get(SPACE_AS_OF_KEY)
as_of = today if layer_active else clamp_as_of(stored_as_of, today)
if not layer_active and stored_as_of is not None and stored_as_of != as_of:
    st.session_state[SPACE_AS_OF_KEY] = as_of
all_status = get_space_equipment_status(equipment, downtime, as_of=as_of)
if no_fleet:
    # 고를 호기가 없어 조건 위젯을 세우지 않는다(카드에는 위의 까닭 한 줄).
    selected_processes: list[str] = []
    color_choice = default_color_choice()
else:
    # 필터는 사이드바 조건 카드 `Space 조건` 이다(2026-09-29 사용자 결정). 기준일은 층 상세 도면
    # 맨 위의 페이더이고, 단계 필터는 두지 않는다(2026-10-16 사용자 결정). 이 화면은 배치·공간만
    # 본다 — 기간별 단계 전환은 가용설비 현황 Main 의 「단계 전환」이다(2026-10-01 사용자 결정).
    with condition_card(SPACE_CARD_LABEL, name=SPACE_CARD_NAME):
        selected_processes = st.multiselect(
            "공정소분류",
            options=all_status["공정소분류"].dropna().drop_duplicates().tolist(),
            placeholder="전체",
            key=PROCESS_FILTER_KEY,
            persist_state="session",
        )
        # 도면 색 기준은 하나만 고른다(2026-10-16 사용자 결정 — 질문 7). 고른 기준의 그룹마다
        # 체크(처음엔 모두 켬)이고, 체크한 그룹만 그 색이다. 바꾸면 도면은 같은 epoch 로 색만 다시
        # 칠한다(배율 유지).
        basis = st.radio(
            "색 기준",
            options=COLOR_BASES,
            horizontal=True,
            key=COLOR_BASIS_KEY,
            persist_state="session",
            help=(
                "도면 상자를 무엇으로 칠할지 고릅니다. 체크한 그룹만 그 색이고 나머지는 "
                "회색입니다. 보관(검정)·지연(빨강)은 체크와 상관없이 칠합니다(필요 단축에서는 "
                "칠하지 않습니다). 「필요 단축」 은 필요 단축 일정과 같은 계산 · 이 화면의 설비 "
                "시나리오 · 오늘 기준으로 Qual 을 당길 호기를 단축 일수 구간 색과 배지로 보입니다 "
                "— "
                "켠 동안 사이드바에 시나리오·조회기간 줄이 섭니다."
            ),
        )
        capa = (
            capa_groups(all_status[INVESTMENT_CAPA_COLUMN])
            if INVESTMENT_CAPA_COLUMN in all_status.columns
            else ()
        )
        basis_groups = color_basis_groups(basis, capa)
        enabled: set[str] = set()
        if basis == COLOR_BASIS_CAPA and not basis_groups:
            st.caption("숫자로 읽히는 투자Capa 값이 없어 모든 상자가 회색입니다.")
        with st.container(horizontal=True, gap="small", key="space_color_groups"):
            for group in basis_groups:
                if st.checkbox(
                    group.replace("~", "\\~"),
                    value=True,
                    key=color_group_key(basis, group),
                    persist_state="session",
                ):
                    enabled.add(group)
        color_choice = ColorChoice(basis, capa, frozenset(enabled))
        # 체크박스 글자 앞의 그룹 색 견본(CSS — 라벨에는 색 칸을 넣을 수 없다).
        st.html(
            color_check_style(
                [
                    (color_group_key(basis, style.label), style.fill)
                    for style in color_choice.styles()
                ]
            )
        )

# 그리는 색 기준 하나 — 필요 단축을 골랐는데 쉬는 회차(배치 편집 중·호기 없음)는 공정구분 기본
# 색이다. 편집기 채우기와 머리 줄 범례가 같이 쓴다(범례만 빈 「그 밖」 으로 남지 않게).
effective_choice = (
    default_color_choice(color_choice.capa)
    if color_choice.basis == COLOR_BASIS_SHORTENING and not layer_active
    else color_choice
)

space_equipment = all_status.copy()
if selected_processes:
    space_equipment = space_equipment.loc[space_equipment["공정소분류"].isin(selected_processes)]
has_supported_location = pd.Series(
    [
        (building, floor) in valid_location_pairs
        for building, floor in zip(space_equipment["동"], space_equipment["층"], strict=False)
    ],
    index=space_equipment.index,
)
located_equipment = space_equipment.loc[
    space_equipment[LAYOUT_REFLECTED_COLUMN].fillna(False)
    & space_equipment["동"].notna()
    & space_equipment["층"].notna()
    & space_equipment[["X좌표", "Y좌표", "Xsize", "Ysize"]].notna().all(axis=1)
    & has_supported_location
].copy()
# 그리는 행(located)과 세는 행(counted)을 가른다 — 배치는 설비 단위다. 공정소분류 필터가 모듈 행
# 일부만 남기면 그 몫만 센다. 여기서 되돌리지 않는다.
counted_equipment = placed_unit_rows(space_equipment, located_equipment)
# 도면에 서지 않은 설비는 둘로 가른다. 레이아웃표시 Y 면 「미배치」(좌표를 넣으면 설 자리가 있다),
# N 이면 「레이아웃 제외」. 도면 이탈일(반출/이설일정, 없으면 정지일정)이 지난 호기는 공간에 없으니
# 어디에도 세지 않는다 — 상태 이름이 아니라 판정의 `도면이탈여부` 를 본다(정지한 뒤 반출/이설 전인
# 호기는 「정지」이지만 아직 공간에 있다).
exited = space_equipment[LAYOUT_EXITED_COLUMN].fillna(False).astype(bool)
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


def _roster_rows(floor_status: pd.DataFrame, boundaries: pd.DataFrame) -> pd.DataFrame:
    """층 상세 뷰어가 그리는 행 — 페이더 범위 전체의 합집합(`drawn_in_range`)."""
    return floor_status.loc[drawn_in_range(floor_status, boundaries, start=as_of_bounds[0])]


def _floor_viewer_inputs(
    key: FloorKey,
    floor_status: pd.DataFrame,
    boundaries: pd.DataFrame,
    layer_looks: dict[str, dict[str, Any]] | None = None,
) -> tuple[tuple[FloorLayoutMark, ...], dict[str, str], list[dict[str, Any]], str]:
    """층 상세 뷰어의 도면 요소·Main 설비명 위치·호기 payload·그리는 호기 지문. 요소·위치는 세션
    설비 시나리오의 합친 값이다(`effective_floor_layout` — 공식 층 현행값 ⊕ 그 리비전의 배치 차이).

    그리는 호기는 기준일 하나의 행이 아니라 **페이더 범위 전체의 합집합**이다(레이아웃표시 Y ·
    좌표 · 범위 시작 뒤까지 도면에 남음, `drawn_in_range`). 기준일에 안 보이는 호기는 브라우저가
    숨긴다 — 끄는 동안 도면 이탈일을 넘어도 목록·epoch 가 그대로라 다시 서며 배율을 잃지 않는다.

    `layer_looks` 는 색 기준 「필요 단축」 을 켠 회차의 설비명 → 구간·흐림(`floor_layer.looks`)이다
    — 기본 면 위에 얹는다(`apply_layer_looks`). epoch 는 바뀌지 않는다(호기마다의 칸만 바뀐다)."""
    marks, labels = effective_floor_layout(equipment_database_path, key, equipment_session)
    roster_rows = _roster_rows(floor_status, boundaries)
    looks = unit_appearance(roster_rows, boundaries, choice=effective_choice)
    if layer_looks is not None:
        looks = apply_layer_looks(looks, layer_looks)
    items = viewer_items(roster_rows, looks=looks)
    # 설비지분(기준일 보유 지분 — 모듈 넷이 모두 반입했으면 0.25씩, 둘만 반입했으면 그
    # 둘이 0.5씩이고 반입 전 둘은 0) — 뷰어 요약의 「겹쳐 숨긴 반입 예정 n대」를 범례·배치
    # 대수와 같은 축으로 센다. 일부 모듈만 반입한 Main 설비의 반입 전 모듈은 범례의 반입 전
    # 대수에 0 으로 들므로 숨겨도 0 이다. 파이썬의 기준일 값이라 페이더를 끄는 동안은 직전
    # 날의 지분이다(놓으면 그 날로 다시 받는다).
    shares = dict(
        zip(
            floor_status[EQUIPMENT_ID_COLUMN].astype("string").str.strip(),
            row_unit_shares(floor_status),
            strict=True,
        )
    )
    for item in items:
        item["share"] = float(shares.get(str(item["id"]), 1.0))
    roster = hashlib.sha256("|".join(str(item["id"]) for item in items).encode()).hexdigest()[:16]
    return tuple(marks), labels, items, roster


def _today_status() -> pd.DataFrame:
    """오늘 기준 상태(층 사용 끄기 확인의 호기 셈 — 공정소분류 필터 전). 세션 기준일이 오늘이면 이
    회차의 `all_status` 를 그대로 쓴다. 편집 모드 본문에서만 부른다."""
    if as_of == today:
        return all_status
    return get_space_equipment_status(equipment, downtime, as_of=today)


def _official_master() -> pd.DataFrame:
    """공식 배치의 설비 마스터 — 층 캔버스 줄이기 검사 재료. 공식 시나리오 세션이면 세션 스냅샷이
    곧 공식 배치이고, 그 시나리오가 가정이던 때의 리비전을 연 회차만 공식 스냅샷을 따로 읽는다."""
    if (
        latest_snapshot is not None
        and not equipment_session.is_assumption
        and equipment_session.layout_digest == EMPTY_LAYOUT_DIGEST
    ):
        return latest_snapshot.equipment
    official = official_snapshot_for(equipment_database_path, equipment_session)
    return official.equipment if official is not None else empty_equipment_master()


def _unconfirmed_count() -> int:
    """FAB 도구 줄의 「미확인 N대」 — 오늘 기준 미확인 설비 수(설비키, 공정소분류 필터 안). 기준일·
    도면 이탈과 무관하다(가용설비 현황 설비 마스터의 미확인과 같은 셈). 가정 설비 시나리오면 공식
    시나리오 일정 기준이다(1단계 결정 — 가용설비 현황 Main 과 같은 규칙)."""
    if no_fleet:
        return 0
    master = equipment
    if equipment_session.is_assumption and not using_sample_equipment:
        official = official_snapshot_for(equipment_database_path, equipment_session)
        if official is not None:
            master = official_confirmation_master(equipment, official)
    issues = get_schedule_confirmation_issues(master, today=today)
    return confirmation_counts(issues, processes=selected_processes or None)[UNCONFIRMED]


# 「다른 층으로 보내기」 목록 순서 — C1 1F, C1 2F, … (도면의 동·층 배치 순서가 아니라 이름 순).
ALL_FLOORS: tuple[FloorKey, ...] = FLOOR_KEYS


def _saved_frames() -> Frames:
    """최신 저장본의 세 표 — 편집본(`Frames`)과 같은 차례(기존 보유대수·설비 마스터·비가동 일정)."""
    assert latest_snapshot is not None
    return (latest_snapshot.baseline, latest_snapshot.equipment, latest_snapshot.downtime)


def _session_place() -> str:
    """세션 설비 시나리오 「운영 일정 · r1」(지금 보는 쌍)."""
    return f"「{equipment_value_label(equipment_session)}」"


def _scenario_place() -> str:
    """세션 설비 시나리오 이름 「셋업 실무」(가정 배치가 저장될 곳 — 새 리비전이라 rN 을 적지
    않는다)."""
    name = equipment_session.scenario_name
    return f"「{name}」" if name else "이 설비 시나리오"


def _queue_space_flash(message: str) -> None:
    """Space 알림 칸(`SPACE_FLASH_KEY`)에 성공 글을 담는다. 그 글은 `st.success` 로 그려지는데
    설비 시나리오 이름(「10~12월 증설」)을 싣는다 — 물결표를 `\\~` 로 막아 담는다(한 글에 이름이 두
    번 나오면 물결표 하나짜리 이름도 지움선 짝이 된다)."""
    queue_flash(SPACE_FLASH_KEY, markdown_safe_tildes(message))


def _official_target(session: EquipmentSession) -> tuple[str, str | None]:
    """「공식 설비 시나리오로 바꾸기」 가 옮겨 갈 (시나리오, 일정 리비전) — 최신 공식 발행, 없으면
    공식으로 볼 시나리오의 최신."""
    release = session.catalog.latest_release
    if release is not None:
        return release.equipment_scenario_id, release.schedule_revision_id
    official = session.catalog.scenario(session.official_scenario_id)
    if official is None:
        return "", None
    return official.equipment_scenario_id, official.latest_schedule_revision_id


def _latest_target(session: EquipmentSession) -> tuple[str, str | None]:
    """「최신 rM 불러오기」 가 옮겨 갈 (시나리오, 그 최신 일정 리비전)."""
    if session.scenario is None:
        return "", None
    return session.scenario.equipment_scenario_id, session.scenario.latest_schedule_revision_id


def _switch_scenario(
    database_path: str,
    scenario_id: str,
    schedule_revision_id: str | None,
    discard: bool,
    done: str,
) -> None:
    """「공식 설비 시나리오로 바꾸기」·「최신 rM 불러오기」 콜백 — 세션 설비 시나리오를 옮긴다(팝업
    「불러오기」 와 같은 `select_equipment_scenario`). 미저장 편집이 있으면 「변경을 버리고
    불러오기」 를 체크해야 한다. 미저장 FAB 전체 배치는 남는다."""
    if not scenario_id:
        return
    failure = select_equipment_scenario(
        database_path, scenario_id, schedule_revision_id, discard=discard
    )
    if failure is not None:
        st.session_state[SWITCH_ERROR_KEY] = failure
        return
    _queue_space_flash(done)


def _render_switch_popover(
    label: str,
    *,
    key: str,
    target: tuple[str, str | None],
    explanation: str,
    done: str,
) -> None:
    """설비 시나리오를 옮기는 팝오버 하나 — 미저장 편집이면 「변경을 버리고 불러오기」 체크 뒤."""
    with st.popover(label, icon=":material/swap_horiz:"):
        st.caption(markdown_safe_tildes(explanation))
        discard = True
        if has_unsaved_equipment_edits():
            discard = st.checkbox("변경을 버리고 불러오기", key=f"{key}_discard")
        st.button(
            label,
            type="primary",
            key=key,
            disabled=not discard or not target[0],
            on_click=_switch_scenario,
            args=(equipment_database_path, target[0], target[1], discard, done),
        )


def _render_switch_to_official(key: str) -> None:
    """「공식 설비 시나리오로 바꾸기」(G5 — FAB·층 캔버스·층 사용은 공식에서 고친다)."""
    _render_switch_popover(
        "공식으로 바꾸기",
        key=key,
        target=_official_target(equipment_session),
        explanation=(
            "세션의 설비 시나리오를 공식으로 옮깁니다 — 가용설비 현황·필요 단축 일정도 공식을 "
            "봅니다. 저장하지 않은 S.PKG FAB 전체 배치는 남습니다."
        ),
        done="공식 설비 시나리오를 불러왔습니다.",
    )


def _render_edit_lock_line() -> None:
    """층 배치 편집이 잠긴 회차의 까닭 한 줄(+ 「최신 rM 불러오기」), 또는 배치 빨리 감기 캡션.
    「배치 변경만 버리기」 는 저장 안 한 배치 상자에 선다(그 변경이 있을 때만)."""
    if not edit_mode.layout_editable and edit_mode.lock_reason:
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.caption(
                f":material/lock: {markdown_safe_tildes(edit_mode.lock_reason)}", width="content"
            )
            if edit_mode.lock_action == "latest":
                latest = equipment_session.latest_revision_no
                _render_switch_popover(
                    f"최신 r{latest} 불러오기",
                    key=LOAD_LATEST_KEY,
                    target=_latest_target(equipment_session),
                    explanation=(
                        f"세션을 {_session_place()} 에서 그 시나리오의 최신 "
                        f"{with_direction_particle(f'r{latest}')} 옮깁니다."
                    ),
                    done=(
                        f"최신 r{latest}{object_particle(f'r{latest}')} 불러왔습니다 — 배치 편집을 "
                        "할 수 있습니다."
                    ),
                )
    elif edit_mode.notice:
        st.caption(f":material/fast_forward: {markdown_safe_tildes(edit_mode.notice)}")


def _render_unsaved_layout_panel(frames: Frames | None) -> None:
    """저장 안 한 배치 변경(호기 배치·편집 영역·도면 요소·FAB 전체 배치)과 저장·버리기. 어느 단계
    화면에서나 뜬다.

    저장은 가용설비 설비 마스터와 같은 `save_equipment_buffer` 다 — 편집본 전체를 저장하므로 설비
    마스터의 저장 안 한 다른 편집도 함께 들어간다. 그 사실을 건수로 말한다. FAB 전체 배치는 설비
    리비전과 무관한 별도 쓰기라 `frames` 가 None(설비 저장본이 없는 화면)이어도 상자가 서고 FAB 만
    저장한다.

    편집본은 늘 세션 스냅샷에서 섰다 — 견주기도 그것과 한다. 저장은 역할로 갈린다(저장소) — 공식
    설비 시나리오면 공식 배치에, 가정이면 그 시나리오의 새 리비전(가정 배치 차이)에 쓴다. 층 배치
    편집이 잠긴 회차(`edit_mode.layout == "locked"` — 찍힌 역할이 바뀜·남이 그 시나리오에 다른
    배치를 저장·가정이던 때 리비전)에 잠기기 전에 적용한 배치 변경이 남았으면 「배치 변경만 버리기」
    가 서고 저장은 꺼진다(저장해도 저장소가 같은 까닭으로 막는다). 배치 변경이 없으면 상자는 그대로
    저장한다.
    """
    saved_snapshot = equipment_session.snapshot
    # 저장 오류는 상자를 그리지 않는 회차에도 한 번만 보이고 버린다(남의 저장으로 편집이 버려진
    # 회차에는 상자가 없다). 남겨 두면 나중의 상관없는 적용 옆에 다시 뜬다.
    error = st.session_state.pop(SAVE_ERROR_KEY, None)
    fab_pending = pending_fab_layout()
    renames = pending_unit_renames()
    # 편집본이 저장본과 내용까지 같고 이름 바꿈이 없으면 셀 비교(1,566행이면 회차마다 0.1초 넘게)를
    # 건너뛴다 — 결과는 모두 빈 값이다. 판정은 내용으로만 한다(세대 번호는 일괄 삭제를 놓친다).
    unchanged = (
        frames is None
        or saved_snapshot is None
        or buffer_matches_saved(
            (saved_snapshot.baseline, saved_snapshot.equipment, saved_snapshot.downtime),
            frames,
            renames,
        )
    )
    if frames is not None and not unchanged:
        assert saved_snapshot is not None
        changes = layout_changes(saved_snapshot.equipment, frames[1], renames)
        names = name_changes(saved_snapshot.equipment, frames[1], renames)
    else:
        changes, names = pd.DataFrame(), pd.DataFrame()
    canvases = pending_floor_canvases() if frames is not None else {}
    marks = pending_floor_marks() if frames is not None else {}
    group_labels = pending_floor_group_labels() if frames is not None else {}
    # 층 배치 편집이 잠긴 회차에 남은 배치 변경 — 저장을 끄고 「배치 변경만 버리기」 를 세운다.
    layout_locked = (
        frames is not None
        and not edit_mode.layout_editable
        and bool(not changes.empty or canvases or marks or group_labels)
    )
    if (
        changes.empty
        and names.empty
        and not canvases
        and not marks
        and not group_labels
        and fab_pending is None
    ):
        if isinstance(error, str):
            st.error(markdown_safe_tildes(f"배치를 저장하지 못했습니다: {error}"))
        return
    # 설비 마스터의 다른 편집 건수와 곁표 편집은 상자 안내에만 쓰인다 — 상자를 그릴 때만 센다.
    others, side_tables = 0, []
    if frames is not None and not unchanged:
        assert saved_snapshot is not None
        others = other_change_count(saved_snapshot.equipment, frames[1], renames)
        # 저장은 세 표를 다 견준다. 설비 마스터 밖의 편집도 리비전을 만드니 따로 말한다. 비가동
        # 일정은 저장본에 이름 바꿈을 얹어 견준다 — 따라간 설비명은 설비 마스터 편집이 아니다.
        renamed_downtime = downtime_with_renames(
            saved_snapshot.downtime, renames, saved=saved_snapshot.equipment, buffer=frames[1]
        )
        side_tables = [
            label
            for label, saved, buffer in (
                (BASELINE_TARGET, saved_snapshot.baseline, frames[0]),
                (DOWNTIME_TARGET, renamed_downtime, frames[2]),
            )
            if table_changed(saved, buffer)
        ]
    # 호기·층 배치 변경이 없다(FAB 대기분·이름 바꿈·다른 편집만).
    fab_only_layout = (
        changes.empty and names.empty and not canvases and not marks and not group_labels
    )
    parts = [f"호기 배치 {len(changes)}건"] if not changes.empty else []
    if not names.empty:
        parts.append(f"이름 바꿈 {len(names)}건")
    if canvases:
        parts.append(f"편집 영역 {len(canvases)}개 층")
    if marks:
        parts.append(f"도면 요소 {len(marks)}개 층")
    if group_labels:
        parts.append(f"Main 설비명 위치 {len(group_labels)}개 층")
    if fab_pending is not None:
        parts.append("S.PKG FAB 전체 배치")
    with st.container(border=True, key="space_unsaved_layout_panel"):
        st.markdown(f"**:material/edit_note: 저장 안 한 배치 변경** — {' · '.join(parts)}")
        st.caption(
            "적용한 변경은 이 화면(세션)에만 있습니다. 저장해야 도면·요약과 다른 사람 화면에 "
            "반영됩니다."
            + (
                f" 가용설비 현황 설비 마스터 탭의 저장 안 한 다른 편집 {others}건도 함께 "
                "저장됩니다."
                if others
                else ""
            )
            + (
                f" 가용설비 현황 설비 마스터 탭의 {'·'.join(side_tables)} 표 편집도 함께 "
                "저장됩니다."
                if side_tables
                else ""
            )
            + (
                " FAB 전체 배치는 설비 리비전을 만들지 않고 따로 저장합니다."
                if fab_pending is not None
                else ""
            )
            + (
                " S.PKG FAB 전체 배치(공식 세션에서 고친 것)도 함께 저장합니다 — 건물은 설비 "
                "시나리오가 없는 공용 값입니다."
                if fab_pending is not None and equipment_session.is_assumption
                else ""
            )
            + (f" {SAMPLE_SAVE_BLOCKED}" if fab_save_blocked else "")
        )
        if frames is not None and edit_mode.layout == "overlay" and not fab_only_layout:
            # 가정 설비 시나리오의 배치 저장 — 그 시나리오 새 리비전의 배치 차이로 간다.
            st.caption(
                markdown_safe_tildes(
                    f":material/layers: {_scenario_place()}의 새 리비전(가정 배치)으로 저장합니다 "
                    "— 공식 배치는 바뀌지 않습니다."
                    + (
                        f" {edit_mode.notice}"
                        if edit_mode.fast_forward_from is not None and edit_mode.notice
                        else ""
                    )
                )
            )
        if layout_locked:
            # 잠금 까닭은 바로 아래 잠금 줄(`_render_edit_lock_line` — 「최신 rM 불러오기」 곁)이
            # 한 번 적는다. 상자는 저장하지 않는다는 것과 「배치 변경만 버리기」 만(한 화면에
            # 한 번).
            st.caption(
                ":material/lock: 배치 편집이 잠겨 이 배치 변경은 저장하지 않습니다 — "
                + (
                    "까닭은 아래 잠금 줄에 있습니다."
                    if edit_mode.lock_reason
                    else "최신을 불러온 뒤 다시 고치세요."
                )
            )
            st.button(
                "배치 변경만 버리기",
                icon=":material/layers_clear:",
                key=DISCARD_LAYOUT_BUTTON_KEY,
                on_click=_discard_layout_only,
                help=(
                    "호기 자리·크기·레이아웃표시와 층 도면 요소·Main 설비명 위치·편집 영역 변경만 "
                    "버립니다. 설비 마스터의 다른 편집과 이름 바꿈, FAB 전체 배치는 남습니다."
                ),
            )
        if not changes.empty:
            with st.expander(f"바뀐 호기 {len(changes)}건"):
                st.dataframe(changes, hide_index=True, width="stretch")
        if not names.empty:
            # 이름 바꿈은 설비 마스터의 설비명(묶음이면 Main 설비) 자체를 바꾼다(2026-10-08 사용자
            # 결정). 같은 호기라 모든 설비 시나리오의 일정·비가동이 따라가고(G4·R2), 진척 비교
            # 기준선·바깥 Excel 은 따라가지 않는다(Guide). 설비 마스터 탭과 같은 목록 꼴이다.
            render_name_changes(names)
        if fab_pending is not None and fab_pending.marks is not None:
            for label in duplicate_block_links(fab_pending.marks):
                st.caption(
                    f":material/warning: FAB 의 층 블록 둘 이상이 {label} 을 가리킵니다(저장은 됨)."
                )
        if frames is not None:
            _render_layout_warnings(frames, marks)
        if isinstance(error, str):
            st.error(markdown_safe_tildes(f"저장하지 못했습니다: {error}"))
        note_key = f"{SAVE_NOTE_KEY}_{int(st.session_state.get(SAVE_NOTE_NONCE_KEY, 0))}"
        # 메모는 설비 리비전에만 남는다. 설비 쪽 차이가 하나도 없는(FAB 만 바뀐) 저장은 리비전을
        # 만들지 않으니 칸을 두지 않는다.
        fab_only = fab_only_layout and not others and not side_tables
        # 저장·버리기는 **콜백**이다. 본문에서 저장하고 `st.rerun()` 하면 이 상자 아래 위젯
        # (층 상세의 `배치 편집` 토글 등)이 그 회차에 그려지지 않은 것으로 끝나 상태가 버려진다 —
        # 저장하자마자 편집기가 꺼졌다(2026-10-01 브라우저 확인). 콜백은 다음 회차 전에 돈다.
        with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
            if not fab_only:
                st.text_input(
                    "변경 메모", key=note_key, placeholder="예: C1 1F 반입구 앞 정리", width=360
                )
                # 저장자·함께 넣기·공식 발행 칸(설비 마스터 저장과 같은 부품). 수는 적지 않는다 —
                # 실제로 퍼진 목록은 저장 결과 알림이 적는다.
                with st.popover("저장 칸", icon=":material/tune:"):
                    # 가정 세션은 「새 호기를 다른 설비 시나리오에도 넣기」 기본 끔(Q1).
                    render_equipment_save_fields(
                        SPACE_SAVE_FIELDS_PREFIX,
                        release_exists=equipment_session.release_no is not None,
                        assumption=equipment_session.is_assumption,
                    )
                    # 「새 호기」 칸에서 넣은 호기는 그 칸의 체크가 위 체크보다 이긴다(D8) — 끈
                    # 채 저장해도 그 칸에서 켠 호기는 다른 설비 시나리오에 든다.
                    line = (
                        new_unit_choice_line(frames, assumption=equipment_session.is_assumption)
                        if frames is not None
                        else None
                    )
                    if line is not None:
                        st.caption(line)
            # 설비 샘플 화면에서는 FAB 편집이 꺼진다(결정 2). 그 전에 적용한 FAB 대기분도 저장하지
            # 않는다 — 대기분은 두고, 스위치를 끄면 저장할 수 있다. 버리기는 그대로 된다.
            st.button(
                "배치 저장",
                type="primary",
                icon=":material/save:",
                key=SAVE_BUTTON_KEY,
                on_click=_save_space_layout,
                args=(frames, note_key, equipment_database_path, equipment_session.save_basis()),
                kwargs={"assumption": equipment_session.is_assumption},
                disabled=fab_save_blocked or layout_locked,
                help=(
                    SAMPLE_SAVE_BLOCKED
                    if fab_save_blocked
                    else (
                        "배치 편집이 잠겨 저장하지 않습니다 — 「배치 변경만 버리기」 를 쓰세요."
                        if layout_locked
                        else None
                    )
                ),
            )
            with st.popover("버리기", icon=":material/undo:"):
                st.caption(
                    "저장 안 한 설비 편집을 모두 버리고 최신 저장본으로 돌아갑니다. 가용설비 "
                    "설비 마스터 탭의 저장 안 한 편집과 FAB 전체 배치도 함께 버려집니다."
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
    """편집본의 겹침·가림 경고. 설비 마스터의 검증 실패 편집이 남아 있으면 경고만 건너뛴다."""
    try:
        status = get_space_equipment_status(frames[1], frames[2], as_of=as_of)
    except ValueError as exc:
        # 저장·버리기는 둔다(저장하면 같은 까닭으로 막히고, 버리면 풀린다).
        st.caption(
            markdown_safe_tildes(
                ":material/error: 가용설비 현황 설비 마스터 탭에 검증을 통과하지 못한 저장 안 한 "
                f"편집이 있어 겹침 경고를 계산하지 못했습니다: {exc}"
            )
        )
        return
    # 경고는 설비명을 싣는다(「NEW~01~」) — 물결표를 막는다.
    for warning in layout_warnings(status, {**_stored_marks_for(status, set(marks)), **marks}):
        st.caption(f":material/warning: {markdown_safe_tildes(warning)}")


def _discard_layout_only() -> None:
    """「배치 변경만 버리기」 콜백 — 배치 일곱 칸·층 대기분·찍힌 역할만 버린다(설계 8-6)."""
    st.session_state.pop(SAVE_ERROR_KEY, None)
    discard_layout_edits()
    _queue_space_flash(
        "배치 변경만 버렸습니다 — 설비 마스터의 다른 편집과 이름 바꿈은 남아 있습니다.",
    )


def _discard_space_layout(with_equipment: bool) -> None:
    """`모두 버리기`·`FAB 배치만 버리기` 콜백. 편집본·대기분(FAB 포함)과 남은 저장 오류를 버린다.
    `with_equipment` 가 거짓이면(설비 저장본이 없는 화면, 또는 `FAB 배치만 버리기`) FAB 대기분만
    버린다."""
    st.session_state.pop(SAVE_ERROR_KEY, None)
    if with_equipment:
        reset_equipment_drafts()
    else:
        stage_fab_layout(None, None, base=(None, ""))


def _save_space_layout(
    frames: Frames | None,
    note_key: str,
    database_path: str,
    basis: EquipmentSaveBasis | None = None,
    fields_prefix: str = SPACE_SAVE_FIELDS_PREFIX,
    *,
    assumption: bool = False,
) -> None:
    """`배치 저장` 콜백. 편집본(세 표)과 미저장 층 배치를 한 번에 쓰고 알림을 남긴다. FAB 전체
    배치는 그 앞에 따로 쓴다(설비 리비전 없음). `frames` 가 None 이면 FAB 만 쓴다. 저장은 바뀐 쪽만
    — 세 표가 그대로면 층 값만 쓴다. `basis` 는 세션의 설비 시나리오다 — 공식이면 공식 배치에,
    가정이면 그 시나리오 새 리비전의 배치 차이에 간다(저장소가 역할로 가른다). `assumption` 이면
    저장 칸이 가정 세션 꼴이다(함께 넣기 기본 끔 — Q1)."""
    note = st.session_state.get(note_key)
    try:
        message = save_equipment_buffer(
            get_equipment_repository(database_path),
            frames,
            note if isinstance(note, str) else "",
            basis=basis,
            fields=save_fields_from_state(fields_prefix, assumption=assumption),
        )
    except BOOTSTRAP_ERRORS as exc:
        # 검증·충돌(ValueError)만이 아니라 DuckDB 잠금 같은 저장 실패도 문구로 남긴다 — 콜백에서
        # 터지면 화면 전체가 오류 상자가 된다.
        st.session_state[SAVE_ERROR_KEY] = bootstrap_error_message(
            exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)
        )
        return
    st.session_state[SAVE_NOTE_NONCE_KEY] = int(st.session_state.get(SAVE_NOTE_NONCE_KEY, 0)) + 1
    _queue_space_flash(message)


def _stored_marks_for(
    status: pd.DataFrame, pending: set[FloorKey]
) -> dict[FloorKey, tuple[FloorLayoutMark, ...]]:
    """경고에 필요한 층의 저장된 도면 요소 — 편집본에 좌표가 선 호기가 있고 대기 요소가 없는 층만.
    모든 층(30개)을 읽으면 회차마다 느려지고 요소 캐시(층 단위 항목)가 밀려난다. 요소는 세션 설비
    시나리오의 합친 값이다(가정 회차의 겹침·출입금지 경고가 공식 요소로 판정되지 않게)."""
    placed = status.loc[status[["X좌표", "Y좌표"]].notna().all(axis=1), ["동", "층"]].dropna()
    floors = {(str(building), str(floor)) for building, floor in placed.itertuples(index=False)}
    return {
        key: effective_floor_layout(equipment_database_path, key, equipment_session)[0]
        for key in sorted(floors & set(ALL_FLOORS))
        if key not in pending
    }


def _render_layout_editor(
    frames: Frames, building: str, floor: str, profile: FloorLayoutProfile | None
) -> None:
    """한 층 배치 편집기. 편집본을 그리고, `적용` 이 오면 검증해 편집본·대기분에 얹는다.

    저장된 요소·이름표는 세션 설비 시나리오의 합친 값(`effective_floor_layout` — 공식 층 현행값 ⊕ 그
    리비전의 차이)이다. 대기분·「그대로인가」 판정·저장 대조 기준 지문이 모두 그것과 견준다 — 공식과
    견주면 가정 회차에 편집이 없는데도 대기분이 생긴다(검토 F15·M7). 적용이 배치를 바꾸면 그때의
    역할을 찍는다(설계 6-2)."""
    assert latest_snapshot is not None
    key: FloorKey = (building, floor)
    canvases = effective_floor_canvases(floor_canvases)
    canvas = canvases.get(key, (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT))
    stored_marks, stored_labels = effective_floor_layout(
        equipment_database_path, key, equipment_session
    )
    marks = pending_floor_marks().get(key, stored_marks)
    group_labels = pending_floor_group_labels().get(key, stored_labels)
    try:
        status = get_space_equipment_status(frames[1], frames[2], as_of=as_of)
    except ValueError as exc:
        if layer_requested:
            # 편집기를 못 연 회차도 보기는 쉰다 — 쉬는 까닭 한 줄은 여기가 맡는다(본문 조작 줄은
            # FAB 편집만).
            _render_layer_rest_caption(pinned_today=as_of != today)
        st.error(
            "가용설비 현황 설비 마스터 탭에 검증을 통과하지 못한 저장 안 한 편집이 있어 배치 "
            f"편집기를 열 수 없습니다. 설비 마스터 탭에서 고치거나 버린 뒤 여세요: {exc}"
        )
        return
    renames = pending_unit_renames()
    new_ids, arrived_ids = (
        (set(), set())
        if buffer_matches_saved(_saved_frames(), frames, renames)
        else unsaved_unit_ids(latest_snapshot.equipment, frames[1], key, renames)
    )
    # 편집기도 보기와 같은 채우기(색 기준·보관·지연, 기준일 = 사이드바 기준일)다. 테·덧표시는
    # 그리지 않는다.
    inputs = editor_inputs(
        status,
        floor=key,
        new_ids=new_ids,
        arrived_ids=arrived_ids,
        appearance=lambda rows: unit_appearance(
            rows, unit_boundaries(rows, frames[2], today=today), choice=effective_choice
        ),
    )
    options = new_unit_options(frames[1])
    # 낡은 세션(공식 시나리오·배치 빨리 감기) — 새 호기 폼만 끈다(일정이 생기는 새 호기는 낡은
    # 리비전 위 저장에서 막힌다). 가정 세션 최신에서는 새 호기를 넣는다(Q1 — 공식에는 자리 없이
    # 들어간다).
    new_unit_reason = None if edit_mode.new_units else edit_mode.new_unit_reason
    if not edit_mode.new_units:
        options = {**options, "disabled": new_unit_reason or "새 호기를 넣지 않습니다."}
        if new_unit_reason:
            st.caption(f":material/lock_clock: {markdown_safe_tildes(new_unit_reason)}")
    if layer_requested:
        # 필요 단축 보기는 편집 중 쉰다(결정 D7) — 편집기는 공정구분 기본 색이고 배지·흐림·고정 줄이
        # 없다. 층 상세의 쉬는 까닭 한 줄은 여기만 적는다(본문 조작 줄은 FAB 편집만).
        _render_layer_rest_caption(pinned_today=as_of != today)
    st.caption(
        "끌어 놓아 자리·크기를 고치고 **적용**을 누르면 이 세션의 편집본에 들어갑니다(저장 전). "
        "조건 카드의 공정소분류 필터와 상관없이 이 층의 도면 대상 호기를 모두 보입니다. "
        "층이 정해지지 않은 미배치 호기는 트레이에 함께 뜹니다. 기준일은 편집하는 동안 "
        f"{as_of.isoformat()} 로 고정입니다 — 바꾸려면 배치 편집을 끄고 도면 위 페이더를 씁니다."
    )
    # epoch: 층·저장본·편집본 세대·이 층 캔버스·요소·Main 설비명 위치·**편집 대상 호기 목록**.
    # 하나라도 바뀌면 브라우저가 새 값으로 다시 선다. 같으면 진행 중인 편집과 확대 배율을 지킨다.
    # 호기 목록은 기준일로도 바뀐다(도면 이탈일이 지난 호기가 빠진다) — 빠뜨리면 브라우저가 옛
    # 목록을 쥔 채 「이 편집기에 없는 호기」로 적용 전체가 거부된다.
    # 숨은 모듈(묶음 바둑판의 칸만 차지)도 기준일로 바뀐다 — 목록에 넣는다.
    roster = hashlib.sha256(
        "|".join(
            [f"{item['id']}:{int(bool(item['placed']))}" for item in inputs.items]
            + [f"ghost:{ghost['id']}" for ghost in inputs.ghosts]
        ).encode()
    ).hexdigest()[:16]
    epoch = "|".join(
        (
            building,
            floor,
            revision_token(latest_snapshot),
            str(equipment_buffer_generation()),
            f"{canvas[0]:g}x{canvas[1]:g}",
            floor_layout_fingerprint(marks, group_labels),
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
        # 「다른 층으로 보내기」 목록은 사용 층(과 지금 층 — 편집기가 자기 층은 뺀다)이다. epoch
        # 밖이라 남이 층을 꺼도 다음 회차에 목록만 준다. 적용 검사(`parse_editor_apply`)는 30개
        # 그대로다.
        floors=selectable_floor_keys(floor_states, keep=key),
        marks=marks,
        group_labels=group_labels,
        new_unit=options,
        as_of=as_of,
        background_image=profile.image_data_uri if profile is not None else None,
        # 층 캔버스는 공용 값이라 가정 설비 시나리오에서 끈다(설계 8-4 — 서버도 아래에서 거부).
        canvas_editable=edit_mode.canvas,
        canvas_lock=None if edit_mode.canvas else CANVAS_LOCK_REASON,
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
            editor_groups={str(item["group"]) for item in inputs.items if item.get("group")},
            # 놓이거나 자리·크기가 바뀐 모듈 묶음은 정본 바둑판 규칙과 견줘 바로잡거나 거부한다.
            # 숨은 모듈은 그 칸을 차지하고 묶음과 함께 옮겨진다.
            editor_items=inputs.items,
            editor_ghosts=inputs.ghosts,
            # 편집본에 없지만 새 설비명으로 쓸 수 없는 이름 — 설비 마스터에서 지우고 저장 안 한
            # 저장본 이름, 설비 마스터에 없는 설비명을 가리키는 비가동 일정.
            reserved=reserved_names(
                latest_snapshot.equipment, frames[1], frames[2], pending_unit_renames()
            ),
        )
        if applied.created and not edit_mode.new_units:
            # 폼을 껐지만 옛 화면이 보낸 적용 — 새 호기는 낡은 리비전 위 저장에서 막힌다.
            raise ValueError(new_unit_reason or "새 호기를 넣지 않습니다.")
        if applied.canvas is not None and not edit_mode.canvas:
            # 칸을 껐지만 옛 브라우저가 보낸 캔버스 값(두 겹 — 설계 8-4).
            raise ValueError(CANVAS_LOCK_REASON)
        next_canvases = {**canvases, **({key: applied.canvas} if applied.canvas else {})}
        master = apply_layout_edits(
            frames[1],
            applied,
            floor=key,
            canvases=next_canvases,
            default_canvas=(DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT),
        )
        # 이름 바꿈은 배치 변경(옛 이름으로 온다) 뒤에 얹고 비가동 일정의 설비명도 함께 바꾼다.
        master, downtime = apply_name_changes(master, frames[2], applied.renames)
        # 저장 때와 같은 검사를 지금 한다 — 저장 단추에서야 막히면 무엇이 문제인지 멀어진다.
        prepared = prepare_equipment_master(master, floor_canvases=next_canvases)
        if applied.renames:
            prepare_downtime_for_prepared_equipment(downtime, prepared)
        # Main 설비명 위치 — 실린 모듈 묶음은 보낸 위치로(처음 위치면 행 없음), 이름을 바꾼 묶음은
        # 새 이름으로 따라간다.
        sizes = module_group_sizes(inputs.items, inputs.ghosts)
        next_labels = next_group_labels(group_labels, applied, sizes)
    except ValueError as exc:
        st.error(markdown_safe_tildes(f"적용하지 못했습니다: {exc}"))
        return
    stored_canvas = floor_canvases.get(key)
    base = (stored_canvas, floor_layout_fingerprint(stored_marks, stored_labels))
    replace_equipment_buffer((frames[0], master, downtime))
    # 이 적용이 옮기거나 빼거나 보낸 모듈 묶음의 적용 뒤 모양 — 저장 검사가 그 모양 그대로인 묶음을
    # 편집기 결과로 보고 통과시킨다(설비 마스터의 모듈 좌표·크기 막기, `saved_master_violations`).
    touched = {change.unit_id for change in (*applied.changes, *applied.hidden_moves)}
    moved_groups = {
        applied.group_renames.get(str(row["group"]), str(row["group"]))
        for row in (*inputs.items, *inputs.ghosts)
        if row.get("group") in sizes and str(row["id"]) in touched
    }
    stage_editor_module_layouts(module_layouts(master, moved_groups))
    if applied.renames:
        stage_unit_renames(
            compose_renames(pending_unit_renames(), applied, saved=latest_snapshot.equipment)
        )
        follow_unit_renames(applied.unit_renames, applied.group_renames)
    # 이 적용이 지운 「새 호기」 칸 호기의 함께 넣기 고름을 걷는다 — 이름 바꿈을 따라간 뒤에(D8).
    prune_new_unit_propagation()
    if applied.canvas is not None:
        unchanged = applied.canvas == (
            stored_canvas or (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
        )
        stage_floor_canvas(key, None if unchanged else applied.canvas, base=base)
    if applied.marks is not None:
        unchanged = marks_fingerprint(applied.marks) == marks_fingerprint(stored_marks)
        stage_floor_marks(key, None if unchanged else applied.marks, base=base)
    if next_labels != group_labels:
        stage_floor_group_labels(
            key, None if next_labels == stored_labels else next_labels, base=base
        )
    if (
        applied.changes
        or applied.hidden_moves
        or applied.created
        or applied.canvas is not None
        or applied.marks is not None
        or next_labels != group_labels
    ):
        # 배치를 바꾼 적용 — 그때의 역할(공식 배치 · 이 시나리오의 가정 배치)을 찍는다. 저장이 쓰기
        # 잠금 안의 역할과 대조한다(그 사이 남의 발행이면 막힌다 — 설계 6-2).
        stamp_layout_role(equipment_session.layout_role)
    renamed = (
        f" 이름 바꿈 {len(applied.renames)}건도 넣었습니다"
        + (
            " — 같은 호기라 비가동 일정의 설비명이 따라가고, 저장하면 모든 설비 시나리오의 일정이 "
            "새 이름을 따라갑니다."
            if applied.unit_renames
            else "."
        )
        if applied.renames
        else ""
    )
    # 목록이 줄기 전에 비활성 층으로 보낸 호기 — 받되(저장 검사 그대로, S5) 알린다.
    sent_to = {change.move_to for change in applied.changes if change.move_to is not None}
    sent_note = "".join(
        f" 보낸 층 {floor_label(target)} 는 비활성 층입니다 — 호기는 그 층에 들어가고 Space "
        "목록·도면에서 숨습니다."
        for target in FLOOR_KEYS
        if target in sent_to and target in inactive_floors
    )
    overlay_note = (
        f" 저장하면 {_scenario_place()}의 가정 배치로 들어가고 공식 배치는 바뀌지 않습니다."
        if equipment_session.layout_role == "overlay"
        else ""
    )
    _queue_space_flash(
        f"{building} {floor} 배치를 편집본에 적용했습니다. 저장해야 다른 사람 화면에 반영됩니다."
        + overlay_note
        + renamed
        + sent_note,
    )
    st.rerun()


def _render_fab_editor(
    link_stats: dict[str, dict[str, str | None]],
    background_image: str | None,
    on_open: Callable[[FloorKey], None],
) -> None:
    """FAB 전체 배치 편집기. 대기분(없으면 저장본, 그것도 없으면 기본 배치)을 그리고, `적용` 이
    오면 검증해 세션 대기분에 얹는다(저장 전). 설비 편집본과 무관하다. 비활성 층 블록은 회색으로
    그리고(`link_stats` 의 `inactive`) 옮기기·크기·연결 바꾸기는 되며 [열기] 만 꺼진다(`on_open` 이
    서버에서도 거른다). epoch 에 층 사용 상태를 넣지 않는다 — 남이 층을 꺼도 적용 전 편집을 잃지
    않게."""
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
        on_open=on_open,
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
        st.error(markdown_safe_tildes(f"적용하지 못했습니다: {exc}"))
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
    _queue_space_flash(
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
    # 선택지는 사용 층과 지금 연 층(비활성이어도 — 경로 줄이 「지금 어디인가」 를 말하게)이다.
    # 글자는 「C1 3F」 그대로다 — 라벨에 상태를 넣으면 남이 그 층을 다시 켤 때 브라우저가 옛 글자를
    # 되보낸다(AGENTS 9장). 비활성이라는 말은 층 상세의 배너가 한다. 비활성 층으로 옮기는 길은 층
    # 목록 표 「비활성 층」 이다.
    floor_labels = [floor_label(key) for key in selectable_floor_keys(floor_states, keep=selected)]
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
        disabled=not floor_labels,
    )
    st.space("stretch")
    # 층 배치 편집 중에는 견주지 않는다(편집기에는 보내지 않는다). 편집 토글 값은 앞 회차의 것이다 —
    # 이 줄은 층 상세 머리 줄보다 먼저 선다.
    compare_lock = _compare_lock_reason(
        selected is not None and editable and bool(st.session_state.get(EDIT_MODE_KEY, False))
    )
    if compare_lock is None:
        compare_on = st.toggle(
            COMPARE_LABEL, key=COMPARE_KEY, persist_state="session", help=COMPARE_HELP
        )
    else:
        st.toggle(
            COMPARE_LABEL, value=False, key=COMPARE_LOCKED_KEY, disabled=True, help=compare_lock
        )
        compare_on = False

# 저장 안 한 배치 상자의 자리는 늘 서 있다(내용만 비었다 찼다). 상자가 첫 적용에 새로
# 서거나 저장·버리기로 사라질 때 아래 층 상세·FAB 상자의 순번이 밀리면, Streamlit 은 요소를
# key 가 아니라 순번으로 갈아 끼우므로 편집기를 새로 마운트한다. 그 사이 본문 높이가 화면
# 높이로 무너져 스크롤이 맨 위로 튀고, 브라우저에 둔 편집기 상태(서랍·배율)도 잃는다.
panel_drawn = buffer_frames is not None or pending_fab_layout() is not None
with st.container(key="space_unsaved_layout_slot"):
    if panel_drawn:
        _render_unsaved_layout_panel(buffer_frames)
# 층 배치 편집이 잠긴 회차의 까닭 한 줄(「최신 rM 불러오기」)·배치 빨리 감기 캡션. 자리는 늘
# 선다(잠금이 생기고 풀릴 때 아래 층 상세·FAB 상자가 밀리지 않게). 시나리오 바꾸기 실패는 늘 여기서
# 한 번 보이고, 저장 오류는 상자가 없는 회차에만 여기서 보인다.
with st.container(key="space_edit_lock_slot"):
    switch_error = st.session_state.pop(SWITCH_ERROR_KEY, None)
    if isinstance(switch_error, str):
        st.error(markdown_safe_tildes(f"설비 시나리오를 바꾸지 못했습니다: {switch_error}"))
    save_error = None if panel_drawn else st.session_state.pop(SAVE_ERROR_KEY, None)
    if isinstance(save_error, str):
        st.error(markdown_safe_tildes(save_error))
    if buffer_frames is not None:
        _render_edit_lock_line()

# 필요 단축 보기의 본문 조작 줄(결정 D6 — 목표 확보율·흐리게·못 읽음 알림). 자리는 늘 선다 — 빈 칸은
# 높이가 없다(테두리를 주지 않는다). 끈 회차는 칸만 세우고 아무것도 부르지 않는다(AGENTS 5장 9 —
# 시뮬레이션 쪽 부름 0). 쉬는 회차(배치 편집 중)는 FAB 편집이면 까닭 한 줄만 — 층 상세는 편집기 위
# 캡션이 같은 글을 적어 여기는 비운다(한 화면에 한 번).
space_layer: SpaceLayer | None = None
layer_dim = True
with st.container(
    horizontal=True, vertical_alignment="center", gap="small", key="space_shortening_toolbar"
):
    if layer_active:
        controls = render_layer_controls()
        layer_dim = controls.dim_others
        loaded = load_space_layer(
            saved=shortening_saved,
            sample=using_sample_equipment,
            show_sample=showing_sample,
            has_snapshot=latest_snapshot is not None,
            database_path=equipment_database_path,
            today=today,
            level=controls.level,
            unmerged=equipment_session.unmerged,
        )
        if isinstance(loaded, ShorteningStop):
            render_layer_stop(loaded)
        else:
            space_layer = loaded
    elif layer_requested and layer_editing and selected is None:
        _render_layer_rest_caption()
# 필요 단축 FAB 요약(공정소분류 필터를 따름 — 결정 D11). 비활성 층은 층 대수를 싣지 않는다.
layer_scope = frozenset(selected_processes) if selected_processes else None
layer_summary: FabSummary | None = (
    fab_layer_summary(
        space_layer.layer,
        counted_equipment,
        processes=layer_scope,
        inactive=frozenset(inactive_floors),
    )
    if space_layer is not None
    else None
)
# 기준 캡션과 링크 공정 알림 — 자리는 늘 선다(켜고 끌 때 아래가 밀리지 않게).
with st.container(key="space_shortening_basis_slot"):
    if space_layer is not None:
        render_layer_basis(
            equipment_session, space_layer, sample=showing_sample, summary=layer_summary
        )
        render_arrival_filter_note(selected_processes, selected)
    elif not layer_active:
        forget_arrival_note()

if selected is None:
    # FAB 로 돌아오면 층 상세에서 누른 호기는 풀린다(층을 바꾼 것과 같다).
    st.session_state.pop(SPACE_PICKED_KEY, None)
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
    # 합계는 모든 층이다(가용설비 현황 대수와 맞는다). 비활성 층에 남은 배치·미배치는 끝에 따로
    # 말한다 — 사용 층 표 합 + 비활성 층 + 동·층 미정 = 배치 + 미배치.
    inactive_units = sum(
        placement.placed + placement.unplaced
        for placement in placements
        if placement.key in inactive_floors
    )
    if inactive_units > 0:
        fab_summary += f" · 비활성 층 {_units(inactive_units)}"
    # 보기는 저장본이다(저장된 요소가 없으면 기본 배치). 저장 안 한 FAB 편집은 편집기와 상자가
    # 말한다.
    fab_canvas, fab_marks = effective_fab_layout(fab_profile, fab_stored_marks)
    fab_background = fab_profile.image_data_uri if fab_profile is not None else None
    # 「공식과 견주기」 를 켜면 층마다 공식과 자리가 다른 설비 수 — 층 목록 칸과 블록 풍선 한 줄.
    # 층 상세 견주기와 같이 그리는 호기(공정 필터를 지난 것)만 센다 — 같은 표의 배치대수와 맞게.
    unit_differences = (
        floor_unit_differences(
            equipment_session,
            shown=set(space_equipment[EQUIPMENT_ID_COLUMN].dropna().astype(str)),
        )
        if compare_on
        else {}
    )
    # 필요 단축 보기를 켠 동안 층 블록 셋째 줄과 층 목록 표 칸 넷(비활성 층에는 싣지 않는다). epoch
    # 밖이라 목표·필터를 바꿔도 배율이 그대로다.
    layer_counts = (
        fab_floor_counts(
            space_layer.layer,
            counted_equipment,
            not_placed,
            processes=layer_scope,
            inactive=frozenset(inactive_floors),
        )
        if space_layer is not None
        else None
    )
    short_lines = (
        {
            key: short_line
            for key, count in layer_counts.items()
            if (short_line := floor_short_line(count)) is not None
        }
        if layer_counts is not None
        else None
    )
    block_stats = floor_block_stats(
        placements,
        inactive={key: inactive_label(reason) for key, reason in inactive_floors.items()},
        layout_differences=unit_differences,
        short_lines=short_lines,
    )
    # 비활성 층 블록은 눌러도 열지 않는다(브라우저가 거르고 서버도 거른다 — 그린 회차의 집합).
    open_active_floor = partial(_open_unless_inactive, frozenset(inactive_floors))
    with st.container(border=True):
        # 머리 줄은 층 상세와 같은 구조다(제목 · 도면·캔버스 편집 · 배치 편집 · 오른쪽 범례 자리).
        # FAB 범례 자리는 비워 둔다 — 블록 색의 뜻은 사용자가 도면 글자로 적는다.
        with st.container(
            horizontal=True, gap="small", vertical_alignment="center", key="space_fab_head"
        ):
            st.markdown("#### :material/domain: S.PKG FAB 전체 배치", width="content")
            # 잠근 까닭 — 샘플 화면, 가정 설비 시나리오(FAB 은 공식에서만 — G5).
            fab_lock = (
                "샘플 데이터를 보는 중에는 FAB 배치를 고치지 않습니다."
                if showing_sample
                else FAB_LOCK_REASON
            )
            render_fab_layout_drawing_editor(
                database_path=equipment_database_path,
                disabled=not fab_editable,
                reason=None if fab_editable else fab_lock,
            )
            # 설비 저장본이 없어도 켠다(FAB 는 설비 리비전과 무관한 현행값, 결정 2). 샘플 화면·가정
            # 설비 시나리오에서는 끈다. 잠글 때는 **값도 끈다** — 켜 둔 채 잠그면 스위치는 켜짐인데
            # 보기 전용 도면이 그려져 화면이 서로 다른 말을 했다(2026-10-05 E2E). 적용해 둔 대기분은
            # 그대로다(어느 세션에서나 저장된다).
            if not fab_editable:
                st.session_state[FAB_EDIT_MODE_KEY] = False
            fab_editing = (
                st.toggle(
                    "배치 편집",
                    key=FAB_EDIT_MODE_KEY,
                    disabled=not fab_editable,
                    help=(
                        fab_lock
                        if not fab_editable
                        else "층 블록·영역·글자를 끌어 놓아 자리·크기를 고치고, 층 블록의 "
                        "연결 층과 색을 고릅니다. 적용한 변경은 저장하기 전까지 이 세션에만 "
                        "있습니다. " + LAYER_REST_HELP
                    ),
                )
                and fab_editable
            )
            if not showing_sample and not edit_mode.fab and not equipment_session.unmerged:
                # 가정 설비 시나리오 — FAB 자리의 「공식으로 바꾸기」(설계 8-4 표). 일정 없이
                # 연 회차(`unmerged` — 옛 배포 흔적)는 세우지 않는다 — 공식으로 옮겨도 같은
                # 까닭으로 합쳐지지 않는다(1단계 규칙 그대로).
                _render_switch_to_official(SWITCH_TO_OFFICIAL_KEY)
            st.space("stretch")
        if fab_editing:
            _render_fab_editor(block_stats, fab_background, open_active_floor)
        else:
            render_fab_layout_viewer(
                key=FAB_VIEWER_KEY,
                # 도면(캔버스·요소)과 층 사용 상태가 바뀔 때만 새로 선다 — 비활성 블록의 초점·역할은
                # 블록을 세울 때 정해진다. 보던 배율은 잃지 않는다(FAB 의 보기 층은 늘 같다). 블록
                # 대수·기준일·미확인 대수는 epoch 밖이라 기준일·필터가 바뀌면 글자만 다시 쓴다.
                epoch="|".join(
                    (
                        "fab",
                        fab_layout_fingerprint(fab_canvas, fab_marks),
                        floor_states_fingerprint(floor_states),
                    )
                ),
                canvas=fab_canvas,
                marks=fab_marks,
                link_stats=block_stats,
                summary=fab_summary,
                on_open=open_active_floor,
                as_of=as_of,
                today=today,
                as_of_range=as_of_bounds,
                unconfirmed=_unconfirmed_count(),
                on_as_of=_set_space_as_of,
                background_image=fab_background,
            )
    # 필요 단축 요약·추가 호기 상자 — 자리는 늘 선다(켜고 끌 때 아래 key 있는 층 목록 표가 밀리지
    # 않게).
    with st.container(key="space_shortening_fab_slot"):
        if space_layer is not None and layer_summary is not None:
            render_fab_layer_summary(
                space_layer,
                layer_summary,
                [
                    unit
                    for unit in space_layer.layer.virtuals
                    if layer_scope is None or unit.process in layer_scope
                ],
            )
    if exited_count > 0:
        st.caption(
            f"기준일 {as_of.isoformat()}에 반출/이설(없으면 정지)을 마친 "
            f"{_units(exited_count)}는 공간에 없어 세지 않습니다."
        )

    # 층 목록 표. 층마다 배치·미배치·점유율을 견주는 자리이고, 층 바로 가기와 함께 키보드로 층을
    # 여는 길이다(행에 초점을 두고 Shift+Space). 행을 고르면 그 층이 열린다. 비활성 층은 맨 아래
    # 접힌 「비활성 층 n개」 로 내려가고 표 머리 `사용 편집` 이 층 사용 상태를 고친다 — 공용
    # 설정이라 공식 설비 시나리오에서만 연다(Q3 — G5 와 같은 까닭). 샘플 fleet 화면에서도 잠근다.
    render_space_floor_list(
        database_path=equipment_database_path,
        placements=placements,
        floors_with_image=floors_with_layout_image,
        canvas_text=_canvas_text,
        states=floor_states,
        unit_counts=lambda: floor_unit_counts(_today_status()),
        editable=not showing_sample and edit_mode.floor_state,
        on_open=_open_floor,
        locked_reason=None if showing_sample else FLOOR_STATE_LOCK_REASON,
        # 덧붙임 칸 — 「공식과 견주기」 를 켜면 「공식과 다름」(사용·비활성 두 표), 필요 단축 보기를
        # 켠 동안은 칸 넷(사용 층 표만). 함께 켜지면 이 차례로 기본 칸 뒤에 선다.
        extra_columns=(
            *(
                (
                    FloorListColumn(
                        COMPARE_COLUMN,
                        {
                            placement.key: unit_differences.get(placement.key, 0)
                            for placement in placements
                        },
                        st.column_config.NumberColumn(format="localized", help=COMPARE_COLUMN_HELP),
                    ),
                )
                if compare_on
                else ()
            ),
            *(layer_columns(layer_table_columns(layer_counts)) if layer_counts is not None else ()),
        ),
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
    # 비활성 층을 연 회차(층 목록 표 「비활성 층」·주소)의 배너. 자리는 늘 선다 — 남이 층을 켜고
    # 끌 때 아래 층 상세가 밀리지 않게.
    with st.container(key="space_floor_inactive_notice_slot"):
        selected_reason = floor_states.reason_of(selected)
        if selected_reason is not None:
            st.info(
                f":material/block: 이 층은 비활성({inactive_label(selected_reason)})입니다 — FAB "
                "도면·층 바로 가기·「다른 층으로 보내기」에서 빠집니다. 호기는 그대로이고 FAB 전체 "
                "층 목록 표의 「사용 편집」에서 다시 켭니다."
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
        # 보기 회차는 이 층 행 전체(세는 행과 페이더 범위의 그리는 행을 모두 품는다)의 경계 날짜를
        # 한 번 구해 범례 대수와 도면 payload 가 나눠 쓴다. 편집 중에는 편집본으로 편집기가 따로
        # 구한다.
        viewing = not (editable and editing_requested)
        floor_status = space_equipment.loc[
            space_equipment["동"].eq(selected_building).fillna(False).astype(bool)
            & space_equipment["층"].eq(selected_floor).fillna(False).astype(bool)
        ]
        # 도면에서 누른 호기(이 층의 것만). 그 사이 이름이 바뀌었거나 공정소분류 필터로 빠져
        # 이 층 행에 없으면 푼다.
        picked_unit = _picked_unit(selected)
        picked_rows = (
            picked_unit_rows(floor_status, picked_unit) if picked_unit is not None else None
        )
        if picked_rows is not None and picked_rows.empty:
            st.session_state.pop(SPACE_PICKED_KEY, None)
            picked_unit = picked_rows = None
        floor_boundaries = (
            get_space_unit_boundaries(floor_status, downtime, today=today) if viewing else None
        )
        # 필요 단축 보기 — 이 층에 오늘 그려지는 행의 표시·배지·목록. 페이더 범위 합집합(뷰어
        # roster)이 아니다 — 켠 동안 기준일은 오늘 고정이라 지난 12개월 안에 나간 호기는 도면에
        # 없고, FAB 층 대수(오늘 배치 행)와 같은 축이어야 공정 칩·추가N 이 두 화면에서 같다(결정 D8
        # 「그려진 층」). 공정 칩 값은 도면을 칠하기 전에 세션에서 읽는다(칩 위젯은 도면 아래
        # 칸이다). 선택지 밖이면 위젯 전에 None 을 적는다.
        shown_layer: FloorLayer | None = None
        if space_layer is not None and floor_boundaries is not None:
            layer_rows = floor_status.loc[
                drawn_in_range(floor_status, floor_boundaries, start=as_of)
            ]
            focus = valid_focus(
                selected,
                set(layer_rows["공정소분류"].dropna().astype(str).str.strip())
                if "공정소분류" in layer_rows.columns
                else set(),
            )
            shown_layer = floor_layer(
                space_layer.layer,
                layer_rows,
                not_placed.loc[
                    not_placed["동"].eq(selected_building).fillna(False).astype(bool)
                    & not_placed["층"].eq(selected_floor).fillna(False).astype(bool)
                ],
                focus=focus,
                dim_others=layer_dim,
                inactive=selected in inactive_floors,
            )
        # 뷰어 payload 는 머리 줄 앞에서 구한다 — 범례와 도면이 한 회차 안에서 붙어 나가야 페이더를
        # 놓은 뒤 브라우저가 둘을 한 번에 맞춘다(그 사이에 payload 를 만들면 범례만 먼저 바뀐다).
        viewer_inputs = (
            _floor_viewer_inputs(
                selected,
                floor_status,
                floor_boundaries,
                shown_layer.looks if shown_layer is not None else None,
            )
            if floor_boundaries is not None
            else None
        )
        with st.container(
            horizontal=True, gap="small", vertical_alignment="center", key="space_floor_head"
        ):
            st.markdown(
                f"#### :material/map: {selected_building} {selected_floor} 상세 레이아웃",
                width="content",
            )
            # 캔버스 이탈 검사는 그린 호기(`floor_equipment`, 필터·레이아웃표시를 지난 것)가 아니라
            # 저장된 마스터 전체로 한다 — 저장 검증이 보는 행이 그것이다. 층 캔버스·배경 도면은
            # 공용 값이라 공식 설비 시나리오에서만 고친다(설계 8-4) — 그 회차 세션 스냅샷의 마스터는
            # 공식 배치다(가정이던 때 리비전이면 공식 스냅샷을 따로 읽는다).
            canvas_editable = edit_mode.canvas and not showing_sample
            render_floor_layout_editor(
                database_path=equipment_database_path,
                building=selected_building,
                floor=selected_floor,
                saved_equipment=(
                    _official_master()
                    if canvas_editable and not using_sample_equipment
                    else empty_equipment_master()
                ),
                disabled=not canvas_editable and not using_sample_equipment,
                reason=CANVAS_LOCK_REASON,
            )
            if editable:
                editing = st.toggle(
                    "배치 편집",
                    key=EDIT_MODE_KEY,
                    help=(
                        "호기·반입구·문·영역을 끌어 놓아 자리와 크기를 고칩니다. 적용한 변경은 "
                        "저장하기 전까지 이 세션에만 있습니다. " + LAYER_REST_HELP
                    ),
                )
            else:
                editing = False
                if buffer_frames is not None:
                    # 꺼진 단추 — 까닭은 풍선과 본문 위 잠금 줄(「최신 rM 불러오기」)이 말한다.
                    st.toggle(
                        "배치 편집",
                        value=False,
                        key=LOCKED_EDIT_TOGGLE_KEY,
                        disabled=True,
                        help=(
                            markdown_safe_tildes(edit_mode.lock_reason)
                            if edit_mode.lock_reason
                            else None
                        ),
                    )
            st.space("stretch")
            # 보기는 기준일의 색·테·덧표시별 대수(미확인은 오늘 기준 설비 수)다. 편집 중에는
            # 편집본을 그리므로 저장본의 대수를 달지 않고 채우기 뜻만 보인다(편집 화면은 테·덧표시를
            # 그리지 않는다).
            if floor_boundaries is None:
                legend = space_legend_markup(None, choice=effective_choice)
            elif shown_layer is not None:
                # 필요 단축 — 구간 대수(목록 줄과 같은 축)·임박 테·흐림과 지금의 테·덧표시 칸.
                legend = shortening_legend_markup(
                    shown_layer.counts,
                    space_legend_counts(
                        floor_counted, floor_boundaries, choice=effective_choice, as_of=as_of
                    ),
                    as_of=as_of,
                    dim=layer_dim,
                )
            else:
                # 켠 동안 계획을 못 읽은 회차는 상자가 모두 기본 회색이고 뷰어가 지연·보관 면을
                # 끈다(고정 줄 회차 — D12) — 채우기 칸 없이 테·덧표시만(도면에 없는 빨강·검정
                # 견본을 세우지 않는다).
                legend = space_legend_markup(
                    space_legend_counts(
                        floor_counted, floor_boundaries, choice=effective_choice, as_of=as_of
                    ),
                    choice=effective_choice,
                    as_of=as_of,
                    fills=not layer_active,
                )
            st.markdown(legend, unsafe_allow_html=True, width="content")
        if editing and buffer_frames is not None:
            _render_layout_editor(buffer_frames, selected_building, selected_floor, layout_profile)
        else:
            if viewer_inputs is None:
                # 머리 줄은 편집 요청을 보았는데 편집기가 서지 않은 회차(보통은 오지 않는다).
                viewer_inputs = _floor_viewer_inputs(
                    selected,
                    floor_status,
                    get_space_unit_boundaries(floor_status, downtime, today=today),
                )
            marks, viewer_labels, items, roster = viewer_inputs
            render_space_layout_viewer(
                key=f"space_layout_viewer_{selected_building}_{selected_floor}",
                # 저장본·캔버스·요소·그리는 호기(조건 카드 필터, 페이더 범위)가 바뀌면 새로 선다.
                # 기준일·색 기준·그룹 체크만 바뀌면 같은 epoch 다 — 날짜는 epoch 에 넣지 않는다
                # (기준일은 epoch 밖의 `asOf`, 색은 호기마다의 `fill`·`ink`). 브라우저는 바뀐 것만
                # 다시 칠하고 보던 배율을 지킨다. 저장본 쌍 토큰은 편집이 잠긴 회차에도 넣는다 —
                # 같은 epoch 회차에 브라우저는 상자 기하(자리·크기)를 쥔 것대로 지키므로, 잠긴 두
                # 쌍을 오가거나 잠긴 회차에 남이 공통을 저장하면 옛 좌표가 남는다(설계 8-1·검토 F1).
                epoch="|".join(
                    (
                        "view",
                        selected_building,
                        selected_floor,
                        "sample" if using_sample_equipment else revision_token(latest_snapshot),
                        f"{canvas_width:g}x{canvas_height:g}",
                        floor_layout_fingerprint(marks, viewer_labels),
                        roster,
                    )
                ),
                items=items,
                canvas=(canvas_width, canvas_height),
                floor=(selected_building, selected_floor),
                marks=marks,
                group_labels=viewer_labels,
                summary=summary,
                as_of=as_of,
                today=today,
                as_of_range=as_of_bounds,
                on_as_of=_set_space_as_of,
                picked=picked_unit,
                on_pick=partial(_pick_unit, selected),
                background_image=(
                    layout_profile.image_data_uri if layout_profile is not None else None
                ),
                # 「공식과 견주기」 — epoch 밖이라 켜고 꺼도 다시 마운트하지 않는다. 그리는
                # 호기(공정 필터·일정 없음을 지난 것)만 견준다.
                compare=(
                    compare_payload(
                        equipment_session,
                        selected,
                        shown=set(space_equipment[EQUIPMENT_ID_COLUMN].dropna().astype(str)),
                    )
                    if compare_on
                    else None
                ),
                # 필요 단축 보기 — 배지와 기준일 고정 줄(epoch 밖, 켠 동안만 키가 실린다). 계획을 못
                # 읽은 회차도 켠 동안이면 고정 줄이다 — 기준일이 오늘로 고정이라 페이더가 움직이지
                # 않는다(상자는 모두 기본 회색 — R5).
                badges=shown_layer.badges if shown_layer is not None else None,
                as_of_pinned=PINNED_NOTE if layer_active else None,
            )
    # 필요 단축 보기 칸 — 바깥은 늘 서는 테두리 없는 칸이고 켠 동안만 안쪽 테두리 칸이 선다(빈 칸에
    # 테두리를 주지 않는다 — 끈 동안 빈 테두리가 선다). 아래 key 있는 호기 표의 자리가 밀리지
    # 않는다.
    with st.container(key="space_shortening_slot"):
        if space_layer is not None and shown_layer is not None:
            render_floor_layer_panel(
                selected,
                shown_layer,
                space_layer,
                picked_unit=picked_unit,
                picked_rows=picked_rows,
                key_of=unit_keys_by_name(floor_status),
                picked_key=SPACE_PICKED_KEY,
            )
    # 아래 호기 표는 요청한 21칸이다(`FLOOR_TABLE_COLUMNS`). 도면에서 호기를 누르면 그 설비
    # 줄만(모듈이면 그 Main 설비 줄 전부, 누른 모듈이 첫 줄), 「층 전체 보기」 로 층 전체로
    # 돌아간다(2026-10-23 사용자 결정). 줄 머리와 단추는 늘 세운다 — 누를 때마다 표 위 줄이
    # 생기고 사라지며 아래가 밀리지 않게.
    with st.container(
        horizontal=True, gap="small", vertical_alignment="center", key="space_floor_table_head"
    ):
        if picked_rows is not None:
            st.markdown(
                f"**{_markdown_text(str(picked_unit))}** 의 설비 마스터 {len(picked_rows)}줄"
                + (" (같은 Main 설비 모듈)" if len(picked_rows) > 1 else ""),
                width="content",
            )
        else:
            st.caption(
                "층 전체 호기 · 도면에서 호기를 누르면 그 설비 줄만 봅니다.", width="content"
            )
        st.space("stretch")
        st.button(
            "층 전체 보기",
            icon=":material/table_rows:",
            key=f"space_floor_show_all_{selected_building}_{selected_floor}",
            on_click=_show_whole_floor,
            disabled=picked_rows is None,
            help="도면에서 누른 설비만 보던 아래 표를 층 전체 호기로 돌립니다.",
        )
    # 표 도구 막대가 바로 위 줄 오른쪽 끝 「층 전체 보기」 를 덮어 표에서 옮긴 누름을 가로채지 않게
    # 띄운다(AGENTS 9장 「표 도구 막대」).
    st.space(TABLE_TOOLBAR_CLEARANCE)
    st.dataframe(
        floor_table(floor_equipment if picked_rows is None else picked_rows),
        hide_index=True,
        width="stretch",
        # 아직 잡히지 않은 일정·메모 칸에 리터럴 "None" 이 찍혔다. 비워 두는 편이 맞다.
        placeholder="",
        column_config={
            column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
            for column in DATE_COLUMNS
        },
    )
    # 층별 호기 목록은 현장 배치 검토에 그대로 쓰인다 — 표가 좁혀져도 층 전체·모든 칸이다.
    render_csv_download(
        data=floor_equipment.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"space_{selected_building}_{selected_floor}.csv",
        key=f"space_floor_download_{selected_building}_{selected_floor}",
    )
# 호기 없는 화면에 남은 「필요 단축」 을 기본 값으로 적은 회차 — 사이드바 줄을 걷으려 한 번 더 돈다
# (모든 위젯을 그린 뒤라 그 회차의 위젯 값을 잃지 않는다).
if sidebar_rows_stale:
    st.rerun()
