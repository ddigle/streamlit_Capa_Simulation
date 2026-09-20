# Purpose: HOME 상단에 결론·근거·다음 확인 한 묶음을 그린다.

"""결론 → 근거 → 다음 확인.

표를 다 읽기 전에 **먼저 볼 공정·월**과 그렇게 본 근거를 말한다. 문장은 이미 구한 집계
(`services.home_decision`)에서 결정론적으로 만든다 — 여기서 다시 계산하지 않는다.

**필터가 걸린 뒤의 값이다.** 사용자가 공정을 걸러 놓았으면 요약도 거른 뒤의 최저값을
말한다. 그러지 않으면 화면에 없는 공정을 가리키게 된다.
"""

from __future__ import annotations

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.services.home_decision import CapacityDecision
from capa_simulation.services.month_columns import month_label

NO_DATA_NOTICE = "조회기간에 판정할 확보율 데이터가 없습니다."


def _tone(decision: CapacityDecision, *, secure_threshold: float, warning_threshold: float) -> str:
    """최저 구간의 색. `securement_heatmap._tier` 와 같은 부등호를 쓴다."""
    rate = decision.rate
    if rate is None:
        return tokens.TEXT_MUTED
    if rate > secure_threshold:
        return tokens.STATUS_SECURE
    if rate >= warning_threshold:
        return tokens.STATUS_WARNING
    return tokens.STATUS_SHORTAGE


def render_home_capacity_decision(
    decision: CapacityDecision,
    *,
    secure_threshold: float,
    warning_threshold: float,
    process_label: str | None = None,
    filtered: bool = False,
) -> None:
    """HOME 맨 위의 결론 묶음. `Main` 탭의 공지 바로 아래에 선다.

    `process_label` 은 화면 표시명이다. 저장 키는 원본 공정명이므로 여기서 바꾸지 않고
    **부르는 이름만** 받는다.
    """
    if not decision.has_data:
        st.info(NO_DATA_NOTICE, icon=":material/help:")
        return

    name = process_label or decision.process or ""
    month = month_label(decision.month) if decision.month is not None else ""
    rate = decision.rate or 0.0
    tone = _tone(decision, secure_threshold=secure_threshold, warning_threshold=warning_threshold)
    scope = "선택한 공정 기준" if filtered else "전체 공정 기준"

    with st.container(border=True, key="home_capacity_decision"):
        st.markdown(
            f"가장 낮은 확보율은 "
            f'<b style="color:{tone}">{name} · {month}</b> 입니다 — '
            f'<b style="color:{tone}">{rate:.1%}</b>',
            unsafe_allow_html=True,
        )
        # 「몇 건이 미달인가」는 「몇 건을 봤는가」 없이는 뜻이 없다. 분모를 함께 적는다.
        st.caption(
            f":material/fact_check: {scope} · 판정 가능한 {decision.judged:,} 공정·월 중 "
            f"기준 미달 {decision.below:,} — 경고 {decision.warning:,} · 부족 {decision.shortage:,}"
        )
