# Purpose: Pandas equivalents of the XLSB Power Query reference-table transformations.

"""Pandas equivalents of the XLSB Power Query reference-table transformations."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataContract,
    load_core_data_contract,
)
from capa_simulation.services.core_data_derivation import (
    BlankCsDrop,
    derive_q_core_data,
    reject_unmapped_cs_codes,
)
from capa_simulation.services.display_order_editor import transform_display_order
from capa_simulation.services.frame_contracts import require_columns, route_match_keys
from capa_simulation.services.reference_conflicts import (
    SOURCE_ROW_CLASS_COLUMNS,
    conflict_report,
    require_non_null,
    source_row_rank,
    validated_distinct,
)


@dataclass(frozen=True)
class _SourceRows:
    """원천 작업 프레임 한 벌의 행 순위와 구분 칸 — 16표가 같은 것을 받아, 값이 있는 칸 수가
    같은 형제는 표가 달라도 같은 행을 고른다."""

    rank: pd.Series
    classes: pd.DataFrame

    @classmethod
    def of(cls, core: pd.DataFrame) -> _SourceRows:
        classes = core.loc[:, [c for c in SOURCE_ROW_CLASS_COLUMNS if c in core.columns]]
        return cls(rank=source_row_rank(core), classes=classes)

    def distinct(
        self,
        frame: pd.DataFrame,
        table_name: str,
        contract: CoreDataContract,
        conflict_records: list[dict[str, object]],
    ) -> pd.DataFrame:
        return validated_distinct(
            frame,
            table_name,
            contract,
            conflict_records,
            row_rank=self.rank,
            source_classes=self.classes,
        )


@dataclass(frozen=True)
class ReferenceTableBuildResult:
    """파생 RQ 표, 멈추지 않는 업무 키 충돌 보고서, CS 가 비어 뺀 원천 행 수."""

    tables: dict[str, pd.DataFrame]
    conflicts: pd.DataFrame
    blank_cs: BlankCsDrop = field(default_factory=BlankCsDrop)


def build_reference_tables(
    source: pd.DataFrame,
    display_order: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the 16 RQ tables, keeping one ranked sibling row for business-key conflicts."""
    return build_reference_tables_with_conflicts(source, display_order, contract).tables


def build_reference_tables_with_conflicts(
    source: pd.DataFrame,
    display_order: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> ReferenceTableBuildResult:
    """Build all RQ tables and collect conflicting business keys without stopping."""
    selected_contract = contract or load_core_data_contract()
    # CS 가 빈 행은 여기서 이미 빠졌다 — 그 수는 등록 결과 알림·리비전 메모로 올라간다.
    derived = derive_q_core_data(source, selected_contract)
    core = derived.frame
    # 값이 있는데 규칙 밖인 CS 코드는 표를 만들기 전에 코드 이름과 함께 막는다 — 표 검사까지 가면
    # 「양산구분이 비었다」로만 멈춘다.
    reject_unmapped_cs_codes(core)
    # 형제 행 고르기의 순위는 원천 행 전체에서 **한 번** 만든다 — 조회 차례와 상관없이 같은
    # 행이 이기고, 한 원천 행에서 나온 형제 표(보유 · 대여 · 가용 등)도 표마다 값이 있는 칸
    # 수가 같으면 같은 행을 고른다. 아래 빌더는 `core` 의 index(원천 행 번호)를 잇는다.
    rows = _SourceRows.of(core)
    conflict_records: list[dict[str, object]] = []
    tables = {
        "RQ_PKG_PLAN": _rq_pkg_plan(core, rows, selected_contract, conflict_records),
        "RQ_YLD": _rq_yld(core, rows, selected_contract, conflict_records),
        "RQ_CHIP_QTY": _rq_chip_qty(core, rows, selected_contract, conflict_records),
        "RQ_CHIP_EQ": _rq_chip_eq(core, rows, selected_contract, conflict_records),
        "RQ_DISPLAY_ORDER": transform_display_order(display_order),
        "RQ_EQP_OWN": _monthly_process_table(
            core,
            rows,
            "RQ_EQP_OWN",
            "설비보유",
            selected_contract,
            conflict_records,
        ),
        "RQ_EQP_LENT": _monthly_process_table(
            core,
            rows,
            "RQ_EQP_LENT",
            "설비대여평가",
            selected_contract,
            conflict_records,
        ),
        "RQ_EQP_AVBL": _monthly_process_table(
            core,
            rows,
            "RQ_EQP_AVBL",
            "가용대수",
            selected_contract,
            conflict_records,
        ),
        "RQ_UPEH": _rq_upeh(core, rows, selected_contract, conflict_records),
        "RQ_RUN_RATE": _monthly_process_class_table(
            core,
            rows,
            "RQ_RUN_RATE",
            "CAPA_RUN_RATE",
            selected_contract,
            conflict_records,
        ),
        "RQ_VITAL": _monthly_process_class_table(
            core,
            rows,
            "RQ_VITAL",
            "편중률",
            selected_contract,
            conflict_records,
        ),
        "RQ_MODULE": _rq_module(core, rows, selected_contract, conflict_records),
        "RQ_RUN_DAY": _monthly_process_table(
            core,
            rows,
            "RQ_RUN_DAY",
            "RUN_DAY",
            selected_contract,
            conflict_records,
        ),
        "RQ_LOT_RATIO": _measurement_ratio_table(
            core,
            rows,
            "RQ_LOT_RATIO",
            "Lot 측정률",
            selected_contract,
            conflict_records,
        ),
        "RQ_WF_RATIO": _measurement_ratio_table(
            core,
            rows,
            "RQ_WF_RATIO",
            "WF측정률",
            selected_contract,
            conflict_records,
        ),
        "RQ_REQB": _rq_reqb(core, rows, selected_contract, conflict_records),
    }
    tables["RQ_EQP_LENT"], tables["RQ_EQP_AVBL"] = blank_lent_as_zero(
        tables["RQ_EQP_OWN"], tables["RQ_EQP_LENT"], tables["RQ_EQP_AVBL"]
    )
    business_key_columns = list(
        dict.fromkeys(
            key
            for table_name in tables
            for key in selected_contract.derived_keys.get(table_name, ())
        )
    )
    conflicts = conflict_report(conflict_records, business_key_columns)
    return ReferenceTableBuildResult(tables=tables, conflicts=conflicts, blank_cs=derived.blank_cs)


def _rq_pkg_plan(
    core: pd.DataFrame,
    rows: _SourceRows,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    # 순서는 DDL 을 따른다. `제품타입`·`Pack Code` 는 0013, `CUSTOM` 은 0039 에서 ALTER 로
    # 덧붙였으므로 테이블에서도 끝에 있다. 순서가 어긋나면 리비전 왕복 비교가 깨진다.
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
        "CUSTOM",
    ]
    result = core.loc[core["계획기초정보여부"].eq("Y"), columns].copy()
    return rows.distinct(result, "RQ_PKG_PLAN", contract, conflict_records)


def _rq_yld(
    core: pd.DataFrame,
    rows: _SourceRows,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["생산계획년월", "제품정보", "Stack", "WF 구분", "EDS_수율", "BE_수율", "CUSTOM"]
    return rows.distinct(
        core.loc[:, columns].copy(),
        "RQ_YLD",
        contract,
        conflict_records,
    )


def _rq_chip_qty(
    core: pd.DataFrame,
    rows: _SourceRows,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["제품정보", "Stack", "WF 구분", "구분_Chip", "Net Die", "CUSTOM"]
    return rows.distinct(
        core.loc[:, columns].copy(),
        "RQ_CHIP_QTY",
        contract,
        conflict_records,
    )


def _rq_chip_eq(
    core: pd.DataFrame,
    rows: _SourceRows,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["제품정보", "Stack", "WF 구분", "구분_Chip", "구분_EQ", "CUSTOM"]
    result = core.loc[core["구분_EQ"].notna(), columns].copy()
    return rows.distinct(result, "RQ_CHIP_EQ", contract, conflict_records)


def _monthly_process_table(
    core: pd.DataFrame,
    rows: _SourceRows,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["생산계획년월", "공정", value_column]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return rows.distinct(result, table_name, contract, conflict_records)


def blank_lent_as_zero(
    own: pd.DataFrame,
    lent: pd.DataFrame,
    available: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """빈 대여평가를 **0 대**로 메우고, 그 때문에 빈 가용대수를 `보유 − 0` 으로 채운다.

    `가용대수 = 설비보유 − 설비대여평가` 가 빈 대여평가를 그대로 옮기면 가용대수가 비어 확보율
    계산이 멈추고 설비대수 편집기도 열리지 않는다. 설비대수 편집기는 「빈칸은 0 대」로 읽는다
    (`equipment_count`) — 등록도 같은 규칙을 쓴다.

    **표를 접은 뒤에** 메운다. 원천 행에서 먼저 메우면 같은 (월, 공정) 형제 행 가운데 값이 있는
    행을 고르는 규칙(`reference_conflicts._informative_first`)이 보유·대여·가용에서 서로 다른 행을
    골라 세 표가 `보유 − 대여 = 가용` 으로 맞지 않게 된다. 보유대수가 빈 칸은 모르는 값이라 0 으로
    보지 않는다 — 그 달 가용대수는 그대로 빈다.
    """
    keys = ["생산계획년월", "공정"]
    filled_lent = lent.assign(설비대여평가=lent["설비대여평가"].fillna(0.0))
    blank = available["가용대수"].isna()
    if not bool(blank.any()):
        return filled_lent, available
    derived = (
        available.loc[blank, keys]
        .merge(own[[*keys, "설비보유"]], on=keys, how="left", validate="many_to_one")
        .merge(filled_lent[[*keys, "설비대여평가"]], on=keys, how="left", validate="many_to_one")
    )
    filled_available = available.copy()
    filled_available.loc[blank, "가용대수"] = (
        derived["설비보유"] - derived["설비대여평가"]
    ).to_numpy()
    return filled_lent, filled_available


def _monthly_process_class_table(
    core: pd.DataFrame,
    rows: _SourceRows,
    table_name: str,
    value_column: str,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    columns = ["생산계획년월", "공정", "양산구분", value_column]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return rows.distinct(result, table_name, contract, conflict_records)


def _rq_upeh(
    core: pd.DataFrame,
    rows: _SourceRows,
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
        "CUSTOM",
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    return rows.distinct(result, "RQ_UPEH", contract, conflict_records)


def _rq_module(
    core: pd.DataFrame,
    rows: _SourceRows,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    result = _nonblank_rows(core.loc[:, ["공정", "모듈수"]].copy(), "공정")
    return rows.distinct(result, "RQ_MODULE", contract, conflict_records)


def _measurement_ratio_table(
    core: pd.DataFrame,
    rows: _SourceRows,
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
        "CUSTOM",
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "공정")
    result = rows.distinct(result, table_name, contract, conflict_records)
    result[value_column] = result[value_column].fillna(1.0)
    return result


def _rq_reqb(
    core: pd.DataFrame,
    rows: _SourceRows,
    contract: CoreDataContract,
    conflict_records: list[dict[str, object]],
) -> pd.DataFrame:
    """부하량을 공정으로 흘리는 경로 표를 만든다.

    16개 RQ 중 이 표만 업무 키 계약 밖에 있어서 중복 검출도 `drop_duplicates` 도 받지
    않았다. `required_equipment` 가 이 프레임을 왼쪽에 두고 `many_to_one` 으로 붙이므로
    원천에 완전 중복 행이 하나 들어오면 그 경로의 소요대수가 조용히 두 배가 된다.
    14개 컬럼 전부가 키인 경로 표라 값 충돌은 생길 수 없고, 중복은 그대로 접힌다.

    **계산과 같은 정규화**로 접는다(`frame_contracts.route_match_keys`). `WF`·`Wafer` 처럼
    표기만 다른 두 행은 계산에서 같은 경로라 접지 않으면 두 번 세어진다. 남는 것은 원천 행
    순위(`reference_conflicts.source_row_rank`)가 가장 앞선 행이고 그 표기는 원천 그대로다 — 조회
    차례와 상관없이 같은 표기가 저장된다. 경로의 자리는 그 경로가 처음 나온 차례 그대로다.
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
        "CUSTOM",
    ]
    result = _nonblank_rows(core.loc[:, columns].copy(), "Area_Name")
    # 14컬럼 전부가 업무 키라 `validated_distinct` 와 같은 null·빈값 검사를 같은 메시지로
    # 먼저 한다 — 표기 접기는 빈 키를 받지 않는다.
    require_columns(result, columns, "RQ_REQB")
    require_non_null(result, columns, "RQ_REQB")
    # 정규화한 경로마다 원천 행 순위가 가장 앞선 행 하나 — 경로 자리는 첫 등장 차례 그대로다.
    match = route_match_keys(result, columns)
    group = match.groupby(list(match.columns), dropna=False, sort=False).ngroup().to_numpy()
    order = np.lexsort((rows.rank.loc[result.index].to_numpy(), group))
    first = ~pd.Series(group[order]).duplicated().to_numpy()
    return rows.distinct(result.take(order[first]), "RQ_REQB", contract, conflict_records)


def _nonblank_rows(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    values = frame[column].astype("string")
    return frame.loc[values.notna() & values.str.strip().ne("")].copy()
