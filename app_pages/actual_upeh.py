# Purpose: Dynamic Capa의 공정·제품별 UPEH 실적 Gap과 개선 우선순위 관리 화면 초안을 렌더링한다.

import pandas as pd
import streamlit as st

from capa_simulation.components.page_header import render_page_header

PROCESS_PRIORITY_COLUMNS = {
    "우선순위": pd.Series(dtype="Int64"),
    "공정": pd.Series(dtype="string"),
    "소요기준": pd.Series(dtype="string"),
    "실적 UPEH": pd.Series(dtype="Float64"),
    "Capa 기준 UPEH": pd.Series(dtype="Float64"),
    "Gap": pd.Series(dtype="Float64"),
    "기준 미달 개월": pd.Series(dtype="Int64"),
    "우선순위 점수": pd.Series(dtype="Float64"),
    "상태": pd.Series(dtype="string"),
}
PRODUCT_PRIORITY_COLUMNS = {
    "우선순위": pd.Series(dtype="Int64"),
    "제품": pd.Series(dtype="string"),
    "Stack": pd.Series(dtype="string"),
    "WF 속성": pd.Series(dtype="string"),
    "실적 UPEH": pd.Series(dtype="Float64"),
    "Capa 기준 UPEH": pd.Series(dtype="Float64"),
    "Gap": pd.Series(dtype="Float64"),
    "생산 비중": pd.Series(dtype="Float64"),
    "상태": pd.Series(dtype="string"),
}
ACTION_COLUMNS = {
    "공정": pd.Series(dtype="string"),
    "제품": pd.Series(dtype="string"),
    "개선 과제": pd.Series(dtype="string"),
    "담당": pd.Series(dtype="string"),
    "목표일": pd.Series(dtype="datetime64[ns]"),
    "상태": pd.Series(dtype="string"),
    "최근 업데이트": pd.Series(dtype="datetime64[ns]"),
}


render_page_header(
    "UPEH 실적 (구현중)",
    description=(
        "생산이력 DB의 공정·제품별 UPEH 실적을 Capa 기준정보와 비교하고, "
        "개선 필요항목과 조치 진행상태를 관리하는 화면입니다."
    ),
)
st.markdown(":gray-badge[화면 초안] :blue-badge[데이터 미연결]")
st.info(
    "현재는 화면 구조만 구성되어 있습니다. 생산이력 DB와 Capa UPEH 기준정보를 "
    "연결하면 조회 조건, 지표, 순위와 개선과제가 활성화됩니다.",
    icon=":material/database:",
)

overview_tab, priority_tab, action_tab = st.tabs(["분석 현황", "개선 우선순위", "개선과제 관리"])

with overview_tab:
    with st.container(border=True):
        st.markdown("#### :material/filter_alt: 조회 조건")
        st.caption("분석 기간과 공정·제품·WF 속성 범위를 선택하는 영역입니다.")
        with st.container(horizontal=True, gap="small"):
            st.selectbox(
                "분석 기간",
                ["데이터 연결 후 선택"],
                disabled=True,
                key="actual_upeh_period",
                width=220,
            )
            st.selectbox(
                "공정",
                ["전체 공정"],
                disabled=True,
                key="actual_upeh_process",
                width=220,
            )
            st.selectbox(
                "제품",
                ["전체 제품"],
                disabled=True,
                key="actual_upeh_product",
                width=220,
            )
            st.selectbox(
                "WF 속성",
                ["전체"],
                disabled=True,
                key="actual_upeh_wafer_type",
                width=180,
            )

    st.markdown("#### 기준 대비 요약")
    with st.container(horizontal=True):
        st.metric("실적 UPEH", "—", border=True)
        st.metric("Capa 기준 UPEH", "—", border=True)
        st.metric("UPEH Gap", "—", border=True)
        st.metric("기준 미달 공정·제품", "—", border=True)

    trend_column, distribution_column = st.columns(2)
    with trend_column.container(border=True, height=300):
        st.markdown("#### :material/show_chart: 월별 UPEH Gap 추이")
        st.caption("실적 UPEH와 Capa 기준 UPEH를 월별 추이로 비교합니다.")
        st.info("데이터 연결 후 추이 차트가 표시됩니다.")
    with distribution_column.container(border=True, height=300):
        st.markdown("#### :material/bar_chart: 공정별 UPEH Gap")
        st.caption("공정별 기준 미달폭과 생산 영향도를 함께 비교합니다.")
        st.info("데이터 연결 후 공정 비교 차트가 표시됩니다.")

    with st.container(border=True):
        st.markdown("#### :material/rule: 비교 기준 초안")
        st.markdown(
            "- **비교 단위:** 생산계획년월 · 공정 · 양산구분 · 제품 · Stack · WF 속성\n"
            "- **Gap:** 실적 UPEH − Capa 기준 UPEH\n"
            "- **미달 판정:** Gap이 0보다 작은 항목\n"
            "- **우선순위:** 기준 미달폭, 생산 영향도, 연속 미달기간과 표본 신뢰도를 종합"
        )

with priority_tab:
    st.subheader("공정 개선 우선순위")
    st.caption(
        "기준 미달폭이 크고 생산 영향이 큰 공정을 먼저 보여줍니다. "
        "공정별 소요기준과 Area 특성은 실제 데이터 연결 시 함께 반영합니다."
    )
    st.dataframe(
        pd.DataFrame(PROCESS_PRIORITY_COLUMNS),
        hide_index=True,
        width="stretch",
        column_config={
            "우선순위": st.column_config.NumberColumn(format="%d"),
            "실적 UPEH": st.column_config.NumberColumn(format="%.2f"),
            "Capa 기준 UPEH": st.column_config.NumberColumn(format="%.2f"),
            "Gap": st.column_config.NumberColumn(format="%.2f"),
            "기준 미달 개월": st.column_config.NumberColumn(format="%d개월"),
            "우선순위 점수": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    with st.container(border=True):
        st.markdown("#### 공정 내 제품 상세")
        st.caption("선택한 공정 안에서 UPEH가 낮고 영향도가 큰 제품을 순위로 확인합니다.")
        st.selectbox(
            "공정 선택",
            ["데이터 연결 후 선택"],
            disabled=True,
            key="actual_upeh_priority_process",
            width=260,
        )
        st.dataframe(
            pd.DataFrame(PRODUCT_PRIORITY_COLUMNS),
            hide_index=True,
            width="stretch",
            column_config={
                "우선순위": st.column_config.NumberColumn(format="%d"),
                "실적 UPEH": st.column_config.NumberColumn(format="%.2f"),
                "Capa 기준 UPEH": st.column_config.NumberColumn(format="%.2f"),
                "Gap": st.column_config.NumberColumn(format="%.2f"),
                "생산 비중": st.column_config.NumberColumn(format="percent"),
            },
        )

    with st.expander("우선순위 산정 항목", icon=":material/tune:"):
        st.markdown(
            "1. Capa 기준 대비 UPEH 미달폭\n"
            "2. 해당 공정·제품의 생산량 또는 설비시간 영향도\n"
            "3. 기준 미달의 연속성과 최근 추세\n"
            "4. 생산시간·투입량·완료량 표본 수와 데이터 누락률"
        )

with action_tab:
    with st.container(border=True):
        st.markdown("#### :material/task_alt: 개선과제 운영 흐름")
        st.markdown(
            "**우선순위 확인** → **Loss 원인 분류** → **담당·목표 설정** → "
            "**개선 후 UPEH 재확인** → **완료 판정**"
        )
        st.caption(
            "향후 권한이 있는 사용자만 과제를 등록·수정하고, 변경 이력은 별도 저장소에 보존합니다."
        )

    with st.container(horizontal=True):
        st.metric("진행 중", "—", border=True)
        st.metric("기한 임박", "—", border=True)
        st.metric("완료", "—", border=True)

    st.dataframe(
        pd.DataFrame(ACTION_COLUMNS),
        hide_index=True,
        width="stretch",
        column_config={
            "목표일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "최근 업데이트": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        },
    )
    st.button(
        "개선과제 등록",
        icon=":material/add_task:",
        disabled=True,
        key="actual_upeh_add_action",
    )
