# Purpose: 월별 Dynamic 가용대수와 기준정보 Static 가용대수를 한 표로 맞대어 GAP 을 낸다.

"""Static 대 Dynamic 가용대수.

**Static** 은 시뮬레이션 DB 의 기준정보 `RQ_EQP_AVBL`(`생산계획년월`·`공정`·`가용대수`)
이다. Core_Data 에서 `설비보유 - 설비대여평가` 로 한 번에 파생되어 저장된 월별 한 줄
값이고, 확보율이 보는 것이 이 값이다.

**Dynamic** 은 호기 마스터의 일정과 비가동을 공정별 Cut-off 로 안분해 만든 값이다
(`services/monthly_equipment_availability.py`). 둘의 차이가 GAP 이다.

## 두 DB 를 잇는 가정

Static 의 `공정` 은 원본 공정명이고 Dynamic 의 `공정소분류` 는 호기 마스터의 자유
텍스트다. **둘이 같은 이름 공간이라는 것을 강제하는 장치가 저장소에 없다.** 그래서
여기서는 같은 값으로 조인하되 **어느 한쪽에만 있는 공정을 따로 돌려준다**
(`GapComparison.dynamic_only`·`static_only`). 화면은 그 목록을 반드시 드러내야 한다 —
조용히 떨어지면 GAP 이 이유 없이 커 보인다.

**한쪽에만 있는 공정은 GAP 을 내지 않는다**(2026-10-01 사용자 결정). 없는 쪽을 0 으로 보면
「기준정보에 이름이 없다」가 「Dynamic 만큼 모자라다(넘친다)」로 읽힌다 — 공정명이 어긋난
것을 대수 차이로 보고하는 셈이다. 그 공정의 분류·소계(또는 Static) 행은 그대로 두고 GAP 행만
뺀다. 전체 합계(화면이 한쪽짜리 공정을 뺀다)·호기 필터(Static·GAP 을 뺀다)와 같은 규칙이다.

## 행 구성

한 `(월, 공정)` 마다 이렇게 쌓인다.

    분류 행 열 개          기존보유 / 가용 / 운영 비가동 / ... (부호와 가용반영 플래그)
    Dynamic 가용 소계      `가용반영` 이 참인 분류만 더한 값
    Static 가용대수        기준정보에서 그대로
    GAP                    Dynamic 소계 - Static (양쪽에 다 있는 공정만)
    Dynamic 가용 소계(환산) 같은 소계에 호기별 환산비를 곱한 값

`GAP` 이 음수면 기준정보가 실제 확보보다 낙관적이라는 뜻이다.

**환산 소계는 GAP 에 들어가지 않는다.** Static 은 `설비보유 - 설비대여평가` 로 나온
**대수**라, 생산성을 곱한 환산대수와 맞대면 단위가 어긋난다. 그 행은 월 Total Capa 를
낼 때 쓰는 축이고, GAP 은 대수끼리 비교한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pandas as pd

from capa_simulation.services.monthly_equipment_availability import (
    CATEGORIES,
    available_subtotal,
)

__all__ = [
    "DYNAMIC_SUBTOTAL_ROW",
    "DYNAMIC_WEIGHTED_ROW",
    "GAP_COMPARISON_COLUMNS",
    "GAP_ROW",
    "GapComparison",
    "ROW_KIND_CATEGORY",
    "ROW_KIND_GAP",
    "ROW_KIND_STATIC",
    "ROW_KIND_SUBTOTAL",
    "ROW_KIND_WEIGHTED",
    "STATIC_ROW",
    "build_availability_gap",
    "gap_matrix",
]

DYNAMIC_SUBTOTAL_ROW = "Dynamic 가용 소계"
DYNAMIC_WEIGHTED_ROW = "Dynamic 가용 소계 (환산비 반영)"
STATIC_ROW = "Static 가용대수"
GAP_ROW = "GAP (Dynamic - Static)"

ROW_KIND_CATEGORY = "분류"
ROW_KIND_SUBTOTAL = "소계"
ROW_KIND_WEIGHTED = "환산소계"
ROW_KIND_STATIC = "Static"
ROW_KIND_GAP = "GAP"

GAP_COMPARISON_COLUMNS = ("생산계획년월", "공정", "행", "대수", "행종류", "부호", "가용반영")

_CATEGORY_ORDER = {category.name: index for index, category in enumerate(CATEGORIES)}
_ROW_ORDER = {
    ROW_KIND_CATEGORY: 0,
    ROW_KIND_SUBTOTAL: 1,
    ROW_KIND_STATIC: 2,
    ROW_KIND_GAP: 3,
    # 환산 소계는 GAP 아래에 둔다. **GAP 계산에 들어가지 않는다** — Static 은 대수를
    # 센 값(`설비보유 - 설비대여평가`)이라 환산대수와 맞대면 단위가 어긋난다.
    ROW_KIND_WEIGHTED: 4,
}


@dataclass(frozen=True)
class GapComparison:
    """비교 결과와 **맞대지 못한 공정 목록**."""

    rows: pd.DataFrame
    dynamic_only: list[str] = field(default_factory=list)
    """설비는 있는데 기준정보에 없는 공정."""

    static_only: list[str] = field(default_factory=list)
    """기준정보에는 있는데 Cut-off 나 설비가 없어 Dynamic 이 안 나온 공정."""


def _empty_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "생산계획년월": pd.Series(dtype="int64"),
            "공정": pd.Series(dtype="string"),
            "행": pd.Series(dtype="string"),
            "대수": pd.Series(dtype="float64"),
            "행종류": pd.Series(dtype="string"),
            "부호": pd.Series(dtype="int64"),
            "가용반영": pd.Series(dtype="bool"),
        }
    )


def build_availability_gap(
    monthly: pd.DataFrame,
    static_availability: pd.DataFrame,
    months: Sequence[int],
) -> GapComparison:
    """월별 Dynamic 분해와 Static 을 한 표로 맞댄다.

    `static_availability` 는 `RQ_EQP_AVBL` 의 컬럼(`생산계획년월`·`공정`·`가용대수`)을
    그대로 받는다. **어느 DB 도 열지 않는다** — 프레임 둘을 받아 프레임 하나를 만든다.
    """
    wanted = [int(month) for month in dict.fromkeys(months)]
    static = _normalized_static(static_availability, wanted)
    dynamic = monthly.loc[monthly["생산계획년월"].isin(wanted)] if not monthly.empty else monthly

    dynamic_processes = _processes(dynamic)
    static_processes = _processes(static)

    if dynamic.empty and static.empty:
        return GapComparison(rows=_empty_rows())

    pieces: list[pd.DataFrame] = []
    if not dynamic.empty:
        categories = dynamic.rename(columns={"분류": "행"}).copy()
        categories["행종류"] = ROW_KIND_CATEGORY
        pieces.append(categories.loc[:, list(GAP_COMPARISON_COLUMNS)])

    subtotal = available_subtotal(dynamic) if not dynamic.empty else None
    subtotal_frame = _labelled(
        subtotal.rename(columns={"Dynamic가용대수": "대수"}) if subtotal is not None else None,
        row=DYNAMIC_SUBTOTAL_ROW,
        kind=ROW_KIND_SUBTOTAL,
    )
    if subtotal_frame is not None:
        pieces.append(subtotal_frame)

    static_frame = _labelled(
        static.rename(columns={"가용대수": "대수"}) if not static.empty else None,
        row=STATIC_ROW,
        kind=ROW_KIND_STATIC,
    )
    if static_frame is not None:
        pieces.append(static_frame)

    gap = _gap_rows(subtotal, static, wanted, dynamic_processes & static_processes)
    if gap is not None:
        pieces.append(gap)

    weighted = _labelled(
        subtotal.rename(columns={"Dynamic가용환산대수": "대수"})
        if subtotal is not None and "Dynamic가용환산대수" in subtotal.columns
        else None,
        row=DYNAMIC_WEIGHTED_ROW,
        kind=ROW_KIND_WEIGHTED,
    )
    if weighted is not None:
        pieces.append(weighted)

    rows = pd.concat(pieces, ignore_index=True) if pieces else _empty_rows()
    rows = _sorted(rows)
    return GapComparison(
        rows=rows,
        dynamic_only=sorted(dynamic_processes - static_processes),
        static_only=sorted(static_processes - dynamic_processes),
    )


def _normalized_static(static_availability: pd.DataFrame, months: list[int]) -> pd.DataFrame:
    if static_availability.empty:
        return pd.DataFrame({"생산계획년월": [], "공정": [], "가용대수": []})
    required = {"생산계획년월", "공정", "가용대수"}
    missing = sorted(required - set(static_availability.columns))
    if missing:
        raise ValueError(f"Static 가용대수 표에 필수 컬럼이 없습니다: {', '.join(missing)}")
    frame = static_availability.loc[:, ["생산계획년월", "공정", "가용대수"]].copy()
    frame["생산계획년월"] = pd.to_numeric(frame["생산계획년월"], errors="coerce")
    frame = frame.dropna(subset=["생산계획년월", "공정"])
    frame["생산계획년월"] = frame["생산계획년월"].astype("int64")
    frame["공정"] = frame["공정"].astype("string").str.strip()
    frame = frame.loc[frame["생산계획년월"].isin(months)]
    if frame.empty:
        return pd.DataFrame({"생산계획년월": [], "공정": [], "가용대수": []})
    # 같은 월·공정이 여러 줄로 오면 합친다 — 기준정보 편집이 쪼개 놓았을 수 있다.
    return frame.groupby(["생산계획년월", "공정"], as_index=False).agg({"가용대수": "sum"})


def _processes(frame: pd.DataFrame) -> set[str]:
    if frame.empty or "공정" not in frame.columns:
        return set()
    return {str(value).strip() for value in frame["공정"].dropna() if str(value).strip()}


def _labelled(frame: pd.DataFrame | None, *, row: str, kind: str) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    result = frame.loc[:, ["생산계획년월", "공정", "대수"]].copy()
    result["행"] = row
    result["행종류"] = kind
    result["부호"] = 1
    result["가용반영"] = False
    return result.loc[:, list(GAP_COMPARISON_COLUMNS)]


def _gap_rows(
    subtotal: pd.DataFrame | None,
    static: pd.DataFrame,
    months: list[int],
    matched: set[str],
) -> pd.DataFrame | None:
    """양쪽에 다 있는 공정(`matched`)만 GAP 을 낸다 — 한쪽에만 있는 공정은 GAP 이 없다.

    한쪽짜리 공정의 없는 쪽을 0 으로 보면 공정명 불일치가 대수 차이로 읽힌다(모듈 docstring,
    2026-10-01 결정). 양쪽에 다 있는 공정 안에서 어느 달 값이 한쪽에 없으면 그 달은 0 으로
    본다 — 이름이 맞는 공정의 빈 달은 그 달 대수가 없다는 뜻이다. **다만 한쪽에 그 달 자료가
    아예 없으면(설비 조회기간이 시나리오 기간보다 넓은 달 등) 그 달은 GAP 을 내지 않는다** —
    그 달은 「대수가 없다」가 아니라 「맞댈 자료가 없다」다. 전에는 시나리오 밖 달에 Static 0 을
    두고 GAP = +Dynamic 을 냈다(2026-10-01 최종 재점검).
    """
    left = (
        subtotal.rename(columns={"Dynamic가용대수": "dynamic"})
        if subtotal is not None and not subtotal.empty
        else pd.DataFrame({"생산계획년월": [], "공정": [], "dynamic": []})
    )
    right = (
        static.rename(columns={"가용대수": "static"})
        if not static.empty
        else pd.DataFrame({"생산계획년월": [], "공정": [], "static": []})
    )
    if left.empty and right.empty:
        return None
    both_months = _months_of(left) & _months_of(right)
    merged = left.merge(right, on=["생산계획년월", "공정"], how="outer")
    merged = merged.loc[merged["생산계획년월"].isin(both_months)]
    merged = merged.loc[merged["공정"].astype("string").str.strip().isin(matched)].copy()
    merged["dynamic"] = merged["dynamic"].fillna(0.0)
    merged["static"] = merged["static"].fillna(0.0)
    merged["대수"] = merged["dynamic"] - merged["static"]
    merged = merged.loc[merged["생산계획년월"].isin(months)]
    if merged.empty:
        return None
    merged["행"] = GAP_ROW
    merged["행종류"] = ROW_KIND_GAP
    merged["부호"] = 1
    merged["가용반영"] = False
    return merged.loc[:, list(GAP_COMPARISON_COLUMNS)]


def _months_of(frame: pd.DataFrame) -> set[int]:
    """그 쪽에 자료가 있는 달(어느 공정이든)."""
    if frame.empty:
        return set()
    return {int(month) for month in pd.to_numeric(frame["생산계획년월"], errors="coerce").dropna()}


def _sorted(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return _empty_rows()
    result = rows.copy()
    result["생산계획년월"] = result["생산계획년월"].astype("int64")
    result["공정"] = result["공정"].astype("string")
    result["행"] = result["행"].astype("string")
    result["행종류"] = result["행종류"].astype("string")
    result["대수"] = result["대수"].astype("float64")
    result["부호"] = result["부호"].astype("int64")
    result["가용반영"] = result["가용반영"].astype("bool")
    result["_kind"] = result["행종류"].map(_ROW_ORDER).fillna(9)
    result["_row"] = result["행"].map(_CATEGORY_ORDER).fillna(0)
    result = result.sort_values(["공정", "생산계획년월", "_kind", "_row"])
    return result.drop(columns=["_kind", "_row"]).reset_index(drop=True)


def gap_matrix(rows: pd.DataFrame, process: str | None = None) -> pd.DataFrame:
    """화면에 그대로 얹는 행렬 — 행이 분류, 열이 월.

    `process` 를 주면 그 공정만, 없으면 모든 공정을 더한다. GAP 은 합쳐도 GAP 이므로
    그냥 더해도 뜻이 맞는다.
    """
    if rows.empty:
        return pd.DataFrame()
    scoped = rows if process is None else rows.loc[rows["공정"] == process]
    if scoped.empty:
        return pd.DataFrame()
    pivot = scoped.pivot_table(
        index=["행종류", "행"],
        columns="생산계획년월",
        values="대수",
        aggfunc="sum",
        fill_value=0.0,
    )
    order = sorted(
        pivot.index,
        key=lambda pair: (_ROW_ORDER.get(str(pair[0]), 9), _CATEGORY_ORDER.get(str(pair[1]), 0)),
    )
    pivot = pivot.reindex(order)
    pivot.index = pd.Index([str(pair[1]) for pair in pivot.index], name="분류")
    pivot.columns = pd.Index([str(int(column)) for column in pivot.columns], name="생산계획년월")
    return pivot
