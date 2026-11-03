# Purpose: 검수용 합성 샘플의 시뮬레이션 DB 를 앱 저장소 API 로만 만들고 이야기 꼴을 점검한다.
"""검수용 합성 샘플 1단계 — 시뮬레이션 DB(`capa_simulation.duckdb`).

쓰는 길은 앱의 저장소·등록·자동 갱신 공개 함수뿐이다(SQL INSERT·UPDATE 없음). 보통은 입구
`generate_review_sample.py` 가 부른다 — 혼자 돌릴 때도 인자는 같다.

    .venv/bin/python scripts/review_sample_sim.py --out <저장소 밖 뿌리>/data --replace

다 만든 뒤 끝 점검(`run_checks` 외 — 52개)을 찍고, 하나라도 어긋나면 산출물을 옮기지 않고(준비 자리
`<뿌리>/.gen-sim-work/stage` 에 남김) 종료 코드 1 이다. 기록 · 공정×월 표 · 지문은 산출 뿌리에 둔다.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import shutil
import subprocess
import sys
import time as wall_time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Final
from uuid import uuid4

import pandas as pd

import capa_simulation

# Streamlit 캐시 래퍼 모듈은 실행 문맥 밖에서 「No runtime found」 경고를 줄줄이 찍는다.
_LOGGING_DISABLED: Final = logging.root.manager.disable
logging.disable(max(_LOGGING_DISABLED, logging.WARNING))
import review_sample_core_frame as core_frame  # noqa: E402
import review_sample_story as story  # noqa: E402

from capa_simulation.auto_official_update_runner import (  # noqa: E402
    INTERRUPTED_REASON,
    AutoUpdateSources,
    DetailRequest,
    abandon_interrupted_runs,
    auto_off_marks,
    current_official_baseline,
    run_auto_official_update,
)
from capa_simulation.components.capacity_gate import (  # noqa: E402
    density_error,
    derived_save_verdict,
)
from capa_simulation.components.process_labels import process_labels_from_rules  # noqa: E402
from capa_simulation.components.scenario_management import CLONE_PIPELINE_VERSION  # noqa: E402
from capa_simulation.io.company_bigdataquery_adapter import QueryWindow  # noqa: E402
from capa_simulation.io.core_data_source import (  # noqa: E402
    CoreDataBatch,
    CoreDataProvider,
    read_core_data_csv,
)
from capa_simulation.persistence.models import (  # noqa: E402
    ScenarioCreate,
    ScenarioPreset,
    ScenarioSnapshot,
)
from capa_simulation.persistence.repository import (  # noqa: E402
    REVISION_TABLES,
    DuckDBScenarioRepository,
)
from capa_simulation.scenario_preset_state import full_data_scenario_preset  # noqa: E402
from capa_simulation.scenario_registration import (  # noqa: E402
    registration_note,
    save_bigdataquery_scenario,
)
from capa_simulation.services.advance_shipment import advance_shipment_notes  # noqa: E402
from capa_simulation.services.auto_official_update import (  # noqa: E402
    EXCLUSION_AUTO,
    EXCLUSION_INHERITED,
    STATUS_ERROR,
    STATUS_PUBLISH_SKIPPED,
    STATUS_PUBLISHED,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
    AutoUpdateConfig,
    process_minimum_rates,
    scheduled_run_key,
)
from capa_simulation.services.core_data_pipeline import (  # noqa: E402
    PreparedCoreDataset,
    prepare_core_data_dataset,
)
from capa_simulation.services.dashboard import (  # noqa: E402
    build_monthly_bottleneck_ranking,
    build_monthly_bottlenecks_from_ranking,
    build_production_dashboard,
)
from capa_simulation.services.display_order_csv import (  # noqa: E402
    display_order_from_csv,
    display_order_to_csv,
)
from capa_simulation.services.load_calculator import (  # noqa: E402
    calculate_chip_and_wafer_loads,
    filter_edp_plan,
)
from capa_simulation.services.month_columns import month_label  # noqa: E402
from capa_simulation.services.official_summary import (  # noqa: E402
    SUMMARY_MONTH_COUNT,
    summary_months,
)
from capa_simulation.services.required_equipment import (  # noqa: E402
    PKG_UNCOUNTED_REASON,
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    required_exclusion_counts,
)
from capa_simulation.services.scenario_month_merge import (  # noqa: E402
    OverlapPolicy,
    compare_non_monthly_tables,
    merge_scenario_months,
    merged_table_gaps,
    preview_month_sources,
)
from capa_simulation.services.scenario_transform import (  # noqa: E402
    copy_scenario_tables,
    format_month_range,
    format_month_runs,
    missing_calendar_months,
    scenario_months,
)
from capa_simulation.services.scenario_virtual_products import (  # noqa: E402
    merge_result_virtual_products,
    virtual_product_records,
)
from capa_simulation.services.scenario_year_shift import shift_scenario_years  # noqa: E402
from capa_simulation.services.securement_rate import calculate_securement_rate  # noqa: E402
from capa_simulation.services.securement_threshold import (  # noqa: E402
    SecurementThresholds,
    build_securement_thresholds,
)
from capa_simulation.services.simulation_cache import (  # noqa: E402
    full_capacity_outcome,
    get_capacity_and_demand,
)
from capa_simulation.services.unit_capacity import (  # noqa: E402
    CAPACITY_EXCLUSIONS_ATTR,
    capacity_assumptions,
)
from capa_simulation.services.virtual_product import (  # noqa: E402
    VirtualProductRecord,
    VirtualProductRequest,
    clone_product,
)
from capa_simulation.settings import format_month  # noqa: E402

logging.disable(_LOGGING_DISABLED)

DB_NAME: Final = "capa_simulation.duckdb"
CSV_NAMES: Final = ("Core_Data.csv", "RQ_DISPLAY_ORDER.csv")
LOG_NAME: Final = "build-log-sim.txt"
FINGERPRINT_NAME: Final = "fingerprint-sim.txt"
# 산출물 사본에 돌려 S8 r1 만 멈추는지 보는 저장소 스크립트(이 파일 옆).
INSPECT_SCRIPT: Final = Path(__file__).resolve().parent / "inspect_revision_calculations.py"

Key = tuple[int, str]


# ============================================================================== 기록
class BuildLog:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: list[str] = []
        self.started = wall_time.time()

    def say(self, text: str) -> None:
        stamp = f"[{wall_time.time() - self.started:6.1f}s]"
        line = f"{stamp} {text}"
        self.lines.append(line)
        print(line, flush=True)

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = "OK  " if ok else "FAIL"
        self.say(f"{mark} {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.failures.append(label)


LOG = BuildLog()


# ============================================================================== 경로 지킴
def refuse_unsafe(path: Path) -> None:
    """git 작업 트리(이 저장소 포함) 안이면 멈춘다(쓰기 전에)."""
    refusal = story.refuse_place(path)
    if refusal is not None:
        raise SystemExit(refusal)


def resolve_outputs(out: Path, csv_out: Path | None) -> tuple[Path, Path | None]:
    if out.suffix == ".duckdb":
        database = out
        data_dir = out.parent
    else:
        data_dir = out
        database = out / DB_NAME
    return database, (csv_out if csv_out is not None else data_dir / "input")


def own_outputs(database: Path, csv_dir: Path | None) -> list[Path]:
    """이 생성기가 쓰는 파일 — `--replace` 가 지우고 덮는 것은 이것뿐이다."""
    own = [database, database.with_name(database.name + ".wal")]
    if csv_dir is not None:
        own.extend(csv_dir / name for name in CSV_NAMES)
    return own


def prepare_outputs(database: Path, csv_dir: Path | None, *, replace_existing: bool) -> None:
    """쓰기 전 지킴 — 메인 체크아웃·git 안이면 멈추고, 있으면 `--replace` 일 때만 덮는다(덮는 것은 "
    "끝에)."""
    own = own_outputs(database, csv_dir)
    for path in own:
        refuse_unsafe(path)
    existing = [path for path in own if path.exists()]
    if existing and not replace_existing:
        raise SystemExit(
            "이미 있는 산출물은 덮지 않습니다(--replace 를 주면 이 생성기의 산출물만 덮습니다): "
            + ", ".join(str(path) for path in existing)
        )


def stage_outputs(work: Path, with_csv: bool) -> tuple[Path, Path | None]:
    """준비 자리 — 다 만든 뒤 한 번에 옮겨(`os.replace`) 다른 생성기가 반쯤 쓴 DB 를 읽지 않게 "
    "한다."""
    refuse_unsafe(work)
    stage = work / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "input").mkdir(parents=True)
    return stage / DB_NAME, (stage / "input" if with_csv else None)


def publish_outputs(
    stage_db: Path, stage_csv: Path | None, database: Path, csv_dir: Path | None
) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    stale_wal = database.with_name(database.name + ".wal")
    if stale_wal.exists():
        stale_wal.unlink()
    os.replace(stage_db, database)
    if stage_csv is not None and csv_dir is not None:
        csv_dir.mkdir(parents=True, exist_ok=True)
        for name in CSV_NAMES:
            os.replace(stage_csv / name, csv_dir / name)
    LOG.say(f"산출물 옮김 → {database}" + (f" · {csv_dir}" if csv_dir is not None else ""))


# ============================================================================== 표시순서
def story_display_order() -> pd.DataFrame:
    """14범위 표시순서(2-3). 사용자지정 범위는 분류값마다 한 행."""
    values: dict[str, Sequence[str]] = {
        "공정": story.DISPLAY_PROCESS_ORDER,
        "제품정보": (
            *story.PRODUCT_NAMES,
            *(item[2] for item in story.VIRTUAL_PRODUCTS),
            story.QUIRK_UNKNOWN_PRODUCT[0],
        ),
        "Stack": ("8H", "12H", "16H", "4H"),
        "WF 구분": ("Buffer", "Core", "Top", "Top_e", "Master", "Slave", "Dummy"),
        "양산구분": ("양산", "ER"),
        "Customer": (*(f"DEMO_CUST-{n}" for n in range(1, 6)), "DEMO_CUST-9"),
        "CS": ("MP", "CS", "CB", "ER"),
        "수율 구분": ("EDS_수율", "BE_수율"),
    }
    ascending = {"Area_Name", "소요기준", "STEP_SEQ", "MCP_SEQ", "Capa Code"}
    route = ("STEP_SEQ", "MCP_SEQ")
    scopes: dict[tuple[str, str], tuple[str, ...]] = {
        ("기준 정보", "UPEH"): (
            "공정",
            "Area_Name",
            "소요기준",
            "양산구분",
            "제품정보",
            "Stack",
            "WF 구분",
            *route,
        ),
        ("기준 정보", "설비대수"): ("공정",),
        ("기준 정보", "효율"): ("공정", "양산구분"),
        ("기준 정보", "여유율"): ("공정", "양산구분"),
        ("기준 정보", "일수"): ("공정",),
        ("기준 정보", "Lot측정률"): ("공정", "양산구분", "제품정보", "Stack", "WF 구분", *route),
        ("기준 정보", "WF측정률"): ("공정", "양산구분", "제품정보", "Stack", "WF 구분", *route),
        ("산출 결과", "대당 Capa"): (
            "공정",
            "소요기준",
            "양산구분",
            "제품정보",
            "Stack",
            "WF 구분",
            "Area_Name",
            *route,
        ),
        ("산출 결과", "소요대수"): (
            "Area_Name",
            "공정",
            "양산구분",
            "제품정보",
            "Stack",
            "WF 구분",
            "소요기준",
            *route,
        ),
        ("산출 결과", "확보율"): ("Area_Name", "공정"),
        ("생산 계획", "환산"): ("양산구분", "제품정보", "Stack", "WF 구분"),
        ("생산 계획", "PKG PLAN"): ("양산구분", "제품정보", "Stack", "Capa Code", "Customer", "CS"),
        ("생산 계획", "수율"): ("수율 구분", "제품정보", "Stack", "WF 구분"),
        ("표준 목표", "목표 Capa"): ("공정", "제품정보", "Stack", "WF 구분"),
    }
    rows: list[dict[str, object]] = []
    for (page, tab), columns in scopes.items():
        for priority, column in enumerate(columns, start=1):
            base = {
                "페이지 구분": page,
                "탭 구분": tab,
                "정렬우선순위": priority,
                "분류컬럼": column,
                "활성여부": "Y",
            }
            if column in ascending:
                rows.append({**base, "정렬방식": "오름차순", "분류값": pd.NA, "값표시순서": pd.NA})
                continue
            for order, value in enumerate(values[column], start=1):
                rows.append(
                    {**base, "정렬방식": "사용자지정", "분류값": value, "값표시순서": order}
                )
    frame = pd.DataFrame(rows)
    return frame[
        [
            "페이지 구분",
            "탭 구분",
            "정렬우선순위",
            "분류컬럼",
            "정렬방식",
            "분류값",
            "값표시순서",
            "활성여부",
        ]
    ]


RULES: Final = story_display_order()


# ============================================================================== 계산 도우미
def prepare(
    variant: str, frame: pd.DataFrame, *, source_type: str, registered_at: datetime | None = None
) -> PreparedCoreDataset:
    spec = story.SOURCES[variant]
    return prepare_core_data_dataset(
        CoreDataBatch(spec.code, spec.name, source_type, frame, source_registered_at=registered_at),
        RULES,
    )


def required_by_cell(required: pd.DataFrame) -> dict[Key, float]:
    grouped = required.groupby(["생산계획년월", "공정"], as_index=False)["소요대수"].sum()
    return {
        (int(month), str(process)): float(value)
        for month, process, value in grouped.itertuples(index=False)
    }


def frame_requirements(frame: pd.DataFrame) -> dict[Key, float]:
    dataset = prepare_core_data_dataset(CoreDataBatch("CAL", "CAL", "CSV_CAL", frame), RULES)
    _, required = get_capacity_and_demand(dataset.reference_tables)
    return required_by_cell(required)


def table_rates(
    tables: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(대당 Capa, 소요대수, 확보율) — 전체 기간."""
    outcome = full_capacity_outcome(tables, tables)
    if (
        outcome.error is not None
        or outcome.required_equipment is None
        or outcome.unit_capacity is None
    ):
        raise RuntimeError(f"Capa 계산 실패: {outcome.error}")
    rates = calculate_securement_rate(tables["RQ_EQP_AVBL"], outcome.required_equipment)
    return outcome.unit_capacity, outcome.required_equipment, rates


def gate(tables: Mapping[str, pd.DataFrame], label: str) -> None:
    """화면 저장·발행 검사와 같은 셈(전체 기간 Capa + Density) — 통과해야 쓴다."""
    outcome = full_capacity_outcome(tables, tables)
    error = outcome.error or density_error(tables)
    if error is not None:
        raise RuntimeError(f"{label}: 계산 검사 실패 — {error}")


def revision_tables(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {name: tables[name].copy(deep=True) for name in REVISION_TABLES}


def thresholds() -> SecurementThresholds:
    return build_securement_thresholds(
        story.SECURE_DEFAULT, story.WARNING_DEFAULT, threshold_rows()
    )


def threshold_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [month for month, _, _ in story.MONTHLY_THRESHOLDS],
            "확보 기준": [secure for _, secure, _ in story.MONTHLY_THRESHOLDS],
            "경고 기준": [warning for _, _, warning in story.MONTHLY_THRESHOLDS],
        }
    ).astype({"확보 기준": "float64", "경고 기준": "float64"})


# ============================================================================== 보정(메모리)
@dataclass
class Calibration:
    equipment: dict[Key, tuple[float, float]] = field(default_factory=dict)
    scale: dict[Key, float] = field(default_factory=dict)
    designated: dict[Key, float] = field(default_factory=dict)  # 칸 → 목표 확보율(비율)
    required: dict[Key, float] = field(default_factory=dict)  # 보정 뒤 기대 소요대수


def _staircase(
    process: story.Process,
    need: Mapping[int, float],
    months: Sequence[int],
    fixed: Mapping[int, tuple[float, float]] | None = None,
) -> dict[int, tuple[float, float, float]]:
    """달 → (보유, 대여, 가용). 가용 = 반입 계단 have(여유 하한 floor), 대여 평소 1대."""
    out: dict[int, tuple[float, float, float]] = {}
    have: float | None = None
    fraction = story.FINAL_TEST_FRACTION if process.name == "Final Test" else 0.0
    for month in months:
        if fixed and month in fixed:
            owned, lent = fixed[month]
            out[month] = (owned, lent, owned - lent)
            have = owned
            continue
        required = need[month]
        want = math.ceil(required * process.floor - fraction) + fraction
        step = 2 if required >= 10 else 1
        if have is None:
            have = want
        elif want > have:
            have += step * math.ceil((want - have) / step)
        out[month] = (have + 1.0, 1.0, have)
    return out


def calibrate() -> Calibration:
    months = story.CALIBRATION_MONTHS
    LOG.say("보정 1 — 장비 자리표시·UPEH 1 로 소요 측정")
    base = frame_requirements(core_frame.build_core_frame("W44", {}, {}, months=months))
    calibration = Calibration()
    process_scale: dict[str, float] = {}
    for process in story.PROCESSES:
        process_scale[process.name] = base[(202611, process.name)] / process.target_required
    scaled = {key: value / process_scale[key[1]] for key, value in base.items()}
    for month in months:
        for process in story.PROCESSES:
            calibration.scale[(month, process.name)] = process_scale[process.name]

    LOG.say("보정 2 — 반입 계단(여유 하한)으로 보유·대여")
    plans: dict[str, dict[int, tuple[float, float, float]]] = {}
    for process in story.PROCESSES:
        need = {month: scaled[(month, process.name)] for month in months}
        fixed = story.PRE_BD_FIXED if process.name == story.STORY_PROCESS else None
        plans[process.name] = _staircase(process, need, months, fixed)

    LOG.say("보정 3 — 이야기 칸·반입 늦은 칸: 대여로 가용을 내리고 그 공정·그 달 UPEH 로 정밀 맞춤")
    targets: dict[Key, float] = {}
    for month, process_name, percent, _ in story.STORY_CELLS:
        targets[(month, process_name)] = percent / 100
    for month, process_name, percent in story.DELAYED_CELLS:
        targets[(month, process_name)] = percent / 100
    for (month, process_name), target in targets.items():
        owned, lent, available = plans[process_name][month]
        required = scaled[(month, process_name)]
        fraction = story.FINAL_TEST_FRACTION if process_name == "Final Test" else 0.0
        if (process_name, month) == (story.STORY_PROCESS, story.STORY_MONTH):
            wanted_available = story.STORY_AVAILABLE
            wanted_required = story.STORY_REQUIRED
        else:
            if process_name == story.STORY_PROCESS and month in story.PRE_BD_FIXED:
                wanted_available = available
            else:
                wanted_available = fraction + max(1, round(required * target - fraction))
                wanted_available = min(wanted_available, available)
            wanted_required = wanted_available / target
        lent = owned - wanted_available
        plans[process_name][month] = (owned, lent, wanted_available)
        # 소요 ∝ 1/환산 UPEH — 그 달 그 공정 경로 전부에 같은 배수라 다른 칸은 그대로다.
        calibration.scale[(month, process_name)] *= required / wanted_required
        scaled[(month, process_name)] = wanted_required
        calibration.designated[(month, process_name)] = target
    for process in story.PROCESSES:
        for month, (owned, lent, _) in plans[process.name].items():
            calibration.equipment[(month, process.name)] = (owned, lent)
    calibration.required = dict(scaled)
    tweaks = sorted(
        (calibration.scale[key] / process_scale[key[1]], key) for key in calibration.designated
    )
    LOG.say(
        f"정밀 맞춤 칸 {len(tweaks)}개 · 그 달 UPEH 배수 {tweaks[0][0]:.3f}~{tweaks[-1][0]:.3f}"
        f"(가장 작은 {format_month(tweaks[0][1][0])} {tweaks[0][1][1]} · 가장 큰 "
        f"{format_month(tweaks[-1][1][0])} {tweaks[-1][1][1]})"
    )

    LOG.say("보정 4 — Case 전용 Hybrid Bonding(27.07~) 따로 맞춤")
    hybrid = story.HYBRID_PROCESS
    hybrid_base = frame_requirements(
        core_frame.build_core_frame(
            "HYBRID", calibration.equipment, calibration.scale, months=story.PLAN_MONTHS
        )
    )
    hybrid_months = [month for month in story.PLAN_MONTHS if month >= story.HYBRID_START]
    hybrid_scale = hybrid_base[(story.HYBRID_TARGET_MONTH, hybrid.name)] / hybrid.target_required
    need = {month: hybrid_base[(month, hybrid.name)] / hybrid_scale for month in hybrid_months}
    for month, (owned, lent, _) in _staircase(hybrid, need, hybrid_months).items():
        calibration.equipment[(month, hybrid.name)] = (owned, lent)
        calibration.scale[(month, hybrid.name)] = hybrid_scale
        calibration.required[(month, hybrid.name)] = need[month]
    return calibration


def verify_calibration(calibration: Calibration) -> None:
    frame = core_frame.build_core_frame(
        "W44", calibration.equipment, calibration.scale, months=story.CALIBRATION_MONTHS
    )
    actual = frame_requirements(frame)
    worst = max(
        abs(actual[key] - value) / value
        for key, value in calibration.required.items()
        if key in actual and key[1] in story.PROCESS_NAMES
    )
    LOG.check(worst < 1e-6, "보정 선형성(다시 돌린 소요 = 기대 소요)", f"최대 상대 차 {worst:.2e}")


# ============================================================================== 가짜 BigDataQuery
CATALOG_ROWS: Final[dict[str, tuple[tuple[str, str, str], ...]]] = {
    # (시뮬레이션명, 코드, 원천 등록시각)
    "W40": (("DEMO PSM W40 정기", "DEMO-SIM-2640", "2026-10-05 09:00:00"),),
    "PSS43": (("DEMO PSS W43 점검", "DEMO-SIM-PSS43", "2026-10-23 14:00:00"),),
    "W43": (("DEMO PSM W43 정기", "DEMO-SIM-2643", "2026-10-26 09:00:00"),),
    "W44": (
        ("DEMO PSM W44 정기", "DEMO-SIM-2644", "2026-10-28 09:00:00"),
        ("DEMO PSM W44 정기", "DEMO-SIM-2644", "2026-10-29 06:30:00"),
    ),
}


def catalog_frame(*groups: str) -> pd.DataFrame:
    rows = [row for group in groups for row in CATALOG_ROWS[group]]
    return pd.DataFrame(
        {
            "simulation_name": [row[0] for row in rows],
            "simulation_code": [row[1] for row in rows],
            "plan_name": ["DEMO PLAN 정기" for _ in rows],
            "plan_code": ["DEMO-PLAN-01" for _ in rows],
            "regist_data": [row[2] for row in rows],
        }
    )


@dataclass
class FakeProvider:
    request: DetailRequest
    frame: pd.DataFrame

    def fetch(self, simulation_code: str) -> CoreDataBatch:
        return CoreDataBatch(
            simulation_code=simulation_code,
            simulation_name=self.request.simulation_name,
            source_type=story.SOURCE_TYPE_BDQ,
            frame=self.frame.copy(),
            source_registered_at=self.request.registered_at,
        )


@dataclass
class FakeBigDataQuery:
    catalog: pd.DataFrame | None
    frames: Mapping[str, pd.DataFrame]
    error: str | None = None

    def fetch_catalog(self, window: QueryWindow) -> pd.DataFrame:
        del window
        if self.error is not None or self.catalog is None:
            raise RuntimeError(self.error or "목록 없음")
        return self.catalog.copy()

    def provider(self, request: DetailRequest) -> CoreDataProvider:
        return FakeProvider(request, self.frames[request.simulation_code])

    @property
    def sources(self) -> AutoUpdateSources:
        return AutoUpdateSources(fetch_catalog=self.fetch_catalog, detail_provider=self.provider)


class TickClock:
    """부를 때마다 몇 초씩 흐르는 고정 시계 — 기록 시각이 그 날짜에 찍힌다."""

    def __init__(self, start: datetime, step_seconds: float = 4.0) -> None:
        self.now = start
        self.step = timedelta(seconds=step_seconds)

    def __call__(self) -> datetime:
        current = self.now
        self.now += self.step
        return current


# ============================================================================== 시나리오 쓰기
def create_csv_scenario(
    repository: DuckDBScenarioRepository,
    variant: str,
    frame: pd.DataFrame,
    *,
    name: str,
    start_month: int,
    excluded: Sequence[str] = (),
    note: str,
) -> ScenarioSnapshot:
    spec = story.SOURCES[variant]
    prepared = prepare(variant, frame, source_type=story.SOURCE_TYPE_CSV)
    gate(prepared.reference_tables, name)
    return repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=spec.code,
            source_simulation_name=spec.name,
            source_type=story.SOURCE_TYPE_CSV,
            pipeline_version=story.PIPELINE_VERSION,
        ),
        prepared.reference_tables,
        ScenarioPreset(
            start_month=start_month,
            end_month=202812,
            included_processes=tuple(p for p in story.PROCESS_NAMES if p not in excluded),
        ),
        source_data=prepared.source_data,
        revision_name="원천 등록",
        note=note,
    )


def publish(
    repository: DuckDBScenarioRepository,
    snapshot: ScenarioSnapshot,
    release_name: str,
    note: str,
    *,
    expected_latest_release_no: int | None = None,
) -> int:
    gate(snapshot.tables, release_name)
    release = repository.publish_official_revision(
        snapshot.scenario.scenario_id,
        snapshot.revision.revision_id,
        release_name=release_name,
        note=note,
        expected_latest_release_no=expected_latest_release_no,
    )
    LOG.say(
        f"공식 v{release.release_no} 「{release_name}」 = {snapshot.scenario.scenario_name} "
        f"r{snapshot.revision.revision_no}"
    )
    return release.release_no


def save(
    repository: DuckDBScenarioRepository,
    snapshot: ScenarioSnapshot,
    tables: Mapping[str, pd.DataFrame],
    preset: ScenarioPreset,
    *,
    name: str,
    parent: str | None,
    note: str,
    virtual_products: Sequence[Mapping[str, str]] = (),
    check: bool = True,
) -> ScenarioSnapshot:
    if check:
        gate({**snapshot.tables, **tables}, name)
    saved = repository.save_revision(
        snapshot.scenario.scenario_id,
        revision_tables(tables),
        preset,
        revision_name=name,
        parent_revision_id=parent,
        note=note,
        virtual_products=virtual_products,
    )
    LOG.say(f"{saved.scenario.scenario_name} r{saved.revision.revision_no} 「{name}」 저장")
    return saved


def shift_equipment(
    tables: dict[str, pd.DataFrame],
    process: str,
    months: Sequence[int],
    delta: float,
    *,
    names: Sequence[str],
) -> None:
    for name in names:
        frame = tables[name].copy()
        column = {
            "RQ_EQP_OWN": "설비보유",
            "RQ_EQP_AVBL": "가용대수",
            "RQ_EQP_LENT": "설비대여평가",
        }[name]
        mask = frame["공정"].astype("string").str.strip().eq(process) & frame[
            "생산계획년월"
        ].astype("int64").isin(list(months))
        frame.loc[mask, column] = frame.loc[mask, column].astype("float64") + delta
        tables[name] = frame


def month_range(start: int, end: int) -> tuple[int, ...]:
    return story.months_between(start, end)


def merge_provenance(
    base: ScenarioSnapshot,
    donor: ScenarioSnapshot,
    start: int,
    end: int,
    policy: OverlapPolicy,
    comparison: pd.DataFrame,
    sources: pd.DataFrame,
    result: Mapping[str, pd.DataFrame],
    warnings: Sequence[str],
    kept_records: int,
) -> str:
    """`components/scenario_month_merge.py` 의 출처 메모와 같은 꼴."""
    labels = {
        "reject": "겹치면 저장 차단",
        "base": "겹치는 월은 베이스 사용",
        "donor": "겹치는 월은 덧붙일 쪽 사용",
    }
    overlap = sources.loc[sources["베이스"] & sources["덧붙일 쪽"], "생산계획년월"].tolist()
    differences = comparison.loc[comparison["비교"].ne("같음"), "표"].tolist()
    empty_months = missing_calendar_months(scenario_months(result))
    return (
        f"월 머지\n베이스: {source_description(base)}\n덧붙일 쪽: {source_description(donor)}\n"
        f"덧붙인 월 범위: {format_month(start)} ~ {format_month(end)} (양 끝 포함)\n"
        f"겹치는 월 처리: {labels[policy]}\n"
        f"겹치는 월: {', '.join(format_month(month) for month in overlap) if overlap else '없음'}\n"
        "월별 선택 출처:\n"
        + "\n".join(
            f"{format_month(month)}: {origin}"
            for month, origin in sources[["생산계획년월", "선택 출처"]].itertuples(
                index=False, name=None
            )
        )
        + "\n월 없는 4표:\n"
        + "\n".join(
            f"{name}: {rule} · 보충 {count}행"
            for name, rule, count in comparison[["표", "합치는 규칙", "보충 행 수"]].itertuples(
                index=False, name=None
            )
        )
        + f"\n두 원본의 무월 표 차이: {', '.join(differences) if differences else '없음'}\n"
        f"가상제품 복제 이력: {kept_records}건 보존 (동일 이력 중복 제거, 원본 충돌 차단, 결과 "
        "표에 남은 제품만)"
        + (f"\n결과의 빈 달: {format_month_runs(empty_months)}" if empty_months else "")
        + "".join(f"\n경고: {message}" for message in warnings)
    )


def source_description(snapshot: ScenarioSnapshot) -> str:
    return (
        f"{snapshot.scenario.scenario_name} [시나리오 {snapshot.scenario.scenario_id}] / "
        f"r{snapshot.revision.revision_no} {snapshot.revision.revision_name} "
        f"[리비전 {snapshot.revision.revision_id}]"
    )


def derived_preset(source: ScenarioSnapshot, tables: Mapping[str, pd.DataFrame]) -> ScenarioPreset:
    months = scenario_months(tables)
    return replace(
        source.preset,
        start_month=months[0],
        end_month=months[-1],
        included_processes=tuple(sorted(tables["RQ_REQB"]["공정"].dropna().astype(str).unique())),
        standard_target_processes=(),
        standard_target_start_date=None,
        standard_target_end_date=None,
        standard_target_show_detail=False,
    )


def create_derived(
    repository: DuckDBScenarioRepository,
    *,
    name: str,
    operation: str,
    source: ScenarioSnapshot,
    tables: dict[str, pd.DataFrame],
    gate_sources: Sequence[ScenarioSnapshot],
    provenance: str,
) -> ScenarioSnapshot:
    verdict = derived_save_verdict(tables, gate_sources)
    if not verdict.allowed:
        raise RuntimeError(f"{name}: 파생 저장 검사가 막았습니다 — {verdict.message}")
    if verdict.message:
        LOG.say(f"{name}: 파생 저장 경고 — {verdict.message[:160]}")
    snapshot = repository.create_scenario(
        ScenarioCreate(
            scenario_name=name,
            source_simulation_code=f"{operation}-{uuid4().hex[:12]}",
            source_simulation_name=source.scenario.scenario_name,
            source_type=operation,
            pipeline_version="scenario-transform-v1",
        ),
        tables,
        derived_preset(source, tables),
        revision_name="초기 리비전",
        note=provenance,
        virtual_products=(),
    )
    LOG.say(f"{name} 저장({operation}) · {format_month_range(scenario_months(tables))}")
    return snapshot


# ============================================================================== 공용 프로필 재료
def home_monthly(tables: Mapping[str, pd.DataFrame]) -> tuple[dict[int, float], dict[int, float]]:
    """HOME 기본(EDP 제외)의 달별 Density(억Gb)·Wafer(매)."""
    plan = filter_edp_plan(tables["RQ_PKG_PLAN"], False)
    monthly, _ = build_production_dashboard(plan, tables["RQ_CHIP_EQ"])
    _, wafer = calculate_chip_and_wafer_loads(plan, tables["RQ_YLD"], tables["RQ_CHIP_QTY"])
    density = {
        int(m): float(v) for m, v in zip(monthly["생산계획년월"], monthly["부하량"], strict=True)
    }
    wafers = wafer.groupby("생산계획년월")["물량"].sum()
    return density, {int(m): float(v) for m, v in zip(wafers.index, wafers, strict=True)}


def past_factor(month: int) -> float:
    index = story.PAST_MONTHS.index(month)
    return 0.80 + 0.12 * index / (len(story.PAST_MONTHS) - 1)


def past_data(v4: Mapping[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict[int, float]]:
    density, wafer = home_monthly(v4)
    first = 202611
    monthly = pd.DataFrame(
        {
            "생산계획년월": list(story.PAST_MONTHS),
            "Density": [round(density[first] * past_factor(m), 2) for m in story.PAST_MONTHS],
            "Wafer Total": [round(wafer[first] * past_factor(m), 0) for m in story.PAST_MONTHS],
        }
    )
    plan = v4["RQ_PKG_PLAN"].copy()
    plan["생산수량"] = pd.to_numeric(plan["생산수량"], errors="coerce")
    plan = plan.loc[
        plan["생산계획년월"].astype("int64").eq(first)
        & plan["양산구분"].astype("string").eq("양산")
        & ~plan["제품정보"].astype("string").eq(story.NEW_PRODUCT)
    ]
    lines = plan.groupby(["제품정보", "Stack", "Customer"], as_index=False)["생산수량"].sum()
    detail_rows = [
        {
            "생산계획년월": month,
            "제품정보": product,
            "Stack": stack,
            "Customer": customer,
            "생산수량": round(float(quantity) * past_factor(month), 3),
        }
        for month in story.PAST_MONTHS
        for product, stack, customer, quantity in lines.itertuples(index=False)
    ]
    securement_rows = [
        {
            "생산계획년월": month,
            "공정": process,
            "확보율": story.PAST_LOW_CELLS.get(
                (month, process),
                round(1.05 + 0.45 * story.stable_fraction("past", process, month), 3),
            ),
        }
        for month in story.PAST_MONTHS
        for process in story.PROCESS_NAMES
    ]
    past_density = dict(zip(monthly["생산계획년월"], monthly["Density"], strict=True))
    tables = {
        "월별": monthly,
        "계획": pd.DataFrame(detail_rows),
        "확보율": pd.DataFrame(securement_rows),
    }
    return tables, {**past_density, **density}


# ============================================================================== 본 흐름
@dataclass
class Built:
    repository: DuckDBScenarioRepository
    ids: dict[str, str] = field(default_factory=dict)  # 별명 → scenario_id
    revisions: dict[str, str] = field(default_factory=dict)  # 별명 → revision_id
    run_results: list[tuple[str, str, str]] = field(default_factory=list)  # (회차, status, reason)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)


def build(database: Path) -> Built:
    calibration = calibrate_cache()
    verify_calibration(calibration)
    equipment, scale = calibration.equipment, calibration.scale
    frames = {
        variant: core_frame.build_core_frame(variant, equipment, scale)
        for variant in core_frame.VARIANTS
    }
    LOG.say("원천판 행 수: " + " · ".join(f"{k} {len(v):,}" for k, v in frames.items()))

    repository = DuckDBScenarioRepository(database)
    repository.initialize()
    repository.initialize_global_display_order(RULES)
    built = Built(repository, frames=frames)

    # --- S3(W36) → 공식 v1
    s3 = create_csv_scenario(
        repository,
        "W36",
        frames["W36"],
        name=story.S3_NAME,
        start_month=202609,
        note="26년 9월 정기 검토 원천",
    )
    built.ids["S3"], built.revisions["S3r1"] = s3.scenario.scenario_id, s3.revision.revision_id
    publish(repository, s3, "9월 공식안", "9월 정기 검토 확정")

    # --- S2(W40) → 공식 v2, r2·r3(가지)
    s2 = create_csv_scenario(
        repository,
        "W40",
        frames["W40"],
        name=story.S2_NAME,
        start_month=202610,
        excluded=(story.MANUAL_OFF_PROCESS,),
        note="26년 10월 정기 검토 원천 · Tape Pocket Inspection 은 B/N 집계에서 뺌",
    )
    built.ids["S2"], built.revisions["S2r1"] = s2.scenario.scenario_id, s2.revision.revision_id
    publish(repository, s2, "10월 공식안", "10월 정기 검토 확정")
    tables = revision_tables(s2.tables)
    shift_equipment(
        tables, "Wafer Saw", month_range(202701, 202703), -2.0, names=("RQ_EQP_OWN", "RQ_EQP_AVBL")
    )
    s2r2 = save(
        repository,
        s2,
        tables,
        s2.preset,
        name="Wafer Saw 반입 지연 반영",
        parent=s2.revision.revision_id,
        note="반입 지연 2대 · 3개월",
    )
    built.revisions["S2r2"] = s2r2.revision.revision_id
    tables = revision_tables(s2.tables)
    yld = tables["RQ_YLD"].copy()
    mask = yld["제품정보"].astype("string").eq("DEMO-H12A")
    yld.loc[mask, "BE_수율"] = (yld.loc[mask, "BE_수율"].astype("float64") * 0.99).round(6)
    tables["RQ_YLD"] = yld
    s2r3 = save(
        repository,
        s2,
        tables,
        s2.preset,
        name="수율 보정 가지",
        parent=s2.revision.revision_id,
        note="r1 에서 갈라 수율만 보정",
    )
    built.revisions["S2r3"] = s2r3.revision.revision_id

    # --- 자동 갱신 설정 v1(끔)
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(False, time(7, 0), "PSM", 0.80),
        expected_version=0,
        changed_by=story.ADMIN_NAME,
    )

    # --- 자동 갱신 회차 ①~④
    run_frames = {"DEMO-SIM-2643": frames["W43"], "DEMO-SIM-2644": frames["W44"]}
    plan = (
        ("① 10-27", date(2026, 10, 27), ("W40", "PSS43")),
        ("② 10-28", date(2026, 10, 28), ("W40", "PSS43", "W43")),
        ("③ 10-29", date(2026, 10, 29), ("W40", "PSS43", "W43", "W44")),
        ("④ 11-01", date(2026, 11, 1), ("W40", "PSS43", "W43", "W44")),
    )
    for label, day, groups in plan:
        fake = FakeBigDataQuery(catalog_frame(*groups), run_frames)
        result = run_auto_official_update(
            repository,
            trigger=TRIGGER_SCHEDULED,
            run_day=day,
            sources=fake.sources,
            clock=TickClock(datetime.combine(day, time(7, 0))),
        )
        if result.run is None:
            raise RuntimeError(f"자동 갱신 {label} 회차를 잡지 못했습니다: {result.not_run_reason}")
        run = result.run
        built.run_results.append((label, run.status, run.reason or ""))
        LOG.say(f"자동 갱신 {label}: {run.status} — {(run.reason or '')[:200]}")
        if run.simulation_code == "DEMO-SIM-2643" and run.created_scenario_id:
            built.ids["S8"] = run.created_scenario_id
            built.revisions["S8r1"] = str(run.base_revision_id)
        if run.simulation_code == "DEMO-SIM-2644" and run.created_scenario_id:
            built.ids["S1"] = run.created_scenario_id
            built.revisions["S1r1"] = str(run.base_revision_id)
            built.revisions["S1r2"] = str(run.filtered_revision_id)

    # --- S1 정리 → r3 → 공식 v4
    repository.rename_scenario(built.ids["S1"], story.S1_NAME)
    s1r2 = repository.load_revision(built.revisions["S1r2"])
    tables = revision_tables(s1r2.tables)
    own = tables["RQ_EQP_OWN"].set_index(["생산계획년월", "공정"])["설비보유"]
    lent = tables["RQ_EQP_LENT"].set_index(["생산계획년월", "공정"])["설비대여평가"]
    avbl = tables["RQ_EQP_AVBL"].copy()
    for month in story.DAF_MISMATCH_MONTHS:
        mask = avbl["생산계획년월"].astype("int64").eq(month) & avbl["공정"].astype("string").eq(
            "DAF Attach"
        )
        avbl.loc[mask, "가용대수"] = (
            float(own[(month, "DAF Attach")]) - float(lent[(month, "DAF Attach")]) - 1.0
        )
    tables["RQ_EQP_AVBL"] = avbl
    preset = replace(
        s1r2.preset,
        start_month=202601,
        end_month=202812,
        standard_target_processes=("Pre B/D", "TC Bonding", "Mold", "AVI"),
        standard_target_start_date=date(2026, 11, 2),
        standard_target_end_date=date(2027, 3, 31),
        standard_target_show_detail=True,
    )
    s1r3 = save(
        repository,
        s1r2,
        tables,
        preset,
        name="11월 정기 확정 · 가용 보정",
        parent=s1r2.revision.revision_id,
        note="PSM W44 원천 · DAF Attach 가용 −1(27.02~04, 반출 대기 1대)",
    )
    built.revisions["S1r3"] = s1r3.revision.revision_id
    publish(
        repository,
        s1r3,
        "26년 11월 정기 공식안",
        "11/1 정기 검토 확정",
        expected_latest_release_no=3,
    )

    # --- S8 r2(효율 채움)
    s8 = repository.load_revision(built.revisions["S8r1"])
    tables = revision_tables(s8.tables)
    run_rate = tables["RQ_RUN_RATE"].copy()
    blank_month, blank_process = story.W43_BLANK_RUN_RATE
    is_process = run_rate["공정"].astype("string").eq(blank_process)
    months = run_rate["생산계획년월"].astype("int64")
    previous_rates = run_rate.loc[is_process & months.eq(blank_month - 1)].set_index("양산구분")[
        "CAPA_RUN_RATE"
    ]
    target = is_process & months.eq(blank_month)
    run_rate.loc[target, "CAPA_RUN_RATE"] = (
        run_rate.loc[target, "양산구분"].map(previous_rates).astype("float64")
    )
    tables["RQ_RUN_RATE"] = run_rate
    s8r2 = save(
        repository,
        s8,
        tables,
        s8.preset,
        name="효율 빈칸 채움",
        parent=s8.revision.revision_id,
        note="TC Bonding 27.04 효율 원천 누락 보충",
    )
    built.revisions["S8r2"] = s8r2.revision.revision_id

    # --- S4 증산(복제) r1·r2
    source = repository.load_revision(built.revisions["S1r3"])
    tables = revision_tables(source.tables)
    plan_table = tables["RQ_PKG_PLAN"].copy()
    later = plan_table["생산계획년월"].astype("int64").ge(story.CASE_UP_FROM)
    quantity = pd.to_numeric(plan_table["생산수량"], errors="coerce")
    plan_table.loc[later, "생산수량"] = (quantity.loc[later] * story.CASE_UP_FACTOR).round(4)
    tables["RQ_PKG_PLAN"] = plan_table
    gate({**source.tables, **tables}, story.S4_NAME)
    case_preset = replace(
        source.preset,
        standard_target_processes=(),
        standard_target_start_date=None,
        standard_target_end_date=None,
        standard_target_show_detail=False,
    )
    s4 = repository.create_scenario(
        ScenarioCreate(
            story.S4_NAME,
            "DEMO-CASE-UP8",
            "증산 검토용 복제",
            "DUCKDB_SCENARIO_CLONE",
            CLONE_PIPELINE_VERSION,
        ),
        source.tables,
        case_preset,
        source_data=None,
        revision_tables=tables,
        revision_name="증산 계획 반영",
        note="27.01~ 전 제품 계획 ×1.08",
    )
    built.ids["S4"], built.revisions["S4r1"] = s4.scenario.scenario_id, s4.revision.revision_id
    LOG.say(f"{story.S4_NAME} r1 저장(복제)")
    tables = revision_tables(s4.tables)
    shift_equipment(
        tables,
        "TC Bonding",
        month_range(story.CASE_TCB_FROM, 202812),
        float(story.CASE_TCB_EXTRA),
        names=("RQ_EQP_OWN", "RQ_EQP_AVBL"),
    )
    s4r2 = save(
        repository,
        s4,
        tables,
        s4.preset,
        name="증산 · TC Bonding 2대 추가",
        parent=s4.revision.revision_id,
        note="27.03~ TC Bonding 신규 2대(28.02 부족 완화)",
    )
    built.revisions["S4r2"] = s4r2.revision.revision_id

    # --- S5 Hybrid(BigDataQuery 손 등록) r1·r2
    prepared = prepare(
        "HYBRID",
        frames["HYBRID"],
        source_type=story.SOURCE_TYPE_BDQ,
        registered_at=datetime(2026, 10, 29, 10, 0),
    )
    registration = save_bigdataquery_scenario(
        repository,
        prepared,
        full_data_scenario_preset(prepared.reference_tables),
        scenario_name=story.S5_NAME,
        revision_name="BigDataQuery 등록",
        note=registration_note(
            "손 등록 · Hybrid 도입 검토", QueryWindow(date(2026, 10, 22), date(2026, 11, 1))
        ),
    )
    s5 = registration.snapshot
    built.ids["S5"], built.revisions["S5r1"] = s5.scenario.scenario_id, s5.revision.revision_id
    LOG.say(
        f"{story.S5_NAME} r1 저장(BigDataQuery 손 등록) · 등록 Capa 멈춤 "
        f"{registration.capacity.stopped}"
    )
    tables = {name: frame.copy(deep=True) for name, frame in s5.tables.items()}
    requests = [VirtualProductRequest(*item) for item in story.VIRTUAL_PRODUCTS]
    for request in requests:
        tables.update(clone_product(tables, request))
    plan_table = tables["RQ_PKG_PLAN"].copy()
    keys = ["생산계획년월", "양산구분", "CS", "Stack", "Capa Code", "Customer", "Pack Code"]
    source_rows = plan_table.loc[plan_table["제품정보"].astype("string").eq("DEMO-H16A")].set_index(
        keys
    )["생산수량"]
    virtual = plan_table["제품정보"].astype("string").eq("DEMO-H16V") & plan_table[
        "생산계획년월"
    ].astype("int64").ge(story.HYBRID_START)
    lookup = pd.MultiIndex.from_frame(plan_table.loc[virtual, keys])
    plan_table.loc[virtual, "생산수량"] = (
        pd.to_numeric(source_rows.reindex(lookup), errors="coerce").to_numpy()
        * story.VIRTUAL_PLAN_SHARE
    ).round(4)
    tables["RQ_PKG_PLAN"] = plan_table
    lot = tables["RQ_LOT_RATIO"]
    drop = lot["공정"].astype("string").eq(story.HYBRID_PROCESS.name) & lot["생산계획년월"].astype(
        "int64"
    ).between(202801, 202806)
    tables["RQ_LOT_RATIO"] = lot.loc[~drop].reset_index(drop=True)
    s5r2 = save(
        repository,
        s5,
        tables,
        s5.preset,
        name="가상 제품 2종 · 측정률 일부 미정",
        parent=s5.revision.revision_id,
        note=(
            "DEMO-H16V(27.07~ H16A 의 30%) · DEMO-H12V(계획 0) 복제 · "
            "Hybrid Bonding 28.01~06 Lot 측정률 미정"
        ),
        virtual_products=[
            asdict(VirtualProductRecord.from_request(request)) for request in requests
        ],
    )
    built.revisions["S5r2"] = s5r2.revision.revision_id

    # --- S6 월 머지 · S7 연도 Shift
    base = repository.load_revision(built.revisions["S2r1"], apply_global_display_order=False)
    donor = repository.load_revision(built.revisions["S4r1"], apply_global_display_order=False)
    base_tables, donor_tables = (
        copy_scenario_tables(base.tables),
        copy_scenario_tables(donor.tables),
    )
    start, end = story.MERGE_RANGE
    policy: OverlapPolicy = "donor"
    comparison = compare_non_monthly_tables(base_tables, donor_tables)
    sources = preview_month_sources(base_tables, donor_tables, start, end, overlap_policy=policy)
    merged = merge_scenario_months(base_tables, donor_tables, start, end, overlap_policy=policy)
    gaps = merged_table_gaps(merged)
    if gaps.blocking:
        raise RuntimeError("월 머지 결손: " + " / ".join(gaps.blocking))
    history = merge_result_virtual_products(
        virtual_product_records(repository.list_virtual_products(base.revision.revision_id)),
        virtual_product_records(repository.list_virtual_products(donor.revision.revision_id)),
        base_tables=base_tables,
        donor_tables=donor_tables,
        result_tables=merged,
    )
    provenance = merge_provenance(
        base,
        donor,
        start,
        end,
        policy,
        comparison,
        sources,
        merged,
        gaps.warnings,
        len(history.records),
    )
    s6 = create_derived(
        repository,
        name="월 머지 · 10월 정기 + 증산안(27.07~)",
        operation="SCENARIO_MONTH_MERGE",
        source=base,
        tables=merged,
        gate_sources=(base, donor),
        provenance=provenance,
    )
    built.ids["S6"], built.revisions["S6r1"] = s6.scenario.scenario_id, s6.revision.revision_id
    original = copy_scenario_tables(base.tables)
    shifted = shift_scenario_years(original, 1)
    provenance = (
        f"연도 Shift\n원본: {source_description(base)}\n이동 연수: +1년\n"
        f"이동 전: {format_month_range(scenario_months(original))}\n"
        f"이동 후: {format_month_range(scenario_months(shifted))}\n"
        "변경: 12개 표의 생산계획년월 연도만 이동\n월 없는 4표 및 나머지 값: 원본 유지\n"
        "가상제품 복제 이력: 원본 0건 보존"
    )
    s7 = create_derived(
        repository,
        name="연도 Shift · 10월 정기 +1년",
        operation="SCENARIO_YEAR_SHIFT",
        source=base,
        tables=shifted,
        gate_sources=(base,),
        provenance=provenance,
    )
    built.ids["S7"], built.revisions["S7r1"] = s7.scenario.scenario_id, s7.revision.revision_id

    # --- S9(복제 → 보관), S3 보관, 목록 차례
    s2r2_snapshot = repository.load_revision(built.revisions["S2r2"])
    s9 = repository.create_scenario(
        ScenarioCreate(
            story.S9_NAME,
            "DEMO-TMP-PASTE",
            "붙여넣기 시험",
            "DUCKDB_SCENARIO_CLONE",
            CLONE_PIPELINE_VERSION,
        ),
        s2r2_snapshot.tables,
        s2r2_snapshot.preset,
        source_data=None,
        revision_tables=revision_tables(s2r2_snapshot.tables),
        revision_name="초기 리비전",
        note="붙여넣기 시험용 임시 복제(지워도 됨)",
    )
    built.ids["S9"] = s9.scenario.scenario_id
    repository.archive_scenario(built.ids["S9"])
    repository.archive_scenario(built.ids["S3"])
    LOG.say("보관: S9(이력 없음) · S3(공식 v1 이력)")
    repository.reorder_scenarios(
        [built.ids[key] for key in ("S1", "S2", "S4", "S5", "S6", "S7", "S8")]
    )

    # --- 공용 프로필
    write_profiles(built, repository.load_revision(built.revisions["S1r3"]).tables)

    # --- 11-02 07:00 예약 회차 — 목록 조회 중에 앱이 꺼져 「실행 중」으로 남은 기록(dyn-admin-53).
    leave_interrupted_run(repository)
    LOG.say(
        "자동 갱신 11-02 07:00 예약: RUNNING(목록 조회 단계) — CAPA_AUTO_OFFICIAL_UPDATE=1 로 앱을 "
        "띄우면 예약 스레드가 "
        "「앱이 이 회차를 끝내기 전에 꺼져 중단됐습니다」 오류로 닫는다"
    )

    # --- ⑤ 수동 실행(오류) → 설정 v2(켬)
    fake = FakeBigDataQuery(
        None, run_frames, error="사외 PC 라 bigdataquery 패키지가 없어 목록을 조회하지 못했습니다"
    )
    runner_logger = logging.getLogger("capa_simulation.auto_official_update_runner")
    previous_level = runner_logger.level
    runner_logger.setLevel(logging.CRITICAL)  # 일부러 낸 오류 회차 — 앱 로그의 traceback 은 감춘다.
    try:
        result = run_auto_official_update(
            repository,
            trigger=TRIGGER_MANUAL,
            sources=fake.sources,
            clock=TickClock(datetime(2026, 11, 2, 8, 30)),
        )
    finally:
        runner_logger.setLevel(previous_level)
    assert result.run is not None
    built.run_results.append(("⑤ 11-02 수동", result.run.status, result.run.reason or ""))
    LOG.say(f"자동 갱신 ⑤ 11-02 수동: {result.run.status} — {(result.run.reason or '')[:200]}")
    settings = repository.load_auto_official_update_settings()
    repository.replace_auto_official_update_settings(
        AutoUpdateConfig(True, time(7, 0), "PSM", 0.80),
        expected_version=settings.version,
        changed_by=story.ADMIN_NAME,
    )
    return built


def leave_interrupted_run(repository: DuckDBScenarioRepository) -> str:
    """앱이 회차 도중에 꺼진 자리를 남긴다 — 러너가 쓰는 저장소 메서드(선점 → 단계 진행)를 같은
    차례로 부르고 끝맺음(`finish`)만 하지 않는다. 러너는 `BaseException` 까지 잡아 기록을 닫으므로,
    프로세스가 죽은 때의 「실행 중」 행은 이 길로만 만들 수 있다(SQL 쓰기 없음). 예약 스레드가
    기동할 때 이 행을 오류로 닫는다(`auto_update_scheduler._abandon_interrupted` →
    `abandon_interrupted_runs`)."""
    started = story.INTERRUPTED_RUN_AT
    settings = repository.load_auto_official_update_settings()
    run_id = repository.claim_auto_official_update_run(
        run_key=scheduled_run_key(started.date()),
        trigger_kind=TRIGGER_SCHEDULED,
        run_date=started.date(),
        started_at=started,
        keyword=settings.config.keyword,
        threshold=settings.config.threshold,
        settings_version=settings.version,
    )
    if run_id is None:
        raise RuntimeError("11-02 예약 회차를 잡지 못했습니다(이미 잡힌 키).")
    repository.update_auto_official_update_run(run_id, {"stage": "baseline"})
    baseline = current_official_baseline(repository)
    repository.update_auto_official_update_run(
        run_id, {"baseline_release_no": baseline.release_no, "baseline_week": baseline.week}
    )
    repository.update_auto_official_update_run(run_id, {"stage": "catalog"})
    return run_id


def write_profiles(built: Built, v4: Mapping[str, pd.DataFrame]) -> None:
    repository = built.repository
    source = story.PROFILE_SOURCE
    repository.replace_global_securement_threshold(
        story.SECURE_DEFAULT,
        story.WARNING_DEFAULT,
        threshold_rows(),
        source=source,
        expected_version=0,
    )
    repository.replace_global_comparison_scenario(
        built.ids["S2"], built.revisions["S2r1"], source=source
    )
    repository.replace_global_main_case(1, built.ids["S4"], built.revisions["S4r1"], source=source)
    repository.replace_global_main_case(2, built.ids["S5"], built.revisions["S5r2"], source=source)
    repository.replace_global_key_process_presets(list(story.KEY_PROCESS_PRESETS), source=source)
    repository.replace_global_execution_capacity(
        pd.DataFrame(
            story.EXECUTION_ADJUSTMENTS, columns=["생산계획년월", "공정", "증감 확보율", "비고"]
        ),
        source=source,
    )
    past_tables, density = past_data(v4)
    repository.replace_global_advance_load(
        pd.DataFrame(
            [(month, round(density[month] * pct, 2)) for month, pct in story.ADVANCE_LOAD_PCT],
            columns=["생산계획년월", "선행 물량"],
        ),
        source=source,
    )
    repository.replace_global_advance_shipment(
        pd.DataFrame(
            [(month, round(density[month] * pct, 1)) for month, pct in story.ADVANCE_SHIPMENT_PCT],
            columns=["생산계획년월", "선행 입고"],
        ),
        source=source,
    )
    repository.replace_global_summary_note(story.SUMMARY_NOTE, source=source)
    repository.replace_global_top5_band(*story.TOP5_BAND, source=source)
    repository.replace_global_past_data(past_tables, source=source)
    try:
        repository.replace_global_process_rename(
            pd.DataFrame(story.PROCESS_RENAMES, columns=["공정", "표시명"]), source="웹 직접 편집"
        )
    except ValueError as exc:
        LOG.say(f"공정 표시명 겹침 규칙이 막혀 Shipping Inspection → AVI 를 뺍니다: {exc}")
        repository.replace_global_process_rename(
            pd.DataFrame(
                [rule for rule in story.PROCESS_RENAMES if rule != story.PROCESS_RENAME_OVERLAP],
                columns=["공정", "표시명"],
            ),
            source="웹 직접 편집",
        )
    posts = [
        (
            "질문",
            "Pre B/D 12월 확보율 계산 기준 문의",
            "26.12 Pre B/D 가 96% 로 나오는데 대여 2대가 가용에서 빠진 값인지 궁금합니다.",
            "DEMO 담당 A",
        ),
        (
            "개선 요청",
            "필요 단축 일정 카드에 공정 표시명 적용",
            "카드 제목이 원본 공정명으로 나와 표시명(SAM 검사 등)으로 보이면 좋겠습니다.",
            "DEMO 담당 B",
        ),
        (
            "오류 신고",
            "공정 필터 팝업의 자동 off 표지 확인 부탁",
            "Laser Marking 이 자동 off 로 빠졌는데 표지의 확보율 달이 맞는지 확인 부탁드립니다.",
            "DEMO 담당 A",
        ),
        (
            "공지",
            "11월 정기 공식안(v4) 발행 안내",
            "PSM W44 원천 기준 26년 11월 정기 공식안을 발행했습니다. DAF Attach 27.02~04 가용 "
            "1대를 줄였습니다.",
            story.ADMIN_NAME,
        ),
    ]
    ids = [
        repository.create_voc_post(category=c, title=t, body=b, author=a) for c, t, b, a in posts
    ]
    repository.set_voc_post_resolved(ids[1], resolved=True)
    repository.create_voc_reply(
        post_id=ids[2],
        body="확인했습니다. 28.05 최저 확보율 76% 가 표지에 들어갑니다.",
        author=story.ADMIN_NAME,
    )
    repository.create_voc_reply(
        post_id=ids[2],
        body="확인 감사합니다. 다음 주 정기 회의에서 다시 보겠습니다.",
        author="DEMO 담당 A",
    )
    LOG.say("공용 프로필·VOC 저장")


# ============================================================================== 점검(3-3)
def status_of(rate: float, month: int, rules: SecurementThresholds) -> str:
    return rules.status(rate, month)


def run_checks(built: Built, database: Path, notes: Path) -> dict[str, object]:
    repository = built.repository
    rules = thresholds()
    counts: dict[str, object] = {}
    latest = repository.latest_official_release()
    LOG.check(
        latest is not None
        and latest.revision_id == built.revisions["S1r3"]
        and latest.release_no == 4,
        "공식 v4 = S1 r3",
        "" if latest is None else f"v{latest.release_no} {latest.release_name}",
    )
    v4 = repository.load_revision(built.revisions["S1r3"])
    outcome = full_capacity_outcome(v4.tables, v4.tables)
    LOG.check(
        outcome.error is None, "v4 full_capacity_outcome 오류 없음", str(outcome.error or "")[:200]
    )
    LOG.check(density_error(v4.tables) is None, "v4 Density 오류 없음")
    unit, required, rates = table_rates(v4.tables)
    rate_map = {
        (int(m), str(p)): float(r)
        for m, p, r in rates[["생산계획년월", "공정", "확보율"]].itertuples(index=False)
        if pd.notna(r)
    }
    req_map = {
        (int(m), str(p)): float(r)
        for m, p, r in rates[["생산계획년월", "공정", "소요대수"]].itertuples(index=False)
    }
    avl_map = {
        (int(m), str(p)): float(r)
        for m, p, r in rates[["생산계획년월", "공정", "가용대수"]].itertuples(index=False)
    }
    for month, process, percent, expected_status in story.STORY_EXPECTED:
        rate = rate_map[(month, process)]
        shown = round(rate * 100, 1)
        status = status_of(rate, month, rules)
        LOG.check(
            abs(shown - percent) < 1e-9 and status == expected_status,
            f"이야기 칸 {format_month(month)} {process}",
            f"{shown:.1f}% {status}(기대 {percent:.1f}% {expected_status}) · 소요 "
            f"{req_map[(month, process)]:.2f} · 가용 {avl_map[(month, process)]:g}",
        )
    story_req = req_map[(story.STORY_MONTH, story.STORY_PROCESS)]
    story_avl = avl_map[(story.STORY_MONTH, story.STORY_PROCESS)]
    LOG.check(
        round(story_req, 1) == story.STORY_REQUIRED and story_avl == story.STORY_AVAILABLE,
        "Pre B/D 26.12 소요 33.3 · 가용 32",
        f"소요 {story_req:.3f} · 가용 {story_avl:g} · +2 → "
        f"{(story_avl + 2) / story_req * 100:.1f}%",
    )
    cells = rates.merge(
        v4.tables["RQ_EQP_OWN"][["생산계획년월", "공정", "설비보유"]],
        on=["생산계획년월", "공정"],
        how="left",
    ).merge(
        v4.tables["RQ_EQP_LENT"][["생산계획년월", "공정", "설비대여평가"]],
        on=["생산계획년월", "공정"],
        how="left",
    )
    cells["판정"] = [
        status_of(float(rate), int(month), rules) if pd.notna(rate) else ""
        for month, rate in zip(cells["생산계획년월"], cells["확보율"], strict=True)
    ]
    cells["확보율(%)"] = (cells["확보율"].astype("float64") * 100).round(1)
    cells = cells.sort_values(["공정", "생산계획년월"]).reset_index(drop=True)
    cells[
        [
            "생산계획년월",
            "공정",
            "설비보유",
            "설비대여평가",
            "가용대수",
            "소요대수",
            "확보율(%)",
            "판정",
        ]
    ].to_csv(notes / "v4_cells.csv", index=False, encoding="utf-8-sig")
    falling = [
        str(process)
        for process, group in cells.groupby("공정")
        if (
            group.sort_values("생산계획년월")["설비보유"].astype("float64").diff().dropna() < 0
        ).any()
    ]
    LOG.check(
        not falling,
        "v4 보유(RQ_EQP_OWN)는 공정마다 달이 갈수록 줄지 않음(가용 dip 은 대여로)",
        ", ".join(falling),
    )
    dips = cells.loc[cells["설비대여평가"].astype("float64").gt(1)]
    LOG.say(
        "v4 대여 > 1 칸(가용을 내린 이야기·반입 늦은 칸): "
        + " · ".join(
            f"{format_month(int(m))} {p} 대여 {lent:g}"
            for m, p, lent in dips[["생산계획년월", "공정", "설비대여평가"]].itertuples(index=False)
        )
    )
    minimums = process_minimum_rates(rates)
    below = sorted(m.process for m in minimums if m.min_rate < 0.80)
    LOG.check(
        below == [story.AUTO_OFF_PROCESS],
        "최저 확보율 80% 미만 공정 = Laser Marking 하나",
        ", ".join(below),
    )
    status_counts = Counter(
        status_of(rate, month, rules)
        for (month, _), rate in rate_map.items()
        if month in story.PLAN_MONTHS and _ in story.PROCESS_NAMES
    )
    counts["판정 분포(v4 24공정×26개월)"] = dict(status_counts)
    LOG.say(f"판정 분포: {dict(status_counts)}")
    LOG.check(
        8 <= status_counts["shortage"] <= 12 and 15 <= status_counts["warning"] <= 25,
        "판정 분포 목표(부족 8~12 · 경고 15~25)",
        str(dict(status_counts)),
    )

    # Summary 6개월 B/N
    first_plan = int(pd.to_numeric(v4.tables["RQ_PKG_PLAN"]["생산계획년월"]).min())
    last_plan = int(pd.to_numeric(v4.tables["RQ_PKG_PLAN"]["생산계획년월"]).max())
    # 계획 첫 달부터 여섯 달 — 이야기 B/N 차례를 보는 창(Summary 화면의 기본 창과는 따로).
    months = summary_months(max(v4.preset.start_month, first_plan), last_plan)[:SUMMARY_MONTH_COUNT]
    ranking = build_monthly_bottleneck_ranking(rates, list(v4.preset.included_processes))
    top = build_monthly_bottlenecks_from_ranking(ranking)
    bn = {
        int(m): (str(p), float(r))
        for m, p, r in top[["생산계획년월", "공정", "확보율"]].itertuples(index=False)
    }
    actual = [(m, bn[m][0], status_of(bn[m][1], m, rules)) for m in months]
    LOG.check(
        actual == list(story.SUMMARY_EXPECTED),
        "Summary 26.11–27.04 B/N 차례",
        " · ".join(f"{format_month(m)} {p}({s}, {bn[m][1] * 100:.1f}%)" for m, p, s in actual),
    )
    others = [
        bn[m]
        for m in story.PLAN_MONTHS
        if m not in {c[0] for c in story.STORY_EXPECTED} and m in bn
    ]
    LOG.say("이야기 칸 없는 달 B/N: " + " · ".join(f"{p} {r * 100:.1f}%" for p, r in others))

    # 소요대수 밖 수요·제외 사유·PKG 안내
    exclusions = required_exclusion_counts(required)
    counts["소요대수 밖 수요"] = exclusions._asdict()
    LOG.check(
        exclusions.excluded_plans > 0
        and exclusions.blank_plans > 0
        and exclusions.unrouted_loads > 0,
        "소요대수 밖 수요(계획 쪽) > 0",
        str(exclusions._asdict()),
    )
    reasons = set(unit.attrs[CAPACITY_EXCLUSIONS_ATTR]["제외사유"].unique())
    LOG.check(
        {"UPEH 0 이하", "CAPA_RUN_RATE 0 이하"} <= reasons,
        "대당 Capa 제외 사유 2종",
        ", ".join(sorted(reasons)),
    )
    route_exclusions = required.attrs[REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR]
    pkg_rows = (
        int(route_exclusions["제외사유"].eq(PKG_UNCOUNTED_REASON).sum())
        if not route_exclusions.empty
        else 0
    )
    LOG.check(pkg_rows > 0, "PKG 규칙 안내(Buffer 로만 계수) 건수 > 0", f"{pkg_rows}행")

    # 자동 갱신 기록
    runs = repository.list_auto_official_update_runs()
    statuses = Counter(run.status for run in runs)
    counts["자동 갱신 회차"] = dict(statuses)
    LOG.check(
        len(runs) == 6
        and statuses
        == Counter(
            {
                STATUS_SKIPPED: 2,
                STATUS_PUBLISH_SKIPPED: 1,
                STATUS_PUBLISHED: 1,
                STATUS_ERROR: 1,
                STATUS_RUNNING: 1,
            }
        ),
        "자동 갱신 기록 6건(건너뜀 2 · 발행 건너뜀 1 · 발행 1 · 오류 1 · 실행 중 1)",
        str(dict(statuses)),
    )
    running = [run for run in runs if run.status == STATUS_RUNNING]
    LOG.check(
        len(running) == 1
        and running[0].started_at == story.INTERRUPTED_RUN_AT
        and running[0].stage == "catalog"
        and running[0].trigger_kind == TRIGGER_SCHEDULED,
        "끊긴 회차 = 11-02 07:00 예약 · 목록 조회 단계에서 「실행 중」",
        ""
        if not running
        else f"{running[0].started_at} {running[0].trigger_kind} {running[0].stage}",
    )

    # 선행 입고 — HOME 칸 글자(소수 첫째)가 +0.0 으로 숨지 않고, Summary 요약 기간에도 하나 이상
    # 선다.
    shipment_rows = repository.load_global_advance_shipment().rows
    home_labels = [month_label(month) for month, _ in story.ADVANCE_SHIPMENT_PCT]
    home_notes = [text for text, _hover in advance_shipment_notes(shipment_rows, home_labels)]
    summary_labels = [month_label(month) for month in months]
    summary_notes = [
        text for text, _hover in advance_shipment_notes(shipment_rows, summary_labels) if text
    ]
    LOG.check(
        all(home_notes) and bool(summary_notes),
        "선행 입고 칸 글자 4개 모두 보임 · Summary 요약 기간 안 1개 이상",
        f"HOME {dict(zip(home_labels, home_notes, strict=True))} · Summary {summary_notes}",
    )

    # 표시명 — 공식 v4 의 보유 공정에 없는 원본 2(AVI-PKG·Hybrid Bonding), Case2(S5 r2)에서는
    # 1(AVI-PKG).
    rename = repository.load_global_process_rename()
    labels = process_labels_from_rules(rename.rules, rename.version)

    def owned(tables: Mapping[str, pd.DataFrame]) -> list[str]:
        return sorted(
            tables["RQ_MODULE"]["공정"].astype("string").str.strip().dropna().unique().tolist()
        )

    unmatched_v4 = labels.unmatched(owned(v4.tables))
    unmatched_case2 = labels.unmatched(
        owned(repository.load_revision(built.revisions["S5r2"]).tables)
    )
    LOG.check(
        len(rename.rules) == len(story.PROCESS_RENAMES)
        and sorted(unmatched_v4) == sorted(story.PROCESS_RENAME_UNOWNED)
        and unmatched_case2 == ["AVI-PKG"],
        f"Proc Rename {len(rename.rules)}건 · 보유 공정에 없는 원본 v4 2 · Case2 1",
        f"v4 {unmatched_v4} · Case2 {unmatched_case2}",
    )
    exclusions_rows = repository.list_auto_official_update_exclusions()
    kinds = Counter((row.kind, row.process) for row in exclusions_rows)
    LOG.check(
        kinds
        == Counter(
            {
                (EXCLUSION_AUTO, story.AUTO_OFF_PROCESS): 1,
                (EXCLUSION_INHERITED, story.MANUAL_OFF_PROCESS): 1,
            }
        ),
        "제외 기록 AUTO 1(Laser Marking) · INHERITED 1(Tape Pocket Inspection)",
        str(dict(kinds)),
    )
    marks = auto_off_marks(repository, built.ids["S1"], built.revisions["S1r3"])
    LOG.check(
        story.AUTO_OFF_PROCESS in marks,
        "auto_off_marks 가 v4(r3) 에서 Laser Marking 을 찾음",
        str(marks),
    )
    published = [r for r in built.run_results if r[1] == STATUS_PUBLISHED]
    LOG.check(
        bool(published) and "소요대수" in published[0][2],
        "③ 발행 사유에 소요대수 밖 수요 경고",
        (published[0][2][-160:] if published else ""),
    )

    # 계산 멈춤·가상 제품·측정률 가정·파생
    s8r1 = repository.load_revision(built.revisions["S8r1"])
    s8r2 = repository.load_revision(built.revisions["S8r2"])
    LOG.check(full_capacity_outcome(s8r1.tables, s8r1.tables).error is not None, "S8 r1 계산 멈춤")
    LOG.check(full_capacity_outcome(s8r2.tables, s8r2.tables).error is None, "S8 r2 계산됨")
    s5r2 = repository.load_revision(built.revisions["S5r2"])
    s5_unit, _, _ = table_rates(s5r2.tables)
    assumed = capacity_assumptions(s5_unit)
    virtual_count = len(repository.list_virtual_products(built.revisions["S5r2"]))
    LOG.check(
        virtual_count == 2 and sum(assumed.counts.values()) > 0,
        "S5 r2 가상 2 · 측정률 가정 > 0",
        f"가상 {virtual_count} · 가정 {assumed.counts}",
    )
    for key in ("S6r1", "S7r1", "S4r1", "S4r2", "S5r1", "S2r2", "S2r3"):
        snapshot = repository.load_revision(built.revisions[key])
        LOG.check(
            full_capacity_outcome(snapshot.tables, snapshot.tables).error is None, f"{key} 계산됨"
        )

    # 목록 꼴
    active = repository.list_scenarios()
    archived = [s for s in repository.list_scenarios(include_archived=True) if s.status != "ACTIVE"]
    releases = repository.list_official_releases()
    counts["시나리오"] = {"활성": len(active), "보관": len(archived), "공식": len(releases)}
    LOG.check(
        len(active) == 7 and len(archived) == 2 and len(releases) == 4,
        "목록 7 · 보관 2 · 공식 이력 4",
        str(counts["시나리오"]),
    )
    LOG.say("목록 차례: " + " / ".join(s.scenario_name for s in active))
    settings = repository.load_auto_official_update_settings()
    LOG.check(
        settings.config.enabled and settings.version == 2,
        "자동 갱신 설정 v2(켬)",
        f"v{settings.version} {settings.config}",
    )
    return counts


def run_abandon_check(database: Path, work: Path) -> None:
    """산출물 사본에서 예약 스레드의 기동 정리(`abandon_interrupted_runs`)를 돌려 끊긴 회차 하나가 "
    "그 사유로 닫히는지 본다."""
    copy_dir = work / "abandon"
    shutil.rmtree(copy_dir, ignore_errors=True)
    copy_dir.mkdir(parents=True)
    copy = copy_dir / DB_NAME
    shutil.copy2(database, copy)
    try:
        repository = DuckDBScenarioRepository(copy)
        now = datetime.now()
        closed = abandon_interrupted_runs(repository, started_before=now, now=now)
        runs = [
            run
            for run in repository.list_auto_official_update_runs()
            if run.started_at == story.INTERRUPTED_RUN_AT
        ]
        reason = runs[0].reason if runs else None
        status = runs[0].status if runs else None
    finally:
        shutil.rmtree(copy_dir, ignore_errors=True)
    LOG.check(
        closed == 1 and status == STATUS_ERROR and reason == INTERRUPTED_REASON,
        "기동 정리(사본) — 끊긴 회차 1건이 「앱이 꺼져 중단」 오류로 닫힘",
        f"닫음 {closed} · {status} · {reason}",
    )


def run_inspect(
    database: Path, work: Path, notes: Path, s8_id: str, repository: DuckDBScenarioRepository
) -> None:
    """`scripts/inspect_revision_calculations.py` 를 산출물 사본에 돌려 S8 r1 만 멈추는지 본다."""
    copy_dir = work / "inspect"
    shutil.rmtree(copy_dir, ignore_errors=True)
    copy_dir.mkdir(parents=True)
    copy = copy_dir / DB_NAME
    shutil.copy2(database, copy)
    output = copy_dir / "inspect.md"
    env = dict(os.environ)
    result = subprocess.run(
        [sys.executable, str(INSPECT_SCRIPT), "--database", str(copy), "--output", str(output)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(copy_dir),
        timeout=900,
    )
    text = output.read_text(encoding="utf-8") if output.exists() else result.stdout
    (notes / "inspect_revision_calculations.md").write_text(text, encoding="utf-8")
    order = [
        summary.scenario_id
        for summary in sorted(
            repository.list_scenarios(include_archived=True),
            key=lambda item: (item.created_at, item.scenario_id),
        )
    ]
    expected_label = f"S{order.index(s8_id) + 1}"
    stopped: list[str] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if (
            len(cells) >= 6
            and cells[0].startswith("S")
            and cells[1].startswith("r")
            and cells[5].startswith("멈춤")
        ):
            stopped.append(f"{cells[0]} {cells[1]} {cells[5]}")
    LOG.say(
        f"inspect_revision_calculations 종료 {result.returncode} · 멈춘 리비전 {stopped} (S8 = "
        f"만든 차례 {expected_label})"
    )
    shutil.rmtree(copy_dir, ignore_errors=True)
    LOG.check(result.returncode == 0, "inspect_revision_calculations 실행", result.stderr[-300:])
    LOG.check(
        len(stopped) == 1 and stopped[0].startswith(f"{expected_label} r1 "),
        "inspect_revision_calculations — S8 r1 만 멈춤",
        "; ".join(stopped),
    )


def database_counts(database: Path) -> dict[str, int]:
    import duckdb

    with duckdb.connect(str(database), read_only=True) as connection:
        queries = {
            "시나리오(전체)": "SELECT count(*) FROM app_meta.scenario",
            "리비전": "SELECT count(*) FROM app_meta.scenario_revision",
            "공식버전": "SELECT count(*) FROM app_meta.official_release",
            "원천 행(raw_data.core_data)": "SELECT count(*) FROM raw_data.core_data",
            "자동 갱신 회차": "SELECT count(*) FROM app_meta.auto_official_update_run",
            "자동 갱신 설정 변경": "SELECT count(*) FROM app_meta.auto_official_update_setting_log",
            "VOC 글": "SELECT count(*) FROM app_meta.voc_post",
            "VOC 답": "SELECT count(*) FROM app_meta.voc_reply",
            "표시순서 규칙": "SELECT count(*) FROM app_meta.global_display_order_rule",
            "rev_data.rq_reqb 행": "SELECT count(*) FROM rev_data.rq_reqb",
        }
        out: dict[str, int] = {}
        for label, sql in queries.items():
            try:
                row = connection.execute(sql).fetchone()
                out[label] = int(row[0]) if row else 0
            except duckdb.Error as exc:  # 표 이름이 다르면 그 칸만 건너뛴다.
                out[label] = -1
                LOG.say(f"집계 실패 {label}: {exc}")
    return out


FORBIDDEN_TEXT: Final = (
    "HBM나",
    "HBM다",
    "HBM라",
    "LINTEL",
    "BRCM",
    "SAMPLE-",
    "CSS-",
    "@",
    "others",
)


def identifier_scan(database: Path) -> None:
    """글자 칸 전부에서 옛 데모 값·메일 꼴이 없는지 본다(식별값 검사)."""
    import duckdb

    hits: dict[str, int] = {}
    with duckdb.connect(str(database), read_only=True) as connection:
        columns = connection.execute(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns WHERE "
            "data_type = 'VARCHAR'"
        ).fetchall()
        for schema, table, column in columns:
            condition = " OR ".join(f'"{column}" LIKE ?' for _ in FORBIDDEN_TEXT)
            row = connection.execute(
                f'SELECT count(*) FROM {schema}."{table}" WHERE {condition}',
                [f"%{text}%" for text in FORBIDDEN_TEXT],
            ).fetchone()
            if row and row[0]:
                hits[f"{schema}.{table}.{column}"] = int(row[0])
    LOG.check(
        not hits,
        "식별값 검사(옛 데모 값·메일 꼴 0건)",
        str(hits) if hits else f"글자 칸 {len(columns)}개",
    )


def fingerprint(database: Path) -> list[str]:
    """시나리오명·리비전 번호·리비전 내용 지문(`reference_hash`) — 두 번 돌려 같은지 견준다."""
    import duckdb

    with duckdb.connect(str(database), read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT s.scenario_name, r.revision_no, r.revision_name, r.reference_hash
            FROM app_meta.scenario_revision r JOIN app_meta.scenario s USING (scenario_id)
            ORDER BY s.scenario_name, r.revision_no
            """
        ).fetchall()
    return [f"{name}|r{no}|{label}|{digest}" for name, no, label, digest in rows]


def compare_fingerprint(database: Path, notes: Path) -> None:
    path = notes / FINGERPRINT_NAME
    current = fingerprint(database)
    if path.exists():
        previous = path.read_text(encoding="utf-8").splitlines()
        same = previous == current
        LOG.say(
            f"지난 실행과 리비전 내용 지문 {'같음' if same else '다름'}({len(current)}개 리비전)"
        )
    path.write_text("\n".join(current) + "\n", encoding="utf-8")


def write_csvs(csv_dir: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(csv_dir / "Core_Data.csv", index=False, encoding="cp949")
    (csv_dir / "RQ_DISPLAY_ORDER.csv").write_bytes(display_order_to_csv(RULES))
    # 앱의 CSV 읽기(빈 저장소 시드·bootstrap 스크립트가 쓰는 길)로 다시 읽어 같은 표가 나오는지
    # 본다.
    back = read_core_data_csv(csv_dir / "Core_Data.csv")
    rules_back = display_order_from_csv((csv_dir / "RQ_DISPLAY_ORDER.csv").read_bytes())
    again = prepare_core_data_dataset(
        CoreDataBatch("CSV-CHECK", "CSV-CHECK", "CSV_CHECK", back), rules_back
    )
    LOG.check(
        len(back) == len(frame) and len(again.reference_tables["RQ_REQB"]) > 0,
        "CSV 다시 읽기(read_core_data_csv · display_order_from_csv)",
        f"{len(back):,}행 · 표시순서 {len(rules_back)}행",
    )
    LOG.say(
        f"CSV: {csv_dir / 'Core_Data.csv'}({len(frame):,}행, cp949) · "
        f"RQ_DISPLAY_ORDER.csv({len(RULES)}행)"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="검수용 합성 샘플 — 시뮬레이션 DB 생성기")
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="데이터 폴더(그 안에 capa_simulation.duckdb) 또는 .duckdb 경로",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="Core_Data.csv·RQ_DISPLAY_ORDER.csv 폴더(기본 <데이터 폴더>/input)",
    )
    parser.add_argument("--no-csv", action="store_true", help="CSV 를 쓰지 않는다")
    parser.add_argument("--replace", action="store_true", help="이 생성기의 기존 산출물만 덮는다")
    parser.add_argument(
        "--skip-inspect", action="store_true", help="inspect_revision_calculations 점검을 건너뛴다"
    )
    args = parser.parse_args(argv)
    global LOG
    LOG = BuildLog()
    # 실행 문맥 밖에서 부르는 캐시 래퍼가 「No runtime found」 를 줄마다 찍는다 — 계산과 무관하다.
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    if date.today() < story.TODAY:
        raise SystemExit("실제 날짜가 2026-11-02 보다 이르면 돌리지 않습니다(설비 실적 검증).")
    database, csv_dir = resolve_outputs(args.out.resolve(), args.csv_out)
    if args.no_csv:
        csv_dir = None
    prepare_outputs(database, csv_dir, replace_existing=args.replace)
    # 기록 · 공정×월 표 · 지문은 데이터 폴더의 부모(산출 뿌리)에 둔다.
    notes = database.parent.parent
    refuse_unsafe(notes / LOG_NAME)
    work = notes / ".gen-sim-work"
    stage_db, stage_csv = stage_outputs(work, csv_dir is not None)
    LOG.say(
        f"앱 {Path(capa_simulation.__file__).resolve().parents[2]} · 준비 {stage_db} → 산출 "
        f"{database}"
    )
    built = build(stage_db)
    run_checks(built, stage_db, notes)
    if stage_csv is not None:
        write_csvs(stage_csv, built.frames["W44"])
    wal = stage_db.with_name(stage_db.name + ".wal")
    if wal.exists():
        import duckdb

        with duckdb.connect(str(stage_db)) as connection:
            connection.execute("CHECKPOINT")
    LOG.check(not wal.exists(), "WAL 없음(닫은 뒤)")
    s8_id = built.ids["S8"]
    order_repository = built.repository
    if not args.skip_inspect:
        run_inspect(stage_db, work, notes, s8_id, order_repository)
    run_abandon_check(stage_db, work)
    identifier_scan(stage_db)
    compare_fingerprint(stage_db, notes)
    stats = database_counts(stage_db)
    for label, value in stats.items():
        LOG.say(f"집계 {label}: {value:,}")
    LOG.say(f"DB 크기 {stage_db.stat().st_size / 1e6:.1f} MB")
    if LOG.failures:
        LOG.say(
            f"점검 실패 {len(LOG.failures)}건 — 산출물을 옮기지 않습니다(준비 자리 {stage_db}): "
            + ", ".join(LOG.failures)
        )
    else:
        publish_outputs(stage_db, stage_csv, database, csv_dir)
        shutil.rmtree(work / "stage", ignore_errors=True)
        try:
            work.rmdir()  # 비었을 때만
        except OSError:
            pass
        LOG.say("점검 실패 0건")
    log_text = "\n".join(LOG.lines) + "\n"
    (notes / LOG_NAME).write_text(log_text, encoding="utf-8")
    return 1 if LOG.failures else 0


_CALIBRATION: Calibration | None = None


def calibrate_cache() -> Calibration:
    global _CALIBRATION
    if _CALIBRATION is None:
        _CALIBRATION = calibrate()
    return _CALIBRATION


if __name__ == "__main__":
    raise SystemExit(main())
