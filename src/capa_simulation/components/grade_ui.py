# Purpose: 접속 등급의 화면 쪽 창구 — 판정기 꽂기 · 거절 알림 받기 · 등급 밖 화면 멈춤 · 설비 막대
# 감추기.

"""접속 등급의 화면 쪽 창구(`auth/grades.py` 의 판정을 화면에 잇는다).

- **꽂기**(`install`) — `app.py` 맨 앞(매 회차 — 같은 함수면 그대로)과 `capa_server.py`(운영 진입은
늘
  꽂힘)가 `sso_identity.real_caller` 를 판정기로 꽂는다. 그 뒤로 표지를 단 저장소 쓰기가 쓰는 순간의
  실제 등급을 본다(`audit/work.py`).
- **거절 알림**(`refuse` · `emit`) — 거절은 알림창 · Alarm 에 한 번(설계 규칙 UI-NTF-03 · UI-CON-03
—
  그 자리에 고칠 입력이 없어 단추 곁 줄을 두지 않는다). `queue_flash(GRADE_FLASH_KEY, …,
  popup_only=True)` 로 담고 `app.py` 가 알림 칸 곁 고정 자리에서 매 회차 `emit` 한다(이벤트 칸 한
  자리).
- **받는 자리** — 위젯 콜백은 `on_press`(받고 돌아온다 — 콜백 반환값은 버려진다), `st.fragment` ·
  `st.dialog` 함수는 `in_fragment`(받고 앱 전체를 다시 그린다 — 프래그먼트만 도는 회차에는 `app.py`
  의 `emit` 이 돌지 않는다). 프래그먼트 · 팝업 안 위젯 콜백의 거절은 `on_press` 가 표지를 세우고,
  이어
  도는 프래그먼트 본문 첫머리의 `in_fragment` 가 그 표지를 보고 앱 전체를 다시 그린다. 화면
  본문(전체
  회차)의 거절은 `page_failure_card.run_core_page` 가 받는다.
- **등급 밖 화면 · 탭**(`stop_unless`) — 주소 · 알림 · 기억된 탭 값으로 연 등급 밖 자리는 경고 한 줄
+
  「HOME 으로」 + 멈춤(Admin Area 잠금과 같은 꼴 — 설계 규칙 UI-INP-07 예외 · UI-CON-03).
- **설비 화면 내려받기 감추기**(`toolbar_scope` · `chart_config`) — 등급 밖이면 그 칸 안 Streamlit
표
  도구 막대 · 그림 막대를 줄 통째로 감춘다. 막는 벽이 아니라 길을 줄이는 것이다(칸 복사 · 캡처 ·
  인쇄).
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Final, Literal, TypeVar, cast

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

from capa_simulation.auth import grades
from capa_simulation.components import sso_identity
from capa_simulation.components.flash import emit_flash, queue_flash

F = TypeVar("F", bound=Callable[..., Any])

GRADE_FLASH_KEY: Final = "grade_refusal_flash"
# 위젯 콜백이 거절을 담았다는 표지 — 이어 도는 프래그먼트 본문(`in_fragment`)이 보고 앱 전체를 다시
# 그린다. 전체 회차의 `emit` 이 걷는다.
PENDING_KEY: Final = "grade_refusal_pending"
STOP_ICON: Final = ":material/lock:"
# 받는 자리 표지(그물 — `tests/grade_support.assert_refusals_caught` 가 정적으로 데코레이터 이름을
# 본다).
ON_PRESS_ATTRIBUTE: Final = "__grade_on_press__"
IN_FRAGMENT_ATTRIBUTE: Final = "__grade_in_fragment__"


def install() -> None:
    """판정기를 꽂는다 — `sso_identity.real_caller`(같은 함수면 그대로)."""
    if grades.caller_source() is not sso_identity.real_caller:
        grades.install_caller_source(sso_identity.real_caller)


def emit() -> None:
    """담아 둔 거절 알림을 알림창 · Alarm 으로 낸다 — 매 전체 회차 같은 자리에서 한 번(이벤트 칸 한
    자리). 콜백 거절 표지도 여기서 걷는다(이 회차가 알림을 냈다)."""
    st.session_state.pop(PENDING_KEY, None)
    emit_flash(GRADE_FLASH_KEY)


def refusal_message(exc: grades.GradeDenied | grades.SignInEnded) -> str:
    """거절 알림 글 — 등급 거절은 `grades.refusal_text`, 로그인 끝남은 `grades.SIGNED_OUT_TEXT`."""
    if isinstance(exc, grades.SignInEnded):
        return grades.SIGNED_OUT_TEXT
    return grades.refusal_text(exc.action)


def refuse(exc: grades.GradeDenied | grades.SignInEnded) -> None:
    """거절 알림을 담는다(알림창 · Alarm 으로만 — 다음 `emit` 이 낸다)."""
    queue_flash(GRADE_FLASH_KEY, refusal_message(exc), kind="error", popup_only=True)


def on_press(fn: F) -> F:
    """위젯 콜백 감싸기 — 등급 거절을 받아 알림을 담고 돌아온다(그 밖의 예외는 그대로). 거절된
    누름의 반환값은 `None` 이다(콜백 반환값은 Streamlit 이 버린다)."""

    @functools.wraps(fn)
    def inner(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except grades.REFUSALS as exc:
            refuse(exc)
            st.session_state[PENDING_KEY] = True
            return None

    setattr(inner, ON_PRESS_ATTRIBUTE, True)
    return cast(F, inner)


def fragment_only_run() -> bool:
    """지금 회차가 프래그먼트 · 팝업만 다시 도는 회차인가(앱 전체 회차가 아님)."""
    ctx = get_script_run_ctx(suppress_warning=True)
    return bool(ctx is not None and ctx.fragment_ids_this_run)


def in_fragment(fn: F) -> F:
    """`@st.fragment` · `@st.dialog` 함수 감싸기(그 데코레이터 아래쪽에 단다).

    본문에서 난 등급 거절은 알림을 담고 앱 전체를 다시 그린다. 이 팝업 · 프래그먼트 안 위젯 콜백이
    거절을 담았으면(`on_press` 의 표지) 프래그먼트만 도는 회차의 본문 첫머리에서 앱 전체를 다시
    그린다 — 그 회차에는 알림을 낼 자리(`app.py` 의 `emit`)가 돌지 않는다. 앱 전체 회차에서는 그
    회차의 `emit` 이 내므로 다시 그리지 않는다.
    """

    @functools.wraps(fn)
    def inner(*args: Any, **kwargs: Any) -> Any:
        if fragment_only_run() and st.session_state.pop(PENDING_KEY, False):
            st.rerun(scope="app")
        try:
            return fn(*args, **kwargs)
        except grades.REFUSALS as exc:
            refuse(exc)
            st.rerun(scope="app")

    setattr(inner, IN_FRAGMENT_ATTRIBUTE, True)
    return cast(F, inner)


def stop_unless(
    action: str,
    *,
    place: Literal["page", "tab"],
    tab_key: str | None = None,
    first_label: str | None = None,
) -> None:
    """화면 등급으로 그 동작을 할 수 없으면 경고 한 줄 + 「HOME 으로」 + 멈춤.

    탭(`place="tab"`)은 주소가 없어 「그 화면으로」 · 기억된 탭 값이 숨은 탭을 가리킨 회차에 한 번
    멈춘다 — `tab_key` 와 `first_label`(그 탭 묶음의 첫 라벨)을 함께 주면 탭 값을 첫 라벨로 새로
    적은 뒤 멈춰 다음 회차는 정상이다(pop 하지 않는다 — AGENTS 9장). 둘 가운데 하나만 주면
    `ValueError`.
    """
    if (tab_key is None) != (first_label is None):
        raise ValueError("tab_key 와 first_label 은 함께 줍니다")
    if sso_identity.viewer_can(action):
        return
    if place == "tab" and tab_key is not None and first_label is not None:
        st.session_state[tab_key] = first_label
    from capa_simulation.components.page_link import render_page_link
    from capa_simulation.navigation import HOME

    st.warning(grades.stop_text(action, place=place), icon=STOP_ICON)
    render_page_link(HOME.path, label=sso_identity.HOME_LINK_LABEL, icon=":material/home:")
    st.stop()


# 등급 밖 칸의 key 접두 — 앱이 매 회차 보내는 스타일 한 벌(`TOOLBAR_STYLE` — `app.py` 의 사이드바
# 스타일과 함께)이 이 접두의 칸 안 표 도구 막대 · 그림 막대를 감춘다. 칸마다 스타일을 보내지 않아
# 프래그먼트 · 팝업 본문의 이벤트 칸 자리 수가 그대로다.
HIDDEN_TOOLS_PREFIX: Final = "grade_tools_off_"
TOOLBAR_STYLE: Final = (
    "<style>"
    f'[class*="st-key-{HIDDEN_TOOLS_PREFIX}"] [data-testid="stElementToolbar"],'
    f'[class*="st-key-{HIDDEN_TOOLS_PREFIX}"] .modebar-container,'
    f'[class*="st-key-{HIDDEN_TOOLS_PREFIX}"] .modebar'
    " { display: none !important; }"
    "</style>"
)


def toolbar_key(action: str, key: str) -> str:
    """`toolbar_scope` 칸의 key — 화면 등급으로 그 동작을 할 수 없으면 감춤 접두를 단다."""
    return key if sso_identity.viewer_can(action) else f"{HIDDEN_TOOLS_PREFIX}{key}"


@contextmanager
def toolbar_scope(action: str, key: str) -> Iterator[DeltaGenerator]:
    """`st.container` 칸을 연다. 화면 등급으로 그 동작을 할 수 없으면 칸 key 에 감춤 접두를 달아 그
    칸 안 Streamlit 표 도구 막대 · 그림 막대를 줄 통째로 감춘다(찾기 · 크게 보기도 함께 —
    `TOOLBAR_STYLE`). 칸 밖에 스타일을 쓰지 않는다."""
    box = st.container(key=toolbar_key(action, key))
    with box:
        yield box


def chart_config(action: str, config: Mapping[str, object] | None = None) -> dict[str, object]:
    """그림 설정 — 화면 등급으로 그 동작을 할 수 없으면 오른쪽 위 막대(그림 저장 · 표로 보기)를
    끈다."""
    merged: dict[str, object] = dict(config or {})
    if not sso_identity.viewer_can(action):
        merged["displayModeBar"] = False
    return merged
