# Purpose: 제약 시뮬레이션의 세션 키·기본값·버튼 값·주소 인자 계약과 그림 key 를 UI 없이 선언한다.

"""UI 모듈을 import 하지 않아도 읽을 수 있는 「제약 시뮬레이션」 세션 계약.

`app.py`(칸 선택 그림 key — 터치 스크롤 막이 묶음)와 공정 Capa 상세(머리 링크의 주소 인자)가 이
모듈을 import 한다 — 페이지 파일은 import 할 수 없고, 앱 진입점이 화면 컴포넌트를 부르지 않게
key 를 여기 둔다(`components/availability_sheet_keys.py` 와 같은 까닭).

**저장하지 않는다**(2026-10-24 사용자 결정). 조건은 모두 이 세션 칸에만 있고 시뮬레이션·설비 DB
어디에도 쓰지 않는다. 세션 키는 모두 `constraint_sim_`
접두다(`tests/test_session_key_collisions.py`).

- **위젯 칸**(`persist_state="session"`) — 공정·제약 제품·제약 시작·제약 끝 상자, 「개조
  필요」·「신규 설비는 개조 없이」·「소요 비중대로 나눴을 때 함께 보기」 토글, 목록에 없는 보유 제약
  설비 숫자 칸(환산 대수 정수 — 미리 정할 버튼 값이 뜻이 없는 사실 값이라 D10 버튼을 두지 않는다)과
  신규 설비 기준일 날짜 칸(2026-10-26 사용자 결정). 위젯 앞에서 칸이 없거나 틀린 꼴일 때만 심는다
  (`seed_owned_units`·`seed_new_since`·`seed_toggle`).
- **보유 「호기 고르기」**(2026-11-01 사용자 결정 B3) — 정본은 위젯이 아닌 칸 하나에 공정마다 고른
  설비키 목록(`CONSTRAINT_HELD_KEY` — `{공정: [설비키, …]}`)이고 multiselect 칸
  (`CONSTRAINT_HELD_INPUT_KEY`)은 위젯 앞에서 매 회차 그 공정 목록을 다시 적는다(`settle_held_units`
  — 선택지 글자가 바뀌어도 브라우저가 새 글자를 받게, `prune_list_selection` 과 같은 까닭). 공정을
  바꿔도 공정마다의 고름이 남는다. 지금 선택지(세션 설비 시나리오의 그 공정 호기)에 없는 호기는
  목록에서 빼고 한 줄 알림을 남긴다(B3-2 — `CONSTRAINT_HELD_DROPPED_KEY`, 같은 공정 · 같은 선택지인
  동안 서고 고름을 바꾸면 걷는다).
- **정본 칸**(위젯 아님) — 제약 확보율(정수 %)·기준 확보율(`None` = HOME 판정 기준, 아니면 %
  실수)·개조 기간(정수 일). 버튼과 직접 입력 칸 둘이 한 정본을 나눠
  쓴다(`components/preset_number_field.py`).
- **고른 달**(위젯 아님)과 사용자가 눌러 고른 적이 있는가 표지, 두 그림의 칸 누름 세대(한 칸 — 어느
  그림을 눌러도 둘 다 새 요소가 된다).
- **주소 인자 막이**(위젯 아님) — 마지막으로 적용한 `?process=` 값(`CONSTRAINT_QUERY_SEEN_KEY`).
- **잠긴 상세에서 온 방문**(위젯 아님) — 그 인자로 HOME 칸 공정 Capa 상세(설비 공식 고정)에서
  넘어온 (공정, 페이지 방문 차례)(`CONSTRAINT_LOCKED_ARRIVAL_KEY`).

제약 시작·끝 상자는 정수 달 선택지라 `page_bootstrap.prune_choice`(글자 선택지 전용)를 쓰지 않고
`settle_period` 가 위젯 앞에서 매 회차 잡는다 — 사용자가 상자를 고치기 전에는 기본값(그 제품의 첫
소요 달 ~ 보이는 마지막 달)을 따라가고, 고친 뒤에는 그 값이 보이는 달 밖일 때만 가장 가까운 보이는
달을 적는다. 바뀐 칸만 적는다(pop 하지 않는다 — AGENTS 9장). 엇갈림은 승인
초안(`onStart`·`onEnd`)대로 `on_change` 콜백(`follow_period_start`·`follow_period_end`)이 다른 상자
칸을 맞추고 「고침」 표지(`CONSTRAINT_PERIOD_EDITED_KEY`)를 세운다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Final, NamedTuple

import streamlit as st

from capa_simulation.design.theme import THEME_QUERY_PARAM

__all__ = [
    "CONSTRAINT_ABSENT_KEY",
    "CONSTRAINT_CHART_KEY",
    "CONSTRAINT_FIGURE_MEMO_KEY",
    "CONSTRAINT_GENERAL_INPUT_KEY",
    "CONSTRAINT_GENERAL_KEY",
    "CONSTRAINT_GENERAL_PILLS_KEY",
    "CONSTRAINT_HELD_DROPPED_KEY",
    "CONSTRAINT_HELD_INPUT_KEY",
    "CONSTRAINT_HELD_KEY",
    "CONSTRAINT_LOCKED_ARRIVAL_KEY",
    "CONSTRAINT_MODIFY_KEY",
    "CONSTRAINT_MOD_DAYS_INPUT_KEY",
    "CONSTRAINT_MOD_DAYS_KEY",
    "CONSTRAINT_MOD_DAYS_PILLS_KEY",
    "CONSTRAINT_MONTH_KEY",
    "CONSTRAINT_MONTH_PICKED_KEY",
    "CONSTRAINT_NEW_SINCE_KEY",
    "CONSTRAINT_NEW_UNITS_KEY",
    "CONSTRAINT_OWNED_KEY",
    "CONSTRAINT_PERIOD_EDITED_KEY",
    "CONSTRAINT_PERIOD_END_KEY",
    "CONSTRAINT_PERIOD_START_KEY",
    "CONSTRAINT_PROCESS_KEY",
    "CONSTRAINT_PRODUCT_KEY",
    "CONSTRAINT_PRODUCT_LIMIT",
    "CONSTRAINT_PROPORTIONAL_KEY",
    "CONSTRAINT_QUERY_SEEN_KEY",
    "CONSTRAINT_SELECT_GENERATION_KEY",
    "CONSTRAINT_SHEET_KEY",
    "CONSTRAINT_TARGET_INPUT_KEY",
    "CONSTRAINT_TARGET_KEY",
    "CONSTRAINT_TARGET_PILLS_KEY",
    "CONSTRAINT_VIEW_FRAGMENT_KEY",
    "DEFAULT_MODIFY",
    "DEFAULT_MOD_DAYS",
    "DEFAULT_NEW_UNITS",
    "DEFAULT_OWNED_UNITS",
    "DEFAULT_PROPORTIONAL",
    "DEFAULT_TARGET_PERCENT",
    "GENERAL_PRESETS",
    "MOD_DAY_PRESETS",
    "PROCESS_PARAM",
    "TARGET_PRESETS",
    "HeldSettle",
    "SettledPeriod",
    "constraint_query_params",
    "follow_held_units",
    "follow_period_end",
    "follow_period_start",
    "seed_new_since",
    "seed_owned_units",
    "seed_toggle",
    "settle_held_units",
    "settle_period",
    "take_constraint_process_request",
]

# ------------------------------------------------------------------ 위젯 칸
CONSTRAINT_PROCESS_KEY: Final = "constraint_sim_process"
CONSTRAINT_PRODUCT_KEY: Final = "constraint_sim_product"
CONSTRAINT_PERIOD_START_KEY: Final = "constraint_sim_period_start"
CONSTRAINT_PERIOD_END_KEY: Final = "constraint_sim_period_end"
# 사용자가 제약 시작·끝 상자를 고친 적이 있는가(위젯 아님 — 두 상자의 `on_change` 콜백이 세운다).
# 고치기 전에는 기간이 기본값(D8 — 그 제품의 첫 소요 달 ~ 보이는 마지막 달)을 따라가 제품·공정을
# 바꾸면 그 제품의 첫 소요 달로 다시 선다(`settle_period`).
CONSTRAINT_PERIOD_EDITED_KEY: Final = "constraint_sim_period_edited"
CONSTRAINT_MODIFY_KEY: Final = "constraint_sim_modify"
# 개조 묶음의 2판 옵션(개조 끔이면 잠긴다) — 보유 제약 설비(숫자 칸)·신규 설비는 개조 없이(토글)·그
# 기준일(날짜 칸).
CONSTRAINT_OWNED_KEY: Final = "constraint_sim_owned_units"
CONSTRAINT_NEW_UNITS_KEY: Final = "constraint_sim_new_units"
CONSTRAINT_NEW_SINCE_KEY: Final = "constraint_sim_new_since"
# 보유 「호기 고르기」 — 정본(위젯 아님, `{공정: [설비키, …]}`)과 multiselect 칸, 빠진 호기
# 알림(위젯 아님 — (공정, 그 회차 선택지, 뺀 설비키)).
CONSTRAINT_HELD_KEY: Final = "constraint_sim_held_units"
CONSTRAINT_HELD_INPUT_KEY: Final = "constraint_sim_held_units_input"
CONSTRAINT_HELD_DROPPED_KEY: Final = "constraint_sim_held_dropped"
# 본문 보기 전환(프래그먼트 안) — 하위 보기 전환은 본문이다(AGENTS 9장).
CONSTRAINT_PROPORTIONAL_KEY: Final = "constraint_sim_proportional"

# ------------------------------------------------------------------ 정본 칸(위젯 아님)과 그 위젯 둘
CONSTRAINT_TARGET_KEY: Final = "constraint_sim_target"
CONSTRAINT_TARGET_PILLS_KEY: Final = "constraint_sim_target_pills"
CONSTRAINT_TARGET_INPUT_KEY: Final = "constraint_sim_target_input"
# `None` 이면 HOME → Preference 공용 판정 기준(기본 + 월별 예외)을 달마다 쓴다.
CONSTRAINT_GENERAL_KEY: Final = "constraint_sim_general"
CONSTRAINT_GENERAL_PILLS_KEY: Final = "constraint_sim_general_pills"
CONSTRAINT_GENERAL_INPUT_KEY: Final = "constraint_sim_general_input"
CONSTRAINT_MOD_DAYS_KEY: Final = "constraint_sim_mod_days"
CONSTRAINT_MOD_DAYS_PILLS_KEY: Final = "constraint_sim_mod_days_pills"
CONSTRAINT_MOD_DAYS_INPUT_KEY: Final = "constraint_sim_mod_days_input"

# ------------------------------------------------------------------ 본문
# 고른 달(`YYYYMM`). 그래프 칸·계산표 칸 누름 콜백이 적고, 마지막 누름이 이긴다.
CONSTRAINT_MONTH_KEY: Final = "constraint_sim_month"
# 사용자가 달 칸을 눌러 고른 적이 있는가(위젯 아님). 누르기 전에는 고른 달이 기본 달(영향 시작 →
# 기간 시작 → 첫 달)을 따라가 조건(공정·제품·기간·확보율)이 바뀌면 그 조건의 기본 달로 다시 선다 —
# 기간을 옮겨도 기간 밖 달 계산 카드가 남지 않게(2026-10-25 E2E). 누른 뒤에는 그 달이 보이는 동안
# 그대로다.
CONSTRAINT_MONTH_PICKED_KEY: Final = "constraint_sim_month_picked"
# 칸 선택을 켠 그림 둘 — `app.py` 의 `CELL_SELECT_CHART_KEYS` 에 든다(터치 스크롤 막이). 계산표는
# 가로로 스크롤되는 **월 Figure** 의 key 다(라벨 Figure 는 `staticPlot`).
CONSTRAINT_CHART_KEY: Final = "constraint_sim_rate_chart"
CONSTRAINT_SHEET_KEY: Final = "constraint_sim_sheet_chart"
# 두 그림이 한 칸을 나눠 쓰는 칸 누름 세대 — 누를 때마다 올라 두 그림이 함께 새 요소가 되고
# 브라우저에 남은 옛 선택이 다음 누름을 삼키지 않는다(AGENTS 9장 「칸 선택 Plotly」).
CONSTRAINT_SELECT_GENERATION_KEY: Final = "constraint_sim_select_generation"
# 그림 memo(세션 칸 LRU — Streamlit 캐시가 아니다).
CONSTRAINT_FIGURE_MEMO_KEY: Final = "constraint_sim_figure_memo"
CONSTRAINT_VIEW_FRAGMENT_KEY: Final = "constraint_sim_view"
# 설비 일정이 서지 않는 까닭 카드(한 회차에 하나) — 사내 화면
# 확인(`scripts/check_deploy_screens.py`)이 고른다.
CONSTRAINT_ABSENT_KEY: Final = "constraint_sim_absent"

# ------------------------------------------------------------------ 버튼 값·기본값(D8)
TARGET_PRESETS: Final = (100, 110, 115, 120, 130, 140)
# 첫 버튼은 「HOME 기준」(정본 `None`). 라벨에 HOME 값을 넣지 않는다 — 값은 카드 캡션이
# 말한다(AGENTS 9장 format_func).
GENERAL_PRESETS: Final[tuple[int | None, ...]] = (None, 100, 105, 110, 115)
MOD_DAY_PRESETS: Final = (15, 30, 45, 60, 90)
DEFAULT_TARGET_PERCENT: Final = 120
DEFAULT_MOD_DAYS: Final = 30
DEFAULT_MODIFY: Final = True
# 2판 옵션은 꺼 둔다 — 1판 결과가 조용히 바뀌지 않게(사용자 「옵션으로」). 기준일 기본값은 오늘이다.
DEFAULT_OWNED_UNITS: Final = 0
DEFAULT_NEW_UNITS: Final = False
DEFAULT_PROPORTIONAL: Final = True
# 제품별 소요 표의 행 상한 — 「그 밖」 묶음이 생기지 않게 크게 둔다(그 표는 행을 다 더하면 공정
# 소요다).
CONSTRAINT_PRODUCT_LIMIT: Final = 10_000

# ------------------------------------------------------------------ 주소 인자
# 공정 Capa 상세 머리 「이 공정 제약 시뮬레이션」 링크가 싣는 원본 공정명. 받는 쪽은 무엇보다 먼저
# 꺼내고 그 키 하나만 지운다(테마 인자는 남는다).
PROCESS_PARAM: Final = "process"
# 주소 `?process=` 를 마지막으로 적용한 값(위젯 아님). 지운 것이 브라우저에 닿기 전에 옛 주소를 실은
# 회차가 와도 사용자가 그 뒤 고른 공정을 덮지 않는다 — 공정 Capa 상세
# `PROCESS_DETAIL_QUERY_SEEN_KEY` 와 같은 막이다. 주소에 인자가 없는 회차에 비운다.
CONSTRAINT_QUERY_SEEN_KEY: Final = "constraint_sim_query_seen"
# HOME 칸으로 연 공정 Capa 상세(설비 「공식 고정」)의 머리 링크로 넘어온 방문 — (공정, 페이지 방문
# 차례)(위젯 아님). 이 화면은 늘 세션 설비 시나리오라(D6) 설비 기준이 공식에서 가정으로 말없이
# 바뀌지 않게, 그 공정을 보는 그 방문 동안 맨 위에 한 줄을 세운다(2026-10-25 E2E). 다른 공정을
# 고르거나 다른 화면에 다녀오면 걷는다.
CONSTRAINT_LOCKED_ARRIVAL_KEY: Final = "constraint_sim_locked_arrival"


def constraint_query_params(process: str, *, theme: str | None) -> dict[str, str]:
    """「이 공정 제약 시뮬레이션」 링크의 주소 인자 — 공정과(값이 있으면) 테마."""
    params = {PROCESS_PARAM: str(process)}
    if theme:
        params[THEME_QUERY_PARAM] = str(theme)
    return params


def take_constraint_process_request() -> str | None:
    """주소의 `?process=` 를 꺼내고 그 키 하나만 지운다. 페이지가 **무엇보다 먼저** 부른다.

    부트스트랩이 오류로 멈춘 회차에도 주소에 남지 않게 맨 앞에서 꺼낸다(그 회차는 넘겨받은 공정만
    잃는다). 빈 글자는 None 이다.

    한 번 적용한 값은 `CONSTRAINT_QUERY_SEEN_KEY` 에 남긴다 — 같은 값이 다시 오면(지운 것이
    브라우저에 닿기 전에 옛 주소를 실은 회차) 적용하지 않고 지우기만 한다. 인자가 걷힌 회차에 그
    칸을 비우므로 같은 링크로 다시 들어오면 다시 적용한다.
    """
    if PROCESS_PARAM not in st.query_params:
        st.session_state.pop(CONSTRAINT_QUERY_SEEN_KEY, None)
        return None
    value = str(st.query_params.get(PROCESS_PARAM, "")).strip()
    del st.query_params[PROCESS_PARAM]
    if st.session_state.get(CONSTRAINT_QUERY_SEEN_KEY) == value:
        return None
    st.session_state[CONSTRAINT_QUERY_SEEN_KEY] = value
    return value or None


def seed_toggle(key: str, default: bool) -> None:
    """토글 칸이 없을 때만 기본값을 심는다(위젯에 `value=` 를 주지 않는다 — AGENTS 9장)."""
    if not isinstance(st.session_state.get(key), bool):
        st.session_state[key] = bool(default)


def seed_owned_units(maximum: int) -> None:
    """보유 제약 설비 칸이 0~`maximum` 정수가 아니면 기본값(0)을 심는다 — 범위 밖 옛 값이 숫자 칸
    예외가 되지 않게. 같은 값은 다시 적지 않는다."""
    value = st.session_state.get(CONSTRAINT_OWNED_KEY)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        st.session_state[CONSTRAINT_OWNED_KEY] = DEFAULT_OWNED_UNITS


def seed_new_since(today: date) -> None:
    """기준일 칸이 날짜가 아니면 오늘을 심는다. 자정을 넘긴 세션은 그날 값 그대로다(이 세션만의
    가정 — 칸에 보이는 값이 곧 계산 값)."""
    value = st.session_state.get(CONSTRAINT_NEW_SINCE_KEY)
    if not isinstance(value, date) or isinstance(value, datetime):
        st.session_state[CONSTRAINT_NEW_SINCE_KEY] = today


# ------------------------------------------------------------------ 보유 「호기 고르기」


class HeldSettle(NamedTuple):
    """위젯 앞에서 잡은 그 공정의 고른 호기. `dropped` 는 지금 선택지에 없어 뺀 설비키이고 알림이
    설 동안(같은 공정 · 같은 선택지) 그대로 돌려준다."""

    picked: tuple[str, ...]
    dropped: tuple[str, ...]


def _held_map() -> dict[str, list[str]]:
    """정본 칸 — 틀린 꼴이면 빈 것으로 본다(글자 목록이 아닌 값은 버린다)."""
    saved = st.session_state.get(CONSTRAINT_HELD_KEY)
    if not isinstance(saved, dict):
        return {}
    return {
        str(process): [str(name) for name in names]
        for process, names in saved.items()
        if isinstance(names, list | tuple)
    }


def settle_held_units(process: str, choices: Sequence[str]) -> HeldSettle:
    """그 공정의 고른 호기를 위젯 앞에서 잡는다 — 지금 선택지에 없는 호기는 정본에서 빼고 알림을
    남긴 뒤(결정 B3-2), multiselect 칸에 남은 목록을 **매 회차** 적는다(고른 차례 그대로).

    정본은 다를 때만 적는다. 알림은 같은 공정 · 같은 선택지인 동안 서고, 공정이나 선택지가 다시
    바뀌면 그 회차의 뺀 것으로 바뀐다(없으면 걷힌다).
    """
    key = str(process)
    allowed = {str(name) for name in choices}
    signature = tuple(str(name) for name in choices)
    mapping = _held_map()
    saved = mapping.get(key, [])
    kept = [name for name in dict.fromkeys(saved) if name in allowed]
    dropped = tuple(name for name in dict.fromkeys(saved) if name not in allowed)
    if dropped or kept != saved:
        mapping[key] = kept
        st.session_state[CONSTRAINT_HELD_KEY] = mapping
    if dropped:
        st.session_state[CONSTRAINT_HELD_DROPPED_KEY] = (key, signature, dropped)
    notice = st.session_state.get(CONSTRAINT_HELD_DROPPED_KEY)
    shown: tuple[str, ...] = ()
    if isinstance(notice, tuple) and len(notice) == 3:
        if notice[0] == key and notice[1] == signature:
            shown = tuple(str(name) for name in notice[2])
        else:
            st.session_state.pop(CONSTRAINT_HELD_DROPPED_KEY, None)
    st.session_state[CONSTRAINT_HELD_INPUT_KEY] = list(kept)
    return HeldSettle(tuple(kept), shown)


def follow_held_units(process: str) -> None:
    """「보유 제약 호기」 multiselect 콜백 — 고른 목록을 그 공정의 정본에 옮기고 빠진 호기 알림을
    걷는다(사용자가 고름을 바꿨다)."""
    value = st.session_state.get(CONSTRAINT_HELD_INPUT_KEY)
    names = [str(name) for name in value] if isinstance(value, list | tuple) else []
    mapping = _held_map()
    mapping[str(process)] = names
    st.session_state[CONSTRAINT_HELD_KEY] = mapping
    st.session_state.pop(CONSTRAINT_HELD_DROPPED_KEY, None)


# ------------------------------------------------------------------ 제약 기간 상자 둘


class SettledPeriod(NamedTuple):
    """위젯 앞에서 잡은 제약 기간. `moved` 는 보이는 달 밖이던 값을 옮겨 적은 회차다(조회기간이
    좁아짐)."""

    start: int
    end: int
    moved: bool


def _nearest(month: int, months: Sequence[int]) -> int:
    """보이는 달 가운데 `month` 에 가장 가까운 달(같으면 이른 달)."""
    return min(
        months, key=lambda candidate: (abs(_ordinal(candidate) - _ordinal(month)), candidate)
    )


def _ordinal(month: int) -> int:
    year, number = divmod(int(month), 100)
    return year * 12 + number


def _held_month(key: str) -> int | None:
    value = st.session_state.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def settle_period(months: Sequence[int], *, default_start: int) -> SettledPeriod:
    """제약 시작·끝 상자 칸을 위젯 앞에서 잡는다. **다를 때만** 적는다(같은 값을 다시 적지 않는다).

    - 사용자가 상자를 고치기 전(`CONSTRAINT_PERIOD_EDITED_KEY` 없음)에는 늘 기본값(D8) — 시작은
      `default_start`(그 제품의 첫 소요 달), 끝은 보이는 마지막 달. 제품·공정을 바꾸면 그 제품의
      첫 소요 달로 다시 선다 — 앞 제품의 기간이 남아 「소요가 없다」 안내만 보이지 않게(2026-10-25
      E2E).
    - 고친 뒤에는 그 값 그대로이고, 보이는 달 밖이면 가장 가까운 보이는 달로 적는다.
    - 어느 쪽이든 앞 값이 보이는 달 밖이라 옮겼으면 `moved` 다(조회기간이 좁아짐 — 화면이 알린다).
    - 시작이 끝보다 뒤면(조회기간을 옮긴 뒤 가까운 달끼리 엇갈림) 끝을 시작으로 적는다.
    `months` 가 비면 `ValueError` 다(부르는 쪽이 먼저 멈춘다).
    """
    visible = [int(month) for month in months]
    if not visible:
        raise ValueError("보이는 달이 없어 제약 기간을 정할 수 없습니다.")
    allowed = set(visible)
    seed_start = int(default_start) if int(default_start) in allowed else visible[0]
    follows_default = st.session_state.get(CONSTRAINT_PERIOD_EDITED_KEY) is not True
    moved = False

    def settle(key: str, fallback: int) -> int:
        nonlocal moved
        held = _held_month(key)
        if held is not None and held not in allowed:
            moved = True
        if held is None or follows_default:
            value = fallback
        elif held in allowed:
            value = held
        else:
            value = _nearest(held, visible)
        if st.session_state.get(key) != value:
            st.session_state[key] = value
        return value

    start = settle(CONSTRAINT_PERIOD_START_KEY, seed_start)
    end = settle(CONSTRAINT_PERIOD_END_KEY, visible[-1])
    if start > end:
        end = start
        st.session_state[CONSTRAINT_PERIOD_END_KEY] = end
    return SettledPeriod(start, end, moved)


def follow_period_start() -> None:
    """「제약 시작」 상자 콜백 — 시작을 끝 뒤로 고르면 끝이 시작으로 따라온다(초안 `onStart`).
    사용자가 기간을 고쳤다는 표지를 세운다(그 뒤로 기간은 기본값을 따라가지 않는다)."""
    st.session_state[CONSTRAINT_PERIOD_EDITED_KEY] = True
    start = _held_month(CONSTRAINT_PERIOD_START_KEY)
    end = _held_month(CONSTRAINT_PERIOD_END_KEY)
    if start is not None and end is not None and start > end:
        st.session_state[CONSTRAINT_PERIOD_END_KEY] = start


def follow_period_end() -> None:
    """「제약 끝」 상자 콜백 — 끝을 시작 앞으로 고르면 시작이 끝으로 따라온다(초안 `onEnd`).
    사용자가 기간을 고쳤다는 표지를 세운다."""
    st.session_state[CONSTRAINT_PERIOD_EDITED_KEY] = True
    start = _held_month(CONSTRAINT_PERIOD_START_KEY)
    end = _held_month(CONSTRAINT_PERIOD_END_KEY)
    if start is not None and end is not None and end < start:
        st.session_state[CONSTRAINT_PERIOD_START_KEY] = end
