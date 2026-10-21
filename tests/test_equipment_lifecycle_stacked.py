# Purpose: 생애주기 구간의 쌓은 한 번 판정이 날마다 전 호기를 판정하던 길과 같은 표를 내는지 본다.

"""쌓은 판정 = 날마다 판정.

`build_equipment_lifecycle_spans` 는 조회 시작일의 모든 호기와, 그 뒤 날마다 일정·비가동
경계가 걸린 설비키 묶음의 호기만 쌓아 상태 판정을 한 번 부른다. 아래 기준 구현은 바뀔 수 있는
날마다 시점 하나로 전 호기를 판정하던 길을 그대로 옮긴 것이다 — 두 길이 같은 표를 내야 한다.

입력은 고정 시드의 합성 설비 무리다. Main 설비 묶음(형제마다 다른 반입·Qual·정지·반출/이설),
보관·기존설비, 같은 날 두 번 바뀌는 호기, 겹치거나 종료일 없는 비가동, 한 설비의 여러 비가동
유형, 조회 범위 앞뒤의 일정을 섞는다.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    _TIMELINE_EVENT_COLUMNS,
    LIFECYCLE_SPAN_COLUMNS,
    _build_equipment_status_from_prepared,
    _exit_days_by_key,
    _lifecycle_breakpoints,
    build_equipment_lifecycle_spans,
)
from capa_simulation.services.equipment_contract import (
    COUNT_CATEGORY_COLUMN,
    COUNTED_COLUMN,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    EXIT_FOLLOWS_COLUMN,
    EXIT_STARTS_COLUMN,
    counts_for_capacity,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)
from capa_simulation.services.equipment_units import (
    UNIT_COUNT_DECIMALS,
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
    unit_keys,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_master,
)

_ANCHOR = date(2026, 6, 1)
_PROCESSES = ("SAW", "MOLD", "BOND")
_DOWNTIME_KINDS = ("PM", "고장", "개조")

# (시작일, 종료일). 여러 달 · 시작일이 일정일(EDGE-A 반입·Qual)인 석 달 · 하루짜리.
_WINDOWS = (
    (date(2025, 10, 1), date(2027, 3, 31)),
    (date(2026, 3, 1), date(2026, 5, 31)),
    (date(2026, 6, 5), date(2026, 6, 5)),
)


def _day(offset: int) -> date:
    return _ANCHOR + timedelta(days=offset)


def _equipment_row(name: str, process: str, **values: object) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(EQUIPMENT_COLUMNS, None)
    row.update(
        {
            "설비명": name,
            "공정대분류": "조립",
            "공정소분류": process,
            "Qual상태": "계획",
            "사용기준": "HBM",
            "보관유무": "N",
            "기존설비여부": "N",
            "레이아웃표시": "N",
        }
    )
    row.update(values)
    return row


def _downtime_row(name: str, kind: str, start: date, end: date | None) -> dict[str, object]:
    return {
        "설비명": name,
        "비가동유형": kind,
        "시작일": start,
        "종료일": end,
        "상세사유": None,
        "비고": None,
    }


def _edge_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """시드와 상관없이 늘 넣는 경계: 같은 날 반입·Qual, 같은 날 정지·반출/이설, 입고 전에 걸친
    비가동, 겹치는 두 유형(하나는 종료일 없음)."""
    equipment = [
        _equipment_row(
            "EDGE-A",
            "SAW",
            **{
                "Main 설비": "EDGE",
                "반입일정": date(2026, 3, 1),
                "Qual일정": date(2026, 3, 1),
                "정지일정": date(2026, 9, 1),
                "반출/이설일정": date(2026, 9, 1),
            },
        ),
        _equipment_row(
            "EDGE-B",
            "SAW",
            **{"Main 설비": "EDGE", "반입일정": date(2026, 5, 10), "Qual일정": date(2026, 6, 1)},
        ),
    ]
    downtime = [
        _downtime_row("EDGE-A", "PM", date(2026, 2, 20), date(2026, 3, 5)),
        _downtime_row("EDGE-B", "고장", date(2026, 6, 5), None),
        _downtime_row("EDGE-B", "PM", date(2026, 6, 1), date(2026, 6, 10)),
        _downtime_row("EDGE-B", "PM", date(2026, 6, 3), date(2026, 6, 4)),
    ]
    return equipment, downtime


def _fleet(seed: int, groups: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    equipment, downtime = _edge_rows()
    for group in range(groups):
        size = rng.choice((1, 1, 2, 3, 4))
        process = rng.choice(_PROCESSES)
        parent = f"M{group:02d}" if size > 1 else None
        for module in range(size):
            name = f"{parent}-{module}" if parent else f"U{group:02d}"
            kind = rng.choice(("new", "new", "new", "existing", "storage"))
            values: dict[str, object] = {
                "Main 설비": parent,
                "보관유무": "Y" if kind == "storage" else "N",
                "기존설비여부": "Y" if kind == "existing" else "N",
                "사용기준": rng.choice(("HBM", "HBM", "EDP", "범용")),
            }
            arrival: int | None = None
            if rng.random() < (0.9 if kind == "new" else 0.5):
                arrival = rng.randint(-400, 400)
                values["반입일정"] = _day(arrival)
                if rng.random() < 0.85:
                    values["Qual일정"] = _day(arrival + rng.choice((0, 1, rng.randint(2, 60))))
            # 들어온 적 없는 신규 호기는 내보낼 수 없다(검증 규칙).
            if kind != "new" or arrival is not None:
                base = arrival if arrival is not None else -400
                stop: int | None = None
                if rng.random() < 0.35:
                    stop = base + rng.randint(0, 500)
                    values["정지일정"] = _day(stop)
                if rng.random() < 0.35:
                    after = stop if stop is not None else base
                    values["반출/이설일정"] = _day(after + rng.choice((0, rng.randint(1, 200))))
            equipment.append(_equipment_row(name, process, **values))
            if rng.random() < 0.45:
                taken: set[tuple[str, date]] = set()
                for _ in range(rng.randint(1, 3)):
                    kind_name = rng.choice(_DOWNTIME_KINDS)
                    start = _day(rng.randint(-450, 450))
                    if (kind_name, start) in taken:
                        continue
                    taken.add((kind_name, start))
                    end = None if rng.random() < 0.2 else start + timedelta(rng.randint(0, 40))
                    downtime.append(_downtime_row(name, kind_name, start, end))
    return (
        pd.DataFrame(equipment, columns=list(EQUIPMENT_COLUMNS)),
        pd.DataFrame(downtime, columns=list(DOWNTIME_COLUMNS)),
    )


# ------------------------------------------------------------------ 날마다 판정하던 길(그대로 옮김)


def _reference_breakpoints(
    prepared: pd.DataFrame,
    prepared_downtime: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[pd.Timestamp]:
    moments: set[pd.Timestamp] = {start}
    for column in _TIMELINE_EVENT_COLUMNS:
        moments.update(pd.to_datetime(prepared[column].dropna()).tolist())
    if not prepared_downtime.empty:
        moments.update(pd.to_datetime(prepared_downtime["시작일"].dropna()).tolist())
        finished = pd.to_datetime(prepared_downtime["종료일"].dropna())
        moments.update((finished + pd.Timedelta(days=1)).tolist())
    return sorted(moment for moment in moments if start <= moment <= end)


def _reference_spans(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    with_unit_share: bool,
) -> pd.DataFrame:
    columns = [
        *LIFECYCLE_SPAN_COLUMNS,
        *(
            (
                UNIT_SHARE_COLUMN,
                UNIT_KEY_COLUMN,
                COUNT_CATEGORY_COLUMN,
                COUNTED_COLUMN,
                EXIT_STARTS_COLUMN,
                EXIT_FOLLOWS_COLUMN,
            )
            if with_unit_share
            else ()
        ),
    ]
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    breakpoints = _reference_breakpoints(prepared, prepared_downtime, start=start, end=end)
    process_by_unit = prepared.set_index(EQUIPMENT_ID_COLUMN)[["공정소분류", "공정대분류"]]
    open_spans: dict[str, tuple[str, str, float, pd.Timestamp]] = {}
    rows: list[dict[str, object]] = []

    def close(
        unit: str,
        status: str,
        category: str,
        share: float,
        began: pd.Timestamp,
        finished: pd.Timestamp,
    ) -> None:
        row: dict[str, object] = {
            EQUIPMENT_ID_COLUMN: unit,
            "공정소분류": process_by_unit.at[unit, "공정소분류"],
            "공정대분류": process_by_unit.at[unit, "공정대분류"],
            "상태": status,
            "시작일": began.date(),
            "종료일": finished.date(),
        }
        if with_unit_share:
            row[UNIT_SHARE_COLUMN] = share
            row[COUNT_CATEGORY_COLUMN] = category
        rows.append(row)

    for moment in breakpoints:
        status_frame = _build_equipment_status_from_prepared(
            prepared, prepared_downtime, as_of=moment
        )
        shares = (
            status_frame[UNIT_SHARE_COLUMN].round(UNIT_COUNT_DECIMALS + 3)
            if with_unit_share
            else pd.Series(1.0, index=status_frame.index)
        )
        categories = (
            status_frame[COUNT_CATEGORY_COLUMN] if with_unit_share else status_frame["상태"]
        )
        for unit, status, category, share in zip(
            status_frame[EQUIPMENT_ID_COLUMN],
            status_frame["상태"],
            categories,
            shares,
            strict=True,
        ):
            state = (str(status), str(category), float(share))
            previous = open_spans.get(str(unit))
            if previous is not None and previous[:3] == state:
                continue
            if previous is not None:
                close(str(unit), *previous[:3], previous[3], moment - pd.Timedelta(days=1))
            open_spans[str(unit)] = (*state, moment)
    for unit, (status, category, share, began) in open_spans.items():
        close(unit, status, category, share, began, end)
    result = pd.DataFrame(rows, columns=columns)
    if with_unit_share:
        keys = unit_keys(prepared)
        key_by_unit = dict(zip(prepared[EQUIPMENT_ID_COLUMN], keys, strict=True))
        result[UNIT_KEY_COLUMN] = result[EQUIPMENT_ID_COLUMN].map(key_by_unit)
        counted_by_unit = dict(
            zip(prepared[EQUIPMENT_ID_COLUMN], counts_for_capacity(prepared), strict=True)
        )
        result[COUNTED_COLUMN] = (
            result[EQUIPMENT_ID_COLUMN].map(counted_by_unit).fillna(False).astype("bool")
        )
        exit_days = _exit_days_by_key(prepared, keys)
        unit_exits = [exit_days.get(str(key), frozenset()) for key in result[UNIT_KEY_COLUMN]]
        result[EXIT_STARTS_COLUMN] = pd.Series(
            [began in days for began, days in zip(result["시작일"], unit_exits, strict=True)],
            index=result.index,
            dtype="bool",
        )
        result[EXIT_FOLLOWS_COLUMN] = pd.Series(
            [
                finished + timedelta(days=1) in days
                for finished, days in zip(result["종료일"], unit_exits, strict=True)
            ],
            index=result.index,
            dtype="bool",
        )
    result = result.loc[result["종료일"] >= result["시작일"]]
    return result.sort_values([EQUIPMENT_ID_COLUMN, "시작일"]).reset_index(drop=True)


# ------------------------------------------------------------------ 시험


def test_the_fleet_covers_module_groups_and_overlapping_downtime() -> None:
    """시험 입력이 지분·비가동 이어붙임을 실제로 건드리는지 먼저 본다 — 안 건드리면 아래 동등성은
    아무것도 지키지 않는다."""
    equipment, downtime = _fleet(0)
    prepared = prepare_equipment_master(equipment)
    keys = unit_keys(prepared)
    assert keys.value_counts().gt(1).sum() >= 3
    spans = build_equipment_lifecycle_spans(
        equipment,
        downtime,
        start_date=_WINDOWS[0][0],
        end_date=_WINDOWS[0][1],
        with_unit_share=True,
    )
    assert spans[UNIT_SHARE_COLUMN].between(0.0, 1.0, inclusive="neither").any()
    assert spans["상태"].eq("운영 비가동").any()


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize(("start_date", "end_date"), _WINDOWS)
@pytest.mark.parametrize("with_unit_share", [True, False])
def test_stacked_spans_equal_the_day_by_day_reference(
    seed: int, start_date: date, end_date: date, with_unit_share: bool
) -> None:
    equipment, downtime = _fleet(seed)

    actual = build_equipment_lifecycle_spans(
        equipment,
        downtime,
        start_date=start_date,
        end_date=end_date,
        with_unit_share=with_unit_share,
    )
    expected = _reference_spans(
        equipment,
        downtime,
        start_date=start_date,
        end_date=end_date,
        with_unit_share=with_unit_share,
    )

    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    assert actual.equals(expected)


@pytest.mark.parametrize("with_unit_share", [True, False])
def test_stacked_spans_equal_the_reference_on_the_builtin_sample(with_unit_share: bool) -> None:
    equipment = sample_equipment_master(anchor_date=_ANCHOR)
    downtime = sample_downtime_schedule(anchor_date=_ANCHOR)
    window = {"start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)}

    actual = build_equipment_lifecycle_spans(
        equipment, downtime, **window, with_unit_share=with_unit_share
    )
    expected = _reference_spans(equipment, downtime, **window, with_unit_share=with_unit_share)

    assert actual.equals(expected)


@pytest.mark.parametrize("seed", [0, 1])
def test_breakpoints_are_the_union_of_the_change_days(seed: int) -> None:
    equipment, downtime = _fleet(seed)
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)

    for start_date, end_date in _WINDOWS:
        bounds = {"start": pd.Timestamp(start_date), "end": pd.Timestamp(end_date)}
        assert _lifecycle_breakpoints(
            prepared, prepared_downtime, **bounds
        ) == _reference_breakpoints(prepared, prepared_downtime, **bounds)


@pytest.mark.parametrize("seed", [0, 1])
def test_per_row_moments_judge_like_one_moment_at_a_time(seed: int) -> None:
    """같은 판정 줄의 두 길 — 시점 하나와 행마다의 시점 — 이 칸마다 같은 값을 낸다(비가동 유형
    이어붙임 차례·시점별 지분 포함)."""
    equipment, downtime = _fleet(seed)
    prepared = prepare_equipment_master(equipment)
    prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
    moments = _reference_breakpoints(
        prepared,
        prepared_downtime,
        start=pd.Timestamp(_WINDOWS[0][0]),
        end=pd.Timestamp(_WINDOWS[0][1]),
    )[::7]
    stacked = pd.concat([prepared] * len(moments), ignore_index=True)
    as_of = pd.Series(
        [moment for moment in moments for _ in range(len(prepared))], dtype="datetime64[ns]"
    )

    judged = _build_equipment_status_from_prepared(stacked, prepared_downtime, as_of=as_of)

    for offset, moment in enumerate(moments):
        part = judged.iloc[offset * len(prepared) : (offset + 1) * len(prepared)]
        expected = _build_equipment_status_from_prepared(prepared, prepared_downtime, as_of=moment)
        pd.testing.assert_frame_equal(part.reset_index(drop=True), expected, check_exact=True)
