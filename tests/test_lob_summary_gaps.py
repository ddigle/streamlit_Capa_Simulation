# Purpose: Capa LOB 요약의 선행 증감과 비교 GAP 이 각각 무엇을 기준으로 재는지 고정한다.

"""두 증감은 기준이 다르다.

**선행 증감**은 같은 시나리오의 선행 전후 차이다. **GAP**은 비교 시나리오와의 차이이고
선행과 무관한 **원 데이터끼리** 재야 한다 — 비교 쪽에는 선행이 반영되지 않기 때문이다.
선행 반영값으로 GAP 을 재면 남의 계획과의 차이에 내가 넣은 선행 물량이 섞인다.
"""

import pandas as pd

from capa_simulation.components.home_figures import build_lob_summary_figures

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
        secure_threshold=1.095,
        warning_threshold=0.995,
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
        secure_threshold=1.095,
        warning_threshold=0.995,
        baseline_lob_summary=None,
        comparison_density=_monthly([8.0, 8.0]),
        comparison_wafer=_wafer([800.0, 800.0]),
    )

    assert "+2.00" in _gap_texts(month_figure)
