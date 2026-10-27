# Purpose: 필요 단축 일정의 달마다 다른 목표가 스칼라 경로와 같고 달마다 맞게 걸림을 고정한다.

"""달마다 다른 목표(`MonthlyTarget`)와 그 캐시 래퍼.

공정 Capa 상세는 HOME → Preference 의 확보기준(기본값 + 월별 예외)을 달마다 단축 목표로 쓴다
(2026-10-15 사용자 결정). 계산은 탭의 다섯 값과 한 길이라 **모든 달이 같은 목표는 그 스칼라와 같은
결과**여야 하고, 탭의 다섯 값 계획은 달마다 다른 목표를 더해도 그대로여야 한다.

숫자 예 — Cut-off 10, 5월 구간 `(4/20, 5/21]`, 6월 구간 `(5/21, 6/20]`(30일). 기존보유 10대, 소요는
두 달 10대. Qual 6/10 인 A1 은 6/11 부터 6월에 `10/30` 대를 보탠다. 6월 목표만 110% 면 6월 목표대수
11 에 `20/30` 대가 모자라 A1 을 5/21 로 20일 당긴다 — 5월(100%)은 손대지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_equipment_view_cache import (
    ANCHOR,
    MONTHS,
    _clear_equipment_caches,
    _fake_demand,
    _fleet,
    _loader,
)
from test_equipment_view_cache import _required as _fleet_required
from test_required_shortening import (
    EARLY,
    JUNE,
    MAY,
    _baseline,
    _cutoff,
    _downtime,
    _master,
    _required,
    _unit,
)

from capa_simulation.services import simulation_cache
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.required_shortening import (
    LEVEL_COLUMN,
    STATUS_MET,
    STATUS_SHORTENED,
    TARGET_LEVELS,
    MonthlyTarget,
    ShorteningPlan,
    TargetLevel,
    plan_required_shortening,
    process_month_export_frame,
    target_from_thresholds,
    unit_export_frame,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

JULY = 202607


def _plan_with(
    levels: tuple[TargetLevel, ...],
    *,
    units: list[dict[str, Any]] | None = None,
    need: dict[int, float] | None = None,
    downtime: pd.DataFrame | None = None,
    baseline: float = 10.0,
) -> ShorteningPlan:
    need = need or {MAY: 10.0, JUNE: 10.0}
    return plan_required_shortening(
        equipment=_master(units if units is not None else [_unit("A1", date(2026, 6, 10))]),
        downtime=_downtime() if downtime is None else downtime,
        baseline=_baseline(baseline),
        cutoff=_cutoff(),
        required_equipment=_required(need),
        months=sorted(need),
        today=EARLY,
        levels=levels,
    )


def _mixed_fixture() -> tuple[list[dict[str, Any]], dict[int, float], pd.DataFrame]:
    """모듈 묶음·환산비·비가동·가상 호기가 섞인 경우(`test_required_shortening` 의 엔진 대조)."""
    rows: list[dict[str, Any]] = [
        _unit("OLD1", date(2026, 1, 10), arrival=date(2026, 1, 1)),
        _unit("U1", date(2026, 6, 15), ratio=1.5),
        _unit("M1", date(2026, 6, 10), ratio=0.5, parent="G9"),
        _unit("M2", date(2026, 7, 5), ratio=0.7, parent="G9"),
        _unit("U3", date(2026, 7, 20)),
    ]
    downtime = _downtime(
        [("U3", date(2026, 6, 1), date(2026, 6, 5)), ("U1", date(2026, 5, 10), date(2026, 5, 12))]
    )
    need = {MAY: 3.0, JUNE: 4.0, JULY: 5.0, 202608: 5.0}
    return rows, need, downtime


@pytest.mark.parametrize("level", TARGET_LEVELS)
def test_a_target_equal_in_every_month_gives_the_scalar_plan(level: float) -> None:
    """모든 달이 같은 목표는 그 스칼라와 공정·월 표와 호기 표가 바이트까지 같다.

    `MonthlyTarget` 은 기본값과 같은 예외를 지우므로 달마다 같은 값을 적어도 기본값 하나와 같다.
    """
    rows, need, downtime = _mixed_fixture()
    uniform = MonthlyTarget(level, tuple((month, level) for month in need))
    assert uniform == MonthlyTarget(level)

    scalar = _plan_with((level,), units=rows, need=need, downtime=downtime, baseline=0.0)
    monthly = _plan_with((uniform,), units=rows, need=need, downtime=downtime, baseline=0.0)

    assert_frame_equal(monthly.at(uniform).process_months, scalar.at(level).process_months)
    assert_frame_equal(monthly.at(uniform).units, scalar.at(level).units)
    assert monthly.at(uniform).level == level
    assert monthly.at(uniform).target == uniform
    assert scalar.at(level).target == level


def test_the_five_levels_do_not_change_when_a_monthly_target_rides_along() -> None:
    """탭의 다섯 값 결과는 달마다 다른 목표를 함께 계산해도 그대로다(목표끼리 따로 계산한다)."""
    rows, need, downtime = _mixed_fixture()
    target = MonthlyTarget(1.0, ((JUNE, 1.2), (JULY, 0.9)))

    alone = _plan_with(TARGET_LEVELS, units=rows, need=need, downtime=downtime, baseline=0.0)
    together = _plan_with(
        (*TARGET_LEVELS, target), units=rows, need=need, downtime=downtime, baseline=0.0
    )

    for level in TARGET_LEVELS:
        assert_frame_equal(together.at(level).process_months, alone.at(level).process_months)
        assert_frame_equal(together.at(level).units, alone.at(level).units)
    assert together.at(target).monthly_target == target
    # 스칼라로는 달마다 다른 계획을 꺼낼 수 없다 — 기본값이 같아도 다른 계획이다.
    assert together.at(1.0).monthly_target is None


def test_each_month_is_judged_against_its_own_target() -> None:
    """5월 100%·6월 110% — 6월만 모자라 A1 을 20일 당기고, 5월은 충족이다."""
    target = MonthlyTarget(1.0, ((JUNE, 1.1),))
    level = _plan_with((target,)).at(target)
    months = level.process_months.set_index("생산계획년월")

    assert months.loc[MAY, "목표대수"] == pytest.approx(10.0)
    assert months.loc[JUNE, "목표대수"] == pytest.approx(11.0)
    assert months.loc[MAY, "상태"] == STATUS_MET
    assert months.loc[JUNE, "상태"] == STATUS_SHORTENED
    assert months.loc[JUNE, "과부족"] == pytest.approx(10 + 10 / 30 - 11)
    assert months.loc[JUNE, "단축후과부족"] == pytest.approx(0.0)
    assert level.target_for(MAY) == 1.0
    assert level.target_for(JUNE) == 1.1

    units = level.units.set_index("호기")
    assert units.loc["A1", "목표 Qual"] == date(2026, 5, 21)
    assert units.loc["A1", "단축일수"] == 20
    assert units.loc["A1", "대상 월"] == JUNE

    # 5월이 손대지 않은 달이면 6월은 6월만 110% 로 계산한 것과 같다.
    june_only = _plan_with((1.1,), need={JUNE: 10.0}).at(1.1)
    assert_frame_equal(level.units.reset_index(drop=True), june_only.units.reset_index(drop=True))
    with pytest.raises(KeyError):
        _plan_with((target,)).at(1.0)


def test_a_higher_later_target_pulls_more_than_the_default_would() -> None:
    """같은 소요에서 뒤 달 목표만 올리면 그 달 목표대수가 커지고, 앞 달은 기본값 계획과 같다."""
    rows, need, downtime = _mixed_fixture()
    default_only = _plan_with((1.0,), units=rows, need=need, downtime=downtime, baseline=0.0)
    raised = MonthlyTarget(1.0, ((202608, 1.3),))
    plan = _plan_with((raised,), units=rows, need=need, downtime=downtime, baseline=0.0)

    before = default_only.at(1.0).process_months.set_index("생산계획년월")
    after = plan.at(raised).process_months.set_index("생산계획년월")
    assert_frame_equal(after.loc[[MAY, JUNE, JULY]], before.loc[[MAY, JUNE, JULY]])
    assert after.loc[202608, "목표대수"] == pytest.approx(5.0 * 1.3)
    assert (after["단축후과부족"].loc[[202608]] >= -1e-9).all()


def test_target_from_thresholds_takes_the_secure_threshold_of_each_month_in_range() -> None:
    """확보 기준만 본다 — 경고만 적은 달·기간 밖 예외는 목표를 가르지 않는다."""
    thresholds = SecurementThresholds(
        default_secure=1.095,
        default_warning=0.995,
        monthly=((MAY, 1.2, None), (JUNE, None, 0.9), (202612, 1.3, None)),
    )

    target = target_from_thresholds(thresholds, [JUNE, MAY, JULY])

    assert target == MonthlyTarget(1.095, ((MAY, 1.2),))
    assert [target.for_month(month) for month in (MAY, JUNE, JULY)] == [1.2, 1.095, 1.095]
    assert target.for_month(202612) == 1.095


def test_a_monthly_target_is_a_normalized_hashable_value() -> None:
    """같은 목표면 같은 값·같은 해시다 — 예외는 달 차례로 두고 기본값과 같은 달은 지운다."""
    first = MonthlyTarget(1.1, ((JUNE, 1.2), (MAY, 1.1), (JULY, 1.0)))
    second = MonthlyTarget(1.1, ((JULY, 1.0), (JUNE, 1.2)))

    assert first == second
    assert first.monthly == ((JUNE, 1.2), (JULY, 1.0))
    assert len({first, second}) == 1
    with pytest.raises(ValueError, match="두 번"):
        MonthlyTarget(1.1, ((MAY, 1.2), (MAY, 1.3)))


def test_the_exports_carry_each_rows_own_target_percent() -> None:
    """CSV 의 목표 칸은 줄의 달의 목표다 — 공정·월은 그 달, 호기는 대상 월(6월 110%)."""
    target = MonthlyTarget(1.0, ((JUNE, 1.1),))
    plan = _plan_with((target,))

    units = unit_export_frame(plan, (target,))
    months = process_month_export_frame(plan, (target,))

    assert list(units[LEVEL_COLUMN]) == [110]
    assert list(units["대상 월"]) == ["2026-06"]
    assert list(zip(months["생산계획년월"], months[LEVEL_COLUMN], strict=True)) == [
        (MAY, 100),
        (JUNE, 110),
    ]
    assert str(months[LEVEL_COLUMN].dtype) == "int64"


# ---------------------------------------------------------------------- 캐시 래퍼


def _target_plan(
    scenario_key: simulation_cache.ScenarioCacheKey,
    target: MonthlyTarget,
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> tuple[simulation_cache.RequiredShorteningTargetCacheKey, ShorteningPlan]:
    """한 회차 — 페이지처럼 회차마다 로더를 새로 만든다(로더는 한 회차 안에서만 기억한다)."""
    equipment, downtime, baseline, cutoff = frames
    loader: Callable[[], pd.DataFrame] = _loader(scenario_key)
    shortening_key = simulation_cache.required_shortening_cache_key(
        scenario_key,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        months=MONTHS,
        today=ANCHOR,
        manual_downtime=ManualDowntime(),
    )
    key = simulation_cache.required_shortening_target_cache_key(shortening_key, target)
    plan = simulation_cache.get_required_shortening_for_target(
        key, equipment, downtime, baseline, cutoff, _required_equipment=loader
    )
    return key, plan


def test_the_target_plan_cache_extends_the_tab_key_and_matches_a_fresh_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """목표 계획 키는 탭의 계획 키에 목표를 더한 것이다 — 목표가 바뀌면 새로 세우고 같으면 적중.

    결과는 캐시 없이 같은 목표로 낸 계획과 같다. 구간은 탭과 같은 구간 캐시에서 받는다.
    """
    _clear_equipment_caches()
    simulation_cache.get_required_shortening_for_target.clear()
    frames = _fleet()
    equipment, downtime, baseline, cutoff = frames
    processes = sorted(set(equipment["공정소분류"].astype(str)))
    required = _fleet_required(processes, MONTHS)
    scenario_key: simulation_cache.ScenarioCacheKey = (1, "target", MONTHS[0], MONTHS[-1])
    calls = _fake_demand(monkeypatch, {"target": required})

    base = MonthlyTarget(1.095)
    raised = MonthlyTarget(1.095, ((MONTHS[-1], 1.2),))
    key, plan = _target_plan(scenario_key, base, frames)
    again_key, again = _target_plan(scenario_key, base, frames)
    other_key, other = _target_plan(scenario_key, raised, frames)

    tab_key = simulation_cache.required_shortening_cache_key(
        scenario_key,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        months=MONTHS,
        today=ANCHOR,
        manual_downtime=ManualDowntime(),
    )
    assert key[0] == tab_key
    assert again_key == key
    assert other_key != key
    assert len(calls) == 2  # 적중한 회차는 소요대수를 풀지 않았다.
    for cached, target in ((plan, base), (again, base), (other, raised)):
        fresh = plan_required_shortening(
            equipment=equipment,
            downtime=downtime,
            baseline=baseline,
            cutoff=cutoff,
            required_equipment=required,
            months=MONTHS,
            today=ANCHOR,
            levels=(target,),
        )
        assert_frame_equal(cached.at(target).process_months, fresh.at(target).process_months)
        assert_frame_equal(cached.at(target).units, fresh.at(target).units)
    targets = other.at(raised).process_months.groupby("생산계획년월")["목표대수"].sum()
    needs = other.at(raised).process_months.groupby("생산계획년월")["소요대수"].sum()
    assert targets[MONTHS[-1]] == pytest.approx(needs[MONTHS[-1]] * 1.2)
    assert targets[MONTHS[0]] == pytest.approx(needs[MONTHS[0]] * 1.095)
