# Purpose: 가용설비 현황 탭 ① 「설비 마스터」 본문(표·오른쪽 칸·저장 구획)을 그리고 출납을 받는다.

"""가용설비 현황 탭 ① 「설비 마스터」(개편 명세 2-3·4장 — 옛 RawData 폼을 대신한다).

- **열려 있을 때만 그린다**(D11 — AGENTS 9장 「숨은 탭에서도 입력 위젯은 그린다」 의 예외). 표
  편집은
  세션 칸(편집본·출납 기억)에 살아 숨은 회차에 그릴 까닭이 없다. 숨은 회차에 버려지는 위젯 값은 작은
  편집표 둘의 적용 전 편집(화면 탭 줄 떠나기 확인이 잡는다)·변경 메모(입력 초안)·저장 칸
  체크(기본값이
  늘 같다)뿐이고, 저장자는 `persist_state` 로 지킨다. 페이지는 이 모듈을 탭이 열린 회차에만 불러온다
  —
  표 컴포넌트 모듈이 읽힐 때 등록한다.
- **자리**: 맨 위 줄(표 고르기 · 설비 시나리오 알약 · 저장 전 변경 수) → 알림 칸(늘 서 있는 칸 —
  CCv2 마운트 앞에 생겼다 사라지는 요소를 모두 그 안에 둔다, 명세 2-3) → 넓은 화면 두 칸(7:3).
  왼쪽은 표 카드(내려받기 · 불러오기 · 표) 또는 작은 편집표, 오른쪽은 「호기 상세 · 저장 전 변경 ·
  저장 이력」 고르기와 그 칸.
- **출납**: 표·오른쪽 칸이 보낸 상태 값 `outbox` 를 받기 콜백(본문보다 먼저 돈다)이 두 마운트를 함께
  읽어 반영한다(`equipment_grid.pending_ops`·`apply_ops` → `apply_master_grid_result`). 반영한
  마지막
  seq 는 마운트마다 `ack` 로 돌려준다. 그린 회차의 조건(`GridContext` — `base`·잠금)을 콜백 인자로
  묶는다. 배치 칸을 바꾼 출납은 그때의 역할을 찍는다(`stamp_layout_role` — 탭 제출과 같다).
- **저장**: 「저장 전 변경」 아래 저장 구획 하나 — 변경 메모 · 저장 칸(저장자 · 함께 넣기 둘 · 공식
  발행) · 「한 단계 되돌리기」·「모두 버리기」(확인 팝오버)·「리비전 저장」. 「리비전 저장」 은
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

from capa_simulation.components import equipment_master_grid as grid_component
from capa_simulation.components.equipment_data_workspace import (
    _NOTE_CLEAR_KEY,
    _NOTE_KEY,
    BASELINE_DRAFT_KEY,
    BUFFER_KEY,
    DOWNTIME_DRAFT_KEY,
    DOWNTIME_EDITOR_KEY,
    DOWNTIME_VIEW_PREFIX,
    EQUIPMENT_DRAFT_KEY,
    GRID_DETAIL_KEY,
    GRID_LOADED_KEY,
    GRID_MEMO_KEY,
    NOTHING_SAVED_MESSAGE,
    REMOVAL_CONFIRM_KEY,
    SAVE_FIELDS_PREFIX,
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
    equipment_buffer_generation,
    floor_layout_words,
    grid_overlay,
    grid_toasts,
    grid_undo_steps,
    layout_edits,
    layout_lock_origins,
    pending_fab_layout,
    pending_floor_canvases,
    pending_floor_group_labels,
    pending_floor_marks,
    pending_unit_renames,
    queue_grid_toast,
    removals_elsewhere,
    render_name_changes,
    render_small_editor,
    reset_equipment_drafts,
    save_equipment_buffer,
    saved_master_violations,
    stale_delete_lock,
    stamp_layout_role,
)
from capa_simulation.components.equipment_data_workspace import (
    NAME_CHANGES_EXPANDER_KEY as _NAME_CHANGES_KEY,
)
from capa_simulation.components.equipment_data_workspace import (
    _confirmation_master as confirmation_master,
)
from capa_simulation.components.equipment_save_fields import (
    EquipmentSaveBasis,
    render_equipment_save_fields,
    save_fields_from_state,
)
from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.components.table_view_controls import filter_widget_key
from capa_simulation.equipment_scenario_activation import (
    UNMERGED_LOCK_REASON,
    EquipmentSession,
    SpaceEditMode,
)
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
    GridContext,
    GridSource,
    GridState,
    GridView,
    all_load_ids,
    apply_ops,
    build_grid_view,
    cell_text,
    change_counts,
    changes_data,
    detail_data,
    grid_data,
    grid_index,
    load_ids,
    loader_data,
    move_ids,
    pending_ops,
    prune_loaded,
    save_id_map,
    undo_top,
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
    inactive_floor_warnings,
    master_location_options,
)
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

# 표 고르기(맨 위 줄)와 오른쪽 칸 고르기 — 라벨은 고정한다(수를 넣으면 위젯 id 가 흔들린다).
TABLE_KEY: Final = "equipment_master_table_v1"
SIDE_KEY: Final = "equipment_master_side_v1"
TABLE_MASTER: Final = "설비 마스터"
TABLES: Final = (TABLE_MASTER, BASELINE_TARGET, DOWNTIME_TARGET)
SIDE_DETAIL: Final = "호기 상세"
SIDE_CHANGES: Final = "저장 전 변경"
SIDE_HISTORY: Final = "저장 이력"
SIDES: Final = (SIDE_DETAIL, SIDE_CHANGES, SIDE_HISTORY)
# 못 찾은 설비명(다음 불러오기까지)·마운트별 마지막으로 반영한 출납 seq.
MISSING_KEY: Final = "equipment_grid_missing_v1"
APPLIED_KEY: Final = "equipment_grid_applied_v1"
# 저장 구획의 단추·결과 칸.
SAVE_BUTTON_KEY: Final = "equipment_master_save_v1"
UNDO_BUTTON_KEY: Final = "equipment_master_undo_v1"
DISCARD_POPOVER_KEY: Final = "equipment_master_discard_v1"
DISCARD_CONFIRM_KEY: Final = "equipment_master_discard_confirm_v1"
SAVE_RESULT_KEY: Final = "equipment_master_save_result_v1"
DOWNLOAD_POPOVER_KEY: Final = "equipment_master_downloads_v1"
SAVE_LABEL: Final = "리비전 저장"
DISCARD_LABEL: Final = "모두 버리기"
UNDO_LABEL: Final = "한 단계 되돌리기"
NOTE_PLACEHOLDER: Final = "예: 10월 신규 호기 반입일정 갱신"
DOWNLOAD_NOTE: Final = (
    "표에서 고친 값은 곧바로 편집본에 들어가 이 파일에 함께 실립니다(못 읽은 칸 초안은 빼고)."
)
NOTHING_TO_SAVE: Final = "고친 것이 없습니다"
# 출납을 보내는 마운트(토스트 칸 이름) → 그 마운트 key.
_MOUNT_KEYS: Final = {
    "grid": grid_component.GRID_KEY,
    "detail": grid_component.side_key("detail"),
    "changes": grid_component.side_key("changes"),
}


# ------------------------------------------------------------------ 세션 칸


def loaded_ids() -> tuple[str, ...]:
    value = st.session_state.get(GRID_LOADED_KEY)
    return tuple(str(item) for item in value) if isinstance(value, (list, tuple)) else ()


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
        loaded=loaded_ids(),
    )


def _result(kind: str, text: str) -> None:
    """저장 구획 단추 아래 한 줄(성공·오류·안내) — 다음 회차에 한 번 그린다."""
    st.session_state[SAVE_RESULT_KEY] = (kind, text)


# ------------------------------------------------------------------ 표 조건·모양


def grid_context(
    session: EquipmentSession,
    basis: EquipmentSaveBasis | None,
    layout_mode: SpaceEditMode,
    *,
    latest_snapshot: EquipmentSnapshot | None,
    floor_states: FloorStates | None,
    master: pd.DataFrame,
) -> GridContext:
    """한 회차의 표 조건 — 잠금 글은 세션에서(낡음·일정 없이 엶·배치 잠금), `base` 는 편집본
    출발점."""
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
        official_places=(
            _official_places_by_name(latest_snapshot) if layout_mode.layout == "overlay" else {}
        ),
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
    examples = _example_row_count(frames, None)
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
    if layout == "overlay" and context.official_places:
        found = assumption_group_refusal(
            frames[1],
            saved[1],
            layout_lock_origins(frames[1], saved[1], renames),
            context.official_places,
        )
        if found is not None:
            errors.append(f"{found[1]} · Main 설비 — {found[0]}")
    if context.delete_lock:
        index = grid_index(frames[1], saved[1], renames)
        if index.deleted:
            errors.append(
                f"낡은 세션이라 지운 호기 {len(index.deleted):,}대는 저장되지 않습니다 — "
                "되살리거나 "
                "최신을 불러오세요"
            )
    return errors


def _alerts(
    master: pd.DataFrame, official: EquipmentSnapshot | None, today: date
) -> dict[str, str]:
    """설비명 → 일정 확인 갈래 글(「Qual 미확인 · 반입 실적 누락」) — 저장을 막지 않는다. 가정 설비
    시나리오면 공식 일정 기준이다(`official`)."""
    issues = get_schedule_confirmation_issues(
        confirmation_master(master, official, None), today=today
    )
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
    차례에 기대지 않는다). `base` 가 다른 op 는 서비스가 버리고 토스트로 센다."""
    values = [grid_component.outbox_value(key) for key in _MOUNT_KEYS.values()]
    targets = {
        mount: target
        for target, value in zip(_MOUNT_KEYS, values, strict=True)
        if (mount := grid_component.outbox_mount(value))
    }
    ops, applied = pending_ops(values, _applied())
    st.session_state[APPLIED_KEY] = applied
    if not ops:
        return
    result = apply_ops(_grid_state(), ops, context)
    apply_master_grid_result(result)
    _store_loaded(result.state.loaded)
    detail = _detail_id()
    if detail is not None and detail in result.moved:
        st.session_state[GRID_DETAIL_KEY] = result.moved[detail]
    if result.toast:
        target = targets.get(str(ops[-1].get("mount")), "grid")
        queue_grid_toast(target, result.toast, undo=result.toast_step)
    if result.frames_changed[1] and layout != "locked" and _touches_layout(ops):
        saved = st.session_state[EQUIPMENT_DRAFT_KEY]
        master = st.session_state[BUFFER_KEY][1]
        if layout_edits(master, saved, pending_unit_renames().units):
            # 배치 칸을 고친 출납 — 그때의 역할을 찍는다(저장 때 쓰기 잠금 안의 역할과 대조, 설계
            # 6-2).
            stamp_layout_role(layout)


# 배치를 바꿀 수 있는 칸 — 배치 일곱 칸과 새 호기 자리를 정하는 설비명·Main 설비.
_LAYOUT_TRIGGERS: Final = frozenset(
    {*SCENARIO_LAYOUT_COLUMNS, EQUIPMENT_ID_COLUMN, PARENT_EQUIPMENT_COLUMN}
)


def _touches_layout(ops: Sequence[Mapping[str, Any]]) -> bool:
    """배치 칸을 바꿀 수 있는 op 가 있는가 — 역할 찍기 판정(`layout_edits`, 합성 3천 대에 0.17 s
    남짓 — 샘플 관측)을 칸 고침마다 돌리지 않는다. 되돌리기·지우기·되살리기는 저장본 쪽으로 가는
    길이라 새 배치 편집을 만들지 않는다."""
    for op in ops:
        name = op.get("op")
        if name == "official":
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
    frames: Frames = st.session_state[BUFFER_KEY]
    saved = st.session_state[EQUIPMENT_DRAFT_KEY]
    index = grid_index(frames[1], saved, pending_unit_renames().units)
    if request.kind == "all":
        ids = all_load_ids(frames[1], index)
    else:
        known = set(index.live) | set(index.deleted)
        ids = [row_id for row_id in request.ids if row_id in known]
    result = load_ids(loaded_ids(), ids)
    _store_loaded(result.loaded)
    st.session_state[MISSING_KEY] = request.missing if request.kind == "names" else ()
    label = request.label or {"all": "전체", "alerts": "일정 확인 필요"}.get(request.kind, "")
    text = (
        f"{label} — {result.added:,}대를 새로 불러왔습니다"
        if label
        else (f"{result.added:,}대를 새로 불러왔습니다")
    )
    if result.already:
        text += f"({result.already:,}대는 이미 목록에 있음)"
    if result.cut or (request.kind == "all" and len(index.live) > GRID_ROW_LIMIT):
        text = f"앞 {GRID_ROW_LIMIT:,}대만 불러왔습니다 — 공정·설비명으로 좁혀 불러오세요"
    queue_grid_toast("grid", text)


def _on_clear() -> None:
    _store_loaded(())
    st.session_state[MISSING_KEY] = ()
    queue_grid_toast("grid", "목록을 비웠습니다 — 고친 내용은 그대로 남습니다")


def _open_detail(row_id: str) -> None:
    st.session_state[GRID_DETAIL_KEY] = row_id
    st.session_state[SIDE_KEY] = SIDE_DETAIL


def _on_grid_open(row_id: str) -> None:
    _open_detail(row_id)


def _on_side_open(row_id: str) -> None:
    """「저장 전 변경」 의 고칠 것·호기 이름 — 목록에 없으면 맨 위로 불러와 상세로 연다."""
    if row_id not in loaded_ids():
        _store_loaded(load_ids(loaded_ids(), [row_id]).loaded)
    _open_detail(row_id)


def _on_unload(ids: list[str]) -> None:
    drop = set(ids)
    _store_loaded(tuple(row_id for row_id in loaded_ids() if row_id not in drop))


def _on_goto(table: str, unit: str) -> None:
    """「비가동 일정 표에서 고치기」 — 표 고르기를 그 표로, 그 표 설비명 거르기를 그 이름으로. 그
    표는 이 회차에 아직 그려지지 않아 잃을 편집이 없다 — 적용 보기도 거둬 요청 보기가 그대로
    선다."""
    st.session_state[TABLE_KEY] = table
    if table == DOWNTIME_TARGET and unit:
        st.session_state[filter_widget_key(DOWNTIME_VIEW_PREFIX, EQUIPMENT_ID_COLUMN)] = [unit]
        st.session_state.pop(f"{DOWNTIME_EDITOR_KEY}_applied_view", None)


def _on_dialog(name: str) -> None:
    forget_page_dialogs()
    st.session_state[EQUIPMENT_DIALOG_KEY] = name


# ------------------------------------------------------------------ 저장 구획 콜백


def _undo_step(context: GridContext, layout: LayoutMode) -> None:
    apply_outbox(context, layout)
    result = apply_ops(_grid_state(), [{"op": "undo", "base": context.base}], context)
    apply_master_grid_result(result)
    _store_loaded(result.state.loaded)
    if result.toast:
        queue_grid_toast("changes", result.toast)


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
    removal_confirmed = None
    try:
        removal = removals_elsewhere(
            frames,
            database_path=str(repository.database_path),
            scenario_id=basis.equipment_scenario_id if basis is not None else None,
        )
    except BOOTSTRAP_ERRORS:
        removal = None
    if removal is not None and st.session_state.get(f"{REMOVAL_CONFIRM_KEY}__{removal.token}"):
        removal_confirmed = removal
    renames = pending_unit_renames()
    id_map = save_id_map(grid_index(frames[1], _saved_frames()[1], renames.units), frames[1])
    loaded, detail = loaded_ids(), _detail_id()
    note = st.session_state.get(_NOTE_KEY)
    try:
        message = save_equipment_buffer(
            repository,
            frames,
            note if isinstance(note, str) else "",
            basis=basis,
            fields=save_fields_from_state(SAVE_FIELDS_PREFIX),
            removal_confirmed=removal_confirmed,
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


def _render_head(
    session: EquipmentSession,
    basis: EquipmentSaveBasis | None,
    latest_snapshot: EquipmentSnapshot | None,
    layout: LayoutMode,
    pending: int,
) -> str:
    """맨 위 줄 — 표 고르기 · 설비 시나리오 알약 · 리비전 · 저장 전 변경 수. 고른 표를 돌려준다."""
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
        name = session.scenario_name or "설비 시나리오 없음"
        official = basis is None or basis.official_scenario
        tail = "(공식)" if official else "(가정)"
        layout_help = (
            " 배치 칸은 이 시나리오에만(공식과 다른 것만) 저장됩니다."
            if layout == "overlay"
            else " 배치 칸은 공식 배치(공통 대장)에 저장됩니다."
            if layout == "official"
            else " 배치 칸은 지금 잠겨 있습니다."
        )
        st.badge(
            f"설비 시나리오 · {name}{tail}",
            icon=":material/layers:",
            color="primary" if official else "violet",
            help=(
                "일정 칸(시나리오)은 이 시나리오에만, 나머지 칸(공통)은 모든 설비 시나리오에 함께 "
                "저장됩니다." + layout_help
            ),
        )
        if session.unmerged:
            st.badge("일정 없이 엶", icon=":material/event_busy:", color="gray")
        elif latest_snapshot is not None:
            schedule = latest_snapshot.schedule
            revision = f"공통 r{latest_snapshot.revision.revision_no}"
            if schedule is not None:
                revision += f" · 일정 r{schedule.revision_no}"
            st.badge(revision, color="gray")
        # 수가 0 이면 알약이 없다 — 늘 서 있는 칸 안에 둔다(이 줄의 자리는 그대로).
        with st.container():
            if pending:
                st.badge(f"저장 전 변경 {pending:,}건", icon=":material/edit_note:", color="orange")
    return str(table)


def _render_notices(
    session: EquipmentSession,
    basis: EquipmentSaveBasis | None,
    layout_mode: SpaceEditMode,
    floor_states: FloorStates | None,
    latest_snapshot: EquipmentSnapshot | None,
) -> None:
    """알림 — 늘 서 있는 한 칸 안에(아래 컴포넌트 마운트의 자리를 고정한다, 개편 명세 2-3)."""
    with st.container():
        if basis is not None and basis.stale:
            st.warning(_stale_lock_message(basis), icon=":material/lock_clock:")
        layout = layout_mode.layout
        scenario_name = basis.scenario_name if basis is not None else None
        if layout == "locked":
            reason = layout_mode.master_tab_lock_reason
            st.caption(
                ":material/lock: 배치 편집이 잠겨 있어 있던 호기의 배치 칸은 고칠 수 없고 새 "
                "호기는 "
                "자리 없이 들어갑니다" + (f" — {reason}" if reason else ".")
            )
        elif layout == "overlay":
            where = (
                f"「{literal_markdown(scenario_name)}」" if scenario_name else "이 설비 시나리오"
            )
            st.caption(
                f":material/layers: 가정 설비 시나리오 — 배치 칸 고침은 {where}에만(공식과 다른 "
                "것만) "
                "저장되고 공식 배치는 바뀌지 않습니다. 호기 상세 「위치」 에서 공식 자리로 되돌릴 "
                "수 "
                "있습니다."
            )
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
            for message in inactive_floor_warnings(frames[1], saved, floor_states):
                st.warning(message, icon=":material/block:")


def _render_downloads(
    repository: DuckDBEquipmentRepository,
    latest_snapshot: EquipmentSnapshot | None,
    scenario_name: str | None,
) -> None:
    """「내려받기」 팝오버 — 양식 셋 + 현재 데이터 셋(개편 명세 4-9)."""
    with st.popover("내려받기", icon=":material/download:", key=DOWNLOAD_POPOVER_KEY):
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
        )


def _render_grid_card(
    view: GridView,
    context: GridContext,
    layout: LayoutMode,
    *,
    repository: DuckDBEquipmentRepository,
    latest_snapshot: EquipmentSnapshot | None,
    acks: Mapping[str, Mapping[str, Any]],
    toasts: Mapping[str, Mapping[str, Any]],
    top: str | None,
) -> None:
    with st.container(border=True):
        with st.container(horizontal=True, horizontal_alignment="right"):
            _render_downloads(repository, latest_snapshot, context.scenario_name)
        loaded = prune_loaded(loaded_ids(), view.index)
        missing = st.session_state.get(MISSING_KEY)
        alert_ids = [row_id for row_id in view.index.live if row_id in view.alerts]
        grid_component.render_grid_loader(
            loader_data(
                view,
                loaded,
                missing=tuple(missing) if isinstance(missing, tuple) else (),
                alert_ids=alert_ids,
                first_data=latest_snapshot is None and not view.index.live,
            ),
            on_load=_on_load,
            on_clear=_on_clear,
            on_dialog=_on_dialog,
        )
        grid_component.render_grid_table(
            grid_data(
                view,
                loaded,
                toast=toasts.get("grid"),
                undo_top=top,
                ack=acks.get("grid"),
                open_id=_detail_id(),
            ),
            on_outbox=partial(_on_outbox, context, layout),
            on_open=_on_grid_open,
            on_unload=_on_unload,
        )


def _render_save_section(
    repository: DuckDBEquipmentRepository,
    *,
    view: GridView,
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
    st.text_input("변경 메모", key=_NOTE_KEY, placeholder=NOTE_PLACEHOLDER)
    render_equipment_save_fields(
        SAVE_FIELDS_PREFIX,
        show_publish=basis is None or basis.official_scenario,
        release_exists=basis is None or basis.release_no > 0,
        persist_saved_by=True,
    )
    with st.container():
        try:
            removal = removals_elsewhere(
                frames,
                database_path=str(repository.database_path),
                scenario_id=basis.equipment_scenario_id if basis is not None else None,
            )
        except BOOTSTRAP_ERRORS:
            removal = None
        if removal is not None:
            st.warning(removal.message(), icon=":material/group_remove:")
            st.checkbox(removal.confirm_label(), key=f"{REMOVAL_CONFIRM_KEY}__{removal.token}")
    counts = change_counts(view)
    errors = counts.errors
    scenario = literal_markdown(basis.scenario_name) if basis is not None else "이 설비 시나리오"
    if session.legacy_trace_count:
        hint = legacy_trace_message(session.legacy_trace_count)
    elif errors:
        hint = f"오류 {errors:,}개를 고쳐야 저장됩니다"
    elif _has_changes(frames):
        hint = (
            f"공통 칸은 모든 설비 시나리오에, 시나리오 칸은 「{scenario}」 에 새 리비전으로 "
            "저장됩니다"
        )
        if layout == "overlay":
            hint += f" — 배치 칸은 「{scenario}」 에만(공식과 다른 것만)"
    else:
        hint = NOTHING_TO_SAVE
    st.caption(hint)
    has_fab = pending_fab_layout() is not None
    floor_pending = bool(
        pending_floor_canvases() or pending_floor_marks() or pending_floor_group_labels()
    )
    with st.container(horizontal=True, gap="small"):
        st.button(
            UNDO_LABEL,
            key=UNDO_BUTTON_KEY,
            icon=":material/undo:",
            on_click=_undo_step,
            args=(context, layout),
            disabled=not grid_undo_steps(),
        )
        with st.popover(DISCARD_LABEL, icon=":material/delete_sweep:", key=DISCARD_POPOVER_KEY):
            st.caption(
                "편집본을 저장본으로 다시 세웁니다 — 되돌릴 수 없습니다."
                + (" Space 층 배치 대기분도 함께 버립니다." if floor_pending else "")
                + (" S.PKG FAB 전체 배치 대기분은 남깁니다." if has_fab else "")
            )
            st.button(
                "모두 버리기 확인",
                key=DISCARD_CONFIRM_KEY,
                type="primary",
                icon=":material/delete_forever:",
                on_click=_discard_all,
            )
        st.button(
            SAVE_LABEL,
            key=SAVE_BUTTON_KEY,
            type="primary",
            icon=":material/save:",
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
    with st.container():
        result = st.session_state.pop(SAVE_RESULT_KEY, None)
        if isinstance(result, tuple) and len(result) == 2:
            kind, text = result
            if kind == "success":
                st.success(text)
            elif kind == "error":
                st.error(text)
            else:
                st.info(text)


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
    basis = session.save_basis()
    layout: LayoutMode = layout_mode.layout
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
    )
    view = build_view(
        context,
        floor_canvases=floor_canvases,
        today=today,
        confirmation_official=confirmation_official,
        layout=layout,
    )
    counts = change_counts(view)
    pending = counts.total + (1 if view.source.others else 0)
    table = _render_head(session, basis, latest_snapshot, layout, pending)
    _render_notices(session, basis, layout_mode, floor_states, latest_snapshot)
    acks = _acks(_applied())
    toasts = grid_toasts()
    top = undo_top(grid_undo_steps())
    submit = None
    left, right = st.columns([7, 3], gap="medium")
    with left:
        if table == TABLE_MASTER:
            _render_grid_card(
                view,
                context,
                layout,
                repository=repository,
                latest_snapshot=latest_snapshot,
                acks=acks,
                toasts=toasts,
                top=top,
            )
        else:
            stale = (basis is not None and basis.stale) or session.unmerged
            submit = render_small_editor(
                table,
                stale=stale,
                delete_locked=context.delete_lock,
                drafts_replaced=drafts_replaced,
                floor_canvases=floor_canvases,
            )
    with right:
        _seed(SIDE_KEY, SIDE_DETAIL, SIDES)
        side = st.segmented_control(
            "오른쪽 칸",
            SIDES,
            key=SIDE_KEY,
            required=True,
            persist_state="session",
            label_visibility="collapsed",
        )
        if side == SIDE_HISTORY:
            try:
                _render_history(
                    repository,
                    scenario_id=_history_scenario(repository, basis, latest_snapshot),
                    scenario_name=basis.scenario_name if basis is not None else None,
                    in_form=False,
                )
            except BOOTSTRAP_ERRORS as exc:
                st.error(
                    "저장 이력을 읽지 못했습니다: "
                    + bootstrap_error_message(exc, database_paths=(repository.database_path,))
                )
        elif side == SIDE_CHANGES:
            grid_component.render_grid_side(
                "changes",
                changes_data(
                    view, ack=acks.get("changes"), toast=toasts.get("changes"), undo_top=top
                ),
                on_outbox=partial(_on_outbox, context, layout),
                on_open=_on_side_open,
                on_goto=_on_goto,
            )
            _render_save_section(
                repository,
                view=view,
                basis=basis,
                session=session,
                context=context,
                layout=layout,
                floor_canvases=floor_canvases,
                today=today,
            )
        else:
            grid_component.render_grid_side(
                "detail",
                detail_data(
                    view,
                    _detail_id(),
                    ack=acks.get("detail"),
                    toast=toasts.get("detail"),
                    undo_top=top,
                ),
                on_outbox=partial(_on_outbox, context, layout),
                on_open=_on_side_open,
                on_goto=_on_goto,
            )
    # 작은 편집표 제출은 화면의 모든 위젯을 그린 뒤 처리한다(`st.rerun()` 으로 끝난다).
    if submit is not None:
        submit()
