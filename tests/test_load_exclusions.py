# Purpose: 기준정보가 없는 계획 행이 페이지를 멈추지 않고 제외 목록으로 보고되는지 고정한다.

import pandas as pd

from capa_simulation.services.load_calculator import (
    build_monthly_volume,
    calculate_chip_and_wafer_loads,
    calculate_density_load,
    load_exclusions,
)

# 예전에는 조인 실패가 예외였다. 계획 행 하나에 RQ_YLD 가 없으면 부하량·확보율 페이지가
# 통째로 멈췄고, 사용자는 "RQ_YLD가 연결되지 않는 기준이 있습니다" 만 보고 어느 제품이
# 문제인지 알 수 없었다. 신규 제품을 복제 등록할 때도 같은 벽에 부딪힌다.

PLAN = pd.DataFrame(
    {
        "생산계획년월": [202601, 202601, 202601],
        "양산구분": ["양산"] * 3,
        "제품정보": ["DEMO_OK", "DEMO_NO_CHIP", "DEMO_NO_YLD"],
        "Stack": ["8H"] * 3,
        "Capa Code": ["C1", "C2", "C3"],
        "Customer": ["DEMO_CUST"] * 3,
        "CS": ["MP"] * 3,
        "생산수량": [100.0, 50.0, 70.0],
    }
)
CHIP = pd.DataFrame(
    {
        "제품정보": ["DEMO_OK", "DEMO_NO_YLD"],
        "Stack": ["8H", "8H"],
        "WF 구분": ["Core", "Core"],
        "구분_Chip": [4.0, 4.0],
        "Net Die": [100.0, 100.0],
    }
)
YIELD = pd.DataFrame(
    {
        "생산계획년월": [202601],
        "제품정보": ["DEMO_OK"],
        "Stack": ["8H"],
        "WF 구분": ["Core"],
        "EDS_수율": [0.9],
        "BE_수율": [0.95],
    }
)


def test_missing_reference_excludes_only_that_product() -> None:
    chip_load, wafer_load = calculate_chip_and_wafer_loads(PLAN, YIELD, CHIP)

    assert sorted(set(chip_load["제품정보"])) == ["DEMO_OK"]
    assert sorted(set(wafer_load["제품정보"])) == ["DEMO_OK"]


def test_exclusion_list_names_the_product_and_the_missing_table() -> None:
    chip_load, _ = calculate_chip_and_wafer_loads(PLAN, YIELD, CHIP)

    excluded = load_exclusions(chip_load)

    assert dict(zip(excluded["제품정보"], excluded["누락 기준정보"], strict=True)) == {
        "DEMO_NO_CHIP": "RQ_CHIP_QTY",
        "DEMO_NO_YLD": "RQ_YLD",
    }


def test_load_frames_still_concatenate() -> None:
    """제외 목록을 attrs 에 DataFrame 으로 담으면 pd.concat 이 죽는다.

    pandas 가 attrs 를 동등 비교하는데 DataFrame 끼리 비교하면 불리언이 되지 않는다.
    소요대수 계산이 Chip·Wafer 부하량을 실제로 concat 하므로 레코드 튜플로 담는다.
    """
    chip_load, wafer_load = calculate_chip_and_wafer_loads(PLAN, YIELD, CHIP)

    combined = pd.concat([chip_load, wafer_load], ignore_index=True)

    assert len(combined) == len(chip_load) + len(wafer_load)


def test_monthly_volume_carries_the_exclusion_list() -> None:
    """환산 결과까지 목록이 따라와야 화면이 보여줄 수 있다. pivot 은 attrs 를 잃는다."""
    volume = build_monthly_volume(PLAN, YIELD, CHIP, demand_basis="Chip", display_order=None)

    assert sorted(set(load_exclusions(volume)["제품정보"])) == ["DEMO_NO_CHIP", "DEMO_NO_YLD"]


def test_no_exclusions_yields_an_empty_frame() -> None:
    complete_plan = PLAN.loc[PLAN["제품정보"].eq("DEMO_OK")]

    chip_load, _ = calculate_chip_and_wafer_loads(complete_plan, YIELD, CHIP)

    assert load_exclusions(chip_load).empty


# Density 만 옛 방식(예외)으로 남아 있었다. 표본에서는 계획의 모든 제품+Stack 이
# `구분_EQ` 를 가진 행을 하나씩 갖고 있어서 — 비는 것은 Buffer·Dummy 뿐이고 Top·Core·
# Master 중 하나는 늘 채워져 있다 — 이 분기를 한 번도 밟지 않았다. 그래서 남아 있었다.
DENSITY = pd.DataFrame(
    {
        "제품정보": ["DEMO_OK"],
        "Stack": ["8H"],
        "WF 구분": ["Core"],
        "구분_Chip": [4.0],
        "구분_EQ": [16.0],
    }
)


def test_density_excludes_the_unmatched_product_instead_of_raising() -> None:
    """용량이 없는 제품 한 줄 때문에 Density 환산과 HOME 이 통째로 멈추면 안 된다."""
    density_load = calculate_density_load(PLAN, DENSITY)

    assert sorted(set(density_load["제품정보"])) == ["DEMO_OK"]
    assert dict(
        zip(
            load_exclusions(density_load)["제품정보"],
            load_exclusions(density_load)["누락 기준정보"],
            strict=True,
        )
    ) == {"DEMO_NO_CHIP": "RQ_CHIP_EQ", "DEMO_NO_YLD": "RQ_CHIP_EQ"}


def test_density_monthly_volume_carries_the_exclusion_list() -> None:
    """pivot 이 attrs 를 잃으므로 Density 경로도 이어붙여야 화면이 보여줄 수 있다."""
    volume = build_monthly_volume(
        PLAN, YIELD, CHIP, demand_basis="Density", density_data=DENSITY, display_order=None
    )

    assert sorted(set(load_exclusions(volume)["제품정보"])) == ["DEMO_NO_CHIP", "DEMO_NO_YLD"]


def test_home_dashboard_survives_a_product_without_density() -> None:
    """HOME 은 이 함수를 그대로 쓴다. 예외가 나면 헤더와 오류 배너만 남았다."""
    from capa_simulation.services.dashboard import build_production_dashboard

    monthly, detail = build_production_dashboard(PLAN, DENSITY)

    # Density 합계는 붙는 제품만 반영한다. PKG Plan 상세는 계획 그대로라 세 제품이 남는다.
    assert not monthly.empty
    assert "DEMO_OK" in set(detail["제품정보"])
