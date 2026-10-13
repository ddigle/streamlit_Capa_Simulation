# Purpose: 생산 계획 편집표 원본 캐시가 캐시 없는 피벗과 같고 내용·표시순서를 따라 바뀌는지 본다.

"""생산 계획 편집표 원본(PKG PLAN·수율)의 캐시 계약.

편집표는 미적용 편집을 지키려고 닫힌 탭에서도 매 회차 그리므로 원본도 매 회차 필요하다. 그
원본을 (시나리오 내용·편집 기간·표시순서) 키로 꺼낸다. 원본이 낡으면 다음 적용에서 값이 되돌아갈
수 있으므로 키가 바뀌면 반드시 다시 만드는지 본다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from uuid import uuid4

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.services import builtin_seed
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.display_order import prepare_display_order
from capa_simulation.services.display_order_scopes import PAGE_PLAN, TAB_YIELD
from capa_simulation.services.load_calculator import (
    plan_to_edit_table,
    split_editable_yield_rows,
    yield_to_edit_table,
)
from capa_simulation.services.month_filter import filter_month_range

START, END = 202602, 202606


@pytest.fixture(scope="module")
def tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pd.DataFrame]:
    """Git 에 있는 내장 시드. 로컬 `data/input/RQ_DISPLAY_ORDER.csv` 가 있으면 시드가 그것을 읽어
    표시순서 규칙이 PC 마다 달라지므로, 없는 자리를 가리켜 Git 의 시드 JSON 을 쓰게 한다."""
    with pytest.MonkeyPatch.context() as patch:
        missing = tmp_path_factory.mktemp("no_local_display_order") / "RQ_DISPLAY_ORDER.csv"
        patch.setattr(builtin_seed, "LOCAL_DISPLAY_ORDER_CSV_PATH", missing)
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


def _yield_tables(
    key: sc.ScenarioCacheKey, yield_data: pd.DataFrame, display_order: pd.DataFrame
) -> sc.YieldEditTables:
    return sc.get_yield_edit_tables(
        key,
        sc.display_order_digest(display_order),
        _yield_data=yield_data,
        _display_order=prepare_display_order(display_order),
    )


def _with_yield_product_rule(tables: dict[str, pd.DataFrame], mode: str) -> pd.DataFrame:
    """수율 탭의 제품정보 정렬 규칙을 더한 표시순서(내장 시드에는 수율 탭 규칙이 없다)."""
    rules = tables["RQ_DISPLAY_ORDER"]
    rule = rules.loc[rules["페이지 구분"].eq(PAGE_PLAN) & rules["분류컬럼"].eq("제품정보")].head(1)
    assert len(rule) == 1
    rule = rule.assign(**{"탭 구분": TAB_YIELD, "정렬방식": mode})
    return pd.concat([rules, rule], ignore_index=True)


def test_a_new_content_token_rebuilds_the_yield_original(tables: dict[str, pd.DataFrame]) -> None:
    """수율 적용·붙여넣기는 새 토큰을 낸다. 옛 원본(잠근 행 포함)이 남으면 다음 적용이 되돌린다."""
    display_order = tables["RQ_DISPLAY_ORDER"]
    yield_data = _slice(tables, "RQ_YLD")
    edited = yield_data.copy()
    edited["EDS_수율"] = pd.to_numeric(edited["EDS_수율"]) * 0.5
    edited.loc[edited.index[0], "BE_수율"] = 0.0

    before = _yield_tables(_key(), yield_data, display_order)
    after = _yield_tables(_key(), edited, display_order)

    editable, locked = split_editable_yield_rows(edited)
    assert not before.table.equals(after.table)
    assert len(after.locked) == len(before.locked) + 1
    pd.testing.assert_frame_equal(
        after.table,
        yield_to_edit_table(editable, prepare_display_order(display_order), locked=locked),
    )
    pd.testing.assert_frame_equal(after.locked, locked)


def test_a_display_order_change_reorders_the_yield_original(
    tables: dict[str, pd.DataFrame],
) -> None:
    """수율 편집표도 같은 토큰에서 표시순서 지문만 바뀌면 다시 만든다."""
    key = _key()
    yield_data = _slice(tables, "RQ_YLD")

    first = _yield_tables(key, yield_data, _with_yield_product_rule(tables, "오름차순")).table
    second = _yield_tables(key, yield_data, _with_yield_product_rule(tables, "내림차순")).table

    products_first = list(dict.fromkeys(first["제품정보"]))
    assert len(products_first) > 1
    assert products_first == sorted(products_first)
    assert list(dict.fromkeys(second["제품정보"])) == sorted(products_first, reverse=True)


def test_a_hit_does_not_pivot_again(
    tables: dict[str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 키의 두 번째 호출은 피벗을 다시 하지 않는다 — 환산 조건 토글·탭 전환마다 같은 입력으로
    피벗하지 않으려고 둔 캐시다."""
    calls: list[str] = []

    def counting(name: str, function: Callable[..., object]) -> Callable[..., object]:
        def wrapper(*args: object, **kwargs: object) -> object:
            calls.append(name)
            return function(*args, **kwargs)

        return wrapper

    for name in ("plan_to_edit_table", "split_editable_yield_rows", "yield_to_edit_table"):
        monkeypatch.setattr(sc, name, counting(name, getattr(sc, name)))
    key = _key()
    display_order = tables["RQ_DISPLAY_ORDER"]
    plan = _slice(tables, "RQ_PKG_PLAN")
    yield_data = _slice(tables, "RQ_YLD")

    first_plan = _plan_table(key, plan, display_order)
    first_yield = _yield_tables(key, yield_data, display_order)
    assert calls == ["plan_to_edit_table", "split_editable_yield_rows", "yield_to_edit_table"]
    calls.clear()

    pd.testing.assert_frame_equal(_plan_table(key, plan, display_order), first_plan)
    pd.testing.assert_frame_equal(
        _yield_tables(key, yield_data, display_order).table, first_yield.table
    )
    assert calls == []
