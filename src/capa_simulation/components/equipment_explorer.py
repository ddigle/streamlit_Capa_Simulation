# Purpose: 사용자가 고른 설비 질문·기준일·공정에 맞는 결과 하나를 표시한다.

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Literal

import altair as alt
import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.equipment_lifecycle_gantt import (
    render_equipment_lifecycle_gantt,
)
from capa_simulation.components.status_metric import metric_row
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_inactive_equipment,
    build_inactive_equipment_in_month,
    build_milestone_transition_events,
    inactive_equipment_moments,
)
from capa_simulation.services.equipment_contract import (
    ARRIVAL_DATE_COLUMN,
    DATE_COLUMNS,
    EQUIPMENT_ID_COLUMN,
    EQUIPMENT_STATUSES,
    MILESTONES,
    PARENT_EQUIPMENT_COLUMN,
    QUAL_CONFIRMATION_STATUSES,
    STATUS_COUNT_COLUMNS,
)
from capa_simulation.services.equipment_units import (
    UNIT_COUNT_DECIMALS,
    UNIT_KEY_COLUMN,
    UNIT_SHARE_COLUMN,
    format_unit_count,
    static_unit_shares,
    unit_transitions,
)
from capa_simulation.services.simulation_cache import get_weekly_equipment_availability

QUESTION_KEY = "equipment_explorer_question"
AS_OF_KEY = "equipment_explorer_as_of"
INACTIVE_VIEW_KEY = "equipment_explorer_inactive_view"
START_DATE_KEY = "equipment_dashboard_start_date"
END_DATE_KEY = "equipment_dashboard_end_date"
SMALL_PROCESS_KEY = "equipment_dashboard_small_processes"
LINE_TYPE_KEY = "equipment_dashboard_line_types"
UTILIZATION_TYPE_KEY = "equipment_dashboard_utilization_types"
LARGE_PROCESS_KEY = "equipment_dashboard_large_processes"
TRANSITION_VIEW_KEY = "equipment_explorer_transition_view"
TRANSITION_STAGE_KEY = "equipment_transition_stage_filter"
TRANSITION_SCHEDULE_KEY = "equipment_transition_schedule_filter"
TRANSITION_CONFIRMATION_KEY = "equipment_transition_confirmation_filter"
QUESTIONS = ("가용대수", "호기 현황", "비가동 호기", "Qual 일정", "단계 전환")
TRANSITION_STAGES = tuple(label for _, label in MILESTONES)
_INACTIVE_COLUMNS = (
    EQUIPMENT_ID_COLUMN,
    "공정소분류",
    "상태",
    ARRIVAL_DATE_COLUMN,
    "Qual일정",
    "반출일정",
    "이설일",
)
_INACTIVE_MONTH_COLUMNS = (
    EQUIPMENT_ID_COLUMN,
    "비가동 시작",
    "비가동 종료",
    *_INACTIVE_COLUMNS[1:],
)


# 주차별 설비 현황의 막대 폭을 주 수와 잇는 실측값(1600px 창에서 17주일 때 막대 53px).
_WEEKLY_BAR_SPAN_PX = 903.0
# 단계 전환 차트의 막대 폭(px). 단계는 여섯이 전부라 폭을 두지 않으면 막대 하나가 400px 이
# 넘게 퍼져 둥근 머리가 보이지 않는다. HOME 생산계획 LOB 막대와 같은 70px 이다(좁은 창에서도
# 칸이 그보다 넓다).
_TRANSITION_BAR_SIZE_PX = 70


def render_equipment_period(
    *, today: date, width: int | Literal["stretch"] = 180
) -> tuple[date, date]:
    """Main 추이와 월별 비교가 함께 쓰는 조회기간 위젯. 사이드바 카드에서는 `width="stretch"`."""
    start = st.date_input(
        "시작일",
        value=date(today.year, today.month, 1),
        key=START_DATE_KEY,
        persist_state="session",
        width=width,
    )
    end = st.date_input(
        "종료일",
        value=today + timedelta(weeks=12),
        key=END_DATE_KEY,
        persist_state="session",
        width=width,
    )
    assert isinstance(start, date) and isinstance(end, date)
    return start, end


def _options(frame: pd.DataFrame, column: str) -> list[str]:
    return sorted(frame[column].dropna().astype(str).unique().tolist())


def _count(value: float) -> str:
    return format_unit_count(value)


def _rows_label(frame: pd.DataFrame, *, partial: bool = False) -> str:
    """표 제목의 대수. 모듈 행이 섞이면 행 수와 설비 수가 달라 둘 다 적는다.

    `partial` 은 행이 설비의 일부 모듈일 수 있는 표(비가동)다 — 모듈 하나가 멈춘 설비를
    「비가동 1대」로 읽히지 않게 「걸침」이라 적는다.
    """
    rows = len(frame)
    # 행 수와 설비 수가 같은지로 가르지 않는다. 설비마다 모듈 하나씩 멈춘 표는 둘이 같아도
    # 모듈 행이다 — 그것이 바로 「비가동 1대」로 읽히면 안 되는 경우다.
    if (
        UNIT_KEY_COLUMN not in frame.columns
        or not frame[UNIT_KEY_COLUMN].ne(frame[EQUIPMENT_ID_COLUMN]).any()
    ):
        return f"{rows:,}대"
    units = int(frame[UNIT_KEY_COLUMN].nunique())
    return f"호기 행 {rows:,} · 설비 {units:,}대" + ("에 걸침" if partial else "")


def _with_parent(columns: Sequence[str], frame: pd.DataFrame) -> list[str]:
    """모듈 행이 있을 때만 `설비명` 옆에 `Main 설비` 를 보인다. 비모듈 표에는 빈 칸만 늘어난다."""
    result = list(columns)
    if (
        PARENT_EQUIPMENT_COLUMN in frame.columns
        and frame[PARENT_EQUIPMENT_COLUMN].notna().any()
        and EQUIPMENT_ID_COLUMN in result
    ):
        result.insert(result.index(EQUIPMENT_ID_COLUMN) + 1, PARENT_EQUIPMENT_COLUMN)
    return result


def _table(frame: pd.DataFrame, *, columns: list[str] | None = None) -> None:
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_order=columns,
        column_config={
            column: st.column_config.DateColumn(format="YYYY-MM-DD")
            for column in (*DATE_COLUMNS, "비가동 시작", "비가동 종료")
            if column in frame.columns
        },
    )


def _count_chart(frame: pd.DataFrame, column: str, colors: dict[str, str]) -> None:
    chart = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            y=alt.Y(f"{column}:N", sort=list(colors), title=None),
            x=alt.X("설비대수:Q", title="설비 (대)", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color(
                f"{column}:N",
                scale=alt.Scale(domain=list(colors), range=list(colors.values())),
                legend=None,
            ),
            tooltip=[f"{column}:N", alt.Tooltip("설비대수:Q", format=",.2~f")],
        )
        .properties(height=max(160, len(colors) * 30))
    )
    st.altair_chart(chart, width="stretch")


def _availability(
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    start: date,
    end: date,
    view: str,
    expression: str,
) -> None:
    weekly = get_weekly_equipment_availability(
        baseline,
        equipment,
        downtime,
        start_date=start,
        end_date=end,
    )
    if weekly.empty:
        st.info("조건에 맞는 설비가 없습니다. 공정이나 조회기간을 바꿔 보세요.")
        return
    latest = weekly.loc[weekly["주차시작일"].eq(weekly["주차시작일"].max())]
    available = float(latest["가용대수"].sum())
    total = float(latest["총대수"].sum())
    inactive = float(latest["비가동대수"].sum())
    st.caption(
        f"마지막 주 {latest['Weeknum'].iloc[0]} · {latest['주차종료일'].max():%Y-%m-%d} 기준"
        f"　총 {_count(total)}대 · 가용 {_count(available)}대 · 비가동 {_count(inactive)}대"
        f" · 가용률 {available / total if total else 0:.1%}"
    )
    if view == "공정별 내역":
        st.markdown("#### 공정소분류별 현황")
        _table(
            latest.loc[
                :,
                [
                    "공정소분류",
                    "기존보유대수",
                    "추가설비대수",
                    "총대수",
                    "가용대수",
                    "비가동대수",
                    *STATUS_COUNT_COLUMNS.values(),
                ],
            ].sort_values(["비가동대수", "공정소분류"], ascending=[False, True])
        )
        return
    st.markdown("#### 주차별 설비 현황")
    trend = (
        weekly.groupby(["주차시작일", "Weeknum"], as_index=False)[["가용대수", "비가동대수"]]
        .sum()
        .sort_values("주차시작일")
    )
    if expression == "표":
        _table(trend)
        return
    long = trend.melt(
        id_vars=["주차시작일", "Weeknum"],
        value_vars=["가용대수", "비가동대수"],
        var_name="상태",
        value_name="대수",
    )
    # 막대 폭은 조회기간의 주 수로 정해진다(실측 17주에 53px — 폭 ≈ 903 / 주 수). 기간은
    # 사용자가 정하므로 반경 등급도 주 수로 고른다 — 한 해를 고르면 막대가 17px 로 가늘어진다.
    corner_radius = tokens.bar_corner_radius(_WEEKLY_BAR_SPAN_PX / max(len(trend), 1))
    chart = (
        alt.Chart(long)
        .mark_bar(cornerRadiusTopLeft=corner_radius, cornerRadiusTopRight=corner_radius)
        .encode(
            x=alt.X(
                "Weeknum:N", sort=trend["Weeknum"].tolist(), axis=alt.Axis(title=None, labelAngle=0)
            ),
            y=alt.Y("sum(대수):Q", stack="zero", title="설비 (대)"),
            color=alt.Color(
                "상태:N",
                scale=alt.Scale(
                    domain=["가용대수", "비가동대수"], range=[tokens.ACCENT, tokens.STATUS_WARNING]
                ),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=["Weeknum:N", "상태:N", alt.Tooltip("대수:Q", format=",.2~f")],
        )
        .properties(height=300)
    )
    # 읽는 법(각 주 일요일 상태, 환산비 미적용, Main 설비 묶음)은 가용설비 현황 Guide 가 말한다.
    st.altair_chart(chart, width="stretch")


def _transitions(
    equipment: pd.DataFrame,
    *,
    start: date,
    end: date,
    as_of: date,
    view: str,
    expression: str,
    stages: Sequence[str],
    schedule: str,
    confirmations: Sequence[str],
) -> None:
    """조회기간에 제진대·물류·입고·Qual·반출·이설 일정이 든 호기를 전환 한 건씩 편다.

    기준일 이전 일정은 **완료**, 이후는 **예정**이다(호기 마스터에 적힌 날과 기준일을 견준 결과).
    건수는 설비 단위다 — 모듈 행이 같은 날 같은 단계로 넘어가면 1건(`unit_transitions`).
    동·층·좌표를 보지 않고 걸러진 호기 마스터 전체를 본다.
    """
    events = build_milestone_transition_events(
        equipment, start_date=start, end_date=end, as_of=as_of
    )
    if stages and not events.empty:
        events = events.loc[events["전환단계"].isin(stages)]
    if schedule != "전체" and not events.empty:
        events = events.loc[events["일정상태"].eq(schedule)]
    if confirmations and not events.empty:
        events = events.loc[events["전환단계"].eq("Qual") & events["확정상태"].isin(confirmations)]
    st.markdown(f"#### 단계 전환 · {start:%Y-%m-%d} ~ {end:%Y-%m-%d} · 기준일 {as_of:%Y-%m-%d}")
    if events.empty:
        st.info("조건에 맞는 설비 단계 전환 일정이 없습니다. 기간이나 조건을 바꿔 보세요.")
        return
    if view == "전환 일정 목록":
        # 설비키는 모듈 행이 있을 때만 보인다. 비모듈 행은 호기와 같은 값이라 칸만 는다.
        has_modules = bool(events[UNIT_KEY_COLUMN].ne(events[EQUIPMENT_ID_COLUMN]).any())
        st.dataframe(
            events,
            hide_index=True,
            width="stretch",
            column_config={
                EQUIPMENT_ID_COLUMN: st.column_config.TextColumn(pinned=True),
                "전환일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                UNIT_KEY_COLUMN: st.column_config.TextColumn("설비") if has_modules else None,
            },
        )
        return
    unit_events = unit_transitions(events)
    with metric_row(key="equipment_transition_metrics"):
        st.metric("전환 일정", f"{len(unit_events):,}건", border=True)
        st.metric("대상 설비", f"{unit_events[UNIT_KEY_COLUMN].nunique():,}대", border=True)
        st.metric("완료", f"{int(unit_events['일정상태'].eq('완료').sum()):,}건", border=True)
        st.metric("예정", f"{int(unit_events['일정상태'].eq('예정').sum()):,}건", border=True)
        st.metric("Qual 확정·완료", f"{int(unit_events['Qual확정'].sum()):,}건", border=True)
    summary = (
        unit_events.groupby(["전환단계", "일정상태"], observed=True)
        .size()
        .rename("전환건수")
        .reset_index()
    )
    if expression == "표":
        _table(summary)
        return
    chart = (
        alt.Chart(summary)
        # 굵기가 넓음 등급이라 반경 8px. 쌓인 막대는 Vega-Lite 가 막대 전체를 잘라 둥글리므로
        # 이음매는 네모로 남는다(브라우저 실측).
        .mark_bar(
            size=_TRANSITION_BAR_SIZE_PX,
            cornerRadiusTopLeft=tokens.BAR_CORNER_RADIUS_WIDE_PX,
            cornerRadiusTopRight=tokens.BAR_CORNER_RADIUS_WIDE_PX,
        )
        .encode(
            x=alt.X(
                "전환단계:N",
                sort=list(TRANSITION_STAGES),
                axis=alt.Axis(title=None, labelAngle=0, labelFontSize=12),
            ),
            y=alt.Y("전환건수:Q", axis=alt.Axis(title=None, tickMinStep=1)),
            color=alt.Color(
                "일정상태:N",
                scale=alt.Scale(
                    domain=["완료", "예정"],
                    range=[tokens.SCHEDULE_DONE, tokens.SCHEDULE_PLANNED],
                ),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=["전환단계:N", "일정상태:N", "전환건수:Q"],
        )
        .properties(height=240)
    )
    st.altair_chart(chart, width="stretch")


def render_equipment_explorer(
    *,
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    today: date,
    owner_tab: OpenTab | None = None,
    conditions: DeltaGenerator | None = None,
) -> None:
    """Main 탭. 거르는 조건(공정·기간·기준일·추가 조건)은 `conditions`(사이드바 조건 카드)다.

    **무엇을 볼지 고르는 전환(볼 내용·보기·표현)은 본문이다.** 탭 안의 하위 탭과 같은 것이라
    카드에 넣으면 지금 무엇을 보는지 본문에서 사라진다(2026-09-29 사용자 결정). `conditions` 를
    주지 않으면 조건도 본문 상자에 그린다 — 컴포넌트를 홀로 띄우는 테스트가 쓴다. 설명은 가용설비
    현황 Guide 다.
    """
    if tab_is_hidden(owner_tab):
        return
    in_card = conditions is not None
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        question = st.segmented_control(
            "볼 내용",
            QUESTIONS,
            default=QUESTIONS[0],
            required=True,
            key=QUESTION_KEY,
            persist_state="session",
        )
        view = ""
        if question == "가용대수":
            view = st.selectbox(
                "보기",
                ["주차별 추이", "공정별 내역"],
                key="equipment_explorer_availability_view",
                persist_state="session",
                width=200,
            )
        elif question == "호기 현황":
            view = st.selectbox(
                "보기",
                ["상태 분포", "호기 목록", "생애주기 일정"],
                key="equipment_explorer_unit_view",
                persist_state="session",
                width=200,
            )
        elif question == "비가동 호기":
            view = st.selectbox(
                "보기",
                ["기준일 시점", "그 달 전체"],
                key=INACTIVE_VIEW_KEY,
                persist_state="session",
                width=200,
            )
        elif question == "Qual 일정":
            view = st.selectbox(
                "보기",
                ["호기 목록", "확정상태 분포"],
                key="equipment_explorer_qual_view",
                persist_state="session",
                width=200,
            )
        elif question == "단계 전환":
            view = st.selectbox(
                "보기",
                ["단계별 건수", "전환 일정 목록"],
                key=TRANSITION_VIEW_KEY,
                persist_state="session",
                width=200,
            )
        expression = "표"
        if view in ("주차별 추이", "상태 분포", "확정상태 분포", "단계별 건수"):
            expression = (
                st.segmented_control(
                    "표현",
                    ["차트", "표"],
                    default="차트",
                    required=True,
                    key=f"equipment_explorer_expression_{view}",
                    persist_state="session",
                )
                or "차트"
            )
    settings = conditions if conditions is not None else st.container(border=True)
    with settings:
        with st.container(horizontal=not in_card, gap="small"):
            process_options = sorted(
                set(_options(equipment, "공정소분류")) | set(_options(baseline, "공정"))
            )
            selected = st.multiselect(
                "공정소분류",
                process_options,
                placeholder="전체 공정 · 검색 가능",
                key=SMALL_PROCESS_KEY,
                persist_state="session",
                width="stretch" if in_card else 300,
            )
            uses_period = question in ("가용대수", "단계 전환") or view == "생애주기 일정"
            # 단계 전환은 기간과 기준일이 둘 다 든다 — 기간은 어느 일정을 모을지, 기준일은
            # 완료·예정을 가른다. 기준일 위젯은 다른 질문과 같은 것이다(질문을 옮겨도 그대로).
            uses_as_of = not uses_period or question == "단계 전환"
            start = end = today
            as_of = today
            if uses_period:
                start, end = render_equipment_period(
                    today=today, width="stretch" if in_card else 180
                )
            if uses_as_of:
                chosen = st.date_input(
                    "기준일",
                    value=today,
                    key=AS_OF_KEY,
                    persist_state="session",
                    width="stretch" if in_card else 180,
                )
                assert isinstance(chosen, date)
                as_of = chosen
        transition_stages: list[str] = []
        transition_schedule = "전체"
        transition_confirmations: list[str] = []
        if question == "단계 전환":
            with st.container(horizontal=not in_card, gap="small"):
                transition_stages = st.multiselect(
                    "전환단계",
                    list(TRANSITION_STAGES),
                    placeholder="전체",
                    key=TRANSITION_STAGE_KEY,
                    persist_state="session",
                    width="stretch" if in_card else 240,
                )
                transition_schedule = str(
                    st.selectbox(
                        "일정상태",
                        ("전체", "완료", "예정"),
                        key=TRANSITION_SCHEDULE_KEY,
                        persist_state="session",
                        width="stretch" if in_card else 140,
                    )
                )
                transition_confirmations = st.multiselect(
                    "Qual 확정상태",
                    list(QUAL_CONFIRMATION_STATUSES),
                    placeholder="전체",
                    key=TRANSITION_CONFIRMATION_KEY,
                    persist_state="session",
                    width="stretch" if in_card else 240,
                )
        # 카드 안에는 접는 틀을 한 겹 더 두지 않는다 — 카드가 이미 접힌다.
        extra = (
            st.container()
            if in_card
            else st.expander("추가 조건 · 공정구분 / 투자구분 / 공정대분류")
        )
        with extra:
            with st.container(horizontal=not in_card, gap="small"):
                filters = [("공정소분류", selected)]
                for column, key in (
                    ("공정구분", LINE_TYPE_KEY),
                    ("투자구분", UTILIZATION_TYPE_KEY),
                    ("공정대분류", LARGE_PROCESS_KEY),
                ):
                    values = st.multiselect(
                        column,
                        _options(equipment, column),
                        placeholder="전체",
                        key=key,
                        persist_state="session",
                        width="stretch" if in_card else 240,
                    )
                    filters.append((column, values))
    # 무엇으로 걸렀는지는 본문에도 한 줄 남긴다 — 카드가 접혀 있으면 표만 보고는 알 수 없다.
    active_filters = [f"{name}: {', '.join(values)}" for name, values in filters if values]
    if question == "단계 전환":
        active_filters += [
            f"{name}: {', '.join(values)}"
            for name, values in (
                ("전환단계", transition_stages),
                ("Qual 확정상태", transition_confirmations),
            )
            if values
        ]
        if transition_schedule != "전체":
            active_filters.append(f"일정상태: {transition_schedule}")
    if active_filters:
        st.caption(":material/filter_alt: " + " · ".join(active_filters))
    filtered = equipment
    for column, values in filters:
        if values:
            filtered = filtered.loc[filtered[column].isin(values)]
    filtered = filtered.copy()
    filtered_downtime = downtime.loc[
        downtime[EQUIPMENT_ID_COLUMN].isin(filtered[EQUIPMENT_ID_COLUMN])
    ].copy()
    filtered_baseline = (
        baseline.loc[baseline["공정"].isin(selected)].copy() if selected else baseline
    )
    with st.container(border=True):
        if uses_period and start > end:
            st.error("시작일은 종료일보다 늦을 수 없습니다.")
            return
        try:
            if question == "단계 전환":
                _transitions(
                    filtered,
                    start=start,
                    end=end,
                    as_of=as_of,
                    view=view,
                    expression=expression,
                    stages=transition_stages,
                    schedule=transition_schedule,
                    confirmations=transition_confirmations,
                )
            elif question == "가용대수":
                _availability(
                    filtered_baseline,
                    filtered,
                    filtered_downtime,
                    start=start,
                    end=end,
                    view=view,
                    expression=expression,
                )
            elif question == "비가동 호기" and view == "그 달 전체":
                # 기준일이 든 달을 본다. 기준 월을 따로 고르게 하면 축이 둘이 된다.
                moments = inactive_equipment_moments(filtered, filtered_downtime, month=as_of)
                inactive = build_inactive_equipment_in_month(
                    filtered, filtered_downtime, month=as_of, moments=moments
                )
                label = _rows_label(inactive, partial=True)
                st.markdown(f"#### 비가동 호기 · {as_of:%Y-%m} 달 전체 · {label}")
                st.caption(
                    "기준일이 든 달 안에서 한 번이라도 보유 중이면서 가용이 아니었던 "
                    f"호기입니다. 구간이 바뀌는 날 {len(moments)}개 시점을 다시 재어 "
                    "합칩니다 — 상태 이름으로 고르지 않습니다."
                )
                if inactive.empty:
                    st.success("기준일이 든 달과 조건에 비가동 호기가 없습니다.")
                else:
                    _table(inactive, columns=_with_parent(_INACTIVE_MONTH_COLUMNS, inactive))
            elif question == "비가동 호기":
                inactive = build_inactive_equipment(filtered, filtered_downtime, as_of=as_of)
                st.markdown(
                    f"#### 비가동 호기 · {as_of:%Y-%m-%d} · {_rows_label(inactive, partial=True)}"
                )
                if inactive.empty:
                    st.success("선택한 기준일과 조건에 비가동 호기가 없습니다.")
                else:
                    _table(inactive, columns=_with_parent(_INACTIVE_COLUMNS, inactive))
            elif view == "생애주기 일정":
                st.markdown("#### 호기별 생애주기 일정")
                spans = build_equipment_lifecycle_spans(
                    filtered, filtered_downtime, start_date=start, end_date=end
                )
                render_equipment_lifecycle_gantt(
                    spans, key="equipment_lifecycle_gantt", today=today, owner_tab=owner_tab
                )
            else:
                status = build_equipment_status_as_of(filtered, filtered_downtime, as_of=as_of)
                states: Sequence[str]
                # 분포는 행이 아니라 설비를 센다. 생애주기 상태는 그 시점 보유로 매긴 지분을,
                # Qual 은 보유와 상관없는 계획이라 고정 지분(1 ÷ 모듈 수)을 쓴다. 고정 지분은
                # Qual일정이 빈 형제까지 넣어 **거르기 전에** 매긴다.
                shares = status[UNIT_SHARE_COLUMN]
                if question == "Qual 일정":
                    shares = static_unit_shares(status[UNIT_KEY_COLUMN])
                    status = status.loc[status["Qual일정"].notna()].copy()
                    shares = shares.loc[status.index]
                    st.markdown(f"#### Qual 확정상태 실행관리 · {as_of:%Y-%m-%d}")
                    column, states, colors = (
                        "확정상태",
                        QUAL_CONFIRMATION_STATUSES,
                        tokens.QUAL_CONFIRMATION_COLORS,
                    )
                    if view == "호기 목록":
                        _table(
                            status.sort_values(["Qual일정", EQUIPMENT_ID_COLUMN]),
                            columns=_with_parent(
                                [EQUIPMENT_ID_COLUMN, "공정소분류", "Qual일정", "확정상태", "상태"],
                                status,
                            ),
                        )
                        return
                else:
                    st.markdown(f"#### 호기 생애주기 상태 · {as_of:%Y-%m-%d}")
                    st.caption(
                        f"호기 마스터 {_rows_label(status)} · 집계형 기존 보유대수는 제외됩니다."
                    )
                    column, states, colors = (
                        "상태",
                        EQUIPMENT_STATUSES,
                        tokens.EQUIPMENT_STAGE_COLORS,
                    )
                    if view == "호기 목록":
                        _table(
                            status,
                            columns=_with_parent(
                                [
                                    EQUIPMENT_ID_COLUMN,
                                    "공정소분류",
                                    "상태",
                                    ARRIVAL_DATE_COLUMN,
                                    "Qual일정",
                                ],
                                status,
                            ),
                        )
                        return
                counts = (
                    shares.groupby(status[column])
                    .sum()
                    .reindex(states, fill_value=0.0)
                    .round(UNIT_COUNT_DECIMALS)
                    .rename_axis(column)
                    .rename("설비대수")
                    .reset_index()
                )
                if expression == "표":
                    _table(counts)
                else:
                    _count_chart(counts, column, colors)
        except ValueError as exc:
            st.error(str(exc))
