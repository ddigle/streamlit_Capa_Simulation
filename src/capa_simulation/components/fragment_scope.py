# Purpose: 편집기 구역(키 붙은 프래그먼트) 회차의 규칙 도우미 — 앱 전체로 올리는 자리 · 머리 표지
# 견주기 · 작은 인자 · 남의 저장 확인 · 오류 카드.

"""편집기 구역 회차(L1)의 공용 도우미 — AGENTS 9장 「구역 회차 규칙」 R1 ~ R6 의 파이썬 몫.

편집기(설비 마스터 표 · 범용 편집 그리드 · 시나리오 목록)를 `@st.fragment(key=…)` 로 감싸면 칸
하나를 고칠 때 앱 전체 회차 대신 그 구역만 돈다. 구역 밖(머리 띠 변경 칩 · 화면 탭 줄 점 · 떠나기
확인 · 테마 표지 · 팝업 호스트)은 그 회차에 다시 그려지지 않으므로, 밖이 읽는 값이 바뀐 상호작용은
앱 전체 회차로 올린다.

- **R1 올리는 자리**(`escalate` · `escalates` · `escalate_if_moved`) — 위젯 콜백 끝(`st.rerun()` —
  이 상호작용이 앱 전체 회차가 된다, 본문 전이라 위젯 상태가 남는다) 또는 본문을 다 그린
  뒤(`st.rerun(scope="app")`)에서만 올린다. 본문 **앞**에서 올리면 그 회차가 다시 그리지 않은 구역
  위젯(Components v2 출납 상태 값)을 회차 끝 정리가 지워 ack 를 잃는다(rerun-1120 시범 1차 —
  `tests/test_fragment_scope.py` 가 되살린다).
- **R2 머리 표지**(`editor_scope(head=…)`) — 구역 밖이 그리는 값(미저장 있음/없음 · 작은 편집표
  이름 · 출발점 · 편집본 리비전 · 팝업 열림 칸 …)을 해시 가능한 값(보통 튜플)으로 돌려주는 함수. 앱
  전체 회차가 본문 **앞**에서 찍어 두고(밖이 그린 순간의 값), 구역 회차의 콜백 끝(`escalates`) ·
  본문 뒤(`editor_scope` 가 스스로)에서 견줘 다르면 올린다.
- **R3 작은 인자**(`check_small_args` · `editor_scope(one_shot=…)`) — 구역 인자는 직전 앱 전체 회차
  값으로 고정되고 프래그먼트 저장소가 다음 앱 전체 회차까지 쥔다. 표 · 스냅숏(표를 든 dataclass)은
  넘기지 않고 구역 안에서 세션 · 캐시로 다시 읽는다 — 넘기면 `TypeError`. 한 번만 쓰는 표지
  인자(`drafts_replaced` 꼴)는 구역 회차에서 `False` 로 끈다.
- **R4 남의 저장**(`editor_scope(token=…)`) — 저장본 쌍 토큰을 값싸게 읽는 함수(갈래가 넘긴다). 앱
  전체 회차가 찍고, 구역 회차는 본문 머리에서 다시 읽어 다르면 표지를 세운다 — 본문 뒤 · 다음 콜백
  끝에서 올린다(앱 전체 회차의 편집본 세우기가 버리고 다시 세운다).
- **R6 오류 카드** — 구역 본문의 처리 못 한 오류는 Streamlit 기본 오류 상자 대신 코어 화면 카드
  (`page_failure_card.render_page_failure`)로 그 구역 자리에 서고 `st.stop()` 으로 끝난다(카드 ·
  기록 · `AD-22` 는 `run_core_page` 와 같다). 등급 거절은 바깥 `grade_ui.in_fragment` 가 받고,
  Streamlit 제어 예외는 그대로 지나간다.
- **구역 칸**(`SCOPE_BOX_PREFIX` · `box_key`) — 본문은 `st.container(key=box_key(key))` 안에
  그린다. 회차 표지 지킴이(`grid_shared_assets/leave.js` 의 `<capa-scope-run>`)가 이 접두의 칸 안
  요소만 낡음이 된 회차를 「편집기 구역 회차」 로 알아보고 문서 뿌리에 `SCOPE_RUN_ATTRIBUTE` 를
  단다 — 그동안 실행 표시(달리는 사람)와 구역 안 낡음 흐림을 감춘다(`SCOPE_RUN_STYLE`, 머리 띠
  스타일이 앱 전체 회차마다 싣는다).

받는 자리 그물(`tests/grade_support.assert_refusals_caught`)은 데코레이터 이름으로 본다 —
`editor_scope` 는 `@st.fragment(key=…)` · `@grade_ui.in_fragment` 를 대신하지 않고 그 **아래**에
단다::

    @st.fragment(key=SCOPE)
    @grade_ui.in_fragment
    @fragment_scope.editor_scope(SCOPE, head=head_marks, token=saved_pair_token)
    def render_editor_scope(table: str) -> None: ...

콜백은 `@fragment_scope.escalates(SCOPE)` 를 `@grade_ui.on_press` **위**에 단다(거절은 `on_press`
가 구역 회차면 콜백 끝에서 스스로 올린다). 이 모듈은 머리에서 화면 모듈(`grade_ui` ·
`page_failure_card`)을 읽지 않는다 — 머리 띠(`app_header`)가 `SCOPE_RUN_STYLE` 을 읽고, `grade_ui`
→ `sso_identity` → `app_header` 고리를 피한다.
"""

from __future__ import annotations

import dataclasses
import functools
import logging
from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Final, NoReturn, TypeVar, cast

import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import (
    RunLocation,
    ThreadState,
    get_script_run_ctx,
)

from capa_simulation.session_slot import SessionSlot
from capa_simulation.sidebar_status import keeps_app_run_open

F = TypeVar("F", bound=Callable[..., Any])

# 편집기 구역 칸 key 의 접두 — `.st-key-capa_scope_<key>` 가 회차 표지 지킴이(`leave.js`)와
# 스타일의 계약이다.
SCOPE_BOX_PREFIX: Final = "capa_scope_"
# 편집기 구역만 도는 회차 동안 문서 뿌리(`<html>`)에 다는 표지(`leave.js` 의 `SCOPE_RUN_ATTRIBUTE`).
SCOPE_RUN_ATTRIBUTE: Final = "data-capa-scope-run"
# 구역 회차 동안 감추는 것 — 실행 표시(달리는 사람 · Stop)와 구역 칸 안 낡음 흐림. 앱 전체 회차 ·
# 연결 끊김 표시는 그대로다(표지가 서지 않는다). 낡음 흐림은 앱이 0.3초 뒤 곧바로 0.33 으로 내리는
# 규칙(`sidebar_style.STALE_DIM_DELAY`)을 덮는다 — 구역 칸 밖은 구역 회차에 낡음이 되지 않는다.
SCOPE_RUN_STYLE: Final = (
    f":root[{SCOPE_RUN_ATTRIBUTE}] "
    '[data-testid="stStatusWidget"]:has([data-testid="stStatusWidgetRunningIcon"])'
    " { visibility: hidden !important; }"
    f':root[{SCOPE_RUN_ATTRIBUTE}] [class*="st-key-{SCOPE_BOX_PREFIX}"] [data-stale="true"]'
    " { opacity: 1 !important; }"
)
# 구역 인자로 넘겨도 되는 모음의 길이 상한(R3) — 그보다 긴 목록 · 사전은 세션 · 캐시로 다시 읽는다.
SMALL_ITEMS: Final = 32
# 세션 칸 접두 — 구역마다 머리 표지 · 저장 토큰 · 「남의 저장을 봤다」 표지.
_STATE_PREFIX: Final = "capa_scope_state__"
_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class _Spec:
    key: str
    head: Callable[[], Hashable] | None
    token: Callable[[], Hashable] | None
    one_shot: tuple[str, ...]
    box: bool
    page: str
    href: str
    # 세션 칸 — 앱 전체 회차가 찍은 머리 표지 · 저장 토큰, 구역 회차가 남의 저장을 봤다는 표지.
    head_slot: SessionSlot[object]
    token_slot: SessionSlot[object]
    moved_slot: SessionSlot[bool]


# 구역 key → 규칙(모듈을 읽을 때 데코레이터가 적는다 — 콜백 `escalates` 가 부르는 순간 찾는다).
_SPECS: dict[str, _Spec] = {}


def fragment_only_run() -> bool:
    """지금 회차가 프래그먼트 · 팝업만 다시 도는 회차인가(앱 전체 회차가 아님). 콜백도 그 회차
    안에서 돈다."""
    ctx = get_script_run_ctx(suppress_warning=True)
    return bool(ctx is not None and ctx.fragment_ids_this_run)


def in_callback() -> bool:
    """지금 위젯 콜백 안인가(본문 전)."""
    try:
        return ThreadState.get().run_location is RunLocation.CALLBACK
    except RuntimeError:
        return False


def box_key(key: str) -> str:
    """구역 `key` 의 본문 칸 key(`SCOPE_BOX_PREFIX` + key)."""
    return f"{SCOPE_BOX_PREFIX}{key}"


@contextmanager
def scope_box(key: str) -> Iterator[None]:
    """구역 본문 칸을 연다 — `editor_scope(box=False)` 로 칸 자리를 손수 정할 때 쓴다."""
    with st.container(key=box_key(key)):
        yield


def escalate() -> None:
    """구역 회차면 앱 전체 회차로 올린다(R1) — 콜백 안이면 `st.rerun()`, 본문이면
    `st.rerun(scope="app")`. 앱 전체 회차면 아무것도 하지 않는다. 본문에서는 **구역 위젯을 다 그린
    뒤**에만 부른다."""
    if not fragment_only_run():
        return
    if in_callback():
        st.rerun()
    st.rerun(scope="app")


def _pending_refusal() -> bool:
    from capa_simulation.components import grade_ui

    return bool(SessionSlot(grade_ui.PENDING_KEY, bool).peek())


def scope_moved(key: str) -> bool:
    """구역 밖이 그린 값이 낡았는가 — 머리 표지가 앱 전체 회차에 찍은 값과 다르거나, 본문 머리가
    남의 저장을 봤거나(R4), 콜백 거절 알림이 남았다."""
    if _pending_refusal():
        return True
    spec = _SPECS.get(key)
    if spec is None:
        return False
    if spec.moved_slot.get():
        return True
    return spec.head is not None and spec.head() != spec.head_slot.peek()


def escalate_if_moved(key: str) -> None:
    """구역 회차이고 `scope_moved(key)` 면 올린다 — 콜백 끝 · 본문 뒤에서만 부른다(R1)."""
    if fragment_only_run() and scope_moved(key):
        escalate()


def escalates(key: str) -> Callable[[F], F]:
    """위젯 콜백 감싸기 — 콜백이 끝난 뒤 구역 `key` 의 머리 표지가 바뀌었으면 이 상호작용을 앱 전체
    회차로 올린다(R1 · R2). `@grade_ui.on_press` **위**에 단다."""

    def decorate(fn: F) -> F:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            escalate_if_moved(key)
            return result

        return cast(F, inner)

    return decorate


def _too_big(value: object) -> str | None:
    module = type(value).__module__.split(".")[0]
    if module in {"pandas", "numpy", "pyarrow"}:
        return type(value).__name__
    if isinstance(value, (str, bytes)):
        return None
    if isinstance(value, (Mapping, Sequence, set, frozenset)) and len(value) > SMALL_ITEMS:
        return f"{type(value).__name__}({len(value)})"
    return None


def check_small_args(args: Sequence[object], kwargs: Mapping[str, object]) -> None:
    """구역 인자가 작은 값인지 본다(R3) — 표(pandas · numpy · pyarrow), 표를 든 dataclass,
    `SMALL_ITEMS` 보다 긴 목록 · 사전이면 `TypeError`. 크기를 재지 않고 꼴만 본다."""
    named = [(f"#{index}", value) for index, value in enumerate(args)]
    named.extend(kwargs.items())
    for name, value in named:
        found = _too_big(value)
        if found is None and dataclasses.is_dataclass(value) and not isinstance(value, type):
            for field in dataclasses.fields(value):
                inner = _too_big(getattr(value, field.name))
                if inner is not None:
                    found = f"{type(value).__name__}.{field.name}: {inner}"
                    break
        if found is not None:
            raise TypeError(
                f"구역 인자는 작은 값만 넘깁니다({name}: {found}) — "
                "구역 안에서 세션 · 캐시로 다시 읽습니다"
            )


def _stamp(spec: _Spec) -> None:
    if spec.head is not None:
        spec.head_slot.set(spec.head())
    if spec.token is not None:
        spec.token_slot.set(spec.token())
    spec.moved_slot.clear()


def _check_token(spec: _Spec) -> None:
    if spec.token is not None and spec.token() != spec.token_slot.peek():
        spec.moved_slot.set(True)


def _current_page() -> tuple[str, str]:
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx is None:
        return "", ""
    info = ctx.pages_manager.get_pages().get(ctx.page_script_hash)
    if info is None:
        return "", ""
    return str(info.get("page_name") or ""), str(info.get("url_pathname") or "")


def _fail(spec: _Spec, error: BaseException) -> NoReturn:
    from capa_simulation import page_failures
    from capa_simulation.components.page_failure_card import render_page_failure

    page, href = (spec.page, spec.href) if spec.page or spec.href else _current_page()
    failure = page_failures.record_failure(page=page, href=href, kind=type(error).__name__)
    _LOGGER.error("편집기 구역 %s 실패 — 참고 번호 %s", spec.key, failure.ref, exc_info=error)
    render_page_failure(failure, error)
    st.stop()


def _run_guarded(spec: _Spec, body: Callable[[], Any]) -> Any:
    from streamlit.errors import FragmentHandledException
    from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException

    from capa_simulation.auth import grades

    try:
        return body()
    except (ScriptControlException, KeyboardInterrupt, FragmentHandledException):
        raise
    except grades.REFUSALS:
        raise
    except BaseException as error:
        _fail(spec, error)


def editor_scope(
    key: str,
    *,
    head: Callable[[], Hashable] | None = None,
    token: Callable[[], Hashable] | None = None,
    one_shot: Sequence[str] = (),
    box: bool = True,
    page: str = "",
    href: str = "",
) -> Callable[[F], F]:
    """편집기 구역 본문 감싸기(R1 ~ R4 · R6) — `@st.fragment(key=key)` · `@grade_ui.in_fragment`
    **아래**에 단다(모듈 설명). `key` 는 프래그먼트 key 와 같게 준다.

    - 앱 전체 회차: 본문 앞에서 머리 표지(`head`) · 저장 토큰(`token`)을 찍는다.
    - 구역 회차: 한 번만 쓰는 인자(`one_shot`)를 `False` 로 끄고, 본문 머리에서 토큰을 다시 읽어
      다르면 표지를 세운다. 본문을 다 그린 뒤 `scope_moved` 면 앱 전체로 올린다.
    - 인자는 늘 `check_small_args` 를 지난다. 본문은 `box` 면 구역 칸(`box_key(key)`) 안에 그린다.
    - 본문 오류는 코어 화면 카드로(`page` · `href` — 비우면 지금 화면의 이름 · 주소). 앱 전체
      회차로 끝날 수 있는 본문이라 `sidebar_status.keeps_app_run_open` 을 함께 씌운다.
    """
    spec = _Spec(
        key=key,
        head=head,
        token=token,
        one_shot=tuple(one_shot),
        box=box,
        page=page,
        href=href,
        head_slot=SessionSlot(f"{_STATE_PREFIX}{key}:head", object),
        token_slot=SessionSlot(f"{_STATE_PREFIX}{key}:token", object),
        moved_slot=SessionSlot(f"{_STATE_PREFIX}{key}:moved", bool, lambda: False),
    )
    _SPECS[key] = spec

    def decorate(fn: F) -> F:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            check_small_args(args, kwargs)
            fragment_run = fragment_only_run()
            if fragment_run:
                kwargs = {**kwargs, **{name: False for name in spec.one_shot if name in kwargs}}
                _check_token(spec)
            else:
                _stamp(spec)

            def body() -> Any:
                if not spec.box:
                    return fn(*args, **kwargs)
                with scope_box(key):
                    return fn(*args, **kwargs)

            result = _run_guarded(spec, body)
            if fragment_run:
                escalate_if_moved(key)
            return result

        return cast(F, keeps_app_run_open(inner))

    return decorate
