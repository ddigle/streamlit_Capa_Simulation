# Purpose: HOME 생산계획·Wafer 부하량(필요 단축 일정 Wafer 줄 포함)·Bottleneck 집계를 검증한다.

from uuid import uuid4

import dummy_series_tables as demo
import pandas as pd
import pytest
from custom_key_tables import (
    PART_A,
    PART_B,
    TWO_PART_PRODUCT,
    two_part_tables,
    with_blank_custom,
)

from capa_simulation.services import simulation_cache
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    PRODUCTION_DETAIL_DIMENSIONS,
    align_detail_with_comparison,
    build_bottleneck_capacity,
    build_monthly_bottleneck_details_from_ranking,
    build_monthly_bottleneck_ranking,
    build_monthly_bottleneck_top5_from_ranking,
    build_monthly_bottlenecks_from_ranking,
    build_monthly_wafer_load_from_load,
    build_production_dashboard,
    build_production_lob_summary,
)
from capa_simulation.services.load_calculator import (
    calculate_wafer_load,
    exclude_dummy_series,
    filter_edp_plan,
)
from capa_simulation.services.product_parts import PART_NOT_SPLIT, multi_part_products
from capa_simulation.services.product_share import assign_product_slots, build_product_volume
from capa_simulation.services.route_load_exceptions import NO_ROUTE_LOAD_EXCEPTIONS


def test_production_dashboard_groups_pkg_plan_by_product_and_stack() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202609],
            "양산구분": ["양산", "ER", "양산"],
            "제품정보": ["HBM다E", "HBM다E", "HBM다E"],
            "Stack": ["12H", "12H", "12H"],
            "생산수량": [100.0, 50.0, 200.0],
        }
    )
    plan = with_blank_custom(plan)
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11.0],
            "구분_EQ": [24.0],
        }
    )
    density_data = with_blank_custom(density_data)

    monthly, detail = build_production_dashboard(plan, density_data)

    assert monthly["년월"].tolist() == ["26.08", "26.09"]
    assert monthly["부하량"].tolist() == pytest.approx(
        [100 * 11 * 24 / 100_000, 200 * 11 * 24 / 100_000]
    )
    assert list(detail.columns) == ["제품정보", "CUSTOM", "Stack", "26.08", "26.09"]
    assert detail.loc[0, "26.08"] == pytest.approx(100.0)
    assert detail.loc[0, "26.09"] == pytest.approx(200.0)


def test_production_dashboard_can_split_the_detail_by_customer() -> None:
    """`상세 계획` 을 켜면 제품·Stack 아래에 거래선이 분류로 더해진다.

    `Customer` 는 `RQ_PKG_PLAN` 의 1급 컬럼이라 조인이 아니라 묶는 키 하나가 늘어난다.
    같은 제품·Stack 이라도 거래선이 다르면 행이 갈라져야 한다.
    """
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202608],
            "양산구분": ["양산", "양산", "양산"],
            "제품정보": ["HBM다E", "HBM다E", "HBM다E"],
            "Stack": ["12H", "12H", "12H"],
            "Customer": ["Customer-A", "Customer-B", "Customer-A"],
            "생산수량": [100.0, 40.0, 60.0],
        }
    )
    plan = with_blank_custom(plan)
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11.0],
            "구분_EQ": [24.0],
        }
    )
    density_data = with_blank_custom(density_data)

    _, detail = build_production_dashboard(
        plan,
        density_data,
        detail_dimensions=PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    )

    assert list(detail.columns) == ["제품정보", "CUSTOM", "Stack", "Customer", "26.08"]
    assert detail["Customer"].tolist() == ["Customer-A", "Customer-B"]
    # 같은 거래선의 두 행은 합쳐지고 다른 거래선은 갈라진다.
    assert detail["26.08"].tolist() == pytest.approx([160.0, 40.0])
    # Density 는 분류와 무관하게 전체 합이다 — 분류를 바꿔도 부하량은 그대로여야 한다.
    _, base_detail = build_production_dashboard(plan, density_data)
    assert base_detail["26.08"].sum() == pytest.approx(detail["26.08"].sum())


def test_customer_order_comes_from_the_shared_display_order_profile() -> None:
    """거래선 정렬은 표시순서 관리에 `Customer` 규칙을 넣으면 그대로 걸린다.

    `apply_display_order` 는 데이터에 없는 분류컬럼 규칙을 건너뛴다. 그래서 같은 규칙이
    `상세 계획` 을 끈 화면에서는 아무 일도 하지 않고, 켠 화면에서만 거래선 순서를 정한다.
    """
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "양산구분": ["양산", "양산"],
            "제품정보": ["HBM다E", "HBM다E"],
            "Stack": ["12H", "12H"],
            "Customer": ["Customer-A", "Customer-B"],
            "생산수량": [100.0, 40.0],
        }
    )
    plan = with_blank_custom(plan)
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11.0],
            "구분_EQ": [24.0],
        }
    )
    density_data = with_blank_custom(density_data)
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["생산 계획", "생산 계획"],
            "탭 구분": ["PKG PLAN", "PKG PLAN"],
            "정렬우선순위": [3, 3],
            "분류컬럼": ["Customer", "Customer"],
            "정렬방식": ["사용자지정", "사용자지정"],
            "분류값": ["Customer-B", "Customer-A"],
            "값표시순서": [1, 2],
            "활성여부": ["Y", "Y"],
        }
    )

    _, detail = build_production_dashboard(
        plan,
        density_data,
        display_order,
        detail_dimensions=PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    )

    assert detail["Customer"].tolist() == ["Customer-B", "Customer-A"]

    # 같은 규칙이 분류에 거래선이 없는 화면에서는 아무것도 바꾸지 않는다.
    _, base_detail = build_production_dashboard(plan, density_data, display_order)
    assert list(base_detail.columns) == ["제품정보", "CUSTOM", "Stack", "26.08"]


def test_production_dashboard_uses_pkg_plan_display_order() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202608],
            "양산구분": ["양산", "양산", "양산"],
            "제품정보": ["제품B", "제품A", "제품A"],
            "Stack": ["8H", "8H", "12H"],
            "생산수량": [100.0, 200.0, 300.0],
        }
    )
    plan = with_blank_custom(plan)
    density_data = pd.DataFrame(
        {
            "제품정보": ["제품B", "제품A", "제품A"],
            "Stack": ["8H", "8H", "12H"],
            "WF 구분": ["Core", "Core", "Core"],
            "구분_Chip": [1.0, 1.0, 1.0],
            "구분_EQ": [1.0, 1.0, 1.0],
        }
    )
    density_data = with_blank_custom(density_data)
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["생산 계획"] * 4,
            "탭 구분": ["PKG PLAN"] * 4,
            "정렬우선순위": [1, 1, 2, 2],
            "분류컬럼": ["제품정보", "제품정보", "Stack", "Stack"],
            "정렬방식": ["사용자지정"] * 4,
            "분류값": ["제품A", "제품B", "12H", "8H"],
            "값표시순서": [1, 2, 1, 2],
            "활성여부": ["Y"] * 4,
        }
    )

    _, detail = build_production_dashboard(plan, density_data, display_order)

    assert detail[["제품정보", "Stack"]].to_dict("records") == [
        {"제품정보": "제품A", "Stack": "12H"},
        {"제품정보": "제품A", "Stack": "8H"},
        {"제품정보": "제품B", "Stack": "8H"},
    ]


def test_dashboard_selects_lowest_monthly_securement_process() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608, 202609, 202609],
            "공정": ["Process-B", "Process-A", "Process-C", "Process-D"],
            "확보율": [0.8, 0.8, 1.2, 0.9],
        }
    )

    result = build_monthly_bottlenecks_from_ranking(build_monthly_bottleneck_ranking(securement))

    assert result["년월"].tolist() == ["26.08", "26.09"]
    assert result["공정"].tolist() == ["Process-A", "Process-D"]
    assert result["확보율"].tolist() == pytest.approx([0.8, 0.9])
    assert result["축레이블"].tolist() == [
        "26.08<br>Process-A",
        "26.09<br>Process-D",
    ]

    filtered = build_monthly_bottlenecks_from_ranking(
        build_monthly_bottleneck_ranking(securement, included_processes=["Process-B", "Process-C"])
    )
    assert filtered["공정"].tolist() == ["Process-B", "Process-C"]

    excluded = build_monthly_bottlenecks_from_ranking(
        build_monthly_bottleneck_ranking(securement, included_processes=[])
    )
    assert excluded.empty
    assert excluded.columns.tolist() == ["생산계획년월", "공정", "확보율", "년월", "축레이블"]

    monthly_density = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "년월": ["26.08", "26.09"],
            "부하량": [10.0, 20.0],
        }
    )
    monthly_wafer = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "Wafer 부하량": [1_000.0, 2_000.0],
        }
    )
    summary = build_production_lob_summary(monthly_density, monthly_wafer, excluded)
    assert summary["부하량"].tolist() == [10.0, 20.0]
    assert summary["Wafer 부하량"].tolist() == [1_000.0, 2_000.0]
    assert summary["Wafer Capa"].isna().all()


def test_dashboard_reuses_one_monthly_bottleneck_ranking() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202608] * 6,
            "공정": [f"Process-{index}" for index in range(6)],
            "가용대수": [10.0] * 6,
            "소요대수": [20.0] * 6,
            "확보율": [1.2, 0.8, 1.1, 0.9, 1.0, 0.7],
        }
    )
    monthly_density = pd.DataFrame({"생산계획년월": [202608], "부하량": [10.0], "년월": ["26.08"]})
    monthly_wafer = pd.DataFrame(
        {"생산계획년월": [202608], "Wafer 부하량": [1_000.0], "년월": ["26.08"]}
    )

    ranking = build_monthly_bottleneck_ranking(securement)
    top1 = build_monthly_bottlenecks_from_ranking(ranking)
    top5 = build_monthly_bottleneck_top5_from_ranking(
        ranking,
        monthly_density,
        monthly_wafer,
    )
    details = build_monthly_bottleneck_details_from_ranking(
        ranking,
        monthly_wafer,
        rank_limit=20,
    )

    assert ranking["공정"].tolist() == [
        "Process-5",
        "Process-1",
        "Process-3",
        "Process-4",
        "Process-2",
        "Process-0",
    ]
    assert ranking["순위"].tolist() == [1, 2, 3, 4, 5, 6]
    assert top1["공정"].tolist() == ["Process-5"]
    assert top5["공정"].tolist() == ranking["공정"].head(5).tolist()
    # 상한(20)보다 유효 공정이 적은 달은 있는 만큼만 나온다.
    assert details["공정"].tolist() == ranking["공정"].tolist()


def test_dashboard_converts_bottleneck_rate_to_density_capacity() -> None:
    monthly_density = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "부하량": [10.0, 20.0],
            "년월": ["26.08", "26.09"],
        }
    )
    bottlenecks = pd.DataFrame(
        {
            "생산계획년월": [202608, 202609],
            "공정": ["Process-A", "Process-B"],
            "확보율": [1.1, 0.8],
        }
    )

    result = build_bottleneck_capacity(monthly_density, bottlenecks)

    assert result["B/N Capa"].tolist() == pytest.approx([11.0, 16.0])


def test_dashboard_builds_monthly_bottleneck_top5_capacity() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202608] * 7,
            "공정": [f"Process-{index}" for index in range(7)],
            "확보율": [1.2, 0.8, 1.1, 0.9, 1.0, 0.7, 1.3],
        }
    )
    monthly_density = pd.DataFrame({"생산계획년월": [202608], "부하량": [10.0], "년월": ["26.08"]})
    monthly_wafer = pd.DataFrame(
        {"생산계획년월": [202608], "Wafer 부하량": [1_000.0], "년월": ["26.08"]}
    )

    ranking = build_monthly_bottleneck_ranking(
        securement,
        included_processes=[f"Process-{index}" for index in range(6)],
    )
    result = build_monthly_bottleneck_top5_from_ranking(
        ranking,
        monthly_density,
        monthly_wafer=monthly_wafer,
    )

    assert result["공정"].tolist() == [
        "Process-5",
        "Process-1",
        "Process-3",
        "Process-4",
        "Process-2",
    ]
    assert result["순위"].tolist() == [1, 2, 3, 4, 5]
    assert result["B/N Capa"].tolist() == pytest.approx([7.0, 8.0, 9.0, 10.0, 11.0])
    assert result["Wafer Capa"].tolist() == pytest.approx([700.0, 800.0, 900.0, 1_000.0, 1_100.0])


def test_dashboard_builds_monthly_bottleneck_details() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202608] * 12,
            "공정": [f"Process-{index:02d}" for index in range(12)],
            "가용대수": [float(index + 10) for index in range(12)],
            "소요대수": [float(index + 20) for index in range(12)],
            "확보율": [1.2, 0.8, 1.1, 0.9, 1.0, 0.7, 1.3, 0.6, 1.4, 0.5, 1.5, 0.4],
        }
    )
    monthly_wafer = pd.DataFrame(
        {"생산계획년월": [202608], "Wafer 부하량": [1_000.0], "년월": ["26.08"]}
    )

    included = [f"Process-{index:02d}" for index in range(11)]
    ascending_by_rate = [
        "Process-09",
        "Process-07",
        "Process-05",
        "Process-01",
        "Process-03",
        "Process-04",
        "Process-02",
        "Process-00",
        "Process-06",
        "Process-08",
        "Process-10",
    ]

    ranking = build_monthly_bottleneck_ranking(securement, included_processes=included)

    # 상한이 유효 공정 수보다 크면 있는 만큼만 나온다.
    result = build_monthly_bottleneck_details_from_ranking(
        ranking,
        monthly_wafer,
        rank_limit=20,
    )

    assert len(result) == 11
    assert result["공정"].tolist() == ascending_by_rate
    assert result["순위"].tolist() == list(range(1, 12))
    assert result["Wafer Capa"].tolist() == pytest.approx(
        [
            500.0,
            600.0,
            700.0,
            800.0,
            900.0,
            1_000.0,
            1_100.0,
            1_200.0,
            1_300.0,
            1_400.0,
            1_500.0,
        ]
    )

    # 상한이 실제로 자른다.
    limited = build_monthly_bottleneck_details_from_ranking(
        ranking,
        monthly_wafer,
        rank_limit=4,
    )

    assert limited["공정"].tolist() == ascending_by_rate[:4]
    assert limited["순위"].tolist() == [1, 2, 3, 4]


def test_dashboard_rejects_a_bottleneck_detail_rank_limit_below_one() -> None:
    ranking = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "공정": ["Process-A"],
            "가용대수": [10.0],
            "소요대수": [20.0],
            "확보율": [0.5],
            "순위": [1],
        }
    )
    monthly_wafer = pd.DataFrame({"생산계획년월": [202608], "Wafer 부하량": [1_000.0]})

    with pytest.raises(ValueError, match="1 이상"):
        build_monthly_bottleneck_details_from_ranking(ranking, monthly_wafer, rank_limit=0)


def test_dashboard_builds_wafer_lob_summary() -> None:
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "양산구분": ["양산", "ER"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["12H", "12H"],
            "Capa Code": ["A", "A"],
            "Customer": ["Customer-A", "Customer-A"],
            "CS": ["MP", "MP"],
            "생산수량": [100.0, 50.0],
        }
    )
    plan = with_blank_custom(plan)
    yield_data = pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "EDS_수율": [0.8],
            "BE_수율": [0.5],
        }
    )
    yield_data = with_blank_custom(yield_data)
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [2.0],
            "Net Die": [500.0],
        }
    )
    chip_qty = with_blank_custom(chip_qty)
    density = pd.DataFrame({"생산계획년월": [202608], "년월": ["26.08"], "부하량": [10.0]})
    bottleneck = pd.DataFrame({"생산계획년월": [202608], "공정": ["Process-A"], "확보율": [1.1]})

    wafer = build_monthly_wafer_load_from_load(calculate_wafer_load(plan, yield_data, chip_qty))
    summary = build_production_lob_summary(density, wafer, bottleneck)

    assert wafer.loc[0, "Wafer 부하량"] == pytest.approx(150 * 1_000 * 2 / 0.8 / 0.5 / 500)
    assert summary.loc[0, "Wafer Capa"] == pytest.approx(wafer.loc[0, "Wafer 부하량"] * 1.1)


def test_detail_comparison_keeps_rows_that_only_the_comparison_has() -> None:
    """빠진 제품을 화면에서 보이게 하는 것이 비교의 목적이다."""
    dimensions = ["제품정보", "Stack"]
    current = pd.DataFrame(
        {"제품정보": ["A"], "Stack": ["12H"], "26.08": [100.0]},
    )
    comparison = pd.DataFrame(
        {"제품정보": ["A", "B"], "Stack": ["12H", "8H"], "26.08": [80.0, 40.0]},
    )

    aligned_current, aligned_comparison = align_detail_with_comparison(
        current, comparison, dimensions
    )

    assert aligned_current["제품정보"].tolist() == ["A", "B"]
    # 현재 계획에 없는 조합은 결측이고 비교값만 있다.
    assert pd.isna(aligned_current["26.08"].tolist()[1])
    assert aligned_comparison["26.08"].tolist() == pytest.approx([80.0, 40.0])


def _monthly_sheets(frame: pd.DataFrame) -> list[float]:
    return [float(value) for value in frame.sort_values("생산계획년월")["Wafer 부하량"]]


def _demo_wafer_load(*, include_edp: bool) -> pd.DataFrame:
    return calculate_wafer_load(
        filter_edp_plan(demo.plan(), include_edp), demo.yields(), demo.chip_qty()
    )


def _sum_by_month(load: pd.DataFrame) -> list[float]:
    return [float(value) for value in load.groupby("생산계획년월")["물량"].sum().sort_index()]


def test_home_wafer_without_edp_drops_the_dummy_series() -> None:
    """EDP 를 뺀 HOME 의 월 Wafer · 제품별 수량은 Dummy 계열을 뺀 합이다. 제품별 합은 월 합과 한
    치도 다르지 않다."""
    simulation_cache.get_home_lob_without_edp.clear()
    _density, _detail, monthly_wafer, product_volume = simulation_cache.get_home_lob_without_edp(
        cache_key=demo.home_key("lob"),
        _tables=demo.tables(),
        _display_order=demo.display_order(),
    )
    load = _demo_wafer_load(include_edp=False)
    assert _monthly_sheets(monthly_wafer) == pytest.approx(
        _sum_by_month(exclude_dummy_series(load))
    )
    assert all(
        filtered < unfiltered
        for filtered, unfiltered in zip(
            _monthly_sheets(monthly_wafer), _sum_by_month(load), strict=True
        )
    )
    by_month = product_volume.groupby("생산계획년월")["Wafer 부하량"].sum().sort_index()
    assert [float(value) for value in by_month] == pytest.approx(_monthly_sheets(monthly_wafer))
    # Dummy 계열만 있는 제품은 HOME 집계에서 Wafer 가 0 이다.
    only_dummy = product_volume.loc[product_volume["제품정보"].eq(demo.DUMMY_ONLY)]
    assert only_dummy["Wafer 부하량"].eq(0.0).all()
    simulation_cache.get_home_lob_without_edp.clear()


def test_home_simulation_returns_the_home_wafer_without_the_dummy_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """셋째 · 여섯째 원소(EDP 포함)는 HOME 집계 기준 — Dummy 계열을 뺀 합이고, 원소는 여섯이다.
    필요 단축 일정 「Wafer 계획」 줄도 셋째 원소를 읽어 거르지 않은 합을 따로 내지 않는다."""
    monkeypatch.setattr(
        simulation_cache,
        "get_scenario_capacity_and_demand",
        lambda *_args, **_kwargs: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(
        simulation_cache, "get_securement_rate", lambda *_args, **_kwargs: pd.DataFrame()
    )
    simulation_cache.get_home_simulation.clear()
    result = simulation_cache.get_home_simulation(
        cache_key=demo.home_key("simulation"),
        _tables=demo.tables(),
        _display_order=demo.display_order(),
        _reference_tables=demo.tables(),
    )
    assert len(result) == 6
    monthly_wafer, product_volume = result[2], result[5]
    load = _demo_wafer_load(include_edp=True)
    assert _monthly_sheets(monthly_wafer) == pytest.approx(
        _sum_by_month(exclude_dummy_series(load))
    )
    # 견본의 Dummy 계열 행이 달마다 값을 줄인다 — 거르지 않은 합과 같으면 거름이 안 걸린 것이다.
    assert all(
        filtered < unfiltered
        for filtered, unfiltered in zip(
            _monthly_sheets(monthly_wafer), _sum_by_month(load), strict=True
        )
    )
    by_month = product_volume.groupby("생산계획년월")["Wafer 부하량"].sum().sort_index()
    assert [float(value) for value in by_month] == pytest.approx(_monthly_sheets(monthly_wafer))
    simulation_cache.get_home_simulation.clear()


def test_shortening_wafer_plan_reads_the_home_wafer_without_the_dummy_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """필요 단축 일정 `계획 · LOB 요약` 의 Wafer 계획 줄은 HOME `Wafer 계획` 과 같은 값 — 견본의
    Dummy 계열 행을 뺀 월 합(EDP 포함)이고 거르지 않은 합이 아니다. 흉내 낸 원소가 아니라 실제 HOME
    계산을 지나므로 풀기 자리가 어긋나면 값이 달라진다."""
    from capa_simulation.components import required_shortening_panel as panel
    from capa_simulation.page_bootstrap import PageContext
    from capa_simulation.persistence.models import RouteLoadExceptionState

    monkeypatch.setattr(
        simulation_cache,
        "get_scenario_capacity_and_demand",
        lambda *_args, **_kwargs: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(
        simulation_cache, "get_securement_rate", lambda *_args, **_kwargs: pd.DataFrame()
    )
    # 과거 구간 달은 넣지 않는다 — 공용 과거 구간 프로필(DB)을 열지 않는다.
    monkeypatch.setattr(panel, "home_toggle", lambda _state, _key: False)
    tables = demo.tables()
    context = PageContext(
        reference_version=0,
        reference_tables=tables,
        display_order=None,
        active_scenario={
            "reference_version": 0,
            "revision": 0,
            "content_token": "dummy-series-shortening",
            "tables": tables,
        },
        selected_start_month=demo.MONTHS[0],
        selected_end_month=demo.MONTHS[-1],
        route_exceptions=RouteLoadExceptionState().profile,
    )
    simulation_cache.get_home_simulation.clear()
    rows = panel._lob_rows(context, list(demo.MONTHS))
    simulation_cache.get_home_simulation.clear()

    assert rows.error is None
    wafer = [rows.wafer[month] for month in demo.MONTHS]
    load = _demo_wafer_load(include_edp=True)
    assert wafer == pytest.approx(_sum_by_month(exclude_dummy_series(load)))
    assert all(
        shown < unfiltered for shown, unfiltered in zip(wafer, _sum_by_month(load), strict=True)
    )


def test_wafer_capa_follows_the_home_wafer_plan_and_stays_within_it_at_full_securement() -> None:
    """같은 HOME 표의 `Wafer Capa` · B/N Top 5 · 상세 B/N 의 Wafer Capa 는 `Wafer 계획` 과 같은 거른
    월 합 × 확보율이다 — 거르지 않은 합을 곱하면 확보율 100% 에서 Wafer Capa 가 Wafer 계획을 넘어
    표가 스스로 어긋난다."""
    simulation_cache.get_home_lob_without_edp.clear()
    density, _detail, monthly_wafer, _volume = simulation_cache.get_home_lob_without_edp(
        cache_key=demo.home_key("capa"),
        _tables=demo.tables(),
        _display_order=demo.display_order(),
    )
    simulation_cache.get_home_lob_without_edp.clear()
    ranking = build_monthly_bottleneck_ranking(
        pd.DataFrame(
            {
                "생산계획년월": list(demo.MONTHS),
                "공정": ["DEMO-P1", "DEMO-P1"],
                "가용대수": [10.0, 10.0],
                "소요대수": [10.0, 10.0],
                "확보율": [1.0, 1.0],
            }
        )
    )
    summary = build_production_lob_summary(
        density, monthly_wafer, build_monthly_bottlenecks_from_ranking(ranking)
    )
    plan = summary["Wafer 부하량"].to_numpy()
    assert summary["Wafer Capa"].to_numpy() == pytest.approx(plan)
    assert (summary["Wafer Capa"] <= summary["Wafer 부하량"]).all()
    top5 = build_monthly_bottleneck_top5_from_ranking(ranking, density, monthly_wafer=monthly_wafer)
    details = build_monthly_bottleneck_details_from_ranking(ranking, monthly_wafer, rank_limit=5)
    for frame in (top5, details):
        assert frame.sort_values("생산계획년월")["Wafer Capa"].to_numpy() == pytest.approx(plan)


# ---------------------------------------------------------------- 부품(CUSTOM) 갈라 보임


def _part_plan(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    """(제품정보, CUSTOM, Stack, 생산수량) — 한 달 양산 계획."""
    return pd.DataFrame(
        {
            "생산계획년월": [202608] * len(rows),
            "양산구분": ["양산"] * len(rows),
            "제품정보": [row[0] for row in rows],
            "CUSTOM": [row[1] for row in rows],
            "Stack": [row[2] for row in rows],
            "생산수량": [row[3] for row in rows],
        }
    )


def _part_density(plan: pd.DataFrame) -> pd.DataFrame:
    density = plan[["제품정보", "CUSTOM", "Stack"]].drop_duplicates().reset_index(drop=True)
    density["WF 구분"] = "Core"
    density["구분_Chip"] = 1.0
    density["구분_EQ"] = 1.0
    return density


def _rows(detail: pd.DataFrame) -> list[tuple[str, str, str]]:
    return [
        (str(product), str(part), str(stack))
        for product, part, stack in zip(
            detail["제품정보"], detail["CUSTOM"], detail["Stack"], strict=True
        )
    ]


def test_two_parts_of_a_seed_product_get_their_own_rows_and_add_up_to_the_product() -> None:
    """두 부품 견본은 그 제품이 부품마다 한 줄이고 두 줄의 합이 시드 한 제품 줄과 같다 — 지금 합을
    나눈 것이라 숫자는 바뀌지 않는다."""
    tables = two_part_tables()
    plan = tables["RQ_PKG_PLAN"]
    _, detail = build_production_dashboard(
        plan,
        tables["RQ_CHIP_EQ"],
        tables["RQ_DISPLAY_ORDER"],
        multi_part=multi_part_products(plan),
    )
    seed = build_builtin_seed_dataset().reference_tables
    _, seed_detail = build_production_dashboard(
        seed["RQ_PKG_PLAN"], seed["RQ_CHIP_EQ"], seed["RQ_DISPLAY_ORDER"]
    )

    product_rows = detail.loc[detail["제품정보"].eq(TWO_PART_PRODUCT)]
    assert product_rows["CUSTOM"].tolist() == [PART_A, PART_B]
    months = [column for column in detail.columns if column not in PRODUCTION_DETAIL_DIMENSIONS]
    seed_row = seed_detail.loc[seed_detail["제품정보"].eq(TWO_PART_PRODUCT), months]
    assert product_rows[months].sum().tolist() == pytest.approx(seed_row.sum().tolist())
    assert set(seed_detail["CUSTOM"]) == {PART_NOT_SPLIT}


def test_a_product_with_one_part_keeps_the_rows_it_had_without_the_part_column() -> None:
    """제품마다 CUSTOM 이 한 값이면(표지든 실값이든) 부품 칸은 접힌 값이고 나머지는 부품 칸 없이
    묶은 표와 같다."""
    plan = _part_plan([("DEMO_B", "DEMO_CUSTOM_X", "8H", 30.0), ("DEMO_A", "-", "12H", 70.0)])
    density = _part_density(plan)

    _, detail = build_production_dashboard(plan, density, multi_part=multi_part_products(plan))
    _, without = build_production_dashboard(plan, density, detail_dimensions=["제품정보", "Stack"])

    assert set(detail["CUSTOM"]) == {PART_NOT_SPLIT}
    pd.testing.assert_frame_equal(detail.drop(columns=["CUSTOM"]), without)


def test_parts_stand_in_the_part_order_without_a_display_rule() -> None:
    """규칙이 없으면 표시순서는 받은 차례 그대로라 부품 차례를 미리 세운다 — 대소문자를 접은 글자
    오름차순, 표지 `-` 는 끝(피벗은 `-` 를 글자 앞에, 대문자를 소문자 앞에 둔다)."""
    plan = _part_plan(
        [
            ("DEMO_A", "-", "8H", 10.0),
            ("DEMO_A", "DEMO_CUSTOM_B", "8H", 20.0),
            ("DEMO_A", "demo_custom_a", "8H", 30.0),
            ("DEMO_B", "-", "8H", 40.0),
        ]
    )

    _, detail = build_production_dashboard(
        plan, _part_density(plan), multi_part=multi_part_products(plan)
    )

    assert _rows(detail) == [
        ("DEMO_A", "demo_custom_a", "8H"),
        ("DEMO_A", "DEMO_CUSTOM_B", "8H"),
        ("DEMO_A", "-", "8H"),
        ("DEMO_B", PART_NOT_SPLIT, "8H"),
    ]


def test_a_stack_rule_keeps_the_rows_of_one_part_together() -> None:
    """Stack 규칙이 걸리면 표시순서 끝 열쇠는 한 제품의 부품을 Stack 마다 번갈아 세운다. 그림은
    부품을 제품 칸 글에 녹여 이름표 단위로 띠를 두르므로 한 부품의 행이 한 띠에 모여야 한다."""
    plan = _part_plan(
        [
            ("DEMO_A", PART_A, "8H", 10.0),
            ("DEMO_A", PART_A, "12H", 20.0),
            ("DEMO_A", PART_B, "8H", 30.0),
            ("DEMO_A", PART_B, "12H", 40.0),
        ]
    )
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["생산 계획"] * 3,
            "탭 구분": ["PKG PLAN"] * 3,
            "정렬우선순위": [1, 2, 2],
            "분류컬럼": ["제품정보", "Stack", "Stack"],
            "정렬방식": ["오름차순", "사용자지정", "사용자지정"],
            "분류값": [None, "12H", "8H"],
            "값표시순서": [None, 1, 2],
            "활성여부": ["Y"] * 3,
        }
    )

    _, detail = build_production_dashboard(
        plan, _part_density(plan), display_order, multi_part=multi_part_products(plan)
    )

    assert _rows(detail) == [
        ("DEMO_A", PART_A, "12H"),
        ("DEMO_A", PART_A, "8H"),
        ("DEMO_A", PART_B, "12H"),
        ("DEMO_A", PART_B, "8H"),
    ]


def _plan_rule(
    priority: int, column: str, mode: str, value: str | None = None, order: int | None = None
) -> tuple[object, ...]:
    return ("생산 계획", "PKG PLAN", priority, column, mode, value, order, "Y")


_PLAN_RULE_COLUMNS = [
    "페이지 구분",
    "탭 구분",
    "정렬우선순위",
    "분류컬럼",
    "정렬방식",
    "분류값",
    "값표시순서",
    "활성여부",
]
_PARTS_IN_KEY_ORDER = [
    "DEMO_A (DEMO_CUSTOM_X)",
    "DEMO_A (DEMO_CUSTOM_Z)",
    "DEMO_B",
    "DEMO_C (DEMO_CUSTOM_W)",
    "DEMO_C (DEMO_CUSTOM_Y)",
]
_PARTS_IN_RULE_ORDER = [
    "DEMO_A (DEMO_CUSTOM_Z)",
    "DEMO_A (DEMO_CUSTOM_X)",
    "DEMO_B",
    "DEMO_C (DEMO_CUSTOM_Y)",
    "DEMO_C (DEMO_CUSTOM_W)",
]


def _parted_detail_and_donut(
    rules: list[tuple[object, ...]],
) -> tuple[list[tuple[str, str]], list[str]]:
    """세 제품(둘은 부품 둘 — 부품마다 Stack 하나)의 계획 세부수량 (이름표, Stack) 차례와 도넛
    칸 차례."""
    plan = _part_plan(
        [
            ("DEMO_A", "DEMO_CUSTOM_X", "8H", 10.0),
            ("DEMO_A", "DEMO_CUSTOM_Z", "12H", 20.0),
            ("DEMO_B", "-", "8H", 5.0),
            ("DEMO_C", "DEMO_CUSTOM_Y", "8H", 7.0),
            ("DEMO_C", "DEMO_CUSTOM_W", "12H", 3.0),
        ]
    )
    display_order = pd.DataFrame(rules, columns=_PLAN_RULE_COLUMNS) if rules else None
    multi_part = multi_part_products(plan)
    wafer = plan[["생산계획년월", "제품정보", "CUSTOM"]].assign(물량=1.0)

    _, detail = build_production_dashboard(
        plan, _part_density(plan), display_order, multi_part=multi_part
    )
    slots = assign_product_slots(
        build_product_volume(plan, wafer, multi_part=multi_part), display_order
    )
    rows = [
        (product if part == PART_NOT_SPLIT else f"{product} ({part})", str(stack))
        for product, part, stack in zip(
            detail["제품정보"], detail["CUSTOM"], detail["Stack"], strict=True
        )
    ]
    return rows, list(slots.order)


@pytest.mark.parametrize(
    ("rules", "expected"),
    [
        pytest.param([], _PARTS_IN_KEY_ORDER, id="no-rule"),
        pytest.param(
            [
                _plan_rule(1, "제품정보", "오름차순"),
                _plan_rule(2, "Stack", "사용자지정", "12H", 1),
                _plan_rule(2, "Stack", "사용자지정", "8H", 2),
            ],
            _PARTS_IN_KEY_ORDER,
            id="product-then-stack",
        ),
        pytest.param(
            [_plan_rule(1, "제품정보", "오름차순"), _plan_rule(2, "CUSTOM", "내림차순")],
            _PARTS_IN_RULE_ORDER,
            id="product-then-custom-descending",
        ),
        pytest.param([_plan_rule(1, "CUSTOM", "오름차순")], _PARTS_IN_KEY_ORDER, id="custom-only"),
        pytest.param(
            [
                _plan_rule(1, "CUSTOM", "사용자지정", "DEMO_CUSTOM_Y", 1),
                _plan_rule(1, "CUSTOM", "사용자지정", "DEMO_CUSTOM_Z", 2),
            ],
            _PARTS_IN_RULE_ORDER,
            id="custom-user-order",
        ),
    ],
)
def test_the_plan_detail_and_the_donut_share_the_part_order(
    rules: list[tuple[object, ...]], expected: list[str]
) -> None:
    """계획 세부수량 띠와 도넛 · 범례 차례는 같은 데이터 · 같은 규칙에서 부품 차례가 같다 — 차례는
    제품 → 부품 → Stack 이다. 부품마다 Stack 이 겹치지 않아도 Stack 규칙이 부품 차례를 정하지 않고,
    `CUSTOM` 규칙은 한 제품 안의 부품 차례만 정해 다른 제품의 부품이 사이에 끼지 않는다."""
    rows, donut = _parted_detail_and_donut(rules)

    assert [label for label, _ in rows] == expected
    assert donut == expected


def test_a_stack_rule_ahead_of_the_product_splits_the_plan_detail_by_stack_as_before() -> None:
    """Stack 규칙이 제품 규칙보다 앞서면 계획 세부수량은 부품을 싣기 전처럼 Stack 마다 나뉘어 선다 —
    한 제품의 부품도 제 Stack 자리에 서고, Stack 이 없는 도넛 · 범례는 부품 차례 그대로다."""
    rows, donut = _parted_detail_and_donut(
        [
            _plan_rule(1, "Stack", "사용자지정", "12H", 1),
            _plan_rule(1, "Stack", "사용자지정", "8H", 2),
        ]
    )

    assert rows == [
        ("DEMO_A (DEMO_CUSTOM_Z)", "12H"),
        ("DEMO_C (DEMO_CUSTOM_W)", "12H"),
        ("DEMO_A (DEMO_CUSTOM_X)", "8H"),
        ("DEMO_B", "8H"),
        ("DEMO_C (DEMO_CUSTOM_Y)", "8H"),
    ]
    assert donut == _PARTS_IN_KEY_ORDER


def test_a_comparison_only_dash_row_stands_beside_the_parts_of_its_product() -> None:
    """비교 계획에서 짝을 못 찾은 행(부품을 가르는 제품의 「제품 (-)」)은 맨 뒤가 아니라 그 제품의
    부품 곁, 부품 차례 끝에 선다. 부품이 하나뿐인 제품의 비교에만 있는 행은 지금처럼 뒤에 붙는다."""
    dimensions = list(PRODUCTION_DETAIL_DIMENSIONS)
    current = pd.DataFrame(
        {
            "제품정보": ["DEMO_A", "DEMO_A", "DEMO_B"],
            "CUSTOM": [PART_A, PART_B, PART_NOT_SPLIT],
            "Stack": ["8H", "8H", "12H"],
            "26.08": [50.0, 50.0, 40.0],
        }
    )
    comparison = pd.DataFrame(
        {
            "제품정보": ["DEMO_A", "DEMO_B", "DEMO_B"],
            "CUSTOM": ["-", PART_NOT_SPLIT, PART_NOT_SPLIT],
            "Stack": ["8H", "12H", "4H"],
            "26.08": [100.0, 40.0, 10.0],
        }
    )

    aligned_current, aligned_comparison = align_detail_with_comparison(
        current, comparison, dimensions
    )

    assert _rows(aligned_current) == [
        ("DEMO_A", PART_A, "8H"),
        ("DEMO_A", PART_B, "8H"),
        ("DEMO_A", "-", "8H"),
        ("DEMO_B", PART_NOT_SPLIT, "12H"),
        ("DEMO_B", PART_NOT_SPLIT, "4H"),
    ]
    assert aligned_current["26.08"].fillna(0.0).tolist() == pytest.approx(
        [50.0, 50.0, 0.0, 40.0, 0.0]
    )
    assert aligned_comparison["26.08"].fillna(0.0).tolist() == pytest.approx(
        [0.0, 0.0, 100.0, 40.0, 10.0]
    )


def test_home_plan_detail_judges_the_parts_on_the_whole_revision_plan() -> None:
    """조회기간에 한 부품만 남아도 그 제품은 부품 이름으로 선다 — 판정은 리비전 계획 전체라 기간 ·
    EDP · 거래선 칸으로 이름표가 흔들리지 않는다(UI-PRF-03)."""
    tables = two_part_tables()
    plan = tables["RQ_PKG_PLAN"]
    months = sorted({int(month) for month in pd.to_numeric(plan["생산계획년월"])})
    late = pd.to_numeric(plan["생산계획년월"]).ge(months[-1])
    only_b_late = plan["CUSTOM"].ne(PART_B) | late
    tables["RQ_PKG_PLAN"] = plan.loc[only_b_late].reset_index(drop=True)
    display_order = tables["RQ_DISPLAY_ORDER"]
    key = simulation_cache.build_home_simulation_cache_key(
        reference_version=1,
        scenario_token=f"plan-detail-parts-{uuid4().hex}",
        start_month=months[0],
        end_month=months[-2],
        display_order=display_order,
        route_exceptions=NO_ROUTE_LOAD_EXCEPTIONS,
    )

    for include_edp in (True, False):
        for include_customer in (False, True):
            detail = simulation_cache.get_home_plan_detail(
                key,
                tables,
                display_order,
                include_edp=include_edp,
                include_customer=include_customer,
            )
            product_rows = detail.loc[detail["제품정보"].eq(TWO_PART_PRODUCT)]
            assert product_rows["CUSTOM"].tolist() == [PART_A]
