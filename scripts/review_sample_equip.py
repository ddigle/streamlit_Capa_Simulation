# Purpose: 검수용 합성 설비 DB 를 시뮬레이션 DB 의 최신 공식 소요·가용에서 앱 저장 API 로만 만든다.

"""검수용 합성 샘플 2단계 — 설비 DB(`equipment_availability.duckdb`).

보통은 입구 `generate_review_sample.py` 가 1단계 뒤에 부른다. 혼자 돌릴 때는

    .venv/bin/python scripts/review_sample_equip.py --out <뿌리>/data --replace

`--out` 은 데이터 폴더(그 안에 equipment_availability.duckdb) 또는 .duckdb 경로, `--sim` 의
기본값은 같은 폴더의 capa_simulation.duckdb 다.

**읽는 것.** 시뮬레이션 DB 는 **사본으로만** 연다(임시 폴더에 복사한 뒤 읽는다 — 원본은 바이트도
바뀌지 않는다). 최신 공식버전의 소요대수(`full_capacity_outcome` — 제약 시뮬레이션·필요 단축
일정과 같은 길), `RQ_EQP_AVBL`(공식 가용), 판정 기준(Preference 공용 프로필)을 읽는다.

**만드는 것.** 공정마다 26.11 공식 가용만큼의 기존 fleet 과, 공식 가용이 오르는 달마다 Qual 이 그
달 W/D 첫날 1~9일 전인 신규 호기(설비 일정 기준 가용 ≈ 공식 가용)를 짜고, 이야기의 어긋남(Ball
Attach 지연·Wafer Saw 기한 지남·TC Bonding 2대 부족·DAF Attach 앞섬·Pre B/D 개발대여·Mold
공사)과 상태 표본(정지·반출/이설·보관·일정 미정·환산비·사용기준·모듈 묶음·비가동)을 얹는다. 모두
`DuckDBEquipmentRepository` 공개 메서드다(SQL 쓰기 없음).

**지키는 것.** 산출 파일이 git 작업 트리 안이면 멈춘다. 산출 DB 가 이미 있으면 `--replace` 일 때만
그 파일(과 `.wal`)을 지운다. 모든 값은 합성이다 — `DEMO-` 설비명·`DEMO-MAKER-x`·`DEMO 담당 x`.
끝에 점검을 찍고 하나라도 어긋나면 종료 코드 1 이다. 점검·추천 조합은 데이터 폴더의 부모에
`build-log-equip.txt` 로 남긴다.
"""

from __future__ import annotations

import argparse
import logging
import math
import shutil
import sys
import tempfile
import warnings
import zlib
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

import pandas as pd

# 실행 문맥 밖에서 캐시 래퍼 모듈을 읽으면 「No runtime found」 경고가 줄줄이 찍힌다 — 계산과
# 무관하다.
_LOGGING_DISABLED = logging.root.manager.disable
logging.disable(max(_LOGGING_DISABLED, logging.WARNING))

import review_sample_story as story  # noqa: E402

from capa_simulation.persistence.equipment_repository import (  # noqa: E402
    EMPTY_REVISION_TOKEN,
    DuckDBEquipmentRepository,
    EquipmentSaveRequest,
    EquipmentScenarioSummary,
    EquipmentSnapshot,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository  # noqa: E402
from capa_simulation.services.constraint_simulation import (  # noqa: E402
    ConstraintConditions,
    ConstraintResult,
    constraint_month_inputs,
    simulate_constraint,
)
from capa_simulation.services.equipment_availability import (  # noqa: E402
    build_space_equipment_status,
)
from capa_simulation.services.equipment_contract import (  # noqa: E402
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
)
from capa_simulation.services.iso_week_calendar import owning_month, weeknum_label  # noqa: E402
from capa_simulation.services.manual_downtime import manual_downtime_key  # noqa: E402
from capa_simulation.services.process_capa_detail import build_process_product_demand  # noqa: E402
from capa_simulation.services.process_equipment_timeline import (  # noqa: E402
    MISSING_CUTOFF,
    NO_COUNTED_UNITS,
    READY,
    dynamic_readiness,
)
from capa_simulation.services.required_shortening import (  # noqa: E402
    KIND_NEW,
    STATUS_EXPIRED,
    STATUS_MET,
    ShorteningPlan,
    plan_required_shortening,
)
from capa_simulation.services.schedule_confirmation import (  # noqa: E402
    MISSING_ACTUAL,
    STATUS_UPDATE_NEEDED,
    UNCONFIRMED,
    confirmation_counts,
    flagged_equipment,
    schedule_confirmation_issues,
    schedule_confirmation_notice,
)
from capa_simulation.services.securement_threshold import SecurementThresholds  # noqa: E402
from capa_simulation.services.shortening_baseline import (  # noqa: E402
    BaselineProvenance,
    freeze_plan,
)
from capa_simulation.services.simulation_cache import full_capacity_outcome  # noqa: E402
from capa_simulation.services.space_layout_edit import (  # noqa: E402
    layout_warnings,
    overlap_counts_touching,
)
from capa_simulation.services.wd_window import wd_window  # noqa: E402

logging.disable(_LOGGING_DISABLED)

TODAY = date(2026, 11, 2)
AS_OF = {"r1": date(2026, 10, 13), "r2": date(2026, 10, 20), "r3": TODAY}
REV_ORDER = {"r1": 1, "r2": 2, "r3": 3}
FIRST_MONTH = 202611
LAST_MONTH = 202812
SAVED_BY = "DEMO 설비담당"
SOURCE = "DEMO 정기 검토"
LOG_NAME = "build-log-equip.txt"
LOG_BEGIN = "===== review_sample_equip (설비 DB) ====="
LOG_END = "===== /review_sample_equip ====="

# ------------------------------------------------------------------ 공정 표


@dataclass(frozen=True)
class ProcessMeta:
    name: str
    abbr: str
    large: str
    line: str
    building: str
    floor: str
    cutoff: float | None


PROCESS_META: tuple[ProcessMeta, ...] = (
    ProcessMeta("Wafer Incoming Inspection", "WII", "FRONT", "FRONT", "C1", "1F", 7),
    ProcessMeta("Wafer Saw", "WSW", "FRONT", "FRONT", "C1", "1F", 30),
    ProcessMeta("Wafer Sorter", "WST", "FRONT", "FRONT", "C1", "1F", 10),
    ProcessMeta("Laser Grooving", "LGV", "FRONT", "FRONT", "C1", "2F", 8),
    ProcessMeta("Wafer Grinding", "WGD", "FRONT", "FRONT", "C1", "2F", 14),
    ProcessMeta("Pre B/D", "PBD", "BOND", "PKG", "C1", "2F", 5),
    ProcessMeta("Plasma Clean", "PLC", "BOND", "FDY", "C1", "3F", 6),
    ProcessMeta("DAF Attach", "DAF", "BOND", "PKG", "C1", "3F", 18),
    ProcessMeta("TC Bonding", "TCB", "BOND", "PKG", "C2", "2F", 35.8),
    ProcessMeta("Mass Reflow", "MRF", "BOND", "PKG", "C2", "2F", 9),
    ProcessMeta("Underfill", "UF", "MOLD", "PKG", "C2", "3F", 15),
    ProcessMeta("Mold", "MLD", "MOLD", "PKG", "C2", "3F", 12.5),
    ProcessMeta("Post Mold Cure", "PMC", "MOLD", "PKG", "C2", "3F", 5),
    ProcessMeta("Ball Attach", "BA", "MOLD", "PKG", "C3", "1F", 16),
    ProcessMeta("Singulation", "SGL", "TEST", "MI", "C3", "1F", 11),
    ProcessMeta("Laser Marking", "LMK", "TEST", "MI", "C3", "1F", 5),
    ProcessMeta("X-Ray", "XR", "TEST", "MI", "C3", "1F", 7),
    ProcessMeta("Acoustic Delamination Inspection", "SAM", "TEST", "MI", "C3", "2F", 9),
    ProcessMeta("Burn-In", "BI", "TEST", "TEST", "C3", "2F", 25),
    ProcessMeta("Final Test", "FT", "TEST", "TEST", "C4", "2F", 28),
    ProcessMeta("AVI", "AVI", "TEST", "TEST", "C4", "2F", 20.8),
    ProcessMeta("Tape Pocket Inspection", "TPI", "TEST", "MI", "C4", "2F", 6),
    ProcessMeta("Packing", "PK", "LOGI", "물류", "C4", "3F", 5),
    # Cut-off 를 적지 않는 공정(「Cut-off 미기재」 갈래).
    ProcessMeta("Shipping Inspection", "SHI", "LOGI", "물류", "C4", "3F", None),
)


def _with_story(metas: tuple[ProcessMeta, ...]) -> tuple[ProcessMeta, ...]:
    """시뮬레이션 생성기와 같은 약어·공정대분류·공정구분·층(`review_sample_story`)을 입힌다.
    Cut-off 는 이 생성기의 값이다(이야기 상수에 없다)."""
    merged: list[ProcessMeta] = []
    for meta in metas:
        item = story.PROCESS_BY_NAME.get(meta.name)
        if item is None:
            merged.append(meta)
            continue
        merged.append(
            ProcessMeta(
                meta.name,
                item.abbreviation or meta.abbr,
                item.major or meta.large,
                item.space_group or meta.line,
                item.building or meta.building,
                item.floor_name or meta.floor,
                meta.cutoff,
            )
        )
    return tuple(merged)


PROCESS_META = _with_story(PROCESS_META)
META = {meta.name: meta for meta in PROCESS_META}
FLOOR_ORDER = (
    ("C1", "1F"),
    ("C1", "2F"),
    ("C1", "3F"),
    ("C2", "2F"),
    ("C2", "3F"),
    ("C3", "1F"),
    ("C3", "2F"),
    ("C4", "2F"),
    ("C4", "3F"),
)
FLOOR_TITLES = {
    ("C1", "1F"): "C1 1F · Wafer 입고·Saw",
    ("C1", "2F"): "C1 2F · Grinding·Pre B/D",
    ("C1", "3F"): "C1 3F · Plasma·DAF",
    ("C2", "2F"): "C2 2F · TC Bonding 라인",
    ("C2", "3F"): "C2 3F · Underfill·Mold",
    ("C3", "1F"): "C3 1F · Ball Attach·검사",
    ("C3", "2F"): "C3 2F · SAM·Burn-In",
    ("C4", "2F"): "C4 2F · Test·AVI",
    ("C4", "3F"): "C4 3F · Packing·출하",
}
CANVAS_DEFAULT = (160.0, 100.0)
CANVAS_BIG = {("C2", "2F"): (200.0, 120.0)}
DESIGN_CUTOFF = 10.0  # Cut-off 를 적지 않는 공정의 일정 설계용(저장하지 않는다)

# 이야기 상수(어긋남 · 쓰는 차례).
BALL_DELAY_MONTHS = (202701, 202702, 202703, 202704)
BALL_DELAY_DAYS = {"r1": 55, "r2": 55, "r3": 35}
BALL_PULLED_IN_R2 = 3
TCB_SHORT_FROM = 202802
TCB_SHORT_UNITS = 2
TCB_R1_DELAY_DAYS = 20
DAF_EARLY_MONTHS = (202708, 202709, 202710)
WAFER_SAW_LATE_QUAL = date(2026, 12, 20)
WAFER_SAW_LATE_EXISTING_QUAL = date(2026, 10, 20)
BASELINE_CLASS = "기존 (대장 외)"
# 필요 단축 일정 공용 조회 조건의 공정 12 — 이야기 공정 10 + 「앞달 단축으로 해소」 사례 공정 +
# Wafer Sorter (27.09 월별 기준 105 — 110% 목표로는 카드). 사례가 없으면 Burn-In.
SHORTENING_FILTER_BASE = (
    "Wafer Saw",
    "Pre B/D",
    "DAF Attach",
    "TC Bonding",
    "Underfill",
    "Mold",
    "Post Mold Cure",
    "Ball Attach",
    "Singulation",
    "AVI",
)
CARRIED_PREFERRED = (
    "Wafer Grinding",
    "Underfill",
    "Singulation",
    "Burn-In",
    "AVI",
    "Wafer Incoming Inspection",
)
FLOOR_STATES = {("C5", "1F"): "리모델링 공사(27.03 재가동)", ("C5", "6F"): "창고 전환"}


def hashed(text: str) -> int:
    return zlib.crc32(text.encode("utf-8"))


def add_months(month: int, delta: int) -> int:
    year, mon = divmod(month, 100)
    index = year * 12 + (mon - 1) + delta
    return (index // 12) * 100 + index % 12 + 1


def month_text(month: int) -> str:
    return f"{month // 100 % 100:02d}.{month % 100:02d}"


def pct(value: float | None) -> str:
    return (
        "—"
        if value is None or (isinstance(value, float) and math.isnan(value))
        else f"{value * 100:.1f}%"
    )


# ------------------------------------------------------------------ 시뮬레이션 DB 읽기


@dataclass(frozen=True)
class SimFacts:
    release_no: int
    release_name: str
    scenario_id: str
    scenario_name: str
    revision_id: str
    revision_no: int
    months: tuple[int, ...]
    processes: tuple[str, ...]
    available: dict[tuple[str, int], float]
    required: dict[tuple[str, int], float]
    required_rows: pd.DataFrame
    area: dict[str, str]
    thresholds: SecurementThresholds
    edp_processes: frozenset[str]
    products: tuple[str, ...]


def read_sim(copy_path: Path) -> SimFacts:
    repository = DuckDBScenarioRepository(copy_path)
    release = repository.latest_official_release()
    if release is None:
        raise LookupError("시뮬레이션 DB 에 공식버전이 없습니다.")
    snapshot = repository.load_revision(release.revision_id)
    outcome = full_capacity_outcome(snapshot.tables, snapshot.tables)
    if outcome.error is not None or outcome.required_equipment is None:
        raise ValueError(f"공식버전 소요대수를 계산하지 못했습니다 — {outcome.error}")
    rows = outcome.required_equipment
    month_values = pd.to_numeric(rows["생산계획년월"], errors="coerce")
    inside = rows.loc[month_values.between(FIRST_MONTH, LAST_MONTH).fillna(False).to_numpy()].copy()
    months = tuple(sorted({int(m) for m in pd.to_numeric(inside["생산계획년월"])}))
    required: dict[tuple[str, int], float] = defaultdict(float)
    grouped = inside.groupby(["공정", "생산계획년월"], as_index=False)["소요대수"].sum()
    for process, month, value in grouped[["공정", "생산계획년월", "소요대수"]].itertuples(
        index=False
    ):
        required[(str(process).strip(), int(month))] += float(value)
    avbl = snapshot.tables["RQ_EQP_AVBL"]
    available: dict[tuple[str, int], float] = {}
    for process, month, value in zip(
        avbl["공정"].astype("string").str.strip(),
        pd.to_numeric(avbl["생산계획년월"]),
        pd.to_numeric(avbl["가용대수"]),
        strict=True,
    ):
        if FIRST_MONTH <= int(month) <= LAST_MONTH:
            available[(str(process), int(month))] = float(value)
    processes_in = {p for p, _ in required} | {p for p, _ in available}
    ordered = [meta.name for meta in PROCESS_META if meta.name in processes_in]
    ordered += sorted(processes_in - set(ordered))
    area: dict[str, str] = {}
    counts = inside.groupby(["공정", "Area_Name"]).size().reset_index(name="n")
    for name, group in counts.groupby("공정"):
        area[str(name).strip()] = str(group.sort_values("n").iloc[-1]["Area_Name"])
    product_column = inside["제품정보"].astype("string").str.strip()
    edp = frozenset(
        str(p).strip()
        for p in inside.loc[
            product_column.eq("DEMO-E4").fillna(False).to_numpy()
            & (pd.to_numeric(inside["소요대수"]) > 0).to_numpy(),
            "공정",
        ]
    )
    totals = (
        pd.DataFrame(
            {"p": product_column.to_numpy(), "v": pd.to_numeric(inside["소요대수"]).to_numpy()}
        )
        .groupby("p")["v"]
        .sum()
        .sort_values(ascending=False)
    )
    return SimFacts(
        release_no=release.release_no,
        release_name=release.release_name,
        scenario_id=release.scenario_id,
        scenario_name=release.scenario_name,
        revision_id=release.revision_id,
        revision_no=release.revision_no,
        months=months,
        processes=tuple(ordered),
        available=available,
        required=dict(required),
        required_rows=inside,
        area=area,
        thresholds=repository.load_global_securement_threshold().thresholds,
        edp_processes=edp,
        products=tuple(str(p) for p in totals.index if str(p)),
    )


# ------------------------------------------------------------------ 호기 모델


@dataclass
class Unit:
    name: str
    process: str
    kind: str  # existing / new / extra
    month: int | None = None
    ratio: float = 1.0
    usage: str | None = "HBM"
    existing_flag: str = "N"
    storage: str = "N"
    layout_flag: str = "Y"
    placed: bool = True
    vib: date | None = None
    logi: date | None = None
    arrival: date | None = None
    qual: date | None = None
    stop: date | None = None
    relocation: date | None = None
    parent: str | None = None
    model: str = ""
    maker: str = ""
    invest: str = "양산"
    invest_capa: str | None = None
    area_code: str = "Main"
    manager: str = ""
    memo1: str | None = None
    memo2: str | None = None
    history: str | None = None
    equipment_history: str | None = None
    unit_history: str | None = None
    present_from: str = "r1"
    qual_by_rev: dict[str, date] = field(default_factory=dict)
    qual_status_by_rev: dict[str, str] = field(default_factory=dict)
    history_by_rev: dict[str, str] = field(default_factory=dict)
    scenario_memo_by_rev: dict[str, str] = field(default_factory=dict)
    place: tuple[str, str, float, float, float, float] | None = None
    cell: str | None = None  # 모듈 묶음이면 Main 설비(같은 칸)
    confirm: tuple[
        str, ...
    ] = ()  # 일정 확인 사례(r3 공통 대장의 실적·상태만 바꾼다 — CONFIRM_KINDS)

    def qual_at(self, rev: str) -> date | None:
        return self.qual_by_rev.get(rev, self.qual)

    def exit_day(self) -> date | None:
        days = [d for d in (self.stop, self.relocation) if d is not None]
        return min(days) if days else None

    def counted(self) -> bool:
        return self.storage == "N" and (self.usage or "").upper() in ("HBM", "EDP")

    def contributes(self, month: int, cutoff: float) -> float:
        """그 달 W/D 구간을 온전히 덮으면 환산비, 아니면 0(설계용 — 일할은 앱 계산이 한다)."""
        if not self.counted():
            return 0.0
        window = wd_window(month, cutoff)
        if self.existing_flag != "Y":
            if self.qual is None or self.arrival is None or self.qual > window.boundary_start:
                return 0.0
        exit_day = self.exit_day()
        if exit_day is not None and exit_day <= window.boundary_end:
            return 0.0
        return self.ratio


@dataclass
class Downtime:
    unit: str
    kind: str
    start: date
    end: date | None
    reason: str
    note: str | None
    from_rev: str = "r1"


@dataclass
class Fleet:
    units: list[Unit]
    baseline: list[dict[str, object]]
    downtime: list[Downtime]
    targets: dict[str, dict[int, float]]
    canvases: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    marks: dict[tuple[str, str], list[dict[str, object]]] = field(default_factory=dict)
    group_labels: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    free_cells: dict[tuple[str, str], list[tuple[float, float]]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    carried_process: str | None = None

    def filter_processes(self, available: Sequence[str]) -> list[str]:
        extra = [self.carried_process or "Burn-In", "Wafer Sorter"]
        chosen = [p for p in (*SHORTENING_FILTER_BASE, *extra) if p in available]
        return list(dict.fromkeys(chosen))


def design_cutoff(process: str) -> float:
    meta = META.get(process)
    return DESIGN_CUTOFF if meta is None or meta.cutoff is None else float(meta.cutoff)


def meta_for(process: str) -> ProcessMeta:
    meta = META.get(process)
    if meta is not None:
        return meta
    initials = "".join(word[0] for word in process.replace("/", " ").split() if word).upper()[:4]
    return ProcessMeta(process, initials or "XX", "ETC", "PKG", "C4", "3F", 10)


class Namer:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def next(self, process: str) -> str:
        abbr = meta_for(process).abbr
        self.counts[abbr] += 1
        return f"DEMO-{abbr}-{self.counts[abbr]:03d}"


def schedule_from_qual(name: str, qual: date) -> tuple[date, date, date]:
    arrival = qual - timedelta(days=14 + hashed(f"a:{name}") % 21)
    logi = arrival - timedelta(days=3 + hashed(f"l:{name}") % 5)
    vib = logi - timedelta(days=5 + hashed(f"v:{name}") % 6)
    return vib, logi, arrival


def base_unit(process: str, name: str, kind: str, facts: SimFacts, index: int) -> Unit:
    process_no = next((i for i, m in enumerate(PROCESS_META) if m.name == process), 30)
    usage = "HBM"
    if process in facts.edp_processes and hashed(f"edp:{name}") % 10 == 0:
        usage = "EDP"
    unit = Unit(
        name=name,
        process=process,
        kind=kind,
        usage=usage,
        maker=f"DEMO-MAKER-{'ABCD'[hashed(f'mk:{process}') % 4]}",
        model=f"DEMO-MDL-{10 + 2 * process_no + (1 if kind == 'new' else 0):02d}",
        area_code=facts.area.get(process, "Main"),
        manager=f"DEMO 담당 {'ABCD'[process_no % 4]}",
        invest="개발" if hashed(f"inv:{name}") % 17 == 0 else "양산",
    )
    if kind == "new" and hashed(f"capa:{name}") % 3 != 0:
        unit.invest_capa = f"{100 + 5 * (hashed(f'cp:{name}') % 40)}K"
    if hashed(f"eh:{name}") % 7 == 0:
        unit.equipment_history = "26.08 정기 PM 완료(합성)"
    return unit


def existing_done(unit: Unit, index: int) -> None:
    """반입·Qual 실적이 2025-03 ~ 2026-09 인 완료 호기."""
    start = date(2025, 3, 1)
    span = (date(2026, 9, 10) - start).days
    unit.qual = start + timedelta(days=hashed(f"eq:{unit.name}") % span)
    unit.vib, unit.logi, unit.arrival = schedule_from_qual(unit.name, unit.qual)
    unit.unit_history = f"{unit.arrival:%y.%m} 반입 · {unit.qual:%y.%m} Qual"


def design_fleet(facts: SimFacts) -> Fleet:
    namer = Namer()
    units: list[Unit] = []
    baseline: list[dict[str, object]] = []
    downtime: list[Downtime] = []
    targets: dict[str, dict[int, float]] = {}
    notes: list[str] = []
    months = facts.months

    for process in facts.processes:
        if process not in META:
            notes.append(f"표에 없는 공정 {process} — 기본 속성으로 짠다")
        cutoff = design_cutoff(process)
        series: dict[int, float] = {}
        running = 0.0
        last = 0.0
        for month in months:
            value = facts.available.get((process, month), last)
            last = value
            running = max(running, value)
            series[month] = running
        if process == "TC Bonding":
            # 28.02 부터 공식보다 2대 적게 — 기존 2대가 28.02 W/D 첫날 이설로 빠지고 대체 신규가
            # 없다 (아래 기존 fleet 에서 2대에 반출/이설일정을 단다).
            for month in months:
                if month >= TCB_SHORT_FROM:
                    series[month] = series[month] - TCB_SHORT_UNITS
        targets[process] = series
        proc_units: list[Unit] = []

        def add(unit: Unit, units: list[Unit] = proc_units) -> Unit:
            units.append(unit)
            return unit

        def counted_at(
            month: int,
            units: list[Unit] = proc_units,
            days: float = cutoff,
            name: str = process,
        ) -> float:
            total: float = sum(u.contributes(month, days) for u in units)
            total += sum(
                float(cast(float, row["기존보유대수"])) for row in baseline if row["공정"] == name
            )
            return total

        first = months[0]
        if process == "Packing":
            top = max(series.values()) if series else 0.0
            share = math.floor(top * 0.7)
            baseline.append(
                {
                    "공정": process,
                    "분류": BASELINE_CLASS,
                    "기존보유대수": float(share),
                    "비고": "대장 밖 기존 보유(합성)",
                }
            )
            baseline.append(
                {
                    "공정": process,
                    "분류": "물류 위탁",
                    "기존보유대수": float(top - share),
                    "비고": "위탁 운영분(합성)",
                }
            )
            for number in range(2):
                agv = add(
                    base_unit(
                        process,
                        f"DEMO-{meta_for(process).abbr}-AGV{number + 1}",
                        "extra",
                        facts,
                        number,
                    )
                )
                agv.usage = "범용"
                agv.area_code = "부대"
                agv.existing_flag = "Y"
                agv.model = "DEMO-MDL-AGV"
                agv.memo1 = "AGV — 부대 설비(가용대수에 세지 않음)"
            units.extend(proc_units)
            continue
        if process == "Tape Pocket Inspection":
            for number in range(4):
                tpi = add(base_unit(process, namer.next(process), "existing", facts, number))
                tpi.usage = "범용"
                if number < 2:
                    tpi.existing_flag = "Y"
                else:
                    existing_done(tpi, number)
                tpi.memo1 = "범용 — 가용대수에 세지 않음"
            units.extend(proc_units)
            continue
        if process == "Burn-In":
            baseline.append(
                {
                    "공정": process,
                    "분류": BASELINE_CLASS,
                    "기존보유대수": 6.0,
                    "비고": "대장 밖 기존 보유(합성)",
                }
            )
        if process == "Final Test":
            fraction = round(series[first] - math.floor(series[first]), 3)
            baseline.append(
                {
                    "공정": process,
                    "분류": BASELINE_CLASS,
                    "기존보유대수": 4.0 + fraction,
                    "비고": "1/3 모듈 소수 보유 포함(합성)",
                }
            )

        # --- 상태 표본(특수 호기)
        if process == "Wafer Grinding":
            planned = add(base_unit(process, namer.next(process), "existing", facts, 0))
            existing_done(planned, 0)
            planned.stop = date(2027, 3, 15)
            planned.memo1 = "노후 — 27.03 정지 예정"
            stopped = add(base_unit(process, namer.next(process), "existing", facts, 1))
            existing_done(stopped, 1)
            stopped.stop = date(2026, 10, 15)
            stopped.memo1 = "노후 — 26.10 정지"
        if process == "Burn-In":
            leaving = add(base_unit(process, namer.next(process), "existing", facts, 0))
            existing_done(leaving, 0)
            leaving.relocation = date(2027, 6, 30)
            leaving.memo1 = "타 사업장 이설 예정"
        if process == "Laser Grooving":
            gone = add(base_unit(process, namer.next(process), "existing", facts, 0))
            existing_done(gone, 0)
            gone.relocation = date(2026, 9, 30)
            gone.memo1 = "26.09 반출 완료"
        if process == "Final Test":
            for number in range(2):
                kept = add(base_unit(process, namer.next(process), "extra", facts, number))
                kept.storage = "Y"
                kept.arrival = date(2025, 11, 10 + number)
                kept.memo1 = "보관 설비 — 수요 증가 시 투입"
        if process == "AVI":
            for number in range(2):
                pending = add(base_unit(process, namer.next(process), "new", facts, number))
                pending.placed = False
                pending.memo1 = "일정 미정 — 발주 협의 중"
        if process in ("Wafer Sorter", "X-Ray", "Underfill"):
            spare = add(base_unit(process, namer.next(process), "extra", facts, 0))
            spare.usage = None
            spare.existing_flag = "Y"
            spare.memo1 = "예비 설비 — 사용기준 미정"
        if process == "Mold":
            group = "DEMO-MLD-M01"
            qual = date(2026, 5, 20)
            for letter, offset in (("A", 0), ("B", 2)):
                module = add(base_unit(process, f"{group}{letter}", "existing", facts, 0))
                module.parent = group
                module.cell = group
                module.ratio = 0.5
                module.qual = qual + timedelta(days=offset)
                module.vib, module.logi, module.arrival = schedule_from_qual(group, qual)
                module.unit_history = f"{module.arrival:%y.%m} 반입 · 2모듈 묶음"

        # --- 기존 fleet(26.11)
        old_models = 2 if process == "Wafer Saw" else 0
        number = 0
        while counted_at(first) < series[first] - 1e-9:
            unit = add(base_unit(process, namer.next(process), "existing", facts, number))
            if old_models:
                unit.ratio = 0.8
                unit.model = "DEMO-MDL-91"
                unit.memo1 = "구모델(환산비 0.8)"
                old_models -= 1
            if number % 3 == 0:
                unit.existing_flag = "Y"
            else:
                existing_done(unit, number)
            number += 1
        if process == "TC Bonding":
            # 노후 6대는 27년 중 정지하고 대체 신규가 들어온다(신규 30대 이상), 2대는 28.02 W/D 첫날
            # 이설되고 대체가 없다(28.02~ 2대 부족).
            done = [
                u
                for u in proc_units
                if u.kind == "existing" and u.existing_flag == "N" and u.parent is None
            ]
            retire_days = (
                date(2027, 6, 30),
                date(2027, 6, 30),
                date(2027, 9, 30),
                date(2027, 9, 30),
                date(2027, 12, 15),
                date(2027, 12, 15),
            )
            for unit, day in zip(done[:6], retire_days, strict=False):
                unit.stop = day
                unit.memo1 = f"노후 — {day:%y.%m} 정지(대체 신규 반입)"
            leave = wd_window(TCB_SHORT_FROM, cutoff).first_day
            for unit in done[6:8]:
                unit.relocation = leave
                unit.memo1 = f"{leave:%y.%m.%d} 타 사업장 이설 — 대체 미확보"
        if process == "Wafer Saw":
            # 26.11 W/D 구간 안(10/20)에 Qual 이 끝난 완료 호기 — 그 구간은 오늘 이미 끝나 「기한
            # 지남」. 일정 기준 확보율이 그 달 목표 아래로 내려가게 대수를 정한다(1~4대).
            window = wd_window(first, cutoff)
            lost = (
                1 - max(0, (window.boundary_end - WAFER_SAW_LATE_EXISTING_QUAL).days) / window.days
            )
            need = facts.required.get((process, first), 0.0)
            goal = float(facts.thresholds.secure_for(first)) - 0.003
            count = 1
            if lost > 0 and need > 0:
                count = min(4, max(1, math.ceil((counted_at(first) - goal * need) / lost)))
            lates = [
                u
                for u in reversed(proc_units)
                if u.kind == "existing" and u.existing_flag == "N" and u.ratio == 1.0
            ][:count]
            for late in lates:
                late.qual = WAFER_SAW_LATE_EXISTING_QUAL
                late.vib, late.logi, late.arrival = schedule_from_qual(late.name, late.qual)
                late.unit_history = "26.09 반입 · 26.10 Qual(늦게 완료)"
                late.memo1 = "Qual 이 26.11 W/D 구간 안에서 끝남 — 기한 지남 사례"
            notes.append(f"Wafer Saw 26.11 늦은 Qual 호기 {len(lates)}대(구간 손실 {lost:.2f}대씩)")

        # --- 신규(달마다)
        avi_fast = 4
        daf_early = 0
        for month in months[1:]:
            window = wd_window(month, cutoff)
            while counted_at(month) < series[month] - 1e-9:
                unit = add(base_unit(process, namer.next(process), "new", facts, len(proc_units)))
                unit.month = month
                if process == "AVI" and avi_fast > 0:
                    unit.ratio = 1.5
                    unit.model = "DEMO-MDL-90"
                    unit.memo1 = "신모델(환산비 1.5)"
                    avi_fast -= 1
                qual_window = window
                if process == "DAF Attach" and month >= DAF_EARLY_MONTHS[0] and daf_early < 3:
                    qual_window = wd_window(add_months(month, -1), cutoff)
                    unit.memo1 = "일정 앞섬 — 한 달 일찍 Qual"
                    daf_early += 1
                unit.qual = qual_window.boundary_start - timedelta(
                    days=hashed(f"q:{unit.name}") % 9
                )
                unit.vib, unit.logi, unit.arrival = schedule_from_qual(unit.name, unit.qual)
        units.extend(proc_units)

    fleet = Fleet(units=units, baseline=baseline, downtime=downtime, targets=targets, notes=notes)
    apply_stories(fleet, facts)
    ensure_carried_story(fleet, facts)
    return fleet


def manual_cells(facts: SimFacts) -> dict[tuple[str, int], float]:
    """입력 비가동 넷. Post Mold Cure 27.05 는 공식 가용보다 4 크게(⚠)."""
    pmc = facts.available.get(("Post Mold Cure", 202705), 0.0)
    cells = {
        ("Mold", 202702): 2.0,
        ("TC Bonding", 202703): 3.0,
        ("Wafer Saw", 202612): 1.0,
        ("Post Mold Cure", 202705): float(math.ceil(pmc) + 4),
    }
    return {
        key: value
        for key, value in cells.items()
        if key[0] in facts.processes and key[1] in facts.months
    }


def design_plan(fleet: Fleet, facts: SimFacts) -> ShorteningPlan:
    """저장 전 설계(r3)로 앱과 같은 110% 계획을 낸다 — 입력 비가동·Cut-off 포함."""
    equipment = equipment_frame(fleet, "r3")
    names = set(equipment["설비명"].astype(str))
    rows = [(p, m, v) for (p, m), v in manual_cells(facts).items()]
    return plan_required_shortening(
        equipment=equipment,
        downtime=downtime_frame(fleet, "r3", names),
        baseline=baseline_frame(fleet),
        cutoff=cutoff_frame(facts),
        required_equipment=facts.required_rows,
        months=facts.months,
        today=TODAY,
        levels=(1.1,),
        manual_downtime=manual_downtime_key(rows, facts.months),
    )


CARRIED_EXCLUDED = frozenset(
    {
        "Wafer Saw",
        "Pre B/D",
        "TC Bonding",
        "Mold",
        "Post Mold Cure",
        "Ball Attach",
        "DAF Attach",
        "Shipping Inspection",
        "Packing",
        "Tape Pocket Inspection",
    }
)


def ensure_carried_story(fleet: Fleet, facts: SimFacts) -> None:
    """「앞달 단축으로 해소」 칸이 없으면 하나 만든다(11월 1주에 드러난 셋업 지연 — r1·r2 는 원래
    일정).

    한 공정의 이어진 신규 달 [a, b] 의 신규를 모두, 그 뒤 신규가 없는 달 m1 의 W/D 끝 9일 전 Qual
    로 늦춘다. 계획은 처음 모자란 달에 그 호기를 당기고, 당긴 호기가 뒤 달도 덮어 그 사이 원래
    모자랐던 달이 「앞달 단축으로 해소」 가 된다. 후보는 실제 계획의 여유(가용 − 소요 × 110%)로
    미리 흉내 내 고르고, 다시 계산해 그 상태가 서는지 확인한다(안 서면 되돌리고 다음 후보)."""
    from capa_simulation.services.required_shortening import STATUS_CARRIED

    plan = design_plan(fleet, facts)
    table = plan.at(1.1).process_months
    if table["상태"].eq(STATUS_CARRIED).any():
        return
    margin: dict[tuple[str, int], float] = {}
    for process, month, required, available in zip(
        table["공정"], table["생산계획년월"], table["소요대수"], table["가용대수"], strict=True
    ):
        margin[(str(process), int(month))] = float(available) - float(required) * 1.1
    preferred = [p for p in CARRIED_PREFERRED if p not in CARRIED_EXCLUDED]
    ordered = preferred + [
        p for p in facts.processes if p not in preferred and p not in CARRIED_EXCLUDED
    ]
    months = list(facts.months)
    options: list[tuple[int, int, int, int, str, tuple[int, ...], int]] = []
    for rank, process in enumerate(ordered):
        units = [
            u
            for u in fleet.units
            if u.process == process
            and u.kind == "new"
            and u.month
            and u.qual
            and u.present_from == "r1"
        ]
        if any(u.parent for u in units):
            continue
        growth = sorted({u.month for u in units if u.month is not None})
        for i, first in enumerate(growth):
            for j in range(i, min(i + 2, len(growth))):
                block = tuple(growth[i : j + 1])
                last = block[-1]
                after = growth[j + 1] if j + 1 < len(growth) else add_months(months[-1], 1)
                if not (202612 <= first and add_months(last, 1) <= 202712):
                    continue
                count = sum(1 for u in units if u.month in block)
                for m1 in [m for m in months if last < m < after and m <= 202712][:6]:
                    carried = simulate_delay(margin, process, block, count, m1, months)
                    if carried:
                        span = months.index(m1) - months.index(last)
                        options.append((count, span, rank, -carried, process, block, m1))
    for count, _span, _rank, _neg, process, block, m1 in sorted(options)[:10]:
        chosen = [
            u for u in fleet.units if u.process == process and u.kind == "new" and u.month in block
        ]
        window = wd_window(m1, design_cutoff(process))
        target = window.boundary_end - timedelta(days=9)
        saved = [(u, u.qual, dict(u.qual_by_rev), u.memo2, dict(u.history_by_rev)) for u in chosen]
        for unit in chosen:
            assert unit.qual is not None
            unit.qual_by_rev.setdefault("r1", unit.qual)
            unit.qual_by_rev.setdefault("r2", unit.qual)
            unit.qual = target
            unit.memo2 = "11월 1주 — 셋업 지연으로 Qual 늦춤"
            unit.history_by_rev["r3"] = f"Qual {target:%m/%d} 로 지연(셋업 부품)"
        check = design_plan(fleet, facts).at(1.1).process_months
        hit = check.loc[
            check["공정"].eq(process) & check["상태"].eq(STATUS_CARRIED), "생산계획년월"
        ]
        if not hit.empty:
            fleet.carried_process = process
            fleet.notes.append(
                f"「앞달 단축으로 해소」 사례: {process} {'·'.join(month_text(m) for m in block)} "
                f"신규 {count}대 Qual 을 "
                f"{target:%m/%d} 로 늦춤 → " + ", ".join(month_text(int(m)) for m in hit)
            )
            return
        for unit, qual, by_rev, memo, history in saved:
            unit.qual, unit.qual_by_rev, unit.memo2, unit.history_by_rev = (
                qual,
                by_rev,
                memo,
                history,
            )
    fleet.notes.append("「앞달 단축으로 해소」 사례를 만들 자리(빠듯한 이어진 달)를 찾지 못했다")


def simulate_delay(
    margin: dict[tuple[str, int], float],
    process: str,
    block: tuple[int, ...],
    count: int,
    m1: int,
    months: Sequence[int],
) -> int:
    """[a, b] 신규 `count` 대를 m1 끝 9일 전으로 늦췄을 때 계획이 「앞달 단축으로 해소」 로 둘 달 "
    "수(흉내)."""
    per_month = {month: 0 for month in block}
    for month in block:
        per_month[month] = 1  # 자리표 — 실제 대수는 아래 비율로 나눈다
    remaining = float(count)
    pulled_any = False
    carried = 0
    first = block[0]
    for month in months:
        if month < first or month > m1:
            continue
        present = sum(1 for m in block if m <= month)
        share = count * present / len(block) if month < block[-1] else float(count)
        loss_full = share if month < m1 else share * 0.7
        lost_now = min(remaining, share) * (1.0 if month < m1 else 0.7)
        gap = margin.get((process, month))
        if gap is None:
            return 0
        originally_short = loss_full > gap + 0.05
        if lost_now > gap + 0.05:
            need = lost_now - gap
            remaining -= math.ceil(need / (1.0 if month < m1 else 0.7) - 1e-9)
            remaining = max(remaining, 0.0)
            pulled_any = True
        elif originally_short and pulled_any:
            carried += 1
    return carried


def apply_stories(fleet: Fleet, facts: SimFacts) -> None:
    by_process: dict[str, list[Unit]] = defaultdict(list)
    for unit in fleet.units:
        by_process[unit.process].append(unit)

    # Ball Attach 27.01–04 신규 Qual 지연(기준✓·일정✕). r1 은 더 늦고 r2 는 앞 3대만 당겼다.
    ball_new = sorted(
        (
            u
            for u in by_process.get("Ball Attach", [])
            if u.kind == "new"
            and u.month is not None
            and BALL_DELAY_MONTHS[0] <= u.month <= 202709
            and u.qual is not None
        ),
        key=lambda u: (u.month, u.qual, u.name),
    )
    ball = [u for u in ball_new if u.month in BALL_DELAY_MONTHS]
    if len(ball) < 4:
        ball = ball_new[: max(4, len(ball))]
        fleet.notes.append(
            "Ball Attach 27.01–04 신규가 모자라 지연 대상을 "
            + (
                f"{month_text(ball[0].month or 0)}–{month_text(ball[-1].month or 0)}"
                if ball
                else "(없음)"
            )
            + f" {len(ball)}대로 넓혔다"
        )
    ball.sort(key=lambda u: (u.qual, u.name))
    for index, unit in enumerate(ball):
        assert unit.qual is not None
        base = unit.qual
        unit.qual = base + timedelta(days=BALL_DELAY_DAYS["r3"])
        unit.qual_by_rev["r1"] = base + timedelta(days=BALL_DELAY_DAYS["r1"])
        unit.qual_by_rev["r2"] = base + timedelta(
            days=BALL_DELAY_DAYS["r3"] if index < BALL_PULLED_IN_R2 else BALL_DELAY_DAYS["r2"]
        )
        unit.history_by_rev["r3"] = "26.10 Qual 일정 +35일 지연(부품 수급)"
        if index < BALL_PULLED_IN_R2:
            unit.history_by_rev["r2"] = "10월 2주 기준선 요청으로 Qual 당김"
            unit.scenario_memo_by_rev["r2"] = "기준선 ① 요청 반영"
    for unit in ball[:2]:
        unit.qual_status_by_rev["r3"] = "지연"
        unit.memo2 = "Qual 지연 — 부품 수급"

    # Wafer Saw 26.12 몫 1대 Qual 2026-12-20(그 달 W/D 구간을 지남).
    saw = [u for u in by_process.get("Wafer Saw", []) if u.kind == "new" and u.month == 202612]
    if saw:
        target = saw[-1]
        target.qual = WAFER_SAW_LATE_QUAL
        target.memo1 = "Qual 12/20 — 26.12 W/D 구간 밖"
    else:
        later = sorted(
            (u for u in by_process.get("Wafer Saw", []) if u.kind == "new" and u.month),
            key=lambda u: (u.month, u.name),
        )
        if later:
            target = later[0]
            late_month = target.month
            assert late_month is not None  # 신규 호기는 늘 몫 달이 있다(`later` 가 거른다)
            window = wd_window(late_month, design_cutoff("Wafer Saw"))
            target.qual = window.boundary_end - timedelta(days=5)
            target.memo1 = f"Qual {target.qual:%m/%d} — {month_text(late_month)} W/D 구간 끝 무렵"
            fleet.notes.append(
                f"Wafer Saw 26.12 신규가 없어 {month_text(late_month)} 몫 1대를 그 달 구간 끝 "
                "무렵 Qual 로 늦췄다"
            )
        else:
            fleet.notes.append("Wafer Saw 신규가 없어 늦은 Qual 사례를 만들지 못했다")

    # TC Bonding — 모듈 묶음 셋(M01 4모듈 · M02 3모듈 · M03 4모듈 미배치), r1·r2 의 27년 신규 Qual
    # +20일, r3 에만 있는 2028 신규 3대. 묶음 편집(equip-62)이 볼 갈래: 2·3·4모듈 묶음, 숨은
    # 모듈(M01 D — 레이아웃표시 N), 서랍의 묶음(M03 — 좌표 없음).
    tcb = [u for u in by_process.get("TC Bonding", []) if u.kind == "new"]
    group_months = (202703, 202709, 202803)
    group_letters = {1: "ABCD", 2: "ABC", 3: "ABCD"}
    groups_made = 0
    for group_no, wanted in enumerate(group_months, start=1):
        candidates = [
            u
            for u in tcb
            if u.month is not None and u.month >= wanted and u.parent is None and u.cell is None
        ]
        if not candidates:
            continue
        host = candidates[0]
        group = f"DEMO-TCB-M{group_no:02d}"
        window_start = host.qual or TODAY
        qual0 = window_start - timedelta(days=12)
        index = fleet.units.index(host)
        modules: list[Unit] = []
        letters = group_letters[group_no]
        for letter_no, letter in enumerate(letters):
            module = replace(
                host,
                name=f"{group}{letter}",
                parent=group,
                cell=group,
                ratio=1 / len(letters),
                qual=qual0 + timedelta(days=letter_no),
                qual_by_rev={},
                memo1=f"{len(letters)}모듈 묶음 — 모듈 Qual 엇갈림",
            )
            module.vib, module.logi, module.arrival = schedule_from_qual(group, qual0)
            if group_no == 1 and letter == "D":
                module.layout_flag = "N"
                module.memo2 = "D 모듈 도면 숨김(레이아웃표시 N) — 묶음 칸은 비워 둠"
            if group_no == 3:
                module.placed = False
                module.memo2 = "자리 미정 — Space 서랍(미배치)에서 놓기"
            modules.append(module)
        fleet.units[index : index + 1] = modules
        tcb.remove(host)
        groups_made += 1
    if groups_made < 3:
        fleet.notes.append(f"TC Bonding 모듈 묶음 {groups_made}개만 만들었다(신규가 모자람)")
    for unit in tcb:
        if unit.month is not None and unit.month < 202801 and unit.qual is not None:
            unit.qual_by_rev["r1"] = unit.qual + timedelta(days=TCB_R1_DELAY_DAYS)
            unit.qual_by_rev["r2"] = unit.qual + timedelta(days=TCB_R1_DELAY_DAYS)
    late_tcb = [u for u in tcb if u.month is not None and u.month >= 202801][-3:]
    for unit in late_tcb:
        unit.present_from = "r3"
        unit.memo1 = "11월 1주 신규 등록(공통 대장에 처음)"
    if len(late_tcb) < 3:
        fleet.notes.append(f"r3 에만 있는 TC Bonding 2028 신규 {len(late_tcb)}대")

    # 레이아웃표시 N 2대(X-Ray·Laser Marking 의 기존 호기).
    for process in ("X-Ray", "Laser Marking"):
        candidates = [
            u
            for u in by_process.get(process, [])
            if u.kind == "existing" and u.existing_flag == "Y" and u.usage
        ]
        if candidates:
            candidates[0].layout_flag = "N"
            candidates[0].placed = False
            candidates[0].memo2 = "도면 미표시(레이아웃표시 N)"

    # 비가동 — TC Bonding 32건, Pre B/D 개발대여, Mold 공사 1, 보관·셋업 중 호기(영향 없음).
    tcb_hosts = [
        u
        for u in by_process.get("TC Bonding", [])
        if u.kind == "existing" and u.parent is None and u.counted() and u.exit_day() is None
    ][:16]
    kinds = ["기타"] * 20 + ["고장"] * 8 + ["공사"] * 4
    start = date(2026, 11, 5)
    span_days = (date(2028, 12, 10) - start).days
    rows: list[Downtime] = []
    for number in range(32):
        host = tcb_hosts[number % len(tcb_hosts)]
        kind = kinds[(number * 7) % len(kinds)]
        if number == 0:
            begin, end = date(2026, 10, 20), date(2026, 11, 3)
            kind, reason = "고장", "헤드 교체(10월부터 이어짐)"
        elif number == 31:
            begin, end = date(2028, 12, 15), date(2029, 1, 31)
            kind, reason = "공사", "라인 증설 공사(29.01 까지)"
        else:
            begin = start + timedelta(days=(span_days * number) // 31 + hashed(f"dt:{number}") % 9)
            length = {"기타": 1 + number % 3, "고장": 2 + number % 3, "공사": 5 + number % 3}[kind]
            end = begin + timedelta(days=length - 1)
            reason = {"기타": "정기 PM", "고장": "본딩 헤드 고장", "공사": "유틸리티 공사"}[kind]
        from_rev = "r1" if number < 12 else ("r2" if number < 20 else "r3")
        rows.append(Downtime(host.name, kind, begin, end, reason, "합성 비가동", from_rev))
    seen = set()
    for row in rows:
        key = (row.unit, row.kind, row.start)
        if key in seen:
            row.start = row.start + timedelta(days=1)
            if row.end is not None:
                row.end = row.end + timedelta(days=1)
        seen.add((row.unit, row.kind, row.start))
    fleet.downtime.extend(rows)
    dip = fleet.targets.get("Pre B/D", {}).get(202612, 0.0) - facts.available.get(
        ("Pre B/D", 202612), 0.0
    )
    pre_bd = [u for u in by_process.get("Pre B/D", []) if u.kind == "existing" and u.counted()][
        : max(2, min(6, round(dip)))
    ]
    for host in pre_bd:
        fleet.downtime.append(
            Downtime(
                host.name,
                "개발대여",
                date(2026, 12, 1),
                date(2026, 12, 31),
                "개발팀 평가 대여(26.12)",
                "공식 대여 2대와 같은 이야기",
                "r2",
            )
        )
    mold = [
        u
        for u in by_process.get("Mold", [])
        if u.kind == "existing" and u.parent is None and u.counted()
    ][:1]
    for host in mold:
        fleet.downtime.append(
            Downtime(
                host.name,
                "공사",
                date(2027, 2, 1),
                date(2027, 2, 20),
                "금형 교체 공사",
                "27.02 금형 교체",
                "r2",
            )
        )
    kept = [u for u in by_process.get("Final Test", []) if u.storage == "Y"][:1]
    for host in kept:
        fleet.downtime.append(
            Downtime(
                host.name,
                "기타",
                date(2026, 11, 10),
                date(2026, 11, 12),
                "보관 설비 정기 점검",
                "가용 영향 없음",
                "r3",
            )
        )
    setup = next(
        (
            u
            for u in fleet.units
            if u.kind == "new"
            and u.arrival is not None
            and u.qual is not None
            and u.arrival < TODAY - timedelta(days=3)
            and u.qual > TODAY + timedelta(days=10)
            and u.parent is None
            and u.counted()
            and u.present_from == "r1"
        ),
        None,
    )
    if setup is not None:
        fleet.downtime.append(
            Downtime(
                setup.name,
                "기타",
                TODAY + timedelta(days=2),
                TODAY + timedelta(days=4),
                "셋업 중 부품 교체",
                "Qual 전이라 가용 영향 없음",
                "r3",
            )
        )
    else:
        fleet.notes.append("셋업 중(반입 완료·Qual 미래) 호기를 찾지 못해 그 비가동을 넣지 않았다")


# ------------------------------------------------------------------ 배치(Space)

UNIT_W, UNIT_H, PITCH_X, PITCH_Y = 6.0, 4.0, 7.5, 5.5
MARGIN_X, BOTTOM, TOP_RESERVE = 5.0, 8.0, 9.0
RESERVE_COLUMNS = 3
ZONE_COLORS = ("blue", "rose", "green", "violet", "sky", "gray")


# 일정 확인 세 갈래(equip-19) — 11-02 공통 대장(운영 r3)에서 실적·상태만 바꾼다. 날짜는 그대로라
# 설비 일정 기준 가용·필요 단축 일정·공정 Capa 상세 집계는 달라지지 않는다(실적은 Space 실물 판정과
# 알림에만 — equipment_contract).
ARRIVAL_UNCONFIRMED = "반입 미확인"  # 반입일정 지남 · 반입실적 빔 · 반입상태 확정
QUAL_UNCONFIRMED = "Qual 미확인"  # Qual일정 지남 · Qual실적 빔 · Qual상태 확정
ARRIVAL_MISSING = "반입 실적 누락"  # 반입상태 완료 · 반입실적 빔
QUAL_MISSING = "Qual 실적 누락"  # Qual상태 완료 · Qual실적 빔
ARRIVAL_STALE = "반입 상태 갱신 필요"  # 반입실적 있음 · 반입상태 확정
QUAL_STALE = "Qual 상태 갱신 필요"  # Qual실적 있음 · Qual상태 확정
# 이야기·단축 카드에 쓰인 공정은 건드리지 않는다(Qual상태가 「완료」 밖이면 단축 후보가 된다).
CONFIRM_AVOID = frozenset(
    {
        "Wafer Saw",
        "Pre B/D",
        "Mold",
        "Ball Attach",
        "Wafer Incoming Inspection",
        "Post Mold Cure",
        "Wafer Sorter",
    }
)


def confirmation_story(fleet: Fleet) -> list[str]:
    """반입 미확인 3 + 둘 다 미확인 1 + Qual 미확인 2(Space 「!」 — 모두 도면에 놓인 호기), 실적 "
    "누락 2, 상태 갱신 필요 2."""

    def plain(unit: Unit) -> bool:
        return (
            unit.kind in ("new", "existing")
            and unit.existing_flag == "N"
            and unit.storage == "N"
            and unit.parent is None
            and unit.cell is None
            and unit.placed
            and unit.place is not None
            and unit.process not in CONFIRM_AVOID
            and not unit.qual_status_by_rev
            and not unit.history_by_rev
            and not unit.scenario_memo_by_rev
            and unit.memo1 is None
            and unit.exit_day() is None
            and unit.present_from == "r1"
            and unit.arrival is not None
            and unit.qual_at("r3") is not None
            and unit.counted()
        )

    pool = sorted((u for u in fleet.units if plain(u)), key=lambda u: u.name)
    taken: set[str] = set()

    def pick(wanted: Callable[[Unit], bool], count: int, kinds: tuple[str, ...]) -> list[str]:
        found = [u for u in pool if u.name not in taken and wanted(u)]
        chosen: list[Unit] = []
        for unit in found:  # 다른 공정부터
            if len(chosen) < count and unit.process not in {c.process for c in chosen}:
                chosen.append(unit)
        for unit in found:
            if len(chosen) < count and unit not in chosen:
                chosen.append(unit)
        for unit in chosen:
            unit.confirm = kinds
            taken.add(unit.name)
        return [f"{u.name}({u.process})" for u in chosen]

    def qual(unit: Unit) -> date:
        value = unit.qual_at("r3")
        assert value is not None
        return value

    def arrival(unit: Unit) -> date:
        assert unit.arrival is not None
        return unit.arrival

    lines = []
    both = pick(
        lambda u: (
            arrival(u) <= TODAY - timedelta(days=14)
            and TODAY - timedelta(days=7) <= qual(u) < TODAY
        ),
        1,
        (ARRIVAL_UNCONFIRMED, QUAL_UNCONFIRMED),
    )
    lines.append(f"반입·Qual 둘 다 미확인 {len(both)}: {', '.join(both)}")
    quals = pick(
        lambda u: arrival(u) < TODAY and TODAY - timedelta(days=14) <= qual(u) < TODAY,
        2,
        (QUAL_UNCONFIRMED,),
    )
    lines.append(f"Qual 미확인 {len(quals)}: {', '.join(quals)}")
    arrivals = pick(
        lambda u: TODAY - timedelta(days=14) <= arrival(u) < TODAY < qual(u),
        3,
        (ARRIVAL_UNCONFIRMED,),
    )
    lines.append(f"반입 미확인 {len(arrivals)}: {', '.join(arrivals)}")

    def done(unit: Unit) -> bool:
        return date(2026, 8, 1) <= qual(unit) <= date(2026, 9, 30)

    for kinds in ((QUAL_MISSING,), (ARRIVAL_MISSING,), (QUAL_STALE,), (ARRIVAL_STALE,)):
        names = pick(done, 1, kinds)
        lines.append(f"{kinds[0]} {len(names)}: {', '.join(names)}")
    return lines


def apply_confirmation(row: dict[str, object], kinds: tuple[str, ...]) -> None:
    for kind in kinds:
        if kind == ARRIVAL_UNCONFIRMED:
            row.update({"반입실적": pd.NaT, "반입상태": "확정"})
        elif kind == QUAL_UNCONFIRMED:
            row.update({"Qual실적": pd.NaT, "Qual상태": "확정"})
        elif kind == ARRIVAL_MISSING:
            row["반입실적"] = pd.NaT
        elif kind == QUAL_MISSING:
            row["Qual실적"] = pd.NaT
        elif kind == ARRIVAL_STALE:
            row["반입상태"] = "확정"
        elif kind == QUAL_STALE:
            row["Qual상태"] = "확정"
        else:
            raise ValueError(kind)


def layout_fleet(fleet: Fleet, facts: SimFacts) -> None:
    by_floor: dict[tuple[str, str], list[str]] = defaultdict(list)
    for process in facts.processes:
        meta = meta_for(process)
        by_floor[(meta.building, meta.floor)].append(process)
    overlap_unit: Unit | None = None
    singulation = [
        u
        for u in fleet.units
        if u.process == "Singulation"
        and u.kind == "existing"
        and u.existing_flag == "Y"
        and u.placed
    ]
    if len(singulation) >= 2:
        overlap_unit = singulation[1]
    for key in sorted(by_floor, key=lambda k: FLOOR_ORDER.index(k) if k in FLOOR_ORDER else 99):
        width, height = CANVAS_BIG.get(key, CANVAS_DEFAULT)
        rows_total = int((height - BOTTOM - TOP_RESERVE + (PITCH_Y - UNIT_H)) // PITCH_Y)
        blocks: list[tuple[str, list[list[Unit]]]] = []
        for process in by_floor[key]:
            cells: list[list[Unit]] = []
            seen_cells: dict[str, list[Unit]] = {}
            for unit in fleet.units:
                if unit.process != process or not unit.placed or unit is overlap_unit:
                    continue
                if unit.cell is not None:
                    if unit.cell not in seen_cells:
                        seen_cells[unit.cell] = []
                        cells.append(seen_cells[unit.cell])
                    seen_cells[unit.cell].append(unit)
                else:
                    cells.append([unit])
            blocks.append((process, cells))
        columns_needed = sum(max(1, math.ceil(len(c) / rows_total)) for _, c in blocks if c)
        columns_needed += max(0, len([b for b in blocks if b[1]]) - 1) + RESERVE_COLUMNS + 1
        need_width = 2 * MARGIN_X + columns_needed * PITCH_X
        if need_width > width:
            width = float(math.ceil(need_width / 10) * 10)
            fleet.notes.append(f"{key[0]} {key[1]} 캔버스 폭을 {width:g} 로 넓혔다")
        fleet.canvases[key] = (width, height)
        # 폭을 고루 쓴다 — 남는 열(예비 열·통로를 뺀)을 공정 호기 수에 비례해 나눈다(최소는 행
        # 한도로 정한 열).
        filled = [(process, cells) for process, cells in blocks if cells]
        total_columns = int((width - 2 * MARGIN_X + (PITCH_X - UNIT_W)) // PITCH_X)
        spare = total_columns - RESERVE_COLUMNS - 1 - max(0, len(filled) - 1)
        minimum = {process: max(1, math.ceil(len(cells) / rows_total)) for process, cells in filled}
        allotted = dict(minimum)
        units_total = sum(len(cells) for _, cells in filled) or 1
        while sum(allotted.values()) < spare:
            # 행이 가장 많은(가장 길쭉한) 블록에 한 열씩 — 호기 수보다 넓히지 않는다.
            growable = [
                (math.ceil(len(cells) / allotted[process]), len(cells) / units_total, process)
                for process, cells in filled
                if allotted[process] < len(cells)
            ]
            if not growable:
                break
            _rows, _share, widest = max(growable)
            if _rows <= 2:
                break
            allotted[widest] += 1
        top_y = height - TOP_RESERVE - UNIT_H
        cursor = MARGIN_X
        marks: list[dict[str, object]] = []
        labels: dict[str, str] = {}
        for block_no, (process, cells) in enumerate(blocks):
            if not cells:
                continue
            cols = allotted[process]
            xs: list[float] = []
            ys: list[float] = []
            for index, cell in enumerate(cells):
                row, col = divmod(index, cols)
                x = round(cursor + col * PITCH_X, 1)
                y = round(top_y - row * PITCH_Y, 1)
                xs.append(x)
                ys.append(y)
                place_cell(cell, key, x, y)
            right = max(xs) + UNIT_W
            if process == "Singulation" and overlap_unit is not None:
                ox, oy = round(cursor + (cols - 1) * PITCH_X + 3.0, 1), round(top_y, 1)
                overlap_unit.place = (key[0], key[1], ox, oy, UNIT_W, UNIT_H)
                right = max(right, ox + UNIT_W)
            zone_x, zone_y = cursor - 1.0, min(ys) - 1.0
            marks.append(
                {
                    "id": f"z-{meta_for(process).abbr}",
                    "kind": "zone",
                    "x": round(zone_x, 1),
                    "y": round(zone_y, 1),
                    "w": round(right - cursor + 2.0, 1),
                    "h": round(top_y + UNIT_H - min(ys) + 2.0, 1),
                    "label": process[:40],
                    "color": ZONE_COLORS[block_no % len(ZONE_COLORS)],
                    "borderStyle": "solid" if block_no % 2 else "dashed",
                    "labelAlign": "left",
                }
            )
            cursor = cursor + cols * PITCH_X + PITCH_X
        free_x = cursor
        fleet.free_cells[key] = [
            (round(free_x + c * PITCH_X, 1), round(top_y - r * PITCH_Y, 1))
            for r in range(rows_total)
            for c in range(RESERVE_COLUMNS)
            if free_x + c * PITCH_X + UNIT_W <= width - 1
        ]
        marks.append(
            {
                "id": "title",
                "kind": "text",
                "x": 3.0,
                "y": round(height - 7.5, 1),
                "w": 60.0,
                "h": 5.0,
                "label": FLOOR_TITLES.get(key, f"{key[0]} {key[1]}"),
                "fontSize": 13,
            }
        )
        for number, x in enumerate(range(70, int(width) - 10, 30), start=1):
            marks.append(
                {
                    "id": f"col-{number}",
                    "kind": "column",
                    "x": float(x),
                    "y": round(height - 7.0, 1),
                    "w": 1.5,
                    "h": 1.5,
                    "label": "",
                }
            )
        marks.append(
            {
                "id": "shutter-1",
                "kind": "shutter",
                "x": round(width - 16.0, 1),
                "y": 0.5,
                "w": 10.0,
                "h": 1.5,
                "label": "반입구",
            }
        )
        marks.append(
            {
                "id": "door-1",
                "kind": "door",
                "x": 0.5,
                "y": round(height / 2, 1),
                "w": 1.5,
                "h": 4.0,
                "label": "출입문",
            }
        )
        marks.append(
            {
                "id": "flow-1",
                "kind": "arrow",
                "x": 8.0,
                "y": 3.0,
                "w": min(60.0, width - 30),
                "h": 2.0,
                "label": "물류 동선",
            }
        )
        fleet.marks[key] = marks
        for unit in fleet.units:
            if unit.parent and unit.place and (unit.place[0], unit.place[1]) == key:
                labels.setdefault(unit.parent, "")
        positions = ("top", "bottom", "center")
        for number, parent in enumerate(sorted(labels)):
            labels[parent] = "top" if parent.startswith("DEMO-MLD") else positions[number % 3]
        if labels:
            fleet.group_labels[key] = labels


def place_cell(cell: list[Unit], key: tuple[str, str], x: float, y: float) -> None:
    if len(cell) == 1:
        cell[0].place = (key[0], key[1], x, y, UNIT_W, UNIT_H)
        return
    count = len(cell)
    cols = count if count <= 3 else math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    tile_w, tile_h = UNIT_W / cols, UNIT_H / rows
    for index, unit in enumerate(sorted(cell, key=lambda u: u.name)):
        row, col = divmod(index, cols)
        unit.place = (
            key[0],
            key[1],
            round(x + col * tile_w, 1),
            round(y + UNIT_H - (row + 1) * tile_h, 1),
            round(tile_w, 1),
            round(tile_h, 1),
        )


# ------------------------------------------------------------------ 표 만들기


def stage_status(arrival: date | None, qual: date | None, as_of: date) -> dict[str, object]:
    row: dict[str, object] = {
        "반입실적": pd.NaT,
        "Qual실적": pd.NaT,
        "반입상태": None,
        "Qual상태": None,
    }
    if arrival is not None:
        if arrival <= as_of:
            row["반입상태"] = "완료"
            row["반입실적"] = pd.Timestamp(arrival)
        else:
            row["반입상태"] = "확정" if (arrival - as_of).days <= 45 else "계획"
    if qual is not None:
        if arrival is not None and arrival <= as_of and qual <= as_of:
            row["Qual상태"] = "완료"
            row["Qual실적"] = pd.Timestamp(qual)
        elif arrival is not None and arrival <= as_of:
            row["Qual상태"] = "확정" if (qual - as_of).days <= 60 else "계획"
        else:
            row["Qual상태"] = (
                "확정" if row["반입상태"] == "확정" and (qual - as_of).days <= 75 else "계획"
            )
    return row


def ts(value: date | None) -> object:
    return pd.Timestamp(value) if value is not None else pd.NaT


def equipment_frame(fleet: Fleet, rev: str) -> pd.DataFrame:
    as_of = AS_OF[rev]
    rows: list[dict[str, object]] = []
    for unit in fleet.units:
        if REV_ORDER[unit.present_from] > REV_ORDER[rev]:
            continue
        qual = unit.qual_at(rev)
        row: dict[str, object] = dict.fromkeys(EQUIPMENT_COLUMNS)
        row.update(
            {
                "Area Code": unit.area_code,
                "공정대분류": meta_for(unit.process).large,
                "공정소분류": unit.process,
                "Maker": unit.maker,
                "Model": unit.model,
                "설비명": unit.name,
                "공정구분": meta_for(unit.process).line,
                "투자Capa": unit.invest_capa,
                "투자구분": unit.invest,
                "사용기준": unit.usage,
                "동": meta_for(unit.process).building,
                "층": meta_for(unit.process).floor,
                "담당자": unit.manager,
                "제진대일정": ts(unit.vib),
                "물류일정": ts(unit.logi),
                "반입일정": ts(unit.arrival),
                "Qual일정": ts(qual),
                "정지일정": ts(unit.stop),
                "반출/이설일정": ts(unit.relocation),
                "시나리오 메모": unit.scenario_memo_by_rev.get(rev),
                "반입/Qual 이력": unit.history_by_rev.get(rev, unit.history),
                "호기이력": unit.unit_history,
                "설비이력": unit.equipment_history,
                "보관유무": unit.storage,
                "기존설비여부": unit.existing_flag,
                "레이아웃표시": unit.layout_flag,
                "환산비": float(unit.ratio),
                "Main 설비": unit.parent,
                "메모1": unit.memo1,
                "메모2": unit.memo2,
                "메모3": None,
            }
        )
        if unit.place is not None and unit.placed:
            building, floor, x, y, w, h = unit.place
            row.update(
                {"동": building, "층": floor, "X좌표": x, "Y좌표": y, "Xsize": w, "Ysize": h}
            )
        if unit.existing_flag == "Y":
            row.update({"반입실적": pd.NaT, "Qual실적": pd.NaT, "반입상태": None, "Qual상태": None})
        elif unit.storage == "Y":
            row.update(
                {
                    "반입실적": ts(unit.arrival),
                    "반입상태": "완료",
                    "Qual실적": pd.NaT,
                    "Qual상태": None,
                }
            )
        else:
            row.update(stage_status(unit.arrival, qual, as_of))
            override = unit.qual_status_by_rev.get(rev)
            if override is not None:
                row["Qual상태"] = override
            if rev == "r3" and unit.confirm:
                apply_confirmation(row, unit.confirm)
        rows.append(row)
    frame = pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS))
    for column in (
        "제진대일정",
        "물류일정",
        "반입일정",
        "반입실적",
        "Qual일정",
        "Qual실적",
        "정지일정",
        "반출/이설일정",
    ):
        frame[column] = pd.to_datetime(frame[column])
    for column in ("X좌표", "Y좌표", "Xsize", "Ysize", "환산비"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    return frame


def downtime_frame(fleet: Fleet, rev: str, names: set[str]) -> pd.DataFrame:
    rows = [
        {
            "설비명": item.unit,
            "비가동유형": item.kind,
            "시작일": pd.Timestamp(item.start),
            "종료일": ts(item.end),
            "상세사유": item.reason,
            "비고": item.note,
        }
        for item in fleet.downtime
        if REV_ORDER[item.from_rev] <= REV_ORDER[rev] and item.unit in names
    ]
    frame = pd.DataFrame(rows, columns=list(DOWNTIME_COLUMNS))
    frame["시작일"] = pd.to_datetime(frame["시작일"])
    frame["종료일"] = pd.to_datetime(frame["종료일"])
    return frame


def baseline_frame(fleet: Fleet) -> pd.DataFrame:
    return pd.DataFrame(fleet.baseline, columns=["공정", "분류", "기존보유대수", "비고"])


def cutoff_frame(facts: SimFacts) -> pd.DataFrame:
    rows = [
        {"공정": p, "제품구분": "*", "Cutoff일수": float(cutoff), "비고": "DEMO 기준"}
        for p in facts.processes
        if p in META and (cutoff := META[p].cutoff) is not None
    ]
    return pd.DataFrame(rows, columns=["공정", "제품구분", "Cutoff일수", "비고"])


# ------------------------------------------------------------------ 계산(앱과 같은 길)


def plan_for(
    snapshot: EquipmentSnapshot,
    cutoff: pd.DataFrame,
    facts: SimFacts,
    *,
    today: date,
    months: Sequence[int],
    levels: Sequence[float] = (0.9, 1.0, 1.1, 1.2, 1.3),
    manual: Sequence[tuple[str, int, float]] = (),
) -> ShorteningPlan:
    baseline, equipment, downtime = snapshot.calculation_frames()
    return plan_required_shortening(
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        required_equipment=facts.required_rows,
        months=months,
        today=today,
        levels=levels,
        manual_downtime=manual,
    )


def provenance(
    repo: DuckDBEquipmentRepository,
    snapshot: EquipmentSnapshot,
    facts: SimFacts,
    scenario_name: str,
) -> BaselineProvenance:
    release = repo.latest_equipment_release()
    return BaselineProvenance(
        saved_by=SAVED_BY,
        equipment_revision_id=snapshot.revision.revision_id,
        equipment_revision_no=snapshot.revision.revision_no,
        scenario_id=facts.scenario_id,
        scenario_name=facts.scenario_name,
        scenario_revision_id=facts.revision_id,
        scenario_revision_no=facts.revision_no,
        equipment_schedule_revision_ref=snapshot.schedule.schedule_revision_id
        if snapshot.schedule
        else None,
        equipment_schedule_revision_no=snapshot.schedule.revision_no if snapshot.schedule else None,
        equipment_scenario_name=scenario_name,
        equipment_release_no=release.release_no if release else None,
    )


# ------------------------------------------------------------------ 쓰기


@dataclass
class Written:
    ops_id: str
    ops_revisions: dict[str, str] = field(default_factory=dict)
    setup_id: str = ""
    delay_id: str = ""
    log: list[str] = field(default_factory=list)


def scenario_by_name(repo: DuckDBEquipmentRepository, name: str) -> EquipmentScenarioSummary:
    return next(s for s in repo.list_equipment_scenarios() if s.scenario_name == name)


def save_ops(
    repo: DuckDBEquipmentRepository,
    fleet: Fleet,
    rev: str,
    written: Written,
    *,
    first: bool,
    note: str,
    name: str,
) -> None:
    equipment = equipment_frame(fleet, rev)
    names = set(equipment["설비명"].astype(str))
    ops = next(
        s for s in repo.list_equipment_scenarios() if s.equipment_scenario_id == written.ops_id
    )
    release = repo.latest_equipment_release()
    request = EquipmentSaveRequest(
        baseline=baseline_frame(fleet),
        equipment=equipment,
        downtime=downtime_frame(fleet, rev, names),
        equipment_scenario_id=written.ops_id,
        base_common_revision_id=EMPTY_REVISION_TOKEN
        if first
        else (repo.latest_revision_id() or EMPTY_REVISION_TOKEN),
        base_schedule_revision_id=None if first else ops.latest_schedule_revision_id,
        note=note,
        saved_by=SAVED_BY,
        propagate_new_units=rev == "r3",
        propagate_new_downtime=True,
        publish_official=True,
        expected_release_no=release.release_no if release else 0,
        floor_canvases=fleet.canvases if first else None,
        floor_marks=fleet.marks if first else None,
        floor_group_labels=fleet.group_labels if first else None,
    )
    result = repo.save_equipment(request)
    if result.schedule is None:
        raise RuntimeError(f"운영 일정 {rev} 저장이 일정 리비전을 만들지 않았습니다.")
    repo.rename_schedule_revision(
        result.schedule.schedule_revision_id, name=name, expected_name=None
    )
    written.ops_revisions[rev] = result.schedule.schedule_revision_id
    propagated = ", ".join(
        f"「{item.scenario_name}」 r{item.revision_no}(호기 {item.unit_count}·비가동 "
        f"{len(item.downtime)})"
        for item in result.propagated
        if item.revision_no is not None
    )
    written.log.append(
        f"운영 일정 r{result.schedule.revision_no} 「{name}」: 호기 {len(equipment)}행 · 비가동 "
        f"{len(request.downtime)} · "
        + (f"공통 r{result.common.revision_no}" if result.common else "공통 그대로")
        + (f" · 설비 공식 v{result.release_no}" if result.release_no else " · 발행 없음")
        + (f" · 새 호기 {len(result.new_units)}" if not first else "")
        + (f" · 함께 넣기 {propagated}" if propagated else "")
    )


def shift_schedule(frame: pd.DataFrame, names: Iterable[str], days: int, memo: str) -> None:
    mask = frame["설비명"].isin(list(names))
    for column in ("제진대일정", "물류일정", "반입일정", "Qual일정"):
        frame.loc[mask, column] = frame.loc[mask, column] + pd.Timedelta(days=days)
    frame.loc[mask, "시나리오 메모"] = memo


def write_all(
    repo: DuckDBEquipmentRepository, fleet: Fleet, facts: SimFacts, cutoff: pd.DataFrame
) -> Written:
    repo.initialize()
    scenarios = repo.list_equipment_scenarios()
    if len(scenarios) != 1:
        raise RuntimeError(
            f"초기화 뒤 설비 시나리오가 하나가 아닙니다: {[s.scenario_name for s in scenarios]}"
        )
    written = Written(ops_id=scenarios[0].equipment_scenario_id)
    written.log.append(
        f"초기화: 설비 시나리오 「{scenarios[0].scenario_name}」(id {written.ops_id})"
    )

    # 2. 운영 r1 「10월 2주 일정」 → 설비 공식 v1(층 캔버스·요소·묶음 이름표 함께).
    save_ops(
        repo, fleet, "r1", written, first=True, note="10월 2주 정기 갱신", name="10월 2주 일정"
    )
    # 3. 공정별 Cut-off.
    repo.save_process_cutoff(cutoff)
    written.log.append(
        f"Cut-off: {len(cutoff)}공정(Shipping Inspection 미기재) — 소수 TC Bonding 35.8 · Mold "
        "12.5 · AVI 20.8"
    )
    plan_months = [m for m in facts.months if FIRST_MONTH <= m <= 202712]
    ops_name = scenarios[0].scenario_name
    # 4. 기준선 ① — 10-13 의 공식 쌍.
    snapshot = repo.load_official_snapshot()
    assert snapshot is not None
    plan = plan_for(snapshot, cutoff, facts, today=AS_OF["r1"], months=plan_months)
    summary = repo.save_shortening_baseline(
        freeze_plan(
            plan, name="10월 2주 기준선", provenance=provenance(repo, snapshot, facts, ops_name)
        ),
        saved_at=datetime(2026, 10, 13, 8, 0),
    )
    written.log.append(
        f"기준선 ① 「{summary.name}」 · 오늘 {summary.plan_today} · 호기 줄 "
        f"{int(plan.at(1.1).units.shape[0])}(110%)"
    )
    # 5. 운영 r2 「10월 3주 일정」 → v2.
    save_ops(
        repo,
        fleet,
        "r2",
        written,
        first=False,
        note="10월 3주 정기 갱신 — 기준선 ① 요청 반영·실적 입력",
        name="10월 3주 일정",
    )
    # 6. 기준선 ②.
    snapshot = repo.load_official_snapshot()
    assert snapshot is not None
    plan = plan_for(snapshot, cutoff, facts, today=AS_OF["r2"], months=plan_months)
    summary = repo.save_shortening_baseline(
        freeze_plan(
            plan, name="10월 3주 기준선", provenance=provenance(repo, snapshot, facts, ops_name)
        ),
        saved_at=datetime(2026, 10, 20, 8, 0),
    )
    written.log.append(
        f"기준선 ② 「{summary.name}」 · 오늘 {summary.plan_today} · 호기 줄 "
        f"{int(plan.at(1.1).units.shape[0])}(110%)"
    )
    # 7. 가정 시나리오 둘(운영 r2 에서 복제).
    setup = repo.clone_equipment_scenario(
        written.ops_revisions["r2"], name="셋업 가속안", created_by=SAVED_BY
    )
    delay = repo.clone_equipment_scenario(
        written.ops_revisions["r2"], name="반입 지연 대비안", created_by=SAVED_BY
    )
    written.setup_id, written.delay_id = setup.equipment_scenario_id, delay.equipment_scenario_id
    written.log.append("복제: 「셋업 가속안」·「반입 지연 대비안」 ← 운영 일정 r2")
    # 8. 운영 r3 「11월 1주 일정」 → v3, 새 호기 3대 함께 넣기.
    save_ops(
        repo,
        fleet,
        "r3",
        written,
        first=False,
        note="11월 1주 정기 갱신 — 실적·지연·비가동·신규 3대",
        name="11월 1주 일정",
    )

    # 9. 셋업 가속안 r3 — Qual 당김 + 배치 차이(호기 4대 C2 3F · 영역 1).
    setup_now = scenario_by_name(repo, "셋업 가속안")
    common_id = repo.latest_revision_id()
    assert common_id is not None
    merged = repo.load_merged_snapshot(common_id, setup_now.latest_schedule_revision_id)
    frame = merged.equipment.loc[:, list(EQUIPMENT_COLUMNS)].copy()
    future = frame.loc[
        frame["공정소분류"].isin(["TC Bonding", "Ball Attach"])
        & frame["Main 설비"].isna()
        & frame["반입일정"].gt(pd.Timestamp(TODAY + timedelta(days=60)))
        & frame["정지일정"].isna()
        & frame["반출/이설일정"].isna()
    ].sort_values(["반입일정", "설비명"])
    pulled = []
    for process in ("TC Bonding", "Ball Attach"):
        pulled += future.loc[future["공정소분류"].eq(process), "설비명"].head(3).tolist()
    for number, name in enumerate(pulled):
        shift_schedule(frame, [name], -(15 + (number * 3) % 16), "셋업 인력 증원 — Qual 당김")
    movers = future.loc[future["공정소분류"].eq("TC Bonding"), "설비명"].tail(4).tolist()
    free = fleet.free_cells.get(("C2", "3F"), [])
    if len(free) < 4 or len(movers) < 4:
        raise RuntimeError(
            f"셋업 가속안 배치 차이를 만들 자리가 없습니다(빈칸 {len(free)} · 호기 {len(movers)})."
        )
    cells = [free[0], free[1], free[RESERVE_COLUMNS], free[RESERVE_COLUMNS + 1]]
    for name, (x, y) in zip(movers, cells, strict=True):
        mask = frame["설비명"].eq(name)
        frame.loc[mask, ["동", "층"]] = ["C2", "3F"]
        frame.loc[mask, ["X좌표", "Y좌표", "Xsize", "Ysize"]] = [x, y, UNIT_W, UNIT_H]
        frame.loc[mask, "시나리오 메모"] = "임시 셋업 구역(가정)으로 이동"
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    zone = {
        "id": "z-setup-temp",
        "kind": "zone",
        "x": round(min(xs) - 1.0, 1),
        "y": round(min(ys) - 1.0, 1),
        "w": round(max(xs) - min(xs) + UNIT_W + 2.0, 1),
        "h": round(max(ys) - min(ys) + UNIT_H + 2.0, 1),
        "label": "임시 셋업 구역(가정)",
        "color": "violet",
        "borderStyle": "dashed",
        "labelAlign": "left",
    }
    result = repo.save_equipment(
        EquipmentSaveRequest(
            baseline=merged.baseline,
            equipment=frame,
            downtime=merged.downtime.loc[:, list(DOWNTIME_COLUMNS)],
            equipment_scenario_id=setup_now.equipment_scenario_id,
            base_common_revision_id=common_id,
            base_schedule_revision_id=setup_now.latest_schedule_revision_id,
            note="셋업 인력 증원 가정 — Qual 당김·임시 셋업 구역",
            saved_by=SAVED_BY,
            propagate_new_units=False,
            propagate_new_downtime=False,
            publish_official=False,
            floor_marks={("C2", "3F"): [*fleet.marks[("C2", "3F")], zone]},
            expected_layout_role="overlay",
        )
    )
    if result.schedule is None:
        raise RuntimeError("셋업 가속안 r3 이 만들어지지 않았습니다.")
    repo.rename_schedule_revision(
        result.schedule.schedule_revision_id, name="셋업 인력 증원 가정", expected_name=None
    )
    written.log.append(
        f"셋업 가속안 r{result.schedule.revision_no} 「셋업 인력 증원 가정」: Qual 당김 "
        f"{len(pulled)}대 · 배치 차이 호기 "
        f"{result.layout_overlay_units} · 요소 {result.layout_overlay_marks} · 공통 "
        + ("새로 씀(!)" if result.common is not None else "그대로")
    )

    # 10. 반입 지연 대비안 r3(지연 + 위치 차이 1) → r4 배치 차이 정리 → r5 되돌리기(r2).
    delay_now = scenario_by_name(repo, "반입 지연 대비안")
    common_id = repo.latest_revision_id()
    assert common_id is not None
    merged = repo.load_merged_snapshot(common_id, delay_now.latest_schedule_revision_id)
    frame = merged.equipment.loc[:, list(EQUIPMENT_COLUMNS)].copy()
    later = frame.loc[
        frame["반입일정"].gt(pd.Timestamp(TODAY + timedelta(days=14)))
        & frame["Main 설비"].isna()
        & frame["정지일정"].isna()
        & frame["반출/이설일정"].isna()
    ].sort_values(["반입일정", "설비명"])
    delayed = later["설비명"].head(8).tolist()
    shift_schedule(frame, delayed, 45, "반입 2개월 지연 가정")
    ball = frame.loc[
        frame["공정소분류"].eq("Ball Attach") & frame["X좌표"].notna() & frame["Main 설비"].isna(),
        "설비명",
    ].tolist()
    free = fleet.free_cells.get(("C3", "1F"), [])
    if not ball or not free:
        raise RuntimeError("반입 지연 대비안 위치 차이를 만들 자리가 없습니다.")
    moved = ball[-1]
    mask = frame["설비명"].eq(moved)
    frame.loc[mask, ["X좌표", "Y좌표"]] = [free[0][0], free[0][1]]
    result = repo.save_equipment(
        EquipmentSaveRequest(
            baseline=merged.baseline,
            equipment=frame,
            downtime=merged.downtime.loc[:, list(DOWNTIME_COLUMNS)],
            equipment_scenario_id=delay_now.equipment_scenario_id,
            base_common_revision_id=common_id,
            base_schedule_revision_id=delay_now.latest_schedule_revision_id,
            note="반입 2개월 지연 가정",
            saved_by=SAVED_BY,
            propagate_new_units=False,
            propagate_new_downtime=False,
            publish_official=False,
            expected_layout_role="overlay",
        )
    )
    if result.schedule is None:
        raise RuntimeError("반입 지연 대비안 r3 이 만들어지지 않았습니다.")
    r3_id = result.schedule.schedule_revision_id
    repo.rename_schedule_revision(r3_id, name="반입 2개월 지연 가정", expected_name=None)
    written.log.append(
        f"반입 지연 대비안 r{result.schedule.revision_no} 「반입 2개월 지연 가정」: 지연 "
        f"{len(delayed)}대 · 위치 차이 호기 {result.layout_overlay_units}"
    )
    cleared = repo.clear_layout_overlay(
        delay_now.equipment_scenario_id,
        expected_latest_schedule_revision_id=r3_id,
        saved_by=SAVED_BY,
        note="가정 배치 정리",
    )
    if cleared is None:
        raise RuntimeError("배치 차이 정리 리비전이 만들어지지 않았습니다.")
    delay_revs = repo.list_schedule_revisions(delay_now.equipment_scenario_id)
    r2 = next(r for r in delay_revs if r.revision_no == 2)
    restored = repo.restore_schedule_revision(
        r2.schedule_revision_id,
        expected_common_revision_id=common_id,
        expected_latest_schedule_revision_id=cleared.schedule_revision_id,
        saved_by=SAVED_BY,
        note="지연 가정 취소",
        revision_name="지연 가정 되돌림",
        publish_official=False,
    )
    written.log.append(
        f"반입 지연 대비안 r{cleared.revision_no}(배치 차이 정리) · r"
        + (str(restored.schedule.revision_no) if restored.schedule else "?")
        + " 「지연 가정 되돌림」(r2 로)"
    )

    # 11. 표준 목표 주차별 가용(26-W40~27-W26) — Burn-In·AVI 27-W10~13 비움, Packing 없음.
    weeks = []
    monday = date.fromisocalendar(2026, 40, 1)
    while monday <= date.fromisocalendar(2027, 26, 1):
        weeks.append(monday)
        monday += timedelta(days=7)
    rows = []
    for process in facts.processes:
        if process == "Packing":
            continue
        for monday in weeks:
            label = weeknum_label(monday)
            if process in ("Burn-In", "AVI") and label in ("27-W10", "27-W11", "27-W12", "27-W13"):
                continue
            month = max(owning_month(monday), facts.months[0])
            value = facts.available.get((process, month))
            if value is None:
                continue
            rows.append({"공정": process, "Weeknum": label, "가용대수": float(value)})
    saved = repo.save_standard_target_availability(
        pd.DataFrame(rows, columns=["공정", "Weeknum", "가용대수"])
    )
    written.log.append(
        f"표준 목표 주차 가용: {len(saved)}행 · {saved['공정'].nunique()}공정 · "
        f"{saved['Weeknum'].nunique()}주"
    )

    # 12. 입력 비가동(Post Mold Cure 는 가용보다 크게 → ⚠).
    pmc = facts.available.get(("Post Mold Cure", 202705), 0.0)
    cells_in = manual_cells(facts)
    version = repo.save_manual_downtime(
        cells_in,
        processes=list(facts.processes),
        months=list(facts.months),
        expected_version=None,
        saved_by=SAVED_BY,
        note="정기 PM·금형 교체 반영",
    )
    written.log.append(
        f"입력 비가동: 칸 {len(cells_in)} · version {version} (Post Mold Cure 27.05 = "
        f"{cells_in[('Post Mold Cure', 202705)]:g} > 공식 가용 {pmc:g})"
    )

    # 13. 필요 단축 일정 공용 조회 조건.
    repo.save_shortening_filter_months(FIRST_MONTH, 202712, source=SOURCE)
    chosen = fleet.filter_processes(facts.processes)
    repo.save_shortening_filter_processes(chosen, visible=list(facts.processes), source=SOURCE)
    written.log.append(f"공용 조회 조건: 202611–202712 · 공정 {len(chosen)}: {', '.join(chosen)}")
    # 14. 층 사용 상태.
    repo.save_floor_states(FLOOR_STATES, expected_version=None, source="DEMO 시설 담당")
    written.log.append("층 사용: C5 1F·C5 6F 비활성")
    return written


# ------------------------------------------------------------------ 점검


@dataclass(frozen=True)
class Pair:
    process: str
    product: str
    start: int
    end: int
    story: str
    mod_days: int | None = 30


def pick_product(facts: SimFacts, wanted: str, process: str, *, smallest: bool = False) -> str:
    rows = facts.required_rows
    in_process = rows.loc[
        rows["공정"].astype("string").str.strip().eq(process).fillna(False).to_numpy()
    ]
    totals = (
        pd.DataFrame(
            {
                "p": in_process["제품정보"].astype("string").str.strip().to_numpy(),
                "v": pd.to_numeric(in_process["소요대수"]).to_numpy(),
            }
        )
        .groupby("p")["v"]
        .sum()
    )
    totals = totals.loc[totals > 0]
    if wanted in totals.index:
        return wanted
    if totals.empty:
        return wanted
    return str(totals.sort_values().index[0 if smallest else -1])


def checks(
    repo: DuckDBEquipmentRepository, fleet: Fleet, facts: SimFacts, written: Written
) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    failures: list[str] = []

    def check(ok: bool, text: str) -> None:
        lines.append(("✓ " if ok else "✗ ") + text)
        if not ok:
            failures.append(text)

    scenarios = {s.scenario_name: s for s in repo.list_equipment_scenarios()}
    check(len(scenarios) == 3, f"설비 시나리오 {len(scenarios)}개: {', '.join(scenarios)}")
    origins: dict[str, list[str]] = {}
    for name, summary in scenarios.items():
        revisions = repo.list_schedule_revisions(summary.equipment_scenario_id)
        origins[name] = [r.origin for r in sorted(revisions, key=lambda r: r.revision_no)]
        names = " · ".join(
            f"r{r.revision_no} {r.origin}" + (f" 「{r.revision_name}」" if r.revision_name else "")
            for r in sorted(revisions, key=lambda r: r.revision_no)
        )
        lines.append(f"   {name}: {names}")
    counts = [len(origins.get(n, [])) for n in ("운영 일정", "셋업 가속안", "반입 지연 대비안")]
    check(counts == [3, 3, 5], f"리비전 수 운영·셋업·지연 = {counts}")
    check(
        set(origins.get("운영 일정", [])) == {"save"},
        f"운영 출처 {sorted(set(origins.get('운영 일정', [])))}",
    )
    check(
        set(origins.get("셋업 가속안", [])) == {"clone", "propagate", "save"},
        f"셋업 출처 {sorted(set(origins.get('셋업 가속안', [])))}",
    )
    check(
        set(origins.get("반입 지연 대비안", []))
        == {"clone", "propagate", "save", "layout_clear", "restore"},
        f"지연 출처 {sorted(set(origins.get('반입 지연 대비안', [])))}",
    )
    release = repo.latest_equipment_release()
    ops = scenarios.get("운영 일정")
    check(
        release is not None
        and ops is not None
        and release.release_no == 3
        and release.schedule_revision_id == ops.latest_schedule_revision_id,
        f"설비 공식 v{release.release_no if release else '?'} = 운영 일정 "
        f"r{release.revision_no if release else '?'}",
    )
    setup = scenarios.get("셋업 가속안")
    if setup is not None:
        check(
            setup.latest_layout_rows[0] == 4 and setup.latest_layout_rows[1] == 1,
            f"셋업 가속안 최신 배치 차이(호기·요소·이름표) = {setup.latest_layout_rows}",
        )
        common_id = repo.latest_revision_id() or ""
        preview = repo.preview_layout_publish(
            setup.latest_schedule_revision_id or "",
            common_revision_id=common_id,
            newest_schedule_revision_id=setup.latest_schedule_revision_id,
        )
        check(
            preview.action == "blocked",
            f"셋업 가속안 공식 발행 판정 = {preview.action}(실효 호기 {preview.units} · 요소 "
            f"{preview.marks})",
        )

    official = repo.load_official_snapshot()
    assert official is not None
    cutoff = repo.load_process_cutoff()
    manual = repo.load_manual_downtime()
    months = list(facts.months)
    plan = plan_for(
        official,
        cutoff,
        facts,
        today=TODAY,
        months=months,
        levels=(1.1,),
        manual=manual_downtime_key(manual.rows, months),
    )
    level = plan.at(1.1)
    pm = level.process_months
    statuses = pm.loc[pm["상태"].ne(STATUS_MET)] if "상태" in pm.columns else pm.iloc[0:0]
    card_processes = sorted(set(statuses["공정"].astype(str)))
    status_kinds = Counter(statuses["상태"].astype(str))
    virtual = (
        int(level.units.loc[level.units["구분"].eq(KIND_NEW)].shape[0])
        if not level.units.empty
        else 0
    )
    check(
        6 <= len(card_processes) <= 10,
        f"110% 단축 카드 공정 {len(card_processes)}: {', '.join(card_processes)}",
    )
    check(
        len(status_kinds) >= 4,
        f"상태 {len(status_kinds)}종: "
        + ", ".join(f"{k} {v}" for k, v in status_kinds.most_common()),
    )
    check(
        status_kinds.get(STATUS_EXPIRED, 0) >= 1,
        f"기한 지남 {status_kinds.get(STATUS_EXPIRED, 0)}칸",
    )
    check(virtual >= 1, f"추가N(가상 호기) {virtual}대")
    in_filter = fleet.filter_processes(facts.processes)
    window = statuses.loc[
        statuses["생산계획년월"].between(FIRST_MONTH, 202712) & statuses["공정"].isin(in_filter)
    ]
    lines.append(
        f"   공용 조회 조건(26.11–27.12 · {len(in_filter)}공정) 안의 카드 공정 "
        f"{window['공정'].nunique()}: "
        + ", ".join(sorted(set(window["공정"].astype(str))))
        + " · 상태 "
        + ", ".join(f"{k} {v}" for k, v in Counter(window["상태"].astype(str)).most_common())
    )
    lines.append(
        f"   맞대지 못한 공정: 소요에만 {list(plan.required_only)} · Cut-off 미기재 "
        f"{list(plan.missing_cutoff)} · 가용에만 {list(plan.availability_only)}"
    )

    readiness: Counter[str] = Counter()
    by_status: dict[str, list[str]] = defaultdict(list)
    for process in facts.processes:
        state = dynamic_readiness(official.equipment, official.baseline, cutoff, process=process)
        readiness[state.status] += 1
        by_status[state.status].append(process)
    other_statuses = {
        status: names
        for status, names in by_status.items()
        if status not in (READY, MISSING_CUTOFF, NO_COUNTED_UNITS)
    }
    check(
        readiness[READY] == len(facts.processes) - 2
        and by_status[MISSING_CUTOFF] == ["Shipping Inspection"]
        and by_status[NO_COUNTED_UNITS] == ["Tape Pocket Inspection"],
        f"공정 Capa 상세 판정 READY {readiness[READY]} · Cut-off 미기재 "
        f"{by_status[MISSING_CUTOFF]} · 셀 호기 없음 {by_status[NO_COUNTED_UNITS]}"
        + (f" · 그 밖 {other_statuses}" if other_statuses else ""),
    )

    # 설비 일정 가용 vs 공식 가용(27.01~, 입력 비가동 빼기 전 — 일정 자체).
    raw = (
        plan_for(official, cutoff, facts, today=TODAY, months=months, levels=(1.1,))
        .at(1.1)
        .process_months
    )
    within = 0
    compared = 0
    worst: list[str] = []
    for process in plan.processes:
        rows = raw.loc[raw["공정"].eq(process) & raw["생산계획년월"].ge(202701)]
        ratios = []
        for month, value in zip(rows["생산계획년월"], rows["가용대수"], strict=True):
            official_value = facts.available.get((process, int(month)))
            if official_value:
                ratios.append(float(value) / official_value)
        if not ratios:
            continue
        compared += 1
        middle = sorted(ratios)[len(ratios) // 2]
        if abs(middle - 1) <= 0.10:
            within += 1
        else:
            worst.append(f"{process} {middle * 100:.0f}%")
    check(
        compared > 0 and within >= math.ceil(compared * 0.8),
        f"설비 일정 가용 ÷ 공식 가용(27.01~ 중앙값) ±10% 안 {within}/{compared}"
        + (f" · 밖 {', '.join(worst)}" if worst else ""),
    )

    # 판정 대조 넷(기준 = 공식 확보율, 일정 = 설비 일정 확보율, 목표 110%·월별 예외).
    thresholds = facts.thresholds
    combos: Counter[str] = Counter()
    for process, month, required, available in zip(
        raw["공정"], raw["생산계획년월"], raw["소요대수"], raw["가용대수"], strict=True
    ):
        required = float(required)
        if required <= 0:
            continue
        target = float(thresholds.secure_for(int(month)))
        official_ok = (
            facts.available.get((str(process), int(month)), 0.0) / required >= target - 1e-9
        )
        schedule_ok = float(available) / required >= target - 1e-9
        combos[
            ("기준✓" if official_ok else "기준✕") + "·" + ("일정✓" if schedule_ok else "일정✕")
        ] += 1
    check(
        all(
            combos.get(k, 0) >= 1
            for k in ("기준✓·일정✓", "기준✓·일정✕", "기준✕·일정✓", "기준✕·일정✕")
        ),
        "판정 대조 " + " · ".join(f"{k} {v}" for k, v in sorted(combos.items())),
    )

    rows_total = len(official.equipment)
    check(
        rows_total < 1000,
        f"호기 행 {rows_total}(공식 쌍) · 기존보유 행 {len(official.baseline)} · 비가동 "
        f"{len(official.downtime)}",
    )
    status = build_space_equipment_status(official.equipment, official.downtime, as_of=TODAY)
    overlaps = overlap_counts_touching(status, status["설비명"].astype(str).tolist())
    check(sum(overlaps.values()) == 1, f"겹침 {sum(overlaps.values())}쌍 {overlaps}")
    marks = {key: repo.load_floor_layout_marks(*key) for key in fleet.canvases}
    blocked = layout_warnings(status, marks).blocked
    check(not blocked, "도면 요소를 덮은 호기 없음" + (f" — {blocked[:3]}" if blocked else ""))
    canvases = repo.load_floor_layout_canvases()
    lines.append(
        f"   층 캔버스 {len(canvases)}: "
        + ", ".join(f"{b} {f} {w:g}×{h:g}" for (b, f), (w, h) in sorted(canvases.items()))
        + f" · 도면 요소 {sum(len(v) for v in marks.values())}("
        + ", ".join(
            f"{k} {v}" for k, v in Counter(m.kind for v in marks.values() for m in v).most_common()
        )
        + ")"
        + " · Main 설비명 위치 "
        f"{sum(len(repo.load_floor_group_labels(*key)) for key in fleet.canvases)}"
    )
    placed = official.equipment.loc[official.equipment["X좌표"].notna()]
    floors = sorted({(str(b), str(f)) for b, f in zip(placed["동"], placed["층"], strict=True)})
    lines.append(
        f"   호기가 놓인 층 {len(floors)}: {', '.join(f'{b} {f}' for b, f in floors)} · "
        f"레이아웃표시 N {int(official.equipment['레이아웃표시'].eq('N').sum())}"
    )
    groups = official.equipment["Main 설비"].dropna().astype(str)
    lines.append(
        f"   모듈 묶음 {groups.nunique()}개({', '.join(sorted(groups.unique()))}) · 모듈 행 "
        f"{len(groups)}"
    )
    usage = official.equipment["사용기준"].fillna("(빈칸)").astype(str).value_counts().to_dict()
    ratio_counts = official.equipment["환산비"].astype(float).value_counts().to_dict()
    lines.append(f"   사용기준 {usage} · 환산비 {ratio_counts}")
    lines.append(f"   공정구분 {official.equipment['공정구분'].value_counts().to_dict()}")
    when = status["상태"].value_counts().to_dict()
    lines.append(f"   상태(오늘 {TODAY}) {when}")
    qual_states = official.equipment["Qual상태"].fillna("(빈칸)").value_counts().to_dict()
    lines.append(f"   Qual상태 {qual_states}")
    kinds = Counter((u.process, u.kind) for u in fleet.units)
    tcb_new = sum(
        1 for u in fleet.units if u.process == "TC Bonding" and u.kind == "new" and u.parent is None
    ) + len({u.parent for u in fleet.units if u.process == "TC Bonding" and u.parent})
    tcb_down = sum(
        1
        for d in fleet.downtime
        if any(u.name == d.unit and u.process == "TC Bonding" for u in fleet.units)
    )
    check(
        tcb_new >= 30 and tcb_down >= 30,
        f"TC Bonding 신규 {tcb_new}대(모듈 묶음은 1대) · 비가동 {tcb_down}건",
    )
    lines.append(
        "   공정별 호기(기존·신규·그 밖): "
        + " · ".join(
            f"{meta_for(p).abbr} {kinds[(p, 'existing')]}/{kinds[(p, 'new')]}/{kinds[(p, 'extra')]}"
            for p in facts.processes
        )
    )
    issues = schedule_confirmation_issues(official.equipment, today=TODAY)
    confirm_counts = confirmation_counts(issues)
    unconfirmed = issues.loc[issues["확인구분"].eq(UNCONFIRMED)]
    by_stage = {
        stage: int(group["설비키"].nunique()) for stage, group in unconfirmed.groupby("단계")
    }
    flagged = flagged_equipment(issues)
    placed_flagged = int(
        official.equipment.loc[official.equipment["설비명"].isin(flagged), "X좌표"].notna().sum()
    )
    check(
        confirm_counts[UNCONFIRMED] >= 4
        and by_stage.get("반입", 0) >= 2
        and by_stage.get("Qual", 0) >= 2
        and confirm_counts[MISSING_ACTUAL] >= 2
        and confirm_counts[STATUS_UPDATE_NEEDED] >= 2
        and placed_flagged >= 1,
        "일정 확인(오늘 "
        + str(TODAY)
        + ") "
        + " · ".join(f"{k} {v}대" for k, v in confirm_counts.items())
        + f" · 미확인 단계 {by_stage} · 도면의 「!」 {placed_flagged}대",
    )
    lines.append("   " + (schedule_confirmation_notice(issues) or "(미확인 안내 없음)"))
    modules = official.equipment.loc[official.equipment["Main 설비"].notna()]
    group_sizes = modules.groupby("Main 설비")["설비명"].count().to_dict()
    unplaced_groups = sorted(modules.loc[modules["X좌표"].isna(), "Main 설비"].astype(str).unique())
    hidden_modules = sorted(modules.loc[modules["레이아웃표시"].eq("N"), "설비명"].astype(str))
    check(
        {2, 3, 4} <= set(group_sizes.values())
        and len(unplaced_groups) == 1
        and len(hidden_modules) == 1,
        f"모듈 묶음 크기 {group_sizes} · 미배치 묶음 {unplaced_groups} · 숨은 모듈 "
        f"{hidden_modules}",
    )
    baselines = repo.list_shortening_baselines()
    check(
        len(baselines) == 2,
        f"기준선 {len(baselines)}: "
        + ", ".join(f"{b.name}({b.saved_at:%m-%d})" for b in baselines),
    )
    return lines, failures


def run_pair(
    pair: Pair,
    facts: SimFacts,
    process_months: pd.DataFrame,
    cutoff_days: Mapping[str, int],
    target: SecurementThresholds,
    months: list[int],
) -> ConstraintResult:
    table = build_process_product_demand(
        facts.required_rows, process=pair.process, split="제품정보", months=months, limit=10_000
    )
    inputs = constraint_month_inputs(
        process_months,
        table,
        process=pair.process,
        product=pair.product,
        months=months,
        general_target=lambda month: float(target.secure_for(month)),
    )
    return simulate_constraint(
        inputs,
        ConstraintConditions(
            period_start=pair.start,
            period_end=pair.end,
            constraint_target=1.2,
            modification_days=pair.mod_days,
            cutoff_days=int(cutoff_days[pair.process]),
        ),
    )


def all_pass_pair(
    facts: SimFacts,
    process_months: pd.DataFrame,
    cutoff_days: Mapping[str, int],
    target: SecurementThresholds,
    months: list[int],
) -> Pair:
    """제약 기간 내내 충족하고 기준 미달이 하나도 없는 조합 — 여유 큰 공정 · 작은 제품부터 "
    "찾는다."""
    rows = facts.required_rows
    scores = []
    for process in cutoff_days:
        if process in CARRIED_EXCLUDED:
            continue
        part = process_months.loc[process_months["공정"].eq(process)]
        if part.empty:
            continue
        scores.append(
            (
                float((part["가용대수"] / part["소요대수"].where(part["소요대수"] > 0)).min()),
                process,
            )
        )
    for _score, process in sorted(scores, reverse=True)[:8]:
        in_process = rows.loc[
            rows["공정"].astype("string").str.strip().eq(process).fillna(False).to_numpy()
        ]
        totals = (
            pd.DataFrame(
                {
                    "p": in_process["제품정보"].astype("string").str.strip().to_numpy(),
                    "v": pd.to_numeric(in_process["소요대수"]).to_numpy(),
                }
            )
            .groupby("p")["v"]
            .sum()
        )
        for product in totals.loc[totals > 0].sort_values().index[:4]:
            pair = Pair(
                process, str(product), 202706, 202712, "넉넉한 공정 + 작은 제품 — 모두 통과"
            )
            try:
                k = run_pair(pair, facts, process_months, cutoff_days, target, months).kpis
            except (KeyError, ValueError):
                continue
            if (
                k.constrained_months >= 7
                and k.constrained_met_months == k.constrained_months
                and not k.below_months
            ):
                return pair
    return Pair(
        "Wafer Incoming Inspection",
        pick_product(facts, "DEMO-H8S", "Wafer Incoming Inspection", smallest=True),
        202706,
        202712,
        "넉넉한 공정 + 작은 제품",
    )


def impact_pair(
    facts: SimFacts,
    process_months: pd.DataFrame,
    cutoff_days: Mapping[str, int],
    target: SecurementThresholds,
    months: list[int],
) -> Pair | None:
    """참고 조합 — 제약을 걸면 기존 제품에 「새로 미달」 이 가장 많이 생기는 조합(큰 제품부터)."""
    rows = facts.required_rows
    best: tuple[int, str, str] | None = None
    for process in cutoff_days:
        in_process = rows.loc[
            rows["공정"].astype("string").str.strip().eq(process).fillna(False).to_numpy()
        ]
        totals = (
            pd.DataFrame(
                {
                    "p": in_process["제품정보"].astype("string").str.strip().to_numpy(),
                    "v": pd.to_numeric(in_process["소요대수"]).to_numpy(),
                }
            )
            .groupby("p")["v"]
            .sum()
        )
        for product in totals.loc[totals > 0].sort_values(ascending=False).index[:3]:
            pair = Pair(process, str(product), 202706, 202712, "")
            try:
                k = run_pair(pair, facts, process_months, cutoff_days, target, months).kpis
            except (KeyError, ValueError):
                continue
            score = len(k.newly_below_months)
            if score and (best is None or score > best[0]):
                best = (score, process, str(product))
    if best is None:
        return None
    return Pair(
        best[1],
        best[2],
        202706,
        202712,
        "참고 — 제약을 걸면 기존 제품에 새로 미달이 가장 많이 생기는 조합",
    )


def constraint_lines(repo: DuckDBEquipmentRepository, facts: SimFacts) -> list[str]:
    official = repo.load_official_snapshot()
    assert official is not None
    cutoff = repo.load_process_cutoff()
    manual = repo.load_manual_downtime()
    months = list(facts.months)
    target = facts.thresholds
    plan = plan_for(
        official,
        cutoff,
        facts,
        today=TODAY,
        months=months,
        levels=(1.1,),
        manual=manual_downtime_key(manual.rows, months),
    )
    process_months = plan.at(1.1).process_months
    cutoff_days = plan.cutoff_days
    pairs = [
        Pair(
            "TC Bonding",
            pick_product(facts, "DEMO-H16A", "TC Bonding"),
            202706,
            202712,
            "신제품 램프 — 1대 전용이 큰 공정",
        ),
        Pair(
            "Wafer Saw",
            pick_product(facts, "DEMO-E4", "Wafer Saw"),
            202706,
            202712,
            "EDP 제품을 빠듯한 공정에서 떼기",
        ),
        Pair(
            "Underfill",
            pick_product(facts, "DEMO-H12B", "Underfill"),
            202706,
            202712,
            "경고 경계 공정(27.05) 뒤 기간",
        ),
        Pair(
            "TC Bonding",
            pick_product(facts, "DEMO-H16A", "TC Bonding"),
            202706,
            202712,
            "견주기 — 같은 조합에서 개조만 끔",
            None,
        ),
    ]
    pairs.append(all_pass_pair(facts, process_months, cutoff_days, target, months))
    impact = impact_pair(facts, process_months, dict(cutoff_days), target, months)
    if impact is not None:
        pairs.append(impact)
    lines = [
        "제약 시뮬레이션 추천 조합(실행 관리 › 제약 시뮬레이션, 제약 확보율 120% · 기준 HOME · "
        "설비 시나리오 공식):",
    ]
    for number, pair in enumerate(pairs, start=1):
        if pair.process not in cutoff_days:
            lines.append(
                f"  {number}. {pair.process} · {pair.product} — Cut-off·설비 맞댐이 없어 건너뜀"
            )
            continue
        try:
            result = run_pair(pair, facts, process_months, dict(cutoff_days), target, months)
        except (KeyError, ValueError) as exc:
            lines.append(f"  {number}. {pair.process} · {pair.product} — 계산 못 함: {exc}")
            continue
        k = result.kpis
        lines.append(
            f"  {number}. {pair.process} · {pair.product} · "
            f"{month_text(pair.start)}–{month_text(pair.end)} · "
            + (f"개조 켬 {pair.mod_days}일" if pair.mod_days is not None else "개조 끔")
            + f" — 제약 충족 {k.constrained_met_months}/{k.constrained_months}달 · 기존 최저 "
            f"{pct(k.lowest_existing_rate)}"
            + (f"({month_text(k.lowest_existing_month)})" if k.lowest_existing_month else "")
            + f" · 기준 미달 {len(k.below_months)}달(새로 {len(k.newly_below_months)})"
            + (f" · 개조 {k.max_dedicated}대" if k.max_dedicated is not None else "")
            + f" — {pair.story}"
        )
    return lines


# ------------------------------------------------------------------ 진입


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="데이터 폴더(그 안에 equipment_availability.duckdb) 또는 .duckdb 경로",
    )
    parser.add_argument(
        "--sim",
        type=Path,
        help="시뮬레이션 DB(읽기만 — 사본을 떠서 읽는다). 기본: 같은 폴더의 capa_simulation.duckdb",
    )
    parser.add_argument(
        "--replace", action="store_true", help="산출 DB 가 있으면 지우고 새로 만든다"
    )
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    # pandas 의 앞으로 바뀔 동작 알림 — 이 생성기의 계산과 무관하고 기록을 덮는다.
    warnings.filterwarnings("ignore", category=FutureWarning)

    out = args.out.expanduser()
    if out.suffix != ".duckdb":
        out = out / "equipment_availability.duckdb"
    sim = (args.sim or out.with_name("capa_simulation.duckdb")).expanduser()
    for place in (out, out.parent.parent / LOG_NAME):
        refusal = story.refuse_place(place)
        if refusal is not None:
            sys.stderr.write("멈춤 — " + refusal + "\n")
            return 2
    if not sim.is_file():
        sys.stderr.write(f"시뮬레이션 DB 가 없습니다: {sim}\n")
        return 2
    if out.resolve() == sim.resolve():
        sys.stderr.write("산출 DB 와 시뮬레이션 DB 가 같은 파일입니다.\n")
        return 2
    stale = [out, out.with_name(out.name + ".wal")]
    if any(p.exists() for p in stale):
        if not args.replace:
            sys.stderr.write(f"이미 있는 산출 DB 는 --replace 일 때만 지웁니다: {out}\n")
            return 2
        for p in stale:
            p.unlink(missing_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    log_path = out.parent.parent / LOG_NAME
    if datetime.now().date() < TODAY:
        sys.stderr.write(f"오늘이 {TODAY} 보다 일러 실적 검사에 걸립니다 — 돌리지 않습니다.\n")
        return 2

    with tempfile.TemporaryDirectory(prefix="review_sample_equip_") as folder:
        copy = Path(folder) / "capa_simulation.duckdb"
        shutil.copy2(sim, copy)
        wal = sim.with_name(sim.name + ".wal")
        if wal.exists():
            shutil.copy2(wal, copy.with_name(copy.name + ".wal"))
        facts = read_sim(copy)
    print(
        f"소요·가용: 공식 v{facts.release_no} 「{facts.release_name}」(「{facts.scenario_name}」 "
        f"r{facts.revision_no}) · "
        f"{len(facts.processes)}공정 · "
        f"{month_text(facts.months[0])}–{month_text(facts.months[-1])} {len(facts.months)}달 · "
        f"제품 {len(facts.products)} · EDP 경로 공정 {len(facts.edp_processes)}"
    )
    fleet = design_fleet(facts)
    layout_fleet(fleet, facts)
    confirm_lines = [f"일정 확인 사례 — {line}" for line in confirmation_story(fleet)]
    print("\n".join(confirm_lines))
    print(
        f"설계: 호기 {len(fleet.units)}행(r3) · 기존보유 행 {len(fleet.baseline)} · 비가동 "
        f"{len(fleet.downtime)} · 층 {len(fleet.canvases)}"
    )
    for note in fleet.notes:
        print(f"  주의: {note}")

    repo = DuckDBEquipmentRepository(out)
    written = write_all(repo, fleet, facts, cutoff_frame(facts))
    for line in written.log:
        print(line)
    lines, failures = checks(repo, fleet, facts, written)
    print("\n".join(lines))
    pair_lines = constraint_lines(repo, facts)
    print("\n".join(pair_lines))
    size = out.stat().st_size / 1e6
    wal = out.with_name(out.name + ".wal")
    body = [
        f"만든 때 {datetime.now():%Y-%m-%d %H:%M} · 산출 {out} ({size:.1f}MB"
        + (", .wal 남음" if wal.exists() else "")
        + ")",
        f"원천 시뮬레이션 DB {sim} — 공식 v{facts.release_no} 「{facts.release_name}」",
        *written.log,
        *confirm_lines,
        "점검:",
        *lines,
        *pair_lines,
        *(f"주의: {note}" for note in fleet.notes),
        "결과: "
        + ("통과" if not failures else f"어긋남 {len(failures)} — " + " / ".join(failures)),
    ]
    text = "\n".join([LOG_BEGIN, *body, LOG_END]) + "\n"
    log_path.write_text(text, encoding="utf-8")
    print(
        f"빌드 기록: {log_path} · 산출 {out} ({size:.1f}MB)"
        + (" · .wal 남음" if wal.exists() else "")
    )
    if failures:
        print(f"점검 어긋남 {len(failures)}: " + " / ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
