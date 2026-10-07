# Purpose: 설비 전용 DB가 비어 있을 때만 화면에 보여줄 비영속 샘플 데이터를 만든다.

"""설비 전용 DB가 비어 있을 때만 화면에 보여줄 비영속 샘플 데이터를 만든다."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    COUNTED_USAGE_BASIS,
    DEFAULT_CONVERSION_RATIO,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    RELOCATION_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
    USAGE_BASIS_COLUMN,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)

# 샘플 행임을 표시하는 비고. 저장 직전에 이 표식으로 손대지 않은 행을 가려낸다.
SAMPLE_BASELINE_NOTE = "Core Data 개발 샘플"

# 합성 Core Data 생성기 `scripts/generate_sample_core_data.py` 의 `PROCESS_SPECS` 와 같은
# 공정·`owned`(설비보유) 값이다. `src` 는 `scripts/` 를 읽지 않으므로 옮겨 적고,
# `tests/test_equipment_availability.py` 가 생성기와 한 줄씩 대조한다.
SAMPLE_BASELINE_COUNTS = (
    ("Pre B/D", 5.0),
    ("Wafer_Sorter", 18.0),
    ("AVI-CoW", 1.0),
    ("Laser Grooving", 16.0),
    ("Wafer Grinding", 14.0),
    ("Wafer Mount", 12.0),
    ("Wafer Saw", 1.0),
    ("Plasma Clean", 3.0),
    ("DAF Attach", 4.0),
    ("Die Attach", 4.0),
    ("TC Bonding", 5.0),
    ("Mass Reflow", 3.0),
    ("Underfill", 4.0),
    ("Mold", 3.0),
    ("Cure", 2.0),
    ("Laser Marking", 2.0),
    ("Ball Attach", 4.0),
    ("Flux Clean", 2.0),
    ("Singulation", 3.0),
    ("Package Sorter", 3.0),
    ("Burn-In", 5.0),
    ("Final Test", 5.0),
    ("AVI-PKG", 3.0),
    ("O/S Test", 2.0),
    ("Taping", 2.0),
    ("Packing", 2.0),
    ("X-Ray", 4.0),
    ("SAM", 22.0),
    ("Warpage", 3.0),
    ("Shipping Inspection", 2.0),
    ("Wafer Incoming Inspection", 18.0),
    ("Back Grinding Tape Lamination", 12.0),
    ("Wafer Thinning", 14.0),
    ("Stress Relief Polish", 14.0),
    ("Wafer Debond", 12.0),
    ("UV Release", 12.0),
    ("Die Expansion", 12.0),
    ("Wafer Surface Treatment", 16.0),
    ("Protective Film Lamination", 12.0),
    ("Wafer Edge Inspection", 1.0),
    ("Backside Surface Inspection", 1.0),
    ("Wafer Thickness Measurement", 1.0),
    ("Die Crack Inspection", 1.0),
    ("Wafer Map Verification", 1.0),
    ("Die Cleaning", 3.0),
    ("Adhesive Dispense", 3.0),
    ("Epoxy Dispense", 3.0),
    ("Flip Chip Placement", 5.0),
    ("Thermal Compression Prebond", 5.0),
    ("Copper Pillar Reflow", 3.0),
    ("Compression Mold", 3.0),
    ("Transfer Mold", 3.0),
    ("Post Mold Cure", 2.0),
    ("Solder Ball Inspection", 3.0),
    ("Package Cleaning", 2.0),
    ("Lid Attach", 4.0),
    ("Heat Spreader Attach", 4.0),
    ("Substrate Bake", 2.0),
    ("Bump Co-Planarity Check", 3.0),
    ("Reel Sealing", 2.0),
    ("Tray Loading", 3.0),
    ("Wire Bond", 4.0),
    ("Electrical Continuity Inspection", 5.0),
    ("Fine Pitch Interconnect Inspection", 5.0),
    ("Micro Bump Alignment Verification", 4.0),
    ("Acoustic Delamination Inspection", 22.0),
    ("Laser Package Trimming", 3.0),
    ("Post Singulation Edge Inspection", 2.0),
    ("Mark Readback", 2.0),
    ("Tape Pocket Inspection", 2.0),
)


def sample_equipment_baseline() -> pd.DataFrame:
    """설비 DB 가 비었을 때 조회에만 보충하는 기존 보유대수 샘플을 새 표로 만든다."""
    return pd.DataFrame(
        {
            "공정": pd.Series([process for process, _ in SAMPLE_BASELINE_COUNTS], dtype="string"),
            "분류": pd.Series(["전체"] * len(SAMPLE_BASELINE_COUNTS), dtype="string"),
            "기존보유대수": pd.Series(
                [count for _, count in SAMPLE_BASELINE_COUNTS], dtype="float64"
            ),
            "비고": pd.Series([SAMPLE_BASELINE_NOTE] * len(SAMPLE_BASELINE_COUNTS), dtype="string"),
        }
    )


# 데모 fleet 이 서는 동·층. 한 층에 몰아 두면 Space 배치도가 한 장만 차고 나머지 층은
# 비어, 「층을 갈아 가며 본다」는 이 화면의 쓰임이 드러나지 않는다.
_FLEET_FLOORS = (
    ("C1", "1F"),
    ("C1", "2F"),
    ("C2", "2F"),
    ("C2", "3F"),
    ("C3", "1F"),
    ("C4", "2F"),
)
# 층마다 3 × 3 격자. 캔버스 기본값 100 × 60 안에 여백을 두고 들어간다.
_FLEET_COLUMN_X = (8.0, 38.0, 68.0)
_FLEET_ROW_Y = (8.0, 26.0, 44.0)
_FLEET_UNIT_SIZE = (12.0, 7.0)
_FLEET_PROCESSES = (
    "TC Bonding",
    "Underfill",
    "Mold",
    "Die Attach",
    "Final Test",
    "Burn-In",
)
# 상태 분포. 가용이 다수여야 현실적이고, 나머지 상태가 **하나씩은** 있어야 범례의 색이
# 전부 화면에 뜬다. 25 칸 주기를 fleet 크기와 어긋나게 두어 층마다 구성이 달라진다.
_FLEET_KIND_CYCLE = (
    "가용",
    "가용",
    "가용",
    "셋업",
    "가용",
    "가용",
    "입고예정",
    "가용",
    "가용",
    "비가동",
    "가용",
    "반출예정",
    "가용",
    "가용",
    "셋업",
    "가용",
    "이설예정",
    "가용",
    "가용",
    "보관",
    "가용",
    "기존",
    "가용",
    "입고예정",
    "가용",
)
_DOWNTIME_KINDS = ("고장", "예방보전", "개조")


@dataclass(frozen=True)
class _FleetSchedule:
    """상태 하나를 일정 여섯 개로 푼 결과. 값은 기준일로부터의 일수다."""

    vibration: int | None = None
    logistics: int | None = None
    arrival: int | None = None
    qual: int | None = None
    confirmation: str | None = None
    removal: int | None = None
    relocation: int | None = None
    storage: str = "N"
    existing: str = "N"


def sample_equipment_master(*, anchor_date: date | None = None) -> pd.DataFrame:
    """생애주기 상태를 모두 덮는 비영속 데모 fleet.

    예전에는 상태마다 한 대씩 일곱 대였다. 상태 색을 **확인**하기에는 충분했지만 Space
    배치도·주차별 추이·생애주기 Gantt 는 그 일곱 대로는 「이 화면이 무엇을 보여 주는가」를
    말하지 못한다. 층을 갈아 가며 보는 화면에서 한 층에 두 대가 서 있으면 배치도가 아니라
    점 두 개다.

    난수를 쓰지 않는다. 다시 열 때마다 배치가 달라지면 화면을 두고 이야기할 수가 없다.
    """
    anchor = pd.Timestamp(anchor_date or date.today()).normalize()
    common = {
        "구분": "임시 샘플",
        "공정대분류": "B/N",
        "Maker": "Sample Maker",
        "Model": "Sample Model",
        "공정구분": "Line-A",
        "투자Capa": None,
        "투자구분": "양산",
        "담당자": "샘플 담당자",
        "설비가동현황": None,
        "호기이력": "화면 검토용 샘플",
        "설비이력": "화면 검토용 샘플 · DB 미저장",
        "레이아웃표시": "Y",
    }
    records: list[dict[str, object]] = []
    for index, (equipment_id, building, floor, x, y) in enumerate(_fleet_slots()):
        kind = _FLEET_KIND_CYCLE[index % len(_FLEET_KIND_CYCLE)]
        schedule = _fleet_schedule(kind, index)
        records.append(
            {
                EQUIPMENT_ID_COLUMN: equipment_id,
                **common,
                "공정소분류": _FLEET_PROCESSES[index % len(_FLEET_PROCESSES)],
                "동": building,
                "층": floor,
                "X좌표": x,
                "Y좌표": y,
                "Xsize": _FLEET_UNIT_SIZE[0],
                "Ysize": _FLEET_UNIT_SIZE[1],
                "제진대일정": _offset_date(anchor, schedule.vibration),
                "물류일정": _offset_date(anchor, schedule.logistics),
                ARRIVAL_DATE_COLUMN: _offset_date(anchor, schedule.arrival),
                "Qual일정": _offset_date(anchor, schedule.qual),
                "확정상태": schedule.confirmation,
                "반출일정": _offset_date(anchor, schedule.removal),
                RELOCATION_DATE_COLUMN: _offset_date(anchor, schedule.relocation),
                STORAGE_FLAG_COLUMN: schedule.storage,
                "기존설비여부": schedule.existing,
                # 같은 공정에 생산성이 다른 모델이 섞인 모습을 샘플에서도 볼 수 있게 둔다.
                # 전부 1.0 이면 빈 DB 로 여는 사람은 이 컬럼이 무엇을 하는지 알 수 없다.
                "환산비": _fleet_conversion_ratio(index),
                USAGE_BASIS_COLUMN: _fleet_usage_basis(index),
            }
        )
    return prepare_equipment_master(pd.DataFrame(records, columns=EQUIPMENT_COLUMNS))


def sample_downtime_schedule(*, anchor_date: date | None = None) -> pd.DataFrame:
    """데모 fleet 의 비가동 일정.

    지금 걸려 있는 비가동뿐 아니라 **지나간 것과 앞으로 올 것**도 넣는다. 생애주기 Gantt 는
    구간을 보여 주는 화면인데 오늘 하루짜리만 있으면 그 줄이 한 점으로 보인다.
    """
    anchor = pd.Timestamp(anchor_date or date.today()).normalize()
    records: list[dict[str, object]] = []
    for index, (equipment_id, _, _, _, _) in enumerate(_fleet_slots()):
        kind = _FLEET_KIND_CYCLE[index % len(_FLEET_KIND_CYCLE)]
        spans: tuple[tuple[int, int], ...]
        if kind == "비가동":
            spans = ((-(2 + index % 5), 4 + index % 9),)
        elif kind == "가용" and index % 7 == 3:
            # 가용 설비에도 지나간 비가동이 있다. 그래야 Gantt 가 「지금」이 아니라 「이력」을
            # 보여 주는 화면이 된다.
            spans = ((-(90 + index), -(80 + index)), (45 + index % 30, 52 + index % 30))
        else:
            continue
        for span_index, (begins, ends) in enumerate(spans):
            records.append(
                {
                    EQUIPMENT_ID_COLUMN: equipment_id,
                    "비가동유형": _DOWNTIME_KINDS[(index + span_index) % len(_DOWNTIME_KINDS)],
                    "시작일": anchor + pd.Timedelta(days=begins),
                    "종료일": anchor + pd.Timedelta(days=ends),
                    "상세사유": "화면 검토용 샘플 비가동",
                    "비고": "DB 미저장",
                }
            )
    return prepare_downtime_schedule(pd.DataFrame(records, columns=DOWNTIME_COLUMNS))


def _fleet_slots() -> list[tuple[str, str, str, float, float]]:
    """호기 이름과 자리. 이름에 동·층이 들어가야 배치도와 표를 눈으로 맞출 수 있다."""
    slots: list[tuple[str, str, str, float, float]] = []
    for building, floor in _FLEET_FLOORS:
        position = 0
        for y in _FLEET_ROW_Y:
            for x in _FLEET_COLUMN_X:
                position += 1
                slots.append((f"SAMPLE-{building}{floor}-{position:02d}", building, floor, x, y))
    return slots


def _fleet_schedule(kind: str, index: int) -> _FleetSchedule:
    """상태 하나를 일정 여섯 개로 푼다. 검증 규칙이 요구하는 순서를 여기서 지킨다.

    제진대 ≤ 물류 ≤ 입고 ≤ Qual 이어야 하고, Qual 이 있는 신규 호기는 확정상태가 있어야 한다.
    반출일정과 이설일정은 함께 둘 수 없다. 샘플은 상태를 보이려고 신규 호기마다 입고·Qual 을 둔다
    (일정은 비워도 저장되지만 그러면 입고 예정·셋업 진행중에 머문다).
    """
    if kind == "보관":
        return _FleetSchedule(storage="Y")
    if kind == "기존":
        return _FleetSchedule(existing="Y")

    if kind == "입고예정":
        arrival = 25 + index % 40
        return _FleetSchedule(
            vibration=arrival - 20,
            logistics=arrival - 10,
            arrival=arrival,
            qual=arrival + 25,
            confirmation="계획",
        )
    if kind == "셋업":
        arrival = -(8 + index % 20)
        return _FleetSchedule(
            vibration=arrival - 20,
            logistics=arrival - 10,
            arrival=arrival,
            qual=14 + index % 25,
            confirmation="지연" if index % 3 == 0 else "확정",
        )

    # 나머지는 이미 Qual 을 마친 설비다. 반출·이설만 그 위에 얹는다.
    arrival = -(120 + index * 4)
    settled = _FleetSchedule(
        vibration=arrival - 20,
        logistics=arrival - 10,
        arrival=arrival,
        qual=arrival + 25,
        confirmation="완료",
    )
    if kind == "반출예정":
        return replace(settled, removal=20 + index % 70)
    if kind == "이설예정":
        return replace(settled, relocation=30 + index % 60)
    return settled


# 사용기준이 HBM 이 아닌 샘플 호기 자리. Dynamic 가용대수는 HBM 만 세므로(`counts_for_capacity`)
# 이 호기들은 배치도·호기 목록에는 서고 가용대수에서는 빠진다 — 그 알림 줄이 샘플에서도 보이게 둔다.
_FLEET_NON_HBM_SLOTS = (8, 25)
_FLEET_NON_HBM_BASIS = "범용"


def _fleet_usage_basis(index: int) -> str:
    """사용기준. 대부분 HBM 이고 몇 대만 다른 값이다."""
    return _FLEET_NON_HBM_BASIS if index in _FLEET_NON_HBM_SLOTS else COUNTED_USAGE_BASIS[0]


def _fleet_conversion_ratio(index: int) -> float:
    """환산비. 몇 대만 1.0 에서 벗어나게 두어 컬럼이 하는 일이 보이게 한다."""
    if index % 11 == 4:
        return 1.5
    if index % 13 == 7:
        return 0.8
    return DEFAULT_CONVERSION_RATIO


def _offset_date(anchor: pd.Timestamp, offset: int | None) -> pd.Timestamp | None:
    return None if offset is None else anchor + pd.Timedelta(days=offset)


def untouched_sample_baseline_rows(baseline: pd.DataFrame) -> pd.DataFrame:
    """편집기에 채워 준 샘플 그대로인 행만 골라낸다.

    `sample_equipment_baseline()` 은 설비 DB 가 비었을 때 **화면 표시용**으로만 채워 넣는
    값인데, 그대로 저장하면 불변 리비전에 영구 기록된다. 그 숫자는 합성 생성기
    `scripts/generate_sample_core_data.py` 의 `PROCESS_SPECS.owned` 를 옮겨 적은 고정
    리터럴이고 공정명도 그 생성기가 정한 합성 이름이다. 실제 공정명이 다르면 호기 마스터와 절대
    붙지 않는 유령 공정이 총대수·가용대수·가용률에 영원히 섞인다.

    값을 하나라도 고쳤으면 그 행은 사용자의 것이므로 걸러 내지 않는다. **네 컬럼이 모두
    샘플과 같은 행만** 고른다.
    """
    if baseline.empty:
        return baseline.iloc[0:0]
    sample = sample_equipment_baseline()
    columns = list(sample.columns)
    if any(column not in baseline.columns for column in columns):
        return baseline.iloc[0:0]
    normalized = baseline.loc[:, columns].copy()
    for column in ("공정", "분류", "비고"):
        normalized[column] = normalized[column].astype("string").str.strip()
    normalized["기존보유대수"] = pd.to_numeric(normalized["기존보유대수"], errors="coerce")
    marker = normalized.merge(sample, on=columns, how="left", indicator=True)
    return baseline.loc[(marker["_merge"] == "both").to_numpy()]
