# Purpose: Admin 「부대공정」 탭의 앱 작성 편집기 — 공정 · 생산성 · 설비 · 효율 표를 범용 그리드
# 한 마운트(종류 단추)로 그리고, 참조공정 · STEP · MCP 후보 · 「따라올 제품」 미리보기와 판
# 만들기(받은 판 자리에 싣기)를 맡는다.

"""Admin 「부대공정」 — 판을 앱에서 쓰는 셋째 길(CSV · S3 Drive 가져오기 · 「새 판으로」 곁).

**정본은 그리드 초안이다**(순수 몸통 `services/extra_process_editor.py` 의 화면 계약 1 ~ 10).
회차마다 펼친 판(`EDITOR` — 펼친 때의 판 이력 차례 · sha · 바이트)에서 모형을 다시 짓는다 —
`with_cells(with_lines(model_from_pack(바탕), 줄 그리드 전체), 값 그리드 전체)`. 병합이 아니라 전체
상태라 그리드 되돌리기 · 「적용 전」 서랍이 그대로 먹는다. 정본 칸(펼친 판 · 칸 이름 지도 · 그리드
초안)은 기본형이고, 메모 칸(맥락 · 미리보기 · 펼친 판 읽기)은 꼴 검사로 다시 짓는다. 흡수할 때마다
초안을 이 회차 표에 맞춘다 — 빈칸 초안만 남은 새 줄은 지우고(`_clear_blank_fresh`), 값 표의 걷은
칸(`redundant_cells`)은 그리드에 보이지 않을 때만 지우고(`_tidy` — 남기면 다른 창의 이후 칸처럼
숨은 옛 입력이 되살아난다 — 보이는 칸은 사람이 지금 보고 적은 값이라 남긴다), 이 회차 이후 칸과
같은 열쇠의 초안은 그 칸(여러 값이면 숨은 짝)으로 옮긴다. `ignored_cells` 는 지우지 않는다(경로가
넓어지면 산다). 그리드 이력은 건드리지 않는다.

- **표 넷 · 마운트 하나**(UI-LAY-07) — 종류 단추 「공정 · 생산성 · 설비 · 효율」. 형식이 칸마다라
  값 표를 판 파일(03 · 04 · 05)마다 나눈다. 공정 표는 줄 규칙 표(지우기 · 되살리기)이고, 통째 옮김
  줄은 지우기만 열린다. 펼친 줄 뒤에 빈 새 줄(`n<k>` — 채운 새 줄 뒤로 늘 `FRESH_ROWS` 개)이 서고,
  새 공정은 새 줄에 바로 적는다. 한 칸이라도 적은 새 줄이 편집기 줄이다(반쯤 찬 줄도 — 빈칸은
  입력 문제). 값 표 줄은 살아 있는 편집기 몫 줄에서 짓는다 — 공정을 지우면 값 줄이 함께 빠진다
  (지운 새 줄의 값 표 초안은 남아 「판에 안 든 칸 입력」 이고 되돌리기가 값째 되살린다). 값 표
  초안이 남은 새 줄 번호는 빈 새 줄로 다시 내놓지 않는다(`held` — 그 줄에 다른 공정을 적으면 지운
  공정 값이 표지 없이 붙는다). op 는 건너뛴 줄을 잠가 더한 색인으로 받는다(`_line_slot`).
- **월 칸** = [이전(읽기 전용)] + 계획 첫 달 ~ 끝 달(`YY.MM`) + [이후(한 값이면 고침)]. 칸 이름이
  머리 글이라 이전 · 이후 칸 이름에 그 달을 싣는다(「~26.12」 · 「27.07~」) — 이후 칸은 절대
  `Onward` 열쇠라 시나리오가 바뀌어도 옛 이후 칸 초안이 숨은 칸으로 남는다. 칸 이름 → 달은 세션
  지도(`COLUMNS`)가 기억한다. 양식은 `CellView.default`, 잠금은 `not editable`(까닭은 줄마다 한 글).
  「여러 값」 으로 잠긴 이후 칸의 초안은 숨은 짝 칸(`hidden_after`)에 두어 잠긴 칸에 그리지 않는다.
- **참조공정 · STEP · MCP** — 그리드 「글 + 후보」 칸(값은 글 그대로라 시나리오가 바뀌어도 · 목록
  밖 글도 칸에 남는다 — 판정은 입력 문제 · 관문). 참조공정 후보는 `reference_choices`(「표시명
  (원본)」 을 보이고 원본을 넣음 — UI-DAT-10), STEP · MCP 후보는 그 줄 참조공정 글로 고르는 조합
  표(「STEP · MCP」 를 보이고 제 칸 몫을 넣음). Area 는 그리드 고르기, 소요기준은 참조공정을 따라
  잠근다. 줄의 양식(`line_form`)이 그 줄의 지금 참조공정 글을 따른다 — 참조가 바뀐 줄의 STEP ·
  MCP(조합이 하나일 때만) · 새 줄 기본값은 양식이고 초안에 쓰지 않아(사람이 친 칸이 이김) 참조를
  되돌리면 양식도 돌아온다.
- **자리 차례**(늘 같은 칸 — 그리드 앞에 조건부 형제를 두지 않는다): 표 위 작업 줄(종류 ·
  「따라올 제품」 팝오버 — 공정마다 참조공정 · 조합 · 따라올 제품 표 · 「판 만들기」 팝오버 — 00
  메모 · 「만들기」, UI-LAY-03) → 그리드 → 표 아래 「확인할 칸 n」(있을 때만). 받은 판 상자는 그
  뒤(`extra_process_admin`).
- **판 만들기**(누른 회차) — 출납을 다시 모아 반영 · 흡수한 뒤(G2) 판 번호(마지막 내용 판 + 1) ·
  작성시각(KST 초) · 작성자(통합인증 이름, 없으면 빈칸)를 한 번 고정해 `fold` → `canonical` 로
  짓는다. 00 고정 본문이 펼친 판과 같으면 받은 판을 두지 않고 「바뀐 것 없음」, 펼친 뒤 판
  이력이 움직였으면 적용할 수 없는 판으로 싣는다. 입력 문제는 막지 않는다(관문이 정본 — 표지
  「확인할 칸 n」). 판에는 만든 때의 지문(`_stamp` — 줄 · 걷은 뒤 남은 고침 · 00 메모)을 싣고, 그 뒤
  표가 바뀌면 다음 흡수가 그 판을 걷는다(`_drop_stale` — 「새 판 적용」 이 옛 판을 넣고 작성을 닫아
  그 뒤 고친 것을 버리지 않게).
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
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final

import pandas as pd
import streamlit as st

from capa_simulation.components import edit_grid, sso_identity
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.saved_note import field_placeholder
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
    ROW_REMOVED,
    DraftState,
    GridSpec,
    LockKind,
    RowRules,
    Suggestion,
    Suggestions,
    ValueFormat,
    build_index,
    removed_keys,
)
from capa_simulation.services.edit_grid_payload import EditGridBase, build_base
from capa_simulation.services.extra_process_editor import (
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
    line_form,
    model_from_pack,
    month_view,
    plan_span,
    redundant_cells,
    reference_choice,
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
CLOSE_MENU_KEY: Final = "admin_extra_editor_close_menu"
CLOSE_CONFIRM_KEY: Final = "admin_extra_editor_close_confirm"
MAKE_MENU_KEY: Final = "admin_extra_editor_make_menu"
MAKE_BUTTON_KEY: Final = "admin_extra_editor_make"
KIND_KEY: Final = "admin_extra_editor_kind"
MEMO_KEY: Final = "admin_extra_editor_memo"
FOLLOW_MENU_KEY: Final = "admin_extra_editor_follow_menu"
CHECK_MENU_KEY: Final = "admin_extra_editor_check_menu"
ACTIONS_BOX: Final = "admin_extra_editor_actions"
ACTION_ROW: Final = "admin_extra_editor_action_row"
GRID_BOX: Final = "admin_extra_editor_grid_box"
MAKE_BOX: Final = "admin_extra_editor_make_box"

EDITOR_KEY: Final = "admin_extra_editor"
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
MAKE_BUTTON_LABEL: Final = "만들기"
FOLLOW_LABEL: Final = "따라올 제품"
MEMO_LABEL: Final = "판 메모"
CHANGES_LABEL: Final = "적용 전 변경"
OPEN_HELP: Final = (
    "활성 판(끈 동안은 마지막 판, 판이 없으면 빈 판)을 펼쳐 표로 고칩니다 — 「판 만들기」 · "
    "「새 판 적용」 을 눌러야 바뀝니다."
)
CLOSE_HELP: Final = "작성을 닫습니다."
CLOSE_DIRTY_HELP: Final = "고친 것과 이 표로 만든 판을 버리고 작성을 닫습니다."
MAKE_HELP: Final = (
    "고친 표로 다음 판을 만들어 받은 판 자리에 둡니다(받아 둔 판을 바꿈) — 판은 통째로 바뀌어 "
    "지운 공정은 빠지고, 「새 판 적용」 을 눌러야 들어갑니다."
)
FOLLOW_HELP: Final = (
    "공정마다 참조공정 · STEP · MCP 와 그 참조공정을 따라올 제품 · 줄 · Buffer 밖(따라와도 셈에 "
    "들지 않는 PKG 줄) 수입니다 — 읽기 전용."
)
NO_PLAN_REASON: Final = "올라와 있는 시나리오에 계획 월이 없습니다"
UNREADABLE_REASON: Final = "부대공정 판 내용을 읽지 못해 펼칠 수 없습니다"
UNCHANGED_EDITOR: Final = "바뀐 것 없음 — 펼친 판과 같은 판입니다"
UNCHANGED_CLEARED: Final = f"{UNCHANGED_EDITOR}(받아 둔 판을 비움)"
# 「만들기」 결과 알림 — 받은 판 상자 머리(「앱에서 만든 판 · 새 판 n」)와 같은 낱말.
MADE_PACK: Final = "앱에서 만든 판 · 새 판 {n}"
MADE_REJECTED: Final = "앱에서 만든 판 · 거절 {n}"
MADE_MOVED: Final = "앱에서 만든 판 · 새 판 {n} — 적용할 수 없음"
MOVED_VERDICT: Final = "moved"
MOVED_REASON: Final = (
    "펼친 뒤 다른 판이 들어와 적용할 수 없습니다 — 「작성 닫기」 뒤 다시 펼쳐 고칩니다"
)
STALE_STAGED: Final = (
    "판을 만든 뒤 표가 바뀌어 받은 판을 걷었습니다 — 「판 만들기」 를 다시 누릅니다"
)
# 탭 점 풍선(`page_tabs.page_unsaved_marks`).
UNSAVED_NOTE: Final = "적용하지 않은 부대공정 작성"
CHECK_LABEL: Final = "확인할 칸 {n}"
# 「까닭」 을 앞에 — 좁은 팝오버에서도 먼저 보이게(표 폭은 `CHECK_WIDTH`).
CHECK_COLUMNS: Final = ("공정", "까닭", "표", "칸", "달")
CHECK_WIDTH: Final = 640
# 후보 밖 참조 글이 후보의 표시명일 때 R-02 까닭 끝(`_labelled_source`).
LABEL_HINT: Final = " · 표시명 — 원본은 「{name}」"
# 기준 데이터 알림 코드 → 그 알림이 짚는 표(「표」 칸에는 표 이름만 — 등록 규칙 코드는 「까닭」
# 앞머리).
WARNING_TABLES: Final = {
    "R-01": "공정",
    "R-02": "공정",
    "조합": "공정",
    "끝월": "공정",
    "창": "공정",
    "효율": "효율",
}
# 「따라올 제품」 팝오버 표 — 편집기 몫 줄마다(통째 옮김 줄은 판 그대로라 뺀다). 줄이 없으면 빈
# 상태 한 마디(`EMPTY_LINES`).
FOLLOW_COLUMNS: Final = ("공정", "참조공정", "STEP · MCP", "따라올 제품", "줄", "Buffer 밖")
FOLLOW_COUNTS: Final = FOLLOW_COLUMNS[3:]
FOLLOW_WIDTH: Final = 640
EMPTY_LINES: Final = "공정 없음"
EMPTY_VALUES: Final = "고칠 공정 없음"
ROW_REMOVE_HINT: Final = (
    "고른 공정을 지웁니다 — 「판 만들기」 · 「새 판 적용」 을 눌러야 판에서 빠집니다"
)
MEMO_PLACEHOLDER: Final = field_placeholder(MEMO_LABEL, "26.12 새 공정 더함")

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
# 편집기 몫 줄에서 잠근 칸 — 소요기준은 참조공정을 따른다(`line_form`), 「옮김」 은 표지다.
BASIS_WHY: Final = "소요기준은 참조공정을 따릅니다"
CARRY_MARK_WHY: Final = "「옮김」 은 통째 옮김 줄 표지입니다"
CARRIED_WHY: Final = "통째 옮김({reason}) — 줄 지우기만 됩니다"
# 건너뛴 새 줄(`held`)의 잠금 — op 를 받는 색인에만 있고 그리지 않는다.
HELD_WHY: Final = "지운 새 줄 — 되돌리기로만 돌아옵니다"
# 빈 새 줄 — 채운 새 줄 뒤로 늘 이만큼(업무 키 `n<k>`, 「No.」 칸은 「새 k」). 접속 명단과 같은 수 —
# 붙일 덩어리가 남은 새 줄보다 길면 통째 거절이라 셋이면 공정 넷부터 한 번에 붙지 않았다.
FRESH_ROWS: Final = 10
NEW_LINE_PREFIX: Final = "n"
# 고칠 수 있는 공정 표 칸 → `LineFields` 이름.
_EDITABLE: Final = {
    NAME_COLUMN: "name",
    AREA_COLUMN: "area",
    MODULES_COLUMN: "modules",
    REFERENCE_COLUMN: "reference",
    STEP_COLUMN: "step",
    MCP_COLUMN: "mcp",
    START_COLUMN: "start",
    END_COLUMN: "end",
    MEMO_COLUMN: "memo",
}
# 초안 글을 글 그대로 받는 `LineFields` 칸.
_TEXT_FIELDS: Final = frozenset({"name", "memo", "area", "reference", "step", "mcp"})
_MONTH_PATTERN: Final = r"\d{6}"
_TEXT: Final = ValueFormat("text", 0)
_SUGGEST: Final = ValueFormat("suggest", 0, max_length=100)
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
        (REFERENCE_COLUMN, _SUGGEST),
        (STEP_COLUMN, _SUGGEST),
        (MCP_COLUMN, _SUGGEST),
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
# 이전 · 이후 칸은 머리 글(「~YY.MM」 · 「YY.MM~」)로 부른다 — 화면에 「이전」 · 「이후」 라는 칸
# 이름은 없다(Guide 「앱에서 작성」 과 한 이름).
_EDGE_HELP: Final = (
    "끝 「YY.MM~」 칸은 그 달부터 경로 끝까지 한 값, 앞 「~YY.MM」 칸은 그 앞 달 값(읽기 "
    "전용)입니다."
)
_ER_HELP: Final = (
    "바탕 값이 없는 달(새 공정 · 늘린 경로)의 ER 은 고치지 않으면 같은 달 양산 값을 따릅니다 — "
    "바탕 값이 있는 달은 고친 칸만 바뀝니다."
)
VALUE_HELPS: Final = {
    PRODUCTIVITY_TABLE: (
        f"UPEH — MI 공정도 UPEH 로 적습니다(판에는 ST = 60 / UPEH). {_ER_HELP} {_EDGE_HELP}"
    ),
    EQUIPMENT_TABLE: (
        f"설비보유 · 설비대여평가(빈칸 = 0) — 대여는 보유보다 클 수 없습니다. {_EDGE_HELP}"
    ),
    RATE_TABLE: f"효율(CAPA_RUN_RATE) · 편중률 — {_ER_HELP} {_EDGE_HELP}",
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
BEFORE_WHY: Final = "앞 「~YY.MM」 칸은 읽기 전용"
MULTIPLE_WHY: Final = "여러 값 — 한 값으로 고칠 수 없음"
OUTSIDE_WHY: Final = "경로 밖 달"
# 표 위 작업 줄(종류 · 「따라올 제품」 · 「판 만들기」)과 표 도구 막대를 한 줄로
# 세우는 창 폭 · 작업 줄 자리(`edit_grid.one_line_style` — 설계 규칙 4장 「부대공정 편집기 표 위
# 한 줄」).
ONE_LINE_MIN_WINDOW_PX: Final = 1360
ACTION_ROW_RESERVE_PX: Final = 490
ONE_LINE_STYLE: Final = edit_grid.one_line_style(
    ACTIONS_BOX,
    ACTION_ROW,
    GRID_BOX,
    min_window_px=ONE_LINE_MIN_WINDOW_PX,
    reserve_px=ACTION_ROW_RESERVE_PX,
)

# 세션 칸(AGENTS 5장 42). 펼친 판 = (펼친 때의 판 이력 차례, 바탕 sha 또는 None, 바탕 바이트 또는
# None). 칸 지도 = 값 표 칸 이름 → (갈래 "m" · "after" · "before", 달).
EDITOR: Final = SessionSlot(EDITOR_KEY, tuple)
COLUMNS: Final = SessionSlot(COLUMNS_KEY, dict, dict)
# (맥락 열쇠, `EditorContext`) — (시나리오 id, 기준정보 판)마다 한 번 센다.
CONTEXT: Final = SessionSlot(CONTEXT_KEY, tuple, tuple)
# (맥락 열쇠, 참조, 소요기준, 시작, 끝) → `FollowPreview` — 이 회차 줄들이 쓰는 열쇠만 남긴다(줄이
# 많아도 회차마다 다시 세지 않고, 바뀐 참조의 옛 열쇠는 걷힌다).
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
    받은 판 두기 · 비우기 · 읽기(만든 뒤 표가 바뀌거나 작성을 닫으면 편집기 판을 걷는다)."""

    lock: Callable[[], str | None]
    place: Callable[[StagedPack], None]
    discard: Callable[[], None]
    staged: Callable[[], StagedPack | None]


# --------------------------------------------------------------------------- 세션 상태


def editor_open() -> bool:
    return EDITOR.peek() is not None


def editor_has_edits() -> bool:
    """탭 점 · 새로고침 확인의 술어 — 흡수 때 적은 「펼친 판과 다름」(세션만 읽는다)."""
    return editor_open() and DIRTY.get()


def close_editor() -> None:
    """작성을 닫는다(「작성 닫기」 · 편집기 판 적용 뒤) — 네 표 초안 · 이력을 일부러 버리고(누름
    직전에 보낸 op 를 알림 없이 버림) 칸 지도 · 메모 칸 · 표지를 지운다."""
    for keys in TABLE_KEYS.values():
        edit_grid.discard_table(keys, KEYS)
    for slot in (EDITOR, COLUMNS, FOLLOW, DIRTY, BASE_PACK):
        slot.clear()
    INBOX.clear()


def collect() -> None:
    """출납 콜백 — 새 op 를 inbox 에 쌓고(`edit_grid.collect_outbox`) 탭 점을 먼저 켠다(화면 탭
    줄은 페이지보다 먼저 그린다 — 흡수가 정확한 값으로 고친다)."""
    edit_grid.collect_outbox(HOST, KEYS)
    if INBOX.peek():
        DIRTY.set(True)


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
        _render_close(hooks)
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


def _render_close(hooks: Hooks) -> None:
    if not DIRTY.get():
        if st.button(CLOSE_LABEL, key=CLOSE_BUTTON_KEY, icon=":material/close:", help=CLOSE_HELP):
            _close(hooks)
        return
    # 잃을 것이 있을 때만 한 번 묻는다(UI-STA-02 · UI-NTF-09).
    with st.popover(
        CLOSE_LABEL, icon=":material/close:", help=CLOSE_DIRTY_HELP, key=CLOSE_MENU_KEY
    ):
        if st.button(CLOSE_CONFIRM_LABEL, key=CLOSE_CONFIRM_KEY, icon=":material/delete_sweep:"):
            _close(hooks)


def _close(hooks: Hooks) -> None:
    """「작성 닫기」 · 「버리고 닫기」 — 받은 판 자리의 편집기 판도 걷는다(두면 버린 초안에서 나온
    판이 「새 판 적용」 으로 들어간다). 가져온 판 · 「새 판으로」 판은 그대로다. 적용 성공으로
    닫히는 길(`close_editor`)은 받은 판 상자가 먼저 비운다."""
    staged = hooks.staged()
    if staged is not None and staged.editor is not None:
        hooks.discard()
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
        # 누른 순간의 잠금 · 못 읽음은 그 자리에 고칠 입력이 없다 — 알림창 · Alarm 한 번(UI-NTF-03).
        queue_flash(
            FLASH_KEY,
            reason or UNREADABLE_REASON,
            kind="error",
            icon=":material/block:",
            popup_only=True,
        )
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


def follow_frame(
    model: EditorModel, context: EditorContext, key: tuple[object, ...]
) -> pd.DataFrame:
    """「따라올 제품」 표(결정2 — 읽기 전용) — 편집기 몫 줄마다 공정 · 참조공정(「표시명 (원본)」) ·
    STEP · MCP 와 그 참조공정을 따라올 제품 · 줄 · Buffer 밖 수. 수는 (맥락, 참조, 소요기준,
    기간)마다 한 번 센다(`FOLLOW` — 이 회차 줄들의 열쇠만 남김). 참조가 후보 밖이거나 시작월이
    없거나 표를 못 읽은 줄은 수 칸이 빈칸이다."""
    labels = get_process_labels()
    memo = FOLLOW.get()
    kept: dict[object, FollowPreview] = {}
    rows: list[dict[str, object]] = []
    for line in model.lines:
        if line.carried is not None:
            continue
        fields = line.fields
        reference = _text_or_none(fields.reference)
        choice = None if reference is None else reference_choice(context, reference)
        start = _month_of(fields.start)
        preview: FollowPreview | None = None
        if choice is not None and start is not None:
            end = _month_of(fields.end)
            memo_key = (key, choice.name, choice.basis, start, end)
            found = kept.get(memo_key, memo.get(memo_key))
            if not isinstance(found, FollowPreview):
                try:
                    found = follow_preview(
                        get_effective_reference_tables(),
                        choice.name,
                        choice.basis,
                        Period(start, end),
                    )
                except BOOTSTRAP_ERRORS:
                    found = None
            if isinstance(found, FollowPreview):
                kept[memo_key] = preview = found
        step = " · ".join(text for text in (fields.step.strip(), fields.mcp.strip()) if text)
        rows.append(
            {
                "공정": _line_name(line.line_id, fields.name),
                "참조공정": "" if reference is None else _reference_label(labels, reference),
                "STEP · MCP": step,
                "따라올 제품": None if preview is None else preview.products,
                "줄": None if preview is None else preview.rows,
                "Buffer 밖": None if preview is None else preview.uncounted,
            }
        )
    if kept.keys() != memo.keys():
        FOLLOW.set(kept)
    frame = pd.DataFrame(rows, columns=list(FOLLOW_COLUMNS))
    return frame.astype({column: "Int64" for column in FOLLOW_COUNTS})


def _reference_label(labels: ProcessLabels, name: str) -> str:
    """참조공정 후보 · 미리보기 글 — 표시명이 있으면 「표시명 (원본)」(UI-DAT-10), 없으면 원본."""
    label = labels.label(name)
    return name if label == name else f"{label} ({name})"


# --------------------------------------------------------------------------- 표 짓기


@dataclass(frozen=True)
class _LineRow:
    """공정 표 한 줄 — 줄 id · 양식 값(`line_form`) · 통째 옮김 까닭, 새 줄이면 그 번호와 한 칸
    이라도 적었나(적지 않은 새 줄은 편집기 줄이 아니다) · 건너뛴 줄인가(`held` — 적지 않았는데
    값 표 초안이 남은 새 줄, 그리지 않는다)."""

    line_id: str
    fields: LineFields
    carried: str | None
    number: int | None = None
    filled: bool = True
    held: bool = False


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
    """이 회차의 편집기 — 모형 · 공정 표 줄 · 값 표 칸 · 표 넷 · 초안 칸의 모형 열쇠 → 그리드
    자리 · 줄마다 월 보기, 흡수가 적는 판 지문(`_stamp`)."""

    model: EditorModel
    rows: tuple[_LineRow, ...]
    columns: _Columns
    tables: Mapping[str, _Table]
    places: Mapping[CellKey, tuple[tuple[str, str, str], ...]]
    views: Mapping[str, LineView]
    stamp: str = ""


def _line_rows(origin: EditorModel, context: EditorContext) -> tuple[_LineRow, ...]:
    """펼친 줄(차례 그대로) 뒤에 새 줄 `n1` ~ (채운 줄 · 건너뛴 줄 가운데 가장 뒤 번호 +
    `FRESH_ROWS`). 양식은 그 줄의 지금 참조공정 글(초안 포함)을 따른다(`line_form`) — 통째 옮김
    줄은 펼친 값, 적지 않은 새 줄은 빈 양식. 건너뛴 줄(`_held_numbers`)도 싣고 표시만 한다."""
    typed = _typed(_draft(LINE_TABLE))
    held = _held_numbers(typed)
    rows: list[_LineRow] = []
    for line in origin.origin:
        fields = line.fields
        if line.carried is None:
            own = typed.get(line.line_id, {})
            reference = own[REFERENCE_COLUMN] if REFERENCE_COLUMN in own else fields.reference
            fields = line_form(context, reference, fields)
        rows.append(_LineRow(line.line_id, fields, line.carried))
    filled = [
        number
        for line_id, own in typed.items()
        if (number := _fresh_number(line_id)) is not None and _filled(own)
    ]
    for number in range(1, max((*filled, *held), default=0) + FRESH_ROWS + 1):
        line_id = f"{NEW_LINE_PREFIX}{number}"
        own = typed.get(line_id, {})
        if not _filled(own):
            rows.append(_LineRow(line_id, LineFields(), None, number, False, number in held))
            continue
        fields = line_form(context, own.get(REFERENCE_COLUMN, ""))
        rows.append(_LineRow(line_id, fields, None, number))
    return tuple(rows)


def _held_numbers(typed: Mapping[str, Mapping[str, object]]) -> set[int]:
    """건너뛸 새 줄 번호 — 공정 표에 적은 칸이 없는데 값 표 초안이 남은 새 줄(그 줄을 지우거나 비운
    뒤). 빈 새 줄로 다시 내놓으면 그 줄에 적은 다른 공정이 남은 값을 물려받는다."""
    held: set[int] = set()
    for table in VALUE_TABLES:
        draft = _draft(table)
        if draft is None:
            continue
        for book in (draft["cells"], draft["bad"]):
            for row_id in book:
                line_id = str(row_id).split("|", 1)[0]
                number = _fresh_number(line_id)
                if number is not None and not _filled(typed.get(line_id, {})):
                    held.add(number)
    return held


def _fresh_number(line_id: str) -> int | None:
    """새 줄 업무 키 `n<k>` 의 k(펼친 줄 `b<n>` 이면 None)."""
    tail = line_id.removeprefix(NEW_LINE_PREFIX)
    return int(tail) if tail != line_id and tail.isdigit() else None


def _line_name(line_id: str, name: object) -> str:
    """줄을 부르는 이름 — 공정 이름, 없으면 새 줄은 「새 줄 k」, 그 밖은 줄 id."""
    number = _fresh_number(line_id)
    return _text_or_none(name) or (line_id if number is None else f"새 줄 {number}")


def _typed(draft: DraftState | None) -> dict[str, dict[str, object]]:
    """공정 표 초안 — 줄 id → 칸 → 적은 값(못 읽은 글은 적은 글). 줄 지우기 표지는 뺀다."""
    found: dict[str, dict[str, object]] = {}
    if draft is None:
        return found
    for book, wrong in ((draft["cells"], False), (draft["bad"], True)):
        for row_id, row_cells in book.items():
            for column, raw in row_cells.items():
                if column == ROW_REMOVED:
                    continue
                value = raw[0] if wrong and isinstance(raw, tuple) else raw
                found.setdefault(str(row_id), {})[str(column)] = value
    return found


def _filled(own: Mapping[str, object]) -> bool:
    """새 줄에 적은 칸이 있나(빈칸으로 되돌린 칸만 남은 줄은 적지 않은 줄)."""
    return any(value is not None for value in own.values())


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
    if name in _TEXT_FIELDS:
        return "" if raw is None else str(raw)
    if isinstance(raw, (int, float, str)) or raw is None:
        return raw
    return str(raw)


def _line_inputs(rows: Sequence[_LineRow]) -> list[tuple[str, LineFields]]:
    """공정 표의 전체 상태(양식 + 초안, 지운 줄 · 적지 않은 새 줄 뺌) → `with_lines` 입력."""
    draft = _draft(LINE_TABLE)
    typed = _typed(draft)
    removed = set(removed_keys(draft))
    found: list[tuple[str, LineFields]] = []
    for row in rows:
        if row.line_id in removed or not row.filled:
            continue
        if row.carried is not None:
            found.append((row.line_id, row.fields))
            continue
        own = typed.get(row.line_id, {})
        changes: dict[str, Any] = {
            name: _field_value(name, own[column])
            for column, name in _EDITABLE.items()
            if column in own
        }
        found.append((row.line_id, replace(row.fields, **changes)))
    return found


def _line_spec(carried: bool) -> GridSpec:
    """공정 표 규격 — 「옮김」 칸은 통째 옮김 줄이 있을 때만 싣는다(UI-TXT-08). 펼친 줄은 표에서
    빠지지 않고(지운 줄도 표지로 남는다) 새 줄은 옮김이 아니라, 작성 중 칸 집합은 바뀌지 않는다."""
    if carried:
        return LINE_SPEC
    return replace(
        LINE_SPEC,
        value_columns=tuple(column for column in LINE_COLUMNS if column != CARRY_COLUMN),
        column_formats=tuple(item for item in LINE_SPEC.column_formats if item[0] != CARRY_COLUMN),
    )


def _line_table(rows: Sequence[_LineRow]) -> _Table:
    """공정 표 — 펼친 줄 뒤에 빈 새 줄(빈 시작도 새 줄 칸이 먼저 선다 — UI-LAY-10). 편집기 몫 줄은
    소요기준(· 「옮김」)만 잠그고, 새 줄은 「빈 새 줄」 규칙(지우기는 그 줄 칸을 비움 · 붙일
    덩어리가 남은 새 줄보다 길면 거절)이다. 건너뛴 줄(`held`)은 그리지 않는다."""
    return _built(*_line_frame([row for row in rows if not row.held]))


def _line_slot(screen: _Screen) -> edit_grid.TableSlot:
    """op 를 받을 공정 표 — 그린 줄에 건너뛴 줄을 더한 색인. 건너뛴 줄은 모든 칸 · 지우기가 잠겨
    되돌리기 · 다시 실행(잠금을 보지 않는다)으로만 바뀐다 — 그 줄이 걷히기 전에 보낸 칸 쓰기가 지운
    공정 값을 물려받지 않고 건너뛴 수로 알려진다."""
    built = screen.tables[LINE_TABLE]
    if not any(row.held for row in screen.rows):
        return built.slot
    frame, spec, rules = _line_frame(screen.rows)
    return replace(built.slot, index=build_index(frame, spec, rules))


def _line_frame(rows: Sequence[_LineRow]) -> tuple[pd.DataFrame, GridSpec, RowRules]:
    """공정 표 양식 · 규격 · 줄 규칙(`_line_table` 몸통 — 건너뛴 줄은 모든 칸 · 지우기 잠금)."""
    carried = any(row.carried is not None for row in rows)
    spec = _line_spec(carried)
    locked = (BASIS_COLUMN, CARRY_COLUMN) if carried else (BASIS_COLUMN,)
    why = f"{BASIS_WHY} · {CARRY_MARK_WHY}" if carried else BASIS_WHY
    kinds: list[LockKind] = [
        LockKind(cols=locked, reason=why),
        LockKind(cols=locked, reason=why, fresh=True),
    ]
    rules: list[int] = []
    records: list[dict[str, object]] = []
    for number, row in enumerate(rows, start=1):
        fields = row.fields
        if row.held:
            kind = LockKind(cols=spec.value_columns, reason=HELD_WHY, remove=HELD_WHY)
            if kind not in kinds:
                kinds.append(kind)
            rules.append(kinds.index(kind))
        elif row.number is not None:
            rules.append(1)
        elif row.carried is None:
            rules.append(0)
        else:
            kind = LockKind(cols=LINE_COLUMNS, reason=CARRIED_WHY.format(reason=row.carried))
            if kind not in kinds:
                kinds.append(kind)
            rules.append(kinds.index(kind))
        records.append(
            {
                NO_COLUMN: str(number) if row.number is None else f"새 {row.number}",
                ID_COLUMN: row.line_id,
                LABEL_COLUMN: (
                    _text_or_none(fields.name) or row.line_id
                    if row.number is None
                    else f"새 줄 {row.number}"
                ),
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
                **(
                    {CARRY_COLUMN: None if row.carried is None else CARRY_COLUMN} if carried else {}
                ),
            }
        )
    frame = pd.DataFrame(records, columns=[NO_COLUMN, ID_COLUMN, LABEL_COLUMN, *spec.value_columns])
    return frame, spec, RowRules(tuple(kinds), tuple(rules))


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


def hidden_after(name: str) -> str:
    """이후 칸 이름의 숨은 짝 — 「여러 값」 으로 잠긴 이후 칸의 초안을 옮겨 두는 그리드 밖 칸이다.
    칸 지도가 같은 달을 가리켜 판에는 그대로 들고, 잠긴 칸에 그 초안 값이 그려지지 않는다."""
    return f"{name} (여러 값)"


def _columns(span: Sequence[int], views: Mapping[str, LineView]) -> _Columns:
    """값 표 칸 — 이전 칸은 어느 줄이 계획 첫 달 앞에서 시작할 때만, 이후 칸은 어느 줄이 계획 끝
    달 뒤로 이어질 때만 선다(UI-TXT-08). 이름(이후 칸의 숨은 짝 포함)은 칸 지도(`COLUMNS`)에 더해
    둔다."""
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
        roles[hidden_after(after)] = ("after", edge)
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
) -> _Table:
    """값 표 하나 — 살아 있는 편집기 몫 줄마다 그 파일의 값 줄(없으면 머리 줄만 — 「고칠 공정
    없음」). 칸 값은 양식(`CellView.default`)이고 잠긴 칸의 까닭은 줄마다 한 글로 잇는다."""
    file = VALUE_TABLES[table]
    kinds: list[LockKind] = []
    rules: list[int] = []
    records: list[dict[str, object]] = []
    for line in model.lines:
        if line.carried is not None:
            continue
        view = views.get(line.line_id)
        name = _line_name(line.line_id, line.fields.name)
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
    """월 칸 → YYYYMM(달 1 ~ 12 — 입력 문제 「월 꼴(YYYYMM)이 아님」 과 같은 판정), 아니면 None."""
    text = "" if value is None else str(value).strip()
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    valid = len(text) == 6 and text.isdigit() and 1 <= int(text[4:]) <= 12
    return int(text) if valid else None


def _screen(base: ExtraProcessPack | None, context: EditorContext) -> _Screen:
    """초안 전체에서 모형 · 표 넷을 다시 짓는다(병합 아님)."""
    origin = model_from_pack(base)
    rows = _line_rows(origin, context)
    model = with_lines(origin, _line_inputs(rows))
    cells, places = _value_inputs(model)
    model = with_cells(model, cells)
    views = month_view(model, context.months)
    columns = _columns(plan_span(context.months), views)
    tables: dict[str, _Table] = {LINE_TABLE: _line_table(rows)}
    for table in VALUE_TABLES:
        tables[table] = _value_table(table, model, views, columns)
    return _Screen(model, rows, columns, tables, places, views)


Place = tuple[str, str, str]


def _shown_place(screen: _Screen, place: Place) -> bool:
    """초안 칸이 이 회차 그리드 표 넷 가운데 하나에 보이는 칸인가(마운트한 종류와 상관없이)."""
    table, row_id, column = place
    built = screen.tables.get(table)
    return (
        built is not None and row_id in built.base.index.rows and column in built.spec.value_columns
    )


def _after_home(screen: _Screen, key: CellKey) -> str | None:
    """그 열쇠가 이 회차 이후 칸의 열쇠면 초안이 설 칸 이름 — 한 값이면 이후 칸, 여러 값으로
    잠겼으면 그 숨은 짝(`hidden_after`). 아니면 None(제자리)."""
    row, month = key
    after = screen.columns.after
    if not isinstance(month, Onward) or after is None:
        return None
    view = screen.views.get(row[0])
    cell = None if view is None else view.after.get(row)
    if cell is None or cell.key != month:
        return None
    return after if cell.editable else hidden_after(after)


def _tidy(screen: _Screen) -> bool:
    """초안을 이 회차 표에 맞춘다(그리드 이력은 건드리지 않는다) — 바꿨으면 참.

    - 걷은 칸(`redundant_cells`)은 이 회차 그리드에 보이지 않을 때만 지운다(계약 5 — 숨은 옛
      입력이 다른 창에서 되살아나지 않게). 보이는 칸은 사람이 지금 보고 적은 값이라 남긴다 — 다른
      칸 고침 · 되돌리기 뒤에도 그 값이다(보이는 값 = 판 값은 그대로).
    - 이 회차 이후 칸과 같은 열쇠의 초안은 이후 칸(한 값) 또는 그 숨은 짝(여러 값 — 잠긴 칸에 옛
      초안 값이 그려지지 않게)으로 옮긴다. 시작월이 계획 끝 뒤인 줄은 창마다 다른 이후 칸 이름이 한
      열쇠라, 옮기지 않으면 다른 창에서 적은 값이 보이지 않는 채 판에 든다.
    - 한 열쇠에 초안 자리가 둘 이상이면 하나만 남긴다 — 그 칸 이름, 보이는 자리, 마지막 자리
      차례(마지막 자리가 지금 모형이 쓰는 값이다)."""
    redundant = set(redundant_cells(screen.model))
    moves: dict[Place, str | None] = {}
    for key, places in screen.places.items():
        home = _after_home(screen, key)
        shown = [place for place in places if _shown_place(screen, place)]
        if key in redundant and not shown:
            moves.update(dict.fromkeys(places))
            continue
        keeper = next((place for place in places if place[2] == home), None)
        if keeper is None:
            keeper = shown[-1] if shown else places[-1]
        moves.update((place, None) for place in places if place != keeper)
        if home is not None and keeper[2] != home:
            moves[keeper] = home
    return _rewrite_drafts(moves)


def _clear_blank_fresh() -> bool:
    """공정 표 초안에서 빈칸 초안만 남은 새 줄(채운 줄을 Delete 로 비움)의 칸을 지운다 — 적지
    않은 새 줄의 양식은 빈칸이라 보이는 것은 그대로이고, 남기면 「적용 전 (n)」 에 세이고 그 줄에
    다시 적을 때 참조를 따른 양식(STEP · 시작월 등)을 빈칸 초안이 이긴다. 그리드 이력은 그대로라
    되돌리기는 비우기 앞 칸을 되살린다. 바꿨으면 참."""
    typed = _typed(_draft(LINE_TABLE))
    return _rewrite_drafts(
        {
            (LINE_TABLE, line_id, column): None
            for line_id, own in typed.items()
            if _fresh_number(line_id) is not None and not _filled(own)
            for column in own
        }
    )


def _rewrite_drafts(moves: Mapping[Place, str | None]) -> bool:
    """그리드 초안 칸을 옮기거나(새 칸 이름) 지운다(None) — 바꿨으면 참."""
    by_table: dict[str, dict[tuple[str, str], str | None]] = {}
    for (table, row_id, column), target in moves.items():
        by_table.setdefault(table, {})[(row_id, column)] = target
    changed = False
    for table, spots in by_table.items():
        draft = _draft(table)
        if draft is None:
            continue
        books: dict[str, dict[str, dict[str, Any]]] = {}
        for name in ("cells", "bad"):
            book: dict[str, dict[str, Any]] = {}
            for row_id, row_cells in draft[name].items():
                kept: dict[str, Any] = {}
                for column, value in row_cells.items():
                    spot = (str(row_id), str(column))
                    if spot not in spots:
                        kept[column] = value
                        continue
                    changed = True
                    target = spots[spot]
                    if target is not None:
                        kept[target] = value
                if kept:
                    book[row_id] = kept
            books[name] = book
        slot = SessionSlot(TABLE_KEYS[table][0], dict)
        if books["cells"] or books["bad"]:
            slot.set(books)
        else:
            slot.clear()
    return changed


def _stamp(model: EditorModel, edits: Mapping[CellKey, CellInput]) -> str:
    """판 본문을 정하는 것의 지문 — 줄(01 · 02 값) · 걷은 뒤 남은 고침 · 00 메모. 창 · 초안 자리와
    상관없다(시나리오를 바꿔도 같다)."""
    body = repr(
        (
            model.lines,
            sorted((repr(key), repr(value)) for key, value in edits.items()),
            MEMO.peek() or "",
        )
    )
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


def _absorb(base: ExtraProcessPack | None, context: EditorContext) -> _Screen:
    """inbox 를 반영하고(앞 회차 양식 — 브라우저가 본 표에 건너뛴 새 줄을 더해 — 로) 모형을 다시
    짓고 초안을 이 회차 표에 맞춘 뒤(`_tidy`) 탭 점 표지를 적고 판 지문을 단다."""
    if INBOX.peek():
        before = _screen(base, context)
        slots = {table: built.slot for table, built in before.tables.items()}
        slots[LINE_TABLE] = _line_slot(before)
        edit_grid.apply_inbox(KEYS, slots)
        _clear_blank_fresh()
    screen = _screen(base, context)
    if _tidy(screen):
        screen = _screen(base, context)
    model = screen.model
    edits = effective_edits(model)
    DIRTY.set(bool(edits) or model.lines != model.origin)
    return replace(screen, stamp=_stamp(model, edits))


def _drop_stale(hooks: Hooks, stamp: str) -> None:
    """받은 판이 이 편집기에서 만든 판인데 그 뒤 표가 바뀌었으면 걷는다 — 두면 「새 판 적용」 이
    만든 때의 판을 넣고 작성을 닫아 그 뒤 고친 것을 말없이 버린다. 받은 판 상자보다 먼저 부른다
    (같은 회차의 「새 판 적용」 누름도 닿지 않는다)."""
    staged = hooks.staged()
    if staged is None or staged.editor is None or staged.editor.made_from == stamp:
        return
    hooks.discard()
    queue_flash(FLASH_KEY, STALE_STAGED, kind="info")
    st.rerun()


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
    check_box = st.container(key=MAKE_BOX)
    with actions:
        kind, pressed = _render_actions(screen, key, context, lock)
    with grid_box:
        _render_grid(screen, kind, context)
    with check_box:
        _render_check(screen, context)
    if pressed:
        _make(repository, base, context, hooks, seen_seq=int(seen_seq), base_sha=base_sha)
    _drop_stale(hooks, screen.stamp)


def _render_actions(
    screen: _Screen, key: tuple[object, ...], context: EditorContext, lock: str | None
) -> tuple[str, bool]:
    """작업 줄(표 위 — UI-LAY-03) — 종류 단추 · 「따라올 제품」 · 「판 만들기」(셋 다 늘 선다 —
    그리드 앞에 조건부 형제를 두지 않는다). (고른 종류, 「만들기」 누름)."""
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
        with st.popover(
            FOLLOW_LABEL, icon=":material/account_tree:", help=FOLLOW_HELP, key=FOLLOW_MENU_KEY
        ):
            _render_follow(screen, key, context)
        with st.popover(
            MAKE_LABEL,
            icon=":material/note_add:",
            help=lock or MAKE_HELP,
            disabled=lock is not None,
            key=MAKE_MENU_KEY,
        ):
            pressed = _render_make_form(lock)
    kind = chosen if isinstance(chosen, str) and chosen in KINDS else next(iter(KINDS))
    return kind, pressed


def _render_grid(screen: _Screen, kind: str, context: EditorContext) -> None:
    """고른 종류의 표를 그린다 — 공정 표는 「글 + 후보」 칸의 후보를 껍데기에 싣는다(표 본문 ·
    `baseKey` 밖이라 후보가 바뀌어도 다시 마운트되지 않는다)."""
    table = KINDS[kind]
    built = screen.tables[table]
    suggest = _suggestions(context, screen.model) if table == LINE_TABLE else None
    shell = edit_grid.shell_data(
        HOST,
        built.base,
        built.spec,
        base_key=built.base_key,
        changes_label=CHANGES_LABEL,
        suggest=suggest,
    )
    # 공정 표는 늘 새 줄이 있어 빈 표가 없다 — 값 표는 편집기 몫 줄이 없을 때(옮김 줄뿐 포함).
    texts = dict(shell["texts"])
    if table == LINE_TABLE:
        texts["rowRemoveHint"] = ROW_REMOVE_HINT
    else:
        texts["empty"] = EMPTY_VALUES
    shell["texts"] = texts
    feed = edit_grid.feed_data(HOST, built.slot, KEYS, base_key=built.base_key)
    edit_grid.render_edit_grid(
        HOST, shell, feed, on_outbox=collect, page_style=ONE_LINE_STYLE, rows=True
    )


def _render_make_form(lock: str | None) -> bool:
    """「판 만들기」 팝오버 — 00 메모와 「만들기」(쓰기 잠금으로만 잠근다 — 고친 것 없는 누름도 누른
    회차에 판정)."""
    st.text_input(
        MEMO_LABEL,
        key=MEMO_KEY,
        persist_state="session",
        max_chars=200,
        placeholder=MEMO_PLACEHOLDER,
        label_visibility="collapsed",
        width=320,
    )
    pressed = st.button(
        MAKE_BUTTON_LABEL,
        key=MAKE_BUTTON_KEY,
        type="primary",
        icon=":material/note_add:",
        disabled=lock is not None,
        help=lock or MAKE_HELP,
    )
    return bool(pressed) and lock is None


def _render_check(screen: _Screen, context: EditorContext) -> None:
    """표 아래 「확인할 칸 n」(입력 문제 + 기준 데이터 알림 — 막지 않는다, G6). 있을 때만 서고
    그리드 뒤라 그리드를 다시 마운트하지 않는다."""
    frame = check_frame(screen.model, context)
    if frame.empty:
        return
    with st.popover(
        CHECK_LABEL.format(n=f"{len(frame):,}"), icon=":material/error:", key=CHECK_MENU_KEY
    ):
        # 팝오버는 안 글 폭만큼 넓어진다 — 표 폭을 정해 「까닭」 이 굴림 밖으로 숨지 않게.
        st.dataframe(frame, hide_index=True, width=CHECK_WIDTH, placeholder="")


def check_frame(model: EditorModel, context: EditorContext) -> pd.DataFrame:
    """「확인할 칸 n」 의 내역 — 관문이 거절할 입력(`input_problems`)과 관문은 받지만 등록 때
    빠지거나 잘릴 것(`editor_warnings`)."""
    names = {line.line_id: _line_name(line.line_id, line.fields.name) for line in model.lines}
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
    labels: ProcessLabels | None = None
    for warning in editor_warnings(model, context):
        rule = warning.code.startswith("R-")
        reason = f"{warning.code} · {warning.text}" if rule else warning.text
        line = None if warning.line_id is None else model.line(warning.line_id)
        if warning.code == "R-02" and line is not None:
            labels = get_process_labels() if labels is None else labels
            source = _labelled_source(labels, context, line.fields.reference)
            reason += "" if source is None else LABEL_HINT.format(name=source)
        rows.append(
            {
                "공정": "" if warning.line_id is None else names.get(warning.line_id, ""),
                "까닭": reason,
                "표": WARNING_TABLES.get(warning.code, ""),
                "칸": "",
                "달": "",
            }
        )
    return pd.DataFrame(rows, columns=list(CHECK_COLUMNS))


def _labelled_source(labels: ProcessLabels, context: EditorContext, reference: str) -> str | None:
    """후보 밖 참조공정 글이 어떤 후보의 표시명(또는 「표시명 (원본)」 — 대소문자 무시)이면 그
    원본 — 표시명을 적거나 붙인 실수를 R-02 까닭 끝에 짚는다(AGENTS 8장 — 막지는 않는다, G6)."""
    text = reference.strip().casefold()
    if not text or reference_choice(context, reference) is not None:
        return None
    for name in context.references:
        label = labels.label(name)
        if label != name and text in {label.casefold(), _reference_label(labels, name).casefold()}:
            return name
    return None


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


# ------------------------------------------------------------------- 후보 · 따라올 제품


def _suggestions(context: EditorContext, model: EditorModel) -> dict[str, Suggestions]:
    """공정 표 「글 + 후보」 칸의 후보 — 참조공정은 `reference_choices`(지금 줄 이름은 뺌 — V-06,
    「표시명 (원본)」 을 보이고 원본을 넣음), STEP · MCP 는 그 줄 참조공정 글로 고르는 조합 표
    (「STEP · MCP」 를 보이고 제 칸 몫을 넣음 — 후보 밖 참조면 목록 없음)."""
    labels = get_process_labels()
    references = tuple(
        Suggestion(_reference_label(labels, choice.name), choice.name)
        for choice in reference_choices(context, model)
    )
    steps: dict[str, tuple[Suggestion, ...]] = {}
    mcps: dict[str, tuple[Suggestion, ...]] = {}
    for name, choice in context.references.items():
        steps[name] = tuple(Suggestion(f"{step} · {mcp}", step) for step, mcp in choice.steps)
        mcps[name] = tuple(Suggestion(f"{step} · {mcp}", mcp) for step, mcp in choice.steps)
    return {
        REFERENCE_COLUMN: Suggestions(references),
        STEP_COLUMN: Suggestions(by=REFERENCE_COLUMN, table=steps),
        MCP_COLUMN: Suggestions(by=REFERENCE_COLUMN, table=mcps),
    }


def _render_follow(screen: _Screen, key: tuple[object, ...], context: EditorContext) -> None:
    """「따라올 제품」 팝오버 안 — 표(`follow_frame`), 편집기 몫 줄이 없으면 빈 상태 한 마디."""
    frame = follow_frame(screen.model, context, key)
    if frame.empty:
        st.caption(EMPTY_LINES)
        return
    # 팝오버는 안 글 폭만큼 넓어진다 — 표 폭을 정해 수 칸이 굴림 밖으로 숨지 않게.
    st.dataframe(frame, hide_index=True, width=FOLLOW_WIDTH, placeholder="")


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
        queue_flash(FLASH_KEY, reason, kind="error", icon=":material/block:", popup_only=True)
        st.rerun()
    collect()
    screen = _absorb(base, context)
    model = screen.model
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
            # 받아 둔 판이 있었으면 비웠다고 말한다(말없이 사라지지 않게 — UI-NTF-09).
            held = hooks.staged() is not None
            hooks.discard()
            queue_flash(FLASH_KEY, UNCHANGED_CLEARED if held else UNCHANGED_EDITOR, kind="info")
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
        made_from=screen.stamp,
    )
    staged = stage_editor_pack(built, origin, now=now, base=model.base, before=before)
    if pack is not None and state.last_seq != seen_seq:
        staged = replace(staged, judgement=PackJudgement(MOVED_VERDICT, MOVED_REASON))
    hooks.place(staged)
    _queue_made(staged)
    st.rerun()


def _queue_made(staged: StagedPack) -> None:
    """「만들기」 결과를 알림창 한 줄로도 낸다 — 그리드가 화면 높이를 채우면 받은 판 상자가 첫
    화면 밖에 선다(G3). 거절 · 적용할 수 없음은 상자가 표 · 까닭을 들어 곁에 그리지 않는다
    (UI-NTF-03)."""
    reading = staged.reading
    if not reading.accepted or staged.judgement is None:
        message = MADE_REJECTED.format(n=f"{len(reading.problems):,}")
        queue_flash(FLASH_KEY, message, kind="warning", popup_only=True)
    elif not staged.applicable:
        message = MADE_MOVED.format(n=reading.version_no)
        queue_flash(FLASH_KEY, message, kind="warning", popup_only=True)
    else:
        queue_flash(FLASH_KEY, MADE_PACK.format(n=reading.version_no))
