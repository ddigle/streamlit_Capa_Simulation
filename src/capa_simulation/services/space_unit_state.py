# Purpose: Space 도면 호기의 경계 날짜(실물·이탈·정지·지연·비가동·미확인)와 기준일 판정을 낸다.

"""Space 층 도면의 호기 판정(2026-10-16 사용자 결정 — 질문 3·4·6 권장안).

도면은 기준일(T)마다 호기 상자의 테·채우기·덧표시를 바꾼다. 판정은 **날짜 몇 개를 견주는
것뿐**이라 호기마다 경계 날짜를 한 번 구해 두고 T 와 견준다.
브라우저(`space_layout_editor_assets/editor.js`)는 같은 경계 날짜를 `YYYY-MM-DD` 글자로 받아
**글자 비교**로 같은 판정을 한다 — 기준일 페이더가 끄는 동안 서버를 부르지 않고 칠하기 위해서다.
규칙은 이 모듈 하나이고(`boundary_payload` 가 브라우저로 보내는 꼴, `unit_states_at` 이 파이썬의
같은 판정), 시험이 두 판정을 T 를 훑으며 대조한다.

**경계 날짜**(`unit_boundaries`)

- **실물시작일** — 반입실적이 있으면 반입실적. 없고 반입상태가 「지연」이면 **없음**(실적이 들어올
  때까지 반입 전). 그 밖에 반입일정이 있으면 반입일정. 날짜가 둘 다 없으면 기존설비·보관 Y 는
  **처음부터**, 신규는 없음. 실적은 **Space 실물 판정에만** 쓴다 — 가용대수 집계는 일정 기준
  그대로다 (「Space 는 실물, 집계는 계획」).
- **도면이탈일** — 반출/이설일정, 없으면 정지일정(`equipment_availability` 의 `도면이탈여부` 와
  같은 규칙). **정지일**은 두 날짜가 다 있을 때만 뜻이 있다(정지한 뒤 반출/이설 전까지 빗금).
- **지연 구간** — 반입·Qual 단계마다 상태가 「지연」이면 [min(일정, 오늘), 실적). 실적이 없으면
  끝이 없다(일정이 없으면 오늘부터). 두 단계의 합집합이다.
- **비가동 구간** — 비가동 일정 [시작일, 종료일](종료일이 없으면 끝이 없다). 가용설비의 운영
  비가동과 같은 날 경계다(`_active_downtime`).
- **미확인** — 오늘 기준으로 고정한다(`schedule_confirmation` 의 미확인 — T 를 따르지 않는다).
- **보관** — 보관유무 Y.

**T 의 판정**(`unit_states_at`): 보임 = 도면이탈일 없음 또는 T < 도면이탈일, 실물 = 처음부터이거나
실물시작일 ≤ T, 반출/이설 예정 = T < 도면이탈일, 정지 중 = 정지일 ≤ T < 도면이탈일, 지연 = T 가
지연 구간 안, 운영 비가동 = T 가 비가동 구간 안(양 끝 포함).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ACTUAL_STAGES,
    ARRIVAL_ACTUAL_COLUMN,
    ARRIVAL_DATE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    DELAYED_STAGE_STATUS,
    EQUIPMENT_ID_COLUMN,
    RELOCATION_DATE_COLUMN,
    STOP_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
)
from capa_simulation.services.schedule_confirmation import (
    flagged_equipment,
    schedule_confirmation_issues,
)

# 「처음부터 실물」을 글자로 보낼 때의 값. 어느 `YYYY-MM-DD` 글자보다 앞서 글자 비교로 늘 ≤ T 다.
REAL_FROM_START: Final = "0000-01-01"
EXISTING_FLAG_COLUMN: Final = "기존설비여부"

# 경계 날짜 칸(`unit_boundaries` 결과).
REAL_FROM_COLUMN: Final = "실물시작일"
REAL_ALWAYS_COLUMN: Final = "처음부터실물"
LAYOUT_EXIT_COLUMN: Final = "도면이탈일"
STOP_ON_COLUMN: Final = "정지일"
DELAY_SPANS_COLUMN: Final = "지연구간"
OFFLINE_SPANS_COLUMN: Final = "비가동구간"
STORAGE_COLUMN: Final = "보관"
FLAG_COLUMN: Final = "미확인"

# T 의 판정 칸(`unit_states_at` 결과, 모두 bool).
VISIBLE_STATE: Final = "보임"
REAL_STATE: Final = "실물"
EXIT_PLANNED_STATE: Final = "반출이설예정"
STOPPED_STATE: Final = "정지중"
DELAYED_STATE: Final = "지연"
OFFLINE_STATE: Final = "운영비가동"
STORAGE_STATE: Final = "보관"
FLAG_STATE: Final = "미확인"
STATE_COLUMNS: Final = (
    VISIBLE_STATE,
    REAL_STATE,
    EXIT_PLANNED_STATE,
    STOPPED_STATE,
    DELAYED_STATE,
    OFFLINE_STATE,
    STORAGE_STATE,
    FLAG_STATE,
)

Span = tuple[pd.Timestamp, pd.Timestamp | None]


def _dates(frame: pd.DataFrame, column: str) -> pd.Series:
    """날짜 칸을 자정 Timestamp 로. 없는 칸·못 읽는 값은 NaT 다(검증 전 편집본·옛 표도 받는다)."""
    if column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    raw = frame[column]
    blank = raw.isna() | raw.astype("string").str.strip().eq("")
    parsed = pd.to_datetime(raw.mask(blank), errors="coerce")
    return pd.Series(parsed, index=frame.index).astype("datetime64[ns]").dt.normalize()


def _equals(frame: pd.DataFrame, column: str, value: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype=bool)
    text = frame[column].astype("string").str.strip()
    return text.eq(value).fillna(False).astype(bool)


def _names(frame: pd.DataFrame) -> pd.Series:
    return frame[EQUIPMENT_ID_COLUMN].astype("string").str.strip()


def _offline_spans(downtime: pd.DataFrame) -> dict[str, tuple[Span, ...]]:
    """설비명마다 비가동 구간(시작 차례). 시작일을 못 읽는 행은 버린다."""
    if downtime.empty or EQUIPMENT_ID_COLUMN not in downtime.columns:
        return {}
    starts = _dates(downtime, "시작일")
    ends = _dates(downtime, "종료일")
    names = _names(downtime)
    spans: dict[str, list[Span]] = {}
    for name, start, end in zip(names, starts, ends, strict=True):
        if pd.isna(name) or pd.isna(start):
            continue
        spans.setdefault(str(name), []).append((start, None if pd.isna(end) else end))
    return {name: tuple(sorted(found, key=lambda span: span[0])) for name, found in spans.items()}


def unit_boundaries(status: pd.DataFrame, downtime: pd.DataFrame, *, today: date) -> pd.DataFrame:
    """호기마다 경계 날짜. 결과는 `status` 와 같은 인덱스이고 칸은 모듈 머리말의 경계 날짜다.

    `status` 는 Space 상태(`build_space_equipment_status`) 같은 설비 마스터 행이다 — 검증 전
    편집본도 받는다(없는 칸은 빈 칸). 날짜 칸은 Timestamp(없으면 NaT), 지연·비가동 구간은 `(시작,
    끝 | None)` 튜플의 튜플이다.
    """
    today_stamp = pd.Timestamp(today)
    arrival_actual = _dates(status, ARRIVAL_ACTUAL_COLUMN)
    arrival_plan = _dates(status, ARRIVAL_DATE_COLUMN)
    arrival_delayed = _equals(status, ARRIVAL_STATUS_COLUMN, DELAYED_STAGE_STATUS)
    storage = _equals(status, STORAGE_FLAG_COLUMN, "Y")
    existing = _equals(status, EXISTING_FLAG_COLUMN, "Y")
    planned_from = arrival_plan.mask(arrival_delayed)
    real_from = arrival_actual.fillna(planned_from)
    always = arrival_actual.isna() & ~arrival_delayed & arrival_plan.isna() & (existing | storage)

    stop = _dates(status, STOP_DATE_COLUMN)
    relocation = _dates(status, RELOCATION_DATE_COLUMN)
    layout_exit = relocation.fillna(stop)
    stop_on = stop.where(relocation.notna())

    stage_spans: list[list[Span]] = [[] for _ in range(len(status))]
    for stage in ACTUAL_STAGES:
        delayed = _equals(status, stage.status, DELAYED_STAGE_STATUS).to_numpy()
        planned = _dates(status, stage.schedule).fillna(today_stamp)
        starts = planned.where(planned.le(today_stamp), today_stamp)
        ends = _dates(status, stage.actual)
        for position, (flag, start, end) in enumerate(zip(delayed, starts, ends, strict=True)):
            if flag:
                stage_spans[position].append((start, None if pd.isna(end) else end))

    names = (
        _names(status)
        if EQUIPMENT_ID_COLUMN in status.columns
        else pd.Series(pd.NA, index=status.index, dtype="string")
    )
    offline_by_name = _offline_spans(downtime)
    flagged = flagged_equipment(schedule_confirmation_issues(status, today=today))
    return pd.DataFrame(
        {
            REAL_FROM_COLUMN: real_from.astype("datetime64[ns]"),
            REAL_ALWAYS_COLUMN: always.astype(bool),
            LAYOUT_EXIT_COLUMN: layout_exit.astype("datetime64[ns]"),
            STOP_ON_COLUMN: stop_on.astype("datetime64[ns]"),
            DELAY_SPANS_COLUMN: pd.Series(
                [tuple(spans) for spans in stage_spans], index=status.index, dtype=object
            ),
            OFFLINE_SPANS_COLUMN: pd.Series(
                [offline_by_name.get(str(name), ()) for name in names],
                index=status.index,
                dtype=object,
            ),
            STORAGE_COLUMN: storage,
            FLAG_COLUMN: names.isin(flagged).fillna(False).astype(bool),
        },
        index=status.index,
    )


def _inside(spans: pd.Series, moment: pd.Timestamp, *, closed_end: bool) -> pd.Series:
    """구간 목록 칸에서 `moment` 를 품은 구간이 있는 행. `closed_end` 면 끝날도 안이다."""

    def hit(found: tuple[Span, ...]) -> bool:
        for start, end in found:
            if start > moment:
                continue
            if end is None or (moment <= end if closed_end else moment < end):
                return True
        return False

    return pd.Series([hit(found) for found in spans], index=spans.index, dtype=bool)


def unit_states_at(boundaries: pd.DataFrame, *, as_of: date) -> pd.DataFrame:
    """경계 날짜(`unit_boundaries`)로 T(`as_of`)의 판정. 칸은 `STATE_COLUMNS`(모두 bool)다."""
    moment = pd.Timestamp(as_of)
    real_from = boundaries[REAL_FROM_COLUMN]
    layout_exit = boundaries[LAYOUT_EXIT_COLUMN]
    stop_on = boundaries[STOP_ON_COLUMN]
    before_exit = layout_exit.notna() & layout_exit.gt(moment)
    return pd.DataFrame(
        {
            VISIBLE_STATE: layout_exit.isna() | before_exit,
            REAL_STATE: boundaries[REAL_ALWAYS_COLUMN] | (real_from.notna() & real_from.le(moment)),
            EXIT_PLANNED_STATE: before_exit,
            STOPPED_STATE: stop_on.notna() & stop_on.le(moment) & before_exit,
            DELAYED_STATE: _inside(boundaries[DELAY_SPANS_COLUMN], moment, closed_end=False),
            OFFLINE_STATE: _inside(boundaries[OFFLINE_SPANS_COLUMN], moment, closed_end=True),
            STORAGE_STATE: boundaries[STORAGE_COLUMN],
            FLAG_STATE: boundaries[FLAG_COLUMN],
        },
        index=boundaries.index,
    ).astype(bool)


def _day(value: pd.Timestamp | None) -> str | None:
    return None if value is None or pd.isna(value) else value.strftime("%Y-%m-%d")


def _span_payload(spans: tuple[Span, ...]) -> list[list[str | None]]:
    return [[_day(start), _day(end)] for start, end in spans]


def boundary_payload(boundaries: pd.DataFrame) -> list[dict[str, Any]]:
    """브라우저로 보낼 호기마다의 경계 날짜(행 차례). 날짜는 `YYYY-MM-DD` 글자다.

    `realFrom` 은 없으면 None, 처음부터면 `REAL_FROM_START`. `exitOn`·`stopOn` 은 없으면 None.
    `delays`· `offline` 은 ``[[시작, 끝 | None], …]`` 이다. `flag`(미확인)·`storage`(보관)는
    참·거짓이다.
    """
    payload: list[dict[str, Any]] = []
    for row in boundaries.itertuples(index=False):
        values: Mapping[str, Any] = dict(zip(boundaries.columns, row, strict=True))
        payload.append(
            {
                "realFrom": REAL_FROM_START
                if values[REAL_ALWAYS_COLUMN]
                else _day(values[REAL_FROM_COLUMN]),
                "exitOn": _day(values[LAYOUT_EXIT_COLUMN]),
                "stopOn": _day(values[STOP_ON_COLUMN]),
                "delays": _span_payload(values[DELAY_SPANS_COLUMN]),
                "offline": _span_payload(values[OFFLINE_SPANS_COLUMN]),
                "flag": bool(values[FLAG_COLUMN]),
                "storage": bool(values[STORAGE_COLUMN]),
            }
        )
    return payload
