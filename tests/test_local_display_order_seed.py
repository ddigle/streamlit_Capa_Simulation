# Purpose: 시험이 로컬 표시순서 시드와 떨어져 돌고, 그 시드 규칙이 부품 차례를 정하는 꼴을 고정한다.

"""로컬 표시순서 시드(`data/input/RQ_DISPLAY_ORDER.csv`)와 시험.

그 파일은 체크아웃마다 다르다 — 사내 PC 에는 그 PC 의 프로필이 있을 수 있고 사외 본 체크아웃에는
검수용 견본이 있으며 CI · 갈래 클론에는 없다. 앱은 공용 프로필이 없을 때 그것을 Git 의 내장 시드보다
먼저 쓴다. 시험은 `tests/conftest.py` 가 그 자리를 없는 곳으로 돌려 늘 Git 의 시드로 돈다.

PKG PLAN 범위에 부품마다 값이 다른 칸(Capa Code)의 규칙이 든 프로필이면 격자의 부품 차례는 그 규칙이
정한다(규칙 칸은 CUSTOM 뒤 칸이어도 부품의 주인 — AGENTS 8장). 시드 규칙만 전제로 한 시험이 로컬
시드가 있는 체크아웃에서만 늘 깨지던 꼴이다. 차례는 프로필로만 정해지고 입력 행 차례와는 상관없다.
"""

from __future__ import annotations

from pathlib import Path

import auto_update_fakes
import pandas as pd
import pytest
from conftest import NO_LOCAL_DISPLAY_ORDER_CSV
from custom_key_tables import PART_A, PART_B, TWO_PART_PRODUCT, two_part_tables
from pandas.testing import assert_frame_equal

from capa_simulation.services import builtin_seed
from capa_simulation.services.core_data_derivation import CUSTOM_BLANK
from capa_simulation.services.display_order_csv import display_order_to_csv
from capa_simulation.services.display_order_scopes import PAGE_PLAN, TAB_PKG_PLAN
from capa_simulation.services.load_calculator import plan_to_edit_table
from capa_simulation.settings import PROJECT_ROOT

# 입력 행 차례를 바꿔 보는 섞기 씨앗 — 몇 개든 차례가 하나로 나와야 한다.
_SHUFFLE_SEEDS = (0, 1, 2, 3, 4)


def test_the_suite_reads_the_tracked_seed_whatever_the_checkout_keeps() -> None:
    """시험의 로컬 시드 자리는 체크아웃의 `data/input` 이 아니고 늘 비어 있다. 그래서 내장 시드도,
    수집 때 시드를 읽은 도우미(`auto_update_fakes`)도 Git 의 시드 JSON 과 같다."""
    checkout_seed = PROJECT_ROOT / "data" / "input" / "RQ_DISPLAY_ORDER.csv"
    assert builtin_seed.LOCAL_DISPLAY_ORDER_CSV_PATH == NO_LOCAL_DISPLAY_ORDER_CSV
    assert builtin_seed.LOCAL_DISPLAY_ORDER_CSV_PATH != checkout_seed
    assert not NO_LOCAL_DISPLAY_ORDER_CSV.exists()

    tracked = builtin_seed.load_tracked_display_order()
    assert_frame_equal(builtin_seed.load_builtin_display_order(), tracked)
    assert_frame_equal(auto_update_fakes.DISPLAY_ORDER, tracked)


def _with_capa_code_rule(rules: pd.DataFrame) -> pd.DataFrame:
    """PKG PLAN 범위에 `Capa Code` 오름차순 규칙 하나를 더한 프로필 — 검수용 견본 프로필 꼴."""
    pkg_plan = rules["탭 구분"].eq(TAB_PKG_PLAN)
    capa_code = pd.DataFrame(
        {
            "페이지 구분": [PAGE_PLAN],
            "탭 구분": [TAB_PKG_PLAN],
            "정렬우선순위": [int(rules.loc[pkg_plan, "정렬우선순위"].max()) + 1],
            "분류컬럼": ["Capa Code"],
            "정렬방식": ["오름차순"],
            "분류값": [None],
            "값표시순서": [None],
            "활성여부": ["Y"],
        }
    )
    return pd.concat([rules, capa_code.astype(rules.dtypes.to_dict())], ignore_index=True)


def _grid_parts(plan: pd.DataFrame, display_order: pd.DataFrame) -> list[str]:
    grid = plan_to_edit_table(plan, display_order)
    rows = grid["제품정보"].eq(TWO_PART_PRODUCT).fillna(False).astype("bool")
    return list(dict.fromkeys(grid.loc[rows, "CUSTOM"].astype(str)))


def test_a_local_seed_rule_on_the_parts_capa_code_orders_the_grid_whatever_the_input_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """로컬 시드가 PKG PLAN 범위에 Capa Code 규칙을 들면 내장 시드가 그 규칙을 싣고, 부품마다 Capa
    Code 가 다른 제품은 격자에서 Capa Code 차례(표지 부품 `DEMO_CAPA_A` → `DEMO_CAPA_A2`)로 선다.
    Git 의 시드면 부품 차례(표지 끝)다. 어느 쪽이든 입력 행을 섞어도 차례는 하나다."""
    # 두 부품 견본은 프로세스에 한 번 만든 시드를 쓴다 — 로컬 시드 자리를 돌리기 **전에** 만들어야
    # 그 캐시에 이 시험의 규칙이 들지 않는다.
    plan = two_part_tables(split_capa_code=True)["RQ_PKG_PLAN"]
    plan = plan.assign(CUSTOM=plan["CUSTOM"].replace({PART_A: CUSTOM_BLANK}))
    orders = [plan, plan.iloc[::-1]]
    orders += [plan.sample(frac=1.0, random_state=seed) for seed in _SHUFFLE_SEEDS]
    tracked = builtin_seed.load_tracked_display_order()

    seed_csv = tmp_path / "RQ_DISPLAY_ORDER.csv"
    seed_csv.write_bytes(display_order_to_csv(_with_capa_code_rule(tracked)))
    monkeypatch.setattr(builtin_seed, "LOCAL_DISPLAY_ORDER_CSV_PATH", seed_csv)
    local = builtin_seed.load_builtin_display_order()
    assert local["분류컬럼"].eq("Capa Code").any()

    assert {tuple(_grid_parts(order, local)) for order in orders} == {(CUSTOM_BLANK, PART_B)}
    assert {tuple(_grid_parts(order, tracked)) for order in orders} == {(PART_B, CUSTOM_BLANK)}
