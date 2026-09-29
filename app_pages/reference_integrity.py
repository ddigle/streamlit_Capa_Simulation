# Purpose: 표준 대비 실적 Capa 손실을 분해하고 그 손실을 파고드는 하위 화면으로 잇는다.

"""Dynamic Capa 상위 화면.

이 그룹의 하위 여섯 화면은 각각 **손실 한 조각**을 본다. 그런데 그 조각들이 무엇의
조각인지는 어디에도 없었다. 그래서 하위 화면을 따로 보면 「이걸 왜 보나」가 남는다.

상위 화면을 손실 분해로 세우고, 분해된 칸마다 그 칸을 파고드는 화면으로 링크를 건다.
그러면 그룹 전체가 **하나의 질문**을 갖는다 — 표준 Capa 를 왜 다 못 냈나.

요약과 상세를 탭으로 가른다. 보고 자리에서 볼 것(결론 한 문장·순위·다음 화면)과
분석하며 뒤질 것(조회 조건·워터폴·일별 추이)이 다르다.
"""

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
from capa_simulation.components.page_header import (
    MATURITY_BADGES,
    page_badges,
    pending_badge,
    render_page_header,
)
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.roadmap_panel import render_roadmap_panel
from capa_simulation.components.sample_data import (
    render_pending_source,
    render_sample_switch,
)
from capa_simulation.components.status_metric import (
    metric_row,
    render_status_metric,
    shortage_tone,
)
from capa_simulation.components.tab_state import OpenTab, stateful_tabs, tab_is_hidden
from capa_simulation.services.dynamic_capacity import (
    aggregate_dynamic_capacity,
    build_dynamic_capacity_demo,
    filter_dynamic_capacity,
)

_ALL = "전체"
_CAPACITY_UNIT_LABELS = {"WF": "매", "CHIP": "Kea", "PKG": "Kea"}
_SOURCE = "실적 DB"

# 손실 한 칸과 그 칸을 파고드는 화면. **워터폴에 서는 차례 그대로** 둔다 — 화면 목록이
# 손실 순서와 다르면 목차 구실을 못 한다.
_LOSS_ROUTES = (
    (
        "효율 손실",
        "표준 → 효율 반영",
        "app_pages/actual_efficiency.py",
        ":material/speed:",
    ),
    (
        "UPEH 손실",
        "효율 반영 → 실효",
        "app_pages/actual_upeh.py",
        ":material/timer:",
    ),
    (
        "수율 손실",
        "양품 기준 차감",
        "app_pages/yield_actual.py",
        ":material/percent:",
    ),
    (
        "재공부족 미활용",
        "실효 → 모델 실적",
        "app_pages/wip_status.py",
        ":material/inventory_2:",
    ),
    (
        "설비 가용",
        "손실 이전의 전제",
        "app_pages/available_equipment_status.py",
        ":material/precision_manufacturing:",
    ),
)


def _clear_invalid_widget_value(key: str, options: list[str]) -> None:
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def _render_pending_screen() -> None:
    """스위치를 껐을 때. 이 화면이 무엇을 기다리는지만 적는다."""
    render_pending_source(
        subject="표준 대비 실적 Capa",
        source=_SOURCE,
        expects=(
            "일자 · 공정 · 제품 · Stack · WF 속성별 **실적 효율**과 **실적 UPEH**",
            "같은 분류의 **생산실적 수량**",
            "**계획시간 · 실가동시간 · Rundown 시간 · 설비 Down 시간** 분류 규칙 — "
            "이 분류가 곧 손실의 이름이 되므로 컬럼 매핑을 먼저 확정해야 합니다",
            "표준 Capa 는 지금처럼 활성 시나리오·리비전 스냅샷에서 옵니다",
        ),
    )
    with st.container(border=True):
        st.markdown("#### :material/route: 연결되면 이 화면이 하는 일")
        st.markdown(
            "- 표준 Capa 부터 실제 실적까지를 **손실 한 칸씩** 이어 붙입니다.\n"
            "- 각 칸의 크기로 **어느 하위 화면부터 봐야 하는지**를 정합니다.\n"
            "- 공정 간 단위(WF 매 · CHIP/PKG Kea)가 달라 수량은 합산하지 않고 비율로 비교합니다."
        )


def _render_summary(
    process_summary: pd.DataFrame,
    labels: ProcessLabels,
    *,
    owner_tab: OpenTab | None,
) -> None:
    needs_action = process_summary.loc[process_summary["상태"].eq("개선 필요")]
    if needs_action.empty:
        st.success("Capa 실현률이 판정 기준을 밑도는 공정이 없습니다.")
    else:
        worst = needs_action.iloc[0]
        st.warning(
            f"**{labels.label(worst['공정'])}** 의 Capa 실현률이 "
            f"{float(worst['Capa 실현률']):.0%} 로 가장 낮습니다. 설비 성능 실현률은 "
            f"{float(worst['설비 성능 실현률']):.0%}, 가용 Capa 활용률은 "
            f"{float(worst['가용 Capa 활용률']):.0%} 입니다 — 성능과 활용 중 어느 쪽이 "
            f"더 깎아먹는지가 다음 화면을 정합니다. 개선 필요 공정은 모두 "
            f"{len(needs_action):,}개입니다."
        )

    with metric_row(key="reference_integrity_summary_metrics"):
        st.metric("분석 공정", f"{process_summary['공정'].nunique():,}개", border=True)
        render_status_metric(
            "개선 필요",
            f"{len(needs_action):,}개",
            key="reference_integrity_needs_action",
            tone=shortage_tone(len(needs_action)),
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
    st.caption(
        "프로토타입 판정 기준: Capa 실현률 90% 이상 정상, 80% 이상 관찰, 80% 미만 개선 필요. "
        "아래 `Capa 실현률` 막대의 색이 이 판정이며 정상·관찰·개선 필요 순으로 짙어집니다."
    )

    overview_chart, overview_table = st.columns([1.35, 1.0], gap="medium")
    with overview_chart.container(border=True):
        st.markdown("#### :material/bar_chart: 공정별 Capa 실현 수준")
        st.caption("단위가 다른 공정은 수량을 합산하지 않고 각 공정의 비율로 비교합니다.")
        if not tab_is_hidden(owner_tab):
            st.plotly_chart(
                build_process_comparison_figure(process_summary, process_labels=labels),
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
        # CSV 출구가 없는 조회 표다. 화면 복사본에만 표시명을 입힌다.
        priority["공정"] = labels.series(priority["공정"])
        st.dataframe(
            priority,
            hide_index=True,
            width="stretch",
            # 높이를 못박으면 공정이 적을 때 빈 줄이 남아 데이터가 잘린 것처럼 보인다.
            height=min(365, (len(priority) + 1) * 36 + 4),
            column_config={
                "순위": st.column_config.NumberColumn(width="small", format="%d"),
                "소요기준": st.column_config.TextColumn("단위", width="small"),
                "Capa 실현률": st.column_config.NumberColumn(format="percent"),
                "설비 성능 실현률": st.column_config.NumberColumn(format="percent"),
                "가용 Capa 활용률": st.column_config.NumberColumn(format="percent"),
                "재공부족 미활용률": st.column_config.NumberColumn(format="percent"),
            },
        )

    _render_loss_routes()


def _render_loss_routes() -> None:
    """손실 칸마다 그 칸을 파고드는 화면으로 잇는다. 이 그룹의 목차다."""
    with st.container(border=True):
        st.markdown("#### :material/alt_route: 손실을 파고드는 화면")
        st.caption(
            "아래 순서는 워터폴에서 손실이 차감되는 차례와 같습니다. 칸이 큰 쪽부터 "
            "들어가면 됩니다."
        )
        columns = st.columns(len(_LOSS_ROUTES), gap="small")
        for column, (title, subtitle, page_path, icon) in zip(columns, _LOSS_ROUTES, strict=True):
            with column.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(subtitle)
                render_page_link(page_path, label="열기", icon=icon)


def _render_detail(
    demo: pd.DataFrame,
    process_summary: pd.DataFrame,
    labels: ProcessLabels,
    *,
    owner_tab: OpenTab | None,
) -> None:
    """조회 조건은 숨은 탭에서도 그린다. 건너뛰면 탭을 옮길 때마다 선택이 초기화된다."""
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
                persist_state="session",
                width=165,
            )
            end_date: date = st.date_input(
                "종료일",
                value=maximum_date,
                min_value=minimum_date,
                max_value=maximum_date,
                key="dynamic_capacity_end_date",
                persist_state="session",
                width=165,
            )
            process = cast(
                str,
                st.selectbox(
                    "공정",
                    process_options,
                    index=default_process_index,
                    key="dynamic_capacity_process_filter",
                    persist_state="session",
                    width=210,
                    # 표시만 바꾼다. 선택값은 원본이라 아래 `eq`·`filter_dynamic_capacity` 가
                    # 원본 컬럼과 그대로 대조한다.
                    format_func=labels.format_func(),
                ),
            )

            process_rows = demo.loc[demo["공정"].eq(process)]
            product_options = [
                _ALL,
                *sorted(process_rows["제품정보"].astype(str).unique().tolist()),
            ]
            _clear_invalid_widget_value("dynamic_capacity_product_filter", product_options)
            product = cast(
                str,
                st.selectbox(
                    "제품",
                    product_options,
                    key="dynamic_capacity_product_filter",
                    persist_state="session",
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
                    persist_state="session",
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
                    persist_state="session",
                    width=160,
                ),
            )

    if start_date > end_date:
        st.error("조회 시작일은 종료일보다 늦을 수 없습니다.")
        return

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
        st.info("선택한 조건에 해당하는 Dynamic Capa 데이터가 없습니다.")
        return

    detail_summary = aggregate_dynamic_capacity(filtered, ["공정"]).iloc[0]
    requirement_basis = str(detail_summary["소요기준"])
    unit_label = _CAPACITY_UNIT_LABELS.get(requirement_basis, requirement_basis)

    with metric_row(key="reference_integrity_detail_metrics"):
        st.metric(
            f"표준 Capa ({unit_label})",
            f"{detail_summary['표준 Capa']:,.0f}",
            border=True,
        )
        # 증감 문구는 부호로 시작해야 한다. 앞에 말을 붙이면 Streamlit 이 음수로 읽지 못해
        # 미달인데도 초록 상승 화살표가 붙는다. 설명은 `delta_description` 이 맡는다.
        st.metric(
            f"실효 Capa ({unit_label})",
            f"{detail_summary['실효 Capa']:,.0f}",
            delta=f"{detail_summary['설비 성능 실현률'] - 1:.1%}",
            delta_description="표준 대비",
            border=True,
        )
        st.metric(
            f"실제 실적 ({unit_label})",
            f"{detail_summary['실적수량']:,.0f}",
            delta=f"{detail_summary['Capa 실현률'] - 1:.1%}",
            delta_description="표준 대비",
            border=True,
        )
        st.metric("Capa 실현률", f"{detail_summary['Capa 실현률']:.1%}", border=True)
        st.metric(
            "가용 Capa 활용률",
            f"{detail_summary['가용 Capa 활용률']:.1%}",
            border=True,
        )

    if tab_is_hidden(owner_tab):
        return

    waterfall_column, trend_column = st.columns(2, gap="medium")
    with waterfall_column.container(border=True):
        st.markdown("#### :material/waterfall_chart: Capa 손실 구조")
        st.caption(
            f"선택한 {labels.label(process)} 공정의 표준 Capa부터 실제 실적까지를 "
            f"{unit_label}로 연결합니다."
        )
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
        with metric_row(key="reference_integrity_cause_metrics"):
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
            # 이 줄은 증감이 아니라 함께 보는 값이다. `delta_color="off"` 는 색만 끄므로
            # 화살표까지 지우려면 `delta_arrow="off"` 가 따로 필요하다.
            st.metric(
                "Rundown 시간",
                f"{detail_summary['Rundown 시간']:,.1f}h",
                delta=f"미활용 Capa {detail_summary['재공부족 미활용 Capa']:,.0f}{unit_label}",
                delta_color="off",
                delta_arrow="off",
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


def _render_guide() -> None:
    st.caption(
        "공정별 소요기준이 다르므로 Capa 수량 단위는 WF=매, CHIP·PKG=Kea로 표시합니다. "
        "서로 다른 단위의 공정은 수량을 합산하지 않고 실현률로 비교합니다."
    )
    capacity_guide, rate_guide = st.columns(2, gap="large")
    with capacity_guide.container(border=True):
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

    with rate_guide.container(border=True):
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

    with st.container(border=True):
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

    with st.container(border=True):
        st.markdown("##### 실제 DB 연결 시 적용할 데이터 구조")
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


# 공정 표시명은 화면 표기 전용 라벨이다. 선택값·집계 키·계산 입력은 원본 공정명을 쓴다.
process_labels = get_process_labels()

render_page_header(
    "Dynamic Capa",
    description=(
        "표준 Capa와 실적 효율·UPEH·생산실적을 연결해 Capa 손실 원인과 개선 우선순위를 분석합니다."
    ),
    badges=page_badges(MATURITY_BADGES["prototype"], pending_badge(_SOURCE)),
)
render_roadmap_panel(
    purpose=(
        "실적 DB를 표준 Capa와 연결해 가용 Capa 활용 손실과 설비 성능 손실을 분리하고 "
        "담당 부서별 Action Item으로 전환합니다."
    ),
    owners=(
        (
            "제조팀 · Capa 활용 극대화",
            "Rundown을 줄이기 위한 재공운영 A/Item으로 가용 Capa 활용률 개선",
        ),
        (
            "기술팀 · 설비성능 극대화",
            "UPEH·효율 실적 Gap을 근거로 설비 성능 실현률 개선 항목을 우선 관리",
        ),
    ),
    roadmap="실적 DB 연결 → 손실 원인 분해 → 부서별 A/Item → 개선 효과 이력 관리",
)

if not render_sample_switch(key="dynamic_capa_sample_switch", source=_SOURCE):
    _render_pending_screen()
    st.stop()

demo = build_dynamic_capacity_demo()
process_summary = aggregate_dynamic_capacity(demo, ["공정"]).sort_values(
    ["Capa 실현률", "공정"], kind="stable"
)

summary_tab, detail_tab, guide_tab = stateful_tabs(
    ["요약", "공정 상세", "산식 가이드"],
    key="dynamic_capa_active_tab",
)
with summary_tab:
    _render_summary(process_summary, process_labels, owner_tab=summary_tab)
with detail_tab:
    _render_detail(demo, process_summary, process_labels, owner_tab=detail_tab)
with guide_tab:
    _render_guide()
