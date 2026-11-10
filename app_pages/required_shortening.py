# Purpose: 설비 일정·소요대수로 목표 확보율을 채울 Qual 단축 화면과 Qual 마감 계산기 팝업을 그린다.

"""필요 단축 일정(실행 관리 아래, 공정 Capa 상세 다음 — 2026-10-18 사용자 결정).

정체성(2026-10-22 사용자 요청): **단축이 필요한 공정 전부의 진척 관리 한 페이지**다 — 공정 진척
보드, 기한 임박·이행 지연, 공정 카드. 공정 하나를 깊게 보는 일은 카드의 「공정 Capa 상세에서 근거
보기」 로 공정 Capa 상세에 넘긴다.

가용설비 현황의 한 탭이던 것을 별도 페이지로 뗐다. 그 탭이 페이지에서 받던 것을 이 페이지가 스스로
모은다 — 설비 운영 DB 의 저장본 사본·미저장 편집본(`equipment_data_workspace`, 가용설비 현황·Space
현황과 같은 세션 칸), 샘플 fleet 스위치(같은 공용 칸), 저장된 공정별 Cut-off(가용설비 현황 사이드바
「가용설비 설정」 팝업에서 고친다), 활성 시나리오의 소요대수 로더. 그림·조건·진척 비교는 그대로
`required_shortening_panel` 이다.

사이드바 팝업 상자 「Qual 마감 계산기」(조회 조건 패널 바로 밑 · 조건 카드 위 — 2026-11-09 사용자
검수 g03-1 「Qual 마감 계산기도 사이드바 조건박스 상자로 이동」, 그 전에는 머리 끝 단추)가 큰 팝업을
연다(2026-10-24 사용자 결정 — 가용설비 현황의 탭이던 것). 상자는 설정 상자와 같은 꼴(상자 = 단추
→ 같은 제목 팝업 — `settings_box.render_settings_box`)이고 설정이 아니라 도구다. 데이터를 읽기
전에 세워 호기가 없거나 설비 DB 를 못 읽은 회차에도 같은 자리에 선다. 팝업은 키 붙은 호스트
프래그먼트가 부른다(`components/dialog_host.py` — 열기 · 닫기가 페이지를 다시 계산하지 않는다,
설계 규칙 UI-PRF-01). 계산기는 설비 데이터와 잇지 않아 호기가 없어도
열리므로 호스트는 머리 바로 뒤, 데이터를 읽기 전 · 멈춤(`st.stop()`) 앞에서 매 앱 전체 회차 선다.
호스트는 이벤트 칸에 늘 한 자리를 쓴다 — 열렸으면 팝업, 아니면 빈 스타일 자리표시자다. 그 뒤의
기준선 결과 알림 표지 자리(`shortening_progress_panel` — 본문 프래그먼트 안)가 팝업을 여닫을 때
밀리지 않게 한다. 계산기 입력은 닫아도 남는다(`persist_state` · 원본 표 칸) — 닫기가 지우는 것은
붙여넣기 글 칸 초안 하나다.

사이드바 조회 조건 패널의 **목표 확보율** 줄(값 칸 + 팝업 — Space 「필요 단축」 보기와 같은 부품,
2차 보드 Q2-26)도 같은 호스트가 연다(`required_shortening_panel.LEVEL_FIELD`). 줄은 호스트 바로
뒤 — 데이터를 읽기 전에 세워 멈춘 회차에도 서고 고를 수 있다. 호기가 없는 회차에는 같은 자리이고,
설비 DB 를 못 읽은 회차에는 그 앞 「설비 시나리오」 줄이 서지 않아 한 줄만큼 위에 선다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.equipment_data_workspace import (
    EQUIPMENT_DRAFT_KEY,
    calculation_drafts,
    ensure_equipment_drafts,
    render_reopen_notices,
    rerun_if_head_stale,
)
from capa_simulation.components.equipment_scenario_status import (
    baseline_equipment_refusal,
    render_equipment_scenario_row,
    render_legacy_trace_warning,
    shortening_equipment_basis,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.qual_deadline_calculator import (
    PASTE_TEXT_KEY,
    render_qual_deadline_calculator,
)
from capa_simulation.components.required_shortening_panel import (
    LEVEL_FIELD,
    SHORTENING_DIALOG_HOST,
    render_required_shortening_tab,
)
from capa_simulation.components.sample_data import (
    NO_UNITS_HELP,
    NO_UNITS_MARK,
    SAMPLE_TOGGLE_KEY,
    render_sample_switch,
)
from capa_simulation.components.settings_box import render_settings_box
from capa_simulation.components.shortening_source import (
    load_shortening_demand,
    shortening_frames,
)
from capa_simulation.equipment_scenario_activation import (
    EquipmentSession,
    resolve_equipment_session,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PageContext,
    bootstrap_error_message,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_floor_states,
    load_process_cutoff,
)
from capa_simulation.services.simulation_cache import ScenarioCacheKey
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card


def _baseline_refusal(*, sample: bool, session: EquipmentSession | None = None) -> str | None:
    """「기준선 저장」 을 막을 까닭. 기준선은 모든 사용자가 보는 고칠 수 없는 기록이라 합성 샘플에서
    만들지 않고, 설비는 **공식 발행 쌍**에서만 얼린다(E5 — 진척 비교 기준선은 공식에서만 저장).

    공식 발행 쌍이 아닌 까닭은 둘로 가른다 — 가정 설비 시나리오, 또는 공식 시나리오의 발행하지 않은
    리비전. 미저장 설비 편집(설비 마스터 제출·Space 배치)은 막지 않는다 — 그 편집은 편집본(buffer)
    에만 있고 계산은 저장본 사본(draft)만 읽으므로, 화면의 계획은 늘 저장 리비전 그대로다.
    """
    if sample:
        return (
            "샘플 데이터를 보는 중이라 기준선을 저장하지 않습니다 — 공용 기록은 저장된 호기 "
            "마스터에서만 만듭니다."
        )
    return baseline_equipment_refusal(session)


# 이 화면의 팝업 호스트(페이지에 한 칸 — 값이 팝업을 가른다, AGENTS 9장 「팝업과 콜백」). 목표
# 확보율 줄이 같은 호스트로 열어 컴포넌트 쪽에 둔다.
DIALOG_HOST = SHORTENING_DIALOG_HOST
QUAL_CALCULATOR_DIALOG = "qual_calculator"
QUAL_CALCULATOR_BUTTON_KEY = "required_shortening_qual_calculator_v1"


@st.dialog(
    "Qual 마감 계산기", width="large", icon=":material/calculate:", on_dismiss=DIALOG_HOST.close
)
def _qual_calculator_dialog(today: date) -> None:
    """설비 데이터와 잇지 않는 계산기 — 원본을 바꾸는 동작이 없어 앱 전체를 다시 돌리지 않는다."""
    render_qual_deadline_calculator(today=today)


def _open_qual_calculator() -> None:
    """사이드바 「Qual 마감 계산기」 상자의 콜백 — 화면 팝업 호스트만 다시 돌려 연다."""
    DIALOG_HOST.open(QUAL_CALCULATOR_DIALOG, QUAL_CALCULATOR_BUTTON_KEY)


# 화면 소개(정체성 한 문장)는 Guide 첫 단락이 맡는다 — 머리에 설명 줄을 두지 않는다(그림 메모 g03,
# 설계 규칙 UI-TXT-01). 머리 끝 칸도 비운다 — 계산기 단추는 사이드바 상자다(2026-11-09 사용자 검수
# g03-1, 페이지 상단 문구 · 여백 최소화).
render_page_header("필요 단축 일정")
render_page_guide("required_shortening", title="필요 단축 일정")
notices = st.container()
# 사이드바 「Qual 마감 계산기」 상자 — 조회 조건 패널 바로 밑 · 조건 카드 위(카드보다 먼저 부른다).
# 단추 key 는 옮기기 전 그대로다(시험 · 화면 확인이 산다).
render_settings_box(
    "Qual 마감 계산기",
    name="qual_calculator",
    button_key=QUAL_CALCULATOR_BUTTON_KEY,
    on_click=_open_qual_calculator,
    tooltip=(
        "Cut-off · 월별 목표 가용대수 · 신규 호기로 호기마다 Qual 완료 마감을 내는 "
        "계산기입니다. 설비 데이터와 잇지 않습니다."
    ),
    icon=":material/calculate:",
)

today = date.today()
# 팝업 호스트 — 매 앱 전체 회차 빠짐없이, 이벤트 칸에 늘 한 자리(모듈 설명). 데이터를 읽기 전이라
# 호기가 없거나 설비 DB 를 못 읽어도 계산기는 열린다. 닫기는 붙여넣기 글 칸 초안만 지운다 — 숫자 ·
# 날짜 칸과 편집표는 닫아도 남는 입력이다(`qual_deadline_calculator` 모듈 설명).
DIALOG_HOST.render(
    {
        QUAL_CALCULATOR_DIALOG: partial(_qual_calculator_dialog, today),
        **{value: body for value, (body, _) in LEVEL_FIELD.dialogs.items()},
    },
    widget_keys={
        QUAL_CALCULATOR_DIALOG: (PASTE_TEXT_KEY,),
        **{value: keys for value, (_, keys) in LEVEL_FIELD.dialogs.items()},
    },
)
# 사이드바 조회 조건 패널의 목표 확보율 줄 — 데이터를 읽기 전이라 멈춘 회차에도 선다(설비 DB 를
# 못 읽은 회차에는 설비 시나리오 줄이 서지 않아 한 줄 위 — 모듈 설명).
LEVEL_FIELD.render()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    repository = get_equipment_repository(equipment_database_path)
    # 세션이 든 설비 시나리오(새 세션은 공식) — 공통 최신 + 고른 일정 리비전의 합친 스냅샷.
    equipment_session = resolve_equipment_session(equipment_database_path)
    latest_snapshot = equipment_session.snapshot
    # 저장된 Cut-off. 고치는 곳은 가용설비 현황 사이드바 「가용설비 설정」 팝업이다.
    stored_cutoff = load_process_cutoff(equipment_database_path)
    # 카드 「도면에서 보기」 가 열 층에서 뺄 비활성 층(Space 층 사용 0029 — 링크 대상이 아니다).
    inactive_floors = frozenset(load_floor_states(equipment_database_path).inactive)
except BOOTSTRAP_ERRORS as exc:
    message = "설비 일정을 준비하지 못했습니다. " + bootstrap_error_message(
        exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)
    )
    render_data_error(message, code="RS-01", text="필요 단축 일정을 준비하지 못했습니다(설비 DB)")
    st.stop()
with notices:
    render_schema_ahead_warning(repository.schema_ahead)
    render_legacy_trace_warning(equipment_session)

# 저장본 사본과 미저장 편집본 — 가용설비 현황·Space 현황과 같은 세션 칸이라 어디서 먼저 세웠어도
# 같은 토큰이다. 계산은 저장본 사본만 읽는다.
ensure_equipment_drafts(latest_snapshot)
with notices:
    render_reopen_notices()
render_equipment_scenario_row(equipment_session)
# 계산은 이 설비 시나리오에 일정이 없는 호기와 그 비가동을 뺀 저장본 사본(F4)이다.
baseline, equipment, downtime = calculation_drafts()
using_dashboard_sample = st.session_state[EQUIPMENT_DRAFT_KEY].empty

show_sample_fleet = bool(st.session_state.get(SAMPLE_TOGGLE_KEY, True))
if using_dashboard_sample:
    show_sample_fleet = render_sample_switch(key="shortening_sample_switch", source="설비 운영 DB")
# 합성값은 조회에만 쓴다(가용설비 현황 Main 과 같은 fleet). Space 「필요 단축」 보기가 같은 함수로
# 같은 세 표를 낸다(같은 계획 키).
dashboard_baseline, dashboard_equipment, dashboard_downtime = shortening_frames(
    (baseline, equipment, downtime),
    sample=using_dashboard_sample,
    show_sample=show_sample_fleet,
    has_snapshot=latest_snapshot is not None,
    today=today,
)

# 진척 비교와 거르는 조건(기간·공정)은 사이드바 조건 카드다(목표 확보율은 위의 조회 조건 패널 줄).
# 맨 위 진척 비교가 본문 머리 줄에서 옮겨 온 자주 쓰는 칸이라 카드는 처음 펼친 채 선다(설계 규칙
# UI-LAY-06 — HOME 「LOB 표시 조건」 과 같은 까닭, 한 번 접으면 기억 칸을 따른다).
conditions_card = condition_card("필요 단축 일정 조건", name="shortening", default=True)
if using_dashboard_sample and not show_sample_fleet:
    # 카드에는 값 한 마디와 풍선(하는 법), 본문에는 빈 결과 한 줄만 둔다 — 같은 말을 두 번 그리지
    # 않는다(설계 규칙 UI-TXT-04 · UI-TXT-07).
    with conditions_card:
        st.caption(NO_UNITS_MARK, help=NO_UNITS_HELP)
    st.caption("등록된 호기가 없습니다.")
    rerun_if_head_stale()
    st.stop()

# 소요대수는 활성 시나리오에 있다. 여기서는 계산이 서는지만 본다(적중이면 프레임을 풀지 않는다 —
# `shortening_source.load_shortening_demand`, Space 「필요 단축」 보기와 같은 길). 패널은 같은
# 시나리오 키와 로더로 달 범위·계획을 꺼낸다 — 소요대수는 그 캐시가 빗나갈 때만, 한 회차에 한 번만
# 푼다. 못 읽었거나 계산이 멈췄으면 패널이 본문에 까닭을 알린다.
shortening_context: PageContext | None = None
shortening_key: ScenarioCacheKey | None = None
shortening_demand: Callable[[], pd.DataFrame] | None = None
shortening_error: str | None = None
try:
    demand = load_shortening_demand()
    shortening_context, shortening_key, shortening_demand = (
        demand.context,
        demand.key,
        demand.loader,
    )
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
    inactive_floors=inactive_floors,
)
# 남의 저장으로 앱 머리(변경 칩 · 화면 탭 점)가 센 편집을 버린 회차 — 모든 위젯을 그린 뒤 한 번 다시
# 돈다(`ensure_equipment_drafts` 가 표지를 단다).
rerun_if_head_stale()
