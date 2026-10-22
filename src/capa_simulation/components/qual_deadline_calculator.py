# Purpose: 가용설비 현황 「Qual 마감 계산기」 탭의 입력 칸·12개월 편집표와 계산 결과를 그린다.

"""Qual 마감 계산기 탭(2026-10-22 사용자 요청 — 10-07 의 계산기 한 장을 앱에 내장).

**다른 데이터와 잇지 않는다.** 설비 DB·시나리오·Cut-off 프로필을 읽지 않고 어디에도 쓰지 않는다 —
사람이 적은 Cut-off·목표·호기만으로 계산한다. 입력은 이 세션에만 남는다(새로 고치거나 다른 사람이
열면 예시에서 시작한다 — 원본은 브라우저 저장소에 남겼다. 그 차이를 메울지는 사용자 결정 대기다,
`docs/TODO.md` 2장 「Streamlit 화면」). 계산·글자는 `services/qual_deadline.py` 가 원본과 같게 내고,
이 파일은 칸을 받아 넘기고 결과를 그리기만 한다. 계산이 가벼워(12개월·호기 수십) 캐시하지 않는다.

**닫힌 탭에서는 그리지 않는다**(페이지가 `tab_is_hidden` 으로 건너뛴다). 그래도 입력은 남는다 —
숫자·날짜 칸은 `persist_state="session"` 이 지키고, 편집표는 고칠 때마다 `on_change` 콜백이 편집을
원본 표(`MONTHS_KEY`, 위젯 아닌 칸)에 옮겨 둔다. 콜백은 본문보다 먼저 돌므로, 칸을 고치고 바로 다른
탭을 눌러 두 조작이 한 회차에 와도(그 회차에는 편집표를 그리지 않는다) 고친 값이 남는다.

엑셀 여러 칸은 원본처럼 「엑셀에서 한 번에 붙여넣기」 칸(글 칸 + 「표에 넣기」)으로 받는다 — 규칙은
`parse_pasted_months`. 편집표에 바로 붙여 넣는 길은 덤이다: 표의 붙여넣기는 브라우저 클립보드 읽기라
보안 문맥이 아닌 주소(평문 HTTP 로 다른 호스트)에서는 아무것도 들어가지 않고, 신규 호기 칸 뒤의 칸은
버린다. 목표 칸에는 `step` 을 주지 않는다 — Streamlit 1.63 편집표는 `step` 의 소수 자릿수에서 값을
**잘라** 저장해(19.3456 → 19.34) 원본과 다른 마감을 낸다. 원본의 「복사」 두 단추는 같은 표를 CSV 로
내려받는 단추다(`table_toolbar` 관례 — 결과 표도 칸을 골라 Ctrl+C 로 복사된다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal, cast

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler
from streamlit.elements.lib.column_types import ColumnConfig

from capa_simulation.components.editor_state import discard_editor, editor_widget_key
from capa_simulation.components.status_metric import metric_row, render_status_metric
from capa_simulation.components.table_toolbar import render_csv_download
from capa_simulation.design import tokens
from capa_simulation.services.qual_deadline import (
    CHECK_TABLE_COLUMNS,
    EMPTY_UNITS_MESSAGE,
    EXAMPLE_BASE_UNITS,
    EXAMPLE_CUTOFF_DAYS,
    EXAMPLE_MONTHS,
    EXAMPLE_YEAR,
    MONTHS_PER_YEAR,
    PASTE_HINT,
    UNIT_TABLE_COLUMNS,
    CheckTableRow,
    QualDeadlineInput,
    QualDeadlineResult,
    QualMonthInput,
    UnitTableRow,
    VerdictTone,
    check_table_rows,
    compute_qual_deadlines,
    format_day,
    format_short_day,
    is_example,
    month_check_rows,
    parse_number,
    parse_pasted_months,
    unit_result_rows,
    unit_table_rows,
)
from capa_simulation.sidebar_status import remembered_expander

__all__ = [
    "BASE_KEY",
    "CUTOFF_KEY",
    "EDITOR_KEY",
    "MONTHS_KEY",
    "MONTH_COLUMN",
    "PASTE_APPLY_KEY",
    "PASTE_NOTICE_KEY",
    "PASTE_TEXT_KEY",
    "TARGET_COLUMN",
    "TODAY_KEY",
    "UNITS_COLUMN",
    "YEAR_KEY",
    "months_frame",
    "render_qual_deadline_calculator",
]

CUTOFF_KEY = "equipment_qualcalc_cutoff_v1"
YEAR_KEY = "equipment_qualcalc_year_v1"
BASE_KEY = "equipment_qualcalc_base_v1"
TODAY_KEY = "equipment_qualcalc_today_v1"
# 편집표의 원본 표(위젯 아닌 칸). 편집은 콜백이 여기에 옮기고, 되돌리기·비우기는 이 칸을 갈고
# 편집표를 `discard_editor` 로 버린다.
MONTHS_KEY = "equipment_qualcalc_months_v1"
EDITOR_KEY = "equipment_qualcalc_editor_v1"
_RESET_KEY = "equipment_qualcalc_reset_v1"
_CLEAR_KEY = "equipment_qualcalc_clear_v1"
# 「엑셀에서 한 번에 붙여넣기」 — 펼침 상자(닫힌 탭을 지나도 펼침을 기억한다)·폼·글 칸·
# 「표에 넣기」·알림. 글 칸은 입력 초안이라 `persist_state` 를 주지 않는다(AGENTS 9장 — 원본도
# 저장하지 않았다).
_PASTE_BOX_KEY = "equipment_qualcalc_paste_box_v1"
_PASTE_FORM_KEY = "equipment_qualcalc_paste_form_v1"
PASTE_TEXT_KEY = "equipment_qualcalc_paste_text_v1"
PASTE_APPLY_KEY = "equipment_qualcalc_paste_apply_v1"
PASTE_NOTICE_KEY = "equipment_qualcalc_paste_notice_v1"
_KPI_ROW_KEY = "equipment_qualcalc_kpis"
_UNITS_CSV_KEY = "equipment_qualcalc_units_csv_v1"
_MONTHS_CSV_KEY = "equipment_qualcalc_months_csv_v1"

MONTH_COLUMN = "월"
TARGET_COLUMN = "목표 가용대수"
UNITS_COLUMN = "신규 호기"
_EDITABLE_COLUMNS = (TARGET_COLUMN, UNITS_COLUMN)

# 원본 입력 칸의 범위 — 연도 2000~2100, Cut-off 0 이상(한 해를 넘는 납기는 받지 않는다).
_MIN_YEAR, _MAX_YEAR = 2000, 2100
_MAX_CUTOFF_DAYS = 365
_MIN_TODAY, _MAX_TODAY = date(_MIN_YEAR, 1, 1), date(_MAX_YEAR, 12, 31)
# 표 한 줄 높이는 앱의 편집 격자와 같다. 열두 달 표는 내용 높이로 다 보이고, 호기별 표는 이 줄 수를
# 넘으면 그 높이에서 스크롤한다.
_ROW_HEIGHT_PX = tokens.MONTH_GRID_ROW_HEIGHT_PX
_MAX_VISIBLE_UNIT_ROWS = 15
_SCROLLED_UNIT_TABLE_PX = (_MAX_VISIBLE_UNIT_ROWS + 1) * _ROW_HEIGHT_PX
# 호기별 표의 짧은 칸 폭 — 내용 폭에 맞춰 좁게 두어 긴 `메모` 칸이 결과 칸 안에서 더 보이게 한다.
_UNIT_COLUMN_PX = {
    "호기": 80,
    "쓰이는 달": 72,
    "그 달 기여": 80,
    "Qual 완료 마감": 108,
    "기여 시작": 96,
}
# 판정 칩·지난 마감 칸의 옅은 면 — 상태색을 표 면(`SURFACE`)에 섞은 불투명 색이라 그 위 본문 글자가
# 라이트·다크 모두 읽힌다. 짙기는 확보율 표의 부족 띠(0.12~0.3)보다 한 단 진하게 둔다 — 칸 하나다.
_TINT_ALPHA: dict[VerdictTone, float] = {"ok": 0.16, "warn": 0.28, "bad": 0.26}
_TONE_TOKEN: dict[VerdictTone, str] = {
    "ok": "ACCENT",
    "warn": "STATUS_WARNING",
    "bad": "STATUS_SHORTAGE",
}


def months_frame(months: Sequence[QualMonthInput]) -> pd.DataFrame:
    """편집표 원본 — 1~12월 줄. 목표를 비운 달은 빈칸(NaN), 호기 글은 빈 글이다."""
    padded = list(months[:MONTHS_PER_YEAR])
    padded += [QualMonthInput()] * (MONTHS_PER_YEAR - len(padded))
    return pd.DataFrame(
        {
            MONTH_COLUMN: [f"{month}월" for month in range(1, MONTHS_PER_YEAR + 1)],
            TARGET_COLUMN: pd.Series(
                [float("nan") if row.target is None else float(row.target) for row in padded],
                dtype="float64",
            ),
            UNITS_COLUMN: pd.Series([row.units_text for row in padded], dtype="object"),
        }
    )


def _seed_defaults(today: date) -> None:
    """처음 여는 세션은 원본 예시로 시작한다. 이미 적은 값(비운 칸 포함)은 건드리지 않는다."""
    st.session_state.setdefault(CUTOFF_KEY, EXAMPLE_CUTOFF_DAYS)
    st.session_state.setdefault(YEAR_KEY, EXAMPLE_YEAR)
    st.session_state.setdefault(BASE_KEY, EXAMPLE_BASE_UNITS)
    st.session_state.setdefault(TODAY_KEY, today)
    if not isinstance(st.session_state.get(MONTHS_KEY), pd.DataFrame):
        st.session_state[MONTHS_KEY] = months_frame(EXAMPLE_MONTHS)


def _reset_to_example(today: date) -> None:
    """「예시로 되돌리기」 — 원본 예시. 오늘은 원본이 박은 날 대신 실제 오늘이다."""
    st.session_state[CUTOFF_KEY] = EXAMPLE_CUTOFF_DAYS
    st.session_state[YEAR_KEY] = EXAMPLE_YEAR
    st.session_state[BASE_KEY] = EXAMPLE_BASE_UNITS
    st.session_state[TODAY_KEY] = today
    st.session_state[MONTHS_KEY] = months_frame(EXAMPLE_MONTHS)
    # 편집 델타는 행 위치라 새 표에 얹히면 되돌린 값을 다시 덮는다 — 편집표를 새 위젯으로 세운다.
    discard_editor(EDITOR_KEY)


def _clear_all() -> None:
    """「모두 비우기」 — 원본대로 Cut-off·연도·오늘은 두고 직전 달 가용대수와 열두 달을 비운다."""
    st.session_state[BASE_KEY] = None
    st.session_state[MONTHS_KEY] = months_frame(())
    discard_editor(EDITOR_KEY)


def _keep_editor_edits(widget_key: str) -> None:
    """편집표를 고칠 때마다 그 편집을 원본 표에 옮긴다(`on_change`).

    델타는 행 위치·칸 이름별 **값**이라, 옮긴 뒤 같은 델타가 다시 얹혀도 결과가 같다. 닫힌 탭에서는
    편집표를 그리지 않아 델타가 사라지므로 원본 표가 고친 값을 지킨다.
    """
    state = st.session_state.get(widget_key)
    base = st.session_state.get(MONTHS_KEY)
    if not isinstance(state, Mapping) or not isinstance(base, pd.DataFrame):
        return
    edited_rows = state.get("edited_rows")
    if not isinstance(edited_rows, Mapping) or not edited_rows:
        return
    merged = base.copy()
    for position, changes in edited_rows.items():
        row = int(position)
        if not 0 <= row < len(merged) or not isinstance(changes, Mapping):
            continue
        for column, value in changes.items():
            if column == TARGET_COLUMN:
                number = parse_number(value)
                merged.loc[row, TARGET_COLUMN] = float("nan") if number is None else number
            elif column == UNITS_COLUMN:
                merged.loc[row, UNITS_COLUMN] = "" if value is None else str(value)
    st.session_state[MONTHS_KEY] = merged


def _apply_pasted_months() -> None:
    """「표에 넣기」 — 원본 규칙(`parse_pasted_months`)으로 1월부터 붙여 넣은 줄 수만큼 달을
    갈고, 그 뒤 달은 그대로 둔다. 원본 토스트 글자를 알림 칸에 남긴다.

    갈았으면 편집표를 새 위젯으로 세운다 — 편집 델타는 행 위치라 그대로 두면 붙여 넣은 값을 다시
    덮는다(되돌리기와 같다). 그 앞 편집은 `on_change` 콜백이 이미 원본 표에 옮겨 두었다.
    """
    pasted = parse_pasted_months(st.session_state.get(PASTE_TEXT_KEY))
    current = st.session_state.get(MONTHS_KEY)
    table = current.copy() if isinstance(current, pd.DataFrame) else months_frame(())
    for row, month in enumerate(pasted.months):
        table.loc[row, TARGET_COLUMN] = float("nan") if month.target is None else month.target
        table.loc[row, UNITS_COLUMN] = month.units_text
    if pasted.months:
        st.session_state[MONTHS_KEY] = table
        discard_editor(EDITOR_KEY)
    st.session_state[PASTE_NOTICE_KEY] = (bool(pasted.months), pasted.message)


def _render_paste_notice() -> None:
    """「표에 넣기」 알림 — 한 번만 그린다. 늘 서 있는 한 칸 안이라 뒤 요소의 자리가 밀리지
    않는다."""
    notice = st.session_state.pop(PASTE_NOTICE_KEY, None)
    with st.container():
        if not (isinstance(notice, tuple) and len(notice) == 2):
            return
        applied, message = notice
        if applied:
            st.success(str(message), icon=":material/check_circle:")
        else:
            st.info(str(message), icon=":material/info:")


def _render_paste_box() -> None:
    """원본 「엑셀에서 한 번에 붙여넣기」 — 펼침 상자 안의 글 칸과 「표에 넣기」."""
    with remembered_expander(
        "엑셀에서 한 번에 붙여넣기", key=_PASTE_BOX_KEY, icon=":material/content_paste:"
    ):
        with st.form(_PASTE_FORM_KEY, border=False):
            st.caption(PASTE_HINT)
            st.text_area(
                "엑셀 붙여넣기 칸",
                key=PASTE_TEXT_KEY,
                height=150,
                label_visibility="collapsed",
            )
            st.form_submit_button(
                "표에 넣기",
                icon=":material/input:",
                key=PASTE_APPLY_KEY,
                on_click=_apply_pasted_months,
            )
        _render_paste_notice()


def _month_inputs(table: pd.DataFrame) -> tuple[QualMonthInput, ...]:
    months: list[QualMonthInput] = []
    for target, units in zip(table[TARGET_COLUMN], table[UNITS_COLUMN], strict=True):
        months.append(QualMonthInput(parse_number(target), units if isinstance(units, str) else ""))
    return tuple(months)


def _today_value() -> date | None:
    value = st.session_state.get(TODAY_KEY)
    return value if isinstance(value, date) else None


def _render_inputs(today: date) -> QualDeadlineInput:
    st.markdown("##### :material/edit_note: 입력")
    first, second = st.columns(2)
    with first:
        st.number_input(
            "Cut-off (일)",
            min_value=0,
            max_value=_MAX_CUTOFF_DAYS,
            step=1,
            value=None,
            key=CUTOFF_KEY,
            persist_state="session",
            help="그 공정을 끝낸 물건이 입고되기까지의 표준 납기(일)입니다. 비우면 0 입니다.",
        )
    with second:
        st.number_input(
            "연도",
            min_value=_MIN_YEAR,
            max_value=_MAX_YEAR,
            step=1,
            value=None,
            key=YEAR_KEY,
            persist_state="session",
        )
    third, fourth = st.columns(2)
    with third:
        st.number_input(
            "직전 달(전년 12월) 가용대수",
            step=0.01,
            value=None,
            key=BASE_KEY,
            persist_state="session",
            help="1월 앞까지 이미 있는 가용대수입니다. 비우면 0 입니다.",
        )
    with fourth:
        st.date_input(
            "오늘(지난 마감 표시용)",
            value=None,
            min_value=_MIN_TODAY,
            max_value=_MAX_TODAY,
            format="YYYY-MM-DD",
            key=TODAY_KEY,
            persist_state="session",
        )
    widget_key = editor_widget_key(EDITOR_KEY)
    edited = st.data_editor(
        st.session_state[MONTHS_KEY],
        key=widget_key,
        on_change=_keep_editor_edits,
        args=(widget_key,),
        hide_index=True,
        num_rows="fixed",
        disabled=[MONTH_COLUMN],
        width="stretch",
        height="content",
        row_height=_ROW_HEIGHT_PX,
        placeholder="",
        column_config={
            MONTH_COLUMN: st.column_config.TextColumn(MONTH_COLUMN, width="small"),
            # `step`·`format` 을 주지 않는다 — `step` 은 그 자릿수에서 값을 잘라 저장한다(모듈
            # 설명). 표시는 기본(소수 넷째 자리까지, 뒤 0 없음)이라 적은 값이 그대로 보인다.
            TARGET_COLUMN: st.column_config.NumberColumn(
                TARGET_COLUMN,
                help="그 달 W/D 구간 전체 기준 대수(소수 가능). 비우면 그 달은 판정하지 않습니다.",
            ),
            UNITS_COLUMN: st.column_config.TextColumn(
                UNITS_COLUMN,
                width="large",
                help="그 달 목표를 채울 차례대로 적습니다 — 쉼표·띄어쓰기·줄바꿈으로 나눕니다.",
            ),
        },
    )
    _render_paste_box()
    inputs = QualDeadlineInput(
        cutoff_days=parse_number(st.session_state.get(CUTOFF_KEY)),
        year=parse_number(st.session_state.get(YEAR_KEY)),
        base_units=parse_number(st.session_state.get(BASE_KEY)),
        today=_today_value(),
        months=_month_inputs(edited),
    )
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.button(
            "예시로 되돌리기",
            icon=":material/restart_alt:",
            key=_RESET_KEY,
            on_click=_reset_to_example,
            args=(today,),
        )
        st.button("모두 비우기", icon=":material/clear_all:", key=_CLEAR_KEY, on_click=_clear_all)
        if is_example(inputs, today):
            st.markdown(":orange-badge[지금 값은 예시입니다]", width="content")
    return inputs


def _tint(tone: VerdictTone) -> str:
    return tokens.opaque_mix(
        str(getattr(tokens, _TONE_TOKEN[tone])), tokens.SURFACE, _TINT_ALPHA[tone]
    )


def _unit_table_height(rows: int) -> int | Literal["content"]:
    return "content" if rows <= _MAX_VISIBLE_UNIT_ROWS else _SCROLLED_UNIT_TABLE_PX


def _units_styler(rows: list[UnitTableRow]) -> Styler:
    """호기별 표 — 마감 칸은 강조색 글자, 지난 마감은 부족색 면, 남은 호기 줄은 흐린 글자."""
    frame = pd.DataFrame([row.cells for row in rows], columns=list(UNIT_TABLE_COLUMNS))
    deadline = UNIT_TABLE_COLUMNS.index("Qual 완료 마감")
    past_fill = _tint("bad")

    def style(line: pd.Series) -> list[str]:
        meta = rows[cast(int, line.name)]
        if meta.leftover:
            return [f"color: {tokens.TEXT_MUTED}"] * len(line)
        styles = [""] * len(line)
        styles[deadline] = (
            f"background-color: {past_fill}; color: {tokens.TEXT}"
            if meta.past
            else f"color: {tokens.ACCENT}"
        )
        return styles

    styler = frame.style.apply(style, axis=1)
    # 고정 uuid — 내용이 같으면 회차마다 같은 메시지라 브라우저가 표를 다시 받지 않는다(9장).
    styler.set_uuid("equipment_qualcalc_units")
    return styler


def _checks_styler(rows: list[CheckTableRow]) -> Styler:
    """월 점검 표 — 판정 칸을 칩 색 면으로 칠한다(충족 강조색 · 목표 없음 경고색 · 부족 부족색)."""
    frame = pd.DataFrame([row.cells for row in rows], columns=list(CHECK_TABLE_COLUMNS))
    verdict_column = len(CHECK_TABLE_COLUMNS) - 1
    fills = {tone: _tint(tone) for tone in _TONE_TOKEN}

    def style(line: pd.Series) -> list[str]:
        styles = [""] * len(line)
        tone = rows[cast(int, line.name)].tone
        styles[verdict_column] = f"background-color: {fills[tone]}; color: {tokens.TEXT}"
        return styles

    styler = frame.style.apply(style, axis=1)
    styler.set_uuid("equipment_qualcalc_checks")
    return styler


def _csv_bytes(rows: list[list[str]]) -> bytes:
    """복사 표를 CSV 로 — 다른 설비 표와 같은 BOM 붙은 UTF-8. 열두 달·호기 수십 줄이라 회차마다
    만들어도 1ms 안이다(`cutoff_management` 의 Cut-off CSV 와 같다)."""
    return pd.DataFrame(rows[1:], columns=rows[0]).to_csv(index=False).encode("utf-8-sig")


def _text_column(
    label: str,
    *,
    right: bool = False,
    help: str | None = None,
    width: int | None = None,
    pinned: bool | None = None,
) -> ColumnConfig:
    return st.column_config.TextColumn(
        label, alignment="right" if right else None, help=help, width=width, pinned=pinned
    )


def _render_kpis(result: QualDeadlineResult) -> None:
    kpis = result.kpis
    with metric_row(key=_KPI_ROW_KEY):
        render_status_metric(
            "마감 낸 호기",
            f"{kpis.unit_count}대",
            key="equipment_qualcalc_kpi_units",
            help="목표를 채우는 데 쓰여 Qual 마감이 나온 호기 수입니다.",
        )
        render_status_metric(
            "가장 이른 마감",
            format_short_day(kpis.earliest_deadline) if kpis.earliest_deadline else "—",
            key="equipment_qualcalc_kpi_first",
            caption=format_day(kpis.earliest_deadline) if kpis.earliest_deadline else None,
        )
        render_status_metric(
            "이미 지난 마감",
            f"{kpis.past_count}대",
            key="equipment_qualcalc_kpi_past",
            tone="critical" if kpis.past_count else "neutral",
            help="마감이 「오늘」보다 앞선 호기 수입니다. 오늘을 비우면 세지 않습니다.",
        )
        render_status_metric(
            "목표 대비 부족 달",
            f"{kpis.short_months}개월",
            key="equipment_qualcalc_kpi_short",
            tone="critical" if kpis.short_months else "neutral",
            help="적은 호기를 다 써도 목표에 모자라는 달 수입니다.",
        )


def _render_heading(title: str, *, csv: bytes, file_name: str, key: str, label: str) -> None:
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f"##### {title}", width="content")
        render_csv_download(data=csv, file_name=file_name, key=key, label=label)


def _render_results(result: QualDeadlineResult) -> None:
    st.markdown("##### :material/insights: 결과")
    _render_kpis(result)

    unit_rows = unit_table_rows(result)
    _render_heading(
        "호기별 Qual 마감",
        csv=_csv_bytes(unit_result_rows(result)),
        file_name=f"qual_deadline_units_{result.year}.csv",
        key=_UNITS_CSV_KEY,
        label="호기별 결과 CSV",
    )
    if unit_rows:
        st.dataframe(
            _units_styler(unit_rows),
            hide_index=True,
            width="stretch",
            height=_unit_table_height(len(unit_rows)),
            row_height=_ROW_HEIGHT_PX,
            column_config={
                # 결과 칸이 좁으면 `메모` 까지 가로로 넘긴다 — 호기 이름은 붙박아 둔다.
                "호기": _text_column("호기", width=_UNIT_COLUMN_PX["호기"], pinned=True),
                "쓰이는 달": _text_column("쓰이는 달", width=_UNIT_COLUMN_PX["쓰이는 달"]),
                "그 달 기여": _text_column(
                    "그 달 기여",
                    right=True,
                    width=_UNIT_COLUMN_PX["그 달 기여"],
                    help=(
                        "1 보다 작으면 그 달 구간 일부만 채우면 되는 호기입니다 — 마감이 구간 "
                        "안쪽 날짜로 늦춰지고 다음 달부터 1대로 셉니다."
                    ),
                ),
                "Qual 완료 마감": _text_column(
                    "Qual 완료 마감",
                    help="이 날 Qual 을 끝내면 다음 날부터 기여합니다.",
                    width=_UNIT_COLUMN_PX["Qual 완료 마감"],
                ),
                "기여 시작": _text_column("기여 시작", width=_UNIT_COLUMN_PX["기여 시작"]),
                "메모": _text_column("메모"),
            },
        )
    else:
        st.caption(EMPTY_UNITS_MESSAGE)

    _render_heading(
        "월 점검",
        csv=_csv_bytes(month_check_rows(result)),
        file_name=f"qual_deadline_months_{result.year}.csv",
        key=_MONTHS_CSV_KEY,
        label="월 점검 CSV",
    )
    check_rows = check_table_rows(result)
    st.dataframe(
        _checks_styler(check_rows),
        hide_index=True,
        width="stretch",
        height="content",
        row_height=_ROW_HEIGHT_PX,
        column_config={
            "월": _text_column("월"),
            "W/D 구간": _text_column(
                "W/D 구간", help="(앞 경계, 끝] — 앞 경계 날은 앞 달 몫입니다."
            ),
            "목표": _text_column("목표", right=True),
            "기존 + 앞달 호기": _text_column(
                "기존 + 앞달 호기",
                right=True,
                help="직전 달 가용대수 + 앞 달까지 쓰인 호기가 이 달에 보태는 몫입니다.",
            ),
            "이 달 호기로 채움": _text_column("이 달 호기로 채움", right=True),
            "판정": _text_column("판정"),
        },
    )


def render_qual_deadline_calculator(*, today: date) -> None:
    """탭 본문 하나. `today` 는 「오늘」 칸의 처음 값이자 예시 표지가 견주는 날이다."""
    _seed_defaults(today)
    st.markdown("#### :material/calculate: Qual 마감 계산기")
    st.caption(
        "Cut-off · 월별 목표 가용대수 · 신규 호기를 넣으면 호기마다 Qual 완료 마감을 냅니다. "
        "설비 DB 와 잇지 않은 계산기라 적은 값은 이 화면에만 남습니다."
    )
    inputs_column, results_column = st.columns([5, 7], gap="medium")
    with inputs_column, st.container(border=True):
        inputs = _render_inputs(today)
    result = compute_qual_deadlines(inputs)
    with results_column, st.container(border=True):
        _render_results(result)
