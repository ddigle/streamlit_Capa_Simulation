# Purpose: PKG and wafer monthly volume calculations.

"""PKG and wafer monthly volume calculations."""

from typing import Literal

import pandas as pd

from capa_simulation.services.display_order import DisplayOrderInput, apply_display_order
from capa_simulation.services.frame_contracts import require_columns

DemandBasis = Literal["PKG", "Chip", "Wafer", "Density"]

CLASSIFICATION_COLUMNS = ["양산구분", "제품정보", "Stack"]
LOAD_DETAIL_COLUMNS = ["Capa Code", "Customer", "CS"]
# 제품군을 가르는 컬럼. EDP-TSV 는 HBM 과 다른 규칙을 갖는다고 확인됐으므로(2026-09-05)
# 분류 키가 아니라 **계산이 참조하는 속성**으로 계획 프레임에 실어 나른다.
PRODUCT_TYPE_COLUMN = "제품타입"
EDP_PRODUCT_TYPE = "EDP-TSV"
HBM_PRODUCT_TYPE = "HBM"
# 계획에 딸려 다니지만 사용자가 격자에서 고칠 값이 아닌 속성들. 편집 왕복에서 떨어지므로
# `attach_plan_attributes` 로 되붙인다.
PLAN_ATTRIBUTE_COLUMNS = [PRODUCT_TYPE_COLUMN, "Pack Code"]

# 제품타입별 `WF 구분` 값 집합 (2026-09-05 확인). **두 목록은 일부러 따로 적는다.**
# 두 제품군이 `Top`·`Master` 라는 같은 이름을 공유하므로, `WF 구분` 만 보고 쓴 규칙은
# 의도와 무관하게 양쪽에 다 걸린다. 한쪽 규칙이 다른 쪽을 건드리지 않게 하려면 규칙을
# **(제품타입, WF 구분)** 으로 걸어야 한다. 한쪽을 고칠 때 다른 쪽이 따라 움직이면 안 되므로
# 공통 부분을 뽑아 공유하지 않는다.
HBM_WF_DIVISIONS = ("Buffer", "Core", "Top", "Dummy")
EDP_WF_DIVISIONS = ("Top", "Master", "Slave")
WF_DIVISIONS_BY_PRODUCT_TYPE = {
    HBM_PRODUCT_TYPE: HBM_WF_DIVISIONS,
    EDP_PRODUCT_TYPE: EDP_WF_DIVISIONS,
}
# Dummy 산식을 받는 `WF 구분`. EDP-TSV 에는 Dummy 가 없다.
DUMMY_DIVISIONS_BY_PRODUCT_TYPE = {
    HBM_PRODUCT_TYPE: ("Dummy",),
    EDP_PRODUCT_TYPE: (),
}
PLAN_EDITOR_DIMENSIONS = [
    "양산구분",
    "제품정보",
    "Stack",
    "Capa Code",
    "Customer",
    "CS",
]
PLAN_REQUIRED_COLUMNS = [
    "생산계획년월",
    *CLASSIFICATION_COLUMNS,
    "생산수량",
]
YIELD_KEYS = ["생산계획년월", "제품정보", "Stack", "WF 구분"]
YIELD_REQUIRED_COLUMNS = [*YIELD_KEYS, "EDS_수율", "BE_수율"]
YIELD_EDITOR_DIMENSIONS = ["수율 구분", "제품정보", "Stack", "WF 구분"]
YIELD_VALUE_COLUMNS = ["EDS_수율", "BE_수율"]
YIELD_DISPLAY_NAMES = {"EDS_수율": "EDS", "BE_수율": "BE"}
YIELD_INTERNAL_NAMES = {display: internal for internal, display in YIELD_DISPLAY_NAMES.items()}
CHIP_KEYS = ["제품정보", "Stack", "WF 구분"]
CHIP_REQUIRED_COLUMNS = [*CHIP_KEYS, "구분_Chip", "Net Die"]
DENSITY_KEYS = ["제품정보", "Stack", "WF 구분"]
DENSITY_REQUIRED_COLUMNS = [*DENSITY_KEYS, "구분_Chip", "구분_EQ"]

# 기준정보가 없어 계산에서 뺀 계획 행을 결과 프레임에 붙여 화면이 목록으로 보여준다.
# 예전에는 여기서 예외를 던져 계획 행 하나 때문에 페이지 전체가 멈췄다.
#
# 값은 DataFrame 이 아니라 레코드 튜플로 담는다. `attrs` 에 DataFrame 을 넣으면
# `pd.concat` 이 attrs 를 동등 비교하다가 "truth value of a DataFrame is ambiguous" 로
# 죽는다. 부하량 프레임들은 소요대수 계산에서 실제로 concat 된다.
LOAD_EXCLUSIONS_ATTR = "excluded_load_rows"
LOAD_EXCLUSION_COLUMNS = ["생산계획년월", "제품정보", "Stack", "WF 구분", "누락 기준정보"]


def plan_to_edit_table(plan: pd.DataFrame, display_order: DisplayOrderInput = None) -> pd.DataFrame:
    """Pivot the default Long PKG plan into an editable month-column table."""
    required = ["생산계획년월", *PLAN_EDITOR_DIMENSIONS, "생산수량"]
    require_columns(plan, required, "RQ_PKG_PLAN")
    prepared = _normalize_text(plan[required], PLAN_EDITOR_DIMENSIONS)
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared = _to_numeric(prepared, ["생산수량"], "RQ_PKG_PLAN")
    prepared["생산수량"] = prepared["생산수량"].fillna(0.0)

    if prepared[["생산계획년월", *PLAN_EDITOR_DIMENSIONS]].isna().any(axis=None):
        raise ValueError("RQ_PKG_PLAN의 편집 테이블 식별 컬럼에 누락값이 있습니다.")

    duplicate_keys = [*PLAN_EDITOR_DIMENSIONS, "생산계획년월"]
    duplicated = prepared.duplicated(duplicate_keys, keep=False)
    if duplicated.any():
        example = (
            prepared.loc[duplicated, duplicate_keys].drop_duplicates().head(5).to_dict("records")
        )
        raise ValueError(f"RQ_PKG_PLAN의 월별 계획 키가 중복되었습니다: {example}")

    result = prepared.pivot(
        index=PLAN_EDITOR_DIMENSIONS,
        columns="생산계획년월",
        values="생산수량",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    result[raw_month_columns] = result[raw_month_columns].fillna(0.0)
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in PLAN_EDITOR_DIMENSIONS]
    )
    result = result[[*PLAN_EDITOR_DIMENSIONS, *month_columns]]
    return apply_display_order(result, display_order, "부하량", "PKG PLAN")


def plan_from_edit_table(plan_table: pd.DataFrame) -> pd.DataFrame:
    """Convert the edited month-column plan back to the calculation Long format."""
    require_columns(plan_table, PLAN_EDITOR_DIMENSIONS, "PKG PLAN 편집값")
    month_columns = [
        column for column in plan_table.columns if column not in PLAN_EDITOR_DIMENSIONS
    ]
    invalid_months = [
        column for column in month_columns if not str(column).isdigit() or len(str(column)) != 6
    ]
    if invalid_months:
        raise ValueError(f"PKG PLAN의 월 컬럼은 YYYYMM 형식이어야 합니다: {invalid_months}")

    long_plan = plan_table.melt(
        id_vars=PLAN_EDITOR_DIMENSIONS,
        value_vars=month_columns,
        var_name="생산계획년월",
        value_name="생산수량",
    )
    long_plan["생산계획년월"] = pd.to_numeric(long_plan["생산계획년월"], errors="raise").astype(
        "Int64"
    )
    long_plan = _to_numeric(long_plan, ["생산수량"], "PKG PLAN 편집값")
    long_plan["생산수량"] = long_plan["생산수량"].fillna(0.0)
    if long_plan["생산수량"].lt(0).any():
        raise ValueError("PKG PLAN 생산수량은 0 이상이어야 합니다.")
    # 수량 0 행을 여기서 버리면 그 제품이 편집 격자에서 사라져 다시 물량을 넣을 수 없고,
    # 내려받은 CSV 와 행 수가 달라져 붙여넣기가 어긋난다. 0 은 "이 달 계획 없음" 이라는
    # 사용자의 입력이므로 그대로 보존하고, 계산 경계(_prepare_plan)에서 제외한다.
    return long_plan.sort_values(["생산계획년월", *PLAN_EDITOR_DIMENSIONS]).reset_index(drop=True)


def attach_plan_attributes(long_plan: pd.DataFrame, source_plan: pd.DataFrame) -> pd.DataFrame:
    """편집 격자가 들고 있지 않은 계획 속성을 원래 계획에서 되붙인다.

    격자는 `PLAN_EDITOR_DIMENSIONS` 와 월 컬럼만 보여 준다. `제품타입`·`Pack Code` 는
    사용자가 고칠 값이 아니라 제품에 딸린 속성이라 격자에 두지 않았는데, 되붙이지 않으면
    변경사항을 적용할 때마다 조용히 사라진다. 그러면 `replace_month_range` 가
    "편집값에 원본 컬럼이 없습니다" 로 막고, 화면에는 오류만 뜬 채 적용이 안 된다.

    격자에 없던 새 행은 붙일 원본이 없어 결측으로 남는다. 그 상태로 EDP 를 판별하려 하면
    `filter_edp_plan` 이 어느 제품인지 짚어 알려 준다 — 조용히 넘어가지 않는다.
    """
    attributes = [column for column in PLAN_ATTRIBUTE_COLUMNS if column in source_plan.columns]
    if not attributes:
        return long_plan
    keys = [column for column in PLAN_EDITOR_DIMENSIONS if column in source_plan.columns]
    lookup = _normalize_text(source_plan[[*keys, *attributes]], keys).drop_duplicates(subset=keys)
    merged = _normalize_text(long_plan, keys).merge(
        lookup, on=keys, how="left", validate="many_to_one"
    )
    return merged


def yield_to_edit_table(
    yield_data: pd.DataFrame, display_order: DisplayOrderInput = None
) -> pd.DataFrame:
    """Pivot Long yield data into editable EDS/BE rows with month columns."""
    require_columns(yield_data, YIELD_REQUIRED_COLUMNS, "RQ_YLD")
    prepared = _normalize_text(yield_data[YIELD_REQUIRED_COLUMNS], YIELD_KEYS[1:])
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared = _to_numeric(prepared, YIELD_VALUE_COLUMNS, "RQ_YLD")

    if prepared[YIELD_KEYS].isna().any(axis=None):
        raise ValueError("RQ_YLD의 연결 키에 누락값이 있습니다.")
    if prepared[YIELD_VALUE_COLUMNS].isna().any(axis=None):
        raise ValueError("RQ_YLD의 EDS_수율 또는 BE_수율에 누락값이 있습니다.")
    _assert_unique(prepared, YIELD_KEYS, "RQ_YLD")
    _validate_yield_range(prepared, "RQ_YLD")

    long_yield = prepared.melt(
        id_vars=YIELD_KEYS,
        value_vars=YIELD_VALUE_COLUMNS,
        var_name="수율 구분",
        value_name="수율",
    )
    long_yield["수율 구분"] = long_yield["수율 구분"].replace(YIELD_DISPLAY_NAMES)
    result = long_yield.pivot(
        index=YIELD_EDITOR_DIMENSIONS,
        columns="생산계획년월",
        values="수율",
    ).reset_index()
    result.columns.name = None
    raw_month_columns = [
        column for column in result.columns if column not in YIELD_EDITOR_DIMENSIONS
    ]
    result = result.rename(columns={column: str(int(column)) for column in raw_month_columns})
    month_columns = sorted(
        [column for column in result.columns if column not in YIELD_EDITOR_DIMENSIONS]
    )
    result = result[[*YIELD_EDITOR_DIMENSIONS, *month_columns]]
    return apply_display_order(
        result,
        display_order,
        "부하량",
        "수율",
        value_aliases={"수율 구분": YIELD_DISPLAY_NAMES},
    )


def yield_from_edit_table(yield_table: pd.DataFrame) -> pd.DataFrame:
    """Convert edited month-column yields back to the RQ_YLD Long format."""
    require_columns(yield_table, YIELD_EDITOR_DIMENSIONS, "수율 편집값")
    month_columns = [
        column for column in yield_table.columns if column not in YIELD_EDITOR_DIMENSIONS
    ]
    invalid_months = [
        column for column in month_columns if not str(column).isdigit() or len(str(column)) != 6
    ]
    if invalid_months:
        raise ValueError(f"수율의 월 컬럼은 YYYYMM 형식이어야 합니다: {invalid_months}")

    prepared = _normalize_text(yield_table, YIELD_EDITOR_DIMENSIONS)
    invalid_types = sorted(set(prepared["수율 구분"].dropna()) - set(YIELD_INTERNAL_NAMES))
    if invalid_types:
        raise ValueError(f"지원하지 않는 수율 구분이 있습니다: {invalid_types}")

    long_yield = prepared.melt(
        id_vars=YIELD_EDITOR_DIMENSIONS,
        value_vars=month_columns,
        var_name="생산계획년월",
        value_name="수율",
    )
    long_yield["수율 구분"] = long_yield["수율 구분"].replace(YIELD_INTERNAL_NAMES)
    long_yield["생산계획년월"] = pd.to_numeric(long_yield["생산계획년월"], errors="raise").astype(
        "Int64"
    )
    long_yield = _to_numeric(long_yield, ["수율"], "수율 편집값")
    long_yield = long_yield.dropna(subset=["수율"])

    duplicated = long_yield.duplicated(["생산계획년월", *YIELD_EDITOR_DIMENSIONS], keep=False)
    if duplicated.any():
        raise ValueError("수율 편집값의 월별 연결 키가 중복되었습니다.")

    result = long_yield.pivot(
        index=YIELD_KEYS,
        columns="수율 구분",
        values="수율",
    ).reset_index()
    result.columns.name = None
    require_columns(result, YIELD_REQUIRED_COLUMNS, "수율 편집값")
    if result[YIELD_VALUE_COLUMNS].isna().any(axis=None):
        raise ValueError("동일한 기준에는 EDS_수율과 BE_수율이 모두 필요합니다.")
    _validate_yield_range(result, "수율 편집값")
    return result[YIELD_REQUIRED_COLUMNS].sort_values(YIELD_KEYS).reset_index(drop=True)


def _normalize_text(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    normalized = data.copy()
    for column in columns:
        normalized[column] = normalized[column].astype("string").str.strip()
    return normalized


def _to_numeric(data: pd.DataFrame, columns: list[str], table_name: str) -> pd.DataFrame:
    converted = data.copy()
    for column in columns:
        original = converted[column]
        converted[column] = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & converted[column].isna()
        if invalid.any():
            raise ValueError(f"{table_name}.{column}에 숫자가 아닌 값이 있습니다.")
    return converted


def _assert_unique(data: pd.DataFrame, keys: list[str], table_name: str) -> None:
    duplicated = data.duplicated(keys, keep=False)
    if duplicated.any():
        example = data.loc[duplicated, keys].drop_duplicates().head(5).to_dict("records")
        raise ValueError(f"{table_name} 연결 키가 중복되었습니다: {example}")


def _validate_yield_range(data: pd.DataFrame, table_name: str) -> None:
    invalid_rate = (
        data["EDS_수율"].le(0)
        | data["EDS_수율"].gt(1)
        | data["BE_수율"].le(0)
        | data["BE_수율"].gt(1)
    )
    if invalid_rate.any():
        raise ValueError(f"{table_name}의 수율은 0 초과 100% 이하여야 합니다.")


def _prepare_plan(plan: pd.DataFrame) -> pd.DataFrame:
    require_columns(plan, PLAN_REQUIRED_COLUMNS, "RQ_PKG_PLAN")
    available_detail_columns = [column for column in LOAD_DETAIL_COLUMNS if column in plan.columns]
    # 제품타입은 분류 키가 아니지만 계산 분기가 참조하므로 있으면 그대로 들고 간다.
    carried = [PRODUCT_TYPE_COLUMN] if PRODUCT_TYPE_COLUMN in plan.columns else []
    prepared_columns = [*PLAN_REQUIRED_COLUMNS, *available_detail_columns, *carried]
    prepared = _normalize_text(
        plan[prepared_columns],
        [*CLASSIFICATION_COLUMNS, *available_detail_columns, *carried],
    )
    prepared["생산계획년월"] = pd.to_numeric(prepared["생산계획년월"], errors="coerce").astype(
        "Int64"
    )
    prepared = _to_numeric(prepared, ["생산수량"], "RQ_PKG_PLAN")

    missing_keys = prepared[["생산계획년월", *CLASSIFICATION_COLUMNS]].isna().any(axis=1)
    if missing_keys.any():
        raise ValueError("RQ_PKG_PLAN에 월별 물량 분류 키가 누락된 행이 있습니다.")
    return drop_unplanned_rows(prepared)


def drop_unplanned_rows(plan: pd.DataFrame) -> pd.DataFrame:
    """계산에서 제외할 수량 0 행을 걷어낸다.

    편집 격자는 계획이 없는 달도 행으로 들고 있어야 사용자가 다시 물량을 넣을 수 있다.
    그러나 계산은 모든 계획 행에 대해 RQ_CHIP_QTY·RQ_YLD 매칭을 요구하므로, 계획이 없는
    제품까지 기준정보를 갖출 것을 강요하게 된다. 그래서 계산 입구에서만 제외한다.
    """
    quantities = pd.to_numeric(plan["생산수량"], errors="coerce").fillna(0.0)
    return plan.loc[quantities.gt(0)].copy()


def _prepare_load_base(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Expand each plan by WF type and attach the matching yield and chip standards."""
    prepared_plan = _prepare_plan(plan)
    require_columns(yield_data, YIELD_REQUIRED_COLUMNS, "RQ_YLD")
    require_columns(chip_qty, CHIP_REQUIRED_COLUMNS, "RQ_CHIP_QTY")

    prepared_yield = _normalize_text(yield_data[YIELD_REQUIRED_COLUMNS], YIELD_KEYS[1:])
    prepared_yield["생산계획년월"] = pd.to_numeric(
        prepared_yield["생산계획년월"], errors="coerce"
    ).astype("Int64")
    prepared_yield = _to_numeric(prepared_yield, ["EDS_수율", "BE_수율"], "RQ_YLD")

    prepared_chip = _normalize_text(chip_qty[CHIP_REQUIRED_COLUMNS], CHIP_KEYS)
    prepared_chip = _to_numeric(prepared_chip, ["구분_Chip", "Net Die"], "RQ_CHIP_QTY")

    _assert_unique(prepared_yield, YIELD_KEYS, "RQ_YLD")
    _assert_unique(prepared_chip, CHIP_KEYS, "RQ_CHIP_QTY")

    expanded = prepared_plan.merge(
        prepared_chip,
        on=["제품정보", "Stack"],
        how="left",
        validate="many_to_many",
        indicator="_chip_merge",
    )
    chip_missing = expanded["_chip_merge"] != "both"
    exclusions = [_load_exclusion_rows(expanded.loc[chip_missing], "RQ_CHIP_QTY")]
    expanded = expanded.loc[~chip_missing].drop(columns="_chip_merge")

    calculation = expanded.merge(
        prepared_yield,
        on=YIELD_KEYS,
        how="left",
        validate="many_to_one",
        indicator="_yield_merge",
    )
    yield_missing = calculation["_yield_merge"] != "both"
    exclusions.append(_load_exclusion_rows(calculation.loc[yield_missing], "RQ_YLD"))
    calculation = calculation.loc[~yield_missing].drop(columns="_yield_merge")

    _validate_yield_range(calculation, "RQ_YLD")
    if calculation["Net Die"].le(0).any():
        raise ValueError("Net Die는 0보다 커야 합니다.")
    if calculation["구분_Chip"].lt(0).any():
        raise ValueError("구분_Chip은 0 이상이어야 합니다.")

    calculation.attrs[LOAD_EXCLUSIONS_ATTR] = _merge_load_exclusions(exclusions)
    return calculation


def _load_exclusion_rows(
    unmatched: pd.DataFrame, table_name: str
) -> tuple[tuple[object, ...], ...]:
    """조인에 실패한 계획 행을 "무엇이 없어서 빠졌는지" 레코드로 정리한다."""
    if unmatched.empty:
        return ()
    columns = [column for column in LOAD_EXCLUSION_COLUMNS[:-1] if column in unmatched.columns]
    rows = unmatched[columns].drop_duplicates()
    return tuple(
        (*(record.get(column) for column in LOAD_EXCLUSION_COLUMNS[:-1]), table_name)
        for record in rows.to_dict("records")
    )


def _merge_load_exclusions(
    groups: list[tuple[tuple[object, ...], ...]],
) -> tuple[tuple[object, ...], ...]:
    merged: list[tuple[object, ...]] = []
    for group in groups:
        for row in group:
            if row not in merged:
                merged.append(row)
    return tuple(merged)


def calculate_chip_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate Top/Core/Buffer/Slave/Master and Dummy chip volume in Kea."""
    return _calculate_chip_load_from_base(_prepare_load_base(plan, yield_data, chip_qty))


def calculate_chip_and_wafer_loads(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate Chip and Wafer loads from one shared validated join result."""
    calculation = _prepare_load_base(plan, yield_data, chip_qty)
    return (
        _calculate_chip_load_from_base(calculation),
        _calculate_wafer_load_from_base(calculation),
    )


def carry_load_exclusions(source: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    """제외 목록을 결과 프레임에 이어붙인다. pandas 연산에서 attrs 는 쉽게 사라진다."""
    target.attrs[LOAD_EXCLUSIONS_ATTR] = source.attrs.get(LOAD_EXCLUSIONS_ATTR, ())
    return target


def load_exclusions(data: pd.DataFrame) -> pd.DataFrame:
    """기준정보가 없어 계산에서 빠진 계획 행 목록을 표로 돌려준다."""
    excluded = data.attrs.get(LOAD_EXCLUSIONS_ATTR)
    if not excluded:
        return pd.DataFrame(columns=LOAD_EXCLUSION_COLUMNS)
    return pd.DataFrame(list(excluded), columns=LOAD_EXCLUSION_COLUMNS)


def _dummy_mask(calculation: pd.DataFrame) -> pd.Series:
    """Dummy 산식을 받을 행을 (제품타입, WF 구분) 으로 고른다.

    `WF 구분` 만 보고 고르면 두 제품군이 공유하는 이름 때문에 한쪽 규칙이 다른 쪽에
    적용된다. 지금은 Dummy 가 HBM 에만 있어 결과가 같지만, 규칙을 이름 하나에 걸어 두면
    나중에 EDP 쪽 규칙을 넣을 때 HBM 이 조용히 따라 움직인다.

    `제품타입` 이 없는 프레임(제품타입 도입 이전 경로)은 예전처럼 이름만 보고 고른다.
    """
    division = calculation["WF 구분"].astype("string").str.strip().str.casefold()
    if PRODUCT_TYPE_COLUMN not in calculation.columns:
        declared = {
            name.casefold() for names in DUMMY_DIVISIONS_BY_PRODUCT_TYPE.values() for name in names
        }
        return division.isin(declared).fillna(False)

    product_type = calculation[PRODUCT_TYPE_COLUMN].astype("string").str.strip()
    mask = pd.Series(False, index=calculation.index)
    for declared_type, dummy_divisions in DUMMY_DIVISIONS_BY_PRODUCT_TYPE.items():
        if not dummy_divisions:
            continue
        names = {name.casefold() for name in dummy_divisions}
        mask |= product_type.eq(declared_type) & division.isin(names).fillna(False)
    return mask


def _calculate_chip_load_from_base(load_base: pd.DataFrame) -> pd.DataFrame:
    calculation = load_base.copy()
    calculation["물량"] = (
        calculation["생산수량"] * calculation["구분_Chip"] / calculation["BE_수율"]
    )
    is_dummy = _dummy_mask(calculation)
    calculation.loc[is_dummy, "물량"] = (
        calculation.loc[is_dummy, "생산수량"]
        * calculation.loc[is_dummy, "구분_Chip"]
        / calculation.loc[is_dummy, "EDS_수율"]
        / calculation.loc[is_dummy, "BE_수율"]
        * (1 - calculation.loc[is_dummy, "EDS_수율"])
    )
    return carry_load_exclusions(load_base, calculation)


def calculate_wafer_load(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate regular and Dummy wafer volume in sheets."""
    return _calculate_wafer_load_from_base(_prepare_load_base(plan, yield_data, chip_qty))


def _calculate_wafer_load_from_base(load_base: pd.DataFrame) -> pd.DataFrame:
    calculation = load_base.copy()
    calculation["물량"] = (
        calculation["생산수량"]
        * 1_000
        * calculation["구분_Chip"]
        / calculation["EDS_수율"]
        / calculation["BE_수율"]
        / calculation["Net Die"]
    )
    is_dummy = _dummy_mask(calculation)
    calculation.loc[is_dummy, "물량"] *= 1 - calculation.loc[is_dummy, "EDS_수율"]
    return carry_load_exclusions(load_base, calculation)


def calculate_density_load(plan: pd.DataFrame, density_data: pd.DataFrame) -> pd.DataFrame:
    """Calculate product density by capacity-bearing WF type in 100M Gb."""
    prepared_plan = _prepare_plan(plan)
    require_columns(density_data, DENSITY_REQUIRED_COLUMNS, "RQ_CHIP_EQ")

    prepared_density = _normalize_text(density_data[DENSITY_REQUIRED_COLUMNS], DENSITY_KEYS)
    prepared_density = _to_numeric(prepared_density, ["구분_Chip", "구분_EQ"], "RQ_CHIP_EQ")

    if prepared_density[DENSITY_KEYS].isna().any(axis=None):
        raise ValueError("RQ_CHIP_EQ의 연결 키에 누락값이 있습니다.")
    if prepared_density[["구분_Chip", "구분_EQ"]].isna().any(axis=None):
        raise ValueError("RQ_CHIP_EQ의 구분_Chip 또는 구분_EQ에 누락값이 있습니다.")
    _assert_unique(prepared_density, DENSITY_KEYS, "RQ_CHIP_EQ")

    if prepared_density["구분_Chip"].le(0).any():
        raise ValueError("RQ_CHIP_EQ.구분_Chip은 0보다 커야 합니다.")
    if prepared_density["구분_EQ"].le(0).any():
        raise ValueError("RQ_CHIP_EQ.구분_EQ는 0보다 커야 합니다.")

    calculation = prepared_plan.merge(
        prepared_density,
        on=["제품정보", "Stack"],
        how="left",
        validate="many_to_many",
        indicator="_density_merge",
    )
    # Chip·Wafer 경로와 같은 처리다. 예전에는 여기서 예외를 던져 계획 행 하나 때문에
    # Density 환산은 물론 HOME 대시보드까지 통째로 멈췄다. 용량이 발생하지 않는 제품이나
    # `구분_EQ` 미등록 신규 제품이 계획에 한 줄만 들어와도 그렇게 된다.
    density_missing = calculation["_density_merge"] != "both"
    exclusions = _load_exclusion_rows(calculation.loc[density_missing], "RQ_CHIP_EQ")
    calculation = calculation.loc[~density_missing].drop(columns="_density_merge")
    calculation["물량"] = (
        calculation["생산수량"] * calculation["구분_Chip"] * calculation["구분_EQ"] / 100_000
    )
    calculation.attrs[LOAD_EXCLUSIONS_ATTR] = exclusions
    return calculation


def _pivot_monthly(
    data: pd.DataFrame,
    detailed: bool,
    display_order: DisplayOrderInput = None,
) -> pd.DataFrame:
    classification_columns = [*CLASSIFICATION_COLUMNS]
    if detailed:
        classification_columns.append("WF 구분")
    grouped = (
        data.groupby(["생산계획년월", *classification_columns], as_index=False, dropna=False)[
            ["물량"]
        ]
        .sum()
        .sort_values([*classification_columns, "생산계획년월"])
    )
    pivoted = grouped.pivot(
        index=classification_columns,
        columns="생산계획년월",
        values="물량",
    ).fillna(0)
    pivoted.columns = [str(int(month)) for month in pivoted.columns]
    return apply_display_order(pivoted.reset_index(), display_order, "부하량", "환산")


def build_monthly_volume(
    plan: pd.DataFrame,
    yield_data: pd.DataFrame,
    chip_qty: pd.DataFrame,
    demand_basis: DemandBasis,
    detailed: bool = False,
    density_data: pd.DataFrame | None = None,
    display_order: DisplayOrderInput = None,
) -> pd.DataFrame:
    """Return a monthly matrix grouped by production class, product, and stack."""
    prepared_plan = _prepare_plan(plan)
    if demand_basis == "PKG":
        volume = prepared_plan.rename(columns={"생산수량": "물량"})
        if detailed:
            volume["WF 구분"] = "PKG"
        return _pivot_monthly(volume, detailed, display_order)
    if demand_basis == "Chip":
        chip_load = calculate_chip_load(prepared_plan, yield_data, chip_qty)
        return carry_load_exclusions(chip_load, _pivot_monthly(chip_load, detailed, display_order))
    if demand_basis == "Wafer":
        wafer_load = calculate_wafer_load(prepared_plan, yield_data, chip_qty)
        return carry_load_exclusions(
            wafer_load, _pivot_monthly(wafer_load, detailed, display_order)
        )
    if demand_basis == "Density":
        if density_data is None:
            raise ValueError("Density 계산에 RQ_CHIP_EQ 기준정보가 필요합니다.")
        density_load = calculate_density_load(prepared_plan, density_data)
        return carry_load_exclusions(
            density_load, _pivot_monthly(density_load, detailed, display_order)
        )
    raise ValueError(f"지원하지 않는 소요기준입니다: {demand_basis}")


def filter_edp_plan(plan: pd.DataFrame, include_edp: bool) -> pd.DataFrame:
    """EDP 토글이 꺼져 있는 동안 `제품타입` 이 EDP-TSV 인 계획 행을 환산에서 뺀다.

    **판별은 `제품타입` 이다** (2026-09-05 확인). 예전에는 `제품정보` 에 `DDR` 이 들어
    있는지로 판별했는데, 그것은 개발 표본에서 EDP-TSV 제품이 `A1a-DDR5` 하나뿐이라
    우연히 맞아떨어진 것이었다. 실제로 EDP-TSV 제품명에는 전부 DDR4 또는 DDR5 가
    들어 있지만, 그 반대(이름에 DDR 이 든 비-EDP 제품)는 보장되지 않는다. 제품군을 정하는
    것은 이름이 아니라 `제품타입` 컬럼이다.

    토글이 켜져 있으면 아무것도 가리지 않으므로 판별 자체가 필요 없다. 그래서 컬럼 요구도
    그때는 하지 않는다 — 판단이 필요한 순간에만 근거를 요구한다.
    """
    if include_edp:
        return plan.copy()
    require_columns(plan, [PRODUCT_TYPE_COLUMN], "RQ_PKG_PLAN")
    product_type = plan[PRODUCT_TYPE_COLUMN].astype("string").str.strip()
    unknown = product_type.isna() | product_type.eq("")
    if unknown.any():
        examples = sorted(
            {str(value) for value in plan.loc[unknown, "제품정보"].dropna().unique()[:5]}
        )
        raise ValueError(
            "제품타입이 비어 있어 EDP 여부를 판단할 수 없습니다"
            f"({unknown.sum()}행, 예: {', '.join(examples) or '제품정보 없음'}). "
            "기준정보를 다시 등록하거나 EDP 를 포함해 조회하세요."
        )
    return plan.loc[product_type.ne(EDP_PRODUCT_TYPE)].copy()


def product_type_of(plan: pd.DataFrame) -> pd.Series:
    """계획 행의 제품군을 정규화해 돌려준다.

    EDP-TSV 와 HBM 은 앞으로 서로 다른 로직을 탄다. 판정을 한 곳에 모아 두어야 분기가
    늘어도 갈라지지 않는다.
    """
    require_columns(plan, [PRODUCT_TYPE_COLUMN], "RQ_PKG_PLAN")
    return plan[PRODUCT_TYPE_COLUMN].astype("string").str.strip()
