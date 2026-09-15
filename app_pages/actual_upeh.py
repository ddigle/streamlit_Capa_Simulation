# Purpose: UPEH 실적 Gap 과 개선 우선순위 화면을 공통 실적 화면으로 그린다.

"""UPEH 실적 — 기준 대비 실적 Gap 과 개선 우선순위.

화면 한 벌은 `components/performance_actual_screen.py` 가 갖는다. 효율·UPEH·수율 세
화면이 **같은 질문을 지표만 바꿔** 묻기 때문이다. 이 파일이 갖는 것은 지표 사양과 머리말
문구뿐이다.
"""

import streamlit as st

from capa_simulation.components.page_header import (
    MATURITY_BADGES,
    page_badges,
    pending_badge,
    render_page_header,
)
from capa_simulation.components.performance_actual_screen import (
    render_performance_actual_screen,
)
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.services.performance_actuals import UPEH_METRIC

render_page_header(
    "UPEH 실적 (구현중)",
    description=(
        "생산이력의 공정·제품별 UPEH 실적을 Capa UPEH 기준정보와 비교하고, "
        "개선 우선순위와 조치 진행상태를 관리하는 화면입니다."
    ),
    badges=page_badges(MATURITY_BADGES["prototype"], pending_badge("생산이력 DB")),
)
st.caption(UPEH_METRIC.description)

render_performance_actual_screen(
    UPEH_METRIC,
    key_prefix="actual_upeh",
    process_labels=get_process_labels(),
)
