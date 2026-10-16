# Purpose: 가용설비 현황 캐시 래퍼가 키로 적중하고 캐시 없이 새로 계산한 결과와 같은지 고정한다.

"""가용설비 현황 캐시 래퍼(`services/simulation_cache.py`).

래퍼는 프레임을 해시하지 않고 키만 본다(`_` 인자). 그래서 **키에서 입력을 하나라도 빠뜨리면 낡은
값이 나온다.** 여기서는 입력을 하나씩 바꿔 가며 (1) 키가 바뀌는지, (2) 캐시를 거친 결과가 캐시 없이
새로 계산한 결과와 같은지를 본다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_required_shortening import MAY, PROCESS, _worked_example

from capa_simulation.services import simulation_cache
from capa_simulation.services.availability_gap import GapComparison, build_availability_gap
from capa_simulation.services.availability_sheet import (
    ROW_SCHEDULE_LENT,
    AvailabilitySheet,
    build_availability_sheet,
)
from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
    build_monthly_equipment_contributions,
    span_date_range,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff
from capa_simulation.services.required_shortening import (
    TARGET_LEVELS,
    ShorteningPlan,
    plan_required_shortening,
    process_month_export_frame,
    unit_export_frame,
)
from capa_simulation.services.securement_cross_check import (
    CrossCheck,
    cross_check_from_monthly,
)


def _csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


# ------------------------------------------------------------------ 필요단축일정 CSV(A10)


def test_shortening_csvs_are_built_once_per_plan_key_and_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """목표만 바꾼 rerun 이 세 표를 다시 만들지 않는다 — 바이트는 새로 만든 것과 같다(점검 A10)."""
    simulation_cache.get_required_shortening_csvs.clear()
    plan = _worked_example()
    key = ((1, "plan-token", MAY, MAY), "m", "d", "b", "c", plan.months, plan.today.isoformat())
    built: list[tuple[float, ...]] = []

    def counting(
        plan: ShorteningPlan, levels: Sequence[float], processes: Sequence[str] | None = None
    ) -> pd.DataFrame:
        built.append(tuple(levels))
        return unit_export_frame(plan, levels, processes)

    monkeypatch.setattr(simulation_cache, "unit_export_frame", counting)
    scope = (PROCESS,)

    first = simulation_cache.get_required_shortening_csvs(key, 1.1, scope, (MAY,), _plan=plan)
    again = simulation_cache.get_required_shortening_csvs(key, 1.1, scope, (MAY,), _plan=plan)

    assert again == first
    assert built == [(1.1,), TARGET_LEVELS]
    assert first == (
        _csv(unit_export_frame(plan, (1.1,), scope)),
        _csv(unit_export_frame(plan, TARGET_LEVELS, scope)),
        _csv(process_month_export_frame(plan, (1.1,), scope, (MAY,))),
    )
    assert first[0].startswith(b"\xef\xbb\xbf")

    # 목표를 바꾸면 새 키다 — 고른 목표의 두 표가 그 목표로 다시 나온다.
    other = simulation_cache.get_required_shortening_csvs(key, 1.3, scope, (MAY,), _plan=plan)
    assert len(built) == 4
    assert other[0] == _csv(unit_export_frame(plan, (1.3,), scope))
    assert other[2] == _csv(process_month_export_frame(plan, (1.3,), scope, (MAY,)))
    assert other[1] == first[1]


# ------------------------------------------------------------------ Static/Dynamic(A2)

ANCHOR = date(2026, 10, 8)
MONTHS = (202610, 202611, 202612)


def _fleet(
    anchor: date = ANCHOR,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """샘플 fleet(설비 마스터·비가동·기존보유)과 그 공정 전부에 Cut-off 10일."""
    equipment = sample_equipment_master(anchor_date=anchor)
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    cutoff = prepare_process_cutoff(
        pd.DataFrame(
            {
                "공정": processes,
                "Cutoff일수": [10.0] * len(processes),
                "비고": [None] * len(processes),
            }
        )
    )
    return (
        equipment,
        sample_downtime_schedule(anchor_date=anchor),
        sample_equipment_baseline(),
        cutoff,
    )


def _ratios(equipment: pd.DataFrame) -> dict[str, float]:
    """페이지와 같은 환산비 매핑(값이 없는 호기는 뺀다 — 서비스가 1.0 으로 읽는다)."""
    return {
        str(unit).strip(): float(ratio)
        for unit, ratio in zip(equipment["설비명"], equipment["환산비"], strict=True)
        if pd.notna(ratio)
    }


def _static(processes: Sequence[str], months: Sequence[int], count: float = 3.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"생산계획년월": month, "공정": process, "가용대수": count}
            for month in months
            for process in processes
        ]
    )


def _span_range(cutoff: pd.DataFrame, months: Sequence[int]) -> tuple[date, date]:
    span = span_date_range(months, cutoff)
    assert span is not None
    return span


def _cached_spans(
    equipment: pd.DataFrame, downtime: pd.DataFrame, start: date, end: date
) -> tuple[simulation_cache.EquipmentSpanCacheKey, pd.DataFrame]:
    key = simulation_cache.equipment_span_cache_key(
        equipment=equipment, downtime=downtime, start_date=start, end_date=end
    )
    spans = simulation_cache.get_equipment_lifecycle_spans(
        key, _equipment=equipment, _downtime=downtime
    )
    return key, spans


def _fresh_spans(
    equipment: pd.DataFrame, downtime: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    return build_equipment_lifecycle_spans(
        equipment, downtime, start_date=start, end_date=end, with_unit_share=True
    )


def _clear_equipment_caches() -> None:
    simulation_cache.get_equipment_lifecycle_spans.clear()
    simulation_cache.get_availability_comparison.clear()
    simulation_cache.get_monthly_equipment_contributions.clear()
    simulation_cache.get_availability_sheet.clear()
    simulation_cache.get_required_shortening.clear()


def _later_qual(equipment: pd.DataFrame) -> pd.DataFrame:
    """조회 범위 안에 Qual 이 있는 신규 호기 하나의 Qual 을 26일 늦춘다(마스터 한 칸)."""
    changed = equipment.copy()
    qual = pd.to_datetime(changed["Qual일정"])
    inside = changed["기존설비여부"].eq("N") & qual.between("2026-10-01", "2026-11-15")
    position = changed.index[inside.fillna(False).astype(bool)][0]
    changed.loc[position, "Qual일정"] = qual.loc[position] + pd.Timedelta(days=26)
    return changed


@pytest.mark.parametrize("change", ["master_cell", "downtime_row", "span_end", "today"])
def test_cached_spans_follow_every_input(change: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """구간 캐시는 마스터 한 칸·비가동 한 줄·범위·오늘(샘플 fleet 의 기준일)을 모두 키로 갈라낸다.

    바뀐 입력에서 캐시를 거친 구간은 캐시 없이 새로 만든 구간과 같고, 바뀌기 전 구간과는 다르다
    (다르지 않으면 그 경우는 무엇도 증명하지 않는다). 오늘은 구간 함수의 인자가 아니다 — 페이지의
    샘플 fleet 이 오늘을 기준으로 만들어지므로 그 내용 지문이 덮는다.
    """
    _clear_equipment_caches()
    equipment, downtime, _baseline, cutoff = _fleet()
    start, end = _span_range(cutoff, MONTHS)
    base_key, base_spans = _cached_spans(equipment, downtime, start, end)

    if change == "master_cell":
        equipment = _later_qual(equipment)
    elif change == "downtime_row":
        downtime = downtime.iloc[1:].reset_index(drop=True)
    elif change == "span_end":
        end = end + timedelta(days=31)
    else:
        equipment, downtime, _baseline, cutoff = _fleet(ANCHOR + timedelta(days=1))
    key, spans = _cached_spans(equipment, downtime, start, end)
    fresh = _fresh_spans(equipment, downtime, start, end)

    assert key != base_key
    assert_frame_equal(spans, fresh)
    assert not fresh.equals(base_spans)

    # 같은 키로 다시 부르면 만들지 않는다 — 보기 전환의 rerun 이 이 경로다.
    built: list[object] = []

    def counting(*args: object, **kwargs: object) -> pd.DataFrame:
        built.append(args)
        return fresh

    monkeypatch.setattr(simulation_cache, "build_equipment_lifecycle_spans", counting)
    _, again = _cached_spans(equipment, downtime, start, end)
    assert built == []
    assert_frame_equal(again, fresh)


def _comparison(
    spans: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    static: pd.DataFrame,
    months: Sequence[int],
    ratios: dict[str, float],
) -> tuple[simulation_cache.AvailabilityComparisonCacheKey, pd.DataFrame, GapComparison]:
    monthly_key = simulation_cache.dynamic_monthly_cache_key(
        spans=spans, baseline=baseline, cutoff=cutoff, months=months, conversion_ratios=ratios
    )
    key = simulation_cache.availability_comparison_cache_key(monthly_key, static=static)
    monthly, comparison = simulation_cache.get_availability_comparison(
        key,
        _spans=spans,
        _baseline=baseline,
        _cutoff=cutoff,
        _static=static,
        _conversion_ratios=ratios,
    )
    return key, monthly, comparison


@pytest.mark.parametrize("change", ["cutoff", "months", "ratio", "baseline", "static", "spans"])
def test_cached_monthly_comparison_follows_every_input(change: str) -> None:
    """월별·비교 캐시는 Cut-off·달 범위·환산비·기존보유·Static·구간을 모두 키로 갈라낸다.

    환산비는 구간 표에 없는 입력이라 구간 지문이 덮지 못한다 — 키에 따로 싣는지를 본다.
    """
    _clear_equipment_caches()
    equipment, downtime, baseline, cutoff = _fleet()
    start, end = _span_range(cutoff, MONTHS)
    spans = _fresh_spans(equipment, downtime, start, end)
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    static = _static(processes, MONTHS)
    ratios = _ratios(equipment)
    months: Sequence[int] = MONTHS
    base_key, base_monthly, base_comparison = _comparison(
        spans, baseline, cutoff, static, months, ratios
    )

    if change == "cutoff":
        cutoff = cutoff.copy()
        cutoff.loc[cutoff["공정"].eq("Die Attach"), "Cutoff일수"] = 20.0
    elif change == "months":
        months = MONTHS[:2]
    elif change == "ratio":
        die_attach = equipment.loc[equipment["공정소분류"].eq("Die Attach"), "설비명"]
        ratios = {**ratios, str(die_attach.iloc[0]): 0.5}
    elif change == "baseline":
        # Cut-off 가 있는 공정의 기존보유여야 월별에 든다.
        baseline = baseline.copy()
        die_attach = baseline["공정"].eq("Die Attach")
        assert die_attach.any()
        baseline.loc[die_attach, "기존보유대수"] = baseline.loc[die_attach, "기존보유대수"] + 7.0
    elif change == "static":
        static = _static(processes, MONTHS, count=4.0)
    else:
        spans = _fresh_spans(_later_qual(equipment), downtime, start, end)
    key, monthly, comparison = _comparison(spans, baseline, cutoff, static, months, ratios)
    fresh_monthly = build_monthly_equipment_availability(
        spans, baseline, cutoff, months, conversion_ratios=ratios
    )
    fresh = build_availability_gap(fresh_monthly, static, months)

    assert key != base_key
    assert_frame_equal(monthly, fresh_monthly)
    assert_frame_equal(comparison.rows, fresh.rows)
    assert (comparison.dynamic_only, comparison.static_only) == (
        fresh.dynamic_only,
        fresh.static_only,
    )
    assert not fresh.rows.equals(base_comparison.rows)
    if change != "static":
        assert not fresh_monthly.equals(base_monthly)


def test_cached_contributions_match_a_fresh_build() -> None:
    """분류별 내역의 호기별 기여도 월별과 같은 키로 캐시하고, 새로 만든 것과 같다."""
    _clear_equipment_caches()
    equipment, downtime, baseline, cutoff = _fleet()
    start, end = _span_range(cutoff, MONTHS)
    spans = _fresh_spans(equipment, downtime, start, end)
    ratios = _ratios(equipment)
    key = simulation_cache.dynamic_monthly_cache_key(
        spans=spans, baseline=baseline, cutoff=cutoff, months=MONTHS, conversion_ratios=ratios
    )

    cached = simulation_cache.get_monthly_equipment_contributions(
        key, _spans=spans, _baseline=baseline, _cutoff=cutoff, _conversion_ratios=ratios
    )

    assert_frame_equal(
        cached,
        build_monthly_equipment_contributions(
            spans, baseline, cutoff, MONTHS, conversion_ratios=ratios
        ),
    )


def _required(processes: Sequence[str], months: Sequence[int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"생산계획년월": month, "공정": process, "STEP": "S1", "소요대수": 6.0}
            for month in months
            for process in processes
        ]
    )


def _plan_frames(plan: ShorteningPlan) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        unit_export_frame(plan, TARGET_LEVELS),
        process_month_export_frame(plan, TARGET_LEVELS),
    )


# 시나리오 표 자리에 넘기는 빈 묶음 — 아래 테스트는 소요대수를 내는 함수를 대역으로 바꾼다.
_NO_TABLES: dict[str, pd.DataFrame] = {}


def _fake_demand(
    monkeypatch: pytest.MonkeyPatch, by_token: dict[str, pd.DataFrame]
) -> list[simulation_cache.ScenarioCacheKey]:
    """`get_scenario_capacity_and_demand` 를 content_token 별 소요대수를 내는 대역으로 바꾼다.

    키 전용 캐시가 소요대수를 **언제** 꺼내는지 보려고 부른 키를 적어 돌려준다(빗나갈 때만 늘어야
    한다). 소요대수는 조회기간으로 자른다 — 진짜 함수와 같은 약속이다.
    """
    calls: list[simulation_cache.ScenarioCacheKey] = []

    def fake(
        cache_key: simulation_cache.ScenarioCacheKey, **_kwargs: object
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        calls.append(cache_key)
        _, token, start, end = cache_key
        required = by_token[token]
        months = pd.to_numeric(required["생산계획년월"], errors="coerce")
        return pd.DataFrame(), required.loc[months.between(start, end)].reset_index(drop=True)

    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", fake)
    return calls


def _loader(scenario_key: simulation_cache.ScenarioCacheKey) -> Callable[[], pd.DataFrame]:
    """페이지가 넘기는 것과 같은 소요대수 로더(표 묶음은 대역이 보지 않는 빈 묶음)."""
    return simulation_cache.scenario_required_equipment(
        scenario_key, scenario_tables=_NO_TABLES, reference_tables=_NO_TABLES
    )


@pytest.mark.parametrize("today", [ANCHOR, ANCHOR + timedelta(days=9)])
def test_shortening_shares_the_span_cache_and_matches_a_fresh_plan(
    today: date, monkeypatch: pytest.MonkeyPatch
) -> None:
    """필요단축일정은 Static/Dynamic 과 같은 구간 캐시를 쓰고, 결과는 캐시 없이 낸 계획과 같다.

    오늘은 계획 키에 들고(바닥 `max(구간 앞, 오늘)`), 구간 키에는 들지 않는다 — 구간은 오늘을 보지
    않는다. 그래서 오늘만 바뀐 두 번째 계획은 구간을 다시 만들지 않는다.
    """
    _clear_equipment_caches()
    equipment, downtime, baseline, cutoff = _fleet()
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    required = _required(processes, MONTHS)
    scenario_key: simulation_cache.ScenarioCacheKey = (1, "shortening", MONTHS[0], MONTHS[-1])
    _fake_demand(monkeypatch, {"shortening": required})
    start, end = _span_range(cutoff, MONTHS)
    built: list[object] = []

    def counting(*args: object, **kwargs: object) -> pd.DataFrame:
        built.append(kwargs.get("end_date"))
        return build_equipment_lifecycle_spans(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(simulation_cache, "build_equipment_lifecycle_spans", counting)

    def planned(day: date) -> tuple[simulation_cache.RequiredShorteningCacheKey, ShorteningPlan]:
        key = simulation_cache.required_shortening_cache_key(
            scenario_key,
            equipment=equipment,
            downtime=downtime,
            baseline=baseline,
            cutoff=cutoff,
            months=MONTHS,
            today=day,
        )
        plan = simulation_cache.get_required_shortening(
            key,
            equipment,
            downtime,
            baseline,
            cutoff,
            _required_equipment=_loader(scenario_key),
        )
        return key, plan

    yesterday_key, _ = planned(today - timedelta(days=1))
    key, plan = planned(today)
    fresh = plan_required_shortening(
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        required_equipment=required,
        months=MONTHS,
        today=today,
    )

    assert key != yesterday_key
    # 구간은 한 번만 만들었다 — 오늘만 다른 두 계획이 같은 구간을 나눴다.
    assert built == [end]
    for cached_frame, fresh_frame in zip(_plan_frames(plan), _plan_frames(fresh), strict=True):
        assert_frame_equal(cached_frame, fresh_frame)
    # Static/Dynamic 이 같은 범위를 보면 같은 키라 다시 만들지 않는다.
    _, shared = _cached_spans(equipment, downtime, start, end)
    assert built == [end]
    assert_frame_equal(shared, _fresh_spans(equipment, downtime, start, end))


def test_shortening_reads_the_demand_only_on_a_miss_and_follows_the_scenario_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """계획 캐시는 빗나갈 때만 키의 시나리오 키로 소요대수를 꺼낸다 — 적중 회차는 풀지 않는다.

    시나리오 키만 다른 계획(미저장 편집·리비전 전환이 content_token 을 바꾼 경우)은 새 소요대수로
    다시 세우고, 그 결과는 그 소요대수로 캐시 없이 낸 계획과 같다.
    """
    _clear_equipment_caches()
    equipment, downtime, baseline, cutoff = _fleet()
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    first = _required(processes, MONTHS)
    edited = first.assign(소요대수=9.0)
    calls = _fake_demand(monkeypatch, {"before-edit": first, "after-edit": edited})
    today = ANCHOR

    def planned(token: str) -> ShorteningPlan:
        scenario_key: simulation_cache.ScenarioCacheKey = (1, token, MONTHS[0], MONTHS[-1])
        key = simulation_cache.required_shortening_cache_key(
            scenario_key,
            equipment=equipment,
            downtime=downtime,
            baseline=baseline,
            cutoff=cutoff,
            months=MONTHS,
            today=today,
        )
        return simulation_cache.get_required_shortening(
            key,
            equipment,
            downtime,
            baseline,
            cutoff,
            _required_equipment=_loader(scenario_key),
        )

    def fresh(required: pd.DataFrame) -> ShorteningPlan:
        return plan_required_shortening(
            equipment=equipment,
            downtime=downtime,
            baseline=baseline,
            cutoff=cutoff,
            required_equipment=required,
            months=MONTHS,
            today=today,
        )

    before = planned("before-edit")
    assert [key[1] for key in calls] == ["before-edit"]
    again = planned("before-edit")
    assert [key[1] for key in calls] == ["before-edit"]
    after = planned("after-edit")
    assert [key[1] for key in calls] == ["before-edit", "after-edit"]

    for cached, expected in (
        (before, fresh(first)),
        (again, fresh(first)),
        (after, fresh(edited)),
    ):
        for cached_frame, fresh_frame in zip(
            _plan_frames(cached), _plan_frames(expected), strict=True
        ):
            assert_frame_equal(cached_frame, fresh_frame)
    # 소요대수가 달라 계획이 달라야 이 경우가 무엇을 증명한다.
    assert not _plan_frames(after)[1].equals(_plan_frames(before)[1])


# ------------------------------------------------------------------ 필요단축일정 달 범위(EQ-2)


def _frame_month_bounds(required: pd.DataFrame) -> tuple[int, int] | None:
    """소요대수 프레임에서 바로 잰 달 범위 — 필요단축일정이 고를 달을 정하는 식."""
    if not required.empty and "생산계획년월" in required.columns:
        present = pd.to_numeric(required["생산계획년월"], errors="coerce").dropna()
        if not present.empty:
            return int(present.min()), int(present.max())
    return None


@pytest.mark.parametrize(
    "required",
    [
        _required(["Die Attach", "Etch"], MONTHS),
        # 달이 빈 행·문자열 달이 섞여도 프레임에서 바로 잰 범위와 같다.
        pd.DataFrame(
            {"생산계획년월": ["202611", None, 202612], "공정": ["A", "A", "A"], "소요대수": 1.0}
        ),
        pd.DataFrame({"생산계획년월": [], "공정": [], "소요대수": []}),
        pd.DataFrame({"생산계획년월": [None], "공정": ["A"], "소요대수": [1.0]}),
    ],
    ids=["months", "mixed", "empty", "no-month"],
)
def test_required_month_span_matches_the_frame(
    required: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    """달 범위 캐시는 소요대수 프레임에서 바로 잰 범위와 같다(달이 없으면 `None`)."""
    simulation_cache.get_required_month_span.clear()

    def fake(
        cache_key: simulation_cache.ScenarioCacheKey, **_kwargs: object
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        return pd.DataFrame(), required

    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", fake)
    key: simulation_cache.ScenarioCacheKey = (1, "span-shape", 0, 999999)

    span = simulation_cache.get_required_month_span(key, _required_equipment=_loader(key))

    assert span == _frame_month_bounds(required)


def test_required_month_span_reads_the_demand_only_on_a_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """적중이면 소요대수를 풀지 않는다. content_token·조회기간이 바뀌면 새로 잰다."""
    simulation_cache.get_required_month_span.clear()
    later = _required(["Die Attach"], (202612, 202701, 202702))
    calls = _fake_demand(
        monkeypatch, {"span-a": _required(["Die Attach"], MONTHS), "span-b": later}
    )

    def span(token: str, start: int, end: int) -> tuple[int, int] | None:
        key: simulation_cache.ScenarioCacheKey = (1, token, start, end)
        return simulation_cache.get_required_month_span(key, _required_equipment=_loader(key))

    assert span("span-a", 202601, 202712) == (MONTHS[0], MONTHS[-1])
    assert span("span-a", 202601, 202712) == (MONTHS[0], MONTHS[-1])
    assert len(calls) == 1
    # 미저장 편집·리비전 전환은 새 content_token 이다.
    assert span("span-b", 202601, 202712) == (202612, 202702)
    # 조회기간이 바뀌면 그 기간으로 자른 소요대수의 범위다.
    assert span("span-b", 202701, 202712) == (202701, 202702)
    assert len(calls) == 3


def test_a_failed_demand_check_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """오류 확인(`check_scenario_capacity`)·달 범위는 실패를 캐시하지 않는다 — 같은 키라도 다음
    회차에 다시 계산해, DB 가 돌아오거나 일시 오류가 걷히면 풀린다."""
    simulation_cache.check_scenario_capacity.clear()
    simulation_cache.get_required_month_span.clear()
    required = _required(["Die Attach"], MONTHS)
    failures = [RuntimeError("일시 오류")]

    def flaky(
        cache_key: simulation_cache.ScenarioCacheKey, **_kwargs: object
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if failures:
            raise failures.pop()
        return pd.DataFrame(), required

    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", flaky)
    key: simulation_cache.ScenarioCacheKey = (1, "flaky", MONTHS[0], MONTHS[-1])
    with pytest.raises(RuntimeError):
        simulation_cache.check_scenario_capacity(
            key, _scenario_tables=_NO_TABLES, _reference_tables=_NO_TABLES
        )
    assert simulation_cache.check_scenario_capacity(
        key, _scenario_tables=_NO_TABLES, _reference_tables=_NO_TABLES
    )

    failures.append(RuntimeError("일시 오류"))
    with pytest.raises(RuntimeError):
        simulation_cache.get_required_month_span(key, _required_equipment=_loader(key))
    assert simulation_cache.get_required_month_span(key, _required_equipment=_loader(key)) == (
        MONTHS[0],
        MONTHS[-1],
    )

    # 로더로 확인해도 같다 — 실패한 로더를 다시 불러도 기억된 실패가 아니라 새로 꺼낸다.
    simulation_cache.check_scenario_capacity.clear()
    failures.append(RuntimeError("일시 오류"))
    load = _loader(key)
    with pytest.raises(RuntimeError):
        simulation_cache.check_scenario_capacity(
            key, _scenario_tables=_NO_TABLES, _reference_tables=_NO_TABLES, _required_equipment=load
        )
    assert simulation_cache.check_scenario_capacity(
        key, _scenario_tables=_NO_TABLES, _reference_tables=_NO_TABLES, _required_equipment=load
    )


def test_one_loader_reads_the_demand_once_with_the_tables_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """로더 하나는 소요대수를 한 번만 꺼내고, 키를 낸 바로 그 표 묶음을 넘긴다.

    한 회차에 오류 확인·달 범위·계획이 함께 빗나가도(첫 진입, 조회기간·토큰이 바뀐 회차) 언피클은
    한 번이다. 로더가 다르면(다음 회차) 다시 꺼낸다.
    """
    simulation_cache.check_scenario_capacity.clear()
    simulation_cache.get_required_month_span.clear()
    required = _required(["Die Attach"], MONTHS)
    scenario_tables: dict[str, pd.DataFrame] = {"RQ_PKG_PLAN": pd.DataFrame()}
    reference_tables: dict[str, pd.DataFrame] = {"RQ_EQP_AVBL": pd.DataFrame()}
    given: list[tuple[object, object]] = []

    def fake(
        cache_key: simulation_cache.ScenarioCacheKey,
        *,
        _scenario_tables: object,
        _reference_tables: object,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        given.append((_scenario_tables, _reference_tables))
        return pd.DataFrame(), required

    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", fake)
    key: simulation_cache.ScenarioCacheKey = (1, "one-loader", MONTHS[0], MONTHS[-1])
    load = simulation_cache.scenario_required_equipment(
        key, scenario_tables=scenario_tables, reference_tables=reference_tables
    )

    assert simulation_cache.check_scenario_capacity(
        key,
        _scenario_tables=scenario_tables,
        _reference_tables=reference_tables,
        _required_equipment=load,
    )
    assert simulation_cache.get_required_month_span(key, _required_equipment=load) == (
        MONTHS[0],
        MONTHS[-1],
    )
    assert load() is load()
    assert len(given) == 1
    assert given[0][0] is scenario_tables and given[0][1] is reference_tables

    again = simulation_cache.scenario_required_equipment(
        key, scenario_tables=scenario_tables, reference_tables=reference_tables
    )
    assert_frame_equal(again(), required)
    assert len(given) == 2


# ------------------------------------------------------------------ 확보율 교차검증(EQ-6)


def _same_check(cached: CrossCheck, fresh: CrossCheck) -> None:
    assert_frame_equal(cached.rows, fresh.rows)
    assert cached.months == fresh.months
    assert cached.fallback_processes == fresh.fallback_processes
    assert cached.dynamic_only_processes == fresh.dynamic_only_processes
    assert cached.compared_processes == fresh.compared_processes


@pytest.mark.parametrize("change", ["cutoff", "months", "static", "required", "spans"])
def test_cached_cross_check_follows_every_input(
    change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """교차검증 캐시는 월별(Cut-off·달·구간)·Static·소요대수(시나리오 키) 어느 것이 바뀌어도 다시
    맞댄다. 소요대수는 해시하지 않으므로 시나리오 키가 갈려야 한다 — 페이지는 그 키로 소요대수를
    받는다(`get_scenario_capacity_and_demand`)."""
    _clear_equipment_caches()
    simulation_cache.get_securement_cross_check.clear()
    equipment, downtime, baseline, cutoff = _fleet()
    start, end = _span_range(cutoff, MONTHS)
    spans = _fresh_spans(equipment, downtime, start, end)
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    static = _static(processes, MONTHS)
    required = _required(processes, MONTHS)
    ratios = _ratios(equipment)
    months: Sequence[int] = MONTHS
    scenario_key: simulation_cache.ScenarioCacheKey = (1, "cross-a", MONTHS[0], MONTHS[-1])

    def checked(
        spans: pd.DataFrame,
        cutoff: pd.DataFrame,
        static: pd.DataFrame,
        months: Sequence[int],
        required: pd.DataFrame,
        scenario_key: simulation_cache.ScenarioCacheKey,
    ) -> tuple[simulation_cache.SecurementCrossCheckCacheKey, CrossCheck, CrossCheck]:
        comparison_key, monthly, _ = _comparison(spans, baseline, cutoff, static, months, ratios)
        key = (comparison_key, scenario_key)

        def load() -> pd.DataFrame:
            loaded.append(scenario_key)
            return required

        cached = simulation_cache.get_securement_cross_check(
            key, _monthly=monthly, _static=static, _required_equipment=load
        )
        fresh_monthly = build_monthly_equipment_availability(
            spans, baseline, cutoff, months, conversion_ratios=ratios
        )
        fresh = cross_check_from_monthly(static, fresh_monthly, required)
        assert cached.has_demand and cached.check is not None
        return key, cached.check, fresh

    # 소요대수 로더를 부른 차례 — 캐시가 빗나간 회차에만 늘어야 한다.
    loaded: list[simulation_cache.ScenarioCacheKey] = []

    base_key, base, _ = checked(spans, cutoff, static, months, required, scenario_key)

    if change == "cutoff":
        cutoff = cutoff.copy()
        cutoff.loc[cutoff["공정"].eq("Die Attach"), "Cutoff일수"] = 20.0
    elif change == "months":
        months = MONTHS[:2]
    elif change == "static":
        static = _static(processes, MONTHS, count=4.0)
    elif change == "required":
        required = required.assign(소요대수=9.0)
        scenario_key = (1, "cross-b", MONTHS[0], MONTHS[-1])
    else:
        spans = _fresh_spans(_later_qual(equipment), downtime, start, end)
    built: list[object] = []

    def counting(*args: object, **kwargs: object) -> CrossCheck:
        built.append(args)
        return cross_check_from_monthly(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(simulation_cache, "cross_check_from_monthly", counting)
    key, cached, fresh = checked(spans, cutoff, static, months, required, scenario_key)

    assert key != base_key
    assert len(built) == 1
    assert len(loaded) == 2
    _same_check(cached, fresh)
    assert not fresh.rows.equals(base.rows)

    # 같은 키로 다시 부르면 맞대지 않고 소요대수도 풀지 않는다 — 그 보기를 열어 둔 rerun 이 이
    # 경로다.
    _, again, _ = checked(spans, cutoff, static, months, required, scenario_key)
    assert len(built) == 1
    assert len(loaded) == 2
    _same_check(again, fresh)


# ------------------------------------------------------------------ 비교 시트(9행)


def _static_tables(
    processes: Sequence[str], months: Sequence[int], owned: float = 5.0, lent: float = 1.0
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    def table(column: str, value: float) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"생산계획년월": month, "공정": process, column: value}
                for month in months
                for process in processes
            ]
        )

    return table("설비보유", owned), table("설비대여평가", lent), table("가용대수", owned - lent)


def _sheet(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    tables: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> tuple[simulation_cache.AvailabilitySheetCacheKey, AvailabilitySheet, AvailabilitySheet]:
    """페이지와 같은 길 — 구간 둘(실제·빈 비가동)을 구간 캐시로, 시트를 시트 캐시로. 새로 만든
    것도."""
    start, end = _span_range(cutoff, MONTHS)
    ratios = _ratios(equipment)
    _, spans = _cached_spans(equipment, downtime, start, end)
    free_key, free_spans = _cached_spans(equipment, downtime.iloc[0:0], start, end)
    owned, lent, available = tables
    comparison_key, monthly, _ = _comparison(spans, baseline, cutoff, available, MONTHS, ratios)
    free_monthly_key = simulation_cache.dynamic_monthly_cache_key(
        spans=free_spans, baseline=baseline, cutoff=cutoff, months=MONTHS, conversion_ratios=ratios
    )
    key = simulation_cache.availability_sheet_cache_key(
        comparison_key[0],
        free_monthly_key,
        static_owned=owned,
        static_lent=lent,
        static_available=available,
    )
    cached = simulation_cache.get_availability_sheet(
        key,
        _actual_monthly=monthly,
        _free_spans=free_spans,
        _baseline=baseline,
        _cutoff=cutoff,
        _conversion_ratios=ratios,
        _static_owned=owned,
        _static_lent=lent,
        _static_available=available,
    )
    fresh = build_availability_sheet(
        build_monthly_equipment_availability(
            _fresh_spans(equipment, downtime, start, end),
            baseline,
            cutoff,
            MONTHS,
            conversion_ratios=ratios,
        ),
        build_monthly_equipment_availability(
            _fresh_spans(equipment, downtime.iloc[0:0], start, end),
            baseline,
            cutoff,
            MONTHS,
            conversion_ratios=ratios,
        ),
        owned,
        lent,
        available,
        MONTHS,
    )
    return key, cached, fresh


@pytest.mark.parametrize("change", ["owned", "lent", "available", "downtime", "master"])
def test_cached_sheet_follows_every_input(change: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """시트 캐시는 Static 세 표(보유·대여·가용)와 실제·반사실 월별을 모두 키로 갈라낸다.

    비가동 한 줄을 지우면 실제 구간만 바뀌고 반사실(빈 비가동) 구간은 그대로다 — 키의 실제 월별
    키가 바뀌어 대여가 달라진다. 캐시를 거친 시트는 새로 만든 시트와 같다.
    """
    _clear_equipment_caches()
    equipment, downtime, baseline, cutoff = _fleet()
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    tables = _static_tables(processes, MONTHS)
    base_key, base, _ = _sheet(equipment, downtime, baseline, cutoff, tables)

    owned, lent, available = tables
    if change == "owned":
        tables = (owned.assign(설비보유=7.0), lent, available)
    elif change == "lent":
        tables = (owned, lent.assign(설비대여평가=2.0), available)
    elif change == "available":
        tables = (owned, lent, available.assign(가용대수=9.0))
    elif change == "downtime":
        downtime = downtime.iloc[1:].reset_index(drop=True)
    else:
        equipment = _later_qual(equipment)
    key, cached, fresh = _sheet(equipment, downtime, baseline, cutoff, tables)

    assert key != base_key
    assert_frame_equal(cached.rows, fresh.rows)
    assert not fresh.rows.equals(base.rows)
    if change == "downtime":
        assert key[1] == base_key[1]  # 반사실 월별 키는 비가동을 보지 않는다
        assert not fresh.rows[ROW_SCHEDULE_LENT].equals(base.rows[ROW_SCHEDULE_LENT])

    # 같은 키로 다시 부르면 만들지 않는다.
    built: list[object] = []

    def counting(*args: object, **kwargs: object) -> AvailabilitySheet:
        built.append(args)
        return fresh

    monkeypatch.setattr(simulation_cache, "build_availability_sheet", counting)
    _, again, _ = _sheet(equipment, downtime, baseline, cutoff, tables)
    assert built == []
    assert_frame_equal(again.rows, fresh.rows)


def test_a_sheet_without_a_counterfactual_is_its_own_entry() -> None:
    """반사실 키가 None 인 시트(「가용대수 비교」 그림)는 반사실이 있는 시트와 다른 항목이다."""
    _clear_equipment_caches()
    equipment, downtime, baseline, cutoff = _fleet()
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    owned, lent, available = _static_tables(processes, MONTHS)
    key, full, _ = _sheet(equipment, downtime, baseline, cutoff, (owned, lent, available))
    start, end = _span_range(cutoff, MONTHS)
    _, spans = _cached_spans(equipment, downtime, start, end)
    ratios = _ratios(equipment)
    _, monthly, _ = _comparison(spans, baseline, cutoff, available, MONTHS, ratios)
    bare_key = (key[0], None, key[2], key[3], key[4])
    bare = simulation_cache.get_availability_sheet(
        bare_key,
        _actual_monthly=monthly,
        _free_spans=None,
        _baseline=baseline,
        _cutoff=cutoff,
        _conversion_ratios=ratios,
        _static_owned=owned,
        _static_lent=lent,
        _static_available=available,
    )

    assert full.has_counterfactual and not bare.has_counterfactual
    assert bare.rows[ROW_SCHEDULE_LENT].isna().all()
    assert not full.rows[ROW_SCHEDULE_LENT].isna().any()
