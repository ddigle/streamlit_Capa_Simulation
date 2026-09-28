# Purpose: 측정률 행이 없어 중립값으로 이어 간 건수를 화면에 알리는 한 줄을 그린다.

"""**메운 것을 말하지 않으면 완화가 곧 조용한 오류다.**

`RQ_LOT_RATIO`·`RQ_WF_RATIO` 에 (경로 + 월) 행이 없으면 대당 Capa 는 중립값 1.0 으로
이어 간다(`unit_capacity._join_reference`). 예전에는 그 자리에서 `ValueError` 로 화면
전체가 멈췄는데, 어차피 부하량이 없어 빠질 행 하나 때문에 그 값을 고칠 편집기조차 못
여는 쪽이 더 나빴다.

대신 **오차의 방향이 실제 측정률에 달려 있다.** 측정률은 대당 Capa 식의 분모라, 실제가
1 보다 작은 경로에 1.0 을 쓰면 대당 Capa 과소 → 소요대수 과대 → **확보율 과소**(보수 쪽)이고,
1 보다 큰 경로에서만 확보율 과대(낙관 쪽)다. 어느 쪽이든 보는 사람이 모르면 숫자를 그대로
믿는다.

그래서 이 한 줄은 장식이 아니라 완화의 **조건**이다. 계산이 계속되는 대신 무엇을 가정했는지
같은 화면에서 말한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import streamlit as st

from capa_simulation.services.unit_capacity import CapacityAssumptions

# 표 이름을 화면 라벨로. 사용자가 여는 탭 이름과 같아야 어디를 고칠지 바로 안다.
_TABLE_LABELS: Mapping[str, str] = {
    "RQ_LOT_RATIO": "Lot측정률",
    "RQ_WF_RATIO": "WF측정률",
}
# 문장에 적는 달의 수. 넘으면 「외 N개월」로 줄인다.
MONTH_LIST_LIMIT = 6


def assumption_message(
    assumed: Mapping[str, int],
    months: Mapping[str, Sequence[int]] | None = None,
) -> str:
    """가정 건수와 그 달을 한 문장으로. 빈 값이면 빈 문자열이라 호출부가 분기를 줄인다.

    **시나리오 전체 기간 기준이다.** 대당 Capa 는 전체 기간을 한 번에 계산하므로 조회기간
    밖의 달도 센다. 그래서 달을 함께 적는다 — 건수만 말하면 어느 달 칸을 채울지 다시 찾아야
    하고, 보는 기간에 없는 달이면 왜 떴는지도 모른다.
    """
    parts = []
    for table, count in assumed.items():
        if not count:
            continue
        part = f"{_TABLE_LABELS.get(table, table)} {count:,}건"
        table_months = tuple((months or {}).get(table, ()))
        if table_months:
            part += f"({_month_list(table_months)})"
        parts.append(part)
    if not parts:
        return ""
    return (
        "측정률 행이 없어 **중립값 1.0 으로 계산한 경로가 있습니다**(시나리오 전체 기준) — "
        f"{' · '.join(parts)}. "
        "측정률은 대당 Capa 의 분모라 실제가 1 보다 작으면 **확보율이 실제보다 낮게**, "
        "1 보다 크면 높게 나옵니다. "
        "기준 정보 페이지의 해당 탭에서 그 달 칸을 채우면 정확해집니다."
    )


def _month_list(months: Sequence[int], limit: int = MONTH_LIST_LIMIT) -> str:
    """앞 몇 달만 적고 나머지는 개수로 줄인다. 달이 많으면 문장이 표가 된다."""
    shown = ", ".join(f"{month // 100}-{month % 100:02d}" for month in months[:limit])
    rest = len(months) - limit
    return f"{shown} 외 {rest}개월" if rest > 0 else shown


def render_capacity_assumption_notice(assumptions: CapacityAssumptions) -> None:
    """가정이 있을 때만 그린다. 없는 날에 자리를 차지하면 다음에는 아무도 안 읽는다."""
    message = assumption_message(assumptions.counts, assumptions.months)
    if message:
        st.warning(message, icon=":material/rule:")
