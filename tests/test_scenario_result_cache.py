# Purpose: 산출 결과·Static Capa 의 키 전용 파생 캐시가 같은 값을 내고 제때 무효화되는지 본다.

"""대당 Capa·소요대수 프레임을 풀지 않는 파생 캐시(확보율·요약·월 표)의 계약.

적중 경로에서 큰 프레임(pickle 약 16MB, 합성 표본의 샘플 관측)을 풀지 않으려고 파생값을 키로
캐시했다. 지키는 것은 셋이다.

- **같은 숫자** — 고치기 전 페이지가 프레임에서 바로 만들던 값과 같다.
- **무효화** — 키의 시나리오 내용(content_token)·표시순서 지문이 바뀌면 다시 만든다.
- **적중이면 프레임을 받지 않는다** — 그래야 이 캐시를 둔 까닭이 선다.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset
from capa_simulation.services.display_order import (
    apply_display_order,
    prepare_display_order,
    reorder_display_columns,
)
from capa_simulation.services.display_order_scopes import (
    PAGE_CALCULATION,
    TAB_REQUIRED,
    TAB_UNIT_CAPACITY,
)
from capa_simulation.services.month_filter import filter_month_range
from capa_simulation.services.required_equipment import (
    REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR,
    RESULT_DIMENSIONS,
    required_equipment_to_month_table,
)
from capa_simulation.services.securement_rate import calculate_securement_rate
from capa_simulation.services.unit_capacity import (
    CAPACITY_EXCLUSIONS_ATTR,
    UNIT_CAPACITY_DIMENSIONS,
    capacity_assumptions,
    unit_capacity_to_month_table,
)
from capa_simulation.services.weighted_unit_capacity import (
    effective_process_capacity_to_month_table,
)

START, END = 202602, 202605


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return dict(build_builtin_seed_dataset().reference_tables)


@pytest.fixture
def key() -> sc.ScenarioCacheKey:
    # st.cache_data 는 프로세스 전역이다. 테스트마다 토큰을 새로 만들어 칸을 나눠 쓰지 않는다.
    return (1, f"test-result-cache-{uuid4().hex}", START, END)


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[sc.ScenarioCacheKey]]:
    """`get_scenario_capacity_and_demand` 를 부른 키를 적는다(계산은 그대로 한다)."""
    calls: list[sc.ScenarioCacheKey] = []
    original = sc.get_scenario_capacity_and_demand

    def recording(
        cache_key: sc.ScenarioCacheKey, **kwargs: object
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        calls.append(cache_key)
        return original(cache_key, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sc, "get_scenario_capacity_and_demand", recording)
    yield calls


def _frames(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return sc.get_scenario_capacity_and_demand(
        key, _scenario_tables=tables, _reference_tables=tables
    )


def _available(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return filter_month_range(tables["RQ_EQP_AVBL"], START, END, "RQ_EQP_AVBL")


def _descending(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """`산출 결과` 의 공정 규칙만 내림차순으로 뒤집은 표시순서."""
    flipped = tables["RQ_DISPLAY_ORDER"].copy()
    target = flipped["페이지 구분"].eq(PAGE_CALCULATION) & flipped["분류컬럼"].eq("공정")
    flipped.loc[target, "정렬방식"] = "내림차순"
    return {**tables, "RQ_DISPLAY_ORDER": flipped}


def test_securement_rate_matches_the_old_page_path(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    _, required = _frames(key, tables)
    expected = calculate_securement_rate(_available(tables), required)

    cached = sc.get_scenario_securement_rate(
        key,
        _scenario_tables=tables,
        _reference_tables=tables,
        _available_equipment=_available(tables),
    )

    pd.testing.assert_frame_equal(cached, expected)


def test_summary_matches_the_old_page_path(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    unit, required = _frames(key, tables)

    summary = sc.get_scenario_result_summary(key, _scenario_tables=tables, _reference_tables=tables)

    pd.testing.assert_frame_equal(
        summary.capacity_exclusions, unit.attrs.get(CAPACITY_EXCLUSIONS_ATTR, pd.DataFrame())
    )
    pd.testing.assert_frame_equal(
        summary.required_exclusions,
        required.attrs.get(REQUIRED_EQUIPMENT_EXCLUSIONS_ATTR, pd.DataFrame()),
    )
    assert summary.capacity_assumptions == capacity_assumptions(unit)
    assert summary.unit_capacity_rows == len(unit)
    display_order = prepare_display_order(tables["RQ_DISPLAY_ORDER"])
    expected_processes = (
        apply_display_order(
            required[["공정"]].drop_duplicates(), display_order, PAGE_CALCULATION, TAB_UNIT_CAPACITY
        )["공정"]
        .astype(str)
        .tolist()
    )
    assert (
        sc.get_display_ordered_values(
            summary.processes,
            sc.display_order_digest(tables["RQ_DISPLAY_ORDER"]),
            PAGE_CALCULATION,
            TAB_UNIT_CAPACITY,
            _display_order=display_order,
        )
        == expected_processes
    )


def test_month_tables_match_the_old_page_path(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    _, required = _frames(key, tables)
    display_order = prepare_display_order(tables["RQ_DISPLAY_ORDER"])
    expected = apply_display_order(
        required_equipment_to_month_table(required), display_order, PAGE_CALCULATION, TAB_REQUIRED
    )
    expected, expected_dimensions = reorder_display_columns(
        expected, RESULT_DIMENSIONS, display_order, PAGE_CALCULATION, TAB_REQUIRED
    )

    table, dimensions = sc.get_required_month_table(
        key,
        sc.display_order_digest(tables["RQ_DISPLAY_ORDER"]),
        PAGE_CALCULATION,
        TAB_REQUIRED,
        _scenario_tables=tables,
        _reference_tables=tables,
        _display_order=display_order,
    )

    pd.testing.assert_frame_equal(table, expected)
    assert dimensions == expected_dimensions
    for level in ("공정", "제품정보", "WF 구분"):
        pd.testing.assert_frame_equal(
            sc.get_effective_process_capacity_table(
                key, _scenario_tables=tables, _reference_tables=tables, detail_level=level
            ),
            effective_process_capacity_to_month_table(required, level),
        )


def test_a_hit_does_not_unpickle_the_capacity_frames(
    key: sc.ScenarioCacheKey,
    tables: dict[str, pd.DataFrame],
    counted: list[sc.ScenarioCacheKey],
) -> None:
    display_order = prepare_display_order(tables["RQ_DISPLAY_ORDER"])
    digest = sc.display_order_digest(tables["RQ_DISPLAY_ORDER"])

    def everything() -> None:
        sc.check_scenario_capacity(key, _scenario_tables=tables, _reference_tables=tables)
        sc.get_scenario_securement_rate(
            key,
            _scenario_tables=tables,
            _reference_tables=tables,
            _available_equipment=_available(tables),
        )
        sc.get_scenario_result_summary(key, _scenario_tables=tables, _reference_tables=tables)
        sc.get_required_month_table(
            key,
            digest,
            PAGE_CALCULATION,
            TAB_REQUIRED,
            _scenario_tables=tables,
            _reference_tables=tables,
            _display_order=display_order,
        )
        sc.get_effective_process_capacity_table(
            key, _scenario_tables=tables, _reference_tables=tables, detail_level="공정"
        )

    everything()
    assert counted, "첫 호출은 계산 결과를 받아야 한다"
    counted.clear()

    everything()

    assert counted == []


def test_a_new_content_token_recomputes(tables: dict[str, pd.DataFrame]) -> None:
    """편집 적용은 새 content_token 을 낸다. 같은 기간이라도 새 내용으로 다시 만든다."""
    before_key: sc.ScenarioCacheKey = (1, f"test-result-before-{uuid4().hex}", START, END)
    after_key: sc.ScenarioCacheKey = (1, f"test-result-after-{uuid4().hex}", START, END)
    edited = dict(tables)
    available = tables["RQ_EQP_AVBL"].copy()
    available["가용대수"] = pd.to_numeric(available["가용대수"]) * 2
    edited["RQ_EQP_AVBL"] = available
    upeh = tables["RQ_UPEH"].copy()
    upeh["UPEH"] = pd.to_numeric(upeh["UPEH"]) * 0.5
    edited["RQ_UPEH"] = upeh

    before = sc.get_scenario_securement_rate(
        before_key,
        _scenario_tables=tables,
        _reference_tables=tables,
        _available_equipment=_available(tables),
    )
    after = sc.get_scenario_securement_rate(
        after_key,
        _scenario_tables=edited,
        _reference_tables=edited,
        _available_equipment=_available(edited),
    )
    _, edited_required = _frames(after_key, edited)

    assert not before.equals(after)
    pd.testing.assert_frame_equal(
        after, calculate_securement_rate(_available(edited), edited_required)
    )
    before_table = sc.get_effective_process_capacity_table(
        before_key, _scenario_tables=tables, _reference_tables=tables, detail_level="공정"
    )
    after_table = sc.get_effective_process_capacity_table(
        after_key, _scenario_tables=edited, _reference_tables=edited, detail_level="공정"
    )
    assert not before_table.equals(after_table)
    pd.testing.assert_frame_equal(
        after_table, effective_process_capacity_to_month_table(edited_required, "공정")
    )


def test_a_display_order_change_reorders_the_cached_tables(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    """표시순서는 `reference_version`·content_token 을 바꾸지 않고 바뀐다. 지문이 키다."""
    flipped = _descending(tables)

    def ordered(source: dict[str, pd.DataFrame]) -> tuple[list[str], list[str]]:
        display_order = prepare_display_order(source["RQ_DISPLAY_ORDER"])
        digest = sc.display_order_digest(source["RQ_DISPLAY_ORDER"])
        table, _ = sc.get_required_month_table(
            key,
            digest,
            PAGE_CALCULATION,
            TAB_REQUIRED,
            _scenario_tables=tables,
            _reference_tables=tables,
            _display_order=display_order,
        )
        summary = sc.get_scenario_result_summary(
            key, _scenario_tables=tables, _reference_tables=tables
        )
        processes = sc.get_display_ordered_values(
            summary.processes,
            digest,
            PAGE_CALCULATION,
            TAB_UNIT_CAPACITY,
            _display_order=display_order,
        )
        return list(dict.fromkeys(table["공정"].astype(str))), processes

    ascending_table, ascending_processes = ordered(tables)
    descending_table, descending_processes = ordered(flipped)

    assert ascending_table == sorted(ascending_table)
    assert descending_table == sorted(ascending_table, reverse=True)
    assert ascending_processes == sorted(ascending_processes)
    assert descending_processes == sorted(ascending_processes, reverse=True)


def test_a_failing_scenario_is_raised_every_time_and_never_cached(
    tables: dict[str, pd.DataFrame],
) -> None:
    """실패는 캐시되지 않는다 — 오류가 난 시나리오는 매 회차 같은 자리에서 다시 멈춘다."""
    broken = dict(tables)
    run_rate = tables["RQ_RUN_RATE"]
    months = pd.to_numeric(run_rate["생산계획년월"])
    broken["RQ_RUN_RATE"] = run_rate.loc[months.ne(START)].reset_index(drop=True)
    broken_key: sc.ScenarioCacheKey = (1, f"test-result-broken-{uuid4().hex}", START, END)

    for _ in range(2):
        with pytest.raises(ValueError):
            sc.check_scenario_capacity(
                broken_key, _scenario_tables=broken, _reference_tables=broken
            )
        with pytest.raises(ValueError):
            sc.get_scenario_result_summary(
                broken_key, _scenario_tables=broken, _reference_tables=broken
            )


@pytest.fixture(autouse=True)
def _quiet_cache() -> Iterator[None]:
    yield
    st.cache_data.clear()


# ------------------------------------------------- STEP별 대당 Capa 월표(S8)


def _step_table(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame], display_order: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    return sc.get_step_unit_capacity_table(
        key,
        sc.display_order_digest(display_order),
        PAGE_CALCULATION,
        TAB_UNIT_CAPACITY,
        _scenario_tables=tables,
        _reference_tables=tables,
        _display_order=prepare_display_order(display_order),
    )


def _old_step_table(
    unit: pd.DataFrame, display_order: pd.DataFrame, processes: list[str]
) -> pd.DataFrame:
    """고치기 전 화면 — 전 공정 피벗 → 정렬 → 재배치 → 공정 거르기."""
    prepared = prepare_display_order(display_order)
    table = apply_display_order(
        unit_capacity_to_month_table(unit), prepared, PAGE_CALCULATION, TAB_UNIT_CAPACITY
    )
    table, _ = reorder_display_columns(
        table, list(UNIT_CAPACITY_DIMENSIONS), prepared, PAGE_CALCULATION, TAB_UNIT_CAPACITY
    )
    return table.loc[table["공정"].isin(processes)].reset_index(drop=True)


def test_the_step_table_matches_the_old_page_path(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    unit, _ = _frames(key, tables)
    display_order = tables["RQ_DISPLAY_ORDER"]
    processes = sorted(set(unit["공정"].astype(str)))

    table, dimensions = _step_table(key, tables, display_order)

    _, expected_dimensions = reorder_display_columns(
        unit_capacity_to_month_table(unit),
        list(UNIT_CAPACITY_DIMENSIONS),
        prepare_display_order(display_order),
        PAGE_CALCULATION,
        TAB_UNIT_CAPACITY,
    )
    assert dimensions == expected_dimensions
    for selected in ([processes[0]], processes[1:], processes):
        filtered = table.loc[table["공정"].isin(selected)].reset_index(drop=True)
        pd.testing.assert_frame_equal(filtered, _old_step_table(unit, display_order, selected))


def test_the_step_table_follows_the_display_order(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    ascending, _ = _step_table(key, tables, tables["RQ_DISPLAY_ORDER"])
    descending, _ = _step_table(key, tables, _descending(tables)["RQ_DISPLAY_ORDER"])

    order = list(dict.fromkeys(ascending["공정"].astype(str)))
    assert order == sorted(order)
    assert list(dict.fromkeys(descending["공정"].astype(str))) == sorted(order, reverse=True)


def test_a_step_table_hit_does_not_unpickle_the_capacity_frames(
    key: sc.ScenarioCacheKey,
    tables: dict[str, pd.DataFrame],
    counted: list[sc.ScenarioCacheKey],
) -> None:
    _step_table(key, tables, tables["RQ_DISPLAY_ORDER"])
    assert counted == [key]
    counted.clear()

    _step_table(key, tables, tables["RQ_DISPLAY_ORDER"])

    assert counted == []
