# Purpose: 공정 Capa 상세의 요약·제품별 소요대수·경로 추적이 계산 결과와 같은 숫자를 내는지 본다.

"""공정 Capa 상세 서비스(`process_capa_detail`)와 그 캐시 래퍼의 계약.

지키는 것은 넷이다.

- **같은 숫자** — 요약의 가용·소요·확보율은 `calculate_securement_rate` 그대로이고, 제품 행을 다
  더하면 부모(공정 소요대수)와 같다(허용오차 1e-9).
- **경로 인자의 곱 = 대당 Capa** — 기준정보 표에서 꺼낸 인자로 식을 다시 곱하면 계산 결과와 같다.
- **원수요는 한 번** — STEP 이 여럿이어도 원수요 부하량을 STEP 수만큼 세지 않는다(합성 표본은
  공정·월당 STEP 이 하나라 STEP 을 하나 더 붙인 픽스처로 본다).
- **캐시** — 래퍼는 순수 함수와 같은 값을 내고, 적중이면 시나리오 전체 프레임을 풀지 않는다.

HOME 표시 확보율(`home_display_rates`)은 HOME 과 같은 함수·차례로 얹는다(실행 Capa → 선행 B/O).
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from uuid import uuid4

import pandas as pd
import pytest

from capa_simulation.services import builtin_seed
from capa_simulation.services import simulation_cache as sc
from capa_simulation.services.builtin_seed import build_builtin_seed_dataset, builtin_seed_processes
from capa_simulation.services.display_order import prepare_display_order
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_REQUIRED
from capa_simulation.services.process_capa_detail import (
    CAUSE_AVAILABILITY_MISMATCH,
    FILTERED_OUT_LABEL,
    GROUPED_COUNT_COLUMN,
    MISMATCH_COLUMN,
    OTHER_ROW_COLUMN,
    PRODUCT_DEMAND_SPLITS,
    PRODUCT_LABEL_COLUMN,
    RATIO_ASSUMED_MISSING_ROW,
    RATIO_BLANK_OR_ZERO,
    ROUTE_COLUMNS,
    RULE_EXCLUDED_COLUMN,
    ProcessMonthTrace,
    build_process_capa_summary,
    build_process_month_trace,
    build_process_product_demand,
    home_display_rates,
    month_column,
    process_calculation_rows,
    process_capa_kpis,
    route_factor_product,
)
from capa_simulation.services.required_equipment import PKG_UNCOUNTED_REASON
from capa_simulation.services.securement_rate import (
    CAUSE_OWNED_SHORT,
    CAUSE_RENTAL,
    calculate_securement_rate,
)
from capa_simulation.services.securement_threshold import SecurementThresholds
from capa_simulation.services.simulation_cache import CAPACITY_INPUT_TABLES, get_capacity_and_demand

START, END = 202602, 202605
TRACE_MONTH = 202603
WAFER_PROCESS = "DEMO_Wafer_Inspect"
THRESHOLDS = SecurementThresholds(1.095, 0.995, ((202603, 1.2, None),))
TOLERANCE = 1e-9


@pytest.fixture(scope="module")
def tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pd.DataFrame]:
    """Git 에 있는 내장 시드. 로컬 표시순서 CSV 가 있으면 PC 마다 규칙이 달라지므로 없는 자리를
    가리켜 Git 의 시드 JSON 을 쓰게 한다."""
    with pytest.MonkeyPatch.context() as patch:
        missing = tmp_path_factory.mktemp("no_local_display_order") / "RQ_DISPLAY_ORDER.csv"
        patch.setattr(builtin_seed, "LOCAL_DISPLAY_ORDER_CSV_PATH", missing)
        return dict(build_builtin_seed_dataset().reference_tables)


def _months(required: pd.DataFrame) -> list[int]:
    return sorted({int(month) for month in pd.to_numeric(required["생산계획년월"])})


def _capacity_tables(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {name: tables[name] for name in CAPACITY_INPUT_TABLES}


def _trace(tables: dict[str, pd.DataFrame], process: str, month: int) -> ProcessMonthTrace:
    unit, required = get_capacity_and_demand(tables)
    rows = process_calculation_rows(unit, required, process=process)
    return build_process_month_trace(rows, _capacity_tables(tables), process=process, month=month)


def _process_rows_of(table: pd.DataFrame, process: str) -> pd.Series:
    return table["공정"].astype("string").str.strip().eq(process).fillna(False).astype("bool")


# ------------------------------------------------------------------ 월별 요약


def test_summary_carries_the_securement_numbers_unchanged(tables: dict[str, pd.DataFrame]) -> None:
    """가용·소요·확보율은 확보율 계산 그대로다.

    산출 결과·Static Capa 와 다른 숫자를 내면 안 된다.
    """
    _, required = get_capacity_and_demand(tables)
    securement = calculate_securement_rate(tables["RQ_EQP_AVBL"], required)
    months = _months(required)

    for process in builtin_seed_processes():
        summary = build_process_capa_summary(
            securement,
            tables["RQ_EQP_OWN"],
            tables["RQ_EQP_LENT"],
            process=f"  {process} ",
            months=months,
            thresholds=THRESHOLDS,
        )
        expected = (
            securement.loc[securement["공정"].eq(process)]
            .sort_values("생산계획년월")
            .reset_index(drop=True)
        )
        assert summary["생산계획년월"].tolist() == months
        assert summary["공정"].astype(str).eq(process).all()
        for column in ("가용대수", "소요대수", "확보율"):
            pd.testing.assert_series_equal(
                summary[column].reset_index(drop=True),
                expected[column].astype("float64").reset_index(drop=True),
                check_names=False,
            )
        owned = (
            tables["RQ_EQP_OWN"]
            .loc[_process_rows_of(tables["RQ_EQP_OWN"], process)]
            .assign(month=lambda frame: pd.to_numeric(frame["생산계획년월"]))
            .sort_values("month")
        )
        assert summary["총보유대수"].tolist() == pd.to_numeric(owned["설비보유"]).tolist()
        assert not summary[MISMATCH_COLUMN].any()
        assert summary.loc[summary["생산계획년월"].eq(202603), "확보기준"].tolist() == [1.2]
        assert set(summary.loc[summary["생산계획년월"].ne(202603), "확보기준"]) == {1.095}


def test_summary_marks_months_where_owned_minus_lent_is_not_available(
    tables: dict[str, pd.DataFrame],
) -> None:
    available = tables["RQ_EQP_AVBL"].copy()
    edited = _process_rows_of(available, WAFER_PROCESS) & pd.to_numeric(
        available["생산계획년월"]
    ).eq(202604)
    available.loc[edited, "가용대수"] = pd.to_numeric(available.loc[edited, "가용대수"]) + 1
    _, required = get_capacity_and_demand(tables)
    securement = calculate_securement_rate(available, required)

    summary = build_process_capa_summary(
        securement,
        tables["RQ_EQP_OWN"],
        tables["RQ_EQP_LENT"],
        process=WAFER_PROCESS,
        months=_months(required),
        thresholds=THRESHOLDS,
    )

    assert summary.loc[summary[MISMATCH_COLUMN], "생산계획년월"].tolist() == [202604]


def test_months_without_rows_are_zero_and_keep_the_given_order(
    tables: dict[str, pd.DataFrame],
) -> None:
    _, required = get_capacity_and_demand(tables)
    securement = calculate_securement_rate(tables["RQ_EQP_AVBL"], required)

    summary = build_process_capa_summary(
        securement,
        tables["RQ_EQP_OWN"],
        tables["RQ_EQP_LENT"],
        process=WAFER_PROCESS,
        months=[202703, 202602, 202602],
        thresholds=THRESHOLDS,
    )

    assert summary["생산계획년월"].tolist() == [202703, 202602]
    later = summary.iloc[0]
    assert (later["가용대수"], later["소요대수"], later["총보유대수"]) == (0.0, 0.0, 0.0)
    assert math.isnan(float(later["확보율"]))
    assert later["판정"] is None
    assert later["확보기준 과부족"] == 0


def test_kpis_read_the_lowest_rate_shortages_and_causes() -> None:
    securement = pd.DataFrame(
        {
            "생산계획년월": [202601, 202602, 202603, 202604],
            "공정": ["P"] * 4,
            "가용대수": [12.0, 8.0, 9.0, 0.0],
            "소요대수": [10.0, 10.0, 10.0, 0.0],
        }
    )
    owned = pd.DataFrame(
        {
            "생산계획년월": [202601, 202602, 202603],
            "공정": ["P"] * 3,
            "설비보유": [12.0, 10.0, 12.0],
        }
    )
    lent = pd.DataFrame(
        {"생산계획년월": [202602, 202603], "공정": ["P"] * 2, "설비대여평가": [2.0, 3.0]}
    )

    summary = build_process_capa_summary(
        securement,
        owned,
        lent,
        process="P",
        months=[202601, 202602, 202603, 202604],
        thresholds=SecurementThresholds(1.1, 0.9),
    )
    kpis = process_capa_kpis(summary)

    assert summary["판정"].tolist() == ["secure", "shortage", "warning", None]
    assert summary["확보기준 과부족"].tolist() == [1, -3, -2, 0]
    assert summary["부족 원인"].tolist() == ["", "보유로도 부족", "대여 영향", ""]
    assert kpis.lowest_rate == pytest.approx(0.8)
    assert kpis.lowest_rate_month == 202602
    assert kpis.shortage_months == 2
    assert kpis.max_shortage == 3
    assert (kpis.owned_short_months, kpis.rental_months, kpis.mismatch_months) == (1, 1, 0)


def test_a_shortage_from_an_edited_available_count_is_not_called_rental() -> None:
    """가용만 따로 낮춘 달(대여 0)은 「대여 영향」이 아니라 「가용 불일치」다.

    - 202601: 총보유 12 · 대여 0 · 가용 8 — 총보유 − 대여로는 확보(1.2)라 대여 탓이 아니다.
    - 202602: 총보유 12 · 대여 3 · 가용 8 — 어긋나지만(12 − 3 ≠ 8) 총보유 − 대여(0.9)로도 미달이라
      대여가 부족에 들어간다 → 「대여 영향」 그대로.
    - 202603: 총보유 12 · 대여 4 · 가용 8 — 어긋남 없음 → 「대여 영향」.
    - 202604: 총보유 9 · 대여 0 · 가용 8 — 총보유로도 미달 → 「보유로도 부족」.
    """
    months = [202601, 202602, 202603, 202604]
    securement = pd.DataFrame(
        {
            "생산계획년월": months,
            "공정": ["P"] * 4,
            "가용대수": [8.0] * 4,
            "소요대수": [10.0] * 4,
        }
    )
    owned = pd.DataFrame(
        {"생산계획년월": months, "공정": ["P"] * 4, "설비보유": [12.0, 12.0, 12.0, 9.0]}
    )
    lent = pd.DataFrame(
        {"생산계획년월": months, "공정": ["P"] * 4, "설비대여평가": [0.0, 3.0, 4.0, 0.0]}
    )

    summary = build_process_capa_summary(
        securement,
        owned,
        lent,
        process="P",
        months=months,
        thresholds=SecurementThresholds(1.1, 0.9),
    )
    kpis = process_capa_kpis(summary)

    assert summary[MISMATCH_COLUMN].tolist() == [True, True, False, True]
    assert summary["부족 원인"].tolist() == [
        CAUSE_AVAILABILITY_MISMATCH,
        CAUSE_RENTAL,
        CAUSE_RENTAL,
        CAUSE_OWNED_SHORT,
    ]
    assert (kpis.owned_short_months, kpis.rental_months, kpis.mismatch_months) == (1, 2, 1)
    assert kpis.owned_short_months + kpis.rental_months + kpis.mismatch_months == (
        kpis.shortage_months
    )


# ------------------------------------------------------------------ 제품별 소요대수


@pytest.mark.parametrize("split", list(PRODUCT_DEMAND_SPLITS))
def test_product_rows_add_up_to_the_process_demand(
    tables: dict[str, pd.DataFrame], split: str
) -> None:
    """자식 행을 다 더하면 부모(공정 소요대수)다.

    「그 밖」·거르기를 걸어도 아무것도 버리지 않는다.
    """
    _, required = get_capacity_and_demand(tables)
    securement = calculate_securement_rate(tables["RQ_EQP_AVBL"], required)
    months = _months(required)
    display_order = prepare_display_order(tables["RQ_DISPLAY_ORDER"])

    for process in builtin_seed_processes():
        summary = build_process_capa_summary(
            securement,
            tables["RQ_EQP_OWN"],
            tables["RQ_EQP_LENT"],
            process=process,
            months=months,
            thresholds=THRESHOLDS,
        )
        parent = summary["소요대수"].tolist()
        for products, classes, limit in (
            ((), (), 12),
            ((), (), 1),
            (("DEMO PRODUCT A",), (), 12),
            ((), ("양산",), 1),
        ):
            demand = build_process_product_demand(
                required,
                process=process,
                split=split,
                months=months,
                display_order=display_order,
                products=products,
                production_classes=classes,
                limit=limit,
            )
            children = [float(demand[month_column(month)].sum()) for month in months]
            assert children == pytest.approx(parent, abs=TOLERANCE, rel=0)


def _many_products(count: int) -> pd.DataFrame:
    """공정 하나에 제품 `count` 개. 제품 번호가 클수록 소요가 크다."""
    names = [f"P{index:02d}" for index in range(1, count + 1)]
    return pd.DataFrame(
        {
            "생산계획년월": [202601] * count + [202602] * count,
            "공정": ["Proc"] * (2 * count),
            "양산구분": ["양산"] * (2 * count),
            "제품정보": names * 2,
            "Stack": ["8H"] * (2 * count),
            "WF 구분": ["Core"] * (2 * count),
            "소요기준": ["WF"] * (2 * count),
            "소요대수": [float(index) for index in range(1, count + 1)]
            + [float(index) / 10 for index in range(1, count + 1)],
        }
    )


def test_more_than_twelve_products_fold_the_smallest_into_one_other_row() -> None:
    demand = build_process_product_demand(
        _many_products(15), process="Proc", split="제품정보", months=[202601, 202602]
    )

    assert demand[PRODUCT_LABEL_COLUMN].tolist() == [
        *(f"P{index:02d}" for index in range(4, 16)),
        "그 밖 3개",
    ]
    other = demand.iloc[-1]
    assert bool(other[OTHER_ROW_COLUMN]) and other[GROUPED_COUNT_COLUMN] == 3
    assert other["202601"] == pytest.approx(1.0 + 2.0 + 3.0)
    assert demand["202601"].sum() == pytest.approx(sum(range(1, 16)))
    assert not demand[OTHER_ROW_COLUMN].iloc[:-1].any()


def test_product_rows_follow_the_required_equipment_display_order() -> None:
    rules = pd.DataFrame(
        {
            "페이지 구분": [PAGE_CALCULATION] * 2,
            "탭 구분": [TAB_REQUIRED] * 2,
            "정렬우선순위": [1, 1],
            "분류컬럼": ["제품정보", "제품정보"],
            "정렬방식": ["사용자지정", "사용자지정"],
            "분류값": ["P02", "P05"],
            "값표시순서": [1, 2],
            "활성여부": ["Y", "Y"],
        }
    )

    demand = build_process_product_demand(
        _many_products(5),
        process="Proc",
        split="제품정보",
        months=[202601],
        display_order=prepare_display_order(rules),
    )

    assert demand[PRODUCT_LABEL_COLUMN].tolist() == ["P02", "P05", "P01", "P03", "P04"]


def test_filtered_out_products_land_in_the_other_row() -> None:
    demand = build_process_product_demand(
        _many_products(4),
        process="Proc",
        split="제품정보",
        months=[202601, 202602],
        products=["P01", "P04"],
    )

    assert demand[PRODUCT_LABEL_COLUMN].tolist() == ["P01", "P04", "그 밖 2개 (거르기 밖 포함)"]
    assert demand["202601"].tolist() == pytest.approx([1.0, 4.0, 5.0])
    assert demand[GROUPED_COUNT_COLUMN].tolist() == [1, 1, 2]


def test_the_other_row_does_not_recount_values_shown_above() -> None:
    """제품으로 거르고 Stack 으로 나누면 거르기 밖 제품이 위에 보이는 Stack 값을 실을 수 있다.

    「그 밖」의 수는 위에 안 보이는 분류값만 센다. 안 보이는 값이 없으면 이름이 「거르기 밖」이다.
    """
    frame = _many_products(3)
    frame["Stack"] = frame["제품정보"].map({"P01": "8H", "P02": "8H", "P03": "12H"})

    split_by_stack = build_process_product_demand(
        frame, process="Proc", split="Stack", months=[202601], products=["P01"]
    )
    only_shared = build_process_product_demand(
        frame.loc[frame["제품정보"].ne("P03")],
        process="Proc",
        split="Stack",
        months=[202601],
        products=["P01"],
    )

    assert split_by_stack[PRODUCT_LABEL_COLUMN].tolist() == ["8H", "그 밖 1개 (거르기 밖 포함)"]
    assert split_by_stack[GROUPED_COUNT_COLUMN].tolist() == [1, 1]
    assert split_by_stack["202601"].tolist() == pytest.approx([1.0, 2.0 + 3.0])
    assert only_shared[PRODUCT_LABEL_COLUMN].tolist() == ["8H", FILTERED_OUT_LABEL]
    assert only_shared[GROUPED_COUNT_COLUMN].tolist() == [1, 0]
    assert only_shared["202601"].tolist() == pytest.approx([1.0, 2.0])


def test_two_level_split_labels_and_zero_rows() -> None:
    frame = _many_products(3)
    frame.loc[frame["제품정보"].eq("P02"), "소요대수"] = 0.0
    frame.loc[frame["제품정보"].eq("P03"), "양산구분"] = "ER"

    demand = build_process_product_demand(
        frame, process="Proc", split="양산구분·제품", months=[202601, 202602]
    )

    assert demand[PRODUCT_LABEL_COLUMN].tolist() == ["ER · P03", "양산 · P01"]
    assert list(demand.columns[:2]) == ["양산구분", "제품정보"]


def test_an_unknown_split_is_refused() -> None:
    with pytest.raises(ValueError, match="분류"):
        build_process_product_demand(
            _many_products(2), process="Proc", split="공정", months=[202601]
        )


# ------------------------------------------------------------------ 경로 추적


def test_route_factors_multiply_back_to_the_unit_capacity(tables: dict[str, pd.DataFrame]) -> None:
    """기준정보 표에서 꺼낸 인자로 식을 다시 곱하면 계산 결과의 대당 Capa 다.

    대당 Capa 식이나 인자 연결 키가 바뀌었는데 이 서비스만 남으면 여기서 갈린다.
    """
    for process in builtin_seed_processes():
        for month in (202601, TRACE_MONTH, 202612):
            trace = _trace(tables, process, month)
            routes = trace.routes

            assert list(routes.columns) == ROUTE_COLUMNS
            assert not routes.empty
            assert route_factor_product(routes).tolist() == pytest.approx(
                routes["대당 Capa"].tolist(), rel=1e-12
            )
            assert (routes["부하량"] / routes["대당 Capa"]).tolist() == pytest.approx(
                routes["소요대수"].tolist(), rel=1e-12
            )
            assert trace.evidence.required == pytest.approx(
                float(routes["소요대수"].sum()), abs=TOLERANCE
            )
            assert trace.common_factors.run_day is not None
            assert trace.common_factors.module_count is not None
            assert set(trace.common_factors.by_class["양산구분"]) == set(routes["양산구분"])
            assert routes["Lot 측정률 근거"].eq("").all()
            assert routes["WF측정률 근거"].eq("").all()


def test_route_trace_matches_the_securement_demand(tables: dict[str, pd.DataFrame]) -> None:
    _, required = get_capacity_and_demand(tables)
    securement = calculate_securement_rate(tables["RQ_EQP_AVBL"], required)
    row = securement.loc[
        securement["공정"].eq(WAFER_PROCESS) & securement["생산계획년월"].eq(TRACE_MONTH)
    ]

    trace = _trace(tables, WAFER_PROCESS, TRACE_MONTH)

    assert trace.evidence.required == pytest.approx(float(row["소요대수"].iloc[0]), abs=TOLERANCE)
    assert trace.evidence.route_count == len(trace.routes)
    assert trace.evidence.excluded_route_count == 0
    top = trace.evidence.top_products
    assert top["소요대수"].is_monotonic_decreasing
    assert float(top["비중"].sum()) == pytest.approx(1.0)


def _with_second_step(tables: dict[str, pd.DataFrame], process: str) -> dict[str, pd.DataFrame]:
    """공정 하나에 STEP 을 하나 더 붙인다. 둘째 STEP 은 UPEH 가 두 배라 소요가 절반이다."""
    edited = dict(tables)
    for name in ("RQ_REQB", "RQ_UPEH", "RQ_LOT_RATIO", "RQ_WF_RATIO"):
        table = tables[name]
        added = table.loc[_process_rows_of(table, process)].copy()
        added["STEP_SEQ"] = "DEMO-P201"
        added["MCP_SEQ"] = "DEMO-2B"
        if name == "RQ_UPEH":
            added["UPEH"] = pd.to_numeric(added["UPEH"]) * 2
        edited[name] = pd.concat([table, added], ignore_index=True)
    return edited


def test_unique_demand_is_counted_once_across_steps(tables: dict[str, pd.DataFrame]) -> None:
    """STEP 마다 같은 부하량을 나눠 받는다. 원수요 부하량은 STEP 수만큼 부풀지 않는다."""
    single = _trace(tables, WAFER_PROCESS, TRACE_MONTH)
    double = _trace(_with_second_step(tables, WAFER_PROCESS), WAFER_PROCESS, TRACE_MONTH)

    assert double.evidence.route_count == 2 * single.evidence.route_count
    assert set(double.routes["STEP_SEQ"]) == {"DEMO-P200", "DEMO-P201"}
    assert double.evidence.unique_demand_load == pytest.approx(single.evidence.unique_demand_load)
    assert float(double.routes["부하량"].sum()) == pytest.approx(
        2 * single.evidence.unique_demand_load
    )
    assert double.evidence.required == pytest.approx(1.5 * single.evidence.required)
    assert route_factor_product(double.routes).tolist() == pytest.approx(
        double.routes["대당 Capa"].tolist(), rel=1e-12
    )


def _with_ratio_gaps(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """제품 A 는 Lot 측정률 행을 빼고 WF측정률을 빈칸으로, 제품 B 는 WF측정률을 0 으로 둔다."""
    edited = dict(tables)
    lot = tables["RQ_LOT_RATIO"]
    here = _process_rows_of(lot, WAFER_PROCESS) & pd.to_numeric(lot["생산계획년월"]).eq(TRACE_MONTH)
    edited["RQ_LOT_RATIO"] = lot.loc[~(here & lot["제품정보"].eq("DEMO PRODUCT A"))].reset_index(
        drop=True
    )
    wf = tables["RQ_WF_RATIO"].copy()
    wf["WF측정률"] = pd.to_numeric(wf["WF측정률"]).astype("float64")
    wf_here = _process_rows_of(wf, WAFER_PROCESS) & pd.to_numeric(wf["생산계획년월"]).eq(
        TRACE_MONTH
    )
    wf.loc[wf_here & wf["제품정보"].eq("DEMO PRODUCT A"), "WF측정률"] = float("nan")
    wf.loc[wf_here & wf["제품정보"].eq("DEMO PRODUCT B"), "WF측정률"] = 0.0
    edited["RQ_WF_RATIO"] = wf
    return edited


def test_measurement_ratio_defaults_are_marked_by_kind(tables: dict[str, pd.DataFrame]) -> None:
    """측정률 1.0 의 두 꼴 — 행이 없어 이어 간 가정과, 빈칸·0 을 1.0 으로 쓴 것 — 을 가른다."""
    trace = _trace(_with_ratio_gaps(tables), WAFER_PROCESS, TRACE_MONTH)
    routes = trace.routes.set_index("제품정보")

    assert routes.loc["DEMO PRODUCT A", "Lot 측정률"] == 1.0
    assert routes.loc["DEMO PRODUCT A", "Lot 측정률 근거"] == RATIO_ASSUMED_MISSING_ROW
    assert routes.loc["DEMO PRODUCT A", "WF측정률"] == 1.0
    assert routes.loc["DEMO PRODUCT A", "WF측정률 근거"] == RATIO_BLANK_OR_ZERO
    assert routes.loc["DEMO PRODUCT B", "WF측정률"] == 1.0
    assert routes.loc["DEMO PRODUCT B", "WF측정률 근거"] == RATIO_BLANK_OR_ZERO
    assert routes.loc["DEMO PRODUCT B", "Lot 측정률 근거"] == ""
    assert trace.evidence.assumed_ratio_routes == 1
    assert trace.evidence.blank_ratio_routes == 2
    assert route_factor_product(trace.routes).tolist() == pytest.approx(
        trace.routes["대당 Capa"].tolist(), rel=1e-12
    )


def test_excluded_routes_carry_the_unit_capacity_reason(tables: dict[str, pd.DataFrame]) -> None:
    edited = dict(tables)
    upeh = tables["RQ_UPEH"].copy()
    upeh["UPEH"] = pd.to_numeric(upeh["UPEH"]).astype("float64")
    target = (
        _process_rows_of(upeh, WAFER_PROCESS)
        & pd.to_numeric(upeh["생산계획년월"]).eq(TRACE_MONTH)
        & upeh["제품정보"].eq("DEMO PRODUCT A")
    )
    upeh.loc[target, "UPEH"] = 0.0
    edited["RQ_UPEH"] = upeh

    trace = _trace(edited, WAFER_PROCESS, TRACE_MONTH)

    assert trace.routes["제품정보"].tolist() == ["DEMO PRODUCT B"]
    assert trace.excluded["제품정보"].tolist() == ["DEMO PRODUCT A"]
    assert trace.excluded["제외사유"].tolist() == ["대당 Capa 없음 (UPEH 0 이하)"]
    assert trace.excluded[RULE_EXCLUDED_COLUMN].tolist() == [False]
    assert trace.evidence.excluded_route_count == 1
    assert trace.evidence.rule_excluded_route_count == 0


def _month_rows_of(rows: pd.DataFrame, process: str, month: int) -> pd.DataFrame:
    here = _process_rows_of(rows, process) & pd.to_numeric(rows["생산계획년월"]).eq(month)
    return rows.loc[here].reset_index(drop=True)


def test_rule_exclusions_are_counted_apart_from_errors(tables: dict[str, pd.DataFrame]) -> None:
    """PKG 의 Buffer 아닌 행(규칙상 제외)은 오류 제외 수에 들지 않는다 — 정상 공정이 늘 「제외 경로
    n」을 띄우지 않게."""
    unit, required = get_capacity_and_demand(tables)
    rows = process_calculation_rows(unit, required, process=WAFER_PROCESS)
    base = _month_rows_of(rows.required_equipment, WAFER_PROCESS, TRACE_MONTH)
    pkg = base.copy()
    pkg["소요기준"] = "PKG"
    pkg["WF 구분"] = "Top"
    pkg["제외사유"] = PKG_UNCOUNTED_REASON
    pkg["부하량"] = 0.0
    broken = base.head(1).assign(STEP_SEQ="DEMO-P999", 제외사유="대당 Capa 없음")
    exclusions = pd.concat([pkg, broken], ignore_index=True)

    trace = build_process_month_trace(
        rows._replace(required_exclusions=exclusions),
        _capacity_tables(tables),
        process=WAFER_PROCESS,
        month=TRACE_MONTH,
    )

    assert trace.evidence.rule_excluded_route_count == len(base)
    assert trace.evidence.excluded_route_count == 1
    assert trace.excluded[RULE_EXCLUDED_COLUMN].sum() == len(base)
    assert set(trace.excluded.loc[trace.excluded[RULE_EXCLUDED_COLUMN], "제외사유"]) == {
        PKG_UNCOUNTED_REASON
    }


def test_a_process_with_two_demand_bases_still_gives_its_evidence(
    tables: dict[str, pd.DataFrame],
) -> None:
    """공정당 소요기준 하나는 본 계산이 강제하지 않는다. 그 데이터에서도 근거 요약은 멈추지 않고
    원수요 키로 중복을 뺀 부하량을 낸다."""
    unit, required = get_capacity_and_demand(tables)
    rows = process_calculation_rows(unit, required, process=WAFER_PROCESS)
    base = _month_rows_of(rows.required_equipment, WAFER_PROCESS, TRACE_MONTH)
    second_step = base.assign(STEP_SEQ="DEMO-P201")
    other_basis = base.head(1).assign(소요기준="CHIP", 부하량=7.0, STEP_SEQ="DEMO-P202")
    edited = pd.concat([base, second_step, other_basis], ignore_index=True)

    trace = build_process_month_trace(
        rows._replace(required_equipment=edited),
        _capacity_tables(tables),
        process=WAFER_PROCESS,
        month=TRACE_MONTH,
    )

    single_load = float(pd.to_numeric(base["부하량"]).sum())
    assert trace.evidence.unique_demand_load == pytest.approx(single_load + 7.0)


def test_a_month_without_rows_gives_an_empty_trace(tables: dict[str, pd.DataFrame]) -> None:
    trace = _trace(tables, WAFER_PROCESS, 209912)

    assert trace.routes.empty and list(trace.routes.columns) == ROUTE_COLUMNS
    assert trace.evidence.route_count == 0
    assert trace.evidence.required == 0.0
    assert trace.evidence.effective_capacity is None


# ------------------------------------------------------------------ 캐시 래퍼


@pytest.fixture
def key() -> sc.ScenarioCacheKey:
    # st.cache_data 는 프로세스 전역이다. 테스트마다 토큰을 새로 만들어 칸을 나눠 쓰지 않는다.
    return (1, f"test-process-detail-{uuid4().hex}", START, END)


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


def _period_months() -> tuple[int, ...]:
    return tuple(range(START, END + 1))


def test_wrappers_match_the_pure_functions(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    unit, required = sc.get_scenario_capacity_and_demand(
        key, _scenario_tables=tables, _reference_tables=tables
    )
    rows = process_calculation_rows(unit, required, process=WAFER_PROCESS)
    display_order = prepare_display_order(tables["RQ_DISPLAY_ORDER"])
    digest = sc.display_order_digest(tables["RQ_DISPLAY_ORDER"])

    for split in PRODUCT_DEMAND_SPLITS:
        expected = build_process_product_demand(
            rows.required_equipment,
            process=WAFER_PROCESS,
            split=split,
            months=_period_months(),
            display_order=display_order,
            products=("DEMO PRODUCT B",),
        )
        cached = sc.get_process_product_demand(
            key,
            digest,
            WAFER_PROCESS,
            split,
            _period_months(),
            _scenario_tables=tables,
            _reference_tables=tables,
            _display_order=display_order,
            products=("DEMO PRODUCT B",),
        )
        pd.testing.assert_frame_equal(cached, expected)

    expected_trace = build_process_month_trace(
        rows, _capacity_tables(tables), process=WAFER_PROCESS, month=TRACE_MONTH
    )
    cached_trace = sc.get_process_month_trace(
        key, WAFER_PROCESS, TRACE_MONTH, _scenario_tables=tables, _reference_tables=tables
    )
    pd.testing.assert_frame_equal(cached_trace.routes, expected_trace.routes)
    pd.testing.assert_frame_equal(cached_trace.excluded, expected_trace.excluded)
    pd.testing.assert_frame_equal(
        cached_trace.common_factors.by_class, expected_trace.common_factors.by_class
    )
    assert cached_trace.common_factors[1:] == expected_trace.common_factors[1:]
    pd.testing.assert_frame_equal(
        cached_trace.evidence.top_products, expected_trace.evidence.top_products
    )
    # 근거 요약의 숫자 칸(상위 제품 표 밖).
    blank = pd.DataFrame()
    assert cached_trace.evidence._replace(top_products=blank) == expected_trace.evidence._replace(
        top_products=blank
    )


def test_changing_split_filter_or_month_does_not_unpickle_the_scenario_frames(
    key: sc.ScenarioCacheKey,
    tables: dict[str, pd.DataFrame],
    counted: list[sc.ScenarioCacheKey],
) -> None:
    """공정 조각이 캐시되므로 같은 공정에서 분류·거르기·달을 바꿔도 전체 프레임을 풀지 않는다."""
    display_order = prepare_display_order(tables["RQ_DISPLAY_ORDER"])
    digest = sc.display_order_digest(tables["RQ_DISPLAY_ORDER"])

    def demand(split: str, products: tuple[str, ...] = ()) -> pd.DataFrame:
        return sc.get_process_product_demand(
            key,
            digest,
            WAFER_PROCESS,
            split,
            _period_months(),
            _scenario_tables=tables,
            _reference_tables=tables,
            _display_order=display_order,
            products=products,
        )

    demand("제품정보")
    assert counted == [key], "첫 호출만 계산 결과를 받는다"
    counted.clear()

    demand("Stack")
    demand("제품정보", ("DEMO PRODUCT A",))
    for month in _period_months():
        sc.get_process_month_trace(
            key, WAFER_PROCESS, month, _scenario_tables=tables, _reference_tables=tables
        )
    demand("제품정보")

    assert counted == []


def test_a_new_content_token_recomputes(tables: dict[str, pd.DataFrame]) -> None:
    before_key: sc.ScenarioCacheKey = (1, f"test-process-before-{uuid4().hex}", START, END)
    after_key: sc.ScenarioCacheKey = (1, f"test-process-after-{uuid4().hex}", START, END)
    edited = dict(tables)
    upeh = tables["RQ_UPEH"].copy()
    upeh["UPEH"] = pd.to_numeric(upeh["UPEH"]) * 0.5
    edited["RQ_UPEH"] = upeh

    def demand(cache_key: sc.ScenarioCacheKey, scenario: dict[str, pd.DataFrame]) -> pd.DataFrame:
        return sc.get_process_product_demand(
            cache_key,
            "no-order",
            WAFER_PROCESS,
            "제품정보",
            _period_months(),
            _scenario_tables=scenario,
            _reference_tables=scenario,
            _display_order=None,
        )

    before = demand(before_key, tables)
    after = demand(after_key, edited)
    month = month_column(TRACE_MONTH)

    assert after[month].tolist() == pytest.approx([2 * value for value in before[month]])
    before_trace = sc.get_process_month_trace(
        before_key, WAFER_PROCESS, TRACE_MONTH, _scenario_tables=tables, _reference_tables=tables
    )
    after_trace = sc.get_process_month_trace(
        after_key, WAFER_PROCESS, TRACE_MONTH, _scenario_tables=edited, _reference_tables=edited
    )
    assert after_trace.routes["UPEH"].tolist() == pytest.approx(
        [0.5 * value for value in before_trace.routes["UPEH"]]
    )


def test_the_period_slice_bounds_the_product_months(
    key: sc.ScenarioCacheKey, tables: dict[str, pd.DataFrame]
) -> None:
    """캐시 키의 조회기간 밖 달을 물으면 그 달 칸은 0 이다(계산 결과가 그 기간으로 잘려 있다)."""
    outside = 202606
    demand = sc.get_process_product_demand(
        key,
        "no-order",
        WAFER_PROCESS,
        "제품정보",
        (START, outside),
        _scenario_tables=tables,
        _reference_tables=tables,
        _display_order=None,
    )

    assert outside > END
    assert demand[month_column(outside)].eq(0.0).all()
    assert demand[month_column(START)].gt(0).all()


def test_home_display_rates_follow_the_home_chain() -> None:
    """실행 Capa(%p)를 얹은 뒤 선행 B/O 변동률을 곱한다 — HOME 과 같은 함수·같은 차례다."""
    securement = pd.DataFrame(
        {
            "생산계획년월": [202611, 202612, 202611],
            "공정": [" Mold ", "Mold", "Saw"],
            "가용대수": [10.0, 10.0, 5.0],
            "소요대수": [10.0, 8.0, 5.0],
            "확보율": [1.0, 1.25, 1.0],
        }
    )
    execution = pd.DataFrame(
        {"생산계획년월": [202611], "공정": ["Mold"], "증감 확보율": [5.0], "비고": ["점검"]}
    )
    advance = pd.DataFrame({"생산계획년월": [202611, 202612], "변동률": [0.5, 1.0]})

    assert home_display_rates(securement, process="Mold", months=[202611, 202612, 202701]) == {
        202611: 1.0,
        202612: 1.25,
        202701: None,
    }
    with_execution = home_display_rates(
        securement, process="Mold", months=[202611, 202612], execution_rows=execution
    )
    assert with_execution[202611] == pytest.approx(1.05)
    assert with_execution[202612] == pytest.approx(1.25)
    both = home_display_rates(
        securement,
        process="Mold",
        months=[202611, 202612],
        execution_rows=execution,
        advance_ratio=advance,
    )
    assert both[202611] == pytest.approx(1.05 * 0.5)
    assert both[202612] == pytest.approx(1.25)
