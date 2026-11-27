# Purpose: Admin 「부대공정」 탭의 앱 작성 편집기 — 공정 · 생산성 · 설비 · 효율 표를 범용 그리드
# 한 마운트(종류 단추)로 그리고, 공정 더하기 · 참조 바꾸기 꼴과 판 만들기(받은 판 자리에 싣기)를
# 맡는다.

"""Admin 「부대공정」 — 판을 앱에서 쓰는 셋째 길(CSV · S3 Drive 가져오기 · 「새 판으로」 곁).

**정본은 그리드 초안이다**(순수 몸통 `services/extra_process_editor.py` 의 화면 계약 1 ~ 10).
회차마다 펼친 판(`EDITOR` — 펼친 때의 판 이력 차례 · sha · 바이트)에서 모형을 다시 짓는다 —
`with_cells(with_lines(model_from_pack(바탕), 줄 그리드 전체), 값 그리드 전체)`. 병합이 아니라 전체
상태라 그리드 되돌리기 · 「적용 전」 서랍이 그대로 먹는다. 세션에는 기본형만 둔다(바탕 바이트 ·
줄 씨앗 tuple · 칸 이름 지도). 흡수할 때마다 `redundant_cells` 를 초안에서 지운다 — 남기면 다른 창의
이후 칸처럼 숨은 옛 입력이 되살아난다. `ignored_cells` 는 지우지 않는다(경로가 넓어지면 산다).

- **표 넷 · 마운트 하나**(UI-LAY-07) — 종류 단추 「공정 · 생산성 · 설비 · 효율」. 형식이 칸마다라
  값 표를 판 파일(03 · 04 · 05)마다 나눈다. 공정 표는 줄 규칙 표(지우기 · 되살리기)이고, 통째 옮김
  줄은 지우기만 열린다. 값 표 줄은 살아 있는 편집기 몫 줄에서 짓는다 — 공정을 지우면 값 줄이
  함께 빠진다.
- **월 칸** = [이전(읽기 전용)] + 계획 첫 달 ~ 끝 달(`YY.MM`) + [이후(한 값이면 고침)]. 칸 이름이
  머리 글이라 이전 · 이후 칸 이름에 그 달을 싣는다(「~26.12」 · 「27.07~」) — 이후 칸은 절대
  `Onward` 열쇠라 시나리오가 바뀌어도 옛 이후 칸 초안이 숨은 칸으로 남는다. 칸 이름 → 달은 세션
  지도(`COLUMNS`)가 기억한다. 양식은 `CellView.default`, 잠금은 `not editable`(까닭은 줄마다 한 글).
- **고르기** — 줄마다 후보가 달라지는 참조공정 · (STEP, MCP) 조합은 그리드 칸이 아니라 표 위
  「공정 더하기 · 참조 바꾸기」 팝오버의 Streamlit 고르기(찾기 · 「표시명 (원본)」 — UI-DAT-10)다.
  조합 칸은 직접 넣는 글도 받는다(결정3 — UI-INP-05). 그리드의 그 칸들은 읽기 전용 글이고, 목록이
  짧고 줄과 무관한 Area 만 그리드 고르기다. 팝오버 값은 「더하기」 · 「바꾸기」 누름에만 씨앗
  (`LINES`)에 들어간다 — 새 줄의 기본값(`line_defaults`)은 더한 때 고정한다.
- **자리 차례**(늘 같은 칸 — 그리드 앞에 조건부 형제를 두지 않는다): 작업 줄(종류 · 팝오버) →
  그리드 → 판 줄(00 메모 · 「판 만들기」 · 「확인할 칸 n」). 받은 판 상자는 그
  뒤(`extra_process_admin`).
- **판 만들기**(누른 회차) — 출납을 다시 모아 반영 · 흡수한 뒤(G2) 판 번호(마지막 내용 판 + 1) ·
  작성시각(KST 초) · 작성자(통합인증 이름, 없으면 빈칸)를 한 번 고정해 `fold` → `canonical` 로
  짓는다. 00 고정 본문이 펼친 판과 같으면 받은 판을 두지 않고 「바뀐 것 없음」, 펼친 뒤 판
  이력이 움직였으면 적용할 수 없는 판으로 싣는다. 입력 문제는 막지 않는다(관문이 정본 — 표지
  「확인할 칸 n」).
- **잠금**(UI-INP-07) — 진입 · 판 만들기는 `write_lock_reason`(C-DEP 밖 · 개발자 아님)으로 잠그고,
  진입은 활성 판 내용을 못 읽을 때(G1) · 활성 시나리오 · 계획 월이 없을 때도 잠근다.
- **탭 점** — 술어는 「모형이 펼친 판과 다름」(`effective_edits` 가 있거나 줄이 바뀜)이고 흡수 때
  세션 표지(`DIRTY`)로 둔다. 화면 탭 줄은 페이지보다 먼저 그려 출납 콜백이 새 op 를 받으면 먼저
  켠다(`page_tabs.page_unsaved_marks`).
- 닫힌 탭은 그리지 않는다 — 초안 · inbox 는 세션에 남고 다시 연 회차가 반영한다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import astuple, dataclass, replace
from datetime import datetime
from typing import Any, Final

import pandas as pd
import streamlit as st

from capa_simulation.components import edit_grid, sso_identity
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.state_alerts import tab_name
from capa_simulation.extra_process_intake import (
    EditorOrigin,
    StagedPack,
    previous_content,
    stage_editor_pack,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.korea_time import KST
from capa_simulation.navigation import ADMIN_AREA_TABS
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.models import ExtraProcessState, ExtraProcessVersion
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import active_persisted_scenario_id
from capa_simulation.services.edit_grid import (
    DraftState,
    GridSpec,
    LockKind,
    RowRules,
    ValueFormat,
    removed_keys,
)
from capa_simulation.services.edit_grid_payload import EditGridBase, build_base
from capa_simulation.services.extra_process_editor import (
    BASE_LINE_PREFIX,
    EQUIPMENT,
    LENT_COLUMN,
    OWNED_COLUMN,
    PRODUCTIVITY,
    RATE,
    RUN_RATE_COLUMN,
    VITAL_COLUMN,
    CellInput,
    CellKey,
    EditorContext,
    EditorModel,
    FollowPreview,
    InputProblem,
    LineFields,
    LineView,
    Onward,
    RowKey,
    editor_context,
    editor_warnings,
    effective_edits,
    fold,
    follow_preview,
    ignored_cells,
    input_problems,
    line_defaults,
    model_from_pack,
    month_view,
    plan_span,
    redundant_cells,
    reference_choices,
    same_body,
    value_rows,
    with_cells,
    with_lines,
)
from capa_simulation.services.extra_process_editor import canonical as canonical_pack
from capa_simulation.services.extra_process_merge import split_previous
from capa_simulation.services.extra_process_pack import (
    ENGINEERING,
    FORMAT_VERSION,
    MASS,
    ExtraProcessPack,
    PackInfo,
    PackJudgement,
    Period,
    read_pack_zip,
)
from capa_simulation.services.frame_contracts import AREA_NAMES
from capa_simulation.services.month_columns import month_label
from capa_simulation.session_slot import SessionSlot

TAB_LABEL: Final = ADMIN_AREA_TABS[3]
HOST: Final = "admin-extra-editor-grid"
FLASH_KEY: Final = "admin_extra_editor_flash"
OPEN_BUTTON_KEY: Final = "admin_extra_editor_open"
CLOSE_BUTTON_KEY: Final = "admin_extra_editor_close"
CLOSE_CONFIRM_KEY: Final = "admin_extra_editor_close_confirm"
MAKE_BUTTON_KEY: Final = "admin_extra_editor_make"
KIND_KEY: Final = "admin_extra_editor_kind"
MEMO_KEY: Final = "admin_extra_editor_memo"
LINE_PICK_KEY: Final = "admin_extra_editor_line_pick"
NAME_INPUT_KEY: Final = "admin_extra_editor_new_name"
REFERENCE_PICK_KEY: Final = "admin_extra_editor_reference"
STEP_PICK_KEY: Final = "admin_extra_editor_step"
LINE_BUTTON_KEY: Final = "admin_extra_editor_line_apply"
ADD_MENU_KEY: Final = "admin_extra_editor_add_menu"
CHECK_MENU_KEY: Final = "admin_extra_editor_check_menu"
ACTIONS_BOX: Final = "admin_extra_editor_actions"
ACTION_ROW: Final = "admin_extra_editor_action_row"
GRID_BOX: Final = "admin_extra_editor_grid_box"
MAKE_BOX: Final = "admin_extra_editor_make_box"

EDITOR_KEY: Final = "admin_extra_editor"
LINES_KEY: Final = "admin_extra_editor_lines"
COLUMNS_KEY: Final = "admin_extra_editor_columns"
CONTEXT_KEY: Final = "admin_extra_editor_context"
FOLLOW_KEY: Final = "admin_extra_editor_follow"
DIRTY_KEY: Final = "admin_extra_editor_dirty"
BASE_SEEN_KEY: Final = "admin_extra_editor_base_seen"
BASE_PACK_KEY: Final = "admin_extra_editor_base_pack"
INBOX_KEY: Final = "admin_extra_editor_inbox"
APPLIED_KEY: Final = "admin_extra_editor_applied"
TOAST_KEY: Final = "admin_extra_editor_toast"
DISCARDED_KEY: Final = "admin_extra_editor_discarded"
LINE_CELLS_KEY: Final = "admin_extra_editor_lines_cells"
LINE_HISTORY_KEY: Final = "admin_extra_editor_lines_history"
PRODUCTIVITY_CELLS_KEY: Final = "admin_extra_editor_productivity_cells"
PRODUCTIVITY_HISTORY_KEY: Final = "admin_extra_editor_productivity_history"
EQUIPMENT_CELLS_KEY: Final = "admin_extra_editor_equipment_cells"
EQUIPMENT_HISTORY_KEY: Final = "admin_extra_editor_equipment_history"
RATE_CELLS_KEY: Final = "admin_extra_editor_rate_cells"
RATE_HISTORY_KEY: Final = "admin_extra_editor_rate_history"

KEYS: Final = edit_grid.GridKeys(
    inbox=INBOX_KEY, applied=APPLIED_KEY, toast=TOAST_KEY, discarded=DISCARDED_KEY
)
LINE_TABLE: Final = "EXTRA_LINES"
PRODUCTIVITY_TABLE: Final = "EXTRA_PRODUCTIVITY"
EQUIPMENT_TABLE: Final = "EXTRA_EQUIPMENT"
RATE_TABLE: Final = "EXTRA_RATE"
# 종류 단추 글 → 표(차례가 단추 차례).
KINDS: Final = {
    "공정": LINE_TABLE,
    "생산성": PRODUCTIVITY_TABLE,
    "설비": EQUIPMENT_TABLE,
    "효율": RATE_TABLE,
}
TABLE_KEYS: Final = {
    LINE_TABLE: (LINE_CELLS_KEY, LINE_HISTORY_KEY),
    PRODUCTIVITY_TABLE: (PRODUCTIVITY_CELLS_KEY, PRODUCTIVITY_HISTORY_KEY),
    EQUIPMENT_TABLE: (EQUIPMENT_CELLS_KEY, EQUIPMENT_HISTORY_KEY),
    RATE_TABLE: (RATE_CELLS_KEY, RATE_HISTORY_KEY),
}
VALUE_TABLES: Final = {
    PRODUCTIVITY_TABLE: PRODUCTIVITY,
    EQUIPMENT_TABLE: EQUIPMENT,
    RATE_TABLE: RATE,
}

OPEN_LABEL: Final = "앱에서 작성"
CLOSE_LABEL: Final = "작성 닫기"
CLOSE_CONFIRM_LABEL: Final = "버리고 닫기"
MAKE_LABEL: Final = "판 만들기"
ADD_MENU_LABEL: Final = "공정 더하기 · 참조 바꾸기"
ADD_LABEL: Final = "더하기"
CHANGE_LABEL: Final = "바꾸기"
NEW_LINE: Final = "새 공정"
MEMO_LABEL: Final = "판 메모"
CHANGES_LABEL: Final = "적용 전 변경"
OPEN_HELP: Final = (
    "활성 판(끈 동안은 마지막 판, 판이 없으면 빈 판)을 펼쳐 표로 고칩니다 — 「판 만들기」 · "
    "「새 판 적용」 을 눌러야 바뀝니다."
)
CLOSE_HELP: Final = "작성을 닫습니다."
CLOSE_DIRTY_HELP: Final = "고친 것을 버리고 작성을 닫습니다."
MAKE_HELP: Final = (
    "고친 표로 다음 판을 만들어 받은 판 자리에 둡니다(받아 둔 판을 바꿈) — 판은 통째로 바뀌어 "
    "지운 공정은 빠지고, 「새 판 적용」 을 눌러야 들어갑니다."
)
ADD_HELP: Final = "참조공정과 STEP · MCP 조합을 골라 새 공정을 더하거나 고른 줄의 참조를 바꿉니다."
STEP_HELP: Final = "목록에 없는 조합은 「STEP · MCP」 꼴로 적습니다."
NO_PLAN_REASON: Final = "올라와 있는 시나리오에 계획 월이 없습니다"
UNREADABLE_REASON: Final = "부대공정 판 내용을 읽지 못해 펼칠 수 없습니다"
UNCHANGED_EDITOR: Final = "바뀐 것 없음 — 펼친 판과 같은 판입니다"
MOVED_VERDICT: Final = "moved"
MOVED_REASON: Final = (
    "펼친 뒤 다른 판이 들어와 적용할 수 없습니다 — 「작성 닫기」 뒤 다시 펼쳐 고칩니다"
)
NO_REFERENCE: Final = "참조공정을 고릅니다"
BAD_STEP: Final = "STEP · MCP 를 「STEP · MCP」 꼴로 적습니다"
# 탭 점 풍선(`page_tabs.page_unsaved_marks`).
UNSAVED_NOTE: Final = "적용하지 않은 부대공정 작성"
CHECK_LABEL: Final = "확인할 칸 {n}"
CHECK_COLUMNS: Final = ("공정", "표", "칸", "달", "까닭")

# 공정 표 칸.
NO_COLUMN: Final = "No."
ID_COLUMN: Final = "_id"
LABEL_COLUMN: Final = "_label"
NAME_COLUMN: Final = "공정"
AREA_COLUMN: Final = "Area_Name"
BASIS_COLUMN: Final = "소요기준"
MODULES_COLUMN: Final = "모듈수"
REFERENCE_COLUMN: Final = "참조공정"
STEP_COLUMN: Final = "STEP_SEQ"
MCP_COLUMN: Final = "MCP_SEQ"
START_COLUMN: Final = "시작월"
END_COLUMN: Final = "끝월"
MEMO_COLUMN: Final = "메모"
CARRY_COLUMN: Final = "옮김"
LINE_COLUMNS: Final = (
    NAME_COLUMN,
    AREA_COLUMN,
    BASIS_COLUMN,
    MODULES_COLUMN,
    REFERENCE_COLUMN,
    STEP_COLUMN,
    MCP_COLUMN,
    START_COLUMN,
    END_COLUMN,
    MEMO_COLUMN,
    CARRY_COLUMN,
)
PICKED_COLUMNS: Final = (BASIS_COLUMN, REFERENCE_COLUMN, STEP_COLUMN, MCP_COLUMN, CARRY_COLUMN)
PICKED_WHY: Final = (
    "소요기준 · 참조공정 · STEP · MCP 는 「공정 더하기 · 참조 바꾸기」 에서 고릅니다"
)
CARRIED_WHY: Final = "통째 옮김({reason}) — 줄 지우기만 됩니다"
# 고칠 수 있는 공정 표 칸 → `LineFields` 이름.
_EDITABLE: Final = {
    NAME_COLUMN: "name",
    AREA_COLUMN: "area",
    MODULES_COLUMN: "modules",
    START_COLUMN: "start",
    END_COLUMN: "end",
    MEMO_COLUMN: "memo",
}
_MONTH_PATTERN: Final = r"\d{6}"
_TEXT: Final = ValueFormat("text", 0)
LINE_SPEC: Final = GridSpec(
    table=LINE_TABLE,
    title="공정",
    key_columns=(NO_COLUMN,),
    value_columns=LINE_COLUMNS,
    fmt=_TEXT,
    column_formats=(
        (NAME_COLUMN, ValueFormat("text", 0, max_length=100)),
        (AREA_COLUMN, ValueFormat("choice", 0, options=AREA_NAMES)),
        (BASIS_COLUMN, _TEXT),
        (MODULES_COLUMN, ValueFormat("sig", 6)),
        (REFERENCE_COLUMN, _TEXT),
        (STEP_COLUMN, _TEXT),
        (MCP_COLUMN, _TEXT),
        (START_COLUMN, ValueFormat("text", 0, pattern=_MONTH_PATTERN)),
        (END_COLUMN, ValueFormat("text", 0, pattern=_MONTH_PATTERN)),
        (MEMO_COLUMN, ValueFormat("text", 0, max_length=200)),
        (CARRY_COLUMN, _TEXT),
    ),
    id_column=ID_COLUMN,
    label_column=LABEL_COLUMN,
    row_ops=True,
)
# 값 표 — 분류 칸 공정 · 구분, 형식 · 머리 풍선은 표마다.
VALUE_KEY_COLUMNS: Final = ("공정", "구분")
VALUE_TITLES: Final = {PRODUCTIVITY_TABLE: "생산성", EQUIPMENT_TABLE: "설비", RATE_TABLE: "효율"}
VALUE_FORMATS: Final = {
    PRODUCTIVITY_TABLE: ValueFormat("sig", 6),
    EQUIPMENT_TABLE: ValueFormat("fixed", 2),
    RATE_TABLE: ValueFormat("percent", 2),
}
VALUE_HELPS: Final = {
    PRODUCTIVITY_TABLE: (
        "UPEH — MI 공정도 UPEH 로 적습니다(판에는 ST = 60 / UPEH). ER 은 고치지 않으면 같은 달 "
        "양산 값을 따르고, 끝의 「이후」 칸은 그 달부터 경로 끝까지 한 값입니다."
    ),
    EQUIPMENT_TABLE: (
        "설비보유 · 설비대여평가(빈칸 = 0) — 대여는 보유보다 클 수 없습니다. 끝의 「이후」 칸은 그 "
        "달부터 경로 끝까지 한 값입니다."
    ),
    RATE_TABLE: (
        "효율(CAPA_RUN_RATE) · 편중률 — ER 은 고치지 않으면 같은 달 양산 값을 따르고, 끝의 "
        "「이후」 칸은 그 달부터 경로 끝까지 한 값입니다."
    ),
}
# (표, 양산구분, 칸) → 구분 글.
ROW_LABELS: Final = {
    (PRODUCTIVITY, MASS): "양산",
    (PRODUCTIVITY, ENGINEERING): "ER",
    (EQUIPMENT, OWNED_COLUMN): "보유",
    (EQUIPMENT, LENT_COLUMN): "대여",
    (RATE, MASS, RUN_RATE_COLUMN): "양산 효율",
    (RATE, MASS, VITAL_COLUMN): "양산 편중률",
    (RATE, ENGINEERING, RUN_RATE_COLUMN): "ER 효율",
    (RATE, ENGINEERING, VITAL_COLUMN): "ER 편중률",
}
TABLE_WORDS: Final = {
    "": "판",
    "01": "공정",
    PRODUCTIVITY: "생산성",
    EQUIPMENT: "설비",
    RATE: "효율",
}
NO_PERIOD_WHY: Final = "시작월 · 끝월을 먼저 적습니다"
BEFORE_WHY: Final = "이전 칸은 읽기 전용"
MULTIPLE_WHY: Final = "여러 값 — 한 값으로 고칠 수 없음"
OUTSIDE_WHY: Final = "경로 밖 달"
# 표 위 작업 줄과 표 도구 막대를 한 줄로(`edit_grid.one_line_style`).
ONE_LINE_STYLE: Final = edit_grid.one_line_style(
    ACTIONS_BOX, ACTION_ROW, GRID_BOX, min_window_px=1300, reserve_px=520
)
_FOLLOW_MEMO_LIMIT: Final = 16

# 세션 칸(AGENTS 5장 42). 펼친 판 = (펼친 때의 판 이력 차례, 바탕 sha 또는 None, 바탕 바이트 또는
# None). 줄 씨앗 = 줄 id → `LineFields` 칸 값 tuple(새 줄 · 참조를 바꾼 줄). 칸 지도 = 값 표 칸
# 이름 → (갈래 "m" · "after" · "before", 달).
EDITOR: Final = SessionSlot(EDITOR_KEY, tuple)
LINES: Final = SessionSlot(LINES_KEY, dict, dict)
COLUMNS: Final = SessionSlot(COLUMNS_KEY, dict, dict)
# (맥락 열쇠, `EditorContext`) — (시나리오 id, 기준정보 판)마다 한 번 센다.
CONTEXT: Final = SessionSlot(CONTEXT_KEY, tuple, tuple)
# (맥락 열쇠, 참조, 소요기준, 시작, 끝) → `FollowPreview`.
FOLLOW: Final = SessionSlot(FOLLOW_KEY, dict, dict)
DIRTY: Final = SessionSlot(DIRTY_KEY, bool, bool)
# (판 sha, 읽혔나) — 진입 잠금(G1)을 판 sha 마다 한 번 본다.
BASE_SEEN: Final = SessionSlot(BASE_SEEN_KEY, tuple, tuple)
# (펼친 판 sha, 읽은 판) — 회차마다 관문을 다시 돌리지 않게.
BASE_PACK: Final = SessionSlot(BASE_PACK_KEY, tuple, tuple)
KIND: Final = SessionSlot(KIND_KEY, str)
MEMO: Final = SessionSlot(MEMO_KEY, str)
INBOX: Final = SessionSlot(INBOX_KEY, list)


@dataclass(frozen=True)
class Hooks:
    """받은 판 상자(`extra_process_admin`)가 넘기는 것 — 쓰기 잠금 판정(누른 회차에 다시 부름),
    받은 판 두기 · 비우기."""

    lock: Callable[[], str | None]
    place: Callable[[StagedPack], None]
    discard: Callable[[], None]


# --------------------------------------------------------------------------- 세션 상태


def editor_open() -> bool:
    return EDITOR.peek() is not None


def editor_has_edits() -> bool:
    """탭 점 · 새로고침 확인의 술어 — 흡수 때 적은 「펼친 판과 다름」(세션만 읽는다)."""
    return editor_open() and DIRTY.get()


def close_editor() -> None:
    """작성을 닫는다(「작성 닫기」 · 편집기 판 적용 뒤) — 네 표 초안 · 이력을 일부러 버리고(누름
    직전에 보낸 op 를 알림 없이 버림) 씨앗 · 칸 지도 · 표지를 지운다."""
    for keys in TABLE_KEYS.values():
        edit_grid.discard_table(keys, KEYS)
    for slot in (EDITOR, LINES, COLUMNS, FOLLOW, DIRTY, BASE_PACK):
        slot.clear()
    INBOX.clear()


def collect() -> None:
    """출납 콜백 — 새 op 를 inbox 에 쌓고(`edit_grid.collect_outbox`) 탭 점을 먼저 켠다(화면 탭
    줄은 페이지보다 먼저 그린다 — 흡수가 정확한 값으로 고친다)."""
    edit_grid.collect_outbox(HOST, KEYS)
    if INBOX.peek():
        DIRTY.set(True)


def _seeds() -> dict[str, LineFields]:
    found: dict[str, LineFields] = {}
    for line_id, values in LINES.get().items():
        if isinstance(line_id, str) and isinstance(values, tuple):
            found[line_id] = LineFields(*values)
    return found


def _set_seed(line_id: str, fields: LineFields) -> None:
    seeds = dict(LINES.get())
    seeds[line_id] = astuple(fields)
    LINES.set(seeds)


def _next_line_id(seeds: Mapping[str, LineFields]) -> str:
    numbers = [
        int(line_id[1:]) for line_id in seeds if line_id.startswith("n") and line_id[1:].isdigit()
    ]
    return f"n{max(numbers, default=0) + 1}"


# --------------------------------------------------------------------------- 진입 · 닫기


def render_entry(
    repository: DuckDBScenarioRepository,
    state: ExtraProcessState,
    hooks: Hooks,
    *,
    lock: str | None,
) -> None:
    """단추 줄의 「앱에서 작성」(닫혀 있을 때) 또는 「작성 닫기」(열려 있을 때). `lock` 은 그 회차의
    쓰기 잠금 까닭이다."""
    if editor_open():
        _render_close()
        return
    reason = lock or _entry_lock(repository, state)
    if st.button(
        OPEN_LABEL,
        key=OPEN_BUTTON_KEY,
        icon=":material/edit_note:",
        disabled=reason is not None,
        help=reason or OPEN_HELP,
    ):
        _open(repository, hooks)


def _render_close() -> None:
    if not DIRTY.get():
        if st.button(CLOSE_LABEL, key=CLOSE_BUTTON_KEY, icon=":material/close:", help=CLOSE_HELP):
            close_editor()
            st.rerun()
        return
    # 잃을 것이 있을 때만 한 번 묻는다(UI-STA-02 · UI-NTF-09).
    with st.popover(CLOSE_LABEL, icon=":material/close:", help=CLOSE_DIRTY_HELP):
        if st.button(CLOSE_CONFIRM_LABEL, key=CLOSE_CONFIRM_KEY, icon=":material/delete_sweep:"):
            close_editor()
            st.rerun()


def _opened_version(state: ExtraProcessState) -> ExtraProcessVersion | None:
    """펼칠 판 — 활성 판, 끈 동안은 마지막 내용 판. 판이 하나도 없으면 None(빈 판)."""
    return state.active or state.latest_content


def _entry_lock(repository: DuckDBScenarioRepository, state: ExtraProcessState) -> str | None:
    """진입을 잠그는 까닭(쓰기 잠금 밖) — 펼칠 판 내용을 못 읽음(G1) · 맥락을 못 셈."""
    opened = _opened_version(state)
    if opened is not None and not _readable(repository, opened):
        return UNREADABLE_REASON
    return _context_problem()


def _readable(repository: DuckDBScenarioRepository, version: ExtraProcessVersion) -> bool:
    """판 내용이 관문을 지나는가 — 판 sha 마다 한 번 읽는다."""
    sha = version.sha256
    if sha is None:
        return False
    seen = BASE_SEEN.get()
    if len(seen) == 2 and seen[0] == sha:
        return bool(seen[1])
    try:
        ok = read_pack_zip(repository.load_extra_process_content(sha)).pack is not None
    except BOOTSTRAP_ERRORS:
        return False
    BASE_SEEN.set((sha, ok))
    return ok


def _context_problem() -> str | None:
    try:
        tables = get_effective_reference_tables()
        get_effective_reference_version()
    except BOOTSTRAP_ERRORS as exc:
        return bootstrap_error_message(exc)
    plan = tables.get("RQ_PKG_PLAN")
    if plan is None or plan.get("생산계획년월") is None or plan["생산계획년월"].dropna().empty:
        return NO_PLAN_REASON
    return None


def _open(repository: DuckDBScenarioRepository, hooks: Hooks) -> None:
    """누른 회차에 다시 판정하고 판을 펼친다 — 펼친 때의 차례 · sha · 바이트를 고정한다."""
    reason = hooks.lock()
    opened_at: tuple[int, str | None, bytes | None] | None = None
    if reason is None:
        try:
            opened_at = _opened_bytes(repository)
            reason = _context_problem()
        except BOOTSTRAP_ERRORS as exc:
            reason = bootstrap_error_message(exc)
    if reason is not None or opened_at is None:
        queue_flash(FLASH_KEY, reason or UNREADABLE_REASON, kind="error", icon=":material/block:")
        st.rerun()
    close_editor()
    EDITOR.set(opened_at)
    KIND.set(next(iter(KINDS)))
    MEMO.set("")
    st.rerun()


def _opened_bytes(repository: DuckDBScenarioRepository) -> tuple[int, str | None, bytes | None]:
    """(판 이력 마지막 차례, 펼칠 판 sha, 그 바이트) — 판이 하나도 없으면 sha · 바이트가 None(빈
    판). 펼칠 판이 있는데 내용을 못 읽으면 ValueError(G1 — 빈 판으로 펴면 공정이 모두 빠진다)."""
    state = repository.load_extra_process_state()
    opened = _opened_version(state)
    if opened is None:
        return state.last_seq, None, None
    if opened.sha256 is None:
        raise ValueError(UNREADABLE_REASON)
    data = repository.load_extra_process_content(opened.sha256)
    if read_pack_zip(data).pack is None:
        raise ValueError(UNREADABLE_REASON)
    return state.last_seq, opened.sha256, data


def _base_pack(sha: object, data: object) -> ExtraProcessPack | None:
    """펼친 판 — 바이트를 sha 마다 한 번 읽는다."""
    if not isinstance(data, bytes):
        return None
    memo = BASE_PACK.get()
    if len(memo) == 2 and memo[0] == sha and isinstance(memo[1], ExtraProcessPack):
        return memo[1]
    pack = read_pack_zip(data).pack
    BASE_PACK.set((sha, pack))
    return pack


# --------------------------------------------------------------------------- 맥락


def _context(repository: DuckDBScenarioRepository) -> tuple[tuple[object, ...], EditorContext]:
    """(맥락 열쇠, 맥락) — (시나리오 id, 기준정보 판)마다 한 번 센다(UI-PRF-01 · 05). 옛 판 공정은
    그 시나리오 출처의 걷을 이름으로 뺀다(내장 시드 — 저장 시나리오 없음 — 이면 없음)."""
    scenario_id = active_persisted_scenario_id()
    key: tuple[object, ...] = (scenario_id, get_effective_reference_version())
    memo = CONTEXT.get()
    if len(memo) == 2 and memo[0] == key and isinstance(memo[1], EditorContext):
        return key, memo[1]
    tables = get_effective_reference_tables()
    excluded = (
        ()
        if scenario_id is None
        else split_previous(repository.load_scenario_extra_process(scenario_id)).stripped
    )
    context = editor_context(tables, excluded)
    CONTEXT.set((key, context))
    return key, context


def _follow(
    key: tuple[object, ...], reference: str, basis: str, start: int | None, end: int | None
) -> FollowPreview | None:
    """따라올 줄 미리보기(결정2 — 읽기 전용) — (맥락, 참조, 소요기준, 기간)마다 메모한다. 기간이
    없거나 표를 못 읽으면 None."""
    if start is None:
        return None
    memo_key = (key, reference, basis, start, end)
    memo = dict(FOLLOW.get())
    found = memo.get(memo_key)
    if isinstance(found, FollowPreview):
        return found
    try:
        preview = follow_preview(
            get_effective_reference_tables(), reference, basis, Period(start, end)
        )
    except BOOTSTRAP_ERRORS:
        return None
    memo[memo_key] = preview
    if len(memo) > _FOLLOW_MEMO_LIMIT:
        memo.pop(next(iter(memo)))
    FOLLOW.set(memo)
    return preview


# --------------------------------------------------------------------------- 표 짓기


@dataclass(frozen=True)
class _LineRow:
    """공정 표 한 줄 — 줄 id · 양식 값(씨앗 또는 펼친 값) · 통째 옮김 까닭."""

    line_id: str
    fields: LineFields
    carried: str | None


@dataclass(frozen=True)
class _Table:
    """그리드 표 하나 — 규격 · 양식 몫 · 지문."""

    spec: GridSpec
    base: EditGridBase
    base_key: str

    @property
    def slot(self) -> edit_grid.TableSlot:
        cells_key, history_key = TABLE_KEYS[self.spec.table]
        return edit_grid.TableSlot(self.base.index, self.spec, cells_key, history_key)


@dataclass(frozen=True)
class _Columns:
    """값 표 칸 — 이름 차례, 창 달 이름 → 달, 이전 · 이후 칸 이름(없으면 None)."""

    names: tuple[str, ...]
    months: Mapping[str, int]
    before: str | None
    after: str | None


@dataclass(frozen=True)
class _Screen:
    """이 회차의 편집기 — 모형 · 공정 표 줄 · 값 표 칸 · 표 넷(줄이 없으면 None) · 초안 칸의 모형
    열쇠 → 그리드 자리."""

    model: EditorModel
    rows: tuple[_LineRow, ...]
    columns: _Columns
    tables: Mapping[str, _Table | None]
    places: Mapping[CellKey, tuple[tuple[str, str, str], ...]]


def _line_rows(origin: EditorModel, seeds: Mapping[str, LineFields]) -> tuple[_LineRow, ...]:
    """펼친 줄(차례 그대로) 뒤에 새 줄(더한 차례)."""
    rows = [
        _LineRow(line.line_id, seeds.get(line.line_id, line.fields), line.carried)
        for line in origin.origin
    ]
    rows += [
        _LineRow(line_id, fields, None)
        for line_id, fields in seeds.items()
        if not line_id.startswith(BASE_LINE_PREFIX)
    ]
    return tuple(rows)


def _draft(table: str) -> DraftState | None:
    return edit_grid.draft_of(TABLE_KEYS[table][0])


def _area_index(value: object) -> float | None:
    text = "" if value is None else str(value).strip().casefold()
    for at, name in enumerate(AREA_NAMES):
        if name.casefold() == text:
            return float(at)
    return None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _text_or_none(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _field_value(name: str, raw: object) -> CellInput:
    """공정 표 초안 칸 → 모형 값(못 읽은 글은 글 그대로 — 관문 · 입력 문제가 거절한다)."""
    if name == "area" and isinstance(raw, float):
        at = int(raw)
        return AREA_NAMES[at] if 0 <= at < len(AREA_NAMES) else ""
    if name in ("name", "memo", "area"):
        return "" if raw is None else str(raw)
    if isinstance(raw, (int, float, str)) or raw is None:
        return raw
    return str(raw)


def _line_inputs(rows: Sequence[_LineRow]) -> list[tuple[str, LineFields]]:
    """공정 표의 전체 상태(양식 + 초안, 지운 줄 뺌) → `with_lines` 입력."""
    draft = _draft(LINE_TABLE)
    cells = {} if draft is None else draft["cells"]
    bad = {} if draft is None else draft["bad"]
    removed = set(removed_keys(draft))
    found: list[tuple[str, LineFields]] = []
    for row in rows:
        if row.line_id in removed:
            continue
        if row.carried is not None:
            found.append((row.line_id, row.fields))
            continue
        own = cells.get(row.line_id, {})
        wrong = bad.get(row.line_id, {})
        changes: dict[str, Any] = {}
        for column, name in _EDITABLE.items():
            if column in wrong:
                changes[name] = _field_value(name, wrong[column][0])
            elif column in own:
                changes[name] = _field_value(name, own[column])
        found.append((row.line_id, replace(row.fields, **changes)))
    return found


def _line_table(rows: Sequence[_LineRow]) -> _Table | None:
    if not rows:
        return None
    kinds: list[LockKind] = [LockKind(cols=PICKED_COLUMNS, reason=PICKED_WHY)]
    rules: list[int] = []
    records: list[dict[str, object]] = []
    for number, row in enumerate(rows, start=1):
        fields = row.fields
        if row.carried is None:
            rules.append(0)
        else:
            kind = LockKind(cols=LINE_COLUMNS, reason=CARRIED_WHY.format(reason=row.carried))
            if kind not in kinds:
                kinds.append(kind)
            rules.append(kinds.index(kind))
        records.append(
            {
                NO_COLUMN: str(number),
                ID_COLUMN: row.line_id,
                LABEL_COLUMN: _text_or_none(fields.name) or row.line_id,
                NAME_COLUMN: _text_or_none(fields.name),
                AREA_COLUMN: _area_index(fields.area),
                BASIS_COLUMN: _text_or_none(fields.basis),
                MODULES_COLUMN: _number(fields.modules),
                REFERENCE_COLUMN: _text_or_none(fields.reference),
                STEP_COLUMN: _text_or_none(fields.step),
                MCP_COLUMN: _text_or_none(fields.mcp),
                START_COLUMN: _text_or_none(fields.start),
                END_COLUMN: _text_or_none(fields.end),
                MEMO_COLUMN: _text_or_none(fields.memo),
                CARRY_COLUMN: row.carried,
            }
        )
    frame = pd.DataFrame(records, columns=[NO_COLUMN, ID_COLUMN, LABEL_COLUMN, *LINE_COLUMNS])
    return _built(frame, LINE_SPEC, RowRules(tuple(kinds), tuple(rules)))


def _built(frame: pd.DataFrame, spec: GridSpec, rules: RowRules) -> _Table:
    base = build_base(frame, spec, None, rules)
    digest = hashlib.sha1(
        json.dumps(base.body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return _Table(spec, base, f"{spec.table}:{digest}")


def _next_month(month: int) -> int:
    return month + 1 if month % 100 < 12 else (month // 100 + 1) * 100 + 1


def _previous_month(month: int) -> int:
    return month - 1 if month % 100 > 1 else (month // 100 - 1) * 100 + 12


def _columns(span: Sequence[int], views: Mapping[str, LineView]) -> _Columns:
    """값 표 칸 — 이전 칸은 어느 줄이 계획 첫 달 앞에서 시작할 때만, 이후 칸은 어느 줄이 계획 끝
    달 뒤로 이어질 때만 선다(UI-TXT-08). 이름은 칸 지도(`COLUMNS`)에 더해 둔다."""
    months = {month_label(month): month for month in span}
    before = after = None
    roles: dict[str, tuple[str, int]] = {name: ("m", month) for name, month in months.items()}
    if span and any(view.axis is not None and view.axis.before for view in views.values()):
        edge = _previous_month(span[0])
        before = f"~{month_label(edge)}"
        roles[before] = ("before", edge)
    if span and any(view.axis is not None and view.axis.after for view in views.values()):
        edge = _next_month(span[-1])
        after = f"{month_label(edge)}~"
        roles[after] = ("after", edge)
    known = COLUMNS.get()
    if any(known.get(name) != role for name, role in roles.items()):
        COLUMNS.set({**known, **roles})
    names = tuple(name for name in (before, *months, after) if name is not None)
    return _Columns(names, months, before, after)


def _row_id(row: RowKey) -> str:
    return "|".join(row)


def _row_key(row_id: str) -> RowKey | None:
    parts = row_id.split("|")
    return (parts[0], parts[1], parts[2], parts[3]) if len(parts) == 4 else None


def _row_label(row: RowKey) -> str:
    table, mass_class, column = row[1], row[2], row[3]
    return ROW_LABELS.get(
        (table, mass_class, column),
        ROW_LABELS.get((table, column if table == EQUIPMENT else mass_class), column),
    )


def _value_table(
    table: str, model: EditorModel, views: Mapping[str, LineView], columns: _Columns
) -> _Table | None:
    """값 표 하나 — 살아 있는 편집기 몫 줄마다 그 파일의 값 줄. 칸 값은 양식(`CellView.default`)이고
    잠긴 칸의 까닭은 줄마다 한 글로 잇는다."""
    file = VALUE_TABLES[table]
    kinds: list[LockKind] = []
    rules: list[int] = []
    records: list[dict[str, object]] = []
    for line in model.lines:
        if line.carried is not None:
            continue
        view = views.get(line.line_id)
        name = _text_or_none(line.fields.name) or line.line_id
        for row in value_rows(line.line_id):
            if row[1] != file:
                continue
            values, locked, why = _row_cells(row, view, columns)
            label = _row_label(row)
            records.append(
                {
                    "공정": name,
                    "구분": label,
                    ID_COLUMN: _row_id(row),
                    LABEL_COLUMN: f"{name} · {label}",
                    **values,
                }
            )
            if not locked:
                rules.append(-1)
                continue
            kind = LockKind(cols=tuple(locked), reason=" · ".join(why))
            if kind not in kinds:
                kinds.append(kind)
            rules.append(kinds.index(kind))
    if not records:
        return None
    spec = GridSpec(
        table=table,
        title=VALUE_TITLES[table],
        key_columns=VALUE_KEY_COLUMNS,
        value_columns=columns.names,
        fmt=VALUE_FORMATS[table],
        value_help=VALUE_HELPS[table],
        id_column=ID_COLUMN,
        label_column=LABEL_COLUMN,
    )
    frame = pd.DataFrame(
        records, columns=[*VALUE_KEY_COLUMNS, ID_COLUMN, LABEL_COLUMN, *columns.names]
    )
    return _built(frame, spec, RowRules(tuple(kinds), tuple(rules)))


def _row_cells(
    row: RowKey, view: LineView | None, columns: _Columns
) -> tuple[dict[str, object], list[str], list[str]]:
    """값 줄 하나의 (칸 → 양식 값, 잠긴 칸, 잠긴 까닭)."""
    values: dict[str, object] = dict.fromkeys(columns.names)
    if view is None or view.axis is None:
        return values, list(columns.names), [NO_PERIOD_WHY]
    locked: list[str] = []
    why: list[str] = []

    def lock(name: str, reason: str) -> None:
        locked.append(name)
        if reason not in why:
            why.append(reason)

    if columns.before is not None:
        cell = view.before.get(row)
        if cell is not None and not cell.multiple:
            values[columns.before] = _shown(cell.value)
        lock(columns.before, MULTIPLE_WHY if cell is not None and cell.multiple else BEFORE_WHY)
    shown_months = view.months.get(row, {})
    for name, month in columns.months.items():
        cell = shown_months.get(month)
        if cell is None:
            lock(name, OUTSIDE_WHY)
        else:
            values[name] = _shown(cell.default)
    if columns.after is not None:
        cell = view.after.get(row)
        if cell is None:
            lock(columns.after, OUTSIDE_WHY)
        elif cell.editable:
            values[columns.after] = _shown(cell.default)
        else:
            if not cell.multiple:
                values[columns.after] = _shown(cell.value)
            lock(columns.after, MULTIPLE_WHY)
    return values, locked, why


def _shown(value: CellInput) -> object:
    """양식 칸 값 — 수만 싣는다(글 입력은 양식이 아니라 초안에 산다)."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _value_inputs(
    model: EditorModel,
) -> tuple[dict[CellKey, CellInput], dict[CellKey, tuple[tuple[str, str, str], ...]]]:
    """값 표 셋의 초안 전체 → 모형 칸 입력과 그 칸의 그리드 자리(표, 줄 업무 키, 칸 이름). 이후
    칸은 칸 이름의 달과 줄 시작월 가운데 늦은 달의 `Onward` 다(`month_axis` 의 이후 시작과 같음).
    이전 칸 · 지도에 없는 칸은 열쇠가 없다."""
    roles = COLUMNS.get()
    starts = {line.line_id: line.fields.start for line in model.lines}
    cells: dict[CellKey, CellInput] = {}
    places: dict[CellKey, list[tuple[str, str, str]]] = {}
    for table in VALUE_TABLES:
        draft = _draft(table)
        if draft is None:
            continue
        for book, wrong in ((draft["cells"], False), (draft["bad"], True)):
            for row_id, row_cells in book.items():
                row = _row_key(str(row_id))
                if row is None:
                    continue
                for column, raw in row_cells.items():
                    role = roles.get(column)
                    if not isinstance(role, tuple) or len(role) != 2 or role[0] == "before":
                        continue
                    month = int(role[1])
                    key: CellKey
                    if role[0] == "after":
                        start = _month_of(starts.get(row[0]))
                        key = (row, Onward(max(month, start) if start is not None else month))
                    else:
                        key = (row, month)
                    value = raw[0] if wrong and isinstance(raw, tuple) else raw
                    cells[key] = value if isinstance(value, (float, int, str)) else None
                    places.setdefault(key, []).append((table, str(row_id), str(column)))
    return cells, {key: tuple(found) for key, found in places.items()}


def _month_of(value: object) -> int | None:
    text = "" if value is None else str(value).strip()
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    return int(text) if len(text) == 6 and text.isdigit() else None


def _screen(base: ExtraProcessPack | None, context: EditorContext) -> _Screen:
    """초안 전체에서 모형 · 표 넷을 다시 짓는다(병합 아님)."""
    origin = model_from_pack(base)
    rows = _line_rows(origin, _seeds())
    model = with_lines(origin, _line_inputs(rows))
    cells, places = _value_inputs(model)
    model = with_cells(model, cells)
    views = month_view(model, context.months)
    columns = _columns(plan_span(context.months), views)
    tables: dict[str, _Table | None] = {LINE_TABLE: _line_table(rows)}
    for table in VALUE_TABLES:
        tables[table] = _value_table(table, model, views, columns)
    return _Screen(model, rows, columns, tables, places)


def _prune(screen: _Screen) -> bool:
    """걷은 칸(`redundant_cells`)을 초안에서 지운다(계약 5) — 지웠으면 참."""
    targets: dict[str, dict[str, set[str]]] = {}
    for key in redundant_cells(screen.model):
        for table, row_id, column in screen.places.get(key, ()):
            targets.setdefault(table, {}).setdefault(row_id, set()).add(column)
    changed = False
    for table, rows in targets.items():
        draft = _draft(table)
        if draft is None:
            continue
        books: dict[str, dict[str, dict[str, Any]]] = {}
        for name in ("cells", "bad"):
            book: dict[str, dict[str, Any]] = {}
            for row_id, row_cells in draft[name].items():
                kept = {
                    column: value
                    for column, value in row_cells.items()
                    if column not in rows.get(row_id, set())
                }
                changed = changed or len(kept) != len(row_cells)
                if kept:
                    book[row_id] = kept
            books[name] = book
        slot = SessionSlot(TABLE_KEYS[table][0], dict)
        if books["cells"] or books["bad"]:
            slot.set(books)
        else:
            slot.clear()
    return changed


def _absorb(base: ExtraProcessPack | None, context: EditorContext) -> _Screen:
    """inbox 를 반영하고(앞 회차 양식 — 브라우저가 본 표 — 로) 모형을 다시 짓고 걷은 칸을 지운 뒤
    탭 점 표지를 적는다."""
    if INBOX.peek():
        before = _screen(base, context)
        slots = {table: built.slot for table, built in before.tables.items() if built is not None}
        edit_grid.apply_inbox(KEYS, slots)
    screen = _screen(base, context)
    if _prune(screen):
        screen = _screen(base, context)
    model = screen.model
    DIRTY.set(bool(effective_edits(model)) or model.lines != model.origin)
    return screen


# --------------------------------------------------------------------------- 그리기


def render_editor(repository: DuckDBScenarioRepository, hooks: Hooks, *, lock: str | None) -> None:
    """작성 중일 때만 그린다 — 작업 줄 → 그리드 → 판 줄(늘 같은 칸). 맥락을 못 세면 그 자리에
    「데이터 Error」 마크(UI-NTF-08)이고 초안은 남는다."""
    opened = EDITOR.peek()
    if opened is None or len(opened) != 3:
        return
    seen_seq, base_sha, data = opened
    base = _base_pack(base_sha, data)
    try:
        key, context = _context(repository)
        if not context.months:
            raise ValueError(NO_PLAN_REASON)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            bootstrap_error_message(exc),
            code="AD-07",
            tab=tab_name(TAB_LABEL),
            text="부대공정 작성에 쓸 시나리오를 읽지 못했습니다",
        )
        return
    screen = _absorb(base, context)
    actions = st.container(key=ACTIONS_BOX)
    grid_box = st.container(key=GRID_BOX)
    make_box = st.container(key=MAKE_BOX)
    with actions:
        kind = _render_actions(screen, key, context)
    with grid_box:
        _render_grid(screen, kind)
    with make_box:
        pressed = _render_make_row(screen, context, lock)
    if pressed:
        _make(repository, base, context, hooks, seen_seq=int(seen_seq), base_sha=base_sha)


def _render_actions(screen: _Screen, key: tuple[object, ...], context: EditorContext) -> str:
    """작업 줄 — 종류 단추와 「공정 더하기 · 참조 바꾸기」(둘 다 늘 선다)."""
    with st.container(key=ACTION_ROW, horizontal=True, vertical_alignment="center", gap="small"):
        if KIND.peek() not in KINDS:
            KIND.set(next(iter(KINDS)))
        chosen = st.segmented_control(
            "부대공정 표 종류",
            list(KINDS),
            key=KIND_KEY,
            required=True,
            persist_state="session",
            label_visibility="collapsed",
        )
        with st.popover(ADD_MENU_LABEL, icon=":material/add:", help=ADD_HELP, key=ADD_MENU_KEY):
            _render_line_form(screen, key, context)
    return chosen if isinstance(chosen, str) and chosen in KINDS else next(iter(KINDS))


def _render_grid(screen: _Screen, kind: str) -> None:
    table = KINDS[kind]
    built = screen.tables.get(table)
    if built is None:
        shell = edit_grid.shell_data(HOST, None, None, base_key="", changes_label=CHANGES_LABEL)
        shell["texts"] = {**shell["texts"], "empty": "공정 없음"}
        feed = edit_grid.feed_data(HOST, None, KEYS, base_key="")
    else:
        shell = edit_grid.shell_data(
            HOST, built.base, built.spec, base_key=built.base_key, changes_label=CHANGES_LABEL
        )
        feed = edit_grid.feed_data(HOST, built.slot, KEYS, base_key=built.base_key)
    # 표 없는 껍데기는 높이가 없어 끌어올리면 판 줄이 작업 줄을 덮는다 — 표가 있을 때만 한 줄로.
    style = "" if built is None else ONE_LINE_STYLE
    edit_grid.render_edit_grid(HOST, shell, feed, on_outbox=collect, page_style=style, rows=True)


def _render_make_row(screen: _Screen, context: EditorContext, lock: str | None) -> bool:
    """판 줄 — 00 메모 · 「판 만들기」(쓰기 잠금으로만 잠근다 — 고친 것 없는 누름도 누른 회차에
    판정) · 「확인할 칸 n」(입력 문제 + 기준 데이터 알림 — 막지 않는다, G6)."""
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.text_input(
            MEMO_LABEL,
            key=MEMO_KEY,
            persist_state="session",
            max_chars=200,
            placeholder=MEMO_LABEL,
            label_visibility="collapsed",
            width=320,
        )
        pressed = st.button(
            MAKE_LABEL,
            key=MAKE_BUTTON_KEY,
            icon=":material/note_add:",
            disabled=lock is not None,
            help=lock or MAKE_HELP,
        )
        frame = check_frame(screen.model, context)
        if not frame.empty:
            with st.popover(
                CHECK_LABEL.format(n=f"{len(frame):,}"), icon=":material/error:", key=CHECK_MENU_KEY
            ):
                st.dataframe(frame, hide_index=True, width="stretch", placeholder="")
    return bool(pressed) and lock is None


def check_frame(model: EditorModel, context: EditorContext) -> pd.DataFrame:
    """「확인할 칸 n」 의 내역 — 관문이 거절할 입력(`input_problems`)과 관문은 받지만 등록 때
    빠지거나 잘릴 것(`editor_warnings`)."""
    names = {line.line_id: _text_or_none(line.fields.name) or line.line_id for line in model.lines}
    rows: list[dict[str, str]] = []
    for problem in input_problems(model):
        rows.append(
            {
                "공정": "" if problem.line_id is None else names.get(problem.line_id, ""),
                "표": TABLE_WORDS.get(problem.table, problem.table),
                "칸": _problem_column(problem),
                "달": _months_text(problem.months),
                "까닭": problem.reason,
            }
        )
    for warning in editor_warnings(model, context):
        rows.append(
            {
                "공정": "" if warning.line_id is None else names.get(warning.line_id, ""),
                "표": warning.code,
                "칸": "",
                "달": "",
                "까닭": warning.text,
            }
        )
    return pd.DataFrame(rows, columns=list(CHECK_COLUMNS))


def _problem_column(problem: InputProblem) -> str:
    if problem.row is None:
        return problem.column
    return _row_label(problem.row)


def _months_text(months: Sequence[int]) -> str:
    if not months:
        return ""
    if len(months) == 1:
        return month_label(months[0])
    return f"{month_label(months[0])} ~ {month_label(months[-1])} ({len(months)}달)"


# ------------------------------------------------------------------- 공정 더하기 · 참조 바꾸기


def _render_line_form(screen: _Screen, key: tuple[object, ...], context: EditorContext) -> None:
    """팝오버 꼴 — 줄 · (새 줄이면 공정 이름) · 참조공정 · STEP · MCP 조합, 따라올 줄 미리보기,
    「더하기」 · 「바꾸기」. 값은 누른 회차에만 씨앗에 든다."""
    model = screen.model
    editable = [line for line in model.lines if line.carried is None]
    names = {line.line_id: _text_or_none(line.fields.name) or line.line_id for line in editable}
    target = st.selectbox(
        "줄",
        [NEW_LINE, *names],
        format_func=lambda value: names.get(value, value),
        key=LINE_PICK_KEY,
    )
    line = model.line(target) if target != NEW_LINE else None
    fields = line.fields if line is not None else LineFields()
    # 칸 key 꼬리 — 새 줄은 더할 줄 id 라 더한 뒤에는 빈 칸으로 다시 선다(`form_key`).
    form = form_key(target)
    name = ""
    if line is None:
        name = st.text_input(NAME_COLUMN, key=f"{NAME_INPUT_KEY}-{form}", max_chars=100)
    choices = reference_choices(context, model, basis=None if line is None else fields.basis)
    options = [choice.name for choice in choices]
    current = _text_or_none(fields.reference)
    if current is not None and current not in options:
        options.append(current)
    labels = get_process_labels()

    def shown(value: str) -> str:
        label = labels.label(value)
        return value if label == value else f"{label} ({value})"

    reference = st.selectbox(
        REFERENCE_COLUMN,
        options,
        index=options.index(current) if current in options else None,
        format_func=shown,
        key=f"{REFERENCE_PICK_KEY}-{form}",
        placeholder=REFERENCE_COLUMN,
    )
    choice = next((item for item in choices if item.name == reference), None)
    steps = [f"{step} · {mcp}" for step, mcp in (choice.steps if choice is not None else ())]
    present = f"{fields.step} · {fields.mcp}" if _text_or_none(fields.step) and fields.mcp else None
    if present is not None and reference == current and present not in steps:
        steps.append(present)
    step_index = steps.index(present) if present in steps else (0 if steps else None)
    step_text = st.selectbox(
        "STEP · MCP",
        steps,
        index=step_index,
        key=f"{STEP_PICK_KEY}-{form}-{reference}",
        accept_new_options=True,
        help=STEP_HELP,
        placeholder="STEP · MCP",
    )
    if choice is not None:
        start = _month_of(fields.start) or (context.months[0] if context.months else None)
        preview = _follow(key, choice.name, choice.basis, start, _month_of(fields.end))
        if preview is not None:
            st.caption(
                f"따라올 제품 {preview.products:,} · 줄 {preview.rows:,} · Buffer 밖 "
                f"{preview.uncounted:,}"
            )
    pressed = st.button(
        ADD_LABEL if line is None else CHANGE_LABEL,
        key=LINE_BUTTON_KEY,
        type="primary",
        icon=":material/add:" if line is None else ":material/swap_horiz:",
    )
    if pressed:
        # 있는 줄은 양식(씨앗 또는 펼친 값 — 그리드 초안을 뺀 값)에서 바꾼다. 모형 값(초안 포함)을
        # 씨앗에 구우면 그 칸의 그리드 되돌리기가 먹지 않는다.
        template = next((row.fields for row in screen.rows if row.line_id == target), None)
        _apply_line_form(target, template, name, reference, step_text, context)


def form_key(target: str) -> str:
    """「공정 더하기 · 참조 바꾸기」 칸 key 의 꼬리 — 있는 줄은 그 줄 id, 새 공정은 다음에 더할 줄
    id(더하고 나면 바뀌어 이름 · 참조 칸이 비어 다시 선다)."""
    return _next_line_id(_seeds()) if target == NEW_LINE else target


def _split_step(text: object) -> tuple[str, str] | None:
    """「STEP · MCP」(또는 / · , · 빈칸으로 가른) 글 → (STEP_SEQ, MCP_SEQ)."""
    if not isinstance(text, str):
        return None
    for separator in ("·", "/", ",", " "):
        if separator in text:
            left, _, right = text.partition(separator)
            step, mcp = left.strip(), right.strip()
            return (step, mcp) if step and mcp else None
    return None


def _apply_line_form(
    target: str,
    template: LineFields | None,
    name: str,
    reference: object,
    step_text: object,
    context: EditorContext,
) -> None:
    """「더하기」 · 「바꾸기」 누름 — 새 줄이면 그때의 기본값(`line_defaults`)을 씨앗으로 고정하고,
    있는 줄이면 그 줄 양식의 참조공정 · 소요기준 · STEP · MCP 를 바꾼다(새 줄은 Area · 모듈수
    기본값도)."""
    if not isinstance(reference, str) or not reference.strip():
        queue_flash(FLASH_KEY, NO_REFERENCE, kind="error", icon=":material/block:")
        st.rerun()
    assert isinstance(reference, str)
    step = _split_step(step_text)
    if step is None:
        queue_flash(FLASH_KEY, BAD_STEP, kind="error", icon=":material/block:")
        st.rerun()
    assert step is not None
    seeds = _seeds()
    defaults = line_defaults(context, reference)
    if template is None:
        line_id = _next_line_id(seeds)
        fields = replace(defaults, name=name.strip(), step=step[0], mcp=step[1])
    else:
        line_id = target
        base = template
        picked = replace(
            base,
            reference=defaults.reference,
            basis=defaults.basis or base.basis,
            step=step[0],
            mcp=step[1],
        )
        if not target.startswith(BASE_LINE_PREFIX):
            picked = replace(
                picked,
                area=defaults.area or picked.area,
                modules=defaults.modules if defaults.modules is not None else picked.modules,
            )
        fields = picked
    _set_seed(line_id, fields)
    st.rerun()


# --------------------------------------------------------------------------- 판 만들기


def _make(
    repository: DuckDBScenarioRepository,
    base: ExtraProcessPack | None,
    context: EditorContext,
    hooks: Hooks,
    *,
    seen_seq: int,
    base_sha: object,
) -> None:
    """「판 만들기」 누름 — 출납을 다시 모아 흡수한 뒤(G2) 판 번호 · 작성시각 · 작성자를 한 번
    고정해 판을 짓고 받은 판 자리에 둔다(쓰지 않는다)."""
    reason = hooks.lock()
    if reason is not None:
        queue_flash(FLASH_KEY, reason, kind="error", icon=":material/block:")
        st.rerun()
    collect()
    model = _absorb(base, context).model
    now = datetime.now(KST)
    try:
        state = repository.load_extra_process_state()
        latest = state.latest_content
        version_no = (0 if latest is None else latest.version_no or 0) + 1
        identity = sso_identity.verified_identity()
        author = "" if identity is None else identity.name or ""
        info = PackInfo(
            FORMAT_VERSION,
            version_no,
            now.isoformat(timespec="seconds"),
            author,
            MEMO.peek() or "",
        )
        folded = fold(model, info)
        built = canonical_pack(folded.rows)
        pack = built.reading.pack
        if pack is not None and same_body(pack, model.base):
            hooks.discard()
            queue_flash(FLASH_KEY, UNCHANGED_EDITOR, kind="info")
            st.rerun()
        earlier = previous_content(state)
        before = (
            None
            if earlier is None or earlier.sha256 is None
            else read_pack_zip(repository.load_extra_process_content(earlier.sha256)).pack
        )
    except BOOTSTRAP_ERRORS as exc:
        queue_flash(FLASH_KEY, bootstrap_error_message(exc), kind="error", icon=":material/error:")
        st.rerun()
    origin = EditorOrigin(
        seen_seq,
        base_sha if isinstance(base_sha, str) else None,
        folded,
        ignored=len(ignored_cells(model)),
    )
    staged = stage_editor_pack(built, origin, now=now, base=model.base, before=before)
    if pack is not None and state.last_seq != seen_seq:
        staged = replace(staged, judgement=PackJudgement(MOVED_VERDICT, MOVED_REASON))
    hooks.place(staged)
    st.rerun()
