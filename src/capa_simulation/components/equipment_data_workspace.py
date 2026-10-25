# Purpose: 설비 마스터 탭의 편집본 경계·작은 편집표·저장 이력·세 표 리비전 저장을 둔다.

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import pandas as pd
import streamlit as st

from capa_simulation.components.editor_state import (
    discard_editor,
    editor_has_edits,
    editor_widget_key,
)
from capa_simulation.components.equipment_save_fields import (
    EquipmentSaveBasis,
    EquipmentSaveFields,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.components.table_view_controls import (
    TableView,
    filter_widget_key,
    merge_edited_rows,
    render_table_view_controls,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    date_range_value,
    prune_choice,
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_snapshot_cache,
    clear_floor_layout_cache,
    latest_equipment_revision_id,
    load_equipment_csv_payloads,
    load_equipment_revision_summaries,
    load_equipment_scenario_catalog,
    load_equipment_schedule_revisions,
    load_merged_equipment_snapshot,
    load_units_scheduled_elsewhere,
)
from capa_simulation.persistence.equipment_repository import (
    EMPTY_REVISION_TOKEN,
    DuckDBEquipmentRepository,
    EquipmentSaveRequest,
    EquipmentSaveResult,
    EquipmentScheduleRevisionSummary,
    EquipmentSnapshot,
    FloorLayoutBase,
    PropagatedRevision,
)
from capa_simulation.services.equipment_bulk_delete import (
    BASELINE_TARGET,
    DOWNTIME_TARGET,
    TARGET_LAYOUT,
    DeletionPlan,
    RowKey,
    apply_deletion,
    checked_keys,
    matching_keys,
    plan_deletion,
    restore_rows,
    row_keys,
)
from capa_simulation.services.equipment_contract import (
    COMMON_MASTER_COLUMNS,
    DOWNTIME_TYPES,
    EQUIPMENT_ID_COLUMN,
    SCENARIO_LAYOUT_COLUMNS,
    SCENARIO_SCHEDULE_COLUMNS,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.equipment_csv import (
    EquipmentPaste,
    baseline_csv_bytes,
    build_baseline_import_preview,
    build_downtime_import_preview,
    build_equipment_import_preview,
    describe_case_variants,
    downtime_csv_bytes,
    equipment_csv_bytes,
    merge_baseline_rows,
    merge_downtime_rows,
    merge_equipment_rows,
    read_baseline_clipboard,
    read_baseline_csv,
    read_downtime_clipboard,
    read_downtime_csv,
    read_equipment_update,
    untouched_template_baseline_rows,
)
from capa_simulation.services.equipment_grid import (
    GridApplied,
    after_row_steps,
    grid_index,
    prune_overlay,
    undo_from_state,
    undo_to_state,
)
from capa_simulation.services.equipment_samples import untouched_sample_baseline_rows
from capa_simulation.services.equipment_scenario import (
    calculation_frames,
    inherited_unit_names,
    legacy_unit_key,
)
from capa_simulation.services.equipment_validation import (
    UnitGroupCollisionError,
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
    unit_group_collision_message,
)
from capa_simulation.services.fab_layout import FabLayoutBase, FabLayoutMark
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.floor_layout_profile import CanvasSize, FloorCanvasMap, FloorKey
from capa_simulation.services.korean_particle import (
    object_particle,
    with_direction_particle,
)
from capa_simulation.services.layout_overlay import (
    Place,
    ReappliedLayout,
    assumption_common_places,
    assumption_group_refusal,
    misplaced_rows,
    place_of,
    place_rows,
    reapply_layout_edits,
)
from capa_simulation.services.space_layout_edit import (
    ModuleLayout,
    PendingRenames,
    module_layout_message,
    module_layout_violations,
    natural_name_key,
    reserved_names,
    restore_saved_layout,
    saved_layout_drift,
)

FLASH_KEY = "equipment_status_flash"
# 설비 마스터 탭 표 고르기의 작은 편집표 둘(기존 보유대수·비가동 일정 — `render_small_editor`).
BASELINE_EDITOR_KEY = "equipment_baseline_editor_v3"
DOWNTIME_EDITOR_KEY = "equipment_downtime_editor_v3"
# 설비 마스터 표(가용설비 현황 탭 ① — `components/equipment_master_tab.py`, 개편 B1)의 세션 칸
# 가운데 편집본과 함께 사는 것. 편집본을 다시 세우면(`ensure_equipment_drafts`)·저장하거나 모두
# 버리면(`reset_equipment_drafts`) 함께 비운다 — 옛 편집본의 칸 초안·되돌리기가 새 편집본에 남지
# 않게.
# 칸 초안 = {"<행 id>\t<칸>": 못 읽은 글}(편집본 밖 — 저장을 막는다, `save_equipment_buffer`).
GRID_OVERLAY_KEY = "equipment_grid_overlay_v1"
# 되돌리기 단계(`services/equipment_grid.undo_to_state` 의 기본형 — 최대 40, 통째 단계는 하나).
GRID_UNDO_KEY = "equipment_grid_undo_v1"
# 마운트별 토스트 {"grid"|"detail"|"changes": {"id", "text", "undo"}}. 번호는 `GRID_TOAST_SEQ_KEY`
# 하나로 늘 오른다(비우지 않는다 — 같은 번호를 다시 쓰면 닫은 토스트로 보고 숨긴다).
GRID_TOAST_KEY = "equipment_grid_toast_v1"
GRID_TOAST_SEQ_KEY = "equipment_grid_toast_seq_v1"
# 마운트에 실어 보낸 토스트 번호 {마운트: 번호} — 그 마운트가 사라지면 그 토스트를 거둔다
# (`settle_grid_toasts`).
GRID_TOAST_SHOWN_KEY = "equipment_grid_toast_shown_v1"
# 회차 메모(칸 결과·표 단위 오류 — 열쇠가 바뀌면 덮는다).
GRID_MEMO_KEY = "equipment_grid_memo_v1"
# 표에 불러온 목록(행 id 차례)·상세에 연 행 id — 편집본을 다시 세워도·저장해도 남는다(저장 뒤에는
# 이름 바꾼 호기를 새 id 로 옮긴다, 개편 명세 7-3). 편집본에 없는 id 는 회차마다 거른다.
GRID_LOADED_KEY = "equipment_grid_loaded_v1"
GRID_DETAIL_KEY = "equipment_grid_detail_v1"
# 오른쪽 「새 호기」 칸(개편 단계 C)에서 넣은 호기마다 고른 「다른 설비 시나리오에도 같은
# 일정으로 넣기」 {지금 이름 → bool}(개편 명세 13장 D8). 저장이 이것으로
# `EquipmentSaveRequest.propagate_units` 를 만든다 — 그 칸에서 넣지 않은 새 호기(표 붙여넣기·
# 엑셀·CSV·Space)는 저장 칸 체크를 따른다. 새 호기 이름을 바꾸면 따라간다(`follow_unit_renames`).
# 편집본과 함께 산다.
NEW_UNIT_PROPAGATE_KEY = "equipment_new_unit_propagate_v1"
# 「새 호기」 칸의 초안 {"seq": 번호, "values": 39칸 글, "propagate": bool} — 저장해도 남고(다음
# 호기를 이어 넣는다) 「호기 추가」 뒤에는 공정소분류·동·층만 남긴다. 편집본과 따로 산다.
NEW_UNIT_DRAFT_KEY = "equipment_new_unit_draft_v1"
_GRID_SESSION_KEYS = (
    GRID_OVERLAY_KEY,
    GRID_UNDO_KEY,
    GRID_TOAST_KEY,
    GRID_TOAST_SHOWN_KEY,
    GRID_MEMO_KEY,
    NEW_UNIT_PROPAGATE_KEY,
)
BASELINE_DRAFT_KEY = "equipment_baseline_draft_v3"
EQUIPMENT_DRAFT_KEY = "equipment_master_draft_v3"
DOWNTIME_DRAFT_KEY = "equipment_downtime_draft_v3"
DRAFT_REVISION_KEY = "equipment_draft_revision_v4"
# 저장본 사본(draft)이 나온 설비 시나리오 일정 리비전에 일정 행이 없는 설비명(F4). 계산 화면은 이
# 호기와 그 비가동을 뺀 사본을 읽는다(`calculation_drafts`). 편집·설비 마스터 탭·CSV 는 39칸
# 전체다.
DRAFT_UNSCHEDULED_KEY = "equipment_draft_unscheduled_v1"
# 저장본 사본의 (설비명, 호기 키) 쌍 — 지우는 호기가 다른 설비 시나리오에 일정이 있는지 키로 본다.
DRAFT_UNIT_KEYS_KEY = "equipment_draft_unit_keys_v1"
# 편집본(buffer)이 나온 출발점 — {"common": 공통 id 또는 EMPTY_REVISION_TOKEN, "schedule": 일정 id
# 또는 None, "scenario": 시나리오 id 또는 None, "common_no", "schedule_no"}. 기본형만 담는다.
# 저장 요청의 두 대조 값이 여기서 나온다.
_BASE_KEY = "equipment_workspace_base_v1"
# 이 세션의 저장이 설비 시나리오 일정 리비전을 새로 만들었다는 표지 —
# {"scenario_id", "schedule_revision_id"}.
# 다음 회차의 `equipment_scenario_activation.resolve_equipment_session` 이 읽어 세션 선택을 그
# 리비전으로 옮긴다(공통만 쓴 저장은 선택이 그대로다).
SAVED_SCHEDULE_KEY = "equipment_workspace_saved_schedule_v1"
BASELINE_IMPORT_KEY = "baseline_import_preview_rows_v3"
EQUIPMENT_IMPORT_KEY = "equipment_import_preview_rows_v3"
DOWNTIME_IMPORT_KEY = "downtime_import_preview_rows_v3"
TARGET_KEY = "equipment_import_target_v1"
CLIPBOARD_KEY = "equipment_import_clipboard_v1"
UPLOAD_KEY = "equipment_import_upload_v1"
PREVIEW_BUTTON_KEY = "equipment_import_preview_v1"
PREVIEW_KEY = "equipment_workspace_preview_v1"
# 미리보기를 마지막으로 그린 페이지 방문 차례(`page_bootstrap.page_visit`).
_PREVIEW_VISIT_KEY = "equipment_workspace_preview_visit_v1"
BUFFER_KEY = "equipment_workspace_buffers_v1"
DROP_EXAMPLE_ROWS_KEY = "equipment_workspace_drop_examples_v1"
EXAMPLE_DROP_BUTTON_KEY = "equipment_workspace_drop_examples_button_v1"
_REVISION_KEY = "equipment_workspace_revision_v1"
_ERROR_KEY = "equipment_workspace_error_v1"
_NOTICE_KEY = "equipment_workspace_notice_v1"
_NOTE_KEY = "equipment_workspace_note_v1"
# 「저장 전 변경」 의 변경 메모 칸을 다음 회차에 비우라는 표지. 칸을 지우기만 하면 브라우저가 옛
# 값을 다음 회차에 다시 보낸다(2026-10-05 E2E — r4 의 메모가 r5 에 그대로 실렸다). 다음 회차 칸
# 앞에서 빈 값을 적는다(설비 마스터 탭 저장 구획).
_NOTE_CLEAR_KEY = "equipment_workspace_note_clear_v1"
# CSV 업로드 칸의 key 세대. 업로드는 세션으로 값을 적을 수 없어 저장 뒤 비울 때 세대를 올려
# 새 칸으로 세운다(`_upload_widget_key`).
_UPLOAD_GENERATION_KEY = "equipment_import_upload_generation_v1"
# 작은 편집표의 일괄 삭제. 선택은 행 번호가 아니라 업무 키로 기억한다
# (`services/equipment_bulk_delete`).
SELECT_COLUMN = "선택"
SELECTION_KEY = "equipment_workspace_selection_v1"
PENDING_DELETE_KEY = "equipment_workspace_pending_delete_v1"
LAST_REMOVED_KEY = "equipment_workspace_last_removed_v1"
CONFIRM_DELETE_BUTTON_KEY = "equipment_delete_confirm_v1"
# Space 편집기가 쌓는 미저장 층 캔버스·도면 요소((동, 층) → 값). 호기 편집본(BUFFER_KEY)과
# **함께 저장되고 함께 버려진다** — 어느 저장 단추를 눌러도 같은 저장 helper 를 탄다.
PENDING_CANVASES_KEY = "equipment_pending_floor_canvases_v1"
PENDING_MARKS_KEY = "equipment_pending_floor_marks_v1"
# 층마다 Main 설비 모듈 묶음 이름표 위치((동, 층) → {Main 설비: 위치}, 그 층 전체 — 처음 위치인
# 묶음은 빠짐).
PENDING_GROUP_LABELS_KEY = "equipment_pending_floor_group_labels_v1"
# 층마다 편집을 시작할 때 본 저장값(캔버스·요소와 위치의 지문). 저장이 이것과 지금 저장값을 견줘, 그
# 사이 다른 사람이 바꾼 층을 옛 목록으로 덮지 않는다(요소·위치는 층 전체 교체다).
PENDING_BASES_KEY = "equipment_pending_floor_bases_v1"
# Space FAB 편집기가 쌓는 미저장 FAB 전체 배치(캔버스·요소와 편집을 시작할 때 본 저장값). FAB 는
# 설비 리비전과 무관한 현행값이라 **설비 저장본이 없어도** 쌓고 저장한다. 같은 저장 단추가 쓰고
# 같은 `모두 버리기` 가 버린다. 남이 새 리비전을 저장해도 버리지 않는다 — 리비전과 상관없고, 남이
# FAB 를 먼저 바꿨는지는 저장 때 본 저장값으로 따로 견준다.
PENDING_FAB_KEY = "equipment_pending_fab_layout_v1"
# Space 편집기에서 바꾼 저장 안 한 이름(지금 이름 → 저장본 이름, 설비명·Main 설비). 편집본과
# 함께 버려진다. 호기는 설비명으로만 짝지어지므로 이것이 없으면 이름을 바꾼 호기가 「지운 호기 +
# 새 호기」로 읽힌다(`services/space_layout_edit.PendingRenames`).
PENDING_RENAMES_KEY = "equipment_pending_unit_renames_v1"
# 이름 바꿈을 따라갈 비가동 일정 작은 편집표 목록 필터(칸 이름 → {옛 값: 새 값}). 이름은 그 필터가
# 그려지기 **전**에만 고칠 수 있어(위젯 key) 여기 모았다가 `render_small_editor` 가 필터를 그리기
# 전에 얹는다.
FOLLOWED_FILTERS_KEY = "equipment_workspace_followed_filters_v1"
# 비가동 일정 작은 편집표 보기 설정의 key 접두어(`render_table_view_controls`).
DOWNTIME_VIEW_PREFIX = "equipment_downtime_view"
# 「이름 바꿈」 목록 펼침(설비 마스터 탭 알림 칸).
NAME_CHANGES_EXPANDER_KEY = "equipment_workspace_name_changes_v1"
# 이름 바꿈 목록 아래 한 줄 — Space 편집기 상자와 설비 마스터 탭이 같이 쓴다(G4·R2 — 이름
# 바꾸기는 같은 호기다).
NAME_CHANGES_CAPTION = (
    "이름 바꾸기는 같은 호기입니다 — 저장하면 새 리비전부터 새 이름이고, 모든 설비 시나리오의 "
    "일정·비가동이 새 이름을 따라갑니다. 지난 리비전과 필요 단축 일정 진척 비교 기준선은 옛 이름 "
    "그대로이고, 설비 마스터를 바깥 Excel 에서 붙여넣어 관리하면 그 Excel 의 이름도 바꿔야 합니다."
)
# Space 배치 편집기가 적용한 모듈 묶음의 적용 뒤 모양(Main 설비 → `ModuleLayout`). 저장 검사
# (`module_layout_violations`)가 이 모양 그대로인 묶음을 편집기 결과로 보고 통과시킨다 — 그 뒤에
# 붙여넣기 등으로 그 묶음 좌표·크기를 고치면 모양이 달라져 다시 검사받는다. 편집본과 함께
# 버려진다.
EDITOR_MODULE_LAYOUTS_KEY = "equipment_editor_module_layouts_v1"
# 이 편집본에 쌓인 배치 편집을 적용할 때의 역할("official"·"overlay" — 설계 6-2). 배치를 바꾸는
# 적용마다(Space 편집기 적용·설비 마스터 탭 배치 칸·붙여넣기 배치 칸) 찍고, 편집본을 다시 세우거나
# 배치 변경을 버리거나 저장하면 지운다. 편집본을 세울 때는 찍지 않는다 — 남의 발행은 토큰을 바꾸지
# 않아, 세울 때 찍으면 역할이 바뀐 **뒤**의 정상 편집까지 옛 역할로 막힌다(검토 M3).
LAYOUT_ROLE_KEY = "equipment_layout_role_v1"
# 편집본 배치 편집 판정 메모 — (열쇠, 있음). `buffer_has_layout_edits`.
LAYOUT_EDITS_MEMO_KEY = "equipment_layout_edits_memo_v1"
# 다른 사람이 새 리비전을 저장해 이 세션의 저장 안 한 편집을 버렸을 때 한 번 띄우는 알림.
DISCARDED_NOTICE_KEY = "equipment_workspace_discarded_v1"
# 이번 회차 맨 위에서 편집본을 새 저장본으로 갈아 끼웠다는 표시. 그 회차의 작은 편집표 제출은 옛
# 편집본 위의 것이라 반영하지 않는다 — 페이지가 `pop_drafts_replaced` 로 한 번 읽는다(표 출납은
# `base` 대조로 같은 규칙).
DRAFTS_REPLACED_KEY = "equipment_workspace_drafts_replaced_v1"
# 편집본을 저장본에서 새로 세운 직후의 세대. 지금 세대가 이보다 크면 저장 안 한 편집이 있다.
_SEEDED_GENERATION_KEY = "equipment_workspace_seeded_generation_v1"
# 편집본을 바꿀 때마다 오르는 세대. Space 편집기 epoch 에 넣어 설비 마스터 탭 편집을 놓치지 않게
# 한다.
BUFFER_GENERATION_KEY = "equipment_workspace_buffer_generation_v1"
CANCEL_DELETE_BUTTON_KEY = "equipment_delete_cancel_v1"
UNDO_DELETE_BUTTON_KEY = "equipment_delete_undo_v1"
SELECT_MATCHING = "select_matching"
SELECT_CLEAR = "select_clear"
DELETE_SELECTED = "delete_selected"
# 저장 이력 「조회 조건」 펼침의 key — 위젯이 아니라 브라우저가 펼침을 기억하는 이름이다.
HISTORY_FILTER_EXPANDER_KEY = "equipment_history_filters_v1"
_EDITOR_KEYS = (BASELINE_EDITOR_KEY, DOWNTIME_EDITOR_KEY)
# 「엑셀·CSV로 한꺼번에」 등록할 표·내려받기 단추 차례.
_TARGETS = ("설비 마스터", "기존 보유대수", "비가동 일정")
Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]


@dataclass(frozen=True)
class ImportReview:
    """「엑셀·CSV로 한꺼번에」 미리보기가 쓴 원문·출발 편집본과 넣을 후보 세 표를 묶는다 — 넣기
    직전에 입력·표·편집본이 그대로인지(`matches`) 다시 본다."""

    target: str
    payload: str | bytes
    source: Frames
    candidate: Frames
    changes: pd.DataFrame
    # 원문을 읽으며 남긴 알림(빠진 옛 컬럼 `투자기준`·`설비가동현황` 을 떼어 냄, 붙여넣은 열만
    # 바꾼다 등). 미리보기와 함께 남는다.
    notices: tuple[str, ...] = ()
    # 저장하면 값이 지워지는 칸처럼 저장 전에 눈에 띄어야 하는 것. 경고로 그린다.
    cautions: tuple[str, ...] = ()
    # 「배치 칸도 붙여넣기」 를 켜고 만든 후보인가(가정 세션 — 설비 시나리오 2단계 S3). 미리본 뒤 그
    # 체크를 바꾸면 후보를 다시 만든다.
    layout_pasted: bool = True

    def matches(
        self,
        target: str,
        payload: str | bytes,
        source: Frames,
        *,
        layout_pasted: bool = True,
    ) -> bool:
        return (
            self.target == target
            and self.payload == payload
            and self.layout_pasted == layout_pasted
            and all(left.equals(right) for left, right in zip(self.source, source, strict=True))
        )


def _clear_editors() -> None:
    # 세션 칸만 지우면 브라우저가 옛 편집을 다시 보낸다. 위젯 키를 바꿔 새 편집표로 세운다
    # (`components/editor_state.py`).
    for key in _EDITOR_KEYS:
        discard_editor(key)
        st.session_state.pop(f"{key}_applied_view", None)


def reset_equipment_drafts(*, keep_fab: bool = False) -> None:
    """새 저장본으로 돌아갈 때 페이지 draft와 설비 마스터 탭의 입력·편집표 delta를 함께 비운다.

    `keep_fab` 이면 미저장 FAB 전체 배치는 남긴다 — 설비 시나리오와 무관한 현행값이라 시나리오를
    바꿔 불러와도 버릴 까닭이 없다.
    """
    _clear_editors()
    for key in (
        BASELINE_DRAFT_KEY,
        EQUIPMENT_DRAFT_KEY,
        DOWNTIME_DRAFT_KEY,
        DRAFT_REVISION_KEY,
        DRAFT_UNSCHEDULED_KEY,
        DRAFT_UNIT_KEYS_KEY,
        _BASE_KEY,
        BASELINE_IMPORT_KEY,
        EQUIPMENT_IMPORT_KEY,
        DOWNTIME_IMPORT_KEY,
        BUFFER_KEY,
        PREVIEW_KEY,
        DROP_EXAMPLE_ROWS_KEY,
        _REVISION_KEY,
        _ERROR_KEY,
        _NOTICE_KEY,
        _NOTE_KEY,
        SELECTION_KEY,
        PENDING_DELETE_KEY,
        LAST_REMOVED_KEY,
        PENDING_CANVASES_KEY,
        PENDING_MARKS_KEY,
        PENDING_GROUP_LABELS_KEY,
        PENDING_BASES_KEY,
        *(() if keep_fab else (PENDING_FAB_KEY,)),
        PENDING_RENAMES_KEY,
        FOLLOWED_FILTERS_KEY,
        EDITOR_MODULE_LAYOUTS_KEY,
        LAYOUT_ROLE_KEY,
        LAYOUT_EDITS_MEMO_KEY,
        _SEEDED_GENERATION_KEY,
        *_GRID_SESSION_KEYS,
    ):
        st.session_state.pop(key, None)
    # 입력 칸(메모·업로드)은 지우기만 하면 브라우저가 옛 값을 다시 보낸다. 메모는 표지로 다음 회차
    # 칸 앞에서 빈 값을 적고, 업로드는 key 세대를 올린다.
    st.session_state[_NOTE_CLEAR_KEY] = True
    st.session_state[_UPLOAD_GENERATION_KEY] = _upload_generation() + 1


def _upload_generation() -> int:
    generation = st.session_state.get(_UPLOAD_GENERATION_KEY, 0)
    return generation if isinstance(generation, int) else 0


def _upload_widget_key() -> str:
    """CSV 업로드 칸의 지금 key. 첫 세대는 `UPLOAD_KEY` 그대로다."""
    generation = _upload_generation()
    return UPLOAD_KEY if generation == 0 else f"{UPLOAD_KEY}_{generation}"


def _copy_frames(frames: Frames) -> Frames:
    return frames[0].copy(), frames[1].copy(), frames[2].copy()


def _bump_buffer_generation() -> None:
    st.session_state[BUFFER_GENERATION_KEY] = equipment_buffer_generation() + 1


def _store_changed_buffer(frames: Frames) -> None:
    """내용이 바뀐 편집본을 넣고 세대를 올린다. 일괄 삭제 확정·되살리기가 이 길로만 쓴다.

    세대가 「저장하지 않은 편집」의 유일한 근거다(`has_unsaved_equipment_edits`). 편집표 칸은
    그대로이고 행만 빠진 제출에서 세대가 그대로면, 테마 단추가 묻지 않고 새로고침하고 다른 사람의
    저장이 이 삭제를 알림 없이 버린다.
    """
    st.session_state[BUFFER_KEY] = frames
    _bump_buffer_generation()


def equipment_buffer_generation() -> int:
    """편집본 세대. 편집본이 바뀔 때마다(설비 마스터 탭 고침·Space 적용·새 리비전) 오른다."""
    value = st.session_state.get(BUFFER_GENERATION_KEY, 0)
    return int(value) if isinstance(value, int) else 0


def revision_token(latest_snapshot: EquipmentSnapshot | None) -> str:
    """편집본이 어느 저장본에서 나왔는지 가르는 값 — (공통 대장, 설비 시나리오 일정) 쌍 토큰
    (`EquipmentSnapshot.token`). 저장본이 없으면 `EMPTY_REVISION_TOKEN`.

    두 리비전 내용은 불변이라 토큰이 같으면 저장본이 같다. 남이 공통 대장을 저장하면 앞쪽이 바뀌어
    편집본을 다시 세운다. 남이 내 시나리오에 일정을 저장해도 세션은 고른 일정 리비전을 그대로 들고
    있어 토큰이 그대로다 — 그때는 화면이 「낡음」 으로 일정 칸을 잠근다(설계 4-2).
    """
    if latest_snapshot is None:
        return EMPTY_REVISION_TOKEN
    return latest_snapshot.token


def _base_of(latest_snapshot: EquipmentSnapshot | None) -> dict[str, object]:
    """편집본 출발점(`_BASE_KEY`) — 기본형만."""
    if latest_snapshot is None:
        return {
            "common": EMPTY_REVISION_TOKEN,
            "schedule": None,
            "scenario": None,
            "common_no": None,
            "schedule_no": None,
        }
    schedule = latest_snapshot.schedule
    return {
        "common": latest_snapshot.revision.revision_id,
        "schedule": schedule.schedule_revision_id if schedule is not None else None,
        "scenario": schedule.equipment_scenario_id if schedule is not None else None,
        "common_no": latest_snapshot.revision.revision_no,
        "schedule_no": schedule.revision_no if schedule is not None else None,
    }


def _token_parts(token: object) -> tuple[str, str]:
    """쌍 토큰을 (공통, 일정) 으로 가른다. 옛 꼴·빈 저장소 토큰은 일정이 「-」다."""
    text = str(token)
    common, _, schedule = text.partition("|")
    return common, schedule or "-"


def _replaced_by_words(previous: object, latest_snapshot: EquipmentSnapshot | None) -> str:
    """남의 저장으로 편집본을 다시 세운 까닭 — 「공통 대장 r16」 또는 「설비 시나리오 일정 r4」."""
    if latest_snapshot is None:
        return "새 저장"
    before_common, before_schedule = _token_parts(previous)
    after_common, after_schedule = _token_parts(latest_snapshot.token)
    schedule = latest_snapshot.schedule
    if before_common == after_common and before_schedule != after_schedule and schedule:
        return f"설비 시나리오 일정 r{schedule.revision_no}"
    return f"공통 대장 r{latest_snapshot.revision.revision_no}"


def calculation_drafts() -> Frames:
    """계산 화면이 읽는 저장본 사본 — 이 설비 시나리오에 일정이 없는 호기와 그 비가동을 뺀 사본.

    `ensure_equipment_drafts` 뒤에 부른다(사본이 아직 없으면 빈 표). 돌려준 표는 사본의 복사라
    고쳐도 세션 칸이 바뀌지 않는다.
    """
    baseline = st.session_state.get(BASELINE_DRAFT_KEY)
    equipment = st.session_state.get(EQUIPMENT_DRAFT_KEY)
    downtime = st.session_state.get(DOWNTIME_DRAFT_KEY)
    unscheduled = st.session_state.get(DRAFT_UNSCHEDULED_KEY)
    frames = calculation_frames(
        baseline.copy() if isinstance(baseline, pd.DataFrame) else empty_equipment_baseline(),
        equipment.copy() if isinstance(equipment, pd.DataFrame) else empty_equipment_master(),
        downtime.copy() if isinstance(downtime, pd.DataFrame) else empty_downtime_schedule(),
        unscheduled if isinstance(unscheduled, frozenset) else frozenset(),
    )
    return frames


def draft_unscheduled_units() -> frozenset[str]:
    """저장본 사본의 일정 없음 설비명(F4 — 「일정 없음 n대」 알림 재료)."""
    value = st.session_state.get(DRAFT_UNSCHEDULED_KEY)
    return value if isinstance(value, frozenset) else frozenset()


def pop_saved_schedule() -> tuple[str, str] | None:
    """이 세션의 저장이 만든 (시나리오 id, 일정 리비전 id). 한 번 읽으면 지운다."""
    value = st.session_state.pop(SAVED_SCHEDULE_KEY, None)
    if isinstance(value, dict):
        scenario = value.get("scenario_id")
        schedule = value.get("schedule_revision_id")
        if isinstance(scenario, str) and isinstance(schedule, str):
            return scenario, schedule
    return None


def has_unsaved_equipment_edits() -> bool:
    """편집본을 저장본에서 세운 뒤 바뀐 것이 있는가(설비 마스터 탭 고침·Space 호기 적용·미저장 층
    배치).

    Space FAB 전체 배치 대기분은 세대를 올리지 않아 여기 들지 않는다(`pending_fab_layout`)."""
    seeded = st.session_state.get(_SEEDED_GENERATION_KEY)
    return isinstance(seeded, int) and equipment_buffer_generation() > seeded


def pop_drafts_replaced() -> bool:
    """이번 회차에 다른 사람의 저장으로 편집본을 새로 세웠는가. 페이지가 `ensure_equipment_drafts`
    바로 뒤에 한 번 읽는다(안 읽으면 다음 회차의 정상 제출까지 막는다)."""
    return st.session_state.pop(DRAFTS_REPLACED_KEY, False) is True


def pop_discarded_notice() -> str | None:
    """다른 사람의 저장으로 이 세션의 편집이 버려졌다는 알림. 한 번 읽으면 지운다."""
    value = st.session_state.pop(DISCARDED_NOTICE_KEY, None)
    return value if isinstance(value, str) else None


def ensure_equipment_drafts(latest_snapshot: EquipmentSnapshot | None) -> Frames:
    """저장본 사본(draft)과 미저장 편집본(buffer)을 **한 곳에서** 세우고 편집본을 돌려준다.

    가용설비 현황과 Space 현황이 같은 편집본을 쓴다. 어느 쪽을 먼저 열어도 같은 저장본
    토큰으로 세워야, 나중에 연 쪽이 「토큰이 다르다」며 편집본을 저장본으로 덮어쓰지 않는다.
    새 리비전이 생기면(누가 저장하면) 미저장 편집·캔버스·도면 요소는 버리고 다시 세운다 — 단 가정
    역할로 찍힌 배치 편집은 남이 **공통**을 저장했을 때(일정 쪽 그대로) 그 배치 일곱 칸을 새
    저장본 위에 다시 얹는다(설계 9장 — 찍힌 역할도 남긴다). 샘플 fleet 은 넣지 않는다 — 합성값이
    섞이면 첫 실제 저장이 막힌다.
    """
    token = revision_token(latest_snapshot)
    previous = st.session_state.get(_REVISION_KEY)
    # 남의 저장으로 다시 세우면 버리는 가정 배치 편집을 옛 저장본 사본이 바뀌기 **전**에 센다. 남의
    # **공통** 저장(일정 쪽 그대로)이면 그 편집의 배치 일곱 칸은 새 저장본 위에 다시 얹는다(설계
    # 9장 — 재료도 옛 사본이 바뀌기 전에 든다).
    swapped = previous is not None and previous != token
    overlay_dropped = _stamped_overlay_edits() if swapped else 0
    reapply = _reapply_material(previous, token) if swapped else None
    if st.session_state.get(DRAFT_REVISION_KEY) != token:
        saved: Frames = (
            (latest_snapshot.baseline, latest_snapshot.equipment, latest_snapshot.downtime)
            if latest_snapshot is not None
            else (empty_equipment_baseline(), empty_equipment_master(), empty_downtime_schedule())
        )
        st.session_state[BASELINE_DRAFT_KEY] = saved[0].copy()
        st.session_state[EQUIPMENT_DRAFT_KEY] = saved[1].copy()
        st.session_state[DOWNTIME_DRAFT_KEY] = saved[2].copy()
        st.session_state[DRAFT_UNSCHEDULED_KEY] = (
            frozenset(latest_snapshot.unscheduled_units)
            if latest_snapshot is not None
            else frozenset()
        )
        st.session_state[DRAFT_UNIT_KEYS_KEY] = (
            tuple(latest_snapshot.unit_key_pairs) if latest_snapshot is not None else ()
        )
        st.session_state[DRAFT_REVISION_KEY] = token
        for preview_key in (BASELINE_IMPORT_KEY, EQUIPMENT_IMPORT_KEY, DOWNTIME_IMPORT_KEY):
            st.session_state.pop(preview_key, None)
    if previous != token or BUFFER_KEY not in st.session_state:
        # 토큰이 **실제로 바뀐** 경우(다른 사람이 새 리비전을 저장)에만 옛 편집을 버리고 알린다.
        # 처음 세우는 회차(앞 토큰 없음)에 미리 쌓인 층 배치까지 지우면 그 편집이 사라진다.
        replaced = previous is not None and previous != token
        if replaced:
            st.session_state[DRAFTS_REPLACED_KEY] = True
        _clear_editors()
        st.session_state[BUFFER_KEY] = _copy_frames(
            (
                st.session_state[BASELINE_DRAFT_KEY],
                st.session_state[EQUIPMENT_DRAFT_KEY],
                st.session_state[DOWNTIME_DRAFT_KEY],
            )
        )
        reapplied = (
            _reapply_layout(reapply, latest_snapshot)
            if reapply is not None and latest_snapshot is not None
            else None
        )
        if replaced and has_unsaved_equipment_edits():
            number = _replaced_by_words(previous, latest_snapshot)
            st.session_state[DISCARDED_NOTICE_KEY] = discarded_notice(
                number, overlay_dropped=overlay_dropped, reapplied=reapplied
            )
        st.session_state[_REVISION_KEY] = token
        st.session_state[_BASE_KEY] = _base_of(latest_snapshot)
        # 선택·삭제 대기·되돌리기·이름 바꿈·미저장 층 배치는 옛 편집본의 것이다. 새 저장본 위에서
        # 쓰이면 안 된다.
        stale = [
            PREVIEW_KEY,
            SELECTION_KEY,
            PENDING_DELETE_KEY,
            LAST_REMOVED_KEY,
            PENDING_RENAMES_KEY,
            EDITOR_MODULE_LAYOUTS_KEY,
            *_GRID_SESSION_KEYS,
        ]
        if replaced:
            # 남의 저장으로 다시 세우면 저장 안 한 이름 바꿈이 돌아가므로 필터가 따라갈 지도도
            # 버린다(자기 저장 뒤의 지도는 `_save_equipment_frames` 가 남긴다 — 이름이 저장본이
            # 됐다). 가정 배치 편집을 다시 얹었으면 그 편집의 찍힌 역할은 남긴다(설계 9장).
            stale += [
                FOLLOWED_FILTERS_KEY,
                PENDING_CANVASES_KEY,
                PENDING_MARKS_KEY,
                PENDING_GROUP_LABELS_KEY,
                PENDING_BASES_KEY,
            ]
            if reapplied is None or not reapplied.reapplied:
                stale.append(LAYOUT_ROLE_KEY)
        for key in stale:
            st.session_state.pop(key, None)
        _bump_buffer_generation()
        st.session_state[_SEEDED_GENERATION_KEY] = equipment_buffer_generation()
        if reapplied is not None and reapplied.reapplied:
            # 다시 얹은 편집은 저장 안 한 편집이다 — 세운 세대보다 한 칸 올린다. 편집기가 적용한
            # 묶음 모양 승인은 다시 얹은 결과에서도 그 모양인 묶음만 새 이름으로 남긴다(위 stale
            # 목록이 옛 승인을 지웠다).
            frames_now: Frames = st.session_state[BUFFER_KEY]
            st.session_state[BUFFER_KEY] = (
                frames_now[0],
                reapplied.equipment,
                frames_now[2],
            )
            stage_editor_module_layouts(reapplied.approved)
            _bump_buffer_generation()
    frames: Frames = st.session_state[BUFFER_KEY]
    return frames


def _remember_edits(frames: Frames) -> None:
    # 검증 실패한 값도 수정할 수 있어야 한다. 화면 계산이 읽는 draft에는 올리지 않는다.
    current = st.session_state.get(BUFFER_KEY)
    unchanged = isinstance(current, tuple) and all(
        left.equals(right) for left, right in zip(current, frames, strict=True)
    )
    st.session_state[BUFFER_KEY] = _copy_frames(frames)
    _clear_editors()
    # 내용이 그대로인 제출(작은 편집표 보기 적용 등)은 세대를 올리지 않는다 — 올리면 「저장 안 한
    # 편집이 있다」로 보여, 남의 저장 때 버린 것도 없는데 버렸다고 알린다.
    if not unchanged:
        _bump_buffer_generation()
        _forget_grid_undo()


def _forget_grid_undo() -> None:
    """표 밖의 길(Space 적용·작은 편집표 적용·엑셀·CSV 넣기)이 편집본을 바꿨다 — 표의 되돌리기는
    조작 뒤 자리의 역 patch 라 그 위에서 맞지 않으므로 비운다. 비울 것이 있었으면 표 토스트에
    적는다(개편 명세 7-1 넷째 자리)."""
    if st.session_state.pop(GRID_UNDO_KEY, None):
        queue_grid_toast(
            "grid", "표 밖에서 편집본을 바꿔 표의 되돌리기를 비웠습니다 — 고친 값은 그대로입니다"
        )


def queue_grid_toast(target: str, text: str, *, undo: str | None = None) -> None:
    """설비 마스터 표의 한 마운트(`"grid"`·`"detail"`·`"changes"`)에 토스트를 둔다. 번호는 늘
    오른다 — 브라우저는 번호가 바뀌어야 새 토스트로 본다(닫은 토스트 번호는 숨긴다)."""
    number = st.session_state.get(GRID_TOAST_SEQ_KEY, 0)
    number = (number if isinstance(number, int) else 0) + 1
    st.session_state[GRID_TOAST_SEQ_KEY] = number
    toasts = st.session_state.get(GRID_TOAST_KEY)
    toasts = dict(toasts) if isinstance(toasts, dict) else {}
    toasts[target] = {"id": number, "text": text, "undo": undo}
    st.session_state[GRID_TOAST_KEY] = toasts


def grid_toasts() -> dict[str, dict[str, Any]]:
    """마운트별 지금 토스트(없으면 빈 dict)."""
    toasts = st.session_state.get(GRID_TOAST_KEY)
    return {
        str(target): dict(toast)
        for target, toast in (toasts.items() if isinstance(toasts, dict) else ())
        if isinstance(toast, dict)
    }


def settle_grid_toasts(drawn: Collection[str]) -> None:
    """이 회차에 그린 마운트(`drawn` — `"grid"`·`"detail"`·`"changes"`)의 토스트는 실어 보냈다고
    적고, 실어 보낸 뒤 마운트가 그려지지 않은 토스트는 거둔다. 브라우저의 닫은 토스트 번호는
    마운트마다 새로 시작하므로(표 고르기 왕복·탭 왕복·오른쪽 칸 왕복) 남겨 두면 닫은 토스트가 다시
    마운트할 때 되살아난다. 아직 실어 보내지 않은 토스트(마운트가 숨은 동안 쌓인 것 — Space
    적용·작은 편집표 적용이 비운 되돌리기 알림)는 남겨 처음 마운트할 때 보인다. 탭 ① 이 그려진
    회차의 끝과 숨은 회차(`drawn` 빈 것)에 부른다."""
    toasts = st.session_state.get(GRID_TOAST_KEY)
    shown = st.session_state.get(GRID_TOAST_SHOWN_KEY)
    toasts = dict(toasts) if isinstance(toasts, dict) else {}
    shown = dict(shown) if isinstance(shown, dict) else {}
    for target in list(toasts):
        toast = toasts[target]
        number = toast.get("id") if isinstance(toast, dict) else None
        if target in drawn:
            shown[target] = number
        elif shown.get(target) == number:
            toasts.pop(target)
            shown.pop(target, None)
    shown = {target: number for target, number in shown.items() if target in toasts}
    for key, value in ((GRID_TOAST_KEY, toasts), (GRID_TOAST_SHOWN_KEY, shown)):
        if value:
            st.session_state[key] = value
        else:
            st.session_state.pop(key, None)


def grid_overlay() -> dict[str, str]:
    """설비 마스터 표의 칸 초안(못 읽은 글 — 편집본 밖)."""
    value = st.session_state.get(GRID_OVERLAY_KEY)
    return (
        {str(key): str(text) for key, text in value.items() if isinstance(text, str)}
        if isinstance(value, dict)
        else {}
    )


def grid_undo_steps() -> tuple[Any, ...]:
    """설비 마스터 표의 되돌리기 단계(`services/equipment_grid.UndoStep`)."""
    return undo_from_state(st.session_state.get(GRID_UNDO_KEY))


def new_unit_propagation() -> dict[str, bool]:
    """「새 호기」 칸에서 넣은 호기마다 고른 함께 넣기(지금 이름 → bool)."""
    value = st.session_state.get(NEW_UNIT_PROPAGATE_KEY)
    return (
        {str(name): flag for name, flag in value.items() if isinstance(flag, bool)}
        if isinstance(value, dict)
        else {}
    )


def remember_new_unit_propagation(name: str, propagate: bool) -> None:
    """「호기 추가」 가 그 호기의 함께 넣기를 적는다(저장 때 저장 칸 체크보다 이긴다)."""
    choices = new_unit_propagation()
    choices[name] = propagate
    st.session_state[NEW_UNIT_PROPAGATE_KEY] = choices


def chosen_new_units(frames: Frames, *, default: bool) -> frozenset[str] | None:
    """저장 요청의 `propagate_units` — 편집본의 새 호기마다 「새 호기」 칸에서 고른 값, 그 칸에서
    넣지 않은 새 호기는 저장 칸 체크(`default`). 그 칸에서 넣은 새 호기가 편집본에 없으면 None(저장
    칸 체크 하나가 모든 새 호기에 — 지금 길)."""
    choices = new_unit_propagation()
    if not choices:
        return None
    fresh = _new_unit_names(frames[1])
    if not any(name in choices for name in fresh):
        return None
    return frozenset(name for name in fresh if choices.get(name, default))


def chosen_new_unit_counts(frames: Frames) -> tuple[int, int]:
    """편집본 새 호기 가운데 「새 호기」 칸에서 넣은 것의 (같은 일정으로 넣을 수, 일정 없음 수) —
    저장 칸 아래 한 줄이 쓴다."""
    choices = new_unit_propagation()
    if not choices:
        return 0, 0
    picked = [choices[name] for name in _new_unit_names(frames[1]) if name in choices]
    return sum(picked), len(picked) - sum(picked)


# 가정 세션 저장 칸 아래 한 줄 꼬리(Q1 — Space 저장 상자 경고
# `ASSUMPTION_PROPAGATE_WARNING` 과 같은 뜻).
NEW_UNIT_OFFICIAL_COUNT_NOTE = (
    "같은 일정으로 넣는 {count:,}대는 공식 설비 시나리오에 자리 없는 새 호기로 들어가 "
    "공식 가용대수에 셉니다"
)


def new_unit_choice_line(frames: Frames, *, assumption: bool = False) -> str | None:
    """저장 칸 아래 한 줄 — 「새 호기」 칸에서 넣은 호기 수와 그 고름(그 칸의 체크가 저장
    칸 체크보다 이긴다, D8). 세 저장 자리(설비 마스터 탭 저장 구획·사이드바 설비 시나리오
    팝업·Space 「저장 칸」)가 같은 글을 쓴다 — 저장 칸 체크를 끈 채 저장해도 그 칸에서 켠
    호기는 다른 설비 시나리오에 들어가므로 어느 저장 자리에서나 미리 보인다. 가정
    세션(`assumption`)이면 같은 일정으로 넣는 호기가 공식 가용대수에 센다는 꼬리를 붙인다
    (Q1). 그 칸에서 넣은 호기가 편집본에 없으면 None."""
    spread, alone = chosen_new_unit_counts(frames)
    if not spread and not alone:
        return None
    text = (
        f":material/library_add: 「새 호기」 칸에서 넣은 {spread + alone:,}대는 그 칸의 체크를 "
        f"따릅니다 — 다른 설비 시나리오에 같은 일정으로 {spread:,}대 · 일정 없음 {alone:,}대"
    )
    if assumption and spread:
        text += f" · {NEW_UNIT_OFFICIAL_COUNT_NOTE.format(count=spread)}"
    return text


def prune_new_unit_propagation() -> None:
    """「새 호기」 칸에서 고른 함께 넣기 가운데 편집본에 그 새 호기가 더는 없는 이름을
    걷는다 — 토스트 「되돌리기」·한 단계 되돌리기·지우기·호기 되돌리기·엑셀·CSV 넣기·Space
    적용으로 그 호기가 빠지면 고름도 빠진다. 같은 이름이 다른 길(붙여넣기·엑셀·CSV·Space)로
    다시 들면 저장 칸 체크를 따른다(D8). 다시 되돌려 그 호기가 돌아와도 고름은 돌아오지
    않는다(저장 칸 체크 — 저장 구획 한 줄이 그 수를 적어 보인다). 이름 바꿈을 따라간
    **뒤**에 부른다(`follow_unit_renames` — 먼저 부르면 옛 이름의 고름이 걷힌다)."""
    choices = new_unit_propagation()
    if not choices:
        return
    buffer = st.session_state.get(BUFFER_KEY)
    fresh = set(_new_unit_names(buffer[1])) if isinstance(buffer, tuple) else set()
    kept = {name: flag for name, flag in choices.items() if name in fresh}
    if kept == choices:
        return
    if kept:
        st.session_state[NEW_UNIT_PROPAGATE_KEY] = kept
    else:
        st.session_state.pop(NEW_UNIT_PROPAGATE_KEY, None)


def _new_unit_names(master: pd.DataFrame) -> list[str]:
    """편집본 설비 마스터의 새 호기 이름(저장의 호기 키 규칙으로 저장본 호기를 잇지 않는 것)."""
    if EQUIPMENT_ID_COLUMN not in master.columns:
        return []
    names = [
        str(value).strip()
        for value in master[EQUIPMENT_ID_COLUMN].tolist()
        if isinstance(value, str) and value.strip()
    ]
    inherited = layout_lock_origins(master, _saved_master(), pending_unit_renames().units)
    return [name for name in dict.fromkeys(names) if name not in inherited]


def apply_master_grid_result(applied: GridApplied) -> None:
    """설비 마스터 표의 출납 반영 결과(`equipment_grid.apply_ops`)를 세션에 적는다 — 편집본·칸 초안·
    이름 지도·되돌리기를 한 번에. 편집본은 `replace_equipment_buffer` 또는 이 함수로만 바꾼다(같은
    세대 규칙 — 내용이 그대로면 세대를 올리지 않는다).

    `replace_equipment_buffer` 와 같은 뒷정리(미리보기·삭제 대기 거두기)를 하되 편집표는 **내용이
    바뀐 표의 것만** 버린다 — 오른쪽 칸 출납이 작은 편집표(기존 보유대수·비가동 일정)의 적용 전
    편집을 지우지 않게(개편 명세 4-7). 되돌리기 목록은 비우지 않고 결과의 목록을 쓴다. 이름을
    바꿨으면 고름·필터가 따라간다(`follow_unit_renames` — 결과 목록을 적기 **전**에 부른다: 이번 op
    뒤의 단계까지 버리지 않게)."""
    state = applied.state
    if applied.renamed:
        follow_unit_renames(applied.renamed, {})
    if applied.changed:
        if any(applied.frames_changed):
            st.session_state[BUFFER_KEY] = state.frames
            pending = st.session_state.get(PENDING_DELETE_KEY)
            baseline_changed, _, downtime_changed = applied.frames_changed
            for changed, key, target in (
                (baseline_changed, BASELINE_EDITOR_KEY, BASELINE_TARGET),
                (downtime_changed, DOWNTIME_EDITOR_KEY, DOWNTIME_TARGET),
            ):
                if not changed:
                    continue
                discard_editor(key)
                st.session_state.pop(f"{key}_applied_view", None)
                if isinstance(pending, tuple) and pending and pending[0] == target:
                    st.session_state.pop(PENDING_DELETE_KEY, None)
            st.session_state.pop(PREVIEW_KEY, None)
        _bump_buffer_generation()
    if state.overlay:
        st.session_state[GRID_OVERLAY_KEY] = dict(state.overlay)
    else:
        st.session_state.pop(GRID_OVERLAY_KEY, None)
    stage_unit_renames(state.renames)
    if state.undo:
        st.session_state[GRID_UNDO_KEY] = undo_to_state(state.undo)
    else:
        st.session_state.pop(GRID_UNDO_KEY, None)


def replace_equipment_buffer(frames: Frames) -> None:
    """표 밖(Space 편집기·작은 편집표·엑셀·CSV 넣기)에서 편집본을 바꾼다. **편집본은 이 함수 또는
    설비 마스터 표 전용 `apply_master_grid_result`(같은 세대 규칙)로만 바꾼다.**

    BUFFER_KEY 만 바꾸면 편집표가 옛 `{key}_applied_view` 프레임을 그대로 그리다 다음 제출 때 이
    편집을 되돌린다. 편집표 세대를 올리고 보기·미리보기·삭제 대기를 버린다. 내용이 바뀌면 설비
    마스터 표의 되돌리기를 비운다(그 역 patch 는 이 편집본 위에서 맞지 않는다).
    """
    _remember_edits(frames)
    st.session_state.pop(PREVIEW_KEY, None)
    st.session_state.pop(PENDING_DELETE_KEY, None)


def pending_unit_renames() -> PendingRenames:
    """Space 편집기에서 바꾼 저장 안 한 이름(지금 이름 → 저장본 이름)."""
    value = st.session_state.get(PENDING_RENAMES_KEY)
    if not isinstance(value, dict):
        return PendingRenames()
    return PendingRenames(
        units=dict(value.get("units") or {}), groups=dict(value.get("groups") or {})
    )


def stage_unit_renames(renames: PendingRenames) -> None:
    """저장 안 한 이름 지도를 둔다(비면 지운다). 편집본과 함께 버려지고 저장하면 비워진다."""
    if renames:
        st.session_state[PENDING_RENAMES_KEY] = {
            "units": dict(renames.units),
            "groups": dict(renames.groups),
        }
    else:
        st.session_state.pop(PENDING_RENAMES_KEY, None)


def editor_module_layouts() -> dict[str, ModuleLayout]:
    """Space 배치 편집기가 적용한 모듈 묶음의 적용 뒤 모양(Main 설비 → 모양)."""
    value = st.session_state.get(EDITOR_MODULE_LAYOUTS_KEY)
    return dict(value) if isinstance(value, dict) else {}


def stage_editor_module_layouts(layouts: Mapping[str, ModuleLayout]) -> None:
    """배치 편집기 적용이 옮기거나 빼거나 보낸 묶음의 적용 뒤 모양을 더한다(같은 묶음은 새 모양이
    이긴다). 저장 검사가 이 모양 그대로인 묶음을 통과시킨다(`saved_master_violations`)."""
    if layouts:
        st.session_state[EDITOR_MODULE_LAYOUTS_KEY] = {**editor_module_layouts(), **layouts}


def _saved_master() -> pd.DataFrame:
    """편집본이 나온 저장본의 설비 마스터(`ensure_equipment_drafts` 가 세운 사본, 없으면 빈 표)."""
    saved = st.session_state.get(EQUIPMENT_DRAFT_KEY)
    return saved if isinstance(saved, pd.DataFrame) else empty_equipment_master()


def saved_master_violations(master: pd.DataFrame) -> list[str]:
    """저장하려는 설비 마스터에서 모듈 좌표·크기가 저장본과 달라졌는데 바둑판이 아닌 Main 설비
    묶음(`space_layout_edit.module_layout_violations` — 저장 안 한 Space 이름 바꿈과 배치 편집기가
    적용한 묶음 모양을 함께 넘긴다). 비면 저장해도 된다."""
    return module_layout_violations(
        _saved_master(),
        master,
        renames=pending_unit_renames().units,
        approved=editor_module_layouts(),
    )


def draft_unit_keys() -> dict[str, str]:
    """저장본 사본의 설비명 → 호기 키(`ensure_equipment_drafts` 가 세운다, 없으면 빈 지도)."""
    value = st.session_state.get(DRAFT_UNIT_KEYS_KEY)
    if not isinstance(value, tuple):
        return {}
    return {str(name): str(key) for name, key in value}


def _sample_names(names: Sequence[str], limit: int = 3) -> str:
    """「APW01, APW02 외 3」 — 자연 정렬 앞 `limit` 개."""
    ordered = sorted(names, key=natural_name_key)
    head = ", ".join(ordered[:limit])
    return head if len(ordered) <= limit else f"{head} 외 {len(ordered) - limit}"


@dataclass(frozen=True)
class RemovalElsewhere:
    """편집본에서 지운 저장본 호기 가운데 **다른** 설비 시나리오 최신에 일정이 있는 것 — (설비명, 그
    시나리오 이름들). 저장하면 공통 대장에서 빠져 그 시나리오들의 일정·비가동도 빠진다(설계 11-2
    6단계 — 호기 목록은 공통 하나다)."""

    units: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(name for name, _ in self.units)

    @property
    def scenarios(self) -> tuple[str, ...]:
        return tuple(sorted({scenario for _, names in self.units for scenario in names}))

    @property
    def token(self) -> str:
        """확인 체크 key 꼬리 — 호기마다 (설비명, 일정이 있는 시나리오들)의 지문. 경고·체크 글의
        수와 이름(호기·시나리오)이 이것으로 정해지므로, 남이 복제·되돌리기로 그 호기 일정이 든
        시나리오를 바꾸거나 같은 제출에서 더 지우면 체크가 풀린 새 칸으로 선다."""
        text = "\n".join(
            "\t".join((name, *sorted(scenarios))) for name, scenarios in sorted(self.units)
        )
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    def covered_by(self, confirmed: RemovalElsewhere | None) -> bool:
        """확인 체크로 본 것(`confirmed`)이 이 삭제를 덮는가 — 호기마다 본 글에 있었고 그 호기
        일정이 빠질 시나리오가 본 글의 것 안이다. 본 뒤 남이 그 호기 일정이 든 시나리오를 늘렸으면
        거짓."""
        if confirmed is None:
            return False
        seen = {name: set(scenarios) for name, scenarios in confirmed.units}
        return all(name in seen and set(scenarios) <= seen[name] for name, scenarios in self.units)

    def message(self) -> str:
        scenarios = "·".join(f"「{literal_markdown(name)}」" for name in self.scenarios)
        return (
            f"지우는 호기 {len(self.units):,}대({_sample_names(sorted(self.names))})는 다른 설비 "
            f"시나리오 {len(self.scenarios):,}개({scenarios})에도 일정이 있습니다 — 저장하면 공통 "
            "대장에서 빠져 그 설비 시나리오에서도 일정·비가동과 함께 빠집니다. 이 시나리오에서만 "
            "빼려면 지우지 말고 정지·반출/이설일정을 적으세요."
        )

    def confirm_label(self) -> str:
        return (
            f"다른 설비 시나리오 {len(self.scenarios):,}개에서 {len(self.units):,}대의 일정이 "
            "빠지는 것을 알고 저장합니다"
        )

    def refusal(self) -> str:
        return (
            f"{self.message()} 저장하려면 가용설비 현황 설비 마스터 탭 저장 칸의 "
            f"「{self.confirm_label()}」 를 켜고 다시 저장하세요."
        )


def removals_elsewhere(
    frames: Frames, *, database_path: str, scenario_id: str | None
) -> RemovalElsewhere | None:
    """편집본(`frames`)에서 지운 저장본 호기 가운데 `scenario_id` 가 아닌 ACTIVE 설비 시나리오
    최신에 일정이 있는 것. 지운 호기가 없으면 저장소를 읽지 않는다. 이름 바꿈으로 비운 이름은 지운
    것이 아니다(`reserved_names`). 없으면 None."""
    saved = _saved_master()
    deleted = reserved_names(saved, frames[1], frames[2], pending_unit_renames()).deleted
    if not deleted:
        return None
    elsewhere = load_units_scheduled_elsewhere(database_path, scenario_id)
    if not elsewhere:
        return None
    keys = draft_unit_keys()
    units = tuple(
        (name, elsewhere[key])
        for name in sorted(deleted, key=natural_name_key)
        if (key := keys.get(name, legacy_unit_key(name))) in elsewhere
    )
    return RemovalElsewhere(units) if units else None


# 배치 일곱 칸을 어디에 고치나(`space_edit_mode(...).layout` 과 같은 값 — 그 모듈이 이 모듈을 읽어
# 여기서는 글자로 둔다).
LayoutMode = Literal["official", "overlay", "locked"]


def _official_places_by_name(snapshot: EquipmentSnapshot | None) -> dict[str, Place]:
    """그리는 한 벌에서 얹은 배치가 공식과 다른 호기 — 설비명 → 공식 일곱 칸."""
    if snapshot is None or not snapshot.layout_official_places:
        return {}
    names = {key: name for name, key in snapshot.unit_key_pairs}
    return {names[key]: place for key, place in snapshot.layout_official_places if key in names}


def official_layout_cells(
    snapshot: EquipmentSnapshot | None, official: EquipmentSnapshot | None
) -> dict[str, tuple[object, ...]]:
    """`_official_places_by_name` 과 같은 호기의 공식 일곱 칸 **원래 값** — 공식 스냅샷(공통 최신
    + 최신 공식 발행)의 그 호기 칸 그대로(반올림 없음). 호기는 호기 키로 맞댄다. 가정 세션
    「공식 자리로 되돌리기」 가 견줄 꼴 대신 적는다(`GridContext.official_cells`)."""
    if snapshot is None or official is None or not snapshot.layout_official_places:
        return {}
    names = {key: name for name, key in snapshot.unit_key_pairs}
    official_names = {key: name for name, key in official.unit_key_pairs}
    columns = [column for column in SCENARIO_LAYOUT_COLUMNS if column in official.equipment.columns]
    if len(columns) != len(SCENARIO_LAYOUT_COLUMNS):
        return {}
    rows = official.equipment.drop_duplicates(EQUIPMENT_ID_COLUMN).set_index(EQUIPMENT_ID_COLUMN)
    cells: dict[str, tuple[object, ...]] = {}
    for key, _ in snapshot.layout_official_places:
        name, official_name = names.get(key), official_names.get(key)
        if name is None or official_name is None or official_name not in rows.index:
            continue
        cells[name] = tuple(rows.loc[official_name, column] for column in columns)
    return cells


def _csv_scenario_mismatch(file_name: str | None, scenario_name: str | None) -> str | None:
    """올린 CSV 이름이 「현재 데이터」 내보내기 꼴(`current_data_file_name` —
    `equipment_master_<시나리오>_rN_cM…`)인데 그 시나리오가 지금 세션의 것이 아니면 한 줄(설계
    10장 — 공식 CSV 를 가정 세션에 올리면 배치안이 공식 자리로 돌아간다). 꼴이 아니거나 같으면
    None."""
    if not file_name or not scenario_name:
        return None
    matched = _CURRENT_DATA_NAME.fullmatch(file_name)
    if matched is None:
        return None
    named = matched.group(1)
    if named == _file_name_part(scenario_name):
        return None
    return (
        f"올린 CSV 는 다른 설비 시나리오(「{named.replace('_', ' ')}」)에서 내려받은 「현재 "
        f"데이터」 입니다 — 지금 세션은 「{scenario_name}」 입니다. 배치·일정 칸이 그 시나리오의 "
        "값이면 이 시나리오의 배치·일정이 그 값으로 바뀝니다."
    )


# 「현재 데이터」 설비 마스터 내보내기 이름(`current_data_file_name`)에서 시나리오 몫을 꺼낸다.
_CURRENT_DATA_NAME = re.compile(r"equipment_master_(.+)_r\d+_c\d+(?:_edited)?_\d{8}\.csv")


def layout_lock_origins(
    buffer: pd.DataFrame, saved: pd.DataFrame, renames: Mapping[str, str]
) -> dict[str, str]:
    """편집본 설비명 → 저장하면 그 호기 키를 이어받을 저장본 설비명(`inherited_unit_names` —
    저장이 호기 키를 정하는 규칙 그대로, `renames` 도 저장이 넘기는 저장 안 한 이름 지도). 새
    호기는 빠진다.

    배치 칸 잠금·「배치 변경만 버리기」 가 「있던 호기」를 이 지도로 고른다 — 제출 전 편집본에 그
    이름이 있었는지가 아니라 저장했을 때 같은 호기인지로 보아야, 지운 뒤 다시 넣거나 설비명을
    바꿨다 되돌린 행도 같은 호기로 읽힌다."""
    names = [name for name in buffer[EQUIPMENT_ID_COLUMN].dropna().astype(str).str.strip() if name]
    saved_names = saved[EQUIPMENT_ID_COLUMN].dropna().astype(str).str.strip()
    return inherited_unit_names(names, set(saved_names) - {""}, renames)


@dataclass(frozen=True)
class LayoutLock:
    """편집본에서 저장본(세션 저장본 — 가정 세션이면 그 시나리오의 배치)과 다른 배치 — 「배치 변경만
    버리기」 와 배치 편집이 잠긴 회차(`space_edit_mode(...).layout == "locked"`)의 제출 검사가 이
    값으로 되돌린다.

    - `restore` — 배치 일곱 칸을 저장본 값으로 되돌릴 있던 호기(지금 설비명 → 저장본 설비명).
    - `place` — 자리 없이 맞출 행(지금 설비명 → 일곱 칸 — 새 호기는 동·층·X좌표·Y좌표를 비우고,
      있는 묶음에 드는 모듈과 묶음에 든 동·층 미정 호기는 그 묶음의 동·층). 크기·레이아웃표시는
      편집본 값 그대로다.

    둘 다 비면 편집본에 배치 편집이 없다(`layout_edits` — 저장의 대조 역할 재료)."""

    restore: Mapping[str, str]
    place: Mapping[str, Place]

    def __bool__(self) -> bool:
        return bool(self.restore or self.place)

    def apply(self, buffer: pd.DataFrame, saved: pd.DataFrame) -> pd.DataFrame:
        """잠근 칸을 되돌리고 맞춘 `buffer` 사본(나머지 칸·행은 그대로)."""
        return place_rows(restore_saved_layout(buffer, saved, self.restore), self.place)

    @property
    def unit_names(self) -> tuple[str, ...]:
        """바뀐 배치의 지금 설비명(되돌릴 것 → 맞출 것, 자연 정렬)."""
        return tuple(sorted({*self.restore, *self.place}, key=natural_name_key))


def layout_edits(
    buffer: pd.DataFrame, saved: pd.DataFrame, renames: Mapping[str, str]
) -> LayoutLock:
    """편집본(`buffer`)을 세션 저장본(`saved`)에 대 본 배치 편집. 「있던 호기」 는 저장의 호기 키
    규칙(`layout_lock_origins`)으로 고르고, 그 가운데 자리가 묶음 규칙으로 정해지는 행(동·층 미정
    호기를 묶음에 넣음)은 저장본 값이 아니라 그 자리로 맞춘다."""
    origins = layout_lock_origins(buffer, saved, renames)
    governed = assumption_common_places(buffer, saved, origins)
    restore = {
        name: origins[name]
        for name in saved_layout_drift(saved, buffer, origins)
        if name not in governed
    }
    return LayoutLock(restore=restore, place=misplaced_rows(buffer, governed))


def stamped_layout_role() -> str | None:
    """이 편집본에 쌓인 배치 편집을 적용할 때 찍은 역할("official"·"overlay"). 없으면 None."""
    value = st.session_state.get(LAYOUT_ROLE_KEY)
    return value if value in ("official", "overlay") else None


def stamp_layout_role(role: str) -> None:
    """배치를 바꾸는 적용마다 그때의 역할을 찍는다. 이미 다른 역할이 찍혀 있으면 그대로 둔다 —
    그 회차는 화면이 배치 편집을 잠가(`space_edit_mode`) 이 적용이 오지 않는다."""
    if role in ("official", "overlay") and stamped_layout_role() is None:
        st.session_state[LAYOUT_ROLE_KEY] = role


def _layout_memo_key() -> tuple[object, ...]:
    """배치 편집 판정 메모의 열쇠 — 편집본 세대(내용이 바뀔 때마다 오른다)·편집본 출발 토큰·저장본
    사본 토큰·이름 지도."""
    return (
        equipment_buffer_generation(),
        st.session_state.get(_REVISION_KEY),
        st.session_state.get(DRAFT_REVISION_KEY),
        tuple(sorted(pending_unit_renames().units.items())),
    )


def buffer_has_layout_edits() -> bool:
    """편집본에 배치 편집(`layout_edits` — 있던 호기 배치 칸·새 호기 자리)이 있는가. 편집본
    전체를 저장본에 대 보므로(합성 3천 대에 0.13~0.17 s — 샘플 관측) 열쇠(`_layout_memo_key`)로
    세션에 한 번만 잰다 — 역할이 찍힌 세션의 회차마다 `live_layout_role` 이 부른다(개편 명세 8장
    예산)."""
    buffer = st.session_state.get(BUFFER_KEY)
    if not isinstance(buffer, tuple):
        return False
    key = _layout_memo_key()
    memo = st.session_state.get(LAYOUT_EDITS_MEMO_KEY)
    if isinstance(memo, tuple) and len(memo) == 2 and memo[0] == key:
        return bool(memo[1])
    found = bool(layout_edits(buffer[1], _saved_master(), pending_unit_renames().units))
    st.session_state[LAYOUT_EDITS_MEMO_KEY] = (key, found)
    return found


def layout_memo_mark() -> tuple[object, ...]:
    """편집을 얹기 **전** 메모 열쇠 — 배치에 닿지 않는 편집 뒤 `carry_layout_memo` 에 넘긴다."""
    return _layout_memo_key()


def carry_layout_memo(before: tuple[object, ...]) -> None:
    """배치 칸·설비명·Main 설비·행을 건드리지 않은 편집(칸 고침·날짜 밀기 — 표 출납)은 배치 편집
    판정을 바꾸지 않는다. 얹기 전 열쇠(`before`)의 판정을 지금 열쇠로 옮겨 다음 회차가 다시 재지
    않게 한다. 얹기 전 메모가 없으면 그대로 둔다(다음에 잰다)."""
    memo = st.session_state.get(LAYOUT_EDITS_MEMO_KEY)
    if isinstance(memo, tuple) and len(memo) == 2 and memo[0] == before:
        st.session_state[LAYOUT_EDITS_MEMO_KEY] = (_layout_memo_key(), memo[1])


def live_layout_role() -> str | None:
    """찍힌 역할 — 편집본에 배치 편집(있던 호기 배치 칸·새 호기 자리)이나 층 값 대기분이 아직 있을
    때만. 모두 사라졌으면(되돌린 편집·저장본과 같아진 편집) 찍힌 역할을 지우고 None 이다 — 남은
    찍힘이 역할이 바뀐 뒤의 새 편집을 잠그지 않게. Space·설비 마스터 탭이 편집 권한을 정하기 전에
    부른다(판정은 `buffer_has_layout_edits` 메모)."""
    stamped = stamped_layout_role()
    if stamped is None:
        return None
    if (
        pending_floor_canvases()
        or pending_floor_marks()
        or pending_floor_group_labels()
        or buffer_has_layout_edits()
    ):
        return stamped
    st.session_state.pop(LAYOUT_ROLE_KEY, None)
    return None


def _stamped_overlay_edits() -> int:
    """가정 역할로 찍힌 배치 편집의 호기 수(편집본 대 저장본 사본) — 남의 저장으로 편집본을 다시
    세울 때 버림 알림에 따로 적는다. 가정 역할이 아니거나 편집본이 없으면 0."""
    buffer = st.session_state.get(BUFFER_KEY)
    if stamped_layout_role() != "overlay" or not isinstance(buffer, tuple):
        return 0
    return len(layout_edits(buffer[1], _saved_master(), pending_unit_renames().units).unit_names)


@dataclass(frozen=True)
class _ReapplyMaterial:
    """남의 공통 저장으로 편집본을 다시 세우기 **전**에 든 다시 얹기 재료(설계 9장)."""

    old_saved: pd.DataFrame
    buffer: pd.DataFrame
    origins: Mapping[str, str]
    old_keys: Mapping[str, str]
    approved: Mapping[str, ModuleLayout]


def _reapply_material(previous: object, token: str) -> _ReapplyMaterial | None:
    """다시 얹기 재료 — 가정 역할로 찍힌 배치 편집이 있고 토큰의 일정 쪽이 그대로(남의 **공통**
    저장)일 때만. 일정 쪽이 바뀌었거나(다른 리비전) 공식 역할이면 None(지금처럼 버린다)."""
    if stamped_layout_role() != "overlay" or _token_parts(previous)[1] != _token_parts(token)[1]:
        return None
    buffer = st.session_state.get(BUFFER_KEY)
    if not isinstance(buffer, tuple):
        return None
    saved = _saved_master()
    pairs = st.session_state.get(DRAFT_UNIT_KEYS_KEY)
    if not isinstance(pairs, tuple) or not pairs:
        return None
    return _ReapplyMaterial(
        old_saved=saved.copy(),
        buffer=buffer[1].copy(),
        origins=layout_lock_origins(buffer[1], saved, pending_unit_renames().units),
        old_keys={str(name): str(key) for name, key in pairs},
        approved=editor_module_layouts(),
    )


def _reapply_layout(
    material: _ReapplyMaterial, latest_snapshot: EquipmentSnapshot
) -> ReappliedLayout:
    """새 저장본 사본 위에 가정 배치 일곱 칸 편집을 다시 얹는다 — 호기 키로 잇고 남이 지운 호기는
    뺀다(`layout_overlay.reapply_layout_edits`). 배치 편집기가 적용한 묶음 모양 승인도 새 저장본
    이름으로 옮겨 돌려받는다 — 버리면 편집기만 낼 수 있는 묶음이 저장에서 막힌다."""
    return reapply_layout_edits(
        material.old_saved,
        material.buffer,
        st.session_state[EQUIPMENT_DRAFT_KEY],
        origins=material.origins,
        old_keys=material.old_keys,
        new_names={str(key): str(name) for name, key in latest_snapshot.unit_key_pairs},
        approved=material.approved,
    )


def discarded_notice(
    number: str, *, overlay_dropped: int, reapplied: ReappliedLayout | None
) -> str:
    """남의 저장으로 편집본을 다시 세운 회차의 알림(한 번). 가정 배치 편집을 새 저장본 위에 다시
    얹었으면 그 수와 빠진 호기를 따로 적는다(설계 9장) — 그 밖의 저장 안 한 편집(설비 마스터 칸·
    도면 요소·Main 설비명 위치)은 지금처럼 버렸다."""
    head = f"다른 사용자가 {number}{object_particle(number)} 저장해, "
    if reapplied is not None and reapplied.reapplied:
        dropped = (
            f" 그 사이 공통 대장에서 빠진 호기 {len(reapplied.dropped):,}대"
            f"({', '.join(reapplied.dropped[:3])}{' 외' if len(reapplied.dropped) > 3 else ''})의 "
            "편집은 뺐습니다."
            if reapplied.dropped
            else ""
        )
        return (
            head + "최신 저장본으로 다시 열고 저장하지 않은 가정 배치 편집 "
            f"{reapplied.reapplied:,}대(호기 위치)는 그 위에 다시 얹었습니다.{dropped} 그 밖의 "
            "저장하지 않은 설비 편집(설비 마스터 칸·도면 요소·Main 설비명 위치)은 버렸습니다 — "
            "배치를 확인하고 저장하세요."
        )
    return (
        head
        + "이 화면에서 저장하지 않은 설비 편집(설비 마스터·Space 배치)을 버리고 최신 저장본으로 "
        "다시 열었습니다."
        + (
            f" 그 가운데 가정 배치 편집 {overlay_dropped:,}대도 버렸습니다 — 최신 위에서 "
            "다시 옮기세요."
            if overlay_dropped
            else ""
        )
    )


def discard_layout_edits() -> None:
    """「배치 변경만 버리기」 — 편집본의 배치 일곱 칸을 저장본 값으로 되돌리고(새 호기는 자리
    없이) 층 대기분(캔버스·도면 요소·Main 설비명 위치)·편집기 모듈 모양·찍힌 역할을 비운다. 공통·
    일정 칸 편집과 이름 바꿈, FAB 전체 배치 대기분은 남긴다(설계 8-6·검토 M5). 콜백에서 부른다."""
    buffer = st.session_state.get(BUFFER_KEY)
    if isinstance(buffer, tuple):
        saved = _saved_master()
        lock = layout_edits(buffer[1], saved, pending_unit_renames().units)
        if lock:
            replace_equipment_buffer((buffer[0], lock.apply(buffer[1], saved), buffer[2]))
    for key in (
        PENDING_CANVASES_KEY,
        PENDING_MARKS_KEY,
        PENDING_GROUP_LABELS_KEY,
        PENDING_BASES_KEY,
        EDITOR_MODULE_LAYOUTS_KEY,
        LAYOUT_ROLE_KEY,
    ):
        st.session_state.pop(key, None)


def layout_lock_refusal(
    names: Sequence[str],
    *,
    reason: str | None,
    pasted: bool,
    held: bool = False,
    placed: Sequence[str] = (),
) -> str:
    """배치 편집이 잠긴 회차(`reason` — `space_edit_mode` 의 잠금 까닭)에 배치 칸을 고친 제출·
    붙여넣기 글 — `names` 는 배치 칸을 고친 있던 호기, `placed` 는 자리 없이 맞춘(붙여넣기면 맞춰야
    할) 새 호기다. `held` 는 그 제출이 저장·미리보기 단추였다는 뜻이다 — 고친 칸을 보게 그 회차
    저장·미리보기는 하지 않는다."""
    units = f"있던 호기 {len(names):,}대({_sample_names(names)})"
    news = f"새 호기 {len(placed):,}대({_sample_names(placed)})"
    why = f" — {reason}" if reason else ""
    if pasted:
        moves = f"{units}의 배치 칸을"
        places = f"{news}에 자리(동·층·X좌표·Y좌표)를"
        if names and placed:
            what = f"{moves} 바꾸고 {places} 넣습니다"
        elif names:
            what = f"{moves} 바꿉니다"
        else:
            what = f"{places} 넣습니다"
        head = f"붙여넣기가 {what} — 배치 편집이 잠겨 있어 미리보지 않았습니다{why}"
        if names:
            head += " 있던 호기의 배치 칸은 빼거나 저장본 값 그대로 다시 붙여넣으세요."
        if placed:
            head += " 새 호기는 동·층·X좌표·Y좌표를 비우고 다시 붙여넣으세요."
        return head
    parts = []
    if names:
        parts.append(f"{units}의 배치 칸 고침은 저장본 값으로 되돌리고")
    if placed:
        parts.append(f"{news}는 자리 없이 넣도록 동·층·X좌표·Y좌표를 맞추고")
    head = f"배치 편집이 잠겨 있어 {' '.join(parts)} 나머지 편집은 편집본에 반영했습니다{why}"
    if held:
        head += " 이번에 누른 저장·미리보기는 하지 않았습니다 — 바뀐 칸을 보고 다시 누르세요."
    return head


def layout_paste_refusal(
    review: ImportReview,
    *,
    saved: pd.DataFrame,
    renames: Mapping[str, str],
    reason: str | None,
) -> str | None:
    """배치 편집이 잠긴 회차에 배치를 바꾸는 설비 마스터 붙여넣기를 미리보기 전에 막는다(`saved` 는
    세션 저장본, `renames` 는 저장 안 한 이름 지도): 있던 호기의 배치 칸을 저장본과 다르게 하거나,
    새 호기에 자리(동·층·X좌표·Y좌표)를 넣는 것. 새 호기 행 자체·크기·레이아웃표시는 받는다. 막을
    것이 없으면 None."""
    if review.target != "설비 마스터":
        return None
    lock = layout_edits(review.candidate[1], saved, renames)
    if not lock:
        return None
    return layout_lock_refusal(
        list(lock.restore), reason=reason, pasted=True, placed=list(lock.place)
    )


def assumption_group_paste_refusal(
    review: ImportReview,
    *,
    saved: pd.DataFrame,
    renames: Mapping[str, str],
    official_places: Mapping[str, Place],
) -> str | None:
    """가정 설비 시나리오에서 공식 동·층이 다른 호기를 한 묶음으로 묶는 설비 마스터 붙여넣기를
    미리보기 전에 막는다 — 저장소가 같은 글로 거부할 것을 먼저 쓴다(설계 10장·Q1(c)). 막을 것이
    없으면 None."""
    if review.target != "설비 마스터":
        return None
    candidate = review.candidate[1]
    found = assumption_group_refusal(
        candidate,
        saved,
        layout_lock_origins(candidate, saved, renames),
        official_places,
    )
    return found[0] if found is not None else None


def follow_unit_renames(renames: Mapping[str, str], groups: Mapping[str, str]) -> None:
    """이름을 바꿨다(설비명 `renames`·Main 설비 `groups`, 옛 이름 → 새 이름). 이름을 기억한
    설비 마스터 탭 칸을 따라 옮긴다 — Space 편집기와 설비 마스터 호기 상세(개편)가 같이 부른다.

    - 비가동 일정 작은 편집표의 **선택**과 **삭제 확인 대기**(`PENDING_DELETE_KEY`)의 키는 새
      설비명으로 옮긴다 — 옛 이름에 매달린 확인이 엉뚱한 행을 지우거나 비게 되지 않게.
    - 그 표 목록 필터의 고른 값(`설비명`)도 새 이름으로 옮긴다 — 그대로 두면 다음 회차에 선택지에
      없는 값이라 지워져 필터가 「전체」 로 돌아간다. 필터 위젯이 그려지기 전에만 고칠 수 있어
      `FOLLOWED_FILTERS_KEY` 에 모았다가 `render_small_editor` 가 얹는다.
    - `방금 삭제 되돌리기` 는 **어느 이름이든 바꾸면** 버린다. 지운 행은 옛 이름을 지니므로 되살리면
      비가동 일정이 옛 설비명을 가리키거나 엉뚱한 호기에 붙고, 지운 모듈 행은 옛 Main 설비로 돌아와
      한 설비가 둘로 갈린다(검증은 통과해 그대로 저장된다).
    """
    renames = {old: new for old, new in renames.items() if old != new}
    groups = {old: new for old, new in groups.items() if old != new}
    if not renames and not groups:
        return
    selection = _current_selection()
    if selection and renames:
        st.session_state[SELECTION_KEY] = {
            target: (_renamed_keys(keys, renames) if target in _NAMED_TARGETS else keys)
            for target, keys in selection.items()
        }
    pending = st.session_state.get(PENDING_DELETE_KEY)
    if renames and isinstance(pending, tuple) and len(pending) == 2:
        target, keys = pending
        if target in _NAMED_TARGETS and isinstance(keys, frozenset):
            st.session_state[PENDING_DELETE_KEY] = (target, _renamed_keys(keys, renames))
    _stage_followed_filter(filter_widget_key(DOWNTIME_VIEW_PREFIX, EQUIPMENT_ID_COLUMN), renames)
    st.session_state.pop(LAST_REMOVED_KEY, None)
    # 「새 호기」 칸에서 고른 함께 넣기는 새 호기 이름에 매달려 있다 — 이름을 따라간다(맞바꿈도).
    choices = new_unit_propagation()
    if renames and any(name in choices for name in renames):
        st.session_state[NEW_UNIT_PROPAGATE_KEY] = {
            renames.get(name, name): flag for name, flag in choices.items()
        }
    # 설비 마스터 표의 되돌리기 가운데 행 조각을 든 단계(지우기·되살리기·통째)와 그 앞 단계도 같은
    # 까닭으로 버린다(개편 명세 4-11 셋째 자리 — 역 patch 라 앞 단계는 자리가 맞지 않는다).
    steps = grid_undo_steps()
    if steps:
        kept = after_row_steps(steps)
        if kept:
            st.session_state[GRID_UNDO_KEY] = undo_to_state(kept)
        else:
            st.session_state.pop(GRID_UNDO_KEY, None)


# 선택·삭제 대기 키의 첫 칸이 설비명인 작은 편집표(기존 보유대수 키의 첫 칸은 공정이다).
_NAMED_TARGETS = (DOWNTIME_TARGET,)


def _renamed_keys(keys: frozenset[RowKey], renames: Mapping[str, str]) -> frozenset[RowKey]:
    """업무 키(첫 칸 설비명)의 설비명을 옛 → 새로 한꺼번에 옮긴다(맞바꿈도 맞게 간다)."""
    return frozenset((renames.get(key[0], key[0]), *key[1:]) for key in keys)


def _stage_followed_filter(filter_key: str, mapping: Mapping[str, str]) -> None:
    """목록 필터 한 칸이 따라갈 이름 지도를 앞서 모은 지도에 잇는다(A→B 뒤 B→C 는 A→C·B→C)."""
    if not mapping:
        return
    staged = st.session_state.get(FOLLOWED_FILTERS_KEY)
    followed: dict[str, dict[str, str]] = dict(staged) if isinstance(staged, dict) else {}
    before = dict(followed.get(filter_key, {}))
    joined = {old: mapping.get(new, new) for old, new in before.items()}
    joined.update({old: new for old, new in mapping.items() if old not in joined})
    followed[filter_key] = joined
    st.session_state[FOLLOWED_FILTERS_KEY] = followed


def _apply_followed_filters() -> None:
    """모아 둔 이름 지도를 목록 필터의 고른 값에 얹는다. 필터 위젯을 그리기 **전**에 부른다."""
    staged = st.session_state.pop(FOLLOWED_FILTERS_KEY, None)
    if not isinstance(staged, dict):
        return
    for filter_key, mapping in staged.items():
        chosen = st.session_state.get(filter_key)
        if not isinstance(chosen, list) or not isinstance(mapping, dict):
            continue
        moved = list(dict.fromkeys(mapping.get(str(value), str(value)) for value in chosen))
        if moved != chosen:
            st.session_state[filter_key] = moved


def render_name_changes(names: pd.DataFrame, *, key: str | None = None) -> None:
    """저장 안 한 이름 바꿈 목록(`space_layout_edit.name_changes`) — 접힌 「이름 바꿈 n건」 과 그
    뜻. Space 편집기 상자와 설비 마스터 탭이 같은 꼴로 그린다."""
    with st.expander(f"이름 바꿈 {len(names)}건", key=key):
        st.dataframe(names, hide_index=True, width="stretch")
        st.caption(NAME_CHANGES_CAPTION)


def pending_floor_canvases() -> dict[FloorKey, CanvasSize]:
    """Space 에서 바꿨지만 아직 저장하지 않은 층 캔버스."""
    value = st.session_state.get(PENDING_CANVASES_KEY)
    return dict(value) if isinstance(value, dict) else {}


def pending_floor_marks() -> dict[FloorKey, tuple[FloorLayoutMark, ...]]:
    """Space 에서 바꿨지만 아직 저장하지 않은 층 도면 요소(층 전체 목록)."""
    value = st.session_state.get(PENDING_MARKS_KEY)
    return dict(value) if isinstance(value, dict) else {}


def pending_floor_group_labels() -> dict[FloorKey, dict[str, str]]:
    """Space 에서 바꿨지만 아직 저장하지 않은 층 Main 설비명 위치(층 전체 — 처음 위치인 묶음은
    빠짐)."""
    value = st.session_state.get(PENDING_GROUP_LABELS_KEY)
    return dict(value) if isinstance(value, dict) else {}


def pending_floor_bases() -> dict[FloorKey, FloorLayoutBase]:
    """층마다 편집을 시작할 때 본 저장값(캔버스, 요소·위치 지문)."""
    value = st.session_state.get(PENDING_BASES_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _remember_base(key: FloorKey, base: FloorLayoutBase | None) -> None:
    """그 층의 **첫** 대기분이 본 저장값만 남긴다. 대기분이 다 빠지면 함께 버린다."""
    bases = pending_floor_bases()
    if (
        key not in pending_floor_canvases()
        and key not in pending_floor_marks()
        and key not in pending_floor_group_labels()
    ):
        bases.pop(key, None)
    elif key not in bases and base is not None:
        bases[key] = base
    st.session_state[PENDING_BASES_KEY] = bases


def stage_floor_canvas(
    key: FloorKey, canvas: CanvasSize | None, *, base: FloorLayoutBase | None = None
) -> None:
    """미저장 캔버스를 둔다. None 이면 그 층 대기분을 지운다(저장값과 같아졌을 때·팝업이 그 층
    캔버스를 저장했을 때). `base` 는 편집을 시작할 때 본 저장값이다."""
    staged = pending_floor_canvases()
    if canvas is None and key not in staged:
        return
    if canvas is None:
        staged.pop(key, None)
    else:
        staged[key] = canvas
    st.session_state[PENDING_CANVASES_KEY] = staged
    _remember_base(key, base)
    _bump_buffer_generation()


def stage_floor_marks(
    key: FloorKey,
    marks: tuple[FloorLayoutMark, ...] | None,
    *,
    base: FloorLayoutBase | None = None,
) -> None:
    """미저장 도면 요소(층 전체)를 둔다. None 이면 그 층 대기분을 지운다."""
    staged = pending_floor_marks()
    if marks is None and key not in staged:
        return
    if marks is None:
        staged.pop(key, None)
    else:
        staged[key] = marks
    st.session_state[PENDING_MARKS_KEY] = staged
    _remember_base(key, base)
    _bump_buffer_generation()


def stage_floor_group_labels(
    key: FloorKey,
    labels: Mapping[str, str] | None,
    *,
    base: FloorLayoutBase | None = None,
) -> None:
    """미저장 Main 설비명 위치(층 전체)를 둔다. None 이면 그 층 대기분을 지운다(저장값과 같아졌을
    때)."""
    staged = pending_floor_group_labels()
    if labels is None and key not in staged:
        return
    if labels is None:
        staged.pop(key, None)
    else:
        staged[key] = dict(labels)
    st.session_state[PENDING_GROUP_LABELS_KEY] = staged
    _remember_base(key, base)
    _bump_buffer_generation()


def rebase_floor_canvas(key: FloorKey, canvas: CanvasSize | None) -> None:
    """이 세션이 팝업으로 그 층 캔버스를 방금 저장·삭제했다. 그 층 대기분이 본 저장값의 **캔버스
    부분만** 새 값으로 바꾼다 — 그대로 두면 다음 저장이 「다른 사용자가 먼저 바꿨다」로 영영 막힌다.
    요소 지문은 처음 본 값 그대로 둔다(그 사이 남이 바꾼 요소는 여전히 저장 때 걸린다)."""
    bases = pending_floor_bases()
    if key in bases:
        bases[key] = (canvas, bases[key][1])
        st.session_state[PENDING_BASES_KEY] = bases


def effective_floor_canvases(stored: FloorCanvasMap) -> dict[FloorKey, CanvasSize]:
    """저장된 캔버스에 미저장 캔버스를 덮은 값. 저장·미리보기 검증과 편집표 상한이 이것을 본다 —
    Space 에서 넓힌 캔버스에 놓은 호기가 설비 마스터 탭 저장에서 「캔버스 밖」으로 막히지 않게."""
    return {**stored, **pending_floor_canvases()}


@dataclass(frozen=True)
class PendingFabLayout:
    """저장 안 한 FAB 전체 배치. 바꾼 쪽만 든다(None 은 저장값 그대로). `base` 는 첫 대기분이 본
    저장값(캔버스|None, 요소 지문)이다."""

    canvas: CanvasSize | None
    marks: tuple[FabLayoutMark, ...] | None
    base: FabLayoutBase


def pending_fab_layout() -> PendingFabLayout | None:
    """Space FAB 편집기에서 적용했지만 아직 저장하지 않은 FAB 전체 배치."""
    value = st.session_state.get(PENDING_FAB_KEY)
    if not isinstance(value, dict):
        return None
    return PendingFabLayout(canvas=value["canvas"], marks=value["marks"], base=value["base"])


def stage_fab_layout(
    canvas: CanvasSize | None,
    marks: tuple[FabLayoutMark, ...] | None,
    *,
    base: FabLayoutBase,
) -> None:
    """미저장 FAB 배치를 둔다. 둘 다 None 이면 대기분을 지운다(저장값과 같아졌을 때). `base` 는
    첫 대기분의 것만 남긴다 — 그 뒤의 적용은 이 세션이 쌓은 것이라 남의 변경이 아니다."""
    current = pending_fab_layout()
    if canvas is None and marks is None:
        st.session_state.pop(PENDING_FAB_KEY, None)
        return
    st.session_state[PENDING_FAB_KEY] = {
        "canvas": canvas,
        "marks": marks,
        "base": current.base if current is not None else base,
    }


def rebase_fab_canvas(canvas: CanvasSize | None) -> None:
    """이 세션이 팝업으로 FAB 캔버스를 방금 저장·삭제했다. 대기분의 캔버스는 버리고(팝업 값이
    정본이다), 본 저장값의 **캔버스 부분만** 새 값으로 바꾼다 — 요소 지문은 처음 본 값 그대로라
    그 사이 남이 바꾼 요소는 여전히 저장 때 걸린다."""
    current = pending_fab_layout()
    if current is None:
        return
    if current.marks is None:
        st.session_state.pop(PENDING_FAB_KEY, None)
        return
    st.session_state[PENDING_FAB_KEY] = {
        "canvas": None,
        "marks": current.marks,
        "base": (canvas, current.base[1]),
    }


def save_pending_fab_layout(repository: DuckDBEquipmentRepository) -> bool:
    """미저장 FAB 배치를 쓴다(설비 리비전 없음). 썼으면 대기분·도면 캐시를 비우고 True."""
    pending = pending_fab_layout()
    if pending is None:
        return False
    wrote = repository.save_fab_layout(
        canvas=pending.canvas,
        marks=(
            [mark.editor_payload() for mark in pending.marks] if pending.marks is not None else None
        ),
        base=pending.base,
    )
    st.session_state.pop(PENDING_FAB_KEY, None)
    if wrote:
        clear_floor_layout_cache()
    return wrote


FAB_SAVED_MESSAGE = "S.PKG FAB 전체 배치를 저장했습니다. 설비 리비전과 무관한 현행값입니다."
NOTHING_SAVED_MESSAGE = "바뀐 내용이 없어 저장하지 않았습니다."
# FAB 저장이 거부됐을 때 빠져나갈 곳. 가용설비 현황 설비 마스터 탭 저장도 FAB 대기분을 쓰므로 그
# 화면에서도 이 문구가 뜬다 — FAB 대기분만 버리는 단추는 Space 현황에 있다.
FAB_DISCARD_HINT = (
    " FAB 대기분만 버리려면 Space 현황의 `저장 안 한 배치 변경` › `버리기` › "
    "`FAB 배치만 버리기` 를 누르세요."
)


def save_equipment_buffer(
    repository: DuckDBEquipmentRepository,
    frames: Frames | None,
    note: str,
    *,
    basis: EquipmentSaveBasis | None = None,
    fields: EquipmentSaveFields | None = None,
    removal_confirmed: RemovalElsewhere | None = None,
) -> str:
    """편집본(세 표)과 미저장 층 캔버스·도면 요소를 **한 트랜잭션**에 저장하고 알림 문구를 돌려준다.

    설비 마스터 탭 「리비전 저장」·Space 저장·사이드바 설비 시나리오 팝업 저장이 이 한 곳을
    탄다(저장소 `save_equipment` — 공통 대장·설비 시나리오 일정 가운데 **바뀐 쪽만** 쓴다. 둘 다
    그대로면 층 값만 쓰거나 아무것도 쓰지 않는다). `basis` 는 저장할 설비 시나리오와 화면이 본
    공식 번호(페이지가 세션에서 만든다 — 없으면 편집본이 나온 시나리오, 그것도 없으면 공식
    시나리오), `fields` 는 저장 칸 값(없으면 기본값)이다. 예시 행 가드는 repository 에 없으므로
    여기서 건다. 성공하면 캐시와 편집본을 모두 비운다.

    미저장 **FAB 전체 배치**는 설비 리비전과 무관한 별도 쓰기다(`save_pending_fab_layout`). 설비
    편집보다 **먼저** 쓴다 — 설비 저장이 막혀도 FAB 는 저장된 채 남고(그 사실을 오류 문구에 적는다),
    반대 순서면 설비 저장 뒤 편집본을 비우면서 FAB 대기분까지 잃는다. FAB 가 거부돼도(남이 먼저
    저장) 설비 저장은 그대로 하고, FAB 대기분은 남긴 채 두 결과를 함께 적은 `ValueError` 를 낸다.
    `frames` 가 None 이면(설비 저장본이 없어 대조할 출발 리비전이 없는 화면) FAB 대기분만 쓴다.

    `removal_confirmed` 는 설비 마스터 탭 저장 칸의 확인 체크로 「다른 설비 시나리오에서도 일정이
    빠지는 것을 알고 지운다」 고 확인한 그 글의 재료다(`RemovalElsewhere` — 호기와 그 일정이 빠질
    시나리오). 저장 때 다시 센 삭제가 그것으로 덮이지 않으면(확인하지 않은 호기, 본 뒤 그 호기
    일정이 든 시나리오가 늘어남) 저장하지 않는다 — 그 체크가 없는 자리(Space·팝업)의 저장도 같은
    까닭으로 막힌다.
    """
    if frames is None:
        return FAB_SAVED_MESSAGE if save_pending_fab_layout(repository) else NOTHING_SAVED_MESSAGE
    drafts = unsaved_grid_drafts(frames)
    if drafts:
        # 칸 초안은 편집본 밖이다 — 이 저장 길(사이드바 팝업·Space 배치 저장)이 모른 채 저장하면
        # 저장 성공이 초안을 지워 친 글이 말없이 사라진다(개편 명세 5-3).
        raise ValueError(
            f"설비 마스터 표에 못 읽은 값 {drafts:,}칸이 남아 있어 저장하지 않았습니다 — 가용설비 "
            "현황 설비 마스터에서 고치거나 되돌리세요."
        )
    leftovers = _example_baseline_rows(frames[0])
    if not leftovers.empty:
        raise ValueError(
            f"기존 보유대수에 지우지 않은 예시 행이 {len(leftovers)}건 남아 있습니다. "
            "실제 값으로 고치거나 지운 뒤 저장하세요."
        )
    # FAB 는 별도 쓰기라 그 거부(남이 먼저 저장·검증 실패)가 설비 저장을 막지 않는다. 거부된 FAB
    # 대기분은 남긴다 — 설비 저장이 편집본을 비우면서 대기분도 지우므로 끝나고 다시 얹는다.
    fab_pending = pending_fab_layout()
    fab_error: str | None = None
    try:
        fab_saved = save_pending_fab_layout(repository)
    except ValueError as exc:
        fab_saved, fab_error = False, str(exc)
    try:
        message = _save_equipment_frames(
            repository,
            frames,
            note,
            basis=basis,
            fields=fields,
            fab_saved=fab_saved,
            removal_confirmed=removal_confirmed,
        )
    except BOOTSTRAP_ERRORS as exc:
        if not (fab_saved or fab_error):
            raise
        reason = bootstrap_error_message(exc, database_paths=(repository.database_path,))
        if fab_saved:
            raise ValueError(
                f"S.PKG FAB 전체 배치는 저장했지만 설비·층 배치는 저장하지 못했습니다: {reason}"
            ) from exc
        raise ValueError(
            f"설비·층 배치를 저장하지 못했습니다: {reason} S.PKG FAB 전체 배치도 저장하지 "
            f"못했습니다: {fab_error}{FAB_DISCARD_HINT}"
        ) from exc
    finally:
        if fab_error is not None and fab_pending is not None:
            stage_fab_layout(fab_pending.canvas, fab_pending.marks, base=fab_pending.base)
    if fab_error is None:
        return message
    if message == NOTHING_SAVED_MESSAGE:
        raise ValueError(f"{fab_error}{FAB_DISCARD_HINT}")
    raise ValueError(
        f"S.PKG FAB 전체 배치만 저장하지 못했습니다(이 화면의 FAB 대기분은 남겼습니다): "
        f"{fab_error}{FAB_DISCARD_HINT} 설비 쪽은 저장했습니다 — {message}"
    )


def unsaved_grid_drafts(frames: Frames) -> int:
    """편집본(`frames`)의 살아 있는 행에 남은 설비 마스터 표 칸 초안 수. 없는 행의 초안(그 사이
    Space 가 호기를 지움·이름을 바꾼 새 호기)은 세지 않는다 — 표가 다음 회차에 걷는다."""
    overlay = grid_overlay()
    if not overlay:
        return 0
    index = grid_index(frames[1], _saved_master(), pending_unit_renames().units)
    return len(prune_overlay(overlay, index))


def _save_equipment_frames(
    repository: DuckDBEquipmentRepository,
    frames: Frames,
    note: str,
    *,
    basis: EquipmentSaveBasis | None,
    fields: EquipmentSaveFields | None,
    fab_saved: bool,
    removal_confirmed: RemovalElsewhere | None = None,
) -> str:
    """`save_equipment_buffer` 의 설비 쪽(공통·일정 + 층 캔버스·요소 한 트랜잭션).

    설비 마스터를 쓰는 모든 저장(설비 마스터 탭 「리비전 저장」 — 표·붙여넣기·CSV·작은 편집표 —,
    Space 배치 저장, 팝업 저장)이 이 한 곳을 지나므로 모듈 묶음 좌표·크기
    검사(`saved_master_violations` — 바뀐 묶음은 묶음 범위의 바둑판이어야 한다, 2026-10-23 사용자 답
    「막자」)도 여기서 한다."""
    violations = saved_master_violations(frames[1])
    if violations:
        raise ValueError(module_layout_message(violations))
    base = st.session_state.get(_BASE_KEY)
    if not isinstance(base, dict):
        raise ValueError("편집본이 아직 서지 않아 저장하지 않았습니다. 화면을 다시 불러오세요.")
    canvases = pending_floor_canvases()
    marks = {
        key: [mark.editor_payload() for mark in staged]
        for key, staged in pending_floor_marks().items()
    }
    labels = pending_floor_group_labels()
    chosen = fields if fields is not None else EquipmentSaveFields()
    scenario_id = (
        basis.equipment_scenario_id
        if basis is not None
        else (
            str(base["scenario"])
            if isinstance(base.get("scenario"), str)
            else repository.official_scenario_id()
        )
    )
    if scenario_id is None:
        raise ValueError("설비 시나리오가 없어 설비 마스터를 저장하지 않았습니다.")
    # 지운 호기가 다른 설비 시나리오에도 일정이 있으면 확인한 것만 지운다(설계 11-2 6단계).
    removal = removals_elsewhere(
        frames, database_path=str(repository.database_path), scenario_id=scenario_id
    )
    if removal is not None and not removal.covered_by(removal_confirmed):
        raise ValueError(removal.refusal())
    schedule_id = base.get("schedule")
    renames = pending_unit_renames()
    # 편집본이 나온 두 리비전과 층마다 본 저장값을 함께 넘긴다. 그 사이 다른 사람이 저장했으면
    # 저장소가 쓰기 잠금 안에서 거부한다 — 옛 편집이 남의 저장을 조용히 되돌리지 않게.
    request = EquipmentSaveRequest(
        baseline=frames[0],
        equipment=frames[1],
        downtime=frames[2],
        equipment_scenario_id=scenario_id,
        base_common_revision_id=str(base["common"]),
        base_schedule_revision_id=schedule_id if isinstance(schedule_id, str) else None,
        renames=dict(renames.units),
        group_renames=dict(renames.groups),
        note=note,
        saved_by=chosen.saved_by,
        propagate_new_units=chosen.propagate_new_units,
        propagate_new_downtime=chosen.propagate_new_downtime,
        publish_official=chosen.publish_official,
        expected_release_no=basis.release_no if basis is not None else None,
        # 「새 호기」 칸에서 넣은 호기는 그 칸의 체크가 저장 칸 체크보다 이긴다(D8) — 어느 저장
        # 길(설비 마스터 탭·사이드바 팝업·Space)이든 같은 편집본이라 같다.
        propagate_units=chosen_new_units(frames, default=chosen.propagate_new_units),
        floor_canvases=canvases,
        floor_marks=marks,
        floor_layout_bases=pending_floor_bases(),
        floor_group_labels=labels,
        expected_layout_role=_layout_role_of(
            frames[1], renames.units, floor_values=bool(canvases or marks or labels), basis=basis
        ),
    )
    result = repository.save_equipment(request)
    fab = " S.PKG FAB 전체 배치도 저장했습니다." if fab_saved else ""
    # 문구는 대기분이 아니라 **저장 결과**로 만든다(검토 F18b) — 가정 역할의 도면 요소·Main 설비명
    # 위치는 층 현행값이 아니라 그 시나리오 새 리비전의 배치 차이로 갔다.
    floor_layouts = (
        floor_layout_words(canvases, marks, labels) if result.floor_values_written else ""
    )
    if not result.wrote_revision and not result.floor_values_written and result.release_no is None:
        # 설비 쪽은 아무것도 쓰지 않았다. 편집본·변경 메모·선택을 그대로 둔다.
        return FAB_SAVED_MESSAGE if fab_saved else NOTHING_SAVED_MESSAGE
    clear_equipment_snapshot_cache()
    if result.floor_values_written:
        clear_floor_layout_cache()
    # 저장한 이름 바꿈은 이제 저장본 이름이다 — 설비 마스터 탭을 그리지 않은 채(Space 에서)
    # 저장했으면 목록 필터가 따라갈 지도가 아직 남아 있으니 편집본과 함께 버리지 않는다(버리면
    # 다음 설비 마스터 탭 회차에 옛 이름이 선택지 밖이라 필터가 「전체」 로 돌아간다).
    # 버리기·남의 저장은 이름이 돌아가므로 버린다.
    followed = st.session_state.get(FOLLOWED_FILTERS_KEY)
    reset_equipment_drafts()
    if followed:
        st.session_state[FOLLOWED_FILTERS_KEY] = followed
    if result.schedule is not None:
        st.session_state[SAVED_SCHEDULE_KEY] = {
            "scenario_id": result.schedule.equipment_scenario_id,
            "schedule_revision_id": result.schedule.schedule_revision_id,
        }
    layouts = f" {floor_layouts}도 함께 저장했습니다." if floor_layouts else ""
    if not result.wrote_revision:
        if not floor_layouts:
            return f"{NOTHING_SAVED_MESSAGE}{fab}"
        return f"설비 마스터가 바뀌지 않아 새 리비전 없이 {floor_layouts}만 저장했습니다.{fab}"
    name = basis.scenario_name if basis is not None else None
    return save_result_message(result, scenario_name=name) + layouts + fab


def _layout_role_of(
    master: pd.DataFrame,
    renames: Mapping[str, str],
    *,
    floor_values: bool,
    basis: EquipmentSaveBasis | None,
) -> str | None:
    """저장이 저장소에 넘기는 대조 역할(설계 6-2) — 배치 편집을 적용할 때 찍은 역할
    (`stamped_layout_role`), 없으면 편집본에 배치 편집(있던 호기 배치 칸·새 호기 자리)이나 층 값
    대기분이 있을 때 지금 세션의 역할(공식 시나리오 → "official", 가정 → "overlay"), 배치를
    건드리지 않았으면 None(대조하지 않는다).

    찍힌 역할과 쓰기 잠금 안의 역할이 다르면(그 사이 남의 발행) 저장소가
    `EquipmentLayoutRoleChanged`
    로 막는다 — 공식 배치에 들어갈 편집이 가정 배치 차이로(또는 그 반대로) 조용히 들어가지 않게."""
    stamped = stamped_layout_role()
    if stamped is not None:
        return stamped
    if floor_values or layout_edits(master, _saved_master(), renames):
        return "overlay" if basis is not None and not basis.official_scenario else "official"
    return None


# 지운 호기와 새 호기가 한 저장에 함께 있을 때 결과 알림 꼬리(설계 11-4).
RENAME_INSTEAD_HINT = (
    "이름만 바꾸려면 설비 마스터 호기 상세의 설비명 칸이나 Space 편집기 「이름 바꾸기」 를 쓰세요 "
    "— 지우고 새로 넣으면 다른 설비 시나리오의 그 호기 일정이 빠집니다."
)


def save_result_message(result: EquipmentSaveResult, *, scenario_name: str | None) -> str:
    """저장 결과 알림 — 공통 rN · 시나리오 rN · 함께 넣은 목록 · 발행 · 지운 호기(설계 6-3·6-4)."""
    written: list[str] = []
    if result.common is not None:
        written.append(f"공통 대장 r{result.common.revision_no}")
    if result.schedule is not None:
        label = f"「{scenario_name}」 " if scenario_name else "설비 시나리오 일정 "
        written.append(f"{label}r{result.schedule.revision_no}")
    sentences = [
        f"설비 데이터를 저장했습니다 — {' · '.join(written)}."
        if written
        else "설비 데이터를 저장했습니다."
    ]
    if result.forced_common:
        sentences.append(
            "설비 시나리오로 옮긴 뒤 첫 저장이라 공통 대장도 새 리비전으로 함께 저장했습니다."
        )
    propagated = [item for item in result.propagated if item.revision_no is not None]
    if propagated:
        sentences.append(
            "함께 넣음: " + ", ".join(_propagated_words(item) for item in propagated) + "."
        )
    skipped = sum(item.skipped for item in result.propagated)
    if skipped:
        sentences.append(
            f"비가동 {skipped:,}건은 받는 시나리오에 그 호기 일정이 없거나 이미 같은 비가동이 있어 "
            "넣지 않았습니다."
        )
    if result.layout_overlay_written:
        sentences.append(overlay_saved_sentence(result, scenario_name=scenario_name))
    if result.release_no is not None:
        released = f"공식 v{result.release_no}"
        sentences.append(f"{with_direction_particle(released)} 발행했습니다.")
    elif result.release_withheld:
        sentences.append(
            "공식 설비 시나리오에 발행하지 않은 더 새 리비전이 있어 공식 발행은 하지 않았습니다 — "
            "공식 발행은 시나리오 관리 › 설비 시나리오에서 하세요."
        )
    if result.removed_units:
        removed = f"지운 호기 {len(result.removed_units):,}대는 모든 설비 시나리오에서 빠졌습니다."
        if result.new_units:
            # 붙여넣기·CSV·설비 마스터 탭 설비명 칸 고침은 설비명이 키라 이름 바꾸기가 아니다
            # (지운 + 새 호기).
            removed += f" {RENAME_INSTEAD_HINT}"
        sentences.append(removed)
    sentences.append(
        "가용설비와 필요 단축 일정에 반영되고, Space 현황은 고른 설비 시나리오의 배치입니다."
    )
    return " ".join(sentences)


def overlay_saved_sentence(result: EquipmentSaveResult, *, scenario_name: str | None) -> str:
    """가정 배치를 저장한 한 문장 — 그 리비전의 공식과 다른 호기 · 도면 요소 · Main 설비명 위치 수
    (0 인 것은 뺀다, Space 머리 알림과 같은 꼴 — 설계 8-2). 요소·이름표만 옮긴 저장도 무엇이
    저장됐는지 말한다. 모두 0 이면 이제 공식 배치와 같다는 말이다(차이를 모두 걷은 저장)."""
    place = f"「{scenario_name}」" if scenario_name else "이 설비 시나리오"
    parts = []
    if result.layout_overlay_units:
        parts.append(f"공식과 다른 호기 {result.layout_overlay_units:,}대")
    if result.layout_overlay_marks:
        parts.append(f"도면 요소 {result.layout_overlay_marks:,}개")
    if result.layout_overlay_labels:
        parts.append(f"Main 설비명 위치 {result.layout_overlay_labels:,}개")
    if not parts:
        return f"{place}의 가정 배치를 저장했습니다 — 이제 공식 배치와 같습니다."
    return (
        f"{place}의 가정 배치를 저장했습니다({' · '.join(parts)}) — 공식 배치는 바뀌지 않았습니다."
    )


def _propagated_words(item: PropagatedRevision) -> str:
    """함께 넣은 시나리오 한 줄 — 「셋업 실무」 r4(호기 2대 · 비가동 1건)."""
    parts = []
    if item.unit_count:
        parts.append(f"호기 {item.unit_count:,}대")
    if item.downtime:
        parts.append(f"비가동 {len(item.downtime):,}건")
    detail = f"({' · '.join(parts)})" if parts else ""
    return f"「{item.scenario_name}」 r{item.revision_no}{detail}"


def floor_layout_words(canvases: object, marks: object, labels: object) -> str:
    """저장 알림에 적을 층 현행값 — 대기분이 있는 것만 차례대로(층 캔버스·도면 요소·Main 설비명
    위치). 하나도 없으면 빈 글자."""
    parts = (("층 캔버스", canvases), ("도면 요소", marks), ("Main 설비명 위치", labels))
    return "·".join(word for word, pending in parts if pending)


def current_data_file_name(
    table_slug: str,
    *,
    latest_snapshot: EquipmentSnapshot | None,
    edited: bool,
    today: date,
    scenario_name: str | None = None,
) -> str:
    """`equipment_master_운영_일정_r3_c5_20260924.csv` 꼴. 무엇을 기준으로 한 파일인지 이름이
    말한다.

    월 범위가 없는 표라 기준 정보 쪽(`RQ_UPEH_<시작>_<끝>.csv`)처럼 범위를 담을 수 없다.
    대신 **어느 저장본에서 출발했는지**(설비 시나리오 이름 · 그 일정 리비전 `r3` · 공통 대장
    `c5`, 저장본이 없으면 `r0`)와 **언제 받았는지**를 담고, 저장하지 않은 변경이 섞여 있으면
    `_edited` 를 붙인다 — 같은 날 받은 두 파일이 어느 시나리오·저장본인지, 편집본인지 이름만 보고
    갈리게 하기 위해서다. 시나리오 이름의 파일 이름에 못 쓰는 글자·빈칸은 `_` 로 바꾼다.
    """
    suffix = "_edited" if edited else ""
    if latest_snapshot is None:
        return f"{table_slug}_r0{suffix}_{today:%Y%m%d}.csv"
    scenario = f"_{_file_name_part(scenario_name)}" if scenario_name else ""
    schedule = latest_snapshot.schedule
    schedule_no = schedule.revision_no if schedule is not None else 0
    common_no = latest_snapshot.revision.revision_no
    return f"{table_slug}{scenario}_r{schedule_no}_c{common_no}{suffix}_{today:%Y%m%d}.csv"


def _file_name_part(text: str) -> str:
    """파일 이름 한 토막 — 경로·예약 글자와 빈칸을 `_` 로, 겹친 `_` 는 하나로."""
    cleaned = "".join("_" if char in '\\/:*?"<>|' or char.isspace() else char for char in text)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "scenario"


def _saved_basis_words(snapshot: EquipmentSnapshot, scenario_name: str | None) -> str:
    """「저장본 r3 · 「운영 일정」 · 공통 대장 r5」 — 편집본이 나온 저장본 쌍."""
    schedule = snapshot.schedule
    head = f"저장본 r{schedule.revision_no}" if schedule is not None else "저장본 일정 없음"
    name = f" · 「{scenario_name}」" if scenario_name else ""
    return f"{head}{name} · 공통 대장 r{snapshot.revision.revision_no}"


def _render_current_data_downloads(
    frames: Frames,
    *,
    saved: Frames,
    latest_snapshot: EquipmentSnapshot | None,
    database_path: str,
    scenario_name: str | None,
    edit_note: str,
    memo_key: tuple[object, ...],
) -> None:
    """세 표의 **현재 데이터**를 내려받는 단추 셋 — 설비 마스터 탭 「내려받기」 팝오버의 양식 단추
    아래에 같은 차례로 선다. `edit_note` 는 편집본이 언제 이 파일에 드는지 말하는 캡션 글이다.
    내보낼 바이트와 「편집본」 판정은 `memo_key`(편집본 세대·출발점·저장본 토큰) 열쇠로 세션
    메모(`GRID_MEMO_KEY`)에 한 번만 낸다 — 고친 편집본은 회차마다 직렬화해 합성 3천 대에 수십 ms 가
    들었다(개편 명세 8장).

    내보내는 것은 **편집 버퍼**(설비 마스터 표가 보여 주는 편집본)이지 저장된 리비전이 아니다.
    사용자가 「지금 보는 것」을 받아야 Excel 에서 고쳐 되돌리는 왕복이 맞아떨어지고, 저장본과 같을
    때는 둘이 같은 파일이다. 저장본과 다른지는 **내보낼 바이트를 비교**해 판단한다 — 파일이 달라질
    때만 「편집본」이다.

    바이트는 표마다 **저장 리비전과 같은 표면 리비전 캐시**(`load_equipment_csv_payloads`)에서
    꺼낸다 — 고친 것이 없을 때 여섯 번의 직렬화(내보낼 셋 + 견줄 셋)를 치르지 않는다. 같은지는
    `DataFrame.equals`(값·dtype·차례)로 가르고, 다르면 직렬화해 바이트로 견준다 — dtype 만 달라 같은
    파일이 되는 경우도 「편집본」으로 잘못 적지 않는다. 지연 생성(콜러블)은 쓰지 않는다(TODO 결정
    기록).

    내보내기는 읽기만 한다. 버퍼·미리보기·저장 상태를 건드리지 않고, 파일은 브라우저
    다운로드로만 나간다(저장소 안에 쓰지 않는다).
    """
    buffered_baseline, buffered_equipment, buffered_downtime = frames
    saved_baseline, saved_equipment, saved_downtime = saved
    serializers = (equipment_csv_bytes, baseline_csv_bytes, downtime_csv_bytes)
    stored: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None = None
    stored_bytes: tuple[bytes, bytes, bytes] | None = None
    if latest_snapshot is not None:
        stored = (latest_snapshot.equipment, latest_snapshot.baseline, latest_snapshot.downtime)
        stored_bytes = load_equipment_csv_payloads(
            database_path,
            latest_snapshot.revision.revision_id,
            latest_snapshot.schedule.schedule_revision_id
            if latest_snapshot.schedule is not None
            else None,
        )

    def table_bytes(position: int, frame: pd.DataFrame) -> bytes:
        if stored is not None and stored_bytes is not None and frame.equals(stored[position]):
            return stored_bytes[position]
        return serializers[position](frame)

    memo = st.session_state.get(GRID_MEMO_KEY)
    cached = memo.get("downloads") if isinstance(memo, dict) else None
    if (
        isinstance(memo, dict)
        and memo.get("downloads_key") == memo_key
        and isinstance(cached, tuple)
        and len(cached) == 2
    ):
        payloads, edited = cached
    else:
        payloads = tuple(
            table_bytes(position, frame)
            for position, frame in enumerate(
                (buffered_equipment, buffered_baseline, buffered_downtime)
            )
        )
        edited = payloads != tuple(
            table_bytes(position, frame)
            for position, frame in enumerate((saved_equipment, saved_baseline, saved_downtime))
        )
        stored_memo = dict(memo) if isinstance(memo, dict) else {}
        stored_memo["downloads_key"] = memo_key
        stored_memo["downloads"] = (payloads, edited)
        st.session_state[GRID_MEMO_KEY] = stored_memo
    basis = _saved_basis_words(latest_snapshot, scenario_name) if latest_snapshot else "저장본 없음"
    state = "저장하지 않은 변경 포함" if edited else "저장본과 같음"
    st.caption(
        f"현재 데이터 · {basis} · {state}. {edit_note} 고치지 않고 그대로 붙여넣어도 통과합니다."
    )
    today = date.today()
    for column, label, payload, slug, key, frame in zip(
        st.columns(3),
        _TARGETS,
        payloads,
        ("equipment_master", "equipment_baseline", "equipment_downtime"),
        (
            "equipment_master_current_download_v1",
            "equipment_baseline_current_download_v1",
            "equipment_downtime_current_download_v1",
        ),
        (buffered_equipment, buffered_baseline, buffered_downtime),
        strict=True,
    ):
        with column:
            # 빈 표도 막지 않는다. 헤더만 든 파일이 곧 정확한 컬럼 차례의 양식이고, 그대로
            # 붙여넣으면 0행으로 읽혀 아무것도 바꾸지 않는다.
            render_csv_download(
                data=payload,
                file_name=current_data_file_name(
                    slug,
                    latest_snapshot=latest_snapshot,
                    edited=edited,
                    today=today,
                    scenario_name=scenario_name,
                ),
                key=key,
                label=f"{label} 현재 데이터 · {len(frame):,}행",
            )


def _example_baseline_rows(baseline: pd.DataFrame) -> pd.DataFrame:
    """손대지 않은 예시 행. 저장 가드가 잡는 것과 **정확히 같은 두 함수**로 센다.

    화면이 미리 알리는 건수와 저장이 막는 건수가 갈리면 「지웠는데도 막힌다」가 된다.
    """
    return pd.concat(
        [untouched_sample_baseline_rows(baseline), untouched_template_baseline_rows(baseline)]
    )


def _without_example_rows(baseline: pd.DataFrame) -> pd.DataFrame:
    leftovers = _example_baseline_rows(baseline)
    if leftovers.empty:
        return baseline
    return baseline.loc[~baseline.index.isin(leftovers.index)].reset_index(drop=True)


def _example_row_count(frames: Frames, pending: object) -> int:
    """저장이 막을 예시 행 수.

    검토 후보가 있으면 **그쪽만** 센다. `candidate[0]` 은 버퍼를 merge 한 결과라 버퍼의
    예시 행을 이미 품고 있어, 둘을 더하면 같은 행을 두 번 세고 지운 뒤에도 수가 남는다.
    """
    baseline = pending.candidate[0] if isinstance(pending, ImportReview) else frames[0]
    return len(_example_baseline_rows(baseline))


def _drop_example_rows(*, floor_canvases: FloorCanvasMap) -> None:
    """예시 행을 편집본과 검토 후보에서 **함께** 뺀다.

    후보에서만 빼면 되돌아온다 — 원문이 그대로라 재검토(`matches()` 가 깨질 때)가 원문을
    다시 읽고 예시 줄을 또 넣는다. 그래서 세션 플래그를 남겨 이후의 모든
    `build_import_review` 가 merge 전에 같은 행을 뺀 채 돌게 한다.

    **저장 검증은 건드리지 않는다.** 이것은 저장을 눌러야 알던 것을 누르기 전에 말하고
    한 번에 지우는 길일 뿐이다. 콜백은 위젯이 만들어지기 전에 돌므로 editor 키를 비우는
    것이 안전하고, `st.rerun` 은 부르지 않는다 — `on_click` 이 이미 한 회차를 돌린다.
    """
    frames: Frames = st.session_state[BUFFER_KEY]
    pending = st.session_state.get(PREVIEW_KEY)
    removed = _example_row_count(frames, pending)
    st.session_state[DROP_EXAMPLE_ROWS_KEY] = True
    _remember_edits((_without_example_rows(frames[0]), frames[1], frames[2]))
    if isinstance(pending, ImportReview):
        try:
            st.session_state[PREVIEW_KEY] = build_import_review(
                pending.target,
                pending.payload,
                st.session_state[BUFFER_KEY],
                floor_canvases=floor_canvases,
                drop_examples=True,
            )
        except BOOTSTRAP_ERRORS as exc:
            st.session_state.pop(PREVIEW_KEY, None)
            st.session_state[_ERROR_KEY] = str(exc)
            return
    st.session_state[_NOTICE_KEY] = (
        f"예시 행 {removed:,}건을 빼고 검토했습니다. 저장 검증은 그대로 돕니다."
    )


def build_import_review(
    target: str,
    payload: str | bytes,
    source: Frames,
    *,
    floor_canvases: FloorCanvasMap,
    drop_examples: bool = False,
    layout_role: str | None = None,
    paste_layout: bool = True,
    official_places: Mapping[str, Place] | None = None,
) -> ImportReview:
    """기존 입력 서비스를 통해 원문을 검증하고 다른 표를 포함한 저장 후보를 만든다.

    `drop_examples` 는 「예시 행 지우기」를 누른 뒤의 재검토다. 원문은 그대로 두고 merge
    **전에** 예시 줄만 빼므로 지운 행이 재검토에서 되살아나지 않는다.

    설비 마스터의 배치 일곱 칸(설비 시나리오 2단계 S3 — Q2): `layout_role` 이 "overlay"(가정 설비
    시나리오)이고 `paste_layout` 이 거짓(「배치 칸도 붙여넣기」 끔 — 기본)이면 있던 호기의 배치
    칸은 지금 값을 두고 새 호기의 배치 칸만 받는다. 켜면 「가정 배치 n대가 바뀝니다(그 가운데 m대는
    공식 자리로 돌아가 차이가 지워집니다)」 — `official_places` 는 설비명 → 공식 일곱 칸(얹은 값이
    공식과 다른 호기만, `EquipmentSnapshot.layout_official_places`). "official" 이면 「공식 배치 k칸
    (호기 n대)이 바뀝니다」 를 경고한다.
    """
    baseline, equipment, downtime = source
    notices: list[str] = []
    cautions: list[str] = []
    if target == "설비 마스터":
        # 붙여넣은 열만 바꾼다(2026-10-08 사용자 요청). 붙여넣지 않은 열은 편집본 값으로 채운
        # 38컬럼 표가 오므로 아래 미리보기·병합·병합 뒤 전체 검증은 전체 열 붙여넣기와 같은 길이다.
        try:
            paste = read_equipment_update(
                payload, equipment, floor_canvases=floor_canvases, notices=notices
            )
        except UnitGroupCollisionError as exc:
            # 붙여넣은 행끼리 부딪혔다. 다만 붙여넣지 않은 열(Main 설비 등)은 편집본 값이라
            # 편집본에도 있는 이름은 (붙여넣기·편집본)으로 적는다 — 붙여넣을 표에서만 빼면
            # 다시 막힌다.
            raise ValueError(
                unit_group_collision_message(
                    exc.collisions,
                    pasted=_collision_names(exc),
                    existing=_equipment_names(equipment),
                )
            ) from exc
        incoming = paste.rows
        layout_pasted = [column for column in SCENARIO_LAYOUT_COLUMNS if column in paste.columns]
        if layout_pasted and layout_role in ("official", "overlay"):
            incoming, layout_note = _paste_layout_review(
                equipment,
                incoming,
                role=layout_role,
                paste_layout=paste_layout,
                official_places=official_places or {},
            )
            if layout_note is not None:
                (notices if layout_role == "overlay" and not paste_layout else cautions).append(
                    layout_note
                )
        changes = build_equipment_import_preview(equipment, incoming, columns=paste.columns)
        try:
            # 저장 때만 도는 실적 검사도 미리 한다 — 저장을 눌러야 알던 것을 미리보기에서 말한다.
            merged = merge_equipment_rows(
                equipment, incoming, floor_canvases=floor_canvases, today=date.today()
            )
        except UnitGroupCollisionError as exc:
            # 검증은 병합된 표만 본다. 이름마다 붙여넣기·편집본 어디에 있었는지 붙여 다시 알린다
            # — 붙여넣기는 설비명 기준 upsert 라 편집본 쪽 행을 지우지 못한다.
            raise ValueError(
                unit_group_collision_message(
                    exc.collisions,
                    pasted=_equipment_names(incoming),
                    existing=_equipment_names(equipment),
                )
            ) from exc
        equipment = merged
        downtime = merge_downtime_rows(downtime, empty_downtime_schedule(), equipment=equipment)
        baseline = prepare_equipment_baseline(baseline)
        scope = _paste_scope_notice(paste, new_rows=int(changes["Import구분"].eq("신규").sum()))
        if scope is not None:
            notices.append(scope)
        if paste.cleared_cells:
            cautions.append(
                f"붙여넣은 빈칸이 기존 값 {paste.cleared_cells:,}칸을 지웁니다 — 「변경내용」의 "
                "(빈 값)을 확인하세요. 지우지 않으려면 그 칸을 채우거나 그 열을 빼고 다시 "
                "붙여넣으세요."
            )
        if paste.case_variants:
            cautions.append(
                f"대소문자만 다른 기존 호기가 있는데 새 호기로 더합니다: "
                f"{describe_case_variants(paste.case_variants)}. 같은 설비면 설비명을 기존 표기 "
                "그대로 적어 다시 붙여넣으세요 — Space 이름 바꾸기는 대소문자·앞뒤 공백을 무시하고 "
                "겹친 이름을 막습니다."
            )
    elif target == "기존 보유대수":
        incoming = (
            read_baseline_csv(payload)
            if isinstance(payload, bytes)
            else read_baseline_clipboard(payload)
        )
        if drop_examples:
            incoming = _without_example_rows(incoming)
        changes = build_baseline_import_preview(baseline, incoming)
        baseline = merge_baseline_rows(baseline, incoming)
        equipment = prepare_equipment_master(equipment, floor_canvases=floor_canvases)
        downtime = prepare_downtime_for_prepared_equipment(downtime, equipment)
    elif target == "비가동 일정":
        equipment = prepare_equipment_master(equipment, floor_canvases=floor_canvases)
        incoming = (
            read_downtime_csv(payload, equipment=equipment)
            if isinstance(payload, bytes)
            else read_downtime_clipboard(payload, equipment=equipment)
        )
        changes = build_downtime_import_preview(downtime, incoming)
        downtime = merge_downtime_rows(downtime, incoming, equipment=equipment)
        baseline = prepare_equipment_baseline(baseline)
    else:
        raise ValueError("등록할 표를 다시 선택하세요.")
    return ImportReview(
        target,
        payload,
        _copy_frames(source),
        (baseline, equipment, downtime),
        changes,
        tuple(notices),
        tuple(cautions),
    )


def _name_places(frame: pd.DataFrame) -> dict[str, tuple[int, Place]]:
    """설비명(앞뒤 공백을 뗌) → (첫 행의 자리, 배치 일곱 칸 견줄 값). 빈 설비명은 뺀다."""
    places: dict[str, tuple[int, Place]] = {}
    for position, record in enumerate(frame.to_dict("records")):
        row = {str(key): value for key, value in record.items()}
        name = row.get(EQUIPMENT_ID_COLUMN)
        if isinstance(name, str) and name.strip() and name.strip() not in places:
            places[name.strip()] = (position, place_of(row))
    return places


def _paste_layout_review(
    equipment: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    role: str,
    paste_layout: bool,
    official_places: Mapping[str, Place],
) -> tuple[pd.DataFrame, str | None]:
    """붙여넣기의 배치 일곱 칸 몫 — (받을 행, 한 줄). 있던 호기(편집본에 있는 설비명) 가운데 배치가
    바뀌는 것만 본다(새 호기의 배치 칸은 늘 받는다)."""
    current = _name_places(equipment)
    moved: list[tuple[int, str, Place]] = []
    for name, (position, place) in _name_places(incoming).items():
        if name in current and current[name][1] != place:
            moved.append((position, name, place))
    if not moved:
        return incoming, None
    sample = _sample_names([name for _, name, _ in moved])
    if role == "official":
        cells = sum(
            sum(1 for before, after in zip(current[name][1], place, strict=True) if before != after)
            for _, name, place in moved
        )
        return incoming, (
            f"공식 배치 {cells:,}칸(호기 {len(moved):,}대 — {sample})이 바뀝니다 — 공식 설비 "
            "시나리오의 배치는 모든 가정 설비 시나리오에서 손대지 않은 호기가 따라갑니다."
        )
    if not paste_layout:
        kept = incoming.copy()
        columns = [column for column in SCENARIO_LAYOUT_COLUMNS if column in kept.columns]
        positions = {column: list(kept.columns).index(column) for column in columns}
        for position, name, _ in moved:
            source = equipment.iloc[current[name][0]]
            for column in columns:
                kept.iat[position, positions[column]] = source[column]
        return kept, (
            f"있던 호기 {len(moved):,}대({sample})의 배치 칸은 붙여넣지 않고 지금 값을 "
            f"두었습니다 — 바꾸려면 「{PASTE_LAYOUT_LABEL}」 를 켜고 다시 미리보세요."
        )
    back = sum(
        1 for _, name, place in moved if name in official_places and place == official_places[name]
    )
    tail = f"(그 가운데 {back:,}대는 공식 자리로 돌아가 차이가 지워집니다)" if back else ""
    return incoming, (
        f"가정 배치 {len(moved):,}대({sample})가 바뀝니다{tail} — 이 설비 시나리오에만 저장되고 "
        "공식 배치는 바뀌지 않습니다."
    )


def _paste_scope_notice(paste: EquipmentPaste, *, new_rows: int) -> str | None:
    """붙여넣은 열과 그대로 두는 열을 한 줄로. 모든 열을 붙여넣었으면 말할 것이 없다."""
    kept = paste.kept_columns
    if not kept:
        return None
    pasted = [column for column in paste.columns if column != EQUIPMENT_ID_COLUMN]
    # 짧은 쪽 이름을 적는다 — 서른 개를 늘어놓으면 읽히지 않는다.
    if len(pasted) <= len(kept):
        text = (
            f"붙여넣은 열 {len(pasted)}개({' · '.join(pasted)})만 바꿉니다 — 나머지 "
            f"{len(kept)}개 열은 기존 호기의 값을 그대로 둡니다."
        )
    else:
        text = (
            f"붙여넣은 열 {len(pasted)}개만 바꿉니다 — 붙여넣지 않은 {len(kept)}개 열"
            f"({' · '.join(kept)})은 기존 호기의 값을 그대로 둡니다."
        )
    if new_rows:
        text += f" 새 호기 {new_rows:,}건은 그 열이 빈칸입니다."
    return text


def _collision_names(exc: UnitGroupCollisionError) -> set[str]:
    """충돌에 든 설비명 전부(설비 행과 모듈 행)."""
    return {*exc.collisions, *(name for modules in exc.collisions.values() for name in modules)}


def _equipment_names(frame: pd.DataFrame) -> set[str]:
    """표의 설비명(앞뒤 공백을 뗀다 — 편집본은 검증 전일 수 있다)."""
    if EQUIPMENT_ID_COLUMN not in frame.columns:
        return set()
    names = frame[EQUIPMENT_ID_COLUMN].dropna().astype(str).str.strip()
    return set(names.loc[names.ne("")])


def _editor_view(
    data: pd.DataFrame,
    *,
    key: str,
    prefix: str,
    filters: tuple[str, ...],
    locked: tuple[str, ...],
    label: str,
) -> tuple[TableView, TableView]:
    """(화면에 적용된 보기, 방금 고른 보기). 둘은 「보기 적용」 전까지 다를 수 있다."""
    requested = render_table_view_controls(
        data,
        key_prefix=prefix,
        # 보기를 바꾼 제출에도 이전 화면의 행 위치로 delta를 먼저 해석해야 한다.
        editor_key=f"{key}_requested_view",
        filter_columns=filters,
        locked_columns=locked,
        label=label,
    )
    view_key = f"{key}_applied_view"
    applied = st.session_state.get(view_key)
    if not isinstance(applied, TableView):
        applied = requested
        st.session_state[view_key] = applied
    return applied, requested


@dataclass(frozen=True)
class EditorResult:
    """작은 편집표 하나가 한 번 제출될 때의 것(`render_small_editor` → `_apply_bulk_actions`).

    `frames` 에는 **선택 칸이 없다.** 편집본·저장·미리보기 대조가 모두 이 세 표를 그대로
    쓰므로, 화면에만 있는 칸이 섞이면 대조(`ImportReview.matches`)가 조용히 어긋난다.
    """

    frames: Frames
    checked: Mapping[str, frozenset[RowKey]]
    filters: Mapping[str, Mapping[str, tuple[str, ...]]]
    action: tuple[str, str] | None


def _selection_flags(frame: pd.DataFrame, target: str, selection: frozenset[RowKey]) -> pd.Series:
    """편집표 맨 앞 선택 칸의 값 — 행의 업무 키가 고른 키 안에 드는가.

    **선택이 비면 키를 만들지 않는다.** 빈 선택에는 어떤 키도 들지 않으니 답은 모두 거짓이고, 키를
    만들려면 행마다 값을 글자로 맞추며 비가동 `시작일` 은 날짜 형식을 추정해 읽는다(사내 규모 합성
    사본 비가동 300건에서 40ms 남짓 — 샘플 관측, 행 수에 비례). 작은 편집표는 폼 밖이라 칸을 고칠
    때마다 회차가 돌므로 키를 만들면 그 비용이 그 회차마다 붙는다. dtype 은 못박는다 — 빈 표에서
    목록으로 넣으면 float 칸이 되어 체크박스와 맞지 않는다.
    """
    if selection:
        chosen = [row in selection for row in row_keys(frame, target)] or [False] * len(frame)
    else:
        chosen = [False] * len(frame)
    return pd.Series(chosen, index=frame.index, dtype="bool")


def _selectable_editor(
    original: pd.DataFrame,
    view: TableView,
    *,
    key: str,
    target: str,
    column_config: Mapping[str, Any],
    selection: frozenset[RowKey],
    locked_columns: Sequence[str] = (),
    fixed_rows: bool = False,
) -> tuple[pd.DataFrame, frozenset[RowKey]]:
    """맨 앞에 선택 칸을 붙여 편집표를 그리고, 선택 칸을 뗀 편집 결과와 고른 키를 돌려준다.

    `locked_columns` 는 고칠 수 없게 잠글 칸, `fixed_rows` 는 행 추가·삭제를 막는다(낡은 설비
    시나리오 세션 — 설계 4-2). 선택 칸은 늘 고칠 수 있다 — 낡은 세션에서 호기·비가동의 「선택 행
    삭제」 는 단추가 막는다(`_selection_buttons(delete_locked=)`).
    """
    display = view.frame.copy()
    display.insert(0, SELECT_COLUMN, _selection_flags(display, target, selection))
    result = st.data_editor(
        display,
        key=editor_widget_key(key),
        num_rows="fixed" if fixed_rows else view.row_mode,
        disabled=[column for column in locked_columns if column in display.columns],
        hide_index=True,
        width="stretch",
        # 빈 칸은 빈칸으로 보인다. 주지 않으면 Streamlit 이 결측값을 회색 "None" 글자로 그려
        # 「종료일이 비어 있으면 진행 중」 같은 작성 기준의 빈칸이 값처럼 읽힌다(2026-10-01).
        placeholder="",
        column_config={
            SELECT_COLUMN: st.column_config.CheckboxColumn(
                "선택",
                default=False,
                pinned=True,
                help="일괄 삭제할 행을 고릅니다. 필터를 걸어도 고를 수 있고, 저장되지 않습니다.",
            ),
            **column_config,
            **view.column_config,
        },
    )
    checked = checked_keys(result, SELECT_COLUMN, target)
    edited = merge_edited_rows(
        original, result.drop(columns=[SELECT_COLUMN]), filtered=view.filtered
    )
    return edited, checked


def _selection_buttons(slug: str, *, delete_locked: str | None = None) -> str | None:
    """작은 편집표 **위** 세 단추(2026-09-29 — 작업 단추는 표 위). 누른 것의 이름을 돌려준다. 단추
    값은 표보다 먼저 만들어도 같은 회차의 편집·선택이 함께 들어온다. 필터·삭제·저장의 관계는
    가용설비 현황 Guide 가 말한다. `delete_locked` 를 주면 「선택 행 삭제」 를 끄고 그 까닭을
    풍선으로 보인다(낡은 세션의 비가동 일정).
    """
    with st.container(horizontal=True, gap="small"):
        matching = st.button(
            "필터에 맞는 행 모두 선택",
            key=f"equipment_{slug}_select_matching_v1",
            icon=":material/checklist:",
        )
        clear = st.button(
            "선택 해제",
            key=f"equipment_{slug}_select_clear_v1",
            icon=":material/deselect:",
        )
        delete = st.button(
            "선택 행 삭제",
            key=f"equipment_{slug}_delete_selected_v1",
            icon=":material/delete:",
            disabled=delete_locked is not None,
            help=delete_locked,
        )
    if matching:
        return SELECT_MATCHING
    if clear:
        return SELECT_CLEAR
    if delete:
        return DELETE_SELECTED
    return None


def _current_selection() -> dict[str, frozenset[RowKey]]:
    saved = st.session_state.get(SELECTION_KEY)
    return dict(saved) if isinstance(saved, dict) else {}


def _deletion_message(plan: DeletionPlan) -> str:
    """작은 편집표(기존 보유대수·비가동 일정)에서 무엇이 얼마나 빠지는지. 호기 지우기는 설비 마스터
    표의 출납(`delete` — 딸린 비가동 함께, 토스트)이다."""
    count = plan.target_count
    samples = ", ".join(plan.sample_keys())
    more = " 외" if count > len(plan.sample_keys()) else ""
    if plan.target == BASELINE_TARGET:
        head = f"기존 보유대수 {count:,}행을 편집본에서 지웁니다"
    else:
        head = f"비가동 일정 {count:,}건을 편집본에서 지웁니다"
    return (
        f"{head}. 대상: {samples}{more}. 확정해도 「저장 전 변경」 의 「리비전 저장」 을 눌러야 새 "
        "리비전에 반영됩니다."
    )


def _render_bulk_delete_status(frames: Frames) -> tuple[bool, bool, bool]:
    """확인 대기 중인 삭제와 방금 한 삭제를 작은 편집표 위에 말한다. (확정, 취소, 되돌리기)."""
    confirm = cancel = undo = False
    pending = st.session_state.get(PENDING_DELETE_KEY)
    if isinstance(pending, tuple) and len(pending) == 2:
        target, keys = pending
        # 계획은 **지금 편집본**으로 다시 세운다. 대기하는 동안 편집이 있었으면 수가 바뀐다.
        plan = plan_deletion(frames, target, keys)
        if plan.target_count:
            st.warning(_deletion_message(plan), icon=":material/delete:")
            with st.container(horizontal=True, gap="small"):
                confirm = st.button(
                    "삭제 확정",
                    key=CONFIRM_DELETE_BUTTON_KEY,
                    type="primary",
                    icon=":material/delete_forever:",
                )
                cancel = st.button("취소", key=CANCEL_DELETE_BUTTON_KEY, icon=":material/close:")
    removed = st.session_state.get(LAST_REMOVED_KEY)
    if isinstance(removed, tuple):
        count = sum(len(frame) for frame in removed)
        st.info(
            f"방금 편집본에서 {count:,}행을 지웠습니다. 저장하기 전까지 되돌릴 수 있습니다.",
            icon=":material/undo:",
        )
        undo = st.button("방금 삭제 되돌리기", key=UNDO_DELETE_BUTTON_KEY, icon=":material/undo:")
    return confirm, cancel, undo


def _apply_bulk_actions(
    editor: EditorResult,
    *,
    confirm: bool,
    undo: bool,
    view_applied: bool,
) -> None:
    """선택·삭제·되돌리기를 편집본에 반영한다. `_remember_edits` 뒤에 부른다.

    **확인 대기는 어떤 제출이든 한 번 쓰고 버린다.** 삭제 버튼이 다시 세우지 않는 한 남지
    않는다 — 확인 상자가 누른 순간보다 오래 살아 있으면 나중에 다른 뜻으로 눌린다.
    """
    frames: Frames = st.session_state[BUFFER_KEY]
    pending = st.session_state.pop(PENDING_DELETE_KEY, None)
    # 편집표에서 켠 선택은 다른 제출을 지나도 남는다. 보기를 바꾸면 풀린다.
    selection: dict[str, frozenset[RowKey]] = {} if view_applied else dict(editor.checked)
    if editor.action is not None:
        action, target = editor.action
        position, _ = TARGET_LAYOUT[target]
        if action == SELECT_MATCHING:
            selection[target] = matching_keys(frames[position], editor.filters[target], target)
        elif action == SELECT_CLEAR:
            selection[target] = frozenset()
        elif action == DELETE_SELECTED:
            keys = selection.get(target, frozenset())
            if keys:
                st.session_state[PENDING_DELETE_KEY] = (target, keys)
            else:
                st.session_state[_NOTICE_KEY] = (
                    "선택한 행이 없습니다. 표의 ‘선택’ 칸을 켜거나 "
                    "‘필터에 맞는 행 모두 선택’을 누른 뒤 지우세요."
                )
    elif confirm and isinstance(pending, tuple):
        target, keys = pending
        plan = plan_deletion(frames, target, keys)
        _store_changed_buffer(apply_deletion(frames, plan))
        st.session_state[LAST_REMOVED_KEY] = plan.removed
        selection[target] = frozenset()
        st.session_state[_NOTICE_KEY] = _deletion_message(plan).replace("지웁니다", "지웠습니다", 1)
    elif undo:
        removed = st.session_state.pop(LAST_REMOVED_KEY, None)
        if isinstance(removed, tuple):
            restored, skipped = restore_rows(frames, removed)
            _store_changed_buffer(restored)
            message = "방금 지운 행을 편집본에 되살렸습니다."
            if skipped:
                message += f" 그 사이 같은 키가 다시 생긴 {skipped:,}행은 건너뛰었습니다."
            st.session_state[_NOTICE_KEY] = message
    st.session_state[SELECTION_KEY] = selection


# 설비 마스터 탭 「저장 전 변경」 저장 칸 key 접두어(`equipment_save_fields`) — 옛 설비 마스터 탭
# 폼과 같은 글자라 저장자 칸이 배포를 건너 이어진다.
SAVE_FIELDS_PREFIX = "equipment_workspace_save"
# 지우는 호기가 다른 설비 시나리오에 일정이 있을 때의 확인 체크(설계 11-2 6단계). key 꼬리는
# (호기, 그 일정이 든 시나리오들)의 지문(`RemovalElsewhere.token`)이라 글이 바뀌면 체크가 풀린 새
# 칸으로 선다.
REMOVAL_CONFIRM_KEY = "equipment_workspace_removal_confirm_v1"
# 붙여넣기·CSV 「배치 칸도 붙여넣기」(설비 시나리오 2단계 S3 — Q2). 가정 설비 시나리오에서만 서고
# 기본 끔이다 — 「현재 데이터」 CSV 는 합친 값을 내보내 공식 CSV 를 올리면 배치안이 공식 자리로
# 돌아가 정규화로 지워진다. 끄면 있던 호기의 배치 칸은 지금 값을 두고 새 호기의 배치 칸만 받는다.
PASTE_LAYOUT_KEY = "equipment_import_paste_layout_v1"
PASTE_LAYOUT_LABEL = "배치 칸도 붙여넣기"
PASTE_LAYOUT_HELP = (
    "가정 설비 시나리오의 배치(동·층·X좌표·Y좌표·Xsize·Ysize·레이아웃표시)는 이 시나리오에만 "
    "저장됩니다. 끄면 있던 호기의 배치 칸은 지금 값 그대로 두고 새 호기의 배치 칸만 받습니다."
)


def _stale_lock_message(basis: EquipmentSaveBasis) -> str:
    """낡은 세션의 잠금 알림 — 무엇이 잠겼고 어떻게 풀리는지."""
    latest = f"r{basis.latest_revision_no}" if basis.latest_revision_no is not None else "최신"
    return (
        f"「{basis.scenario_name}」 {latest} 가 더 새롭습니다 — 지금 보는 r{basis.revision_no} "
        "에서는 일정 여섯·시나리오 메모 칸과 비가동 일정 표, 행 추가, 호기·비가동 지우기를 "
        "잠갔습니다. 일정을 고치거나 호기를 지우려면 사이드바 「설비 시나리오」 에서 "
        f"최신 {latest} 를 불러오세요. 공통 칸(기존 보유대수 지우기 포함)은 그대로 고쳐 "
        "저장됩니다."
    )


def stale_delete_lock(basis: EquipmentSaveBasis) -> str:
    """낡은 세션에서 호기·비가동 「선택 행 삭제」 를 끈 까닭(단추 풍선). 호기를 지우면 그 호기의
    일정 행도 이 설비 시나리오에서 빠져 일정이 바뀐 저장이 되고, 낡은 리비전 위의 일정 저장은
    저장소가 늘 거부한다 — 지운 편집을 버려야 했다."""
    latest = f"r{basis.latest_revision_no}" if basis.latest_revision_no is not None else "최신"
    return (
        f"지금 보는 r{basis.revision_no} 는 「{basis.scenario_name}」 최신이 아니라 지울 수 "
        f"없습니다 — 호기·비가동을 지우면 이 설비 시나리오의 일정도 바뀝니다. 최신 {latest} 를 "
        "불러온 뒤 지우세요."
    )


def stale_paste_refusal(
    review: ImportReview, current: Frames, basis: EquipmentSaveBasis
) -> str | None:
    """낡은 세션에서 일정 쪽을 바꾸는 붙여넣기를 미리보기 전에 막는다. 막을 것이 없으면 None.

    비가동 일정은 표 전체가 시나리오 쪽이라 늘 막고, 설비 마스터는 새 호기 행이나 일정 일곱 칸이
    바뀌는 행이 있으면 막는다(공통 칸만 바꾸는 붙여넣기는 통과).
    """
    latest = f"r{basis.latest_revision_no}" if basis.latest_revision_no is not None else "최신"
    way_out = f" 사이드바 「설비 시나리오」 에서 최신 {latest} 를 불러온 뒤 다시 미리보세요."
    if review.target == "비가동 일정":
        if not review.candidate[2].equals(current[2]):
            refusal = "비가동 일정은 설비 시나리오 쪽이라 지금 보는 낡은 리비전에 넣지 않습니다."
            return refusal + way_out
        return None
    if review.target != "설비 마스터":
        return None
    before = current[1].set_index(EQUIPMENT_ID_COLUMN, drop=False)
    after = review.candidate[1].set_index(EQUIPMENT_ID_COLUMN, drop=False)
    added = [name for name in after.index if name not in before.index]
    if added:
        return (
            f"새 호기 {len(added):,}행은 설비 시나리오 일정과 함께 들어가 낡은 리비전에 넣지 "
            f"않습니다.{way_out}"
        )
    columns = [column for column in SCENARIO_SCHEDULE_COLUMNS if column in after.columns]
    left = before.loc[list(after.index), columns].reset_index(drop=True)
    right = after.loc[:, columns].reset_index(drop=True)
    # 글 칸(`string`)의 빈 값과 글을 견주면 `==` 가 NA 를 내고 `all` 이 NA 를 건너뛰어 「같다」 로
    # 읽힌다 — 빈 시나리오 메모에 글을 넣거나 지우는 붙여넣기가 낡은 리비전에 들었다. NA 는 다름으로
    # 보고 둘 다 빈 칸만 같다고 본다.
    equal = (left == right).astype("boolean").fillna(False)
    same = equal | (left.isna() & right.isna())
    changed = int((~same.all(axis=1)).sum())
    if changed:
        return (
            f"일정·시나리오 메모 칸이 바뀌는 호기 {changed:,}대가 있어 낡은 리비전에 넣지 "
            f"않습니다.{way_out}"
        )
    return None


def paste_split_summary(source: Frames, candidate: Frames) -> str | None:
    """붙여넣기 미리보기의 두 쪽 한 줄 — 「공통 칸 n · 시나리오 칸 m 바뀜 · 새 호기 k · 새
    비가동 j」.

    칸 수는 두 편집본에 다 있는 호기의 바뀐 칸 수다(공통 = 공통 대장으로, 시나리오 = 이 설비
    시나리오 일정으로 간다). 새 호기·새 비가동은 저장할 때 다른 설비 시나리오에 함께 넣을
    후보다(저장 칸의 두 체크 — 실제로 퍼진 목록은 저장 결과 알림이 적는다). 바뀐 것이 없으면 None.
    """
    before = source[1].set_index(EQUIPMENT_ID_COLUMN, drop=False)
    after = candidate[1].set_index(EQUIPMENT_ID_COLUMN, drop=False)
    before = before.loc[~before.index.duplicated()]
    after = after.loc[~after.index.duplicated()]
    kept = [name for name in after.index if name in before.index]
    new_units = len(after.index) - len(kept)

    def changed(columns: Sequence[str]) -> int:
        shown = [
            column for column in columns if column in after.columns and column in before.columns
        ]
        if not kept or not shown:
            return 0
        # 칸 형(날짜·수·글자)이 두 표에서 달라도 같은 값이면 같다 — 글자로 맞춰 견준다.
        left = before.loc[kept, shown].reset_index(drop=True).astype("string").fillna("")
        right = after.loc[kept, shown].reset_index(drop=True).astype("string").fillna("")
        return int(left.ne(right).to_numpy().sum())

    common = changed(
        [
            column
            for column in COMMON_MASTER_COLUMNS
            if column != EQUIPMENT_ID_COLUMN and column not in SCENARIO_LAYOUT_COLUMNS
        ]
    )
    layout_cells = changed(list(SCENARIO_LAYOUT_COLUMNS))
    layout_units = len(_layout_changed_units(before, after, kept)) if layout_cells else 0
    schedule = changed(list(SCENARIO_SCHEDULE_COLUMNS))

    def downtime_keys(frame: pd.DataFrame) -> set[tuple[str, str, str]]:
        if frame.empty:
            return set()
        starts = pd.to_datetime(frame["시작일"], errors="coerce").dt.strftime("%Y-%m-%d")
        return {
            (str(name), str(kind), str(start))
            for name, kind, start in zip(
                frame[EQUIPMENT_ID_COLUMN], frame["비가동유형"], starts, strict=True
            )
        }

    new_downtime = len(downtime_keys(candidate[2]) - downtime_keys(source[2]))
    if not (common or layout_cells or schedule or new_units or new_downtime):
        return None
    layout = f" · 배치 칸 {layout_cells:,}(호기 {layout_units:,}대)" if layout_cells else ""
    return (
        f"공통 칸 {common:,}{layout} · 시나리오 칸 {schedule:,} 바뀜 · 새 호기 {new_units:,} · "
        f"새 비가동 {new_downtime:,}(다른 설비 시나리오에 넣을 후보)"
    )


def _layout_changed_units(
    before: pd.DataFrame, after: pd.DataFrame, names: Sequence[str]
) -> list[str]:
    """두 표(설비명 색인)에 다 있는 `names` 가운데 배치 일곱 칸 견줄 값(`place_of`)이 다른
    설비명."""
    left = _name_places(before.reset_index(drop=True))
    right = _name_places(after.reset_index(drop=True))
    return [
        str(name)
        for name in names
        if str(name) in left and str(name) in right and left[str(name)][1] != right[str(name)][1]
    ]


def _history_scenario(
    repository: DuckDBEquipmentRepository,
    basis: EquipmentSaveBasis | None,
    snapshot: EquipmentSnapshot | None,
) -> str | None:
    """저장 이력이 보일 설비 시나리오 — 세션 것, 없으면 편집본이 나온 것, 그것도 없으면 공식."""
    if basis is not None:
        return basis.equipment_scenario_id
    if snapshot is not None and snapshot.schedule is not None:
        return snapshot.schedule.equipment_scenario_id
    catalog = load_equipment_scenario_catalog(str(repository.database_path))
    return catalog.effective_official_scenario_id


SMALL_EDITOR_NAMES = {BASELINE_EDITOR_KEY: BASELINE_TARGET, DOWNTIME_EDITOR_KEY: DOWNTIME_TARGET}
SMALL_EDITOR_NOTE = (
    "적용하지 않은 편집은 탭이나 화면을 옮기면 사라집니다(탭 이름 옆 점이 알리고, 화면 탭을 "
    "옮길 때는 묻습니다) — 「편집본에 적용」 을 누른 뒤 옮깁니다. 저장은 오른쪽 「저장 전 변경」 "
    "한 곳입니다."
)


def small_editor_edits() -> list[str]:
    """적용하지 않은 편집이 남은 작은 편집표의 이름(기존 보유대수·비가동 일정). 그리지 않은 표는
    칸이 없어 빠진다 — 화면 탭 줄 떠나기 확인·탭 ① 점이 이것을 본다. 작은 편집표가 **폼 밖**이라
    칸을 고친 회차마다 서버에 와 이 판정이 선다(폼 안이면 적용을 누르기 전까지 서버에 오지 않는다 —
    AGENTS 9장 「다른 위젯의 잠금·표시를 바꾸는 위젯은 폼 밖」)."""
    return [name for key, name in SMALL_EDITOR_NAMES.items() if editor_has_edits(key)]


def buffer_base() -> str:
    """편집본 출발점 표지 — 저장본 쌍 토큰 + 씨뿌린 세대(개편 명세 6-3 `base`). 남의 저장·내 저장·
    모두 버리기·시나리오 불러오기 때만 바뀐다 — 표 출납의 `base` 대조와 「리비전 저장」 두 번 누름
    거르기의 잣대다(편집본 세대는 출납마다 올라 잣대가 될 수 없다)."""
    token = st.session_state.get(_REVISION_KEY)
    seeded = st.session_state.get(_SEEDED_GENERATION_KEY)
    return f"{token}#{seeded}"


def render_small_editor(
    target: str,
    *,
    stale: bool,
    delete_locked: str | None,
    drafts_replaced: bool,
    floor_canvases: FloorCanvasMap,
) -> Callable[[], None] | None:
    """설비 마스터 탭 표 고르기의 작은 편집표 하나(기존 보유대수·비가동 일정 — 개편 명세 4-7)를
    그린다. 「보기 적용」 으로 확정한 보기(`_editor_view`)를 고르기 칸 붙은 편집표
    (`_selectable_editor`)로 그리고, 「편집본에 적용」 은 `_remember_edits`, 일괄 삭제는
    `_apply_bulk_actions` 다.

    **폼으로 묶지 않는다**(명세 4-7 「작은 폼」 에서 바꿈 — D11). 폼 안 편집은 제출 전까지
    서버에 오지 않아 적용 전 편집을 탭 ① 점·화면 탭 줄 떠나기 확인(`small_editor_edits`)이 볼 수
    없다. 칸을 고칠 때마다 회차가 돌지만 편집표는 「보기 적용」 으로 확정한 보기를 그대로 그려
    편집이 남고, 보기 설정·고르기 칸도 같다(보기는 「보기 적용」 을 눌러야 바뀐다).

    제출을 받았으면 그 처리(편집본 적용 → `st.rerun()`)를 돌려준다 — 화면의 모든 위젯(오른쪽 칸
    포함)을 그린 **뒤에** 부른다(AGENTS 9장 「`st.rerun()` 은 그 화면의 모든 편집표를 그린
    뒤에만」). 받은 제출이 없으면 None. 비가동 일정은 시나리오 쪽이라 낡은 세션이면 통째로
    잠근다. 저장은 오른쪽 「저장 전 변경」 한 곳이다."""
    frames: Frames = st.session_state[BUFFER_KEY]
    baseline_table = target == BASELINE_TARGET
    position = 0 if baseline_table else 2
    slug = "baseline" if baseline_table else "downtime"
    # 이름 바꿈이 남긴 필터 지도를 필터를 그리기 전에 얹는다(`follow_unit_renames`).
    _apply_followed_filters()
    if delete_locked is not None:
        # 낡기 전에 눌러 둔 비가동 삭제 확인은 버린다 — 확정하면 저장이 늘 거부된다.
        waiting = st.session_state.get(PENDING_DELETE_KEY)
        if isinstance(waiting, tuple) and waiting and waiting[0] == DOWNTIME_TARGET:
            st.session_state.pop(PENDING_DELETE_KEY, None)
    # 알림은 늘 서 있는 한 칸 안에 그린다(아래 편집표 칸의 자리를 고정한다).
    with st.container():
        error = st.session_state.pop(_ERROR_KEY, None)
        if isinstance(error, str):
            st.error(error)
        notice = st.session_state.pop(_NOTICE_KEY, None)
        if isinstance(notice, str):
            st.info(notice)
        if baseline_table:
            example_rows = _example_row_count(frames, None)
            if example_rows:
                st.warning(
                    f"기존 보유대수에 손대지 않은 예시 행 {example_rows:,}건 — 저장이 막힙니다"
                    "(양식의 예시 줄이거나 개발용 샘플입니다)."
                )
                st.button(
                    f"예시 행 {example_rows:,}건 지우기",
                    icon=":material/delete_sweep:",
                    key=EXAMPLE_DROP_BUTTON_KEY,
                    on_click=_drop_example_rows,
                    kwargs={"floor_canvases": floor_canvases},
                )
    selection = _current_selection()
    # 폼이 아니라 key 있는 칸 하나다(단추·보기·표가 한 칸에 선다).
    with st.container(key=f"equipment_small_{slug}_editor_v1"):
        with st.container(horizontal=True, gap="small"):
            apply_clicked = st.button(
                "편집본에 적용",
                key=f"equipment_{slug}_apply_v1",
                type="primary",
                icon=":material/check:",
            )
            view_clicked = st.button("보기 적용", key=f"equipment_{slug}_view_apply_v1")
        confirm_delete, cancel_delete, undo_delete = _render_bulk_delete_status(frames)
        if baseline_table:
            view, requested = _editor_view(
                frames[0],
                key=BASELINE_EDITOR_KEY,
                prefix="equipment_baseline_view",
                filters=("공정", "분류"),
                locked=("공정", "분류", "기존보유대수"),
                label="기존 보유대수 · 표 보기 설정",
            )
            action = _selection_buttons("baseline")
            edited, checked = _selectable_editor(
                frames[0],
                view,
                key=BASELINE_EDITOR_KEY,
                target=BASELINE_TARGET,
                column_config={
                    "공정": st.column_config.TextColumn(required=True, pinned=True),
                    "분류": st.column_config.TextColumn(required=True),
                    # `step` 을 주지 않는다 — Streamlit 은 step 의 소수 자릿수만큼 입력을 **잘라**
                    # 저장한다(0.01 이면 1/3 모듈 0.333… → 0.33). 적은 값이 그대로 들어가고 보이는
                    # 자리만 형식이 소수 둘째 자리로 반올림한다(`prepare_equipment_baseline`).
                    "기존보유대수": st.column_config.NumberColumn(
                        "기존 보유대수", min_value=0, format="%.2f 대", required=True
                    ),
                    "비고": st.column_config.TextColumn(),
                },
                selection=selection.get(BASELINE_TARGET, frozenset()),
            )
        else:
            downtime = frames[2]
            view, requested = _editor_view(
                downtime,
                key=DOWNTIME_EDITOR_KEY,
                prefix=DOWNTIME_VIEW_PREFIX,
                filters=(EQUIPMENT_ID_COLUMN, "비가동유형"),
                locked=(EQUIPMENT_ID_COLUMN, "비가동유형", "시작일"),
                label="운영 비가동 일정 · 표 보기 설정",
            )
            types = sorted(set(DOWNTIME_TYPES) | set(downtime["비가동유형"].dropna().astype(str)))
            action = _selection_buttons("downtime", delete_locked=delete_locked)
            edited, checked = _selectable_editor(
                downtime,
                view,
                key=DOWNTIME_EDITOR_KEY,
                target=DOWNTIME_TARGET,
                column_config={
                    EQUIPMENT_ID_COLUMN: st.column_config.TextColumn(required=True, pinned=True),
                    "비가동유형": st.column_config.SelectboxColumn(options=types, required=True),
                    "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
                    "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                },
                selection=selection.get(DOWNTIME_TARGET, frozenset()),
                # 비가동 일정 표 전체가 설비 시나리오 쪽이다 — 낡은 세션에서는 통째로 잠근다.
                locked_columns=tuple(downtime.columns) if stale else (),
                fixed_rows=stale,
            )
        st.caption(SMALL_EDITOR_NOTE)
    if not any(
        (
            apply_clicked,
            view_clicked,
            action is not None,
            confirm_delete,
            cancel_delete,
            undo_delete,
        )
    ):
        return None

    def submit() -> None:
        if drafts_replaced:
            st.session_state[_ERROR_KEY] = (
                "다른 사용자가 먼저 저장해 이번 제출은 반영하지 않았습니다. 최신 저장본으로 다시 "
                "열었으니 확인한 뒤 다시 고치세요."
            )
            st.rerun()
        current: Frames = st.session_state[BUFFER_KEY]
        updated = list(current)
        updated[position] = edited
        _remember_edits((updated[0], updated[1], updated[2]))
        _apply_bulk_actions(
            EditorResult(
                frames=(updated[0], updated[1], updated[2]),
                checked={**selection, target: checked},
                filters={target: requested.filters},
                action=(action, target) if action is not None else None,
            ),
            confirm=confirm_delete,
            undo=undo_delete,
            view_applied=view_clicked,
        )
        st.rerun()

    return submit


# 일정 리비전 출처(`origin`) 화면 글자.
ORIGIN_WORDS = {
    "legacy": "이관",
    "save": "저장",
    "clone": "복제",
    "propagate": "함께 넣기",
    "restore": "되돌리기",
    "layout_clear": "배치 차이 정리",
}


def schedule_revision_title(revision: EquipmentScheduleRevisionSummary) -> str:
    """일정 리비전의 짧은 이름 — 「r3」, 리비전명이 있으면 「r3 · 셋업 반영본」(E7).

    리비전명은 이름표라 고칠 수 있다 — 리비전 목록(`load_equipment_schedule_revisions`)에서 받은
    요약으로만 부른다. 합친 본문의 `schedule` 은 이름을 싣지 않는다(늘 None). 선택지·표 칸처럼
    글자 그대로 그리는 자리용이다 — Markdown 에 넣을 때는 부르는 쪽이 `literal_markdown` 으로
    감싼다.
    """
    name = (revision.revision_name or "").strip()
    return f"r{revision.revision_no} · {name}" if name else f"r{revision.revision_no}"


def _render_history(
    repository: DuckDBEquipmentRepository,
    *,
    scenario_id: str | None,
    scenario_name: str | None,
) -> None:
    """고른 설비 시나리오의 일정 리비전 이력과 그 리비전 하나의 「그때 그대로」 조회 — 설비 마스터
    탭 오른쪽 칸 「저장 이력」. 폼 밖이라 조건을 바꾸면 바로 다시 그린다.

    목록은 설비 시나리오 리비전 목록 캐시(세대·stat·TTL), 조회는 그 리비전과 그 저장이 함께 본
    공통 리비전 쌍의 합친 본문 캐시다(`load_saved_pair` 와 같은 쌍). 공통 대장 번호는 공통 이력
    목록(최신 공통 id 키)에서 붙인다.
    """
    database_path = str(repository.database_path)
    if scenario_id is None:
        st.info("첫 리비전을 저장하면 이곳에서 저장 시점별 데이터를 확인할 수 있습니다.")
        return
    revisions = load_equipment_schedule_revisions(database_path, scenario_id)
    if not revisions:
        st.info("첫 리비전을 저장하면 이곳에서 저장 시점별 데이터를 확인할 수 있습니다.")
        return
    latest_common = latest_equipment_revision_id(database_path)
    common_numbers = {
        item.revision_id: item.revision_no
        for item in load_equipment_revision_summaries(database_path, latest_common)
    }
    if scenario_name:
        st.caption(
            f"「{scenario_name}」 의 일정 리비전 — 공통 대장은 저장 때 함께 본 리비전입니다."
        )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "리비전": f"r{item.revision_no}",
                    "리비전명": item.revision_name,
                    "저장시각": item.created_at,
                    "저장자": item.saved_by,
                    "출처": ORIGIN_WORDS.get(item.origin, item.origin),
                    "공통": _common_words(item, common_numbers),
                    "호기행": item.unit_row_count,
                    "비가동행": item.downtime_row_count,
                    "변경메모": item.note,
                }
                for item in revisions
            ]
        ),
        hide_index=True,
        width="stretch",
        placeholder="",
        column_config={"저장시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
    )
    by_id = {item.schedule_revision_id: item for item in revisions}
    selected_id = prune_choice(
        "equipment_history_revision_id_v4", list(by_id), default=next(iter(by_id))
    )
    # 보기 조건은 다른 화면(탭)에 갔다 와도 남는다(`persist_state="session"`, AGENTS 9장).
    st.selectbox(
        "조회 리비전",
        options=list(by_id),
        key="equipment_history_revision_id_v4",
        persist_state="session",
        format_func=lambda value: (
            f"{schedule_revision_title(by_id[value])} · {by_id[value].note or '메모 없음'}"
        ),
    )
    chosen = by_id[selected_id]
    common_id = chosen.common_revision_id or latest_common
    if common_id is None:
        st.info("공통 대장 리비전이 없어 조회할 수 없습니다.")
        return
    historical = load_merged_equipment_snapshot(database_path, common_id, selected_id)
    equipment = historical.equipment
    downtime = historical.downtime
    filters: dict[str, list[str]] = {}
    with st.expander("조회 조건", expanded=False, key=HISTORY_FILTER_EXPANDER_KEY):
        with st.container(horizontal=True, gap="small"):
            for column, suffix in (
                ("공정소분류", "process"),
                ("동", "building"),
                ("층", "floor"),
                (EQUIPMENT_ID_COLUMN, "id"),
            ):
                filters[column] = st.multiselect(
                    column,
                    equipment[column].dropna().drop_duplicates().tolist(),
                    key=f"equipment_history_{suffix}_filter_v3",
                    persist_state="session",
                )
            downtime_types = st.multiselect(
                "비가동유형",
                downtime["비가동유형"].dropna().drop_duplicates().tolist(),
                key="equipment_history_downtime_type_filter_v3",
                persist_state="session",
            )
        today = date.today()
        event_start = downtime["시작일"].min()
        event_end = downtime["종료일"].max()
        first_date = pd.Timestamp(event_start).date() if pd.notna(event_start) else today
        last_date = pd.Timestamp(event_end).date() if pd.notna(event_end) else today
        default_range = (first_date, max(today, first_date, last_date))
        event_range = st.date_input(
            "비가동 일정 기간",
            value=default_range,
            key="equipment_history_event_range_v3",
            persist_state="session",
        )
    for column, selected in filters.items():
        if selected:
            equipment = equipment.loc[equipment[column].isin(selected)]
    if any(filters.values()):
        downtime = downtime.loc[downtime[EQUIPMENT_ID_COLUMN].isin(equipment[EQUIPMENT_ID_COLUMN])]
    if downtime_types:
        downtime = downtime.loc[downtime["비가동유형"].isin(downtime_types)]
    start, end = date_range_value(event_range, default_range)
    if start > end:
        st.error("조회 시작일이 종료일보다 늦습니다. 기간을 다시 선택하세요.")
    elif not downtime.empty:
        downtime = downtime.loc[
            downtime["시작일"].le(pd.Timestamp(end))
            & (downtime["종료일"].isna() | downtime["종료일"].ge(pd.Timestamp(start)))
        ]
    st.caption(
        "조회 조건을 바꾸면 바로 다시 그립니다. 조회는 편집본과 저장 이력을 바꾸지 않습니다."
    )
    for label, frame in (
        ("기존 보유대수", historical.baseline),
        ("설비 마스터", equipment),
        ("비가동 일정", downtime),
    ):
        with st.expander(label, expanded=True):
            st.dataframe(frame, hide_index=True, width="stretch")


def _common_words(item: EquipmentScheduleRevisionSummary, numbers: Mapping[str, int]) -> str:
    """이력 표의 「공통」 칸 — 그 저장이 함께 본 공통 대장 번호(목록 밖이면 빈칸)."""
    if item.common_revision_id is None:
        return ""
    number = numbers.get(item.common_revision_id)
    return f"r{number}" if number is not None else ""


# 가정 설비 시나리오의 일정 확인(설비 마스터 탭 「일정 확인 필요」·표 풍선)이 볼 마스터 한 벌 —
# ((공식 토큰, 편집본 세대, 미리보기), 표).
_CONFIRMATION_OFFICIAL_KEY = "equipment_schedule_confirmation_official_v1"


def official_confirmation_master(master: pd.DataFrame, official: EquipmentSnapshot) -> pd.DataFrame:
    """가정 설비 시나리오의 일정 확인(설비 마스터 탭 「일정 확인 필요」·표 풍선)이 볼 마스터 —
    편집본의 공통 칸 + 공식 일정 일곱 칸.

    미확인은 공식 시나리오 일정 기준이다(결정). 공통 칸(실적·상태)은 편집본 그대로라 실적·상태를
    고치면 목록에서 빠지고, 이 시나리오에서 고친 일정은 목록을 바꾸지 않는다. 공식에 없는 호기(새
    호기·공식 일정 없음)는 일정 칸이 빈다. Space 편집기로 이름을 바꾼 호기는 저장본 이름으로 찾는다.
    """
    columns = [column for column in SCENARIO_SCHEDULE_COLUMNS if column in master.columns]
    source = official.equipment.copy()
    source.index = pd.Index(source[EQUIPMENT_ID_COLUMN].astype("string").str.strip())
    source = source.loc[~source.index.duplicated()]
    renames = pending_unit_renames().units
    names = master[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
    lookup = names.map(lambda name: renames.get(str(name), str(name)) if pd.notna(name) else name)
    result = master.copy()
    for column in columns:
        result[column] = lookup.map(source[column]).to_numpy()
        if pd.api.types.is_datetime64_any_dtype(source[column]):
            result[column] = pd.to_datetime(result[column])
    return result


def _confirmation_master(
    master: pd.DataFrame, official: EquipmentSnapshot | None, preview: object
) -> pd.DataFrame:
    """일정 확인 목록이 볼 마스터. 공식 기준이면 세션 칸에 한 벌(공식 토큰·편집본 세대·미리보기로
    키) — 설비 마스터 탭은 표 출납마다 회차가 돌므로 바뀐 것이 없는 회차에 다시 짓지 않는다."""
    if official is None:
        return master
    key = (official.token, equipment_buffer_generation(), id(preview) if preview else None)
    memo = st.session_state.get(_CONFIRMATION_OFFICIAL_KEY)
    if isinstance(memo, tuple) and len(memo) == 2 and memo[0] == key:
        cached = memo[1]
        if isinstance(cached, pd.DataFrame):
            return cached
    built = official_confirmation_master(master, official)
    st.session_state[_CONFIRMATION_OFFICIAL_KEY] = (key, built)
    return built


# CSV 업로드 칸 하나만의 상한(MB). 빼면 서버 전체 상한(`.streamlit/config.toml` 의
# `maxUploadSize`, 1GB)을 물려받는데, CSV 파싱은 파일 크기의 몇 배 메모리를 써 잘못 고른 큰 파일
# 하나가 공용 앱 프로세스를 몰 수 있다. 칸 안내(「50MB per file」)와 브라우저가 올리기 전에 막는
# 크기(「File must be 50.0MB or smaller.」)가 이 값이다 — 서버 전체 상한은 그대로라 다른 올리기
# 칸은 묶지 않는다.
CSV_UPLOAD_LIMIT_MB = 50
