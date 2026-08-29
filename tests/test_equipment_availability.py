from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    build_inactive_equipment,
    build_milestone_transition_events,
    build_space_equipment_status,
    build_weekly_equipment_availability,
    prepare_downtime_schedule,
    prepare_equipment_master,
    sample_equipment_baseline,
)


def _baseline() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["Process-A"],
            "분류": ["전체"],
            "기존보유대수": [2],
            "비고": [None],
        }
    )


def _equipment() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "호기": ["EQ-01", "EQ-02"],
            "공정": ["Process-A", "Process-A"],
            "분류": ["전체", "전체"],
            "동": ["C1", "C1"],
            "층": ["1F", "1F"],
            "X": [10, 30],
            "Y": [10, 10],
            "너비": [12, 12],
            "사전인프라완료일": ["2026-08-01", "2026-08-08"],
            "입고일": ["2026-08-04", "2026-08-11"],
            "Hookup완료일": ["2026-08-05", "2026-08-12"],
            "하드웨어셋업완료일": ["2026-08-06", "2026-08-13"],
            "Qual완료일": ["2026-08-07", None],
            "TTTM완료일": ["2026-08-08", None],
            "양산전환일": ["2026-08-09", None],
            "비고": [None, "일정 미정"],
        }
    )


def _downtime() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "비가동ID": ["DOWN-01"],
            "호기": ["EQ-01"],
            "비가동유형": ["고장"],
            "시작일": ["2026-08-10"],
            "종료일": ["2026-08-20"],
            "상세사유": ["부품 교체"],
            "비고": [None],
        }
    )


def test_sample_baseline_matches_development_process_sample() -> None:
    result = sample_equipment_baseline()

    assert len(result) == 30
    assert result["분류"].unique().tolist() == ["전체"]
    assert result.loc[result["공정"].eq("TC Bonding"), "기존보유대수"].item() == 51.0


def test_weekly_counts_use_production_transition_and_downtime() -> None:
    result = build_weekly_equipment_availability(
        _baseline(),
        _equipment(),
        _downtime(),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 16),
    )

    assert result["Weeknum"].tolist() == ["26-W32", "26-W33"]
    assert result["총대수"].tolist() == [3, 4]
    assert result["가용대수"].tolist() == [3, 2]
    assert result["셋업중대수"].tolist() == [0, 1]
    assert result["운영비가동대수"].tolist() == [0, 1]
    assert result["비가동대수"].tolist() == [0, 2]


def test_space_status_shows_stage_and_downtime_override() -> None:
    result = build_space_equipment_status(
        _equipment(),
        _downtime(),
        as_of=date(2026, 8, 16),
    )

    assert result["단계"].tolist() == ["양산", "H/W 셋업"]
    assert result["상태"].tolist() == ["비가동", "H/W 셋업"]
    assert result.loc[0, "비가동유형"] == "고장"
    assert pd.isna(result.loc[1, "비가동유형"])


def test_milestone_transition_events_include_completed_and_planned_stages() -> None:
    result = build_milestone_transition_events(
        _equipment(),
        start_date=date(2026, 8, 5),
        end_date=date(2026, 8, 12),
        as_of=date(2026, 8, 8),
    )

    assert len(result) == 8
    assert result["일정상태"].value_counts().to_dict() == {"완료": 5, "예정": 3}
    production = result.loc[result["호기"].eq("EQ-01") & result["전환단계"].eq("양산")].iloc[0]
    assert production["이전단계"] == "TTTM"
    assert production["전환일"] == pd.Timestamp("2026-08-09")
    assert production["기준일대비"] == "D-1"


def test_milestone_transition_events_reject_invalid_range() -> None:
    with pytest.raises(ValueError, match="시작일"):
        build_milestone_transition_events(
            _equipment(),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 8, 1),
            as_of=date(2026, 8, 8),
        )


def test_inactive_equipment_includes_setup_and_operational_downtime() -> None:
    result = build_inactive_equipment(
        _equipment(),
        _downtime(),
        as_of=date(2026, 8, 16),
    )

    assert result["호기"].tolist() == ["EQ-01", "EQ-02"]
    assert result["상태"].tolist() == ["운영 비가동", "양산 준비 중"]


def test_equipment_rejects_invalid_milestone_order() -> None:
    equipment = _equipment()
    equipment.loc[0, "Qual완료일"] = "2026-08-03"

    with pytest.raises(ValueError, match="순서"):
        prepare_equipment_master(equipment)


def test_downtime_rejects_unknown_equipment() -> None:
    downtime = _downtime()
    downtime.loc[0, "호기"] = "UNKNOWN"

    with pytest.raises(ValueError, match="없는 설비"):
        prepare_downtime_schedule(downtime, equipment=_equipment())
