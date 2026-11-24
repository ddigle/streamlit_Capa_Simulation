# Purpose: 월 환산의 두 집계 기준(총량 · HOME 집계) 계산과 HOME Wafer 와의 맞대기를 고정한다.

"""환산 탭의 집계 기준은 둘이다.

- **산출 기준 총량**(기본 `total`) — 지금까지와 같은 값 · 같은 표다.
- **HOME 집계 기준**(`home`) — Chip · Wafer 를 묶기 전에 Dummy 계열 행을 뺀다. 그 행은 0 이
  아니라 표에서 없어진다(0 은 표 · CSV 에서 빈칸으로 그려져 「값 없음」 과 구별되지 않는다).
  PKG · Density 는 두 기준이 같다.

HOME 집계 기준의 월 합은 HOME `Wafer 계획` 과 같다(같은 EDP · 선행 B/O 끔 · 과거 구간 밖).
"""

from __future__ import annotations

import dummy_series_tables as demo
import pandas as pd
import pytest

from capa_simulation.services import simulation_cache
from capa_simulation.services.load_calculator import (
    LOAD_EXCLUSIONS_ATTR,
    MONTHLY_AGGREGATION_HOME,
    MONTHLY_AGGREGATION_TOTAL,
    MONTHLY_AGGREGATIONS,
    DemandBasis,
    build_monthly_volume,
    calculate_chip_load,
    calculate_wafer_load,
    exclude_dummy_series,
    filter_edp_plan,
)

MONTH_COLUMNS = [str(month) for month in demo.MONTHS]


def _volume(
    basis: DemandBasis,
    *,
    detailed: bool = False,
    aggregation: str | None = None,
    plan: pd.DataFrame | None = None,
) -> pd.DataFrame:
    options = {} if aggregation is None else {"aggregation": aggregation}
    return build_monthly_volume(
        plan=demo.plan() if plan is None else plan,
        yield_data=demo.yields(),
        chip_qty=demo.chip_qty(),
        demand_basis=basis,
        detailed=detailed,
        density_data=demo.chip_eq(),
        display_order=demo.display_order(),
        **options,  # type: ignore[arg-type]
    )


def _month_sums(volume: pd.DataFrame) -> list[float]:
    return [float(volume[column].sum()) for column in MONTH_COLUMNS]


def _load_sums(load: pd.DataFrame) -> list[float]:
    return [float(value) for value in load.groupby("생산계획년월")["물량"].sum().sort_index()]


def test_the_two_bases_are_named_once() -> None:
    assert MONTHLY_AGGREGATIONS == (MONTHLY_AGGREGATION_TOTAL, MONTHLY_AGGREGATION_HOME)
    assert (MONTHLY_AGGREGATION_TOTAL, MONTHLY_AGGREGATION_HOME) == ("total", "home")


@pytest.mark.parametrize("basis", ["PKG", "Chip", "Wafer", "Density"])
@pytest.mark.parametrize("detailed", [False, True])
def test_the_default_is_the_total_and_unchanged(basis: DemandBasis, detailed: bool) -> None:
    """기본은 산출 기준 총량이고, 인자를 주지 않던 지금까지의 표와 한 칸도 다르지 않다."""
    default = _volume(basis, detailed=detailed)
    total = _volume(basis, detailed=detailed, aggregation=MONTHLY_AGGREGATION_TOTAL)
    pd.testing.assert_frame_equal(default, total)
    assert default.attrs.get(LOAD_EXCLUSIONS_ATTR) == total.attrs.get(LOAD_EXCLUSIONS_ATTR)


def test_the_total_keeps_every_division_row() -> None:
    """총량의 상세 표는 Dummy · Top_Dummy 행을 그대로 품고 월 합이 상세 부하량 합과 같다."""
    total = _volume("Wafer", detailed=True)
    assert {"Dummy", "TOP_DUMMY", "Top_Dummy"} <= set(total["WF 구분"])
    load = calculate_wafer_load(demo.plan(), demo.yields(), demo.chip_qty())
    assert _month_sums(total) == pytest.approx(_load_sums(load))


@pytest.mark.parametrize("basis", ["Chip", "Wafer"])
def test_the_home_basis_drops_dummy_series_rows(basis: DemandBasis) -> None:
    calculate = calculate_wafer_load if basis == "Wafer" else calculate_chip_load
    load = calculate(demo.plan(), demo.yields(), demo.chip_qty())
    home = _volume(basis, detailed=True, aggregation=MONTHLY_AGGREGATION_HOME)
    # 빼는 것은 HBM 의 Dummy 계열뿐이다 — EDP-TSV 의 이름만 Dummy 인 행은 남는다.
    rows = home[["제품정보", "WF 구분"]].astype(str).apply(tuple, axis=1).tolist()
    assert (demo.HBM, "Dummy") not in rows
    assert (demo.HBM, "TOP_DUMMY") not in rows
    assert (demo.EDP, "Dummy") in rows
    assert not home["제품정보"].eq(demo.DUMMY_ONLY).any()
    assert _month_sums(home) == pytest.approx(_load_sums(exclude_dummy_series(load)))
    collapsed = _volume(basis, aggregation=MONTHLY_AGGREGATION_HOME)
    assert _month_sums(collapsed) == pytest.approx(_month_sums(home))
    # Dummy 계열만 있는 제품은 0 행이 아니라 표에서 없어진다.
    assert not collapsed["제품정보"].eq(demo.DUMMY_ONLY).any()
    assert all(
        home_sum < total_sum
        for home_sum, total_sum in zip(
            _month_sums(collapsed), _month_sums(_volume(basis)), strict=True
        )
    )


@pytest.mark.parametrize("basis", ["PKG", "Density"])
@pytest.mark.parametrize("detailed", [False, True])
def test_pkg_and_density_ignore_the_basis(basis: DemandBasis, detailed: bool) -> None:
    pd.testing.assert_frame_equal(
        _volume(basis, detailed=detailed, aggregation=MONTHLY_AGGREGATION_HOME),
        _volume(basis, detailed=detailed),
    )


@pytest.mark.parametrize("basis", ["PKG", "Chip", "Wafer", "Density"])
def test_the_exclusion_list_is_the_same_under_both_bases(basis: DemandBasis) -> None:
    """기준정보가 없어 빠진 계획 행(ST-05 건수)은 두 기준에서 같다 — 거르기 전 부하량 것을
    잇는다."""
    missing_yield = demo.yields().loc[lambda frame: ~frame["제품정보"].eq(demo.EDP)]
    plan = demo.plan()
    plan.loc[plan.index[0], "생산수량"] = None
    options = {
        "plan": plan,
        "yield_data": missing_yield,
        "chip_qty": demo.chip_qty(),
        "demand_basis": basis,
        "density_data": demo.chip_eq(),
        "display_order": demo.display_order(),
    }
    total = build_monthly_volume(**options)  # type: ignore[arg-type]
    home = build_monthly_volume(**options, aggregation=MONTHLY_AGGREGATION_HOME)  # type: ignore[arg-type]
    assert total.attrs[LOAD_EXCLUSIONS_ATTR]
    assert home.attrs[LOAD_EXCLUSIONS_ATTR] == total.attrs[LOAD_EXCLUSIONS_ATTR]


def test_an_unknown_basis_is_refused() -> None:
    with pytest.raises(ValueError, match="집계 기준"):
        _volume("Wafer", aggregation="dummy")


def test_the_cached_getters_pass_the_basis_through() -> None:
    """`get_monthly_volume` · `get_monthly_volume_by_key` 는 같은 인자를 받고 기준마다 칸이
    갈린다."""
    simulation_cache.get_monthly_volume.clear()
    simulation_cache.get_monthly_volume_by_key.clear()
    arguments = {
        "plan": demo.plan(),
        "yield_data": demo.yields(),
        "chip_qty": demo.chip_qty(),
        "demand_basis": "Wafer",
        "detailed": False,
        "density_data": demo.chip_eq(),
        "display_order": demo.display_order(),
    }
    for aggregation in MONTHLY_AGGREGATIONS:
        expected = _volume("Wafer", aggregation=aggregation)
        pd.testing.assert_frame_equal(
            simulation_cache.get_monthly_volume(**arguments, aggregation=aggregation),  # type: ignore[arg-type]
            expected,
        )
        pd.testing.assert_frame_equal(
            simulation_cache.get_monthly_volume_by_key(
                ("dummy-series", "monthly"),
                demo.plan(),
                demo.yields(),
                demo.chip_qty(),
                demo.chip_eq(),
                demo.display_order(),
                "Wafer",
                False,
                aggregation,
            ),
            expected,
        )
    simulation_cache.get_monthly_volume.clear()
    simulation_cache.get_monthly_volume_by_key.clear()


def _home_wafer(frame: pd.DataFrame) -> list[float]:
    return [float(value) for value in frame.sort_values("생산계획년월")["Wafer 부하량"]]


def test_the_home_basis_month_sum_is_the_home_wafer_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """교차: 환산 「HOME 집계 기준」 Wafer 월 합 = HOME `Wafer 계획`(같은 EDP · 선행 B/O 끔 ·
    과거 구간 밖) — EDP 를 뺀 쪽(`get_home_lob_without_edp`) · 포함한 쪽(`get_home_simulation`) ·
    비교 계획(`get_home_comparison_plan`) 셋 다."""
    monkeypatch.setattr(
        simulation_cache,
        "get_scenario_capacity_and_demand",
        lambda *_args, **_kwargs: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(
        simulation_cache, "get_securement_rate", lambda *_args, **_kwargs: pd.DataFrame()
    )
    for cached in (
        simulation_cache.get_home_simulation,
        simulation_cache.get_home_lob_without_edp,
        simulation_cache.get_home_comparison_plan,
    ):
        cached.clear()
    tables = demo.tables()
    without_edp = filter_edp_plan(demo.plan(), False)

    with_edp_home = simulation_cache.get_home_simulation(
        cache_key=demo.home_key("cross-edp"),
        _tables=tables,
        _display_order=demo.display_order(),
        _reference_tables=tables,
    )[2]
    assert _month_sums(_volume("Wafer", aggregation=MONTHLY_AGGREGATION_HOME)) == pytest.approx(
        _home_wafer(with_edp_home)
    )

    without_edp_home = simulation_cache.get_home_lob_without_edp(
        cache_key=demo.home_key("cross"),
        _tables=tables,
        _display_order=demo.display_order(),
    )[2]
    assert _month_sums(
        _volume("Wafer", aggregation=MONTHLY_AGGREGATION_HOME, plan=without_edp)
    ) == pytest.approx(_home_wafer(without_edp_home))

    comparison_plan = demo.plan(without=(demo.DUMMY_ONLY,))
    comparison_home = simulation_cache.get_home_comparison_plan(
        cache_key=demo.home_key("cross"),
        _tables=tables,
        _comparison_plan=comparison_plan,
        _display_order=demo.display_order(),
        comparison_revision_id="R-CMP",
        include_edp=True,
        detail_dimensions=("제품정보", "Stack"),
    )[1]
    assert _month_sums(
        _volume("Wafer", aggregation=MONTHLY_AGGREGATION_HOME, plan=comparison_plan)
    ) == pytest.approx(_home_wafer(comparison_home))
    for cached in (
        simulation_cache.get_home_simulation,
        simulation_cache.get_home_lob_without_edp,
        simulation_cache.get_home_comparison_plan,
    ):
        cached.clear()
