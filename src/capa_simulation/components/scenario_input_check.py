# Purpose: 시나리오 목록 관리 「점검」 칸 — 고른 저장 리비전의 계산에서 빠진 행을 묶음 줄로 그린다.

"""「점검」 칸(2026-11-11 입력 점검 시안 보드 답 q1 ~ q7 + 등록 행 보기 — 시안 `mock_ga` ·
`mock_ga_stop`).

시나리오 관리 › Capa 시나리오 › 목록 관리 오른쪽 칸 다섯째다. 묶음의 셈은 순수 서비스
(`services/revision_input_check.py`)이고 계산 · 캐시는 `capacity_gate.input_check_verdict` 다. 이
조각은 그 결과를 그리기만 한다.

- **리비전 표**는 이 칸 전용 마운트(`CHECKS_KEY` — r · 리비전명 · 계산)이고 고름은 「상세」 칸 표와
  같은 `ListDraft.picked` 다. 이름은 여기서 고치지 않는다. 「계산」 칸은 이 세션에서 센 리비전만
  글이 서고(`CHECK_LABELS_KEY` — 저장 리비전은 내용이 바뀌지 않아 리비전 id 로 둔다) 나머지는 「—」
  다(DB 칸 없음). 고른 리비전은 이 칸이 열린 회차에 센다(상세 칸 고름은 세지 않는다 — UI-PRF-01).
  셈을 먼저 하고 표를 그 자리에 그린다 — 고른 줄의 「계산」 이 같은 회차에 선다.
- **칸 머리 한 줄**은 「rN · 전체 기간 YY.MM–YY.MM」(UI-TXT-07 — 기간은 이 한 자리)이다.
- **묶음 줄**은 단계 표지 · 이름 · 수 · 부제와 「행 보기 / 행 접기」 · 「그 화면으로」 다. 펼치면 앞
  다섯 칸 · 앞 `PREVIEW_ROWS` 행과 「앞 n행 · 전체 m행」 · 「넓게 보기」(모든 칸 — 화면 팝업
  호스트 하나를 함께 쓴다) · 묶음 CSV(원본 값 — UI-DAT-10)다. 화면 글은 공정 표시명 · 까닭 표시명
  (`reason_label`)이고 CSV 는 원본이다. 규칙대로 뺀 것은 맨 아래 접힌 한 줄이고 펼치면 두 표다.
- **「그 화면으로」**(설계 규칙 UI-TXT-03 예외 — q4)는 고칠 화면의 그 탭 · 종류 단추까지 연다
  (UI-NAV-01). 고른 리비전이 올라와 있지 않으면 불러온 뒤 연다 — 미저장 편집이 있으면 사이드바
  시나리오 팝업이 묻는다(`scenario_status.open_scenario_dialog_on`). 같은 화면의 탭(DB 등록)은
  탭만 바꾸고 불러오지 않는다.
- 셈 동안 진행 표시(UI-PRF-05 — 이 화면의 다른 전체 기간 검사와 같은 `st.spinner`), 읽기 · 계산
  실패는 「데이터 Error」 마크(UI-NTF-08 — `SC-02`)다. 미저장 편집이 있어도 저장된 리비전을 센다 —
  칸 머리 표지 없이 Guide 가 말한다.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd
import streamlit as st

from capa_simulation.components.capacity_gate import input_check_verdict
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.literal_markdown import literal_markdown, markdown_safe_tildes
from capa_simulation.components.process_labels import (
    PROCESS_COLUMN,
    ProcessLabels,
    get_process_labels,
)
from capa_simulation.components.scenario_edit_bar import pending_edit_labels
from capa_simulation.components.scenario_list_state import CHECKS_KEY
from capa_simulation.components.scenario_management_tabs import (
    CAPA_SCENARIO_TAB_NAME,
    QUERY_TAB,
    SCENARIO_MANAGEMENT_TABS_KEY,
)
from capa_simulation.components.tab_state import remember_open_tab, remembered_tab_key
from capa_simulation.components.table_toolbar import render_csv_download, toolbar_clearance
from capa_simulation.design import tokens
from capa_simulation.navigation import (
    CALCULATION_RESULT_TAB_KEY,
    LOAD_CONVERSION,
    LOAD_CONVERSION_TAB_KEY,
    REFERENCE_DATA,
    SCENARIO_MANAGEMENT,
    STATIC_CAPA_SUBPAGES,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    bootstrap_error_message,
    calculation_stop_notice,
)
from capa_simulation.page_tabs_state import queue_switch, refused_at_tab_limit
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.models import RevisionSummary, ScenarioSummary
from capa_simulation.reference_grid_keys import DATASET_KEY, DATASETS
from capa_simulation.scenario_activation import (
    active_persisted_revision_id,
    has_unsaved_scenario_changes,
)
from capa_simulation.services.month_columns import month_label
from capa_simulation.services.revision_input_check import (
    GROUP_ASSUMED,
    GROUP_CAPACITY,
    GROUP_PLANS,
    GROUP_ROUTES,
    GROUP_RULES,
    GROUP_SOURCE,
    GROUP_STOP,
    GROUP_UNROUTED,
    LEVEL_LABELS,
    InputCheckGroup,
    InputCheckTable,
    RevisionInputCheck,
    reason_label,
)
from capa_simulation.services.scenario_list_edits import (
    CheckTone,
    ListDraft,
    RevisionFacts,
    checks_payload,
)
from capa_simulation.services.unit_capacity import (
    RUN_RATE_EXCLUSION_REASON,
    UPEH_EXCLUSION_REASON,
)

# 이 세션에서 센 리비전의 「계산」 칸 — 리비전 id → (글, 단계). 저장 리비전은 내용이 바뀌지 않아
# 리비전 id 로 둔다. 오래된 것부터 `LABEL_MEMO_LIMIT` 개를 넘으면 뺀다.
CHECK_LABELS_KEY: Final = "scenario_input_check_labels"
LABEL_MEMO_LIMIT: Final = 64
# 펼친 묶음 — 묶음 id 차례(리비전을 바꿔도 같은 묶음은 펼친 채다).
CHECK_OPEN_KEY: Final = "scenario_input_check_open"
# 「그 화면으로」 의 결과 칸 — 그 단추 곁(누른 동작의 실패 · UI-NTF-03).
CHECK_NOTICE_KEY: Final = "scenario_input_check_notice"
# 펼친 묶음이 보이는 앞 행 수(시안 「앞 4행 · 전체 134행」).
PREVIEW_ROWS: Final = 4
# 묶음 줄을 담는 칸과 묶음 칸 key 앞머리 — 줄 서식(`panel_style`)이 이 key 로 고른다.
GROUPS_KEY: Final = "input_check_groups"
GROUP_KEY_PREFIX: Final = "input_check_group_"
RULES_KEY: Final = "input_check_rules"
# 「넓게 보기」 팝업의 열림 값 앞머리 — (앞머리, 시나리오 id, 리비전 id, 리비전 번호, 묶음 id). 화면
# 팝업 호스트 하나를 공식 지정 팝업과 함께 쓴다(열림 값의 꼴로 가른다 — 결정 17).
WIDE_TAG: Final = "input_check_wide"
WIDE_TITLE: Final = "넓게 보기"
# 계산 멈춤 알림 짧은 글(`calculation_stop_notice`)의 머리 — 묶음 이름 「계산 멈춤 — 대당 Capa」 와
# 겹쳐 부제에서는 뗀다(시험이 알림 글과 맞댄다).
STOP_NOTICE_HEAD: Final = "대당 Capa 계산 멈춤 — "
# 「그 화면으로」 풍선 — 고른 리비전이 올라와 있지 않을 때(결정 1).
GO_LOADS_HELP: Final = "고른 리비전을 불러온 뒤 엽니다."
SPINNER_TEXT: Final = "고른 리비전의 전체 기간 계산을 점검하는 중입니다..."
# 누른 사이 다른 리비전 · 다른 시나리오를 고른 「그 화면으로」 — 아무것도 하지 않는다.
PICK_MOVED_MESSAGE: Final = "고른 리비전이 바뀌어 하지 않았습니다 — 지금 고른 리비전을 확인하세요."
EMPTY_REVISIONS: Final = "이 시나리오에 저장된 리비전이 없습니다."
# 규칙대로 뺀 행이 없어 잠긴 「규칙대로 셈에서 뺀 것」 줄의 까닭 풍선(설계 규칙 UI-INP-07).
RULES_EMPTY_HELP: Final = "규칙대로 셈에서 뺀 행이 없어 펼칠 것이 없습니다."

# 「그 화면으로」 가 여는 산출 결과 · 생산 계획 탭 라벨. 화면 모듈은 불러올 수 없어 여기 같은 글을
# 두고 시험이 화면 글과 맞댄다(`tests/test_scenario_input_check.py`). 탭 key 는 화면과 함께 쓰는
# `navigation` 의 한 벌이다.
CALCULATION_RESULT: Final = next(
    spec for spec in STATIC_CAPA_SUBPAGES if spec.path == "app_pages/calculation_result.py"
)
CALCULATION_UNIT_TAB: Final = ":material/insights: 대당 Capa"
CALCULATION_REQUIRED_TAB: Final = ":material/precision_manufacturing: 소요대수"
PLAN_PKG_TAB: Final = ":material/edit_calendar: PKG PLAN"
PLAN_YIELD_TAB: Final = ":material/percent: 수율"
# 대당 Capa 에서 뺀 기준의 까닭 → 고칠 기준 정보 표(까닭이 하나일 때만 — 결정 15).
_CAPACITY_REASON_TABLES: Final[Mapping[str, str]] = {
    UPEH_EXCLUSION_REASON: "RQ_UPEH",
    RUN_RATE_EXCLUSION_REASON: "RQ_RUN_RATE",
}
# 부하량에서 빠진 계획 가운데 수율 탭에서 고치는 까닭.
_YIELD_REASONS: Final = frozenset({"RQ_YLD", "RQ_YLD 값 없음"})
# 묶음 줄 이름 · 수의 글자 크기(rem) — 시안 13px · 14.5px · 표지 11px.
_TITLE_REM: Final = 0.8125
_COUNT_REM: Final = 0.906
_LEVEL_REM: Final = 0.6875
_MONTH_COLUMN: Final = "생산계획년월"
_COLUMN_LABELS: Final[Mapping[str, str]] = {_MONTH_COLUMN: "년월"}


# 「넓게 보기」 열림 값 — (앞머리, 시나리오 id, 리비전 id, 「rN」, 「묶음 id:표 차례」).
WideValue = tuple[str, str, str, str, str]
WideValues = tuple[WideValue, ...]


@dataclass(frozen=True)
class Arrival:
    """「그 화면으로」 가 열 곳 — 화면 주소(`PageSpec.path`), 그 화면에서 고를 칸 key 와 값.

    `tab` 이 참이면 그 화면 `stateful_tabs` 의 기억 칸(`remember_open_tab`), 거짓이면 그 위젯의
    세션 값(기준 정보 종류 단추)이다. `value` 가 None 이면 화면만 연다."""

    path: str
    key: str = ""
    value: str | None = None
    tab: bool = True


def _calculation_tab(label: str) -> Arrival:
    return Arrival(CALCULATION_RESULT.path, CALCULATION_RESULT_TAB_KEY, label)


def _reference(table: str | None) -> Arrival:
    return Arrival(REFERENCE_DATA.path, DATASET_KEY, table, tab=False)


def arrival_for(group: InputCheckGroup, check: RevisionInputCheck) -> Arrival | None:
    """묶음의 「그 화면으로」 도착지(결정 15). 수가 없거나 0 이면 None(단추 없음).

    멈춤은 계산 멈춤 알림과 같은 갈 곳이다(`calculation_stop_notice` — 기준 정보 그 종류). 그 알림이
    갈 곳을 말하지 않는 멈춤(모듈수 · Density · 경로 키 없는 옛 리비전 · 그 밖의 계산 오류)은 단추가
    없다.
    """
    if group.key == GROUP_STOP:
        if check.stop is None or check.stop.kind != "capacity":
            return None
        notice = calculation_stop_notice(ValueError(check.stop.error))
        if notice is None or notice.goto is None:
            return None
        table = next((key for key, label in DATASETS.items() if label == notice.goto[2]), None)
        return _reference(table)
    if not group.count:
        return None
    reasons = [reason for reason, _ in group.reasons]
    if group.key == GROUP_CAPACITY:
        if len(reasons) == 1 and reasons[0] in _CAPACITY_REASON_TABLES:
            return _reference(_CAPACITY_REASON_TABLES[reasons[0]])
        return _calculation_tab(CALCULATION_UNIT_TAB)
    if group.key == GROUP_ROUTES:
        return _calculation_tab(CALCULATION_REQUIRED_TAB)
    if group.key == GROUP_PLANS:
        yield_only = bool(reasons) and all(reason in _YIELD_REASONS for reason in reasons)
        tab = PLAN_YIELD_TAB if yield_only else PLAN_PKG_TAB
        return Arrival(LOAD_CONVERSION.path, LOAD_CONVERSION_TAB_KEY, tab)
    if group.key == GROUP_UNROUTED:
        return Arrival(LOAD_CONVERSION.path, LOAD_CONVERSION_TAB_KEY, PLAN_PKG_TAB)
    if group.key == GROUP_ASSUMED:
        return _reference(reasons[0] if len(reasons) == 1 else None)
    if group.key == GROUP_SOURCE:
        return Arrival(SCENARIO_MANAGEMENT.path, SCENARIO_MANAGEMENT_TABS_KEY, QUERY_TAB)
    return None


def calculation_cell(check: RevisionInputCheck) -> tuple[str, CheckTone]:
    """「계산」 칸 (글, 단계) — 멈춤은 오류, 확인할 묶음이 있으면 확인, 없으면 됨."""
    if check.stopped:
        return check.calculation_label, "error"
    return check.calculation_label, "check" if check.check_count else "done"


def remembered_calculations() -> dict[str, tuple[str, CheckTone]]:
    held = st.session_state.get(CHECK_LABELS_KEY)
    return dict(held) if isinstance(held, dict) else {}


def _remember_calculation(revision_id: str, cell: tuple[str, CheckTone]) -> None:
    held = remembered_calculations()
    if held.get(revision_id) == cell:
        return
    held.pop(revision_id, None)
    held[revision_id] = cell
    while len(held) > LABEL_MEMO_LIMIT:
        held.pop(next(iter(held)))
    st.session_state[CHECK_LABELS_KEY] = held


def _open_groups() -> tuple[str, ...]:
    held = st.session_state.get(CHECK_OPEN_KEY)
    return tuple(item for item in held if isinstance(item, str)) if isinstance(held, tuple) else ()


def _toggle_group(key: str) -> None:
    """「행 보기 / 행 접기」 콜백."""
    held = _open_groups()
    st.session_state[CHECK_OPEN_KEY] = (
        tuple(item for item in held if item != key) if key in held else (*held, key)
    )


def render_input_check_panel(
    database_path: str,
    summary: ScenarioSummary,
    revisions: Sequence[RevisionSummary],
    draft: ListDraft,
    *,
    facts: Sequence[RevisionFacts],
    mount_data: Mapping[str, object],
    on_outbox: Callable[[], None],
    fold: Callable[[], ListDraft],
    open_wide: Callable[[object, str], None],
    counting: bool,
) -> WideValues:
    """「점검」 칸 본문. 이 칸이 그린 「넓게 보기」 단추의 열림 값(그 리비전 · 묶음 · 표)을 돌려준다
    — 화면 팝업 호스트가 열린 팝업이 아직 이 칸의 것인지 본다.

    `mount_data` 는 리비전 표 마운트 공통 data(세대 · ack), `fold` 는 목록 출납을 접는 함수(누른
    회차의 고름을 본다), `open_wide` 는 화면 팝업 호스트의 여는 콜백이다. `counting` 이 거짓이면(이
    탭이 닫힌 회차) 셈 없이 표만 그린다 — 숨은 칸이 전체 기간 계산을 돌리지 않는다.
    """
    from capa_simulation.components.scenario_list_grid import render_list_mount

    table_box = st.container()
    revision = next((item for item in revisions if item.revision_id == draft.picked), None)
    check: RevisionInputCheck | None = None
    failure: str | None = None
    if counting and revision is not None:
        with st.container():
            try:
                with st.spinner(SPINNER_TEXT):
                    check = input_check_verdict(
                        database_path, summary.scenario_id, revision.revision_id
                    )
            except BOOTSTRAP_ERRORS as exc:
                failure = bootstrap_error_message(exc)
        if check is not None:
            _remember_calculation(revision.revision_id, calculation_cell(check))
    with table_box:
        render_list_mount(
            CHECKS_KEY,
            {
                **mount_data,
                **checks_payload(
                    draft,
                    owner=summary.scenario_id,
                    facts=facts,
                    calculations=remembered_calculations(),
                ),
            },
            on_outbox=on_outbox,
        )
    # 「그 화면으로」 의 결과 칸 — 칸이 서는 회차마다(멈춤 · 실패 · 빈 시나리오에도) 한 자리.
    render_flash(CHECK_NOTICE_KEY)
    if not revisions:
        st.caption(EMPTY_REVISIONS)
        return ()
    if not counting or revision is None:
        return ()
    if failure is not None:
        render_data_error(failure, code="SC-02", tab=CAPA_SCENARIO_TAB_NAME)
        return ()
    assert check is not None
    return _render_check(database_path, summary, revision, check, fold=fold, open_wide=open_wide)


def _render_check(
    database_path: str,
    summary: ScenarioSummary,
    revision: RevisionSummary,
    check: RevisionInputCheck,
    *,
    fold: Callable[[], ListDraft],
    open_wide: Callable[[object, str], None],
) -> WideValues:
    """칸 머리 한 줄 · 결과 칸 · 묶음 줄. 그린 「넓게 보기」 단추의 열림 값을 돌려준다."""
    number = f"r{revision.revision_no}"
    period = check.period_label
    scope = f"{number} · 전체 기간 {period}" if period else number
    # 칸 머리 한 줄에 묶음 줄 서식을 함께 싣는다(이벤트 칸 자리를 쓰지 않는 캡션 안 서식).
    st.caption(html.escape(scope) + panel_style(), unsafe_allow_html=True)
    loaded = revision.revision_id == active_persisted_revision_id()
    opened = _open_groups()
    labels = get_process_labels()
    wide_values: list[WideValue] = []
    target = (database_path, summary.scenario_id, revision.revision_id, number)
    with st.container(key=GROUPS_KEY, gap=None):
        for group in check.groups:
            if group.key == GROUP_RULES:
                continue
            wide_values.extend(
                _render_group(
                    group,
                    check,
                    expanded=group.key in opened,
                    target=target,
                    loaded=loaded,
                    labels=labels,
                    fold=fold,
                    open_wide=open_wide,
                )
            )
        rules = check.group(GROUP_RULES)
        if rules is not None:
            wide_values.extend(
                _render_rules(
                    rules,
                    expanded=GROUP_RULES in opened,
                    target=target,
                    labels=labels,
                    open_wide=open_wide,
                )
            )
    return tuple(wide_values)


def panel_style() -> str:
    """묶음 줄 서식 — 줄 사이 선 · 촘촘한 세로 간격, 글자 단추(행 보기 · 그 화면으로 · 넓게 보기)는
    강조색 작은 굵은 글(시안 `m-link`), 머리 줄은 접지 않고 이름이 접힌다. 맨 아래 규칙 줄은 선이
    없다(key 앞머리가 다르다 — 칸마다 감싸개가 따로라 `:last-child` 로 고를 수 없다). 색은
    토큰이다."""
    groups = f".st-key-{GROUPS_KEY}"
    group = f'{groups} [class*="st-key-{GROUP_KEY_PREFIX}"]'
    rules = f".st-key-{RULES_KEY}"
    link = f'{groups} [data-testid="stBaseButton-tertiary"]'
    # 묶음 CSV 내려받기도 글자 단추 꼴이다(시안 「CSV」 — 공용 내려받기 단추를 이 칸에서만 덮는다).
    download = f'{groups} [data-testid="stDownloadButton"] button'
    return (
        "<style>"
        f"{group} {{ padding: 0.45rem 0.1rem; border-bottom: 1px solid {tokens.BORDER}; }}"
        f"{rules} {{ padding: 0.45rem 0.1rem 0; }}"
        f"{link} {{ color: {tokens.ACCENT}; font-weight: 700; min-height: 0; padding: 0 0.15rem; }}"
        f"{link} p {{ font-size: 0.75rem; font-weight: 700; white-space: nowrap; }}"
        f"{download} {{ border: none; background: none; color: {tokens.ACCENT}; min-height: 0; "
        "padding: 0 0.15rem; }"
        f"{download} p {{ font-size: 0.75rem; font-weight: 700; white-space: nowrap; }}"
        f'{group} [data-testid="stDataFrame"] {{ margin-top: 0.3rem; }}'
        "</style>"
    )


def _head_markup(group: InputCheckGroup) -> str:
    """묶음 줄 머리 — 단계 표지 · 이름 · 수. 색은 토큰(알림 단계 색)이고 글자도 단계를 말한다
    (UI-ACC-03). 이름 · 수 · 표지는 앱이 지은 글이라 HTML 로 막아 넣는다."""
    colors = {"error": tokens.ALERT_ERROR, "check": tokens.ALERT_CHECK, "info": tokens.ALERT_INFO}
    parts = []
    level = LEVEL_LABELS.get(group.level)
    if level is not None:
        parts.append(
            f'<span style="color:{colors[group.level]};font-size:{_LEVEL_REM}rem;'
            f'font-weight:700;margin-right:0.4rem">{html.escape(level)}</span>'
        )
    muted = group.level in ("muted", "rule")
    title_color = f"color:{tokens.TEXT_MUTED};font-weight:600" if muted else "font-weight:700"
    parts.append(
        f'<span style="{title_color};font-size:{_TITLE_REM}rem">{html.escape(group.title)}</span>'
    )
    count = group.count_text
    if count:
        style = (
            f"font-weight:800;font-size:{_COUNT_REM}rem;font-variant-numeric:tabular-nums"
            if group.count
            else f"color:{tokens.TEXT_MUTED};font-size:{_TITLE_REM * 0.92:.3f}rem"
        )
        parts.append(f'<span style="{style};margin-left:0.5rem">{html.escape(count)}</span>')
    return "".join(parts)


def _subtitle(group: InputCheckGroup, check: RevisionInputCheck) -> tuple[str, str | None]:
    """부제(마크다운으로 막은 글)와 풍선. 멈춤은 계산 멈춤 알림의 짧은 글에서 제목과 겹치는 머리를
    뗀 글 + 「경로 n」 이고 전문은 풍선이다. 알림이 알아보지 못하는 멈춤은 원문이다."""
    if group.key != GROUP_STOP or check.stop is None:
        return literal_markdown(group.subtitle), None
    stop = check.stop
    if stop.kind == "blocked":
        return "경로 키 없는 옛 리비전", markdown_safe_tildes(stop.error)
    notice = calculation_stop_notice(ValueError(stop.error)) if stop.kind == "capacity" else None
    if notice is None:
        return markdown_safe_tildes(stop.error), None
    text = notice.text.removeprefix(STOP_NOTICE_HEAD)
    if stop.problem is not None and stop.problem.rows:
        text = f"{text} · 경로 {stop.problem.rows:,}"
    return text, notice.message


def _render_group(
    group: InputCheckGroup,
    check: RevisionInputCheck,
    *,
    expanded: bool,
    target: tuple[str, str, str, str],
    loaded: bool,
    labels: ProcessLabels,
    fold: Callable[[], ListDraft],
    open_wide: Callable[[object, str], None],
) -> list[WideValue]:
    """묶음 한 줄 — 머리(표지 · 이름 · 수 · 단추) · 부제 · 펼친 표."""
    database_path, scenario_id, revision_id, number = target
    has_rows = bool(group.count) and any(not table.frame.empty for table in group.tables)
    arrival = arrival_for(group, check)
    with st.container(key=f"{GROUP_KEY_PREFIX}{group.key}", gap=None):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=False):
            st.markdown(_head_markup(group), unsafe_allow_html=True, width="stretch")
            if has_rows:
                st.button(
                    "행 접기" if expanded else "행 보기",
                    type="tertiary",
                    key=f"input_check_rows_{group.key}",
                    on_click=_toggle_group,
                    args=(group.key,),
                )
            if arrival is not None:
                same_page = arrival.path == SCENARIO_MANAGEMENT.path
                st.button(
                    "그 화면으로",
                    type="tertiary",
                    key=f"input_check_go_{group.key}",
                    help=None if loaded or same_page else GO_LOADS_HELP,
                    on_click=_go,
                    args=(database_path, scenario_id, revision_id, arrival, fold),
                )
        subtitle, tip = _subtitle(group, check)
        if subtitle:
            st.caption(subtitle, help=tip)
        if not (expanded and has_rows):
            return []
        return [
            _render_rows(
                table,
                group=group,
                target=target,
                labels=labels,
                open_wide=open_wide,
                index=index,
            )
            for index, table in enumerate(group.tables)
        ]


def _render_rules(
    group: InputCheckGroup,
    *,
    expanded: bool,
    target: tuple[str, str, str, str],
    labels: ProcessLabels,
    open_wide: Callable[[object, str], None],
) -> list[WideValue]:
    """맨 아래 접힌 한 줄 「규칙대로 셈에서 뺀 것」 — 펼치면 두 표(PKG Buffer 밖 · 쓰지 않는 경로
    조합)를 소제목과 함께."""
    with st.container(key=RULES_KEY, gap=None):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=False):
            st.button(
                group.title,
                icon=":material/expand_more:" if expanded else ":material/chevron_right:",
                type="tertiary",
                key=f"input_check_rows_{group.key}",
                on_click=_toggle_group,
                args=(group.key,),
                disabled=not group.count,
                help=None if group.count else RULES_EMPTY_HELP,
            )
            st.markdown(
                f'<span style="font-weight:800;font-size:{_COUNT_REM}rem;'
                f'font-variant-numeric:tabular-nums">{html.escape(group.count_text)}</span>',
                unsafe_allow_html=True,
                width="stretch",
            )
        if group.subtitle:
            st.caption(literal_markdown(group.subtitle))
        if not (expanded and group.count):
            return []
        drawn = []
        for index, table in enumerate(group.tables):
            if table.frame.empty:
                continue
            st.markdown(f"**{literal_markdown(table.title)}** · {len(table.frame):,}")
            drawn.append(
                _render_rows(
                    table,
                    group=group,
                    target=target,
                    labels=labels,
                    open_wide=open_wide,
                    index=index,
                )
            )
        return drawn


def display_frame(
    table: InputCheckTable, frame: pd.DataFrame, labels: ProcessLabels
) -> pd.DataFrame:
    """화면용 사본 — 공정은 표시명, 까닭은 표시명, 달은 YY.MM. 원본(캐시가 든 행)은 고치지
    않는다."""
    shown = frame.copy()
    if PROCESS_COLUMN in shown.columns:
        shown[PROCESS_COLUMN] = labels.series(shown[PROCESS_COLUMN])
    if table.reason_column is not None and table.reason_column in shown.columns:
        shown[table.reason_column] = shown[table.reason_column].map(
            lambda value: reason_label(str(value)) if isinstance(value, str) else value
        )
    if _MONTH_COLUMN in shown.columns:
        months = pd.to_numeric(shown[_MONTH_COLUMN], errors="coerce")
        shown[_MONTH_COLUMN] = [
            month_label(int(month)) if pd.notna(month) else "" for month in months
        ]
    return shown


def _column_config(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        column: st.column_config.Column(label)
        for column, label in _COLUMN_LABELS.items()
        if column in frame.columns
    }


def _render_rows(
    table: InputCheckTable,
    *,
    group: InputCheckGroup,
    target: tuple[str, str, str, str],
    labels: ProcessLabels,
    open_wide: Callable[[object, str], None],
    index: int,
) -> WideValue:
    """펼친 표 하나 — 앞 다섯 칸 · 앞 행, 「앞 n행 · 전체 m행」 · 「넓게 보기」 · CSV. 「넓게 보기」
    열림 값을 돌려준다."""
    database_path, scenario_id, revision_id, number = target
    del database_path
    frame = table.frame
    head = frame.head(PREVIEW_ROWS)
    preview = display_frame(table, head.loc[:, table.preview_columns], labels)
    # 표 도구 막대가 바로 위 줄의 글자 단추(행 접기 · 그 화면으로)를 덮지 않게 띄운다(AGENTS 9장).
    toolbar_clearance()
    st.dataframe(
        preview,
        hide_index=True,
        width="stretch",
        placeholder="",
        column_config=_column_config(preview),
    )
    wide = (WIDE_TAG, scenario_id, revision_id, number, f"{group.key}:{index}")
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption(f"앞 {len(head):,}행 · 전체 {len(frame):,}행", width="stretch")
        wide_key = f"input_check_wide_{group.key}_{index}"
        st.button(
            WIDE_TITLE,
            type="tertiary",
            key=wide_key,
            on_click=open_wide,
            args=(wide, wide_key),
        )
        render_csv_download(
            data=frame.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"Capa_Input_Check_{group.key}_{index + 1}_{number}.csv",
            key=f"input_check_csv_{group.key}_{index}",
            label="CSV",
        )
    return wide


def wide_target(value: object) -> WideValue | None:
    """화면 팝업 호스트 열림 값이 「넓게 보기」 꼴이면 그 값 — (앞머리, 시나리오, 리비전, rN,
    묶음:표)."""
    if (
        isinstance(value, tuple)
        and len(value) == 5
        and value[0] == WIDE_TAG
        and all(isinstance(part, str) for part in value)
    ):
        return value[0], value[1], value[2], value[3], value[4]
    return None


def render_wide_body(database_path: str, value: WideValue) -> None:
    """「넓게 보기」 팝업 본문 — 그 묶음 표의 모든 칸 · 모든 행(화면 글은 표시명). 점검은 리비전
    id 로 다시 부른다(요약 칸 적중 — 칸이 빠졌으면 다시 센다)."""
    _, scenario_id, revision_id, number, where = value
    group_key, _, raw_index = where.partition(":")
    try:
        with pinned_connections(Path(database_path)):
            check = input_check_verdict(database_path, scenario_id, revision_id)
    except BOOTSTRAP_ERRORS as exc:
        render_data_error(bootstrap_error_message(exc), code="SC-02", tab=CAPA_SCENARIO_TAB_NAME)
        return
    group = check.group(group_key)
    index = int(raw_index) if raw_index.isdigit() else 0
    if group is None or index >= len(group.tables):
        st.caption("보일 행이 없습니다.")
        return
    table = group.tables[index]
    title = group.title if len(group.tables) == 1 else f"{group.title} · {table.title}"
    st.caption(f"{number} · {literal_markdown(title)} · 전체 {len(table.frame):,}행")
    shown = display_frame(table, table.frame, get_process_labels())
    toolbar_clearance()
    st.dataframe(
        shown,
        hide_index=True,
        width="stretch",
        placeholder="",
        column_config=_column_config(shown),
    )


def _arrive(arrival: Arrival) -> None:
    """도착 칸을 적는다 — 탭은 기억 칸, 기준 정보 종류는 위젯 세션 값."""
    if arrival.value is None or not arrival.key:
        return
    if arrival.tab:
        remember_open_tab(arrival.key, arrival.value)
    else:
        st.session_state[arrival.key] = arrival.value


def _notify(text: str) -> None:
    queue_flash(CHECK_NOTICE_KEY, text, kind="error", icon=":material/block:")


def _go(
    database_path: str,
    drawn_scenario: str,
    drawn_revision: str,
    arrival: Arrival,
    fold: Callable[[], ListDraft],
) -> None:
    """「그 화면으로」 콜백(결정 1 · 15). 출납을 접은 뒤의 고름이 그린 리비전이어야 한다.

    같은 화면의 탭(DB 등록)은 탭 칸만 바꾼다. 다른 화면은 화면 탭 상한을 먼저 보고
    (`refused_at_tab_limit` — 걸리면 알리고 다시 돌아 아무것도 적지 않는다), 고른 리비전이 올라와
    있지 않으면 불러온다 — 미저장 편집 · 적용 전 편집이 있으면 사이드바 시나리오 팝업이 그
    리비전으로 묻고 옮기지 않는다. 불러오기에 실패하면 단추 곁에 알린다. 옮기는 것은 다음 회차
    `app.py` 의 `switch_to_queued_tab` 이다(콜백 안 `st.switch_page` 금지 — AGENTS 9장).
    """
    # 시나리오 팝업 모듈은 이 화면 모듈을 불러오므로(순환) 누를 때 불러온다.
    from capa_simulation.components.scenario_status import (
        load_saved_revision,
        open_scenario_dialog_on,
    )

    draft = fold()
    if draft.opened != drawn_scenario or draft.picked != drawn_revision:
        _notify(PICK_MOVED_MESSAGE)
        return
    if arrival.path == SCENARIO_MANAGEMENT.path:
        st.session_state[SCENARIO_MANAGEMENT_TABS_KEY] = arrival.value
        st.session_state[remembered_tab_key(SCENARIO_MANAGEMENT_TABS_KEY)] = arrival.value
        return
    if refused_at_tab_limit(arrival.path):
        return
    if drawn_revision != active_persisted_revision_id():
        if has_unsaved_scenario_changes() or pending_edit_labels(
            Path(SCENARIO_MANAGEMENT.path).name
        ):
            open_scenario_dialog_on(drawn_scenario, drawn_revision)
            return
        with pinned_connections(Path(database_path)):
            failure = load_saved_revision(database_path, drawn_revision)
        if failure is not None:
            _notify(failure)
            return
    _arrive(arrival)
    queue_switch(arrival.path)
