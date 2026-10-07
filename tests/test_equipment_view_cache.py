# Purpose: 가용설비 현황 캐시 래퍼가 키로 적중하고 캐시 없이 새로 계산한 결과와 같은지 고정한다.

"""가용설비 현황 캐시 래퍼(`services/simulation_cache.py`).

래퍼는 프레임을 해시하지 않고 키만 본다(`_` 인자). 그래서 **키에서 입력을 하나라도 빠뜨리면 낡은
값이 나온다.** 여기서는 입력을 하나씩 바꿔 가며 (1) 키가 바뀌는지, (2) 캐시를 거친 결과가 캐시 없이
새로 계산한 결과와 같은지를 본다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_required_shortening import MAY, PROCESS, _worked_example

from capa_simulation.services import simulation_cache
from capa_simulation.services.availability_gap import GapComparison, build_availability_gap
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
    """샘플 fleet(호기 마스터·비가동·기존보유)과 그 공정 전부에 Cut-off 10일."""
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
            key, equipment, downtime, baseline, cutoff, required
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
