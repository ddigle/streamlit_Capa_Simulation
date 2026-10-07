# Purpose: 반출·이설 예정 호기를 실행일 전날까지 가용 판정대로 세고 실행일 당일부터 빼는지 검증한다.

"""반출·이설 예정 호기의 대수(2026-10-07·10-08 사용자 결정).

상태 이름은 반출·이설일정이 적히는 순간부터 실행일 전날까지 「반출 예정」·「이설 예정」이다. 그
이름으로 세면 멀쩡히 쓰는 호기가 날짜를 적은 첫날부터 Dynamic 가용대수에서 빠졌다. 세는 자리는
가용 판정(`집계분류`)을 보고, 이름을 보이는 자리는 그대로 이름을 본다.

월별 기여는 상태가 바뀐 다음 날부터지만 **반출·이설일정 당일은 이미 기여하지 않는다**
(2026-10-08 — Guide 「전날까지 가용」에 코드를 맞췄다). Qual 은 그대로 다음 날부터다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_weekly_equipment_availability,
)
from capa_simulation.services.equipment_contract import (
    COUNT_CATEGORY_COLUMN,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    EXIT_FOLLOWS_COLUMN,
    EXIT_STARTS_COLUMN,
    PARENT_EQUIPMENT_COLUMN,
    RELOCATION_DATE_COLUMN,
)
from capa_simulation.services.monthly_equipment_availability import (
    available_subtotal,
    build_monthly_equipment_availability,
    span_date_range,
)

PROCESS = "DEMO_EXIT"
EXIT_DAY = date(2026, 3, 16)
# 반출 컬럼과 이설 컬럼은 같은 규칙이다. 두 번 돌린다.
EXIT_COLUMNS = ("반출일정", RELOCATION_DATE_COLUMN)
PLANNED_NAME = {"반출일정": "반출 예정", RELOCATION_DATE_COLUMN: "이설 예정"}
DONE_NAME = {"반출일정": "반출 완료", RELOCATION_DATE_COLUMN: "이설 완료"}


def _unit(name: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(EQUIPMENT_COLUMNS)
    row.update(
        {
            "설비명": name,
            "공정소분류": PROCESS,
            "공정대분류": "B/N",
            "사용기준": "HBM",
            "반입일정": "2025-10-01",
            "Qual일정": "2025-10-20",
            "확정상태": "완료",
            "보관유무": "N",
            "기존설비여부": "N",
            "레이아웃표시": "N",
        }
    )
    row.update(overrides)
    return row


def _master(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(EQUIPMENT_COLUMNS))


def _no_downtime() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DOWNTIME_COLUMNS))


def _downtime(unit: str, start: str, end: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"설비명": unit, "비가동유형": "고장", "시작일": start, "종료일": end}],
        columns=list(DOWNTIME_COLUMNS),
    )


def _no_baseline() -> pd.DataFrame:
    return pd.DataFrame(columns=["공정", "분류", "기존보유대수", "비고"])


def _cutoff_zero() -> pd.DataFrame:
    return pd.DataFrame({"공정": [PROCESS], "제품구분": ["*"], "Cutoff일수": [0]})


def _monthly(equipment: pd.DataFrame, downtime: pd.DataFrame, months: list[int]) -> pd.DataFrame:
    spans = build_equipment_lifecycle_spans(
        equipment,
        downtime,
        start_date=date(2025, 12, 1),
        end_date=date(2026, 6, 30),
        with_unit_share=True,
    )
    return build_monthly_equipment_availability(spans, _no_baseline(), _cutoff_zero(), months)


def _cell(monthly: pd.DataFrame, month: int, category: str) -> float:
    rows = monthly.loc[monthly["생산계획년월"].eq(month) & monthly["분류"].eq(category), "대수"]
    return float(rows.sum())


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_an_available_unit_keeps_its_name_but_counts_as_available(column: str) -> None:
    """이름은 「반출 예정」 그대로이고(상태 분포·Space 가 보는 값), 세는 분류는 가용이다."""
    status = build_equipment_status_as_of(
        _master(_unit("EQ-1", **{column: EXIT_DAY})), _no_downtime(), as_of=date(2026, 3, 1)
    )

    assert status["상태"].tolist() == [PLANNED_NAME[column]]
    assert status["가용여부"].tolist() == [True]
    assert status[COUNT_CATEGORY_COLUMN].tolist() == ["가용"]


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_an_available_unit_counts_until_the_day_before_the_exit(column: str) -> None:
    """3/16 반출이면 3/15 까지 가용이다. 실행일은 그날부터 빠지므로(Cut-off 0 의 3월 구간
    `(2/28, 3/31]`) 3월에 15일 가용·16일 완료이고, 2월은 통째로 가용이다.
    """
    monthly = _monthly(
        _master(_unit("EQ-1", **{column: EXIT_DAY})), _no_downtime(), [202602, 202603]
    )

    assert _cell(monthly, 202602, "가용") == pytest.approx(1.0)
    assert _cell(monthly, 202603, "가용") == pytest.approx(15 / 31)
    assert _cell(monthly, 202603, DONE_NAME[column]) == pytest.approx(16 / 31)
    # 예정 이름의 행은 생기지 않는다 — 가용이 아닌 날이 없다.
    assert _cell(monthly, 202602, PLANNED_NAME[column]) == 0.0
    subtotal = available_subtotal(monthly).set_index("생산계획년월")["Dynamic가용대수"]
    assert subtotal.to_dict() == pytest.approx({202602: 1.0, 202603: 15 / 31})


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_the_counting_spans_break_where_the_unit_becomes_available(column: str) -> None:
    """이름은 셋업 중·Qual 후가 모두 예정 이름 한 구간이지만, 세는 구간은 Qual 날에 끊긴다.

    Gantt 용 구간(지분을 끄는 기본값)은 이름으로만 끊어 예전 그대로다.
    """
    equipment = _master(
        _unit("EQ-1", **{"반입일정": "2026-01-05", "Qual일정": "2026-02-10", column: EXIT_DAY})
    )
    start, end = date(2026, 1, 1), date(2026, 4, 30)

    counting = build_equipment_lifecycle_spans(
        equipment, _no_downtime(), start_date=start, end_date=end, with_unit_share=True
    )
    gantt = build_equipment_lifecycle_spans(
        equipment, _no_downtime(), start_date=start, end_date=end
    )

    planned, done = PLANNED_NAME[column], DONE_NAME[column]
    assert counting[["상태", COUNT_CATEGORY_COLUMN, "시작일", "종료일"]].values.tolist() == [
        [planned, planned, date(2026, 1, 1), date(2026, 2, 9)],
        [planned, "가용", date(2026, 2, 10), date(2026, 3, 15)],
        [done, done, date(2026, 3, 16), date(2026, 4, 30)],
    ]
    # 날짜는 상태가 바뀐 날 그대로이고, 반출·이설일에 닿는 경계만 표시가 선다(월별이 밀지 않는
    # 경계다).
    assert counting[[EXIT_STARTS_COLUMN, EXIT_FOLLOWS_COLUMN]].values.tolist() == [
        [False, False],
        [False, True],
        [True, False],
    ]
    assert gantt[["상태", "시작일", "종료일"]].values.tolist() == [
        [planned, date(2026, 1, 1), date(2026, 3, 15)],
        [done, date(2026, 3, 16), date(2026, 4, 30)],
    ]
    assert EXIT_STARTS_COLUMN not in gantt.columns


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_a_unit_still_in_setup_does_not_count_before_the_exit(column: str) -> None:
    """Qual 이 없는(셋업 중) 호기는 반출·이설 예정이어도 가용이 아니다 — 예정 행에 남는다."""
    equipment = _master(
        _unit(
            "EQ-1",
            **{"반입일정": "2026-01-05", "Qual일정": None, "확정상태": None, column: EXIT_DAY},
        )
    )

    monthly = _monthly(equipment, _no_downtime(), [202602])

    assert _cell(monthly, 202602, "가용") == 0.0
    assert _cell(monthly, 202602, PLANNED_NAME[column]) == pytest.approx(1.0)
    assert available_subtotal(monthly).empty or float(
        available_subtotal(monthly)["Dynamic가용대수"].sum()
    ) == pytest.approx(0.0)


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_a_unit_down_before_the_exit_does_not_count_while_down(column: str) -> None:
    """반출 예정 호기라도 비가동인 날은 운영 비가동이다(가용 판정이 거짓이다)."""
    equipment = _master(_unit("EQ-1", **{column: EXIT_DAY}))

    monthly = _monthly(equipment, _downtime("EQ-1", "2026-02-01", "2026-02-14"), [202602])

    # 비가동 상태는 2/1~2/14, 기여일로는 2/2~2/15 = 14일. 나머지 14일은 가용이다.
    assert _cell(monthly, 202602, "운영 비가동") == pytest.approx(14 / 28)
    assert _cell(monthly, 202602, "가용") == pytest.approx(14 / 28)


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_the_weekly_count_follows_availability_not_the_name(column: str) -> None:
    """주차별 가용호기대수 = 가용대수 − 기존보유대수. 예정 대수 칸은 가용이 아닌 예정 호기다."""
    equipment = _master(
        _unit("EQ-1", **{column: EXIT_DAY}),
        _unit(
            "EQ-2",
            **{"반입일정": "2026-01-05", "Qual일정": None, "확정상태": None, column: EXIT_DAY},
        ),
    )

    weekly = build_weekly_equipment_availability(
        _no_baseline(),
        equipment,
        _no_downtime(),
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 22),
    ).set_index("Weeknum")

    planned_column = "반출예정대수" if column == "반출일정" else "이설예정대수"
    done_column = "반출완료대수" if column == "반출일정" else "이설완료대수"
    # 3/8(일)·3/15(일): EQ-1 가용, EQ-2 셋업 중이라 예정 칸.
    for week in ("26-W10", "26-W11"):
        assert weekly.at[week, "가용대수"] == 1.0
        assert weekly.at[week, "가용호기대수"] == 1.0
        assert weekly.at[week, planned_column] == 1.0
        assert weekly.at[week, "비가동대수"] == 1.0
    # 3/22(일): 둘 다 3/16 에 나갔다.
    assert weekly.at["26-W12", "가용대수"] == 0.0
    assert weekly.at["26-W12", done_column] == 2.0


# ------------------------------------------------------------------ 실행일 당일(2026-10-08)


def _cutoff(days: int) -> pd.DataFrame:
    return pd.DataFrame({"공정": [PROCESS], "제품구분": ["*"], "Cutoff일수": [days]})


def _counted(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    months: list[int],
    cutoff: pd.DataFrame,
    ratios: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Static/Dynamic 과 같은 길 — `span_date_range` 로 넓힌 세는 구간을 월별로 안분한다."""
    span = span_date_range(months, cutoff)
    assert span is not None
    spans = build_equipment_lifecycle_spans(
        equipment, downtime, start_date=span[0], end_date=span[1], with_unit_share=True
    )
    return build_monthly_equipment_availability(
        spans, _no_baseline(), cutoff, months, conversion_ratios=ratios
    )


def _month_total(monthly: pd.DataFrame, month: int) -> float:
    return float(monthly.loc[monthly["생산계획년월"].eq(month), "대수"].sum())


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_the_exit_day_itself_no_longer_counts(column: str) -> None:
    """기존설비가 2027-03-31 에 나간다. Cut-off 34 의 2027-05 구간 `(3/27, 4/27]`(31일)에서 가용은
    3/28~3/30 의 3일이고, 3/31 부터 28일이 완료다 — 예전엔 반출일까지 4일을 셌다(r5 샘플
    SMP-DA-01 과 같은 날짜). 아홉 상태의 합은 그대로 한 대다 — 가용 하루가 완료로 옮겨 갔을 뿐이다.
    """
    existing = {
        "기존설비여부": "Y",
        "반입일정": None,
        "Qual일정": None,
        "확정상태": None,
        column: "2027-03-31",
    }
    monthly = _counted(
        _master(_unit("EQ-1", **existing)), _no_downtime(), [202704, 202705], _cutoff(34)
    )

    assert _cell(monthly, 202704, "가용") == pytest.approx(1.0)
    assert _cell(monthly, 202705, "가용") == pytest.approx(3 / 31)
    assert _cell(monthly, 202705, DONE_NAME[column]) == pytest.approx(28 / 31)
    assert _month_total(monthly, 202705) == pytest.approx(1.0)


def test_qual_still_counts_from_the_next_day() -> None:
    """바꾸지 않은 규칙(2026-10-07 B-7): Qual 3/5 이면 3/6 부터 가용이다 — Cut-off 0 의 3월에
    26일."""
    equipment = _master(_unit("EQ-1", **{"반입일정": "2026-02-01", "Qual일정": "2026-03-05"}))

    monthly = _counted(equipment, _no_downtime(), [202603], _cutoff(0))

    assert _cell(monthly, 202603, "셋업 진행중") == pytest.approx(5 / 31)
    assert _cell(monthly, 202603, "가용") == pytest.approx(26 / 31)


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_qual_and_exit_in_the_same_month_keep_their_own_rules(column: str) -> None:
    """Qual 3/5 → 3/6 부터, 3/20 반출 → 3/19 까지. Cut-off 0 의 3월은 셋업(이름은 예정) 5일·
    가용 14일·완료 12일이고 합이 31일이다."""
    equipment = _master(
        _unit("EQ-1", **{"반입일정": "2026-02-01", "Qual일정": "2026-03-05", column: "2026-03-20"})
    )

    monthly = _counted(equipment, _no_downtime(), [202603], _cutoff(0))

    assert _cell(monthly, 202603, PLANNED_NAME[column]) == pytest.approx(5 / 31)
    assert _cell(monthly, 202603, "가용") == pytest.approx(14 / 31)
    assert _cell(monthly, 202603, DONE_NAME[column]) == pytest.approx(12 / 31)
    assert _month_total(monthly, 202603) == pytest.approx(1.0)


@pytest.mark.parametrize("column", EXIT_COLUMNS)
@pytest.mark.parametrize(
    ("exit_day", "march_available"),
    [
        # 3월 구간의 앞 경계(`span_date_range` 의 시작) — 그날 이미 나가 3월에 하루도 없다.
        ("2026-02-28", 0.0),
        # 3월 구간의 첫날 — 앞 경계에서 시작한 가용 구간이 그 경계에서 끝난다.
        ("2026-03-01", 0.0),
        # 3월 구간의 끝날 — 3월은 30일이다.
        ("2026-03-31", 30 / 31),
        # 4월 구간의 첫날 — 3월은 통째로 가용이다.
        ("2026-04-01", 1.0),
    ],
)
def test_an_exit_on_a_window_edge(column: str, exit_day: str, march_available: float) -> None:
    """W/D 구간 경계에 걸린 반출·이설일(Cut-off 0 — 3월 `(2/28, 3/31]`, 4월 `(3/31, 4/30]`).
    어느 경우든 4월은 첫날부터 완료다."""
    monthly = _counted(
        _master(_unit("EQ-1", **{column: exit_day})), _no_downtime(), [202603, 202604], _cutoff(0)
    )

    assert _cell(monthly, 202603, "가용") == pytest.approx(march_available)
    assert _cell(monthly, 202603, DONE_NAME[column]) == pytest.approx(1 - march_available)
    assert _cell(monthly, 202604, "가용") == 0.0
    assert _cell(monthly, 202604, DONE_NAME[column]) == pytest.approx(1.0)
    assert _month_total(monthly, 202603) == pytest.approx(1.0)


@pytest.mark.parametrize("column", EXIT_COLUMNS)
def test_downtime_running_into_the_exit_moves_only_its_start(column: str) -> None:
    """비가동 3/10~3/25 중 3/20 에 나간다. 비가동 시작은 지금처럼 다음 날(3/11)부터, 반출·이설은
    그날(3/20)부터다 — Cut-off 0 의 3월은 가용 10일·비가동 9일·완료 12일."""
    equipment = _master(_unit("EQ-1", **{column: "2026-03-20"}))

    monthly = _counted(
        equipment, _downtime("EQ-1", "2026-03-10", "2026-03-25"), [202603], _cutoff(0)
    )

    assert _cell(monthly, 202603, "가용") == pytest.approx(10 / 31)
    assert _cell(monthly, 202603, "운영 비가동") == pytest.approx(9 / 31)
    assert _cell(monthly, 202603, DONE_NAME[column]) == pytest.approx(12 / 31)


def test_a_leaving_module_hands_its_share_to_its_siblings_on_the_same_day() -> None:
    """모듈 넷(0.25씩) 가운데 D 가 5/10 에 나간다. 그날부터 D 는 빠지고 남은 셋이 1/3 씩 한 대를
    채운다. 나간 모듈만 당일로 두고 형제의 지분 경계를 다음 날로 밀면 5/10 하루가 0.75대가 되므로
    경계 표시는 설비키 단위다. 그래서 5월(Cut-off 0) 대수는 정확히 1대이고, 지분을 보지 않는
    환산대수에는 D 의 9일(5/1~5/9)만 남는다(예전엔 반출일까지 10일).
    """
    rows = [_unit(f"APW01{suffix}", **{PARENT_EQUIPMENT_COLUMN: "APW01"}) for suffix in "ABCD"]
    rows[3]["반출일정"] = "2026-05-10"
    equipment = _master(*rows)
    ratios = {str(row["설비명"]): 0.25 for row in rows}

    monthly = _counted(equipment, _no_downtime(), [202605], _cutoff(0), ratios)
    subtotal = available_subtotal(monthly).iloc[0]

    assert subtotal["Dynamic가용대수"] == pytest.approx(1.0)
    assert subtotal["Dynamic가용환산대수"] == pytest.approx(0.75 + 0.25 * 9 / 31)
    spans = build_equipment_lifecycle_spans(
        equipment,
        _no_downtime(),
        start_date=date(2026, 4, 30),
        end_date=date(2026, 5, 31),
        with_unit_share=True,
    )
    starts = spans.loc[spans[EXIT_STARTS_COLUMN], ["설비명", "시작일"]].values.tolist()
    assert sorted(starts) == [[f"APW01{suffix}", date(2026, 5, 10)] for suffix in "ABCD"]
