# Purpose: 실 DB 사본으로 공식·UPEH 가정 단축 계획의 1회 시간을 재어 초·개수만 찍는다.

"""「가정 계획 1회 시간」 — 사내 런북 6-3 b 가 실 DB 사본으로 잰다.

UPEH 가정 % 칸은 1 단위로 바꾸면 곧바로 반영한다(2026-10-22 사용자 결정). 필요 단축 일정의 「UPEH
가정 비교」 보기와 공정 Capa 상세는 % 를 바꿀 때마다 가정 계획을 새로 세운다(가정 칸 캐시가 빗나간
회차). 그 한 번이 실데이터에서 얼마나 걸리는지를 잰다 — **1초를 넘으면 % 입력을 「적용」 단추 폼으로
바꾼다**(설계 D4 조건). 합성 시드와 샘플 fleet 은 공정이 겹치지 않아 사외에서는 잴 수 없다.

    uv run --no-sync python scripts/benchmark_upeh_assumption.py --data-dir <사본 폴더> \\
        --output <저장소 밖 파일>

**하는 일.** 사본의 최신 공식버전 리비전으로 대당 Capa → 소요대수(시나리오 전체 기간)를 세고, 설비
DB 사본의 공식 설비 시나리오(공통 최신 + 최신 공식 발행 — 그 시나리오에 일정이 없는 호기는 뺀다)·
Cut-off 로 이번 달부터 시나리오 끝 달까지 다섯 목표 계획을 세운다 — 앱의 필요 단축 일정과 같은
함수(`plan_required_shortening`)이고, 호기 구간은 앱처럼 한 번 만들어 두 계획이 나눈다(앱의 구간
캐시). 그다음 같은 달에 `--percent`(기본 110) 가정을 건 소요대수로 한 번 더 세운다.
두 계획 시간과 ÷f 를 거는 시간을 찍는다.

**지키는 것** — `inspect_revision_calculations.py` 와 같다. 사본에만 돌린다(`--data-dir` 은 기본값이
없고, 저장소 안(`data/` 와 그 아래 포함)은 `benchmark_home.py` 처럼 거절한다 —
`settings.is_operational_database_place`). 저장소(Repository)는 읽기만 하고
`initialize()`(마이그레이션 — 쓰기)를 부르지 않는다. 값을 찍지 않는다 — 초·달 수·공정 수·호기 수만
찍고, 실패는 단계와 예외 종류 한 줄이다(문구에는 공정·제품 이름이 실린다). 사외에서 돌린 수는 합성
표본의 `샘플 관측` 일 뿐 업무 사실이 아니다(AGENTS.md 10-1).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import TextIO

import pandas as pd

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.monthly_equipment_availability import span_date_range
from capa_simulation.services.required_equipment import calculate_required_equipment
from capa_simulation.services.required_shortening import TARGET_LEVELS, plan_required_shortening
from capa_simulation.services.unit_capacity import calculate_unit_capacity
from capa_simulation.services.upeh_assumption import (
    PERCENT_MAX,
    PERCENT_MIN,
    UpehAssumption,
    scale_required_equipment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DATABASE = "capa_simulation.duckdb"
EQUIPMENT_DATABASE = "equipment_availability.duckdb"
LIMIT_SECONDS = 1.0
"""가정 계획 1회가 이보다 길면 % 입력을 「적용」 단추 폼으로 바꾼다."""


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-dir",
        required=True,
        help=(
            f"DB 사본 폴더({SCENARIO_DATABASE}·{EQUIPMENT_DATABASE}). 운영 data 폴더를 주지 않는다."
        ),
    )
    parser.add_argument(
        "--percent",
        type=int,
        default=110,
        help=f"잴 UPEH 가정 %({PERCENT_MIN}~{PERCENT_MAX}, 기본 110).",
    )
    parser.add_argument("--output", help="결과 JSON 을 쓸 파일(먼저 비운다). 없으면 표준 출력만.")
    return parser.parse_args(argv)


def measure(data_dir: Path, *, percent: int, today: date) -> dict[str, object]:
    """두 계획의 시간과 개수. 실패는 `RuntimeError(단계 · 예외 종류)` 로 줄여 올린다."""
    stage = "시나리오 읽기"
    try:
        scenario = DuckDBScenarioRepository(data_dir / SCENARIO_DATABASE)
        release = scenario.latest_official_release()
        if release is None:
            raise LookupError("공식버전 없음")
        tables = scenario.load_revision(release.revision_id).tables
        stage = "대당 Capa·소요대수"
        unit_capacity = calculate_unit_capacity(
            upeh=tables["RQ_UPEH"],
            run_rate=tables["RQ_RUN_RATE"],
            vital=tables["RQ_VITAL"],
            module=tables["RQ_MODULE"],
            run_day=tables["RQ_RUN_DAY"],
            lot_ratio=tables["RQ_LOT_RATIO"],
            wf_ratio=tables["RQ_WF_RATIO"],
        )
        required = calculate_required_equipment(
            reqb=tables["RQ_REQB"],
            plan=tables["RQ_PKG_PLAN"],
            yield_data=tables["RQ_YLD"],
            chip_qty=tables["RQ_CHIP_QTY"],
            unit_capacity=unit_capacity,
        )
        this_month = today.year * 100 + today.month
        months = sorted(
            {int(month) for month in required["생산계획년월"] if int(month) >= this_month}
        )
        if not months:
            raise LookupError("이번 달 이후 소요 없음")
        stage = "설비 읽기"
        equipment_repository = DuckDBEquipmentRepository(data_dir / EQUIPMENT_DATABASE)
        # 공식 설비 시나리오(공통 최신 + 최신 공식 발행) — 앱 화면이 새 세션에 여는 한 벌이다.
        official = equipment_repository.load_official_snapshot()
        if official is None:
            raise LookupError("설비 저장본 없음")
        # 계산은 그 시나리오에 일정이 없는 호기와 그 비가동을 뺀 세 표다(앱 계산과 같다).
        baseline_frame, equipment_frame, downtime_frame = official.calculation_frames()
        cutoff = equipment_repository.load_process_cutoff()
        stage = "호기 구간"
        span = span_date_range(months, cutoff)
        spans = (
            build_equipment_lifecycle_spans(
                equipment_frame,
                downtime_frame,
                start_date=span[0],
                end_date=span[1],
                with_unit_share=True,
            )
            if span is not None
            else None
        )

        def plan(demand: pd.DataFrame) -> tuple[float, int, int]:
            started = time.perf_counter()
            result = plan_required_shortening(
                equipment=equipment_frame,
                downtime=downtime_frame,
                baseline=baseline_frame,
                cutoff=cutoff,
                required_equipment=demand,
                months=months,
                today=today,
                spans=spans,
            )
            seconds = time.perf_counter() - started
            units = sum(len(level.units) for level in result.levels)
            return seconds, len(result.processes), units

        stage = "공식 계획"
        official_seconds, processes, official_units = plan(required)
        stage = "가정 계획"
        token = UpehAssumption(percent, months[0], months[-1]).token(months)
        started = time.perf_counter()
        scaled = scale_required_equipment(required, token)
        scale_seconds = time.perf_counter() - started
        assumed_seconds, _, assumed_units = plan(scaled)
    except Exception as exc:  # 사본의 문구에는 공정·제품 이름이 실린다 — 단계와 종류만 남긴다
        raise RuntimeError(f"{stage} 실패 — {type(exc).__name__}") from None
    assumed_total = scale_seconds + assumed_seconds
    return {
        "percent": percent,
        "months": len(months),
        "processes": processes,
        "levels": len(TARGET_LEVELS),
        "official_seconds": round(official_seconds, 3),
        "scale_seconds": round(scale_seconds, 3),
        "assumed_seconds": round(assumed_total, 3),
        "official_unit_rows": official_units,
        "assumed_unit_rows": assumed_units,
        "verdict": (
            f"{LIMIT_SECONDS:g}초 이하 — 1 단위 곧바로 반영 그대로"
            if assumed_total <= LIMIT_SECONDS
            else f"{LIMIT_SECONDS:g}초 넘음 — % 입력을 「적용」 단추 폼으로 바꾼다(사외에 알린다)"
        ),
    }


def copy_folder_refused(data_dir: Path) -> bool:
    """`--data-dir` 가 운영 DB 자리인가 — 저장소의 `data/` 와 그 아래, git 저장소 안.

    `benchmark_home.py`·`inspect_revision_calculations.py` 와 같은 판정이다
    (`settings.is_operational_database_place` — 운영 DB 옆에 둔 사본은 경로 한 글자 틀림이 곧 운영
    DB 다).
    """
    from capa_simulation.settings import is_operational_database_place

    folder = data_dir.expanduser().resolve()
    return is_operational_database_place(
        folder,
        (PROJECT_ROOT / "data" / SCENARIO_DATABASE, PROJECT_ROOT / "data" / EQUIPMENT_DATABASE),
    )


def _emit(text: str, output: Path | None, stream: TextIO) -> None:
    stream.write(text + "\n")
    if output is not None:
        with output.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def _use_utf8_output() -> None:
    # 사내 Windows 콘솔·파이프의 기본 코드페이지(cp949)는 「—」 같은 기호를 못 쓴다.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_output()
    args = parse_args(argv)
    output = Path(args.output) if args.output else None
    if output is not None:
        output.write_text("", encoding="utf-8")
    data_dir = Path(args.data_dir)
    if copy_folder_refused(data_dir):
        # 저장소 연결은 읽기 전용이 아니다 — 재는 동안 사용자 앱의 운영 DB 연결을 막는다.
        _emit(
            "저장소 안(data/ 포함)은 쓰지 않는다 — 저장소 밖 사본 폴더를 준다(런북 6-3)",
            output,
            sys.stderr,
        )
        return 2
    if not PERCENT_MIN <= int(args.percent) <= PERCENT_MAX:
        _emit(f"--percent 는 {PERCENT_MIN}~{PERCENT_MAX} 입니다", output, sys.stderr)
        return 2
    missing = [
        name for name in (SCENARIO_DATABASE, EQUIPMENT_DATABASE) if not (data_dir / name).exists()
    ]
    if missing:
        _emit(f"사본 폴더에 없는 파일: {', '.join(missing)}", output, sys.stderr)
        return 2
    try:
        result = measure(data_dir, percent=int(args.percent), today=date.today())
    except RuntimeError as exc:
        _emit(str(exc), output, sys.stderr)
        return 1
    _emit(json.dumps(result, ensure_ascii=False, indent=2), output, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
