# Purpose: 시나리오 목록·리비전 표를 바로 고치는 관리 화면과 복제·월 머지·연도 Shift 작업을 그린다.

"""시나리오 관리 「Capa 시나리오」 탭 — 목록 관리 · 복제 · 월 머지 · 연도 Shift.

「목록 관리」 가 시나리오를 다루는 단일 입구다. 설비 마스터 편집기와 같은 두 칸이다(2026-11-06
사용자 결정 안 3 — 틀은 `components/side_panel.py`) —

- 왼쪽: 시나리오 표(`components/scenario_list_grid` — 브라우저 표). 이름을 눌러 열고, 연 줄의
  이름을 다시 눌러 고치고, 줄을 끌어 옮긴다. 칸을 고치는 동안 앱이 돌지 않고 확정 뒤 묶어 한 번
  돈다.
- 오른쪽 칸 다섯: 상세(그 시나리오의 리비전 표 · 값 줄 · 불러오기 · 공식으로 지정… · 보관…) · 점검
  (고른 리비전의 계산에서 빠진 행 묶음 — `components/scenario_input_check.py`) · 저장 전 변경(수
  넷 · 옛 값 → 새 값 · 줄 되돌리기 · 모두 버리기 · 변경 저장) · 공식 이력 · 보관함(되돌리기 · 영구
  삭제).

고침은 행 id 로 세션 초안에 둔다(`services/scenario_list_edits.ListDraft`) — 다른 시나리오를 열어도
리비전명 고침이 남고, 다른 세션이 차례를 바꿔도 엉뚱한 줄에 붙지 않는다. 리비전 **내용**은
append-only 라 고칠 수 있는 것은 시나리오명 · 리비전명 · 순서뿐이고, 저장은 「변경 저장」 한 곳에서
한 트랜잭션으로 쓴다. 새 리비전 저장은 사이드바 시나리오 팝업 한 곳이다.

표 컴포넌트 모듈은 읽을 때 등록하므로 「목록 관리」 를 그리는 회차에 늦게 불러온다 — 화면 탭 줄은
`scenario_list_state` 만 읽는다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, NoReturn, cast

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.capacity_gate import official_publish_verdict, revision_save_verdict
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.dialog_host import DialogBody, DialogHost
from capa_simulation.components.flash import (
    FlashKind,
    queue_flash,
    render_flash,
    send_to_popup,
)
from capa_simulation.components.grid_shared import outbox_mount, outbox_value
from capa_simulation.components.intro_summary import forget_intro_summary_check
from capa_simulation.components.literal_markdown import literal_markdown, markdown_safe_tildes
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.profile_caption import render_row_value
from capa_simulation.components.required_exclusion_notice import (
    REQUIRED_TAB_GOTO,
    required_check_target,
)
from capa_simulation.components.revision_label import revision_label
from capa_simulation.components.save_section import discard_popover
from capa_simulation.components.scenario_input_check import (
    CHECK_NOTICE_KEY,
    WIDE_TITLE,
    WideValue,
    WideValues,
    render_input_check_panel,
    render_wide_body,
    wide_target,
)
from capa_simulation.components.scenario_list_state import (
    CHANGES_KEY,
    CHECKS_KEY,
    LIST_MODE,
    MOUNT_KEYS,
    REVISIONS_KEY,
    SIDE_CHECK,
    SIDE_CHOICE_KEY,
    SIDE_NEXT_KEY,
    TABLE_KEY,
    follow_created_scenario,
    load_draft,
    remember_shown_order,
    shown_order,
    store_draft,
    take_check_target,
)
from capa_simulation.components.scenario_management_tabs import CAPA_SCENARIO_TAB_NAME
from capa_simulation.components.scenario_month_merge import (
    MERGE_SOURCE_ROLES,
    render_scenario_month_merge,
)
from capa_simulation.components.scenario_transform import forget_derived_sources
from capa_simulation.components.scenario_year_shift import (
    SHIFT_SOURCE_ROLES,
    render_scenario_year_shift,
)
from capa_simulation.components.widget_generation import (
    bump,
    generation,
    widget_key,
    write_once_value,
)
from capa_simulation.components.write_guard import (
    SEEN_MISSING_MESSAGE,
    NoticeMark,
    held_flash,
    held_notice,
    is_own_save,
    just_written,
    note_notice,
    note_written,
    notice_marks,
    own_save_marks,
    queue_refusal,
    remember_own_save,
    remember_seen,
    save_once,
    seen,
    take_refusal,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    prune_named_choice,
)
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.cache import (
    clear_global_comparison_scenario_cache,
    clear_global_main_cases_cache,
    clear_global_securement_threshold_cache,
    clear_scenario_snapshot_cache,
    get_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import (
    OfficialReleaseSummary,
    RevisionSummary,
    ScenarioCreate,
    ScenarioPreset,
    ScenarioSummary,
)
from capa_simulation.persistence.repository import (
    DUPLICATE_SCENARIO_NAME_MESSAGE,
    REVISION_TABLES,
    SCENARIO_LIST_MOVED_MESSAGE,
    BatchEditRefused,
    DuckDBScenarioRepository,
    OfficialReleaseMoved,
    name_moved_message,
)
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    active_persisted_revision_id,
    active_persisted_scenario_id,
    active_scenario_label,
    clear_persisted_scenario_activation,
    has_unsaved_scenario_changes,
    rename_active_revision_label,
    rename_active_scenario_label,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import (
    ActiveScenario,
    ensure_active_scenario,
    session_virtual_products,
)
from capa_simulation.services.korean_particle import object_particle, with_topic_particle
from capa_simulation.services.revision_compatibility import revision_block_reason
from capa_simulation.services.scenario_list_edits import (
    ChangeCounts,
    ListDraft,
    ListProblems,
    ListRules,
    Reconciled,
    RevisionFacts,
    SavedList,
    SavedRevision,
    SavePlan,
    ScenarioFacts,
    SettledName,
    change_counts,
    changes_payload,
    cleared,
    draft_base,
    draft_fingerprint,
    fold_ops,
    has_edits,
    list_problems,
    official_label,
    rebased_order,
    reconcile,
    revision_status_label,
    revisions_payload,
    save_plan,
    scenarios_payload,
    table_rows,
    without_edits,
    without_scenario,
)
from capa_simulation.services.scenario_virtual_products import (
    inherit_virtual_product_records,
    virtual_product_records,
)
from capa_simulation.services.virtual_product import VirtualProductRecord
from capa_simulation.sidebar_status import keeps_app_run_open

CLONE_PIPELINE_VERSION = "duckdb-rq-snapshot-v3"
FLASH_KEY = "scenario_management_flash"
# 성공 알림과 함께 띄울 경고. 저장은 됐지만 남은 계산 오류가 있을 때 쓴다.
FLASH_WARNING_KEY = "scenario_management_flash_warning"
MODE_KEY = "scenario_page_mode"
CLONE_MODE = "복제"
# 복제 폼 원천 코드·원천명 칸의 풍선 — 두 칸이 빈 채로 서는 까닭과 새로 적어야 한다는 것. 원본
# 값으로 미리 채우지 않는 것은 결정이다(TODO 3장 화면 2026-10-22 — 원천명은 자동 갱신 주차 판정
# 근거). 늘 띄워 두지 않고 그 두 칸 곁 풍선에 둔다(설계 규칙 UI-TXT-01 · AMB-01 (가)) — 빈 칸을
# 남기고 누른 저장은 「필수 칸이 비어 있습니다」 가 그 자리에서 한 번에 알린다.
CLONE_SOURCE_NOTE = (
    "원천 시뮬레이션 코드·원천 시뮬레이션명은 새로 적는 필수 칸입니다 — 원천 시뮬레이션명은 "
    "공식버전 자동 갱신이 주차(W##)를 읽는 근거라 올라와 있는 시나리오의 값을 물려받지 않습니다."
)
MODES = (
    LIST_MODE,
    CLONE_MODE,
    "월 머지",
    "연도 Shift",
)
# 원본 리비전을 메모해 두는 모드와 그 역할(`scenario_transform.SOURCE_MEMO_KEY`).
DERIVED_SOURCE_ROLES: dict[str, tuple[str, ...]] = {
    "월 머지": MERGE_SOURCE_ROLES,
    "연도 Shift": SHIFT_SOURCE_ROLES,
}
# 오른쪽 칸 다섯. 라벨은 고정한다(수를 넣으면 위젯 id 가 흔들린다). 「점검」 은 고른 리비전의 입력
# 점검이다(2026-11-11 입력 점검 시안 보드 답 q1 — 「상세」 와 같은 리비전 고름).
SIDE_DETAIL = "상세"
SIDE_CHANGES = "저장 전 변경"
SIDE_HISTORY = "공식 이력"
SIDE_ARCHIVE = "보관함"
SIDES = (SIDE_DETAIL, SIDE_CHECK, SIDE_CHANGES, SIDE_HISTORY, SIDE_ARCHIVE)
SIDE_KEY = SIDE_CHOICE_KEY
# 「저장 전 변경」 칸 결과 · 오류 칸. 콜백이 적고 다음 회차에 그 칸 단추 바로 아래에 한 번 그린다 —
# 그 회차에 칸이 안 서면 맨 위 칸이 알림창 · Alarm 으로 낸다(`_notices_without_a_place`).
LIST_NOTICE_KEY = "scenario_list_notice"
DISCARD_LABEL = "모두 버리기"
DISCARD_POPOVER_KEY = "scenario_list_discard_v1"
DISCARD_CONFIRM_KEY = "scenario_list_discard_confirm_v1"
ACTION_KEY = "scenario_list_action"
ACTION_OWNER_KEY = "scenario_list_action_owner"
DELETE_CONFIRM_KEY = "scenario_list_delete_confirm"
# 영구 삭제 확인 칸을 다음 회차에 비우라는 표지. 삭제는 칸을 그린 **뒤**에 일어나 그 회차에는 칸을
# 바꿀 수 없고, 칸을 지우기(`pop`)만 하면 브라우저가 지운 이름을 계속 보인다. 다음 회차 칸 앞에서
# 빈 값을 적는다(AGENTS 9장 「pop 하지 말고 새 값을 적는다」).
DELETE_CLEAR_KEY = "scenario_list_delete_confirm_clear"
# 「영구 삭제 실행」 단추. 주 동작(청록 primary)처럼 보이지 않게 보조 단추에 빨간 글자로 둔다 —
# 빨간 글자는 이름을 맞게 적어 누를 수 있을 때만이다(잠긴 단추가 빨가면 누를 수 있는 것처럼 보인다).
# 라벨이 바뀌어도 같은 단추로 남게 key 를 준다.
DELETE_BUTTON_KEY = "scenario_list_delete_execute"
DELETE_BUTTON_LABEL = "영구 삭제 실행"
# 보관 확인 체크. 시나리오마다 따로 받는다(`archive_confirm_key`).
ARCHIVE_CONFIRM_KEY = "scenario_list_archive_confirm"
# 가상 제품이 든 리비전을 공식버전으로 지정할 때의 확인 체크. 리비전마다 따로 받는다
# (`official_confirm_key`).
OFFICIAL_CONFIRM_KEY = "scenario_list_official_virtual_confirm"
ARCHIVED_SELECT_KEY = "scenario_list_archived_id"
# 보관함 「되돌리기」·「영구 삭제 실행」 의 출발점 대조 저장 이름(`write_guard.save_once` — 출발점은
# 그 보관본 id). 겹쳐 온 둘째 누름은 저장소에 다시 가지 않고 첫 결과로 뒷정리·알림을 잇는다.
ARCHIVED_RESTORE_SAVE_NAME = "scenario_archived_restore"
ARCHIVED_DELETE_SAVE_NAME = "scenario_archived_delete"
# 카드 「보관 실행」 의 같은 저장 이름(출발점은 그 시나리오 id).
ARCHIVE_SAVE_NAME = "scenario_archive"
# 고른 보관본이 그 사이 보관함에서 빠진 회차의 누름에 내는 알림 — 아무것도 쓰지 않는다.
ARCHIVED_GONE_MESSAGE = (
    "고른 보관본이 그 사이 보관함에서 빠져 아무것도 바꾸지 않았습니다 — 목록으로 되돌렸거나 영구 "
    "삭제했습니다. 지금 고른 보관본을 확인한 뒤 다시 누르세요."
)
# 고른 시나리오가 그 사이 목록에서 빠진 회차의 「보관 실행」 에 내는 알림 — 아무것도 쓰지 않는다.
ARCHIVE_GONE_MESSAGE = (
    "고른 시나리오가 그 사이 목록에서 빠져 아무것도 바꾸지 않았습니다 — 보관했거나 영구 "
    "삭제했습니다."
)
# 「공식 이력」 칸에 보이는 최근 건수.
HISTORY_LIMIT = 20
# 「공식 이력」 표 칸 폭(px)과 시각 꼴(`_short_time` 과 같은 글자). 앞 네 칸의 합이 옆 칸 처음 폭
# 안에 들어 「지정시각」 이 기준 창에서 보인다 — 시나리오 칸이 줄고 공식버전명은 남는 폭을 쓴다.
HISTORY_VERSION_WIDTH_PX = 66
HISTORY_SCENARIO_WIDTH_PX = 96
HISTORY_REVISION_WIDTH_PX = 54
HISTORY_TIME_WIDTH_PX = 112
HISTORY_TIME_FORMAT = "YY.MM.DD HH:mm"
# 복제 폼 입력칸의 세대. 저장에 성공하면 올라 다음 회차에 빈 폼으로 선다(`clone_field_key`).
CLONE_FORM_GENERATION_KEY = "scenario_create_form_generation"
# 복제 폼 「초기 리비전명」 칸이 새로 설 때 든 값.
CLONE_REVISION_NAME_DEFAULT = "초기 리비전"
# 「상세」 칸 작업 줄 아래 결과 · 오류 칸(종류, 글).
CARD_NOTICE_KEY = "scenario_card_notice"
# 카드 단추 key 앞머리. 뒤에 그린 회차의 시나리오 id 를 싣는다 — 다른 줄을 연 회차가 서버에서 끝난
# 뒤 브라우저의 옛 카드 단추에 닿은 누름은 옛 key 의 콜백으로 돌아 옛 시나리오를 인자로 받는다(고정
# key 면 새 시나리오 인자로 돌아 대조를 지나 그 시나리오를 올린다).
CARD_LOAD_KEY = "scenario_card_load"
CARD_OFFICIAL_KEY = "scenario_list_action_official"
# 목록·카드 결과 칸의 종류별 아이콘(`_notify`). 안내(info)는 아이콘이 없다.
_NOTICE_ICONS: dict[str, str] = {"success": ":material/check_circle:", "error": ":material/block:"}
# 미저장 편집이 있을 때 불러오기 전에 받는 「변경을 버리고 불러오기」 체크.
DISCARD_UNSAVED_KEY = "scenario_discard_unsaved_changes"
# 리비전 표에 씨앗으로 고른 올라와 있는 리비전 id. 올라와 있는 리비전이 이것과 달라지면(사이드바
# 시나리오 팝업의 불러오기·저장) 표의 고름을 새 리비전으로 옮긴다 — 팝업의 불러오기는 프래그먼트
# 실행이라 이 페이지의 위젯 값이 버려지지 않아, 처음에만 넣던 씨앗이 옛 리비전을 고른 채 남았다
# (2026-10-11 병합 전 리뷰 — 「불러오기」·「공식버전 지정」이 엉뚱한 리비전에 걸렸다).
REVISION_SEED_KEY = "scenario_list_revision_seed"
# 공식버전 지정 확인 팝업의 열림 칸 — (시나리오 id, 리비전 id). `PAGE_DIALOG_SUFFIX` 로 끝나
# 페이지를 떠나면 비워지고, 여는 콜백이 다른 팝업 칸부터 비운다(한 실행에 팝업 하나).
OFFICIAL_DIALOG_KEY = f"scenario_official{PAGE_DIALOG_SUFFIX}"
# 그 팝업을 여닫는 호스트 프래그먼트(`components/dialog_host.py` — 열기 · 닫기가 페이지를 다시
# 계산하지 않는다). 「Capa 시나리오」 탭을 그리는 매 앱 전체 회차 끝에 선다
# (`_render_official_host`).
OFFICIAL_HOST = DialogHost("scenario_official_dialog_host", OFFICIAL_DIALOG_KEY)
# 팝업의 공식버전명 · 메모 칸 — 닫으면 호스트가 값을 지운다(`OFFICIAL_HOST.render(widget_keys=)`).
OFFICIAL_NAME_KEY = "scenario_official_release_name"
OFFICIAL_NOTE_KEY = "scenario_official_release_note"
# 팝업이 이번 열림에서 마지막으로 읽어 그린 대상(`_OfficialView`). 여는 콜백과 닫기가 비운다 — 비어
# 있으면 이번 열림의 첫 회차다. 다시 읽지 못한 회차(파일 잠금 따위)는 이것으로 팝업과 친 글을
# 지킨다(`_official_dialog`).
OFFICIAL_VIEW_KEY = "scenario_official_view"
# 다시 읽지 못한 회차의 거부를 팝업 안에서 알림창 · Alarm 으로 내는 칸.
OFFICIAL_UNREAD_KEY = "scenario_official_unread"
# 공식버전 지정 팝업이 지정 단추를 누르지 않은 회차에 보인 「지금 공식」 번호(없으면 0) — 지정이
# 저장소에 넘기는 대조 값이다(`write_guard.remember_seen`). 제출 회차에 다시 읽은 번호를 넘기면 첫
# 지정 뒤의 빠른 둘째 누름이 그 번호로 대조를 지나 공식을 한 번 더 세운다.
OFFICIAL_SEEN_KEY = "scenario_official_seen_release_no"
# 공식 지정 · 이름 쓰기의 제 저장 표지 이름(`write_guard.own_save_marks`). 이름은 줄마다
# `<이름>:<줄 id>` 다.
OFFICIAL_SAVE_NAME = "scenario_official_release"
REVISION_NAME_SAVE_NAME = "scenario_revision_name"
SCENARIO_NAME_SAVE_NAME = "scenario_name"
# 「공식버전 지정」 팝업에서 고른 리비전이 지금 공식일 때의 값 표지와, 그래도 지정되는 뜻을 말하는
# 지정 단추 풍선(설계 규칙 UI-TXT-04 — 검수표 11/02 equip-41 과 같은 기준).
SAME_AS_OFFICIAL_LINE = ":material/verified: 지금 공식과 같은 리비전"
SAME_AS_OFFICIAL_HELP = (
    "지금 공식과 같은 리비전입니다 — 지정하면 같은 리비전에 새 공식 번호가 섭니다."
)
# 잠긴 단추의 까닭 풍선 — 잠긴 동안만 단다(설계 규칙 UI-INP-07).
REVISION_PICK_HELP = "리비전 표에서 리비전을 고르면 풀립니다."
DISCARD_LOCK_HELP = "위 「변경을 버리고 불러오기」 를 체크하면 풀립니다."
OFFICIAL_CONFIRM_HELP = "위 「가상 제품이 포함된 것을 확인했습니다」 를 체크하면 풀립니다."
ARCHIVE_EFFECT_HELP = "보관하면 목록에서 숨겨지고 새 리비전 저장·공식버전 지정이 막힙니다."
ARCHIVE_LOCK_HELP = f"위 확인을 체크하면 풀립니다. {ARCHIVE_EFFECT_HELP}"
DELETE_LOCK_HELP = "위 칸에 시나리오 이름을 그대로 입력하면 풀립니다."
# 「변경 저장」 의 출발점 대조 저장 이름(`write_guard.save_once` — 출발점은 저장본에 맞추기 전
# 초안의 이름 · 순서 고침과 순서의 본 차례).
LIST_SAVE_NAME = "scenario_list_edits"
# 막힘 판정이 저장소와 같은 글을 쓰게 넘긴다(`services` 는 저장소를 부르지 않는다).
LIST_RULES = ListRules(
    duplicate=DUPLICATE_SCENARIO_NAME_MESSAGE,
    order=SCENARIO_LIST_MOVED_MESSAGE,
    moved=name_moved_message,
    empty=lambda label: f"{with_topic_particle(label)} 비어 있을 수 없습니다.",
)
# 왼쪽 줄을 누르고 바로 옛 카드 단추를 누른 꼴 — 아무것도 하지 않는다.
OPENED_MOVED_MESSAGE = "고른 시나리오가 바뀌어 하지 않았습니다 — 지금 연 시나리오를 확인하세요."
# 공식 지정 팝업을 그린 뒤 그 시나리오가 영구 삭제돼 지정하지 않은 까닭 — 그 사이 보관된 것의 저장소
# 거부(「보관된 시나리오는 …」)와 같이 알림창 · Alarm 에 낸다(검수 보드 sc-purged).
OFFICIAL_PURGED_MESSAGE = (
    "팝업을 연 사이 그 시나리오가 영구 삭제돼 공식버전으로 지정하지 않았습니다."
)
# 저장 · 모두 버리기 사이에 고친 것(옛 세대) · 다른 곳에서 차례가 바뀐 뒤의 옮기기.
OUTBOX_LIMIT = 2000
ORDER_MOVED_NOTICE = "목록 차례가 바뀌어 그 옮기기는 반영하지 않았습니다."


def render_scenario_management(
    repository: DuckDBScenarioRepository,
    database_path: str,
    *,
    alert_tab: str | None = "",
) -> None:
    """「Capa 시나리오」 탭 본문. `alert_tab` 은 이 탭 이름(상태 알림 `SC-01` 의 「그 화면으로」 —
    `state_alerts.open_tab_name`)이고 None 이면 닫힌 탭이라 그 회차에는 알리지 않는다."""
    # 저장소 생성자는 프로세스 캐시라 따뜻한 프로세스에서는 페이지 준비 단계가 DB 를 열지 않는다.
    # 이 읽기가 그 회차의 첫 DB 열기이므로 다른 프로그램의 파일 잠금도 여기서 안내로 받는다.
    try:
        scenarios = repository.list_scenarios()
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(bootstrap_error_message(exc), code="SC-02", tab=CAPA_SCENARIO_TAB_NAME)
        _render_official_host(database_path, official_open=False)
        return
    # 작업 이름이 바뀌었으므로 예전 세션에 남은 값은 위젯이 만들어지기 전에 버린다.
    # 옵션에 없는 값이 그대로 오면 Streamlit 이 선택을 잃고 필수 선택에서 막힌다.
    if st.session_state.get(MODE_KEY) not in MODES:
        st.session_state.pop(MODE_KEY, None)
    list_mode = st.session_state.get(MODE_KEY, MODES[0]) == MODES[0]
    # 맨 위 알림 **앞에서** 접고 맞춘다 — 사라진 고침의 알림이 그 회차에 뜬다.
    view = _settle_list_draft(repository, scenarios) if list_mode else None
    # 알림은 늘 서 있는 한 칸 안에 그린다(AGENTS 9장 「key 가 있어도 자리는 고정한다」). 형제
    # 자리에 바로 그리면 알림이 생기는 회차에 그 아래가 한 칸 밀린다 — 보관함의 「되돌리기」·
    # 「영구 삭제」는 본문에서 `st.rerun()` 으로 회차를 끊으므로, 끊긴 회차의 key 있는 보관함
    # 상자가 옛 자리에 흐린 사본으로 남아 모드를 바꿔도 새로고침 전까지 따라왔다(2026-10-22 사본
    # 앱 이분 탐색 — 알림을 빼거나 상자 key 를 빼거나 되돌리기를 콜백으로 바꾸면 각각 사라졌다).
    render_flash(FLASH_KEY, FLASH_WARNING_KEY, *_notices_without_a_place(list_mode))
    _report_missing_official(repository, alert_tab, active_count=len(scenarios))
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        mode = st.segmented_control(
            "시나리오 작업",
            list(MODES),
            default=MODES[0],
            key=MODE_KEY,
            persist_state="session",
            # 선택 해제를 허용하면 mode 가 None 이 되어 아무 작업도 그리지 않는다.
            required=True,
            # 보이는 글 없이 탭 바로 아래에 선다 — 라벨은 보조 기술이 읽는 이름으로 남는다.
            label_visibility="collapsed",
        )
        # 수가 0 이면 알약이 없다 — 늘 서 있는 칸 안에 둔다(이 줄의 자리는 그대로).
        with st.container():
            if view is not None and view.pending:
                st.badge(
                    f"저장 전 변경 {view.pending:,}건", icon=":material/edit_note:", color="orange"
                )
        # 복제할 때 무엇을 복제하는지는 이 줄 오른쪽 끝 작은 값 글이다 — 폼 위에 따로 줄을 세우지
        # 않는다(2026-11-09 사용자 보드 T2, 설계 규칙 UI-TXT-04 · UI-LAY-11). 곁에 자리가 모자라면
        # 통째로 다음 줄 오른쪽 끝으로 내려간다(2026-11-11 보드 D1 · UI-ACC-02). 다른 작업에서는
        # 그리지 않는다.
        render_row_value(clone_target_caption() if mode == CLONE_MODE else None, place="push")
    # 새 리비전 저장은 사이드바 시나리오 팝업 한 곳이다(2026-10-22 사용자 결정 S8). 그리로 가는 길
    # 안내 글은 늘 띄워 두지 않는다(설계 규칙 UI-TXT-03 · AMB-06 (나)).
    # 월 머지·연도 Shift 가 메모한 원본(리비전 하나 크기의 살아 있는 표)은 그 모드에서만 둔다.
    forget_derived_sources(keep=DERIVED_SOURCE_ROLES.get(str(mode), ()))
    official_open = False
    if mode == LIST_MODE:
        official_open = _render_list_management(
            repository, database_path, scenarios, _list_view(view), counting=alert_tab is not None
        )
    elif mode == CLONE_MODE:
        _render_clone(repository)
    elif mode == "월 머지":
        render_scenario_month_merge(repository, database_path)
    elif mode == "연도 Shift":
        render_scenario_year_shift(repository, database_path)
    _render_official_host(database_path, official_open=official_open)


def _render_official_host(database_path: str, *, official_open: bool) -> None:
    """공식버전 지정 팝업의 호스트 — 이 탭을 그리는 매 앱 전체 회차 끝에 한 번(이벤트 칸 늘 한
    자리).

    `official_open` 은 이 회차 「상세」 칸이 열림 칸의 시나리오 · 리비전을 그렸는지(「점검」 칸이면
    그 「넓게 보기」 단추를 그렸는지)다 — 아니면(다른 작업 · 다른 칸 · 그 사이 빠진 줄) 열림 칸을
    비우고 팝업을 걷는다. 호스트 하나를 두 팝업이 함께 쓰고 열림 값의 꼴로 가른다. 호스트만 도는
    여닫는 회차는 이 함수를 거치지 않는다 — 열림 값은 여는 콜백이 지금 연 줄로 적었고, 팝업 본문이
    저장값을 다시 읽는다(`_official_dialog`).
    """
    if not official_open:
        st.session_state.pop(OFFICIAL_DIALOG_KEY, None)
    OFFICIAL_HOST.render(
        partial(_pick_official_dialog, database_path), widget_keys=_official_widget_keys
    )


def _pick_official_dialog(database_path: str, value: object) -> DialogBody | None:
    """열림 값 (시나리오 id, 리비전 id) → 공식 지정 팝업, 「넓게 보기」 꼴(`wide_target`) → 그
    팝업. 꼴이 다르면 None(빈 자리)."""
    wide = wide_target(value)
    if wide is not None:
        return partial(_wide_dialog, database_path, wide)
    if not (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(part, str) for part in value)
    ):
        return None
    return partial(_official_dialog, database_path, value[0], value[1])


def _official_widget_keys(value: object) -> tuple[str, ...]:
    """팝업의 입력 위젯 — 가상 제품 확인 체크(리비전마다) · 공식버전명 · 메모. 「넓게 보기」 는
    입력 위젯이 없다."""
    if wide_target(value) is not None:
        return ()
    keys = (OFFICIAL_NAME_KEY, OFFICIAL_NOTE_KEY)
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], str):
        return (official_confirm_key(value[1]), *keys)
    return keys


def _report_missing_official(
    repository: DuckDBScenarioRepository, alert_tab: str | None, *, active_count: int
) -> None:
    """공식버전이 없는 것은 상태 알림(`SC-01` — 알림창 · Alarm)이다. 있어도 부른다(해소) — 닫힌
    탭이면 알리지 않고 읽지도 않는다.

    시나리오가 보관본만 남았으면 목록에 고를 것이 없다 — 그 상태만 글을 갈라 보관함의 「되돌리기」
    를 가리킨다(검수 보드 st-sc01 — 작은 결정 a8 과 같은 꼴). 그 판정의 보관본 읽기는 공식버전이
    없고 활성 시나리오가 0건(`active_count`)일 때만 한다. 내용 값이 갈라 바뀌면 그 줄도 새로
    뜬다(지문)."""
    if alert_tab is None:
        return
    official = repository.latest_official_release()
    archived_only = (
        official is None
        and active_count == 0
        and bool(repository.list_scenarios(include_archived=True))
    )
    if archived_only:
        text = "공식버전이 없습니다 — 보관본만 있음 · 목록 관리 「보관함」 › 「되돌리기」"
        full = (
            "공식버전이 없고 보관본만 있어 지정할 시나리오가 없습니다 — 시나리오 관리 › Capa "
            "시나리오 › 목록 관리의 「보관함」 에서 「되돌리기」 한 뒤 「공식으로 지정…」 으로 "
            "리비전 하나를 공식으로 정하세요."
        )
    else:
        text = "공식버전이 없습니다 — 새 세션이 불러올 기준 없음 · 목록 관리 「공식으로 지정…」"
        full = (
            "공식버전이 없습니다. 새 웹 세션에서 자동으로 불러올 기준이 없습니다 — 시나리오 관리 › "
            "Capa 시나리오 › 목록 관리에서 시나리오를 고르고 「공식으로 지정…」 으로 리비전 하나를 "
            "공식으로 정하세요."
        )
    alerts.state(
        "SC-01",
        scope=None,
        content=("archived_only" if archived_only else True) if official is None else None,
        active=official is None,
        text=text,
        full=full,
        tab=alert_tab,
    )


@dataclass(frozen=True)
class _ListView:
    """그 회차 목록 관리의 재료 — 맞춘 초안 · 저장본 · 공식 발행 이력 · 막힘."""

    draft: ListDraft
    saved: SavedList
    releases: Sequence[OfficialReleaseSummary]
    problems: ListProblems
    counts: ChangeCounts

    @property
    def pending(self) -> int:
        """배지 「저장 전 변경 n건」 — 「저장 전 변경」 칸의 수 셋을 더한다(순서는 옮긴 줄 수)."""
        return self.counts.scenario + self.counts.order + self.counts.revision


def _list_view(view: _ListView | None) -> _ListView:
    """위젯 값이 머리에서 읽은 값과 다를 수는 없다 — 「목록 관리」 회차면 머리가 이미 세웠다."""
    if view is None:
        raise RuntimeError("목록 관리 회차인데 초안을 세우지 않았습니다.")
    return view


def _side_now() -> object:
    """이 회차에 설 오른쪽 칸 — 받기 콜백이 고른 칸이 먼저다."""
    chosen = st.session_state.get(SIDE_NEXT_KEY)
    if chosen in SIDES:
        return chosen
    current = st.session_state.get(SIDE_KEY)
    return current if current in SIDES else SIDE_DETAIL


def _notices_without_a_place(list_mode: bool) -> tuple[str, ...]:
    """이 회차에 자기 칸이 안 서는 결과 알림 키 — 맨 위 칸이 알림창 · Alarm 으로 꺼낸다.

    `render_flash` 는 부른 회차에만 꺼낸다. 칸이 안 서면 담아 둔 글이 그 칸을 다시 열 때까지 잠자다
    새 알림처럼 뜨고, 「변경 저장」 거부를 저장된 줄로 믿게 된다(사라진 위젯의 콜백도 돈다).
    """
    side = _side_now()
    keys = []
    if not list_mode or side != SIDE_CHANGES:
        keys.append(LIST_NOTICE_KEY)
    if not list_mode or side != SIDE_DETAIL:
        keys.append(CARD_NOTICE_KEY)
    if not list_mode or side != SIDE_CHECK:
        keys.append(CHECK_NOTICE_KEY)
    for key in keys:
        send_to_popup(key)
    return tuple(keys)


def _warn_list(message: str) -> None:
    """동작은 끝났고 그 자리에 고칠 입력이 없는 경고 — 알림창 · Alarm 에만 낸다."""
    queue_flash(
        FLASH_WARNING_KEY, message, kind="warning", icon=":material/warning:", popup_only=True
    )


def _warn_gone(count: int) -> None:
    """맞추기가 뺀 사라진 줄의 고침 — 본문 맞추기 · 저장 콜백 어느 쪽에서 빠져도 같은 글이다."""
    _warn_list(f"그 사이 보관 · 삭제된 시나리오의 고침 {count:,}건을 버렸습니다.")


def _fold_outboxes() -> ListDraft:
    """세 마운트의 출납을 초안에 접어 적는다. 받기 콜백 · 단추 콜백 · 본문 머리가 모두 부른다 — 어느
    쪽이 먼저 돌아도 같고(`applied`), 콜백이 끊겨도 본문이 잇는다."""
    from capa_simulation.components.scenario_list_grid import LIST_SIDE
    from capa_simulation.components.side_panel import switch_side

    draft = load_draft()
    result = fold_ops(draft, [outbox_value(key) for key in MOUNT_KEYS], shown_order())
    if result.draft != draft:
        store_draft(result.draft)
    notes = []
    if result.dropped:
        notes.append(f"저장 사이에 고친 {result.dropped:,}건은 반영하지 않았습니다.")
    if result.order_refused:
        notes.append(ORDER_MOVED_NOTICE)
    if notes:
        _warn_list(" ".join(notes))
    if result.opened:
        # 「저장 전 변경」 · 「점검」 을 보며 다른 줄을 연다 — 그 칸을 둔다(점검은 다른 시나리오의
        # 리비전을 이어 본다 — 결정 16). 「저장 전 변경」 칸 안 이름 누름만 「상세」 로 돌린다.
        current = st.session_state.get(SIDE_KEY)
        keep = current in (SIDE_CHANGES, SIDE_CHECK) and not result.to_detail
        switch_side(LIST_SIDE, str(current) if keep else SIDE_DETAIL)
    return result.draft


def _read_saved(
    repository: DuckDBScenarioRepository,
    scenarios: Sequence[ScenarioSummary],
    releases: Sequence[OfficialReleaseSummary],
    draft: ListDraft,
) -> SavedList:
    """지금 저장본 — 고친 것이 있을 때만 더 읽는다(보관본 포함 이름 · 고친 리비전의 지금 값)."""
    names = {item.scenario_id: item.scenario_name for item in scenarios}
    all_names = (
        {
            item.scenario_id: item.scenario_name
            for item in repository.list_scenarios(include_archived=True)
        }
        if draft.scenarios
        else dict(names)
    )
    release_by_revision: dict[str, int] = {}
    for release in releases:
        release_by_revision.setdefault(release.revision_id, release.release_no)
    revisions = {
        revision_id: SavedRevision(
            revision_id,
            summary.revision_no,
            summary.revision_name,
            summary.scenario_id,
            active=status == "ACTIVE" and summary.scenario_id in names,
            release_no=release_by_revision.get(revision_id),
        )
        for revision_id, (summary, status) in repository.list_revisions_by_ids(
            list(draft.revisions)
        ).items()
    }
    return SavedList(
        order=tuple(item.scenario_id for item in scenarios),
        names=names,
        all_names=all_names,
        revisions=revisions,
    )


def _settle_list_draft(
    repository: DuckDBScenarioRepository, scenarios: Sequence[ScenarioSummary]
) -> _ListView:
    """목록 관리 회차 머리 — 출납을 접고 지금 저장본에 맞춘다. 맨 위 알림 앞에서 돈다.

    이번에 그릴 저장 차례를 적어 다음 회차의 `move` 가 지문을 대조한다. 끊긴 첫 저장(이름은 이미
    쓰였는데 초안을 비우기 전에 끊김)의 뒷정리는 여기서도 잇는다.
    """
    draft = _fold_outboxes()
    remember_shown_order(tuple(item.scenario_id for item in scenarios))
    releases = repository.list_official_releases()
    saved = _read_saved(repository, scenarios, releases, draft)
    fitted = reconcile(draft, saved, preferred_open=active_persisted_scenario_id())
    if fitted.gone:
        _warn_gone(fitted.gone)
    own = _own_settled(fitted, own_save_marks())
    if own:
        _after_list_save(SavePlan(settled=own))
    settled = (
        _aim_at_check_target(fitted.draft, saved) if _side_now() == SIDE_CHECK else fitted.draft
    )
    if settled != draft:
        store_draft(settled)
    problems = list_problems(settled, saved, LIST_RULES)
    counts = change_counts(settled, saved, problems)
    return _ListView(settled, saved, releases, problems, counts)


def _aim_at_check_target(draft: ListDraft, saved: SavedList) -> ListDraft:
    """「점검」 칸이 서는 회차에 저장 · 지정 · 복제 · 자동 갱신 경고 줄의 「그 화면으로」 를 누른
    리비전을 고른다(`required_exclusion_notice.required_check_target` — 2026-11-11 입력 점검 검토
    보드 F4 (나) · 다음 배포 물음 보드 F4 뒤 (a)).

    대상은 경고 줄이 들고 다니다 알림 칸이 탭 길(목록 관리 › 「점검」)을 다 연 뒤에만 보내므로
    (`alert_center._on_goto` → `scenario_list_state.queue_check_target`) 같은 줄을 다시 누르면 다시,
    앞 경고 줄을 누르면 그 줄의 리비전을 고르고, 누르지 않고 손으로 연 「점검」 칸에는 꺼낼 것이
    없다. 적어 둔 것은 한 번만 쓴다 — 고른 뒤에는 사용자가 고른 줄이 이긴다. 다른 칸(상세 · 저장 전
    변경 따위)이 서는 회차에는 꺼내지 않고, 그 회차가 끝나도 남은 것은 다음 앱 전체 회차에
    버려진다(`scenario_list_state.expire_check_target`).
    그 사이 보관 · 삭제된 시나리오면 조용히 버리고, 지운 리비전이면 고름 씨앗이 다시 고른다. 연
    시나리오가 바뀌면 상세 칸 작업 칸 · 확인 체크를 버리는 것은 `_opened_revisions` 처음 보기와
    같다. 고름 씨앗(`REVISION_SEED_KEY`)은 올라와 있는 리비전으로 맞춰 다음 회차의 씨앗이 적어 둔
    리비전을 덮지 않게 한다. 오른쪽 칸이 접혀 있었으면 편다(`switch_side` — 줄을 열 때와 같은 길).
    알림 칸은 접힌 칸의 숨은 「점검」 단추도 누르므로, 펴지 않으면 그 칸을 고른 채 접힌 채로 남는다.
    """
    from capa_simulation.components.scenario_list_grid import LIST_SIDE
    from capa_simulation.components.side_panel import switch_side

    target = take_check_target()
    if target is None:
        return draft
    scenario_id, revision_id = target
    if scenario_id not in saved.names:
        return draft
    switch_side(LIST_SIDE, SIDE_CHECK)
    if st.session_state.get(ACTION_OWNER_KEY) != scenario_id:
        st.session_state[ACTION_OWNER_KEY] = scenario_id
        for key in (ACTION_KEY, DELETE_CONFIRM_KEY, archive_confirm_key(scenario_id)):
            st.session_state.pop(key, None)
    if scenario_id == active_persisted_scenario_id():
        st.session_state[REVISION_SEED_KEY] = active_persisted_revision_id()
    else:
        st.session_state.pop(REVISION_SEED_KEY, None)
    return replace(draft, opened=scenario_id, picked=revision_id)


def _on_list_outbox() -> None:
    """받기 콜백(본문보다 먼저 돈다). 세 마운트가 함께 보낼 수 있어 한 번에 접는다."""
    _fold_outboxes()


def _list_common(draft: ListDraft, key: str) -> dict[str, Any]:
    """세 마운트 data 공통 — 세대 · 그 마운트가 보낸 op 가운데 반영한 마지막 seq · 보낼 목록
    상한."""
    common: dict[str, Any] = {"base": draft_base(draft), "limits": {"outboxCells": OUTBOX_LIMIT}}
    mount = outbox_mount(outbox_value(key))
    if mount:
        common["ack"] = {"mount": mount, "seq": int(draft.applied.get(mount, 0))}
    return common


def _short_time(value: datetime) -> str:
    """표 날짜 꼴 — 해가 바뀌어도 줄을 가른다."""
    return value.strftime("%y.%m.%d %H:%M")


def _scenario_facts(
    scenarios: Sequence[ScenarioSummary], releases: Sequence[OfficialReleaseSummary]
) -> dict[str, ScenarioFacts]:
    """목록 표 값 칸. 「최신」 은 그 시나리오에 마지막으로 저장한 리비전이다 — 이 세션에 올라와 있는
    리비전은 사이드바 시나리오 칸과 리비전 표 상태 칸이 말한다. 「활성 리비전」 이라 부르던 때는 그
    둘이 같은 것으로 읽혀, 「r5 | v5 · 최신」 이 r5 를 공식으로 오독하게 했다. 그래서 공식 칸에
    공식 리비전 번호를 함께 적는다(`official_label`)."""
    # 발행 이력은 최신 번호가 먼저 온다. 시나리오마다 첫 번째가 그 시나리오의 최신 공식이다.
    official: dict[str, tuple[int, int]] = {}
    for release in releases:
        official.setdefault(release.scenario_id, (release.release_no, release.revision_no))
    latest = releases[0].scenario_id if releases else None
    return {
        item.scenario_id: ScenarioFacts(
            source_code=item.source_simulation_code,
            latest=f"r{item.active_revision_no}",
            official=official_label(item.scenario_id, official, latest),
            updated=_short_time(item.updated_at),
        )
        for item in scenarios
    }


def _render_list_management(
    repository: DuckDBScenarioRepository,
    database_path: str,
    scenarios: Sequence[ScenarioSummary],
    view: _ListView,
    *,
    counting: bool,
) -> bool:
    """목록 관리 두 칸 — 왼쪽 시나리오 표, 오른쪽 칸(상세 · 점검 · 저장 전 변경 · 공식 이력 ·
    보관함). 「상세」 칸이 공식 지정 팝업의 시나리오 · 리비전을, 「점검」 칸이 열린 「넓게 보기」 의
    단추를 그렸으면 `True`(그 팝업이 열려 있어도 된다).

    Capa 탭은 다른 탭이 열린 회차에도 그린다(폼 · 보관함 입력을 잃지 않는다) — 표 data 가 그대로면
    브라우저로 다시 보내지 않아 그 회차 비용은 줄 조립뿐이다. `counting` 은 이 탭이 열린 회차인가다
    — 닫힌 회차의 「점검」 칸은 전체 기간 계산을 돌리지 않는다.
    """
    from capa_simulation.components.scenario_list_grid import LIST_SIDE, render_list_mount
    from capa_simulation.components.side_panel import render_side_head, split_frame

    left, right = split_frame(LIST_SIDE)
    with left:
        if scenarios:
            render_list_mount(
                TABLE_KEY,
                {
                    **_list_common(view.draft, TABLE_KEY),
                    **scenarios_payload(
                        view.draft,
                        view.saved,
                        view.problems,
                        _scenario_facts(scenarios, view.releases),
                    ),
                    "side": {"choice": LIST_SIDE.choice_key, "body": LIST_SIDE.body_key},
                },
                on_outbox=_on_list_outbox,
            )
        else:
            # 빈 결과는 값이다 — 평문 한 줄만 두고 하는 법은 붙이지 않는다(설계 규칙 AMB-02 (가)).
            st.caption("저장된 시나리오가 없습니다.")
    with right:
        side, body = render_side_head(LIST_SIDE, SIDES, SIDE_DETAIL)
    official_open = False
    with body:
        if side == SIDE_DETAIL:
            official_open = _render_detail(repository, database_path, scenarios, view)
        elif side == SIDE_CHECK:
            drawn = _render_check(repository, database_path, scenarios, view, counting=counting)
            official_open = st.session_state.get(OFFICIAL_DIALOG_KEY) in drawn
        elif side == SIDE_CHANGES:
            _render_changes(database_path, view)
        elif side == SIDE_HISTORY:
            _render_official_history(view.releases)
        elif side == SIDE_ARCHIVE:
            _render_archived_scenarios(repository)
    return official_open


def _render_check(
    repository: DuckDBScenarioRepository,
    database_path: str,
    scenarios: Sequence[ScenarioSummary],
    view: _ListView,
    *,
    counting: bool,
) -> WideValues:
    """「점검」 칸 — 연 시나리오의 리비전 표(r · 리비전명 · 계산)와 고른 리비전의 입력 점검
    (`components/scenario_input_check.py`). 고름 · 씨앗은 「상세」 칸과 같다(`_opened_revisions`).
    그린 「넓게 보기」 단추의 열림 값을 돌려준다."""
    opened = _opened_revisions(repository, scenarios, view)
    if opened is None:
        return ()
    summary, revisions, draft = opened
    return render_input_check_panel(
        database_path,
        summary,
        revisions,
        draft,
        facts=_revision_facts(repository, revisions, view.releases),
        mount_data=_list_common(draft, CHECKS_KEY),
        on_outbox=_on_list_outbox,
        fold=_fold_outboxes,
        open_wide=OFFICIAL_HOST.open,
        counting=counting,
    )


def _opened_revisions(
    repository: DuckDBScenarioRepository,
    scenarios: Sequence[ScenarioSummary],
    view: _ListView,
) -> tuple[ScenarioSummary, list[RevisionSummary], ListDraft] | None:
    """「상세」 · 「점검」 칸이 함께 쓰는 머리 — 연 시나리오, 그 리비전, 고름을 씨앗 규칙으로 맞춘
    초안. 연 시나리오가 없으면 None.

    연 시나리오가 바뀌면 열려 있던 작업 칸 · 확인 체크를 버린다. 고른 리비전은 씨앗 규칙이 다시
    고른다(`_seed_revision_pick`). 리비전명 고침은 리비전 id 로 초안에 남는다. 두 칸이 같은 기록
    칸(`ACTION_OWNER_KEY` · `REVISION_SEED_KEY`)을 써서 한 칸에서 고른 리비전이 다른 칸으로 옮겨도
    다시 씨앗을 넣지 않는다.
    """
    draft = view.draft
    summary = next((item for item in scenarios if item.scenario_id == draft.opened), None)
    if summary is None:
        return None
    first_view = st.session_state.get(ACTION_OWNER_KEY) != summary.scenario_id
    if first_view:
        st.session_state[ACTION_OWNER_KEY] = summary.scenario_id
        for key in (
            ACTION_KEY,
            DELETE_CONFIRM_KEY,
            archive_confirm_key(summary.scenario_id),
            REVISION_SEED_KEY,
        ):
            st.session_state.pop(key, None)
    revisions = repository.list_revisions(summary.scenario_id)
    revision_ids = [revision.revision_id for revision in revisions]
    picked_id = _seed_revision_pick(summary, draft.picked, revision_ids, first_view)
    if picked_id != draft.picked:
        draft = replace(draft, picked=picked_id)
        store_draft(draft)
    return summary, revisions, draft


def _render_changes(database_path: str, view: _ListView) -> None:
    """「저장 전 변경」 — 수 넷 · 옛 값 → 새 값 · 줄 되돌리기, 그 아래 저장 구획 한 곳(설계 규칙
    UI-LAY-03). 「변경 저장」 은 잠그지 않는다 — 출납이 300ms 묶음이라 마지막 회차의 판정은
    브라우저보다 늦다(UI-INP-07). 콜백이 출납을 먼저 접은 뒤 판정해 단추 바로 아래에 알린다."""
    from capa_simulation.components.scenario_list_grid import render_list_mount

    base = draft_base(view.draft)
    render_list_mount(
        CHANGES_KEY,
        {
            **_list_common(view.draft, CHANGES_KEY),
            **changes_payload(
                view.draft,
                view.saved,
                view.problems,
                view.counts,
            ),
        },
        on_outbox=_on_list_outbox,
    )
    with st.container(horizontal=True, gap="small"):
        discard_popover(
            label=DISCARD_LABEL,
            popover_key=DISCARD_POPOVER_KEY,
            confirm_key=DISCARD_CONFIRM_KEY,
            note="저장하지 않은 이름 · 순서 고침을 모두 버립니다 — 되돌릴 수 없습니다.",
            on_confirm=_discard_all,
            args=(base,),
        )
        st.button(
            "변경 저장",
            icon=":material/save:",
            type="primary",
            key="scenario_list_save",
            on_click=_save_list_edits,
            args=(database_path, base),
        )
    render_flash(LIST_NOTICE_KEY)


def _discard_all(drawn_base: str) -> None:
    """「모두 버리기」 확인 — 이름 · 순서 고침을 비우고 세대를 올린다. 연 시나리오 · 고름은 남는다.

    둘째 누름은 세대가 달라 끝난다. 알림은 표지(`note_notice`)로 그 회차에도 남는다. 버릴 것이
    없으면 세대를 올리지 않는다 — 올리면 막 보내던 고침이 옛 세대로 버려진다. 팝오버를 잠그지 않는
    것은 「변경 저장」 과 같다(`_render_changes`).
    """
    notices = notice_marks()
    draft = _fold_outboxes()
    if draft_base(draft) != drawn_base:
        return
    if not has_edits(draft):
        if held_notice(LIST_NOTICE_KEY) is None:
            _notify(LIST_NOTICE_KEY, "info", "버릴 것이 없습니다.")
        return
    message = "저장하지 않은 이름 · 순서 고침을 모두 버렸습니다."
    note_notice(notices, LIST_NOTICE_KEY, message, kind="info")
    store_draft(cleared(draft))
    _notify(LIST_NOTICE_KEY, "info", message)


def _notify(key: str, kind: FlashKind, text: str) -> None:
    """목록·카드 결과 칸(`LIST_NOTICE_KEY`·`CARD_NOTICE_KEY`)에 콜백의 결과·오류를 담는다.

    다음 회차에 그 칸의 `render_flash` 가 늘 서 있는 한 칸 안에 한 번 그린다. 성공은 체크, 오류는
    막힘 아이콘이다.
    """
    queue_flash(key, text, kind=kind, icon=_NOTICE_ICONS.get(kind))


def _note_saved(notices: dict[str, NoticeMark], key: str, text: str) -> None:
    """쓰기에 성공한 바로 뒤 그 성공 알림을 알림 표지에 적는다(`write_guard.note_notice` — 쓰기 전에
    받아 둔 dict 라 끊기지 않는다).

    「변경 저장」 을 사람 속도로 두 번 누르면(0.15~0.2초) 둘째 누름은 옛 화면의
    단추에 닿는다 — 그 회차에 단추가 이미 잠겼으면 Streamlit 이 누름을 버리고, 아직 열려 있었으면
    콜백이 고친 것 없이 돈다. 어느 쪽이든 그 회차가 첫 누름의 성공 알림을 지웠다(2026-10-26 E2E).
    창(`TRAILING_PRESS_SECONDS`) 안의 회차는 그 칸의 `render_flash` 가 이 알림을 같은 아이콘으로
    다시 그린다.
    """
    note_notice(notices, key, text, icon=_NOTICE_ICONS["success"])


def _name_save_name(kind: str, row_id: str) -> str:
    """이름 한 칸의 제 저장 표지 이름."""
    prefix = REVISION_NAME_SAVE_NAME if kind == "revision" else SCENARIO_NAME_SAVE_NAME
    return f"{prefix}:{row_id}"


def _own_settled(
    fitted: Reconciled, marks: Mapping[str, tuple[Any, Any]]
) -> tuple[SettledName, ...]:
    """지금 이름과 같아져 뺀 고침 가운데 이 세션이 쓴 것 — 첫 콜백이 쓴 뒤 초안을 비우기 전에
    끊겼다. 짝이 **정확히** 같을 때만이다(남이 같은 이름으로 바꾼 것은 뒷정리할 것이 없다)."""
    return tuple(
        item
        for item in fitted.settled
        if is_own_save(_name_save_name(item.kind, item.row_id), item.seen, item.text, marks)
    )


def _save_list_edits(database_path: str, drawn_base: str) -> None:
    """「변경 저장」 콜백 — 시나리오명 · 순서 · 리비전명을 한 트랜잭션으로 쓴다. 하나라도 거부되면
    쓰지 않는다.

    차례: 그린 세대 대조 → 출납 접기 → 지문(저장본에 맞추기 **전** 초안) → `save_once` 안에서 지금
    값 읽기 · 맞추기 · 쓰기 → 표지 → 후속 → 세대 올리기. 세대 올리기를 맨 끝에 둔다 — 그 앞에서
    끊기면 둘째 누름이 같은 지문으로 저장소에 다시 가지 않고 첫 결과로 뒷정리를 잇는다. 그 창이
    지났으면 맞추기가 「같아진 고침」 을 내고 제 저장 짝이면 뒷정리를 한다. 이름은 비교 후 쓰기(본
    이름 — 그 칸을 처음 고칠 때 본 이름)고, 순서는 처음 옮길 때 본 저장 차례와 지금 차례가 같을
    때만 쓴다. 콜백이라 본문 `st.rerun()` 이 없고 DB 핀을 스스로 잡는다.
    """
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    notices = notice_marks()
    marks = own_save_marks()
    draft = _fold_outboxes()
    if draft_base(draft) != drawn_base:
        # 저장 뒤 옛 화면에 닿은 누름이다 — 알림 칸이 표지로 첫 성공을 다시 그린다.
        return
    if not has_edits(draft):
        # 방금 저장한 같은 단추의 빠른 둘째 누름이면 알림 칸이 그 성공을 다시 그린다 — 「고친 것이
        # 없습니다」 로 덮지 않는다(`_note_saved`).
        if held_notice(LIST_NOTICE_KEY) is None:
            _notify(LIST_NOTICE_KEY, "info", "고친 것이 없습니다.")
        return
    # 거부 알림이 줄 번호 · 이름을 적으려면 맞춘 초안이 필요하다 — 저장 안에서 맞춘 것을 건네받는다.
    fitted: list[tuple[Reconciled, SavedList]] = []

    def save() -> SavePlan:
        repository = get_scenario_repository(database_path)
        saved = _read_saved(repository, repository.list_scenarios(), (), draft)
        settled = reconcile(draft, saved)
        fitted.append((settled, saved))
        plan = save_plan(settled.draft, saved)
        if plan.writes:
            repository.apply_scenario_list_edits(
                plan.scenario_renames,
                plan.order,
                expected_order=plan.order_base,
                revision_renames=plan.revision_renames,
            )
            for kind, renames in (
                ("scenario", plan.scenario_renames),
                ("revision", plan.revision_renames),
            ):
                for row_id, (shown, text) in renames.items():
                    # 끊긴 첫 저장을 뒤 회차 맞추기가 제 저장으로 알아보게 적는다(`_own_settled`).
                    # 쓰기 바로 뒤 dict 칸이라 끊기지 않는다.
                    remember_own_save(_name_save_name(kind, row_id), shown, text, marks)
        return replace(plan, settled=_own_settled(settled, marks), gone=settled.gone)

    try:
        with pinned_connections(Path(database_path)):
            done = save_once(
                LIST_SAVE_NAME, draft_fingerprint(draft), save, wrote=lambda plan: plan.done
            )
    except BatchEditRefused as exc:
        settled, saved = fitted[-1]
        _notify(
            LIST_NOTICE_KEY,
            "error",
            refused_edits_message(
                _refused_lines(exc, settled.draft, saved), reloaded=bool(exc.moved_names)
            ),
        )
        # 먼저 바뀐 이름은 그 고침만 빼 지금 이름을 다시 보이고, 차례가 거절되면 순서 고침만
        # 뺀다. 나머지 고침은 줄 id 로 남는다. 세대는 올리지 않는다(보내는 중인 op 는 유효하다).
        kept = without_edits(draft, exc.moved_names)
        if any(row_id is None for row_id, _ in exc.problems):
            kept = replace(kept, order=None, order_base=None)
        store_draft(kept)
        return
    except BOOTSTRAP_ERRORS as exc:
        _notify(LIST_NOTICE_KEY, "error", bootstrap_error_message(exc))
        return
    # 사라진 고침 수는 본문 맞추기가 못 본다(콜백이 먼저 돌아 초안을 비운다). 첫 콜백은 쓴 뒤 이
    # 경고를 담기 전에 끊길 수 있어, 겹쳐 온 둘째 누름도 첫 결과의 수로 다시 담는다(같은 칸이다).
    if done.gone:
        _warn_gone(done.gone)
    if not done.done:
        if not done.gone and held_notice(LIST_NOTICE_KEY) is None:
            _notify(LIST_NOTICE_KEY, "info", "고친 것이 없습니다.")
        store_draft(cleared(draft))
        return
    message = list_saved_message(
        len(done.scenario_names()),
        reordered=done.order is not None,
        revision_count=len(done.revision_names()),
    )
    _note_saved(notices, LIST_NOTICE_KEY, message)
    _after_list_save(done)
    store_draft(cleared(draft))
    _notify(LIST_NOTICE_KEY, "success", message)


def _refused_lines(
    exc: BatchEditRefused, draft: ListDraft, saved: SavedList
) -> list[tuple[str | None, str]]:
    """거부 알림 줄 — 시나리오는 「3행 「이름」」, 리비전은 「r3 「이름」」, 목록 전체는 까닭만."""
    rows = table_rows(draft, saved.order)
    lines: list[tuple[str | None, str]] = []
    for row_id, message in exc.problems:
        place = None
        if row_id is not None and row_id in draft.scenarios and row_id in rows:
            shown = draft.scenarios[row_id].text or saved.names.get(row_id, "")
            place = _row_place(f"{rows.index(row_id) + 1}행", shown)
        elif row_id is not None and row_id in draft.revisions and row_id in saved.revisions:
            revision = saved.revisions[row_id]
            place = _row_place(f"r{revision.no}", draft.revisions[row_id].text or revision.name)
        lines.append((place, message))
    return lines


def _after_list_save(plan: SavePlan) -> None:
    """저장 뒤 이 세션의 후속 처리.

    시나리오명이 바뀌면 — 스냅샷 payload 는 시나리오명을 함께 담는다. 비우지 않으면 그 리비전에서
    파생한 시나리오의 원천명 · 출처 메모에 옛 이름이 남는다. 비교 대상이 이 시나리오면 저장소가 그
    프로필 version 을 올렸다 — 입장 화면 Summary GAP 풍선의 이름이 바뀐다(캐시는 경로 키라 따로
    비우고, 이 세션은 곧바로 다시 확인한다). 머리 띠의 시나리오명은 활성화 때 떠 둔 값이다. 주요
    Case 프로필도 같은 까닭으로 version 이 올랐다.

    리비전명이 바뀌면 — 스냅샷 payload 가 리비전 요약을 통째로 담으므로 프로세스 캐시를 비우고, 파생
    화면이 메모한 원본(요약 포함)을 버리고, 그 리비전이 이 세션에 올라와 있으면 머리 띠 · 팝업 머리
    줄의 이름표를 바꾼다(활성화는 다시 하지 않는다). 주요 Case 슬롯 글자는 리비전명을 실어 저장소가
    그 프로필 version 을 올렸다. 공식 이력 · 비교 프로필 · 입장 화면 Summary 는 리비전명을 싣지
    않아 건드리지 않는다. 시나리오 「최근 수정」 도 오르지 않아 목록 차례가 그대로다.
    """
    scenario_names = plan.scenario_names()
    revision_names = plan.revision_names()
    if scenario_names or revision_names:
        clear_scenario_snapshot_cache()
        forget_derived_sources()
        clear_global_main_cases_cache()
    if scenario_names:
        clear_global_comparison_scenario_cache()
        forget_intro_summary_check()
        for scenario_id, name in scenario_names.items():
            rename_active_scenario_label(scenario_id, name)
    for revision_id, name in revision_names.items():
        rename_active_revision_label(revision_id, name)


def _row_place(place: str, name: str) -> str:
    """거부 알림 줄의 행 표지 — 「2행 「이름」」·「r3 「이름」」."""
    return f"{place} 「{literal_markdown(name)}」"


def refused_edits_message(
    problems: Sequence[tuple[str | None, str]], *, reloaded: bool = False
) -> str:
    """거부된 일괄 저장의 알림. 줄마다 (행 표지, 까닭) — 표지가 없으면 목록 전체의 까닭이다.

    `reloaded` 면 먼저 바뀐 이름을 표에 지금 이름으로 다시 올렸다는 한 줄을 붙인다.
    """
    lines = ["저장하지 않았습니다 — 하나라도 막히면 아무것도 쓰지 않습니다."]
    for place, message in problems:
        reason = literal_markdown(message)
        lines.append(f"- {place}: {reason}" if place else f"- {reason}")
    if reloaded:
        lines.append(
            "\n먼저 바뀐 이름은 표에 지금 이름으로 다시 올렸습니다 — 그래도 바꾸려면 다시 고쳐 "
            "저장하세요."
        )
    return "\n".join(lines)


def list_saved_message(rename_count: int, *, reordered: bool, revision_count: int = 0) -> str:
    """「변경 저장」 성공 한 줄 — 저장한 것만."""
    parts = []
    if rename_count:
        parts.append(f"시나리오명 {rename_count}건")
    if reordered:
        parts.append("누적 순서")
    if revision_count:
        parts.append(f"리비전명 {revision_count}건")
    return f"{' · '.join(parts)}{object_particle(parts[-1])} 저장했습니다."


def _render_detail(
    repository: DuckDBScenarioRepository,
    database_path: str,
    scenarios: Sequence[ScenarioSummary],
    view: _ListView,
) -> bool:
    """「상세」 칸. 공식 지정 팝업의 열림 칸이 이 칸이 그린 시나리오 · 리비전이면 `True` — 팝업은
    호스트가 연다(`_render_official_host`).

    자리 차례: 리비전 표(표 · 제목 · 원천 코드 · 최근 수정 · 값 줄) · 미저장 확인 칸 · 작업 줄 ·
    결과 칸 · 「보관…」 · 보관 칸. 쓰는 차례로 짠다 — 불러오기를 먼저, 보관은 아래(설계 규칙
    UI-LAY-06). 표가 맨 위라 왼쪽 시나리오 표 머리와 윗선이 같다. 생기고 사라지는 것은 모두 늘
    서 있는 칸 안이다.
    """
    from capa_simulation.components.scenario_list_grid import render_list_mount

    opened = _opened_revisions(repository, scenarios, view)
    if opened is None:
        return False
    summary, revisions, draft = opened
    revision_by_id = {revision.revision_id: revision for revision in revisions}
    picked_id = draft.picked
    render_list_mount(
        REVISIONS_KEY,
        {
            **_list_common(draft, REVISIONS_KEY),
            **revisions_payload(
                draft,
                owner=summary.scenario_id,
                title=summary.scenario_name,
                sub=f"{summary.source_simulation_code} · {_short_time(summary.updated_at)}",
                facts=_revision_facts(repository, revisions, view.releases),
                problems=view.problems,
            ),
        },
        on_outbox=_on_list_outbox,
    )
    picked = revision_by_id.get(picked_id) if picked_id is not None else None
    if not revisions:
        st.caption("이 시나리오에 저장된 리비전이 없습니다.")
    else:
        # 불러오는 입구가 둘이다 — 이 칸과 사이드바 시나리오 팝업. 확인 절차와 글자를 맞춘다
        # (`components/scenario_status.py`): 미저장 변경이 있으면 버린다는 체크를 받는다.
        discard_changes = True
        with st.container():
            if has_unsaved_scenario_changes():
                discard_changes = st.checkbox(
                    "변경을 버리고 불러오기",
                    key=DISCARD_UNSAVED_KEY,
                )
        _refuse_stale_official_press(summary.scenario_id, revision_by_id)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.button(
                "선택한 리비전 불러오기",
                icon=":material/download:",
                type="primary",
                disabled=picked is None or not discard_changes,
                help=(
                    REVISION_PICK_HELP
                    if picked is None
                    else None
                    if discard_changes
                    else DISCARD_LOCK_HELP
                ),
                key=f"{CARD_LOAD_KEY}_{summary.scenario_id}",
                on_click=_load_picked_revision,
                args=(database_path, summary.scenario_id),
            )
            st.button(
                "공식으로 지정…",
                icon=":material/verified:",
                disabled=picked is None,
                help=REVISION_PICK_HELP if picked is None else None,
                key=f"{CARD_OFFICIAL_KEY}_{summary.scenario_id}",
                on_click=_open_official_dialog,
                args=(summary.scenario_id, f"{CARD_OFFICIAL_KEY}_{summary.scenario_id}"),
            )
        render_flash(CARD_NOTICE_KEY)
    st.button(
        "보관…",
        icon=":material/archive:",
        type="tertiary",
        key=f"{ACTION_KEY}_archive",
        on_click=_toggle_action,
        args=("archive",),
    )
    with st.container():
        if st.session_state.get(ACTION_KEY) == "archive":
            _render_archive(repository, summary)
    opened = st.session_state.get(OFFICIAL_DIALOG_KEY)
    return (
        isinstance(opened, tuple)
        and len(opened) == 2
        and opened[0] == summary.scenario_id
        and opened[1] in revision_by_id
    )


def _revision_facts(
    repository: DuckDBScenarioRepository,
    revisions: Sequence[RevisionSummary],
    releases: Sequence[OfficialReleaseSummary],
) -> list[RevisionFacts]:
    """리비전 표 줄 — 상태는 「공식 vN · 올라와 있음 · 가상 n」 이다. 가상 제품 수는 리비전 id
    목록으로 한 번에 센다(`count_virtual_products` — 회차마다 리비전 수만큼 읽지 않는다)."""
    number_by_id = {revision.revision_id: revision.revision_no for revision in revisions}
    release_by_revision: dict[str, int] = {}
    for release in releases:
        release_by_revision.setdefault(release.revision_id, release.release_no)
    virtual_counts = repository.count_virtual_products(list(number_by_id))
    active_revision_id = active_persisted_revision_id()
    return [
        RevisionFacts(
            revision_id=revision.revision_id,
            no=revision.revision_no,
            name=revision.revision_name,
            status=revision_status_label(
                release_by_revision.get(revision.revision_id),
                loaded=revision.revision_id == active_revision_id,
                virtual_count=virtual_counts.get(revision.revision_id, 0),
            ),
            memo=(revision.note or "").replace("\n", " "),
            created=_short_time(revision.created_at),
            parent=_parent_label(revision.parent_revision_id, number_by_id),
        )
        for revision in revisions
    ]


def _toggle_action(action: str) -> None:
    """카드 작업 칸 하나를 열고 닫는다(「보관…」)."""
    if st.session_state.get(ACTION_KEY) == action:
        st.session_state.pop(ACTION_KEY, None)
    else:
        st.session_state[ACTION_KEY] = action


def _seed_revision_pick(
    summary: ScenarioSummary,
    picked: str | None,
    revision_ids: Sequence[str],
    first_view: bool,
) -> str | None:
    """리비전 표의 고름 씨앗. 처음 볼 때와 올라와 있는 리비전이 바뀔 때만 코드가 고른다.

    지금 보고 있는 시나리오라면 **올라와 있는 리비전**이 미리 골라져 있어야 한다 — 화면과 다른 것이
    골라져 있으면 「같은 것을 다시 불러왔다」고 여기면서 실은 다른 리비전을 올리게 된다. 올라와 있는
    리비전이 씨앗(`REVISION_SEED_KEY`)과 달라지면 다시 고른다. 사용자가 일부러 고른 리비전은 올라와
    있는 리비전이 그대로인 동안 남는다. 다른 시나리오는 처음 볼 때 최신 리비전을 고른다. 고름이 연
    시나리오의 리비전이 아니면 `first_view` 와 상관없이 다시 고른다 — 불러오기가 잠긴 채 서지
    않는다.
    """
    active_revision_id = active_persisted_revision_id()
    active_here = (
        summary.scenario_id == active_persisted_scenario_id() and active_revision_id in revision_ids
    )
    if active_here and st.session_state.get(REVISION_SEED_KEY) != active_revision_id:
        st.session_state[REVISION_SEED_KEY] = active_revision_id
        return active_revision_id
    if not active_here:
        # 올라와 있는 것이 다른 시나리오로 옮겨 가면 씨앗 기록을 버린다. 남겨 두면 마지막으로
        # 씨앗을 넣은 리비전으로 돌아왔을 때 「같은 씨앗」으로 읽혀 표가 따라오지 않았다
        # (2026-10-11 재검증).
        st.session_state.pop(REVISION_SEED_KEY, None)
        if first_view:
            return revision_ids[0] if revision_ids else None
    if picked in revision_ids:
        return picked
    if active_here:
        return active_revision_id
    return revision_ids[0] if revision_ids else None


def _parent_label(parent_revision_id: str | None, number_by_id: Mapping[str, int]) -> str:
    if parent_revision_id is None or parent_revision_id not in number_by_id:
        return ""
    return f"r{number_by_id[parent_revision_id]}"


def _load_picked_revision(database_path: str, drawn_scenario: str) -> None:
    """「선택한 리비전 불러오기」 콜백. 고른 리비전은 출납을 접은 뒤의 고름이다 — 리비전 줄을 누른
    직후의 단추도 그 리비전에 걸린다. 왼쪽 줄을 누르고 바로 옛 카드 단추를 눌렀거나 고른 리비전이
    이 시나리오 것이 아니면 하지 않는다(불러오기에는 확인 팝업이 없다)."""
    draft = _fold_outboxes()
    if draft.opened != drawn_scenario:
        _notify(CARD_NOTICE_KEY, "error", OPENED_MOVED_MESSAGE)
        return
    revision_id = draft.picked
    if revision_id is None:
        _notify(CARD_NOTICE_KEY, "error", "불러올 리비전을 표에서 고르세요.")
        return
    # 단추 잠금은 화면의 약속일 뿐이다. 누른 회차에도 미저장 편집을 버린다는 체크를 다시 본다.
    if has_unsaved_scenario_changes() and not st.session_state.get(DISCARD_UNSAVED_KEY):
        _notify(
            CARD_NOTICE_KEY,
            "error",
            "저장하지 않은 편집이 있습니다 — 「변경을 버리고 불러오기」를 체크해야 불러옵니다.",
        )
        return
    try:
        with pinned_connections(Path(database_path)):
            # 옛 카드의 누름 — 남이 그 사이 보관 · 삭제했으면 목록에 없는 시나리오를 올리지 않는다.
            listed = get_scenario_repository(database_path).list_scenarios()
            if drawn_scenario not in {item.scenario_id for item in listed}:
                _notify(CARD_NOTICE_KEY, "error", ARCHIVE_GONE_MESSAGE)
                return
            snapshot = load_scenario_snapshot(database_path, revision_id)
            # 옛 리비전 줄의 누름이 지금 연 시나리오 이름표를 달고 올 수 있다 — 소속으로 다시 본다.
            if snapshot.scenario.scenario_id != drawn_scenario:
                _notify(CARD_NOTICE_KEY, "error", OPENED_MOVED_MESSAGE)
                return
            # 활성화 **전에** 본다. 활성화한 뒤에 계산이 죽으면 올라와 있는 시나리오가 이미 바뀐
            # 뒤라 화면에서 되돌릴 방법이 없다.
            blocked = revision_block_reason(snapshot.tables)
            if blocked is not None:
                _notify(CARD_NOTICE_KEY, "error", blocked)
                return
            activate_persisted_snapshot(snapshot)
    except BOOTSTRAP_ERRORS as exc:
        _notify(CARD_NOTICE_KEY, "error", bootstrap_error_message(exc))
        return
    queue_flash(
        FLASH_KEY,
        f"{literal_markdown(snapshot.scenario.scenario_name)} r{snapshot.revision.revision_no}"
        f"{object_particle(str(snapshot.revision.revision_no))} 불러왔습니다.",
    )


def _revision_name_save_name(revision_id: str) -> str:
    return f"{REVISION_NAME_SAVE_NAME}:{revision_id}"


def save_revision_name(
    database_path: str, revision: RevisionSummary, revision_name: str
) -> RevisionSummary | None:
    """리비전 하나의 이름표만 바꾸고 이 세션의 후속 처리를 한다. 바뀐 것이 없으면 쓰지 않고 `None`.

    `revision` 은 화면이 그 회차에 읽어 보인 요약이다. 그 이름을 `expected_name` 으로 넘겨 비교 후
    쓰기를 한다 — 그 사이 다른 사용자가 먼저 바꿨으면 저장소가 `RevisionNameMoved` 로 거절한다.
    빈 이름·보관된 시나리오·파일 잠금도 저장소 예외(`BOOTSTRAP_ERRORS` 안)로 그대로 올리고, 부르는
    쪽이 누른 자리에서 알린다. 콜백에서도 부를 수 있게 DB 핀을 스스로 잡는다(겹쳐도 된다).
    후속 처리는 `_after_list_save` 와 같다.
    """
    if revision_name.strip() == revision.revision_name:
        return None
    save_marks = own_save_marks()
    with pinned_connections(Path(database_path)):
        renamed = get_scenario_repository(database_path).rename_revision(
            revision.revision_id, revision_name, expected_name=revision.revision_name
        )
    remember_own_save(
        _revision_name_save_name(renamed.revision_id),
        revision.revision_name,
        renamed.revision_name,
        save_marks,
    )
    _after_revision_rename([renamed])
    return renamed


def _after_revision_rename(renamed: Sequence[RevisionSummary]) -> None:
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    clear_global_main_cases_cache()
    for revision in renamed:
        rename_active_revision_label(revision.revision_id, revision.revision_name)


def _open_official_dialog(drawn_scenario: str, widget_key: str) -> None:
    """「공식으로 지정…」 콜백. 출납을 접은 뒤의 고름으로 연다 — 다른 팝업 칸을 비우고(한 실행에
    하나) 할 수 있으면 호스트만 다시 돌린다(`DialogHost.open` — 출납도 함께 바뀐 누름은 앱 전체
    회차다). `widget_key` 는 누른 단추의 key 다."""
    draft = _fold_outboxes()
    if draft.opened != drawn_scenario:
        _notify(CARD_NOTICE_KEY, "error", OPENED_MOVED_MESSAGE)
        return
    if draft.picked is None:
        return
    st.session_state.pop(OFFICIAL_VIEW_KEY, None)
    OFFICIAL_HOST.open((drawn_scenario, draft.picked), widget_key)


def _close_official_dialog() -> None:
    """열림 칸 · 팝업의 입력 위젯 값(`DialogHost.close`)과 팝업이 읽어 둔 대상을 지운다. 팝업
    닫기(X · 바깥 · Esc — `on_dismiss`)도 이것이다."""
    st.session_state.pop(OFFICIAL_VIEW_KEY, None)
    OFFICIAL_HOST.close()


def _refuse_stale_official_press(
    scenario_id: str, revision_by_id: Mapping[str, RevisionSummary]
) -> None:
    """「공식으로 지정…」 을 누른 옛 카드가 지금 연 시나리오 · 리비전이 아니다(남이 그 사이 보관해
    본문이 줄을 옮겼다). 팝업 칸을 비우고 결과 칸에 알린다 — 말없이 지우면 팝업도 알림도 없이 표만
    바뀐다."""
    opened = st.session_state.get(OFFICIAL_DIALOG_KEY)
    if not isinstance(opened, tuple) or len(opened) != 2:
        return
    if opened[0] == scenario_id and opened[1] in revision_by_id:
        return
    _close_official_dialog()
    _notify(CARD_NOTICE_KEY, "error", OPENED_MOVED_MESSAGE)


@dataclass(frozen=True)
class _OfficialView:
    """공식 지정 팝업이 그리는 대상 — 시나리오(보관본일 수 있다) · 리비전 · 「지금 공식」 · 그
    리비전의 가상 제품."""

    summary: ScenarioSummary
    revision: RevisionSummary
    latest: OfficialReleaseSummary | None
    virtual_products: tuple[VirtualProductRecord, ...]


def _read_official_view(
    repository: DuckDBScenarioRepository, scenario_id: str, revision_id: str
) -> _OfficialView | None:
    """팝업이 그릴 대상을 지금 저장소에서 읽는다. 시나리오는 보관본까지 본다 — 그 사이 보관된 것은
    지정 단추에서 저장소가 거부한다. 시나리오 · 리비전이 없으면(영구 삭제) None."""
    summary = next(
        (
            item
            for item in repository.list_scenarios(include_archived=True)
            if item.scenario_id == scenario_id
        ),
        None,
    )
    if summary is None:
        return None
    revision = next(
        (
            item
            for item in repository.list_revisions(scenario_id)
            if item.revision_id == revision_id
        ),
        None,
    )
    if revision is None:
        return None
    return _OfficialView(
        summary,
        revision,
        repository.latest_official_release(),
        virtual_product_records(repository.list_virtual_products(revision_id)),
    )


def _kept_official_view(scenario_id: str, revision_id: str) -> _OfficialView | None:
    """이번 열림에서 팝업이 마지막으로 읽어 그린 그 시나리오 · 리비전의 대상(없으면 None — 이번
    열림의 첫 회차)."""
    kept = st.session_state.get(OFFICIAL_VIEW_KEY)
    if (
        isinstance(kept, _OfficialView)
        and kept.summary.scenario_id == scenario_id
        and kept.revision.revision_id == revision_id
    ):
        return kept
    return None


@st.dialog(WIDE_TITLE, width="large", on_dismiss=_close_official_dialog)
def _wide_dialog(database_path: str, value: WideValue) -> None:
    """「점검」 칸 「넓게 보기」 — 그 묶음 표의 모든 칸 · 모든 행. 호스트(`OFFICIAL_HOST`)가 공식
    지정 팝업과 함께 열림 값의 꼴로 가른다(결정 17). 원본을 바꾸지 않는 읽기 팝업이다."""
    render_wide_body(database_path, value)


@st.dialog("공식버전 지정", width="medium", on_dismiss=_close_official_dialog)
@keeps_app_run_open
def _official_dialog(database_path: str, scenario_id: str, revision_id: str) -> None:
    """공식버전 지정 확인 팝업. 호스트(`OFFICIAL_HOST`)가 부르고, 팝업 안 조작은 실행 핀 밖의
    프래그먼트라 DB 핀을 스스로 잡는다.

    시나리오 · 리비전 · 「지금 공식」 · 가상 제품은 **본문에서 다시 읽는다** — 호스트만 도는 여는
    회차의 인자는 이 화면의 마지막 앱 전체 회차의 것이라 그 사이 남이 지정 · 보관한 것이 빠진다.
    「지금 공식」 은 지정의 대조 값이기도 하다(`OFFICIAL_SEEN_KEY`).

    - 연 회차(읽어 둔 대상 없음)에 그 시나리오가 보관됐거나 줄이 없으면 팝업을 걷고 카드 결과 칸에
      알린다(앱 전체 회차가 지금 연 줄로 다시 그린다).
    - 팝업을 그린 뒤에 보관됐으면 그대로 그리고 지정 단추에서 저장소가 거부한다 — 알림창의 까닭과
      카드 곁 알림 둘이다(작은 결정 a7 「지금대로」). 그 뒤 영구 삭제까지 됐으면 다시 읽기가 빈
      대상을 받아 팝업을 걷는다 — 같은 둘(까닭 `OFFICIAL_PURGED_MESSAGE` + 카드 곁)이다(검수 보드
      sc-purged — a1 답과 같은 꼴).
    - 다시 읽지 못하면(파일 잠금 따위) 팝업을 걷지 않는다. 읽어 둔 대상이 있으면 그것으로 친 글과
      함께 다시 그리고 지정하지 않는다 — 앱 전체를 다시 돌리면 같은 까닭으로 페이지가 서지 못해
      팝업과 친 글이 사라진다. 연 회차부터 못 읽었으면 그릴 것이 없어 앱 전체로 물러난다.
    """
    kept = _kept_official_view(scenario_id, revision_id)
    with pinned_connections(Path(database_path)):
        repository = get_scenario_repository(database_path)
        try:
            view = _read_official_view(repository, scenario_id, revision_id)
        except BOOTSTRAP_ERRORS as exc:
            if kept is None:
                _refuse_official(bootstrap_error_message(exc))
            _render_official(repository, database_path, kept, unread=bootstrap_error_message(exc))
            return
        if view is None or (kept is None and view.summary.status != "ACTIVE"):
            _close_official_dialog()
            if view is None and kept is not None:
                # 그린 뒤 영구 삭제 — 고칠 입력이 이 자리에 없는 거부라 까닭은 알림창 · Alarm 에만
                # 낸다(`_refuse_official` 과 같은 칸 · 꼴, 맨 위 칸이라 카드 곁 알림보다 먼저 선다).
                queue_flash(
                    FLASH_WARNING_KEY,
                    OFFICIAL_PURGED_MESSAGE,
                    kind="error",
                    icon=_NOTICE_ICONS["error"],
                    popup_only=True,
                )
            _notify(CARD_NOTICE_KEY, "error", OPENED_MOVED_MESSAGE)
            st.rerun()
        st.session_state[OFFICIAL_VIEW_KEY] = view
        _render_official(repository, database_path, view)


def _render_official(
    repository: DuckDBScenarioRepository,
    database_path: str,
    view: _OfficialView,
    *,
    unread: str | None = None,
) -> None:
    """팝업 본문 — 「지금 공식 → 새 공식」을 나란히 보이고, 확인을 받아 지정한다.

    모두의 첫 화면이 바뀌는 작업이라 대상을 사람 눈으로도 확인하게 적는다. 팝업이 보인 「지금
    공식」 번호를 저장소에 넘겨(`expected_latest_release_no`) 그 사이 다른 사람이 먼저 지정했으면
    쓰지 않는다. `unread` 는 이 회차에 저장소를 다시 읽지 못한 까닭이다 — 읽어 둔 대상과 친 글을
    그대로 그리고, 지정하지 않고 그 까닭을 알림창 · Alarm 에만 낸다(고칠 입력이 이 자리에 없다 —
    설계 규칙 UI-NTF-03).
    """
    summary, revision, latest = view.summary, view.revision, view.latest
    revision_id = revision.revision_id
    current_column, next_column = st.columns(2)
    with current_column:
        st.caption("지금 공식")
        if latest is None:
            st.markdown("없음")
        else:
            st.markdown(
                f"**v{latest.release_no}** · {literal_markdown(latest.scenario_name)} "
                f"r{latest.revision_no}  \n{literal_markdown(latest.release_name)}"
            )
    with next_column:
        st.caption("새 공식")
        next_no = (latest.release_no if latest is not None else 0) + 1
        st.markdown(
            f"**v{next_no}** · {literal_markdown(summary.scenario_name)} "
            f"{literal_markdown(revision_label(revision))}"
        )
    # 지금 공식과 같은 리비전이면 값 표지 한 마디 — 그래도 지정되는 뜻은 지정 단추 풍선이 말한다.
    same_as_official = latest is not None and latest.revision_id == revision_id
    if same_as_official:
        st.caption(SAME_AS_OFFICIAL_LINE)
    # 가상 제품은 실적과 대조할 수 없는 값이다. 그런 리비전이 모두의 첫 화면이 되기 전에
    # 지정하는 사람이 그 사실을 보고 확인하게 한다(2026-10-06 사용자 결정). 확인 체크는 폼
    # **밖**에 둔다 — 폼 안의 체크는 누를 때 다시 그리지 않아 지정 버튼을 풀 수 없다.
    virtual_products = view.virtual_products
    confirmed = True
    if virtual_products:
        st.warning(official_virtual_product_warning(virtual_products), icon=":material/warning:")
        confirmed = st.checkbox(
            "가상 제품이 포함된 것을 확인했습니다",
            key=official_confirm_key(revision_id),
        )
    with st.form("scenario_official_form"):
        release_name = st.text_input(
            "공식버전명", value=f"{summary.scenario_name} 공식안", key=OFFICIAL_NAME_KEY
        )
        release_note = st.text_area("공식 지정 메모", height=80, key=OFFICIAL_NOTE_KEY)
        official_submitted = st.form_submit_button(
            "선택 리비전을 공식버전으로 지정",
            icon=":material/publish:",
            type="primary",
            disabled=not confirmed,
            width="stretch",
            help=(
                OFFICIAL_CONFIRM_HELP
                if not confirmed
                else SAME_AS_OFFICIAL_HELP
                if same_as_official
                else None
            ),
        )
    refused = take_refusal(OFFICIAL_SAVE_NAME)
    if refused is not None:
        st.error(refused)
    if unread is not None:
        queue_flash(
            OFFICIAL_UNREAD_KEY,
            markdown_safe_tildes(unread),
            kind="error",
            icon=_NOTICE_ICONS["error"],
            popup_only=True,
        )
        render_flash(OFFICIAL_UNREAD_KEY)
        return
    if official_submitted and not confirmed:
        # 버튼 잠금은 화면의 약속일 뿐이다. 제출 회차에도 확인을 다시 본다.
        st.error("가상 제품이 포함된 것을 확인해야 공식버전으로 지정할 수 있습니다.")
        return
    if not official_submitted:
        # 이 회차가 보인 「지금 공식」 이 지정의 대조 값이다 — 제출 회차에는 적지 않는다
        # (write_guard).
        remember_seen(OFFICIAL_SEEN_KEY, latest.release_no if latest is not None else 0)
        return
    expected_no = seen(OFFICIAL_SEEN_KEY)
    if not isinstance(expected_no, int):
        # 팝업이 보인 번호를 모른다 — 지금 번호로 대체하면 남의 지정을 모르는 채 그 위에 세운다.
        queue_refusal(OFFICIAL_SAVE_NAME, SEEN_MISSING_MESSAGE)
        st.rerun()
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    save_marks = own_save_marks()
    try:
        # 공식버전은 모두의 첫 화면이다. 계산이 안 되는 리비전을 지정하면 모두의 HOME 이
        # 멈춘다. 검사는 HOME 과 같은 캐시 칸을 써서, 통과하면 HOME 이 이미 데워져 있다.
        with st.spinner("공식버전으로 지정할 수 있는지 Capa 계산을 확인하는 중입니다..."):
            verdict = official_publish_verdict(
                database_path, revision_id, labels=get_process_labels
            )
        if not verdict.allowed:
            st.error(markdown_safe_tildes(verdict.message))
            return
        release = repository.publish_official_revision(
            summary.scenario_id,
            revision_id,
            release_name=release_name,
            note=release_note,
            expected_latest_release_no=expected_no,
        )
    except OfficialReleaseMoved as exc:
        current = None
        if is_own_save(OFFICIAL_SAVE_NAME, exc.expected, exc.current, save_marks):
            try:
                current = repository.latest_official_release()
            except BOOTSTRAP_ERRORS:
                current = None
        if current is None or current.release_no != exc.current:
            # 저장소 문구는 배경 회차(자동 갱신) 말투라 팝업에서는 무엇을 하면 되는지로 바꿔 적는다.
            _refuse_official(official_moved_message(exc.current))
        # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 지정했다(write_guard). 첫 누름의 뒷정리가
        # 끊겼을 수 있어 여기서 다시 한다(경고 글은 첫 누름의 회차가 냈다).
        _official_published(current, revision_id, warning=None, exclusion=False)
    except BOOTSTRAP_ERRORS as exc:
        _refuse_official(bootstrap_error_message(exc))
    remember_own_save(OFFICIAL_SAVE_NAME, expected_no, release.release_no, save_marks)
    _official_published(
        release, revision_id, warning=verdict.message or None, exclusion=verdict.exclusion
    )


def _official_published(
    release: OfficialReleaseSummary,
    revision_id: str,
    *,
    warning: str | None,
    exclusion: bool,
) -> NoReturn:
    """공식 지정 뒤 이 세션의 뒷정리 — 알림을 담고 팝업을 닫고 다음 회차가 새 공식을 싣게 한 뒤 앱을
    다시 돌린다. `exclusion` 은 `warning` 이 소요대수에 들지 않은 수요 경고라는 표지다
    (`capacity_gate.GateVerdict.exclusion`)."""
    queue_flash(
        FLASH_KEY,
        f"공식 v{release.release_no} · {literal_markdown(release.release_name)}"
        f"{object_particle(release.release_name)} 지정했습니다.",
    )
    # 허락하면서 하는 경고(소요대수에 들지 않은 수요 건수)는 지정한 사람이 알림창에서 본다 — 지정은
    # 끝났고 고칠 입력이 이 자리에 없어 버튼 곁 상자 없이 알림창 · Alarm 에만 낸다(사이드바 리비전
    # 저장과 한 꼴 — 2026-11-04 검수 의견 home-18).
    if warning:
        # 소요대수에 들지 않은 수요의 「그 화면으로」 는 지정한 리비전을 고른 목록 관리 「점검」
        # 칸이다(같은 리비전 · 전체 기간 — 검토 보드 F4 (나) · 리비전은 줄이 들고 감, F4 뒤 (a)).
        queue_flash(
            FLASH_WARNING_KEY,
            markdown_safe_tildes(warning),
            kind="warning",
            icon=":material/warning:",
            popup_only=True,
            goto=REQUIRED_TAB_GOTO if exclusion else None,
            target=required_check_target(release.scenario_id, revision_id) if exclusion else None,
        )
    _close_official_dialog()
    st.session_state.pop(official_confirm_key(revision_id), None)
    # 입장 화면 Summary 가 새 공식버전을 다음 회차에 곧바로 싣게 한다
    # (평소에는 30초에 한 번 본다).
    forget_intro_summary_check()
    # 판정 기준을 아직 저장하지 않았으면 기본값이 최신 공식버전 프리셋에서 온다.
    clear_global_securement_threshold_cache()
    st.rerun()


def _refuse_official(message: str) -> NoReturn:
    """아무것도 지정하지 않은 거부 — 그 자리에 고칠 입력이 없어 알림창 · Alarm 에만 내고(설계 규칙
    UI-NTF-03) 앱 전체를 다시 돌린다. 팝업 안 제출은 팝업만 도는 회차라 탭 맨 위 칸이 서지 않는다 —
    다시 도는 회차가 그 칸에서 알림을 내고, 열림 칸이 남은 팝업은 지금 「지금 공식」 으로 다시
    선다."""
    queue_flash(
        FLASH_WARNING_KEY,
        markdown_safe_tildes(message),
        kind="error",
        icon=_NOTICE_ICONS["error"],
        popup_only=True,
    )
    st.rerun()


def official_moved_message(current_release_no: int) -> str:
    """팝업을 연 사이 다른 사람이 먼저 공식버전을 지정해 지정하지 않았을 때의 알림."""
    return (
        f"팝업을 연 사이 다른 사람이 공식 v{current_release_no}"
        f"{object_particle(str(current_release_no))} 먼저 지정해 지정하지 않았습니다 — 팝업의 "
        "「지금 공식」을 확인한 뒤 다시 지정하세요."
    )


def _render_official_history(releases: Sequence[OfficialReleaseSummary]) -> None:
    """「공식 이력」 칸 — 공식 발행 이력(r 번호 · 공식버전명만, 리비전명은 싣지 않는다).

    리비전명은 고칠 수 있어, 실으면 이름을 바꾸는 순간 과거 발행 행이 발행 당시와 다른 이름을
    보인다.
    """
    if not releases:
        st.caption("공식으로 지정한 리비전이 없습니다.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "공식버전": f"v{release.release_no}",
                    "시나리오": release.scenario_name,
                    "리비전": f"r{release.revision_no}",
                    "지정시각": release.published_at,
                    "공식버전명": release.release_name,
                }
                for release in releases[:HISTORY_LIMIT]
            ]
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "공식버전": st.column_config.TextColumn(width=HISTORY_VERSION_WIDTH_PX),
            "시나리오": st.column_config.TextColumn(width=HISTORY_SCENARIO_WIDTH_PX),
            "리비전": st.column_config.TextColumn(width=HISTORY_REVISION_WIDTH_PX),
            "지정시각": st.column_config.DatetimeColumn(
                format=HISTORY_TIME_FORMAT, width=HISTORY_TIME_WIDTH_PX
            ),
        },
    )
    if len(releases) > HISTORY_LIMIT:
        st.caption(f"최근 {HISTORY_LIMIT}건만 보입니다.")


def official_confirm_key(revision_id: str) -> str:
    """가상 제품 확인 체크의 key. 리비전을 바꾸면 다른 칸이라 앞 리비전의 확인이 따라오지 않는다."""
    return f"{OFFICIAL_CONFIRM_KEY}_{revision_id}"


def archive_confirm_key(scenario_id: str) -> str:
    """보관 확인 체크의 key. 칸을 지워도 브라우저가 옛 값을 다시 보내므로 시나리오를 실어 다른
    칸으로 세운다 — 앞 시나리오의 확인이 따라오면 「B 를 보관합니다」 가 켜진 채 선다."""
    return f"{ARCHIVE_CONFIRM_KEY}_{scenario_id}"


def official_virtual_product_warning(records: Sequence[VirtualProductRecord]) -> str:
    """공식버전 지정 전에 보일 가상 제품 확인 문장. 제품 · Stack 을 모두 적는다.

    `st.warning`(마크다운)으로 그리므로 사람이 적은 제품정보·Stack 은 막아 싣는다.
    """
    products = ", ".join(
        f"{literal_markdown(record.product)} · {literal_markdown(record.stack)}"
        for record in records
    )
    return (
        f"이 리비전에는 가상 제품 {len(records)}건이 포함되어 있습니다({products}). "
        "실적과 대조할 수 없는 값입니다. 그대로 공식버전으로 지정할까요?"
    )


def _render_archive(repository: DuckDBScenarioRepository, summary: ScenarioSummary) -> None:
    # 최신 공식버전의 시나리오는 저장소가 보관을 거절한다(`_require_not_latest_official`). 체크하고
    # 눌러 본 뒤에야 알게 하지 않고 그린 회차의 최신 공식으로 미리 말한다. 저장소 검사는 그대로
    # 마지막 방어선이다(그 사이 다른 사용자가 공식을 바꾼 경우).
    official = repository.latest_official_release()
    # 잠금 까닭 · 확인 글은 결과만 적는다 — 먼저 할 일(다른 리비전을 공식으로 지정)과 되돌리는
    # 자리(「보관함」)는 Guide 가 말한다(설계 규칙 UI-TXT-03 — 같은 화면 안 길 안내도 걷는다).
    if official is not None and official.scenario_id == summary.scenario_id:
        st.caption(":material/block: 공식버전이라 보관 막힘")
        st.button(
            "보관 실행",
            icon=":material/archive:",
            type="primary",
            disabled=True,
            width="stretch",
            help=f"지금 최신 공식버전(v{official.release_no})의 시나리오라 보관할 수 없습니다.",
        )
        return
    # 보관이 파일 크기를 줄이지 않는다는 것(용량 목적이면 영구 삭제 + compact)은 Guide 가 말한다.
    confirmed = st.checkbox(
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "보관합니다",
        key=archive_confirm_key(summary.scenario_id),
    )
    if not st.button(
        "보관 실행",
        icon=":material/archive:",
        type="primary",
        disabled=not confirmed,
        width="stretch",
        help=ARCHIVE_EFFECT_HELP if confirmed else ARCHIVE_LOCK_HELP,
    ):
        return
    message = (
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "보관했습니다."
    )
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    notices = notice_marks()
    settle_draft = _draft_settler(repository, summary.scenario_id)
    try:
        # 보관함 「되돌리기」·「영구 삭제 실행」 과 같다 — 첫 쓰기 전 목록을 그린 겹친 둘째 누름은
        # 저장소에 다시 가지 않는다(가면 이미 보관한 시나리오라 날 KeyError 가 선다).
        save_once(
            ARCHIVE_SAVE_NAME,
            summary.scenario_id,
            lambda: repository.archive_scenario(summary.scenario_id),
            wrote=lambda _: True,
        )
    except KeyError:
        # 그 사이 남이 먼저 보관했거나 지웠다(저장소가 활성 시나리오를 찾지 못했다).
        _refuse_gone_press(ARCHIVE_GONE_MESSAGE)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    note_notice(notices, FLASH_KEY, message)
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    # 저장소가 이 시나리오를 가리키던 공용 비교 대상·주요 Case 를 비웠다. 캐시는 경로 키라 따로
    # 비운다.
    clear_global_comparison_scenario_cache()
    clear_global_main_cases_cache()
    # 입장 화면 Summary 의 GAP 도 그 비교 대상을 쓴다 — 이 세션은 곧바로 다시 확인한다.
    forget_intro_summary_check()
    # 보관한 시나리오의 공식버전이 판정 기준의 미저장 기본값을 정했을 수 있다.
    clear_global_securement_threshold_cache()
    if summary.scenario_id == active_persisted_scenario_id():
        clear_persisted_scenario_activation()
    queue_flash(FLASH_KEY, message)
    settle_draft()
    for key in (ACTION_KEY, ACTION_OWNER_KEY, archive_confirm_key(summary.scenario_id)):
        st.session_state.pop(key, None)
    st.rerun()


def _draft_settler(
    repository: DuckDBScenarioRepository, gone_scenario: str | None = None
) -> Callable[[], None]:
    """이 세션의 보관 · 되돌리기 · 영구 삭제 뒤 초안을 맞추는 함수 — **쓰기 전에** 부른다.

    리비전 고침은 소속이 없어 그 시나리오의 리비전 id 를 쓰기 전에 읽어 둔다(쓴 뒤면 다음 회차
    맞추기가 「사라진 고침」 으로 세어 알린다 — 이 세션이 한 일은 알리지 않는다). 순서 고침이
    있으면 이 세션의 일로 바뀐 저장 차례를 본 차례로 옮긴다 — 안 옮기면 「다른 곳에서
    바뀌었습니다」 로 막히는데 거짓이다.
    """
    draft_before = load_draft()
    revisions = (
        [item.revision_id for item in repository.list_revisions(gone_scenario)]
        if gone_scenario is not None and has_edits(draft_before)
        else []
    )
    before = (
        tuple(item.scenario_id for item in repository.list_scenarios())
        if draft_before.order is not None
        else ()
    )

    def settle() -> None:
        draft = load_draft()
        if draft.order is not None:
            after = tuple(item.scenario_id for item in repository.list_scenarios())
            draft = rebased_order(draft, before, after)
        if gone_scenario is not None:
            draft = without_scenario(draft, gone_scenario, revisions)
        store_draft(draft)

    return settle


def _render_archived_scenarios(repository: DuckDBScenarioRepository) -> None:
    """「보관함」 칸. 되돌리기와 영구 삭제가 여기 모인다."""
    archived = [
        scenario
        for scenario in repository.list_scenarios(include_archived=True)
        if scenario.status != "ACTIVE"
    ]
    if not archived:
        st.caption("보관된 시나리오가 없습니다.")
        return
    by_id = {scenario.scenario_id: scenario for scenario in archived}
    # 되돌리거나 지운 보관본은 선택지에서 빠진다. 그 선택을 지우기만 하면 서버는 첫 보관본을
    # 쓰는데 브라우저는 처리한 이름을 계속 보여, 다음 「되돌리기」 가 보이지 않는 시나리오에
    # 걸린다. 매 회차 지금 선택지로 다시 적어 브라우저도 새 글자를 받게 한다. 고른 보관본이 빠져
    # 첫 보관본으로 바꾼 회차(와 그 창 안)의 「되돌리기」 는 바꾼 보관본에 걸지 않는다 — 빠른 두
    # 번 누름의 둘째나 남이 먼저 되돌린 보관본에서 누른 것이 고르지 않은 보관본까지
    # 되돌렸다(2026-10-27 E2E). 영구 삭제는 바꾼 보관본의 이름을 적어야 열려 그 꼴이 없다.
    choice = prune_named_choice(
        ARCHIVED_SELECT_KEY,
        {scenario_id: item.scenario_name for scenario_id, item in by_id.items()},
        default=next(iter(by_id)),
    )
    if choice.moved:
        _clear_gone_delete_confirm(by_id[choice.value].scenario_name)
    selected_id = st.selectbox(
        "보관본",
        options=list(by_id),
        format_func=lambda value: by_id[value].scenario_name,
        key=ARCHIVED_SELECT_KEY,
    )
    summary = by_id[selected_id]
    restore_column, _ = st.columns(2)
    with restore_column:
        if st.button(
            "되돌리기",
            icon=":material/unarchive:",
            width="stretch",
            key="scenario_archived_restore",
        ):
            if choice.moved:
                _refuse_gone_press()
            _restore_scenario(repository, summary)
    _render_delete(repository, summary)


def _clear_gone_delete_confirm(current_name: str) -> None:
    """고름이 옮은 회차 — 영구 삭제 확인 칸에 빠진 보관본의 이름이 남았으면 칸을 비운다(칸을 그리기
    전이라 새 값을 적는다). 지금 고른 보관본(`current_name`)의 이름이면 그대로 둔다.

    그 칸이 켠 「영구 삭제 실행」 을 이 회차에 눌렀으면 단추가 꺼져 그 누름이 말없이 버려진다(남이
    그 보관본을 먼저 되돌렸거나 지웠다). 그때만 아무것도 하지 않았다는 것을 알린다
    (`_refuse_gone_press` — 설계 규칙 UI-NTF-03). 다른 단추의 누름이나 입력으로 온 회차는 칸만
    비우고 잇는다 — 이 칸은 숨은 탭에서도 늘 돌아, 끊으면 그 회차의 다른 탭 누름(설비 시나리오 지정
    등)을 버린다. 이 세션이 방금 지우거나(`DELETE_CLEAR_KEY`) 되돌린 보관본이면(`held_flash`) 칸만
    비운다."""
    typed = st.session_state.get(DELETE_CONFIRM_KEY)
    if not isinstance(typed, str) or typed.strip() in ("", current_name):
        return
    st.session_state[DELETE_CONFIRM_KEY] = ""
    # 단추를 그리기 전이라 브라우저가 보낸 앞 회차 단추의 누름이 그대로 읽힌다 — 꺼진 채 그리면
    # Streamlit 이 그 누름을 지운다.
    if st.session_state.get(DELETE_BUTTON_KEY) is not True:
        return
    if st.session_state.get(DELETE_CLEAR_KEY) or held_flash(FLASH_KEY) is not None:
        return
    _refuse_gone_press()


def _refuse_gone_press(message: str = ARCHIVED_GONE_MESSAGE) -> NoReturn:
    """고른 시나리오가 그 사이 목록·보관함에서 빠진 회차의 누름 — 쓰지 않고 알린 뒤 다시 돈다.

    이 세션이 방금(`TRAILING_PRESS_SECONDS` 안) 보관·되돌리기·지우기를 한 것이면 같은 단추의 빠른
    둘째 누름이라 그 성공 알림을 다시 내고, 아니면 남이 먼저 처리한 것이라 그 사실(`message`)을
    알린다. 다시 도는 회차가 지금 목록·보관함을 그린다.
    """
    held = held_flash(FLASH_KEY)
    if held is not None:
        queue_flash(FLASH_KEY, held[0], icon=held[1])
    else:
        # 아무것도 쓰지 않았고 그 자리에 고칠 입력이 없다 — 알림창 · Alarm 에만 낸다(그리는 칸은
        # 누른 단추가 아니라 탭 맨 위다, 설계 규칙 UI-NTF-03).
        queue_flash(
            FLASH_WARNING_KEY, message, kind="warning", icon=":material/warning:", popup_only=True
        )
    st.rerun()


def _restore_scenario(
    repository: DuckDBScenarioRepository,
    summary: ScenarioSummary,
) -> None:
    message = (
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "목록으로 되돌렸습니다."
    )
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    notices = notice_marks()
    settle_draft = _draft_settler(repository)
    try:
        # 겹쳐 온 둘째 누름(첫 쓰기 전 목록을 그린 회차)은 저장소에 다시 가지 않는다 — 가면 이미
        # 되돌린 보관본이라 날 KeyError 가 섰다.
        save_once(
            ARCHIVED_RESTORE_SAVE_NAME,
            summary.scenario_id,
            lambda: repository.restore_scenario(summary.scenario_id),
            wrote=lambda _: True,
        )
    except KeyError:
        # 그 사이 남이 먼저 되돌렸거나 지웠다(저장소가 보관본을 찾지 못했다).
        _refuse_gone_press()
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    note_notice(notices, FLASH_KEY, message)
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    queue_flash(FLASH_KEY, message)
    settle_draft()
    st.rerun()


def _render_delete(repository: DuckDBScenarioRepository, summary: ScenarioSummary) -> None:
    """영구 삭제. 보관본에만 연다 — 되돌릴 수 없는 길을 한 단계 뒤에 둔다.

    지워질 양(리비전 수·공식 발행 이력 수)과 되돌릴 수 없다는 말을 **입력 칸 바로 위** 한 줄에
    둔다. 입력 칸은 빈 칸으로 선다 — 이름을 placeholder 로 깔면 이미 채워진 칸처럼 보였다.
    """
    st.warning(
        delete_scope_warning(
            len(repository.list_revisions(summary.scenario_id)),
            repository.count_official_releases(summary.scenario_id),
        ),
        icon=":material/delete_forever:",
    )
    if st.session_state.pop(DELETE_CLEAR_KEY, False):
        st.session_state[DELETE_CONFIRM_KEY] = ""
    # 라벨은 숨기고 같은 글을 바로 위에 보인다 — 위젯 라벨은 마크다운이라 이름을 막아 넘기면 그 막음
    # 글자(`\(`)가 낭독기 이름(aria-label)에 그대로 들었다. 숨긴 라벨은 평문 이름 그대로다.
    name = summary.scenario_name
    particle = object_particle(name)
    with st.container(gap="xxsmall"):
        st.markdown(f":small[확인: 「{literal_markdown(name)}」{particle} 그대로 입력하세요]")
        typed = st.text_input(
            f"확인: 「{name}」{particle} 그대로 입력하세요",
            key=DELETE_CONFIRM_KEY,
            placeholder="",
            label_visibility="collapsed",
        )
    ready = typed.strip() == summary.scenario_name
    if not st.button(
        f":red[{DELETE_BUTTON_LABEL}]" if ready else DELETE_BUTTON_LABEL,
        key=DELETE_BUTTON_KEY,
        icon=":material/delete_forever:",
        type="secondary",
        disabled=not ready,
        help=None if ready else DELETE_LOCK_HELP,
        width="stretch",
    ):
        return
    message = (
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "영구 삭제했습니다."
    )
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓴 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    notices = notice_marks()
    settle_draft = _draft_settler(repository, summary.scenario_id)
    try:
        # 「영구 삭제 실행」 을 빠르게 두 번 누르면 둘째 회차가 첫 삭제 전 목록(지울 보관본이 아직
        # 있다)을 그리고 저장소에 다시 가 날 KeyError(「'시나리오를 찾을 수 없습니다: …'」)를
        # 세웠고, 그 회차는 지운 보관본을 보관함에 그대로 보였다(2026-10-27 E2E). 같은 보관본의 겹쳐
        # 온 둘째 누름은 저장소에 가지 않고 첫 삭제의 뒷정리·알림을 잇는다.
        save_once(
            ARCHIVED_DELETE_SAVE_NAME,
            summary.scenario_id,
            lambda: repository.delete_scenario(summary.scenario_id),
            wrote=lambda _: True,
        )
    except KeyError:
        # 그 사이 남이 먼저 지웠다(저장소가 시나리오를 찾지 못했다).
        _refuse_gone_press()
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    # 첫 회차가 쓴 뒤 끊겨 알림을 담지 못해도 그 창 안의 회차가 다시 그린다(`flash.render_flash`).
    note_notice(notices, FLASH_KEY, message)
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    clear_global_comparison_scenario_cache()
    clear_global_main_cases_cache()
    # 입장 화면 Summary 의 GAP 도 그 비교 대상을 쓴다 — 이 세션은 곧바로 다시 확인한다.
    forget_intro_summary_check()
    # 지운 시나리오의 공식버전이 판정 기준의 미저장 기본값을 정했을 수 있다.
    clear_global_securement_threshold_cache()
    if summary.scenario_id == active_persisted_scenario_id():
        clear_persisted_scenario_activation()
    queue_flash(FLASH_KEY, message)
    settle_draft()
    for key in (ACTION_KEY, ACTION_OWNER_KEY):
        st.session_state.pop(key, None)
    st.session_state[DELETE_CLEAR_KEY] = True
    st.rerun()


def delete_scope_warning(revision_count: int, release_count: int) -> str:
    """영구 삭제 입력 칸 위 한 줄. 함께 지워질 리비전·공식 발행 이력의 수와 되돌릴 수 없다는 것."""
    if release_count:
        scope = f"리비전 {revision_count}개와 공식 이력 {release_count}건이"
    else:
        scope = f"리비전 {revision_count}개가"
    return f"영구 삭제하면 {scope} 함께 지워지고 되돌릴 수 없습니다."


def clone_field_key(field: str) -> str:
    """복제 폼 한 칸의 위젯 키. 저장에 성공할 때마다 세대가 바뀐다.

    **저장한 값이 폼에 남으면 한 번 더 눌러 같은 시나리오가 또 생긴다**(2026-10-01 브라우저
    재현). `clear_on_submit` 은 이름 중복 같은 **실패**에도 입력을 지워 쓰지 않는다. 세션 칸만
    지우면 브라우저가 옛 값을 다시 보내므로(`components/editor_state.py` 와 같은 사정) 성공한
    회차에만 키를 바꿔 새 빈 칸으로 세운다. 첫 세대도 꼬리를 단다(`scenario_create_name_g0`).
    """
    return widget_key(
        f"scenario_create_{field}", CLONE_FORM_GENERATION_KEY, style="_g", bare_zero=False
    )


def _untouched_clone_form(
    scenario_name: str, source_code: str, source_name: str, note: str, revision_name: str
) -> bool:
    """복제 폼이 새로 선 그대로인가 — 적은 칸이 하나도 없고 초기 리비전명이 든 값 그대로다."""
    typed = (scenario_name, source_code, source_name, note)
    return not any(value.strip() for value in typed) and (
        revision_name.strip() == CLONE_REVISION_NAME_DEFAULT
    )


def _render_clone(repository: DuckDBScenarioRepository) -> None:
    try:
        reference_tables, active_scenario = _current_reference_context()
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            f"신규 시나리오의 기준 표시순서를 준비하지 못했습니다: {bootstrap_error_message(exc)}",
            code="SC-02",
            tab=CAPA_SCENARIO_TAB_NAME,
            text="신규 시나리오의 기준 표시순서를 준비하지 못했습니다",
        )
        return
    # 무엇을 복제하는지는 「시나리오 작업」 줄 오른쪽 끝 값 글이다(`clone_target_caption`). 원천
    # 코드·이름 칸의 기본값은 비워 둔다 — 원천 시뮬레이션명은 공식버전 자동 갱신이 주차(W##)를 읽는
    # 두 번째 근거라, 복제본이 원본의 이름을 물려받으면 그 복제를 공식으로 지정했을 때 기준 주차가
    # 달라진다. 그 까닭은 두 칸 풍선이다.
    # 칸 key 의 세대가 저장 쓰기의 세대이기도 하다(`write_once_value`).
    create_generation = generation(CLONE_FORM_GENERATION_KEY)
    with st.form("scenario_create_form"):
        # 이름은 보관본을 포함해 겹칠 수 없다 — 검사는 저장소가 한다(`create_scenario`).
        scenario_name = st.text_input("시나리오명", key=clone_field_key("name"))
        source_code = st.text_input(
            "원천 시뮬레이션 코드", key=clone_field_key("source_code"), help=CLONE_SOURCE_NOTE
        )
        source_name = st.text_input(
            "원천 시뮬레이션명", key=clone_field_key("source_name"), help=CLONE_SOURCE_NOTE
        )
        revision_name = st.text_input(
            "초기 리비전명",
            value=CLONE_REVISION_NAME_DEFAULT,
            key=clone_field_key("revision_name"),
        )
        note = st.text_area("메모", height=100, key=clone_field_key("note"))
        create_submitted = st.form_submit_button(
            "신규 시나리오 저장",
            icon=":material/save:",
            type="primary",
            width="stretch",
        )
    if not create_submitted:
        return
    untouched = _untouched_clone_form(scenario_name, source_code, source_name, note, revision_name)
    if untouched and just_written(CLONE_FORM_GENERATION_KEY):
        # 느린 두 번 누름의 꼬리 — 둘째 누름이 저장 뒤 새로 선 빈 폼에 닿았다
        # (`write_guard.just_written`). 첫 저장의 성공 알림은 맨 위 칸이 이 회차에도 같은 id 로
        # 다시 보내므로 「필수 칸이 비어 있습니다」 를 그 자리에 세우지 않는다. 창이 지난 빈 제출은
        # 그대로 거절한다.
        return
    # 빈 필수 칸을 **한 번에** 모두 알린다. 저장소 검사에 맡기면 한 번에 한 칸씩만 말해 세 번
    # 눌러야 했다(2026-10-05 E2E). 저장소 검사는 그대로 마지막 방어선이다.
    missing = [
        label
        for label, value in (
            ("시나리오명", scenario_name),
            ("원천 시뮬레이션 코드", source_code),
            ("원천 시뮬레이션명", source_name),
            ("초기 리비전명", revision_name),
        )
        if not value.strip()
    ]
    if missing:
        st.error(f"필수 칸이 비어 있습니다: {', '.join(missing)}")
        return
    try:
        # 지금 편집본(기준정보 16표)을 새 데이터셋으로 통째로 복제한다. 표가 크면 몇 초가 걸린다.
        with st.spinner("지금 편집본을 새 시나리오로 복제하는 중입니다..."):
            # 지금 편집본이 새 시나리오의 초기 리비전이 된다 — 리비전 저장과 같은 검사다.
            verdict = revision_save_verdict(
                get_effective_reference_version(),
                active_scenario,
                reference_tables,
                labels=get_process_labels,
            )
            if not verdict.allowed:
                st.error(markdown_safe_tildes(verdict.message))
                return
            revision_source = revision_tables_for_save(active_scenario, reference_tables)
            preset = _compatible_preset(capture_scenario_preset(revision_source), revision_source)
            parent_revision_id = active_persisted_revision_id()
            virtual_products = revision_virtual_product_rows(
                repository, parent_revision_id, revision_source
            )
            request = ScenarioCreate(
                scenario_name=scenario_name,
                source_simulation_code=source_code,
                source_simulation_name=source_name,
                source_type="DUCKDB_SCENARIO_CLONE",
                pipeline_version=CLONE_PIPELINE_VERSION,
                source_registered_at=None,
            )
            note_text = note.strip() or None
            # 같은 세대·같은 입력의 저장은 한 번만 쓴다 — 스피너 도는 동안 한 번 더 누른 둘째
            # 회차는 쓰지 않고(같은 이름이라 「이미 있는 이름」 으로 거절됐다), 첫 회차가 만든
            # 시나리오로 끊긴 뒷정리를 잇는다. 지문은 복제하는 편집본(토큰·리비전)과 적은 칸이다 —
            # 끊긴 쓰기 뒤 다른 이름이나 편집으로 누른 저장은 새로 쓴다. 입력은 모두 위에서 읽었다.
            written = write_once_value(
                CLONE_FORM_GENERATION_KEY,
                create_generation,
                lambda: repository.create_scenario(
                    request,
                    reference_tables,
                    preset,
                    source_data=None,
                    revision_tables=revision_source,
                    revision_name=revision_name,
                    note=note_text,
                    virtual_products=virtual_products,
                ),
                fingerprint=(
                    active_scenario["content_token"],
                    parent_revision_id,
                    scenario_name,
                    source_code,
                    source_name,
                    revision_name,
                    note_text,
                ),
            )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
    else:
        if written is None:
            return
        snapshot = written.value
        if snapshot is None:
            queue_flash(FLASH_KEY, "신규 시나리오를 저장했습니다.")
        else:
            # 내용은 지금 편집본 그대로지만 **다른 시나리오**가 된다 — 시나리오를 바꾸는 경로처럼
            # HOME 토글을 푼다.
            activate_persisted_snapshot(snapshot)
            follow_created_scenario(repository, snapshot.scenario.scenario_id)
            queue_flash(
                FLASH_KEY,
                f"{literal_markdown(snapshot.scenario.scenario_name)}"
                f"{object_particle(snapshot.scenario.scenario_name)} 저장했습니다."
                + virtual_product_save_notice(len(virtual_products)),
            )
        if verdict.message:
            # 계산 검사 경고(`capacity_gate`)는 오류의 예시 키(편집한 칸 값)를 날로 담는다 — 알림
            # 글(마크다운 원문)에서 물결표가 지움선이 되지 않게 막는다. 복제는 끝났고 고칠 입력이
            # 이 자리에 없어 알림창 · Alarm 에만 낸다 — 소요대수에 들지 않은 수요(2026-11-04 검수
            # 의견 home-18)도, 남은 계산 오류(설계 규칙 AMB-05 (나))도 사이드바 리비전 저장과 한
            # 꼴이다.
            # 소요대수에 들지 않은 수요의 「그 화면으로」 는 새 시나리오의 초기 리비전을 고른 목록
            # 관리 「점검」 칸이다(같은 리비전 · 전체 기간 — 검토 보드 F4 (나)).
            queue_flash(
                FLASH_WARNING_KEY,
                markdown_safe_tildes(verdict.message),
                kind="warning",
                icon=":material/warning:",
                popup_only=True,
                goto=REQUIRED_TAB_GOTO if verdict.exclusion else None,
                target=(
                    required_check_target(
                        snapshot.scenario.scenario_id if snapshot is not None else None,
                        snapshot.revision.revision_id if snapshot is not None else None,
                    )
                    if verdict.exclusion
                    else None
                ),
            )
        # 꼬리 누름의 창(`just_written`)은 뒷정리를 마친 이 시각부터 센다 — 쓰기 시각부터 세면 큰
        # 편집본의 활성화가 그 창을 먹어 새 빈 폼이 선 뒤에는 남지 않는다.
        note_written(CLONE_FORM_GENERATION_KEY)
        bump(CLONE_FORM_GENERATION_KEY)
        written.release()
        st.rerun()


def clone_target_caption() -> str:
    """복제 작업의 값 글 — 「복제 대상 · 「이름」 rN」, 저장하지 않은 편집이 함께 들어가면 그 표지
    배지(「미저장 편집 포함」)를 붙인다(설계 규칙 UI-TXT-04 — 값 · 표지만). 「시나리오 작업」 전환
    단추 줄 오른쪽 끝에 선다."""
    label = active_scenario_label()
    target = (
        "올라와 있는 편집본"
        if label is None
        else f"「{literal_markdown(label.scenario_name)}」 r{label.revision_no}"
    )
    unsaved = " · :orange-badge[미저장 편집 포함]" if has_unsaved_scenario_changes() else ""
    return f"복제 대상 · {target}{unsaved}"


def revision_virtual_product_rows(
    repository: DuckDBScenarioRepository,
    parent_revision_id: str | None,
    revision_tables: Mapping[str, pd.DataFrame],
) -> list[dict[str, str]]:
    """새 리비전에 남길 가상 제품 이력을 저장소가 받는 행으로 만든다.

    부모 리비전(세션이 불러온 리비전, 복제라면 복제하는 활성 리비전)의 이력에 이 세션이 복제
    등록한 가상 제품을 더한다(`inherit_virtual_product_records` — 같은 키는 한 건, 저장할 표에서
    사라진 부모 제품은 뺀다). 부모가 없는 세션(내장 시드)은 세션 등록만 남는다.

    저장한 스냅샷을 활성화하면 세션 목록이 비므로(`clear_virtual_products`) 저장 **전에**
    읽고, 알림의 건수도 이 결과에서 센다. 새 리비전을 남기는 저장 단추(사이드바 팝업의 새 리비전
    저장, 이 페이지의 복제)가 모두 이것을 넘겨야 가상 제품 출처가 DB 에 이어진다.
    """
    parent = (
        virtual_product_records(repository.list_virtual_products(parent_revision_id))
        if parent_revision_id is not None
        else ()
    )
    records = inherit_virtual_product_records(
        parent,
        cast(tuple[VirtualProductRecord, ...], session_virtual_products()),
        revision_tables,
    )
    return [
        {
            "product": record.product,
            "stack": record.stack,
            "source_product": record.source_product,
            "source_stack": record.source_stack,
        }
        for record in records
    ]


def virtual_product_save_notice(count: int) -> str:
    """저장 알림 뒤에 붙일 가상 제품 확인 문장. 없으면 빈 문자열이라 알림이 그대로다."""
    if not count:
        return ""
    return (
        f" 가상 제품 {count}건이 포함되어 있습니다. "
        "실적과 대조할 수 없으므로 공식버전으로 지정하기 전에 확인하세요."
    )


def revision_tables_for_save(
    active_scenario: ActiveScenario,
    _reference_tables: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    return {
        name: active_scenario["tables"][name]
        for name in REVISION_TABLES
        if name in active_scenario["tables"]
    }


def _current_reference_context() -> tuple[dict[str, pd.DataFrame], ActiveScenario]:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    return reference_tables, ensure_active_scenario(reference_tables, reference_version)


def _compatible_preset(
    preset: ScenarioPreset,
    reference_tables: dict[str, pd.DataFrame],
) -> ScenarioPreset:
    available = set(
        reference_tables["RQ_REQB"]["공정"].astype("string").str.strip().dropna().tolist()
    )
    return replace(
        preset,
        included_processes=tuple(
            process for process in preset.included_processes if process in available
        ),
    )
