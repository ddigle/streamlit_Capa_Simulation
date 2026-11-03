# Purpose: Space 현황 사이드바 「Space 도면」 상자의 자리·위젯 key·본문 걷기를 검사한다.

"""2026-11-03 사용자 요청 — 레이아웃 위 요소 넷(일정 없는 호기 대수·계산 제외 설명 / `S.PKG FAB
전체` › 층 / `도면·캔버스 편집`·`배치 편집` / `공식과 견주기`)을 사이드바 조회 조건 상자 꼴로 옮기고
불필요한 여백을 걷는다.

- 상자는 조회 조건 패널 바로 밑 · `Space 조건` 카드 **위**다(사이드바는 부른 차례 — 호기 없는 화면도
  같다).
- 안의 위젯 key 는 옮기기 전 그대로다(세션 값·화면 확인 `check_deploy_screens` 가 산다).
- 본문에는 경로 줄(`space_path`)·머리 줄(`space_fab_head`·`space_floor_head`)·편집 캡션이 없다.
  도면은 늘 서는 칸 (`space_fab_stage`·`space_floor_stage`) 안이다.
- 도면·캔버스 팝업은 사이드바 단추가 열림 칸만 적고 본문 호스트가 연다(사이드바 `with` 안에서 열지
  않는다).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block
from test_equipment_scenario_repository import (
    OPERATIONS,
    _clone,
    _request,
    _session,
    _with_unit,
)
from test_equipment_scenario_screens import _ok, _repository, _select, _shell

from capa_simulation.components.equipment_scenario_status import unscheduled_notice
from capa_simulation.components.sample_data import SAMPLE_TOGGLE_KEY
from capa_simulation.components.space_layout_editor import space_lock_style
from capa_simulation.navigation import SPACE_STATUS
from capa_simulation.sidebar_status import CONDITIONS_BOX_KEY, PAGE_BOX_PREFIX, page_box_key

__all__ = ["_shell"]

BOX_KEY = page_box_key("space")
CARD_KEY = "condition_card_space"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sidebar_keys(app: AppTest) -> list[str]:
    """사이드바 **최상위** 칸의 key(화면 차례). key 를 준 컨테이너·확장 패널은 id 끝이 그 key 다."""
    keys: list[str] = []
    for node in app.sidebar.children.values():
        identifier = str(getattr(getattr(node, "proto", None), "id", "") or "")
        keys.append(identifier.rsplit("-", 1)[-1] if identifier else "")
    return keys


def _box(app: AppTest) -> Block:
    keys = _sidebar_keys(app)
    assert BOX_KEY in keys, keys
    node = list(app.sidebar.children.values())[keys.index(BOX_KEY)]
    assert isinstance(node, Block)
    return node


def _keys_in(node: Block, kind: str) -> set[str]:
    return {str(widget.key) for widget in node.get(kind) if getattr(widget, "key", None)}


def _texts(node: Block, kind: str) -> list[str]:
    """그 칸 안 `kind` 요소의 글(`value`) — 블록은 건너뛴다."""
    return [str(getattr(item, "value", "")) for item in node.get(kind)]


def _main_keys(app: AppTest) -> list[str]:
    """본문 맨 윗단 칸의 key(없으면 빈 글)."""
    keys: list[str] = []
    for node in app.main.children.values():
        identifier = str(getattr(getattr(node, "proto", None), "id", "") or "")
        keys.append(identifier.split("-", 2)[-1] if identifier.startswith("$$ID-") else "")
    return keys


def test_the_box_key_is_a_page_box_prefix() -> None:
    assert BOX_KEY == f"{PAGE_BOX_PREFIX}space" == "sidebar_page_box_space"


def test_the_space_box_stands_under_the_panel_and_above_the_card_on_fab_and_floor(
    _shell: AppTest,
) -> None:
    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())

    keys = _sidebar_keys(app)
    assert keys.index(CONDITIONS_BOX_KEY) < keys.index(BOX_KEY) == keys.index(CARD_KEY) - 1
    box = _box(app)
    assert {"space_status_fab_breadcrumb", "space_floor_layout_open_FAB"} <= _keys_in(box, "button")
    assert "space_status_floor_jump_fab" in _keys_in(box, "selectbox")
    toggles = _keys_in(box, "toggle")
    assert "space_fab_edit_mode" in toggles
    assert toggles & {"space_compare_official_v1", "space_compare_official_locked_v1"}
    assert not _keys_in(app.main, "toggle") & toggles
    main = _main_keys(app)
    assert "space_fab_stage" in main
    assert not {"space_path", "space_fab_head", "space_floor_head"} & set(main)

    app.selectbox(key="space_status_floor_jump_fab").set_value("C1 1F").run()
    _ok(app)
    keys = _sidebar_keys(app)
    assert keys.index(BOX_KEY) == keys.index(CARD_KEY) - 1
    box = _box(app)
    assert "space_floor_layout_open_C1_1F" in _keys_in(box, "button")
    assert "space_status_floor_jump_C1-1F" in _keys_in(box, "selectbox")
    assert "space_layout_edit_mode" in _keys_in(box, "toggle")
    main = _main_keys(app)
    assert "space_floor_stage" in main and "space_fab_stage" not in main
    assert not {"space_path", "space_fab_head", "space_floor_head"} & set(main)
    # 층 화면에는 머리 줄 「… 상세 레이아웃」 제목이 없다 — 지금 층은 편집기 도구 줄 제목이 말한다.
    assert not any("상세 레이아웃" in str(item.value) for item in app.markdown)
    # 「도면·캔버스 편집」 은 아이콘 없이 「배치 편집」 토글과 한 줄에 선다(리뷰 browser-2 —
    # 아이콘을 달면 245px 상자에서 둘째 줄로 감겨 아래 견주기가 첫 화면 밖으로 밀렸다).
    assert not _box(app).button(key="space_floor_layout_open_C1_1F").proto.icon

    # 배치 편집을 켜도 편집 캡션(「끌어 놓아 …」)이 본문에 서지 않는다 — 왼쪽 칸 「도움말」 과 Guide
    # 몫이다.
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    _ok(app)
    assert not any("끌어 놓아" in str(item.value) for item in app.caption)
    assert "space_floor_stage" in _main_keys(app)


def test_the_page_draws_the_scroll_lock_style_once_on_fab_and_floor(_shell: AppTest) -> None:
    """도구 줄 「고정」 은 `<html data-space-lock>` 만 단다 — 본문을 실제로 막는 것은 이 화면이
    그리는 페이지 서식(`space_lock_style`)이다. 그 한 줄이 빠지면 단추는 켜져도 본문이 굴러가고,
    다른 화면으로 가면 서식이 사라져 풀리는 규칙도 없다(리뷰 rules-7). FAB·층·편집 모두 한 번씩."""

    def lock_styles(app: AppTest) -> list[str]:
        return [
            str(element.proto.body)
            for element in app.get("html")
            if 'html[data-space-lock="1"] [data-testid="stMain"]' in str(element.proto.body)
        ]

    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    assert lock_styles(app) == [space_lock_style()]
    app.selectbox(key="space_status_floor_jump_fab").set_value("C1 1F").run()
    _ok(app)
    assert lock_styles(app) == [space_lock_style()]
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    _ok(app)
    assert lock_styles(app) == [space_lock_style()]


def test_the_drawing_popup_opens_from_the_body_host_not_inside_the_sidebar(
    _shell: AppTest,
) -> None:
    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    app.selectbox(key="space_status_floor_jump_fab").set_value("C1 1F").run()
    _ok(app)
    assert len(app.get("file_uploader")) == 0

    _box(app).button(key="space_floor_layout_open_C1_1F").click().run()
    _ok(app)
    assert len(app.get("file_uploader")) == 1
    assert len(_box(app).get("file_uploader")) == 0
    assert len(app.sidebar.get("file_uploader")) == 0


def test_an_assumption_box_carries_the_unscheduled_line_and_the_switch_to_official(
    _shell: AppTest, tmp_path: Path
) -> None:
    """함께 넣기를 끄고 공식에 넣은 새 호기는 가정 설비 시나리오에 일정이 없다 — 상자 끝 한 줄
    「일정 없는 호기 1대 · 계산 제외」 이고 지금 온 문장은 풍선이다. FAB 자리의 「공식으로 바꾸기」
    도 상자 안이다. 공식으로 돌아오면 그 줄이 없다."""
    repository = _repository(tmp_path)
    clone = _clone(repository)
    session = _session(repository)
    repository.save_equipment(
        _request(
            session,
            equipment=_with_unit(session.equipment, "EQ-NEW", 70),
            propagate_new_units=False,
        )
    )
    app = _ok(_shell.run())
    app.switch_page(SPACE_STATUS.path)
    _select(app, clone.equipment_scenario_id, clone.latest_schedule_revision_id)
    _ok(app.run())

    box = _box(app)
    lines = [
        item
        for item in box.get("caption")
        if "일정 없는 호기 1대 · 계산 제외" in str(getattr(item, "value", ""))
    ]
    assert len(lines) == 1
    assert lines[0].proto.help == unscheduled_notice(1)
    assert "space_switch_to_official" in _keys_in(box, "button")
    # 본문 알림 칸에는 그 줄이 없다(옮겼다).
    assert not any("일정 없는 호기" in text for text in _texts(app.main, "caption"))

    _select(app, OPERATIONS, None)
    _ok(app.run())
    assert not any("계산 제외" in text for text in _texts(_box(app), "caption"))


@pytest.fixture
def _empty_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 DuckDB 둘을 보는 `app.py` — 설비 마스터가 비어 샘플 스위치를 끈 「호기 없는
    화면」(no_fleet)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    return AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=300)


def test_the_box_stands_above_the_card_on_a_screen_without_units(_empty_app: AppTest) -> None:
    app = _ok(_empty_app.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    if app.toggle(key=SAMPLE_TOGGLE_KEY).value:
        app.toggle(key=SAMPLE_TOGGLE_KEY).set_value(False).run()
        _ok(app)
    assert any("조회할 호기가 없습니다" in text for text in _texts(app.sidebar, "caption"))

    keys = _sidebar_keys(app)
    assert keys.index(CONDITIONS_BOX_KEY) < keys.index(BOX_KEY) == keys.index(CARD_KEY) - 1
    assert "space_status_fab_breadcrumb" in _keys_in(_box(app), "button")
