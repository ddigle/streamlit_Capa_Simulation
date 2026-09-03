# Purpose: 계산 서비스가 공유하는 DataFrame 컬럼 계약 검증과 업무 키 정규화 규칙을 제공한다.

"""Shared column contracts and business-key normalization for calculation services.

같은 규칙이 서비스마다 복제되면 한쪽만 고쳐져 조용히 갈라진다. 여러 서비스가 공유하는
검증·정규화는 여기서 단 한 번 정의한다. 계약이 서로 다른 것(예: null을 허용하는 숫자
변환과 거부하는 숫자 변환)은 억지로 합치지 않고 각 모듈에 남긴다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

# 소요기준은 공정이 어떤 부하 Unit을 쓰는지 정하며 BOX·PCB는 산식 구현 전까지 제외한다.
DEMAND_BASES = ("PKG", "CHIP", "WF")
# Area_Name은 대당 Capa의 UPEH/ST 분기를 결정한다.
AREA_NAMES = ("Main", "MI")
_AREA_BY_CASEFOLD = {name.casefold(): name for name in AREA_NAMES}


def require_columns(data: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    """필수 컬럼 누락을 계산 전에 한국어 오류로 알린다."""
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"{label} 필수 컬럼이 없습니다: {', '.join(missing)}")


def normalize_demand_basis(values: pd.Series) -> pd.Series:
    """소요기준 표기를 대문자로 통일하고 `WAFER`를 `WF`로 맞춘다.

    지원 값 검증은 하지 않는다. 원천에 아직 계산하지 않는 기준(BOX·PCB)이 섞여 있어도
    통과시켜야 하는 경로가 있으므로, 검증이 필요한 곳은 `validate_demand_basis`를 쓴다.
    """
    return values.astype("string").str.strip().str.upper().replace({"WAFER": "WF"})


def normalize_demand_basis_value(value: object) -> str:
    """스칼라 소요기준 한 건을 `normalize_demand_basis`와 같은 규칙으로 정규화한다."""
    normalized = str(value).strip().upper()
    return "WF" if normalized == "WAFER" else normalized


def validate_demand_basis(values: pd.Series, label: str) -> pd.Series:
    """소요기준을 정규화하고 지원하지 않는 값이 있으면 예시와 함께 거부한다."""
    normalized = normalize_demand_basis(values)
    invalid = ~normalized.isin(DEMAND_BASES)
    if invalid.any():
        examples = normalized.loc[invalid].drop_duplicates().head(5).tolist()
        raise ValueError(f"{label}에 지원하지 않는 소요기준이 있습니다: {examples}")
    return normalized


def normalize_month_column(data: pd.DataFrame, label: str, *, column: str = "생산계획년월") -> None:
    """월 컬럼을 유효한 정수 `YYYYMM`으로 제자리 정규화한다."""
    numeric = pd.to_numeric(data[column], errors="coerce")
    valid = numeric.notna() & numeric.mod(1).eq(0)
    months = numeric.fillna(0).astype("int64")
    valid &= months.mod(100).between(1, 12)
    if not valid.all():
        raise ValueError(f"{label}의 {column}은 YYYYMM 형식이어야 합니다.")
    data[column] = months


def assert_complete(data: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    """연결 키로 쓸 컬럼에 null이나 빈 문자열이 없는지 확인한다.

    수치 컬럼을 넘기지 않도록 주의한다. 비어 있는 것이 정상인 값까지 검사하면 정상
    데이터가 예외로 죽는다.
    """
    if any(data[column].isna().any() or data[column].eq("").any() for column in columns):
        raise ValueError(f"{label}의 필수 연결 키에 누락값이 있습니다.")


def to_numeric_strict(values: pd.Series, label: str) -> pd.Series:
    """숫자로 바꿀 수 없는 값과 누락값을 모두 거부한다.

    빈값을 허용해야 하는 컬럼에는 쓰지 않는다.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{label}에 숫자가 아닌 값 또는 누락값이 있습니다.")
    return numeric.astype("float64")


def normalize_area_name(values: pd.Series, label: str) -> pd.Series:
    """Area_Name의 대소문자·공백을 흡수해 `Main`·`MI`로 통일한다.

    원천과 기존 리비전의 표기 차이를 여기서 흡수하므로 `RQ_REQB`와 UPEH·측정률이
    같은 경로 키로 연결된다. 두 값 외에는 계산할 수 없으므로 거부한다.
    """
    folded = values.astype("string").str.strip().str.casefold()
    invalid = folded.isna() | ~folded.isin(_AREA_BY_CASEFOLD)
    if invalid.any():
        examples = values.loc[invalid].drop_duplicates().head(5).tolist()
        raise ValueError(f"{label}의 Area_Name은 Main 또는 MI여야 합니다: {examples}")
    return folded.map(_AREA_BY_CASEFOLD).astype("string")
