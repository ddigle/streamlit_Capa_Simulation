# Purpose: 시나리오 목록·리비전 표를 바로 고치는 관리 화면과 복제·월 머지·연도 Shift 작업을 그린다.

"""시나리오 관리 탭 — 목록 관리(C안)·지금 편집본 복제·월 머지·연도 Shift.

「목록 관리」가 시나리오를 다루는 단일 입구다(2026-10-22 사용자 결정 C안). 지금 구조(모드·목록
편집표·고른 시나리오 카드)를 두고 **표 안에서 바로 고친다** —

- 목록 편집표: 시나리오명(✎)과 순서를 고쳐 표 위 「변경 저장」 한 번으로 쓴다(하나라도 거부되면
  아무것도 쓰지 않는다). 순서 칸에 자리 번호를 넣으면 그 자리로 끼워 넣고, 고른 시나리오는 위로·
  아래로·맨 위로 단추로도 옮긴다.
- 고른 시나리오 카드: 리비전 편집표(고름 하나·리비전명 ✎)와 그 위 작업 줄 — 불러오기·공식으로
  지정…(확인 팝업)·이름 저장·편집 버리기. 보관은 카드 제목 오른쪽 「보관…」.
- 카드 아래 늘 있는 접힘 칸 둘 — 공식 발행 이력, 보관된 시나리오.

두 편집표의 고름·미저장 편집은 행 id 로 세션 초안에 둔다(`components/pick_edit_table.py`) — 다른
행을 골라도 이름·순서 편집을 잃지 않고, 다른 세션이 차례를 바꿔도 편집이 엉뚱한 행에 붙지 않는다.
새 리비전 저장은 사이드바 시나리오 팝업 한 곳이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.components.capacity_gate import official_publish_verdict, revision_save_verdict
from capa_simulation.components.editor_state import discard_editor
from capa_simulation.components.intro_summary import forget_intro_summary_check
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.pick_edit_table import (
    TableColumns,
    TableDraft,
    changed_names,
    drop_names,
    forget_table,
    forget_table_edits,
    move_row,
    moved_count,
    moved_names,
    peek_table,
    remount_table,
    repick_table,
    settle_table,
    store_draft,
    table_rows,
    with_order,
)
from capa_simulation.components.revision_label import revision_label
from capa_simulation.components.scenario_month_merge import (
    MERGE_SOURCE_ROLES,
    render_scenario_month_merge,
)
from capa_simulation.components.scenario_transform import forget_derived_sources
from capa_simulation.components.scenario_year_shift import (
    SHIFT_SOURCE_ROLES,
    render_scenario_year_shift,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    forget_page_dialogs,
    prune_choice,
)
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.cache import (
    clear_global_comparison_scenario_cache,
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
    REVISION_TABLES,
    BatchEditRefused,
    DuckDBScenarioRepository,
    OfficialReleaseMoved,
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
from capa_simulation.services.builtin_seed import BUILTIN_SEED_SOURCE_CODE
from capa_simulation.services.korean_particle import object_particle
from capa_simulation.services.revision_compatibility import revision_block_reason
from capa_simulation.services.scenario_virtual_products import (
    inherit_virtual_product_records,
    virtual_product_records,
)
from capa_simulation.services.virtual_product import VirtualProductRecord

CLONE_PIPELINE_VERSION = "duckdb-rq-snapshot-v3"
FLASH_KEY = "scenario_management_flash"
# 성공 알림과 함께 띄울 경고. 저장은 됐지만 남은 계산 오류가 있을 때 쓴다.
FLASH_WARNING_KEY = "scenario_management_flash_warning"
MODE_KEY = "scenario_page_mode"
CLONE_MODE = "지금 편집본 복제"
MODES = (
    "목록 관리",
    CLONE_MODE,
    "월 머지",
    "연도 Shift",
)
# 새 리비전 저장은 사이드바 시나리오 팝업 한 곳이다(2026-10-22 사용자 결정 S8). 모드 줄 바로 아래에
# 그 길을 늘 적는다.
REVISION_SAVE_GUIDE = (
    "새 리비전 저장은 사이드바 「시나리오」 칸을 눌러 여는 팝업의 「새 리비전 저장」에서 합니다."
)
# 원본 리비전을 메모해 두는 모드와 그 역할(`scenario_transform.SOURCE_MEMO_KEY`).
DERIVED_SOURCE_ROLES: dict[str, tuple[str, ...]] = {
    "월 머지": MERGE_SOURCE_ROLES,
    "연도 Shift": SHIFT_SOURCE_ROLES,
}
LIST_EDITOR_KEY = "scenario_list_editor"
# 목록 편집표 위 결과·오류 칸(종류, 글). 콜백이 적고 다음 회차에 늘 서 있는 칸 안에 한 번 그린다.
LIST_NOTICE_KEY = "scenario_list_notice"
ACTION_KEY = "scenario_list_action"
ACTION_OWNER_KEY = "scenario_list_action_owner"
DELETE_CONFIRM_KEY = "scenario_list_delete_confirm"
# 영구 삭제 확인 칸을 다음 회차에 비우라는 표지. 삭제는 칸을 그린 **뒤**에 일어나 그 회차에는 칸을
# 바꿀 수 없고, 칸을 지우기(`pop`)만 하면 브라우저가 지운 이름을 계속 보인다. 다음 회차 칸 앞에서
# 빈 값을 적는다(AGENTS 9장 「pop 하지 말고 새 값을 적는다」).
DELETE_CLEAR_KEY = "scenario_list_delete_confirm_clear"
ARCHIVE_CONFIRM_KEY = "scenario_list_archive_confirm"
# 가상 제품이 든 리비전을 공식버전으로 지정할 때의 확인 체크. 리비전마다 따로 받는다
# (`official_confirm_key`).
OFFICIAL_CONFIRM_KEY = "scenario_list_official_virtual_confirm"
ARCHIVED_SELECT_KEY = "scenario_list_archived_id"
# 접힘 칸의 key. 위젯이 아니라 브라우저가 펼침을 기억하는 이름이다(`_render_archived_scenarios`).
ARCHIVED_EXPANDER_KEY = "scenario_list_archived_expander"
HISTORY_EXPANDER_KEY = "scenario_list_history_expander"
# 공식 발행 이력 칸에 보이는 최근 건수.
HISTORY_LIMIT = 20
IDENTIFIER_EXPANDER_KEY = "scenario_store_identifier_expander"
# 복제 폼 입력칸의 세대. 저장에 성공하면 올라 다음 회차에 빈 폼으로 선다(`clone_field_key`).
CLONE_FORM_GENERATION_KEY = "scenario_create_form_generation"
# 고른 시나리오 카드의 리비전 편집표. 고른 리비전은 이 표 초안의 `picked` 다(행 id 라 리비전명이
# 바뀌어도 고른 대상이 그대로다).
REVISION_EDITOR_KEY = "scenario_revision_editor"
# 카드 작업 줄 아래 결과·오류 칸(종류, 글).
CARD_NOTICE_KEY = "scenario_card_notice"
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
SELECT_COLUMN = "선택"
ORDER_COLUMN = "순서"
NAME_COLUMN = "시나리오명"
LIST_COLUMNS = TableColumns(pick=SELECT_COLUMN, name=NAME_COLUMN, order=ORDER_COLUMN)
REVISION_PICK_COLUMN = "고름"
REVISION_NAME_COLUMN = "리비전명"
REVISION_COLUMNS = TableColumns(pick=REVISION_PICK_COLUMN, name=REVISION_NAME_COLUMN)


def render_scenario_management(
    repository: DuckDBScenarioRepository,
    database_path: str,
) -> None:
    # 저장소 생성자는 프로세스 캐시라 따뜻한 프로세스에서는 페이지 준비 단계가 DB 를 열지 않는다.
    # 이 읽기가 그 회차의 첫 DB 열기이므로 다른 프로그램의 파일 잠금도 여기서 안내로 받는다.
    try:
        scenarios = repository.list_scenarios()
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    _render_store_status(repository, scenarios)
    # 작업 이름이 바뀌었으므로 예전 세션에 남은 값은 위젯이 만들어지기 전에 버린다.
    # 옵션에 없는 값이 그대로 오면 Streamlit 이 선택을 잃고 필수 선택에서 막힌다.
    if st.session_state.get(MODE_KEY) not in MODES:
        st.session_state.pop(MODE_KEY, None)
    mode = st.segmented_control(
        "시나리오 작업",
        list(MODES),
        default=MODES[0],
        key=MODE_KEY,
        persist_state="session",
        # 선택 해제를 허용하면 mode 가 None 이 되어 아무 작업도 그리지 않는다.
        required=True,
    )
    st.caption(REVISION_SAVE_GUIDE)
    # 월 머지·연도 Shift 가 메모한 원본(리비전 하나 크기의 살아 있는 표)은 그 모드에서만 둔다.
    forget_derived_sources(keep=DERIVED_SOURCE_ROLES.get(str(mode), ()))
    if mode == "목록 관리":
        _render_list_management(repository, database_path, scenarios)
    elif mode == CLONE_MODE:
        _render_clone(repository)
    elif mode == "월 머지":
        render_scenario_month_merge(repository, database_path)
    elif mode == "연도 Shift":
        render_scenario_year_shift(repository, database_path)


def _render_store_status(
    repository: DuckDBScenarioRepository,
    scenarios: list[ScenarioSummary],
) -> None:
    # 알림은 늘 서 있는 한 칸 안에 그린다(AGENTS 9장 「key 가 있어도 자리는 고정한다」). 형제
    # 자리에 바로 그리면 알림이 생기는 회차에 그 아래가 한 칸 밀린다 — 보관함의 「되돌리기」·
    # 「영구 삭제」는 본문에서 `st.rerun()` 으로 회차를 끊으므로, 끊긴 회차의 key 있는 보관함
    # 상자가 옛 자리에 흐린 사본으로 남아 모드를 바꿔도 새로고침 전까지 따라왔다(2026-10-22 사본
    # 앱 이분 탐색 — 알림을 빼거나 상자 key 를 빼거나 되돌리기를 콜백으로 바꾸면 각각 사라졌다).
    notice = st.container()
    flash = st.session_state.pop(FLASH_KEY, None)
    if isinstance(flash, str):
        notice.success(flash)
    warning = st.session_state.pop(FLASH_WARNING_KEY, None)
    if isinstance(warning, str):
        notice.warning(warning, icon=":material/warning:")
    official = repository.latest_official_release()
    with st.container(border=True):
        st.markdown("#### :material/database: 저장소 상태")
        active_id = active_persisted_scenario_id()
        active_revision_id = active_persisted_revision_id()
        if active_id and active_revision_id:
            st.write(_active_scenario_line(repository, scenarios, active_id, active_revision_id))
            # UUID 는 사람이 읽을 것이 아니라 장애를 신고할 때 적어 보낼 값이다. 상태 줄에
            # 그대로 두면 정작 어느 시나리오인지가 안 읽혀 접어 둔다.
            with st.expander("식별자", icon=":material/tag:", key=IDENTIFIER_EXPANDER_KEY):
                st.caption(f"시나리오 ID `{active_id}`")
                st.caption(f"리비전 ID `{active_revision_id}`")
        else:
            st.write("지금 올라와 있는 저장 리비전이 없습니다.")
        if official is None:
            st.warning("공식버전이 없습니다. 새 웹 세션에서 자동으로 불러올 기준이 없습니다.")
        else:
            st.success(
                f"최신 공식 v{official.release_no} · {literal_markdown(official.scenario_name)} "
                f"r{official.revision_no} · {literal_markdown(official.release_name)}"
            )
            if official.source_simulation_code == BUILTIN_SEED_SOURCE_CODE:
                st.info(
                    "현재 공식버전은 GitHub 독립 실행용 합성 DEMO 데이터입니다. "
                    "운영 전 BigDataQuery 등록으로 실제 시나리오를 만들어 새 공식버전으로 "
                    "지정하세요."
                )


def _active_scenario_line(
    repository: DuckDBScenarioRepository,
    scenarios: list[ScenarioSummary],
    active_id: str,
    active_revision_id: str,
) -> str:
    """올라와 있는 시나리오·리비전을 사람이 읽는 이름으로 적는다. 이름을 못 찾으면 ID 로 적는다.

    `st.write` 가 마크다운으로 그리므로 사람이 적은 이름은 `literal_markdown` 으로 싣는다.
    """
    scenario = next((item for item in scenarios if item.scenario_id == active_id), None)
    scenario_text = scenario.scenario_name if scenario is not None else active_id
    revision_text = active_revision_id
    if scenario is not None:
        revision = next(
            (
                item
                for item in repository.list_revisions(active_id)
                if item.revision_id == active_revision_id
            ),
            None,
        )
        if revision is not None:
            revision_text = revision_label(revision)
    dirty = " · :orange-badge[저장하지 않은 변경 있음]" if has_unsaved_scenario_changes() else ""
    return (
        f"올라와 있음 · **{literal_markdown(scenario_text)}** · "
        f"{literal_markdown(revision_text)}{dirty}"
    )


def _render_list_management(
    repository: DuckDBScenarioRepository,
    database_path: str,
    scenarios: list[ScenarioSummary],
) -> None:
    """목록 관리. 자리는 늘 같다 — 작업 줄 · 결과 칸 · 목록 표 · 카드 칸 · 접힘 칸 둘.

    작업 줄·결과 알림·고른 시나리오 카드는 생기고 사라져도 늘 서 있는 한 칸 안에 그린다. 그래야 아래
    key 있는 접힘 칸 둘의 순번이 밀리지 않는다(AGENTS 9장 「key 가 있어도 자리는 고정한다」 — 보관함
    유령 칸, 2026-10-22).
    """
    releases = repository.list_official_releases()
    base_ids = [scenario.scenario_id for scenario in scenarios]
    base_names = {scenario.scenario_id: scenario.scenario_name for scenario in scenarios}
    draft, widget_key = settle_table(LIST_EDITOR_KEY, base_ids, base_names, LIST_COLUMNS)
    with st.container():
        if scenarios:
            _render_list_toolbar(database_path, base_ids, base_names, draft)
    _render_notice(LIST_NOTICE_KEY)
    if scenarios:
        _render_scenario_list_editor(scenarios, releases, draft, widget_key)
    else:
        st.info("저장된 시나리오가 없습니다. 초기 이관 또는 신규 등록이 필요합니다.")
    dialog_shown = False
    with st.container():
        if draft.picked is not None:
            summary = next(item for item in scenarios if item.scenario_id == draft.picked)
            dialog_shown = _render_scenario_actions(repository, database_path, summary, releases)
        elif scenarios:
            st.caption(
                "표에서 시나리오 한 건을 고르면 그 리비전 표와 불러오기·공식으로 지정·이름 저장·"
                "보관이 나옵니다."
            )
    if not dialog_shown:
        st.session_state.pop(OFFICIAL_DIALOG_KEY, None)
    _render_official_history(releases)
    _render_archived_scenarios(repository)


def _render_notice(key: str) -> None:
    """콜백이 남긴 결과·오류(`(종류, 글)`)를 늘 서 있는 한 칸 안에 한 번 그린다."""
    slot = st.container()
    notice = st.session_state.pop(key, None)
    if not (isinstance(notice, tuple) and len(notice) == 2):
        return
    kind, text = notice
    if kind == "success":
        slot.success(str(text), icon=":material/check_circle:")
    elif kind == "error":
        slot.error(str(text), icon=":material/block:")
    else:
        slot.info(str(text))


def _render_list_toolbar(
    database_path: str,
    base_ids: Sequence[str],
    base_names: Mapping[str, str],
    draft: TableDraft,
) -> None:
    """목록 표 **위** 작업 줄(2026-09-29 — 적용 버튼은 표 위). 고친 것이 있을 때만 저장이 열린다.

    순서 바꾸기는 두 길이다 — 순서 칸에 자리 번호를 넣어 끼워 넣기, 고른 시나리오를 위로·아래로·
    맨 위로. 둘 다 미저장 순서 편집으로 쌓이고 이름 편집과 같은 「변경 저장」 한 번으로 쓴다.
    """
    renames = changed_names(draft, base_names)
    moved = moved_count(draft, base_ids)
    edited = bool(renames) or moved > 0
    rows = table_rows(draft, base_ids)
    place = rows.index(draft.picked) if draft.picked in rows else None
    args = (tuple(base_ids), dict(base_names))
    with st.container(horizontal=True, gap="small", vertical_alignment="center"):
        st.button(
            "변경 저장",
            icon=":material/save:",
            type="primary",
            disabled=not edited,
            key="scenario_list_save",
            on_click=_save_list_edits,
            args=(database_path, *args),
        )
        st.button(
            "편집 버리기",
            icon=":material/undo:",
            disabled=not edited,
            key="scenario_list_discard",
            on_click=forget_table_edits,
            args=(LIST_EDITOR_KEY,),
        )
        st.button(
            "위로",
            icon=":material/arrow_upward:",
            disabled=place is None or place == 0,
            key="scenario_list_up",
            on_click=_move_picked_scenario,
            args=(*args, -1),
            help="고른 시나리오를 한 칸 위로 옮깁니다. 「변경 저장」을 눌러야 저장됩니다.",
        )
        st.button(
            "아래로",
            icon=":material/arrow_downward:",
            disabled=place is None or place == len(rows) - 1,
            key="scenario_list_down",
            on_click=_move_picked_scenario,
            args=(*args, 1),
            help="고른 시나리오를 한 칸 아래로 옮깁니다. 「변경 저장」을 눌러야 저장됩니다.",
        )
        st.button(
            "맨 위로",
            icon=":material/vertical_align_top:",
            disabled=place is None or place == 0,
            key="scenario_list_top",
            on_click=_move_picked_scenario,
            args=(*args, None),
            help="고른 시나리오를 맨 위로 옮깁니다. 「변경 저장」을 눌러야 저장됩니다.",
        )
    st.caption(list_edit_caption(len(renames), moved))
    stale = moved_names(draft, base_names)
    if stale:
        st.warning(
            moved_names_warning(
                [
                    (_row_place(f"{rows.index(row_id) + 1}행", draft.names[row_id]), current)
                    for row_id, current in stale.items()
                    if row_id in rows
                ]
            ),
            icon=":material/warning:",
        )


def moved_names_warning(lines: Sequence[tuple[str, str]]) -> str:
    """저장 전 미리 알림 — 보고 고친 뒤 다른 곳에서 먼저 바뀐 이름. 줄마다 (행 표지, 지금 이름)."""
    head = (
        "다른 사용자가 먼저 이름을 바꿨습니다 — 저장하면 거부되고 그 칸은 지금 이름으로 돌아갑니다."
    )
    return "\n".join(
        [head, *(f"- {place}{literal_markdown(f'(지금: {current})')}" for place, current in lines)]
    )


def list_edit_caption(rename_count: int, moved: int) -> str:
    """작업 줄 아래 한 줄 — 무엇을 바로 고칠 수 있는지와 지금 고친 수."""
    return (
        "시나리오명·순서 칸을 바로 고칩니다(순서 칸에 자리 번호를 넣으면 그 자리로 끼워 "
        "넣습니다) · "
        f"고친 것: 이름 {rename_count} · 순서 {moved}"
    )


def _move_picked_scenario(
    base_ids: Sequence[str], base_names: Mapping[str, str], step: int | None
) -> None:
    """고른 시나리오를 한 칸 위·아래(`step`) 또는 맨 위(`None`)로 옮긴다(미저장 순서 편집)."""
    draft = peek_table(LIST_EDITOR_KEY, base_ids, base_names, LIST_COLUMNS)
    rows = table_rows(draft, base_ids)
    if draft.picked is None or draft.picked not in rows:
        return
    index = 0 if step is None else rows.index(draft.picked) + step
    order = move_row(rows, draft.picked, index)
    remount_table(LIST_EDITOR_KEY, with_order(draft, order, base_ids))


def _save_list_edits(
    database_path: str, base_ids: Sequence[str], base_names: Mapping[str, str]
) -> None:
    """「변경 저장」 콜백. 이름·순서 편집을 한 트랜잭션으로 쓴다. 하나라도 거부되면 쓰지 않는다.

    이름은 비교 후 쓰기(보고 고친 이름 = 초안의 `name_base` — 그 칸을 처음 고칠 때 표가 보인
    이름), 순서는 처음 고칠 때의 저장 차례(`order_base`)와 지금 차례가 같을 때만 쓴다. 차례가
    바뀌어 거부되면 순서 편집만 버려 지금 차례로 표를 다시 세운다(이름 편집은 행 id 로 남는다).
    다른 사용자가 먼저 바꿔 거부된 이름은 그 행의 이름 편집만 버려 지금 이름을 다시 보인다. 콜백이라
    본문 `st.rerun()` 이 없고, DB 핀을 스스로 잡는다.
    """
    draft = peek_table(LIST_EDITOR_KEY, base_ids, base_names, LIST_COLUMNS)
    renames = changed_names(draft, base_names)
    if not renames and draft.order is None:
        st.session_state[LIST_NOTICE_KEY] = ("info", "고친 것이 없습니다.")
        return
    try:
        with pinned_connections(Path(database_path)):
            get_scenario_repository(database_path).apply_scenario_list_edits(
                renames, draft.order, expected_order=draft.order_base
            )
    except BatchEditRefused as exc:
        rows = table_rows(draft, base_ids)
        st.session_state[LIST_NOTICE_KEY] = (
            "error",
            refused_edits_message(
                [
                    (
                        _row_place(
                            f"{rows.index(row_id) + 1}행",
                            draft.names.get(row_id) or base_names[row_id],
                        )
                        if row_id is not None and row_id in rows
                        else None,
                        message,
                    )
                    for row_id, message in exc.problems
                ],
                reloaded=bool(exc.moved_names),
            ),
        )
        order_refused = any(row_id is None for row_id, _ in exc.problems)
        if order_refused or exc.moved_names:
            kept = drop_names(draft, exc.moved_names)
            if order_refused:
                kept = replace(kept, order=None, order_base=None)
            remount_table(LIST_EDITOR_KEY, kept)
        else:
            store_draft(LIST_EDITOR_KEY, draft)
        return
    except BOOTSTRAP_ERRORS as exc:
        st.session_state[LIST_NOTICE_KEY] = ("error", bootstrap_error_message(exc))
        store_draft(LIST_EDITOR_KEY, draft)
        return
    if renames:
        # 스냅샷 payload 는 시나리오명을 함께 담는다. 비우지 않으면 그 리비전에서 파생한 시나리오의
        # 원천명·출처 메모에 옛 이름이 남는다. 비교 대상이 이 시나리오면 저장소가 그 프로필
        # version 을 올렸다 — 입장 화면 Summary GAP 풍선의 이름이 바뀐다(캐시는 경로 키라 따로
        # 비우고, 이 세션은 곧바로 다시 확인한다). 머리 띠의 시나리오명은 활성화 때 떠 둔 값이다.
        clear_scenario_snapshot_cache()
        forget_derived_sources()
        clear_global_comparison_scenario_cache()
        forget_intro_summary_check()
        for scenario_id, (_, renamed) in renames.items():
            rename_active_scenario_label(scenario_id, renamed)
    forget_table_edits(LIST_EDITOR_KEY)
    st.session_state[LIST_NOTICE_KEY] = (
        "success",
        list_saved_message(len(renames), reordered=draft.order is not None),
    )


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


def list_saved_message(rename_count: int, *, reordered: bool) -> str:
    if rename_count and reordered:
        return f"시나리오명 {rename_count}건과 누적 순서를 저장했습니다."
    if rename_count:
        return f"시나리오명 {rename_count}건을 저장했습니다."
    return "누적 순서를 저장했습니다."


def _render_scenario_list_editor(
    scenarios: Sequence[ScenarioSummary],
    releases: Sequence[OfficialReleaseSummary],
    draft: TableDraft,
    widget_key: str,
) -> None:
    """누적 목록 편집표. 고름·순서·시나리오명(✎)만 고치고 나머지는 읽기 전용이다.

    그리는 값은 초안이다(고친 이름·차례·고른 행). 편집은 다음 회차 머리에서 `settle_table` 이
    접는다 — 이 함수는 돌려받는 프레임을 쓰지 않는다.

    「최신 리비전」은 그 시나리오에 마지막으로 저장한 리비전이다(`active_revision_no`). 이 세션에
    올라와 있는 리비전은 위 저장소 상태 줄이 말한다 — 「활성 리비전」이라 부르던 때는 그 둘이 같은
    것으로 읽혀, 「r5 | v5 · 최신」이 r5 를 공식으로 오독하게 했다. 그래서 공식 칸에 공식 리비전
    번호를 함께 적는다(`_official_label`).
    """
    # 발행 이력은 최신 번호가 먼저 온다. 시나리오마다 첫 번째가 그 시나리오의 최신 공식이다.
    official_by_scenario: dict[str, OfficialReleaseSummary] = {}
    for release in releases:
        official_by_scenario.setdefault(release.scenario_id, release)
    # 최신 공식 시나리오는 기본 진입점이라 보관·삭제가 막힌다. 눌러 보고 알게 하지 않는다.
    latest_official_scenario = releases[0].scenario_id if releases else None
    by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    rows = table_rows(draft, list(by_id))
    table = pd.DataFrame(
        {
            SELECT_COLUMN: [row_id == draft.picked for row_id in rows],
            ORDER_COLUMN: range(1, len(rows) + 1),
            NAME_COLUMN: [draft.names.get(row_id, by_id[row_id].scenario_name) for row_id in rows],
            "원천 코드": [by_id[row_id].source_simulation_code for row_id in rows],
            "최신 리비전": [f"r{by_id[row_id].active_revision_no}" for row_id in rows],
            "공식버전": [
                _official_label(row_id, official_by_scenario, latest_official_scenario)
                for row_id in rows
            ],
            "최근 수정": [by_id[row_id].updated_at for row_id in rows],
        },
        index=pd.Index(rows, name="scenario_id"),
    )
    st.data_editor(
        table,
        key=widget_key,
        placeholder="",
        num_rows="fixed",
        hide_index=True,
        width="stretch",
        # 체크박스 한 칸, 두 자리 숫자, `r12` 는 `small` 로도 필요 이상 넓다. 남는 폭은
        # 실제로 길어질 수 있는 시나리오명·원천 코드가 가져가는 편이 읽기 좋다.
        #
        # 픽셀 값은 **최소 폭이 아니라 비율**이다. 합이 표 폭보다 작으면 Streamlit 이
        # 남는 폭을 비례로 나눠 준다. 그래서 좁힐 칸만 줄이면 소용이 없고 넓힐 칸을 함께
        # 키워야 비율이 바뀐다.
        column_config={
            SELECT_COLUMN: st.column_config.CheckboxColumn(SELECT_COLUMN, width=44),
            ORDER_COLUMN: st.column_config.NumberColumn(
                ORDER_COLUMN,
                min_value=1,
                max_value=len(rows),
                step=1,
                required=True,
                width=44,
                help="자리 번호를 넣으면 그 자리로 끼워 넣고 나머지는 한 칸씩 밀립니다.",
            ),
            NAME_COLUMN: st.column_config.TextColumn(
                f"{NAME_COLUMN} ✎", width=300, required=True, help="두 번 눌러 바로 고칩니다."
            ),
            "원천 코드": st.column_config.TextColumn("원천 코드", width=240),
            "최신 리비전": st.column_config.TextColumn("최신 리비전", width=70),
            "공식버전": st.column_config.TextColumn("공식버전", width=110),
            "최근 수정": st.column_config.DatetimeColumn(
                "최근 수정", format="YYYY-MM-DD HH:mm", width=140
            ),
        },
        disabled=["원천 코드", "최신 리비전", "공식버전", "최근 수정"],
    )


def _official_label(
    scenario_id: str,
    official_by_scenario: Mapping[str, OfficialReleaseSummary],
    latest_official_scenario: str | None,
) -> str:
    """그 시나리오의 최신 공식버전과 그 리비전(「v3 · r3」). 저장소 전체의 최신이면 「· 최신」."""
    release = official_by_scenario.get(scenario_id)
    if release is None:
        return ""
    label = f"v{release.release_no} · r{release.revision_no}"
    if scenario_id == latest_official_scenario:
        return f"{label} · 최신"
    return label


def _render_scenario_actions(
    repository: DuckDBScenarioRepository,
    database_path: str,
    summary: ScenarioSummary,
    releases: Sequence[OfficialReleaseSummary],
) -> bool:
    """고른 시나리오 카드. 공식 지정 확인 팝업을 그렸으면 `True`.

    자리 차례: 제목 줄(「보관…」) · 보관 칸 · 미저장 확인 칸 · 작업 줄 · 결과 칸 · 리비전 편집표 ·
    안내 칸. 생기고 사라지는 것은 모두 늘 서 있는 칸 안이라 리비전 편집표의 자리가 밀리지 않는다.
    """
    # 고른 시나리오가 바뀌면 열려 있던 작업 칸·확인 체크와 리비전 표의 고름·이름 편집을 버린다.
    # 다른 시나리오의 리비전을 고친 채 남으면 어느 쪽을 고치는 중인지 알 수 없다.
    first_view = st.session_state.get(ACTION_OWNER_KEY) != summary.scenario_id
    if first_view:
        st.session_state[ACTION_OWNER_KEY] = summary.scenario_id
        for key in (ACTION_KEY, DELETE_CONFIRM_KEY, ARCHIVE_CONFIRM_KEY, REVISION_SEED_KEY):
            st.session_state.pop(key, None)
        forget_table(REVISION_EDITOR_KEY)
    revisions = repository.list_revisions(summary.scenario_id)
    with st.container(border=True):
        title_column, archive_column = st.columns([6, 1], vertical_alignment="center")
        with title_column:
            st.markdown(f"#### :material/check_box: {literal_markdown(summary.scenario_name)}")
        with archive_column:
            st.button(
                "보관…",
                icon=":material/archive:",
                type="tertiary",
                key=f"{ACTION_KEY}_archive",
                on_click=_toggle_action,
                args=("archive",),
            )
        archive_slot = st.container()
        if not revisions:
            st.info("이 시나리오에 저장된 리비전이 없습니다.")
            with archive_slot:
                if st.session_state.get(ACTION_KEY) == "archive":
                    _render_archive(repository, summary)
            return False
        revision_by_id = {revision.revision_id: revision for revision in revisions}
        base_ids = list(revision_by_id)
        base_names = {revision.revision_id: revision.revision_name for revision in revisions}
        draft, widget_key = settle_table(
            REVISION_EDITOR_KEY, base_ids, base_names, REVISION_COLUMNS
        )
        draft, widget_key = _seed_revision_pick(
            summary, draft, widget_key, base_ids, base_names, first_view
        )
        picked = revision_by_id.get(draft.picked) if draft.picked is not None else None
        args = (tuple(base_ids), dict(base_names))
        # 불러오는 입구가 둘이다 — 이 카드와 사이드바 시나리오 팝업. 확인 절차와 글자를 맞춘다
        # (`components/scenario_status.py`): 미저장 변경이 있으면 버린다는 체크를 받는다.
        discard_changes = True
        with st.container():
            if has_unsaved_scenario_changes():
                st.warning("지금 올라와 있는 시나리오에 저장하지 않은 편집이 있습니다.")
                discard_changes = st.checkbox(
                    "변경을 버리고 불러오기",
                    key=DISCARD_UNSAVED_KEY,
                )
        renames = changed_names(draft, base_names)
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.button(
                "선택한 리비전 불러오기",
                icon=":material/download:",
                type="primary",
                disabled=picked is None or not discard_changes,
                key="scenario_card_load",
                on_click=_load_picked_revision,
                args=(database_path, *args),
            )
            st.button(
                "공식으로 지정…",
                icon=":material/verified:",
                disabled=picked is None,
                key=f"{ACTION_KEY}_official",
                on_click=_open_official_dialog,
                args=(summary.scenario_id, *args),
            )
            st.button(
                f"이름 저장 ({len(renames)})" if renames else "이름 저장",
                icon=":material/save:",
                disabled=not renames,
                key="scenario_card_save_names",
                on_click=_save_revision_names_clicked,
                args=(database_path, tuple(revisions)),
            )
            st.button(
                "편집 버리기",
                icon=":material/undo:",
                type="tertiary",
                disabled=not renames,
                key="scenario_card_discard",
                on_click=forget_table_edits,
                args=(REVISION_EDITOR_KEY,),
            )
        _render_notice(CARD_NOTICE_KEY)
        _render_revision_editor(repository, revisions, releases, draft, widget_key)
        with st.container():
            st.caption(
                "리비전명 칸을 바로 고칩니다 — 이름표라 표·계산·공식 이력은 바뀌지 않습니다. "
                "메모는 조회기간·출처 같은 시스템 기록이 있어 고치지 않습니다."
            )
            official_names = _official_rename_notes(renames, revision_by_id, releases)
            if official_names:
                st.caption(official_names)
            stale = moved_names(draft, base_names)
            if stale:
                st.warning(
                    moved_names_warning(
                        [
                            (
                                _row_place(
                                    f"r{revision_by_id[revision_id].revision_no}",
                                    draft.names[revision_id],
                                ),
                                current,
                            )
                            for revision_id, current in stale.items()
                        ]
                    ),
                    icon=":material/warning:",
                )
        with archive_slot:
            if st.session_state.get(ACTION_KEY) == "archive":
                _render_archive(repository, summary)
    opened = st.session_state.get(OFFICIAL_DIALOG_KEY)
    if (
        isinstance(opened, tuple)
        and len(opened) == 2
        and opened[0] == summary.scenario_id
        and opened[1] in revision_by_id
    ):
        _official_dialog(
            database_path, summary, revision_by_id[opened[1]], releases[0] if releases else None
        )
        return True
    return False


def _toggle_action(action: str) -> None:
    """카드 작업 칸 하나를 열고 닫는다(「보관…」)."""
    if st.session_state.get(ACTION_KEY) == action:
        st.session_state.pop(ACTION_KEY, None)
    else:
        st.session_state[ACTION_KEY] = action


def _seed_revision_pick(
    summary: ScenarioSummary,
    draft: TableDraft,
    widget_key: str,
    base_ids: Sequence[str],
    base_names: Mapping[str, str],
    first_view: bool,
) -> tuple[TableDraft, str]:
    """리비전 표의 고름 씨앗. 처음 볼 때와 올라와 있는 리비전이 바뀔 때만 코드가 고른다.

    지금 보고 있는 시나리오라면 **올라와 있는 리비전**이 미리 골라져 있어야 한다 — 화면과 다른 것이
    골라져 있으면 「같은 것을 다시 불러왔다」고 여기면서 실은 다른 리비전을 올리게 된다. 올라와 있는
    리비전이 씨앗(`REVISION_SEED_KEY`)과 달라지면 다시 고른다. 사용자가 일부러 고른 리비전은 올라와
    있는 리비전이 그대로인 동안 남는다. 다른 시나리오는 처음 볼 때 최신 리비전을 고른다.
    """
    active_revision_id = active_persisted_revision_id()
    active_here = (
        summary.scenario_id == active_persisted_scenario_id() and active_revision_id in base_ids
    )
    if active_here and st.session_state.get(REVISION_SEED_KEY) != active_revision_id:
        st.session_state[REVISION_SEED_KEY] = active_revision_id
        widget_key = repick_table(
            REVISION_EDITOR_KEY, draft, active_revision_id, base_ids, base_names
        )
        return replace(draft, picked=active_revision_id), widget_key
    if not active_here:
        # 올라와 있는 것이 다른 시나리오로 옮겨 가면 씨앗 기록을 버린다. 남겨 두면 마지막으로
        # 씨앗을 넣은 리비전으로 돌아왔을 때 「같은 씨앗」으로 읽혀 표가 따라오지 않았다
        # (2026-10-11 재검증).
        st.session_state.pop(REVISION_SEED_KEY, None)
        if first_view:
            widget_key = repick_table(REVISION_EDITOR_KEY, draft, base_ids[0], base_ids, base_names)
            return replace(draft, picked=base_ids[0]), widget_key
    return draft, widget_key


def _render_revision_editor(
    repository: DuckDBScenarioRepository,
    revisions: Sequence[RevisionSummary],
    releases: Sequence[OfficialReleaseSummary],
    draft: TableDraft,
    widget_key: str,
) -> None:
    """리비전 편집표 — 고름(하나) | r | 리비전명 ✎ | 메모 | 저장일 | 부모 | 상태.

    상태는 「공식 vN · 올라와 있음 · 가상 n」이다. 가상 제품 수는 리비전 id 목록으로 한 번에 센다
    (`count_virtual_products` — 회차마다 리비전 수만큼 읽지 않는다).
    """
    by_id = {revision.revision_id: revision for revision in revisions}
    rows = table_rows(draft, list(by_id))
    number_by_id = {revision.revision_id: revision.revision_no for revision in revisions}
    release_by_revision: dict[str, int] = {}
    for release in releases:
        release_by_revision.setdefault(release.revision_id, release.release_no)
    virtual_counts = repository.count_virtual_products(rows)
    active_revision_id = active_persisted_revision_id()
    table = pd.DataFrame(
        {
            REVISION_PICK_COLUMN: [row_id == draft.picked for row_id in rows],
            "r": [f"r{by_id[row_id].revision_no}" for row_id in rows],
            REVISION_NAME_COLUMN: [
                draft.names.get(row_id, by_id[row_id].revision_name) for row_id in rows
            ],
            "메모": [(by_id[row_id].note or "").replace("\n", " ") for row_id in rows],
            "저장일": [by_id[row_id].created_at for row_id in rows],
            "부모": [
                _parent_label(by_id[row_id].parent_revision_id, number_by_id) for row_id in rows
            ],
            "상태": [
                revision_status_label(
                    release_by_revision.get(row_id),
                    loaded=row_id == active_revision_id,
                    virtual_count=virtual_counts.get(row_id, 0),
                )
                for row_id in rows
            ],
        },
        index=pd.Index(rows, name="revision_id"),
    )
    st.data_editor(
        table,
        key=widget_key,
        placeholder="",
        num_rows="fixed",
        hide_index=True,
        width="stretch",
        column_config={
            REVISION_PICK_COLUMN: st.column_config.CheckboxColumn(REVISION_PICK_COLUMN, width=44),
            "r": st.column_config.TextColumn("r", width=44),
            REVISION_NAME_COLUMN: st.column_config.TextColumn(
                f"{REVISION_NAME_COLUMN} ✎",
                width=220,
                required=True,
                help="두 번 눌러 바로 고칩니다. 「이름 저장」을 눌러야 저장됩니다.",
            ),
            "메모": st.column_config.TextColumn("메모", width=260),
            "저장일": st.column_config.DatetimeColumn("저장일", format="YY.MM.DD HH:mm", width=110),
            "부모": st.column_config.TextColumn("부모", width=50),
            "상태": st.column_config.TextColumn("상태", width=180),
        },
        disabled=["r", "메모", "저장일", "부모", "상태"],
    )


def _parent_label(parent_revision_id: str | None, number_by_id: Mapping[str, int]) -> str:
    if parent_revision_id is None or parent_revision_id not in number_by_id:
        return ""
    return f"r{number_by_id[parent_revision_id]}"


def revision_status_label(release_no: int | None, *, loaded: bool, virtual_count: int) -> str:
    """리비전 표 「상태」 칸 — 「공식 v3 · 올라와 있음 · 가상 2」(해당하는 것만)."""
    parts = []
    if release_no is not None:
        parts.append(f"공식 v{release_no}")
    if loaded:
        parts.append("올라와 있음")
    if virtual_count:
        parts.append(f"가상 {virtual_count}")
    return " · ".join(parts)


def _official_rename_notes(
    renames: Mapping[str, tuple[str, str]],
    revision_by_id: Mapping[str, RevisionSummary],
    releases: Sequence[OfficialReleaseSummary],
) -> str:
    """이름을 고치는 중인 리비전 가운데 공식으로 지정된 것마다 공식버전명은 그대로라는 한 줄."""
    release_by_revision: dict[str, int] = {}
    for release in releases:
        release_by_revision.setdefault(release.revision_id, release.release_no)
    return "  \n".join(
        f"r{revision_by_id[revision_id].revision_no}: 공식 v{release_by_revision[revision_id]} "
        "으로 지정된 리비전입니다 — 공식버전명은 바뀌지 않습니다."
        for revision_id in renames
        if revision_id in release_by_revision and revision_id in revision_by_id
    )


def _picked_revision(base_ids: Sequence[str], base_names: Mapping[str, str]) -> str | None:
    """누른 회차의 리비전 표 고름(초안 + 브라우저가 보낸 편집)."""
    return peek_table(REVISION_EDITOR_KEY, base_ids, base_names, REVISION_COLUMNS).picked


def _load_picked_revision(
    database_path: str, base_ids: Sequence[str], base_names: Mapping[str, str]
) -> None:
    """「선택한 리비전 불러오기」 콜백. 고른 리비전은 누른 회차의 표에서 다시 읽는다."""
    revision_id = _picked_revision(base_ids, base_names)
    if revision_id is None:
        st.session_state[CARD_NOTICE_KEY] = ("error", "불러올 리비전을 표에서 고르세요.")
        return
    # 단추 잠금은 화면의 약속일 뿐이다. 누른 회차에도 미저장 편집을 버린다는 체크를 다시 본다.
    if has_unsaved_scenario_changes() and not st.session_state.get(DISCARD_UNSAVED_KEY):
        st.session_state[CARD_NOTICE_KEY] = (
            "error",
            "저장하지 않은 편집이 있습니다 — 「변경을 버리고 불러오기」를 체크해야 불러옵니다.",
        )
        return
    try:
        with pinned_connections(Path(database_path)):
            snapshot = load_scenario_snapshot(database_path, revision_id)
            # 활성화 **전에** 본다. 활성화한 뒤에 계산이 죽으면 올라와 있는 시나리오가 이미 바뀐
            # 뒤라 화면에서 되돌릴 방법이 없다.
            blocked = revision_block_reason(snapshot.tables)
            if blocked is not None:
                st.session_state[CARD_NOTICE_KEY] = ("error", blocked)
                return
            activate_persisted_snapshot(snapshot)
    except BOOTSTRAP_ERRORS as exc:
        st.session_state[CARD_NOTICE_KEY] = ("error", bootstrap_error_message(exc))
        return
    st.session_state[FLASH_KEY] = (
        f"{literal_markdown(snapshot.scenario.scenario_name)} r{snapshot.revision.revision_no}"
        f"{object_particle(str(snapshot.revision.revision_no))} 불러왔습니다."
    )


def _save_revision_names_clicked(database_path: str, revisions: Sequence[RevisionSummary]) -> None:
    """「이름 저장 (n)」 콜백. 리비전 표에서 고친 이름을 한 번에 쓴다.

    이름마다 그 칸을 처음 고칠 때 표가 보인 이름(초안의 `name_base`)과 대조한다. 하나라도 거부되면
    아무것도 쓰지 않고 리비전마다 까닭을 적는다. 다른 사용자가 먼저 바꿔 거부된 리비전은 그 이름
    편집만 버려 표에 지금 이름을 다시 보인다.
    """
    by_id = {revision.revision_id: revision for revision in revisions}
    base_names = {revision.revision_id: revision.revision_name for revision in revisions}
    draft = peek_table(REVISION_EDITOR_KEY, list(by_id), base_names, REVISION_COLUMNS)
    renames = changed_names(draft, base_names)
    if not renames:
        st.session_state[CARD_NOTICE_KEY] = ("info", "고친 리비전명이 없습니다.")
        return
    try:
        saved = save_revision_names(database_path, renames)
    except BatchEditRefused as exc:
        st.session_state[CARD_NOTICE_KEY] = (
            "error",
            refused_edits_message(
                [
                    (
                        _row_place(
                            f"r{by_id[revision_id].revision_no}",
                            draft.names.get(revision_id) or base_names[revision_id],
                        )
                        if revision_id in by_id
                        else None,
                        message,
                    )
                    for revision_id, message in exc.problems
                ],
                reloaded=bool(exc.moved_names),
            ),
        )
        if exc.moved_names:
            remount_table(REVISION_EDITOR_KEY, drop_names(draft, exc.moved_names))
        else:
            store_draft(REVISION_EDITOR_KEY, draft)
        return
    except BOOTSTRAP_ERRORS as exc:
        st.session_state[CARD_NOTICE_KEY] = ("error", bootstrap_error_message(exc))
        store_draft(REVISION_EDITOR_KEY, draft)
        return
    forget_table_edits(REVISION_EDITOR_KEY)
    st.session_state[CARD_NOTICE_KEY] = (
        "success",
        "리비전명을 저장했습니다: "
        + ", ".join(literal_markdown(revision_label(revision)) for revision in saved),
    )


def save_revision_name(
    database_path: str, revision: RevisionSummary, revision_name: str
) -> RevisionSummary | None:
    """리비전 하나의 이름표만 바꾸고 이 세션의 후속 처리를 한다. 바뀐 것이 없으면 쓰지 않고 `None`.

    `revision` 은 화면이 그 회차에 읽어 보인 요약이다. 그 이름을 `expected_name` 으로 넘겨 비교 후
    쓰기를 한다 — 그 사이 다른 사용자가 먼저 바꿨으면 저장소가 `RevisionNameMoved` 로 거절한다.
    빈 이름·보관된 시나리오·파일 잠금도 저장소 예외(`BOOTSTRAP_ERRORS` 안)로 그대로 올리고, 부르는
    쪽이 누른 자리에서 알린다. 콜백에서도 부를 수 있게 DB 핀을 스스로 잡는다(겹쳐도 된다).
    후속 처리는 `save_revision_names` 와 같다.
    """
    if revision_name.strip() == revision.revision_name:
        return None
    with pinned_connections(Path(database_path)):
        renamed = get_scenario_repository(database_path).rename_revision(
            revision.revision_id, revision_name, expected_name=revision.revision_name
        )
    _after_revision_rename([renamed])
    return renamed


def save_revision_names(
    database_path: str, renames: Mapping[str, tuple[str, str]]
) -> list[RevisionSummary]:
    """리비전 여러 개의 이름표를 한 트랜잭션으로 바꾸고 이 세션의 후속 처리를 한다.

    `renames` 는 리비전 id → (보고 고친 이름, 새 이름)이다(`changed_names`). 보고 고친 이름은 그
    칸을 처음 고칠 때 표가 보인 이름이다 — 마지막 회차에 다시 읽은 이름을 넘기면 남이 먼저 바꾼 뒤
    회차가 한 번만 돌아도 대조가 통과해 남의 변경을 덮는다. 하나라도 거부되면 저장소가
    `BatchEditRefused` 로 아무것도 쓰지 않는다. 고친 것이 없으면 쓰지 않는다.

    후속 처리는 셋이다. 스냅샷 payload 가 리비전 요약을 통째로 담으므로 프로세스 캐시를 비우고
    (`clear_scenario_snapshot_cache`), 파생 화면이 메모한 원본(요약 포함)을 버리고
    (`forget_derived_sources`), 그 리비전이 이 세션에 올라와 있으면 머리 띠·팝업 머리 줄의 이름표를
    바꾼다(`rename_active_revision_label` — 활성화는 다시 하지 않는다). 공식 이력·비교 프로필·입장
    화면 Summary 는 리비전명을 싣지 않아 건드리지 않는다. 시나리오 「최근 수정」도 오르지 않아 목록
    차례와 행 선택이 그대로다.
    """
    if not renames:
        return []
    with pinned_connections(Path(database_path)):
        renamed = get_scenario_repository(database_path).rename_revisions(renames)
    _after_revision_rename(renamed)
    return renamed


def _after_revision_rename(renamed: Sequence[RevisionSummary]) -> None:
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    for revision in renamed:
        rename_active_revision_label(revision.revision_id, revision.revision_name)


def _open_official_dialog(
    scenario_id: str, base_ids: Sequence[str], base_names: Mapping[str, str]
) -> None:
    """「공식으로 지정…」 콜백. 다른 팝업 칸을 비우고(한 실행에 하나) 누른 회차의 고름으로 연다."""
    revision_id = _picked_revision(base_ids, base_names)
    if revision_id is None:
        return
    forget_page_dialogs()
    st.session_state[OFFICIAL_DIALOG_KEY] = (scenario_id, revision_id)


def _close_official_dialog() -> None:
    st.session_state.pop(OFFICIAL_DIALOG_KEY, None)


@st.dialog("공식버전 지정", width="medium", on_dismiss=_close_official_dialog)
def _official_dialog(
    database_path: str,
    summary: ScenarioSummary,
    revision: RevisionSummary,
    latest: OfficialReleaseSummary | None,
) -> None:
    """공식버전 지정 확인 팝업. 팝업 안 조작은 실행 핀 밖의 프래그먼트라 DB 핀을 스스로 잡는다."""
    with pinned_connections(Path(database_path)):
        _render_official(
            get_scenario_repository(database_path), database_path, summary, revision, latest
        )


def _render_official(
    repository: DuckDBScenarioRepository,
    database_path: str,
    summary: ScenarioSummary,
    revision: RevisionSummary,
    latest: OfficialReleaseSummary | None,
) -> None:
    """팝업 본문 — 「지금 공식 → 새 공식」을 나란히 보이고, 확인을 받아 지정한다.

    모두의 첫 화면이 바뀌는 작업이라 대상을 사람 눈으로도 확인하게 적는다. 팝업이 보인 「지금
    공식」 번호를 저장소에 넘겨(`expected_latest_release_no`) 그 사이 다른 사람이 먼저 지정했으면
    쓰지 않는다.
    """
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
    if latest is not None and latest.revision_id == revision_id:
        st.info("지금 공식과 같은 리비전입니다 — 지정하면 같은 리비전에 새 공식 번호가 섭니다.")
    # 가상 제품은 실적과 대조할 수 없는 값이다. 그런 리비전이 모두의 첫 화면이 되기 전에
    # 지정하는 사람이 그 사실을 보고 확인하게 한다(2026-10-06 사용자 결정). 확인 체크는 폼
    # **밖**에 둔다 — 폼 안의 체크는 누를 때 다시 그리지 않아 지정 버튼을 풀 수 없다.
    virtual_products = virtual_product_records(repository.list_virtual_products(revision_id))
    confirmed = True
    if virtual_products:
        st.warning(official_virtual_product_warning(virtual_products), icon=":material/warning:")
        confirmed = st.checkbox(
            "가상 제품이 포함된 것을 확인했습니다",
            key=official_confirm_key(revision_id),
        )
    with st.form("scenario_official_form"):
        release_name = st.text_input("공식버전명", value=f"{summary.scenario_name} 공식안")
        release_note = st.text_area("공식 지정 메모", height=80)
        official_submitted = st.form_submit_button(
            "선택 리비전을 공식버전으로 지정",
            icon=":material/publish:",
            type="primary",
            disabled=not confirmed,
            width="stretch",
        )
    if official_submitted and not confirmed:
        # 버튼 잠금은 화면의 약속일 뿐이다. 제출 회차에도 확인을 다시 본다.
        st.error("가상 제품이 포함된 것을 확인해야 공식버전으로 지정할 수 있습니다.")
        return
    if not official_submitted:
        return
    try:
        # 공식버전은 모두의 첫 화면이다. 계산이 안 되는 리비전을 지정하면 모두의 HOME 이
        # 멈춘다. 검사는 HOME 과 같은 캐시 칸을 써서, 통과하면 HOME 이 이미 데워져 있다.
        with st.spinner("공식버전으로 지정할 수 있는지 Capa 계산을 확인하는 중입니다..."):
            verdict = official_publish_verdict(database_path, revision_id)
        if not verdict.allowed:
            st.error(verdict.message)
            return
        release = repository.publish_official_revision(
            summary.scenario_id,
            revision_id,
            release_name=release_name,
            note=release_note,
            expected_latest_release_no=latest.release_no if latest is not None else 0,
        )
    except OfficialReleaseMoved as exc:
        # 저장소 문구는 배경 회차(자동 갱신) 말투라 팝업에서는 무엇을 하면 되는지로 바꿔 적는다.
        st.error(official_moved_message(exc.current))
        return
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    st.session_state[FLASH_KEY] = (
        f"공식 v{release.release_no} · {literal_markdown(release.release_name)}"
        f"{object_particle(release.release_name)} 지정했습니다."
    )
    # 허락하면서 하는 경고(소요대수에 들지 않은 수요 건수)는 지정한 사람이 그 자리에서 본다.
    if verdict.message:
        st.session_state[FLASH_WARNING_KEY] = verdict.message
    _close_official_dialog()
    st.session_state.pop(official_confirm_key(revision_id), None)
    # 입장 화면 Summary 가 새 공식버전을 다음 회차에 곧바로 싣게 한다
    # (평소에는 30초에 한 번 본다).
    forget_intro_summary_check()
    # 판정 기준을 아직 저장하지 않았으면 기본값이 최신 공식버전 프리셋에서 온다.
    clear_global_securement_threshold_cache()
    st.rerun()


def official_moved_message(current_release_no: int) -> str:
    """팝업을 연 사이 다른 사람이 먼저 공식버전을 지정해 지정하지 않았을 때의 알림."""
    return (
        f"팝업을 연 사이 다른 사람이 공식 v{current_release_no}"
        f"{object_particle(str(current_release_no))} 먼저 지정해 지정하지 않았습니다 — 팝업을 "
        "닫고 다시 열어 「지금 공식」을 확인하세요."
    )


def _render_official_history(releases: Sequence[OfficialReleaseSummary]) -> None:
    """카드 아래 늘 있는 접힘 칸 — 공식 발행 이력(r 번호·공식버전명만, 리비전명은 싣지 않는다).

    리비전명은 고칠 수 있어, 실으면 이름을 바꾸는 순간 과거 발행 행이 발행 당시와 다른 이름을
    보인다.
    """
    with st.expander(
        f"공식 발행 이력 {len(releases)}건",
        icon=":material/history:",
        key=HISTORY_EXPANDER_KEY,
    ):
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
                        "공식버전명": release.release_name,
                        "지정시각": release.published_at,
                    }
                    for release in releases[:HISTORY_LIMIT]
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        if len(releases) > HISTORY_LIMIT:
            st.caption(f"최근 {HISTORY_LIMIT}건만 보입니다.")


def official_confirm_key(revision_id: str) -> str:
    """가상 제품 확인 체크의 key. 리비전을 바꾸면 다른 칸이라 앞 리비전의 확인이 따라오지 않는다."""
    return f"{OFFICIAL_CONFIRM_KEY}_{revision_id}"


def official_virtual_product_warning(records: Sequence[VirtualProductRecord]) -> str:
    """공식버전 지정 전에 보일 가상 제품 확인 문장. 제품 · Stack 을 모두 적는다."""
    products = ", ".join(f"{record.product} · {record.stack}" for record in records)
    return (
        f"이 리비전에는 가상 제품 {len(records)}건이 포함되어 있습니다({products}). "
        "실적과 대조할 수 없는 값입니다. 그대로 공식버전으로 지정할까요?"
    )


def _render_archive(repository: DuckDBScenarioRepository, summary: ScenarioSummary) -> None:
    # 최신 공식버전의 시나리오는 저장소가 보관을 거절한다(`_require_not_latest_official`). 체크하고
    # 눌러 본 뒤에야 알게 하지 않고 그린 회차의 최신 공식으로 미리 말한다. 저장소 검사는 그대로
    # 마지막 방어선이다(그 사이 다른 사용자가 공식을 바꾼 경우).
    official = repository.latest_official_release()
    if official is not None and official.scenario_id == summary.scenario_id:
        st.info(
            f"지금 최신 공식버전(v{official.release_no})의 시나리오라 보관할 수 없습니다 — "
            "다른 리비전을 먼저 공식으로 지정하세요.",
            icon=":material/block:",
        )
        return
    st.info(
        "보관하면 목록에서 숨겨지고 새 리비전 저장·공식버전 지정이 막힙니다. 데이터는 "
        "그대로 남아 아래 「보관된 시나리오」에서 되돌릴 수 있습니다."
    )
    # 보관이 파일 크기를 줄이지 않는다는 것(용량 목적이면 영구 삭제 + compact)은 Guide 가 말한다.
    confirmed = st.checkbox(
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "보관합니다",
        key=ARCHIVE_CONFIRM_KEY,
    )
    if not st.button(
        "보관 실행",
        icon=":material/archive:",
        type="primary",
        disabled=not confirmed,
        width="stretch",
    ):
        return
    try:
        repository.archive_scenario(summary.scenario_id)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    # 저장소가 이 시나리오를 가리키던 공용 비교 대상을 비웠다. 캐시는 경로 키라 따로 비운다.
    clear_global_comparison_scenario_cache()
    # 입장 화면 Summary 의 GAP 도 그 비교 대상을 쓴다 — 이 세션은 곧바로 다시 확인한다.
    forget_intro_summary_check()
    # 보관한 시나리오의 공식버전이 판정 기준의 미저장 기본값을 정했을 수 있다.
    clear_global_securement_threshold_cache()
    if summary.scenario_id == active_persisted_scenario_id():
        clear_persisted_scenario_activation()
    st.session_state[FLASH_KEY] = (
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "보관했습니다."
    )
    discard_editor(LIST_EDITOR_KEY)
    for key in (ACTION_KEY, ACTION_OWNER_KEY, ARCHIVE_CONFIRM_KEY):
        st.session_state.pop(key, None)
    st.rerun()


def _render_archived_scenarios(repository: DuckDBScenarioRepository) -> None:
    """보관함. 되돌리기와 영구 삭제가 여기 모인다. 보관본이 없어도 칸은 늘 선다(C안 — 자리 고정)."""
    archived = [
        scenario
        for scenario in repository.list_scenarios(include_archived=True)
        if scenario.status != "ACTIVE"
    ]
    # **key 는 펼침을 지키려고 준다**(2026-10-01). 위의 일회성 알림(보관·되돌리기 완료)이
    # 사라지는 회차에 이 칸의 자리가 밀려 새로 마운트되고, key 가 없으면 접혀 이름을 적던
    # 영구 삭제 버튼이 가려졌다(브라우저 실측). `on_change` 없는 key 라 위젯이 아니고, id 가
    # 제목을 보지 않아 건수가 바뀌어도 같은 칸이다.
    with st.expander(
        f"보관된 시나리오 {len(archived)}건",
        icon=":material/inventory_2:",
        key=ARCHIVED_EXPANDER_KEY,
    ):
        if not archived:
            st.caption("보관된 시나리오가 없습니다. 고른 시나리오 카드의 「보관…」으로 보관합니다.")
            return
        by_id = {scenario.scenario_id: scenario for scenario in archived}
        # 되돌리거나 지운 보관본은 선택지에서 빠진다. 그 선택을 지우기만 하면 서버는 첫 보관본을
        # 쓰는데 브라우저는 처리한 이름을 계속 보여, 다음 「되돌리기」 가 보이지 않는 시나리오에
        # 걸린다. 매 회차 지금 선택지로 다시 적어 브라우저도 새 글자를 받게 한다.
        prune_choice(ARCHIVED_SELECT_KEY, list(by_id), default=next(iter(by_id)))
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
                _restore_scenario(repository, summary)
        _render_delete(repository, summary)


def _restore_scenario(
    repository: DuckDBScenarioRepository,
    summary: ScenarioSummary,
) -> None:
    try:
        repository.restore_scenario(summary.scenario_id)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    st.session_state[FLASH_KEY] = (
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "목록으로 되돌렸습니다."
    )
    discard_editor(LIST_EDITOR_KEY)
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
    typed = st.text_input(
        f"확인: 「{literal_markdown(summary.scenario_name)}」"
        f"{object_particle(summary.scenario_name)} 그대로 입력하세요",
        key=DELETE_CONFIRM_KEY,
        placeholder="",
    )
    if not st.button(
        "영구 삭제 실행",
        icon=":material/delete_forever:",
        type="primary",
        disabled=typed.strip() != summary.scenario_name,
        width="stretch",
    ):
        return
    try:
        repository.delete_scenario(summary.scenario_id)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
        return
    clear_scenario_snapshot_cache()
    forget_derived_sources()
    clear_global_comparison_scenario_cache()
    # 입장 화면 Summary 의 GAP 도 그 비교 대상을 쓴다 — 이 세션은 곧바로 다시 확인한다.
    forget_intro_summary_check()
    # 지운 시나리오의 공식버전이 판정 기준의 미저장 기본값을 정했을 수 있다.
    clear_global_securement_threshold_cache()
    if summary.scenario_id == active_persisted_scenario_id():
        clear_persisted_scenario_activation()
    st.session_state[FLASH_KEY] = (
        f"{literal_markdown(summary.scenario_name)}{object_particle(summary.scenario_name)} "
        "영구 삭제했습니다."
    )
    discard_editor(LIST_EDITOR_KEY)
    for key in (ACTION_KEY, ACTION_OWNER_KEY):
        st.session_state.pop(key, None)
    st.session_state[DELETE_CLEAR_KEY] = True
    st.rerun()


def delete_scope_warning(revision_count: int, release_count: int) -> str:
    """영구 삭제 입력 칸 위 한 줄. 함께 지워질 리비전·공식 발행 이력의 수와 되돌릴 수 없다는 것."""
    if release_count:
        scope = f"리비전 {revision_count}개와 공식 발행 이력 {release_count}건이"
    else:
        scope = f"리비전 {revision_count}개가"
    return f"영구 삭제하면 {scope} 함께 지워지고 되돌릴 수 없습니다."


def clone_field_key(field: str) -> str:
    """복제 폼 한 칸의 위젯 키. 저장에 성공할 때마다 세대가 바뀐다.

    **저장한 값이 폼에 남으면 한 번 더 눌러 같은 시나리오가 또 생긴다**(2026-10-01 브라우저
    재현). `clear_on_submit` 은 이름 중복 같은 **실패**에도 입력을 지워 쓰지 않는다. 세션 칸만
    지우면 브라우저가 옛 값을 다시 보내므로(`components/editor_state.py` 와 같은 사정) 성공한
    회차에만 키를 바꿔 새 빈 칸으로 세운다.
    """
    generation = int(st.session_state.get(CLONE_FORM_GENERATION_KEY, 0))
    return f"scenario_create_{field}_g{generation}"


def _render_clone(repository: DuckDBScenarioRepository) -> None:
    try:
        reference_tables, active_scenario = _current_reference_context()
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            f"신규 시나리오의 기준 표시순서를 준비하지 못했습니다: {bootstrap_error_message(exc)}"
        )
        return
    # 무엇을 복제하는지 폼 위에 적는다. 원천 코드·이름 칸의 기본값은 비워 둔다 — 원천 시뮬레이션명은
    # 공식버전 자동 갱신이 주차(W##)를 읽는 두 번째 근거라, 복제본이 원본의 이름을 물려받으면 그
    # 복제를 공식으로 지정했을 때 기준 주차가 달라진다.
    st.caption(clone_target_caption())
    with st.form("scenario_create_form"):
        # 이름은 보관본을 포함해 겹칠 수 없다 — 검사는 저장소가 한다(`create_scenario`).
        scenario_name = st.text_input("시나리오명", key=clone_field_key("name"))
        source_code = st.text_input("원천 시뮬레이션 코드", key=clone_field_key("source_code"))
        source_name = st.text_input("원천 시뮬레이션명", key=clone_field_key("source_name"))
        revision_name = st.text_input(
            "초기 리비전명", value="초기 리비전", key=clone_field_key("revision_name")
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
                get_effective_reference_version(), active_scenario, reference_tables
            )
            if not verdict.allowed:
                st.error(verdict.message)
                return
            revision_source = revision_tables_for_save(active_scenario, reference_tables)
            preset = _compatible_preset(capture_scenario_preset(revision_source), revision_source)
            virtual_products = revision_virtual_product_rows(
                repository, active_persisted_revision_id(), revision_source
            )
            snapshot = repository.create_scenario(
                ScenarioCreate(
                    scenario_name=scenario_name,
                    source_simulation_code=source_code,
                    source_simulation_name=source_name,
                    source_type="DUCKDB_SCENARIO_CLONE",
                    pipeline_version=CLONE_PIPELINE_VERSION,
                    source_registered_at=None,
                ),
                reference_tables,
                preset,
                source_data=None,
                revision_tables=revision_source,
                revision_name=revision_name,
                note=note.strip() or None,
                virtual_products=virtual_products,
            )
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc))
    else:
        # 내용은 지금 편집본 그대로지만 **다른 시나리오**가 된다 — 시나리오를 바꾸는 경로처럼
        # HOME 토글을 푼다.
        activate_persisted_snapshot(snapshot)
        st.session_state[FLASH_KEY] = (
            f"{literal_markdown(snapshot.scenario.scenario_name)}"
            f"{object_particle(snapshot.scenario.scenario_name)} 저장했습니다."
            + virtual_product_save_notice(len(virtual_products))
        )
        if verdict.message:
            st.session_state[FLASH_WARNING_KEY] = verdict.message
        st.session_state[CLONE_FORM_GENERATION_KEY] = (
            int(st.session_state.get(CLONE_FORM_GENERATION_KEY, 0)) + 1
        )
        st.rerun()


def clone_target_caption() -> str:
    """복제 폼 위 한 줄 — 지금 올라와 있는 리비전과 저장하지 않은 편집이 함께 들어가는지."""
    edits = (
        "저장하지 않은 편집도 함께 들어갑니다"
        if has_unsaved_scenario_changes()
        else "저장하지 않은 편집은 없습니다"
    )
    label = active_scenario_label()
    if label is None:
        return f"지금 올라와 있는 편집본을 새 시나리오로 복제합니다 — {edits}."
    return (
        f"지금 올라와 있는 「{literal_markdown(label.scenario_name)}」 r{label.revision_no}"
        f"{object_particle(str(label.revision_no))} 새 시나리오로 복제합니다 — {edits}."
    )


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
    저장, 이 페이지의 지금 편집본 복제)가 모두 이것을 넘겨야 가상 제품 출처가 DB 에 이어진다.
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
        "실적과 대조할 수 없으므로 공식버전으로 발행하기 전에 확인하세요."
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
