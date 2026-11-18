# Purpose: 설비 마스터 정규화 칸 지름길 · 묶음 갈림 좁히기가 일반 길과 같은 값을 내는지 지킨다.

"""설비 마스터 칸 다듬기(`equipment_validation._read_master`)의 칸 단위 지름길.

편집본 · 저장본은 날짜 · 실수 · 글자 칸이 이미 그 dtype 이라 일반 길(글자로 바꿔 빈 값을 가르고
pandas 로 다시 읽기)을 건너뛴다. 지름길은 **일반 길과 같은 값 · 같은 dtype** 이어야 한다 — 칸 결과 ·
저장 거부 · 다듬은 저장본이 모두 이 값을 본다. 모듈 묶음 칸 갈림은 두 줄 이상인 묶음만 묶는다 —
고치기 전 길(이 파일의 `_reference_mixed`)과 같은 찾은 것을 낸다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from datetime import date
from functools import partial

import numpy as np
import pandas as pd
import pytest

from capa_simulation.services import equipment_validation as ev
from capa_simulation.services.equipment_contract import (
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    UNIT_CONSISTENT_COLUMNS,
    UNIT_SAVE_CONSISTENT_COLUMNS,
)
from capa_simulation.services.equipment_samples import sample_equipment_master

ANCHOR = date(2026, 10, 1)


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_a_date_column_reads_like_the_general_path(unit: str) -> None:
    values = pd.to_datetime(
        pd.Series(["2026-01-01 13:45:00", None, "2026-02-03 00:00:00", "1999-12-31 23:59:59"])
    ).astype(np.dtype(f"datetime64[{unit}]"))
    series = pd.Series(values.to_numpy(), index=[3, 1, 7, 9], name="반입일정")
    fast = ev._read_date(series)
    general = ev._read_date_values(series)
    pd.testing.assert_series_equal(fast[0], general[0], check_names=False)
    assert fast[0].dtype == general[0].dtype == np.dtype(f"datetime64[{unit}]")
    assert fast[1].tolist() == general[1].tolist()
    assert list(fast[1].index) == list(general[1].index)
    assert fast[2] == general[2]


def test_a_float_column_reads_like_the_general_path() -> None:
    series = pd.Series([1.5, np.nan, 0.0, -0.0, -3.0, np.inf], index=[5, 4, 3, 2, 1, 0])
    for fast, general in (
        (ev._read_number(series), ev._read_number_values(series)),
        ((ev._blank_numbers(series),), (ev._blank_number_values(series),)),
    ):
        for left, right in zip(fast, general, strict=True):
            pd.testing.assert_series_equal(left, right, check_names=False)
    ratio, unreadable, not_positive = ev._read_ratio(series)
    assert ratio.tolist()[1] == 1.0
    assert not unreadable.any()
    assert not_positive.tolist() == [False, False, True, True, True, False]


def test_a_string_column_reads_like_the_general_path() -> None:
    series = pd.Series([" a ", "", None, "b", "  "], dtype="string", index=[2, 0, 1, 4, 3])
    expected = series.astype("string").str.strip()
    expected = expected.mask(expected.eq(""))
    pd.testing.assert_series_equal(ev._optional_text(series), expected)


def _master() -> pd.DataFrame:
    return sample_equipment_master(anchor_date=ANCHOR)


def _as_text(master: pd.DataFrame) -> pd.DataFrame:
    """같은 값의 객체 · 글자 칸 표(붙여넣기 꼴) — 일반 길을 지난다."""
    text = master.astype(object)
    for column in master.columns:
        if pd.api.types.is_datetime64_any_dtype(master[column]):
            text[column] = master[column].dt.strftime("%Y-%m-%d").astype(object)
    text = text.astype(object)
    text[master.isna()] = None
    return text


def test_typed_and_text_masters_give_the_same_cells_and_the_same_saved_frame() -> None:
    master = _master()
    master.loc[2, "X좌표"] = -1.0
    master.loc[4, "보관유무"] = "y"
    master.loc[5, "Qual일정"] = pd.Timestamp("2020-01-01")
    for kwargs in (
        {},
        {"today": ANCHOR},
        {"today": ANCHOR, "floor_canvases": {("C1", "1F"): (50.0, 50.0)}},
    ):
        typed = ev.equipment_master_issues(master, **kwargs)
        text = ev.equipment_master_issues(_as_text(master), **kwargs)
        assert typed == text
        assert typed


def _reference_mixed(
    master: ev._MasterFrame,
    columns: Sequence[str],
    message: Callable[[str], str],
    error: Callable[[str, str, Sequence[object]], ValueError],
) -> Iterator[ev._Finding]:
    """고치기 전 `_mixed_findings` — 모든 줄을 묶음 열쇠로 묶는다."""
    result = master.data
    parents = result[PARENT_EQUIPMENT_COLUMN]
    named = parents.notna()
    if not named.any():
        return
    keys = parents.where(named, result[EQUIPMENT_ID_COLUMN])
    for column in columns:
        values = result[column].astype("string").fillna("")
        mixed = values.groupby(keys).nunique().gt(1)
        groups = mixed.loc[mixed].index
        head = message(column)
        yield ev._hit(
            keys.isin(groups),
            head,
            column,
            error=partial(error, head, column, groups.tolist()),
        )


def test_mixed_groups_are_the_same_with_duplicate_plain_units_beside_a_module_group() -> None:
    master = _master().iloc[:6].copy()
    names = ["M1A", "M1B", "M1C", "D1", "D1", "S1"]
    master[EQUIPMENT_ID_COLUMN] = names
    master[PARENT_EQUIPMENT_COLUMN] = ["M1", "M1", "M1", None, None, None]
    master["공정구분"] = ["A", "B", "A", "X", "Y", "Z"]
    master["Maker"] = ["m", "m", "n", "p", "p", "q"]
    master["동"] = ["C1", "C1", "C1", "C2", "C3", "C1"]
    read = ev._read_master(master, floor_canvases=None, today=ANCHOR)
    assert read is not None
    for columns, message, error in (
        (UNIT_CONSISTENT_COLUMNS, ev._unit_group_mixed_message, ev._listed_groups),
        (UNIT_SAVE_CONSISTENT_COLUMNS, ev._unit_group_saved_message, ev.UnitGroupSplitError),
    ):
        new = list(ev._mixed_findings(read, columns, message, error))
        old = list(_reference_mixed(read, columns, message, error))
        assert len(new) == len(old)
        for left, right in zip(new, old, strict=True):
            assert left.rows.tolist() == right.rows.tolist()
            assert left.head == right.head and left.column == right.column
            assert left.error is not None and right.error is not None
            assert str(left.error()) == str(right.error())
    issues = ev.equipment_master_issues(master, today=ANCHOR)
    mixed = {(issue.unit, issue.column) for issue in issues if issue.rule == "unit_group_mixed"}
    assert ("D1", "공정구분") in mixed and ("M1A", "공정구분") in mixed
    assert ("S1", "공정구분") not in mixed
