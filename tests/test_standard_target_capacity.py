from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.standard_target_capacity import (
    build_iso_week_calendar,
    build_weekly_availability_template,
    build_weekly_standard_target_capacity,
    prepare_weekly_availability,
    weekly_standard_target_to_wide,
)


def _required_equipment() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for step_seq in ("S1", "S2"):
        for capa_code, customer, cs, load in (
            ("C1", "Customer-A", "MP", 60.0),
            ("C2", "Customer-B", "ER", 40.0),
        ):
            rows.append(
                {
                    "생산계획년월": 202608,
                    "공정": "Process-A",
                    "소요기준": "WF",
                    "양산구분": "양산",
                    "제품정보": "Product-A",
                    "Stack": "8H",
                    "Capa Code": capa_code,
                    "Customer": customer,
                    "CS": cs,
                    "WF 구분": "Core",
                    "부하량": load,
                    "소요대수": load / 100.0,
                    "STEP_SEQ": step_seq,
                }
            )
    return pd.DataFrame(rows)


def test_iso_week_calendar_uses_monday_month_at_month_boundary() -> None:
    result = build_iso_week_calendar(date(2026, 8, 31), date(2026, 9, 6))

    assert result.to_dict("records") == [
        {
            "Weeknum": "26-W36",
            "주차시작일": date(2026, 8, 31),
            "주차종료일": date(2026, 9, 6),
            "생산계획년월": 202608,
        }
    ]


def test_availability_template_preserves_process_order() -> None:
    result = build_weekly_availability_template(
        ["Process-B", "Process-A", "Process-B"],
        date(2026, 8, 3),
        date(2026, 8, 9),
    )

    assert result["공정"].tolist() == ["Process-B", "Process-A"]
    assert result["Weeknum"].tolist() == ["26-W32", "26-W32"]
    assert result["가용대수"].tolist() == [0.0, 0.0]


def test_weekly_target_uses_daily_effective_capacity_and_availability() -> None:
    availability = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-A"],
            "Weeknum": ["26-W32", "26-W33"],
            "가용대수": [2.0, 3.0],
        }
    )
    result = build_weekly_standard_target_capacity(
        required_equipment=_required_equipment(),
        run_day=pd.DataFrame({"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [31.0]}),
        weekly_availability=availability,
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 16),
        detail_level="제품정보",
    )

    assert result["공정 유효 Capa"].tolist() == pytest.approx([50.0, 50.0])
    assert result["대당 일 Capa"].tolist() == pytest.approx([50.0 / 31.0] * 2)
    assert result["일 표준 가능량"].tolist() == pytest.approx([100.0 / 31.0, 150.0 / 31.0])

    wide = weekly_standard_target_to_wide(
        result,
        ["공정", "소요기준", "양산구분", "제품정보"],
        value_column="가용대수",
    )
    assert wide.columns.tolist() == [
        "공정",
        "소요기준",
        "양산구분",
        "제품정보",
        "26-W32",
        "26-W33",
    ]
    assert wide.loc[0, "26-W32"] == pytest.approx(2.0)
    assert wide.loc[0, "26-W33"] == pytest.approx(3.0)


def test_process_summary_uses_product_mix_and_always_excludes_er() -> None:
    required_equipment = pd.DataFrame(
        [
            {
                "생산계획년월": 202608,
                "공정": "Process-A",
                "소요기준": "WF",
                "양산구분": "양산",
                "제품정보": "Product-A",
                "Stack": "8H",
                "Capa Code": "C1",
                "Customer": "Customer-A",
                "CS": "MP",
                "WF 구분": "Core",
                "부하량": 100.0,
                "소요대수": 1.0,
            },
            {
                "생산계획년월": 202608,
                "공정": "Process-A",
                "소요기준": "WF",
                "양산구분": "양산",
                "제품정보": "Product-B",
                "Stack": "12H",
                "Capa Code": "C2",
                "Customer": "Customer-B",
                "CS": "MP",
                "WF 구분": "Top",
                "부하량": 100.0,
                "소요대수": 2.0,
            },
            {
                "생산계획년월": 202608,
                "공정": "Process-A",
                "소요기준": "WF",
                "양산구분": " er ",
                "제품정보": "Product-ER",
                "Stack": "4H",
                "Capa Code": "C3",
                "Customer": "Customer-C",
                "CS": "ER",
                "WF 구분": "Buffer",
                "부하량": 9_000.0,
                "소요대수": 1.0,
            },
        ]
    )
    result = build_weekly_standard_target_capacity(
        required_equipment=required_equipment,
        run_day=pd.DataFrame({"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [10.0]}),
        weekly_availability=pd.DataFrame(
            {"공정": ["Process-A"], "Weeknum": ["26-W32"], "가용대수": [3.0]}
        ),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 9),
        detail_level="공정",
    )

    assert len(result) == 1
    assert result.loc[0, "원수요_부하량"] == pytest.approx(200.0)
    assert result.loc[0, "STEP_소요대수"] == pytest.approx(3.0)
    assert result.loc[0, "공정 유효 Capa"] == pytest.approx(200.0 / 3.0)
    assert result.loc[0, "일 표준 가능량"] == pytest.approx(20.0)


def test_availability_rejects_duplicate_process_week() -> None:
    source = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-A"],
            "Weeknum": ["26-W32", "26-W32"],
            "가용대수": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="중복"):
        prepare_weekly_availability(source)
