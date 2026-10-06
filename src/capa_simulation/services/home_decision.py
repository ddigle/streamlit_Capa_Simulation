# Purpose: HOME 상단 결론 요약이 읽을 확보율 판정을 필터 적용 상태로 집계한다.

"""표를 다 읽기 전에 **먼저 볼 곳**을 정한다.

HOME 은 월 열여덟 개와 공정 수십 개를 한 화면에 펼친다. 그 안에서 가장 낮은 곳을 눈으로
찾게 두지 않고 결론 한 줄로 먼저 말한다.

**판정은 화면에 보이는 것과 같아야 한다.** 그래서 두 가지를 지킨다.

- 공정 필터(`included_processes`)를 그대로 받는다. 사용자가 공정을 걸러 놓았으면 요약도
  거른 뒤의 최저값을 말해야 한다. 거르기 전 값을 말하면 화면에 없는 공정을 가리킨다.
- 구간 판정은 `securement_heatmap._tier` 와 **같은 부등호**를 쓴다. 경계가 갈리면 히트맵은
  「경고」로 칠한 칸을 요약이 「부족」이라고 부른다. 경계는 **그 달의 실효 기준**이다
  (`services/securement_threshold`) — 월별 예외가 있는 달은 그 달 기준으로 센다.

값이 없으면 0% 로 그리지 않고 「판정할 데이터 없음」으로 둔다 — 조회기간에 데이터가 없는
것과 확보율이 0 인 것은 다른 일이다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from capa_simulation.services.frame_contracts import require_columns
from capa_simulation.services.securement_threshold import SecurementThresholds

DECISION_COLUMNS = ("생산계획년월", "공정", "확보율")


@dataclass(frozen=True)
class CapacityDecision:
    """결론 한 줄과 그 근거. 화면 문구는 이 값으로만 만든다."""

    process: str | None
    month: int | None
    rate: float | None
    judged: int
    warning: int
    shortage: int

    @property
    def has_data(self) -> bool:
        return self.judged > 0

    @property
    def below(self) -> int:
        """기준 미달 공정·월. 경고와 부족을 합친 수다."""
        return self.warning + self.shortage


def build_capacity_decision(
    securement_rate: pd.DataFrame,
    *,
    included_processes: list[str] | None,
    thresholds: SecurementThresholds,
) -> CapacityDecision:
    """필터가 걸린 뒤의 공정·월 확보율에서 최저값과 구간별 개수를 낸다.

    정규화는 `build_monthly_bottleneck_ranking` 과 같은 차례다 — 공백을 떼고, 숫자로
    바꾸고, 셋 중 하나라도 비면 버린다. 그래야 「판정 가능한 수」가 그림이 센 것과 같다.
    """
    require_columns(securement_rate, list(DECISION_COLUMNS), "확보율")
    prepared = securement_rate.loc[:, list(DECISION_COLUMNS)].copy()
    prepared["공정"] = prepared["공정"].astype("string").str.strip()
    prepared["확보율"] = pd.to_numeric(prepared["확보율"], errors="coerce")
    prepared = prepared.dropna(subset=list(DECISION_COLUMNS))
    if included_processes is not None:
        prepared = prepared.loc[prepared["공정"].isin(included_processes)]
    if prepared.empty:
        return CapacityDecision(None, None, None, 0, 0, 0)

    rates = prepared["확보율"]
    # 행마다 그 달의 실효 기준을 맞대어 둔다. 월별 예외가 없으면 모든 행이 기본값이다.
    pairs = [thresholds.for_month(int(value)) for value in prepared["생산계획년월"]]
    secure_limits = pd.Series([pair[0] for pair in pairs], index=prepared.index, dtype="float64")
    warning_limits = pd.Series([pair[1] for pair in pairs], index=prepared.index, dtype="float64")
    # `_tier` 와 같은 부등호다. 확보는 초과, 경고는 이상, 나머지가 부족이다.
    shortage = int((rates < warning_limits).sum())
    warning = int((~(rates < warning_limits) & ~(rates > secure_limits)).sum())
    worst = prepared.loc[rates.idxmin()]
    return CapacityDecision(
        process=str(worst["공정"]),
        month=int(worst["생산계획년월"]),
        rate=float(worst["확보율"]),
        judged=int(len(prepared)),
        warning=warning,
        shortage=shortage,
    )
