# Purpose: 검수용 합성 샘플의 이야기 상수(제품·공정·판정 칸·프로필 값)와 산출 자리 지킴을 둔다.
"""검수용 합성 샘플의 이야기 상수 — 앱 패키지를 import 하지 않는다.

시뮬레이션 생성기(`review_sample_sim.py`)와 설비 생성기(`review_sample_equip.py`)가 같이 읽는다.
이야기 꼴(이야기 칸 · 판정 분포 · 달별 B/N)은 `docs/review_sample.md` 에 있다. 숫자·이름은 모두
합성이다(`DEMO-` 꼴 제품·코드, 저장소 합성 생성기가 이미 쓰는 일반 후공정 이름). `Pre B/D` 는 코드
상수라 그대로 둔다.
"""

from __future__ import annotations

import calendar
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Final

TODAY: Final = date(2026, 11, 2)


def git_work_tree(path: Path) -> Path | None:
    """`path`(없으면 가장 가까운 있는 부모)부터 위로 `.git` 을 찾는다. 찾으면 그 작업 트리 뿌리."""
    probe = path.resolve()
    while not probe.exists():
        probe = probe.parent
    for folder in (probe, *probe.parents):
        if (folder / ".git").exists():
            return folder
    return None


def refuse_place(path: Path) -> str | None:
    """산출 자리 지킴 — git 작업 트리(이 저장소 · 그 워크트리 포함) 안이면 까닭, 아니면 None.

    산출은 늘 저장소 밖이다. `git archive` 사본(가이드 예시판의 앱 사본)은 `.git` 이 없어 받는다.
    """
    tree = git_work_tree(path)
    if tree is None:
        return None
    return f"git 작업 트리({tree}) 안에는 쓰지 않습니다: {path.resolve()}"


def next_month(month: int) -> int:
    year, number = divmod(month, 100)
    return (year + 1) * 100 + 1 if number == 12 else year * 100 + number + 1


def months_between(start: int, end: int) -> tuple[int, ...]:
    out: list[int] = []
    current = start
    while current <= end:
        out.append(current)
        current = next_month(current)
    return tuple(out)


def month_index(month: int) -> int:
    return (month // 100) * 12 + month % 100 - 1


PLAN_MONTHS: Final = months_between(202611, 202812)  # 계획(26개월, 27·28 완전한 해)
PAST_MONTHS: Final = months_between(202601, 202610)  # Past Data · 설비 실적
# 보정은 9월 원천(W36)까지 덮도록 두 달 앞에서 시작한다.
CALIBRATION_MONTHS: Final = months_between(202609, 202812)


def stable_fraction(*parts: object) -> float:
    """난수 대신 쓰는 0~1 값(`zlib.crc32` — 두 번 돌려도 같다)."""
    text = "|".join(str(part) for part in parts)
    return zlib.crc32(text.encode("utf-8")) / 0xFFFFFFFF


# ----------------------------------------------------------------------------- 시간 축
# 월 투입 Wafer(K매) 닻 — 사이는 직선. 2·9월 RUN_DAY 감소는 계획에 반영하지 않는다.
WAFER_K_ANCHORS: Final[tuple[tuple[int, float], ...]] = (
    (202609, 20.0),
    (202610, 21.0),
    (202611, 22.0),
    (202612, 24.0),
    (202706, 28.0),
    (202712, 33.0),
    (202812, 38.0),
)


def wafer_k(month: int) -> float:
    index = month_index(month)
    anchors = [(month_index(m), value) for m, value in WAFER_K_ANCHORS]
    if index <= anchors[0][0]:
        return anchors[0][1]
    for (left, low), (right, high) in zip(anchors, anchors[1:], strict=False):
        if left <= index <= right:
            return low + (high - low) * (index - left) / (right - left)
    return anchors[-1][1]


# 달 일수 — 연휴 점검 달은 줄인다.
RUN_DAY_OVERRIDES: Final[dict[int, int]] = {202702: 26, 202709: 28}


def run_day(month: int) -> int:
    return RUN_DAY_OVERRIDES.get(month, calendar.monthrange(month // 100, month % 100)[1])


# ----------------------------------------------------------------------------- 제품
HBM: Final = "HBM"
EDP: Final = "EDP-TSV"


@dataclass(frozen=True)
class Variant:
    """제품의 계획 변형 한 줄(Capa Code × Customer × CS × Pack Code × Stack)."""

    capa_code: str
    customer: str
    cs: str
    pack_code: str
    stack: str
    weight: float
    start: int = 0
    end: int = 999912


@dataclass(frozen=True)
class Product:
    name: str
    product_type: str
    gb_per_chip: int
    net_die: int  # Core·Top·Dummy·EDP 다이
    net_die_buffer: int  # HBM Buffer(베이스 다이)
    eds: float
    be: float
    variants: tuple[Variant, ...]
    lob: str = "DEMO-LOB-H"


PRODUCTS: Final[tuple[Product, ...]] = (
    Product(
        "DEMO-H8A",
        HBM,
        16,
        640,
        560,
        0.93,
        0.97,
        (
            Variant("DEMO-CAPA-01", "DEMO_CUST-1", "MP", "PK-A1", "8H", 0.6),
            Variant("DEMO-CAPA-02", "DEMO_CUST-2", "CS", "4.00E+02", "8H", 0.4),
        ),
    ),
    Product(
        "DEMO-H8B",
        HBM,
        16,
        640,
        560,
        0.92,
        0.97,
        (
            Variant("DEMO-CAPA-03", "DEMO_CUST-3", "MP", "PK-B1", "8H", 0.65),
            Variant("DEMO-CAPA-03", "DEMO_CUST-1", "CB", "PK-B1", "8H", 0.35, end=202706),
        ),
    ),
    Product(
        "DEMO-H12A",
        HBM,
        24,
        580,
        520,
        0.91,
        0.96,
        (
            Variant("DEMO-CAPA-04", "DEMO_CUST-1", "MP", "PK-A1", "12H", 0.45),
            # 같은 7키 안에 Pack Code 둘(엑셀 숫자 꼴 포함).
            Variant("DEMO-CAPA-04", "DEMO_CUST-1", "MP", "4.00E+02", "12H", 0.25),
            Variant("DEMO-CAPA-05", "DEMO_CUST-2", "CS", "PK-C1", "12H", 0.30),
        ),
    ),
    Product(
        "DEMO-H12B",
        HBM,
        24,
        580,
        520,
        0.90,
        0.96,
        (
            Variant("DEMO-CAPA-06", "DEMO_CUST-3", "MP", "PK-D1", "12H", 0.60),
            Variant("DEMO-CAPA-07", "DEMO_CUST-4", "MP", "PK-D2", "8H", 0.32),
            Variant("DEMO-CAPA-06", "DEMO_CUST-5", "ER", "PK-D1", "12H", 0.08),
        ),
    ),
    Product(
        "DEMO-H12C",
        HBM,
        24,
        560,
        500,
        0.88,
        0.95,
        (
            Variant("DEMO-CAPA-08", "DEMO_CUST-2", "ER", "PK-C2", "12H", 1.0, end=202612),
            Variant("DEMO-CAPA-08", "DEMO_CUST-2", "MP", "PK-C2", "12H", 0.7, start=202701),
            Variant("DEMO-CAPA-08", "DEMO_CUST-4", "CS", "PK-C3", "12H", 0.3, start=202701),
        ),
    ),
    Product(
        "DEMO-H16A",
        HBM,
        32,
        540,
        480,
        0.86,
        0.94,
        (
            Variant("DEMO-CAPA-09", "DEMO_CUST-1", "MP", "PK-E1", "16H", 0.7, start=202704),
            Variant("DEMO-CAPA-09", "DEMO_CUST-3", "CS", "PK-E1", "16H", 0.3, start=202704),
        ),
    ),
    Product(
        "DEMO-H8S",
        HBM,
        16,
        640,
        560,
        0.90,
        0.95,
        (Variant("DEMO-CAPA-10", "DEMO_CUST-5", "ER", "PK-S1", "8H", 1.0),),
    ),
    Product(
        "DEMO-E4",
        EDP,
        16,
        820,
        820,
        0.94,
        0.98,
        (
            Variant("DEMO-CAPA-11", "DEMO_CUST-2", "MP", "PK-T1", "4H", 0.7),
            Variant("DEMO-CAPA-12", "DEMO_CUST-4", "CS", "PK-T2", "4H", 0.3),
        ),
        lob="DEMO-LOB-E",
    ),
)
PRODUCT_BY_NAME: Final = {product.name: product for product in PRODUCTS}
PRODUCT_NAMES: Final = tuple(product.name for product in PRODUCTS)
NEW_PRODUCT: Final = "DEMO-H16A"  # W44 신제품 — W36·W40 에 없다.
DISCONTINUED_PRODUCT: Final = "DEMO-H8B"  # 27.06 단종
DISCONTINUED_LAST_MONTH: Final = 202706


def product_weight(name: str, month: int) -> float:
    """정규화 전 Wafer 비중(%)."""
    if name == "DEMO-H8A":
        return 22.0
    if name == "DEMO-H8B":
        return {202704: 6.0, 202705: 4.0, 202706: 2.0}.get(month, 9.0 if month <= 202703 else 0.0)
    if name == "DEMO-H12A":
        return 24.0
    if name == "DEMO-H12B":
        return 15.0
    if name == "DEMO-H12C":
        return 8.0
    if name == "DEMO-H16A":
        if month < 202704:
            return 0.0
        return min(14.0, 3.0 + 1.5 * (month_index(month) - month_index(202704)))
    if name == "DEMO-H8S":
        return 2.0
    if name == "DEMO-E4":
        return 6.0
    raise KeyError(name)


def product_share(name: str, month: int) -> float:
    total = sum(product_weight(product.name, month) for product in PRODUCTS)
    return product_weight(name, month) / total


def stack_height(stack: str) -> int:
    return int(stack.rstrip("H"))


def divisions(product: Product, stack: str) -> tuple[tuple[str, int, int, int | None], ...]:
    """(원천 WF 구분, 구분_Chip, Net Die, 구분_EQ) — HBM 은 Buffer 1 · Core N−1 · Top 1 · Dummy 1
    (메인 합성 CSV 와 같은 꼴, CHIP = N + 2), EDP 는 TOP 1 · Master 1 · Slave N−2(CHIP = N)."""
    height = stack_height(stack)
    if product.product_type == EDP:
        return (
            ("TOP", 1, product.net_die, product.gb_per_chip),
            ("Master", 1, product.net_die, product.gb_per_chip),
            ("Slave", height - 2, product.net_die, product.gb_per_chip),
        )
    return (
        ("Buffer", 1, product.net_die_buffer, None),
        ("Core", height - 1, product.net_die, product.gb_per_chip),
        ("Top", 1, product.net_die, product.gb_per_chip),
        ("Dummy", 1, product.net_die, None),
    )


def chip_count(product: Product, stack: str) -> int:
    return sum(chips for _, chips, _, _ in divisions(product, stack))


# ----------------------------------------------------------------------------- 공정
@dataclass(frozen=True)
class Process:
    name: str
    area: str  # Main(UPEH) / MI(ST 분)
    basis: str  # WF / CHIP / PKG
    hbm_divisions: tuple[str, ...]
    edp_divisions: tuple[str, ...]
    run_rate: float
    vital: float
    modules: int
    lot_ratio: float
    wf_ratio: float
    floor: float  # 여유 하한(소요대수 배수) — 반입 계단이 이 아래로 내려가지 않는다.
    target_required: float  # 26.11 목표 소요대수(보정 목표)
    space_group: str  # 설비 공정구분(Space 색)
    building: str
    floor_name: str
    abbreviation: str
    display_name: str | None = None
    major: str = ""  # 설비 공정대분류(합성 묶음)
    # TC Bonding 의 Core 둘째 STEP 처럼 WF 구분별 추가 STEP: {WF 구분: ((STEP_SEQ, MCP_SEQ, 배수),
    # ...)}
    extra_steps: dict[str, tuple[tuple[str, str, float], ...]] = field(default_factory=dict)
    note: str = ""


_WF_HBM = ("Buffer", "Core")
_EDP_ALL = ("TOP", "Master", "Slave")

PROCESSES: Final[tuple[Process, ...]] = (
    Process(
        "Wafer Incoming Inspection",
        "MI",
        "WF",
        _WF_HBM,
        _EDP_ALL,
        0.88,
        1.04,
        1,
        0.98,
        0.97,
        1.22,
        8,
        "FRONT",
        "C1",
        "1F",
        "WII",
        "WF 입고검사",
        "FRONT",
    ),
    Process(
        "Wafer Saw",
        "MI",
        "WF",
        _WF_HBM,
        _EDP_ALL,
        0.86,
        1.05,
        1,
        0.97,
        0.96,
        1.18,
        14,
        "FRONT",
        "C1",
        "1F",
        "WSA",
        None,
        "FRONT",
    ),
    Process(
        "Wafer Sorter",
        "Main",
        "WF",
        _WF_HBM,
        _EDP_ALL,
        0.88,
        1.04,
        1,
        1.00,
        0.99,
        1.18,
        12,
        "FRONT",
        "C1",
        "1F",
        "WSO",
        None,
        "FRONT",
    ),
    Process(
        "Laser Grooving",
        "Main",
        "WF",
        _WF_HBM,
        _EDP_ALL,
        0.84,
        1.06,
        1,
        1.00,
        1.00,
        1.22,
        10,
        "FRONT",
        "C1",
        "2F",
        "LGR",
        None,
        "FRONT",
    ),
    Process(
        "Wafer Grinding",
        "Main",
        "WF",
        _WF_HBM,
        _EDP_ALL,
        0.82,
        1.08,
        1,
        0.99,
        0.98,
        1.19,
        16,
        "FRONT",
        "C1",
        "2F",
        "WGR",
        None,
        "FRONT",
    ),
    Process(
        "Pre B/D",
        "Main",
        "CHIP",
        ("Core", "Top", "Dummy"),
        (),
        0.84,
        1.08,
        1,
        1.00,
        1.00,
        1.17,
        30,
        "PKG",
        "C1",
        "2F",
        "PBD",
        None,
        "BOND",
    ),
    Process(
        "Plasma Clean",
        "Main",
        "CHIP",
        ("Core", "Top"),
        _EDP_ALL,
        0.90,
        1.03,
        1,
        1.00,
        1.00,
        1.26,
        8,
        "FDY",
        "C1",
        "3F",
        "PLC",
        None,
        "BOND",
    ),
    Process(
        "DAF Attach",
        "Main",
        "CHIP",
        ("Core", "Top"),
        _EDP_ALL,
        0.83,
        1.06,
        1,
        0.98,
        0.99,
        1.28,
        12,
        "PKG",
        "C1",
        "3F",
        "DAF",
        None,
        "BOND",
    ),
    Process(
        "TC Bonding",
        "Main",
        "CHIP",
        ("Core", "Top"),
        _EDP_ALL,
        0.78,
        1.10,
        1,
        0.95,
        0.96,
        1.18,
        40,
        "PKG",
        "C2",
        "2F",
        "TCB",
        None,
        "BOND",
        extra_steps={"Core": (("S195", "2A", 1.6),)},
    ),
    Process(
        "Mass Reflow",
        "Main",
        "CHIP",
        ("Core", "Top"),
        _EDP_ALL,
        0.91,
        1.03,
        1,
        1.00,
        1.00,
        1.24,
        9,
        "PKG",
        "C2",
        "2F",
        "MRF",
        None,
        "BOND",
    ),
    # Underfill 은 Core·Top 경로 행도 둔다 — PKG 는 Buffer 로만 센다는 안내(W44 quirk 7).
    Process(
        "Underfill",
        "Main",
        "PKG",
        ("Buffer", "Core", "Top"),
        (),
        0.85,
        1.06,
        1,
        0.97,
        0.98,
        1.20,
        14,
        "PKG",
        "C2",
        "3F",
        "UFL",
        None,
        "MOLD",
    ),
    Process(
        "Mold",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.86,
        1.06,
        2,
        0.99,
        0.99,
        1.18,
        18,
        "PKG",
        "C2",
        "3F",
        "MLD",
        None,
        "MOLD",
    ),
    Process(
        "Post Mold Cure",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.92,
        1.02,
        1,
        1.00,
        1.00,
        1.30,
        7,
        "PKG",
        "C2",
        "3F",
        "PMC",
        "PMC",
        "MOLD",
    ),
    Process(
        "Ball Attach",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.84,
        1.07,
        1,
        0.98,
        0.98,
        1.20,
        16,
        "PKG",
        "C3",
        "1F",
        "BAT",
        None,
        "MOLD",
    ),
    Process(
        "Singulation",
        "MI",
        "PKG",
        ("Buffer",),
        (),
        0.80,
        1.08,
        1,
        0.96,
        0.97,
        1.19,
        12,
        "MI",
        "C3",
        "1F",
        "SNG",
        None,
        "MOLD",
    ),
    Process(
        "Laser Marking",
        "MI",
        "PKG",
        ("Buffer",),
        (),
        0.87,
        1.04,
        1,
        1.00,
        1.00,
        1.22,
        6,
        "MI",
        "C3",
        "1F",
        "LMK",
        None,
        "TEST",
    ),
    Process(
        "X-Ray",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.82,
        1.08,
        1,
        0.95,
        0.96,
        1.24,
        8,
        "MI",
        "C3",
        "1F",
        "XRY",
        None,
        "TEST",
    ),
    Process(
        "Acoustic Delamination Inspection",
        "MI",
        "PKG",
        ("Buffer",),
        (),
        0.80,
        1.09,
        1,
        0.94,
        0.95,
        1.21,
        10,
        "MI",
        "C3",
        "2F",
        "SAM",
        "SAM 검사",
        "TEST",
    ),
    Process(
        "Burn-In",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.76,
        1.10,
        1,
        0.94,
        0.95,
        1.17,
        22,
        "TEST",
        "C3",
        "2F",
        "BIN",
        None,
        "TEST",
    ),
    Process(
        "Final Test",
        "MI",
        "PKG",
        ("Buffer",),
        (),
        0.78,
        1.10,
        1,
        0.95,
        0.96,
        1.17,
        20,
        "TEST",
        "C4",
        "2F",
        "FTS",
        None,
        "TEST",
    ),
    Process(
        "AVI",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.86,
        1.05,
        1,
        0.99,
        0.99,
        1.18,
        14,
        "TEST",
        "C4",
        "2F",
        "AVI",
        None,
        "TEST",
    ),
    Process(
        "Tape Pocket Inspection",
        "MI",
        "PKG",
        ("Buffer",),
        (),
        0.85,
        1.05,
        1,
        1.00,
        1.00,
        1.30,
        4,
        "MI",
        "C4",
        "2F",
        "TPI",
        None,
        "LOGI",
    ),
    Process(
        "Packing",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.92,
        1.02,
        1,
        1.00,
        1.00,
        1.30,
        6,
        "물류",
        "C4",
        "3F",
        "PKG",
        None,
        "LOGI",
    ),
    Process(
        "Shipping Inspection",
        "Main",
        "PKG",
        ("Buffer",),
        (),
        0.93,
        1.02,
        1,
        1.00,
        1.00,
        1.30,
        5,
        "물류",
        "C4",
        "3F",
        "SHI",
        "AVI",
        "LOGI",
    ),
)
# Case(S5) 에만 있는 공정 — 설비 DB 에 호기가 없다(「설비 없음」).
HYBRID_PROCESS: Final = Process(
    "Hybrid Bonding",
    "Main",
    "CHIP",
    ("Core", "Top"),
    (),
    0.80,
    1.10,
    1,
    0.97,
    0.98,
    1.20,
    6,
    "",
    "",
    "",
    "HBD",
    None,
    "BOND",
)
HYBRID_PRODUCTS: Final = ("DEMO-H16A", "DEMO-H12B")
HYBRID_START: Final = 202707
HYBRID_TARGET_MONTH: Final = 202707

PROCESS_BY_NAME: Final = {process.name: process for process in (*PROCESSES, HYBRID_PROCESS)}
PROCESS_NAMES: Final = tuple(process.name for process in PROCESSES)
# 표시순서의 공정 차례 — Hybrid Bonding 은 TC Bonding 바로 앞(Case 에서만 보인다).
DISPLAY_PROCESS_ORDER: Final = (
    *PROCESS_NAMES[: PROCESS_NAMES.index("TC Bonding")],
    HYBRID_PROCESS.name,
    *PROCESS_NAMES[PROCESS_NAMES.index("TC Bonding") :],
)


def step_seq(process: Process) -> str:
    if process.name == HYBRID_PROCESS.name:
        return "S185"
    return f"S{100 + 10 * (PROCESS_NAMES.index(process.name) + 1)}"


# 공정 표시명(Proc Rename) — Shipping Inspection → AVI 는 다른 공정 원본(AVI)과 겹치는 사례다. 끝의
# 둘은 「보유 공정에 없는 공정」 규칙이다(Admin › Proc Rename 안내): AVI-PKG 는 Dynamic Capa·실적
# 데모의 코드 리터럴 공정이라 그 화면에서만 표시명이 입혀지고, Hybrid Bonding 은 Case(S5) 에만 있어
# 공식 v4 를 연 동안은 안내에 들고 Case2(S5 r2)를 열면 빠진다.
PROCESS_RENAMES: Final[tuple[tuple[str, str], ...]] = (
    ("Acoustic Delamination Inspection", "SAM 검사"),
    ("Wafer Incoming Inspection", "WF 입고검사"),
    ("Post Mold Cure", "PMC"),
    ("Shipping Inspection", "AVI"),
    ("AVI-PKG", "PKG 외관"),
    ("Hybrid Bonding", "HB 접합"),
)
# 겹침 규칙(원본 AVI 와 같은 표시명)이 저장 검증에 막히면 이 한 줄만 뺀다.
PROCESS_RENAME_OVERLAP: Final = ("Shipping Inspection", "AVI")
# 공식 v4(S1 r3) 의 RQ_MODULE 에 없는 원본 — Admin 안내 「보유 공정에 없는 공정에 지정된 표시명
# 2건」.
PROCESS_RENAME_UNOWNED: Final = ("AVI-PKG", "Hybrid Bonding")

# ----------------------------------------------------------------------------- 판정 이야기 칸
# (달, 공정, 목표 확보율 %, 종류). 확보율은 공식 v4(S1 r3) 기준. Pre B/D 26.11 은 이야기 칸의 가용
# 이야기(26.12 대여 2대)를 맞추려고 보유 34 · 대여 0 으로 두는 보조 칸이다.
STORY_CELLS: Final[tuple[tuple[int, str, float, str], ...]] = (
    (202611, "Wafer Saw", 113.0, "bn_secure"),
    (202611, "Pre B/D", 115.0, "aux"),
    (202612, "Pre B/D", 96.1, "shortage"),
    (202701, "Mold", 104.0, "warning"),
    (202702, "Mold", 98.0, "shortage"),
    (202703, "TC Bonding", 112.0, "monthly_override"),
    (202704, "Ball Attach", 116.0, "bn_secure"),
    (202705, "Underfill", 99.7, "boundary_warning"),
    (202706, "Ball Attach", 97.0, "shortage"),
    (202707, "AVI", 109.6, "boundary_secure"),
    (202708, "Singulation", 99.0, "shortage"),
    (202709, "Wafer Sorter", 106.0, "monthly_override"),
    (202711, "Burn-In", 101.0, "warning"),
    (202802, "TC Bonding", 95.0, "shortage"),
    (202804, "Laser Marking", 88.0, "shortage"),
    (202805, "Laser Marking", 76.0, "shortage"),
    (202806, "Laser Marking", 84.0, "shortage"),
    (202809, "Final Test", 92.0, "shortage"),
)
# 경고만 만드는 반입 늦은 칸(대여 늘림 — 그 달 B/N 보다 높다). (달, 공정, 목표 %)
DELAYED_CELLS: Final[tuple[tuple[int, str, float], ...]] = (
    (202612, "Plasma Clean", 106.0),
    (202701, "Mass Reflow", 107.0),
    (202702, "Underfill", 103.0),
    (202705, "Singulation", 105.0),
    (202706, "X-Ray", 104.0),
    (202706, "Wafer Incoming Inspection", 107.0),
    (202706, "Acoustic Delamination Inspection", 105.0),
    (202708, "Wafer Grinding", 102.0),
    (202711, "Packing", 108.0),
    (202802, "Mold", 105.0),
    (202802, "DAF Attach", 108.0),
    (202809, "Wafer Saw", 103.0),
    (202809, "Post Mold Cure", 106.0),
)
# 이야기 칸 확보율 기대(1-3 표) — (달, 공정, 확보율 소수 첫째, 판정 secure/warning/shortage).
STORY_EXPECTED: Final[tuple[tuple[int, str, float, str], ...]] = (
    (202611, "Wafer Saw", 113.0, "secure"),
    (202612, "Pre B/D", 96.1, "shortage"),
    (202701, "Mold", 104.0, "warning"),
    (202702, "Mold", 98.0, "shortage"),
    (202703, "TC Bonding", 112.0, "warning"),
    (202704, "Ball Attach", 116.0, "secure"),
    (202705, "Underfill", 99.7, "warning"),
    (202706, "Ball Attach", 97.0, "shortage"),
    (202707, "AVI", 109.6, "secure"),
    (202708, "Singulation", 99.0, "shortage"),
    (202709, "Wafer Sorter", 106.0, "secure"),
    (202711, "Burn-In", 101.0, "warning"),
    (202802, "TC Bonding", 95.0, "shortage"),
    (202805, "Laser Marking", 76.0, "shortage"),
    (202809, "Final Test", 92.0, "shortage"),
)
SUMMARY_EXPECTED: Final[tuple[tuple[int, str, str], ...]] = (
    (202611, "Wafer Saw", "secure"),
    (202612, "Pre B/D", "shortage"),
    (202701, "Mold", "warning"),
    (202702, "Mold", "shortage"),
    (202703, "TC Bonding", "warning"),
    (202704, "Ball Attach", "secure"),
)
# Pre B/D 이야기 — 26.12 소요 33.3 · 가용 32(보유 34 · 대여 2). 가이드 「+2 → 102%」.
STORY_PROCESS: Final = "Pre B/D"
STORY_MONTH: Final = 202612
STORY_REQUIRED: Final = 33.3
STORY_AVAILABLE: Final = 32.0
PRE_BD_FIXED: Final[dict[int, tuple[float, float]]] = {
    # 달: (보유, 대여)
    202609: (34.0, 1.0),
    202610: (34.0, 1.0),
    202611: (34.0, 0.0),
    202612: (34.0, 2.0),
}
FINAL_TEST_FRACTION: Final = 0.333  # 1/3 모듈 소수 보유
AUTO_OFF_PROCESS: Final = "Laser Marking"
MANUAL_OFF_PROCESS: Final = "Tape Pocket Inspection"
DAF_MISMATCH_MONTHS: Final = (202702, 202703, 202704)

# ----------------------------------------------------------------------------- 원천 판
SOURCE_TYPE_CSV: Final = "CSV_CORE_DATA_REVIEW"
SOURCE_TYPE_BDQ: Final = "BIGDATAQUERY"
PIPELINE_VERSION: Final = "review-sample-1102-v1"


@dataclass(frozen=True)
class SourceSpec:
    code: str
    name: str
    first_month: int
    plan_scale: float
    with_new_product: bool


SOURCES: Final[dict[str, SourceSpec]] = {
    "W36": SourceSpec("DEMO-SIM-2636", "DEMO PSM W36 정기", 202609, 0.95, False),
    "W40": SourceSpec("DEMO-SIM-2640", "DEMO PSM W40 정기", 202610, 0.98, False),
    "W43": SourceSpec("DEMO-SIM-2643", "DEMO PSM W43 정기", 202611, 1.0, True),
    "W44": SourceSpec("DEMO-SIM-2644", "DEMO PSM W44 정기", 202611, 1.0, True),
    "HYBRID": SourceSpec("DEMO-SIM-2644H", "DEMO PSS W44 Hybrid 검토", 202611, 1.0, True),
}
# W40 의 제품별 차이(±5~15%) — W44 와 GAP 이 보이게.
W40_PRODUCT_FACTORS: Final[dict[str, float]] = {
    "DEMO-H8A": 1.06,
    "DEMO-H8B": 1.12,
    "DEMO-H12A": 0.93,
    "DEMO-H12B": 1.08,
    "DEMO-H12C": 0.90,
    "DEMO-H8S": 1.00,
    "DEMO-E4": 1.15,
}
W43_BLANK_RUN_RATE: Final = (202704, "TC Bonding")

# W44 quirk 재료
QUIRK_MISMATCH_CUSTOMER: Final = ("DEMO-H12A", "DEMO_CUST-9", (202701, 202702))
QUIRK_UNKNOWN_PRODUCT: Final = ("DEMO-X1", 202703)
QUIRK_NO_YIELD: Final = ("DEMO-H12C", 202705)
QUIRK_BLANK_EDS: Final = ("DEMO-H8S", 202806)
QUIRK_BLANK_QUANTITY: Final = ("DEMO-H8B", (202811, 202812))
QUIRK_ZERO_UPEH: Final = ("DEMO-H8S", "X-Ray")
QUIRK_ZERO_ER_RUN_RATE: Final = "Laser Grooving"
QUIRK_BLANK_CS: Final = ("DEMO-H12B", 202612)

# ----------------------------------------------------------------------------- 시나리오
S1_NAME: Final = "26년 11월 정기 Capa 검토"
S2_NAME: Final = "26년 10월 정기 Capa 검토"
S3_NAME: Final = "26년 9월 정기 Capa 검토"
S4_NAME: Final = "Case · 27년 증산안 (+8%)"
S5_NAME: Final = "Case · Hybrid Bonding 도입안"
S9_NAME: Final = "임시 · 붙여넣기 시험본"
CASE_UP_FACTOR: Final = 1.08
CASE_UP_FROM: Final = 202701
CASE_TCB_EXTRA: Final = 2
CASE_TCB_FROM: Final = 202703
VIRTUAL_PRODUCTS: Final = (
    ("DEMO-H16A", "16H", "DEMO-H16V", "16H"),
    ("DEMO-H12B", "12H", "DEMO-H12V", "12H"),
)
VIRTUAL_PLAN_SHARE: Final = 0.30
MERGE_RANGE: Final = (202707, 202812)

# ----------------------------------------------------------------------------- 공용 프로필
SECURE_DEFAULT: Final = 1.10
WARNING_DEFAULT: Final = 1.00
MONTHLY_THRESHOLDS: Final[tuple[tuple[int, float | None, float | None], ...]] = (
    (202703, 1.15, 1.05),
    (202709, 1.05, None),
    (202906, 1.12, None),
)
KEY_PROCESS_PRESETS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "핵심 공정",
        ("Wafer Saw", "Pre B/D", "TC Bonding", "Mold", "Underfill", "Ball Attach", "AVI"),
    ),
    ("Wafer 공정", PROCESS_NAMES[:5]),
    ("신공정 점검", ("Hybrid Bonding", "TC Bonding", "Mass Reflow", "Underfill")),
)
EXECUTION_ADJUSTMENTS: Final[tuple[tuple[int, str, float, str], ...]] = (
    (202612, "Pre B/D", 6.0, "임시 대여 2대 회수 협의(비가동 감소)"),
    (202702, "Mold", -8.0, "금형 교체 비가동"),
    (202705, "Underfill", 5.0, "UPEH 개선 시험 결과"),
    (202706, "Ball Attach", -5.0, "재공 부진"),
    (202703, "Hybrid Bonding", 10.0, "신공정 선반영(Case 전용)"),
)
ADVANCE_LOAD_PCT: Final[tuple[tuple[int, float], ...]] = (
    (202611, 0.05),
    (202612, 0.03),
    (202701, -0.04),
    (202702, -0.04),
)
# 선행 입고 실적(그 달 Density 의 몫). 칸 글자가 소수 첫째(`{:+.1f}`)라 +0.0 으로 보이는 값은 앱이
# 적지 않는다 — Density 가 1.3~1.6 억Gb 인 지난 달·이번 달에 10~28% 를 넣어 +0.2~+0.4 로 읽히게
# 한다. 값은 소수 첫째로 반올림해 저장한다(화면 글자와 저장값이 같게). 26.11 은 Summary 요약
# 기간(26.11~27.04)의 첫 달이다.
ADVANCE_SHIPMENT_PCT: Final[tuple[tuple[int, float], ...]] = (
    (202608, 0.15),
    (202609, 0.20),
    (202610, 0.28),
    (202611, 0.18),
)
SUMMARY_NOTE: Final = "\n".join(
    (
        "11월 정기(PSM W44) 공식안 기준입니다.",
        "26.12 Pre B/D 96% 부족 — 임시 대여 2대 회수 협의 중(확보율 보정 +6% 반영).",
        "27.02 Mold 금형 교체로 부족 — 실행 관리 › 필요 단축 일정 참고.",
    )
)
TOP5_BAND: Final = (0.70, 1.60)
PAST_LOW_CELLS: Final[dict[tuple[int, str], float]] = {
    (202608, "Mold"): 0.97,
    (202604, "Wafer Saw"): 0.996,
}
PROFILE_SOURCE: Final = "DEMO 정기 검토"
ADMIN_NAME: Final = "DEMO 관리자"
# 11-02 07:00 예약 회차 — 목록 조회 중에 앱이 다시 시작돼 「실행 중」으로 남은 기록(앱을 자동 갱신
# 허락으로 띄우면 예약 스레드가 기동하자마자 「앱이 이 회차를 끝내기 전에 꺼져 중단됐습니다」 오류로
# 닫는다).
INTERRUPTED_RUN_AT: Final = datetime(2026, 11, 2, 7, 0)
