# Purpose: UPEH/ST와 효율·여유율·모듈·일수·측정률로 경로별 대당 Capa를 계산한다.

from typing import NamedTuple

import pandas as pd

from capa_simulation.services.frame_checks import assert_unique_keys, strip_text_columns
from capa_simulation.services.frame_contracts import (
    UNIMPLEMENTED_BASES,
    assert_complete,
    normalize_area_name,
    normalize_month_column,
    require_columns,
)

PERFORMANCE_KEYS = [
    "생산계획년월",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
]
UNIT_CAPACITY_DIMENSIONS = [
    "공정",
    "Area_Name",
    "소요기준",
    "양산구분",
    "제품정보",
    "Stack",
    "WF 구분",
    "STEP_SEQ",
    "MCP_SEQ",
]
CAPACITY_EXCLUSIONS_ATTR = "excluded_capacity_rows"
# 측정률 행이 없어 중립값 1.0 으로 이어 간 건수. **세지 않고 메우면 조용히 틀린다.**
# 측정률은 분모라 실제가 1 보다 작으면 대당 Capa 과소 → 소요대수 과대 → 확보율 과소(보수 쪽),
# 1 보다 크면 그 반대(낙관 쪽)로 틀린다.
CAPACITY_ASSUMPTIONS_ATTR = "assumed_capacity_defaults"
# 같은 가정이 걸린 달. 건수만 말하면 어느 달 칸을 채워야 하는지 다시 찾아야 한다.
# 대당 Capa 는 시나리오 전체 기간을 한 번에 계산하므로 조회기간 밖의 달도 들어 있다.
CAPACITY_ASSUMED_MONTHS_ATTR = "assumed_capacity_months"


class CapacityAssumptions(NamedTuple):
    """측정률을 1.0 으로 메운 경로 수와 그 달. 화면 알림이 둘 다 말한다."""

    counts: dict[str, int]
    months: dict[str, tuple[int, ...]]


def capacity_assumptions(unit_capacity: pd.DataFrame) -> CapacityAssumptions:
    """대당 Capa 프레임의 `attrs` 에서 가정을 꺼낸다. 없으면 빈 묶음이다."""
    return CapacityAssumptions(
        counts=dict(unit_capacity.attrs.get(CAPACITY_ASSUMPTIONS_ATTR, {})),
        months=dict(unit_capacity.attrs.get(CAPACITY_ASSUMED_MONTHS_ATTR, {})),
    )


# 검증 실패 메시지에 문제 행의 업무 키를 실으려면 그 컬럼이 어떤 키로 붙었는지 알아야 한다.
# 연결에 쓰는 키 목록과 검증이 보고하는 키 목록이 갈라지지 않게 한 곳에 둔다.
RUN_RATE_KEYS = ["생산계획년월", "공정", "양산구분"]
VITAL_KEYS = ["생산계획년월", "공정", "양산구분"]
MODULE_KEYS = ["공정"]
RUN_DAY_KEYS = ["생산계획년월", "공정"]

# 음수이면 그 행만 계산에서 빼는 컬럼. 둘 다 대당 Capa 식의 분모이고 결측 기본값이
# 1.0 인 쌍둥이 기준정보라 같은 규칙을 쓴다.
NEGATIVE_EXCLUDED_COLUMNS = (
    ("WF측정률", "WF측정률 음수"),
    ("Lot 측정률", "Lot 측정률 음수"),
)

# 측정률 0 은 측정 대상이 아닌 경로로 보고 빈 값과 같이 1.0 을 적용한다. 분모라서 0 을
# 그대로 두면 나눌 수 없어 예전에는 행을 통째로 뺐지만, 원천에서 0 과 빈 값이 같은 뜻으로
# 들어오는 것이 확인돼 같은 규칙으로 맞췄다. 음수는 입력 오류라 그대로 제외한다.
MEASUREMENT_RATIO_ZERO_DEFAULT = 1.0

# Main 행 UPEH 가 0 이하면 대당 Capa 도 0 이 된다. 예전에는 `대당 Capa 0 이하` 로만 적혀
# 분모·분자 어느 쪽이 문제인지 알 수 없었다. 원천 접힘으로 0 이 저장되는 일이 실제로 있어
# (`services/reference_conflicts.py` 참조) 원인을 사유에 적는다. MI 행은 ST 가 0 이하면
# `_prepare_performance` 가 먼저 막으므로 여기 걸리는 것은 Main 행뿐이다.
UPEH_EXCLUSION_REASON = "UPEH 0 이하"

# CAPA_RUN_RATE 는 대당 Capa 식의 **분자**다. 검사도 전용 규칙도 없는 유일한 인자여서,
# 0·음수가 들어오면 곱이 0 이하가 되어 `대당 Capa 0 이하` 로만 적혔다 — 사용자를 UPEH 쪽으로
# 보내는 오지목이다. 편중률 0 은 하드 오류인데 효율 0 은 조용한 제외라는 비대칭도 같이 남았다.
#
# 편중률처럼 하드 오류로 올리지 않는 이유는 `calculate_unit_capacity` 의 「계산 대상 행을 먼저
# 확정한다」 주석과 같다. 원천이 "해당 없음" 을 0 으로 적는 일이 실제로 있어
# (`services/reference_conflicts.py`) 그 한 줄 때문에 편집기조차 못 여는 쪽이 더 나쁘다.
# 대신 무엇이 0 인지 사유에 적는다.
RUN_RATE_EXCLUSION_REASON = "CAPA_RUN_RATE 0 이하"


def calculate_unit_capacity(
    upeh: pd.DataFrame,
    run_rate: pd.DataFrame,
    vital: pd.DataFrame,
    module: pd.DataFrame,
    run_day: pd.DataFrame,
    lot_ratio: pd.DataFrame,
    wf_ratio: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate monthly per-equipment capacity for Main and MI process rows."""
    performance = _prepare_performance(upeh)
    if performance.empty:
        empty_result = pd.DataFrame(
            columns=[
                "생산계획년월",
                *UNIT_CAPACITY_DIMENSIONS,
                "환산_UPEH",
                "대당 Capa",
            ]
        )
        empty_result.attrs[CAPACITY_EXCLUSIONS_ATTR] = pd.DataFrame()
        empty_result.attrs[CAPACITY_ASSUMPTIONS_ATTR] = {}
        empty_result.attrs[CAPACITY_ASSUMED_MONTHS_ATTR] = {}
        return empty_result

    assumed: dict[str, int] = {}
    assumed_months: dict[str, set[int]] = {}
    result = performance
    result = _join_reference(
        result,
        run_rate,
        RUN_RATE_KEYS,
        "CAPA_RUN_RATE",
        "RQ_RUN_RATE",
    )
    result = _join_reference(
        result,
        vital,
        VITAL_KEYS,
        "편중률",
        "RQ_VITAL",
    )
    result = _join_reference(result, module, MODULE_KEYS, "모듈수", "RQ_MODULE")
    result = _join_reference(
        result,
        run_day,
        RUN_DAY_KEYS,
        "RUN_DAY",
        "RQ_RUN_DAY",
    )
    result = _join_reference(
        result,
        lot_ratio,
        PERFORMANCE_KEYS,
        "Lot 측정률",
        "RQ_LOT_RATIO",
        missing_value_default=1.0,
        assumed=assumed,
        assumed_months=assumed_months,
    )
    result = _join_reference(
        result,
        wf_ratio,
        PERFORMANCE_KEYS,
        "WF측정률",
        "RQ_WF_RATIO",
        missing_value_default=1.0,
        assumed=assumed,
        assumed_months=assumed_months,
    )

    # 계산 대상 행을 먼저 확정한다. 어차피 빠질 행의 다른 기준값 때문에 화면 전체가
    # 멈추면 그 값을 고칠 편집기조차 열리지 않는다. 0 을 1.0 으로 올리는 것이 먼저다 —
    # 뒤에 두면 이미 뺀 행을 되살릴 수 없다.
    excluded_frames: list[pd.DataFrame] = []
    nonpositive_upeh = result["환산_UPEH"].le(0)
    excluded_frames.append(_exclusion_rows(result, nonpositive_upeh, UPEH_EXCLUSION_REASON))
    result = result.loc[~nonpositive_upeh].copy()

    nonpositive_run_rate = result["CAPA_RUN_RATE"].le(0)
    excluded_frames.append(_exclusion_rows(result, nonpositive_run_rate, RUN_RATE_EXCLUSION_REASON))
    result = result.loc[~nonpositive_run_rate].copy()

    for column, reason in NEGATIVE_EXCLUDED_COLUMNS:
        result[column] = result[column].mask(result[column].eq(0), MEASUREMENT_RATIO_ZERO_DEFAULT)
        negative_ratio = result[column].lt(0)
        excluded_frames.append(_exclusion_rows(result, negative_ratio, reason))
        result = result.loc[~negative_ratio].copy()

    for column, table_name, keys in (
        ("편중률", "RQ_VITAL", VITAL_KEYS),
        ("모듈수", "RQ_MODULE", MODULE_KEYS),
        ("RUN_DAY", "RQ_RUN_DAY", RUN_DAY_KEYS),
    ):
        _assert_positive(result, column, table_name, keys)

    result["대당 Capa"] = (
        result["환산_UPEH"]
        * 24.0
        * result["CAPA_RUN_RATE"]
        / result["편중률"]
        * result["모듈수"]
        * result["RUN_DAY"]
        / result["Lot 측정률"]
        / result["WF측정률"]
    )
    # 여기까지 온 행은 모든 인자가 양수다(UPEH·CAPA_RUN_RATE 는 위에서 뺐고, 편중률·모듈수·
    # RUN_DAY 는 하드 오류, 측정률은 0 → 1.0). 그래서 이 제외는 언더플로 같은 경우만 받는
    # 마지막 안전망이다 — 사유를 보고 원인을 찾을 수 없으니 여기 걸리는 것이 정상은 아니다.
    nonpositive_capacity = result["대당 Capa"].le(0)
    excluded_frames.append(_exclusion_rows(result, nonpositive_capacity, "대당 Capa 0 이하"))
    result = result.loc[~nonpositive_capacity].copy()
    columns = ["생산계획년월", *UNIT_CAPACITY_DIMENSIONS, "환산_UPEH", "대당 Capa"]
    output = (
        result[columns]
        .sort_values(["생산계획년월", *UNIT_CAPACITY_DIMENSIONS])
        .reset_index(drop=True)
    )
    output.attrs[CAPACITY_EXCLUSIONS_ATTR] = pd.concat(excluded_frames, ignore_index=True)
    output.attrs[CAPACITY_ASSUMPTIONS_ATTR] = assumed
    output.attrs[CAPACITY_ASSUMED_MONTHS_ATTR] = {
        table: tuple(sorted(months)) for table, months in assumed_months.items()
    }
    return output


def unit_capacity_to_month_table(unit_capacity: pd.DataFrame) -> pd.DataFrame:
    """Pivot calculated unit capacity into month columns for display."""
    required = ["생산계획년월", *UNIT_CAPACITY_DIMENSIONS, "대당 Capa"]
    require_columns(unit_capacity, required, "대당 Capa")
    if unit_capacity.empty:
        return pd.DataFrame(columns=UNIT_CAPACITY_DIMENSIONS)
    result = unit_capacity.pivot(
        index=UNIT_CAPACITY_DIMENSIONS,
        columns="생산계획년월",
        values="대당 Capa",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in UNIT_CAPACITY_DIMENSIONS
    ]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in UNIT_CAPACITY_DIMENSIONS]
    )
    return result[[*UNIT_CAPACITY_DIMENSIONS, *month_columns]]


def _prepare_performance(data: pd.DataFrame) -> pd.DataFrame:
    table_name = "RQ_UPEH"
    required = [*PERFORMANCE_KEYS, "소요기준", "UPEH", "ST"]
    require_columns(data, required, table_name)
    result = data[required].copy()
    if result.empty:
        result["환산_UPEH"] = pd.Series(dtype="float64")
        return result
    normalize_month_column(result, table_name)
    strip_text_columns(result, [key for key in PERFORMANCE_KEYS if key != "생산계획년월"])
    result["Area_Name"] = result["Area_Name"].astype("string").str.strip()
    result["소요기준"] = result["소요기준"].astype("string").str.strip().str.upper()
    result = result.loc[~result["소요기준"].isin(UNIMPLEMENTED_BASES)].copy()
    if result.empty:
        result["환산_UPEH"] = pd.Series(dtype="float64")
        return result
    assert_complete(result, [*PERFORMANCE_KEYS, "소요기준"], table_name)
    result["Area_Name"] = normalize_area_name(result["Area_Name"], table_name)
    assert_unique_keys(result, [*PERFORMANCE_KEYS, "소요기준"], f"{table_name}의 연결 키가")

    upeh_values = pd.to_numeric(result["UPEH"], errors="coerce")
    st_values = pd.to_numeric(result["ST"], errors="coerce")
    main_rows = result["Area_Name"].eq("Main")
    mi_rows = result["Area_Name"].eq("MI")
    if upeh_values.loc[main_rows].isna().any():
        raise ValueError("RQ_UPEH의 Main 행에 UPEH 누락값 또는 숫자가 아닌 값이 있습니다.")
    if st_values.loc[mi_rows].isna().any():
        raise ValueError("RQ_UPEH의 MI 행에 ST 누락값 또는 숫자가 아닌 값이 있습니다.")
    if st_values.loc[mi_rows].le(0).any():
        raise ValueError("RQ_UPEH의 MI 행 ST 값은 0보다 커야 합니다.")

    result["환산_UPEH"] = upeh_values
    result.loc[mi_rows, "환산_UPEH"] = 3600.0 / st_values.loc[mi_rows]
    kea_rows = result["소요기준"].isin(["CHIP", "PKG"])
    result.loc[kea_rows, "환산_UPEH"] = result.loc[kea_rows, "환산_UPEH"] / 1000.0
    return result


def _join_reference(
    base: pd.DataFrame,
    reference: pd.DataFrame,
    keys: list[str],
    value_column: str,
    table_name: str,
    *,
    missing_value_default: float | None = None,
    assumed: dict[str, int] | None = None,
    assumed_months: dict[str, set[int]] | None = None,
) -> pd.DataFrame:
    """기준정보 한 표를 붙인다. **연결값이 없을 때의 처리가 표마다 다르다.**

    `missing_value_default` 가 **선언된 표만** 행이 없어도 그 값으로 이어 간다. 측정률
    둘이 그렇고, 1.0 은 「측정으로 깎이지 않는다」는 중립값이지 지어낸 수가 아니다 —
    빈 값과 `0` 은 이미 같은 결정을 받고 있다(`MEASUREMENT_RATIO_ZERO_DEFAULT`,
    `reference_transformer` 의 파생 단계, AGENTS.md 측정률 절). 행 부재만 하드 오류로
    남아 있던 것을 같은 선 안으로 들인다.

    **나머지 표는 그대로 멈춘다.** 가동률·편중률·모듈수·가동일수에는 중립값이 없다.
    1.0 을 넣으면 「가동률 100%」 같은 거짓 주장이 되고, 기준정보가 통째로 빠진 배포에서도
    숫자가 나와 버린다.

    가정한 건수는 `assumed` 에 쌓아 화면이 말하게 한다. **세지 않고 메우면 (c) 가 아니라
    (b) 가 된다** — 조용히 틀리는 경로를 하나 더 여는 것이다. 측정률은 분모라 실제가
    1 보다 작으면(표본은 모두 그렇다) 대당 Capa 과소 → 소요대수 과대 → 확보율 과소로
    **보수 쪽**이고, 1 보다 큰 경로에서만 낙관 쪽이다.
    """
    require_columns(reference, [*keys, value_column], table_name)
    prepared = reference[[*keys, value_column]].copy()
    if "생산계획년월" in keys:
        normalize_month_column(prepared, table_name)
    strip_text_columns(prepared, [key for key in keys if key != "생산계획년월"])
    assert_complete(prepared, keys, table_name)
    if "Area_Name" in keys:
        prepared["Area_Name"] = normalize_area_name(prepared["Area_Name"], table_name)
    assert_unique_keys(prepared, keys, f"{table_name}의 연결 키가")
    prepared[value_column] = _numeric_column(
        prepared,
        value_column,
        table_name,
        missing_value_default=missing_value_default,
    )
    result = base.merge(prepared, on=keys, how="left", validate="many_to_one")
    missing = result[value_column].isna()
    if not missing.any():
        return result
    if missing_value_default is None:
        examples = result.loc[missing, keys].drop_duplicates().head(5).to_dict("records")
        raise ValueError(f"{table_name} 연결값이 없는 대당 Capa 기준이 있습니다: {examples}")
    result[value_column] = result[value_column].fillna(missing_value_default)
    if assumed is not None:
        assumed[table_name] = assumed.get(table_name, 0) + int(missing.sum())
    if assumed_months is not None and "생산계획년월" in result.columns:
        months = pd.to_numeric(result.loc[missing, "생산계획년월"], errors="coerce").dropna()
        assumed_months.setdefault(table_name, set()).update(int(month) for month in months)
    return result


def _numeric_column(
    data: pd.DataFrame,
    column: str,
    table_name: str,
    *,
    missing_value_default: float | None = None,
) -> pd.Series:
    values = data[column]
    if missing_value_default is not None:
        blank = values.isna() | values.astype("string").str.strip().eq("").fillna(False)
        values = values.mask(blank, missing_value_default)
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{table_name}의 {column} 컬럼에 숫자가 아닌 값이 있습니다.")
    return numeric.astype("float64")


def _assert_positive(
    data: pd.DataFrame,
    column: str,
    table_name: str,
    keys: list[str],
) -> None:
    """0 이하 값을 막고, 어느 경로가 걸렸는지 건수와 예시 키·값으로 알린다."""
    nonpositive = data[column].le(0)
    if not bool(nonpositive.any()):
        return
    examples = data.loc[nonpositive, [*keys, column]].drop_duplicates().head(5).to_dict("records")
    raise ValueError(
        f"{table_name}의 {column} 값은 0보다 커야 합니다:"
        f" {int(nonpositive.sum()):,}건, 예시 {examples}"
    )


def _exclusion_rows(data: pd.DataFrame, mask: pd.Series, reason: str) -> pd.DataFrame:
    """Keep the joined reference values used by an excluded capacity row."""
    excluded = data.loc[mask].copy()
    excluded["제외사유"] = reason
    return excluded
