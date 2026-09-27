# Purpose: 기존 합성 계획을 확장하고 이름별 고정 편차를 가진 공정 기준정보 CSV를 재생성한다.

"""기존 합성 계획과 공정 기준정보를 목표 월까지 확장한다.

원본 계획은 보존하고 **원본의** 마지막 달의 제품 구성을 연장한다. 이 스크립트가 앞서
연장해 둔 행은 걷어내고 다시 만들므로, 이미 연장된 파일에 다시 돌려도 결과가 같다.
공정별 높이 차이는 고정 기준정보에서, 월별 추세는 계획에서 만들어 반복 실행 결과를
동일하게 유지한다.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import math
import shutil
from dataclasses import dataclass, replace
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


# 처리량의 단위 크기는 유지하되 합성 계획에 비해 과도했던 병렬 모듈·보유대수를 낮춘다.
# 이는 데모 화면용 기준값이며 실제 설비의 사양이나 필요대수가 아니다.
_BASE_PROCESS_SPECS = (
    ProcessSpec("Pre B/D", "Main", "CHIP", 76000, 0.86, 1.04, 1, 1.00, 1.00, 5, 0),
    ProcessSpec("Wafer_Sorter", "Main", "WF", 42, 0.82, 1.05, 1, 1.00, 0.98, 18, 1),
    ProcessSpec("AVI-CoW", "MI", "WF", 5.0, 0.90, 1.04, 1, 0.98, 0.97, 1, 0),
    ProcessSpec("Laser Grooving", "Main", "WF", 33, 0.83, 1.06, 2, 1.00, 1.00, 16, 1),
    ProcessSpec("Wafer Grinding", "Main", "WF", 28, 0.80, 1.08, 2, 0.99, 0.98, 14, 1),
    ProcessSpec("Wafer Mount", "Main", "WF", 48, 0.88, 1.03, 1, 1.00, 1.00, 12, 0),
    ProcessSpec("Wafer Saw", "MI", "WF", 7.2, 0.84, 1.07, 1, 0.97, 0.96, 1, 0),
    ProcessSpec("Plasma Clean", "Main", "CHIP", 92000, 0.89, 1.03, 1, 1.00, 1.00, 3, 0),
    ProcessSpec("DAF Attach", "Main", "CHIP", 68000, 0.82, 1.06, 1, 0.98, 0.99, 4, 0),
    ProcessSpec("Die Attach", "MI", "CHIP", 0.045, 0.78, 1.10, 1, 0.96, 0.97, 4, 0),
    ProcessSpec("TC Bonding", "Main", "CHIP", 54000, 0.76, 1.12, 1, 0.95, 0.96, 5, 0),
    ProcessSpec("Mass Reflow", "Main", "CHIP", 105000, 0.91, 1.03, 1, 1.00, 1.00, 3, 0),
    ProcessSpec("Underfill", "MI", "CHIP", 0.052, 0.81, 1.08, 1, 0.97, 0.98, 4, 0),
    ProcessSpec("Mold", "Main", "CHIP", 83000, 0.84, 1.06, 1, 0.99, 0.99, 3, 0),
    ProcessSpec("Cure", "Main", "CHIP", 120000, 0.92, 1.02, 1, 1.00, 1.00, 2, 0),
    ProcessSpec("Laser Marking", "MI", "CHIP", 0.035, 0.87, 1.04, 1, 1.00, 1.00, 2, 0),
    ProcessSpec("Ball Attach", "Main", "CHIP", 74000, 0.83, 1.07, 1, 0.98, 0.98, 4, 0),
    ProcessSpec("Flux Clean", "Main", "CHIP", 98000, 0.88, 1.04, 1, 1.00, 1.00, 2, 0),
    ProcessSpec("Singulation", "MI", "CHIP", 0.041, 0.79, 1.09, 1, 0.96, 0.97, 3, 0),
    ProcessSpec("Package Sorter", "Main", "CHIP", 112000, 0.90, 1.03, 1, 1.00, 1.00, 3, 0),
    ProcessSpec("Burn-In", "Main", "CHIP", 61000, 0.75, 1.11, 1, 0.94, 0.95, 5, 0),
    ProcessSpec("Final Test", "MI", "CHIP", 0.058, 0.77, 1.10, 1, 0.95, 0.96, 5, 0),
    ProcessSpec("AVI-PKG", "Main", "CHIP", 88000, 0.86, 1.05, 1, 0.99, 0.99, 3, 0),
    ProcessSpec("O/S Test", "Main", "CHIP", 97000, 0.89, 1.04, 1, 1.00, 1.00, 2, 0),
    ProcessSpec("Taping", "MI", "CHIP", 0.032, 0.85, 1.05, 1, 1.00, 1.00, 2, 0),
    ProcessSpec("Packing", "Main", "CHIP", 125000, 0.92, 1.02, 1, 1.00, 1.00, 2, 0),
    ProcessSpec("X-Ray", "Main", "CHIP", 57000, 0.80, 1.09, 1, 0.95, 0.96, 4, 0),
    ProcessSpec("SAM", "MI", "CHIP", 0.650, 0.78, 1.10, 2, 0.94, 0.95, 22, 3),
    ProcessSpec("Warpage", "Main", "CHIP", 69000, 0.84, 1.07, 1, 0.97, 0.98, 3, 0),
    ProcessSpec("Shipping Inspection", "Main", "CHIP", 118000, 0.93, 1.02, 1, 1.00, 1.00, 2, 0),
)

# 일반 후공정 이름을 직접 고르고 유사 공정의 단위·계산 경로를 이어받는다.
# 표시 폭 검증을 위해 약어부터 긴 검사 이름까지 섞되 제품·고객 식별값은 넣지 않는다.
_PROCESS_VARIANTS = (
    ("Wafer Incoming Inspection", "Wafer_Sorter"),
    ("Back Grinding Tape Lamination", "Wafer Mount"),
    ("Wafer Thinning", "Wafer Grinding"),
    ("Stress Relief Polish", "Wafer Grinding"),
    ("Wafer Debond", "Wafer Mount"),
    ("UV Release", "Wafer Mount"),
    ("Die Expansion", "Wafer Mount"),
    ("Wafer Surface Treatment", "Laser Grooving"),
    ("Protective Film Lamination", "Wafer Mount"),
    ("Wafer Edge Inspection", "AVI-CoW"),
    ("Backside Surface Inspection", "AVI-CoW"),
    ("Wafer Thickness Measurement", "Wafer Saw"),
    ("Die Crack Inspection", "AVI-CoW"),
    ("Wafer Map Verification", "AVI-CoW"),
    ("Die Cleaning", "Plasma Clean"),
    ("Adhesive Dispense", "Mold"),
    ("Epoxy Dispense", "Mold"),
    ("Flip Chip Placement", "TC Bonding"),
    ("Thermal Compression Prebond", "TC Bonding"),
    ("Copper Pillar Reflow", "Mass Reflow"),
    ("Compression Mold", "Mold"),
    ("Transfer Mold", "Mold"),
    ("Post Mold Cure", "Cure"),
    ("Solder Ball Inspection", "AVI-PKG"),
    ("Package Cleaning", "Flux Clean"),
    ("Lid Attach", "DAF Attach"),
    ("Heat Spreader Attach", "DAF Attach"),
    ("Substrate Bake", "Cure"),
    ("Bump Co-Planarity Check", "Warpage"),
    ("Reel Sealing", "Packing"),
    ("Tray Loading", "Package Sorter"),
    ("Wire Bond", "Die Attach"),
    ("Electrical Continuity Inspection", "Final Test"),
    ("Fine Pitch Interconnect Inspection", "Final Test"),
    ("Micro Bump Alignment Verification", "Die Attach"),
    ("Acoustic Delamination Inspection", "SAM"),
    ("Laser Package Trimming", "Singulation"),
    ("Post Singulation Edge Inspection", "Laser Marking"),
    ("Mark Readback", "Laser Marking"),
    ("Tape Pocket Inspection", "Taping"),
)


def stable_fraction(*values: str) -> float:
    digest = hashlib.sha256("|".join(values).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def varied_process_spec(spec: ProcessSpec) -> ProcessSpec:
    """공정명·인자별 해시로 처리량과 가동률에 월과 무관한 편차를 준다."""
    throughput = 0.65 + 0.70 * stable_fraction(spec.name, "throughput")
    run_rate = 0.90 + 0.16 * stable_fraction(spec.name, "run-rate")
    return replace(
        spec,
        # MI는 초 단위 ST이므로 처리량 배율을 반대로 걸어 Main과 뜻을 맞춘다.
        performance=(
            spec.performance * throughput if spec.area == "Main" else spec.performance / throughput
        ),
        run_rate=spec.run_rate * run_rate,
    )


_BASE_BY_NAME = {spec.name: spec for spec in _BASE_PROCESS_SPECS}
PROCESS_SPECS = tuple(
    varied_process_spec(spec)
    for spec in (
        *_BASE_PROCESS_SPECS,
        *(replace(_BASE_BY_NAME[source], name=name) for name, source in _PROCESS_VARIANTS),
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--end-month", type=int, default=202812)
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


def plan_group_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (row["제품정보"], row["Stack"], row["Capa Code"], row["Customer"], row["CS"])


def is_extended_plan(row: dict[str, str]) -> bool:
    """이 스크립트가 연장해 만든 계획 행인가. PLAN ID 를 같은 식으로 다시 만들어 맞대 본다."""
    return row["PLAN ID"] == row_id("PLAN", row[PLAN_MONTH], *plan_group_key(row))


def extend_plans(plan_rows: list[dict[str, str]], end_month: int) -> list[dict[str, str]]:
    # 연장분 위에 다시 연장하면 그 마지막 달이 새 원점이 되어 믹스가 한 번 더 곱해지고
    # 계절 위상·성장도 처음부터 다시 걸린다 — 그 달에 계단이 생긴다. 그래서 연장분을
    # 걷어내고 원본의 마지막 달부터 다시 만든다. 식이 같으니 있던 연장분은 같은 값으로
    # 되살아난다. 목표 월이 입력보다 이르면 입력 범위를 줄이지 않는다.
    original_rows = [row for row in plan_rows if not is_extended_plan(row)]
    if not original_rows:
        raise ValueError("No original plan rows were found")
    end_month = max(end_month, *(int(row[PLAN_MONTH]) for row in plan_rows))
    latest_month = max(int(row[PLAN_MONTH]) for row in original_rows)
    if latest_month >= end_month:
        return original_rows

    source_rows = [row for row in original_rows if int(row[PLAN_MONTH]) == latest_month]
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
    extended = list(original_rows)
    for offset, month in enumerate(month_sequence(next_month(latest_month), end_month), start=1):
        seasonal = 1.0 + 0.055 * math.sin(offset * math.pi / 3.0)
        for source in source_rows:
            group_key = plan_group_key(source)
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
        wf_type = plan["WF 구분"]
        product_modifier = 0.93 + stable_fraction(plan["제품정보"], plan["Stack"], wf_type) * 0.14

        for index, spec in enumerate(PROCESS_SPECS, start=1):
            row = dict(plan)
            # 달력 일수 외 기준정보는 고정한다. 공정별 월 위상을 넣으면 추세가 갈린다.
            performance = spec.performance * product_modifier
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
            row["설비보유"] = f"{spec.owned:.3f}"
            row["설비대수변화관리"] = "0"
            row["설비대여평가"] = f"{spec.lent:.3f}"
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
