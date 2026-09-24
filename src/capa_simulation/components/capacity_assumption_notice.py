# Purpose: 측정률 행이 없어 중립값으로 이어 간 건수를 화면에 알리는 한 줄을 그린다.

"""**메운 것을 말하지 않으면 완화가 곧 조용한 오류다.**

`RQ_LOT_RATIO`·`RQ_WF_RATIO` 에 (경로 + 월) 행이 없으면 대당 Capa 는 중립값 1.0 으로
이어 간다(`unit_capacity._join_reference`). 예전에는 그 자리에서 `ValueError` 로 화면
전체가 멈췄는데, 어차피 부하량이 없어 빠질 행 하나 때문에 그 값을 고칠 편집기조차 못
여는 쪽이 더 나빴다.

대신 **오차가 한 방향으로만 난다.** 측정률은 대당 Capa 식의 분모라, 실제가 1 보다 작은
경로에 1.0 을 쓰면 대당 Capa 과대 → 소요대수 과소 → **확보율 과대**다. 여유 있어 보이는
쪽으로만 틀리므로, 보는 사람이 그 사실을 모르면 판단이 그대로 낙관으로 기운다.

그래서 이 한 줄은 장식이 아니라 완화의 **조건**이다. 계산이 계속되는 대신 무엇을 가정했는지
같은 화면에서 말한다.
"""

from __future__ import annotations

from collections.abc import Mapping

import streamlit as st

# 표 이름을 화면 라벨로. 사용자가 여는 탭 이름과 같아야 어디를 고칠지 바로 안다.
_TABLE_LABELS: Mapping[str, str] = {
    "RQ_LOT_RATIO": "Lot측정률",
    "RQ_WF_RATIO": "WF측정률",
}


def assumption_message(assumed: Mapping[str, int]) -> str:
    """가정 건수를 한 문장으로. 빈 값이면 빈 문자열이라 호출부가 분기를 줄인다."""
    parts = [
        f"{_TABLE_LABELS.get(table, table)} {count:,}건"
        for table, count in assumed.items()
        if count
    ]
    if not parts:
        return ""
    return (
        f"측정률 행이 없어 **중립값 1.0 으로 계산한 경로가 있습니다** — {' · '.join(parts)}. "
        "측정률은 대당 Capa 의 분모라 실제가 1 보다 작으면 **확보율이 실제보다 높게** 나옵니다. "
        "기준 정보 페이지의 해당 탭에서 그 달 칸을 채우면 정확해집니다."
    )


def render_capacity_assumption_notice(assumed: Mapping[str, int]) -> None:
    """가정이 있을 때만 그린다. 없는 날에 자리를 차지하면 다음에는 아무도 안 읽는다."""
    message = assumption_message(assumed)
    if message:
        st.warning(message, icon=":material/rule:")
