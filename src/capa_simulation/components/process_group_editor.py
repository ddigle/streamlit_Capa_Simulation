# Purpose: 공용 공정 그룹 대응을 보이고 고쳐 버전 대조로 저장하는 편집 카드를 그린다.

"""공정 그룹 편집 카드 — HOME 공정 필터 팝업의 그룹 단추가 쓰는 「공정 → 공정 그룹」 공용 프로필.

공정 목록을 인자로 받는 부품이고 두 자리에 붙는다(설계 규칙 UI-CON-04).

- HOME 설정 `Capa 요약 · 표시` 탭 — 조회기간 공정(확보율 선택지)을 넘기는 테 두른 카드다.
- Admin Area 「공정 그룹」 탭(`AdminTab`) — 활성 시나리오의 모든 공정(`RQ_MODULE`)을 넘겨 조회기간에
  확보율이 없는 공정에도 그룹을 준다. 탭 이름을 거듭하지 않게 제목이 Admin 의 다른 편집 탭과 같은
  「직접 편집」 이고 테가 없다(UI-TXT-07 · UI-CON-03). 빈 선택지 글 · 목록 밖 표지와 그 풍선 · 읽기
  실패 마크(`AD-07` — 열린 탭에서만)도 Admin 낱말이다.

줄은 받은 목록 차례(한 열쇠는 한 줄 — `services.process_group.process_group_editor_frame`)이고,
그 목록에 없는 저장 공정은 뒤에 표지를 달고 선다. HOME 은 「· 이 화면에 없음」(조회기간 선택지 밖),
Admin 은 옆 탭 Proc Rename 과 같은 낱말 「· 보유 공정 밖」(활성 시나리오 `RQ_MODULE` 밖)이다 — 두
목록이 다른 개념이라 이름도 둘이다(UI-CON-02). 통째 교체 저장이 화면에 안 보이는 남의 값을 지우지
않게 저장된 줄을 모두 보인다 — 지우려면 그 줄의 그룹 칸을 비운다.

저장은 확보율 보정 편집기(`home_preference._render_execution_editor`)와 같은 길이다.

- **버전 대조** — 편집을 시작한 회차에 본 version 을 `write_guard.remember_seen` 으로 두고 제출
  회차에 넘긴다. 그 사이 남이 저장했으면 저장소가 거부한다(`ProfileVersionConflict`). 본 값이 없으면
  지금 값으로 대체하지 않고 막는다.
- **빠른 두 번 누름 · 남의 저장 뒤 둘째 누름** — 제 저장 판정(`is_own_save`) · 충돌 표지
  (`note_profile_conflict` · `held_profile_conflict`) · 느린 둘째 누름의 성공 다시 알림
  (`note_notice` · `held_notice`).
- **바뀐 것 없는 저장은 새 버전을 만들지 않는다** — 최신 저장본을 보고 누른 표가 저장할 꼴로 그
  저장본과 같으면 쓰지 않는다. 한 번도 저장하지 않은 프로필(v0)의 첫 저장은 쓴다.

편집 표 key 끝에 저장본 version 과 줄 지문을 붙인다(`process_group_editor_key`) — 편집은 줄 위치로
남으므로, 줄 목록이나 저장본이 바뀐 회차에 옛 편집이 다른 공정 줄에 붙지 않고 표가 저장본으로 다시
선다. 프로필은 인자로 받지 않고 회차마다 다시 읽는다 — 팝업을 여는 회차의 인자는 직전 앱 전체 회차의
것이다(`dialog_host`).

`home_preference` 를 들이지 않는다(그쪽이 이 부품을 부른다). 값만 보기 여부와 저장 단추 풍선은
부르는 쪽이 넘긴다. 세션 key · 저장 이름은 두 자리가 같다 — 한 공용 프로필의 이 세션 저장 표지
(제 저장 · 충돌 · 거부)는 하나이고, 두 자리는 한 회차에 같이 그려지지 않는다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

import streamlit as st
from streamlit.elements.lib.column_types import ColumnConfig

from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.profile_caption import render_profile_heading
from capa_simulation.components.saved_note import (
    mark_note_saved,
    mark_note_saved_again,
    note_placeholder,
    ready_note_field,
)
from capa_simulation.components.table_toolbar import toolbar_room_css
from capa_simulation.components.write_guard import (
    SEEN_MISSING_MESSAGE,
    held_notice,
    held_profile_conflict,
    is_own_save,
    note_notice,
    note_profile_conflict,
    notice_marks,
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
from capa_simulation.persistence.cache import (
    clear_global_process_group_cache,
    get_scenario_repository,
    load_global_process_group,
)
from capa_simulation.persistence.models import GlobalProcessGroup
from capa_simulation.services.process_group import (
    PROCESS_GROUP_COLUMNS,
    PROCESS_GROUP_LABEL,
    PROCESS_GROUPS,
    ProcessGroupDuplicateError,
    assignments_from_editor,
    process_group_duplicate_message,
    process_group_editor_frame,
    same_process_groups,
)

PROCESS_GROUP_FORM_KEY = "home_process_group_form"
# 편집 표 key 머리 — 끝에 저장본 version 과 줄 지문이 붙는다(`process_group_editor_key`).
PROCESS_GROUP_EDITOR_KEY_PREFIX = "home_process_group_editor_"
PROCESS_GROUP_NOTE_KEY = "home_process_group_note"
# 편집을 시작한 회차가 본 공용 version. 저장 회차에 저장소가 대조한다.
PROCESS_GROUP_BASE_VERSION_KEY = "home_process_group_base_version"
# 저장 줄(저장 · 메모) — 오른쪽 끝을 표 도구 막대 자리로 비운다(서식은 제목 줄 캡션에 싣는다).
PROCESS_GROUP_SAVE_ROW_KEY = "home_process_group_save_row"
PROCESS_GROUP_FLASH_KEY = "home_process_group_flash"
# 이 세션이 한 저장의 표지 이름(`write_guard` 제 저장 짝 · 충돌 표지 · 거부 칸).
PROCESS_GROUP_SAVE_NAME = "home_process_group"
PROCESS_GROUP_SAVE_LABEL = "공정 그룹 저장"
PROCESS_GROUP_SAVED_MESSAGE = "공정 그룹을 저장했습니다."
PROCESS_GROUP_UNCHANGED_MESSAGE = (
    "바뀐 것이 없습니다 — 지금 공정 그룹 그대로라 새 버전을 만들지 않았습니다."
)
PROCESS_GROUP_TITLE = f"#### :material/category: {PROCESS_GROUP_LABEL}"
PROCESS_GROUP_EMPTY = "아직 나눈 공정 그룹이 없습니다"
NO_PROCESS_CAPTION = "조회기간에 계산된 공정이 없어 입력할 칸이 없습니다."
ABSENT_MARK = " · 이 화면에 없음"
# 「공정」 칸 풍선 — 「· 이 화면에 없음」 줄이 있을 때만 단다(칸 머리 표지 + 풍선).
ABSENT_PROCESS_GROUP_HELP = (
    "「이 화면에 없음」 공정은 이번 공정 목록에 없어 그룹 단추에 들지 않습니다. 공용 설정이라 "
    "저장해도 그대로 남고 그 공정이 있는 화면에서는 단추에 듭니다. 빼려면 공정 그룹 칸을 비웁니다."
)
DEFAULT_SOURCE = "웹 직접 편집"
# Admin Area 「공정 그룹」 탭 자리 — 탭 이름을 거듭하지 않는 제목(Admin 의 다른 편집 탭과 같은
# 낱말), 보유 공정이 없을 때의 글, 목록 밖 표지와 「공정」 칸 풍선(Proc Rename 의 「보유 공정
# 밖」 과 같은 낱말), 저장 단추 풍선(HOME 의 공용 설정 풍선은 팝업을 말한다).
ADMIN_TITLE = "#### 직접 편집"
ADMIN_NO_PROCESS_CAPTION = "활성 시나리오의 보유 공정이 없어 입력할 칸이 없습니다."
ADMIN_ABSENT_MARK = " · 보유 공정 밖"
ADMIN_ABSENT_PROCESS_GROUP_HELP = (
    "「보유 공정 밖」 공정은 이 시나리오의 보유 공정에 없는 공정입니다. 공용 설정이라 저장해도 "
    "그대로 남고, 그 공정이 있는 시나리오에서는 HOME 공정 필터의 그룹 단추에 듭니다. 빼려면 공정 "
    "그룹 칸을 비웁니다."
)
ADMIN_SAVE_HELP = (
    "모든 사용자가 함께 쓰는 공용 설정으로 저장합니다. HOME 설정 「Capa 요약 · 표시」 탭의 "
    "「공정 그룹」 과 같은 값입니다."
)


@dataclass(frozen=True)
class AdminTab:
    """Admin Area 「공정 그룹」 탭에 붙일 때 — 알림이 열 탭 이름(`state_alerts.tab_name`)과 그 탭이
    이번 회차에 열렸나(닫힌 탭의 읽기 실패는 그 회차에 알리지 않는다)."""

    name: str
    opened: bool


def process_group_editor_key(version: int, processes: Sequence[str]) -> str:
    """편집 표 key — 저장본 version 과 줄 공정(차례 그대로)의 짧은 지문."""
    fingerprint = hashlib.sha256("\x1f".join(processes).encode("utf-8")).hexdigest()[:12]
    return f"{PROCESS_GROUP_EDITOR_KEY_PREFIX}{version}_{fingerprint}"


def render_process_group_editor(
    *,
    process_options: Sequence[str],
    process_labels: ProcessLabels,
    database_path: str,
    read_only: bool,
    save_help: str,
    admin: AdminTab | None = None,
) -> None:
    """공정 그룹 카드 — 공정 · 공정 그룹 두 칸 편집 표와 그 위 저장 줄.

    `process_options` 는 줄로 세울 원본 공정(부르는 쪽 차례 그대로)이고 글자만 표시명이다.
    `read_only` 이면 표가 잠기고 저장 줄(단추 · 메모)이 없다 — 값은 그대로 보인다. `save_help` 는
    저장 단추 풍선이다. `admin` 을 주면 Admin Area 탭 자리다(제목 · 테 · 빈 선택지 글 · 목록 밖
    표지와 풍선 · 읽기 실패 마크 — 모듈 설명).
    """
    submitted_base = seen(PROCESS_GROUP_BASE_VERSION_KEY)
    try:
        profile = load_global_process_group(database_path)
    except BOOTSTRAP_ERRORS as exc:
        if admin is None:
            render_data_error(
                bootstrap_error_message(exc), code="HM-01", text="공정 그룹을 읽지 못했습니다"
            )
        elif admin.opened:
            render_data_error(
                bootstrap_error_message(exc),
                code="AD-07",
                tab=admin.name,
                text="공정 그룹을 읽지 못했습니다",
            )
        return
    with st.container(border=admin is None):
        render_profile_heading(
            PROCESS_GROUP_TITLE if admin is None else ADMIN_TITLE,
            profile,
            key="home_process_group",
            empty=PROCESS_GROUP_EMPTY,
            style=toolbar_room_css(PROCESS_GROUP_SAVE_ROW_KEY),
        )
        if not process_options:
            st.caption(NO_PROCESS_CAPTION if admin is None else ADMIN_NO_PROCESS_CAPTION)
            return
        table, outside = process_group_editor_frame(profile.assignments, process_options)
        processes = [str(process) for process in table[PROCESS_GROUP_COLUMNS[0]]]
        with st.container() if read_only else st.form(PROCESS_GROUP_FORM_KEY):
            submitted, note = False, ""
            if not read_only:
                with st.container(
                    horizontal=True,
                    vertical_alignment="bottom",
                    gap="small",
                    key=PROCESS_GROUP_SAVE_ROW_KEY,
                ):
                    submitted = st.form_submit_button(
                        PROCESS_GROUP_SAVE_LABEL,
                        icon=":material/save:",
                        type="primary",
                        help=save_help,
                    )
                    ready_note_field(
                        PROCESS_GROUP_NOTE_KEY, submitted=submitted, start=submitted_base
                    )
                    note = st.text_input(
                        "변경 메모",
                        placeholder=note_placeholder("DEMO_MOLD 를 PKG 로"),
                        key=PROCESS_GROUP_NOTE_KEY,
                        label_visibility="collapsed",
                    )
            # 저장 결과(성공 · 오류)는 누른 단추 바로 아래 한 자리다. 거부 글도 그 칸 안에 쓴다 —
            # 폼 안 빈 칸은 간격을 먹지 않는다.
            notice = render_flash(PROCESS_GROUP_FLASH_KEY)
            with notice:
                refused = take_refusal(PROCESS_GROUP_SAVE_NAME)
                if refused is not None:
                    st.error(refused)
            edited = st.data_editor(
                table,
                key=process_group_editor_key(profile.version, processes),
                hide_index=True,
                # 줄은 공정 목록이 정한다 — 더하거나 지우지 않는다.
                num_rows="fixed",
                disabled=read_only,
                width="stretch",
                placeholder="",
                column_config=_column_config(
                    processes,
                    outside,
                    process_labels,
                    absent_text=(
                        (ABSENT_MARK, ABSENT_PROCESS_GROUP_HELP)
                        if admin is None
                        else (ADMIN_ABSENT_MARK, ADMIN_ABSENT_PROCESS_GROUP_HELP)
                    ),
                ),
            )
        if not submitted:
            # 이 회차가 그린 저장본이 사용자가 본 화면이다 — 제출 · 충돌 회차에는 적지 않는다.
            remember_seen(PROCESS_GROUP_BASE_VERSION_KEY, profile.version)
            return
        # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
        save_marks = own_save_marks()
        conflict_marks = profile_conflict_marks()
        held = held_profile_conflict(conflict_marks, PROCESS_GROUP_SAVE_NAME)
        if held is not None:
            # 남의 저장에 거부된 누름의 둘째 누름이다 — 옛 화면의 입력이라 저장하지 않고 그 거부를
            # 다시 알린다. 이 회차가 넘어온 거부 글을 이미 그렸으면 한 번만. 본 version 은 이 회차가
            # 그린 최신 저장본으로 적는다(둘째 누름이 끊은 거부 뒤 회차 몫).
            remember_seen(PROCESS_GROUP_BASE_VERSION_KEY, profile.version)
            if refused != held:
                notice.error(held)
            return
        if not isinstance(submitted_base, int):
            # 편집을 시작한 version 을 모른다 — 지금 version 으로 대체하지 않는다.
            queue_refusal(PROCESS_GROUP_SAVE_NAME, SEEN_MISSING_MESSAGE)
            st.rerun(scope="app")
        expected_version = submitted_base
        notices = notice_marks()
        try:
            assignments = assignments_from_editor(edited)
            if (
                profile.version > 0
                and expected_version == profile.version
                and same_process_groups(assignments, profile.assignments)
            ):
                # 방금 저장한 같은 표의 느린 둘째 누름이면 알림 칸이 그 성공을 이미 다시 그렸다.
                if held_notice(PROCESS_GROUP_FLASH_KEY) is None:
                    notice.info(PROCESS_GROUP_UNCHANGED_MESSAGE, icon=":material/info:")
                return
            saved = _save_process_group(
                database_path,
                assignments=assignments,
                source=note.strip() or DEFAULT_SOURCE,
                expected_version=expected_version,
            )
        except ProfileVersionConflict as exc:
            # 다음 회차가 최신 저장본을 그리게 캐시를 비운다. 이 회차는 본 version 을 올리지 않는다.
            clear_global_process_group_cache()
            if is_own_save(PROCESS_GROUP_SAVE_NAME, exc.expected, exc.stored, save_marks):
                # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다. 끊긴 첫 회차가 못 비운
                # 메모 칸도 비운다.
                queue_flash(PROCESS_GROUP_FLASH_KEY, PROCESS_GROUP_SAVED_MESSAGE)
                mark_note_saved_again(PROCESS_GROUP_NOTE_KEY, note)
            else:
                message = bootstrap_error_message(exc)
                note_profile_conflict(conflict_marks, PROCESS_GROUP_SAVE_NAME, message)
                queue_refusal(PROCESS_GROUP_SAVE_NAME, message)
            st.rerun(scope="app")
        except BOOTSTRAP_ERRORS as exc:
            notice.error(_save_error_message(exc))
            return
        remember_own_save(PROCESS_GROUP_SAVE_NAME, expected_version, saved.version, save_marks)
        note_notice(notices, PROCESS_GROUP_FLASH_KEY, PROCESS_GROUP_SAVED_MESSAGE)
        queue_flash(PROCESS_GROUP_FLASH_KEY, PROCESS_GROUP_SAVED_MESSAGE)
        mark_note_saved(PROCESS_GROUP_NOTE_KEY, note)
        st.rerun(scope="app")


def _column_config(
    processes: Sequence[str],
    outside: Sequence[str],
    process_labels: ProcessLabels,
    *,
    absent_text: tuple[str, str],
) -> dict[str, ColumnConfig]:
    """두 칸 — 「공정」(잠김, 값은 원본 · 글자는 표시명) · 「공정 그룹」(빈 칸 = 그룹 없음).

    `absent_text` 는 목록 밖 줄의 표지와 「공정」 칸 풍선이다(자리마다 낱말이 다르다 — 모듈 설명).
    """
    process_column, group_column = PROCESS_GROUP_COLUMNS
    base_format = process_labels.unique_format_func(processes)
    absent = frozenset(outside)
    absent_mark, absent_help = absent_text

    def process_text(value: str | int | float | bool) -> str:
        text = base_format(value)
        return f"{text}{absent_mark}" if value in absent else text

    return {
        process_column: st.column_config.SelectboxColumn(
            "공정",
            options=list(processes),
            format_func=process_text,
            disabled=True,
            help=absent_help if absent else None,
        ),
        group_column: st.column_config.SelectboxColumn(
            PROCESS_GROUP_LABEL,
            options=list(PROCESS_GROUPS),
            required=False,
        ),
    }


def _save_error_message(exc: BaseException) -> str:
    """알림 칸(마크다운)에 그릴 저장 실패 글 — 같은 공정 두 줄은 이름을 막아 다시 짓는다."""
    if isinstance(exc, ProcessGroupDuplicateError):
        return process_group_duplicate_message([literal_markdown(name) for name in exc.names])
    return bootstrap_error_message(exc)


def _save_process_group(
    database_path: str,
    *,
    assignments: Sequence[tuple[str, str]],
    source: str,
    expected_version: int,
) -> GlobalProcessGroup:
    saved = get_scenario_repository(database_path).replace_global_process_group(
        assignments, source=source, expected_version=expected_version
    )
    clear_global_process_group_cache()
    return saved
