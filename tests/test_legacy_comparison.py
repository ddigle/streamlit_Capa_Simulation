# Purpose: 기존 결과 대조의 집계 단위가 뒤집히지 않게 고정한다.

"""원천의 기존 결과와 신규 계산을 맞춰 보는 규칙.

**접는 층을 어디서 잡느냐가 전부다.** 원천은 경로(공정·STEP·MCP)별로 행이 펼쳐져 있고
기존 결과 컬럼은 그 경로 행마다 같은 값이 반복된다. 그래서 기존 쪽은 계획 한 줄
(`RQ_PKG_PLAN` 업무 키) × `WF 구분` 을 한 칸으로 보고 그 안의 반복만 접은 뒤 대조 키로
합산한다.

처음에는 접는 층을 한 단계 위(대조 키)에서 잡았다. 그러자 같은 대조 키에 계획 줄이
여럿인 경우 — Capa Code·Customer·CS 가 다른 줄들 — 이 "값이 갈린다" 로 분류돼 대조에서
통째로 빠졌고, 샘플에서 Wafer 270키 중 121키만 보고 "완전 일치" 라는 거짓 결론이 났다.
`test_separate_plan_rows_are_summed_not_treated_as_a_conflict` 가 그 회귀를 막는다.

`기존 0·신규 있음` 을 따로 세는 것도 같은 이유다. 기존값이 0 이면 비율을 구할 수 없는데
예전에는 `fillna(0.0)` 으로 통과 처리해 59건을 놓쳤다.
"""

import pandas as pd
import pytest

from capa_simulation.io.core_data_source import load_core_data_contract
from capa_simulation.services.legacy_comparison import (
    AGREE_GROUP,
    COMPARISON_KEYS,
    COMPARISONS,
    FORMULA_INPUTS,
    GROUP_COLUMN,
    MANY_VALUES,
    OTHER_GROUP,
    RATIO_COLUMN,
    SUSPECT_GROUP,
    WAFER_ROUTE_FACTORS,
    WAFER_ROUTE_RESULTS,
    FactorAgreement,
    FactorFold,
    FormulaInput,
    LegacyMetric,
    ProcessConsistency,
    ResultFold,
    RouteCells,
    RouteFactor,
    RouteLink,
    RouteValueSpread,
    ScalingCheck,
    attach_formula_inputs,
    compare_metric,
    describe_ratios,
    difference_distribution,
    factor_agreement,
    fold_route_cells,
    fold_route_result,
    folded_route_totals,
    group_spread,
    hourly_rate,
    input_applies,
    legacy_grain,
    measured_wafer_load,
    median_ratio,
    plan_line_keys,
    process_consistency,
    ratio_distribution,
    ratio_groups,
    route_cells,
    route_factor_by_key,
    route_factor_values,
    scaling_check,
    split_mixed_processes,
    split_route_cells,
    summarize_comparison,
    time_agreement,
)
from capa_simulation.services.required_equipment import REQB_COLUMNS
from capa_simulation.services.unit_capacity import PERFORMANCE_KEYS, calculate_unit_capacity

METRIC = LegacyMetric(label="Wafer 부하량 (매)", legacy_column="WF수(매)")
CONTRACT = load_core_data_contract()

# 대조 키 밖에 있으면서 계획 줄을 가르는 컬럼들. 이것이 다르면 서로 다른 계획이다.
_PLAN_DEFAULTS = {
    "양산구분": "양산",
    "CS": "MP",
    "Capa Code": "CAPA-1",
    "Customer": "고객가",
    "Pack Code": "PACK-1",
}


def _plan_row(value: float, *, routes: int = 31, **overrides: object) -> pd.DataFrame:
    """계획 한 줄이 경로 `routes` 개로 펼쳐진 원천 조각.

    기존 결과 컬럼은 그 경로 행마다 같은 값으로 반복된다 — 실제 원천이 그렇다.
    """
    fields: dict[str, object] = {
        "생산계획년월": 202608,
        "제품정보": "Product-A",
        "Stack": "8H",
        "WF 구분": "Core",
        **_PLAN_DEFAULTS,
        **overrides,
    }
    return pd.DataFrame(
        {**{k: [v] * routes for k, v in fields.items()}, "WF수(매)": [value] * routes}
    )


def _core(*rows: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(rows, ignore_index=True)


def _calculated(*values: float, **overrides: object) -> pd.DataFrame:
    fields: dict[str, object] = {
        "생산계획년월": 202608,
        "제품정보": "Product-A",
        "Stack": "8H",
        "WF 구분": "Core",
        **overrides,
    }
    return pd.DataFrame({**{k: [v] * len(values) for k, v in fields.items()}, "물량": list(values)})


def _compare(core: pd.DataFrame, calculated: pd.DataFrame) -> pd.DataFrame:
    return compare_metric(core, calculated, METRIC, CONTRACT)


def test_repeated_route_rows_are_folded_not_summed() -> None:
    """한 계획 줄의 경로 31행에 같은 값이 반복돼도 기존값은 그 값 하나여야 한다."""
    comparison = _compare(_core(_plan_row(100.0)), _calculated(100.0))

    assert len(comparison) == 1
    assert comparison["기존값"].iloc[0] == 100.0
    assert comparison["차이"].iloc[0] == 0.0
    assert summarize_comparison(comparison)["허용 초과"] == 0


def test_separate_plan_rows_are_summed_not_treated_as_a_conflict() -> None:
    """같은 대조 키의 서로 다른 계획 줄은 **합산**이다. 값이 갈린 것이 아니다.

    이것을 값 불일치로 처리했다가 실제로 270키 중 149키를 대조에서 빠뜨렸다.
    """
    core = _core(
        _plan_row(100.0).assign(**{"Capa Code": "CAPA-1"}),
        _plan_row(60.0).assign(**{"Capa Code": "CAPA-2"}),
    )

    comparison = _compare(core, _calculated(160.0))
    summary = summarize_comparison(comparison)

    assert comparison["기존값"].iloc[0] == 160.0
    assert bool(comparison["값 불일치"].iloc[0]) is False
    assert summary["대조 건수"] == 1
    assert summary["값 불일치"] == 0


def test_a_real_difference_still_shows_up() -> None:
    """집계를 고쳤다고 진짜 차이까지 가려지면 안 된다."""
    comparison = _compare(_core(_plan_row(100.0)), _calculated(110.0))

    assert comparison["차이"].iloc[0] == 10.0
    assert comparison["차이율"].iloc[0] == 0.1
    assert summarize_comparison(comparison)["허용 초과"] == 1


def test_conflict_inside_one_plan_row_is_reported_not_picked() -> None:
    """한 계획 줄의 경로 행끼리 값이 갈리면 접을 수 없다. 조용히 고르지 않는다."""
    core = _plan_row(100.0, routes=2)
    core.loc[1, "WF수(매)"] = 200.0

    comparison = _compare(core, _calculated(100.0))
    summary = summarize_comparison(comparison)

    assert pd.isna(comparison["기존값"].iloc[0])
    assert bool(comparison["값 불일치"].iloc[0]) is True
    assert summary["값 불일치"] == 1
    assert summary["대조 건수"] == 0
    # 집계 실패를 "기존이 비워 둔 자리" 로 흘려보내면 안 된다.
    assert summary["신규에만 있음"] == 0


def test_one_sided_keys_are_counted_by_direction() -> None:
    """기존이 비워 둔 자리와 신규가 놓친 자리는 뜻이 정반대다."""
    calculated = pd.concat(
        [_calculated(100.0), _calculated(50.0, 제품정보="Product-B")], ignore_index=True
    )

    summary = summarize_comparison(_compare(_core(_plan_row(100.0)), calculated))

    assert summary["대조 건수"] == 1
    assert summary["신규에만 있음"] == 1
    assert summary["기존에만 있음"] == 0


def test_zero_legacy_value_is_counted_apart_from_a_ratio_breach() -> None:
    """기존값 0 은 비율이 없다. 통과로 세면 안 되고 허용 초과와 뭉쳐도 안 된다."""
    comparison = _compare(_core(_plan_row(0.0)), _calculated(5.0))
    summary = summarize_comparison(comparison)

    assert comparison["차이"].iloc[0] == 5.0
    assert pd.isna(comparison["차이율"].iloc[0])
    assert summary["기존 0·신규 있음"] == 1
    assert summary["허용 초과"] == 0
    assert summary["최대 차이율"] is None


def test_grain_follows_the_pkg_plan_business_key() -> None:
    """기존값이 한 번 기록되는 단위는 계약의 계획 업무 키다. 키가 늘면 대조도 따라간다."""
    assert legacy_grain(CONTRACT) == [*CONTRACT.derived_keys["RQ_PKG_PLAN"], "WF 구분"]
    assert COMPARISON_KEYS == ["생산계획년월", "제품정보", "Stack", "WF 구분"]


def test_plan_rows_that_differ_only_by_pack_code_are_summed_in_the_grain() -> None:
    """Pack Code 가 업무 키가 되면 두 줄은 각각의 그레인이라 대조 키에서 더해진다.

    승격 전에는 같은 그레인 안에서 값이 갈린 것으로 보여 `값 불일치` 가 되고 기존값이
    비워졌다 — 대조에서 통째로 빠지는 자리다.
    """
    core = _core(
        _plan_row(100.0).assign(**{"Pack Code": "PACK-1"}),
        _plan_row(60.0).assign(**{"Pack Code": "PACK-2"}),
    )

    comparison = _compare(core, _calculated(160.0))

    assert len(comparison) == 1
    assert comparison["기존값"].iloc[0] == 160.0
    assert bool(comparison["값 불일치"].iloc[0]) is False
    assert summarize_comparison(comparison)["값 불일치"] == 0


# ------------------------------------------------------------- 분포로만 접기 (사내 실데이터 확인용)


def _keyed(legacy: list[float | None], fresh: list[float | None]) -> pd.DataFrame:
    """제품마다 계획 한 줄. `None` 은 그쪽에 키가 없다는 뜻이다."""
    core_rows = [
        _plan_row(value, routes=3, 제품정보=f"Product-{index}")
        for index, value in enumerate(legacy)
        if value is not None
    ]
    calculated = pd.concat(
        [
            _calculated(value, 제품정보=f"Product-{index}")
            for index, value in enumerate(fresh)
            if value is not None
        ],
        ignore_index=True,
    )
    return _compare(_core(*core_rows), calculated)


def test_difference_distribution_counts_only_comparable_keys() -> None:
    """한쪽에만 있는 키·기존 0 인 키는 차이율 분포에 들지 않는다. 합계는 비율로만 남는다."""
    comparison = _keyed(
        [100.0, 100.0, 100.0, 0.0, 50.0, None], [100.0, 100.5, 120.0, 5.0, None, 7.0]
    )

    spread = difference_distribution(comparison)

    assert spread.keys == 3
    assert spread.median == pytest.approx(0.005)
    assert spread.maximum == pytest.approx(0.2)
    assert dict(spread.over) == {0.001: 2, 0.01: 1}
    # 대조 건수(기존 0 포함 4키)의 Σ신규 ÷ Σ기존.
    assert spread.sum_ratio == pytest.approx((100.0 + 100.5 + 120.0 + 5.0) / 300.0)


def test_ratio_distribution_shows_a_thousandfold_unit_gap() -> None:
    """단위가 1000 배 갈리면 비율이 1000 근처에 몰린다 — 값을 내보내지 않고 단위를 가린다."""
    comparison = _keyed([1000.0, 2010.0, 3.0, 0.0], [1.0, 2.0, 3.0, 4.0])

    spread = ratio_distribution(comparison)

    assert spread.keys == 3
    # 기존 0 인 키는 대조 건수에 들지만 비율은 없다.
    assert spread.undefined == 1
    assert dict(spread.near) == {1.0: 1, 1000.0: 2, 0.001: 0}
    assert dict(spread.decades) == {0: 1, 3: 2}


def test_describe_ratios_skips_non_positive_pairs() -> None:
    spread = describe_ratios(pd.Series([2.0, 0.0, -1.0, 4.0]), pd.Series([1.0, 1.0, 1.0, None]))

    assert spread.keys == 1
    assert spread.undefined == 3
    assert spread.median == 2.0


def test_custom_keys_fold_inside_their_grain_before_summing() -> None:
    """소요대수처럼 경로마다 값이 다른 컬럼은 경로 키까지 접는 단위로 잡아야 더해진다."""
    core = pd.concat(
        [
            _plan_row(1.5, routes=2, 공정="P1"),
            _plan_row(2.5, routes=2, 공정="P2"),
        ],
        ignore_index=True,
    )
    calculated = _calculated(1.5, 2.5).assign(공정=["P1", "P2"])
    metric = LegacyMetric(label="소요대수", legacy_column="WF수(매)", new_column="물량")
    keys = ["생산계획년월", "공정"]

    folded = compare_metric(
        core, calculated, metric, CONTRACT, keys=keys, grain=[*legacy_grain(CONTRACT), "공정"]
    )

    assert folded.columns[:2].tolist() == keys
    assert folded["기존값"].tolist() == [1.5, 2.5]
    assert folded["차이"].tolist() == [0.0, 0.0]
    with pytest.raises(ValueError, match="접는 단위 밖"):
        compare_metric(core, calculated, metric, CONTRACT, keys=keys)


# ------------------------------------------------------------- Chip 부하량 정식 대조 (2026-10-08)


def test_plan_chip_is_a_formal_comparison_on_plan_lines() -> None:
    """`Plan_Chip(K개)` 는 계획 줄(Pack Code 합산) × WF 구분으로 맞댄다. `GOOD_DIE` 는 빠진다."""
    chip = next(metric for metric in COMPARISONS if metric.legacy_column == "Plan_Chip(K개)")
    assert chip.plan_line
    assert "GOOD_DIE" not in {metric.legacy_column for metric in COMPARISONS}
    assert plan_line_keys(CONTRACT) == [k for k in legacy_grain(CONTRACT) if k != "Pack Code"]

    renamed = {"WF수(매)": "Plan_Chip(K개)"}
    core = _core(
        _plan_row(100.0).assign(**{"Pack Code": "PACK-1"}).rename(columns=renamed),
        _plan_row(60.0).assign(**{"Pack Code": "PACK-2"}).rename(columns=renamed),
        _plan_row(7.0).assign(**{"Capa Code": "CAPA-2"}).rename(columns=renamed),
    )
    plan_fields = {key: value for key, value in _PLAN_DEFAULTS.items() if key != "Pack Code"}
    calculated = pd.concat(
        [
            _calculated(100.0, 60.0).assign(**plan_fields),
            _calculated(7.0).assign(**{**plan_fields, "Capa Code": "CAPA-2"}),
        ],
        ignore_index=True,
    )

    comparison = compare_metric(core, calculated, chip, CONTRACT)

    # 계획 줄마다 한 칸 — 월×제품×Stack×WF 구분 하나로 뭉치지 않는다. Pack Code 둘은 더한다.
    assert len(comparison) == 2
    assert sorted(comparison["기존값"].tolist()) == [7.0, 160.0]
    assert comparison["차이"].tolist() == [0.0, 0.0]


# ------------------------------------------------------------- 소요대수 ≈60 배 가르기


def _path_key(
    process: str, area: str, basis: str, month: int, product: str, legacy: float, fresh: float
) -> dict[str, object]:
    """`compare_metric(keys=REQB_COLUMNS)` 결과 한 줄과 같은 꼴."""
    return {
        "생산계획년월": month,
        "Area_Name": area,
        "공정": process,
        "양산구분": "양산",
        "제품정보": product,
        "Stack": "8H",
        "Capa Code": "CAPA-1",
        "Customer": "고객가",
        "CS": "MP",
        "WF 구분": "Core",
        "STEP_SEQ": f"{process}-S1",
        "MCP_SEQ": "1A",
        "소요기준": basis,
        "기존값": legacy,
        "신규값": fresh,
        "값 불일치": False,
    }


def _sixty_fold_paths() -> pd.DataFrame:
    """공정 셋 × 두 달 × 두 제품. 일부러 ×60 무리를 만든다.

    - `P-MI`(MI · CHIP) — 전부 기존 = 신규 × 60.
    - `P-WF`(Main · WF) — 202608 만 × 60, 202607 은 × 1. 달이 이 공정을 가른다.
    - `P-OK`(Main · CHIP) — 전부 × 1. `P-MI` 와 부하량(공정 없는 키)을 같이 쓴다.
    """
    rows: list[dict[str, object]] = []
    for month in (202607, 202608):
        for product in ("Product-A", "Product-B"):
            rows.append(_path_key("P-MI", "MI", "CHIP", month, product, 60.0, 1.0))
            fold = 60.0 if month == 202608 else 1.0
            rows.append(_path_key("P-WF", "Main", "WF", month, product, 2.0 * fold, 2.0))
            rows.append(_path_key("P-OK", "Main", "CHIP", month, product, 3.0, 3.0))
    return pd.DataFrame(rows)


def _formula_input(label: str) -> FormulaInput:
    return next(item for item in FORMULA_INPUTS if item.label == label)


def test_ratio_groups_split_sixty_one_and_the_rest() -> None:
    pairs: list[tuple[float, float | None]] = [
        (60.0, 1.0),
        (61.5, 1.0),
        (1.02, 1.0),
        (7.0, 1.0),
        (0.0, 1.0),
        (5.0, None),
    ]
    frame = pd.DataFrame(
        [
            _path_key("P", "Main", "WF", 202608, f"Product-{index}", legacy, fresh or float("nan"))
            for index, (legacy, fresh) in enumerate(pairs)
        ]
    )

    groups = ratio_groups(frame)

    assert groups.frame[GROUP_COLUMN].tolist() == [
        SUSPECT_GROUP,
        SUSPECT_GROUP,
        AGREE_GROUP,
        OTHER_GROUP,
    ]
    # 기존 0 은 대조 건수에 들지만 비율이 없다. 신규가 빈 키는 대조 건수부터 아니다.
    assert groups.undefined == 1
    # 61.5 는 ±5% 안이지만 60 에 딱 붙지는 않는다 — 단위 상수라면 딱 붙는다.
    assert groups.tight == 1


def test_process_consistency_finds_the_mixed_process_and_what_splits_it() -> None:
    groups = ratio_groups(_sixty_fold_paths())
    frame = groups.frame.assign(순번=range(len(groups.frame)))

    assert groups.size(SUSPECT_GROUP) == 6
    assert groups.size(AGREE_GROUP) == 6
    assert process_consistency(frame) == ProcessConsistency(
        processes=3, all_suspect=1, all_agree=1, all_other=0, mixed=1, partly_other=0
    )
    splits = {
        count.attribute: (count.splits, count.fails, count.trivial)
        for count in split_mixed_processes(frame, ["생산계획년월", "제품정보", "순번"])
    }
    assert splits == {"생산계획년월": (1, 0, 0), "제품정보": (0, 1, 0), "순번": (0, 0, 1)}


def test_scaling_one_input_by_sixty_counts_what_it_fixes_and_what_it_breaks() -> None:
    """키 하나로는 어느 인자든 60 배를 맞춘다. 가르는 것은 인자 값을 같이 쓰는 ≈1 키다."""
    frame = ratio_groups(_sixty_fold_paths()).frame

    def check(label: str) -> ScalingCheck:
        item = _formula_input(label)
        return scaling_check(frame, item.keys, input_applies(frame, item))

    # ST 는 MI 에만 걸리고, MI 공정은 전부 ×60 이다 — 혼자서 그 넷을 설명한다.
    assert check("ST") == ScalingCheck(applicable=4, fixed=4, collateral=0)
    # UPEH 는 Main 에만 — P-WF 의 202608 둘. 값이 달마다 정해져 202607 과 나눠 쓰지 않는다.
    assert check("UPEH") == ScalingCheck(applicable=2, fixed=2, collateral=0)
    # 달×공정 단위 인자는 여섯 모두를 ≈1 하나 건드리지 않고 고친다.
    assert check("RUN_DAY") == ScalingCheck(applicable=6, fixed=6, collateral=0)
    # 공정 단위 모듈수는 P-WF 를 고치면 그 공정의 ≈1 둘이 같이 60 배가 된다.
    assert check("모듈수") == ScalingCheck(applicable=6, fixed=4, collateral=2)
    # 부하량은 공정이 없는 키라 P-MI 와 P-OK 가 같이 쓴다 — P-MI 를 고치면 P-OK 넷이 어긋난다.
    assert check("부하량") == ScalingCheck(applicable=6, fixed=2, collateral=4)
    # Net Die 는 WF 에만 걸린다 — P-WF 의 202608 둘.
    assert check("Net Die").applicable == 2


def test_formula_inputs_are_read_per_key_and_a_minutes_input_stands_out() -> None:
    """≈60 무리의 RUN_DAY 만 60 분의 1 이면 무리 중앙의 비가 그것을 드러낸다. 표 표기는 흡수한다."""
    frame = ratio_groups(_sixty_fold_paths()).frame
    run_day = pd.DataFrame(
        {
            "생산계획년월": ["202607", "202608", "202607", "202608", "202607", "202608"],
            "공정": [" P-MI", "P-MI", "p-wf", "P-WF", "P-OK", "P-OK "],
            "RUN_DAY": [0.5, 0.5, 30.0, 0.5, 30.0, 30.0],
        }
    )
    required = frame.loc[:, REQB_COLUMNS].assign(부하량=10.0)

    inputs = attach_formula_inputs(frame, required, {"RQ_RUN_DAY": run_day})

    spread = group_spread(inputs, inputs["RUN_DAY"])
    assert spread[SUSPECT_GROUP].median == 0.5
    assert spread[AGREE_GROUP].median == 30.0
    assert median_ratio(spread) == pytest.approx(1 / 60)
    assert inputs["부하량"].eq(10.0).all()
    # 표가 없으면 빈 칸이다 — 멈추지 않는다.
    assert inputs["UPEH"].isna().all()


def test_hourly_rate_is_the_rate_the_capacity_calculation_uses() -> None:
    """8-2 산식 인자 표의 `환산_UPEH` 는 대당 Capa 계산과 같은 식이다 — MI 는 60 ÷ ST(분 단위)."""
    rows = [
        ("MAIN", "WF", "P-1", 45.0, None),
        ("Main", "CHIP", "P-2", 72_000.0, None),
        ("mi", "WF", "P-3", None, 2.0),
        ("MI", "CHIP", "P-4", None, 0.5),
        ("MI ", "PKG", "P-5", None, 0.25),
    ]
    upeh = pd.DataFrame(
        {
            "생산계획년월": 202608,
            "Area_Name": [row[0] for row in rows],
            "소요기준": [row[1] for row in rows],
            "공정": [row[2] for row in rows],
            "STEP_SEQ": "S1",
            "MCP_SEQ": "1A",
            "양산구분": "양산",
            "제품정보": "Product-A",
            "Stack": "8H",
            "WF 구분": "Core",
            "UPEH": [row[3] for row in rows],
            "ST": [row[4] for row in rows],
        }
    )
    by_month = upeh[["생산계획년월", "공정", "양산구분"]]
    calculated = calculate_unit_capacity(
        upeh,
        by_month.assign(CAPA_RUN_RATE=0.8),
        by_month.assign(편중률=1.0),
        upeh[["공정"]].assign(모듈수=1.0),
        upeh[["생산계획년월", "공정"]].assign(RUN_DAY=30.0),
        upeh[PERFORMANCE_KEYS].assign(**{"Lot 측정률": 1.0}),
        upeh[PERFORMANCE_KEYS].assign(WF측정률=1.0),
    ).set_index("공정")["환산_UPEH"]

    rate = hourly_rate(upeh).set_axis(upeh["공정"])

    assert rate.tolist() == pytest.approx([45.0, 72.0, 30.0, 0.12, 0.24])
    assert rate.tolist() == pytest.approx(calculated.reindex(rate.index).tolist())


def test_hourly_rate_leaves_a_non_positive_st_blank() -> None:
    frame = pd.DataFrame(
        {"Area_Name": ["MI", "MI"], "소요기준": ["WF", "WF"], "UPEH": None, "ST": [0.0, -1.0]}
    )

    assert hourly_rate(frame).isna().all()


def test_time_agreement_is_one_when_upeh_and_minutes_st_tell_the_same_speed() -> None:
    """UPEH × ST ÷ 60 — ST 가 정의(한 개당 분)대로면 1. 한쪽이라도 없거나 0 이하면 빈 값."""
    frame = pd.DataFrame(
        {"UPEH": [120.0, 120.0, None, 0.0], "ST": [0.5, 30.0, 0.5, 0.5]},
    )

    agreement = time_agreement(frame)

    assert agreement.iloc[0] == pytest.approx(1.0)
    # 초로 적힌 ST 는 정의와 달라 60 배로 드러난다.
    assert agreement.iloc[1] == pytest.approx(60.0)
    assert agreement.iloc[2:].isna().all()


def test_route_columns_are_counted_by_group_without_values() -> None:
    frame = ratio_groups(_sixty_fold_paths()).frame
    route = frame.loc[:, REQB_COLUMNS].copy()
    route["모델명"] = frame[GROUP_COLUMN].map({SUSPECT_GROUP: "M-60", AGREE_GROUP: "M-1"})
    # ≈1 키 하나는 경로 행이 둘이고 모델이 갈린다.
    first_agree = frame.index[frame[GROUP_COLUMN].eq(AGREE_GROUP)][0]
    extra = route.loc[[first_agree]].assign(모델명="M-1b")
    route = pd.concat([route, extra], ignore_index=True)

    link = RouteLink.build(frame, route)
    contrast = link.contrast("모델명")

    assert contrast is not None
    assert contrast.distinct == {SUSPECT_GROUP: 1, AGREE_GROUP: 2, OTHER_GROUP: 0}
    assert (contrast.shared, contrast.suspect_only, contrast.suspect_only_keys) == (0, 1, 6)
    assert contrast.agree_only == 2
    assert int(link.labels("모델명").eq(MANY_VALUES).sum()) == 1
    assert link.contrast("없는 칸") is None


def test_route_totals_fold_repeats_and_sum_pack_codes() -> None:
    """`일 필요` 는 기존 소요대수와 같은 규칙 — 같은 계획 줄의 반복은 접고 Pack Code 는 더한다."""
    frame = ratio_groups(_sixty_fold_paths()).frame.iloc[:2]
    first, second = frame.loc[:, REQB_COLUMNS].to_dict("records")
    route = pd.DataFrame(
        [
            {**first, "Pack Code": "PK-1", "일 필요": 2.0},
            {**first, "Pack Code": "PK-2", "일 필요": 3.0},
            {**second, "Pack Code": "PK-1", "일 필요": 4.0},
            {**second, "Pack Code": "PK-1", "일 필요": 4.0},
        ]
    )

    totals = folded_route_totals(frame, route, "일 필요", legacy_grain(CONTRACT))

    assert totals.tolist() == [5.0, 4.0]


# ------------------------------------------------------------------ Wafer 경로 값 가르기


def _route_row(
    product: str,
    process: str,
    area: str | None,
    basis: str | None,
    value: float,
    **extra: object,
) -> dict[str, object]:
    """원천 한 행 — 계획 줄 키는 `_plan_row` 와 같고 경로 칸을 더한다. `area` 가 없으면 계획 행."""
    return {
        "생산계획년월": 202608,
        "제품정보": product,
        "Stack": "8H",
        "WF 구분": "Core",
        **_PLAN_DEFAULTS,
        "Area_Name": area,
        "공정": process,
        "STEP_SEQ": f"{process}-S1",
        "MCP_SEQ": "1A",
        "소요기준": basis,
        "Para": "1",
        "WF측정률": 0.5,
        "Lot 측정률": 1.0,
        "WF수(매)": value,
        **extra,
    }


def _wafer_routes() -> pd.DataFrame:
    """계획 줄 셋. 원천 경로 값 = 계획 줄 값 × Step수 로 갈리게 심는다.

    - A — 계획 행(100) + 경로 넷(Step수 2·3·4·3). Step수 3 이 둘이라 Step수 가 「가름」이다.
    - B — 경로 둘(Step수 2·3), `Lot 측정률` 이 비었다 — 그 후보로는 판정할 수 없다.
    - C — 경로 값이 모두 같고 0 인 행 하나 — 0 만 빼면 갈리지 않는다.
    """
    rows = [
        _route_row("A", "-", None, None, 100.0),
        _route_row("A", "P1", "Main", "CHIP", 200.0, Step수="2"),
        _route_row("A", "P2", "Main", "WF", 300.0, Step수="3"),
        _route_row("A", "P3", "MI", "CHIP", 400.0, Step수="4"),
        _route_row("A", "P4", "Main", "WF", 300.0, Step수="3"),
        _route_row("B", "P1", "Main", "CHIP", 100.0, Step수="2", **{"Lot 측정률": None}),
        _route_row("B", "P2", "Main", "WF", 150.0, Step수="3", **{"Lot 측정률": None}),
        _route_row("C", "P1", "Main", "CHIP", 70.0, Step수="2"),
        _route_row("C", "P2", "Main", "WF", 70.0, Step수="3"),
        _route_row("C", "P3", "MI", "CHIP", 0.0, Step수="4"),
    ]
    return pd.DataFrame(rows)


def _factor(label: str) -> RouteFactor:
    return next(factor for factor in WAFER_ROUTE_FACTORS if factor.label == label)


def test_route_cells_count_the_split_that_plan_rows_and_zeros_do_not_explain() -> None:
    spread, cells = route_cells(_wafer_routes(), "WF수(매)", legacy_grain(CONTRACT))

    # 셋 모두 `compare_metric` 이 접지 못하는 칸이다. 그 가운데 C 는 0 행만 빼면 한 값이다.
    assert spread == RouteValueSpread(cells=3, split=3, route_cells=3, route_split=2)
    assert len(cells.frame) == 8  # 계획 행과 0 행은 빠진다


def test_route_splits_are_told_by_the_attribute_that_carries_the_factor() -> None:
    _, cells = route_cells(_wafer_routes(), "WF수(매)", legacy_grain(CONTRACT))

    splits = {
        count.attribute: (count.splits, count.fails, count.trivial)
        for count in split_route_cells(cells, ["소요기준", "Step수", "Para", "없는 칸"])
    }

    # A 의 CHIP 경로 둘은 값이 다르다(못 가름). B 는 경로마다 소요기준이 달라 저절로 갈린다(자명).
    assert splits == {"소요기준": (0, 1, 1), "Step수": (1, 0, 1), "Para": (0, 2, 0)}


def test_dividing_by_the_carrying_column_folds_every_split_cell() -> None:
    _, cells = route_cells(_wafer_routes(), "WF수(매)", legacy_grain(CONTRACT))

    def fold(label: str) -> FactorFold:
        factor = _factor(label)
        return fold_route_cells(cells, route_factor_values(cells.frame, factor), label=label)

    assert fold("Step수") == FactorFold("Step수", testable=2, constant=0, divided=2, multiplied=0)
    # 칸 안에서 한 값인 칸은 무엇으로 나눠도 갈림이 남는다.
    assert fold("WF측정률") == FactorFold(
        "WF측정률", testable=2, constant=2, divided=0, multiplied=0
    )
    # B 에는 Lot 측정률이 없다 — 판정할 수 있는 칸은 A 하나다. 곱 후보도 같다.
    assert fold("Lot 측정률").testable == 1
    assert fold("Lot 측정률 × WF측정률") == FactorFold(
        "Lot 측정률 × WF측정률", testable=1, constant=1, divided=0, multiplied=0
    )
    # 원천에 없는 칸은 판정할 칸이 없다.
    assert fold("Shot수").testable == 0


def _result(label: str) -> RouteFactor:
    return next(factor for factor in WAFER_ROUTE_RESULTS if factor.label == label)


def _split_cells(**columns: list[float]) -> RouteCells:
    """경로 셋이 값 100·110·120 으로 갈리는 칸 하나 — 결과 칸 값은 `columns` 로 준다."""
    frame = pd.DataFrame(
        [
            _route_row(
                "A",
                f"P{index}",
                "Main",
                "WF",
                value,
                **{column: values[index] for column, values in columns.items()},
            )
            for index, value in enumerate((100.0, 110.0, 120.0))
        ]
    )
    return route_cells(frame, "WF수(매)", legacy_grain(CONTRACT))[1]


def test_result_columns_are_kept_apart_from_the_candidates() -> None:
    """`일 필요` 는 기존 시스템이 경로 값에서 만든 결과일 수 있다 — 설명 후보에 넣지 않는다."""
    labels = {factor.label for factor in WAFER_ROUTE_FACTORS}

    assert {factor.label for factor in WAFER_ROUTE_RESULTS} == {"일 필요", "TEST WF수(매)"}
    assert labels.isdisjoint({"일 필요", "TEST WF수(매)"})


def test_a_same_unit_result_column_is_tried_by_subtraction() -> None:
    cells = _split_cells(**{"TEST WF수(매)": [0.0, 10.0, 20.0]})

    assert fold_route_result(cells, _result("TEST WF수(매)")) == ResultFold(
        "TEST WF수(매)", additive=True, testable=1, constant=0, equal=0, inverse=1, forward=0
    )


def test_a_result_column_equal_to_the_value_explains_nothing() -> None:
    """결과 칸이 곧 경로 값이면 빼면 0 으로 「한 값」이 되지만 설명이 아니다 — 따로 센다."""
    cells = _split_cells(**{"TEST WF수(매)": [100.0, 110.0, 120.0]})

    assert fold_route_result(cells, _result("TEST WF수(매)")) == ResultFold(
        "TEST WF수(매)", additive=True, testable=1, constant=0, equal=1, inverse=0, forward=0
    )


def test_a_daily_result_column_folds_by_division_but_stays_a_result() -> None:
    """`일 필요` = 경로 값 ÷ 30 이면 나누면 한 값이 된다 — 원인이 아니라 결과라서 결과 칸 표에
    든다."""
    cells = _split_cells(**{"일 필요": [100.0 / 30, 110.0 / 30, 120.0 / 30]})

    fold = fold_route_result(cells, _result("일 필요"))

    assert (fold.additive, fold.testable, fold.equal, fold.inverse, fold.forward) == (
        False,
        1,
        0,
        1,
        0,
    )


def test_route_cells_do_not_mix_rows_that_share_an_index() -> None:
    frame = _wafer_routes()
    frame.index = [0] * len(frame)

    spread, _ = route_cells(frame, "WF수(매)", legacy_grain(CONTRACT))

    assert spread == RouteValueSpread(cells=3, split=3, route_cells=3, route_split=2)


def test_factor_agreement_tells_following_from_inverse_and_unrelated() -> None:
    frame = pd.DataFrame({RATIO_COLUMN: [3.0, 2.0, 1.0, 0.5, 1.0, 2.0]})
    factor = pd.Series([3.0, 2.0, 1.0, 2.0, 4.0, None])

    agreement = factor_agreement(frame, factor, label="Step수")

    # 후보가 1 인 키는 가를 수 없고, 후보가 빈 키는 세지 않는다.
    assert agreement == FactorAgreement(
        label="Step수", keys=5, off_one=4, near_factor=2, near_inverse=1, near_one=1
    )


def test_route_factors_are_read_per_key_from_the_source_route_rows() -> None:
    frame = ratio_groups(_sixty_fold_paths()).frame.iloc[:2]
    first, second = frame.loc[:, REQB_COLUMNS].to_dict("records")
    route = pd.DataFrame(
        [
            {**first, "Lot 측정률": 0.5, "WF측정률": 0.4},
            {**first, "Lot 측정률": 0.5, "WF측정률": 0.4},
            {**second, "Lot 측정률": "글자", "WF측정률": 0.4},
        ]
    )

    values = route_factor_by_key(RouteLink.build(frame, route), _factor("Lot 측정률 × WF측정률"))

    assert values.iloc[0] == pytest.approx(0.2)
    assert pd.isna(values.iloc[1])


def test_measured_wafer_load_moves_the_measurement_ratios_onto_the_load() -> None:
    """측정률은 대당 Capa 의 분모다. 비었거나 0 이면 계산과 같이 1.0 이다."""
    keys = ratio_groups(_sixty_fold_paths()).frame.loc[:, REQB_COLUMNS].iloc[:3]
    required = keys.assign(부하량=[10.0, 10.0, 10.0])
    performance = [key for key in REQB_COLUMNS if key not in {"Capa Code", "Customer", "CS"}]
    ratios = keys.loc[:, performance].drop(columns="소요기준")
    tables = {
        "RQ_LOT_RATIO": ratios.iloc[:2].assign(**{"Lot 측정률": [0.5, 0.0]}),
        "RQ_WF_RATIO": ratios.iloc[:1].assign(WF측정률=[0.4]),
    }

    load = measured_wafer_load(required, tables)

    assert load.tolist() == pytest.approx([2.0, 10.0, 10.0])
