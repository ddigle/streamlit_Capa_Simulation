# Purpose: 파생 시나리오의 16표 복사와 월 축 조회·검증을 공통 계약으로 제공한다.

from collections.abc import Mapping

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
