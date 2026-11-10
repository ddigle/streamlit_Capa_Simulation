# Purpose: 공용 공정 값 칸 · 고르는 팝업과 머리 칩 · 탭 표지의 글 · data 를 한 꼴로 만든다.

"""공용 공정 칸의 화면 조각(2026-11-08 사용자 답 P1 · P2 — 값과 규칙은 `shared_process.py`).

- **값 칸** — 사이드바 조회 조건 패널의 페이지 칸(`page_condition_slot(0)`)에 이름 줄 「공정」 + 값
  칸 한 벌(`condition_field`)로 선다. 칸 높이는 고른 수와 상관없이 같다(칩 칸은 고른 수에 따라 60 →
  160px 로 흔들려 사이드바를 밀었다 — 2026-11-07 조사). 고른 값 글은 한 줄 「Wafer Saw 외 2개」
  꼴이다(`first_and_rest` — 2026-11-09 사용자 검수 g03-2): 하나면 그 이름, 둘부터 첫 공정 +
  나머지 수, 넘치면 칸 폭에서 말줄임이고 둘 이상이면 풍선이 전체 목록이다. 첫 공정은 표시순서상 첫
  공정이다 — 판이 고른 값을 선택지 차례로 다시 늘어놓아 고른 차례가 남지 않는다. 공용 값이 이
  화면에 걸리면 값 칸 테두리를 강조하고(`ACCENT_SUFFIX`), 다른 화면에서 온 값이면 이름 줄
  오른쪽에 「HOME 에서」 꼴 출처를 단다. 이 화면에 없는 공정은 값 칸 아이콘 `filter_alt_off` 로만
  알리고 이름은 머리 띠 칩 「n개 이 화면 없음」 · 그 판 · 화면 탭 표지가 말한다(이름 줄에는 배지를
  두지 않는다 — 2026-11-09 보드 P1-6).
- **팝업** — 값 칸을 누르면 `app.py` 의 조건 팝업 호스트 프래그먼트만 다시 돈다(열기로 앱 전체가
  돌지 않는다 — 설계 규칙 UI-PRF-01, 시나리오 · 조회기간 칸과 같은 `rerun_fragment_if_alone`). 팝업
  본문은 Components v2 판 하나(`process_field_assets/`)라 타일을 누르는 동안 서버가 돌지 않고, 누른
  뒤에도 초점이 그 타일에 남아 키보드만으로 「적용」 까지 닿는다(UI-INP-03). 팝업이 쓰는 선택지는
  페이지가 값 칸을 그린 전체 회차에 세션에 적어 둔다(호스트만 도는 회차는 페이지를 돌리지 않는다).
  하나 고름 화면의 팝업에서 고른 공정은 공용 값을 그 하나로 바꾼다(`shared_process.pick_single` —
  2026-11-09 보드 C2 (가)).
- **머리 띠 칩 · 화면 탭 표지**(2026-11-09 보드 C1 (라) — 본문 위에는 칩을 두지 않는다). 공용 값이
  있으면 알림 칸(`components/alert_center.py`)이 머리 툴바 맨 왼쪽에 「공정」 칩을
  세우고(`header_chip`), 화면 탭 줄(`components/page_tabs.py`)이 따라가는 화면 탭 이름 곁에 깔때기
  표지를 단다(`tab_mark`). 칩 · 판의 글자는 보낸 화면의 표시명이고, 원본 이름으로 그리는
  화면(Space — `shared_process.ORIGINAL_NAME_SCREENS`)에서는 원본이다. 둘 다 페이지보다 먼저
  그리므로 세션의 기록(`shared_process.screen_mark` — 그 화면이 마지막으로 그린 선택지)으로
  짐작하고, 값 칸을 그린 회차에는 그 회차의
  표지(`MARKER_ATTRIBUTE` — 스타일만 든 `st.html` 의 JSON)를 남겨 알림 칸 JS 가 회차 끝에
  바로잡는다. 표지는 값 칸과 같은 칸(간격 없는 블록)에 서서 사이드바에 틈을 만들지 않는다.

한 회차에 값 칸은 하나다 — 같은 전체 회차에 두 번 부르면 둘째부터는 그리지 않고 거를 값만 돌려준다.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation import alerts, shared_process
from capa_simulation.components.condition_field import condition_field
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.page_bootstrap import PAGE_DIALOG_SUFFIX, forget_page_dialogs
from capa_simulation.services.korean_particle import topic_particle
from capa_simulation.sidebar_status import (
    APP_RUN_STATE_KEY,
    CONDITION_DIALOG_FRAGMENT_KEY,
    keeps_app_run_open,
    page_condition_slot,
    rerun_fragment_if_alone,
)

FIELD_LABEL = "공정"
FIELD_ICON = ":material/filter_alt:"
# 공용 값이 이 화면에 없어 전체를 보이는 동안의 값 칸 아이콘.
MISSING_ICON = ":material/filter_alt_off:"
FIELD_KEY = "sidebar_process_field"
FIELD_SLUG = "process"
DIALOG_KEY = f"sidebar_process{PAGE_DIALOG_SUFFIX}"
PICKER_KEY = "sidebar_process_picker"
# 팝업이 읽는 이번 화면의 선택지(마지막으로 값 칸을 그린 전체 회차의 것).
CONTEXT_KEY = "sidebar_process_context"
# 이번 전체 회차에 값 칸을 이미 그렸는가 — 실행 표지(`APP_RUN_STATE_KEY` 의 `run`)를 적어 둔다.
DRAWN_KEY = "sidebar_process_drawn"
MULTI = shared_process.MULTI
SINGLE = shared_process.SINGLE
# 고를 공정이 없는 값 칸 · 팝업의 값(빈 결과 — 설계 규칙 UI-TXT-04).
NO_PROCESS_VALUE = "고를 공정 없음"
# 공통 진입(계산)이 멈춘 회차의 잠긴 값 칸 글 — HOME 공정 필터 · 주요공정 히트맵 줄과 같은 글.
STOPPED_VALUE = "계산 멈춤"
# 값 칸을 그린 회차의 표지 속성 — 알림 칸 JS 가 회차 끝에 이 속성의 JSON 으로 머리 칩 · 지금 탭
# 표지를 바로잡는다(`alert_center.js` 의 `readProcessMark`).
MARKER_ATTRIBUTE = "data-capa-process"
# 둘 이상 고른 값의 한 줄 글(`first_and_rest`) — 머리 칩 JS 도 같은 글로 이 화면 차례의 첫 이름을
# 적는다.
REST_TEXT = "{first} 외 {n}개"
# 화면 탭 표지 · 머리 칩 풍선의 글.
FROM_TEXT = "{origin} 에서"
TAB_TITLE = "공정 {names}"
ABSENT_LINE = "{names} {particle} 이 화면에 없음"

_ASSETS = Path(__file__).with_name("process_field_assets")
PROCESS_FIELD_HTML = (_ASSETS / "process_field.html").read_text(encoding="utf-8")
PROCESS_FIELD_CSS = (_ASSETS / "process_field.css").read_text(encoding="utf-8")
PROCESS_FIELD_JS = (_ASSETS / "process_field.js").read_text(encoding="utf-8")

# **그림자 DOM 으로 가두지 않는다**(`isolate_styles=False`) — 팝업(`st.dialog`)은 포커스를 팝업
# 안에서 돌리는데 그 순서는 그림자 DOM 안을 보지 못한다(조회기간 달 고르기와 같다 —
# `month_range_picker`). 서식은 `capa-proc-*` 클래스로만 건다.
_PROCESS_PICKER = st.components.v2.component(
    "capa_process_picker",
    html=PROCESS_FIELD_HTML,
    css=PROCESS_FIELD_CSS,
    js=PROCESS_FIELD_JS,
    isolate_styles=False,
)


@dataclass(frozen=True)
class PickerResult:
    """팝업 판의 트리거 하나 — `clear`(「전체」) 이거나 고른 공정(`values`, 원본 이름)."""

    values: tuple[str, ...] = ()
    clear: bool = False


@dataclass(frozen=True)
class _PickerContext:
    mode: str
    screen: str
    page: str | None
    options: tuple[str, ...]
    texts: tuple[str, ...]
    selected: tuple[str, ...]
    key: str | None


def _page_hash() -> str | None:
    ctx = get_script_run_ctx(suppress_warning=True)
    return None if ctx is None else ctx.page_script_hash


def _text_func(options: Sequence[str], labels: ProcessLabels | None) -> Callable[[object], str]:
    """보이는 글자 — 표시명이 있으면 이 화면 선택지 안에서 겹치지 않게 가른 글자, 없으면 원본."""
    if labels:
        return labels.unique_format_func(options)
    return str


def _shown_names(values: Sequence[str], text: Callable[[object], str]) -> str:
    return " · ".join(literal_markdown(text(value)) for value in values)


def first_and_rest(names: Sequence[str]) -> str:
    """고른 공정 한 줄 글 — 하나면 그 이름, 둘부터 「<첫 이름> 외 n개」(2026-11-09 사용자 검수 g03-2
    「가장 먼저 선택된 공정 1개만 이름 보여주는식으로 (Wafer Saw 외 n개 선택)」 — 칸 이름이 「공정」
    이라 「선택」 은 붙이지 않는다). `names` 는 보이는 글자 그대로(마크다운 막음은 부르는 쪽)이고 그
    차례의 첫 이름이 앞에 선다. 공용 값 칸과 필요 단축 일정 카드의 공정 칸이 같이 쓴다(설계 규칙
    UI-CON-04). 빈 목록은 빈 글자다."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return REST_TEXT.format(first=names[0], n=len(names) - 1)


def filter_value(
    hits: Sequence[str],
    options: Sequence[str],
    text: Callable[[object], str],
    *,
    empty: str | None = None,
) -> str:
    """여러 개 고름 값 칸 글자 — 걸린 것이 없으면 「전체 N공정」(또는 `empty`), 걸렸으면 한 줄
    「Mold 외 2개」(`first_and_rest` — 첫 공정은 표시순서상 첫 공정)."""
    if not options:
        return NO_PROCESS_VALUE
    if not hits:
        return empty if empty is not None else f"전체 {len(options)}공정"
    return first_and_rest([literal_markdown(text(value)) for value in hits])


def filter_help(hits: Sequence[str], text: Callable[[object], str]) -> str | None:
    """값 칸 풍선 — 둘 이상 걸렸으면 전체 목록(한 줄 글에는 첫 공정만 보인다). 하나 · 전체는
    None 이다(말줄임된 한 줄 단추는 Streamlit 이 풍선으로 글을 다 보인다)."""
    return _shown_names(hits, text) if len(hits) >= 2 else None


def origin_status(origin: str | None) -> str | None:
    """이름 줄 오른쪽 출처 글 — 다른 화면에서 온 값이 이 화면에 걸렸을 때만(「HOME 에서」)."""
    return FROM_TEXT.format(origin=origin) if origin else None


def _first_draw_this_run() -> bool:
    """이번 전체 회차에 값 칸을 처음 그리는가. 실행 표지가 없으면(페이지만 띄운 시험) 늘 참이다."""
    state = st.session_state.get(APP_RUN_STATE_KEY)
    token = state.get("run") if isinstance(state, dict) else None
    if token is None:
        return True
    if st.session_state.get(DRAWN_KEY) is token:
        return False
    st.session_state[DRAWN_KEY] = token
    return True


def render_process_filter(
    options: Sequence[object],
    *,
    screen: str,
    labels: ProcessLabels | None = None,
    empty: str | None = None,
) -> list[str]:
    """여러 개 따라감 화면의 값 칸을 그리고 이 화면에 거는 공정(원본, 빈 목록 = 전체)을 돌려준다.

    `screen` 은 출처 이름(「산출 결과」 · 「가용설비」 …), `labels` 는 보이는 글자(없으면 원본 —
    Space), `empty` 는 걸린 것이 없을 때 값 칸 글자다(산출 결과 STEP별 「공정을 선택하세요」).
    """
    choices = tuple(dict.fromkeys(str(option) for option in options))
    hits = shared_process.applied(choices)
    if not _first_draw_this_run():
        return hits
    gone = shared_process.missing(choices)
    text = _text_func(choices, labels)
    origin = shared_process.origin_for(screen) if hits else None
    _remember(
        _PickerContext(
            mode=MULTI,
            screen=screen,
            page=_page_hash(),
            options=choices,
            texts=tuple(text(option) for option in choices),
            selected=tuple(hits),
            key=None,
        )
    )
    shared_process.note_drawn(screen, MULTI, choices)
    with page_condition_slot(0).container(gap=None):
        condition_field(
            FIELD_LABEL,
            filter_value(hits, choices, text, empty=empty),
            slug=FIELD_SLUG,
            key=FIELD_KEY,
            icon=MISSING_ICON if gone and not hits else FIELD_ICON,
            status=origin_status(origin),
            help=filter_help(hits, text),
            accent=bool(hits),
            disabled=not choices,
            on_click=open_process_dialog,
        )
        st.html(process_marker(screen, MULTI))
    return hits


def render_process_choice(
    options: Sequence[object],
    *,
    screen: str,
    key: str,
    labels: ProcessLabels | None = None,
) -> str | None:
    """하나 고름 화면의 값 칸을 그리고 지금 공정(`st.session_state[key]`, 원본)을 돌려준다.

    공정은 부르는 쪽이 먼저 정해 `key` 에 적어 둔다(공용 값을 따를지는
    `shared_process.follow_single`). 팝업에서 사용자가 직접 고른 공정은 `key` 에 적고 공용 값도 그
    하나로 바꾼다(`shared_process.pick_single` — 2026-11-09 보드 C2 (가)). 들어온 길 · 기본 공정 ·
    따라 연 공정은 보내지 않는다. 강조 · 출처는 지금 공정이 공용 값을 따라 연(또는 여기서 보낸)
    공정일 때만 선다(`shared_process.single_applied`).
    """
    choices = tuple(dict.fromkeys(str(option) for option in options))
    saved = st.session_state.get(key)
    selected = str(saved) if saved is not None and str(saved) in choices else None
    if not _first_draw_this_run():
        return selected
    text = _text_func(choices, labels)
    followed = shared_process.single_applied(screen, selected)
    origin = shared_process.origin_for(screen) if followed else None
    gone = shared_process.missing(choices) if not shared_process.inside(choices) else []
    _remember(
        _PickerContext(
            mode=SINGLE,
            screen=screen,
            page=_page_hash(),
            options=choices,
            texts=tuple(text(option) for option in choices),
            selected=(selected,) if selected is not None else (),
            key=key,
        )
    )
    shared_process.note_drawn(screen, SINGLE, choices, selected)
    with page_condition_slot(0).container(gap=None):
        condition_field(
            FIELD_LABEL,
            literal_markdown(text(selected)) if selected is not None else NO_PROCESS_VALUE,
            slug=FIELD_SLUG,
            key=FIELD_KEY,
            icon=MISSING_ICON if gone else FIELD_ICON,
            status=origin_status(origin),
            accent=followed,
            disabled=not choices,
            on_click=open_process_dialog,
        )
        st.html(process_marker(screen, SINGLE))
    return selected


def render_stopped_process_field() -> None:
    """공통 진입(계산)이 멈춘 회차의 값 칸 — 선택지는 계산 뒤에야 나온다. 잠긴 채 정상 회차와 같은
    페이지 칸(`page_condition_slot(0)`)에 서서 공정 줄이 빠지지 않게 한다(HOME 공정 필터 줄과 같은
    꼴 — 검수 보드 p-stop-row). 산출 결과는 정상 회차와 같은 높이에 선다. 공정 Capa 상세도 그 앞
    「설비 시나리오」 줄이 정상 회차처럼 서서 같은 높이다(2026-11-10 답 Q2-29). 까닭은
    Alarm 의 오류가 말한다.

    선택지 기록(`_remember` · `shared_process.note_drawn`)과 표지는 남기지 않는다 — 머리 칩 · 화면
    탭 표지가 이 화면이 마지막으로 그린 선택지로 짐작하는 값을 빈 목록으로 덮지 않게.
    """
    if not _first_draw_this_run():
        return
    with page_condition_slot(0).container(gap=None):
        condition_field(
            FIELD_LABEL,
            STOPPED_VALUE,
            slug=FIELD_SLUG,
            key=FIELD_KEY,
            icon=FIELD_ICON,
            disabled=True,
        )


# ------------------------------------------------------------------ 팝업


def _remember(context: _PickerContext) -> None:
    st.session_state[CONTEXT_KEY] = context


def _context() -> _PickerContext | None:
    """팝업이 쓸 선택지 — 지금 페이지에서 적은 것만."""
    context = st.session_state.get(CONTEXT_KEY)
    if not isinstance(context, _PickerContext) or context.page != _page_hash():
        return None
    return context


def open_process_dialog() -> None:
    """값 칸 콜백 — 다른 팝업 칸과 고르다 만 판을 비우고 팝업을 연다. **마지막 줄**에서 팝업 호스트
    프래그먼트만 다시 돌린다(못 넘으면 앱 전체 — `rerun_fragment_if_alone`)."""
    forget_page_dialogs()
    st.session_state.pop(PICKER_KEY, None)
    st.session_state[DIALOG_KEY] = True
    rerun_fragment_if_alone(CONDITION_DIALOG_FRAGMENT_KEY, FIELD_KEY)


def close_process_dialog() -> None:
    st.session_state.pop(DIALOG_KEY, None)


def process_dialog_is_open() -> bool:
    return DIALOG_KEY in st.session_state


@st.dialog(FIELD_LABEL, width="large", icon=FIELD_ICON, on_dismiss=close_process_dialog)
def show_process_dialog(page_file: str | None) -> None:
    """팝업 껍데기. 열림 키가 있는 동안 `app.py` 의 호스트 프래그먼트가 매 회차 부른다."""
    del page_file
    render_process_dialog_body()


@keeps_app_run_open
def render_process_dialog_body() -> None:
    """판 하나(찾기 · 「전체」 · 「적용」 · 타일). 트리거가 온 회차에만 값을 바꾸고 앱 전체를 다시
    돌린다.

    여러 개 고름의 「적용」 은 `shared_process.apply_from_screen`(이 화면에 없는 값은 남김 · 모두
    켜면 이 화면 몫은 전체), 「전체」 는 `shared_process.clear`, 하나 고름은 그 화면의 공정
    칸(`key`)을 바꾸고 공용 값을 그 하나로 보낸다(`shared_process.pick_single` — C2 (가)).
    """
    context = _context()
    if context is None:
        st.caption(NO_PROCESS_VALUE)
        return
    result = render_process_picker_apply(
        mode=context.mode,
        options=context.options,
        texts=context.texts,
        selected=context.selected,
        has_shared=bool(shared_process.values()),
        key=PICKER_KEY,
    )
    if result is None:
        return
    if result.clear:
        shared_process.clear()
    elif context.mode == SINGLE:
        if not result.values or context.key is None:
            return
        st.session_state[context.key] = result.values[0]
        shared_process.pick_single(context.screen, result.values[0], labels=_shown_labels(context))
    else:
        shared_process.apply_from_screen(
            result.values, context.options, context.screen, labels=_shown_labels(context)
        )
    close_process_dialog()
    st.rerun()


def render_process_picker_apply(
    *,
    mode: str,
    options: Sequence[str],
    texts: Sequence[str],
    selected: Sequence[str],
    has_shared: bool,
    key: str,
) -> PickerResult | None:
    """Components v2 판. 「적용」 · 「전체」 · 하나 고름 누름이 온 회차에만 결과를 돌려준다.

    고른 값은 받은 선택지 안 것만 남긴다(차례는 선택지 차례). 그 밖의 회차는 None — 판에서 고르는
    동안의 값은 서버에 오지 않는다(초안). 시험은 이 함수를 갈아 끼운다(Components v2 는 AppTest 에
    없다).
    """
    result = _PROCESS_PICKER(
        key=key,
        data={
            "mode": mode,
            "options": [
                {"value": value, "label": text} for value, text in zip(options, texts, strict=True)
            ],
            "selected": list(selected),
            "hasShared": has_shared,
        },
        on_apply_change=lambda: None,
        width="stretch",
    )
    # 트리거는 `apply` 하나다 — 결과는 dict 라 `clear` 같은 이름은 메서드(`dict.clear`)와 겹친다.
    applied = getattr(result, "apply", None)
    if not isinstance(applied, Mapping):
        return None
    if applied.get("clear") is True:
        return PickerResult(clear=True)
    raw = applied.get("values")
    if not isinstance(raw, list):
        return None
    picked = {str(value) for value in raw}
    values = tuple(option for option in options if option in picked)
    if mode == SINGLE and len(values) != 1:
        return None
    return PickerResult(values=values)


def _shown_labels(context: _PickerContext) -> dict[str, str]:
    """판 선택지의 보이는 글자 가운데 원본과 다른 것 — 공용 값에 함께 실어 머리 칩이 그 글자로
    읽는다(원본 그대로인 화면 — Space — 은 다른 화면이 준 표시명을 덮지 않는다)."""
    return {
        value: text
        for value, text in zip(context.options, context.texts, strict=True)
        if text != value
    }


# ------------------------------------------------------------------ 머리 띠 칩 · 화면 탭 표지


def _label_of(path: str | None = None) -> Callable[[str], str]:
    """원본 → 보이는 글자(보낸 화면이 준 표시명, 없으면 원본). `path` 가 원본 이름으로 그리는
    화면(`shared_process.ORIGINAL_NAME_SCREENS` — Space)이면 원본 그대로다."""
    if path in shared_process.ORIGINAL_NAME_SCREENS:
        return str
    mapping = dict(zip(shared_process.values(), shared_process.labels(), strict=True))
    return lambda value: mapping.get(value, value)


def tab_title(mark: shared_process.ScreenMark) -> str:
    """화면 탭 표지 풍선 — 「공정 Mold · Underfill — 산출 결과 에서」 + 없는 공정이 있으면 둘째 줄
    「PMC 는 이 화면에 없음」. 이 화면에 걸리는 공정이 없으면 첫 줄은 수만 적는다."""
    label = _label_of()
    names = " · ".join(label(value) for value in mark.inside) or f"{len(shared_process.values())}개"
    head = TAB_TITLE.format(names=names)
    origin = shared_process.origin()
    if origin:
        head = f"{head} — {FROM_TEXT.format(origin=origin)}"
    if not mark.missing:
        return head
    absent = [label(value) for value in mark.missing]
    line = ABSENT_LINE.format(names=" · ".join(absent), particle=topic_particle(absent[-1]))
    return f"{head}\n{line}"


def _mark_for(path: str | None) -> shared_process.ScreenMark | None:
    entry = shared_process.FOLLOWERS.get(path or "")
    return None if entry is None else shared_process.screen_mark(*entry)


def _tab_of(mark: shared_process.ScreenMark | None) -> dict[str, Any] | None:
    """탭 표지 한 벌 — 지금 값이 그 화면이 따르는 꼴이고, 그린 화면이면 실제로 걸리거나 없는
    공정이 있을 때만. 하나 고름 화면이 들어온 길 · ◀▶ 로 다른 공정을 보고 있으면 걸린 것이
    아니라 표지가 없다."""
    if mark is None or not mark.follows:
        return None
    if mark.drawn and not mark.on and not mark.missing:
        return None
    return {"miss": bool(mark.missing), "title": tab_title(mark)}


def tab_mark(path: str) -> dict[str, Any] | None:
    """화면 탭 이름 곁 깔때기 표지 — 따라가는 화면이고 지금 값이 그 화면에 걸릴 때만(`_tab_of`).
    `miss` 는 그 화면이 마지막으로 그린 선택지에 없는 공용 공정이 있나(주황), 아직 그리지 않은
    화면은 청록이다."""
    return _tab_of(_mark_for(path))


def _here(mark: shared_process.ScreenMark) -> dict[str, Any]:
    """이 화면에 대한 값 — 걸리나 · 따르나 · 걸린 공정(`inside` — 이 화면 선택지 차례) · 없는
    공정."""
    return {
        "on": mark.on,
        "follows": mark.follows,
        "inside": list(mark.inside),
        "missing": list(mark.missing),
    }


def screen_order(held: Sequence[str], mark: shared_process.ScreenMark | None) -> list[str]:
    """머리 칩 · 판의 공정 차례. 따라가는 화면이면 이 화면 선택지 차례로 걸린 공정을 앞에, 없는
    공정을 뒤에 둔다 — 칩의 첫 이름 · 판 · 탭 풍선 · 사이드바 값 칸(표시순서상 첫 공정)이 같은
    차례를 따른다. 따라가지 않는 화면은 보낸 차례 그대로다."""
    if mark is None or not mark.follows:
        return list(held)
    first = [value for value in mark.inside if value in held]
    return [*first, *(value for value in held if value not in first)]


def header_chip(path: str | None) -> dict[str, Any] | None:
    """머리 띠 「공정」 칩 data — 공용 값이 있을 때만. 값 · 이 화면 기록이 그대로면 같은 dict
    다(시각 · 카운터 없음).

    글자(`labels` · `top`)는 그 화면 글자다 — 원본 이름으로 그리는 화면(Space)이면 원본, 아니면
    보낸 화면의 표시명(2026-11-10 보드 Q-3). `here` 는 지금 화면(`path`)에 대한 짐작(세션 기록 —
    따라가지 않는 화면은 None)이고, 값 칸을 그린 회차에는 그 회차의 표지(`process_marker`)가 알림
    칸 JS 에서 이긴다 — 차례(`screen_order`)도 그 표지의 `inside` 로 JS 가 다시 세운다. `field` 는
    사이드바 값 칸 key 다 — 판 「공정 고르기」 가 그 칸을 눌러 팝업을 연다.
    """
    held = shared_process.values()
    if not held:
        return None
    mark = _mark_for(path)
    ordered = screen_order(held, mark)
    label = _label_of(path)
    shown = [label(value) for value in ordered]
    return {
        "values": ordered,
        "labels": shown,
        "top": first_and_rest(shown),
        "origin": shared_process.origin(),
        "version": shared_process.version(),
        "here": None if mark is None else _here(mark),
        "field": FIELD_KEY,
        "marker": MARKER_ATTRIBUTE,
    }


def process_marker(screen: str, mode: str) -> str:
    """값 칸을 그린 회차의 표지 — 스타일만 든 `st.html` 한 자리. 이 화면 주소 · 공용 값의 판 · 이
    화면에 걸리나 · 없는 공정 · 지금 탭 표지를 싣는다. 값 칸과 같은 칸(간격 없는 블록)에 그린다 —
    `with` 안의 스타일 `st.html` 은 그 칸에 서므로 간격 있는 칸이면 틈이 생긴다."""
    mark = shared_process.screen_mark(screen, mode)
    payload = {
        "page": alerts.current_page()[1],
        "version": shared_process.version(),
        "here": None if mark is None else _here(mark),
        "tab": _tab_of(mark),
    }
    body = html.escape(json.dumps(payload, ensure_ascii=False), quote=True)
    return f'<style {MARKER_ATTRIBUTE}="{body}"></style>'
