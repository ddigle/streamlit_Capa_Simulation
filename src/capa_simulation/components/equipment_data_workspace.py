# Purpose: 설비 마스터 탭의 편집본 경계·작은 편집표·저장 이력·세 표 리비전 저장을 둔다.

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, NamedTuple, cast
from uuid import uuid4

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.date_panel import date_range_field
from capa_simulation.components.editor_state import (
    discard_editor,
    editor_has_edits,
    editor_widget_key,
)
from capa_simulation.components.equipment_save_fields import EquipmentSaveBasis
from capa_simulation.components.flash import FlashKind, queue_flash, render_flash
from capa_simulation.components.literal_markdown import (
    literal_markdown,
    markdown_safe_tildes,
    quoted,
)
from capa_simulation.components.table_toolbar import (
    file_name_part,
    render_csv_download,
    toolbar_clearance,
    toolbar_room_css,
)
from capa_simulation.components.table_view_controls import (
    TableView,
    filter_widget_key,
    merge_edited_rows,
    render_table_view_controls,
)
from capa_simulation.components.widget_generation import bump, widget_key
from capa_simulation.components.write_guard import (
    held_notice,
    is_own_save,
    note_notice,
    notice_marks,
    own_save_marks,
    remember_own_save,
    remember_seen,
    save_once,
    seen,
)
from capa_simulation.navigation import (
    EQUIPMENT_MASTER_TAB,
    EQUIPMENT_TAB_KEY,
    EQUIPMENT_TABS,
    opening_tab,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    prune_choice,
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_snapshot_cache,
    clear_floor_layout_cache,
    get_equipment_repository,
    latest_equipment_revision_id,
    load_equipment_csv_payloads,
    load_equipment_revision_summaries,
    load_equipment_scenario_catalog,
    load_equipment_schedule_revisions,
    load_merged_equipment_snapshot,
)
from capa_simulation.persistence.equipment_repository import (
    EMPTY_REVISION_TOKEN,
    DuckDBEquipmentRepository,
    EquipmentRevisionConflict,
    EquipmentRevisionSummary,
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
    move_ids,
    prune_overlay,
    renamed_saved_ids,
    save_id_map,
    stale_scenario_edit_spots,
    undo_from_state,
    undo_step_tables,
    undo_to_state,
)
from capa_simulation.services.equipment_samples import untouched_sample_baseline_rows
from capa_simulation.services.equipment_scenario import (
    calculation_frames,
    inherited_unit_names,
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
    subject_particle,
    with_object_particle,
    with_topic_particle,
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
    live_renames,
    module_layout_message,
    module_layout_violations,
    natural_name_key,
    restore_saved_layout,
    saved_layout_drift,
)

# 빠른 두 번 누름 거름(`write_guard.save_once`)의 저장 이름 — 설비 편집본 저장과 FAB 전체 배치 쓰기.
# 설비 편집본 저장은 같은 이름으로 제 저장 표지(`write_guard.own_save_marks` — `<이름>:<설비
# 시나리오 id>`)도 단다. 그 짝은 (편집본이 나온 공통·일정 리비전 id, 저장 뒤 공통·일정 최신 id) 다.
EQUIPMENT_SAVE_NAME = "equipment_buffer"
FAB_SAVE_NAME = "equipment_fab_layout"
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
# 표 · 오른쪽 칸 조작 결과 칸 — 고칠 입력이 없어 알림창 · Alarm 으로만 낸다(`queue_grid_result`).
GRID_RESULT_KEY = "equipment_grid_result_v1"
# 오른쪽 칸 자리 거부 한 줄 {"detail"|"new": {"id", "text"}} — 고칠 입력이 그 칸에 있는 거부만
# (설계 규칙 UI-NTF-03). 번호는 `GRID_TOAST_SEQ_KEY` 하나로 늘 오른다(비우지 않는다 — 같은 번호를
# 다시 쓰면 닫은 한 줄로 보고 숨긴다).
GRID_TOAST_KEY = "equipment_grid_toast_v1"
GRID_TOAST_SEQ_KEY = "equipment_grid_toast_seq_v1"
# 마운트에 실어 보낸 자리 거부 번호 {마운트: 번호} — 그 마운트가 사라지면 그 한 줄을 거둔다
# (`settle_grid_toasts`).
GRID_TOAST_SHOWN_KEY = "equipment_grid_toast_shown_v1"
# 회차 메모(칸 결과·표 단위 오류 — 열쇠가 바뀌면 덮는다).
GRID_MEMO_KEY = "equipment_grid_memo_v1"
# 표에 불러온 목록(행 id 차례)·상세에 연 행 id — 편집본을 다시 세워도·저장해도 남는다(이름 바꾼
# 저장본 호기는 새 id 로 옮긴다 — 자기 저장 뒤는 저장 길이, 남의 저장으로 다시 세우면
# `ensure_equipment_drafts` 가 호기 키로 잇는다, 개편 명세 7-3). 편집본에 없는 id 는 회차마다
# 거른다.
GRID_LOADED_KEY = "equipment_grid_loaded_v1"
GRID_DETAIL_KEY = "equipment_grid_detail_v1"
# 「새 호기」 칸의 초안 {"seq": 번호, "values": 39칸 글} — 저장해도 남고(다음 호기를 이어 넣는다)
# 「호기 추가」 뒤에는 공정소분류·동·층만 남긴다. 편집본과 따로 산다.
NEW_UNIT_DRAFT_KEY = "equipment_new_unit_draft_v1"
_GRID_SESSION_KEYS = (
    GRID_OVERLAY_KEY,
    GRID_UNDO_KEY,
    GRID_RESULT_KEY,
    GRID_TOAST_KEY,
    GRID_TOAST_SHOWN_KEY,
    GRID_MEMO_KEY,
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
# 「한 단계 되돌리기」 가 미룬 일괄 삭제 되살리기(값은 표 이름 — `restore_bulk_deletion`). 그 표에
# 적용하지 않은 편집이 있을 때만 서고, 그 표 편집표가 선 회차의 제출이 편집을 먼저 넣고 되살린다.
RESTORE_REQUEST_KEY = "equipment_workspace_restore_request_v1"
# 「한 단계 되돌리기」 가 미룬 표 단계 되돌리기(값은 표 이름 — `defer_grid_undo`). 그 단계가 바꿀
# 작은 편집표에 적용하지 않은 편집이 있을 때만 서고, 그 표 편집표가 선 회차의 제출이 편집을 먼저
# 넣고 되돌린다.
GRID_UNDO_REQUEST_KEY = "equipment_workspace_grid_undo_request_v1"
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
# 비가동 일정 작은 편집표 「표 보기」 팝오버의 key 접두어(`render_table_view_controls`).
DOWNTIME_VIEW_PREFIX = "equipment_downtime_view"
# 「이름 바꿈」 목록 펼침(설비 마스터 탭 알림 칸).
NAME_CHANGES_EXPANDER_KEY = "equipment_workspace_name_changes_v1"
# 이름 바꿈 목록 아래 한 줄 — Space 편집기 상자와 설비 마스터 탭이 같이 쓴다(G4·R2 — 이름
# 바꾸기는 같은 호기다).
NAME_CHANGES_MARK = ":material/badge: 같은 호기 · 저장하면 새 이름"
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
# 다른 사람이 새 리비전을 저장해 이 세션의 저장 안 한 편집을 버렸을 때의 알림 — 화면을 늦게 본
# 사람도 까닭을 알게 「알림 닫기」 를 누를 때까지(또는 다음 버림 알림이 덮을 때까지) 남긴다.
DISCARDED_NOTICE_KEY = "equipment_workspace_discarded_v1"
# 다른 사람의 저장으로 편집본을 다시 세웠지만 버린 편집이 없을 때 한 번 띄우는 알림(목록·이름이
# 바뀐 까닭 — 이름 바뀐 호기 수). `flash` 한 칸이다.
REOPENED_NOTICE_KEY = "equipment_workspace_reopened_v1"
DISMISS_DISCARDED_LABEL = "알림 닫기"
# 세 화면(가용설비 현황·Space 현황·필요 단축 일정)이 같은 key 로 그리는 「알림 닫기」 단추(한
# 회차에 한 화면만 돈다).
REOPEN_DISMISS_KEY = "equipment_reopen_dismiss_v1"
# 이번 회차 맨 위에서 편집본을 새 저장본으로 갈아 끼웠다는 표시. 그 회차의 작은 편집표 제출은 옛
# 편집본 위의 것이라 반영하지 않는다 — 페이지가 `pop_drafts_replaced` 로 한 번 읽는다(표 출납은
# `base` 대조로 같은 규칙).
DRAFTS_REPLACED_KEY = "equipment_workspace_drafts_replaced_v1"
# 이번 회차에 남의 저장으로 편집본을 다시 세우며 앱 머리(변경 칩 · 화면 탭 점)가 센 편집을 버렸다는
# 표지. 머리는 페이지 본문보다 먼저 옛 값으로 그렸다 — 부르는 화면이 모든 편집표를 그린 뒤 한 번
# 다시 돈다(`rerun_if_head_stale`, AGENTS 9장 「`st.rerun()` 은 그 화면의 모든 편집표를 그린
# 뒤에만」).
HEAD_STALE_KEY = "equipment_workspace_head_stale_v1"
# 그 회차에 비켜 둔 곁 알림 {되돌릴 칸 이름: 담아 둔 값} — 다시 도는 회차가 그 칸에 한 번 그리고 한
# 번 보낸다(`hold_until_head_rerun` · `carry_until_head_rerun`).
_HEAD_HELD_KEY = "equipment_workspace_head_held_v1"
# 그 회차에 담은 사건 알림(버림 `EQ-05`)을 다시 도는 회차가 같은 id 로 한 번 더 보낼 목록 — 다시
# 돌기 전 회차의 표지는 브라우저가 훑기 전에 다음 회차가 덮을 수 있다(브라우저는 id 로 한 번만
# 띄운다 — `flash` 의 `again` 과 같은 꼴).
_HEAD_RESEND_KEY = "equipment_workspace_head_resend_v1"
# 편집본을 저장본에서 새로 세운 직후의 세대. 지금 세대가 이보다 크면 저장 안 한 편집이 있다.
_SEEDED_GENERATION_KEY = "equipment_workspace_seeded_generation_v1"
# 편집본이 저장본으로 돌아온 세대(`_note_if_back_to_saved`). 세운 세대를 옮기지 않고 따로 둔다 —
# 세운 세대는 표 출납의 `base`(`buffer_base`)라, 옮기면 표시가 걷히기 전에 보낸 op 가 버려진다.
_CLEAN_GENERATION_KEY = "equipment_workspace_clean_generation_v1"
# 세션마다 한 번 정하는 표 출납 `base` 의 머리 — 세션이 바뀐 뒤 브라우저에 남은 앞 세션의 op 를
# 가른다.
_BUFFER_SESSION_KEY = "equipment_workspace_session_v1"
# 편집본을 바꿀 때마다 오르는 세대. Space 편집기 epoch 에 넣어 설비 마스터 탭 편집을 놓치지 않게
# 한다.
BUFFER_GENERATION_KEY = "equipment_workspace_buffer_generation_v1"
CANCEL_DELETE_BUTTON_KEY = "equipment_delete_cancel_v1"
SELECT_MATCHING = "select_matching"
SELECT_CLEAR = "select_clear"
DELETE_SELECTED = "delete_selected"
# 작은 편집표 작업 줄의 「선택 ▾」 메뉴(「선택 해제」 · 「선택 행 삭제」 — 2026-11-10 사용자 답
# Q-14 「한 줄로」). 「선택 행 삭제」 는 누르면 세대를 올려 메뉴를 닫는다 — 열린 채 두면 그 아래
# 서는 「삭제 확정」 줄을 덮는다. 「선택 해제」 는 메뉴를 열어 둔다 — 세대를 올리면 메뉴가 새로
# 서며 키보드 초점이 문서 몸통으로 떨어진다(열어 두면 초점이 그 단추에 남고 Esc 로 닫힌다).
# 라벨이 짧은 것은 1283 창에서도 작업 줄이 표 도구 막대 자리 앞 한 줄에 들게 하려는 것이다
# (`render_small_editor`).
SELECTION_MENU_LABEL = "선택"
SELECTION_MENU_ICON = ":material/check_box:"
# 저장 이력 「조회 조건」 펼침의 key — 위젯이 아니라 브라우저가 펼침을 기억하는 이름이다.
HISTORY_FILTER_EXPANDER_KEY = "equipment_history_filters_v1"
HISTORY_EVENT_START_KEY = "equipment_history_event_start_v3"
HISTORY_EVENT_END_KEY = "equipment_history_event_end_v3"
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
        RESTORE_REQUEST_KEY,
        GRID_UNDO_REQUEST_KEY,
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
        _CLEAN_GENERATION_KEY,
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
    """내용이 바뀐 편집본을 넣고 세대를 올린다. 일괄 삭제 확정 · 되살리기가 이 길로만 쓴다.

    세대가 「저장하지 않은 편집」의 근거다(`has_unsaved_equipment_edits` — 저장본으로 돌아온 세대만
    뺀다). 편집표 칸은 그대로이고 행만 빠진 제출에서 세대가 그대로면, 테마 단추가 묻지 않고
    새로고침하고 다른 사람의 저장이 이 삭제를 알림 없이 버린다.
    """
    st.session_state[BUFFER_KEY] = frames
    _bump_buffer_generation()
    _note_if_back_to_saved()


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
    """편집본을 저장본에서 세운 뒤 바뀐 것이 남아 있는가(설비 마스터 탭 고침·Space 호기 적용·미저장
    층 배치). 세대가 올랐어도 저장본으로 돌아온 세대면 저장할 것이 없다(`_note_if_back_to_saved`).

    Space FAB 전체 배치 대기분은 세대를 올리지 않아 여기 들지 않는다(`pending_fab_layout`)."""
    seeded = st.session_state.get(_SEEDED_GENERATION_KEY)
    generation = equipment_buffer_generation()
    return (
        isinstance(seeded, int)
        and generation > seeded
        and generation != st.session_state.get(_CLEAN_GENERATION_KEY)
    )


def pop_drafts_replaced() -> bool:
    """이번 회차에 다른 사람의 저장으로 편집본을 새로 세웠는가. 페이지가 `ensure_equipment_drafts`
    바로 뒤에 한 번 읽는다(안 읽으면 다음 회차의 정상 제출까지 막는다)."""
    return st.session_state.pop(DRAFTS_REPLACED_KEY, False) is True


def _head_marks() -> tuple[bool, tuple[str, ...]]:
    """앱 머리가 세는 이 편집본의 미저장 표시 — 설비 편집본(칩 · 두 화면 탭 점)과 작은 편집표의 적용
    전 편집(칩 · 탭 점). 둘 다 세션만 읽는다."""
    return has_unsaved_equipment_edits(), tuple(small_editor_edits())


def _release_head_hold() -> None:
    """비켜 둔 곁 알림을 제 칸으로 되돌리고, 다시 보낼 사건 알림을 담아 둔 사건 알림 끝에 잇는다."""
    held = st.session_state.pop(_HEAD_HELD_KEY, None)
    if isinstance(held, dict):
        for key, value in held.items():
            st.session_state[key] = value
    resend = st.session_state.pop(_HEAD_RESEND_KEY, None)
    if isinstance(resend, list) and resend:
        outbox = st.session_state.get(alerts.OUTBOX_KEY)
        st.session_state[alerts.OUTBOX_KEY] = [
            *(outbox if isinstance(outbox, list) else []),
            *resend,
        ]


def hold_until_head_rerun(*keys: str) -> None:
    """머리를 다시 그리려 다시 돌 회차(`HEAD_STALE_KEY`)면 `keys` 에 담아 둔 곁 알림을 다시 도는
    회차까지 비켜 둔다 — 그 칸을 그리기 **전**에 부른다. 이 회차에 꺼내 그리면 다시 돈 회차가 빈
    칸을 그려 곁 글(남의 저장에 진 「배치 저장」 거부)이 깜빡 사라지고, 다시 담으면 알림창 ·
    Alarm 이 한 번 일어난 일을 두 번 센다. 다시 도는 회차는 같은 칸에 되돌린다 — 그 회차가 칸을
    그리기 전에 둘째 누름이 같은 칸에 결과를 담을 수 있으면 `carry_until_head_rerun` 이다."""
    for key in keys:
        _hold_for_head_rerun(key, key)


def carry_until_head_rerun(key: str, *, into: str) -> None:
    """`hold_until_head_rerun` 과 같되 다시 도는 회차에 `into` 칸으로 되돌린다 — 부르는 화면은 그
    칸을 `key` 칸과 한 자리에 그린다(`render_flash(into, key)`). 같은 칸으로 되돌리면, 다시 도는
    회차가 그 칸을 그리기 전에 온 둘째 누름의 결과(「고친 것이 없습니다」)가 그 칸을 덮어 비켜 둔
    거부(남의 공통 저장에 진 「리비전 저장」)가 곁 글 · 알림창 · Alarm 어디에도 남지 않는다."""
    _hold_for_head_rerun(key, into)


def _hold_for_head_rerun(key: str, into: str) -> None:
    """다시 돌 회차면 `key` 칸에 담아 둔 값을 꺼내 다시 도는 회차에 `into` 칸으로 되돌릴 목록에
    적는다."""
    if st.session_state.get(HEAD_STALE_KEY) is not True or key not in st.session_state:
        return
    held = st.session_state.get(_HEAD_HELD_KEY)
    kept = dict(held) if isinstance(held, dict) else {}
    kept[into] = st.session_state.pop(key)
    st.session_state[_HEAD_HELD_KEY] = kept


def rerun_if_head_stale() -> None:
    """남의 저장으로 머리가 센 편집을 버린 회차면 비켜 둔 알림을 되돌리고 한 번 다시 돈다 — 앱 머리
    (변경 칩 · 화면 탭 점)를 새 값으로 그린다(UI-DAT-11). 편집본을 세운 화면이 **모든 편집표를 그린
    뒤** 부른다. 다음 회차는 표지가 없어 되풀이되지 않는다."""
    if st.session_state.pop(HEAD_STALE_KEY, None) is not True:
        return
    _release_head_hold()
    st.rerun()


def discarded_notice_text() -> str | None:
    """다른 사람의 저장으로 이 세션의 편집이 버려졌다는 알림 — 「알림 닫기」 전까지 남는다."""
    value = st.session_state.get(DISCARDED_NOTICE_KEY)
    return value if isinstance(value, str) else None


def dismiss_discarded_notice() -> None:
    """「알림 닫기」 콜백 — 버림 알림을 걷는다."""
    st.session_state.pop(DISCARDED_NOTICE_KEY, None)


def reopened_notice(number: str, *, renamed: int) -> str:
    """버린 편집 없이 다른 사람의 저장으로 편집본을 다시 세운 회차의 알림 — 그 저장(「공통 대장
    r16」)과 이름 바뀐 저장본 호기 수(목록·상세가 새 이름으로 옮는다)."""
    text = f"다른 사용자가 {number}{object_particle(number)} 저장해 최신 저장본으로 다시 열었습니다"
    if renamed:
        text += f" · 이름 바뀐 호기 {renamed:,}대"
    return text


def render_reopen_notices() -> None:
    """다른 사람의 저장으로 편집본을 다시 세운 알림 둘을 페이지 머리 알림 칸 안에 그린다.

    버린 편집이 없었으면 「… 다시 열었습니다 · 이름 바뀐 호기 n대」 를 한 번(`flash` 한 칸),
    있었으면 버렸다는 경고와 「알림 닫기」를 **누를 때까지** 남긴다 — 한 회차만 서면 화면을 늦게
    본 사람이 편집이 사라진 까닭을 모른다(E2E #66). 다음 버림 알림이 오면 그것으로 바뀐다. 두 칸
    모두 알림 유무와 상관없이 늘 서 있어 뒤 형제의 자리를 밀지 않는다. 편집본을
    세운(`ensure_equipment_drafts`) 뒤 부른다 — 가용설비 현황·Space 현황·필요 단축 일정이 같은
    세션 칸을 본다.
    """
    render_flash(REOPENED_NOTICE_KEY)
    slot = st.container()
    notice = discarded_notice_text()
    if notice is None:
        return
    with slot:
        st.warning(notice, icon=":material/sync_problem:")
        st.button(
            DISMISS_DISCARDED_LABEL,
            icon=":material/close:",
            type="tertiary",
            key=REOPEN_DISMISS_KEY,
            on_click=dismiss_discarded_notice,
        )


def ensure_equipment_drafts(latest_snapshot: EquipmentSnapshot | None) -> Frames:
    """저장본 사본(draft)과 미저장 편집본(buffer)을 **한 곳에서** 세우고 편집본을 돌려준다.

    가용설비 현황과 Space 현황이 같은 편집본을 쓴다. 어느 쪽을 먼저 열어도 같은 저장본
    토큰으로 세워야, 나중에 연 쪽이 「토큰이 다르다」며 편집본을 저장본으로 덮어쓰지 않는다.
    새 리비전이 생기면(누가 저장하면) 미저장 편집·캔버스·도면 요소는 버리고 다시 세운다 — 단 가정
    역할로 찍힌 배치 편집은 남이 **공통**을 저장했을 때(일정 쪽 그대로) 그 배치 일곱 칸을 새
    저장본 위에 다시 얹는다(설계 9장 — 찍힌 역할도 남긴다). 설비 마스터 표의 불러온 목록·상세 id 는
    남기고, 남의 저장이 이름을 바꾼 저장본 호기는 호기 키로 이어 새 이름 id 로
    옮긴다(`_follow_saved_unit_renames`). 샘플 fleet 은 넣지 않는다 — 합성값이 섞이면 첫 실제 저장이
    막힌다.
    """
    # 앞 회차가 다시 돌기 전에 끊겼으면(본문 `st.rerun()` · `st.stop()`) 표지와 비켜 둔 알림이
    # 남는다 — 끊긴 뒤 이 회차가 머리를 이미 새 값으로 그렸으니 알림만 제 칸으로 되돌린다.
    lingering = st.session_state.pop(HEAD_STALE_KEY, None) is not None
    if lingering or _HEAD_HELD_KEY in st.session_state or _HEAD_RESEND_KEY in st.session_state:
        _release_head_hold()
    # 이 세션의 저장이 쓰기 뒤 · 뒷정리 전에 끊겼으면(빠른 다음 조작의 회차 — fastReruns) 그
    # 뒷정리와 성공 알림을 여기서 잇는다 — 잇지 않으면 아래가 제 저장을 남의 저장으로 읽는다(a5).
    own_head = _settle_own_save()
    token = revision_token(latest_snapshot)
    previous = st.session_state.get(_REVISION_KEY)
    # 남의 저장으로 다시 세우면 버리는 가정 배치 편집을 옛 저장본 사본이 바뀌기 **전**에 센다. 남의
    # **공통** 저장(일정 쪽 그대로)이면 그 편집의 배치 일곱 칸은 새 저장본 위에 다시 얹는다(설계
    # 9장 — 재료도 옛 사본이 바뀌기 전에 든다).
    swapped = previous is not None and previous != token
    # 앱 머리가 이 회차에 센 미저장 표시(다시 세운 뒤와 견준다).
    head_before = own_head.marks if own_head is not None else _head_marks() if swapped else None
    overlay_dropped = _stamped_overlay_edits() if swapped else 0
    reapply = _reapply_material(previous, token) if swapped else None
    # 저장 안 한 이름 바꿈은 다시 얹지 않고 버린다 — 다시 얹은 알림이 그 수를 버린 것에 적는다(같은
    # 호기의 위치만 다시 얹고 이름은 돌아가 이름도 남았다고 읽혔다, E2E r6).
    renames_dropped = _live_rename_count() if reapply is not None else 0
    # 옛 저장본의 (설비명, 호기 키) — 남이 이름을 바꾼 호기의 표 행 id 를 새 이름으로 옮길 재료.
    old_unit_keys = tuple(draft_unit_keys().items()) if swapped else ()
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
        moved = (
            renamed_saved_ids(old_unit_keys, latest_snapshot.unit_key_pairs)
            if replaced and latest_snapshot is not None
            else {}
        )
        if replaced:
            number = _replaced_by_words(previous, latest_snapshot)
            if has_unsaved_equipment_edits():
                # 닫을 때까지 남긴다(`render_reopen_notices`) — 다음 버림 알림이 덮는다. 알림창 ·
                # Alarm 에도 사건 알림(`EQ-05`)으로 한 번 낸다 — 담기만 하고 페이지 머리 알림
                # 칸(`render_reopen_notices` 의 `render_flash`)이 보낸다.
                discarded = discarded_notice(
                    number,
                    overlay_dropped=overlay_dropped,
                    reapplied=reapplied,
                    renames_dropped=renames_dropped,
                )
                st.session_state[DISCARDED_NOTICE_KEY] = discarded
                alerts.event(
                    "EQ-05",
                    text=f"다른 사용자가 {number}{object_particle(number)} 저장해 내 설비 편집을 "
                    "버렸습니다",
                    full=alerts.plain_text(discarded),
                )
            else:
                queue_flash(
                    REOPENED_NOTICE_KEY,
                    reopened_notice(number, renamed=len(moved)),
                    kind="info",
                    icon=":material/sync:",
                )
        st.session_state[_REVISION_KEY] = token
        # 편집본이 나온 저장본 — 저장이 대조하는 본 값이다(write_guard). 편집본을 세울 때만 적는다.
        remember_seen(_BASE_KEY, _base_of(latest_snapshot))
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
        if moved:
            _follow_saved_unit_renames(moved)
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
    if head_before is not None and _head_marks() != head_before:
        # 머리는 버린 편집을 센 채 그렸다 — 부르는 화면이 회차 끝에 한 번 다시 돈다. 다시 얹은
        # 편집이 남아 표시가 그대로면 머리가 맞아 돌지 않는다. 방금 담은 사건 알림(버림 `EQ-05`)은
        # 다시 도는 회차가 같은 id 로 한 번 더 보낸다 — 이 회차의 표지만으로는 탭만 옮긴 회차에
        # 알림창 · Alarm 에서 빠졌다(사본 앱 확인). 다시 열었다는 안내 칸은 `flash` 가 다시 보낸다.
        st.session_state[HEAD_STALE_KEY] = True
        outbox = st.session_state.get(alerts.OUTBOX_KEY)
        st.session_state[_HEAD_RESEND_KEY] = [
            cast(alerts.AlertNote, {**note, "again": True})
            for note in (outbox if isinstance(outbox, list) else [])
            if isinstance(note, dict)
        ]
    if own_head is not None and own_head.moved:
        # 제 저장이 새 일정 리비전을 썼다 — 세션을 그리로 옮기는 것은 다음 회차(페이지가
        # `pop_saved_schedule` 로 읽는다)다. 이 회차의 저장본 표지를 남기지 않아 다음 회차가 옮긴
        # 리비전에서 말없이 새로 세운다(남의 저장으로 읽지 않는다). 머리도 그 회차에 다시 그린다.
        st.session_state.pop(_REVISION_KEY, None)
        st.session_state[HEAD_STALE_KEY] = True
    frames: Frames = st.session_state[BUFFER_KEY]
    return frames


class _OwnSaveSettled(NamedTuple):
    """끊긴 제 저장의 뒷정리를 이은 회차 — 그 전 머리 표시(`marks`)와 새 일정 리비전을 썼는가."""

    marks: tuple[bool, tuple[str, ...]]
    moved: bool


def _settle_own_save() -> _OwnSaveSettled | None:
    """「리비전 저장」 · 「배치 저장」 이 DB 에 쓴 뒤 뒷정리(`_after_equipment_save`) 전에 끊겼으면
    그 뒷정리와 성공 알림을 잇는다(2026-11-08 사용자 답 a5 — 「제 저장 표지로 뒷정리 · 성공 알림을
    잇는다」).

    끊긴 회차는 `fastReruns` 다 — 저장 중 표 출납 같은 다음 조작이 새 회차를 세우고 옛 콜백은 쓰기
    뒤 다음 세션 칸 접근에서 멈춘다. 그때도 끊기지 않는 dict 칸의 제 저장 짝(`remember_own_save` —
    본 값, 쓴 값)과 알림(`note_notice`)은 남는다. 편집본 출발점(`_BASE_KEY`)이 아직 그 짝의 본
    값이고 알림이 창(`write_guard.TRAILING_PRESS_SECONDS`) 안일 때만 끊긴 제 저장으로 본다 —
    뒷정리를 마친 저장은 출발점을 쓴 값으로 옮기고, 창 밖은 옛 리비전을 일부러 다시 불러온 세션일
    수 있다. 잇지 않으면 다음 판정이 새 저장본을 남의 저장으로 읽어 「다른 사용자가 … 저장해 …
    버렸습니다」 를 알리고 성공 알림이 사라졌다. 알림은 남의 저장 안내와 같은
    칸(`REOPENED_NOTICE_KEY` — 성공이라 알림창)이다."""
    base = seen(_BASE_KEY)
    if not isinstance(base, dict) or not isinstance(base.get("common"), str):
        return None
    schedule = base.get("schedule")
    expected = (str(base["common"]), schedule if isinstance(schedule, str) else "")
    for name, pair in own_save_marks().items():
        if not name.startswith(f"{EQUIPMENT_SAVE_NAME}:") or not isinstance(pair, tuple):
            continue
        if len(pair) != 2 or pair[0] != expected or pair[1] == expected:
            continue
        message = held_notice(name)
        if message is None:
            continue
        stored = pair[1]
        written = stored[1] if isinstance(stored, tuple) and len(stored) == 2 else None
        moved = written if isinstance(written, str) and written != expected[1] else None
        marks = _head_marks()
        # 저장 뒤 목록 · 상세 id 를 새 저장본 id 로 — 저장 길(`_save_revision`)이 못 한 몫이다.
        frames = st.session_state.get(BUFFER_KEY)
        ids: dict[str, str | None] = {}
        if isinstance(frames, tuple):
            renames = pending_unit_renames().units
            ids = save_id_map(grid_index(frames[1], _saved_master(), renames), frames[1])
        loaded, detail = grid_loaded_ids(), st.session_state.get(GRID_DETAIL_KEY)
        _after_equipment_save(name.partition(":")[2], moved or None)
        st.session_state[GRID_LOADED_KEY] = move_ids(loaded, ids)
        if isinstance(detail, str) and ids.get(detail, detail):
            st.session_state[GRID_DETAIL_KEY] = ids.get(detail, detail)
        else:
            st.session_state.pop(GRID_DETAIL_KEY, None)
        queue_flash(REOPENED_NOTICE_KEY, markdown_safe_tildes(message))
        return _OwnSaveSettled(marks, bool(moved))
    return None


def grid_loaded_ids() -> tuple[str, ...]:
    """설비 마스터 표에 불러온 목록(행 id 차례) — 칸이 없거나 목록이 아니면 빈 튜플."""
    value = st.session_state.get(GRID_LOADED_KEY)
    return tuple(str(item) for item in value) if isinstance(value, (list, tuple)) else ()


def _follow_saved_unit_renames(moved: Mapping[str, str]) -> None:
    """남의 저장이 이름을 바꾼 저장본 호기(`moved` — `s:옛` → `s:새`, `renamed_saved_ids`)를 설비
    마스터 표의 불러온 목록·상세에 연 id 에서 새 id 로 옮긴다. 행 id 가 `s:` + 저장본 설비명이라
    옮기지 않으면 살아 있는 호기가 다음 회차에 목록에서 말없이 빠지고 상세가 빈 안내로 돌아간다."""
    if not moved:
        return
    loaded = st.session_state.get(GRID_LOADED_KEY)
    if isinstance(loaded, (list, tuple)):
        st.session_state[GRID_LOADED_KEY] = move_ids([str(item) for item in loaded], moved)
    detail = st.session_state.get(GRID_DETAIL_KEY)
    if isinstance(detail, str) and detail in moved:
        st.session_state[GRID_DETAIL_KEY] = moved[detail]


def same_frame_content(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    """두 표의 내용이 같은가 — `DataFrame.equals` 에 날짜 칸의 시각 단위만 맞춰 본다.

    저장본 사본(DuckDB 에서 읽음)의 날짜 칸은 `datetime64[us]`, 엑셀·CSV 넣기의 병합 결과는
    `datetime64[ns]` 다. 단위만 다른 같은 표를 「바뀜」 으로 보면 바뀐 것 없는 넣기(내려받은 현재
    데이터를 그대로 올림)가 세대를 올려 「저장 전 변경」 0건인데 「미저장 변경」·탭 점·떠나기 확인이
    남는다. 시간대가 있는 날짜 칸과 다른 형은 그대로 견준다."""
    if left.equals(right):
        return True
    if list(left.columns) != list(right.columns) or len(left) != len(right):
        return False
    units = {
        column: "datetime64[ns]"
        for column in left.columns
        if left[column].dtype != right[column].dtype
        and pd.api.types.is_datetime64_dtype(left[column])
        and pd.api.types.is_datetime64_dtype(right[column])
    }
    return bool(units) and left.astype(units).equals(right.astype(units))


def _remember_edits(frames: Frames, *, keep_undo: bool = False) -> None:
    """작은 편집표의 편집을 편집본에 넣는다. `keep_undo` 면 표의 되돌리기를 비우지 않는다 — 미룬
    표 단계 되돌리기가 곧바로 그 위에 얹힌다(`defer_grid_undo` — 칸만 고친 편집이라 줄 자리가
    그대로일 때만)."""
    # 검증 실패한 값도 수정할 수 있어야 한다. 화면 계산이 읽는 draft에는 올리지 않는다.
    current = st.session_state.get(BUFFER_KEY)
    unchanged = isinstance(current, tuple) and all(
        same_frame_content(left, right) for left, right in zip(current, frames, strict=True)
    )
    st.session_state[BUFFER_KEY] = _copy_frames(frames)
    _clear_editors()
    # 내용이 그대로인 제출(작은 편집표 보기 적용 등)은 세대를 올리지 않는다 — 올리면 「저장 안 한
    # 편집이 있다」로 보여, 남의 저장 때 버린 것도 없는데 버렸다고 알린다.
    if not unchanged:
        _bump_buffer_generation()
        if not keep_undo:
            _forget_grid_undo()
        _note_if_back_to_saved()


def _forget_grid_undo() -> None:
    """표 밖의 길(Space 적용·작은 편집표 적용·일괄 삭제·엑셀·CSV 넣기)이 편집본을 바꿨다 — 표의
    되돌리기는 조작 뒤 자리의 역 patch 라 그 위에서 맞지 않으므로 비운다. 비울 것이 있었으면 그
    사실을 알린다(개편 명세 7-1 넷째 자리 — 다른 화면에서 비웠으면 이 탭을 열 때)."""
    if st.session_state.pop(GRID_UNDO_KEY, None):
        queue_grid_result(
            "표 밖에서 편집본을 바꿔 표의 되돌리기를 비웠습니다 — 고친 값은 그대로입니다",
            kind="info",
        )


def queue_grid_result(text: str, *, kind: FlashKind = "success") -> None:
    """표 · 오른쪽 칸 조작의 결과 — 띠가 아니라 알림창 · Alarm 으로만(설계 규칙 UI-NTF-03). 탭 끝
    칸이 꺼내 낸다. 글에 호기 이름이 들어 구두점을 막는다."""
    queue_flash(GRID_RESULT_KEY, literal_markdown(text), kind=kind, popup_only=True)


def queue_grid_toast(target: str, text: str) -> None:
    """오른쪽 칸 한 마운트(`"detail"`·`"new"`)에 자리 거부 한 줄을 둔다 — 고칠 입력이 그 칸에 있는
    거부뿐이다. 번호는 늘 오른다 — 브라우저는 번호가 바뀌어야 새 글로 본다(닫은 번호는 숨긴다)."""
    number = st.session_state.get(GRID_TOAST_SEQ_KEY, 0)
    number = (number if isinstance(number, int) else 0) + 1
    st.session_state[GRID_TOAST_SEQ_KEY] = number
    toasts = st.session_state.get(GRID_TOAST_KEY)
    toasts = dict(toasts) if isinstance(toasts, dict) else {}
    toasts[target] = {"id": number, "text": text}
    st.session_state[GRID_TOAST_KEY] = toasts


def grid_toasts() -> dict[str, dict[str, Any]]:
    """마운트별 지금 자리 거부 한 줄(없으면 빈 dict)."""
    toasts = st.session_state.get(GRID_TOAST_KEY)
    return {
        str(target): dict(toast)
        for target, toast in (toasts.items() if isinstance(toasts, dict) else ())
        if isinstance(toast, dict)
    }


def settle_grid_toasts(drawn: Collection[str]) -> None:
    """이 회차에 그린 마운트(`drawn` — `"detail"`·`"new"`)의 한 줄은 실어 보냈다고 적고, 실어 보낸
    뒤 마운트가 그려지지 않은 한 줄은 거둔다. 브라우저의 닫은 번호는 마운트마다 새로 시작하므로
    (탭 왕복·오른쪽 칸 왕복) 남겨 두면 닫은 한 줄이 다시 마운트할 때 되살아난다. 아직 실어 보내지
    않은 한 줄은 남겨 처음 마운트할 때 보인다. 탭 ① 이 그려진 회차의 끝과 숨은 회차(`drawn` 빈
    것)에 부른다."""
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
            _drop_changed_editors(applied.frames_changed)
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
    if applied.changed:
        _note_if_back_to_saved()


def _drop_changed_editors(changed: tuple[bool, bool, bool]) -> None:
    """내용이 바뀐 표(기존 보유대수, 설비 마스터, 비가동 일정)의 편집표 · 그 표의 삭제 대기와
    미리보기를 버린다 — 편집표의 줄 번호 delta 가 바뀐 표 위에 얹히지 않게."""
    pending = st.session_state.get(PENDING_DELETE_KEY)
    baseline_changed, _, downtime_changed = changed
    for was_changed, key, target in (
        (baseline_changed, BASELINE_EDITOR_KEY, BASELINE_TARGET),
        (downtime_changed, DOWNTIME_EDITOR_KEY, DOWNTIME_TARGET),
    ):
        if not was_changed:
            continue
        discard_editor(key)
        st.session_state.pop(f"{key}_applied_view", None)
        if isinstance(pending, tuple) and pending and pending[0] == target:
            st.session_state.pop(PENDING_DELETE_KEY, None)
    st.session_state.pop(PREVIEW_KEY, None)


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
    elif st.session_state.pop(PENDING_RENAMES_KEY, None) is not None:
        _note_if_back_to_saved()


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
    """「APW01, APW02 외 3」 — 자연 정렬 앞 `limit` 개. 정렬은 이름으로 하고 이름마다
    `literal_markdown` 으로 막아 적는다 — 이 목록은 알림 상자·미리보기 알림·거절 글(마크다운)로만
    간다. 물결표만 막으면(옛 `markdown_safe_tildes`) 「DA*31*R」 의 별표가 기울임이 되어 「DA31R」
    로 보였다(2026-10-27 E2E)."""
    ordered = sorted(names, key=natural_name_key)
    head = ", ".join(literal_markdown(name) for name in ordered[:limit])
    return head if len(ordered) <= limit else f"{head} 외 {len(ordered) - limit}"


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
    if named == file_name_part(scenario_name, fallback=_SCENARIO_FILE_FALLBACK):
        return None
    return (
        f"올린 CSV 는 다른 설비 시나리오({quoted(named.replace('_', ' '))})에서 내려받은 「현재 "
        f"데이터」 입니다 — 지금 세션은 {quoted(scenario_name)} 입니다. 배치·일정 칸이 그 "
        "시나리오의 값이면 이 시나리오의 배치·일정이 그 값으로 바뀝니다."
    )


# 「현재 데이터」 설비 마스터 내보내기 이름(`current_data_file_name`)에서 시나리오 몫을 꺼낸다.
_CURRENT_DATA_NAME = re.compile(r"equipment_master_(.+)_r\d+_c\d+(?:_edited)?_\d{8}\.csv")
# 시나리오 이름이 파일 이름에 쓸 글자를 남기지 않을 때의 토막(`table_toolbar.file_name_part`).
_SCENARIO_FILE_FALLBACK = "scenario"


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
    버리기」 가 이 값으로 되돌리고(`apply`), 배치 편집이 잠긴 회차(`space_edit_mode(...).layout ==
    "locked"`)의 붙여넣기 거절(`layout_paste_refusal`)이 이 값의 호기를 적는다.

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


def _live_rename_count() -> int:
    """저장 안 한 이름 바꿈 수 — Space 저장 안 한 배치 상자 「이름 바꿈 n건」 과 같은 셈
    (`live_renames` — 설비명·Main 설비 바꿈마다 한 건). 편집본을 다시 세우기 **전**(옛 저장본
    사본)에 센다."""
    pending = pending_unit_renames()
    buffer = st.session_state.get(BUFFER_KEY)
    if not pending or not isinstance(buffer, tuple):
        return 0
    live = live_renames(pending, _saved_master(), buffer[1])
    return len(live.units) + len(live.groups)


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
    number: str,
    *,
    overlay_dropped: int,
    reapplied: ReappliedLayout | None,
    renames_dropped: int = 0,
) -> str:
    """남의 저장으로 편집본을 다시 세운 회차의 알림(한 번). 가정 배치 편집을 새 저장본 위에 다시
    얹었으면 그 수와 빠진 호기를 따로 적는다(설계 9장) — 그 밖의 저장 안 한 편집(설비 마스터 칸·
    도면 요소·Main 설비명 위치)은 지금처럼 버렸다. 다시 얹을 편집이 남이 지운 호기에만 있었으면
    (다시 얹은 0대) 버렸다는 일반 글에 그 호기와 까닭을 적고, 그 호기는 「최신 위에서 다시
    옮기세요」 에 세지 않는다(E2E r6 — 이제 없는 호기를 다시 옮기라 했다). `renames_dropped` 는 버린
    저장 안 한 이름 바꿈 수다 — 다시 얹은 갈래는 버린 것에 「이름 바꿈 n건」 을 적는다(같은 호기의
    위치만 다시 얹고 이름은 돌아가, 적지 않으면 이름 바꿈도 남았다고 읽혔다 — E2E r6). 버린 갈래는
    「설비 편집(설비 마스터·Space 배치)을 버리고」 가 이미 모두 말한다."""
    head = f"다른 사용자가 {number}{object_particle(number)} 저장해, "
    gone = reapplied.dropped if reapplied is not None else ()
    # 알림 칸(마크다운)으로만 간다 — 설비명마다 구두점을 막는다(물결표·별표).
    names = ", ".join(literal_markdown(name) for name in gone[:3])
    names += " 외" if len(gone) > 3 else ""
    dropped = (
        f" 그 사이 공통 대장에서 빠진 호기 {len(gone):,}대({names})의 편집은 뺐습니다."
        if gone
        else ""
    )
    if reapplied is not None and reapplied.reapplied:
        renamed = f"이름 바꿈 {renames_dropped:,}건·" if renames_dropped else ""
        return (
            head + "최신 저장본으로 다시 열고 저장하지 않은 가정 배치 편집 "
            f"{reapplied.reapplied:,}대(호기 위치)는 그 위에 다시 얹었습니다.{dropped} 그 밖의 "
            f"저장하지 않은 설비 편집(설비 마스터 칸·{renamed}도면 요소·Main 설비명 위치)은 "
            "버렸습니다 — 배치를 확인하고 저장하세요."
        )
    # 남이 지운 호기의 편집은 다시 옮길 수 없다 — 그 밖의 버린 가정 배치 편집만 다시 옮기라 한다.
    rest = max(overlay_dropped - len(gone), 0)
    return (
        head
        + "이 화면에서 저장하지 않은 설비 편집(설비 마스터·Space 배치)을 버리고 최신 저장본으로 "
        "다시 열었습니다."
        + (f" 저장하지 않은 가정 배치 편집 가운데{dropped}" if gone else "")
        + (
            f" {'그 밖의' if gone else '그 가운데'} 가정 배치 편집 {rest:,}대도 버렸습니다 — 최신 "
            "위에서 다시 옮기세요."
            if rest
            else ""
        )
    )


def discard_layout_edits() -> bool:
    """「배치 변경만 버리기」 — 편집본의 배치 일곱 칸을 저장본 값으로 되돌리고(새 호기는 자리
    없이) 층 대기분(캔버스·도면 요소·Main 설비명 위치)·편집기 모듈 모양·찍힌 역할을 비운다. 공통·
    일정 칸 편집과 이름 바꿈, FAB 전체 배치 대기분은 남긴다(설계 8-6·검토 M5). 콜백에서 부른다.

    버린 뒤 설비 편집이 남았는가를 돌려준다. 남은 것이 없으면 그 세대를 저장본으로 돌아온 세대로
    적는다(`_note_if_back_to_saved`) — 버리기도 편집본을 바꿔 세대를 올린다."""
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
    _note_if_back_to_saved()
    return has_unsaved_equipment_edits()


def _note_if_back_to_saved() -> None:
    """편집본이 저장본으로 돌아왔으면 그 세대를 적어 세대 판정(`has_unsaved_equipment_edits`)이 편집
    없음으로 보게 한다 — 세대는 내용이 바뀌면 오를 뿐 내려오지 않아, 넣었다 지운 새 호기·되돌린 칸도
    「미저장 변경」 배지·머리 변경 칩·탭 점·떠나기 확인을 남겼다. 다음 편집은 세대를 올리므로
    (되돌리기로 되살림 포함) 표시가 다시 선다. 편집본 · 층 대기분을 바꾼 **뒤에** 부른다."""
    if has_unsaved_equipment_edits() and _buffer_is_saved():
        st.session_state[_CLEAN_GENERATION_KEY] = equipment_buffer_generation()


def _buffer_is_saved() -> bool:
    """편집본이 세운 저장본 사본과 내용까지 같고 저장 안 한 이름 바꿈·설비 마스터 표 칸 초안·층
    대기분이 없는가(세 표 모두 — 날짜 칸 시각 단위만 다른 것은 같다고 본다, `same_frame_content`).
    표 비교보다 싼 대기분부터 본다."""
    buffer = st.session_state.get(BUFFER_KEY)
    saved = tuple(
        st.session_state.get(key)
        for key in (BASELINE_DRAFT_KEY, EQUIPMENT_DRAFT_KEY, DOWNTIME_DRAFT_KEY)
    )
    if not isinstance(buffer, tuple) or len(buffer) != len(saved):
        return False
    if (
        pending_unit_renames()
        or grid_overlay()
        or pending_floor_canvases()
        or pending_floor_marks()
        or pending_floor_group_labels()
    ):
        return False
    return all(
        isinstance(left, pd.DataFrame)
        and isinstance(right, pd.DataFrame)
        and same_frame_content(left, right)
        for left, right in zip(saved, buffer, strict=True)
    )


def layout_paste_refusal(
    review: ImportReview,
    *,
    saved: pd.DataFrame,
    renames: Mapping[str, str],
    reason: str | None,
) -> str | None:
    """배치 편집이 잠긴 회차(`reason` — `space_edit_mode` 의 잠금 까닭)에 배치를 바꾸는 설비 마스터
    붙여넣기를 미리보기 전에 막는 글(`saved` 는 세션 저장본, `renames` 는 저장 안 한 이름 지도):
    있던 호기의 배치 칸을 저장본과 다르게 하거나, 새 호기에 자리(동·층·X좌표·Y좌표)를 넣는 것. 새
    호기 행 자체·크기·레이아웃표시는 받는다. 막을 것이 없으면 None. 잠긴 회차의 표는 배치 칸을
    잠그므로(`render_equipment_master_tab(layout_mode=)`) 이 파일의 잠긴 회차 배치 거절 글은 이것
    하나다."""
    if review.target != "설비 마스터":
        return None
    lock = layout_edits(review.candidate[1], saved, renames)
    if not lock:
        return None
    names, placed = list(lock.restore), list(lock.place)
    moves = f"있던 호기 {len(names):,}대({_sample_names(names)})의 배치 칸을"
    places = f"새 호기 {len(placed):,}대({_sample_names(placed)})에 자리(동·층·X좌표·Y좌표)를"
    if names and placed:
        what = f"{moves} 바꾸고 {places} 넣습니다"
    elif names:
        what = f"{moves} 바꿉니다"
    else:
        what = f"{places} 넣습니다"
    why = f" — {literal_markdown(reason)}" if reason else ""
    head = f"붙여넣기가 {what} — 배치 편집이 잠겨 있어 미리보지 않았습니다{why}"
    if names:
        head += " 있던 호기의 배치 칸은 빼거나 저장본 값 그대로 다시 붙여넣으세요."
    if placed:
        head += " 새 호기는 동·층·X좌표·Y좌표를 비우고 다시 붙여넣으세요."
    return head


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
    - 일괄 삭제 되살리기(`LAST_REMOVED_KEY`)는 **어느 이름이든 바꾸면** 버린다. 지운 행은 옛 이름을
      지니므로 되살리면
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
        # 표 도구 막대가 바로 위 펼침 머리의 오른쪽 끝(접는 자리)을 덮지 않게(AGENTS 9장).
        toolbar_clearance()
        st.dataframe(names, hide_index=True, width="stretch", placeholder="")
        # 이름 바꿈의 뜻 · 저장 뒤 남는 옛 이름은 풍선이다 — 자리에는 값만(설계 규칙 UI-TXT-01).
        st.caption(NAME_CHANGES_MARK, help=NAME_CHANGES_CAPTION)


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
    """미저장 캔버스를 둔다. None 이면 그 층 대기분을 지운다(저장값과 같아졌을 때). `base` 는 편집을
    시작할 때 본 저장값이다."""
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
    _note_if_back_to_saved()


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
    _note_if_back_to_saved()


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
    _note_if_back_to_saved()


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


def save_pending_fab_layout(repository: DuckDBEquipmentRepository) -> bool:
    """미저장 FAB 배치를 쓴다(설비 리비전 없음). 썼으면 대기분·도면 캐시를 비우고 True. 쓴 성공
    알림은 `FAB_SAVE_NAME` 칸에 적는다 — 대기분을 비운 뒤 닿은 같은 단추의 둘째 누름이 첫 성공을
    다시 낸다(`save_equipment_buffer`)."""
    pending = pending_fab_layout()
    if pending is None:
        return False
    marks = [mark.editor_payload() for mark in pending.marks] if pending.marks is not None else None
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    messages = notice_marks()
    # 같은 대기분의 둘째 누름(첫 콜백이 쓰고 대기분을 비우기 전에 끊김)은 다시 쓰지 않는다 — 옛 본
    # 저장값으로 가면 제 저장을 남의 저장으로 거부당한다(`write_guard.save_once`).
    wrote = save_once(
        FAB_SAVE_NAME,
        pending,
        lambda: repository.save_fab_layout(canvas=pending.canvas, marks=marks, base=pending.base),
        wrote=bool,
    )
    if wrote:
        note_notice(messages, FAB_SAVE_NAME, FAB_SAVED_MESSAGE)
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


# 빠른 두 번 누름의 둘째가 제 저장을 알아봤는데 첫 누름의 알림이 창(`TRAILING_PRESS_SECONDS`)을
# 지났을 때.
SAVED_AGAIN_MESSAGE = "설비 데이터를 저장했습니다."


def _fab_tail() -> str | None:
    """이 누름 앞에 같은 단추의 첫 누름이 FAB 대기분을 막 썼으면(`FAB_SAVE_NAME` 칸의 알림이 창
    `TRAILING_PRESS_SECONDS` 안이고 대기분이 이제 없다) 그 성공 알림. 첫 콜백이 쓰고 대기분을 비운
    뒤 닿은 둘째 누름은 쓸 것이 없어 「바뀐 내용이 없어 …」 로 방금 저장의 성공 알림을 덮었다
    (2026-10-27 E2E — FAB 만 바뀐 Space 「배치 저장」 0.15~0.5초 두 번 누름). 저장에 **들어올 때**
    본다 — 설비 쪽 대조를 마친 뒤에 보면 그 사이 창이 지날 수 있다(사외 사본 앱 브라우저 확인)."""
    return held_notice(FAB_SAVE_NAME) if pending_fab_layout() is None else None


def common_conflict_reopened(newest: str) -> str:
    """편집본을 세우기 **전**(콜백)에 돈 저장이 남의 공통 대장 저장에 거부됐을 때의 글.

    그 회차 본문이 편집본을 그 저장본으로 다시 세우며(`ensure_equipment_drafts`) 머리에 무엇을 다시
    얹고 버렸는지 알린다(`discarded_notice`). 저장소의 공용 거부 글(「화면을 다시 불러와 …」)을
    그대로 두면 그 알림과 다른 길을 말해, 안내대로 브라우저를 새로 불러온 사용자가 다시 얹은 가정
    배치 편집까지 잃었다(2026-10-27 E2E). 콜백은 다시 세우기 전에 돌아 편집이 남는지(다시 얹은
    가정 배치) 모두 버려지는지 모른다 — 끝 문장은 어느 쪽에도 맞는 말이다(남은 편집이 없는데 「남은
    편집을 확인」 하라고 하면 있지도 않은 편집을 찾는다)."""
    return (
        f"다른 사용자가 먼저 {with_object_particle(newest)} 저장해 저장하지 않았습니다 — 이 화면을 "
        "그 저장본으로 다시 열었습니다(위 알림). 최신 저장본을 확인한 뒤 다시 고쳐 저장하세요."
    )


def save_equipment_buffer(
    repository: DuckDBEquipmentRepository,
    frames: Frames | None,
    note: str,
    *,
    basis: EquipmentSaveBasis | None = None,
    saved_by: str | None = None,
    reopens: bool = False,
) -> str:
    """편집본(세 표)과 미저장 층 캔버스·도면 요소를 **한 트랜잭션**에 저장하고 알림 문구를 돌려준다.

    설비 마스터 탭 「리비전 저장」·Space 저장·사이드바 설비 시나리오 팝업 저장이 이 한 곳을
    탄다(저장소 `save_equipment` — 공통 대장·설비 시나리오 일정 가운데 **바뀐 쪽만** 쓴다. 둘 다
    그대로면 층 값만 쓰거나 아무것도 쓰지 않는다). `basis` 는 저장할 설비 시나리오와 화면이 본
    공식 번호(페이지가 세션에서 만든다 — 없으면 편집본이 나온 시나리오, 그것도 없으면 공식
    시나리오), `saved_by` 는 저장자 칸 값이다. 함께 넣기·공식 발행은 저장소 기본값 그대로 늘 한다 —
    일어난 일은 돌려주는 알림 문구가 적는다(`save_result_message`, 2026-11-05 사용자 결정). 예시 행
    가드는 repository 에 없으므로 여기서 건다. 성공하면 캐시와 편집본을 모두 비운다.

    미저장 **FAB 전체 배치**는 설비 리비전과 무관한 별도 쓰기다(`save_pending_fab_layout`). 설비
    편집보다 **먼저** 쓴다 — 설비 저장이 막혀도 FAB 는 저장된 채 남고(그 사실을 오류 문구에 적는다),
    반대 순서면 설비 저장 뒤 편집본을 비우면서 FAB 대기분까지 잃는다. FAB 가 거부돼도(남이 먼저
    저장) 설비 저장은 그대로 하고, FAB 대기분은 남긴 채 두 결과를 함께 적은 `ValueError` 를 낸다.
    `frames` 가 None 이면(설비 저장본이 없어 대조할 출발 리비전이 없는 화면) FAB 대기분만 쓴다.

    `reopens` 는 이 저장이 그 회차 편집본을 세우기 전(콜백 — 설비 마스터 「리비전 저장」·Space
    「배치 저장」)에 돈다는 뜻이다. 남이 먼저 공통 대장을 저장해 거부되면 같은 회차 본문이 편집본을
    그 저장본으로 다시 세우므로 거부 글도 그 길을 말한다(`common_conflict_reopened`).
    """
    fab_tail = _fab_tail()
    if frames is None:
        return (
            FAB_SAVED_MESSAGE
            if save_pending_fab_layout(repository)
            else fab_tail or NOTHING_SAVED_MESSAGE
        )
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
            saved_by=saved_by,
            fab_saved=fab_saved,
            fab_tail=fab_tail,
            reopens=reopens,
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


def equipment_write_token(database_path: str, scenario_id: str) -> tuple[str, str, int] | None:
    """설비 쓰기의 제 저장 판정 토큰 — (공통 대장 최신 id, 그 설비 시나리오 최신 일정 리비전 id,
    최신 공식 번호). 캐시가 아니라 저장소에서 바로 읽는다 — 거부 직후에 부른다(그 거부의 「지금
    값」). 쓰기에 성공한 쪽의 짝은 쓰기 결과로 만든다(쓴 뒤 다시 읽으면 그 사이 남의 저장이 짝에
    들어간다). 읽지 못하면 None(제 저장으로 보지 않는다 — `write_guard.is_own_save`)."""
    repository = get_equipment_repository(database_path)
    try:
        common = repository.latest_revision_id() or ""
        catalog = repository.load_scenario_catalog()
    except BOOTSTRAP_ERRORS:
        return None
    scenario = catalog.scenario(scenario_id)
    latest = scenario.latest_schedule_revision_id if scenario is not None else None
    return common, latest or "", catalog.release_no or 0


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
    saved_by: str | None,
    fab_saved: bool,
    fab_tail: str | None = None,
    reopens: bool = False,
) -> str:
    """`save_equipment_buffer` 의 설비 쪽(공통·일정 + 층 캔버스·요소 한 트랜잭션). `fab_tail` 은
    같은 단추의 첫 누름이 막 낸 FAB 저장 알림이다(`_fab_tail`) — 이 누름이 아무것도 쓰지 않으면 그
    알림을 잇는다.

    설비 마스터를 쓰는 모든 저장(설비 마스터 탭 「리비전 저장」 — 표·붙여넣기·CSV·작은 편집표 —,
    Space 배치 저장, 팝업 저장)이 이 한 곳을 지나므로 모듈 묶음 좌표·크기
    검사(`saved_master_violations` — 바뀐 묶음은 묶음 범위의 바둑판이어야 한다, 2026-10-23 사용자 답
    「막자」)도 여기서 한다."""
    violations = saved_master_violations(frames[1])
    if violations:
        raise ValueError(module_layout_message(violations))
    # 낡은 세션의 낡기 전 편집(지운 호기·고친 일정 칸)은 저장소가 공통 칸까지 거부한다 — 설비 쪽을
    # 쓰기 전에 같은 글로 멈춘다(설비 마스터 탭·사이드바 팝업·Space 배치 저장 모두 여기를 지난다).
    # 탭은 같은 판정을 「저장하기 전에 고칠 것」 줄로도 보인다(`stale_save_reasons`). FAB 대기분은
    # 별도 쓰기라 이 거부와 상관없이 앞에서 이미 썼다 — 거부 글이 그 사실을 함께 말한다.
    stale = stale_save_refusal(frames, basis)
    if stale is not None:
        raise ValueError(stale)
    base = seen(_BASE_KEY)
    if not isinstance(base, dict):
        raise ValueError("편집본이 아직 서지 않아 저장하지 않았습니다. 화면을 다시 불러오세요.")
    canvases = pending_floor_canvases()
    marks = {
        key: [mark.editor_payload() for mark in staged]
        for key, staged in pending_floor_marks().items()
    }
    labels = pending_floor_group_labels()
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
        saved_by=saved_by,
        expected_release_no=basis.release_no if basis is not None else None,
        floor_canvases=canvases,
        floor_marks=marks,
        floor_layout_bases=pending_floor_bases(),
        floor_group_labels=labels,
        expected_layout_role=_layout_role_of(
            frames[1], renames.units, floor_values=bool(canvases or marks or labels), basis=basis
        ),
    )
    own_name = f"{EQUIPMENT_SAVE_NAME}:{scenario_id}"
    expected = (request.base_common_revision_id, request.base_schedule_revision_id or "")
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    save_marks = own_save_marks()
    messages = notice_marks()
    try:
        # 출발점(`buffer_base`)은 아래 뒷정리(`reset_equipment_drafts`)가 옮긴다. 빠른 두 번 누름의
        # 둘째 회차가 첫 콜백을 DB 쓰기 뒤·뒷정리 전에 끊으면 출발점이 그대로라, 둘째 콜백이 옛
        # 출발점으로 다시 저장하다 거부되고 제 저장을 「다른 사용자가 먼저 저장」 으로 알렸다
        # (2026-10-26 E2E). 같은 출발점의 둘째 누름은 저장하지 않고 첫 결과로 뒷정리·알림을 잇는다.
        result = save_once(
            EQUIPMENT_SAVE_NAME,
            (buffer_base(), scenario_id),
            lambda: repository.save_equipment(request),
            wrote=_wrote_anything,
        )
    except EquipmentRevisionConflict as exc:
        # 창(`TRAILING_PRESS_SECONDS`)을 지나 닿은 둘째 누름은 저장소가 거부한다 — 그 거부가 제 저장
        # 짝이면 제 저장으로 알아본다.
        current = equipment_write_token(str(repository.database_path), scenario_id)
        if current is None or not is_own_save(own_name, expected, current[:2], save_marks):
            if reopens and exc.side == "common":
                # 같은 회차 본문이 편집본을 남의 저장본으로 다시 세운다 — 그 머리 알림과 같은 길을
                # 말한다(「화면을 다시 불러와」 를 따르면 다시 얹은 편집을 잃는다).
                raise ValueError(common_conflict_reopened(exc.newest)) from exc
            raise
        # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard). 첫 누름의 뒷정리
        # (편집본 비우기·세션 옮기기)가 끊겼을 수 있어 여기서 다시 하고 그 알림을 다시 낸다.
        moved = current[1] if current[1] and current[1] != expected[1] else None
        _after_equipment_save(scenario_id, moved)
        return held_notice(own_name) or SAVED_AGAIN_MESSAGE
    if result.wrote_revision:
        # 저장된 값은 이 쓰기의 결과다 — 쓴 뒤 저장소를 다시 읽으면 그 사이 남의 저장이 짝에 들어가
        # 남의 저장 뒤 충돌을 제 저장으로 알아본다(쓰기 잠금 안의 결과라 그대로 지금 최신이다).
        stored = (
            result.common.revision_id
            if result.common is not None
            else request.base_common_revision_id,
            result.schedule.schedule_revision_id
            if result.schedule is not None
            else request.base_schedule_revision_id or "",
        )
        remember_own_save(own_name, expected, stored, save_marks)
    fab = " S.PKG FAB 전체 배치도 저장했습니다." if fab_saved else ""
    # 문구는 대기분이 아니라 **저장 결과**로 만든다(검토 F18b) — 가정 역할의 도면 요소·Main 설비명
    # 위치는 층 현행값이 아니라 그 시나리오 새 리비전의 배치 차이로 갔다.
    floor_layouts = (
        floor_layout_words(canvases, marks, labels) if result.floor_values_written else ""
    )
    if not _wrote_anything(result):
        # 설비 쪽은 아무것도 쓰지 않았다. 편집본·변경 메모·선택을 그대로 둔다. 이 누름이 FAB 도 쓰지
        # 않았으면 같은 단추의 첫 누름이 방금 낸 FAB 성공 알림을 잇는다(`_fab_tail`).
        return FAB_SAVED_MESSAGE if fab_saved else fab_tail or NOTHING_SAVED_MESSAGE
    layouts = f" {floor_layouts}도 함께 저장했습니다." if floor_layouts else ""
    if not result.wrote_revision:
        message = (
            f"{NOTHING_SAVED_MESSAGE}{fab}"
            if not floor_layouts
            else f"설비 마스터가 바뀌지 않아 새 리비전 없이 {floor_layouts}만 저장했습니다.{fab}"
        )
    else:
        name = basis.scenario_name if basis is not None else None
        message = save_result_message(result, scenario_name=name) + layouts + fab
        # 둘째 누름이 제 저장을 알아보면 이 알림을 다시 낸다(`write_guard.held_notice`).
        note_notice(messages, own_name, message)
    _after_equipment_save(
        result.schedule.equipment_scenario_id if result.schedule is not None else scenario_id,
        result.schedule.schedule_revision_id if result.schedule is not None else None,
        floor_values_written=result.floor_values_written,
    )
    return message


def _after_equipment_save(
    scenario_id: str, schedule_revision_id: str | None, *, floor_values_written: bool = True
) -> None:
    """저장 뒤 이 세션의 뒷정리 — 캐시를 비우고 편집본을 저장본으로 다시 세우고, 새 일정 리비전을
    썼으면 세션을 그 리비전으로 옮긴다(`SAVED_SCHEDULE_KEY`)."""
    clear_equipment_snapshot_cache()
    if floor_values_written:
        clear_floor_layout_cache()
    # 저장한 이름 바꿈은 이제 저장본 이름이다 — 설비 마스터 탭을 그리지 않은 채(Space 에서)
    # 저장했으면 목록 필터가 따라갈 지도가 아직 남아 있으니 편집본과 함께 버리지 않는다(버리면
    # 다음 설비 마스터 탭 회차에 옛 이름이 선택지 밖이라 필터가 「전체」 로 돌아간다).
    # 버리기·남의 저장은 이름이 돌아가므로 버린다.
    followed = st.session_state.get(FOLLOWED_FILTERS_KEY)
    reset_equipment_drafts()
    if followed:
        st.session_state[FOLLOWED_FILTERS_KEY] = followed
    if schedule_revision_id is not None:
        st.session_state[SAVED_SCHEDULE_KEY] = {
            "scenario_id": scenario_id,
            "schedule_revision_id": schedule_revision_id,
        }


def _wrote_anything(result: EquipmentSaveResult) -> bool:
    """설비 저장이 무엇이든 썼는가(리비전·층 현행값·공식 발행). 아니면 편집본을 그대로 둔다."""
    return result.wrote_revision or result.floor_values_written or result.release_no is not None


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


def _spread_words(propagated: Sequence[PropagatedRevision]) -> str:
    """함께 넣은 수 한 마디 — 「다른 설비 시나리오 2개에 호기 2대 · 비가동 1건」. 같은 저장의 함께
    넣기라 시나리오마다 수가 거의 같아 가장 큰 수를 적는다(시나리오마다 수는 뒤 「함께 넣음」 문장이
    적는다)."""
    units = max(item.unit_count for item in propagated)
    downtime = max(len(item.downtime) for item in propagated)
    parts = [
        *([f"호기 {units:,}대"] if units else []),
        *([f"비가동 {downtime:,}건"] if downtime else []),
    ]
    return f"다른 설비 시나리오 {len(propagated):,}개에 {' · '.join(parts)}"


def save_result_message(result: EquipmentSaveResult, *, scenario_name: str | None) -> str:
    """저장 결과 알림 — 일어난 일만 한 번에 적는다(2026-11-05 사용자 결정 — 저장 칸 체크 · 경고를
    걷고 여기로 모았다, 설계 6-3·6-4). 알림창은 앞 60자 안팎만 보이므로(`alerts.SHORT_LIMIT`, 전문은
    Alarm) 첫 문장이 일어난 일을 무거운 차례로 적는다 — 지운 호기 수와 그 일정이 함께 빠진 다른 설비
    시나리오 수 · 공식 발행 · 함께 넣은 대수 · 건수. 그 뒤가 쓴 리비전과 시나리오마다의 내역이다."""
    written: list[str] = []
    if result.common is not None:
        written.append(f"공통 대장 r{result.common.revision_no}")
    if result.schedule is not None:
        label = f"{quoted(scenario_name)} " if scenario_name else "설비 시나리오 일정 "
        written.append(f"{label}r{result.schedule.revision_no}")
    where = " · ".join(written)
    propagated = [item for item in result.propagated if item.revision_no is not None]
    facts: list[str] = []
    if result.removed_units:
        elsewhere = (
            f"(다른 설비 시나리오 {len(result.removed_elsewhere):,}개 일정도 빠짐)"
            if result.removed_elsewhere
            else ""
        )
        facts.append(f"지운 호기 {len(result.removed_units):,}대{elsewhere}")
    if result.release_no is not None:
        facts.append(f"공식 v{result.release_no} 지정")
    if propagated:
        facts.append(_spread_words(propagated))
    head = "설비 데이터를 저장했습니다"
    summary = " · ".join(facts) or where
    sentences = [f"{head} — {summary}." if summary else f"{head}."]
    if facts and where:
        sentences.append(f"{where}.")
    if result.forced_common:
        sentences.append(
            "설비 시나리오로 옮긴 뒤 첫 저장이라 공통 대장도 새 리비전으로 함께 저장했습니다."
        )
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
    if result.release_withheld:
        sentences.append(
            "공식 설비 시나리오에 공식으로 지정하지 않은 더 새 리비전이 있어 공식 지정은 하지 "
            "않았습니다 — "
            "공식 지정은 시나리오 관리 › 설비 시나리오에서 하세요."
        )
    return " ".join(sentences)


def overlay_saved_sentence(result: EquipmentSaveResult, *, scenario_name: str | None) -> str:
    """가정 배치를 저장한 한 문장 — 그 리비전의 공식과 다른 호기 · 도면 요소 · Main 설비명 위치 수
    (0 인 것은 뺀다, Space 머리 알림과 같은 꼴 — 설계 8-2). 요소·이름표만 옮긴 저장도 무엇이
    저장됐는지 말한다. 모두 0 이면 이제 공식 배치와 같다는 말이다(차이를 모두 걷은 저장)."""
    place = quoted(scenario_name, empty="이 설비 시나리오")
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
    return f"{quoted(item.scenario_name)} r{item.revision_no}{detail}"


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
    scenario = (
        f"_{file_name_part(scenario_name, fallback=_SCENARIO_FILE_FALLBACK)}"
        if scenario_name
        else ""
    )
    schedule = latest_snapshot.schedule
    schedule_no = schedule.revision_no if schedule is not None else 0
    common_no = latest_snapshot.revision.revision_no
    return f"{table_slug}{scenario}_r{schedule_no}_c{common_no}{suffix}_{today:%Y%m%d}.csv"


def _saved_basis_words(snapshot: EquipmentSnapshot, scenario_name: str | None) -> str:
    """「저장본 r3 · 「운영 일정」 · 공통 대장 r5」 — 편집본이 나온 저장본 쌍."""
    schedule = snapshot.schedule
    head = f"저장본 r{schedule.revision_no}" if schedule is not None else "저장본 일정 없음"
    name = f" · 「{literal_markdown(scenario_name)}」" if scenario_name else ""
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
    """세 표의 **현재 데이터**를 내려받는 단추 셋 — 설비 마스터 탭 메뉴 「엑셀·CSV」 의 양식 단추
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
    # 값 한 줄(무엇을 내려받나), 편집본이 언제 드는지 · 되붙이는 법은 풍선이다(UI-TXT-01).
    st.caption(
        f"현재 데이터 · {basis} · {state}",
        help=f"{edit_note} 고치지 않고 그대로 붙여넣어도 통과합니다.",
    )
    today = date.today()
    for label, payload, slug, key, frame in zip(
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
        # 빈 표도 막지 않는다. 헤더만 든 파일이 곧 정확한 컬럼 차례의 양식이고, 그대로
        # 붙여넣으면 0행으로 읽혀 아무것도 바꾸지 않는다. 양식 단추처럼 세로로 쌓는다 — 나란히
        # 두면 칸 폭에 이름이 잘려 행 수가 「64…」 로 읽혔다(설계 규칙 UI-ACC-02).
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


def _example_row_count(frames: Frames) -> int:
    """편집본에서 저장이 막을 예시 행 수(기존 보유대수 — `_example_baseline_rows`)."""
    return len(_example_baseline_rows(frames[0]))


def _drop_example_rows() -> None:
    """「예시 행 n건 지우기」 — 예시 행을 편집본에서 빼고 세션 표지를 남긴다.

    표지(`DROP_EXAMPLE_ROWS_KEY`)가 있으면 이후의 모든 `build_import_review` 가 merge 전에 같은
    행을 뺀다 — 원문이 그대로라 다시 미리보면 예시 줄이 또 들어오기 때문이다. 편집본은 표 밖 길
    (`replace_equipment_buffer`)로 바꾼다 — 남은 붙여넣기 미리보기·삭제 대기도 다른 길처럼 거둔다
    (미리보기는 「엑셀·CSV로 한꺼번에」 팝업이 다시 짓는다 — 그 팝업만 배치 역할·「배치 칸도
    붙여넣기」·공식 자리를 안다).

    **저장 검증은 건드리지 않는다.** 이것은 저장을 눌러야 알던 것을 누르기 전에 말하고
    한 번에 지우는 길일 뿐이다. 콜백은 위젯이 만들어지기 전에 돌므로 editor 키를 비우는
    것이 안전하고, `st.rerun` 은 부르지 않는다 — `on_click` 이 이미 한 회차를 돌린다.

    단추는 예시 행이 있을 때만 서므로 뺄 행이 없는 누름은 더블클릭의 둘째(첫 회차가 단추를 다시
    그리기 전의 옛 화면)다 — 편집본을 다시 세우지도 「예시 행 0건을 …」 으로 첫 알림을 덮지도
    않는다. 알림은 쓰기 알림 표지에도 적어(`note_notice`) 그 둘째 회차가 지우지 않게 한다(2026-10-27
    E2E 「삭제 확정」 과 같은 결함류).
    """
    notices = notice_marks()
    frames: Frames = st.session_state[BUFFER_KEY]
    removed = _example_row_count(frames)
    if not removed:
        return
    st.session_state[DROP_EXAMPLE_ROWS_KEY] = True
    replace_equipment_buffer((_without_example_rows(frames[0]), frames[1], frames[2]))
    message = (
        f"예시 행 {removed:,}건을 편집본에서 뺐습니다. 다음 붙여넣기·CSV 미리보기도 예시 행을 빼고 "
        "검토합니다 — 저장 검증은 그대로 돕니다."
    )
    note_notice(notices, _NOTICE_KEY, message, kind="info")
    queue_flash(_NOTICE_KEY, message, kind="info")


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
        # 가정 세션에서 「배치 칸도 붙여넣기」 를 끄면 있던 호기의 배치 칸은 읽을 때부터 지금
        # 값이다 — 넣지 않을 배치 값의 검증 오류가 미리보기를 막았다(2026-10-30 E2E).
        hold_layout = layout_role == "overlay" and not paste_layout
        try:
            paste = read_equipment_update(
                payload,
                equipment,
                floor_canvases=floor_canvases,
                notices=notices,
                keep_current=SCENARIO_LAYOUT_COLUMNS if hold_layout else (),
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
            layout_note = _paste_layout_review(
                equipment,
                paste.held_rows if hold_layout else incoming,
                role=layout_role,
                held=hold_layout,
                official_places=official_places or {},
            )
            if layout_note is not None:
                (notices if hold_layout else cautions).append(layout_note)
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
        # 가정 세션에서 「배치 칸도 붙여넣기」 를 끄면 붙여넣은 배치 열은 있던 호기에 들지 않는다 —
        # 「붙여넣은 열 n개(…)만 바꿉니다」 가 그 열을 바꾸는 열로 세면 앞 줄과 어긋났다(E2E).
        held = layout_pasted if hold_layout else []
        scope = _paste_scope_notice(
            paste, new_rows=int(changes["Import구분"].eq("신규").sum()), held=held
        )
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
                f"{describe_case_variants(paste.case_variants, shown=literal_markdown)}. 같은 "
                "설비면 설비명을 기존 표기 "
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
    pasted: pd.DataFrame | None,
    *,
    role: str,
    held: bool,
    official_places: Mapping[str, Place],
) -> str | None:
    """붙여넣기의 배치 일곱 칸 몫 한 줄. 있던 호기(편집본에 있는 설비명) 가운데 붙여넣은 배치가
    지금과 다른 것만 본다(새 호기의 배치 칸은 늘 받는다).

    `held`(가정 세션 「배치 칸도 붙여넣기」 끔)이면 있던 호기의 배치 칸은 읽을 때부터 지금 값이라
    (`read_equipment_update` 의 `keep_current`) `pasted` 는 붙여넣은 그대로의 그 호기 행
    (`EquipmentPaste.held_rows`)이고 「넣지 않았다」 고 적는다. 아니면 받을 행이다."""
    if pasted is None:
        return None
    current = _name_places(equipment)
    moved: list[tuple[int, str, Place]] = []
    for name, (position, place) in _name_places(pasted).items():
        if name in current and current[name][1] != place:
            moved.append((position, name, place))
    if not moved:
        return None
    sample = _sample_names([name for _, name, _ in moved])
    if role == "official":
        cells = sum(
            sum(1 for before, after in zip(current[name][1], place, strict=True) if before != after)
            for _, name, place in moved
        )
        return (
            f"공식 배치 {cells:,}칸(호기 {len(moved):,}대 — {sample})이 바뀝니다 — 공식 설비 "
            "시나리오의 배치는 모든 가정 설비 시나리오에서 손대지 않은 호기가 따라갑니다."
        )
    if held:
        return (
            f"있던 호기 {len(moved):,}대({sample})의 배치 칸은 붙여넣지 않고 지금 값을 "
            f"두었습니다 — 바꾸려면 「{PASTE_LAYOUT_LABEL}」 를 켜고 다시 미리보세요."
        )
    back = sum(
        1 for _, name, place in moved if name in official_places and place == official_places[name]
    )
    tail = f"(그 가운데 {back:,}대는 공식 자리로 돌아가 차이가 지워집니다)" if back else ""
    return (
        f"가정 배치 {len(moved):,}대({sample})가 바뀝니다{tail} — 이 설비 시나리오에만 저장되고 "
        "공식 배치는 바뀌지 않습니다."
    )


def _paste_scope_notice(
    paste: EquipmentPaste, *, new_rows: int, held: Sequence[str] = ()
) -> str | None:
    """붙여넣은 열과 그대로 두는 열을 한 줄로. 모든 열을 붙여넣었으면 말할 것이 없다.

    `held` 는 붙여넣었지만 있던 호기에는 넣지 않는 열이다(가정 세션 「배치 칸도 붙여넣기」 끔 —
    배치 일곱 칸은 새 호기에만 든다). 바꾸는 열에서 빼고 따로 한 문장으로 적는다."""
    kept = paste.kept_columns
    if not kept:
        return None
    held = [column for column in paste.columns if column in held]
    pasted = [
        column for column in paste.columns if column != EQUIPMENT_ID_COLUMN and column not in held
    ]
    # 짧은 쪽 이름을 적는다 — 서른 개를 늘어놓으면 읽히지 않는다.
    if not pasted:
        text = "기존 호기는 바꾸는 열이 없습니다."
    elif len(pasted) <= len(kept):
        text = (
            f"붙여넣은 열 {len(pasted)}개({' · '.join(pasted)})만 바꿉니다 — 나머지 "
            f"{len(kept)}개 열은 기존 호기의 값을 그대로 둡니다."
        )
    else:
        text = (
            f"붙여넣은 열 {len(pasted)}개만 바꿉니다 — 붙여넣지 않은 {len(kept)}개 열"
            f"({' · '.join(kept)})은 기존 호기의 값을 그대로 둡니다."
        )
    if held:
        text += f" 붙여넣은 배치 칸({' · '.join(held)})은 새 호기에만 넣습니다."
    if new_rows:
        blank = "붙여넣지 않은 열이" if held else "그 열이"
        text += f" 새 호기 {new_rows:,}건은 {blank} 빈칸입니다."
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
    apply_key: str,
) -> tuple[TableView, TableView, bool]:
    """(화면에 적용된 보기, 방금 고른 보기, 「보기 적용」 누름). 두 보기는 「보기 적용」 전까지
    다를 수 있다. 부르는 쪽이 표 위 작업 줄 안에서 부른다 — 「표 보기 ▾」 팝오버가 그 줄 끝에 서고
    (2026-11-09 사용자 보드 T5) 단추는 고르는 칸이 든 팝오버 맨 끝에 선다(설계 규칙 UI-LAY-03) —
    빈 표는 팝오버가 없어 누를 것도 없다."""
    pressed = False

    def apply_button() -> None:
        nonlocal pressed
        pressed = st.button("보기 적용", key=apply_key)

    view_key = f"{key}_applied_view"
    applied = st.session_state.get(view_key)
    requested = render_table_view_controls(
        data,
        key_prefix=prefix,
        # 보기를 바꾼 제출에도 이전 화면의 행 위치로 delta를 먼저 해석해야 한다.
        editor_key=f"{key}_requested_view",
        filter_columns=filters,
        locked_columns=locked,
        footer=apply_button,
        # 「표 보기 · 필터」 표지는 편집표에 건 보기를 따른다 — 이 표는 폼 밖이라 고르는 즉시 회차가
        # 돌고, 「보기 적용」 전에는 표가 거르지 않고 행 추가 · 삭제도 열려 있다(UI-DAT-11).
        applied_filtered=applied.filtered if isinstance(applied, TableView) else None,
    )
    if not isinstance(applied, TableView):
        applied = requested
        st.session_state[view_key] = applied
    return applied, requested, pressed


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


def selection_menu_generation_key(slug: str) -> str:
    """작은 편집표 「선택 ▾」 메뉴의 세대 칸(`SELECTION_MENU_LABEL`)."""
    return f"equipment_{slug}_selection_menu_generation_v1"


def _close_selection_menu(slug: str) -> None:
    """「선택 ▾」 메뉴 「선택 행 삭제」 의 콜백 — 세대를 올려 메뉴를 닫는다(다음 그림이 새
    메뉴다)."""
    bump(selection_menu_generation_key(slug))


def _selection_buttons(slug: str, *, delete_locked: str | None = None) -> str | None:
    """작은 편집표 **위** 작업 줄의 「모두 선택」 단추와 「선택 ▾」 메뉴(「선택 해제」 · 「선택 행
    삭제」 — 2026-11-10 사용자 답 Q-14) — 부르는 쪽의 가로 칸 안에 선다(「편집본에 적용」 과 한 줄,
    설계 규칙 UI-LAY-11). 누른 것의 이름을 돌려준다. 단추 값은 표보다 먼저 만들어도 같은 회차의
    편집·선택이 함께 들어온다. 필터·삭제·저장의 관계는 가용설비 현황 Guide 가 말한다.
    `delete_locked` 를 주면 「선택 행 삭제」 를 끄고 그 까닭을 풍선으로 보인다(낡은 세션의 비가동
    일정). 「선택 행 삭제」 는 누르면 메뉴를 닫고 「선택 해제」 는 열어 둔다
    (`SELECTION_MENU_LABEL`) — 단추 key 는 그대로다.
    """
    matching = st.button(
        "모두 선택",
        key=f"equipment_{slug}_select_matching_v1",
        icon=":material/checklist:",
        help="「표 보기」 의 필터에 맞는 행을 모두 고릅니다.",
    )
    generation = selection_menu_generation_key(slug)
    with st.popover(
        SELECTION_MENU_LABEL,
        icon=SELECTION_MENU_ICON,
        key=widget_key(f"equipment_{slug}_selection_menu_v1", generation, bare_zero=False),
    ):
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
            help=literal_markdown(delete_locked) if delete_locked is not None else None,
            on_click=_close_selection_menu,
            args=(slug,),
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


# 「삭제 확정」 풍선이자 결과 알림의 끝 문장 — 확정은 편집본만 바꾼다.
DELETE_CONFIRM_HELP = (
    "확정해도 「저장 전 변경」 의 「리비전 저장」 을 눌러야 새 리비전에 반영되고, 그 전에는 같은 "
    "칸의 「한 단계 되돌리기」 로 되살립니다."
)


def _deletion_value(plan: DeletionPlan) -> str:
    """삭제 확인 줄의 값 한 줄 — 무엇을 몇 건 지우나(설계 규칙 UI-NTF-09 — 되돌릴 수 있는 삭제라
    문장 · 대상 목록을 늘어놓지 않는다)."""
    count = plan.target_count
    if plan.target == BASELINE_TARGET:
        return f"기존 보유대수 {count:,}행 지움"
    return f"비가동 일정 {count:,}건 지움"


def _deletion_message(plan: DeletionPlan) -> str:
    """작은 편집표(기존 보유대수·비가동 일정)에서 무엇이 얼마나 빠졌는지 — 「삭제 확정」 결과 알림.
    호기 지우기는 설비 마스터 표의 출납(`delete` — 딸린 비가동 함께, 결과 알림)이다."""
    count = plan.target_count
    # 알림 칸(마크다운)으로만 간다 — 키에 든 설비명·공정명마다 구두점을 막는다(물결표·별표).
    samples = ", ".join(literal_markdown(key) for key in plan.sample_keys())
    more = " 외" if count > len(plan.sample_keys()) else ""
    if plan.target == BASELINE_TARGET:
        head = f"기존 보유대수 {count:,}행을 편집본에서 지웠습니다"
    else:
        head = f"비가동 일정 {count:,}건을 편집본에서 지웠습니다"
    return f"{head}. 대상: {samples}{more}. {DELETE_CONFIRM_HELP}"


def _render_bulk_delete_status(frames: Frames) -> tuple[bool, bool]:
    """확인 대기 중인 삭제를 작은 편집표 위에 말한다. (확정, 취소)."""
    confirm = cancel = False
    pending = st.session_state.get(PENDING_DELETE_KEY)
    if isinstance(pending, tuple) and len(pending) == 2:
        target, keys = pending
        # 계획은 **지금 편집본**으로 다시 세운다. 대기하는 동안 편집이 있었으면 수가 바뀐다.
        plan = plan_deletion(frames, target, keys)
        if plan.target_count:
            with st.container(horizontal=True, gap="small", vertical_alignment="center"):
                st.caption(_deletion_value(plan), width="content")
                confirm = st.button(
                    "삭제 확정",
                    key=CONFIRM_DELETE_BUTTON_KEY,
                    type="primary",
                    icon=":material/delete_forever:",
                    help=DELETE_CONFIRM_HELP,
                )
                cancel = st.button("취소", key=CANCEL_DELETE_BUTTON_KEY, icon=":material/close:")
    return confirm, cancel


def _apply_bulk_actions(editor: EditorResult, *, confirm: bool, view_applied: bool) -> bool:
    """선택 · 삭제를 편집본에 반영한다. `_remember_edits` 뒤에 부른다. 삭제를 확정했으면 참이다.

    **확인 대기는 어떤 제출이든 한 번 쓰고 버린다.** 삭제 버튼이 다시 세우지 않는 한 남지
    않는다 — 확인 상자가 누른 순간보다 오래 살아 있으면 나중에 다른 뜻으로 눌린다.

    「삭제 확정」 의 결과 알림은 쓰기 알림 표지에도 적는다(`note_notice` — 종류 info). 사람 속도의
    더블클릭은 둘째 누름이 이미 사라진 단추(첫 회차가 확인 대기를 꺼냈다)에 닿아 아무것도 하지 않는
    회차가 되는데, 첫 회차가 꺼내 그린 알림을 그 회차가 다시 그리며 지웠다(2026-10-27 E2E 「삭제
    확정」 5/9). 표지가 창(`TRAILING_PRESS_SECONDS`) 안이면 알림 칸(`render_flash`)이 같은 꼴로 다시
    그린다. 표지 dict 는 편집본을 바꾸기 **전에** 받는다.

    확정한 삭제는 표의 되돌리기를 비운다(`_forget_grid_undo`) — 그 뒤로 삭제가 「한 단계
    되돌리기」 의 맨 위이고, 그 위에 쌓인 표 조작부터 되돌린 다음 삭제를 되살린다
    (`restore_bulk_deletion`).
    """
    notices = notice_marks()
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
                queue_flash(
                    _NOTICE_KEY,
                    "선택한 행이 없습니다. 표의 ‘선택’ 칸을 켜거나 ‘모두 선택’을 누른 뒤 지우세요.",
                    kind="info",
                )
    elif confirm and isinstance(pending, tuple):
        target, keys = pending
        plan = plan_deletion(frames, target, keys)
        _store_changed_buffer(apply_deletion(frames, plan))
        _forget_grid_undo()
        done = _deletion_message(plan)
        note_notice(notices, _NOTICE_KEY, done, kind="info")
        st.session_state[LAST_REMOVED_KEY] = plan.removed
        selection[target] = frozenset()
        queue_flash(_NOTICE_KEY, done, kind="info")
        st.session_state[SELECTION_KEY] = selection
        return True
    st.session_state[SELECTION_KEY] = selection
    return False


def restore_bulk_deletion() -> bool:
    """방금 한 일괄 삭제를 되살린다(「한 단계 되돌리기」 — 표 단계가 다 빠진 뒤). 되살릴 것이 없으면
    거짓.

    콜백에서 불려 편집표 위젯이 아직 서지 않았고 그 결과(적용 전 편집을 얹은 표)도 모른다. 되살린
    표의 편집표는 줄 번호 delta 가 바뀐 표 위에 얹히지 않게 새로 세워야 하는데, 그 표에 적용하지
    않은 편집이 있으면 그것까지 알림 없이 버린다(화면 탭을 옮길 때는 묻고 지키는 편집이다). 그때는
    표지(`RESTORE_REQUEST_KEY`)만 세운다 — 그 표 편집표가 선 회차의 제출(`render_small_editor`)이
    편집을 먼저 편집본에 넣고 되살린다(작은 편집표 단추 제출과 같은 차례). 편집이 없으면 곧바로
    되살린다(`_restore_removed`)."""
    removed = st.session_state.get(LAST_REMOVED_KEY)
    if not isinstance(removed, tuple):
        st.session_state.pop(LAST_REMOVED_KEY, None)
        return False
    for name in small_editor_edits():
        if not removed[TARGET_LAYOUT[name][0]].empty:
            st.session_state[RESTORE_REQUEST_KEY] = name
            return True
    return _restore_removed()


def defer_grid_undo() -> bool:
    """표의 맨 위 단계가 바꿀 작은 편집표(기존 보유대수·비가동 일정)에 적용하지 않은 편집이 있으면
    되돌리기를 미루고 참이다. 되돌리면 그 표의 편집표를 새로 세워야 해(줄 번호 delta 가 바뀐 표에
    얹히지 않게) 적용 전 편집이 말없이 사라졌다(X1). 표지(`GRID_UNDO_REQUEST_KEY`)만 세우고 그 표
    편집표가 선 회차의 제출(`render_small_editor` 의 `undo`)이 편집을 먼저 넣고 되돌린다 — 일괄 삭제
    되살리기(`restore_bulk_deletion`)와 같은 차례다."""
    steps = grid_undo_steps()
    if not steps:
        return False
    touched = undo_step_tables(steps[-1])
    for name in small_editor_edits():
        if touched[TARGET_LAYOUT[name][0]]:
            st.session_state[GRID_UNDO_REQUEST_KEY] = name
            return True
    return False


def settle_grid_undo(undo: Callable[[], None]) -> None:
    """미룬 표 단계 되돌리기의 표를 이번 회차에 그리지 않으면 곧바로 되돌린다 — 누른 회차가 끊긴
    사이 표 고르기를 바꿨다(그 표의 적용 전 편집은 그리지 않아 어차피 걷힌다)."""
    request = st.session_state.get(GRID_UNDO_REQUEST_KEY)
    if request is not None and request != st.session_state.get(MASTER_TABLE_KEY):
        st.session_state.pop(GRID_UNDO_REQUEST_KEY, None)
        undo()


def _undo_lines_up(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    """표 단계의 역 patch(줄 자리 기준)가 편집을 넣은 표에도 맞는가 — 편집이 표 내용을 바꾸지
    않았거나(「선택」 칸만 고름 등 — 통째 단계여도 표가 그대로라 맞는다), 통째 단계가 아니고 편집이
    줄을 지우거나 옮기지 않았을 때(칸 고침 · 끝에 더한 줄)다. 값이 그대로인 편집을 맞지 않는다고
    보면 편집본이 그대로라 되돌리기를 비우지도 않아 단추가 말없이 듣지 않는다."""
    steps = grid_undo_steps()
    if not steps:
        return False
    if same_frame_content(before, after):
        return True
    if steps[-1].kind == "whole" or len(after) < len(before):
        return False
    return list(after.index[: len(before)]) == list(before.index)


def settle_bulk_restore() -> None:
    """미룬 되살리기(`RESTORE_REQUEST_KEY`)의 표를 이번 회차에 그리지 않으면 곧바로 되살린다 — 누른
    회차가 끊긴 사이 표 고르기를 바꿨다(그 표의 적용 전 편집은 그리지 않아 어차피 걷힌다). 그대로
    두면 나중에 그 표를 열 때 말없이 되살아난다. 탭 ① 이 편집본을 읽기 **전에** 부른다."""
    request = st.session_state.get(RESTORE_REQUEST_KEY)
    if request is not None and request != st.session_state.get(MASTER_TABLE_KEY):
        _restore_removed()


def _restore_removed() -> bool:
    """`LAST_REMOVED_KEY` 의 행을 편집본에 되살리고 그 표 편집표를 새로 세운다(다른 표는 남는다).
    미룬 표지도 거둔다. 결과는 탭 끝 칸이 알림창으로 낸다 — 표 고르기가 어느 표든 그 칸은 선다.
    표지 dict 는 편집본을 바꾸기 **전에** 받는다(`_apply_bulk_actions` 와 같다)."""
    st.session_state.pop(RESTORE_REQUEST_KEY, None)
    removed = st.session_state.pop(LAST_REMOVED_KEY, None)
    if not isinstance(removed, tuple):
        return False
    notices = notice_marks()
    frames: Frames = st.session_state[BUFFER_KEY]
    restored, skipped = restore_rows(frames, removed)
    _store_changed_buffer(restored)
    _drop_changed_editors((not removed[0].empty, False, not removed[2].empty))
    message = "방금 지운 행을 편집본에 되살렸습니다."
    if skipped:
        message += f" 그 사이 같은 키가 다시 생긴 {skipped:,}행은 건너뛰었습니다."
    note_notice(notices, GRID_RESULT_KEY, message, kind="info")
    queue_grid_result(message, kind="info")
    return True


# 설비 마스터 탭 「저장 전 변경」 저장자 칸 key 접두어(`equipment_save_fields`) — 옛 설비 마스터 탭
# 폼과 같은 글자라 저장자 칸이 배포를 건너 이어진다.
SAVE_FIELDS_PREFIX = "equipment_workspace_save"
# 붙여넣기·CSV 「배치 칸도 붙여넣기」(설비 시나리오 2단계 S3 — Q2). 가정 설비 시나리오에서만 서고
# 기본 끔이다 — 「현재 데이터」 CSV 는 합친 값을 내보내 공식 CSV 를 올리면 배치안이 공식 자리로
# 돌아가 정규화로 지워진다. 끄면 있던 호기의 배치 칸은 지금 값을 두고 새 호기의 배치 칸만 받는다.
PASTE_LAYOUT_KEY = "equipment_import_paste_layout_v1"
PASTE_LAYOUT_LABEL = "배치 칸도 붙여넣기"
PASTE_LAYOUT_HELP = (
    "가정 설비 시나리오의 배치(동·층·X좌표·Y좌표·Xsize·Ysize·레이아웃표시)는 이 시나리오의 배치 "
    "차이로만(공식과 다른 것만) 저장됩니다. 끄면 있던 호기의 배치 칸은 지금 값 그대로 두고 새 "
    "호기의 배치 칸만 받습니다."
)


def _stale_lock_message(basis: EquipmentSaveBasis) -> str:
    """낡은 세션의 잠금 알림 — 무엇이 잠겼고 어떻게 풀리는지. 설비 마스터 표(JS) 잠금 글(평문)에도
    가는 날 이름 글이라, 경고 상자는 그리는 자리에서 글 통째로 `literal_markdown` 한다."""
    latest = f"r{basis.latest_revision_no}" if basis.latest_revision_no is not None else "최신"
    return (
        f"「{basis.scenario_name}」 {latest}{subject_particle(latest)} 더 새롭습니다 — 지금 보는 "
        f"r{basis.revision_no}에서는 일정 여섯·시나리오 메모 칸과 비가동 일정 표, 행 추가, "
        "호기·비가동 지우기를 잠갔습니다. 일정을 고치거나 호기를 지우려면 사이드바 "
        f"「설비 시나리오」 에서 최신 {with_object_particle(latest)} 불러오세요. 공통 칸(기존 "
        "보유대수 지우기 포함)은 그대로 고쳐 저장됩니다 — 낡기 전에 고친 일정·시나리오 메모 칸은 "
        "「저장 전 변경」 에서 되돌려야 저장됩니다."
    )


def stale_delete_lock(basis: EquipmentSaveBasis) -> str:
    """낡은 세션에서 호기·비가동 「선택 행 삭제」 를 끈 까닭(단추 풍선). 호기를 지우면 그 호기의
    일정 행도 이 설비 시나리오에서 빠져 일정이 바뀐 저장이 되고, 낡은 리비전 위의 일정 저장은
    저장소가 늘 거부한다 — 지운 편집을 버려야 했다."""
    latest = f"r{basis.latest_revision_no}" if basis.latest_revision_no is not None else "최신"
    return (
        f"지금 보는 {with_topic_particle(f'r{basis.revision_no}')} 「{basis.scenario_name}」 "
        "최신이 아니라 지울 수 없습니다 — 호기·비가동을 지우면 이 설비 시나리오의 일정도 바뀝니다. "
        f"최신 {with_object_particle(latest)} 불러온 뒤 지우세요."
    )


# 낡은 세션의 저장을 막는 까닭 두 가지 — 고칠 자리만 저장 길마다 다르다. 설비 마스터 탭은 「저장하기
# 전에 고칠 것」 줄(그 아래 목록이 「저장 전 변경」 이다)로, 표 밖 저장 자리(사이드바 설비 시나리오
# 팝업 「저장」·Space 「배치 저장」)는 경고·거부 글로 같은 판정(`stale_save_reasons`)을 보인다.
STALE_DELETED_UNITS_TAB = (
    "낡은 세션이라 지운 호기 {units:,}대는 저장되지 않습니다(버려질 호기: {names}) — 되살리거나 "
    "최신을 불러오세요"
)
STALE_SCENARIO_EDITS_TAB = (
    "낡은 세션이 되기 전에 고친 일정·시나리오 메모 칸 {cells:,}개(호기 {units:,}대)는 저장되지 "
    "않습니다(버려질 칸: {spots}) — 아래 목록에서 그 칸을 되돌리면(↶) 공통 칸은 저장됩니다. 일정을 "
    "살리려면 최신을 불러와 다시 고칩니다"
)
STALE_DELETED_UNITS_ELSEWHERE = (
    "낡은 세션이라 지운 호기 {units:,}대는 저장되지 않습니다(버려질 호기: {names}) — 가용설비 "
    "현황 › 설비 마스터에서 되살리거나 최신을 불러오세요."
)
STALE_SCENARIO_EDITS_ELSEWHERE = (
    "낡은 세션이 되기 전에 고친 일정·시나리오 메모 칸 {cells:,}개(호기 {units:,}대)는 저장되지 "
    "않습니다(버려질 칸: {spots}) — 가용설비 현황 › 설비 마스터 「저장 전 변경」 에서 그 칸을 "
    "되돌리면(↶) 공통 칸은 저장됩니다. 일정을 살리려면 최신을 불러와 다시 고칩니다."
)
# 버려질 칸·호기 목록에 이름을 적는 호기 수(나머지는 「외 n대」).
STALE_LISTED_UNITS = 3


def stale_spots_words(spots: Sequence[tuple[str, Sequence[str]]]) -> str:
    """버려질 칸 목록 — 「EQ-01 반입일정·Qual일정, EQ-02 시나리오 메모 외 2대」(앞 셋)."""
    shown = ", ".join(f"{name} {'·'.join(columns)}" for name, columns in spots[:STALE_LISTED_UNITS])
    rest = len(spots) - STALE_LISTED_UNITS
    return f"{shown} 외 {rest:,}대" if rest > 0 else shown


def stale_names_words(names: Sequence[str]) -> str:
    """버려질 호기 목록 — 「EQ-03, EQ-04 외 1대」(앞 셋)."""
    shown = ", ".join(names[:STALE_LISTED_UNITS])
    rest = len(names) - STALE_LISTED_UNITS
    return f"{shown} 외 {rest:,}대" if rest > 0 else shown


def stale_save_reasons(
    master: pd.DataFrame,
    saved_master: pd.DataFrame,
    renames: Mapping[str, str],
    *,
    in_tab: bool,
) -> list[str]:
    """낡은 세션의 저장을 막을 까닭 줄 — 낡기 전에 지운 저장본 호기와 고친 일정·시나리오 메모 칸.

    낡은 세션인지는 부르는 쪽이 본다. 일정이 바뀐 저장은 저장소가 늘 거부하고
    (`EquipmentRevisionConflict` — 공통 칸까지) 그 문구는 「화면을 다시 불러와」 만 말해 다시
    불러오면 공통 편집까지 잃는다. 그래서 저장 전에 그 칸과 고칠 길(그 칸을 되돌리면 공통 칸은
    저장된다)을 알린다. 세 저장 길이 이 한 판정을 쓴다 — 설비 마스터 탭의 고칠 것 줄(`in_tab`),
    사이드바 팝업 「저장」 의 경고 글, 저장(`save_equipment_buffer`)의 거부 글. 견줌은 「바뀐 칸」
    표지와 같은 글자 견줌(`stale_scenario_edit_spots`)이고, 버려질 칸·호기는 앞 셋까지 이름을 적는다
    (나머지는 「외 n대」). 탭 줄은 평문 자리(설비 마스터 표)라 이름을 날로, 표 밖 줄은 마크다운
    자리(경고·거부 글)라 이름마다 `literal_markdown` 으로 막는다. 비가동 일정 표의 낡기 전 편집은
    세지 않는다(저장소가 거부한다)."""
    deleted_line, edits_line = (
        (STALE_DELETED_UNITS_TAB, STALE_SCENARIO_EDITS_TAB)
        if in_tab
        else (STALE_DELETED_UNITS_ELSEWHERE, STALE_SCENARIO_EDITS_ELSEWHERE)
    )

    def mark(name: str) -> str:
        return name if in_tab else literal_markdown(name)

    lines: list[str] = []
    index = grid_index(master, saved_master, renames)
    deleted = [mark(name) for row_id in index.deleted if (name := index.saved_name(row_id))]
    if index.deleted:
        lines.append(
            deleted_line.format(units=len(index.deleted), names=stale_names_words(deleted))
        )
    spots = [
        (mark(name), columns)
        for name, columns in stale_scenario_edit_spots(master, saved_master, renames)
    ]
    if spots:
        cells = sum(len(columns) for _, columns in spots)
        lines.append(
            edits_line.format(cells=cells, units=len(spots), spots=stale_spots_words(spots))
        )
    return lines


def stale_save_refusal(frames: Frames, basis: EquipmentSaveBasis | None) -> str | None:
    """표 밖 저장 자리가 알릴 낡은 세션 저장 거부 글(`stale_save_reasons`). 없거나 낡은 세션이
    아니면 None — 사이드바 팝업 「저장」 은 경고 글에, 저장(`save_equipment_buffer`)은 거부 글에
    쓴다."""
    if basis is None or not basis.stale:
        return None
    lines = stale_save_reasons(
        frames[1], _saved_master(), pending_unit_renames().units, in_tab=False
    )
    return " ".join(lines) or None


def stale_paste_refusal(
    review: ImportReview, current: Frames, basis: EquipmentSaveBasis
) -> str | None:
    """낡은 세션에서 일정 쪽을 바꾸는 붙여넣기를 미리보기 전에 막는다. 막을 것이 없으면 None.

    비가동 일정은 표 전체가 시나리오 쪽이라 늘 막고, 설비 마스터는 새 호기 행이나 일정 일곱 칸이
    바뀌는 행이 있으면 막는다(공통 칸만 바꾸는 붙여넣기는 통과).
    """
    latest = f"r{basis.latest_revision_no}" if basis.latest_revision_no is not None else "최신"
    way_out = (
        f" 사이드바 「설비 시나리오」 에서 최신 {with_object_particle(latest)} 불러온 뒤 다시 "
        "미리보세요."
    )
    if review.target == "비가동 일정":
        if not same_frame_content(review.candidate[2], current[2]):
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
    시나리오 일정으로 간다). 새 호기·새 비가동은 저장할 때 다른 설비 시나리오에 함께 넣는다(실제로
    퍼진 목록은 저장 결과 알림이 적는다). 바뀐 것이 없으면 None.
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
        f"새 비가동 {new_downtime:,}"
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
# 탭 ① 맨 위 줄 표 고르기(설비 마스터·기존 보유대수·비가동 일정)의 위젯 key — 값은 표 이름이다.
# 그리는 쪽은 `equipment_master_tab.TABLE_KEY`(같은 값)이고, 작은 편집표가 이번 회차에 그려지는지
# (`small_editor_edits`)를 여기서 본다 — 탭 줄은 그 모듈을 부르지 않는다.
MASTER_TABLE_KEY = "equipment_master_table_v1"
SMALL_EDITOR_NOTE = (
    "적용하지 않은 편집은 탭이나 화면을 옮기면 사라집니다(탭 이름 옆 점이 알리고, 화면 탭을 "
    "옮길 때는 묻습니다) — 「편집본에 적용」 을 누른 뒤 옮깁니다. 저장은 오른쪽 「저장 전 변경」 "
    "한 곳입니다."
)
# 작은 편집표의 필수 칸(`required=True`). Streamlit 은 필수 칸이 빈 새 줄을 서버에 보내지 않아
# (브라우저가 그 줄을 편집 상태에서 빼고, 적용 뒤 편집표를 다시 세우면 사라진다) 버린 줄 수를 셀 수
# 없다 — 넣기 전에 알린다.
SMALL_EDITOR_REQUIRED = {
    BASELINE_TARGET: ("공정", "분류", "기존 보유대수"),
    DOWNTIME_TARGET: (EQUIPMENT_ID_COLUMN, "비가동유형", "시작일"),
}


def small_editor_required_note(target: str) -> str:
    """작은 편집표 아래 한 줄 — 필수 칸을 다 채우지 않은 새 줄은 「편집본에 적용」 때 버려진다."""
    columns = "·".join(SMALL_EDITOR_REQUIRED[target])
    return (
        f"새 줄은 필수 칸({columns})을 모두 채워야 들어갑니다 — 하나라도 비운 새 줄은 「편집본에 "
        "적용」 때 버려집니다."
    )


def small_editor_edits() -> list[str]:
    """적용하지 않은 편집이 남은 작은 편집표의 이름(기존 보유대수·비가동 일정). 그리지 않은 표는
    칸이 없어 빠진다 — 화면 탭 줄 떠나기 확인·탭 ① 점이 이것을 본다. 작은 편집표가 **폼 밖**이라
    칸을 고친 회차마다 서버에 와 이 판정이 선다(폼 안이면 적용을 누르기 전까지 서버에 오지 않는다 —
    AGENTS 9장 「다른 위젯의 잠금·표시를 바꾸는 위젯은 폼 밖」).

    **이번 회차에 그릴 표만 센다** — 바깥 탭이 ① 이고 표 고르기(`MASTER_TABLE_KEY`)가 그 표일 때.
    표 고르기나 바깥 탭을 바꾼 회차에는 그 표를 그리지 않아 편집이 회차 끝에 걷히는데(그리지 않은
    위젯), 위젯 상태는 그때까지 세션에 남는다. 그 상태를 그대로 세면 페이지보다 먼저 그리는 탭 줄
    점·떠나기 확인·테마 표지와 탭 ① 점이 이미 사라진 편집을 한 회차 동안 말한다. 두 고르기 값은
    누른 회차 첫머리에 세션에 들어와 있어 페이지보다 먼저 읽어도 맞다(`navigation.opening_tab`)."""
    if (
        opening_tab(st.session_state, EQUIPMENT_TAB_KEY, EQUIPMENT_MASTER_TAB, EQUIPMENT_TABS)
        != EQUIPMENT_MASTER_TAB
    ):
        return []
    table = st.session_state.get(MASTER_TABLE_KEY)
    return [
        name for key, name in SMALL_EDITOR_NAMES.items() if name == table and editor_has_edits(key)
    ]


def buffer_base() -> str:
    """편집본 출발점 표지 — 세션 표지 + 저장본 쌍 토큰 + 씨뿌린 세대(개편 명세 6-3 `base`). 남의
    저장·내 저장·모두 버리기·시나리오 불러오기 때만 바뀐다 — 표 출납의 `base` 대조와 「리비전 저장」
    두 번 누름 거르기의 잣대다(편집본 세대는 출납마다 올라 잣대가 될 수 없다). 세션 표지가 없으면
    저장본과 세대가 같은 새 세션이 끊긴 사이 낸 앞 세션의 op 를 받아들인다."""
    session = st.session_state.setdefault(_BUFFER_SESSION_KEY, uuid4().hex[:6])
    token = st.session_state.get(_REVISION_KEY)
    seeded = st.session_state.get(_SEEDED_GENERATION_KEY)
    return f"{session}:{token}#{seeded}"


def render_small_editor(
    target: str,
    *,
    stale: bool,
    delete_locked: str | None,
    drafts_replaced: bool,
    undo: Callable[[], None] | None = None,
    on_deleted: Callable[[], None] | None = None,
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
    잠근다. 저장은 오른쪽 「저장 전 변경」 한 곳이다. `undo` 는 미룬 표 단계
    되돌리기(`defer_grid_undo`)를 편집을 넣은 뒤 잇는 길이다 — 값을 바꾼 편집이 줄을 지웠거나 통째
    단계면 되돌리기를 비우고 편집을 지킨다(그 사실은 알림창이 말한다). 값이 그대로인 편집(「선택」
    칸만 고름)은 그대로 되돌린다(`_undo_lines_up`). `on_deleted` 는 「삭제 확정」 을
    받은 제출 뒤에 부른다 — 화면이 「한 단계 되돌리기」 가 있는 「저장 전 변경」 칸을 연다(c6)."""
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
    with render_flash(_ERROR_KEY, _NOTICE_KEY):
        if baseline_table:
            example_rows = _example_row_count(frames)
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
                )
    selection = _current_selection()
    action_row = f"equipment_small_{slug}_action_row_v1"
    st.html(f"<style>{toolbar_room_css(action_row)}</style>")
    # 폼이 아니라 key 있는 칸 하나다(단추·보기·표가 한 칸에 선다).
    with st.container(key=f"equipment_small_{slug}_editor_v1"):
        # 표 위 작업 줄은 한 줄이다(설계 규칙 UI-LAY-11) — 그 끝에 「표 보기 ▾」 팝오버(보기 설정 ·
        # 「보기 적용」 — `_editor_view`)가 선다. 접힘 줄을 따로 세우지 않는다(2026-11-09 사용자
        # 보드 T5 — Cut-off 표와 같은 꼴). 줄 오른쪽 끝은 표 도구 막대 자리로 비운다 — 표가 줄 바로
        # 아래 붙어 있어 단추가 그 자리에 닿으면 막대가 덮는다. 다 들지 못하면 「표 보기 ▾」 가
        # 다음 줄로 내려간다(1600 · 1283 창은 한 줄, 1283 창에서 필터가 걸려 「표 보기 · 필터」 면
        # 두 줄 — 샘플 관측).
        view_apply_key = f"equipment_{slug}_view_apply_v1"
        downtime = frames[2]
        with st.container(horizontal=True, gap="small", key=action_row):
            # 적용하지 않은 편집 · 필수 칸을 비운 새 줄이 버려지는 것은 누르기 전에 알아야 해 이
            # 단추의 풍선에 둔다(설계 규칙 UI-NTF-09 · UI-TXT-01 — 표 밑에 늘 세우지 않는다).
            apply_clicked = st.button(
                "편집본에 적용",
                key=f"equipment_{slug}_apply_v1",
                type="primary",
                icon=":material/check:",
                help=f"{small_editor_required_note(target)} {SMALL_EDITOR_NOTE}",
            )
            action = _selection_buttons(
                slug, delete_locked=None if baseline_table else delete_locked
            )
            if baseline_table:
                view, requested, view_clicked = _editor_view(
                    frames[0],
                    key=BASELINE_EDITOR_KEY,
                    prefix="equipment_baseline_view",
                    filters=("공정", "분류"),
                    locked=("공정", "분류", "기존보유대수"),
                    apply_key=view_apply_key,
                )
            else:
                view, requested, view_clicked = _editor_view(
                    downtime,
                    key=DOWNTIME_EDITOR_KEY,
                    prefix=DOWNTIME_VIEW_PREFIX,
                    filters=(EQUIPMENT_ID_COLUMN, "비가동유형"),
                    locked=(EQUIPMENT_ID_COLUMN, "비가동유형", "시작일"),
                    apply_key=view_apply_key,
                )
        confirm_delete, cancel_delete = _render_bulk_delete_status(frames)
        if baseline_table:
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
            types = sorted(set(DOWNTIME_TYPES) | set(downtime["비가동유형"].dropna().astype(str)))
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
    # 「한 단계 되돌리기」 가 미룬 이 표의 되살리기(`restore_bulk_deletion`) — 제출로 받는다.
    restoring = st.session_state.get(RESTORE_REQUEST_KEY) == target
    # 「한 단계 되돌리기」 가 미룬 표 단계 되돌리기(`defer_grid_undo`) — 제출로 받는다.
    undoing = st.session_state.get(GRID_UNDO_REQUEST_KEY) == target
    if not any(
        (
            apply_clicked,
            view_clicked,
            action is not None,
            confirm_delete,
            cancel_delete,
            restoring,
            undoing,
        )
    ):
        return None

    def submit() -> None:
        if drafts_replaced:
            queue_flash(
                _ERROR_KEY,
                "다른 사용자가 먼저 저장해 이번 제출은 반영하지 않았습니다. 최신 저장본으로 다시 "
                "열었으니 확인한 뒤 다시 고치세요.",
                kind="error",
            )
            st.rerun()
        current: Frames = st.session_state[BUFFER_KEY]
        updated = list(current)
        updated[position] = edited
        if undoing:
            st.session_state.pop(GRID_UNDO_REQUEST_KEY, None)
        keep_undo = undoing and undo is not None and _undo_lines_up(current[position], edited)
        _remember_edits((updated[0], updated[1], updated[2]), keep_undo=keep_undo)
        deleted = _apply_bulk_actions(
            EditorResult(
                frames=(updated[0], updated[1], updated[2]),
                checked={**selection, target: checked},
                filters={target: requested.filters},
                action=(action, target) if action is not None else None,
            ),
            confirm=confirm_delete,
            view_applied=view_clicked,
        )
        if deleted and on_deleted is not None:
            on_deleted()
        if restoring:
            _restore_removed()
        if keep_undo and undo is not None:
            undo()
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


def origin_count_words(origins: Mapping[str, int]) -> str:
    """출처별 리비전 수 — 「이관 70 · 저장 10 · 되돌리기 2」. 차례는 `ORIGIN_WORDS`, 모르는
    출처는 그 값 그대로 뒤에(이름 차례), 0 인 출처는 뺀다. 셀 것이 없으면 빈 글."""
    known = [(word, origins.get(origin, 0)) for origin, word in ORIGIN_WORDS.items()]
    other = sorted(
        (origin, count) for origin, count in origins.items() if origin not in ORIGIN_WORDS
    )
    return " · ".join(f"{word} {count:,}" for word, count in (*known, *other) if count)


def revision_count_line(
    shown: int,
    origins: Mapping[str, int],
    *,
    unit: str,
    elsewhere: str | None = None,
    by_origin: bool = True,
) -> str:
    """리비전 목록의 머릿수 한 줄 — 목록이 싣는 수와 상관없는 전체 수.

    다 보이면 「전체 82줄(이관 70 · 저장 12)」(시나리오 관리 리비전 표 — 늘 전부 싣는다). 최근
    n 개만 싣는 목록(사이드바 팝업 라디오 — `SCHEDULE_REVISION_LIST_LIMIT`)이면 「최근 50개 · 전체
    82개 — 더 옛 32개는 시나리오 관리 › 설비 시나리오에서 고릅니다.」(`elsewhere` 가 그 자리 —
    없으면 「… 이 목록에 없습니다.」). `shown` 은 목록에 든 수, `origins` 는 출처별 전체 수
    (`load_equipment_schedule_revision_counts` — 목록과 같은 캐시 칸)이고 `by_origin=False` 면
    괄호를 뺀다. 사내 런북의 「리비전 N줄 = 이관 N」 확인은 표를 세지 않고 이 줄의 이관 수를 8-4s
    `L` 과 견준다.
    """
    total = max(sum(origins.values()), shown)
    head = (
        f"전체 {total:,}{unit}"
        if shown >= total
        else f"최근 {shown:,}{unit} · 전체 {total:,}{unit}"
    )
    words = origin_count_words(origins) if by_origin else ""
    if words:
        head += f"({words})"
    if shown >= total:
        return head
    hidden = with_topic_particle(f"{total - shown:,}{unit}")
    tail = f"{elsewhere}에서 고릅니다" if elsewhere else "이 목록에 없습니다"
    return f"{head} — 더 옛 {hidden} {tail}."


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
    공통 리비전 쌍의 합친 본문 캐시다(`load_saved_pair` 와 같은 쌍). 표와 「조회 리비전」 상자는
    리비전을 전부 싣고, 「공통」 칸 번호는 리비전 줄이 들고 온 번호가 먼저다(`common_revision_words`
    — 공통 이력 목록은 최신 50개라 옛 줄의 공통이 그 밖에 있다).
    """
    database_path = str(repository.database_path)
    if scenario_id is None:
        # 빈 결과는 평문 한 줄, 하는 법은 풍선이다(설계 규칙 UI-TXT-04).
        st.caption(NO_HISTORY_TEXT, help=NO_HISTORY_HELP)
        return
    # 표와 「조회 리비전」 상자는 리비전을 전부 싣는다(2026-11-01 사용자 결정 A4 — 표는 스크롤·찾기,
    # 상자는 글로 찾음).
    revisions = load_equipment_schedule_revisions(database_path, scenario_id)
    if not revisions:
        st.caption(NO_HISTORY_TEXT, help=NO_HISTORY_HELP)
        return
    latest_common = latest_equipment_revision_id(database_path)
    commons = load_equipment_revision_summaries(database_path, latest_common)
    common_numbers = {item.revision_id: item.revision_no for item in commons}
    if scenario_name:
        # 값 한 줄(무슨 목록인가) — 「공통」 칸의 뜻과 이 목록에 없는 저장은 풍선이다(UI-TXT-01).
        st.caption(
            f"「{literal_markdown(scenario_name)}」 의 일정 리비전",
            help=(
                f"「공통」 칸은 그 저장이 함께 본 공통 대장 리비전입니다. "
                f"{COMMON_ONLY_HISTORY_NOTE}"
            ),
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
                    "공통": common_revision_words(item, common_numbers),
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
    _render_common_history(commons, revisions)
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
        format_func=lambda value: schedule_revision_title(by_id[value]),
    )
    chosen = by_id[selected_id]
    common_id = chosen.common_revision_id or latest_common
    if common_id is None:
        st.caption("공통 대장 리비전이 없어 조회할 수 없습니다.")
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
        start, end = date_range_field(
            "비가동 일정 기간",
            start_key=HISTORY_EVENT_START_KEY,
            end_key=HISTORY_EVENT_END_KEY,
            default=default_range,
        )
    for column, selected in filters.items():
        if selected:
            equipment = equipment.loc[equipment[column].isin(selected)]
    if any(filters.values()):
        downtime = downtime.loc[downtime[EQUIPMENT_ID_COLUMN].isin(equipment[EQUIPMENT_ID_COLUMN])]
    if downtime_types:
        downtime = downtime.loc[downtime["비가동유형"].isin(downtime_types)]
    if start > end:
        st.error("조회 시작일이 종료일보다 늦습니다. 기간을 다시 선택하세요.")
    elif not downtime.empty:
        downtime = downtime.loc[
            downtime["시작일"].le(pd.Timestamp(end))
            & (downtime["종료일"].isna() | downtime["종료일"].ge(pd.Timestamp(start)))
        ]
    for index, (label, frame) in enumerate(
        (
            ("기존 보유대수", historical.baseline),
            ("설비 마스터", equipment),
            ("비가동 일정", downtime),
        )
    ):
        with st.expander(label, expanded=True, key=f"equipment_history_view_{index}"):
            st.dataframe(frame, hide_index=True, width="stretch", placeholder="")


# 저장 이력이 빈 자리 — 값 한 줄과 하는 법 풍선(설계 규칙 UI-TXT-04).
NO_HISTORY_TEXT = "저장된 리비전이 없습니다."
NO_HISTORY_HELP = "첫 리비전을 저장하면 이곳에서 저장 시점별 데이터를 확인할 수 있습니다."
# 저장 이력 「공통 대장 저장 이력」 펼침의 key — 머리에 건수가 들어 바뀌어도 펼침이 남게.
COMMON_HISTORY_EXPANDER_KEY = "equipment_common_history_v1"
COMMON_ONLY_HISTORY_NOTE = (
    "공통 칸만 바꾼 저장(설비명 바꿈·담당자 등)은 일정 리비전을 만들지 않아 위 목록에 없습니다 — "
    "아래 「공통 대장 저장 이력」 에 있습니다."
)


def common_history_label(commons: Sequence[EquipmentRevisionSummary]) -> str:
    """「공통 대장 저장 이력」 펼침 머리. 목록은 최신 50개까지라
    (`load_equipment_revision_summaries`) 그보다 옛 리비전이 있으면 「n건」 이 전체처럼 읽히지
    않게 「최근 n건(rA~rB)」 으로 범위를 적는다 — 공통 번호는 1 부터 붙고 지우지 않으므로 가장 옛
    줄이 r1 이 아니면 더 옛 리비전이 있다(사이드바 설비 시나리오 팝업 라디오가 한도에 걸렸을 때만
    「최근 50개 · 전체 N개」 를 적는 것과 같은 뜻 — 일정 리비전 표는 전부 싣는다)."""
    numbers = [item.revision_no for item in commons]
    if not numbers or min(numbers) <= 1:
        return f"공통 대장 저장 이력 {len(commons):,}건"
    return f"공통 대장 저장 이력 최근 {len(commons):,}건(r{min(numbers)}~r{max(numbers)})"


def _render_common_history(
    commons: Sequence[EquipmentRevisionSummary],
    revisions: Sequence[EquipmentScheduleRevisionSummary],
) -> None:
    """저장 이력 일정 표 아래 — 공통 대장 리비전(최신 50개)의 저장자·메모. 공통 칸만 바꾼 저장은
    일정 리비전을 만들지 않아 일정 표에 없으므로 방금 저장한 사람이 제 저장을 여기서 찾는다(E2E).
    「이 시나리오 일정」 은 그 공통을 함께 본 이 설비 시나리오 일정 리비전이다(없으면 빈칸 — 공통만
    바꾼 저장이거나 다른 설비 시나리오의 저장)."""
    if not commons:
        return
    paired: dict[str, list[str]] = {}
    for item in sorted(revisions, key=lambda revision: revision.revision_no):
        if item.common_revision_id is not None:
            paired.setdefault(item.common_revision_id, []).append(f"r{item.revision_no}")
    with st.expander(
        common_history_label(commons), expanded=False, key=COMMON_HISTORY_EXPANDER_KEY
    ):
        # 펼침 첫 표 — 도구 막대가 펼침 머리 오른쪽 끝 누름을 먹지 않게 띄운다(AGENTS 9장).
        toolbar_clearance()
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "공통": f"r{item.revision_no}",
                        "저장시각": item.created_at,
                        "저장자": item.saved_by,
                        "변경메모": item.note,
                        "호기행": item.equipment_row_count,
                        "이 시나리오 일정": "·".join(paired.get(item.revision_id, [])),
                    }
                    for item in commons
                ]
            ),
            hide_index=True,
            width="stretch",
            placeholder="",
            column_config={"저장시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
        )


def common_revision_words(
    item: EquipmentScheduleRevisionSummary, numbers: Mapping[str, int]
) -> str:
    """일정 리비전 표의 「공통」 칸(설비 마스터 탭 저장 이력 · 시나리오 관리 리비전 표) — 그 저장이
    함께 본 공통 대장 번호 「r12」. 리비전 줄이 들고 온 번호(`common_revision_no`)가 먼저다 — 표는
    리비전을 전부 싣는데 `numbers`(공통 대장 이력 목록)는 최신 50개라 옛 줄의 공통이 그 밖에 있다.
    번호가 없는 옛 캐시 값이면 `numbers` 에서 찾고, 어디에도 없으면 빈칸."""
    if item.common_revision_id is None:
        return ""
    number = item.common_revision_no
    if number is None:
        number = numbers.get(item.common_revision_id)
    return f"r{number}" if number is not None else ""


# 가정 설비 시나리오의 일정 확인(설비 마스터 탭 「일정 확인」·표 풍선)이 볼 마스터 한 벌 —
# ((공식 토큰, 편집본 세대), 표).
_CONFIRMATION_OFFICIAL_KEY = "equipment_schedule_confirmation_official_v1"


def official_confirmation_master(master: pd.DataFrame, official: EquipmentSnapshot) -> pd.DataFrame:
    """가정 설비 시나리오의 일정 확인(설비 마스터 탭 「일정 확인」·표 풍선)이 볼 마스터 —
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


def _confirmation_master(master: pd.DataFrame, official: EquipmentSnapshot | None) -> pd.DataFrame:
    """일정 확인 목록이 볼 마스터(`master` 는 편집본 설비 마스터). 공식 기준이면 세션 칸에 한
    벌(공식 토큰·편집본 세대로 키) — 설비 마스터 탭은 표 출납마다 회차가 돌므로 바뀐 것이 없는
    회차에 다시 짓지 않는다."""
    if official is None:
        return master
    key = (official.token, equipment_buffer_generation())
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
