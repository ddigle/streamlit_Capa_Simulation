# Purpose: 탭 목록의 열기·닫기·고정·상한·다시 들어옴 판정과 이동 대기 처리를 UI 없이 시험한다.

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.errors import StreamlitPageNotFoundError

from capa_simulation import page_tabs_state
from capa_simulation.navigation import (
    ALL_SPECS,
    CAPA_CHATBOT,
    HOME,
    LOAD_CONVERSION,
    PROCESS_CAPA_DETAIL,
    SCENARIO_MANAGEMENT,
)
from capa_simulation.page_tabs_state import (
    INITIAL_STRIP,
    MAX_TABS,
    PAGE_TABS_EPOCH_KEY,
    PAGE_TABS_NOTICE_KEY,
    PAGE_TABS_OPEN_KEY,
    PAGE_TABS_QUEUED_KEY,
    PAGE_TABS_REENTRY_KEY,
    TabStrip,
    can_open,
    closed,
    fallback_tab,
    load_strip,
    normalized,
    note_current_page,
    opened,
    pinned_to,
    pop_fresh_notice,
    reentered_open_tab,
    store_strip,
    switch_to_queued_tab,
)

H, A, B, C = HOME.path, LOAD_CONVERSION.path, SCENARIO_MANAGEMENT.path, CAPA_CHATBOT.path


def _strip(*paths: str, pinned: tuple[str, ...] = (H,)) -> TabStrip:
    return TabStrip(paths, frozenset(pinned))


def test_home_starts_as_the_only_pinned_tab() -> None:
    assert INITIAL_STRIP == _strip(H)
    assert not INITIAL_STRIP.closable(H)


def test_a_new_page_is_appended_and_an_open_page_keeps_its_place() -> None:
    strip = opened(opened(INITIAL_STRIP, A), B)
    assert strip.paths == (H, A, B)
    assert opened(strip, A) == strip


def test_unknown_and_repeated_paths_are_dropped_and_pinned_tabs_stay_left() -> None:
    strip = normalized(TabStrip((A, "app_pages/gone.py", H, A, B), frozenset({H, "x"})))
    assert strip.paths == (H, A, B)
    assert strip.pinned == frozenset({H})


def test_pinning_and_unpinning_keep_pinned_tabs_on_the_left() -> None:
    """고정하면 고정 묶음의 끝으로, 풀면 나머지 묶음의 앞으로 간다(브라우저 탭과 같다)."""
    strip = _strip(H, A, B, C)

    pinned = pinned_to(strip, C, True)
    assert pinned.paths == (H, C, A, B)
    assert not pinned.closable(C)

    unpinned = pinned_to(pinned, H, False)
    assert unpinned.paths == (C, H, A, B)
    assert unpinned.closable(H)
    assert pinned_to(strip, "app_pages/gone.py", True) == strip


def test_closing_a_background_tab_keeps_the_page() -> None:
    assert closed(_strip(H, A, B), A, B) == (_strip(H, B), None)


def test_closing_the_active_tab_moves_to_the_right_then_the_left_neighbour() -> None:
    assert closed(_strip(H, A, B), A, A) == (_strip(H, B), B)
    assert closed(_strip(H, A, B), B, B) == (_strip(H, A), A)
    assert closed(_strip(H, A), A, A) == (_strip(H), H)


def test_pinned_tabs_the_last_tab_and_unknown_ids_are_not_closed() -> None:
    strip = _strip(H, A)
    assert closed(strip, H, H) == (strip, None)
    assert closed(strip, "app_pages/gone.py", H) == (strip, None)
    alone = _strip(A, pinned=())
    assert not alone.closable(A)
    assert closed(alone, A, A) == (alone, None)


def test_an_unpinned_home_can_be_closed() -> None:
    strip = pinned_to(_strip(H, A), H, False)
    assert closed(strip, H, H) == (_strip(A, pinned=()), A)


def test_the_strip_holds_at_most_ten_tabs() -> None:
    paths = tuple(spec.path for spec in ALL_SPECS[:MAX_TABS])
    full = _strip(*paths)
    extra = ALL_SPECS[MAX_TABS].path

    assert MAX_TABS == 10
    assert not can_open(full, extra)
    assert can_open(full, paths[3])
    assert opened(full, extra) == full


def test_a_blocked_move_returns_to_the_previous_tab_or_the_first() -> None:
    strip = _strip(H, A)
    assert fallback_tab(strip, A) == A
    assert fallback_tab(strip, B) == H
    assert fallback_tab(strip, None) == H


# ------------------------------------------------------------------ 세션


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """가짜 `st` — 세션·주소 인자와 `st.switch_page` 기록."""
    fake = SimpleNamespace(session_state={}, query_params={}, switched=[], missing=False)

    def switch_page(page: str, *, query_params: dict[str, str] | None = None) -> None:
        if fake.missing:
            raise StreamlitPageNotFoundError(page, "", False)
        fake.switched.append((page, query_params))

    fake.switch_page = switch_page
    monkeypatch.setattr(page_tabs_state, "st", fake)
    return fake


def test_the_epoch_rises_only_when_the_list_really_changes(session: SimpleNamespace) -> None:
    store_strip(INITIAL_STRIP)
    first = session.session_state[PAGE_TABS_EPOCH_KEY]
    store_strip(INITIAL_STRIP)
    assert session.session_state[PAGE_TABS_EPOCH_KEY] == first
    store_strip(_strip(H, A))
    assert session.session_state[PAGE_TABS_EPOCH_KEY] == first + 1
    assert load_strip() == _strip(H, A)


def test_noting_pages_marks_reentry_only_for_an_already_open_tab(session: SimpleNamespace) -> None:
    note_current_page(H, page_changed=True)
    assert session.session_state[PAGE_TABS_OPEN_KEY] == (H,)
    assert session.session_state[PAGE_TABS_REENTRY_KEY] is None

    note_current_page(A, page_changed=True)
    assert load_strip().paths == (H, A)
    assert not reentered_open_tab(A)

    note_current_page(H, page_changed=True)
    assert reentered_open_tab(H)

    note_current_page(H, page_changed=False)
    assert not reentered_open_tab(H)


def test_a_queued_tab_is_switched_to_with_the_theme_kept(session: SimpleNamespace) -> None:
    session.query_params["theme"] = "dark"
    session.session_state[PAGE_TABS_QUEUED_KEY] = A

    switch_to_queued_tab(H)

    assert session.switched == [(A, {"theme": "dark"})]
    assert PAGE_TABS_QUEUED_KEY not in session.session_state


def test_a_queue_for_the_current_page_is_dropped_without_moving(session: SimpleNamespace) -> None:
    session.session_state[PAGE_TABS_QUEUED_KEY] = H

    switch_to_queued_tab(H)

    assert session.switched == []
    assert PAGE_TABS_QUEUED_KEY not in session.session_state


def test_a_switch_without_navigation_is_dropped_quietly(session: SimpleNamespace) -> None:
    session.missing = True
    session.session_state[PAGE_TABS_QUEUED_KEY] = A

    switch_to_queued_tab(H)

    assert PAGE_TABS_QUEUED_KEY not in session.session_state


def test_an_eleventh_page_is_sent_back_with_a_notice_and_its_handoff_dropped(
    session: SimpleNamespace,
) -> None:
    paths = tuple(spec.path for spec in ALL_SPECS if spec.path != PROCESS_CAPA_DETAIL.path)[
        :MAX_TABS
    ]
    store_strip(_strip(*paths))
    session.session_state["handoff"] = object()

    switch_to_queued_tab(
        PROCESS_CAPA_DETAIL.path,
        current_title="공정 Capa 상세",
        previous_path=paths[2],
        handoff_keys=("handoff",),
    )

    assert session.switched == [(paths[2], None)]
    assert "handoff" not in session.session_state
    notice = pop_fresh_notice()
    assert notice is not None and notice[0] == 1 and "안 쓰는 탭을 닫아 주세요" in notice[1]
    assert "공정 Capa 상세" in notice[1]
    # 한 번만 싣는다. 다음 알림은 새 번호다.
    assert pop_fresh_notice() is None
    switch_to_queued_tab(PROCESS_CAPA_DETAIL.path, previous_path=paths[2])
    second: Any = session.session_state[PAGE_TABS_NOTICE_KEY]
    assert second[0] == 2


def test_an_open_page_or_a_free_slot_is_never_sent_back(session: SimpleNamespace) -> None:
    store_strip(_strip(H, A))
    switch_to_queued_tab(B, previous_path=A)
    switch_to_queued_tab(A, previous_path=H)
    assert session.switched == []
