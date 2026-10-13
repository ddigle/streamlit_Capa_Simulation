# Purpose: 표준 목표 주간 캐시가 5만 행 넘는 소요대수의 한 행 편집도 반영하는지 고정한다.

"""표준 목표 주간 캐시의 키 계약 (회귀).

Streamlit 1.63 은 5만 행 이상인 DataFrame 인자를 1만 행 표본으로만 해시한다. 표준 목표가 주간
캐시에 소요대수 상세(사내·합성 모두 5만 행 넘음)를 해시 인자로 넘기던 동안, 표본 밖 한 행만
바뀌는 편집(UPEH·REQB 한 칸)을 적용해도 캐시가 옛 결과를 돌려줬다 — 화면에 틀린 숫자가 남는다.

여기서는 두 시나리오 내용(편집 전·후, 토큰이 다르다)을 같은 프로세스에서 차례로 그려, 뒤
화면이 편집 뒤 소요대수로 새로 계산한 값을 보이는지 본다.
"""

from collections.abc import Iterator
from datetime import date

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.services.display_order import apply_display_order, prepare_display_order
from capa_simulation.services.display_order_scopes import (
    PAGE_STANDARD_TARGET,
    TAB_TARGET_CAPACITY,
)
from capa_simulation.services.standard_target_capacity import (
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
    exclude_er_required_equipment,
    split_standard_target_required_equipment,
    weekly_standard_target_to_wide,
)

ROWS_PER_PROCESS = 6_000
PROCESSES = [f"P{index:02d}" for index in range(10)]
MONTH = 202608
WEEKS = ["26-W32", "26-W33", "26-W34", "26-W35"]


def required_frame() -> pd.DataFrame:
    """공정 10개 × 원수요 6천 줄 = 6만 행. 행마다 원수요가 달라 한 행이 공정 값을 바꾼다."""
    rows = len(PROCESSES) * ROWS_PER_PROCESS
    index = pd.RangeIndex(rows)
    return pd.DataFrame(
        {
            "생산계획년월": MONTH,
            "공정": [PROCESSES[i // ROWS_PER_PROCESS] for i in index],
            "소요기준": "WF",
            "양산구분": "양산",
            "제품정보": [f"Prod-{i % ROWS_PER_PROCESS:05d}" for i in index],
            "Stack": "8H",
            "Capa Code": "CAPA",
            "Customer": "Customer",
            "CS": "MP",
            "WF 구분": "Core",
            "부하량": [100.0 + (i % 7) for i in index],
            "소요대수": [1.0 + (i % 3) * 0.5 for i in index],
        }
    )


def out_of_sample_row(frame: pd.DataFrame) -> int:
    """Streamlit 이 해시할 1만 행 표본(기본 시드 0)에 들지 않는 행 하나."""
    sampled = set(frame.sample(n=10_000, random_state=0).index)
    return next(int(row) for row in frame.index if row not in sampled and row > 0)


SCRIPT = r"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation
import capa_simulation.components.hierarchical_monthly_table as hierarchical_table
import capa_simulation.components.process_labels as process_labels_module
import capa_simulation.io.reference_cache as reference_cache
import capa_simulation.persistence.equipment_cache as equipment_cache
import capa_simulation.scenario_state as scenario_state
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.services.month_filter import filter_month_range

required_equipment = pd.read_pickle(REQUIRED_PATH)
processes = sorted(required_equipment["공정"].unique())
weeks = ["26-W32", "26-W33", "26-W34", "26-W35", "26-W36"]
display_order = pd.DataFrame(
    columns=[
        "페이지 구분", "탭 구분", "정렬우선순위", "분류컬럼", "정렬방식", "분류값",
        "값표시순서", "활성여부",
    ]
)
scenario_tables = {
    name: pd.DataFrame()
    for name in (
        "RQ_RUN_RATE", "RQ_VITAL", "RQ_LOT_RATIO", "RQ_WF_RATIO", "RQ_YLD",
        "RQ_CHIP_QTY", "RQ_CHIP_EQ",
    )
}
scenario_tables["RQ_UPEH"] = pd.DataFrame({"생산계획년월": [202608]})
scenario_tables["RQ_RUN_DAY"] = pd.DataFrame(
    {
        "생산계획년월": [202608] * len(processes),
        "공정": processes,
        "RUN_DAY": [31.0] * len(processes),
    }
)
scenario_tables["RQ_PKG_PLAN"] = pd.DataFrame(
    {
        "생산계획년월": [202608], "양산구분": ["양산"], "제품정보": ["Prod-00000"], "Stack": ["8H"],
        "Capa Code": ["CAPA"], "Customer": ["Customer"], "CS": ["MP"], "생산수량": [50.0],
    }
)
scenario_tables["RQ_REQB"] = pd.DataFrame(
    {"공정": processes, "양산구분": ["양산"] * len(processes)}
)
active = {
    "reference_version": 1,
    "revision": 1,
    "content_token": CONTENT_TOKEN,
    "tables": scenario_tables,
}
reference_tables = {
    "RQ_MODULE": pd.DataFrame(),
    "RQ_CHIP_QTY": pd.DataFrame(),
    "RQ_DISPLAY_ORDER": display_order,
}
availability = pd.DataFrame(
    {
        "공정": [process for process in processes for _ in weeks],
        "Weeknum": weeks * len(processes),
        "가용대수": [2.0] * (len(processes) * len(weeks)),
    }
)

originals = (
    reference_cache.get_effective_reference_version,
    reference_cache.get_effective_reference_tables,
    equipment_cache.get_equipment_repository,
    scenario_state.ensure_active_scenario,
    scenario_state.scenario_month_table,
    simulation_cache.get_scenario_capacity_and_demand,
    hierarchical_table.render_hierarchical_monthly_table,
    process_labels_module.get_process_labels,
)


class FakeEquipmentRepository:
    schema_ahead = None

    def load_standard_target_availability(self):
        return availability.copy()


def capture_table(data, **kwargs):
    st.session_state["captured_table"] = data.copy()


reference_cache.get_effective_reference_version = lambda: 1
reference_cache.get_effective_reference_tables = lambda: reference_tables
equipment_cache.get_equipment_repository = lambda _path: FakeEquipmentRepository()
scenario_state.ensure_active_scenario = lambda _tables, _version: active
scenario_state.scenario_month_table = lambda scenario, name, start, end: filter_month_range(
    scenario["tables"][name], start, end, name
)
# 운영의 계산 래퍼처럼 키의 토큰이 내용을 정한다 — 토큰이 다르면 다른 프레임이다.
simulation_cache.get_scenario_capacity_and_demand = lambda cache_key, **_kwargs: (
    pd.DataFrame(),
    filter_month_range(required_equipment, cache_key[2], cache_key[3], "소요대수 상세"),
)
hierarchical_table.render_hierarchical_monthly_table = capture_table
process_labels_module.get_process_labels = lambda: process_labels_module.ProcessLabels()

try:
    st.session_state["production_month_range_v2"] = ("2026-08", "2026-08")
    root = Path(capa_simulation.__file__).resolve().parents[2]
    page = root / "app_pages" / "standard_target_capa.py"
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"))
finally:
    (
        reference_cache.get_effective_reference_version,
        reference_cache.get_effective_reference_tables,
        equipment_cache.get_equipment_repository,
        scenario_state.ensure_active_scenario,
        scenario_state.scenario_month_table,
        simulation_cache.get_scenario_capacity_and_demand,
        hierarchical_table.render_hierarchical_monthly_table,
        process_labels_module.get_process_labels,
    ) = originals
"""


def _render(
    required: pd.DataFrame, token: str, tmp_path_factory: pytest.TempPathFactory
) -> pd.DataFrame:
    path = tmp_path_factory.mktemp("required") / "required.pkl"
    required.to_pickle(path)
    script = SCRIPT.replace("REQUIRED_PATH", repr(str(path))).replace("CONTENT_TOKEN", repr(token))
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception
    assert [element.value for element in app.error] == []
    captured = app.session_state["captured_table"]
    assert isinstance(captured, pd.DataFrame)
    return captured


def _expected_table(required: pd.DataFrame) -> pd.DataFrame:
    weekly = build_weekly_standard_target_capacity(
        required_equipment=required,
        run_day=pd.DataFrame(
            {"생산계획년월": [MONTH] * len(PROCESSES), "공정": PROCESSES, "RUN_DAY": [31.0] * 10}
        ),
        weekly_availability=pd.DataFrame(
            {
                "공정": [process for process in PROCESSES for _ in [*WEEKS, "26-W36"]],
                "Weeknum": [*WEEKS, "26-W36"] * len(PROCESSES),
                "가용대수": [2.0] * (len(PROCESSES) * 5),
            }
        ),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        detail_level="공정",
    )
    return weekly_standard_target_to_wide(weekly, ["공정", "소요기준"])


def test_one_edited_row_outside_the_hash_sample_reaches_the_weekly_table(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    st.cache_data.clear()
    before = required_frame()
    after = before.copy()
    row = out_of_sample_row(before)
    needs = after["소요대수"].to_numpy(dtype="float64", copy=True)
    needs[row] *= 40.0
    after["소요대수"] = needs
    edited_process = str(after["공정"].iloc[row])

    first = _render(before, "weekly-cache-before-edit", tmp_path_factory)
    second = _render(after, "weekly-cache-after-edit", tmp_path_factory)

    expected_before = _expected_table(before)
    expected_after = _expected_table(after)
    # 편집이 실제로 그 공정의 값을 바꾸는 편집인지 먼저 확인한다(시험 자체가 헛돌지 않게).
    changed = expected_before.ne(expected_after).any(axis=1)
    assert expected_after.loc[changed, "공정"].tolist() == [edited_process]

    pd.testing.assert_frame_equal(first.reset_index(drop=True), expected_before)
    pd.testing.assert_frame_equal(second.reset_index(drop=True), expected_after)


# ------------------------------------------------- 캐시 래퍼: 같은 숫자 · 키 성분마다 무효화


def _small_required() -> pd.DataFrame:
    """공정 셋·제품 둘. ER 한 줄과 Pre B/D Dummy 한 줄이 섞여 표준 목표 제외가 함께 돈다."""
    rows = []
    for process, basis in (("P-A", "WF"), ("P-B", "Chip"), ("Pre B/D", "WF")):
        for product, load, need in (("Prod-1", 120.0, 2.0), ("Prod-2", 80.0, 1.0)):
            rows.append((process, basis, "양산", product, "Core", load, need))
    rows.append(("P-A", "WF", "ER", "Prod-1", "Core", 999.0, 9.0))
    rows.append(("Pre B/D", "WF", "양산", "Prod-1", "Dummy", 50.0, 5.0))
    return pd.DataFrame(
        [
            {
                "생산계획년월": MONTH,
                "공정": process,
                "소요기준": basis,
                "양산구분": production,
                "제품정보": product,
                "Stack": "8H",
                "Capa Code": "CAPA",
                "Customer": "Customer",
                "CS": "MP",
                "WF 구분": division,
                "부하량": load,
                "소요대수": need,
            }
            for process, basis, production, product, division, load, need in rows
        ]
    )


SMALL_PROCESSES = ["P-A", "P-B", "Pre B/D"]


def _scenario_tables() -> dict[str, pd.DataFrame]:
    return {
        "RQ_RUN_DAY": pd.DataFrame(
            {"생산계획년월": [MONTH] * 3, "공정": SMALL_PROCESSES, "RUN_DAY": [31.0, 30.0, 29.0]}
        ),
        "RQ_PKG_PLAN": pd.DataFrame(
            {
                "생산계획년월": [MONTH, MONTH],
                "양산구분": ["양산", "양산"],
                "제품정보": ["Prod-1", "Prod-2"],
                "Stack": ["8H", "8H"],
                "Capa Code": ["CAPA", "CAPA"],
                "Customer": ["Customer", "Customer"],
                "CS": ["MP", "MP"],
                "생산수량": [60.0, 40.0],
            }
        ),
        # 공정 필터 선택지의 재료. ER 만 있는 공정은 빠지고 차례는 처음 나온 차례다.
        "RQ_REQB": pd.DataFrame(
            {
                "공정": ["P-B", "ER-only", "P-A", "Pre B/D", "P-A"],
                "양산구분": ["양산", "ER", "양산", "양산", "ER"],
            }
        ),
    }


def _availability(units: float = 2.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": [process for process in SMALL_PROCESSES for _ in WEEKS],
            "Weeknum": WEEKS * len(SMALL_PROCESSES),
            "가용대수": [units] * (len(SMALL_PROCESSES) * len(WEEKS)),
        }
    )


@pytest.fixture
def fake_scenario(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, pd.DataFrame]]:
    """토큰마다 소요대수를 돌려주는 계산 대역. 키의 토큰이 내용을 정한다는 운영 계약 그대로다."""
    frames: dict[str, pd.DataFrame] = {}

    def fake(
        cache_key: tuple[int, str, int, int], **_kwargs: object
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        return pd.DataFrame(), frames[cache_key[1]].copy()

    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", fake)
    st.cache_data.clear()
    yield frames
    st.cache_data.clear()


def _weekly(
    token: str,
    *,
    availability: pd.DataFrame | None = None,
    detail_level: str = "공정",
    processes: tuple[str, ...] = (),
    products: tuple[str, ...] = (),
    pkg: bool = False,
) -> pd.DataFrame:
    availability = _availability() if availability is None else availability
    key = simulation_cache.standard_target_weekly_cache_key(
        simulation_cache.scenario_cache_key(1, {"content_token": token}, 202607, 202609),
        availability=availability,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        detail_level=detail_level,
        processes=processes,
        products=products,
    )
    wrapper = (
        simulation_cache.get_pkg_equivalent_standard_target
        if pkg
        else simulation_cache.get_weekly_standard_target_capacity
    )
    return wrapper(
        key,
        _scenario_tables=_scenario_tables(),
        _reference_tables={},
        _weekly_availability=availability,
    )


def _old_path(
    required: pd.DataFrame,
    *,
    availability: pd.DataFrame | None = None,
    detail_level: str = "공정",
    processes: tuple[str, ...] = (),
    products: tuple[str, ...] = (),
    pkg: bool = False,
) -> pd.DataFrame:
    """고치기 전 화면의 계산 경로 — 분리 → 페이지 필터 → 주간 계산(→ PKG 환산)."""
    availability = _availability() if availability is None else availability
    prepared, _ = split_standard_target_required_equipment(required)
    if processes or products:
        mask = pd.Series(True, index=prepared.index)
        if processes:
            mask &= prepared["공정"].isin(list(processes))
        if products:
            mask &= prepared["제품정보"].isin(list(products))
        prepared = prepared.loc[mask].reset_index(drop=True)
    tables = _scenario_tables()
    weekly = build_weekly_standard_target_capacity(
        required_equipment=prepared,
        run_day=tables["RQ_RUN_DAY"],
        weekly_availability=availability,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        detail_level=detail_level,
    )
    if not pkg:
        return weekly
    return add_pkg_equivalent_standard_target(
        weekly_target=weekly,
        required_equipment=prepared,
        plan=tables["RQ_PKG_PLAN"],
        detail_level=detail_level,
    )


@pytest.mark.parametrize("detail_level", ["공정", "양산구분", "제품정보", "Stack", "WF 구분"])
@pytest.mark.parametrize("processes", [(), ("P-A",), ("P-B", "Pre B/D")])
@pytest.mark.parametrize("pkg", [False, True])
def test_the_key_only_wrapper_returns_the_same_numbers_as_the_old_page_path(
    fake_scenario: dict[str, pd.DataFrame],
    detail_level: str,
    processes: tuple[str, ...],
    pkg: bool,
) -> None:
    fake_scenario["same"] = _small_required()

    cached = _weekly("same", detail_level=detail_level, processes=processes, pkg=pkg)
    again = _weekly("same", detail_level=detail_level, processes=processes, pkg=pkg)
    expected = _old_path(_small_required(), detail_level=detail_level, processes=processes, pkg=pkg)

    pd.testing.assert_frame_equal(cached, expected)
    pd.testing.assert_frame_equal(again, expected)


def test_the_wip_product_filter_matches_the_old_wip_path(
    fake_scenario: dict[str, pd.DataFrame],
) -> None:
    fake_scenario["wip"] = _small_required()

    cached = _weekly("wip", detail_level="제품정보", processes=("P-A",), products=("Prod-2",))

    expected = _old_path(
        _small_required(), detail_level="제품정보", processes=("P-A",), products=("Prod-2",)
    )
    pd.testing.assert_frame_equal(cached, expected)


def test_every_key_part_invalidates_the_weekly_result(
    fake_scenario: dict[str, pd.DataFrame],
) -> None:
    """키에 든 입력 하나만 바꿔도 결과가 바뀐다 — 그리고 바뀐 결과는 새로 계산한 값이다."""
    base = _small_required()
    edited = base.copy()
    edited.loc[edited["공정"].eq("P-A") & edited["제품정보"].eq("Prod-2"), "소요대수"] = 4.0
    fake_scenario["before"] = base
    fake_scenario["after"] = edited

    reference = _weekly("before")

    # 미저장 편집 적용(새 content_token)
    after_edit = _weekly("after")
    assert not after_edit.equals(reference)
    pd.testing.assert_frame_equal(after_edit, _old_path(edited))

    # 가용대수 한 칸
    availability = _availability()
    availability.loc[0, "가용대수"] = 7.0
    with_one_cell = _weekly("before", availability=availability)
    assert not with_one_cell.equals(reference)
    pd.testing.assert_frame_equal(with_one_cell, _old_path(base, availability=availability))

    # 공정 선택
    only_b = _weekly("before", processes=("P-B",))
    assert set(only_b["공정"]) == {"P-B"}
    pd.testing.assert_frame_equal(only_b, _old_path(base, processes=("P-B",)))

    # 분류 수준
    by_product = _weekly("before", detail_level="제품정보")
    assert "제품정보" in by_product.columns and "제품정보" not in reference.columns


def test_a_wip_call_does_not_leak_into_the_standard_target_result(
    fake_scenario: dict[str, pd.DataFrame],
) -> None:
    """재공 현황은 같은 날짜·분류 수준을 제품 일부로 부른다. 표준 목표가 그 결과에 적중하면
    안 된다."""
    fake_scenario["shared"] = _small_required()

    wip = _weekly("shared", detail_level="제품정보", processes=("P-A",), products=("Prod-1",))
    standard = _weekly("shared", detail_level="제품정보", processes=("P-A",))

    assert set(wip["제품정보"]) == {"Prod-1"}
    assert set(standard["제품정보"]) == {"Prod-1", "Prod-2"}
    pd.testing.assert_frame_equal(
        standard, _old_path(_small_required(), detail_level="제품정보", processes=("P-A",))
    )


def test_the_selection_order_does_not_split_the_key() -> None:
    scenario_key = simulation_cache.scenario_cache_key(1, {"content_token": "t"}, 202608, 202608)
    keys = {
        simulation_cache.standard_target_weekly_cache_key(
            scenario_key,
            availability=_availability(),
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            detail_level="공정",
            processes=processes,
        )
        for processes in (["P-B", "P-A"], ["P-A", "P-B"], ("P-A", "P-B", "P-A"))
    }
    assert len(keys) == 1


# ------------------------------------------------- 표준 목표 요약: 예외 행 수 · 공정 선택지


def _summary(token: str) -> simulation_cache.StandardTargetSummary:
    return simulation_cache.get_standard_target_summary(
        simulation_cache.scenario_cache_key(1, {"content_token": token}, 202607, 202609),
        _scenario_tables=_scenario_tables(),
        _reference_tables={},
    )


def _process_display_order(mode: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "페이지 구분": [PAGE_STANDARD_TARGET],
            "탭 구분": [TAB_TARGET_CAPACITY],
            "정렬우선순위": [1],
            "분류컬럼": ["공정"],
            "정렬방식": [mode],
            "분류값": [pd.NA],
            "값표시순서": [pd.NA],
            "활성여부": ["Y"],
        }
    )


def test_the_standard_target_summary_matches_the_old_page_path(
    fake_scenario: dict[str, pd.DataFrame],
) -> None:
    fake_scenario["summary"] = _small_required()

    summary = _summary("summary")

    _, expected_rows = split_standard_target_required_equipment(_small_required())
    assert summary.exception_rows == expected_rows == 1
    expected_processes = exclude_er_required_equipment(_scenario_tables()["RQ_REQB"])[["공정"]]
    pd.testing.assert_frame_equal(summary.processes, expected_processes.drop_duplicates())
    for mode in ("오름차순", "내림차순"):
        rules = _process_display_order(mode)
        prepared = prepare_display_order(rules)
        old = apply_display_order(
            expected_processes.drop_duplicates(),
            prepared,
            PAGE_STANDARD_TARGET,
            TAB_TARGET_CAPACITY,
        )
        assert (
            simulation_cache.get_display_ordered_values(
                summary.processes,
                simulation_cache.display_order_digest(rules),
                PAGE_STANDARD_TARGET,
                TAB_TARGET_CAPACITY,
                _display_order=prepared,
            )
            == old["공정"].astype(str).tolist()
        )


def test_the_standard_target_summary_follows_a_new_content_token(
    fake_scenario: dict[str, pd.DataFrame],
) -> None:
    fake_scenario["summary-before"] = _small_required()
    edited = _small_required()
    dummy = edited.loc[edited["WF 구분"].eq("Dummy")].assign(제품정보="Prod-2")
    fake_scenario["summary-after"] = pd.concat([edited, dummy], ignore_index=True)

    assert _summary("summary-before").exception_rows == 1
    assert _summary("summary-after").exception_rows == 2


def test_a_failing_scenario_is_not_cached_by_the_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def broken(cache_key: tuple[int, str, int, int], **_kwargs: object) -> None:
        calls.append(cache_key[1])
        raise ValueError("계산 실패")

    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", broken)
    st.cache_data.clear()
    for _ in range(2):
        with pytest.raises(ValueError, match="계산 실패"):
            _summary("summary-broken")
    assert calls == ["summary-broken", "summary-broken"]
    st.cache_data.clear()


# ------------------------------------------------- 분리 결과 캐시(로직 분석·주간 미스 경로)


def _split(token: str) -> tuple[pd.DataFrame, int]:
    return simulation_cache.get_standard_target_split(
        simulation_cache.scenario_cache_key(1, {"content_token": token}, 202607, 202609),
        _scenario_tables=_scenario_tables(),
        _reference_tables={},
    )


def test_the_split_cache_matches_the_old_split_and_follows_the_token(
    fake_scenario: dict[str, pd.DataFrame],
) -> None:
    fake_scenario["split-before"] = _small_required()
    edited = _small_required()
    edited.loc[edited["공정"].eq("P-B"), "소요대수"] = 3.0
    fake_scenario["split-after"] = edited

    before, before_rows = _split("split-before")
    after, after_rows = _split("split-after")

    expected_before, expected_rows = split_standard_target_required_equipment(_small_required())
    pd.testing.assert_frame_equal(before, expected_before)
    assert before_rows == expected_rows == 1
    pd.testing.assert_frame_equal(after, split_standard_target_required_equipment(edited)[0])
    assert after_rows == 1
    assert not before.equals(after)


def test_the_split_is_shared_so_new_weekly_keys_do_not_refetch_the_demand(
    fake_scenario: dict[str, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    """공정 조합·분류 수준이 바뀐 주간 미스와 요약 미스는 분리 결과 캐시에서 받는다."""
    fake_scenario["shared-split"] = _small_required()
    calls: list[str] = []
    fake = simulation_cache.get_scenario_capacity_and_demand

    def counting(cache_key: tuple[int, str, int, int], **kwargs: object) -> object:
        calls.append(cache_key[1])
        return fake(cache_key, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(simulation_cache, "get_scenario_capacity_and_demand", counting)

    _weekly("shared-split")
    _weekly("shared-split", processes=("P-A",))
    _weekly("shared-split", detail_level="제품정보", processes=("P-B",))
    _summary("shared-split")

    assert calls == ["shared-split"]
