# Purpose: 반출·이설일정이 적힌 호기를 실행일 전까지 가용 판정대로 세는지 검증한다.

"""반출·이설 예정 호기의 대수(2026-10-07 사용자 결정).

상태 이름은 반출·이설일정이 적히는 순간부터 실행일 전날까지 「반출 예정」·「이설 예정」이다. 그
이름으로 세면 멀쩡히 쓰는 호기가 날짜를 적은 첫날부터 Dynamic 가용대수에서 빠졌다. 세는 자리는
가용 판정(`집계분류`)을 보고, 이름을 보이는 자리는 그대로 이름을 본다.
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
    RELOCATION_DATE_COLUMN,
)
from capa_simulation.services.monthly_equipment_availability import (
    available_subtotal,
    build_monthly_equipment_availability,
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
    """3/16 반출이면 3/15 까지 가용이다. 월별은 바뀐 다음 날부터 기여하므로(Cut-off 0 의 3월
    구간 `(2/28, 3/31]`) 3월에 16일 가용·15일 완료이고, 2월은 통째로 가용이다.
    """
    monthly = _monthly(
        _master(_unit("EQ-1", **{column: EXIT_DAY})), _no_downtime(), [202602, 202603]
    )

    assert _cell(monthly, 202602, "가용") == pytest.approx(1.0)
    assert _cell(monthly, 202603, "가용") == pytest.approx(16 / 31)
    assert _cell(monthly, 202603, DONE_NAME[column]) == pytest.approx(15 / 31)
    # 예정 이름의 행은 생기지 않는다 — 가용이 아닌 날이 없다.
    assert _cell(monthly, 202602, PLANNED_NAME[column]) == 0.0
    subtotal = available_subtotal(monthly).set_index("생산계획년월")["Dynamic가용대수"]
    assert subtotal.to_dict() == pytest.approx({202602: 1.0, 202603: 16 / 31})


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
    assert gantt[["상태", "시작일", "종료일"]].values.tolist() == [
        [planned, date(2026, 1, 1), date(2026, 3, 15)],
        [done, date(2026, 3, 16), date(2026, 4, 30)],
    ]


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
