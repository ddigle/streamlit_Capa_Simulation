# Purpose: 설비 마스터·비가동 이력을 편집하고 주차별 가용설비 및 변경 리비전 대시보드를 제공한다.

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from capa_simulation.components.availability_gap_panel import (
    GapSection,
    render_availability_gap_panel,
)
from capa_simulation.components.cutoff_management import render_cutoff_management
from capa_simulation.components.equipment_import_preview import (
    PINNED_COLUMNS,
    ImportPreviewResult,
    attribute_row_errors,
    build_preview_table,
    render_import_errors,
)
from capa_simulation.components.equipment_lifecycle_gantt import (
    render_equipment_lifecycle_gantt,
)
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.sample_data import (
    render_pending_source,
    render_sample_switch,
)
from capa_simulation.components.status_metric import (
    metric_row,
    render_status_metric,
    shortage_tone,
)
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.components.table_toolbar import CSV_TEMPLATE_LABEL, render_csv_download
from capa_simulation.components.table_view_controls import (
    TableView,
    merge_edited_rows,
    render_table_view_controls,
)
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    date_range_value,
    load_page_context,
)
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_snapshot_cache,
    get_equipment_repository,
    load_equipment_snapshot,
    load_floor_layout_canvases,
    load_latest_equipment_snapshot,
)
from capa_simulation.services.equipment_availability import (
    build_equipment_lifecycle_spans,
    build_equipment_status_as_of,
    build_inactive_equipment,
)
from capa_simulation.services.equipment_contract import (
    DATE_COLUMNS,
    DOWNTIME_TYPES,
    EQUIPMENT_STATUSES,
    QUAL_CONFIRMATION_STATUSES,
    STATUS_COUNT_COLUMNS,
    VALID_BUILDINGS,
    VALID_FLOORS,
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.services.equipment_csv import (
    baseline_csv_template,
    build_baseline_import_preview,
    build_downtime_import_preview,
    build_equipment_import_preview,
    downtime_csv_template,
    equipment_csv_template,
    merge_baseline_rows,
    merge_downtime_rows,
    merge_equipment_rows,
    read_baseline_clipboard,
    read_downtime_clipboard,
    read_equipment_clipboard,
    untouched_template_baseline_rows,
)
from capa_simulation.services.equipment_samples import (
    sample_downtime_schedule,
    sample_equipment_baseline,
    sample_equipment_master,
    untouched_sample_baseline_rows,
)
from capa_simulation.services.floor_layout_profile import max_canvas_extent
from capa_simulation.services.monthly_equipment_availability import (
    processes_in,
    span_date_range,
)
from capa_simulation.services.simulation_cache import (
    get_scenario_capacity_and_demand,
    get_weekly_equipment_availability,
    scenario_cache_key,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

FLASH_KEY = "equipment_status_flash"
# 탭 라벨은 `stateful_tabs` 의 기억값에 그대로 묶인다 — 문자열을 두 곳에 적으면 기억이
# 조용히 끊긴다. 선언은 여기 한 곳이다.
TAB_MAIN = ":material/dashboard: Main"
TAB_PREFERENCE = ":material/tune: Preference"
TAB_RAWDATA = ":material/table_rows: RawData"
EQUIPMENT_TAB_KEY = "equipment_active_tab"
# `Preference` 탭의 위젯 자리. `Main` 이 계산 전에 같은 칸을 읽으므로 문자열을 두 곳에
# 적지 않는다 — 갈라지면 화면은 멀쩡한데 값만 조용히 기본값으로 돌아간다.
START_DATE_KEY = "equipment_dashboard_start_date"
END_DATE_KEY = "equipment_dashboard_end_date"
LINE_TYPE_KEY = "equipment_dashboard_line_types"
UTILIZATION_TYPE_KEY = "equipment_dashboard_utilization_types"
LARGE_PROCESS_KEY = "equipment_dashboard_large_processes"
SMALL_PROCESS_KEY = "equipment_dashboard_small_processes"
BASELINE_EDITOR_KEY = "equipment_baseline_editor_v3"
EQUIPMENT_EDITOR_KEY = "equipment_master_editor_v3"
DOWNTIME_EDITOR_KEY = "equipment_downtime_editor_v3"
BASELINE_DRAFT_KEY = "equipment_baseline_draft_v3"
EQUIPMENT_DRAFT_KEY = "equipment_master_draft_v3"
DOWNTIME_DRAFT_KEY = "equipment_downtime_draft_v3"
DRAFT_REVISION_KEY = "equipment_draft_revision_v4"
BASELINE_IMPORT_KEY = "baseline_import_preview_rows_v3"
EQUIPMENT_IMPORT_KEY = "equipment_import_preview_rows_v3"
DOWNTIME_IMPORT_KEY = "downtime_import_preview_rows_v3"
# 붙여넣기 칸. 기존 리터럴을 상수로 올린 것이라 **값은 그대로**다 — 바꾸면 열려 있던
# 세션의 붙여넣은 글이 사라진다.
BASELINE_CLIPBOARD_KEY = "equipment_baseline_clipboard_v4"
EQUIPMENT_CLIPBOARD_KEY = "equipment_master_clipboard_v4"
DOWNTIME_CLIPBOARD_KEY = "equipment_downtime_clipboard_v4"
# 파싱이 실패한 붙여넣기의 판정(`ImportPreviewResult`). 성공한 붙여넣기는 여전히
# `*_IMPORT_KEY` 에 **DataFrame** 으로 들어간다 — 적용 경로의 계약이 그것이다.
BASELINE_IMPORT_ERROR_KEY = "baseline_import_row_errors_v1"
EQUIPMENT_IMPORT_ERROR_KEY = "equipment_import_row_errors_v1"
DOWNTIME_IMPORT_ERROR_KEY = "downtime_import_row_errors_v1"
# 오류 행 내려받기 버튼은 세 대상이 한 화면에 올 수 있으므로 키가 셋이어야 한다.
BASELINE_ERROR_DOWNLOAD_KEY = "equipment_baseline_import_error_rows_v1"
EQUIPMENT_ERROR_DOWNLOAD_KEY = "equipment_master_import_error_rows_v1"
DOWNTIME_ERROR_DOWNLOAD_KEY = "equipment_downtime_import_error_rows_v1"
# 적용 콜백이 `merge_*` 에서 받은 오류. 콜백은 `st.error` 를 부를 수 없어 본문에 넘긴다.
IMPORT_APPLY_ERROR_KEY = "equipment_import_apply_error_v1"
# 붙여넣기 대상 셋. 콜백 하나가 이 이름으로 자기 칸을 찾는다.
TARGET_BASELINE = "baseline"
TARGET_EQUIPMENT = "equipment"
TARGET_DOWNTIME = "downtime"
# 대상 → (붙여넣기 칸, 성공 칸, 오류 칸). 한 번에 하나만 살아 있어야 하므로 콜백이 이
# 표를 돌며 나머지 둘을 지운다.
IMPORT_SLOTS: dict[str, tuple[str, str, str]] = {
    TARGET_BASELINE: (BASELINE_CLIPBOARD_KEY, BASELINE_IMPORT_KEY, BASELINE_IMPORT_ERROR_KEY),
    TARGET_EQUIPMENT: (EQUIPMENT_CLIPBOARD_KEY, EQUIPMENT_IMPORT_KEY, EQUIPMENT_IMPORT_ERROR_KEY),
    TARGET_DOWNTIME: (DOWNTIME_CLIPBOARD_KEY, DOWNTIME_IMPORT_KEY, DOWNTIME_IMPORT_ERROR_KEY),
}

# **Main 이 답하는 질문 여섯.** 라벨이 곧 pill 의 값이고 세션에 그대로 저장되므로 문구를
# 바꾸면 기억값이 옵션에서 빠진다 — 그때는 아래 재선택 규칙이 마지막 달처럼 되돌린다.
QUESTION_STATUS = "지금 몇 대가 어느 상태인가"
QUESTION_SCHEDULE = "언제 몇 대가 쓸 수 있게 되나"
QUESTION_DOWNTIME = "어디가 비가동인가"
QUESTION_QUAL = "Qual 은 어디까지 왔나"
QUESTION_PROCESS = "공정별로는 어떤가"
QUESTION_GAP = "기준정보와 맞나 (Static·Dynamic)"
MAIN_QUESTIONS = (
    QUESTION_STATUS,
    QUESTION_SCHEDULE,
    QUESTION_DOWNTIME,
    QUESTION_QUAL,
    QUESTION_PROCESS,
    QUESTION_GAP,
)
# 기준 월을 옵션으로 갖는 질문들. 셋이 같은 시점을 공유해야 「10월」을 한 번만 고른다.
_MONTH_QUESTIONS = (QUESTION_STATUS, QUESTION_DOWNTIME, QUESTION_PROCESS)
MAIN_QUESTION_KEY = "equipment_main_question_v1"
ASOF_MONTH_KEY = "equipment_main_asof_month_v1"
STATUS_VIEW_KEY = "equipment_main_status_view_v1"
TIMELINE_VIEW_KEY = "equipment_main_timeline_view_v1"
QUAL_STATUS_KEY = "equipment_main_qual_status_v1"
PROCESS_SORT_KEY = "equipment_main_process_sort_v1"
DOWNTIME_VIEW_KEY = "equipment_main_downtime_view_v1"
GAP_SECTION_KEY = "equipment_main_gap_section_v1"
STATUS_VIEW_CHART = "막대"
STATUS_VIEW_TABLE = "표"
TIMELINE_VIEW_TREND = "합계 추이(주차)"
TIMELINE_VIEW_GANTT = "호기별 타임라인"
PROCESS_SORT_INACTIVE = "비가동 많은 순"
PROCESS_SORT_NAME = "공정명 순"
DOWNTIME_VIEW_MONTH = "그 달 전체"
DOWNTIME_VIEW_WEEK = "기준 주차 시점"
DOWNTIME_VIEW_SOURCE = "비가동 일정 원본"
GAP_SECTION_CHART = "월별 비교(그림)"
GAP_SECTION_BREAKDOWN = "분류 분해(표)"
GAP_SECTION_CROSSCHECK = "확보율 교차검증"
# 화면 라벨을 패널이 아는 이름으로 옮긴다. 라벨은 한국어로 바꿀 수 있어야 하고 패널의
# 인자는 계약이라 같은 문자열을 쓰지 않는다.
_GAP_SECTIONS: dict[str, GapSection] = {
    GAP_SECTION_CHART: "chart",
    GAP_SECTION_BREAKDOWN: "breakdown",
    GAP_SECTION_CROSSCHECK: "crosscheck",
}


def _filter_equipment(
    data: pd.DataFrame,
    *,
    line_types: list[str],
    utilization_types: list[str],
    large_processes: list[str],
    small_processes: list[str],
) -> pd.DataFrame:
    filtered = data
    for column, selected_values in (
        ("라인구분", line_types),
        ("활용구분", utilization_types),
        ("공정대분류", large_processes),
        ("공정소분류", small_processes),
    ):
        if selected_values:
            filtered = filtered.loc[filtered[column].isin(selected_values)]
    return filtered.copy()


def _filter_options(data: pd.DataFrame, column: str) -> list[str]:
    return sorted(data[column].dropna().astype(str).unique().tolist())


def _downtime_for_equipment(downtime: pd.DataFrame, equipment: pd.DataFrame) -> pd.DataFrame:
    return downtime.loc[downtime["호기"].isin(equipment["호기"])].copy()


def _reset_drafts() -> None:
    for key in (
        BASELINE_EDITOR_KEY,
        EQUIPMENT_EDITOR_KEY,
        DOWNTIME_EDITOR_KEY,
        BASELINE_DRAFT_KEY,
        EQUIPMENT_DRAFT_KEY,
        DOWNTIME_DRAFT_KEY,
        DRAFT_REVISION_KEY,
        BASELINE_IMPORT_KEY,
        EQUIPMENT_IMPORT_KEY,
        DOWNTIME_IMPORT_KEY,
        BASELINE_IMPORT_ERROR_KEY,
        EQUIPMENT_IMPORT_ERROR_KEY,
        DOWNTIME_IMPORT_ERROR_KEY,
        IMPORT_APPLY_ERROR_KEY,
    ):
        st.session_state.pop(key, None)


def _clipboard_parser(
    target: str,
    floor_canvases: dict[tuple[str, str], tuple[float, float]],
) -> Callable[[str], pd.DataFrame]:
    """붙여넣기 문자열 하나만 받는 파서로 묶는다.

    **편집본 프레임은 여기서 잡지 않고 호출될 때 세션에서 읽는다.** `args=` 로 묶어 넘기면
    콜백이 만들어지던 회차의 편집본이 그대로 굳어, 방금 적용한 행이 다음 검사에서 없는
    것으로 읽힌다. `floor_canvases` 는 DB 스냅샷이라 회차 사이에 바뀌지 않아 묶어도 된다.

    호기 마스터는 읽기만으로 끝나지 않는다 — 적용에서 도는 `merge_equipment_rows` ·
    `merge_downtime_rows` 까지 같이 돌려야 「편집본과 합쳤을 때 비로소 드러나는 잘못」
    (좌표 상한, 비가동이 매달린 호기가 사라지는 경우)이 미리보기 자리에서 잡힌다.
    """
    if target == TARGET_BASELINE:
        return read_baseline_clipboard

    if target == TARGET_EQUIPMENT:

        def parse_equipment(text: str) -> pd.DataFrame:
            incoming = read_equipment_clipboard(text, floor_canvases=floor_canvases)
            merged = merge_equipment_rows(
                st.session_state[EQUIPMENT_DRAFT_KEY],
                incoming,
                floor_canvases=floor_canvases,
            )
            merge_downtime_rows(
                st.session_state[DOWNTIME_DRAFT_KEY],
                empty_downtime_schedule(),
                equipment=merged,
            )
            return incoming

        return parse_equipment

    def parse_downtime(text: str) -> pd.DataFrame:
        return read_downtime_clipboard(text, equipment=st.session_state[EQUIPMENT_DRAFT_KEY])

    return parse_downtime


def _scan_clipboard(
    target: str,
    floor_canvases: dict[tuple[str, str], tuple[float, float]],
) -> None:
    """붙여넣은 글을 칸을 벗어나는 순간 검사한다.

    **`st.rerun()` 을 부르지 않는다.** `on_change` 콜백이 끝나면 Streamlit 이 이미 한 번
    다시 돌린다 — 여기서 또 부르면 그 회차가 통째로 버려지고 화면이 두 번 그려진다.
    """
    clipboard_key, import_key, error_key = IMPORT_SLOTS[target]
    # 한 번에 하나만 살아 있게 한다. 셋이 동시에 서면 어느 표에 적용하는 버튼인지 화면이
    # 말하지 못한다(지금 동작 그대로).
    for other, (_, other_import, other_error) in IMPORT_SLOTS.items():
        if other != target:
            st.session_state.pop(other_import, None)
            st.session_state.pop(other_error, None)
    st.session_state.pop(IMPORT_APPLY_ERROR_KEY, None)

    text = str(st.session_state.get(clipboard_key) or "")
    if not text.strip():
        st.session_state.pop(import_key, None)
        st.session_state.pop(error_key, None)
        return

    result = attribute_row_errors(text, _clipboard_parser(target, floor_canvases))
    if result.frame is not None:
        st.session_state[import_key] = result.frame
        st.session_state.pop(error_key, None)
    else:
        st.session_state[error_key] = result
        st.session_state.pop(import_key, None)


def _clear_import(target: str) -> None:
    """미리보기와 **붙여넣은 글**을 함께 비운다.

    적용을 마친 글이 칸에 남아 있으면 옆 위젯을 건드릴 때마다 같은 표가 다시 검사되고,
    다음 표를 붙여넣으려면 먼저 지워야 한다 — 30행 입력에서 가장 자주 걸리던 자리다.
    """
    clipboard_key, import_key, error_key = IMPORT_SLOTS[target]
    st.session_state.pop(import_key, None)
    st.session_state.pop(error_key, None)
    st.session_state.pop(IMPORT_APPLY_ERROR_KEY, None)
    st.session_state[clipboard_key] = ""


def _apply_baseline_import() -> None:
    incoming = st.session_state.get(BASELINE_IMPORT_KEY)
    if not isinstance(incoming, pd.DataFrame):
        return
    try:
        merged = merge_baseline_rows(st.session_state[BASELINE_DRAFT_KEY], incoming)
    except ValueError as exc:
        st.session_state[IMPORT_APPLY_ERROR_KEY] = str(exc)
        return
    st.session_state[BASELINE_DRAFT_KEY] = merged
    st.session_state.pop(BASELINE_EDITOR_KEY, None)
    _clear_import(TARGET_BASELINE)
    st.session_state[FLASH_KEY] = (
        f"기존 보유대수 붙여넣기 데이터 {len(incoming):,}행을 편집본에 "
        "적용했습니다. 아직 DuckDB에는 저장되지 않았습니다. 손대지 않은 개발 "
        "샘플 행이 남아 있으면 저장 전에 고치거나 지워야 합니다."
    )


def _apply_equipment_import(
    floor_canvases: dict[tuple[str, str], tuple[float, float]],
) -> None:
    incoming = st.session_state.get(EQUIPMENT_IMPORT_KEY)
    if not isinstance(incoming, pd.DataFrame):
        return
    try:
        merged_equipment = merge_equipment_rows(
            st.session_state[EQUIPMENT_DRAFT_KEY], incoming, floor_canvases=floor_canvases
        )
        merged_downtime = merge_downtime_rows(
            st.session_state[DOWNTIME_DRAFT_KEY],
            empty_downtime_schedule(),
            equipment=merged_equipment,
        )
    except ValueError as exc:
        st.session_state[IMPORT_APPLY_ERROR_KEY] = str(exc)
        return
    st.session_state[EQUIPMENT_DRAFT_KEY] = merged_equipment
    st.session_state[DOWNTIME_DRAFT_KEY] = merged_downtime
    st.session_state.pop(EQUIPMENT_EDITOR_KEY, None)
    st.session_state.pop(DOWNTIME_EDITOR_KEY, None)
    _clear_import(TARGET_EQUIPMENT)
    st.session_state[FLASH_KEY] = (
        f"호기 마스터 붙여넣기 데이터 {len(incoming):,}행을 편집본에 "
        "적용했습니다. 아직 DuckDB에는 저장되지 않았습니다."
    )


def _apply_downtime_import() -> None:
    incoming = st.session_state.get(DOWNTIME_IMPORT_KEY)
    if not isinstance(incoming, pd.DataFrame):
        return
    try:
        merged = merge_downtime_rows(
            st.session_state[DOWNTIME_DRAFT_KEY],
            incoming,
            equipment=st.session_state[EQUIPMENT_DRAFT_KEY],
        )
    except ValueError as exc:
        st.session_state[IMPORT_APPLY_ERROR_KEY] = str(exc)
        return
    st.session_state[DOWNTIME_DRAFT_KEY] = merged
    st.session_state.pop(DOWNTIME_EDITOR_KEY, None)
    _clear_import(TARGET_DOWNTIME)
    st.session_state[FLASH_KEY] = (
        f"비가동 일정 붙여넣기 데이터 {len(incoming):,}행을 편집본에 "
        "적용했습니다. 아직 DuckDB에는 저장되지 않았습니다."
    )


def _table_view_popover(
    data: pd.DataFrame,
    *,
    title: str,
    key_prefix: str,
    editor_key: str,
    filter_columns: tuple[str, ...],
    locked_columns: tuple[str, ...],
) -> TableView:
    """표 보기 설정 하나를 popover 안으로 접는다.

    셋을 세로로 쌓으면 편집표가 화면 한참 아래로 밀린다. 세 표의 설정을 **한 줄**에 세우고
    누를 때만 펴면 붙여넣기 바로 아래가 편집표 자리가 된다. popover 본문은 서버에서 늘
      그려지므로 「볼 컬럼」 선택값과 편집표 키 무효화는 접힌 동안에도 그대로 돈다.
    """
    label = f"{title} · 표 보기 설정"

    def controls() -> TableView:
        return render_table_view_controls(
            data,
            key_prefix=key_prefix,
            editor_key=editor_key,
            filter_columns=filter_columns,
            locked_columns=locked_columns,
            label=label,
        )

    if data.empty:
        # 빈 표에는 보기 설정이 없다 — `render_table_view_controls` 가 아무것도 그리지 않고
        # 돌아간다. popover 를 세우면 눌러도 빈 껍데기만 나온다.
        return controls()
    with st.popover(title, icon=":material/view_column:"):
        return controls()


def _render_import_error_preview(result: ImportPreviewResult, *, download_key: str) -> None:
    """오류 요약·행 목록·내려받기 아래에 **판정을 붙인 원문 표**를 그린다.

    `검증`·`행` 두 컬럼을 고정해 31컬럼을 가로로 밀어도 「몇 행이 왜 틀렸는가」가 화면에
    남는다. 검증을 통과하지 못한 표라 `build_*_import_preview`(신규·대체 판정)는 만들 수
    없고, 검증 없이 읽은 원문(`raw_frame`)에 판정만 얹는다.
    """
    render_import_errors(result, key=download_key)
    if result.raw_frame is None:
        return
    st.dataframe(
        build_preview_table(result.raw_frame, result),
        hide_index=True,
        width="stretch",
        column_config={column: st.column_config.Column(pinned=True) for column in PINNED_COLUMNS},
    )


def _import_summary(preview: pd.DataFrame) -> None:
    with st.container(horizontal=True):
        st.metric("Import 행", f"{len(preview):,}건", border=True)
        st.metric("신규", f"{int(preview['Import구분'].eq('신규').sum()):,}건", border=True)
        st.metric(
            "기존 대체",
            f"{int(preview['Import구분'].eq('대체').sum()):,}건",
            border=True,
        )


def _equipment_status_scale() -> alt.Scale:
    """설비 상태 9종에 고정 색을 준다.

    scale 을 생략하면 Altair 가 config.toml 의 chartCategoricalColors 4색을 순환해
    5~9번째 상태가 앞의 것과 같은 색으로 그려진다.
    """
    return alt.Scale(
        domain=list(tokens.EQUIPMENT_STAGE_COLORS),
        range=list(tokens.EQUIPMENT_STAGE_COLORS.values()),
    )


def _month_label(value: date) -> str:
    return f"{value:%Y-%m}"


def _month_label_of(year_month: int) -> str:
    """`YYYYMM` 정수를 화면이 쓰는 `YYYY-MM` 라벨로."""
    return f"{year_month // 100:04d}-{year_month % 100:02d}"


def _asof_month_options(weekly: pd.DataFrame) -> list[str]:
    """기준 월 목록.

    **주차 종료일이 그 달에 드는 달**만 고른다. 주차는 달을 걸쳐 있는데 이 화면의 주차 값은
    일요일 종료 시점의 상태라, 그 주차가 어느 달의 것인지는 종료일이 정한다.
    """
    if weekly.empty:
        return []
    return sorted({_month_label(value) for value in weekly["주차종료일"]})


def _asof_week(weekly: pd.DataFrame, month: str) -> pd.DataFrame:
    """고른 달의 **마지막 주차** 한 주. 옵션에 없는 달이면 조회기간의 마지막 주차다."""
    scoped = weekly.loc[weekly["주차종료일"].map(_month_label).eq(month)]
    week_start = (scoped if not scoped.empty else weekly)["주차시작일"].max()
    return weekly.loc[weekly["주차시작일"].eq(week_start)]


def _month_bounds(month: str) -> tuple[date, date]:
    """`YYYY-MM` 라벨의 첫날과 마지막 날."""
    year, month_no = (int(part) for part in month.split("-"))
    first = date(year, month_no, 1)
    last = date(year + 1, 1, 1) if month_no == 12 else date(year, month_no + 1, 1)
    return first, last - timedelta(days=1)


def _month_evaluation_moments(
    spans: pd.DataFrame, *, month_start: date, month_end: date
) -> list[date]:
    """그 달 안에서 **판정이 달라질 수 있는 날**. 월초 ∪ 구간 시작일 ∪ 주차 종료일.

    주차 종료일만 재면 월요일에 시작해 토요일에 끝난 비가동이 통째로 빠진다. 구간 시작일은
    `build_equipment_lifecycle_spans` 가 이미 「상태가 바뀔 수 있는 날」로 뽑아 둔 것이라
    여기서 규칙을 다시 적지 않아도 된다.
    """
    moments = {month_start}
    for value in spans["시작일"]:
        moment = value if isinstance(value, date) else pd.Timestamp(value).date()
        moments.add(min(max(moment, month_start), month_end))
    sunday = month_start + timedelta(days=(6 - month_start.weekday()) % 7)
    while sunday <= month_end:
        moments.add(sunday)
        sunday += timedelta(days=7)
    return sorted(moments)


def _inactive_equipment_in_month(
    equipment: pd.DataFrame,
    downtime: pd.DataFrame,
    *,
    moments: list[date],
) -> pd.DataFrame:
    """그 달 안에서 **한 번이라도** 비가동이었던 호기.

    상태 이름 화이트리스트로 고르지 않는다 — 「반출 예정」이 셋업을 덮는 호기가 통째로
    빠진다. 오늘 표와 같은 술어(`build_inactive_equipment` = 보유 & ~가용)를 시점마다 다시
    물어 `호기` 로 union 하고, 그 호기가 비가동으로 잡힌 시점의 최소·최대를 덧붙인다.
    """
    rows: dict[str, pd.Series] = {}
    caught: dict[str, list[date]] = {}
    empty: pd.DataFrame | None = None
    for moment in moments:
        frame = build_inactive_equipment(equipment, downtime, as_of=moment)
        if empty is None:
            empty = frame.iloc[0:0]
        for _, row in frame.iterrows():
            unit = str(row["호기"])
            caught.setdefault(unit, []).append(moment)
            rows.setdefault(unit, row)
    result = (
        pd.DataFrame(list(rows.values())).reset_index(drop=True)
        if rows
        else (empty if empty is not None else pd.DataFrame())
    )
    result.insert(1, "비가동 시작", [min(caught[unit]) for unit in rows])
    result.insert(2, "비가동 종료", [max(caught[unit]) for unit in rows])
    return result


def _format_equipment_count(value: float) -> str:
    """대수를 적는다. 주중에 상태가 바뀌면 소수가 나오므로 정수일 때만 소수점을 뗀다.

    설비 751대를 "751.0대" 로 적으면 계산이 어긋난 것처럼 읽힌다.
    """
    return f"{value:,.0f}대" if float(value).is_integer() else f"{value:,.1f}대"


render_page_header(
    "가용설비 현황 (Data확보중)",
    description=(
        "기존 보유대수와 31개 컬럼 호기 마스터, 운영 비가동 일정을 설비 전용 DuckDB "
        "불변 리비전으로 관리합니다."
    ),
)
flash = st.session_state.pop(FLASH_KEY, None)
if isinstance(flash, str):
    st.success(flash)

today = date.today()
try:
    equipment_database_path = str(EQUIPMENT_DUCKDB_PATH.resolve())
    repository = get_equipment_repository(equipment_database_path)
    # 층마다 캔버스가 달라 편집기 상한은 전 층 최댓값으로 열어 두고, 층별 범위는 붙여넣기·
    # 저장 시점에 호기 마스터 검증이 잡는다.
    floor_canvases = load_floor_layout_canvases(equipment_database_path)
    max_canvas_width, max_canvas_height = max_canvas_extent(floor_canvases)
    latest_snapshot = load_latest_equipment_snapshot(equipment_database_path)
    if latest_snapshot is None:
        saved_baseline = sample_equipment_baseline()
        saved_equipment = empty_equipment_master()
        saved_downtime = empty_downtime_schedule()
        revision_token = "empty"
    else:
        saved_baseline = latest_snapshot.baseline
        saved_equipment = latest_snapshot.equipment
        saved_downtime = latest_snapshot.downtime
        revision_token = latest_snapshot.revision.revision_id
    # **한 회차에 한 번만 읽는다.** Cut-off 편집 본문은 `Preference` 안이라 화면 순서상
    # 맨 뒤인데, 월별 Dynamic 가용대수는 그보다 먼저 그려진다. 여기서 읽어 양쪽에 같은
    # 값을 넘기면 어느 쪽이 먼저 그려지든 같은 수를 본다.
    stored_cutoff = repository.load_process_cutoff()
except BOOTSTRAP_ERRORS as exc:
    st.error(
        "설비 현황을 준비하지 못했습니다: "
        + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
    )
    st.stop()

if st.session_state.get(DRAFT_REVISION_KEY) != revision_token:
    st.session_state[BASELINE_DRAFT_KEY] = saved_baseline.copy()
    st.session_state[EQUIPMENT_DRAFT_KEY] = saved_equipment.copy()
    st.session_state[DOWNTIME_DRAFT_KEY] = saved_downtime.copy()
    st.session_state[DRAFT_REVISION_KEY] = revision_token
    for _clipboard_key, _import_key, _error_key in IMPORT_SLOTS.values():
        st.session_state.pop(_import_key, None)
        st.session_state.pop(_error_key, None)
        # 여기는 위젯이 만들어지기 **전**이라 붙여넣기 칸도 비울 수 있다. 저장으로 리비전이
        # 바뀌었는데 옛 글이 칸에 남아 있으면 다음 회차에 다시 검사된다.
        st.session_state.pop(_clipboard_key, None)
    st.session_state.pop(IMPORT_APPLY_ERROR_KEY, None)
# 세 표 모두 편집본을 본다. 대시보드가 저장본만 보면 붙여넣기 직후 기존 보유대수만
# 옛 값으로 남아 총대수·가용률이 호기 마스터와 어긋난다.
baseline = st.session_state[BASELINE_DRAFT_KEY].copy()
equipment = st.session_state[EQUIPMENT_DRAFT_KEY].copy()
downtime = st.session_state[DOWNTIME_DRAFT_KEY].copy()
using_dashboard_sample = equipment.empty
# 스위치는 **호기 마스터가 비었을 때만** 뜻이 있다. 실데이터가 있으면 끌 것이 없다.
show_sample_fleet = (
    render_sample_switch(key="equipment_sample_switch", source="설비 운영 DB")
    if using_dashboard_sample
    else True
)
dashboard_equipment = (
    sample_equipment_master(anchor_date=today)
    if using_dashboard_sample and show_sample_fleet
    else equipment
)
dashboard_downtime = (
    sample_downtime_schedule(anchor_date=today)
    if using_dashboard_sample and show_sample_fleet
    else downtime
)

# 조회기간·조회조건 위젯은 `Preference` 탭 안에서 그리지만 값은 `Main` 이 계산에 먼저
# 쓴다. **위젯이 아니라 세션 칸을 읽는다** — 닫힌 탭의 위젯은 그 회차에 만들어지지
# 않으므로 반환값을 기다리면 `Main` 을 볼 때마다 기본값으로 되돌아간다. 위젯이 `key` 로
# 쓰는 자리를 그대로 읽고, 사용자가 `Preference` 에서 바꾸면 다음 실행의 이 줄에 새 값이
# 들어온다. HOME 이 쓰는 방식과 같다.
DEFAULT_START_DATE = date(today.year, today.month, 1)
DEFAULT_END_DATE = today + timedelta(weeks=12)


def _session_date(key: str, default: date) -> date:
    value = st.session_state.get(key, default)
    return value if isinstance(value, date) else default


def _months_between(start: date, end: date) -> list[int]:
    """`start` 가 든 달부터 `end` 가 든 달까지 `YYYYMM` 목록.

    조회기간은 날짜 두 개인데 Static 가용대수는 월 단위다. 두 축을 맞추는 자리가 여기다.
    """
    if start > end:
        return []
    months: list[int] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _session_list(key: str) -> list[str]:
    value = st.session_state.get(key, [])
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else []


start_date = _session_date(START_DATE_KEY, DEFAULT_START_DATE)
end_date = _session_date(END_DATE_KEY, DEFAULT_END_DATE)
selected_line_types = _session_list(LINE_TYPE_KEY)
selected_utilization_types = _session_list(UTILIZATION_TYPE_KEY)
selected_large_processes = _session_list(LARGE_PROCESS_KEY)
selected_small_processes = _session_list(SMALL_PROCESS_KEY)

small_process_options = sorted(
    set(_filter_options(dashboard_equipment, "공정소분류"))
    | set(baseline["공정"].dropna().astype(str).unique().tolist())
)

main_tab, preference_tab, rawdata_tab = stateful_tabs(
    [TAB_MAIN, TAB_PREFERENCE, TAB_RAWDATA],
    key=EQUIPMENT_TAB_KEY,
)

with preference_tab:
    with st.container(border=True):
        st.markdown("#### :material/date_range: 조회기간 설정")
        st.caption(
            "가용설비 현황에만 적용되는 월요일 시작 ISO Weeknum 조회기간입니다. "
            "주차 값은 각 주 일요일 종료 시점의 상태입니다."
        )
        with st.container(horizontal=True, gap="small"):
            st.date_input(
                "시작일",
                value=DEFAULT_START_DATE,
                key=START_DATE_KEY,
                persist_state="session",
                width=180,
            )
            st.date_input(
                "종료일",
                value=DEFAULT_END_DATE,
                key=END_DATE_KEY,
                persist_state="session",
                width=180,
            )
        covered_months = _months_between(start_date, end_date)
        if covered_months:
            st.caption(
                "조회기간이 덮는 달: "
                f"{_month_label_of(covered_months[0])} ~ {_month_label_of(covered_months[-1])} "
                "(Main 의 기준 월)"
            )
        st.caption("라인·활용·공정 조건은 Main 의 질문 옆으로 옮겼습니다.")

    # **Cut-off 는 「고르는 곳」이다.** 한 번 적고 나면 다시 들어올 일이 드문 기준값이라
    # 탭 하나를 상시 차지할 자리가 아니었다. 조회기간·조회 조건과 같은 성격이라 여기로
    # 모은다 — 저장 경로와 계약은 그대로다(`equipment_ops.process_cutoff`, 전체 교체).
    with st.container(border=True):
        render_cutoff_management(
            repository,
            equipment_processes=processes_in(dashboard_equipment, baseline),
            stored=stored_cutoff,
        )

with main_tab:
    # **이 탭은 답을 하나만 그린다.** 여섯 구획을 세로로 쌓으면 「어느 것이 내가 찾던
    # 양식인지」부터 찾아야 한다. 질문을 고르면 그 질문에만 딸린 옵션 줄이 서고 그 아래
    # 답 하나가 선다 — 나머지 다섯은 아예 그리지 않는다(계산도 하지 않는다).
    if using_dashboard_sample and show_sample_fleet:
        st.caption(
            "호기 마스터가 비어 있어 생애주기 상태를 모두 덮는 데모 fleet 을 표시합니다. "
            "샘플은 DuckDB에 저장되지 않으며 실제 호기 리비전이 저장되면 자동으로 대체됩니다."
        )
    elif latest_snapshot is not None:
        st.caption(
            f"현재 적용 이력: r{latest_snapshot.revision.revision_no} · "
            f"{latest_snapshot.revision.created_at:%Y-%m-%d %H:%M}"
        )
    st.caption(f"조회기간 {start_date:%Y-%m-%d} ~ {end_date:%Y-%m-%d} · Preference 에서 바꿉니다")

    filtered_equipment = _filter_equipment(
        dashboard_equipment,
        line_types=selected_line_types,
        utilization_types=selected_utilization_types,
        large_processes=selected_large_processes,
        small_processes=selected_small_processes,
    )
    filtered_downtime = _downtime_for_equipment(dashboard_downtime, filtered_equipment)
    filtered_baseline = baseline.copy()
    if selected_small_processes:
        filtered_baseline = filtered_baseline.loc[
            filtered_baseline["공정"].isin(selected_small_processes)
        ].copy()

    # **주차 집계는 질문과 무관하게 항상 낸다.** 기준 월 목록이 이 결과에서 나오고, 캐시된
    # 함수라 같은 입력에서 두 번 계산되지 않는다.
    if start_date > end_date:
        st.error("설비 대시보드 시작일은 종료일보다 늦을 수 없습니다.")
        weekly = pd.DataFrame()
    else:
        try:
            weekly = get_weekly_equipment_availability(
                filtered_baseline,
                filtered_equipment,
                filtered_downtime,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError as exc:
            st.error(str(exc))
            weekly = pd.DataFrame()

    # **`default=` 를 주지 않는다.** `key` 로 세션에 값이 있는 위젯에 `default=` 를 함께
    # 주면 매 회차 「created with a default value but also had its value set via the
    # Session State API」 경고가 뜬다. 기본값은 세션에 심고 위젯은 그 칸만 본다.
    if MAIN_QUESTION_KEY not in st.session_state:
        st.session_state[MAIN_QUESTION_KEY] = QUESTION_STATUS
    st.pills(
        "무엇을 볼까요",
        options=MAIN_QUESTIONS,
        selection_mode="single",
        required=True,
        key=MAIN_QUESTION_KEY,
        persist_state="session",
        label_visibility="collapsed",
        width="stretch",
    )
    question = str(st.session_state[MAIN_QUESTION_KEY])

    month_options = _asof_month_options(weekly)
    if month_options:
        remembered_month = st.session_state.get(ASOF_MONTH_KEY)
        if not isinstance(remembered_month, str) or remembered_month not in month_options:
            # 기억값이 옵션에 없으면 **렌더 전에** 갈아 끼운다. 위젯을 만든 뒤에 고치면
            # 이미 만들어진 위젯의 키를 본문에서 쓰는 꼴이라 예외가 난다.
            st.session_state[ASOF_MONTH_KEY] = month_options[-1]

    # 옵션 줄. 왼쪽은 고른 질문 전용이고 오른쪽 둘은 여섯 질문이 함께 쓰는 조회 조건이다.
    # **선택되지 않은 질문의 옵션 위젯은 그리지 않는다** — 값은 `persist_state` 가 지킨다.
    with st.container(horizontal=True, border=True, vertical_alignment="bottom", gap="medium"):
        if question in _MONTH_QUESTIONS and month_options:
            st.pills(
                "기준 월",
                options=month_options,
                selection_mode="single",
                required=True,
                key=ASOF_MONTH_KEY,
                persist_state="session",
                help="그 달에 **주차 종료일이 드는** 마지막 주차 시점으로 봅니다.",
            )
        if question == QUESTION_STATUS:
            if STATUS_VIEW_KEY not in st.session_state:
                st.session_state[STATUS_VIEW_KEY] = STATUS_VIEW_CHART
            st.segmented_control(
                "보기",
                options=(STATUS_VIEW_CHART, STATUS_VIEW_TABLE),
                selection_mode="single",
                required=True,
                key=STATUS_VIEW_KEY,
                persist_state="session",
            )
        elif question == QUESTION_SCHEDULE:
            if TIMELINE_VIEW_KEY not in st.session_state:
                st.session_state[TIMELINE_VIEW_KEY] = TIMELINE_VIEW_TREND
            st.segmented_control(
                "보기",
                options=(TIMELINE_VIEW_TREND, TIMELINE_VIEW_GANTT),
                selection_mode="single",
                required=True,
                key=TIMELINE_VIEW_KEY,
                persist_state="session",
            )
        elif question == QUESTION_DOWNTIME:
            if DOWNTIME_VIEW_KEY not in st.session_state:
                st.session_state[DOWNTIME_VIEW_KEY] = DOWNTIME_VIEW_MONTH
            st.segmented_control(
                "보기",
                options=(DOWNTIME_VIEW_MONTH, DOWNTIME_VIEW_WEEK, DOWNTIME_VIEW_SOURCE),
                selection_mode="single",
                required=True,
                key=DOWNTIME_VIEW_KEY,
                persist_state="session",
            )
        elif question == QUESTION_QUAL:
            if QUAL_STATUS_KEY not in st.session_state:
                st.session_state[QUAL_STATUS_KEY] = []
            st.pills(
                "확정상태",
                options=list(QUAL_CONFIRMATION_STATUSES),
                selection_mode="multi",
                key=QUAL_STATUS_KEY,
                persist_state="session",
                help="고르지 않으면 전체입니다.",
            )
        elif question == QUESTION_GAP:
            if GAP_SECTION_KEY not in st.session_state:
                st.session_state[GAP_SECTION_KEY] = GAP_SECTION_CHART
            st.segmented_control(
                "보기",
                options=(GAP_SECTION_CHART, GAP_SECTION_BREAKDOWN, GAP_SECTION_CROSSCHECK),
                selection_mode="single",
                required=True,
                key=GAP_SECTION_KEY,
                persist_state="session",
            )
        elif question == QUESTION_PROCESS:
            if PROCESS_SORT_KEY not in st.session_state:
                st.session_state[PROCESS_SORT_KEY] = PROCESS_SORT_INACTIVE
            st.segmented_control(
                "정렬",
                options=(PROCESS_SORT_INACTIVE, PROCESS_SORT_NAME),
                selection_mode="single",
                required=True,
                key=PROCESS_SORT_KEY,
                persist_state="session",
            )
        # 공정소분류는 **탭을 옮기지 않고** 좁히는 자리라 옵션 줄에 펴 둔다. 나머지 셋은
        # 처음 여는 사람이 거의 쓰지 않아 popover 안에 접고, 몇 개가 걸렸는지만 라벨에 적는다.
        st.multiselect(
            "공정소분류",
            options=small_process_options,
            placeholder="전체",
            key=SMALL_PROCESS_KEY,
            persist_state="session",
            width=300,
        )
        active_conditions = sum(
            1
            for values in (
                selected_line_types,
                selected_utilization_types,
                selected_large_processes,
            )
            if values
        )
        with st.popover(f"조회 조건 ({active_conditions})", icon=":material/filter_alt:"):
            st.multiselect(
                "라인구분",
                options=_filter_options(dashboard_equipment, "라인구분"),
                placeholder="전체",
                key=LINE_TYPE_KEY,
                persist_state="session",
                width=220,
            )
            st.multiselect(
                "활용구분",
                options=_filter_options(dashboard_equipment, "활용구분"),
                placeholder="전체",
                key=UTILIZATION_TYPE_KEY,
                persist_state="session",
                width=220,
            )
            st.multiselect(
                "공정대분류",
                options=_filter_options(dashboard_equipment, "공정대분류"),
                placeholder="전체",
                key=LARGE_PROCESS_KEY,
                persist_state="session",
                width=260,
            )
            st.caption(
                "기존 보유대수에는 라인·활용·공정대분류 정보가 없으므로 공정소분류 조건만 "
                "적용되고, 나머지 조건은 호기 마스터 설비에 적용됩니다."
            )

    # 숨은 탭에서는 위젯만 그리고 답은 그리지 않는다. 본문을 통째로 접으면 위 위젯의
    # 선택값이 버려지고, 답을 그리면 보이지도 않는 Plotly·Altair 를 매 회차 만든다.
    if not tab_is_hidden(main_tab):
        if not show_sample_fleet:
            render_pending_source(
                subject="가용설비 현황",
                source="설비 운영 DB",
                expects=(
                    "호기 마스터 31컬럼 — 특히 **제진대·물류·입고·Qual·반출·이설** 여섯 일정. "
                    "이 여섯 개가 생애주기 구간과 주차별 가용대수를 모두 만듭니다",
                    "동·층·좌표·크기 — Space 배치도가 이 값으로 그려집니다",
                    "운영 비가동 일정(호기 · 유형 · 시작일 · 종료일)",
                    "공정별 **기존 보유대수** — 호기 마스터에 없는 기존 설비의 출발점입니다",
                ),
            )
        elif weekly.empty and start_date <= end_date:
            st.info("집계할 기존 보유대수 또는 호기 마스터가 없습니다.")
        elif not weekly.empty:
            selected_month = str(st.session_state.get(ASOF_MONTH_KEY, month_options[-1]))
            asof_week = _asof_week(weekly, selected_month)
            asof_week_end = asof_week["주차종료일"].max()
            asof_weeknum = str(asof_week["Weeknum"].iloc[0])

            if question == QUESTION_STATUS:
                trend = (
                    weekly.groupby(["주차시작일", "Weeknum"], as_index=False)[
                        ["가용대수", "비가동대수"]
                    ]
                    .sum()
                    .sort_values("주차시작일")
                )
                total_count = float(asof_week["총대수"].sum())
                available_count = float(asof_week["가용대수"].sum())
                inactive_count = float(asof_week["비가동대수"].sum())
                # 카드마다 자기 주차 추이를 스파크라인으로 함께 보여준다. 한 주 값만으로는
                # 늘고 있는지 줄고 있는지 알 수 없어 아래 차트를 열어야 했다. 네 장 모두에
                # 넣어야 카드 높이가 어긋나지 않는다.
                weekly_total = trend["가용대수"] + trend["비가동대수"]
                weekly_rate = (trend["가용대수"] / weekly_total.where(weekly_total.ne(0))).fillna(
                    0.0
                )
                st.caption(f"{selected_month} 마지막 주 기준 · {asof_weeknum}")
                with metric_row(key="equipment_weekly_metrics"):
                    st.metric(
                        "총대수",
                        _format_equipment_count(total_count),
                        chart_data=weekly_total,
                        chart_type="area",
                        border=True,
                    )
                    st.metric(
                        "가용대수",
                        _format_equipment_count(available_count),
                        chart_data=trend["가용대수"],
                        chart_type="area",
                        border=True,
                    )
                    render_status_metric(
                        "비가동대수",
                        _format_equipment_count(inactive_count),
                        key="equipment_inactive_count",
                        tone=shortage_tone(int(inactive_count > 0)),
                        chart_data=trend["비가동대수"],
                    )
                    st.metric(
                        "가용률",
                        f"{available_count / total_count if total_count else 0:.1%}",
                        chart_data=weekly_rate,
                        chart_type="area",
                        border=True,
                    )

                unit_status = build_equipment_status_as_of(
                    filtered_equipment, filtered_downtime, as_of=asof_week_end
                )
                status_counts = (
                    unit_status["상태"]
                    .value_counts()
                    .reindex(EQUIPMENT_STATUSES, fill_value=0)
                    .rename_axis("상태")
                    .rename("호기대수")
                    .reset_index()
                )
                with st.container(border=True):
                    st.markdown("#### 호기 생애주기 상태 모니터링")
                    st.caption(
                        "상태는 호기별로 하나만 부여합니다. 반출·이설 예정 호기는 실행일 전까지 "
                        "보유·가용 산정에 포함되며, 기존 보유대수 집계는 호기 상태에서 제외됩니다."
                    )
                    if st.session_state[STATUS_VIEW_KEY] == STATUS_VIEW_TABLE:
                        st.dataframe(status_counts, hide_index=True, width="stretch")
                    else:
                        status_chart = (
                            alt.Chart(status_counts)
                            .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                            .encode(
                                y=alt.Y(
                                    "상태:N",
                                    sort=list(EQUIPMENT_STATUSES),
                                    axis=alt.Axis(title=None, labelFontSize=13),
                                ),
                                x=alt.X(
                                    "호기대수:Q",
                                    axis=alt.Axis(title=None, tickMinStep=1, labelFontSize=13),
                                ),
                                color=alt.Color(
                                    "상태:N", scale=_equipment_status_scale(), legend=None
                                ),
                                tooltip=("상태:N", "호기대수:Q"),
                            )
                            .properties(height=300)
                        )
                        st.altair_chart(status_chart, width="stretch")

            elif question == QUESTION_SCHEDULE:
                if st.session_state[TIMELINE_VIEW_KEY] == TIMELINE_VIEW_GANTT:
                    with st.container(border=True):
                        st.markdown("#### 호기별 생애주기 일정")
                        st.caption(
                            "날짜 컬럼은 점이라 표로는 그 사이 간격이 보이지 않습니다. "
                            "구간 판정은 「지금 몇 대가 어느 상태인가」의 상태 막대와 같은 "
                            "규칙입니다."
                        )
                        try:
                            lifecycle_spans = build_equipment_lifecycle_spans(
                                filtered_equipment,
                                filtered_downtime,
                                start_date=start_date,
                                end_date=end_date,
                            )
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            render_equipment_lifecycle_gantt(
                                lifecycle_spans,
                                key="equipment_lifecycle_gantt",
                                today=today,
                                owner_tab=main_tab,
                            )
                else:
                    trend = (
                        weekly.groupby(["주차시작일", "Weeknum"], as_index=False)[
                            ["가용대수", "비가동대수"]
                        ]
                        .sum()
                        .sort_values("주차시작일")
                    )
                    trend_long = trend.melt(
                        id_vars=["주차시작일", "Weeknum"],
                        value_vars=["가용대수", "비가동대수"],
                        var_name="상태",
                        value_name="대수",
                    )
                    with st.container(border=True):
                        st.markdown("#### 주차별 설비 현황")
                        chart = (
                            alt.Chart(trend_long)
                            .mark_bar()
                            .encode(
                                x=alt.X(
                                    "Weeknum:N",
                                    sort=trend["Weeknum"].tolist(),
                                    axis=alt.Axis(title=None, labelAngle=0, labelFontSize=14),
                                ),
                                y=alt.Y(
                                    "sum(대수):Q",
                                    stack="zero",
                                    axis=alt.Axis(title=None, labelFontSize=14),
                                ),
                                color=alt.Color(
                                    "상태:N",
                                    scale=_equipment_status_scale(),
                                    legend=alt.Legend(title=None, labelFontSize=14),
                                ),
                                tooltip=(
                                    alt.Tooltip("Weeknum:N", title="Weeknum"),
                                    alt.Tooltip("상태:N", title="상태"),
                                    alt.Tooltip("대수:Q", title="대수", format=".1f"),
                                ),
                            )
                            .properties(height=360)
                        )
                        st.altair_chart(chart, width="stretch")

            elif question == QUESTION_DOWNTIME:
                downtime_view_mode = str(st.session_state[DOWNTIME_VIEW_KEY])
                month_start, month_end = _month_bounds(selected_month)
                with st.container(border=True):
                    st.markdown("#### 비가동 설비호기")
                    if downtime_view_mode == DOWNTIME_VIEW_WEEK:
                        # **옛 표 그대로다.** 한 시점을 찍어 보는 자리를 잃지 않는다.
                        inactive_equipment = build_inactive_equipment(
                            filtered_equipment, filtered_downtime, as_of=asof_week_end
                        )
                        st.caption(
                            f"{asof_week_end:%Y-%m-%d} 기준 보유 중이지만 가용이 아닌 "
                            "셋업·보관·운영 비가동 호기입니다."
                        )
                        if inactive_equipment.empty:
                            st.success("해당 주차에 비가동 설비호기가 없습니다.")
                        else:
                            st.dataframe(
                                inactive_equipment,
                                hide_index=True,
                                width="stretch",
                                column_config={
                                    column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
                                    for column in DATE_COLUMNS
                                },
                            )
                    elif downtime_view_mode == DOWNTIME_VIEW_SOURCE:
                        # **`.dt.date` 로 비교하지 않는다.** 종료일이 전부 비어 있는 편집본에서
                        # `datetime64` 가 그대로 나와 `date` 와의 비교가 `TypeError` 로 죽는다.
                        starts = pd.to_datetime(filtered_downtime["시작일"], errors="coerce")
                        ends = pd.to_datetime(filtered_downtime["종료일"], errors="coerce")
                        overlaps = starts.le(pd.Timestamp(month_end)) & (
                            ends.isna() | ends.ge(pd.Timestamp(month_start))
                        )
                        source_rows = filtered_downtime.loc[overlaps]
                        st.caption(
                            f"{selected_month} 과 겹치는 **운영 비가동 일정 원본 행**입니다. "
                            "위 두 보기가 센 것이 어느 줄에서 나왔는지를 여기서 봅니다."
                        )
                        if source_rows.empty:
                            st.success("그 달과 겹치는 비가동 일정이 없습니다.")
                        else:
                            st.dataframe(
                                source_rows,
                                hide_index=True,
                                width="stretch",
                                column_config={
                                    column: st.column_config.DateColumn(column, format="YYYY-MM-DD")
                                    for column in ("시작일", "종료일")
                                },
                            )
                    else:
                        try:
                            month_spans = build_equipment_lifecycle_spans(
                                filtered_equipment,
                                filtered_downtime,
                                start_date=month_start,
                                end_date=month_end,
                            )
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            moments = _month_evaluation_moments(
                                month_spans, month_start=month_start, month_end=month_end
                            )
                            inactive_in_month = _inactive_equipment_in_month(
                                filtered_equipment, filtered_downtime, moments=moments
                            )
                            st.caption(
                                f"{selected_month} 안에서 **한 번이라도** 비가동이었던 호기입니다. "
                                f"구간이 바뀌는 날짜마다 재었습니다(시점 {len(moments)}개). "
                                "주차 종료일만 보면 주중에 시작해 주말 전에 끝난 비가동이 "
                                "빠집니다. "
                                "원천 행은 「비가동 일정 원본」 보기에 있습니다."
                            )
                            if inactive_in_month.empty:
                                st.success("그 달에 비가동 설비호기가 없습니다.")
                            else:
                                st.dataframe(
                                    inactive_in_month,
                                    hide_index=True,
                                    width="stretch",
                                    column_config={
                                        column: st.column_config.DateColumn(
                                            column, format="YYYY-MM-DD"
                                        )
                                        for column in (*DATE_COLUMNS, "비가동 시작", "비가동 종료")
                                    },
                                )

            elif question == QUESTION_QUAL:
                # Qual 은 「지금 어디까지 왔나」라 조회기간의 마지막 주차로 본다 — 기준 월을
                # 거슬러 올라가면 그때의 계획을 보는 것이라 실행관리의 뜻이 달라진다.
                last_week_end = weekly["주차종료일"].max()
                unit_status = build_equipment_status_as_of(
                    filtered_equipment, filtered_downtime, as_of=last_week_end
                )
                qual_execution = unit_status.loc[unit_status["Qual일정"].notna()].copy()
                selected_confirmations = _session_list(QUAL_STATUS_KEY)
                if selected_confirmations:
                    qual_execution = qual_execution.loc[
                        qual_execution["확정상태"].isin(selected_confirmations)
                    ]
                confirmation_counts = (
                    qual_execution["확정상태"]
                    .value_counts()
                    .reindex(QUAL_CONFIRMATION_STATUSES, fill_value=0)
                    .rename_axis("확정상태")
                    .rename("호기대수")
                    .reset_index()
                )
                with st.container(border=True):
                    st.markdown("#### Qual 확정상태 실행관리")
                    st.caption(
                        "확정상태는 Qual 일정의 계획·확정·완료·지연만 관리합니다. "
                        "가용대수는 기존 규칙대로 Qual일정을 기준으로 계산합니다."
                    )
                    with metric_row(key="equipment_qual_confirmation_metrics"):
                        st.metric("Qual 대상", f"{len(qual_execution):,}대", border=True)
                        for confirmation_status in QUAL_CONFIRMATION_STATUSES:
                            count = int(
                                confirmation_counts.loc[
                                    confirmation_counts["확정상태"].eq(confirmation_status),
                                    "호기대수",
                                ].sum()
                            )
                            st.metric(confirmation_status, f"{count:,}대", border=True)
                    if not qual_execution.empty:
                        st.dataframe(
                            qual_execution.loc[
                                :,
                                [
                                    "호기",
                                    "공정대분류",
                                    "공정소분류",
                                    "Qual일정",
                                    "확정상태",
                                    "상태",
                                ],
                            ].sort_values(["Qual일정", "호기"]),
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "Qual일정": st.column_config.DateColumn(format="YYYY-MM-DD")
                            },
                        )

            elif question == QUESTION_PROCESS:
                breakdown_columns = (
                    "공정소분류",
                    "기존보유대수",
                    "추가설비대수",
                    "총대수",
                    "가용대수",
                    "비가동대수",
                    *STATUS_COUNT_COLUMNS.values(),
                )
                if st.session_state[PROCESS_SORT_KEY] == PROCESS_SORT_NAME:
                    breakdown = asof_week.loc[:, breakdown_columns].sort_values("공정소분류")
                else:
                    breakdown = asof_week.loc[:, breakdown_columns].sort_values(
                        ["비가동대수", "공정소분류"], ascending=[False, True]
                    )
                with st.container(border=True):
                    st.markdown("#### 공정소분류별 현황")
                    st.caption(f"{selected_month} 마지막 주 기준 · {asof_weeknum}")
                    st.dataframe(breakdown, hide_index=True, width="stretch")

            elif question == QUESTION_GAP:
                # **Static 은 시뮬레이션 DB 에 있다.** 이 페이지의 나머지는 설비 DB 만 열고
                # 활성 시나리오가 없어도 열린다. 그래서 여기서만 예외를 잡아 이 답 안에서
                # 알리고 나머지 다섯 질문과 RawData 를 막지 않는다 — 페이지가 통째로 죽으면
                # Cut-off 를 적으러 들어올 수도 없다. **이 질문을 고르지 않으면 시뮬레이션
                # DB 를 아예 열지 않는다.**
                static_availability: pd.DataFrame | None = None
                gap_required_equipment: pd.DataFrame | None = None
                static_error: str | None = None
                try:
                    gap_context = load_page_context()
                    static_availability = gap_context.reference_tables["RQ_EQP_AVBL"]
                    # 소요대수는 확보율을 맞대려고 받는다. 다섯 페이지가 같은 키로 한 번만
                    # 계산하므로 여기서 다시 계산되지 않는다.
                    _, gap_required_equipment = get_scenario_capacity_and_demand(
                        scenario_cache_key(
                            gap_context.reference_version,
                            gap_context.active_scenario,
                            gap_context.selected_start_month,
                            gap_context.selected_end_month,
                        ),
                        _scenario_tables=gap_context.active_scenario["tables"],
                        _reference_tables=gap_context.reference_tables,
                    )
                except BOOTSTRAP_ERRORS as exc:
                    static_error = bootstrap_error_message(
                        exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)
                    )

                gap_months = _months_between(start_date, end_date)
                # Cut-off 가 크면 그 달의 W/D 구간이 앞으로 밀린다. 조회기간만큼만 구간을
                # 만들면 첫 달이 조용히 모자라게 세어지므로, 필요한 만큼 앞에서부터 다시 만든다.
                required_span = span_date_range(gap_months, stored_cutoff)
                span_start = min(start_date, required_span[0]) if required_span else start_date
                span_end = max(end_date, required_span[1]) if required_span else end_date
                try:
                    gap_spans = build_equipment_lifecycle_spans(
                        dashboard_equipment,
                        dashboard_downtime,
                        start_date=span_start,
                        end_date=span_end,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    # 호기별 환산비. 월 Total Capa 축(`환산대수`)만 이 값을 곱한다 — 대수를
                    # 세는 축은 그대로다. 값이 없는 호기는 기준 모델과 같다고 보고 1.0 이다.
                    gap_ratios = {
                        str(unit).strip(): float(ratio)
                        for unit, ratio in zip(
                            dashboard_equipment.get("호기", []),
                            dashboard_equipment.get("환산비", []),
                            strict=False,
                        )
                        if pd.notna(ratio)
                    }
                    with st.container(border=True):
                        # **숫자 체계가 다르다는 것을 여기서 말한다.** 같은 달을 두 축이
                        # 다르게 말하는 것이 정상인데, 그 이유가 화면에 없으면 어느 쪽이
                        # 틀렸다고 읽힌다.
                        st.caption(
                            "앞의 다섯 질문은 **일요일 시점의 표본**이라 대수가 정수이고, "
                            "이 답은 **W/D 일할**이라 소수입니다 — 그 달에 며칠 있었는지로 "
                            "1대를 쪼개 셉니다. 같은 달을 다르게 말하는 것이 정상입니다. "
                            "이 답은 기준정보와 맞대는 자리라 위 조회 조건 대신 아래 "
                            "`공정` 으로 좁힙니다."
                        )
                        render_availability_gap_panel(
                            spans=gap_spans,
                            baseline=baseline,
                            cutoff=stored_cutoff,
                            months=gap_months,
                            static_availability=static_availability,
                            static_error=static_error,
                            span_bounds=(span_start, span_end),
                            conversion_ratios=gap_ratios,
                            required_equipment=gap_required_equipment,
                            section=_GAP_SECTIONS[str(st.session_state[GAP_SECTION_KEY])],
                        )

with rawdata_tab:
    if latest_snapshot is None:
        st.info(
            "기존 보유대수 샘플은 유지하고 호기 마스터·비가동 일정은 빈 상태입니다. "
            "웹에서 행을 추가하거나 Excel 표를 붙여넣은 뒤 첫 리비전을 저장하세요."
        )
    else:
        st.caption(
            f"최근 저장본 r{latest_snapshot.revision.revision_no}을 편집합니다. "
            "저장하면 세 입력 전체가 새 불변 리비전으로 보관됩니다."
        )

    # **폼 밖이다.** 적용·취소는 일반 버튼인데 `st.form` 안에는 제출 버튼 말고 다른
    # 버튼을 둘 수 없다. 처음 여는 사람이 가장 먼저 할 일이 여기라 펴 둔다.
    with st.expander("Excel 붙여넣기 Import", icon=":material/content_paste:", expanded=True):
        st.caption(
            "기존 보유대수는 공정 + 분류, 호기 마스터는 호기, 비가동 일정은 호기 + "
            "비가동유형 + 시작일을 중복 구분자로 사용합니다. CSV 양식을 Excel에서 열어 "
            "수정한 뒤 헤더를 포함한 전체 표를 복사해 붙여넣으세요. 화면 표시 이름이 아니라 "
            "양식의 헤더를 그대로 써야 하며, 기존 보유대수는 쉼표 없는 숫자로 적습니다. "
            "신규/대체 행과 변경 컬럼을 확인한 뒤 편집본에 적용하며, 실제 DuckDB 저장은 "
            "아래 저장 버튼에서 한 번 더 수행합니다."
        )
        st.caption("**붙여넣은 뒤 표 밖을 클릭하면 바로 검사합니다.**")
        baseline_import_col, equipment_import_col, downtime_import_col = st.columns(3)
        with baseline_import_col:
            # 「미리보기」 버튼이 없다. 붙여넣고 칸을 벗어나면 `on_change` 가 그 자리에서
            # 검사한다 — 30행 입력에서 사람이 눌러야 하던 클릭 하나가 여기서 사라진다.
            st.text_area(
                "기존 보유대수 표 붙여넣기",
                key=BASELINE_CLIPBOARD_KEY,
                height=140,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
                on_change=_scan_clipboard,
                args=(TARGET_BASELINE, floor_canvases),
            )
            render_csv_download(
                data=baseline_csv_template(),
                file_name="equipment_baseline_template.csv",
                key="equipment_baseline_template_download_v3",
                label=CSV_TEMPLATE_LABEL,
            )
        with equipment_import_col:
            st.text_area(
                "호기 마스터 표 붙여넣기",
                key=EQUIPMENT_CLIPBOARD_KEY,
                height=140,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
                on_change=_scan_clipboard,
                args=(TARGET_EQUIPMENT, floor_canvases),
            )
            render_csv_download(
                data=equipment_csv_template(),
                file_name="equipment_master_template.csv",
                key="equipment_master_template_download_v3",
                label=CSV_TEMPLATE_LABEL,
            )
        with downtime_import_col:
            st.text_area(
                "비가동 일정 표 붙여넣기",
                key=DOWNTIME_CLIPBOARD_KEY,
                height=140,
                placeholder="Excel에서 헤더를 포함한 전체 셀 범위를 복사한 뒤 Ctrl+V",
                on_change=_scan_clipboard,
                args=(TARGET_DOWNTIME, floor_canvases),
            )
            render_csv_download(
                data=downtime_csv_template(),
                file_name="equipment_downtime_template.csv",
                key="equipment_downtime_template_download_v3",
                label=CSV_TEMPLATE_LABEL,
            )

        # 적용 콜백이 `merge_*` 에서 받은 오류. 콜백 안에서는 `st.error` 가 화면에 닿지
        # 않으므로 세션 칸을 거쳐 여기서 알린다.
        apply_error = st.session_state.get(IMPORT_APPLY_ERROR_KEY)
        if isinstance(apply_error, str):
            st.error(apply_error)

        baseline_errors = st.session_state.get(BASELINE_IMPORT_ERROR_KEY)
        if isinstance(baseline_errors, ImportPreviewResult):
            st.markdown("**기존 보유대수 Import 확인**")
            _render_import_error_preview(baseline_errors, download_key=BASELINE_ERROR_DOWNLOAD_KEY)
            with st.container(horizontal=True):
                st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_baseline_import_v3",
                    disabled=True,
                    help="오류 행을 고쳐 다시 붙여넣어야 적용할 수 있습니다.",
                )
                st.button(
                    "취소",
                    icon=":material/close:",
                    key="cancel_baseline_import_v3",
                    on_click=_clear_import,
                    args=(TARGET_BASELINE,),
                )

        incoming_baseline = st.session_state.get(BASELINE_IMPORT_KEY)
        if isinstance(incoming_baseline, pd.DataFrame):
            st.markdown("**기존 보유대수 Import 확인**")
            baseline_preview = build_baseline_import_preview(baseline, incoming_baseline)
            _import_summary(baseline_preview)
            st.dataframe(baseline_preview, hide_index=True, width="stretch")
            with st.container(horizontal=True):
                st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_baseline_import_v3",
                    on_click=_apply_baseline_import,
                )
                st.button(
                    "취소",
                    icon=":material/close:",
                    key="cancel_baseline_import_v3",
                    on_click=_clear_import,
                    args=(TARGET_BASELINE,),
                )

        equipment_errors = st.session_state.get(EQUIPMENT_IMPORT_ERROR_KEY)
        if isinstance(equipment_errors, ImportPreviewResult):
            st.markdown("**호기 마스터 Import 확인**")
            _render_import_error_preview(
                equipment_errors, download_key=EQUIPMENT_ERROR_DOWNLOAD_KEY
            )
            with st.container(horizontal=True):
                st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_equipment_import_v3",
                    disabled=True,
                    help="오류 행을 고쳐 다시 붙여넣어야 적용할 수 있습니다.",
                )
                st.button(
                    "취소",
                    icon=":material/close:",
                    key="cancel_equipment_import_v3",
                    on_click=_clear_import,
                    args=(TARGET_EQUIPMENT,),
                )

        incoming_equipment = st.session_state.get(EQUIPMENT_IMPORT_KEY)
        if isinstance(incoming_equipment, pd.DataFrame):
            st.markdown("**호기 마스터 Import 확인**")
            equipment_preview = build_equipment_import_preview(equipment, incoming_equipment)
            _import_summary(equipment_preview)
            st.dataframe(equipment_preview, hide_index=True, width="stretch")
            with st.container(horizontal=True):
                st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_equipment_import_v3",
                    on_click=_apply_equipment_import,
                    args=(floor_canvases,),
                )
                st.button(
                    "취소",
                    icon=":material/close:",
                    key="cancel_equipment_import_v3",
                    on_click=_clear_import,
                    args=(TARGET_EQUIPMENT,),
                )

        downtime_errors = st.session_state.get(DOWNTIME_IMPORT_ERROR_KEY)
        if isinstance(downtime_errors, ImportPreviewResult):
            st.markdown("**비가동 일정 Import 확인**")
            _render_import_error_preview(downtime_errors, download_key=DOWNTIME_ERROR_DOWNLOAD_KEY)
            with st.container(horizontal=True):
                st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_downtime_import_v3",
                    disabled=True,
                    help="오류 행을 고쳐 다시 붙여넣어야 적용할 수 있습니다.",
                )
                st.button(
                    "취소",
                    icon=":material/close:",
                    key="cancel_downtime_import_v3",
                    on_click=_clear_import,
                    args=(TARGET_DOWNTIME,),
                )

        incoming_downtime = st.session_state.get(DOWNTIME_IMPORT_KEY)
        if isinstance(incoming_downtime, pd.DataFrame):
            st.markdown("**비가동 일정 Import 확인**")
            downtime_preview = build_downtime_import_preview(downtime, incoming_downtime)
            _import_summary(downtime_preview)
            st.dataframe(downtime_preview, hide_index=True, width="stretch")
            with st.container(horizontal=True):
                st.button(
                    "확인 후 편집본에 적용",
                    type="primary",
                    icon=":material/check:",
                    key="confirm_downtime_import_v3",
                    on_click=_apply_downtime_import,
                )
                st.button(
                    "취소",
                    icon=":material/close:",
                    key="cancel_downtime_import_v3",
                    on_click=_clear_import,
                    args=(TARGET_DOWNTIME,),
                )

    downtime_type_options = sorted(
        set(DOWNTIME_TYPES) | set(downtime["비가동유형"].dropna().astype(str).tolist())
    )
    # 보기 설정은 **폼 밖**이다. 폼 안에 두면 저장을 눌러야 적용돼 고르는 뜻이 없어진다.
    # 세로로 쌓지 않고 한 줄에 세운다 — 편집표가 붙여넣기 바로 아래에 오게 하는 자리다.
    with st.container(horizontal=True, gap="small"):
        baseline_view = _table_view_popover(
            baseline,
            title="기존 보유대수",
            key_prefix="equipment_baseline_view",
            editor_key=BASELINE_EDITOR_KEY,
            filter_columns=("공정", "분류"),
            locked_columns=("공정", "분류", "기존보유대수"),
        )
        equipment_view = _table_view_popover(
            equipment,
            title="호기 마스터",
            key_prefix="equipment_master_view",
            editor_key=EQUIPMENT_EDITOR_KEY,
            filter_columns=(
                "공정소분류",
                "라인구분",
                "활용구분",
                "공정대분류",
                "동",
                "층",
                "확정상태",
                "장기보관여부",
                "기존설비여부",
                "레이아웃표시",
            ),
            locked_columns=(
                "호기",
                "공정소분류",
                "장기보관여부",
                "기존설비여부",
                "레이아웃표시",
            ),
        )
        downtime_view = _table_view_popover(
            downtime,
            title="운영 비가동 일정",
            key_prefix="equipment_downtime_view",
            editor_key=DOWNTIME_EDITOR_KEY,
            filter_columns=("호기", "비가동유형"),
            locked_columns=("호기", "비가동유형", "시작일"),
        )

    with st.form("equipment_operations_form_v3", border=True):
        # **Import 바로 아래가 이 버튼의 자리다.** 붙여넣기의 「적용」은 편집본까지만
        # 가고 DuckDB 에는 닿지 않는다 — 그 다음에 눌러야 하는 것이 무엇인지 순서로
        # 보이게 한다. 폼은 제출 때 안의 위젯을 한꺼번에 보내므로 버튼이 표 위에 있어도
        # 아래 세 표의 편집이 그대로 함께 저장된다.
        st.caption(
            "Import 의 「확인 후 편집본에 적용」은 편집본까지입니다. "
            "**DuckDB 에 새 리비전으로 남기려면 아래 저장을 눌러야 합니다.**"
        )
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            revision_note = st.text_input(
                "변경 메모",
                placeholder="예: 신규 호기 Qual 일정 및 8월 고장 일정 반영",
                width=520,
            )
            submitted = st.form_submit_button(
                "설비 데이터 저장", icon=":material/save:", type="primary"
            )

        st.markdown("#### 기존 보유대수")
        st.caption(
            "호기·Qual 이력을 관리할 실익이 없는 기존 가동설비를 공정·분류별 집계로 "
            "유지합니다. 공정 값은 호기 마스터의 공정소분류와 연결됩니다."
        )
        edited_baseline = merge_edited_rows(
            baseline,
            filtered=baseline_view.filtered,
            edited=st.data_editor(
                baseline_view.frame,
                key=BASELINE_EDITOR_KEY,
                num_rows=baseline_view.row_mode,
                hide_index=True,
                width="stretch",
                column_config={
                    **baseline_view.column_config,
                    "공정": st.column_config.TextColumn(required=True, pinned=True),
                    "분류": st.column_config.TextColumn(required=True),
                    "기존보유대수": st.column_config.NumberColumn(
                        "기존 보유대수",
                        min_value=0,
                        step=0.1,
                        format="%.1f 대",
                        required=True,
                    ),
                    "비고": st.column_config.TextColumn(),
                },
            ),
        )

        st.markdown("#### 호기 마스터")
        st.caption(
            "일반 신규 호기는 입고일정·Qual일정이 필수입니다. 장기보관 또는 기존설비 Y는 "
            "두 일정이 없어도 됩니다. 확정상태는 Qual 실행관리 전용이며, 레이아웃표시 Y는 "
            "위치와 좌표·크기가 모두 필요합니다. 환산비는 같은 공정에 생산성이 다른 모델이 "
            "섞일 때 **한 대가 몇 대 몫을 하는지**입니다 — 기준 모델이 1이고 비우면 1로 "
            "채워집니다. 아직 Capa 가용대수에는 반영되지 않고 이력으로만 쌓입니다."
        )
        equipment_column_config: dict[str, Any] = {
            "호기": st.column_config.TextColumn(required=True, pinned=True),
            "공정소분류": st.column_config.TextColumn(required=True),
            "동": st.column_config.SelectboxColumn(options=list(VALID_BUILDINGS)),
            "층": st.column_config.SelectboxColumn(options=list(VALID_FLOORS)),
            "X좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_canvas_width, step=1.0
            ),
            "Y좌표": st.column_config.NumberColumn(
                min_value=0.0, max_value=max_canvas_height, step=1.0
            ),
            "Xsize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_canvas_width, step=1.0
            ),
            "Ysize": st.column_config.NumberColumn(
                min_value=0.1, max_value=max_canvas_height, step=1.0
            ),
            "확정상태": st.column_config.SelectboxColumn(options=list(QUAL_CONFIRMATION_STATUSES)),
            "장기보관여부": st.column_config.SelectboxColumn(options=["N", "Y"], required=True),
            "기존설비여부": st.column_config.SelectboxColumn(options=["N", "Y"], required=True),
            "레이아웃표시": st.column_config.SelectboxColumn(options=["Y", "N"], required=True),
            # 하한을 0 이 아니라 그 위로 둔다. 0 은 「이 설비는 없는 셈」이라는 뜻이 되는데
            # 그것은 비가동 일정이 맡는 일이다. 비워 두면 기준 모델(1.0)로 채워진다.
            "환산비": st.column_config.NumberColumn(min_value=0.01, step=0.1, format="%.2f"),
        }
        equipment_column_config.update(
            {column: st.column_config.DateColumn(format="YYYY-MM-DD") for column in DATE_COLUMNS}
        )
        edited_equipment = merge_edited_rows(
            equipment,
            filtered=equipment_view.filtered,
            edited=st.data_editor(
                equipment_view.frame,
                key=EQUIPMENT_EDITOR_KEY,
                num_rows=equipment_view.row_mode,
                hide_index=True,
                width="stretch",
                column_config={**equipment_column_config, **equipment_view.column_config},
            ),
        )

        st.markdown("#### 운영 비가동 일정")
        st.caption(
            "비가동ID 없이 호기·비가동유형·시작일 조합을 일정의 고유 기준으로 사용합니다. "
            "종료일이 없으면 진행 중입니다."
        )
        edited_downtime = merge_edited_rows(
            downtime,
            filtered=downtime_view.filtered,
            edited=st.data_editor(
                downtime_view.frame,
                key=DOWNTIME_EDITOR_KEY,
                num_rows=downtime_view.row_mode,
                hide_index=True,
                width="stretch",
                column_config={
                    **downtime_view.column_config,
                    "호기": st.column_config.TextColumn(required=True, pinned=True),
                    "비가동유형": st.column_config.SelectboxColumn(
                        options=downtime_type_options, required=True
                    ),
                    "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
                    "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                    "상세사유": st.column_config.TextColumn(),
                    "비고": st.column_config.TextColumn(),
                },
            ),
        )
    if submitted:
        # 화면을 채우려고 넣어 준 샘플이 그대로 불변 리비전에 들어가면 되돌릴 수 없다.
        # 실제 공정명과 다르면 호기 마스터에 붙지 않는 유령 공정이 총대수에 영원히 남는다.
        # 내려받은 양식의 예시 한 줄도 네 컬럼이 다 차 있어 검증을 그냥 통과한다 — 출처만
        # 다를 뿐 같은 위험이라 함께 막는다.
        leftover_samples = pd.concat(
            [
                untouched_sample_baseline_rows(edited_baseline),
                untouched_template_baseline_rows(edited_baseline),
            ]
        )
    if submitted and not leftover_samples.empty:
        st.error(
            f"기존 보유대수에 지우지 않은 예시 행이 {len(leftover_samples)}건 남아 있습니다. "
            "실제 값으로 고치거나 지운 뒤 저장하세요. 이 숫자는 개발용 샘플과 CSV 양식의 "
            "예시라 실제 설비와 맞지 않고, 저장하면 리비전에서 지울 수 없습니다."
        )
    elif submitted:
        try:
            saved = repository.save_snapshot(
                edited_baseline,
                edited_equipment,
                edited_downtime,
                note=revision_note,
            )
        except BOOTSTRAP_ERRORS as exc:
            st.error(bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,)))
        else:
            clear_equipment_snapshot_cache()
            _reset_drafts()
            st.session_state[FLASH_KEY] = (
                f"설비 운영 데이터 r{saved.revision.revision_no}을 저장했습니다. "
                "가용설비와 Space 현황에 반영됩니다."
            )
            st.rerun()

    try:
        revisions = repository.list_revisions()
    except BOOTSTRAP_ERRORS as exc:
        st.error(
            "저장 이력을 읽지 못했습니다: "
            + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
        )
        st.stop()
    with st.expander("저장 이력 및 필터 조회", icon=":material/history:", expanded=False):
        if not revisions:
            st.caption("저장된 설비 운영 이력이 없습니다.")
        else:
            history = pd.DataFrame(
                [
                    {
                        "리비전": f"r{revision.revision_no}",
                        "저장시각": revision.created_at,
                        "기존대수행": revision.baseline_row_count,
                        "호기행": revision.equipment_row_count,
                        "비가동행": revision.downtime_row_count,
                        "변경메모": revision.note,
                    }
                    for revision in revisions
                ]
            )
            st.dataframe(
                history,
                hide_index=True,
                width="stretch",
                # 메모 없는 리비전에 리터럴 "None" 이 찍혔다. 같은 화면의 선택 상자는
                # 이미 "메모 없음" 을 쓴다.
                placeholder="메모 없음",
                column_config={
                    "저장시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")
                },
            )
            revision_by_id = {revision.revision_id: revision for revision in revisions}
            selected_revision_id = st.selectbox(
                "조회 리비전",
                options=list(revision_by_id),
                format_func=lambda value: (
                    f"r{revision_by_id[value].revision_no} · "
                    f"{revision_by_id[value].created_at:%Y-%m-%d %H:%M} · "
                    f"{revision_by_id[value].note or '메모 없음'}"
                ),
                key="equipment_history_revision_id_v3",
                persist_state="session",
            )
            try:
                historical = load_equipment_snapshot(equipment_database_path, selected_revision_id)
            except BOOTSTRAP_ERRORS as exc:
                st.error(
                    "선택한 이력을 읽지 못했습니다: "
                    + bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
                )
                st.stop()
            historical_equipment = historical.equipment
            with st.container(horizontal=True, gap="small"):
                history_processes = st.multiselect(
                    "공정소분류",
                    historical_equipment["공정소분류"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_process_filter_v3",
                    persist_state="session",
                )
                history_buildings = st.multiselect(
                    "동",
                    historical_equipment["동"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_building_filter_v3",
                    persist_state="session",
                )
                history_floors = st.multiselect(
                    "층",
                    historical_equipment["층"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_floor_filter_v3",
                    persist_state="session",
                )
                history_equipment_ids = st.multiselect(
                    "호기",
                    historical_equipment["호기"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_id_filter_v3",
                    persist_state="session",
                )
                history_downtime_types = st.multiselect(
                    "비가동유형",
                    historical.downtime["비가동유형"].dropna().drop_duplicates().tolist(),
                    key="equipment_history_downtime_type_filter_v3",
                    persist_state="session",
                )
            filtered_history_equipment = historical_equipment.copy()
            for column, selected in (
                ("공정소분류", history_processes),
                ("동", history_buildings),
                ("층", history_floors),
                ("호기", history_equipment_ids),
            ):
                if selected:
                    filtered_history_equipment = filtered_history_equipment.loc[
                        filtered_history_equipment[column].isin(selected)
                    ]
            filtered_history_downtime = historical.downtime.copy()
            if history_equipment_ids:
                filtered_history_downtime = filtered_history_downtime.loc[
                    filtered_history_downtime["호기"].isin(history_equipment_ids)
                ]
            elif history_processes or history_buildings or history_floors:
                filtered_history_downtime = _downtime_for_equipment(
                    filtered_history_downtime, filtered_history_equipment
                )
            if history_downtime_types:
                filtered_history_downtime = filtered_history_downtime.loc[
                    filtered_history_downtime["비가동유형"].isin(history_downtime_types)
                ]
            event_range = st.date_input(
                "비가동 일정 기간",
                value=(start_date, end_date),
                key="equipment_history_event_range_v3",
                persist_state="session",
            )
            event_start, event_end = date_range_value(event_range, (start_date, end_date))
            if event_start <= event_end and not filtered_history_downtime.empty:
                # **`.dt.date` 로 비교하지 않는다.** 그 컬럼이 전부 비어 있으면 `.dt.date` 가
                # `datetime64` 를 그대로 물고 나와 `date` 와의 비교가 `TypeError` 로 죽는다.
                # 값이 하나라도 있으면 object 로 바뀌어 통과하므로, 「종료일이 전부 비어 있는
                # 리비전」에서만 터진다 — 화면이 「종료일이 없으면 진행 중」이라고 허용하는
                # 바로 그 상태다. `Timestamp` 끼리 재면 빈값은 비교가 거짓이 되고, 그 몫은
                # 왼쪽의 `isna()` 가 이미 맡는다.
                start_bound = pd.Timestamp(event_start)
                end_bound = pd.Timestamp(event_end)
                overlaps = filtered_history_downtime["시작일"].le(end_bound) & (
                    filtered_history_downtime["종료일"].isna()
                    | filtered_history_downtime["종료일"].ge(start_bound)
                )
                filtered_history_downtime = filtered_history_downtime.loc[overlaps]
            st.markdown("**기존 보유대수**")
            st.dataframe(historical.baseline, hide_index=True, width="stretch")
            st.markdown("**호기 마스터**")
            st.dataframe(filtered_history_equipment, hide_index=True, width="stretch")
            st.markdown("**비가동 일정**")
            st.dataframe(filtered_history_downtime, hide_index=True, width="stretch")

    with st.expander("운영 지침", icon=":material/menu_book:", expanded=False):
        st.markdown(
            """
#### 입력 데이터 구분

- **기존 보유대수**: 호기별 일정·상태를 관리할 필요가 없는 오래된 가동설비를
  `공정소분류별 집계 대수`로 관리합니다. 전 조회기간에 보유·가용 설비로 반영됩니다.
- **호기 마스터**: 입고·Qual 일정, Qual 확정상태, 반출·이설, 개별 비가동 또는
  Space 배치를 관리할 설비를 호기별로 등록합니다. 오래된 설비라도 개별 관리가 필요하면
  호기 마스터에 등록하고 `기존설비여부=Y`로 지정합니다.
- **비가동 일정**: 호기 마스터에 등록된 설비의 개발대여·공사·고장·이설 기간을
  호기별로 관리합니다.

#### 운영 절차

1. 웹에서 직접 행을 편집하거나 기존 보유대수·호기 마스터·비가동 일정 Excel 표를
   붙여넣습니다.
2. 붙여넣기 Import 시 신규·대체 행과 변경 컬럼을 미리 확인합니다.
3. `확인 후 편집본에 적용`으로 현재 편집본에 반영합니다.
4. 하단의 `설비 데이터 저장`을 눌러야 DuckDB에 새 불변 리비전으로 영구 저장됩니다.

#### 적용 시 유의사항

- 기존 보유대수에는 호기명이 없으므로 개별 비가동 일정과 Space 배치를 적용할 수 없습니다.
- 일반 신규 설비는 입고일정·Qual일정·확정상태가 필요합니다.
- 가용대수는 Qual일정을 기준으로 계산하며, 확정상태는 Qual 실행 모니터링에만 사용합니다.
- Space 표시는 `레이아웃표시=Y`와 동·층·X/Y좌표·X/Ysize 입력이 필요합니다.
- 설비 운영 가용대수는 현재 시뮬레이션 Capa 산출 데이터와 분리되어 있습니다.

#### 상태 판정 기준

- **입고 예정**: 입고일정 전이며, 제진대·물류 일정도 이 상태의 선행 일정으로 관리
- **셋업 진행중**: 입고일정 이상, Qual일정 미만
- **가용**: Qual일정 이상 또는 기존설비 Y
- **확정상태**: Qual 일정만 계획·확정·완료·지연으로 실행관리하며 가용 판정에는 미사용
- **반출 예정 / 이설 예정**: 일정이 등록됐고 실행일 전
- **보관 설비**: 장기보관여부 Y
- **운영 비가동**: 개발대여·공사·고장·이설 등 비가동 일정 활성
- **반출 완료 / 이설 완료**: 실행일부터 보유·가용·레이아웃에서 제외
            """
        )
