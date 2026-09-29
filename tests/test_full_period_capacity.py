# Purpose: Capa 를 시나리오 전체 기간으로 한 번 계산해 조회기간으로 잘라 쓰는 계약을 검증한다.

"""**조회기간을 바꿀 때마다 계산이 처음부터 다시 돌았다.**

계산 캐시가 기간별로 갈려 있어 처음 보는 기간마다 1.8~2.4초가 들었다(70공정 합성 표본,
샘플 관측). 월끼리 섞이는 계산이 없으므로 전체 기간을 한 번 계산하고 잘라 쓴다.

그 대가로 **보지 않는 달의 기준정보 오류도 계산을 멈춘다.** 사용자 결정이다 — 그 달을 열
때까지 오류가 숨으면 조치가 늦어진다. 대신 멈춘 이유가 조회기간 밖이라는 것을 말한다.
"""

from __future__ import annotations

from uuid import uuid4

import pandas as pd
import pytest

from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return dict(build_builtin_seed_dataset().reference_tables)


def _months(tables: dict[str, pd.DataFrame]) -> list[int]:
    values = pd.to_numeric(tables["RQ_UPEH"]["생산계획년월"]).unique().tolist()
    return sorted(int(value) for value in values)


def _key(start: int, end: int) -> sc.ScenarioCacheKey:
    # st.cache_data 는 프로세스 전역이다. 테스트마다 토큰을 새로 만들어 칸을 나눠 쓰지 않는다.
    return (1, f"test-full-period-{uuid4().hex}", start, end)


def _without_month(tables: dict[str, pd.DataFrame], month: int) -> dict[str, pd.DataFrame]:
    """가동률에서 한 달을 뺀다. 가동률은 중립값이 없어 행이 없으면 하드 오류다."""
    broken = dict(tables)
    run_rate = tables["RQ_RUN_RATE"]
    months = pd.to_numeric(run_rate["생산계획년월"])
    broken["RQ_RUN_RATE"] = run_rate.loc[months.ne(month)].reset_index(drop=True)
    return broken


def test_a_period_is_a_slice_of_the_whole_scenario(tables: dict[str, pd.DataFrame]) -> None:
    """자른 결과가 그 기간만 계산한 결과와 행 차례까지 같아야 잘라 써도 된다."""
    months = _months(tables)
    start, end = months[2], months[5]

    unit, required = sc.get_scenario_capacity_and_demand(
        _key(start, end), _scenario_tables=tables, _reference_tables=tables
    )
    alone = sc._capacity_outcome(sc._capacity_tables(tables, tables, (start, end)))

    assert alone.unit_capacity is not None and alone.required_equipment is not None
    assert unit.equals(alone.unit_capacity.reset_index(drop=True))
    assert required.equals(alone.required_equipment.reset_index(drop=True))
    assert set(pd.to_numeric(unit["생산계획년월"])) <= set(range(start, end + 1))


def test_an_error_outside_the_period_still_stops_and_says_so(
    tables: dict[str, pd.DataFrame],
) -> None:
    months = _months(tables)
    broken = _without_month(tables, months[-1])

    with pytest.raises(ValueError, match=r"조회기간\(.+\) 밖의 달에 기준정보 오류") as caught:
        sc.get_scenario_capacity_and_demand(
            _key(months[0], months[-2]), _scenario_tables=broken, _reference_tables=broken
        )

    assert "RQ_RUN_RATE" in str(caught.value)


def test_an_empty_ratio_table_does_not_hide_the_real_error_outside_the_period(
    tables: dict[str, pd.DataFrame],
) -> None:
    """측정률 표가 통째로 비어도(1.0 가정 — 정당한 상태) 조회기간 검사가 진짜 원인을 올린다.

    조회기간 검사가 빈 측정률 표까지 `filter_month_range` 로 자르다 「선택할 생산계획년월
    데이터가 없습니다」를 던져, 모든 계산 화면이 가동률 결손 대신 그 문구를 보였다(2026-09-29
    리뷰).
    """
    months = _months(tables)
    broken = _without_month(tables, months[-1])
    broken["RQ_LOT_RATIO"] = tables["RQ_LOT_RATIO"].iloc[0:0].copy()

    with pytest.raises(ValueError, match=r"조회기간\(.+\) 밖의 달에 기준정보 오류") as caught:
        sc.get_scenario_capacity_and_demand(
            _key(months[0], months[-2]), _scenario_tables=broken, _reference_tables=broken
        )

    assert "RQ_RUN_RATE" in str(caught.value)
    assert "선택할 생산계획년월" not in str(caught.value)


def test_an_out_of_range_yield_outside_the_period_names_the_row_and_the_yield_tab(
    tables: dict[str, pd.DataFrame],
) -> None:
    """보지 않는 달의 범위 밖 수율도 멈춘다 — 오류문이 그 행과 고칠 곳(생산 계획 → 수율 탭)을
    가리키고, 감싸는 문구가 「기준 정보 페이지」로 엇갈리게 보내지 않는다(2026-09-29 리뷰)."""
    months = _months(tables)
    broken = dict(tables)
    yields = tables["RQ_YLD"].copy()
    last = pd.to_numeric(yields["생산계획년월"]).eq(months[-1])
    product = str(yields.loc[last, "제품정보"].iloc[0])
    yields.loc[last & yields["제품정보"].eq(product), "EDS_수율"] = 0.0
    broken["RQ_YLD"] = yields

    with pytest.raises(ValueError, match="밖의 달에 기준정보 오류") as caught:
        sc.get_scenario_capacity_and_demand(
            _key(months[0], months[-2]), _scenario_tables=broken, _reference_tables=broken
        )

    message = str(caught.value)
    assert f"{months[-1]} · {product}" in message
    assert "생산 계획 → 수율 탭" in message
    assert "기준 정보 페이지에서 고친" not in message


def test_an_error_inside_the_period_is_reported_as_it_is(tables: dict[str, pd.DataFrame]) -> None:
    """보는 기간 안의 오류는 「밖」이라고 말하면 안 된다 — 고칠 곳을 엉뚱하게 가리킨다."""
    months = _months(tables)
    broken = _without_month(tables, months[-1])

    with pytest.raises(ValueError, match="RQ_RUN_RATE") as caught:
        sc.get_scenario_capacity_and_demand(
            _key(months[0], months[-1]), _scenario_tables=broken, _reference_tables=broken
        )

    assert "밖의 달" not in str(caught.value)


def test_a_failed_calculation_is_cached_rather_than_rerun(
    tables: dict[str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """예외는 캐시되지 않는다. 결과로 담지 않으면 오류 화면을 여는 실행마다 몇 초씩 다시 돈다."""
    months = _months(tables)
    broken = _without_month(tables, months[-1])
    calls: list[int] = []
    original = sc.get_capacity_and_demand

    def counted(inputs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
        calls.append(1)
        return original(inputs)

    monkeypatch.setattr(sc, "get_capacity_and_demand", counted)
    key = (1, f"test-full-period-{uuid4().hex}")

    first = sc.get_full_capacity_outcome(key, _scenario_tables=broken, _reference_tables=broken)
    second = sc.get_full_capacity_outcome(key, _scenario_tables=broken, _reference_tables=broken)

    assert first.error is not None and first.error == second.error
    assert len(calls) == 1


def test_exclusion_lists_follow_the_period_but_assumptions_cover_the_scenario() -> None:
    """제외 목록은 보는 기간만, 측정률 가정은 시나리오 전체를 말한다(사용자 결정)."""
    frame = pd.DataFrame({"생산계획년월": [202601, 202602, 202603], "값": [1, 2, 3]})
    frame.attrs = {
        "excluded": pd.DataFrame({"생산계획년월": [202601, 202603], "사유": ["a", "b"]}),
        "counts": {"RQ_LOT_RATIO": 4},
    }

    sliced = sc.slice_capacity_months(frame, 202602, 202603)

    assert sliced["값"].tolist() == [2, 3]
    assert sliced.attrs["excluded"]["사유"].tolist() == ["b"]
    assert sliced.attrs["counts"] == {"RQ_LOT_RATIO": 4}
