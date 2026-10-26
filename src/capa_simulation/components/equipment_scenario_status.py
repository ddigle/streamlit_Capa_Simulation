# Purpose: 사이드바 조건 패널의 「설비 시나리오」 줄(배지·잠근 꼴)과 팝업(불러오기·저장)을 그린다.

"""사이드바 「조회 조건」 패널의 설비 시나리오 줄과 팝업(설계 6-1).

- **줄은 페이지가 그린다.** `app.py` 는 패널 안에 블록 칸 하나만 세우고(`sidebar_status`), 페이지가
  `resolve_equipment_session` 뒤 그 칸에 줄을 그린다 — 배지가 그 회차 목록으로 맞고(한 회차 늦지
  않음), 부트스트랩 오류는 페이지의 오류 처리 안에서 나며, `app.py` 는 설비 DB 를 읽지 않는다. 값 칸
  단추는 위젯 상태가 없고 값은 세션 칸에만 있어 페이지가 그려도 화면 사이에 잃을 것이 없다.
- 값 칸 「운영 일정 · r12」, 배지 하나 — `미저장 변경`(주황 띠) → `일정 없이 엶` → `공식 vN` →
  `최신 rM 있음`(낡음) → `가정 배치`(그리는 한 벌의 배치가 공식과 다름 — 설비 0031) → `저장된
  리비전` 차례. 라벨은 늘 「설비 시나리오」.
- **잠근 꼴**(팝업 없음): 값 칸 「운영 일정 · r12 (고정)」 — 공정 Capa 상세 HOME 방문(까닭은 줄 아래
  한 줄). 긴 이름은 값 칸에서 줄여 리비전 번호가 늘 보인다. Space 현황은 고를 수 있는 줄이다(설비
  시나리오 2단계 S3 — 그 시나리오의 배치를 그린다).
- **팝업은 세션 키로 연다** — `app.py` 의 호스트 프래그먼트가 셋째 갈래로 부른다(한 실행에 팝업
  하나). 「불러오기」 는 모든 설비 화면, 「저장」 은 편집본을 세우는 화면(가용설비 현황·필요 단축
  일정)에만 선다. 저장소는 팝업을 연 동안에만 읽는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import streamlit as st

# 테스트가 `settings.EQUIPMENT_DUCKDB_PATH` 를 갈아끼운다 — 부를 때 모듈에서 찾는다.
import capa_simulation.settings as settings
from capa_simulation.components.app_header import (
    UNMERGED_STATUS,
    equipment_header_suffix,
    refresh_equipment_header,
    short_scenario_name,
)
from capa_simulation.components.condition_field import condition_field
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    DOWNTIME_DRAFT_KEY,
    EQUIPMENT_DRAFT_KEY,
    Frames,
    has_unsaved_equipment_edits,
    new_unit_choice_line,
    pending_fab_layout,
    pending_unit_renames,
    save_equipment_buffer,
    schedule_revision_title,
    stale_save_refusal,
)
from capa_simulation.components.equipment_save_fields import (
    SaveCandidateCounts,
    render_equipment_save_fields,
)
from capa_simulation.components.equipment_scenario_management import render_legacy_trace_goto
from capa_simulation.components.literal_markdown import literal_markdown, markdown_safe_tildes
from capa_simulation.components.space_floor_list import (
    discard_floor_state_draft,
    floor_state_draft_pending,
)
from capa_simulation.equipment_scenario_activation import (
    EquipmentSession,
    current_selection,
    resolve_equipment_session,
    select_equipment_scenario,
)
from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS, REQUIRED_SHORTENING
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    forget_page_dialogs,
    prune_choice,
)
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_equipment_schedule_revisions,
)
from capa_simulation.persistence.equipment_repository import (
    EquipmentScheduleRevisionSummary,
    legacy_trace_message,
)
from capa_simulation.services.equipment_contract import EQUIPMENT_ID_COLUMN
from capa_simulation.services.korean_particle import with_object_particle, with_topic_particle
from capa_simulation.services.shortening_baseline import ShorteningEquipmentBasis
from capa_simulation.sidebar_status import (
    CONDITION_DIALOG_FRAGMENT_KEY,
    equipment_scenario_slot,
    keeps_app_run_open,
    rerun_fragment_if_alone,
)

EQUIPMENT_SCENARIO_FIELD_KEY = "sidebar_equipment_scenario_field"
EQUIPMENT_SCENARIO_FIELD_LABEL = "설비 시나리오"
EQUIPMENT_SCENARIO_FIELD_ICON = ":material/account_tree:"
EQUIPMENT_SCENARIO_DIALOG_TITLE = "설비 시나리오"
# 팝업 열림 칸. `PAGE_DIALOG_SUFFIX` 로 끝나 페이지를 떠나면 비워진다.
EQUIPMENT_SCENARIO_DIALOG_KEY = f"sidebar_equipment_scenario{PAGE_DIALOG_SUFFIX}"
EQUIPMENT_SCENARIO_DIALOG_MODE_KEY = "sidebar_equipment_scenario_dialog_mode"
LOAD_MODE = "불러오기"
SAVE_MODE = "저장"
# 팝업 안 시나리오·리비전 초안. 열 때마다 세션 값으로 다시 적는다.
DIALOG_SCENARIO_KEY = "sidebar_equipment_scenario_id"
DIALOG_REVISION_KEY = "sidebar_equipment_schedule_revision_id"
DISCARD_KEY = "sidebar_equipment_discard_unsaved"
# Space 층 사용 편집 초안이 있는데 가정 설비 시나리오를 고른 회차의 한 줄(그 초안은 버려진다 — Q3).
FLOOR_DRAFT_DISCARD_NOTE = (
    "저장하지 않은 Space 층 사용 편집이 있습니다 — 층 사용은 공식 설비 시나리오에서만 고쳐, 가정 "
    "설비 시나리오를 불러오면 버려집니다."
)
LOAD_BUTTON_KEY = "sidebar_equipment_load_revision"
SAVE_BUTTON_KEY = "sidebar_equipment_save"
SAVE_NOTE_KEY = "sidebar_equipment_save_note"
# 메모 칸 key 세대 — 저장에 성공한 회차에만 올라 다음에 빈 칸으로 선다(닫힌 팝업의 칸은 세션에 빈
# 값을 적어도 브라우저가 옛 값을 되보낸다 — `scenario_status.save_field_key` 와 같은 까닭).
SAVE_NOTE_GENERATION_KEY = "sidebar_equipment_save_note_generation"
SAVE_FIELDS_PREFIX = "sidebar_equipment_save"
# 「저장」 구획 안내 끝 — 설비 마스터 탭 작은 편집표의 적용 전 편집은 위젯 상태라 편집본에 없다.
UNAPPLIED_SMALL_EDITS_NOTE = (
    "기존 보유대수·비가동 일정 표에서 아직 「편집본에 적용」 하지 않은 편집은 저장되지 않습니다."
)
# 불러오기·저장 알림 — 다음 회차에 한 번, 줄 바로 아래.
FLASH_KEY = "sidebar_equipment_scenario_flash"
# 「저장」 구획을 세우는 화면(편집본을 세우는 화면)의 파일 이름.
SAVE_PAGES = frozenset(
    {Path(AVAILABLE_EQUIPMENT_STATUS.path).name, Path(REQUIRED_SHORTENING.path).name}
)
_NOTE_PREVIEW_LIMIT = 40


# 잠근 꼴(공정 Capa 상세 HOME 방문)의 값 칸 꼬리.
FIXED_LOCK_REASON = "(고정)"
# 이름 줄 배지 「가정 배치」 — 그리는 한 벌의 배치가 공식과 다르다(가정 설비 시나리오의 배치 차이).
LAYOUT_BADGE = "가정 배치"
# HOME 칸으로 들어온 공정 Capa 상세의 잠근 까닭. 값 칸에는 「(고정)」 만 붙이고 이 글은 줄 아래 한
# 줄로 둔다 — 값 칸 끝에 붙이면 1280px 창에서도 「(HOME 칸에서 들어…」 로 잘리고, 꺼진 단추라
# 풍선도 없어 ◀▶ 뒤(출처 띠가 걷힌 뒤) 기준을 알리는 자리가 사라진다(2026-10-24 E2E).
HOME_VISIT_LOCK_REASON = (
    "HOME 칸에서 들어온 방문이라 공식 설비 시나리오로 고정했습니다 — ◀▶ 로 옮겨도 그대로입니다."
)
# 가정 설비 시나리오에서 「설정」 팝업의 공용 Cut-off 를 잠근 까닭(E3).
PREFERENCE_LOCK_MESSAGE = (
    "Cut-off 는 모든 설비 시나리오 공용입니다 — 공식 설비 시나리오에서 고칩니다. 지금은 가정 설비 "
    "시나리오를 보는 중이라 표를 잠갔습니다."
)


def unscheduled_notice(count: int, *, official: bool = False) -> str | None:
    """이 설비 시나리오에 일정 행이 없는 호기 n대 한 줄(F4). 0대면 None.

    `official` 이면 공식 설비 시나리오(공식 발행 쌍)를 그리는 회차의 문구다(「공식 일정 없음 n대」 —
    Space 가 공식 세션일 때).
    """
    if count <= 0:
        return None
    if official:
        return (
            f"공식 일정 없음 {count:,}대 — 공식 설비 시나리오에 일정이 없는 호기는 이 화면에 "
            "그리지 않습니다(가정 설비 시나리오에만 든 호기)."
        )
    return (
        f"이 설비 시나리오에 일정이 없는 호기 {count:,}대 — 이 시나리오 계산에 들지 않습니다. "
        "넣으려면 그 호기의 일정 칸이나 시나리오 메모에 값을 적어 저장하세요."
    )


def render_legacy_trace_warning(session: EquipmentSession) -> None:
    """옛 배포로 저장한 설비 리비전이 있으면 맨 위 경고 한 줄(저장 거부 문구와 같은 글)과 「시나리오
    관리에서 이어 쓰기」 단추 — 「이대로 이어 쓰기」 는 다른 화면(시나리오 관리 「설비 시나리오」
    구획)에 있어 그리로 옮기는 길을 둔다."""
    if session.legacy_trace_count:
        st.warning(legacy_trace_message(session.legacy_trace_count), icon=":material/history:")
        render_legacy_trace_goto()


def equipment_basis_label(session: EquipmentSession) -> str | None:
    """화면이 보는 설비 시나리오 한 마디 — 「셋업 실무 r4」(공식 발행 쌍이면 「공식 v3」)."""
    if session.scenario_name is None:
        return None
    if session.is_official_pair and session.release_no is not None:
        return f"공식 v{session.release_no}"
    if session.revision_no is None:
        return session.scenario_name
    return f"{session.scenario_name} r{session.revision_no}"


def baseline_equipment_refusal(session: EquipmentSession | None) -> str | None:
    """진척 비교 기준선을 저장하지 않을 설비 쪽 까닭 — 세션이 **공식 발행 쌍**이 아니면(E5).

    까닭은 둘로 가른다 — 가정 설비 시나리오, 또는 공식 시나리오의 발행하지 않은 리비전. 시나리오가
    없거나(빈 설비 DB) 공식 발행 쌍이면 None.
    """
    if session is not None and session.unmerged:
        return (
            "옛 배포로 저장한 공통 대장이 설비 시나리오 일정과 합쳐지지 않아 일정 없이 연 상태라 "
            "기준선을 저장하지 않습니다 — 런북 4-2 대로 백업을 복원한 뒤 저장하세요."
        )
    if session is None or session.scenario is None or session.is_official_pair:
        return None
    official = f"공식 v{session.release_no}" if session.release_no is not None else "공식"
    if session.is_assumption:
        return (
            f"가정 설비 시나리오(「{session.scenario_name}」 r{session.revision_no})를 보는 중이라 "
            f"기준선을 저장하지 않습니다 — 진척 비교 기준선은 공식 설비 시나리오({official})에서만 "
            "저장합니다. 사이드바 설비 시나리오에서 공식을 불러온 뒤 저장하세요."
        )
    return (
        f"발행하지 않은 리비전(「{session.scenario_name}」 r{session.revision_no} — 공식은 "
        f"{official})을 보는 중이라 기준선을 저장하지 않습니다 — 공식으로 발행하거나 공식 "
        "리비전을 불러온 뒤 저장하세요."
    )


def shortening_equipment_basis(session: EquipmentSession) -> ShorteningEquipmentBasis:
    """필요 단축 일정이 기준선 머리(0027 출처 칸)·진척 비교 머리·카드 링크 `eq` 에 실을 설비 쪽."""
    schedule = session.snapshot.schedule if session.snapshot is not None else None
    label = equipment_basis_label(session)
    note = None
    if session.scenario is not None and not session.is_official_pair:
        note = f"지금 = {label} · 기준선 = 공식(진척 비교 기준선은 공식 설비 시나리오에서 저장)"
    return ShorteningEquipmentBasis(
        schedule_revision_id=schedule.schedule_revision_id if schedule is not None else None,
        schedule_revision_no=schedule.revision_no if schedule is not None else None,
        scenario_name=session.scenario_name,
        release_no=session.release_no if session.is_official_pair else None,
        label=label,
        compare_note=note,
    )


def equipment_value_label(session: EquipmentSession) -> str:
    """값 칸 글 — 「운영 일정 · r12」(리비전이 없으면 시나리오 이름만)."""
    if session.scenario_name is None:
        return "설비 시나리오 없음"
    name = literal_markdown(session.scenario_name)
    return f"{name} · r{session.revision_no}" if session.revision_no is not None else name


def equipment_field_label(session: EquipmentSession) -> str:
    """사이드바 값 칸 글 — 「운영 일정 · r12」. 이름이 길면 줄여 「 · rN」 이 잘리지 않게 한다."""
    if session.scenario_name is None:
        return "설비 시나리오 없음"
    name = literal_markdown(short_scenario_name(session.scenario_name))
    return f"{name} · r{session.revision_no}" if session.revision_no is not None else name


def equipment_status_badge(session: EquipmentSession, *, unsaved: bool) -> str:
    """이름 줄 배지 하나 — 미저장 → 일정 없이 엶 → 공식 vN → 낡음 → 가정 배치 → 저장된 리비전
    차례(공식 쌍은 배치 차이가 없어 「공식 vN」 과 겹치지 않고, 낡음이 더 급하다 — 설계 8-2).
    「가정 배치」 재료는 세션 라벨의 판정(`EquipmentSession.layout_differs`)이라 그리는 동안
    저장소를 부르지 않는다."""
    if unsaved:
        return ":orange-badge[미저장 변경]"
    if session.scenario is None:
        return ""
    if session.unmerged:
        return f":red-badge[{UNMERGED_STATUS}]"
    if session.is_official_pair and session.release_no is not None:
        return f":green-badge[공식 v{session.release_no}]"
    if session.stale and session.latest_revision_no is not None:
        return f":orange-badge[최신 r{session.latest_revision_no} 있음]"
    if session.layout_differs:
        return f":violet-badge[{LAYOUT_BADGE}]"
    return ":gray-badge[저장된 리비전]"


def render_equipment_scenario_row(
    session: EquipmentSession, *, locked_reason: str | None = None
) -> None:
    """패널의 설비 시나리오 줄을 칸에 그린다(칸이 없는 회차는 그리지 않는다). **세션만 읽는다.**

    `locked_reason` 을 주면 팝업 없는 잠근 꼴이다 — 값 칸이 꺼지고 값 칸 끝에 「(고정)」 이 붙는다.
    까닭이 「(고정)」 그 자체가 아니면(공정 Capa 상세 HOME 방문 — `HOME_VISIT_LOCK_REASON`) 그 글은
    줄 아래 한 줄로 선다(값 칸은 한 줄 말줄임이고 꺼진 단추라 풍선이 없다). 머리 띠 꼬리는 잠근
    꼴에서도 세션 라벨 그대로다(「(고정)」 을 붙이지 않는다).
    """
    slot = equipment_scenario_slot()
    if slot is None:
        return
    flash = st.session_state.pop(FLASH_KEY, None)
    unsaved = has_unsaved_equipment_edits() and locked_reason is None
    # 머리 띠 아래 줄 끝의 설비 시나리오 꼬리 — 이 회차 목록으로 정해 같은 회차에 맞춘다.
    refresh_equipment_header(equipment_header_suffix(session.label(), unsaved=unsaved))
    value = equipment_field_label(session)
    if locked_reason is not None:
        value = f"{value} {FIXED_LOCK_REASON}"
    with slot.container():
        condition_field(
            EQUIPMENT_SCENARIO_FIELD_LABEL,
            value,
            slug="equipment_scenario",
            key=EQUIPMENT_SCENARIO_FIELD_KEY,
            icon=EQUIPMENT_SCENARIO_FIELD_ICON,
            status=equipment_status_badge(session, unsaved=unsaved),
            pending=unsaved,
            disabled=locked_reason is not None or session.scenario is None,
            on_click=open_equipment_scenario_dialog,
        )
        with st.container():
            if locked_reason is not None and locked_reason != FIXED_LOCK_REASON:
                st.caption(f":material/lock: {locked_reason}")
            # 저장 결과 알림(`save_result_message`)·세션 이동 알림은 날 설비 시나리오 이름을 두 번
            # 싣기도 한다(「10~12월 증설」 r2. 「10~12월 증설」의 가정 배치…) — 물결표가 지움선 짝이
            # 되지 않게 막는다(설비 마스터 탭 결과 알림과 같다).
            if isinstance(flash, str):
                st.success(markdown_safe_tildes(flash))
            if session.notice:
                st.warning(markdown_safe_tildes(session.notice), icon=":material/sync_problem:")


def open_equipment_scenario_dialog() -> None:
    """값 칸 콜백 — 다른 팝업 칸을 비우고 초안을 세션 값으로 적고 팝업을 연다. 미저장 편집이 있으면
    저장 구획으로 연다(그 편집을 남기려는 사람이 먼저 할 일이 저장이다). 마지막 줄에서 팝업 호스트만
    다시 돌린다."""
    forget_page_dialogs()
    selection = current_selection()
    if selection is None:
        st.session_state.pop(DIALOG_SCENARIO_KEY, None)
    else:
        st.session_state[DIALOG_SCENARIO_KEY] = selection[0]
    # 리비전은 고른 시나리오의 **최신**이 기본이다 — 낡은 세션이 팝업을 열면 곧바로 최신을 불러온다.
    st.session_state.pop(DIALOG_REVISION_KEY, None)
    st.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = (
        SAVE_MODE if has_unsaved_equipment_edits() else LOAD_MODE
    )
    st.session_state[EQUIPMENT_SCENARIO_DIALOG_KEY] = True
    rerun_fragment_if_alone(CONDITION_DIALOG_FRAGMENT_KEY, EQUIPMENT_SCENARIO_FIELD_KEY)


def close_equipment_scenario_dialog() -> None:
    st.session_state.pop(EQUIPMENT_SCENARIO_DIALOG_KEY, None)


def equipment_scenario_dialog_is_open() -> bool:
    return EQUIPMENT_SCENARIO_DIALOG_KEY in st.session_state


@st.dialog(
    EQUIPMENT_SCENARIO_DIALOG_TITLE,
    width="medium",
    icon=EQUIPMENT_SCENARIO_FIELD_ICON,
    on_dismiss=close_equipment_scenario_dialog,
)
def show_equipment_scenario_dialog(page_file: str | None) -> None:
    """팝업 껍데기. 열림 키가 있는 동안 `app.py` 의 호스트 프래그먼트가 매 회차 부른다."""
    render_equipment_scenario_dialog_body(page_file=page_file)


@keeps_app_run_open
def render_equipment_scenario_dialog_body(
    database_path: Path | None = None, *, page_file: str | None
) -> None:
    """팝업 본문. `database_path` 를 주지 않으면 **부를 때의** `settings.EQUIPMENT_DUCKDB_PATH`.

    팝업 안 조작은 `app.py` 의 실행 핀 밖에서 도는 프래그먼트라 핀을 여기서 다시 잡는다.
    """
    resolved = (
        settings.EQUIPMENT_DUCKDB_PATH if database_path is None else database_path
    ).resolve()
    with pinned_connections(resolved):
        try:
            session = resolve_equipment_session(str(resolved))
        except BOOTSTRAP_ERRORS as exc:
            st.error(
                "설비 시나리오를 읽지 못했습니다: "
                + bootstrap_error_message(exc, database_paths=(resolved,))
            )
            return
        _render_dialog_body(str(resolved), session, can_save=page_file in SAVE_PAGES)


def _render_dialog_body(database_path: str, session: EquipmentSession, *, can_save: bool) -> None:
    unsaved = has_unsaved_equipment_edits()
    badge = equipment_status_badge(session, unsaved=unsaved)
    if session.scenario is None:
        st.info("설비 시나리오가 없습니다.")
        return
    st.caption(f"올라와 있음 · {equipment_value_label(session)}" + (f" {badge}" if badge else ""))
    modes = [LOAD_MODE, SAVE_MODE] if can_save else [LOAD_MODE]
    if st.session_state.get(EQUIPMENT_SCENARIO_DIALOG_MODE_KEY) not in modes:
        st.session_state[EQUIPMENT_SCENARIO_DIALOG_MODE_KEY] = LOAD_MODE
    mode = (
        st.segmented_control(
            "구획",
            options=modes,
            required=True,
            key=EQUIPMENT_SCENARIO_DIALOG_MODE_KEY,
            label_visibility="collapsed",
        )
        if len(modes) > 1
        else LOAD_MODE
    )
    if mode == SAVE_MODE:
        _render_save(database_path, session)
        return
    _render_load(database_path, session, unsaved=unsaved)


def _render_load(database_path: str, session: EquipmentSession, *, unsaved: bool) -> None:
    """불러오기 구획 — 시나리오 → 리비전 라디오(최신 기본, 공식 발행에 「공식 vN」) → 버리기
    확인."""
    scenario_by_id = {item.equipment_scenario_id: item for item in session.catalog.scenarios}
    selected_scenario = prune_choice(
        DIALOG_SCENARIO_KEY,
        list(scenario_by_id),
        default=session.scenario_id or next(iter(scenario_by_id)),
    )
    try:
        revisions = load_equipment_schedule_revisions(database_path, selected_scenario)
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            markdown_safe_tildes(f"리비전 목록을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        )
        return
    revision_by_id = {item.schedule_revision_id: item for item in revisions}
    if revision_by_id:
        preferred = scenario_by_id[selected_scenario].latest_schedule_revision_id
        prune_choice(
            DIALOG_REVISION_KEY,
            list(revision_by_id),
            default=preferred
            if preferred is not None and preferred in revision_by_id
            else next(iter(revision_by_id)),
        )
    # Space 층 사용 편집 초안은 공식 설비 시나리오에서만 산다(Q3) — 가정 시나리오를 불러오면 그
    # 초안을 버린다(불러온 회차에 팝업이 토글·초안을 걷고, Space 는 편집을 잠근다). 그때도 「변경을
    # 버리고 불러오기」 를 묻는다(설계 9장).
    floor_draft = floor_state_draft_pending() and selected_scenario != session.official_scenario_id
    discard = True
    if unsaved or floor_draft:
        discard = st.checkbox("변경을 버리고 불러오기", key=DISCARD_KEY)
    if floor_draft:
        st.caption(FLOOR_DRAFT_DISCARD_NOTE)
    load_clicked = st.button(
        "불러오기",
        icon=":material/download:",
        type="primary",
        disabled=not discard or not revision_by_id,
        key=LOAD_BUTTON_KEY,
    )
    st.selectbox(
        "설비 시나리오",
        options=list(scenario_by_id),
        format_func=lambda value: scenario_by_id[value].scenario_name,
        key=DIALOG_SCENARIO_KEY,
    )
    if not revision_by_id:
        st.info("이 설비 시나리오에 저장된 리비전이 없습니다.")
    else:
        options = list(revision_by_id)
        release = session.catalog.latest_release
        st.radio(
            "리비전",
            options=options,
            format_func=lambda value: literal_markdown(
                schedule_revision_title(revision_by_id[value])
            ),
            captions=[
                _revision_caption(
                    revision_by_id[value],
                    official_id=release.schedule_revision_id if release else None,
                    official_no=release.release_no if release else None,
                    active_id=session.schedule_revision_id,
                )
                for value in options
            ],
            key=DIALOG_REVISION_KEY,
        )
    if load_clicked:
        failure = select_equipment_scenario(
            database_path,
            str(st.session_state[DIALOG_SCENARIO_KEY]),
            str(st.session_state[DIALOG_REVISION_KEY]),
            discard=discard,
        )
        if failure is not None:
            st.error(markdown_safe_tildes(failure))
            return
        if selected_scenario != session.official_scenario_id:
            # 묻고 버린 층 사용 초안은 여기서 버린다 — Space 가 잠그며 버리기를 기다리면 다음
            # 회차 `app.py` 의 탭 점·떠나기 확인이 버린 초안을 한 회차 더 센다(E2E).
            discard_floor_state_draft()
        chosen = revision_by_id[str(st.session_state[DIALOG_REVISION_KEY])]
        name = scenario_by_id[str(st.session_state[DIALOG_SCENARIO_KEY])].scenario_name
        st.session_state[FLASH_KEY] = loaded_revision_message(name, chosen.revision_no)
        close_equipment_scenario_dialog()
        st.rerun()


def _revision_caption(
    revision: EquipmentScheduleRevisionSummary,
    *,
    official_id: str | None,
    official_no: int | None,
    active_id: str | None,
) -> str:
    """리비전 선택지 아래 한 줄 — 저장 시각 · 저장자 · 공식 · 올라와 있음 · 메모."""
    parts = [f"{revision.created_at:%y.%m.%d %H:%M}"]
    if revision.saved_by:
        parts.append(literal_markdown(revision.saved_by))
    if official_no is not None and revision.schedule_revision_id == official_id:
        parts.append(f"공식 v{official_no}")
    if revision.schedule_revision_id == active_id:
        parts.append("올라와 있음")
    note = (revision.note or "").strip().replace("\n", " ")
    if note:
        shown = note if len(note) <= _NOTE_PREVIEW_LIMIT else note[:_NOTE_PREVIEW_LIMIT] + "…"
        parts.append(literal_markdown(shown))
    return " · ".join(parts)


def save_candidate_counts(buffer: Frames, saved_master: object) -> SaveCandidateCounts:
    """팝업이 미리 적는 함께 넣기 후보 수 — 저장본에 없던 호기(이름 바꿈은 이은 호기), 새 비가동.

    비가동은 저장본 사본에 없던 (설비명, 유형, 시작일) 수다. 저장소의 「고침이 아닌 새 비가동」
    판정(같은 묶음에 지운 행 없음)보다 넓게 셀 수 있다 — 실제로 퍼진 목록은 결과 알림이 적는다.
    """
    renames: Mapping[str, str] = pending_unit_renames().units
    saved_names: set[str] = set()
    if isinstance(saved_master, pd.DataFrame) and EQUIPMENT_ID_COLUMN in saved_master.columns:
        saved_names = {str(name) for name in saved_master[EQUIPMENT_ID_COLUMN].dropna()}
    saved_downtime = _downtime_keys(st.session_state.get(DOWNTIME_DRAFT_KEY))
    names = buffer[1][EQUIPMENT_ID_COLUMN].dropna().astype(str)
    new_units = sum(1 for name in names if renames.get(name, name) not in saved_names)
    new_downtime = len(_downtime_keys(buffer[2]) - saved_downtime)
    return SaveCandidateCounts(new_units=new_units, new_downtime=new_downtime)


def _downtime_keys(frame: object) -> set[tuple[str, str, str]]:
    """비가동 표의 (설비명, 유형, 시작일 `YYYY-MM-DD`) 모음. 표가 아니거나 비면 빈 모음."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return set()
    starts = pd.to_datetime(frame["시작일"], errors="coerce").dt.strftime("%Y-%m-%d")
    return {
        (str(name), str(kind), str(start))
        for name, kind, start in zip(
            frame[EQUIPMENT_ID_COLUMN], frame["비가동유형"], starts, strict=True
        )
    }


def stale_save_warning(revision_no: int | None, latest_revision_no: int | None) -> str:
    """팝업 「저장」 구획의 낡은 리비전 경고 — 번호 뒤 조사는 끝소리로 고른다."""
    return (
        f"지금 보는 {with_topic_particle(f'r{revision_no}')} 최신(r{latest_revision_no})이 "
        "아니라 일정이 바뀐 저장은 거부됩니다 — 공통 칸만 저장됩니다."
    )


def loaded_revision_message(scenario_name: str, revision_no: int) -> str:
    """팝업 「불러오기」 뒤 알림 — 번호 뒤 조사는 끝소리로 고른다."""
    revision = with_object_particle(f"r{revision_no}")
    return f"설비 시나리오 「{literal_markdown(scenario_name)}」 {revision} 불러왔습니다."


def _render_save(database_path: str, session: EquipmentSession) -> None:
    """저장 구획 — 지금 편집본을 이 설비 시나리오에(바뀐 쪽만). 작은 편집표(기존 보유대수·비가동
    일정)에서 아직 「편집본에 적용」 하지 않은 편집은 편집본에 없어 저장되지 않는다."""
    buffer = st.session_state.get(BUFFER_KEY)
    basis = session.save_basis()
    if not isinstance(buffer, tuple) or basis is None:
        st.info("저장할 설비 편집본이 없습니다.")
        return
    has_changes = has_unsaved_equipment_edits() or pending_fab_layout() is not None
    st.caption(
        f"「{literal_markdown(basis.scenario_name)}」 에 저장합니다 — 공통 칸은 공통 대장, 일정·"
        "시나리오 메모·비가동은 이 설비 시나리오로, 바뀐 쪽만 새 리비전이 됩니다. "
        f"{UNAPPLIED_SMALL_EDITS_NOTE}"
    )
    if basis.stale:
        st.warning(
            stale_save_warning(basis.revision_no, basis.latest_revision_no),
            icon=":material/lock_clock:",
        )
        # 낡기 전에 고친 일정 칸·지운 호기가 있으면 공통 칸까지 거부된다 — 저장 전에 그 칸과 고칠
        # 길을 알린다(누르면 같은 글로 거부한다 — `save_equipment_buffer`).
        refusal = stale_save_refusal(buffer, basis)
        if refusal is not None:
            st.warning(markdown_safe_tildes(refusal), icon=":material/block:")
    if not has_changes:
        st.caption("저장할 변경이 없습니다.")
    note = st.text_input("변경 메모", key=save_note_key(), placeholder="예: 셋업 실무 일정 반영")
    fields = render_equipment_save_fields(
        SAVE_FIELDS_PREFIX,
        counts=save_candidate_counts(buffer, st.session_state.get(EQUIPMENT_DRAFT_KEY)),
        release_exists=basis.release_no > 0,
    )
    with st.container():
        # 「새 호기」 칸에서 넣은 호기는 그 칸의 체크가 위 체크보다 이긴다(D8).
        line = new_unit_choice_line(buffer, assumption=not basis.official_scenario)
        if line is not None:
            st.caption(line)
    clicked = st.button(
        "설비 데이터 저장",
        icon=":material/save:",
        type="primary",
        disabled=not has_changes,
        key=SAVE_BUTTON_KEY,
    )
    if not clicked:
        return
    try:
        message = save_equipment_buffer(
            get_equipment_repository(database_path),
            buffer,
            note if isinstance(note, str) else "",
            basis=basis,
            fields=fields,
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            markdown_safe_tildes(
                "저장하지 못했습니다: "
                + bootstrap_error_message(exc, database_paths=(Path(database_path),))
            )
        )
        return
    st.session_state[SAVE_NOTE_GENERATION_KEY] = _note_generation() + 1
    st.session_state[FLASH_KEY] = message
    close_equipment_scenario_dialog()
    st.rerun()


def _note_generation() -> int:
    value = st.session_state.get(SAVE_NOTE_GENERATION_KEY, 0)
    return value if isinstance(value, int) else 0


def save_note_key() -> str:
    """팝업 저장 구획 메모 칸의 지금 key(첫 세대는 바탕 key 그대로)."""
    generation = _note_generation()
    return SAVE_NOTE_KEY if generation == 0 else f"{SAVE_NOTE_KEY}__g{generation}"
