# Purpose: B/N Top5 확보율 구간의 검증·저장·막대 높이 반영을 고정한다.

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from capa_simulation.components.home_figures import build_lob_summary_figures
from capa_simulation.components.process_labels import process_labels_from_rules
from capa_simulation.services.process_rename import PROCESS_RENAME_COLUMNS
from capa_simulation.services.top5_band import (
    DEFAULT_TOP5_MAX_RATE,
    DEFAULT_TOP5_MIN_RATE,
    clamp_rate,
    validate_top5_band,
)

LABELS = process_labels_from_rules(
    pd.DataFrame([], columns=list(PROCESS_RENAME_COLUMNS)),
    version=1,
)
MONTHS = ["26.08"]


def test_default_band_is_fifty_to_two_hundred_percent() -> None:
    """화면 기본값이다. 확보율은 비율이라 0.5 = 50% 다."""
    assert (DEFAULT_TOP5_MIN_RATE, DEFAULT_TOP5_MAX_RATE) == (0.50, 2.00)


def test_band_rejects_an_inverted_or_negative_range() -> None:
    with pytest.raises(ValueError, match="상한은 하한보다"):
        validate_top5_band(2.0, 0.5)
    with pytest.raises(ValueError, match="0% 이상"):
        validate_top5_band(-0.1, 2.0)


def test_clamp_cuts_at_both_ends() -> None:
    band = (0.5, 2.0)
    assert clamp_rate(0.2, band) == pytest.approx(0.5)
    assert clamp_rate(1.0, band) == pytest.approx(1.0)
    assert clamp_rate(28.6, band) == pytest.approx(2.0)


def _frames() -> dict[str, pd.DataFrame]:
    """한 달, Top5 세 줄. 확보율이 밴드 아래·안·위로 하나씩이다."""
    density = pd.DataFrame({"생산계획년월": [202608], "년월": ["26.08"], "부하량": [10.0]})
    return {
        "monthly_density": density,
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "년월": ["26.08"],
                "부하량": [10.0],
                "Wafer 부하량": [1000.0],
                "Wafer Capa": [900.0],
            }
        ),
        "bottleneck_capacity": pd.DataFrame(
            {
                "생산계획년월": [202608],
                "년월": ["26.08"],
                "공정": ["P1"],
                "확보율": [0.3],
                "B/N Capa": [3.0],
            }
        ),
        "monthly_top5": pd.DataFrame(
            {
                "생산계획년월": [202608, 202608, 202608],
                "년월": ["26.08"] * 3,
                "공정": ["P1", "P2", "P3"],
                "순위": [1, 2, 3],
                "부하량": [10.0, 10.0, 10.0],
                "확보율": [0.30, 1.00, 28.60],
                "B/N Capa": [3.0, 10.0, 286.0],
                "Wafer Capa": [300.0, 1000.0, 28600.0],
            }
        ),
    }


def _top5_trace(figure: object) -> object:
    return next(
        trace
        for trace in figure.data  # type: ignore[attr-defined]
        if getattr(trace, "name", "") == "B/N Capa Top 5"
    )


def _build(band: tuple[float, float]) -> object:
    frames = _frames()
    _, month_figure = build_lob_summary_figures(
        lob_summary=frames["lob_summary"],
        monthly_density=frames["monthly_density"],
        bottleneck_capacity=frames["bottleneck_capacity"],
        monthly_top5=frames["monthly_top5"],
        month_labels=MONTHS,
        process_labels=LABELS,
        secure_threshold=1.095,
        warning_threshold=0.995,
        top5_rate_band=band,
    )
    return month_figure


def test_bar_heights_are_cut_at_the_band() -> None:
    """막대 높이는 `부하량 × 밴드로 자른 확보율` 이다.

    밴드가 없으면 확보율 2860% 인 공정 하나가 그 달의 다른 막대를 눈동자로 만든다.
    """
    trace = _top5_trace(_build((0.5, 2.0)))

    # 30% → 50% 로 올려 5.0, 100% 는 그대로 10.0, 2860% → 200% 로 잘려 20.0.
    assert list(trace.y) == pytest.approx([5.0, 10.0, 20.0])  # type: ignore[attr-defined]


def test_a_wider_band_lets_the_tall_bar_grow() -> None:
    """구간을 넓히면 잘리던 막대가 그만큼 자란다."""
    trace = _top5_trace(_build((0.5, 5.0)))

    assert list(trace.y) == pytest.approx([5.0, 10.0, 50.0])  # type: ignore[attr-defined]


def test_hover_keeps_the_real_capa_not_the_cut_bar() -> None:
    """자르는 것은 막대 길이뿐이다. hover 숫자는 실제 Capa 여야 한다."""
    trace = _top5_trace(_build((0.5, 2.0)))

    template = trace.hovertemplate  # type: ignore[attr-defined]
    assert "customdata[4]" in template, template
    assert "%{y" not in template, "잘린 막대 값이 hover 에 뜬다"
    assert list(trace.customdata[2])[4] == pytest.approx(286.0)  # type: ignore[attr-defined]


def test_migration_is_registered(tmp_path: Path) -> None:
    """0022 가 카탈로그에 등재돼 있어야 한다. 기존 SQL 은 한 글자도 고치지 않는다."""
    root = Path(__file__).resolve().parents[1]
    catalog = (root / "docs/migration_catalog.md").read_text(encoding="utf-8")

    assert "0022_global_top5_band.sql" in catalog
