# Purpose: 반입·Qual 일정이 비어 가용대수에 들지 못하는 신규 설비를 세고 알림 한 줄을 만든다.

"""일정 미정 설비.

반입·Qual 일정은 비워도 저장된다(2026-10-06 사용자 결정). 그런 신규 호기는 반입이 비면 「입고
예정」, 반입만 있고 Qual 이 비면 「셋업 진행중」에 머물러 **날짜가 들어올 때까지 가용대수에 들지
않는다.** Dynamic 가용대수를 읽는 자리(가용설비 현황 Main·Static/Dynamic·필요단축일정)가 그
대수를 한 줄로 알린다 — 말하지 않으면 「설비가 모자라다」로 읽힌다. 필요단축일정에서는 단축
후보도 아니다(당길 Qual 일정이 없다).

- **대상** — 사용기준이 HBM 이고(`equipment_contract.counts_for_capacity` — 다른 행은 날짜를
  채워도 가용대수에 들지 않는다) 기존설비여부 N · 보관유무 N 이며 반출일정·이설일정이 모두 빈 행
  가운데 반입일정 또는 Qual일정이 빈 행. 반출·이설 날짜가 있는 행은 뺀다 — 이 알림은 기준일이
  없어 이미 나간 호기와 나갈 호기를 가를 수 없고, 나갈 호기는 날짜를 채워도 실행일에 빠지는 호기다.
  반입은 있고 Qual 만 빈 채 나갈 호기는 그래서 세지 않는다(드문 경우).
- **나눔** — 반입이 빈 행은 `반입 미정`, 반입은 있고 Qual 만 빈 행은 `Qual 미정` 이다. 겹치지 않아
  둘을 더하면 전체다.
- **세는 법** — 행이 아니라 설비이고, **Dynamic 이 날짜 때문에 실제로 빼는 몫**만 센다. Dynamic
  의 대수 축은 그 시점 보유 중인 모듈 수로 1 을 나누므로(`equipment_units.held_unit_shares`)
  기준일 없이 이렇게 옮긴다. 「보유할 수 있는 행」은 반입일정이 있거나 기존설비·보관 설비인 행이다.
  - `반입 미정` — 반입이 빈 행인데 **같은 설비에 보유할 수 있는 행이 하나도 없을 때만**이다. 설비
    전체가 들어오지 않았으므로 그 설비를 1대로 센다(해당 행들이 1 을 나눠 갖는다). 형제 모듈이
    이미 들어와 있으면 그 설비는 형제로 1대가 차 있어 반입이 빈 모듈 몫은 Dynamic 에서 0 이다 —
    세지 않는다.
  - `Qual 미정` — 반입은 있고 Qual 이 빈 행. 그 설비에서 보유할 수 있는 행 수로 1 을 나눈
    몫이다(모듈 넷 중 A·B 가용, C 는 Qual 없음, D 는 반입 없음 → C 의 1/3 = 0.33대).
  지분은 넘겨받은 호기 마스터 전체로 매기므로 **거르기 전의 표**를 넘기고, 범위는 `processes`·
  `unit_ids` 로 좁힌다(행마다 몫이 정해져 있어 호기 필터가 모듈 하나만 골라도 그 몫만 남는다).
  사용기준도 몫을 다 매긴 뒤에 거른다 — Dynamic 이 설비지분을 형제 전체로 매기고 HBM 이 아닌 행의
  몫만 빼는 것과 같은 셈이다.
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
    counts_for_capacity,
)
from capa_simulation.services.equipment_units import (
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
    format_unit_count,
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
    keys = unit_keys(prepared)
    fresh = prepared["기존설비여부"].eq("N") & prepared[STORAGE_FLAG_COLUMN].eq("N")
    staying = prepared["반출일정"].isna() & prepared[RELOCATION_DATE_COLUMN].isna()
    has_arrival = prepared[ARRIVAL_DATE_COLUMN].notna()
    holdable = (has_arrival | ~fresh).astype("int64")
    holdable_in_unit = holdable.groupby(keys).transform("sum")
    no_arrival = fresh & staying & ~has_arrival & holdable_in_unit.eq(0)
    no_qual = fresh & staying & has_arrival & prepared["Qual일정"].isna()
    # 몫은 사용기준과 상관없이 매기고 HBM 행만 남긴다(모듈 docstring).
    chosen = (no_arrival | no_qual) & counts_for_capacity(prepared)
    if not chosen.any():
        return _empty()
    arrival_rows = no_arrival.astype("int64").groupby(keys).transform("sum")
    shares = (1.0 / arrival_rows.where(no_arrival)).fillna(1.0 / holdable_in_unit.where(no_qual))
    kinds = pd.Series(UNDATED_QUAL, index=prepared.index, dtype="string").mask(
        no_arrival, UNDATED_ARRIVAL
    )
    result = pd.DataFrame(
        {
            EQUIPMENT_ID_COLUMN: prepared[EQUIPMENT_ID_COLUMN].astype("string"),
            "공정소분류": prepared["공정소분류"].astype("string"),
            UNIT_KEY_COLUMN: keys,
            UNIT_SHARE_COLUMN: shares.astype("float64"),
            UNDATED_KIND_COLUMN: kinds,
        }
    )
    return result.loc[chosen].reset_index(drop=True)


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
