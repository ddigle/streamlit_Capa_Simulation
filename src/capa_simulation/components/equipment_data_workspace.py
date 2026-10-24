# Purpose: 설비 세 입력의 검토·편집·이력 조회를 한 작업 공간에서 잇고 바뀐 쪽만 저장한다.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

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
    render_equipment_save_fields,
)
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.components.table_view_controls import (
    TableView,
    merge_edited_rows,
    render_table_view_controls,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    date_range_value,
    page_visit,
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
    load_floor_states,
    load_merged_equipment_snapshot,
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
    EQUIPMENT_TARGET,
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
    AREA_CODE_COLUMN,
    AREA_CODES,
    ARRIVAL_STATUS_COLUMN,
    ARRIVAL_STATUSES,
    COMMON_MASTER_COLUMNS,
    DATE_COLUMNS,
    DOWNTIME_TYPES,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    QUAL_STATUS_COLUMN,
    SCENARIO_SCHEDULE_COLUMNS,
    STORAGE_FLAG_COLUMN,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.equipment_csv import (
    EquipmentPaste,
    baseline_csv_bytes,
    baseline_csv_template,
    build_baseline_import_preview,
    build_downtime_import_preview,
    build_equipment_import_preview,
    describe_case_variants,
    downtime_csv_bytes,
    downtime_csv_template,
    equipment_csv_bytes,
    equipment_csv_template,
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
from capa_simulation.services.equipment_samples import untouched_sample_baseline_rows
from capa_simulation.services.equipment_scenario import calculation_frames
from capa_simulation.services.equipment_units import module_group_warnings
from capa_simulation.services.equipment_validation import (
    UnitGroupCollisionError,
    area_code_warnings,
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_baseline,
    prepare_equipment_master,
    unit_group_collision_message,
)
from capa_simulation.services.fab_layout import FabLayoutBase, FabLayoutMark
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.floor_layout_profile import CanvasSize, FloorCanvasMap, FloorKey
from capa_simulation.services.floor_state import (
    FloorStates,
    inactive_floor_summary,
    inactive_floor_warnings,
    master_location_options,
    present_location_values,
)
from capa_simulation.services.korean_particle import object_particle, with_direction_particle
from capa_simulation.services.schedule_confirmation import (
    ACTUAL_COLUMN,
    CONFIRMATION_KIND_COLUMN,
    MISSING_ACTUAL,
    PROCESS_COLUMN,
    SCHEDULE_COLUMN,
    STAGE_COLUMN,
    STATUS_COLUMN,
    STATUS_UPDATE_NEEDED,
    UNCONFIRMED,
    schedule_confirmation_summary,
)
from capa_simulation.services.simulation_cache import get_schedule_confirmation_issues
from capa_simulation.services.space_layout_edit import (
    ModuleLayout,
    PendingRenames,
    module_layout_message,
    module_layout_violations,
)

FLASH_KEY = "equipment_status_flash"
BASELINE_EDITOR_KEY = "equipment_baseline_editor_v3"
EQUIPMENT_EDITOR_KEY = "equipment_master_editor_v3"
# 설비 마스터 편집표 `동`·`층` 칸의 지난 회차 선택지 (동 목록, 층 목록). 거름이 없는 편집표는
# `num_rows="dynamic"` 이라 Streamlit 1.63 이 `column_config` 를 위젯 정체에 넣는다 — 남이 Space
# 에서 층을 끄면 선택지가 바뀌어 적용 전 칸 편집이 사라진다. 그래서 칸 편집이 있는 동안은 이
# 선택지를 그대로 쓴다(Space 층 사용 상태, 설비 0029).
LOCATION_OPTIONS_KEY = "equipment_master_location_options_v1"
DOWNTIME_EDITOR_KEY = "equipment_downtime_editor_v3"
BASELINE_DRAFT_KEY = "equipment_baseline_draft_v3"
EQUIPMENT_DRAFT_KEY = "equipment_master_draft_v3"
DOWNTIME_DRAFT_KEY = "equipment_downtime_draft_v3"
DRAFT_REVISION_KEY = "equipment_draft_revision_v4"
# 저장본 사본(draft)이 나온 설비 시나리오 일정 리비전에 일정 행이 없는 설비명(F4). 계산 화면은 이
# 호기와 그 비가동을 뺀 사본을 읽는다(`calculation_drafts`). 편집·RawData·CSV 는 39칸 전체다.
DRAFT_UNSCHEDULED_KEY = "equipment_draft_unscheduled_v1"
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
WORKSPACE_FORM_KEY = "equipment_data_workspace_form_v1"
TARGET_KEY = "equipment_import_target_v1"
CLIPBOARD_KEY = "equipment_import_clipboard_v1"
UPLOAD_KEY = "equipment_import_upload_v1"
PREVIEW_BUTTON_KEY = "equipment_import_preview_v1"
IMPORT_SAVE_BUTTON_KEY = "equipment_import_save_v1"
EDIT_SAVE_BUTTON_KEY = "equipment_edit_save_v1"
VIEW_APPLY_BUTTON_KEY = "equipment_view_apply_v1"
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
# 변경 메모·붙여넣기 칸을 다음 회차에 비우라는 표지. 저장은 두 칸을 그린 **뒤**에 일어나 그
# 회차에는 칸을 바꿀 수 없고, 칸을 지우기만 하면 브라우저가 옛 값을 다음 제출에 다시 보낸다
# (2026-10-05 E2E — r4 의 메모가 r5 에 그대로 실렸다). 다음 회차 각 칸 앞에서 빈 값을 적는다.
_NOTE_CLEAR_KEY = "equipment_workspace_note_clear_v1"
# CSV 업로드 칸의 key 세대. 업로드는 세션으로 값을 적을 수 없어 저장 뒤 비울 때 세대를 올려
# 새 칸으로 세운다(`_upload_widget_key`).
_UPLOAD_GENERATION_KEY = "equipment_import_upload_generation_v1"
# 일괄 삭제. 선택은 행 번호가 아니라 업무 키로 기억한다(`services/equipment_bulk_delete`).
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
# Space 배치 편집기가 적용한 모듈 묶음의 적용 뒤 모양(Main 설비 → `ModuleLayout`). 저장 검사
# (`module_layout_violations`)가 이 모양 그대로인 묶음을 편집기 결과로 보고 통과시킨다 — RawData 가
# 그 뒤에 그 묶음 좌표·크기를 고치면 모양이 달라져 다시 검사받는다. 편집본과 함께 버려진다.
EDITOR_MODULE_LAYOUTS_KEY = "equipment_editor_module_layouts_v1"
# 설비 마스터 편집표 위 한 줄과 좌표·크기 칸 머리 도움말.
MODULE_LAYOUT_HELP = (
    "Main 설비 모듈 묶음(모듈 둘 이상)의 X좌표·Y좌표·Xsize·Ysize 는 Space 현황 배치 편집기에서 "
    "묶음 범위로 고칩니다 — 여기서 고쳐 묶음 범위의 바둑판이 아니게 되면 저장이 막힙니다."
)
# 다른 사람이 새 리비전을 저장해 이 세션의 저장 안 한 편집을 버렸을 때 한 번 띄우는 알림.
DISCARDED_NOTICE_KEY = "equipment_workspace_discarded_v1"
# 이번 회차 맨 위에서 편집본을 새 저장본으로 갈아 끼웠다는 표시. 그 회차의 RawData 제출은 옛
# 편집본 위의 것이라 반영하지 않는다 — 페이지가 `pop_drafts_replaced` 로 한 번 읽는다.
DRAFTS_REPLACED_KEY = "equipment_workspace_drafts_replaced_v1"
# 편집본을 저장본에서 새로 세운 직후의 세대. 지금 세대가 이보다 크면 저장 안 한 편집이 있다.
_SEEDED_GENERATION_KEY = "equipment_workspace_seeded_generation_v1"
# 편집본을 바꿀 때마다 오르는 세대. Space 편집기 epoch 에 넣어 RawData 편집을 놓치지 않게 한다.
BUFFER_GENERATION_KEY = "equipment_workspace_buffer_generation_v1"
CANCEL_DELETE_BUTTON_KEY = "equipment_delete_cancel_v1"
UNDO_DELETE_BUTTON_KEY = "equipment_delete_undo_v1"
SELECT_MATCHING = "select_matching"
SELECT_CLEAR = "select_clear"
DELETE_SELECTED = "delete_selected"
# 안쪽 탭·접힘 칸의 key. 위젯이 아니라 **브라우저가 고른 탭·펼침을 기억하는 이름**이다
# (`render_equipment_data_workspace` 의 탭 주석).
WORKSPACE_TABS_KEY = "equipment_workspace_tabs_v1"
EDITOR_TABS_KEY = "equipment_workspace_editor_tabs_v1"
DOWNLOADS_EXPANDER_KEY = "equipment_workspace_downloads_v1"
HISTORY_FILTER_EXPANDER_KEY = "equipment_history_filters_v1"
# 일정 확인(미확인·실적 누락·상태 갱신 필요) 목록. 건수가 바뀌어 제목 글자가 달라져도 key 가 펼침을
# 지킨다 — key 가 있으면 블록 id 가 제목과 상관없이 정해진다.
CONFIRMATION_EXPANDER_KEY = "equipment_schedule_confirmation_list_v1"
# 목록에 보이는 칸과 차례. `설비키` 는 대수를 세는 데만 쓴다(Main 설비는 편집표에 있다).
_CONFIRMATION_LIST_COLUMNS = (
    CONFIRMATION_KIND_COLUMN,
    EQUIPMENT_ID_COLUMN,
    PROCESS_COLUMN,
    STAGE_COLUMN,
    SCHEDULE_COLUMN,
    ACTUAL_COLUMN,
    STATUS_COLUMN,
)
_EDITOR_KEYS = (BASELINE_EDITOR_KEY, EQUIPMENT_EDITOR_KEY, DOWNTIME_EDITOR_KEY)
_TARGETS = ("설비 마스터", "기존 보유대수", "비가동 일정")
Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]


@dataclass(frozen=True)
class ImportReview:
    """검토 화면이 사용한 원문과 세 편집본을 최종 저장 후보에 묶는다."""

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

    def matches(self, target: str, payload: str | bytes, source: Frames) -> bool:
        return (
            self.target == target
            and self.payload == payload
            and all(left.equals(right) for left, right in zip(self.source, source, strict=True))
        )


def _clear_editors() -> None:
    # 세션 칸만 지우면 브라우저가 옛 편집을 다시 보낸다. 위젯 키를 바꿔 새 편집표로 세운다
    # (`components/editor_state.py`).
    for key in _EDITOR_KEYS:
        discard_editor(key)
        st.session_state.pop(f"{key}_applied_view", None)


def reset_equipment_drafts(*, keep_fab: bool = False) -> None:
    """새 저장본으로 돌아갈 때 페이지 draft와 작업 공간의 입력·delta를 함께 비운다.

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
        EDITOR_MODULE_LAYOUTS_KEY,
        _SEEDED_GENERATION_KEY,
    ):
        st.session_state.pop(key, None)
    # 입력 칸(메모·붙여넣기·업로드)은 지우기만 하면 브라우저가 옛 값을 다시 보낸다. 메모·붙여넣기는
    # 표지로 다음 회차 칸 앞에서 빈 값을 적고, 업로드는 key 세대를 올린다.
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
    """편집본 세대. 편집본이 바뀔 때마다(RawData 제출·Space 적용·새 리비전) 오른다."""
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
    """편집본을 저장본에서 세운 뒤 바뀐 것이 있는가(RawData 제출·Space 호기 적용·미저장 층 배치).

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
    새 리비전이 생기면(누가 저장하면) 미저장 편집·캔버스·도면 요소는 버리고 다시 세운다.
    샘플 fleet 은 넣지 않는다 — 합성값이 섞이면 첫 실제 저장이 막힌다.
    """
    token = revision_token(latest_snapshot)
    previous = st.session_state.get(_REVISION_KEY)
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
        st.session_state[DRAFT_REVISION_KEY] = token
        for preview_key in (BASELINE_IMPORT_KEY, EQUIPMENT_IMPORT_KEY, DOWNTIME_IMPORT_KEY):
            st.session_state.pop(preview_key, None)
    if previous != token or BUFFER_KEY not in st.session_state:
        # 토큰이 **실제로 바뀐** 경우(다른 사람이 새 리비전을 저장)에만 옛 편집을 버리고 알린다.
        # 처음 세우는 회차(앞 토큰 없음)에 미리 쌓인 층 배치까지 지우면 그 편집이 사라진다.
        replaced = previous is not None and previous != token
        if replaced:
            st.session_state[DRAFTS_REPLACED_KEY] = True
        if replaced and has_unsaved_equipment_edits():
            number = _replaced_by_words(previous, latest_snapshot)
            st.session_state[DISCARDED_NOTICE_KEY] = (
                f"다른 사용자가 {number}{object_particle(number)} 저장해, 이 화면에서 "
                "저장하지 않은 설비 편집"
                "(RawData·Space 배치)을 버리고 최신 저장본으로 다시 열었습니다."
            )
        _clear_editors()
        st.session_state[BUFFER_KEY] = _copy_frames(
            (
                st.session_state[BASELINE_DRAFT_KEY],
                st.session_state[EQUIPMENT_DRAFT_KEY],
                st.session_state[DOWNTIME_DRAFT_KEY],
            )
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
        ]
        if replaced:
            stale += [
                PENDING_CANVASES_KEY,
                PENDING_MARKS_KEY,
                PENDING_GROUP_LABELS_KEY,
                PENDING_BASES_KEY,
            ]
        for key in stale:
            st.session_state.pop(key, None)
        _bump_buffer_generation()
        st.session_state[_SEEDED_GENERATION_KEY] = equipment_buffer_generation()
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
    # 내용이 그대로인 제출(보기 적용·이력 조회)은 세대를 올리지 않는다 — 올리면 「저장 안 한 편집이
    # 있다」로 보여, 남의 저장 때 버린 것도 없는데 버렸다고 알린다.
    if not unchanged:
        _bump_buffer_generation()


def replace_equipment_buffer(frames: Frames) -> None:
    """RawData 밖(Space 편집기)에서 편집본을 바꾼다. **편집본은 이 함수로만 바꾼다.**

    BUFFER_KEY 만 바꾸면 RawData 편집표가 옛 `{key}_applied_view` 프레임을 그대로 그리다
    다음 제출 때 이 편집을 되돌린다. 편집표 세대를 올리고 보기·미리보기·삭제 대기를 버린다.
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


def follow_unit_renames(renames: Mapping[str, str], groups: Mapping[str, str]) -> None:
    """Space 편집기가 이름을 바꿨다(설비명 `renames`·Main 설비 `groups`, 옛 이름 → 새 이름). 이름을
    기억한 RawData 칸을 따라 옮긴다 — 설비 마스터·비가동 일정의 선택은 새 설비명으로 옮기고,
    `방금 삭제 되돌리기` 는 **어느 이름이든 바꾸면** 버린다. 지운 행은 옛 이름을 지니므로 되살리면
    비가동 일정이 옛 설비명을 가리키거나 엉뚱한 호기에 붙고, 지운 모듈 행은 옛 Main 설비로 돌아와
    한 설비가 둘로 갈린다(검증은 통과해 그대로 저장된다)."""
    if not renames and not groups:
        return
    selection = _current_selection()
    if selection and renames:
        st.session_state[SELECTION_KEY] = {
            target: (
                frozenset((renames.get(key[0], key[0]), *key[1:]) for key in keys)
                if target in (EQUIPMENT_TARGET, DOWNTIME_TARGET)
                else keys
            )
            for target, keys in selection.items()
        }
    st.session_state.pop(LAST_REMOVED_KEY, None)


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
    Space 에서 넓힌 캔버스에 놓은 호기가 RawData 저장에서 「캔버스 밖」으로 막히지 않게."""
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
# FAB 저장이 거부됐을 때 빠져나갈 곳. 가용설비 RawData 저장도 FAB 대기분을 쓰므로 그 화면에서도
# 이 문구가 뜬다 — FAB 대기분만 버리는 단추는 Space 현황에 있다.
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
) -> str:
    """편집본(세 표)과 미저장 층 캔버스·도면 요소를 **한 트랜잭션**에 저장하고 알림 문구를 돌려준다.

    RawData 저장·Space 저장·사이드바 설비 시나리오 팝업 저장이 이 한 곳을 탄다(저장소
    `save_equipment` — 공통 대장·설비 시나리오 일정 가운데 **바뀐 쪽만** 쓴다. 둘 다 그대로면 층
    값만 쓰거나 아무것도 쓰지 않는다). `basis` 는 저장할 설비 시나리오와 화면이 본 공식
    번호(페이지가 세션에서 만든다 — 없으면 편집본이 나온 시나리오, 그것도 없으면 공식
    시나리오), `fields` 는 저장 칸 값(없으면 기본값)이다. 예시 행 가드는 repository 에 없으므로
    여기서 건다. 성공하면 캐시와 편집본을 모두 비운다.

    미저장 **FAB 전체 배치**는 설비 리비전과 무관한 별도 쓰기다(`save_pending_fab_layout`). 설비
    편집보다 **먼저** 쓴다 — 설비 저장이 막혀도 FAB 는 저장된 채 남고(그 사실을 오류 문구에 적는다),
    반대 순서면 설비 저장 뒤 편집본을 비우면서 FAB 대기분까지 잃는다. FAB 가 거부돼도(남이 먼저
    저장) 설비 저장은 그대로 하고, FAB 대기분은 남긴 채 두 결과를 함께 적은 `ValueError` 를 낸다.
    `frames` 가 None 이면(설비 저장본이 없어 대조할 출발 리비전이 없는 화면) FAB 대기분만 쓴다.
    """
    if frames is None:
        return FAB_SAVED_MESSAGE if save_pending_fab_layout(repository) else NOTHING_SAVED_MESSAGE
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
            repository, frames, note, basis=basis, fields=fields, fab_saved=fab_saved
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


def _save_equipment_frames(
    repository: DuckDBEquipmentRepository,
    frames: Frames,
    note: str,
    *,
    basis: EquipmentSaveBasis | None,
    fields: EquipmentSaveFields | None,
    fab_saved: bool,
) -> str:
    """`save_equipment_buffer` 의 설비 쪽(공통·일정 + 층 캔버스·요소 한 트랜잭션).

    설비 마스터를 쓰는 모든 저장(RawData 직접 편집·붙여넣기·CSV·일괄 삭제·Space 배치 저장·팝업
    저장)이 이 한 곳을 지나므로 모듈 묶음 좌표·크기 검사(`saved_master_violations` — 바뀐 묶음은
    묶음 범위의 바둑판이어야 한다, 2026-10-23 사용자 답 「막자」)도 여기서 한다."""
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
    schedule_id = base.get("schedule")
    # 편집본이 나온 두 리비전과 층마다 본 저장값을 함께 넘긴다. 그 사이 다른 사람이 저장했으면
    # 저장소가 쓰기 잠금 안에서 거부한다 — 옛 편집이 남의 저장을 조용히 되돌리지 않게.
    request = EquipmentSaveRequest(
        baseline=frames[0],
        equipment=frames[1],
        downtime=frames[2],
        equipment_scenario_id=scenario_id,
        base_common_revision_id=str(base["common"]),
        base_schedule_revision_id=schedule_id if isinstance(schedule_id, str) else None,
        renames=dict(pending_unit_renames().units),
        note=note,
        saved_by=chosen.saved_by,
        propagate_new_units=chosen.propagate_new_units,
        propagate_new_downtime=chosen.propagate_new_downtime,
        publish_official=chosen.publish_official,
        expected_release_no=basis.release_no if basis is not None else None,
        floor_canvases=canvases,
        floor_marks=marks,
        floor_layout_bases=pending_floor_bases(),
        floor_group_labels=labels,
    )
    result = repository.save_equipment(request)
    fab = " S.PKG FAB 전체 배치도 저장했습니다." if fab_saved else ""
    floor_layouts = floor_layout_words(canvases, marks, labels)
    if not result.wrote_revision and not floor_layouts and result.release_no is None:
        # 설비 쪽은 아무것도 쓰지 않았다. 편집본·변경 메모·선택을 그대로 둔다.
        return FAB_SAVED_MESSAGE if fab_saved else NOTHING_SAVED_MESSAGE
    clear_equipment_snapshot_cache()
    if floor_layouts:
        clear_floor_layout_cache()
    reset_equipment_drafts()
    if result.schedule is not None:
        st.session_state[SAVED_SCHEDULE_KEY] = {
            "scenario_id": result.schedule.equipment_scenario_id,
            "schedule_revision_id": result.schedule.schedule_revision_id,
        }
    layouts = f" {floor_layouts}도 함께 저장했습니다." if floor_layouts else ""
    if not result.wrote_revision:
        return f"설비 마스터가 바뀌지 않아 새 리비전 없이 {floor_layouts}만 저장했습니다.{fab}"
    name = basis.scenario_name if basis is not None else None
    return save_result_message(result, scenario_name=name) + layouts + fab


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
    if result.release_no is not None:
        released = f"공식 v{result.release_no}"
        sentences.append(f"{with_direction_particle(released)} 발행했습니다.")
    elif result.release_withheld:
        sentences.append(
            "공식 설비 시나리오에 발행하지 않은 더 새 리비전이 있어 공식 발행은 하지 않았습니다 — "
            "공식 발행은 가용설비 현황 「설비 시나리오」 탭에서 하세요."
        )
    if result.removed_units:
        removed = f"지운 호기 {len(result.removed_units):,}대는 모든 설비 시나리오에서 빠졌습니다."
        if result.new_units:
            removed += " 이름만 바꾸려면 Space 편집기 「이름 바꾸기」 를 쓰세요."
        sentences.append(removed)
    sentences.append("가용설비와 필요 단축 일정에 반영되고, Space 현황은 공식 기준입니다.")
    return " ".join(sentences)


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
    scenario_name: str | None = None,
) -> None:
    """세 표의 **현재 데이터**를 내려받는 버튼 셋. 양식 버튼 아래에 같은 차례로 선다.

    내보내는 것은 **편집 버퍼**(「직접 편집」 표가 보여 주는 편집본)이지 저장된 리비전이
    아니다. 사용자가 「지금 보는 것」을 받아야 Excel 에서 고쳐 되돌리는 왕복이 맞아떨어지고,
    저장본과 같을 때는 둘이 같은 파일이다. 다만 표 안에서 고치는 중인 값은 「보기 적용」·
    「변경 미리보기」·저장 중 하나를 눌러야 버퍼에 들어오므로, 그 사실을 캡션이 말한다.
    저장본과 다른지는 **내보낼 바이트를 비교**해 판단한다 — 파일이 달라질 때만 「편집본」이다.

    바이트는 표마다 **저장 리비전과 같은 표면 리비전 캐시**(`load_equipment_csv_payloads`)에서
    꺼낸다. 이 작업 공간은 숨은 탭에서도 rerun 마다 그려지므로, 고친 것이 없을 때 여섯 번의
    직렬화(내보낼 셋 + 견줄 셋)를 매번 치르고 있었다. 같은지는 `DataFrame.equals`(값·dtype·차례)로
    가르고, 다르면 지금처럼 직렬화해 바이트로 견준다 — dtype 만 달라 같은 파일이 되는 경우도
    「편집본」으로 잘못 적지 않는다. 지연 생성(콜러블)은 쓰지 않는다(TODO 결정 기록).

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

    payloads = tuple(
        table_bytes(position, frame)
        for position, frame in enumerate((buffered_equipment, buffered_baseline, buffered_downtime))
    )
    edited = payloads != tuple(
        table_bytes(position, frame)
        for position, frame in enumerate((saved_equipment, saved_baseline, saved_downtime))
    )
    basis = _saved_basis_words(latest_snapshot, scenario_name) if latest_snapshot else "저장본 없음"
    state = "저장하지 않은 변경 포함" if edited else "저장본과 같음"
    st.caption(
        f"현재 데이터 · {basis} · {state}. 「직접 편집」 표에 보이는 편집본을 그대로 "
        "내려받습니다. 표 안에서 고치는 중인 값은 「보기 적용」을 누른 뒤에 들어갑니다. "
        "고치지 않고 그대로 붙여넣어도 통과합니다."
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
) -> ImportReview:
    """기존 입력 서비스를 통해 원문을 검증하고 다른 표를 포함한 저장 후보를 만든다.

    `drop_examples` 는 「예시 행 지우기」를 누른 뒤의 재검토다. 원문은 그대로 두고 merge
    **전에** 예시 줄만 빼므로 지운 행이 재검토에서 되살아나지 않는다.
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


def _save_snapshot(
    repository: DuckDBEquipmentRepository,
    frames: Frames,
    note: str,
    *,
    basis: EquipmentSaveBasis | None,
    fields: EquipmentSaveFields,
) -> None:
    st.session_state[FLASH_KEY] = save_equipment_buffer(
        repository, frames, note, basis=basis, fields=fields
    )


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
    """직접 편집 탭이 한 번 제출될 때 돌려주는 것.

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
    사본 비가동 300건에서 40ms 남짓 — 샘플 관측, 행 수에 비례). RawData 는 어느 탭에서나 그려지므로
    키를 만들면 그 비용이 가용설비 현황의 모든 rerun 에 붙는다. dtype 은 못박는다 — 빈 표에서
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
    """표 **위** 세 버튼(2026-09-29 — 작업 버튼은 표 위). 폼 안이라 모두 제출 버튼이고, 누른
    것의 이름을 돌려준다. 버튼 값은 표보다 먼저 만들어도 같은 제출의 편집·선택이 함께 들어온다.
    필터·삭제·저장의 관계는 가용설비 현황 Guide 가 말한다. `delete_locked` 를 주면 「선택 행 삭제」
    를 끄고 그 까닭을 풍선으로 보인다(낡은 세션의 설비 마스터·비가동 일정).
    """
    with st.container(horizontal=True, gap="small"):
        matching = st.form_submit_button(
            "필터에 맞는 행 모두 선택",
            key=f"equipment_{slug}_select_matching_v1",
            icon=":material/checklist:",
        )
        clear = st.form_submit_button(
            "선택 해제", key=f"equipment_{slug}_select_clear_v1", icon=":material/deselect:"
        )
        delete = st.form_submit_button(
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
    """무엇이 얼마나 빠지는지. 호기를 지우면 딸려 빠지는 비가동 일정 수를 반드시 말한다."""
    count = plan.target_count
    samples = ", ".join(plan.sample_keys())
    more = " 외" if count > len(plan.sample_keys()) else ""
    if plan.target == EQUIPMENT_TARGET:
        # 행 수다. 모듈 설비는 한 대가 여러 행이라 「대」로 적으면 넷이 네 대로 읽힌다.
        head = f"호기 {count:,}행을 편집본에서 지웁니다"
        if plan.cascaded_downtime_count:
            head += f" — 이 호기의 비가동 일정 {plan.cascaded_downtime_count:,}건도 함께 지웁니다"
    elif plan.target == BASELINE_TARGET:
        head = f"기존 보유대수 {count:,}행을 편집본에서 지웁니다"
    else:
        head = f"비가동 일정 {count:,}건을 편집본에서 지웁니다"
    scope = f" {UNIT_DELETE_SCOPE_NOTE}" if plan.target == EQUIPMENT_TARGET else ""
    return (
        f"{head}. 대상: {samples}{more}. 확정해도 ‘설비 데이터 저장’을 눌러야 새 리비전에 "
        f"반영됩니다.{scope}"
    )


def _render_bulk_delete_status(frames: Frames) -> tuple[bool, bool, bool]:
    """확인 대기 중인 삭제와 방금 한 삭제를 편집표 위에 말한다. (확정, 취소, 되돌리기)."""
    confirm = cancel = undo = False
    pending = st.session_state.get(PENDING_DELETE_KEY)
    if isinstance(pending, tuple) and len(pending) == 2:
        target, keys = pending
        # 계획은 **지금 편집본**으로 다시 세운다. 대기하는 동안 편집이 있었으면 수가 바뀐다.
        plan = plan_deletion(frames, target, keys)
        if plan.target_count:
            st.warning(_deletion_message(plan), icon=":material/delete:")
            with st.container(horizontal=True, gap="small"):
                confirm = st.form_submit_button(
                    "삭제 확정",
                    key=CONFIRM_DELETE_BUTTON_KEY,
                    type="primary",
                    icon=":material/delete_forever:",
                )
                cancel = st.form_submit_button(
                    "취소", key=CANCEL_DELETE_BUTTON_KEY, icon=":material/close:"
                )
    removed = st.session_state.get(LAST_REMOVED_KEY)
    if isinstance(removed, tuple):
        count = sum(len(frame) for frame in removed)
        st.info(
            f"방금 편집본에서 {count:,}행을 지웠습니다. 저장하기 전까지 되돌릴 수 있습니다.",
            icon=":material/undo:",
        )
        undo = st.form_submit_button(
            "방금 삭제 되돌리기", key=UNDO_DELETE_BUTTON_KEY, icon=":material/undo:"
        )
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


# 편집표 위 한 줄 범례(설계 6-3). 칸 이름은 계약 그대로 두고 도움말 첫 마디로 어느 쪽인지 말한다.
SCENARIO_COLUMN_LEGEND = (
    ":material/info: 칸은 두 갈래입니다 — **공통**(호기 정보·Space 실물·실적·상태·이력·메모)은 "
    "모든 설비 시나리오에 같은 값이고, **시나리오**(일정 여섯·시나리오 메모·비가동 일정 표)는 "
    "지금 설비 시나리오에만 저장됩니다. 칸 머리에 마우스를 올리면 어느 쪽인지 보입니다."
)
# 상태 두 칸은 공통이지만 「확정」 은 공식 일정이 확정됐다는 뜻이다(결정 모음 — 칸 머리).
_STATUS_COLUMNS = (ARRIVAL_STATUS_COLUMN, QUAL_STATUS_COLUMN)
COMMON_COLUMN_HELP = "공통 — 모든 설비 시나리오에 같은 값"
STATUS_COLUMN_HELP = "공통 — 공식 일정 기준"
# 일괄 삭제·행 지우기 확인 문구에 붙인다(F6 — 호기 목록은 공통 하나).
UNIT_DELETE_SCOPE_NOTE = (
    "호기를 지우면 **모든 설비 시나리오**에서 사라집니다 — 이 시나리오에서만 빼려면 "
    "정지·반출/이설일정을 적으세요."
)
# RawData 폼 안 저장 칸 key 접두어(`equipment_save_fields`).
SAVE_FIELDS_PREFIX = "equipment_workspace_save"


def scenario_column_help(column: str, scenario_name: str | None) -> str:
    """칸 도움말 첫 마디 — 공통·상태·시나리오 가운데 어느 쪽인지."""
    if column in SCENARIO_SCHEDULE_COLUMNS:
        where = f"「{scenario_name}」 에만" if scenario_name else "지금 설비 시나리오에만"
        return f"시나리오 — {where} 저장"
    if column in _STATUS_COLUMNS:
        return STATUS_COLUMN_HELP
    return COMMON_COLUMN_HELP


def _with_scope_help(
    config: dict[str, Any], columns: Sequence[str], scenario_name: str | None
) -> dict[str, Any]:
    """칸 설정마다 도움말 첫 마디(공통·시나리오)를 얹는다. 설정이 없는 칸은 글 칸 설정을 새로 둔다.

    이미 도움말이 있는 칸은 그 앞에 붙인다. 날짜 칸 형식 같은 다른 설정은 그대로다.
    """
    result = dict(config)
    for column in columns:
        scope = scenario_column_help(column, scenario_name)
        existing = result.get(column)
        if existing is None:
            result[column] = st.column_config.Column(help=scope)
            continue
        current = existing.get("help") if isinstance(existing, dict) else None
        merged = dict(existing)
        merged["help"] = f"{scope}. {current}" if current else scope
        result[column] = merged
    return result


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
    same = (left == right) | (left.isna() & right.isna())
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

    common = changed([column for column in COMMON_MASTER_COLUMNS if column != EQUIPMENT_ID_COLUMN])
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
    if not (common or schedule or new_units or new_downtime):
        return None
    return (
        f"공통 칸 {common:,} · 시나리오 칸 {schedule:,} 바뀜 · 새 호기 {new_units:,} · 새 비가동 "
        f"{new_downtime:,}(다른 설비 시나리오에 넣을 후보)"
    )


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
    if catalog.official_scenario_id is not None:
        return catalog.official_scenario_id
    return catalog.scenarios[0].equipment_scenario_id if catalog.scenarios else None


def _location_options(
    floor_states: FloorStates | None, equipment: pd.DataFrame
) -> tuple[list[str], list[str]]:
    """설비 마스터 `동`·`층` 칸의 선택지. 적용 전 칸 편집이 있는 동안은 지난 회차 선택지를 그대로
    쓴다(`LOCATION_OPTIONS_KEY`) — 단, 표에 있는 유효 값이 그 선택지 밖이면(붙여넣기로 바뀐 편집본)
    새로 낸다(선택지 밖 값은 칸 오류로 그려진다)."""
    if floor_states is None:
        return list(VALID_BUILDINGS), list(VALID_FLOORS)
    held = st.session_state.get(LOCATION_OPTIONS_KEY)
    if (
        editor_has_edits(EQUIPMENT_EDITOR_KEY)
        and isinstance(held, tuple)
        and len(held) == 2
        and all(isinstance(part, tuple) for part in held)
    ):
        present_buildings, present_floors = present_location_values(equipment)
        if present_buildings <= set(held[0]) and present_floors <= set(held[1]):
            return list(held[0]), list(held[1])
    buildings, floors = master_location_options(floor_states, equipment)
    st.session_state[LOCATION_OPTIONS_KEY] = (tuple(buildings), tuple(floors))
    return buildings, floors


def _render_editors(
    frames: Frames,
    max_extent: CanvasSize,
    selection: Mapping[str, frozenset[RowKey]],
    *,
    stale: bool = False,
    scenario_name: str | None = None,
    delete_locked: str | None = None,
    floor_states: FloorStates | None = None,
) -> EditorResult:
    """직접 편집 세 표. `stale` 이면 일정 칸·비가동 표·행 추가를 잠그고, `delete_locked`(그 까닭)를
    주면 설비 마스터·비가동 일정의 「선택 행 삭제」 를 끈다 — 기존 보유대수는 공통이라 그대로다.

    `floor_states`(Space 층 사용 상태)를 주면 설비 마스터 `동`·`층` 칸의 선택지에서 쓰지 않는
    값을 칸 단위로 뺀다(`master_location_options` — 표에 이미 있는 값은 남긴다). 저장 검사는
    그대로다(S5)."""
    baseline, equipment, downtime = frames
    buildings, floors = _location_options(floor_states, equipment)
    # 위에 삭제 확인이 서거나 사라지면 이 탭의 자리가 밀린다 — key 가 고른 표를 지킨다.
    master_tab, baseline_tab, downtime_tab = st.tabs(list(_TARGETS), key=EDITOR_TABS_KEY)
    with master_tab:
        equipment_view, equipment_requested = _editor_view(
            equipment,
            key=EQUIPMENT_EDITOR_KEY,
            prefix="equipment_master_view",
            filters=(
                "공정소분류",
                "공정구분",
                "투자구분",
                "공정대분류",
                "동",
                "층",
                AREA_CODE_COLUMN,
                ARRIVAL_STATUS_COLUMN,
                QUAL_STATUS_COLUMN,
                STORAGE_FLAG_COLUMN,
                "기존설비여부",
                "레이아웃표시",
                PARENT_EQUIPMENT_COLUMN,
            ),
            locked=(
                EQUIPMENT_ID_COLUMN,
                "공정소분류",
                STORAGE_FLAG_COLUMN,
                "기존설비여부",
                "레이아웃표시",
            ),
            label="설비 마스터 · 표 보기 설정",
        )
        # 설비명은 고정하지 않는다. 고정 열은 Streamlit 이 맨 앞으로 옮겨 계약 차례(6번째)가 깨진다.
        config: dict[str, Any] = {
            EQUIPMENT_ID_COLUMN: st.column_config.TextColumn(required=True),
            "공정소분류": st.column_config.TextColumn(required=True),
            "동": st.column_config.SelectboxColumn(options=buildings),
            "층": st.column_config.SelectboxColumn(options=floors),
            "X좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_extent[0], step=1.0, help=MODULE_LAYOUT_HELP
            ),
            "Y좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_extent[1], step=1.0, help=MODULE_LAYOUT_HELP
            ),
            "Xsize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_extent[0], step=1.0, help=MODULE_LAYOUT_HELP
            ),
            "Ysize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_extent[1], step=1.0, help=MODULE_LAYOUT_HELP
            ),
            # 목록 밖 값도 받는다(저장 미리보기에서 경고만) — 고르는 칸으로 묶지 않는다.
            AREA_CODE_COLUMN: st.column_config.TextColumn(
                help=(
                    f"{'·'.join(AREA_CODES)} 가운데 하나를 적습니다(대소문자는 저장할 때 맞춥니다)."
                )
            ),
            ARRIVAL_STATUS_COLUMN: st.column_config.SelectboxColumn(options=list(ARRIVAL_STATUSES)),
            QUAL_STATUS_COLUMN: st.column_config.SelectboxColumn(
                options=list(QUAL_CONFIRMATION_STATUSES)
            ),
            STORAGE_FLAG_COLUMN: st.column_config.SelectboxColumn(
                options=["N", "Y"], required=True
            ),
            "기존설비여부": st.column_config.SelectboxColumn(options=["N", "Y"], required=True),
            "레이아웃표시": st.column_config.SelectboxColumn(options=["Y", "N"], required=True),
            # `step` 을 주지 않는다. Streamlit 은 step 의 소수 자릿수만큼 입력을 **잘라** 저장한다
            # (step=0.1 이면 0.25 → 0.2). 모듈 행의 0.25·0.125 가 그대로 들어가야 한다.
            "환산비": st.column_config.NumberColumn(min_value=0.01),
            PARENT_EQUIPMENT_COLUMN: st.column_config.TextColumn(
                help=(
                    "모듈 행을 설비 한 대로 묶는 설비 ID 입니다(APW01A~D → APW01). "
                    "비모듈 설비는 비웁니다."
                )
            ),
        }
        config.update(
            {column: st.column_config.DateColumn(format="YYYY-MM-DD") for column in DATE_COLUMNS}
        )
        config = _with_scope_help(config, list(equipment.columns), scenario_name)
        equipment_action = _selection_buttons("master", delete_locked=delete_locked)
        st.caption(f":material/grid_view: {MODULE_LAYOUT_HELP}")
        # 비활성 층 안내 — 자리는 늘 선다(생기고 사라질 때 아래 편집표가 밀리지 않게).
        with st.container(key="equipment_master_floor_state_note"):
            inactive_summary = (
                inactive_floor_summary(floor_states) if floor_states is not None else ""
            )
            if inactive_summary:
                st.caption(
                    f":material/block: 비활성 층: {inactive_summary} — 동·층 칸은 따로 골라 그 "
                    "짝을 다 거르지 못합니다. 골라도 저장은 되고 Space 목록·도면에서 숨습니다."
                )
        edited_equipment, equipment_checked = _selectable_editor(
            equipment,
            equipment_view,
            key=EQUIPMENT_EDITOR_KEY,
            target=EQUIPMENT_TARGET,
            column_config=config,
            selection=selection.get(EQUIPMENT_TARGET, frozenset()),
            locked_columns=SCENARIO_SCHEDULE_COLUMNS if stale else (),
            fixed_rows=stale,
        )
    with baseline_tab:
        baseline_view, baseline_requested = _editor_view(
            baseline,
            key=BASELINE_EDITOR_KEY,
            prefix="equipment_baseline_view",
            filters=("공정", "분류"),
            locked=("공정", "분류", "기존보유대수"),
            label="기존 보유대수 · 표 보기 설정",
        )
        baseline_action = _selection_buttons("baseline")
        edited_baseline, baseline_checked = _selectable_editor(
            baseline,
            baseline_view,
            key=BASELINE_EDITOR_KEY,
            target=BASELINE_TARGET,
            column_config={
                "공정": st.column_config.TextColumn(required=True, pinned=True),
                "분류": st.column_config.TextColumn(required=True),
                # `step` 을 주지 않는다 — Streamlit 은 step 의 소수 자릿수만큼 입력을 **잘라**
                # 저장한다(0.01 이면 1/3 모듈 0.333… → 0.33). 적은 값이 그대로 들어가고 보이는
                # 자리만 형식이 소수 둘째 자리로 반올림한다. 칸은 늘 실수다
                # (`prepare_equipment_baseline`).
                "기존보유대수": st.column_config.NumberColumn(
                    "기존 보유대수",
                    min_value=0,
                    format="%.2f 대",
                    required=True,
                ),
                "비고": st.column_config.TextColumn(),
            },
            selection=selection.get(BASELINE_TARGET, frozenset()),
        )
    with downtime_tab:
        downtime_view, downtime_requested = _editor_view(
            downtime,
            key=DOWNTIME_EDITOR_KEY,
            prefix="equipment_downtime_view",
            filters=(EQUIPMENT_ID_COLUMN, "비가동유형"),
            locked=(EQUIPMENT_ID_COLUMN, "비가동유형", "시작일"),
            label="운영 비가동 일정 · 표 보기 설정",
        )
        types = sorted(set(DOWNTIME_TYPES) | set(downtime["비가동유형"].dropna().astype(str)))
        downtime_action = _selection_buttons("downtime", delete_locked=delete_locked)
        edited_downtime, downtime_checked = _selectable_editor(
            downtime,
            downtime_view,
            key=DOWNTIME_EDITOR_KEY,
            target=DOWNTIME_TARGET,
            column_config={
                EQUIPMENT_ID_COLUMN: st.column_config.TextColumn(required=True, pinned=True),
                "비가동유형": st.column_config.SelectboxColumn(options=types, required=True),
                "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
                "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            },
            selection=selection.get(DOWNTIME_TARGET, frozenset()),
            # 비가동 일정 표 전체가 설비 시나리오 쪽이다(F2) — 낡은 세션에서는 통째로 잠근다.
            locked_columns=tuple(downtime.columns) if stale else (),
            fixed_rows=stale,
        )
    action = next(
        (
            (name, target)
            for name, target in (
                (equipment_action, EQUIPMENT_TARGET),
                (baseline_action, BASELINE_TARGET),
                (downtime_action, DOWNTIME_TARGET),
            )
            if name is not None
        ),
        None,
    )
    return EditorResult(
        frames=(edited_baseline, edited_equipment, edited_downtime),
        checked={
            EQUIPMENT_TARGET: equipment_checked,
            BASELINE_TARGET: baseline_checked,
            DOWNTIME_TARGET: downtime_checked,
        },
        filters={
            EQUIPMENT_TARGET: equipment_requested.filters,
            BASELINE_TARGET: baseline_requested.filters,
            DOWNTIME_TARGET: downtime_requested.filters,
        },
        action=action,
    )


# 일정 리비전 출처(`origin`) 화면 글자.
ORIGIN_WORDS = {
    "legacy": "이관",
    "save": "저장",
    "clone": "복제",
    "propagate": "함께 넣기",
    "restore": "되돌리기",
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
    """고른 설비 시나리오의 일정 리비전 이력과 그 리비전 하나의 「그때 그대로」 조회.

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
        "조회 조건을 바꾼 뒤 ‘이력 조회’를 누르세요. 조회는 편집본과 저장 이력을 바꾸지 않습니다."
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


# 가정 설비 시나리오의 일정 확인 목록이 볼 마스터 한 벌 — ((공식 토큰, 편집본 세대, 미리보기), 표).
_CONFIRMATION_OFFICIAL_KEY = "equipment_schedule_confirmation_official_v1"


def official_confirmation_master(master: pd.DataFrame, official: EquipmentSnapshot) -> pd.DataFrame:
    """가정 설비 시나리오의 일정 확인 목록이 볼 마스터 — 편집본의 공통 칸 + 공식 일정 일곱 칸.

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
    키) — 이 작업 공간은 숨은 탭에서도 회차마다 그려지므로 바뀐 것이 없는 회차에 다시 짓지
    않는다."""
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


def _render_schedule_confirmation(
    master: pd.DataFrame, *, today: date, official_basis: bool = False
) -> None:
    """반입·Qual 의 일정·실적·상태가 맞지 않는 호기 — 경고 한 줄과 접힌 목록. 셋 다 없으면 그리지
    않는다. 저장은 막지 않는다. `official_basis` 면 `master` 의 일정은 공식 설비 시나리오의 것이다
    (가정 설비 시나리오 — 그 사실을 한 줄 더 적는다).

    `master` 는 편집본(미리보기 중이면 저장될 후보)이다. 편집표가 폼 안이라 칸만 고쳐서는 바뀌지
    않고, 저장하지 않은 편집도 제출(보기 적용·저장·변경 미리보기 등) 뒤 회차에 보인다.
    판정은 내용 지문 + 오늘 캐시(`get_schedule_confirmation_issues`)로 받는다 — 이 작업 공간은
    숨은 탭에서도 회차마다 그려지므로, 고친 것이 없는 회차는 지문만 잰다. 미확인은
    오늘(`today`) 기준이고, 일정 당일은 아직 미확인이 아니다.
    """
    issues = get_schedule_confirmation_issues(master, today=today)
    summary = schedule_confirmation_summary(issues)
    if summary is None:
        return
    st.warning(summary, icon=":material/fact_check:")
    with st.expander(
        f"일정 확인 목록 · {len(issues):,}건", expanded=False, key=CONFIRMATION_EXPANDER_KEY
    ):
        if official_basis:
            st.caption(
                "가정 설비 시나리오라 일정은 **공식 설비 시나리오 기준**입니다 — 이 시나리오에서 "
                "고친 일정은 이 목록을 바꾸지 않고, 실적·상태(공통)를 고치면 빠집니다."
            )
        st.caption(
            f"**{UNCONFIRMED}** — 일정이 지났는데({today:%Y-%m-%d} 기준, 당일은 빼고) 실적이 "
            f"비고 상태가 계획·확정 · **{MISSING_ACTUAL}** — 상태가 완료인데 실적이 빔 · "
            f"**{STATUS_UPDATE_NEEDED}** — 실적이 있는데 상태가 계획·확정. 한 행이 한 (호기, "
            "단계)입니다. 직접 편집에서 그 단계의 실적·상태를 고친 뒤 보기 적용(붙여넣기는 "
            "변경 미리보기)을 누르면 이 목록에서 빠지고, 저장해야 Main 화면에도 반영됩니다."
        )
        st.dataframe(
            issues.loc[:, list(_CONFIRMATION_LIST_COLUMNS)],
            hide_index=True,
            width="stretch",
            # 빈 일정·실적은 빈칸이다 — 기본값이면 회색 "None" 글자가 값처럼 읽힌다.
            placeholder="",
            column_config={
                column: st.column_config.DateColumn(format="YYYY-MM-DD")
                for column in (SCHEDULE_COLUMN, ACTUAL_COLUMN)
            },
        )


# CSV 업로드 칸 하나만의 상한(MB). 빼면 서버 전체 상한(`.streamlit/config.toml` 의
# `maxUploadSize`, 1GB)을 물려받는데, CSV 파싱은 파일 크기의 몇 배 메모리를 써 잘못 고른 큰 파일
# 하나가 공용 앱 프로세스를 몰 수 있다. 칸 안내(「50MB per file」)와 브라우저가 올리기 전에 막는
# 크기(「File must be 50.0MB or smaller.」)가 이 값이다 — 서버 전체 상한은 그대로라 다른 올리기
# 칸은 묶지 않는다.
CSV_UPLOAD_LIMIT_MB = 50


def render_equipment_data_workspace(
    *,
    repository: DuckDBEquipmentRepository,
    latest_snapshot: EquipmentSnapshot | None,
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    floor_canvases: FloorCanvasMap,
    max_extent: CanvasSize,
    drafts_replaced: bool = False,
    today: date | None = None,
    basis: EquipmentSaveBasis | None = None,
    confirmation_official: EquipmentSnapshot | None = None,
) -> None:
    """입력·직접 편집·조회 중 한 작업을 표시하고 편집본을 저장한다(바뀐 쪽만 — 공통 대장·설비
    시나리오 일정).

    `confirmation_official` 을 주면(가정 설비 시나리오) 일정 확인 목록은 공식 일정 + 편집본 공통
    칸으로 본다 — 미확인은 공식 시나리오 일정 기준이다(결정).

    `basis` 는 세션의 설비 시나리오(저장할 곳·화면이 본 공식 번호·낡음)다. 낡았으면(세션 리비전이
    그 시나리오 최신이 아님) 일정 일곱 칸과 비가동 표·행 추가를 잠그고, 일정이 바뀌는 붙여넣기
    미리보기를 거부한다 — 막힌 뒤에 버리는 일이 없게 편집하기 전에 막는다(설계 4-2). 공통 칸은
    그대로 편집·저장된다.

    `drafts_replaced` 는 이번 회차 맨 위에서 다른 사람의 저장으로 편집본을 새로 세웠다는 뜻이다
    (`pop_drafts_replaced`). 그 회차의 제출은 반영하지 않는다 — 옛 편집본 위의 제출을 새 저장본에
    얹어 저장하면 남의 리비전과 같은 리비전이 「저장했습니다」로 생기고, 다시 그리면서 버림 알림도
    사라진다.

    `today` 는 일정 확인 경고의 「오늘」이다. 페이지는 Main 과 같은 날을 넘긴다(주지 않으면
    오늘)."""
    frames = ensure_equipment_drafts(latest_snapshot)
    scenario_name = basis.scenario_name if basis is not None else None
    stale = basis is not None and basis.stale
    # Space 층 사용 상태(설비 0029, 공용 현행값) — 동·층 칸 선택지와 저장 미리보기 경고에 쓴다.
    # 못 읽으면 지금처럼 30개 층 그대로다(RawData 를 막지 않는다).
    floor_states: FloorStates | None
    try:
        floor_states = load_floor_states(str(repository.database_path))
    except BOOTSTRAP_ERRORS:
        floor_states = None
    if latest_snapshot is None:
        st.info(
            "아직 저장된 설비 데이터가 없습니다. 설비 마스터를 붙여넣고 "
            "변경 내용을 확인해 첫 리비전을 저장하세요."
        )
    else:
        st.caption(
            f"최근 {_saved_basis_words(latest_snapshot, scenario_name)} · 저장하면 바뀐 쪽만 새 "
            "리비전으로 보관됩니다(공통 칸 → 공통 대장, 일정·시나리오 메모·비가동 → 이 설비 "
            "시나리오)."
        )
    st.caption(SCENARIO_COLUMN_LEGEND)
    if stale and basis is not None:
        st.warning(_stale_lock_message(basis), icon=":material/lock_clock:")
    # 미리보기는 등록할 표·붙여넣기·업로드에서 나온 위젯 아닌 칸이라 그 입력보다 오래 산다.
    # 다른 화면을 다녀오면 입력 칸은 비어 돌아오는데 「저장할 변경」과 저장 단추만 남아, 누르면
    # 입력이 없다는 오류로 막힌다. 페이지에 새로 들어온 회차에는 미리보기도 거둔다. 같은 페이지
    # 안의 `st.rerun()`(앞 탭의 Cut-off 저장 등)은 브라우저가 입력을 다시 보내므로 남긴다.
    visit = page_visit()
    if st.session_state.get(_PREVIEW_VISIT_KEY) != visit:
        st.session_state.pop(PREVIEW_KEY, None)
    st.session_state[_PREVIEW_VISIT_KEY] = visit
    pending = st.session_state.get(PREVIEW_KEY)
    # 알림(오류·안내·예시 행·Main 설비 묶음)은 수가 회차마다 다르다. **늘 서 있는 한 칸** 안에
    # 그려 아래 key 있는 펼침·탭의 자리를 고정한다 — 자리가 밀리면 `st.rerun()` 으로 끊긴
    # 저장 회차의 사본이 화면에 남는다(2026-10-05 E2E).
    with st.container():
        error = st.session_state.pop(_ERROR_KEY, None)
        if isinstance(error, str):
            st.error(error)
        notice = st.session_state.pop(_NOTICE_KEY, None)
        if isinstance(notice, str):
            st.info(notice)
        # **저장을 누르기 전에 말한다.** 30행을 다 붙여넣고 저장에서 막히는 것과, 들어오자마자
        # 아는 것은 다르다. 폼 밖이라 일반 버튼이 되고 콜백이 그 자리에서 지운다.
        example_rows = _example_row_count(frames, pending)
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
        # 저장은 막지 않는다. 묶음의 환산비가 모두 1 이면 능력이 모듈 수만큼 부풀려진다.
        # 미리보기 중이면 **저장될 후보**를 본다 — 편집본만 보면 저장한 뒤에야 경고가 뜬다.
        master = pending.candidate[1] if isinstance(pending, ImportReview) else frames[1]
        for message in module_group_warnings(master):
            st.warning(message, icon=":material/view_module:")
        # 모듈 묶음 좌표·크기를 바둑판이 아니게 고친 편집은 저장이 막힌다 — 저장 전에 같은 문구로
        # 알린다. 방금 그 문구로 거부된 회차는 위 오류가 이미 말하므로 경고를 거듭 세우지 않는다
        # (다음 회차부터 오류는 사라지고 이 경고가 남는다).
        violations = saved_master_violations(master)
        if violations:
            layout_message = module_layout_message(violations)
            if layout_message != error:
                st.warning(layout_message, icon=":material/grid_view:")
        # Area Code 목록 밖과 일정 확인(미확인·실적 누락·상태 갱신 필요)도 같은 자리에서
        # 알리고 막지 않는다. 일정 확인은 한 줄 + 접힌 목록이라 이 칸 안에 둔다 — 칸 밖이면 그
        # 목록이 생기고 사라질 때마다 아래 key 있는 펼침·탭이 밀린다.
        for message in area_code_warnings(master):
            st.warning(message, icon=":material/rule:")
        # 비활성 층으로 옮기거나 새로 넣은 호기 — 저장은 되고 Space 목록·도면에서 숨는다(막지
        # 않는다).
        if floor_states is not None:
            saved_master = (
                latest_snapshot.equipment if latest_snapshot is not None else master.iloc[0:0]
            )
            for message in inactive_floor_warnings(master, saved_master, floor_states):
                st.warning(message, icon=":material/block:")
        _render_schedule_confirmation(
            _confirmation_master(master, confirmation_official, pending),
            today=today or date.today(),
            official_basis=confirmation_official is not None,
        )
    # 표마다 무엇을 키로 대체하는지·Main 설비·환산비 같은 작성 기준은 Guide 가 말한다. 여기는
    # 내려받기만 남긴다.
    with st.expander(
        "입력 양식 · 현재 데이터 내려받기", expanded=False, key=DOWNLOADS_EXPANDER_KEY
    ):
        for column, label, payload, filename, key in zip(
            st.columns(3),
            _TARGETS,
            (equipment_csv_template(), baseline_csv_template(), downtime_csv_template()),
            (
                "equipment_master_template.csv",
                "equipment_baseline_template.csv",
                "equipment_downtime_template.csv",
            ),
            (
                "equipment_master_template_download_v3",
                "equipment_baseline_template_download_v3",
                "equipment_downtime_template_download_v3",
            ),
            strict=True,
        ):
            with column:
                render_csv_download(
                    data=payload, file_name=filename, key=key, label=f"{label} 양식"
                )
        _render_current_data_downloads(
            frames,
            saved=(baseline, equipment, downtime),
            latest_snapshot=latest_snapshot,
            database_path=str(repository.database_path),
            scenario_name=scenario_name,
        )
    with st.form(WORKSPACE_FORM_KEY, border=False, enter_to_submit=False):
        # 두 저장(입력·직접 편집)이 같이 쓰는 메모라 탭 **위**에 둔다 — 저장 버튼이 표 위로
        # 올라가면서 메모만 폼 맨 아래에 남으면 적지 않고 저장하기 쉽다.
        clear_inputs = bool(st.session_state.pop(_NOTE_CLEAR_KEY, False))
        if clear_inputs:
            st.session_state[_NOTE_KEY] = ""
        note = st.text_input("변경 메모", key=_NOTE_KEY, placeholder="예: 10월 신규 호기 30대 등록")
        # 저장자·함께 넣기·공식 발행 칸. 폼 안이라 늘 세우고 수를 적지 않는다 — 이 회차의 편집본에는
        # 같은 제출의 새 호기가 아직 없다. 실제로 퍼진 목록은 저장 결과 알림이 적는다(설계 6-4).
        save_fields = render_equipment_save_fields(
            SAVE_FIELDS_PREFIX, release_exists=basis is None or basis.release_no > 0
        )
        # 전환은 브라우저에서만 한다. 폼의 다른 탭도 계속 생성해 미제출 delta를 유지한다.
        # **key 는 고른 탭을 지키려고 준다**(2026-10-01). 폼 위 알림(오류·안내·예시 행·저장
        # 완료)이 생기거나 사라지는 제출마다 이 탭의 자리가 한 칸 밀려 새로 마운트되고,
        # key 가 없으면 「입력」으로 돌아갔다(삭제 확정·저장 직후 이력 조회, 브라우저 실측).
        # `on_change` 를 주지 않은 key 는 위젯이 아니다 — 브라우저가 고른 탭을 그 이름으로
        # 기억했다 다시 세울 때 되돌릴 뿐이고, 탭을 눌러도 rerun 이 돌지 않는다.
        input_tab, edit_tab, history_tab = st.tabs(
            ["입력", "직접 편집", "저장 이력"], key=WORKSPACE_TABS_KEY
        )
        with input_tab:
            target = st.selectbox("등록할 표", _TARGETS, key=TARGET_KEY)
            paste_column, upload_column = st.columns([3, 2])
            with paste_column:
                if clear_inputs:
                    st.session_state[CLIPBOARD_KEY] = ""
                clipboard = st.text_area(
                    "Excel 표 붙여넣기",
                    key=CLIPBOARD_KEY,
                    height=200,
                    placeholder=(
                        "헤더를 포함해 Ctrl+V로 붙여넣으세요. 설비 마스터는 설비명과 바꿀 열만 "
                        "넣어도 됩니다."
                    ),
                )
            with upload_column:
                uploaded = st.file_uploader(
                    "또는 CSV 파일 업로드",
                    type=["csv"],
                    key=_upload_widget_key(),
                    max_upload_size=CSV_UPLOAD_LIMIT_MB,
                )
            # 작업 줄은 미리보기 표 **위**다 — 저장 버튼이 긴 변경 표 아래로 밀리지 않게 한다.
            with st.container(horizontal=True, gap="small"):
                preview_clicked = st.form_submit_button(
                    "변경 미리보기",
                    key=PREVIEW_BUTTON_KEY,
                    icon=":material/preview:",
                )
                import_save_clicked = st.form_submit_button(
                    "확인 후 리비전 저장",
                    key=IMPORT_SAVE_BUTTON_KEY,
                    type="primary",
                    disabled=not isinstance(pending, ImportReview),
                    icon=":material/save:",
                )
            if isinstance(pending, ImportReview):
                st.markdown(f"**{pending.target} · 저장할 변경 {len(pending.changes):,}행**")
                split = paste_split_summary(pending.source, pending.candidate)
                if split is not None:
                    st.caption(f":material/call_split: {split}")
                for message in pending.notices:
                    st.info(message, icon=":material/info:")
                for message in pending.cautions:
                    st.warning(message, icon=":material/ink_eraser:")
                with st.container(horizontal=True):
                    st.metric("신규", f"{int(pending.changes['Import구분'].eq('신규').sum()):,}건")
                    st.metric(
                        "기존 대체", f"{int(pending.changes['Import구분'].eq('대체').sum()):,}건"
                    )
                st.dataframe(pending.changes, hide_index=True, width="stretch")
                st.caption(
                    f"저장 후: 기존 보유대수 {len(pending.candidate[0]):,}행 · "
                    f"호기 {len(pending.candidate[1]):,}행 · 비가동 {len(pending.candidate[2]):,}행"
                )
                if st.session_state.get(DROP_EXAMPLE_ROWS_KEY, False):
                    st.caption("예시 행은 빼고 검토했습니다.")
        with edit_tab:
            # 작업 줄은 세 표 **위**다(2026-09-29). 아래 두면 고친 뒤 버튼이 화면 밖이었다.
            with st.container(horizontal=True, gap="small"):
                edit_save_clicked = st.form_submit_button(
                    "설비 데이터 저장",
                    key=EDIT_SAVE_BUTTON_KEY,
                    type="primary",
                    icon=":material/save:",
                )
                view_clicked = st.form_submit_button("보기 적용", key=VIEW_APPLY_BUTTON_KEY)
            delete_locked = stale_delete_lock(basis) if stale and basis is not None else None
            if delete_locked is not None:
                # 낡기 전에 눌러 둔 호기·비가동 삭제 확인도 버린다 — 확정하면 저장이 늘 거부된다.
                pending = st.session_state.get(PENDING_DELETE_KEY)
                if isinstance(pending, tuple) and pending[0] in (EQUIPMENT_TARGET, DOWNTIME_TARGET):
                    st.session_state.pop(PENDING_DELETE_KEY, None)
            confirm_delete, cancel_delete, undo_delete = _render_bulk_delete_status(frames)
            editor = _render_editors(
                frames,
                max_extent,
                _current_selection(),
                stale=stale,
                scenario_name=scenario_name,
                delete_locked=delete_locked,
                floor_states=floor_states,
            )
            edited = editor.frames
        with history_tab:
            try:
                _render_history(
                    repository,
                    scenario_id=_history_scenario(repository, basis, latest_snapshot),
                    scenario_name=scenario_name,
                )
            except BOOTSTRAP_ERRORS as exc:
                st.error(
                    "저장 이력을 읽지 못했습니다: "
                    + bootstrap_error_message(exc, database_paths=(repository.database_path,))
                )
            history_clicked = st.form_submit_button("이력 조회", key="equipment_history_apply_v1")
    # 폼 안의 새 제출 단추는 반드시 이 목록에 더한다 — 빠지면 그 단추를 눌러도 아무 일도 하지
    # 않는다.
    if not any(
        (
            preview_clicked,
            import_save_clicked,
            edit_save_clicked,
            view_clicked,
            history_clicked,
            editor.action is not None,
            confirm_delete,
            cancel_delete,
            undo_delete,
        )
    ):
        return
    if drafts_replaced:
        st.warning(
            "다른 사용자가 먼저 저장해 이번 제출은 반영하지 않았습니다. 최신 저장본으로 다시 "
            "열었으니 확인한 뒤 다시 고치세요.",
            icon=":material/sync_problem:",
        )
        return
    _remember_edits(edited)
    _apply_bulk_actions(
        editor,
        confirm=confirm_delete,
        undo=undo_delete,
        view_applied=view_clicked,
    )
    try:
        if preview_clicked or import_save_clicked:
            if clipboard.strip() and uploaded is not None:
                raise ValueError(
                    "붙여넣기와 CSV 파일이 함께 있습니다. "
                    "사용할 입력 하나만 남기고 다시 미리보세요."
                )
            content: str | bytes = uploaded.getvalue() if uploaded is not None else clipboard
            if not content.strip():
                raise ValueError("Excel 표를 붙여넣거나 CSV 파일을 올린 뒤 미리보세요.")
            if (
                import_save_clicked
                and isinstance(pending, ImportReview)
                and pending.matches(target, content, edited)
            ):
                _save_snapshot(repository, pending.candidate, note, basis=basis, fields=save_fields)
            else:
                review = build_import_review(
                    target,
                    content,
                    edited,
                    floor_canvases=floor_canvases,
                    drop_examples=bool(st.session_state.get(DROP_EXAMPLE_ROWS_KEY, False)),
                )
                if stale and basis is not None:
                    refusal = stale_paste_refusal(review, edited, basis)
                    if refusal is not None:
                        raise ValueError(refusal)
                st.session_state[PREVIEW_KEY] = review
                if import_save_clicked:
                    st.session_state[_NOTICE_KEY] = (
                        "입력 또는 편집본이 바뀌어 미리보기를 갱신했습니다. "
                        "변경 내용을 확인한 뒤 다시 저장하세요."
                    )
        elif edit_save_clicked:
            _save_snapshot(repository, edited, note, basis=basis, fields=save_fields)
    except BOOTSTRAP_ERRORS as exc:
        if preview_clicked or import_save_clicked:
            st.session_state.pop(PREVIEW_KEY, None)
        st.session_state[_ERROR_KEY] = bootstrap_error_message(
            exc, database_paths=(repository.database_path,)
        )
    st.rerun()
