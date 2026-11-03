# Purpose: Space 도면 편집기 「호기 정보」 창에 보낼 호기 표(칸 꼴·글자 칸·도면 자리)를 만든다.

"""층 상세 도면 위에 뜨는 「호기 정보」 창의 표 재료(2026-11-03 사용자 요청 — 페이지 아래 호기 표를
편집기 안 창으로 옮기고, 거꾸로 칸마다 필터를 걸어 맞는 호기를 도면에서 강조한다).

창은 편집기 JS 안에서 그리고 거른다(필터를 고칠 때마다 앱 전체가 돌지 않게). 파이썬은 칸 꼴과 칸
값을 JSON 으로 옮기기 좋게 한 번 정리할 뿐이다 — 날짜는 「YYYY-MM-DD」 글, 숫자 칸(투자Capa)은
읽히면 수, 그 밖은 글(길면 줄임), 빈 값은 None 이다. 칸 끝에 「도면」(배치·미배치·레이아웃 제외)을
붙인다. 행 차례는 받은 그대로이고 `MAX_SHEET_ROWS` 를 넘으면 앞에서 자르고 잘린 줄 수를 `cut` 에
적는다.

창의 「CSV」(2026-11-04 Space 결정 보드 답 — 옛 도면 아래 내려받기를 창 안으로)의 「층 전체」
는 파이썬이 지은 글을 표에 함께 싣는다(`floor_csv` — 옛 내려받기와 같은 칸 · 줄). 브라우저가
BOM 을 붙여 UTF-8 로 내려받는다. 「보이는 줄」 은 창의 칸으로 브라우저가 짓는다.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from datetime import date, datetime
from typing import Any, Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    DATE_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    INVESTMENT_CAPA_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
)

# 「도면」 칸 — 그 호기가 지금 도면 어디에 있는가. 배치 편집 중에는 편집기가 브라우저가 쥔 편집으로
# 덮어 쓴다(트레이로 뺀 호기는 미배치, 다른 층으로 보낸 호기는 「다른 층으로 보냄」).
PLACE_COLUMN: Final = "도면"
PLACE_PLACED: Final = "배치"
PLACE_UNPLACED: Final = "미배치"
PLACE_EXCLUDED: Final = "레이아웃 제외"
# 창에 싣는 줄의 상한 — 층당 많아야 수백 줄이다(샘플 관측 222줄). 넘으면 앞에서 자르고 창이 「n줄
# 더 — CSV 로」 를 단다(CSV 는 늘 층 전체).
MAX_SHEET_ROWS: Final = 3000
# 글 칸 하나의 길이 상한(메모처럼 긴 칸이 창을 늘리지 않게). 넘으면 잘라 「…」 를 붙인다.
MAX_TEXT_LENGTH: Final = 200
# 칸 꼴. 날짜·숫자 칸은 창의 필터에 「~부터 ~까지」 범위 칸이 선다.
SHEET_TYPES: Final = ("text", "date", "number")
# 층 전체 CSV 파일 이름 — 옛 도면 아래 내려받기와 같다.
FLOOR_CSV_NAME: Final = "space_{building}_{floor}.csv"


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False


def _day_text(value: object) -> str | None:
    """날짜 칸 값 → 「YYYY-MM-DD」(못 읽으면 None)."""
    if _blank(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    parsed = pd.to_datetime(str(value).strip(), errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _number_or_text(value: object) -> float | str | None:
    """숫자 칸 값 → 유한한 수, 수로 읽히지 않는 글은 그 글(필터 값 목록에 그대로 선다)."""
    if _blank(value):
        return None
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return _text(text)
    return number if math.isfinite(number) else _text(text)


def _text(value: object) -> str | None:
    """글 칸 값 → 앞뒤 공백을 걷은 글. 소수점 아래가 0 인 수는 정수 글(「3.0」 → 「3」)이고 길면
    줄인다."""
    if _blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    elif isinstance(value, (datetime, pd.Timestamp)):
        text = value.strftime("%Y-%m-%d")
    else:
        text = str(value).strip()
    if len(text) > MAX_TEXT_LENGTH:
        return text[: MAX_TEXT_LENGTH - 1] + "…"
    return text


def sheet_type(
    column: str, *, date_columns: Collection[str], number_columns: Collection[str]
) -> str:
    """칸 꼴 — 날짜 칸이면 date, 숫자 칸이면 number, 그 밖은 text."""
    if column in date_columns:
        return "date"
    if column in number_columns:
        return "number"
    return "text"


def default_place(row: Mapping[Any, Any]) -> str:
    """편집기가 그리지 않는 호기의 자리 — 레이아웃표시 Y 면 미배치(좌표를 넣으면 설 자리가 있다),
    아니면 레이아웃 제외."""
    shown = row.get("레이아웃표시")
    return PLACE_UNPLACED if isinstance(shown, str) and shown.strip() == "Y" else PLACE_EXCLUDED


def floor_csv(frame: pd.DataFrame, *, building: str, floor: str) -> dict[str, str]:
    """「호기 정보」 창 「CSV」 의 층 전체 — ``{"text": CSV 글, "file": 파일 이름}``.

    글은 `frame.to_csv(index=False)` 그대로(BOM 없음 — 브라우저가 내려받을 때 붙인다)라, 옛
    도면 아래 내려받기(`.encode("utf-8-sig")`)와 BOM 을 붙인 바이트가 같다. `frame` 은 그 층
    도면에 선 호기(공정소분류 필터 뒤)의 모든 칸이다.
    """
    return {
        "text": frame.to_csv(index=False),
        "file": FLOOR_CSV_NAME.format(building=building, floor=floor),
    }


def unit_sheet(
    rows: pd.DataFrame,
    *,
    columns: Sequence[str],
    place_of: Mapping[str, str],
    date_columns: Collection[str] = DATE_COLUMNS,
    number_columns: Collection[str] = (INVESTMENT_CAPA_COLUMN,),
    limit: int = MAX_SHEET_ROWS,
) -> dict[str, Any]:
    """「호기 정보」 창의 표 — ``{"columns": [{name, type}], "rows": [{id, group, cells}],
    "cut": n}``.

    - 칸은 `columns` 가운데 `rows` 에 있는 것을 그 차례로, 끝에 「도면」(`PLACE_COLUMN`, text).
    - 행 `id` 는 설비명(앞뒤 공백을 걷음 — 도면 호기 id 와 같다), `group` 은 Main 설비(없으면 None —
      창의 「고른 호기」 가 모듈 형제를 함께 보인다, `picked_unit_rows` 와 같은 규칙), `cells` 는
      칸 차례의 값이다. 설비명이 빈 행은 뺀다.
    - 「도면」 값은 `place_of[id]`, 없으면 레이아웃표시로 가른다(`default_place`).
    - `limit` 를 넘는 행은 앞에서 자르고 잘린 수를 `cut` 에 적는다.
    """
    if EQUIPMENT_ID_COLUMN not in rows.columns:
        return {"columns": [], "rows": [], "cut": 0}
    shown = [column for column in columns if column in rows.columns]
    kinds = [
        sheet_type(column, date_columns=date_columns, number_columns=number_columns)
        for column in shown
    ]
    converters = {"date": _day_text, "number": _number_or_text, "text": _text}
    records = rows.to_dict(orient="records")
    out_rows: list[dict[str, Any]] = []
    for record in records:
        raw_id = record.get(EQUIPMENT_ID_COLUMN)
        if _blank(raw_id):
            continue
        unit_id = str(raw_id).strip()
        parent = record.get(PARENT_EQUIPMENT_COLUMN)
        cells: list[Any] = [
            converters[kind](record.get(column)) for column, kind in zip(shown, kinds, strict=True)
        ]
        cells.append(place_of.get(unit_id) or default_place(record))
        out_rows.append(
            {
                "id": unit_id,
                "group": None if _blank(parent) else str(parent).strip(),
                "cells": cells,
            }
        )
    cut = max(len(out_rows) - max(limit, 0), 0)
    return {
        "columns": [
            *({"name": column, "type": kind} for column, kind in zip(shown, kinds, strict=True)),
            {"name": PLACE_COLUMN, "type": "text"},
        ],
        "rows": out_rows[: max(limit, 0)],
        "cut": cut,
    }
