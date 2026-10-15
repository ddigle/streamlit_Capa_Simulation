# Purpose: 공정별 가용대수와 소요대수에서 확보율과 기준별 추가 필요대수·부호 있는 과부족을 계산한다.

from math import ceil, floor

import pandas as pd

from capa_simulation.services.frame_contracts import normalize_month_column, require_columns
from capa_simulation.services.securement_threshold import CapacityStatus, SecurementThresholds

SECUREMENT_DIMENSIONS = ["공정"]

# 확보기준 과부족(`securement_balance`)의 컬럼과 부족 원인 값.
OWNED_COLUMN = "총보유대수"
STATUS_COLUMN = "판정"
BALANCE_COLUMN = "확보기준 과부족"
WARNING_NEED_COLUMN = "경고기준 필요대수"
CAUSE_COLUMN = "부족 원인"
CAUSE_OWNED_SHORT = "보유로도 부족"
CAUSE_RENTAL = "대여 영향"
BALANCE_COLUMNS = [
    "생산계획년월",
    "공정",
    OWNED_COLUMN,
    "가용대수",
    "소요대수",
    "확보율",
    "확보기준",
    "경고기준",
    STATUS_COLUMN,
    BALANCE_COLUMN,
    WARNING_NEED_COLUMN,
    CAUSE_COLUMN,
]
SHORTFALL_COLUMNS = [
    "생산계획년월",
    "공정",
    "가용대수",
    "소요대수",
    "확보율",
    "경고기준",
    "확보기준",
    "경고기준 필요대수",
    "확보기준 추가대수",
    "확보목표 총 필요대수",
]


def calculate_securement_rate(
    available_equipment: pd.DataFrame,
    required_equipment: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate monthly process securement rate as available / required."""
    available_required = ["생산계획년월", "공정", "가용대수"]
    required_required = ["생산계획년월", "공정", "소요대수"]
    require_columns(available_equipment, available_required, "RQ_EQP_AVBL")
    require_columns(required_equipment, required_required, "소요대수")

    available = available_equipment[available_required].copy()
    required = required_equipment[required_required].copy()
    _prepare_keys_and_value(available, "가용대수", "RQ_EQP_AVBL")
    _prepare_keys_and_value(required, "소요대수", "소요대수")

    available = available.groupby(["생산계획년월", "공정"], as_index=False, dropna=False)[
        ["가용대수"]
    ].sum()
    required = required.groupby(["생산계획년월", "공정"], as_index=False, dropna=False)[
        ["소요대수"]
    ].sum()

    positive_required = required.loc[required["소요대수"].gt(0)]
    availability_check = positive_required.merge(
        available[["생산계획년월", "공정"]],
        on=["생산계획년월", "공정"],
        how="left",
        indicator=True,
        # 양쪽 다 groupby 결과라 월·공정이 유일하다. 상위에서 집계가 깨지면 조기에 실패한다.
        validate="one_to_one",
    )
    missing_available = availability_check["_merge"].ne("both")
    if missing_available.any():
        examples = (
            availability_check.loc[missing_available, ["생산계획년월", "공정"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"소요대수는 있지만 가용대수가 없는 공정이 있습니다: {examples}")

    result = available.merge(
        required,
        on=["생산계획년월", "공정"],
        how="left",
        validate="one_to_one",
    )
    result["소요대수"] = result["소요대수"].fillna(0.0)
    result["확보율"] = result["가용대수"] / result["소요대수"].where(result["소요대수"].gt(0))
    return result


def securement_rate_to_month_table(data: pd.DataFrame) -> pd.DataFrame:
    """Pivot monthly process securement rates for display."""
    required = ["생산계획년월", "공정", "확보율"]
    require_columns(data, required, "확보율")
    result = data.pivot(
        index=SECUREMENT_DIMENSIONS,
        columns="생산계획년월",
        values="확보율",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [column for column in result.columns if column not in SECUREMENT_DIMENSIONS]
    result = result.rename(columns={month: str(int(month)) for month in raw_month_columns})
    month_columns = sorted(str(int(month)) for month in raw_month_columns)
    return result[[*SECUREMENT_DIMENSIONS, *month_columns]]


def build_securement_shortfall_tables(
    securement_rate: pd.DataFrame,
    *,
    thresholds: SecurementThresholds,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split monthly equipment gaps into warning and secure-threshold steps.

    The first result contains processes below the warning threshold. Its two
    incremental columns partition the minimum whole equipment count needed to
    reach the secure threshold. The second result contains processes that meet
    the warning threshold but remain below the secure threshold.

    기준은 **행의 달마다** 그 달의 실효 기준이다(`thresholds.for_month`). `경고기준`·`확보기준`
    컬럼이 행마다 그 값을 적는다. 월별 예외가 없으면 모든 행이 기본값이다.
    """
    # 저장 단계가 거꾸로 된 짝을 막지만, 이 함수는 저장본이 아닌 값도 받는다(테스트·직접 호출).
    # 기본 짝과 월별 예외의 실효 짝을 모두 본다.
    pairs_to_check = [
        thresholds.for_month(None),
        *(thresholds.for_month(month) for month in thresholds.exception_months),
    ]
    if any(secure < 0 or warning < 0 for secure, warning in pairs_to_check):
        raise ValueError("확보 기준과 경고 기준은 0 이상이어야 합니다.")
    if any(warning > secure for secure, warning in pairs_to_check):
        raise ValueError("경고 기준은 확보 기준보다 클 수 없습니다.")

    required = ["생산계획년월", "공정", "가용대수", "소요대수", "확보율"]
    require_columns(securement_rate, required, "확보율")
    result = securement_rate[required].copy()
    _prepare_shortfall_input(result)
    result = result.loc[result["소요대수"].gt(0)].copy()
    result["확보율"] = result["가용대수"] / result["소요대수"]
    pairs = [thresholds.for_month(int(month)) for month in result["생산계획년월"]]
    result["경고기준"] = pd.Series([pair[1] for pair in pairs], index=result.index, dtype="float64")
    result["확보기준"] = pd.Series([pair[0] for pair in pairs], index=result.index, dtype="float64")

    warning_gap = result["소요대수"].mul(result["경고기준"]).sub(result["가용대수"])
    secure_gap = result["소요대수"].mul(result["확보기준"]).sub(result["가용대수"])
    result["경고기준 필요대수"] = warning_gap.map(_ceil_positive).astype("int64")
    result["확보목표 총 필요대수"] = secure_gap.map(_ceil_positive).astype("int64")
    result["확보기준 추가대수"] = result["확보목표 총 필요대수"] - result["경고기준 필요대수"]

    sort_columns = ["생산계획년월", "확보율", "공정"]
    warning_shortfalls = result.loc[result["확보율"].lt(result["경고기준"])]
    warning_shortfalls = warning_shortfalls.sort_values(sort_columns, kind="stable")
    secure_shortfalls = result.loc[
        result["확보율"].ge(result["경고기준"]) & result["확보율"].lt(result["확보기준"])
    ]
    secure_shortfalls = secure_shortfalls.sort_values(sort_columns, kind="stable")
    return (
        warning_shortfalls[SHORTFALL_COLUMNS].reset_index(drop=True),
        secure_shortfalls[SHORTFALL_COLUMNS].reset_index(drop=True),
    )


def securement_balance(
    securement_rate: pd.DataFrame,
    *,
    thresholds: SecurementThresholds,
) -> pd.DataFrame:
    """행마다 그 달 확보기준에 대한 **부호 있는 정수 과부족**·판정·부족 원인을 붙인다.

    입력은 `생산계획년월`·`공정`·`총보유대수`·`가용대수`·`소요대수` 다(행 차례 그대로 돌려준다).
    기준은 행의 달마다 그 달의 실효 기준(`thresholds.for_month`)이다.

    - **판정**(`판정`)은 `thresholds.status(가용 ÷ 소요, 달)` 한 길이다. 확보율 칸과 과부족 칸이 이
      한 값으로 칠해진다. 소요가 0 인 행은 확보율이 없어 판정도 없다(`None`).
    - **과부족**(`확보기준 과부족`)은 판정이 확보가 아니면
      `−_ceil_positive(소요 × 확보기준 − 가용)`, 아니면
      `+floor(round(가용 − 소요 × 확보기준, 9))` 다. 모자란 쪽 크기는 Static Capa 의
      「확보목표 총 필요대수」(`build_securement_shortfall_tables`)와 같은 정수다.
    - 판정은 반올림하지 않은 확보율을, 과부족은 9자리 반올림을 본다. 그래서 부동소수 잡음
      경계(차이가 1e-9 안)에서는 **경고·부족으로 칠한 칸에 0 이 찍힐 수 있다** — 소요
      10.000000000000002·가용 10.95·확보기준 1.095 가 그렇다. 칠하기는 판정을, 숫자는 Static
      Capa 와 같은 올림을 따른다.
    - **부족 원인**(`부족 원인`)은 판정이 확보가 아닌 행에만 적는다. 총보유로도 소요 × 확보기준에
      못 미치면 「보유로도 부족」(대여를 거둬도 못 메운다 — 투자 검토), 총보유로는 닿지만 가용
      (보유 − 대여)이 못 미치면 「대여 영향」이다. 확보인 행은 빈 글자다. 총보유 비교도 같은 9자리
      반올림을 본다.
    - `경고기준 필요대수` 는 `_ceil_positive(소요 × 경고기준 − 가용)` 이다(소요 0 이면 0).
    """
    required = ["생산계획년월", "공정", OWNED_COLUMN, "가용대수", "소요대수"]
    require_columns(securement_rate, required, "확보율")
    result = securement_rate[required].copy().reset_index(drop=True)
    _prepare_shortfall_input(result)
    owned = pd.to_numeric(result[OWNED_COLUMN], errors="coerce")
    if owned.isna().any():
        raise ValueError(f"확보율.{OWNED_COLUMN}에 숫자가 아닌 값이 있습니다.")
    result[OWNED_COLUMN] = owned.astype("float64")

    months = [int(month) for month in result["생산계획년월"]]
    pairs = [thresholds.for_month(month) for month in months]
    result["확보기준"] = pd.Series([pair[0] for pair in pairs], index=result.index, dtype="float64")
    result["경고기준"] = pd.Series([pair[1] for pair in pairs], index=result.index, dtype="float64")

    demand = result["소요대수"].astype("float64")
    available = result["가용대수"].astype("float64")
    has_demand = demand.gt(0)
    result["확보율"] = available / demand.where(has_demand)
    statuses: list[CapacityStatus | None] = [
        thresholds.status(float(available_count) / float(demand_count), month)
        if demand_count > 0
        else None
        for available_count, demand_count, month in zip(available, demand, months, strict=True)
    ]
    result[STATUS_COLUMN] = pd.Series(statuses, index=result.index, dtype="object")

    secure_gap = demand.mul(result["확보기준"]).sub(available)
    warning_gap = demand.mul(result["경고기준"]).sub(available)
    owned_gap = demand.mul(result["확보기준"]).sub(result[OWNED_COLUMN])
    short = [status is not None and status != "secure" for status in statuses]
    result[BALANCE_COLUMN] = pd.Series(
        [
            -_ceil_positive(gap) if is_short else _floor_surplus(-gap)
            for gap, is_short in zip(secure_gap, short, strict=True)
        ],
        index=result.index,
        dtype="int64",
    )
    result[WARNING_NEED_COLUMN] = pd.Series(
        [
            _ceil_positive(gap) if demand_count > 0 else 0
            for gap, demand_count in zip(warning_gap, demand, strict=True)
        ],
        index=result.index,
        dtype="int64",
    )
    result[CAUSE_COLUMN] = pd.Series(
        [
            "" if not is_short else CAUSE_OWNED_SHORT if round(float(gap), 9) > 0 else CAUSE_RENTAL
            for gap, is_short in zip(owned_gap, short, strict=True)
        ],
        index=result.index,
        dtype="object",
    )
    return result[BALANCE_COLUMNS]


def _prepare_keys_and_value(data: pd.DataFrame, value_column: str, table_name: str) -> None:
    normalize_month_column(data, table_name)
    data["공정"] = data["공정"].astype("string").str.strip()
    if data["공정"].isna().any() or data["공정"].eq("").any():
        raise ValueError(f"{table_name}의 공정에 누락값이 있습니다.")
    data[value_column] = pd.to_numeric(data[value_column], errors="coerce")
    if data[value_column].isna().any():
        raise ValueError(f"{table_name}.{value_column}에 숫자가 아닌 값이 있습니다.")
    if data[value_column].lt(0).any():
        raise ValueError(f"{table_name}.{value_column} 값은 0 이상이어야 합니다.")


def _prepare_shortfall_input(data: pd.DataFrame) -> None:
    normalize_month_column(data, "확보율")

    data["공정"] = data["공정"].astype("string").str.strip()
    if data["공정"].isna().any() or data["공정"].eq("").any():
        raise ValueError("확보율의 공정에 누락값이 있습니다.")

    for column in ("가용대수", "소요대수"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
        if data[column].isna().any():
            raise ValueError(f"확보율.{column}에 숫자가 아닌 값이 있습니다.")
        if data[column].lt(0).any():
            raise ValueError(f"확보율.{column} 값은 0 이상이어야 합니다.")


def _ceil_positive(value: float) -> int:
    """올림 전에 부동소수 먼지를 턴다.

    `소요대수 × 기준 − 가용대수` 는 정확히 0 이어야 할 때도 0 이 되지 않는다 — 가용 55·
    소요 50·기준 1.1 이면 `50 * 1.1 = 55.00000000000001` 이라 차이가 1e-14 로 남고,
    올림이 그것을 **설비 1대**로 키운다. 대수는 정수 단위라 그 1대가 곧 투자 판단 1대다.

    대수는 보통 1e2 이하라 1e-9 는 업무상 의미 있는 차이를 삼키지 않는다.
    """
    return max(0, ceil(round(float(value), 9)))


def _floor_surplus(value: float) -> int:
    """여유 대수. `_ceil_positive` 의 짝 — 같은 9자리 반올림 뒤 내림하고 음수는 0 이다."""
    return max(0, floor(round(float(value), 9)))
