# Purpose: 재공 경로·선택지 메모가 옛 계산과 같고 시나리오·표시순서가 바뀌면 다시 세는지 본다.

from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from test_wip_status_page import TEST_SCRIPT

from capa_simulation.components import process_labels as process_labels_module
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_scopes import PAGE_STANDARD_TARGET, TAB_TARGET_CAPACITY
from capa_simulation.services.standard_target_capacity import (
    prepare_standard_target_required_equipment,
)
from capa_simulation.services.wip_status import (
    build_wip_route_scope,
    prepare_wip_route_choices,
    processes_in_step_order,
)


def _display_order(products: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": ["표준 목표"] * len(products),
            "탭 구분": ["목표 Capa"] * len(products),
            "정렬우선순위": [1] * len(products),
            "분류컬럼": ["제품정보"] * len(products),
            "정렬방식": ["사용자지정"] * len(products),
            "분류값": products,
            "값표시순서": list(range(1, len(products) + 1)),
            "활성여부": ["Y"] * len(products),
        }
    )


def _required() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": ["T-Process", "P-Process", "T-Process", "P-Process", "Q-Process"],
            "STEP_SEQ": ["T100", "P100", "T100", "P100", "P200"],
            "제품정보": [" Product-B", "Product-B", "Product-A", "Product-A", "Product-C"],
            "소요기준": ["WF", "CHIP", "WF", "CHIP", "PKG"],
            "양산구분": ["양산"] * 5,
            "WF 구분": ["Core", "Core", "Core", "Core", "DUMMY"],
        }
    )


def test_the_prepared_choices_equal_the_old_page_chain() -> None:
    """옛 화면이 회차마다 하던 차례(표준 목표 규칙 → 경로 범위 → 공정 차례 → 제품 표시순서)와
    같은 값이다."""
    required = _required()
    display_order = _display_order(["Product-C", "Product-B", "Product-A"])

    choices = prepare_wip_route_choices(required, display_order)

    prepared = prepare_standard_target_required_equipment(required)
    routes = build_wip_route_scope(prepared)
    products = apply_display_order(
        routes[["제품정보"]].drop_duplicates().reset_index(drop=True),
        display_order,
        PAGE_STANDARD_TARGET,
        TAB_TARGET_CAPACITY,
    )
    pd.testing.assert_frame_equal(choices.required_equipment, prepared)
    pd.testing.assert_frame_equal(choices.routes, routes)
    assert list(choices.processes) == processes_in_step_order(routes)
    assert list(choices.products) == products["제품정보"].astype(str).tolist()


def test_a_copy_does_not_share_tables() -> None:
    choices = prepare_wip_route_choices(_required(), _display_order(["Product-A"]))
    copied = choices.copy()
    copied.routes.loc[0, "공정"] = "고친 값"
    copied.required_equipment.loc[0, "공정"] = "고친 값"

    assert "고친 값" not in set(choices.routes["공정"])
    assert "고친 값" not in set(choices.required_equipment["공정"])


# 화면: 소요대수 조회 횟수를 세고, 세션 칸으로 content_token·표시순서를 바꿀 수 있게 한 대본.
COUNTING_SCRIPT = (
    TEST_SCRIPT.replace(
        '"content_token": "test-wip-status-page",',
        '"content_token": st.session_state.get("test_token", "test-wip-status-page"),',
    )
    .replace(
        '"분류값": ["Product-B", "Product-A"],',
        '"분류값": st.session_state.get("test_order", ["Product-B", "Product-A"]),',
    )
    .replace(
        """simulation_cache.get_scenario_capacity_and_demand = lambda *_args, **_kwargs: (
    pd.DataFrame(),
    required_equipment.copy(),
)""",
        """def counting_capacity_and_demand(*_args, **_kwargs):
    st.session_state["demand_calls"] = st.session_state.get("demand_calls", 0) + 1
    return pd.DataFrame(), required_equipment.copy()


simulation_cache.get_scenario_capacity_and_demand = counting_capacity_and_demand""",
    )
)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    assert COUNTING_SCRIPT.count("test_token") == 1
    assert COUNTING_SCRIPT.count("test_order") == 1
    assert "counting_capacity_and_demand" in COUNTING_SCRIPT
    monkeypatch.setattr(
        process_labels_module,
        "load_global_process_rename",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DB 를 읽으면 안 됩니다")),
    )
    started = AppTest.from_string(COUNTING_SCRIPT, default_timeout=60).run()
    assert not started.exception, [item.message for item in started.exception]
    return started


def test_a_rerun_reuses_the_choices_without_reloading_demand(app: AppTest) -> None:
    options = (app.multiselect[0].options, app.multiselect[1].options)
    assert app.session_state["demand_calls"] == 1

    app.run()

    assert not app.exception
    assert app.session_state["demand_calls"] == 1
    assert (app.multiselect[0].options, app.multiselect[1].options) == options
    assert app.session_state["captured_wip_products"] == ["Product-B", "Product-A"]
    assert app.session_state["captured_wip_steps"] == ["P100", "T100"]


def test_a_new_content_token_reloads_the_demand(app: AppTest) -> None:
    app.session_state["test_token"] = "test-wip-status-page-edited"
    app.run()

    assert not app.exception
    assert app.session_state["demand_calls"] == 2


def test_a_new_display_order_reorders_the_products(app: AppTest) -> None:
    """표시순서는 reference_version 을 바꾸지 않고 바뀐다 — 내용 지문으로 다시 계산한다."""
    app.session_state["test_order"] = ["Product-A", "Product-B"]
    app.run()

    assert not app.exception
    assert app.session_state["demand_calls"] == 2
    assert app.multiselect[1].options == ["Product-A", "Product-B"]
    assert app.session_state["captured_wip_products"] == ["Product-A", "Product-B"]
