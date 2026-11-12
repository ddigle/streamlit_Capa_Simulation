# Purpose: Space 「호기 정보」 창 칸 고치기의 칸 꼴 · 잠금 data 와 고친 칸의 판정 · 얹기를 낸다.

"""배치 편집기 「호기 정보」 창에서 칸을 고친다(2026-11-12 Space 시안 보드 답 5-4 · 5-5 · 5-6).

- **같은 칸 · 같은 잠금**(5-4 「same」) — 칸 꼴 · 고를 값 · 빈 값 허용 · 제안은 설비 마스터 표의 칸
  정의(`equipment_grid.columns_payload`)를, 줄마다 잠금 갈래는 표와 같은 판정(`row_lock_kinds` ×
  `LOCK_SETS`)을 쓴다. 창에서만 잠그는 칸(`SHEET_FIXED_LOCKS` — 설비명 · 동 · 층 · 단계 · 도면)은
  고치는 길이 따로 있거나(선택 칸 「이름」 · 「다른 층으로 보내기」) 계산 칸이다.
- **판정은 설비 마스터 한 벌**(5-6 메모 「호기 정보 창에서 즉시 막고, 알람으로」) — 고친 칸은
  표 출납과 같은 다듬기(`coerce_master_cell`), 모듈 묶음 같이 쓰기 계획
  (`equipment_units.plan_group_writes` — 2026-11-12 답 3-5 「all」), 같은 규칙
  표(`equipment_master_issues`, 표와 같은 인자 — 캔버스 · 오늘)를 지난다. 규칙은 **받은 칸을 모두
  얹은 마지막 상태**와 고치기 앞을 견줘 고친 줄 · 따라간 형제 줄에 **새로** 생긴 막는 결과만 그
  칸에 짚는다 — 입력 차례를 타지 않고, 다른 호기의 기존 오류로는 막히지 않는다.
- 브라우저는 data 가 준 잠금 · 고를 값만 곧바로 막는다(설비 마스터 표 JS 와 같은 몫). 칸끼리 ·
  줄끼리 규칙은 여기에만 있다 — 브라우저에 같은 판정을 또 만들지 않는다.

`parse_sheet_cells` · `SheetCell` 은 `space_unit_sheet` 에 둔다 — 적용값 읽기
(`space_layout_edit.parse_editor_apply`)가 이 파일을 부르면 import 고리가 생긴다(이 파일이 표
계층을 부른다). 여기서 같은 이름으로 다시 내보낸다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    UNIT_SHARED_COLUMNS,
)
from capa_simulation.services.equipment_grid import (
    GROUP_LOCKED_TOAST,
    LOCK_SETS,
    GridContext,
    cell_text,
    columns_payload,
    grid_index,
    row_lock_kinds,
    store_cell,
)
from capa_simulation.services.equipment_units import (
    GroupWrite,
    module_group_rows,
    plan_group_writes,
)
from capa_simulation.services.equipment_validation import (
    CellParseError,
    MasterIssue,
    coerce_master_cell,
    equipment_master_issues,
)
from capa_simulation.services.floor_layout_profile import FloorCanvasMap
from capa_simulation.services.space_layout_edit import PendingRenames
from capa_simulation.services.space_unit_sheet import (
    PLACE_COLUMN,
)
from capa_simulation.services.space_unit_sheet import (
    SheetCell as SheetCell,
)
from capa_simulation.services.space_unit_sheet import (
    parse_sheet_cells as parse_sheet_cells,
)

# 창에서만 잠그는 칸 → 까닭(풍선). 설비 마스터 표에서는 고치는 칸이지만 창에서는 고치는 길이 따로
# 있거나(이름 바꿈은 비가동 일정 · 묶음이 따라가는 선택 칸 「이름」, 층 옮김은 모듈 묶음이 함께 가는
# 「다른 층으로 보내기」) 계산 칸(단계 · 도면)이다. 표의 `_locked` 는 배치 잠금이 없으면 동 · 층을
# 받으므로 서버도 이 표로 따로 거부한다.
STAGE_COLUMN: Final = "단계"
NAME_LOCK_REASON: Final = "설비명은 선택 칸 「이름」 으로 바꿉니다"
FLOOR_LOCK_REASON: Final = "동 · 층은 선택 칸 「다른 층으로 보내기」 로 옮깁니다"
COMPUTED_LOCK_REASON: Final = "계산 칸이라 고치지 않습니다"
SHEET_FIXED_LOCKS: Final[Mapping[str, str]] = {
    EQUIPMENT_ID_COLUMN: NAME_LOCK_REASON,
    "동": FLOOR_LOCK_REASON,
    "층": FLOOR_LOCK_REASON,
    STAGE_COLUMN: COMPUTED_LOCK_REASON,
    PLACE_COLUMN: COMPUTED_LOCK_REASON,
}
# 창 줄이 편집본의 한 줄로 이어지지 않을 때(같은 이름 둘 · 편집본에 없음)의 잠금 까닭.
MISSING_LOCK_REASON: Final = "편집본에서 이 호기를 한 줄로 찾지 못해 고치지 않습니다"
# 막힌 칸의 갈래(`CellVerdict.rule`) — 규칙 표 밖의 것. 규칙에 걸린 칸은 그 규칙 코드다.
RULE_FIXED: Final = "sheet_fixed"
RULE_COLUMN: Final = "sheet_column"
RULE_UNIT: Final = "sheet_unit"
RULE_LOCKED: Final = "sheet_locked"
RULE_SIBLING_LOCKED: Final = "sheet_sibling_locked"
RULE_SPLIT: Final = "sheet_split"
# 칸 글이 빈 값일 때 알림 글에 적는 말.
BLANK_TEXT: Final = "(비움)"


def editable_columns(columns: Sequence[str]) -> tuple[str, ...]:
    """창 칸 가운데 고칠 수 있는 칸(창 차례) — 계약 칸이고 창에서만 잠그는 칸이 아닌 것."""
    return tuple(
        column
        for column in columns
        if column in EQUIPMENT_COLUMNS and column not in SHEET_FIXED_LOCKS
    )


def _unit_names(frame: pd.DataFrame) -> list[str]:
    """줄마다 설비명(앞뒤 공백을 뗀 글, 빈 값은 `""`) — 창 줄 id 와 같은 규칙이다."""
    return [cell_text(value) for value in frame[EQUIPMENT_ID_COLUMN].tolist()]


def _positions(names: Sequence[str]) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for position, name in enumerate(names):
        if name:
            found.setdefault(name, []).append(position)
    return found


def unit_lock_kinds(
    context: GridContext,
    master: pd.DataFrame,
    saved: pd.DataFrame,
    renames: PendingRenames,
) -> dict[str, tuple[str, ...]]:
    """설비명 → 잠금 갈래(잠금이 있는 호기만) — 표와 같은 판정(`row_lock_kinds`)을 창 줄 id 로
    옮긴 것이다. 저장본 호기인지(배치 잠금의 `layout` · `place`)는 표의 행 id 규칙(`grid_index`)으로
    가른다."""
    frame = master.reset_index(drop=True)
    index = grid_index(frame, saved.reset_index(drop=True), renames.units)
    names = _unit_names(frame)
    kinds_by_name: dict[str, tuple[str, ...]] = {}
    for row_id, kinds in row_lock_kinds(context, index, frame).items():
        name = names[index.live[row_id]]
        if name:
            kinds_by_name[name] = tuple(dict.fromkeys((*kinds_by_name.get(name, ()), *kinds)))
    return kinds_by_name


def _group_names(frame: pd.DataFrame) -> list[str | None]:
    """줄마다 모듈 묶음(둘 이상) 이름, 아니면 None."""
    if not len(frame):
        return []
    return [name if isinstance(name, str) else None for name in module_group_rows(frame).tolist()]


def sheet_edit_data(
    sheet: Mapping[str, Any],
    master: pd.DataFrame,
    *,
    context: GridContext,
    locks: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    """배치 편집기 data `sheetEdit` — 창 칸 고치기의 칸 꼴 · 잠금 · 원래 글(epoch 밖).

    - ``cols`` 고칠 수 있는 칸(창 차례), ``kinds`` 칸마다 설비 마스터 표 칸 정의(꼴 · 고를 값 ·
      빈 값 허용 · 제안), ``fixed`` 창에서만 잠그는 칸 → 까닭.
    - ``locks`` 잠금 갈래 → 그 갈래가 잠그는 고칠 칸, ``reasons`` 갈래 → 까닭(표와 같은 글).
    - ``rows`` 창 줄 id → ``{"t": 고칠 칸마다 원래 글(자르지 않음 — `cell_text`), "k": 잠금 갈래,
      "g": 모듈 묶음 이름}``. 편집본의 한 줄로 이어지지 않는 창 줄은 싣지 않는다 — 브라우저가
      모든 칸을 ``missing`` 까닭으로 잠근다.
    - ``shared`` 고칠 칸 가운데 묶음이 같이 바뀌는 칸(`UNIT_SHARED_COLUMNS`), ``groups`` 모듈 묶음
      이름 → 줄 수(편집본 전체 — 숨은 모듈 포함). 「묶음」 표지 풍선이 쓴다.
    """
    columns = [str(column.get("name")) for column in sheet.get("columns") or ()]
    editable = editable_columns(columns)
    specs = {str(item["name"]): item for item in columns_payload(context)}
    kinds = {
        column: {
            key: specs[column][key]
            for key in ("kind", "options", "blank", "suggest")
            if key in specs[column]
        }
        for column in editable
    }
    fixed = {
        column: SHEET_FIXED_LOCKS.get(column, COMPUTED_LOCK_REASON)
        for column in columns
        if column not in editable
    }
    lock_columns = {
        kind: [column for column in LOCK_SETS[kind] if column in editable] for kind in LOCK_SETS
    }
    lock_columns = {kind: names for kind, names in lock_columns.items() if names}
    reasons = {
        kind: reason for kind, reason in context.lock_reasons().items() if kind in lock_columns
    }
    frame = master.reset_index(drop=True)
    names = _unit_names(frame)
    found = _positions(names)
    groups = _group_names(frame)
    sizes: dict[str, int] = {}
    for name in groups:
        if name is not None:
            sizes[name] = sizes.get(name, 0) + 1
    rows: dict[str, dict[str, Any]] = {}
    for row in sheet.get("rows") or ():
        unit = str(row.get("id") or "")
        hits = found.get(unit, [])
        if len(hits) != 1:
            continue
        position = hits[0]
        values = frame.iloc[position]
        rows[unit] = {
            "t": [cell_text(values[column]) for column in editable],
            "k": [kind for kind in locks.get(unit, ()) if kind in lock_columns],
            "g": groups[position],
        }
    shown_groups = {str(item["g"]) for item in rows.values() if item["g"] is not None}
    return {
        "cols": list(editable),
        "kinds": kinds,
        "fixed": fixed,
        "locks": lock_columns,
        "reasons": reasons,
        "missing": MISSING_LOCK_REASON,
        "rows": rows,
        "shared": [column for column in editable if column in UNIT_SHARED_COLUMNS],
        "groups": {name: sizes[name] for name in sorted(shown_groups)},
    }


@dataclass(frozen=True)
class CellVerdict:
    """고친 칸 하나의 판정 — `rule` 이 비었으면 받음, 아니면 막음(규칙 코드 또는 창 갈래)과 문구."""

    cell: SheetCell
    rule: str = ""
    message: str = ""

    @property
    def blocked(self) -> bool:
        return bool(self.rule)


@dataclass(frozen=True)
class SheetCheck:
    """고친 칸 판정 한 번(`check_sheet_cells`).

    - `verdicts` — 넘긴 칸 차례의 판정.
    - `master` — 받은 칸(과 따라간 형제)을 얹은 **새** 프레임(줄 자리 0부터). 막힌 칸이 있으면 쓰지
      않는다(`ok` 일 때만 편집본에 넣는다).
    - `written` — 쓴 (설비명, 칸) — 고친 줄과 따라간 형제 줄(막히지 않은 쓰기만).
    - `followers` — 사람이 고치지 않았지만 묶음이라 같이 바뀌는 (형제 설비명, 칸, 화면 글자).
    """

    verdicts: tuple[CellVerdict, ...]
    master: pd.DataFrame
    written: tuple[tuple[str, str], ...] = ()
    followers: tuple[tuple[str, str, str], ...] = ()

    @property
    def blocked(self) -> tuple[CellVerdict, ...]:
        return tuple(verdict for verdict in self.verdicts if verdict.blocked)

    @property
    def ok(self) -> bool:
        return not self.blocked


def _issue_key(issue: MasterIssue) -> tuple[int, str, str]:
    return (issue.position, issue.column, issue.rule)


def _lock_message(
    write: GroupWrite,
    locked: Sequence[tuple[int, str]],
    *,
    names: Sequence[str],
    reasons: Mapping[str, str],
) -> tuple[str, str]:
    """잠긴 줄(`(줄 자리, 잠금 갈래)`, 쓸 줄 차례)에 닿은 쓰기의 (갈래, 문구) — 첫 잠긴 줄이 고친
    줄이면 그 잠금 까닭, 형제 줄이면 묶음째 거절이다. 묶음째 거절 글은 설비 마스터 표와 한 벌
    (`GROUP_LOCKED_TOAST` — 수는 잠긴 형제 줄 수)이고 첫 잠긴 형제를 붙인다."""
    position, kind = locked[0]
    reason = reasons.get(kind, "잠긴 칸입니다")
    if position in write.asked or write.group is None:
        return RULE_LOCKED, reason
    siblings = [p for p, _ in locked if p not in write.asked]
    text = GROUP_LOCKED_TOAST.format(group=write.group, count=len(siblings), column=write.column)
    return RULE_SIBLING_LOCKED, f"{text}({reason}) · 잠긴 줄 {names[position]}"


def check_sheet_cells(
    master: pd.DataFrame,
    cells: Sequence[SheetCell],
    *,
    columns: Sequence[str],
    context: GridContext,
    locks: Mapping[str, tuple[str, ...]],
    floor_canvases: FloorCanvasMap | None = None,
    today: date | None = None,
) -> SheetCheck:
    """「호기 정보」 창에서 고친 칸을 판정하고 받은 칸을 얹은 새 프레임을 낸다(편집본은 그대로).

    차례(설계 5-6):

    1. 창에서만 잠그는 칸(`SHEET_FIXED_LOCKS`)과 창에 없는 · 계약 밖 칸(`columns` 는 창 칸)을 먼저
       거부한다. 편집본의 한 줄로 이어지지 않는 호기(같은 이름 둘 · 없음)도 거부한다.
    2. 글을 `coerce_master_cell` 로 다듬는다 — 못 다듬으면 설비 마스터 칸 초안과 같은 문구로 막는다.
    3. `plan_group_writes` 로 쓸 줄(고친 줄 + 같이 바뀌는 칸의 묶음 형제 — 편집본 전체)을 계획한다.
       계획한 줄 하나라도 같은 잠금 갈래(`locks` × `LOCK_SETS`)에 걸리면 그 쓰기를 통째로 막는다.
       같은 묶음 · 같은 칸에 다른 값이 오면(`split`) 그 칸들을 막는다 — 어느 값이 맞는지 고르지
       않는다.
    4. 받은 칸을 모두 얹은 마지막 상태와 고치기 앞에 같은 규칙 표(`equipment_master_issues`, 표와
       같은 인자 `floor_canvases` · `today`)를 돌려 쓴 줄에 **새로** 생긴 막는 결과를 그 쓰기의 고친
       칸에 짚는다 — 결과 칸이 쓴 칸이면 그 칸, 아니면 그 줄에 쓴 칸 전부다.

    `locks` 는 설비명 → 잠금 갈래(`unit_lock_kinds`), `context` 는 표와 같은 조건(잠금 까닭)이다.
    규칙 표가 읽지 못하는 표(계약 칸 없음)는 `equipment_master_issues` 의 `ValueError` 그대로다.
    """
    frame = master.reset_index(drop=True)
    names = _unit_names(frame)
    found = _positions(names)
    allowed = set(editable_columns(columns))
    reasons = context.lock_reasons()
    verdicts: list[CellVerdict | None] = [None] * len(cells)
    staged: list[tuple[int, int, str, object]] = []
    for at, cell in enumerate(cells):
        hits = found.get(cell.unit, [])
        if cell.column in SHEET_FIXED_LOCKS:
            verdicts[at] = CellVerdict(cell, RULE_FIXED, SHEET_FIXED_LOCKS[cell.column])
        elif cell.column not in allowed:
            verdicts[at] = CellVerdict(
                cell, RULE_COLUMN, f"{cell.column} 칸은 이 창에서 고치지 않습니다"
            )
        elif len(hits) != 1:
            verdicts[at] = CellVerdict(cell, RULE_UNIT, MISSING_LOCK_REASON)
        else:
            parsed = coerce_master_cell(cell.column, cell.text)
            if isinstance(parsed, CellParseError):
                verdicts[at] = CellVerdict(cell, parsed.rule, parsed.message)
            else:
                staged.append((at, hits[0], cell.column, parsed))
    plan = plan_group_writes(
        frame, [(position, column, value) for _, position, column, value in staged]
    )
    groups = _group_names(frame)
    split = set(plan.split)

    def asked_cells(write: GroupWrite) -> list[int]:
        return [
            at
            for at, position, column, _ in staged
            if column == write.column and position in write.asked
        ]

    accepted: list[tuple[GroupWrite, list[int]]] = []
    for write in plan.writes:
        owners = asked_cells(write)
        group = groups[write.rows[0]] if write.group is None and write.rows else write.group
        if write.group is None and group is not None and (group, write.column) in split:
            for at in owners:
                verdicts[at] = CellVerdict(
                    cells[at],
                    RULE_SPLIT,
                    f"{group} 묶음 {write.column} — 같은 묶음 모듈에 서로 다른 값을 넣었습니다",
                )
            continue
        locked = [
            (position, kind)
            for position in write.rows
            for kind in [
                next(
                    (k for k in locks.get(names[position], ()) if write.column in LOCK_SETS[k]),
                    None,
                )
            ]
            if kind is not None
        ]
        if locked:
            refusal = _lock_message(write, locked, names=names, reasons=reasons)
            for at in owners:
                verdicts[at] = CellVerdict(cells[at], *refusal)
            continue
        accepted.append((write, owners))
    after = frame.copy()
    for write, _ in accepted:
        for position in write.rows:
            store_cell(after, position, write.column, write.value)
    if accepted:
        before_keys = {
            _issue_key(issue)
            for issue in equipment_master_issues(frame, floor_canvases=floor_canvases, today=today)
            if issue.blocking
        }
        touched = {position for write, _ in accepted for position in write.rows}
        fresh = [
            issue
            for issue in equipment_master_issues(after, floor_canvases=floor_canvases, today=today)
            if issue.blocking and issue.position in touched and _issue_key(issue) not in before_keys
        ]
        for issue in fresh:
            on_row = [(write, owners) for write, owners in accepted if issue.position in write.rows]
            same = [(write, owners) for write, owners in on_row if write.column == issue.column]
            for _write, owners in same or on_row:
                for at in owners:
                    if verdicts[at] is not None:
                        continue
                    cell = cells[at]
                    message = (
                        issue.message
                        if (issue.unit, issue.column) == (cell.unit, cell.column)
                        else f"{issue.unit} {issue.column} — {issue.message}"
                    )
                    verdicts[at] = CellVerdict(cell, issue.rule, message)
    final = tuple(
        verdict if verdict is not None else CellVerdict(cells[at])
        for at, verdict in enumerate(verdicts)
    )
    kept = [
        write
        for write, owners in accepted
        if owners and all(not final[at].blocked for at in owners)
    ]
    written = tuple(
        dict.fromkeys((names[position], write.column) for write in kept for position in write.rows)
    )
    followers = tuple(
        (names[position], write.column, cell_text(write.value))
        for write in kept
        for position in write.rows
        if position not in write.asked
    )
    return SheetCheck(verdicts=final, master=after, written=written, followers=followers)


def blocked_line(verdict: CellVerdict) -> str:
    """막힌 칸 한 줄(알림 글) — 「{설비명} {칸} {친 글} — {까닭}」(무엇을 · 어디서)."""
    cell = verdict.cell
    text = cell.text.strip() or BLANK_TEXT
    return f"{cell.unit} {cell.column} {text} — {verdict.message}"


def verdict_payload(check: SheetCheck) -> dict[str, Any]:
    """판정의 브라우저 꼴 — ``{"blocked": [{id, col, text, rule, message}], "follow": [{id, col,
    text}]}``(편집기 data `sheetVerdict` · `sheetRefused` 의 몸). 막힌 칸의 `text` 는 판정한
    글이다 — 브라우저는 그 칸을 다시 고치면 다음 판정까지 빨강을 걷는다."""
    return {
        "blocked": [
            {
                "id": verdict.cell.unit,
                "col": verdict.cell.column,
                "text": verdict.cell.text,
                "rule": verdict.rule,
                "message": verdict.message,
            }
            for verdict in check.blocked
        ],
        "follow": [
            {"id": unit, "col": column, "text": text} for unit, column, text in check.followers
        ],
    }


def blocked_keys(payload: Mapping[str, Any] | None) -> frozenset[tuple[str, str, str, str]]:
    """판정 몸(`verdict_payload`)의 막힌 칸 열쇠(설비명, 칸, 친 글, 규칙) — 「새로 막힌 칸」 만 알릴
    때 앞 판정과 견준다(같은 칸에 다른 글을 다시 넣어 막히면 새로 막힌 것이다)."""
    if not isinstance(payload, Mapping):
        return frozenset()
    keys: set[tuple[str, str, str, str]] = set()
    for item in payload.get("blocked") or ():
        if isinstance(item, Mapping):
            keys.add(
                (
                    str(item.get("id")),
                    str(item.get("col")),
                    str(item.get("text")),
                    str(item.get("rule")),
                )
            )
    return frozenset(keys)


def sheet_columns_of(sheet: Mapping[str, Any] | None) -> tuple[str, ...]:
    """창 표(`unit_sheet` 꼴)의 칸 이름(창 차례)."""
    if not isinstance(sheet, Mapping):
        return ()
    return tuple(str(column.get("name")) for column in sheet.get("columns") or ())


def sheet_ids_of(sheet: Mapping[str, Any] | None) -> frozenset[str]:
    """창 표의 줄 id(설비명) — 적용값 · 확인 요청의 `cells` 를 읽을 때 쓴다."""
    if not isinstance(sheet, Mapping):
        return frozenset()
    return frozenset(str(row.get("id")) for row in sheet.get("rows") or () if row.get("id"))


def changed_cell_count(
    cells: Collection[tuple[str, str]],
    buffer: pd.DataFrame,
    saved: pd.DataFrame,
    origins: Mapping[str, str],
) -> int:
    """창에서 고쳐 적용한 칸 가운데 지금도 저장본과 다른 칸 수 — 저장 상자 「호기 정보 칸 n건」.

    `cells` 는 (지금 설비명, 칸), `origins` 는 지금 이름 → 저장본 이름(저장 안 한 이름 바꿈)이다.
    견줌은 표의 「바뀐 칸」 과 같은 화면 글자(`cell_text`)다. 저장본에 없는 호기(새 호기)는 칸마다
    다르다고 센다."""
    if not cells:
        return 0
    now_frame = buffer.reset_index(drop=True)
    old_frame = saved.reset_index(drop=True)
    now = {name: hits[0] for name, hits in _positions(_unit_names(now_frame)).items()}
    before = {name: hits[0] for name, hits in _positions(_unit_names(old_frame)).items()}
    count = 0
    for unit, column in cells:
        position = now.get(unit)
        if position is None or column not in now_frame.columns:
            continue
        text = cell_text(now_frame.iloc[position][column])
        origin = before.get(origins.get(unit, unit))
        if origin is None or column not in old_frame.columns:
            count += 1
        elif cell_text(old_frame.iloc[origin][column]) != text:
            count += 1
    return count
