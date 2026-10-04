# Purpose: 계산 서비스가 공유하는 DataFrame 컬럼 계약 검증과 업무 키 정규화 규칙을 제공한다.

"""Shared column contracts and business-key normalization for calculation services.

같은 규칙이 서비스마다 복제되면 한쪽만 고쳐져 조용히 갈라진다. 여러 서비스가 공유하는
검증·정규화는 여기서 단 한 번 정의한다. 계약이 서로 다른 것(예: null을 허용하는 숫자
변환과 거부하는 숫자 변환)은 억지로 합치지 않고 각 모듈에 남긴다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd

from capa_simulation.services.month_filter import valid_month_mask

# 소요기준은 공정이 어떤 부하 Unit을 쓰는지 정하며 BOX·PCB는 산식 구현 전까지 제외한다.
DEMAND_BASES = ("PKG", "CHIP", "WF")
# 산식이 확정되지 않아 대당 Capa·소요대수가 함께 빼는 소요기준. 두 계산이 같은 집합을 봐야
# 한쪽만 고쳐 서로 다른 행을 조용히 빼는 일이 없다 — 여기 한 곳에서만 정의한다.
UNIMPLEMENTED_BASES = {"BOX", "PCB"}
# Area_Name은 대당 Capa의 UPEH/ST 분기를 결정한다.
AREA_NAMES = ("Main", "MI")
_AREA_BY_CASEFOLD = {name.casefold(): name for name in AREA_NAMES}


def assert_one_demand_basis_per_process(
    data: pd.DataFrame,
    label: str,
    *,
    process_column: str = "공정",
    basis_column: str = "소요기준",
) -> None:
    """한 공정이 소요기준을 둘 이상 갖지 못하게 막는다.

    **업무 규칙이다** (2026-09-05 확인). 한 공정에 들어오는 유닛은 전부 같은 형태다.
    환산으로 다른 소요기준의 유효 Capa 나 재공 값을 만들 수는 있어도, 공정 자체가 소요기준을
    복수로 갖지는 않는다. 그러므로 이것이 감지되면 계산을 멈추고 알려야 한다 — 조용히
    한쪽을 고르면 그 공정의 유효 Capa 와 소요대수가 통째로 틀린다.

    메시지에 **충돌한 소요기준을 함께 적는다.** 공정 이름만 있으면 사용자가 기준정보의
    어느 행을 고쳐야 하는지 알 수 없다.
    """
    require_columns(data, [process_column, basis_column], label)
    if data.empty:
        return
    grouped = (
        data.loc[:, [process_column, basis_column]]
        .assign(**{basis_column: data[basis_column].astype("string").str.strip()})
        .dropna(subset=[basis_column])
        .drop_duplicates()
        .groupby(process_column, dropna=False)[basis_column]
    )
    conflicts = {
        str(process): sorted(str(value) for value in bases)
        for process, bases in grouped.unique().items()
        if len(bases) > 1
    }
    if not conflicts:
        return
    shown = list(conflicts)[:5]
    detail = " / ".join(f"{process} → {', '.join(conflicts[process])}" for process in shown)
    more = f" 외 {len(conflicts) - len(shown)}건" if len(conflicts) > len(shown) else ""
    raise ValueError(
        f"공정 하나에 소요기준이 둘 이상입니다 ({label}): {detail}{more}. "
        "한 공정은 같은 형태의 유닛만 투입하므로 소요기준이 하나여야 합니다. "
        "기준정보에서 해당 공정의 소요기준을 하나로 맞춘 뒤 다시 실행하세요."
    )


def require_columns(data: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    """필수 컬럼 누락을 계산 전에 한국어 오류로 알린다."""
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"{label} 필수 컬럼이 없습니다: {', '.join(missing)}")


def require_exact_columns(
    columns: Iterable[object],
    expected: Sequence[str],
    label: str,
    *,
    limit: int | None = None,
    check_order: bool = False,
    strip: bool = False,
) -> None:
    """컬럼이 계약과 정확히 같은지 확인하고, 다르면 누락·추가를 적은 한국어 오류를 낸다.

    문구는 `"{label} 계약이 일치하지 않습니다 (누락: …; 추가: …)."` 하나다. `label` 은
    `계약이` 앞의 주어 전체다 — `선행 물량 컬럼`, `Core Data 78컬럼` 처럼 넘긴다. 누락은
    계약 차례로, 추가는 입력 차례로 싣는다. 이름은 모두 `str()` 로 바꿔 비교한다.

    - `check_order=False`(저장·계산 경계): 이름 집합만 본다. 차례가 달라도, 계약 컬럼이
      겹쳐 들어와도 여기서는 통과한다 — 뒤 단계가 계약 차례로 다시 고른다.
    - `check_order=True`(붙여넣기·CSV 입력): 목록이 양식과 한 칸이라도 다르면 막는다.
      누락·추가가 모두 비면(차례만 다르거나 머리글이 겹치면) `컬럼 순서가 양식과 다름` 을
      싣는다.
    - `strip=True`: 입력 머리글의 앞뒤 공백을 떼고 비교한다(복사한 머리글에 공백이 붙는다).
    - `limit`: 누락·추가를 각각 앞에서 이만큼만 싣는다. 78컬럼처럼 긴 계약의 오류가
      화면을 덮지 않게 한다.
    """
    actual = [str(column).strip() if strip else str(column) for column in columns]
    contract = [str(column) for column in expected]
    actual_names = set(actual)
    contract_names = set(contract)
    missing = [column for column in contract if column not in actual_names]
    extra = [column for column in actual if column not in contract_names]
    mismatched = actual != contract if check_order else bool(missing or extra)
    if not mismatched:
        return
    details: list[str] = []
    if missing:
        details.append(f"누락: {', '.join(missing[:limit])}")
    if extra:
        details.append(f"추가: {', '.join(extra[:limit])}")
    if not details:
        details.append("컬럼 순서가 양식과 다름")
    raise ValueError(f"{label} 계약이 일치하지 않습니다 ({'; '.join(details)}).")


def match_key(values: pd.Series) -> pd.Series:
    """분류값을 **맞대어 볼 때만** 쓰는 형태로 줄인다. 앞뒤 공백을 떼고 대소문자를 없앤다.

    원천 표기와 사람이 적은 표기가 대소문자만 다른 일이 잦다 — 원천 `WF 구분` 은 `TOP` 인데
    표시순서 규칙에는 `Top` 이라고 적는 식이다. 글자 그대로 맞추면 규칙이 없는 것과 똑같이
    동작하는데, 오류도 경고도 없이 순서나 파생만 조용히 틀린다.

    **줄인 값은 비교에만 쓰고 저장·화면에는 원래 글자를 그대로 쓴다.** 사용자가 적은 표기나
    원천 표기가 앱을 지나며 바뀌면 그것대로 혼란이다.

    빈 값은 빈 문자열로 내린다. `astype("string")` 이 `None` 을 `pd.NA` 로 올리는데, 그러면
    `.eq(...)` 가 불리언이 아니라 **NA 를 품은** 불리언이 되어 `.astype(int)` 와 `.loc[]`
    마스킹이 그 자리에서 죽는다.
    """
    return values.astype("string").str.strip().str.casefold().fillna("")


def scalar_match_key(value: object) -> str:
    """`match_key` 의 한 값짜리. 두 곳이 같은 규칙으로 줄여야 짝이 맞는다."""
    return str(value).strip().casefold()


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
    if not valid_month_mask(numeric).all():
        raise ValueError(f"{label}의 {column}은 YYYYMM 형식이어야 합니다.")
    data[column] = numeric.astype("int64")


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
