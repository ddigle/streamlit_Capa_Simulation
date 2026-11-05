# Purpose: 날짜 칸을 조회기간과 같은 값 칸 + 기간 판(일 격자 · 빠른 선택 · 「적용」)으로 그린다.

"""날짜 칸과 기간 판(2026-11-05 사용자 검수 static-35 — 「날짜 지정 양식을 사이드바 조회기간 칸을
누르면 뜨는 기간판으로 공통 적용」).

앱의 날짜 고르기는 모두 이 부품이다 — 값 칸 하나를 누르면 판이 뜨고, 판에서 고른 값은 「적용」
때만 서버로 간다. 시작 · 끝을 이어 고르는 두 칸은 범위 칸 하나(`date_range_field` ·
`optional_date_range_field`)로, 날짜 하나만 고르는 칸은 한 날 칸(`date_field` ·
`optional_date_field`)으로 쓴다. 생김과 조작은 조회기간 판(`month_range_picker`)과 같다 — 두 번
눌러 범위, 빠른 선택, 키보드, 「적용」, 지금 값 그대로면 잠김.

**값의 정본은 위젯이 아니라 세션 칸이다.** `start_key` · `end_key` · `key` 칸에 `date`(비운 칸은
`None`)가 들어 있고, 「적용」 콜백이 그 칸을 고쳐 회차 맨 앞부터 새 값이 보인다. 그래서 리비전
프리셋 · 등록 폼처럼 칸을 직접 쓰는 쪽은 예전 위젯 칸과 같은 이름 · 같은 값 꼴을 그대로 쓴다.
범위 밖 · 거꾸로인 칸은 그리기 전에 맞춰 되적는다.

**판은 브라우저 안에서 열리고 닫힌다**(HTML `<dialog>` — 맨 위 층이라 사이드바 · 펼침에 잘리지
않는다). 여닫기와 고르기는 회차가 없다(설계 규칙 UI-PRF-01 · UI-PRF-04). 트리거가 콜백으로
오므로 `st.form` 안에는 두지 않는다 — 폼 안 트리거는 제출 때까지 서버에 오지 않는다(칸은 폼 밖에
둔다).

화면 조각은 `date_panel_assets/` 의 세 파일이다. 판정 구획(`// <date-panel-core>`)은 DOM 을 모르는
순수 함수라 node 로 떼어 시험한다(`tests/test_date_panel.py`). 해 넘김 · 빠른 선택 · 바닥 줄 서식은
조회기간 판의 서식을 이름만 옮겨 쓴다(`DATE_PANEL_CSS`) — 한쪽만 고쳐 생김이 갈라지지 않게.

**다른 컴포넌트 안의 칸.** 값이 브라우저에 머무는 Space 편집기 「+ 호기 추가」 도 같은 판이다 — 조각
(`DATE_PANEL_HTML`) · 서식(`DATE_PANEL_CSS`) · 세우는 함수(`DATE_PANEL_MOUNT_JS`)를 그 컴포넌트에
싣고 「적용」 을 제 상태로 받는다. 설비 마스터 호기 상세 · 새 호기 칸의 일정은 표 칸과 한 몸인 글
칸이라(치거나 붙여넣는다) 이 부품 밖이다(UI-INP-03 예외).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Final, Literal

import streamlit as st

from capa_simulation.components.month_range_picker import MONTH_RANGE_CSS

_ASSETS = Path(__file__).with_name("date_panel_assets")
DATE_PANEL_HTML: Final = (_ASSETS / "date_panel.html").read_text(encoding="utf-8")
DATE_PANEL_OWN_CSS: Final = (_ASSETS / "date_panel.css").read_text(encoding="utf-8")
DATE_PANEL_JS: Final = (_ASSETS / "date_panel.js").read_text(encoding="utf-8")
DATE_PANEL_CSS: Final = MONTH_RANGE_CSS.replace("capa-month-", "capa-date-") + DATE_PANEL_OWN_CSS
# 다른 컴포넌트 JS 앞에 붙여 같은 판을 세우는 머리 — 판의 이름들을 가두고 `mountDatePanel` 하나만
# 바깥에 둔다(Space 편집기 호기 추가 — 값이 브라우저에 머무는 칸, 설계 규칙 UI-INP-03).
DATE_PANEL_MOUNT_JS: Final = (
    "const mountDatePanel = (() => {\n"
    + DATE_PANEL_JS.split("export default", 1)[0]
    + "return mountDatePanel\n})()\n"
)

# 비운 칸의 값 칸 글자.
EMPTY_TEXT: Final = "비어 있음"
# 끝을 주지 않은 칸의 고를 수 있는 범위 — 오늘 앞뒤 십 년. 지금 값이 그 밖이면 값까지 넓힌다 — 칸이
# 값을 말없이 바꾸지 않게.
_FREE_YEARS: Final = 10

# 팝업 포커스 · 맨 위 층 판 때문에 그림자 DOM 에 가두지 않는다(`month_range_picker` 와 같은 까닭).
_DATE_PANEL = st.components.v2.component(
    "capa_date_panel",
    html=DATE_PANEL_HTML,
    css=DATE_PANEL_CSS,
    js=DATE_PANEL_JS,
    isolate_styles=False,
)

Width = int | Literal["stretch"]


def panel_key(key: str) -> str:
    """값 칸 키(범위는 시작 칸 키)에 딸린 컴포넌트 위젯 키. Components v2 키는 `__` 를 못 쓴다."""
    return f"{key}_date_panel"


def _as_day(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _parse_day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _shift_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _limits(
    values: tuple[date | None, ...], min_date: date | None, max_date: date | None, today: date
) -> tuple[date, date]:
    """고를 수 있는 범위. 준 끝은 그대로, 주지 않은 끝은 오늘 앞뒤 십 년(값이 그 밖이면 값까지)."""
    held = [value for value in values if value is not None]
    if min_date is not None:
        low = min_date
    else:
        low = min([_shift_years(today, -_FREE_YEARS), *held])
    if max_date is not None:
        high = max_date
    else:
        high = max([_shift_years(today, _FREE_YEARS), *held])
    return low, max(low, high)


def _clamped(day: date | None, low: date, high: date) -> date | None:
    return None if day is None else min(max(day, low), high)


def accepted_range(
    payload: object, low: date, high: date, *, clearable: bool
) -> tuple[date | None, date | None] | None:
    """「적용」 트리거를 다시 본다 — 범위 밖 · 거꾸로 · 깨진 값은 받지 않는다(JS 가 막아도)."""
    if not isinstance(payload, Mapping):
        return None
    start_text, end_text = payload.get("start"), payload.get("end")
    if start_text is None and end_text is None:
        return (None, None) if clearable else None
    start, end = _parse_day(start_text), _parse_day(end_text)
    if start is None or end is None or start > end or start < low or end > high:
        return None
    return start, end


def _trigger_payload(widget_key: str) -> object:
    state = st.session_state.get(widget_key)
    return state.get("apply") if isinstance(state, Mapping) else getattr(state, "apply", None)


def _on_apply_range(
    widget_key: str, start_key: str, end_key: str, low: date, high: date, clearable: bool
) -> None:
    accepted = accepted_range(_trigger_payload(widget_key), low, high, clearable=clearable)
    if accepted is None:
        return
    st.session_state[start_key], st.session_state[end_key] = accepted


def _on_apply_day(widget_key: str, key: str, low: date, high: date, clearable: bool) -> None:
    accepted = accepted_range(_trigger_payload(widget_key), low, high, clearable=clearable)
    if accepted is None:
        return
    st.session_state[key] = accepted[0]


def _settle(key: str, value: date | None) -> None:
    """맞춘 값을 칸에 되적는다. 같으면 쓰지 않는다."""
    if st.session_state.get(key) != value or key not in st.session_state:
        st.session_state[key] = value


def _draw(
    *,
    mode: Literal["range", "single"],
    label: str,
    widget_key: str,
    start: date | None,
    end: date | None,
    low: date,
    high: date,
    bounded: bool,
    clearable: bool,
    disabled: bool,
    help_text: str | None,
    empty_text: str,
    on_apply: partial[None],
    width: Width,
) -> None:
    _DATE_PANEL(
        key=widget_key,
        data={
            "mode": mode,
            "label": label,
            "help": help_text or "",
            "emptyText": empty_text,
            "start": None if start is None else start.isoformat(),
            "end": None if end is None else end.isoformat(),
            "minDay": low.isoformat(),
            "maxDay": high.isoformat(),
            "today": date.today().isoformat(),
            "clearable": clearable,
            "bounded": bounded,
            "disabled": disabled,
        },
        on_apply_change=on_apply,
        width=width,
    )


def _range_field(
    label: str,
    *,
    start_key: str,
    end_key: str,
    default: tuple[date | None, date | None],
    min_date: date | None,
    max_date: date | None,
    clearable: bool,
    disabled: bool,
    help_text: str | None,
    empty_text: str,
    width: Width,
) -> tuple[date | None, date | None]:
    raw_start = _as_day(st.session_state.get(start_key))
    raw_end = _as_day(st.session_state.get(end_key))
    if not clearable and (raw_start is None or raw_end is None):
        raw_start = raw_start if raw_start is not None else default[0]
        raw_end = raw_end if raw_end is not None else default[1]
    low, high = _limits((raw_start, raw_end), min_date, max_date, date.today())
    start, end = _clamped(raw_start, low, high), _clamped(raw_end, low, high)
    if start is not None and end is not None and start > end:
        end = start
    _settle(start_key, start)
    _settle(end_key, end)
    widget_key = panel_key(start_key)
    _draw(
        mode="range",
        label=label,
        widget_key=widget_key,
        start=start,
        end=end,
        low=low,
        high=high,
        bounded=min_date is not None and max_date is not None,
        clearable=clearable,
        disabled=disabled,
        help_text=help_text,
        empty_text=empty_text,
        on_apply=partial(_on_apply_range, widget_key, start_key, end_key, low, high, clearable),
        width=width,
    )
    return start, end


def _day_field(
    label: str,
    *,
    key: str,
    default: date | None,
    min_date: date | None,
    max_date: date | None,
    clearable: bool,
    disabled: bool,
    help_text: str | None,
    empty_text: str,
    width: Width,
) -> date | None:
    raw = _as_day(st.session_state.get(key))
    if raw is None and not clearable:
        raw = default
    low, high = _limits((raw,), min_date, max_date, date.today())
    value = _clamped(raw, low, high)
    _settle(key, value)
    widget_key = panel_key(key)
    _draw(
        mode="single",
        label=label,
        widget_key=widget_key,
        start=value,
        end=value,
        low=low,
        high=high,
        bounded=False,
        clearable=clearable,
        disabled=disabled,
        help_text=help_text,
        empty_text=empty_text,
        on_apply=partial(_on_apply_day, widget_key, key, low, high, clearable),
        width=width,
    )
    return value


def date_range_field(
    label: str,
    *,
    start_key: str,
    end_key: str,
    default: tuple[date, date],
    min_date: date | None = None,
    max_date: date | None = None,
    disabled: bool = False,
    help: str | None = None,
    width: Width = "stretch",
) -> tuple[date, date]:
    """시작 · 끝을 함께 고르는 칸 하나. 지금 값(비었으면 `default`)을 범위 안으로 맞춰 돌려준다."""
    start, end = _range_field(
        label,
        start_key=start_key,
        end_key=end_key,
        default=default,
        min_date=min_date,
        max_date=max_date,
        clearable=False,
        disabled=disabled,
        help_text=help,
        empty_text=EMPTY_TEXT,
        width=width,
    )
    assert start is not None and end is not None
    return start, end


def optional_date_range_field(
    label: str,
    *,
    start_key: str,
    end_key: str,
    min_date: date | None = None,
    max_date: date | None = None,
    help: str | None = None,
    empty_text: str = EMPTY_TEXT,
    width: Width = "stretch",
) -> tuple[date | None, date | None]:
    """비울 수 있는 범위 칸 — 판에 「비움」 이 있고 두 값이 함께 비거나 함께 찬다."""
    return _range_field(
        label,
        start_key=start_key,
        end_key=end_key,
        default=(None, None),
        min_date=min_date,
        max_date=max_date,
        clearable=True,
        disabled=False,
        help_text=help,
        empty_text=empty_text,
        width=width,
    )


def date_field(
    label: str,
    *,
    key: str,
    default: date,
    min_date: date | None = None,
    max_date: date | None = None,
    disabled: bool = False,
    help: str | None = None,
    width: Width = "stretch",
) -> date:
    """날짜 하나를 고르는 칸."""
    value = _day_field(
        label,
        key=key,
        default=default,
        min_date=min_date,
        max_date=max_date,
        clearable=False,
        disabled=disabled,
        help_text=help,
        empty_text=EMPTY_TEXT,
        width=width,
    )
    assert value is not None
    return value


def optional_date_field(
    label: str,
    *,
    key: str,
    min_date: date | None = None,
    max_date: date | None = None,
    help: str | None = None,
    empty_text: str = EMPTY_TEXT,
    width: Width = "stretch",
) -> date | None:
    """비울 수 있는 날짜 칸 — 판에 「비움」 이 있다."""
    return _day_field(
        label,
        key=key,
        default=None,
        min_date=min_date,
        max_date=max_date,
        clearable=True,
        disabled=False,
        help_text=help,
        empty_text=empty_text,
        width=width,
    )
