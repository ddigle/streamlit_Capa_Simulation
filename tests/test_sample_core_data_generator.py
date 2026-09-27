# Purpose: 합성 데모 생성기의 계획 재연장이 이음매 없이 같은 결과를 내는지 검증한다.

"""**연장분 위에 다시 연장하면 그 달에 계단이 생겼다.**

`extend_plans` 는 입력의 마지막 달을 원점으로 제품 믹스·계절·성장을 곱한다. 이미 연장된
파일을 다시 넣으면 그 파일의 마지막 달이 새 원점이 되어, 믹스가 한 번 더 곱해지고 계절
위상도 처음부터 다시 시작했다. 202712 까지 연장된 표본을 202812 로 늘렸을 때 202801 에만
계획 합계가 +12.4% 뛰었다(샘플 관측). `data/` 는 커밋하지 않으므로 돌릴 때마다 되풀이된다.

지금은 스크립트가 만든 행을 PLAN ID 로 알아보고 걷어낸 뒤 원본의 마지막 달부터 다시 만든다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "generate_sample_core_data.py"

QUANTITY_COLUMNS = (
    "생산수량",
    "Plan_Chip(K개)",
    "계획(K개)",
    "8H 환산 계획(K개)",
    "WF수(매)",
    "PCB수(K매)",
    "EQ(억Gb)",
    "일 필요",
    "소요대수",
)


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_sample_core_data", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_sample_core_data"] = module
    spec.loader.exec_module(module)
    return module


def _original_plans() -> list[dict[str, str]]:
    """원본 계획 두 달 × 제품 둘. PLAN ID 는 원천 형식이라 연장분과 갈린다."""
    rows: list[dict[str, str]] = []
    for month in (202607, 202608):
        for product, quantity in (("DEMO_A", "100"), ("DEMO_B", "40")):
            row = {
                "기준정보년월": str(month),
                "생산계획년월": str(month),
                "Month": str(month % 10000),
                "제품정보": product,
                "Stack": "4H",
                "Capa Code": "DEMO_CAPA",
                "Customer": "DEMO_CUSTOMER",
                "CS": "MP",
                "PLAN ID": f"ORIGIN-{month}-{product}",
                "시뮬레이션 ID": f"ORIGIN-SIM-{month}-{product}",
            }
            row.update({column: quantity for column in QUANTITY_COLUMNS})
            rows.append(row)
    return rows


def test_extending_an_extended_plan_equals_extending_the_original_once(
    script: ModuleType,
) -> None:
    original = _original_plans()

    direct = script.extend_plans(original, 202706)
    staged = script.extend_plans(script.extend_plans(original, 202612), 202706)

    assert staged == direct


def test_rerunning_on_its_own_output_is_a_fixed_point(script: ModuleType) -> None:
    once = script.extend_plans(_original_plans(), 202612)

    assert script.extend_plans(once, 202612) == once


def test_original_rows_are_kept_and_only_extended_rows_are_recognised(
    script: ModuleType,
) -> None:
    original = _original_plans()
    extended = script.extend_plans(original, 202612)

    assert extended[: len(original)] == original
    assert not any(script.is_extended_plan(row) for row in original)
    assert all(script.is_extended_plan(row) for row in extended[len(original) :])


def test_an_earlier_target_month_does_not_shrink_the_input_range(script: ModuleType) -> None:
    extended = script.extend_plans(_original_plans(), 202612)

    assert script.extend_plans(extended, 202609) == extended
