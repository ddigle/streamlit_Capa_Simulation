# Purpose: dynamic capacity 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date

import pandas as pd
import pytest

from capa_simulation.components.dynamic_capacity_dashboard import (
    build_capacity_waterfall_figure,
    build_process_comparison_figure,
)
from capa_simulation.services.dynamic_capacity import (
    aggregate_dynamic_capacity,
    build_dynamic_capacity_demo,
    calculate_dynamic_capacity,
    filter_dynamic_capacity,
)


def _input_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "일자": date(2026, 8, 1),
        "공정": "Test",
        "제품정보": "HBM라",
        "Stack": "12H",
        "WF 구분": "Core",
        "소요기준": "WF",
        "표준 Capa": 100.0,
        "표준 효율": 0.80,
        "실적 효율": 0.72,
        "표준 UPEH": 10.0,
        "실적 UPEH": 9.0,
        "계획시간": 8.0,
        "실가동시간": 6.0,
        "Rundown 시간": 3.0,
        "설비 Down 시간": 1.0,
        "기타 제약시간": 0.0,
        "실적수량": 50.0,
    }
    row.update(overrides)
    return row


def test_dynamic_capacity_bridge_balances_to_actual() -> None:
    result = calculate_dynamic_capacity(pd.DataFrame([_input_row()]))
    row = result.iloc[0]

    assert row["효율 반영 Capa"] == pytest.approx(90.0)
    assert row["실효 Capa"] == pytest.approx(81.0)
    assert row["모델 실적 Capa"] == pytest.approx(54.0)
    assert row["효율 손실 Capa"] == pytest.approx(10.0)
    assert row["UPEH 손실 Capa"] == pytest.approx(9.0)
    assert row["재공부족 미활용 Capa"] == pytest.approx(27.0)
    assert row["기타 정합성 Gap"] == pytest.approx(4.0)
    assert (
        row["표준 Capa"]
        - row["효율 손실 Capa"]
        - row["UPEH 손실 Capa"]
        - row["재공부족 미활용 Capa"]
        - row["기타 정합성 Gap"]
    ) == pytest.approx(row["실적수량"])


def test_dynamic_capacity_aggregation_uses_time_weighted_rates() -> None:
    detail = calculate_dynamic_capacity(
        pd.DataFrame(
            [
                _input_row(),
                _input_row(
                    일자=date(2026, 8, 2),
                    **{
                        "표준 Capa": 50.0,
                        "실적 효율": 0.76,
                        "실적 UPEH": 8.0,
                        "계획시간": 4.0,
                        "실가동시간": 2.0,
                        "Rundown 시간": 1.0,
                        "실적수량": 18.0,
                    },
                ),
            ]
        )
    )

    summary = aggregate_dynamic_capacity(detail, ["공정"]).iloc[0]

    assert summary["표준 Capa"] == pytest.approx(150.0)
    assert summary["실적 효율"] == pytest.approx((0.72 * 8 + 0.76 * 4) / 12)
    assert summary["실적 UPEH"] == pytest.approx((9.0 * 6 + 8.0 * 2) / 8)
    assert summary["Capa 실현률"] == pytest.approx(68.0 / 150.0)


def test_dynamic_capacity_demo_filters_process_product_and_date() -> None:
    demo = build_dynamic_capacity_demo()
    filtered = filter_dynamic_capacity(
        demo,
        start_date=date(2026, 8, 16),
        end_date=date(2026, 8, 18),
        process="Wafer Sorter",
        product="HBM라",
    )

    assert len(filtered) == 3
    assert filtered["공정"].eq("Wafer Sorter").all()
    assert filtered["제품정보"].eq("HBM라").all()
    assert filtered["일자"].min() == pd.Timestamp("2026-08-16")
    assert filtered["일자"].max() == pd.Timestamp("2026-08-18")


def test_dynamic_capacity_demo_has_one_requirement_basis_per_process() -> None:
    demo = build_dynamic_capacity_demo()
    assert demo.groupby("공정")["소요기준"].nunique().le(1).all()


def test_the_process_comparison_puts_the_worst_process_on_top() -> None:
    """나란한 「관리 우선순위」 표와 같은 차례다 — 범주는 실현률 오름차순이고 축을 뒤집어 나쁜
    공정이 맨 위에 온다(후보 g7-20)."""
    summary = aggregate_dynamic_capacity(build_dynamic_capacity_demo(), ["공정"])
    worst = summary.sort_values("Capa 실현률", ascending=True, kind="stable").iloc[0]

    figure = build_process_comparison_figure(summary)

    assert figure.layout.yaxis.autorange == "reversed"
    assert figure.data[0].y[0] == str(worst["공정"])


def test_the_waterfall_names_quantities_not_the_gap_rates() -> None:
    """워터폴 칸은 수량이다 — 「효율 Gap」 · 「UPEH Gap」 은 공정 상세 표의 비율 차이 이름이라 쓰지
    않고, 손실 칸은 「손실을 파고드는 화면」 카드와 같은 이름이다(설계 규칙 UI-CON-02)."""
    summary = aggregate_dynamic_capacity(build_dynamic_capacity_demo(), ["공정"]).iloc[0]

    figure = build_capacity_waterfall_figure(summary)
    (waterfall,) = figure.data

    assert list(waterfall.x) == [
        "표준 Capa",
        "효율 손실",
        "UPEH 손실",
        "재공부족 미활용",
        "기타 Gap",
        "실제 실적",
    ]
    assert list(waterfall.y) == pytest.approx(
        [
            summary["표준 Capa"],
            -summary["효율 손실 Capa"],
            -summary["UPEH 손실 Capa"],
            -summary["재공부족 미활용 Capa"],
            -summary["기타 정합성 Gap"],
            summary["실적수량"],
        ]
    )


def test_the_waterfall_ticks_stay_flat_at_any_window_width() -> None:
    """자동 각도는 칸이 좁으면 눈금을 30도 · 90도로 눕히고 어느 쪽인지가 창 폭과 앞 그림 상태에
    달린다 — 각도를 못 박고 이름을 모두 두 줄로 접어 좁은 칸에 들인다."""
    summary = aggregate_dynamic_capacity(build_dynamic_capacity_demo(), ["공정"]).iloc[0]

    axis = build_capacity_waterfall_figure(summary).layout.xaxis

    assert axis.tickangle == 0
    assert list(axis.ticktext) == [
        "표준<br>Capa",
        "효율<br>손실",
        "UPEH<br>손실",
        "재공부족<br>미활용",
        "기타<br>Gap",
        "실제<br>실적",
    ]


def test_the_waterfall_hover_says_what_the_bar_says() -> None:
    """풍선 값은 막대 글과 같은 그 칸의 증감이다 — `%{y}` 는 누계라 손실 이름에 누계가 붙는다.
    눈금을 배열로 주면 `%{x}` 는 접은 눈금 글자를 내므로 이름은 `customdata` 로 받는다."""
    summary = aggregate_dynamic_capacity(build_dynamic_capacity_demo(), ["공정"]).iloc[0]

    (waterfall,) = build_capacity_waterfall_figure(summary).data

    assert list(waterfall.customdata) == list(waterfall.x)
    assert waterfall.hovertemplate == "%{customdata}<br>%{delta:,.1f}<extra></extra>"
