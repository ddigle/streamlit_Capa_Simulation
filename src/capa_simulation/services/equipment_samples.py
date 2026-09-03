# Purpose: 설비 전용 DB가 비어 있을 때만 화면에 보여줄 비영속 샘플 데이터를 만든다.

"""설비 전용 DB가 비어 있을 때만 화면에 보여줄 비영속 샘플 데이터를 만든다."""

from __future__ import annotations

from datetime import date

import pandas as pd

from capa_simulation.services.equipment_contract import (
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)

SAMPLE_BASELINE_COUNTS = (
    ("Pre B/D", 46.0),
    ("Wafer_Sorter", 18.0),
    ("AVI-CoW", 21.0),
    ("Laser Grooving", 16.0),
    ("Wafer Grinding", 14.0),
    ("Wafer Mount", 12.0),
    ("Wafer Saw", 19.0),
    ("Plasma Clean", 25.0),
    ("DAF Attach", 35.0),
    ("Die Attach", 42.0),
    ("TC Bonding", 51.0),
    ("Mass Reflow", 18.0),
    ("Underfill", 38.0),
    ("Mold", 27.0),
    ("Cure", 13.0),
    ("Laser Marking", 15.0),
    ("Ball Attach", 32.0),
    ("Flux Clean", 17.0),
    ("Singulation", 29.0),
    ("Package Sorter", 20.0),
    ("Burn-In", 48.0),
    ("Final Test", 44.0),
    ("AVI-PKG", 23.0),
    ("O/S Test", 18.0),
    ("Taping", 16.0),
    ("Packing", 12.0),
    ("X-Ray", 26.0),
    ("SAM", 22.0),
    ("Warpage", 19.0),
    ("Shipping Inspection", 10.0),
)


def sample_equipment_baseline() -> pd.DataFrame:
    """Return a detached baseline copied from the development Core Data sample."""
    return pd.DataFrame(
        {
            "공정": pd.Series([process for process, _ in SAMPLE_BASELINE_COUNTS], dtype="string"),
            "분류": pd.Series(["전체"] * len(SAMPLE_BASELINE_COUNTS), dtype="string"),
            "기존보유대수": pd.Series(
                [count for _, count in SAMPLE_BASELINE_COUNTS], dtype="float64"
            ),
            "비고": pd.Series(
                ["Core Data 개발 샘플"] * len(SAMPLE_BASELINE_COUNTS), dtype="string"
            ),
        }
    )


def sample_equipment_master(*, anchor_date: date | None = None) -> pd.DataFrame:
    """Return unsaved sample units spanning every active lifecycle status."""
    anchor = pd.Timestamp(anchor_date or date.today()).normalize()
    common = {
        "공정대분류": "B/N",
        "라인구분": "Line-A",
        "활용구분": "양산",
        "사업부": "PKG",
        "투자기준": "샘플",
        "Maker": "Sample Maker",
        "모델": "Sample Model",
        "분류1": "임시 샘플",
        "분류2": None,
        "분류3": None,
        "호기이력": "화면 검토용 샘플",
        "비고": "화면 검토용 샘플 · DB 미저장",
        "레이아웃표시": "Y",
    }
    specifications = (
        # 호기, 공정, 동, 층, X, Y, 제진, 물류, 입고, Qual, 반출, 이설, 보관, 기존
        ("SAMPLE-IN-01", "TC Bonding", "C1", "1F", 5.0, 6.0, 5, 9, 14, 25, None, None, "N", "N"),
        (
            "SAMPLE-SETUP-01",
            "TC Bonding",
            "C1",
            "1F",
            22.0,
            6.0,
            -18,
            -14,
            -8,
            8,
            None,
            None,
            "N",
            "N",
        ),
        (
            "SAMPLE-AVBL-01",
            "Underfill",
            "C2",
            "2F",
            5.0,
            18.0,
            -40,
            -35,
            -30,
            -20,
            None,
            None,
            "N",
            "N",
        ),
        (
            "SAMPLE-OUT-01",
            "Underfill",
            "C2",
            "2F",
            22.0,
            18.0,
            -50,
            -45,
            -40,
            -30,
            12,
            None,
            "N",
            "N",
        ),
        ("SAMPLE-MOVE-01", "Mold", "C3", "1F", 5.0, 30.0, -50, -45, -40, -30, None, 18, "N", "N"),
        (
            "SAMPLE-STORE-01",
            "Mold",
            "C3",
            "1F",
            22.0,
            30.0,
            None,
            None,
            None,
            None,
            None,
            None,
            "Y",
            "N",
        ),
        (
            "SAMPLE-DOWN-01",
            "Mold",
            "C3",
            "1F",
            39.0,
            30.0,
            None,
            None,
            None,
            None,
            None,
            None,
            "N",
            "Y",
        ),
    )
    confirmation_by_equipment = {
        "SAMPLE-IN-01": "계획",
        "SAMPLE-SETUP-01": "확정",
        "SAMPLE-AVBL-01": "완료",
        "SAMPLE-OUT-01": "완료",
        "SAMPLE-MOVE-01": "지연",
    }
    records: list[dict[str, object]] = []
    for (
        equipment_id,
        process,
        building,
        floor,
        x,
        y,
        vibration,
        logistics,
        arrival,
        qual,
        removal,
        relocation,
        storage,
        existing,
    ) in specifications:
        records.append(
            {
                "호기": equipment_id,
                **common,
                "공정소분류": process,
                "동": building,
                "층": floor,
                "X좌표": x,
                "Y좌표": y,
                "Xsize": 12.0,
                "Ysize": 7.0,
                "제진대일정": _offset_date(anchor, vibration),
                "물류일정": _offset_date(anchor, logistics),
                "입고일정": _offset_date(anchor, arrival),
                "Qual일정": _offset_date(anchor, qual),
                "확정상태": confirmation_by_equipment.get(equipment_id),
                "반출일정": _offset_date(anchor, removal),
                "이설일": _offset_date(anchor, relocation),
                "장기보관여부": storage,
                "기존설비여부": existing,
            }
        )
    return prepare_equipment_master(pd.DataFrame(records, columns=EQUIPMENT_COLUMNS))


def sample_downtime_schedule(*, anchor_date: date | None = None) -> pd.DataFrame:
    """Return an unsaved active downtime event for the sample equipment master."""
    anchor = pd.Timestamp(anchor_date or date.today()).normalize()
    return prepare_downtime_schedule(
        pd.DataFrame(
            [
                {
                    "호기": "SAMPLE-DOWN-01",
                    "비가동유형": "고장",
                    "시작일": anchor - pd.Timedelta(days=2),
                    "종료일": anchor + pd.Timedelta(days=5),
                    "상세사유": "화면 검토용 샘플 비가동",
                    "비고": "DB 미저장",
                }
            ],
            columns=DOWNTIME_COLUMNS,
        )
    )


def _offset_date(anchor: pd.Timestamp, offset: int | None) -> pd.Timestamp | None:
    return None if offset is None else anchor + pd.Timedelta(days=offset)
