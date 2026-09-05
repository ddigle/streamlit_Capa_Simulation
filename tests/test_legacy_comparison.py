# Purpose: 기존 결과 대조의 집계 방식이 뒤집히지 않게 고정한다.

"""원천의 기존 결과와 신규 계산을 맞춰 보는 규칙.

**두 쪽의 집계 방식이 다르다.** 원천은 경로(공정·STEP·MCP)별로 행이 펼쳐져 있고 기존
결과 컬럼은 그 행마다 같은 값이 반복된다. 실측하면 키 하나에 31행, 서로 다른 값은 1개다.
기존 쪽을 합산하면 경로 수만큼 뻥튀기되어 차이율이 30/31 = 96.77% 로 나온다 — 처음에
실제로 그렇게 나왔고, 계산이 틀린 줄 알 뻔했다. 그래서 기존은 대표값, 신규는 합계다.

`신규에만 있음` 과 `기존에만 있음` 을 따로 센다. 앞은 기존이 비워 둔 자리를 채우는
안전한 방향이고, 뒤는 신규가 놓쳤다는 뜻이라 성격이 정반대다.
"""

import pandas as pd

from capa_simulation.services.legacy_comparison import (
    COMPARISON_KEYS,
    LegacyMetric,
    compare_metric,
    summarize_comparison,
)

METRIC = LegacyMetric(label="Wafer 부하량 (매)", legacy_column="WF수(매)")


def _core(rows: int, value: float) -> pd.DataFrame:
    """같은 키의 경로 행 여러 개. 기존 결과 컬럼은 행마다 같은 값이다."""
    return pd.DataFrame(
        {
            "생산계획년월": [202608] * rows,
            "제품정보": ["Product-A"] * rows,
            "Stack": ["8H"] * rows,
            "WF 구분": ["Core"] * rows,
            "WF수(매)": [value] * rows,
        }
    )


def _calculated(value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": [202608],
            "제품정보": ["Product-A"],
            "Stack": ["8H"],
            "WF 구분": ["Core"],
            "물량": [value],
        }
    )


def test_repeated_legacy_rows_are_not_summed() -> None:
    """경로 31행에 같은 값이 반복돼도 기존값은 그 값 하나여야 한다."""
    comparison = compare_metric(_core(31, 100.0), _calculated(100.0), METRIC)

    assert len(comparison) == 1
    assert comparison["기존값"].iloc[0] == 100.0
    assert comparison["차이"].iloc[0] == 0.0
    assert summarize_comparison(comparison)["허용 초과"] == 0


def test_a_real_difference_still_shows_up() -> None:
    """집계를 고쳤다고 진짜 차이까지 가려지면 안 된다."""
    comparison = compare_metric(_core(31, 100.0), _calculated(110.0), METRIC)

    assert comparison["차이"].iloc[0] == 10.0
    assert comparison["차이율"].iloc[0] == 0.1
    assert summarize_comparison(comparison)["허용 초과"] == 1


def test_conflicting_legacy_values_are_not_silently_picked() -> None:
    """키 안에 서로 다른 기존 값이 있으면 대표값을 고를 수 없다. 결측으로 둔다."""
    core = _core(2, 100.0)
    core.loc[1, "WF수(매)"] = 200.0

    comparison = compare_metric(core, _calculated(100.0), METRIC)

    assert pd.isna(comparison["기존값"].iloc[0])
    assert summarize_comparison(comparison)["대조 건수"] == 0


def test_one_sided_keys_are_counted_by_direction() -> None:
    """기존이 비워 둔 자리와 신규가 놓친 자리는 뜻이 정반대다."""
    core = _core(3, 100.0)
    extra = _calculated(50.0).assign(제품정보="Product-B")
    calculated = pd.concat([_calculated(100.0), extra], ignore_index=True)

    summary = summarize_comparison(compare_metric(core, calculated, METRIC))

    assert summary["대조 건수"] == 1
    assert summary["신규에만 있음"] == 1
    assert summary["기존에만 있음"] == 0


def test_zero_legacy_value_reports_the_gap_without_a_ratio() -> None:
    """0 으로 나누면 무한대가 된다. 절대 차이만 남기고 비율은 비운다."""
    comparison = compare_metric(_core(3, 0.0), _calculated(5.0), METRIC)

    assert comparison["차이"].iloc[0] == 5.0
    assert pd.isna(comparison["차이율"].iloc[0])


def test_comparison_keys_exist_on_both_sides() -> None:
    """키가 바뀌면 대조가 통째로 어긋난다. 계약을 눈에 보이게 고정해 둔다."""
    assert COMPARISON_KEYS == ["생산계획년월", "제품정보", "Stack", "WF 구분"]
