# Purpose: 정지·반출/이설 두 날짜의 집계·도면 이탈 판정과 기존 데이터의 숫자·도면 불변을 검증한다.

"""정지일정(옛 반출일정)·반출/이설일정(옛 이설일정) — 2026-10-16 사용자 결정.

- **집계 이탈일** = min(정지, 반출/이설). 그날부터 보유·가용·지분에서 빠진다(옛 반출·이설과
  같은 셈).
- **도면 이탈일** = 반출/이설일정, 없으면 정지일정. `레이아웃반영여부` 는 그 전날까지 참이다.
- 두 날짜를 함께 적을 수 있다(정지 ≤ 반출/이설). 개편 전에는 함께 적을 수 없어 기존 행은 둘 중
  하나만 있다 — 그래서 **기존 데이터의 숫자·도면은 바뀌지 않는다.**

아래 `*_BEFORE` 블록은 개편 **전** 규칙(정지·반출/이설 가운데 하나만 적던 때)으로 같은 합성
fleet 을 돌려 얻은 결과를 그대로 박은 것이다. 바뀐 것은 상태 이름 넷(반출 예정 → 정지 예정,
반출 완료 → 정지, 이설 예정 → 반출/이설 예정, 이설 완료 → 반출/이설 완료)과 분류 대수 컬럼
이름뿐이고, 숫자는 한 칸도 같아야 한다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_milestone_transition_events,
    build_space_equipment_status,
    build_weekly_equipment_availability,
)
from capa_simulation.services.equipment_contract import (
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    LAYOUT_EXITED_COLUMN,
    LAYOUT_REFLECTED_COLUMN,
    RELOCATION_DATE_COLUMN,
    STATUS_COUNT_COLUMNS,
    STOP_DATE_COLUMN,
)
from capa_simulation.services.monthly_equipment_availability import (
    build_monthly_equipment_availability,
)

PROCESS = "DEMO_GOLD"
_EMPTY_BASELINE = pd.DataFrame(columns=["공정", "분류", "기존보유대수", "비고"])


def _unit(name: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(EQUIPMENT_COLUMNS)
    row.update(
        {
            "설비명": name,
            "공정소분류": PROCESS,
            "공정대분류": "B/N",
            "사용기준": "HBM",
            "보관유무": "N",
            "기존설비여부": "N",
            "레이아웃표시": "Y",
            "동": "C1",
            "층": "1F",
            "X좌표": 10,
            "Y좌표": 10,
            "Xsize": 5,
            "Ysize": 5,
        }
    )
    row.update(overrides)
    return row


def _new_unit(name: str, arrival: str, qual: str, status: str, **overrides: Any) -> dict[str, Any]:
    return _unit(name, 반입일정=arrival, Qual일정=qual, Qual상태=status, **overrides)


def _fleet() -> pd.DataFrame:
    """개편 전 데이터의 꼴 — 정지일정(옛 반출)·반출/이설일정(옛 이설) 가운데 하나만 적힌 행들."""
    stop, exit_ = STOP_DATE_COLUMN, RELOCATION_DATE_COLUMN
    module = {"Main 설비": "G-M1"}
    rows = [
        _unit("G-A", 기존설비여부="Y", **{stop: "2026-03-16"}),
        _unit("G-B", 기존설비여부="Y", **{exit_: "2026-04-10"}),
        _new_unit("G-C", "2026-01-05", "2026-02-02", "완료", **{stop: "2026-05-20"}),
        _new_unit("G-D", "2026-02-10", "2026-03-03", "확정", **{exit_: "2026-05-05"}),
        _new_unit("G-M1A", "2025-12-01", "2026-01-10", "완료", **module, **{stop: "2026-04-01"}),
        _new_unit("G-M1B", "2025-12-01", "2026-01-10", "완료", **module),
        _unit("G-E", 보관유무="Y", **{exit_: "2026-03-20"}),
        _unit("G-F", 기존설비여부="Y", 레이아웃표시="N", **{stop: "2026-06-01"}),
        _new_unit("G-G", "2026-03-15", "2026-04-15", "계획"),
    ]
    return pd.DataFrame(rows, columns=list(EQUIPMENT_COLUMNS))


def _downtime() -> pd.DataFrame:
    return pd.DataFrame(
        [{"설비명": "G-F", "비가동유형": "고장", "시작일": "2026-03-01", "종료일": "2026-03-10"}],
        columns=list(DOWNTIME_COLUMNS),
    )


def _no_downtime() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DOWNTIME_COLUMNS))


def _lines(block: str) -> list[list[str]]:
    return [line.split("|") for line in block.strip().splitlines()]


def _num(value: object) -> str:
    text = f"{float(str(value)):.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _flag(value: object) -> str:
    return "Y" if bool(value) else "N"


STATUS_BEFORE = """
2026-01-01|G-A|정지 예정|Y|Y|가용|Y|1
2026-01-01|G-B|반출/이설 예정|Y|Y|가용|Y|1
2026-01-01|G-C|정지 예정|N|N|정지 예정|Y|1
2026-01-01|G-D|반출/이설 예정|N|N|반출/이설 예정|Y|1
2026-01-01|G-M1A|정지 예정|Y|N|정지 예정|Y|0.5
2026-01-01|G-M1B|셋업 진행중|Y|N|셋업 진행중|Y|0.5
2026-01-01|G-E|반출/이설 예정|Y|N|반출/이설 예정|Y|1
2026-01-01|G-F|정지 예정|Y|Y|가용|N|1
2026-01-01|G-G|입고 예정|N|N|입고 예정|Y|1
2026-02-15|G-A|정지 예정|Y|Y|가용|Y|1
2026-02-15|G-B|반출/이설 예정|Y|Y|가용|Y|1
2026-02-15|G-C|정지 예정|Y|Y|가용|Y|1
2026-02-15|G-D|반출/이설 예정|Y|N|반출/이설 예정|Y|1
2026-02-15|G-M1A|정지 예정|Y|Y|가용|Y|0.5
2026-02-15|G-M1B|가용|Y|Y|가용|Y|0.5
2026-02-15|G-E|반출/이설 예정|Y|N|반출/이설 예정|Y|1
2026-02-15|G-F|정지 예정|Y|Y|가용|N|1
2026-02-15|G-G|입고 예정|N|N|입고 예정|Y|1
2026-03-05|G-A|정지 예정|Y|Y|가용|Y|1
2026-03-05|G-B|반출/이설 예정|Y|Y|가용|Y|1
2026-03-05|G-C|정지 예정|Y|Y|가용|Y|1
2026-03-05|G-D|반출/이설 예정|Y|Y|가용|Y|1
2026-03-05|G-M1A|정지 예정|Y|Y|가용|Y|0.5
2026-03-05|G-M1B|가용|Y|Y|가용|Y|0.5
2026-03-05|G-E|반출/이설 예정|Y|N|반출/이설 예정|Y|1
2026-03-05|G-F|운영 비가동|Y|N|운영 비가동|N|1
2026-03-05|G-G|입고 예정|N|N|입고 예정|Y|1
2026-03-16|G-A|정지|N|N|정지|N|1
2026-03-16|G-B|반출/이설 예정|Y|Y|가용|Y|1
2026-03-16|G-C|정지 예정|Y|Y|가용|Y|1
2026-03-16|G-D|반출/이설 예정|Y|Y|가용|Y|1
2026-03-16|G-M1A|정지 예정|Y|Y|가용|Y|0.5
2026-03-16|G-M1B|가용|Y|Y|가용|Y|0.5
2026-03-16|G-E|반출/이설 예정|Y|N|반출/이설 예정|Y|1
2026-03-16|G-F|정지 예정|Y|Y|가용|N|1
2026-03-16|G-G|셋업 진행중|Y|N|셋업 진행중|Y|1
2026-03-20|G-A|정지|N|N|정지|N|1
2026-03-20|G-B|반출/이설 예정|Y|Y|가용|Y|1
2026-03-20|G-C|정지 예정|Y|Y|가용|Y|1
2026-03-20|G-D|반출/이설 예정|Y|Y|가용|Y|1
2026-03-20|G-M1A|정지 예정|Y|Y|가용|Y|0.5
2026-03-20|G-M1B|가용|Y|Y|가용|Y|0.5
2026-03-20|G-E|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-03-20|G-F|정지 예정|Y|Y|가용|N|1
2026-03-20|G-G|셋업 진행중|Y|N|셋업 진행중|Y|1
2026-04-01|G-A|정지|N|N|정지|N|1
2026-04-01|G-B|반출/이설 예정|Y|Y|가용|Y|1
2026-04-01|G-C|정지 예정|Y|Y|가용|Y|1
2026-04-01|G-D|반출/이설 예정|Y|Y|가용|Y|1
2026-04-01|G-M1A|정지|N|N|정지|N|0
2026-04-01|G-M1B|가용|Y|Y|가용|Y|1
2026-04-01|G-E|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-04-01|G-F|정지 예정|Y|Y|가용|N|1
2026-04-01|G-G|셋업 진행중|Y|N|셋업 진행중|Y|1
2026-04-10|G-A|정지|N|N|정지|N|1
2026-04-10|G-B|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-04-10|G-C|정지 예정|Y|Y|가용|Y|1
2026-04-10|G-D|반출/이설 예정|Y|Y|가용|Y|1
2026-04-10|G-M1A|정지|N|N|정지|N|0
2026-04-10|G-M1B|가용|Y|Y|가용|Y|1
2026-04-10|G-E|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-04-10|G-F|정지 예정|Y|Y|가용|N|1
2026-04-10|G-G|셋업 진행중|Y|N|셋업 진행중|Y|1
2026-05-05|G-A|정지|N|N|정지|N|1
2026-05-05|G-B|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-05-05|G-C|정지 예정|Y|Y|가용|Y|1
2026-05-05|G-D|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-05-05|G-M1A|정지|N|N|정지|N|0
2026-05-05|G-M1B|가용|Y|Y|가용|Y|1
2026-05-05|G-E|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-05-05|G-F|정지 예정|Y|Y|가용|N|1
2026-05-05|G-G|가용|Y|Y|가용|Y|1
2026-05-20|G-A|정지|N|N|정지|N|1
2026-05-20|G-B|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-05-20|G-C|정지|N|N|정지|N|1
2026-05-20|G-D|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-05-20|G-M1A|정지|N|N|정지|N|0
2026-05-20|G-M1B|가용|Y|Y|가용|Y|1
2026-05-20|G-E|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-05-20|G-F|정지 예정|Y|Y|가용|N|1
2026-05-20|G-G|가용|Y|Y|가용|Y|1
2026-06-01|G-A|정지|N|N|정지|N|1
2026-06-01|G-B|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-06-01|G-C|정지|N|N|정지|N|1
2026-06-01|G-D|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-06-01|G-M1A|정지|N|N|정지|N|0
2026-06-01|G-M1B|가용|Y|Y|가용|Y|1
2026-06-01|G-E|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-06-01|G-F|정지|N|N|정지|N|1
2026-06-01|G-G|가용|Y|Y|가용|Y|1
2026-06-15|G-A|정지|N|N|정지|N|1
2026-06-15|G-B|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-06-15|G-C|정지|N|N|정지|N|1
2026-06-15|G-D|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-06-15|G-M1A|정지|N|N|정지|N|0
2026-06-15|G-M1B|가용|Y|Y|가용|Y|1
2026-06-15|G-E|반출/이설 완료|N|N|반출/이설 완료|N|1
2026-06-15|G-F|정지|N|N|정지|N|1
2026-06-15|G-G|가용|Y|Y|가용|Y|1
"""

WEEKLY_BEFORE = """
26-W01|5|5|3|2|1|0.5|3|1.5|2|0|0|0|0
26-W02|6|6|4|2|1|0|4|1|2|0|0|0|0
26-W03|6|6|4|2|1|0|4|1|2|0|0|0|0
26-W04|6|6|4|2|1|0|4|1|2|0|0|0|0
26-W05|6|6|4|2|1|0|4|1|2|0|0|0|0
26-W06|6|6|5|1|1|0|5|0|2|0|0|0|0
26-W07|7|7|5|2|1|0|5|0|2|0|0|0|0
26-W08|7|7|5|2|1|0|5|0|2|0|0|0|0
26-W09|7|7|4|3|1|0|4|0|2|0|1|0|0
26-W10|7|7|5|2|1|0|5|0|1|0|1|0|0
26-W11|8|8|6|2|0|1|6|0|1|0|0|0|0
26-W12|6|6|5|1|0|1|5|0|0|0|0|1|1
26-W13|6|6|5|1|0|1|5|0|0|0|0|1|1
26-W14|6|6|5|1|0|1|5|0|0|0|0|1|1
26-W15|5|5|4|1|0|1|4|0|0|0|0|1|2
26-W16|5|5|5|0|0|0|5|0|0|0|0|1|2
26-W17|5|5|5|0|0|0|5|0|0|0|0|1|2
26-W18|5|5|5|0|0|0|5|0|0|0|0|1|2
26-W19|4|4|4|0|0|0|4|0|0|0|0|1|3
26-W20|4|4|4|0|0|0|4|0|0|0|0|1|3
26-W21|3|3|3|0|0|0|3|0|0|0|0|2|3
26-W22|3|3|3|0|0|0|3|0|0|0|0|2|3
26-W23|2|2|2|0|0|0|2|0|0|0|0|3|3
26-W24|2|2|2|0|0|0|2|0|0|0|0|3|3
26-W25|2|2|2|0|0|0|2|0|0|0|0|3|3
26-W26|2|2|2|0|0|0|2|0|0|0|0|3|3
26-W27|2|2|2|0|0|0|2|0|0|0|0|3|3
"""

SPANS_BEFORE = """
G-A|정지 예정|2025-12-01|2026-03-15|1|가용|Y|N|Y
G-A|정지|2026-03-16|2026-07-31|1|정지|Y|Y|N
G-B|반출/이설 예정|2025-12-01|2026-04-09|1|가용|Y|N|Y
G-B|반출/이설 완료|2026-04-10|2026-07-31|1|반출/이설 완료|Y|Y|N
G-C|정지 예정|2025-12-01|2026-02-01|1|정지 예정|Y|N|N
G-C|정지 예정|2026-02-02|2026-05-19|1|가용|Y|N|Y
G-C|정지|2026-05-20|2026-07-31|1|정지|Y|Y|N
G-D|반출/이설 예정|2025-12-01|2026-03-02|1|반출/이설 예정|Y|N|N
G-D|반출/이설 예정|2026-03-03|2026-05-04|1|가용|Y|N|Y
G-D|반출/이설 완료|2026-05-05|2026-07-31|1|반출/이설 완료|Y|Y|N
G-E|반출/이설 예정|2025-12-01|2026-03-19|1|반출/이설 예정|Y|N|Y
G-E|반출/이설 완료|2026-03-20|2026-07-31|1|반출/이설 완료|Y|Y|N
G-F|정지 예정|2025-12-01|2026-02-28|1|가용|Y|N|N
G-F|운영 비가동|2026-03-01|2026-03-10|1|운영 비가동|Y|N|N
G-F|정지 예정|2026-03-11|2026-05-31|1|가용|Y|N|Y
G-F|정지|2026-06-01|2026-07-31|1|정지|Y|Y|N
G-G|입고 예정|2025-12-01|2026-03-14|1|입고 예정|Y|N|N
G-G|셋업 진행중|2026-03-15|2026-04-14|1|셋업 진행중|Y|N|N
G-G|가용|2026-04-15|2026-07-31|1|가용|Y|N|N
G-M1A|정지 예정|2025-12-01|2026-01-09|0.5|정지 예정|Y|N|N
G-M1A|정지 예정|2026-01-10|2026-03-31|0.5|가용|Y|N|Y
G-M1A|정지|2026-04-01|2026-07-31|0|정지|Y|Y|N
G-M1B|셋업 진행중|2025-12-01|2026-01-09|0.5|셋업 진행중|Y|N|N
G-M1B|가용|2026-01-10|2026-03-31|0.5|가용|Y|N|Y
G-M1B|가용|2026-04-01|2026-07-31|1|가용|Y|Y|N
"""

MONTHLY_BEFORE = """
202601|가용|3.677419|4.354839|1|Y
202601|입고 예정|1|1|1|N
202601|셋업 진행중|0.16129|0.322581|1|N
202601|정지 예정|1.16129|1.322581|-1|N
202601|반출/이설 예정|2|2|-1|N
202602|가용|4.928571|5.928571|1|Y
202602|입고 예정|1|1|1|N
202602|정지 예정|0.071429|0.071429|-1|N
202602|반출/이설 예정|2|2|-1|N
202603|가용|5.064516|6.064516|1|Y
202603|운영 비가동|0.322581|0.322581|-1|N
202603|입고 예정|0.483871|0.483871|1|N
202603|셋업 진행중|0.516129|0.516129|1|N
202603|정지|0.516129|0.516129|-1|N
202603|반출/이설 예정|0.709677|0.709677|-1|N
202603|반출/이설 완료|0.387097|0.387097|-1|N
202604|가용|4.8|4.8|1|Y
202604|셋업 진행중|0.5|0.5|1|N
202604|정지|1|2|-1|N
202604|반출/이설 완료|1.7|1.7|-1|N
202605|가용|3.741935|3.741935|1|Y
202605|정지|1.387097|2.387097|-1|N
202605|반출/이설 완료|2.870968|2.870968|-1|N
202606|가용|2|2|1|Y
202606|정지|3|4|-1|N
202606|반출/이설 완료|3|3|-1|N
202607|가용|2|2|1|Y
202607|정지|3|4|-1|N
202607|반출/이설 완료|3|3|-1|N
"""

GANTT_BEFORE = """
G-A|정지 예정|2025-12-01|2026-03-15
G-A|정지|2026-03-16|2026-07-31
G-B|반출/이설 예정|2025-12-01|2026-04-09
G-B|반출/이설 완료|2026-04-10|2026-07-31
G-C|정지 예정|2025-12-01|2026-05-19
G-C|정지|2026-05-20|2026-07-31
G-D|반출/이설 예정|2025-12-01|2026-05-04
G-D|반출/이설 완료|2026-05-05|2026-07-31
G-E|반출/이설 예정|2025-12-01|2026-03-19
G-E|반출/이설 완료|2026-03-20|2026-07-31
G-F|정지 예정|2025-12-01|2026-02-28
G-F|운영 비가동|2026-03-01|2026-03-10
G-F|정지 예정|2026-03-11|2026-05-31
G-F|정지|2026-06-01|2026-07-31
G-G|입고 예정|2025-12-01|2026-03-14
G-G|셋업 진행중|2026-03-15|2026-04-14
G-G|가용|2026-04-15|2026-07-31
G-M1A|정지 예정|2025-12-01|2026-03-31
G-M1A|정지|2026-04-01|2026-07-31
G-M1B|셋업 진행중|2025-12-01|2026-01-09
G-M1B|가용|2026-01-10|2026-07-31
"""


# ------------------------------------------------------------------ 기존 데이터 불변


def test_existing_rows_keep_their_status_and_layout_day_by_day() -> None:
    expected = _lines(STATUS_BEFORE)
    days = sorted({row[0] for row in expected})
    actual: list[list[str]] = []
    for day in days:
        status = build_equipment_status_as_of(_fleet(), _downtime(), as_of=date.fromisoformat(day))
        actual.extend(
            [
                day,
                str(row["설비명"]),
                str(row["상태"]),
                _flag(row["보유여부"]),
                _flag(row["가용여부"]),
                str(row["집계분류"]),
                _flag(row[LAYOUT_REFLECTED_COLUMN]),
                _num(row["설비지분"]),
            ]
            for _, row in status.iterrows()
        )

    assert actual == expected


def test_existing_rows_keep_their_weekly_counts() -> None:
    weekly = build_weekly_equipment_availability(
        _EMPTY_BASELINE,
        _fleet(),
        _downtime(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )
    columns = ["추가설비대수", "총대수", "가용대수", "비가동대수", *STATUS_COUNT_COLUMNS.values()]

    actual = [
        [str(row["Weeknum"]), *(_num(row[column]) for column in columns)]
        for _, row in weekly.iterrows()
    ]

    assert actual == _lines(WEEKLY_BEFORE)


def _counting_spans() -> pd.DataFrame:
    return build_equipment_lifecycle_spans(
        _fleet(),
        _downtime(),
        start_date=date(2025, 12, 1),
        end_date=date(2026, 7, 31),
        with_unit_share=True,
    )


def test_existing_rows_keep_their_counting_spans() -> None:
    actual = [
        [
            str(row["설비명"]),
            str(row["상태"]),
            str(row["시작일"]),
            str(row["종료일"]),
            _num(row["설비지분"]),
            str(row["집계분류"]),
            _flag(row["가용대수반영"]),
            _flag(row["반출이설시작"]),
            _flag(row["반출이설직전"]),
        ]
        for _, row in _counting_spans().iterrows()
    ]

    assert actual == _lines(SPANS_BEFORE)


def test_existing_rows_keep_their_monthly_counts() -> None:
    cutoff = pd.DataFrame({"공정": [PROCESS], "제품구분": ["*"], "Cutoff일수": [0]})
    monthly = build_monthly_equipment_availability(
        _counting_spans(),
        _EMPTY_BASELINE,
        cutoff,
        [202601, 202602, 202603, 202604, 202605, 202606, 202607],
    )

    actual = [
        [
            str(row["생산계획년월"]),
            str(row["분류"]),
            _num(row["대수"]),
            _num(row["환산대수"]),
            str(row["부호"]),
            _flag(row["가용반영"]),
        ]
        for _, row in monthly.iterrows()
    ]

    assert actual == _lines(MONTHLY_BEFORE)


def test_existing_rows_keep_their_gantt() -> None:
    spans = build_equipment_lifecycle_spans(
        _fleet(), _downtime(), start_date=date(2025, 12, 1), end_date=date(2026, 7, 31)
    )

    actual = [
        [str(row["설비명"]), str(row["상태"]), str(row["시작일"]), str(row["종료일"])]
        for _, row in spans.iterrows()
    ]

    assert actual == _lines(GANTT_BEFORE)


def test_a_single_exit_date_leaves_the_layout_on_the_day_it_leaves_the_counts() -> None:
    """두 날짜 가운데 하나만 있으면 도면 이탈일 = 집계 이탈일이다 — 옛 「반출·이설 완료」와 같다."""
    for day in ("2026-03-15", "2026-03-16", "2026-04-09", "2026-04-10"):
        status = build_space_equipment_status(
            _fleet(), _downtime(), as_of=date.fromisoformat(day)
        ).set_index("설비명")
        for unit in ("G-A", "G-B"):
            gone = bool(status.at[unit, LAYOUT_EXITED_COLUMN])
            assert gone == (not bool(status.at[unit, "보유여부"])), (day, unit)
            assert bool(status.at[unit, LAYOUT_REFLECTED_COLUMN]) == (not gone), (day, unit)
            assert status.at[unit, "단계"] == status.at[unit, "상태"]


# ------------------------------------------------------------------- 두 날짜를 함께


def _stop_then_exit() -> pd.DataFrame:
    """정지 5/10 → 반출/이설 6/20 인 기존 호기 하나(새 규칙에서만 가능한 행)."""
    dates = {STOP_DATE_COLUMN: "2026-05-10", RELOCATION_DATE_COLUMN: "2026-06-20"}
    return pd.DataFrame([_unit("G-S", 기존설비여부="Y", **dates)], columns=list(EQUIPMENT_COLUMNS))


@pytest.mark.parametrize(
    ("day", "status", "owned", "on_layout"),
    [
        ("2026-05-09", "정지 예정", True, True),
        ("2026-05-10", "정지", False, True),
        ("2026-06-19", "정지", False, True),
        ("2026-06-20", "반출/이설 완료", False, False),
    ],
)
def test_a_stopped_unit_leaves_the_counts_on_the_stop_date_and_the_layout_on_the_exit_date(
    day: str, status: str, owned: bool, on_layout: bool
) -> None:
    frame = build_space_equipment_status(
        _stop_then_exit(), _no_downtime(), as_of=date.fromisoformat(day)
    )

    assert frame.loc[0, "상태"] == status
    assert bool(frame.loc[0, "보유여부"]) is owned
    assert bool(frame.loc[0, "가용여부"]) is owned
    assert bool(frame.loc[0, LAYOUT_REFLECTED_COLUMN]) is on_layout
    assert bool(frame.loc[0, LAYOUT_EXITED_COLUMN]) is (not on_layout)


def test_a_stopped_unit_counts_until_the_day_before_the_stop_date() -> None:
    weekly = build_weekly_equipment_availability(
        _EMPTY_BASELINE,
        _stop_then_exit(),
        _no_downtime(),
        start_date=date(2026, 5, 4),
        end_date=date(2026, 6, 28),
    ).set_index("Weeknum")

    # 5/10 은 일요일이다 — 그 주(W19)부터 정지로 센다. 반출/이설 6/20(토)이 든 W25 부터는 완료다.
    assert weekly.loc["26-W19", "가용대수"] == 0.0
    assert weekly.loc["26-W19", "정지대수"] == 1.0
    assert weekly.loc["26-W24", "정지대수"] == 1.0
    assert weekly.loc["26-W25", "정지대수"] == 0.0
    assert weekly.loc["26-W25", "반출이설완료대수"] == 1.0
    spans = build_equipment_lifecycle_spans(
        _stop_then_exit(),
        _no_downtime(),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 30),
    )
    assert spans[["상태", "시작일", "종료일"]].values.tolist() == [
        ["정지 예정", date(2026, 5, 1), date(2026, 5, 9)],
        ["정지", date(2026, 5, 10), date(2026, 6, 19)],
        ["반출/이설 완료", date(2026, 6, 20), date(2026, 6, 30)],
    ]


def test_the_exit_transition_of_a_stopped_unit_comes_from_the_stop_stage() -> None:
    events = build_milestone_transition_events(
        _stop_then_exit(),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 30),
        as_of=date(2026, 6, 1),
    )

    assert events[["전환단계", "이전단계", "일정상태"]].values.tolist() == [
        ["정지", "가용/보관", "완료"],
        ["반출/이설", "정지", "예정"],
    ]
    # Qual상태는 Qual 단계에만 뜻이 있다.
    assert events["Qual상태"].tolist() == ["", ""]


def test_a_unit_stopping_and_leaving_on_the_same_day_makes_one_transition() -> None:
    """정지일정 = 반출/이설일정이면 전날 「정지 예정」, 그날 「반출/이설 완료」다 — 정지 단계를
    거치지 않으므로 전환은 「가용/보관 → 반출/이설」 한 건이다(두 건이면 단계별 건수에서 한 대가
    두 번 세어진다)."""
    same = {STOP_DATE_COLUMN: "2026-06-01", RELOCATION_DATE_COLUMN: "2026-06-01"}
    master = pd.DataFrame(
        [_unit("G-SAME", 기존설비여부="Y", **same)], columns=list(EQUIPMENT_COLUMNS)
    )
    statuses = [
        build_space_equipment_status(master, _no_downtime(), as_of=date.fromisoformat(day)).loc[
            0, "상태"
        ]
        for day in ("2026-05-31", "2026-06-01")
    ]

    events = build_milestone_transition_events(
        master,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 30),
        as_of=date(2026, 6, 15),
    )

    assert statuses == ["정지 예정", "반출/이설 완료"]
    assert events[["전환단계", "이전단계", "전환일"]].values.tolist() == [
        ["반출/이설", "가용/보관", pd.Timestamp("2026-06-01")],
    ]
