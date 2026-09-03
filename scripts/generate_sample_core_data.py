# Purpose: Expand the local Core Data sample through a target month.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

"""Expand the local Core Data sample through a target month.

The script keeps existing plan rows, extends the latest plan mix, and rebuilds
process-reference rows so the whole Streamlit calculation chain can be tested.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import math
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ENCODING = "cp949"
PLAN_FLAG = "계획기초정보여부"
PLAN_MONTH = "생산계획년월"
REFERENCE_MONTH = "기준정보년월"


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    area: str
    basis: str
    performance: float
    run_rate: float
    vital: float
    module: int
    lot_ratio: float
    wf_ratio: float
    owned: float
    lent: float


PROCESS_SPECS = (
    ProcessSpec("Pre B/D", "Main", "CHIP", 76000, 0.86, 1.04, 4, 1.00, 1.00, 46, 2),
    ProcessSpec("Wafer_Sorter", "Main", "WF", 42, 0.82, 1.05, 1, 1.00, 0.98, 18, 1),
    ProcessSpec("AVI-CoW", "MI", "WF", 5.0, 0.90, 1.04, 1, 0.98, 0.97, 21, 0),
    ProcessSpec("Laser Grooving", "Main", "WF", 33, 0.83, 1.06, 2, 1.00, 1.00, 16, 1),
    ProcessSpec("Wafer Grinding", "Main", "WF", 28, 0.80, 1.08, 2, 0.99, 0.98, 14, 1),
    ProcessSpec("Wafer Mount", "Main", "WF", 48, 0.88, 1.03, 1, 1.00, 1.00, 12, 0),
    ProcessSpec("Wafer Saw", "MI", "WF", 7.2, 0.84, 1.07, 2, 0.97, 0.96, 19, 2),
    ProcessSpec("Plasma Clean", "Main", "CHIP", 92000, 0.89, 1.03, 4, 1.00, 1.00, 25, 1),
    ProcessSpec("DAF Attach", "Main", "CHIP", 68000, 0.82, 1.06, 4, 0.98, 0.99, 35, 3),
    ProcessSpec("Die Attach", "MI", "CHIP", 0.045, 0.78, 1.10, 4, 0.96, 0.97, 42, 4),
    ProcessSpec("TC Bonding", "Main", "CHIP", 54000, 0.76, 1.12, 4, 0.95, 0.96, 51, 5),
    ProcessSpec("Mass Reflow", "Main", "CHIP", 105000, 0.91, 1.03, 6, 1.00, 1.00, 18, 1),
    ProcessSpec("Underfill", "MI", "CHIP", 0.052, 0.81, 1.08, 4, 0.97, 0.98, 38, 3),
    ProcessSpec("Mold", "Main", "CHIP", 83000, 0.84, 1.06, 4, 0.99, 0.99, 27, 2),
    ProcessSpec("Cure", "Main", "CHIP", 120000, 0.92, 1.02, 8, 1.00, 1.00, 13, 0),
    ProcessSpec("Laser Marking", "MI", "CHIP", 0.035, 0.87, 1.04, 2, 1.00, 1.00, 15, 1),
    ProcessSpec("Ball Attach", "Main", "CHIP", 74000, 0.83, 1.07, 4, 0.98, 0.98, 32, 3),
    ProcessSpec("Flux Clean", "Main", "CHIP", 98000, 0.88, 1.04, 4, 1.00, 1.00, 17, 1),
    ProcessSpec("Singulation", "MI", "CHIP", 0.041, 0.79, 1.09, 3, 0.96, 0.97, 29, 3),
    ProcessSpec("Package Sorter", "Main", "CHIP", 112000, 0.90, 1.03, 4, 1.00, 1.00, 20, 1),
    ProcessSpec("Burn-In", "Main", "CHIP", 61000, 0.75, 1.11, 6, 0.94, 0.95, 48, 6),
    ProcessSpec("Final Test", "MI", "CHIP", 0.058, 0.77, 1.10, 4, 0.95, 0.96, 44, 5),
    ProcessSpec("AVI-PKG", "Main", "CHIP", 88000, 0.86, 1.05, 3, 0.99, 0.99, 23, 2),
    ProcessSpec("O/S Test", "Main", "CHIP", 97000, 0.89, 1.04, 3, 1.00, 1.00, 18, 1),
    ProcessSpec("Taping", "MI", "CHIP", 0.032, 0.85, 1.05, 2, 1.00, 1.00, 16, 1),
    ProcessSpec("Packing", "Main", "CHIP", 125000, 0.92, 1.02, 4, 1.00, 1.00, 12, 0),
    ProcessSpec("X-Ray", "Main", "CHIP", 57000, 0.80, 1.09, 2, 0.95, 0.96, 26, 3),
    ProcessSpec("SAM", "MI", "CHIP", 0.650, 0.78, 1.10, 2, 0.94, 0.95, 22, 3),
    ProcessSpec("Warpage", "Main", "CHIP", 69000, 0.84, 1.07, 2, 0.97, 0.98, 19, 2),
    ProcessSpec("Shipping Inspection", "Main", "CHIP", 118000, 0.93, 1.02, 3, 1.00, 1.00, 10, 0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--end-month", type=int, default=202712)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def next_month(month: int) -> int:
    year, number = divmod(month, 100)
    return (year + 1) * 100 + 1 if number == 12 else year * 100 + number + 1


def month_sequence(start: int, end: int) -> list[int]:
    values: list[int] = []
    current = start
    while current <= end:
        values.append(current)
        current = next_month(current)
    return values


def stable_fraction(*values: str) -> float:
    digest = hashlib.sha256("|".join(values).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def scaled_number(value: str, factor: float) -> str:
    if not value.strip():
        return value
    try:
        number = float(value)
    except ValueError:
        return value
    return f"{number * factor:.9f}".rstrip("0").rstrip(".")


def row_id(prefix: str, *values: str) -> str:
    return prefix + hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:28].upper()


def extend_plans(plan_rows: list[dict[str, str]], end_month: int) -> list[dict[str, str]]:
    latest_month = max(int(row[PLAN_MONTH]) for row in plan_rows)
    if latest_month >= end_month:
        return plan_rows

    source_rows = [row for row in plan_rows if int(row[PLAN_MONTH]) == latest_month]
    quantity_columns = (
        "생산수량",
        "Plan_Chip(K개)",
        "계획(K개)",
        "8H 환산 계획(K개)",
        "WF수(매)",
        "PCB수(K매)",
        "EQ(억Gb)",
        "일 필요",
        "소요대수",
    )
    extended = list(plan_rows)
    for offset, month in enumerate(month_sequence(next_month(latest_month), end_month), start=1):
        seasonal = 1.0 + 0.055 * math.sin(offset * math.pi / 3.0)
        for source in source_rows:
            group_key = (
                source["제품정보"],
                source["Stack"],
                source["Capa Code"],
                source["Customer"],
                source["CS"],
            )
            mix = 0.92 + stable_fraction(*group_key) * 0.18
            growth = 1.0 + 0.018 * offset
            factor = seasonal * growth * mix
            row = dict(source)
            row[REFERENCE_MONTH] = str(month)
            row[PLAN_MONTH] = str(month)
            row["Month"] = str(month % 10000)
            row["시뮬레이션 ID"] = row_id("SIM", str(month), *group_key)
            row["PLAN ID"] = row_id("PLAN", str(month), *group_key)
            for column in quantity_columns:
                row[column] = scaled_number(row[column], factor)
            extended.append(row)
    return extended


def unique_plan_rows(plan_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    keys = (
        PLAN_MONTH,
        "양산구분",
        "제품정보",
        "Stack",
        "Capa Code",
        "Customer",
        "CS",
        "WF 구분",
    )
    result: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in plan_rows:
        production_class = "양산" if row["CS"] in {"MP", "CS"} else "ER"
        key = tuple(production_class if column == "양산구분" else row[column] for column in keys)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def process_rows(plan_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for plan in unique_plan_rows(plan_rows):
        month = int(plan[PLAN_MONTH])
        production_class = "양산" if plan["CS"] in {"MP", "CS"} else "ER"
        days = calendar.monthrange(month // 100, month % 100)[1]
        month_index = (month // 100 - 2026) * 12 + month % 100 - 7
        wf_type = plan["WF 구분"]
        product_modifier = 0.93 + stable_fraction(plan["제품정보"], plan["Stack"], wf_type) * 0.14

        for index, spec in enumerate(PROCESS_SPECS, start=1):
            row = dict(plan)
            monthly_wave = 1.0 + 0.035 * math.sin((month_index + index) * math.pi / 6.0)
            performance = spec.performance * monthly_wave * product_modifier
            owned = max(1.0, spec.owned + month_index * (0.08 + index % 4 * 0.03))
            lent = min(owned - 0.5, spec.lent + (1 if (month_index + index) % 9 == 0 else 0))
            run_rate = spec.run_rate * (0.94 if production_class == "ER" else 1.0)

            row[PLAN_FLAG] = "N"
            row["FAB"] = "PKG"
            row["Area_Name"] = spec.area
            row["공정"] = spec.name
            row["STEP_SEQ"] = f"P{100 + index * 10:03d}"
            row["MCP_SEQ"] = "11A" if wf_type == "Core" else "1A"
            row["CAPA_RUN_RATE"] = f"{run_rate:.4f}"
            row["소요기준"] = spec.basis
            row["RUN_DAY"] = str(days)
            if spec.area == "Main":
                row["UPEH"] = f"{performance:.6f}"
                row["ST"] = ""
            else:
                row["UPEH"] = ""
                row["ST"] = f"{performance:.6f}"
            row["Lot 측정률"] = f"{spec.lot_ratio:.4f}"
            row["WF측정률"] = f"{spec.wf_ratio:.4f}"
            row["모듈수"] = str(spec.module)
            row["Side반영률"] = "1"
            row["편중률"] = f"{spec.vital:.4f}"
            row["설비보유"] = f"{owned:.3f}"
            row["설비대수변화관리"] = "0"
            row["설비대여평가"] = f"{lent:.3f}"
            row["설비대여평가항목"] = "샘플"
            row["설비대여평가DESC"] = "프로토타입 시뮬레이션"
            row["MCP_Chip_Ratio"] = "1"
            row["시뮬레이션 누락여부"] = "N"
            row["시뮬레이션 ID"] = row_id("SIM", str(month), spec.name, plan["Capa Code"], wf_type)
            result.append(row)
    return result


def main() -> None:
    args = parse_args()
    with args.input.open("r", encoding=ENCODING, newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("Core Data header is missing")
        headers = reader.fieldnames
        rows = list(reader)

    plan_rows = [row for row in rows if row[PLAN_FLAG] == "Y"]
    if not plan_rows:
        raise ValueError("No plan rows were found")
    plan_rows = extend_plans(plan_rows, args.end_month)
    generated_process_rows = process_rows(plan_rows)
    output_rows = [*plan_rows, *generated_process_rows]

    months = sorted({int(row[PLAN_MONTH]) for row in output_rows})
    processes = sorted({row["공정"] for row in generated_process_rows})
    print(f"rows: {len(rows)} -> {len(output_rows)}")
    print(f"months: {months[0]} -> {months[-1]} ({len(months)})")
    print(f"processes: {len(processes)}")
    if args.dry_run:
        return

    backup_dir = args.backup_dir or args.input.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = backup_dir / f"{args.input.stem}.{timestamp}{args.input.suffix}"
    shutil.copy2(args.input, backup_path)

    temporary_path = args.input.with_suffix(args.input.suffix + ".tmp")
    with temporary_path.open("w", encoding=ENCODING, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    temporary_path.replace(args.input)
    print(f"backup: {backup_path}")
    print(f"output: {args.input}")


if __name__ == "__main__":
    main()
