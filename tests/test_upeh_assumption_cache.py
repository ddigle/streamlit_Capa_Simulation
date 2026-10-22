# Purpose: 가정 계획이 공식 계획·HOME 확보율 캐시를 더럽히지 않고 짝 어긋남을 막는지 본다.

"""UPEH 가정과 계산 캐시(`simulation_cache`).

`st.cache_data` 는 프로세스 전역이라, 가정 결과가 공식 칸(모두가 보는 계획·CSV·진척, HOME 확보율)에
한 번만 들어가도 다른 사용자 화면에 가정 숫자가 보인다. 그래서 본다.

- 배수는 **키 안의 토큰에서만** 나온다 — 가정 칸은 원 로더를 받고 안에서 ÷f 를 건다.
- 공식 칸은 가정 키를, 가정 칸은 공식 키를 받지 않는다. CSV·진척 캐시는 받은 키와 계획 묶음의 키가
  다르면 멈춘다(짝 어긋남 회귀). 진척 비교는 공식 계획만 받는다.
- 가정 계획·CSV 를 한 번 돌린 뒤에도 같은 공식 키의 결과와 HOME 확보율(`get_securement_rate`)이 공식
  그대로다.
- 가정 칸도 키가 같으면 다시 계산하지 않는다(목표만 바꾼 회차).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any, cast

import pandas as pd
import pytest
from test_required_shortening import PROCESS, _baseline, _cutoff, _downtime, _master, _unit

import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.services.required_shortening import plan_required_shortening
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.upeh_assumption import UpehToken, scale_required_equipment

MAY, JUNE = 202605, 202606
SCENARIO_KEY: simulation_cache.ScenarioCacheKey = (1, "upeh-cache", MAY, JUNE)
TODAY = date(2026, 4, 1)
TOKEN: UpehToken = (130, (MAY, JUNE))


@pytest.fixture(autouse=True)
def _clear_caches() -> Iterator[None]:
    for wrapper in (
        simulation_cache.get_required_shortening,
        simulation_cache.get_assumed_required_shortening,
        simulation_cache.get_required_shortening_csvs,
        simulation_cache.get_shortening_progress,
        simulation_cache.get_securement_rate,
        simulation_cache.get_required_shortening_for_target,
        simulation_cache.get_assumed_required_shortening_for_target,
        simulation_cache.get_equipment_lifecycle_spans,
    ):
        wrapper.clear()
    yield


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    equipment = _master(
        [
            _unit("A1", date(2026, 5, 10)),
            _unit("B2", date(2026, 5, 31)),
            _unit("C3", date(2026, 6, 20)),
        ]
    )
    required = pd.DataFrame(
        {
            "생산계획년월": [MAY, MAY, JUNE, JUNE],
            "공정": [PROCESS] * 4,
            "STEP": ["S1", "S2", "S1", "S2"],
            "소요대수": [6.5, 6.5, 6.8, 6.8],
        }
    )
    return equipment, _downtime(), _baseline(10.0), _cutoff(), required


def _key(token: UpehToken = ()) -> simulation_cache.RequiredShorteningCacheKey:
    equipment, downtime, baseline, cutoff, _ = _inputs()
    return simulation_cache.required_shortening_cache_key(
        SCENARIO_KEY,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        months=(MAY, JUNE),
        today=TODAY,
        upeh=token,
    )


class _Loader:
    """원 로더 대역 — 몇 번 불렸는지 세고, 늘 같은 프레임 객체를 돌려준다."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls = 0

    def __call__(self) -> pd.DataFrame:
        self.calls += 1
        return self.frame


def _load(
    key: simulation_cache.RequiredShorteningCacheKey, loader: _Loader
) -> simulation_cache.KeyedShorteningPlan:
    equipment, downtime, baseline, cutoff, _ = _inputs()
    return simulation_cache.load_required_shortening(
        key, equipment, downtime, baseline, cutoff, required_equipment=loader
    )


def _direct(required: pd.DataFrame) -> pd.DataFrame:
    equipment, downtime, baseline, cutoff, _ = _inputs()
    plan = plan_required_shortening(
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        required_equipment=required,
        months=(MAY, JUNE),
        today=TODAY,
    )
    return plan.at(1.1).process_months


def test_the_token_is_the_last_key_cell_and_the_timeline_key_ignores_it() -> None:
    official, assumed = _key(), _key(TOKEN)
    assert official[:7] == assumed[:7]
    assert simulation_cache.shortening_key_token(official) == ()
    assert simulation_cache.shortening_key_token(assumed) == TOKEN
    assert simulation_cache.with_upeh_token(official, TOKEN) == assumed
    assert simulation_cache.process_timeline_key_from_shortening(
        official, PROCESS
    ) == simulation_cache.process_timeline_key_from_shortening(assumed, PROCESS)


def test_the_assumed_plan_scales_demand_from_the_key_token_only() -> None:
    """가정 칸은 원 로더를 받는다 — ÷f 는 키의 토큰으로 안에서 건다. 결과 = ÷f 프레임으로 직접 세운
    계획."""
    *_, required = _inputs()
    loader = _Loader(required)
    before = required.copy()
    assumed = _load(_key(TOKEN), loader)
    pd.testing.assert_frame_equal(
        assumed.plan.at(1.1).process_months, _direct(scale_required_equipment(required, TOKEN))
    )
    # 원 로더의 프레임은 고치지 않는다(같은 회차의 다른 쓰임이 같은 객체를 받는다).
    pd.testing.assert_frame_equal(required, before)
    assert assumed.key == _key(TOKEN)
    # 130% 면 소요가 줄어 단축 전 부족이 작아진다(이 표본에서는 부족이 남는다 — 정수 단계).
    official = _load(_key(), _Loader(required))
    assert (
        assumed.plan.at(1.1).process_months["과부족"].min()
        > official.plan.at(1.1).process_months["과부족"].min()
    )


def test_running_the_assumed_plan_and_csvs_leaves_the_official_cells_and_home_rate_alone() -> None:
    """HOME 오염 회귀 — 가정 계획·CSV 를 돌린 뒤 같은 공식 키로 꺼낸 결과·HOME 확보율이 공식
    그대로다."""
    *_, required = _inputs()
    available = pd.DataFrame(
        {"생산계획년월": [MAY, JUNE], "공정": [PROCESS] * 2, "가용대수": [10.0, 10.0]}
    )
    home_before = simulation_cache.get_securement_rate(SCENARIO_KEY, available, required).copy()
    official_before = _load(_key(), _Loader(required))
    csv_before = simulation_cache.shortening_csvs(official_before, 1.1, (PROCESS,), (MAY, JUNE))

    assumed = _load(_key(TOKEN), _Loader(required))
    assumed_csv = simulation_cache.shortening_csvs(assumed, 1.1, (PROCESS,), (MAY, JUNE))

    official_after = _load(_key(), _Loader(required))
    pd.testing.assert_frame_equal(official_after.plan.at(1.1).process_months, _direct(required))
    pd.testing.assert_frame_equal(
        official_after.plan.at(1.1).units, official_before.plan.at(1.1).units
    )
    assert simulation_cache.shortening_csvs(official_after, 1.1, (PROCESS,), (MAY, JUNE)) == (
        csv_before
    )
    home_after = simulation_cache.get_securement_rate(SCENARIO_KEY, available, required)
    pd.testing.assert_frame_equal(home_after, home_before)
    pd.testing.assert_frame_equal(home_after, calculate_securement_rate(available, required))
    # 가정 CSV 는 첫 열에 표지를 단다 — 공식 CSV 에는 없다.
    assert assumed_csv[0].decode("utf-8-sig").startswith("UPEH 가정,")
    assert "UPEH 가정 130% · 26-05–26-06" in assumed_csv[0].decode("utf-8-sig")
    assert not csv_before[0].decode("utf-8-sig").startswith("UPEH 가정")


def test_mismatched_keys_and_plans_are_refused() -> None:
    """짝 어긋남 회귀 — 공식 칸에 가정 키, 가정 칸에 공식 키, 키와 다른 계획 묶음은 멈춘다."""
    equipment, downtime, baseline, cutoff, required = _inputs()
    loader = _Loader(required)
    official = _load(_key(), loader)
    assumed = _load(_key(TOKEN), loader)
    with pytest.raises(ValueError, match="공식 계획 칸"):
        simulation_cache.get_required_shortening(
            _key(TOKEN), equipment, downtime, baseline, cutoff, _required_equipment=loader
        )
    with pytest.raises(ValueError, match="가정 계획 칸"):
        simulation_cache.get_assumed_required_shortening(
            _key(), equipment, downtime, baseline, cutoff, _required_equipment=loader
        )
    with pytest.raises(ValueError, match="짝이 아닙니다"):
        simulation_cache.get_required_shortening_csvs(
            official.key, 1.1, (PROCESS,), (MAY, JUNE), _keyed=assumed
        )
    # 진척 비교는 늘 공식 계획이다 — 가정 키는 받지 않는다(기준선은 거기까지 오기 전에 멈춘다).
    with pytest.raises(ValueError, match="공식 계획 칸"):
        simulation_cache.get_shortening_progress(
            assumed.key, "baseline", 1.1, _keyed=assumed, _baseline=cast(Any, None)
        )
    with pytest.raises(ValueError, match="짝이 아닙니다"):
        simulation_cache.get_shortening_progress(
            official.key, "baseline", 1.1, _keyed=assumed, _baseline=cast(Any, None)
        )


def test_the_assumed_cell_is_hit_on_the_same_key() -> None:
    """목표만 바꾼 회차는 계획을 다시 세우지 않는다 — 다섯 목표가 한 번에 들어 있다."""
    *_, required = _inputs()
    loader = _Loader(required)
    first = _load(_key(TOKEN), loader)
    calls = loader.calls
    again = _load(_key(TOKEN), loader)
    assert loader.calls == calls
    assert again.plan.at(1.3) is not None and first.plan.at(0.9) is not None
    assert simulation_cache.ASSUMED_PLAN_MAX_ENTRIES < 8


def test_the_target_plan_is_split_by_token_too() -> None:
    """공정 Capa 상세의 달마다 다른 목표 계획도 같은 규칙이다(공식 칸·가정 칸·짝)."""
    from capa_simulation.services.required_shortening import MonthlyTarget

    equipment, downtime, baseline, cutoff, required = _inputs()
    loader = _Loader(required)
    target = MonthlyTarget(default=1.095)
    official_key = simulation_cache.required_shortening_target_cache_key(_key(), target)
    assumed_key = simulation_cache.required_shortening_target_cache_key(_key(TOKEN), target)
    official = simulation_cache.load_required_shortening_for_target(
        official_key, equipment, downtime, baseline, cutoff, required_equipment=loader
    )
    assumed = simulation_cache.load_required_shortening_for_target(
        assumed_key, equipment, downtime, baseline, cutoff, required_equipment=loader
    )
    assert (
        assumed.at(target).process_months["소요대수"].sum()
        < official.at(target).process_months["소요대수"].sum()
    )
    with pytest.raises(ValueError, match="공식 계획 칸"):
        simulation_cache.get_required_shortening_for_target(
            assumed_key, equipment, downtime, baseline, cutoff, _required_equipment=loader
        )
