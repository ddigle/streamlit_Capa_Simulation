# Purpose: 설비 세 입력을 정규화·검증한다 — 설비 마스터는 규칙 표 하나로 저장 거부와 칸 결과를 낸다.

"""설비 마스터·기존 보유대수·비가동 일정 입력을 정규화하고 검증한다.

설비 마스터는 **규칙 표 하나**(`MASTER_RULES`)를 세 쓰임이 함께 본다 — 문구 글자도 이 표의
규칙에서만 나온다.

- `prepare_equipment_master` — 저장·리비전 읽기·붙여넣기. 칸을 다듬은 뒤 표를 차례대로 보며
  **처음 걸린 규칙 하나**를 그 규칙의 문구(예시 5개 붙임)와 예외 형으로 던진다.
- `equipment_master_issues` — 칸 단위 결과(`MasterIssue`). 앞 규칙이 걸려도 멈추지 않고, 못 읽은
  값은 결측으로 보고 다음 규칙을 본다. 막지 않는 경고 셋(Area Code 목록 밖·대소문자만 다른
  설비명·모듈 묶음 환산비 모두 1)도 같은 표의 줄이다.
- `coerce_master_cell` — 칸 하나의 글을 저장 정규화와 **같은 함수**로 계약 꼴 값으로 다듬는다. 못
  다듬으면 그 규칙 문구를 단 `CellParseError`.

리비전을 다시 읽을 때도 이 표를 지나므로 **규칙을 조이지 않는다**(AGENTS 7장).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property, partial
from typing import Any, TypeAlias

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_dtype
from pandas.api.typing import NAType

from capa_simulation.services.equipment_contract import (
    AREA_CODE_COLUMN,
    AREA_CODES,
    ARRIVAL_ACTUAL_COLUMN,
    ARRIVAL_DATE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    ARRIVAL_STATUSES,
    BASELINE_COLUMNS,
    BASELINE_KEY_COLUMNS,
    CONVERSION_RATIO_COLUMN,
    COORDINATE_COLUMNS,
    DATE_COLUMNS,
    DEFAULT_CONVERSION_RATIO,
    DOWNTIME_COLUMNS,
    DOWNTIME_KEY_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    EXIT_SCHEDULE_COLUMNS,
    FLAG_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_ACTUAL_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
    REFERENCE_TEXT_COLUMNS,
    RELOCATION_DATE_COLUMN,
    STOP_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    UNIT_CONSISTENT_COLUMNS,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
    normalize_area_code,
    unknown_area_codes,
    with_optional_equipment_columns,
)
from capa_simulation.services.equipment_units import (
    MODULE_RATIO_WARNING,
    module_ratio_warning_rows,
)
from capa_simulation.services.floor_layout_profile import (
    CANVAS_DECIMALS,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    CanvasSize,
    FloorCanvasMap,
    FloorKey,
)
from capa_simulation.services.frame_contracts import require_columns, scalar_match_key


def prepare_equipment_baseline(
    data: pd.DataFrame,
    *,
    reject_infinite: bool = False,
) -> pd.DataFrame:
    """Normalize aggregate counts for unidentified legacy equipment.

    `reject_infinite` 는 붙여넣기·CSV 입구(`equipment_csv.read_baseline_*`)만 켠다. `to_numeric`
    은 `inf`·`Infinity` 를 무한으로 읽고 `ge(0)` 은 그것을 통과시켜, 켜지 않으면 스냅샷에
    무한대가 저장되고 총대수·가용대수가 무한이 된다. 되읽기·병합 경로는 끈 채 둔다 — 이미
    저장된 무한까지 막으면 그 스냅샷이 영영 열리지 않아 그 칸을 고칠 길도 사라진다.
    """
    require_columns(data, BASELINE_COLUMNS, "기존 보유대수")
    result = data.loc[:, BASELINE_COLUMNS].copy()
    result = _drop_blank_rows(result, ("공정", "분류", "기존보유대수"))
    if result.empty:
        return empty_equipment_baseline()
    _normalize_required_text(result, BASELINE_KEY_COLUMNS, "기존 보유대수")
    counts = pd.to_numeric(result["기존보유대수"], errors="coerce")
    valid_counts = counts.notna() & counts.ge(0)
    if reject_infinite:
        valid_counts &= counts.ne(math.inf)
    invalid_counts = ~valid_counts
    if invalid_counts.any():
        examples = _key_examples(result.loc[invalid_counts], BASELINE_KEY_COLUMNS)
        raise ValueError(f"기존보유대수는 0 이상의 숫자여야 합니다: {examples}")
    result["기존보유대수"] = counts.astype("float64")
    result["비고"] = _optional_text(result["비고"])
    duplicated = result.duplicated(list(BASELINE_KEY_COLUMNS), keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], BASELINE_KEY_COLUMNS)
        raise ValueError(f"기존 보유대수의 공정·분류가 중복되었습니다: {examples}")
    return result.reset_index(drop=True)


# ============================================================== 설비 마스터 — 규칙 표 하나

# 칸 하나에 다듬어 넣는 값. 날짜는 `Timestamp`, 좌표·크기·환산비는 `float`, 그 밖은 글자, 빈 값은
# `pd.NA` 다(계약 dtype 칸에 넣으면 그 칸의 결측 — NaN·NaT·<NA> — 이 된다).
CellValue: TypeAlias = str | float | pd.Timestamp | NAType


@dataclass(frozen=True)
class MasterIssue:
    """설비 마스터 칸 하나에 걸린 규칙 하나.

    - `position` — 넘긴 표의 줄 자리(`iloc`). 설비명이 빈 줄은 저장 정규화가 조용히 빼므로
      결과가 없다.
    - `unit` — 그 줄의 설비명(앞뒤 공백을 뗀 글자).
    - `column` — 계약 칸 이름. 칸 둘 이상에 걸리는 규칙은 줄마다 대표 칸 하나다(`MASTER_RULES`
      줄 주석).
    - `rule` — 규칙 코드(`MasterRule.code`).
    - `message` — 칸 문구. 저장 거부 문구에서 예시 목록을 뗀 앞머리다(캔버스 밖만 줄마다 그
      동·층 캔버스).
    - `blocking` — 거짓이면 저장을 막지 않는 경고다.
    """

    position: int
    unit: str
    column: str
    rule: str
    message: str
    blocking: bool = True


@dataclass(frozen=True)
class CellParseError:
    """칸 하나의 글을 계약 꼴로 다듬지 못했다. 그 글은 편집본에 넣지 않는다.

    `rule`·`message` 는 규칙 표에서 그 칸을 막는 규칙의 코드와 문구 앞머리다 — 저장이 같은 글을
    같은 문구로 막는다.
    """

    column: str
    text: str
    rule: str
    message: str


def prepare_equipment_master(
    data: pd.DataFrame,
    *,
    floor_canvases: FloorCanvasMap | None = None,
    today: date | None = None,
) -> pd.DataFrame:
    """설비 마스터 39컬럼 계약을 정규화하고 검증한다. 선택 컬럼은 없으면 빈 칸이다
    (`OPTIONAL_EQUIPMENT_COLUMNS`).

    규칙 표(`MASTER_RULES`)를 차례대로 보며 **처음 걸린 규칙 하나**를 그 규칙의 문구와 예외
    형(대개 `ValueError`, Main 설비 충돌은 `UnitGroupCollisionError`)으로 던진다. 설비명이 빈
    줄은 오류가 아니라 조용히 빠진다.

    `floor_canvases` 를 넘기면 층별 캔버스 폭·높이를 상한으로 좌표를 검사한다. 넘기지
    않으면 상한 검사를 건너뛴다 — 이미 저장된 리비전은 캔버스가 줄어든 뒤에도 열려야 한다.

    `today` 를 넘기면 **저장할 때만 도는** 실적 검사를 한다(실적이 오늘보다 늦음·반입실적이
    Qual실적보다 늦음). 결과가 날짜에 따라 달라지는 검사라 리비전을 다시 읽을 때는 넘기지 않는다 —
    저장 때 통과한 리비전이 시간이 지나 열리지 않으면 안 된다.
    """
    master = _read_master(data, floor_canvases=floor_canvases, today=today)
    if master is None:
        return empty_equipment_master()
    for rule in MASTER_RULES:
        if not rule.blocking:
            continue
        for finding in rule.check(master):
            if finding.rows.any():
                raise _rejection(master, finding)
    return master.data.reset_index(drop=True)


def equipment_master_issues(
    data: pd.DataFrame,
    *,
    floor_canvases: FloorCanvasMap | None = None,
    today: date | None = None,
) -> tuple[MasterIssue, ...]:
    """설비 마스터의 칸 단위 결과 — `prepare_equipment_master` 와 **같은 규칙 표, 같은 인자**다.

    저장 함수는 처음 걸린 규칙에서 멈추지만 여기서는 모든 규칙을 본다. 못 읽은 값(날짜·좌표·크기·
    환산비)은 결측으로 보고 다음 규칙을 이어 본다.

    결과 차례는 규칙 표 차례다. 한 규칙 안에서는 **칸 차례가 먼저, 그 칸 안에서 줄 차례**다 — 칸
    여럿을 따로 보는 규칙(Y/N·좌표·크기 못 읽음·모듈 행 칸 불일치·날짜·상태 값·반출 < 반입·
    실적 > 오늘)은 칸마다 결과를 묶어 낸다. 저장 함수도 같은 차례로 보므로 처음 막는 결과가 저장
    함수가 던질 규칙(칸 여럿을 보는 규칙이면 그 칸)이고, 그 문구가 거부 문구의 앞머리다. 저장이
    막힌다 ⇔ 막는 결과가 있다.

    막지 않는 경고(`blocking=False`)는 막는 결과가 있어도 낸다 — 경고 문장(`area_code_warnings`·
    `equipment_units.module_group_warnings`)이 검증 전 편집본을 보고 서는 것과 같다.

    표에 계약 칸이 없으면 저장 함수와 같은 `ValueError` 다. 설비명이 빈 줄은 결과가 없다.
    """
    master = _read_master(data, floor_canvases=floor_canvases, today=today)
    if master is None:
        return ()
    issues: list[MasterIssue] = []
    for rule in MASTER_RULES:
        for finding in rule.check(master):
            issues.extend(_finding_issues(master, rule, finding))
    return tuple(issues)


def coerce_master_cell(column: str, text: str) -> CellValue | CellParseError:
    """칸 하나의 글을 설비 마스터 계약 꼴 값으로 다듬는다.

    글을 한 칸짜리 Series 로 감싸 **저장 정규화와 같은 함수**를 지난다 — 날짜(`_read_date`)·
    좌표·크기(`_read_number`)·환산비(`_read_ratio`, 빈 값은 1.0)·Y/N(대문자)·Area Code
    (`normalize_area_code`)·글(앞뒤 공백 뗌, 빈 글은 결측)·동/층·상태 허용값. 그래서 저장이 같은
    글을 다르게 읽지 않는다.

    다듬지 못하면 `CellParseError` 다(문구는 저장이 그 글을 막는 규칙의 문구 앞머리). 빈 값은 늘
    받는다 — 비우면 안 되는 칸(설비명·공정소분류·Y/N)은 저장 규칙이 칸 결과로 막는다.

    시간대가 붙은 날짜는 저장과 같이 못 읽은 날짜다(`_read_master_dates`).
    """
    if column not in EQUIPMENT_COLUMNS:
        raise ValueError(f"설비 마스터 계약 칸이 아닙니다: {column}")
    cell = pd.Series([text], dtype="object")
    refuse = partial(CellParseError, column, text)
    if column in DATE_COLUMNS:
        dates, invalid = _read_master_dates(cell)
        if bool(invalid.iloc[0]):
            return refuse("date_unreadable", _date_message(column))
        return _cell_value(dates.iloc[0])
    if column in COORDINATE_COLUMNS:
        numbers, unreadable = _read_number(cell)
        if bool(unreadable.iloc[0]):
            return refuse("number_unreadable", _number_message(column))
        return _cell_value(numbers.iloc[0])
    if column == CONVERSION_RATIO_COLUMN:
        ratios, unreadable, not_positive = _read_ratio(cell)
        if bool(unreadable.iloc[0]):
            return refuse("ratio_unreadable", _number_message(column))
        if bool(not_positive.iloc[0]):
            return refuse("ratio_not_positive", _RATIO_NOT_POSITIVE)
        return _cell_value(ratios.iloc[0])
    if column in FLAG_COLUMNS:
        flag = _cell_value(_optional_text(_flag_text(cell)).iloc[0])
        if isinstance(flag, str) and flag not in ("Y", "N"):
            return refuse("flag", _flag_message(column))
        return flag
    if column == AREA_CODE_COLUMN:
        return _cell_value(normalize_area_code(cell).iloc[0])
    value = _cell_value(_optional_text(cell).iloc[0])
    if not isinstance(value, str):
        return value
    if (column == "동" and value not in VALID_BUILDINGS) or (
        column == "층" and value not in VALID_FLOORS
    ):
        return refuse("location_range", _LOCATION_RANGE)
    allowed = _STATUS_VALUES.get(column)
    if allowed is not None and value not in allowed:
        return refuse("status_value", _status_message(column, allowed))
    return value


def unit_case_variant_rows(names: pd.Series) -> pd.Series:
    """대소문자·앞뒤 공백만 다른 설비명이 표에 함께 있는 줄(겹친 줄 모두, `names` 와 같은 색인).

    짝을 찾는 열쇠는 붙여넣기 미리보기(`equipment_csv._case_variants`)와 같은
    `scalar_match_key` 다 — 두 곳이 다른 열쇠를 쓰면 한쪽만 경고한다. 글자까지 같은 이름끼리는
    세지 않는다(막는 규칙 「설비명 중복」 의 몫이다).
    """
    values = names.astype("string").tolist()
    spellings: dict[str, set[str]] = {}
    for value in values:
        if isinstance(value, str):
            spellings.setdefault(scalar_match_key(value), set()).add(value)
    flagged = [
        isinstance(value, str) and len(spellings[scalar_match_key(value)]) > 1 for value in values
    ]
    return pd.Series(flagged, index=names.index, dtype=bool)


# ------------------------------------------------------------------ 규칙 문구 — 한 곳


def _missing_text_message(label: str, column: str) -> str:
    return f"{label}의 {column}에 누락값이 있습니다"


def _unit_group_mixed_message(column: str) -> str:
    return f"같은 Main 설비의 모듈 행은 {column} 이 같아야 합니다"


def _flag_message(column: str) -> str:
    return f"{column}는 Y 또는 N이어야 합니다"


def _number_message(column: str) -> str:
    return f"{column}를 숫자로 읽을 수 없습니다"


def _date_message(label: str) -> str:
    return f"{label}은 날짜 형식이어야 합니다"


def _status_message(column: str, allowed: Sequence[str]) -> str:
    return f"{column}는 {'·'.join(allowed)} 중 하나여야 합니다"


def _exit_before_arrival_message(column: str) -> str:
    return f"{column}은 반입일정보다 빠를 수 없습니다"


def _actual_future_message(column: str, limit: pd.Timestamp) -> str:
    return (
        f"{column}은 오늘({limit:%Y-%m-%d})보다 늦을 수 없습니다 — 실적은 이미 끝난 날을 적습니다"
    )


_DUPLICATE_UNIT = "설비명은 중복될 수 없습니다"
_LOCATION_RANGE = "동은 C1~C5, 층은 1F~6F 범위여야 합니다"
_POSITION_PAIR = "X좌표·Y좌표는 함께 넣거나 함께 비워야 합니다"
_SIZE_PAIR = "Xsize·Ysize는 함께 넣거나 함께 비워야 합니다"
_POSITION_NEEDS_SIZE = "Space 좌표(X좌표·Y좌표)가 있으면 Xsize·Ysize 도 넣어야 합니다"
_LAYOUT_NEEDS_LOCATION = "레이아웃표시 Y 호기에 좌표를 넣으면 동·층도 넣어야 합니다"
_POSITION_NEGATIVE = "Space 좌표(X좌표·Y좌표)는 0 이상이어야 합니다"
_SIZE_NOT_POSITIVE = "Xsize·Ysize는 0 보다 커야 합니다"
_CANVAS_OUTSIDE = "Space 블럭이 층 캔버스 범위를 벗어났습니다"
_RATIO_NOT_POSITIVE = "환산비는 0보다 큰 숫자여야 합니다"
_QUAL_STATUS_REQUIRED = (
    f"Qual일정이 있는 호기(보관·기존설비 제외)는 {QUAL_STATUS_COLUMN}가 필수입니다"
)
_SCHEDULE_ORDER = "제진대·물류·반입·Qual 일정 순서가 올바르지 않습니다"
_EXIT_WITHOUT_ARRIVAL = (
    f"반입일정이 없는 신규 설비에는 {STOP_DATE_COLUMN}·{RELOCATION_DATE_COLUMN}을 넣을 수 없습니다"
)
_STOP_AFTER_EXIT = f"{STOP_DATE_COLUMN}은 {RELOCATION_DATE_COLUMN}보다 늦을 수 없습니다"
_ACTUAL_REVERSED = f"{ARRIVAL_ACTUAL_COLUMN}은 {QUAL_ACTUAL_COLUMN}보다 늦을 수 없습니다"
_AREA_CODE_OUTSIDE = f"{AREA_CODE_COLUMN} 가 {'·'.join(AREA_CODES)} 밖"
_AREA_CODE_CHECK = "저장은 되지만 값을 확인하세요"
_AREA_CODE_CELL = f"{_AREA_CODE_OUTSIDE}입니다 — {_AREA_CODE_CHECK}"
_CASE_VARIANT = (
    "대소문자·앞뒤 공백만 다른 설비명이 함께 있습니다 — 저장은 되지만 같은 설비를 둘로 적었는지 "
    "확인하세요"
)

_STATUS_VALUES: Mapping[str, Sequence[str]] = {
    QUAL_STATUS_COLUMN: QUAL_CONFIRMATION_STATUSES,
    ARRIVAL_STATUS_COLUMN: ARRIVAL_STATUSES,
}

# 신규 호기의 일정 차례. 앞 칸이 뒤 칸보다 늦으면 「차례를 깬 뒤 칸」 에 결과를 단다.
_SCHEDULE_CHAIN = ("제진대일정", "물류일정", ARRIVAL_DATE_COLUMN, QUAL_DATE_COLUMN)


# ------------------------------------------------------------------ 규칙이 보는 표


@dataclass(frozen=True, eq=False)
class _MasterFrame:
    """규칙이 보는 설비 마스터 한 벌. 색인은 넘긴 표의 줄 자리(`iloc`)다.

    - `raw_dates` — 날짜 칸의 입력 값 그대로(날짜 못 읽음의 예시는 입력 글자다).
    - `data` — 칸마다 저장 정규화를 지난 값. **못 읽은 값은 결측**이다 — 저장 함수는 그 칸의
      규칙에서 먼저 멈추므로 결측으로 본 값이 뒤 규칙에 닿지 않고, 모으는 쪽은 결측으로 이어
      본다. 날짜 칸은 늘 시간대 없는 날짜 dtype 이다.
    - `unreadable` — 좌표·크기·환산비·날짜 칸마다 못 읽은 줄.
    """

    raw_dates: pd.DataFrame
    data: pd.DataFrame
    unreadable: Mapping[str, pd.Series]
    ratio_not_positive: pd.Series
    floor_canvases: FloorCanvasMap | None
    today: date | None

    @cached_property
    def placement(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(X좌표·Y좌표 있음, Xsize·Ysize 있음) — 칸마다 참거짓(위치 규칙 일곱이 함께 본다)."""
        return (
            self.data.loc[:, ["X좌표", "Y좌표"]].notna(),
            self.data.loc[:, ["Xsize", "Ysize"]].notna(),
        )

    @cached_property
    def ordinary(self) -> pd.Series:
        """보관·기존설비가 아닌 신규 호기."""
        data = self.data
        return _flags(data[STORAGE_FLAG_COLUMN].eq("N") & data["기존설비여부"].eq("N"))


@dataclass(frozen=True, eq=False)
class _Finding:
    """규칙 하나가 찾은 것 — 저장 거부 예외 하나, 칸 결과 여럿.

    `column` 은 칸 이름 하나이거나 줄마다 대표 칸을 내는 함수(`rows` 와 같은 색인 — 칸 결과를 낼
    때만 부른다). `error` 가 없으면 저장 거부는 `ValueError("{head}: {설비명 예시 5}")` 다.
    `messages` 는 줄마다 다른 칸 문구(캔버스 밖)다.
    """

    rows: pd.Series
    head: str
    column: str | Callable[[], pd.Series]
    error: Callable[[], Exception] | None = None
    messages: pd.Series | None = None


@dataclass(frozen=True)
class MasterRule:
    """설비 마스터 규칙 표의 한 줄 — 코드와 그 규칙이 걸린 줄을 찾는 함수. `blocking` 이 거짓이면
    저장을 막지 않는 경고다(저장 함수는 건너뛰고, 칸 결과는 막는 결과가 있어도 낸다)."""

    code: str
    check: Callable[[_MasterFrame], Iterator[_Finding]] = field(repr=False, compare=False)
    blocking: bool = True


def _read_master(
    data: pd.DataFrame,
    *,
    floor_canvases: FloorCanvasMap | None,
    today: date | None,
) -> _MasterFrame | None:
    """칸을 모두 다듬는다 — 막지 않는다. 설비명이 빈 줄은 뺀다(남는 줄이 없으면 None)."""
    data = with_optional_equipment_columns(data)
    require_columns(data, EQUIPMENT_COLUMNS, "설비 마스터")
    selected = data.loc[:, list(EQUIPMENT_COLUMNS)].reset_index(drop=True)
    raw = _drop_blank_rows(selected, (EQUIPMENT_ID_COLUMN,))
    if raw.empty:
        return None
    raw_dates = raw.loc[:, list(DATE_COLUMNS)]
    result = raw
    for column in (EQUIPMENT_ID_COLUMN, "공정소분류"):
        result[column] = result[column].astype("string").str.strip()
    for column in REFERENCE_TEXT_COLUMNS + ("동", "층"):
        result[column] = _optional_text(result[column])
    result[AREA_CODE_COLUMN] = normalize_area_code(result[AREA_CODE_COLUMN])
    for column in (QUAL_STATUS_COLUMN, ARRIVAL_STATUS_COLUMN, PARENT_EQUIPMENT_COLUMN):
        result[column] = _optional_text(result[column])
    for column in FLAG_COLUMNS:
        result[column] = _flag_text(result[column])
    unreadable: dict[str, pd.Series] = {}
    for column in COORDINATE_COLUMNS:
        result[column], unreadable[column] = _read_number(result[column])
    ratio, unreadable[CONVERSION_RATIO_COLUMN], not_positive = _read_ratio(
        result[CONVERSION_RATIO_COLUMN]
    )
    result[CONVERSION_RATIO_COLUMN] = ratio
    for column in DATE_COLUMNS:
        result[column], unreadable[column] = _read_master_dates(raw_dates[column])
    return _MasterFrame(raw_dates, result, unreadable, not_positive, floor_canvases, today)


def _flags(mask: pd.Series) -> pd.Series:
    """결측 없는 bool 줄. 다듬지 못한 값이 남은 표에서 글자 칸 비교가 결측을 낸다."""
    if mask.dtype == bool:
        return mask
    return mask.fillna(False).astype(bool)


def _hit(
    rows: pd.Series,
    head: str,
    column: str | Callable[[], pd.Series],
    *,
    error: Callable[[], Exception] | None = None,
    messages: pd.Series | None = None,
) -> _Finding:
    return _Finding(_flags(rows), head, column, error, messages)


def _first_column(index: pd.Index, *marks: tuple[pd.Series, str]) -> pd.Series:
    """줄마다 표지가 선 첫 칸(대표 칸 하나). 표지가 없는 줄은 빈 글자다."""
    chosen = np.select(
        [_flags(mask).to_numpy(dtype=bool) for mask, _ in marks],
        [column for _, column in marks],
        default="",
    )
    return pd.Series(chosen, index=index, dtype="object")


def _listed(head: str, examples: Sequence[object]) -> ValueError:
    return ValueError(f"{head}: {list(examples)}")


def _listed_values(head: str, values: pd.Series, rows: pd.Series) -> ValueError:
    """`rows` 줄의 `values` 앞 다섯을 예시로 단 거부 — 거부할 때만 센다."""
    return _listed(head, values.loc[rows].head(5).tolist())


def _duplicate_error(names: pd.Series, duplicated: pd.Series) -> ValueError:
    return _listed(_DUPLICATE_UNIT, names.loc[duplicated].drop_duplicates().head(5).tolist())


def _rejection(master: _MasterFrame, finding: _Finding) -> Exception:
    if finding.error is not None:
        return finding.error()
    examples = master.data.loc[finding.rows, EQUIPMENT_ID_COLUMN].head(5).tolist()
    return _listed(finding.head, examples)


def _finding_issues(
    master: _MasterFrame, rule: MasterRule, finding: _Finding
) -> Iterator[MasterIssue]:
    rows = finding.rows
    if not rows.any():
        return
    picked = master.data.loc[rows]
    count = len(picked)
    columns = (
        [finding.column] * count
        if isinstance(finding.column, str)
        else finding.column().loc[rows].tolist()
    )
    messages = (
        [finding.head] * count if finding.messages is None else finding.messages.loc[rows].tolist()
    )
    for position, unit, column, message in zip(
        picked.index.tolist(),
        picked[EQUIPMENT_ID_COLUMN].tolist(),
        columns,
        messages,
        strict=True,
    ):
        yield MasterIssue(
            position=int(position),
            unit=str(unit),
            column=str(column),
            rule=rule.code,
            message=str(message),
            blocking=rule.blocking,
        )


# ------------------------------------------------------------------ 규칙 — 표 차례대로


def _check_required_text(master: _MasterFrame) -> Iterator[_Finding]:
    # 설비명이 빈 줄은 읽을 때 이미 빠졌다 — 남은 필수 글은 공정소분류 하나다.
    values = master.data["공정소분류"]
    head = _missing_text_message("설비 마스터", "공정소분류")
    yield _hit(
        values.isna() | values.eq(""),
        head,
        "공정소분류",
        error=partial(ValueError, f"{head}."),
    )


def _check_duplicate_units(master: _MasterFrame) -> Iterator[_Finding]:
    names = master.data[EQUIPMENT_ID_COLUMN]
    duplicated = names.duplicated(keep=False)
    yield _hit(
        duplicated,
        _DUPLICATE_UNIT,
        EQUIPMENT_ID_COLUMN,
        error=partial(_duplicate_error, names, duplicated),
    )


def _check_unit_group_collision(master: _MasterFrame) -> Iterator[_Finding]:
    """Main 설비는 다른 행의 설비명과 같을 수 없다. 설비 행(APW01)과 모듈 행(APW01A~D)을 함께
    두면 같은 설비가 두 번 세어진다. 칸 결과는 모듈 행의 Main 설비와 설비 행의 설비명이다."""
    result = master.data
    parents = result[PARENT_EQUIPMENT_COLUMN]
    named = parents.notna()
    if not named.any():
        return
    # 자기 호기를 적은 것은 무해하다(묶음 1행 = 지분 1). 다른 행의 호기를 가리킬 때만 막는다.
    units = result[EQUIPMENT_ID_COLUMN].astype("string")
    colliding = _flags(named & parents.isin(set(units)) & parents.ne(units))
    if not colliding.any():
        return
    collisions: dict[str, tuple[str, ...]] = {}
    for parent, module in zip(parents.loc[colliding], units.loc[colliding], strict=True):
        collisions[str(parent)] = (*collisions.get(str(parent), ()), str(module))
    targets = _flags(units.isin(set(collisions)))
    yield _hit(
        colliding | targets,
        _COLLISION_HEAD,
        partial(
            _first_column,
            result.index,
            (colliding, PARENT_EQUIPMENT_COLUMN),
            (targets, EQUIPMENT_ID_COLUMN),
        ),
        error=partial(UnitGroupCollisionError, collisions),
    )


def _check_unit_group_mixed(master: _MasterFrame) -> Iterator[_Finding]:
    """한 설비의 모듈 행끼리 공정·공정구분·투자구분·동·층이 같아야 한다. 화면 필터가 이 값들로
    행을 거르므로, 다르면 필터가 설비를 쪼개 지분 합이 1 이 아니게 된다. 칸 결과는 묶음 모든 줄의
    그 칸이다."""
    result = master.data
    parents = result[PARENT_EQUIPMENT_COLUMN]
    named = parents.notna()
    if not named.any():
        return
    keys = parents.where(named, result[EQUIPMENT_ID_COLUMN])
    for column in UNIT_CONSISTENT_COLUMNS:
        values = result[column].astype("string").fillna("")
        mixed = values.groupby(keys).nunique().gt(1)
        groups = mixed.loc[mixed].index
        head = _unit_group_mixed_message(column)
        yield _hit(
            keys.isin(groups),
            head,
            column,
            error=partial(_listed, head, groups.tolist()[:5]),
        )


def _check_flags(master: _MasterFrame) -> Iterator[_Finding]:
    for column in FLAG_COLUMNS:
        yield _hit(~master.data[column].isin(["Y", "N"]), _flag_message(column), column)


def _check_numbers(master: _MasterFrame) -> Iterator[_Finding]:
    for column in COORDINATE_COLUMNS:
        yield _hit(master.unreadable[column], _number_message(column), column)


# Space 위치 계약(아래 여섯 규칙과 캔버스 밖).
#
# 레이아웃표시는 「도면 대상인가」만 가른다 — Y 인데 좌표가 없으면 Space 편집기의 미배치 트레이에
# 뜨고, 동·층까지 비면 모든 층 트레이에 뜬다. 크기만 있고 X·Y 가 없는 행도 받는다(트레이로 빼도
# 실제 설비 치수를 지킨다, 2026-10-01 사용자 결정).
#
# - X좌표·Y좌표는 함께, Xsize·Ysize 도 함께 넣거나 비운다.
# - X·Y 가 있으면 크기도 있어야 한다. 레이아웃표시 Y 면 동·층도 있어야 한다. N 행은 예전처럼 동·층
#   없이 좌표만 있어도 받는다 — 그런 행이 든 리비전이 다시 읽힐 때 막히지 않게.
# - 부호는 있는 값마다 본다(X·Y ≥ 0, 크기 > 0). 캔버스 상한은 X·Y 가 있는 행에만 건다.
#
# 과거 리비전을 다시 읽을 때도 이 검사를 탄다. 그래서 **풀기만 하고 다시 조이지 않는다** — 조이면
# 그 사이에 저장된 리비전이 열리지 않는다.


def _check_location_range(master: _MasterFrame) -> Iterator[_Finding]:
    result = master.data
    building = result["동"].notna() & ~result["동"].isin(VALID_BUILDINGS)
    floor = result["층"].notna() & ~result["층"].isin(VALID_FLOORS)
    yield _hit(
        building | floor,
        _LOCATION_RANGE,
        partial(_first_column, result.index, (building, "동"), (floor, "층")),
    )


def _check_position_pair(master: _MasterFrame) -> Iterator[_Finding]:
    position, _ = master.placement
    yield _hit(
        position.any(axis=1) & ~position.all(axis=1),
        _POSITION_PAIR,
        partial(
            _first_column,
            position.index,
            (~position["X좌표"], "X좌표"),
            (~position["Y좌표"], "Y좌표"),
        ),
    )


def _check_size_pair(master: _MasterFrame) -> Iterator[_Finding]:
    _, size = master.placement
    yield _hit(
        size.any(axis=1) & ~size.all(axis=1),
        _SIZE_PAIR,
        partial(_first_column, size.index, (~size["Xsize"], "Xsize"), (~size["Ysize"], "Ysize")),
    )


def _check_position_needs_size(master: _MasterFrame) -> Iterator[_Finding]:
    position, size = master.placement
    yield _hit(position.all(axis=1) & ~size.all(axis=1), _POSITION_NEEDS_SIZE, "Xsize")


def _check_layout_needs_location(master: _MasterFrame) -> Iterator[_Finding]:
    result = master.data
    position, _ = master.placement
    no_building = result["동"].isna()
    no_floor = result["층"].isna()
    yield _hit(
        position.all(axis=1) & result["레이아웃표시"].eq("Y") & (no_building | no_floor),
        _LAYOUT_NEEDS_LOCATION,
        partial(_first_column, result.index, (no_building, "동"), (no_floor, "층")),
    )


def _check_position_negative(master: _MasterFrame) -> Iterator[_Finding]:
    result = master.data
    position, _ = master.placement
    x_negative = result["X좌표"].lt(0)
    y_negative = result["Y좌표"].lt(0)
    yield _hit(
        position.all(axis=1) & (x_negative | y_negative),
        _POSITION_NEGATIVE,
        partial(_first_column, result.index, (x_negative, "X좌표"), (y_negative, "Y좌표")),
    )


def _check_size_not_positive(master: _MasterFrame) -> Iterator[_Finding]:
    result = master.data
    _, size = master.placement
    x_flat = result["Xsize"].le(0)
    y_flat = result["Ysize"].le(0)
    yield _hit(
        size.all(axis=1) & (x_flat | y_flat),
        _SIZE_NOT_POSITIVE,
        partial(_first_column, result.index, (x_flat, "Xsize"), (y_flat, "Ysize")),
    )


def _check_canvas(master: _MasterFrame) -> Iterator[_Finding]:
    floor_canvases = master.floor_canvases
    if floor_canvases is None:
        return
    result = master.data
    position, size = master.placement
    complete = position.all(axis=1) & size.all(axis=1)
    limit_width, limit_height = _canvas_limits(result, floor_canvases)
    outside = _flags(complete & _beyond_canvas(result, limit_width, limit_height))
    yield _hit(
        outside,
        _CANVAS_OUTSIDE,
        "X좌표",
        error=partial(_outside_canvas_error, result, outside, complete, floor_canvases),
        messages=_outside_canvas_cells(result, outside, floor_canvases) if outside.any() else None,
    )


def _check_ratio_unreadable(master: _MasterFrame) -> Iterator[_Finding]:
    column = CONVERSION_RATIO_COLUMN
    yield _hit(master.unreadable[column], _number_message(column), column)


def _check_ratio_not_positive(master: _MasterFrame) -> Iterator[_Finding]:
    yield _hit(master.ratio_not_positive, _RATIO_NOT_POSITIVE, CONVERSION_RATIO_COLUMN)


def _check_dates(master: _MasterFrame) -> Iterator[_Finding]:
    for column in DATE_COLUMNS:
        head = _date_message(column)
        invalid = _flags(master.unreadable[column])
        # 예시는 입력 글자다 — 칸에서 무엇을 고칠지 보이게(시간대 붙은 값도 그 글자).
        entered = master.raw_dates[column]
        yield _hit(invalid, head, column, error=partial(_listed_values, head, entered, invalid))


def _check_qual_status_required(master: _MasterFrame) -> Iterator[_Finding]:
    # 반입·Qual 일정은 비워도 된다(2026-10-06 사용자 결정) — 반입이 비면 「입고 예정」, 반입만 있고
    # Qual 이 비면 「셋업 진행중」에 머물러 날짜가 들어올 때까지 가용대수에 들지 않는다. Qual상태는
    # Qual 일정의 진행 상태 값이라 Qual일정이 있는 신규 호기에만 필수다.
    result = master.data
    yield _hit(
        master.ordinary & result[QUAL_DATE_COLUMN].notna() & result[QUAL_STATUS_COLUMN].isna(),
        _QUAL_STATUS_REQUIRED,
        QUAL_STATUS_COLUMN,
    )


def _check_status_values(master: _MasterFrame) -> Iterator[_Finding]:
    # 반입상태는 새 선택 컬럼이라 옛 리비전에 값이 없다 — 리비전을 다시 읽을 때 돌아도 막히지
    # 않는다.
    for column, allowed in _STATUS_VALUES.items():
        values = master.data[column]
        yield _hit(values.notna() & ~values.isin(allowed), _status_message(column, allowed), column)


def _check_schedule_order(master: _MasterFrame) -> Iterator[_Finding]:
    result = master.data
    breaks = {
        column: pd.Series(False, index=result.index, dtype=bool) for column in _SCHEDULE_CHAIN[1:]
    }
    # 반입 ≤ Qual — 모든 호기.
    breaks[QUAL_DATE_COLUMN] |= (
        result[ARRIVAL_DATE_COLUMN].notna()
        & result[QUAL_DATE_COLUMN].notna()
        & result[QUAL_DATE_COLUMN].lt(result[ARRIVAL_DATE_COLUMN])
    )
    # 제진대 ≤ 물류 ≤ 반입 — 이웃한 둘이 모두 있을 때만(모든 호기).
    for column, broken in _neighbour_order_breaks(result, _SCHEDULE_CHAIN[:3]).items():
        breaks[column] |= broken
    # 신규 호기는 빈 일정을 건너뛰고 **있는 날짜끼리** 차례를 본다 — 반입이 비어도 물류 ≤ Qual
    # 이다. 보관·기존설비는 예전처럼 이웃한 둘만 본다(그런 저장본이 다시 열려야 한다). 신규 호기는
    # 이 규칙이 생기기 전에 반입·Qual 이 필수였으므로 이미 저장된 리비전이 새로 막히지 않는다.
    ordinary = master.ordinary
    for column, broken in _present_order_breaks(result, _SCHEDULE_CHAIN).items():
        breaks[column] |= ordinary & broken
    rows = pd.Series(False, index=result.index, dtype=bool)
    for broken in breaks.values():
        rows |= broken
    yield _hit(
        rows,
        _SCHEDULE_ORDER,
        partial(
            _first_column, result.index, *((broken, column) for column, broken in breaks.items())
        ),
    )


def _check_exit_without_arrival(master: _MasterFrame) -> Iterator[_Finding]:
    # 들어온 적 없는 신규 호기를 내보낼 수는 없다. 받아 두면 반입 없이 「반출/이설 완료」가 되어
    # 어느 대수에도 들지 않고 일정 미정 알림에서도 빠진다.
    result = master.data
    exits = result.loc[:, list(EXIT_SCHEDULE_COLUMNS)].notna()
    yield _hit(
        master.ordinary & result[ARRIVAL_DATE_COLUMN].isna() & exits.any(axis=1),
        _EXIT_WITHOUT_ARRIVAL,
        partial(
            _first_column,
            result.index,
            *((exits[column], column) for column in EXIT_SCHEDULE_COLUMNS),
        ),
    )


def _check_stop_after_exit(master: _MasterFrame) -> Iterator[_Finding]:
    # 두 날짜를 함께 적을 수 있다(2026-10-16 사용자 결정) — 정지한 뒤 자리를 비운다. 거꾸로면 집계
    # 이탈일(둘 중 이른 날)과 도면 이탈일(반출/이설일정)의 뜻이 어긋난다.
    result = master.data
    stop = result[STOP_DATE_COLUMN]
    relocation = result[RELOCATION_DATE_COLUMN]
    yield _hit(
        stop.notna() & relocation.notna() & stop.gt(relocation),
        _STOP_AFTER_EXIT,
        STOP_DATE_COLUMN,
    )


def _check_exit_before_arrival(master: _MasterFrame) -> Iterator[_Finding]:
    result = master.data
    arrival = result[ARRIVAL_DATE_COLUMN]
    for column in EXIT_SCHEDULE_COLUMNS:
        values = result[column]
        yield _hit(
            values.notna() & arrival.notna() & values.lt(arrival),
            _exit_before_arrival_message(column),
            column,
        )


def _check_actual_future(master: _MasterFrame) -> Iterator[_Finding]:
    # 저장할 때만 돈다(`today`). 실적은 이미 일어난 날이라 오늘보다 늦을 수 없다.
    if master.today is None:
        return
    limit = pd.Timestamp(master.today)
    for column in (ARRIVAL_ACTUAL_COLUMN, QUAL_ACTUAL_COLUMN):
        values = master.data[column]
        yield _hit(values.notna() & values.gt(limit), _actual_future_message(column, limit), column)


def _check_actual_reversed(master: _MasterFrame) -> Iterator[_Finding]:
    # 저장할 때만 돈다(`today`). Qual 은 반입한 뒤에 끝난다.
    if master.today is None:
        return
    arrival = master.data[ARRIVAL_ACTUAL_COLUMN]
    qual = master.data[QUAL_ACTUAL_COLUMN]
    yield _hit(
        arrival.notna() & qual.notna() & arrival.gt(qual),
        _ACTUAL_REVERSED,
        ARRIVAL_ACTUAL_COLUMN,
    )


def _check_area_code(master: _MasterFrame) -> Iterator[_Finding]:
    yield _hit(area_code_warning_rows(master.data), _AREA_CODE_CELL, AREA_CODE_COLUMN)


def _check_case_variants(master: _MasterFrame) -> Iterator[_Finding]:
    yield _hit(
        unit_case_variant_rows(master.data[EQUIPMENT_ID_COLUMN]),
        _CASE_VARIANT,
        EQUIPMENT_ID_COLUMN,
    )


def _check_module_ratio(master: _MasterFrame) -> Iterator[_Finding]:
    yield _hit(
        module_ratio_warning_rows(master.data), MODULE_RATIO_WARNING, CONVERSION_RATIO_COLUMN
    )


# 규칙 표. **차례가 계약이다** — 저장 함수는 이 차례로 처음 걸린 규칙 하나를 던지고(기존 시험이 그
# 문구를 본다), 칸 결과도 이 차례로 낸다. 리비전을 다시 읽을 때도 이 표를 지나므로 **규칙을 조이지
# 않는다** — 새 규칙은 기존 저장본이 새로 막히지 않게 걸고, 날짜에 기대는 규칙은 `today` 를 줄 때만
# 돈다. 줄 끝 주석은 칸 결과의 대표 칸이다.
MASTER_RULES: tuple[MasterRule, ...] = (
    MasterRule("required_text", _check_required_text),  # 공정소분류
    MasterRule("duplicate_unit", _check_duplicate_units),  # 설비명(겹친 줄 모두)
    MasterRule("unit_group_collision", _check_unit_group_collision),  # Main 설비 / 설비명
    MasterRule("unit_group_mixed", _check_unit_group_mixed),  # 갈린 칸, 묶음 모든 줄
    MasterRule("flag", _check_flags),  # 그 Y/N 칸
    MasterRule("number_unreadable", _check_numbers),  # 그 좌표·크기 칸
    MasterRule("location_range", _check_location_range),  # 동 또는 층
    MasterRule("position_pair", _check_position_pair),  # 빈 쪽
    MasterRule("size_pair", _check_size_pair),  # 빈 쪽
    MasterRule("position_needs_size", _check_position_needs_size),  # Xsize
    MasterRule("layout_needs_location", _check_layout_needs_location),  # 빈 쪽(동 먼저)
    MasterRule("position_negative", _check_position_negative),  # 그 칸(X 먼저)
    MasterRule("size_not_positive", _check_size_not_positive),  # 그 칸(Xsize 먼저)
    MasterRule("canvas_outside", _check_canvas),  # X좌표(`floor_canvases` 줄 때만)
    MasterRule("ratio_unreadable", _check_ratio_unreadable),  # 환산비
    MasterRule("ratio_not_positive", _check_ratio_not_positive),  # 환산비
    MasterRule("date_unreadable", _check_dates),  # 그 날짜 칸
    MasterRule("qual_status_required", _check_qual_status_required),  # Qual상태
    MasterRule("status_value", _check_status_values),  # 그 상태 칸
    MasterRule("schedule_order", _check_schedule_order),  # 차례를 깬 뒤 칸
    MasterRule("exit_without_arrival", _check_exit_without_arrival),  # 찬 쪽(정지일정 먼저)
    MasterRule("stop_after_exit", _check_stop_after_exit),  # 정지일정
    MasterRule("exit_before_arrival", _check_exit_before_arrival),  # 그 반출 칸
    MasterRule("actual_future", _check_actual_future),  # 그 실적 칸(`today` 줄 때만)
    MasterRule("actual_reversed", _check_actual_reversed),  # 반입실적(`today` 줄 때만)
    MasterRule("area_code_unknown", _check_area_code, blocking=False),  # Area Code
    MasterRule("unit_case_variant", _check_case_variants, blocking=False),  # 설비명
    MasterRule("module_ratio_default", _check_module_ratio, blocking=False),  # 묶음 줄들의 환산비
)


def area_code_warning_rows(equipment: pd.DataFrame) -> pd.Series:
    """Area Code 가 Main·MI·부대 밖인 줄 — `equipment` 와 같은 색인의 참거짓.

    칸 단위 결과(`area_code_unknown`)와 경고 문장(`area_code_warnings`)이 이 판정 하나를 본다.
    검증 전 편집본도 받는다(칸이 없으면 모두 거짓). 설비명이 빈 줄은 저장이 조용히 빼므로 세지
    않는다 — 저장되지 않을 줄을 「확인하세요」 라고 하지 않는다.
    """
    if AREA_CODE_COLUMN not in equipment.columns:
        return pd.Series(False, index=equipment.index, dtype=bool)
    unknown = unknown_area_codes(equipment[AREA_CODE_COLUMN]).to_numpy(dtype=bool)
    if EQUIPMENT_ID_COLUMN in equipment.columns:
        names = equipment[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
        unknown = unknown & _flags(names.notna() & names.ne("")).to_numpy(dtype=bool)
    return pd.Series(unknown, index=equipment.index, dtype=bool)


def area_code_warnings(equipment: pd.DataFrame) -> list[str]:
    """Area Code 가 Main·MI·부대 밖인 호기를 알리는 경고(저장은 막지 않는다). 검증 전 편집본도
    받는다 — 컬럼이 없거나 표가 비면 빈 목록이다. 칸 단위 결과(`equipment_master_issues` 의
    `area_code_unknown`)와 같은 줄 판정(`area_code_warning_rows`)·같은 문구 조각이다."""
    if equipment.empty:
        return []
    unknown = area_code_warning_rows(equipment).to_numpy(dtype=bool)
    if not unknown.any():
        return []
    rows = equipment.loc[unknown]
    names = (
        rows[EQUIPMENT_ID_COLUMN].astype("string").fillna("").str.strip().tolist()
        if EQUIPMENT_ID_COLUMN in rows.columns
        else []
    )
    values = sorted({str(value).strip() for value in rows[AREA_CODE_COLUMN].tolist()})
    return [
        f"{_AREA_CODE_OUTSIDE}인 호기 {len(rows):,}건 — {_AREA_CODE_CHECK}"
        f"({', '.join(values[:5])}): {names[:5]}"
    ]


_COLLISION_EXAMPLES = 5
_COLLISION_HEAD = (
    "Main 설비는 다른 행의 설비명과 같을 수 없습니다 — 설비 행과 그 설비를 Main 설비로 적은 모듈 "
    "행을 함께 두면 같은 설비가 두 번 세어집니다"
)


class UnitGroupCollisionError(ValueError):
    """Main 설비가 다른 행의 설비명과 같다. `collisions` 는 {설비 행 이름: 그 이름을 Main 설비로
    적은 모듈 행 이름들}이다.

    문구만으로는 어느 쪽이 붙여넣은 행인지 모른다 — 검증은 병합된 표 하나만 보기 때문이다.
    붙여넣기 미리보기는 이 예외를 잡아 양쪽의 출처를 붙인 문구(`unit_group_collision_message`)로
    다시 알린다. 문자열을 다시 읽지 않도록 이름을 그대로 싣는다.
    """

    def __init__(self, collisions: Mapping[str, Sequence[str]]) -> None:
        self.collisions = {parent: tuple(modules) for parent, modules in collisions.items()}
        super().__init__(unit_group_collision_message(self.collisions))

    def __reduce__(self) -> tuple[type[UnitGroupCollisionError], tuple[dict[str, tuple[str, ...]]]]:
        return (type(self), (self.collisions,))


def unit_group_collision_message(
    collisions: Mapping[str, Sequence[str]],
    *,
    pasted: Collection[str] | None = None,
    existing: Collection[str] = (),
) -> str:
    """충돌한 **양쪽 설비명**(설비 행과 그 이름을 Main 설비로 적은 모듈 행)을 적은 오류 문구.

    `pasted` 가 없으면 저장 경로다 — 두 행이 모두 지금 편집본에 있으니 한쪽을 지우라고
    한다. `pasted`(붙여넣은 표의 설비명)를 주면 붙여넣기 미리보기다. `existing` 은 붙여넣기 **전**
    편집본의 설비명이다. 이름마다 출처를 붙인다 — 붙여넣기에만 있으면 (붙여넣기), 편집본에만
    있으면 (편집본), 둘 다에 있으면 (붙여넣기·편집본). 둘 다에 있는 이름은 한 곳에서만 빼면 다시
    막히므로 그렇게 적는다. 고칠 길은 출처를 따른다(2026-10-08 점검 A3·리뷰, 사내 AWB05 와 같은
    꼴: 모듈 행이 저장된 설비의 설비 행을 다시 붙여넣었다).

    - 붙여넣은 이름이 충돌에 하나도 없다 — 편집본 안에서 이미 부딪힌 것이다. 붙여넣기와 상관없으니
      설비 마스터 표(「선택 n대 지우기」·호기 상세 「이 호기 지우기」)에서 한쪽을 지우라고만 한다.
    - 충돌한 이름이 모두 붙여넣기에만 있다 — 붙여넣을 표 안에서 부딪혔다. 그 표를 고친다.
    - 그 밖 — **붙여넣기는 설비명 기준으로 행을 더하거나 바꿀 뿐 이미 있는(편집본의) 행을 지우지
      않는다.** 편집본 쪽 행을 없애는 길은 설비 마스터 표의 지우기뿐이다.
    """
    shown = list(collisions.items())[:_COLLISION_EXAMPLES]
    pasted_names = set(pasted) if pasted is not None else None
    existing_names = set(existing)

    def origin_of(value: str) -> str:
        assert pasted_names is not None
        if value in pasted_names:
            return "붙여넣기·편집본" if value in existing_names else "붙여넣기"
        return "편집본"

    def names(values: Sequence[str]) -> str:
        if pasted_names is None:
            return ", ".join(values)
        groups: list[tuple[str, list[str]]] = []
        for value in values:
            origin = origin_of(value)
            if groups and groups[-1][0] == origin:
                groups[-1][1].append(value)
            else:
                groups.append((origin, [value]))
        return ", ".join(f"{', '.join(group)}({origin})" for origin, group in groups)

    pairs = " / ".join(
        f"설비 행 {names([parent])} · 모듈 행 {names(modules)}" for parent, modules in shown
    )
    more = f" 외 {len(collisions) - len(shown)}건" if len(collisions) > len(shown) else ""
    if pasted_names is None:
        remedy = (
            "한쪽만 남기세요 — 모듈로 나눠 세려면 설비 행을, 한 대로 세려면 모듈 행을 지우거나 "
            "그 행의 Main 설비를 비웁니다."
        )
    else:
        every = {*collisions, *(module for modules in collisions.values() for module in modules)}
        if not every & pasted_names:
            remedy = (
                "붙여넣기 전 편집본에 이미 있던 충돌입니다 — 설비 마스터 표에서 한쪽을 지운 뒤 "
                "다시 미리보세요."
            )
        elif every <= pasted_names - existing_names:
            remedy = "붙여넣을 표에서 한쪽을 빼고 다시 미리보세요."
        else:
            remedy = (
                "붙여넣기는 이미 있는(편집본의) 행을 지우지 않습니다 — 편집본 쪽 행을 없애려면 "
                "설비 마스터 표에서 지운 뒤 다시 미리보세요. 붙여넣은 쪽이 잘못이면 그 행을 빼고 "
                "다시 붙여넣으세요."
            )
            if every & pasted_names & existing_names:
                remedy += " (붙여넣기·편집본) 이름은 두 곳 모두에서 빼야 합니다."
    return f"{_COLLISION_HEAD}: {pairs}{more}. {remedy}"


def prepare_downtime_schedule(
    data: pd.DataFrame,
    *,
    equipment: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Normalize downtime intervals keyed by equipment, type, and start date."""
    require_columns(data, DOWNTIME_COLUMNS, "비가동 일정")
    result = data.loc[:, DOWNTIME_COLUMNS].copy()
    result = _drop_blank_rows(result, DOWNTIME_KEY_COLUMNS)
    if result.empty:
        return empty_downtime_schedule()
    _normalize_required_text(result, (EQUIPMENT_ID_COLUMN, "비가동유형"), "비가동 일정")
    for column in ("상세사유", "비고"):
        result[column] = _optional_text(result[column])
    result["시작일"] = _normalize_date(result["시작일"], "시작일")
    result["종료일"] = _normalize_date(result["종료일"], "종료일")
    if result["시작일"].isna().any():
        raise ValueError("모든 비가동 일정에 시작일을 입력해야 합니다.")
    duplicated = result.duplicated(list(DOWNTIME_KEY_COLUMNS), keep=False)
    if duplicated.any():
        examples = _key_examples(result.loc[duplicated], DOWNTIME_KEY_COLUMNS)
        raise ValueError(f"설비명·비가동유형·시작일이 중복되었습니다: {examples}")
    invalid_end = result["종료일"].notna() & result["종료일"].lt(result["시작일"])
    if invalid_end.any():
        examples = _key_examples(result.loc[invalid_end], DOWNTIME_KEY_COLUMNS)
        raise ValueError(f"비가동 종료일은 시작일보다 빠를 수 없습니다: {examples}")
    if equipment is not None:
        prepared_equipment = prepare_equipment_master(equipment)
        _validate_downtime_equipment(result, prepared_equipment)
    return result.reset_index(drop=True)


def _validate_downtime_equipment(
    prepared_downtime: pd.DataFrame,
    prepared_equipment: pd.DataFrame,
) -> None:
    unknown = prepared_downtime.loc[
        ~prepared_downtime[EQUIPMENT_ID_COLUMN].isin(prepared_equipment[EQUIPMENT_ID_COLUMN]),
        EQUIPMENT_ID_COLUMN,
    ]
    if not unknown.empty:
        examples = unknown.drop_duplicates().head(5).tolist()
        raise ValueError(f"설비 마스터에 없는 설비의 비가동 일정이 있습니다: {examples}")


def prepare_downtime_for_prepared_equipment(
    downtime: pd.DataFrame,
    prepared_equipment: pd.DataFrame,
) -> pd.DataFrame:
    """Validate downtime against an equipment frame normalized by this module."""
    prepared_downtime = prepare_downtime_schedule(downtime)
    _validate_downtime_equipment(prepared_downtime, prepared_equipment)
    return prepared_downtime


def floor_equipment_outside_canvas(
    equipment: pd.DataFrame, floor: FloorKey, canvas: CanvasSize
) -> list[str]:
    """그 동·층 호기 가운데 블럭(좌표 + 크기)이 `canvas` 를 벗어나는 설비명(표 차례).

    저장 검증(규칙 `canvas_outside`)과 **같은 행, 같은 판정**이다 — 레이아웃표시·
    상태·화면 필터와 무관하게 그 층에서 좌표·크기가 다 있는 행을 모두 본다. 층 캔버스를 바꾸는
    화면(Space `도면·캔버스 편집` 팝업)이 저장된 마스터를 넘겨, 그 캔버스로 바꾸면 다음 설비 저장이
    「캔버스 밖」으로 막히는지 미리 잰다. 화면에 그린 행만 넘기면 안 보이는 호기를 놓친다.
    """
    if equipment.empty or not {"동", "층", *COORDINATE_COLUMNS} <= set(equipment.columns):
        return []
    numeric = equipment.loc[:, list(COORDINATE_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    on_floor = (
        equipment["동"].astype("string").eq(floor[0]).fillna(False)
        & equipment["층"].astype("string").eq(floor[1]).fillna(False)
        & numeric.notna().all(axis=1)
    )
    outside = on_floor & _beyond_canvas(numeric, float(canvas[0]), float(canvas[1]))
    return [str(name) for name in equipment.loc[outside, EQUIPMENT_ID_COLUMN]]


def _beyond_canvas(
    frame: pd.DataFrame, width: pd.Series | float, height: pd.Series | float
) -> pd.Series:
    """블럭 끝이 캔버스 폭·높이를 넘는 행. 끝 좌표는 저장 정밀도로 반올림해 견준다 — 편집기가
    캔버스 끝에 붙여 놓은 호기(88.7 + 11.3)가 부동소수 합(100.00000000000001)으로 「밖」이 되지
    않게(푸는 쪽이라 과거 리비전도 열린다)."""
    right = frame["X좌표"].add(frame["Xsize"]).round(CANVAS_DECIMALS)
    top = frame["Y좌표"].add(frame["Ysize"]).round(CANVAS_DECIMALS)
    return right.gt(width) | top.gt(height)


def _outside_canvas_error(
    result: pd.DataFrame,
    outside: pd.Series,
    complete: pd.Series,
    floor_canvases: FloorCanvasMap,
) -> ValueError:
    return ValueError(_outside_canvas_message(result, outside, complete, floor_canvases))


def _outside_canvas_message(
    result: pd.DataFrame,
    outside: pd.Series,
    complete: pd.Series,
    floor_canvases: FloorCanvasMap,
) -> str:
    """캔버스를 벗어난 호기를 동·층별로 묶어 **원인과 고칠 곳**까지 적는다.

    누가 층 캔버스를 줄여 두면, 뒤에 다른 사람이 무관한 기존보유대수 한 칸만 고쳐 저장해도
    설비 마스터 전체 검증이 이 오류로 막힌다. 예전 문구는 호기 이름만 적어서 원인이 캔버스
    라는 것도, 어디서 고치는지도 알 수 없었다(2026-09-29 버그 보고). 검사 범위는 그대로
    두고(바뀐 행만 보면 검증이 약해진다) 문구만 넓힌다 — 층 이름·캔버스 크기·그 층 호기를
    담는 데 필요한 크기·해결 방법.
    """
    floors: list[str] = []
    outside_rows = result.loc[outside]
    for (raw_building, raw_floor), rows in outside_rows.groupby(
        ["동", "층"], dropna=False, sort=True
    ):
        building, floor = _text_or_none(raw_building), _text_or_none(raw_floor)
        unplaced = building is None or floor is None
        stored = None if unplaced else floor_canvases.get((str(building), str(floor)))
        width, height = (
            stored if stored is not None else (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
        )
        on_floor = complete & _same_value(result["동"], building) & _same_value(result["층"], floor)
        right = result.loc[on_floor, "X좌표"].add(result.loc[on_floor, "Xsize"]).max()
        top = result.loc[on_floor, "Y좌표"].add(result.loc[on_floor, "Ysize"]).max()
        need_width = max(width, round(float(right), CANVAS_DECIMALS))
        need_height = max(height, round(float(top), CANVAS_DECIMALS))
        label = "동·층 미지정" if unplaced else f"{building} {floor}"
        source = "" if stored is not None else "(저장된 캔버스 없음 · 기본값)"
        examples = rows[EQUIPMENT_ID_COLUMN].head(5).tolist()
        floors.append(
            f"{label} 캔버스 {width:g} × {height:g}{source} — 이 층 호기를 모두 담으려면 "
            f"{need_width:g} × {need_height:g} 이상: {examples}"
        )
    return (
        f"{_CANVAS_OUTSIDE} — 그 동·층의 캔버스가 호기 좌표보다 "
        f"좁습니다. {'; '.join(floors[:3])}. 설비 마스터 저장은 모든 호기를 한 번에 검증하므로 "
        "그 층과 무관한 칸만 고쳐도 같은 오류로 막힙니다. Space 현황의 그 동·층 상세 레이아웃에서 "
        "「도면·캔버스 편집」으로 캔버스를 넓히거나, 가용설비 현황에서 그 호기의 X좌표·Y좌표·"
        "Xsize·Ysize 를 고치세요."
    )


def _outside_canvas_cells(
    result: pd.DataFrame, outside: pd.Series, floor_canvases: FloorCanvasMap
) -> pd.Series:
    """캔버스 밖 줄마다 칸 문구 — 그 줄의 동·층 캔버스 크기(저장 문구와 같은 캔버스·같은 기본값)."""
    messages = pd.Series("", index=result.index, dtype="object")
    for label in result.index[outside.to_numpy(dtype=bool)].tolist():
        building = _text_or_none(result.at[label, "동"])
        floor = _text_or_none(result.at[label, "층"])
        unplaced = building is None or floor is None
        stored = None if unplaced else floor_canvases.get((str(building), str(floor)))
        width, height = (
            stored if stored is not None else (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)
        )
        place = "동·층 미지정" if unplaced else f"{building} {floor}"
        messages.at[label] = (
            f"{place} 캔버스 {width:g} × {height:g} 밖 — 캔버스를 넓히거나 좌표를 고칩니다"
        )
    return messages


def _text_or_none(value: Any) -> str | None:
    """groupby 키를 글자로 바꾼다. 결측(`dropna=False` 가 남긴 NA)은 `None` 이다."""
    return None if pd.isna(value) else str(value)


def _same_value(column: pd.Series, value: str | None) -> pd.Series:
    """`value` 가 `None` 이면 결측 행을, 아니면 같은 값인 행을 참으로 돌려준다."""
    if value is None:
        return column.isna()
    return column.eq(value).fillna(False).astype(bool)


def _canvas_limits(
    result: pd.DataFrame,
    floor_canvases: FloorCanvasMap,
) -> tuple[pd.Series, pd.Series]:
    width = pd.Series(DEFAULT_CANVAS_WIDTH, index=result.index, dtype="float64")
    height = pd.Series(DEFAULT_CANVAS_HEIGHT, index=result.index, dtype="float64")
    for (building, floor), (canvas_width, canvas_height) in floor_canvases.items():
        matched = result["동"].eq(building) & result["층"].eq(floor)
        width = width.mask(matched, canvas_width)
        height = height.mask(matched, canvas_height)
    return width, height


def _neighbour_order_breaks(data: pd.DataFrame, columns: tuple[str, ...]) -> dict[str, pd.Series]:
    """이웃한 두 칸이 모두 있고 뒤 칸이 앞 칸보다 이른 줄 — 뒤 칸 이름마다."""
    return {
        right: data[left].notna() & data[right].notna() & data[right].lt(data[left])
        for left, right in zip(columns, columns[1:], strict=False)
    }


def _present_order_breaks(data: pd.DataFrame, columns: tuple[str, ...]) -> dict[str, pd.Series]:
    """빈 칸을 건너뛰고 있는 날짜를 바로 앞의 **있는** 날짜와 견준다(앞이 더 늦으면 참) — 칸마다."""
    breaks: dict[str, pd.Series] = {}
    previous = data[columns[0]]
    for column in columns[1:]:
        current = data[column]
        breaks[column] = current.notna() & previous.notna() & current.lt(previous)
        previous = current.where(current.notna(), previous)
    return breaks


def _blank_numbers(raw: pd.Series) -> pd.Series:
    return raw.isna() | raw.astype("string").str.strip().isin(["", "nan", "None", "<NA>"])


def _read_ratio(raw: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """환산비를 양수 실수로 읽는다 — (값, 못 읽은 줄, 0 이하인 줄). 빈 칸은 기준 모델(1.0)이다.

    **빈 칸과 못 읽는 값을 가른다.** 둘 다 `to_numeric` 으로는 NaN 이 되는데, 빈 칸은
    1.0 으로 채우고 못 읽는 값은 막아야 한다. 한데 묶어 1.0 으로 채우면 `1,5`·`1.5배`
    같은 오타가 조용히 기준 모델로 내려앉아, 화면에는 아무 말도 없이 그 설비의 몫이
    3분의 1 줄어든다.

    빈 칸을 0 으로 읽지도 않는다. 모델이 하나뿐인 공정은 적을 것이 없어 대개 비어 있고,
    0 으로 읽으면 그 설비가 가용대수에서 통째로 사라진다.

    0 과 음수는 막는다(규칙 `ratio_not_positive`). 0 은 「이 설비는 없는 셈」이라는 뜻이 되는데
    그것은 비가동 일정이 맡는 일이고, 음수는 다른 설비의 몫을 깎아 합계를 거짓으로 만든다.
    """
    blank = _blank_numbers(raw)
    ratio = pd.to_numeric(raw, errors="coerce")
    unreadable = ~blank & ratio.isna()
    not_positive = ~blank & ratio.le(0)
    return ratio.mask(blank, DEFAULT_CONVERSION_RATIO).astype("float64"), unreadable, not_positive


def _read_number(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    """좌표·크기 칸을 숫자로 읽는다 — (값, 못 읽은 줄). **빈 칸과 못 읽는 값을 가른다**(환산비와
    같은 이유).

    좌표는 비어도 되는 칸이라(레이아웃표시 Y 의 미배치·크기만 있는 행), 못 읽는 값을 NaN 으로
    흘리면 붙여넣기의 `12,5`·`12m`·줄바꿈 없는 공백이 조용히 「미배치」로 저장된다.
    """
    blank = _blank_numbers(raw)
    number = pd.to_numeric(raw, errors="coerce")
    unreadable = ~blank & number.isna()
    return number.mask(blank).astype("float64"), unreadable


def _flag_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def _cell_value(value: object) -> CellValue:
    """한 칸짜리 다듬기 결과를 계약 꼴 값으로 — 결측(NA·NaN·NaT)은 모두 `pd.NA`."""
    if value is None or value is pd.NA or value is pd.NaT:
        return pd.NA
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, float | np.floating):
        number = float(value)
        return pd.NA if math.isnan(number) else number
    return str(value)


def _drop_blank_rows(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    present = pd.DataFrame(index=data.index)
    for column in columns:
        values = data[column]
        present[column] = values.notna() & values.astype("string").str.strip().ne("")
    return data.loc[present.any(axis=1)].copy()


def _normalize_required_text(data: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    for column in columns:
        data[column] = data[column].astype("string").str.strip()
        invalid = data[column].isna() | data[column].eq("")
        if invalid.any():
            raise ValueError(f"{_missing_text_message(label, column)}.")


def _optional_text(series: pd.Series) -> pd.Series:
    result = series.astype("string").str.strip()
    return result.mask(result.eq(""))


# 연도가 앞인 날짜 글자. 구분자는 한 값 안에서 같아야 하고(`\2`), 붙은 시각은 떼어 낸다.
# 떼어 낼 시각도 있을 수 있는 값(0~23시·0~59분·0~59초)만 받는다 — `24:00`·`23:75` 같은
# 시각이 날짜만 남아 통과하지 않고 지금처럼 막히게 한다.
_YEAR_FIRST_DATE = re.compile(
    r"\s*(\d{4})\s*([-./])\s*(\d{1,2})\s*\2\s*(\d{1,2})\.?"
    r"(?:(?:\s+|T)(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?)?\s*",
    re.ASCII,
)


def _year_first_text(value: object) -> str | None:
    """연도가 앞인 날짜 글자를 `YYYY-MM-DD` 로 고쳐 쓴다. 그 꼴이 아니면 None."""
    if not isinstance(value, str):
        return None
    match = _YEAR_FIRST_DATE.fullmatch(value)
    if match is None:
        return None
    return f"{match[1]}-{int(match[3]):02d}-{int(match[4]):02d}"


def _read_date(series: pd.Series) -> tuple[pd.Series, pd.Series, bool]:
    """날짜 칸을 읽는다 — (날짜, 못 읽은 줄, 한 날짜 dtype 으로 모이지 않았는가).

    pandas 는 글자 칸의 첫 값으로 날짜 꼴을 정해 칸 전체에 쓰므로, 꼴이 다른 값은 날짜여도
    NaT 가 된다. 그렇게 못 읽은 값 가운데 연도가 앞인 꼴(뜻이 하나다)만 따로 다시 읽는다.
    시간대가 붙은 칸은 다시 읽은 값과 섞을 수 없어 그대로 둔다. 칸이 날짜 dtype 으로 모이지 않으면
    (시간대가 서로 다른 값이 섞임 등) 셋째 값이 True 이고 첫째 값은 모두 NaT 다 — 부르는 쪽은 이
    예외를 던지지 않고 시간대 붙은 값을 빼고 다시 읽는다(`_read_master_dates`).
    """
    missing = series.isna() | series.astype("string").str.strip().eq("")
    not_dates = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    try:
        converted = pd.to_datetime(series.mask(missing), errors="coerce")
        retry = ~missing & converted.isna()
        if retry.any() and is_datetime64_dtype(converted):
            rewritten = series.loc[retry].map(_year_first_text)
            converted.loc[retry] = pd.to_datetime(rewritten, format="%Y-%m-%d", errors="coerce")
    except Exception:  # 날짜 dtype 으로 모이지 않은 칸 — 부르는 쪽이 다시 읽는다
        return not_dates, pd.Series(False, index=series.index, dtype=bool), True
    invalid = ~missing & converted.isna()
    try:
        normalized = converted.dt.normalize()
    except Exception:  # 날짜 dtype 으로 모이지 않은 칸 — 부르는 쪽이 다시 읽는다
        return not_dates, invalid, True
    return normalized, invalid, False


def _read_master_dates(entered: pd.Series) -> tuple[pd.Series, pd.Series]:
    """설비 마스터·비가동 일정 날짜 칸을 읽는다 — (시간대 없는 날짜, 못 읽은 줄). 저장·칸 결과·칸
    다듬기·비가동 일정 정규화(`_normalize_date`)가 함께 쓴다.

    계약 칸은 시간대 없는 날짜(DB 의 DATE)다. **시간대가 붙은 값(`…T00:00+09:00`)은 못 읽은
    값**으로 보고 나머지 값만 칸으로 다시 읽는다. 그대로 읽으면 칸이 어긋난다 — 시간대 붙은 값이 칸
    첫 값이면 pandas 가 칸 전체를 그 꼴로 읽어 멀쩡한 날짜가 못 읽은 값이 되고, 시간대가 서로 다르면
    칸이 날짜 dtype 으로 모이지 않아 영어 pandas 예외(화면이 잡지 못하는 `AttributeError` 까지)로
    멈추며, 한 칸이 모두 시간대 꼴이면 시간대 없는 칸과 견주다 멈추거나 그대로 통과한다. 시간대를
    떼고 받지 않는다(그 날짜가 하루 밀릴 수 있다). 저장본은 시간대가 없으니 다시 읽는 리비전은 이
    길에서 달라지지 않는다.
    """
    dates, invalid, scattered = _read_date(entered)
    if not scattered and not isinstance(dates.dtype, pd.DatetimeTZDtype):
        return dates, invalid
    zoned = pd.Series(
        [_zoned_date(value) for value in entered.tolist()], index=entered.index, dtype=bool
    )
    dates, invalid, scattered = _read_date(entered.mask(zoned))
    if not scattered and not isinstance(dates.dtype, pd.DatetimeTZDtype):
        return dates, invalid | zoned
    # 시간대 붙은 값을 빼고도 한 dtype 으로 모이지 않는 칸 — 어느 값 탓인지 칸으로는 알 수 없어 찬
    # 줄 모두를 못 읽은 값으로 본다.
    filled = entered.notna() & entered.astype("string").str.strip().ne("")
    return pd.Series(pd.NaT, index=entered.index, dtype="datetime64[ns]"), _flags(filled)


def _zoned_date(value: object) -> bool:
    """값 하나를 혼자 읽으면 시간대 꼴 날짜가 되거나 날짜로 모이지 않는가."""
    dates, _, scattered = _read_date(pd.Series([value], dtype="object"))
    return scattered or isinstance(dates.dtype, pd.DatetimeTZDtype)


def _normalize_date(series: pd.Series, label: str) -> pd.Series:
    """날짜 칸을 읽고 못 읽은 값이 있으면 그 값 예시와 함께 막는다(비가동 일정).

    설비 마스터와 같은 길(`_read_master_dates`)로 읽는다 — 시간대가 붙은 값은 못 읽은 값이고,
    시간대가 서로 다른 값이 섞여도 pandas 예외(화면이 잡지 못하는 `AttributeError`)로 새지 않고
    이 문구로 막힌다.
    """
    converted, invalid = _read_master_dates(series)
    if invalid.any():
        raise _listed(_date_message(label), series.loc[invalid].head(5).tolist())
    return converted


def _key_examples(data: pd.DataFrame, columns: tuple[str, ...]) -> list[str]:
    return (
        data.loc[:, columns]
        .astype("string")
        .agg(" / ".join, axis=1)
        .drop_duplicates()
        .head(5)
        .tolist()
    )
