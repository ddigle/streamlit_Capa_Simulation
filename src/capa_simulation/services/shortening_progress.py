# Purpose: 필요단축일정 기준선과 지금 계획의 호기 결과를 짝지어 필요·확보 시점·단축일수 변동을 낸다.

"""필요단축일정 진척 비교(2026-10-08 사용자 요청, 시안 B 「호기마다 과거·현재 두 줄」).

「과거 시점의 필요시점/확보시점 대비 지금 생산성 향상·납기 단축으로 그 시점과 단축 일수가 얼마나
움직였는가」를 낸다. 원인(UPEH·효율·납기·계획)은 보지 않는다 — **날짜가 움직인 것만** 견준다.
Streamlit·DB 를 모르는 순수 함수다. 입력은 같은 목표 하나의 호기 표 두 벌이다.

- 과거: 기준선의 그 목표 호기 표(`ShorteningBaseline.units_at`).
- 현재: 지금 계획의 그 목표 호기 표(`LevelPlan.units`).

두 표는 같은 칸(`공정`·`호기`·`구분`·`기존 Qual`·`목표 Qual`·`단축일수`·`모듈 수`)을 갖는다. **필요
시점**은 목표 Qual(그때까지 Qual 을 마쳐야 한다), **확보 시점**은 기존 Qual(지금 일정대로면 그날
Qual 이 끝난다)이고, 단축일수 = 확보 − 필요다.

## 짝짓기

공정 안에서만 짝짓는다(공정 이름은 원본이다 — 표시명은 화면 라벨일 뿐).

- 당긴 호기(`단축`)는 **같은 호기**끼리 — 호기는 설비명, 모듈 묶음은 설비키(Main 설비)다.
- 가상 호기 「추가N」(`신규`)은 **공정 안 차례**(추가1, 추가2 …)끼리다. 이름이 그 차례다.

## 상태

| 짝 | 상태 |
| --- | --- |
| 둘 다 있는 당긴 호기 | 단축일수가 줄면 `개선`, 늘면 `악화`, 같으면 `변동 없음` |
| 둘 다 있는 가상 호기 | `신규 유지` — 단축일수가 없어 필요 시점 이동만 적는다 |
| 지금에만 | `신규 필요` — 그때는 단축(또는 신규 투자)이 필요 없던 호기 |
| 과거에만 | `해소` — 지금 계획에서는 단축 대상이 아니다(가상 호기면 신규 투자가 필요 없다) |
| 기준선 공정이 지금 맞댄 공정에 없음 | `지금 범위 밖` — 짝짓지 않는다(해소가 아니다) |
| 과거 필요 시점이 지금의 오늘보다 앞 | `필요 시점 지남` — 견주지 않는다(아래) |

**필요 시점 지남.** 지금 계획은 오늘보다 앞으로 당길 수 없다(`required_shortening` 의 바닥이
`max(구간 시작, 오늘)`). 그래서 기준선을 저장한 뒤 오늘이 지나 과거 필요 시점이 오늘보다 앞이 된
호기는, 아무 진척이 없어도 필요 시점이 오늘로 밀려 단축일수가 줄거나(개선처럼) 후보에서 빠진다
(해소처럼). 그런 호기는 두 줄을 그대로 보이되 상태를 `필요 시점 지남` 으로 두고 증감·합계·대수에서
뺀다 — 성과로 세지 않는다. 오늘 바로 그날은 지금 계획도 닿으므로 견준다(엄격한 `<`). 필요 시점이
지난 추가N 은 홀로 서고 남은 추가N 끼리 차례로 짝짓는다(지금 계획에는 오늘보다 앞의 신규 필요가
없다).

`단축일수 증감` 은 현재 − 과거(음수가 줄임)이고, 한쪽에만 있는 당긴 호기는 없는 쪽을 0일로 센다 —
그래서 공정·전체의 증감이 그대로 합계의 차이다(`필요 시점 지남` 은 양쪽 합계에서 함께 뺀다). 가상
호기는 단축일수가 없어 비운다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import zip_longest

import pandas as pd

from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    LEVEL_COLUMN,
    level_percent,
    unit_number,
)

__all__ = [
    "PROGRESS_COLUMNS",
    "PROGRESS_EXPORT_COLUMNS",
    "PROGRESS_IMPROVED",
    "PROGRESS_KEPT_NEW",
    "PROGRESS_LAPSED",
    "PROGRESS_NEW",
    "PROGRESS_OUT_OF_SCOPE",
    "PROGRESS_RESOLVED",
    "PROGRESS_UNCHANGED",
    "PROGRESS_WORSENED",
    "ProgressSummary",
    "ScopeDifference",
    "compare_progress",
    "progress_export_frame",
    "scope_difference",
    "summarize_progress",
]

PROGRESS_IMPROVED = "개선"
PROGRESS_WORSENED = "악화"
PROGRESS_UNCHANGED = "변동 없음"
PROGRESS_NEW = "신규 필요"
PROGRESS_RESOLVED = "해소"
PROGRESS_KEPT_NEW = "신규 유지"
PROGRESS_OUT_OF_SCOPE = "지금 범위 밖"
PROGRESS_LAPSED = "필요 시점 지남"

PROGRESS_COLUMNS = (
    "공정",
    "호기",
    "구분",
    "상태",
    "과거 필요 시점",
    "과거 확보 시점",
    "과거 단축일수",
    "현재 필요 시점",
    "현재 확보 시점",
    "현재 단축일수",
    "단축일수 증감",
    "필요 시점 이동(일)",
    "확보 시점 이동(일)",
    "모듈 수",
)
"""짝지은 행. 시점은 `date`(없으면 None), 일수는 `Int64` 다. 이동은 현재 − 과거(양수가 늦춰짐)."""

PROGRESS_EXPORT_COLUMNS = (LEVEL_COLUMN, *PROGRESS_COLUMNS)
"""「진척 비교 CSV」 의 칸. 시점은 `YYYY-MM-DD` 글자다."""

_DATE_COLUMNS = ("과거 필요 시점", "과거 확보 시점", "현재 필요 시점", "현재 확보 시점")
_INTEGER_COLUMNS = (
    "과거 단축일수",
    "현재 단축일수",
    "단축일수 증감",
    "필요 시점 이동(일)",
    "확보 시점 이동(일)",
    "모듈 수",
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class ProgressSummary:
    """고른 공정들의 요약. 일수는 당긴 호기의 단축일수 합이다(가상 호기는 0일).

    `필요 시점 지남` 행은 일수·추가N 대수에서 양쪽 모두 뺀다 — `lapsed` 가 그 대수,
    `lapsed_current_days` 가 그 행들의 지금 단축일수 합(비교 안 함 화면의 합계와 맞춰 볼 수
    있게)이다.
    """

    past_days: int = 0
    current_days: int = 0
    improved: int = 0
    worsened: int = 0
    unchanged: int = 0
    new: int = 0
    resolved: int = 0
    kept_new: int = 0
    out_of_scope: int = 0
    past_virtual: int = 0
    current_virtual: int = 0
    lapsed: int = 0
    lapsed_current_days: int = 0

    @property
    def change(self) -> int:
        """현재 − 과거. 음수가 줄인 것이다."""
        return self.current_days - self.past_days


@dataclass(frozen=True)
class ScopeDifference:
    """기준선과 지금의 조회 달·맞댄 공정이 어떻게 다른가."""

    baseline_months: tuple[int, int]
    current_months: tuple[int, int]
    added: tuple[str, ...] = ()
    """지금만 맞댄 공정."""

    removed: tuple[str, ...] = ()
    """기준선에만 있던 공정(지금 범위 밖)."""

    @property
    def months_differ(self) -> bool:
        return self.baseline_months != self.current_months

    @property
    def differs(self) -> bool:
        return self.months_differ or bool(self.added) or bool(self.removed)


def compare_progress(
    past: pd.DataFrame,
    current: pd.DataFrame,
    *,
    current_processes: Iterable[str],
    today: date,
) -> pd.DataFrame:
    """같은 목표의 과거·현재 호기 표를 짝지은 행(`PROGRESS_COLUMNS`).

    `current_processes` 는 지금 계획이 맞댄 공정(`ShorteningPlan.processes`)이다 — 그 밖의 기준선
    공정은 `지금 범위 밖` 이다. `today` 는 지금 계획의 오늘(`ShorteningPlan.today`)이다 — 과거 필요
    시점이 그보다 앞인 행은 `필요 시점 지남` 이다. 공정은 지금 맞댄 공정 차례, 그 뒤에 범위 밖
    공정(기준선 차례)이다.
    공정 안은 당긴 호기를 확보 시점(지금, 없으면 과거) → 호기 번호 차례로, 그 뒤에 가상 호기다.
    """
    scope = [str(process) for process in current_processes]
    in_scope = set(scope)
    past_by = _by_process(past)
    current_by = _by_process(current)
    order = [process for process in scope if process in past_by or process in current_by]
    order += [process for process in past_by if process not in in_scope]
    rows: list[dict[str, object]] = []
    for process in order:
        rows.extend(
            _process_rows(
                process,
                past_by.get(process, []),
                current_by.get(process, []),
                inside=process in in_scope,
                today=today,
            )
        )
    return _frame(rows)


def summarize_progress(
    rows: pd.DataFrame, processes: Iterable[str] | None = None
) -> ProgressSummary:
    """짝지은 행의 요약. `processes` 를 주면 그 공정만 센다(화면 범위)."""
    if processes is not None:
        rows = rows.loc[rows["공정"].isin(list(processes))]
    status = rows["상태"]
    lapsed = status.eq(PROGRESS_LAPSED)
    shortened = rows["구분"].eq(KIND_SHORTENED) & ~lapsed
    virtual = rows["구분"].eq(KIND_NEW) & ~lapsed
    return ProgressSummary(
        past_days=_total(rows.loc[shortened, "과거 단축일수"]),
        current_days=_total(rows.loc[shortened, "현재 단축일수"]),
        improved=int(status.eq(PROGRESS_IMPROVED).sum()),
        worsened=int(status.eq(PROGRESS_WORSENED).sum()),
        unchanged=int(status.eq(PROGRESS_UNCHANGED).sum()),
        new=int(status.eq(PROGRESS_NEW).sum()),
        resolved=int(status.eq(PROGRESS_RESOLVED).sum()),
        kept_new=int(status.eq(PROGRESS_KEPT_NEW).sum()),
        out_of_scope=int(status.eq(PROGRESS_OUT_OF_SCOPE).sum()),
        past_virtual=int((virtual & rows["과거 필요 시점"].notna()).sum()),
        current_virtual=int((virtual & rows["현재 필요 시점"].notna()).sum()),
        lapsed=int(lapsed.sum()),
        lapsed_current_days=_total(rows.loc[lapsed, "현재 단축일수"]),
    )


def scope_difference(
    *,
    baseline_months: tuple[int, int],
    baseline_processes: Iterable[str],
    months: Sequence[int],
    processes: Iterable[str],
) -> ScopeDifference:
    """기준선의 (시작 월, 끝 월)·맞댄 공정과 지금의 달·맞댄 공정을 견준다."""
    before = [str(process) for process in baseline_processes]
    now = [str(process) for process in processes]
    current = (int(months[0]), int(months[-1])) if months else baseline_months
    return ScopeDifference(
        baseline_months=(int(baseline_months[0]), int(baseline_months[1])),
        current_months=current,
        added=tuple(process for process in now if process not in set(before)),
        removed=tuple(process for process in before if process not in set(now)),
    )


def progress_export_frame(
    rows: pd.DataFrame, *, level: float, processes: Sequence[str]
) -> pd.DataFrame:
    """「진척 비교 CSV」 의 표(`PROGRESS_EXPORT_COLUMNS`). 공정은 `processes` 차례(화면 차례)다."""
    names = [str(process) for process in processes]
    order = {name: index for index, name in enumerate(names)}
    chosen = rows.loc[rows["공정"].isin(names)].copy()
    chosen["_order"] = chosen["공정"].map(order)
    chosen = chosen.sort_values("_order", kind="stable").drop(columns="_order")
    for column in _DATE_COLUMNS:
        chosen[column] = [None if day is None else day.isoformat() for day in chosen[column]]
    chosen.insert(0, LEVEL_COLUMN, level_percent(level))
    return chosen.loc[:, list(PROGRESS_EXPORT_COLUMNS)].reset_index(drop=True)


# ---------------------------------------------------------------------- 짝짓기


def _by_process(frame: pd.DataFrame) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    if frame.empty:
        return grouped
    for record in frame.to_dict("records"):
        row = {str(key): value for key, value in record.items()}
        grouped.setdefault(str(row["공정"]), []).append(row)
    return grouped


def _process_rows(
    process: str,
    past: list[dict[str, object]],
    current: list[dict[str, object]],
    *,
    inside: bool,
    today: date,
) -> list[dict[str, object]]:
    if not inside:
        return [
            _row(process, row, None, today=today, out_of_scope=True)
            for row in sorted(past, key=_secure_order)
        ]
    past_units = {str(row["호기"]): row for row in past if row["구분"] == KIND_SHORTENED}
    current_units = {str(row["호기"]): row for row in current if row["구분"] == KIND_SHORTENED}
    names = sorted(
        {*past_units, *current_units},
        key=lambda name: _secure_order(current_units.get(name) or past_units[name]),
    )
    rows = [
        _row(process, past_units.get(name), current_units.get(name), today=today) for name in names
    ]
    past_virtual = sorted((row for row in past if row["구분"] == KIND_NEW), key=_virtual_order)
    current_virtual = sorted(
        (row for row in current if row["구분"] == KIND_NEW), key=_virtual_order
    )
    # 필요 시점이 지난 과거 추가N 은 지금 계획에 짝이 있을 수 없다(오늘보다 앞의 신규 필요는 서지
    # 않는다) — 홀로 세우고 남은 것끼리 차례로 짝짓는다. 당긴 호기는 같은 실물이라 짝을 지킨다.
    lapsed_virtual = [row for row in past_virtual if (_need(row) or date.max) < today]
    past_virtual = [row for row in past_virtual if (_need(row) or date.max) >= today]
    rows += [_row(process, row, None, today=today) for row in lapsed_virtual]
    rows += [
        _row(process, before, now, today=today)
        for before, now in zip_longest(past_virtual, current_virtual)
    ]
    return rows


def _secure_order(row: Record) -> tuple[date, int, int, str]:
    name = str(row["호기"])
    number = unit_number(name)
    secure = _day(row["기존 Qual"]) or _day(row["목표 Qual"]) or date.max
    return (secure, 0 if number is not None else 1, number or 0, name)


def _virtual_order(row: Record) -> tuple[int, str]:
    name = str(row["호기"])
    number = unit_number(name)
    return (number if number is not None else 0, name)


def _row(
    process: str,
    past: Record | None,
    current: Record | None,
    *,
    today: date,
    out_of_scope: bool = False,
) -> dict[str, object]:
    either = current if current is not None else past
    assert either is not None
    kind = str(either["구분"])
    shortened = kind == KIND_SHORTENED
    past_need, current_need = _need(past), _need(current)
    past_secure, current_secure = _secure(past), _secure(current)
    past_days, current_days = _days(past), _days(current)
    lapsed = not out_of_scope and past_need is not None and past_need < today
    if out_of_scope:
        status = PROGRESS_OUT_OF_SCOPE
    elif lapsed:
        status = PROGRESS_LAPSED
    elif past is None:
        status = PROGRESS_NEW
    elif current is None:
        status = PROGRESS_RESOLVED
    elif not shortened:
        status = PROGRESS_KEPT_NEW
    else:
        change = (current_days or 0) - (past_days or 0)
        status = (
            PROGRESS_IMPROVED
            if change < 0
            else PROGRESS_WORSENED
            if change > 0
            else PROGRESS_UNCHANGED
        )
    compared = shortened and not out_of_scope and not lapsed
    delta = (current_days or 0) - (past_days or 0) if compared else None
    return {
        "공정": process,
        "호기": str(either["호기"]),
        "구분": kind,
        "상태": status,
        "과거 필요 시점": past_need,
        "과거 확보 시점": past_secure,
        "과거 단축일수": past_days,
        "현재 필요 시점": current_need,
        "현재 확보 시점": current_secure,
        "현재 단축일수": current_days,
        "단축일수 증감": delta,
        "필요 시점 이동(일)": _shift(past_need, current_need),
        "확보 시점 이동(일)": _shift(past_secure, current_secure),
        "모듈 수": _whole(either["모듈 수"]) or 1,
    }


def _need(row: Record | None) -> date | None:
    return None if row is None else _day(row["목표 Qual"])


def _secure(row: Record | None) -> date | None:
    if row is None or row["구분"] != KIND_SHORTENED:
        return None
    return _day(row["기존 Qual"])


def _days(row: Record | None) -> int | None:
    if row is None or row["구분"] != KIND_SHORTENED:
        return None
    return _whole(row["단축일수"])


def _shift(before: date | None, after: date | None) -> int | None:
    return None if before is None or after is None else (after - before).days


# ---------------------------------------------------------------------- 표


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        frame = pd.DataFrame({column: pd.Series(dtype="object") for column in PROGRESS_COLUMNS})
    else:
        frame = pd.DataFrame(rows, columns=list(PROGRESS_COLUMNS))
    for column in _INTEGER_COLUMNS:
        frame[column] = pd.to_numeric(frame[column]).astype("Int64")
    return frame


def _total(values: pd.Series) -> int:
    return int(pd.to_numeric(values).fillna(0).sum())


def _blank(value: object) -> bool:
    return (
        value is None
        or value is pd.NA
        or value is pd.NaT
        or (isinstance(value, float) and math.isnan(value))
    )


def _day(value: object) -> date | None:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    stamp = pd.Timestamp(str(value))
    return None if pd.isna(stamp) else stamp.date()


def _whole(value: object) -> int | None:
    return None if _blank(value) else round(float(str(value)))
