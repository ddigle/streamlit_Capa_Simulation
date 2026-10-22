# Purpose: 필요 단축 일정의 진척 보드·카드 차례·기한 임박·이행 지연 표를 계획과 마스터로 낸다.

"""필요 단축 일정 진척 관리(2026-10-22 사용자 요청 「단축이 필요한 공정 전부의 진척 관리 한
페이지」).

Streamlit·DB 를 모르는 순수 함수다. 입력은 이미 캐시된 계획(`LevelPlan`)·진척 비교 행
(`shortening_progress.compare_progress`)·설비 마스터이고, **DB 에 아무것도 쓰지 않는다** — 조치
상태·메모 같은 공용 기록은 두지 않는다(후속).

- **공정 진척 보드**(`process_board`) — 공정마다 한 줄: 첫 부족 달, 월 최대 부족, 당길 호기 수,
  단축일 합계·최대, 신규, 가장 이른 목표 Qual 과 오늘부터 남은 날. 진척 비교 행을 주면 기준선 대비
  (`progress_trend` — 개선·악화·해소·변동 없음과 단축일 증감)와 이행 지연 대수가 붙는다.
- **카드 차례**(`board_order`) — 표시순서 / 목표 Qual 이른 순 / 최대 부족 큰 순 / 기준선 대비 악화
  먼저. 같으면 표시순서다.
- **기한 임박**(`imminent_units`) — 지금 계획의 목표 Qual(가상 호기는 필요 Qual)이 오늘부터 N일 안인
  호기.
- **이행 지연**(`delayed_units`) — 기준선의 목표 Qual(과거 필요 시점)이 지났는데 설비 마스터의
  Qual실적이 비었거나 Qual상태가 「완료」가 아닌 당긴 호기. 마스터에 없는 호기도 실적이 없으므로
  지연이다(`Qual상태` 칸에 「마스터에 없음」).

호기 마스터 한 줄(`unit_qual_status`)은 설비키(Main 설비, 없으면 설비명)로 모듈 행을 묶는다 — 계획의
`호기` 가 같은 키다. 모듈 행 가운데 하나라도 실적이 없거나 완료가 아니면 그 호기는 완료가 아니다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from capa_simulation.services.equipment_contract import (
    DONE_STAGE_STATUS,
    QUAL_ACTUAL_COLUMN,
    QUAL_DATE_COLUMN,
    QUAL_STATUS_COLUMN,
)
from capa_simulation.services.equipment_units import unit_keys
from capa_simulation.services.equipment_validation import prepare_equipment_master
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    LevelPlan,
)
from capa_simulation.services.shortening_progress import summarize_progress

__all__ = [
    "BOARD_COLUMNS",
    "BOARD_ORDERS",
    "DELAYED_COLUMNS",
    "IMMINENT_COLUMNS",
    "MANAGER_COLUMN",
    "MASTER_MISSING",
    "ORDER_DISPLAY",
    "ORDER_EARLIEST_QUAL",
    "ORDER_LARGEST_GAP",
    "ORDER_WORSENED_FIRST",
    "TREND_IMPROVED",
    "TREND_RESOLVED",
    "TREND_UNCHANGED",
    "TREND_WORSENED",
    "UNIT_STATUS_COLUMNS",
    "ProgressTrend",
    "board_order",
    "delayed_units",
    "first_shortage_month",
    "imminent_units",
    "process_board",
    "process_counts",
    "progress_trend",
    "unit_managers",
    "unit_qual_status",
]

MANAGER_COLUMN = "담당자"

ORDER_DISPLAY = "표시순서"
ORDER_EARLIEST_QUAL = "목표 Qual 이른 순"
ORDER_LARGEST_GAP = "최대 부족 큰 순"
ORDER_WORSENED_FIRST = "기준선 대비 악화 먼저"
BOARD_ORDERS = (ORDER_DISPLAY, ORDER_EARLIEST_QUAL, ORDER_LARGEST_GAP, ORDER_WORSENED_FIRST)
"""카드 차례 선택지. 늘 넷이다 — 진척 비교가 없을 때의 「악화 먼저」 는 표시순서로 읽는다."""

TREND_IMPROVED = "개선"
TREND_WORSENED = "악화"
TREND_RESOLVED = "해소"
TREND_UNCHANGED = "변동 없음"

MASTER_MISSING = "마스터에 없음"

BOARD_COLUMNS = (
    "공정",
    "첫 부족 달",
    "월 최대 부족",
    "당길 호기",
    "단축일 합계",
    "최대 단축",
    "신규",
    "가장 이른 목표 Qual",
    "남은 일수",
    "기준선 대비",
    "단축일 증감",
    "이행 지연",
)
"""보드 한 줄. 달은 `YYYYMM` 정수(없으면 None), 날짜는 `date`(없으면 None). 기준선 대비 셋은 진척
비교 행을 줄 때만 값이 있다."""

UNIT_STATUS_COLUMNS = (
    "호기",
    "공정",
    QUAL_DATE_COLUMN,
    QUAL_ACTUAL_COLUMN,
    QUAL_STATUS_COLUMN,
    MANAGER_COLUMN,
    "완료",
)
"""설비키마다 한 줄. `Qual일정` 은 가장 늦은 모듈, `Qual실적` 은 모든 모듈에 있을 때 가장 늦은
날(하나라도 비면 None), 글자는 서로 다른 값을 모듈 차례로 「, 」로 잇는다. `완료` 는 모든 모듈이
실적·완료다."""

IMMINENT_COLUMNS = ("공정", "호기", "구분", "목표 Qual", "남은 일수", "단축일수", MANAGER_COLUMN)
DELAYED_COLUMNS = (
    "공정",
    "호기",
    "기준선 목표 Qual",
    "지난 일수",
    QUAL_DATE_COLUMN,
    QUAL_ACTUAL_COLUMN,
    QUAL_STATUS_COLUMN,
    MANAGER_COLUMN,
)


@dataclass(frozen=True)
class ProgressTrend:
    """공정 하나의 기준선 대비. `change` 는 현재 − 과거 단축일 합(음수가 줄임)이다."""

    label: str
    change: int
    past_virtual: int
    current_virtual: int

    def text(self) -> str:
        """「개선 −12일」·「악화 +5일 · 신규 1→2」·「해소」·「변동 없음」."""
        parts = [self.label]
        if self.label in (TREND_IMPROVED, TREND_WORSENED) and self.change:
            parts[0] += f" {_signed(self.change)}일"
        if self.past_virtual != self.current_virtual and self.label != TREND_RESOLVED:
            parts.append(f"신규 {self.past_virtual}→{self.current_virtual}")
        return " · ".join(parts)


def _signed(value: int) -> str:
    return f"+{value:,}" if value > 0 else f"−{abs(value):,}" if value < 0 else "0"


# ------------------------------------------------------------------ 공정 하나의 숫자


def _rows_of(
    frame: pd.DataFrame, process: str, months: Sequence[int] | None = None
) -> pd.DataFrame:
    if frame.empty:
        return frame
    chosen = frame["공정"].astype("string").eq(process).fillna(False)
    if months is not None and "생산계획년월" in frame.columns:
        chosen &= pd.to_numeric(frame["생산계획년월"], errors="coerce").isin(list(months))
    return frame.loc[chosen.to_numpy()]


def first_shortage_month(
    level_plan: LevelPlan, process: str, months: Sequence[int] | None = None
) -> int | None:
    """그 공정이 목표에 처음 모자란 달(`과부족 < 0`). 없으면 None. `months` 를 주면 그 달
    안에서만."""
    return _first_short(_rows_of(level_plan.process_months, process, months))


def process_counts(level_plan: LevelPlan, process: str) -> tuple[int, int]:
    """(당긴 호기 대수, 신규 대수) — 공정 카드 배지와 같은 셈."""
    return _counts(_rows_of(level_plan.units, process))


def _split(frame: pd.DataFrame, months: Sequence[int] | None = None) -> dict[str, pd.DataFrame]:
    """공정마다 조각 — 공정 수만큼 표를 다시 거르지 않게 한 번에 가른다."""
    if frame.empty:
        return {}
    if months is not None and "생산계획년월" in frame.columns:
        inside = pd.to_numeric(frame["생산계획년월"], errors="coerce").isin(list(months))
        frame = frame.loc[inside.to_numpy()]
    keys = frame["공정"].astype("string").to_numpy()
    return {str(process): rows for process, rows in frame.groupby(keys, sort=False)}


def _first_short(rows: pd.DataFrame) -> int | None:
    if rows.empty:
        return None
    short = rows.loc[pd.to_numeric(rows["과부족"], errors="coerce").lt(0).fillna(False).to_numpy()]
    if short.empty:
        return None
    return int(pd.to_numeric(short["생산계획년월"]).min())


def _counts(units: pd.DataFrame) -> tuple[int, int]:
    if units.empty:
        return 0, 0
    new = int(units["구분"].eq(KIND_NEW).sum())
    return len(units) - new, new


def _worst_gap(rows: pd.DataFrame) -> float:
    if rows.empty:
        return 0.0
    worst = float(pd.to_numeric(rows["과부족"], errors="coerce").min())
    return round(-worst, 9) if worst < 0 else 0.0


def _days(units: pd.DataFrame) -> pd.Series:
    moved = units.loc[units["구분"].ne(KIND_NEW).to_numpy()]
    return pd.to_numeric(moved["단축일수"], errors="coerce").dropna()


def _as_date(value: object) -> date | None:
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, date):
        return value
    try:
        stamp = pd.Timestamp(str(value))
    except (TypeError, ValueError):
        return None
    return None if pd.isna(stamp) else stamp.date()


# ------------------------------------------------------------------ 보드


def progress_trend(rows: pd.DataFrame) -> ProgressTrend:
    """공정 하나의 진척 비교 행으로 낸 기준선 대비. 지금 계획에서 단축·신규가 모두 사라졌으면
    해소다.

    일수·추가N 은 `summarize_progress` 와 같은 셈이다(`필요 시점 지남` 은 양쪽에서 뺀다).
    """
    summary = summarize_progress(rows)
    change = summary.change
    virtual = summary.current_virtual - summary.past_virtual
    had = summary.past_days > 0 or summary.past_virtual > 0
    if had and summary.current_days == 0 and summary.current_virtual == 0:
        label = TREND_RESOLVED
    elif change < 0 or (change == 0 and virtual < 0):
        label = TREND_IMPROVED
    elif change > 0 or (change == 0 and virtual > 0):
        label = TREND_WORSENED
    else:
        label = TREND_UNCHANGED
    return ProgressTrend(label, change, summary.past_virtual, summary.current_virtual)


def process_board(
    level_plan: LevelPlan,
    processes: Sequence[str],
    *,
    today: date,
    months: Sequence[int] | None = None,
    progress_rows: pd.DataFrame | None = None,
    delayed: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """공정마다 한 줄(`BOARD_COLUMNS`), `processes` 차례 그대로.

    `months` 를 주면 첫 부족 달·월 최대 부족을 그 달 안에서만 본다(카드와 같은 범위). 진척 비교
    행(`progress_rows`)을 주면 기준선 대비 칸을, 이행 지연 표(`delayed_units`)를 주면 공정마다 그
    대수를 채운다.
    """
    delayed_counts: dict[str, int] = (
        {
            str(process): int(count)
            for process, count in delayed["공정"].astype(str).value_counts().items()
        }
        if delayed is not None and not delayed.empty
        else {}
    )
    months_by = _split(level_plan.process_months, months)
    units_by = _split(level_plan.units)
    progress_by = _split(progress_rows) if progress_rows is not None else {}
    empty_months = level_plan.process_months.iloc[0:0]
    empty_units = level_plan.units.iloc[0:0]
    rows: list[dict[str, object]] = []
    for process in processes:
        units = units_by.get(str(process), empty_units)
        process_months = months_by.get(str(process), empty_months)
        days = _days(units) if not units.empty else pd.Series(dtype="float64")
        targets = [day for day in (_as_date(value) for value in units.get("목표 Qual", [])) if day]
        earliest = min(targets) if targets else None
        moved, new = _counts(units)
        row: dict[str, object] = {
            "공정": process,
            "첫 부족 달": _first_short(process_months),
            "월 최대 부족": _worst_gap(process_months),
            "당길 호기": moved,
            "단축일 합계": int(days.sum()) if not days.empty else 0,
            "최대 단축": int(days.max()) if not days.empty else 0,
            "신규": new,
            "가장 이른 목표 Qual": earliest,
            "남은 일수": (earliest - today).days if earliest is not None else None,
            "기준선 대비": None,
            "단축일 증감": None,
            "이행 지연": None,
        }
        if progress_rows is not None:
            trend = progress_trend(progress_by.get(str(process), progress_rows.iloc[0:0]))
            row["기준선 대비"] = trend.text()
            row["단축일 증감"] = trend.change
            row["이행 지연"] = int(delayed_counts.get(process, 0))
        rows.append(row)
    frame = pd.DataFrame(rows, columns=list(BOARD_COLUMNS))
    for column in ("남은 일수", "단축일 증감", "이행 지연"):
        frame[column] = pd.array(frame[column].tolist(), dtype="Int64")
    frame["첫 부족 달"] = pd.array(frame["첫 부족 달"].tolist(), dtype="Int64")
    return frame


def board_order(board: pd.DataFrame, order: str, *, compared: bool) -> list[str]:
    """보드의 공정을 고른 차례로. 같으면 보드 차례(표시순서)다.

    - 목표 Qual 이른 순: 당길 호기·신규가 없는 공정은 뒤.
    - 최대 부족 큰 순: 월 최대 부족이 큰 공정부터.
    - 기준선 대비 악화 먼저: 단축일 증감이 큰 공정부터(악화 → 변동 없음 → 개선·해소). `compared` 가
      거짓(진척 비교 없음)이면 표시순서다.
    """
    processes = [str(process) for process in board["공정"]]
    if board.empty or order == ORDER_DISPLAY:
        return processes
    position = {process: index for index, process in enumerate(processes)}
    records = [
        {str(column): value for column, value in record.items()}
        for record in board.to_dict("records")
    ]
    if order == ORDER_EARLIEST_QUAL:

        def key(record: dict[str, object]) -> tuple[object, ...]:
            earliest = record["가장 이른 목표 Qual"]
            return (
                earliest is None,
                earliest or date.max,
                position[str(record["공정"])],
            )

    elif order == ORDER_LARGEST_GAP:

        def key(record: dict[str, object]) -> tuple[object, ...]:
            return (-float(str(record["월 최대 부족"])), position[str(record["공정"])])

    elif order == ORDER_WORSENED_FIRST and compared:

        def key(record: dict[str, object]) -> tuple[object, ...]:
            change = record["단축일 증감"]
            number = 0 if change is None or change is pd.NA else int(str(change))
            return (-number, position[str(record["공정"])])

    else:
        return processes
    return [str(record["공정"]) for record in sorted(records, key=key)]


# ------------------------------------------------------------------ 호기 마스터


def unit_qual_status(equipment: pd.DataFrame) -> pd.DataFrame:
    """설비키마다 Qual 일정·실적·상태·담당자(`UNIT_STATUS_COLUMNS`). 마스터가 검증을 못 넘으면 빈
    표.

    `ValueError` 를 삼킨다 — 계산 자리(필요 단축 일정 계획)가 이미 그 까닭을 알린다.
    """
    empty = pd.DataFrame({column: pd.Series(dtype="object") for column in UNIT_STATUS_COLUMNS})
    if equipment.empty:
        return empty
    try:
        prepared = prepare_equipment_master(equipment)
    except ValueError:
        return empty
    if prepared.empty:
        return empty
    keys = unit_keys(prepared).astype("string").str.strip()
    rows: list[dict[str, object]] = []
    for key, members in prepared.groupby(keys.to_numpy(), sort=True):
        quals = [day for day in (_as_date(v) for v in members[QUAL_DATE_COLUMN]) if day]
        actuals = [_as_date(value) for value in members[QUAL_ACTUAL_COLUMN]]
        statuses = [
            str(value).strip() for value in members[QUAL_STATUS_COLUMN] if not _blank(value)
        ]
        done = (
            all(actual is not None for actual in actuals)
            and len(statuses) == len(members)
            and all(status == DONE_STAGE_STATUS for status in statuses)
        )
        rows.append(
            {
                "호기": str(key),
                "공정": _distinct(members["공정소분류"]),
                QUAL_DATE_COLUMN: max(quals) if quals else None,
                QUAL_ACTUAL_COLUMN: (
                    max(actual for actual in actuals if actual is not None)
                    if actuals and all(actual is not None for actual in actuals)
                    else None
                ),
                QUAL_STATUS_COLUMN: _distinct(members[QUAL_STATUS_COLUMN]),
                MANAGER_COLUMN: _distinct(members[MANAGER_COLUMN]),
                "완료": done,
            }
        )
    return pd.DataFrame(rows, columns=list(UNIT_STATUS_COLUMNS))


def unit_managers(*frames: pd.DataFrame) -> dict[str, str]:
    """`호기` → 담당자. 앞 표가 먼저다(계획의 마스터 속성 → 호기 마스터). 빈 담당자는 싣지
    않는다."""
    managers: dict[str, str] = {}
    for frame in frames:
        if frame.empty or "호기" not in frame.columns or MANAGER_COLUMN not in frame.columns:
            continue
        for unit, manager in zip(frame["호기"], frame[MANAGER_COLUMN], strict=True):
            if _blank(manager) or str(unit) in managers:
                continue
            text = str(manager).strip()
            if text:
                managers[str(unit)] = text
    return managers


def _blank(value: object) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, float) and value != value:
        return True
    return isinstance(value, str) and not value.strip()


def _distinct(values: Iterable[object]) -> str | None:
    seen: list[str] = []
    for value in values:
        if _blank(value):
            continue
        text = str(value).strip()
        if text not in seen:
            seen.append(text)
    return ", ".join(seen) or None


# ------------------------------------------------------------------ 기한 임박·이행 지연


def imminent_units(
    level_plan: LevelPlan,
    processes: Iterable[str],
    *,
    today: date,
    days: int,
    managers: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """목표 Qual(가상 호기는 필요 Qual)이 오늘부터 `days` 일 안인 호기(`IMMINENT_COLUMNS`).

    남은 일수가 짧은 차례, 같으면 공정·호기 차례다. 오늘 바로 그날(0일)도 든다.
    """
    wanted = {str(process) for process in processes}
    units = level_plan.units
    rows: list[dict[str, object]] = []
    if not units.empty:
        for record in units.to_dict("records"):
            process = str(record["공정"])
            target = _as_date(record["목표 Qual"])
            if process not in wanted or target is None:
                continue
            left = (target - today).days
            if not 0 <= left <= days:
                continue
            virtual = record["구분"] == KIND_NEW
            cut = pd.to_numeric(pd.Series([record["단축일수"]]), errors="coerce").iloc[0]
            rows.append(
                {
                    "공정": process,
                    "호기": str(record["호기"]),
                    "구분": str(record["구분"]),
                    "목표 Qual": target,
                    "남은 일수": left,
                    "단축일수": None if virtual or pd.isna(cut) else int(cut),
                    MANAGER_COLUMN: (managers or {}).get(str(record["호기"])),
                }
            )
    frame = pd.DataFrame(rows, columns=list(IMMINENT_COLUMNS))
    if frame.empty:
        return frame
    frame = frame.sort_values(["남은 일수", "공정", "호기"], kind="stable").reset_index(drop=True)
    for column in ("남은 일수", "단축일수"):
        frame[column] = pd.array(frame[column].tolist(), dtype="Int64")
    return frame


def delayed_units(
    progress_rows: pd.DataFrame,
    status: pd.DataFrame,
    *,
    today: date,
    processes: Iterable[str],
) -> pd.DataFrame:
    """기준선 목표 Qual 이 오늘보다 앞인데 마스터 Qual 이 끝나지 않은 당긴 호기(`DELAYED_COLUMNS`).

    끝났다 = 모든 모듈 행에 `Qual실적` 이 있고 `Qual상태` 가 「완료」. 가상 호기(추가N)는 마스터에
    없어 보지 않는다. 마스터에 없는 호기는 실적이 없으므로 지연이고 `Qual상태` 에 「마스터에 없음」
    을 적는다. 지난 일수가 긴 차례, 같으면 공정·호기 차례다.
    """
    wanted = {str(process) for process in processes}
    by_unit = (
        {str(record["호기"]): record for record in status.to_dict("records")}
        if not status.empty
        else {}
    )
    rows: list[dict[str, object]] = []
    if not progress_rows.empty:
        for record in progress_rows.to_dict("records"):
            process = str(record["공정"])
            if process not in wanted or record["구분"] != KIND_SHORTENED:
                continue
            need = _as_date(record["과거 필요 시점"])
            if need is None or not need < today:
                continue
            unit = str(record["호기"])
            master = by_unit.get(unit)
            if master is not None and bool(master["완료"]):
                continue
            rows.append(
                {
                    "공정": process,
                    "호기": unit,
                    "기준선 목표 Qual": need,
                    "지난 일수": (today - need).days,
                    QUAL_DATE_COLUMN: None if master is None else master[QUAL_DATE_COLUMN],
                    QUAL_ACTUAL_COLUMN: None if master is None else master[QUAL_ACTUAL_COLUMN],
                    QUAL_STATUS_COLUMN: (
                        MASTER_MISSING if master is None else master[QUAL_STATUS_COLUMN]
                    ),
                    MANAGER_COLUMN: None if master is None else master[MANAGER_COLUMN],
                }
            )
    frame = pd.DataFrame(rows, columns=list(DELAYED_COLUMNS))
    if frame.empty:
        return frame
    frame = frame.sort_values(
        ["지난 일수", "공정", "호기"], ascending=[False, True, True], kind="stable"
    ).reset_index(drop=True)
    frame["지난 일수"] = pd.array(frame["지난 일수"].tolist(), dtype="Int64")
    return frame
