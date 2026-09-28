# Purpose: 설비 세 표의 선택 삭제가 키로 행을 고르고 딸린 비가동 일정까지 빼고 되돌리는지 검증한다.

"""**행 번호가 아니라 키로 지운다.**

편집본은 제출마다 다시 만들어지고, 필터 없이 행을 지우면 편집표가 번호를 다시 매긴다.
번호로 기억한 선택은 다음 실행에 다른 행을 가리킨다. 그래서 업무 키로 고르고 키로 지운다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from capa_simulation.services.equipment_bulk_delete import (
    BASELINE_TARGET,
    DOWNTIME_TARGET,
    EQUIPMENT_TARGET,
    apply_deletion,
    checked_keys,
    matching_keys,
    normalize_key_value,
    plan_deletion,
    restore_rows,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    baseline = pd.DataFrame(
        {
            "공정": ["DEMO_A", "DEMO_A", "DEMO_B"],
            "분류": ["전체", "신형", "전체"],
            "기존보유대수": [3, 1, 2],
        }
    )
    equipment = pd.DataFrame(
        {
            "호기": ["E1", "E2", "E3", " E4 "],
            "공정소분류": ["DEMO_A", "DEMO_A", "DEMO_B", "DEMO_B"],
            "동": ["A동", "B동", "A동", "A동"],
        }
    )
    downtime = pd.DataFrame(
        {
            "호기": ["E1", "E1", "E3", "E9"],
            "비가동유형": ["PM", "고장", "PM", "PM"],
            "시작일": [
                pd.Timestamp("2026-10-01"),
                date(2026, 11, 2),
                "2026-12-03",
                pd.Timestamp("2026-10-05"),
            ],
        }
    )
    return baseline, equipment, downtime


def test_the_same_key_reads_the_same_whatever_shape_it_arrives_in() -> None:
    """편집표를 지나면 같은 날짜가 Timestamp·date·글자로 섞여 온다."""
    assert normalize_key_value(" E1 ") == "E1"
    assert normalize_key_value(None) == normalize_key_value(float("nan")) == ""
    assert normalize_key_value(pd.NaT, is_date=True) == ""
    for value in (pd.Timestamp("2026-10-01 00:00"), date(2026, 10, 1), "2026-10-01"):
        assert normalize_key_value(value, is_date=True) == "2026-10-01"


def test_only_checked_cells_count_and_untouched_ones_arrive_as_none() -> None:
    edited = pd.DataFrame({"선택": [True, None, False], "호기": ["E1", "E2", "E3"]})

    assert checked_keys(edited, "선택", EQUIPMENT_TARGET) == {("E1",)}


def test_a_filter_picks_the_rows_it_would_show_and_no_filter_picks_all() -> None:
    _, equipment, _ = _frames()

    assert matching_keys(equipment, {"동": ["A동"]}, EQUIPMENT_TARGET) == {
        ("E1",),
        ("E3",),
        ("E4",),
    }
    assert len(matching_keys(equipment, {}, EQUIPMENT_TARGET)) == 4


def test_deleting_machines_takes_their_downtime_with_them() -> None:
    """남겨 두면 저장이 「호기 마스터에 없는 설비의 비가동 일정」으로 막힌다."""
    frames = _frames()

    plan = plan_deletion(frames, EQUIPMENT_TARGET, {("E1",), ("E3",)})
    baseline, equipment, downtime = apply_deletion(frames, plan)

    assert (plan.target_count, plan.cascaded_downtime_count) == (2, 3)
    assert equipment["호기"].str.strip().tolist() == ["E2", "E4"]
    assert downtime["호기"].tolist() == ["E9"]
    assert baseline.equals(frames[0])


def test_deleting_other_tables_touches_only_that_table() -> None:
    frames = _frames()

    baseline_plan = plan_deletion(frames, BASELINE_TARGET, {("DEMO_A", "전체")})
    downtime_plan = plan_deletion(frames, DOWNTIME_TARGET, {("E1", "고장", "2026-11-02")})

    assert apply_deletion(frames, baseline_plan)[0]["분류"].tolist() == ["신형", "전체"]
    assert baseline_plan.cascaded_downtime_count == 0
    assert apply_deletion(frames, downtime_plan)[2]["비가동유형"].tolist() == ["PM", "PM", "PM"]


def test_duplicate_keys_in_an_unvalidated_draft_all_go() -> None:
    baseline, equipment, downtime = _frames()
    equipment = pd.concat([equipment, equipment.iloc[[0]]], ignore_index=True)

    plan = plan_deletion((baseline, equipment, downtime), EQUIPMENT_TARGET, {("E1",)})

    assert plan.target_count == 2


def test_undo_puts_rows_back_but_never_duplicates_a_key() -> None:
    """방금 지운 뒤 같은 호기를 다시 넣었으면 그 행은 되살리지 않고 센다."""
    frames = _frames()
    plan = plan_deletion(frames, EQUIPMENT_TARGET, {("E1",), ("E3",)})
    after = apply_deletion(frames, plan)
    readded = pd.concat([after[1], pd.DataFrame({"호기": ["E1"], "공정소분류": ["DEMO_A"]})])
    after = (after[0], readded.reset_index(drop=True), after[2])

    (baseline, equipment, downtime), skipped = restore_rows(after, plan.removed)

    assert skipped == 1
    assert sorted(equipment["호기"].str.strip()) == ["E1", "E2", "E3", "E4"]
    assert len(downtime) == 4
    assert baseline.equals(frames[0])
