# Purpose: 공정 하나의 Capa 근거를 보는 「공정 Capa 상세」 화면의 진입·공정 선택·출처 띠를 그린다.

"""공정 Capa 상세 — 공정 하나의 산출 근거 → 부족한 달 → 그 달을 메우는 설비 일정을 잇는 화면.

이 파일이 지금 갖는 것은 **진입과 선택 흐름**이다.

1. 공통 진입(`page_bootstrap`) — 활성 리비전·표시순서·조회기간, 유효 기간은 산출 결과처럼
   `RQ_REQB` 원천에서 정한다. 확보율은 키 전용 캐시(`get_scenario_securement_rate`)로 꺼낸다.
2. 공정·달 정하기(`process_detail_state.resolve_process_and_month`) — HOME 전달 칸 → 주소 인자 →
   세션 → 기본값(기간 최저 확보율 공정, 그 공정의 첫 확보기준 미달 달) 차례다. **공정 선택 상자보다
   먼저** 정해 세션에 적는다.
3. 사이드바 `공정 상세 조건` 카드의 공정 선택(원본 공정명, 표시만 표시명).
4. HOME 에서 왔으면 출처 띠 — HOME 확보율에는 실행 Capa·선행 B/O 가 얹혀 있어 이 화면의 원 확보율과
   다를 수 있으므로 그 차이를 먼저 밝힌다.

월별 요약 표·산출 근거 패널·설비 일정 구획은 그 아래 자리에 선다.
"""

import pandas as pd
import streamlit as st

from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
    resolve_effective_months,
    stop_calculation_on_error,
)
from capa_simulation.persistence.cache import load_global_securement_threshold
from capa_simulation.process_detail_state import (
    PROCESS_DETAIL_PROCESS_KEY,
    first_shortfall_month,
    lowest_rate_process,
    origin_band_text,
    resolve_process_and_month,
)
from capa_simulation.scenario_state import scenario_month_table
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_SECUREMENT
from capa_simulation.services.korean_particle import with_object_particle, with_topic_particle
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.process_picker import build_process_picker_summary
from capa_simulation.services.simulation_cache import (
    check_scenario_capacity,
    display_order_digest,
    get_display_ordered_values,
    get_scenario_securement_rate,
    scenario_cache_key,
)
from capa_simulation.settings import DUCKDB_PATH
from capa_simulation.sidebar_status import condition_card

# 사이드바 조건 카드. 이 화면이 실제로 읽는 고유 조건(공정 하나, 펼친 제품 행의 거르기)을 모은다.
CARD_LABEL = "공정 상세 조건"
CARD_NAME = "process_capa_detail"
CARD_ICON = ":material/troubleshoot:"
# 화면 조립이 끝나기 전, 요약 표·근거 패널이 설 자리를 알리는 한 줄.
ASSEMBLY_NOTICE = "화면 조립 중 — 월별 요약 표·산출 근거·설비 일정이 이 자리에 섭니다."

render_page_header("공정 Capa 상세")
render_page_guide("process_capa_detail", title="공정 Capa 상세")
# 공정 표시명은 화면 라벨이다. 선택값·세션값·주소 인자는 원본 공정명이다.
process_labels = get_process_labels()

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
    # 공정 차례는 산출 결과 확보율 탭·HOME 공정 필터와 같은 공용 표시순서 범위다.
    process_options = get_display_ordered_values(
        pd.DataFrame({"공정": sorted(process_column.dropna().unique().tolist())}),
        display_order_digest(reference_tables["RQ_DISPLAY_ORDER"]),
        PAGE_CALCULATION,
        TAB_SECUREMENT,
        _display_order=context.display_order,
    )
    picker_items = build_process_picker_summary(
        securement_rate,
        process_options,
        start_month=effective_start,
        end_month=effective_end,
        thresholds=thresholds,
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


def default_month_for(process: str | None) -> int | None:
    """그 공정의 첫 확보기준 미달 달. 없으면 None — 첫 달을 연다."""
    if process is None:
        return None
    rows = securement_rate.loc[process_column.eq(process).fillna(False)]
    return first_shortfall_month(
        zip(rows["생산계획년월"].tolist(), rows["확보율"].tolist(), strict=True), thresholds
    )


# 공정 선택 상자보다 **먼저** 공정·달을 정해 세션에 적는다. HOME 이 넘긴 공정은 위젯 키가 아니라
# 전달 칸으로 오므로 여기서 위젯 키에 옮겨 적어야 첫 회차에도 상자가 그 공정을 보인다.
entry = resolve_process_and_month(
    process_options,
    months,
    default_process=lowest_rate_process(picker_items),
    default_month=default_month_for,
)

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
    st.info(
        origin_band_text(
            entry.origin,
            month_text=month_label(origin_month) if origin_month is not None else "-",
        ),
        icon=":material/call_received:",
    )

if selected_process is None or entry.month is None:
    st.info("조회기간에 확보율을 낼 공정이 없습니다.", icon=":material/info:")
    st.stop()

st.markdown(f"**{process_labels.label(selected_process)}** · {month_label(entry.month)}")
st.caption(ASSEMBLY_NOTICE)
