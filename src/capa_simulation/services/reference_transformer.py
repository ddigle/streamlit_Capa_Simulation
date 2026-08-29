"""Pandas equivalents of the XLSB Power Query reference-table transformations."""

from __future__ import annotations

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataContract,
    load_core_data_contract,
    normalize_core_data,
)

ACTIVE_CORE_COLUMNS = (
    "제품타입",
    "U/PKG",
    "PKG1",
    "LOB Code",
    "Capa Code",
    "제품정보",
    "생산계획년월",
    "생산수량",
    "Stack",
    "Customer",
    "Pack Code",
    "CS",
    "D_EQ",
    "WF 구분",
    "구분_Chip",
    "구분_EQ",
    "Plan_Chip(K개)",
    "CHIP",
    "Net Die",
    "Month",
    "8H 환산 계획(K개)",
    "WF수(매)",
    "EQ(억Gb)",
    "계획기초정보여부",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "Para",
    "Step수",
    "CAPA_RUN_RATE",
    "소요기준",
    "RUN_DAY",
    "일 필요",
    "UPEH",
    "ST",
    "Lot 측정률",
    "WF측정률",
    "EDS_수율",
    "BE_수율",
    "CUM_수율",
    "GOOD_DIE",
    "TEST WF수(매)",
    "Shot Time",
    "Shot수",
    "Index Time",
    "모듈수",
    "Side반영률",
    "편중률",
    "설비보유",
    "설비대수변화관리",
    "설비대여평가",
    "설비대여평가항목",
    "설비대여평가DESC",
    "MCP_Chip_Ratio",
    "소요대수",
    "시뮬레이션 누락여부",
)


def build_q_core_data(
    source: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> pd.DataFrame:
    """Apply Q_Core_Data types, active columns, and derived columns."""
    normalized = normalize_core_data(source, contract)
    core = normalized.loc[:, list(ACTIVE_CORE_COLUMNS)].copy()
    # BigDataQuery represents an embedded blank in product names as the literal
    # marker "*_".  Normalize it before any RQ key is derived so every table
    # receives the same product key.
    core["제품정보"] = core["제품정보"].str.replace("*_", " ", regex=False)
    core["양산구분"] = pd.Series(pd.NA, index=core.index, dtype="string")
    core.loc[core["CS"].isin(["MP", "CS"]), "양산구분"] = "양산"
    core.loc[core["CS"].eq("ER"), "양산구분"] = "ER"
    core["가용대수"] = core["설비보유"] - core["설비대여평가"]
    return core


def build_reference_tables(
    source: pd.DataFrame,
    display_order: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the 16 RQ tables from one Core Data snapshot and display-order input."""
    selected_contract = contract or load_core_data_contract()
    core = build_q_core_data(source, selected_contract)
    tables = {
        "RQ_PKG_PLAN": _rq_pkg_plan(core, selected_contract),
        "RQ_YLD": _rq_yld(core, selected_contract),
        "RQ_CHIP_QTY": _rq_chip_qty(core, selected_contract),
        "RQ_CHIP_EQ": _rq_chip_eq(core, selected_contract),
        "RQ_DISPLAY_ORDER": transform_display_order(display_order),
        "RQ_EQP_OWN": _monthly_process_table(
            core,
            "RQ_EQP_OWN",
            "설비보유",
            selected_contract,
        ),
        "RQ_EQP_LENT": _monthly_process_table(
            core,
            "RQ_EQP_LENT",
            "설비대여평가",
            selected_contract,
        ),
        "RQ_EQP_AVBL": _monthly_process_table(
            core,
            "RQ_EQP_AVBL",
            "가용대수",
            selected_contract,
        ),
        "RQ_UPEH": _rq_upeh(core, selected_contract),
        "RQ_RUN_RATE": _monthly_process_class_table(
            core,
            "RQ_RUN_RATE",
            "CAPA_RUN_RATE",
            selected_contract,
        ),
        "RQ_VITAL": _monthly_process_class_table(
            core,
            "RQ_VITAL",
            "편중률",
            selected_contract,
        ),
        "RQ_MODULE": _rq_module(core, selected_contract),
        "RQ_RUN_DAY": _monthly_process_table(
            core,
            "RQ_RUN_DAY",
            "RUN_DAY",
            selected_contract,
        ),
        "RQ_LOT_RATIO": _measurement_ratio_table(
            core,
            "RQ_LOT_RATIO",
            "Lot 측정률",
            selected_contract,
        ),
        "RQ_WF_RATIO": _measurement_ratio_table(
            core,
            "RQ_WF_RATIO",
            "WF측정률",
            selected_contract,
        ),
        "RQ_REQB": _rq_reqb(core),
    }
    return tables


def transform_display_order(source: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "페이지 구분",
        "탭 구분",
        "정렬우선순위",
        "분류컬럼",
        "정렬방식",
        "분류값",
        "값표시순서",
        "활성여부",
    ]
    _require_columns(source, columns, "RQ_DISPLAY_ORDER")
    result = source.loc[:, columns].copy()
    text_columns = [
        "페이지 구분",
        "탭 구분",
        "분류컬럼",
        "정렬방식",
        "분류값",
        "활성여부",
    ]
    for column in text_columns:
        result[column] = result[column].astype("string").str.strip()
    result["활성여부"] = result["활성여부"].str.upper()
    result["정렬우선순위"] = _nullable_integer(result["정렬우선순위"], "정렬우선순위")
    result["값표시순서"] = _nullable_integer(result["값표시순서"], "값표시순서")

    required_text_columns = [
        "페이지 구분",
        "탭 구분",
        "분류컬럼",
        "정렬방식",
        "활성여부",
    ]
    required_text_valid = pd.Series(True, index=result.index, dtype=bool)
    for column in required_text_columns:
        required_text_valid &= result[column].notna() & result[column].ne("")
    allowed_sort = result["정렬방식"].isin(["사용자지정", "오름차순", "내림차순"])
    allowed_active = result["활성여부"].isin(["Y", "N"])
    custom = result["정렬방식"].eq("사용자지정")
    custom_valid = (~custom) | (
        result["분류값"].notna() & result["분류값"].ne("") & result["값표시순서"].notna()
    )
    mask = (
        required_text_valid
        & result["정렬우선순위"].notna()
        & allowed_sort
        & allowed_active
        & custom_valid
    )
    return result.loc[mask].reset_index(drop=True)


def _rq_pkg_plan(core: pd.DataFrame, contract: CoreDataContract) -> pd.DataFrame:
    columns = [
        "생산계획년월",
        "양산구분",
        "CS",
        "제품정보",
        "Stack",
        "Capa Code",
        "Customer",
        "생산수량",
    ]
    result = core.loc[core["계획기초정보여부"].eq("Y"), columns].copy()
    return _validated_distinct(result, "RQ_PKG_PLAN", contract)


def _rq_yld(core: pd.DataFrame, contract: CoreDataContract) -> pd.DataFrame:
    columns = ["생산계획년월", "제품정보", "Stack", "WF 구분", "EDS_수율", "BE_수율"]
    return _validated_distinct(core.loc[:, columns].copy(), "RQ_YLD", contract)


def _rq_chip_qty(core: pd.DataFrame, contract: CoreDataContract) -> pd.DataFrame:
    columns = ["제품정보", "Stack", "WF 구분", "구분_Chip", "Net Die"]
    return _validated_distinct(core.loc[:, columns].copy(), "RQ_CHIP_QTY", contract)


def _rq_chip_eq(core: pd.DataFrame, contract: CoreDataContract) -> pd.DataFrame:
    columns = ["제품정보", "Stack", "WF 구분", "구분_Chip", "구분_EQ"]
    result = core.loc[core["구분_EQ"].notna(), columns].copy()
    return _validated_distinct(result, "RQ_CHIP_EQ", contract)


def _monthly_process_table(
    core: pd.DataFrame,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
) -> pd.DataFrame:
    columns = ["생산계획년월", "공정", value_column]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return _validated_distinct(result, table_name, contract)


def _monthly_process_class_table(
    core: pd.DataFrame,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
) -> pd.DataFrame:
    columns = ["생산계획년월", "공정", "양산구분", value_column]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return _validated_distinct(result, table_name, contract)


def _rq_upeh(core: pd.DataFrame, contract: CoreDataContract) -> pd.DataFrame:
    columns = [
        "생산계획년월",
        "Area_Name",
        "공정",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
        "소요기준",
        "UPEH",
        "ST",
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return _validated_distinct(result, "RQ_UPEH", contract)


def _rq_module(core: pd.DataFrame, contract: CoreDataContract) -> pd.DataFrame:
    result = _nonblank_rows(core.loc[:, ["공정", "모듈수"]].copy(), "공정")
    return _validated_distinct(result, "RQ_MODULE", contract)


def _measurement_ratio_table(
    core: pd.DataFrame,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
) -> pd.DataFrame:
    columns = [
        "생산계획년월",
        "공정",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
        value_column,
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    result = _validated_distinct(result, table_name, contract)
    result[value_column] = result[value_column].fillna(1.0)
    return result


def _rq_reqb(core: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "생산계획년월",
        "Area_Name",
        "공정",
        "양산구분",
        "제품정보",
        "Stack",
        "Capa Code",
        "Customer",
        "CS",
        "WF 구분",
        "STEP_SEQ",
        "MCP_SEQ",
        "소요기준",
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "Area_Name")
    required = [
        "생산계획년월",
        "Area_Name",
        "공정",
        "양산구분",
        "제품정보",
        "Stack",
        "Capa Code",
        "Customer",
        "CS",
        "WF 구분",
        "STEP_SEQ",
        "MCP_SEQ",
        "소요기준",
    ]
    _require_non_null(result, required, "RQ_REQB")
    return result.reset_index(drop=True)


def _validated_distinct(
    frame: pd.DataFrame,
    table_name: str,
    contract: CoreDataContract,
) -> pd.DataFrame:
    keys = contract.derived_keys.get(table_name)
    if keys is None:
        raise KeyError(f"{table_name} 업무 키 계약이 없습니다.")
    _require_columns(frame, list(keys), table_name)
    _require_non_null(frame, list(keys), table_name)
    duplicated = frame.duplicated(subset=list(keys), keep=False)
    if duplicated.any():
        non_keys = [column for column in frame.columns if column not in keys]
        conflicts = _has_conflicting_duplicates(frame.loc[duplicated], list(keys), non_keys)
        if conflicts:
            raise ValueError(f"{table_name}의 동일 업무 키에 서로 다른 값이 있습니다.")
    return frame.drop_duplicates(subset=list(keys), keep="first").reset_index(drop=True)


def _has_conflicting_duplicates(
    frame: pd.DataFrame,
    keys: list[str],
    value_columns: list[str],
) -> bool:
    if not value_columns:
        return False
    grouped = frame.groupby(keys, dropna=False, sort=False)[value_columns].nunique(dropna=False)
    return bool(grouped.gt(1).any(axis=None))


def _nonblank_rows(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    values = frame[column].astype("string")
    return frame.loc[values.notna() & values.str.strip().ne("")].copy()


def _require_non_null(frame: pd.DataFrame, columns: list[str], table_name: str) -> None:
    invalid_columns = [column for column in columns if frame[column].isna().any()]
    for column in columns:
        if pd.api.types.is_string_dtype(frame[column].dtype):
            if frame[column].astype("string").str.strip().eq("").any():
                invalid_columns.append(column)
    if invalid_columns:
        labels = ", ".join(dict.fromkeys(invalid_columns))
        raise ValueError(f"{table_name} 업무 키에 null 또는 빈값이 있습니다: {labels}")


def _require_columns(frame: pd.DataFrame, columns: list[str], table_name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{table_name}에 필수 컬럼이 없습니다: {', '.join(missing)}")


def _nullable_integer(series: pd.Series, label: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    source_missing = series.isna() | series.astype("string").str.strip().eq("").fillna(False)
    invalid = numeric.isna() & ~source_missing
    fractional = numeric.notna() & numeric.mod(1).ne(0)
    if invalid.any() or fractional.any():
        raise ValueError(f"RQ_DISPLAY_ORDER {label}은 정수여야 합니다.")
    return numeric.astype("Int64")
