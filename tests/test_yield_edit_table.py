# Purpose: 수율 편집표가 값이 잘못된 원천 행을 빼고 적용 때 되붙이는지 고정한다.

"""수율 편집표의 원천 행 보존(2026-09-29 횡전개 감사).

RQ_YLD 한 행의 EDS·BE 가 비었거나 0 이면 `yield_to_edit_table` 이 표 전체를 거부하고 생산 계획
화면이 통째로 섰다. 그런 행은 표에서 빼고(`split_editable_yield_rows`) 적용 때 원본 그대로
되붙인다(`restore_locked_yield_rows`). 빈칸으로 실으면 적용의 `dropna` 가 원천 행을 지우고, 0 을
받아 주면 수율로 나누는 계산이 깨진다.
"""

import math

import pandas as pd
import pytest

from capa_simulation.services.load_calculator import (
    YIELD_KEYS,
    YIELD_LOCK_REASON_COLUMN,
    YIELD_REQUIRED_COLUMNS,
    restore_locked_yield_rows,
    split_editable_yield_rows,
    yield_from_edit_table,
    yield_to_edit_table,
)

MONTHS = (202601, 202602, 202603)


def _source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "생산계획년월": month,
                "제품정보": product,
                "Stack": "8H",
                "WF 구분": "Core",
                "EDS_수율": 0.9,
                "BE_수율": 0.95,
            }
            for product in ("DEMO_P1", "DEMO_P2")
            for month in MONTHS
        ]
    )


def _row(frame: pd.DataFrame, product: str, month: int) -> pd.DataFrame:
    return frame.loc[frame["제품정보"].eq(product) & frame["생산계획년월"].eq(month)]


def _broken_source() -> pd.DataFrame:
    """DEMO_P1 의 202602 는 BE 가 비고, 202603 은 EDS 가 0, DEMO_P2 의 202603 은 EDS 가 120%."""
    source = _source()
    p1 = source["제품정보"].eq("DEMO_P1")
    p2 = source["제품정보"].eq("DEMO_P2")
    source.loc[p1 & source["생산계획년월"].eq(202602), "BE_수율"] = float("nan")
    source.loc[p1 & source["생산계획년월"].eq(202603), "EDS_수율"] = 0.0
    source.loc[p2 & source["생산계획년월"].eq(202603), "EDS_수율"] = 1.2
    return source


def test_the_edit_table_used_to_reject_a_single_empty_or_zero_yield() -> None:
    """결함 재현: 값 하나 때문에 표 전체가 거부된다(화면이 이 오류로 통째로 섰다)."""
    with pytest.raises(ValueError):
        yield_to_edit_table(_broken_source())


def test_rows_with_missing_or_out_of_range_values_are_split_out_with_a_reason() -> None:
    editable, locked = split_editable_yield_rows(_broken_source())

    assert len(editable) == 3
    yield_to_edit_table(editable)  # 남은 행만으로는 표가 선다.
    reasons = {
        (row["제품정보"], row["생산계획년월"]): row[YIELD_LOCK_REASON_COLUMN]
        for _, row in locked.iterrows()
    }
    assert reasons == {
        ("DEMO_P1", 202602): "BE 값 없음",
        ("DEMO_P1", 202603): "EDS 0 이하",
        ("DEMO_P2", 202603): "EDS 100% 초과",
    }


def test_a_broken_link_key_still_stops_the_table() -> None:
    """연결 키 결측·중복은 값 하나의 문제가 아니라 표 구조의 문제라 가르지 않고 던진다."""
    missing_key = _source()
    missing_key.loc[0, "WF 구분"] = None
    with pytest.raises(ValueError, match="연결 키에 누락값"):
        split_editable_yield_rows(missing_key)

    duplicated = pd.concat([_source(), _source().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="중복"):
        split_editable_yield_rows(duplicated)


def test_an_unrelated_edit_keeps_every_locked_row_as_it_was() -> None:
    """뺀 행과 무관한 칸을 고쳐 적용해도 뺀 행은 원본 값 그대로 남고 행 수도 같다."""
    source = _broken_source()
    editable, locked = split_editable_yield_rows(source)
    grid = yield_to_edit_table(editable)
    grid.loc[grid["제품정보"].eq("DEMO_P2") & grid["수율 구분"].eq("EDS"), "202601"] = 0.5

    applied = restore_locked_yield_rows(yield_from_edit_table(grid), locked)

    assert len(applied) == len(source)
    assert not applied.duplicated(YIELD_KEYS).any()
    assert list(applied.columns) == YIELD_REQUIRED_COLUMNS
    assert math.isnan(_row(applied, "DEMO_P1", 202602)["BE_수율"].item())
    assert _row(applied, "DEMO_P1", 202603)["EDS_수율"].item() == 0.0
    assert _row(applied, "DEMO_P2", 202603)["EDS_수율"].item() == 1.2
    assert _row(applied, "DEMO_P2", 202601)["EDS_수율"].item() == 0.5


def test_filling_both_cells_of_a_locked_month_replaces_the_locked_row() -> None:
    """뺀 달의 빈칸에 EDS·BE 를 모두 넣으면 넣은 값이 이긴다 — 원본을 되붙여 키가 겹치면 안 된다."""
    editable, locked = split_editable_yield_rows(_broken_source())
    grid = yield_to_edit_table(editable)
    p2 = grid["제품정보"].eq("DEMO_P2")
    grid.loc[p2 & grid["수율 구분"].eq("EDS"), "202603"] = 0.8
    grid.loc[p2 & grid["수율 구분"].eq("BE"), "202603"] = 0.9

    applied = restore_locked_yield_rows(yield_from_edit_table(grid), locked)

    fixed = _row(applied, "DEMO_P2", 202603)
    assert len(fixed) == 1
    assert fixed[["EDS_수율", "BE_수율"]].iloc[0].tolist() == [0.8, 0.9]
    assert len(applied) == len(_source())


def test_nothing_to_restore_returns_the_edited_rows() -> None:
    editable, locked = split_editable_yield_rows(_source())
    assert locked.empty
    edited = yield_from_edit_table(yield_to_edit_table(editable))

    assert restore_locked_yield_rows(edited, locked) is edited


def test_a_space_only_yield_cell_reads_as_empty() -> None:
    """공백 한 칸(`' '`)은 빈칸과 같다 — 두 칸 다 비면 그 달 행이 빠진다.

    붙여넣기 검증은 `' '` 를 빈칸으로 통과시키는데 변환은 「숫자가 아닌 값」으로 표 전체를
    거부했고 어느 칸인지도 알리지 않았다(2026-09-29 횡전개 감사).
    """
    grid = yield_to_edit_table(_source()).astype({str(month): object for month in MONTHS})
    grid.loc[grid["제품정보"].eq("DEMO_P1"), "202602"] = " "

    applied = yield_from_edit_table(grid)

    assert len(applied) == len(_source()) - 1
    assert _row(applied, "DEMO_P1", 202602).empty
