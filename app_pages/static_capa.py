# Purpose: 확보·경고 기준별 부족 공정과 추가 필요대수를 Static Capa 현황판에 표시한다.

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.roadmap_panel import render_roadmap_panel
from capa_simulation.components.status_metric import (
    metric_row,
    render_status_metric,
    shortage_tone,
)
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    load_page_context,
    resolve_effective_months,
)
from capa_simulation.scenario_preset_state import (
    DEFAULT_SECURE_THRESHOLD_PERCENT,
    DEFAULT_WARNING_THRESHOLD_PERCENT,
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
)
from capa_simulation.scenario_state import (
    scenario_month_table,
)
from capa_simulation.services.securement_rate import build_securement_shortfall_tables
from capa_simulation.services.simulation_cache import (
    get_scenario_capacity_and_demand,
    get_securement_rate,
    scenario_cache_key,
)


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


def _render_shortfall_table(
    data: pd.DataFrame,
    *,
    warning_section: bool,
    key: str,
    labels: ProcessLabels,
) -> None:
    """화면용 프레임과 CSV 프레임을 분리한다.

    표시명은 `st.dataframe` 에 넘기는 복사본에만 입힌다. 이 표의 CSV 는 투자 검토와
    A/Item 배분에 그대로 옮겨 쓰므로 `공정` 은 원본이어야 한다.
    """
    exported = _display_shortfalls(data, warning_section=warning_section)
    displayed = exported.copy()
    displayed["공정"] = labels.series(displayed["공정"])
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
    # 투자 검토와 A/Item 배분에 그대로 쓰는 표다. 화면에서 옮겨 적지 않도록 내보낸다.
    render_csv_download(
        data=exported.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{key}.csv",
        key=f"{key}_download",
    )


process_labels = get_process_labels()

render_page_header(
    "Static Capa",
    description="생산계획과 투자 기준정보를 기반으로 미래 구간의 Capa 과부족을 판단합니다.",
)

render_roadmap_panel(
    purpose=(
        "Capa 기준정보(투자 기준)로 부족대수를 산출한 뒤 Total 대수와 가용 일정을 분리해 "
        "투자 또는 실행 Action Item으로 연결합니다."
    ),
    owners=(
        (
            "GO팀 · 투자 판단",
            "Total 설비가 부족한 공정은 산출 부족대수를 투자 검토 기준으로 활용",
        ),
        (
            "기술팀 · 실행 개선",
            "투자는 완료됐지만 가용 일정이 부족하면 Setup 단축·생산성 향상 A/Item으로 전환",
        ),
    ),
    roadmap="부족대수 모니터링 → Total/가용 일정 분리 → 부서별 A/Item 및 이력 관리",
)

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
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    active_scenario = context.active_scenario
    # 유효 기간은 활성 리비전의 RQ_REQB 전체에서 잡는다(process_securement 와 같다). 먼저 월로
    # 거른 표를 넘기면 같은 필터를 두 번 걸고, 선택 범위 밖일 때 이 페이지의 안내문 대신
    # month_filter 의 일반 오류가 먼저 났다.
    effective_start, effective_end = resolve_effective_months(
        context,
        active_scenario["tables"]["RQ_REQB"],
        "RQ_REQB",
        empty_message="선택 범위에 소요대수 산출 기준이 없습니다.",
    )

    capacity_cache_key = scenario_cache_key(
        reference_version, active_scenario, effective_start, effective_end
    )
    unit_capacity, required_equipment = get_scenario_capacity_and_demand(
        capacity_cache_key,
        _scenario_tables=active_scenario["tables"],
        _reference_tables=reference_tables,
    )
    securement_rate = get_securement_rate(
        capacity_cache_key,
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
except BOOTSTRAP_ERRORS as exc:
    st.error(str(exc))
else:
    with st.container(border=True):
        st.markdown("#### :material/priority_high: 경고 기준 미달")
        st.markdown(":red-badge[집중 관리] 물리적 Capa가 계획을 받치지 못하는 공정·월입니다.")
        with metric_row(key="static_capa_warning_metrics"):
            render_status_metric(
                "미달 공정·월",
                f"{len(warning_shortfalls):,}건",
                key="static_capa_warning_rows",
                tone="critical" if len(warning_shortfalls) else "neutral",
            )
            render_status_metric(
                "미달 공정",
                f"{warning_shortfalls['공정'].nunique():,}개",
                key="static_capa_warning_processes",
                tone=shortage_tone(int(warning_shortfalls["공정"].nunique())),
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
                labels=process_labels,
            )
            st.caption(
                "`경고까지 필요 + 확보까지 추가 = 총 추가 필요`입니다. 같은 설비가 여러 달에 "
                "재사용될 수 있으므로 기간 전체 대수를 단순 합산하지 않습니다."
            )

    with st.container(border=True):
        st.markdown("#### :material/trending_up: 확보 기준 추가 확보")
        st.markdown(
            ":orange-badge[계획 관리] 경고 기준은 충족했지만 확보 기준까지 여유 설비가 필요한 "
            "공정·월입니다."
        )
        with metric_row(key="static_capa_secure_metrics"):
            render_status_metric(
                "추가 확보 공정·월",
                f"{len(secure_shortfalls):,}건",
                key="static_capa_secure_rows",
                tone=shortage_tone(len(secure_shortfalls)),
            )
            render_status_metric(
                "추가 확보 공정",
                f"{secure_shortfalls['공정'].nunique():,}개",
                key="static_capa_secure_processes",
                tone=shortage_tone(int(secure_shortfalls["공정"].nunique())),
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
                labels=process_labels,
            )

    with st.expander("추가 필요대수 계산 기준", icon=":material/function:"):
        st.markdown(
            "- **경고 기준 필요대수** = `ceil(max(소요대수 × 경고 기준 − 가용대수, 0))`\n"
            "- **확보목표 총 필요대수** = `ceil(max(소요대수 × 확보 기준 − 가용대수, 0))`\n"
            "- **확보 기준 추가대수** = `확보목표 총 필요대수 − 경고 기준 필요대수`"
        )
