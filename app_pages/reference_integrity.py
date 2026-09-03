# Purpose: 표준·실효·실적 Capa와 손실 원인을 비교하는 Dynamic Capa 상위 대시보드 초안을 렌더링한다.
# Applied: 2026-09-03 KST
# Agent: OpenAI Codex
# Model: GPT-5 (exact runtime variant unavailable)
# Change: 파일 목적 및 최신 변경 출처 헤더를 표준화함; 이전 이력은 Git 기록을 참조함.

from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd
import streamlit as st

from capa_simulation.components.dynamic_capacity_dashboard import (
    build_capacity_trend_figure,
    build_capacity_waterfall_figure,
    build_process_comparison_figure,
)
from capa_simulation.services.dynamic_capacity import (
    aggregate_dynamic_capacity,
    build_dynamic_capacity_demo,
    filter_dynamic_capacity,
)

_ALL = "전체"
_CAPACITY_UNIT_LABELS = {"WF": "매", "CHIP": "Kea", "PKG": "Kea"}


def _clear_invalid_widget_value(key: str, options: list[str]) -> None:
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


st.title("Dynamic Capa (구현중)")
st.caption(
    "표준 Capa와 실적 효율·UPEH·생산실적을 연결해 Capa 손실 원인과 개선 우선순위를 분석합니다."
)
with st.container(border=True):
    st.markdown("#### :material/route: 업무 활용 목적 및 로드맵")
    st.caption(
        "실적 DB를 표준 Capa와 연결해 가용 Capa 활용 손실과 설비 성능 손실을 분리하고 "
        "담당 부서별 Action Item으로 전환합니다."
    )
    with st.container(horizontal=True, gap="small"):
        with st.container(border=True):
            st.markdown("**제조팀 · Capa 활용 극대화**")
            st.write("Rundown을 줄이기 위한 재공운영 A/Item으로 가용 Capa 활용률 개선")
        with st.container(border=True):
            st.markdown("**기술팀 · 설비성능 극대화**")
            st.write("UPEH·효율 실적 Gap을 근거로 설비 성능 실현률 개선 항목을 우선 관리")
    st.caption("로드맵 · 실적 DB 연결 → 손실 원인 분해 → 부서별 A/Item → 개선 효과 이력 관리")

st.markdown(":green-badge[인터랙티브 프로토타입] :orange-badge[실적 DB 미연결]")
st.info(
    "현재 화면의 수치는 구조 검토용 데모 데이터입니다. 실제 운영 연결 시 표준 Capa는 "
    "선택한 시나리오·리비전에서, 효율과 생산실적은 누적 이력 DB에서 읽습니다.",
    icon=":material/science:",
)

with st.expander("용어 및 산식 가이드", icon=":material/menu_book:"):
    st.caption(
        "공정별 소요기준이 다르므로 Capa 수량 단위는 WF=매, CHIP·PKG=Kea로 표시합니다. "
        "서로 다른 단위의 공정은 수량을 합산하지 않고 실현률로 비교합니다."
    )
    capacity_guide, rate_guide = st.columns(2, gap="large")
    with capacity_guide:
        st.markdown("##### Capa 단계")
        st.markdown(
            "- **표준 Capa**: 선택한 표준 시나리오의 기준 효율·기준 UPEH로 계산한 Capa입니다.\n"
            "- **효율 반영 Capa**: `표준 Capa × 실적 효율 ÷ 표준 효율`입니다. 설비 Down 등 "
            "효율 차이를 반영한 값입니다.\n"
            "- **실효 Capa**: `효율 반영 Capa × 실적 UPEH ÷ 표준 UPEH`입니다. 효율과 UPEH "
            "실적을 반영했지만 Rundown은 차감하지 않은 가용 성능입니다.\n"
            "- **모델 실적 Capa**: `실효 Capa × 실가동시간 ÷ (실가동시간 + Rundown시간)`입니다.\n"
            "- **실제 실적**: 생산실적 DB에서 집계한 실제 투입·생산수량입니다."
        )

    with rate_guide:
        st.markdown("##### 실현률과 활용률")
        st.markdown(
            "- **설비 성능 실현률**: `실효 Capa ÷ 표준 Capa`입니다. 재공부족 영향은 제외하고 "
            "효율·UPEH 성능이 표준을 얼마나 실현했는지 보여줍니다.\n"
            "- **Capa 실현률**: `실제 실적 ÷ 표준 Capa`입니다. 효율·UPEH·Rundown과 기타 "
            "요인을 모두 포함한 최종 실현 수준입니다.\n"
            "- **가용 Capa 활용률**: `실제 실적 ÷ 실효 Capa`입니다. 확보한 실효 Capa가 "
            "실제 생산으로 얼마나 사용됐는지 보여줍니다.\n"
            "- **Rundown**: 설비는 투입할 수 있었지만 재공이 없어 가동하지 못한 시간입니다.\n"
            "- **재공부족 미활용 Capa**: `실효 Capa − 모델 실적 Capa`입니다."
        )

    st.markdown("##### Gap 해석")
    st.markdown(
        "- **효율 Gap**: `실적 효율 − 표준 효율`이며 `%p`로 해석합니다. 음수이면 표준보다 "
        "효율이 낮습니다.\n"
        "- **UPEH Gap**: `실적 UPEH ÷ 표준 UPEH − 1`입니다. 음수이면 표준보다 생산성이 "
        "낮습니다.\n"
        "- **효율 손실 Capa**: `표준 Capa − 효율 반영 Capa`, **UPEH 손실 Capa**는 "
        "`효율 반영 Capa − 실효 Capa`입니다.\n"
        "- **기타 Gap**: `모델 실적 Capa − 실제 실적`입니다. 아직 효율·UPEH·Rundown으로 "
        "설명되지 않은 정합성 잔차이며, 실제 DB 연결 후 수율·데이터 시점·미분류 Loss 등으로 "
        "세분화합니다. 양수이면 모델 대비 실제 실적이 부족하고, 음수이면 실제 실적이 모델을 "
        "초과한 것입니다."
    )

demo = build_dynamic_capacity_demo()
process_summary = aggregate_dynamic_capacity(demo, ["공정"]).sort_values(
    ["Capa 실현률", "공정"], kind="stable"
)

st.subheader("전체 공정 요약", divider="gray")
with st.container(horizontal=True, gap="small"):
    st.metric("분석 공정", f"{process_summary['공정'].nunique():,}개", border=True)
    st.metric(
        "개선 필요",
        f"{process_summary['상태'].eq('개선 필요').sum():,}개",
        border=True,
    )
    st.metric(
        "중앙 Capa 실현률",
        f"{process_summary['Capa 실현률'].median():.1%}",
        border=True,
    )
    st.metric(
        "중앙 설비 성능 실현률",
        f"{process_summary['설비 성능 실현률'].median():.1%}",
        border=True,
    )
    st.metric(
        "Rundown 누계",
        f"{process_summary['Rundown 시간'].sum():,.1f}h",
        border=True,
    )
st.caption("프로토타입 판정 기준: Capa 실현률 90% 이상 정상, 80% 이상 관찰, 80% 미만 개선 필요")

overview_chart, overview_table = st.columns([1.35, 1.0], gap="medium")
with overview_chart.container(border=True):
    st.markdown("#### :material/bar_chart: 공정별 Capa 실현 수준")
    st.caption("단위가 다른 공정은 수량을 합산하지 않고 각 공정의 비율로 비교합니다.")
    st.plotly_chart(
        build_process_comparison_figure(process_summary),
        width="stretch",
        config={"displayModeBar": False},
        key="dynamic_capacity_process_overview",
    )

with overview_table.container(border=True):
    st.markdown("#### :material/priority_high: 관리 우선순위")
    st.caption("실현률이 낮은 공정부터 배치하며 제품 Mix는 상세 조회에서 분리합니다.")
    priority = process_summary[
        [
            "공정",
            "소요기준",
            "Capa 실현률",
            "설비 성능 실현률",
            "가용 Capa 활용률",
            "재공부족 미활용률",
            "상태",
        ]
    ].reset_index(drop=True)
    priority.insert(0, "순위", pd.Series(range(1, len(priority) + 1), dtype="int64"))
    st.dataframe(
        priority,
        hide_index=True,
        width="stretch",
        height=365,
        column_config={
            "순위": st.column_config.NumberColumn(width="small", format="%d"),
            "소요기준": st.column_config.TextColumn("단위", width="small"),
            "Capa 실현률": st.column_config.NumberColumn(format="percent"),
            "설비 성능 실현률": st.column_config.NumberColumn(format="percent"),
            "가용 Capa 활용률": st.column_config.NumberColumn(format="percent"),
            "재공부족 미활용률": st.column_config.NumberColumn(format="percent"),
        },
    )

st.subheader("표준 대비 실적 Capa 상세", divider="gray")
with st.container(border=True):
    st.markdown("#### :material/filter_alt: 상세 조회 조건")
    minimum_date = cast(pd.Timestamp, demo["일자"].min()).date()
    maximum_date = cast(pd.Timestamp, demo["일자"].max()).date()
    worst_process = str(process_summary.iloc[0]["공정"])
    process_options = sorted(demo["공정"].astype(str).unique().tolist())
    default_process_index = process_options.index(worst_process)

    with st.container(horizontal=True, gap="small"):
        start_date: date = st.date_input(
            "시작일",
            value=minimum_date,
            min_value=minimum_date,
            max_value=maximum_date,
            key="dynamic_capacity_start_date",
            width=165,
        )
        end_date: date = st.date_input(
            "종료일",
            value=maximum_date,
            min_value=minimum_date,
            max_value=maximum_date,
            key="dynamic_capacity_end_date",
            width=165,
        )
        process = cast(
            str,
            st.selectbox(
                "공정",
                process_options,
                index=default_process_index,
                key="dynamic_capacity_process_filter",
                width=210,
            ),
        )

        process_rows = demo.loc[demo["공정"].eq(process)]
        product_options = [_ALL, *sorted(process_rows["제품정보"].astype(str).unique().tolist())]
        _clear_invalid_widget_value("dynamic_capacity_product_filter", product_options)
        product = cast(
            str,
            st.selectbox(
                "제품",
                product_options,
                key="dynamic_capacity_product_filter",
                width=190,
            ),
        )
        product_rows = process_rows
        if product != _ALL:
            product_rows = product_rows.loc[product_rows["제품정보"].eq(product)]

        stack_options = [_ALL, *sorted(product_rows["Stack"].astype(str).unique().tolist())]
        _clear_invalid_widget_value("dynamic_capacity_stack_filter", stack_options)
        stack = cast(
            str,
            st.selectbox(
                "Stack",
                stack_options,
                key="dynamic_capacity_stack_filter",
                width=140,
            ),
        )
        stack_rows = product_rows
        if stack != _ALL:
            stack_rows = stack_rows.loc[stack_rows["Stack"].eq(stack)]

        wafer_type_options = [
            _ALL,
            *sorted(stack_rows["WF 구분"].astype(str).unique().tolist()),
        ]
        _clear_invalid_widget_value("dynamic_capacity_wafer_type_filter", wafer_type_options)
        wafer_type = cast(
            str,
            st.selectbox(
                "WF 속성",
                wafer_type_options,
                key="dynamic_capacity_wafer_type_filter",
                width=160,
            ),
        )

if start_date > end_date:
    st.error("조회 시작일은 종료일보다 늦을 수 없습니다.")
    st.stop()

filtered = filter_dynamic_capacity(
    demo,
    start_date=start_date,
    end_date=end_date,
    process=process,
    product=None if product == _ALL else product,
    stack=None if stack == _ALL else stack,
    wafer_type=None if wafer_type == _ALL else wafer_type,
)
if filtered.empty:
    st.warning("선택한 조건에 해당하는 Dynamic Capa 데이터가 없습니다.")
    st.stop()

detail_summary = aggregate_dynamic_capacity(filtered, ["공정"]).iloc[0]
requirement_basis = str(detail_summary["소요기준"])
unit_label = _CAPACITY_UNIT_LABELS.get(requirement_basis, requirement_basis)

with st.container(horizontal=True, gap="small"):
    st.metric(
        f"표준 Capa ({unit_label})",
        f"{detail_summary['표준 Capa']:,.0f}",
        border=True,
    )
    st.metric(
        f"실효 Capa ({unit_label})",
        f"{detail_summary['실효 Capa']:,.0f}",
        delta=f"표준 대비 {detail_summary['설비 성능 실현률'] - 1:.1%}",
        border=True,
    )
    st.metric(
        f"실제 실적 ({unit_label})",
        f"{detail_summary['실적수량']:,.0f}",
        delta=f"표준 대비 {detail_summary['Capa 실현률'] - 1:.1%}",
        border=True,
    )
    st.metric("Capa 실현률", f"{detail_summary['Capa 실현률']:.1%}", border=True)
    st.metric(
        "가용 Capa 활용률",
        f"{detail_summary['가용 Capa 활용률']:.1%}",
        border=True,
    )

waterfall_column, trend_column = st.columns(2, gap="medium")
with waterfall_column.container(border=True):
    st.markdown("#### :material/waterfall_chart: Capa 손실 구조")
    st.caption(f"선택한 {process} 공정의 표준 Capa부터 실제 실적까지를 {unit_label}로 연결합니다.")
    st.plotly_chart(
        build_capacity_waterfall_figure(detail_summary),
        width="stretch",
        config={"displayModeBar": False},
        key="dynamic_capacity_waterfall",
    )

with trend_column.container(border=True):
    st.markdown("#### :material/show_chart: 일별 Capa 추이")
    st.caption("표준 Capa, 설비 성능 기준 실효 Capa와 실제 생산실적을 일별로 비교합니다.")
    st.plotly_chart(
        build_capacity_trend_figure(filtered),
        width="stretch",
        config={"displayModeBar": False},
        key="dynamic_capacity_trend",
    )

with st.container(border=True):
    st.markdown("#### :material/search_insights: 원인 지표")
    with st.container(horizontal=True, gap="small"):
        st.metric(
            "효율 실적 / 기준",
            f"{detail_summary['실적 효율']:.1%} / {detail_summary['표준 효율']:.1%}",
            delta=f"{detail_summary['효율 Gap']:.1%}p",
            border=True,
        )
        st.metric(
            "UPEH 실적 / 기준",
            f"{detail_summary['실적 UPEH']:,.1f} / {detail_summary['표준 UPEH']:,.1f}",
            delta=f"{detail_summary['UPEH Gap']:.1%}",
            border=True,
        )
        st.metric(
            "Rundown 시간",
            f"{detail_summary['Rundown 시간']:,.1f}h",
            delta=f"미활용 Capa {detail_summary['재공부족 미활용 Capa']:,.0f}{unit_label}",
            delta_color="off",
            border=True,
        )
        st.metric(
            "설비 Down 시간",
            f"{detail_summary['설비 Down 시간']:,.1f}h",
            border=True,
        )

    product_detail = aggregate_dynamic_capacity(
        filtered,
        ["제품정보", "Stack", "WF 구분"],
    ).sort_values(["Capa 실현률", "제품정보", "Stack"], kind="stable")
    st.dataframe(
        product_detail[
            [
                "제품정보",
                "Stack",
                "WF 구분",
                "표준 Capa",
                "실효 Capa",
                "실적수량",
                "Capa 실현률",
                "효율 Gap",
                "UPEH Gap",
                "재공부족 미활용 Capa",
                "상태",
            ]
        ].rename(columns={"제품정보": "제품", "WF 구분": "속성", "실적수량": "실제 실적"}),
        hide_index=True,
        width="stretch",
        column_config={
            "표준 Capa": st.column_config.NumberColumn(format="%,.1f"),
            "실효 Capa": st.column_config.NumberColumn(format="%,.1f"),
            "실제 실적": st.column_config.NumberColumn(format="%,.1f"),
            "Capa 실현률": st.column_config.NumberColumn(format="percent"),
            "효율 Gap": st.column_config.NumberColumn(format="percent"),
            "UPEH Gap": st.column_config.NumberColumn(format="percent"),
            "재공부족 미활용 Capa": st.column_config.NumberColumn(format="%,.1f"),
        },
    )

with st.expander("실제 DB 연결 시 적용할 데이터 구조", icon=":material/database:"):
    st.markdown(
        "- **표준 Capa:** 현재처럼 시나리오·리비전별 스냅샷으로 보존합니다.\n"
        "- **실적 효율·생산실적:** 일정 주기로 갱신하되 과거 행을 덮지 않는 누적 이력으로 "
        "관리합니다. 시나리오마다 실적을 복제하지 않습니다.\n"
        "- **상세 연결 수준:** 일자 · 공정 · 제품 · Stack · WF 속성을 기본으로 하고, "
        "실제 DB가 제공하면 설비·호기·Shift까지 확장합니다.\n"
        "- **상위 집계:** Capa와 생산수량은 합계, 효율은 계획시간, UPEH는 실가동시간을 "
        "가중치로 사용합니다. 비율은 집계된 분자·분모로 다시 계산합니다.\n"
        "- **시간 분류:** Rundown·실가동·설비 Down 등 실제 컬럼 매핑은 실적효율 DB 연결 시 "
        "확정합니다."
    )
