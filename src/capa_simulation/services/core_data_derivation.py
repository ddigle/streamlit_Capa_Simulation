# Purpose: 원천 Core Data의 78컬럼에서 RQ 파생에 쓰는 정규화된 작업 프레임을 만든다.

"""원천 Core Data의 78컬럼에서 RQ 파생에 쓰는 정규화된 작업 프레임을 만든다."""

from __future__ import annotations

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataContract,
    normalize_core_data,
)
from capa_simulation.services.product_type import apply_edp_wf_division

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
    # BigDataQuery can represent blanks in product names with underscores. Keep
    # the typed raw snapshot unchanged, but normalize the RQ business key before
    # any table is derived so every downstream join receives the same value.
    core["제품정보"] = (
        core["제품정보"]
        .str.replace("*_", " ", regex=False)
        .str.replace("_", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    area_names = core["Area_Name"].astype("string").str.strip()
    normalized_areas = area_names.str.casefold()
    core["Area_Name"] = area_names
    core.loc[normalized_areas.eq("main").fillna(False), "Area_Name"] = "Main"
    core.loc[normalized_areas.eq("mi").fillna(False), "Area_Name"] = "MI"
    core["양산구분"] = pd.Series(pd.NA, index=core.index, dtype="string")
    core.loc[core["CS"].isin(["MP", "CS"]), "양산구분"] = "양산"
    core.loc[core["CS"].eq("ER"), "양산구분"] = "ER"
    core["가용대수"] = core["설비보유"] - core["설비대여평가"]
    # EDP-TSV 의 `Top` 을 `Top_e` 로 가른다. 원천에는 `Top_e` 가 없으므로 입력은 그대로
    # 받고 여기서 한 번만 바꾼다 — 아래로 내려가는 16개 RQ 표와 화면이 전부 같은 값을 본다.
    core = apply_edp_wf_division(core)
    return core
