# Purpose: 설비 세 입력의 검토·편집·이력 조회를 한 작업 공간에서 연결하고 전체 리비전을 저장한다.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from capa_simulation.components.editor_state import discard_editor, editor_widget_key
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
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_snapshot_cache,
    clear_floor_layout_cache,
    load_equipment_csv_payloads,
    load_equipment_revision_summaries,
    load_equipment_snapshot,
)
from capa_simulation.persistence.equipment_repository import (
    EMPTY_REVISION_TOKEN,
    DuckDBEquipmentRepository,
    EquipmentSnapshot,
    FloorLayoutBase,
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
    DATE_COLUMNS,
    DOWNTIME_TYPES,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    STORAGE_FLAG_COLUMN,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.equipment_csv import (
    baseline_csv_bytes,
    baseline_csv_template,
    build_baseline_import_preview,
    build_downtime_import_preview,
    build_equipment_import_preview,
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
    read_equipment_clipboard,
    read_equipment_csv,
    untouched_template_baseline_rows,
)
from capa_simulation.services.equipment_samples import untouched_sample_baseline_rows
from capa_simulation.services.equipment_units import module_group_warnings
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
from capa_simulation.services.korean_particle import object_particle

FLASH_KEY = "equipment_status_flash"
BASELINE_EDITOR_KEY = "equipment_baseline_editor_v3"
EQUIPMENT_EDITOR_KEY = "equipment_master_editor_v3"
DOWNTIME_EDITOR_KEY = "equipment_downtime_editor_v3"
BASELINE_DRAFT_KEY = "equipment_baseline_draft_v3"
EQUIPMENT_DRAFT_KEY = "equipment_master_draft_v3"
DOWNTIME_DRAFT_KEY = "equipment_downtime_draft_v3"
DRAFT_REVISION_KEY = "equipment_draft_revision_v4"
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
BUFFER_KEY = "equipment_workspace_buffers_v1"
DROP_EXAMPLE_ROWS_KEY = "equipment_workspace_drop_examples_v1"
EXAMPLE_DROP_BUTTON_KEY = "equipment_workspace_drop_examples_button_v1"
_REVISION_KEY = "equipment_workspace_revision_v1"
_ERROR_KEY = "equipment_workspace_error_v1"
_NOTICE_KEY = "equipment_workspace_notice_v1"
_NOTE_KEY = "equipment_workspace_note_v1"
# 변경 메모를 다음 회차에 비우라는 표지. 저장은 메모 칸을 그린 **뒤**에 일어나 그 회차에는 칸을
# 바꿀 수 없고, 칸을 지우기만 하면 브라우저가 옛 메모를 다음 저장에 다시 보낸다(2026-10-05 E2E —
# r4 의 메모가 r5 에 그대로 실렸다). 다음 회차 메모 칸 앞에서 빈 값을 적는다.
_NOTE_CLEAR_KEY = "equipment_workspace_note_clear_v1"
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
# 층마다 편집을 시작할 때 본 저장값(캔버스·요소 지문). 저장이 이것과 지금 저장값을 견줘, 그 사이
# 다른 사람이 바꾼 층을 옛 목록으로 덮지 않는다(요소는 층 전체 교체다).
PENDING_BASES_KEY = "equipment_pending_floor_bases_v1"
# Space FAB 편집기가 쌓는 미저장 FAB 전체 배치(캔버스·요소와 편집을 시작할 때 본 저장값). FAB 는
# 설비 리비전과 무관한 현행값이라 **설비 저장본이 없어도** 쌓고 저장한다. 같은 저장 단추가 쓰고
# 같은 `모두 버리기` 가 버린다. 남이 새 리비전을 저장해도 버리지 않는다 — 리비전과 상관없고, 남이
# FAB 를 먼저 바꿨는지는 저장 때 본 저장값으로 따로 견준다.
PENDING_FAB_KEY = "equipment_pending_fab_layout_v1"
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
_EDITOR_KEYS = (BASELINE_EDITOR_KEY, EQUIPMENT_EDITOR_KEY, DOWNTIME_EDITOR_KEY)
_TARGETS = ("호기 마스터", "기존 보유대수", "비가동 일정")
Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]


@dataclass(frozen=True)
class ImportReview:
    """검토 화면이 사용한 원문과 세 편집본을 최종 저장 후보에 묶는다."""

    target: str
    payload: str | bytes
    source: Frames
    candidate: Frames
    changes: pd.DataFrame
    # 원문을 읽으며 남긴 알림(빠진 옛 컬럼 `투자기준` 을 떼어 냄 등). 미리보기와 함께 남는다.
    notices: tuple[str, ...] = ()

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


def reset_equipment_drafts() -> None:
    """새 저장본으로 돌아갈 때 페이지 draft와 작업 공간의 입력·delta를 함께 비운다."""
    _clear_editors()
    for key in (
        BASELINE_DRAFT_KEY,
        EQUIPMENT_DRAFT_KEY,
        DOWNTIME_DRAFT_KEY,
        DRAFT_REVISION_KEY,
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
        CLIPBOARD_KEY,
        UPLOAD_KEY,
        SELECTION_KEY,
        PENDING_DELETE_KEY,
        LAST_REMOVED_KEY,
        PENDING_CANVASES_KEY,
        PENDING_MARKS_KEY,
        PENDING_BASES_KEY,
        PENDING_FAB_KEY,
        _SEEDED_GENERATION_KEY,
    ):
        st.session_state.pop(key, None)
    st.session_state[_NOTE_CLEAR_KEY] = True


def _copy_frames(frames: Frames) -> Frames:
    return frames[0].copy(), frames[1].copy(), frames[2].copy()


def _bump_buffer_generation() -> None:
    st.session_state[BUFFER_GENERATION_KEY] = equipment_buffer_generation() + 1


def equipment_buffer_generation() -> int:
    """편집본 세대. 편집본이 바뀔 때마다(RawData 제출·Space 적용·새 리비전) 오른다."""
    value = st.session_state.get(BUFFER_GENERATION_KEY, 0)
    return int(value) if isinstance(value, int) else 0


def revision_token(latest_snapshot: EquipmentSnapshot | None) -> str:
    """편집본이 어느 저장본에서 나왔는지 가르는 값. 저장본이 없으면 `EMPTY_REVISION_TOKEN`."""
    if latest_snapshot is None:
        return EMPTY_REVISION_TOKEN
    return latest_snapshot.revision.revision_id


def has_unsaved_equipment_edits() -> bool:
    """편집본을 저장본에서 세운 뒤 바뀐 것이 있는가(RawData 제출·Space 적용·미저장 층 배치)."""
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
            number = f"r{latest_snapshot.revision.revision_no}" if latest_snapshot else "새 저장"
            st.session_state[DISCARDED_NOTICE_KEY] = (
                f"다른 사용자가 {number}{object_particle(number)} 저장해, 이 화면에서 저장하지 "
                "않은 설비 편집"
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
        # 선택·삭제 대기·되돌리기·미저장 층 배치는 옛 편집본의 것이다. 새 저장본 위에서
        # 쓰이면 안 된다.
        stale = [PREVIEW_KEY, SELECTION_KEY, PENDING_DELETE_KEY, LAST_REMOVED_KEY]
        if replaced:
            stale += [PENDING_CANVASES_KEY, PENDING_MARKS_KEY, PENDING_BASES_KEY]
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


def pending_floor_canvases() -> dict[FloorKey, CanvasSize]:
    """Space 에서 바꿨지만 아직 저장하지 않은 층 캔버스."""
    value = st.session_state.get(PENDING_CANVASES_KEY)
    return dict(value) if isinstance(value, dict) else {}


def pending_floor_marks() -> dict[FloorKey, tuple[FloorLayoutMark, ...]]:
    """Space 에서 바꿨지만 아직 저장하지 않은 층 도면 요소(층 전체 목록)."""
    value = st.session_state.get(PENDING_MARKS_KEY)
    return dict(value) if isinstance(value, dict) else {}


def pending_floor_bases() -> dict[FloorKey, FloorLayoutBase]:
    """층마다 편집을 시작할 때 본 저장값(캔버스, 요소 지문)."""
    value = st.session_state.get(PENDING_BASES_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _remember_base(key: FloorKey, base: FloorLayoutBase | None) -> None:
    """그 층의 **첫** 대기분이 본 저장값만 남긴다. 대기분이 다 빠지면 함께 버린다."""
    bases = pending_floor_bases()
    if key not in pending_floor_canvases() and key not in pending_floor_marks():
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
    revision_optional: bool = False,
) -> str:
    """편집본(세 표)과 미저장 층 캔버스·도면 요소를 **한 트랜잭션**에 저장하고 알림 문구를 돌려준다.

    RawData 저장과 Space 저장이 이 한 곳을 탄다. `revision_optional` 이면 세 표가 최신
    리비전과 같을 때 리비전 없이 캔버스·요소만 쓴다(Space 에서 요소만 고친 저장). 예시 행 가드는
    repository 에 없으므로 여기서 건다. 성공하면 두 캐시와 편집본을 모두 비운다.

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
            repository, frames, note, revision_optional=revision_optional, fab_saved=fab_saved
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
    revision_optional: bool,
    fab_saved: bool,
) -> str:
    """`save_equipment_buffer` 의 설비 쪽(세 표 + 층 캔버스·요소 한 트랜잭션)."""
    canvases = pending_floor_canvases()
    marks = {
        key: [mark.editor_payload() for mark in staged]
        for key, staged in pending_floor_marks().items()
    }
    # 편집본이 나온 리비전과 층마다 본 저장값을 함께 넘긴다. 그 사이 다른 사람이 저장했으면
    # 저장소가 쓰기 잠금 안에서 거부한다 — 옛 편집이 남의 저장을 조용히 되돌리지 않게.
    options: dict[str, Any] = {
        "note": note,
        "floor_canvases": canvases,
        "floor_marks": marks,
        "base_revision_id": st.session_state.get(_REVISION_KEY),
        "floor_layout_bases": pending_floor_bases(),
    }
    if revision_optional:
        saved = repository.save_space_layout(*frames, **options)
    else:
        saved = repository.save_snapshot(*frames, **options)
    fab = " S.PKG FAB 전체 배치도 저장했습니다." if fab_saved else ""
    if saved is None and not (canvases or marks):
        # 설비 쪽은 아무것도 쓰지 않았다. 편집본·변경 메모·선택을 그대로 둔다.
        return FAB_SAVED_MESSAGE if fab_saved else NOTHING_SAVED_MESSAGE
    clear_equipment_snapshot_cache()
    if canvases or marks:
        clear_floor_layout_cache()
    reset_equipment_drafts()
    layouts = " 층 캔버스·도면 요소도 함께 저장했습니다." if canvases or marks else ""
    if saved is None:
        return f"호기 마스터가 바뀌지 않아 새 리비전 없이 층 캔버스·도면 요소만 저장했습니다.{fab}"
    return (
        f"설비 운영 데이터 r{saved.revision.revision_no}"
        f"{object_particle(str(saved.revision.revision_no))} 저장했습니다. "
        f"가용설비와 Space 현황에 반영됩니다.{layouts}{fab}"
    )


def current_data_file_name(
    table_slug: str,
    *,
    latest_snapshot: EquipmentSnapshot | None,
    edited: bool,
    today: date,
) -> str:
    """`equipment_master_r3_20260924.csv` 꼴. 무엇을 기준으로 한 파일인지 이름이 말한다.

    월 범위가 없는 표라 기준 정보 쪽(`RQ_UPEH_<시작>_<끝>.csv`)처럼 범위를 담을 수 없다.
    대신 **어느 저장본에서 출발했는지**(`r3`, 저장본이 없으면 `r0`)와 **언제 받았는지**를
    담고, 저장하지 않은 변경이 섞여 있으면 `_edited` 를 붙인다 — 같은 날 받은 두 파일이
    저장본인지 편집본인지 이름만 보고 갈리게 하기 위해서다.
    """
    revision_no = latest_snapshot.revision.revision_no if latest_snapshot is not None else 0
    suffix = "_edited" if edited else ""
    return f"{table_slug}_r{revision_no}{suffix}_{today:%Y%m%d}.csv"


def _render_current_data_downloads(
    frames: Frames,
    *,
    saved: Frames,
    latest_snapshot: EquipmentSnapshot | None,
    database_path: str,
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
    「편집본」으로 잘못 적지 않는다. 지연 생성(콜러블)은 쓰지 않는다(TODO [결정]).

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
            database_path, latest_snapshot.revision.revision_id
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
    basis = (
        f"저장본 r{latest_snapshot.revision.revision_no}"
        if latest_snapshot is not None
        else "저장본 없음"
    )
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
                    slug, latest_snapshot=latest_snapshot, edited=edited, today=today
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
    if target == "호기 마스터":
        try:
            incoming = (
                read_equipment_csv(payload, floor_canvases=floor_canvases, notices=notices)
                if isinstance(payload, bytes)
                else read_equipment_clipboard(
                    payload, floor_canvases=floor_canvases, notices=notices
                )
            )
        except UnitGroupCollisionError as exc:
            # 붙여넣은 표 안에서 부딪혔다 — 양쪽 모두 붙여넣은 행이다.
            raise ValueError(
                unit_group_collision_message(exc.collisions, pasted=_collision_names(exc))
            ) from exc
        changes = build_equipment_import_preview(equipment, incoming)
        try:
            equipment = merge_equipment_rows(equipment, incoming, floor_canvases=floor_canvases)
        except UnitGroupCollisionError as exc:
            # 검증은 병합된 표만 본다. 어느 쪽이 붙여넣은 행인지 붙여 다시 알린다 — 붙여넣기는
            # 설비명 기준 upsert 라 편집본 쪽 행을 지우지 못한다.
            pasted = set(incoming[EQUIPMENT_ID_COLUMN].dropna().astype(str))
            raise ValueError(unit_group_collision_message(exc.collisions, pasted=pasted)) from exc
        downtime = merge_downtime_rows(downtime, empty_downtime_schedule(), equipment=equipment)
        baseline = prepare_equipment_baseline(baseline)
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
    )


def _collision_names(exc: UnitGroupCollisionError) -> set[str]:
    """충돌에 든 설비명 전부(설비 행과 모듈 행)."""
    return {*exc.collisions, *(name for modules in exc.collisions.values() for name in modules)}


def _save_snapshot(repository: DuckDBEquipmentRepository, frames: Frames, note: str) -> None:
    st.session_state[FLASH_KEY] = save_equipment_buffer(repository, frames, note)


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


def _selectable_editor(
    original: pd.DataFrame,
    view: TableView,
    *,
    key: str,
    target: str,
    column_config: Mapping[str, Any],
    selection: frozenset[RowKey],
) -> tuple[pd.DataFrame, frozenset[RowKey]]:
    """맨 앞에 선택 칸을 붙여 편집표를 그리고, 선택 칸을 뗀 편집 결과와 고른 키를 돌려준다."""
    display = view.frame.copy()
    # dtype 을 못박는다. 빈 표에서 목록으로 넣으면 float 칸이 되어 체크박스와 맞지 않는다.
    chosen = [row in selection for row in row_keys(view.frame, target)] or [False] * len(display)
    display.insert(0, SELECT_COLUMN, pd.Series(chosen, index=display.index, dtype="bool"))
    result = st.data_editor(
        display,
        key=editor_widget_key(key),
        num_rows=view.row_mode,
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


def _selection_buttons(slug: str) -> str | None:
    """표 **위** 세 버튼(2026-09-29 — 작업 버튼은 표 위). 폼 안이라 모두 제출 버튼이고, 누른
    것의 이름을 돌려준다. 버튼 값은 표보다 먼저 만들어도 같은 제출의 편집·선택이 함께 들어온다.
    필터·삭제·저장의 관계는 가용설비 현황 Guide 가 말한다.
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
            "선택 행 삭제", key=f"equipment_{slug}_delete_selected_v1", icon=":material/delete:"
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
    return (
        f"{head}. 대상: {samples}{more}. 확정해도 ‘설비 데이터 저장’을 눌러야 새 리비전에 "
        "반영됩니다."
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
        st.session_state[BUFFER_KEY] = apply_deletion(frames, plan)
        st.session_state[LAST_REMOVED_KEY] = plan.removed
        selection[target] = frozenset()
        st.session_state[_NOTICE_KEY] = _deletion_message(plan).replace("지웁니다", "지웠습니다", 1)
    elif undo:
        removed = st.session_state.pop(LAST_REMOVED_KEY, None)
        if isinstance(removed, tuple):
            restored, skipped = restore_rows(frames, removed)
            st.session_state[BUFFER_KEY] = restored
            message = "방금 지운 행을 편집본에 되살렸습니다."
            if skipped:
                message += f" 그 사이 같은 키가 다시 생긴 {skipped:,}행은 건너뛰었습니다."
            st.session_state[_NOTICE_KEY] = message
    st.session_state[SELECTION_KEY] = selection


def _render_editors(
    frames: Frames,
    max_extent: CanvasSize,
    selection: Mapping[str, frozenset[RowKey]],
) -> EditorResult:
    baseline, equipment, downtime = frames
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
                "확정상태",
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
            label="호기 마스터 · 표 보기 설정",
        )
        # 설비명은 고정하지 않는다. 고정 열은 Streamlit 이 맨 앞으로 옮겨 계약 차례(6번째)가 깨진다.
        config: dict[str, Any] = {
            EQUIPMENT_ID_COLUMN: st.column_config.TextColumn(required=True),
            "공정소분류": st.column_config.TextColumn(required=True),
            "동": st.column_config.SelectboxColumn(options=list(VALID_BUILDINGS)),
            "층": st.column_config.SelectboxColumn(options=list(VALID_FLOORS)),
            "X좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_extent[0], step=1.0
            ),
            "Y좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_extent[1], step=1.0
            ),
            "Xsize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_extent[0], step=1.0
            ),
            "Ysize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_extent[1], step=1.0
            ),
            "확정상태": st.column_config.SelectboxColumn(options=list(QUAL_CONFIRMATION_STATUSES)),
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
        equipment_action = _selection_buttons("master")
        edited_equipment, equipment_checked = _selectable_editor(
            equipment,
            equipment_view,
            key=EQUIPMENT_EDITOR_KEY,
            target=EQUIPMENT_TARGET,
            column_config=config,
            selection=selection.get(EQUIPMENT_TARGET, frozenset()),
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
                # 소수 둘째 자리(모듈 단위 기존 보유 0.25대)까지 받는다. Streamlit 은 step 의
                # 소수 자릿수만큼 입력을 자른다(step=0.1 이면 0.25 → 0.2).
                "기존보유대수": st.column_config.NumberColumn(
                    "기존 보유대수",
                    min_value=0,
                    step=0.01,
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
        downtime_action = _selection_buttons("downtime")
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


def _render_history(repository: DuckDBEquipmentRepository, latest_revision_id: str | None) -> None:
    # 리비전은 덧붙이기만 하므로 최신 id 가 목록을 정한다 — rerun 마다 DB 를 읽지 않는다.
    revisions = load_equipment_revision_summaries(str(repository.database_path), latest_revision_id)
    if not revisions:
        st.info("첫 리비전을 저장하면 이곳에서 저장 시점별 데이터를 확인할 수 있습니다.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "리비전": f"r{item.revision_no}",
                    "저장시각": item.created_at,
                    "기존대수행": item.baseline_row_count,
                    "호기행": item.equipment_row_count,
                    "비가동행": item.downtime_row_count,
                    "변경메모": item.note,
                }
                for item in revisions
            ]
        ),
        hide_index=True,
        width="stretch",
        placeholder="메모 없음",
        column_config={"저장시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
    )
    by_id = {item.revision_id: item for item in revisions}
    selected_id = st.selectbox(
        "조회 리비전",
        options=list(by_id),
        key="equipment_history_revision_id_v3",
        format_func=lambda value: (
            f"r{by_id[value].revision_no} · {by_id[value].note or '메모 없음'}"
        ),
    )
    historical = load_equipment_snapshot(str(repository.database_path), selected_id)
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
                )
            downtime_types = st.multiselect(
                "비가동유형",
                downtime["비가동유형"].dropna().drop_duplicates().tolist(),
                key="equipment_history_downtime_type_filter_v3",
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
        ("호기 마스터", equipment),
        ("비가동 일정", downtime),
    ):
        with st.expander(label, expanded=True):
            st.dataframe(frame, hide_index=True, width="stretch")


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
) -> None:
    """입력·직접 편집·조회 중 한 작업을 표시하고 세 표를 한 리비전으로 저장한다.

    `drafts_replaced` 는 이번 회차 맨 위에서 다른 사람의 저장으로 편집본을 새로 세웠다는 뜻이다
    (`pop_drafts_replaced`). 그 회차의 제출은 반영하지 않는다 — 옛 편집본 위의 제출을 새 저장본에
    얹어 저장하면 남의 리비전과 같은 리비전이 「저장했습니다」로 생기고, 다시 그리면서 버림 알림도
    사라진다."""
    frames = ensure_equipment_drafts(latest_snapshot)
    if latest_snapshot is None:
        st.info(
            "아직 저장된 설비 데이터가 없습니다. 호기 마스터를 붙여넣고 "
            "변경 내용을 확인해 첫 리비전을 저장하세요."
        )
    else:
        st.caption(
            f"최근 저장본 r{latest_snapshot.revision.revision_no} · "
            "저장할 때 세 표 전체가 새 리비전으로 보관됩니다."
        )
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
        )
    with st.form(WORKSPACE_FORM_KEY, border=False, enter_to_submit=False):
        # 두 저장(입력·직접 편집)이 같이 쓰는 메모라 탭 **위**에 둔다 — 저장 버튼이 표 위로
        # 올라가면서 메모만 폼 맨 아래에 남으면 적지 않고 저장하기 쉽다.
        if st.session_state.pop(_NOTE_CLEAR_KEY, False):
            st.session_state[_NOTE_KEY] = ""
        note = st.text_input("변경 메모", key=_NOTE_KEY, placeholder="예: 10월 신규 호기 30대 등록")
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
                clipboard = st.text_area(
                    "Excel 표 붙여넣기",
                    key=CLIPBOARD_KEY,
                    height=200,
                    placeholder="헤더를 포함한 전체 표를 Ctrl+V로 붙여넣으세요.",
                )
            with upload_column:
                uploaded = st.file_uploader("또는 CSV 파일 업로드", type=["csv"], key=UPLOAD_KEY)
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
                for message in pending.notices:
                    st.info(message, icon=":material/info:")
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
            confirm_delete, cancel_delete, undo_delete = _render_bulk_delete_status(frames)
            editor = _render_editors(frames, max_extent, _current_selection())
            edited = editor.frames
        with history_tab:
            try:
                _render_history(
                    repository,
                    latest_snapshot.revision.revision_id if latest_snapshot is not None else None,
                )
            except BOOTSTRAP_ERRORS as exc:
                st.error(
                    "저장 이력을 읽지 못했습니다: "
                    + bootstrap_error_message(exc, database_paths=(repository.database_path,))
                )
            history_clicked = st.form_submit_button("이력 조회", key="equipment_history_apply_v1")
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
                _save_snapshot(repository, pending.candidate, note)
            else:
                st.session_state[PREVIEW_KEY] = build_import_review(
                    target,
                    content,
                    edited,
                    floor_canvases=floor_canvases,
                    drop_examples=bool(st.session_state.get(DROP_EXAMPLE_ROWS_KEY, False)),
                )
                if import_save_clicked:
                    st.session_state[_NOTICE_KEY] = (
                        "입력 또는 편집본이 바뀌어 미리보기를 갱신했습니다. "
                        "변경 내용을 확인한 뒤 다시 저장하세요."
                    )
        elif edit_save_clicked:
            _save_snapshot(repository, edited, note)
    except BOOTSTRAP_ERRORS as exc:
        if preview_clicked or import_save_clicked:
            st.session_state.pop(PREVIEW_KEY, None)
        st.session_state[_ERROR_KEY] = bootstrap_error_message(
            exc, database_paths=(repository.database_path,)
        )
    st.rerun()
