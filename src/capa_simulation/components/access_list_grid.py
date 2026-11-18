# Purpose: Admin 「접속 명단」 을 범용 편집 그리드의 줄 규칙 표로 잇는다(양식 · 잠금 · 새 줄).

"""Admin Area 「접속 명단」 의 편집 표(2026-11-18 접속 등급 구현 확인 보드 「고칠 것」 — 메모 「JS
기반 편집기 만들어둔거 그 형태로 적용시킬수있나?」, 사용자 답 「추가 · 지우기까지 표 안에서」).

기준 정보 · 생산 계획과 같은 범용 편집 그리드(`components/edit_grid.py`)를 줄 규칙 표로 쓴다 —
칸마다 형식(글 · 고르기), 보이지 않는 업무 키, 줄 규칙(잠긴 칸 · 지울 수 없는 줄 · 빈 새 줄), 줄
지우기(`services/edit_grid` 모듈 설명).

- **줄** — 명단 사람(파일 차례) 뒤에 빈 새 줄 `FRESH_ROWS` 개(채운 새 줄 뒤로 늘 그만큼 — 여러
  사람을 붙여 넣으면 저장 뒤 · 다음 회차에 줄이 는다). 업무 키는 사람의 견주는 꼴 loginid · 새 줄
  `+n` 이고 맨 앞 분류 칸 `No.` 는 차례 글(새 줄은 「새 n」)이다 — 업무 키가 보이는 칸이 아니라
  명단이
  다시 읽혀 차례가 바뀌어도 초안이 제 사람에게 붙는다.
- **칸** — 계정 · 이름 · 부서(글) · 등록일 · 등록 길(글, 늘 잠김) · 등급(고르기 — 열람 · 실무자 ·
  관리자 · 개발자, 값은 차례 번호). 새 줄은 계정 · 이름 · 부서 · 등급을 적고, 계정은 loginid 꼴만
  받는다(틀리면 빨간 칸).
- **잠금**(까닭은 칸 · 단추 풍선과 상태 줄) — 명단 사람의 계정 · 이름 · 부서 · 등록일 · 등록 길, 나
  자신과 환경변수로 정한 개발자의 등급 칸 · 줄 지우기, 새 줄의 등록일 · 등록 길.
- **초안은 세션 칸**(`CELLS_KEY` · `HISTORY_KEY`) — 출납 콜백은 inbox 에 쌓기만 하고(`collect`)
  본문 · 저장 콜백이 반영한다(`apply`). 저장은 `access_list_admin` 이 이 초안을
  `services/access_list_plan` 으로 읽어 지금 저장 함수로 쓴다.
- **표는 이 회차의 명단 한 벌로 짓는다**(작은 표라 캐시 경계를 두지 않는다 — 프로세스 전역 캐시에
  사람 값을 두지 않는다). `baseKey` 는 껍데기 본문의 지문이라 같은 명단 · 같은 줄 수면 회차마다 같은
  껍데기(해시 참조)다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation.auth import grades
from capa_simulation.auth.access import LOGINID_PATTERN, VIA_SELF, ListDocument, ListEntry
from capa_simulation.auth.access_store import MAX_PROFILE_LENGTH
from capa_simulation.components import edit_grid
from capa_simulation.korea_time import kst_clock
from capa_simulation.services.access_list_plan import (
    ACCOUNT_COLUMN,
    DATE_COLUMN,
    DEPT_COLUMN,
    GRADE_COLUMN,
    GRADE_OPTIONS,
    NAME_COLUMN,
    VALUE_COLUMNS,
    VIA_COLUMN,
    AccessPlan,
    fresh_key,
    is_fresh,
    plan_changes,
)
from capa_simulation.services.edit_grid import (
    GridSpec,
    LockKind,
    RowRules,
    ValueFormat,
    change_counts,
)
from capa_simulation.services.edit_grid_payload import EditGridBase, build_base

HOST: Final = "admin-access-grid"
TABLE: Final = "ACCESS_LIST"
TITLE: Final = "접속 명단"
CHANGES_LABEL: Final = "저장 전 변경"
CHANGES_BUTTON: Final = "저장 전"
CELLS_KEY: Final = "admin_area_access_grid_cells"
HISTORY_KEY: Final = "admin_area_access_grid_history"
KEYS: Final = edit_grid.GridKeys(
    inbox="admin_area_access_grid_inbox",
    applied="admin_area_access_grid_applied",
    toast="admin_area_access_grid_toast",
    discarded="admin_area_access_grid_discarded",
)
KEY_COLUMN: Final = "No."
ID_COLUMN: Final = "_id"
LABEL_COLUMN: Final = "_label"
# 채운 새 줄 뒤로 늘 비워 두는 새 줄 수.
FRESH_ROWS: Final = 10
# 명단에 든 길 — 「등록 길」 칸과 「최근 등록 · 빼기」 의 「한 일」 이 함께 쓰는 두 낱말.
VIA_SELF_LABEL: Final = "스스로 등록"
VIA_ADMIN_LABEL: Final = "개발자가 넣음"
# loginid 꼴(`access.LOGINID_PATTERN`) + 글자 · 숫자가 하나는 있음(`access.entry_key`).
ACCOUNT_PATTERN: Final = r"(?=.*[A-Za-z0-9])" + LOGINID_PATTERN.pattern.removeprefix(
    "^"
).removesuffix("$")
ACCOUNT_PATTERN_ERROR: Final = "loginid 꼴이 아닙니다 — 영문 · 숫자 · . _ @ - 만 씁니다"
LISTED_WHY: Final = "명단에 든 사람의 계정 · 이름 · 부서 · 등록일 · 등록 길은 고칠 수 없습니다"
SELF_WHY: Final = "나 자신의 등급은 바꾸거나 지울 수 없습니다"
ENV_WHY: Final = "환경변수로 정한 개발자는 등급을 바꾸거나 지울 수 없습니다"
FRESH_WHY: Final = "등록일 · 등록 길은 저장할 때 적힙니다"
_LOCKED_INFO: Final = (ACCOUNT_COLUMN, NAME_COLUMN, DEPT_COLUMN, DATE_COLUMN, VIA_COLUMN)
# 줄 규칙의 차례 — `RULES.kinds` 번호.
LISTED, SELF, ENV, FRESH = 0, 1, 2, 3
RULE_KINDS: Final = (
    LockKind(cols=_LOCKED_INFO, reason=LISTED_WHY),
    LockKind(cols=VALUE_COLUMNS, reason=SELF_WHY, remove=SELF_WHY),
    LockKind(cols=VALUE_COLUMNS, reason=ENV_WHY, remove=ENV_WHY),
    LockKind(cols=(DATE_COLUMN, VIA_COLUMN), reason=FRESH_WHY, fresh=True),
)
_TEXT: Final = ValueFormat("text", 0)
_PROFILE: Final = ValueFormat("text", 0, max_length=MAX_PROFILE_LENGTH)
SPEC: Final = GridSpec(
    table=TABLE,
    title=TITLE,
    key_columns=(KEY_COLUMN,),
    value_columns=VALUE_COLUMNS,
    fmt=_TEXT,
    column_formats=(
        (ACCOUNT_COLUMN, ValueFormat("text", 0, pattern=ACCOUNT_PATTERN, max_length=64)),
        (NAME_COLUMN, _PROFILE),
        (DEPT_COLUMN, _PROFILE),
        (DATE_COLUMN, _TEXT),
        (VIA_COLUMN, _TEXT),
        (GRADE_COLUMN, ValueFormat("choice", 0, options=GRADE_OPTIONS)),
    ),
    id_column=ID_COLUMN,
    label_column=LABEL_COLUMN,
    row_ops=True,
)


def date_text(value: str) -> str:
    """파일의 UTC 등록 시각 → KST 날짜. 읽지 못하면 받은 글 그대로(사람이 고친 파일)."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return kst_clock(moment, "%Y-%m-%d")
    except (ValueError, OverflowError, OSError):
        return value


def via_label(entry: ListEntry) -> str:
    return VIA_SELF_LABEL if entry.via == VIA_SELF else VIA_ADMIN_LABEL


@dataclass(frozen=True)
class AccessTable:
    """이 회차의 표 — 양식 · 껍데기 본문 · 지문, 명단 사람의 지금 등급 · 새 줄 키 · 잠긴 사람."""

    template: pd.DataFrame
    base: EditGridBase
    base_key: str
    listed: Mapping[str, str]
    fresh: tuple[str, ...]
    locked: frozenset[str]

    @property
    def slot(self) -> edit_grid.TableSlot:
        return edit_grid.TableSlot(self.base.index, SPEC, CELLS_KEY, HISTORY_KEY)


def fresh_count(draft_keys: Mapping[str, object] | None) -> int:
    """새 줄 수 — 채운 새 줄 가운데 가장 뒤 번호 + `FRESH_ROWS`."""
    highest = 0
    for key, cells in (draft_keys or {}).items():
        if is_fresh(key) and cells:
            number = key.removeprefix("+")
            if number.isdigit():
                highest = max(highest, int(number))
    return highest + FRESH_ROWS


def _filled(draft: Mapping[str, object] | None) -> dict[str, object]:
    """초안에서 값이 있는 새 줄 칸(빈칸만 남은 줄은 채운 줄이 아니다)."""
    if not isinstance(draft, Mapping):
        return {}
    cells = draft.get("cells")
    bad = draft.get("bad")
    found: dict[str, object] = {}
    for book in (cells, bad):
        if not isinstance(book, Mapping):
            continue
        for key, row in book.items():
            if isinstance(row, Mapping) and any(value is not None for value in row.values()):
                found[str(key)] = row
    return found


def build_table(
    document: ListDocument,
    grade_of: Callable[[str], str],
    *,
    own: str | None,
    env: frozenset[str],
) -> AccessTable:
    """명단 한 벌 → 표. 새 줄 수는 지금 초안이 정한다(`fresh_count`)."""
    rows: list[dict[str, object]] = []
    kinds: list[int] = []
    listed: dict[str, str] = {}
    locked: set[str] = set()
    for number, entry in enumerate(document.entries, start=1):
        key = entry.loginid
        grade = grade_of(key)
        listed[key] = grade
        kind = SELF if key == own else ENV if key in env else LISTED
        if kind != LISTED:
            locked.add(key)
        kinds.append(kind)
        rows.append(
            {
                KEY_COLUMN: str(number),
                ID_COLUMN: key,
                LABEL_COLUMN: key,
                ACCOUNT_COLUMN: key,
                NAME_COLUMN: entry.name or None,
                DEPT_COLUMN: entry.dept or None,
                DATE_COLUMN: date_text(entry.added_at) or None,
                VIA_COLUMN: via_label(entry),
                GRADE_COLUMN: float(grades.GRADES.index(grade)),
            }
        )
    count = fresh_count(_filled(st.session_state.get(CELLS_KEY)))
    fresh = tuple(fresh_key(number) for number in range(1, count + 1))
    for number, key in enumerate(fresh, start=1):
        kinds.append(FRESH)
        rows.append(
            {
                KEY_COLUMN: f"새 {number}",
                ID_COLUMN: key,
                LABEL_COLUMN: f"새 줄 {number}",
                **dict.fromkeys(VALUE_COLUMNS),
            }
        )
    columns = [KEY_COLUMN, ID_COLUMN, LABEL_COLUMN, *VALUE_COLUMNS]
    template = pd.DataFrame(rows, columns=columns)
    base = build_base(template, SPEC, None, RowRules(RULE_KINDS, tuple(kinds)))
    digest = hashlib.sha1(
        json.dumps(base.body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return AccessTable(
        template=template,
        base=base,
        base_key=f"{TABLE}:{digest}",
        listed=listed,
        fresh=fresh,
        locked=frozenset(locked),
    )


def collect() -> None:
    """출납 콜백 — 새 op 를 inbox 에 쌓기만 한다(`edit_grid.collect_outbox`)."""
    edit_grid.collect_outbox(HOST, KEYS)


def apply(table: AccessTable) -> bool:
    """inbox 의 op 를 초안 · 이력에 반영한다(초안이 바뀌었으면 참)."""
    return edit_grid.apply_inbox(KEYS, {TABLE: table.slot})


def draft_counts() -> tuple[int, int, int]:
    """(고친 칸, 고친 줄, 오류 칸)."""
    return change_counts(edit_grid.draft_of(CELLS_KEY))


def plan(table: AccessTable) -> AccessPlan:
    """이 회차 초안의 저장 판."""
    return plan_changes(
        edit_grid.draft_of(CELLS_KEY), listed=table.listed, fresh=table.fresh, locked=table.locked
    )


def discard(*, quiet: bool = True) -> None:
    """초안 · 이력을 버린다(「편집 취소」 · 저장 끝 — 다음 회차에 새 `gen`). `quiet` 면 누름 직전에
    보낸 op 를 알림 없이 버린다."""
    edit_grid.discard_table((CELLS_KEY, HISTORY_KEY), KEYS if quiet else None)


def forget(keys: frozenset[str]) -> None:
    """저장한 사람 · 새 줄의 초안 칸을 걷고 이력을 버린다(일부만 저장된 뒤 — 남은 고침은 둔다)."""
    draft = edit_grid.draft_of(CELLS_KEY)
    if draft is None:
        discard()
        return
    kept = {
        name: {key: row for key, row in book.items() if key not in keys}
        for name, book in (("cells", draft["cells"]), ("bad", draft["bad"]))
    }
    discard()
    st.session_state[CELLS_KEY] = kept if kept["cells"] or kept["bad"] else None


def _shell(table: AccessTable | None) -> dict[str, object]:
    if table is None:
        return edit_grid.shell_data(HOST, None, None, base_key="", changes_label=CHANGES_LABEL)
    shell = edit_grid.shell_data(
        HOST, table.base, SPEC, base_key=table.base_key, changes_label=CHANGES_LABEL
    )
    texts = dict(shell["texts"])
    texts["errors"] = {**texts["errors"], "pattern": ACCOUNT_PATTERN_ERROR}
    texts["empty"] = "명단에 사람이 없습니다"
    # 이 표의 동작은 「저장」 이라 변경 목록 단추도 「저장 전 (n)」 이다(설계 규칙 UI-CON-02).
    texts["changesButton"] = CHANGES_BUTTON
    shell["texts"] = texts
    return shell


def render(table: AccessTable | None, *, page_style: str = "") -> None:
    """그리드 자리 — 늘 같은 자리에서 부른다(명단을 못 읽은 회차는 표 없는 껍데기로 마운트만
    남긴다)."""
    feed = edit_grid.feed_data(
        HOST,
        table.slot if table is not None else None,
        KEYS,
        base_key=table.base_key if table is not None else "",
    )
    edit_grid.render_edit_grid(HOST, _shell(table), feed, on_outbox=collect, page_style=page_style)
