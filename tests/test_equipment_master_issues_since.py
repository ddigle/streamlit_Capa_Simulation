# Purpose: 바뀐 칸만 다시 보는 설비 마스터 칸 결과가 처음부터 본 결과와 늘 같은지 지킨다.

"""`equipment_validation.equipment_master_issues_since` — 설비 마스터 표 칸 고치기의 칸 결과.

바뀐 칸만 다시 다듬고(칸 다듬기는 칸마다 그 칸의 입력만 본다), 보는 칸(`MasterRule.reads`)이 바뀐
규칙만 다시 본다. 지키는 것:

1. **칸 다듬기 한 길** — 칸마다 다듬는 `_read_column` 으로 짠 `_read_master` 가 고치기 전 길(이
   파일의 `_reference_read_master`)과 같은 한 벌을 낸다.
2. **보는 칸 그물** — 규칙마다, 그 규칙이 걸리는 표에서 적은 칸(+ 설비명)만 남긴 한 벌로 보아도 온
   표로 본 칸 결과와 같다. 적지 않은 칸을 읽으면 `KeyError` 이거나 결과가 달라 걸린다.
3. **같은 결과** — 무작위 칸 고치기를 이어 가며 매번 처음부터 본 `equipment_master_issues` 와 같고,
   막는 결과가 있다 ⇔ `prepare_equipment_master` 가 막는다.
"""

from __future__ import annotations

import random
from datetime import date

import numpy as np
import pandas as pd
import pytest

from capa_simulation.services import equipment_grid as eg
from capa_simulation.services import equipment_validation as ev
from capa_simulation.services.equipment_contract import (
    AREA_CODE_COLUMN,
    ARRIVAL_STATUS_COLUMN,
    CONVERSION_RATIO_COLUMN,
    COORDINATE_COLUMNS,
    DATE_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    FLAG_COLUMNS,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_STATUS_COLUMN,
    REFERENCE_TEXT_COLUMNS,
    normalize_area_code,
    with_optional_equipment_columns,
)
from capa_simulation.services.equipment_samples import sample_equipment_master

ANCHOR = date(2026, 10, 1)
CANVASES = {("C1", "1F"): (100.0, 60.0), ("C2", "2F"): (200.0, 120.0)}


def _reference_read_master(data: pd.DataFrame) -> ev._MasterFrame | None:
    """고치기 전 `_read_master` 몸통(칸 묶음마다 차례대로) — 칸 다듬기 한 길의 대조."""
    data = with_optional_equipment_columns(data)
    selected = data.loc[:, list(EQUIPMENT_COLUMNS)].reset_index(drop=True)
    raw = ev._drop_blank_rows(selected, (EQUIPMENT_ID_COLUMN,))
    if raw.empty:
        return None
    raw_dates = raw.loc[:, list(DATE_COLUMNS)]
    result = raw
    for column in (EQUIPMENT_ID_COLUMN, "공정소분류"):
        result[column] = result[column].astype("string").str.strip()
    for column in REFERENCE_TEXT_COLUMNS + ("동", "층"):
        result[column] = ev._optional_text(result[column])
    result[AREA_CODE_COLUMN] = normalize_area_code(result[AREA_CODE_COLUMN])
    for column in (QUAL_STATUS_COLUMN, ARRIVAL_STATUS_COLUMN, PARENT_EQUIPMENT_COLUMN):
        result[column] = ev._optional_text(result[column])
    for column in FLAG_COLUMNS:
        result[column] = ev._flag_text(result[column])
    unreadable: dict[str, pd.Series] = {}
    for column in COORDINATE_COLUMNS:
        result[column], unreadable[column] = ev._read_number(result[column])
    ratio, unreadable[CONVERSION_RATIO_COLUMN], not_positive = ev._read_ratio(
        result[CONVERSION_RATIO_COLUMN]
    )
    result[CONVERSION_RATIO_COLUMN] = ratio
    for column in DATE_COLUMNS:
        result[column], unreadable[column] = ev._read_master_dates(raw_dates[column])
    return ev._MasterFrame(raw_dates, result, unreadable, not_positive, None, None)


def _typed() -> pd.DataFrame:
    return sample_equipment_master(anchor_date=ANCHOR)


def _as_text(master: pd.DataFrame) -> pd.DataFrame:
    """같은 값의 객체 칸 표(붙여넣기 꼴) — 날짜는 글자."""
    text = master.astype(object)
    for column in master.columns:
        if pd.api.types.is_datetime64_any_dtype(master[column]):
            text[column] = master[column].dt.strftime("%Y-%m-%d").astype(object)
    text[master.isna()] = None
    return text


def _firing() -> pd.DataFrame:
    """규칙 표의 줄마다 걸리는 줄이 있는 객체 칸 표(날짜 · 수는 글자 — 못 읽는 값도 넣는다)."""
    frame = _as_text(_typed())
    frame["보관유무"] = "N"
    frame["기존설비여부"] = "N"
    names = frame[EQUIPMENT_ID_COLUMN].tolist()

    def put(row: int, **cells: str | None) -> None:
        for column, value in cells.items():
            frame.at[row, column] = value

    put(0, 공정소분류=None)
    put(2, 설비명=names[1])
    frame.loc[3, PARENT_EQUIPMENT_COLUMN] = names[4]
    frame.loc[5, PARENT_EQUIPMENT_COLUMN] = "GRP-1"
    frame.loc[6, PARENT_EQUIPMENT_COLUMN] = "GRP-1"
    put(5, 공정구분="A")
    put(6, 공정구분="B")
    frame.loc[7, PARENT_EQUIPMENT_COLUMN] = "GRP-2"
    frame.loc[8, PARENT_EQUIPMENT_COLUMN] = "GRP-2"
    put(7, Maker="m1")
    put(8, Maker="m2")
    put(9, 보관유무="X")
    put(10, X좌표="12m", Y좌표="1", Xsize="1", Ysize="1")
    put(11, 동="C9")
    put(12, X좌표="1", Y좌표=None)
    put(13, Xsize="1", Ysize=None)
    put(14, X좌표="1", Y좌표="1", Xsize=None, Ysize=None)
    put(15, 레이아웃표시="Y", X좌표="1", Y좌표="1", Xsize="1", Ysize="1", 동=None)
    put(16, X좌표="-1", Y좌표="1", Xsize="1", Ysize="1")
    put(17, X좌표="1", Y좌표="1", Xsize="0", Ysize="1")
    put(18, X좌표="1000", Y좌표="1", Xsize="5", Ysize="5", 동="C1", 층="1F")
    frame.loc[19, CONVERSION_RATIO_COLUMN] = "1,5"
    frame.loc[20, CONVERSION_RATIO_COLUMN] = "-1"
    put(21, 반입일정="내일")
    put(22, 반입일정="2026-11-05+09:00")
    put(23, Qual일정="2026-12-01", Qual상태=None)
    put(24, Qual상태="이상")
    put(25, 반입일정="2026-12-20", Qual일정="2026-12-01", Qual상태="계획")
    put(26, 반입일정=None, Qual일정=None, 정지일정="2026-12-01")
    put(27, 반입일정="2026-01-01", 정지일정="2026-12-05", **{"반출/이설일정": "2026-12-01"})
    put(28, 반입일정="2026-06-01", **{"반출/이설일정": "2026-05-01"})
    put(29, 반입실적="2099-01-01")
    put(30, 반입실적="2026-09-01", Qual실적="2026-08-01")
    frame.loc[31, AREA_CODE_COLUMN] = "XYZ"
    put(32, 설비명=str(names[33]).lower())
    frame.loc[34, PARENT_EQUIPMENT_COLUMN] = "GRP-3"
    frame.loc[35, PARENT_EQUIPMENT_COLUMN] = "GRP-3"
    frame.loc[34, CONVERSION_RATIO_COLUMN] = None
    frame.loc[35, CONVERSION_RATIO_COLUMN] = "1"
    return frame


def _restricted(master: ev._MasterFrame, reads: frozenset[str]) -> ev._MasterFrame:
    """적은 칸(+ 설비명)만 남긴 한 벌 — 적지 않은 칸을 읽으면 `KeyError` 다. 환산비를 적지 않은
    규칙의 0 이하 표지는 모두 참으로 바꿔 읽으면 결과가 달라지게 한다."""
    keep = [column for column in EQUIPMENT_COLUMNS if column in reads]
    return ev._MasterFrame(
        raw_dates=master.raw_dates.loc[:, [column for column in DATE_COLUMNS if column in reads]],
        data=master.data.loc[:, keep],
        unreadable={key: value for key, value in master.unreadable.items() if key in reads},
        ratio_not_positive=(
            master.ratio_not_positive
            if CONVERSION_RATIO_COLUMN in reads
            else pd.Series(True, index=master.data.index, dtype=bool)
        ),
        floor_canvases=master.floor_canvases,
        today=master.today,
    )


@pytest.mark.parametrize("make", [_typed, lambda: _as_text(_typed()), _firing])
def test_reading_column_by_column_is_the_old_read(make: object) -> None:
    frame = make()  # type: ignore[operator]
    new = ev._read_master(frame, floor_canvases=None, today=None)
    old = _reference_read_master(frame)
    assert new is not None and old is not None
    pd.testing.assert_frame_equal(new.data, old.data)
    pd.testing.assert_frame_equal(new.raw_dates, old.raw_dates)
    pd.testing.assert_series_equal(new.ratio_not_positive, old.ratio_not_positive)
    assert list(new.unreadable) == list(old.unreadable)
    for key, value in old.unreadable.items():
        pd.testing.assert_series_equal(new.unreadable[key], value, check_names=False)


def test_every_rule_fires_on_the_fixture_and_reads_only_its_declared_columns() -> None:
    master = ev._read_master(_firing(), floor_canvases=CANVASES, today=ANCHOR)
    assert master is not None
    for rule in ev.MASTER_RULES:
        assert rule.reads is not None, rule.code
        assert rule.reads <= set(EQUIPMENT_COLUMNS), rule.code
        full = ev._rule_found(master, rule)
        assert any(found for found in full), f"걸리는 줄이 없는 규칙: {rule.code}"
        assert ev._rule_found(_restricted(master, rule.reads), rule) == full, rule.code


def _edit_pool(column: str, rng: random.Random) -> object:
    """칸 꼴에 맞는 고칠 값 — 막는 값 · 빈 값 · 멀쩡한 값이 섞인다."""
    if column in DATE_COLUMNS:
        return rng.choice(
            [
                None,
                pd.Timestamp("2026-01-15"),
                pd.Timestamp("2027-03-01"),
                pd.Timestamp("2099-01-01"),
            ]
        )
    if column in COORDINATE_COLUMNS or column == CONVERSION_RATIO_COLUMN:
        return rng.choice([None, 0.0, -1.0, 0.25, 1.0, 12.5, 1000.0])
    if column in FLAG_COLUMNS:
        return rng.choice(["Y", "N", "y", "X", None])
    if column == EQUIPMENT_ID_COLUMN:
        return rng.choice(["NEW-1", "new-1", "DEMO-EQ01"])
    if column == PARENT_EQUIPMENT_COLUMN:
        return rng.choice([None, "GRP-A", "GRP-B"])
    if column in ("동", "층"):
        return rng.choice([None, "C1", "C9", "1F", "9F"])
    if column in (QUAL_STATUS_COLUMN, ARRIVAL_STATUS_COLUMN):
        return rng.choice([None, "계획", "확정", "이상"])
    return rng.choice([None, " a ", "b", "Main", "main", "XYZ", ""])


def _assert_same(
    previous: ev.MasterIssueState | None, frame: pd.DataFrame, **kwargs: object
) -> ev.MasterIssueState:
    issues, state = ev.equipment_master_issues_since(previous, frame, **kwargs)  # type: ignore[arg-type]
    assert issues == ev.equipment_master_issues(frame, **kwargs)  # type: ignore[arg-type]
    blocked = any(issue.blocking for issue in issues)
    try:
        ev.prepare_equipment_master(frame, **kwargs)  # type: ignore[arg-type]
    except ValueError:
        assert blocked
    else:
        assert not blocked
    return state


@pytest.mark.parametrize("seed", range(6))
def test_random_cell_edits_match_a_fresh_check(seed: int) -> None:
    rng = random.Random(seed)
    frame = _typed()
    kwargs: dict[str, object] = (
        {"floor_canvases": CANVASES, "today": ANCHOR} if seed % 2 else {"today": ANCHOR}
    )
    state = _assert_same(None, frame, **kwargs)
    columns = list(EQUIPMENT_COLUMNS)
    for _ in range(25):
        frame = frame.copy()
        for _ in range(rng.choice([1, 1, 1, 2, 3])):
            column = rng.choice(columns)
            eg.store_cell(frame, rng.randrange(len(frame)), column, _edit_pool(column, rng))
        state = _assert_same(state, frame, **kwargs)


@pytest.mark.parametrize("seed", range(3))
def test_random_text_edits_on_object_columns_match_a_fresh_check(seed: int) -> None:
    """객체 칸 표(붙여넣기 꼴)는 칸 견줌이 늘 「바뀜」 이라 칸마다 다시 읽는다 — 그래도 같다."""
    rng = random.Random(100 + seed)
    frame = _firing()
    kwargs: dict[str, object] = {"floor_canvases": CANVASES, "today": ANCHOR}
    state = _assert_same(None, frame, **kwargs)
    for _ in range(10):
        frame = frame.copy()
        column = rng.choice([column for column in EQUIPMENT_COLUMNS if column != "설비명"])
        frame.loc[rng.randrange(len(frame)), column] = rng.choice(
            ["", " x ", "2026-13-01", "2026/11/05", "12m", "-3", None, "Y"]
        )
        state = _assert_same(state, frame, **kwargs)


def test_rows_names_canvases_and_today_start_over() -> None:
    frame = _typed()
    state = _assert_same(None, frame, today=ANCHOR)
    # 줄을 넣고 뺌 · 설비명 · 캔버스 · 오늘이 바뀌면 처음부터 — 그래도 같은 결과.
    longer = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    _assert_same(state, longer, today=ANCHOR)
    renamed = frame.copy()
    eg.store_cell(renamed, 3, EQUIPMENT_ID_COLUMN, "  ")
    _assert_same(state, renamed, today=ANCHOR)
    _assert_same(state, frame, today=ANCHOR, floor_canvases=CANVASES)
    _assert_same(state, frame, today=date(2027, 1, 1))
    # 바뀐 것이 없으면 앞 재료를 그대로 돌려준다.
    issues, again = ev.equipment_master_issues_since(state, frame.copy(), today=ANCHOR)
    assert again is state and issues == state.issues


def test_unchanged_columns_are_compared_bit_for_bit() -> None:
    before = pd.Series([0.0, np.nan, 1.5])
    assert ev._same_column(before, before.copy())
    assert not ev._same_column(before, pd.Series([-0.0, np.nan, 1.5]))
    text = pd.Series(["a", None, "b"], dtype="string")
    assert ev._same_column(text, text.copy())
    assert not ev._same_column(text, pd.Series(["a", "b", "b"], dtype="string"))
    assert not ev._same_column(text, pd.Series([None, None, "b"], dtype="string"))
    objects = pd.Series(["a", None], dtype=object)
    assert not ev._same_column(objects, objects.copy())
