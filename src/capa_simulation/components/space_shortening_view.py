# Purpose: Space 현황 「필요 단축」 보기의 조작 줄·안내·층 칸·호기 상세와 화면 사이 이동을 그린다.

"""Space 현황 색 기준 「필요 단축」(2026-10-24 사용자 결정 — 시안 승인, L1~L8·D1~D15 권장대로).

새 화면이 아니라 Space 의 보기 하나다. 사이드바 `Space 조건` 의 「색 기준」 이 `필요 단축` 이고 배치
편집 중이 아니면(결정 D7) **그 회차에만** 필요 단축 일정과 같은 계획을 같은 캐시 칸에서
꺼낸다(AGENTS 5장 9 — 끈 회차는 시뮬레이션 쪽을 한 번도 부르지 않는다). 계획은 `shortening_source`
한 길이고, 설비 쪽은 **Space 가 그리는 세션 설비 시나리오**의 계산 세 표다(설비 시나리오 2단계 LY6 —
필요 단축 일정 화면과 늘 같은 키·같은 칸).

- **목표 확보율**(`TARGET_LEVELS` 다섯 + 직접 입력 50 ~ 300%, 처음엔 필요 단축 일정 목표 → 110%)은
  사이드바 조회 조건 패널의 한 줄이다(2026-11-08 그림 메모 g05 — 보기 상태의 고르기를 조회 조건
  상자로). 다른 조건 줄과 같은 값 칸 + 팝업이고(검수 보드 p-target-form — 필요 단축 일정과 같은 부품
  `target_level_field`, 직접 입력은 2026-11-11 사용자 고칠 것 Q2-26 — 부품이 하나라 이 보기에도
  선다) 팝업은 Space 화면 팝업 호스트가 연다 — 고르거나 넣으면 곧바로 닫히며 그 목표로 다시 그린다.
  다섯 밖 값은 필요 단축 일정과 같은 길로 그 값 하나를 더
  계산한다(`load_official_shortening(level=)`). 고른 값은 세션 칸(`SPACE_SHORT_LEVEL_KEY`)이다. 배치
  편집으로 보기가 쉬는 회차에도 값 칸은 잠근 채 선다(`render_level_field`).
- **「단축 없는 호기 흐리게」 · 기준 달**은 사이드바 `Space 조건` 카드의 「색 기준」
  밑이다(2026-11-09 사용자 검수 g05 — 페이지 상단 문구 · 여백 최소화). 「필요 단축」 은 그룹 체크가
  없는 기준이라 흐리게 칸이 그 자리를 잇고(`render_dim_field`), 기준 달 값 한
  줄(`render_layer_basis`)이 그 밑에 선다 — 어느 설비 · 시뮬레이션 · 오늘인지는 그 풍선이다.
  맞대지 못한 공정은 필요 단축 일정과 같은 상태 알림 `RS-02`(`report_layer_unmatched`), 공정 필터
  밖 단축 대수는 FAB 요약 · 층 칸 머리 줄의 값이다. 본문 도면 위에는 못 읽음 마크 · 쉼 표지만
  남는다.
- **달** — 필요 단축 일정 시작·끝 월 칸 → 공용 프로필(0019) 심기를 **읽기만** 한다(결정 D3). 임박
  날수는 필요 단축 일정 「기한 임박」 칸(결정 D9). 어느 칸에도 쓰지 않는다.
- **층 보기 칸** — 이 층 요약 · 공정 칩(원본 공정소분류 — 결정 D10, 공정 표시명을 읽지 않는다) ·
  「이 층에서 단축할 호기」 표 · 도면에 자리가 없는 호기(좌표 없는 단축 호기·추가N) · 누른 호기
  상세와 「필요 단축 일정에서 이 공정 보기」.
- **두 화면 사이** — 필요 단축 일정 카드의 「도면에서 보기」 주소 인자(`layer=short` · `floor` ·
  `proc` · `target`)를 페이지 맨 앞에서 한 번 받고(`consume_layer_link`), 상세 단추는 대기 칸만 적어
  다음 회차 본문 맨 앞이 옮긴다 (`switch_to_queued_shortening` — 콜백 안 `st.switch_page` 금지).
  옮길 때 필요 단축 일정의 **강조 공정 칸과 목표 칸 둘만** 적는다(공정 필터 칸·공용 프로필·기준선은
  쓰지 않는다).

아래로 내려가는 부름은 모듈 속성으로 한다(`shortening_source.…`·`equipment_cache.…`) — 시험이 부름을
센다.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any, Final

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

import capa_simulation.components.required_shortening_panel as shortening_panel
import capa_simulation.components.shortening_source as shortening_source
import capa_simulation.persistence.equipment_cache as equipment_cache
from capa_simulation import alerts
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.dialog_host import DialogBody
from capa_simulation.components.equipment_scenario_status import equipment_value_label
from capa_simulation.components.floor_canvas_dialog import CANVAS_DIALOG_HOST
from capa_simulation.components.literal_markdown import literal_markdown, quoted
from capa_simulation.components.shortening_board import (
    DEFAULT_DUE_DAYS,
    DUE_DAYS_KEY,
    HIGHLIGHT_FROM_SPACE,
    highlight_shortening_process,
)
from capa_simulation.components.shortening_source import (
    SHORTENING_END_KEY,
    SHORTENING_LEVEL_KEY,
    SHORTENING_START_KEY,
    Frames,
    ShorteningStop,
)
from capa_simulation.components.table_toolbar import toolbar_clearance
from capa_simulation.components.target_level_field import (
    TargetLevelField,
    level_text,
    target_level,
)
from capa_simulation.design.theme import THEME_QUERY_PARAM
from capa_simulation.equipment_scenario_activation import EquipmentSession
from capa_simulation.navigation import REQUIRED_SHORTENING
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.page_tabs_state import refused_at_tab_limit
from capa_simulation.scenario_activation import (
    active_scenario_label,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_state import ActiveScenario
from capa_simulation.services.fab_layout import (
    FLOOR_KEYS,
    floor_from_param,
    floor_label,
    floor_param,
)
from capa_simulation.services.floor_layout_profile import FloorKey
from capa_simulation.services.month_columns import iso_month_text
from capa_simulation.services.required_shortening import ShorteningPlan
from capa_simulation.services.shortening_filter_profile import effective_filter_months
from capa_simulation.services.simulation_cache import RequiredShorteningCacheKey
from capa_simulation.services.space_color_basis import COLOR_BASIS_SHORTENING
from capa_simulation.services.space_shortening_layer import (
    BUCKET_EXPIRED,
    FabSummary,
    FloorLayer,
    ShorteningLayer,
    ShorteningMark,
    VirtualUnit,
    build_shortening_layer,
    day_text,
)
from capa_simulation.settings import DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH

__all__ = [
    "LAYER_PARAM",
    "LAYER_SHORT",
    "LEVEL_DIALOGS",
    "LEVEL_ENTRY_KEY",
    "LEVEL_FIELD_KEY",
    "LEVEL_PICK_KEY",
    "PINNED_NOTE",
    "PROCESS_PARAM",
    "SPACE_SHORT_DIM_KEY",
    "SPACE_SHORT_LEVEL_KEY",
    "SPACE_SHORT_PROCESS_PREFIX",
    "SPACE_SHORT_SWITCH_KEY",
    "SPACE_SHORT_TABLE_PREFIX",
    "TARGET_PARAM",
    "SpaceLayer",
    "consume_layer_link",
    "load_space_layer",
    "layer_table_columns",
    "note_unit_pick",
    "process_chip_key",
    "release_process_chip",
    "render_fab_layer_summary",
    "render_floor_layer_panel",
    "render_dim_field",
    "render_layer_basis",
    "render_layer_stop",
    "render_level_field",
    "forget_arrival_note",
    "report_arrival_filter",
    "report_layer_unmatched",
    "switch_to_queued_shortening",
    "take_unit_pick",
    "unit_keys_by_name",
    "valid_focus",
]

SPACE_SHORT_LEVEL_KEY: Final = "space_shortening_level_v1"
SPACE_SHORT_DIM_KEY: Final = "space_shortening_dim_v1"
# 목표 확보율 줄 — 조회 조건 패널의 둘째 페이지 칸(`target_level_field.LEVEL_SLOT` — 첫째는 공용
# 공정 칸)에 다른 조건 줄과 같은 이름 줄 + 값 칸이고 값 칸을 누르면 고르는 팝업이 열린다(검수 보드
# p-target-form — 필요 단축 일정과 같은 부품 `TargetLevelField`). 팝업은 Space 화면 팝업
# 호스트(`floor_canvas_dialog.CANVAS_DIALOG_HOST` — 화면당 호스트 하나)가 연다. 칸이 없으면 필요
# 단축 일정 목표(받을 수 있는 값일 때 — 다섯 또는 직접 넣은 값) → 110% 로 심는다.
LEVEL_FIELD: Final = TargetLevelField(
    state_key=SPACE_SHORT_LEVEL_KEY,
    field_key="space_shortening_level_field",
    slug="space_target",
    pick_key="space_shortening_level_pick",
    dialog="space_target_level",
    host=CANVAS_DIALOG_HOST,
    seed_keys=(SHORTENING_LEVEL_KEY,),
)
LEVEL_FIELD_KEY: Final = LEVEL_FIELD.field_key
LEVEL_DIALOG: Final = LEVEL_FIELD.dialog
LEVEL_PICK_KEY: Final = LEVEL_FIELD.pick_key
LEVEL_ENTRY_KEY: Final = LEVEL_FIELD.entry_key
# 배치 편집으로 보기가 쉬는 회차의 목표 줄 — 값 칸은 잠근 채 서고 까닭은 그 칸 풍선이다(설계 규칙
# UI-INP-07 — `condition_field` 의 잠긴 칸 풍선).
LEVEL_REST_HELP: Final = (
    "배치 편집 중에는 필요 단축 보기를 쉬어 고를 수 없습니다 — 편집을 끄면 다시 고릅니다."
)
SPACE_SHORT_PROCESS_PREFIX: Final = "space_shortening_process"
SPACE_SHORT_SWITCH_KEY: Final = "space_shortening_switch_v1"
SPACE_SHORT_TABLE_PREFIX: Final = "space_shortening_table"
_TABLE_GENERATION_KEY: Final = "space_shortening_table_generation"
# 층마다 공정 칩을 마지막으로 본 목표(`(동, 층) → 목표`) — 목표를 바꾼 회차를 알아본다
# (`release_process_chip`).
_CHIP_LEVELS_KEY: Final = "space_shortening_chip_levels"
# 이번 회차에 도면에서 호기를 눌렀다는 표지(`note_unit_pick` — 뷰어 누르기 콜백이 적는다).
_PICKED_NOW_KEY: Final = "space_shortening_picked_now"
# 「도면에서 보기」 로 온 공정 — 공정소분류 필터(공용 공정 칸)에 걸러졌는지 알리는 한 줄. (공정,
# 도착 층, 도착 때 공용 공정 값)을 쥐고 **그 층·값이 처음 바뀔 때**(또는 보기를 끌 때) 거둔다 —
# 알림은 도착한 링크에 대한 것이라 나중에 사용자가 고른 상관없는 필터에 남지 않는다.
_ARRIVED_PROCESS_KEY: Final = "space_shortening_arrived_process"
_OPEN_BOARD_PREFIX: Final = "space_shortening_open_board"
LAYER_PARAM: Final = "layer"
LAYER_SHORT: Final = "short"
PROCESS_PARAM: Final = "proc"
TARGET_PARAM: Final = "target"
# 층 상세 뷰어 기준일 고정 줄의 풍선 글(줄에 선 글은 「기준일 … · 오늘 고정」 — 편집기가 쓴다).
PINNED_NOTE: Final = "필요 단축은 오늘 기준 — 색 기준을 바꾸면 페이더로 돌아갑니다"
# 추가N 의 뜻 — FAB 요약 줄 · 층 칸 「도면에 자리가 없는 호기」 의 풍선(설계 규칙 UI-TXT-01).
_VIRTUAL_HELP: Final = (
    "추가N 은 기존 호기를 다 당겨도 모자라 새로 들여야 하는 대수입니다. 배치 편집기에서 자리를 "
    "잡으면 도면에 나타납니다."
)
# 「필터 밖 n대」 의 뜻 — FAB 요약 줄 · 층 칸 머리 줄의 풍선(숨은 데이터는 값 + 풍선 — 설계 규칙
# UI-TXT-04 · UI-NTF-05).
_FILTERED_HELP: Final = (
    "필터 밖 n대는 사이드바 「공정」 칸에 걸리지 않아 도면 · 요약에 세지 않은 FAB 전체의 단축 "
    "호기입니다."
)
UNMERGED_MESSAGE: Final = (
    "설비 시나리오 일정과 합쳐지지 않아 일정 없이 연 상태라 필요 단축을 낼 수 없습니다 — 런북 4-2"
)


_percent = level_text


def _months_text(months: str) -> str:
    """계획의 「해소 기여 월」 글(「202611, 202612」)을 「2026-11, 2026-12」 로."""
    parts = [part.strip() for part in months.split(",") if part.strip()]
    return ", ".join(
        iso_month_text(int(part)) if part.isdigit() and len(part) == 6 else part for part in parts
    )


_target_level = target_level


def process_chip_key(floor: FloorKey) -> str:
    """층마다 따로인 공정 칩 위젯 key — 다른 층으로 옮기면 남지 않는다."""
    return f"{SPACE_SHORT_PROCESS_PREFIX}_{floor[0]}_{floor[1]}"


# ------------------------------------------------------------------ 두 화면 사이


def consume_layer_link(
    *,
    basis_key: str,
    location_keys: tuple[str, str],
    floor_param_name: str,
    clear_keys: Sequence[str],
    edit_keys: Sequence[str],
    inactive: Collection[FloorKey],
    filter_values: Sequence[str],
) -> bool:
    """필요 단축 일정 「도면에서 보기」 주소(`?layer=short&floor=C1-2F&proc=W/B&target=1.1`)를 한 번
    받는다.

    색 기준 칸 = 필요 단축, 목표 칸 = `target`(받을 수 있는 목표일 때만 — 다섯 또는 50 ~ 300% 의
    직접 넣은 값, `target_level_field.target_level`), 그 층의 공정 칩 칸 =
    `proc`(선택지 확인은 칩을 그릴 때), `clear_keys`(누른 호기) 비움, `edit_keys`(층·FAB 배치 편집
    토글) 끔 — 링크로 보러 왔다. `filter_values` 는 지금 공용 공정 값(`shared_process.values()` —
    Space 공정소분류가 따라가는 값)이다 — 도착 때 값을 알림 칸에 함께 적어 그 값이 바뀌면 알림을
    거둔다(공정 값 자체는 건드리지 않는다). `floor` 가 사용
    층이면 세션 층을 **덮는다**(지금 규칙은 세션이 먼저 — 링크만 예외), 없거나 비활성 층이면(링크
    대상이 아니다) 세션 층을 지워 FAB 전체로 연다. 남길 인자(`floor`·테마·그 밖)는 `from_dict` **한
    번**으로 다시 싣는다(기록이 키 수만큼 쌓이지 않게). 받았으면 참이다(받는 쪽이 사이드바를
    맞추려고 회차를 한 번 더 돈다).
    """
    params = st.query_params
    if params.get(LAYER_PARAM) != LAYER_SHORT:
        return False
    st.session_state[basis_key] = COLOR_BASIS_SHORTENING
    level = _target_level(params.get(TARGET_PARAM))
    if level is not None:
        st.session_state[SPACE_SHORT_LEVEL_KEY] = level
    for key in clear_keys:
        st.session_state.pop(key, None)
    for key in edit_keys:
        st.session_state[key] = False
    floor = floor_from_param(params.get(floor_param_name))
    if floor is not None and floor in set(inactive):
        floor = None
    building_key, floor_key = location_keys
    if floor is None:
        st.session_state.pop(building_key, None)
        st.session_state.pop(floor_key, None)
    else:
        st.session_state[building_key], st.session_state[floor_key] = floor
    process = params.get(PROCESS_PARAM)
    process = process.strip() if isinstance(process, str) else ""
    if process:
        st.session_state[_ARRIVED_PROCESS_KEY] = (process, floor, _filter_values(filter_values))
        if floor is not None:
            st.session_state[process_chip_key(floor)] = process
            # 링크가 목표와 칩을 함께 정했다 — 「목표를 바꿨다」 로 보고 칩을 풀지 않게.
            _forget_chip_level(floor)
    else:
        st.session_state.pop(_ARRIVED_PROCESS_KEY, None)
    kept = {
        name: params.get_all(name)
        for name in params
        if name not in (LAYER_PARAM, PROCESS_PARAM, TARGET_PARAM)
        and not (name == floor_param_name and floor is None)
    }
    if floor is not None:
        kept[floor_param_name] = [floor_param(floor)]
    st.query_params.from_dict(kept)
    return True


def _queue_switch(process: str, level: float) -> None:
    """「필요 단축 일정에서 이 공정 보기」 콜백 — 대기 칸만 적는다(옮기기는 다음 회차 본문 맨
    앞)."""
    st.session_state[SPACE_SHORT_SWITCH_KEY] = (str(process), float(level))


def switch_to_queued_shortening() -> None:
    """대기 칸이 있으면 필요 단축 일정으로 옮긴다 — 페이지 본문 맨 앞에서 부른다.

    강조 공정 칸(출처 「Space 도면에서 연 공정」)과 필요 단축 일정 목표 칸 **둘만** 적는다 — 공정
    필터 칸·공용 프로필(0019)·기준선(0021)은 건드리지 않는다(2026-10-22 결함 규칙 그대로). 화면 탭
    상한에 걸리면 적지 않는다. 내비게이션이 없으면(단독 실행) 옮기지 않고 대기 칸만 거둔다.
    """
    queued = st.session_state.pop(SPACE_SHORT_SWITCH_KEY, None)
    if not (isinstance(queued, tuple) and len(queued) == 2 and isinstance(queued[0], str)):
        return
    process, raw_level = queued
    level = _target_level(raw_level)
    if refused_at_tab_limit(REQUIRED_SHORTENING.path):
        return
    highlight_shortening_process(process, source=HIGHLIGHT_FROM_SPACE)
    if level is not None:
        st.session_state[SHORTENING_LEVEL_KEY] = level
    theme = st.query_params.get(THEME_QUERY_PARAM)
    try:
        st.switch_page(
            REQUIRED_SHORTENING.path, query_params={THEME_QUERY_PARAM: theme} if theme else None
        )
    except StreamlitPageNotFoundError:
        return


# ------------------------------------------------------------------ 조작 칸


def render_level_field(*, resting: bool = False) -> float:
    """목표 확보율 줄 — 사이드바 조회 조건 패널의 페이지 칸(`LEVEL_SLOT`)에 이름 줄 + 값 칸으로
    선다(2026-11-08 그림 메모 g05 — 사이드바 조회 조건 상자로, 검수 보드 p-target-form — 다른 조건
    줄처럼 값 칸 + 팝업, 부품은 `TargetLevelField`). 고른 목표를 돌려준다.

    `resting` 은 보기를 골랐지만 배치 편집으로 쉬는 회차다 — 값 칸은 잠근 채 같은 자리에 서고
    까닭은 그 칸 풍선이다. 줄이 빠지면 켜고 끌 때마다 아래 「Space 도면」 상자와 방금 누른 「배치
    편집」 토글이 줄 높이만큼 오르내렸다(설계 규칙 UI-PRF-03 · UI-INP-07).
    """
    return LEVEL_FIELD.render(help=LEVEL_REST_HELP if resting else None, disabled=resting)


# Space 화면 팝업 호스트가 함께 여는 팝업(열림 값 → (팝업, 입력 위젯 key)) — 보기를 그리는 회차에만
# 넘긴다(`render_floor_canvas_dialog_host(others=)`).
LEVEL_DIALOGS: Final[dict[str, tuple[DialogBody, tuple[str, ...]]]] = LEVEL_FIELD.dialogs


def render_dim_field() -> bool:
    """「단축 없는 호기 흐리게」 — 사이드바 `Space 조건` 카드의 「색 기준」 밑, 「필요 단축」 을
    고른 회차에만 부른다(2026-11-09 사용자 검수 g05 — 도면 위 본문 조작 줄에서 옮김). 다른 기준의
    그룹 체크와 같은 자리다(필요 단축은 그룹이 없다). 배치 편집으로 보기가 쉬는 회차에도 선다 —
    고른 값은 편집을 끈 뒤 보기가 쓴다. 칸이 없으면 켬으로 심는다."""
    if not isinstance(st.session_state.get(SPACE_SHORT_DIM_KEY), bool):
        st.session_state[SPACE_SHORT_DIM_KEY] = True
    return bool(
        st.checkbox(
            "단축 없는 호기 흐리게",
            key=SPACE_SHORT_DIM_KEY,
            persist_state="session",
        )
    )


@dataclass(frozen=True)
class SpaceLayer:
    """이 회차 보기의 재료 — 계획(키와 한 묶음)과 고른 목표의 표시."""

    layer: ShorteningLayer
    plan_key: RequiredShorteningCacheKey
    plan: ShorteningPlan
    months: tuple[int, ...]
    # 계획을 낸 활성 시나리오 — 맞대지 못한 공정 알림(`RS-02`)의 범위가 필요 단축 일정과 같게.
    scenario: ActiveScenario


def _due_days() -> int:
    value = st.session_state.get(DUE_DAYS_KEY)
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else DEFAULT_DUE_DAYS
    )


def load_space_layer(
    *,
    saved: Frames,
    sample: bool,
    show_sample: bool,
    has_snapshot: bool,
    database_path: str,
    today: date,
    level: float,
    unmerged: bool,
) -> SpaceLayer | ShorteningStop:
    """필요 단축 일정과 같은 함수·같은 키로 계획을 꺼내 고른 목표의 표시를 만든다. 못 내면 까닭.

    `saved` 는 Space 가 그리는 세션 설비 시나리오의 계산 세 표(샘플로 갈아 끼우기 전)다. 일정 없이
    연 회차 (`unmerged`)는 계획을 부르지 않는다. 시뮬레이션 쪽 오류(`BOOTSTRAP_ERRORS`)와 계산
    실패(`ValueError`)만 여기서 받는다 — 그 밖의 예외는 지금처럼 화면 오류다.
    """
    if unmerged:
        return ShorteningStop("info", UNMERGED_MESSAGE)
    try:
        demand = shortening_source.load_shortening_demand()
    except BOOTSTRAP_ERRORS as exc:
        return ShorteningStop(
            "scenario",
            bootstrap_error_message(exc, database_paths=(DUCKDB_PATH, EQUIPMENT_DUCKDB_PATH)),
        )
    try:
        cutoff = equipment_cache.load_process_cutoff(database_path)
    except BOOTSTRAP_ERRORS as exc:
        return ShorteningStop(
            "error", bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
        )
    options = shortening_source.shortening_month_options(demand, cutoff)
    if isinstance(options, ShorteningStop):
        return options
    months = effective_filter_months(
        options,
        shortening_source.shortening_filter_profile_or_default(database_path),
        st.session_state.get(SHORTENING_START_KEY),
        st.session_state.get(SHORTENING_END_KEY),
    )
    frames = shortening_source.shortening_frames(
        saved, sample=sample, show_sample=show_sample, has_snapshot=has_snapshot, today=today
    )
    try:
        manual = shortening_source.manual_downtime_for(database_path)
    except BOOTSTRAP_ERRORS as exc:
        return ShorteningStop(
            "error", bootstrap_error_message(exc, database_paths=(EQUIPMENT_DUCKDB_PATH,))
        )
    try:
        keyed = shortening_source.load_official_shortening(
            demand, frames, cutoff, tuple(months), today, manual_downtime=manual, level=level
        )
    except ValueError as exc:
        return ShorteningStop(
            "error", f"필요 단축 일정을 계산하지 못했습니다 — {bootstrap_error_message(exc)}"
        )
    if not keyed.plan.processes:
        return ShorteningStop(
            "info",
            "시나리오 소요대수와 설비 일정 기준 가용대수에 같은 이름으로 함께 있는 공정이 "
            "없습니다.",
        )
    layer = build_shortening_layer(
        keyed.plan, level, today=keyed.plan.today, imminent_days=_due_days()
    )
    return SpaceLayer(
        layer=layer,
        plan_key=keyed.key,
        plan=keyed.plan,
        months=tuple(months),
        scenario=demand.context.active_scenario,
    )


def _equipment_basis_text(session: EquipmentSession) -> str:
    """기준 캡션의 설비 쪽 — 「운영 일정 · r12 · 공식 v3」·「셋업 실무 · r4 · 가정」.

    이미 마크다운에 싣는 글이다 — 시나리오 이름은 `equipment_value_label` 이 `literal_markdown` 으로
    막았다. 한 번 더 막으면 `\\` 자체가 막혀 「가정\\~R5」 처럼 역슬래시가 글자로 보인다."""
    text = equipment_value_label(session)
    if session.is_official_pair and session.release_no is not None:
        return f"{text} · 공식 v{session.release_no}"
    if session.is_assumption:
        return f"{text} · 가정"
    return text


def render_layer_basis(session: EquipmentSession, space_layer: SpaceLayer, *, sample: bool) -> None:
    """기준 달 값 한 줄 — 사이드바 `Space 조건` 카드의 흐리게 칸 밑(FAB·층 공통, 2026-11-09 사용자
    검수 g05 — 도면 위에서 옮김). 줄에는 다른 자리에 없는 값(달 범위)만 둔다 — 설비 시나리오 ·
    시뮬레이션(미저장 편집 포함 여부) · 오늘은 사이드바 줄 · 머리 변경 칩 · 고정 줄과 거듭되어
    풍선이다(설계 규칙 UI-TXT-04 · UI-TXT-07 · UI-LAY-04)."""
    label = active_scenario_label()
    scenario = (
        f"「{literal_markdown(label.scenario_name)} · r{label.revision_no}」"
        if label is not None
        else "활성 시나리오"
    )
    months = space_layer.months
    span = f"{iso_month_text(months[0])}~{iso_month_text(months[-1])}" if months else "달 없음"
    equipment = (
        "설비 샘플(데모)" if sample else f"설비 시나리오 「{_equipment_basis_text(session)}」"
    )
    unsaved = " (미저장 편집 포함)" if has_unsaved_scenario_changes() else ""
    st.caption(
        f":material/grid_view: {span}",
        width="stretch",
        help=(
            f"필요 단축 · {equipment} 기준 · 시뮬레이션 {scenario}{unsaved} · "
            f"오늘 {space_layer.plan.today.isoformat()} — 필요 단축 일정과 같은 계산"
        ),
    )


def report_layer_unmatched(
    space_layer: SpaceLayer, *, revision: tuple[str | None, int | None]
) -> None:
    """맞대지 못한 공정 — 필요 단축 일정과 같은 상태 알림 `RS-02`(같은 계획 · 범위 · 내용 — 화면을
    옮겨도 다시 뜨지 않는다). 도면 위 표지 한 줄이던 것이다(2026-11-09 사용자 검수 g05 — 화면에 상태
    문장을 달지 않는다, 설계 규칙 UI-NTF-02). 보기를 그린 회차에만 부른다 — 끈 · 쉬는 · 못 읽은
    회차는 이 조건을 보지 않으므로 해소로 부르지 않는다(부르는 쪽이 같은 자리에서 `alerts.flush()`).
    `revision` 은 계산 세 표를 낸 설비 저장 리비전(id, 번호)이고 샘플이면 (None, None) 이다."""
    shortening_panel.report_unmatched_processes(
        space_layer.plan,
        active_scenario=space_layer.scenario,
        months=space_layer.months,
        revision=revision,
    )


def render_layer_stop(stop: ShorteningStop) -> None:
    """못 칠함(R5) — 조작 줄 안 한 자리. 소요를 못 읽음 · 계산 오류 · 다른 화면에서 채울 입력이
    빠짐(Cut-off — 「그 화면으로」 가 그 화면을 연다)은 마크(글은 알림)이고, 칠할 것이 없는 빈
    상태는 회색 평문 한 줄이다. 상자는 모두 기본 회색이고 배치·편집·다른 색 기준은 그대로다."""
    if stop.kind == "info":
        st.caption(stop.message or "")
        return
    if stop.kind == "scenario":
        reason = "활성 시나리오의 소요대수를 읽지 못했습니다" + (
            f" — {stop.message}" if stop.message else ""
        )
    else:
        reason = stop.message or "계획을 세우지 못했습니다"
    message = (
        f"필요 단축을 칠하지 못했습니다: {reason} 도면·배치 편집·다른 색 기준은 그대로 씁니다."
    )
    render_data_error(
        message, code="EQ-10", text=stop.brief("필요 단축을 칠하지 못했습니다"), goto=stop.goto
    )


def _filter_values(value: object) -> tuple[str, ...]:
    """공용 공정 값(목록)을 견줄 수 있는 글자 튜플로."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def forget_arrival_note() -> None:
    """도착 알림 칸을 거둔다 — 보기가 켜지지 않은 회차에 부른다(끈 뒤 다시 켜도 옛 링크 알림이
    서지 않게)."""
    st.session_state.pop(_ARRIVED_PROCESS_KEY, None)


# 「도면에서 보기」 로 온 공정이 공정 필터 밖일 때의 사건 알림(`EQ-24`) — 도면 위 표지 줄 대신
# 도착한 회차에 한 번 뜬다(2026-11-09 사용자 보드 T10, 설계 규칙 UI-NTF-01 · UI-TXT-04).
ARRIVAL_FILTER_ALERT: Final = "EQ-24"


def report_arrival_filter(
    selected_processes: Sequence[str], floor: FloorKey | None, filter_values: Sequence[str]
) -> None:
    """「도면에서 보기」 로 온 공정이 Space 공정소분류 거름(공용 공정 칸)에 걸러졌으면 사건 알림
    한 번(`EQ-24` — 공정 값은 건드리지 않는다). 도면 위에 표지 줄을 세우지 않는다 — **그리지
    않는다**(`alerts.event` 는 담기만 하고 같은 회차의 늘 부르는 표지 자리가 보낸다). 도착한 층 ·
    공용 값(`filter_values`)이 그대로인 동안 처음 본 회차에만 — 낸 뒤나 층을 옮기거나 값이 바뀌면
    칸을 거두고 다시 내지 않는다. `selected_processes` 는 이 화면에 걸린 공정이다."""
    held = st.session_state.get(_ARRIVED_PROCESS_KEY)
    if not (isinstance(held, tuple) and len(held) == 3 and isinstance(held[0], str)):
        st.session_state.pop(_ARRIVED_PROCESS_KEY, None)
        return
    process, arrived_floor, arrived_filter = held
    if arrived_floor != floor or arrived_filter != _filter_values(filter_values):
        st.session_state.pop(_ARRIVED_PROCESS_KEY, None)
        return
    if not process or not selected_processes or process in set(selected_processes):
        return
    st.session_state.pop(_ARRIVED_PROCESS_KEY, None)
    alerts.event(
        ARRIVAL_FILTER_ALERT,
        # 짧은 글은 무엇 · 어디만(긴 공정 이름도 60자 안 — `SHORT_LIMIT`), 하는 법은 전문이다.
        text=f"필터 밖 {quoted(process)} — 사이드바 「공정」 칸에 없음",
        full=(
            f"Space 현황 — 필요 단축 일정 「도면에서 보기」 로 연 {quoted(process)} 공정이 "
            "사이드바 「공정」 칸(다른 화면과 같이 쓰는 공정 거름)에 없어 그 단축 호기가 "
            "도면 · 요약에 보이지 않습니다 — 공정을 비우거나 더하면 보입니다."
        ),
        cause="「도면에서 보기」 로 도착",
    )


# ------------------------------------------------------------------ FAB 전체


def render_fab_layer_summary(
    space_layer: SpaceLayer, summary: FabSummary, virtuals: Sequence[VirtualUnit]
) -> None:
    """FAB 도면 아래 요약 한 줄과 「도면에 자리가 없는 추가 호기」 상자(처음 접힘).

    단축 대수는 모든 층 합이다(결정 그대로). 괄호 안은 도면에 그린 것 · 비활성 층(그려지지 않는다 —
    있을 때만) · 자리 없음으로 나눈다 — 비활성 층 대수를 「도면」 에 넣고 끝에 따로 적으면 셈이
    맞아 보이지 않았다(E2E r1)."""
    shown = summary.drawn - summary.inactive
    where = [f"도면 {shown}"]
    if summary.inactive:
        where.append(f"비활성 층 {summary.inactive}")
    where.append(f"자리 없음 {summary.unplaced}")
    parts = [
        f"목표 {_percent(space_layer.layer.level)}",
        f"단축 {summary.total}대({' · '.join(where)})",
    ]
    if summary.total:
        parts.append(f"최대 −{summary.max_days}일")
    parts.append(f"기한 지남 {summary.expired}")
    if summary.expired_months:
        parts.append(f"기한 지남 달 {summary.expired_months}")
    parts.append(f"추가 호기 {summary.virtual}대")
    tips = [_VIRTUAL_HELP]
    if summary.filtered_out:
        parts.append(f"필터 밖 {summary.filtered_out}대")
        tips.append(_FILTERED_HELP)
    st.caption(
        ":material/event_upcoming: " + " · ".join(parts), width="stretch", help=" ".join(tips)
    )
    if not virtuals:
        return
    with st.expander(
        f"도면에 자리가 없는 추가 호기 {len(virtuals)}대",
        expanded=False,
        key="space_shortening_unplaced_expander",
    ):
        # 표 도구 막대가 바로 위 펼침 머리의 오른쪽 끝(접는 자리)을 덮지 않게(AGENTS 9장).
        toolbar_clearance()
        st.dataframe(
            _virtual_frame(virtuals),
            hide_index=True,
            width="stretch",
            key="space_shortening_fab_virtuals",
        )


def _virtual_frame(virtuals: Sequence[VirtualUnit]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "공정": [unit.process for unit in virtuals],
            "이름": [unit.name for unit in virtuals],
            "필요 Qual": [unit.target_qual.isoformat() for unit in virtuals],
            "대상 월": [iso_month_text(unit.month) if unit.month else "" for unit in virtuals],
        }
    )


# ------------------------------------------------------------------ 층 상세


def valid_focus(floor: FloorKey, processes: Collection[str]) -> str | None:
    """이 층 공정 칩의 지금 값 — 이번 선택지(이 층에 그린 공정) 밖이면 위젯 전에 None 을 **적는다**
    (pop 하지 않는다 — AGENTS 9장). 칩을 그리기 전·도면을 칠하기 전에 부른다."""
    key = process_chip_key(floor)
    value = st.session_state.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or value not in set(processes):
        st.session_state[key] = None
        return None
    return value


def note_unit_pick() -> None:
    """층 상세 도면의 호기 누르기 콜백이 부른다 — 이번 회차 본문이 칩 밖 공정의 호기를 누른 것인지
    가린다(`release_process_chip`)."""
    st.session_state[_PICKED_NOW_KEY] = True


def take_unit_pick() -> bool:
    """이번 회차에 도면에서 호기를 눌렀는가 — 표지를 거둔다. 층 상세를 그리는 회차마다 부른다."""
    return bool(st.session_state.pop(_PICKED_NOW_KEY, False))


def _chip_levels() -> dict[FloorKey, float]:
    stored = st.session_state.get(_CHIP_LEVELS_KEY)
    return dict(stored) if isinstance(stored, dict) else {}


def _forget_chip_level(floor: FloorKey) -> None:
    levels = _chip_levels()
    if levels.pop(floor, None) is not None:
        st.session_state[_CHIP_LEVELS_KEY] = levels


def release_process_chip(
    floor: FloorKey,
    level: float,
    floor_layer: FloorLayer,
    *,
    picked_processes: Collection[str] | None = None,
) -> bool:
    """공정 칩을 풀 회차면 칩 칸에 None 을 **적고**(pop 하지 않는다 — AGENTS 9장) 참이다. 칩 위젯과
    도면 payload 전에 부른다 — 참이면 부르는 쪽이 칩 없이(`focus=None`) 층 보기를 다시 낸다.

    - 목표를 바꿨는데(칩을 마지막으로 본 목표와 다르다) 칩 공정이 새 목표에서 이 층에 단축할 것이
      없다(목록·자리 없음·추가N 이 모두 비었다 — 칩 글 「단축 없음」). 칩이 남으면 층 호기가 다
      흐려졌다(E2E r1). 그 목표에서 사용자가 일부러 고른 「단축 없음」 칩은 남긴다.
    - 이번 회차에 도면에서 칩 공정이 아닌 호기를 눌렀다(`picked_processes` — 그 호기의 공정소분류,
      누르지 않은 회차는 None). 머리 줄은 칩 공정을, 상세 카드는 다른 공정 호기를 말했다(E2E r3).

    그 밖이면 칩을 본 목표를 지금 목표로 적는다. 칩이 없으면 적어 둔 목표를 지운다."""
    focus = floor_layer.focus
    if focus is None:
        _forget_chip_level(floor)
        return False
    levels = _chip_levels()
    seen = levels.get(floor)
    quiet = not floor_layer.rows and not floor_layer.unplaced and not floor_layer.virtuals
    changed = seen is not None and not math.isclose(seen, level)
    outside = picked_processes is not None and focus not in set(picked_processes)
    release = (changed and quiet) or outside
    if release:
        st.session_state[process_chip_key(floor)] = None
        levels.pop(floor, None)
    else:
        levels[floor] = level
    st.session_state[_CHIP_LEVELS_KEY] = levels
    return release


def _pick_table_row(floor: FloorKey, pick_ids: tuple[str, ...], key: str, picked_key: str) -> None:
    """「이 층에서 단축할 호기」 줄 고르기 콜백 — 그 호기를 누른 것과 같다. 표 key 세대를 올려 고른
    줄은 남기지 않는다(`shortening_board._pick_board_row` 꼴)."""
    state = st.session_state.get(key)
    rows: Sequence[object] = ()
    try:
        selection = state["selection"] if state is not None else None
        rows = selection["rows"] if selection is not None else ()
    except (KeyError, TypeError):
        rows = ()
    picked = [int(str(row)) for row in rows if str(row).isdigit()]
    if picked and 0 <= picked[0] < len(pick_ids):
        st.session_state[picked_key] = (floor[0], floor[1], pick_ids[picked[0]])
    generation = st.session_state.get(_TABLE_GENERATION_KEY, 0)
    st.session_state[_TABLE_GENERATION_KEY] = (generation if isinstance(generation, int) else 0) + 1


def _mark_frame(rows: Sequence[ShorteningMark], managers: Mapping[str, str | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "호기": [mark.unit for mark in rows],
            "공정": [mark.process for mark in rows],
            "단축(일)": [mark.days for mark in rows],
            "목표 Qual": [mark.target_qual.isoformat() for mark in rows],
            "D-n/기한": [mark.sub_text for mark in rows],
            "담당자": [managers.get(mark.unit) or "" for mark in rows],
        }
    )


def _tag(mark: ShorteningMark) -> str:
    if mark.bucket == BUCKET_EXPIRED:
        return ":red-badge[기한 지남]"
    if mark.imminent:
        return ":orange-badge[임박]"
    return ":gray-badge[여유]"


def _render_picked(
    floor: FloorKey,
    picked_unit: str,
    picked_rows: pd.DataFrame,
    space_layer: SpaceLayer,
    key_of: Mapping[str, str],
) -> None:
    """누른 호기 상세 — 이름(모듈은 Main 설비) · 공정 · Model · 층 · 모듈 수, 단축 일수와 꼬리표,
    Qual 일정 기존 → 목표, 목표까지, 대상 월, 상태, 담당자, 「필요 단축 일정에서 이 공정 보기」.
    단축이 없으면 그 말과 상태·Qual 일정만."""
    level = space_layer.layer.level
    unit_key = key_of.get(picked_unit, picked_unit)
    mark = space_layer.layer.marks.get(unit_key)
    first = picked_rows.iloc[0] if not picked_rows.empty else None
    stage = str(first["단계"]) if first is not None and "단계" in picked_rows.columns else ""
    qual = first["Qual일정"] if first is not None and "Qual일정" in picked_rows.columns else None
    qual_text = "" if qual is None or pd.isna(qual) else str(qual)[:10]
    with st.container(border=True, key=f"space_shortening_picked_{floor[0]}_{floor[1]}"):
        name = literal_markdown(unit_key)
        if mark is None:
            st.markdown(f"**{name}**")
            st.caption(
                f"목표 {_percent(level)} 에서는 이 호기를 당길 필요가 없습니다."
                + (f" · 상태 {stage}" if stage else "")
                + (f" · Qual 일정 {qual_text}" if qual_text else "")
            )
            return
        facts = [literal_markdown(mark.process)]
        if mark.model:
            facts.append(literal_markdown(mark.model))
        facts.append(floor_label(floor))
        if mark.modules > 1:
            facts.append(f"모듈 {mark.modules}개 한 대")
        st.markdown(f"**{name}** · " + " · ".join(facts))
        st.markdown(f"### {mark.main_text} {_tag(mark)}")
        month = (
            f"{iso_month_text(mark.month)} 부족을 메웁니다" if mark.month is not None else "—"
        ) + (f" (해소 기여 월 {_months_text(mark.contributes)})" if mark.contributes else "")
        lines = [
            f"Qual 일정 ~~{mark.original_qual.isoformat()}~~ → **{mark.target_qual.isoformat()}**",
            f"목표까지 {mark.sub_text}",
            f"대상 월 {month}",
        ]
        if stage:
            lines.append(f"상태 {stage}")
        if mark.manager:
            lines.append(f"담당자 {literal_markdown(mark.manager)}")
        st.markdown("  \n".join(lines))
        st.button(
            "필요 단축 일정에서 이 공정 보기",
            icon=":material/event_upcoming:",
            key=f"{_OPEN_BOARD_PREFIX}_{floor[0]}_{floor[1]}",
            on_click=_queue_switch,
            args=(mark.process, level),
            help=(
                "필요 단축 일정 화면을 이 공정 카드 강조(「Space 도면에서 연 공정」)·같은 목표로 "
                "엽니다. "
                "공정 필터와 공용 조회 조건은 바꾸지 않습니다."
            ),
        )


def render_floor_layer_panel(
    floor: FloorKey,
    floor_layer: FloorLayer,
    space_layer: SpaceLayer,
    *,
    picked_unit: str | None,
    picked_rows: pd.DataFrame | None,
    key_of: Mapping[str, str],
    picked_key: str,
    filtered_out: int = 0,
) -> None:
    """층 보기 칸 — 이 층 요약 · 공정 칩 · 누른 호기 상세 · 「이 층에서 단축할 호기」 · 자리 없는
    호기. 늘 서는 바깥 칸(테두리 없음) 안에서 켠 동안만 부른다 — 이 함수가 테두리 칸 하나를
    세운다. `filtered_out` 은 공정 필터 밖 FAB 전체 단축 대수다(머리 줄 끝 값 + 풍선)."""
    level = space_layer.layer.level
    with st.container(border=True, key=f"space_shortening_panel_{floor[0]}_{floor[1]}"):
        rows, loose, virtuals = floor_layer.rows, floor_layer.unplaced, floor_layer.virtuals
        # 공정 칩을 고르면 아래 수·목록은 그 공정만 센다 — 머리 줄과 빈 글도 그 공정을 말한다(층에
        # 다른 공정의 단축 호기·배지가 남아 있는데 「이 층에는 없다」 고 하지 않게).
        focus = floor_layer.focus
        scope = "이 층" if focus is None else f"이 층 · {literal_markdown(focus)}"
        parts = [f"{scope} · 목표 {_percent(level)}", f"단축 {len(rows) + len(loose)}대"]
        if rows or loose:
            parts.append(f"최대 −{floor_layer.max_days}일")
        if virtuals:
            parts.append(f"추가 {len(virtuals)}")
        if floor_layer.elsewhere:
            parts.append(f"다른 층 {floor_layer.elsewhere}대")
        if filtered_out:
            parts.append(f"필터 밖 {filtered_out}대")
        st.markdown(
            "**:material/event_upcoming: " + " · ".join(parts) + "**",
            help=_FILTERED_HELP if filtered_out else None,
        )
        if floor_layer.chips:
            st.pills(
                "이 층 공정",
                options=list(floor_layer.chips),
                # 선택지 글은 마크다운으로 그려진다 — 공정소분류 이름(「Die~Attach~2」)은 글자
                # 그대로(2026-10-27 E2E). 고른 값은 이름 원본이다.
                format_func=lambda process: literal_markdown(
                    floor_layer.chips.get(process, process)
                ),
                selection_mode="single",
                key=process_chip_key(floor),
                help=(
                    "고르면 다른 공정의 호기·배지를 흐리고 아래 목록을 그 공정만으로 좁힙니다. "
                    "비우면 모든 공정."
                ),
            )
        if picked_unit is not None and picked_rows is not None:
            _render_picked(floor, picked_unit, picked_rows, space_layer, key_of)
        if not rows and not loose and not virtuals:
            # 빈 결과 한 줄 — 칩을 비우는 법은 칩 풍선이 말한다(설계 규칙 UI-TXT-04).
            st.caption(
                f"이 층에는 목표 {_percent(level)} 에서 단축할 호기가 없습니다."
                if focus is None
                else f"이 층 {literal_markdown(focus)} 공정에는 목표 {_percent(level)} 에서 단축할 "
                "호기가 없습니다."
            )
            return
        managers = {mark.unit: mark.manager for mark in (*rows, *loose)}
        if rows:
            st.markdown("**이 층에서 단축할 호기**")
            generation = st.session_state.get(_TABLE_GENERATION_KEY, 0)
            table_key = f"{SPACE_SHORT_TABLE_PREFIX}_{floor[0]}_{floor[1]}_{generation}"
            st.dataframe(
                _mark_frame(rows, managers),
                hide_index=True,
                width="stretch",
                key=table_key,
                on_select=partial(
                    _pick_table_row, floor, tuple(floor_layer.pick_ids), table_key, picked_key
                ),
                selection_mode="single-row",
            )
        if loose or virtuals:
            st.markdown(
                "**도면에 자리가 없는 호기**",
                help=(
                    "좌표가 없어 그리지 못한 단축 호기와, 이 층에 호기가 그려진 공정의 추가N "
                    f"입니다. {_VIRTUAL_HELP}"
                ),
            )
            frame = pd.concat(
                [
                    _mark_frame(loose, managers).assign(구분="좌표 없음"),
                    pd.DataFrame(
                        {
                            "호기": [unit.name for unit in virtuals],
                            "공정": [unit.process for unit in virtuals],
                            "단축(일)": [None] * len(virtuals),
                            "목표 Qual": [unit.target_qual.isoformat() for unit in virtuals],
                            "D-n/기한": [day_text(unit.left) for unit in virtuals],
                            "담당자": [""] * len(virtuals),
                            "구분": ["추가"] * len(virtuals),
                        }
                    ),
                ],
                ignore_index=True,
            )
            st.dataframe(
                frame.loc[
                    :, ["구분", "호기", "공정", "단축(일)", "목표 Qual", "D-n/기한", "담당자"]
                ],
                hide_index=True,
                width="stretch",
                # 추가N 의 단축(일)은 없다 — 리터럴 "None" 대신 비운다.
                placeholder="",
                key=f"space_shortening_loose_{floor[0]}_{floor[1]}",
            )


def unit_keys_by_name(rows: pd.DataFrame) -> dict[str, str]:
    """설비명 → 설비키(상태 표의 「설비키」, 없으면 설비명)."""
    if rows.empty:
        return {}
    names = rows["설비명"].astype("string").str.strip()
    keys = rows["설비키"].astype("string").str.strip() if "설비키" in rows.columns else names
    return {
        str(name): str(key) if not pd.isna(key) else str(name)
        for name, key in zip(names, keys, strict=True)
        if not pd.isna(name)
    }


def layer_table_columns(counts: Mapping[FloorKey, Any]) -> dict[FloorKey, dict[str, object]]:
    """층 목록 표에 켠 동안만 붙는 칸 넷(사용 층만 — 비활성 층은 층 대수를 싣지 않는다)."""
    out: dict[FloorKey, dict[str, object]] = {}
    for key in FLOOR_KEYS:
        count = counts.get(key)
        out[key] = {
            "단축 호기": int(count.units) if count is not None else 0,
            "최대 단축(일)": int(count.max_days) if count is not None and count.units else None,
            "기한 지남": int(count.expired) if count is not None else 0,
            "추가 호기": int(count.virtual) if count is not None else 0,
        }
    return out
