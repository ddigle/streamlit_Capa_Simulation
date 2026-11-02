# Purpose: 범용 편집 그리드의 껍데기·feed 꼴(64자 코드·값 사전·줄 RLE)을 짓는다(streamlit 모름).

"""범용 편집 그리드가 브라우저로 보내는 두 data 의 꼴.

- **껍데기**(무거운 요소 `capa_edit_grid` 의 data) = 표 본문(`encode_table` — 분류 칸 사전·줄마다
  고정 폭 코드, 값 사전·줄마다 (값 코드, 길이) RLE) +
  호스트·`baseKey`·글·팔레트·상한(`encode_base`). 표가 같으면 같은 dict 라 Streamlit 이 해시 참조(약
  75 B)로 보낸다 — 편집 회차에는 바뀌지 않는다. 본문은 캐시(`simulation_cache.
  get_edit_grid_base`)에서 오고 팔레트·글은 회차마다 더한다(테마를 바꾸면 껍데기도 바뀐다).
- **feed**(작은 요소 `capa_edit_grid_feed` 의 data) = 초안(줄마다 (코드, 길이) RLE — 0 초안 없음 · 1
  빈칸 · 2 못 읽음 · 3.. 값 사전)·오류 칸·수·ack·토스트·필터. 편집 회차마다 바뀌어도 작다.

코드 글자는 64자(`CODE_ALPHABET`)이고 사전 크기 n 의 코드 폭은 `max(1, ceil(log64 n))` 이다.
브라우저는 `eg_pure.js` 의 `// <eg-codes>` 가 같은 표로 푼다(쌍둥이 시험).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from capa_simulation.services.edit_grid import (
    BAD_LIMIT,
    OUTBOX_CELL_LIMIT,
    PASTE_CELL_LIMIT,
    UNDO_LIMIT,
    DraftState,
    GridIndex,
    GridSpec,
    HistoryState,
    build_index,
    change_counts,
    format_payload,
    key_duplicates,
)

CODE_ALPHABET: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
# 같은 값 런 길이는 글자 하나(1~63)라 더 긴 런은 나눈다.
RUN_LIMIT: Final = 63
HEAD_HEIGHT_PX: Final = 32
# feed 초안 코드: 0 초안 없음 · 1 빈칸 · 2 못 읽음 · 3.. 값 사전(`dvals`).
DRAFT_NONE: Final = 0
DRAFT_BLANK: Final = 1
DRAFT_BAD: Final = 2
DRAFT_FIRST_VALUE: Final = 3
LIMITS: Final[Mapping[str, int]] = {
    "paste": PASTE_CELL_LIMIT,
    "outbox": OUTBOX_CELL_LIMIT,
    "bad": BAD_LIMIT,
    "undo": UNDO_LIMIT,
}

Labels = Mapping[str, Mapping[str, str]]


def code_width(count: int) -> int:
    """값 `count` 개를 번호로 적는 글자 수(64 진)."""
    width = 1
    while len(CODE_ALPHABET) ** width < max(count, 1):
        width += 1
    return width


def _code_table(count: int, width: int) -> list[str]:
    """번호 0..count-1 의 고정 폭 글(높은 자리 먼저)."""
    base = len(CODE_ALPHABET)
    table: list[str] = []
    for number in range(count):
        digits = []
        for _ in range(width):
            number, digit = divmod(number, base)
            digits.append(CODE_ALPHABET[digit])
        table.append("".join(reversed(digits)))
    return table


def encode_codes(codes: Sequence[int] | npt.NDArray[np.int64], width: int) -> str:
    """번호 목록을 고정 폭 글자로 잇는다."""
    array = np.asarray(codes, dtype=np.int64)
    if array.size == 0:
        return ""
    table = np.array(_code_table(int(array.max()) + 1, width), dtype=object)
    return "".join(table[array].tolist())


def json_number(value: float) -> int | float:
    """JSON 에 싣는 수 — 정수 값은 정수로(「30.0」 대신 「30」), -0 은 0."""
    value += 0.0
    if value.is_integer() and abs(value) < 2**53:
        return int(value)
    return value


def encode_runs(codes: npt.NDArray[np.int64], width: int) -> list[str]:
    """줄마다 (코드 `width` 글자 + 길이 1 글자) 짝을 이은 글. 같은 코드가 이어지는 칸을 한
    짝으로."""
    rows, cols = codes.shape
    if cols == 0:
        return [""] * rows
    change = np.ones((rows, cols), dtype=bool)
    change[:, 1:] = codes[:, 1:] != codes[:, :-1]
    starts = np.flatnonzero(change.ravel())
    lengths = np.diff(np.append(starts, rows * cols))
    run_codes = codes.ravel()[starts]
    run_rows = starts // cols
    pieces = (lengths + RUN_LIMIT - 1) // RUN_LIMIT
    if int(pieces.max()) > 1:
        total = int(pieces.sum())
        first = np.repeat(np.cumsum(pieces) - pieces, pieces)
        order = np.arange(total) - first
        last = order == np.repeat(pieces - 1, pieces)
        tail = np.repeat(lengths - RUN_LIMIT * (pieces - 1), pieces)
        lengths = np.where(last, tail, RUN_LIMIT)
        run_codes = np.repeat(run_codes, pieces)
        run_rows = np.repeat(run_rows, pieces)
    table = np.array(_code_table(int(run_codes.max()) + 1, width), dtype=object)
    pairs = (table[run_codes] + np.array(list(CODE_ALPHABET), dtype=object)[lengths]).tolist()
    bounds = np.searchsorted(run_rows, np.arange(rows + 1))
    return ["".join(pairs[bounds[row] : bounds[row + 1]]) for row in range(rows)]


def _dictionary(series: pd.Series) -> tuple[list[str], npt.NDArray[np.int64]]:
    codes, uniques = pd.factorize(series.astype(str), sort=False)
    return [str(item) for item in uniques], np.asarray(codes, dtype=np.int64)


def labels_digest(labels: Labels | None) -> str:
    """표시명 사전의 지문(캐시 키 · `baseKey`)."""
    if not labels:
        return "-"
    flat = sorted((str(column), sorted(mapping.items())) for column, mapping in labels.items())
    return hashlib.sha1(json.dumps(flat, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def base_key(table: str, content_token: str, order_digest: str, labels_key: str) -> str:
    """껍데기 지문 — 표·내용·줄 차례·표시명이 같으면 같다. feed 가 같은 값을 싣는다."""
    return f"{table}:{content_token}:{order_digest}:{labels_key}"


def encode_table(
    template: pd.DataFrame, spec: GridSpec, labels: Labels | None, index: GridIndex
) -> dict[str, Any]:
    """표 본문(캐시하는 몫) — 칸 규격·분류 사전과 코드·값 사전과 줄 RLE·중복 키 꼬리표."""
    dims: list[list[str]] = []
    label_lists: list[list[str] | None] = []
    key_codes: list[str] = []
    widths: list[int] = []
    for column in spec.key_columns:
        values, codes = _dictionary(template[column])
        width = code_width(len(values))
        mapping = (labels or {}).get(column)
        shown = [str(mapping.get(value, value)) for value in values] if mapping else None
        dims.append(values)
        label_lists.append(shown if shown is not None and shown != values else None)
        key_codes.append(encode_codes(codes, width))
        widths.append(width)
    matrix = index.values
    finite = ~np.isnan(matrix)
    uniques, inverse = np.unique(matrix[finite] + 0.0, return_inverse=True)
    value_codes = np.zeros(matrix.shape, dtype=np.int64)
    value_codes[finite] = inverse.reshape(-1) + 1
    value_width = code_width(len(uniques) + 1)
    return {
        "table": spec.table,
        "title": spec.title,
        "rows": len(index.keys),
        "keyCols": [{"name": column, "label": column} for column in spec.key_columns],
        "valueCols": list(spec.value_columns),
        "valueHelp": spec.value_help,
        "fmt": format_payload(spec.fmt),
        "dims": dims,
        "labels": label_lists,
        "codes": key_codes,
        "codeWidths": widths,
        "vals": [None, *(json_number(float(value)) for value in uniques)],
        "valWidth": value_width,
        "runs": encode_runs(value_codes, value_width),
        "dupes": [list(pair) for pair in key_duplicates(template, spec.key_columns)],
    }


@dataclass(frozen=True)
class EditGridBase:
    """캐시하는 양식 몫 — op 반영에 쓰는 색인과 껍데기 본문."""

    index: GridIndex
    body: dict[str, Any]


def build_base(template: pd.DataFrame, spec: GridSpec, labels: Labels | None) -> EditGridBase:
    """양식 하나의 색인과 본문(캐시 빗나감에만 — `simulation_cache.get_edit_grid_base`)."""
    index = build_index(template, spec)
    return EditGridBase(index, encode_table(template, spec, labels, index))


def encode_base(
    body: Mapping[str, Any],
    *,
    host: str,
    base_key: str,
    texts: Mapping[str, Any],
    palette: Mapping[str, str],
    row_height: int,
    limits: Mapping[str, int] = LIMITS,
) -> dict[str, Any]:
    """껍데기 — 본문에 호스트·지문·글·팔레트·줄 높이·상한을 더한다(같은 표·같은 테마면 같은
    dict)."""
    return {
        **body,
        "rowHeight": row_height,
        "headHeight": HEAD_HEIGHT_PX,
        "host": host,
        "baseKey": base_key,
        "texts": dict(texts),
        "palette": dict(palette),
        "limits": dict(limits),
    }


def empty_base(
    *, host: str, texts: Mapping[str, Any], palette: Mapping[str, str]
) -> dict[str, Any]:
    """표 없는 껍데기(읽기 보기를 고른 회차 — 그리드 마운트는 표 없이 남는다)."""
    return {
        "table": None,
        "host": host,
        "baseKey": "",
        "texts": dict(texts),
        "palette": dict(palette),
    }


def _draft_rows(
    index: GridIndex, draft: DraftState
) -> tuple[list[list[Any]], list[int | float], int, list[list[Any]], int]:
    """초안을 줄 RLE 로 — (drows, dvals, 코드 폭, 오류 칸 앞 `BAD_LIMIT` 개, 오류 칸 수)."""
    dictionary: dict[float, int] = {}
    per_row: dict[int, dict[int, int]] = {}
    for key, cells in draft["cells"].items():
        row = index.rows.get(key)
        if row is None:
            continue
        line = per_row.setdefault(row, {})
        for month, value in cells.items():
            col = index.cols.get(month)
            if col is None:
                continue
            if value is None:
                line[col] = DRAFT_BLANK
            else:
                code = dictionary.get(value)
                if code is None:
                    code = dictionary[value] = DRAFT_FIRST_VALUE + len(dictionary)
                line[col] = code
    bad: list[list[Any]] = []
    bad_count = 0
    for key, cells_bad in draft["bad"].items():
        row = index.rows.get(key)
        if row is None:
            continue
        line = per_row.setdefault(row, {})
        for month, (text, code_name) in cells_bad.items():
            col = index.cols.get(month)
            if col is None:
                continue
            line[col] = DRAFT_BAD
            bad_count += 1
            if len(bad) < BAD_LIMIT:
                bad.append([row, col, text, code_name])
    width = code_width(DRAFT_FIRST_VALUE + len(dictionary))
    table = _code_table(DRAFT_FIRST_VALUE + len(dictionary), width)
    drows: list[list[Any]] = []
    for row in sorted(per_row):
        line = per_row[row]
        if not line:
            continue
        start, end = min(line), max(line)
        pairs: list[str] = []
        col = start
        while col <= end:
            code = line.get(col, DRAFT_NONE)
            length = 1
            while col + length <= end and length < RUN_LIMIT and line.get(col + length, 0) == code:
                length += 1
            pairs.append(table[code] + CODE_ALPHABET[length])
            col += length
        drows.append([row, start, "".join(pairs)])
    bad.sort(key=lambda item: (item[0], item[1]))
    values = [json_number(value) for value in dictionary]
    return drows, values, width, bad, bad_count


def encode_feed(
    index: GridIndex | None,
    draft: DraftState | None,
    history: HistoryState | None,
    *,
    host: str,
    base_key: str,
    acks: Mapping[str, int],
    toast: Mapping[str, Any] | None,
    filters: Mapping[int, Sequence[int]] | None = None,
) -> dict[str, Any]:
    """feed — 초안·오류 칸·수·되돌리기 수·ack·토스트·필터. 표가 없으면(읽기 보기) 빈 feed."""
    cells, rows, errors = change_counts(draft)
    feed: dict[str, Any] = {
        "host": host,
        "table": index.table if index is not None else None,
        "baseKey": base_key,
        "gen": history["gen"] if history is not None else "",
        "dvals": [],
        "dwidth": 1,
        "drows": [],
        "bad": [],
        "badCount": 0,
        "counts": {"cells": cells, "rows": rows, "errors": errors},
        "undo": len(history["undo"]) if history is not None else 0,
        "redo": len(history["redo"]) if history is not None else 0,
        "acks": dict(acks),
        "toast": dict(toast) if toast is not None else None,
        "filters": {str(col): list(codes) for col, codes in filters.items()} if filters else None,
    }
    if index is not None and draft is not None:
        drows, values, width, bad, bad_count = _draft_rows(index, draft)
        feed.update(dvals=values, dwidth=width, drows=drows, bad=bad, badCount=bad_count)
    return feed


def payload_bytes(data: Mapping[str, Any]) -> int:
    """data 의 JSON 바이트 수(예산 시험·측정)."""
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
