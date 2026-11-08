# Purpose: 수율 실적 Gap 과 개선 우선순위 화면을 공통 실적 화면으로 그린다.

"""수율 실적 — 기준 대비 실적 Gap 과 개선 우선순위.

화면 한 벌은 `components/performance_actual_screen.py` 가 갖는다. 효율·UPEH·수율 세
화면이 **같은 질문을 지표만 바꿔** 묻기 때문이다. 이 파일이 갖는 것은 지표 사양과 머리
배지뿐이고 소개는 `guides/yield_actual.md` 다.
"""

from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import (
    MATURITY_BADGES,
    page_badges,
    render_page_header,
)
from capa_simulation.components.performance_actual_screen import (
    render_performance_actual_screen,
)
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.sample_data import pending_source_badge
from capa_simulation.services.performance_actuals import YIELD_METRIC

render_page_header(
    "수율 실적 (구현중)",
    badges=page_badges(MATURITY_BADGES["prototype"], pending_source_badge("수율 실적 DB")),
)
render_page_guide("yield_actual", title="수율 실적")

render_performance_actual_screen(
    YIELD_METRIC,
    key_prefix="yield_actual",
    process_labels=get_process_labels(),
)
