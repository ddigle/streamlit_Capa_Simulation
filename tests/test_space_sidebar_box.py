# Purpose: Space 현황 사이드바 「Space 도면」 상자의 자리·위젯 key·본문 걷기를 검사한다.

"""2026-11-03 사용자 요청 — 레이아웃 위 요소 넷(일정 없는 호기 대수·계산 제외 설명 / `S.PKG FAB
전체` › 층 / `배치 편집` / `공식과 견주기`)을 사이드바 조회 조건 상자 꼴로 옮기고 불필요한 여백을
걷는다.

- 상자는 조회 조건 패널 바로 밑 · `Space 조건` 카드 **위**다(사이드바는 부른 차례 — 호기 없는 화면도
  같다).
- 안의 위젯 key 는 옮기기 전 그대로다(세션 값·화면 확인 `check_deploy_screens` 가 산다).
- 본문에는 경로 줄(`space_path`)·머리 줄(`space_fab_head`·`space_floor_head`)·편집 캡션이 없다.
  도면은 늘 서는 칸 (`space_fab_stage`·`space_floor_stage`) 안이다.
- 상자에 「캔버스 편집」 단추가 없다 — 캔버스는 「배치 편집」 왼쪽 칸 「캔버스」 다(2026-11-12
  Space 보드 답 1-4). 자리 줄 밑은 줄마다 위젯 하나(가로 줄은 자리 줄 하나)이고, 설비 저장본이 없는
  층에도 꺼진 「배치 편집」 이 선다(줄 수가 화면마다 같다).
- 상자에는 조작(자리 · 도면 · 견주기)만 둔다 — 상자 끝에 서던 배치 줄 · 일정 없는 호기 줄은 상태
  알림이다(2026-11-04 Space 결정 보드 답 — `EQ-13` ~ `EQ-15` · `EQ-04`).
- Space 화면 팝업 호스트(필요 단축 보기 목표 확보율)는 화면 팝업 호스트 프래그먼트다 — 여닫아도
  페이지를 다시 돌리지 않는다(2026-11-08 사용자 결정 U5).
- 공정소분류는 조회 조건 패널의 공용 공정 칸이다(2026-11-08 사용자 답 P1).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from alert_marks import active_state, states
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
from test_process_field import process_marks, share

from capa_simulation.components.equipment_scenario_status import unscheduled_notice
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.process_field import CONTEXT_KEY
from capa_simulation.components.process_field import FIELD_KEY as PROCESS_FIELD_KEY
from capa_simulation.components.sample_data import NO_UNITS_MARK, SAMPLE_TOGGLE_KEY
from capa_simulation.components.space_layout_editor import space_lock_style
from capa_simulation.components.space_shortening_view import (
    LEVEL_FIELD_KEY,
    LEVEL_PICK_KEY,
    SPACE_DIALOG_HOST,
    SPACE_DIALOG_KEY,
)
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


def _canvas_buttons(node: Block) -> set[str]:
    """걷은 「캔버스 편집」 단추 key(`space_floor_layout_open_<범위>`)."""
    return {key for key in _keys_in(node, "button") if key.startswith("space_floor_layout_")}


def _box_order(node: Block) -> list[str]:
    """상자 안 위젯 key(화면 차례, 칸 안까지)와 key 를 준 칸(`[칸 key]`)."""
    order: list[str] = []
    for child in node.children.values():
        if isinstance(child, Block):
            identifier = str(getattr(child.proto, "id", "") or "")
            if identifier.startswith("$$ID-"):
                order.append(f"[{identifier.rsplit('-', 1)[-1]}]")
            order += _box_order(child)
        elif getattr(child, "key", None):
            order.append(str(child.key))
    return order


def _compare_at(order: list[str]) -> int:
    """「공식과 견주기」 토글(켜는 짝 또는 잠긴 짝)의 자리."""
    return next(
        index
        for index, key in enumerate(order)
        if key in {"space_compare_official_v1", "space_compare_official_locked_v1"}
    )


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
    # 테두리는 조회 조건 패널(`border=True`)과 같은 1px 선이다 — 같은 사이드바 꼴(검수 2026-11-03).
    assert box.proto.flex_container.border
    assert "space_status_fab_breadcrumb" in _keys_in(box, "button")
    # 「캔버스 편집」 단추는 없다 — 캔버스는 「배치 편집」 왼쪽 칸 「캔버스」 다(2026-11-12 Space
    # 보드 답 1-4).
    assert not _canvas_buttons(box)
    # 줄 이름 「자리」 · 「도면」 은 없다 — 단추 · 고르기 칸 글이 하는 일을 말한다(2026-11-09 사용자
    # 검수 P1-5 「space 도면 박스에서는 자리, 도면 문구 제거해」).
    assert not {"자리", "도면"} & set(_texts(box, "caption"))
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
    assert not _canvas_buttons(box)
    assert "space_status_floor_jump_C1-1F" in _keys_in(box, "selectbox")
    assert "space_layout_edit_mode" in _keys_in(box, "toggle")
    main = _main_keys(app)
    assert "space_floor_stage" in main and "space_fab_stage" not in main
    assert not {"space_path", "space_fab_head", "space_floor_head"} & set(main)
    # 층 화면에는 머리 줄 「… 상세 레이아웃」 제목이 없다 — 지금 층은 편집기 도구 줄 제목이 말한다.
    assert not any("상세 레이아웃" in str(item.value) for item in app.markdown)
    # 줄마다 위젯 하나 — 가로 줄은 자리 줄 하나이고, 그 밑은 배치 편집 → 견주기 차례다(보드 답 1-4
    # 「각 버튼의 간격 일정하게」 — 줄 사이는 Streamlit 기본 칸 틈 그대로).
    order = _box_order(_box(app))
    assert [key for key in order if key.startswith("[")] == ["[space_box_place_row]"]
    edit_at = order.index("space_layout_edit_mode")
    assert order.index("space_status_floor_jump_C1-1F") < edit_at < _compare_at(order)

    # 배치 편집을 켜도 편집 캡션(「끌어 놓아 …」)이 본문에 서지 않는다 — 도구 줄 「단축키」 와 Guide
    # 몫이다.
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    _ok(app)
    assert not any("끌어 놓아" in str(item.value) for item in app.caption)
    assert "space_floor_stage" in _main_keys(app)


def test_the_page_draws_the_scroll_lock_style_once_on_fab_and_floor(_shell: AppTest) -> None:
    """도구 줄 「화면 고정」 은 `<html data-space-lock>` 만 단다 — 본문을 실제로 막는 것은 이 화면이
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


def test_no_canvas_popup_opens_from_the_box_on_fab_or_floor(_shell: AppTest) -> None:
    """상자에서 캔버스를 바꾸는 팝업이 열리지 않는다 — 폭 · 높이 칸은 「배치 편집」 왼쪽 칸 하나다
    (2026-11-12 Space 보드 답 1-4 「배치 편집의 캔버스 편집버튼은 지우고」)."""
    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    assert not [item for item in app.button if str(item.label) == "캔버스 편집"]
    app.selectbox(key="space_status_floor_jump_fab").set_value("C1 1F").run()
    _ok(app)
    assert not [item for item in app.button if str(item.label) == "캔버스 편집"]
    assert not [item for item in app.number_input if item.label == "캔버스 폭"]


def test_an_assumption_raises_the_unscheduled_and_layout_alerts_and_keeps_the_box_to_controls(
    _shell: AppTest, tmp_path: Path
) -> None:
    """함께 넣기를 끄고 공식에 넣은 새 호기는 가정 설비 시나리오에 일정이 없다 — 상태 알림
    `EQ-04`(가용설비 현황과 같은 코드 · 범위 · 내용 — 설비명 목록)이고 배치 차이(「가정 배치 ·
    공식과 같음」)는 `EQ-13` 이다. 상자에는 그 줄이 없다(2026-11-04 Space 결정 보드 답 — 상자에는
    조작만). FAB 자리의 「공식으로 바꾸기」 는 상자 안이다. 공식으로 돌아오면 두 알림이 해소된다."""
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
    unscheduled = active_state(app, "EQ-04")
    assert unscheduled is not None
    assert unscheduled["short"] == (
        "이 설비 시나리오에 일정이 없는 호기 1대 — 도면 · 계산에서 빠짐 · 설비 마스터 일정 칸에 "
        "적어 저장"
    )
    assert unscheduled["full"] == unscheduled_notice(1)
    # 「그 화면으로」 는 고칠 자리인 가용설비 현황 › 설비 마스터다 — 가용설비 현황이 내는 줄과 같아
    # Space 가 먼저 내도 줄이 Space 로 굳지 않는다(재검 b-3 · c-3).
    assert (unscheduled["page"], unscheduled["href"], unscheduled["tab"]) == (
        "가용설비 현황",
        "available_equipment_status",
        "설비 마스터",
    )
    layout = active_state(app, "EQ-13")
    assert layout is not None and layout["short"] == "가정 배치 · 공식과 같음"
    assert layout["full"].startswith("가정 설비 시나리오 · 배치는 공식과 같습니다")
    assert layout["level"] == "info"
    # 모듈 구성이 바뀐 묶음 · 지운 호기의 차이는 없어도 회차마다 해소로 부른다(표지 자리 수가 같다).
    for code in ("EQ-14", "EQ-15"):
        notes = states(app, code)
        assert notes and not any(note["active"] for note in notes), notes
    assert "space_switch_to_official" in _keys_in(box, "button")
    # 상자 · 본문 어디에도 그 줄이 없다 — 상자 안 캡션은 조작 줄의 것뿐이다.
    for node in (box, app.main):
        captions = _texts(node, "caption")
        assert not any("일정 없는 호기" in text or "가정 배치" in text for text in captions)
        assert not any("공식 일정 없음" in text for text in captions)

    _select(app, OPERATIONS, None)
    _ok(app.run())
    assert active_state(app, "EQ-04") is None and active_state(app, "EQ-13") is None
    assert states(app, "EQ-04") and states(app, "EQ-13")


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
    assert NO_UNITS_MARK in _texts(app.sidebar, "caption")

    keys = _sidebar_keys(app)
    assert keys.index(CONDITIONS_BOX_KEY) < keys.index(BOX_KEY) == keys.index(CARD_KEY) - 1
    assert "space_status_fab_breadcrumb" in _keys_in(_box(app), "button")


def test_a_floor_without_saved_units_keeps_a_locked_layout_toggle_row(_empty_app: AppTest) -> None:
    """설비 저장본이 없는 층(호기 없음 · 샘플 화면)에도 도면 줄이 선다 — 꺼진 「배치 편집」 과 까닭
    풍선이다. 「캔버스 편집」 단추를 걷어 그 줄이 비면 이 화면에서만 상자가 한 줄 짧아진다(설계 규칙
    UI-PRF-03 — 줄 수와 자리가 화면마다 같다)."""
    app = _ok(_empty_app.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    if app.toggle(key=SAMPLE_TOGGLE_KEY).value:
        app.toggle(key=SAMPLE_TOGGLE_KEY).set_value(False).run()
        _ok(app)
    app.selectbox(key="space_status_floor_jump_fab").set_value("C1 1F").run()
    _ok(app)
    locked = _box(app).toggle(key="space_layout_edit_mode_locked")
    assert locked.disabled and locked.value is False
    assert str(locked.help) == "설비 마스터를 저장한 뒤 배치를 편집합니다."
    order = _box_order(_box(app))
    assert (
        order.index("space_status_floor_jump_C1-1F")
        < order.index("space_layout_edit_mode_locked")
        < _compare_at(order)
    )

    app.toggle(key=SAMPLE_TOGGLE_KEY).set_value(True).run()
    _ok(app)
    locked = _box(app).toggle(key="space_layout_edit_mode_locked")
    assert locked.disabled
    assert str(locked.help) == "샘플 데이터를 보는 중에는 배치를 고치지 않습니다."


def test_the_runbook_space_lines_name_the_box_and_not_the_old_head() -> None:
    """런북 7장의 Space 줄은 합친 화면 자리로 말한다 — 사내 에이전트는 새 ZIP 화면에서
    7장 글을 그대로 찾는다(2026-11-03 합친 판 재검). 배치 줄 · 일정 없는 호기 줄은 「Space 도면」
    상자가 아니라 알림창 · Alarm(`EQ-13` · `EQ-04`)으로 갔고 층 CSV 는 「호기 정보」 창 제목 줄
    `CSV` 다(2026-11-04 Space 결정 보드 답). 자리 줄 첫 단추는 `FAB 전체` 다 — 옛 단추
    `S.PKG FAB 전체` 는 「옛 경로 줄」 로만 말한다."""
    runbook = (PROJECT_ROOT / "docs" / "internal_update_runbook.md").read_text(encoding="utf-8")
    chapter = " ".join(runbook.split("\n## 7. ", 1)[1].split("\n## 8. ", 1)[0].split())
    assert "머리 「가정 설비 시나리오" not in chapter
    page = (PROJECT_ROOT / "app_pages" / "space_status.py").read_text(encoding="utf-8")
    assert '"FAB 전체",' in page and '"S.PKG FAB 전체"' not in page
    old_names = [found.start() for found in re.finditer(r"`S\.PKG FAB 전체`", chapter)]
    assert all(chapter[:start].endswith("옛 경로 줄 ") for start in old_names), old_names
    for gone in (
        "「Space 도면」 상자의 배치 줄",
        "상자 배치 줄 「가정 배치",
        "층 CSV 내려받기 한 줄은 남았다",
    ):
        assert gone not in chapter, gone
    assert "오른쪽 아래 알림창 「가정 배치 · 공식과 같음」" in chapter


# ------------------------------------------------------------------ 공용 공정 칸(P1)


def test_the_process_field_follows_the_shared_value_and_marks_a_missing_name(
    _shell: AppTest,
) -> None:
    """공정소분류는 조회 조건 패널의 공용 공정 칸이다(2026-11-08 사용자 답 P1) — 카드 안 칩 칸이
    없고, 다른 화면(HOME)에서 고른 공정을 따라가 이름 줄에 「HOME 에서」 가 선다. 글자는 원본
    공정소분류다(2026-10-24 D10 · D11). 본문 위 칩은 없다(2026-11-09 보드 C1 (라) — 머리 띠 칩 · 탭
    표지). 이 화면에 없는 공정이면 전체를 보이고 값은 지우지 않는다 — 이름 줄 배지 없이 값 칸 표지가
    그 공정을 실어 머리 칩이 「1개 이 화면 없음」 으로 말한다(P1-6)."""
    app = _ok(_shell.run())
    _ok(app.switch_page(SPACE_STATUS.path).run())
    assert not _keys_in(_box(app), "multiselect")
    assert "space_status_process_filter" not in {
        str(widget.key) for widget in app.sidebar.multiselect
    }
    options = list(app.session_state[CONTEXT_KEY].options)
    assert options, "Space 공정소분류 선택지가 없다"
    field = app.sidebar.button(key=PROCESS_FIELD_KEY)
    assert field.label == f"전체 {len(options)}공정"
    assert not [b for b in app.button if str(b.key).startswith("shared_process_chip")]

    share(app, [options[0]])
    _ok(app.run())
    shown = literal_markdown(options[0])
    assert app.sidebar.button(key=PROCESS_FIELD_KEY).label == shown
    assert "HOME 에서" in _texts(app.sidebar, "caption")
    assert not [b for b in app.button if str(b.key).startswith("shared_process_chip")]
    assert app.session_state[CONTEXT_KEY].selected == (options[0],)

    share(app, ["DEMO-없는-공정"])
    _ok(app.run())
    assert app.sidebar.button(key=PROCESS_FIELD_KEY).label == f"전체 {len(options)}공정"
    assert not [text for text in _texts(app.sidebar, "caption") if "orange-badge" in text]
    (mark,) = process_marks(app)
    assert mark["here"] == {
        "on": False,
        "follows": True,
        "inside": [],
        "missing": ["DEMO-없는-공정"],
    }
    assert mark["tab"]["miss"] is True


# ------------------------------------------------------------------ Space 화면 팝업 호스트(U5)


def _target_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[AppTest, Any]:
    """색 기준 「필요 단축」 으로 C1 1F 를 연 Space 페이지 — 앱 전체 회차 표지(`app.py` 처럼)를
    두르고 프래그먼트 회차를 흉내 내는 브라우저 대역을 단다."""
    from fragment_browser import install_fragment_browser
    from test_equipment_pages import _page_script, _wide_floor_with_hidden_units

    from capa_simulation.navigation import SPACE_COLOR_BASIS_KEY
    from capa_simulation.services.space_color_basis import COLOR_BASIS_SHORTENING

    database = tmp_path / "space_dialog_host.duckdb"
    _wide_floor_with_hidden_units(database)
    page = PROJECT_ROOT / "app_pages" / "space_status.py"
    script = (
        "from capa_simulation.sidebar_status import begin_app_run\n"
        "app_run = begin_app_run()\n" + _page_script(page, database) + "\napp_run.finish()\n"
    )
    browser = install_fragment_browser(monkeypatch)
    app = AppTest.from_string(script, default_timeout=120)
    app.session_state["space_status_selected_building"] = "C1"
    app.session_state["space_status_selected_floor"] = "1F"
    app.session_state[SPACE_COLOR_BASIS_KEY] = COLOR_BASIS_SHORTENING
    return _ok(app.run()), browser


def test_opening_and_closing_the_target_dialog_runs_only_the_space_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Space 화면 팝업(필요 단축 보기의 목표 확보율)을 여닫아도 페이지를 다시 계산하지 않는다 — 값
    칸의 여는 콜백 뒤 호스트(`space_dialog_host`)만 돌고 닫기(X · 바깥 · Esc)도 호스트만
    돈다(2026-11-08 사용자 결정 U5, 설계 규칙 UI-PRF-01). 닫으면 라디오 값을 지워 다시 열면 지금
    목표로 선다."""
    from capa_simulation.components.dialog_host import WIDGET_KEYS_SUFFIX

    app, browser = _target_app(tmp_path, monkeypatch)
    host = browser.fragment_keyed(SPACE_DIALOG_HOST.key)
    assert LEVEL_FIELD_KEY in {str(button.key) for button in app.sidebar.button}

    app.button(key=LEVEL_FIELD_KEY).click().run()
    _ok(app)
    assert browser.started == [[], [host]]
    assert all(
        message.delta.fragment_id
        for message in browser.messages
        if message.WhichOneof("type") == "delta"
    ), "페이지가 다시 돌았다"
    assert app.session_state[SPACE_DIALOG_KEY] == "space_target_level"
    assert app.radio(key=LEVEL_PICK_KEY).value == 1.1

    browser.send_trigger(app, browser.dialog_widget_id(), [host])
    _ok(app)
    assert browser.started == [[host]]
    for key in (SPACE_DIALOG_KEY, LEVEL_PICK_KEY, f"{SPACE_DIALOG_HOST.key}{WIDGET_KEYS_SUFFIX}"):
        assert key not in app.session_state, key
