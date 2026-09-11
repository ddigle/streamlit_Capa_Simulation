# Purpose: standard target capacity 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.standard_target_capacity import (
    PKG_EQUIVALENT_COLUMN,
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
    weekly_standard_target_to_wide,
)
from capa_simulation.services.standard_target_logic import (
    build_standard_target_logic_analysis,
)
from capa_simulation.services.weekly_availability_input import (
    build_weekly_availability_template,
    parse_weekly_availability_clipboard,
    prepare_weekly_availability,
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


def test_iso_week_calendar_gives_the_boundary_week_to_the_month_with_more_days() -> None:
    """8월 31일 하루 대 9월 6일이므로 9월이 가져간다(2026-09-05 확정 규칙).

    예전에는 월요일이 속한 8월로 보냈다. 규칙 자체의 검증은
    `tests/test_iso_week_calendar.py` 가 전담한다.
    """
    result = build_iso_week_calendar(date(2026, 8, 31), date(2026, 9, 6))

    assert result.to_dict("records") == [
        {
            "Weeknum": "26-W36",
            "주차시작일": date(2026, 8, 31),
            "주차종료일": date(2026, 9, 6),
            "생산계획년월": 202609,
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


def test_weekly_availability_clipboard_is_validated() -> None:
    result = parse_weekly_availability_clipboard("공정\tWeeknum\t가용대수\nProcess-A\t26-W32\t2.5")

    assert result.to_dict("records") == [
        {"공정": "Process-A", "Weeknum": "26-W32", "가용대수": 2.5}
    ]


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


def test_pkg_equivalent_uses_unique_pkg_plan_over_original_demand_load() -> None:
    required_equipment = _required_equipment()
    weekly_target = build_weekly_standard_target_capacity(
        required_equipment=required_equipment,
        run_day=pd.DataFrame({"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [10.0]}),
        weekly_availability=pd.DataFrame(
            {"공정": ["Process-A"], "Weeknum": ["26-W32"], "가용대수": [2.0]}
        ),
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 9),
        detail_level="공정",
    )
    plan = pd.DataFrame(
        {
            "생산계획년월": [202608, 202608],
            "양산구분": ["양산", "양산"],
            "제품정보": ["Product-A", "Product-A"],
            "Stack": ["8H", "8H"],
            "Capa Code": ["C1", "C2"],
            "Customer": ["Customer-A", "Customer-B"],
            "CS": ["MP", "ER"],
            "생산수량": [30.0, 20.0],
        }
    )

    result = add_pkg_equivalent_standard_target(
        weekly_target=weekly_target,
        required_equipment=required_equipment,
        plan=plan,
        detail_level="공정",
    )

    assert result.loc[0, "원수요_부하량"] == pytest.approx(100.0)
    assert result.loc[0, "일 표준 가능량"] == pytest.approx(10.0)
    assert result.loc[0, PKG_EQUIVALENT_COLUMN] == pytest.approx(5.0)


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


def test_logic_analysis_explains_one_process_week_with_product_wf_mix() -> None:
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
                "부하량": 300.0,
                "소요대수": 6.0,
            },
        ]
    )

    target, contributions = build_standard_target_logic_analysis(
        required_equipment=required_equipment,
        run_day=pd.DataFrame({"생산계획년월": [202608], "공정": ["Process-A"], "RUN_DAY": [20.0]}),
        weekly_availability=pd.DataFrame(
            {"공정": ["Process-A"], "Weeknum": ["26-W32"], "가용대수": [4.0]}
        ),
        weeknum="26-W32",
        process="Process-A",
        demand_basis="wafer",
    )

    assert len(target) == 1
    assert target.loc[0, "원수요_부하량"] == pytest.approx(400.0)
    assert target.loc[0, "STEP_소요대수"] == pytest.approx(7.0)
    assert target.loc[0, "공정 유효 Capa"] == pytest.approx(400.0 / 7.0)
    assert target.loc[0, "대당 일 Capa"] == pytest.approx(20.0 / 7.0)
    assert target.loc[0, "일 표준 가능량"] == pytest.approx(80.0 / 7.0)
    assert contributions["부하량 비중"].tolist() == pytest.approx([0.25, 0.75])
    assert contributions["소요대수 비중"].tolist() == pytest.approx([1.0 / 7.0, 6.0 / 7.0])
    assert contributions["분류 유효 Capa"].tolist() == pytest.approx([100.0, 50.0])
    assert contributions["Capa 역수 기여"].sum() == pytest.approx(7.0 / 400.0)


def test_pre_bd_standard_target_excludes_dummy_from_product_mix() -> None:
    required_equipment = pd.DataFrame(
        [
            {
                "생산계획년월": 202608,
                "공정": "Pre B/D",
                "소요기준": "CHIP",
                "양산구분": "양산",
                "제품정보": "Product-A",
                "Stack": "12H",
                "Capa Code": "C1",
                "Customer": "Customer-A",
                "CS": "MP",
                "WF 구분": "Core",
                "부하량": 100.0,
                "소요대수": 1.0,
            },
            {
                "생산계획년월": 202608,
                "공정": "Pre B/D",
                "소요기준": "CHIP",
                "양산구분": "양산",
                "제품정보": "Product-A",
                "Stack": "12H",
                "Capa Code": "C1",
                "Customer": "Customer-A",
                "CS": "MP",
                "WF 구분": " dummy ",
                "부하량": 900.0,
                "소요대수": 1.0,
            },
        ]
    )
    run_day = pd.DataFrame({"생산계획년월": [202608], "공정": ["Pre B/D"], "RUN_DAY": [10.0]})
    availability = pd.DataFrame({"공정": ["Pre B/D"], "Weeknum": ["26-W32"], "가용대수": [2.0]})

    result = build_weekly_standard_target_capacity(
        required_equipment=required_equipment,
        run_day=run_day,
        weekly_availability=availability,
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 9),
        detail_level="공정",
    )
    target, contributions = build_standard_target_logic_analysis(
        required_equipment=required_equipment,
        run_day=run_day,
        weekly_availability=availability,
        weeknum="26-W32",
        process="Pre B/D",
        demand_basis="CHIP",
    )

    assert result.loc[0, "원수요_부하량"] == pytest.approx(100.0)
    assert result.loc[0, "STEP_소요대수"] == pytest.approx(1.0)
    assert result.loc[0, "일 표준 가능량"] == pytest.approx(20.0)
    assert target.loc[0, "일 표준 가능량"] == pytest.approx(20.0)
    assert contributions["WF 구분"].tolist() == ["Core"]


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


def test_availability_rejects_a_process_outside_the_known_list() -> None:
    """화면이 표시명을 그리므로 그 이름을 양식에 적어 붙여넣는 실수가 여기서 막혀야 한다."""
    source = pd.DataFrame(
        {
            "공정": ["Process-A", "절단"],
            "Weeknum": ["26-W32", "26-W32"],
            "가용대수": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="보유하지 않은 공정"):
        prepare_weekly_availability(source, known_processes=["Process-A", "Process-B"])


def test_availability_without_a_known_list_accepts_any_process() -> None:
    """저장된 값을 되읽는 경로는 목록을 넘기지 않는다. 막으면 화면이 열리지 않는다."""
    source = pd.DataFrame({"공정": ["절단"], "Weeknum": ["26-W32"], "가용대수": [1.0]})

    assert prepare_weekly_availability(source)["공정"].tolist() == ["절단"]


def test_availability_clipboard_passes_the_known_process_list_through() -> None:
    with pytest.raises(ValueError, match="보유하지 않은 공정"):
        parse_weekly_availability_clipboard(
            "공정\tWeeknum\t가용대수\n절단\t26-W32\t2.5",
            known_processes=["Process-A"],
        )
