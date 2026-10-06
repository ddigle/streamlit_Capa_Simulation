# Purpose: 과거 구간 월 열이 표·차트에서 한 단계 어두운 면색으로 구분되는지 고정한다.

"""과거 구간 면색 계약.

Past Data 로 채운 달의 값은 DB 계산 결과가 아니라 입력해 둔 지난 이력이다. 숫자만 보아서는
둘이 구분되지 않으므로 열 바탕을 한 단계 눌러 알린다. 같은 경계가 GAP 을 적을지도 정한다 —
`gap_month_labels` 와 여기의 과거 판정은 하나의 근거(`calculated_months`)에서 나온다.

칠하는 곳은 세 군데다. Capa LOB 요약(표 칸 + 차트 두 칸), 계획 세부수량(표 칸), 상세 B/N
(차트 열). 세 Figure 가 같은 월 축을 세로로 공유하므로 한 곳만 빠져도 띠가 중간에 끊긴다.
"""

from collections.abc import Collection
from typing import Any, TypedDict

import pandas as pd

from capa_simulation.components.home_figures import (
    build_bottleneck_detail_figures,
    build_lob_summary_figures,
    build_plan_detail_figures,
)
from capa_simulation.design import tokens
from capa_simulation.services.month_columns import build_past_month_labels
from capa_simulation.services.securement_threshold import SecurementThresholds

# 26.01 은 과거, 26.07·26.08 은 DB 계산 구간, 26년 은 둘이 섞인 연간 Total 이다.
MONTH_LABELS = ["26.01", "26.07", "26.08", "26년"]
YEAR_TOTALS = ["26년"]
CALCULATED = {"26.07", "26.08"}
PAST = build_past_month_labels(MONTH_LABELS, YEAR_TOTALS, CALCULATED)


def _rects(figure: Any, color: str) -> list[Any]:
    """그 면색으로 칠한 사각형. 두 Figure 모두 면색을 `shapes` 로 그린다."""
    return [
        shape for shape in figure.layout.shapes if shape.type == "rect" and shape.fillcolor == color
    ]


# ------------------------------------------------------------------ 과거 판정


def test_a_month_outside_the_db_range_is_past() -> None:
    assert "26.01" in PAST
    assert "26.07" not in PAST and "26.08" not in PAST


def test_a_year_total_mixing_past_and_db_months_is_not_past() -> None:
    """섞인 합계를 과거로 칠하면 그 해 전체가 확정된 실적으로 읽힌다."""
    assert "26년" not in PAST


def test_a_year_total_whose_months_are_all_past_is_past() -> None:
    labels = ["25.11", "25.12", "25년", "26.07"]

    past = build_past_month_labels(labels, ["25년"], {"26.07"})

    assert past == frozenset({"25.11", "25.12", "25년"})


def test_a_year_total_without_any_month_column_is_not_past() -> None:
    """빈 조건에 `all()` 이 참이 되는 자리다. 달이 없는 Total 은 판단 근거가 없다."""
    assert build_past_month_labels(["26년"], YEAR_TOTALS, CALCULATED) == frozenset()


# ------------------------------------------------------- Capa LOB 요약 (표·차트)


class _LobFrames(TypedDict):
    """`build_lob_summary_figures(**frames)` 로 펼치는 네 프레임."""

    monthly_density: pd.DataFrame
    lob_summary: pd.DataFrame
    bottleneck_capacity: pd.DataFrame
    monthly_top5: pd.DataFrame


def _lob_frames() -> _LobFrames:
    months = [202601, 202607, 202608]
    labels = ["26.01", "26.07", "26.08"]
    return {
        "monthly_density": pd.DataFrame(
            {"생산계획년월": months, "년월": labels, "부하량": [1.0, 1.5, 1.6]}
        ),
        "lob_summary": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "부하량": [1.0, 1.5, 1.6],
                "Wafer 부하량": [9_000.0, 12_000.0, 13_000.0],
                "Wafer Capa": [9_500.0, 11_000.0, 12_000.0],
            }
        ),
        "bottleneck_capacity": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "공정": ["SAW"] * 3,
                "확보율": [0.95, 0.82, 0.88],
                "B/N Capa": [1.0, 1.2, 1.3],
            }
        ),
        "monthly_top5": pd.DataFrame(
            {
                "생산계획년월": months,
                "년월": labels,
                "순위": [1, 1, 1],
                "공정": ["SAW"] * 3,
                "확보율": [0.95, 0.82, 0.88],
                "Wafer Capa": [9_500.0, 11_000.0, 12_000.0],
                "B/N Capa": [1.0, 1.2, 1.3],
            }
        ),
    }


def _lob_month_figure(past: Collection[str] | None) -> Any:
    _, month_figure = build_lob_summary_figures(
        **_lob_frames(),
        month_labels=MONTH_LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        year_totals={"26년": {"부하량": 4.1, "Wafer 부하량": 34_000.0}},
        past_month_labels=past,
    )
    return month_figure


def test_the_lob_past_band_covers_the_whole_column() -> None:
    """표 칸만 칠하면 띠가 표 아래에서 끊긴다. 차트 면은 행이 없어 세로 띠로 따로 덮는다."""
    rects = _rects(_lob_month_figure(PAST), tokens.SURFACE_PAST)

    assert rects, "과거 구간을 칠한 자리가 없다"
    # 26.01 은 네 칸 중 첫 칸이다. 표 칸과 차트 띠가 같은 x 범위를 써야 세로로 이어진다.
    assert {(round(rect.x0, 6), round(rect.x1, 6)) for rect in rects} == {(0.0, 0.25)}
    # 값 세 행과 차트 띠는 y 범위가 다르다. 하나뿐이면 어느 한쪽이 빠진 것이다.
    assert len({(rect.y0, rect.y1) for rect in rects}) > 1, "표와 차트 중 한쪽이 비었다"


def test_the_lob_year_total_column_keeps_its_own_surface() -> None:
    """과거색이 합계 칸까지 덮으면 두 종류의 특별한 열이 한 색으로 뭉친다."""
    assert _rects(_lob_month_figure(PAST), tokens.SURFACE_YEAR_TOTAL)


def test_lob_without_past_labels_keeps_the_old_surfaces() -> None:
    """과거를 모르는 호출자(테스트·다른 화면)의 화면이 바뀌면 안 된다."""
    figure = _lob_month_figure(None)

    assert not _rects(figure, tokens.SURFACE_PAST)
    assert _rects(figure, tokens.SURFACE_YEAR_TOTAL)


# ------------------------------------------------------------- 계획 세부수량 (표)


def _detail() -> pd.DataFrame:
    """제품이 둘이라 줄무늬가 갈린다 — 과거 구간에서도 그 갈림이 남아야 한다."""
    return pd.DataFrame(
        {
            "제품정보": ["A", "B"],
            "Stack": ["12H", "8H"],
            "26.01": [1_000.0, 500.0],
            "26.07": [200.0, 100.0],
            "26.08": [300.0, 150.0],
            "26년": [1_500.0, 750.0],
        }
    )


def _detail_column_fills(past: Collection[str] | None) -> list[list[str]]:
    _, month_figure = build_plan_detail_figures(
        production_detail=_detail(),
        month_labels=MONTH_LABELS,
        year_total_labels=YEAR_TOTALS,
        past_month_labels=past,
    )
    return [list(column) for column in month_figure.data[0].cells.fill.color]


def test_the_detail_table_keeps_the_product_stripe_inside_the_past_column() -> None:
    """줄무늬를 과거색 하나로 덮으면 그 구간에서만 제품 경계가 사라진다."""
    columns = _detail_column_fills(PAST)

    assert columns[0] == [tokens.SURFACE_PAST, tokens.SURFACE_PAST_SUBTLE]
    assert columns[1] == [tokens.SURFACE, tokens.SURFACE_SUBTLE]
    assert columns[3] == [tokens.SURFACE_YEAR_TOTAL] * 2


def test_the_detail_table_without_past_labels_keeps_the_old_surfaces() -> None:
    assert _detail_column_fills(None)[0] == [tokens.SURFACE, tokens.SURFACE_SUBTLE]


# ----------------------------------------------------------------- 상세 B/N (차트)


def _bottleneck_month_figure(past: Collection[str] | None) -> Any:
    details = pd.DataFrame(
        {
            "생산계획년월": [202601, 202607, 202608],
            "년월": ["26.01", "26.07", "26.08"],
            "순위": [1, 1, 1],
            "공정": ["SAW"] * 3,
            "확보율": [0.95, 0.82, 0.88],
            "가용대수": [10.0, 10.0, 10.0],
            "소요대수": [11.0, 12.0, 12.5],
            "Wafer Capa": [9_500.0, 11_000.0, 12_000.0],
        }
    )
    _, month_figure = build_bottleneck_detail_figures(
        monthly_bottleneck_details=details,
        month_labels=MONTH_LABELS,
        thresholds=SecurementThresholds(1.095, 0.995),
        year_total_labels=YEAR_TOTALS,
        past_month_labels=past,
    )
    return month_figure


def test_the_bottleneck_detail_bands_the_past_column_below_its_header() -> None:
    """머리글까지 누르면 월 라벨 줄이 구간마다 다른 회색으로 끊긴다."""
    rects = _rects(_bottleneck_month_figure(PAST), tokens.SURFACE_PAST)

    assert len(rects) == 1
    assert (round(rects[0].x0, 6), round(rects[0].x1, 6)) == (0.0, 0.25)
    assert rects[0].y0 == 0


def test_the_bottleneck_detail_without_past_labels_keeps_the_old_surfaces() -> None:
    figure = _bottleneck_month_figure(None)

    assert not _rects(figure, tokens.SURFACE_PAST)
    assert _rects(figure, tokens.SURFACE_YEAR_TOTAL)


# --------------------------------------------------------------------- 가독성


def _luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def test_the_past_surfaces_stay_readable_behind_body_text() -> None:
    """면을 눌러 구간을 알리되 값은 그대로 읽혀야 한다."""
    text = _luminance(tokens.TEXT)
    for surface in (
        tokens.SURFACE_PAST,
        tokens.SURFACE_PAST_SUBTLE,
        tokens.SURFACE_PAST_YEAR_TOTAL,
    ):
        contrast = (_luminance(surface) + 0.05) / (text + 0.05)
        assert contrast >= 7.0, f"{surface} 위의 본문 대비가 {contrast:.1f}:1 이다"


def test_the_past_surfaces_keep_the_hierarchy_they_replace() -> None:
    """줄무늬와 합계의 위계가 과거 구간에서 뒤집히면 같은 표가 구간마다 다르게 읽힌다."""
    assert _luminance(tokens.SURFACE) - _luminance(tokens.SURFACE_PAST) > 0.1
    assert (
        _luminance(tokens.SURFACE_PAST)
        > _luminance(tokens.SURFACE_PAST_SUBTLE)
        > _luminance(tokens.SURFACE_PAST_YEAR_TOTAL)
    )
