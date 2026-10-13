# Purpose: 생산 계획 편집표 원본 캐시가 고치기 전과 같고 내용·표시순서를 따라 다시 만드는지 본다.

"""생산 계획 편집표 원본(PKG PLAN·수율)의 캐시 계약.

편집표는 미적용 편집을 지키려고 닫힌 탭에서도 매 회차 그리므로 원본도 매 회차 필요하다. 그
원본을 (시나리오 내용·편집 기간·표시순서) 키로 꺼낸다. 원본이 낡으면 다음 적용에서 값이 되돌아갈
수 있으므로 키가 바뀌면 반드시 다시 만드는지 본다.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.display_order import prepare_display_order
from capa_simulation.services.display_order_scopes import PAGE_PLAN
from capa_simulation.services.load_calculator import (
    plan_to_edit_table,
    split_editable_yield_rows,
    yield_to_edit_table,
)
from capa_simulation.services.month_filter import filter_month_range

START, END = 202602, 202606


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return dict(build_builtin_seed_dataset().reference_tables)


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    yield
    st.cache_data.clear()


def _key() -> sc.ScenarioCacheKey:
    return (1, f"test-plan-edit-{uuid4().hex}", START, END)


def _slice(tables: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    return filter_month_range(tables[name], START, END, name)


def _plan_table(
    key: sc.ScenarioCacheKey, plan: pd.DataFrame, display_order: pd.DataFrame
) -> pd.DataFrame:
    return sc.get_plan_edit_table(
        key,
        sc.display_order_digest(display_order),
        _plan=plan,
        _display_order=prepare_display_order(display_order),
    )


def test_the_cached_originals_match_the_old_pivots(tables: dict[str, pd.DataFrame]) -> None:
    key = _key()
    display_order = tables["RQ_DISPLAY_ORDER"]
    prepared = prepare_display_order(display_order)
    plan = _slice(tables, "RQ_PKG_PLAN")
    yield_data = _slice(tables, "RQ_YLD")
    editable, locked = split_editable_yield_rows(yield_data)

    pd.testing.assert_frame_equal(
        _plan_table(key, plan, display_order), plan_to_edit_table(plan, prepared)
    )
    cached = sc.get_yield_edit_tables(
        key,
        sc.display_order_digest(display_order),
        _yield_data=yield_data,
        _display_order=prepared,
    )
    pd.testing.assert_frame_equal(
        cached.table, yield_to_edit_table(editable, prepared, locked=locked)
    )
    pd.testing.assert_frame_equal(cached.locked, locked)


def test_a_new_content_token_rebuilds_the_plan_original(tables: dict[str, pd.DataFrame]) -> None:
    """적용·붙여넣기 적용·가상 제품 등록은 새 토큰을 낸다. 옛 원본이 남으면 다음 적용이 되돌린다."""
    display_order = tables["RQ_DISPLAY_ORDER"]
    plan = _slice(tables, "RQ_PKG_PLAN")
    edited = plan.copy()
    edited["생산수량"] = pd.to_numeric(edited["생산수량"]) * 0.5

    before = _plan_table(_key(), plan, display_order)
    after = _plan_table(_key(), edited, display_order)

    assert not before.equals(after)
    pd.testing.assert_frame_equal(
        after, plan_to_edit_table(edited, prepare_display_order(display_order))
    )


def test_a_display_order_change_reorders_the_plan_original(
    tables: dict[str, pd.DataFrame],
) -> None:
    """표시순서는 content_token 을 바꾸지 않고 바뀐다. 같은 토큰이라도 지문이 다르면 다시 만든다."""
    key = _key()
    plan = _slice(tables, "RQ_PKG_PLAN")
    ascending = tables["RQ_DISPLAY_ORDER"]
    descending = ascending.copy()
    target = descending["페이지 구분"].eq(PAGE_PLAN) & descending["분류컬럼"].eq("제품정보")
    assert target.any()
    descending.loc[target, "정렬방식"] = "내림차순"

    first = _plan_table(key, plan, ascending)
    second = _plan_table(key, plan, descending)

    products_first = list(dict.fromkeys(first["제품정보"]))
    products_second = list(dict.fromkeys(second["제품정보"]))
    assert products_first == sorted(products_first)
    assert products_second == sorted(products_first, reverse=True)


def test_a_yield_table_error_is_raised_every_time(tables: dict[str, pd.DataFrame]) -> None:
    """표를 세울 수 없는 원천(연결 키 결측)은 캐시되지 않고 매 회차 다시 난다."""
    key = _key()
    broken = _slice(tables, "RQ_YLD").copy()
    broken.loc[broken.index[0], "제품정보"] = None
    display_order = tables["RQ_DISPLAY_ORDER"]

    for _ in range(2):
        with pytest.raises(ValueError):
            sc.get_yield_edit_tables(
                key,
                sc.display_order_digest(display_order),
                _yield_data=broken,
                _display_order=prepare_display_order(display_order),
            )
