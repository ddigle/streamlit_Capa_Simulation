# Purpose: 설비 마스터 표의 칸 정의·행 id·data·출납 반영·차이·되돌리기를 streamlit 없이 낸다.

"""가용설비 현황 「설비 마스터」 탭 표의 streamlit 을 모르는 부분(개편 명세 4~7장).

- **칸 정의**(`GRID_COLUMNS`) — 계약 39칸 차례(`EQUIPMENT_COLUMNS`) 그대로, 칸마다 글
  꼴(`kind`)·저장 갈래(`scope` — 공통·시나리오·상태)·폭·고를 값. 칸 묶음(`COLUMN_SETS`)과 상세
  묶음(`DETAIL_GROUPS`)도 여기 한 곳이다. 브라우저로 가는 자리 번호는 모두 이 차례다.
- **행 id**(`grid_index`) — 저장본 호기는 `s:` + 저장본 설비명(이름을 바꿔도 그대로), 이 세션 새
  호기는 `n:` + 지금 이름이다. 짝은 저장의 호기 키
  규칙(`equipment_scenario.inherited_unit_names`)으로 잇는다 — 둘이 갈리면 표가 「바뀐 칸」 으로
  보인 호기가 저장에서 새 호기가 된다.
- **칸 글자**(`cell_text`) — 화면 글자이자 견줌 글자. 「바뀐 칸」 은 저장본 글자와 편집본 글자가
  다른 칸이다(형과 상관없다).
- **data**(`grid_data`·`loader_data`·`detail_data`·`changes_data`) — 한 회차의 표
  모양(`GridView`)에서 세 마운트(불러오기·표·오른쪽 칸)의 data 를 낸다. 같은 입력이면 같은 dict 다 —
  같은 JSON 이면 브라우저 ForwardMsg 캐시가 맞는다.
- **출납**(`pending_ops`·`apply_ops`) — 브라우저가 상태 값 `outbox` 로 보낸 「반영되지 않은 조작
  전부」 에서 아직 반영하지 않은 것만 `(at, mount, seq)` 차례로 골라 편집본 세 표에 얹는다. 칸 값은
  저장 정규화와 같은 함수(`equipment_validation.coerce_master_cell`)로 다듬고, 못 다듬은 글은
  편집본에 넣지 않고 칸 초안(`overlay`)에 둔다 — 편집본 세 표는 늘 계약 dtype 이다.
- **되돌리기**(`UndoStep`) — 한 조작의 역 patch(칸 자리·옛 값, 뺀 행·넣은 행). 표의 조작만 쌓이고
  다른 길(Space 적용·작은 편집표 적용)이 편집본을 바꾸면 목록을 비우므로 나중 것부터(LIFO) 되돌리면
  자리가 늘 맞는다. 행 조각을 든 단계를 버릴 때는 그보다 앞 단계도 함께 버린다(뒤 단계만 남는다).

업무 검증은 여기와 `equipment_validation` 이 한다 — 브라우저는 data 가 준 잠금·고를 값·자리 계산만
안다.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Final, Literal

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_float_dtype

from capa_simulation.services.equipment_contract import (
    AREA_CODE_COLUMN,
    AREA_CODES,
    ARRIVAL_ACTUAL_COLUMN,
    ARRIVAL_DATE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    ARRIVAL_STATUSES,
    CONVERSION_RATIO_COLUMN,
    COORDINATE_COLUMNS,
    DATE_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    FLAG_COLUMNS,
    MEMO_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_ACTUAL_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    RELOCATION_DATE_COLUMN,
    SCENARIO_LAYOUT_COLUMNS,
    SCENARIO_MEMO_COLUMN,
    SCENARIO_SCHEDULE_COLUMNS,
    STOP_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    VALID_BUILDINGS,
    VALID_FLOORS,
)
from capa_simulation.services.equipment_scenario import inherited_unit_names
from capa_simulation.services.equipment_validation import (
    CellParseError,
    MasterIssue,
    coerce_master_cell,
)
from capa_simulation.services.space_layout_edit import (
    NameChange,
    PendingRenames,
    apply_name_changes,
    check_unit_rename,
    compose_unit_renames,
    module_group_rows,
    natural_name_key,
    reserved_names,
)

Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]

# ------------------------------------------------------------------ 한계(합성 표본 측정으로 정한다)
# 한 번에 불러오는 호기(개편 명세 13장 D6 — 사용자 R3 「1,000대」). 넘으면 앞 1,000대만 불러온다.
GRID_ROW_LIMIT: Final = 1_000
# 한 번에 붙이는 칸. 넘으면 브라우저가 넣지 않고 「엑셀·CSV로 한꺼번에」 를 권한다.
GRID_PASTE_CELLS: Final = 5_000
# 브라우저가 들고 있는 보낼 목록의 칸 상한. 붙여넣기 상한이 먼저 걸린다.
GRID_OUTBOX_CELLS: Final = 10_000
# 되돌리기 단계 수. 통째 단계(엑셀·CSV 「편집본에 넣기」)는 그 앞 단계를 모두 버린다.
UNDO_LIMIT: Final = 40
# 출납 반영 기억의 마운트 수. 넘으면 오래 안 보낸 마운트부터 잊는다.
MOUNT_LIMIT: Final = 20
# 「저장 전 변경」 의 고칠 것 줄·호기별 변경 줄 상한.
CHANGE_ERROR_LIMIT: Final = 30
CHANGE_LINE_LIMIT: Final = 300

SAVED_PREFIX: Final = "s:"
NEW_PREFIX: Final = "n:"

# ------------------------------------------------------------------ 칸 도움말(공통·시나리오)
# 상태 두 칸은 공통이지만 「확정」 은 공식 일정이 확정됐다는 뜻이다(결정 모음 — 칸 머리).
_STATUS_COLUMNS = (ARRIVAL_STATUS_COLUMN, QUAL_STATUS_COLUMN)
COMMON_COLUMN_HELP: Final = "공통 — 모든 설비 시나리오에 같은 값"
STATUS_COLUMN_HELP: Final = "공통 — 공식 일정 기준"


def scenario_column_help(column: str, scenario_name: str | None) -> str:
    """칸 도움말 첫 마디 — 공통·상태·시나리오 가운데 어느 쪽인지. 옛 RawData 편집표 머리와 새 표
    머리가 같은 글이다."""
    if column in SCENARIO_SCHEDULE_COLUMNS:
        where = f"「{scenario_name}」 에만" if scenario_name else "지금 설비 시나리오에만"
        return f"시나리오 — {where} 저장"
    if column in _STATUS_COLUMNS:
        return STATUS_COLUMN_HELP
    return COMMON_COLUMN_HELP


# ------------------------------------------------------------------ 칸 정의

ColumnKind = Literal["name", "text", "memo", "date", "number", "choice"]
ColumnScope = Literal["common", "scenario", "status"]
# 칸 폭 갈래(브라우저 CSS `.emg-w-<폭>`) — 시안 2차의 폭 그대로다.
ColumnWidth = Literal["name", "short", "status", "date", "num", "text", "memo"]

FLAG_VALUES: Final = ("Y", "N")
_SHORT_TEXT_COLUMNS = frozenset(
    {"공정대분류", "공정구분", "투자Capa", "투자구분", "사용기준", "담당자"}
)
_MEMO_COLUMNS = frozenset(
    {*MEMO_COLUMNS, "반입/Qual 이력", "호기이력", "설비이력", SCENARIO_MEMO_COLUMN}
)
_NUMBER_COLUMNS = frozenset({*COORDINATE_COLUMNS, CONVERSION_RATIO_COLUMN})
_CHOICES: Mapping[str, tuple[tuple[str, ...], bool]] = {
    "동": (VALID_BUILDINGS, True),
    "층": (VALID_FLOORS, True),
    ARRIVAL_STATUS_COLUMN: (tuple(ARRIVAL_STATUSES), True),
    QUAL_STATUS_COLUMN: (tuple(QUAL_CONFIRMATION_STATUSES), True),
    **{column: (FLAG_VALUES, False) for column in FLAG_COLUMNS},
}


@dataclass(frozen=True)
class GridColumn:
    """표 칸 하나. `options`·`blank` 은 고르는 칸(`choice`)만 — 빈 값을 받는 칸만 「(비움)」 이
    있다. `suggest` 는 글 칸의 제안(Area Code)이고 목록 밖 값은 막지 않는다(경고)."""

    name: str
    kind: ColumnKind
    scope: ColumnScope
    width: ColumnWidth
    options: tuple[str, ...] = ()
    blank: bool = True
    suggest: tuple[str, ...] = ()


def _column(name: str) -> GridColumn:
    scope: ColumnScope = (
        "scenario"
        if name in SCENARIO_SCHEDULE_COLUMNS
        else "status"
        if name in _STATUS_COLUMNS
        else "common"
    )
    if name == EQUIPMENT_ID_COLUMN:
        return GridColumn(name, "name", scope, "name")
    if name in DATE_COLUMNS:
        return GridColumn(name, "date", scope, "date")
    if name in _NUMBER_COLUMNS:
        return GridColumn(name, "number", scope, "num")
    if name in _CHOICES:
        options, blank = _CHOICES[name]
        width: ColumnWidth = "status" if name in _STATUS_COLUMNS else "short"
        return GridColumn(name, "choice", scope, width, options=options, blank=blank)
    if name == AREA_CODE_COLUMN:
        return GridColumn(name, "text", scope, "short", suggest=AREA_CODES)
    if name in _MEMO_COLUMNS:
        return GridColumn(name, "memo", scope, "memo")
    return GridColumn(name, "text", scope, "short" if name in _SHORT_TEXT_COLUMNS else "text")


GRID_COLUMNS: Final[tuple[GridColumn, ...]] = tuple(_column(name) for name in EQUIPMENT_COLUMNS)
COLUMN_INDEX: Final[Mapping[str, int]] = {
    name: index for index, name in enumerate(EQUIPMENT_COLUMNS)
}
NAME_INDEX: Final = COLUMN_INDEX[EQUIPMENT_ID_COLUMN]


@dataclass(frozen=True)
class ColumnSet:
    """칸 묶음 하나(표 위 고르기). 설비명은 늘 맨 왼쪽 고정 칸이라 묶음에 넣지 않는다."""

    key: str
    label: str
    tip: str
    columns: tuple[str, ...]


# 칸 묶음 다섯(개편 명세 4-2). 「전체 39칸」 은 계약(엑셀 양식) 차례다 — 여러 칸 붙여넣기가 양식과
# 맞는다(13장 D10).
COLUMN_SETS: Final[tuple[ColumnSet, ...]] = (
    ColumnSet(
        "basic",
        "기본",
        "공정·위치와 반입·Qual 일정 요약",
        (
            "공정소분류",
            AREA_CODE_COLUMN,
            "Model",
            "동",
            "층",
            ARRIVAL_DATE_COLUMN,
            ARRIVAL_STATUS_COLUMN,
            QUAL_DATE_COLUMN,
            QUAL_STATUS_COLUMN,
            "담당자",
        ),
    ),
    ColumnSet(
        "schedule",
        "일정",
        "일정(시나리오) 여섯 + 실적·상태(공통)",
        (
            ARRIVAL_DATE_COLUMN,
            ARRIVAL_ACTUAL_COLUMN,
            ARRIVAL_STATUS_COLUMN,
            QUAL_DATE_COLUMN,
            QUAL_ACTUAL_COLUMN,
            QUAL_STATUS_COLUMN,
            "제진대일정",
            "물류일정",
            STOP_DATE_COLUMN,
            RELOCATION_DATE_COLUMN,
            SCENARIO_MEMO_COLUMN,
        ),
    ),
    ColumnSet(
        "place",
        "위치",
        "Space 실물 칸(공통)",
        (
            "공정소분류",
            "동",
            "층",
            "X좌표",
            "Y좌표",
            "Xsize",
            "Ysize",
            "레이아웃표시",
            PARENT_EQUIPMENT_COLUMN,
            CONVERSION_RATIO_COLUMN,
        ),
    ),
    ColumnSet(
        "memo",
        "이력·메모",
        "이력·메모(공통) + 시나리오 메모",
        (
            "공정소분류",
            "담당자",
            "반입/Qual 이력",
            "호기이력",
            "설비이력",
            *MEMO_COLUMNS,
            SCENARIO_MEMO_COLUMN,
        ),
    ),
    ColumnSet(
        "all",
        "전체 39칸",
        "모든 칸 — 엑셀 양식 차례",
        tuple(name for name in EQUIPMENT_COLUMNS if name != EQUIPMENT_ID_COLUMN),
    ),
)


@dataclass(frozen=True)
class DetailGroup:
    """오른쪽 「호기 상세」 의 칸 묶음 하나 — 범위 꼬리표(공통·시나리오)와 한 줄 설명."""

    key: str
    title: str
    scope: Literal["common", "scenario"]
    note: str
    columns: tuple[str, ...]


# 상세 묶음 다섯(개편 명세 4-6 가). 39칸이 빠짐없이 한 번씩 든다(시험이 본다).
DETAIL_GROUPS: Final[tuple[DetailGroup, ...]] = (
    DetailGroup(
        "info",
        "호기 정보",
        "common",
        "어떤 설비인가",
        (
            EQUIPMENT_ID_COLUMN,
            AREA_CODE_COLUMN,
            "공정대분류",
            "공정소분류",
            "공정구분",
            "Maker",
            "Model",
            "투자Capa",
            "투자구분",
            "사용기준",
            "담당자",
            CONVERSION_RATIO_COLUMN,
            PARENT_EQUIPMENT_COLUMN,
            STORAGE_FLAG_COLUMN,
            "기존설비여부",
        ),
    ),
    DetailGroup(
        "schedule",
        "일정",
        "scenario",
        "시나리오마다 다를 수 있는 날짜 여섯 + 시나리오 메모",
        (
            "제진대일정",
            "물류일정",
            ARRIVAL_DATE_COLUMN,
            QUAL_DATE_COLUMN,
            STOP_DATE_COLUMN,
            RELOCATION_DATE_COLUMN,
            SCENARIO_MEMO_COLUMN,
        ),
    ),
    DetailGroup(
        "actual",
        "실적·상태",
        "common",
        "실제로 끝난 날과 진행 상태 — 상태는 공식 일정 기준",
        (ARRIVAL_ACTUAL_COLUMN, ARRIVAL_STATUS_COLUMN, QUAL_ACTUAL_COLUMN, QUAL_STATUS_COLUMN),
    ),
    DetailGroup(
        "place",
        "위치",
        "common",
        "Space 실물 — 좌표·크기는 배치 편집기에서",
        ("동", "층", "X좌표", "Y좌표", "Xsize", "Ysize", "레이아웃표시"),
    ),
    DetailGroup(
        "memo",
        "이력·메모",
        "common",
        "",
        ("반입/Qual 이력", "호기이력", "설비이력", *MEMO_COLUMNS),
    ),
)

# ------------------------------------------------------------------ 잠금

# 잠금 갈래 → 칸. 모듈 묶음(Main 설비 모듈 둘 이상)의 좌표·크기, 가정 설비 시나리오(S3 전)의 있던
# 호기 배치 일곱 칸, 낡은 세션의 시나리오 일곱 칸. 지운 표시 줄은 모든 칸이 잠긴다(`deleted`).
LOCK_SETS: Final[Mapping[str, tuple[str, ...]]] = {
    "module": tuple(COORDINATE_COLUMNS),
    "layout": tuple(SCENARIO_LAYOUT_COLUMNS),
    "stale": tuple(SCENARIO_SCHEDULE_COLUMNS),
}
MODULE_LOCK_REASON: Final = "모듈 묶음 좌표·크기는 Space 배치 편집기에서 고칩니다"
DELETED_LOCK_REASON: Final = "지울 목록에 든 호기입니다 — 되살리면 고칠 수 있습니다"


@dataclass(frozen=True)
class GridContext:
    """한 회차의 표 조건. 글은 화면 쪽(설비 시나리오 세션)이 만들어 넘긴다.

    - `base` — 편집본이 나온 저장본 쌍 토큰 + 씨뿌린 세대. 출납 op 의 `base` 가 다르면 버린다.
    - `stale_lock` — 낡은 세션(또는 일정 없이 엶)이면 시나리오 일곱 칸 잠금 까닭.
    - `delete_lock` — 낡은 세션이면 저장본 호기 지우기 잠금 까닭(`stale_delete_lock`).
    - `layout_lock` — 가정 설비 시나리오(설비 시나리오 2단계 S3 전)면 있던 호기 배치 일곱 칸 잠금
      까닭.
    - `location_options` — 동·층 고를 값(Space 층 사용 상태로 좁힌 것). 없으면 유효 동·층 전부.
    """

    base: str
    scenario_name: str | None = None
    official: bool = True
    stale_lock: str | None = None
    delete_lock: str | None = None
    layout_lock: str | None = None
    new_rows_locked: bool = False
    location_options: tuple[tuple[str, ...], tuple[str, ...]] | None = None

    def lock_reasons(self) -> dict[str, str]:
        reasons = {"module": MODULE_LOCK_REASON, "deleted": DELETED_LOCK_REASON}
        if self.stale_lock:
            reasons["stale"] = self.stale_lock
        if self.layout_lock:
            reasons["layout"] = self.layout_lock
        return reasons


# ------------------------------------------------------------------ 칸 글자


def cell_text(value: object) -> str:
    """칸 값의 화면 글자 — 빈 값 `""`, 날짜 `YYYY-MM-DD`, 수는 반올림하지 않은 짧은 꼴(`0.25`·`12`),
    글은 앞뒤 공백을 뗀다. 「바뀐 칸」 견줌도 이 글자끼리다."""
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else value.strftime("%Y-%m-%d")
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, np.datetime64):
        return "" if np.isnat(value) else pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    ):
        number = float(value)
        if math.isnan(number):
            return ""
        if number == 0:
            return "0"
        return str(np.format_float_positional(number, trim="-"))
    return str(value).strip()


def _text_column(series: pd.Series) -> list[str]:
    """칸 하나를 화면 글자 목록으로 — 칸 형마다 한 번에(3천 줄 × 39칸을 회차마다 본다)."""
    if is_datetime64_any_dtype(series):
        stamped = series.dt.strftime("%Y-%m-%d")
        return ["" if not isinstance(text, str) else text for text in stamped.tolist()]
    return [cell_text(value) for value in series.tolist()]


def text_matrix(master: pd.DataFrame) -> list[list[str]]:
    """설비 마스터를 줄마다 39칸 화면 글자로(계약 차례). 없는 칸은 빈 글자다."""
    columns = [
        _text_column(master[name]) if name in master.columns else [""] * len(master)
        for name in EQUIPMENT_COLUMNS
    ]
    return [list(row) for row in zip(*columns, strict=True)] if columns and len(master) else []


def _names(master: pd.DataFrame) -> list[str]:
    if EQUIPMENT_ID_COLUMN not in master.columns:
        return [""] * len(master)
    return [cell_text(value) for value in master[EQUIPMENT_ID_COLUMN].tolist()]


# ------------------------------------------------------------------ 행 id


@dataclass(frozen=True)
class GridIndex:
    """편집본 줄 ↔ 행 id.

    - `ids` — 편집본 설비 마스터 줄 차례의 행 id(같은 이름이 둘이면 뒤 줄에 `~2` 꼬리).
    - `live` — 행 id → 편집본 줄 자리.
    - `saved` — `s:` 행 id → 저장본 줄 자리(지운 호기 포함).
    - `deleted` — 저장본에 있는데 편집본이 잇지 않는 호기(저장본 차례). 지운 표시 줄이다.
    """

    ids: tuple[str, ...]
    live: Mapping[str, int]
    saved: Mapping[str, int]
    deleted: tuple[str, ...]

    def is_new(self, row_id: str) -> bool:
        return row_id in self.live and not row_id.startswith(SAVED_PREFIX)


def grid_index(master: pd.DataFrame, saved: pd.DataFrame, renames: Mapping[str, str]) -> GridIndex:
    """행 id 를 낸다(`renames` 는 저장 안 한 이름 지도 — 지금 이름 → 저장본 이름, 저장이 넘기는 그
    지도 그대로). 저장본 이름을 잇는 줄은 `s:` + 저장본 이름, 나머지는 `n:` + 지금 이름이다."""
    names = _names(master)
    saved_names = _names(saved)
    saved_set = set(saved_names) - {""}
    inherited = inherited_unit_names(names, saved_set, renames)
    used_origins = set(inherited.values())
    ids: list[str] = []
    seen: dict[str, int] = {}
    for name in names:
        origin = inherited.get(name)
        base = SAVED_PREFIX + origin if origin is not None else NEW_PREFIX + name
        count = seen.get(base, 0) + 1
        seen[base] = count
        ids.append(base if count == 1 else f"{base}~{count}")
    saved_positions: dict[str, int] = {}
    for position, name in enumerate(saved_names):
        if name:
            saved_positions.setdefault(SAVED_PREFIX + name, position)
    deleted = tuple(
        SAVED_PREFIX + name
        for name in dict.fromkeys(saved_names)
        if name and name not in used_origins
    )
    return GridIndex(
        ids=tuple(ids),
        live={row_id: position for position, row_id in enumerate(ids)},
        saved=saved_positions,
        deleted=deleted,
    )


def saved_name_of(row_id: str) -> str | None:
    """`s:` 행 id 의 저장본 설비명(`~n` 꼬리 뗌), 새 호기면 None."""
    if not row_id.startswith(SAVED_PREFIX):
        return None
    return row_id[len(SAVED_PREFIX) :].split("~", 1)[0] if "~" in row_id else row_id[2:]


def save_id_map(index: GridIndex, master: pd.DataFrame) -> dict[str, str | None]:
    """지금 행 id → 저장 뒤 행 id(이름 바꾼 호기 `s:옛 → s:새`, 새 호기 `n:X → s:X`, 지운 호기
    None). 저장 직전에 만들어 두고 저장이 성공하면 불러온 목록·상세 id 를 이 지도로 옮긴다(개편 명세
    7-3)."""
    names = _names(master)
    moved: dict[str, str | None] = {
        row_id: SAVED_PREFIX + names[position] for row_id, position in index.live.items()
    }
    moved.update({row_id: None for row_id in index.deleted})
    return moved


# ------------------------------------------------------------------ 불러온 목록


@dataclass(frozen=True)
class LoadResult:
    """불러오기 한 번의 결과 — 새 목록과 새로 든 수·이미 있던 수·상한으로 버린 수."""

    loaded: tuple[str, ...]
    added: int
    already: int
    cut: int


def load_ids(
    loaded: Sequence[str], ids: Sequence[str], *, limit: int = GRID_ROW_LIMIT
) -> LoadResult:
    """`ids` 를 불러온 목록에 더한다 — 새로 든 호기는 위로(받은 차례), 이미 있던 호기는 그 자리.
    합쳐 `limit` 을 넘으면 넘는 몫(새로 든 쪽의 뒤)을 버린다."""
    present = set(loaded)
    fresh = [row_id for row_id in dict.fromkeys(ids) if row_id not in present]
    already = len(set(ids) & present)
    room = max(limit - len(loaded), 0)
    cut = max(len(fresh) - room, 0)
    taken = fresh[:room]
    return LoadResult(tuple(taken) + tuple(loaded), len(taken), already, cut)


def prune_loaded(loaded: Sequence[str], index: GridIndex) -> tuple[str, ...]:
    """편집본에 없는 id 를 거른다 — 지운 표시 호기는 남긴다."""
    keep = set(index.live) | set(index.deleted)
    return tuple(row_id for row_id in loaded if row_id in keep)


def move_ids(ids: Sequence[str], moved: Mapping[str, str | None]) -> tuple[str, ...]:
    """id 목록을 옮김 지도로 바꾼다(None 이면 뺀다, 겹치면 첫 것만)."""
    result = [moved.get(row_id, row_id) for row_id in ids]
    return tuple(dict.fromkeys(row_id for row_id in result if row_id))


def all_load_ids(
    master: pd.DataFrame, index: GridIndex, *, limit: int = GRID_ROW_LIMIT
) -> list[str]:
    """「전체 불러오기」 — 살아 있는 호기 모두, 상한을 넘으면 설비명 자연 차례 앞 `limit` 대."""
    names = _names(master)
    ordered = sorted(index.live.items(), key=lambda item: natural_name_key(names[item[1]]))
    return [row_id for row_id, _ in ordered][:limit] if len(ordered) > limit else list(index.live)


def overlay_key(row_id: str, column: str) -> str:
    """칸 초안 열쇠(세션 칸은 dict 라 글자 하나로)."""
    return f"{row_id}\t{column}"


def overlay_parts(key: str) -> tuple[str, str]:
    row_id, _, column = key.partition("\t")
    return row_id, column


def prune_overlay(overlay: Mapping[str, str], index: GridIndex) -> dict[str, str]:
    """편집본에 없는 행의 칸 초안을 걷는다(Space 가 그 호기를 지웠거나 이름을 바꾼 새 호기)."""
    return {key: text for key, text in overlay.items() if overlay_parts(key)[0] in index.live}


# ------------------------------------------------------------------ 한 회차의 표 모양


@dataclass(frozen=True)
class GridSource:
    """표 모양을 낼 재료. `frames`·`saved` 는 (기존 보유대수, 설비 마스터, 비가동 일정) 이다.

    `issues` 는 편집본 설비 마스터에 규칙 표를 돌린 결과(`equipment_master_issues`, 저장과 같은
    인자), `alerts` 는 설비명 → 일정 확인 갈래 글(「Qual 미확인」 등), `table_errors` 는 표 단위
    오류 줄(기존 보유대수·비가동 일정·예시 행·모듈 묶음 바둑판), `others` 는 「저장 전 변경」 의
    다른 것 한 줄이다."""

    frames: Frames
    saved: Frames
    renames: PendingRenames = field(default_factory=PendingRenames)
    overlay: Mapping[str, str] = field(default_factory=dict)
    issues: Sequence[MasterIssue] = ()
    alerts: Mapping[str, str] = field(default_factory=dict)
    table_errors: Sequence[str] = ()
    others: str = ""


@dataclass(frozen=True)
class RowMarks:
    """한 줄의 표지 — 자리 번호(계약 차례) → 글. 「바뀐 칸」 의 값은 저장본 글자다."""

    changed: dict[int, str] = field(default_factory=dict)
    errors: dict[int, str] = field(default_factory=dict)
    warns: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GridView:
    """한 회차의 표 모양 — 세 마운트의 data 가 모두 여기서 나온다."""

    context: GridContext
    index: GridIndex
    values: Mapping[str, list[str]]
    marks: Mapping[str, RowMarks]
    locks: Mapping[str, tuple[str, ...]]
    tags: Mapping[str, str]
    names: Mapping[str, str]
    alerts: Mapping[str, str]
    errors: tuple[tuple[str | None, str, str, str], ...]
    downtime: pd.DataFrame
    source: GridSource

    @property
    def live_count(self) -> int:
        return len(self.index.live)


def _overlay_error(
    row_id: str, column: str, text: str, current_name: str, source: GridSource
) -> str:
    """칸 초안의 오류 글 — 다듬기 오류 문구, 설비명은 이름 규칙 문구."""
    if column == EQUIPMENT_ID_COLUMN:
        master, downtime = source.frames[1], source.frames[2]
        reserved = reserved_names(source.saved[1], master, downtime, source.renames)
        message = check_unit_rename(current_name, text, master=master, reserved=reserved)
        return message or "설비명을 다시 확인합니다"
    parsed = coerce_master_cell(column, text)
    return parsed.message if isinstance(parsed, CellParseError) else "값을 다시 확인합니다"


def build_grid_view(source: GridSource, context: GridContext) -> GridView:
    """표 모양을 한 번에 낸다 — 편집본·저장본 글자, 줄마다 바뀐·오류·경고 표지와 잠금, 고칠 것
    목록."""
    master = source.frames[1].reset_index(drop=True)
    saved = source.saved[1].reset_index(drop=True)
    index = grid_index(master, saved, source.renames.units)
    buffer_texts = text_matrix(master)
    saved_texts = text_matrix(saved)
    values: dict[str, list[str]] = {}
    marks: dict[str, RowMarks] = {}
    names: dict[str, str] = {}
    tags: dict[str, str] = {}
    for row_id, position in index.live.items():
        row = buffer_texts[position]
        values[row_id] = list(row)
        names[row_id] = row[NAME_INDEX]
        changed: dict[int, str] = {}
        saved_position = index.saved.get(row_id) if row_id.startswith(SAVED_PREFIX) else None
        if saved_position is not None and "~" not in row_id:
            before = saved_texts[saved_position]
            changed = {j: before[j] for j in range(len(row)) if row[j] != before[j]}
        else:
            tags[row_id] = "new"
        marks[row_id] = RowMarks(changed=changed)
    for row_id in index.deleted:
        position = index.saved[row_id]
        values[row_id] = list(saved_texts[position])
        names[row_id] = saved_texts[position][NAME_INDEX]
        tags[row_id] = "deleted"
        marks[row_id] = RowMarks()
    errors: list[tuple[str | None, str, str, str]] = []
    for issue in source.issues:
        if issue.position >= len(index.ids):
            continue
        row_id = index.ids[issue.position]
        spot = COLUMN_INDEX.get(issue.column)
        if spot is None:
            continue
        target = marks[row_id].errors if issue.blocking else marks[row_id].warns
        target.setdefault(spot, issue.message)
        if issue.blocking:
            errors.append((row_id, names[row_id], issue.column, issue.message))
    for key, text in prune_overlay(source.overlay, index).items():
        row_id, column = overlay_parts(key)
        if column not in COLUMN_INDEX:
            continue
        position = COLUMN_INDEX[column]
        message = _overlay_error(row_id, column, text, values[row_id][NAME_INDEX], source)
        values[row_id][position] = text
        marks[row_id].errors[position] = message
        marks[row_id].changed.pop(position, None)
        errors.append((row_id, names[row_id], column, message))
    errors.extend((None, "", "", line) for line in source.table_errors)
    module_rows = module_group_rows(master).notna().tolist() if len(master) else []
    locks: dict[str, tuple[str, ...]] = {}
    for row_id, position in index.live.items():
        kinds: list[str] = []
        if context.stale_lock:
            kinds.append("stale")
        if context.layout_lock and row_id.startswith(SAVED_PREFIX):
            kinds.append("layout")
        if module_rows and module_rows[position]:
            kinds.append("module")
        if kinds:
            locks[row_id] = tuple(kinds)
    return GridView(
        context=context,
        index=index,
        values=values,
        marks=marks,
        locks=locks,
        tags=tags,
        names=names,
        alerts={
            row_id: source.alerts[name] for row_id, name in names.items() if name in source.alerts
        },
        errors=tuple(errors),
        downtime=source.frames[2],
        source=source,
    )


def lock_of(view: GridView, row_id: str, column: str) -> str | None:
    """그 칸의 잠금 갈래(없으면 None). 지운 표시 줄은 모든 칸이 `deleted` 다."""
    if view.tags.get(row_id) == "deleted":
        return "deleted"
    for kind in view.locks.get(row_id, ()):
        if column in LOCK_SETS[kind]:
            return kind
    return None


# ------------------------------------------------------------------ data


def _sparse(marks: Mapping[int, str]) -> dict[str, str]:
    return {str(position): text for position, text in sorted(marks.items())}


def columns_payload(context: GridContext) -> list[dict[str, Any]]:
    """39칸 정의(계약 차례). 머리 풍선은 공통·시나리오 갈래 글 + 「· 눌러서 정렬」 이다."""
    buildings, floors = context.location_options or (VALID_BUILDINGS, VALID_FLOORS)
    result: list[dict[str, Any]] = []
    for column in GRID_COLUMNS:
        options = column.options
        if column.name == "동":
            options = tuple(buildings)
        elif column.name == "층":
            options = tuple(floors)
        item: dict[str, Any] = {
            "name": column.name,
            "kind": column.kind,
            "scope": column.scope,
            "width": column.width,
            "help": scenario_column_help(column.name, context.scenario_name),
        }
        if column.kind == "choice":
            item["options"] = list(options)
            item["blank"] = column.blank
        if column.suggest:
            item["suggest"] = list(column.suggest)
        result.append(item)
    return result


def column_sets_payload() -> list[list[Any]]:
    """칸 묶음 다섯 — [열쇠, 이름, 풍선, 자리 번호들]."""
    return [
        [item.key, item.label, item.tip, [COLUMN_INDEX[name] for name in item.columns]]
        for item in COLUMN_SETS
    ]


def detail_groups_payload() -> list[list[Any]]:
    """상세 묶음 다섯 — [열쇠, 이름, 범위, 설명, 자리 번호들]."""
    return [
        [group.key, group.title, group.scope, group.note, [COLUMN_INDEX[c] for c in group.columns]]
        for group in DETAIL_GROUPS
    ]


def lock_sets_payload() -> dict[str, list[int]]:
    return {kind: [COLUMN_INDEX[c] for c in columns] for kind, columns in LOCK_SETS.items()}


def view_token(ids: Sequence[str]) -> str:
    """불러온 목록(차례 포함)의 지문 — 바뀌면 브라우저가 고름·기준 줄·스크롤을 처음으로 돌린다."""
    return hashlib.sha1("\n".join(ids).encode("utf-8")).hexdigest()[:16]


def _row_payload(view: GridView, row_id: str) -> dict[str, Any]:
    marks = view.marks[row_id]
    row: dict[str, Any] = {"id": row_id, "values": view.values[row_id]}
    tag = view.tags.get(row_id)
    if tag:
        row["tag"] = tag
    if marks.changed:
        row["changed"] = _sparse(marks.changed)
    if marks.errors:
        row["errors"] = _sparse(marks.errors)
    if marks.warns:
        row["warns"] = _sparse(marks.warns)
    locks = view.locks.get(row_id)
    if locks and tag != "deleted":
        row["locks"] = list(locks)
    alert = view.alerts.get(row_id)
    if alert:
        row["alert"] = alert
    return row


def _scenario_payload(context: GridContext) -> dict[str, Any]:
    return {"name": context.scenario_name or "", "official": context.official}


def grid_data(
    view: GridView,
    loaded: Sequence[str],
    *,
    toast: Mapping[str, Any] | None = None,
    ack: Mapping[str, Any] | None = None,
    moved: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """표 마운트(`grid`)의 data(팔레트는 화면 쪽이 더한다). 줄은 불러온 목록 차례이고 편집본에 없는
    id 는 거른다."""
    rows = [_row_payload(view, row_id) for row_id in loaded if row_id in view.values]
    return {
        "mode": "grid",
        "base": view.context.base,
        "ack": dict(ack or {}),
        "scenario": _scenario_payload(view.context),
        "toast": dict(toast) if toast else None,
        "view": view_token([row["id"] for row in rows]),
        "columns": columns_payload(view.context),
        "colSets": column_sets_payload(),
        "lockSets": lock_sets_payload(),
        "lockReasons": view.context.lock_reasons(),
        "rows": rows,
        "counts": {"loaded": len(rows), "total": view.live_count, "limit": GRID_ROW_LIMIT},
        "newRowsLocked": view.context.new_rows_locked,
        "deleteLock": view.context.delete_lock,
        "limits": {"pasteCells": GRID_PASTE_CELLS, "outboxCells": GRID_OUTBOX_CELLS},
        "moved": dict(moved or {}),
    }


# 불러오기 「조건으로 불러오기」 칸(사용자 R1 — 옛 RawData 표 보기 거르기 13칸).
CONDITION_COLUMNS: Final = (
    "공정소분류",
    "공정구분",
    "투자구분",
    "공정대분류",
    "동",
    "층",
    AREA_CODE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    QUAL_STATUS_COLUMN,
    STORAGE_FLAG_COLUMN,
    "기존설비여부",
    "레이아웃표시",
    PARENT_EQUIPMENT_COLUMN,
)
BLANK_LABEL: Final = "(빈칸)"


def _sorted_values(values: Iterable[str]) -> list[str]:
    """빈 값은 맨 끝, 나머지는 설비명과 같은 자연 차례."""
    seen = set(values)
    present = sorted((value for value in seen if value), key=natural_name_key)
    return present + ([""] if "" in seen else [])


# 조건 칸 값 번호를 글자로 싣는 64자(번호 하나 = 칸마다 정한 자리 수의 글자). 3천 대 × 13칸을 수
# 배열로 실으면 수백 KB 라, 칸마다 이은 글자 하나로 싣는다(JS `decodeCodes` 가 같은 표로 푼다).
CODE_ALPHABET: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"


def code_width(count: int) -> int:
    """값 `count` 개를 번호로 적는 글자 수."""
    width = 1
    while len(CODE_ALPHABET) ** width < max(count, 1):
        width += 1
    return width


def encode_codes(codes: Sequence[int], width: int) -> str:
    """값 번호 목록을 고정 폭 글자로 잇는다(높은 자리 먼저)."""
    base = len(CODE_ALPHABET)
    chunks: list[str] = []
    for code in codes:
        digits = []
        for _ in range(width):
            code, digit = divmod(code, base)
            digits.append(CODE_ALPHABET[digit])
        chunks.append("".join(reversed(digits)))
    return "".join(chunks)


def loader_data(
    view: GridView,
    loaded: Sequence[str],
    *,
    missing: Sequence[str] = (),
    alert_ids: Sequence[str] = (),
    first_data: bool = False,
) -> dict[str, Any]:
    """불러오기 마운트(`loader`)의 data. 살아 있는 호기 전부(편집본 차례)의 설비명과 조건 칸 값을
    싣는다 — 이름·조건 칸이 바뀔 때만 바뀌어, 다른 칸만 고친 회차에는 같은 메시지다.

    - `names` — 설비명. 행 id 는 `s:` + 설비명이 아닌 자리만 `ids`(자리 → id)에 싣는다(새 호기·이름
      바꾼 호기).
    - `conditions` — 조건 칸(`CONDITION_COLUMNS`, 공정소분류·동·층 포함)의 값 목록(빈 값 `""` 은 맨
      끝)과 칸마다 줄 차례로 이은 값 번호 글자(`CODE_ALPHABET`, 폭 `widths`). 공정·동층 제안과
      「조건으로 불러오기」(사용자 R1)가 이것을 쓴다.
    - `processes` — 공정소분류와 대수(자연 차례, 「(빈칸)」 맨 끝).
    """
    live = list(view.index.live)
    names = [view.names[row_id] for row_id in live]
    ids = {
        str(position): row_id
        for position, row_id in enumerate(live)
        if row_id != SAVED_PREFIX + names[position]
    }
    values: list[list[str]] = []
    codes: list[str] = []
    widths: list[int] = []
    for column in CONDITION_COLUMNS:
        position = COLUMN_INDEX[column]
        cells = [view.values[row_id][position] for row_id in live]
        ordered = _sorted_values(cells)
        lookup = {value: number for number, value in enumerate(ordered)}
        width = code_width(len(ordered))
        values.append(ordered)
        widths.append(width)
        codes.append(encode_codes([lookup[cell] for cell in cells], width))
    counts: dict[str, int] = {}
    for cell in (view.values[row_id][COLUMN_INDEX["공정소분류"]] for row_id in live):
        counts[cell] = counts.get(cell, 0) + 1
    processes = [[label or BLANK_LABEL, counts[label]] for label in _sorted_values(counts)]
    known = set(view.values)
    return {
        "mode": "loader",
        "base": view.context.base,
        "names": names,
        "ids": ids,
        "processes": processes,
        "conditions": {
            "columns": list(CONDITION_COLUMNS),
            "values": values,
            "codes": codes,
            "widths": widths,
        },
        "loaded": [row_id for row_id in loaded if row_id in known],
        "alertIds": [row_id for row_id in alert_ids if row_id in view.index.live],
        "total": view.live_count,
        "limit": GRID_ROW_LIMIT,
        "missing": list(missing),
        "firstData": first_data,
        "newRowsLocked": view.context.new_rows_locked,
    }


def _downtime_rows(downtime: pd.DataFrame, name: str) -> list[list[str]]:
    if not name or downtime.empty or EQUIPMENT_ID_COLUMN not in downtime.columns:
        return []
    owned = downtime[EQUIPMENT_ID_COLUMN].astype("string").str.strip().eq(name).fillna(False)
    rows = downtime.loc[owned.astype(bool)]
    return [
        [cell_text(row.get(column)) for column in ("비가동유형", "시작일", "종료일", "상세사유")]
        for row in rows.to_dict(orient="records")
    ]


def detail_meta(view: GridView, row_id: str) -> str:
    """상세 머리 한 줄 — 공정소분류 · Model · 동 층 · 일정 확인 갈래."""
    row = view.values[row_id]
    where = f"{row[COLUMN_INDEX['동']]} {row[COLUMN_INDEX['층']]}".strip()
    parts = [row[COLUMN_INDEX["공정소분류"]], row[COLUMN_INDEX["Model"]], where]
    parts.append(view.alerts.get(row_id, ""))
    return " · ".join(part for part in parts if part)


def detail_data(view: GridView, row_id: str | None) -> dict[str, Any]:
    """오른쪽 「호기 상세」 마운트의 data. 없는 id 면 `unit` 이 None 이다(빈 상세)."""
    unit: dict[str, Any] | None = None
    if row_id is not None and row_id in view.values:
        unit = _row_payload(view, row_id)
        unit["meta"] = detail_meta(view, row_id)
        unit["downtime"] = _downtime_rows(view.downtime, view.names[row_id])
        deleted = view.tags.get(row_id) == "deleted"
        locked = view.context.delete_lock if row_id.startswith(SAVED_PREFIX) else None
        unit["deletable"] = not deleted and not locked
        unit["deleteLock"] = locked if not deleted else None
    return {
        "mode": "side",
        "panel": "detail",
        "base": view.context.base,
        "scenario": _scenario_payload(view.context),
        "columns": columns_payload(view.context),
        "groups": detail_groups_payload(),
        "lockSets": lock_sets_payload(),
        "lockReasons": view.context.lock_reasons(),
        "unit": unit,
        "newRowsLocked": view.context.new_rows_locked,
    }


@dataclass(frozen=True)
class ChangeCounts:
    """「저장 전 변경」 수 넷 — 고친 칸·새 호기·지울 호기·오류."""

    cells: int
    new: int
    deleted: int
    errors: int

    @property
    def total(self) -> int:
        return self.cells + self.new + self.deleted


def change_counts(view: GridView) -> ChangeCounts:
    cells = sum(
        len(view.marks[row_id].changed)
        for row_id in view.index.live
        if view.tags.get(row_id) != "new"
    )
    new = sum(1 for row_id in view.index.live if view.tags.get(row_id) == "new")
    return ChangeCounts(cells, new, len(view.index.deleted), len(view.errors))


def changes_data(view: GridView) -> dict[str, Any]:
    """오른쪽 「저장 전 변경」 마운트의 data — 수 넷, 고칠 것(최대 30), 호기별 변경(최대 300줄)."""
    counts = change_counts(view)
    errors = [list(item) for item in view.errors[:CHANGE_ERROR_LIMIT]]
    units: list[dict[str, Any]] = []
    lines_left = CHANGE_LINE_LIMIT
    more_lines = 0
    for row_id in (*view.index.live, *view.index.deleted):
        tag = view.tags.get(row_id)
        changed = view.marks[row_id].changed
        if not changed and tag is None:
            continue
        lines: list[list[str]] = []
        for position, before in sorted(changed.items()):
            if lines_left <= 0:
                more_lines += 1
                continue
            column = GRID_COLUMNS[position]
            lines.append([column.name, column.scope, before, view.values[row_id][position]])
            lines_left -= 1
        unit: dict[str, Any] = {"id": row_id, "name": view.names[row_id], "lines": lines}
        if tag:
            unit["tag"] = tag
        units.append(unit)
    return {
        "mode": "side",
        "panel": "changes",
        "base": view.context.base,
        "scenario": _scenario_payload(view.context),
        "counts": {
            "cells": counts.cells,
            "new": counts.new,
            "deleted": counts.deleted,
            "errors": counts.errors,
        },
        "errors": errors,
        "moreErrors": max(len(view.errors) - CHANGE_ERROR_LIMIT, 0),
        "units": units,
        "moreLines": more_lines,
        "others": view.source.others,
    }


# ------------------------------------------------------------------ 출납 고르기


def _seq(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def pending_ops(
    outboxes: Iterable[object], applied: Mapping[str, int]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """마운트들의 출납에서 아직 반영하지 않은 op 만 `(at, mount, seq)` 차례로 고른다.

    `outboxes` 는 마운트마다의 상태 값 `outbox`(``{"mount", "ops": [...]}``) — 꼴이 다른 것은
    버린다. `applied` 는 마운트 → 마지막으로 반영한 seq 다. 같은 출납이 여러 회차에 다시 와도 한
    번이고, 어느 콜백이 먼저 불려도 같은 차례다. 돌려준 기억은 이번에 본 마운트를 맨 뒤로 옮기고
    `MOUNT_LIMIT` 을 넘으면 오래된 것부터 잊는다. op 에는 `mount` 를 붙여 돌려준다."""
    memory = dict(applied)
    picked: list[dict[str, Any]] = []
    for outbox in outboxes:
        if not isinstance(outbox, Mapping):
            continue
        mount = outbox.get("mount")
        ops = outbox.get("ops")
        if not isinstance(mount, str) or not mount or not isinstance(ops, list):
            continue
        last = memory.get(mount, 0)
        newest = last
        for op in ops:
            if not isinstance(op, Mapping):
                continue
            seq = _seq(op.get("seq"))
            if seq is None or seq <= last:
                continue
            picked.append({**op, "mount": mount})
            newest = max(newest, seq)
        memory.pop(mount, None)
        memory[mount] = newest
    while len(memory) > MOUNT_LIMIT:
        memory.pop(next(iter(memory)))

    def order(op: Mapping[str, Any]) -> tuple[float, str, int]:
        at = op.get("at")
        moment = float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else 0.0
        return (moment, str(op["mount"]), int(op["seq"]))

    picked.sort(key=order)
    return picked, memory


# ------------------------------------------------------------------ 되돌리기


@dataclass(frozen=True)
class UndoStep:
    """한 조작의 역 patch. 칸은 (편집본 줄 자리, 칸, 옛 값)이고 조작 **뒤** 자리다.

    - `master_removed`·`downtime_removed` — 조작이 뺀 줄(행 이름 = 빼기 전 자리). 되돌리면 그 자리로
      다시 넣는다.
    - `master_added`·`downtime_added` — 조작이 넣은 줄의 조작 뒤 자리. 되돌리면 뺀다.
    - `overlay` — (초안 열쇠, 옛 글 또는 None). `renames` 는 옛 이름 지도(바뀌었을 때만).
    - `loaded` — 옛 불러온 목록(바뀌었을 때만). `frames` 는 통째 단계의 옛 세 표다.
    """

    label: str
    kind: Literal["cells", "rows", "whole"] = "cells"
    master: tuple[tuple[int, str, Any], ...] = ()
    downtime: tuple[tuple[int, str, Any], ...] = ()
    master_removed: pd.DataFrame | None = None
    downtime_removed: pd.DataFrame | None = None
    master_added: tuple[int, ...] = ()
    downtime_added: tuple[int, ...] = ()
    overlay: tuple[tuple[str, str | None], ...] = ()
    renames: PendingRenames | None = None
    loaded: tuple[str, ...] | None = None
    frames: Frames | None = None


def undo_to_state(steps: Sequence[UndoStep]) -> tuple[dict[str, Any], ...]:
    """세션에 둘 기본형(dict·tuple·DataFrame)으로 — 모델 인스턴스를 세션에 두면 핫리로드 뒤
    `isinstance` 가 거짓이 된다(AGENTS 5장 21 과 같은 까닭)."""
    return tuple(
        {
            "label": step.label,
            "kind": step.kind,
            "master": step.master,
            "downtime": step.downtime,
            "master_removed": step.master_removed,
            "downtime_removed": step.downtime_removed,
            "master_added": step.master_added,
            "downtime_added": step.downtime_added,
            "overlay": step.overlay,
            "renames": None
            if step.renames is None
            else {"units": dict(step.renames.units), "groups": dict(step.renames.groups)},
            "loaded": step.loaded,
            "frames": step.frames,
        }
        for step in steps
    )


def undo_from_state(value: object) -> tuple[UndoStep, ...]:
    """세션 칸의 기본형을 되살린다. 꼴이 다르면 빈 목록이다(되돌리기만 사라지고 편집은 그대로)."""
    if not isinstance(value, tuple):
        return ()
    steps: list[UndoStep] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str):
            return ()
        renames = item.get("renames")
        frames = item.get("frames")
        steps.append(
            UndoStep(
                label=item["label"],
                kind=item.get("kind", "cells"),
                master=tuple(item.get("master") or ()),
                downtime=tuple(item.get("downtime") or ()),
                master_removed=item.get("master_removed"),
                downtime_removed=item.get("downtime_removed"),
                master_added=tuple(item.get("master_added") or ()),
                downtime_added=tuple(item.get("downtime_added") or ()),
                overlay=tuple(item.get("overlay") or ()),
                renames=PendingRenames(
                    units=dict(renames.get("units") or {}), groups=dict(renames.get("groups") or {})
                )
                if isinstance(renames, dict)
                else None,
                loaded=tuple(item["loaded"]) if isinstance(item.get("loaded"), tuple) else None,
                frames=frames if isinstance(frames, tuple) and len(frames) == 3 else None,
            )
        )
    return tuple(steps)


def push_undo(steps: Sequence[UndoStep], step: UndoStep) -> tuple[UndoStep, ...]:
    """단계를 쌓는다. 통째 단계는 앞 단계를 모두 버리고(통째 단계는 하나), 넘치면 오래된 것부터."""
    if step.kind == "whole":
        return (step,)
    return (*steps, step)[-UNDO_LIMIT:]


def after_row_steps(steps: Sequence[UndoStep]) -> tuple[UndoStep, ...]:
    """행 조각을 든 단계(지우기·되살리기·통째) 가운데 마지막 것 **뒤** 단계만 — 이름을 바꾸면 행
    조각의 옛 이름이 엉뚱한 호기에 붙으므로 버리고, 그보다 앞 단계는 자리가 맞지 않아 함께
    버린다."""
    last = max((k for k, step in enumerate(steps) if step.kind != "cells"), default=-1)
    return tuple(steps[last + 1 :])


# ------------------------------------------------------------------ 출납 반영


@dataclass(frozen=True)
class GridState:
    """출납을 얹을 세션 상태(기본형만 — 화면 쪽이 세션 칸에서 모아 넘긴다)."""

    frames: Frames
    saved: Frames
    renames: PendingRenames = field(default_factory=PendingRenames)
    overlay: Mapping[str, str] = field(default_factory=dict)
    undo: tuple[UndoStep, ...] = ()
    loaded: tuple[str, ...] = ()


@dataclass(frozen=True)
class GridApplied:
    """출납 반영 결과.

    - `changed` — 편집본·칸 초안·이름 지도 가운데 하나라도 바뀌었다(세대를 올린다).
    - `frames_changed` — 바뀐 표(기존 보유대수, 설비 마스터, 비가동 일정) — 그 표의 편집표만 버린다.
    - `moved` — 새 호기 이름을 바꿔 바뀐 행 id(옛 → 새). 브라우저가 고름·초점을 옮긴다.
    - `renamed` — 이번에 반영한 설비명 이름 바꿈(옛 → 새). 화면 쪽이 고름·필터를 따라 옮긴다.
    - `dropped` — `base` 가 달라 버린 op 수. `refused` — 잠긴 칸·없는 행·잠긴 지우기로 넣지 못한 수.
    """

    state: GridState
    changed: bool = False
    frames_changed: tuple[bool, bool, bool] = (False, False, False)
    toast: str | None = None
    toast_undo: bool = False
    moved: Mapping[str, str] = field(default_factory=dict)
    renamed: Mapping[str, str] = field(default_factory=dict)
    dropped: int = 0
    refused: int = 0


def _loc(frame: pd.DataFrame, column: str) -> int:
    """칸 이름의 자리(겹친 칸 이름은 계약 밖이라 거절한다)."""
    position = frame.columns.get_loc(column)
    if not isinstance(position, int):
        raise KeyError(column)
    return position


def _missing_value(series: pd.Series) -> Any:
    if is_datetime64_any_dtype(series):
        return pd.NaT
    if is_float_dtype(series.dtype):
        return np.nan
    return pd.NA


def _store(frame: pd.DataFrame, position: int, column: str, value: Any) -> None:
    """한 칸을 계약 dtype 그대로 넣는다(빈 값은 그 칸 형의 결측)."""
    series = frame[column]
    if (
        value is None
        or value is pd.NA
        or value is pd.NaT
        or (isinstance(value, float) and math.isnan(value))
    ):
        value = _missing_value(series)
    frame.iat[position, _loc(frame, column)] = value


@dataclass
class _Work:
    """한 번의 `apply_ops` 동안 고쳐 가는 상태(복사본)."""

    baseline: pd.DataFrame
    master: pd.DataFrame
    downtime: pd.DataFrame
    saved: Frames
    renames: PendingRenames
    overlay: dict[str, str]
    undo: list[UndoStep]
    loaded: list[str]
    context: GridContext
    changed: list[bool] = field(default_factory=lambda: [False, False, False])
    overlay_changed: bool = False
    renames_changed: bool = False
    moved: dict[str, str] = field(default_factory=dict)
    renamed: dict[str, str] = field(default_factory=dict)
    rename_count: int = 0
    toast: str | None = None
    toast_undo: bool = False
    dropped: int = 0
    refused: int = 0

    def index(self) -> GridIndex:
        return grid_index(self.master, self.saved[1], self.renames.units)


@dataclass
class _Patch:
    """op 하나가 쌓는 역 patch(조작 뒤 자리)."""

    master: dict[tuple[int, str], Any] = field(default_factory=dict)
    downtime: dict[tuple[int, str], Any] = field(default_factory=dict)
    overlay: dict[str, str | None] = field(default_factory=dict)
    renames: PendingRenames | None = None
    loaded: tuple[str, ...] | None = None
    cells: int = 0

    def step(self, label: str) -> UndoStep | None:
        if not (self.master or self.downtime or self.overlay or self.renames is not None):
            return None
        return UndoStep(
            label=label,
            master=tuple((pos, col, old) for (pos, col), old in self.master.items()),
            downtime=tuple((pos, col, old) for (pos, col), old in self.downtime.items()),
            overlay=tuple(self.overlay.items()),
            renames=self.renames,
            loaded=self.loaded,
        )


def _set_master(work: _Work, patch: _Patch, position: int, column: str, value: Any) -> bool:
    """편집본 설비 마스터 한 칸을 바꾼다 — 화면 글자가 같으면 그대로 둔다. 바뀌었으면 참."""
    current = work.master.iat[position, _loc(work.master, column)]
    if cell_text(current) == cell_text(value):
        return False
    patch.master.setdefault((position, column), current)
    _store(work.master, position, column, value)
    work.changed[1] = True
    return True


def _set_overlay(work: _Work, patch: _Patch, key: str, text: str | None) -> bool:
    current = work.overlay.get(key)
    if current == text:
        return False
    patch.overlay.setdefault(key, current)
    if text is None:
        work.overlay.pop(key, None)
    else:
        work.overlay[key] = text
    work.overlay_changed = True
    return True


def _locked(work: _Work, index: GridIndex, row_id: str, column: str, modules: list[bool]) -> bool:
    """파이썬도 잠금을 본다 — 브라우저 잠금만 믿지 않는다."""
    if column == EQUIPMENT_ID_COLUMN or column not in COLUMN_INDEX:
        return True
    if work.context.stale_lock and column in LOCK_SETS["stale"]:
        return True
    if (
        work.context.layout_lock
        and row_id.startswith(SAVED_PREFIX)
        and column in LOCK_SETS["layout"]
    ):
        return True
    position = index.live[row_id]
    return bool(modules and modules[position] and column in LOCK_SETS["module"])


# 칸 다듬기 기억 — 붙여넣기는 같은 (칸, 글)이 되풀이된다. 결과(`Timestamp`·수·글·NA·
# `CellParseError`)는 모두 바뀌지 않는 값이라 프로세스 안에서 나눠 써도 된다(Streamlit 캐시가
# 아니다).
_coerce = lru_cache(maxsize=8192)(coerce_master_cell)


def _module_flags(master: pd.DataFrame) -> list[bool]:
    return (
        [bool(flag) for flag in module_group_rows(master).notna().tolist()] if len(master) else []
    )


def _write_cell(
    work: _Work,
    patch: _Patch,
    index: GridIndex,
    modules: list[bool],
    row_id: str,
    column: str,
    text: str,
) -> int:
    """칸 하나에 글을 넣는다 — 다듬으면 편집본, 못 다듬으면 칸 초안. 바뀐 칸 수(0·1), 잠겼으면
    -1."""
    if row_id not in index.live or _locked(work, index, row_id, column, modules):
        return -1
    key = overlay_key(row_id, column)
    parsed = _coerce(column, text)
    if isinstance(parsed, CellParseError):
        return 1 if _set_overlay(work, patch, key, text) else 0
    cleared = _set_overlay(work, patch, key, None)
    changed = _set_master(work, patch, index.live[row_id], column, parsed)
    return 1 if (changed or cleared) else 0


def _rename(work: _Work, patch: _Patch, index: GridIndex, row_id: str, text: str) -> int:
    """설비명 칸 확정 = 이름 바꿈(개편 명세 4-11, 사용자 R2·G4 「같은 호기」). 걸리면 칸 초안."""
    if row_id not in index.live:
        return -1
    position = index.live[row_id]
    old = cell_text(work.master.iat[position, _loc(work.master, EQUIPMENT_ID_COLUMN)])
    new = text.strip()
    key = overlay_key(row_id, EQUIPMENT_ID_COLUMN)
    if new == old:
        return 1 if _set_overlay(work, patch, key, None) else 0
    reserved = reserved_names(work.saved[1], work.master, work.downtime, work.renames)
    refusal = check_unit_rename(old, new, master=work.master, reserved=reserved)
    if refusal is not None:
        return 1 if _set_overlay(work, patch, key, text) else 0
    _set_overlay(work, patch, key, None)
    before_master = work.master.copy()
    before_downtime = work.downtime.copy()
    master, downtime = apply_name_changes(
        work.master, work.downtime, [NameChange(kind="unit", old=old, new=new)]
    )
    _record_differences(
        patch.master, before_master, master, (EQUIPMENT_ID_COLUMN, PARENT_EQUIPMENT_COLUMN)
    )
    _record_differences(patch.downtime, before_downtime, downtime, (EQUIPMENT_ID_COLUMN,))
    work.master, work.downtime = master.reset_index(drop=True), downtime.reset_index(drop=True)
    work.changed[1] = True
    if not before_downtime.equals(work.downtime):
        work.changed[2] = True
    if patch.renames is None:
        patch.renames = work.renames
    saved_names = set(_names(work.saved[1])) - {""}
    work.renames = compose_unit_renames(work.renames, {old: new}, saved_names=saved_names)
    work.renames_changed = True
    # 한 번에 온 사슬(A→B 뒤 B→C)은 A→C 로 잇는다 — 화면 쪽이 한꺼번에 옮긴다.
    chained = {before: (new if after == old else after) for before, after in work.renamed.items()}
    if old not in work.renamed.values():
        chained[old] = new
    work.renamed = chained
    work.rename_count += 1
    if not row_id.startswith(SAVED_PREFIX):
        target = NEW_PREFIX + new
        work.moved[row_id] = target
        work.overlay = {
            (overlay_key(target, overlay_parts(k)[1]) if overlay_parts(k)[0] == row_id else k): v
            for k, v in work.overlay.items()
        }
        if row_id in work.loaded:
            if patch.loaded is None:
                patch.loaded = tuple(work.loaded)
            work.loaded = [target if item == row_id else item for item in work.loaded]
    return 1


def _record_differences(
    store: dict[tuple[int, str], Any],
    before: pd.DataFrame,
    after: pd.DataFrame,
    columns: Sequence[str],
) -> None:
    """두 표(같은 줄 수)에서 다른 칸의 옛 값을 쌓는다."""
    for column in columns:
        if column not in before.columns:
            continue
        old = before[column].tolist()
        new = after[column].tolist()
        for position, (left, right) in enumerate(zip(old, new, strict=True)):
            if cell_text(left) != cell_text(right):
                store.setdefault((position, column), left)


def _unit_name(work: _Work, position: int) -> str:
    return cell_text(work.master.iat[position, _loc(work.master, EQUIPMENT_ID_COLUMN)])


def _downtime_mask(downtime: pd.DataFrame, names: Collection[str]) -> list[bool]:
    if downtime.empty or EQUIPMENT_ID_COLUMN not in downtime.columns:
        return [False] * len(downtime)
    return [cell_text(value) in names for value in downtime[EQUIPMENT_ID_COLUMN].tolist()]


def _delete(work: _Work, ids: Sequence[str]) -> UndoStep | None:
    """지우기 — 저장본 호기는 지울 목록(줄은 지운 표시로 남는다), 새 호기는 바로 빠진다. 그 호기의
    비가동 일정도 함께 뺀다(2026-09-28 결정). 낡은 세션은 저장본 호기를 지우지 않는다."""
    index = work.index()
    targets: list[int] = []
    for row_id in dict.fromkeys(ids):
        if row_id not in index.live:
            work.refused += 1
            continue
        if row_id.startswith(SAVED_PREFIX) and work.context.delete_lock:
            work.refused += 1
            continue
        targets.append(index.live[row_id])
    if not targets:
        return None
    names = {_unit_name(work, position) for position in targets}
    master_removed = work.master.iloc[sorted(targets)].copy()
    downtime_flags = _downtime_mask(work.downtime, names)
    downtime_removed = work.downtime.loc[downtime_flags].copy()
    removed_ids = {index.ids[position] for position in targets}
    loaded_before = tuple(work.loaded)
    work.loaded = [
        row_id
        for row_id in work.loaded
        if not (row_id in removed_ids and not row_id.startswith(SAVED_PREFIX))
    ]
    overlay_before: dict[str, str | None] = {}
    for key in list(work.overlay):
        if overlay_parts(key)[0] in removed_ids:
            overlay_before[key] = work.overlay.pop(key)
            work.overlay_changed = True
    renames_before = work.renames
    remaining = {now: origin for now, origin in work.renames.units.items() if now not in names}
    if remaining != dict(work.renames.units):
        work.renames = PendingRenames(units=remaining, groups=dict(work.renames.groups))
        work.renames_changed = True
    work.master = work.master.drop(index=work.master.index[sorted(targets)]).reset_index(drop=True)
    work.downtime = work.downtime.loc[[not flag for flag in downtime_flags]].reset_index(drop=True)
    work.changed[1] = True
    if any(downtime_flags):
        work.changed[2] = True
    return UndoStep(
        label="호기 지움",
        kind="rows",
        master_removed=master_removed,
        downtime_removed=downtime_removed if not downtime_removed.empty else None,
        overlay=tuple(overlay_before.items()),
        renames=renames_before if work.renames is not renames_before else None,
        loaded=loaded_before if tuple(work.loaded) != loaded_before else None,
    )


def _insert_row(frame: pd.DataFrame, position: int, row: pd.DataFrame) -> pd.DataFrame:
    position = min(max(position, 0), len(frame))
    return pd.concat([frame.iloc[:position], row, frame.iloc[position:]], ignore_index=True)


def _restore_position(work: _Work, index: GridIndex, saved_position: int) -> int:
    """되살릴 자리 = 저장본 차례에서 그 호기 **뒤** 저장본 호기 가운데 편집본에 남은 첫 호기의 바로
    앞 (없으면 끝). 행 번호로 넣으면 따로따로 지웠다 되살릴 때 차례만 다른 공통 리비전이 생긴다."""
    saved_names = _names(work.saved[1])
    for name in saved_names[saved_position + 1 :]:
        live = index.live.get(SAVED_PREFIX + name)
        if live is not None:
            return live
    return len(work.master)


def _downtime_key(row: Mapping[Any, Any], names: Mapping[str, str]) -> tuple[str, str, str]:
    name = cell_text(row.get(EQUIPMENT_ID_COLUMN))
    return (names.get(name, name), cell_text(row.get("비가동유형")), cell_text(row.get("시작일")))


def _restore(work: _Work, ids: Sequence[str]) -> UndoStep | None:
    """되살리기 — 지운 표시 호기를 **저장본 값**으로 저장본 차례 자리에 다시 넣고, 저장본 비가동도
    저장본 차례 자리에 넣는다. 그 사이 같은 이름이 다시 생겼으면 건너뛴다(`refused`). 묶음 이름(Main
    설비)이 바뀌었으면 되살린 모듈 행에도 얹는다(옛 이름으로 돌아오면 한 설비가 둘로 갈린다)."""
    added_master: list[int] = []
    added_downtime: list[int] = []
    saved_master, saved_downtime = work.saved[1].reset_index(drop=True), work.saved[2]
    group_now = {origin: now for now, origin in work.renames.groups.items()}
    for row_id in dict.fromkeys(ids):
        index = work.index()
        if row_id not in index.deleted:
            work.refused += 1
            continue
        name = saved_name_of(row_id) or ""
        if name in set(_names(work.master)):
            work.refused += 1
            continue
        saved_position = index.saved[row_id]
        row = saved_master.iloc[[saved_position]].copy()
        if PARENT_EQUIPMENT_COLUMN in row.columns:
            parent = cell_text(row.iat[0, _loc(row, PARENT_EQUIPMENT_COLUMN)])
            if parent in group_now:
                row.iat[0, _loc(row, PARENT_EQUIPMENT_COLUMN)] = group_now[parent]
        row = row.reindex(columns=work.master.columns)
        position = _restore_position(work, index, saved_position)
        work.master = _insert_row(work.master, position, row.astype(work.master.dtypes.to_dict()))
        added_master = [p + 1 if p >= position else p for p in added_master] + [position]
        # 비가동 — 저장본 차례에서 그 호기 줄 뒤의 저장본 비가동 가운데 편집본에 남은 첫 줄 앞.
        now_of = {origin: now for now, origin in work.renames.units.items()}
        saved_rows = saved_downtime.reset_index(drop=True).to_dict(orient="records")
        present = {
            _downtime_key(item, {}): k
            for k, item in enumerate(work.downtime.to_dict(orient="records"))
        }
        owned = [
            k
            for k, item in enumerate(saved_rows)
            if cell_text(item.get(EQUIPMENT_ID_COLUMN)) == name
        ]
        for k in owned:
            key = _downtime_key(saved_rows[k], {})
            if key in present:
                continue
            target = len(work.downtime)
            for later in saved_rows[k + 1 :]:
                found = present.get(_downtime_key(later, now_of))
                if found is not None:
                    target = found
                    break
            piece = (
                saved_downtime.reset_index(drop=True)
                .iloc[[k]]
                .reindex(columns=work.downtime.columns)
            )
            work.downtime = _insert_row(
                work.downtime, target, piece.astype(work.downtime.dtypes.to_dict())
            )
            added_downtime = [p + 1 if p >= target else p for p in added_downtime] + [target]
            present = {
                _downtime_key(item, {}): j
                for j, item in enumerate(work.downtime.to_dict(orient="records"))
            }
    if not added_master:
        return None
    work.changed[1] = True
    if added_downtime:
        work.changed[2] = True
    return UndoStep(
        label="되살리기",
        kind="rows",
        master_added=tuple(added_master),
        downtime_added=tuple(added_downtime),
    )


def _revert(work: _Work, patch: _Patch, row_id: str, column: str | None) -> UndoStep | None:
    """칸·호기 되돌리기 — 저장본 값으로. 호기 통째면 지운 호기는 되살리고 새 호기는 뺀다."""
    index = work.index()
    if column is None and row_id in index.deleted:
        return _restore(work, [row_id])
    if column is None and index.is_new(row_id):
        return _delete(work, [row_id])
    if row_id not in index.live or not row_id.startswith(SAVED_PREFIX):
        work.refused += 1
        return None
    saved_position = index.saved.get(row_id)
    if saved_position is None:
        work.refused += 1
        return None
    saved_row = work.saved[1].reset_index(drop=True).iloc[saved_position]
    columns = (
        [column]
        if column is not None
        else [c for c in EQUIPMENT_COLUMNS if c != EQUIPMENT_ID_COLUMN]
    )
    position = index.live[row_id]
    modules = _module_flags(work.master)
    for name in columns:
        if name == EQUIPMENT_ID_COLUMN or name not in work.master.columns:
            continue
        if _locked(work, index, row_id, name, modules):
            if column is not None:
                work.refused += 1
            continue
        _set_overlay(work, patch, overlay_key(row_id, name), None)
        _set_master(work, patch, position, name, saved_row.get(name))
    if column is None or column == EQUIPMENT_ID_COLUMN:
        _set_overlay(work, patch, overlay_key(row_id, EQUIPMENT_ID_COLUMN), None)
        origin = cell_text(saved_row.get(EQUIPMENT_ID_COLUMN))
        if _unit_name(work, position) != origin:
            _rename(work, patch, work.index(), row_id, origin)
    return None


def _shift_dates(work: _Work, patch: _Patch, ids: Sequence[str], days: int) -> int:
    """반입·Qual 일정 밀기 — 날짜가 있는 칸만. 둘 다 시나리오 칸이라 낡은 세션에서는 잠긴다."""
    index = work.index()
    modules = _module_flags(work.master)
    changed = 0
    for row_id in dict.fromkeys(ids):
        for column in (ARRIVAL_DATE_COLUMN, QUAL_DATE_COLUMN):
            if row_id not in index.live or _locked(work, index, row_id, column, modules):
                work.refused += 1
                continue
            position = index.live[row_id]
            value = work.master.iat[position, _loc(work.master, column)]
            if not isinstance(value, pd.Timestamp) or pd.isna(value):
                continue
            if _set_master(work, patch, position, column, value + pd.Timedelta(days=days)):
                changed += 1
    return changed


def _days(value: object) -> int | None:
    """밀 날 수 — 정수 또는 「−7」·「-7」·「+3」 글. 0 이면 None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value or None
    if isinstance(value, str):
        text = value.strip().replace("−", "-").replace("+", "")
        try:
            number = int(text)
        except ValueError:
            return None
        return number or None
    return None


def _texts(value: object) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def _apply_inverse(work: _Work, step: UndoStep) -> None:
    """역 patch 를 얹는다 — 칸 먼저, 넣은 줄 빼기, 뺀 줄 다시 넣기."""
    if step.kind == "whole" and step.frames is not None:
        work.baseline, work.master, work.downtime = (frame.copy() for frame in step.frames)
        work.changed = [True, True, True]
    for position, column, old in step.master:
        if position < len(work.master) and column in work.master.columns:
            _store(work.master, position, column, old)
            work.changed[1] = True
    for position, column, old in step.downtime:
        if position < len(work.downtime) and column in work.downtime.columns:
            _store(work.downtime, position, column, old)
            work.changed[2] = True
    if step.master_added:
        drop = [p for p in sorted(set(step.master_added), reverse=True) if p < len(work.master)]
        work.master = work.master.drop(index=work.master.index[drop]).reset_index(drop=True)
        work.changed[1] = True
    if step.downtime_added:
        drop = [p for p in sorted(set(step.downtime_added), reverse=True) if p < len(work.downtime)]
        work.downtime = work.downtime.drop(index=work.downtime.index[drop]).reset_index(drop=True)
        work.changed[2] = True
    for removed, slot in ((step.master_removed, 1), (step.downtime_removed, 2)):
        if removed is None or removed.empty:
            continue
        frame = work.master if slot == 1 else work.downtime
        for label in sorted(int(item) for item in removed.index.tolist()):
            piece = removed.loc[[label]].reindex(columns=frame.columns)
            frame = _insert_row(frame, label, piece.astype(frame.dtypes.to_dict()))
        if slot == 1:
            work.master = frame
        else:
            work.downtime = frame
        work.changed[slot] = True
    for key, old in step.overlay:
        if old is None:
            work.overlay.pop(key, None)
        else:
            work.overlay[key] = old
        work.overlay_changed = True
    if step.renames is not None:
        work.renames = step.renames
        work.renames_changed = True
    if step.loaded is not None:
        work.loaded = list(step.loaded)


DELETE_TOAST: Final = (
    "{count}대를 지울 목록에 넣었습니다 — 리비전을 저장해야 실제로 지워집니다. 호기를 지우면 모든 "
    "설비 시나리오에서 사라집니다(이 시나리오에서만 빼려면 정지·반출/이설일정을 적으세요)"
)
DROPPED_TOAST: Final = (
    "다른 사용자의 저장으로 편집본을 다시 세워, 그 전에 보낸 고침 {count}건은 반영하지 않았습니다"
)


def _paste_toast(lines: int, changed: int, cut: int, skipped: int) -> str:
    text = f"붙여넣기 {lines:,}줄 → {changed:,}칸 바뀜"
    if cut:
        text += f" · 표 끝을 넘은 {cut:,}줄은 버림"
    if skipped:
        text += f" · 넣지 못한 칸 {skipped:,}개"
    return text


def _cell_op(work: _Work, op: Mapping[str, Any]) -> UndoStep | None:
    row_id, column, text = op.get("id"), op.get("col"), op.get("text")
    if not isinstance(row_id, str) or not isinstance(column, str) or not isinstance(text, str):
        work.refused += 1
        return None
    patch = _Patch()
    index = work.index()
    if column == EQUIPMENT_ID_COLUMN:
        result = _rename(work, patch, index, row_id, text)
    else:
        result = _write_cell(work, patch, index, _module_flags(work.master), row_id, column, text)
    if result < 0:
        work.refused += 1
    return patch.step(f"{column} 고침")


def _paste_op(work: _Work, op: Mapping[str, Any]) -> UndoStep | None:
    ids, columns, rows = _texts(op.get("ids")), _texts(op.get("cols")), op.get("rows")
    if ids is None or columns is None or not isinstance(rows, list):
        work.refused += 1
        return None
    patch = _Patch()
    index = work.index()
    modules = _module_flags(work.master)
    changed = 0
    skipped = int(op["skipped"]) if isinstance(op.get("skipped"), int) else 0
    for row_id, cells in zip(ids, rows, strict=False):
        if not isinstance(cells, list):
            continue
        for column, text in zip(columns, cells, strict=False):
            if not isinstance(text, str):
                continue
            result = _write_cell(work, patch, index, modules, row_id, column, text)
            if result < 0:
                skipped += 1
            else:
                changed += result
    cut = int(op["cut"]) if isinstance(op.get("cut"), int) else 0
    work.toast = _paste_toast(len(rows) + cut, changed, cut, skipped)
    work.toast_undo = changed > 0
    return patch.step("붙여넣기")


def _set_op(work: _Work, op: Mapping[str, Any]) -> UndoStep | None:
    ids, column, text = _texts(op.get("ids")), op.get("col"), op.get("text")
    if ids is None or not isinstance(column, str) or not isinstance(text, str):
        work.refused += 1
        return None
    patch = _Patch()
    index = work.index()
    modules = _module_flags(work.master)
    changed = 0
    for row_id in dict.fromkeys(ids):
        result = _write_cell(work, patch, index, modules, row_id, column, text)
        if result < 0:
            work.refused += 1
        else:
            changed += result
    work.toast = f"값 넣기 — {changed:,}칸 바뀜"
    work.toast_undo = changed > 0
    return patch.step("값 넣기")


def _shift_op(work: _Work, op: Mapping[str, Any]) -> UndoStep | None:
    ids, days = _texts(op.get("ids")), _days(op.get("days"))
    if ids is None or days is None:
        work.refused += 1
        return None
    patch = _Patch()
    changed = _shift_dates(work, patch, ids, days)
    work.toast = f"날짜 밀기 — {changed:,}칸 바뀜"
    work.toast_undo = changed > 0
    return patch.step("날짜 밀기")


def _delete_op(work: _Work, op: Mapping[str, Any]) -> UndoStep | None:
    ids = _texts(op.get("ids"))
    if ids is None:
        work.refused += 1
        return None
    before = work.refused
    step = _delete(work, ids)
    refused = work.refused - before
    if step is not None:
        count = len(step.master_removed) if step.master_removed is not None else 0
        work.toast = DELETE_TOAST.format(count=count)
        work.toast_undo = True
    if refused and work.context.delete_lock:
        work.toast = (work.toast + " · " if work.toast else "") + work.context.delete_lock
    return step


def _restore_op(work: _Work, op: Mapping[str, Any]) -> UndoStep | None:
    ids = _texts(op.get("ids"))
    if ids is None:
        work.refused += 1
        return None
    before = work.refused
    step = _restore(work, ids)
    skipped = work.refused - before
    restored = len(step.master_added) if step is not None else 0
    text = f"{restored:,}대를 되살렸습니다"
    if skipped:
        text += f" · 같은 설비명이 이미 있어 {skipped:,}대는 건너뜀"
    work.toast = text
    work.toast_undo = restored > 0
    return step


def _revert_op(work: _Work, op: Mapping[str, Any]) -> UndoStep | None:
    row_id, column = op.get("id"), op.get("col")
    if not isinstance(row_id, str) or (column is not None and not isinstance(column, str)):
        work.refused += 1
        return None
    patch = _Patch()
    structural = _revert(work, patch, row_id, column)
    if structural is not None:
        return structural
    return patch.step("되돌림")


def _undo_op(work: _Work) -> None:
    if not work.undo:
        return
    step = work.undo.pop()
    _apply_inverse(work, step)
    work.toast = f"되돌림: {step.label}"
    work.toast_undo = False


_OPS = {
    "cell": _cell_op,
    "paste": _paste_op,
    "set": _set_op,
    "shift": _shift_op,
    "delete": _delete_op,
    "restore": _restore_op,
    "revert": _revert_op,
}
OP_NAMES: Final = frozenset({*_OPS, "undo"})


def apply_ops(
    state: GridState, ops: Sequence[Mapping[str, Any]], context: GridContext
) -> GridApplied:
    """출납 op 를 차례대로 편집본에 얹는다(`pending_ops` 가 고른 것).

    `base` 가 지금 편집본의 `context.base` 와 다른 op 는 반영하지 않고 버린다 — 남의 저장으로 다시
    세운 편집본 위에 옛 편집을 얹지 않는다(그 수는 토스트 한 줄). 잠긴 칸·지운 표시 줄·낡은 세션의
    저장본 호기 지우기는 브라우저가 막아도 여기서 한 번 더 막는다. 내용이 그대로면 `changed` 가
    거짓이다(세대를 올리지 않는다).
    """
    work = _Work(
        baseline=state.frames[0],
        master=state.frames[1].reset_index(drop=True).copy(),
        downtime=state.frames[2].reset_index(drop=True).copy(),
        saved=state.saved,
        renames=state.renames,
        overlay=dict(state.overlay),
        undo=list(state.undo),
        loaded=list(state.loaded),
        context=context,
    )
    for op in ops:
        if op.get("base") != context.base:
            work.dropped += 1
            continue
        name = op.get("op")
        if name == "undo":
            _undo_op(work)
            continue
        handler = _OPS.get(str(name))
        if handler is None:
            work.refused += 1
            continue
        renamed_before = work.rename_count
        step = handler(work, op)
        if step is not None:
            work.undo = list(push_undo(work.undo, step))
        if work.rename_count > renamed_before:
            # 이름을 바꾸면 행 조각을 든 앞 단계는 옛 이름을 지녀 버린다(그 단계까지 함께).
            work.undo = list(after_row_steps(work.undo))
    if work.dropped:
        dropped = DROPPED_TOAST.format(count=work.dropped)
        work.toast = f"{work.toast} · {dropped}" if work.toast else dropped
    frames: Frames = (work.baseline, work.master, work.downtime)
    changed = any(work.changed) or work.overlay_changed or work.renames_changed
    new_state = GridState(
        frames=frames if changed else state.frames,
        saved=state.saved,
        renames=work.renames,
        overlay=work.overlay,
        undo=tuple(work.undo),
        loaded=tuple(work.loaded),
    )
    return GridApplied(
        state=new_state,
        changed=changed,
        frames_changed=(work.changed[0], work.changed[1], work.changed[2]),
        toast=work.toast,
        toast_undo=work.toast_undo,
        moved=dict(work.moved),
        renamed=dict(work.renamed),
        dropped=work.dropped,
        refused=work.refused,
    )


def whole_step(label: str, state: GridState) -> UndoStep:
    """통째 단계(엑셀·CSV 「편집본에 넣기」) — 옛 세 표·칸 초안·이름 지도·불러온 목록을 통째로
    든다."""
    baseline, master, downtime = state.frames
    return UndoStep(
        label=label,
        kind="whole",
        frames=(baseline.copy(), master.copy(), downtime.copy()),
        overlay=tuple((key, text) for key, text in state.overlay.items()),
        renames=state.renames,
        loaded=state.loaded,
    )
