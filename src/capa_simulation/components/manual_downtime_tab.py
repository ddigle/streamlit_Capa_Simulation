# Purpose: 가용설비 현황 Preference 탭의 입력 비가동 편집표·버전 대조 저장·이력을 그린다.

"""가용설비 현황 ③ 「Preference」 — 입력 비가동 대수(2026-10-27 사용자 결정).

호기에 잇지 않고 **공정 × 생산월로 넣는 비가동 대수**(환산 대수, 소수)다. 넣은 대수는 실행 관리의
「설비 일정 기준 가용대수」(단축 전 월별 환산 가용)에서 빠진다 — 공정 Capa 상세 ②·④, 필요 단축 일정,
제약 시뮬레이션, Space 필요 단축 보기가 같이 바뀐다. HOME·Static 의 기준정보 가용과 주차별 가용,
이 화면의 Summary(Main·Static 대비 일정)는 그대로다(규칙은 `services/manual_downtime.py`).

- **행은 공정, 열은 조회기간의 달**(사이드바 조회기간 — 생산월, 공정 Capa 상세와 같은 W/D 월)이다.
  공정은 지금 설비 시나리오 저장본의 공정(설비 마스터 `공정소분류` · 기존보유 `공정`)이고, 그 밖에
  저장된 값이 있는 공정도 뒤에 선다(「설비 마스터에 없음」). 보이는 글자만 공정 표시명이다.
- **칸**은 0 이상 소수(둘째 자리)다. 빈칸 = 0 이고 0 칸은 저장하지 않는다.
- **저장은 버전 대조**다 — 편집을 시작한 회차의 version 을 세션에 두고(`write_guard.remember_seen`)
  저장 회차에 넘긴다. 그 사이 다른 사람이 저장했으면 저장소가 거부하고 최신을 다시 그린다(확보율
  보정 편집표와 같은 길 — 제 저장의 빠른 두 번 누름은 성공으로, 거부 뒤 둘째 누름은 거부로 다시
  알린다). 저장은 **보이는 범위(조회기간 달 × 보이는 공정)만** 갈아 쓰고 그 밖의 저장 칸은 남긴다.
- **모든 설비 시나리오 공용**이다 — Cut-off 처럼 가정 설비 시나리오를 보는 동안에는 표를 잠근다
  (E3 와 같은 규칙. 시나리오별 값은 다음 몫).
- 폼은 **숨은 탭에서도 그린다**(AGENTS 9장 — 적은 칸이 버려지지 않게). 저장 이력 표만 열린 회차에
  읽어 그린다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.profile_caption import profile_version_caption
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.components.write_guard import (
    SEEN_MISSING_MESSAGE,
    held_profile_conflict,
    is_own_save,
    note_profile_conflict,
    own_save_marks,
    profile_conflict_marks,
    queue_refusal,
    remember_own_save,
    remember_seen,
    seen,
    take_refusal,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.equipment_cache import (
    clear_manual_downtime_cache,
    get_equipment_repository,
    load_manual_downtime,
    load_manual_downtime_saves,
)
from capa_simulation.services.manual_downtime import (
    MANUAL_DOWNTIME_MAX_UNITS,
    ManualDowntime,
    ManualDowntimeSave,
    manual_units_text,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

__all__ = [
    "MANUAL_BASE_VERSION_KEY",
    "MANUAL_EDITOR_KEY",
    "MANUAL_FLASH_KEY",
    "MANUAL_FORM_KEY",
    "MANUAL_NOTE_KEY",
    "MANUAL_PROCESS_COLUMN",
    "MANUAL_SAVED_BY_KEY",
    "MANUAL_SAVED_MESSAGE",
    "MANUAL_SAVE_BUTTON",
    "MANUAL_SAVE_NAME",
    "MANUAL_UNCHANGED_MESSAGE",
    "edited_cells",
    "manual_editor_frame",
    "manual_tab_processes",
    "render_manual_downtime_tab",
]

MANUAL_FORM_KEY: Final = "equipment_manual_downtime_form"
MANUAL_EDITOR_KEY: Final = "equipment_manual_downtime_editor"
MANUAL_NOTE_KEY: Final = "equipment_manual_downtime_note"
MANUAL_SAVED_BY_KEY: Final = "equipment_manual_downtime_saved_by"
MANUAL_BASE_VERSION_KEY: Final = "equipment_manual_downtime_base_version"
MANUAL_SAVE_NAME: Final = "equipment_manual_downtime"
MANUAL_FLASH_KEY: Final = "equipment_manual_downtime_flash"
MANUAL_SAVE_BUTTON: Final = "입력 비가동 저장"
MANUAL_PROCESS_COLUMN: Final = "공정"
MANUAL_SAVED_MESSAGE: Final = (
    "입력 비가동 대수를 저장했습니다 — 공정 Capa 상세 ②·④·필요 단축 일정·제약 시뮬레이션·"
    "Space 필요 단축 보기가 새 값으로 계산합니다."
)
MANUAL_UNCHANGED_MESSAGE: Final = "바뀐 칸이 없어 저장하지 않았습니다."
# 「설비 마스터에 없음」 공정 꼬리(저장된 값만 남은 공정).
_ABSENT_SUFFIX: Final = " (설비 마스터에 없음)"
_HISTORY_LIMIT: Final = 20


def manual_tab_processes(
    snapshot_processes: Sequence[str], profile: ManualDowntime
) -> tuple[tuple[str, ...], frozenset[str]]:
    """표의 행 공정과 그 가운데 설비 저장본에 없는 공정.

    저장본의 공정(이름 차례)이 먼저이고, 그 밖에 저장된 값이 있는 공정이 뒤에 선다 — 값을 지울 수
    있게 숨기지 않는다.
    """
    present = sorted(
        {str(process).strip() for process in snapshot_processes if str(process).strip()}
    )
    stored_only = sorted(set(profile.processes) - set(present))
    return (*present, *stored_only), frozenset(stored_only)


def manual_editor_frame(
    profile: ManualDowntime,
    processes: Sequence[str],
    months: Sequence[int],
    labels: ProcessLabels,
    *,
    absent: frozenset[str] = frozenset(),
) -> pd.DataFrame:
    """편집표 — index 는 원본 공정명(감춘다), 첫 칸은 공정 표시명(고칠 수 없다), 달마다 한 칸
    (이름은 `YYYYMM` 글자). 저장된 0 아닌 값만 채우고 나머지는 빈칸(None)이다."""
    cells = profile.cells
    frame = pd.DataFrame(
        {
            MANUAL_PROCESS_COLUMN: [
                labels.label(process) + (_ABSENT_SUFFIX if process in absent else "")
                for process in processes
            ]
        },
        index=pd.Index(list(processes), dtype="object"),
    )
    for month in months:
        frame[str(int(month))] = pd.Series(
            [cells.get((process, int(month))) for process in processes],
            index=frame.index,
            dtype="Float64",
        )
    return frame


def edited_cells(
    edited: pd.DataFrame, processes: Sequence[str], months: Sequence[int]
) -> dict[tuple[str, int], object]:
    """편집표 결과를 (공정, 달) → 칸 값으로 — 보이는 범위 전부(빈칸 포함). 행은 index(원본 공정명)로
    읽는다(화면에서 정렬해도 결과 차례는 바뀌지 않지만 위치에 기대지 않는다)."""
    cells: dict[tuple[str, int], object] = {}
    wanted = set(processes)
    for process in edited.index:
        name = str(process)
        if name not in wanted:
            continue
        for month in months:
            column = str(int(month))
            value = edited.at[process, column] if column in edited.columns else None
            cells[(name, int(month))] = None if pd.isna(value) else value
    return cells


def render_manual_downtime_tab(
    *,
    database_path: str,
    snapshot_processes: Sequence[str],
    months: Sequence[int],
    process_labels: ProcessLabels,
    owner_tab: OpenTab | None,
    locked_reason: str | None = None,
) -> None:
    """탭 본문. 숨은 회차에도 폼을 그린다(적은 칸을 지킨다) — 저장 이력만 열린 회차에 그린다."""
    try:
        profile = load_manual_downtime(database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            "입력 비가동 대수를 읽지 못했습니다 — "
            + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
        )
        return
    processes, absent = manual_tab_processes(snapshot_processes, profile)
    ordered_months = sorted({int(month) for month in months})
    _render_intro(profile, ordered_months)
    if locked_reason is not None:
        st.info(locked_reason, icon=":material/lock:")
    if not processes or not ordered_months:
        st.info(
            "넣을 칸이 없습니다 — 설비 마스터를 저장하면 그 공정이 행으로 서고, 열은 사이드바 "
            "조회기간의 달입니다."
        )
        return
    _render_editor(
        database_path=database_path,
        profile=profile,
        processes=processes,
        absent=absent,
        months=ordered_months,
        process_labels=process_labels,
        locked=locked_reason is not None,
    )
    if not tab_is_hidden(owner_tab):
        _render_history(database_path)


def _render_intro(profile: ManualDowntime, months: Sequence[int]) -> None:
    st.markdown("#### :material/event_busy: 월별 비가동 대수(입력)")
    st.caption(
        "호기에 잇지 않고 **공정 × 달로 넣는 비가동 대수**(환산 대수, 소수 가능)입니다. "
        "호기별 비가동과 별도 손실로 **설비 일정 기준 가용대수**에서 더 뺍니다 — 공정 Capa "
        "상세 ②·④, 필요 단축 일정, 제약 시뮬레이션, Space 필요 단축 보기가 같이 바뀝니다. "
        "그 달 가용보다 크면 가용은 0 에서 멈춥니다. HOME·Static(기준정보 가용)·표준 목표·"
        "표준 대비 재공(주차별 가용)·이 화면 Summary 는 그대로입니다."
    )
    period = f"{month_label(months[0])}–{month_label(months[-1])}" if months else "없음"
    outside = sum(1 for _, month, _ in profile.rows if month not in set(months))
    st.caption(
        f"열은 조회기간({period})의 생산월 — 공정별 Cut-off 의 W/D 월(공정 Capa 상세와 같은 달). "
        "빈칸 = 0. 모든 설비 시나리오 공용입니다."
        + (f" 조회기간 밖에 저장된 {outside}칸은 그대로 둡니다." if outside else "")
    )
    st.caption(profile_version_caption(profile, empty="아직 넣은 입력 비가동이 없습니다"))


def _render_editor(
    *,
    database_path: str,
    profile: ManualDowntime,
    processes: Sequence[str],
    absent: frozenset[str],
    months: Sequence[int],
    process_labels: ProcessLabels,
    locked: bool,
) -> None:
    """편집표 폼과 저장(버전 대조). 확보율 보정 편집표(`home_preference`)와 같은 차례다."""
    submitted_base = seen(MANUAL_BASE_VERSION_KEY)
    frame = manual_editor_frame(profile, processes, months, process_labels, absent=absent)
    with st.form(MANUAL_FORM_KEY):
        # 작업 줄(저장·저장자·메모)은 표 **위**, 버튼이 왼쪽이다(오른쪽 끝은 표 도구 막대에 가린다).
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            submitted = st.form_submit_button(
                MANUAL_SAVE_BUTTON,
                icon=":material/save:",
                type="primary",
                disabled=locked,
            )
            saved_by = st.text_input("저장자(선택)", key=MANUAL_SAVED_BY_KEY, disabled=locked)
            note = st.text_input(
                "변경 메모",
                placeholder="예: 26.07 Wafer Mount PM 1.5대",
                key=MANUAL_NOTE_KEY,
                disabled=locked,
            )
        # 저장 결과(성공·오류)는 누른 버튼 바로 아래 한 자리다.
        notice = st.container()
        with notice:
            render_flash(MANUAL_FLASH_KEY)
            refused = take_refusal(MANUAL_SAVE_NAME)
            if refused is not None:
                st.error(refused)
        edited = st.data_editor(
            frame,
            key=MANUAL_EDITOR_KEY,
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
            placeholder="",
            disabled=True if locked else [MANUAL_PROCESS_COLUMN],
            column_config={
                MANUAL_PROCESS_COLUMN: st.column_config.TextColumn(
                    "공정", pinned=True, width="medium"
                ),
                **{
                    str(int(month)): st.column_config.NumberColumn(
                        month_label(int(month)),
                        min_value=0.0,
                        max_value=MANUAL_DOWNTIME_MAX_UNITS,
                        step=0.01,
                        format="%.2f",
                    )
                    for month in months
                },
            },
        )
    if not submitted:
        # 이 회차가 그린 저장본이 사용자가 본 화면이다 — 제출·충돌 회차에는 적지
        # 않는다(write_guard).
        remember_seen(MANUAL_BASE_VERSION_KEY, profile.version)
        return
    # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    save_marks = own_save_marks()
    conflict_marks = profile_conflict_marks()
    held = held_profile_conflict(conflict_marks, MANUAL_SAVE_NAME)
    if held is not None:
        # 남의 저장에 거부된 누름의 둘째 누름이다 — 옛 화면의 입력이라 저장하지 않고 그 거부를 다시
        # 알린다. 본 version 은 이 회차가 그린 최신 저장본으로 적는다(확보율 보정과 같다).
        remember_seen(MANUAL_BASE_VERSION_KEY, profile.version)
        if refused != held:
            notice.error(held)
        return
    if not isinstance(submitted_base, int):
        # 편집을 시작한 version 을 모른다 — 지금 version 으로 대체하지 않는다(write_guard).
        queue_refusal(MANUAL_SAVE_NAME, SEEN_MISSING_MESSAGE)
        st.rerun(scope="app")
    expected_version = submitted_base
    try:
        version = get_equipment_repository(database_path).save_manual_downtime(
            edited_cells(edited, processes, months),
            processes=processes,
            months=months,
            expected_version=expected_version,
            saved_by=str(saved_by or ""),
            note=str(note or ""),
        )
    except ProfileVersionConflict as exc:
        # 앱 밖의 쓰기면 이 회차가 그린 저장본도 낡았을 수 있다 — 다음 회차가 최신을 그리게 비운다.
        # 이 회차는 본 version 을 올리지 않는다(다음 회차가 최신을 그리며 적는다).
        clear_manual_downtime_cache()
        if is_own_save(MANUAL_SAVE_NAME, exc.expected, exc.stored, save_marks):
            # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
            queue_flash(MANUAL_FLASH_KEY, MANUAL_SAVED_MESSAGE)
        else:
            message = bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
            note_profile_conflict(conflict_marks, MANUAL_SAVE_NAME, message)
            queue_refusal(MANUAL_SAVE_NAME, message)
        st.rerun(scope="app")
    except BOOTSTRAP_ERRORS as exc:
        notice.error(bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)))
        return
    except ValueError as exc:
        notice.error(bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)))
        return
    if version is None:
        notice.info(MANUAL_UNCHANGED_MESSAGE, icon=":material/info:")
        return
    remember_own_save(MANUAL_SAVE_NAME, expected_version, version, save_marks)
    # 저장마다 공정 Capa 상세·필요 단축 일정 등의 계산 키(칸 자체)가 바뀐다 — 프로필 캐시만 비운다.
    clear_manual_downtime_cache()
    queue_flash(MANUAL_FLASH_KEY, MANUAL_SAVED_MESSAGE)
    st.rerun(scope="app")


def _render_history(database_path: str) -> None:
    """저장 이력(최근 것부터) — 위젯 없는 읽기 전용 표라 열린 회차에만 읽는다."""
    try:
        saves = load_manual_downtime_saves(database_path, limit=_HISTORY_LIMIT)
    except BOOTSTRAP_ERRORS as exc:
        message = bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
        st.caption(f"저장 이력을 읽지 못했습니다 — {message}")
        return
    with st.expander(
        f":material/history: 저장 이력 {len(saves)}건"
        + (f"(최근 {_HISTORY_LIMIT}건)" if len(saves) >= _HISTORY_LIMIT else ""),
        key="equipment_manual_downtime_history",
    ):
        if not saves:
            st.caption("아직 저장한 적이 없습니다.")
            return
        st.dataframe(_history_frame(saves), hide_index=True, width="stretch")


def _history_frame(saves: Sequence[ManualDowntimeSave]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "버전": [f"v{save.version}" for save in saves],
            "저장 시각": [f"{save.saved_at:%Y-%m-%d %H:%M}" for save in saves],
            "저장자": [save.saved_by for save in saves],
            "메모": [save.note for save in saves],
            "바뀐 칸": [save.changed_cells for save in saves],
            "채운 칸": [save.filled_cells for save in saves],
            "대수 합": [manual_units_text(save.total_units) for save in saves],
        }
    )
