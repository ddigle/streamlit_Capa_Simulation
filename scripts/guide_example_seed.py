# Purpose: 가이드 예시판이 띄울 합성 시나리오 DB 를 앱 파이프라인으로 만든다(예시판 시드).
"""따라하기 가이드 예시판 합성 시드 — 생성기 `--example` 의 시드 단계.

앱 내장 시드(`builtin_seed`: 제품 2 · 공정 3)는 계획 물량이 대당 Capa 에 비해 너무 작아
확보율이 수만 % 로 나오고 부족 칸이 없어 예시판 그림으로 쓸 수 없다. 이 모듈은 앱 코드를
그대로 불러 Core Data → 파이프라인 → 계산을 돌리고, 두 단계로 맞춘다.

1. 계획만 넣고 소요대수를 잰다.
2. 공정마다 여유 하한을 지키는 계단식 반입(2대 단위)으로 가용대수를 정하고, 부족 칸만
   하한 아래로 둔다.

결과 DB(시나리오 저장소 하나)
- 표시순서: 공정을 흐름 차례(Wafer Saw → … → AVI)로 — 리비전의 `RQ_DISPLAY_ORDER` 와
  공용 프로필 둘 다.
- 핵심 공정 프리셋 하나.
- 시나리오 둘 — 「26년 9월 정기 Capa 검토」(공식) → 「26년 10월 정기 Capa 검토」
  r1(최신 공식). 비교 시나리오는 비워 둔다(가이드 촬영이 고른다).
- 이야기 칸: 12월 Pre B/D 부족(96%) — 가용 +2 로 부족을 벗어난다(102%). 가이드
  「가용대수 바꾸기」 → 리비전 → 공식 흐름이 이 칸을 쓴다. 촬영 계획의 매개값
  기본값(`STORY_*` · `ACTIVE_SCENARIO_NAME`)과 맞물린다.

`RQ_UPEH` 의 ST 는 분 단위다(정의 — 환산 UPEH = 60 ÷ ST, CHIP·PKG 는 다시 ÷ 1000).
MI 공정의 ST 는 목표 대당 Capa 에서 거꾸로 낸 환산 UPEH 로 `60 / 환산` · `0.06 / 환산` 이다.

숫자 · 이름은 모두 합성이다(공정 이름은 혁신대회 덱과 같은 일반 공정명). 업무 계약이
아니라 예시판 이야기 꼴이고, 그 꼴(확보율 범위 · 판정 개수 · 달별 B/N · 이야기 칸)은
`tests/test_guide_example_seed.py` 가 지킨다.

쓰임(앱 사본의 가상환경 · 소스로 — 결과 DB 는 저장소 밖 사본의 `data/` 에 둔다):
    PYTHONPATH=<앱 사본>/src <앱 .venv>/bin/python scripts/guide_example_seed.py \\
        --out <앱 사본>/data/capa_simulation.duckdb
"""

from __future__ import annotations

import argparse
import calendar
import logging
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NamedTuple

import pandas as pd

from capa_simulation.io.core_data_source import CoreDataBatch, load_core_data_contract
from capa_simulation.persistence.models import ScenarioCreate, ScenarioPreset
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services import builtin_seed
from capa_simulation.services.core_data_pipeline import (
    PreparedCoreDataset,
    prepare_core_data_dataset,
)
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.securement_threshold import (
    DEFAULT_SECURE_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    CapacityStatus,
    capacity_status,
)

# `get_capacity_and_demand` 는 Streamlit 캐시 래퍼 모듈에 있다. 실행 문맥 밖이라 래퍼마다
# 「No runtime found」 경고가 표준 오류에 한 줄씩(수십 줄) 찍히므로 불러오는 동안만 끄고 앞
# 단계로 되돌린다(`inspect_revision_calculations.py` 와 같은 꼴).
_LOGGING_DISABLED: Final = logging.root.manager.disable
logging.disable(max(_LOGGING_DISABLED, logging.WARNING))
try:
    from capa_simulation.services.simulation_cache import get_capacity_and_demand
finally:
    logging.disable(_LOGGING_DISABLED)

PIPELINE_VERSION = "guide-example-seed-v1"
# 머리 띠의 원천 이름. `CSV_` 로 시작하면 「CSV」로 적힌다(`app_header.source_type_label`)
# — 「내장 시드」 대신 보통 화면처럼 보이게.
SOURCE_TYPE = "CSV_CORE_DATA_GUIDE_EXAMPLE"
# 판정 개수의 이름. 앱 판정(`capacity_status`)의 세 상태를 화면 말로 적는다.
STATUS_LABELS: Mapping[CapacityStatus, str] = {
    "secure": "확보",
    "warning": "경고",
    "shortage": "부족",
}


class _Product(NamedTuple):
    name: str
    stack: str
    core_chips: int
    net_die: int
    gb_per_chip: int
    eds_yield: float
    be_yield: float
    cs: str
    plan_share: float


class _Process(NamedTuple):
    name: str
    area: str
    demand_basis: str
    divisions: tuple[str, ...]
    # 대당 월 Capa 목표(WF 는 매, CHIP·PKG 는 K개) — 30일 달의 대당 Capa 가 이 값이 되게
    # UPEH·ST 를 거꾸로 낸다.
    target_capacity: float
    run_rate: float
    vital: float
    modules: int
    # 여유 하한(소요대수 배수). 반입 계단이 이 아래로 내려가지 않는다.
    floor: float


PRODUCTS: tuple[_Product, ...] = (
    _Product("제품 A", "12H", 12, 720, 24, 0.93, 0.97, "MP", 0.30),
    _Product("제품 B", "8H", 8, 760, 24, 0.94, 0.97, "MP", 0.22),
    _Product("제품 C", "12H", 12, 700, 24, 0.92, 0.96, "MP", 0.18),
    _Product("제품 D", "16H", 16, 680, 24, 0.90, 0.95, "MP", 0.13),
    _Product("제품 E", "8H", 8, 800, 16, 0.95, 0.98, "MP", 0.10),
    _Product("제품 F", "12H", 12, 720, 24, 0.88, 0.94, "ER", 0.07),
)
# 흐름 차례 — 표시순서의 공정 차례도 이것이다.
PROCESSES: tuple[_Process, ...] = (
    _Process("Wafer Saw", "MI", "WF", ("Buffer", "Core"), 1200, 0.86, 1.05, 1, 1.06),
    _Process("Wafer Sorter", "Main", "WF", ("Buffer", "Core"), 1450, 0.88, 1.04, 1, 1.08),
    _Process("Pre B/D", "Main", "CHIP", ("Core",), 330, 0.84, 1.08, 1, 1.05),
    _Process("Underfill", "Main", "PKG", ("Buffer",), 34, 0.85, 1.06, 1, 1.06),
    _Process("Mold", "Main", "PKG", ("Buffer",), 44, 0.88, 1.05, 2, 1.04),
    _Process("Ball Attach", "Main", "PKG", ("Buffer",), 42, 0.87, 1.04, 1, 1.07),
    _Process("Singulation", "MI", "PKG", ("Buffer",), 44, 0.86, 1.05, 1, 1.06),
    _Process("AVI", "Main", "PKG", ("Buffer",), 60, 0.90, 1.03, 1, 1.16),
)
PROCESS_NAMES: tuple[str, ...] = tuple(process.name for process in PROCESSES)
KEY_PROCESS_PRESET = "핵심 공정"
KEY_PROCESSES: tuple[str, ...] = (
    "Wafer Saw",
    "Pre B/D",
    "Underfill",
    "Mold",
    "Singulation",
    "AVI",
)
# 반입이 늦은 달(계단을 건너뛴다) — 경고 칸이 생긴다. 건너뛰면 부족까지 떨어지는 달은
# 건너뛰지 않는다(부족은 `SHORT_CELLS` 만).
DELAYED_CELLS: frozenset[tuple[str, int]] = frozenset(
    {
        ("Pre B/D", 202611),
        ("Mold", 202701),
        ("Mold", 202702),
        ("Underfill", 202705),
        ("Underfill", 202706),
        ("Ball Attach", 202707),
        ("Singulation", 202708),
    }
)
# 가이드가 고치는 칸 — 하한 바로 아래보다 한 대 더 모자라게 두어, +2 대면 부족을 벗어나 경고가 된다.
STORY_PROCESS = "Pre B/D"
STORY_MONTH = 202612
STORY_DELTA = 2
# 부족 칸 — 가용 = ceil(소요 × 경고 기준) − 1(이야기 칸은 − 2). 대여로 빠진 만큼
# 보유 − 가용 이 늘어난다.
SHORT_CELLS: tuple[tuple[str, int], ...] = ((STORY_PROCESS, STORY_MONTH), ("Wafer Saw", 202704))

WAFER_K_BY_MONTH: Mapping[int, float] = {  # 월 투입 Wafer(K 매) — 연말 · 2분기에 늘어나는 꼴
    202609: 18,
    202610: 18,
    202611: 19,
    202612: 21,
    202701: 21,
    202702: 20,
    202703: 21,
    202704: 21,
    202705: 22,
    202706: 23,
    202707: 23,
    202708: 22,
    202709: 23,
}


class _ScenarioSeed(NamedTuple):
    label: str
    simulation_code: str
    simulation_name: str
    scenario_name: str
    release_name: str
    first_month: int
    plan_scale: float
    with_short_cells: bool


SCENARIOS: tuple[_ScenarioSeed, ...] = (
    _ScenarioSeed(
        "9월",
        "DEMO-SIM-2609A",
        "26년 9월 정기 시뮬레이션",
        "26년 9월 정기 Capa 검토",
        "9월 공식안",
        202609,
        0.97,
        False,
    ),
    _ScenarioSeed(
        "10월",
        "DEMO-SIM-2610A",
        "26년 10월 정기 시뮬레이션",
        "26년 10월 정기 Capa 검토",
        "10월 공식안",
        202610,
        1.0,
        True,
    ),
)
# 최신 공식 = 앱이 처음 띄우는 활성 시나리오. 촬영 계획의 활성 시나리오 매개값 기본값이다.
ACTIVE_SCENARIO_NAME = SCENARIOS[-1].scenario_name
SEED_NOTE = "가이드 예시판 합성 데이터"

EquipmentPlan = Mapping[tuple[int, str], tuple[int, int]]


@dataclass(frozen=True)
class Bottleneck:
    """한 달의 B/N — 그 달 확보율이 가장 낮은 공정."""

    month: int
    process: str
    rate_percent: float


@dataclass(frozen=True)
class ScenarioShape:
    """시나리오 하나의 확보율 꼴. 퍼센트 값이다."""

    label: str
    scenario_name: str
    rate_min: float
    rate_max: float
    rate_median: float
    status_counts: Mapping[str, int]
    bottlenecks: tuple[Bottleneck, ...]

    @property
    def bottleneck_processes(self) -> tuple[str, ...]:
        """달별 B/N 공정의 종류(처음 나온 차례)."""
        return tuple(dict.fromkeys(item.process for item in self.bottlenecks))


@dataclass(frozen=True)
class StoryCell:
    """이야기 칸 — 고치기 전 확보율과 `STORY_DELTA` 대를 더한 뒤 확보율."""

    process: str
    month: int
    required: float
    available: float
    rate_percent: float
    rate_after_percent: float
    status: CapacityStatus
    status_after: CapacityStatus


@dataclass(frozen=True, eq=False)
class ExampleDataset:
    """DB 에 쓰기 전의 시나리오 하나 — 준비된 원천과 그 확보율."""

    seed: _ScenarioSeed
    months: tuple[int, ...]
    dataset: PreparedCoreDataset
    rates: pd.DataFrame


@dataclass(frozen=True, eq=False)
class GuideExampleSeed:
    """만든 시드의 요약. `examples` 는 DB 에 쓴 두 시나리오(원천 · 확보율)다."""

    database: Path
    shapes: tuple[ScenarioShape, ...]
    story: StoryCell
    scenario_count: int
    latest_release_no: int
    examples: tuple[ExampleDataset, ...] = field(repr=False)

    @property
    def latest(self) -> ScenarioShape:
        """최신 공식(앱이 처음 띄우는 활성 시나리오)의 꼴."""
        return self.shapes[-1]

    @property
    def latest_rates(self) -> pd.DataFrame:
        """최신 공식 시나리오의 공정 × 달 확보율(긴 꼴)."""
        return self.examples[-1].rates


def months_from(start: int, count: int = 12) -> tuple[int, ...]:
    """YYYYMM `start` 부터 `count` 달."""
    year, month = divmod(start, 100)
    out: list[int] = []
    for _ in range(count):
        out.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(out)


def _plan_quantity(month: int, index: int, scale: float) -> dict[str, float]:
    """제품별 월 계획(K PKG). 투입 Wafer × 비중 × 수율 → Core chip + Buffer 1 장."""
    out: dict[str, float] = {}
    for product in PRODUCTS:
        wafers = (
            WAFER_K_BY_MONTH[month]
            * 1000
            * product.plan_share
            * (1 + 0.04 * math.sin(index * 1.3 + len(product.name)))
        )
        out[product.name] = (
            wafers
            * product.net_die
            * product.eds_yield
            * product.be_yield
            / (1000 * (product.core_chips + 1))
            * scale
        )
    return out


def _standard_time(process: _Process, converted_upeh: float) -> float | None:
    """MI 경로의 ST(분). 환산 UPEH = 60 ÷ ST 이고 CHIP·PKG 는 다시 ÷ 1000 이라 그 거꾸로다."""
    if process.area != "MI":
        return None
    return 60 / converted_upeh if process.demand_basis == "WF" else 0.06 / converted_upeh


def _core_data(months: Sequence[int], equipment: EquipmentPlan, scale: float) -> pd.DataFrame:
    """78컬럼 계약의 합성 Core Data — 제품마다 계획 행과 공정 경로 행."""
    columns = [column.name for column in load_core_data_contract().columns]
    rows: list[dict[str, object]] = []
    for month_index, month in enumerate(months):
        days = calendar.monthrange(month // 100, month % 100)[1]
        quantity = _plan_quantity(month, month_index, scale)
        for product_no, product in enumerate(PRODUCTS, start=1):
            plan = quantity[product.name]
            for division, chips, gb_per_chip in (
                ("Buffer", 1, None),
                ("Core", product.core_chips, product.gb_per_chip),
            ):
                common: dict[str, object] = dict.fromkeys(columns, pd.NA)
                common.update(
                    {
                        "기준정보년월": month,
                        "제품타입": "DEMO",
                        "U/PKG": "1",
                        "PKG1": "PKG-S",
                        "LOB Code": "LOB-1",
                        "Capa Code": f"CAPA-{product.name[-1]}",
                        "제품정보": product.name,
                        "생산계획년월": month,
                        "생산수량": round(plan, 3),
                        "Stack": product.stack,
                        "Customer": f"CUST-{product_no}",
                        "Pack Code": "PK-1",
                        "CS": product.cs,
                        "D_EQ": product.gb_per_chip,
                        "WF 구분": division,
                        "구분_Chip": chips,
                        "구분_EQ": pd.NA if gb_per_chip is None else gb_per_chip,
                        "CHIP": chips,
                        "Net Die": product.net_die,
                        "Month": month % 10000,
                        "Plan_Chip(K개)": plan * chips,
                        "계획(K개)": plan,
                        "8H 환산 계획(K개)": plan,
                        "WF수(매)": plan * 1000 * chips / product.net_die,
                        "EQ(억Gb)": (
                            pd.NA if gb_per_chip is None else plan * chips * gb_per_chip / 1e5
                        ),
                        "누락여부": "N",
                        "EDS_수율": product.eds_yield,
                        "BE_수율": product.be_yield,
                        "CUM_수율": product.eds_yield * product.be_yield,
                    }
                )
                plan_row = dict(common)
                plan_row.update(
                    {
                        "시뮬레이션 ID": f"G-{month}-{product_no}-{division}",
                        "PLAN ID": f"P-{month}-{product_no}",
                        "계획기초정보여부": "Y",
                    }
                )
                rows.append(plan_row)
                for step_no, process in enumerate(PROCESSES, start=1):
                    if division not in process.divisions:
                        continue
                    # 대당 Capa = 환산 UPEH × 24 × 효율 / 편중률 × 모듈수 × 일수 — 목표에서
                    # 환산 UPEH 를 거꾸로 낸다.
                    converted = process.target_capacity / (
                        24 * process.run_rate / process.vital * process.modules * 30
                    )
                    upeh = converted * (1000 if process.demand_basis in ("CHIP", "PKG") else 1)
                    standard_time = _standard_time(process, converted)
                    owned, lent = equipment.get((month, process.name), (2, 1))
                    route_row = dict(common)
                    route_row.update(
                        {
                            "시뮬레이션 ID": f"G-{month}-{product_no}-{division}-{step_no}",
                            "PLAN ID": f"P-{month}-{product_no}",
                            "계획기초정보여부": "N",
                            "FAB": "PKG",
                            "Area_Name": process.area,
                            "공정": process.name,
                            "메이커": "MAKER-1",
                            "STEP_SEQ": f"S{100 + step_no * 10}",
                            "MCP_SEQ": "1A",
                            "모델명": "MODEL-1",
                            "Para": "1",
                            "Step수": "1",
                            "CAPA_RUN_RATE": process.run_rate,
                            "소요기준": process.demand_basis,
                            "RUN_DAY": days,
                            "UPEH": upeh if process.area == "Main" else pd.NA,
                            "ST": pd.NA if standard_time is None else standard_time,
                            "Lot 측정률": 1,
                            "WF측정률": 1,
                            "모듈수": process.modules,
                            "Side반영률": 1,
                            "편중률": process.vital,
                            "설비보유": owned,
                            "설비대수변화관리": "0",
                            "설비대여평가": lent,
                            "설비대여평가항목": "샘플",
                            "설비대여평가DESC": "가이드 합성",
                            "MCP_Chip_Ratio": 1,
                            "시뮬레이션 누락여부": "N",
                        }
                    )
                    rows.append(route_row)
    return pd.DataFrame(rows, columns=columns)


def display_order() -> pd.DataFrame:
    """내장 표시순서(추적 파일만)에서 「공정」 규칙만 흐름 차례(사용자지정)로 바꾼다."""
    rules = builtin_seed.load_tracked_display_order()
    keep = rules.loc[rules["분류컬럼"].ne("공정")]
    custom: list[dict[str, object]] = []
    process_rules: list[dict[str, object]] = [
        {str(key): value for key, value in rule.items()}
        for rule in rules.loc[rules["분류컬럼"].eq("공정")].to_dict("records")
    ]
    for rule in process_rules:
        for order, name in enumerate(PROCESS_NAMES, start=1):
            custom.append({**rule, "정렬방식": "사용자지정", "분류값": name, "값표시순서": order})
    return pd.concat([keep, pd.DataFrame(custom)], ignore_index=True)


def _prepare(
    seed: _ScenarioSeed, months: Sequence[int], equipment: EquipmentPlan, rules: pd.DataFrame
) -> tuple[PreparedCoreDataset, pd.DataFrame]:
    frame = _core_data(months, equipment, seed.plan_scale)
    # 화면은 리비전의 RQ_DISPLAY_ORDER 를 읽으므로 원천 변환에도 흐름 차례를 넘긴다.
    dataset = prepare_core_data_dataset(
        CoreDataBatch(seed.simulation_code, seed.simulation_name, SOURCE_TYPE, frame), rules
    )
    _, required = get_capacity_and_demand(dataset.reference_tables)
    rates = calculate_securement_rate(dataset.reference_tables["RQ_EQP_AVBL"], required)
    return dataset, rates


def _equipment_plan(
    months: Sequence[int], need: Mapping[tuple[int, str], float], with_short_cells: bool
) -> dict[tuple[int, str], tuple[int, int]]:
    """(달, 공정) → (보유, 대여). 가용 = 보유 − 대여.

    대여는 평소 1대이고, 부족 칸은 하한 아래로 내려갈 만큼 늘린다.
    """
    out: dict[tuple[int, str], tuple[int, int]] = {}
    for process in PROCESSES:
        have: int | None = None
        for month in months:
            required = need[(month, process.name)]
            want = math.ceil(required * process.floor)
            if have is None:
                have = want + 1
            elif want > have and not (
                (process.name, month) in DELAYED_CELLS
                and have >= math.ceil(required * DEFAULT_WARNING_THRESHOLD)
            ):
                have += 2 * math.ceil((want - have) / 2)
            available = have
            if with_short_cells and (process.name, month) in SHORT_CELLS:
                below = 2 if (process.name, month) == (STORY_PROCESS, STORY_MONTH) else 1
                available = min(have, math.ceil(required * DEFAULT_WARNING_THRESHOLD) - below)
            out[(month, process.name)] = (have + 1, 1 + have - available)
    return out


def _required_by_cell(rates: pd.DataFrame) -> dict[tuple[int, str], float]:
    return {
        (int(month), str(process)): float(required)
        for month, process, required in rates[["생산계획년월", "공정", "소요대수"]].itertuples(
            index=False
        )
    }


def build_example_datasets() -> tuple[ExampleDataset, ...]:
    """DB 에 쓰지 않고 두 시나리오의 원천과 확보율을 만든다(계획만 → 소요 → 가용 계단 → 다시)."""
    rules = display_order()
    out: list[ExampleDataset] = []
    for seed in SCENARIOS:
        months = months_from(seed.first_month)
        _, first = _prepare(seed, months, {}, rules)
        equipment = _equipment_plan(months, _required_by_cell(first), seed.with_short_cells)
        dataset, rates = _prepare(seed, months, equipment, rules)
        out.append(ExampleDataset(seed, months, dataset, rates))
    return tuple(out)


def _status(rate: float) -> CapacityStatus:
    return capacity_status(
        rate,
        secure_threshold=DEFAULT_SECURE_THRESHOLD,
        warning_threshold=DEFAULT_WARNING_THRESHOLD,
    )


def scenario_shape(example: ExampleDataset) -> ScenarioShape:
    """확보율 범위 · 판정 개수(앱 기본 판정 기준) · 달별 B/N."""
    rates = example.rates
    ratios = [float(value) for value in rates["확보율"]]
    percents = pd.Series(ratios, dtype="float64") * 100
    counts = dict.fromkeys(STATUS_LABELS.values(), 0)
    for ratio in ratios:
        counts[STATUS_LABELS[_status(ratio)]] += 1
    lowest = (
        rates.sort_values(["확보율", "공정"], kind="stable")
        .groupby("생산계획년월", sort=True)
        .head(1)
        .sort_values("생산계획년월", kind="stable")
    )
    bottlenecks = tuple(
        Bottleneck(int(month), str(process), float(ratio) * 100)
        for month, process, ratio in lowest[["생산계획년월", "공정", "확보율"]].itertuples(
            index=False
        )
    )
    return ScenarioShape(
        label=example.seed.label,
        scenario_name=example.seed.scenario_name,
        rate_min=float(percents.min()),
        rate_max=float(percents.max()),
        rate_median=float(percents.median()),
        status_counts=counts,
        bottlenecks=bottlenecks,
    )


def story_cell(example: ExampleDataset) -> StoryCell:
    """이야기 칸의 고치기 전 · 뒤 확보율."""
    rates = example.rates
    row = rates.loc[rates["공정"].eq(STORY_PROCESS) & rates["생산계획년월"].eq(STORY_MONTH)]
    if len(row) != 1:
        raise ValueError(
            f"이야기 칸({STORY_PROCESS} {STORY_MONTH})이 확보율 표에 한 행으로 없습니다."
        )
    required = float(row["소요대수"].iloc[0])
    available = float(row["가용대수"].iloc[0])
    after = (available + STORY_DELTA) / required
    return StoryCell(
        process=STORY_PROCESS,
        month=STORY_MONTH,
        required=required,
        available=available,
        rate_percent=available / required * 100,
        rate_after_percent=after * 100,
        status=_status(available / required),
        status_after=_status(after),
    )


def rate_table(rates: pd.DataFrame) -> pd.DataFrame:
    """공정(흐름 차례) × 달 확보율(%) 표."""
    table = rates.pivot(index="공정", columns="생산계획년월", values="확보율").astype("float64")
    return (table * 100).round(1).reindex(list(PROCESS_NAMES))


def build_example_seed(out_path: Path, *, replace: bool = False) -> GuideExampleSeed:
    """`out_path` 에 예시판 시나리오 DB 를 만들고 그 꼴을 돌려준다.

    이미 파일이 있으면 `replace=True` 일 때만 지우고 새로 만든다 — 실 DB 를 잘못 짚어 덮지 않게.
    """
    database = Path(out_path)
    stale = [database, database.with_name(database.name + ".wal")]
    if any(path.exists() for path in stale) and not replace:
        raise FileExistsError(
            f"이미 있는 DB 는 덮지 않습니다(replace 를 주면 지웁니다): {database}"
        )
    examples = build_example_datasets()

    database.parent.mkdir(parents=True, exist_ok=True)
    for path in stale:
        path.unlink(missing_ok=True)
    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.initialize_global_display_order(display_order())
    repository.replace_global_key_process_presets(
        [(KEY_PROCESS_PRESET, KEY_PROCESSES)], source="가이드 합성"
    )
    for example in examples:
        batch = example.dataset.batch
        snapshot = repository.create_scenario(
            ScenarioCreate(
                scenario_name=example.seed.scenario_name,
                source_simulation_code=batch.simulation_code,
                source_simulation_name=batch.simulation_name,
                source_type=batch.source_type,
                pipeline_version=PIPELINE_VERSION,
            ),
            example.dataset.reference_tables,
            ScenarioPreset(
                start_month=example.months[0],
                end_month=example.months[-1],
                included_processes=PROCESS_NAMES,
            ),
            source_data=example.dataset.source_data,
            revision_name="원천 등록",
            note=SEED_NOTE,
        )
        repository.publish_official_revision(
            snapshot.scenario.scenario_id,
            snapshot.revision.revision_id,
            release_name=example.seed.release_name,
            note=SEED_NOTE,
        )
    latest = repository.latest_official_release()
    if latest is None:
        raise RuntimeError("공식버전을 발행하지 못했습니다.")
    return GuideExampleSeed(
        database=database,
        shapes=tuple(scenario_shape(example) for example in examples),
        story=story_cell(examples[-1]),
        scenario_count=len(repository.list_scenarios()),
        latest_release_no=latest.release_no,
        examples=examples,
    )


def _shape_lines(shape: ScenarioShape) -> list[str]:
    counts = " · ".join(f"{label} {count}" for label, count in shape.status_counts.items())
    bottlenecks = " ".join(
        f"{item.month % 10000}:{item.process}({item.rate_percent:.0f})"
        for item in shape.bottlenecks
    )
    return [
        f"[{shape.label}] 확보율 {shape.rate_min:.1f}~{shape.rate_max:.1f}% "
        f"(중앙 {shape.rate_median:.1f}) · 판정 {counts}",
        f"[{shape.label}] 달별 B/N {len(shape.bottleneck_processes)}종: {bottlenecks}",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="따라하기 가이드 예시판 합성 시나리오 DB 를 만든다."
    )
    parser.add_argument("--out", required=True, type=Path, help="만들 시나리오 DB 경로")
    parser.add_argument(
        "--replace", action="store_true", help="그 자리에 DB 가 있으면 지우고 새로 만든다"
    )
    parser.add_argument(
        "--table", action="store_true", help="최신 공식의 공정 × 달 확보율 표를 찍는다"
    )
    args = parser.parse_args(argv)

    try:
        result = build_example_seed(args.out, replace=args.replace)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for shape in result.shapes:
        print("\n".join(_shape_lines(shape)))
    story = result.story
    print(
        f"[이야기] {story.process} {story.month}: 소요 {story.required:.1f} · 가용 "
        f"{story.available:.0f} → {story.rate_percent:.1f}% · +{STORY_DELTA} 대면 "
        f"{story.rate_after_percent:.1f}%"
    )
    if args.table:
        print(rate_table(result.latest_rates).to_string())
    print(
        f"DB {result.database} · 시나리오 {result.scenario_count} · "
        f"최신 공식 v{result.latest_release_no}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
