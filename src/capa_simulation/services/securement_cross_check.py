# Purpose: 같은 소요대수에 Static·Dynamic 가용대수를 각각 적용해 확보율을 맞대어 본다.

"""확보율 교차검증.

`RQ_EQP_AVBL`(Static)은 Core_Data 에서 `설비보유 - 설비대여평가` 로 한 번에 파생된
월별 한 줄 값이다. 그 값이 맞는지 확인할 방법이 지금껏 없었다 — 확보율·B/N 이 전부
그것 하나만 보고 있었기 때문이다.

호기 마스터의 일정을 Cut-off 로 일할 계산한 값(Dynamic)이 생기면서 **같은 소요대수에
두 가용대수를 각각 나눠** 볼 수 있게 됐다. 두 확보율의 차이가 곧 「기준정보가 실제
설비 확보와 얼마나 어긋나 있나」다.

## 무엇을 바꾸지 않는가

**`calculate_securement_rate` 를 고치지 않는다.** 그 함수는 가용대수 프레임을 인자로
받으므로, 프레임만 두 벌 만들어 두 번 부르면 된다. 계산 규칙이 한 곳에 남아야 두
숫자가 같은 잣대로 나온다 — 여기서 산식을 다시 적으면 그 순간부터 두 화면이 서로 다른
이야기를 하게 된다.

## Cut-off 를 안 적은 공정

Dynamic 은 Cut-off 원장에 적힌 공정만 덮는다. 나머지 공정은 `소요대수 > 0` 인데
가용대수 행이 없어 `calculate_securement_rate` 가 예외를 던진다. 그래서 여기서는
**그 공정을 Static 값으로 채워 넣고, 채운 공정 목록을 함께 돌려준다**
(`CrossCheck.fallback_processes`).

채우는 이유는 예외로 멈추면 나머지 공정의 비교도 못 보기 때문이고, 목록을 돌려주는
이유는 **채운 자리는 비교가 아니라 같은 값을 두 번 본 것**이기 때문이다. 화면이 그
구분을 반드시 드러내야 한다 — 안 그러면 「차이 없음」으로 읽힌다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from capa_simulation.services.monthly_equipment_availability import available_subtotal
from capa_simulation.services.securement_rate import calculate_securement_rate

__all__ = [
    "CROSS_CHECK_COLUMNS",
    "CrossCheck",
    "build_securement_cross_check",
    "dynamic_available_equipment",
]

CROSS_CHECK_COLUMNS = (
    "생산계획년월",
    "공정",
    "소요대수",
    "Static가용대수",
    "Dynamic가용대수",
    "Static확보율",
    "Dynamic확보율",
    "확보율차이",
    "Static대체",
)


@dataclass(frozen=True)
class CrossCheck:
    """두 확보율과, **비교가 성립하지 않은 자리**."""

    rows: pd.DataFrame
    fallback_processes: list[str] = field(default_factory=list)
    """Cut-off 가 없어 Dynamic 을 Static 으로 채운 공정. 그 행은 차이가 늘 0 이다."""

    @property
    def compared_processes(self) -> list[str]:
        """실제로 두 값을 맞대어 본 공정."""
        if self.rows.empty:
            return []
        every = {str(value) for value in self.rows["공정"].dropna()}
        return sorted(every - set(self.fallback_processes))


def dynamic_available_equipment(monthly: pd.DataFrame, *, weighted: bool = True) -> pd.DataFrame:
    """월별 일할 가용대수를 `RQ_EQP_AVBL` 과 같은 모양으로 바꾼다.

    `weighted` 가 참이면 호기별 환산비를 곱한 축(`Dynamic가용환산대수`)을 쓴다.
    **기본이 참인 것은 확보율이 생산 능력을 재는 값이기 때문**이다 — 소요대수가
    `부하량 ÷ 대당 Capa` 로 나온 「능력 기준 대수」라 분자도 같은 잣대여야 한다.
    대수를 그대로 세고 싶을 때만 거짓으로 부른다.
    """
    subtotal = available_subtotal(monthly)
    if subtotal.empty:
        return pd.DataFrame({"생산계획년월": [], "공정": [], "가용대수": []})
    column = "Dynamic가용환산대수" if weighted else "Dynamic가용대수"
    result = subtotal.loc[:, ["생산계획년월", "공정", column]].copy()
    return result.rename(columns={column: "가용대수"})


def build_securement_cross_check(
    static_available: pd.DataFrame,
    dynamic_available: pd.DataFrame,
    required_equipment: pd.DataFrame,
) -> CrossCheck:
    """같은 소요대수에 두 가용대수를 각각 나눈 결과.

    **어느 DB 도 열지 않는다.** 프레임 셋을 받아 하나를 돌려준다.
    """
    static_rate = calculate_securement_rate(static_available, required_equipment)
    filled, fallback = _fill_missing_from_static(dynamic_available, static_available, static_rate)
    dynamic_rate = calculate_securement_rate(filled, required_equipment)

    merged = static_rate.loc[:, ["생산계획년월", "공정", "소요대수", "가용대수", "확보율"]].rename(
        columns={"가용대수": "Static가용대수", "확보율": "Static확보율"}
    )
    dynamic_side = dynamic_rate.loc[:, ["생산계획년월", "공정", "가용대수", "확보율"]].rename(
        columns={"가용대수": "Dynamic가용대수", "확보율": "Dynamic확보율"}
    )
    result = merged.merge(dynamic_side, on=["생산계획년월", "공정"], how="outer")
    result["확보율차이"] = result["Dynamic확보율"] - result["Static확보율"]
    result["Static대체"] = result["공정"].isin(fallback)
    result = result.sort_values(["생산계획년월", "공정"]).reset_index(drop=True)
    return CrossCheck(rows=result.loc[:, list(CROSS_CHECK_COLUMNS)], fallback_processes=fallback)


def _fill_missing_from_static(
    dynamic_available: pd.DataFrame,
    static_available: pd.DataFrame,
    static_rate: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Dynamic 이 못 덮는 월·공정을 Static 으로 채운다. 채운 공정 이름을 함께 돌려준다."""
    needed = static_rate.loc[:, ["생산계획년월", "공정"]].drop_duplicates()
    if dynamic_available.empty:
        covered = pd.DataFrame({"생산계획년월": [], "공정": []})
    else:
        covered = dynamic_available.loc[:, ["생산계획년월", "공정"]].drop_duplicates()

    gap = needed.merge(covered, on=["생산계획년월", "공정"], how="left", indicator=True)
    missing = gap.loc[gap["_merge"].ne("both"), ["생산계획년월", "공정"]]
    if missing.empty:
        return dynamic_available, []

    patch = missing.merge(
        static_available.loc[:, ["생산계획년월", "공정", "가용대수"]],
        on=["생산계획년월", "공정"],
        how="left",
    )
    patch["가용대수"] = patch["가용대수"].fillna(0.0)
    filled = pd.concat([dynamic_available, patch], ignore_index=True)
    fallback = sorted({str(value) for value in missing["공정"].dropna()})
    return filled, fallback
