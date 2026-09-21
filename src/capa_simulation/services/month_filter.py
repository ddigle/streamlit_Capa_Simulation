# Purpose: 공통 YYYYMM 유효성 검증과 원천 데이터의 조회기간 산출·필터를 제공한다.

import pandas as pd

MONTH_COLUMN = "생산계획년월"


def valid_month_mask(numeric: pd.Series) -> pd.Series:
    """숫자로 변환된 값에서 연도 1~9999·월 1~12인 YYYYMM 정수만 고른다.

    정수 dtype 으로 바꾸기 전에 검사한다. 무한대·정수 범위 밖의 큰 수·누락값도
    변환 예외 없이 False 가 되며, 오류 문구와 빈 표 정책은 각 입력 경계가 정한다.
    UI 조회기간 제한은 달력의 유효성과 다른 정책이므로 여기 넣지 않는다.
    """
    bounded = numeric.where(numeric.between(101, 999912))
    return (bounded.notna() & bounded.mod(1).eq(0) & bounded.mod(100).between(1, 12)).fillna(False)


def available_month_range(data: pd.DataFrame, table_name: str) -> tuple[int, int]:
    """Return the minimum and maximum valid YYYYMM values in a table."""
    months = _validated_months(data, table_name)
    return int(months.min()), int(months.max())


def filter_month_range(
    data: pd.DataFrame,
    start_month: int,
    end_month: int,
    table_name: str,
) -> pd.DataFrame:
    """Keep rows whose YYYYMM value falls within the inclusive range."""
    _validate_month_value(start_month, "시작년월")
    _validate_month_value(end_month, "종료년월")
    if start_month > end_month:
        raise ValueError("시작년월은 종료년월보다 클 수 없습니다.")

    months = _validated_months(data, table_name)
    return data.loc[months.between(start_month, end_month)].copy()


def _validated_months(data: pd.DataFrame, table_name: str) -> pd.Series:
    if MONTH_COLUMN not in data.columns:
        raise ValueError(f"{table_name}에 {MONTH_COLUMN} 컬럼이 없습니다.")

    numeric = pd.to_numeric(data[MONTH_COLUMN], errors="coerce")
    valid = valid_month_mask(numeric)
    if not valid.all():
        examples = data.loc[~valid, MONTH_COLUMN].head(5).tolist()
        raise ValueError(f"{table_name}의 {MONTH_COLUMN}은 YYYYMM 형식이어야 합니다: {examples}")
    if numeric.empty:
        raise ValueError(f"{table_name}에 선택할 생산계획년월 데이터가 없습니다.")
    return numeric.astype("int64")


def _validate_month_value(month: int, label: str) -> None:
    numeric = pd.to_numeric(pd.Series([month]), errors="coerce")
    if not valid_month_mask(numeric).iloc[0]:
        raise ValueError(f"{label}은 YYYYMM 형식이어야 합니다: {month}")
