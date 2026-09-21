# Purpose: Prototype calculations for standard-versus-actual Dynamic Capa analysis.

"""Prototype calculations for standard-versus-actual Dynamic Capa analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import sin

import pandas as pd

from capa_simulation.services.frame_contracts import (
    normalize_demand_basis,
    require_columns,
)

DYNAMIC_CAPACITY_KEYS = ["일자", "공정", "제품정보", "Stack", "WF 구분", "소요기준"]
DYNAMIC_CAPACITY_INPUT_COLUMNS = [
    *DYNAMIC_CAPACITY_KEYS,
    "표준 Capa",
    "표준 효율",
    "실적 효율",
    "표준 UPEH",
    "실적 UPEH",
    "계획시간",
    "실가동시간",
    "Rundown 시간",
    "설비 Down 시간",
    "기타 제약시간",
    "실적수량",
]

_TEXT_COLUMNS = ["공정", "제품정보", "Stack", "WF 구분", "소요기준"]
_NUMERIC_COLUMNS = [
    "표준 Capa",
    "표준 효율",
    "실적 효율",
    "표준 UPEH",
    "실적 UPEH",
    "계획시간",
    "실가동시간",
    "Rundown 시간",
    "설비 Down 시간",
    "기타 제약시간",
    "실적수량",
]
_SUM_COLUMNS = [
    "표준 Capa",
    "효율 반영 Capa",
    "실효 Capa",
    "모델 실적 Capa",
    "실적수량",
    "효율 손실 Capa",
    "UPEH 손실 Capa",
    "재공부족 미활용 Capa",
    "기타 정합성 Gap",
    "계획시간",
    "실가동시간",
    "Rundown 시간",
    "설비 Down 시간",
    "기타 제약시간",
]


@dataclass(frozen=True)
class DemoProfile:
    """데모 세계의 공정·제품 한 줄.

    Dynamic Capa 화면들이 **같은 세계**를 보게 하려고 공개한다. 상위 워터폴의 효율 손실과
    효율 실적 화면의 Gap 이 다른 데이터에서 나오면, 화면 사이를 오갈 때 숫자가 어긋나
    「이 손실을 저기서 파고든다」는 이야기가 무너진다.
    """

    process: str
    product: str
    stack: str
    wafer_type: str
    requirement_basis: str
    standard_upeh: float
    standard_efficiency: float
    efficiency_factor: float
    upeh_factor: float
    rundown_share: float


DEMO_PROFILES = [
    DemoProfile("Wafer Sorter", "HBM라", "12H", "Core", "WF", 2_400, 0.86, 0.95, 0.97, 0.08),
    DemoProfile("Wafer Sorter", "HBM다E", "12H", "Top", "WF", 2_050, 0.86, 0.91, 0.94, 0.13),
    DemoProfile("Pre B/D", "HBM라", "12H", "Core", "WF", 1_820, 0.84, 0.88, 0.96, 0.17),
    DemoProfile("Pre B/D", "HBM나", "8H", "Buffer", "WF", 1_650, 0.84, 0.92, 0.92, 0.12),
    DemoProfile("TC Bonding", "HBM라", "12H", "Core", "CHIP", 225, 0.82, 0.86, 0.90, 0.18),
    DemoProfile("TC Bonding", "HBM다E", "12H", "Top", "CHIP", 238, 0.82, 0.90, 0.93, 0.15),
    DemoProfile("Mold", "HBM나", "8H", "Core", "PKG", 145, 0.88, 1.00, 1.00, 0.03),
    DemoProfile("Mold", "DDR5", "2H", "Buffer", "PKG", 170, 0.88, 0.99, 0.995, 0.04),
    DemoProfile("AVI-PKG", "HBM라", "12H", "PKG", "PKG", 112, 0.90, 0.94, 0.91, 0.14),
    DemoProfile("AVI-PKG", "DDR5", "2H", "PKG", "PKG", 132, 0.90, 0.97, 0.95, 0.09),
]


def build_dynamic_capacity_demo() -> pd.DataFrame:
    """Return deterministic demo rows matching the future DB join contract."""
    records: list[dict[str, object]] = []
    start = date(2026, 8, 15)
    for day_index in range(14):
        production_date = start + timedelta(days=day_index)
        for profile_index, profile in enumerate(DEMO_PROFILES):
            planned_hours = 8.0
            daily_wave = sin((day_index + profile_index) * 0.72)
            actual_efficiency = _clip(
                profile.standard_efficiency
                * profile.efficiency_factor
                * (1.0 + daily_wave * 0.025),
                0.40,
                0.99,
            )
            actual_upeh = profile.standard_upeh * profile.upeh_factor * (1.0 + daily_wave * 0.018)
            available_hours = planned_hours * actual_efficiency
            rundown_share = _clip(
                profile.rundown_share + 0.018 * sin(day_index * 0.9 + profile_index),
                0.02,
                0.35,
            )
            run_hours = available_hours * (1.0 - rundown_share)
            rundown_hours = available_hours - run_hours
            down_hours = planned_hours - available_hours
            standard_capacity = profile.standard_upeh * planned_hours * profile.standard_efficiency
            reconciliation_factor = 0.985 + 0.012 * sin(day_index * 0.55 + profile_index)
            actual_quantity = actual_upeh * run_hours * reconciliation_factor
            records.append(
                {
                    "일자": production_date,
                    "공정": profile.process,
                    "제품정보": profile.product,
                    "Stack": profile.stack,
                    "WF 구분": profile.wafer_type,
                    "소요기준": profile.requirement_basis,
                    "표준 Capa": standard_capacity,
                    "표준 효율": profile.standard_efficiency,
                    "실적 효율": actual_efficiency,
                    "표준 UPEH": profile.standard_upeh,
                    "실적 UPEH": actual_upeh,
                    "계획시간": planned_hours,
                    "실가동시간": run_hours,
                    "Rundown 시간": rundown_hours,
                    "설비 Down 시간": down_hours,
                    "기타 제약시간": 0.0,
                    "실적수량": actual_quantity,
                }
            )
    return calculate_dynamic_capacity(pd.DataFrame.from_records(records))


def calculate_dynamic_capacity(data: pd.DataFrame) -> pd.DataFrame:
    """Calculate the sequential capacity bridge for detailed actual-history rows."""
    require_columns(data, DYNAMIC_CAPACITY_INPUT_COLUMNS, "Dynamic Capa")
    result = data[DYNAMIC_CAPACITY_INPUT_COLUMNS].copy()
    result["일자"] = pd.to_datetime(result["일자"], errors="coerce")
    if result["일자"].isna().any():
        raise ValueError("Dynamic Capa의 일자 컬럼에 유효하지 않은 값이 있습니다.")

    for column in _TEXT_COLUMNS:
        result[column] = result[column].astype("string").str.strip()
        if result[column].isna().any() or result[column].eq("").any():
            raise ValueError(f"Dynamic Capa의 {column} 연결 키에 누락값이 있습니다.")
    result["소요기준"] = normalize_demand_basis(result["소요기준"])

    for column in _NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if result[column].isna().any():
            raise ValueError(f"Dynamic Capa의 {column} 컬럼에 숫자가 아닌 값이 있습니다.")
        result[column] = result[column].astype("float64")

    positive_columns = ["표준 Capa", "표준 효율", "표준 UPEH", "계획시간"]
    if any(result[column].le(0).any() for column in positive_columns):
        raise ValueError("표준 Capa·효율·UPEH와 계획시간은 0보다 커야 합니다.")
    nonnegative_columns = [
        "실적 효율",
        "실적 UPEH",
        "실가동시간",
        "Rundown 시간",
        "설비 Down 시간",
        "기타 제약시간",
        "실적수량",
    ]
    if any(result[column].lt(0).any() for column in nonnegative_columns):
        raise ValueError("Dynamic Capa의 실적값과 시간 분류값은 0 이상이어야 합니다.")

    result["효율 반영 Capa"] = result["표준 Capa"] * (result["실적 효율"] / result["표준 효율"])
    result["실효 Capa"] = result["효율 반영 Capa"] * (result["실적 UPEH"] / result["표준 UPEH"])
    available_hours = result["실가동시간"] + result["Rundown 시간"]
    loading_rate = result["실가동시간"].div(available_hours.where(available_hours.gt(0)))
    loading_rate = loading_rate.fillna(0.0).clip(lower=0.0, upper=1.0)
    result["모델 실적 Capa"] = result["실효 Capa"] * loading_rate
    result["효율 손실 Capa"] = result["표준 Capa"] - result["효율 반영 Capa"]
    result["UPEH 손실 Capa"] = result["효율 반영 Capa"] - result["실효 Capa"]
    result["재공부족 미활용 Capa"] = result["실효 Capa"] - result["모델 실적 Capa"]
    result["기타 정합성 Gap"] = result["모델 실적 Capa"] - result["실적수량"]
    _add_derived_rates(result)
    return result


def filter_dynamic_capacity(
    data: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    process: str | None = None,
    product: str | None = None,
    stack: str | None = None,
    wafer_type: str | None = None,
) -> pd.DataFrame:
    """Filter calculated Dynamic Capa rows without changing their granularity."""
    if start_date > end_date:
        raise ValueError("Dynamic Capa 조회 시작일은 종료일보다 늦을 수 없습니다.")
    dates = data["일자"].astype("datetime64[ns]")
    date_mask = dates.ge(pd.Timestamp(start_date)) & dates.le(pd.Timestamp(end_date))
    result: pd.DataFrame = data[date_mask].copy()
    for column, value in (
        ("공정", process),
        ("제품정보", product),
        ("Stack", stack),
        ("WF 구분", wafer_type),
    ):
        if value is not None:
            result = result[result[column].eq(value)].copy()
    return result.reset_index(drop=True)


def aggregate_dynamic_capacity(
    data: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    """Aggregate capacities and calculate weighted standard/actual reference values."""
    required = [*_SUM_COLUMNS, "표준 효율", "실적 효율", "표준 UPEH", "실적 UPEH", "소요기준"]
    require_columns(data, [*group_columns, *required], "Dynamic Capa")
    if data.empty:
        return pd.DataFrame(columns=[*group_columns, *required])

    records: list[dict[str, object]] = []
    group_key: str | list[str] = group_columns[0] if len(group_columns) == 1 else group_columns
    for raw_key, group in data.groupby(group_key, dropna=False, sort=False):
        key_values = raw_key if isinstance(raw_key, tuple) else (raw_key,)
        record = dict(zip(group_columns, key_values, strict=True))
        requirement_bases = group["소요기준"].dropna().astype("string").unique().tolist()
        if len(requirement_bases) != 1:
            # 한 공정은 소요기준을 하나만 갖는다(업무 규칙). 그래서 이 집계는 소요기준이
            # 섞이지 않는다는 전제 위에 서 있다. 섞였다면 그룹 축이 공정을 넘었거나
            # 기준정보가 어긋난 것이므로, 조용히 더하지 않고 어느 기준들이 섞였는지 말한다.
            mixed = ", ".join(sorted(requirement_bases)) or "없음"
            raise ValueError(
                f"집계 그룹 안에 소요기준이 둘 이상이라 Capa 수량을 합산할 수 없습니다 "
                f"({record}: {mixed}). 한 공정은 같은 형태의 유닛만 투입하므로 "
                "기준정보에서 소요기준을 하나로 맞추세요."
            )
        record["소요기준"] = str(requirement_bases[0])
        for column in _SUM_COLUMNS:
            record[column] = float(group[column].sum())
        record["표준 효율"] = _weighted_average(group["표준 효율"], group["계획시간"])
        record["실적 효율"] = _weighted_average(group["실적 효율"], group["계획시간"])
        record["표준 UPEH"] = _weighted_average(group["표준 UPEH"], group["실가동시간"])
        record["실적 UPEH"] = _weighted_average(group["실적 UPEH"], group["실가동시간"])
        records.append(record)

    result = pd.DataFrame.from_records(records)
    _add_derived_rates(result)
    result["상태"] = result["Capa 실현률"].map(_status_label).astype("string")
    return result


def _add_derived_rates(data: pd.DataFrame) -> None:
    data["Capa 실현률"] = _ratio_or_zero(data["실적수량"], data["표준 Capa"])
    data["설비 성능 실현률"] = _ratio_or_zero(data["실효 Capa"], data["표준 Capa"])
    data["가용 Capa 활용률"] = _ratio_or_zero(data["실적수량"], data["실효 Capa"])
    data["효율 Gap"] = data["실적 효율"] - data["표준 효율"]
    data["UPEH Gap"] = _ratio_or_zero(data["실적 UPEH"], data["표준 UPEH"]) - 1.0
    data["재공부족 미활용률"] = _ratio_or_zero(data["재공부족 미활용 Capa"], data["실효 Capa"])


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    numeric_values = pd.to_numeric(values, errors="coerce").astype("float64")
    numeric_weights = pd.to_numeric(weights, errors="coerce").astype("float64")
    valid = numeric_values.notna() & numeric_weights.notna() & numeric_weights.gt(0)
    if not valid.any():
        return float("nan")
    return float(
        (numeric_values[valid] * numeric_weights[valid]).sum() / numeric_weights[valid].sum()
    )


def _ratio_or_zero(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """분모가 0이면 **0** 으로 내린다. `performance_actuals._ratio_or_na` 와 합치지 않는다."""
    return numerator.div(denominator.where(denominator.ne(0))).fillna(0.0)


def _status_label(rate: float) -> str:
    if rate >= 0.90:
        return "정상"
    if rate >= 0.80:
        return "관찰"
    return "개선 필요"


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
