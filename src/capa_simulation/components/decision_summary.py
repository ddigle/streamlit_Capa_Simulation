# Purpose: HOME 상단에 결론·근거·다음 확인 한 묶음을 그린다.

"""결론 → 근거 → 다음 확인.

표를 다 읽기 전에 **먼저 볼 공정·월**과 그렇게 본 근거를 말한다. 문장은 이미 구한 집계
(`services.home_decision`)에서 결정론적으로 만든다 — 여기서 다시 계산하지 않는다.

**필터가 걸린 뒤의 값이다.** 사용자가 공정을 걸러 놓았으면 요약도 거른 뒤의 최저값을
말한다. 그러지 않으면 화면에 없는 공정을 가리키게 된다.
"""

from __future__ import annotations

import html

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.services.home_decision import CapacityDecision
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.securement_threshold import SecurementThresholds

NO_DATA_NOTICE = "조회기간에 판정할 확보율 데이터가 없습니다."


def _tone(decision: CapacityDecision, *, thresholds: SecurementThresholds) -> str:
    """최저 구간의 **면**색. `home_figures.capacity_status` 와 같은 부등호를 그 달의 기준으로 쓴다.

    `STATUS_*` 는 칸을 칠하고 그 위에 `TEXT` 를 얹는 색이다(토큰 설명). 글자색으로 쓰면 어두운
    테마에서 부족 2.0:1·경고 3.3:1 로 결론 문장이 읽히지 않았고, 밝은 테마의 확보 회색도 흰
    면에서 1.5:1 이었다(2026-10-05 E2E). 그래서 이 색은 강조 칸의 바탕에 깔고 글자는 `TEXT` 로
    쓴다 — 두 테마 모두 토큰이 보증하는 짝(밝게 4.8:1·어둡게 4.5:1 이상)이다.
    """
    rate = decision.rate
    if rate is None:
        return tokens.SURFACE_SUBTLE
    # 상태 → 색 짝은 함수 안에서 만든다. 모듈 상수로 올리면 처음 임포트한 순간의 팔레트가
    # 굳어 테마를 바꿔도 이 색만 따라오지 않는다.
    return {
        "secure": tokens.STATUS_SECURE,
        "warning": tokens.STATUS_WARNING,
        "shortage": tokens.STATUS_SHORTAGE,
    }[thresholds.status(rate, decision.month)]


def render_home_capacity_decision(
    decision: CapacityDecision,
    *,
    thresholds: SecurementThresholds,
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
    tone = _tone(decision, thresholds=thresholds)
    scope = "선택한 공정 기준" if filtered else "전체 공정 기준"

    chip = (
        f"background:{tone};color:{tokens.TEXT};padding:0 0.3em;border-radius:4px;"
        "box-decoration-break:clone;-webkit-box-decoration-break:clone"
    )
    with st.container(border=True, key="home_capacity_decision"):
        st.markdown(
            f"가장 낮은 확보율은 "
            f'<b style="{chip}">{html.escape(name)} · {month}</b> 입니다 — '
            f'<b style="{chip}">{rate:.1%}</b>',
            unsafe_allow_html=True,
        )
        # 「몇 건이 미달인가」는 「몇 건을 봤는가」 없이는 뜻이 없다. 분모를 함께 적는다.
        st.caption(
            f":material/fact_check: {scope} · 판정 가능한 {decision.judged:,} 공정·월 중 "
            f"기준 미달 {decision.below:,} — 경고 {decision.warning:,} · 부족 {decision.shortage:,}"
        )
