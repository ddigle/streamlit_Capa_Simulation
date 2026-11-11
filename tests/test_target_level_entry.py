# Purpose: 목표 확보율 직접 입력의 받는 값 · 거부와 다섯 밖 목표 하나 계산 길을 고정한다.

"""목표 확보율 직접 입력(2026-11-11 사용자 고칠 것 Q2-26 「목표 확보율 5개 프리셋 외에 직접 입력도
가능하도록 수정」).

- **받는 값** — 판정 기준 칸과 한 범위 · 걸음 · 자릿수(50 ~ 300%, 1, 정수 % 사사오입). 범위 밖 ·
  빈 칸 · 숫자 아님은 거부 글이다(`read_level_entry`). 세션 칸 · 주소 인자(`target_level`)도 같은
  범위로 읽는다. 범위를 한참 넘는 값(1e30)은 사사오입 전에 거른다 — 멈추지 않는다.
- **계산** — 다섯 밖 값은 목표 하나 칸(`get_required_shortening_for_target` — 값이 키에 든다)에서 그
  값 하나만 계산해 다섯 값 계획에 스칼라로 더한다(`load_required_shortening(level=)`). 다섯 가운데
  하나를 그 길로 계산해도 미리 계산한 것과 같다.
- **기준선** — 직접 넣은 목표는 얼리지 않는다(다섯 그대로).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
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

from capa_simulation.components import home_preference
from capa_simulation.components.target_level_field import (
    ENTRY_EMPTY,
    ENTRY_FORMAT,
    ENTRY_NOT_A_NUMBER,
    ENTRY_STEP,
    entry_out_of_range,
    level_text,
    read_level_entry,
    target_level,
)
from capa_simulation.services import simulation_cache
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.required_shortening import (
    LEVEL_COLUMN,
    TARGET_LEVELS,
    LevelPlan,
    MonthlyTarget,
    ShorteningPlan,
    plan_required_shortening,
    plan_with_level,
    target_preset,
)
from capa_simulation.services.shortening_baseline import ShorteningBaseline, baseline_units_frame

Frames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]


# ---------------------------------------------------------------------- 받는 값


def test_the_entry_follows_the_threshold_fields_step_format_and_range() -> None:
    """걸음 · 꼴은 HOME 설정 › 판정 기준 기본 칸과 같고, 받는 범위는 판정 기준 저장 · 제약 확보율과
    한 값(50 ~ 300%)이다 — 새로 짓지 않는다."""
    assert ENTRY_STEP == home_preference.DEFAULT_THRESHOLD_STEP
    assert ENTRY_FORMAT == home_preference.DEFAULT_THRESHOLD_FORMAT
    assert read_level_entry(50) == 0.5 and read_level_entry(300) == 3.0
    assert read_level_entry(49) == entry_out_of_range(49)
    assert read_level_entry(301) == entry_out_of_range(301)
    assert entry_out_of_range(400) == "50% ~ 300% 밖이라 받지 않았습니다 — 400%."
    assert entry_out_of_range(1e30) == "50% ~ 300% 밖이라 받지 않았습니다 — 1e+30%."


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        (115, 1.15),
        (115.0, 1.15),
        ("115%", 1.15),
        (110, 1.1),
        # 소수는 사사오입한 정수 % 다(판정 기준 칸과 한 규칙 — 109.5 → 110, 108.5 → 109).
        (109.5, 1.1),
        (108.5, 1.09),
        (49.5, 0.5),
        (300.4, 3.0),
        (400, entry_out_of_range(400)),
        (49.4, entry_out_of_range(49)),
        (300.5, entry_out_of_range(301)),
        # 받는 범위를 한참 넘는 값은 사사오입(`Decimal.quantize` — 28 자리) 전에 거부다.
        (1e30, entry_out_of_range(1e30)),
        ("1e30", entry_out_of_range(1e30)),
        ("1e300", entry_out_of_range(1e300)),
        # 숫자 칸이 비면(지우기 · ⊗) 빈 칸 거부다 — 숫자 아님은 칸 밖에서 넘어온 값뿐이다.
        (None, ENTRY_EMPTY),
        ("  ", ENTRY_EMPTY),
        ("목표", ENTRY_NOT_A_NUMBER),
        (float("nan"), ENTRY_NOT_A_NUMBER),
        (True, ENTRY_NOT_A_NUMBER),
    ],
)
def test_a_typed_percent_is_a_target_or_a_refusal(typed: object, expected: float | str) -> None:
    got = read_level_entry(typed)
    if isinstance(expected, str):
        assert got == expected
    else:
        assert isinstance(got, float) and got == pytest.approx(expected)


def test_a_typed_preset_is_the_same_float_as_the_radio_option() -> None:
    """다섯 가운데 하나를 치면 라디오 선택지와 같은 float 이다 — 미리 계산한 결과를 그대로
    꺼낸다."""
    for level in TARGET_LEVELS:
        typed = read_level_entry(level * 100)
        assert typed is level or typed == level
        assert target_preset(float(typed)) == level


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (1.1, 1.1),
        ("1.1", 1.1),
        (1.15, 1.15),
        ("1.15", 1.15),
        (0.75, 0.75),
        # 주소 · 세션의 비율도 정수 % 로 읽는다(1.153 → 115%).
        (1.153, 1.15),
        (3.0, 3.0),
        (0.3, None),
        (3.01, None),
        # 범위를 한참 넘는 주소 인자는 사사오입 전에 None 이다(`target=1e30`).
        (1e30, None),
        ("1e30", None),
        ("1e300", None),
        ("목표", None),
        (None, None),
        (float("nan"), None),
        (True, None),
    ],
)
def test_a_stored_or_linked_target_is_read_within_the_same_range(
    stored: object, expected: float | None
) -> None:
    got = target_level(stored)
    assert got == (None if expected is None else pytest.approx(expected))


def test_the_value_text_reads_a_typed_target_like_the_five() -> None:
    assert level_text(1.15) == "115%"
    assert level_text(1.1) == "110%"
    assert level_text(0.75) == "75%"


# ---------------------------------------------------------------------- 계산


def _keys(frames: Frames) -> tuple[simulation_cache.RequiredShorteningCacheKey, Any]:
    equipment, downtime, baseline, cutoff = frames
    scenario_key: simulation_cache.ScenarioCacheKey = (1, "typed", MONTHS[0], MONTHS[-1])
    key = simulation_cache.required_shortening_cache_key(
        scenario_key,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        months=MONTHS,
        today=ANCHOR,
        manual_downtime=ManualDowntime(),
    )
    return key, scenario_key


def _load(
    key: simulation_cache.RequiredShorteningCacheKey,
    scenario_key: simulation_cache.ScenarioCacheKey,
    frames: Frames,
    level: float | None,
) -> ShorteningPlan:
    """한 회차 — 페이지처럼 회차마다 로더를 새로 만든다."""
    equipment, downtime, baseline, cutoff = frames
    loader: Callable[[], pd.DataFrame] = _loader(scenario_key)
    keyed = simulation_cache.load_required_shortening(
        key, equipment, downtime, baseline, cutoff, required_equipment=loader, level=level
    )
    assert keyed.key == key
    return keyed.plan


@pytest.fixture
def typed_world(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Frames, pd.DataFrame, list[Any]]]:
    """샘플 fleet 과 공정마다 달마다 소요 10대 — 다섯 가운데 넷과 115% 에 당길 호기가 있다(샘플
    관측 — 100% 2대 · 110% 8대 · 115% 11대). 시험이 목표 하나 칸을 갈아 끼워도 비우도록 원래 칸의
    `clear` 를 쥔다."""
    clear_target = simulation_cache.get_required_shortening_for_target.clear
    _clear_equipment_caches()
    clear_target()
    frames = _fleet()
    processes = sorted(set(frames[0]["공정소분류"].astype(str)))
    required = _fleet_required(processes, MONTHS).assign(소요대수=10.0)
    calls = _fake_demand(monkeypatch, {"typed": required})
    yield frames, required, calls
    _clear_equipment_caches()
    clear_target()


def test_each_of_the_five_through_the_one_value_path_equals_the_precomputed_plan(
    typed_world: tuple[Frames, pd.DataFrame, list[Any]],
) -> None:
    """다섯 가운데 하나를 직접 입력의 길(목표 하나 칸 — 모든 달이 같은 목표)로 계산해도 미리 계산한
    다섯 값 계획과 공정·월 표 · 호기 표가 바이트까지 같다. 그래서 더한 스칼라 계획을 다섯과 같은
    길로 꺼내도 숫자가 갈리지 않는다."""
    frames, _, _ = typed_world
    equipment, downtime, baseline, cutoff = frames
    key, scenario_key = _keys(frames)
    five = _load(key, scenario_key, frames, None)
    pulled = 0
    for level in TARGET_LEVELS:
        single = simulation_cache.get_required_shortening_for_target(
            simulation_cache.required_shortening_target_cache_key(key, MonthlyTarget(level)),
            equipment,
            downtime,
            baseline,
            cutoff,
            _required_equipment=_loader(scenario_key),
        )
        (one,) = single.levels
        assert_frame_equal(one.process_months, five.at(level).process_months)
        assert_frame_equal(one.units, five.at(level).units)
        pulled += len(one.units)
        # 이미 든 목표면 더하지 않는다 — 다섯 값 계획 그대로다.
        assert plan_with_level(five, single) is five
    assert pulled > 0, "다섯 가운데 당길 호기가 있는 목표가 있어야 뜻이 있다"


def test_a_typed_target_is_planned_once_by_its_own_key_and_rides_on_the_five(
    typed_world: tuple[Frames, pd.DataFrame, list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """다섯 밖 값(115%)은 목표 하나 칸을 그 값이 든 키로 그때 부른다 — 같은 값이면 적중이고 다섯
    안의 값 · 없음이면 부르지 않는다. 더한 계획의 그 목표는 캐시 없이 낸 스칼라 계획과 같고 다섯은
    그대로다."""
    frames, required, calls = typed_world
    equipment, downtime, baseline, cutoff = frames
    key, scenario_key = _keys(frames)
    seen: list[simulation_cache.RequiredShorteningTargetCacheKey] = []
    wrapped = simulation_cache.get_required_shortening_for_target

    def counted(cache_key: Any, *args: Any, **kwargs: Any) -> ShorteningPlan:
        seen.append(cache_key)
        return wrapped(cache_key, *args, **kwargs)

    monkeypatch.setattr(simulation_cache, "get_required_shortening_for_target", counted)

    five = _load(key, scenario_key, frames, None)
    preset = _load(key, scenario_key, frames, 1.1)
    assert [plan.level for plan in preset.levels] == list(TARGET_LEVELS)
    assert seen == []

    typed = _load(key, scenario_key, frames, 1.15)
    again = _load(key, scenario_key, frames, 1.15)
    assert seen == [(key, 1.15, ()), (key, 1.15, ())]
    # 소요대수는 다섯 값 계획과 115% 계획이 빗나간 두 번만 풀었다 — 다시 부른 회차는 적중이다.
    assert len(calls) == 2
    assert [plan.level for plan in typed.levels] == [*TARGET_LEVELS, 1.15]
    assert typed.at(1.15).monthly_target is None
    fresh = plan_required_shortening(
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        required_equipment=required,
        months=MONTHS,
        today=ANCHOR,
        levels=(1.15,),
    )
    for plan in (typed, again):
        assert_frame_equal(plan.at(1.15).process_months, fresh.at(1.15).process_months)
        assert_frame_equal(plan.at(1.15).units, fresh.at(1.15).units)
        for level in TARGET_LEVELS:
            assert_frame_equal(plan.at(level).units, five.at(level).units)
            assert_frame_equal(plan.at(level).process_months, five.at(level).process_months)
    assert not typed.at(1.15).units.empty
    targets = typed.at(1.15).process_months
    assert targets["목표대수"].sum() == pytest.approx(targets["소요대수"].sum() * 1.15)


def test_a_plan_from_other_inputs_is_not_added() -> None:
    """같은 입력으로 세운 계획이 아니거나(달 · 오늘 · 공정) 달마다 다른 목표 · 목표 여럿이면 더하지
    않는다."""
    base = ShorteningPlan(
        months=(202610,),
        today=date(2026, 10, 1),
        processes=("P",),
        cutoff_days={"P": 10},
        levels=(),
    )
    one = LevelPlan(1.15, pd.DataFrame(), pd.DataFrame(), monthly_target=MonthlyTarget(1.15))
    with pytest.raises(ValueError, match="같은 입력"):
        plan_with_level(base, replace(base, today=date(2026, 10, 2), levels=(one,)))
    with pytest.raises(ValueError, match="같은 입력"):
        plan_with_level(base, replace(base, processes=("Q",), levels=(one,)))
    monthly = LevelPlan(
        1.15,
        pd.DataFrame(),
        pd.DataFrame(),
        monthly_target=MonthlyTarget(1.15, ((202610, 1.2),)),
    )
    with pytest.raises(ValueError, match="달마다"):
        plan_with_level(base, replace(base, levels=(monthly,)))
    with pytest.raises(ValueError, match="하나여야"):
        plan_with_level(base, replace(base, levels=(one, one)))
    added = plan_with_level(base, replace(base, levels=(one,)))
    assert added.at(1.15).monthly_target is None and added.covers(1.15)
    assert not base.covers(1.15)


# ---------------------------------------------------------------------- 기준선


def test_a_baseline_freezes_the_five_even_when_a_typed_target_rides_along(
    typed_world: tuple[Frames, pd.DataFrame, list[Any]],
) -> None:
    """직접 넣은 목표를 더한 계획을 얼려도 기준선은 다섯 목표 그대로다 — 그 목표로는 견주지
    않는다."""
    frames, _, _ = typed_world
    key, scenario_key = _keys(frames)
    five = _load(key, scenario_key, frames, None)
    typed = _load(key, scenario_key, frames, 1.15)
    assert not typed.at(1.15).units.empty

    frozen = baseline_units_frame(typed)
    assert_frame_equal(frozen, baseline_units_frame(five))
    assert set(frozen[LEVEL_COLUMN].astype(int)) <= {90, 100, 110, 120, 130}
    assert ShorteningBaseline.has_level(1.1)
    assert not ShorteningBaseline.has_level(1.15)
