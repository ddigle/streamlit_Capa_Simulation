# Purpose: 가용설비 Main 판정 캐시가 고치기 전 경로와 같은 표를 내고 입력마다 다시 계산하는지 본다.

"""가용설비 Main(호기 현황·비가동 호기·Qual 일정·생애주기 일정)의 판정 캐시.

두 가지를 본다.

1. **같은 숫자** — 검증을 한 번만 하고 시점마다 판정만 다시 하는 새 경로가, 시점마다 처음부터
   다시 하던 옛 경로(이 파일의 `_reference_*`, 고치기 전 코드를 그대로 옮긴 것)와 같은 표를 낸다.
2. **무효화** — 캐시는 키(거른 두 표의 내용 지문 + 날짜 인자)로만 적중한다. 입력을 하나씩 바꿔
   가며 키가 갈리는지, 캐시를 거친 결과가 캐시 없이 새로 낸 결과와 같은지, 바꾸기 전과 다른지
   (다르지 않으면 그 경우는 무엇도 증명하지 않는다) 본다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import cast

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from capa_simulation.services import simulation_cache
from capa_simulation.services.equipment_availability import (
    _lifecycle_breakpoints,
    _month_bounds,
    build_inactive_equipment,
    build_inactive_equipment_in_month,
    build_inactive_equipment_month_view,
    inactive_equipment_moments,
)
from capa_simulation.services.equipment_contract import (
    CONVERSION_RATIO_COLUMN,
    DOWNTIME_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_master,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_for_prepared_equipment,
    prepare_equipment_master,
)

ANCHOR = date(2026, 10, 13)
MONTHS = (date(2026, 9, 20), date(2026, 10, 15), date(2026, 11, 2), date(2026, 12, 31))


def _fleet(anchor: date = ANCHOR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """샘플 fleet + 모듈 설비 한 대(모듈 넷, 하나는 그 달 중 반출) + 겹치는 비가동.

    - `MOD-01A~D` 는 `MOD-01` 의 모듈이다. B 는 기준일 10일 뒤 반출되어 형제의 지분이 바뀐다.
      C 는 기준일 앞뒤로 비가동이다.
    - 샘플의 첫 비가동 호기에 겹치는 비가동을 하나 더 둔다(같은 호기, 다른 유형).
    - 반출 예정 호기 하나에 비가동을 둔다(상태 이름이 「반출 예정」으로 가려지는 호기).
    """
    equipment = sample_equipment_master(anchor_date=anchor)
    downtime = sample_downtime_schedule(anchor_date=anchor)
    template = equipment.iloc[0].to_dict()
    arrival = pd.Timestamp(anchor - timedelta(days=60))
    modules = []
    for suffix in "ABCD":
        modules.append(
            {
                **template,
                EQUIPMENT_ID_COLUMN: f"MOD-01{suffix}",
                PARENT_EQUIPMENT_COLUMN: "MOD-01",
                CONVERSION_RATIO_COLUMN: 0.25,
                "레이아웃표시": "N",
                "동": None,
                "층": None,
                "X좌표": None,
                "Y좌표": None,
                "제진대일정": pd.NaT,
                "물류일정": pd.NaT,
                "반입일정": arrival,
                "Qual일정": arrival + pd.Timedelta(days=20),
                "확정상태": "완료",
                "반출일정": (
                    pd.Timestamp(anchor + timedelta(days=10)) if suffix == "B" else pd.NaT
                ),
                "이설일정": pd.NaT,
            }
        )
    module_rows = pd.DataFrame(modules, columns=equipment.columns).astype(equipment.dtypes)
    equipment = pd.concat([equipment, module_rows], ignore_index=True)
    exit_scheduled = equipment.loc[equipment["반출일정"].notna(), EQUIPMENT_ID_COLUMN].iloc[0]
    first_down = str(downtime[EQUIPMENT_ID_COLUMN].iloc[0])
    first_start = pd.Timestamp(downtime["시작일"].iloc[0])
    extra = pd.DataFrame(
        [
            {
                EQUIPMENT_ID_COLUMN: "MOD-01C",
                "비가동유형": "예방보전",
                "시작일": pd.Timestamp(anchor - timedelta(days=3)),
                "종료일": pd.Timestamp(anchor + timedelta(days=2)),
                "상세사유": "모듈 PM",
                "비고": None,
            },
            {
                EQUIPMENT_ID_COLUMN: first_down,
                "비가동유형": "개조겹침",
                "시작일": first_start + pd.Timedelta(days=4),
                "종료일": first_start + pd.Timedelta(days=15),
                "상세사유": "겹침",
                "비고": None,
            },
            {
                EQUIPMENT_ID_COLUMN: exit_scheduled,
                "비가동유형": "고장",
                "시작일": pd.Timestamp(anchor + timedelta(days=5)),
                "종료일": pd.Timestamp(anchor + timedelta(days=8)),
                "상세사유": "반출 전 고장",
                "비고": None,
            },
        ],
        columns=list(DOWNTIME_COLUMNS),
    ).astype(downtime.dtypes)
    downtime = pd.concat([downtime, extra], ignore_index=True)
    return equipment, downtime


def _filtered(
    equipment: pd.DataFrame, downtime: pd.DataFrame, processes: tuple[str, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """화면(`render_equipment_explorer`)과 같은 거르기 — 공정을 거르고 그 호기의 비가동만 남긴다."""
    filtered = equipment
    if processes:
        filtered = filtered.loc[filtered["공정소분류"].isin(processes)]
    filtered = filtered.copy()
    filtered_downtime = downtime.loc[
        downtime[EQUIPMENT_ID_COLUMN].isin(filtered[EQUIPMENT_ID_COLUMN])
    ].copy()
    return filtered, filtered_downtime


# ------------------------------------------------------------------ 고치기 전 경로(그대로 옮김)


def _reference_moments(equipment: pd.DataFrame, downtime: pd.DataFrame, month: date) -> list[date]:
    month_start, month_end = _month_bounds(month)
    moments = {month_start}
    prepared = prepare_equipment_master(equipment)
    if not prepared.empty:
        prepared_downtime = prepare_downtime_for_prepared_equipment(downtime, prepared)
        moments.update(
            breakpoint.date()
            for breakpoint in _lifecycle_breakpoints(
                prepared,
                prepared_downtime,
                start=pd.Timestamp(month_start),
                end=pd.Timestamp(month_end),
            )
        )
    sunday = month_start + timedelta(days=(6 - month_start.weekday()) % 7)
    while sunday <= month_end:
        moments.add(sunday)
        sunday += timedelta(days=7)
    return sorted(moments)


def _reference_in_month(
    equipment: pd.DataFrame, downtime: pd.DataFrame, month: date, moments: list[date]
) -> pd.DataFrame:
    sampled = sorted(set(moments)) or [_month_bounds(month)[0]]
    stacked = pd.concat(
        [
            build_inactive_equipment(equipment, downtime, as_of=moment).assign(_시점=moment)
            for moment in sampled
        ],
        ignore_index=True,
    )
    caught = stacked.groupby(EQUIPMENT_ID_COLUMN)["_시점"].agg(["min", "max"])
    result = (
        stacked.drop_duplicates(EQUIPMENT_ID_COLUMN, keep="first")
        .drop(columns=["_시점"])
        .reset_index(drop=True)
    )
    after_id = cast(int, result.columns.get_loc(EQUIPMENT_ID_COLUMN)) + 1
    result.insert(after_id, "비가동 시작", result[EQUIPMENT_ID_COLUMN].map(caught["min"]))
    result.insert(after_id + 1, "비가동 종료", result[EQUIPMENT_ID_COLUMN].map(caught["max"]))
    return result.sort_values(["비가동 시작", EQUIPMENT_ID_COLUMN], kind="stable").reset_index(
        drop=True
    )


# ------------------------------------------------------------------ 「그 달 전체」 같은 숫자


_FILTERS: tuple[tuple[str, ...], ...] = ((), ("Final Test", "Burn-In"), ("TC Bonding",))


@pytest.mark.parametrize("processes", _FILTERS)
@pytest.mark.parametrize("month", MONTHS)
def test_month_view_matches_the_per_moment_path(month: date, processes: tuple[str, ...]) -> None:
    """검증 한 번 + 시점마다 판정은 시점마다 처음부터 하던 옛 경로와 시점·행·값이 모두 같다."""
    equipment, downtime = _filtered(*_fleet(), processes)
    expected_moments = _reference_moments(equipment, downtime, month)
    expected = _reference_in_month(equipment, downtime, month, expected_moments)

    moments, result = build_inactive_equipment_month_view(equipment, downtime, month=month)

    assert moments == expected_moments
    assert_frame_equal(result, expected)
    assert inactive_equipment_moments(equipment, downtime, month=month) == expected_moments
    assert_frame_equal(
        build_inactive_equipment_in_month(equipment, downtime, month=month), expected
    )
    assert_frame_equal(
        build_inactive_equipment_in_month(equipment, downtime, month=month, moments=moments),
        expected,
    )


def test_the_month_fixture_exercises_modules_overlaps_and_exits() -> None:
    """전제: 고른 달의 결과에 모듈 행·겹친 비가동 호기·반출 예정 호기가 실제로 든다."""
    equipment, downtime = _fleet()
    _, result = build_inactive_equipment_month_view(equipment, downtime, month=ANCHOR)
    units = set(result[EQUIPMENT_ID_COLUMN].astype(str))

    assert "MOD-01C" in units
    # 반출 예정 호기의 비가동(맨 끝 줄)과 겹친 비가동 호기(그 앞 줄)
    assert {str(unit) for unit in downtime[EQUIPMENT_ID_COLUMN].iloc[-2:]} <= units
    # 달마다 다른 표가 나온다 — 달을 키에서 빼면 틀린다는 것을 아래 무효화 테스트가 보려면 필요하다.
    tables = {
        tuple(build_inactive_equipment_month_view(equipment, downtime, month=month)[1]["설비명"])
        for month in MONTHS
    }
    assert len(tables) == len(MONTHS)


def test_an_invalid_master_still_raises_and_is_not_cached() -> None:
    """검증 실패는 지금처럼 `ValueError` 이고 캐시에 남지 않는다 — 고친 뒤 다시 부르면 계산한다."""
    simulation_cache._cached_inactive_equipment_month.clear()
    equipment, downtime = _fleet()
    broken = equipment.copy()
    broken.loc[0, "보관유무"] = "X"

    with pytest.raises(ValueError, match="보관유무"):
        simulation_cache.get_inactive_equipment_month(broken, downtime, month=ANCHOR)
    with pytest.raises(ValueError, match="보관유무"):
        build_inactive_equipment_in_month(broken, downtime, month=ANCHOR)

    _, result = simulation_cache.get_inactive_equipment_month(equipment, downtime, month=ANCHOR)
    assert not result.empty


# ------------------------------------------------------------------ 「그 달 전체」 캐시 무효화


def _counting(
    monkeypatch: pytest.MonkeyPatch, name: str, original: Callable[..., object]
) -> list[object]:
    built: list[object] = []

    def counting(*args: object, **kwargs: object) -> object:
        built.append(kwargs.get("month", kwargs.get("as_of", kwargs.get("end_date"))))
        return original(*args, **kwargs)

    monkeypatch.setattr(simulation_cache, name, counting)
    return built


def _without_downtime_of(downtime: pd.DataFrame, unit: str) -> pd.DataFrame:
    return downtime.loc[downtime[EQUIPMENT_ID_COLUMN].ne(unit)].reset_index(drop=True)


@pytest.mark.parametrize("change", ["month", "process_filter", "downtime_row", "master_cell"])
def test_cached_month_view_follows_every_input(
    change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    simulation_cache._cached_inactive_equipment_month.clear()
    equipment, downtime = _fleet()
    month = ANCHOR
    base_moments, base = simulation_cache.get_inactive_equipment_month(
        equipment, downtime, month=month
    )

    if change == "month":
        month = date(2026, 11, 2)
    elif change == "process_filter":
        equipment, downtime = _filtered(equipment, downtime, ("Final Test", "Burn-In"))
    elif change == "downtime_row":
        downtime = _without_downtime_of(downtime, "MOD-01C")
    else:
        # 반출일을 한 달 늦추면 형제 모듈의 지분 경계(시점)가 그 달에서 빠진다.
        equipment = equipment.copy()
        moved = equipment[EQUIPMENT_ID_COLUMN].eq("MOD-01B")
        equipment.loc[moved, "반출일정"] = equipment.loc[moved, "반출일정"] + pd.Timedelta(days=40)
        downtime = _without_downtime_of(downtime, "MOD-01C")
    built = _counting(
        monkeypatch,
        "build_inactive_equipment_month_view",
        build_inactive_equipment_month_view,
    )
    moments, cached = simulation_cache.get_inactive_equipment_month(
        equipment, downtime, month=month
    )
    fresh_moments, fresh = build_inactive_equipment_month_view(equipment, downtime, month=month)

    assert len(built) == 1  # 새 키라 다시 계산했다
    assert moments == fresh_moments
    assert_frame_equal(cached, fresh)
    assert (moments, list(fresh["설비명"])) != (base_moments, list(base["설비명"]))

    # 같은 입력으로 다시 부르면 계산하지 않는다 — 같은 보기를 열어 둔 rerun 이 이 경로다.
    _, again = simulation_cache.get_inactive_equipment_month(equipment, downtime, month=month)
    assert len(built) == 1
    assert_frame_equal(again, fresh)


def test_another_day_in_the_same_month_reuses_the_month(monkeypatch: pytest.MonkeyPatch) -> None:
    """결과는 그 달(년·월)로만 정해진다 — 같은 달 안에서 기준일만 옮기면 다시 계산하지 않는다."""
    simulation_cache._cached_inactive_equipment_month.clear()
    equipment, downtime = _fleet()
    first_moments, first = simulation_cache.get_inactive_equipment_month(
        equipment, downtime, month=date(2026, 10, 3)
    )
    built = _counting(
        monkeypatch,
        "build_inactive_equipment_month_view",
        build_inactive_equipment_month_view,
    )

    moments, again = simulation_cache.get_inactive_equipment_month(
        equipment, downtime, month=date(2026, 10, 29)
    )
    fresh_moments, fresh = build_inactive_equipment_month_view(
        equipment, downtime, month=date(2026, 10, 29)
    )

    assert built == []
    assert moments == first_moments == fresh_moments
    assert_frame_equal(again, first)
    assert_frame_equal(again, fresh)


def test_a_caller_editing_the_cached_frame_does_not_change_the_next_read() -> None:
    simulation_cache._cached_inactive_equipment_month.clear()
    equipment, downtime = _fleet()
    _, first = simulation_cache.get_inactive_equipment_month(equipment, downtime, month=ANCHOR)
    expected = first.copy()
    first.loc[:, "상태"] = "고친 값"

    _, again = simulation_cache.get_inactive_equipment_month(equipment, downtime, month=ANCHOR)

    assert_frame_equal(again, expected)
