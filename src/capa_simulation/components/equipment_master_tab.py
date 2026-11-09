# Purpose: 가용설비 현황 탭 ① 「설비 마스터」 본문(표·오른쪽 칸·저장 구획)을 그리고 출납을 받는다.

"""가용설비 현황 탭 ① 「설비 마스터」(개편 명세 2-3·4장 — 옛 RawData 폼을 대신한다).

- **열려 있을 때만 그린다**(D11 — AGENTS 9장 「숨은 탭에서도 입력 위젯은 그린다」 의 예외). 표
  편집은
  세션 칸(편집본·출납 기억)에 살아 숨은 회차에 그릴 까닭이 없다. 숨은 회차에 버려지는 위젯 값은 작은
  편집표 둘의 적용 전 편집(화면 탭 줄 떠나기 확인이 잡는다)·변경 메모(입력 초안)뿐이고, 저장자는
  `persist_state` 로 지킨다. 페이지는 이 모듈을 탭이 열린 회차에만 불러온다
  —
  표 컴포넌트 모듈이 읽힐 때 등록한다.
- **자리**: 맨 위 줄(표 고르기 · 설비 시나리오 알약 · 저장 전 변경 수) → 알림 칸(늘 서 있는 칸 —
  CCv2 마운트 앞에 생겼다 사라지는 요소를 모두 그 안에 둔다, 명세 2-3) → 테두리 하나의 편집기 영역
  (`equipment_master_grid.FRAME_KEY`) 안 두 칸(key 가로 칸 — `SPLIT_KEY`). 왼쪽은 표 구획(불러오기
  · 그 줄 끝의 메뉴 「엑셀·CSV」 · 표) 또는 작은 편집표, 오른쪽은 칸막이(끌어 폭 바꾸기 · 칸 머리의
  접기 단추 — 브라우저 몫) → 「호기 상세 · 새 호기 · 저장 전 변경 · 저장 이력」 고르기 → 본문
  칸(`SIDE_BODY_KEY` — 그 칸, 창 높이 상한 안에서 스크롤). 오른쪽 칸은 붙어 있다(sticky). 받기
  콜백이 오른쪽 칸을 열면(`_switch_side`) 접힌 칸을 편다.
- **새 호기**(개편 단계 C): 오른쪽 「새 호기」 칸 — 초안(세션 `NEW_UNIT_DRAFT_KEY`, 브라우저가
  칸을 확정할 때마다 상태 값 `draft` 로 보낸다)을 `equipment_grid.new_unit_check` 로 보고 체크 상자
  셋(에러 없이 추가 · 가용대수 · 도면)과 칸 오류를 싣는다. 「호기 추가」 는 출납 op `add` 라 받은
  초안을 다시 보고 편집본 끝·불러온 목록 맨 위에 넣은 뒤 그 호기를 「호기 상세」 로 연다. 오른쪽 칸
  고르기 말고도 첫 화면 「+ 새 호기」·상세 「이 호기로 새 호기 만들기」·「비슷한 호기에서 값
  가져오기」 가 이 칸을 연다.
  오른쪽 칸 고르기는 받기 콜백이 바로 적지 않고 다음 고르기 앞에서 적는다(`side_panel.switch_side` —
  그 고르기 뒤에 그린 마운트의 콜백도 같은 길).
- **출납**: 표·오른쪽 칸이 보낸 상태 값 `outbox` 를 받기 콜백(본문보다 먼저 돈다)이 두 마운트를 함께
  읽어 반영한다(`equipment_grid.pending_ops`·`apply_ops` → `apply_master_grid_result`). 반영한
  마지막
  seq 는 마운트마다 `ack` 로 돌려준다. 그린 회차의 조건(`GridContext` — `base`·잠금)을 콜백 인자로
  묶는다. 배치 칸을 바꾼 출납은 그때의 역할을 찍는다(`stamp_layout_role` — 탭 제출과 같다).
- **저장**: 「저장 전 변경」 아래 저장 구획 하나 — 변경 메모 · 저장자 · 「한 단계 되돌리기」·
  「모두 버리기」(확인 팝오버)·「리비전 저장」. 체크 · 확인 칸은 없다 — 함께 넣기 · 공식 발행 ·
  지우기는 늘 하고 일어난 일은 결과 알림이 적는다(`equipment_save_fields` 모듈 설명). 「리비전
  저장」 은
  잠그지
  않는다(출납은 300ms 묶음이라 마지막 회차의 판정은 브라우저보다 늦다) — 콜백이 출납을 먼저 반영한
  뒤
  오류·고친 것 없음을 판정해 단추 아래에 알린다. 두 번 누름 거르기의 잣대는 편집본 세대가 아니라
  `base`(저장본 쌍 토큰 + 씨뿌린 세대 — `buffer_base`)다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import astuple
from datetime import date
from functools import partial
from typing import Any, Final

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components import equipment_master_grid as grid_component
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.equipment_data_workspace import (
    _NOTE_CLEAR_KEY,
    _NOTE_KEY,
    BASELINE_DRAFT_KEY,
    BUFFER_KEY,
    DOWNTIME_DRAFT_KEY,
    DOWNTIME_EDITOR_KEY,
    DOWNTIME_VIEW_PREFIX,
    DRAFT_REVISION_KEY,
    EQUIPMENT_DRAFT_KEY,
    GRID_DETAIL_KEY,
    GRID_LOADED_KEY,
    GRID_MEMO_KEY,
    GRID_RESULT_KEY,
    MASTER_TABLE_KEY,
    NEW_UNIT_DRAFT_KEY,
    NOTHING_SAVED_MESSAGE,
    SAVE_FIELDS_PREFIX,
    STALE_SCENARIO_EDITS_TAB,
    Frames,
    LayoutMode,
    _example_row_count,
    _history_scenario,
    _official_places_by_name,
    _render_current_data_downloads,
    _render_history,
    _stale_lock_message,
    apply_master_grid_result,
    buffer_base,
    buffer_has_layout_edits,
    carry_layout_memo,
    carry_until_head_rerun,
    defer_grid_undo,
    equipment_buffer_generation,
    floor_layout_words,
    grid_loaded_ids,
    grid_overlay,
    grid_toasts,
    grid_undo_steps,
    layout_lock_origins,
    layout_memo_mark,
    official_layout_cells,
    pending_fab_layout,
    pending_floor_canvases,
    pending_floor_group_labels,
    pending_floor_marks,
    pending_unit_renames,
    queue_grid_result,
    queue_grid_toast,
    render_name_changes,
    render_small_editor,
    reset_equipment_drafts,
    restore_bulk_deletion,
    save_equipment_buffer,
    saved_master_violations,
    settle_bulk_restore,
    settle_grid_toasts,
    settle_grid_undo,
    stale_delete_lock,
    stale_save_reasons,
    stale_save_refusal,
    stamp_layout_role,
)
from capa_simulation.components.equipment_data_workspace import (
    NAME_CHANGES_EXPANDER_KEY as _NAME_CHANGES_KEY,
)
from capa_simulation.components.equipment_data_workspace import (
    _confirmation_master as confirmation_master,
)
from capa_simulation.components.equipment_import_dialog import (
    IMPORT_DIALOG_TITLE,
    import_closed_count,
    import_opened_from_menu,
    open_equipment_import,
)
from capa_simulation.components.equipment_save_fields import (
    EquipmentSaveBasis,
    render_saved_by_field,
    saved_by_from_state,
)
from capa_simulation.components.equipment_scenario_status import render_load_latest_button
from capa_simulation.components.equipment_settings_dialog import (
    EQUIPMENT_DIALOG_KEY,
    IMPORT_DIALOG,
)
from capa_simulation.components.flash import FlashKind, queue_flash, render_flash
from capa_simulation.components.literal_markdown import (
    literal_markdown,
    markdown_safe_tildes,
    quoted,
)
from capa_simulation.components.save_section import discard_popover
from capa_simulation.components.saved_note import note_placeholder
from capa_simulation.components.side_panel import render_side_head, split_frame, switch_side
from capa_simulation.components.state_alerts import tab_name
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.components.table_view_controls import filter_widget_key
from capa_simulation.components.widget_generation import bump, widget_key
from capa_simulation.components.write_guard import current_generation, just_written, note_written
from capa_simulation.equipment_scenario_activation import (
    UNMERGED_LOCK_REASON,
    EquipmentSession,
    SpaceEditMode,
)
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    forget_page_dialogs,
)
from capa_simulation.persistence.equipment_cache import load_floor_states
from capa_simulation.persistence.equipment_repository import (
    DuckDBEquipmentRepository,
    EquipmentSnapshot,
    legacy_trace_message,
)
from capa_simulation.services.equipment_bulk_delete import (
    BASELINE_TARGET,
    DOWNTIME_TARGET,
)
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    SCENARIO_LAYOUT_COLUMNS,
)
from capa_simulation.services.equipment_csv import (
    baseline_csv_template,
    downtime_csv_template,
    equipment_csv_template,
)
from capa_simulation.services.equipment_grid import (
    GRID_ROW_LIMIT,
    NAME_INDEX,
    GridApplied,
    GridContext,
    GridSource,
    GridState,
    GridView,
    all_load_ids,
    apply_ops,
    blank_draft,
    build_grid_view,
    cell_text,
    change_counts,
    changes_data,
    copied_draft,
    copy_source,
    detail_data,
    draft_seq_of,
    draft_texts,
    grid_data,
    grid_index,
    kept_draft,
    load_ids,
    loader_data,
    move_ids,
    new_unit_check,
    new_unit_data,
    pending_ops,
    prune_loaded,
    save_id_map,
    text_matrix,
    unit_texts,
)
from capa_simulation.services.equipment_validation import (
    MasterIssue,
    equipment_master_issues,
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
)
from capa_simulation.services.floor_layout_profile import FloorCanvasMap
from capa_simulation.services.floor_state import (
    FloorStates,
    floors_by_building,
    inactive_floor_warnings,
    master_location_options,
)
from capa_simulation.services.grid_outbox import this_session
from capa_simulation.services.korean_particle import with_object_particle
from capa_simulation.services.layout_overlay import assumption_group_refusal
from capa_simulation.services.schedule_confirmation import (
    CONFIRMATION_KIND_COLUMN,
    STAGE_COLUMN,
)
from capa_simulation.services.simulation_cache import get_schedule_confirmation_issues
from capa_simulation.services.space_layout_edit import (
    buffer_matches_saved,
    module_layout_message,
    name_changes,
)

# 표 고르기(맨 위 줄)와 오른쪽 칸 고르기 — 라벨은 고정한다(수를 넣으면 위젯 id 가 흔들린다). 표
# 고르기 key 는 작은 편집표 판정(`small_editor_edits` — 탭 줄이 페이지보다 먼저 읽는다)도 읽어
# `equipment_data_workspace` 에 둔다.
TABLE_KEY: Final = MASTER_TABLE_KEY
SIDE_KEY: Final = grid_component.SIDE_CHOICE_KEY
TABLE_MASTER: Final = "설비 마스터"
TABLES: Final = (TABLE_MASTER, BASELINE_TARGET, DOWNTIME_TARGET)
SIDE_DETAIL: Final = "호기 상세"
SIDE_NEW: Final = "새 호기"
SIDE_CHANGES: Final = "저장 전 변경"
SIDE_HISTORY: Final = "저장 이력"
SIDES: Final = (SIDE_DETAIL, SIDE_NEW, SIDE_CHANGES, SIDE_HISTORY)
# 받기 콜백이 오른쪽 칸을 연 수 — 칸막이 data `reveal`. 늘면 접힌 오른쪽 칸을 편다(표에서 설비명을
# 누른 것이 보이게). 접힘 자체는 브라우저에만 있다.
SIDE_REVEAL_KEY: Final = grid_component.MASTER_SIDE.reveal_key
# 다음 회차에 처음 설 오른쪽 칸의 머리를 보이라는 표지 — 칸 아래쪽에서 누른 「호기 추가」 · 「이
# 호기로 새 호기 만들기」 는 다른 칸을 연다. 스크롤이 그대로면 새 칸의 가운데부터 보인다.
SIDE_HEAD_KEY: Final = "equipment_grid_side_head_v1"
# 못 찾은 설비명(다음 불러오기까지)·마운트별 마지막으로 반영한 출납 seq.
MISSING_KEY: Final = "equipment_grid_missing_v1"
APPLIED_KEY: Final = "equipment_grid_applied_v1"
# 편집본이 없을 때 온 출납을 본문에 넘긴다는 표지(`apply_outbox`).
OUTBOX_HELD_KEY: Final = "equipment_grid_outbox_held_v1"
# 저장 구획의 단추·결과 칸.
SAVE_BUTTON_KEY: Final = "equipment_master_save_v1"
# 낡은 세션 저장 거절 곁 「최신 rN 불러오기(변경 버림)」.
LOAD_LATEST_BUTTON_KEY: Final = "equipment_master_load_latest_v1"
UNDO_BUTTON_KEY: Final = "equipment_master_undo_v1"
# 「한 단계 되돌리기」 누름 세대(정수)·쓰기 표지 이름. 단추는 그린 회차의 값을 콜백 인자로 받아,
# 지금 값과 다르거나 앞 되돌리기의 창 안이면 더블클릭의 둘째 누름이라 아무것도 되돌리지
# 않는다(`_undo_step`).
UNDO_PRESS_KEY: Final = "equipment_master_undo_press_v1"
DISCARD_POPOVER_KEY: Final = "equipment_master_discard_v1"
DISCARD_CONFIRM_KEY: Final = "equipment_master_discard_confirm_v1"
SAVE_RESULT_KEY: Final = "equipment_master_save_result_v1"
# 머리를 다시 그리려 다시 도는 회차가 그리는 앞 누름의 결과(남의 공통 저장에 진 거부) — 결과 칸과
# 한 자리에 그린다. 결과 칸에 되돌리면 그 회차가 그리기 전에 온 둘째 누름의 결과가 덮는다
# (`carry_until_head_rerun`).
SAVE_RESULT_CARRIED_KEY: Final = "equipment_master_save_result_carried_v1"
# 불러오기 · 목록 비우기 결과 칸 — 고칠 입력이 없어 알림창 · Alarm 으로만 낸다(`_load_result`).
LOAD_RESULT_KEY: Final = "equipment_master_load_result_v1"
# 불러오기 줄 끝 메뉴 — 팝오버 key 꼬리는 메뉴 세대다. 「엑셀·CSV로 한꺼번에」 가 세대를 올려
# 메뉴가 팝업 뒤에 남지 않고 닫힌 채 다시 선다(`on_change` 로 여닫힘을 받으면 메뉴를 열 때마다
# 앱이 다시 돈다).
DATA_MENU_KEY: Final = "equipment_master_data_menu_v1"
DATA_MENU_GENERATION_KEY: Final = "equipment_master_data_menu_generation_v1"
IMPORT_MENU_BUTTON_KEY: Final = "equipment_master_import_open_v1"
DATA_MENU_LABEL: Final = "엑셀·CSV"
IMPORT_MENU_LABEL: Final = IMPORT_DIALOG_TITLE
SAVE_LABEL: Final = "리비전 저장"
DISCARD_LABEL: Final = "모두 버리기"
UNDO_LABEL: Final = "한 단계 되돌리기"
UNDO_HELP: Final = (
    "표 · 상세의 마지막 고침부터 한 단계씩 되돌립니다. 표 고침을 다 되돌리면 기존 보유대수 · "
    "비가동 일정의 일괄 삭제를 되살립니다 — 그 표의 적용하지 않은 편집은 먼저 편집본에 넣습니다."
)
NOTE_PLACEHOLDER: Final = note_placeholder("10월 신규 호기 반입일정 갱신")
DOWNLOAD_NOTE: Final = (
    "표에서 고친 값은 곧바로 편집본에 들어가 이 파일에 함께 실립니다(못 읽은 칸 초안은 빼고)."
)
NOTHING_TO_SAVE: Final = "고친 것이 없습니다"
# 출납을 보내는 마운트(`ack` 칸 이름) → 그 마운트 key.
_MOUNT_KEYS: Final = {
    "grid": grid_component.GRID_KEY,
    "detail": grid_component.side_key("detail"),
    "new": grid_component.side_key("new"),
    "changes": grid_component.side_key("changes"),
}
# 「새 호기」 칸 안내(가정 설비 시나리오·배치 잠금 — 설계 Q1). 가정은 표지 + 풍선(설계 규칙
# UI-TXT-01 — 새 호기 자리의 뜻은 늘 세우지 않는다), 잠금은 그 칸의 잠금 까닭 한 줄이다.
NEW_UNIT_OVERLAY_MARK: Final = "가정 배치 · 공식에는 자리 없이"
NEW_UNIT_OVERLAY_NOTE: Final = (
    "가정 설비 시나리오 — 새 호기의 동·층은 이 시나리오의 배치로만 저장되고, 공식 배치에는 자리 "
    "없이 들어갑니다(있는 묶음에 드는 모듈은 그 묶음의 동·층)."
)
NEW_UNIT_LOCKED_NOTE: Final = (
    "배치 편집이 잠겨 새 호기는 자리 없이 들어갑니다(있는 묶음에 드는 모듈은 그 묶음의 동·층)"
)


# ------------------------------------------------------------------ 세션 칸


def _store_loaded(ids: Sequence[str]) -> None:
    st.session_state[GRID_LOADED_KEY] = tuple(ids)


def _detail_id() -> str | None:
    value = st.session_state.get(GRID_DETAIL_KEY)
    return value if isinstance(value, str) and value else None


def _saved_frames() -> Frames:
    return (
        st.session_state[BASELINE_DRAFT_KEY],
        st.session_state[EQUIPMENT_DRAFT_KEY],
        st.session_state[DOWNTIME_DRAFT_KEY],
    )


def _grid_state() -> GridState:
    frames: Frames = st.session_state[BUFFER_KEY]
    return GridState(
        frames=frames,
        saved=_saved_frames(),
        renames=pending_unit_renames(),
        overlay=grid_overlay(),
        undo=grid_undo_steps(),
        loaded=grid_loaded_ids(),
        draft_seq=_new_draft()[0],
    )


def _switch_side(side: str) -> None:
    """오른쪽 칸을 바꾼다 — 다음 고르기 위젯 앞에서 적고 접힌 칸을 편다(`side_panel.switch_side` —
    진짜 콜백은 회차 맨 앞이라 같은 회차, 시험 대역은 그 고르기 뒤 마운트에서 부르므로 다음 회차).
    """
    switch_side(grid_component.MASTER_SIDE, side)


def _new_draft() -> tuple[int, list[str]]:
    """「새 호기」 칸 세션 초안 (번호, 39칸 글) — 없거나 꼴이 다르면 빈 초안."""
    value = st.session_state.get(NEW_UNIT_DRAFT_KEY)
    if isinstance(value, dict):
        seq, values = value.get("seq"), draft_texts(value.get("values"))
        if isinstance(seq, int) and values is not None:
            return seq, values
    return 0, blank_draft()


def _store_new_draft(seq: int, values: Sequence[str]) -> None:
    st.session_state[NEW_UNIT_DRAFT_KEY] = {"seq": seq, "values": list(values)}


def _result(kind: FlashKind, text: str) -> None:
    """저장 구획 단추 아래 한 줄(성공·오류·안내) — 다음 회차에 그 칸이 한 번 그린다(`flash`).

    글에 설비 시나리오·호기 이름이 들어 물결표를 막는다(「NEW~01~」 가 지움선이 되지 않게).
    """
    queue_flash(SAVE_RESULT_KEY, markdown_safe_tildes(text), kind=kind)


def _load_result(kind: FlashKind, text: str) -> None:
    """불러오기 · 목록 비우기 결과 — 표 안 띠가 아니라 알림창 · Alarm 으로만(설계 규칙 UI-NTF-03).
    띠는 닫을 때까지 남아 표를 밀어내고 그 뒤 호기를 더해도 옛 대수를 적었다. 글에 호기 이름 ·
    조건 값이 들어 구두점을 막는다."""
    queue_flash(LOAD_RESULT_KEY, literal_markdown(text), kind=kind, popup_only=True)


# ------------------------------------------------------------------ 표 조건·모양


def grid_context(
    session: EquipmentSession,
    basis: EquipmentSaveBasis | None,
    layout_mode: SpaceEditMode,
    *,
    latest_snapshot: EquipmentSnapshot | None,
    floor_states: FloorStates | None,
    master: pd.DataFrame,
    official_snapshot: EquipmentSnapshot | None = None,
    floor_canvases: FloorCanvasMap | None = None,
    today: date | None = None,
) -> GridContext:
    """한 회차의 표 조건 — 잠금 글은 세션에서(낡음·일정 없이 엶·배치 잠금), `base` 는 편집본
    출발점. `official_snapshot` 은 가정 세션의 공식 스냅샷이다 — 「공식 자리로 되돌리기」 가 공식
    일곱 칸 원래 값을 적는다(`official_layout_cells`). `floor_canvases`·`today` 는 저장 검증과 같은
    인자다(「새 호기」 칸 체크·`add` op)."""
    stale = basis is not None and basis.stale
    stale_lock: str | None = None
    if stale and basis is not None:
        stale_lock = _stale_lock_message(basis)
    elif session.unmerged:
        stale_lock = session.notice or UNMERGED_LOCK_REASON
    location = master_location_options(floor_states, master) if floor_states is not None else None
    return GridContext(
        base=buffer_base(),
        scenario_name=basis.scenario_name if basis is not None else None,
        official=basis is None or basis.official_scenario,
        stale_lock=stale_lock,
        delete_lock=stale_delete_lock(basis) if stale and basis is not None else None,
        layout_lock=(
            layout_mode.master_tab_lock_reason if layout_mode.layout == "locked" else None
        ),
        new_rows_locked=stale or session.unmerged,
        location_options=(tuple(location[0]), tuple(location[1])) if location else None,
        floors_by_building=floors_by_building(floor_states) if floor_states is not None else None,
        official_places=(
            _official_places_by_name(latest_snapshot) if layout_mode.layout == "overlay" else {}
        ),
        official_cells=(
            official_layout_cells(latest_snapshot, official_snapshot)
            if layout_mode.layout == "overlay"
            else {}
        ),
        floor_canvases=dict(floor_canvases or {}),
        today=today,
    )


def _canvas_key(canvases: FloorCanvasMap) -> tuple[tuple[Any, ...], ...]:
    return tuple(sorted((tuple(key), tuple(size)) for key, size in canvases.items()))


def _issues(master: pd.DataFrame, canvases: FloorCanvasMap, today: date) -> tuple[MasterIssue, ...]:
    """편집본 마스터의 칸 결과(저장과 같은 인자 — 캔버스·오늘). 편집본 세대·저장본 토큰·오늘·캔버스
    열쇠로 회차마다 한 번 — 세션 칸에는 튜플로 푼다(모델 인스턴스를 세션에 두지 않는다)."""
    key = (
        equipment_buffer_generation(),
        buffer_base(),
        today.isoformat(),
        _canvas_key(canvases),
    )
    memo = st.session_state.get(GRID_MEMO_KEY)
    if isinstance(memo, dict) and memo.get("issues_key") == key:
        rows = memo.get("issues")
        if isinstance(rows, tuple):
            return tuple(MasterIssue(*row) for row in rows)
    try:
        issues = equipment_master_issues(master, floor_canvases=canvases, today=today)
    except ValueError:
        issues = ()
    memo = dict(memo) if isinstance(memo, dict) else {}
    memo["issues_key"] = key
    memo["issues"] = tuple(astuple(issue) for issue in issues)
    st.session_state[GRID_MEMO_KEY] = memo
    return issues


def _texts(buffer: pd.DataFrame, saved: pd.DataFrame) -> tuple[list[list[str]], list[list[str]]]:
    """(편집본, 저장본) 설비 마스터의 화면 글자(`text_matrix` — 3천 대 × 39칸). 편집본은 편집본
    세대·출발점, 저장본은 저장본 사본 토큰 열쇠로 세션 메모(`GRID_MEMO_KEY` — 글 목록만)에 한 번 —
    바뀐 것 없는 회차·편집본만 바뀐 회차가 둘 다 다시 내지 않게(개편 명세 8장 「payload 메모」)."""
    memo = st.session_state.get(GRID_MEMO_KEY)
    memo = dict(memo) if isinstance(memo, dict) else {}
    keys = {
        "buffer": (equipment_buffer_generation(), buffer_base(), len(buffer)),
        "saved": (st.session_state.get(DRAFT_REVISION_KEY), buffer_base(), len(saved)),
    }
    result: dict[str, list[list[str]]] = {}
    for name, frame in (("buffer", buffer), ("saved", saved)):
        cached = memo.get(f"{name}_texts")
        if memo.get(f"{name}_texts_key") == keys[name] and isinstance(cached, list):
            result[name] = cached
            continue
        result[name] = text_matrix(frame.reset_index(drop=True))
        memo[f"{name}_texts_key"] = keys[name]
        memo[f"{name}_texts"] = result[name]
    st.session_state[GRID_MEMO_KEY] = memo
    return result["buffer"], result["saved"]


def _changed_rows(saved: pd.DataFrame, buffer: pd.DataFrame) -> int:
    """두 표에서 바뀐 행 수(넣음·뺌·고침을 한 행으로 — 많은 쪽)."""
    if saved.equals(buffer):
        return 0

    def rows(frame: pd.DataFrame) -> Counter[tuple[str, ...]]:
        return Counter(
            tuple(cell_text(value) for value in row) for row in frame.itertuples(index=False)
        )

    before, after = rows(saved), rows(buffer)
    return max(sum((after - before).values()), sum((before - after).values()))


# 낡기 전에 고친 시나리오 칸의 고칠 것 줄 — 저장 길 셋이 같은 판정을 쓴다
# (`equipment_data_workspace.stale_save_reasons`).
STALE_SCENARIO_EDITS: Final = STALE_SCENARIO_EDITS_TAB


def _table_errors(
    frames: Frames,
    saved: Frames,
    context: GridContext,
    *,
    layout: LayoutMode,
) -> list[str]:
    """표 단위로 저장을 막는 것 — 기존 보유대수·비가동 일정(칸 단위로 그리지 않는다)·예시 행·모듈
    묶음 바둑판·가정 세션 묶음 거부·낡은 세션의 지운 호기(개편 명세 5-2·4-5)."""
    errors: list[str] = []
    try:
        prepare_equipment_baseline(frames[0])
    except ValueError as exc:
        errors.append(f"기존 보유대수 — {exc}")
    names = frames[1][EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    try:
        prepare_downtime_for_prepared_equipment(
            frames[2], pd.DataFrame({EQUIPMENT_ID_COLUMN: names.dropna().tolist()})
        )
    except ValueError as exc:
        errors.append(f"비가동 일정 — {exc}")
    examples = _example_row_count(frames)
    if examples:
        errors.append(
            f"기존 보유대수에 손대지 않은 예시 행 {examples:,}건 — 표 고르기 「기존 보유대수」 "
            "에서 "
            "지우거나 실제 값으로 고칩니다"
        )
    violations = saved_master_violations(frames[1])
    if violations:
        errors.append(module_layout_message(violations))
    renames = pending_unit_renames().units
    # 배치 차이가 아직 없는 가정 시나리오(갓 복제한 것)는 `official_places` 가 비어도 판정한다 —
    # 그때 공식 = 저장본이다(저장소 `split_layout` 와 같은 판정, 옛 탭 제출·팝업과 같은 조건).
    if layout == "overlay":
        found = assumption_group_refusal(
            frames[1],
            saved[1],
            layout_lock_origins(frames[1], saved[1], renames),
            context.official_places,
        )
        if found is not None:
            errors.append(f"{found[1]} · Main 설비 — {found[0]}")
    if context.delete_lock:
        # 낡은 세션 — 저장(`save_equipment_buffer`)이 같은 판정으로 거부한다. 탭은 고칠 것 줄로
        # 보인다.
        errors.extend(stale_save_reasons(frames[1], saved[1], renames, in_tab=True))
    return errors


def _alerts(
    master: pd.DataFrame, official: EquipmentSnapshot | None, today: date
) -> dict[str, str]:
    """설비명 → 일정 확인 갈래 글(「Qual 미확인 · 반입 실적 누락」) — 저장을 막지 않는다. 가정 설비
    시나리오면 공식 일정 기준이다(`official`)."""
    issues = get_schedule_confirmation_issues(confirmation_master(master, official), today=today)
    alerts: dict[str, list[str]] = {}
    for name, stage, kind in zip(
        issues[EQUIPMENT_ID_COLUMN].tolist(),
        issues[STAGE_COLUMN].tolist(),
        issues[CONFIRMATION_KIND_COLUMN].tolist(),
        strict=True,
    ):
        words = alerts.setdefault(cell_text(name), [])
        word = f"{stage} {kind}"
        if word not in words:
            words.append(word)
    return {name: " · ".join(words) for name, words in alerts.items() if name}


def _others(frames: Frames, saved: Frames) -> str:
    parts: list[str] = []
    baseline = _changed_rows(saved[0], frames[0])
    if baseline:
        parts.append(f"기존 보유대수 {baseline:,}행")
    downtime = _changed_rows(saved[2], frames[2])
    if downtime:
        parts.append(f"비가동 일정 {downtime:,}행 바뀜")
    floor = floor_layout_words(
        pending_floor_canvases(), pending_floor_marks(), pending_floor_group_labels()
    )
    if floor:
        parts.append(f"층 배치({floor})")
    if pending_fab_layout() is not None:
        parts.append("S.PKG FAB 전체 배치")
    return " · ".join(parts) + " — 함께 저장됩니다" if parts else ""


def build_view(
    context: GridContext,
    *,
    floor_canvases: FloorCanvasMap,
    today: date,
    confirmation_official: EquipmentSnapshot | None,
    layout: LayoutMode,
) -> GridView:
    """이 회차의 표 모양 — 세 마운트 data 가 모두 여기서 나온다."""
    frames: Frames = st.session_state[BUFFER_KEY]
    saved = _saved_frames()
    source = GridSource(
        frames=frames,
        saved=saved,
        renames=pending_unit_renames(),
        overlay=grid_overlay(),
        issues=_issues(frames[1], floor_canvases, today),
        alerts=_alerts(frames[1], confirmation_official, today),
        table_errors=tuple(_table_errors(frames, saved, context, layout=layout)),
        others=_others(frames, saved),
        texts=_texts(frames[1], saved[1]),
    )
    return build_grid_view(source, context)


# ------------------------------------------------------------------ 받기 처리


def _acks(applied: Mapping[str, int]) -> dict[str, dict[str, Any]]:
    """마운트마다 제 `ack`(그 마운트가 보낸 출납 가운데 반영한 마지막 seq)."""
    result: dict[str, dict[str, Any]] = {}
    for target, key in _MOUNT_KEYS.items():
        mount = grid_component.outbox_mount(grid_component.outbox_value(key))
        if mount:
            result[target] = {"mount": mount, "seq": int(applied.get(mount, 0))}
    return result


def _applied() -> dict[str, int]:
    value = st.session_state.get(APPLIED_KEY)
    return (
        {str(mount): int(seq) for mount, seq in value.items() if isinstance(seq, int)}
        if isinstance(value, dict)
        else {}
    )


def apply_outbox(context: GridContext, layout: LayoutMode) -> None:
    """두 마운트(표·오른쪽 칸)의 출납에서 아직 반영하지 않은 op 를 `(at, mount, seq)` 차례로
    편집본에 얹는다. 받기 콜백과 「리비전 저장」·「한 단계 되돌리기」 콜백이 먼저 부른다(콜백
    차례에 기대지 않는다). `base` 가 다른 op 는 서비스가 버리고 결과 알림으로 세고, 앞 세션의 op 는
    세지 않고 뺀다(`this_session`).

    편집본이 없으면(저장 · 모두 버리기 콜백이 비운 뒤 본문이 다시 세우기 전에 회차가 끊김) 얹을 곳이
    없다 — op 를 건드리지 않고 표지만 남겨, 다시 세운 편집본을 본 본문이 부른다. 결과 알림 칸은 그
    회차에 다시 세우면서 비우는 칸이라 여기서 세면 사라진다."""
    if BUFFER_KEY not in st.session_state:
        st.session_state[OUTBOX_HELD_KEY] = True
        return
    values = [grid_component.outbox_value(key) for key in _MOUNT_KEYS.values()]
    ops, applied = pending_ops(values, _applied())
    st.session_state[APPLIED_KEY] = applied
    ops = this_session(ops, context.base)
    if not ops:
        return
    before = layout_memo_mark()
    result = apply_ops(_grid_state(), ops, context)
    apply_master_grid_result(result)
    _store_loaded(result.state.loaded)
    detail = _detail_id()
    if detail is not None and detail in result.moved:
        st.session_state[GRID_DETAIL_KEY] = result.moved[detail]
    _follow_added(ops, result)
    _grid_result(ops, result)
    if result.frames_changed[1] and not _layout_neutral(ops):
        _stamp_if_layout_edited(ops, layout)
    else:
        # 배치에 닿지 않는 편집 — 배치 편집 판정 메모를 새 세대로 옮긴다(다음 회차
        # `live_layout_role` 이 편집본 전체를 다시 재지 않게, 개편 명세 8장).
        carry_layout_memo(before)


def _grid_result(ops: Sequence[Mapping[str, Any]], result: GridApplied) -> None:
    """출납 결과 — 고칠 입력이 없는 결과는 알림창으로, 막힌 「호기 추가」 는 고칠 칸이 그 자리에
    있어 「새 호기」 칸 머리에 둔다(설계 규칙 UI-NTF-03)."""
    if not result.toast:
        return
    if ops[-1].get("op") == "add" and result.refused and not result.added:
        queue_grid_toast("new", result.toast)
        return
    queue_grid_result(result.toast, kind=_result_kind(result))


def _result_kind(result: GridApplied) -> FlashKind:
    """막힌 조작이 있으면 경고, 바뀐 것이 있으면 성공, 없으면 안내."""
    if result.dropped or result.refused:
        return "warning"
    return "success" if result.changed else "info"


def _follow_added(ops: Sequence[Mapping[str, Any]], result: Any) -> None:
    """「호기 추가」 op 뒤 — 마지막 호기를 상세로 열고 초안은 공정소분류·동·층만 남긴다(번호를 올려
    브라우저가 바꾼다). 막혔으면 받은 초안을 세션 초안으로 둔다(그 초안의 칸 오류가 다음 회차에
    선다). 세션 초안보다 번호가 작은 op(서비스가 말없이 버린 두 번 누름·옛 초안)는 보지 않는다 —
    다음 회차에 따로 온 둘째 누름이 넣은 뒤 초안을 옛 초안으로 덮지 않게."""
    seq, values = _new_draft()
    adds = [op for op in ops if op.get("op") == "add" and draft_seq_of(op) >= seq]
    if not adds:
        return
    top = max([seq, *(draft_seq_of(op) for op in adds)])
    last = draft_texts(adds[-1].get("draft"))
    if result.added:
        row_id, _name = result.added[-1]
        _store_new_draft(top + 1, kept_draft(last if last is not None else values))
        st.session_state[GRID_DETAIL_KEY] = row_id
        _switch_side(SIDE_DETAIL)
        st.session_state[SIDE_HEAD_KEY] = True
    elif last is not None:
        _store_new_draft(top, last)


def _stamp_if_layout_edited(ops: Sequence[Mapping[str, Any]], layout: LayoutMode) -> None:
    """배치를 바꿀 수 있는 op 뒤 편집본에 배치 편집이 있으면 그때의 역할을 찍는다(저장 때 쓰기 잠금
    안의 역할과 대조, 설계 6-2 — 탭 제출·Space 적용과 같다). 잠긴 회차는 찍지 않는다."""
    if layout == "locked" or not _touches_layout(ops):
        return
    if buffer_has_layout_edits():
        stamp_layout_role(layout)


# 배치 편집 판정에 닿지 않는 op — 칸 고침·값 넣기·붙여넣기·날짜 밀기(배치·설비명·Main 설비 칸이 아닐
# 때). 지우기·되살리기·되돌리기는 행이나 배치를 저장본 쪽으로 옮겨 판정이 바뀔 수 있다.
_NEUTRAL_OPS: Final = frozenset({"cell", "set", "paste", "shift"})


def _layout_neutral(ops: Sequence[Mapping[str, Any]]) -> bool:
    return all(op.get("op") in _NEUTRAL_OPS for op in ops) and not _touches_layout(ops)


# 배치를 바꿀 수 있는 칸 — 배치 일곱 칸과 새 호기 자리를 정하는 설비명·Main 설비.
_LAYOUT_TRIGGERS: Final = frozenset(
    {*SCENARIO_LAYOUT_COLUMNS, EQUIPMENT_ID_COLUMN, PARENT_EQUIPMENT_COLUMN}
)


def _touches_layout(ops: Sequence[Mapping[str, Any]]) -> bool:
    """배치 칸을 바꿀 수 있는 op 가 있는가 — 역할 찍기 판정(`layout_edits`, 합성 3천 대에 0.17 s
    남짓 — 샘플 관측)을 칸 고침마다 돌리지 않는다. 지우기·되살리기·칸 되돌리기는 저장본 쪽으로 가는
    길이라 새 배치 편집을 만들지 않는다. **한 단계 되돌리기(`undo`)는 넣는다** — 찍힘이 걷힌 뒤
    (`live_layout_role` — 배치 편집이 사라짐) 되돌리기가 배치 편집을 되살릴 수 있다(칸
    되돌리기·지우기·엑셀·CSV 넣기를 되돌림). **「호기 추가」(`add`)도 넣는다** — 새 호기 자리(동·층·
    레이아웃표시)는 배치 편집이라(붙여넣기 새 행·엑셀·CSV 넣기와 같다) 넣은 뒤 저장 전에 공식 설비
    시나리오가 바뀌면 찍힌 역할로 막는다(설계 6-2·Q1)."""
    for op in ops:
        name = op.get("op")
        if name in ("official", "undo", "add"):
            return True
        columns: list[object] = []
        if name in ("cell", "set"):
            columns = [op.get("col")]
        elif name == "paste" and isinstance(op.get("cols"), list):
            columns = list(op["cols"])
        if any(column in _LAYOUT_TRIGGERS for column in columns):
            return True
    return False


def _on_outbox(context: GridContext, layout: LayoutMode) -> None:
    apply_outbox(context, layout)


def _on_load(request: grid_component.LoadRequest) -> None:
    if BUFFER_KEY not in st.session_state:
        return
    frames: Frames = st.session_state[BUFFER_KEY]
    saved = st.session_state[EQUIPMENT_DRAFT_KEY]
    index = grid_index(frames[1], saved, pending_unit_renames().units)
    if request.kind == "all":
        ids = all_load_ids(frames[1], index)
    else:
        known = set(index.live) | set(index.deleted)
        ids = [row_id for row_id in request.ids if row_id in known]
    result = load_ids(grid_loaded_ids(), ids)
    _store_loaded(result.loaded)
    st.session_state[MISSING_KEY] = request.missing if request.kind == "names" else ()
    label = request.label or {"all": "전체", "alerts": "일정 확인"}.get(request.kind, "")
    text = (
        f"{label} — {result.added:,}대를 새로 불러왔습니다"
        if label
        else (f"{result.added:,}대를 새로 불러왔습니다")
    )
    if result.already:
        text += f"({result.already:,}대는 이미 목록에 있음)"
    if result.cut or (request.kind == "all" and len(index.live) > GRID_ROW_LIMIT):
        text = f"앞 {GRID_ROW_LIMIT:,}대만 불러왔습니다 — 공정·설비명으로 좁혀 불러오세요"
        _load_result("warning", text)
        return
    _load_result("success" if result.added else "info", text)


def _on_clear() -> None:
    _store_loaded(())
    st.session_state[MISSING_KEY] = ()
    _load_result("info", "목록을 비웠습니다 — 고친 내용은 그대로 남습니다")


def _open_detail(row_id: str) -> None:
    st.session_state[GRID_DETAIL_KEY] = row_id
    _switch_side(SIDE_DETAIL)


def _on_new() -> None:
    """첫 화면 「+ 새 호기」 — 오른쪽 칸을 「새 호기」 로."""
    _switch_side(SIDE_NEW)


def _on_draft(value: grid_component.DraftValue) -> None:
    """「새 호기」 칸이 보낸 초안 — 번호가 세션 초안보다 작지 않을 때만 적는다(늦게 온 옛 초안이
    가져오기·「호기 추가」 뒤 초안을 덮지 않게)."""
    seq, _values = _new_draft()
    if value.seq >= seq:
        _store_new_draft(value.seq, value.values)


def _on_copy(request: grid_component.CopyRequest) -> None:
    """가져오기 — 상세 「이 호기로 새 호기 만들기」(빈 초안에 그 호기 값) 또는 「비슷한 호기에서
    값 가져오기」(브라우저 초안 위에 설비명이 같거나 앞부분이 맞는 첫 호기 값). 「새 호기」 칸을
    연다."""
    if BUFFER_KEY not in st.session_state:
        return
    frames: Frames = st.session_state[BUFFER_KEY]
    master = frames[1].reset_index(drop=True)
    seq, values = _new_draft()
    if request.draft is not None:
        seq = max(seq, request.draft.seq)
        values = list(request.draft.values)
    if request.row_id is not None:
        live = grid_index(master, _saved_frames()[1], pending_unit_renames().units).live
        position = live.get(request.row_id)
        base: list[str] | None = None
    else:
        names = [cell_text(value) for value in master[EQUIPMENT_ID_COLUMN].tolist()]
        position = copy_source(names, request.query)
        base = values
    if position is None:
        if request.draft is not None:
            _store_new_draft(seq, values)
        what = f"「{request.query}」 설비명" if request.query else "그 호기"
        queue_grid_toast(
            "new" if request.query else "detail", f"{with_object_particle(what)} 찾지 못했습니다"
        )
        return
    source = unit_texts(master, position)
    _store_new_draft(seq + 1, copied_draft(source, base))
    name = source[NAME_INDEX]
    queue_grid_result(f"{name} 의 호기 정보·위치를 가져왔습니다 — 설비명과 일정을 채웁니다")
    _switch_side(SIDE_NEW)
    st.session_state[SIDE_HEAD_KEY] = True


def _on_grid_open(row_id: str) -> None:
    _open_detail(row_id)


def _on_side_open(row_id: str) -> None:
    """「저장 전 변경」 의 고칠 것·호기 이름 — 목록에 없으면 맨 위로 불러와 상세로 연다."""
    if row_id not in grid_loaded_ids():
        _store_loaded(load_ids(grid_loaded_ids(), [row_id]).loaded)
    _open_detail(row_id)


def _on_unload(ids: list[str]) -> None:
    drop = set(ids)
    _store_loaded(tuple(row_id for row_id in grid_loaded_ids() if row_id not in drop))


def _on_goto(table: str, unit: str) -> None:
    """「비가동 일정 표에서 고치기」 — 표 고르기를 그 표로, 그 표 설비명 거르기를 그 이름으로. 그
    표는 이 회차에 아직 그려지지 않아 잃을 편집이 없다 — 적용 보기도 거둬 요청 보기가 그대로
    선다."""
    st.session_state[TABLE_KEY] = table
    if table == DOWNTIME_TARGET and unit:
        st.session_state[filter_widget_key(DOWNTIME_VIEW_PREFIX, EQUIPMENT_ID_COLUMN)] = [unit]
        st.session_state.pop(f"{DOWNTIME_EDITOR_KEY}_applied_view", None)


def _on_import_menu() -> None:
    """메뉴 「엑셀·CSV로 한꺼번에」 — 팝업을 열고 메뉴는 세대를 올려 닫는다."""
    open_equipment_import(from_menu=True)
    bump(DATA_MENU_GENERATION_KEY)


def _on_dialog(name: str) -> None:
    if name == IMPORT_DIALOG:
        open_equipment_import()
        return
    forget_page_dialogs()
    st.session_state[EQUIPMENT_DIALOG_KEY] = name


# ------------------------------------------------------------------ 저장 구획 콜백


def _undo_step(context: GridContext, layout: LayoutMode, press: int) -> None:
    """「한 단계 되돌리기」 — 출납을 먼저 반영하고 맨 위 단계 하나를 되돌린다. 표 단계가 없으면 그
    아래 일괄 삭제를 되살린다 — 일괄 삭제가 표 단계를 비우므로 삭제는 늘 표 단계 밑이다. 그 표에
    적용하지 않은 편집이 있으면 그 편집표의 제출이 편집을 먼저 넣고 되살린다
    (`restore_bulk_deletion`).

    더블클릭(0.15초)은 한 번으로 친다. 옛 코드는 둘째 누름이 한 단계를 더 꺼내 메모3·메모2 가
    함께 돌아갔고, 첫 회차의 알림(「되돌림: 메모3 고침」)을 둘째의 것이 덮었다(2026-10-27 E2E).
    둘째 누름은 두 꼴로 닿는다 — 거르는 것도 둘이다.

    - 첫 회차가 단추를 다시 그리기 **전**의 옛 화면 — `press`(그린 회차의 누름 세대
      `UNDO_PRESS_KEY`)가 지금 세대와 다르다.
    - 첫 회차가 단추를 다시 그린 **뒤** — 세대가 같아 그것만으로는 일부러 누른 다음 단계와 가를
      수 없다. 첫 되돌리기에서 `write_guard.TRAILING_PRESS_SECONDS`(1초 — 사람 더블클릭 간격에
      회차 한 번의 여유) 안의 누름은 같은 더블클릭으로 본다(`just_written`). 두 단계를
      되돌리려면 결과를 보고 다시 누른다.

    거른 누름은 되돌리지도 알리지도 않는다. 세대·시각은 되돌리기 **전에** 적는다 — 이 회차가 그
    뒤에 끊기면 둘째 누름이 다시 되돌리지 않고 이번 누름이 빈손으로 끝날 뿐이다(다시 누르면
    된다)."""
    apply_outbox(context, layout)
    if BUFFER_KEY not in st.session_state:
        return
    if press != current_generation(UNDO_PRESS_KEY) or just_written(UNDO_PRESS_KEY):
        return
    note_written(UNDO_PRESS_KEY)
    st.session_state[UNDO_PRESS_KEY] = press + 1
    if not grid_undo_steps() and restore_bulk_deletion():
        return
    if defer_grid_undo():
        return
    _grid_undo(context, layout)


def _grid_undo(context: GridContext, layout: LayoutMode) -> None:
    """표의 맨 위 단계 하나를 되돌린다 — 「한 단계 되돌리기」 콜백, 또는 미룬 되돌리기를 잇는 작은
    편집표 제출(`render_small_editor` 의 `undo`) · 그 표가 그려지지 않은
    회차(`settle_grid_undo`)."""
    ops = [{"op": "undo", "base": context.base}]
    before = layout_memo_mark()
    result = apply_ops(_grid_state(), ops, context)
    apply_master_grid_result(result)
    _store_loaded(result.state.loaded)
    _grid_result(ops, result)
    if result.frames_changed[1]:
        _stamp_if_layout_edited(ops, layout)
    else:
        carry_layout_memo(before)


def _discard_all() -> None:
    """「모두 버리기」 확인 — 편집본을 저장본으로 다시 세운다(FAB 대기분은 남김, 되돌릴 수 없음)."""
    reset_equipment_drafts(keep_fab=True)
    _result("info", "저장하지 않은 설비 편집을 모두 버리고 저장본으로 다시 열었습니다.")


def _blocking_count(
    frames: Frames, canvases: FloorCanvasMap, today: date, context: GridContext, layout: LayoutMode
) -> int:
    issues = _issues(frames[1], canvases, today)
    overlay = grid_overlay()
    drafts = 0
    if overlay:
        live = grid_index(frames[1], _saved_frames()[1], pending_unit_renames().units).live
        drafts = sum(1 for key in overlay if key.partition("\t")[0] in live)
    table = _table_errors(frames, _saved_frames(), context, layout=layout)
    return sum(1 for issue in issues if issue.blocking) + drafts + len(table)


def _has_changes(frames: Frames) -> bool:
    return (
        not buffer_matches_saved(_saved_frames(), frames, pending_unit_renames())
        or bool(grid_overlay())
        or bool(pending_floor_canvases() or pending_floor_marks() or pending_floor_group_labels())
        or pending_fab_layout() is not None
    )


def _save_revision(
    repository: DuckDBEquipmentRepository,
    *,
    basis: EquipmentSaveBasis | None,
    context: GridContext,
    layout: LayoutMode,
    floor_canvases: FloorCanvasMap,
    today: date,
    drawn_base: str,
) -> None:
    """「리비전 저장」 — 출납을 먼저 반영하고 오류를 다시 센 뒤 0 이면 저장한다. 그린 회차의 `base`
    와 지금 `base` 가 다르면(저장 뒤의 옛 누름) 쓰지도 알리지도 않는다."""
    if buffer_base() != drawn_base:
        return
    apply_outbox(context, layout)
    frames: Frames = st.session_state[BUFFER_KEY]
    errors = _blocking_count(frames, floor_canvases, today, context, layout)
    if errors:
        _result(
            "error",
            f"오류 {errors:,}개를 고쳐야 저장됩니다 — 「저장 전 변경」 의 「저장하기 전에 고칠 "
            "것」 을 "
            "봅니다.",
        )
        return
    if not _has_changes(frames):
        _result("info", NOTHING_TO_SAVE)
        return
    renames = pending_unit_renames()
    id_map = save_id_map(grid_index(frames[1], _saved_frames()[1], renames.units), frames[1])
    loaded, detail = grid_loaded_ids(), _detail_id()
    note = st.session_state.get(_NOTE_KEY)
    try:
        message = save_equipment_buffer(
            repository,
            frames,
            note if isinstance(note, str) else "",
            basis=basis,
            saved_by=saved_by_from_state(SAVE_FIELDS_PREFIX),
            # 콜백이라 이 회차 편집본을 세우기 전이다 — 남의 공통 저장 거부면 본문이 다시 세운다.
            reopens=True,
        )
    except BOOTSTRAP_ERRORS as exc:
        _result("error", bootstrap_error_message(exc, database_paths=(repository.database_path,)))
        return
    if message == NOTHING_SAVED_MESSAGE:
        _result("info", message)
        return
    # 저장 뒤 목록·상세 id 를 새 저장본 id 로(이름 바꾼 호기 s:옛 → s:새, 새 호기 n:X → s:X, 지운
    # 호기는 뺀다 — 개편 명세 7-3).
    _store_loaded(move_ids(loaded, id_map))
    if detail is not None:
        moved = id_map.get(detail, detail)
        if moved:
            st.session_state[GRID_DETAIL_KEY] = moved
        else:
            st.session_state.pop(GRID_DETAIL_KEY, None)
    _result("success", message)


# ------------------------------------------------------------------ 그리기


def _seed(key: str, value: str, options: Sequence[str]) -> None:
    """세션에 값을 적는 위젯(콜백이 적는다)에는 `default=` 를 주지 않고 칸이 없거나 목록 밖일 때만
    심는다(AGENTS 9장)."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = value


# 맨 위 줄 표 고르기의 뜻과 칸의 저장 자리 — 표 고르기는 라벨 줄이 없고(접근성 이름 「표」 로만
# 남는다) 1.63 은 그때 위젯 풍선도 숨기므로 그 곁 빈 캡션의 풍선이 말한다. 공통 · 시나리오 · 배치
# 칸이 어디에 저장되나도 이 풍선이 말한다(2026-11-09 사용자 규칙 「페이지 상단 최소화」 — 자리는
# 상단 띠 재고 권장, 설계 규칙 UI-TXT-01 · UI-TXT-02).
HEAD_HELP: Final = (
    "표 — 설비 마스터 · 기존 보유대수 · 비가동 일정 가운데 고칠 표를 고릅니다. 일정 칸(시나리오)은 "
    "이 설비 시나리오에만, 나머지 칸(공통)은 모든 설비 시나리오에 함께 저장됩니다."
)
HEAD_LAYOUT_HELP: Final[dict[str, str]] = {
    "overlay": (
        "배치 칸은 이 시나리오에만(공식과 다른 것만) 저장되고 공식 배치는 바뀌지 않습니다 — 호기 "
        "상세 「위치」 에서 공식 자리로 되돌릴 수 있습니다."
    ),
    "official": "배치 칸은 공식 배치(공통 대장)에 저장됩니다.",
}
HEAD_LOCKED_LAYOUT_HELP: Final = "배치 칸은 지금 잠겨 있습니다."


def head_help(layout: LayoutMode) -> str:
    """맨 위 줄 표 고르기 곁 풍선 — 표의 뜻 + 칸의 저장 자리(배치 칸은 이 회차의 배치 갈래)."""
    return f"{HEAD_HELP} {HEAD_LAYOUT_HELP.get(str(layout), HEAD_LOCKED_LAYOUT_HELP)}"


def _render_head(
    session: EquipmentSession,
    basis: EquipmentSaveBasis | None,
    layout: LayoutMode,
    pending: int,
) -> str:
    """맨 위 줄 — 표 고르기 · 그 뜻 풍선 · 일정 없이 엶 · 저장 전 변경 수 · 일정 잠김. 고른 표를
    돌려준다."""
    _seed(TABLE_KEY, TABLE_MASTER, TABLES)
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        table = st.segmented_control(
            "표",
            TABLES,
            key=TABLE_KEY,
            required=True,
            persist_state="session",
            label_visibility="collapsed",
        )
        st.caption("", help=head_help(layout), width="content")
        # 설비 시나리오 알약(「설비 시나리오 · 운영 일정(공식)」)과 리비전 알약(「공통 rN · 일정
        # rM」)은 두지 않는다 — 사이드바 「설비 시나리오」 줄과 머리 띠 둘째 줄이 같은 값이다(설계
        # 규칙 UI-TXT-07, 2026-11-09 상단 띠 재고). 어느 칸이 어디에 저장되는지는 바로 앞 풍선
        # (`head_help`)이다. 일정 없이 연 회차만 그 상태 표지를 남긴다(값이 아니라 조건이 있을 때만
        # 서는 표지).
        if session.unmerged:
            st.badge("일정 없이 엶", icon=":material/event_busy:", color="gray")
        # 수가 0 이면 알약이 없다 — 늘 서 있는 칸 안에 둔다(이 줄의 자리는 그대로).
        with st.container():
            if pending:
                st.badge(f"저장 전 변경 {pending:,}건", icon=":material/edit_note:", color="orange")
        # 남이 이 시나리오에 일정을 저장해 지금 보는 리비전이 낡았다 — 자리에는 표지 한 마디, 무엇이
        # 잠겼고 어떻게 푸는지는 풍선 · 상태 알림이다(Space 배치 잠김과 같은 꼴, 2026-11-08 사용자
        # 답 c1 · 설계 규칙 UI-NTF-02 · UI-INP-07).
        with st.container(width="content"):
            if basis is not None and basis.stale:
                st.caption(
                    STALE_LOCK_MARK,
                    help=literal_markdown(_stale_lock_message(basis)),
                    width="content",
                )
    report_stale_lock(basis)
    return str(table)


# 낡은 세션 잠김 표지 — 무엇이 잠겼고 어떻게 푸는지는 풍선(`_stale_lock_message`)과 상태 알림
# `EQ-19` 다.
STALE_LOCK_MARK: Final = ":material/lock_clock: 일정 잠김"


def report_stale_lock(basis: EquipmentSaveBasis | None) -> None:
    """낡은 세션의 상태 알림(`EQ-19` — 다른 사용자가 이 설비 시나리오에 일정을 저장해 최신 리비전이
    있음). 머리 줄 표지가 서는 회차와 같은 조건이고 없어도 부른다(해소). 범위는 본 리비전, 내용은
    최신 번호다 — 더 새 리비전이 또 생기면 다시 알린다."""
    stale = basis is not None and basis.stale
    latest = basis.latest_revision_no if basis is not None else None
    alerts.state(
        "EQ-19",
        scope=(basis.equipment_scenario_id, basis.revision_no) if basis is not None else None,
        content=latest if stale else None,
        active=stale,
        text=(
            f"{quoted(basis.scenario_name)} 최신 r{latest} 있음 — 일정 칸 잠김 · 사이드바 「설비 "
            "시나리오」 에서 최신 불러오기"
            if stale and basis is not None
            else None
        ),
        full=_stale_lock_message(basis) if stale and basis is not None else None,
        tab=tab_name(EQUIPMENT_MASTER_TAB),
    )


# 배치 잠금 표지 — Space 현황의 같은 표지(`LAYOUT_LOCK_MARK`)와 같은 한 마디다. 무엇이 잠기는지와
# 까닭은 풍선이 말한다(`layout_lock_help`, 설계 규칙 UI-TXT-01 · UI-INP-07).
LAYOUT_LOCK_MARK: Final = ":material/lock: 배치 잠김"
LAYOUT_LOCK_HELP: Final = (
    "배치 편집이 잠겨 있어, 원래 있던 호기의 배치 칸은 고칠 수 없고 새 호기는 자리 없이 들어갑니다."
)


def layout_lock_help(reason: str | None) -> str:
    """배치 잠김 표지의 풍선 — 무엇이 잠기는지 한 문장, 까닭(`master_tab_lock_reason`)은 둘째 문장.
    까닭 글에도 대시가 있어 「— 까닭」 으로 이으면 대시 둘이 이어 붙는다. 까닭은 평문 겸용 글이라
    통째로 `literal_markdown` 으로 막는다."""
    if not reason:
        return LAYOUT_LOCK_HELP
    return f"{LAYOUT_LOCK_HELP} {literal_markdown(reason)}"


def _render_notices(
    session: EquipmentSession,
    basis: EquipmentSaveBasis | None,
    layout_mode: SpaceEditMode,
    floor_states: FloorStates | None,
    latest_snapshot: EquipmentSnapshot | None,
) -> None:
    """알림 — 늘 서 있는 한 칸 안에(아래 컴포넌트 마운트의 자리를 고정한다, 개편 명세 2-3)."""
    with st.container():
        layout = layout_mode.layout
        if layout == "locked":
            st.caption(
                LAYOUT_LOCK_MARK,
                help=layout_lock_help(layout_mode.master_tab_lock_reason),
                width="content",
            )
        # 가정 배치가 어디에 저장되나는 맨 위 줄 설비 시나리오 알약의 풍선이 말한다 — 자리에 같은
        # 설명 줄을 두지 않는다(설계 규칙 UI-TXT-01 · UI-TXT-07).
        frames: Frames = st.session_state[BUFFER_KEY]
        renames = pending_unit_renames()
        if renames:
            names = name_changes(_saved_frames()[1], frames[1], renames)
            if not names.empty:
                render_name_changes(names, key=_NAME_CHANGES_KEY)
        if floor_states is not None:
            saved = (
                latest_snapshot.equipment if latest_snapshot is not None else frames[1].iloc[0:0]
            )
            # 사유·호기 이름은 사람 글이다 — 짓는 함수가 하나씩 막아 끼운다(`escape`). 물결표만
            # 막으면 「DA*31*R」 의 별표가 기울임이 됐다(2026-10-27 E2E).
            for message in inactive_floor_warnings(
                frames[1], saved, floor_states, escape=literal_markdown
            ):
                st.warning(message, icon=":material/block:")


def _render_data_menu(
    repository: DuckDBEquipmentRepository,
    latest_snapshot: EquipmentSnapshot | None,
    scenario_name: str | None,
) -> None:
    """메뉴 「엑셀·CSV」 — 맨 위 「엑셀·CSV로 한꺼번에」(팝업), 그 아래 양식 셋 + 현재 데이터
    셋(개편 명세 4-9). 폭 고정은 불러오기 줄이 비워 두는 자리와 맞추려는 것이다
    (`tools_menu_style`)."""
    with st.popover(
        DATA_MENU_LABEL,
        key=widget_key(DATA_MENU_KEY, DATA_MENU_GENERATION_KEY, bare_zero=False),
        width=grid_component.TOOLS_MENU_WIDTH_PX,
    ):
        st.button(
            IMPORT_MENU_LABEL,
            key=IMPORT_MENU_BUTTON_KEY,
            icon=":material/upload_file:",
            on_click=_on_import_menu,
        )
        for label, payload, filename, key in (
            (
                "설비 마스터 양식",
                equipment_csv_template(),
                "equipment_master_template.csv",
                "equipment_master_template_download_v3",
            ),
            (
                "기존 보유대수 양식",
                baseline_csv_template(),
                "equipment_baseline_template.csv",
                "equipment_baseline_template_download_v3",
            ),
            (
                "비가동 일정 양식",
                downtime_csv_template(),
                "equipment_downtime_template.csv",
                "equipment_downtime_template_download_v3",
            ),
        ):
            render_csv_download(data=payload, file_name=filename, key=key, label=label)
        _render_current_data_downloads(
            st.session_state[BUFFER_KEY],
            saved=_saved_frames(),
            latest_snapshot=latest_snapshot,
            database_path=str(repository.database_path),
            scenario_name=scenario_name,
            edit_note=DOWNLOAD_NOTE,
            memo_key=(
                equipment_buffer_generation(),
                buffer_base(),
                st.session_state.get(DRAFT_REVISION_KEY),
                latest_snapshot.revision.revision_id if latest_snapshot is not None else None,
            ),
        )


def _render_grid_section(
    view: GridView,
    context: GridContext,
    layout: LayoutMode,
    *,
    repository: DuckDBEquipmentRepository,
    latest_snapshot: EquipmentSnapshot | None,
    acks: Mapping[str, Mapping[str, Any]],
) -> None:
    loaded = prune_loaded(grid_loaded_ids(), view.index)
    missing = st.session_state.get(MISSING_KEY)
    alert_ids = [row_id for row_id in view.index.live if row_id in view.alerts]
    grid_component.render_grid_loader(
        loader_data(
            view,
            loaded,
            missing=tuple(missing) if isinstance(missing, tuple) else (),
            alert_ids=alert_ids,
            first_data=latest_snapshot is None and not view.index.live,
            new_enabled=True,
            dialog_closed=import_closed_count(),
            dialog_from_menu=import_opened_from_menu(),
            menu_key=grid_component.TOOLS_KEY,
        ),
        on_load=_on_load,
        on_clear=_on_clear,
        on_dialog=_on_dialog,
        on_new=_on_new,
    )
    # 메뉴는 불러오기 마운트 다음 차례다 — 서식(`tools_menu_style`)이 불러오기 줄 끝에 얹어도 키보드
    # 차례는 불러오기 줄 → 값 줄(「목록 비우기」 · 「전체 N대 불러오기」) 다음이 메뉴다.
    with st.container(key=grid_component.TOOLS_KEY, horizontal=True, horizontal_alignment="right"):
        _render_data_menu(repository, latest_snapshot, context.scenario_name)
    grid_component.render_grid_table(
        grid_data(
            view,
            loaded,
            ack=acks.get("grid"),
            open_id=_detail_id(),
        ),
        on_outbox=partial(_on_outbox, context, layout),
        on_open=_on_grid_open,
        on_unload=_on_unload,
    )


def save_target(basis: EquipmentSaveBasis | None) -> str:
    """저장 안내가 가리키는 설비 시나리오 — 막은 「이름」, 출발점이 없으면 「이 설비 시나리오」."""
    return quoted(basis.scenario_name) if basis is not None else "「이 설비 시나리오」"


def save_button_help(basis: EquipmentSaveBasis | None, layout: LayoutMode) -> str:
    """「리비전 저장」 풍선 — 무엇이 어디로 저장되나 한 줄(저장이 늘 하는 일은 Guide, 일어난 일은
    결과 알림 — 그림 검수표 equip-13)."""
    scenario = save_target(basis)
    place = f"공통 칸은 모든 설비 시나리오에, 시나리오 칸은 {scenario} 에 새 리비전으로 저장됩니다"
    if layout == "overlay":
        place += f" — 배치 칸은 {scenario} 에만(공식과 다른 것만)"
    return f"{place}."


def _render_save_section(
    repository: DuckDBEquipmentRepository,
    *,
    basis: EquipmentSaveBasis | None,
    session: EquipmentSession,
    context: GridContext,
    layout: LayoutMode,
    floor_canvases: FloorCanvasMap,
    today: date,
) -> None:
    """「저장 전 변경」 아래 저장 구획(개편 명세 4-6 다)."""
    frames: Frames = st.session_state[BUFFER_KEY]
    if st.session_state.pop(_NOTE_CLEAR_KEY, False):
        st.session_state[_NOTE_KEY] = ""
    # 변경 메모 · 저장자는 이름 줄 없이 칸 안 안내 글이 이름을 말한다(2026-11-09 상단 띠 재고 ·
    # 사용자 지시 — 설계 규칙 UI-CON-03).
    st.text_input(
        "변경 메모", key=_NOTE_KEY, placeholder=NOTE_PLACEHOLDER, label_visibility="collapsed"
    )
    render_saved_by_field(SAVE_FIELDS_PREFIX, persist=True)
    # 수 칸 · 「저장하기 전에 고칠 것」 줄이 고친 것 없음 · 오류 수를 이미 말하고 저장 뒤의 거부는
    # 단추 아래에 선다 — 이 칸은 다른 자리에 없는 옛 배포 흔적만(늘 서 있는 칸이라 아래 단추 줄의
    # 자리가 밀리지 않는다, 설계 규칙 UI-TXT-07).
    with st.container():
        if session.legacy_trace_count:
            st.caption(legacy_trace_message(session.legacy_trace_count))
    has_fab = pending_fab_layout() is not None
    floor_pending = bool(
        pending_floor_canvases() or pending_floor_marks() or pending_floor_group_labels()
    )
    with st.container(horizontal=True, gap="small"):
        # 「리비전 저장」 처럼 잠그지 않는다 — 출납은 300ms 묶음이라 이 회차의 단계 수는
        # 브라우저보다 늦고, 콜백이 출납을 먼저 반영한 뒤 판정해 없으면 알림창이 알린다(설계 규칙
        # UI-INP-07 의 제출 단추).
        st.button(
            UNDO_LABEL,
            key=UNDO_BUTTON_KEY,
            icon=":material/undo:",
            help=UNDO_HELP,
            on_click=_undo_step,
            args=(context, layout, current_generation(UNDO_PRESS_KEY)),
        )
        discard_popover(
            label=DISCARD_LABEL,
            popover_key=DISCARD_POPOVER_KEY,
            confirm_key=DISCARD_CONFIRM_KEY,
            note=(
                "편집본을 저장본으로 다시 세웁니다 — 되돌릴 수 없습니다."
                + (" Space 층 배치 대기분도 함께 버립니다." if floor_pending else "")
                + (" S.PKG FAB 전체 배치 대기분은 남깁니다." if has_fab else "")
            ),
            on_confirm=_discard_all,
        )
        st.button(
            SAVE_LABEL,
            key=SAVE_BUTTON_KEY,
            type="primary",
            icon=":material/save:",
            help=save_button_help(basis, layout),
            on_click=_save_revision,
            args=(repository,),
            kwargs={
                "basis": basis,
                "context": context,
                "layout": layout,
                "floor_canvases": floor_canvases,
                "today": today,
                "drawn_base": context.base,
            },
        )
    slot = render_flash(SAVE_RESULT_CARRIED_KEY, SAVE_RESULT_KEY)
    # 낡은 세션의 낡기 전 편집(버려질 칸·지운 호기)이 저장을 막으면 그 거절 곁에서 최신으로 옮긴다 —
    # 버려질 칸은 「저장하기 전에 고칠 것」 줄이 적는다.
    if stale_save_refusal(frames, basis) is not None:
        with slot:
            render_load_latest_button(
                str(repository.database_path), session, key=LOAD_LATEST_BUTTON_KEY
            )


def _render_new_unit(
    view: GridView,
    context: GridContext,
    layout_mode: SpaceEditMode,
    *,
    ack: Mapping[str, Any] | None,
    toast: Mapping[str, Any] | None,
    reveal_head: bool,
) -> None:
    """오른쪽 「새 호기」 칸(개편 명세 4-6 나) — 세션 초안을 이 회차 편집본 위에서 보고(체크 상자·칸
    오류·잠금) 그린다. 가정 설비 시나리오면 새 호기 자리 안내를 싣는다."""
    seq, values = _new_draft()
    check = new_unit_check(
        values,
        frames=st.session_state[BUFFER_KEY],
        saved_master=_saved_frames()[1],
        renames=pending_unit_renames(),
        context=context,
    )
    notes: list[str | tuple[str, str]] = []
    if layout_mode.layout == "overlay":
        notes.append((NEW_UNIT_OVERLAY_MARK, NEW_UNIT_OVERLAY_NOTE))
    elif layout_mode.layout == "locked" and context.layout_lock:
        notes.append(f"{NEW_UNIT_LOCKED_NOTE} — {context.layout_lock}")
    grid_component.render_grid_side(
        "new",
        new_unit_data(
            view,
            check,
            seq=seq,
            ack=ack,
            toast=toast,
            reveal_head=reveal_head,
            notes=notes,
        ),
        on_outbox=partial(_on_outbox, context, layout_mode.layout),
        on_open=_on_side_open,
        on_goto=_on_goto,
        on_draft=_on_draft,
        on_copy=_on_copy,
        columns=len(EQUIPMENT_COLUMNS),
    )


def render_equipment_master_tab(
    *,
    repository: DuckDBEquipmentRepository,
    session: EquipmentSession,
    latest_snapshot: EquipmentSnapshot | None,
    floor_canvases: FloorCanvasMap,
    layout_mode: SpaceEditMode,
    today: date,
    confirmation_official: EquipmentSnapshot | None = None,
    drafts_replaced: bool = False,
) -> None:
    """탭 ① 본문. 페이지가 `ensure_equipment_drafts` 를 부른 뒤, 탭이 열린 회차에만 부른다."""
    # 남의 저장에 진 「리비전 저장」 거부는 머리를 다시 그리려 다시 도는 회차가 그린다(페이지 끝).
    carry_until_head_rerun(SAVE_RESULT_KEY, into=SAVE_RESULT_CARRIED_KEY)
    basis = session.save_basis()
    layout: LayoutMode = layout_mode.layout
    settle_bulk_restore()
    frames: Frames = st.session_state[BUFFER_KEY]
    floor_states: FloorStates | None
    try:
        floor_states = load_floor_states(str(repository.database_path))
    except BOOTSTRAP_ERRORS:
        floor_states = None
    context = grid_context(
        session,
        basis,
        layout_mode,
        latest_snapshot=latest_snapshot,
        floor_states=floor_states,
        master=frames[1],
        official_snapshot=confirmation_official,
        floor_canvases=floor_canvases,
        today=today,
    )
    if st.session_state.pop(OUTBOX_HELD_KEY, False):
        apply_outbox(context, layout)
    settle_grid_undo(partial(_grid_undo, context, layout))
    view = build_view(
        context,
        floor_canvases=floor_canvases,
        today=today,
        confirmation_official=confirmation_official,
        layout=layout,
    )
    counts = change_counts(view)
    pending = counts.total + (1 if view.source.others else 0)
    table = _render_head(session, basis, layout, pending)
    _render_notices(session, basis, layout_mode, floor_states, latest_snapshot)
    acks = _acks(_applied())
    toasts = grid_toasts()
    reveal_head = bool(st.session_state.pop(SIDE_HEAD_KEY, False))
    submit = None
    # 테두리 하나의 편집기 영역 안 두 칸 — 왼쪽 표, 오른쪽 칸(칸막이로 폭을 바꾸고 칸 머리 단추로
    # 접는다). 간격은 서식이 경계선 양쪽 여백으로 둔다. 배치 서식은 늘 같은 글 한 덩이다.
    left, right = split_frame(grid_component.MASTER_SIDE)
    st.html(grid_component.tools_menu_style())
    with left:
        if table == TABLE_MASTER:
            _render_grid_section(
                view,
                context,
                layout,
                repository=repository,
                latest_snapshot=latest_snapshot,
                acks=acks,
            )
        else:
            stale = (basis is not None and basis.stale) or session.unmerged
            submit = render_small_editor(
                table,
                stale=stale,
                delete_locked=context.delete_lock,
                drafts_replaced=drafts_replaced,
                undo=partial(_grid_undo, context, layout),
                # 삭제를 확정하면 「한 단계 되돌리기」 가 있는 「저장 전 변경」 칸을 연다 — 오른쪽
                # 칸이 접혀 있으면 펴고(c6).
                on_deleted=partial(_switch_side, SIDE_CHANGES),
            )
    with right:
        # 칸막이(칸 머리 접기 단추 포함)는 오른쪽 칸 맨 앞에 늘 선다(절대 위치 — 흐름 높이 0). 그
        # 뒤 고르기, 그 뒤 본문 칸.
        side, body = render_side_head(grid_component.MASTER_SIDE, SIDES, SIDE_DETAIL)
    with body:
        if side == SIDE_HISTORY:
            try:
                _render_history(
                    repository,
                    scenario_id=_history_scenario(repository, basis, latest_snapshot),
                    scenario_name=basis.scenario_name if basis is not None else None,
                )
            except BOOTSTRAP_ERRORS as exc:
                render_data_error(
                    "저장 이력을 읽지 못했습니다: "
                    + bootstrap_error_message(exc, database_paths=(repository.database_path,)),
                    code="EQ-09",
                    text="설비 저장 이력을 읽지 못했습니다",
                )
        elif side == SIDE_CHANGES:
            grid_component.render_grid_side(
                "changes",
                changes_data(view, ack=acks.get("changes")),
                on_outbox=partial(_on_outbox, context, layout),
                on_open=_on_side_open,
                on_goto=_on_goto,
            )
            _render_save_section(
                repository,
                basis=basis,
                session=session,
                context=context,
                layout=layout,
                floor_canvases=floor_canvases,
                today=today,
            )
        elif side == SIDE_NEW:
            _render_new_unit(
                view,
                context,
                layout_mode,
                ack=acks.get("new"),
                toast=toasts.get("new"),
                reveal_head=reveal_head,
            )
        else:
            grid_component.render_grid_side(
                "detail",
                detail_data(
                    view,
                    _detail_id(),
                    ack=acks.get("detail"),
                    toast=toasts.get("detail"),
                    reveal_head=reveal_head,
                ),
                on_outbox=partial(_on_outbox, context, layout),
                on_open=_on_side_open,
                on_goto=_on_goto,
                on_copy=_on_copy,
            )
    # 그린 마운트의 자리 거부는 실어 보냈다고 적고, 사라진 마운트의 실어 보낸 것은 거둔다(닫은 한
    # 줄이 다시 마운트할 때 되살아나지 않게).
    settle_grid_toasts({"detail"} if side == SIDE_DETAIL else {"new"} if side == SIDE_NEW else ())
    # 불러오기 · 표 조작 결과는 알림창으로만 가 그릴 것이 없다 — 탭 맨 끝에 둔다. 표 위 알림 칸에
    # 두면 그 칸이 늘 서서 편집기 영역이 틈 하나만큼 내려간다.
    render_flash(LOAD_RESULT_KEY, GRID_RESULT_KEY)
    # 작은 편집표 제출은 화면의 모든 위젯을 그린 뒤 처리한다(`st.rerun()` 으로 끝난다).
    if submit is not None:
        submit()
