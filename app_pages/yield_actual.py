# Purpose: Dynamic Capa의 공정·제품별 수율 실적 화면 자리를 잡는다.

"""수율 실적 — 아직 화면 구조를 잡지 않은 빈 자리다.

구성과 지표는 실적 DB 의 수율 컬럼 계약이 정해진 뒤에 붙인다. 지금 표를 먼저 그려 두면
연결 시점에 그 모양을 다시 뜯게 되고, 무엇보다 **합성 표본으로 채운 화면이 실적처럼 읽힌다.**
"""

import streamlit as st

from capa_simulation.components.page_header import (
    MATURITY_BADGES,
    page_badges,
    pending_badge,
    render_page_header,
)

render_page_header(
    "수율 실적 (구현중)",
    description=(
        "공정·제품별 수율 실적을 Capa 기준정보의 수율과 비교하는 화면입니다. "
        "아직 화면을 구성하지 않았습니다."
    ),
    badges=page_badges(MATURITY_BADGES["draft"], pending_badge("데이터")),
)
st.info(
    "아직 빈 화면입니다. 실적 DB 의 수율 컬럼 계약(집계 구간·공정·제품 매핑)이 정해지면 "
    "조회 조건과 지표를 붙입니다.",
    icon=":material/database:",
)
