# Purpose: 원천 Core Data의 78컬럼에서 RQ 파생에 쓰는 정규화된 작업 프레임을 만든다.

"""원천 Core Data의 78컬럼에서 RQ 파생에 쓰는 정규화된 작업 프레임을 만든다."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

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


# 원천 `CS` 코드 → `양산구분`. 계산은 양산구분을 **양산·ER 두 값**으로만 본다(ER 은 제품 Mix·표준
# 목표 등에서 뺀다). **여기 없는 코드는 등록을 막는다**(`reject_unmapped_cs_codes`) — 새 코드를 어느
# 쪽으로 셀지는 업무 결정이라 조용히 한쪽으로 넣지 않는다. 사내 1월 시나리오에 새 코드 `CB` 가 와서
# 「RQ_PKG_PLAN 업무 키에 null 또는 빈값이 있습니다: 양산구분」으로만 막혔다(2026-09-30).
# 코드는 앞뒤 공백을 지우고 대문자로 맞춘 뒤 대조한다.
CS_PRODUCTION_CLASSES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "MP": "양산",
        "CS": "양산",
        "ER": "ER",
    }
)
# 오류문에 싣는 규칙 밖 코드 수. 코드 종류가 이보다 많으면 원천 매핑 자체가 틀렸을 공산이 크다.
UNMAPPED_CS_EXAMPLE_LIMIT: Final = 10


def reject_unmapped_cs_codes(core: pd.DataFrame) -> None:
    """`CS_PRODUCTION_CLASSES` 에 없는 CS 코드가 있으면 코드별 행 수와 함께 막는다.

    막지 않으면 그 행의 양산구분이 비고, 첫 RQ 표의 업무 키 검사에서 「업무 키에 null 또는
    빈값이 있습니다: 양산구분」으로만 멈춰 어떤 코드 때문인지 알 길이 없었다(2026-09-30).
    `build_q_core_data` 를 거친 프레임을 받는다. 계획 행(`계획기초정보여부 = Y`) 수를 따로 적는다
    — PKG PLAN 에 실리는 행이다.
    """
    unmapped = core["양산구분"].isna()
    if not bool(unmapped.any()):
        return
    codes = core.loc[unmapped, "CS"].astype("string").fillna("").replace("", "(빈값)")
    plan = core.loc[unmapped, "계획기초정보여부"].astype("string").str.strip().eq("Y").fillna(False)
    counts = codes.value_counts()
    plan_counts = codes.loc[plan].value_counts()
    shown = [
        f"`{code}` {int(count):,}행(계획 {int(plan_counts.get(code, 0)):,}행)"
        for code, count in counts.head(UNMAPPED_CS_EXAMPLE_LIMIT).items()
    ]
    rest = len(counts) - len(shown)
    raise ValueError(
        "원천 CS 코드 중 양산구분(양산·ER) 규칙에 없는 값이 있습니다: "
        + ", ".join(shown)
        + (f" 외 {rest:,}종" if rest > 0 else "")
        + f". 규칙에 있는 코드는 {', '.join(CS_PRODUCTION_CLASSES)} 입니다. 새 코드를 양산·ER 중 "
        "어느 쪽으로 셀지 정해 사외에 알려 주세요 — 규칙에 더해야 등록할 수 있습니다."
    )


def build_q_core_data(
    source: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> pd.DataFrame:
    """Apply Q_Core_Data types, active columns, and derived columns."""
    normalized = normalize_core_data(source, contract)
    core = normalized.loc[:, list(ACTIVE_CORE_COLUMNS)].copy()
    # `normalize_core_data` 가 붙인 attrs(원천 dtype 78항목)는 컬럼 프로파일이 원본에서 읽는다.
    # 파생 프레임까지 들고 가면 pandas 가 연산마다 `__finalize__` 에서 deepcopy 한다 —
    # RQ 16표를 만드는 동안 5만 6천 회. 여기서 비운다. 원본(normalized)은 건드리지 않는다.
    core.attrs = {}
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
    # CS 는 업무 키(RQ_PKG_PLAN·RQ_REQB)이기도 하다. 모든 표가 이 프레임에서 나오므로 여기서 한 번
    # 맞추면 표 사이 조인이 같은 값을 본다. 원천 스냅샷(typed raw)은 그대로 둔다.
    core["CS"] = core["CS"].astype("string").str.strip().str.upper()
    core["양산구분"] = core["CS"].map(dict(CS_PRODUCTION_CLASSES)).astype("string")
    core["가용대수"] = core["설비보유"] - core["설비대여평가"]
    # EDP-TSV 의 `Top` 을 `Top_e` 로 가른다. 원천에는 `Top_e` 가 없으므로 입력은 그대로
    # 받고 여기서 한 번만 바꾼다 — 아래로 내려가는 16개 RQ 표와 화면이 전부 같은 값을 본다.
    core = apply_edp_wf_division(core)
    return core
