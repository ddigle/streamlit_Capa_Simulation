# Purpose: 시나리오 관리 「설비 시나리오」 구획의 표와 불러오기·되돌리기·복제·이름·발행을 그린다.

"""시나리오 관리 「설비 시나리오」 구획(E8 — 1단계 몫, 설계 6-2, E7 리비전 도구).

자리는 시나리오 관리 화면 「시나리오 관리」 탭 맨 위 「관리할 시나리오」 전환의 「설비 시나리오」
쪽이다(2026-10-24 사용자 결정 — 가용설비 현황 두 탭 개편. 그 전에는 가용설비 현황의 탭이었다). 그
화면에는 사이드바 설비 시나리오 줄이 서지 않아 구획 머리에 「이 세션: …」 한 줄과 세션 알림을 그린다
(`render_equipment_scenario_section` — 탭이 숨은 회차의 이동 알림만 화면이 넘긴 탭 묶음 위
자리). 다른 설비 화면 맨 위 옛 배포 흔적 경고의 「시나리오 관리에서 이어 쓰기」 는 이 구획으로
옮긴다(`open_equipment_scenario_management`).

- **시나리오 표**: 이름·상태(공식 vN / 활성)·최신 rN·리비전 수·저장된 배치 차이(최신의 원시 행 —
  설비 0031)·올라와 있음. 고른 시나리오에 「시나리오 이름 바꾸기」 와, 가정 시나리오 최신에 배치
  차이가 있으면 「배치 차이 모두 지우기」(차이만 비운 새 리비전 — 설계 6-6). 옛 판(0031 을 모르는
  배포)이 저장해 가정 배치가 빠진 리비전이 있으면 그 시나리오 이름과 수를 한 줄로(설계 14장).
- **리비전 표**: 고른 시나리오의 일정 리비전(r·리비전명·저장시각·저장자·출처·공통 rN·호기 행·비가동
  행·배치·공식·메모). 「배치」 는 저장된 배치 차이 행 수, 옛 판 흔적은 「옛 판 저장 — rN 배치 빠짐」
  이고 표 위에 되살리는 길(그 리비전으로 되돌리기)을 적는다.
- **고른 리비전의 작업 다섯**: 「이 리비전 불러오기」(세션을 옮김 — 미저장이면 「변경을 버리고
  불러오기」), 「이 리비전으로 되돌리기」(E7 — 그 일정으로 같은 시나리오에 새 리비전, 바뀌는 호기
  수와 「일정 없음」 이 되는 호기를 보이고 확인 체크 뒤에), 「여기서 새 시나리오」(E7 — 그 리비전을
  r1 로 복제. 만들기는 복제로만), 「리비전명」(E7 — 이름표만 고침), 「공식으로 발행」(지금 공식 → 새
  공식을 나란히, 최신이 아니면 그 사실도. 배치 차이가 있으면 발행 쓰기와 같은 판정을 미리 읽어 막힘
  까닭과 함께 단추를 끄고, 공식과 같아진 차이만 남았으면 정리 리비전으로 발행한다고 적는다 — 설계
  6-5). 되돌리기 확인 글은 되살리는 가정 배치에서 그때와 자리가 다른 손대지 않은 호기 수도 적는다.
- **옛 배포 흔적**이 있을 때만 「이대로 이어 쓰기」(설비 저장 막기를 푼다 — 백업 복원 대신). 확인
  체크(빠지는 호기 수)를 켜야 단추가 서고, 옛 배포 리비전이 일정과 합쳐지지 않으면 단추 대신 백업
  복원 안내만 선다.

구획 본문(`render_equipment_scenario_management`)이 받는 것은 DB 경로와 그 회차 설비 시나리오
세션뿐이다. 목록·리비전은 설비 시나리오 목록 캐시(세대·stat·TTL), 되돌리기 확인 재료는 불변 리비전
id 키 캐시에서 받는다 — 이 구획을 그리는 회차에만 읽는다(「시뮬레이션 시나리오」 쪽을 고른 회차에는
설비 DB 를 열지 않는다). 쓰기(복제·이름·리비전명·되돌리기·발행·이어 쓰기)는 저장소가 하고 그 뒤
`clear_equipment_scenario_cache()` 를 부른다(저장소는 캐시 경계를 모른다). 2단계(보관·삭제·순서·공통
이력·비교)는 짓지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.errors import StreamlitPageNotFoundError

# 테스트가 `settings.EQUIPMENT_DUCKDB_PATH` 를 갈아끼운다 — 부를 때 모듈에서 찾는다.
import capa_simulation.settings as settings
from capa_simulation.components.equipment_data_workspace import (
    ORIGIN_WORDS,
    has_unsaved_equipment_edits,
    schedule_revision_title,
)
from capa_simulation.components.equipment_save_fields import (
    DEFAULT_PUBLISH_OFFICIAL,
    PUBLISH_OFFICIAL_LABEL,
    SAVED_BY_LABEL,
)
from capa_simulation.components.literal_markdown import literal_markdown, markdown_safe_tildes
from capa_simulation.components.tab_state import remember_open_tab
from capa_simulation.equipment_scenario_activation import (
    EquipmentSession,
    resolve_equipment_session,
    select_equipment_scenario,
)
from capa_simulation.navigation import SCENARIO_MANAGEMENT
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    prune_choice,
    render_schema_ahead_warning,
)
from capa_simulation.page_tabs_state import refused_at_tab_limit
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_scenario_cache,
    clear_equipment_snapshot_cache,
    get_equipment_repository,
    latest_equipment_revision_id,
    load_equipment_revision_summaries,
    load_equipment_schedule_revisions,
    load_layout_publish_preview,
    load_legacy_trace_review,
    load_schedule_restore_preview,
)
from capa_simulation.persistence.equipment_repository import (
    SCHEDULE_REVISION_NAME_MAX_CHARS,
    EquipmentLayoutPublishBlocked,
    EquipmentLayoutRoleChanged,
    EquipmentReleaseMoved,
    EquipmentRevisionConflict,
    EquipmentScenarioNameMoved,
    EquipmentScenarioSummary,
    EquipmentScheduleRevisionNameMoved,
    EquipmentScheduleRevisionSummary,
    LayoutPublishPreview,
    LegacyTraceReview,
    ScheduleRestoreResult,
    legacy_trace_message,
)
from capa_simulation.services.equipment_scenario import (
    ScheduleRestorePreview,
    restore_writes_nothing,
)
from capa_simulation.services.korean_particle import (
    object_particle,
    topic_particle,
    with_direction_particle,
    with_object_particle,
    with_topic_particle,
)
from capa_simulation.services.layout_overlay import (
    EMPTY_LAYOUT_DIGEST,
    layout_publish_blocked_words,
)

__all__ = [
    "EQUIPMENT_KIND",
    "SCENARIO_KINDS",
    "SCENARIO_KIND_KEY",
    "SCENARIO_MANAGEMENT_TAB",
    "SCENARIO_MANAGEMENT_TABS_KEY",
    "SIMULATION_KIND",
    "open_equipment_scenario_management",
    "render_equipment_scenario_management",
    "render_equipment_scenario_section",
]

# 시나리오 관리 화면의 탭 묶음(`stateful_tabs`) key 와 첫 탭 라벨 — 다른 화면에서 이 구획으로 보낼
# 때 그 탭 기억 칸을 적는다. 화면(`app_pages/scenario_management.py`)도 이 이름을 읽는다.
SCENARIO_MANAGEMENT_TABS_KEY = "scenario_management_tabs"
SCENARIO_MANAGEMENT_TAB = ":material/database: 시나리오 관리"
# 「시나리오 관리」 탭 맨 위 「관리할 시나리오」 전환(2026-10-24 사용자 결정 D4). 보기 조건이라
# `persist_state="session"` 이고, 다른 화면(옛 배포 흔적 경고의 단추)이 값을 적으므로 `default=` 를
# 주지 않고 위젯 앞에서 칸이 없을 때만 심는다(AGENTS 9장).
SCENARIO_KIND_KEY = "scenario_management_kind_v1"
SIMULATION_KIND = "시뮬레이션 시나리오"
EQUIPMENT_KIND = "설비 시나리오"
SCENARIO_KINDS = (SIMULATION_KIND, EQUIPMENT_KIND)
# 「시나리오 관리에서 이어 쓰기」 단추(설비 화면 맨 위 옛 배포 흔적 경고 옆).
LEGACY_TRACE_GOTO_KEY = "equipment_legacy_trace_goto_v1"

SCENARIO_KEY = "equipment_scenario_manage_scenario_v1"
REVISION_KEY = "equipment_scenario_manage_revision_v1"
DISCARD_KEY = "equipment_scenario_manage_discard_v1"
LOAD_BUTTON_KEY = "equipment_scenario_manage_load_v1"
# 「여기서 새 시나리오」 — 고른 리비전을 r1 로 복제한다.
CLONE_NAME_KEY = "equipment_scenario_manage_clone_name_v1"
CLONE_BY_KEY = "equipment_scenario_manage_clone_by_v1"
CLONE_BUTTON_KEY = "equipment_scenario_manage_clone_v1"
RENAME_KEY = "equipment_scenario_manage_rename_v1"
RENAME_BUTTON_KEY = "equipment_scenario_manage_rename_button_v1"
# 「리비전명」 — 고른 리비전의 이름표.
REVISION_NAME_KEY = "equipment_scenario_manage_revision_name_v1"
REVISION_NAME_BUTTON_KEY = "equipment_scenario_manage_revision_name_button_v1"
# 「이 리비전으로 되돌리기」. 입력 칸 key 는 고른 리비전을, 확인 체크 key 는 확인 글을 정하는 값
# 다섯(시나리오·고른 리비전·그 시나리오 최신·공통 최신·공식 발행 번호)을 덧붙인다 — 다른 리비전을
# 고르거나 확인 뒤 그 값이 바뀌면 체크가 풀린 새 칸으로 선다(본 적 없는 글로 되돌리지 않게).
RESTORE_NAME_KEY = "equipment_scenario_manage_restore_name_v1"
RESTORE_NOTE_KEY = "equipment_scenario_manage_restore_note_v1"
RESTORE_BY_KEY = "equipment_scenario_manage_restore_by_v1"
RESTORE_PUBLISH_KEY = "equipment_scenario_manage_restore_publish_v1"
RESTORE_CONFIRM_KEY = "equipment_scenario_manage_restore_confirm_v1"
RESTORE_BUTTON_KEY = "equipment_scenario_manage_restore_v1"
# 확인 체크가 켜진 회차의 그 값 다섯 — 다음 회차에 값이 바뀌어 체크가 풀렸으면 그 까닭을 알린다
# (Streamlit 1.63 은 잠가 그린 단추의 클릭을 서버에서 버려 누른 회차에 코드가 알 수 없다).
RESTORE_AGREED_KEY = "equipment_scenario_manage_restore_agreed_v1"
PUBLISH_BY_KEY = "equipment_scenario_manage_publish_by_v1"
PUBLISH_NOTE_KEY = "equipment_scenario_manage_publish_note_v1"
PUBLISH_BUTTON_KEY = "equipment_scenario_manage_publish_v1"
# 「공식으로 발행」 확인 글을 그린 회차의 {고른 리비전, 지금 공식 번호, 그 시나리오 최신}
# (`publish_seen_token`). 단추를 누른 회차에는 확인 글이 이미 새 목록으로 다시 그려지므로, 누르기
# **전** 회차에 본 값을 여기 남겨 누른 회차의 값과 견준다 — 그 사이 남이 발행했으면 본 적 없는 새
# 번호(v5 → v6)로, 남이 새 리비전을 저장했으면 본 적 없는 「최신이 아닙니다」 로 말없이 발행하지
# 않는다.
PUBLISH_SEEN_KEY = "equipment_scenario_manage_publish_seen_v1"
# 「배치 차이 모두 지우기」(설비 시나리오 2단계 S4 — 가정 시나리오 최신에 배치 차이가 있을 때만).
CLEAR_LAYOUT_BY_KEY = "equipment_scenario_manage_clear_layout_by_v1"
CLEAR_LAYOUT_NOTE_KEY = "equipment_scenario_manage_clear_layout_note_v1"
CLEAR_LAYOUT_CONFIRM_KEY = "equipment_scenario_manage_clear_layout_confirm_v1"
CLEAR_LAYOUT_BUTTON_KEY = "equipment_scenario_manage_clear_layout_v1"
CONTINUE_BUTTON_KEY = "equipment_scenario_manage_continue_v1"
# 「이대로 이어 쓰기」 확인 체크. key 꼬리에 체크 글을 정하는 값 셋(흔적 수·옛 배포 리비전
# 번호·빠지는 호기 수)을 붙인다 — 그 값이 바뀌면 체크가 풀린 새 칸으로 서서 본 적 없는 글로 이어
# 쓰지 않는다.
CONTINUE_CONFIRM_KEY = "equipment_scenario_manage_continue_confirm_v1"
# 이 구획 작업 알림 — 다음 회차에 한 번, 구획 맨 위.
FLASH_KEY = "equipment_scenario_manage_flash_v1"
# 그 사이 남의 저장·발행·이름 변경으로 거절한 작업 알림 — 다음 회차에 한 번, 구획 맨 위(확인
# 체크·입력 칸을 새로 세운 뒤라 옛 확인으로 다시 누르지 않게).
REFUSED_KEY = "equipment_scenario_manage_refused_v1"
# 되돌리기가 만든 리비전 — 다음 회차 리비전 상자를 그리기 전에 그 리비전으로 옮긴다(위젯을 그린
# 뒤에는 그 칸을 고칠 수 없다).
PENDING_REVISION_KEY = "equipment_scenario_manage_pending_revision_v1"
# 입력 칸 세대 — 쓰기에 성공한 회차에 올라 다음 회차에 빈 칸으로 선다(옛 값을 되보내지 않게).
GENERATION_KEY = "equipment_scenario_manage_generation_v1"
# 구획의 팝오버 일곱(시나리오 줄 둘·리비전 줄 다섯). key 꼬리는 팝오버 세대
# (`POPOVER_GENERATION_KEY`)다 — 한 번뿐인 알림(작업 알림·거절 알림·세션 이동 알림)을 그리는
# 회차에만 올라 그 회차에 팝오버가 닫힌 채 다시 선다(작업을 마친 팝오버를 닫는다). 그 밖의 회차에는
# key 도 자리도 그대로라 열린 팝오버가 확인 체크·글자 칸·Enter 로 닫히지 않는다 — 알림은 늘 서 있는
# 칸 안에 그려, 빠지는 회차에 팝오버 줄이 한 칸 당겨져 다시 서지 않게 한다(9장 「key 가 있어도
# 자리는 고정한다」).
RENAME_POPOVER_KEY = "equipment_scenario_manage_rename_popover_v1"
CLEAR_LAYOUT_POPOVER_KEY = "equipment_scenario_manage_clear_layout_popover_v1"
LOAD_POPOVER_KEY = "equipment_scenario_manage_load_popover_v1"
RESTORE_POPOVER_KEY = "equipment_scenario_manage_restore_popover_v1"
CLONE_POPOVER_KEY = "equipment_scenario_manage_clone_popover_v1"
REVISION_NAME_POPOVER_KEY = "equipment_scenario_manage_revision_name_popover_v1"
PUBLISH_POPOVER_KEY = "equipment_scenario_manage_publish_popover_v1"
POPOVER_GENERATION_KEY = "equipment_scenario_manage_popover_generation_v1"
# 리비전 표 위 띄움(px, `st.space`) — 표 도구 막대가 바로 위 줄 팝오버 단추에 닿지 않을 만큼(그리는
# 자리의 설명).
REVISION_TABLE_TOOLBAR_CLEARANCE = 24

# 리비전명 칸 글자 수 한도 — 저장소도 같은 한도로 거절한다.
REVISION_NAME_MAX_CHARS = SCHEDULE_REVISION_NAME_MAX_CHARS


def _generation() -> int:
    value = st.session_state.get(GENERATION_KEY, 0)
    return value if isinstance(value, int) else 0


def _keyed(base: str) -> str:
    generation = _generation()
    return base if generation == 0 else f"{base}__g{generation}"


def _popover_generation() -> int:
    value = st.session_state.get(POPOVER_GENERATION_KEY, 0)
    return value if isinstance(value, int) else 0


def _popover_key(base: str) -> str:
    """팝오버 key — 팝오버 세대 꼬리를 늘 붙인다(`POPOVER_GENERATION_KEY`)."""
    return f"{base}__p{_popover_generation()}"


def _written(message: str) -> None:
    """쓰기 뒤 — 목록 캐시를 비우고 알림을 남기고 입력 칸을 새로 세운 뒤 다시 돈다."""
    clear_equipment_scenario_cache()
    st.session_state[FLASH_KEY] = message
    st.session_state[GENERATION_KEY] = _generation() + 1
    st.session_state.pop(RESTORE_AGREED_KEY, None)
    st.rerun()


def _refused(message: str) -> None:
    """그 사이 남의 쓰기로 거절했을 때 — 공통 최신·목록을 다시 읽게 비우고, 확인 체크·입력 칸을 새로
    세운 뒤(옛 확인으로 다시 누르지 않게) 다음 회차 맨 위에 까닭을 알린다."""
    clear_equipment_snapshot_cache()
    st.session_state[REFUSED_KEY] = message
    st.session_state[GENERATION_KEY] = _generation() + 1
    st.session_state.pop(RESTORE_AGREED_KEY, None)
    st.rerun()


def scenario_rows(session: EquipmentSession) -> pd.DataFrame:
    """시나리오 표 — 이름·상태·최신·리비전 수·저장된 배치 차이. 공식은 「공식 vN」, 그 밖은
    「활성」.

    「저장된 배치 차이」 는 최신 리비전에 **저장된** 차이 행 수(원시 — 「호기 3행·요소 1개」)다.
    목록 표에는 실효(지금 공식과 실제로 다른 것)를 셀 재료가 없어 원시만 적는다(설계 8-2·검토 F4) —
    공식과 같아진 행은 다음 저장·발행 때 정리된다."""
    official_id = session.catalog.official_scenario_id
    release_no = session.catalog.release_no
    return pd.DataFrame(
        [
            {
                "설비 시나리오": item.scenario_name,
                "상태": (
                    f"공식 v{release_no}"
                    if item.equipment_scenario_id == official_id and release_no is not None
                    else "활성"
                ),
                "최신": f"r{item.latest_revision_no}" if item.latest_revision_no else "",
                "리비전 수": item.revision_count,
                "저장된 배치 차이": stored_layout_words(*item.latest_layout_rows),
                "올라와 있음": "●" if item.equipment_scenario_id == session.scenario_id else "",
            }
            for item in session.catalog.scenarios
        ]
    )


def revision_rows(
    revisions: Sequence[EquipmentScheduleRevisionSummary],
    *,
    common_numbers: dict[str, int],
    official_id: str | None,
    official_no: int | None,
) -> pd.DataFrame:
    """리비전 표 — r·리비전명·저장시각·저장자·출처·공통 rN·호기 행·비가동 행·배치·공식·메모.

    「배치」 는 그 리비전에 저장된 배치 차이 행 수(원시)다. 옛 판(설비 0031 을 모르는 코드)이 저장해
    앞 리비전의 가정 배치가 빠진 리비전(옛 코드 흔적 — 설계 14장)은 「옛 판 저장 — rN 배치
    빠짐」."""
    traces = layout_trace_sources(revisions)
    return pd.DataFrame(
        [
            {
                "리비전": f"r{item.revision_no}",
                "리비전명": item.revision_name,
                "저장시각": item.created_at,
                "저장자": item.saved_by,
                "출처": ORIGIN_WORDS.get(item.origin, item.origin),
                "공통": (
                    f"r{common_numbers[item.common_revision_id]}"
                    if item.common_revision_id in common_numbers
                    else ""
                ),
                "호기행": item.unit_row_count,
                "비가동행": item.downtime_row_count,
                "배치": (
                    f"옛 판 저장 — r{traces[item.revision_no]} 배치 빠짐"
                    if item.revision_no in traces
                    else stored_layout_words(
                        item.layout_unit_count, item.layout_mark_count, item.layout_label_count
                    )
                ),
                "공식": (
                    f"v{official_no}"
                    if official_no is not None and item.schedule_revision_id == official_id
                    else ""
                ),
                "메모": item.note,
            }
            for item in revisions
        ]
    )


def stored_layout_words(units: int, marks: int, labels: int) -> str:
    """「호기 1행·요소 2개·이름표 1개」 — 저장된 배치 차이 행 수(0 인 것은 뺀다, 모두 0 이면 빈
    글)."""
    parts = [
        f"{word} {count:,}{unit}"
        for word, count, unit in (
            ("호기", units, "행"),
            ("요소", marks, "개"),
            ("이름표", labels, "개"),
        )
        if count
    ]
    return "·".join(parts)


def _has_layout(revision: EquipmentScheduleRevisionSummary) -> bool:
    return revision.layout_hash is not None and revision.layout_hash != EMPTY_LAYOUT_DIGEST


def layout_trace_sources(revisions: Sequence[EquipmentScheduleRevisionSummary]) -> dict[int, int]:
    """옛 코드 흔적 — 배치 차이가 있는 리비전보다 번호가 큰데 지문이 없는(설비 0031 을 모르는 옛
    판이 저장한) 리비전 번호 → 그 앞에서 가장 가까운 배치 차이가 있는 리비전 번호(설계 14장 — 목록
    셈 `layout_trace_count` 와 같은 규칙, 읽은 목록 안에서). 그 리비전으로 되돌리면(E7) 배치안이
    되살아난다."""
    ordered = sorted(revisions, key=lambda item: item.revision_no)
    result: dict[int, int] = {}
    source: int | None = None
    for revision in ordered:
        if _has_layout(revision):
            source = revision.revision_no
        elif revision.layout_hash is None and source is not None:
            result[revision.revision_no] = source
    return result


def layout_trace_sentence(
    scenario: EquipmentScenarioSummary, revisions: Sequence[EquipmentScheduleRevisionSummary]
) -> str | None:
    """고른 설비 시나리오의 옛 코드 흔적 경고 한 문장(없으면 None) — 가장 늦은 흔적과 그 앞
    배치안."""
    traces = layout_trace_sources(revisions)
    if not traces and not scenario.layout_trace_count:
        return None
    name = literal_markdown(scenario.scenario_name)
    if not traces:
        return (
            f"「{name}」 에 옛 판이 저장해 앞 리비전의 가정 배치가 빠진 리비전이 "
            f"{scenario.layout_trace_count:,}개 있습니다(아래 표보다 옛 리비전) — 빠지기 전 "
            "리비전으로 되돌리면(이 리비전으로 되돌리기) 되살아납니다."
        )
    latest = max(traces)
    source = f"r{traces[latest]}"
    more = (
        f" 옛 판이 저장한 리비전은 모두 {scenario.layout_trace_count:,}개입니다."
        if scenario.layout_trace_count > 1
        else ""
    )
    return (
        f"「{name}」 r{latest}{topic_particle(f'r{latest}')} 옛 판이 저장해 {source}의 가정 배치가 "
        f"빠졌습니다 — {with_direction_particle(source)} 되돌리기(이 리비전으로 되돌리기)로 "
        f"되살립니다.{more} 옛 판으로 저장하지 않게 런북 4-2 「되돌림」 을 보세요."
    )


def open_equipment_scenario_management() -> None:
    """시나리오 관리 「설비 시나리오」 구획으로 옮긴다 — 그 화면의 탭 기억 칸과 전환 칸만 적는다.

    위젯 콜백이 아니라 회차 본문에서 부른다(AGENTS 9장 — 콜백 안 `st.switch_page` 금지). 화면 탭
    상한에 걸리면 아무것도 적지 않는다(`refused_at_tab_limit`). 갈 곳이 없으면(내비게이션 없는 단독
    실행) 칸만 적고 옮기지 않는다.
    """
    if refused_at_tab_limit(SCENARIO_MANAGEMENT.path):
        return
    st.session_state[SCENARIO_KIND_KEY] = EQUIPMENT_KIND
    remember_open_tab(SCENARIO_MANAGEMENT_TABS_KEY, SCENARIO_MANAGEMENT_TAB)
    try:
        st.switch_page(SCENARIO_MANAGEMENT.path)
    except StreamlitPageNotFoundError:
        return


def render_legacy_trace_goto() -> None:
    """설비 화면 맨 위 옛 배포 흔적 경고 옆 「시나리오 관리에서 이어 쓰기」 단추."""
    if st.button(
        "시나리오 관리에서 이어 쓰기",
        icon=":material/arrow_forward:",
        key=LEGACY_TRACE_GOTO_KEY,
        type="tertiary",
    ):
        open_equipment_scenario_management()


def session_heading(session: EquipmentSession) -> str:
    """구획 머리 한 줄 — 「이 세션: 운영 일정 · r12 · 공식 v3」.

    이 화면에는 사이드바 설비 시나리오 줄이 서지 않아(D4) 세션이 든 쌍을 여기 적는다. 일정 없이 연
    세션(`unmerged`)이면 그 말을 적는다.
    """
    if session.scenario_name is None:
        return "이 세션: 설비 시나리오 없음"
    name = literal_markdown(session.scenario_name)
    if session.unmerged:
        return f"이 세션: {name} · 일정 없이 엶(옛 배포 흔적이 일정과 합쳐지지 않음)"
    parts = [name]
    if session.revision_no is not None:
        parts.append(f"r{session.revision_no}")
    if session.is_official_pair and session.release_no is not None:
        parts.append(f"공식 v{session.release_no}")
    elif session.stale and session.latest_revision_no is not None:
        parts.append(f"최신 r{session.latest_revision_no} 있음")
    return "이 세션: " + " · ".join(parts)


def render_equipment_scenario_section(*, notice_slot: DeltaGenerator | None = None) -> None:
    """시나리오 관리 「설비 시나리오」 구획 — 설비 DB 를 이 구획 안에서만 연다.

    설비 DB 를 읽지 못하면 그 까닭을 이 구획 안에서만 알린다(「시뮬레이션 시나리오」 쪽은 막지
    않는다). 옛 배포 흔적 경고는 구획 본문이 「이대로 이어 쓰기」 와 함께 그린다 — 머리에 따로
    세우지 않는다.

    `notice_slot` 은 이 구획이 든 탭이 숨은 회차에 화면이 넘기는 늘 보이는 자리(탭 묶음 위
    `st.empty`)다. 세션을 다른 리비전으로 옮겼다는 알림은 그 회차 한 번뿐이라(미저장 설비 편집을
    버렸다는 말이 든다) 숨은 패널에 그리면 보지 못한 채 사라진다 — 그 알림만 그 자리에 그린다. 일정
    없이 연 회차(`unmerged`)의 알림은 회차마다 다시 나오므로 구획 안 그대로다.
    """
    try:
        database_path = str(settings.EQUIPMENT_DUCKDB_PATH.resolve())
        repository = get_equipment_repository(database_path)
        session = resolve_equipment_session(database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            "설비 시나리오를 준비하지 못했습니다. "
            + bootstrap_error_message(exc, database_paths=(settings.EQUIPMENT_DUCKDB_PATH,))
        )
        return
    render_schema_ahead_warning(repository.schema_ahead)
    st.markdown(f"**{session_heading(session)}**")
    st.caption(
        "설비 시나리오 불러오기·저장은 설비 화면(가용설비 현황·필요 단축 일정·공정 Capa 상세) "
        "사이드바 설비 시나리오 줄에서도 합니다. 이 세션이 든 쌍은 그 화면들과 같습니다."
    )
    # 세션 이동 알림은 한 회차뿐이다 — 늘 서 있는 칸 안에 그려 빠지는 회차에 구획 본문(팝오버 줄)이
    # 한 칸 당겨지지 않게 한다(`POPOVER_GENERATION_KEY`).
    with st.container():
        if session.notice:
            if notice_slot is not None and not session.unmerged:
                notice_slot.warning(session.notice, icon=":material/sync_problem:")
            else:
                st.warning(session.notice, icon=":material/sync_problem:")
    render_equipment_scenario_management(database_path, session)


def render_equipment_scenario_management(database_path: str, session: EquipmentSession) -> None:
    """구획 본문. 「설비 시나리오」 쪽을 고른 회차에만 부른다 — 입력은 위젯이 세션에 지킨다.

    한 번뿐인 알림(작업 알림·거절 알림·세션 이동 알림)을 그리는 회차에 팝오버 세대를 올려 팝오버를
    닫힌 채 세우고, 알림·옛 배포 흔적·옛 판 흔적 줄은 생기거나 빠져도 뒤 형제의 자리가 그대로이게
    늘 서 있는 칸 안에 그린다(`POPOVER_GENERATION_KEY`).
    """
    flash = st.session_state.pop(FLASH_KEY, None)
    refused = st.session_state.pop(REFUSED_KEY, None)
    if (
        isinstance(flash, str)
        or isinstance(refused, str)
        or (bool(session.notice) and not session.unmerged)
    ):
        st.session_state[POPOVER_GENERATION_KEY] = _popover_generation() + 1
    with st.container():
        if isinstance(flash, str):
            st.success(flash)
        if isinstance(refused, str):
            st.error(markdown_safe_tildes(refused))
    with st.container():
        if session.legacy_trace_count:
            _render_legacy_trace(database_path, session.legacy_trace_count)
    scenarios = {item.equipment_scenario_id: item for item in session.catalog.scenarios}
    if not scenarios:
        st.info(
            "설비 시나리오가 없습니다. 가용설비 현황 「설비 마스터」 탭에서 첫 설비 데이터를 "
            "저장하면 「운영 일정」이 섭니다."
        )
        return
    st.caption(
        "공통 칸(호기 정보·실적·상태·Space 실물)은 모든 설비 시나리오가 함께 씁니다. 설비 "
        "시나리오는 일정 여섯·시나리오 메모·비가동만 따로 듭니다 — 만들기는 복제로만 합니다."
    )
    st.dataframe(scenario_rows(session), hide_index=True, width="stretch", placeholder="")
    traced = [item for item in session.catalog.scenarios if item.layout_trace_count]
    with st.container():
        if traced:
            st.caption(
                ":material/history: 옛 판(설비 0031 을 모르는 배포)이 저장해 가정 배치가 빠진 "
                "리비전이 있는 설비 시나리오 — "
                + ", ".join(
                    f"「{literal_markdown(item.scenario_name)}」 {item.layout_trace_count:,}개"
                    for item in traced
                )
                + ". 그 시나리오를 고르면 리비전 표 「배치」 칸이 빠진 자리를 가리킵니다."
            )
    default_scenario = (
        session.scenario_id if session.scenario_id in scenarios else next(iter(scenarios))
    )
    selected_id = prune_choice(SCENARIO_KEY, list(scenarios), default=default_scenario)
    with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
        st.selectbox(
            "설비 시나리오",
            options=list(scenarios),
            format_func=lambda value: scenarios[value].scenario_name,
            key=SCENARIO_KEY,
        )
        with st.popover(
            "시나리오 이름 바꾸기", icon=":material/edit:", key=_popover_key(RENAME_POPOVER_KEY)
        ):
            _render_rename(database_path, scenarios[selected_id])
        # 가정 설비 시나리오 최신에 배치 차이가 있을 때만(공식 시나리오에는 지울 것이 없다 — I2).
        if clearable_layout(session, scenarios[selected_id]):
            with st.popover(
                "배치 차이 모두 지우기",
                icon=":material/layers_clear:",
                key=_popover_key(CLEAR_LAYOUT_POPOVER_KEY),
            ):
                _render_clear_layout(database_path, session, scenarios[selected_id])
    scenario = scenarios[selected_id]
    try:
        revisions = load_equipment_schedule_revisions(database_path, selected_id)
        latest_common = latest_equipment_revision_id(database_path)
        common_numbers = {
            item.revision_id: item.revision_no
            for item in load_equipment_revision_summaries(database_path, latest_common)
        }
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            markdown_safe_tildes(f"리비전 목록을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        )
        return
    release = session.catalog.latest_release
    official_id = release.schedule_revision_id if release is not None else None
    official_no = release.release_no if release is not None else None
    if not revisions:
        st.info("이 설비 시나리오에 저장된 리비전이 없습니다.")
        return
    trace = layout_trace_sentence(scenario, revisions)
    with st.container():
        if trace is not None:
            st.warning(trace, icon=":material/history:")
    # 표 도구 막대(열 보기·내려받기·찾기·전체 화면)는 표 오른쪽 위에 떠 표 위로 솟는다 — 붙어 있으면
    # 바로 위 줄 맨 오른쪽 팝오버 단추(「시나리오 이름 바꾸기」·「배치 차이 모두 지우기」)를 덮어
    # 표에서 단추로 옮긴 누름을 가로챈다. 그 막대가 위 줄에 닿지 않을 만큼 띄운다.
    st.space(REVISION_TABLE_TOOLBAR_CLEARANCE)
    st.dataframe(
        revision_rows(
            revisions,
            common_numbers=common_numbers,
            official_id=official_id,
            official_no=official_no,
        ),
        hide_index=True,
        width="stretch",
        placeholder="",
        column_config={"저장시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")},
    )
    by_id = {item.schedule_revision_id: item for item in revisions}
    default_revision = (
        scenario.latest_schedule_revision_id
        if scenario.latest_schedule_revision_id in by_id
        else next(iter(by_id))
    )
    pending = st.session_state.pop(PENDING_REVISION_KEY, None)
    if isinstance(pending, str) and pending in by_id:
        st.session_state[REVISION_KEY] = pending
    chosen_id = prune_choice(REVISION_KEY, list(by_id), default=default_revision)
    st.selectbox(
        "리비전",
        options=list(by_id),
        format_func=lambda value: _revision_label(
            by_id[value], official_id=official_id, official_no=official_no
        ),
        key=REVISION_KEY,
    )
    chosen = by_id[chosen_id]
    with st.container(horizontal=True, gap="small"):
        with st.popover(
            "이 리비전 불러오기", icon=":material/download:", key=_popover_key(LOAD_POPOVER_KEY)
        ):
            _render_load(database_path, scenario, chosen)
        with st.popover(
            "이 리비전으로 되돌리기",
            icon=":material/history:",
            key=_popover_key(RESTORE_POPOVER_KEY),
        ):
            _render_restore(database_path, session, scenario, chosen)
        with st.popover(
            "여기서 새 시나리오", icon=":material/call_split:", key=_popover_key(CLONE_POPOVER_KEY)
        ):
            _render_branch(database_path, scenario, chosen)
        with st.popover(
            "리비전명", icon=":material/label:", key=_popover_key(REVISION_NAME_POPOVER_KEY)
        ):
            _render_revision_name(database_path, scenario, chosen)
        with st.popover(
            "공식으로 발행", icon=":material/verified:", key=_popover_key(PUBLISH_POPOVER_KEY)
        ):
            _render_publish(database_path, session, scenario, chosen)


def _revision_label(
    revision: EquipmentScheduleRevisionSummary, *, official_id: str | None, official_no: int | None
) -> str:
    parts = [schedule_revision_title(revision), f"{revision.created_at:%y.%m.%d %H:%M}"]
    if official_no is not None and revision.schedule_revision_id == official_id:
        parts.append(f"공식 v{official_no}")
    if revision.note:
        parts.append(revision.note.replace("\n", " ")[:40])
    return " · ".join(parts)


def _render_load(
    database_path: str,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> None:
    name = literal_markdown(scenario.scenario_name)
    title = f"r{revision.revision_no}"
    st.caption(f"「{name}」 {with_object_particle(title)} 이 세션의 설비 시나리오로 올립니다.")
    discard = True
    if has_unsaved_equipment_edits():
        discard = st.checkbox("변경을 버리고 불러오기", key=DISCARD_KEY)
    if st.button(
        "불러오기", type="primary", disabled=not discard, key=LOAD_BUTTON_KEY, width="stretch"
    ):
        failure = select_equipment_scenario(
            database_path,
            scenario.equipment_scenario_id,
            revision.schedule_revision_id,
            discard=discard,
        )
        if failure is not None:
            st.error(markdown_safe_tildes(failure))
            return
        st.session_state[FLASH_KEY] = (
            f"설비 시나리오 「{name}」 {with_object_particle(title)} 불러왔습니다."
        )
        st.rerun()


def _latest_common_id(database_path: str) -> str:
    """지금 공통 대장 최신 id(캐시). 없으면 `KeyError`(`BOOTSTRAP_ERRORS` 안 — 부르는 쪽이
    알린다)."""
    common_id = latest_equipment_revision_id(database_path)
    if common_id is None:
        raise KeyError("공통 대장 리비전이 없습니다.")
    return common_id


def _preview_for(
    database_path: str,
    common_id: str,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> ScheduleRestorePreview:
    """고른 리비전을 공통 대장 `common_id` 와 합쳐 그 시나리오 최신 자리에 놓았을 때의 차이(캐시).

    「이 리비전으로 되돌리기」 와 「여기서 새 시나리오」 가 같은 칸을 쓴다. 그 리비전을 공통 대장과
    합칠 수 없으면 예외다(`BOOTSTRAP_ERRORS` 안 — 부르는 쪽이 알린다).
    """
    return load_schedule_restore_preview(
        database_path,
        common_id,
        scenario.latest_schedule_revision_id,
        revision.schedule_revision_id,
    )


def restore_seen_token(
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
    *,
    common_id: str,
    release_no: int,
) -> str:
    """되돌리기 확인 글을 정하는 값 다섯 — 확인 체크 key 꼬리이자 저장소에 넘기는 대조값의 짝.

    확인 재료는 (공통, 그 시나리오 최신, 고른 리비전) 이 정하고 공식 시나리오의 발행 줄은 공식 발행
    번호가 정한다. 앞 두 칸(시나리오·고른 리비전)은 「같은 리비전에서 값만 바뀌었는가」 를 가른다.
    """
    return "__".join(
        (
            scenario.equipment_scenario_id,
            revision.schedule_revision_id,
            scenario.latest_schedule_revision_id or "",
            common_id,
            str(release_no),
        )
    )


def added_since_sentence(revision: EquipmentScheduleRevisionSummary, count: int) -> str:
    """그 리비전 뒤에 공통 대장에 든 호기가 「일정 없음」 이 된다는 한 문장(F4 — 수는 늘 적는다).
    0대면 빠지는 호기가 없다고 적는다."""
    title = f"r{revision.revision_no}"
    if not count:
        return f"{title} 뒤에 공통 대장에 든 호기는 없습니다(0대)."
    return (
        f"{title} 뒤에 공통 대장에 든 호기(지금 {count:,}대)는 {title}에 일정이 없어 이 설비 "
        "시나리오에서 「일정 없음」 이 됩니다 — 그 시나리오 계산·Space 에서 빠집니다."
    )


def branch_unscheduled_sentence(
    revision: EquipmentScheduleRevisionSummary, preview: ScheduleRestorePreview
) -> str:
    """「여기서 새 시나리오」 안내 — 새 시나리오의 일정 없음 수와 그 가운데 그 리비전 뒤에 든
    호기 수(0대면 없다고 적는다)."""
    title = f"r{revision.revision_no}"
    if not preview.unscheduled_after:
        return (
            f"{title}에는 일정이 없는 호기가 없습니다(0대) — 새 시나리오의 모든 호기가 일정을 "
            "듭니다."
        )
    added = (
        f"그 가운데 {title} 뒤에 공통 대장에 든 호기가 {preview.added_since:,}대입니다."
        if preview.added_since
        else f"{title} 뒤에 공통 대장에 든 호기는 없습니다(0대)."
    )
    return (
        f"{title}에 일정이 없는 호기 {preview.unscheduled_after:,}대는 새 시나리오에서도 「일정 "
        f"없음」 입니다 — {added}"
    )


def restore_preview_lines(
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
    preview: ScheduleRestorePreview,
    *,
    official_scenario: bool,
) -> list[str]:
    """「이 리비전으로 되돌리기」 확인 글 — 무엇이 바뀌고 무엇이 그대로인지(Markdown 줄).

    바뀌는 호기 수·비가동 행 수·일정 없음이 되는 호기, 그 리비전 뒤에 공통 대장에 든 호기의 「일정
    없음」(늘 적는다), 그대로인 것(사이 리비전·공통 대장·다른 시나리오), 공식 시나리오면 발행 규칙.
    """
    name = literal_markdown(scenario.scenario_name)
    title = f"r{revision.revision_no}"
    latest_no = scenario.latest_revision_no or 0
    new_title = f"r{latest_no + 1}"
    lines = [
        f"「{name}」 {title}의 일정(날짜 여섯·시나리오 메모·비가동)으로 되돌립니다 — 최신 "
        f"r{latest_no} 위에 새 리비전 {new_title}{object_particle(new_title)} 저장하고 "
        f"{title}~{with_topic_particle(f'r{latest_no}')} 그대로 남습니다.",
        f"**일정이나 비가동이 바뀌는 호기 {preview.changed_units:,}대** · 비가동 "
        f"{preview.downtime_rows_before:,}행 → {preview.downtime_rows_after:,}행 · 되돌린 뒤 "
        f"일정 없음 {preview.unscheduled_after:,}대(지금 일정이 있다가 빠지는 호기 "
        f"{preview.newly_unscheduled:,}대).",
        added_since_sentence(revision, preview.added_since),
        "공통 대장(호기 정보·실적·상태·Space 실물)과 다른 설비 시나리오는 그대로입니다.",
    ]
    layout = restore_layout_sentence(revision, preview, official_scenario=official_scenario)
    if layout:
        lines.append(layout)
    if official_scenario:
        lines.append(
            "공식 설비 시나리오입니다 — 아래 발행 체크가 켜져 있고 그 사이 발행하지 않은 더 새 "
            "리비전이 없으면 새 리비전을 공식으로 발행합니다."
        )
    return lines


def restore_layout_sentence(
    revision: EquipmentScheduleRevisionSummary,
    preview: ScheduleRestorePreview,
    *,
    official_scenario: bool,
) -> str:
    """되돌리기가 배치 차이(설비 0031)에 하는 일 한 문장 — 고른 리비전과 지금 최신의 저장된 차이가
    같으면 빈 글. 공식 설비 시나리오면 차이를 버린다(I2), 가정이면 고른 리비전의 차이를 지금 공통·층
    현행값으로 정규화해 되살린다 — 글은 **실제로 쓸** 차이(`restored_layout_*_rows`)로 적고, 그 뒤
    지운 호기·공식과 같아진 행이 빠지면 그 사실을 적는다. 판정은 저장소와 같은
    `restore_writes_nothing` 의 몫과 맞는다(설계 6-6 — 확인 글과 실제 쓰기가 갈리지 않게).

    가정 배치를 되살릴 때 그때 손대지 않은 호기는 지금 공식 자리를 따른다 — 그 리비전을 저장할 때
    본 공통과 자리가 달라진 호기(`layout_moved_since`)가 있으면 그 수를 덧붙인다(이력 「그때
    그대로」 와 다르다 — 검토 F21)."""
    if preview.layout_identical:
        return ""
    title = f"r{revision.revision_no}"
    stored = stored_layout_words(
        preview.layout_unit_rows, preview.layout_mark_rows, preview.layout_label_rows
    )
    if official_scenario:
        if not stored:
            return ""
        return (
            f"{title}에 저장된 배치 차이({stored})는 공식 설비 시나리오라 따라오지 않습니다 — "
            "일정·비가동만 되돌립니다."
        )
    restored = stored_layout_words(
        preview.restored_layout_unit_rows,
        preview.restored_layout_mark_rows,
        preview.restored_layout_label_rows,
    )
    dropped = (
        f"{title}에 저장된 차이({stored}) 가운데 그 뒤 지운 호기·지금 공식과 같아진 것은 빠집니다."
        if stored and stored != restored
        else ""
    )
    if preview.restored_layout_same:
        if not stored:
            return ""
        return (
            f"{title}에 저장된 배치 차이({stored})는 그 뒤 지운 호기이거나 지금 공식과 같아져 "
            "되살릴 것이 없습니다 — 가정 배치는 지금 최신 그대로입니다."
            if not restored
            else f"{title}의 가정 배치는 지금 최신과 같습니다 — 배치는 바뀌지 않습니다."
        )
    if restored:
        moved = (
            " 그때 손대지 않은 호기는 지금 공식 자리를 따르므로 그때와 자리가 다른 호기 "
            f"{preview.layout_moved_since:,}대가 있습니다(이력 「그때 그대로」 와 다름)."
            if preview.layout_moved_since
            else ""
        )
        if dropped:
            return f"{title}의 가정 배치(되살릴 차이 {restored})도 되살립니다 — {dropped}{moved}"
        return f"{title}의 가정 배치(저장된 차이 {stored})도 되살립니다.{moved}"
    if stored:
        return (
            f"{title}에 저장된 배치 차이({stored})는 그 뒤 지운 호기이거나 지금 공식과 같아져 "
            "되살릴 것이 없습니다 — 지금 최신의 가정 배치 차이는 지워지고 공식 배치를 따릅니다."
        )
    return (
        f"{title}에는 배치 차이가 없어 지금 최신의 가정 배치 차이는 지워지고 공식 배치를 따릅니다."
    )


def restore_confirm_label(
    revision: EquipmentScheduleRevisionSummary, preview: ScheduleRestorePreview
) -> str:
    """되돌리기 확인 체크 글 — 바뀌는 호기 수와 「일정 없음」 이 되는 호기를 수로 적는다(0대면 그
    리비전 뒤에 든 호기가 없다고)."""
    title = f"r{revision.revision_no}"
    added = (
        f"{title} 뒤에 공통 대장에 든 호기 {preview.added_since:,}대는 「일정 없음」 이 됩니다."
        if preview.added_since
        else f"{title} 뒤에 공통 대장에 든 호기는 없습니다(0대)."
    )
    return (
        f"{with_direction_particle(title + '의 일정')} 되돌립니다 — 호기 "
        f"{preview.changed_units:,}대의 일정이 바뀌고, {added}"
    )


def restore_result_message(
    scenario_name: str,
    revision: EquipmentScheduleRevisionSummary,
    result: ScheduleRestoreResult,
    *,
    moved: bool,
    kept_unsaved: bool,
) -> str:
    """되돌리기 뒤 알림 — 새 리비전·바뀐 호기 수·배치 차이·발행·세션 이동."""
    name = literal_markdown(scenario_name)
    title = f"r{revision.revision_no}"
    if result.schedule is None:
        return f"「{name}」 최신과 {title}의 일정·비가동이 같아 새 리비전을 만들지 않았습니다."
    created = f"r{result.schedule.revision_no}"
    sentences = [
        f"「{name}」 {with_direction_particle(title + '의 일정')} 되돌려 "
        f"{with_object_particle(created)} 저장했습니다(일정이 바뀐 호기 "
        f"{result.preview.changed_units:,}대)."
    ]
    if not result.preview.restored_layout_same:
        stored = stored_layout_words(
            result.schedule.layout_unit_count,
            result.schedule.layout_mark_count,
            result.schedule.layout_label_count,
        )
        sentences.append(
            f"배치 차이도 {title} 것으로 맞췄습니다({created}에 저장된 차이 {stored})."
            if stored
            else f"{created}에는 배치 차이가 없습니다 — 공식 배치를 따릅니다."
        )
    if result.release_no is not None:
        sentences.append(f"{with_direction_particle(f'공식 v{result.release_no}')} 발행했습니다.")
    elif result.release_withheld:
        sentences.append(
            "공식 설비 시나리오에 발행하지 않은 더 새 리비전이 있어 공식 발행은 하지 않았습니다 — "
            "이 구획의 「공식으로 발행」 으로 냅니다."
        )
    if moved:
        sentences.append(f"이 세션을 {with_direction_particle(created)} 옮겼습니다.")
    elif kept_unsaved:
        sentences.append(
            "이 세션에는 저장하지 않은 설비 편집이 있어 보던 리비전을 그대로 둡니다 — 일정 칸은 "
            f"잠기고, 사이드바 「설비 시나리오」 에서 최신 {with_object_particle(created)} "
            "불러올 수 있습니다."
        )
    return " ".join(sentences)


def _render_restore(
    database_path: str,
    session: EquipmentSession,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> None:
    """「이 리비전으로 되돌리기」(E7) — 확인 글을 보이고 확인 체크 뒤에 새 리비전으로 다시 저장한다.

    모든 설비 시나리오에서 된다(공식 시나리오면 저장과 같은 발행 규칙 — 발행 체크 기본 켬). 이
    세션이 그 시나리오를 보고 있고 저장하지 않은 설비 편집이 없으면 세션을 새 리비전으로 옮긴다(자기
    저장 뒤와 같다). 편집이 있으면 옮기지 않는다 — 버리지 않게 하고 낡음 잠금이 최신을 알린다.

    확인 체크는 그 회차에 확인 글을 정한 값 다섯(`restore_seen_token`)에 묶이고, 저장소에는 같은
    값을 대조값으로 넘긴다 — 다른 리비전을 고르거나 그 사이 남의 저장·발행으로 값이 바뀐 회차에는
    체크가 풀린 새 칸이 서고(그 까닭을 알린다) 단추가 잠긴다. 값이 그대로인데 저장소가 그 사이
    쓰기를 보면(캐시가 늦은 경우) 거절한다.
    """
    agreed_before = st.session_state.pop(RESTORE_AGREED_KEY, None)
    if revision.schedule_revision_id == scenario.latest_schedule_revision_id:
        title = f"r{revision.revision_no}"
        st.caption(
            f"{title}{topic_particle(title)} 「{literal_markdown(scenario.scenario_name)}」 의 "
            "최신이라 되돌릴 것이 없습니다 — 위 리비전 상자에서 옛 리비전을 고르세요."
        )
        return
    if session.legacy_trace_count:
        st.caption(legacy_trace_message(session.legacy_trace_count))
        return
    try:
        common_id = _latest_common_id(database_path)
        preview = _preview_for(database_path, common_id, scenario, revision)
    except BOOTSTRAP_ERRORS as exc:
        st.error(markdown_safe_tildes(f"되돌릴 수 없습니다: {bootstrap_error_message(exc)}"))
        return
    release_no = session.catalog.release_no or 0
    seen = restore_seen_token(scenario, revision, common_id=common_id, release_no=release_no)
    official_scenario = session.official_scenario_id == scenario.equipment_scenario_id
    for line in restore_preview_lines(
        scenario, revision, preview, official_scenario=official_scenario
    ):
        st.caption(line)
    # 단추를 세울지는 저장소의 「쓸 것 없음」 판정과 같은 함수다 — 공식 시나리오는 배치 차이를
    # 버리므로 일정·비가동만 본다(확인 글과 실제 쓰기가 갈리지 않게, 설계 6-6).
    if restore_writes_nothing(preview, official_scenario=official_scenario):
        same = "일정·비가동과" if official_scenario else "일정·비가동·가정 배치와"
        st.info(f"최신 r{scenario.latest_revision_no} 의 {same} 모두 같아 되돌릴 것이 없습니다.")
        return
    chosen = revision.schedule_revision_id
    revision_name = st.text_input(
        "새 리비전명(선택)",
        key=f"{_keyed(RESTORE_NAME_KEY)}__{chosen}",
        max_chars=REVISION_NAME_MAX_CHARS,
        placeholder=f"예: r{revision.revision_no} 일정 복원",
    )
    note = st.text_input("변경 메모(선택)", key=f"{_keyed(RESTORE_NOTE_KEY)}__{chosen}")
    saved_by = st.text_input(SAVED_BY_LABEL, key=f"{_keyed(RESTORE_BY_KEY)}__{chosen}")
    publish = DEFAULT_PUBLISH_OFFICIAL
    if official_scenario:
        publish = st.checkbox(
            PUBLISH_OFFICIAL_LABEL,
            value=DEFAULT_PUBLISH_OFFICIAL,
            key=f"{_keyed(RESTORE_PUBLISH_KEY)}__{chosen}",
        )
    if (
        isinstance(agreed_before, str)
        and agreed_before != seen
        and agreed_before.startswith(f"{scenario.equipment_scenario_id}__{chosen}__")
    ):
        st.warning(
            "확인한 뒤 공통 대장·이 시나리오 최신·공식 발행이 바뀌어 확인 체크를 풀었습니다 — 바뀐 "
            "확인 글을 다시 보고 체크하세요.",
            icon=":material/sync_problem:",
        )
    agreed = st.checkbox(
        restore_confirm_label(revision, preview), key=f"{_keyed(RESTORE_CONFIRM_KEY)}__{seen}"
    )
    if agreed:
        st.session_state[RESTORE_AGREED_KEY] = seen
    clicked = st.button(
        "되돌리기",
        icon=":material/history:",
        type="primary",
        disabled=not agreed,
        key=RESTORE_BUTTON_KEY,
        width="stretch",
    )
    if not clicked or not agreed:
        return
    try:
        # 대조값은 확인 체크를 묶은 값 그대로다 — 확인 글을 그린 값과 저장소가 대조하는 값이 같다.
        result = get_equipment_repository(database_path).restore_schedule_revision(
            chosen,
            expected_common_revision_id=common_id,
            expected_latest_schedule_revision_id=scenario.latest_schedule_revision_id,
            saved_by=saved_by or None,
            note=note or None,
            revision_name=revision_name or None,
            publish_official=publish,
            expected_release_no=release_no,
            expected_layout_role="official" if official_scenario else "overlay",
        )
    except EquipmentLayoutRoleChanged:
        # 확인 글(배치 차이를 버리나 되살리나)을 정한 역할이 그 사이 남의 발행으로 바뀌었다.
        _refused(
            "그 사이 공식 설비 시나리오가 바뀌어 되돌리지 않았습니다 — 바뀐 확인 글을 다시 보고 "
            "되돌리세요."
        )
        return
    except EquipmentRevisionConflict as exc:
        # 확인 글의 수가 그 사이 바뀌었다 — 목록·공통 최신을 다시 읽어 새 확인 글을 보인다.
        _refused(
            f"그 사이 다른 사용자가 {with_object_particle(exc.newest)} 저장해 되돌리지 "
            "않았습니다 — 바뀐 확인 글을 다시 보고 되돌리세요."
        )
        return
    except EquipmentReleaseMoved as exc:
        _refused(
            f"그 사이 다른 공식 발행(지금 공식 v{exc.current})이 있어 되돌리지 않았습니다 — 다시 "
            "보고 되돌리세요."
        )
        return
    except BOOTSTRAP_ERRORS as exc:
        st.error(markdown_safe_tildes(f"되돌리지 못했습니다: {bootstrap_error_message(exc)}"))
        return
    moved = False
    kept_unsaved = False
    if result.schedule is not None:
        st.session_state[PENDING_REVISION_KEY] = result.schedule.schedule_revision_id
    if result.schedule is not None and session.scenario_id == scenario.equipment_scenario_id:
        if has_unsaved_equipment_edits():
            kept_unsaved = True
        else:
            clear_equipment_scenario_cache()
            moved = (
                select_equipment_scenario(
                    database_path,
                    scenario.equipment_scenario_id,
                    result.schedule.schedule_revision_id,
                    discard=True,
                )
                is None
            )
    _written(
        restore_result_message(
            scenario.scenario_name, revision, result, moved=moved, kept_unsaved=kept_unsaved
        )
    )


def _render_branch(
    database_path: str,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> None:
    """「여기서 새 시나리오」(E7) — 고른 리비전의 일정을 r1 로 든 새 설비 시나리오(복제로만 만든다).

    출처는 고른 리비전이고, 새 r1 은 그 리비전을 지금 공통 대장과 합친 일정이라 그 리비전 뒤에 공통
    대장에 든 호기는 일정 없음이다.
    """
    name = literal_markdown(scenario.scenario_name)
    title = f"r{revision.revision_no}"
    st.caption(
        f"「{name}」 {title}의 일정·시나리오 메모·비가동을 지금 공통 대장과 합쳐 새 설비 시나리오 "
        "r1 로 옮깁니다. 이 시나리오는 그대로입니다."
    )
    try:
        preview = _preview_for(database_path, _latest_common_id(database_path), scenario, revision)
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            markdown_safe_tildes(
                f"이 리비전에서 새 시나리오를 만들 수 없습니다: {bootstrap_error_message(exc)}"
            )
        )
        return
    st.caption(branch_unscheduled_sentence(revision, preview))
    new_name = st.text_input(
        "새 설비 시나리오 이름", key=_keyed(CLONE_NAME_KEY), placeholder="예: 셋업 실무"
    )
    created_by = st.text_input("만든 사람(선택)", key=_keyed(CLONE_BY_KEY))
    if st.button(
        "새 시나리오 만들기",
        icon=":material/call_split:",
        type="primary",
        key=CLONE_BUTTON_KEY,
        width="stretch",
    ):
        try:
            created = get_equipment_repository(database_path).clone_equipment_scenario(
                revision.schedule_revision_id, name=new_name, created_by=created_by or None
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(
                markdown_safe_tildes(
                    f"새 시나리오를 만들지 못했습니다: {bootstrap_error_message(exc)}"
                )
            )
            return
        _written(
            f"「{name}」 {title}에서 설비 시나리오 「{literal_markdown(created.scenario_name)}」 "
            "r1 을 만들었습니다 — 설비 화면의 사이드바 설비 시나리오 줄이나 이 구획의 「이 리비전 "
            "불러오기」로 올립니다."
        )


def _settle_compare_field(key: str, current: str) -> str:
    """비교 후 쓰기 이름 칸(리비전명·시나리오 이름)을 위젯 앞에서 세우고 본 이름 칸 key 를 돌려준다.

    칸을 세울 때 본 이름(`…__seen`)이 비교 후 쓰기의 기준이다 — 그 사이 남이 바꿨으면 거절한다.
    고치지 않은 칸(칸 값 = 본 이름)은 **매 회차** 지금 이름을 다시 적는다. 남이 바꾼 이름으로
    다시 설 뿐 아니라, 닫힌 팝오버 안 칸은 브라우저에 마운트되지 않아 나중에 열 때 마지막 회차가
    실어 보낸 값으로만 서기 때문이다 — 처음 적은 회차 뒤 한 회차라도 지나 열면 빈 기본값으로
    서고, 그대로 누른 「리비전명 저장」 이 그 빈 값을 되보내 이름을 지웠다(2026-10-26 E2E). 고치던
    칸은 그대로 둔다(본 이름도 그대로 — 그 사이 남의 바꿈을 거절할 기준). 위젯을 그리기 전에
    부른다.
    """
    seen_key = f"{key}__seen"
    if key not in st.session_state or st.session_state.get(key) == st.session_state.get(seen_key):
        st.session_state[key] = current
        st.session_state[seen_key] = current
    return seen_key


def _render_revision_name(
    database_path: str,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> None:
    """「리비전명」(E7) — 고른 리비전의 이름표만 고친다(비우면 지운다). 일정·번호·메모는 그대로다.

    비교 후 쓰기라 그 사이 남이 바꿨으면 거절하고 지금 이름을 알린다. 이름은 리비전 목록 캐시만
    싣는다 — 쓰기 뒤 `clear_equipment_scenario_cache()`(쓰기 세대)로 목록이 새 이름을 읽는다.
    """
    key = f"{_keyed(REVISION_NAME_KEY)}__{revision.schedule_revision_id}"
    seen_key = _settle_compare_field(key, revision.revision_name or "")
    st.caption(
        f"r{revision.revision_no} 의 이름표입니다 — 일정·번호·메모는 그대로이고 나중에 다시 "
        "고칠 수 있습니다. 비우고 저장하면 이름이 지워집니다."
    )
    label = st.text_input("리비전명", key=key, max_chars=REVISION_NAME_MAX_CHARS)
    if st.button(
        "리비전명 저장",
        type="primary",
        key=REVISION_NAME_BUTTON_KEY,
        width="stretch",
    ):
        try:
            seen_name = st.session_state.get(seen_key)
            renamed = get_equipment_repository(database_path).rename_schedule_revision(
                revision.schedule_revision_id,
                name=label,
                expected_name=seen_name if isinstance(seen_name, str) and seen_name else None,
            )
        except EquipmentScheduleRevisionNameMoved as exc:
            # 남이 먼저 바꿨다 — 다음 회차가 목록에서 지금 이름을 읽어 칸을 다시 세운다.
            _refused(f"리비전명을 바꾸지 않았습니다 — {exc}")
            return
        except BOOTSTRAP_ERRORS as exc:
            st.error(
                markdown_safe_tildes(
                    f"리비전명을 바꾸지 못했습니다: {bootstrap_error_message(exc)}"
                )
            )
            return
        shown = schedule_revision_title(renamed)
        _written(
            f"「{literal_markdown(scenario.scenario_name)}」 "
            f"{literal_markdown(shown)} — 리비전명을 "
            + ("지웠습니다." if renamed.revision_name is None else "저장했습니다.")
        )


def _render_rename(database_path: str, scenario: EquipmentScenarioSummary) -> None:
    """「시나리오 이름 바꾸기」 — 비교 후 쓰기다. 칸을 세울 때 본 이름을 따로 들고(`__seen`) 그
    이름과 대조하므로, 그 사이 남이 바꿨으면 덮지 않고 거절해 지금 이름을 알린다. 고치지 않은 칸은
    매 회차 지금 이름으로 다시 적는다(`_settle_compare_field` — 팝오버 안 칸은 매 회차 그려져 key 가
    남는다)."""
    key = f"{_keyed(RENAME_KEY)}__{scenario.equipment_scenario_id}"
    current = scenario.scenario_name
    seen_key = _settle_compare_field(key, current)
    name = st.text_input("이름", key=key)
    if st.button("이름 바꾸기", type="primary", key=RENAME_BUTTON_KEY, width="stretch"):
        seen_name = st.session_state.get(seen_key)
        try:
            renamed = get_equipment_repository(database_path).rename_equipment_scenario(
                scenario.equipment_scenario_id,
                name=name,
                expected_name=seen_name if isinstance(seen_name, str) else current,
            )
        except EquipmentScenarioNameMoved as exc:
            # 남이 먼저 바꿨다 — 다음 회차가 목록에서 지금 이름을 읽어 칸을 다시 세운다.
            _refused(f"설비 시나리오 이름을 바꾸지 않았습니다 — {exc}")
            return
        except BOOTSTRAP_ERRORS as exc:
            st.error(
                markdown_safe_tildes(f"이름을 바꾸지 못했습니다: {bootstrap_error_message(exc)}")
            )
            return
        quoted = f"「{literal_markdown(renamed.scenario_name)}」"
        _written(f"설비 시나리오 이름을 {with_direction_particle(quoted)} 했습니다.")


def clearable_layout(session: EquipmentSession, scenario: EquipmentScenarioSummary) -> bool:
    """「배치 차이 모두 지우기」 를 세울까 — 가정 설비 시나리오(공식 시나리오에는 지울 것이 없다 —
    I2)이고 최신에 저장된 배치 차이가 있을 때(행이 있거나 지문이 빈 차이가 아님)."""
    if scenario.equipment_scenario_id == session.official_scenario_id:
        return False
    if scenario.latest_schedule_revision_id is None:
        return False
    return any(scenario.latest_layout_rows) or (
        scenario.latest_layout_hash is not None
        and scenario.latest_layout_hash != EMPTY_LAYOUT_DIGEST
    )


def clear_layout_lines(scenario: EquipmentScenarioSummary) -> list[str]:
    """「배치 차이 모두 지우기」 확인 글(Markdown 줄) — 무엇을 비우고 무엇이 그대로인지."""
    name = literal_markdown(scenario.scenario_name)
    latest_no = scenario.latest_revision_no or 0
    latest = f"r{latest_no}"
    new_title = f"r{latest_no + 1}"
    stored = stored_layout_words(*scenario.latest_layout_rows) or "저장된 차이"
    return [
        f"「{name}」 최신 {latest}의 일정·비가동은 그대로 두고 배치 차이({stored})만 비운 새 "
        f"리비전 {new_title}{object_particle(new_title)} 저장합니다 — 이 설비 시나리오의 Space "
        "배치가 공식 배치로 돌아갑니다(공식에서 고친 자리를 다시 따라갑니다).",
        f"{with_topic_particle(latest)} 그대로 남습니다 — 배치안을 되살리려면 그 리비전을 고르고 "
        "「이 리비전으로 되돌리기」, 따로 남기려면 먼저 「여기서 새 시나리오」 로 옮겨 두세요.",
        "공통 대장·층 도면·다른 설비 시나리오는 그대로입니다. 공식 발행은 하지 않습니다.",
    ]


def clear_layout_message(
    scenario_name: str,
    created: EquipmentScheduleRevisionSummary | None,
    *,
    moved: bool,
    kept_unsaved: bool,
) -> str:
    """「배치 차이 모두 지우기」 뒤 알림 — 새 리비전·세션 이동."""
    name = literal_markdown(scenario_name)
    if created is None:
        return f"「{name}」 최신에 지울 배치 차이가 없어 새 리비전을 만들지 않았습니다."
    title = f"r{created.revision_no}"
    sentences = [
        f"「{name}」 의 배치 차이를 모두 지운 {with_object_particle(title)} 저장했습니다 — 이 "
        "설비 시나리오의 배치는 이제 공식 배치를 따릅니다."
    ]
    if moved:
        sentences.append(f"이 세션을 {with_direction_particle(title)} 옮겼습니다.")
    elif kept_unsaved:
        sentences.append(
            "이 세션에는 저장하지 않은 설비 편집이 있어 보던 리비전을 그대로 둡니다 — 사이드바 "
            f"「설비 시나리오」 에서 최신 {with_object_particle(title)} 불러올 수 있습니다."
        )
    return " ".join(sentences)


def _render_clear_layout(
    database_path: str, session: EquipmentSession, scenario: EquipmentScenarioSummary
) -> None:
    """「배치 차이 모두 지우기」(설계 6-6 — 저장소 `clear_layout_overlay`). 확인 체크는 그 시나리오
    최신 id 에 묶인다 — 그 사이 남이 저장해 최신이 바뀌면 체크가 풀린 새 칸이 서고, 캐시가 늦어 못
    봤으면 저장소가 낡음으로 거절한다. 이 세션이 그 시나리오를 보고 있고 저장하지 않은 설비 편집이
    없으면 세션을 새 리비전으로 옮긴다(되돌리기와 같다)."""
    if session.legacy_trace_count:
        st.caption(legacy_trace_message(session.legacy_trace_count))
        return
    for line in clear_layout_lines(scenario):
        st.caption(line)
    latest_id = scenario.latest_schedule_revision_id or ""
    suffix = f"{scenario.equipment_scenario_id}__{latest_id}"
    note = st.text_input("변경 메모(선택)", key=f"{_keyed(CLEAR_LAYOUT_NOTE_KEY)}__{suffix}")
    saved_by = st.text_input(SAVED_BY_LABEL, key=f"{_keyed(CLEAR_LAYOUT_BY_KEY)}__{suffix}")
    agreed = st.checkbox(
        "배치 차이를 모두 지우고 공식 배치로 돌립니다",
        key=f"{_keyed(CLEAR_LAYOUT_CONFIRM_KEY)}__{suffix}",
    )
    if not st.button(
        "배치 차이 모두 지우기",
        icon=":material/layers_clear:",
        type="primary",
        disabled=not agreed,
        key=CLEAR_LAYOUT_BUTTON_KEY,
        width="stretch",
    ):
        return
    try:
        created = get_equipment_repository(database_path).clear_layout_overlay(
            scenario.equipment_scenario_id,
            expected_latest_schedule_revision_id=scenario.latest_schedule_revision_id,
            saved_by=saved_by or None,
            note=note or None,
        )
    except EquipmentRevisionConflict as exc:
        _refused(
            f"그 사이 다른 사용자가 {with_object_particle(exc.newest)} 저장해 배치 차이를 지우지 "
            "않았습니다 — 바뀐 확인 글을 다시 보고 지우세요."
        )
        return
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            markdown_safe_tildes(f"배치 차이를 지우지 못했습니다: {bootstrap_error_message(exc)}")
        )
        return
    moved = False
    kept_unsaved = False
    if created is not None:
        # 그 리비전에서 남은 일을 이어 하게(공식 발행 등) 리비전 상자·세션을 새 리비전에 둔다.
        moved, kept_unsaved = _follow_new_revision(
            database_path, session, scenario, created.schedule_revision_id
        )
    clear_equipment_snapshot_cache()
    _written(
        clear_layout_message(
            scenario.scenario_name, created, moved=moved, kept_unsaved=kept_unsaved
        )
    )


def publish_layout_lines(
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
    preview: LayoutPublishPreview,
    *,
    official: bool = False,
) -> tuple[list[str], bool]:
    """발행 확인 팝업의 배치 줄 — (줄, 막힘). 발행 쓰기와 같은 판정(`load_layout_publish_preview`)을
    미리 읽어 막히면 그 까닭을(「발행」 단추를 끈다), 공식과 같아진 차이만 남았으면 정리 리비전으로
    발행한다는 것을 적는다(설계 6-5 — 머리 「배치는 공식과 같습니다」 와 발행 거부가 함께 뜨지
    않게). 셈은 「실효 n대(저장된 차이 m행)」 꼴 하나다(설계 8-2). 막힘 글은 발행 쓰기 거부와 같은
    한 곳(`layout_publish_blocked_words`)이다 — 실제로 공식과 다른 쪽만 「실효」 로 적고, 옛
    리비전은 그 경우에 서는 길(되돌린 뒤 지우기·최신 발행)을 안내한다. `official` 은 그 시나리오가
    지금 공식 설비 시나리오인가다."""
    if preview.action == "publish":
        return [], False
    name = literal_markdown(scenario.scenario_name)
    if preview.action == "clean":
        new_title = f"r{(scenario.latest_revision_no or 0) + 1}"
        stored = stored_layout_words(
            preview.stored_units, preview.stored_marks, preview.stored_labels
        )
        return (
            [
                f"r{revision.revision_no}의 배치 차이({stored})는 지금 공식과 같아졌습니다 — "
                f"공식과 같아진 배치 차이 {preview.stored_rows:,}행을 정리한 "
                f"{with_direction_particle(new_title)} 발행합니다(일정·비가동은 r"
                f"{revision.revision_no} 그대로)."
            ],
            False,
        )
    block = preview.block(
        name,
        revision.revision_no,
        scenario.latest_revision_no or revision.revision_no,
        official=official,
    )
    return [layout_publish_blocked_words(block)], True


def publish_preview(
    session: EquipmentSession,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
    *,
    official_revisions: Sequence[EquipmentScheduleRevisionSummary] = (),
) -> list[str]:
    """발행 전에 보일 줄 — 지금 공식 → 새 공식, 고른 리비전이 그 시나리오 최신이 아니면 그 사실.

    지금 공식의 리비전 번호는 그 시나리오 최신·이 세션의 스냅샷·`official_revisions`(공식 시나리오의
    리비전 목록) 차례로 찾는다 — 공식이 그 시나리오 최신이 아니고 이 세션이 그것을 들고 있지 않으면
    목록에서만 나온다. 어디에도 없으면(목록 한도 밖) 번호를 적지 않는다.
    """
    release = session.catalog.latest_release
    current = "공식 발행 없음"
    if release is not None:
        official = session.catalog.scenario(release.equipment_scenario_id)
        official_name = official.scenario_name if official is not None else "?"
        official_revision = _revision_no(
            session, release.schedule_revision_id, official, official_revisions
        )
        current = f"지금 공식 v{release.release_no} · 「{literal_markdown(official_name)}」" + (
            f" r{official_revision}" if official_revision is not None else ""
        )
    next_no = (release.release_no if release is not None else 0) + 1
    lines = [
        f"{current} → 새 공식 v{next_no} · 「{literal_markdown(scenario.scenario_name)}」 "
        f"r{revision.revision_no}"
    ]
    if revision.schedule_revision_id != scenario.latest_schedule_revision_id:
        lines.append(
            f"{with_topic_particle(f'r{revision.revision_no}')} "
            f"「{literal_markdown(scenario.scenario_name)}」 의 최신"
            f"(r{scenario.latest_revision_no})이 아닙니다."
        )
    if release is not None and release.schedule_revision_id == revision.schedule_revision_id:
        lines.append("이미 공식 발행인 리비전입니다 — 발행해도 바뀌지 않습니다.")
    return lines


def _revision_no(
    session: EquipmentSession,
    schedule_revision_id: str,
    scenario: EquipmentScenarioSummary | None,
    revisions: Sequence[EquipmentScheduleRevisionSummary],
) -> int | None:
    if scenario is None:
        return None
    if scenario.latest_schedule_revision_id == schedule_revision_id:
        return scenario.latest_revision_no
    if session.snapshot is not None and session.snapshot.schedule is not None:
        if session.snapshot.schedule.schedule_revision_id == schedule_revision_id:
            return session.snapshot.schedule.revision_no
    return next(
        (
            item.revision_no
            for item in revisions
            if item.schedule_revision_id == schedule_revision_id
            and item.equipment_scenario_id == scenario.equipment_scenario_id
        ),
        None,
    )


def publish_seen_token(
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
    release_no: int,
) -> dict[str, object]:
    """발행 확인 글을 정하는 값 — 고른 리비전·공식 번호·그 시나리오 최신(id 와 번호).

    확인 글의 「지금 공식 → 새 공식」 은 공식 번호가, 「rN은 … 의 최신(rM)이 아닙니다」 와 배치 줄은
    그 시나리오 최신이 정한다(되돌리기 `restore_seen_token` 과 같은 꼴). 그린 회차에
    `PUBLISH_SEEN_KEY` 에 남기고 누른 회차에 `publish_seen_refusal` 이 지금 값과 견준다.
    """
    return {
        "revision": revision.schedule_revision_id,
        "release_no": release_no,
        "latest": scenario.latest_schedule_revision_id,
        "latest_no": scenario.latest_revision_no,
    }


def publish_seen_refusal(
    seen: object,
    *,
    scenario: EquipmentScenarioSummary,
    schedule_revision_id: str,
    release_no: int,
) -> str | None:
    """「공식으로 발행」 을 누른 회차에 거절할 까닭 — 누르기 전 회차의 확인 글(`seen` — 그 회차에
    남긴 `publish_seen_token`)이 지금과 다르면 그 사실을, 같으면 None.

    단추를 누른 회차에는 확인 글이 지금 목록으로 다시 그려진다. 그 사이 남이 발행했으면 지금 번호로
    대조해도 맞아 「지금 공식 v4 → 새 공식 v5」 를 본 사람이 말없이 v6 을 내게 된다(E7 리뷰).
    그 사이 남이 같은 시나리오에 새 리비전을 저장했으면, 「rN은 최신이 아닙니다」 를 본 적 없는
    사람이 최신이 아닌 리비전을 말없이 공식으로 낸다(2026-10-26 E2E) — 그것도 거절해 바뀐 확인
    글을 보게 한다.
    """
    if not isinstance(seen, dict) or seen.get("revision") != schedule_revision_id:
        return "발행 확인 글을 다시 그렸습니다 — 바뀐 확인 글을 보고 다시 누르세요."
    before = seen.get("release_no")
    if before != release_no:
        was = release_words(before if isinstance(before, int) else 0)
        now = release_words(release_no)
        return (
            f"확인 글을 본 뒤 공식이 바뀌어({was} → 지금 {now}) 발행하지 않았습니다 — 다른 "
            f"사용자가 그 사이 발행했습니다. 바뀐 확인 글(지금 공식 {now} → 새 공식 "
            f"v{release_no + 1})을 다시 보고 발행하세요."
        )
    if seen.get("latest") == scenario.latest_schedule_revision_id:
        return None
    was_no = seen.get("latest_no")
    latest = f"r{scenario.latest_revision_no}"
    if not isinstance(was_no, int) or scenario.latest_revision_no is None:
        return "발행 확인 글을 다시 그렸습니다 — 바뀐 확인 글을 보고 다시 누르세요."
    name = literal_markdown(scenario.scenario_name)
    return (
        f"확인 글을 본 뒤 「{name}」 의 최신이 바뀌어(r{was_no} → 지금 {latest}) 발행하지 "
        f"않았습니다 — 다른 사용자가 그 사이 {with_object_particle(latest)} 저장했습니다. 바뀐 "
        "확인 글을 다시 보고 발행하세요."
    )


def release_words(release_no: int) -> str:
    """공식 발행 번호 한 마디 — 「v3」, 발행이 없던 0 은 「발행 없음」(「v0」 이라 적지 않는다)."""
    return f"v{release_no}" if release_no > 0 else "발행 없음"


def _official_revisions(
    database_path: str, session: EquipmentSession
) -> tuple[EquipmentScheduleRevisionSummary, ...]:
    """지금 공식 시나리오의 리비전 목록(캐시 — 고른 시나리오가 공식이면 리비전 표와 같은 칸). 발행이
    없거나 읽지 못하면 빈 묶음이다(확인 글이 지금 공식 번호만 빼고 선다)."""
    release = session.catalog.latest_release
    if release is None:
        return ()
    try:
        return load_equipment_schedule_revisions(database_path, release.equipment_scenario_id)
    except BOOTSTRAP_ERRORS:
        return ()


def _render_publish(
    database_path: str,
    session: EquipmentSession,
    scenario: EquipmentScenarioSummary,
    revision: EquipmentScheduleRevisionSummary,
) -> None:
    # 앞 회차(누르기 전)에 그린 확인 글의 값 — 이번 회차 값으로 바꿔 두기 전에 꺼낸다.
    seen_before = st.session_state.pop(PUBLISH_SEEN_KEY, None)
    release_no = session.catalog.release_no or 0
    for line in publish_preview(
        session,
        scenario,
        revision,
        official_revisions=_official_revisions(database_path, session),
    ):
        st.caption(line)
    # 배치 차이가 있으면 발행하지 않는다(LY5 「공식으로 올리기」 전까지 — Q4). 발행 쓰기와 같은
    # 판정을 미리 읽어 단추를 끄거나 정리 리비전으로 발행한다는 것을 적는다.
    try:
        layout = load_layout_publish_preview(
            database_path,
            _latest_common_id(database_path),
            revision.schedule_revision_id,
            scenario.latest_schedule_revision_id,
        )
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            markdown_safe_tildes(
                f"발행 확인 글을 만들지 못했습니다: {bootstrap_error_message(exc)}"
            )
        )
        return
    layout_lines, blocked = publish_layout_lines(
        scenario,
        revision,
        layout,
        official=scenario.equipment_scenario_id == session.official_scenario_id,
    )
    for line in layout_lines:
        if blocked:
            st.error(line, icon=":material/block:")
        else:
            st.caption(f":material/layers: {line}")
    st.session_state[PUBLISH_SEEN_KEY] = publish_seen_token(scenario, revision, release_no)
    st.caption(
        "공식은 새 세션(Space 포함 — 처음 연 화면)·공정 Capa 상세(HOME 칸)·진척 비교 기준선이 보는 "
        "설비 시나리오입니다. 발행은 append-only 입니다."
    )
    released_by = st.text_input("발행자(선택)", key=_keyed(PUBLISH_BY_KEY))
    note = st.text_input("발행 메모(선택)", key=_keyed(PUBLISH_NOTE_KEY))
    if st.button(
        "공식으로 발행",
        type="primary",
        key=PUBLISH_BUTTON_KEY,
        width="stretch",
        disabled=blocked,
    ):
        refusal = publish_seen_refusal(
            seen_before,
            scenario=scenario,
            schedule_revision_id=revision.schedule_revision_id,
            release_no=release_no,
        )
        if refusal is not None:
            _refused(refusal)
            return
        try:
            # 대조값은 누르기 전 확인 글이 보인 번호다(위 대조로 지금 목록 번호와 같다) — 목록
            # 캐시가 늦어 그 사이의 발행을 못 봤으면 저장소가 쓰기 잠금 안에서 거절한다.
            published = get_equipment_repository(database_path).publish_equipment_release(
                revision.schedule_revision_id,
                released_by=released_by or None,
                note=note or None,
                expected_latest_release_no=release_no or None,
            )
        except EquipmentReleaseMoved as exc:
            _refused(
                f"확인 글을 본 뒤 공식이 바뀌어({release_words(exc.expected)} → 지금 "
                f"{release_words(exc.current)}) 발행하지 않았습니다 — 바뀐 확인 글을 다시 보고 "
                "발행하세요."
            )
            return
        except EquipmentLayoutPublishBlocked as exc:
            # 확인 글을 그린 뒤 남이 배치를 저장했다 — 목록을 다시 읽어 막힘 글을 보인다.
            _refused(literal_markdown(str(exc)))
            return
        except BOOTSTRAP_ERRORS as exc:
            st.error(markdown_safe_tildes(f"발행하지 못했습니다: {bootstrap_error_message(exc)}"))
            return
        cleaned = published.schedule_revision_id != revision.schedule_revision_id
        moved = kept_unsaved = False
        if cleaned:
            # 정리 리비전 rN+1 로 발행했다 — 「배치 차이 모두 지우기」 처럼 리비전 상자와 (그
            # 시나리오를 보던) 세션을 새 리비전으로 옮긴다. 남기면 세션이 옛 rN 에 남아 낡음·Space
            # 배치 잠금·빨간 막힘 글(옛 리비전의 남은 행)이 바로 선다(S4 리뷰).
            moved, kept_unsaved = _follow_new_revision(
                database_path, session, scenario, published.schedule_revision_id
            )
        _written(
            publish_result_message(
                scenario.scenario_name,
                revision,
                published.release_no,
                cleaned_no=(scenario.latest_revision_no or 0) + 1 if cleaned else None,
                moved=moved,
                kept_unsaved=kept_unsaved,
            )
        )


def publish_result_message(
    scenario_name: str,
    revision: EquipmentScheduleRevisionSummary,
    release_no: int,
    *,
    cleaned_no: int | None,
    moved: bool,
    kept_unsaved: bool,
) -> str:
    """「공식으로 발행」 뒤 알림 — 정리 리비전으로 발행했으면(`cleaned_no`) 그 번호와 세션 이동."""
    name = literal_markdown(scenario_name)
    release = f"v{release_no}"
    head = f"공식 {with_direction_particle(release)} 발행했습니다 — 「{name}」 "
    if cleaned_no is None:
        return head + f"r{revision.revision_no}."
    title = f"r{cleaned_no}"
    sentences = [head + f"r{revision.revision_no}의 공식과 같아진 배치 차이를 정리한 {title}."]
    if moved:
        sentences.append(f"이 세션을 {with_direction_particle(title)} 옮겼습니다.")
    elif kept_unsaved:
        sentences.append(
            "이 세션에는 저장하지 않은 설비 편집이 있어 보던 리비전을 그대로 둡니다 — 사이드바 "
            f"「설비 시나리오」 에서 최신 {with_object_particle(title)} 불러올 수 있습니다."
        )
    return " ".join(sentences)


def _follow_new_revision(
    database_path: str,
    session: EquipmentSession,
    scenario: EquipmentScenarioSummary,
    schedule_revision_id: str,
) -> tuple[bool, bool]:
    """쓰기가 그 시나리오의 새 리비전을 만든 뒤 — 리비전 상자를 새 리비전에 두고(남은 일을 이어
    하게), 이 세션이 그 시나리오를 보고 있으면 세션도 옮긴다. 저장하지 않은 설비 편집이 있으면 보던
    리비전을 그대로 둔다. (옮김, 편집 때문에 남김)."""
    st.session_state[PENDING_REVISION_KEY] = schedule_revision_id
    if session.scenario_id != scenario.equipment_scenario_id:
        return False, False
    if has_unsaved_equipment_edits():
        return False, True
    clear_equipment_snapshot_cache()
    moved = (
        select_equipment_scenario(
            database_path,
            scenario.equipment_scenario_id,
            schedule_revision_id,
            discard=True,
        )
        is None
    )
    return moved, False


def continue_confirm_label(review: LegacyTraceReview) -> str:
    """「이대로 이어 쓰기」 확인 체크 글 — 무엇을 잃는지 수로 적는다(설계 2-4)."""
    revision = (
        f"옛 배포 리비전 r{review.trace_revision_no}"
        if review.trace_revision_no
        else "옛 배포 리비전"
    )
    dropped = (
        f" 지금 공통 대장의 호기 {review.dropped_units:,}대가 그 리비전에 없어 모든 설비 "
        "시나리오에서 빠지고(그 일정·비가동은 고아가 됩니다),"
        if review.dropped_units
        else ""
    )
    return (
        f"{revision}{object_particle(revision)} 공통 대장 최신으로 받아들입니다 —{dropped} 옛 "
        "배포에서 고친 일정은 들어오지 않습니다. 백업 복원 대신 이대로 이어 씁니다."
    )


def continue_confirm_key(count: int, review: LegacyTraceReview) -> str:
    """「이대로 이어 쓰기」 확인 체크 key — 체크 글을 정하는 값 셋(흔적 수·옛 배포 리비전
    번호·빠지는 호기 수)이 바뀌면 다른 key 라 체크가 풀린 새 칸으로 선다."""
    return (
        f"{_keyed(CONTINUE_CONFIRM_KEY)}__{count}__{review.trace_revision_no or 0}"
        f"__{review.dropped_units}"
    )


def _render_legacy_trace(database_path: str, count: int) -> None:
    """옛 배포 흔적 — 경고와 「이대로 이어 쓰기」(확인 체크 뒤, 흔적 수를 대조해 이관 경계를
    덧붙인다). 이어 쓰기는 append-only 라 되돌릴 수 없다 — 빠지는 호기 수를 체크 글에 적고, 옛 배포
    리비전이 어느 시나리오 일정과도 합쳐지지 않으면 단추를 끄고 백업 복원만 남긴다."""
    st.warning(legacy_trace_message(count), icon=":material/history:")
    try:
        review = load_legacy_trace_review(database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            markdown_safe_tildes(f"옛 배포 흔적을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        )
        return
    if review.refusal is not None:
        st.error(
            "옛 배포로 저장한 공통 대장이 설비 시나리오 일정과 합쳐지지 않아 이어 쓸 수 없습니다 — "
            f"{literal_markdown(review.refusal)} 런북 4-2 대로 백업을 복원하세요.",
            icon=":material/block:",
        )
        return
    st.caption(
        "백업을 복원할 수 있으면 복원이 먼저입니다(런북 4-2). 이어 쓰기는 되돌릴 수 없습니다."
    )
    agreed = st.checkbox(continue_confirm_label(review), key=continue_confirm_key(count, review))
    if st.button(
        "이대로 이어 쓰기",
        icon=":material/fast_forward:",
        key=CONTINUE_BUTTON_KEY,
        disabled=not agreed,
    ):
        try:
            get_equipment_repository(database_path).acknowledge_legacy_trace(
                expected_trace_count=count, note="이대로 이어 쓰기"
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(markdown_safe_tildes(f"이어 쓰지 못했습니다: {bootstrap_error_message(exc)}"))
            return
        _written("옛 배포 흔적을 확인했습니다 — 설비 저장을 다시 할 수 있습니다.")
