# Purpose: 범용 편집 그리드의 열 규격·업무 키·값 다듬기·op 반영·되돌리기·변경 목록·되머지를 맡는다.

"""범용 편집 그리드(Components v2 `components/edit_grid.py`)의 서버 쪽 규칙.

**초안은 업무 키 + 월로 둔다.** 줄 번호가 아니라 분류 칸 원값을 `\\x1f` 로 이은 글(`row_keys`)이라
줄 차례(공용 표시순서)가 바뀌어도 같은 칸에 붙는다. 세션에 두는 꼴은
기본형(dict·tuple·float·str)뿐이다 — AGENTS 5장.

- **초안** `DraftState` = ``{"cells": {키: {월: float | None}}, "bad": {키: {월: (적은 글, 오류
  코드)}}}`` 또는 None(고친 것 없음). 양식과 같은 값이 되면 그 칸을 지운다(못 읽은 글도).
- **이력** `HistoryState` = ``{"gen", "undo": [단계…], "redo": [단계…]}``. `gen` 은 이력을 처음 만들
  때 새로 뽑고, 초안을 버리면 이력도 함께 지워져 다음 `gen` 은 다른 값이다 — 그 전에 보낸 op 는
  `gen` 이 달라 버려진다.
- **op** 는 브라우저가 상태 값 `outbox`(``{"mount", "ops"}``)로 보낸다. 칸을 고치는 op
  넷(`write`·`fill`·`clear`·`revert`)은 직사각형 하나(업무 키 × 월)이고 op 하나가 되돌리기 한
  단계다. 되돌리기 40단계.
- **값 다듬기**(`coerce`)는 Python 이 정본이고 브라우저(`eg_pure.js` 의 `parseInput`)는 같은 규칙의
  미리보기다 — `tests/fixtures/edit_grid_cases.json` 의 같은 사례를 둘이 같은 답으로 낸다(쌍둥이
  시험). 표시 형식(`format_value` ↔ `formatValue`)도 같다.
"""

from __future__ import annotations

import math
import re
import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final, Literal, TypeAlias, TypedDict

import numpy as np
import numpy.typing as npt
import pandas as pd

ValueKind = Literal["percent", "fixed", "sig"]

# 업무 키 — 분류 칸 원값(`astype(str)`)을 이 글자로 잇고, 같은 키가 또 나오면 둘째부터 `\x1e<n>` 을
# 붙인다.
KEY_SEPARATOR: Final = "\x1f"
DUPLICATE_SEPARATOR: Final = "\x1e"

OP_NAMES: Final = frozenset({"write", "fill", "clear", "revert", "undo", "redo"})
FILL_DIRECTIONS: Final = frozenset({"down", "up", "right", "left"})
ERROR_CODES: Final = ("num", "finite", "min", "max", "int")

UNDO_LIMIT: Final = 40
# 이력 전체 칸 수(단계마다 줄 × 칸) 상한 — 넘으면 오래된 단계부터 버린다(맨 새 단계는 남긴다).
HISTORY_CELL_LIMIT: Final = 200_000
# `write` 한 op 의 값 칸 수 상한(엑셀 500×30 붙여넣기). 넘는 op 는 버리고 안내한다.
PASTE_CELL_LIMIT: Final = 15_000
# 브라우저가 한 출납에 쌓아 둘 수 있는 값 칸 수, feed 에 싣는 오류 칸 수.
OUTBOX_CELL_LIMIT: Final = 30_000
BAD_LIMIT: Final = 2_000
# 마운트별 마지막 seq 기억 — 최근 마운트 몇 개만 남긴다.
MOUNT_LIMIT: Final = 8

# 이력 칸 상태: 값(float · None=빈칸) · 초안 없음 · 못 읽은 글 (적은 글, 오류 코드).
NO_DRAFT: Final = "\x00"
# 반영 중에만 쓰는 표지 — 그 칸은 그대로 둔다(쓰기 덩어리의 빈 자리·없는 원본).
_KEEP: Final = "\x01"
BadCell: TypeAlias = tuple[str, str]
CellState: TypeAlias = float | None | str | BadCell

# 서버가 짓는 토스트 글(브라우저 글은 `components/edit_grid.texts`).
DROPPED_TOAST: Final = "표가 바뀌기 전에 보낸 편집 {n}개는 버렸습니다 — 다시 고쳐 주세요"
MISSING_ROWS_TOAST: Final = "없는 줄 {n}개는 건너뛰었습니다"
PASTE_LIMIT_TOAST: Final = (
    "한 번에 붙여넣을 수 있는 칸은 {limit}칸입니다 — 큰 표는 「Excel 붙여넣기」 를 쓰세요"
)
UNDO_EMPTY_TOAST: Final = "되돌릴 편집이 없습니다"
REDO_EMPTY_TOAST: Final = "다시 실행할 편집이 없습니다"


# ------------------------------------------------------------------ 열 규격


@dataclass(frozen=True)
class ValueFormat:
    """값 칸의 표시·다듬기 규칙.

    `kind` — percent(분수 0.9875 를 「98.75%」 로) · fixed(천 단위 + 소수 `digits` 자리) ·
    sig(유효숫자 `digits` 자리). `integer` 면 소수는 칸 오류, `blank_zero` 면 빈칸을 0 으로
    다듬는다(설비대수 — 빈칸 = 0)."""

    kind: ValueKind
    digits: int
    integer: bool = False
    min_value: float | None = 0.0
    max_value: float | None = None
    blank_zero: bool = False


@dataclass(frozen=True)
class GridSpec:
    """편집 그리드 표 하나 — op 의 `table`, 제목, 분류(열쇠) 칸, 값(월) 칸, 값 형식, 월 머리
    풍선."""

    table: str
    title: str
    key_columns: tuple[str, ...]
    value_columns: tuple[str, ...]
    fmt: ValueFormat
    value_help: str | None = None


def format_payload(fmt: ValueFormat) -> dict[str, Any]:
    """브라우저가 받는 값 형식(`fmt`) — 껍데기와 쌍둥이 시험 사례가 같은 꼴을 쓴다."""
    return {
        "kind": fmt.kind,
        "digits": fmt.digits,
        "int": fmt.integer,
        "min": fmt.min_value,
        "max": fmt.max_value,
        "blankZero": fmt.blank_zero,
    }


# ------------------------------------------------------------------ 업무 키


def _joined_keys(frame: pd.DataFrame, key_columns: Sequence[str]) -> pd.Series:
    if not key_columns:
        raise ValueError("편집 그리드에는 분류 칸이 하나 이상 있어야 합니다")
    joined = frame[key_columns[0]].astype(str)
    for column in key_columns[1:]:
        joined = joined + KEY_SEPARATOR + frame[column].astype(str)
    return joined.reset_index(drop=True)


def key_duplicates(frame: pd.DataFrame, key_columns: Sequence[str]) -> tuple[tuple[int, int], ...]:
    """같은 업무 키가 둘 이상인 줄 — (줄, n) n = 1, 2, …(첫 줄은 꼬리표 없음). 껍데기 `dupes` 로
    간다.
    """
    joined = _joined_keys(frame, key_columns)
    counts = joined.groupby(joined, sort=False).cumcount().to_numpy()
    positions = np.flatnonzero(counts > 0)
    return tuple((int(row), int(counts[row])) for row in positions)


def row_keys(frame: pd.DataFrame, key_columns: Sequence[str]) -> tuple[str, ...]:
    """줄마다 업무 키 — 분류 칸 `astype(str)` 을 `\\x1f` 로 잇고 같은 키의 둘째부터 `\\x1e<n>` 을
    붙인다."""
    keys = _joined_keys(frame, key_columns).tolist()
    for row, count in key_duplicates(frame, key_columns):
        keys[row] = f"{keys[row]}{DUPLICATE_SEPARATOR}{count}"
    return tuple(str(key) for key in keys)


@dataclass(frozen=True)
class GridIndex:
    """양식 색인 — 업무 키 → 줄, 값 행렬(float64, NaN = 빈칸), 월 → 칸. 캐시에서 온다(op 반영·feed
    짓기)."""

    table: str
    keys: tuple[str, ...]
    rows: Mapping[str, int]
    values: npt.NDArray[np.float64]
    months: tuple[str, ...]
    cols: Mapping[str, int]

    def template_value(self, row: int, col: int) -> float | None:
        value = float(self.values[row, col])
        return None if math.isnan(value) else value


def month_matrix(frame: pd.DataFrame, columns: Sequence[str]) -> npt.NDArray[np.float64]:
    """값 칸을 float64 행렬로(읽지 못하는 값·결측은 NaN)."""
    if not columns:
        return np.empty((len(frame), 0), dtype="float64")
    numeric = frame[list(columns)].apply(pd.to_numeric, errors="coerce")
    matrix: npt.NDArray[np.float64] = numeric.to_numpy(dtype="float64", na_value=np.nan)
    return matrix


def build_index(template: pd.DataFrame, spec: GridSpec) -> GridIndex:
    """양식(분류 칸 + 월 칸 표)의 색인. 칸이 모자라면 KeyError."""
    missing = [
        column
        for column in (*spec.key_columns, *spec.value_columns)
        if column not in template.columns
    ]
    if missing:
        raise KeyError(f"{spec.title} 양식에 없는 칸: {', '.join(missing)}")
    keys = row_keys(template, spec.key_columns)
    return GridIndex(
        table=spec.table,
        keys=keys,
        rows={key: row for row, key in enumerate(keys)},
        values=month_matrix(template, spec.value_columns),
        months=tuple(spec.value_columns),
        cols={month: col for col, month in enumerate(spec.value_columns)},
    )


# ------------------------------------------------------------------ 값 다듬기

# 앞뒤에서 걷는 공백 — 브라우저(`parseInput`)와 같은 글자 묶음이다(Python `strip()` 과 JS `trim()`
# 은
# 걷는 글자가 조금씩 달라 둘 다 쓰지 않는다).
_STRIP: Final = " \t\n\r\f\v 　"
_NUMBER: Final = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
# 천 단위 쉼표는 엄격한 세 자리 묶음만 받는다(「1,234.5」 받음, 「1,5」 오류).
_GROUPED: Final = re.compile(r"[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]*)?")
_NONFINITE: Final = re.compile(r"[+-]?(?:inf|infinity|nan)", re.IGNORECASE)


@dataclass(frozen=True)
class Coerced:
    """다듬은 값 — 받은 값(빈칸 None, `blank_zero` 면 0.0), 오류 코드, 오류일 때 적은 글."""

    value: float | None
    error: str | None = None
    text: str | None = None


def number_text(value: float) -> str:
    """수의 글(브라우저 `String(number)` 와 같은 꼴 — 정수면 소수점 없이)."""
    if math.isfinite(value) and value == int(value) and abs(value) < 1e16:
        return str(int(value))
    return repr(value)


def _parse_number(body: str, *, percent: bool = False) -> tuple[float | None, str | None]:
    """수 글 → 값. `percent` 면 소수점을 두 자리 옮긴 글로 읽는다(「99.99%」 → 0.9999 — 100 으로
    나누면 0.9998999… 이 된다)."""
    if "," in body:
        if not _GROUPED.fullmatch(body):
            return None, "num"
        body = body.replace(",", "")
    if _NONFINITE.fullmatch(body):
        return None, "finite"
    if not _NUMBER.fullmatch(body):
        return None, "num"
    if percent:
        number = float(body + "e-2") if "e" not in body.lower() else float(body) / 100
    else:
        number = float(body)
    if not math.isfinite(number):
        return None, "finite"
    return number, None


def coerce(raw: object, fmt: ValueFormat, *, template_value: float | None) -> Coerced:
    """칸에 적은 글(또는 수)을 그 표의 값으로 다듬는다(규칙은 명세 1-2 의 12).

    빈 글은 빈칸(None — `blank_zero` 면 0.0). 수는 유한한 값만, 천 단위 쉼표는 세 자리 묶음만,
    `percent` 표만 「85%」 → 0.85. 하한·상한·정수 검사는 양식과 같은 값이면 하지 않는다(양식에 이미
    있는 범위 밖 값을 다시 적어도 오류가 아니다). 오류면 값은 None 이고 적은 글이 남는다."""
    if raw is None:
        return Coerced(0.0 if fmt.blank_zero else None)
    if isinstance(raw, bool):
        return Coerced(None, "num", str(raw))
    if isinstance(raw, (int, float)):
        number = float(raw)
        text = number_text(number) if math.isfinite(number) else str(raw)
        if not math.isfinite(number):
            return Coerced(None, "finite", text)
    elif isinstance(raw, str):
        text = raw
        body = raw.strip(_STRIP)
        if not body:
            return Coerced(0.0 if fmt.blank_zero else None)
        percent = fmt.kind == "percent" and body.endswith("%")
        if percent:
            body = body[:-1].rstrip(_STRIP)
        parsed, error = _parse_number(body, percent=percent)
        if parsed is None:
            return Coerced(None, error or "num", text)
        number = parsed
    else:
        return Coerced(None, "num", str(raw))
    number += 0.0
    if template_value is not None and number == template_value:
        return Coerced(number)
    if fmt.min_value is not None and number < fmt.min_value:
        return Coerced(None, "min", text)
    if fmt.max_value is not None and number > fmt.max_value:
        return Coerced(None, "max", text)
    if fmt.integer and number != math.floor(number):
        return Coerced(None, "int", text)
    return Coerced(number)


# ------------------------------------------------------------------ 표시 형식


def _group(digits: str) -> str:
    """정수 자리 글에 천 단위 쉼표."""
    head = len(digits) % 3 or 3
    parts = [digits[:head]] + [digits[at : at + 3] for at in range(head, len(digits), 3)]
    return ",".join(parts)


def _grouped_text(text: str) -> str:
    sign = "-" if text.startswith("-") else ""
    body = text[1:] if sign else text
    whole, dot, fraction = body.partition(".")
    return sign + _group(whole) + (dot + fraction if dot else "")


def _strip_zeros(text: str) -> str:
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")


def _fixed(value: float, digits: int) -> str:
    """소수 `digits` 자리 — 이진 값 그대로에서 반올림(같으면 0 에서 먼 쪽 — JS `toFixed` 와
    같다)."""
    quantum = Decimal(1).scaleb(-digits)
    return format(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _significant(value: float, digits: int) -> str:
    """유효숫자 `digits` 자리(`%g` 꼴 — 지수 -4 이상 `digits` 미만이면 고정 소수, 아니면 e±XX)."""
    if value == 0:
        return "0"
    exact = Decimal(abs(value))
    exponent = exact.adjusted()
    rounded = exact.quantize(Decimal(1).scaleb(exponent - digits + 1), rounding=ROUND_HALF_UP)
    if rounded.adjusted() != exponent:
        exponent = rounded.adjusted()
        rounded = exact.quantize(Decimal(1).scaleb(exponent - digits + 1), rounding=ROUND_HALF_UP)
    sign = "-" if value < 0 else ""
    if -4 <= exponent < digits:
        return sign + _grouped_text(_strip_zeros(format(rounded, "f")))
    mantissa = rounded.scaleb(-exponent)
    body = _strip_zeros(format(mantissa.quantize(Decimal(1).scaleb(-(digits - 1))), "f"))
    return f"{sign}{body}e{'+' if exponent >= 0 else '-'}{abs(exponent):02d}"


def format_value(value: float | None, fmt: ValueFormat) -> str:
    """칸에 보이는 글(브라우저 `formatValue` 와 같은 답 — 쌍둥이 시험). 빈칸은 빈 글."""
    if value is None or math.isnan(value):
        return ""
    value += 0.0
    if fmt.kind == "percent":
        return _grouped_text(_strip_zeros(_fixed(value * 100, fmt.digits))) + "%"
    if fmt.kind == "fixed":
        return _grouped_text(_fixed(value, fmt.digits))
    return _significant(value, fmt.digits)


# ------------------------------------------------------------------ 초안·이력


class DraftState(TypedDict):
    cells: dict[str, dict[str, float | None]]
    bad: dict[str, dict[str, BadCell]]


class Step(TypedDict):
    rows: tuple[str, ...]
    cols: tuple[str, ...]
    before: tuple[tuple[CellState, ...], ...]
    after: tuple[tuple[CellState, ...], ...]


class HistoryState(TypedDict):
    gen: str
    undo: list[Step]
    redo: list[Step]


def new_history() -> HistoryState:
    """새 이력 — `gen` 은 그때마다 새로 뽑는다."""
    return {"gen": secrets.token_hex(4), "undo": [], "redo": []}


def history_from(value: object) -> HistoryState | None:
    """세션 값을 이력으로(꼴이 다르면 None)."""
    if not isinstance(value, Mapping):
        return None
    gen, undo, redo = value.get("gen"), value.get("undo"), value.get("redo")
    if not isinstance(gen, str) or not isinstance(undo, list) or not isinstance(redo, list):
        return None
    return {"gen": gen, "undo": list(undo), "redo": list(redo)}


def draft_from(value: object) -> DraftState | None:
    """세션 값을 초안으로(비었거나 꼴이 다르면 None)."""
    if not isinstance(value, Mapping):
        return None
    cells, bad = value.get("cells"), value.get("bad")
    if not isinstance(cells, Mapping) or not isinstance(bad, Mapping):
        return None
    draft: DraftState = {
        "cells": {str(key): dict(row) for key, row in cells.items() if isinstance(row, Mapping)},
        "bad": {str(key): dict(row) for key, row in bad.items() if isinstance(row, Mapping)},
    }
    return draft if draft["cells"] or draft["bad"] else None


def _cell_state(draft: DraftState, key: str, month: str) -> CellState:
    bad_row = draft["bad"].get(key)
    if bad_row is not None and month in bad_row:
        text, code = bad_row[month]
        return (text, code)
    row = draft["cells"].get(key)
    if row is not None and month in row:
        return row[month]
    return NO_DRAFT


def _set_cell(draft: DraftState, key: str, month: str, state: CellState) -> None:
    for book in (draft["cells"], draft["bad"]):
        row = book.get(key)
        if row is not None and month in row:
            del row[month]
            if not row:
                del book[key]
    if isinstance(state, tuple):
        draft["bad"].setdefault(key, {})[month] = (state[0], state[1])
    elif state != NO_DRAFT:
        value = state if state is None or isinstance(state, float) else None
        draft["cells"].setdefault(key, {})[month] = value


def _state_of(coerced: Coerced, template_value: float | None) -> CellState:
    """다듬은 값 → 칸 상태. 양식과 같은 값이면 초안 없음."""
    if coerced.error is not None:
        return (coerced.text or "", coerced.error)
    if coerced.value == template_value:
        return NO_DRAFT
    return coerced.value


# ------------------------------------------------------------------ op


@dataclass(frozen=True)
class Op:
    """출납에서 고른 op 하나. `kind` 가 "bad" 면 꼴이 틀려 반영하지 않고 ack 만 한다."""

    mount: str
    seq: int
    at: float
    table: str
    gen: str
    kind: str
    rows: tuple[str, ...] = ()
    cols: tuple[str, ...] = ()
    values: tuple[tuple[object, ...], ...] = ()
    src_rows: tuple[str, ...] = ()
    src_cols: tuple[str, ...] = ()
    direction: str = ""


def _seq(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _texts(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _cell_value(value: object) -> bool:
    return value is None or (isinstance(value, (str, int, float)) and not isinstance(value, bool))


def _matrix(value: object) -> tuple[tuple[object, ...], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    lines: list[tuple[object, ...]] = []
    for line in value:
        if not isinstance(line, list) or not all(_cell_value(item) for item in line):
            return None
        lines.append(tuple(line))
    return tuple(lines)


def _parse_op(mount: str, raw: Mapping[str, Any]) -> Op | None:
    seq = _seq(raw.get("seq"))
    if seq is None:
        return None
    at = raw.get("at")
    moment = float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else 0.0
    table, gen, kind = raw.get("table"), raw.get("gen"), raw.get("op")

    def make(name: str, **parts: Any) -> Op:
        return Op(
            mount=mount,
            seq=seq,
            at=moment,
            table=table if isinstance(table, str) else "",
            gen=gen if isinstance(gen, str) else "",
            kind=name,
            **parts,
        )

    if not isinstance(table, str) or not isinstance(gen, str) or kind not in OP_NAMES:
        return make("bad")
    if kind in ("undo", "redo"):
        return make(str(kind))
    rows, cols = _texts(raw.get("rows")), _texts(raw.get("cols"))
    if rows is None or cols is None:
        return make("bad")
    if kind == "write":
        values = _matrix(raw.get("values"))
        return make("bad") if values is None else make("write", rows=rows, cols=cols, values=values)
    if kind == "fill":
        src = raw.get("src")
        direction = raw.get("dir")
        if not isinstance(src, Mapping) or direction not in FILL_DIRECTIONS:
            return make("bad")
        src_rows, src_cols = _texts(src.get("rows")), _texts(src.get("cols"))
        if not src_rows or not src_cols:
            return make("bad")
        return make(
            "fill",
            rows=rows,
            cols=cols,
            src_rows=src_rows,
            src_cols=src_cols,
            direction=str(direction),
        )
    return make(str(kind), rows=rows, cols=cols)


def parse_outbox(value: object) -> tuple[str, list[Op]] | None:
    """상태 값 `outbox`(``{"mount", "ops": [...]}``)의 꼴을 거른다. seq 가 없는 op 는 버리고,
    나머지가
    틀린 op 는 `kind="bad"` 로 남겨 ack 만 받게 한다(브라우저가 다시 보내지 않게)."""
    if not isinstance(value, Mapping):
        return None
    mount, ops = value.get("mount"), value.get("ops")
    if not isinstance(mount, str) or not mount or not isinstance(ops, list):
        return None
    parsed = [
        op for raw in ops if isinstance(raw, Mapping) and (op := _parse_op(mount, raw)) is not None
    ]
    return mount, parsed


def new_ops(
    outboxes: Mapping[str, object], applied: Mapping[str, int]
) -> tuple[list[Op], dict[str, int]]:
    """출납들(호스트 key → 상태 값)에서 마운트별 마지막 seq 보다 큰 op 만 `(at, mount, seq)` 차례로.

    같은 출납이 여러 회차에 다시 와도 한 번이다. 돌려준 기억은 이번에 본 마운트를 맨 뒤로 옮기고
    `MOUNT_LIMIT` 을 넘으면 오래된 것부터 잊는다."""
    memory = dict(applied)
    picked: list[Op] = []
    for outbox in outboxes.values():
        parsed = parse_outbox(outbox)
        if parsed is None:
            continue
        mount, ops = parsed
        last = memory.get(mount, 0)
        fresh = [op for op in ops if op.seq > last]
        picked.extend(fresh)
        memory.pop(mount, None)
        memory[mount] = max([last, *(op.seq for op in fresh)])
    while len(memory) > MOUNT_LIMIT:
        memory.pop(next(iter(memory)))
    picked.sort(key=lambda op: (op.at, op.mount, op.seq))
    return picked, memory


# ------------------------------------------------------------------ op 반영


@dataclass
class ApplyResult:
    """op 반영 결과 — 새 초안·이력, 마운트별 반영한 마지막 seq, 토스트 글, 초안이 바뀌었는가."""

    draft: DraftState | None
    history: HistoryState
    acks: dict[str, int] = field(default_factory=dict)
    toasts: list[str] = field(default_factory=list)
    changed: bool = False


@dataclass
class _Tally:
    dropped: int = 0
    missing_rows: int = 0
    skipped_cols: int = 0
    too_big: int = 0
    undo_empty: int = 0
    redo_empty: int = 0


def _rect(
    index: GridIndex, rows: Sequence[str], cols: Sequence[str], tally: _Tally
) -> tuple[list[tuple[int, str, int]], list[tuple[int, str, int]]]:
    """op 의 줄·칸에서 양식에 있는 것만 (op 안 자리, 이름, 양식 자리). 같은 이름은 한 번."""
    seen_rows: set[str] = set()
    picked_rows: list[tuple[int, str, int]] = []
    for at, key in enumerate(rows):
        row = index.rows.get(key)
        if row is None:
            tally.missing_rows += 1
        elif key not in seen_rows:
            seen_rows.add(key)
            picked_rows.append((at, key, row))
    seen_cols: set[str] = set()
    picked_cols: list[tuple[int, str, int]] = []
    for at, month in enumerate(cols):
        col = index.cols.get(month)
        if col is None:
            tally.skipped_cols += 1
        elif month not in seen_cols:
            seen_cols.add(month)
            picked_cols.append((at, month, col))
    return picked_rows, picked_cols


def _effective(index: GridIndex, draft: DraftState, key: str, month: str) -> object:
    """지금 칸 값(초안 ∪ 양식) — 채우기 원본. 못 읽은 칸은 그 글."""
    state = _cell_state(draft, key, month)
    if isinstance(state, tuple):
        return state[0]
    if state == NO_DRAFT:
        return index.template_value(index.rows[key], index.cols[month])
    return state


def _fill_source(op: Op, k: int, size: int) -> int:
    """채우기 대상의 k 번째(원본에서 멀어지는 차례) 줄·칸이 가져올 원본 자리."""
    return k % size if op.direction in ("down", "right") else size - 1 - (k % size)


def _new_states(
    index: GridIndex,
    spec: GridSpec,
    draft: DraftState,
    op: Op,
    rows: list[tuple[int, str, int]],
    cols: list[tuple[int, str, int]],
) -> list[list[CellState]]:
    """직사각형 칸마다 새 상태(`_KEEP` 이면 그 칸은 그대로 — 쓰기 덩어리의 빈 자리)."""
    fmt = spec.fmt
    out: list[list[CellState]] = []
    if op.kind == "fill":
        vertical = op.direction in ("down", "up")
        src_rows = list(op.src_rows)
        src_cols = list(op.src_cols)
        if any(key not in index.rows for key in src_rows) or any(
            month not in index.cols for month in src_cols
        ):
            return [[_KEEP] * len(cols) for _ in rows]
    for row_at, _key, row in rows:
        line: list[CellState] = []
        for col_at, _month, col in cols:
            template = index.template_value(row, col)
            if op.kind == "revert":
                line.append(NO_DRAFT)
                continue
            if op.kind == "clear":
                raw: object = ""
            elif op.kind == "write":
                block = op.values[row_at % len(op.values)]
                if not block:
                    line.append(_KEEP)
                    continue
                cell = block[col_at % len(block)]
                if cell is None:
                    line.append(_KEEP)
                    continue
                raw = cell
            else:
                source_key: str | None
                source_month: str | None
                if vertical:
                    source_key = src_rows[_fill_source(op, row_at, len(src_rows))]
                    source_month = src_cols[col_at] if col_at < len(src_cols) else None
                else:
                    source_key = src_rows[row_at] if row_at < len(src_rows) else None
                    source_month = src_cols[_fill_source(op, col_at, len(src_cols))]
                if source_key is None or source_month is None:
                    line.append(_KEEP)
                    continue
                raw = _effective(index, draft, source_key, source_month)
            line.append(_state_of(coerce(raw, fmt, template_value=template), template))
        out.append(line)
    return out


def _value_cells(op: Op) -> int:
    return sum(len(line) for line in op.values)


def _step_cells(step: Step) -> int:
    return len(step["rows"]) * len(step["cols"])


def _push(history: HistoryState, step: Step) -> None:
    history["undo"].append(step)
    del history["undo"][:-UNDO_LIMIT]
    total = sum(_step_cells(item) for item in history["undo"])
    while len(history["undo"]) > 1 and total > HISTORY_CELL_LIMIT:
        total -= _step_cells(history["undo"].pop(0))
    history["redo"].clear()


def _apply_cells(
    index: GridIndex,
    spec: GridSpec,
    draft: DraftState,
    history: HistoryState,
    op: Op,
    tally: _Tally,
) -> bool:
    rows, cols = _rect(index, op.rows, op.cols, tally)
    if not rows or not cols:
        return False
    states = _new_states(index, spec, draft, op, rows, cols)
    before: list[tuple[CellState, ...]] = []
    after: list[tuple[CellState, ...]] = []
    changed = False
    for (_, key, _), line in zip(rows, states, strict=True):
        old_line: list[CellState] = []
        new_line: list[CellState] = []
        for (_, month, _), state in zip(cols, line, strict=True):
            old = _cell_state(draft, key, month)
            new = old if state == _KEEP else state
            old_line.append(old)
            new_line.append(new)
            if new != old:
                _set_cell(draft, key, month, new)
                changed = True
        before.append(tuple(old_line))
        after.append(tuple(new_line))
    if changed:
        _push(
            history,
            {
                "rows": tuple(key for _, key, _ in rows),
                "cols": tuple(month for _, month, _ in cols),
                "before": tuple(before),
                "after": tuple(after),
            },
        )
    return changed


def _replay(index: GridIndex, draft: DraftState, step: Step, side: str) -> None:
    states = step["before"] if side == "before" else step["after"]
    for key, line in zip(step["rows"], states, strict=True):
        if key not in index.rows:
            continue
        for month, state in zip(step["cols"], line, strict=True):
            if month in index.cols:
                _set_cell(draft, key, month, state)


def _apply_history(
    index: GridIndex, draft: DraftState, history: HistoryState, kind: str, tally: _Tally
) -> bool:
    source = history["undo"] if kind == "undo" else history["redo"]
    target = history["redo"] if kind == "undo" else history["undo"]
    if not source:
        if kind == "undo":
            tally.undo_empty += 1
        else:
            tally.redo_empty += 1
        return False
    step = source.pop()
    _replay(index, draft, step, "before" if kind == "undo" else "after")
    target.append(step)
    return True


def _copy_draft(draft: DraftState | None) -> DraftState:
    if draft is None:
        return {"cells": {}, "bad": {}}
    return {
        "cells": {key: dict(row) for key, row in draft["cells"].items()},
        "bad": {key: dict(row) for key, row in draft["bad"].items()},
    }


def _toasts(tally: _Tally) -> list[str]:
    toasts: list[str] = []
    if tally.dropped:
        toasts.append(DROPPED_TOAST.format(n=f"{tally.dropped:,}"))
    if tally.too_big:
        toasts.append(PASTE_LIMIT_TOAST.format(limit=f"{PASTE_CELL_LIMIT:,}"))
    if tally.missing_rows:
        toasts.append(MISSING_ROWS_TOAST.format(n=f"{tally.missing_rows:,}"))
    if tally.undo_empty:
        toasts.append(UNDO_EMPTY_TOAST)
    if tally.redo_empty:
        toasts.append(REDO_EMPTY_TOAST)
    return toasts


def apply_ops(
    index: GridIndex,
    spec: GridSpec,
    draft: DraftState | None,
    history: HistoryState,
    ops: Iterable[Op],
) -> ApplyResult:
    """그 표의 op 를 차례로 초안·이력에 반영한다(받은 초안·이력은 바꾸지 않는다).

    `gen` 이 이력과 다른 op·꼴이 틀린 op·다른 표의 op 는 버리고 수를 토스트로 알린다. 양식에 없는
    줄은 건너뛰고 센다. `write` 의 값 칸이 `PASTE_CELL_LIMIT` 를 넘으면 그 op 를 버린다."""
    work = _copy_draft(draft)
    new: HistoryState = {
        "gen": history["gen"],
        "undo": list(history["undo"]),
        "redo": list(history["redo"]),
    }
    tally = _Tally()
    acks: dict[str, int] = {}
    changed = False
    for op in ops:
        acks[op.mount] = max(acks.get(op.mount, 0), op.seq)
        if op.kind == "bad" or op.table != spec.table or op.gen != new["gen"]:
            tally.dropped += 1
            continue
        if op.kind in ("undo", "redo"):
            changed = _apply_history(index, work, new, op.kind, tally) or changed
            continue
        if op.kind == "write" and _value_cells(op) > PASTE_CELL_LIMIT:
            tally.too_big += 1
            continue
        changed = _apply_cells(index, spec, work, new, op, tally) or changed
    result_draft = work if work["cells"] or work["bad"] else None
    return ApplyResult(result_draft, new, acks, _toasts(tally), changed)


# ------------------------------------------------------------------ 변경 목록·수·되머지


def change_counts(draft: DraftState | None) -> tuple[int, int, int]:
    """(고친 칸, 고친 줄, 오류 칸). 오류 칸도 고친 칸으로 센다."""
    if draft is None:
        return (0, 0, 0)
    values = sum(len(row) for row in draft["cells"].values())
    errors = sum(len(row) for row in draft["bad"].values())
    rows = len(set(draft["cells"]) | set(draft["bad"]))
    return (values + errors, rows, errors)


@dataclass(frozen=True)
class ChangeEntry:
    """「적용 전 변경」 한 줄 — 업무 키·양식 줄, 월·칸, 옛 값, 새 값(오류면 None), 오류(적은 글,
    코드).
    """

    key: str
    row: int
    month: str
    col: int
    before: float | None
    after: float | None
    bad: BadCell | None = None


def _spot(index: GridIndex, key: str, month: str) -> tuple[int, int] | None:
    row, col = index.rows.get(key), index.cols.get(month)
    return None if row is None or col is None else (row, col)


def change_list(
    index: GridIndex, draft: DraftState | None, limit: int | None = None
) -> list[ChangeEntry]:
    """초안의 칸을 양식 줄·칸 차례로(양식에 없는 키·월은 뺀다). `limit` 이 있으면 앞 그만큼."""
    if draft is None:
        return []
    entries: list[ChangeEntry] = []
    for key, value_cells in draft["cells"].items():
        for month, value in value_cells.items():
            spot = _spot(index, key, month)
            if spot is not None:
                row, col = spot
                before = index.template_value(row, col)
                entries.append(ChangeEntry(key, row, month, col, before, value))
    for key, bad_cells in draft["bad"].items():
        for month, (text, code) in bad_cells.items():
            spot = _spot(index, key, month)
            if spot is not None:
                row, col = spot
                before = index.template_value(row, col)
                entries.append(ChangeEntry(key, row, month, col, before, None, (text, code)))
    entries.sort(key=lambda entry: (entry.row, entry.col))
    return entries if limit is None else entries[:limit]


def merge_into_template(
    template: pd.DataFrame, spec: GridSpec, draft: DraftState | None
) -> pd.DataFrame:
    """양식 사본에 초안을 업무 키로 덮는다(빈칸 NaN, 값 칸은 float64). 오류 칸이 있으면 ValueError —
    적용 전에 고칠 칸으로 멈춰야 한다. 줄 차례가 바뀐 양식에서도 같은 업무 키 칸에 붙는다."""
    merged = template.copy()
    if draft is None:
        return merged
    if any(draft["bad"].values()):
        raise ValueError("못 읽은 칸이 남아 있어 양식에 덮을 수 없습니다")
    index = build_index(template, spec)
    matrix = index.values.copy()
    for key, row_cells in draft["cells"].items():
        row = index.rows.get(key)
        if row is None:
            continue
        for month, value in row_cells.items():
            col = index.cols.get(month)
            if col is not None:
                matrix[row, col] = np.nan if value is None else value
    for col, month in enumerate(spec.value_columns):
        merged[month] = matrix[:, col]
    return merged
