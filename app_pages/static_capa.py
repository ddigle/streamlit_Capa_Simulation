# Purpose: 확보·경고 기준별 부족 공정과 추가 필요대수를 Static Capa 현황판에 표시한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.scenario_preset_state import (
    MONTH_RANGE_KEY,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
)
from capa_simulation.scenario_state import ensure_active_scenario, scenario_month_table
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.securement_rate import build_securement_shortfall_tables
from capa_simulation.services.simulation_cache import (
    get_required_equipment,
    get_securement_rate,
    get_unit_capacity,
)
from capa_simulation.settings import (
    MONTH_SELECTION_END,
    MONTH_SELECTION_START,
    format_month,
)
from capa_simulation.sidebar_status import show_applied_month_range

DEFAULT_SECURE_THRESHOLD_PERCENT = 109.5
DEFAULT_WARNING_THRESHOLD_PERCENT = 99.5


def _selected_month_range() -> tuple[int, int]:
    default = (format_month(MONTH_SELECTION_START), format_month(MONTH_SELECTION_END))
    value = st.session_state.get(MONTH_RANGE_KEY, default)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        value = default
    return int(str(value[0]).replace("-", "")), int(str(value[1]).replace("-", ""))


def _display_shortfalls(data: pd.DataFrame, *, warning_section: bool) -> pd.DataFrame:
    result = data.copy()
    result.insert(
        0,
        "년월",
        result["생산계획년월"].map(
            lambda value: f"{int(value) // 100 % 100:02d}.{int(value) % 100:02d}"
        ),
    )
    columns = ["년월", "공정", "확보율", "가용대수", "소요대수"]
    if warning_section:
        columns.extend(
            [
                "경고기준 필요대수",
                "확보기준 추가대수",
                "확보목표 총 필요대수",
            ]
        )
    else:
        columns.append("확보기준 추가대수")
    return result[columns]


def _monthly_peak(data: pd.DataFrame, value_column: str) -> int:
    if data.empty:
        return 0
    monthly_sum = data.groupby("생산계획년월", sort=False)[value_column].sum()
    return int(monthly_sum.max())


def _render_shortfall_table(data: pd.DataFrame, *, warning_section: bool, key: str) -> None:
    displayed = _display_shortfalls(data, warning_section=warning_section)
    st.dataframe(
        displayed,
        hide_index=True,
        width="stretch",
        height=min(560, max(150, (len(displayed) + 1) * 36 + 4)),
        key=key,
        column_config={
            "년월": st.column_config.TextColumn(width="small"),
            "공정": st.column_config.TextColumn(width="large"),
            "확보율": st.column_config.NumberColumn(format="percent", width="small"),
            "가용대수": st.column_config.NumberColumn(format="%.1f대", width="small"),
            "소요대수": st.column_config.NumberColumn(format="%.1f대", width="small"),
            "경고기준 필요대수": st.column_config.NumberColumn(
                "경고까지 필요",
                format="%d대",
                width="small",
            ),
            "확보기준 추가대수": st.column_config.NumberColumn(
                "확보까지 추가",
                format="%d대",
                width="small",
            ),
            "확보목표 총 필요대수": st.column_config.NumberColumn(
                "총 추가 필요",
                format="%d대",
                width="small",
            ),
        },
    )


st.title("Static Capa")
st.caption("생산계획과 투자 기준정보를 기반으로 미래 구간의 Capa 과부족을 판단합니다.")

with st.container(border=True):
    st.markdown("#### :material/route: 업무 활용 목적 및 로드맵")
    st.caption(
        "Capa 기준정보(투자 기준)로 부족대수를 산출한 뒤 Total 대수와 가용 일정을 분리해 "
        "투자 또는 실행 Action Item으로 연결합니다."
    )
    with st.container(horizontal=True, gap="small"):
        with st.container(border=True):
            st.markdown("**GO팀 · 투자 판단**")
            st.write("Total 설비가 부족한 공정은 산출 부족대수를 투자 검토 기준으로 활용")
        with st.container(border=True):
            st.markdown("**기술팀 · 실행 개선**")
            st.write(
                "투자는 완료됐지만 가용 일정이 부족하면 Setup 단축·생산성 향상 A/Item으로 전환"
            )
    st.caption("로드맵 · 부족대수 모니터링 → Total/가용 일정 분리 → 부서별 A/Item 및 이력 관리")

st.subheader("확보율 기준 설비 부족 현황", divider="gray")
st.caption("월·공정별 가용대수 ÷ 소요대수를 기준으로 최소 추가 설비대수를 정수 올림합니다.")

if SECURE_THRESHOLD_KEY not in st.session_state:
    st.session_state[SECURE_THRESHOLD_KEY] = DEFAULT_SECURE_THRESHOLD_PERCENT
if WARNING_THRESHOLD_KEY not in st.session_state:
    st.session_state[WARNING_THRESHOLD_KEY] = DEFAULT_WARNING_THRESHOLD_PERCENT

with st.container(border=True):
    st.markdown("#### :material/tune: 판정 기준")
    with st.form("static_capa_shortfall_threshold_form", border=False):
        with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
            secure_threshold_percent = st.number_input(
                "확보 기준 (%)",
                min_value=0.0,
                step=0.1,
                key=SECURE_THRESHOLD_KEY,
                persist_state="session",
                width=170,
            )
            warning_threshold_percent = st.number_input(
                "경고 기준 (%)",
                min_value=0.0,
                step=0.1,
                key=WARNING_THRESHOLD_KEY,
                persist_state="session",
                width=170,
            )
            st.form_submit_button("판정 기준 적용", type="primary", width="content")
    st.caption(
        "경고 기준 미달은 물리적 Capa 부족으로 우선 관리하고, 경고 이상·확보 기준 미달은 "
        "추가 확보 계획 대상으로 구분합니다."
    )

if warning_threshold_percent > secure_threshold_percent:
    st.error("경고 기준은 확보 기준보다 클 수 없습니다.")
    st.stop()

try:
    reference_version = get_effective_reference_version()
    reference_tables = get_effective_reference_tables()
    active_scenario = ensure_active_scenario(reference_tables, reference_version)
    selected_start, selected_end = _selected_month_range()
    active_reqb = scenario_month_table(
        active_scenario,
        "RQ_REQB",
        selected_start,
        selected_end,
    )
    source_start, source_end = available_month_range(active_reqb, "RQ_REQB")
    effective_start = max(selected_start, source_start)
    effective_end = min(selected_end, source_end)
    if effective_start > effective_end:
        raise ValueError("선택 범위에 소요대수 산출 기준이 없습니다.")
    show_applied_month_range(effective_start, effective_end)

    unit_capacity = get_unit_capacity(
        upeh=scenario_month_table(active_scenario, "RQ_UPEH", effective_start, effective_end),
        run_rate=scenario_month_table(
            active_scenario,
            "RQ_RUN_RATE",
            effective_start,
            effective_end,
        ),
        vital=scenario_month_table(active_scenario, "RQ_VITAL", effective_start, effective_end),
        module=reference_tables["RQ_MODULE"],
        run_day=scenario_month_table(
            active_scenario,
            "RQ_RUN_DAY",
            effective_start,
            effective_end,
        ),
        lot_ratio=scenario_month_table(
            active_scenario,
            "RQ_LOT_RATIO",
            effective_start,
            effective_end,
        ),
        wf_ratio=scenario_month_table(
            active_scenario,
            "RQ_WF_RATIO",
            effective_start,
            effective_end,
        ),
    )
    required_equipment = get_required_equipment(
        reqb=scenario_month_table(
            active_scenario,
            "RQ_REQB",
            effective_start,
            effective_end,
        ),
        plan=scenario_month_table(
            active_scenario,
            "RQ_PKG_PLAN",
            effective_start,
            effective_end,
        ),
        yield_data=scenario_month_table(
            active_scenario,
            "RQ_YLD",
            effective_start,
            effective_end,
        ),
        chip_qty=reference_tables["RQ_CHIP_QTY"],
        unit_capacity=unit_capacity,
    )
    securement_rate = get_securement_rate(
        scenario_month_table(
            active_scenario,
            "RQ_EQP_AVBL",
            effective_start,
            effective_end,
        ),
        required_equipment,
    )
    warning_shortfalls, secure_shortfalls = build_securement_shortfall_tables(
        securement_rate,
        warning_threshold=float(warning_threshold_percent) / 100.0,
        secure_threshold=float(secure_threshold_percent) / 100.0,
    )
except (KeyError, OSError, ValueError) as exc:
    st.error(str(exc))
else:
    with st.container(border=True):
        st.markdown("### :material/priority_high: 경고 기준 미달")
        st.markdown(":red-badge[집중 관리] 물리적 Capa가 계획을 받치지 못하는 공정·월입니다.")
        with st.container(horizontal=True, gap="small"):
            st.metric("미달 공정·월", f"{len(warning_shortfalls):,}건", border=True)
            st.metric(
                "미달 공정",
                f"{warning_shortfalls['공정'].nunique():,}개",
                border=True,
            )
            st.metric(
                "월 최대 경고 필요",
                f"{_monthly_peak(warning_shortfalls, '경고기준 필요대수'):,}대",
                border=True,
            )
            st.metric(
                "월 최대 확보 총 필요",
                f"{_monthly_peak(warning_shortfalls, '확보목표 총 필요대수'):,}대",
                border=True,
            )
        if warning_shortfalls.empty:
            st.success("선택 기간에 경고 기준 미달 공정이 없습니다.")
        else:
            _render_shortfall_table(
                warning_shortfalls,
                warning_section=True,
                key="static_capa_warning_shortfalls",
            )
            st.caption(
                "`경고까지 필요 + 확보까지 추가 = 총 추가 필요`입니다. 같은 설비가 여러 달에 "
                "재사용될 수 있으므로 기간 전체 대수를 단순 합산하지 않습니다."
            )

    with st.container(border=True):
        st.markdown("### :material/trending_up: 확보 기준 추가 확보")
        st.markdown(
            ":orange-badge[계획 관리] 경고 기준은 충족했지만 확보 기준까지 여유 설비가 필요한 "
            "공정·월입니다."
        )
        with st.container(horizontal=True, gap="small"):
            st.metric("추가 확보 공정·월", f"{len(secure_shortfalls):,}건", border=True)
            st.metric(
                "추가 확보 공정",
                f"{secure_shortfalls['공정'].nunique():,}개",
                border=True,
            )
            st.metric(
                "월 최대 추가 필요",
                f"{_monthly_peak(secure_shortfalls, '확보기준 추가대수'):,}대",
                border=True,
            )
        if secure_shortfalls.empty:
            st.success("선택 기간에 경고 이상·확보 기준 미달 공정이 없습니다.")
        else:
            _render_shortfall_table(
                secure_shortfalls,
                warning_section=False,
                key="static_capa_secure_shortfalls",
            )

    with st.expander("추가 필요대수 계산 기준", icon=":material/function:"):
        st.markdown(
            "- **경고 기준 필요대수** = `ceil(max(소요대수 × 경고 기준 − 가용대수, 0))`\n"
            "- **확보목표 총 필요대수** = `ceil(max(소요대수 × 확보 기준 − 가용대수, 0))`\n"
            "- **확보 기준 추가대수** = `확보목표 총 필요대수 − 경고 기준 필요대수`"
        )
