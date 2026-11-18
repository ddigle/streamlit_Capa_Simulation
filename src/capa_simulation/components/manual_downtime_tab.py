# Purpose: 가용설비 현황 Preference 탭의 입력 비가동 편집표·버전 대조 저장·이력을 그린다.

"""가용설비 현황 ③ 「Preference」 — 입력 비가동 대수(2026-10-27 사용자 결정).

호기에 잇지 않고 **공정 × 생산월로 넣는 비가동 대수**(환산 대수, 소수)다. 넣은 대수는 실행 쪽
「설비 일정 기준 가용대수」(단축 전 월별 환산 가용)에서 빠진다 — 공정 Capa 상세 ③·⑤, 필요 단축 일정,
제약 시뮬레이션, Space 필요 단축 보기, 이 화면 Summary › Static 대비 일정(그림·시트·확보율
교차검증)이 같이 바뀐다. HOME·Static 의 기준정보 가용과 주차별 가용, Summary › Main(호기 상태)은
그대로다(규칙은 `services/manual_downtime.py`).

- **행은 공정, 열은 조회기간의 달**(사이드바 조회기간 — 생산월, 공정 Capa 상세와 같은 W/D 월)이다.
  공정은 지금 설비 시나리오 저장본의 공정(설비 마스터 `공정소분류` · 기존보유 `공정`)이고, 그 밖에
  저장된 값이 있는 공정도 뒤에 선다(「설비 마스터에 없음」). 보이는 글자만 공정 표시명이다.
- **칸**은 0 이상 소수(둘째 자리)다. 빈칸 = 0 이고 0 칸은 저장하지 않는다.
- **편집표는 폼 밖이고 적은 칸은 세션 초안이다**(`MANUAL_DRAFT` — (공정, 달) → 값, 저장본과 다른
  칸만, 2026-11-19 사용자 요청 「다른 화면에 다녀오거나 테마를 바꾸면 말없이 사라진다」). 칸을 고친
  회차마다 편집표 `on_change` 가 초안에 접고(`_fold_edits` — 콜백은 `app.py` 보다 먼저 돌아 같은
  회차의 화면 탭 점 · 변경 칩 · 테마 · 새로고침 확인이 바로 안다), 본문도 편집표 결과로 다시 접는다.
  편집표는 늘 저장본 위에 초안을 얹어 그린다 — 다른 화면에 다녀와도 칸이 그대로 선다. 초안이 있는
  동안 화면 탭 점 · 이 탭 ③ 점 · 머리 변경 칩(「저장 안 함」 묶음)이 서고, 새로고침 · 탭 닫기 · 테마
  전환이 묻는다. 화면을 옮겨도 초안은 남으므로 탭 줄 떠나기 확인(`page_tabs.leave_notice`)에는 넣지
  않는다(설계 규칙 UI-STA-02 — 잃을 것이 없으면 묻지 않는다). 조회기간을 바꿔 보이지 않게 된 칸도
  초안에 남고 저장은 보이는 칸만이다. 「되돌리기」 가 초안을 버린다. 표를 그리지 않는 화면 — 열람
  등급의 읽기 표(개발자의 「이 등급으로 보기」 포함)는 초안을 얹지도 버리지도 않고 점 · 칩도 세지
  않는다(`manual_downtime_draft_count` 가 0). 「넣을 칸이 없습니다」 화면은 초안이 있으면
  「되돌리기」 하나를 세운다.
- **저장은 버전 대조**다 — 초안이 없는 회차는 그린 저장본의 version 을 본 값으로 적고
  (`write_guard.remember_seen`), 초안이 생기면 그 값을 붙든다(초안이 출발한 version). 저장 회차는
  그 값을 저장소에 넘기고, 그 사이 다른 사람이 저장했으면 저장소가 거부한다(확보율 보정 편집표와
  같은 길 — 제 저장의 빠른 두 번 누름은 성공으로, 거부 뒤 둘째 누름은 거부로 다시 알린다). 초안이
  붙든 version 이 저장본과 달라진 저장 아닌 회차는 제 저장이 끊긴 것이면(`is_own_save`) 저장한 칸을
  초안에서 빼고, 남의 저장이면 초안을 버리고 그 수를 알린다(`MANUAL_DROPPED_MESSAGE` — 곁 경고 ·
  알림창). 저장을 누른 회차가 남의 저장에 지면 거부 글 끝에 버린 칸 수를 붙인다
  (`MANUAL_REFUSED_DROPPED_TAIL`). 두 글과 「되돌리기」 풍선은 지금 표에 보이지 않는 칸이 섞였으면
  그 수도 말한다(`MANUAL_HIDDEN_NOTE`). 남의 저장 뒤에도 숨은 칸을 남길지는 사용자 결정 대기다
  (`docs/TODO.md` 2장 「입력 비가동 대수」). 저장은 **보이는 범위(조회기간 달 × 보이는 공정)만**
  갈아 쓰고 그 밖의 저장 칸은 남긴다.
- **편집표 key 는 표가 출발한 version 을 든다**(`manual_editor_key`). key 붙은 `num_rows="fixed"`
  편집표는 데이터 서명(칸·행·형)이 같으면 같은 위젯이라, 값이 바뀌어도 위젯에 남은 칸 편집이
  그대로 다시 얹힌다 — 남이 저장한 칸이 보이지 않은 채 본 version 만 최신으로 올라가 그 저장을
  거부 없이 덮었다(2026-10-27 리뷰, 사본 앱 두 세션). 그래서 저장 회차는 본 version 으로, 그 밖은
  그 회차가 그린 저장본의 version 으로 key 를 짓는다 — 「본 값」 과 「보이는 칸」 이 늘 같은
  version 이다. 예외 하나 — 남의 저장에 거부된 누름의 둘째 누름 회차(`held_profile_conflict`)는
  저장하지 않고 초안을 버린 뒤 본 version 을 그 회차가 그린 저장본으로 적으므로 key 도 그
  version 이다(2026-11-02 E2E). 바깥 상자는 늘 같은 key(`MANUAL_EDITOR_KEY`)라 화면 확인
  `equipment_preference` 가 그 칸으로 찾는다. 위젯 key 는 `editor_state.editor_widget_key` 를
  지난다(되돌리기의 세대 · 앞 세션 표지).
- **같은 입력의 꼬리 누름**(0.5~1초 간격 두 번 — 둘째 누름이 첫 저장 뒤 새로 그린 표에서 온다)은
  저장소가 바뀐 것이 없다고 돌려줘 「바뀐 것이 없습니다」 가 성공 알림 자리를 차지했다
  (2026-10-27 리뷰). 저장을 `write_guard.save_once` 로 하고 출발점 자리에 **저장할 입력의
  지문**(보이는 공정·달과 0 아닌 칸 — `manual_downtime_digest`)을 준다 — 창 안의 같은 입력은 첫
  결과로 성공을 다시 알린다.
- **모든 설비 시나리오 공용**이다 — Cut-off 처럼 가정 설비 시나리오를 보는 동안에는 표를 잠근다
  (E3 와 같은 규칙. 시나리오별 값은 다음 몫). 잠긴 동안에도 초안은 남아 표에 얹혀 보인다.
- 표는 **숨은 탭에서도 그린다**(저장자 · 메모 칸이 탭 왕복에 남게). 저장자 · 메모 칸은
  `persist_state="session"` 이라 다른 화면에 다녀와도 남는다. 저장 이력 표만 열린 회차에 읽어
  그린다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd
import streamlit as st

from capa_simulation.components import admin_view, grade_ui, sso_identity
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.editor_state import discard_editor, editor_widget_key
from capa_simulation.components.equipment_save_fields import (
    SAVED_BY_LABEL,
    SAVED_BY_PLACEHOLDER,
)
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.profile_caption import render_profile_heading
from capa_simulation.components.saved_note import (
    mark_note_saved,
    mark_note_saved_again,
    note_placeholder,
    ready_note_field,
)
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.components.table_toolbar import toolbar_room_css
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
    save_once,
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
    manual_cell_value,
    manual_downtime_digest,
    manual_units_text,
    prepare_manual_downtime,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.session_slot import SessionSlot
from capa_simulation.settings import EQUIPMENT_DUCKDB_PATH

__all__ = [
    "MANUAL_BASE_VERSION_KEY",
    "MANUAL_COLUMNS_HELP",
    "MANUAL_DRAFT",
    "MANUAL_DROPPED_MESSAGE",
    "MANUAL_EDITOR_KEY",
    "MANUAL_FLASH_KEY",
    "MANUAL_HIDDEN_NOTE",
    "MANUAL_NOTE_KEY",
    "MANUAL_PROCESS_COLUMN",
    "MANUAL_REFUSED_DROPPED_TAIL",
    "MANUAL_REVERT_HIDDEN_HELP",
    "MANUAL_REVERT_BUTTON",
    "MANUAL_SAVED_BY_KEY",
    "MANUAL_SAVED_MESSAGE",
    "MANUAL_SAVE_BUTTON",
    "MANUAL_SAVE_NAME",
    "MANUAL_UNCHANGED_MESSAGE",
    "NOTE_PLACEHOLDER",
    "dropped_text",
    "edited_cells",
    "manual_downtime_draft_count",
    "manual_editor_frame",
    "manual_editor_key",
    "manual_tab_processes",
    "render_manual_downtime_tab",
]

MANUAL_EDITOR_KEY: Final = "equipment_manual_downtime_editor"
# 적은 칸 초안 — (공정, 달) → 값(None = 빈칸), 저장본과 다른 칸만(모듈 docstring). 화면 탭 점 · 변경
# 칩 · 이 탭 ③ 점이 이것을 센다(`manual_downtime_draft_count`).
MANUAL_DRAFT_KEY: Final = "equipment_manual_downtime_draft_v1"
MANUAL_DRAFT: Final = SessionSlot(MANUAL_DRAFT_KEY, dict, dict)
MANUAL_REVERT_KEY: Final = "equipment_manual_downtime_revert"
MANUAL_SAVE_BUTTON_KEY: Final = "equipment_manual_downtime_save"
MANUAL_REVERT_BUTTON: Final = "되돌리기"
# 등급으로 표 도구 막대를 가르는 칸(편집표 · 읽기 표 — 실무자부터)과 저장 이력 칸(설비 화면
# 내려받기 — 관리자부터), 열람의 읽기 표.
MANUAL_TOOLS_KEY: Final = "equipment_manual_downtime_tools"
MANUAL_HISTORY_TOOLS_KEY: Final = "equipment_manual_downtime_history_tools"
MANUAL_VIEW_ONLY_KEY: Final = "equipment_manual_downtime_view_only"
MANUAL_NOTE_KEY: Final = "equipment_manual_downtime_note"
MANUAL_SAVED_BY_KEY: Final = "equipment_manual_downtime_saved_by"
MANUAL_BASE_VERSION_KEY: Final = "equipment_manual_downtime_base_version"
MANUAL_SAVE_NAME: Final = "equipment_manual_downtime"
MANUAL_FLASH_KEY: Final = "equipment_manual_downtime_flash"
# 저장 줄(저장 단추 · 되돌리기 · 저장자 · 변경 메모). 오른쪽 끝을 표 도구 막대 자리로 비운다 — 메모
# 칸은 그 앞까지 늘고 막대가 그 빈 위에 서서 표가 저장 줄 바로 아래(줄 사이 14px)에 붙는다
# (2026-11-10 사용자 그림 메모 「저장 버튼과 시트 사이 여백 조정」, 설계 규칙 UI-LAY-13).
MANUAL_SAVE_ROW_KEY: Final = "equipment_manual_downtime_save_row"
MANUAL_SAVE_BUTTON: Final = "입력 비가동 저장"
# 저장 줄 변경 메모 칸의 안내 글 — 이름 줄 없이 이 글이 칸 이름과 예를 말한다. 오른쪽 끝을 표 도구
# 막대 자리로 비운 줄이라 예는 창 1100 에서도 칸에 다 드는 짧은 글이다.
NOTE_PLACEHOLDER: Final = note_placeholder("26.07 PM 1.5대")
MANUAL_PROCESS_COLUMN: Final = "공정"
MANUAL_SAVED_MESSAGE: Final = (
    "입력 비가동대수를 저장했습니다 — 공정 Capa 상세 ③·⑤·필요 단축 일정·제약 시뮬레이션·"
    "Space 필요 단축 보기·Summary › Static 대비 일정이 새 값으로 계산합니다."
)
# 바꾼 것 없는 저장의 알림 — 새 버전을 만들지 않는다(설계 규칙 UI-STA-01 — 다른 공용 프로필 저장과
# 같은 꼴).
MANUAL_UNCHANGED_MESSAGE: Final = (
    "바뀐 것이 없습니다 — 보이는 칸의 값이 지금 입력 비가동 그대로라 새 버전을 만들지 않았습니다."
)
# 「설비 마스터에 없음」 공정 꼬리(저장된 값만 남은 공정).
_ABSENT_SUFFIX: Final = " (설비 마스터에 없음)"
_HISTORY_LIMIT: Final = 20
# 자리에 늘 두던 설명을 옮긴 풍선(설계 규칙 UI-TXT-01 · UI-TXT-02 — 자리에는 값만). 무엇인가 ·
# 어디에 드나는 구획 제목, 달 · 빈칸은 값 줄, 저장해야 남는다는 것은 저장 단추(UI-NTF-09)다.
MANUAL_INTRO_HELP: Final = (
    "호기에 잇지 않고 공정 × 달로 넣는 비가동대수(환산 대수, 소수 가능)입니다. 호기별 비가동과 "
    "별도 손실로 설비 일정 기준 가용대수에서 더 뺍니다 — 공정 Capa 상세 ③·⑤, 필요 단축 일정, 제약 "
    "시뮬레이션, Space 필요 단축 보기, 이 화면 Summary › Static 대비 일정이 같이 바뀝니다. 그 달 "
    "가용보다 크면 가용은 0 에서 멈춥니다. HOME·Static(기준정보 가용)·표준 목표·표준 대비 "
    "재공(주차별 가용)은 그대로입니다."
)
MANUAL_COLUMNS_HELP: Final = (
    "열은 사이드바 조회기간의 생산월 — 공정별 Cut-off 의 W/D 월(공정 Capa 상세와 같은 달)입니다. "
    "빈칸은 0 이고, 조회기간 밖에 저장된 칸은 그대로 둡니다. 모든 설비 시나리오가 함께 씁니다."
)
MANUAL_SAVE_HELP: Final = (
    "적은 칸은 이 단추를 눌러야 모두에게 남습니다 — 저장 전에는 이 창(세션)에만 남아 다른 화면에 "
    "다녀와도 그대로이고, 새로고침 · 테마 전환에는 사라집니다. 그 사이 다른 사람이 저장하면 적은 "
    "칸은 버려지고 최신 저장본이 섭니다."
)
MANUAL_REVERT_HELP: Final = "저장하지 않은 칸을 모두 버리고 저장본으로 되돌립니다."
# 버리는 초안에 지금 표에 보이지 않는 칸(조회기간 밖 · 표에 없는 공정)이 있으면 그 수를 말한다 —
# 버린 칸 수 바로 뒤(`{hidden}` 자리)와 되돌리기 풍선 끝.
MANUAL_HIDDEN_NOTE: Final = "(지금 표에 보이지 않는 {hidden}칸 포함)"
MANUAL_REVERT_HIDDEN_HELP: Final = (
    " 지금 표에 보이지 않는 {hidden}칸(조회기간 밖 · 표에 없는 공정)도 함께 버립니다."
)
# 남의 저장이 초안을 버린 회차의 곁 경고 · 알림창 글(설계 규칙 UI-STA-05 — 겹친 저장은 말없이 덮지
# 않는다, 버리는 것도 말없이 하지 않는다). `{hidden}` 은 `MANUAL_HIDDEN_NOTE` 이거나 빈 글이다.
MANUAL_DROPPED_MESSAGE: Final = (
    "다른 사용자가 입력 비가동을 저장해 저장하지 않은 칸 {count}개{hidden}를 버렸습니다 — 최신 "
    "저장본을 다시 그렸습니다."
)
# 저장을 누른 회차가 남의 저장에 진 거부 글 끝에 붙이는 버린 칸 수(위와 같은 꼴 — 거부 글이 「다른
# 사용자가 먼저 … 저장해」 를 이미 말한다).
MANUAL_REFUSED_DROPPED_TAIL: Final = " 저장하지 않은 칸 {count}개{hidden}를 버렸습니다."
MANUAL_NO_CELLS_HELP: Final = (
    "설비 마스터를 저장하면 그 공정이 행으로 서고, 열은 사이드바 조회기간의 달입니다."
)


def manual_editor_key(version: int) -> str:
    """편집표 위젯 key — 표가 출발한 저장본 version 을 든다(모듈 docstring). 바깥 상자 key 는
    `MANUAL_EDITOR_KEY` 그대로다."""
    return f"{MANUAL_EDITOR_KEY}__v{int(version)}"


Cell = tuple[str, int]


def manual_downtime_draft_count() -> int:
    """저장하지 않은 입력 비가동 칸 수(보이지 않게 된 칸 포함). 세션만 읽는다 — 화면 탭 점 · 변경
    칩 · 이 화면 ③ 탭 점이 페이지보다 먼저 부른다(칸 편집은 그 회차 첫머리 `on_change` 가 이미
    접었다).

    입력 비가동을 고칠 수 없는 화면 등급(열람 — 개발자의 「이 등급으로 보기」 포함)이면 0 이다 — 그
    등급은 표를 값만 그려 초안을 보이지도 버리지도 못한다. 초안은 지우지 않고 남아, 고칠 수 있는
    등급으로 돌아오면 표에 다시 얹히고 점 · 칩도 다시 선다."""
    draft = MANUAL_DRAFT.get()
    if not draft or not sso_identity.viewer_can("equipment.manual_downtime"):
        return 0
    return len(draft)


def _hidden_count(draft: Mapping[Cell, object], visible: frozenset[Cell]) -> int:
    """초안 가운데 지금 표에 보이지 않는 칸(조회기간 밖 · 표에 없는 공정)의 수."""
    return sum(1 for cell in draft if cell not in visible)


def dropped_text(template: str, draft: Mapping[Cell, object], visible: frozenset[Cell]) -> str:
    """버린 초안 칸 수 글(`MANUAL_DROPPED_MESSAGE` · `MANUAL_REFUSED_DROPPED_TAIL`) — 보이지 않는
    칸이 섞였으면 그 수를 칸 수 바로 뒤에 붙인다."""
    hidden = _hidden_count(draft, visible)
    return template.format(
        count=len(draft), hidden=MANUAL_HIDDEN_NOTE.format(hidden=hidden) if hidden else ""
    )


def _revert_help(draft: Mapping[Cell, object], visible: frozenset[Cell]) -> str:
    hidden = _hidden_count(draft, visible)
    return MANUAL_REVERT_HELP + (MANUAL_REVERT_HIDDEN_HELP.format(hidden=hidden) if hidden else "")


def _draft() -> dict[Cell, float | None]:
    """세션 초안의 사본 — 꼴이 다른 칸(앞 판이 남긴 값)은 뺀다."""
    draft: dict[Cell, float | None] = {}
    for key, value in MANUAL_DRAFT.get().items():
        if (
            isinstance(key, tuple)
            and len(key) == 2
            and isinstance(key[0], str)
            and isinstance(key[1], int)
            and (value is None or isinstance(value, float))
        ):
            draft[(key[0], key[1])] = value
    return draft


def _store_draft(draft: Mapping[Cell, float | None]) -> None:
    if draft:
        MANUAL_DRAFT.set(dict(draft))
    else:
        MANUAL_DRAFT.clear()


def _draft_value(value: object) -> float | None:
    """칸 값을 초안 값으로 — 빈칸 · 0 은 None(빈칸 = 0). 받을 수 없는 값(음수 등)은 숫자면 그대로
    두어 저장이 거절하게 한다(편집표 칸 꼴이 먼저 거른다)."""
    try:
        number = manual_cell_value(value)
    except ValueError:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
    return None if round(number, 9) == 0 else number


def _same(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return round(left, 9) == round(right, 9)


def _folded(
    draft: Mapping[Cell, float | None],
    shown: Mapping[Cell, object],
    saved: Mapping[Cell, float],
) -> dict[Cell, float | None]:
    """초안에 보인 칸 값(`shown` — (공정, 달) → 칸 값)을 접는다 — 저장본과 같으면 빼고 다르면 둔다.
    `shown` 밖의 초안 칸(보이지 않게 된 칸)은 그대로다."""
    folded = dict(draft)
    for cell, raw in shown.items():
        value = _draft_value(raw)
        if _same(value, _draft_value(saved.get(cell))):
            folded.pop(cell, None)
        else:
            folded[cell] = value
    return folded


def _fold_edits(
    widget_key: str,
    processes: tuple[str, ...],
    months: tuple[int, ...],
    saved: Mapping[Cell, float],
) -> None:
    """편집표 `on_change` — 위젯에 남은 칸 편집(`edited_rows` — 줄 위치 → {달 칸: 값})을 초안에
    접는다. 콜백은 `app.py` 보다 먼저 돌아 그 회차의 탭 점 · 변경 칩 · 테마 표지가 바로 안다. 칸
    편집은 위젯에 남아 회차마다 다시 오지만 같은 값을 다시 접어도 같다."""
    state = SessionSlot(widget_key, dict).peek()
    rows = state.get("edited_rows") if state is not None else None
    if not isinstance(rows, Mapping):
        return
    columns = {str(month): month for month in months}
    shown: dict[Cell, object] = {}
    for position, change in rows.items():
        try:
            index = int(position)
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(processes) or not isinstance(change, Mapping):
            continue
        for column, value in change.items():
            month = columns.get(str(column))
            if month is not None:
                shown[(processes[index], month)] = value
    _store_draft(_folded(_draft(), shown, saved))


def _revert(widget_key: str) -> None:
    """「되돌리기」 — 초안을 버리고 편집표를 새 위젯으로 세운다(브라우저에 남은 칸 편집까지)."""
    MANUAL_DRAFT.clear()
    discard_editor(widget_key)


def _settle_draft(profile: ManualDowntime, visible: frozenset[Cell]) -> None:
    """저장 아닌 회차 — 초안이 붙든 version(본 값)이 저장본과 다르면 맞춘다.

    제 저장이 끊긴 것이면(`is_own_save` — 첫 누름이 저장하고 뒷정리 전에 끊겼다) 저장한 칸(보이는
    칸)을 초안에서 빼고 성공을 다시 알린다. 남의 저장이면 초안을 모두 버리고 그 수를 곁 경고 ·
    알림창으로 알린다 — 남의 저장 위에 옛 초안을 얹어 보이지 않은 칸을 덮지 않게(9장 「본 값과
    보이는 칸」). 그 뒤(또는 초안이 없으면) 그린 저장본의 version 을 본 값으로 적는다."""
    draft = _draft()
    base = seen(MANUAL_BASE_VERSION_KEY)
    if draft and base != profile.version:
        if isinstance(base, int) and is_own_save(MANUAL_SAVE_NAME, base, profile.version):
            _store_draft({cell: value for cell, value in draft.items() if cell not in visible})
            queue_flash(MANUAL_FLASH_KEY, MANUAL_SAVED_MESSAGE)
        else:
            MANUAL_DRAFT.clear()
            queue_flash(
                MANUAL_FLASH_KEY,
                dropped_text(MANUAL_DROPPED_MESSAGE, draft, visible),
                kind="warning",
                icon=":material/sync_problem:",
            )
    if not _draft() or base != profile.version:
        remember_seen(MANUAL_BASE_VERSION_KEY, profile.version)


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
    draft: Mapping[Cell, float | None] | None = None,
) -> pd.DataFrame:
    """편집표 — index 는 원본 공정명(감춘다), 첫 칸은 공정 표시명(고칠 수 없다), 달마다 한 칸
    (이름은 `YYYYMM` 글자). 저장된 0 아닌 값만 채우고 나머지는 빈칸(None)이다. `draft` 는 저장본
    위에 얹을 초안 칸이다(None = 빈칸)."""
    cells: dict[Cell, float | None] = {**profile.cells, **(draft or {})}
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
    """탭 본문. 숨은 회차에도 표를 그린다(저장자 · 메모 칸이 탭 왕복에 남게 — 적은 칸은 세션
    초안이 지킨다) — 저장 이력만 열린 회차에 그린다.

    입력 비가동 고치기 · 저장은 실무자부터다(2026-11-18 접속 등급 — 2차 답 「다」). 열람은 같은 표를
    값만 본다(설계 규칙 UI-INP-07 예외 · UI-NTF-05 — 저장 줄 없이 읽기 표). 표 위 작은 단추 줄도
    실무자부터 선다(`grade_ui.toolbar_scope` — 열린 물음: 2차 답이 이 표의 내려받기를 말하지
    않았다)."""
    try:
        profile = load_manual_downtime(database_path)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            "입력 비가동대수를 읽지 못했습니다 — "
            + admin_view.diagnostic_message(
                bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
            ),
            code="EQ-09",
            text="입력 비가동대수를 읽지 못했습니다",
        )
        return
    processes, absent = manual_tab_processes(snapshot_processes, profile)
    ordered_months = sorted({int(month) for month in months})
    _render_intro(profile, ordered_months)
    if locked_reason is not None:
        # 자리에는 표지 한 마디, 까닭은 풍선이다(설계 규칙 UI-TXT-04 · UI-INP-07).
        st.caption(":material/lock: 입력 비가동 잠김", help=locked_reason)
    if not processes or not ordered_months:
        # 빈 결과는 평문 한 줄, 칸이 서는 법은 풍선이다(설계 규칙 UI-TXT-04).
        st.caption("넣을 칸이 없습니다.", help=MANUAL_NO_CELLS_HELP)
        draft = _draft()
        if draft and sso_identity.viewer_can("equipment.manual_downtime"):
            # 다른 설비 시나리오 · 조회기간에서 적은 초안이 남아 점 · 칩이 서 있다 — 표가 없는
            # 화면에서도 버릴 길을 둔다(그 칸은 표가 다시 서면 그대로 얹힌다).
            st.button(
                MANUAL_REVERT_BUTTON,
                icon=":material/undo:",
                key=MANUAL_REVERT_KEY,
                on_click=MANUAL_DRAFT.clear,
                help=MANUAL_REVERT_HELP,
            )
        return
    if not sso_identity.viewer_can("equipment.manual_downtime"):
        with grade_ui.toolbar_scope("equipment.manual_downtime", MANUAL_TOOLS_KEY):
            st.dataframe(
                manual_editor_frame(
                    profile, processes, ordered_months, process_labels, absent=absent
                ),
                hide_index=True,
                width="stretch",
                placeholder="",
                column_config=_month_columns(ordered_months),
                key=MANUAL_VIEW_ONLY_KEY,
            )
    else:
        _render_editor(
            database_path=database_path,
            profile=profile,
            processes=processes,
            absent=absent,
            months=ordered_months,
            process_labels=process_labels,
            locked_reason=locked_reason,
        )
    if not tab_is_hidden(owner_tab):
        with grade_ui.toolbar_scope("equipment.export", MANUAL_HISTORY_TOOLS_KEY):
            _render_history(database_path)


def _month_columns(months: Sequence[int]) -> dict[str, Any]:
    """편집표 · 읽기 표 칸 꼴 — 공정 칸(고정)과 달마다 소수 둘째 자리 대수."""
    return {
        MANUAL_PROCESS_COLUMN: st.column_config.TextColumn("공정", pinned=True, width="medium"),
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
    }


def _render_intro(profile: ManualDowntime, months: Sequence[int]) -> None:
    """제목 줄 하나 — 제목 · 공용 버전 줄(2026-11-08 그림 메모 g18). 열 · 빈칸 · 공용의 뜻은 제목
    아래 줄이 아니라 제목 풍선이다(2026-11-09 상단 띠 재고 — 페이지 상단 문구 최소화, 설계 규칙
    UI-TXT-01 · UI-TXT-02). 조회기간 밖에 저장된 칸은 표에 보이지 않는 저장분이라 있을 때만 버전
    줄에 표지 한 마디로 둔다(UI-TXT-04 · UI-TXT-08)."""
    period = f"{month_label(months[0])}–{month_label(months[-1])}" if months else "없음"
    outside = sum(1 for _, month, _ in profile.rows if month not in set(months))
    render_profile_heading(
        "#### :material/event_busy: 월별 비가동대수(입력)",
        profile,
        key="manual_downtime",
        empty="아직 넣은 입력 비가동이 없습니다",
        detail=f"조회기간 밖 저장 {outside}칸" if outside else None,
        help=f"{MANUAL_INTRO_HELP}\n\n지금 열: 생산월 {period}. {MANUAL_COLUMNS_HELP}",
    )


def _render_editor(
    *,
    database_path: str,
    profile: ManualDowntime,
    processes: Sequence[str],
    absent: frozenset[str],
    months: Sequence[int],
    process_labels: ProcessLabels,
    locked_reason: str | None,
) -> None:
    """편집표와 저장(버전 대조) — 폼 밖이고 적은 칸은 세션 초안이다(모듈 docstring). 저장 차례는
    확보율 보정 편집표(`home_preference`)와 같다."""
    locked = locked_reason is not None
    submitted_base = seen(MANUAL_BASE_VERSION_KEY)
    visible = frozenset((process, int(month)) for process in processes for month in months)
    saved = {cell: units for cell, units in profile.cells.items() if cell in visible}
    st.html(f"<style>{toolbar_room_css(MANUAL_SAVE_ROW_KEY)}</style>")
    # 폼이 두르던 테두리를 그대로 둔다 — 저장 줄 · 알림 칸 · 표가 한 상자다.
    with st.container(border=True):
        # 작업 줄(저장·되돌리기·저장자·메모)은 표 **위**, 버튼이 왼쪽이다 — 오른쪽 끝은 표 도구 막대
        # 자리로 비운다(`MANUAL_SAVE_ROW_KEY`).
        with st.container(
            horizontal=True, vertical_alignment="bottom", gap="small", key=MANUAL_SAVE_ROW_KEY
        ):
            submitted = st.button(
                MANUAL_SAVE_BUTTON,
                icon=":material/save:",
                type="primary",
                key=MANUAL_SAVE_BUTTON_KEY,
                disabled=locked,
                help=locked_reason or MANUAL_SAVE_HELP,
            )
            held = (
                held_profile_conflict(profile_conflict_marks(), MANUAL_SAVE_NAME)
                if submitted
                else None
            )
            if held is not None:
                # 남의 저장에 거부된 누름의 둘째 누름 — 옛 화면의 칸이라 초안을 버리고 최신을
                # 그린다(아래 key 도 그린 저장본 version).
                MANUAL_DRAFT.clear()
            if not submitted:
                _settle_draft(profile, visible)
            # 편집표 key 는 표가 출발한 version — 저장 회차는 본 version, 그 밖은 이 회차가 그린
            # 저장본(모듈 docstring). 남이 저장한 뒤의 회차는 초안을 버리고 새 위젯으로 최신을
            # 그린다. 이것은 **위젯 key** 일 뿐 대조 값이 아니다 — 저장소에 넘기는 대조 값은 아래 본
            # 값(`submitted_base`) 그대로이고, 없으면 저장하지 않는다(write_guard).
            if submitted and held is None and isinstance(submitted_base, int):
                started = submitted_base
            else:
                started = profile.version
            widget_base = manual_editor_key(started)
            # 잠가 그리지 않는다 — 칸을 고친 회차와 누른 회차가 같으면 잠긴 단추의 누름을
            # 버린다(AGENTS 9장). 초안이 없으면 누름이 할 일이 없다.
            st.button(
                MANUAL_REVERT_BUTTON,
                icon=":material/undo:",
                key=MANUAL_REVERT_KEY,
                on_click=_revert,
                args=(widget_base,),
                help=_revert_help(_draft(), visible),
            )
            # 저장자 칸은 저장에 비우지 않는다 — 다음 저장에 이어 쓴다. 메모만 저장에 비운다
            # (saved_note). 두 칸은 다른 화면에 다녀와도 남는다(`persist_state` — 초안과 같은 세션).
            # 두 칸은 라벨 줄을 걷고 칸 안 안내 글(placeholder)이 이름을 말한다 — 라벨은 접근성
            # 이름으로 남는다(2026-11-09 상단 띠 재고 — 페이지 상단 여백 최소화, UI-TXT-01 예외
            # 「사람이 쓰는 자유 글 칸의 안내 글」).
            saved_by = st.text_input(
                SAVED_BY_LABEL,
                placeholder=SAVED_BY_PLACEHOLDER,
                key=MANUAL_SAVED_BY_KEY,
                disabled=locked,
                label_visibility="collapsed",
                persist_state="session",
            )
            ready_note_field(MANUAL_NOTE_KEY, submitted=submitted, start=submitted_base)
            note = st.text_input(
                "변경 메모",
                placeholder=NOTE_PLACEHOLDER,
                key=MANUAL_NOTE_KEY,
                disabled=locked,
                label_visibility="collapsed",
                persist_state="session",
            )
        # 저장 결과(성공·오류)와 남의 저장이 버린 초안의 경고는 누른 버튼 바로 아래 한 자리다. 거부
        # 글도 그 알림 칸 안에 쓴다 — 빈 알림 칸은 간격을 먹지 않는다
        # (`app_header.EMPTY_SLOT_SELECTOR`).
        notice = render_flash(MANUAL_FLASH_KEY)
        with notice:
            refused = take_refusal(MANUAL_SAVE_NAME)
            if refused is not None:
                st.error(refused)
        frame = manual_editor_frame(
            profile, processes, months, process_labels, absent=absent, draft=_draft()
        )
        # 표 앞 띄움을 두지 않는다 — 표 도구 막대(표 머리 위 37px)는 저장 줄 오른쪽 끝 빈 자리
        # 위에 선다(AGENTS 9장 「표 도구 막대」 — 저장 줄 → 표 14px, 빈 알림 칸은 간격을 먹지
        # 않는다).
        with (
            grade_ui.toolbar_scope("equipment.manual_downtime", MANUAL_TOOLS_KEY),
            st.container(key=MANUAL_EDITOR_KEY),
        ):
            widget_key = editor_widget_key(widget_base)
            edited = st.data_editor(
                frame,
                key=widget_key,
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                # 결측 칸은 `None` 글자가 아니라 빈칸으로 그린다(`month_editor` 와 같은 규칙).
                placeholder="",
                disabled=True if locked else [MANUAL_PROCESS_COLUMN],
                column_config=_month_columns(months),
                on_change=_fold_edits,
                args=(widget_key, tuple(processes), tuple(int(month) for month in months), saved),
            )
        # 본문도 편집표 결과로 접는다 — 콜백이 돌지 않은 회차(시험이 위젯 값을 직접 적음 등)에도
        # 초안이 보이는 칸과 맞는다. 같은 값을 다시 접어도 같다.
        _store_draft(_folded(_draft(), edited_cells(edited, processes, months), saved))
    if not submitted:
        return
    # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    save_marks = own_save_marks()
    conflict_marks = profile_conflict_marks()
    if held is not None:
        # 남의 저장에 거부된 누름의 둘째 누름이다 — 옛 화면의 입력이라 저장하지 않고 그 거부를 다시
        # 알린다. 본 version 은 이 회차가 그린 최신 저장본으로 적는다(확보율 보정과 같다 — 칸도
        # 위에서 그 version 으로 그렸다).
        remember_seen(MANUAL_BASE_VERSION_KEY, profile.version)
        if refused != held:
            notice.error(held)
        return
    if not isinstance(submitted_base, int):
        # 편집을 시작한 version 을 모른다 — 지금 version 으로 대체하지 않는다(write_guard).
        queue_refusal(MANUAL_SAVE_NAME, SEEN_MISSING_MESSAGE)
        st.rerun(scope="app")
    expected_version = submitted_base
    cells = edited_cells(edited, processes, months)
    raw: dict[tuple[object, object], object] = {key: value for key, value in cells.items()}
    try:
        # 저장할 입력의 지문 — 같은 입력의 꼬리 누름을 첫 결과로 알린다(모듈 docstring).
        start = (
            tuple(processes),
            tuple(int(month) for month in months),
            manual_downtime_digest(prepare_manual_downtime(raw)),
        )
    except ValueError as exc:
        notice.error(
            admin_view.diagnostic_message(
                bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
            )
        )
        return
    repository = get_equipment_repository(database_path)
    reviewer = str(saved_by or "")
    memo = str(note or "")

    def save() -> tuple[int | None, str]:
        # 세션 칸을 읽지 않는다(`save_once` 의 잠금 안) — 짝은 미리 받아 둔 dict 에 적는다.
        stored = repository.save_manual_downtime(
            cells,
            processes=processes,
            months=months,
            expected_version=expected_version,
            saved_by=reviewer,
            note=memo,
        )
        if stored is not None:
            remember_own_save(MANUAL_SAVE_NAME, expected_version, stored, save_marks)
        return stored, memo

    try:
        version, saved_memo = save_once(
            MANUAL_SAVE_NAME, start, save, wrote=lambda outcome: outcome[0] is not None
        )
    except ProfileVersionConflict as exc:
        # 앱 밖의 쓰기면 이 회차가 그린 저장본도 낡았을 수 있다 — 다음 회차가 최신을 그리게 비운다.
        # 이 회차는 본 version 을 올리지 않는다(다음 회차가 최신을 그리며 적는다).
        clear_manual_downtime_cache()
        if is_own_save(MANUAL_SAVE_NAME, exc.expected, exc.stored, save_marks):
            # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard). 끊긴 첫 회차가
            # 못 비운 메모 칸 · 초안의 보이는 칸도 비운다(saved_note).
            _forget_visible(visible)
            queue_flash(MANUAL_FLASH_KEY, MANUAL_SAVED_MESSAGE)
            mark_note_saved_again(MANUAL_NOTE_KEY, memo)
        else:
            # 남의 저장에 졌다 — 초안을 버려 다음 회차가 최신 저장본을 그린다. 버린 칸 수(보이지
            # 않는 칸 포함)는 거부 글 끝에 붙인다 — 저장 아닌 회차의 버림 알림과 같이 말없이 버리지
            # 않는다(설계 규칙 UI-STA-05). 충돌 표지에도 같은 글을 적어 둘째 누름이 같은 글을 다시
            # 알린다(`held_profile_conflict` — 글이 다르면 두 상자가 선다).
            dropped = _draft()
            message = admin_view.diagnostic_message(
                bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
            ) + (dropped_text(MANUAL_REFUSED_DROPPED_TAIL, dropped, visible) if dropped else "")
            note_profile_conflict(conflict_marks, MANUAL_SAVE_NAME, message)
            MANUAL_DRAFT.clear()
            queue_refusal(MANUAL_SAVE_NAME, message)
        st.rerun(scope="app")
    except BOOTSTRAP_ERRORS as exc:
        notice.error(
            admin_view.diagnostic_message(
                bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
            )
        )
        return
    except ValueError as exc:
        notice.error(
            admin_view.diagnostic_message(
                bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
            )
        )
        return
    if version is None:
        # 보이는 칸이 저장본 그대로다 — 그 칸의 초안도 할 일이 없다.
        _forget_visible(visible)
        notice.info(MANUAL_UNCHANGED_MESSAGE, icon=":material/info:")
        return
    # 같은 칸의 겹친 누름은 `save_once` 가 첫 결과를 돌려줘 이 회차가 쓰지 않았다 — 칸 글이 첫
    # 누름이 쓴 메모일 때만 비운다(saved_note).
    if memo == saved_memo:
        mark_note_saved(MANUAL_NOTE_KEY, memo)
    # 저장한 칸(보이는 칸)은 초안에서 뺀다 — 조회기간 밖이라 보이지 않은 칸만 남는다.
    _forget_visible(visible)
    if version <= expected_version:
        # 같은 입력의 꼬리 누름 — 첫 누름이 이미 그 version 을 썼다(`save_once` 가 첫 결과를 돌려준
        # 것). 제 저장 짝은 첫 누름이 적었으므로 바꾸지 않고 성공만 다시 알린다.
        queue_flash(MANUAL_FLASH_KEY, MANUAL_SAVED_MESSAGE)
        st.rerun(scope="app")
    # 저장마다 공정 Capa 상세·필요 단축 일정 등의 계산 키(칸 자체)가 바뀐다 — 프로필 캐시만 비운다.
    clear_manual_downtime_cache()
    queue_flash(MANUAL_FLASH_KEY, MANUAL_SAVED_MESSAGE)
    st.rerun(scope="app")


def _forget_visible(visible: frozenset[Cell]) -> None:
    """초안에서 보이는 칸을 뺀다(저장했거나 저장본 그대로인 칸) — 보이지 않게 된 칸만 남는다."""
    _store_draft({cell: value for cell, value in _draft().items() if cell not in visible})


def _render_history(database_path: str) -> None:
    """저장 이력(최근 것부터) — 위젯 없는 읽기 전용 표라 열린 회차에만 읽는다."""
    try:
        saves = load_manual_downtime_saves(database_path, limit=_HISTORY_LIMIT)
    except BOOTSTRAP_ERRORS as exc:
        message = admin_view.diagnostic_message(
            bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
        )
        render_data_error(
            f"저장 이력을 읽지 못했습니다 — {message}",
            code="EQ-09",
            text="입력 비가동 저장 이력을 읽지 못했습니다",
        )
        return
    with st.expander(
        f":material/history: 저장 이력 {len(saves)}건"
        + (f"(최근 {_HISTORY_LIMIT}건)" if len(saves) >= _HISTORY_LIMIT else ""),
        key="equipment_manual_downtime_history",
    ):
        if not saves:
            st.caption("아직 저장한 적이 없습니다.")
            return
        st.dataframe(_history_frame(saves), hide_index=True, width="stretch", placeholder="")


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
