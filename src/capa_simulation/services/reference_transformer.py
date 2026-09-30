# Purpose: Pandas equivalents of the XLSB Power Query reference-table transformations.

"""Pandas equivalents of the XLSB Power Query reference-table transformations."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataContract,
    load_core_data_contract,
)
from capa_simulation.services.core_data_derivation import (
    build_q_core_data,
    reject_unmapped_cs_codes,
)
from capa_simulation.services.display_order_editor import transform_display_order
from capa_simulation.services.reference_conflicts import (
    conflict_report,
    validated_distinct,
)


@dataclass(frozen=True)
class ReferenceTableBuildResult:
    """Derived RQ tables and non-blocking business-key conflict diagnostics."""

    tables: dict[str, pd.DataFrame]
    conflicts: pd.DataFrame


def build_reference_tables(
    source: pd.DataFrame,
    display_order: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the 16 RQ tables, keeping the first row for temporary conflicts."""
    return build_reference_tables_with_conflicts(source, display_order, contract).tables


def build_reference_tables_with_conflicts(
    source: pd.DataFrame,
    display_order: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> ReferenceTableBuildResult:
    """Build all RQ tables and collect conflicting business keys without stopping."""
    selected_contract = contract or load_core_data_contract()
    core = build_q_core_data(source, selected_contract)
    # 규칙 밖 CS 코드는 표를 만들기 전에 코드 이름과 함께 막는다 — 표 검사까지 가면 「양산구분이
    # 비었다」로만 멈춘다.
    reject_unmapped_cs_codes(core)
    conflict_records: list[dict[str, object]] = []
    tables = {
        "RQ_PKG_PLAN": _rq_pkg_plan(core, selected_contract, conflict_records),
        "RQ_YLD": _rq_yld(core, selected_contract, conflict_records),
        "RQ_CHIP_QTY": _rq_chip_qty(core, selected_contract, conflict_records),
        "RQ_CHIP_EQ": _rq_chip_eq(core, selected_contract, conflict_records),
        "RQ_DISPLAY_ORDER": transform_display_order(display_order),
        "RQ_EQP_OWN": _monthly_process_table(
            core,
            "RQ_EQP_OWN",
            "설비보유",
            selected_contract,
            conflict_records,
        ),
        "RQ_EQP_LENT": _monthly_process_table(
            core,
            "RQ_EQP_LENT",
            "설비대여평가",
            selected_contract,
            conflict_records,
        ),
        "RQ_EQP_AVBL": _monthly_process_table(
            core,
            "RQ_EQP_AVBL",
            "가용대수",
            selected_contract,
            conflict_records,
        ),
        "RQ_UPEH": _rq_upeh(core, selected_contract, conflict_records),
        "RQ_RUN_RATE": _monthly_process_class_table(
            core,
            "RQ_RUN_RATE",
            "CAPA_RUN_RATE",
            selected_contract,
            conflict_records,
        ),
        "RQ_VITAL": _monthly_process_class_table(
            core,
            "RQ_VITAL",
            "편중률",
            selected_contract,
            conflict_records,
        ),
        "RQ_MODULE": _rq_module(core, selected_contract, conflict_records),
        "RQ_RUN_DAY": _monthly_process_table(
            core,
            "RQ_RUN_DAY",
            "RUN_DAY",
            selected_contract,
            conflict_records,
        ),
        "RQ_LOT_RATIO": _measurement_ratio_table(
            core,
            "RQ_LOT_RATIO",
            "Lot 측정률",
            selected_contract,
            conflict_records,
        ),
        "RQ_WF_RATIO": _measurement_ratio_table(
            core,
            "RQ_WF_RATIO",
            "WF측정률",
            selected_contract,
            conflict_records,
        ),
        "RQ_REQB": _rq_reqb(core, selected_contract, conflict_records),
    }
    business_key_columns = list(
        dict.fromkeys(
            key
            for table_name in tables
            for key in selected_contract.derived_keys.get(table_name, ())
        )
    )
    conflicts = conflict_report(conflict_records, business_key_columns)
    return ReferenceTableBuildResult(tables=tables, conflicts=conflicts)


def _rq_pkg_plan(
    core: pd.DataFrame,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    # 순서는 DDL 을 따른다. `제품타입`·`Pack Code` 는 0013 에서 ALTER 로 덧붙였으므로
    # 테이블에서도 끝에 있다. 순서가 어긋나면 리비전 왕복 비교가 깨진다.
    columns = [
        "생산계획년월",
        "양산구분",
        "CS",
        "제품정보",
        "Stack",
        "Capa Code",
        "Customer",
        "생산수량",
        "제품타입",
        "Pack Code",
    ]
    result = core.loc[core["계획기초정보여부"].eq("Y"), columns].copy()
    return validated_distinct(result, "RQ_PKG_PLAN", contract, conflict_records)


def _rq_yld(
    core: pd.DataFrame,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["생산계획년월", "제품정보", "Stack", "WF 구분", "EDS_수율", "BE_수율"]
    return validated_distinct(
        core.loc[:, columns].copy(),
        "RQ_YLD",
        contract,
        conflict_records,
    )


def _rq_chip_qty(
    core: pd.DataFrame,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["제품정보", "Stack", "WF 구분", "구분_Chip", "Net Die"]
    return validated_distinct(
        core.loc[:, columns].copy(),
        "RQ_CHIP_QTY",
        contract,
        conflict_records,
    )


def _rq_chip_eq(
    core: pd.DataFrame,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["제품정보", "Stack", "WF 구분", "구분_Chip", "구분_EQ"]
    result = core.loc[core["구분_EQ"].notna(), columns].copy()
    return validated_distinct(result, "RQ_CHIP_EQ", contract, conflict_records)


def _monthly_process_table(
    core: pd.DataFrame,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["생산계획년월", "공정", value_column]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return validated_distinct(result, table_name, contract, conflict_records)


def _monthly_process_class_table(
    core: pd.DataFrame,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["생산계획년월", "공정", "양산구분", value_column]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return validated_distinct(result, table_name, contract, conflict_records)


def _rq_upeh(
    core: pd.DataFrame,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = [
        "생산계획년월",
        "Area_Name",
        "공정",
        "STEP_SEQ",
        "MCP_SEQ",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
        "소요기준",
        "UPEH",
        "ST",
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return validated_distinct(result, "RQ_UPEH", contract, conflict_records)


def _rq_module(
    core: pd.DataFrame,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    result = _nonblank_rows(core.loc[:, ["공정", "모듈수"]].copy(), "공정")
    return validated_distinct(result, "RQ_MODULE", contract, conflict_records)


def _measurement_ratio_table(
    core: pd.DataFrame,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = [
        "생산계획년월",
        "Area_Name",
        "공정",
        "STEP_SEQ",
        "MCP_SEQ",
        "양산구분",
        "제품정보",
        "Stack",
        "WF 구분",
        value_column,
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    result = validated_distinct(result, table_name, contract, conflict_records)
    result[value_column] = result[value_column].fillna(1.0)
    return result


def _rq_reqb(
    core: pd.DataFrame,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    """부하량을 공정으로 흘리는 경로 표를 만든다.

    16개 RQ 중 이 표만 업무 키 계약 밖에 있어서 중복 검출도 `drop_duplicates` 도 받지
    않았다. `required_equipment` 가 이 프레임을 왼쪽에 두고 `many_to_one` 으로 붙이므로
    원천에 완전 중복 행이 하나 들어오면 그 경로의 소요대수가 조용히 두 배가 된다.
    13개 컬럼 전부가 키인 경로 표라 값 충돌은 생길 수 없고, 중복은 그대로 접힌다.
    """
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
    # 13컬럼 전부가 업무 키라 `validated_distinct` 가 같은 null·빈값 검사를 같은 메시지로 한다.
    return validated_distinct(result, "RQ_REQB", contract, conflict_records)


def _nonblank_rows(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    values = frame[column].astype("string")
    return frame.loc[values.notna() & values.str.strip().ne("")].copy()
