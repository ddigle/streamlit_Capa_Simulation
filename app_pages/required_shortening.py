# Purpose: 설비 일정·소요대수로 목표 확보율을 채울 Qual 단축 화면과 Qual 마감 계산기 팝업을 그린다.

"""필요 단축 일정(실행 관리 아래, 공정 Capa 상세 다음 — 2026-10-18 사용자 결정).

정체성(2026-10-22 사용자 요청): **단축이 필요한 공정 전부의 진척 관리 한 페이지**다 — 공정 진척
보드, 기한 임박·이행 지연, 공정 카드. 공정 하나를 깊게 보는 일은 카드의 「공정 Capa 상세에서 근거
보기」 로 공정 Capa 상세에 넘긴다.

가용설비 현황의 한 탭이던 것을 별도 페이지로 뗐다. 그 탭이 페이지에서 받던 것을 이 페이지가 스스로
모은다 — 설비 운영 DB 의 저장본 사본·미저장 편집본(`equipment_data_workspace`, 가용설비 현황·Space
현황과 같은 세션 칸), 샘플 fleet 스위치(같은 공용 칸), 저장된 공정별 Cut-off(가용설비 현황 머리
「설정」 팝업에서 고친다), 활성 시나리오의 소요대수 로더. 그림·조건·진척 비교는 그대로
`required_shortening_panel` 이다.

머리 끝의 「Qual 마감 계산기」 단추는 큰 팝업을 연다(2026-10-24 사용자 결정 — 가용설비 현황의
탭이던 것). 계산기는 설비 데이터와 잇지 않아 호기가 없어도 열리므로 팝업 호스트는 머리 바로 뒤,
데이터를 읽기 전이다. 호스트는 이벤트 칸에 늘 한 자리를 쓴다 — 열렸으면 팝업, 아니면 빈 스타일
자리표시자다. 그 뒤의 기준선 알림 토스트 자리(`shortening_progress_panel`)가 팝업을 여닫을 때
밀리지 않게 한다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_data_workspace import (
    EQUIPMENT_DRAFT_KEY,
    calculation_drafts,
    ensure_equipment_drafts,
    pop_discarded_notice,
)
from capa_simulation.components.equipment_scenario_status import (
    baseline_equipment_refusal,
    render_equipment_scenario_row,
    render_legacy_trace_warning,
    shortening_equipment_basis,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.qual_deadline_calculator import render_qual_deadline_calculator
from capa_simulation.components.required_shortening_panel import render_required_shortening_tab
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY, render_sample_switch
from capa_simulation.components.shortening_progress_panel import reserve_baseline_notice_slots
from capa_simulation.equipment_scenario_activation import (
    EquipmentSession,
    resolve_equipment_session,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    PageContext,
    bootstrap_error_message,
    forget_page_dialogs,
    load_page_context,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_process_cutoff,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
)
from capa_simulation.services.simulation_cache import (
    ScenarioCacheKey,
    check_scenario_capacity,
    scenario_cache_key,
    scenario_required_equipment,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card


def _baseline_refusal(*, sample: bool, session: EquipmentSession | None = None) -> str | None:
    """「기준선 저장」 을 막을 까닭. 기준선은 모든 사용자가 보는 고칠 수 없는 기록이라 합성 샘플에서
    만들지 않고, 설비는 **공식 발행 쌍**에서만 얼린다(E5 — 진척 비교 기준선은 공식에서만 저장).

    공식 발행 쌍이 아닌 까닭은 둘로 가른다 — 가정 설비 시나리오, 또는 공식 시나리오의 발행하지
    않은 리비전. 미저장 설비 편집(RawData 제출·Space 배치)은 막지 않는다 — 그 편집은 편집본(buffer)
    에만 있고 계산은 저장본 사본(draft)만 읽으므로, 화면의 계획은 늘 저장 리비전 그대로다.
    """
    if sample:
        return (
            "샘플 데이터를 보는 중이라 기준선을 저장하지 않습니다 — 공용 기록은 저장된 호기 "
            "마스터에서만 만듭니다."
        )
    return baseline_equipment_refusal(session)


# 머리말 한 줄 — 이 화면의 정체성. 공정 Capa 상세 머리말과 짝이다.
PAGE_DESCRIPTION = (
    "단축이 필요한 공정 전부의 진척 관리 한 페이지 — 공정 진척 보드 · 기한 임박 · 이행 지연 · "
    "공정 카드. 공정 하나를 깊게 보려면 카드의 「공정 Capa 상세에서 근거 보기」 입니다."
)

# 이 화면의 팝업 칸(페이지에 한 칸 — 값이 팝업을 가른다, AGENTS 9장 「팝업과 콜백」).
DIALOG_KEY = f"required_shortening{PAGE_DIALOG_SUFFIX}"
QUAL_CALCULATOR_DIALOG = "qual_calculator"
QUAL_CALCULATOR_BUTTON_KEY = "required_shortening_qual_calculator_v1"


def _open_qual_calculator() -> None:
    """여는 단추의 콜백 — 다른 팝업 칸(사이드바 조건 팝업 등)부터 비운다."""
    forget_page_dialogs()
    st.session_state[DIALOG_KEY] = QUAL_CALCULATOR_DIALOG


def _close_dialog() -> None:
    st.session_state.pop(DIALOG_KEY, None)


@st.dialog("Qual 마감 계산기", width="large", icon=":material/calculate:", on_dismiss=_close_dialog)
def _qual_calculator_dialog(today: date) -> None:
    render_qual_deadline_calculator(today=today)


def _render_header_actions() -> None:
    st.button(
        "Qual 마감 계산기",
        icon=":material/calculate:",
        key=QUAL_CALCULATOR_BUTTON_KEY,
        on_click=_open_qual_calculator,
        help=(
            "Cut-off · 월별 목표 가용대수 · 신규 호기로 호기마다 Qual 완료 마감을 내는 "
            "계산기입니다. 설비 데이터와 잇지 않습니다."
        ),
    )


render_page_header("필요 단축 일정", description=PAGE_DESCRIPTION, trailing=_render_header_actions)
render_page_guide("required_shortening", title="필요 단축 일정")
notices = st.container()

today = date.today()
# 팝업 호스트 — 이벤트 칸에 늘 한 자리(모듈 설명). 데이터를 읽기 전이라 호기가 없거나 설비 DB 를
# 못 읽어도 계산기는 열린다.
if st.session_state.get(DIALOG_KEY) == QUAL_CALCULATOR_DIALOG:
    _qual_calculator_dialog(today)
else:
    st.html("<style></style>")
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    repository = get_equipment_repository(equipment_database_path)
    # 세션이 든 설비 시나리오(새 세션은 공식) — 공통 최신 + 고른 일정 리비전의 합친 스냅샷.
    equipment_session = resolve_equipment_session(equipment_database_path)
    latest_snapshot = equipment_session.snapshot
    # 저장된 Cut-off. 고치는 곳은 가용설비 현황 머리 「설정」 팝업이다.
    stored_cutoff = load_process_cutoff(equipment_database_path)
except BOOTSTRAP_ERRORS as exc:
    st.error(
        "설비 일정을 준비하지 못했습니다. "
        + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
    )
    st.stop()
with notices:
    render_schema_ahead_warning(repository.schema_ahead)
    render_legacy_trace_warning(equipment_session)

# 저장본 사본과 미저장 편집본 — 가용설비 현황·Space 현황과 같은 세션 칸이라 어디서 먼저 세웠어도
# 같은 토큰이다. 계산은 저장본 사본만 읽는다.
ensure_equipment_drafts(latest_snapshot)
discarded_notice = pop_discarded_notice()
if discarded_notice:
    notices.warning(discarded_notice, icon=":material/sync_problem:")
render_equipment_scenario_row(equipment_session)
# 계산은 이 설비 시나리오에 일정이 없는 호기와 그 비가동을 뺀 저장본 사본(F4)이다.
baseline, equipment, downtime = calculation_drafts()
using_dashboard_sample = st.session_state[EQUIPMENT_DRAFT_KEY].empty

show_sample_fleet = bool(st.session_state.get(SAMPLE_TOGGLE_KEY, True))
if using_dashboard_sample:
    show_sample_fleet = render_sample_switch(key="shortening_sample_switch", source="설비 운영 DB")
# 합성값은 조회에만 쓴다(가용설비 현황 Main 과 같은 fleet).
dashboard_equipment = (
    sample_equipment_master(anchor_date=today)
    if using_dashboard_sample and show_sample_fleet
    else equipment
)
dashboard_downtime = (
    sample_downtime_schedule(anchor_date=today)
    if using_dashboard_sample and show_sample_fleet
    else downtime
)
dashboard_baseline = (
    sample_equipment_baseline()
    if latest_snapshot is None and baseline.empty and using_dashboard_sample and show_sample_fleet
    else baseline
)

# 거르는 조건(기간·공정)은 사이드바 조건 카드다. 목표 확보율·진척 비교는 본문 맨 위다.
conditions_card = condition_card("필요 단축 일정 조건", name="shortening")
if using_dashboard_sample and not show_sample_fleet:
    with conditions_card:
        st.caption(
            "조회할 호기가 없습니다. 가용설비 현황 RawData 에서 입력하거나 샘플 데이터를 켜세요."
        )
    st.info(
        "등록된 호기가 없습니다. 가용설비 현황 RawData 에서 설비 마스터를 입력하거나 샘플 데이터를 "
        "켜서 화면을 살펴보세요."
    )
    reserve_baseline_notice_slots()
    st.stop()

# 소요대수는 활성 시나리오에 있다. 여기서는 계산이 서는지만 본다(적중이면 프레임을 풀지 않는다).
# 패널은 같은 시나리오 키와 로더로 달 범위·계획을 꺼낸다 — 소요대수는 그 캐시가 빗나갈 때만, 한
# 회차에 한 번만 푼다. 못 읽었거나 계산이 멈췄으면 패널이 본문에 까닭을 알린다.
shortening_context: PageContext | None = None
shortening_key: ScenarioCacheKey | None = None
shortening_demand: Callable[[], pd.DataFrame] | None = None
shortening_error: str | None = None
try:
    shortening_context = load_page_context()
    candidate_key = scenario_cache_key(
        shortening_context.reference_version,
        shortening_context.active_scenario,
        shortening_context.selected_start_month,
        shortening_context.selected_end_month,
    )
    candidate_demand = scenario_required_equipment(
        candidate_key,
        scenario_tables=shortening_context.active_scenario["tables"],
        reference_tables=shortening_context.reference_tables,
    )
    check_scenario_capacity(
        candidate_key,
        _scenario_tables=shortening_context.active_scenario["tables"],
        _reference_tables=shortening_context.reference_tables,
        _required_equipment=candidate_demand,
    )
    shortening_key, shortening_demand = candidate_key, candidate_demand
except BOOTSTRAP_ERRORS as exc:
    shortening_error = bootstrap_error_message(
        exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
    )
render_required_shortening_tab(
    equipment=dashboard_equipment,
    downtime=dashboard_downtime,
    baseline=dashboard_baseline,
    cutoff=stored_cutoff,
    today=today,
    context=shortening_context,
    required_equipment=shortening_demand,
    required_equipment_key=shortening_key,
    scenario_error=shortening_error,
    conditions=conditions_card,
    # 거르는 조건(기간·공정)은 이 DB 의 공용 프로필이고(0019) 진척 비교 기준선도 이 DB 다(0021).
    # 기준선 머리에 화면의 호기가 나온 저장 리비전을 남긴다.
    equipment_database_path=equipment_database_path,
    equipment_revision_id=(
        None
        if using_dashboard_sample or latest_snapshot is None
        else latest_snapshot.revision.revision_id
    ),
    equipment_revision_no=(
        None
        if using_dashboard_sample or latest_snapshot is None
        else latest_snapshot.revision.revision_no
    ),
    baseline_refusal=_baseline_refusal(sample=using_dashboard_sample, session=equipment_session),
    # 공정 Capa 상세는 설비 저장본만 본다 — 샘플 fleet 카드에서는 근거 링크를 숨긴다.
    link_details=not using_dashboard_sample,
    # 기준선 머리의 설비 시나리오 출처(공식 발행 쌍에서만 저장)·진척 비교 머리·카드 링크 `eq`.
    equipment_basis=(
        None if using_dashboard_sample else shortening_equipment_basis(equipment_session)
    ),
)
