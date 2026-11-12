# Purpose: 소요대수와 설비 일정 기준 가용으로 공정 하나의 미래 제약 영향과 개조 일정을 보는 화면을
# 그린다.

"""제약 시뮬레이션 — 실행 관리 셋째 화면(필요 단축 일정 다음, 2026-10-24 사용자 결정).

정체성: 「한 공정에 미래 구간 제약(특정 제품만 쓸 수 있게 개조·전용해야 하는 설비)이 생기면, 제약
제품에 먼저 떼어 준 뒤 기존 제품의 확보율이 언제부터 얼마나 떨어지는가」 를 그때그때 본다.
**저장하지 않는다** — 조건은 이 세션에만 있고 시뮬레이션·설비 DB 어디에도 쓰지 않는다.

모드는 둘이다 — 사이드바 조건 카드 맨 위 「제약 영향 | 개조 일정」(2026-10-26 결정 3, 자리는
2026-11-08 사용자 그림 메모 g12 — 모드 전환이 그 안이라 카드는 처음 펼친 채 선다). 「개조 일정」 은
「제약 없이 N대 × D일 개조를 모든 달 기준 확보율을 지키며 언제 할까」 를 찾는 역방향 계산이고, 공통
진입·설비 세션 뒤에 `components/modification_schedule_view.render_schedule_mode` 하나가 카드의
나머지·계획·계산·본문을 그린 뒤 이 화면이 멈춘다(제약 영향 모드의 카드·본문은 서지 않는다). 두
모드는 공정 칸(조회 조건 패널의 공용 공정 칸 — 하나 고름)·기준 확보율 정본을 나눈다.

입력(새 무거운 계산이 없다 — 공정 Capa 상세가 쓰는 캐시 래퍼를 **같은 키로** 다시 받는다):

- **공통 진입** — `page_bootstrap.process_page_inputs`(공정 Capa 상세와 같은 함수 — 판정 기준·유효
  기간 `RQ_REQB`·시나리오 키·확보율·달·공정 선택지). 확보율 프레임은 선택지·달에만 쓴다.
- **소요대수** — 공정 합은 계획의 `소요대수`, 제품별은 `get_process_product_demand(split="제품정보",
  limit=CONSTRAINT_PRODUCT_LIMIT)`(행을 다 더하면 그 공정 소요). 한 제품정보의 모든 양산구분이
  든다(D4).
- **설비 일정 기준 가용(단축 전)** — 사이드바 세션 설비 시나리오(D6)의 계산 세 표·Cut-off 로 공정
  Capa 상세 ②와 같은 계획 칸(`load_required_shortening_for_target` — 공식 칸, 목표는 키 맞춤용 HOME
  확보 기준)을 받아 `가용대수` 열만 읽는다(D3). 필요 단축 일정의 공용 조회
  조건(`0019`)·기준선(`0021`)·세션 칸은 읽지도 쓰지도 않는다. UPEH 가정·HOME 얹기는 걸지 않는다(D5).

계산은 순수 서비스(`services/constraint_simulation.py`)다. 오류 갈래는 넷으로 가른다 — 공통
진입(카드 표지 `NO_PROCESS_MARK` · 패널 공정 줄은 잠긴 「계산 멈춤」 — 2차 보드 Q2-28, 그 앞 설비
시나리오 줄은 잠그지 않고 선다 — 2026-11-11 보드 C1), 제품별
소요 받기(카드 표지 `NO_PRODUCT_MARK` + 본문 마크 · 알림 「제품별 소요를 읽지 못했습니다 — {글}」 —
「소요가 있는 제품이 없다」 안내와 가른다), 계획
받기(「설비 일정을 계산하지 못했습니다 — …」, 두 DB 경로), 어댑터·서비스의
`ValueError`·`KeyError`(「제약 시뮬레이션을 계산하지 못했습니다 — {글}」, DB 경로 없음).
`BOOTSTRAP_ERRORS` 에 `KeyError`·`ValueError` 가 들어 있어 한 `try` 로 묶으면 뒤의 글이 앞의 글로
둔갑한다. 설비 일정 확인(판정 · 멈춘 자리)과 계획 받기는 「개조 일정」 모드와 같은 함수
(`components/constraint_equipment_plan.render_equipment_plan`)이고, 제품 갈래는 그 사이
(`before_plan`)에 선다.

본문은 머리 줄 → 요약 넷(프래그먼트 밖) → 본문 프래그먼트(`components/constraint_simulation_view` —
달 누름만 그 안에서 돈다, 「비중 배분 비교」 는 카드 토글이라 앱 전체 회차). 머리 줄은 멈춘 갈래의
공정 · 배지뿐이고 계산이 선 회차에는 서지 않는다 — 맨 위 「← 공정 Capa 상세」 되돌아가기 링크는 두지
않는다(화면 탭 줄 · 사이드바가 같은 길, 2026-11-09 보드 T4). 조건은 사이드바 칸이 보이고 소요 ·
가용의 출처와 읽는 법은 Guide 다 — 머리 줄은 조건을 되읊지 않는다(2026-11-08 사용자 그림 메모
g12). 계획이 건 입력 비가동은 상태 알림 `CS-05` 다
(`constraint_equipment_plan.report_manual_downtime` — 2026-11-10 보드 Q-4, 자리에는 그리지 않는다).
개조 · 신규 대기 첫날이 오늘보다 앞이면(그래프 · 계산표가 「제때 시작했다면」 의 값) 상태 알림
`CS-04` 다(`report_late_starts` — 자리에는 그리지 않는다). UPEH 가정을 켠 세션이면(두 모드 모두
공식 소요로 센다) 상태 알림 `CS-06` 이다(`constraint_equipment_plan.report_upeh_not_applied` — 모드
분기 앞 한 자리, 2차 보드 Q2-13).

개조 묶음의 2판 옵션(2026-10-26 사용자 결정, 개조 끔이면 잠긴다) — 「보유 제약 호기」 고르기
(그 공정 세션 설비 시나리오의 호기 — 2026-11-01 결정 B3)와 「목록에 없는 보유 제약 설비」 숫자
칸(환산 대수, 기본 0 — B3-3), 「신규 설비는 개조 없이」 토글 + 기준일(기본 오늘). 호기 고르기
선택지는 같은 마스터 지문의 가벼운 캐시(`get_process_held_units`)로 받고, 계획을 받은 뒤 카드 안
자리(`held_slot`)에 그린다 — 계획 앞에서 멈추는 갈래는 잠긴 빈 칸을 그린다(카드 모양이 같게).
신규 호기(기여 시작 · 환산 대수 · 반출 — 묶음은 첫 모듈 기준)는 새 캐시 없이 공정 Capa 상세
③·④ 와 같은 설비 일정 칸(`get_process_equipment_timeline` — 같은 키)을 기준일로 거르고 고른
호기를 뺀 값이고(`new_unit_availability`), 옵션을 켠 회차에만 받는다. 어느 증가에 붙일지(개조
일수 안 — 그 사이 신규 대기)와 남은 보유가 남은 증가를 다 덮으면 그 증가부터 신규를 붙이지 않는
것(B1 — 증가마다)은 서비스가 정한다. 기준일·고른 호기는 어떤 캐시 키에도 들지 않는다.
"""

from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation import alerts, shared_process
from capa_simulation.components.constraint_equipment_plan import (
    CUTOFF_SOURCE_HELP,
    SESSION_ONLY_CAPTION,
    SESSION_ONLY_HELP,
    EquipmentPlanSource,
    equipment_readiness,
    first_ready_process,
    render_equipment_plan,
    report_manual_downtime,
    report_upeh_not_applied,
)
from capa_simulation.components.constraint_simulation_figures import (
    WAIT_LATE_TEXT,
    WINDOW_LATE_TEXT,
    ConstraintLabels,
    late_waits,
    late_windows,
    units_text,
    waiting_line,
    window_line,
)
from capa_simulation.components.constraint_simulation_view import (
    ConstraintView,
    render_constraint_kpis,
    render_constraint_view,
    settle_selected_month,
)
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.date_panel import date_field
from capa_simulation.components.equipment_scenario_status import (
    equipment_basis_label,
    render_equipment_scenario_row,
    render_legacy_trace_warning,
    render_stopped_equipment_scenario_row,
)
from capa_simulation.components.literal_markdown import (
    literal_markdown,
    markdown_safe_tildes,
)
from capa_simulation.components.modification_schedule_view import (
    ScheduleModeContext,
    render_mode_switch,
    render_schedule_mode,
)
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.preset_number_field import render_preset_number_field
from capa_simulation.components.process_field import (
    render_process_choice,
    render_stopped_process_field,
)
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.state_alerts import (
    equipment_scope,
    missing_handover_text,
)
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_GENERAL_INPUT_KEY,
    CONSTRAINT_GENERAL_KEY,
    CONSTRAINT_GENERAL_PILLS_KEY,
    CONSTRAINT_HELD_IDLE_KEY,
    CONSTRAINT_HELD_INPUT_KEY,
    CONSTRAINT_LOCKED_ARRIVAL_KEY,
    CONSTRAINT_MOD_DAYS_INPUT_KEY,
    CONSTRAINT_MOD_DAYS_KEY,
    CONSTRAINT_MOD_DAYS_PILLS_KEY,
    CONSTRAINT_MODIFY_KEY,
    CONSTRAINT_NEW_SINCE_KEY,
    CONSTRAINT_NEW_UNITS_KEY,
    CONSTRAINT_OWNED_KEY,
    CONSTRAINT_PERIOD_END_KEY,
    CONSTRAINT_PERIOD_START_KEY,
    CONSTRAINT_PROCESS_KEY,
    CONSTRAINT_PRODUCT_KEY,
    CONSTRAINT_PRODUCT_LIMIT,
    CONSTRAINT_PROPORTIONAL_KEY,
    CONSTRAINT_TARGET_INPUT_KEY,
    CONSTRAINT_TARGET_KEY,
    CONSTRAINT_TARGET_PILLS_KEY,
    DEFAULT_MOD_DAYS,
    DEFAULT_MODIFY,
    DEFAULT_NEW_UNITS,
    DEFAULT_PROPORTIONAL,
    DEFAULT_TARGET_PERCENT,
    GENERAL_PRESETS,
    MOD_DAY_PRESETS,
    TARGET_PRESETS,
    follow_held_units,
    follow_period_end,
    follow_period_start,
    seed_new_since,
    seed_owned_units,
    seed_toggle,
    settle_held_units,
    settle_period,
    take_constraint_process_request,
)
from capa_simulation.equipment_scenario_activation import (
    EquipmentSession,
    resolve_equipment_session,
)
from capa_simulation.modification_schedule_state import SCHEDULE_MODE
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    page_visit,
    process_page_inputs,
    prune_choice,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_manual_downtime,
    load_process_cutoff,
)
from capa_simulation.persistence.equipment_repository import EquipmentSnapshot
from capa_simulation.process_detail_state import (
    EQUIPMENT_BASIS_OFFICIAL as DETAIL_EQUIPMENT_BASIS_OFFICIAL,
)
from capa_simulation.process_detail_state import (
    PROCESS_DETAIL_EQUIPMENT_BASIS_KEY,
)
from capa_simulation.services.constraint_simulation import (
    GENERAL_INPUT_RANGE,
    MODIFICATION_DAYS_RANGE,
    OWNED_UNITS_RANGE,
    TARGET_RANGE,
    ConstraintConditions,
    ConstraintResult,
    HeldUnit,
    NewUnit,
    UnitModule,
    constraint_month_inputs,
    simulate_constraint,
)
from capa_simulation.services.manual_downtime import ManualDowntime
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_capa_detail import OTHER_ROW_COLUMN, month_column
from capa_simulation.services.process_cutoff import cutoff_days_words, cutoff_setting
from capa_simulation.services.process_equipment_timeline import (
    HeldUnitChoice,
    ModuleStart,
    NewUnitAvailability,
    new_unit_availability,
)
from capa_simulation.services.securement_threshold import (
    judgment_boundary,
    securement_threshold_caption,
)
from capa_simulation.services.simulation_cache import get_process_product_demand
from capa_simulation.services.threshold_label import threshold_percent
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import NO_PROCESS_MARK, condition_card

CARD_LABEL = "제약 시뮬레이션 조건"
# 공용 공정 칸의 출처 이름. 이 화면은 공용 값을 받고, 사이드바 공정 칸에서 직접 고른 공정만 보낸다
# (2026-11-08 사용자 답 P2-2 · 2026-11-09 보드 C2 (가)).
SCREEN = "제약 시뮬레이션"
CARD_NAME = "constraint_simulation"
CARD_ICON = ":material/call_split:"
# 제품별 소요를 읽지 못한 회차의 카드 표지 — 까닭은 본문 마크의 알림이다(설계 규칙 UI-NTF-08).
NO_PRODUCT_MARK = "제품 · 읽지 못함"
PAGE_TITLE = "제약 시뮬레이션"
HELD_LABEL = "보유 제약 호기"
HELD_HELP = (
    "이미 제약 제품을 돌릴 수 있게 개조·Qual 된 호기를 이 공정의 세션 설비 시나리오 호기에서 "
    "고릅니다(찾기 됨 — 세션에만 두고 저장하지 않습니다). 보유 = 그 달 W/D 첫날에 있는 "
    "고른 호기의 환산 합 — 기여 시작 전 호기는 아직 없고, 정지·반출/이설되는 날부터 뺍니다"
    "(이미 쓴 몫은 풀지 않습니다). 제약 몫이 늘 때 그날 붙일 수 있는 신규 설비 다음으로 써 "
    "그만큼 개조하지 않고, 남은 보유만으로 제약 기간 끝까지 남은 증가가 덮이면 그 증가부터 "
    "신규를 붙이지 않습니다. 쓰지 "
    "않는 동안과 기간 밖에는 기존 제품에 씁니다. 고른 호기는 신규 후보에서 빠집니다(두 번 "
    "세지 않습니다). 설비 시나리오나 조회기간을 바꿔 목록에서 사라진 호기는 빼고 알립니다."
)
# 계획 앞에서 멈춘 회차의 잠긴 칸 — 칸에는 표지, 까닭은 칸 풍선이다(설계 규칙 UI-ACC-02).
HELD_IDLE_PLACEHOLDER = "고를 호기 없음"
HELD_IDLE_HELP = "설비 일정이 서는 공정에서 고릅니다."
OWNED_LABEL = "목록에 없는 보유 제약 설비 (환산 대수)"
OWNED_HELP = (
    "위 「보유 제약 호기」 목록에 없는 보유(기존보유처럼 설비 마스터 호기가 아닌 대수)를 "
    "적습니다 — 환산 대수, 기간 내내 같습니다. 고른 호기에 더해 보유로 셉니다. 목록에 있는 "
    "호기는 여기 적지 말고 위에서 고르세요(신규 후보와 두 번 셉니다)."
)
NEW_UNITS_HELP = (
    "기여 시작(Qual 다음 날)이 기준일 이후인 신규 호기(공정 Capa 상세 ④ 와 같은 날짜)는 셋업 때 "
    "제약 제품으로 Qual 할 수 있다고 봅니다. 기여 시작에서 개조 기간 안에 제약 몫이 늘어나는 달"
    "(그 달 W/D 첫날)이 있으면 개조 없이 그 몫에 붙이고, 그 달까지는 기존 제품이 못 쓰는 "
    "「신규 대기」 로 뺍니다(개조보다 짧습니다). 개조 기간 안에 늘어날 몫이 없으면 기존 제품에 "
    "쓰여 그 뒤로는 일반 설비와 같습니다(제약에 쓰려면 개조). 제약 기간 전에 들어온 신규도 "
    "같습니다. 묶음(모듈) 설비는 첫 모듈 날짜로 보고 모듈마다 제 날짜부터 붙입니다 — 증가 날까지 "
    "오지 않은 모듈은 그 증가에 붙지 않습니다. 남은 보유 제약 설비만으로 제약 기간 끝까지 남은 "
    "증가가 덮이면 그 증가부터 신규는 붙이지 않습니다(기존 제품 몫)."
)
NEW_SINCE_HELP = "기여 시작이 이날 이후(그날 포함)인 호기를 신규로 봅니다. 처음 값은 오늘입니다."
# 「비중 배분 비교」 토글(카드 끝 「견주기」 — 2026-11-09 보드 C3). 풍선은 짧게 두고 뜻 · 식은
# Guide 다.
PROPORTIONAL_LABEL = "비중 배분 비교"
PROPORTIONAL_HELP = "개조 없이 가용을 소요 비중대로 나눴을 때의 기존 제품 확보율을 함께 둡니다."


def new_since_help(*, modify: bool, new_units_on: bool) -> str:
    """「신규 기준일」 풍선 — 잠긴 동안은 왜 잠겼는지를 먼저 말한다(설계 규칙 UI-INP-07)."""
    if not modify:
        return f"「개조 필요」 를 켜면 씁니다. {NEW_SINCE_HELP}"
    if not new_units_on:
        return f"「신규 설비는 개조 없이」 를 켜면 씁니다. {NEW_SINCE_HELP}"
    return NEW_SINCE_HELP


# 주소 `?process=` 는 **무엇보다 먼저** 꺼내고 그 키 하나만 지운다 — 부트스트랩이 멈춘 회차에도
# 주소에 남지 않게(공정 Capa 상세 머리 「이 공정 제약 시뮬레이션」 이 싣는다). 같은 값은 같은 방문
# 안에서만 한 번 적용하고, 다른 화면에서 다시 들어온 방문은 다시 적용한다.
requested_process = take_constraint_process_request(page_visit())

render_page_header("제약 시뮬레이션")
# 머리 줄(멈춘 갈래의 공정 · 배지) 자리. 공정과 계산이 정해진 뒤 채운다 —
# 블록이라 계산 동안 앞 회차 줄이 남는다(빈 블록은 그려지지 않으므로 border·height 를 주지
# 않는다).
header_marks = st.container()
render_page_guide("constraint_simulation", title=PAGE_TITLE)
# 설비 DB 경고(이 코드보다 새 스키마·옛 배포 흔적)와 알림 표지 자리 — 맨 위에 선다.
notices = st.container()
process_labels = get_process_labels()
today = date.today()

try:
    page_inputs = process_page_inputs(str(DUCKDB_PATH.resolve()))
except BOOTSTRAP_ERRORS as exc:
    # 설비 시나리오 줄은 공정 Capa 상세처럼 잠그지 않고 서고(2026-11-11 보드 C1), 패널의 공정 줄은
    # 잠긴 채 자리를 지킨다(산출 결과 · 공정 Capa 상세와 같은 꼴 — 2차 보드 Q2-28) — 정상 회차와
    # 같은 높이다.
    render_stopped_equipment_scenario_row()
    render_stopped_process_field()
    # 카드는 멈춘 회차에도 선다 — 「조회 조건」 제목만 남은 빈 구역을 만들지 않는다.
    with condition_card(CARD_LABEL, name=CARD_NAME, icon=CARD_ICON, default=True):
        st.caption(NO_PROCESS_MARK)
    message = bootstrap_error_message(exc, labels=process_labels)
    render_data_error(message, code="CS-01", text="제약 시뮬레이션을 준비하지 못했습니다")
    st.stop()

thresholds = page_inputs.thresholds
context = page_inputs.context
active_scenario = context.active_scenario
months = list(page_inputs.months)
process_options = page_inputs.process_options
# 사이드바 조건 카드 하나를 세워 두 모드가 차례로 채운다. 맨 위는 모드 전환 「제약 영향 | 개조
# 일정」 — 카드에 무엇이 설지 정하므로 앱 전체 회차로 돈다. 그 전환이 카드 안이라 카드는 처음 펼친
# 채 선다(한 번 접으면 기억 칸을 따른다 — 2026-11-08 사용자 그림 메모 g12).
card = condition_card(CARD_LABEL, name=CARD_NAME, icon=CARD_ICON, default=True)
with card:
    schedule_mode = render_mode_switch() == SCHEDULE_MODE

# 설비 — 세션 설비 시나리오(새 세션은 공식). 못 읽으면 까닭을 들고 카드는 그대로 세운다.
equipment_session: EquipmentSession | None = None
snapshot: EquipmentSnapshot | None = None
cutoff = pd.DataFrame()
# 입력 비가동 대수(가용설비 현황 › Preference — 공용, 설비 0032). 계획 키에 실린다(공정 Capa 상세와
# 같은 가용).
manual_downtime = ManualDowntime()
equipment_error = ""
try:
    equipment_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    equipment_session = resolve_equipment_session(equipment_path)
    snapshot = equipment_session.snapshot
    cutoff = load_process_cutoff(equipment_path)
    manual_downtime = load_manual_downtime(equipment_path)
    with notices:
        render_schema_ahead_warning(get_equipment_repository(equipment_path).schema_ahead)
        render_legacy_trace_warning(equipment_session)
except BOOTSTRAP_ERRORS as exc:
    snapshot = None
    cutoff = pd.DataFrame()
    manual_downtime = ManualDowntime()
    equipment_error = bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
else:
    render_equipment_scenario_row(equipment_session)
# 설비 일정 확인 · 계획 입력 — 두 모드가 같은 묶음을 같은 함수(`render_equipment_plan`)에 넘긴다.
plan_source = EquipmentPlanSource(
    page_inputs=page_inputs,
    snapshot=snapshot,
    cutoff=cutoff,
    equipment_error=equipment_error,
    today=today,
    manual_downtime=manual_downtime,
)

# 공정 — 공정 값 칸보다 먼저 정해 세션 칸에 적는다. 공용 공정(다른 화면에서 고른 공정)은 값이 바뀐
# 뒤 처음 그리는 회차에 하나이고 이 목록에 있을 때만 연다 — 넘겨받은 공정(주소 `process` — 공정 Capa
# 상세 머리 링크)이 이긴다(2026-11-08 사용자 답 P2-2). 따라 연 공정은 설비 일정이 서지 않아도 그대로
# 연다 — 고른 것과 같은 멈춘 자리다. 처음 연 화면의 기본(`first_ready_process`)은 세션 칸이 빈
# 회차에만 쓴다.
followed_process = shared_process.follow_single(
    SCREEN, process_options, entered=requested_process is not None
)
if followed_process is not None:
    st.session_state[CONSTRAINT_PROCESS_KEY] = followed_process
# 넘겨받은 공정이 선택지에 있으면 세션 칸에 적는다. HOME 칸으로 연 공정 Capa 상세(설비 공식
# 고정)에서 넘어왔으면 그 방문을 적어 둔다 — 설비 기준이 바뀐 것을 알린다.
missing_label: str | None = None
if requested_process is not None:
    if requested_process in process_options:
        st.session_state[CONSTRAINT_PROCESS_KEY] = requested_process
        if (
            st.session_state.get(PROCESS_DETAIL_EQUIPMENT_BASIS_KEY)
            == DETAIL_EQUIPMENT_BASIS_OFFICIAL
        ):
            st.session_state[CONSTRAINT_LOCKED_ARRIVAL_KEY] = (requested_process, page_visit())
        else:
            st.session_state.pop(CONSTRAINT_LOCKED_ARRIVAL_KEY, None)
    else:
        missing_label = process_labels.label(requested_process)
saved_process = st.session_state.get(CONSTRAINT_PROCESS_KEY)
opened_process = prune_choice(
    CONSTRAINT_PROCESS_KEY,
    process_options,
    default=(
        str(saved_process)
        if saved_process is not None and str(saved_process) in process_options
        else first_ready_process(plan_source, process_options)
    ),
)
# 넘겨받은 공정을 열지 못한 것은 이 방문 한 번의 사건 알림이다(`CS-02` — 알림창 · Alarm, 자리에
# 그리지 않는다). 알림창 · 패널은 평문이라 이름을 막지 않는다. 표지는 바로 아래 한 자리(`flush` —
# 늘 부른다)가 보낸다.
if missing_label is not None:
    alerts.event(
        "CS-02",
        text=missing_handover_text(
            missing_label,
            None if opened_process is None else process_labels.label(opened_process),
            fallback="공정 없이",
        ),
    )
with notices:
    alerts.flush()
# 조회 조건 패널의 공정 값 칸(하나 고름 — 두 모드가 나눈다). 값은 원본이고 글자만 표시명이다.
# 그 팝업에서 직접 고른 공정만 공용 값으로 보낸다(C2 (가)) — 주소로 넘겨받은 공정 · 기본 공정은
# 보내지 않는다.
selected_process = render_process_choice(
    process_options, screen=SCREEN, key=CONSTRAINT_PROCESS_KEY, labels=process_labels
)


def locked_arrival_label(process: str | None) -> str | None:
    """HOME 칸으로 연 공정 Capa 상세(설비 공식 고정)에서 넘어온 그 공정·그 방문이고 세션이 공식 발행
    쌍이 아니면 세션 설비 시나리오 이름표 — 이 화면의 설비는 두 모드 모두 세션 설비 시나리오다(D6).
    다른 공정·다른 방문이면 그 칸을 걷고 None 이다."""
    arrival = st.session_state.get(CONSTRAINT_LOCKED_ARRIVAL_KEY)
    if arrival is None:
        return None
    if process is None or arrival != (process, page_visit()):
        st.session_state.pop(CONSTRAINT_LOCKED_ARRIVAL_KEY, None)
        return None
    if equipment_session is None or equipment_session.is_official_pair:
        return None
    return equipment_basis_label(equipment_session)


def report_locked_arrival(process: str | None) -> None:
    """설비 기준이 바뀐 도착은 상태 알림(`CS-03`)이다 — 그 공정 · 그 방문인 동안 참이고, 자리에는
    그리지 않는다(설계 규칙 UI-NTF-02). 지문이 바뀔 때만 알림창에 뜨고 다른 공정 · 다른 방문이면
    「해소」 로 닫힌다. 알림창 · 패널은 평문이라 이름을 막지 않는다. 늘 부른다(이벤트 칸 한
    자리)."""
    label = locked_arrival_label(process)
    scope = equipment_scope(equipment_session) if equipment_session is not None else None
    alerts.state(
        "CS-03",
        scope=None if scope is None else {**scope.scope, "process": process},
        scope_label="" if scope is None else scope.label,
        content=None if label is None else [process, page_visit()],
        active=label is not None,
        text=None
        if label is None
        else f"설비는 세션의 「{label}」 기준 — 공정 Capa 상세는 공식 고정",
        full=(
            None
            if label is None
            else f"설비는 세션의 「{label}」 기준입니다 — 공정 Capa 상세는 HOME 칸에서 열어 설비가 "
            "공식 고정이었습니다. 이 화면은 늘 사이드바 설비 시나리오로 계산합니다."
        ),
    )


# 모드 분기 앞 — 「개조 일정」 모드도 같은 세션 설비로 계산하고, 두 모드 모두 UPEH 가정을 걸지
# 않는다(상태 알림 `CS-06` — 늘 부른다).
with notices:
    report_locked_arrival(opened_process)
    report_upeh_not_applied(page_inputs)


def render_header(process: str, line: str = "") -> None:
    """머리 줄 — 멈춘 갈래의 공정 · 배지(`line`). 빈 글이면 줄이 서지 않는다 — 맨 위 되돌아가기
    링크는 두지 않는다(화면 탭 줄 · 사이드바가 같은 길, 2026-11-09 보드 T4). `process` 는 두 모드 ·
    설비 일정 확인이 함께 쓰는 머리 그리기 꼴(`HeaderRenderer`)이라 받는다."""
    del process
    if not line:
        return
    with header_marks.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(line, width="content")


# 「개조 일정」 모드는 카드·계획·계산·본문을 컴포넌트 하나가 그리고 여기서 멈춘다 — 아래 제약 영향
# 모드의 카드·본문은 서지 않는다(1판은 두 모드를 함께 쓰지 않는다, 2026-10-26 결정 3).
if schedule_mode:
    render_schedule_mode(
        ScheduleModeContext(
            source=plan_source,
            process_labels=process_labels,
            equipment_session=equipment_session,
            card=card,
            render_header=render_header,
            process=selected_process,
        )
    )
    st.stop()


def product_choices(table: pd.DataFrame) -> list[str]:
    """제약 제품 선택지 — 제품별 소요 표(산출 결과 · 소요대수 표시순서)의 제품정보. 빈 이름·「그
    밖」 은 뺀다."""
    if table.empty or "제품정보" not in table.columns:
        return []
    names = table["제품정보"].astype("string").str.strip()
    others = (
        table[OTHER_ROW_COLUMN].astype("boolean").fillna(False).astype("bool")
        if OTHER_ROW_COLUMN in table.columns
        else pd.Series(False, index=table.index)
    )
    chosen: list[str] = []
    for name, other in zip(names.tolist(), others.tolist(), strict=True):
        text = "" if name is None or pd.isna(name) else str(name)
        if text and not other and text not in chosen:
            chosen.append(text)
    return chosen


def first_demand_month(table: pd.DataFrame, product: str | None) -> int:
    """그 제품의 첫 소요 달(보이는 달). 없으면 첫 달 — 제약 시작의 기본값(D8)."""
    if product is None or table.empty or "제품정보" not in table.columns:
        return months[0]
    rows = table.loc[table["제품정보"].astype("string").str.strip().eq(product).fillna(False)]
    for month in months:
        column = month_column(month)
        if column in rows.columns and float(pd.to_numeric(rows[column], errors="coerce").sum()) > 0:
            return month
    return months[0]


product_table = pd.DataFrame()
product_options: list[str] = []
# 제품별 소요를 읽지 못한 까닭(빈 글자 = 읽음). 카드에는 짧은 캡션, 본문에는 이 글을 싣는다 —
# 「소요가 있는 제품이 없다」 와 가른다.
product_error = ""
cutoff_line = "Cut-off 미기재"
with card:
    st.caption("**대상**")
    if selected_process is not None and months:
        try:
            product_table = get_process_product_demand(
                page_inputs.capacity_cache_key,
                page_inputs.order_key,
                str(selected_process),
                "제품정보",
                tuple(months),
                _scenario_tables=active_scenario["tables"],
                _reference_tables=context.reference_tables,
                _display_order=context.display_order,
                limit=CONSTRAINT_PRODUCT_LIMIT,
            )
        except BOOTSTRAP_ERRORS as exc:
            product_table, product_error = pd.DataFrame(), bootstrap_error_message(exc)
        product_options = product_choices(product_table)
    prune_choice(
        CONSTRAINT_PRODUCT_KEY,
        product_options,
        default=product_options[0] if product_options else None,
    )
    selected_product = st.selectbox(
        "제약 제품",
        product_options,
        key=CONSTRAINT_PRODUCT_KEY,
        persist_state="session",
        disabled=not product_options,
        help="제품정보 — 그 제품정보의 모든 양산구분(양산·ER) 소요가 듭니다.",
    )
    if product_error:
        st.caption(NO_PRODUCT_MARK)
    period = (
        settle_period(
            months,
            default_start=first_demand_month(
                product_table, str(selected_product) if selected_product is not None else None
            ),
        )
        if months
        else None
    )
    start_column, end_column = st.columns(2)
    with start_column:
        st.selectbox(
            "제약 시작",
            months,
            key=CONSTRAINT_PERIOD_START_KEY,
            persist_state="session",
            format_func=month_label,
            on_change=follow_period_start,
            disabled=not months,
        )
    with end_column:
        st.selectbox(
            "제약 끝",
            months,
            key=CONSTRAINT_PERIOD_END_KEY,
            persist_state="session",
            format_func=month_label,
            on_change=follow_period_end,
            disabled=not months,
        )
    if period is not None and period.moved:
        # 고쳐 읽은 입력 곁 한 줄(설계 규칙 UI-NTF-03 — 그 자리 입력과 짝인 고쳐 읽음).
        st.caption("조회기간이 바뀌어 제약 기간을 보이는 달로 옮겼습니다.")

    st.caption(SESSION_ONLY_CAPTION, help=SESSION_ONLY_HELP)
    st.caption("**확보율**")
    target_value = render_preset_number_field(
        "제약 확보율",
        value_key=CONSTRAINT_TARGET_KEY,
        pills_key=CONSTRAINT_TARGET_PILLS_KEY,
        input_key=CONSTRAINT_TARGET_INPUT_KEY,
        presets=TARGET_PRESETS,
        default=DEFAULT_TARGET_PERCENT,
        minimum=TARGET_RANGE[0] * 100,
        maximum=TARGET_RANGE[1] * 100,
        step=1,
        unit="%",
        # 정수 % 칸이 소수를 받아 반 올림한다(109.5 → 110 — 판정 기준 칸과 한 규칙, 2026-11-01).
        number_format="%.0f",
        decimal_entry=True,
        fallback=DEFAULT_TARGET_PERCENT,
        preset_label=lambda value: f"{value:g}%" if value is not None else "",
        help=(
            "제약 제품에 먼저 떼어 줄 몫 — 필요 대수 = 올림(제약 제품 소요 × 이 값). 정수 % 이고 "
            "소수를 치면 사사오입합니다(109.5 → 110)."
        ),
        tone="warning",
    )
    # 판정 기준은 정수 % 다(2026-11-01 사용자 결정) — HOME 기본도 정수 T 로 보인다.
    home_percent = threshold_percent(thresholds.default_secure)
    general_value = render_preset_number_field(
        "기준 확보율",
        value_key=CONSTRAINT_GENERAL_KEY,
        pills_key=CONSTRAINT_GENERAL_PILLS_KEY,
        input_key=CONSTRAINT_GENERAL_INPUT_KEY,
        presets=GENERAL_PRESETS,
        default=None,
        minimum=round(GENERAL_INPUT_RANGE[0] * 100),
        maximum=round(GENERAL_INPUT_RANGE[1] * 100),
        step=1,
        unit="%",
        # 정수 % 칸이 소수를 받아 반 올림한다(109.5 → 110 — HOME 판정 기준 칸과 한 규칙,
        # 2026-11-01).
        number_format="%.0f",
        decimal_entry=True,
        fallback=home_percent,
        preset_label=lambda value: "HOME 기준" if value is None else f"{value:g}%",
        help=(
            "기존 제품 판정 기준(정수 % — 소수를 치면 사사오입합니다, 109.5 → 110). "
            "「HOME 기준」 은 HOME 설정 → 판정 기준 탭의 공용 판정 기준(기본 + 월별 예외)을 달마다 "
            "씁니다. 판정은 확보율을 사사오입한 정수 % 로 견줍니다 — 110% 면 109.5% 도 "
            "확보입니다."
        ),
    )
    st.caption(
        "HOME · "
        + securement_threshold_caption(
            thresholds, start_month=page_inputs.effective_start, end_month=page_inputs.effective_end
        )
    )
    st.caption("**개조**")
    seed_toggle(CONSTRAINT_MODIFY_KEY, DEFAULT_MODIFY)
    modify = st.toggle(
        "개조 필요",
        key=CONSTRAINT_MODIFY_KEY,
        persist_state="session",
        help=(
            "켜면 제약 제품에 떼어 줄 대수만큼 그 달 W/D 첫날 앞 개조 기간 동안 비가동이 잡힙니다."
        ),
    )
    modification_days = render_preset_number_field(
        "개조 기간",
        value_key=CONSTRAINT_MOD_DAYS_KEY,
        pills_key=CONSTRAINT_MOD_DAYS_PILLS_KEY,
        input_key=CONSTRAINT_MOD_DAYS_INPUT_KEY,
        presets=MOD_DAY_PRESETS,
        default=DEFAULT_MOD_DAYS,
        minimum=MODIFICATION_DAYS_RANGE[0],
        maximum=MODIFICATION_DAYS_RANGE[1],
        step=1,
        unit="일",
        number_format="%d",
        fallback=DEFAULT_MOD_DAYS,
        preset_label=lambda value: f"{value:g}일" if value is not None else "",
        disabled=not modify,
    )
    # 2판 옵션 — 늘 그리고 개조 끔이면 잠근다(갈래마다 카드 모양이 같다). 호기 고르기는 선택지가
    # 계획 뒤에 서므로 자리만 잡는다(`render_held_picker`). 목록에 없는 보유 대수는 사람마다 아는
    # 사실 값이라 D10 버튼을 두지 않는다.
    held_slot = st.container()
    seed_owned_units(OWNED_UNITS_RANGE[1])
    owned_units = st.number_input(
        OWNED_LABEL,
        min_value=OWNED_UNITS_RANGE[0],
        max_value=OWNED_UNITS_RANGE[1],
        step=1,
        key=CONSTRAINT_OWNED_KEY,
        persist_state="session",
        disabled=not modify,
        help=OWNED_HELP,
    )
    seed_toggle(CONSTRAINT_NEW_UNITS_KEY, DEFAULT_NEW_UNITS)
    new_units_on = st.toggle(
        "신규 설비는 개조 없이",
        key=CONSTRAINT_NEW_UNITS_KEY,
        persist_state="session",
        disabled=not modify,
        help=NEW_UNITS_HELP,
    )
    seed_new_since(today)
    new_since = date_field(
        "신규 기준일",
        key=CONSTRAINT_NEW_SINCE_KEY,
        default=today,
        disabled=not (modify and new_units_on),
        help=new_since_help(modify=modify, new_units_on=new_units_on),
    )
    # 개조 끔이면 두 옵션은 걸리지 않는다 — 결과·머리에 걸리지 않은 조건이 남지 않게 넘기지 않는다.
    owned_value = int(owned_units) if modify and isinstance(owned_units, int) else 0
    new_unit_since = new_since if modify and new_units_on and isinstance(new_since, date) else None
    new_units_slot = st.container()
    cutoff_slot = st.container()
    # 견주기 — 본문 위에 보기 줄을 두지 않는다(2026-11-09 보드 C3 — 페이지 상단 문구 최소화).
    # 그래프 · 계산표를 그리는 본문 프래그먼트는 세션 값을 읽는다. 카드 위젯이라 바꾸면 앱 전체
    # 회차다.
    st.caption("**견주기**")
    seed_toggle(CONSTRAINT_PROPORTIONAL_KEY, DEFAULT_PROPORTIONAL)
    st.toggle(
        PROPORTIONAL_LABEL,
        key=CONSTRAINT_PROPORTIONAL_KEY,
        persist_state="session",
        help=PROPORTIONAL_HELP,
    )


def render_idle_held_picker() -> None:
    """계획 앞에서 멈추는 갈래의 호기 고르기 자리 — 잠긴 빈 칸(카드 모양이 같게). 정본은 건드리지
    않는다(설비 일정이 다시 서면 그 공정의 고름이 돌아온다)."""
    with held_slot:
        st.multiselect(
            HELD_LABEL,
            [],
            key=CONSTRAINT_HELD_IDLE_KEY,
            disabled=True,
            placeholder=HELD_IDLE_PLACEHOLDER,
            help=f"{HELD_IDLE_HELP} {HELD_HELP}",
        )


def held_choice_label(choice: HeldUnitChoice) -> str:
    """선택지 글 — 「HB-07 · 환산 0.5 · 2027-03-01 반출/이설」(축 안에서 뜻 있는 날만)."""
    text = f"{choice.unit} · 환산 {units_text(choice.units)}"
    if choice.start is not None:
        text += f" · {choice.start.isoformat()} 기여 시작"
    if choice.until is not None:
        text += f" · {choice.until.isoformat()} {choice.until_kind or '반출'}"
    return text


def render_held_picker(
    process: str, choices: tuple[HeldUnitChoice, ...], *, disabled: bool
) -> list[str]:
    """보유 「호기 고르기」 — 위젯 앞에서 그 공정의 고름을 잡고(없는 호기는 빼고 그 칸 바로 밑 한 줄
    — 결정 B3-2) 카드 자리에 그린다. 고른 설비키(고른 차례)를 돌려준다."""
    settled = settle_held_units(process, [choice.unit for choice in choices])
    labels = {choice.unit: held_choice_label(choice) for choice in choices}
    with held_slot:
        # 초점 앞뒤로 키가 같다 — 사이드바 multiselect 공용 규칙(`sidebar_style`, AGENTS 9장).
        picked = st.multiselect(
            HELD_LABEL,
            list(labels),
            key=CONSTRAINT_HELD_INPUT_KEY,
            format_func=lambda name: labels.get(str(name), str(name)),
            on_change=follow_held_units,
            args=(process,),
            disabled=disabled,
            placeholder="호기 고르기" if choices else "이 공정에 고를 호기가 없습니다",
            help=HELD_HELP,
            # 보유 호기는 하나씩 짚는 칸이다 — 「전체 선택」 한 번에 전부 보유로 잡히면 안 된다.
            select_all=False,
        )
        if picked:
            weights = {choice.unit: choice.units for choice in choices}
            total = sum(weights.get(str(name), 0.0) for name in picked)
            st.caption(f"고른 호기 {len(picked)}대 · 환산 합 {units_text(total)}대")
        if settled.dropped:
            # 고쳐 읽은 고름 — 그 칸 바로 밑 한 줄(설계 규칙 UI-NTF-03 — 입력 곁 고쳐 읽음).
            names = ", ".join(literal_markdown(name) for name in settled.dropped[:4])
            more = f" 외 {len(settled.dropped) - 4}대" if len(settled.dropped) > 4 else ""
            st.caption(
                f":material/playlist_remove: 고른 보유 제약 호기 가운데 지금 설비 시나리오 · "
                f"조회기간의 이 공정 목록에 없는 {len(settled.dropped)}대({names}{more})를 "
                "뺐습니다."
            )
    return [str(name) for name in picked]


def held_unit(choice: HeldUnitChoice) -> HeldUnit:
    """고른 선택지 → 계산 서비스의 보유 호기."""
    return HeldUnit(
        name=choice.unit,
        units=choice.units,
        start=choice.start,
        until=choice.until,
        modules=_unit_modules(choice.modules),
    )


def _unit_modules(modules: tuple[ModuleStart, ...]) -> tuple[UnitModule, ...]:
    return tuple(UnitModule(module.name, module.start, module.units) for module in modules)


if selected_process is None or not months or period is None:
    render_idle_held_picker()
    st.caption("조회기간에 확보율을 낼 공정이 없습니다.")
    # 계획 앞에서 멈춘 회차도 입력 비가동 알림 `CS-05` 를 낸다(`active=False` — 앞 회차 줄이 남지
    # 않게, 필요 단축 일정 `RS-05` 의 멈춘 회차 꼴).
    with notices:
        report_manual_downtime(
            plan_source,
            None,
            process=None if selected_process is None else str(selected_process),
            process_label="",
            equipment_session=equipment_session,
        )
    st.stop()

process = str(selected_process)
process_label = process_labels.label(process)

readiness = equipment_readiness(plan_source, process)
if readiness is not None and readiness.cutoff_days is not None:
    # 팝업에는 적은 값(35.8)이 그대로 보이고 계산은 내림한 일수(35)를 쓴다 — 둘을 함께 적는다.
    setting = cutoff_setting(cutoff, process)
    cutoff_line = (
        f"Cut-off {cutoff_days_words(setting if setting is not None else readiness.cutoff_days)}"
    )
with cutoff_slot:
    # 값만 자리에 — 어디서 고치는지는 풍선(설계 규칙 UI-TXT-03).
    st.caption(cutoff_line, help=CUTOFF_SOURCE_HELP)


def product_ready() -> bool:
    """설비 일정 판정 뒤 · 계획 앞의 제품 갈래 — 제품별 소요를 못 읽었거나 소요가 있는 제품이 없으면
    머리 한 줄과 까닭을 그리고 거짓."""
    if product_error:
        render_header(process, f"**{literal_markdown(process_label)}**")
        render_data_error(
            f"제품별 소요를 읽지 못했습니다 — {product_error}",
            code="CS-01",
            text="제품별 소요를 읽지 못했습니다",
        )
        return False
    if selected_product is None:
        render_header(process, f"**{literal_markdown(process_label)}**")
        st.caption("이 공정은 조회기간에 소요가 있는 제품이 없어 제약 제품을 고를 수 없습니다.")
        return False
    return True


# 설비 일정 확인 → 제품 갈래 → 계획(공정 Capa 상세 ② ~ ④ 와 같은 칸·같은 키 — 목표는 키 맞춤용, 단축
# 열은 읽지 않는다) → 계획에 공정이 있는가. 개조 일정 모드와 같은 함수다. 신규를 켠 회차에는 공정
# Capa 상세 ③·④ 와 같은 설비 일정 칸(같은 키)을 기준일로 거른 신규 호기도 같은 갈래로 받는다.
equipment_plan = render_equipment_plan(
    plan_source,
    readiness,
    process=process,
    process_label=process_label,
    subject="제약 시뮬레이션",
    render_header=render_header,
    before_plan=product_ready,
    with_timeline=new_unit_since is not None,
    with_held_units=True,
)
# 계획이 건 입력 비가동 — 상태 알림 `CS-05`(개조 일정 모드와 같은 함수 · 같은 범위). 멈춘 갈래는
# 「해소」 다.
with notices:
    report_manual_downtime(
        plan_source,
        None if equipment_plan is None else equipment_plan.plan,
        process=process,
        process_label=process_label,
        equipment_session=equipment_session,
    )
if equipment_plan is None or selected_product is None:
    render_idle_held_picker()
    st.stop()
product = str(selected_product)
plan = equipment_plan.plan
target_level = equipment_plan.target_level
# 보유 「호기 고르기」(개조 끔이면 잠긴다 — 고름은 세션에 남고 계산에 걸리지 않는다). 고른 호기는
# 신규 후보에서 뺀다(결정 B3 — 두 번 세지 않게).
picked_held = render_held_picker(process, equipment_plan.held_choices, disabled=not modify)
picked_set = set(picked_held)
held_units = (
    tuple(held_unit(choice) for choice in equipment_plan.held_choices if choice.unit in picked_set)
    if modify
    else ()
)
new_shares = (
    new_unit_availability(
        equipment_plan.timeline,
        since=new_unit_since,
        excluded=[unit.name for unit in held_units],
    )
    if equipment_plan.timeline is not None and new_unit_since is not None
    else None
)


def new_units_caption(shares: NewUnitAvailability) -> str:
    """카드 개조 묶음의 신규 한 줄 — 기준일 이후 기여 시작 호기 수와 앞 몇 대의 이름. 어느 호기를
    붙였는지(전용 · 일반 설비)는 계산표 「들어오는 신규 설비」 칸 풍선이 말한다."""
    if not shares.units:
        return "기준일 이후 기여를 시작하는 신규 설비가 없습니다."
    names = ", ".join(literal_markdown(name) for name in shares.units[:4])
    more = f" 외 {len(shares.units) - 4}대" if len(shares.units) > 4 else ""
    return (
        f"기준일 이후 기여 시작 신규 설비 {len(shares.units)}대(조회기간에 가용 "
        f"{shares.in_axis}대) · {names}{more}"
    )


def general_target(month: int) -> float:
    """그 달 기준 확보율의 판정 경계(비율) — HOME 이면 공용 판정 기준의 그 달 값, 아니면 고른
    정수 %.

    기준은 사사오입 정수 % 로 판정하므로(2026-11-01 사용자 결정) 서비스에는 그 판정 경계(110% 면
    1.095)를 넘긴다 — 판정·그래프 기준선 자리가 그 선이고 글자는 정수 「110%」 로 되읽는다.
    """
    if general_value is None:
        return thresholds.boundary_for(month)[0]
    return judgment_boundary(float(general_value) / 100)


target_percent = int(round(target_value if target_value is not None else DEFAULT_TARGET_PERCENT))
conditions = ConstraintConditions(
    period_start=period.start,
    period_end=period.end,
    constraint_target=target_percent / 100,
    modification_days=(
        int(round(modification_days if modification_days is not None else DEFAULT_MOD_DAYS))
        if modify
        else None
    ),
    cutoff_days=equipment_plan.cutoff_days,
    owned_units=owned_value,
    held_units=held_units,
    new_unit_since=new_unit_since,
)
with new_units_slot:
    if new_shares is not None:
        st.caption(new_units_caption(new_shares))
try:
    month_inputs = constraint_month_inputs(
        plan.at(target_level).process_months,
        product_table,
        process=process,
        product=product,
        months=months,
        general_target=general_target,
    )
    new_units = (
        tuple(
            NewUnit(
                name=entry.unit,
                start=entry.start,
                units=entry.units,
                until=entry.until,
                modules=_unit_modules(entry.modules),
            )
            for entry in new_shares.starts
        )
        if new_shares is not None
        else ()
    )
    result: ConstraintResult = simulate_constraint(month_inputs, conditions, new_units)
except (KeyError, ValueError) as exc:
    # KeyError 는 따옴표 없는 첫 인자(빠진 이름)를 싣는다 — 이름이라 물결표를 막는다.
    message = (
        markdown_safe_tildes(exc.args[0])
        if isinstance(exc, KeyError) and exc.args
        else bootstrap_error_message(exc)
    )
    render_header(process, f"**{literal_markdown(process_label)}** · {literal_markdown(product)}")
    failure = f"제약 시뮬레이션을 계산하지 못했습니다 — {message}"
    render_data_error(failure, code="CS-01", text="제약 시뮬레이션을 계산하지 못했습니다")
    st.stop()

labels = ConstraintLabels(
    process=process,
    process_label=process_label,
    product=product,
    target_percent=target_percent,
    general_percent=None if general_value is None else float(general_value),
    warning_targets=(
        tuple((month, thresholds.boundary_for(month)[1]) for month in months)
        if general_value is None
        else ()
    ),
    today=today,
)
period_text = (
    month_label(period.start)
    if period.start == period.end
    else f"{month_label(period.start)}–{month_label(period.end)}"
)
# 머리 줄은 서지 않는다 — 조건을 되읊지 않고(사이드바가 조건이다) 소요 · 가용의 출처와 읽는 법은
# Guide 다(2026-11-08 사용자 그림 메모 g12). 입력 비가동은 위 상태 알림 `CS-05`, UPEH 가정 미적용은
# 상태 알림 `CS-06` 이다.
if result.kpis.constrained_months == 0:
    st.caption(
        f"제약 기간({period_text})에 {literal_markdown(product)} 소요가 없어 떼어 줄 대수가 "
        "없습니다."
    )


def report_late_starts(process: str, result: ConstraintResult) -> None:
    """첫날이 오늘보다 앞인 개조 창 · 신규 대기의 상태 알림(`CS-04`) — 그래프 · 계산표의 그 달
    감소가 「지금 시작하면」 이 아니라 「제때 시작했다면」 의 모습이라는 가정이다(설계 규칙
    UI-NTF-05 — 자리에는 그리지 않는다). 범위는 세션 설비 기준과 공정, 내용은 그 창 · 대기의
    (달, 첫날, 끝, 대수)다. 계산이 선 회차마다 부르고, 없으면 「해소」 다. 알림 칸 JS 가 평문으로
    그린다."""
    windows = late_windows(result, today)
    waits = late_waits(result, today)
    scope = equipment_scope(equipment_session) if equipment_session is not None else None
    parts = [f"개조 창 {len(windows)}개"] if windows else []
    if waits:
        parts.append(f"신규 대기 {len(waits)}개")
    lines = [f"{window_line(window)} — {WINDOW_LATE_TEXT}" for window in windows] + [
        f"{waiting_line(item)} — {WAIT_LATE_TEXT}" for item in waits
    ]
    alerts.state(
        "CS-04",
        scope={**(scope.scope if scope is not None else {}), "process": process},
        content=[
            ["window", window.month, window.start.isoformat(), window.end.isoformat(), window.units]
            for window in windows
        ]
        + [
            ["wait", item.month, item.unit, item.module, item.start.isoformat(), item.units]
            for item in waits
        ]
        or None,
        active=bool(lines),
        text=f"첫날이 지난 {' · '.join(parts)} — 제때 시작했다면의 확보율" if lines else None,
        full=(
            "\n".join(
                [
                    f"{process_label} — 그래프 · 계산표의 그 달 감소는 「지금 시작하면」 이 아니라 "
                    "「제때 시작했다면」 의 모습입니다.",
                    *lines,
                ]
            )
            if lines
            else None
        ),
        scope_label=" · ".join(
            part for part in ((scope.label if scope is not None else ""), process_label) if part
        ),
    )


with notices:
    report_late_starts(process, result)
render_constraint_kpis(result, labels)
settle_selected_month(result)
render_constraint_view(ConstraintView(result=result, labels=labels))
