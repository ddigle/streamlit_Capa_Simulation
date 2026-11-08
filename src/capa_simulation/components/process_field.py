# Purpose: 공용 공정 값의 사이드바 값 칸 · 고르는 팝업 · 본문 칩을 한 꼴로 그린다.

"""공용 공정 칸의 화면 조각(2026-11-08 사용자 답 P1 · P2 — 값과 규칙은 `shared_process.py`).

- **값 칸** — 사이드바 조회 조건 패널의 페이지 칸(`page_condition_slot(0)`)에 이름 줄 「공정」 + 값
  칸 한 벌(`condition_field`)로 선다. 칸 높이는 고른 수와 상관없이 같다(칩 칸은 고른 수에 따라 60 →
  160px 로 흔들려 사이드바를 밀었다 — 2026-11-07 조사). 공용 값이 이 화면에 걸리면 값 칸 테두리를
  강조하고(`ACCENT_SUFFIX`), 다른 화면에서 온 값이면 이름 줄 오른쪽에 「HOME 에서」 꼴 출처를 단다.
  이 화면에 없는 공정이면 이름 줄에 주황 배지 「HB 접합 없음」(여럿이면 「n개 없음」)과 값 칸 아이콘
  `filter_alt_off` 로 알린다 — 사내는 설비 쪽 공정 이름이 달라 자주 뜨므로 글자만 흐리게 두지
  않는다.
- **팝업** — 값 칸을 누르면 `app.py` 의 조건 팝업 호스트 프래그먼트만 다시 돈다(열기로 앱 전체가
  돌지 않는다 — 설계 규칙 UI-PRF-01, 시나리오 · 조회기간 칸과 같은 `rerun_fragment_if_alone`). 팝업
  본문은 Components v2 판 하나(`process_field_assets/`)라 타일을 누르는 동안 서버가 돌지 않고, 누른
  뒤에도 초점이 그 타일에 남아 키보드만으로 「적용」 까지 닿는다(UI-INP-03). 팝업이 쓰는 선택지는
  페이지가 값 칸을 그린 전체 회차에 세션에 적어 둔다(호스트만 도는 회차는 페이지를 돌리지 않는다).
- **본문 칩** — 공용 값이 이 화면에 걸리면 본문 위에 「공정 Mold · HOME 에서」 칩을 세운다(누르면
  공용 값을 지운다). 자리는 `app.py` 가 페이지 앞에 세운 칸(`render_chip_slot`)이라 사이드바를
  접어도 보인다.

한 회차에 값 칸은 하나다 — 같은 전체 회차에 두 번 부르면 둘째부터는 그리지 않고 거를 값만 돌려준다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation import shared_process
from capa_simulation.components.condition_field import condition_field
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.process_labels import ProcessLabels
from capa_simulation.design import tokens
from capa_simulation.page_bootstrap import PAGE_DIALOG_SUFFIX, forget_page_dialogs
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
# 본문 칩 자리(`app.py` 가 페이지 앞에 세운 칸)와 칩.
CHIP_SLOT_KEY = "shared_process_chip_slot"
CHIP_BOX_KEY = "shared_process_chip_box"
CHIP_KEY = "shared_process_chip"
CHIP_ICON = ":material/close:"
MULTI = "multi"
SINGLE = "single"
# 고를 공정이 없는 값 칸 · 팝업의 값(빈 결과 — 설계 규칙 UI-TXT-04).
NO_PROCESS_VALUE = "고를 공정 없음"
# 이 화면에 없는 공정 표지(이름 줄 배지).
MISSING_BADGE = ":orange-badge[{text}]"

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


def filter_value(
    hits: Sequence[str],
    options: Sequence[str],
    text: Callable[[object], str],
    *,
    empty: str | None = None,
) -> str:
    """여러 개 고름 값 칸 글자 — 걸린 것이 없으면 「전체 N공정」(또는 `empty`), 둘까지는 이름,
    셋부터는
    「n / N 공정」(HOME 공정 필터 칸과 같은 꼴)."""
    if not options:
        return NO_PROCESS_VALUE
    if not hits:
        return empty if empty is not None else f"전체 {len(options)}공정"
    if len(hits) <= 2:
        return _shown_names(hits, text)
    return f"{len(hits)} / {len(options)} 공정"


def missing_badge(gone: Sequence[str], labels: ProcessLabels | None) -> str | None:
    """이 화면에 없는 공용 값의 이름 줄 배지. 하나면 그 이름, 여럿이면 수."""
    if not gone:
        return None
    if len(gone) == 1:
        name = labels.label(gone[0]) if labels else gone[0]
        return MISSING_BADGE.format(text=f"{literal_markdown(name)} 없음")
    return MISSING_BADGE.format(text=f"{len(gone)}개 없음")


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
    """여러 개 따라감 화면의 값 칸 · 칩을 그리고 이 화면에 거는 공정(원본, 빈 목록 = 전체)을
    돌려준다.

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
    status = missing_badge(gone, labels) or (f"{origin} 에서" if origin else None)
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
    with page_condition_slot(0).container():
        condition_field(
            FIELD_LABEL,
            filter_value(hits, choices, text, empty=empty),
            slug=FIELD_SLUG,
            key=FIELD_KEY,
            icon=MISSING_ICON if gone and not hits else FIELD_ICON,
            status=status,
            accent=bool(hits),
            disabled=not choices,
            on_click=open_process_dialog,
        )
    if hits:
        _render_chip(_shown_names(hits, text) if len(hits) <= 2 else f"{len(hits)}개", origin)
    return hits


def render_process_choice(
    options: Sequence[object],
    *,
    screen: str,
    key: str,
    labels: ProcessLabels | None = None,
) -> str | None:
    """하나 고름 화면의 값 칸 · 칩을 그리고 지금 공정(`st.session_state[key]`, 원본)을 돌려준다.

    공정은 부르는 쪽이 먼저 정해 `key` 에 적어 둔다(공용 값을 따를지는
    `shared_process.follow_single`). 팝업에서 고른 공정은 `key` 에만 적고 공용 값은 바꾸지
    않는다(받기만 — P2-2). 표지는 지금 공정이 공용 값을 따라 연 공정일 때만
    선다(`shared_process.single_applied`).
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
    status = missing_badge(gone, labels) or (f"{origin} 에서" if origin else None)
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
    with page_condition_slot(0).container():
        condition_field(
            FIELD_LABEL,
            literal_markdown(text(selected)) if selected is not None else NO_PROCESS_VALUE,
            slug=FIELD_SLUG,
            key=FIELD_KEY,
            icon=MISSING_ICON if gone else FIELD_ICON,
            status=status,
            accent=followed,
            disabled=not choices,
            on_click=open_process_dialog,
        )
    if followed and selected is not None:
        _render_chip(literal_markdown(text(selected)), origin)
    return selected


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
    칸(`key`)만 바꾼다.
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
    else:
        shared_process.apply_from_screen(result.values, context.options, context.screen)
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


# ------------------------------------------------------------------ 본문 칩


def render_chip_slot() -> None:
    """`app.py` 가 페이지 앞, 늘 같은 자리에 칩 칸을 세워 이번 회차 몫으로 적는다.

    빈 칸은 그려지지 않는다(1.63 `st.container()` 는 빈 블록을 그리지 않는다) — 칩이 없는 화면은
    본문이 내려가지 않는다.
    """
    st.session_state[CHIP_SLOT_KEY] = st.container(key=CHIP_BOX_KEY)


def _chip_style() -> str:
    """칩 꼴 — 알약(높이 2.5rem — 35px), 강조색 테두리. 테마 토큰은 그리는 회차에 읽는다."""
    button = f'.st-key-{CHIP_BOX_KEY} [data-testid="stButton"] button'
    return (
        "<style>"
        f"{button}{{min-height:2.5rem;padding:0.15rem 0.85rem 0.15rem 0.65rem;"
        f"border:1px solid {tokens.ACCENT};border-radius:999px;"
        f"background-color:{tokens.NAV_CONTROL_TINT};color:{tokens.TEXT};}}"
        f"{button}:hover{{border-color:{tokens.ACCENT};color:{tokens.TEXT};}}"
        f'{button} [data-testid="stMarkdownContainer"] p{{font-size:0.8rem;font-weight:600;}}'
        f'{button} [data-testid="stIconMaterial"]{{color:{tokens.ACCENT};font-size:1rem;}}'
        "</style>"
    )


def _render_chip(names: str, origin: str | None) -> None:
    """칩 하나. 칩 칸이 없는 회차(`app.py` 없이 페이지만 띄운 시험)는 그리지 않는다."""
    slot = st.session_state.get(CHIP_SLOT_KEY)
    if slot is None:
        return
    with slot:
        st.button(
            f"공정 {names}" + (f" · {origin} 에서" if origin else ""),
            key=CHIP_KEY,
            icon=CHIP_ICON,
            type="tertiary",
            on_click=shared_process.clear,
            help="누르면 모든 화면의 공정 거름을 지웁니다.",
        )
        st.html(_chip_style())
