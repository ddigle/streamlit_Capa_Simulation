# Purpose: 공정 하나의 산출 근거·부족한 달·메우는 설비 일정을 잇는 「공정 Capa 상세」를 그린다.

"""공정 Capa 상세 — 공정 하나의 산출 근거 → 부족한 달 → 그 달을 메우는 설비 일정을 잇는 화면.

차례(2026-10-15 사용자 결정 4 — 목업 그대로):

0. **머리** — 공정 표시명과 배지 둘(`공식 · Core Data`, 설비 일정 상태), 오른쪽 끝 「← HOME」
   링크, HOME 에서 왔으면 출처 띠. 사이드바 `공정 상세 조건` 카드 — 공정 하나와 제품
   거르기(펼친 제품 행에만 걸린다).
1. **KPI 넷** — 최저 확보율, 확보기준 미달 달·월 최대 부족, 부족 원인, 대책(설비 일정 기준).
2. ~ 7. **본문 프래그먼트**(`components/process_capa_view.render_process_detail_view`, key
   `process_detail_view`) — 표 도구 줄, 결합 월 캔버스(① 공식 요약 표 · ② 설비 일정 기준
   가용 · ③ 신규 설비와 단축 · ④ 호기별 비가동), 범례, 산출 근거 패널. 칸을 누르면 그 구획만
   다시 돈다.
8. **정리 줄** — 알림, 「이 공정 단축 일정 CSV」, 필요 단축 일정 화면 링크(설비 일정이 설 때만).
9. **Guide**(`guides/process_capa_detail.md`) — 헤더의 Guide 단추.

입력은 이 화면이 직접 모은다.

- **공식 기준** — 공통 진입(`page_bootstrap`), 유효 기간은 산출 결과처럼 `RQ_REQB` 원천에서
  정한다. 확보율은 키 전용 캐시(`get_scenario_securement_rate`), 요약은 회차마다
  (`build_process_capa_summary` — 판정 기준에 닿는다).
- **설비 일정(참고)** — 설비 DB 의 최신 저장본·Cut-off 를 **읽기만** 한다
  (`PageSpec.uses_equipment_db`). 샘플 fleet 은 쓰지 않는다 — 저장본이 없으면 「설비 일정
  없음」이다. 판정(`dynamic_readiness`)을 통과한 공정만 계획
  (`get_required_shortening_for_target` — 단축 목표는 HOME Preference 확보기준을 달마다,
  사용자 결정 2)과 설비 일정(`get_process_equipment_timeline`)을 받는다. 필요 단축 일정 화면의
  공용 조회 조건(설비 DB `0019`)·진척 비교 기준선(`0021`)은 읽지도 쓰지도 않는다(사용자
  결정 1).
- **HOME 표시 확보율** — HOME 의 확보율 보정·선행 B/O 를 켜고 왔거나(출처 띠) 지금 HOME 이 그
  토글을 켜 두었으면, HOME 과 같은 함수로 얹은 값을 요약 표 회색 줄로 둔다. 선행 변동률의
  계획은 HOME 과 **같은 캐시 키**(`display_month_range` 범위)로 받는다. 원 확보율과 같으면 줄을
  두지 않는다.

공정·달은 **공정 선택 상자보다 먼저** 정한다(`process_detail_state.resolve_process_and_month`)
— HOME 전달 칸 → 주소 인자 → 세션 → 기본값(기간 최저 확보율 공정, 그 공정의 첫 확보기준 미달
달). 전달 칸은 그보다도 앞, 부트스트랩 전에 꺼낸다 — 오류로 멈춘 회차가 칸을 남기지 않게.
"""

from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.process_capa_canvas import DynamicCanvasInput
from capa_simulation.components.process_capa_view import (
    DynamicView,
    ProcessDetailView,
    render_closing_row,
    render_process_detail_view,
    render_process_kpis,
)
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.home_state import (
    ADVANCE_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    HOME_TOGGLE_DEFAULTS,
    PAST_DATA_TOGGLE_KEY,
)
from capa_simulation.navigation import HOME
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
    prune_list_selection,
    resolve_effective_months,
    stop_calculation_on_error,
)
from capa_simulation.persistence.cache import (
    load_global_advance_load,
    load_global_execution_capacity,
    load_global_past_data,
    load_global_securement_threshold,
)
from capa_simulation.persistence.equipment_cache import (
    load_latest_equipment_snapshot,
    load_process_cutoff,
)
from capa_simulation.process_detail_state import (
    ORIGIN_BAND_ICON,
    PROCESS_DETAIL_PROCESS_KEY,
    PROCESS_DETAIL_PRODUCT_FILTER_KEY,
    first_shortfall_month,
    lowest_rate_process,
    origin_band_text,
    resolve_process_and_month,
    take_process_detail_request,
)
from capa_simulation.scenario_state import scenario_month_table
from capa_simulation.services.advance_load import build_advance_load_ratio
from capa_simulation.services.display_order_scopes import (
    PAGE_CALCULATION,
    TAB_REQUIRED,
    TAB_SECUREMENT,
)
from capa_simulation.services.equipment_units import format_unit_count
from capa_simulation.services.frame_contracts import normalize_demand_basis
from capa_simulation.services.korean_particle import with_object_particle, with_topic_particle
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.past_data import display_month_range
from capa_simulation.services.process_capa_detail import (
    PRODUCT_DEMAND_SPLITS,
    build_process_capa_summary,
    home_display_rates,
    process_capa_kpis,
)
from capa_simulation.services.process_equipment_timeline import (
    DynamicReadiness,
    dynamic_readiness,
    production_position,
    unit_events,
)
from capa_simulation.services.process_picker import build_process_picker_summary
from capa_simulation.services.required_shortening import (
    target_from_thresholds,
    unit_export_frame,
)
from capa_simulation.services.simulation_cache import (
    build_home_simulation_cache_key,
    check_scenario_capacity,
    csv_export_key,
    display_order_digest,
    get_display_ordered_values,
    get_export_csv,
    get_home_lob_without_edp,
    get_home_simulation,
    get_process_calculation_rows,
    get_process_equipment_timeline,
    get_required_shortening_for_target,
    get_scenario_securement_rate,
    get_undated_equipment,
    get_usage_excluded_equipment,
    process_timeline_key_from_shortening,
    required_shortening_cache_key,
    required_shortening_target_cache_key,
    scenario_cache_key,
    scenario_required_equipment,
)
from capa_simulation.services.undated_equipment import undated_counts
from capa_simulation.services.usage_basis import usage_excluded_count
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

# 사이드바 조건 카드. 이 화면이 실제로 읽는 고유 조건(공정 하나, 펼친 제품 행의 거르기)을 모은다.
CARD_LABEL = "공정 상세 조건"
CARD_NAME = "process_capa_detail"
CARD_ICON = ":material/troubleshoot:"
# 머리 배지. 공식 숫자는 늘, 설비 일정은 판정에 따라 「참고」·「없음: 까닭」.
OFFICIAL_BADGE = ":gray-badge[공식 · Core Data]"
# HOME 표시 확보율이 원 확보율과 같다고 보는 차이.
HOME_RATE_TOLERANCE = 1e-9

# HOME 이 남긴 전달 칸은 **무엇보다 먼저** 꺼낸다. 아래 부트스트랩·계산이 오류로 멈추면 그 회차는
# 공정·달을 정하는 자리에 닿지 못한다 — 그때 칸이 남으면 나중에 사이드바로 들어온 방문이 이 칸을
# 「HOME 에서 온 것」으로 읽는다.
home_request = take_process_detail_request()

render_page_header("공정 Capa 상세")
# 공정 표시명·배지 자리. 공정과 설비 일정 판정이 정해진 뒤 채운다 — 제목 바로 아래에 선다.
header_marks = st.empty()
render_page_guide("process_capa_detail", title="공정 Capa 상세")
# 공정 표시명은 화면 라벨이다. 선택값·세션값·주소 인자는 원본 공정명이다.
process_labels = get_process_labels()
today = date.today()

try:
    # 판정 기준은 HOME → Preference 의 공용 프로필이다(기본값 + 월별 예외). 기본 공정·기본 달을
    # 정할 때도 HOME·Static Capa 와 같은 판정(`thresholds.status`)을 쓴다.
    thresholds = load_global_securement_threshold(str(DUCKDB_PATH.resolve())).thresholds
    context = load_page_context()
    active_scenario = context.active_scenario
    reference_tables = context.reference_tables
    # 유효 기간은 산출 결과와 같이 RQ_REQB 원천에서 잡는다 — 같은 시나리오 키를 나눠 쓴다.
    effective_start, effective_end = resolve_effective_months(
        context,
        active_scenario["tables"]["RQ_REQB"],
        "RQ_REQB",
        empty_message="선택 범위에 소요대수 산출 기준이 없습니다.",
    )
    capacity_cache_key = scenario_cache_key(
        context.reference_version, active_scenario, effective_start, effective_end
    )
    try:
        securement_rate = get_scenario_securement_rate(
            capacity_cache_key,
            _scenario_tables=active_scenario["tables"],
            _reference_tables=reference_tables,
            _available_equipment=scenario_month_table(
                active_scenario, "RQ_EQP_AVBL", effective_start, effective_end
            ),
        )
    except BOOTSTRAP_ERRORS:
        # 대당 Capa·소요대수 계산이 멈춘 것이면 「계산 멈춤」과 함께 그 오류를 먼저 낸다. 계산은
        # 섰는데 가용대수·확보율에서 난 오류면 그 오류를 그대로 낸다(Static Capa 와 같은 길).
        stop_calculation_on_error(
            check_scenario_capacity,
            capacity_cache_key,
            _scenario_tables=active_scenario["tables"],
            _reference_tables=reference_tables,
        )
        raise
    process_column = securement_rate["공정"].astype("string").str.strip()
    order_key = display_order_digest(reference_tables["RQ_DISPLAY_ORDER"])
    # 공정 차례는 산출 결과 확보율 탭·HOME 공정 필터와 같은 공용 표시순서 범위다.
    process_options = get_display_ordered_values(
        pd.DataFrame({"공정": sorted(process_column.dropna().unique().tolist())}),
        order_key,
        PAGE_CALCULATION,
        TAB_SECUREMENT,
        _display_order=context.display_order,
    )
except BOOTSTRAP_ERRORS as exc:
    # 카드는 멈춘 회차에도 선다 — 「조회 조건」 제목만 남은 빈 구역을 만들지 않는다.
    with condition_card(CARD_LABEL, name=CARD_NAME, icon=CARD_ICON):
        st.caption("계산을 멈춰 공정을 고를 수 없습니다.")
    st.error(bootstrap_error_message(exc))
    st.stop()

months = sorted(
    {
        int(month)
        for month in securement_rate["생산계획년월"]
        if effective_start <= int(month) <= effective_end
    }
)


def default_process_choice() -> str | None:
    """기본 공정 — 조회기간 최저 확보율 공정. 세션·전달 칸·주소로 공정이 정해지지 않은 회차에만
    불린다(공정별 요약과 달마다 판정을 매 회차 만들지 않는다)."""
    return lowest_rate_process(
        build_process_picker_summary(
            securement_rate,
            process_options,
            start_month=effective_start,
            end_month=effective_end,
            thresholds=thresholds,
        )
    )


def default_month_for(process: str | None) -> int | None:
    """그 공정의 첫 확보기준 미달 달. 없으면 None — 첫 달을 연다."""
    if process is None:
        return None
    rows = securement_rate.loc[process_column.eq(process).fillna(False)]
    return first_shortfall_month(
        zip(rows["생산계획년월"].tolist(), rows["확보율"].tolist(), strict=True), thresholds
    )


def product_choices(process: str) -> tuple[list[str], int]:
    """제품 거르기 선택지(축 안 소요가 있는 제품, 산출 결과 · 소요대수 표시순서)와 소요기준 가짓수.

    소요기준은 공정 안에서 늘 한 값이다(계산 규칙) — 둘 이상일 때만 「분류」에 「소요기준」을 둔다.
    공정 조각(`get_process_calculation_rows`)은 키 전용 캐시라 시나리오 전체 프레임을 풀지 않는다.
    """
    rows = get_process_calculation_rows(
        capacity_cache_key,
        process,
        _scenario_tables=active_scenario["tables"],
        _reference_tables=reference_tables,
    ).required_equipment
    if rows.empty:
        return [], 0
    in_axis = rows.loc[pd.to_numeric(rows["생산계획년월"], errors="coerce").isin(months)]
    names = sorted(
        {str(name).strip() for name in in_axis["제품정보"].dropna().tolist() if str(name).strip()}
    )
    ordered = (
        get_display_ordered_values(
            pd.DataFrame({"제품정보": names}),
            order_key,
            PAGE_CALCULATION,
            TAB_REQUIRED,
            _display_order=context.display_order,
        )
        if names
        else []
    )
    bases = int(normalize_demand_basis(in_axis["소요기준"]).dropna().nunique())
    return ordered, bases


# 공정 선택 상자보다 **먼저** 공정·달을 정해 세션에 적는다. HOME 이 넘긴 공정은 위젯 키가 아니라
# 전달 칸으로 오므로 여기서 위젯 키에 옮겨 적어야 첫 회차에도 상자가 그 공정을 보인다.
entry = resolve_process_and_month(
    process_options,
    months,
    request=home_request,
    default_process=default_process_choice,
    default_month=default_month_for,
)

product_options: list[str] = []
demand_bases = 0
with condition_card(CARD_LABEL, name=CARD_NAME, icon=CARD_ICON):
    selected_process = st.selectbox(
        "공정",
        process_options,
        key=PROCESS_DETAIL_PROCESS_KEY,
        persist_state="session",
        disabled=not process_options,
        # 표시만 바꾼다. 선택값은 원본이다 — 보이는 글자가 겹치면 「표시명 (원본)」 으로 가른다
        # (`unique_format_func`). 기본값은 위에서 세션에 적었으므로 `index=` 를 주지 않는다.
        format_func=process_labels.unique_format_func(process_options),
    )
    if selected_process is not None:
        try:
            product_options, demand_bases = product_choices(selected_process)
        except BOOTSTRAP_ERRORS:
            product_options, demand_bases = [], 0
    # 공정을 바꾸면 그 공정에 없는 제품은 걷는다(지우지 않고 새 목록을 적는다).
    prune_list_selection(PROCESS_DETAIL_PRODUCT_FILTER_KEY, product_options)
    chosen_products = st.multiselect(
        "제품 거르기",
        product_options,
        key=PROCESS_DETAIL_PRODUCT_FILTER_KEY,
        persist_state="session",
        placeholder="전체 제품",
        disabled=not product_options,
        help=(
            "본문 「제품별 소요대수」를 펼친 행에만 걸립니다 — 고르지 않은 제품의 소요는 「그 밖」 "
            "한 행에 합쳐 소요대수 합은 그대로입니다."
        ),
    )
    st.caption(
        f"기간 {month_label(effective_start)}–{month_label(effective_end)} · 기본은 기간 최저 "
        "확보율 공정"
    )

if entry.missing_process is not None:
    missing = with_topic_particle(f"「{process_labels.label(entry.missing_process)}」")
    st.warning(f"넘겨받은 공정 {missing} 이 시나리오·조회기간에 없어 기본 공정을 엽니다.")
if entry.month_outside is not None and entry.month is not None:
    outside = with_topic_particle(month_label(entry.month_outside))
    opened = with_object_particle(month_label(entry.month))
    st.info(
        f"넘겨받은 {outside} 이 화면 기간({month_label(effective_start)}–"
        f"{month_label(effective_end)}) 밖이라 {opened} 엽니다.",
        icon=":material/event_busy:",
    )
if entry.origin is not None:
    origin_month = entry.origin.month
    band = origin_band_text(
        entry.origin,
        month_text=month_label(origin_month) if origin_month is not None else "-",
    )
    st.caption(f"{ORIGIN_BAND_ICON} {band}")

if selected_process is None or entry.month is None:
    st.info("조회기간에 확보율을 낼 공정이 없습니다.", icon=":material/info:")
    st.stop()

process = str(selected_process)
process_label = process_labels.label(process)
scenario_tables = active_scenario["tables"]
try:
    summary = build_process_capa_summary(
        securement_rate,
        scenario_tables["RQ_EQP_OWN"],
        scenario_tables["RQ_EQP_LENT"],
        process=process,
        months=months,
        thresholds=thresholds,
    )
except BOOTSTRAP_ERRORS as exc:
    st.error(bootstrap_error_message(exc))
    st.stop()
kpis = process_capa_kpis(summary)


# ------------------------------------------------------------------ HOME 표시 확보율


def home_view_flags() -> tuple[bool, bool, bool]:
    """(확보율 보정, 선행 B/O, EDP 포함) — HOME 에서 왔으면 누른 그때의 조건, 아니면 지금 HOME
    토글."""
    if entry.origin is not None:
        return entry.origin.show_execution, entry.origin.show_advance, entry.origin.include_edp

    def toggle(key: str) -> bool:
        return bool(st.session_state.get(key, HOME_TOGGLE_DEFAULTS[key]))

    return toggle(EXECUTION_TOGGLE_KEY), toggle(ADVANCE_TOGGLE_KEY), toggle(EDP_TOGGLE_KEY)


def home_advance_ratio(include_edp: bool) -> pd.DataFrame | None:
    """HOME 「선행 B/O」 변동률 — HOME 이 지금 쓰는 계획(EDP 를 뺀 화면이면 뺀 계획)의 월별 부하량.

    HOME 과 **같은 캐시 키**로 부른다. 키의 달은 HOME 과 같은 함수
    (`past_data.display_month_range`)로 낸다 — 조회기간 ∩ 계산 원천(`RQ_PKG_PLAN`) 범위를 과거
    구간(Past Data) 달까지 넓힌 범위이고, 과거 구간을 넣을지는 HOME `Past Data 포함` 토글을
    따른다(필요 단축 일정 화면 `_lob_rows` 와 같은 길). 그래서 HOME 을 본 뒤에는 HOME 계산을 한 벌
    더 돌리지 않는다. 월별 부하량은 달마다 값이 정해지므로 축 안 달의 값은 범위와 상관없이 HOME 과
    같다. 범위가 비면 None(선행을 얹지 않는다).
    """
    source = available_month_range(reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN")
    include_past = bool(
        st.session_state.get(PAST_DATA_TOGGLE_KEY, HOME_TOGGLE_DEFAULTS[PAST_DATA_TOGGLE_KEY])
    )
    past_months = (
        [
            int(month)
            for month in load_global_past_data(str(DUCKDB_PATH.resolve())).monthly["생산계획년월"]
        ]
        if include_past
        else []
    )
    display_range = display_month_range(
        (context.selected_start_month, context.selected_end_month), source, past_months
    )
    if display_range.empty:
        return None
    key = build_home_simulation_cache_key(
        reference_version=context.reference_version,
        scenario_token=active_scenario["content_token"],
        start_month=display_range.start,
        end_month=display_range.end,
        display_order=reference_tables["RQ_DISPLAY_ORDER"],
    )
    if include_edp:
        density = get_home_simulation(
            key,
            _tables=scenario_tables,
            _display_order=reference_tables["RQ_DISPLAY_ORDER"],
            _reference_tables=reference_tables,
        )[0]
    else:
        density = get_home_lob_without_edp(
            key, _tables=scenario_tables, _display_order=reference_tables["RQ_DISPLAY_ORDER"]
        )[0]
    advance = load_global_advance_load(str(DUCKDB_PATH.resolve())).rows
    return build_advance_load_ratio(density, advance)


def home_rates_or_none() -> dict[int, float | None] | None:
    """HOME 표시 확보율 줄. 얹을 것이 없거나 원 확보율과 같으면 None(줄 없음)."""
    show_execution, show_advance, include_edp = home_view_flags()
    if not show_execution and not show_advance:
        return None
    try:
        execution_rows = (
            load_global_execution_capacity(str(DUCKDB_PATH.resolve())).rows
            if show_execution
            else None
        )
        advance_ratio = home_advance_ratio(include_edp) if show_advance else None
        rates = home_display_rates(
            securement_rate,
            process=process,
            months=months,
            execution_rows=execution_rows,
            advance_ratio=advance_ratio,
        )
    except BOOTSTRAP_ERRORS:
        return None
    raw = dict(
        zip(
            summary["생산계획년월"].astype("int64").tolist(),
            pd.to_numeric(summary["확보율"], errors="coerce").tolist(),
            strict=True,
        )
    )
    differs = any(
        value is not None
        and not pd.isna(raw.get(month))
        and abs(float(value) - float(raw[month])) > HOME_RATE_TOLERANCE
        for month, value in rates.items()
    )
    return rates if differs else None


home_rates = home_rates_or_none()


# ------------------------------------------------------------------ 설비 일정(참고)


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """내려받기 바이트 — BOM 이 붙은 UTF-8(Excel 이 한글을 깨뜨리지 않게)."""
    return frame.to_csv(index=False).encode("utf-8-sig")


readiness: DynamicReadiness | None = None
dynamic: DynamicView | None = None
dynamic_error = ""
closing_notices: list[str] = []
units_csv: bytes | None = None
try:
    equipment_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    snapshot = load_latest_equipment_snapshot(equipment_path)
    cutoff = load_process_cutoff(equipment_path)
except BOOTSTRAP_ERRORS as exc:
    snapshot = None
    cutoff = pd.DataFrame()
    dynamic_error = bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
else:
    readiness = dynamic_readiness(
        snapshot.equipment if snapshot is not None else None,
        snapshot.baseline if snapshot is not None else None,
        cutoff,
        process=process,
    )

if (
    readiness is not None
    and readiness.ready
    and readiness.cutoff_days is not None
    and snapshot is not None
):
    equipment, downtime, baseline = snapshot.equipment, snapshot.downtime, snapshot.baseline
    # 단축 목표 = HOME Preference 확보기준을 달마다(사용자 결정 2). 계산할 달 밖의 월별 예외는
    # 싣지 않아 키를 가르지 않는다.
    target = target_from_thresholds(thresholds, months)
    shortening_key = required_shortening_cache_key(
        capacity_cache_key,
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        months=tuple(months),
        today=today,
    )
    target_key = required_shortening_target_cache_key(shortening_key, target)
    timeline_key = process_timeline_key_from_shortening(shortening_key, process)
    try:
        plan = get_required_shortening_for_target(
            target_key,
            equipment,
            downtime,
            baseline,
            cutoff,
            _required_equipment=scenario_required_equipment(
                capacity_cache_key,
                scenario_tables=scenario_tables,
                reference_tables=reference_tables,
            ),
        )
        level = plan.at(target)
        timeline = get_process_equipment_timeline(
            timeline_key, equipment, downtime, baseline, cutoff
        )
        undated = get_undated_equipment(equipment)
        usage_excluded = get_usage_excluded_equipment(equipment)
    except BOOTSTRAP_ERRORS as exc:
        dynamic_error = "설비 일정을 계산하지 못했습니다 — " + bootstrap_error_message(
            exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
        )
    else:
        in_process = level.process_months["공정"].astype("string").str.strip().eq(process)
        process_months = level.process_months.loc[in_process.fillna(False).to_numpy()]
        unit_mask = level.units["공정"].astype("string").str.strip().eq(process)
        process_units = level.units.loc[unit_mask.fillna(False).to_numpy()]
        counts = undated_counts(undated, processes=[process])
        undated_total = round(sum(counts.values()), 6)
        undated_line = (
            f"일정 미정 {format_unit_count(undated_total)}대 — 날짜가 들어올 때까지 세지 않습니다"
            if undated_total > 0
            else ""
        )
        dynamic = DynamicView(
            canvas=DynamicCanvasInput(
                cutoff_days=readiness.cutoff_days,
                target=target,
                today=today,
                process_months=process_months.reset_index(drop=True),
                bridge=timeline.bridge,
                unit_events=unit_events(timeline, level.units),
                arrows=timeline.arrows,
                exits=timeline.exits,
                has_units=readiness.has_units,
                steady_units=timeline.steady_units,
                undated_notice=undated_line,
            ),
            units=process_units.reset_index(drop=True),
            memo_key=(target_key, timeline_key, undated_line),
        )
        # 정리 줄 — 0 인 알림은 적지 않는다.
        excluded_count = usage_excluded_count(usage_excluded, processes=[process])
        parts: list[str] = []
        if excluded_count > 0:
            parts.append(f"사용기준 제외 {format_unit_count(excluded_count)}대")
        if undated_total > 0:
            parts.append(f"일정 미정 {format_unit_count(undated_total)}대")
        today_month = production_position(today, readiness.cutoff_days, months).month
        if today_month in months:
            parts.append(
                f"오늘이 든 {with_topic_particle(month_label(today_month))} 남은 날만 셉니다"
            )
        parts.append("단축 결과는 공식 확보율을 바꾸지 않습니다(설비 일정 기준 가용만 바뀜)")
        closing_notices.append(" · ".join(parts))
        export = unit_export_frame(plan, (target,), (process,))
        units_csv = get_export_csv(
            csv_export_key("process_detail_units", export, (), "utf-8-sig"),
            partial(csv_bytes, export),
        )

if readiness is None:
    dynamic_badge = ":blue-badge[설비 일정 없음: 설비 DB 오류]"
elif dynamic is not None and readiness.cutoff_days is not None:
    dynamic_badge = f":gray-badge[{readiness.badge} · Cut-off {readiness.cutoff_days}일]"
elif dynamic_error:
    dynamic_badge = ":blue-badge[설비 일정 없음: 계산 오류]"
else:
    dynamic_badge = f":blue-badge[{readiness.badge}]"
with header_marks.container(horizontal=True, vertical_alignment="center", gap="small"):
    st.markdown(f"**{process_label}** {OFFICIAL_BADGE} {dynamic_badge}", width="content")
    st.space("stretch")
    render_page_link(HOME.path, label="HOME", icon=":material/arrow_back:")

render_process_kpis(
    kpis,
    thresholds=thresholds,
    dynamic=dynamic,
    absent_reason=(
        "설비 DB 오류"
        if readiness is None
        else (readiness.reason if not readiness.ready else "설비 일정 계산 오류")
    ),
)

render_process_detail_view(
    ProcessDetailView(
        process=process,
        process_label=process_label,
        months=tuple(months),
        summary=summary,
        thresholds=thresholds,
        scenario_key=capacity_cache_key,
        display_order_key=order_key,
        scenario_tables=scenario_tables,
        reference_tables=reference_tables,
        display_order=context.display_order,
        products=tuple(str(name) for name in chosen_products),
        splits=tuple(
            name for name in PRODUCT_DEMAND_SPLITS if name != "소요기준" or demand_bases > 1
        ),
        home_rates=home_rates,
        dynamic=dynamic,
        readiness=readiness,
        dynamic_error=dynamic_error,
        initial_month=entry.scroll_month,
    )
)

if dynamic is not None:
    render_closing_row(
        process=process,
        notices=closing_notices,
        csv_bytes=units_csv,
        csv_file_name=f"process_capa_detail_units_{months[0]}_{months[-1]}.csv",
    )
