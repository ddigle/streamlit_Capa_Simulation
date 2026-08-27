from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    build_inactive_equipment,
    build_weekly_equipment_availability,
    prepare_equipment_schedule,
    sample_equipment_baseline,
)


def _baseline() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Process-A"],
            "분류": ["기존 보유"],
            "기존보유대수": [2],
            "비고": [None],
        }
    )


def _schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "호기": ["EQ-01", "EQ-02"],
            "공정": ["Process-A", "Process-A"],
            "분류": ["기존 보유", "기존 보유"],
            "입고일": ["2026-08-04", "2026-08-11"],
            "셋업시작일": ["2026-08-05", "2026-08-12"],
            "셋업완료일": ["2026-08-08", None],
            "비고": [None, "일정 미정"],
        }
    )


def test_sample_baseline_matches_development_process_sample() -> None:
    result = sample_equipment_baseline()

    assert len(result) == 30
    assert result["분류"].unique().tolist() == ["전체"]
    assert result.loc[result["공정"].eq("TC Bonding"), "기존보유대수"].item() == 51.0
    assert result.loc[result["공정"].eq("Shipping Inspection"), "기존보유대수"].item() == 10.0


def test_weekly_counts_follow_arrival_and_setup_completion() -> None:
    result = build_weekly_equipment_availability(
        _baseline(),
        _schedule(),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 16),
    )

    assert result["주차시작일"].tolist() == [date(2026, 8, 3), date(2026, 8, 10)]
    assert result["Weeknum"].tolist() == ["26-W32", "26-W33"]
    assert result["총대수"].tolist() == [3, 4]
    assert result["가용대수"].tolist() == [3, 3]
    assert result["비가동대수"].tolist() == [0, 1]


def test_weeknum_uses_iso_year_across_calendar_year_boundary() -> None:
    result = build_weekly_equipment_availability(
        _baseline(),
        _schedule().iloc[0:0],
        start_date=date(2025, 12, 29),
        end_date=date(2026, 1, 4),
    )

    assert result["Weeknum"].tolist() == ["26-W01"]


def test_inactive_equipment_returns_arrived_unfinished_units() -> None:
    result = build_inactive_equipment(_schedule(), as_of=date(2026, 8, 16))

    assert result["호기"].tolist() == ["EQ-02"]
    assert result["상태"].tolist() == ["셋업 진행 중"]


def test_schedule_rejects_invalid_date_order() -> None:
    schedule = _schedule()
    schedule.loc[0, "셋업완료일"] = "2026-08-03"

    with pytest.raises(ValueError, match="순서"):
        prepare_equipment_schedule(schedule)
