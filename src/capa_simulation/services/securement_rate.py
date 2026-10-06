# Purpose: 공정별 가용대수와 소요대수에서 확보율 및 기준별 추가 필요대수를 계산한다.

from math import ceil

import pandas as pd

from capa_simulation.services.frame_contracts import normalize_month_column, require_columns

SECUREMENT_DIMENSIONS = ["공정"]
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
    warning_threshold: float,
    secure_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split monthly equipment gaps into warning and secure-threshold steps.

    The first result contains processes below the warning threshold. Its two
    incremental columns partition the minimum whole equipment count needed to
    reach the secure threshold. The second result contains processes that meet
    the warning threshold but remain below the secure threshold.
    """
    if warning_threshold < 0 or secure_threshold < 0:
        raise ValueError("확보 기준과 경고 기준은 0 이상이어야 합니다.")
    if warning_threshold > secure_threshold:
        raise ValueError("경고 기준은 확보 기준보다 클 수 없습니다.")

    required = ["생산계획년월", "공정", "가용대수", "소요대수", "확보율"]
    require_columns(securement_rate, required, "확보율")
    result = securement_rate[required].copy()
    _prepare_shortfall_input(result)
    result = result.loc[result["소요대수"].gt(0)].copy()
    result["확보율"] = result["가용대수"] / result["소요대수"]
    result["경고기준"] = warning_threshold
    result["확보기준"] = secure_threshold

    warning_gap = result["소요대수"].mul(warning_threshold).sub(result["가용대수"])
    secure_gap = result["소요대수"].mul(secure_threshold).sub(result["가용대수"])
    result["경고기준 필요대수"] = warning_gap.map(_ceil_positive).astype("int64")
    result["확보목표 총 필요대수"] = secure_gap.map(_ceil_positive).astype("int64")
    result["확보기준 추가대수"] = result["확보목표 총 필요대수"] - result["경고기준 필요대수"]

    sort_columns = ["생산계획년월", "확보율", "공정"]
    warning_shortfalls = result.loc[result["확보율"].lt(warning_threshold)]
    warning_shortfalls = warning_shortfalls.sort_values(sort_columns, kind="stable")
    secure_shortfalls = result.loc[
        result["확보율"].ge(warning_threshold) & result["확보율"].lt(secure_threshold)
    ]
    secure_shortfalls = secure_shortfalls.sort_values(sort_columns, kind="stable")
    return (
        warning_shortfalls[SHORTFALL_COLUMNS].reset_index(drop=True),
        secure_shortfalls[SHORTFALL_COLUMNS].reset_index(drop=True),
    )


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
