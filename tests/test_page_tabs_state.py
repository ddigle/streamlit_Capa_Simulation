# Purpose: 탭 목록의 열기·닫기·고정·상한·다시 들어옴 판정과 이동 대기 처리를 UI 없이 시험한다.

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.errors import StreamlitPageNotFoundError

from capa_simulation import module_registry, navigation, page_tabs_state, settings
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
    moved,
    normalized,
    note_current_page,
    opened,
    pinned_to,
    pop_fresh_notice,
    reentered_open_tab,
    refused_at_tab_limit,
    resync_strip,
    spec_for_path,
    store_strip,
    switch_to_queued_tab,
    tab_label,
    valid_tabs,
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


def test_an_unpinned_tab_moves_before_the_named_tab_or_to_the_end() -> None:
    """끌어서 차례 바꾸기(2026-11-02 사용자 요청). `before` 는 위치 번호가 아니라 탭 id 라 그 사이
    닫힘·새 탭에도 뜻이 남는다. 없거나 모르는 `before` 는 끝이다."""
    strip = _strip(H, A, B, C)

    assert moved(strip, C, A).paths == (H, C, A, B)
    assert moved(strip, A, C).paths == (H, B, A, C)
    assert moved(strip, A, None).paths == (H, B, C, A)
    assert moved(strip, A, "app_pages/gone.py").paths == (H, B, C, A)
    # 옮긴 뒤에도 고정은 그대로다.
    assert moved(strip, C, A).pinned == frozenset({H})


def test_pinned_tabs_never_move_and_nothing_moves_in_front_of_them() -> None:
    """고정 탭은 끌지 않는다. 고정하지 않은 탭을 고정 탭 앞에 놓아도 고정 묶음 바로 뒤에 선다."""
    strip = _strip(H, C, A, B, pinned=(H, C))

    assert moved(strip, H, None) == strip
    assert moved(strip, C, B) == strip
    assert moved(strip, B, H).paths == (H, C, B, A)
    assert moved(strip, B, C).paths == (H, C, B, A)
    # 없는 탭·자기 앞은 그대로다.
    assert moved(strip, "app_pages/gone.py", A) == strip
    assert moved(strip, A, A) == strip


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
    """가짜 `st` — 세션·주소 인자와 `st.switch_page`·`st.rerun` 기록."""
    fake = SimpleNamespace(session_state={}, query_params={}, switched=[], reruns=0, missing=False)

    def switch_page(page: str, *, query_params: dict[str, str] | None = None) -> None:
        if fake.missing:
            raise StreamlitPageNotFoundError(page, "", False)
        fake.switched.append((page, query_params))

    def rerun() -> None:
        fake.reruns += 1

    fake.switch_page = switch_page
    fake.rerun = rerun
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


def test_a_resync_raises_only_the_epoch(session: SimpleNamespace) -> None:
    """탭 줄 JS 의 그림이 서버 목록과 어긋난 때 — 목록은 그대로 두고 epoch 만 올려 다음 data 가
    달라지게 한다(같은 data 면 부품 함수가 다시 불리지 않아 어긋난 그림이 남는다)."""
    store_strip(_strip(H, A))
    first = session.session_state[PAGE_TABS_EPOCH_KEY]

    resync_strip()

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

    # 같은 화면에 머무는 동안 표지는 그대로다 — 다시 들어온 첫 회차가 끊겨도 다음 회차가 이어 본다.
    note_current_page(H, page_changed=False)
    assert reentered_open_tab(H)

    note_current_page(A, page_changed=True)
    assert reentered_open_tab(A) and not reentered_open_tab(H)


def test_a_reentry_survives_an_interrupted_first_run_until_the_page_changes(
    session: SimpleNamespace,
) -> None:
    """이미 연 탭으로 돌아온 첫 회차가 끊기면 다음 회차는 같은 화면(`page_changed=False`)이다. 그
    회차에서 표지를 지우면 공정 Capa 상세가 새 방문으로 보고 출처 띠·설비 방문 기준을 걷는다."""
    store_strip(_strip(H, A, B))
    note_current_page(A, page_changed=True)
    assert reentered_open_tab(A)
    note_current_page(A, page_changed=False)
    note_current_page(A, page_changed=False)
    assert reentered_open_tab(A)

    # 새로 연 화면은 머무는 동안에도 표지가 없다.
    note_current_page(C, page_changed=True)
    note_current_page(C, page_changed=False)
    assert not reentered_open_tab(C)
    assert session.session_state[PAGE_TABS_REENTRY_KEY] is None


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


def test_a_page_helper_is_refused_before_moving_when_the_strip_is_full(
    session: SimpleNamespace,
) -> None:
    """화면을 옮기는 도우미는 옮기기 전에 상한을 본다 — 걸리면 알림을 남기고 앱 전체를 다시
    돌린다(옮긴 뒤 되돌리면 브라우저 기록에 두 화면이 쌓여 뒤로가기가 갇힌다)."""
    detail = PROCESS_CAPA_DETAIL.path
    # 아직 목록이 없는 회차(첫 회차·단독 실행)는 막지 않는다.
    assert not refused_at_tab_limit(detail)

    paths = tuple(spec.path for spec in ALL_SPECS if spec.path != detail)[:MAX_TABS]
    store_strip(_strip(*paths))
    assert not refused_at_tab_limit(paths[4])
    assert session.reruns == 0 and PAGE_TABS_NOTICE_KEY not in session.session_state

    assert refused_at_tab_limit(detail)
    assert session.reruns == 1
    assert session.switched == []
    notice = pop_fresh_notice()
    assert notice is not None
    assert f"「{tab_label(PROCESS_CAPA_DETAIL)}」" in notice[1]
    assert "안 쓰는 탭을 닫아 주세요" in notice[1]

    store_strip(_strip(*paths[:-1]))
    assert not refused_at_tab_limit(detail)
    assert session.reruns == 1


# ------------------------------------------------------------------ 사내 모듈 화면

DEMO_OK_PAGE = "tests/fixtures/modules/demo_ok/demo_ok_page.py"


@pytest.fixture
def fixture_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parent / "fixtures" / "modules"
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(root))


def test_a_module_page_tab_is_a_repository_relative_path(fixture_modules: None) -> None:
    """탭 id 는 브라우저로 나간다 — 서버 경로(사용자 폴더)가 아니라 저장소 상대 경로다."""
    assert DEMO_OK_PAGE in valid_tabs()
    assert not any(str(settings.PROJECT_ROOT) in path for path in valid_tabs())
    spec = spec_for_path(DEMO_OK_PAGE)
    assert spec is not None and spec.module == "demo_ok"
    assert tab_label(spec) == "데모 화면"
    # 꺼진·실패한 모듈의 화면은 탭이 될 수 없다.
    assert not any("demo_off" in path or "demo_future" in path for path in valid_tabs())


def test_a_module_outside_the_repository_keeps_an_absolute_tab_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder = tmp_path / "modules" / "demo_a"
    folder.mkdir(parents=True)
    (folder / "page.py").write_text("# Purpose: 시험.\n", encoding="utf-8")
    declared = {
        "id": "demo_a",
        "name": "시험",
        "api": 1,
        "owner": "시험 담당",
        "enabled": True,
        "maturity": "L2",
        "pages": [{"slug": "main", "file": "page.py", "title": "밖 화면"}],
    }
    (folder / "module.json").write_text(json.dumps(declared, ensure_ascii=False), "utf-8")
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(tmp_path / "modules"))

    assert (folder / "page.py").as_posix() in valid_tabs()


def test_noting_a_module_page_adds_its_tab(session: SimpleNamespace, fixture_modules: None) -> None:
    note_current_page(H, page_changed=True)
    note_current_page(DEMO_OK_PAGE, page_changed=True)

    assert session.session_state[PAGE_TABS_OPEN_KEY] == (H, DEMO_OK_PAGE)


def test_a_queued_module_tab_is_switched_to(
    session: SimpleNamespace, fixture_modules: None
) -> None:
    session.session_state[PAGE_TABS_QUEUED_KEY] = DEMO_OK_PAGE

    switch_to_queued_tab(H)

    assert session.switched == [(DEMO_OK_PAGE, None)]


def test_a_module_page_at_the_limit_is_sent_back_with_a_notice(
    session: SimpleNamespace, fixture_modules: None
) -> None:
    paths = tuple(spec.path for spec in ALL_SPECS)[:MAX_TABS]
    store_strip(_strip(*paths))

    switch_to_queued_tab(DEMO_OK_PAGE, current_title="데모 화면", previous_path=paths[1])

    assert session.switched == [(paths[1], None)]
    notice = pop_fresh_notice()
    assert notice is not None and "「데모 화면」" in notice[1]


def test_the_tab_index_is_built_once_for_the_same_declarations(fixture_modules: None) -> None:
    first = navigation.runtime_specs()
    assert valid_tabs() is valid_tabs()
    assert navigation.runtime_specs() is first
    assert len(first) == len(ALL_SPECS) + 5


def test_without_modules_the_tabs_are_the_core_declarations() -> None:
    assert navigation.runtime_specs() is ALL_SPECS
    assert valid_tabs() == frozenset(spec.path for spec in ALL_SPECS)
