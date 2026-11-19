# Purpose: 화면을 옮긴 뒤 떠난 화면의 위젯 값을 실어 늦게 온 회차를 가려 옮겨 간 화면을 돌려준다.

"""늦게 온 옛 화면 회차 막이(2026-11-19 — 칸을 고치자마자 누른 화면 탭이 Space 로 되돌아오던 수).

**무엇이 늦게 오나.** Streamlit 1.63 프런트는 회차 요청마다 마지막으로 받은 `new_session` 의
화면(`currentPageScriptHash`)을 싣는다. 화면 탭 · 사이드바 링크로 옮기는 요청을 보낸 뒤 옮긴
화면의 `new_session` 이 오기 전에 떠나는 화면의 위젯이 값을 하나 더 보내면, 그 요청은 떠나는
화면 주소로 가 서버가 그 화면을 다시 돈다 — 옮긴 화면이 이미 돌고 있으면 그 회차를 끊고, 아직
돌기 전이면(`st.switch_page` 의 회차 요청이 남아 있으면) 그 요청과 합쳐져 화면 주소를 덮는다.
사람이 친 값이 아니라 프런트가 스스로 보내는 메시지다 — 편집표(`st.data_editor`)는 서버가 고친
칸을 바탕 표에 접어 다시 그리면 바탕과 같아진 편집을 걷고, 걷은 상태를 0.15초 뒤에 보낸다(Space
층 사용 편집처럼 `on_change` 에서 초안에 접는 편집표). 탭 줄 JS 의 붙들기(`<tabs-hold>`)는 그
편집 회차가 끝날 때까지 기다리지만, 회차가 끝난 뒤에 나가는 이 메아리는 회차 표지
(`data-test-script-state`)로 보이지 않는다.

**서버에서 가른다 — 시계를 쓰지 않는다.** 프런트의 옮기는 요청(사이드바 링크 · 뒤로·앞으로가기
— `onPageChange`)은 앱 칸(`app.py` 가 페이지 밖에 그린 위젯)의 값만 싣고, 위젯 요청은 지금 화면
본문 위젯의 값까지 싣는다. 그래서 이번 회차의 화면이 서버가 마지막으로 들인(또는 옮기러 가는)
화면과 다르고 **그 화면 본문 위젯의 값을 실었으면** 브라우저가 옮긴 화면을 받기 전에 보낸 옛
메시지다(`stale_verdict`). `app.py` 는 그 회차를 `st.navigation()` · 머리 띠 · 페이지 전에 옮겨 간
화면으로 다시 보낸다 — 떠난 화면 주소가 브라우저 기록에 쌓이지 않는다. 떠난 화면의 위젯
콜백(편집표 `on_change` 등)은 Streamlit 이 그 앞에서 이미 돌렸다 — 값은 사람의 것이라 버리지
않는다(Space 층 사용 초안은 그 콜백이 접어 남는다).

**기록 셋**(세션 칸 하나 — `GUARD`): 마지막으로 들인 회차의 화면(`page`), 탭 줄이
`st.switch_page` 로 옮기러 간 화면(`pending` — 그 회차가 서기 전에 끊길 수 있다), 화면마다 마지막
회차에 본문(`navigation.run()`)이 등록한 위젯 id(`widgets` — 본문 위젯 id 에는 그 화면 스크립트
해시가 섞여 화면끼리 겹치지 않는다). 화면 해시는 Streamlit 이 회차 요청에서 읽은 것
(`intended_page_script_hash`)과 `st.navigation()` 이 정한 것(`ctx.page_script_hash`)이다.

내부를 못 읽으면(판이 바뀜 · 실행 문맥 없음) 막지 않는다 — 지금까지의 동작이다. 페이지 본문이
스스로 부르는 `st.switch_page`(HOME 칸 · 다음 화면 단추)는 옮기러 간 화면을 적지 않는다 — 그
회차가 서기 전에 옛 메시지가 덮는 갈래만 남는다(서고 난 뒤 온 것은 막는다).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from streamlit.runtime.scriptrunner import get_script_run_ctx

from capa_simulation.session_slot import SessionSlot

GUARD_KEY = "stale_page_guard"


@dataclass(frozen=True)
class GuardRecord:
    """막이 기록 — 들인 화면 · 옮기러 간 화면 · 화면별 본문 위젯 id(모듈 설명)."""

    page: str = ""
    pending: str = ""
    widgets: Mapping[str, frozenset[str]] = field(default_factory=dict)

    @property
    def expected(self) -> str:
        """서버가 브라우저에 세운(세우러 가는) 화면 — 옮기러 간 화면이 있으면 그것이다."""
        return self.pending or self.page


GUARD: SessionSlot[GuardRecord] = SessionSlot(GUARD_KEY, GuardRecord, GuardRecord)


def stale_verdict(record: GuardRecord, incoming: str, widget_ids: Iterable[str]) -> str:
    """늦게 온 옛 화면 회차면 다시 보낼 화면 해시, 아니면 빈 글자.

    `incoming` 은 이번 회차 요청의 화면 해시(빈 글자면 주소로 연 회차 — 보지 않는다),
    `widget_ids` 는 그 요청이 실은 위젯 값의 id 다. 화면이 서버가 세운 화면과 같거나, 그 화면
    본문 위젯의 값을 싣지 않았으면(옮기는 요청 — 앱 칸 값만) 빈 글자다.
    """
    expected = record.expected
    if not incoming or not expected or incoming == expected:
        return ""
    own = record.widgets.get(incoming)
    if not own:
        return ""
    return expected if not own.isdisjoint(widget_ids) else ""


def admitted(record: GuardRecord, incoming: str) -> GuardRecord:
    """막지 않은 회차를 들인다 — 요청한 화면이 있으면 그 화면이 들인 화면이고 옮기러 간 화면은
    걷는다(닿았거나 사람이 다른 길로 옮겼다). 주소로 연 회차(빈 글자)는 `st.navigation()` 뒤
    `note_page` 가 적는다."""
    if not incoming:
        return record
    return replace(record, page=incoming, pending="")


def _incoming_page() -> str:
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx is None:
        return ""
    try:
        return ctx.pages_manager.intended_page_script_hash or ""
    except Exception:  # noqa: BLE001 — 내부가 바뀌면 막지 않는다
        return ""


def _incoming_widget_ids() -> frozenset[str] | None:
    """이번 회차 요청이 실은 위젯 값의 id. 못 읽으면 None(막지 않는다).

    Streamlit 은 콜백을 돌리기 전에 요청의 위젯 값을 새 칸(`_new_widget_state`)에 담는다 — 공개
    API 가 없어 세션 상태 내부를 읽는다(`sidebar_status._only_this_widget_changed` 와 같은 자리,
    버전은 `streamlit==1.63.0` 고정).
    """
    try:
        from streamlit.runtime.state.session_state_proxy import get_session_state

        session = get_session_state()._state
        return frozenset(session._new_widget_state)
    except Exception:  # noqa: BLE001 — 내부가 바뀌면 막지 않는다
        return None


def stale_target() -> str | None:
    """이번 회차가 늦게 온 옛 화면 메시지이면 다시 보낼 화면의 `st.switch_page` 경로(앱 기준
    상대 경로), 아니면 None — 막지 않은 회차는 들인다(`admitted`). `app.py` 가 회차 맨 앞
    (`st.navigation()` 앞)에서 부른다."""
    record = GUARD.get()
    incoming = _incoming_page()
    ids = _incoming_widget_ids()
    target = "" if ids is None else stale_verdict(record, incoming, ids)
    if target:
        path = _page_path(target)
        if path is not None:
            return path
    GUARD.set(admitted(record, incoming))
    return None


def note_page() -> None:
    """`st.navigation()` 이 정한 이번 회차 화면을 들인 화면으로 적는다(주소로 연 첫 회차 등)."""
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx is None or not ctx.page_script_hash:
        return
    record = GUARD.get()
    if record.page != ctx.page_script_hash or record.pending == ctx.page_script_hash:
        GUARD.set(replace(record, page=ctx.page_script_hash, pending=""))


def note_switch(path: str) -> None:
    """탭 줄이 `path` 화면으로 `st.switch_page` 하기 직전에 부른다 — 그 화면 회차가 서기 전에
    온 옛 메시지가 그 요청을 덮어도 다시 보낼 곳이다."""
    target = _page_hash(path)
    if target:
        GUARD.set(replace(GUARD.get(), pending=target))


def body_widgets_before() -> frozenset[str] | None:
    """페이지 본문을 돌리기 직전까지 이번 회차가 등록한 위젯 id(`note_body_widgets` 와 짝)."""
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx is None:
        return None
    try:
        return ctx.shared.widget_ids_this_run.snapshot()
    except Exception:  # noqa: BLE001 — 내부가 바뀌면 적지 않는다
        return None


def note_body_widgets(before: frozenset[str] | None) -> None:
    """페이지 본문이 등록한 위젯 id 를 이번 회차 화면 몫으로 적는다 — 본문이 스스로 멈춘
    회차(`st.stop()`)도 그때까지 등록한 것을 적는다. 하나도 없으면 앞 기록을 둔다."""
    ctx = get_script_run_ctx(suppress_warning=True)
    if before is None or ctx is None or not ctx.page_script_hash:
        return
    try:
        body = ctx.shared.widget_ids_this_run.snapshot() - before
    except Exception:  # noqa: BLE001
        return
    if not body:
        return
    record = GUARD.get()
    widgets = dict(record.widgets)
    widgets[ctx.page_script_hash] = frozenset(body)
    GUARD.set(replace(record, widgets=widgets))


def _pages() -> tuple[Path, dict[str, Path]] | None:
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx is None:
        return None
    try:
        root = Path(ctx.main_script_path).resolve().parent
        pages = {
            page_hash: Path(str(info["script_path"])).resolve()
            for page_hash, info in ctx.pages_manager.get_pages().items()
            if info.get("script_path")
        }
    except Exception:  # noqa: BLE001
        return None
    return root, pages


def _page_hash(path: str) -> str:
    """앱 기준 상대 경로(`app_pages/x.py`)의 화면 해시. 못 찾으면 빈 글자."""
    found = _pages()
    if found is None:
        return ""
    root, pages = found
    want = (root / path).resolve()
    return next((page_hash for page_hash, script in pages.items() if script == want), "")


def _page_path(page_hash: str) -> str | None:
    """화면 해시의 앱 기준 상대 경로. 못 찾으면 None."""
    found = _pages()
    if found is None:
        return None
    root, pages = found
    script = pages.get(page_hash)
    if script is None:
        return None
    try:
        return script.relative_to(root).as_posix()
    except ValueError:
        return None
