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
import streamlit as st

from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.unit_capacity import (
    CAPACITY_ASSUMPTIONS_ATTR,
    CAPACITY_EXCLUSIONS_ATTR,
)


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


def _assert_same_frame(new: pd.DataFrame, old: pd.DataFrame) -> None:
    assert new.equals(old)
    assert new.dtypes.equals(old.dtypes)
    assert new.columns.equals(old.columns) and new.index.equals(old.index)
    assert new.attrs.keys() == old.attrs.keys()
    for name, value in new.attrs.items():
        other = old.attrs[name]
        if isinstance(value, pd.DataFrame):
            assert isinstance(other, pd.DataFrame), name
            assert value.equals(other) and value.dtypes.equals(other.dtypes), name
        else:
            assert value == other, name


def _with_exclusions(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """attrs 가 비지 않은 표 — Lot 측정률 음수 세 달(달 칸이 있는 제외 목록)과 WF 측정률 한 행 빠짐
    (1.0 가정 건수 · 달). 합성 시드에서는 제외 목록이 비어 있어 attrs 대조가 빈 표끼리만 된다."""
    noisy = dict(tables)
    lot = tables["RQ_LOT_RATIO"].copy()
    lot_months = pd.to_numeric(lot["생산계획년월"])
    months = sorted(int(month) for month in lot_months.unique())
    marked = lot_months.isin([months[1], months[4], months[8]])
    picked = lot.loc[marked].groupby(lot_months[marked]).head(1).index
    lot.loc[picked, "Lot 측정률"] = -0.5
    noisy["RQ_LOT_RATIO"] = lot
    wf = tables["RQ_WF_RATIO"]
    wf_months = pd.to_numeric(wf["생산계획년월"])
    noisy["RQ_WF_RATIO"] = wf.drop(wf.index[wf_months.eq(months[3])][:1]).reset_index(drop=True)
    return noisy


@pytest.mark.parametrize("noisy", [False, True], ids=["seed", "exclusions"])
@pytest.mark.parametrize("bounds", [(0, -1), (2, 5), (6, 6)])
def test_slicing_on_every_call_matches_the_old_sliced_cell(
    tables: dict[str, pd.DataFrame],
    bounds: tuple[int, int],
    noisy: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """자른 결과는 칸에 두지 않고 부를 때마다 전체 기간 칸에서 자른다. 옛 길 — 같은 몸통을 조회기간
    키의 `st.cache_data` 칸에 둔 것 — 의 첫 호출(계산한 객체)·적중 호출(피클 왕복)과 프레임 · dtype
    · 열 · 색인 · attrs 가 같아야 한다. 새 길의 두 번째 호출은 전체 칸에 적중해 다시 계산하지 않고,
    받은 프레임을 고쳐도 다음 호출에 닿지 않는다(부를 때마다 새 사본). 제외 목록이 기간을 가로지르는
    표(`_with_exclusions`)로도 본다 — 달 칸이 있는 attrs 는 같이 잘리고 가정 건수는 전체 값이다."""
    if noisy:
        tables = _with_exclusions(tables)
    months = _months(tables)
    start, end = months[bounds[0]], months[bounds[1]]
    computed: list[int] = []
    original = sc.get_capacity_and_demand

    def counted(inputs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
        computed.append(1)
        return original(inputs)

    monkeypatch.setattr(sc, "get_capacity_and_demand", counted)
    old_cell = st.cache_data(show_spinner=False, max_entries=16)(
        sc.get_scenario_capacity_and_demand
    )
    new_key, old_key = _key(start, end), _key(start, end)

    new_first = sc.get_scenario_capacity_and_demand(
        new_key, _scenario_tables=tables, _reference_tables=tables
    )
    new_hit = sc.get_scenario_capacity_and_demand(
        new_key, _scenario_tables=tables, _reference_tables=tables
    )
    assert len(computed) == 1
    old_first = old_cell(old_key, _scenario_tables=tables, _reference_tables=tables)
    old_hit = old_cell(old_key, _scenario_tables=tables, _reference_tables=tables)
    assert len(computed) == 2

    for new in (new_first, new_hit):
        for old in (old_first, old_hit):
            for new_frame, old_frame in zip(new, old, strict=True):
                _assert_same_frame(new_frame, old_frame)
    if noisy:
        excluded = new_first[0].attrs[CAPACITY_EXCLUSIONS_ATTR]
        excluded_months = [months[1], months[4], months[8]]
        assert len(excluded) == sum(start <= month <= end for month in excluded_months)
        assert new_first[0].attrs[CAPACITY_ASSUMPTIONS_ATTR] == {"RQ_WF_RATIO": 1}

    new_hit[0]["대당 Capa"] = -1.0
    again = sc.get_scenario_capacity_and_demand(
        new_key, _scenario_tables=tables, _reference_tables=tables
    )
    _assert_same_frame(again[0], new_first[0])


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
