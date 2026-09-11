# Purpose: HOME 생산계획·Wafer 부하량·Bottleneck 집계를 검증한다.

import pandas as pd
import pytest

from capa_simulation.services.dashboard import (
    PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    align_detail_with_comparison,
    align_monthly_with_comparison,
    build_bottleneck_capacity,
    build_monthly_bottleneck_details,
    build_monthly_bottleneck_details_from_ranking,
    build_monthly_bottleneck_ranking,
    build_monthly_bottleneck_top5,
    build_monthly_bottleneck_top5_from_ranking,
    build_monthly_bottlenecks,
    build_monthly_bottlenecks_from_ranking,
    build_monthly_wafer_load,
    build_production_dashboard,
    build_production_lob_summary,
)


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
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11.0],
            "구분_EQ": [24.0],
        }
    )

    monthly, detail = build_production_dashboard(plan, density_data)

    assert monthly["년월"].tolist() == ["26.08", "26.09"]
    assert monthly["부하량"].tolist() == pytest.approx(
        [100 * 11 * 24 / 100_000, 200 * 11 * 24 / 100_000]
    )
    assert list(detail.columns) == ["제품정보", "Stack", "26.08", "26.09"]
    assert detail.loc[0, "26.08"] == pytest.approx(100.0)
    assert detail.loc[0, "26.09"] == pytest.approx(200.0)


def test_production_dashboard_can_split_the_detail_by_customer() -> None:
    """`상세` 를 켜면 제품·Stack 아래에 거래선이 분류로 더해진다.

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
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11.0],
            "구분_EQ": [24.0],
        }
    )

    _, detail = build_production_dashboard(
        plan,
        density_data,
        detail_dimensions=PRODUCTION_DETAIL_CUSTOMER_DIMENSIONS,
    )

    assert list(detail.columns) == ["제품정보", "Stack", "Customer", "26.08"]
    assert detail["Customer"].tolist() == ["Customer-A", "Customer-B"]
    # 같은 거래선의 두 행은 합쳐지고 다른 거래선은 갈라진다.
    assert detail["26.08"].tolist() == pytest.approx([160.0, 40.0])
    # Density 는 분류와 무관하게 전체 합이다 — 분류를 바꿔도 부하량은 그대로여야 한다.
    _, base_detail = build_production_dashboard(plan, density_data)
    assert base_detail["26.08"].sum() == pytest.approx(detail["26.08"].sum())


def test_customer_order_comes_from_the_shared_display_order_profile() -> None:
    """거래선 정렬은 표시순서 관리에 `Customer` 규칙을 넣으면 그대로 걸린다.

    `apply_display_order` 는 데이터에 없는 분류컬럼 규칙을 건너뛴다. 그래서 같은 규칙이
    `상세` 를 끈 화면에서는 아무 일도 하지 않고, 켠 화면에서만 거래선 순서를 정한다.
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
    density_data = pd.DataFrame(
        {
            "제품정보": ["HBM다E"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [11.0],
            "구분_EQ": [24.0],
        }
    )
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량", "부하량"],
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
    assert list(base_detail.columns) == ["제품정보", "Stack", "26.08"]


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
    density_data = pd.DataFrame(
        {
            "제품정보": ["제품B", "제품A", "제품A"],
            "Stack": ["8H", "8H", "12H"],
            "WF 구분": ["Core", "Core", "Core"],
            "구분_Chip": [1.0, 1.0, 1.0],
            "구분_EQ": [1.0, 1.0, 1.0],
        }
    )
    display_order = pd.DataFrame(
        {
            "페이지 구분": ["부하량"] * 4,
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

    result = build_monthly_bottlenecks(securement)

    assert result["년월"].tolist() == ["26.08", "26.09"]
    assert result["공정"].tolist() == ["Process-A", "Process-D"]
    assert result["확보율"].tolist() == pytest.approx([0.8, 0.9])
    assert result["축레이블"].tolist() == [
        "26.08<br>Process-A",
        "26.09<br>Process-D",
    ]

    filtered = build_monthly_bottlenecks(securement, included_processes=["Process-B", "Process-C"])
    assert filtered["공정"].tolist() == ["Process-B", "Process-C"]

    excluded = build_monthly_bottlenecks(securement, included_processes=[])
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

    result = build_monthly_bottleneck_top5(
        securement,
        monthly_density,
        included_processes=[f"Process-{index}" for index in range(6)],
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

    # 상한이 유효 공정 수보다 크면 있는 만큼만 나온다.
    result = build_monthly_bottleneck_details(
        securement,
        monthly_wafer,
        included_processes=included,
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
    limited = build_monthly_bottleneck_details(
        securement,
        monthly_wafer,
        included_processes=included,
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
    chip_qty = pd.DataFrame(
        {
            "제품정보": ["Product-A"],
            "Stack": ["12H"],
            "WF 구분": ["Core"],
            "구분_Chip": [2.0],
            "Net Die": [500.0],
        }
    )
    density = pd.DataFrame({"생산계획년월": [202608], "년월": ["26.08"], "부하량": [10.0]})
    bottleneck = pd.DataFrame({"생산계획년월": [202608], "공정": ["Process-A"], "확보율": [1.1]})

    wafer = build_monthly_wafer_load(plan, yield_data, chip_qty)
    summary = build_production_lob_summary(density, wafer, bottleneck)

    assert wafer.loc[0, "Wafer 부하량"] == pytest.approx(150 * 1_000 * 2 / 0.8 / 0.5 / 500)
    assert summary.loc[0, "Wafer Capa"] == pytest.approx(wafer.loc[0, "Wafer 부하량"] * 1.1)


def test_monthly_comparison_leaves_a_missing_month_blank_instead_of_zero() -> None:
    """비교 대상에 없는 달과 계획이 0 인 달은 다른 이야기다.

    없는 달을 0 으로 채우면 그 달이 전액 증가로 읽힌다.
    """
    current = pd.DataFrame({"생산계획년월": [202601, 202602], "부하량": [10.0, 20.0]})
    comparison = pd.DataFrame({"생산계획년월": [202601], "부하량": [8.0]})

    aligned = align_monthly_with_comparison(current, comparison, "부하량")

    assert aligned["비교값"].tolist()[0] == pytest.approx(8.0)
    assert pd.isna(aligned["비교값"].tolist()[1])


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
