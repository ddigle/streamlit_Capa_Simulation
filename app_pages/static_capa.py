# Purpose: 확보·경고 기준별 부족 공정과 추가 필요대수를 Static Capa 현황판에 표시한다.

"""Static Capa 현황 요약 — 판정 기준은 사이드바 조건 카드, 설명은 Guide(2026-09-29 사용자 결정).

본문에는 두 결과 상자(경고 기준 미달·확보 기준 추가 확보)만 남는다. 이 화면의 목적·담당 부서
흐름과 추가 필요대수 계산식은 `guides/static_capa.md` 가 말한다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.status_metric import (
    metric_row,
    render_status_metric,
    shortage_tone,
)
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    load_page_context,
    resolve_effective_months,
    scenario_capacity_and_demand,
)
from capa_simulation.scenario_preset_state import (
    SECURE_THRESHOLD_KEY,
    WARNING_THRESHOLD_KEY,
    seed_threshold_defaults,
)
from capa_simulation.scenario_state import (
    scenario_month_table,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.securement_rate import build_securement_shortfall_tables
from capa_simulation.services.simulation_cache import (
    get_securement_rate,
    scenario_cache_key,
)
from capa_simulation.sidebar_status import condition_card


def _display_shortfalls(data: pd.DataFrame, *, warning_section: bool) -> pd.DataFrame:
    result = data.copy()
    result.insert(
        0,
        "년월",
        result["생산계획년월"].map(lambda value: month_label(int(value))),
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
    secure_threshold: float,
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
            # 표는 확보율 오름차순이지만 62.3% 와 71.8% 의 **거리**는 숫자만으로 안 잡힌다.
            # 칸 안 막대 하나면 위에서 몇 줄까지가 진짜 급한 구간인지 훑는 순간 보인다.
            # 길이의 기준은 확보 기준이다 — 기준을 바꾸면 막대도 함께 움직인다.
            "확보율": st.column_config.ProgressColumn(
                format="percent",
                width="small",
                min_value=0.0,
                max_value=secure_threshold,
                # 색을 비워 두면 Streamlit 이 primaryColor(=`ACCENT`)로 그린다. `ACCENT`
                # 는 상호작용·현재 위치 전용이라, 판정 색을 읽는 표에서 그 색이 나오면
                # 「여기가 좋다」로 뒤집혀 읽힌다. 두 구획의 판정색을 그대로 쓴다.
                color=(tokens.STATUS_SHORTAGE if warning_section else tokens.STATUS_WARNING),
            ),
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

render_page_header("Static Capa")
render_page_guide("static_capa", title="Static Capa")

seed_threshold_defaults()

# 판정 기준은 이 화면이 읽는 조건이라 사이드바 조건 카드다. HOME 의 B/N 집계 공정 상자와 **같은
# 세션 키**를 쓴다 — 한쪽에서 바꾸면 다른 쪽도 같은 기준으로 판정한다. 두 칸을 한 줄에 반씩
# 놓고 칸 위 글자는 접는다(B/N 상자와 같은 모양). 어느 칸이 무엇인지는 왼쪽이 확보·오른쪽이
# 경고라는 화면 전체의 차례와 `help` 가 말한다.
with condition_card("판정 기준", name="static_capa", icon=":material/rule:"):
    with st.form("static_capa_shortfall_threshold_form", border=False):
        secure_column, warning_column = st.columns(2, gap="small")
        with secure_column:
            secure_threshold_percent = st.number_input(
                "확보 기준 (%)",
                label_visibility="collapsed",
                min_value=0.0,
                step=0.1,
                key=SECURE_THRESHOLD_KEY,
                persist_state="session",
                help="확보 기준 (%)",
            )
        with warning_column:
            warning_threshold_percent = st.number_input(
                "경고 기준 (%)",
                label_visibility="collapsed",
                min_value=0.0,
                step=0.1,
                key=WARNING_THRESHOLD_KEY,
                persist_state="session",
                help="경고 기준 (%)",
            )
        st.form_submit_button("판정 기준 적용", type="primary", width="stretch")

if warning_threshold_percent > secure_threshold_percent:
    st.error("경고 기준은 확보 기준보다 클 수 없습니다.")
    st.stop()

try:
    context = load_page_context()
    reference_version = context.reference_version
    reference_tables = context.reference_tables
    active_scenario = context.active_scenario
    # 유효 기간은 활성 리비전의 RQ_REQB 전체에서 잡는다(calculation_result 와 같다). 먼저 월로
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
    unit_capacity, required_equipment = scenario_capacity_and_demand(
        capacity_cache_key,
        scenario_tables=active_scenario["tables"],
        reference_tables=reference_tables,
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
    st.error(bootstrap_error_message(exc))
else:
    with st.container(border=True):
        st.markdown("#### :material/priority_high: 경고 기준 미달 :red-badge[집중 관리]")
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
                secure_threshold=float(secure_threshold_percent) / 100.0,
            )

    with st.container(border=True):
        st.markdown("#### :material/trending_up: 확보 기준 추가 확보 :orange-badge[계획 관리]")
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
                secure_threshold=float(secure_threshold_percent) / 100.0,
            )
