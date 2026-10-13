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

import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import cast

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest
from test_equipment_explorer import _render_fixture

from capa_simulation.components.equipment_explorer import (
    QUESTION_KEY,
    SMALL_PROCESS_KEY,
    START_DATE_KEY,
)
from capa_simulation.services import simulation_cache
from capa_simulation.services.equipment_availability import (
    _lifecycle_breakpoints,
    _month_bounds,
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_inactive_equipment,
    build_inactive_equipment_in_month,
    build_inactive_equipment_month_view,
    build_milestone_transition_events,
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
        # 마스터 칸 하나만 고친다(비가동은 그대로). 그 달에 비가동인 MOD-01C 를 전달 말일에 반출하면
        # 그 달에는 보유하지 않아 비가동 호기 목록에서 빠진다 — 키에서 마스터 지문이 빠지면 옛 표가
        # 나온다.
        equipment = equipment.copy()
        moved = equipment[EQUIPMENT_ID_COLUMN].eq("MOD-01C")
        equipment.loc[moved, "반출일정"] = pd.Timestamp(month.replace(day=1) - timedelta(days=1))
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


# ------------------------------------------------------------------ 생애주기 일정(Gantt) 구간

GANTT_START = ANCHOR - timedelta(days=30)
GANTT_END = ANCHOR + timedelta(days=90)


def _fresh_gantt(
    equipment: pd.DataFrame, downtime: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    """고치기 전 경로 — 화면이 캐시 없이 부르던 그대로(지분 없이)."""
    return build_equipment_lifecycle_spans(equipment, downtime, start_date=start, end_date=end)


@pytest.mark.parametrize(
    "change", ["process_filter", "downtime_row", "master_cell", "start", "end"]
)
def test_cached_gantt_spans_follow_every_input(
    change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    simulation_cache._cached_lifecycle_gantt_spans.clear()
    equipment, downtime = _fleet()
    start, end = GANTT_START, GANTT_END
    base = simulation_cache.get_lifecycle_gantt_spans(
        equipment, downtime, start_date=start, end_date=end
    )
    assert_frame_equal(base, _fresh_gantt(equipment, downtime, start, end))

    if change == "process_filter":
        equipment, downtime = _filtered(equipment, downtime, ("Final Test", "Burn-In"))
    elif change == "downtime_row":
        downtime = _without_downtime_of(downtime, "MOD-01C")
    elif change == "master_cell":
        equipment = equipment.copy()
        moved = equipment[EQUIPMENT_ID_COLUMN].eq("MOD-01B")
        equipment.loc[moved, "반출일정"] = equipment.loc[moved, "반출일정"] + pd.Timedelta(days=40)
    elif change == "start":
        start = start + timedelta(days=20)
    else:
        end = end - timedelta(days=45)
    built = _counting(
        monkeypatch, "build_equipment_lifecycle_spans", build_equipment_lifecycle_spans
    )
    cached = simulation_cache.get_lifecycle_gantt_spans(
        equipment, downtime, start_date=start, end_date=end
    )
    fresh = _fresh_gantt(equipment, downtime, start, end)

    assert len(built) == 1
    assert_frame_equal(cached, fresh)
    assert not fresh.equals(base)

    again = simulation_cache.get_lifecycle_gantt_spans(
        equipment, downtime, start_date=start, end_date=end
    )
    assert len(built) == 1
    assert_frame_equal(again, fresh)


def test_gantt_spans_and_counting_spans_do_not_stand_in_for_each_other() -> None:
    """같은 키 꼴이지만 다른 캐시다 — 세는 구간(지분·집계분류로도 끊는다)이 그림에 나오면
    안 된다."""
    simulation_cache._cached_lifecycle_gantt_spans.clear()
    simulation_cache.get_equipment_lifecycle_spans.clear()
    equipment, downtime = _fleet()
    key = simulation_cache.equipment_span_cache_key(
        equipment=equipment, downtime=downtime, start_date=GANTT_START, end_date=GANTT_END
    )
    counting = simulation_cache.get_equipment_lifecycle_spans(
        key, _equipment=equipment, _downtime=downtime
    )

    gantt = simulation_cache.get_lifecycle_gantt_spans(
        equipment, downtime, start_date=GANTT_START, end_date=GANTT_END
    )

    assert_frame_equal(gantt, _fresh_gantt(equipment, downtime, GANTT_START, GANTT_END))
    assert_frame_equal(
        counting,
        build_equipment_lifecycle_spans(
            equipment,
            downtime,
            start_date=GANTT_START,
            end_date=GANTT_END,
            with_unit_share=True,
        ),
    )
    # 모듈 반출로 형제의 지분이 바뀌는 날, 세는 구간만 끊긴다.
    assert len(counting) > len(gantt)


def _gantt_units(app: AppTest) -> set[str]:
    spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    return {str(unit) for trace in spec["data"] for unit in trace.get("y", [])}


def _gantt_spec(app: AppTest) -> str:
    return str(app.get("plotly_chart")[0].proto.spec)


def test_the_gantt_view_redraws_for_filter_period_and_master_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """화면: 같은 조건의 rerun 은 구간을 다시 만들지 않고 같은 그림이다. 필터·기간·마스터를
    바꾸면 새 그림이다."""
    simulation_cache._cached_lifecycle_gantt_spans.clear()
    built = _counting(
        monkeypatch, "build_equipment_lifecycle_spans", build_equipment_lifecycle_spans
    )
    app = AppTest.from_function(_render_fixture, default_timeout=30).run()
    app.segmented_control(QUESTION_KEY).set_value("호기 현황").run()
    app.selectbox("equipment_explorer_unit_view").set_value("생애주기 일정").run()
    assert not app.exception
    base = _gantt_spec(app)
    assert _gantt_units(app) == {"EQ-REPAIR", "EQ-READY", "EQ-QUAL", "EQ-OTHER"}
    count = len(built)

    app.run()
    assert len(built) == count
    assert _gantt_spec(app) == base

    app.multiselect(SMALL_PROCESS_KEY).set_value(["Other"]).run()
    assert _gantt_units(app) == {"EQ-OTHER"}
    app.multiselect(SMALL_PROCESS_KEY).set_value([]).run()
    assert _gantt_spec(app) == base

    app.date_input(START_DATE_KEY).set_value(date(2026, 10, 3)).run()
    assert not app.exception
    assert _gantt_spec(app) != base

    app.session_state["undated_unit"] = True
    app.run()
    assert not app.exception
    assert "EQ-NODATE" in _gantt_units(app)


# ------------------------------------------------------------------ 기준일 상태·비가동·단계 전환


_AS_OF_DAYS = (ANCHOR - timedelta(days=40), ANCHOR, ANCHOR + timedelta(days=11))


@pytest.mark.parametrize("processes", _FILTERS)
@pytest.mark.parametrize("as_of", _AS_OF_DAYS)
def test_cached_status_and_inactive_match_the_direct_calls(
    as_of: date, processes: tuple[str, ...]
) -> None:
    """같은 숫자 — 기준일 상태·비가동(기준일 시점)·단계 전환은 캐시를 지나도 직접 부른 것과 같다."""
    equipment, downtime = _filtered(*_fleet(), processes)

    assert_frame_equal(
        simulation_cache.get_equipment_status_as_of(equipment, downtime, as_of=as_of),
        build_equipment_status_as_of(equipment, downtime, as_of=as_of),
    )
    assert_frame_equal(
        simulation_cache.get_inactive_equipment(equipment, downtime, as_of=as_of),
        build_inactive_equipment(equipment, downtime, as_of=as_of),
    )
    window = {"start_date": GANTT_START, "end_date": GANTT_END, "as_of": as_of}
    assert_frame_equal(
        simulation_cache.get_milestone_transition_events(equipment, **window),
        build_milestone_transition_events(equipment, **window),
    )


@pytest.mark.parametrize("change", ["as_of", "process_filter", "downtime_row", "master_cell"])
def test_cached_status_follows_every_input(change: str, monkeypatch: pytest.MonkeyPatch) -> None:
    simulation_cache._cached_equipment_status_as_of.clear()
    equipment, downtime = _fleet()
    as_of = ANCHOR
    base = simulation_cache.get_equipment_status_as_of(equipment, downtime, as_of=as_of)
    base_inactive = simulation_cache.get_inactive_equipment(equipment, downtime, as_of=as_of)

    if change == "as_of":
        as_of = ANCHOR + timedelta(days=11)  # MOD-01B 반출 뒤
    elif change == "process_filter":
        equipment, downtime = _filtered(equipment, downtime, ("Final Test", "Burn-In"))
    elif change == "downtime_row":
        downtime = _without_downtime_of(downtime, "MOD-01C")
    else:
        equipment = equipment.copy()
        moved = equipment[EQUIPMENT_ID_COLUMN].eq("MOD-01C")
        equipment.loc[moved, "반출일정"] = pd.Timestamp(ANCHOR - timedelta(days=1))
    built = _counting(monkeypatch, "build_equipment_status_as_of", build_equipment_status_as_of)
    status = simulation_cache.get_equipment_status_as_of(equipment, downtime, as_of=as_of)
    inactive = simulation_cache.get_inactive_equipment(equipment, downtime, as_of=as_of)
    fresh = build_equipment_status_as_of(equipment, downtime, as_of=as_of)

    assert len(built) == 1  # 상태 분포와 비가동 시점이 한 판정을 나눈다
    assert_frame_equal(status, fresh)
    assert_frame_equal(inactive, build_inactive_equipment(equipment, downtime, as_of=as_of))
    assert not fresh.equals(base)
    assert not inactive.equals(base_inactive)

    again = simulation_cache.get_equipment_status_as_of(equipment, downtime, as_of=as_of)
    assert len(built) == 1
    assert_frame_equal(again, fresh)


@pytest.mark.parametrize("change", ["start", "end", "as_of", "master_cell"])
def test_cached_transitions_follow_every_input(
    change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    simulation_cache._cached_milestone_transition_events.clear()
    equipment, _ = _fleet()
    window = {"start_date": GANTT_START, "end_date": GANTT_END, "as_of": ANCHOR}
    base = simulation_cache.get_milestone_transition_events(equipment, **window)

    if change == "start":
        window["start_date"] = ANCHOR
    elif change == "end":
        window["end_date"] = ANCHOR + timedelta(days=20)
    elif change == "as_of":
        window["as_of"] = ANCHOR + timedelta(days=30)
    else:
        equipment = equipment.copy()
        moved = equipment[EQUIPMENT_ID_COLUMN].eq("MOD-01B")
        equipment.loc[moved, "반출일정"] = equipment.loc[moved, "반출일정"] + pd.Timedelta(days=3)
    built = _counting(
        monkeypatch, "build_milestone_transition_events", build_milestone_transition_events
    )
    events = simulation_cache.get_milestone_transition_events(equipment, **window)
    fresh = build_milestone_transition_events(equipment, **window)

    assert len(built) == 1
    assert_frame_equal(events, fresh)
    assert not fresh.equals(base)

    again = simulation_cache.get_milestone_transition_events(equipment, **window)
    assert len(built) == 1
    assert_frame_equal(again, fresh)


def _shown(app: AppTest) -> list[str]:
    """화면에 그린 결과 — 표·차트·지표·글을 차례대로 직렬화한다."""
    parts = [frame.value.to_json(force_ascii=False) for frame in app.dataframe]
    parts += [str(chart.proto.spec) for chart in app.get("vega_lite_chart")]
    parts += [f"{metric.label}={metric.value}" for metric in app.metric]
    parts += [item.value for item in app.markdown] + [item.value for item in app.caption]
    return parts


@pytest.mark.parametrize(
    ("question", "view_key", "view"),
    [
        ("호기 현황", "equipment_explorer_unit_view", "상태 분포"),
        ("호기 현황", "equipment_explorer_unit_view", "호기 목록"),
        ("비가동 호기", "equipment_explorer_inactive_view", "기준일 시점"),
        ("비가동 호기", "equipment_explorer_inactive_view", "그 달 전체"),
        ("Qual 일정", "equipment_explorer_qual_view", "호기 목록"),
        ("Qual 일정", "equipment_explorer_qual_view", "확정상태 분포"),
        ("단계 전환", "equipment_explorer_transition_view", "단계별 건수"),
        ("단계 전환", "equipment_explorer_transition_view", "전환 일정 목록"),
    ],
)
def test_a_warm_rerun_shows_exactly_what_a_cold_run_showed(
    question: str, view_key: str, view: str
) -> None:
    """화면: 캐시를 비운 첫 회차와 캐시가 적중한 다음 회차가 같은 표·차트·지표·글을 그린다."""
    for clear in (
        simulation_cache._cached_equipment_status_as_of.clear,
        simulation_cache._cached_inactive_equipment_month.clear,
        simulation_cache._cached_milestone_transition_events.clear,
    ):
        clear()
    app = AppTest.from_function(_render_fixture, default_timeout=30).run()
    app.segmented_control(QUESTION_KEY).set_value(question).run()
    app.selectbox(view_key).set_value(view).run()
    assert not app.exception
    cold = _shown(app)

    app.run()

    assert not app.exception
    assert _shown(app) == cold
    assert cold
