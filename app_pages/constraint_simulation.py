# Purpose: 소요대수와 설비 일정 기준 가용으로 공정 하나의 미래 제약 영향을 보는 화면을 그린다.

"""제약 시뮬레이션 — 실행 관리 셋째 화면(필요 단축 일정 다음, 2026-10-24 사용자 결정).

정체성: 「한 공정에 미래 구간 제약(특정 제품만 쓸 수 있게 개조·전용해야 하는 설비)이 생기면, 제약
제품에 먼저 떼어 준 뒤 기존 제품의 확보율이 언제부터 얼마나 떨어지는가」 를 그때그때 본다.
**저장하지 않는다** — 조건은 이 세션에만 있고 시뮬레이션·설비 DB 어디에도 쓰지 않는다.

입력(새 무거운 계산이 없다 — 공정 Capa 상세가 쓰는 캐시 래퍼를 **같은 키로** 다시 받는다):

- **공통 진입** — `page_bootstrap.process_page_inputs`(공정 Capa 상세와 같은 함수 — 판정 기준·유효
  기간 `RQ_REQB`·시나리오 키·확보율·달·공정 선택지). 확보율 프레임은 선택지·달에만 쓴다.
- **소요대수** — 공정 합은 계획의 `소요대수`, 제품별은 `get_process_product_demand(split="제품정보",
  limit=CONSTRAINT_PRODUCT_LIMIT)`(행을 다 더하면 그 공정 소요). 한 제품정보의 모든 양산구분이
  든다(D4).
- **설비 일정 기준 가용(단축 전)** — 사이드바 세션 설비 시나리오(D6)의 계산 세 표·Cut-off 로 공정
  Capa 상세 ②와 같은 계획 칸(`load_required_shortening_for_target` — 공식 칸, 목표는 키 맞춤용 HOME
  확보기준)을 받아 `가용대수` 열만 읽는다(D3). 필요 단축 일정의 공용 조회
  조건(`0019`)·기준선(`0021`)·세션 칸은 읽지도 쓰지도 않는다. UPEH 가정·HOME 얹기는 걸지 않는다(D5).

계산은 순수 서비스(`services/constraint_simulation.py`)다. 오류 갈래는 넷으로 가른다 — 공통
진입(카드 캡션 「계산을 멈춰 …」), 제품별 소요 받기(카드 캡션 「제품을 읽지 못했습니다」 + 본문
「제품별 소요를 읽지 못했습니다 — {글}」 — 「소요가 있는 제품이 없다」 안내와 가른다), 계획
받기(「설비 일정을 계산하지 못했습니다 — …」, 두 DB 경로), 어댑터·서비스의
`ValueError`·`KeyError`(「제약 시뮬레이션을 계산하지 못했습니다 — {글}」, DB 경로 없음).
`BOOTSTRAP_ERRORS` 에 `KeyError`·`ValueError` 가 들어 있어 한 `try` 로 묶으면 뒤의 글이 앞의 글로
둔갑한다.

본문은 머리 한 줄 → 출처 띠 → 요약 넷(프래그먼트 밖) → 본문
프래그먼트(`components/constraint_simulation_view` — 달 누름·비중 토글만 그 안에서 돈다).

개조 묶음의 2판 옵션(2026-10-26 사용자 결정, 개조 끔이면 잠긴다) — 「보유 제약 설비」 숫자 칸(환산
대수, 기본 0)과 「신규 설비는 개조 없이」 토글 + 기준일(기본 오늘). 신규 몫 A_new(m) 은 새 캐시 없이
공정 Capa 상세 ③·④ 와 같은 설비 일정 칸(`get_process_equipment_timeline` — 같은 키)을 기준일로 거른
값이고(`new_unit_availability`), 옵션을 켠 회차에만 받는다. 기준일은 어떤 캐시 키에도 들지 않는다.
"""

from datetime import date

import pandas as pd
import streamlit as st

from capa_simulation.components.constraint_simulation_figures import (
    ConstraintLabels,
    general_label,
)
from capa_simulation.components.constraint_simulation_view import (
    ConstraintView,
    render_constraint_kpis,
    render_constraint_view,
    settle_selected_month,
)
from capa_simulation.components.equipment_scenario_status import (
    equipment_basis_label,
    render_equipment_scenario_row,
    render_legacy_trace_warning,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.preset_number_field import render_preset_number_field
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.constraint_simulation_state import (
    CONSTRAINT_ABSENT_KEY,
    CONSTRAINT_GENERAL_INPUT_KEY,
    CONSTRAINT_GENERAL_KEY,
    CONSTRAINT_GENERAL_PILLS_KEY,
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
    CONSTRAINT_TARGET_INPUT_KEY,
    CONSTRAINT_TARGET_KEY,
    CONSTRAINT_TARGET_PILLS_KEY,
    DEFAULT_MOD_DAYS,
    DEFAULT_MODIFY,
    DEFAULT_NEW_UNITS,
    DEFAULT_TARGET_PERCENT,
    GENERAL_PRESETS,
    MOD_DAY_PRESETS,
    TARGET_PRESETS,
    follow_period_end,
    follow_period_start,
    seed_new_since,
    seed_owned_units,
    seed_toggle,
    settle_period,
    take_constraint_process_request,
)
from capa_simulation.design.theme import THEME_QUERY_PARAM
from capa_simulation.equipment_scenario_activation import (
    EquipmentSession,
    resolve_equipment_session,
)
from capa_simulation.navigation import AVAILABLE_EQUIPMENT_STATUS, PROCESS_CAPA_DETAIL
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    process_page_inputs,
    prune_choice,
    render_schema_ahead_warning,
)
from capa_simulation.persistence.equipment_cache import (
    get_equipment_repository,
    load_process_cutoff,
)
from capa_simulation.persistence.equipment_repository import EquipmentSnapshot
from capa_simulation.process_detail_state import PROCESS_PARAM as DETAIL_PROCESS_PARAM
from capa_simulation.scenario_activation import active_scenario_label
from capa_simulation.services.constraint_simulation import (
    GENERAL_INPUT_RANGE,
    MODIFICATION_DAYS_RANGE,
    OWNED_UNITS_RANGE,
    TARGET_RANGE,
    ConstraintConditions,
    ConstraintResult,
    constraint_month_inputs,
    simulate_constraint,
)
from capa_simulation.services.korean_particle import topic_particle
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_capa_detail import OTHER_ROW_COLUMN, month_column
from capa_simulation.services.process_equipment_timeline import (
    DynamicReadiness,
    NewUnitAvailability,
    dynamic_readiness,
    new_unit_availability,
)
from capa_simulation.services.required_shortening import target_from_thresholds
from capa_simulation.services.securement_threshold import securement_threshold_caption
from capa_simulation.services.simulation_cache import (
    get_process_equipment_timeline,
    get_process_product_demand,
    load_required_shortening_for_target,
    process_timeline_key_from_shortening,
    required_shortening_cache_key,
    required_shortening_target_cache_key,
    scenario_required_equipment,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_DEFAULT_PERCENT,
    UPEH_ASSUMPTION_PERCENT_KEY,
)

CARD_LABEL = "제약 시뮬레이션 조건"
CARD_NAME = "constraint_simulation"
CARD_ICON = ":material/call_split:"
PAGE_TITLE = "제약 시뮬레이션"
PAGE_DESCRIPTION = (
    "공정 하나에 미래 제약(제약 제품 전용 설비)이 생기면 — 제약 제품에 먼저 떼어 준 뒤 기존 제품 "
    "확보율이 언제부터 얼마나 떨어지는가. 저장하지 않는 그때그때 보기입니다."
)
SESSION_NOTE = (
    "저장하지 않는 시뮬레이션입니다 — 조건은 이 세션에만 남고 다른 사람에게 보이지 않습니다. 공식 "
    "확보율·HOME·필요 단축 일정은 그대로입니다."
)
AVAILABLE_EQUIPMENT_PAGE = AVAILABLE_EQUIPMENT_STATUS.path
OWNED_HELP = (
    "이미 제약 제품을 돌릴 수 있게 개조·Qual 된 설비(환산 대수). 설비 일정 기준 가용 안에 "
    "든다고 보고, 제약 몫이 늘 때 먼저 써 그만큼 개조하지 않습니다. 쓰지 않는 동안과 기간 밖에는 "
    "기존 제품에 씁니다. 「신규 설비는 개조 없이」 에 드는 호기는 빼고 적으세요(두 번 셉니다)."
)
NEW_UNITS_HELP = (
    "기여 시작(Qual 다음 날)이 기준일 이후인 신규 호기(공정 Capa 상세 ③ 과 같은 날짜)는 셋업 때 "
    "제약 제품으로 Qual 한다고 보고, 들어오는 그 달 제약 몫 증가분까지 개조 없이 씁니다. 그보다 "
    "많은 신규와 기간 전에 들어온 신규는 기존 제품에 쓰여 그 뒤로는 일반 설비와 같습니다(제약에 "
    "쓰려면 개조)."
)


# 주소 `?process=` 는 **무엇보다 먼저** 꺼내고 그 키 하나만 지운다 — 부트스트랩이 멈춘 회차에도
# 주소에 남지 않게(공정 Capa 상세 머리 「이 공정 제약 시뮬레이션」 이 싣는다).
requested_process = take_constraint_process_request()

render_page_header("제약 시뮬레이션", description=PAGE_DESCRIPTION)
# 공정·조건 한 줄과 「← 공정 Capa 상세」 자리. 공정과 계산이 정해진 뒤 채운다 — 블록이라 계산 동안
# 앞 회차 줄이 남는다(빈 블록은 그려지지 않으므로 border·height 를 주지 않는다).
header_marks = st.container()
render_page_guide("constraint_simulation", title=PAGE_TITLE)
# 설비 DB 경고(이 코드보다 새 스키마·옛 배포 흔적)와 넘겨받은 공정 알림 자리 — 맨 위에 선다.
notices = st.container()
process_labels = get_process_labels()
today = date.today()

try:
    page_inputs = process_page_inputs(str(DUCKDB_PATH.resolve()))
except BOOTSTRAP_ERRORS as exc:
    # 카드는 멈춘 회차에도 선다 — 「조회 조건」 제목만 남은 빈 구역을 만들지 않는다.
    with condition_card(CARD_LABEL, name=CARD_NAME, icon=CARD_ICON):
        st.caption("계산을 멈춰 공정을 고를 수 없습니다.")
    st.error(bootstrap_error_message(exc))
    st.stop()

thresholds = page_inputs.thresholds
context = page_inputs.context
active_scenario = context.active_scenario
months = list(page_inputs.months)
process_options = page_inputs.process_options

# 설비 — 세션 설비 시나리오(새 세션은 공식). 못 읽으면 까닭을 들고 카드는 그대로 세운다.
equipment_session: EquipmentSession | None = None
snapshot: EquipmentSnapshot | None = None
cutoff = pd.DataFrame()
equipment_error = ""
try:
    equipment_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    equipment_session = resolve_equipment_session(equipment_path)
    snapshot = equipment_session.snapshot
    cutoff = load_process_cutoff(equipment_path)
    with notices:
        render_schema_ahead_warning(get_equipment_repository(equipment_path).schema_ahead)
        render_legacy_trace_warning(equipment_session)
except BOOTSTRAP_ERRORS as exc:
    snapshot = None
    cutoff = pd.DataFrame()
    equipment_error = bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
else:
    render_equipment_scenario_row(equipment_session)

# 공정 — 넘겨받은 공정이 선택지에 있으면 위젯 칸에 적는다(공정 선택 상자보다 먼저).
if requested_process is not None:
    if requested_process in process_options:
        st.session_state[CONSTRAINT_PROCESS_KEY] = requested_process
    else:
        # 주소 인자 글이 그대로 오므로 마크다운에 싣는 글만 escape 하고 조사는 원래 이름으로 고른다.
        missing_label = process_labels.label(requested_process)
        missing = f"「{literal_markdown(missing_label)}」{topic_particle(f'「{missing_label}」')}"
        notices.warning(
            f"넘겨받은 공정 {missing} 시나리오·조회기간에 없어 첫 공정을 엽니다.",
            icon=":material/help:",
        )
prune_choice(
    CONSTRAINT_PROCESS_KEY,
    process_options,
    default=process_options[0] if process_options else None,
)


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
with condition_card(CARD_LABEL, name=CARD_NAME, icon=CARD_ICON):
    st.caption("**대상**")
    selected_process = st.selectbox(
        "공정",
        process_options,
        key=CONSTRAINT_PROCESS_KEY,
        persist_state="session",
        disabled=not process_options,
        # 표시만 바꾼다. 선택값은 원본이다 — 보이는 글자가 겹치면 「표시명 (원본)」 으로 가른다.
        format_func=process_labels.unique_format_func(process_options),
    )
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
        st.caption("제품을 읽지 못했습니다.")
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

    st.caption(":material/person: **이 세션만** — 저장하지 않습니다")
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
        number_format="%d",
        fallback=DEFAULT_TARGET_PERCENT,
        preset_label=lambda value: f"{value:g}%" if value is not None else "",
        help="제약 제품에 먼저 떼어 줄 몫 — 필요 대수 = 올림(제약 제품 소요 × 이 값).",
        tone="warning",
    )
    home_percent = thresholds.default_secure * 100
    general_value = render_preset_number_field(
        "기준 확보율",
        value_key=CONSTRAINT_GENERAL_KEY,
        pills_key=CONSTRAINT_GENERAL_PILLS_KEY,
        input_key=CONSTRAINT_GENERAL_INPUT_KEY,
        presets=GENERAL_PRESETS,
        default=None,
        minimum=GENERAL_INPUT_RANGE[0] * 100,
        maximum=GENERAL_INPUT_RANGE[1] * 100,
        step=0.5,
        unit="%",
        number_format="%.1f",
        fallback=home_percent,
        preset_label=lambda value: "HOME 기준" if value is None else f"{value:g}%",
        help=(
            "기존 제품 판정 기준. 「HOME 기준」 은 HOME → Preference 공용 판정 기준(기본 + "
            f"월별 예외)을 달마다 씁니다 — HOME 기본은 정확히 {home_percent:g}% 라 버튼 "
            "110%(110.0%)와 다를 수 있습니다."
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
    # 2판 옵션 — 늘 그리고 개조 끔이면 잠근다(갈래마다 카드 모양이 같다). 보유 대수는 사람마다 아는
    # 사실 값이라 D10 버튼을 두지 않는다.
    seed_owned_units(OWNED_UNITS_RANGE[1])
    owned_units = st.number_input(
        "보유 제약 설비 (환산 대수)",
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
    new_since = st.date_input(
        "신규 기준일",
        key=CONSTRAINT_NEW_SINCE_KEY,
        persist_state="session",
        format="YYYY-MM-DD",
        disabled=not (modify and new_units_on),
        help="기여 시작이 이날 이후(그날 포함)인 호기를 신규로 봅니다. 처음 값은 오늘입니다.",
    )
    # 개조 끔이면 두 옵션은 걸리지 않는다 — 결과·머리에 걸리지 않은 조건이 남지 않게 넘기지 않는다.
    owned_value = int(owned_units) if modify and isinstance(owned_units, int) else 0
    new_unit_since = new_since if modify and new_units_on and isinstance(new_since, date) else None
    new_units_slot = st.container()
    cutoff_slot = st.container()


def render_reason_card(title: str, detail: str, *, equipment_link: bool) -> None:
    """설비 일정이 서지 않는 까닭 카드 한 장(+ 다음 화면 링크)."""
    with st.container(border=True, key=CONSTRAINT_ABSENT_KEY):
        st.markdown(f":material/event_busy: **{title}**")
        st.caption(detail)
        if equipment_link:
            render_page_link(
                AVAILABLE_EQUIPMENT_PAGE,
                label="가용설비 현황에서 설비·Cut-off 보기",
                icon=":material/precision_manufacturing:",
            )


def render_header(process: str, line: str) -> None:
    """머리 한 줄(공정·조건)과 오른쪽 끝 「← 공정 Capa 상세」."""
    with header_marks.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(line, width="content")
        st.space("stretch")
        theme_value = st.query_params.get(THEME_QUERY_PARAM)
        params = {DETAIL_PROCESS_PARAM: process}
        if theme_value:
            params[THEME_QUERY_PARAM] = str(theme_value)
        render_page_link(
            PROCESS_CAPA_DETAIL.path,
            label="공정 Capa 상세",
            icon=":material/arrow_back:",
            query_params=params,
        )


if selected_process is None or not months or period is None:
    st.info("조회기간에 확보율을 낼 공정이 없습니다.", icon=":material/info:")
    st.stop()

process = str(selected_process)
process_label = process_labels.label(process)

readiness: DynamicReadiness | None = None
if not equipment_error:
    readiness = dynamic_readiness(
        snapshot.calculation_frames()[1] if snapshot is not None else None,
        snapshot.baseline if snapshot is not None else None,
        cutoff,
        process=process,
    )
if readiness is not None and readiness.cutoff_days is not None:
    cutoff_line = (
        f"Cut-off {readiness.cutoff_days}일 — 가용설비 현황 「설정」 팝업의 공정별 값(모든 설비 "
        "시나리오 공용)"
    )
with cutoff_slot:
    st.caption(cutoff_line)

if readiness is None:
    render_header(
        process, f"**{literal_markdown(process_label)}** :blue-badge[설비 일정 없음: 설비 DB 오류]"
    )
    render_reason_card(
        "설비 일정 없음: 설비 DB 를 읽지 못했습니다",
        equipment_error or "설비 DB 를 열지 못했습니다.",
        equipment_link=False,
    )
    st.stop()
if not readiness.ready or readiness.cutoff_days is None or snapshot is None:
    render_header(process, f"**{literal_markdown(process_label)}** :blue-badge[{readiness.badge}]")
    render_reason_card(
        readiness.badge,
        f"{readiness.detail} 제약 시뮬레이션은 설비 일정 기준 가용(공정 Capa 상세 ② 와 같은 "
        "값)으로 계산하므로 설비 DB 에 저장본이 있고 이름이 같으며 Cut-off 가 적힌 공정에만 "
        "섭니다.",
        equipment_link=True,
    )
    st.stop()
if product_error:
    render_header(process, f"**{literal_markdown(process_label)}**")
    st.error(f"제품별 소요를 읽지 못했습니다 — {product_error}")
    st.stop()
if selected_product is None:
    render_header(process, f"**{literal_markdown(process_label)}**")
    st.info(
        "이 공정은 조회기간에 소요가 있는 제품이 없어 제약 제품을 고를 수 없습니다.",
        icon=":material/info:",
    )
    st.stop()
product = str(selected_product)

# 계획 — 공정 Capa 상세 ② 와 같은 칸·같은 키(목표는 키 맞춤용 — 단축 열은 읽지 않는다).
baseline, equipment, downtime = snapshot.calculation_frames()
target_level = target_from_thresholds(thresholds, months)
shortening_key = required_shortening_cache_key(
    page_inputs.capacity_cache_key,
    equipment=equipment,
    downtime=downtime,
    baseline=baseline,
    cutoff=cutoff,
    months=tuple(months),
    today=today,
)
try:
    plan = load_required_shortening_for_target(
        required_shortening_target_cache_key(shortening_key, target_level),
        equipment,
        downtime,
        baseline,
        cutoff,
        required_equipment=scenario_required_equipment(
            page_inputs.capacity_cache_key,
            scenario_tables=active_scenario["tables"],
            reference_tables=context.reference_tables,
        ),
    )
    # 신규 몫 — 공정 Capa 상세 ③·④ 와 같은 설비 일정 칸(같은 키)을 기준일로 거른다. 켠 회차에만.
    new_shares: NewUnitAvailability | None = None
    if new_unit_since is not None:
        new_shares = new_unit_availability(
            get_process_equipment_timeline(
                process_timeline_key_from_shortening(shortening_key, process),
                equipment,
                downtime,
                baseline,
                cutoff,
            ),
            since=new_unit_since,
        )
except BOOTSTRAP_ERRORS as exc:
    render_header(
        process, f"**{literal_markdown(process_label)}** :blue-badge[설비 일정 없음: 계산 오류]"
    )
    st.error(
        "설비 일정을 계산하지 못했습니다 — "
        + bootstrap_error_message(exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH))
    )
    st.stop()

if process not in plan.processes:
    # 판정을 지나도 계획은 「가용 공정 ∩ 소요 공정」 만 맞댄다 — KeyError 로 떨어뜨리지 않는다.
    missing_cutoff = process in plan.missing_cutoff
    render_header(process, f"**{literal_markdown(process_label)}** :blue-badge[설비 일정 없음]")
    render_reason_card(
        "설비 일정 없음: Cut-off 미기재" if missing_cutoff else "설비 일정 없음: 계획에 공정 없음",
        (
            "가용설비 현황의 공정별 Cut-off 에 이 공정이 없습니다."
            if missing_cutoff
            else "설비 일정 기준 가용에 이 공정이 없습니다 — 설비 마스터 공정소분류·기존보유 공정 "
            "이름이 시나리오 공정과 완전히 같아야 맞댑니다."
        ),
        equipment_link=True,
    )
    st.stop()


def new_units_caption(shares: NewUnitAvailability) -> str:
    """카드 개조 묶음의 신규 한 줄 — 기준일 이후 기여 시작 호기 수와 앞 몇 대의 이름."""
    if not shares.units:
        return "기준일 이후 기여를 시작하는 신규 설비가 없습니다."
    names = ", ".join(literal_markdown(name) for name in shares.units[:4])
    more = f" 외 {len(shares.units) - 4}대" if len(shares.units) > 4 else ""
    return (
        f"기준일 이후 기여 시작 신규 설비 {len(shares.units)}대(조회기간에 가용 "
        f"{shares.in_axis}대) · {names}{more}"
    )


def general_target(month: int) -> float:
    """그 달 기준 확보율(비율) — HOME 이면 공용 판정 기준의 그 달 값, 아니면 고른 스칼라."""
    if general_value is None:
        return float(thresholds.secure_for(month))
    return float(general_value) / 100


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
    cutoff_days=int(readiness.cutoff_days),
    owned_units=owned_value,
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
        new_units=new_shares.by_month() if new_shares is not None else None,
        new_units_before=new_shares.before if new_shares is not None else 0.0,
    )
    result: ConstraintResult = simulate_constraint(month_inputs, conditions)
except (KeyError, ValueError) as exc:
    message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
    render_header(process, f"**{literal_markdown(process_label)}** · {literal_markdown(product)}")
    st.error(f"제약 시뮬레이션을 계산하지 못했습니다 — {message}")
    st.stop()

labels = ConstraintLabels(
    process=process,
    process_label=process_label,
    product=product,
    target_percent=target_percent,
    general_percent=None if general_value is None else float(general_value),
)
period_text = (
    month_label(period.start)
    if period.start == period.end
    else f"{month_label(period.start)}–{month_label(period.end)}"
)
modification_text = f"개조 {conditions.modification_days}일" if conditions.modifies else "개조 없음"
if conditions.uses_owned_units:
    modification_text += f" · 보유 제약 {conditions.owned_units}대"
if conditions.uses_new_units and new_unit_since is not None:
    modification_text += f" · 신규 개조 없이({new_unit_since.isoformat()}~)"
render_header(
    process,
    f"**{literal_markdown(process_label)}** · {literal_markdown(product)} · {period_text} · "
    f"제약 {target_percent}% · 기준 {literal_markdown(general_label(labels, result))} · "
    f"{modification_text}",
)
with header_marks:
    st.caption(SESSION_NOTE)

# 출처 띠 — 소요는 활성 시나리오(세션만 읽음), 가용은 세션 설비 시나리오.
scenario_label = active_scenario_label()
scenario_text = (
    f"「{literal_markdown(scenario_label.scenario_name)} r{scenario_label.revision_no}」"
    if scenario_label is not None
    else "활성 시나리오"
)
equipment_text = equipment_basis_label(equipment_session) if equipment_session is not None else None
band = (
    f":material/database: 소요 = 활성 시나리오 {scenario_text} "
    f"{literal_markdown(process_label)} 소요를 제품정보로 나눔"
    f"({literal_markdown(product)} / 그 밖) · 가용 = 설비 일정 기준"
    + (f"({literal_markdown(equipment_text)}, 단축 전)" if equipment_text else "(단축 전)")
    + " · 대수는 환산 대수 — HOME·Static 확보율(기준정보 가용)과 다를 수 있음"
)
upeh_percent = st.session_state.get(UPEH_ASSUMPTION_PERCENT_KEY, UPEH_ASSUMPTION_DEFAULT_PERCENT)
if isinstance(upeh_percent, int) and upeh_percent != UPEH_ASSUMPTION_DEFAULT_PERCENT:
    band += " · UPEH 가정은 이 화면에 걸리지 않습니다(공식 소요)"
if new_shares is not None:
    band += (
        f" · 신규 = 기여 시작 {new_shares.since.isoformat()} 이후 호기 {len(new_shares.units)}대"
        "(공정 Capa 상세 ③ 과 같은 날짜)"
    )
st.caption(band)
if period.moved:
    st.info("조회기간이 바뀌어 제약 기간을 보이는 달로 옮겼습니다.", icon=":material/event_busy:")
if result.kpis.constrained_months == 0:
    st.info(
        f"제약 기간({period_text})에 {literal_markdown(product)} 소요가 없어 떼어 줄 대수가 "
        "없습니다.",
        icon=":material/info:",
    )

render_constraint_kpis(result, labels)
settle_selected_month(result)
render_constraint_view(ConstraintView(result=result, labels=labels, today=today))
