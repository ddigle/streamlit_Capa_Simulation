# Purpose: Capa LOB 요약의 선행 증감과 비교 GAP 이 각각 무엇을 기준으로 재는지 고정한다.

"""두 증감은 기준이 다르다.

**선행 증감**은 같은 시나리오의 선행 전후 차이다. **GAP**은 비교 시나리오와의 차이이고
선행과 무관한 **원 데이터끼리** 재야 한다 — 비교 쪽에는 선행이 반영되지 않기 때문이다.
선행 반영값으로 GAP 을 재면 남의 계획과의 차이에 내가 넣은 선행 물량이 섞인다.
"""

import pandas as pd

from capa_simulation.components.home_figures import build_lob_summary_figures
from capa_simulation.services.securement_threshold import SecurementThresholds

MONTHS = [202601, 202602]
MONTH_LABELS = ["26.01", "26.02"]


def _monthly(load: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"생산계획년월": MONTHS, "년월": MONTH_LABELS, "부하량": load},
    )


def _wafer(load: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"생산계획년월": MONTHS, "년월": MONTH_LABELS, "Wafer 부하량": load})


def _summary(load: list[float], wafer: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": MONTH_LABELS,
            "부하량": load,
            "Wafer 부하량": wafer,
            "확보율": [1.2, 1.2],
            "Wafer Capa": [w * 1.2 for w in wafer],
        }
    )


def _top5() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": MONTH_LABELS,
            "공정": ["A", "A"],
            "확보율": [1.2, 1.2],
            "순위": [1, 1],
            "부하량": [12.0, 12.0],
            "B/N Capa": [14.4, 14.4],
            "Wafer Capa": [100.0, 100.0],
        }
    )


def _capacity() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": MONTHS,
            "년월": MONTH_LABELS,
            "공정": ["A", "A"],
            "부하량": [12.0, 12.0],
            "확보율": [1.2, 1.2],
            "B/N Capa": [14.4, 14.4],
        }
    )


def _gap_texts(figure: object) -> list[str]:
    """증감 주석 문구. 부호로 시작하는 것만 증감이고 나머지는 값·라벨이다."""
    return [
        str(annotation.text)
        for annotation in figure.layout.annotations  # type: ignore[attr-defined]
        if annotation.text and str(annotation.text)[:1] in {"+", "-"}
    ]


def test_the_comparison_gap_ignores_the_advance_load() -> None:
    """선행을 켜도 GAP 은 선행 **전** 값과 비교 시나리오의 차이여야 한다.

    원데이터 10.0 · 선행 반영 12.0 · 비교 시나리오 8.0 이면 GAP 은 +2.00 이다. 선행 반영값을
    쓰면 +4.00 이 되어 남의 계획과의 차이에 내 선행 물량 2.0 이 섞인다.
    """
    advanced = _summary([12.0, 12.0], [1200.0, 1200.0])
    baseline = _summary([10.0, 10.0], [1000.0, 1000.0])
    comparison_density = _monthly([8.0, 8.0])
    comparison_wafer = _wafer([800.0, 800.0])

    _, month_figure = build_lob_summary_figures(
        monthly_density=_monthly([12.0, 12.0]),
        monthly_top5=_top5(),
        bottleneck_capacity=_capacity(),
        lob_summary=advanced,
        month_labels=MONTH_LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        baseline_lob_summary=baseline,
        comparison_density=comparison_density,
        comparison_wafer=comparison_wafer,
    )

    texts = _gap_texts(month_figure)
    # 선행 증감(+2.00)과 GAP(+2.00) 이 같은 수이므로 선행 반영값으로 쟀다면 +4.00 이 섞인다.
    assert "+4.00" not in texts, texts
    assert texts.count("+2.00") >= 1, texts


def test_without_an_advance_baseline_the_gap_uses_the_shown_values() -> None:
    """선행이 꺼져 있으면 화면 값이 곧 원 데이터라 그대로 비교한다."""
    shown = _summary([10.0, 10.0], [1000.0, 1000.0])

    _, month_figure = build_lob_summary_figures(
        monthly_density=_monthly([10.0, 10.0]),
        monthly_top5=_top5(),
        bottleneck_capacity=_capacity(),
        lob_summary=shown,
        month_labels=MONTH_LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        baseline_lob_summary=None,
        comparison_density=_monthly([8.0, 8.0]),
        comparison_wafer=_wafer([800.0, 800.0]),
    )

    assert "+2.00" in _gap_texts(month_figure)


def _month_gap_texts(*, advanced_wafer: float, comparison_wafer: float | None = None) -> list[str]:
    """Density 는 같고 Wafer 계획만 다른 한 쌍의 증감 문구. 기준(선행 전)은 1,000 매다."""
    comparison = None if comparison_wafer is None else _wafer([comparison_wafer] * 2)
    _, month_figure = build_lob_summary_figures(
        monthly_density=_monthly([10.0, 10.0]),
        monthly_top5=_top5(),
        bottleneck_capacity=_capacity(),
        lob_summary=_summary([10.0, 10.0], [advanced_wafer] * 2),
        month_labels=MONTH_LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        baseline_lob_summary=_summary([10.0, 10.0], [1000.0, 1000.0]),
        comparison_density=None if comparison is None else _monthly([10.0, 10.0]),
        comparison_wafer=comparison,
    )
    return _gap_texts(month_figure)


def test_a_small_wafer_plan_gap_is_not_written_as_zero() -> None:
    """천 매 단위 값 칸(`1K`)에 수백 매 증감을 `+0K` 로 적으면 0 이 아닌 증감이 0 으로 읽힌다.

    2026-10-01 브라우저 점검: 선행 +0.05 에 Wafer 계획 증감이 `+0K`/`-0K` 로 찍혔다.
    """
    texts = _month_gap_texts(advanced_wafer=1480.0)
    assert "+0.5K" in texts, texts
    assert not [text for text in texts if text in {"+0K", "-0K"}], texts

    assert "-0.5K" in _month_gap_texts(advanced_wafer=520.0)


def test_a_wafer_plan_gap_that_rounds_to_zero_is_left_out() -> None:
    """한 자리를 늘려도 0 으로 보이는 증감(50 매 미만)은 적지 않는다 — `+0.0K` 도 0 으로 읽힌다."""
    texts = _month_gap_texts(advanced_wafer=1020.0)
    assert not [text for text in texts if text.endswith("K")], texts


def test_the_comparison_wafer_gap_keeps_the_same_precision() -> None:
    """비교 GAP 도 같은 글자다. 원 데이터 1,000 매와 비교 800 매면 `+0.2K` 이다."""
    texts = _month_gap_texts(advanced_wafer=1000.0, comparison_wafer=800.0)
    assert "+0.2K" in texts, texts
