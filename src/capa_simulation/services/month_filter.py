import pandas as pd

MONTH_COLUMN = "생산계획년월"


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
    whole_number = numeric.notna() & numeric.mod(1).eq(0)
    integer_months = numeric.fillna(0).astype("int64")
    calendar_month = integer_months.mod(100).between(1, 12)
    calendar_year = integer_months.floordiv(100).between(1, 9999)
    valid = whole_number & calendar_month & calendar_year
    if not valid.all():
        examples = data.loc[~valid, MONTH_COLUMN].head(5).tolist()
        raise ValueError(f"{table_name}의 {MONTH_COLUMN}은 YYYYMM 형식이어야 합니다: {examples}")
    if integer_months.empty:
        raise ValueError(f"{table_name}에 선택할 생산계획년월 데이터가 없습니다.")
    return integer_months


def _validate_month_value(month: int, label: str) -> None:
    calendar_month = month % 100
    calendar_year = month // 100
    if not 1 <= calendar_year <= 9999 or not 1 <= calendar_month <= 12:
        raise ValueError(f"{label}은 YYYYMM 형식이어야 합니다: {month}")
