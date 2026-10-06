# Purpose: 반입·Qual 일정이 비어 가용대수에 들지 못하는 신규 설비를 세고 알림 한 줄을 만든다.

"""일정 미정 설비.

반입·Qual 일정은 비워도 저장된다(2026-10-06 사용자 결정). 그런 신규 호기는 반입이 비면 「입고
예정」, 반입만 있고 Qual 이 비면 「셋업 진행중」에 머물러 **날짜가 들어올 때까지 가용대수에 들지
않는다.** Dynamic 가용대수를 읽는 자리(가용설비 현황 Main·Static/Dynamic)가 그 대수를 한 줄로 알린다
— 말하지 않으면 「설비가 모자라다」로 읽힌다.

- **대상** — 기존설비여부 N · 보관유무 N 이고 반출일정·이설일정이 모두 빈 행 가운데 반입일정 또는
  Qual일정이 빈 행. 반출·이설 날짜가 있는 행은 상태가 「반출 예정」·「이설 예정」(지나면 완료)으로
  서므로 뺀다 — 그래서 기준일이 필요 없다.
- **나눔** — 반입이 빈 행은 `반입 미정`, 반입은 있고 Qual 만 빈 행은 `Qual 미정` 이다. 겹치지 않아
  둘을 더하면 전체다.
- **세는 법** — 행이 아니라 설비다. 모듈 행은 고정 지분(1 ÷ 같은 설비의 행 수,
  `equipment_units.static_unit_shares`)을 더한다 — 네 모듈 중 하나만 일정이 비면 0.25대다. 날짜가
  비어 보유 여부를 따질 수 없으므로 Qual 계획 표와 같은 고정 지분을 쓴다. 지분은 넘겨받은 호기
  마스터 전체로 매기므로 **거르기 전의 표**(또는 모듈 묶음을 쪼개지 않는 조건으로 거른 표)를 넘긴다.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final

import pandas as pd

from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    EQUIPMENT_ID_COLUMN,
    RELOCATION_DATE_COLUMN,
    STORAGE_FLAG_COLUMN,
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

UNDATED_KIND_COLUMN: Final = "미정구분"
UNDATED_ARRIVAL: Final = "반입 미정"
UNDATED_QUAL: Final = "Qual 미정"
UNDATED_KINDS: Final = (UNDATED_ARRIVAL, UNDATED_QUAL)
UNDATED_COLUMNS: Final = (
    EQUIPMENT_ID_COLUMN,
    "공정소분류",
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
    UNDATED_KIND_COLUMN,
)


def undated_equipment(equipment: pd.DataFrame) -> pd.DataFrame:
    """호기 마스터(검증 전 편집본도 받는다)에서 일정 미정 행을 고른다.

    돌려주는 칸은 `UNDATED_COLUMNS`(설비명·공정소분류·설비키·설비지분·미정구분)다. 호기 마스터가
    검증을 통과하지 못하면 `ValueError` 다 — 화면은 같은 표로 다른 계산도 하므로 이미 그 자리에서
    오류를 알린다.
    """
    prepared = prepare_equipment_master(equipment)
    if prepared.empty:
        return _empty()
    shares = static_unit_shares(unit_keys(prepared))
    fresh = prepared["기존설비여부"].eq("N") & prepared[STORAGE_FLAG_COLUMN].eq("N")
    staying = prepared["반출일정"].isna() & prepared[RELOCATION_DATE_COLUMN].isna()
    no_arrival = prepared[ARRIVAL_DATE_COLUMN].isna()
    undated = fresh & staying & (no_arrival | prepared["Qual일정"].isna())
    if not undated.any():
        return _empty()
    kinds = pd.Series(UNDATED_QUAL, index=prepared.index, dtype="string").mask(
        no_arrival, UNDATED_ARRIVAL
    )
    result = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: prepared[EQUIPMENT_ID_COLUMN].astype("string"),
            "공정소분류": prepared["공정소분류"].astype("string"),
            UNIT_KEY_COLUMN: unit_keys(prepared),
            UNIT_SHARE_COLUMN: shares.astype("float64"),
            UNDATED_KIND_COLUMN: kinds,
        }
    )
    return result.loc[undated].reset_index(drop=True)


def undated_counts(
    undated: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    unit_ids: Collection[str] | None = None,
) -> dict[str, float]:
    """미정구분별 설비 대수(`반입 미정`·`Qual 미정`, 둘 다 늘 있다).

    `processes` 를 주면 그 공정소분류만, `unit_ids` 를 주면 그 설비명만 센다 — 둘러싼 대수가
    건 조건과 같은 범위를 세기 위해서다.
    """
    kept = pd.Series(True, index=undated.index)
    if processes is not None:
        kept &= undated["공정소분류"].isin(set(processes)).fillna(False).astype(bool)
    if unit_ids is not None:
        kept &= undated[EQUIPMENT_ID_COLUMN].isin(set(unit_ids)).fillna(False).astype(bool)
    rows = undated.loc[kept]
    return {
        kind: unit_total(rows.loc[rows[UNDATED_KIND_COLUMN].eq(kind), UNIT_SHARE_COLUMN])
        for kind in UNDATED_KINDS
    }


def undated_equipment_notice(
    undated: pd.DataFrame,
    *,
    processes: Collection[str] | None = None,
    unit_ids: Collection[str] | None = None,
) -> str | None:
    """「일정 미정 N대 (반입 미정 a · Qual 미정 b) — …」 한 줄. 0대면 `None`(그리지 않는다).

    괄호 안에는 0 이 아닌 쪽만 적는다.
    """
    counts = undated_counts(undated, processes=processes, unit_ids=unit_ids)
    total = round(sum(counts.values()), 6)
    if total <= 0:
        return None
    parts = " · ".join(
        f"{kind} {format_unit_count(count)}" for kind, count in counts.items() if count > 0
    )
    return (
        f"일정 미정 {format_unit_count(total)}대 ({parts}) — 날짜가 들어올 때까지 가용대수에 "
        "세지 않습니다."
    )


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: pd.Series(dtype="string"),
            "공정소분류": pd.Series(dtype="string"),
            UNIT_KEY_COLUMN: pd.Series(dtype="string"),
            UNIT_SHARE_COLUMN: pd.Series(dtype="float64"),
            UNDATED_KIND_COLUMN: pd.Series(dtype="string"),
        }
    )
