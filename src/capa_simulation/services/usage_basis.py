# Purpose: 사용기준이 HBM 이 아니어서 Dynamic 가용대수에 세지 않는 설비를 세고 알림 한 줄을 만든다.

"""사용기준 제외 설비.

Dynamic 가용대수는 **사용기준이 HBM 인 호기만** 센다(`equipment_contract.counts_for_capacity`,
2026-10-07 사용자 결정). 나머지 호기는 배치(Space)·호기 목록·상태 분포에는 그대로 있고
가용대수에서만 빠진다. 말하지 않으면 「호기 마스터에는 열 대인데 가용대수는 여섯」이 설명 없이
남으므로, 가용대수를 보이는 자리(가용설비 현황 Main `가용대수`·Static/Dynamic·필요단축일정)가 이
대수를 한 줄로 알린다.

- **대상** — 사용기준이 HBM 이 아닌 행(빈 칸 포함). 날짜를 보지 않는다 — 호기 마스터에 있는
  그대로를 센다(이미 반출된 호기도 마스터에 남아 있으면 센다).
- **세는 법** — 행이 아니라 설비다. 보유와 상관없는 셈이라 고정 지분(`static_unit_shares`, 1 ÷
  같은 설비키의 행 수)을 더한다. 모듈 넷 중 둘만 HBM 이 아니면 0.5대다.
- 지분은 넘겨받은 호기 마스터 전체로 매기므로 **거르기 전의 표**를 넘기고, 범위는 `processes`·
  `unit_ids` 로 좁힌다(일정 미정 알림 `undated_equipment` 와 같은 꼴이다).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    COUNTED_USAGE_BASIS,
    EQUIPMENT_ID_COLUMN,
    USAGE_BASIS_COLUMN,
    counts_for_capacity,
)
from capa_simulation.services.equipment_units import (
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
    format_unit_count,
    static_unit_shares,
    unit_keys,
    unit_total,
)
from capa_simulation.services.equipment_validation import prepare_equipment_master

USAGE_EXCLUDED_COLUMNS: Final = (
    EQUIPMENT_ID_COLUMN,
    "공정소분류",
    USAGE_BASIS_COLUMN,
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
)


def usage_excluded_equipment(equipment: pd.DataFrame) -> pd.DataFrame:
    """호기 마스터(검증 전 편집본도 받는다)에서 사용기준 때문에 가용대수에 세지 않는 행을 고른다.

    돌려주는 칸은 `USAGE_EXCLUDED_COLUMNS` 다. 호기 마스터가 검증을 통과하지 못하면
    `ValueError` 다 — 화면은 같은 표로 다른 계산도 하므로 이미 그 자리에서 오류를 알린다.
    """
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return _empty()
    keys = unit_keys(prepared)
    shares = static_unit_shares(keys)
    excluded = ~counts_for_capacity(prepared)
    if not excluded.any():
        return _empty()
    result = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: prepared[EQUIPMENT_ID_COLUMN].astype("string"),
            "공정소분류": prepared["공정소분류"].astype("string"),
            USAGE_BASIS_COLUMN: prepared[USAGE_BASIS_COLUMN].astype("string"),
            UNIT_KEY_COLUMN: keys.astype("string"),
            UNIT_SHARE_COLUMN: shares.astype("float64"),
        }
    )
    return result.loc[excluded].reset_index(drop=True)


def usage_excluded_count(
    excluded: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    unit_ids: Collection[str] | None = None,
) -> float:
    """사용기준 때문에 뺀 설비 대수. `processes`·`unit_ids` 로 둘러싼 대수와 같은 범위를 센다."""
    kept = pd.Series(True, index=excluded.index)
    if processes is not None:
        kept &= excluded["공정소분류"].isin(set(processes)).fillna(False).astype(bool)
    if unit_ids is not None:
        kept &= excluded[EQUIPMENT_ID_COLUMN].isin(set(unit_ids)).fillna(False).astype(bool)
    return unit_total(excluded.loc[kept, UNIT_SHARE_COLUMN])


def usage_exclusion_notice(
    excluded: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    unit_ids: Collection[str] | None = None,
) -> str | None:
    """「사용기준이 HBM 이 아닌 N대(호기 마스터 기준)는 가용대수에서 뺐습니다 — …」 한 줄.

    0대면 `None`(그리지 않는다).
    """
    count = usage_excluded_count(excluded, processes=processes, unit_ids=unit_ids)
    if count <= 0:
        return None
    basis = "·".join(COUNTED_USAGE_BASIS)
    return (
        f"사용기준이 {basis} 이 아닌 {format_unit_count(count)}대(호기 마스터 기준)는 가용대수에서 "
        "뺐습니다 — 배치·호기 목록에는 그대로 있습니다."
    )


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: pd.Series(dtype="string"),
            "공정소분류": pd.Series(dtype="string"),
            USAGE_BASIS_COLUMN: pd.Series(dtype="string"),
            UNIT_KEY_COLUMN: pd.Series(dtype="string"),
            UNIT_SHARE_COLUMN: pd.Series(dtype="float64"),
        }
    )
