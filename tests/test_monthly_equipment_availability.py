# Purpose: 월별 Dynamic 가용대수의 일수 안분과 가용 소계 규칙을 검사한다.

"""**사용자가 준 숫자가 그대로 나와야 한다** — 9/30 Qual 설비의 10월 기여 0.52대.

그리고 두 가지를 더 지킨다.

- **아홉 상태를 다 더하면 1.0 이다.** 한 호기는 어느 날 하나의 상태만 갖고 구간이
  서로 맞물려 있으므로, 한 달에 그 호기가 내는 기여도의 합은 언제나 1.0 이어야 한다.
  어긋나면 하루가 두 번 세어졌거나 어느 상태에도 안 잡힌 것이다.
- **가용 소계에는 `기존보유` 와 `가용` 만 들어간다.** 여덟을 합계에 넣으면 아직
  들어오지도 않은 설비가 가용대수로 세어진다.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.monthly_equipment_availability import (
    CATEGORIES,
    available_subtotal,
    build_monthly_equipment_availability,
    processes_in,
    span_date_range,
)
from capa_simulation.services.process_cutoff import prepare_process_cutoff

PROCESS = "DEMO_ATTACH"


def cutoff_table(days: float, process: str = PROCESS) -> pd.DataFrame:
    return prepare_process_cutoff(
        pd.DataFrame({"공정": [process], "Cutoff일수": [days], "비고": [None]})
    )


def spans(rows: list[tuple[str, str, date, date]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["설비명", "상태", "시작일", "종료일"]).assign(
        공정소분류=PROCESS
    )[["설비명", "공정소분류", "상태", "시작일", "종료일"]]


def empty_baseline() -> pd.DataFrame:
    return pd.DataFrame(
        {"공정": pd.Series(dtype="string"), "기존보유대수": pd.Series(dtype="float64")}
    )


def test_the_worked_example_gives_half_a_unit() -> None:
    """9/30 Qual 완료 → 10월 `(9/15, 10/16]` 에 16일 → 0.52대."""
    frame = build_monthly_equipment_availability(
        spans([("EQ-1", "가용", date(2026, 9, 30), date(2026, 12, 31))]),
        empty_baseline(),
        cutoff_table(15),
        [202610],
    )

    available = frame.loc[frame["분류"] == "가용", "대수"]
    assert round(float(available.iloc[0]), 2) == 0.52


def test_every_status_of_one_unit_adds_up_to_one_month() -> None:
    """서로 맞물린 구간이면 한 호기의 한 달 기여 합은 1.0 이다."""
    unit_spans = spans(
        [
            ("EQ-1", "입고 예정", date(2026, 9, 1), date(2026, 9, 19)),
            ("EQ-1", "셋업 진행중", date(2026, 9, 20), date(2026, 9, 29)),
            ("EQ-1", "가용", date(2026, 9, 30), date(2026, 10, 9)),
            ("EQ-1", "운영 비가동", date(2026, 10, 10), date(2026, 12, 31)),
        ]
    )

    frame = build_monthly_equipment_availability(
        unit_spans, empty_baseline(), cutoff_table(15), [202610]
    )

    assert round(float(frame["대수"].sum()), 6) == 1.0


def test_the_available_subtotal_excludes_the_reference_rows() -> None:
    """입고 예정·셋업 진행중은 아직 못 쓰는 설비라 소계에 넣지 않는다."""
    unit_spans = spans(
        [
            ("EQ-1", "입고 예정", date(2026, 9, 1), date(2026, 9, 29)),
            ("EQ-1", "가용", date(2026, 9, 30), date(2026, 12, 31)),
        ]
    )

    frame = build_monthly_equipment_availability(
        unit_spans, empty_baseline(), cutoff_table(15), [202610]
    )
    subtotal = available_subtotal(frame)

    assert round(float(subtotal["Dynamic가용대수"].iloc[0]), 2) == 0.52
    assert round(float(frame["대수"].sum()), 6) == 1.0  # 전체는 1.0 이지만
    assert set(frame.loc[frame["가용반영"], "분류"]) == {"가용"}


def test_the_baseline_is_not_prorated() -> None:
    """기존보유는 날짜가 없어 달마다 만액이다."""
    baseline = pd.DataFrame({"공정": [PROCESS], "기존보유대수": [10.0]})

    frame = build_monthly_equipment_availability(
        spans([]), baseline, cutoff_table(15), [202610, 202611]
    )

    rows = frame.loc[frame["분류"] == "기존보유"]
    assert list(rows["생산계획년월"]) == [202610, 202611]
    assert list(rows["대수"]) == [10.0, 10.0]


def test_a_process_without_a_cutoff_is_left_out() -> None:
    """Cut-off 를 안 적은 공정은 산출에서 빠진다 — 0 을 적은 것과 다르다."""
    other = spans([("EQ-1", "가용", date(2020, 1, 1), date(2030, 1, 1))]).assign(
        공정소분류="적지_않은_공정"
    )

    frame = build_monthly_equipment_availability(
        other, empty_baseline(), cutoff_table(15), [202610]
    )

    assert frame.empty


def test_a_downtime_month_shows_as_a_negative_sign_row() -> None:
    unit_spans = spans([("EQ-1", "운영 비가동", date(2026, 9, 1), date(2026, 12, 31))])

    frame = build_monthly_equipment_availability(
        unit_spans, empty_baseline(), cutoff_table(15), [202610]
    )

    row = frame.loc[frame["분류"] == "운영 비가동"].iloc[0]
    assert int(row["부호"]) == -1
    assert not bool(row["가용반영"])
    assert round(float(row["대수"]), 6) == 1.0


def test_span_date_range_reaches_back_by_the_cutoff() -> None:
    """Cut-off 가 크면 구간을 그만큼 앞에서부터 만들어야 한다."""
    window = span_date_range([202610], cutoff_table(45))

    # 첫 구간 `(8/16, 9/16]` 의 앞 경계부터다 — 첫 기여일 8/17 을 정하는 것은 8/16 의 상태다.
    assert window == (date(2026, 8, 16), date(2026, 9, 16))


def test_span_date_range_is_none_without_any_cutoff() -> None:
    assert span_date_range([202610], prepare_process_cutoff(pd.DataFrame())) is None


def test_two_units_add_up() -> None:
    unit_spans = spans(
        [
            ("EQ-1", "가용", date(2020, 1, 1), date(2030, 1, 1)),
            ("EQ-2", "가용", date(2020, 1, 1), date(2030, 1, 1)),
        ]
    )

    frame = build_monthly_equipment_availability(
        unit_spans, empty_baseline(), cutoff_table(0), [202610]
    )

    assert float(frame.loc[frame["분류"] == "가용", "대수"].iloc[0]) == 2.0


def test_rows_follow_the_declared_category_order() -> None:
    unit_spans = spans(
        [
            ("EQ-1", "운영 비가동", date(2026, 1, 1), date(2026, 6, 30)),
            ("EQ-1", "가용", date(2026, 7, 1), date(2026, 12, 31)),
        ]
    )
    baseline = pd.DataFrame({"공정": [PROCESS], "기존보유대수": [1.0]})

    frame = build_monthly_equipment_availability(unit_spans, baseline, cutoff_table(0), [202610])

    order = [category.name for category in CATEGORIES]
    seen = list(frame["분류"])
    assert seen == sorted(seen, key=order.index)


def test_processes_in_collects_both_sources() -> None:
    baseline = pd.DataFrame({"공정": ["BASE_ONLY"], "기존보유대수": [1.0]})
    unit_spans = spans([("EQ-1", "가용", date(2026, 1, 1), date(2026, 12, 31))])

    assert processes_in(unit_spans, baseline) == sorted([PROCESS, "BASE_ONLY"])


@pytest.mark.parametrize("months", [[202601], [202602], [202612]])
def test_a_full_year_unit_contributes_exactly_one_each_month(months: list[int]) -> None:
    """한 해 내내 가용인 설비는 어느 달이든 정확히 1.0 이다."""
    unit_spans = spans([("EQ-1", "가용", date(2020, 1, 1), date(2030, 1, 1))])

    frame = build_monthly_equipment_availability(
        unit_spans, empty_baseline(), cutoff_table(15), months
    )

    assert round(float(frame["대수"].sum()), 6) == 1.0


def test_the_conversion_ratio_applies_to_the_weighted_count_only() -> None:
    """사용자 예시: 환산비 1.5 호기가 3월에 15일 기여 → `1.5 x 15/31`.

    **대수는 그대로다.** 「몇 대인가」에 환산비를 곱하면 열 대가 열다섯 대가 된다.
    """
    # 3월 W/D 를 달력 3월과 맞추려고 Cut-off 0 을 쓴다(3/1~3/31, 31일).
    # 3/17 부터 가용 → 3/17~3/31 = 15일.
    unit_spans = spans([("EQ-1", "가용", date(2026, 3, 16), date(2026, 12, 31))])

    frame = build_monthly_equipment_availability(
        unit_spans,
        empty_baseline(),
        cutoff_table(0),
        [202603],
        conversion_ratios={"EQ-1": 1.5},
    )

    row = frame.loc[frame["분류"] == "가용"].iloc[0]
    assert round(float(row["대수"]), 4) == round(15 / 31, 4)
    assert round(float(row["환산대수"]), 4) == round(1.5 * 15 / 31, 4)
    assert round(float(row["환산대수"]), 3) == 0.726


def test_a_unit_without_a_declared_ratio_counts_as_one() -> None:
    """환산비를 안 준 호기는 1.0 이다 — 기준 모델과 같다고 본다."""
    unit_spans = spans([("EQ-1", "가용", date(2020, 1, 1), date(2030, 1, 1))])

    frame = build_monthly_equipment_availability(
        unit_spans, empty_baseline(), cutoff_table(0), [202603], conversion_ratios={}
    )

    row = frame.loc[frame["분류"] == "가용"].iloc[0]
    assert float(row["대수"]) == float(row["환산대수"]) == 1.0


def test_the_baseline_has_no_ratio_to_apply() -> None:
    """기존보유는 집계 대수라 환산비를 걸 데가 없다 — 두 값이 같다."""
    baseline = pd.DataFrame({"공정": [PROCESS], "기존보유대수": [10.0]})

    frame = build_monthly_equipment_availability(
        spans([]), baseline, cutoff_table(0), [202603], conversion_ratios={"EQ-1": 1.5}
    )

    row = frame.loc[frame["분류"] == "기존보유"].iloc[0]
    assert float(row["대수"]) == float(row["환산대수"]) == 10.0


def test_the_subtotal_reports_both_axes() -> None:
    unit_spans = spans([("EQ-1", "가용", date(2020, 1, 1), date(2030, 1, 1))])
    baseline = pd.DataFrame({"공정": [PROCESS], "기존보유대수": [4.0]})

    frame = build_monthly_equipment_availability(
        unit_spans, baseline, cutoff_table(0), [202603], conversion_ratios={"EQ-1": 2.0}
    )
    subtotal = available_subtotal(frame)

    # 대수 = 기존보유 4 + 가용 1 = 5, 환산 = 4 + (1 x 2.0) = 6
    assert float(subtotal["Dynamic가용대수"].iloc[0]) == 5.0
    assert float(subtotal["Dynamic가용환산대수"].iloc[0]) == 6.0


# ------------------------------------------------------------------ 호기 목록


def test_the_unit_list_adds_up_to_the_count_table_cell_by_cell() -> None:
    """목록은 대수 표와 같은 기여 줄에서 나온다 — 같은 칸을 더하면 표의 값이다.

    모듈(달 중간에 형제가 반출돼 지분이 0.25 → 1/3), 비가동, 기존보유(분류 둘)를 섞는다.
    """
    from test_equipment_units import _modules, _pm

    from capa_simulation.services.equipment_availability import build_equipment_lifecycle_spans
    from capa_simulation.services.monthly_equipment_availability import (
        build_monthly_equipment_contributions,
    )

    frame = _modules(APW01D={"반출일정": "2026-05-10"})
    unit_spans = build_equipment_lifecycle_spans(
        frame,
        _pm(),
        start_date=date(2025, 12, 1),
        end_date=date(2026, 7, 31),
        with_unit_share=True,
    )
    cutoff = pd.DataFrame({"공정": ["DEMO_Bonder"], "제품구분": ["*"], "Cutoff일수": [0]})
    baseline = pd.DataFrame(
        {"공정": ["DEMO_Bonder"] * 2, "분류": ["A", "B"], "기존보유대수": [1.5, 2.0]}
    )
    ratios = dict(zip(frame["설비명"], frame["환산비"], strict=True))
    months = [202602, 202603, 202605, 202606]

    table = build_monthly_equipment_availability(
        unit_spans, baseline, cutoff, months, conversion_ratios=ratios
    )
    units = build_monthly_equipment_contributions(
        unit_spans, baseline, cutoff, months, conversion_ratios=ratios
    )

    summed = units.groupby(["생산계획년월", "공정", "분류"], as_index=False)[
        ["대수", "환산대수"]
    ].sum()
    joined = table.merge(summed, on=["생산계획년월", "공정", "분류"], suffixes=("", "_목록"))
    assert len(joined) == len(table) == len(summed)
    assert joined["대수"].tolist() == pytest.approx(joined["대수_목록"].tolist())
    assert joined["환산대수"].tolist() == pytest.approx(joined["환산대수_목록"].tolist())

    # 한 달 안에서 구간이 끊긴 모듈도 한 줄이다. 5월의 A 는 0.25 로 9일, 1/3 로 22일 — 형제 D 가
    # 5/10 에 나가는 날부터 남은 셋이 한 대를 채운다(반출일 당일은 D 의 기여가 아니다).
    may_a = units.loc[units["생산계획년월"].eq(202605) & units["설비명"].eq("APW01A")]
    assert len(may_a) == 1
    assert may_a["기여일수"].item() == 31
    assert may_a["대수"].item() == pytest.approx(9 / 31 * 0.25 + 22 / 31 / 3)
    assert set(units["설비키"].dropna()) == {"APW01", "DA01"}
    # 기존보유는 공정 단위 한 줄이고, 어느 분류를 더했는지 적는다.
    held = units.loc[units["분류"].eq("기존보유") & units["생산계획년월"].eq(202603)]
    assert held["기존보유분류"].tolist() == ["A · B"]
    assert held["대수"].tolist() == [3.5]
    assert held["기여일수"].isna().all()
