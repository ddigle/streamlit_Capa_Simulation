# Purpose: 필요단축일정 탭의 조건·목표 선택과 공정 카드형 화면(KPI·LOB 요약·호기 타임라인)을 그린다.

"""필요단축일정 탭 — 시안 B 「공정 카드형」(2026-10-07 사용자 승인).

계산은 `services/required_shortening.py` 가 하고 결과는 `simulation_cache.get_required_shortening`
이 다섯 목표를 한 번에 캐시한다. 이 화면은 **고르기만** 한다 — 목표 확보율(본문 머리 줄)·공정
(조건 카드)을 바꾸는 rerun 은 계산을 다시 돌리지 않는다.

거르는 조건(시작 월·끝 월·공정)은 사이드바 `설비 조회 조건` 카드에, 무엇을 볼지(목표 확보율)는
본문 머리 줄에 둔다(2026-09-29 사용자 결정의 규칙 그대로). 공정을 고르지 않으면 **고른 목표에서
한 달이라도 모자란 공정 전체**를 카드로 보인다 — 공정 필터의 「미선택 시 전체」 관례를 「미선택 시
목표 미달 전체」로 읽는다. 목표를 바꾸면 카드 목록도 따라 바뀐다.

화면은 HOME 「Capa LOB Summary」 결의 HTML 이다(`st.html`). 색은 모두 `design/tokens` 에서 실행마다
읽어 밝은·어두운 테마를 따른다. 상태색(`STATUS_*`)은 면색이라 그 위 글자는 `TEXT` 다. 호기·공정
이름은 사용자가 적은 글이라 모두 이스케이프한다.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

import capa_simulation.persistence.cache as persistence_cache
import capa_simulation.services.simulation_cache as simulation_cache
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.components.typography import FIGURE_CLASS
from capa_simulation.design import tokens
from capa_simulation.home_state import HOME_TOGGLE_DEFAULTS, PAST_DATA_TOGGLE_KEY
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PageContext,
    prune_list_selection,
)
from capa_simulation.services.display_order import apply_display_order
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_SECUREMENT
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.month_filter import available_month_range
from capa_simulation.services.past_data import display_month_range
from capa_simulation.services.required_shortening import (
    DEFAULT_TARGET_LEVEL,
    KIND_NEW,
    STATUS_EXPIRED,
    STATUS_NEW_LIMIT,
    TARGET_LEVELS,
    LevelPlan,
    ShorteningPlan,
)
from capa_simulation.services.securement_threshold import (
    DEFAULT_SECURE_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    SecurementThresholds,
)
from capa_simulation.settings import DUCKDB_PATH

__all__ = [
    "SHORTENING_END_KEY",
    "SHORTENING_LEVEL_KEY",
    "SHORTENING_PROCESS_KEY",
    "SHORTENING_START_KEY",
    "render_required_shortening_tab",
]

SHORTENING_LEVEL_KEY = "equipment_shortening_level_v1"
SHORTENING_START_KEY = "equipment_shortening_start_month_v1"
SHORTENING_END_KEY = "equipment_shortening_end_month_v1"
SHORTENING_PROCESS_KEY = "equipment_shortening_process_filter_v1"
_UNITS_CSV_KEY = "equipment_shortening_units_csv"
_MONTHS_CSV_KEY = "equipment_shortening_months_csv"

# 표 첫 칸(행 이름)과 월 칸의 최소 폭. 달이 많으면 가로로 흐른다.
_LABEL_COLUMN_PX = 170
_MONTH_COLUMN_MIN_PX = 84
# 호기 줄: 이름 칸 · 타임라인 · 단축일수 칸.
_UNIT_NAME_PX = 210
_UNIT_RESULT_PX = 130
_TRACK_MIN_PX = 480
# 타임라인 위 달 이름의 최대 개수. 넘으면 몇 달씩 건너뛴다.
_MAX_AXIS_LABELS = 12


@dataclass(frozen=True)
class _LobRows:
    """`계획 · LOB 요약` 의 계획 두 줄. 못 읽으면 `error` 에 까닭을 둔다."""

    density: dict[int, float]
    wafer: dict[int, float]
    error: str | None = None


def render_required_shortening_tab(
    *,
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    baseline: pd.DataFrame,
    cutoff: pd.DataFrame,
    today: date,
    context: PageContext | None,
    required_equipment: pd.DataFrame | None,
    scenario_error: str | None = None,
    owner_tab: OpenTab | None = None,
    conditions: DeltaGenerator | None = None,
) -> None:
    """필요단축일정 탭 본문. 숨은 탭이면 아무것도 하지 않는다.

    조건 위젯 값은 숨은 동안 `persist_state` 가 지킨다.

    `context`·`required_equipment` 는 페이지가 활성 시나리오에서 읽어 넘긴다. 못 읽었으면
    `scenario_error` 에 까닭이 오고 **이 탭 안에서만** 알린다 — 다른 탭은 그대로 쓴다.
    """
    if tab_is_hidden(owner_tab):
        return
    controls: AbstractContextManager[object] = (
        conditions if conditions is not None else nullcontext()
    )
    level = _render_header(today)

    if scenario_error is not None or context is None or required_equipment is None:
        st.warning(
            "활성 시나리오의 소요대수를 읽지 못해 필요단축일정을 계산하지 않았습니다. "
            "다른 탭은 그대로 쓸 수 있습니다."
            + (f"\n\n{scenario_error}" if scenario_error else ""),
            icon=":material/sync_problem:",
        )
        return
    if cutoff.empty:
        st.info(
            "공정별 Cut-off 를 먼저 적어야 Dynamic 가용대수와 필요단축일정을 낼 수 있습니다 "
            "(Preference › Cut-off)."
        )
        return

    month_options = _month_options(context, required_equipment)
    if not month_options:
        st.info("조회기간에 월이 없습니다.")
        return
    with controls:
        months = _render_month_range(month_options)

    key = simulation_cache.required_shortening_cache_key(
        simulation_cache.scenario_cache_key(
            context.reference_version,
            context.active_scenario,
            context.selected_start_month,
            context.selected_end_month,
        ),
        equipment=equipment,
        downtime=downtime,
        baseline=baseline,
        cutoff=cutoff,
        months=tuple(months),
        today=today,
    )
    try:
        plan = simulation_cache.get_required_shortening(
            key, equipment, downtime, baseline, cutoff, required_equipment
        )
    except ValueError as exc:
        st.error(f"필요단축일정을 계산하지 못했습니다 — {exc}")
        return

    ordered = _ordered_processes(plan, context)
    prune_list_selection(SHORTENING_PROCESS_KEY, ordered)
    with controls:
        selected = st.multiselect(
            "공정 (표시순서)",
            options=ordered,
            placeholder="미선택 시 목표 미달 공정 전체",
            key=SHORTENING_PROCESS_KEY,
            persist_state="session",
        )
    level_plan = plan.at(level)
    scope = [process for process in ordered if process in set(selected)] if selected else ordered
    short = _short_processes(level_plan)
    shown = scope if selected else [process for process in ordered if process in short]

    _render_unmatched(plan)
    if not plan.processes:
        st.info(
            "시나리오 소요대수와 Dynamic 가용대수에 같은 이름으로 함께 있는 공정이 없습니다. "
            "Cut-off·호기 마스터의 공정소분류가 시나리오 공정명과 같은지 확인하세요."
        )
        return

    thresholds = _thresholds()
    st.html(_style())
    st.html(_kpi_markup(level_plan, level, scope, short, selected=bool(selected)))
    _render_downloads(level_plan, scope, level, months)
    st.html(
        _lob_markup(
            months,
            _lob_rows(context, months),
            level_plan,
            scope,
            thresholds,
        )
    )
    st.caption(
        ":material/info: Density·Wafer 는 HOME 과 같은 계산(EDP 포함)입니다. B/N 확보율은 보이는 "
        "범위 공정 가운데 **Dynamic 가용(환산) ÷ 소요** 가 가장 낮은 값이라 HOME 의 Static B/N 과 "
        "다릅니다."
    )
    if not shown:
        st.success(
            f"목표 {_percent(level)} 에서 모자란 달이 있는 공정이 없습니다. "
            "다른 목표를 고르거나 조건 카드에서 공정을 골라 보세요.",
            icon=":material/check_circle:",
        )
        return
    for process in shown:
        st.html(
            _card_markup(
                process,
                plan.cutoff_days.get(process, 0),
                level_plan,
                months,
                level,
                thresholds,
                plan.today,
            )
        )


# ------------------------------------------------------------------ 위젯


def _render_header(today: date) -> float:
    """제목과 오른쪽 `목표 확보율`. 제목 옆에 두므로 가로 컨테이너가 아니라 컬럼이다(AGENTS 9장)."""
    if SHORTENING_LEVEL_KEY not in st.session_state:
        st.session_state[SHORTENING_LEVEL_KEY] = DEFAULT_TARGET_LEVEL
    title, picker = st.columns([4, 1], vertical_alignment="bottom")
    with title:
        st.markdown("#### :material/event_upcoming: 필요단축일정")
        st.caption(
            "목표 확보율에 모자란 달을 채우려면 신규 호기 Qual 을 며칠 당겨야 하는지 — "
            f"Dynamic 가용(환산) 기준 · 오늘 {today:%Y-%m-%d}"
        )
    with picker:
        level = st.selectbox(
            "목표 확보율",
            options=list(TARGET_LEVELS),
            format_func=_percent,
            key=SHORTENING_LEVEL_KEY,
            persist_state="session",
        )
    return float(level)


def _render_month_range(options: list[int]) -> list[int]:
    """시작 월·끝 월. 기본은 사이드바 조회기간 전체이고 그 안에서만 고른다.

    소요대수를 그 기간으로 받기 때문이다.
    """
    for key, fallback in ((SHORTENING_START_KEY, options[0]), (SHORTENING_END_KEY, options[-1])):
        # 조회기간이 바뀌어 옛 값이 옵션에 없으면 **새 값을 적는다**(pop 하면 브라우저가 옛 선택을
        # 계속 보인다 — AGENTS 9장).
        if st.session_state.get(key) not in options:
            st.session_state[key] = fallback
    start_column, end_column = st.columns(2)
    with start_column:
        start = st.selectbox(
            "시작 월",
            options=options,
            format_func=month_label,
            key=SHORTENING_START_KEY,
            persist_state="session",
        )
    with end_column:
        end = st.selectbox(
            "끝 월",
            options=options,
            format_func=month_label,
            key=SHORTENING_END_KEY,
            persist_state="session",
        )
    first, last = sorted((int(start), int(end)))
    if int(start) > int(end):
        st.caption("시작 월이 끝 월보다 늦어 바꿔 읽었습니다.")
    return [month for month in options if first <= month <= last]


def _render_unmatched(plan: ShorteningPlan) -> None:
    """맞대지 못한 공정은 비교하지 않고 이름만 알린다.

    조용히 빠지면 부족이 이유 없이 작아 보인다.
    """
    groups = [
        ("시나리오에만 있는 공정", plan.required_only),
        ("설비(Dynamic)에만 있는 공정", plan.availability_only),
    ]
    if not any(names for _, names in groups):
        return
    parts = [f"{label} {len(names)}개" for label, names in groups if names]
    if plan.missing_cutoff:
        parts.append(f"그 가운데 Cut-off 미기재 {len(plan.missing_cutoff)}개")
    with st.expander(":material/link_off: 맞대지 못한 공정 — " + " · ".join(parts)):
        st.caption(
            "호기 마스터 `공정소분류` 와 시나리오 `공정` 이 같은 이름일 때만 맞댑니다. "
            "Cut-off 를 적지 않은 공정은 Dynamic 가용을 낼 수 없어 시나리오 쪽에만 남습니다."
        )
        for label, names in (*groups, ("Cut-off 미기재", plan.missing_cutoff)):
            if names:
                st.text(f"{label}: " + ", ".join(names))


def _render_downloads(
    level_plan: LevelPlan, scope: Sequence[str], level: float, months: Sequence[int]
) -> None:
    span = f"{months[0]}_{months[-1]}" if months else "empty"
    percent = round(level * 100)
    units = level_plan.units.loc[level_plan.units["공정"].isin(list(scope))]
    process_months = level_plan.process_months.loc[
        level_plan.process_months["공정"].isin(list(scope))
        & level_plan.process_months["생산계획년월"].isin(list(months))
    ]
    with st.container(horizontal=True, gap="small"):
        render_csv_download(
            data=units.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8-sig"),
            file_name=f"required_shortening_units_{percent}pct_{span}.csv",
            key=_UNITS_CSV_KEY,
            label="호기 단축 CSV",
        )
        render_csv_download(
            data=process_months.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"required_shortening_process_months_{percent}pct_{span}.csv",
            key=_MONTHS_CSV_KEY,
            label="공정·월 CSV",
        )


# ------------------------------------------------------------------ 데이터 고르기


def _months_between(start: int, end: int) -> list[int]:
    if start > end:
        return []
    months: list[int] = []
    year, month = divmod(start, 100)
    while year * 100 + month <= end:
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _month_options(context: PageContext, required_equipment: pd.DataFrame) -> list[int]:
    """고를 수 있는 달 — 사이드바 조회기간 가운데 소요대수가 있는 범위(HOME 「적용」 범위)."""
    start, end = context.selected_start_month, context.selected_end_month
    if not required_equipment.empty and "생산계획년월" in required_equipment.columns:
        present = pd.to_numeric(required_equipment["생산계획년월"], errors="coerce").dropna()
        if not present.empty:
            start, end = max(start, int(present.min())), min(end, int(present.max()))
    return _months_between(start, end)


def _ordered_processes(plan: ShorteningPlan, context: PageContext) -> list[str]:
    """맞댄 공정을 확보율 표와 같은 공용 표시순서로. 규칙이 깨져 있으면 이름순이다."""
    names = list(plan.processes)
    try:
        ordered = apply_display_order(
            pd.DataFrame({"공정": names}),
            context.reference_tables["RQ_DISPLAY_ORDER"],
            PAGE_CALCULATION,
            TAB_SECUREMENT,
        )
    except (KeyError, ValueError):
        return names
    return [str(name) for name in ordered["공정"]]


def _short_processes(level_plan: LevelPlan) -> set[str]:
    frame = level_plan.process_months
    if frame.empty:
        return set()
    return {str(name) for name in frame.loc[frame["과부족"].lt(0), "공정"]}


def _thresholds() -> SecurementThresholds:
    """확보·경고·부족 칩의 판정 기준. HOME 과 같은 공용 기준이다(못 읽으면 코드 기본값)."""
    try:
        profile = persistence_cache.load_global_securement_threshold(str(DUCKDB_PATH.resolve()))
    except BOOTSTRAP_ERRORS:
        return SecurementThresholds(DEFAULT_SECURE_THRESHOLD, DEFAULT_WARNING_THRESHOLD)
    return profile.thresholds


def _lob_rows(context: PageContext, months: Sequence[int]) -> _LobRows:
    """Density·Wafer 계획. HOME 과 **같은 캐시 키**로 부른다.

    키의 달은 HOME 과 같은 함수(`past_data.display_month_range`)로 낸다 — 조회기간 ∩ 계산 원천
    범위를 **과거 구간(Past Data) 달까지 넓힌** 범위이고, 과거 구간을 넣을지는 HOME 의 `Past Data
    포함` 토글 값을 그대로 따른다. 그래야 HOME 을 본 뒤에는 다시 계산하지 않는다.
    """
    try:
        source = available_month_range(context.reference_tables["RQ_PKG_PLAN"], "RQ_PKG_PLAN")
        include_past = bool(
            st.session_state.get(PAST_DATA_TOGGLE_KEY, HOME_TOGGLE_DEFAULTS[PAST_DATA_TOGGLE_KEY])
        )
        past_months = (
            [
                int(month)
                for month in persistence_cache.load_global_past_data(
                    str(DUCKDB_PATH.resolve())
                ).monthly["생산계획년월"]
            ]
            if include_past
            else []
        )
        display_range = display_month_range(
            (context.selected_start_month, context.selected_end_month), source, past_months
        )
        if display_range.empty:
            return _LobRows({}, {}, "조회기간에 생산계획이 없습니다.")
        home_key = simulation_cache.build_home_simulation_cache_key(
            reference_version=context.reference_version,
            scenario_token=str(context.active_scenario["content_token"]),
            start_month=display_range.start,
            end_month=display_range.end,
            display_order=context.reference_tables["RQ_DISPLAY_ORDER"],
        )
        density, _, wafer, *_ = simulation_cache.get_home_simulation(
            cache_key=home_key,
            _tables=context.active_scenario["tables"],
            _display_order=context.reference_tables["RQ_DISPLAY_ORDER"],
            _reference_tables=context.reference_tables,
        )
    except BOOTSTRAP_ERRORS as exc:
        return _LobRows({}, {}, str(exc))
    wanted = set(months)
    return _LobRows(
        density=_month_values(density, "부하량", wanted),
        wafer=_month_values(wafer, "Wafer 부하량", wanted),
    )


def _month_values(frame: pd.DataFrame, column: str, wanted: set[int]) -> dict[int, float]:
    if frame.empty or column not in frame.columns:
        return {}
    values: dict[int, float] = {}
    for month, value in zip(frame["생산계획년월"], frame[column], strict=True):
        if pd.notna(month) and int(month) in wanted and pd.notna(value):
            values[int(month)] = float(value)
    return values


# ------------------------------------------------------------------ 글자 모양


def _percent(level: float) -> str:
    return f"{round(level * 100)}%"


def _short_date(day: date) -> str:
    return f"{day:%y.%m.%d}"


def _signed(value: float) -> str:
    return ("+" if value >= 0 else "−") + f"{abs(value):,.2f}"


def _whole(value: object) -> int | None:
    """표 칸의 정수. 빈칸(`pd.NA`·NaN·None)이면 None 이다."""
    number = pd.to_numeric(pd.Series([value], dtype="object"), errors="coerce").iloc[0]
    return None if pd.isna(number) else int(number)


def _escape(text: object) -> str:
    return html.escape(str(text))


def _status_color(rate: float, month: int, thresholds: SecurementThresholds) -> str:
    # 상태 → 색 짝은 함수 안에서 만든다. 모듈 상수로 두면 처음 임포트한 순간의 팔레트가 굳는다.
    return {
        "secure": tokens.STATUS_SECURE,
        "warning": tokens.STATUS_WARNING,
        "shortage": tokens.STATUS_SHORTAGE,
    }[thresholds.status(rate, month)]


def _rate_chip(rate: float, month: int, thresholds: SecurementThresholds) -> str:
    if pd.isna(rate):
        return '<span class="shk-muted">—</span>'
    color = _status_color(rate, month, thresholds)
    return (
        f'<span class="shk-chip {FIGURE_CLASS}" style="background:{color}">'
        f"{round(rate * 100):,}%</span>"
    )


def _style() -> str:
    """이 탭의 서식. 색은 지금 테마의 토큰이라 실행마다 만든다."""
    display = tokens.FONT_FAMILY_DISPLAY
    return f"""
<style>
.shk-kpis {{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.shk-kpi {{background:{tokens.SURFACE};border:1px solid {tokens.BORDER};border-radius:10px;
  padding:14px 16px;display:flex;flex-direction:column;gap:4px;color:{tokens.TEXT}}}
.shk-kpi-label {{font-size:12px;color:{tokens.TEXT_MUTED}}}
.shk-kpi-value {{font-family:{display};font-weight:800;font-size:28px;line-height:1.15;
  font-variant-numeric:tabular-nums}}
.shk-kpi-note {{font-size:11.5px;color:{tokens.TEXT_MUTED}}}
.shk-panel {{background:{tokens.SURFACE};border:1px solid {tokens.BORDER};border-radius:10px;
  padding:14px 18px;display:flex;flex-direction:column;gap:10px;color:{tokens.TEXT}}}
.shk-title {{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:700;
  font-family:{display}}}
.shk-title::before {{content:"";width:4px;height:18px;border-radius:2px;background:{tokens.ACCENT}}}
.shk-scroll {{overflow-x:auto}}
.shk-grid {{display:grid;font-size:13px;font-variant-numeric:tabular-nums}}
.shk-grid > div {{padding:6px 4px;border-top:1px solid {tokens.BORDER};text-align:center;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px}}
.shk-grid > div.shk-head {{border-top:none;background:{tokens.SURFACE_CLASSIFICATION};
  font-family:{display};font-weight:700}}
.shk-grid > div.shk-row {{align-items:flex-start;text-align:left;font-weight:600}}
.shk-grid > div.shk-row-muted {{align-items:flex-start;text-align:left;color:{tokens.TEXT_MUTED}}}
.shk-num {{font-family:{display};font-weight:700;font-size:14px}}
.shk-sub {{font-size:10.5px;color:{tokens.TEXT_MUTED};white-space:nowrap}}
.shk-muted {{color:{tokens.TEXT_MUTED}}}
.shk-chip {{font-weight:700;font-size:12.5px;padding:2px 8px;border-radius:999px;
  color:{tokens.TEXT};font-variant-numeric:tabular-nums}}
.shk-short {{background:{tokens.STATUS_SHORTAGE};color:{tokens.TEXT};border-radius:6px;
  padding:0 6px}}
.shk-card {{background:{tokens.SURFACE};border:1px solid {tokens.BORDER};border-radius:12px;
  overflow:hidden;display:flex;flex-direction:column;color:{tokens.TEXT}}}
.shk-card-head {{display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:12px 18px;background:{tokens.SURFACE_CLASSIFICATION};border-bottom:1px solid
  {tokens.BORDER};flex-wrap:wrap}}
.shk-card-name {{font-family:{display};font-weight:800;font-size:20px;margin-right:10px}}
.shk-card-cutoff {{font-size:12px;color:{tokens.TEXT_MUTED}}}
.shk-badge {{font-size:12.5px;font-weight:700;border-radius:999px;padding:4px 12px;
  color:{tokens.TEXT}}}
.shk-card-body {{padding:8px 18px 4px}}
.shk-units {{padding:10px 18px 16px;display:flex;flex-direction:column;gap:6px}}
.shk-units-legend {{font-size:12px;color:{tokens.TEXT_MUTED}}}
.shk-unit {{display:grid;grid-template-columns:{_UNIT_NAME_PX}px minmax({_TRACK_MIN_PX}px,1fr)
  {_UNIT_RESULT_PX}px;align-items:center;gap:10px;background:{tokens.SURFACE_SUBTLE};
  border:1px solid {tokens.BORDER};border-radius:8px;padding:6px 10px}}
.shk-unit-axis {{background:none;border:none;padding:0 10px}}
.shk-unit-name {{font-weight:700;font-size:13.5px;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}}
.shk-unit-dates {{font-size:11.5px;color:{tokens.TEXT_MUTED};white-space:nowrap}}
.shk-track {{position:relative;height:30px}}
.shk-axis {{position:relative;height:16px;font-size:10.5px;color:{tokens.TEXT_MUTED}}}
.shk-grid-line {{position:absolute;top:0;bottom:0;width:1px;background:{tokens.BORDER}}}
.shk-today {{position:absolute;top:0;bottom:0;width:0;border-left:1px dashed {tokens.TEXT_MUTED}}}
.shk-result {{text-align:right;display:flex;flex-direction:column;gap:1px}}
.shk-cut {{font-family:{display};font-weight:800;font-size:16px;color:{tokens.ACCENT}}}
.shk-new {{align-self:flex-end;font-weight:700;font-size:12.5px;border-radius:999px;
  padding:1px 10px;background:{tokens.STATUS_SHORTAGE};color:{tokens.TEXT}}}
.shk-gain {{font-size:11.5px;color:{tokens.TEXT_MUTED}}}
.shk-empty {{font-size:12.5px;color:{tokens.TEXT_MUTED};padding:6px 2px}}
</style>
"""


# ------------------------------------------------------------------ KPI


def _kpi_markup(
    level_plan: LevelPlan,
    level: float,
    scope: Sequence[str],
    short: set[str],
    *,
    selected: bool,
) -> str:
    units = level_plan.units.loc[level_plan.units["공정"].isin(list(scope))]
    moved = units.loc[units["구분"].ne(KIND_NEW)]
    new = units.loc[units["구분"].eq(KIND_NEW)]
    days = pd.to_numeric(moved["단축일수"], errors="coerce")
    longest = int(days.max()) if not days.dropna().empty else 0
    short_count = sum(1 for process in scope if process in short)
    tiles = (
        (
            "부족 공정",
            f"{short_count} / {len(scope)}",
            f"목표 {_percent(level)} 기준, 한 달이라도 모자란 공정"
            + (" (고른 공정 중)" if selected else " (맞댄 공정 중)"),
        ),
        ("단축 대상 호기", f"{len(moved)}대", "Qual 이른 순 → 호기 번호 순으로 당긴 호기"),
        ("최대 단축", f"{longest}일", "한 호기가 당겨야 하는 가장 긴 날수"),
        ("신규 필요", f"{len(new)}대", "단축만으로 못 채워 새로 들일 대수(추가N)"),
    )
    cells = "".join(
        f'<div class="shk-kpi"><span class="shk-kpi-label">{_escape(label)}</span>'
        f'<span class="shk-kpi-value">{_escape(value)}</span>'
        f'<span class="shk-kpi-note">{_escape(note)}</span></div>'
        for label, value, note in tiles
    )
    return f'<div class="shk-kpis" role="group" aria-label="필요단축일정 요약">{cells}</div>'


# ------------------------------------------------------------------ LOB 요약


def _grid_style(months: Sequence[int]) -> str:
    count = max(len(months), 1)
    return (
        f"grid-template-columns:{_LABEL_COLUMN_PX}px repeat({count},"
        f"minmax({_MONTH_COLUMN_MIN_PX}px,1fr));"
        f"min-width:{_LABEL_COLUMN_PX + count * _MONTH_COLUMN_MIN_PX}px"
    )


def _month_header(months: Sequence[int], first: str = "월") -> str:
    head = f'<div class="shk-head shk-row-muted">{_escape(first)}</div>'
    return head + "".join(f'<div class="shk-head">{month_label(month)}</div>' for month in months)


def _bottleneck(frame: pd.DataFrame, month: int, column: str) -> tuple[float, str] | None:
    rows = frame.loc[frame["생산계획년월"].eq(month) & frame["소요대수"].gt(0)]
    if rows.empty:
        return None
    rates = rows[column] / rows["소요대수"]
    position = int(rates.to_numpy().argmin())
    return float(rates.iloc[position]), str(rows["공정"].iloc[position])


def _lob_markup(
    months: Sequence[int],
    lob: _LobRows,
    level_plan: LevelPlan,
    scope: Sequence[str],
    thresholds: SecurementThresholds,
) -> str:
    frame = level_plan.process_months.loc[level_plan.process_months["공정"].isin(list(scope))]
    rows = [_month_header(months)]
    rows.append('<div class="shk-row-muted">Density (억Gb)</div>')
    rows.extend(
        f'<div><span class="shk-num">{lob.density[month]:,.2f}</span></div>'
        if month in lob.density
        else '<div><span class="shk-muted">—</span></div>'
        for month in months
    )
    rows.append('<div class="shk-row-muted">Wafer 계획</div>')
    rows.extend(
        f'<div><span class="shk-num">{lob.wafer[month] / 1_000:,.0f}K</span></div>'
        if month in lob.wafer
        else '<div><span class="shk-muted">—</span></div>'
        for month in months
    )
    for label, column in (
        ("Dynamic B/N 확보율 현재", "가용대수"),
        ("Dynamic B/N 확보율 단축 후", "단축후가용대수"),
    ):
        rows.append(f'<div class="shk-row-muted">{label}</div>')
        for month in months:
            found = _bottleneck(frame, month, column)
            if found is None:
                rows.append('<div><span class="shk-muted">—</span></div>')
                continue
            rate, process = found
            rows.append(
                f"<div>{_rate_chip(rate, month, thresholds)}"
                f'<span class="shk-sub" title="{_escape(process)}">{_escape(process)}</span></div>'
            )
    error = (
        f'<div class="shk-sub">계획 값을 읽지 못했습니다 — {_escape(lob.error)}</div>'
        if lob.error
        else ""
    )
    return (
        '<section class="shk-panel" aria-label="계획 · LOB 요약">'
        '<div class="shk-title" role="heading" aria-level="2">계획 · LOB 요약</div>'
        f'<div class="shk-scroll"><div class="shk-grid" style="{_grid_style(months)}">'
        + "".join(rows)
        + f"</div></div>{error}</section>"
    )


# ------------------------------------------------------------------ 공정 카드


def _card_markup(
    process: str,
    cutoff_days: int,
    level_plan: LevelPlan,
    months: Sequence[int],
    level: float,
    thresholds: SecurementThresholds,
    today: date,
) -> str:
    frame = level_plan.process_months
    rows = frame.loc[frame["공정"].eq(process) & frame["생산계획년월"].isin(list(months))]
    by_month = {
        int(str(row["생산계획년월"])): {str(key): value for key, value in row.items()}
        for row in rows.to_dict("records")
    }
    units = level_plan.units.loc[level_plan.units["공정"].eq(process)]
    moved = units.loc[units["구분"].ne(KIND_NEW)]
    new = units.loc[units["구분"].eq(KIND_NEW)]
    worst = min((float(row["과부족"]) for row in by_month.values()), default=0.0)
    if worst < 0:
        badge = (
            f'<span class="shk-badge" style="background:{tokens.STATUS_SHORTAGE}">'
            f"최대 부족 {abs(worst):,.2f}대 · 단축 {len(moved)}대 · 신규 {len(new)}대</span>"
        )
    else:
        badge = (
            f'<span class="shk-badge" style="background:{tokens.STATUS_SECURE}">목표 충족</span>'
        )
    table = _card_table(by_month, months, level, thresholds)
    timeline = _units_markup(units, months, today=today, short=worst < 0)
    return (
        f'<section class="shk-card" aria-label="{_escape(process)}">'
        '<div class="shk-card-head"><div>'
        f'<span class="shk-card-name">{_escape(process)}</span>'
        f'<span class="shk-card-cutoff">Cut-off {cutoff_days}일</span></div>{badge}</div>'
        f'<div class="shk-card-body shk-scroll">{table}</div>{timeline}</section>'
    )


def _card_table(
    by_month: dict[int, dict[str, object]],
    months: Sequence[int],
    level: float,
    thresholds: SecurementThresholds,
) -> str:
    cells = [_month_header(months, first="")]
    cells.append('<div class="shk-row">가용대수</div>')
    for month in months:
        row = by_month.get(month)
        if row is None:
            cells.append('<div><span class="shk-muted">—</span></div>')
            continue
        before, after = float(str(row["가용대수"])), float(str(row["단축후가용대수"]))
        sub = f"→ {after:,.2f}" if round(after - before, 6) != 0 else ""
        cells.append(
            f'<div><span class="shk-num">{before:,.2f}</span>'
            f'<span class="shk-sub">{sub}</span></div>'
        )
    cells.append('<div class="shk-row">소요대수</div>')
    for month in months:
        row = by_month.get(month)
        value = "—" if row is None else f"{float(str(row['소요대수'])):,.2f}"
        cells.append(f'<div><span class="shk-num">{value}</span></div>')
    cells.append('<div class="shk-row">확보율</div>')
    for month in months:
        row = by_month.get(month)
        rate = float("nan") if row is None else float(str(row["확보율"]))
        cells.append(f"<div>{_rate_chip(rate, month, thresholds)}</div>")
    cells.append(f'<div class="shk-row">과부족 (목표 {_percent(level)})</div>')
    for month in months:
        row = by_month.get(month)
        if row is None:
            cells.append('<div><span class="shk-muted">—</span></div>')
            continue
        gap, after_gap = float(str(row["과부족"])), float(str(row["단축후과부족"]))
        status = str(row["상태"])
        if gap < 0:
            note = f"→ {_signed(after_gap)}"
            if status in (STATUS_EXPIRED, STATUS_NEW_LIMIT):
                note += " · " + ("기한 지남" if status == STATUS_EXPIRED else "남은 날 부족")
            cells.append(
                f'<div title="{_escape(status)}"><span class="shk-num shk-short">'
                f'{_signed(gap)}</span><span class="shk-sub">{_escape(note)}</span></div>'
            )
        else:
            cells.append(f'<div><span class="shk-num">{_signed(gap)}</span></div>')
    return f'<div class="shk-grid" style="{_grid_style(months)}">{"".join(cells)}</div>'


def _axis(months: Sequence[int]) -> tuple[date, date]:
    first = date(months[0] // 100, months[0] % 100, 1)
    year, month = divmod(months[-1], 100)
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, following


def _position(day: date, axis: tuple[date, date]) -> float:
    span = (axis[1] - axis[0]).days
    return min(100.0, max(0.0, (day - axis[0]).days / span * 100))


def _grid_lines(months: Sequence[int], axis: tuple[date, date]) -> str:
    lines = []
    for month in months[1:]:
        start = date(month // 100, month % 100, 1)
        lines.append(
            f'<span class="shk-grid-line" style="left:{_position(start, axis):.3f}%"></span>'
        )
    return "".join(lines)


def _units_markup(
    units: pd.DataFrame,
    months: Sequence[int],
    *,
    today: date,
    short: bool,
) -> str:
    if not months:
        return ""
    axis = _axis(months)
    lines = _grid_lines(months, axis)
    today_mark = (
        f'<span class="shk-today" title="오늘" style="left:{_position(today, axis):.3f}%"></span>'
        if axis[0] <= today < axis[1]
        else ""
    )
    legend = (
        '<div class="shk-units-legend">호기별 단축 — ● 기존 Qual · ◀ 목표 Qual · '
        "◌ 신규 필요 Qual · 칸은 달</div>"
    )
    if units.empty:
        message = (
            "부족한 달이 모두 지난 구간이라 당길 수 있는 호기가 없습니다."
            if short
            else "이 목표에서는 부족한 달이 없어 단축할 호기가 없습니다."
        )
        return f'<div class="shk-units">{legend}<div class="shk-empty">{message}</div></div>'
    # 달이 많으면 이름은 건너뛰며 적는다(격자선은 달마다 그대로). 글자가 서로 겹치지 않게 열둘 남짓.
    step = max(1, -(-len(months) // _MAX_AXIS_LABELS))
    labels = "".join(
        f'<span style="position:absolute;left:{_position(date(m // 100, m % 100, 1), axis):.3f}%;'
        f'padding-left:3px">{month_label(m)}</span>'
        for m in months[::step]
    )
    rows = [
        '<div class="shk-unit shk-unit-axis" aria-hidden="true"><span></span>'
        f'<div class="shk-axis">{labels}</div><span></span></div>'
    ]
    for row in units.to_dict("records"):
        rows.append(_unit_row({str(k): v for k, v in row.items()}, axis, lines + today_mark))
    return (
        f'<div class="shk-units">{legend}<div class="shk-scroll"><div style="min-width:'
        f"{_UNIT_NAME_PX + _TRACK_MIN_PX + _UNIT_RESULT_PX + 60}px;display:flex;"
        f'flex-direction:column;gap:4px">{"".join(rows)}</div></div></div>'
    )


def _unit_row(row: dict[str, object], axis: tuple[date, date], lines: str) -> str:
    name = _escape(row["호기"])
    target = row["목표 Qual"]
    assert isinstance(target, date)
    start = target + timedelta(days=1)
    gain = f"+{float(str(row['늘어난 환산대수'])):,.2f}대"
    modules = _whole(row["모듈 수"]) or 1
    module_note = f" · 모듈 {modules}" if modules > 1 else ""
    left = _position(target, axis)
    if row["구분"] == KIND_NEW:
        dates = f"신규 필요 Qual {_short_date(target)} (기여 {_short_date(start)})"
        # 부족 면색을 채우고 점선 테두리는 글자색이다 — 어두운 테마의 부족색(#8F0040)은 선으로만
        # 그리면 바탕에 묻힌다(2026-10-07 브라우저 확인).
        marks = (
            f'<span style="position:absolute;top:7px;left:calc({left:.3f}% - 8px);width:16px;'
            f"height:16px;border-radius:50%;border:2px dashed {tokens.TEXT};"
            f'background:{tokens.STATUS_SHORTAGE};box-sizing:border-box"></span>'
        )
        result = f'<span class="shk-new">신규</span><span class="shk-gain">{gain}</span>'
    else:
        original = row["기존 Qual"]
        assert isinstance(original, date)
        right = _position(original, axis)
        dates = f"{_short_date(original)} → {_short_date(target)} (기여 {_short_date(start)})"
        marks = (
            f'<span style="position:absolute;top:14px;height:3px;border-radius:2px;'
            f'background:{tokens.ACCENT};left:{left:.3f}%;width:{max(right - left, 0):.3f}%">'
            "</span>"
            f'<span style="position:absolute;top:9px;left:calc({left:.3f}% - 2px);width:0;'
            "height:0;border-top:6px solid transparent;border-bottom:6px solid transparent;"
            f'border-right:10px solid {tokens.ACCENT}"></span>'
            f'<span style="position:absolute;top:9px;left:calc({right:.3f}% - 6px);width:13px;'
            f"height:13px;border-radius:50%;background:{tokens.TEXT_MUTED};"
            f'border:2px solid {tokens.SURFACE_SUBTLE};box-sizing:border-box"></span>'
        )
        result = (
            f'<span class="shk-cut">−{_whole(row["단축일수"]) or 0}일</span>'
            f'<span class="shk-gain">{gain}</span>'
        )
    title = f"{row['호기']} · 해소 기여 월 {row['해소 기여 월'] or '-'}"
    return (
        f'<div class="shk-unit" title="{_escape(title)}">'
        f'<div style="display:flex;flex-direction:column;gap:1px;min-width:0">'
        f'<span class="shk-unit-name">{name}{_escape(module_note)}</span>'
        f'<span class="shk-unit-dates">{_escape(dates)}</span></div>'
        f'<div class="shk-track">{lines}{marks}</div>'
        f'<div class="shk-result">{result}</div></div>'
    )
