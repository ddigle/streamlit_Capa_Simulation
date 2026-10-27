# Purpose: 입력 비가동 대수 규칙(칸 검증·보이는 범위 병합·계산 키·가용 차감과 0 멈춤)을 검증한다.

"""`services/manual_downtime.py` — 2026-10-27 사용자 결정(공정 × 생산월 비가동 대수).

입력이 없으면 가용을 그대로(같은 객체) 돌려주고, 있으면 그 달 가용에서 빼되 0 에서 멈추고 넘친 칸을
알린다. 저장은 보이는 범위만 갈아 쓴다.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from capa_simulation.services.manual_downtime import (
    MANUAL_DOWNTIME_BAND,
    MANUAL_DOWNTIME_EFFECT_COLUMNS,
    ManualDowntime,
    apply_manual_downtime,
    changed_cell_count,
    clamp_manual_units,
    manual_cell_value,
    manual_downtime_key,
    manual_effect_band,
    manual_rows_for_process,
    manual_units_text,
    merge_visible_cells,
    overdrawn_rows,
    period_months,
    prepare_manual_downtime,
)

A, B = "Wafer Mount", "Final Test"


def _available(rows: list[tuple[int, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["생산계획년월", "공정", "가용대수"])


# ------------------------------------------------------------------ 칸 값


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0.0),
        (pd.NA, 0.0),
        (math.nan, 0.0),
        ("", 0.0),
        ("  ", 0.0),
        (0, 0.0),
        (1.5, 1.5),
        ("1.25", 1.25),
        ("1,000", 1000.0),
        (2, 2.0),
        (0.3333333333, 0.333333),
    ],
)
def test_a_cell_reads_blank_as_zero_and_keeps_decimals(raw: object, expected: float) -> None:
    assert manual_cell_value(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [-0.1, "-1", math.inf, "abc", True, 10_000.0])
def test_a_cell_refuses_negative_infinite_text_bool_and_huge(raw: object) -> None:
    with pytest.raises(ValueError):
        manual_cell_value(raw, where="Wafer Mount 26.07")


def test_prepare_drops_zero_cells_and_sorts_by_process_and_month() -> None:
    rows = prepare_manual_downtime(
        {(B, 202608): "0.5", (A, 202607): 0, (A, 202608): 1.0, (" " + B + " ", 202607): 2}
    )
    # 공정 이름 차례(Final Test < Wafer Mount), 그 안은 달 차례다.
    assert rows == ((B, 202607, 2.0), (B, 202608, 0.5), (A, 202608, 1.0))


@pytest.mark.parametrize(
    "cells",
    [
        {("", 202607): 1.0},
        {(A, 202613): 1.0},
        {(A, "26.07"): 1.0},
        {(A, 202607): 1.0, (A + " ", 202607): 2.0},
    ],
)
def test_prepare_refuses_blank_process_bad_month_and_duplicates(
    cells: dict[tuple[object, object], object],
) -> None:
    with pytest.raises(ValueError):
        prepare_manual_downtime(cells)


# ------------------------------------------------------------------ 보이는 범위만 갈아 쓰기


def test_merge_replaces_only_the_visible_processes_and_months() -> None:
    current = ((A, 202606, 3.0), (A, 202607, 1.0), (B, 202607, 2.0), ("Other", 202607, 4.0))
    merged = merge_visible_cells(
        current,
        {(A, 202607): None, (A, 202608): "0.75", (B, 202607): 2.5, (B, 202608): ""},
        processes=(A, B),
        months=(202607, 202608),
    )
    # 조회기간 밖(202606)·보이지 않는 공정(Other)은 남고, 비운 칸은 빠진다.
    assert merged == (
        (B, 202607, 2.5),
        ("Other", 202607, 4.0),
        (A, 202606, 3.0),
        (A, 202608, 0.75),
    )
    assert changed_cell_count(current, merged) == 3


def test_merge_treats_a_visible_cell_missing_from_the_edit_as_cleared() -> None:
    merged = merge_visible_cells(((A, 202607, 1.0),), {}, processes=(A,), months=(202607,))
    assert merged == ()


# ------------------------------------------------------------------ 계산 키


def test_the_key_keeps_only_the_calculated_months_in_a_stable_order() -> None:
    rows = ((B, 202609, 1.0), (A, 202607, 2.0), (A, 202606, 5.0))
    assert manual_downtime_key(rows, (202607, 202608, 202609)) == (
        (B, 202609, 1.0),
        (A, 202607, 2.0),
    )
    assert manual_downtime_key((), (202607,)) == ()
    assert manual_rows_for_process(((A, 202608, 1.0), (B, 202607, 2.0), (A, 202607, 0.5)), A) == (
        (202607, 0.5),
        (202608, 1.0),
    )


def test_period_months_spans_the_year_end() -> None:
    assert period_months(202611, 202702) == (202611, 202612, 202701, 202702)
    assert period_months(202603, 202602) == ()


# ------------------------------------------------------------------ 가용에서 빼기


def test_no_rows_returns_the_same_frame_untouched() -> None:
    available = _available([(202607, A, 3.0)])
    adjusted, effect = apply_manual_downtime(available, ())
    assert adjusted is available
    assert effect.empty and list(effect.columns) == list(MANUAL_DOWNTIME_EFFECT_COLUMNS)


def test_input_is_subtracted_and_stops_at_zero_with_the_overdrawn_cell_flagged() -> None:
    available = _available([(202607, A, 3.0), (202608, A, 0.8), (202607, B, 2.0)])
    adjusted, effect = apply_manual_downtime(
        available, ((A, 202607, 1.25), (A, 202608, 1.5), (B, 202609, 1.0))
    )

    values = {
        (int(month), str(process)): float(value)
        for month, process, value in adjusted.itertuples(index=False)
    }
    assert values == {(202607, A): 1.75, (202608, A): 0.0, (202607, B): 2.0}
    # 가용 행이 없는 달(202609 B)은 뺄 것이 없어 반영 0 이고 넘침이다 — 행을 새로 만들지 않는다.
    assert len(adjusted) == 3
    assert effect.to_dict("records") == [
        {"공정": A, "생산계획년월": 202607, "입력대수": 1.25, "반영대수": 1.25, "초과": False},
        {"공정": A, "생산계획년월": 202608, "입력대수": 1.5, "반영대수": 0.8, "초과": True},
        {"공정": B, "생산계획년월": 202609, "입력대수": 1.0, "반영대수": 0.0, "초과": True},
    ]
    assert list(overdrawn_rows(effect)["생산계획년월"]) == [202608, 202609]
    # 원 프레임은 그대로다.
    assert available["가용대수"].tolist() == [3.0, 0.8, 2.0]


def test_clamp_is_exact_at_the_boundary() -> None:
    assert clamp_manual_units(2.0, 2.0) == (2.0, False)
    assert clamp_manual_units(2.0, 1.999999999999) == (2.0, False)
    assert clamp_manual_units(2.5, 2.0) == (2.0, True)
    assert clamp_manual_units(1.0, -0.5) == (0.0, True)


# ------------------------------------------------------------------ 글


def test_band_text_counts_cells_and_overdrawn_months() -> None:
    _, effect = apply_manual_downtime(
        _available([(202607, A, 3.0), (202608, A, 0.5)]), ((A, 202607, 1.0), (A, 202608, 1.5))
    )
    assert manual_effect_band(effect) == f"{MANUAL_DOWNTIME_BAND}(2칸 · 합 2.5대 · 가용 넘침 1칸)"
    assert manual_effect_band(effect, (B,)) == ""
    assert [manual_units_text(value) for value in (1.5, 2.0, 0.126, 0.0)] == [
        "1.5",
        "2",
        "0.13",
        "0",
    ]


def test_profile_cells_processes_and_source() -> None:
    profile = ManualDowntime(
        rows=((A, 202607, 1.0), (B, 202608, 2.0)), version=3, saved_by="홍길동", note="PM"
    )
    assert profile.cells == {(A, 202607): 1.0, (B, 202608): 2.0}
    assert profile.processes == (B, A)
    assert profile.source == "홍길동 · PM"
    assert ManualDowntime().source == ""
