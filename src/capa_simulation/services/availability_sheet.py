# Purpose: Static 세 표와 설비 일정 기준(실제·반사실) 월별 분해를 9행 비교 시트·호기 분해로 낸다.

"""Static · 설비 일정 기준 가용대수 비교 시트(9행).

가용설비 현황 「Static 대비 일정」 탭의 `분류별 내역` 이 보이는 시트다(2026-10-17 사용자 결정). 세
묶음 × 세 항목이다.

    Static            보유 · 대여 · 가용     기준정보 RQ_EQP_OWN · LENT · AVBL 값 그대로(대수)
    설비 일정 기준      보유 · 대여(비가동) · 가용   설비 DB 일정·비가동·Cut-off(환산대수)
    GAP               보유 · 대여 · 가용     설비 일정 기준 − Static (짝 맞는 행끼리)

**세 묶음 모두 `가용 = 보유 + 대여` 로 읽는다.** 대여는 두 묶음 모두 음수로 보인다 — Static 대여는
`−설비대여평가`(크기는 DB 그대로), 설비 일정 기준 대여는 비가동이 실제로 깎은 가용이다.

## 설비 일정 기준 세 행 — 반사실

- **가용** = 지금의 `available_subtotal(...)["Dynamic가용환산대수"]` 그대로(기존보유 + 「가용」
  환산). 확보율 교차검증의 분자·필요 단축 일정의 가용·공정 Capa 상세 ② `가용 (환산)` 과 같은 값이다.
- **보유** = 기존보유 + **비가동만 비운** 생애주기 구간에서 「가용」 분류에 든 환산대수. 같은
  마스터·같은 구간 범위·같은 엔진으로 비가동 표만 비워 한 번 더 만든 구간(반사실)이다. 그래서 Qual
  다음 날·정지·반출/이설 당일·모듈 지분·W/D 경계는 실제와 반사실에서 같아 상쇄되고, 다른 것은
  비가동뿐이다 — 비가동은 가용을 깎기만 하므로 반사실 ≥ 실제다. 셋업 진행중·보관·입고 예정·정지/반출
  뒤·사용기준 밖 호기는 반사실에서도 가용이 아니라 보유에 들지 않는다.
- **대여(비가동)** = 가용 − 보유 ≤ 0. 행끼리 `보유 + 대여 = 가용` 이 부동소수 오차 안에서 선다. 셋업
  중·보관 호기에 걸린 비가동은 가용을 깎지 않았으므로 들지 않는다 — 호기 상태 분류의 `운영 비가동`
  과 다를 수 있는 까닭이다(공정 Capa 상세 ④ 의 흐린 화살표와 같은 뜻).

세 행 모두 **환산 축**이다. GAP 도 설비 일정 기준(환산) − Static(대수)으로 맞댄다 — 확보율
교차검증이 이미 두 값을 같은 확보율의 분자로 맞대므로 같은 잣대다(대수 축은 「호기 목록」의 `대수`
칸).

## 「—」 칸

맞댈 수 없는 칸은 값 대신 까닭(`REASON_*`)을 갖는다. 시트 모양은 늘 9행이다.

- 한쪽에만 있는 공정 — 없는 쪽 세 행과 GAP 세 행.
- 한쪽에 그 달 자료가 아예 없는 달 — 그쪽 세 행과 GAP 세 행. 「자료 있는 달」은 쪽마다 **한 번**
  정한다 — 설비 일정 기준은 실제 월별 프레임에 (어떤 분류로든) 행이 있는 달, Static 은 세 표 가운데
  하나라도 행이 있는 달. 세 GAP 행이 그 집합을 함께 쓴다(한 달 내내 비가동인 공정도 가용 0 으로 GAP
  을 낸다).
- 호기 필터 중이거나 Static 을 읽지 못했으면 — Static 세 행과 GAP 세 행(`static_blocked`).

이름이 맞는 공정의 빈 달은 0 이다. 전체 합계는 양쪽에 다 있는 공정만 더한다(화면이 범위를 넘긴다).
Static 의 `보유 + 대여 ≠ 가용`(기준정보 화면이 세 표를 따로 고친 달)은 `mismatch` 로 알린다.

어느 DB 도 열지 않는다. 프레임을 받아 프레임을 돌려주는 순수 함수다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final, cast

import pandas as pd

from capa_simulation.services.equipment_contract import EQUIPMENT_ID_COLUMN
from capa_simulation.services.monthly_equipment_availability import (
    BASELINE_CATEGORY,
    available_subtotal,
)
from capa_simulation.services.process_capa_detail import AVAILABILITY_TOLERANCE
from capa_simulation.services.process_cutoff import cutoff_lookup
from capa_simulation.services.wd_window import wd_window

__all__ = [
    "BASELINE_COLUMN",
    "BREAKDOWN_COLUMNS",
    "BREAKDOWN_LENT_COLUMN",
    "GAP_PAIRS",
    "GAP_ROWS",
    "GROUP_GAP",
    "GROUP_SCHEDULE",
    "GROUP_STATIC",
    "KIND_BASELINE_LINE",
    "KIND_UNIT_LINE",
    "MISMATCH_COLUMN",
    "REASON_NO_DYNAMIC_MONTH",
    "REASON_NO_DYNAMIC_PROCESS",
    "REASON_NO_STATIC_MONTH",
    "REASON_NO_STATIC_PROCESS",
    "REASON_STATIC_UNREADABLE",
    "REASON_UNIT_FILTER",
    "ROW_GAP_AVAILABLE",
    "ROW_GAP_LENT",
    "ROW_GAP_OWNED",
    "ROW_GROUPS",
    "ROW_ITEMS",
    "ROW_SCHEDULE_AVAILABLE",
    "ROW_SCHEDULE_LENT",
    "ROW_SCHEDULE_OWNED",
    "ROW_STATIC_AVAILABLE",
    "ROW_STATIC_LENT",
    "ROW_STATIC_OWNED",
    "SCHEDULE_ROWS",
    "SHEET_ROWS",
    "STATIC_ROWS",
    "AvailabilitySheet",
    "SheetView",
    "build_availability_sheet",
    "downtime_without_loss",
    "sheet_view",
    "unit_availability_breakdown",
]

MONTH: Final = "생산계획년월"
_KEYS: Final = [MONTH, "공정"]

# ------------------------------------------------------------------ 행 id
ROW_STATIC_OWNED: Final = "static:owned"
ROW_STATIC_LENT: Final = "static:lent"
ROW_STATIC_AVAILABLE: Final = "static:available"
ROW_SCHEDULE_OWNED: Final = "sched:owned"
ROW_SCHEDULE_LENT: Final = "sched:lent"
ROW_SCHEDULE_AVAILABLE: Final = "sched:available"
ROW_GAP_OWNED: Final = "gap:owned"
ROW_GAP_LENT: Final = "gap:lent"
ROW_GAP_AVAILABLE: Final = "gap:available"

STATIC_ROWS: Final = (ROW_STATIC_OWNED, ROW_STATIC_LENT, ROW_STATIC_AVAILABLE)
SCHEDULE_ROWS: Final = (ROW_SCHEDULE_OWNED, ROW_SCHEDULE_LENT, ROW_SCHEDULE_AVAILABLE)
GAP_ROWS: Final = (ROW_GAP_OWNED, ROW_GAP_LENT, ROW_GAP_AVAILABLE)
SHEET_ROWS: Final = (*STATIC_ROWS, *SCHEDULE_ROWS, *GAP_ROWS)
# GAP 행 → (설비 일정 기준 행, Static 행).
GAP_PAIRS: Final[Mapping[str, tuple[str, str]]] = {
    gap: (schedule, static)
    for gap, schedule, static in zip(GAP_ROWS, SCHEDULE_ROWS, STATIC_ROWS, strict=True)
}

GROUP_STATIC: Final = "Static"
GROUP_SCHEDULE: Final = "설비 일정 기준"
GROUP_GAP: Final = "GAP (설비 일정 − Static)"
ROW_GROUPS: Final[Mapping[str, str]] = {
    **{row: GROUP_STATIC for row in STATIC_ROWS},
    **{row: GROUP_SCHEDULE for row in SCHEDULE_ROWS},
    **{row: GROUP_GAP for row in GAP_ROWS},
}
ROW_ITEMS: Final[Mapping[str, str]] = {
    ROW_STATIC_OWNED: "보유",
    ROW_STATIC_LENT: "대여",
    ROW_STATIC_AVAILABLE: "가용",
    ROW_SCHEDULE_OWNED: "보유",
    ROW_SCHEDULE_LENT: "대여 (비가동)",
    ROW_SCHEDULE_AVAILABLE: "가용",
    ROW_GAP_OWNED: "보유",
    ROW_GAP_LENT: "대여",
    ROW_GAP_AVAILABLE: "가용",
}

# 시트 프레임의 값 칸(월·공정 한 줄). GAP 은 범위를 정한 뒤(`sheet_view`) 뺀다.
BASELINE_COLUMN: Final = BASELINE_CATEGORY.name
MISMATCH_COLUMN: Final = "Static 불일치"
_VALUE_COLUMNS: Final = (*STATIC_ROWS, *SCHEDULE_ROWS)

# ------------------------------------------------------------------ 「—」 까닭
REASON_NO_STATIC_PROCESS: Final = "no_static_process"
REASON_NO_DYNAMIC_PROCESS: Final = "no_dynamic_process"
REASON_NO_STATIC_MONTH: Final = "no_static_month"
REASON_NO_DYNAMIC_MONTH: Final = "no_dynamic_month"
REASON_UNIT_FILTER: Final = "unit_filter"
REASON_STATIC_UNREADABLE: Final = "static_unreadable"

# ------------------------------------------------------------------ 호기 분해
KIND_BASELINE_LINE: Final = "기존보유"
KIND_UNIT_LINE: Final = "호기"
BREAKDOWN_LENT_COLUMN: Final = "대여 (비가동)"
BREAKDOWN_COLUMNS: Final = (
    MONTH,
    "공정",
    "구분",
    EQUIPMENT_ID_COLUMN,
    "설비키",
    "기존보유분류",
    "환산비",
    "구간일수",
    "비가동 없음 기여일수",
    "손실 기여일수",
    "실제 기여일수",
    "보유",
    BREAKDOWN_LENT_COLUMN,
    "가용",
    "비가동 내역",
)
_AVAILABLE_CATEGORY: Final = "가용"
_DOWNTIME_CATEGORY: Final = "운영 비가동"


@dataclass(frozen=True, eq=False)
class AvailabilitySheet:
    """월 × 공정 한 줄의 Static 세 값·설비 일정 기준 세 값(+기존보유)과 맞댈 수 있는 범위."""

    rows: pd.DataFrame
    """`생산계획년월`·`공정`·`기존보유`·Static 세 행·설비 일정 기준 세 행·`Static 불일치`."""

    months: tuple[int, ...]
    dynamic_processes: tuple[str, ...] = ()
    static_processes: tuple[str, ...] = ()
    dynamic_months: tuple[int, ...] = ()
    """설비 일정 기준 자료가 있는 달(실제 월별 프레임에 어떤 분류로든 행이 있는 달)."""

    static_months: tuple[int, ...] = ()
    """Static 자료가 있는 달(세 표 가운데 하나라도 행이 있는 달)."""

    has_counterfactual: bool = True
    """반사실(비가동 비운 구간)을 받았는가. 없으면 설비 일정 기준 보유·대여가 비어 있다
    (그림 전용)."""

    @property
    def dynamic_only(self) -> list[str]:
        """설비에는 있는데 기준정보(Static)에 없는 공정."""
        return sorted(set(self.dynamic_processes) - set(self.static_processes))

    @property
    def static_only(self) -> list[str]:
        """기준정보에는 있는데 설비 일정 기준이 나오지 않은 공정(Cut-off·설비 없음)."""
        return sorted(set(self.static_processes) - set(self.dynamic_processes))


@dataclass(frozen=True, eq=False)
class SheetView:
    """화면에 얹는 9행 — 범위(공정 하나 또는 전체 합계)를 정해 더한 것."""

    months: tuple[int, ...]
    values: pd.DataFrame
    """행 = `SHEET_ROWS`, 열 = 달(정수). 「—」 칸은 NaN 이다."""

    reasons: Mapping[tuple[str, int], str] = field(default_factory=dict)
    """「—」 칸(행 id, 달) → 까닭(`REASON_*`)."""

    mismatch: frozenset[int] = frozenset()
    """Static `보유 + 대여 ≠ 가용` 인 달."""

    baseline: pd.Series = field(default_factory=lambda: pd.Series(dtype="float64"))
    """달 → 기존보유(설비 일정 기준 가용 안의 몫). 설비 일정 기준이 「—」 인 달은 NaN."""

    def value(self, row: str, month: int) -> float | None:
        """그 칸의 값. 「—」 면 None."""
        number = float(cast(float, self.values.at[row, month]))
        return None if number != number else number

    def reason(self, row: str, month: int) -> str | None:
        return self.reasons.get((row, month))


# ================================================================== 시트


def build_availability_sheet(
    actual_monthly: pd.DataFrame,
    free_monthly: pd.DataFrame | None,
    static_owned: pd.DataFrame | None,
    static_lent: pd.DataFrame | None,
    static_available: pd.DataFrame | None,
    months: Sequence[int],
) -> AvailabilitySheet:
    """월 × 공정 시트 프레임.

    `actual_monthly` 는 실제 구간의 `build_monthly_equipment_availability` 결과, `free_monthly` 는
    같은 마스터·같은 구간 범위에서 비가동만 비운 구간의 결과다(None 이면 보유·대여를 비운다 —
    「가용대수 비교」 그림처럼 가용만 쓰는 자리). Static 세 표는
    `RQ_EQP_OWN`(`설비보유`)·`RQ_EQP_LENT`(`설비대여평가`)·`RQ_EQP_AVBL`(`가용대수`)의 컬럼
    그대로다. 표마다 빈 칸은 0 이고, Static 쪽 공정 집합은 `RQ_EQP_AVBL` 로
    정한다(`availability_gap` 과 같은 `dynamic_only`·`static_only`).
    """
    wanted = [int(month) for month in dict.fromkeys(months)]
    owned = _normalized(static_owned, "설비보유", wanted)
    lent = _normalized(static_lent, "설비대여평가", wanted)
    available = _normalized(static_available, "가용대수", wanted)
    actual = _in_months(actual_monthly, wanted)

    dynamic_processes = _processes(actual)
    static_processes = {str(name) for name in available.index.get_level_values("공정")}
    processes = sorted(dynamic_processes | static_processes)
    index = pd.MultiIndex.from_product([wanted, processes], names=_KEYS)
    frame = pd.DataFrame(index=index)

    baseline = _category_sum(actual, BASELINE_CATEGORY.name)
    subtotal = (
        available_subtotal(actual).set_index(_KEYS)["Dynamic가용환산대수"]
        if not actual.empty
        else pd.Series(dtype="float64")
    )
    frame[BASELINE_COLUMN] = _aligned(baseline, index)
    frame[ROW_STATIC_OWNED] = _aligned(owned, index)
    frame[ROW_STATIC_LENT] = -_aligned(lent, index)
    frame[ROW_STATIC_AVAILABLE] = _aligned(available, index)
    frame[ROW_SCHEDULE_AVAILABLE] = _aligned(subtotal, index)
    if free_monthly is not None:
        free = _in_months(free_monthly, wanted)
        free_available = _category_sum(free, _AVAILABLE_CATEGORY)
        frame[ROW_SCHEDULE_OWNED] = frame[BASELINE_COLUMN] + _aligned(free_available, index)
        frame[ROW_SCHEDULE_LENT] = frame[ROW_SCHEDULE_AVAILABLE] - frame[ROW_SCHEDULE_OWNED] + 0.0
    else:
        frame[ROW_SCHEDULE_OWNED] = float("nan")
        frame[ROW_SCHEDULE_LENT] = float("nan")

    static_months = {
        int(month)
        for series in (owned, lent, available)
        for month in series.index.get_level_values(MONTH)
    }
    in_static = frame.index.get_level_values("공정").isin(list(static_processes))
    in_static &= frame.index.get_level_values(MONTH).isin(list(static_months))
    residual = frame[ROW_STATIC_OWNED] + frame[ROW_STATIC_LENT] - frame[ROW_STATIC_AVAILABLE]
    frame[MISMATCH_COLUMN] = residual.abs().gt(AVAILABILITY_TOLERANCE) & in_static

    rows = frame.reset_index()
    rows[MONTH] = rows[MONTH].astype("int64")
    rows["공정"] = rows["공정"].astype("string")
    dynamic_months = (
        {int(month) for month in pd.to_numeric(actual[MONTH], errors="coerce").dropna()}
        if not actual.empty
        else set()
    )
    return AvailabilitySheet(
        rows=rows.loc[:, [*_KEYS, BASELINE_COLUMN, *_VALUE_COLUMNS, MISMATCH_COLUMN]],
        months=tuple(wanted),
        dynamic_processes=tuple(sorted(dynamic_processes)),
        static_processes=tuple(sorted(static_processes)),
        dynamic_months=tuple(sorted(dynamic_months)),
        static_months=tuple(sorted(static_months)),
        has_counterfactual=free_monthly is not None,
    )


def sheet_view(
    sheet: AvailabilitySheet,
    *,
    processes: Collection[str],
    static_blocked: str | None = None,
) -> SheetView:
    """`processes`(공정 하나 또는 전체 합계의 범위)를 더한 9행.

    `static_blocked` 를 주면(`REASON_UNIT_FILTER`·`REASON_STATIC_UNREADABLE`) Static 세 행과 GAP 세
    행을 그 까닭으로 비운다. 범위가 한쪽에만 있으면 없는 쪽과 GAP 을, 한쪽에 자료가 없는 달은 그쪽과
    GAP 을 비운다.
    """
    months = sheet.months
    scope = {str(name) for name in processes}
    scoped = sheet.rows.loc[sheet.rows["공정"].astype(str).isin(scope)]
    columns = [BASELINE_COLUMN, *_VALUE_COLUMNS]
    sums = (
        scoped.groupby(MONTH)[columns].sum(min_count=1).reindex(list(months))
        if not scoped.empty
        else pd.DataFrame(
            index=pd.Index(list(months), name=MONTH), columns=columns, dtype="float64"
        )
    )
    dynamic_side = bool(scope & set(sheet.dynamic_processes))
    static_side = bool(scope & set(sheet.static_processes))
    dynamic_months = set(sheet.dynamic_months)
    static_months = set(sheet.static_months)

    values = pd.DataFrame(
        float("nan"), index=pd.Index(list(SHEET_ROWS)), columns=list(months), dtype="float64"
    )
    reasons: dict[tuple[str, int], str] = {}
    baseline = pd.Series(float("nan"), index=list(months), dtype="float64")
    mismatch: set[int] = set()
    flagged = (
        set(scoped.loc[scoped[MISMATCH_COLUMN], MONTH].astype(int)) if not scoped.empty else set()
    )
    for month in months:
        schedule_reason = (
            REASON_NO_DYNAMIC_PROCESS
            if not dynamic_side
            else (REASON_NO_DYNAMIC_MONTH if month not in dynamic_months else None)
        )
        static_reason = static_blocked or (
            REASON_NO_STATIC_PROCESS
            if not static_side
            else (REASON_NO_STATIC_MONTH if month not in static_months else None)
        )
        record = sums.loc[month]
        cells: dict[str, float] = {}
        for row in SCHEDULE_ROWS:
            if schedule_reason is not None:
                reasons[(row, month)] = schedule_reason
            elif row == ROW_SCHEDULE_AVAILABLE or sheet.has_counterfactual:
                cells[row] = _number(record[row])
        if schedule_reason is None:
            baseline[month] = _number(record[BASELINE_COLUMN])
        for row in STATIC_ROWS:
            if static_reason is None:
                cells[row] = _number(record[row])
            else:
                reasons[(row, month)] = static_reason
        if static_reason is None and month in flagged:
            mismatch.add(month)
        gap_reason = (
            static_blocked
            or (REASON_NO_DYNAMIC_PROCESS if not dynamic_side else None)
            or (REASON_NO_STATIC_PROCESS if not static_side else None)
            or schedule_reason
            or static_reason
        )
        for gap, (schedule, static) in GAP_PAIRS.items():
            if gap_reason is not None:
                reasons[(gap, month)] = gap_reason
            elif schedule in cells and static in cells:
                cells[gap] = cells[schedule] - cells[static] + 0.0
        for row, number in cells.items():
            values.at[row, month] = number
    return SheetView(
        months=tuple(months),
        values=values,
        reasons=reasons,
        mismatch=frozenset(mismatch),
        baseline=baseline,
    )


def _normalized(frame: pd.DataFrame | None, column: str, months: list[int]) -> pd.Series:
    """`(생산계획년월, 공정)` 합계 한 칸. 공정은 앞뒤 공백을 떼고 조회 달만 남긴다."""
    empty = pd.Series(
        dtype="float64",
        index=pd.MultiIndex.from_tuples([], names=_KEYS),
    )
    if frame is None or frame.empty:
        return empty
    required = {MONTH, "공정", column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Static 표에 필수 컬럼이 없습니다: {', '.join(missing)}")
    table = frame.loc[:, [MONTH, "공정", column]].copy()
    table[MONTH] = pd.to_numeric(table[MONTH], errors="coerce")
    table = table.dropna(subset=[MONTH, "공정"])
    table[MONTH] = table[MONTH].astype("int64")
    table["공정"] = table["공정"].astype("string").str.strip()
    table[column] = pd.to_numeric(table[column], errors="coerce")
    table = table.loc[table[MONTH].isin(months)]
    if table.empty:
        return empty
    # 같은 월·공정이 여러 줄로 오면 합친다 — 기준정보 편집이 쪼개 놓았을 수 있다. 빈 값은 0 대다.
    summed = table.groupby(_KEYS)[column].sum()
    summed.index = summed.index.set_names(_KEYS)
    return summed.astype("float64")


def _in_months(frame: pd.DataFrame, months: list[int]) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.loc[frame[MONTH].isin(months)]


def _processes(frame: pd.DataFrame) -> set[str]:
    if frame.empty or "공정" not in frame.columns:
        return set()
    return {str(value).strip() for value in frame["공정"].dropna() if str(value).strip()}


def _category_sum(frame: pd.DataFrame, category: str) -> pd.Series:
    """한 분류의 `(월, 공정)` 환산대수 합."""
    if frame.empty:
        return pd.Series(dtype="float64")
    chosen = frame.loc[frame["분류"].astype(str).eq(category)]
    if chosen.empty:
        return pd.Series(dtype="float64")
    keyed = chosen.assign(공정=chosen["공정"].astype(str).str.strip())
    return keyed.groupby(_KEYS)["환산대수"].sum()


def _aligned(series: pd.Series, index: pd.MultiIndex) -> pd.Series:
    """시트 줄 차례로 맞추고 빈 칸은 0 이다."""
    if series.empty:
        return pd.Series(0.0, index=index, dtype="float64")
    keyed = series.copy()
    keyed.index = pd.MultiIndex.from_tuples(
        [(int(month), str(process)) for month, process in keyed.index], names=_KEYS
    )
    return keyed.reindex(index).fillna(0.0).astype("float64")


def _number(value: object) -> float:
    """범위의 합 한 칸. 범위에 줄이 없으면(NaN) 0 이다."""
    number = float(value)  # type: ignore[arg-type]
    return 0.0 if number != number else number


# ================================================================== 호기 분해


def unit_availability_breakdown(
    actual: pd.DataFrame,
    free: pd.DataFrame,
    *,
    conversion_ratios: Mapping[str, float] | None = None,
    downtime: pd.DataFrame | None = None,
    cutoff: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """호기 × 월 한 줄에 보유·대여(비가동)·가용(`BREAKDOWN_COLUMNS`). 기존보유 줄을 함께 싣는다.

    `actual`·`free` 는 같은 범위의 `build_monthly_equipment_contributions` 결과다 — 실제 구간과
    비가동을 비운 반사실 구간. 「가용」 분류의 호기 줄만 맞대고 한쪽에 없는 칸은 0 이다. 보유 =
    반사실 환산대수, 가용 = 실제 환산대수, 대여 = 가용 − 보유(≤ 0). 그래서 같은 (월, 공정)의 줄을
    더하면 시트의 세 칸이다. 기여일수는 그 달 W/D 구간과 겹친 날 수이고 `손실 기여일수` = 반사실 −
    실제다 — 정지·반출/이설일에 닿는 비가동은 그날부터 세므로 `비가동 내역` 의 날짜보다 하루 길 수
    있다.

    `비가동 내역`(유형 시작~종료)은 `downtime`·`cutoff` 를 주면 그 달 W/D 구간에 걸친 비가동을
    적는다 — 보이기만 하고 더하지 않는다. 값은 반올림하지 않는다.
    """
    ratios = conversion_ratios or {}
    unit_keys = [MONTH, "공정", EQUIPMENT_ID_COLUMN, "설비키", "구간일수"]
    left = _available_units(actual, unit_keys)
    right = _available_units(free, unit_keys)
    merged = left.merge(right, on=unit_keys, how="outer", suffixes=("_실제", "_반사실"))
    for column in ("기여일수_실제", "기여일수_반사실"):
        merged[column] = pd.to_numeric(merged[column]).fillna(0).astype("int64")
    for column in ("환산대수_실제", "환산대수_반사실"):
        merged[column] = pd.to_numeric(merged[column]).fillna(0.0).astype("float64")
    units = pd.DataFrame(
        {
            MONTH: merged[MONTH].astype("int64"),
            "공정": merged["공정"].astype("string"),
            "구분": KIND_UNIT_LINE,
            EQUIPMENT_ID_COLUMN: merged[EQUIPMENT_ID_COLUMN].astype("string"),
            "설비키": merged["설비키"].astype("string"),
            "기존보유분류": pd.Series(pd.NA, index=merged.index, dtype="string"),
            "환산비": [
                float(ratios.get(str(unit).strip(), 1.0)) for unit in merged[EQUIPMENT_ID_COLUMN]
            ],
            "구간일수": merged["구간일수"].astype("int64"),
            "비가동 없음 기여일수": merged["기여일수_반사실"].astype("Int64"),
            "손실 기여일수": (merged["기여일수_반사실"] - merged["기여일수_실제"]).astype("Int64"),
            "실제 기여일수": merged["기여일수_실제"].astype("Int64"),
            "보유": merged["환산대수_반사실"],
            BREAKDOWN_LENT_COLUMN: merged["환산대수_실제"] - merged["환산대수_반사실"] + 0.0,
            "가용": merged["환산대수_실제"],
        }
    )
    units["비가동 내역"] = _downtime_notes(units, downtime, cutoff)

    base = (
        actual.loc[actual["분류"].astype(str).eq(BASELINE_CATEGORY.name)]
        if not actual.empty
        else actual
    )
    baseline = pd.DataFrame(
        {
            MONTH: base[MONTH].astype("int64") if not base.empty else pd.Series(dtype="int64"),
            "공정": base["공정"].astype("string") if not base.empty else pd.Series(dtype="string"),
            "구분": KIND_BASELINE_LINE,
            EQUIPMENT_ID_COLUMN: pd.Series(pd.NA, index=base.index, dtype="string"),
            "설비키": pd.Series(pd.NA, index=base.index, dtype="string"),
            "기존보유분류": (
                base["기존보유분류"].astype("string")
                if not base.empty
                else pd.Series(dtype="string")
            ),
            "환산비": float("nan"),
            "구간일수": base["구간일수"].astype("int64")
            if not base.empty
            else pd.Series(dtype="int64"),
            "비가동 없음 기여일수": pd.Series(pd.NA, index=base.index, dtype="Int64"),
            "손실 기여일수": pd.Series(pd.NA, index=base.index, dtype="Int64"),
            "실제 기여일수": pd.Series(pd.NA, index=base.index, dtype="Int64"),
            "보유": base["환산대수"].astype("float64")
            if not base.empty
            else pd.Series(dtype="float64"),
            BREAKDOWN_LENT_COLUMN: 0.0,
            "가용": base["환산대수"].astype("float64")
            if not base.empty
            else pd.Series(dtype="float64"),
            "비가동 내역": "",
        }
    )
    pieces = [piece for piece in (baseline, units) if not piece.empty]
    if not pieces:
        return _empty_breakdown()
    result = pd.concat(pieces, ignore_index=True)
    result["_order"] = result["구분"].map({KIND_BASELINE_LINE: 0, KIND_UNIT_LINE: 1})
    result = result.sort_values(
        [MONTH, "공정", "_order", EQUIPMENT_ID_COLUMN], kind="stable", na_position="first"
    )
    return result.drop(columns="_order").loc[:, list(BREAKDOWN_COLUMNS)].reset_index(drop=True)


def downtime_without_loss(actual: pd.DataFrame, breakdown: pd.DataFrame) -> pd.DataFrame:
    """가용을 깎지 않은 비가동 — 호기 상태 `운영 비가동` 환산대수에서 손실(−대여)을 뺀 몫이 남는
    호기.

    셋업 중·보관 호기에 걸린 비가동처럼 원래 가용이 아니던 날의 비가동이다. 시트의 대여(비가동)에는
    들지 않고, 호기 목록의 `운영 비가동` 분류에는 든다. 칸
    (`생산계획년월`·`공정`·`설비명`·`환산대수`).
    """
    columns = [MONTH, "공정", EQUIPMENT_ID_COLUMN, "환산대수"]
    if actual.empty:
        return pd.DataFrame({column: [] for column in columns})
    offline = actual.loc[
        actual["분류"].astype(str).eq(_DOWNTIME_CATEGORY) & actual[EQUIPMENT_ID_COLUMN].notna()
    ]
    if offline.empty:
        return pd.DataFrame({column: [] for column in columns})
    keys = [MONTH, "공정", EQUIPMENT_ID_COLUMN]
    off = (
        offline.assign(**{EQUIPMENT_ID_COLUMN: offline[EQUIPMENT_ID_COLUMN].astype(str)})
        .groupby(keys)["환산대수"]
        .sum()
    )
    units = breakdown.loc[breakdown["구분"].eq(KIND_UNIT_LINE)]
    loss = (
        -units.assign(**{EQUIPMENT_ID_COLUMN: units[EQUIPMENT_ID_COLUMN].astype(str)})
        .groupby(keys)[BREAKDOWN_LENT_COLUMN]
        .sum()
    )
    left = off.sub(loss.reindex(off.index).fillna(0.0))
    left = left.loc[left.gt(AVAILABILITY_TOLERANCE)]
    return left.rename("환산대수").reset_index().loc[:, columns]


def _available_units(contributions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """「가용」 호기 줄만(기존보유 줄은 뺀다), 모듈 행 × 월로."""
    columns = [*keys, "기여일수", "환산대수"]
    if contributions.empty:
        return pd.DataFrame({column: pd.Series(dtype="object") for column in columns})
    chosen = contributions.loc[
        contributions["분류"].astype("string").eq(_AVAILABLE_CATEGORY).fillna(False).to_numpy()
        & contributions[EQUIPMENT_ID_COLUMN].notna().to_numpy()
    ]
    frame = chosen.loc[:, columns].copy()
    frame[EQUIPMENT_ID_COLUMN] = frame[EQUIPMENT_ID_COLUMN].astype(str)
    frame["설비키"] = frame["설비키"].astype(str)
    frame["공정"] = frame["공정"].astype(str)
    return frame.groupby(keys, as_index=False).agg({"기여일수": "sum", "환산대수": "sum"})


def _downtime_notes(
    units: pd.DataFrame, downtime: pd.DataFrame | None, cutoff: pd.DataFrame | None
) -> list[str]:
    """줄마다 그 달 W/D 구간에 걸친 비가동(「유형 MM.DD~MM.DD」, 열린 것은 「~계속」).

    「걸친」은 손실을 세는 잣대와 같다 — 상태는 바뀐 다음 날부터라 비가동은 기여일로 (시작일,
    종료일+1] 을 깎고, W/D 구간 (경계 시작, 경계 끝] 과 겹치면 적는다. 경계 끝 날 시작했거나 경계
    시작 날보다 먼저 끝난 비가동은 그 달 손실이 0 이라 적지 않는다(「내내 비가동인데 손실 0」으로
    읽히지 않게). 경계 시작 날 끝난 비가동은 그 달 첫날 하루를 깎아 적는다 — 다만 종료일 다음 날이
    그 설비키의 정지·반출/이설일이면 엔진이 종료일까지만 깎으므로, 그 줄에 `손실 기여일수` 가 있을
    때만 적는다.
    """
    if units.empty or downtime is None or downtime.empty or cutoff is None or cutoff.empty:
        return [""] * len(units)
    days = cutoff_lookup(cutoff)
    by_unit: dict[str, list[tuple[str, date, date | None]]] = {}
    for unit, kind, start, end in zip(
        downtime[EQUIPMENT_ID_COLUMN],
        downtime["비가동유형"],
        downtime["시작일"],
        downtime["종료일"],
        strict=True,
    ):
        begin = _day(start)
        if begin is None:
            continue
        by_unit.setdefault(str(unit).strip(), []).append(
            (str(kind or "비가동").strip(), begin, _day(end))
        )
    notes: list[str] = []
    for month, process, unit, lost_days in zip(
        units[MONTH],
        units["공정"],
        units[EQUIPMENT_ID_COLUMN],
        units["손실 기여일수"],
        strict=True,
    ):
        cut = days.get(str(process))
        entries = by_unit.get(str(unit).strip(), [])
        if cut is None or not entries:
            notes.append("")
            continue
        window = wd_window(int(month), cut)
        lost = bool(pd.notna(lost_days) and int(lost_days) > 0)
        parts = [
            f"{kind} {begin:%m.%d}~" + (f"{end:%m.%d}" if end is not None else "계속")
            for kind, begin, end in sorted(entries, key=lambda item: item[1])
            if begin < window.boundary_end
            and (
                end is None
                or end > window.boundary_start
                or (lost and end == window.boundary_start)
            )
        ]
        notes.append(", ".join(parts))
    return notes


def _day(value: object) -> date | None:
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, float) and value != value:
        return None
    try:
        return pd.Timestamp(str(value)).date()
    except (TypeError, ValueError):
        return None


def _empty_breakdown() -> pd.DataFrame:
    return pd.DataFrame(
        {
            MONTH: pd.Series(dtype="int64"),
            "공정": pd.Series(dtype="string"),
            "구분": pd.Series(dtype="object"),
            EQUIPMENT_ID_COLUMN: pd.Series(dtype="string"),
            "설비키": pd.Series(dtype="string"),
            "기존보유분류": pd.Series(dtype="string"),
            "환산비": pd.Series(dtype="float64"),
            "구간일수": pd.Series(dtype="int64"),
            "비가동 없음 기여일수": pd.Series(dtype="Int64"),
            "손실 기여일수": pd.Series(dtype="Int64"),
            "실제 기여일수": pd.Series(dtype="Int64"),
            "보유": pd.Series(dtype="float64"),
            BREAKDOWN_LENT_COLUMN: pd.Series(dtype="float64"),
            "가용": pd.Series(dtype="float64"),
            "비가동 내역": pd.Series(dtype="object"),
        }
    )
