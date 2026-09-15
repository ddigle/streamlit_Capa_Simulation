# Purpose: 효율·UPEH·수율 실적 화면을 지표 사양 하나만 바꿔 그리는 공통 화면을 제공한다.

"""실적 Gap 화면.

세 화면(효율·UPEH·수율)이 **같은 질문을 지표만 바꿔** 묻는다. 각자 그리면 같은 질문에
세 가지 레이아웃이 나오고, 한 화면만 고쳐지는 일이 반복된다. 여기 한 벌만 두고
`MetricSpec` 을 바꿔 끼운다.

**요약과 상세를 탭으로 가른다.** 보고 자리에서 볼 것과 분석하며 뒤질 것이 다르다.
요약은 결론 한 문장과 큰 숫자 넷, 추이 하나, 순위 하나로 끝낸다 — 그 자리에서 읽히지
않는 것은 요약이 아니다. 상세는 조회 조건을 주고 월 × 공정을 다 편다.

샘플 스위치를 끄면 **지금 상태**(원천 미연결)를 그대로 보여 준다. 합성 숫자가 실적처럼
읽히는 것을 막는 장치이면서, 「무엇이 이 자리를 채우는가」를 같은 화면에서 답하게 한다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.components.sample_data import (
    render_pending_source,
    render_sample_switch,
)
from capa_simulation.components.status_metric import metric_row
from capa_simulation.components.tab_state import OpenTab, stateful_tabs, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.performance_actuals import (
    MetricSpec,
    build_gap_table,
    build_improvement_actions,
    build_monthly_actual_demo,
    build_monthly_trend,
    build_priority_table,
)

_ALL = "전체"
STATUS_COLORS = {
    "개선 필요": tokens.STATUS_SHORTAGE,
    "관찰": tokens.STATUS_WARNING,
    "정상": tokens.STATUS_SECURE,
}


def render_performance_actual_screen(
    metric: MetricSpec,
    *,
    key_prefix: str,
    process_labels: ProcessLabels | None = None,
) -> None:
    """한 지표의 실적 Gap 화면 전체."""
    labels = process_labels or ProcessLabels()
    enabled = render_sample_switch(key=f"{key_prefix}_sample_switch", source=metric.source)
    if not enabled:
        _render_pending_screen(metric)
        return

    monthly = build_monthly_actual_demo()
    # 숨은 탭에서 Plotly 를 그리면 폭 0 짜리 SVG 가 나와 다시 열었을 때 축이 어긋난다.
    # 조회 조건 위젯은 숨어 있어도 그려야 탭을 오갈 때 선택이 살아남는다.
    summary_tab, detail_tab, action_tab = stateful_tabs(
        ["요약", "상세 분석", "개선과제"],
        key=f"{key_prefix}_active_tab",
    )
    with summary_tab:
        _render_summary(metric, monthly, labels, key_prefix=key_prefix, owner_tab=summary_tab)
    with detail_tab:
        _render_detail(metric, monthly, labels, key_prefix=key_prefix, owner_tab=detail_tab)
    with action_tab:
        _render_actions(metric, monthly, labels)


def _render_pending_screen(metric: MetricSpec) -> None:
    """스위치를 껐을 때. 지금 화면이 무엇을 기다리는지만 적는다."""
    render_pending_source(
        subject=f"{metric.name} 실적",
        source=metric.source,
        expects=(
            f"생산계획년월 · 공정 · 양산구분 · 제품 · Stack 별 **{metric.actual_column}**",
            f"같은 분류의 **{metric.standard_column}** (Capa 기준정보에서 옴)",
            "우선순위 가중치로 쓸 **공통 환산 생산수량** — 단위가 다른 공정을 "
            "한 줄에 세우려면 반드시 필요합니다",
            "집계 구간(월 마감 시점)과 공정 코드 매핑 규칙",
        ),
    )
    with st.container(border=True):
        st.markdown("#### :material/rule: 연결되면 계산할 것")
        st.markdown(
            f"- **Gap** = `{metric.actual_column} − {metric.standard_column}`"
            if metric.gap_kind == "point"
            else f"- **Gap** = `{metric.actual_column} ÷ {metric.standard_column} − 1`"
        )
        st.markdown(
            "- **상태** = 마지막 달 기준 연속 미달 개월. 0 정상 · 1~2 관찰 · 3 이상 개선 필요\n"
            "- **우선순위 점수** = `미달폭 × 영향 비중 × 연속 미달 가중`\n"
            "- **비율 집계** = 월별 비율의 평균이 아니라 생산수량 가중으로 다시 계산"
        )


def _render_summary(
    metric: MetricSpec,
    monthly: pd.DataFrame,
    labels: ProcessLabels,
    *,
    key_prefix: str,
    owner_tab: OpenTab | None = None,
) -> None:
    """보고 자리에서 읽히는 것만. 결론 한 문장이 맨 위다."""
    priority = build_priority_table(monthly, metric, ["공정"])
    overall = build_gap_table(monthly, metric, ["양산구분"]).iloc[0]
    trend = build_monthly_trend(monthly, metric)
    needs_action = priority.loc[priority["상태"].eq("개선 필요")]

    if needs_action.empty:
        st.success(f"{metric.name} 기준을 석 달 넘게 못 맞춘 공정이 없습니다.")
    else:
        worst = needs_action.iloc[0]
        st.warning(
            f"**{labels.label(worst['공정'])}** 이(가) {int(worst['연속 미달'])}개월 연속 "
            f"{metric.name} 기준 미달입니다. 기간 평균 Gap "
            f"{float(worst['Gap']):.1%}{metric.gap_suffix}, 영향 물량 비중 "
            f"{float(worst['영향 비중']):.0%}. 개선 필요 공정은 모두 {len(needs_action):,}개입니다."
        )

    with metric_row(key=f"{key_prefix}_summary_metrics"):
        st.metric(
            f"실적 {metric.name}",
            _format_value(float(overall[metric.actual_column]), metric),
            delta=f"{float(overall['Gap']):.1%}{metric.gap_suffix}",
            delta_description="기준 대비",
            border=True,
        )
        st.metric(
            f"기준 {metric.name}",
            _format_value(float(overall[metric.standard_column]), metric),
            border=True,
        )
        st.metric("개선 필요 공정", f"{len(needs_action):,}개", border=True)
        st.metric(
            "관찰 공정",
            f"{int(priority['상태'].eq('관찰').sum()):,}개",
            border=True,
        )
        st.metric("분석 공정", f"{priority['공정'].nunique():,}개", border=True)

    if tab_is_hidden(owner_tab):
        return
    trend_column, rank_column = st.columns([1.25, 1.0], gap="medium")
    with trend_column.container(border=True):
        st.markdown(f"#### :material/show_chart: 월별 {metric.name} 추이")
        st.caption("기준선과 실적선의 간격이 그 달의 Gap 입니다. 생산수량 가중 평균입니다.")
        st.plotly_chart(
            _trend_figure(trend, metric),
            width="stretch",
            config={"displayModeBar": False},
            key=f"{key_prefix}_trend_chart",
        )
    with rank_column.container(border=True):
        st.markdown("#### :material/priority_high: 공정 우선순위")
        st.caption("미달폭에 영향 물량과 연속 미달 개월을 곱한 순서입니다.")
        st.plotly_chart(
            _priority_figure(priority, metric, labels),
            width="stretch",
            config={"displayModeBar": False},
            key=f"{key_prefix}_priority_chart",
        )


def _render_detail(
    metric: MetricSpec,
    monthly: pd.DataFrame,
    labels: ProcessLabels,
    *,
    key_prefix: str,
    owner_tab: OpenTab | None = None,
) -> None:
    """조회 조건을 주고 월 × 공정 × 제품을 편다."""
    process_options = sorted(monthly["공정"].astype(str).unique().tolist())
    with st.container(border=True):
        st.markdown("#### :material/filter_alt: 조회 조건")
        with st.container(horizontal=True, gap="small"):
            months = sorted(int(value) for value in monthly["생산계획년월"].unique())
            start_month, end_month = st.select_slider(
                "분석 기간",
                options=months,
                value=(months[0], months[-1]),
                format_func=month_label,
                key=f"{key_prefix}_month_range",
                width=380,
            )
            selected_processes = st.multiselect(
                "공정",
                options=process_options,
                placeholder="전체 공정",
                format_func=labels.format_func(),
                key=f"{key_prefix}_process_filter",
                width=320,
            )
        product_options = [_ALL, *sorted(monthly["제품정보"].astype(str).unique().tolist())]
        product = st.selectbox(
            "제품",
            product_options,
            key=f"{key_prefix}_product_filter",
            width=220,
        )

    view = monthly.loc[monthly["생산계획년월"].between(start_month, end_month)]
    if selected_processes:
        view = view.loc[view["공정"].astype(str).isin(selected_processes)]
    if product != _ALL:
        view = view.loc[view["제품정보"].astype(str).eq(product)]
    if view.empty:
        st.warning("선택한 조건에 해당하는 실적이 없습니다.")
        return
    # 위젯까지 그린 뒤에 나간다. 앞에서 나가면 탭을 오갈 때 조회 조건이 초기화된다.
    if tab_is_hidden(owner_tab):
        return

    with st.container(border=True):
        st.markdown(f"#### :material/grid_on: 월 × 공정 {metric.name} Gap")
        st.caption(f"음수는 기준 미달입니다. 단위는 {metric.gap_unit} 이고 색이 짙을수록 큽니다.")
        st.plotly_chart(
            _gap_matrix_figure(view, metric, labels),
            width="stretch",
            config={"displayModeBar": False},
            key=f"{key_prefix}_gap_matrix",
        )

    with st.container(border=True):
        st.markdown("#### :material/table_rows: 제품·Stack 상세")
        detail = build_gap_table(view, metric, ["공정", "제품정보", "Stack", "WF 구분"])
        detail = detail.sort_values("Gap").reset_index(drop=True)
        detail["공정"] = labels.series(detail["공정"])
        st.dataframe(
            detail.rename(columns={"제품정보": "제품", "WF 구분": "속성"}),
            hide_index=True,
            width="stretch",
            column_config={
                metric.standard_column: _value_column(metric),
                metric.actual_column: _value_column(metric),
                "Gap": st.column_config.NumberColumn(f"Gap ({metric.gap_unit})", format="percent"),
                "생산수량": st.column_config.NumberColumn(format="%,.0f"),
                "영향 비중": st.column_config.NumberColumn(format="percent"),
            },
        )


def _render_actions(
    metric: MetricSpec,
    monthly: pd.DataFrame,
    labels: ProcessLabels,
) -> None:
    """순위가 그대로 과제 목록이 된다는 흐름을 보여 준다."""
    priority = build_priority_table(monthly, metric, ["공정"])
    actions = build_improvement_actions(metric, priority)

    with st.container(border=True):
        st.markdown("#### :material/format_list_numbered: 우선순위 산출 결과")
        st.caption(
            "점수는 `미달폭 × 영향 비중 × 연속 미달 가중`입니다. 가중치는 실제 데이터 "
            "분포를 보고 확정합니다."
        )
        shown = priority.copy()
        shown["공정"] = labels.series(shown["공정"])
        st.dataframe(
            shown[
                [
                    "우선순위",
                    "공정",
                    metric.standard_column,
                    metric.actual_column,
                    "Gap",
                    "영향 비중",
                    "연속 미달",
                    "점수",
                    "상태",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "우선순위": st.column_config.NumberColumn(width="small", format="%d"),
                metric.standard_column: _value_column(metric),
                metric.actual_column: _value_column(metric),
                "Gap": st.column_config.NumberColumn(f"Gap ({metric.gap_unit})", format="percent"),
                "영향 비중": st.column_config.NumberColumn(format="percent"),
                "연속 미달": st.column_config.NumberColumn("연속 미달(개월)", format="%d"),
                "점수": st.column_config.NumberColumn(format="%.1f"),
            },
        )

    with st.container(border=True):
        st.markdown("#### :material/assignment: 개선과제")
        st.caption("정상이 아닌 공정에만 과제가 붙습니다. 순위와 과제가 따로 놀지 않게 합니다.")
        if actions.empty:
            st.success("지금 기준으로는 개선과제가 필요한 공정이 없습니다.")
        else:
            shown_actions = actions.copy()
            shown_actions["공정"] = labels.series(shown_actions["공정"])
            shown_actions["목표월"] = [month_label(int(value)) for value in actions["목표월"]]
            st.dataframe(shown_actions, hide_index=True, width="stretch")


def _format_value(value: float, metric: MetricSpec) -> str:
    if metric.value_format == "percent":
        return f"{value:.1%}"
    return f"{value:,.0f}"


def _value_column(metric: MetricSpec) -> Any:
    """`st.column_config` 는 타입이 아니라 생성 함수라 반환형을 이름으로 적을 수 없다."""
    if metric.value_format == "percent":
        return st.column_config.NumberColumn(format="percent")
    return st.column_config.NumberColumn(format="%,.0f")


def _trend_figure(trend: pd.DataFrame, metric: MetricSpec) -> go.Figure:
    """기준선과 실적선. 두 선 사이를 칠해 Gap 을 면적으로도 읽게 한다."""
    months = [month_label(int(value)) for value in trend["생산계획년월"]]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=months,
            y=trend[metric.standard_column],
            name=f"기준 {metric.name}",
            mode="lines",
            line={"color": tokens.SERIES_STANDARD, "width": 2, "dash": "dash"},
            hovertemplate="%{x} 기준 %{y:,.3f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=months,
            y=trend[metric.actual_column],
            name=f"실적 {metric.name}",
            mode="lines+markers",
            line={"color": tokens.ACCENT, "width": 2},
            marker={"size": 6},
            fill="tonexty",
            # 면은 읽을 것이 아니라 간격의 크기만 알리는 배경이다. 선이 묻히면 안 된다.
            fillcolor=tokens.GAP_AREA_SHORTFALL,
            hovertemplate="%{x} 실적 %{y:,.3f}<extra></extra>",
        )
    )
    figure.update_layout(
        height=280,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.CHART_CANVAS,
        font={"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": 12},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0.0},
        hovermode="x unified",
    )
    figure.update_xaxes(type="category", title=None, showgrid=False)
    figure.update_yaxes(title=None, gridcolor=tokens.BORDER, zeroline=False)
    return figure


def _priority_figure(
    priority: pd.DataFrame,
    metric: MetricSpec,
    labels: ProcessLabels,
) -> go.Figure:
    """공정별 Gap 가로 막대. 색은 상태고 길이는 미달폭이다."""
    ordered = priority.iloc[::-1]
    names = [labels.label(value) for value in ordered["공정"]]
    figure = go.Figure(
        go.Bar(
            x=ordered["Gap"],
            y=names,
            orientation="h",
            marker={
                "color": [
                    STATUS_COLORS.get(str(status), tokens.BAR_TRACK) for status in ordered["상태"]
                ],
                "line": {"color": tokens.SURFACE, "width": 1},
            },
            text=[f"{value:.1%}{metric.gap_suffix}" for value in ordered["Gap"]],
            textposition="outside",
            # 막대가 0 에서 **왼쪽으로** 뻗으므로 바깥 라벨도 왼쪽으로 나간다. 축 밖으로
            # 나갈 수 있게 열어 두지 않으면 가장 긴 막대의 숫자가 잘린다.
            cliponaxis=False,
            customdata=ordered[["상태", "연속 미달"]],
            hovertemplate=(
                "%{y}<br>Gap %{x:.2%}<br>%{customdata[0]} · "
                "연속 미달 %{customdata[1]}개월<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        height=280,
        # 라벨이 나가는 쪽은 왼쪽이다. 여백을 오른쪽에 주면 잘린 채로 남는다.
        margin={"l": 56, "r": 16, "t": 8, "b": 8},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.CHART_CANVAS,
        font={"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": 12},
        showlegend=False,
    )
    figure.update_xaxes(title=None, gridcolor=tokens.BORDER, zeroline=True, tickformat=".0%")
    figure.update_yaxes(type="category", title=None, showgrid=False)
    return figure


def _gap_matrix_figure(
    view: pd.DataFrame,
    metric: MetricSpec,
    labels: ProcessLabels,
) -> go.Figure:
    """월 × 공정 Gap 격자. 미달과 초과가 한 눈금의 양끝이라 발산 색을 쓴다."""
    matrix = build_gap_table(view, metric, ["공정", "생산계획년월"])
    pivot = matrix.pivot(index="공정", columns="생산계획년월", values="Gap").sort_index()
    limit = float(pivot.abs().to_numpy().max() or 0.01)
    figure = go.Figure(
        go.Heatmap(
            z=pivot.to_numpy(),
            x=[month_label(int(value)) for value in pivot.columns],
            y=[labels.label(value) for value in pivot.index],
            colorscale=[
                [0.0, tokens.DELTA_INCREASE],
                [0.5, tokens.SURFACE],
                [1.0, tokens.DELTA_DECREASE],
            ],
            zmid=0.0,
            zmin=-limit,
            zmax=limit,
            xgap=1,
            ygap=1,
            hoverongaps=False,
            colorbar={"title": f"Gap ({metric.gap_unit})", "tickformat": ".1%"},
            hovertemplate="%{y} · %{x}<br>Gap %{z:.2%}<extra></extra>",
        )
    )
    figure.update_layout(
        height=max(240, len(pivot.index) * 34 + 90),
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        paper_bgcolor=tokens.CHART_CANVAS,
        plot_bgcolor=tokens.CHART_CANVAS,
        font={"color": tokens.TEXT, "family": tokens.FONT_FAMILY, "size": 12},
    )
    figure.update_xaxes(type="category", title=None, side="top")
    figure.update_yaxes(type="category", autorange="reversed", title=None)
    return figure
