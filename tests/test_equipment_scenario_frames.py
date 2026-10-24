# Purpose: 설비 시나리오 순수 함수(나누기·합치기·호기 키·일정 없음·함께 넣기 후보)를 검증한다.

"""`services/equipment_scenario.py` — DB 없이 프레임만으로 도는 규칙.

설비 마스터 39칸은 공통 32칸과 일정 일곱 칸으로 나뉘고 호기 키로 다시 합쳐진다. 나눈 것을 다시
합치면 원래 표와 한 칸도 다르지 않아야 한다(빈칸·모듈 행·NaT·모두 빈 날짜 칸 포함).
"""

from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from capa_simulation.services.equipment_contract import (
    COMMON_MASTER_COLUMNS,
    EQUIPMENT_COLUMNS,
    SCENARIO_MEMO_COLUMN,
    SCENARIO_SCHEDULE_COLUMNS,
)
from capa_simulation.services.equipment_scenario import (
    COMMON_FRAME_COLUMNS,
    SCHEDULE_DOWNTIME_COLUMNS,
    SCHEDULE_FRAME_COLUMNS,
    UNIT_KEY_COLUMN,
    assign_unit_keys,
    calculation_frames,
    legacy_unit_key,
    merge_equipment,
    new_downtime_rows,
    new_unit_keys,
    normalize_schedule_frame,
    select_schedule_rows,
    split_downtime,
    split_equipment,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_master,
)


def _unit(name: str, **values: object) -> dict[str, object]:
    row: dict[str, object] = {
        "설비명": name,
        "공정대분류": "B/N",
        "공정소분류": "Process-A",
        "공정구분": "PKG",
        "투자구분": "양산",
        "사용기준": "HBM",
        "반입일정": "2026-08-01",
        "Qual일정": "2026-08-10",
        "Qual상태": "확정",
        "보관유무": "N",
        "기존설비여부": "N",
        "레이아웃표시": "N",
    }
    row.update(values)
    return row


def _master() -> pd.DataFrame:
    """빈칸·모듈 행·NaT·한글 이름이 든 39칸 마스터. 제진대일정은 모든 행이 비었다."""
    rows = [
        _unit("EQ-01", Maker="KT", 물류일정="2026-07-20", **{SCENARIO_MEMO_COLUMN: "셋업 메모"}),
        _unit("설비가", 반입일정=None, Qual일정=None, Qual상태=None),
        _unit("APW01A", **{"Main 설비": "APW01", "환산비": 0.25}),
        _unit("APW01B", **{"Main 설비": "APW01", "환산비": 0.25, "메모1": "모듈"}),
        _unit("기존01", 반입일정=None, Qual일정=None, Qual상태=None, 기존설비여부="Y"),
        _unit("보관01", 보관유무="Y", 정지일정="2026-12-01"),
    ]
    master = prepare_equipment_master(pd.DataFrame(rows).reindex(columns=list(EQUIPMENT_COLUMNS)))
    assert master["제진대일정"].isna().all()
    return master


def _downtime(*rows: tuple[str, str, str]) -> pd.DataFrame:
    return prepare_downtime_schedule(
        pd.DataFrame(
            [
                {
                    "설비명": name,
                    "비가동유형": kind,
                    "시작일": start,
                    "종료일": None,
                    "상세사유": None,
                    "비고": None,
                }
                for name, kind, start in rows
            ],
            columns=["설비명", "비가동유형", "시작일", "종료일", "상세사유", "비고"],
        )
    )


def _keys(master: pd.DataFrame) -> dict[str, str]:
    return {str(name): legacy_unit_key(str(name)) for name in master["설비명"]}


def _counter() -> Iterator[str]:
    number = 0
    while True:
        number += 1
        yield f"new-{number}"


# ------------------------------------------------------------------------------- 칸 나눔


def test_the_contract_splits_into_32_common_and_7_scenario_columns() -> None:
    assert len(EQUIPMENT_COLUMNS) == 39
    assert (
        EQUIPMENT_COLUMNS.index(SCENARIO_MEMO_COLUMN)
        == EQUIPMENT_COLUMNS.index("반출/이설일정") + 1
    )
    assert SCENARIO_SCHEDULE_COLUMNS == (
        "제진대일정",
        "물류일정",
        "반입일정",
        "Qual일정",
        "정지일정",
        "반출/이설일정",
        SCENARIO_MEMO_COLUMN,
    )
    assert len(COMMON_MASTER_COLUMNS) == 32
    assert set(COMMON_MASTER_COLUMNS) | set(SCENARIO_SCHEDULE_COLUMNS) == set(EQUIPMENT_COLUMNS)
    assert not set(COMMON_MASTER_COLUMNS) & set(SCENARIO_SCHEDULE_COLUMNS)
    # 실적·상태는 시나리오가 나뉘어도 같은 사실이라 공통이다.
    assert {"반입실적", "Qual실적", "반입상태", "Qual상태"} <= set(COMMON_MASTER_COLUMNS)
    assert COMMON_FRAME_COLUMNS[-1] == SCHEDULE_FRAME_COLUMNS[0] == UNIT_KEY_COLUMN


def test_the_legacy_key_is_the_same_value_as_the_sql_md5() -> None:
    names = ["EQ-01", "설비가", "APW01A", "모듈 01 ", "Ω-1"]
    sql: list[str] = []
    with duckdb.connect(":memory:") as connection:
        for name in names:
            row = connection.execute("SELECT 'n' || md5(?)", [name]).fetchone()
            assert row is not None
            sql.append(str(row[0]))

    assert [legacy_unit_key(name) for name in names] == sql
    assert all(len(key) == 33 and key.startswith("n") for key in sql)


def test_merge_of_split_gives_the_same_frame_back() -> None:
    master = _master()
    downtime = _downtime(("EQ-01", "고장", "2026-09-01"), ("APW01B", "공사", "2026-09-05"))
    keys = _keys(master)

    common, schedule = split_equipment(master, keys)
    events = split_downtime(downtime, keys)
    merged = merge_equipment(common, schedule, events)

    assert common.columns.tolist() == list(COMMON_FRAME_COLUMNS)
    assert schedule.columns.tolist() == list(SCHEDULE_FRAME_COLUMNS)
    assert events.columns.tolist() == list(SCHEDULE_DOWNTIME_COLUMNS)
    assert_frame_equal(merged.equipment, master)
    assert_frame_equal(merged.downtime, downtime)
    assert merged.unscheduled_units == frozenset()
    assert merged.orphan_rows == 0
    assert merged.unit_key_pairs == tuple(keys.items())


def test_an_all_null_schedule_read_from_the_database_is_typed_before_merging() -> None:
    """DB 에서 읽은 날짜 칸이 모두 NULL 이면 객체 칸일 수 있다 — 합친 마스터의 칸은 날짜형이다."""
    master = _master()
    keys = _keys(master)
    common, schedule = split_equipment(master, keys)
    # DB 가 돌려줄 수 있는 꼴 — 날짜는 파이썬 date·None 이 섞인 객체 칸, 모두 빈 칸은 None 뿐.
    loose = schedule.astype(object)
    for column in ("물류일정", "반입일정", "Qual일정", "정지일정", "반출/이설일정"):
        loose[column] = [None if pd.isna(value) else value.date() for value in schedule[column]]
    loose["제진대일정"] = None
    loose[SCENARIO_MEMO_COLUMN] = [
        None if pd.isna(v) else str(v) for v in schedule[SCENARIO_MEMO_COLUMN]
    ]

    typed = normalize_schedule_frame(loose)
    merged = merge_equipment(common, loose, split_downtime(_downtime(), keys))

    assert pd.api.types.is_datetime64_any_dtype(typed["제진대일정"])
    assert isinstance(typed[SCENARIO_MEMO_COLUMN].dtype, pd.StringDtype)
    assert pd.api.types.is_datetime64_any_dtype(merged.equipment["제진대일정"])
    assert_frame_equal(prepare_equipment_master(merged.equipment), prepare_equipment_master(master))


def test_units_without_a_schedule_row_have_blank_schedule_cells_and_are_listed() -> None:
    master = _master()
    keys = _keys(master)
    common, schedule = split_equipment(master, keys)
    without = schedule.loc[~schedule[UNIT_KEY_COLUMN].isin([keys["기존01"], keys["보관01"]])]

    merged = merge_equipment(common, without, split_downtime(_downtime(), keys))
    rows = merged.equipment.set_index("설비명")

    assert merged.unscheduled_units == frozenset({"기존01", "보관01"})
    assert rows.loc[["기존01", "보관01"], list(SCENARIO_SCHEDULE_COLUMNS)].isna().all().all()
    # 공통 칸은 그대로다 — 일정 없음은 이 시나리오에 일정이 없을 뿐 호기가 사라진 것이 아니다.
    assert rows.loc["보관01", "보관유무"] == "Y"
    assert merged.equipment["설비명"].tolist() == master["설비명"].tolist()


def test_rows_pointing_at_keys_missing_from_the_common_ledger_are_dropped_and_counted() -> None:
    master = _master()
    keys = _keys(master)
    common, schedule = split_equipment(master, keys)
    stray_schedule = pd.concat(
        [schedule, schedule.iloc[[0]].assign(**{UNIT_KEY_COLUMN: "gone"})], ignore_index=True
    )
    events = split_downtime(_downtime(("EQ-01", "고장", "2026-09-01")), keys)
    stray_events = pd.concat(
        [
            events,
            events.assign(**{UNIT_KEY_COLUMN: "gone"}),
            events.assign(**{UNIT_KEY_COLUMN: "x"}),
        ],
        ignore_index=True,
    )

    merged = merge_equipment(common, stray_schedule, stray_events)

    assert merged.orphan_rows == 3
    assert merged.downtime["설비명"].tolist() == ["EQ-01"]
    assert_frame_equal(merged.equipment, master)


def test_downtime_follows_the_unit_key_to_the_current_common_name() -> None:
    """Space 편집기에서 이름을 바꾼 호기 — 키는 그대로라 비가동이 새 이름에 붙는다."""
    master = _master()
    keys = _keys(master)
    _, schedule = split_equipment(master, keys)
    events = split_downtime(_downtime(("EQ-01", "고장", "2026-09-01")), keys)
    renamed = master.assign(설비명=master["설비명"].replace({"EQ-01": "EQ-01R"}))
    renamed_keys = {**{n: k for n, k in keys.items() if n != "EQ-01"}, "EQ-01R": keys["EQ-01"]}
    common, _ = split_equipment(renamed, renamed_keys)

    merged = merge_equipment(common, schedule, events)

    assert merged.downtime["설비명"].tolist() == ["EQ-01R"]
    assert merged.equipment.loc[0, "물류일정"] == pd.Timestamp("2026-07-20")


def test_duplicate_or_blank_common_keys_are_refused() -> None:
    master = _master()
    keys = _keys(master)
    common, schedule = split_equipment(master, keys)
    doubled = common.assign(**{UNIT_KEY_COLUMN: "same"})

    with pytest.raises(ValueError, match="호기 키"):
        merge_equipment(doubled, schedule, split_downtime(_downtime(), keys))
    with pytest.raises(KeyError, match="호기 키가 없는 설비명"):
        split_equipment(master, {"EQ-01": "k"})


# ------------------------------------------------------------------------------- 호기 키


def test_keys_are_inherited_by_name_and_new_units_get_new_keys() -> None:
    base = {"EQ-01": "k1", "EQ-02": "k2"}
    fresh = _counter()

    keys = assign_unit_keys(["EQ-01", "EQ-02", "EQ-03"], base, {}, new_key=lambda: next(fresh))

    assert keys == {"EQ-01": "k1", "EQ-02": "k2", "EQ-03": "new-1"}


def test_a_renamed_unit_keeps_its_key_and_a_new_unit_with_the_old_name_gets_a_new_one() -> None:
    """「A→B 이름 바꿈 + 새 A」 — B 가 A 의 키를 잇고 새 A 는 새 키다(검토 1-9)."""
    base = {"A": "kA", "C": "kC"}
    fresh = _counter()

    keys = assign_unit_keys(["B", "A", "C"], base, {"B": "A"}, new_key=lambda: next(fresh))

    assert keys == {"B": "kA", "A": "new-1", "C": "kC"}


def test_a_name_typed_over_in_raw_data_is_a_new_unit() -> None:
    """RawData 에서 설비명을 고치면 이름 지도가 없다 — 지운 호기 + 새 호기(질문 4)."""
    fresh = _counter()

    keys = assign_unit_keys(["EQ-01X"], {"EQ-01": "k1"}, {}, new_key=lambda: next(fresh))

    assert keys == {"EQ-01X": "new-1"}


def test_two_units_inheriting_one_saved_name_are_refused() -> None:
    with pytest.raises(ValueError, match="한 호기를 둘 이상의 설비명이"):
        assign_unit_keys(["B", "C"], {"A": "kA"}, {"B": "A", "C": "A"})
    with pytest.raises(ValueError, match="설비명이 겹쳐"):
        assign_unit_keys(["A", "A"], {"A": "kA"}, {})


def test_new_keys_are_distinct_uuids() -> None:
    keys = assign_unit_keys(["X", "Y"], {}, {})

    assert len(set(keys.values())) == 2
    assert all(len(key) == 32 for key in keys.values())


# ----------------------------------------------------------------- 일정 없음·계산 프레임


def test_calculation_frames_drop_unscheduled_units_and_their_downtime() -> None:
    """기존설비 Y·보관 Y 도 일정 행이 없으면 뺀다 — 반입일정 없이도 보유로 세는 호기다(질문 2)."""
    master = _master()
    downtime = _downtime(("기존01", "공사", "2026-09-01"), ("EQ-01", "고장", "2026-09-02"))
    baseline = pd.DataFrame({"공정": ["Process-A"], "분류": ["전체"], "기존보유대수": [2.0]})

    kept_baseline, equipment, events = calculation_frames(
        baseline, master, downtime, frozenset({"기존01", "보관01"})
    )

    assert kept_baseline is baseline
    assert "기존01" not in equipment["설비명"].tolist()
    assert "보관01" not in equipment["설비명"].tolist()
    assert len(equipment) == len(master) - 2
    assert events["설비명"].tolist() == ["EQ-01"]
    assert equipment.index.tolist() == list(range(len(equipment)))


def test_calculation_frames_are_the_same_objects_when_every_unit_is_scheduled() -> None:
    master = _master()
    downtime = _downtime()
    baseline = pd.DataFrame()

    kept_baseline, equipment, events = calculation_frames(baseline, master, downtime, frozenset())

    assert kept_baseline is baseline
    assert equipment is master
    assert events is downtime


# ------------------------------------------------------------- 쓸 일정 행·함께 넣기 후보


def test_rows_written_are_previously_scheduled_valued_with_downtime_or_new() -> None:
    blank = {column: None for column in SCENARIO_SCHEDULE_COLUMNS}
    schedule = pd.DataFrame(
        [
            {UNIT_KEY_COLUMN: "had-row", **blank},
            {UNIT_KEY_COLUMN: "valued", **blank, "반입일정": pd.Timestamp("2026-08-01")},
            {UNIT_KEY_COLUMN: "memo-only", **blank, SCENARIO_MEMO_COLUMN: "메모"},
            {UNIT_KEY_COLUMN: "with-downtime", **blank},
            {UNIT_KEY_COLUMN: "new", **blank},
            {UNIT_KEY_COLUMN: "blank-unscheduled", **blank},
        ]
    )

    chosen = select_schedule_rows(
        schedule,
        previously_scheduled={"had-row"},
        downtime_keys={"with-downtime"},
        new_keys={"new"},
    )

    assert chosen[UNIT_KEY_COLUMN].tolist() == [
        "had-row",
        "valued",
        "memo-only",
        "with-downtime",
        "new",
    ]


def test_new_units_are_keys_missing_from_the_saved_common_ledger() -> None:
    assert new_unit_keys(["k1", "k2", "n3"], {"k1", "k2"}) == frozenset({"n3"})
    assert new_unit_keys([], {"k1"}) == frozenset()


def _events(*rows: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                UNIT_KEY_COLUMN: key,
                "비가동유형": kind,
                "시작일": pd.Timestamp(start),
                "종료일": pd.NaT,
                "상세사유": None,
                "비고": None,
            }
            for key, kind, start in rows
        ],
        columns=list(SCHEDULE_DOWNTIME_COLUMNS),
    )


def _identities(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
    return [
        (str(key), str(kind), f"{pd.Timestamp(start):%Y-%m-%d}")
        for key, kind, start in zip(
            frame[UNIT_KEY_COLUMN], frame["비가동유형"], frame["시작일"], strict=True
        )
    ]


def test_an_added_downtime_with_nothing_removed_in_its_group_is_new() -> None:
    base = _events(("k1", "공사", "2026-09-01"))
    edited = _events(
        ("k1", "공사", "2026-09-01"), ("k1", "공사", "2026-10-01"), ("k2", "고장", "2026-09-05")
    )

    assert _identities(new_downtime_rows(base, edited)) == [
        ("k1", "공사", "2026-10-01"),
        ("k2", "고장", "2026-09-05"),
    ]


def test_a_downtime_whose_start_date_was_corrected_is_not_new() -> None:
    """시작일만 고친 행 — 같은 (호기, 유형) 묶음에서 행이 사라졌으니 고침이다(검토 1-8)."""
    base = _events(("k1", "공사", "2026-09-01"))
    edited = _events(("k1", "공사", "2026-09-03"))

    assert new_downtime_rows(base, edited).empty


def test_a_downtime_whose_type_was_corrected_is_not_new() -> None:
    """유형만 고친 행 — 같은 (호기, 시작일) 의 행이 다른 유형으로 사라졌으니 고침이다(검토 2-5)."""
    base = _events(("k1", "공사", "2026-09-01"))
    edited = _events(("k1", "고장", "2026-09-01"))

    assert new_downtime_rows(base, edited).empty


def test_end_date_or_detail_edits_and_new_unit_downtime_are_not_new_downtime() -> None:
    base = _events(("k1", "공사", "2026-09-01"))
    edited = _events(("k1", "공사", "2026-09-01"), ("new-unit", "공사", "2026-09-01"))
    edited.loc[0, "종료일"] = pd.Timestamp("2026-09-09")

    assert new_downtime_rows(base, edited, exclude_keys={"new-unit"}).empty
    assert _identities(new_downtime_rows(base, edited)) == [("new-unit", "공사", "2026-09-01")]


def test_downtime_dates_compare_by_day_whatever_the_datetime_unit() -> None:
    """저장본(DB 읽기 — us)과 편집본(ns)의 날짜 단위가 달라도 같은 날은 같은 비가동이다."""
    base = _events(("k1", "공사", "2026-09-01"))
    base["시작일"] = base["시작일"].astype("datetime64[us]")
    edited = _events(("k1", "공사", "2026-09-01"))

    assert new_downtime_rows(base, edited).empty
