# Purpose: 파생 시나리오의 16표 복사와 월 축 조회·검증을 공통 계약으로 제공한다.

from collections.abc import Iterable, Mapping

import pandas as pd

from capa_simulation.services.frame_contracts import normalize_month_column, require_columns
from capa_simulation.services.month_filter import MONTH_COLUMN
from capa_simulation.settings import format_month

MONTHLY_TABLES = (
    "RQ_EQP_AVBL",
    "RQ_EQP_LENT",
    "RQ_EQP_OWN",
    "RQ_LOT_RATIO",
    "RQ_PKG_PLAN",
    "RQ_REQB",
    "RQ_RUN_DAY",
    "RQ_RUN_RATE",
    "RQ_UPEH",
    "RQ_VITAL",
    "RQ_WF_RATIO",
    "RQ_YLD",
)
NON_MONTHLY_TABLES = ("RQ_CHIP_EQ", "RQ_CHIP_QTY", "RQ_MODULE", "RQ_DISPLAY_ORDER")


def copy_scenario_tables(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """원본을 건드리지 않고 필수 표와 YYYYMM을 검증한 복사본을 돌려준다."""
    missing = set(MONTHLY_TABLES + NON_MONTHLY_TABLES) - tables.keys()
    if missing:
        raise ValueError(f"시나리오에 필요한 표가 없습니다: {', '.join(sorted(missing))}")
    copied = {name: tables[name].copy(deep=True) for name in MONTHLY_TABLES + NON_MONTHLY_TABLES}
    for name in MONTHLY_TABLES:
        require_columns(copied[name], [MONTH_COLUMN], name)
        normalize_month_column(copied[name], name)
    return copied


def month_axis(frame: pd.DataFrame) -> tuple[int, ...]:
    """정규화된 표의 실제 월 집합을 정렬한다. 중간에 없는 월을 채우지 않는다."""
    return tuple(sorted(int(value) for value in frame[MONTH_COLUMN].unique()))


def scenario_months(tables: Mapping[str, pd.DataFrame]) -> tuple[int, ...]:
    return tuple(sorted({month for name in MONTHLY_TABLES for month in month_axis(tables[name])}))


def format_month_range(months: tuple[int, ...]) -> str:
    return f"{format_month(months[0])} ~ {format_month(months[-1])}" if months else "월 데이터 없음"


def _month_index(month: int) -> int:
    return (month // 100) * 12 + month % 100 - 1


def _index_month(index: int) -> int:
    return (index // 12) * 100 + index % 12 + 1


def missing_calendar_months(months: Iterable[int]) -> tuple[int, ...]:
    """첫 달과 끝 달 사이 달력에서 빠진 달. `validate_month_axes` 는 표끼리만 견준다.

    월 머지는 베이스와 떨어진 달을 덧붙일 수 있다. 사이의 빈 달은 어느 표에도 없어 계산에서
    계획·설비가 없는 달로 남는다 — 막지는 않고 알리는 데 쓴다.
    """
    present = {_month_index(month) for month in months}
    if not present:
        return ()
    return tuple(
        _index_month(index)
        for index in range(min(present), max(present) + 1)
        if index not in present
    )


def format_month_runs(months: Iterable[int]) -> str:
    """이어지는 달을 묶어 `2027-01~2027-03, 2027-06` 처럼 적는다."""
    runs: list[list[int]] = []
    for index in sorted({_month_index(month) for month in months}):
        if runs and index == runs[-1][1] + 1:
            runs[-1][1] = index
        else:
            runs.append([index, index])
    return ", ".join(
        format_month(_index_month(first))
        if first == last
        else f"{format_month(_index_month(first))}~{format_month(_index_month(last))}"
        for first, last in runs
    )


def validate_month_axes(tables: Mapping[str, pd.DataFrame]) -> None:
    """12표의 합집합을 기준으로 중간 누락까지 찾고 빈 결과도 막는다."""
    expected = set(scenario_months(tables))
    if not expected:
        raise ValueError("합친 결과에 월 데이터가 없습니다.")
    errors = []
    for name in MONTHLY_TABLES:
        missing = expected - set(month_axis(tables[name]))
        if missing:
            sample = ", ".join(format_month(month) for month in sorted(missing)[:12])
            errors.append(f"{name}: 누락 {len(missing)}개월 ({sample})")
    if errors:
        raise ValueError(
            "12개 표의 월 축이 일치하지 않아 저장할 수 없습니다.\n" + "\n".join(errors)
        )
