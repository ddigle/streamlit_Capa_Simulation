# Purpose: 사용자가 고른 설비 질문·기준일·공정에 맞는 결과 하나를 표시한다.

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.components.equipment_lifecycle_gantt import (
    render_equipment_lifecycle_gantt,
)
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import tokens
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_inactive_equipment,
    build_inactive_equipment_in_month,
    inactive_equipment_moments,
)
from capa_simulation.services.equipment_contract import (
    DATE_COLUMNS,
    EQUIPMENT_STATUSES,
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
QUESTIONS = ("가용대수", "호기 현황", "비가동 호기", "Qual 일정")
_INACTIVE_COLUMNS = ("호기", "공정소분류", "상태", "입고일정", "Qual일정", "반출일정", "이설일")
_INACTIVE_MONTH_COLUMNS = ("호기", "비가동 시작", "비가동 종료", *_INACTIVE_COLUMNS[1:])


def render_equipment_period(*, today: date) -> tuple[date, date]:
    """Main 추이와 월별 비교가 함께 쓰는 조회기간 위젯."""
    start = st.date_input(
        "시작일",
        value=date(today.year, today.month, 1),
        key=START_DATE_KEY,
        persist_state="session",
        width=180,
    )
    end = st.date_input(
        "종료일",
        value=today + timedelta(weeks=12),
        key=END_DATE_KEY,
        persist_state="session",
        width=180,
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
    if UNIT_KEY_COLUMN not in frame.columns or not frame[UNIT_KEY_COLUMN].ne(frame["호기"]).any():
        return f"{rows:,}대"
    units = int(frame[UNIT_KEY_COLUMN].nunique())
    return f"호기 행 {rows:,} · 설비 {units:,}대" + ("에 걸침" if partial else "")


def _with_parent(columns: Sequence[str], frame: pd.DataFrame) -> list[str]:
    """모듈 행이 있을 때만 `호기` 옆에 `모체호기` 를 보인다. 비모듈 표에는 빈 칸만 늘어난다."""
    result = list(columns)
    if (
        PARENT_EQUIPMENT_COLUMN in frame.columns
        and frame[PARENT_EQUIPMENT_COLUMN].notna().any()
        and "호기" in result
    ):
        result.insert(result.index("호기") + 1, PARENT_EQUIPMENT_COLUMN)
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
    chart = (
        alt.Chart(long)
        .mark_bar()
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
    st.altair_chart(chart, width="stretch")
    st.caption(
        "각 주 일요일의 상태입니다. 기존 보유대수를 포함하며 환산비는 적용하지 않습니다. "
        "모체호기로 묶은 모듈 행은 합쳐 1대로 세고, 모듈 하나가 멈추면 그 몫만 비가동입니다."
    )


def render_equipment_explorer(
    *,
    baseline: pd.DataFrame,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    today: date,
    owner_tab: OpenTab | None = None,
) -> None:
    if tab_is_hidden(owner_tab):
        return
    with st.container(border=True):
        question = st.segmented_control(
            "볼 내용",
            QUESTIONS,
            default=QUESTIONS[0],
            required=True,
            key=QUESTION_KEY,
            persist_state="session",
        )
        view = ""
        with st.container(horizontal=True, gap="small"):
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
            process_options = sorted(
                set(_options(equipment, "공정소분류")) | set(_options(baseline, "공정"))
            )
            selected = st.multiselect(
                "공정소분류",
                process_options,
                placeholder="전체 공정 · 검색 가능",
                key=SMALL_PROCESS_KEY,
                persist_state="session",
                width=300,
            )
            uses_period = question == "가용대수" or view == "생애주기 일정"
            start = end = today
            as_of = today
            if uses_period:
                start, end = render_equipment_period(today=today)
            else:
                chosen = st.date_input(
                    "기준일", value=today, key=AS_OF_KEY, persist_state="session", width=180
                )
                assert isinstance(chosen, date)
                as_of = chosen
        with st.expander("추가 조건 · 라인 / 활용 / 공정대분류"):
            with st.container(horizontal=True, gap="small"):
                filters = [("공정소분류", selected)]
                for column, key in (
                    ("라인구분", LINE_TYPE_KEY),
                    ("활용구분", UTILIZATION_TYPE_KEY),
                    ("공정대분류", LARGE_PROCESS_KEY),
                ):
                    values = st.multiselect(
                        column,
                        _options(equipment, column),
                        placeholder="전체",
                        key=key,
                        persist_state="session",
                        width=240,
                    )
                    filters.append((column, values))
            st.caption(
                "기존 보유대수에는 공정소분류만 적용됩니다. 나머지 조건은 호기 마스터에 적용됩니다."
            )
        active_filters = [f"{name}: {', '.join(values)}" for name, values in filters if values]
        if active_filters:
            st.caption(" · ".join(active_filters))
        filtered = equipment
        for column, values in filters:
            if values:
                filtered = filtered.loc[filtered[column].isin(values)]
        filtered = filtered.copy()
        filtered_downtime = downtime.loc[downtime["호기"].isin(filtered["호기"])].copy()
        filtered_baseline = (
            baseline.loc[baseline["공정"].isin(selected)].copy() if selected else baseline
        )
        expression = "표"
        if view in ("주차별 추이", "상태 분포", "확정상태 분포"):
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
        if uses_period and start > end:
            st.error("시작일은 종료일보다 늦을 수 없습니다.")
            return
        try:
            if question == "가용대수":
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
                st.caption(
                    "선택한 기준일에 보유 중이지만 가용이 아닌 호기입니다. "
                    "달 전체는 보기에서 고릅니다."
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
                    st.caption(
                        "계획·확정·완료·지연을 관리합니다. 가용대수는 Qual일정으로 판정합니다."
                    )
                    column, states, colors = (
                        "확정상태",
                        QUAL_CONFIRMATION_STATUSES,
                        tokens.QUAL_CONFIRMATION_COLORS,
                    )
                    if view == "호기 목록":
                        _table(
                            status.sort_values(["Qual일정", "호기"]),
                            columns=_with_parent(
                                ["호기", "공정소분류", "Qual일정", "확정상태", "상태"], status
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
                                ["호기", "공정소분류", "상태", "입고일정", "Qual일정"], status
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
