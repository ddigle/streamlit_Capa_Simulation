# Purpose: 수율 실적 Gap 과 개선 우선순위 화면을 공통 실적 화면으로 그린다.

"""수율 실적 — 기준 대비 실적 Gap 과 개선 우선순위.

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
from capa_simulation.services.performance_actuals import YIELD_METRIC

render_page_header(
    "수율 실적 (구현중)",
    description=(
        "공정·제품별 수율 실적을 Capa 기준정보(RQ_YLD)의 수율과 비교하고, "
        "개선 우선순위와 조치 진행상태를 관리하는 화면입니다."
    ),
    badges=page_badges(MATURITY_BADGES["prototype"], pending_badge("수율 실적 DB")),
)
st.caption(YIELD_METRIC.description)

render_performance_actual_screen(
    YIELD_METRIC,
    key_prefix="yield_actual",
    process_labels=get_process_labels(),
)
