# Purpose: 필요 단축 일정 「누적 진척」 머리 띠 · 주차별 그림과 설정 상자 · 팝업을 그린다.

"""필요 단축 일정 「누적 진척」(2026-11-20 사용자 보드 답 — 누적-1 A · 누적-2 c · 누적-3 a · 누적-4
「한 줄 기록」 · 누적-5 a).

- **머리 한 줄 띠**(`CumulativeProgress.render_strip`) — 작은 꺾은선 · 지금 일수(마지막 기록) · 지난
  기록 대비 · 첫 기록 → 최종 목표 막대와 남은 일수, 오른쪽 끝 「주차별」 단추. 진척 비교를 고르지
  않아도 늘 선다(누적-5 a) — 기준선을 고르면 호기 두 줄 카드가 그 아래(본문)다. 값은 모두 **기록
  기준**이다 — 화면에서 공정 · 목표 확보율을 바꿔도 띠 · 선은 그대로다(누적-4 「한 줄 기록」).
  기록이 없으면 점선 표지 「기록 없음」, 목표가 없으면 「최종 목표 미지정」 이다(설계 규칙
  UI-LAY-10). 띠는 한 줄이다(UI-LAY-13) — 「주차별」 은 줄을 넘기지 않고, 좁으면 띠 안쪽이 먼저
  줄인다(목표 칸이 좁으면 「첫 기록 … →」 글을 숨김 · 목표 주차 지남은 남은 일수 아래 작은 줄).
- **「주차별」**(누적-1 A)을 누르면 띠 아래에 주차별 꺾은선 + 목표선이 펼쳐진다(B 시안 — 늘어난 주는
  주황 ▲ 와 「+N」, 줄어든 주는 ●, 마지막 기록에서 목표까지 남은 길은 점선). 띠는 키 붙은
  프래그먼트라 여닫기가 띠만 다시 돌린다(설계 규칙 UI-PRF-01). 편 상태는 세션 칸이라 진척 비교를
  바꾸거나 앱 전체가 다시 돌아도 남는다.
- **사이드바 「누적 진척 설정」 상자 → 같은 제목 팝업**(설계 규칙 UI-LAY-01 — 공용 값을 고치는
  팝업은 사이드바 설정 상자). 팝업 위 「주차 기록」 은 기록 표와 넣기 · 고치기 · 지우기 줄(주차 ·
  단축 필요일수 · 저장자 → 「기록 저장」 · 「이번 주 값 넣기」 · 「기록 지우기」), 아래 「최종
  목표」 는 목표 일수 · 목표 주차와 「목표 저장」 · 「목표 지우기」 다. 저장해도 팝업은 열린 채 앱
  전체가 다시 돌아 띠가 새 값으로 선다(설계 규칙 UI-STA-06). 결과는 알림창 하나다(UI-NTF-03) — 남의
  저장에 진 거부만 단추 곁에도 선다.
- **「이번 주 값 넣기」** 는 본문이 마지막으로 그린 화면의 단축 필요일수
  합계(`remember_screen_total` — `required_shortening_panel._render_body` 가 적는다, 계산은
  `screen_shortening_days` 하나)로 이번 주 칸을 채운다 — 고쳐 적을 수 있다. 합계는 조건 카드 맨 위
  현재 일정 기준 전환(Static | 설비 마스터)이 고른 계획이다 — 진척 비교가 기준선과 같은 다른 기준의
  계획을 보이는 회차에도 전환의 기준이고, 풍선이 그 기준 · 목표 · 공정 수를 말한다. 기준선을 남길
  수 없는 화면(샘플 fleet · 공식 발행 쌍이 아닌 설비 · 미저장 시나리오 편집 · UPEH 가정)이면 잠기고
  풍선이 까닭을 말한다 — 기록도 모두가 보는 공용 값이라 기준선과 같은 규칙이다.
- **등급**(접속 등급 — 설계 규칙 UI-INP-07 예외): 기록은 실무자부터(`shortening.progress_log` —
  기준선과 같다), 최종 목표는 관리자부터(`shortening.progress_goal` — 모두의 기준을 바꾸는 공용 값).
  그 아래 등급은 같은 팝업에서 값만 본다.
- **겹친 저장**(설계 규칙 UI-STA-05): 기록은 그 주에서 본 값, 목표는 본 version 과 저장소가 쓰기
  잠금 안에서 대조한다. 본 값은 그 세대의 칸을 처음 그린 회차의 저장값이다(팝업 본문은 회차마다
  저장본을 다시 읽는다 — `dialog_host` 「쓰는 쪽이 지키는 것」 1). 지우기도 그 값으로 대조하고(본
  값이 없었는데 그 사이 남이 넣은 주는 거절 — 본 적 없는 값을 지우지 않는다), 「바뀐 것이 없음」
  도 저장소가 지금 값으로 가른다(칸이 본 값과 같아도 남이 고쳤으면 겹친 저장). 화면 합계가 적을
  수 있는 위끝(`PROGRESS_DAYS_MAX`)을 넘으면 「이번 주 값 넣기」 는 잠기고 풍선이 까닭을 말한다.

저장은 설비 DB `0036`, 캐시는 `equipment_cache.load_shortening_progress_log` 다.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Final
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.dialog_host import DialogHost
from capa_simulation.components.equipment_save_fields import render_saved_by_field
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.grade_hooks import in_fragment, viewer_can
from capa_simulation.components.plotly_layout import (
    apply_axis_text_color,
    chart_canvas_layout,
    hover_chart_config,
)
from capa_simulation.components.settings_box import render_settings_box
from capa_simulation.components.widget_generation import bump, generation, widget_key
from capa_simulation.components.write_guard import (
    held_notice,
    is_own_save,
    note_notice,
    notice_marks,
    own_save_marks,
    remember_own_save,
)
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence._sql_helpers import ProfileVersionConflict
from capa_simulation.persistence.equipment_cache import (
    clear_shortening_progress_cache,
    get_equipment_repository,
    load_shortening_progress_log,
)
from capa_simulation.services.korean_particle import with_object_particle, with_subject_particle
from capa_simulation.services.required_shortening import level_percent
from capa_simulation.services.shortening_progress_log import (
    PROGRESS_DAYS_MAX,
    ProgressGoal,
    ProgressHeadline,
    ProgressLog,
    ProgressLogConflictError,
    ProgressLogInvalidError,
    ProgressWeek,
    goal_week_options,
    normalize_progress_days,
    record_week_options,
    screen_shortening_days,
    summarize_log,
)
from capa_simulation.session_slot import SessionSlot
from capa_simulation.sidebar_status import keeps_app_run_open

__all__ = [
    "CUMULATIVE_BUTTON_KEY",
    "CUMULATIVE_DIALOG",
    "CUMULATIVE_TITLE",
    "SCREEN_TOTAL_KEY",
    "STRIP_FRAGMENT_KEY",
    "WEEKS_OPEN_KEY",
    "CumulativeProgress",
    "ScreenTotal",
    "forget_screen_total",
    "remember_screen_total",
    "strip_markup",
    "weekly_figure",
]

CUMULATIVE_TITLE = "누적 진척 설정"
CUMULATIVE_DIALOG = "shortening_cumulative"
CUMULATIVE_ICON = ":material/timeline:"
CUMULATIVE_BUTTON_KEY = "required_shortening_cumulative_settings_v1"
_BOX_NAME = "shortening_cumulative"
CUMULATIVE_HELP = (
    "필요 단축 일정 머리 「누적 진척」 의 주차 기록(주차 · 단축 필요일수)과 최종 목표(일수 · "
    "주차)를 적는 공용 값입니다 — 모두가 같은 기록을 봅니다."
)
# 머리 띠 — 키 붙은 프래그먼트(「주차별」 여닫기가 띠만 다시 돈다)와 그 칸.
STRIP_FRAGMENT_KEY = "required_shortening_cumulative_strip"
_STRIP_BOX_KEY = "shortening_cumulative_strip_box"
_WEEKS_BUTTON_KEY = "shortening_cumulative_weeks_toggle"
_WEEKS_CHART_KEY = "shortening_cumulative_weeks_chart"
# 「주차별」 을 편 상태(세션 — 진척 비교를 바꾸거나 앱 전체가 다시 돌아도 남는다).
WEEKS_OPEN_KEY = "shortening_cumulative_weeks_open_v1"
# 본문이 마지막으로 그린 화면의 단축 필요일수 합계(「이번 주 값 넣기」 가 읽는다).
SCREEN_TOTAL_KEY = "shortening_cumulative_screen_total_v1"
# 팝업 칸 — 세대가 바뀌면 칸이 새로 서며 그 세대의 기본값(저장값 · 넣은 값)으로 선다.
_RECORD_GENERATION_KEY = "shortening_cumulative_record_generation"
_GOAL_GENERATION_KEY = "shortening_cumulative_goal_generation"
_RECORD_WEEK_KEY = "shortening_cumulative_record_week"
_RECORD_DAYS_KEY = "shortening_cumulative_record_days"
_GOAL_DAYS_KEY = "shortening_cumulative_goal_days"
_GOAL_WEEK_KEY = "shortening_cumulative_goal_week"
_SAVED_BY_PREFIX = "shortening_cumulative"
# 고른 기록 주차(`YY-W##`) · 「이번 주 값 넣기」 가 넣은 (주차, 일수) · 그 세대 칸이 처음 본 저장값.
_CHOSEN_WEEK_KEY = "shortening_cumulative_chosen_week_v1"
_FILL_KEY = "shortening_cumulative_fill_v1"
_RECORD_SEEN_KEY = "shortening_cumulative_record_seen_v1"
_GOAL_SEEN_KEY = "shortening_cumulative_goal_seen_v1"
_RECORD_SAVE_KEY = "shortening_cumulative_record_save"
_RECORD_DELETE_KEY = "shortening_cumulative_record_delete"
_FILL_BUTTON_KEY = "shortening_cumulative_fill_this_week"
_GOAL_SAVE_KEY = "shortening_cumulative_goal_save"
_GOAL_CLEAR_KEY = "shortening_cumulative_goal_clear"
_RECORD_TABLE_KEY = "shortening_cumulative_record_table"
_RECORD_FLASH_KEY = "shortening_cumulative_record_flash_v1"
_GOAL_FLASH_KEY = "shortening_cumulative_goal_flash_v1"
# 이 세션이 한 최종 목표 저장의 제 저장 표지 이름(`write_guard.own_save_marks`).
_GOAL_SAVE_NAME = "shortening_cumulative_goal"

_TABLE_ROWS_SHOWN = 8
_SPARK_WIDTH = 150
_SPARK_HEIGHT = 32
_CHART_HEIGHT_PX = 260
_MAX_AXIS_LABELS = 14


@dataclass(frozen=True)
class ScreenTotal:
    """본문이 마지막으로 그린 화면의 단축 필요일수 합계와 그 범위 · 넣지 않을 까닭."""

    days: int
    level_percent: int
    process_count: int
    selected: bool
    basis: str
    """그 합계의 현재 일정 기준(조건 카드 전환 — Static | 설비 마스터)."""
    refusal: str | None = None


_SCREEN_TOTAL: Final[SessionSlot[ScreenTotal]] = SessionSlot(SCREEN_TOTAL_KEY, ScreenTotal)
_WEEKS_OPEN: Final[SessionSlot[bool]] = SessionSlot(WEEKS_OPEN_KEY, bool, lambda: False)
_CHOSEN_WEEK: Final[SessionSlot[str]] = SessionSlot(_CHOSEN_WEEK_KEY, str)
_FILL: Final[SessionSlot[tuple[object, ...]]] = SessionSlot(_FILL_KEY, tuple)
_RECORD_SEEN: Final[SessionSlot[tuple[object, ...]]] = SessionSlot(_RECORD_SEEN_KEY, tuple)
_GOAL_SEEN: Final[SessionSlot[tuple[object, ...]]] = SessionSlot(_GOAL_SEEN_KEY, tuple)


def remember_screen_total(
    units: pd.DataFrame,
    scope: Sequence[str],
    *,
    level: float,
    selected: bool,
    basis: str,
    refusal: str | None,
) -> None:
    """본문(`required_shortening_panel._render_body`)이 회차마다 적는다 — 고른 목표의 계획 · 범위
    공정의 단축 필요일수 합계(`screen_shortening_days`)와, 기준선을 남길 수 없는 화면이면 그
    까닭. `units` 는 현재 일정 기준 전환이 고른 계획(`basis`)의 것이다 — 진척 비교가 기준선의
    기준으로 바꿔 그리는 계획이 아니다."""
    _SCREEN_TOTAL.set(
        ScreenTotal(
            days=screen_shortening_days(units, scope),
            level_percent=level_percent(level),
            process_count=len(scope),
            selected=selected,
            basis=basis,
            refusal=refusal,
        )
    )


def forget_screen_total() -> None:
    """본문 회차의 처음에 부른다 — 계획이 멈춘 회차에 앞 회차 합계가 남지 않게."""
    _SCREEN_TOTAL.clear()


# ------------------------------------------------------------------ 머리 띠


def _days(value: int) -> str:
    return f"{value:,}일"


def _signed_days(change: int) -> str:
    if change > 0:
        return f"+{change:,}일"
    if change < 0:
        return f"−{-change:,}일"
    return "0일"


def _strip_style() -> str:
    """띠 서식 — 토큰은 부를 때 읽는다(두 테마)."""
    display = tokens.FONT_FAMILY_DISPLAY
    return f"""
<style>
.shk-cum {{display:flex;flex-wrap:wrap;align-items:center;gap:6px 18px;min-height:36px;
  font-family:{tokens.FONT_FAMILY};color:{tokens.TEXT};font-variant-numeric:tabular-nums}}
.shk-cum-label {{font-size:13px;font-weight:600;color:{tokens.TEXT_MUTED};white-space:nowrap}}
.shk-cum-spark {{flex:none;display:block}}
.shk-cum-now {{display:flex;align-items:baseline;gap:6px;white-space:nowrap}}
.shk-cum-days {{font-family:{display};font-size:22px;font-weight:800}}
.shk-cum-week {{font-size:12px;color:{tokens.TEXT_MUTED}}}
.shk-cum-change {{font-size:12px;font-weight:700;white-space:nowrap;padding:1px 10px;
  border-radius:999px;border:1px solid}}
.shk-cum-goal {{display:flex;align-items:center;gap:10px;flex:1 1 180px;max-width:100%}}
.shk-cum-route {{display:flex;flex-direction:column;gap:4px;flex:1 1 90px;min-width:120px;
  container-type:inline-size}}
.shk-cum-route-text {{display:flex;gap:4px;min-width:0;font-size:12px;color:{tokens.TEXT_MUTED};
  white-space:nowrap}}
.shk-cum-route-from,.shk-cum-route-goal {{min-width:0;overflow:hidden;text-overflow:ellipsis}}
.shk-cum-route-from {{flex:0 1000 auto}}
.shk-cum-route-goal {{flex:0 1 auto}}
@container (max-width: 220px) {{ .shk-cum-route-from {{display:none}} }}
.shk-cum-track {{height:8px;border-radius:4px;background:{tokens.BAR_TRACK};overflow:hidden}}
.shk-cum-fill {{display:block;height:100%;border-radius:4px;background:{tokens.ACCENT}}}
.shk-cum-left {{display:flex;flex-direction:column;font-size:14px;font-weight:700;line-height:1.25;
  white-space:nowrap}}
.shk-cum-left-note {{font-size:11px;font-weight:600}}
.shk-cum-mark {{font-size:12px;color:{tokens.TEXT_MUTED};border:1px dashed {tokens.BORDER_STRONG};
  border-radius:6px;padding:1px 10px;white-space:nowrap}}
</style>
"""


def _sparkline(log: ProgressLog) -> str:
    """작은 꺾은선(기록만 잇는다) · 목표선(점선) · 마지막 점. 기록이 둘 미만이면 빈 글."""
    entries = log.entries
    if len(entries) < 2:
        return ""
    goal = log.goal.goal
    values = [entry.days for entry in entries] + ([goal.days] if goal is not None else [])
    low, high = 0, max(max(values), 1)
    first = entries[0].week
    span = max(first.weeks_until(entries[-1].week), 1)

    def point(entry_week: ProgressWeek, days: int) -> tuple[float, float]:
        x = 2 + (_SPARK_WIDTH - 4) * first.weeks_until(entry_week) / span
        y = 3 + (_SPARK_HEIGHT - 6) * (1 - (days - low) / (high - low))
        return x, y

    points = [point(entry.week, entry.days) for entry in entries]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    parts = []
    if goal is not None:
        _, goal_y = point(first, goal.days)
        parts.append(
            f'<line x1="2" y1="{goal_y:.1f}" x2="{_SPARK_WIDTH - 2}" y2="{goal_y:.1f}" '
            f'stroke="{tokens.TEXT_MUTED}" stroke-dasharray="3 3"/>'
        )
    parts.append(
        f'<polyline fill="none" stroke="{tokens.ACCENT}" stroke-width="2" points="{line}"/>'
    )
    end_x, end_y = points[-1]
    parts.append(
        f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="3.5" fill="{tokens.ACCENT}" '
        f'stroke="{tokens.SURFACE}" stroke-width="1.5"/>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_SPARK_WIDTH}" '
        f'height="{_SPARK_HEIGHT}" viewBox="0 0 {_SPARK_WIDTH} {_SPARK_HEIGHT}">'
        f"{''.join(parts)}</svg>"
    )
    # `st.html` 은 인라인 SVG 를 걷어 낸다 — 그림은 data URL 그림으로 싣는다(공정 Capa 상세 시트
    # 고른 칸 표지와 같은 길).
    return (
        f'<img class="shk-cum-spark" width="{_SPARK_WIDTH}" height="{_SPARK_HEIGHT}" '
        f'alt="주차별 기록 {len(entries)}개" '
        f'src="data:image/svg+xml,{quote(svg, safe="")}">'
    )


def _change_markup(change: int | None) -> str:
    """지난 기록 대비 — 줄임 `ACCENT`, 늘어남 `DELTA_INCREASE`(▲ 와 함께 — 색만으로 뜻을 나르지
    않는다), 같으면 `TEXT_MUTED`. 기록이 하나면 없다(0 이 아니다)."""
    if change is None:
        return ""
    if change < 0:
        color, glyph = tokens.ACCENT, "▼ "
    elif change > 0:
        color, glyph = tokens.DELTA_INCREASE, "▲ "
    else:
        color, glyph = tokens.TEXT_MUTED, ""
    return (
        f'<span class="shk-cum-change" style="color:{color};border-color:{color}">'
        f"지난 기록 대비 {glyph}{_signed_days(change)}</span>"
    )


def _goal_markup(headline: ProgressHeadline) -> str:
    goal = headline.goal
    if goal is None:
        return '<span class="shk-cum-mark">최종 목표 미지정</span>'
    target = f"최종 목표 {_days(goal.days)}({html.escape(goal.week.label)})"
    first = headline.first
    if first is None or headline.remaining is None:
        return f'<span class="shk-cum-route-text">{target}</span>'
    start = f"첫 기록 {_days(first.days)}({html.escape(first.week.label)}) →"
    route = f"{start} {target}"
    share = 0.0 if headline.progress is None else headline.progress * 100
    if headline.reached:
        left, color = "목표 도달", tokens.ACCENT
    else:
        # 목표 주차 지남은 남은 일수 아래 작은 줄이다 — 띠 높이 안에서 한 줄 폭을 늘리지 않는다.
        left = f"남은 {_days(headline.remaining)}" + (
            '<span class="shk-cum-left-note">목표 주차 지남</span>' if headline.overdue else ""
        )
        color = tokens.DELTA_INCREASE if headline.overdue else tokens.TEXT
    return (
        '<span class="shk-cum-goal"><span class="shk-cum-route">'
        f'<span class="shk-cum-route-text" title="{route}">'
        f'<span class="shk-cum-route-from">{start}</span>'
        f'<span class="shk-cum-route-goal">{target}</span></span>'
        f'<span class="shk-cum-track"><span class="shk-cum-fill" style="width:{share:.1f}%">'
        "</span></span></span>"
        f'<span class="shk-cum-left" style="color:{color}">{left}</span></span>'
    )


def strip_markup(log: ProgressLog, today: date) -> str:
    """머리 한 줄 — 서식과 한 `st.html`(스타일만 든 `st.html` 은 이벤트 칸으로 간다)."""
    headline = summarize_log(log, today)
    latest = headline.latest
    if latest is None:
        now = '<span class="shk-cum-mark">기록 없음</span>'
    else:
        now = (
            f'<span class="shk-cum-now"><span class="shk-cum-days">{_days(latest.days)}</span>'
            f'<span class="shk-cum-week">{html.escape(latest.week.label)}</span></span>'
        )
    body = "".join(
        (
            '<span class="shk-cum-label">누적 진척</span>',
            _sparkline(log),
            now,
            _change_markup(headline.change),
            _goal_markup(headline),
        )
    )
    return _strip_style() + f'<div class="shk-cum" role="group" aria-label="누적 진척">{body}</div>'


def _axis_weeks(log: ProgressLog) -> tuple[ProgressWeek, ...]:
    """주차별 그림의 가로축 — 첫 기록(또는 목표 주)부터 마지막 기록 · 목표 주까지 모든 주."""
    weeks = [entry.week for entry in log.entries]
    goal = log.goal.goal
    if goal is not None:
        weeks.append(goal.week)
    if not weeks:
        return ()
    start, end = min(weeks), max(weeks)
    return tuple(start.shifted(offset) for offset in range(start.weeks_until(end) + 1))


def weekly_figure(log: ProgressLog) -> go.Figure:
    """주차별 꺾은선 + 목표선(B 시안). 선은 기록만 잇는다 — 기록 없는 주는 건너 이어 그린다. 첫
    기록은 속 빈 회색 점, 줄어든 주는 ●, 늘어난 주는 주황 ▲ 와 「+N」 이다. 목표가 있으면 목표
    일수에 가로 점선과 이름, 마지막 기록이 목표 주보다 앞이고 도달하지 못했으면 거기서 목표 점까지
    점선."""
    axis = _axis_weeks(log)
    index = {week: position for position, week in enumerate(axis)}
    entries = log.entries
    changes = log.changes()
    goal = log.goal.goal
    xs = [index[entry.week] for entry in entries]
    ys = [entry.days for entry in entries]
    colors, symbols, sizes = [], [], []
    for position, change in enumerate(changes):
        if position == 0:
            colors.append(tokens.SURFACE)
            symbols.append("circle")
            sizes.append(9)
        elif change is not None and change > 0:
            colors.append(tokens.DELTA_INCREASE)
            symbols.append("triangle-up")
            sizes.append(12)
        else:
            colors.append(tokens.ACCENT)
            symbols.append("circle")
            sizes.append(9)
    hover = [
        f"{entry.week.label} · {_days(entry.days)}"
        + ("" if change is None else f" · 지난 기록 대비 {_signed_days(change)}")
        for entry, change in zip(entries, changes, strict=True)
    ]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            line={"color": tokens.ACCENT, "width": 2},
            marker={
                "color": colors,
                "symbol": symbols,
                "size": sizes,
                "line": {
                    "color": [tokens.TEXT_MUTED] + [tokens.SURFACE] * (len(xs) - 1),
                    "width": 2,
                },
            },
            hovertext=hover,
            hoverinfo="text",
            showlegend=False,
        )
    )
    rises = [
        (x, y, change)
        for x, y, change in zip(xs, ys, changes, strict=True)
        if change is not None and change > 0
    ]
    if rises:
        figure.add_trace(
            go.Scatter(
                x=[x for x, _, _ in rises],
                y=[y for _, y, _ in rises],
                mode="text",
                text=[_signed_days(change) for _, _, change in rises],
                textposition="top center",
                textfont={"color": tokens.DELTA_INCREASE, "size": 12},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    top = max([*ys, goal.days if goal is not None else 0, 1])
    if goal is not None:
        figure.add_hline(
            y=goal.days,
            line={"color": tokens.TEXT, "width": 1.5, "dash": "dash"},
            annotation_text=f"최종 목표 {_days(goal.days)} · {goal.week.label}",
            annotation_position="top right",
            annotation_font={"color": tokens.TEXT, "size": 12},
        )
        last = entries[-1] if entries else None
        if last is not None and last.week < goal.week and last.days > goal.days:
            figure.add_trace(
                go.Scatter(
                    x=[index[last.week], index[goal.week]],
                    y=[last.days, goal.days],
                    mode="lines",
                    line={"color": tokens.BORDER_STRONG, "width": 1.5, "dash": "dot"},
                    hovertext=f"남은 {_days(last.days - goal.days)}",
                    hoverinfo="text",
                    showlegend=False,
                )
            )
    if entries:
        last = entries[-1]
        figure.add_annotation(
            x=index[last.week],
            y=last.days,
            text=f"<b>{_days(last.days)}</b> ({last.week.label})",
            showarrow=False,
            xanchor="left",
            yanchor="top",
            xshift=8,
            yshift=-4,
            font={"color": tokens.TEXT, "size": 12},
        )
    # 마지막 기록이 축 끝이면(목표 주가 앞이거나 없음) 오른쪽에 그 값 글자 자리를 둔다.
    room = 1.6 if entries and index[entries[-1].week] == len(axis) - 1 else 0.0
    step = max(1, -(-len(axis) // _MAX_AXIS_LABELS))
    ticks = list(range(0, len(axis), step))
    figure.update_layout(
        **chart_canvas_layout(font_size=12),
        height=_CHART_HEIGHT_PX,
        margin={"l": 48, "r": 24, "t": 24, "b": 36},
        hovermode="closest",
        xaxis={
            "tickvals": ticks,
            "ticktext": [axis[tick].label for tick in ticks],
            "range": [-0.5, max(len(axis) - 0.5, 0.5) + room],
            "fixedrange": True,
            "showgrid": False,
            "zeroline": False,
        },
        yaxis={
            "range": [0, top * 1.18],
            "fixedrange": True,
            "ticksuffix": "일",
            "gridcolor": tokens.BAR_TRACK,
            "zeroline": False,
        },
    )
    apply_axis_text_color(figure)
    return figure


def _toggle_weeks() -> None:
    """「주차별」 콜백 — 편 상태만 바꾼다(띠 프래그먼트만 다시 돈다)."""
    _WEEKS_OPEN.set(not _WEEKS_OPEN.get())


def _strip_body(database_path: str, today: date) -> None:
    try:
        log = load_shortening_progress_log(database_path)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(
            "누적 진척 기록을 읽지 못했습니다. " + bootstrap_error_message(exc),
            code="RS-01",
            text="누적 진척 기록을 읽지 못했습니다(설비 DB)",
        )
        return
    opened = _WEEKS_OPEN.get() and bool(log.entries)
    with st.container(border=True, key=_STRIP_BOX_KEY, gap="small"):
        # 한 줄 — 「주차별」 은 늘 띠 오른쪽 끝이다(줄을 넘기지 않는다). 좁으면 띠 안쪽이 먼저
        # 줄인다(첫 기록 글 → 둘째 줄).
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=False):
            st.html(strip_markup(log, today), width="stretch")
            st.button(
                "주차별",
                key=_WEEKS_BUTTON_KEY,
                icon=":material/expand_less:" if opened else ":material/expand_more:",
                on_click=_toggle_weeks,
                disabled=not log.entries,
                help=None if log.entries else "기록이 없습니다 — 「누적 진척 설정」 에서 적습니다.",
                width="content",
            )
        if opened:
            st.plotly_chart(
                weekly_figure(log),
                key=_WEEKS_CHART_KEY,
                config=hover_chart_config(),
                width="stretch",
            )


# ------------------------------------------------------------------ 팝업


def _chosen_week(options: Sequence[ProgressWeek], this_week: ProgressWeek) -> ProgressWeek:
    """고른 기록 주차 — 세션 칸이 선택지 밖이면 이번 주."""
    chosen = _CHOSEN_WEEK.peek()
    if chosen is not None:
        try:
            week = ProgressWeek.parse(chosen)
        except ValueError:
            week = this_week
        if week in options:
            return week
    return this_week


def _choose_week(widget: str) -> None:
    """기록 주차를 바꾼 콜백 — 일수 칸을 그 주의 저장값으로 새로 세운다."""
    picked = SessionSlot(widget, str).peek()
    if picked is not None:
        _CHOSEN_WEEK.set(picked)
    _FILL.clear()
    bump(_RECORD_GENERATION_KEY)


def _fill_this_week(week_label: str, days: int) -> None:
    """「이번 주 값 넣기」 콜백 — 이번 주를 고르고 그 칸을 지금 화면 합계로 채운다(고쳐 적을 수
    있다)."""
    _CHOSEN_WEEK.set(week_label)
    _FILL.set((week_label, days))
    bump(_RECORD_GENERATION_KEY)


def _seen_days(log: ProgressLog, week: ProgressWeek) -> int | None:
    """이 세대 칸이 처음 본 그 주의 저장값 — 겹친 저장 대조의 출발점. 세대 · 주가 바뀌면 지금
    저장값으로 다시 적는다."""
    number = generation(_RECORD_GENERATION_KEY)
    seen = _RECORD_SEEN.peek()
    if seen is not None and len(seen) == 3 and seen[0] == number and seen[1] == week.label:
        value = seen[2]
        return value if isinstance(value, int) else None
    stored = log.days_of(week)
    _RECORD_SEEN.set((number, week.label, stored))
    return stored


def _seen_goal_version(log: ProgressLog) -> int:
    number = generation(_GOAL_GENERATION_KEY)
    seen = _GOAL_SEEN.peek()
    if seen is not None and len(seen) == 2 and seen[0] == number and isinstance(seen[1], int):
        return seen[1]
    _GOAL_SEEN.set((number, log.goal.version))
    return log.goal.version


def _record_frame(log: ProgressLog) -> pd.DataFrame:
    """기록 표 — 최근 주가 위."""
    rows = [
        {
            "주차": entry.week.label,
            "단축 필요일수": _days(entry.days),
            "지난 기록 대비": None if change is None else _signed_days(change),
            "저장자": entry.recorded_by or None,
        }
        for entry, change in zip(log.entries, log.changes(), strict=True)
    ]
    return pd.DataFrame(rows[::-1], columns=["주차", "단축 필요일수", "지난 기록 대비", "저장자"])


def _render_records(log: ProgressLog) -> None:
    if not log.entries:
        st.caption("기록이 없습니다.")
        return
    frame = _record_frame(log)
    st.dataframe(
        frame,
        key=_RECORD_TABLE_KEY,
        hide_index=True,
        width="stretch",
        height=min(len(frame), _TABLE_ROWS_SHOWN) * tokens.TABLE_ROW_HEIGHT_PX
        + tokens.TABLE_HEADER_HEIGHT_PX
        + 3,
        placeholder="",
    )


def _days_in_range(value: object) -> int | None:
    """일수 칸에 세울 수 있는 값(0 ~ `PROGRESS_DAYS_MAX` 정수)이면 그 값 — 밖이면 None(칸이 그
    값으로 서면 Streamlit 이 회차를 멈춘다)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= PROGRESS_DAYS_MAX else None


def _fill_locked(total: ScreenTotal | None) -> bool:
    """「이번 주 값 넣기」 를 잠그나 — 합계가 없음 · 기준선과 같은 거절 · 적을 수 있는 위끝 밖."""
    return total is None or total.refusal is not None or _days_in_range(total.days) is None


def _fill_help(total: ScreenTotal | None, this_week: ProgressWeek) -> str:
    if total is None:
        return "지금 화면의 단축 필요일수 합계가 없습니다 — 계획이 서면 넣습니다."
    if total.refusal is not None:
        return "기준선과 같은 까닭으로 지금 화면 값은 넣지 않습니다 — " + total.refusal
    if _days_in_range(total.days) is None:
        return (
            f"지금 화면 합계 {with_subject_particle(_days(total.days))} 적을 수 있는 위끝 "
            f"{with_object_particle(_days(PROGRESS_DAYS_MAX))} 넘어 넣지 않습니다 — "
            "손으로 적습니다."
        )
    scope = "고른 공정" if total.selected else "맞댄 공정"
    return (
        f"{this_week.label} 칸을 지금 화면 합계 {_days(total.days)}({total.basis} 기준 · "
        f"목표 {total.level_percent}% · {scope} {total.process_count}개)로 채웁니다. "
        "고쳐 적을 수 있습니다."
    )


def _save_record(
    database_path: str,
    slot: DeltaGenerator,
    week: ProgressWeek,
    value: object,
    expected: int | None,
    saved_by: str | None,
) -> None:
    try:
        days = normalize_progress_days(value)
    except ProgressLogInvalidError as exc:
        slot.warning(bootstrap_error_message(exc), icon=":material/edit_note:")
        return
    # 「바뀐 것이 없음」 도 저장소가 쓰기 잠금 안의 지금 값으로 가른다 — 칸이 본 값과 같아도 그 사이
    # 남이 고쳤으면 겹친 저장이다(본 값만 보고 「이미 n일」 이라 하지 않는다).
    notices = notice_marks()
    try:
        repository = get_equipment_repository(database_path)
        wrote = repository.save_shortening_progress_entry(
            week, days, expected_days=expected, recorded_by=saved_by or ""
        )
    except ProgressLogConflictError as exc:
        clear_shortening_progress_cache()
        queue_flash(
            _RECORD_FLASH_KEY,
            bootstrap_error_message(exc),
            kind="warning",
            icon=":material/sync_problem:",
        )
        _FILL.clear()
        bump(_RECORD_GENERATION_KEY)
        st.rerun()
    except BOOTSTRAP_ERRORS as exc:
        slot.error(f"기록을 저장하지 못했습니다 — {bootstrap_error_message(exc)}")
        return
    clear_shortening_progress_cache()
    if not wrote:
        # 지금 저장본이 이미 그 값이다(빠른 둘째 누름 · 남이 같은 값을 적음). 방금 저장한 같은 값의
        # 빠른 둘째 누름이면 그 성공을 덮지 않는다(write_guard.held_notice).
        if held_notice(_RECORD_FLASH_KEY) is None:
            queue_flash(
                _RECORD_FLASH_KEY,
                f"바뀐 것이 없습니다 — {week.label} 기록이 이미 {_days(days)}입니다.",
                kind="info",
            )
    else:
        message = f"누적 진척 기록을 저장했습니다 — {week.label} · {_days(days)}."
        note_notice(notices, _RECORD_FLASH_KEY, message)
        queue_flash(_RECORD_FLASH_KEY, message)
    _FILL.clear()
    bump(_RECORD_GENERATION_KEY)
    st.rerun()


def _delete_record(
    database_path: str,
    slot: DeltaGenerator,
    week: ProgressWeek,
    expected: int | None,
) -> None:
    """그 세대 칸이 처음 본 값(`expected`)으로 지운다 — 누른 회차에 새로 읽은 값을 넘기지 않는다.
    본 값이 없었는데(팝업을 연 뒤 남이 그 주를 넣음) 지금 기록이 있으면 저장소가 겹친 저장으로
    거절한다(본 적 없는 값을 지우지 않는다)."""
    notices = notice_marks()
    try:
        deleted = get_equipment_repository(database_path).delete_shortening_progress_entry(
            week, expected_days=expected
        )
    except ProgressLogConflictError as exc:
        clear_shortening_progress_cache()
        queue_flash(
            _RECORD_FLASH_KEY,
            bootstrap_error_message(exc),
            kind="warning",
            icon=":material/sync_problem:",
        )
        bump(_RECORD_GENERATION_KEY)
        st.rerun()
    except BOOTSTRAP_ERRORS as exc:
        slot.error(f"기록을 지우지 못했습니다 — {bootstrap_error_message(exc)}")
        return
    clear_shortening_progress_cache()
    if deleted:
        message = f"누적 진척 기록을 지웠습니다 — {week.label}."
        note_notice(notices, _RECORD_FLASH_KEY, message)
        queue_flash(_RECORD_FLASH_KEY, message)
    elif held_notice(_RECORD_FLASH_KEY) is None:
        queue_flash(_RECORD_FLASH_KEY, f"이미 지워진 기록입니다 — {week.label}.", kind="info")
    _FILL.clear()
    bump(_RECORD_GENERATION_KEY)
    st.rerun()


def _render_record_form(log: ProgressLog, today: date, database_path: str) -> None:
    this_week = ProgressWeek.of(today)
    options = record_week_options(today, log.entries)
    chosen = _chosen_week(options, this_week)
    expected = _seen_days(log, chosen)
    fill = _FILL.peek()
    filled = (
        _days_in_range(fill[1])
        if fill is not None and len(fill) == 2 and fill[0] == chosen.label
        else None
    )
    labels = [week.label for week in options]
    recorded = {entry.week.label: entry.days for entry in log.entries}
    week_key = widget_key(_RECORD_WEEK_KEY, _RECORD_GENERATION_KEY)
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        picked = st.selectbox(
            "주차",
            labels,
            index=labels.index(chosen.label),
            key=week_key,
            format_func=lambda label: (
                f"{label} · {_days(recorded[label])}" if label in recorded else label
            ),
            on_change=_choose_week,
            args=(week_key,),
            width=190,
        )
        week = ProgressWeek.parse(picked) if picked else chosen
        value = st.number_input(
            "단축 필요일수",
            min_value=0,
            max_value=PROGRESS_DAYS_MAX,
            step=1,
            value=filled if filled is not None else _days_in_range(expected),
            key=widget_key(_RECORD_DAYS_KEY, _RECORD_GENERATION_KEY),
            placeholder="일",
            width=150,
        )
        saved_by = render_saved_by_field(_SAVED_BY_PREFIX, persist=True, width=160)
    total = _SCREEN_TOTAL.peek()
    with st.container(horizontal=True, gap="small"):
        save = st.button(
            "기록 저장",
            key=_RECORD_SAVE_KEY,
            icon=":material/save:",
            type="primary",
            help=(
                "고른 주차의 단축 필요일수를 모두가 보는 누적 진척 기록에 남깁니다(있으면 "
                "고칩니다)."
            ),
        )
        st.button(
            "이번 주 값 넣기",
            key=_FILL_BUTTON_KEY,
            icon=":material/input:",
            on_click=_fill_this_week,
            args=(this_week.label, 0 if total is None else total.days),
            disabled=_fill_locked(total),
            help=_fill_help(total, this_week),
        )
        stored = log.days_of(week)
        delete = st.button(
            "기록 지우기",
            key=_RECORD_DELETE_KEY,
            icon=":material/delete:",
            disabled=stored is None,
            help=(
                f"{week.label} 기록을 지웁니다 — 모든 사용자의 누적 진척에서 사라집니다."
                if stored is not None
                else "이 주에는 기록이 없습니다."
            ),
        )
    slot = render_flash(_RECORD_FLASH_KEY)
    if save:
        _save_record(database_path, slot, week, value, expected, saved_by)
    elif delete:
        _delete_record(database_path, slot, week, expected)


def _goal_text(log: ProgressLog) -> str:
    goal = log.goal.goal
    return "미지정" if goal is None else f"{_days(goal.days)} · {goal.week.label}"


def _goal_message(goal: ProgressGoal | None) -> str:
    return (
        "누적 진척 최종 목표를 지웠습니다."
        if goal is None
        else f"누적 진척 최종 목표를 저장했습니다 — {_days(goal.days)} · {goal.week.label}."
    )


def _save_goal(
    database_path: str,
    slot: DeltaGenerator,
    goal: ProgressGoal | None,
    expected_version: int,
    saved_by: str | None,
) -> None:
    # 표지 dict 는 저장 전에 받아 둔다 — 저장 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    notices = notice_marks()
    save_marks = own_save_marks()
    try:
        version = get_equipment_repository(database_path).save_shortening_progress_goal(
            goal, expected_version=expected_version, saved_by=saved_by or ""
        )
    except ProfileVersionConflict as exc:
        clear_shortening_progress_cache()
        if is_own_save(_GOAL_SAVE_NAME, expected_version, exc.stored, save_marks):
            # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
            queue_flash(_GOAL_FLASH_KEY, _goal_message(goal))
            bump(_GOAL_GENERATION_KEY)
            st.rerun()
        queue_flash(
            _GOAL_FLASH_KEY,
            bootstrap_error_message(exc),
            kind="warning",
            icon=":material/sync_problem:",
        )
        bump(_GOAL_GENERATION_KEY)
        st.rerun()
    except BOOTSTRAP_ERRORS as exc:
        slot.error(f"최종 목표를 저장하지 못했습니다 — {bootstrap_error_message(exc)}")
        return
    if version is not None:
        remember_own_save(_GOAL_SAVE_NAME, expected_version, version, save_marks)
    clear_shortening_progress_cache()
    if version is None:
        if held_notice(_GOAL_FLASH_KEY) is None:
            queue_flash(
                _GOAL_FLASH_KEY, "바뀐 것이 없습니다 — 최종 목표가 그대로입니다.", kind="info"
            )
        st.rerun()
    message = _goal_message(goal)
    note_notice(notices, _GOAL_FLASH_KEY, message)
    queue_flash(_GOAL_FLASH_KEY, message)
    bump(_GOAL_GENERATION_KEY)
    st.rerun()


def _render_goal_form(log: ProgressLog, today: date, database_path: str) -> None:
    current = log.goal.goal
    expected_version = _seen_goal_version(log)
    options = goal_week_options(today, current)
    labels = [week.label for week in options]
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        days = st.number_input(
            "목표 일수",
            min_value=0,
            max_value=PROGRESS_DAYS_MAX,
            step=1,
            value=None if current is None else current.days,
            key=widget_key(_GOAL_DAYS_KEY, _GOAL_GENERATION_KEY),
            placeholder="일",
            width=150,
        )
        week_label = st.selectbox(
            "목표 주차",
            labels,
            index=None if current is None else labels.index(current.week.label),
            key=widget_key(_GOAL_WEEK_KEY, _GOAL_GENERATION_KEY),
            placeholder="주차",
            width=190,
        )
    with st.container(horizontal=True, gap="small"):
        save = st.button(
            "목표 저장",
            key=_GOAL_SAVE_KEY,
            icon=":material/flag:",
            type="primary",
            help=(
                "모두가 보는 최종 목표(일수 · 주차)로 저장합니다 — 머리 띠 · 주차별 그림의 "
                "목표선이 바뀝니다."
            ),
        )
        clear = st.button(
            "목표 지우기",
            key=_GOAL_CLEAR_KEY,
            icon=":material/delete:",
            disabled=current is None,
            help=(
                "최종 목표를 지웁니다 — 모든 사용자의 목표선이 사라집니다."
                if current is not None
                else "지울 목표가 없습니다."
            ),
        )
    slot = render_flash(_GOAL_FLASH_KEY)
    saved_by = _saved_by_value()
    if save:
        if days is None or week_label is None:
            slot.warning("목표 일수와 목표 주차를 함께 적으세요.", icon=":material/edit_note:")
            return
        try:
            goal = ProgressGoal(normalize_progress_days(days), ProgressWeek.parse(week_label))
        except ProgressLogInvalidError as exc:
            slot.warning(bootstrap_error_message(exc), icon=":material/edit_note:")
            return
        _save_goal(database_path, slot, goal, expected_version, saved_by)
    elif clear and current is not None:
        _save_goal(database_path, slot, None, expected_version, saved_by)


def _saved_by_value() -> str | None:
    """기록 줄 저장자 칸의 지금 값 — 목표 저장도 같은 이름을 남긴다(등급이 모자라 기록 줄이 없으면
    비어 있다)."""
    value = SessionSlot(f"{_SAVED_BY_PREFIX}_saved_by", str).peek()
    text = "" if value is None else value.strip()
    return text or None


def _dialog_body(database_path: str, today: date) -> None:
    """「누적 진척 설정」 팝업 — 저장값은 회차마다 다시 읽는다(남의 저장을 옛 값으로 덮지 않게)."""
    try:
        log = load_shortening_progress_log(database_path)
    except BOOTSTRAP_ERRORS as exc:
        st.error(f"누적 진척 기록을 읽지 못했습니다 — {bootstrap_error_message(exc)}")
        return
    st.markdown("#### :material/timeline: 주차 기록")
    _render_records(log)
    if viewer_can("shortening.progress_log"):
        _render_record_form(log, today, database_path)
    st.markdown("#### :material/flag: 최종 목표")
    if viewer_can("shortening.progress_goal"):
        _render_goal_form(log, today, database_path)
    else:
        st.caption(f"최종 목표 · {_goal_text(log)}")


class CumulativeProgress:
    """필요 단축 일정의 누적 진척 — 사이드바 상자 · 팝업(그 화면 호스트가 연다) · 머리 띠."""

    def __init__(self, *, host: DialogHost, database_path: str) -> None:
        self.host = host
        self.database_path = database_path
        self._body: Callable[..., None] = st.dialog(
            CUMULATIVE_TITLE, width="medium", icon=CUMULATIVE_ICON, on_dismiss=host.close
        )(in_fragment(keeps_app_run_open(_dialog_body)))

    def dialogs(self, *, today: date) -> dict[str, Callable[[], None]]:
        """그 화면 호스트가 함께 여는 팝업(열림 값 → 팝업)."""
        return {CUMULATIVE_DIALOG: partial(self._body, self.database_path, today)}

    def widget_keys(self) -> dict[str, tuple[str, ...]]:
        """팝업의 입력 위젯 key(지금 세대) — 닫기가 지운다. 여는 콜백이 세대를 올려 다시 연 팝업은
        새 칸으로 선다."""
        return {
            CUMULATIVE_DIALOG: (
                widget_key(_RECORD_WEEK_KEY, _RECORD_GENERATION_KEY),
                widget_key(_RECORD_DAYS_KEY, _RECORD_GENERATION_KEY),
                widget_key(_GOAL_DAYS_KEY, _GOAL_GENERATION_KEY),
                widget_key(_GOAL_WEEK_KEY, _GOAL_GENERATION_KEY),
            )
        }

    def open_cumulative_settings(self) -> None:
        """사이드바 상자의 콜백 — 지난번 고른 주 · 넣은 값을 걷고 칸 세대를 올려 저장본에서 연다."""
        _CHOSEN_WEEK.clear()
        _FILL.clear()
        bump(_RECORD_GENERATION_KEY)
        bump(_GOAL_GENERATION_KEY)
        self.host.open(CUMULATIVE_DIALOG, CUMULATIVE_BUTTON_KEY)

    def render_box(self) -> None:
        """사이드바 「누적 진척 설정」 상자 — 조건 카드보다 먼저 부른다."""
        render_settings_box(
            CUMULATIVE_TITLE,
            name=_BOX_NAME,
            button_key=CUMULATIVE_BUTTON_KEY,
            on_click=self.open_cumulative_settings,
            tooltip=CUMULATIVE_HELP,
            icon=CUMULATIVE_ICON,
        )

    def render_strip(self, *, today: date) -> None:
        """머리 한 줄 띠 — 키 붙은 프래그먼트(「주차별」 여닫기가 띠만 다시 돈다)."""
        st.fragment(_strip_body, key=STRIP_FRAGMENT_KEY)(self.database_path, today)
