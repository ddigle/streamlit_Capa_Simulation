# Purpose: 설비 마스터 글자 행렬을 바뀐 칸 · 줄만 갈아 끼워도 통째로 만든 것과 같은지 지킨다.

"""`equipment_grid.text_matrix_since` — 설비 마스터 표 칸 고치기마다 쓰는 화면 글자 행렬.

- **같은 글자** — 무작위 칸 고치기 · 줄 넣고 빼기 · 객체 칸 표에서 늘 `text_matrix` 와 같다.
- **다시 쓰는 범위** — 글자가 달라진 줄만 새 줄이고 나머지 줄은 앞 행렬의 줄 그대로다. 앞 행렬의
  줄 목록은 고치지 않는다(앞 회차 표 모양이 쥔 목록).
"""

from __future__ import annotations

import copy
import random
from datetime import date

import pandas as pd
import pytest

from capa_simulation.services import equipment_grid as eg
from capa_simulation.services.equipment_contract import (
    COORDINATE_COLUMNS,
    DATE_COLUMNS,
    EQUIPMENT_COLUMNS,
)
from capa_simulation.services.equipment_samples import sample_equipment_master

ANCHOR = date(2026, 10, 1)


def _value(column: str, rng: random.Random) -> object:
    if column in DATE_COLUMNS:
        return rng.choice([None, pd.Timestamp("2026-01-15"), pd.Timestamp("2027-03-01")])
    if column in COORDINATE_COLUMNS or column == "환산비":
        return rng.choice([None, 0.0, -0.0, 0.25, 12.5])
    return rng.choice([None, " a ", "b", "", "긴 메모"])


@pytest.mark.parametrize("seed", range(5))
def test_random_edits_give_the_whole_matrix(seed: int) -> None:
    rng = random.Random(seed)
    frame = sample_equipment_master(anchor_date=ANCHOR)
    matrix = eg.text_matrix_since(None, frame)
    assert matrix.rows == eg.text_matrix(frame)
    for _ in range(20):
        frame = frame.copy()
        if rng.random() < 0.15:
            frame = pd.concat([frame, frame.iloc[[rng.randrange(len(frame))]]], ignore_index=True)
        elif rng.random() < 0.1:
            frame = frame.drop(index=frame.index[rng.randrange(len(frame))]).reset_index(drop=True)
        else:
            for _ in range(rng.choice([1, 1, 2])):
                column = rng.choice(list(EQUIPMENT_COLUMNS))
                eg.store_cell(frame, rng.randrange(len(frame)), column, _value(column, rng))
        before = copy.deepcopy(matrix.rows)
        previous = matrix
        matrix = eg.text_matrix_since(previous, frame)
        assert matrix.rows == eg.text_matrix(frame)
        assert previous.rows == before


def test_only_rows_whose_text_changed_are_new_lists() -> None:
    frame = sample_equipment_master(anchor_date=ANCHOR)
    first = eg.text_matrix_since(None, frame)
    edited = frame.copy()
    eg.store_cell(edited, 4, "담당자", "홍길동")
    second = eg.text_matrix_since(first, edited)
    assert second.rows[4] is not first.rows[4]
    assert [index for index, row in enumerate(second.rows) if row is not first.rows[index]] == [4]
    # 바뀐 칸이 없으면 앞 행렬 그대로.
    assert eg.text_matrix_since(second, edited.copy()).rows is second.rows


def test_object_columns_are_rewritten_and_still_match() -> None:
    frame = sample_equipment_master(anchor_date=ANCHOR).astype(object)
    first = eg.text_matrix_since(None, frame)
    edited = frame.copy()
    edited.loc[2, "메모1"] = " 새 메모 "
    second = eg.text_matrix_since(first, edited)
    assert second.rows == eg.text_matrix(edited)
