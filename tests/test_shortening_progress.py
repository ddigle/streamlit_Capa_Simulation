# Purpose: 필요단축일정 진척 비교의 짝짓기·상태·요약·범위 차이·CSV 표를 고정한다.

"""필요단축일정 진척 비교(`services/shortening_progress.py`).

과거·현재는 같은 목표의 호기 표 두 벌이다. 날짜는 손으로 셀 수 있게 잡았다 — 단축일수 = 확보 시점
(기존 Qual) − 필요 시점(목표 Qual).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from test_required_shortening import JUNE, MAY, _plan, _unit

from capa_simulation.services.required_shortening import KIND_NEW, KIND_SHORTENED, LEVEL_COLUMN
from capa_simulation.services.shortening_baseline import freeze_plan
from capa_simulation.services.shortening_progress import (
    PROGRESS_COLUMNS,
    PROGRESS_EXPORT_COLUMNS,
    PROGRESS_IMPROVED,
    PROGRESS_KEPT_NEW,
    PROGRESS_LAPSED,
    PROGRESS_NEW,
    PROGRESS_OUT_OF_SCOPE,
    PROGRESS_RESOLVED,
    PROGRESS_UNCHANGED,
    PROGRESS_WORSENED,
    ProgressSummary,
    compare_progress,
    progress_export_frame,
    scope_difference,
    summarize_progress,
)

LG = "Laser Grooving"
DA = "DAF Attach"
TODAY = date(2026, 1, 1)
"""손으로 만든 표의 모든 시점보다 앞 — `필요 시점 지남` 이 없다."""


def _real(
    process: str, unit: str, need: date, secure: date, *, modules: int = 1
) -> dict[str, object]:
    return {
        "공정": process,
        "호기": unit,
        "구분": KIND_SHORTENED,
        "기존 Qual": secure,
        "목표 Qual": need,
        "단축일수": (secure - need).days,
        "모듈 수": modules,
    }


def _virtual(process: str, unit: str, need: date) -> dict[str, object]:
    return {
        "공정": process,
        "호기": unit,
        "구분": KIND_NEW,
        "기존 Qual": None,
        "목표 Qual": need,
        "단축일수": None,
        "모듈 수": 1,
    }


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = ["공정", "호기", "구분", "기존 Qual", "목표 Qual", "단축일수", "모듈 수"]
    frame = pd.DataFrame(rows, columns=columns)
    for column in ("단축일수", "모듈 수"):
        frame[column] = pd.to_numeric(frame[column]).astype("Int64")
    return frame


def _missing(value: object) -> bool:
    """`Int64` 빈칸 — `to_dict` 이 `pd.NA` 나 None 으로 준다."""
    return value is None or value is pd.NA


def _by_unit(rows: pd.DataFrame, process: str) -> dict[str, dict[str, object]]:
    chosen = rows.loc[rows["공정"].eq(process)]
    return {
        str(row["호기"]): {str(key): value for key, value in row.items()}
        for row in chosen.to_dict("records")
    }


def test_a_unit_present_both_times_is_improved_worsened_or_unchanged() -> None:
    """필요 +18일·확보 −13일이면 단축일수가 31일 준다. 필요가 9일 당겨지면 9일 는다."""
    past = _frame(
        [
            _real(LG, "SMP-LG-11", date(2027, 1, 5), date(2027, 3, 10)),
            _real(LG, "SMP-LG-12", date(2027, 3, 1), date(2027, 4, 20)),
            _real(LG, "SMP-LG-13", date(2027, 4, 1), date(2027, 5, 1)),
            _real(LG, "SMP-LG-14", date(2027, 4, 1), date(2027, 5, 1)),
        ]
    )
    current = _frame(
        [
            _real(LG, "SMP-LG-11", date(2027, 1, 23), date(2027, 2, 25)),
            _real(LG, "SMP-LG-12", date(2027, 2, 20), date(2027, 4, 20)),
            _real(LG, "SMP-LG-13", date(2027, 4, 1), date(2027, 5, 1)),
            # 두 시점이 같은 날수만큼 움직이면 단축일수는 그대로다 — 이동은 따로 남는다.
            _real(LG, "SMP-LG-14", date(2027, 4, 11), date(2027, 5, 11)),
        ]
    )

    rows = compare_progress(past, current, current_processes=[LG], today=TODAY)

    assert list(rows.columns) == list(PROGRESS_COLUMNS)
    units = _by_unit(rows, LG)
    improved = units["SMP-LG-11"]
    assert improved["상태"] == PROGRESS_IMPROVED
    assert (improved["과거 단축일수"], improved["현재 단축일수"]) == (64, 33)
    assert improved["단축일수 증감"] == -31
    assert improved["필요 시점 이동(일)"] == 18
    assert improved["확보 시점 이동(일)"] == -13
    assert improved["과거 필요 시점"] == date(2027, 1, 5)
    assert improved["현재 확보 시점"] == date(2027, 2, 25)
    worsened = units["SMP-LG-12"]
    assert worsened["상태"] == PROGRESS_WORSENED
    assert worsened["단축일수 증감"] == 9
    assert (worsened["필요 시점 이동(일)"], worsened["확보 시점 이동(일)"]) == (-9, 0)
    assert units["SMP-LG-13"]["상태"] == PROGRESS_UNCHANGED
    moved = units["SMP-LG-14"]
    assert moved["상태"] == PROGRESS_UNCHANGED
    assert (moved["필요 시점 이동(일)"], moved["확보 시점 이동(일)"]) == (10, 10)


def test_a_unit_only_now_is_new_and_only_then_is_resolved() -> None:
    past = _frame([_real(DA, "SMP-DAF-11", date(2026, 10, 20), date(2026, 11, 25))])
    current = _frame([_real(DA, "SMP-DAF-13", date(2027, 5, 20), date(2027, 6, 15))])

    rows = compare_progress(past, current, current_processes=[DA], today=TODAY)

    units = _by_unit(rows, DA)
    resolved = units["SMP-DAF-11"]
    assert resolved["상태"] == PROGRESS_RESOLVED
    assert resolved["현재 필요 시점"] is None and _missing(resolved["현재 단축일수"])
    # 한쪽에만 있는 호기는 없는 쪽을 0일로 세어 합계 차이와 맞는다.
    assert resolved["단축일수 증감"] == -36
    new = units["SMP-DAF-13"]
    assert new["상태"] == PROGRESS_NEW
    assert new["단축일수 증감"] == 26
    assert _missing(new["필요 시점 이동(일)"])
    summary = summarize_progress(rows, [DA])
    assert (summary.past_days, summary.current_days, summary.change) == (36, 26, -10)
    assert (summary.new, summary.resolved) == (1, 1)


def test_a_module_bundle_pairs_by_its_unit_key() -> None:
    """모듈 묶음은 설비키(Main 설비) 한 줄이다 — 그 키끼리 짝짓고 모듈 수를 싣는다."""
    past = _frame([_real(DA, "G9", date(2027, 4, 10), date(2027, 5, 20), modules=2)])
    current = _frame([_real(DA, "G9", date(2027, 3, 31), date(2027, 5, 10), modules=2)])

    rows = compare_progress(past, current, current_processes=[DA], today=TODAY)

    (row,) = rows.to_dict("records")
    assert (row["호기"], row["모듈 수"], row["상태"]) == ("G9", 2, PROGRESS_UNCHANGED)
    assert (row["필요 시점 이동(일)"], row["확보 시점 이동(일)"]) == (-10, -10)


def test_virtual_units_pair_by_their_order_within_the_process() -> None:
    """추가N 은 공정 안 차례로 짝짓는다. 과거에만 있으면 해소(신규 투자 불필요)다."""
    past = _frame(
        [
            _virtual(LG, "추가2", date(2027, 6, 1)),
            _virtual(LG, "추가1", date(2027, 5, 15)),
            _virtual(DA, "추가1", date(2027, 3, 1)),
        ]
    )
    current = _frame(
        [
            _virtual(LG, "추가1", date(2027, 5, 25)),
            _virtual(DA, "추가1", date(2027, 3, 1)),
            _virtual(DA, "추가2", date(2027, 4, 1)),
        ]
    )

    rows = compare_progress(past, current, current_processes=[LG, DA], today=TODAY)

    lg = _by_unit(rows, LG)
    assert list(lg) == ["추가1", "추가2"]
    assert lg["추가1"]["상태"] == PROGRESS_KEPT_NEW
    assert lg["추가1"]["필요 시점 이동(일)"] == 10
    assert _missing(lg["추가1"]["단축일수 증감"])
    assert lg["추가2"]["상태"] == PROGRESS_RESOLVED
    da = _by_unit(rows, DA)
    assert da["추가1"]["상태"] == PROGRESS_KEPT_NEW
    assert da["추가2"]["상태"] == PROGRESS_NEW
    summary = summarize_progress(rows)
    assert (summary.past_virtual, summary.current_virtual) == (3, 3)
    # 가상 호기는 단축일수가 없어 일수 합에 들지 않는다.
    assert (summary.past_days, summary.current_days) == (0, 0)
    assert (summary.kept_new, summary.new, summary.resolved) == (2, 1, 1)


def test_a_real_unit_and_a_virtual_unit_never_pair() -> None:
    """당긴 호기와 가상 호기는 짝짓는 풀이 다르다 — 이름이 같아도 섞이지 않는다."""
    past = _frame([_real(LG, "추가1", date(2027, 1, 1), date(2027, 2, 1))])
    current = _frame([_virtual(LG, "추가1", date(2027, 1, 10))])

    rows = compare_progress(past, current, current_processes=[LG], today=TODAY)

    assert set(zip(rows["구분"], rows["상태"], strict=True)) == {
        (KIND_NEW, PROGRESS_NEW),
        (KIND_SHORTENED, PROGRESS_RESOLVED),
    }


def test_a_baseline_process_outside_the_current_scope_is_not_resolved() -> None:
    """기준선 공정이 지금 맞댄 공정에 없으면 짝짓지 않는다 — 해소가 아니라 「지금 범위 밖」."""
    past = _frame(
        [
            _real("Old Process", "OLD-1", date(2027, 1, 1), date(2027, 2, 1)),
            _real(LG, "SMP-LG-11", date(2027, 1, 5), date(2027, 3, 10)),
        ]
    )
    current = _frame([_real(LG, "SMP-LG-11", date(2027, 1, 5), date(2027, 3, 10))])

    rows = compare_progress(past, current, current_processes=[LG, DA], today=TODAY)

    # 지금 맞댄 공정이 먼저, 범위 밖 공정이 뒤다. 짝이 없는 DA 는 행이 없다.
    assert list(rows["공정"]) == [LG, "Old Process"]
    out = _by_unit(rows, "Old Process")["OLD-1"]
    assert out["상태"] == PROGRESS_OUT_OF_SCOPE
    assert _missing(out["단축일수 증감"])
    in_scope = summarize_progress(rows, [LG, DA])
    assert in_scope == ProgressSummary(past_days=64, current_days=64, unchanged=1)
    outside = summarize_progress(rows, ["Old Process"])
    assert (outside.out_of_scope, outside.past_days, outside.current_days) == (1, 31, 0)


def test_rows_inside_a_process_follow_the_secure_date_then_the_virtual_units() -> None:
    past = _frame([_real(LG, "LG-9", date(2027, 1, 1), date(2027, 1, 20))])
    current = _frame(
        [
            _virtual(LG, "추가1", date(2027, 1, 2)),
            _real(LG, "LG-2", date(2027, 1, 1), date(2027, 3, 1)),
            _real(LG, "LG-1", date(2027, 1, 1), date(2027, 3, 1)),
        ]
    )

    rows = compare_progress(past, current, current_processes=[LG], today=TODAY)

    assert list(rows["호기"]) == ["LG-9", "LG-1", "LG-2", "추가1"]


def test_empty_inputs_give_an_empty_typed_frame() -> None:
    rows = compare_progress(_frame([]), _frame([]), current_processes=[LG], today=TODAY)

    assert rows.empty and list(rows.columns) == list(PROGRESS_COLUMNS)
    assert summarize_progress(rows) == ProgressSummary()


def test_the_scope_difference_names_months_and_processes() -> None:
    same = scope_difference(
        baseline_months=(202610, 202706),
        baseline_processes=[LG, DA],
        months=[202610, 202706],
        processes=[DA, LG],
    )
    assert not same.differs

    moved = scope_difference(
        baseline_months=(202610, 202706),
        baseline_processes=[LG, "Old Process"],
        months=[202611, 202612, 202707],
        processes=[LG, DA],
    )
    assert moved.months_differ and moved.current_months == (202611, 202707)
    assert (moved.added, moved.removed) == ((DA,), ("Old Process",))


def test_the_progress_csv_frame_follows_the_screen_order_with_iso_dates() -> None:
    past = _frame(
        [
            _real(LG, "SMP-LG-11", date(2027, 1, 5), date(2027, 3, 10)),
            _real(DA, "SMP-DAF-11", date(2026, 10, 20), date(2026, 11, 25)),
        ]
    )
    current = _frame([_real(LG, "SMP-LG-11", date(2027, 1, 23), date(2027, 2, 25))])
    rows = compare_progress(past, current, current_processes=[LG, DA], today=TODAY)

    frame = progress_export_frame(rows, level=1.1, processes=[DA, LG])

    assert list(frame.columns) == list(PROGRESS_EXPORT_COLUMNS)
    assert list(frame["공정"]) == [DA, LG]
    assert set(frame[LEVEL_COLUMN]) == {110}
    assert frame.loc[1, "과거 필요 시점"] == "2027-01-05"
    assert frame.loc[0, "현재 필요 시점"] is None
    assert list(frame["상태"]) == [PROGRESS_RESOLVED, PROGRESS_IMPROVED]
    # 화면에 없는 공정은 싣지 않는다.
    assert progress_export_frame(rows, level=1.1, processes=[DA])["공정"].tolist() == [DA]


def test_a_frozen_plan_compared_with_a_faster_schedule_reads_as_improved() -> None:
    """실제 계산 두 벌 — C3 의 Qual 이 6/15 → 6/1 로 당겨지면 C3 의 단축일수가 14일 준다."""
    units = [_unit("A1", date(2026, 5, 1)), _unit("B2", date(2026, 5, 31))]
    before = _plan([*units, _unit("C3", date(2026, 6, 15))], {MAY: 12 + 20 / 31})
    after = _plan([*units, _unit("C3", date(2026, 6, 1))], {MAY: 12 + 20 / 31})
    baseline_units = freeze_plan(before, name="이전").units
    past = baseline_units.loc[baseline_units[LEVEL_COLUMN].eq(100)].drop(columns=LEVEL_COLUMN)

    rows = compare_progress(
        past, after.at(1.0).units, current_processes=after.processes, today=after.today
    )

    units_by = _by_unit(rows, "Die Attach")
    assert units_by["A1"]["상태"] == PROGRESS_UNCHANGED
    assert units_by["B2"]["상태"] == PROGRESS_UNCHANGED
    assert units_by["C3"]["상태"] == PROGRESS_IMPROVED
    assert units_by["C3"]["확보 시점 이동(일)"] == -14
    assert units_by["C3"]["필요 시점 이동(일)"] == 0
    assert units_by["C3"]["단축일수 증감"] == -14
    summary = summarize_progress(rows)
    assert summary.change == -14 == summary.current_days - summary.past_days
    assert summary.past_days == pytest.approx(11 + 41 + 45)


def test_a_baseline_need_before_today_is_lapsed_and_not_counted_as_progress() -> None:
    """마스터·소요가 같아도 오늘만 4/1 → 5/25 로 지나면 지금 계획은 오늘보다 앞으로 당길 수 없어,
    필요 시점이 오늘로 밀려 단축일수가 줄거나(B2·C3) 후보에서 빠진다(A1). 그건 진척이 아니다."""
    units = [
        _unit("A1", date(2026, 5, 1)),
        _unit("B2", date(2026, 5, 31)),
        _unit("C3", date(2026, 6, 15)),
    ]
    required = {MAY: 12 + 20 / 31, JUNE: 12 + 20 / 31}
    then = _plan(units, required, today=date(2026, 4, 1))
    now = _plan(units, required, today=date(2026, 5, 25))
    baseline_units = freeze_plan(then, name="이전").units
    past = baseline_units.loc[baseline_units[LEVEL_COLUMN].eq(100)].drop(columns=LEVEL_COLUMN)

    # 저장한 그날의 계획과 견주면 아무것도 지나지 않았다 — 모두 변동 없음.
    same_day = compare_progress(
        past, then.at(1.0).units, current_processes=then.processes, today=then.today
    )
    assert set(same_day["상태"]) == {PROGRESS_UNCHANGED}

    rows = compare_progress(
        past, now.at(1.0).units, current_processes=now.processes, today=now.today
    )

    by_unit = _by_unit(rows, "Die Attach")
    assert {name: row["상태"] for name, row in by_unit.items()} == dict.fromkeys(
        ("A1", "B2", "C3"), PROGRESS_LAPSED
    )
    assert all(_missing(row["단축일수 증감"]) for row in by_unit.values())
    # 두 줄은 그대로 남는다 — B2 는 지금 필요 시점이 오늘 그 자체다.
    assert by_unit["B2"]["현재 필요 시점"] == now.today
    assert by_unit["A1"]["현재 필요 시점"] is None
    summary = summarize_progress(rows, now.processes)
    assert (summary.past_days, summary.current_days, summary.change) == (0, 0, 0)
    assert (summary.improved, summary.resolved, summary.lapsed) == (0, 0, 3)
    current_days = int(rows["현재 단축일수"].fillna(0).sum())
    assert summary.lapsed_current_days == current_days > 0


def test_a_need_on_today_is_still_compared_and_a_virtual_unit_can_lapse() -> None:
    """오늘 바로 그날은 지금 계획도 닿는다(엄격한 `<`). 필요 시점이 지난 추가N 은 홀로 서고 남은
    추가N 끼리 차례로 짝짓는다 — 지금 계획에는 오늘보다 앞의 신규 필요가 서지 않는다."""
    today = date(2027, 1, 5)
    past = _frame(
        [
            _real(LG, "SMP-LG-11", today, date(2027, 3, 10)),
            _real(LG, "SMP-LG-12", today - timedelta(days=1), date(2027, 3, 10)),
            _virtual(LG, "추가1", today - timedelta(days=1)),
            _virtual(LG, "추가2", date(2027, 6, 1)),
        ]
    )
    current = _frame(
        [
            _real(LG, "SMP-LG-11", today, date(2027, 3, 1)),
            _real(LG, "SMP-LG-12", today, date(2027, 3, 10)),
            _virtual(LG, "추가1", date(2027, 6, 1)),
        ]
    )

    rows = compare_progress(past, current, current_processes=[LG], today=today)

    by_unit = _by_unit(rows, LG)
    assert by_unit["SMP-LG-11"]["상태"] == PROGRESS_IMPROVED
    assert by_unit["SMP-LG-11"]["단축일수 증감"] == -9
    assert by_unit["SMP-LG-12"]["상태"] == PROGRESS_LAPSED
    virtual = rows.loc[rows["구분"].eq(KIND_NEW), "상태"].tolist()
    assert virtual == [PROGRESS_LAPSED, PROGRESS_KEPT_NEW]
    kept = rows.loc[rows["상태"].eq(PROGRESS_KEPT_NEW)].iloc[0]
    assert (kept["과거 필요 시점"], kept["현재 필요 시점"]) == (date(2027, 6, 1), date(2027, 6, 1))
    summary = summarize_progress(rows)
    # 견준 것은 SMP-LG-11 과 추가N 한 쌍 — 지난 둘은 일수·추가N 대수 양쪽에서 빠진다.
    assert (summary.past_days, summary.current_days) == (64, 55)
    assert (summary.past_virtual, summary.current_virtual, summary.lapsed) == (1, 1, 2)
