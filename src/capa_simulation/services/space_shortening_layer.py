# Purpose: Space 「필요 단축」 보기의 단축 호기를 층·Main 설비 묶음에 붙여 구간·배지·대수를 정한다.

"""Space 현황 색 기준 「필요 단축」(2026-10-24 사용자 결정 — 시안 승인, L1~L8 권장대로).

숫자는 모두 필요 단축 일정 화면과 같은 계획(`services/required_shortening.ShorteningPlan`)에서
나온다 — 이 모듈은 계획을 **고르고 붙이기만** 한다(Streamlit·DB·색을 모른다). 색 값은 화면 몫
(`components/space_layout`·`design/tokens`)이고 여기는 구간 이름(`s`·`m`·`l`·`x`)만 정한다.

- **대상** — 고른 목표 계획(`ShorteningPlan.at`)의 `구분 == 단축` 호기. `구분 == 신규`(추가N)는
  칠하지 않고 「도면에 자리가 없는 호기」 목록에만 든다. 호기는 계획 `호기`(Main 설비가 있으면 Main
  설비 — `equipment_units.unit_keys` 와 같은 규칙)라 모듈 묶음은 한 대·배지 하나다.
- **구간** — 남은 날 `left = 목표 Qual − 오늘`(오늘은 계획의 `plan.today` — 필요 단축 일정과 같은
  값)이 0 보다 작으면 기한 지남(`x`), 아니면 단축 일수 15일 이상 `l`·8일 이상 `m`·그 밖 `s`. 같은 날
  낸 계획은 목표 Qual 을 오늘 아래로 당기지 않아 기한 지남 호기는 구조상 나오지 않는다(결정 D1) —
  분류는 방어로 두고, 실제로 「때를 놓친」 공정·월(`STATUS_EXPIRED`·`STATUS_NEW_LIMIT`)은 「기한
  지남 달」로 따로 센다.
- **임박** — `0 ≤ left ≤ 임박 날수`(필요 단축 일정 「기한 임박」 과 같은 셈 — 결정 D9).
- **층** — 단축 호기의 층은 그리는 상태 행의 동·층이다(설비키 칸 「설비키」 — 설비 시나리오의 호기
  키 `unit_key` 와는 다른 칸이다). 좌표가 없어 그리지 못한 단축 호기는 그 동·층의 「자리 없음」
  이다. 추가N 은 그 공정 호기가 **그려진** 층마다 보이고(결정 D8) FAB 합계는 한 번 센다. 비활성 층은
  층 대수를 싣지 않고 추가N 도 붙이지 않는다(층 사용 0029 규칙).
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final

import pandas as pd

from capa_simulation.services.equipment_contract import EQUIPMENT_ID_COLUMN
from capa_simulation.services.equipment_units import UNIT_KEY_COLUMN, unit_keys
from capa_simulation.services.fab_layout import FLOOR_KEYS
from capa_simulation.services.floor_layout_profile import FloorKey
from capa_simulation.services.required_shortening import (
    KIND_NEW,
    KIND_SHORTENED,
    STATUS_EXPIRED,
    STATUS_NEW_LIMIT,
    LevelPlan,
    ShorteningPlan,
    unit_number,
)

__all__ = [
    "BUCKETS",
    "BUCKET_EXPIRED",
    "BUCKET_LABELS",
    "BUCKET_LARGE",
    "BUCKET_MEDIUM",
    "BUCKET_SMALL",
    "LARGE_FROM",
    "MEDIUM_FROM",
    "FabSummary",
    "FloorCount",
    "FloorLayer",
    "ShorteningLayer",
    "ShorteningMark",
    "VirtualUnit",
    "bucket_of",
    "build_shortening_layer",
    "day_text",
    "fab_floor_counts",
    "fab_layer_summary",
    "floor_layer",
    "floor_short_line",
    "shortening_space_floors",
]

BUCKET_SMALL: Final = "s"
BUCKET_MEDIUM: Final = "m"
BUCKET_LARGE: Final = "l"
BUCKET_EXPIRED: Final = "x"
BUCKETS: Final = (BUCKET_SMALL, BUCKET_MEDIUM, BUCKET_LARGE, BUCKET_EXPIRED)
BUCKET_LABELS: Final[Mapping[str, str]] = {
    BUCKET_SMALL: "1–7일",
    BUCKET_MEDIUM: "8–14일",
    BUCKET_LARGE: "15일 이상",
    BUCKET_EXPIRED: "기한 지남",
}
MEDIUM_FROM: Final = 8
LARGE_FROM: Final = 15

_PROCESS_COLUMN: Final = "공정소분류"
_LAYOUT_FLAG_COLUMN: Final = "레이아웃표시"
_BOX_COLUMNS: Final = ("X좌표", "Y좌표", "Xsize", "Ysize")


def bucket_of(days: int, target: date, today: date) -> str:
    """단축 일수·목표 Qual·오늘로 구간 이름. 목표 Qual 이 오늘 앞이면 일수와 상관없이 기한 지남."""
    if (target - today).days < 0:
        return BUCKET_EXPIRED
    if days >= LARGE_FROM:
        return BUCKET_LARGE
    if days >= MEDIUM_FROM:
        return BUCKET_MEDIUM
    return BUCKET_SMALL


def day_text(left: int) -> str:
    """배지 아랫줄 — 「기한 지남」·「오늘」·「D-5」."""
    if left < 0:
        return "기한 지남"
    if left == 0:
        return "오늘"
    return f"D-{left}"


def _month_text(month: int | None) -> str:
    return "" if month is None else f"{month // 100}-{month % 100:02d}"


@dataclass(frozen=True)
class ShorteningMark:
    """단축 호기 하나(모듈 묶음은 Main 설비 하나). `unit` 은 계획 `호기` 다."""

    unit: str
    process: str
    days: int
    original_qual: date
    target_qual: date
    month: int | None
    contributes: str
    modules: int
    manager: str | None
    model: str | None
    left: int
    bucket: str
    imminent: bool

    @property
    def main_text(self) -> str:
        """배지 윗줄 「−12일」."""
        return f"−{self.days}일"

    @property
    def sub_text(self) -> str:
        """배지 아랫줄 「D-5」·「오늘」·「기한 지남」."""
        return day_text(self.left)

    @property
    def tip(self) -> str:
        """배지 풍선 「APW02 · 기존 Qual 2026-11-11 → 목표 2026-11-04 · 대상 월 2026-11」."""
        month = f" · 대상 월 {_month_text(self.month)}" if self.month is not None else ""
        return (
            f"{self.unit} · 기존 Qual {self.original_qual.isoformat()} → 목표 "
            f"{self.target_qual.isoformat()}{month}"
        )

    @property
    def order(self) -> tuple[int, int, int, int, str]:
        """목록 차례 — 기한 지남 먼저 → 남은 날 짧은 순 → 호기 번호 → 이름."""
        number = unit_number(self.unit)
        return (
            0 if self.left < 0 else 1,
            self.left,
            0 if number is not None else 1,
            number or 0,
            self.unit,
        )


@dataclass(frozen=True)
class VirtualUnit:
    """계획의 가상 호기(추가N) 하나 — 기존 호기를 다 당겨도 모자라 새로 들여야 하는 대수."""

    name: str
    process: str
    target_qual: date
    month: int | None
    left: int


@dataclass(frozen=True)
class ShorteningLayer:
    """고른 목표 하나의 보기 재료. `marks` 의 키는 계획 `호기` 다."""

    level: float
    today: date
    months: tuple[int, ...]
    processes: tuple[str, ...]
    marks: Mapping[str, ShorteningMark]
    virtuals: tuple[VirtualUnit, ...]
    expired_months: Mapping[str, tuple[int, ...]]
    unmatched: int
    imminent_days: int

    def marks_in(self, processes: Collection[str] | None) -> list[ShorteningMark]:
        """고른 공정(없으면 모두)의 표시 — 목록 차례."""
        chosen = None if processes is None else set(processes)
        return sorted(
            (mark for mark in self.marks.values() if chosen is None or mark.process in chosen),
            key=lambda mark: mark.order,
        )


def _as_date(value: object) -> date | None:
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _as_int(value: object) -> int | None:
    if value is None or value is pd.NA:
        return None
    try:
        number = float(str(value))
    except ValueError:
        return None
    return None if math.isnan(number) else int(number)


def _text(value: object) -> str | None:
    if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _master_by_unit(unit_master: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if unit_master.empty or "호기" not in unit_master.columns:
        return {}
    records: dict[str, dict[str, Any]] = {}
    for record in unit_master.to_dict("records"):
        records.setdefault(str(record["호기"]), {str(key): value for key, value in record.items()})
    return records


def _expired_months(level_plan: LevelPlan) -> dict[str, tuple[int, ...]]:
    frame = level_plan.process_months
    if frame.empty or "상태" not in frame.columns:
        return {}
    late = frame.loc[frame["상태"].isin((STATUS_EXPIRED, STATUS_NEW_LIMIT))]
    months: dict[str, list[int]] = {}
    for process, month in zip(late["공정"], late["생산계획년월"], strict=True):
        months.setdefault(str(process), []).append(int(month))
    return {process: tuple(sorted(values)) for process, values in months.items()}


def build_shortening_layer(
    plan: ShorteningPlan, level: float, *, today: date, imminent_days: int
) -> ShorteningLayer:
    """계획과 고른 목표로 보기 재료를 만든다. `today` 는 계획의 오늘(`plan.today`)을 넘긴다."""
    level_plan = plan.at(level)
    master = _master_by_unit(plan.unit_master)
    marks: dict[str, ShorteningMark] = {}
    virtuals: list[VirtualUnit] = []
    units = level_plan.units
    for record in units.to_dict("records") if not units.empty else ():
        target = _as_date(record["목표 Qual"])
        if target is None:
            continue
        unit = str(record["호기"])
        process = str(record["공정"])
        left = (target - today).days
        month = _as_int(record["대상 월"])
        if record["구분"] == KIND_NEW:
            virtuals.append(VirtualUnit(unit, process, target, month, left))
            continue
        if record["구분"] != KIND_SHORTENED or unit in marks:
            continue
        original = _as_date(record["기존 Qual"])
        days = _as_int(record["단축일수"])
        if original is None or days is None:
            continue
        attributes = master.get(unit, {})
        modules = _as_int(attributes.get("모듈 수")) or _as_int(record["모듈 수"]) or 1
        marks[unit] = ShorteningMark(
            unit=unit,
            process=process,
            days=days,
            original_qual=original,
            target_qual=target,
            month=month,
            contributes=_text(record["해소 기여 월"]) or "",
            modules=modules,
            manager=_text(attributes.get("담당자")),
            model=_text(attributes.get("Model")),
            left=left,
            bucket=bucket_of(days, target, today),
            imminent=0 <= left <= imminent_days,
        )
    return ShorteningLayer(
        level=float(level),
        today=today,
        months=tuple(plan.months),
        processes=tuple(plan.processes),
        marks=marks,
        virtuals=tuple(virtuals),
        expired_months=_expired_months(level_plan),
        unmatched=len(plan.required_only) + len(plan.availability_only),
        imminent_days=int(imminent_days),
    )


# ------------------------------------------------------------------ 행 → 설비키·층


def _row_keys(rows: pd.DataFrame) -> pd.Series:
    """행마다 설비키. 상태 표에 이미 있는 「설비키」 칸을 먼저 읽는다."""
    if UNIT_KEY_COLUMN in rows.columns:
        keys = rows[UNIT_KEY_COLUMN].astype("string").str.strip()
        return keys.where(keys.notna() & keys.ne(""), unit_keys(rows))
    return unit_keys(rows)


def _row_floor(building: object, floor: object) -> FloorKey | None:
    if not isinstance(building, str) or not isinstance(floor, str):
        return None
    key = (building, floor)
    return key if key in FLOOR_KEYS else None


def _key_floors(rows: pd.DataFrame) -> dict[str, FloorKey]:
    """설비키 → 그 행의 층(처음 나온 FAB 층)."""
    if rows.empty:
        return {}
    floors: dict[str, FloorKey] = {}
    for key, building, floor in zip(_row_keys(rows), rows["동"], rows["층"], strict=True):
        if pd.isna(key):
            continue
        spot = _row_floor(building, floor)
        if spot is not None:
            floors.setdefault(str(key), spot)
    return floors


def _process_floors(rows: pd.DataFrame) -> dict[str, set[FloorKey]]:
    """공정 → 그 공정 호기가 그려진 층."""
    out: dict[str, set[FloorKey]] = {}
    if rows.empty or _PROCESS_COLUMN not in rows.columns:
        return out
    for process, building, floor in zip(rows[_PROCESS_COLUMN], rows["동"], rows["층"], strict=True):
        spot = _row_floor(building, floor)
        if spot is not None and not pd.isna(process):
            out.setdefault(str(process), set()).add(spot)
    return out


# ------------------------------------------------------------------ 층 상세


@dataclass(frozen=True)
class FloorLayer:
    """층 상세 보기 하나의 재료.

    `looks` 는 설비명 → `{"layer": 구간, "dim": bool}`(표시된 호기) 또는 `{"dim": True}`(흐릴
    호기)다 — 값이 없는 호기는 싣지 않는다. `badges` 는 설비키마다 하나(그 층에 그린 모듈 전부가
    `ids`), `rows` 는 「이 층에서 단축할 호기」 줄(`pick_ids` 가 같은 차례의 그 설비 이 층 첫 모듈
    설비명), `chips` 는 이 층에 그린 공정 → 칩 글, `unplaced` 는 이 층 동·층인데 좌표가 없는 단축
    호기, `virtuals` 는 이 층에 그린 공정의 추가N, `counts` 는 구간 → 대수(목록 줄과 같은 축)다.
    """

    looks: dict[str, dict[str, Any]] = field(default_factory=dict)
    badges: list[dict[str, Any]] = field(default_factory=list)
    rows: list[ShorteningMark] = field(default_factory=list)
    pick_ids: list[str] = field(default_factory=list)
    chips: dict[str, str] = field(default_factory=dict)
    unplaced: tuple[ShorteningMark, ...] = ()
    virtuals: tuple[VirtualUnit, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    elsewhere: int = 0

    @property
    def max_days(self) -> int:
        return max((mark.days for mark in (*self.rows, *self.unplaced)), default=0)


def _chip_text(process: str, marks: Sequence[ShorteningMark], virtual: int, late: int) -> str:
    parts = [process]
    if marks:
        parts.append(f"{len(marks)}대 최대 −{max(mark.days for mark in marks)}일")
    if virtual:
        parts.append(f"추가 {virtual}")
    if late:
        parts.append(f"기한 지남 달 {late}")
    if not marks and not virtual:
        parts.append("단축 없음")
    return " · ".join(parts)


def floor_layer(
    layer: ShorteningLayer,
    rows: pd.DataFrame,
    unplaced_rows: pd.DataFrame,
    *,
    focus: str | None,
    dim_others: bool,
) -> FloorLayer:
    """층 상세의 표시. `rows` 는 뷰어에 보내는 그 층 행, `unplaced_rows` 는 그 층 동·층의 좌표 없는
    행.

    `focus` 는 공정 칩에서 고른 공정(없으면 모든 공정)이다 — 다른 공정의 호기·배지를 흐리고
    목록·자리 없음·추가N 을 그 공정만으로 좁힌다. `dim_others` 면 표시 없는 호기를 흐린다.
    """
    if rows.empty:
        names = pd.Series(dtype="string")
        keys = pd.Series(dtype="string")
        processes = pd.Series(dtype="string")
    else:
        names = rows[EQUIPMENT_ID_COLUMN].astype("string").str.strip()
        keys = _row_keys(rows)
        processes = (
            rows[_PROCESS_COLUMN].astype("string").str.strip()
            if _PROCESS_COLUMN in rows.columns
            else pd.Series(pd.NA, index=rows.index, dtype="string")
        )
    looks: dict[str, dict[str, Any]] = {}
    ids_by_key: dict[str, list[str]] = {}
    drawn_processes: dict[str, None] = {}
    for name, key, process in zip(names, keys, processes, strict=True):
        if pd.isna(name):
            continue
        if not pd.isna(process):
            drawn_processes.setdefault(str(process), None)
        mark = layer.marks.get(str(key)) if not pd.isna(key) else None
        other = focus is not None and (pd.isna(process) or str(process) != focus)
        if mark is not None:
            looks[str(name)] = {"layer": mark.bucket, "dim": bool(other)}
            ids_by_key.setdefault(mark.unit, []).append(str(name))
        elif dim_others or other:
            looks[str(name)] = {"dim": True}
    drawn = sorted((layer.marks[key] for key in ids_by_key), key=lambda mark: mark.order)
    badges = [
        {
            "key": mark.unit,
            "ids": ids_by_key[mark.unit],
            "main": mark.main_text,
            "sub": mark.sub_text,
            "bucket": mark.bucket,
            "imminent": mark.imminent,
            "dim": focus is not None and mark.process != focus,
            "tip": mark.tip,
            "aria": f"{mark.unit} {mark.main_text} {mark.sub_text} — 누르면 상세",
        }
        for mark in drawn
    ]
    unplaced_keys = set(_key_floors(unplaced_rows)) - set(ids_by_key)
    unplaced = sorted(
        (layer.marks[key] for key in unplaced_keys if key in layer.marks),
        key=lambda mark: mark.order,
    )
    floor_virtuals = [unit for unit in layer.virtuals if unit.process in drawn_processes]
    chips = {
        process: _chip_text(
            process,
            [mark for mark in (*drawn, *unplaced) if mark.process == process],
            sum(1 for unit in floor_virtuals if unit.process == process),
            len(layer.expired_months.get(process, ())),
        )
        for process in sorted(drawn_processes)
    }

    def keep(process: str) -> bool:
        return focus is None or process == focus

    listed = [mark for mark in drawn if keep(mark.process)]
    here = {mark.unit for mark in (*drawn, *unplaced)}
    elsewhere = (
        sum(1 for mark in layer.marks.values() if mark.process == focus and mark.unit not in here)
        if focus is not None
        else 0
    )
    counts: dict[str, int] = {}
    for mark in listed:
        counts[mark.bucket] = counts.get(mark.bucket, 0) + 1
    return FloorLayer(
        looks=looks,
        badges=badges,
        rows=listed,
        pick_ids=[ids_by_key[mark.unit][0] for mark in listed],
        chips=chips,
        unplaced=tuple(mark for mark in unplaced if keep(mark.process)),
        virtuals=tuple(unit for unit in floor_virtuals if keep(unit.process)),
        counts=counts,
        elsewhere=elsewhere,
    )


# ------------------------------------------------------------------ FAB 전체


@dataclass(frozen=True)
class FloorCount:
    """FAB 층 하나의 단축 대수 — 블록 셋째 줄·층 목록 표 칸 넷."""

    units: int = 0
    max_days: int = 0
    expired: int = 0
    virtual: int = 0
    unplaced: int = 0


def _in_scope(process: str, processes: Collection[str] | None) -> bool:
    return processes is None or not processes or process in processes


def fab_floor_counts(
    layer: ShorteningLayer,
    counted: pd.DataFrame,
    unplaced: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    inactive: Collection[FloorKey] = (),
) -> dict[FloorKey, FloorCount]:
    """층마다 단축 대수. `counted` 는 세는 배치 행, `unplaced` 는 레이아웃표시 Y 인데 좌표가 없는
    행이다.

    단축 호기는 그 설비키가 그려진 층(없으면 좌표 없는 행의 동·층)에 한 번 든다. 추가N 은 그 공정
    호기가 그려진 층마다 든다(결정 D8). 비활성 층은 싣지 않는다 — 층 대수를 보이지 않고 추가N 도
    붙이지 않는다. `processes` 는 Space 공정소분류 필터다(비면 모두).
    """
    drawn = _key_floors(counted)
    loose = _key_floors(unplaced)
    blocked = set(inactive)
    tallies: dict[FloorKey, dict[str, int]] = {}
    for mark in layer.marks.values():
        if not _in_scope(mark.process, processes):
            continue
        spot = drawn.get(mark.unit)
        is_loose = spot is None
        if spot is None:
            spot = loose.get(mark.unit)
        if spot is None or spot in blocked:
            continue
        tally = tallies.setdefault(
            spot, {"units": 0, "max": 0, "expired": 0, "virtual": 0, "loose": 0}
        )
        tally["units"] += 1
        tally["max"] = max(tally["max"], mark.days)
        tally["expired"] += int(mark.bucket == BUCKET_EXPIRED)
        tally["loose"] += int(is_loose)
    by_process = _process_floors(counted)
    for unit in layer.virtuals:
        if not _in_scope(unit.process, processes):
            continue
        for spot in by_process.get(unit.process, set()) - blocked:
            tally = tallies.setdefault(
                spot, {"units": 0, "max": 0, "expired": 0, "virtual": 0, "loose": 0}
            )
            tally["virtual"] += 1
    return {
        key: FloorCount(
            units=tally["units"],
            max_days=tally["max"],
            expired=tally["expired"],
            virtual=tally["virtual"],
            unplaced=tally["loose"],
        )
        for key, tally in sorted(tallies.items(), key=lambda item: FLOOR_KEYS.index(item[0]))
    }


def floor_short_line(count: FloorCount | None) -> str | None:
    """FAB 층 블록 셋째 줄 「단축 3대 · 최대 −18일 · 지남 1 · 추가 2」. 대수가 없으면 None(빈 줄
    없음)."""
    if count is None or (count.units == 0 and count.virtual == 0):
        return None
    parts = []
    if count.units:
        parts.append(f"단축 {count.units}대 · 최대 −{count.max_days}일")
    if count.expired:
        parts.append(f"지남 {count.expired}")
    if count.virtual:
        parts.append(f"추가 {count.virtual}")
    return " · ".join(parts)


@dataclass(frozen=True)
class FabSummary:
    """FAB 도면 아래 요약 한 줄의 수."""

    total: int
    drawn: int
    unplaced: int
    max_days: int
    expired: int
    virtual: int
    filtered_out: int
    expired_months: int
    inactive: int


def fab_layer_summary(
    layer: ShorteningLayer,
    counted: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    inactive: Collection[FloorKey] = (),
) -> FabSummary:
    """FAB 요약 — 합계는 모든 층이다(추가N 은 한 번). 도면에 그린 설비키가 아니면 「자리 없음」
    이고, 비활성 층에 그린 것은 `inactive` 로 따로 센다. 공정소분류 필터 밖은 세지 않고
    `filtered_out` 이다."""
    drawn = _key_floors(counted)
    blocked = set(inactive)
    scoped = [mark for mark in layer.marks.values() if _in_scope(mark.process, processes)]
    on_floor = [mark for mark in scoped if mark.unit in drawn]
    return FabSummary(
        total=len(scoped),
        drawn=len(on_floor),
        unplaced=len(scoped) - len(on_floor),
        max_days=max((mark.days for mark in scoped), default=0),
        expired=sum(1 for mark in scoped if mark.bucket == BUCKET_EXPIRED),
        virtual=sum(1 for unit in layer.virtuals if _in_scope(unit.process, processes)),
        filtered_out=len(layer.marks) - len(scoped),
        expired_months=sum(
            len(months)
            for process, months in layer.expired_months.items()
            if _in_scope(process, processes)
        ),
        inactive=sum(1 for mark in on_floor if drawn[mark.unit] in blocked),
    )


# ------------------------------------------------------------------ 필요 단축 일정 → Space 층


def _drawn_master(equipment: pd.DataFrame) -> pd.DataFrame:
    """설비 마스터에서 도면에 그려지는 행 — 레이아웃표시 Y · 좌표·크기 있음 · FAB 층."""
    needed = {_LAYOUT_FLAG_COLUMN, "동", "층", _PROCESS_COLUMN, *_BOX_COLUMNS}
    if equipment.empty or not needed <= set(equipment.columns):
        return equipment.iloc[0:0]
    flagged = equipment[_LAYOUT_FLAG_COLUMN].astype("string").str.strip().eq("Y").fillna(False)
    boxed = equipment[list(_BOX_COLUMNS)].notna().all(axis=1)
    return equipment.loc[flagged.astype(bool) & boxed]


def shortening_space_floors(
    level_plan: LevelPlan,
    unit_master: pd.DataFrame,
    equipment: pd.DataFrame,
    *,
    inactive: Collection[FloorKey] = (),
) -> dict[str, FloorKey]:
    """공정마다 「도면에서 보기」 가 열 층 — 공정 전부를 한 번에(카드마다 다시 세지 않는다).

    그 목표의 단축 호기 동·층(`unit_master`)이 가장 많은 사용 층(같으면 `FLOOR_KEYS` 차례). 단축
    호기가 없고 추가N 만이면 설비 마스터에서 그 공정 설비키가 **그려지는** 수가 가장 많은 사용
    층이다(좌표 없는 호기는 세지 않는다 — 모듈 넷은 한 대). 비활성 층과 FAB 밖 층은 버린다 — 고를
    층이 없으면 표에 없다.
    """
    blocked = set(inactive)
    master = _master_by_unit(unit_master)
    shortened: dict[str, dict[FloorKey, int]] = {}
    virtual_only: set[str] = set()
    units = level_plan.units
    for record in units.to_dict("records") if not units.empty else ():
        process = str(record["공정"])
        if record["구분"] == KIND_NEW:
            virtual_only.add(process)
            continue
        if record["구분"] != KIND_SHORTENED:
            continue
        attributes = master.get(str(record["호기"]), {})
        spot = _row_floor(attributes.get("동"), attributes.get("층"))
        tally = shortened.setdefault(process, {})
        if spot is not None and spot not in blocked:
            tally[spot] = tally.get(spot, 0) + 1
    floors: dict[str, FloorKey] = {}
    for process, tally in shortened.items():
        if tally:
            floors[process] = _most(tally)
    wanted = {process for process in virtual_only if process not in floors}
    if wanted:
        drawn = _drawn_master(equipment)
        drawn = drawn.loc[drawn[_PROCESS_COLUMN].astype("string").str.strip().isin(wanted)]
        keys = _row_keys(drawn) if not drawn.empty else pd.Series(dtype="string")
        per: dict[str, dict[FloorKey, set[str]]] = {}
        for process, key, building, floor in zip(
            drawn[_PROCESS_COLUMN] if not drawn.empty else (),
            keys,
            drawn["동"] if not drawn.empty else (),
            drawn["층"] if not drawn.empty else (),
            strict=True,
        ):
            spot = _row_floor(building, floor)
            if spot is None or spot in blocked or pd.isna(key):
                continue
            per.setdefault(str(process).strip(), {}).setdefault(spot, set()).add(str(key))
        for process, by_floor in per.items():
            floors[process] = _most({spot: len(found) for spot, found in by_floor.items()})
    return floors


def _most(tally: Mapping[FloorKey, int]) -> FloorKey:
    return min(tally, key=lambda spot: (-tally[spot], FLOOR_KEYS.index(spot)))
