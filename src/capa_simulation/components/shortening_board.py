# Purpose: 필요 단축 일정의 진척 보드·기한 임박·이행 지연 목록과 강조 공정·상세 링크를 그린다.

"""필요 단축 일정 — 「단축이 필요한 공정 전부의 진척 관리 한 페이지」(2026-10-22 사용자 요청)의 화면
조각.

`required_shortening_panel` 의 본문 프래그먼트가 부른다. 숫자는 `services/shortening_watch.py` 가
내고 여기서는 고르고 그리기만 한다. **DB 에 쓰지 않는다** — 카드 차례·기한 임박 날수·강조 공정은
모두 세션 값이고, 조치 상태·메모 같은 공용 기록은 없다.

- **공정 진척 보드** — KPI 아래·카드 위. 공정마다 한 줄(`process_board`)이고 진척 비교를 고르면
  기준선 대비·이행 지연 칸이 붙는다. 줄을 고르면 그 공정 카드가 맨 위로 올라 강조된다(「진척
  보드에서 고른 공정」) — 카드의 「공정 Capa 상세에서 근거 보기」 로 깊게 본다. 고른 줄은 남기지
  않는다(표 key 세대를 올린다) — 강조를 끄면 표에 옛 선택이 남지 않게.
- **카드 차례** — 표시순서 / 목표 Qual 이른 순 / 최대 부족 큰 순 / 기준선 대비 악화 먼저(세션 값,
  선택지 넷 고정). 보드와 카드가 같은 차례이고 강조 공정만 그 앞이다.
- **기한 임박·이행 지연** — 보드 아래 두 상자(편 상태 기억). 이행 지연은 진척 비교의 기준선이 있어야
  낸다.
- **강조 공정**(`SHORTENING_HIGHLIGHT_KEY`) — 공정 Capa 상세의 「필요 단축 일정」 이동과 보드 줄
  고르기가 적는 세션 칸이다. **공정 필터(공용 프로필 0019 의 세션 칸)를 심지 않는다** — 심은 [공정]
  을 지우면 빈 선택이 공용 프로필에 저장됐다(2026-10-22 결함). 강조 공정이 공용 설정 공정 밖이면
  카드는 서되 KPI·CSV 에 들지 않는다고 적는다.
- **상세 근거 링크** — 카드마다 「공정 Capa 상세에서 근거 보기」(`st.page_link` + 주소 인자 — 그
  카드의 첫 부족 달·목표·기간·단축/신규 대수). 샘플 fleet 이면 숨긴다(상세는 설비 저장본만 본다).
- **도면 링크** — 그 옆 「도면에서 보기」(2026-10-24 결정 — Space 현황을 그 공정의 층·색 기준 「필요
  단축」·같은 목표로 연다, `space_link_params`). 층은 본문이 공정 전부를 한 번에 고른 표를 받는다
  (`space_shortening_layer.shortening_space_floors`). 두 화면이 같은 세션 설비 시나리오를
  따르므로(LY6) 풍선은 없다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design.theme import THEME_QUERY_PARAM
from capa_simulation.navigation import PROCESS_CAPA_DETAIL, SPACE_STATUS
from capa_simulation.process_detail_state import shortening_card_query_params
from capa_simulation.services.fab_layout import floor_param
from capa_simulation.services.floor_layout_profile import FloorKey
from capa_simulation.services.korean_particle import topic_particle
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.required_shortening import KIND_NEW, LevelPlan
from capa_simulation.services.shortening_watch import (
    BOARD_ORDERS,
    ORDER_DISPLAY,
    ORDER_WORSENED_FIRST,
    board_order,
    first_shortage_month,
    imminent_units,
    process_board,
    process_counts,
)
from capa_simulation.sidebar_status import remembered_expander

__all__ = [
    "BOARD_ORDER_KEY",
    "DEFAULT_DUE_DAYS",
    "DUE_DAYS_KEY",
    "HIGHLIGHT_FROM_BOARD",
    "HIGHLIGHT_FROM_DETAIL",
    "HIGHLIGHT_FROM_SPACE",
    "HIGHLIGHT_OFF_KEY",
    "SHORTENING_HIGHLIGHT_KEY",
    "ShorteningHighlight",
    "clear_highlight",
    "current_highlight",
    "detail_link_params",
    "highlight_badge",
    "highlight_first",
    "highlight_shortening_process",
    "render_detail_link",
    "render_highlight_notice",
    "render_progress_board",
    "render_space_link",
    "space_link_params",
]

# 강조 공정 — (원본 공정명, 출처). 위젯 키가 아니다.
SHORTENING_HIGHLIGHT_KEY = "equipment_shortening_highlight_v1"
HIGHLIGHT_FROM_DETAIL = "detail"
HIGHLIGHT_FROM_BOARD = "board"
# Space 현황 「필요 단축」 보기의 「필요 단축 일정에서 이 공정 보기」(2026-10-24 결정). 배지 글이
# 없으면 `current_highlight` 가 그 강조를 말없이 버린다.
HIGHLIGHT_FROM_SPACE = "space"
_HIGHLIGHT_BADGES = {
    HIGHLIGHT_FROM_DETAIL: "공정 Capa 상세에서 연 공정",
    HIGHLIGHT_FROM_BOARD: "진척 보드에서 고른 공정",
    HIGHLIGHT_FROM_SPACE: "Space 도면에서 연 공정",
}
HIGHLIGHT_OFF_KEY = "equipment_shortening_highlight_off"

# 카드 차례(세션 값)와 기한 임박 날수(세션 값).
BOARD_ORDER_KEY = "equipment_shortening_board_order_v1"
DUE_DAYS_KEY = "equipment_shortening_due_days_v1"
DEFAULT_DUE_DAYS = 30
_DUE_DAYS_MAX = 365
_BOARD_KEY = "equipment_shortening_board"
_BOARD_GENERATION_KEY = "equipment_shortening_board_generation"
_IMMINENT_EXPANDER_KEY = "equipment_shortening_imminent"
_DELAYED_EXPANDER_KEY = "equipment_shortening_delayed"
_IMMINENT_TABLE_KEY = "equipment_shortening_imminent_table"
_DELAYED_TABLE_KEY = "equipment_shortening_delayed_table"
_EMPTY = "—"


@dataclass(frozen=True)
class ShorteningHighlight:
    """강조 공정 하나 — 원본 공정명과 그 강조를 건 곳(`HIGHLIGHT_FROM_*`)."""

    process: str
    source: str


# ------------------------------------------------------------------ 강조 공정


def highlight_shortening_process(process: str, *, source: str) -> None:
    """강조 공정을 적는다 — 공정 Capa 상세의 이동(콜백·본문)과 보드 줄 고르기가 부른다.

    세션 칸 하나만 적는다. 필요 단축 일정의 공정 필터 칸·공용 프로필(0019)·기준선(0021)에는 닿지
    않는다. 값은 튜플이다(세션에 남는 값이라 코드가 다시 읽혀도 꺼낼 수 있게).
    """
    st.session_state[SHORTENING_HIGHLIGHT_KEY] = (str(process), str(source))


def current_highlight() -> ShorteningHighlight | None:
    """지금 강조 공정. 없거나 모양이 다르면 None."""
    value = st.session_state.get(SHORTENING_HIGHLIGHT_KEY)
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], str)
        and value[0]
        and value[1] in _HIGHLIGHT_BADGES
    ):
        return ShorteningHighlight(process=value[0], source=str(value[1]))
    return None


def clear_highlight() -> None:
    """「강조 끄기」 콜백."""
    st.session_state.pop(SHORTENING_HIGHLIGHT_KEY, None)


def highlight_badge(highlight: ShorteningHighlight) -> str:
    """카드 머리 배지 글 — 「공정 Capa 상세에서 연 공정」·「진척 보드에서 고른 공정」·「Space
    도면에서 연 공정」."""
    return _HIGHLIGHT_BADGES[highlight.source]


def highlight_first(order: Sequence[str], highlight: ShorteningHighlight | None) -> list[str]:
    """카드 차례 — 강조 공정을 맨 앞에(목록에 없어도 맨 앞에 더한다), 나머지는 그대로."""
    rest = [str(process) for process in order]
    if highlight is None:
        return rest
    return [highlight.process, *(process for process in rest if process != highlight.process)]


def render_highlight_notice(
    highlight: ShorteningHighlight,
    *,
    labels: ProcessLabels,
    matched: bool,
    in_scope: bool,
) -> None:
    """강조 카드 위 한 줄 — 공용 설정 밖이면 그 까닭, 맞대지 못한 공정이면 카드가 없다는 말, 「강조
    끄기」.

    `matched` 는 지금 계획이 맞댄 공정인가, `in_scope` 는 KPI·CSV 범위(조건 카드의 공정, 비면 맞댄
    공정 전체) 안인가다.
    """
    label = labels.label(highlight.process)
    # 사람이 적은 공정 표시명이라 마크다운에 싣는 글만 escape 하고 조사는 원래 이름으로 고른다.
    name = f"「{literal_markdown(label)}」"
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        if not matched:
            st.caption(
                f":material/link_off: 강조 공정 {name}{topic_particle(label)} 지금 시나리오·설비 "
                "일정에서 맞댄 공정이 아니라 카드가 없습니다.",
                width="content",
            )
        elif not in_scope:
            st.caption(
                f":material/filter_alt_off: {name} — 공용 설정의 공정 선택 밖 — KPI·CSV 에 들지 "
                "않음",
                width="content",
            )
        st.button(
            "강조 끄기",
            key=HIGHLIGHT_OFF_KEY,
            type="tertiary",
            icon=":material/close:",
            on_click=clear_highlight,
        )


# ------------------------------------------------------------------ 상세 근거 링크


def detail_link_params(
    level_plan: LevelPlan,
    process: str,
    *,
    level: float,
    months: Sequence[int],
    theme: str | None,
    equipment: str | None = None,
) -> dict[str, str]:
    """카드 하나의 상세 링크 주소 인자 — 그 카드의 첫 부족 달·목표·기간·단축/신규 대수와, 그 카드가
    본 설비 시나리오 한 마디(`equipment` — 표시용 `eq`, 「셋업 실무 r4」)."""
    shortened, new = process_counts(level_plan, process)
    return shortening_card_query_params(
        process=process,
        month=first_shortage_month(level_plan, process, months),
        target=level,
        start_month=int(months[0]),
        end_month=int(months[-1]),
        shortened=shortened,
        new=new,
        theme=theme,
        equipment=equipment,
    )


def render_detail_link(
    level_plan: LevelPlan,
    process: str,
    *,
    level: float,
    months: Sequence[int],
    equipment: str | None = None,
) -> None:
    """카드 아래 「공정 Capa 상세에서 근거 보기」. 달이 없으면 그리지 않는다. `equipment` 는 이
    화면이 본 설비 시나리오 한 마디(받은 상세 화면의 기준과 다르면 그쪽 출처 띠가 알린다)."""
    if not months:
        return
    theme = st.query_params.get(THEME_QUERY_PARAM)
    render_page_link(
        PROCESS_CAPA_DETAIL.path,
        label="공정 Capa 상세에서 근거 보기",
        icon=":material/troubleshoot:",
        query_params=detail_link_params(
            level_plan, process, level=level, months=months, theme=theme, equipment=equipment
        ),
    )


def space_link_params(
    process: str, *, floors: Mapping[str, FloorKey], level: float, theme: str | None
) -> dict[str, str]:
    """「도면에서 보기」 주소 인자 — `layer=short` · `proc`(원본 공정) · `target`(`1.1` — 공정 Capa
    상세 링크의 `target` 과 같은 꼴) · 고른 층이 있으면 `floor`(「C1-2F」), 지금 테마가 있으면
    그것(`st.page_link` 가 주소를 통째로 바꾼다). 층이 없으면 Space 가 FAB 전체로 연다."""
    params = {"layer": "short", "proc": str(process), "target": f"{float(level):g}"}
    floor = floors.get(str(process))
    if floor is not None:
        params["floor"] = floor_param(floor)
    if theme:
        params[THEME_QUERY_PARAM] = theme
    return params


def render_space_link(process: str, *, floors: Mapping[str, FloorKey], level: float) -> None:
    """카드 아래 「도면에서 보기」 — Space 현황을 그 공정의 층·필요 단축 보기·같은 목표로 연다."""
    render_page_link(
        SPACE_STATUS.path,
        label="도면에서 보기",
        icon=":material/grid_view:",
        query_params=space_link_params(
            process, floors=floors, level=level, theme=st.query_params.get(THEME_QUERY_PARAM)
        ),
        fallback="사이드바 Space 현황에서 색 기준 「필요 단축」",
    )


# ------------------------------------------------------------------ 진척 보드


def _board_generation() -> int:
    value = st.session_state.get(_BOARD_GENERATION_KEY, 0)
    return value if isinstance(value, int) else 0


def _pick_board_row(processes: tuple[str, ...], key: str) -> None:
    """보드 줄 고르기 콜백 — 그 공정을 강조하고 표 key 세대를 올린다(고른 줄을 남기지 않는다)."""
    state = st.session_state.get(key)
    rows: Sequence[object] = ()
    try:
        selection = state["selection"] if state is not None else None
        rows = selection["rows"] if selection is not None else ()
    except (KeyError, TypeError):
        rows = ()
    picked = [int(str(row)) for row in rows if str(row).isdigit()]
    if picked and 0 <= picked[0] < len(processes):
        highlight_shortening_process(processes[picked[0]], source=HIGHLIGHT_FROM_BOARD)
    st.session_state[_BOARD_GENERATION_KEY] = _board_generation() + 1


def _render_controls(*, compared: bool) -> tuple[str, int]:
    """카드 차례와 기한 임박 날수. 둘 다 세션 값이고 선택지는 고정이다."""
    if st.session_state.get(BOARD_ORDER_KEY) not in BOARD_ORDERS:
        st.session_state[BOARD_ORDER_KEY] = ORDER_DISPLAY
    if not isinstance(st.session_state.get(DUE_DAYS_KEY), int):
        st.session_state[DUE_DAYS_KEY] = DEFAULT_DUE_DAYS
    order_column, due_column = st.columns([2, 1], vertical_alignment="bottom")
    with order_column:
        order = st.selectbox(
            "카드 차례",
            options=list(BOARD_ORDERS),
            key=BOARD_ORDER_KEY,
            persist_state="session",
            help=(
                "보드와 공정 카드의 차례입니다(강조 공정은 늘 맨 위). 「기준선 대비 악화 먼저」 는 "
                "「진척 비교」 에서 기준선을 골랐을 때 씁니다 — 아니면 표시순서입니다."
            ),
        )
    with due_column:
        due = st.number_input(
            "기한 임박(일)",
            min_value=1,
            max_value=_DUE_DAYS_MAX,
            step=1,
            key=DUE_DAYS_KEY,
            persist_state="session",
            help=(
                "목표 Qual(신규는 필요 Qual)이 오늘부터 이 날수 안인 호기를 「기한 임박」 에 "
                "모읍니다."
            ),
        )
    if order == ORDER_WORSENED_FIRST and not compared:
        st.caption(
            "「기준선 대비 악화 먼저」 는 진척 비교를 고르면 씁니다 — 지금은 표시순서입니다."
        )
    return str(order), int(due)


def _board_view(board: pd.DataFrame, labels: ProcessLabels, *, compared: bool) -> pd.DataFrame:
    def earliest(value: object, left: object) -> str:
        if not isinstance(value, date):
            return _EMPTY
        days = int(str(left)) if left is not None and left is not pd.NA else None
        return f"{value:%Y-%m-%d}" + (f" (D-{days})" if days is not None else "")

    view = pd.DataFrame(
        {
            "공정": [labels.label(process) for process in board["공정"]],
            "첫 부족 달": [
                _EMPTY if month is None or month is pd.NA else month_label(int(str(month)))
                for month in board["첫 부족 달"]
            ],
            "월 최대 부족": board["월 최대 부족"].astype("float64"),
            "당길 호기": board["당길 호기"].astype("int64"),
            "단축일 합계": board["단축일 합계"].astype("int64"),
            "최대 단축": board["최대 단축"].astype("int64"),
            "신규": board["신규"].astype("int64"),
            "가장 이른 목표 Qual": [
                earliest(value, left)
                for value, left in zip(
                    board["가장 이른 목표 Qual"], board["남은 일수"], strict=True
                )
            ],
        }
    )
    if compared:
        view["기준선 대비"] = [str(text) if text else _EMPTY for text in board["기준선 대비"]]
        view["이행 지연"] = board["이행 지연"].fillna(0).astype("int64")
    return view


def render_progress_board(
    level_plan: LevelPlan,
    processes: Sequence[str],
    *,
    scope: Sequence[str],
    labels: ProcessLabels,
    today: date,
    months: Sequence[int],
    managers: Mapping[str, str],
    progress_rows: pd.DataFrame | None = None,
    delayed: pd.DataFrame | None = None,
) -> list[str]:
    """공정 진척 보드와 그 아래 기한 임박·이행 지연 — 고른 카드 차례의 공정 목록을 돌려준다.

    `processes` 는 카드로 세울 공정(표시순서), `scope` 는 기한 임박을 셀 범위(KPI 범위)다. 진척 비교
    행(`progress_rows`)과 이행 지연 표(`delayed`)는 진척 비교를 고른 회차에만 온다. 세울 공정이
    없으면 아무것도 그리지 않고 빈 목록이다.
    """
    if not processes:
        return []
    compared = progress_rows is not None
    board = process_board(
        level_plan,
        list(processes),
        today=today,
        months=months,
        progress_rows=progress_rows,
        delayed=delayed,
    )
    with st.container(border=True, gap="small"):
        st.markdown("**공정 진척 보드**")
        st.caption(
            "단축이 필요한 공정마다 한 줄입니다 — 줄을 고르면 그 공정 카드를 맨 위로 올려 "
            "강조합니다. 깊게 보려면 카드의 「공정 Capa 상세에서 근거 보기」 입니다."
        )
        order_name, due_days = _render_controls(compared=compared)
        order = board_order(board, order_name, compared=compared)
        ranked = board.set_index("공정").loc[order].reset_index()
        key = f"{_BOARD_KEY}_{_board_generation()}"
        st.dataframe(
            _board_view(ranked, labels, compared=compared),
            hide_index=True,
            width="stretch",
            key=key,
            on_select=partial(_pick_board_row, tuple(order), key),
            selection_mode="single-row",
            column_config={
                "월 최대 부족": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        _render_imminent(
            level_plan, scope, today=today, days=due_days, labels=labels, managers=managers
        )
        _render_delayed(delayed, labels=labels, compared=compared)
    return order


def _render_imminent(
    level_plan: LevelPlan,
    scope: Sequence[str],
    *,
    today: date,
    days: int,
    labels: ProcessLabels,
    managers: Mapping[str, str],
) -> None:
    imminent = imminent_units(level_plan, scope, today=today, days=days, managers=managers)
    with remembered_expander(
        f"기한 임박 {len(imminent)}대 — 목표 Qual 이 오늘부터 {days}일 안",
        key=_IMMINENT_EXPANDER_KEY,
        icon=":material/alarm:",
    ):
        if imminent.empty:
            st.caption("오늘부터 그 날수 안에 목표 Qual 이 드는 호기가 없습니다.")
            return
        view = imminent.copy()
        view["공정"] = [labels.label(process) for process in imminent["공정"]]
        view["목표 Qual"] = [f"{day:%Y-%m-%d}" for day in imminent["목표 Qual"]]
        # 빈 칸(신규 호기의 단축일수·담당자 없음)은 이행 지연 표처럼 「—」 다. 주지 않으면
        # Streamlit 이 그 칸에 「None」 글자를 그린다.
        st.dataframe(
            view,
            hide_index=True,
            width="stretch",
            placeholder=_EMPTY,
            key=_IMMINENT_TABLE_KEY,
        )
        new = int(imminent["구분"].eq(KIND_NEW).sum())
        if new:
            st.caption(
                f"신규 {new}대는 단축이 아니라 그날까지 Qual 을 마쳐야 하는 추가 호기입니다."
            )


def _render_delayed(delayed: pd.DataFrame | None, *, labels: ProcessLabels, compared: bool) -> None:
    if not compared:
        st.caption(
            ":material/history: 이행 지연은 「진척 비교」 에서 기준선을 고르면 봅니다 — "
            "기준선의 목표 Qual 이 지났는데 설비 마스터 Qual실적이 비었거나 Qual상태가 완료가 "
            "아닌 호기입니다."
        )
        return
    frame = delayed if delayed is not None else pd.DataFrame()
    with remembered_expander(
        f"이행 지연 {len(frame)}대 — 기준선 목표 Qual 이 지났는데 Qual 미완료",
        key=_DELAYED_EXPANDER_KEY,
        icon=":material/running_with_errors:",
    ):
        if frame.empty:
            st.caption("기준선 목표 Qual 이 지난 당긴 호기는 모두 Qual 을 마쳤습니다.")
            return

        def day(value: object) -> str:
            return f"{value:%Y-%m-%d}" if isinstance(value, date) else _EMPTY

        view = frame.copy()
        view["공정"] = [labels.label(process) for process in frame["공정"]]
        for column in ("기준선 목표 Qual", "Qual일정", "Qual실적"):
            view[column] = [day(value) for value in frame[column]]
        for column in view.columns:
            view[column] = pd.Series(
                [_EMPTY if pd.isna(value) else value for value in view[column]],
                index=view.index,
                dtype="object",
            )
        st.dataframe(view, hide_index=True, width="stretch", key=_DELAYED_TABLE_KEY)
