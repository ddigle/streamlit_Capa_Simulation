# Purpose: standard target capacity 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date

import pandas as pd
import pytest

from capa_simulation.services.iso_week_calendar import build_iso_week_calendar
from capa_simulation.services.standard_target_capacity import (
    PKG_EQUIVALENT_COLUMN,
    add_pkg_equivalent_standard_target,
    build_weekly_standard_target_capacity,
    prepare_standard_target_required_equipment,
    split_standard_target_required_equipment,
    standard_target_exception_row_count,
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
    """저장값이 없으면 가용대수는 0.0 이 아니라 빈칸(NaN)이다.

    예전에는 0.0 을 고정했다. 그 양식을 일부만 고쳐 되붙이면 다른 공정·주차가 0 대로 덮였다
    (2026-09-29 버그 보고) — 붙여넣기가 빈칸을 「그대로 둠」으로 읽도록 바뀌며 양식도 빈칸이다.
    """
    result = build_weekly_availability_template(
        ["Process-B", "Process-A", "Process-B"],
        date(2026, 8, 3),
        date(2026, 8, 9),
    )

    assert result["공정"].tolist() == ["Process-B", "Process-A"]
    assert result["Weeknum"].tolist() == ["26-W32", "26-W32"]
    assert result["가용대수"].isna().all()


def test_availability_template_carries_saved_counts_and_leaves_the_rest_blank() -> None:
    """양식은 저장값을 채워 내려 준다. 저장값이 없는 칸만 빈칸이다(CSV 에서도 빈 칸)."""
    saved = pd.DataFrame(
        {
            "공정": pd.Series(["Process-A", "Process-A", "Process-Z"], dtype="string"),
            "Weeknum": pd.Series(["26-W32", "26-W33", "26-W32"], dtype="string"),
            "가용대수": [2.0, 0.0, 9.0],
        }
    )

    result = build_weekly_availability_template(
        ["Process-A", "Process-B"],
        date(2026, 8, 3),
        date(2026, 8, 16),
        saved=saved,
    )

    counts = {
        (process, weeknum): count
        for process, weeknum, count in result[["공정", "Weeknum", "가용대수"]].itertuples(
            index=False, name=None
        )
    }
    assert counts[("Process-A", "26-W32")] == 2.0
    # 저장된 0 은 「0 대」라 빈칸이 아니라 0 으로 내려와야 한다.
    assert counts[("Process-A", "26-W33")] == 0.0
    assert pd.isna(counts[("Process-B", "26-W32")])
    assert pd.isna(counts[("Process-B", "26-W33")])
    # 양식 공정에 없는 저장값(Process-Z)은 행을 만들지 않는다.
    assert set(result["공정"]) == {"Process-A", "Process-B"}
    csv_lines = result.to_csv(index=False).splitlines()
    assert "Process-B,26-W32,2026-08-03,2026-08-09," in csv_lines


def test_availability_template_pasted_back_as_is_changes_nothing() -> None:
    """저장값이 채워진 양식을 그대로 되붙이면 저장값 행만 다시 들어가고 빈칸은 떨어진다."""
    saved = pd.DataFrame({"공정": ["Process-A"], "Weeknum": ["26-W32"], "가용대수": [2.0]})
    template = build_weekly_availability_template(
        ["Process-A", "Process-B"], date(2026, 8, 3), date(2026, 8, 9), saved=saved
    )

    result = parse_weekly_availability_clipboard(
        template.to_csv(sep="\t", index=False),
        known_processes=["Process-A", "Process-B"],
    )

    assert result.to_dict("records") == [
        {"공정": "Process-A", "Weeknum": "26-W32", "가용대수": 2.0}
    ]


def test_weekly_availability_clipboard_is_validated() -> None:
    result = parse_weekly_availability_clipboard("공정\tWeeknum\t가용대수\nProcess-A\t26-W32\t2.5")

    assert result.to_dict("records") == [
        {"공정": "Process-A", "Weeknum": "26-W32", "가용대수": 2.5}
    ]


def test_availability_clipboard_drops_blank_count_rows() -> None:
    """가용대수 빈칸은 「그대로 둠」이다 — 저장이 upsert 라 떨어뜨린 키는 저장값이 남는다.

    예전에는 빈칸을 「숫자가 아닌 값 또는 누락값」으로 거부해, 모르는 칸을 적을 방법이 0
    뿐이었다(2026-09-29 버그 보고). 공백만 든 칸도 빈칸이다. 적은 0 은 0 대로 남는다.
    """
    result = parse_weekly_availability_clipboard(
        "공정\tWeeknum\t가용대수\n"
        "Process-A\t26-W32\t\n"
        "Process-A\t26-W33\t   \n"
        "Process-B\t26-W32\t0\n"
        "Process-B\t26-W33\t3\n",
        known_processes=["Process-A", "Process-B"],
    )

    assert result.to_dict("records") == [
        {"공정": "Process-B", "Weeknum": "26-W32", "가용대수": 0.0},
        {"공정": "Process-B", "Weeknum": "26-W33", "가용대수": 3.0},
    ]


def test_availability_clipboard_rejects_unreadable_counts() -> None:
    """빈칸과 달리 못 읽는 글자는 막는다. 적었다고 믿는 값이 조용히 버려지면 안 된다."""
    with pytest.raises(ValueError, match=r"숫자가 아닙니다: \['Process-A 26-W33'\]"):
        parse_weekly_availability_clipboard(
            "공정\tWeeknum\t가용대수\nProcess-A\t26-W32\t\nProcess-A\t26-W33\tabc\n"
        )


def test_availability_clipboard_with_only_blank_counts_has_nothing_to_apply() -> None:
    """빈 양식을 그대로 붙여넣으면 아무것도 저장하지 않고 멈춘다."""
    template = build_weekly_availability_template(
        ["Process-A", "Process-B"], date(2026, 8, 3), date(2026, 8, 16)
    )

    with pytest.raises(ValueError, match="적용할 값이 없습니다"):
        parse_weekly_availability_clipboard(
            template.to_csv(sep="\t", index=False),
            known_processes=["Process-A", "Process-B"],
        )


def test_availability_outside_the_paste_path_still_rejects_blank_counts() -> None:
    """빈칸 드롭은 붙여넣기만의 규칙이다. 되읽기·계산 경로는 빈칸을 예전처럼 막는다."""
    source = pd.DataFrame(
        {
            "공정": ["Process-A", "Process-A"],
            "Weeknum": ["26-W32", "26-W33"],
            "가용대수": [1.0, None],
        }
    )

    with pytest.raises(ValueError, match="누락값"):
        prepare_weekly_availability(source)


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


def test_split_standard_target_demand_matches_the_two_single_purpose_helpers() -> None:
    """남는 표와 제외 건수를 한 번에 내는 함수가 두 래퍼와 같은 값을 낸다.

    ER 행은 제외 건수에 세지 않고(공정 예외가 아니다), `Pre B/D` 의 DUMMY 만 센다.
    """
    base = {
        "생산계획년월": 202608,
        "소요기준": "CHIP",
        "제품정보": "Product-A",
        "Stack": "12H",
        "Capa Code": "C1",
        "Customer": "Customer-A",
        "CS": "MP",
        "부하량": 100.0,
        "소요대수": 1.0,
    }
    required_equipment = pd.DataFrame(
        [
            {**base, "공정": "Pre B/D", "양산구분": "양산", "WF 구분": "Core"},
            {**base, "공정": "Pre B/D", "양산구분": "양산", "WF 구분": " dummy "},
            {**base, "공정": "Pre B/D", "양산구분": " er ", "WF 구분": "DUMMY"},
            {**base, "공정": "Process-A", "양산구분": "양산", "WF 구분": "DUMMY"},
            {**base, "공정": "Process-A", "양산구분": "ER", "WF 구분": "Core"},
        ]
    )

    prepared, exception_rows = split_standard_target_required_equipment(required_equipment)

    assert exception_rows == 1
    assert exception_rows == standard_target_exception_row_count(required_equipment)
    pd.testing.assert_frame_equal(
        prepared, prepare_standard_target_required_equipment(required_equipment)
    )
    assert list(zip(prepared["공정"], prepared["WF 구분"], strict=True)) == [
        ("Pre B/D", "Core"),
        ("Process-A", "DUMMY"),
    ]
    assert prepared.index.tolist() == [0, 1]


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


def test_pkg_equivalent_sums_plan_rows_that_differ_only_by_pack_code() -> None:
    """Pack Code 별로 갈린 계획 줄은 PKG 환산에서 7키 합계로 들어가야 한다.

    승격 전에는 `_prepare_pkg_plan_for_equivalent` 가 7키 중복을 예외로 막아, Pack Code 가
    둘인 리비전에서 PKG 환산 토글이 통째로 실패했다.
    """
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
            "생산계획년월": [202608, 202608, 202608],
            "양산구분": ["양산", "양산", "양산"],
            "제품정보": ["Product-A", "Product-A", "Product-A"],
            "Stack": ["8H", "8H", "8H"],
            "Capa Code": ["C1", "C1", "C2"],
            "Customer": ["Customer-A", "Customer-A", "Customer-B"],
            "CS": ["MP", "MP", "ER"],
            "Pack Code": ["PK-1", "PK-2", "PK-1"],
            "생산수량": [20.0, 10.0, 20.0],
        }
    )

    result = add_pkg_equivalent_standard_target(
        weekly_target=weekly_target,
        required_equipment=required_equipment,
        plan=plan,
        detail_level="공정",
    )

    # 20 + 10 + 20 = 50. 7키가 같은 두 줄이 접히지 않고 더해진다.
    assert result.loc[0, PKG_EQUIVALENT_COLUMN] == pytest.approx(5.0)
