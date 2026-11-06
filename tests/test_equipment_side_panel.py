# Purpose: 설비 마스터 한 영역 두 칸 배치·칸막이(폭 끌기·접기·높이 상한)를 자리·서식·node 로 본다.

"""설비 마스터 탭 두 칸 배치(2026-11-02 사용자 결정 — 오른쪽 칸 폭 늘이기·줄이기·최소화, 너비
한계, 넘치면 스크롤. 2026-11-05 검수 — 편집기 영역 안의 서브페이지, 접기 단추는 칸 머리, 접으면
편집기 위에 떠 있는 단추).

AppTest 는 칸막이 JS 를 못 돌린다. 자리(key 칸의 차례)·페이지 서식 한 덩이·칸막이 data 는
AppTest 로, 폭 식·끌기·키는 `splitter.js` 의 순수 구획(`// <splitter-…>`)을 node 로,
마운트(저장값 다시 걸기·접기·펴기·끌기·키·정리)는 파일 전체를 작은 가짜 DOM 에 올려 본다. 실제
폭·sticky·스크롤은 사본 앱 브라우저로 잰다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from grid_fake import Calls, install_fake_grid, last, send
from streamlit.proto.GapSize_pb2 import GapSize
from streamlit.proto.RootContainer_pb2 import RootContainer
from streamlit.testing.v1 import AppTest
from test_equipment_master_grid_assets import _node
from test_equipment_master_tab import _import, _rows
from test_equipment_pages import _page_script

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components import side_panel as sp
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_DETAIL,
    SIDE_HISTORY,
    SIDE_KEY,
    SIDE_NEW,
    SIDE_REVEAL_KEY,
    TABLE_KEY,
)
from capa_simulation.components.page_tabs import EDIT_HOST_KEYS
from capa_simulation.design import tokens
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.services.equipment_bulk_delete import BASELINE_TARGET

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
JS = (sp._ASSETS / "splitter.js").read_text(encoding="utf-8")
CSS = (sp._ASSETS / "splitter.css").read_text(encoding="utf-8")
GRID_CSS = (emg._ASSETS / "grid.css").read_text(encoding="utf-8")
SOURCE = Path(sp.__file__).read_text(encoding="utf-8")
# 마운트 자리를 시험이 보도록 대역이 그 자리에 세우는 빈 key 칸의 앞붙이.
PLACE = "test_place_"


@pytest.fixture(autouse=True)
def _release_repository() -> Iterator[None]:
    yield
    clear_equipment_repository()


# ---------------------------------------------------------------- AppTest — 자리·서식·data


Splits = list[dict[str, Any]]


def _install(monkeypatch: pytest.MonkeyPatch) -> tuple[Calls, Splits]:
    """표·칸막이 대역 — 마운트마다 그 자리에 `PLACE + key` 빈 칸을 세운다(차례를 보려고)."""
    calls = install_fake_grid(monkeypatch)
    fake = emg._GRID

    def placed(**kwargs: Any) -> Any:
        st.container(key=PLACE + str(kwargs["key"]))
        return fake(**kwargs)

    splits: Splits = []

    def splitter(**kwargs: Any) -> None:
        st.container(key=PLACE + str(kwargs["key"]))
        assert not any(name.startswith("on_") for name in kwargs), kwargs
        splits.append(dict(kwargs["data"]))

    monkeypatch.setattr(emg, "_GRID", placed)
    monkeypatch.setattr(sp, "_SPLITTER", splitter)
    return calls, splits


def _app(path: Path) -> AppTest:
    app = AppTest.from_string(_page_script(PAGE, path), default_timeout=60)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.run()
    assert not app.exception, app.exception
    return app


def _keyed(node: Any) -> Iterator[Any]:
    if getattr(node, "key", None):
        yield node
    children = getattr(node, "children", None)
    for child in children.values() if isinstance(children, dict) else ():
        yield from _keyed(child)


def _node_of(app: AppTest, key: str) -> Any:
    (found,) = [node for node in _keyed(app._tree) if node.key == key]
    return found


def _child_keys(node: Any) -> list[str]:
    return [str(getattr(child, "key", None) or "") for child in node.children.values()]


def _descendant_keys(node: Any) -> set[str]:
    return {str(item.key) for item in _keyed(node)}


def _style_slots(app: AppTest) -> list[int]:
    """이벤트 칸에서 두 칸 배치 서식이 선 자리들."""
    event = app._tree.children[RootContainer.EVENT]
    style = emg.side_layout_style()
    return [
        index
        for index, node in event.children.items()
        if getattr(node, "type", "") == "html" and str(node.proto.body) == style
    ]


def _bordered_blocks(node: Any) -> int:
    children = getattr(node, "children", None)
    inside = sum(_bordered_blocks(child) for child in (children or {}).values())
    proto = getattr(node, "proto", None)
    flex = getattr(proto, "flex_container", None)
    return inside + (1 if flex is not None and flex.border else 0)


def test_the_right_column_holds_the_splitter_then_the_choice_then_one_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """테두리 하나의 편집기 영역(`FRAME_KEY`) 안에 key 가로 칸(접지 않음, 간격 없음)이 서고 그 안
    왼쪽·오른쪽 key 칸이다 — 표 구획에 따로 테두리가 없어 오른쪽 칸이 영역 안 서브페이지로 보인다.
    오른쪽 칸은 칸막이 마운트 → 「오른쪽 칸」 고르기 → 본문 칸 차례다. 고른 칸(호기 상세·새 호기·
    저장 전 변경 + 저장 구획·저장 이력)은 모두 본문 칸 안이다 — 본문 칸이 높이 상한 안에서
    스크롤하고 칸막이·고르기는 그 위에 남는다(명세 15-3)."""
    calls, _ = _install(monkeypatch)
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01", "DA-02"))

    frame = _node_of(app, emg.FRAME_KEY)
    assert frame.proto.flex_container.border
    assert _child_keys(frame) == [emg.SPLIT_KEY]
    split = _node_of(app, emg.SPLIT_KEY)
    flex = split.proto.flex_container
    assert flex.direction == flex.HORIZONTAL and not flex.wrap
    # 간격 없음 — 경계선 양쪽 여백은 서식이 둔다(`SIDE_INSET_PX`).
    assert GapSize.Name(flex.gap_config.gap_size) == "NONE"
    assert _child_keys(split) == [emg.LEFT_KEY, emg.RIGHT_KEY]
    assert _bordered_blocks(_node_of(app, emg.LEFT_KEY)) == 0
    assert emg.TOOLS_KEY in _descendant_keys(_node_of(app, emg.LEFT_KEY))
    assert SIDE_KEY == emg.SIDE_CHOICE_KEY
    right = _node_of(app, emg.RIGHT_KEY)
    assert _child_keys(right) == [PLACE + emg.SPLITTER_KEY, SIDE_KEY, emg.SIDE_BODY_KEY]
    assert PLACE + emg.GRID_KEY in _descendant_keys(_node_of(app, emg.LEFT_KEY))

    def body() -> Any:
        return _node_of(app, emg.SIDE_BODY_KEY)  # 회차마다 새 나무

    assert _child_keys(body())[0] == PLACE + emg.side_key("detail")

    app.session_state[SIDE_KEY] = SIDE_NEW
    app.run()
    assert not app.exception, app.exception
    assert _child_keys(body())[0] == PLACE + emg.side_key("new")

    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    assert not app.exception, app.exception
    assert _child_keys(body())[0] == PLACE + emg.side_key("changes")
    assert SAVE_BUTTON_KEY in _descendant_keys(body())
    assert _child_keys(_node_of(app, emg.RIGHT_KEY)) == [
        PLACE + emg.SPLITTER_KEY,
        SIDE_KEY,
        emg.SIDE_BODY_KEY,
    ]

    app.session_state[SIDE_KEY] = SIDE_HISTORY
    app.run()
    assert not app.exception, app.exception
    # 저장 이력(저장본이 없으면 안내 한 줄)도 본문 칸 안이고, 오른쪽 칸의 차례는 그대로다.
    assert body().children
    assert _child_keys(_node_of(app, emg.RIGHT_KEY))[1:] == [SIDE_KEY, emg.SIDE_BODY_KEY]
    # 떠나기 붙들기가 보는 설비 마스터 편집 칸 key 는 그대로다(오른쪽 칸 마운트 셋 + 표) — 칸막이는
    # 편집 칸이 아니다. 다른 화면의 편집 칸(기준 정보 그리드)은 이 시험이 보지 않는다.
    equipment_hosts = {key for key in EDIT_HOST_KEYS if key.startswith("equipment_")}
    assert equipment_hosts == {emg.GRID_KEY, *(emg.side_key(p) for p in emg.SIDE_PANELS)}
    assert emg.SPLITTER_KEY not in EDIT_HOST_KEYS
    assert last(calls, emg.GRID_KEY)["rows"]


def test_the_layout_style_is_one_event_slot_with_the_same_text_in_every_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """페이지 서식은 스타일만 든 `st.html` 한 덩이라 이벤트 칸으로 간다 — 오른쪽 칸 갈래·표
    고르기와 상관없이 같은 글이 같은 자리 하나에 선다(이벤트 칸 자리가 갈래마다 밀리면 그 뒤
    토스트·팝업 자리가 흔들린다)."""
    _install(monkeypatch)
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01"))
    slots = []
    for side in (SIDE_DETAIL, SIDE_NEW, SIDE_CHANGES, SIDE_HISTORY):
        app.session_state[SIDE_KEY] = side
        app.run()
        assert not app.exception, app.exception
        slots.append(tuple(_style_slots(app)))
    app.session_state[TABLE_KEY] = BASELINE_TARGET
    app.run()
    assert not app.exception, app.exception
    slots.append(tuple(_style_slots(app)))
    assert len(set(slots)) == 1 and len(slots[0]) == 1, slots
    style = emg.side_layout_style()
    # ForwardMsg 캐시 문턱(1,000B — AGENTS 9장) 이상이라 같은 글은 해시 참조로 간다.
    assert len(style.encode("utf-8")) >= 1000
    assert "/*" not in style and "position: fixed" not in style
    assert not re.search(r":has\([^)]*:has\(", style)


# 페이지 서식 읽기 — 한 겹 @media 안팎의 규칙을 (미디어, 선택자) → {속성: 값} 으로.
_MEDIA = re.compile(r"@media ([^{]+?) \{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}")
_RULE = re.compile(r"([^{}]+?)\s*\{([^{}]*)\}")
Rules = dict[tuple[str, str], dict[str, str]]


def _css_rules(style: str) -> Rules:
    assert style.startswith("<style>") and style.endswith("</style>")
    text = style.removeprefix("<style>").removesuffix("</style>")
    rules: Rules = {}
    count = 0

    def take(media: str, chunk: str) -> None:
        nonlocal count
        for selectors, block in _RULE.findall(chunk):
            count += 1
            props = {}
            for declaration in filter(str.strip, block.split(";")):
                name, _, value = declaration.partition(":")
                props[name.strip()] = value.strip()
            for selector in selectors.split(","):
                key = (media, selector.strip())
                assert key not in rules, key
                rules[key] = props

    def media(match: re.Match[str]) -> str:
        take(match.group(1), match.group(2))
        return ""

    rest = _MEDIA.sub(media, text)
    take("", rest)
    # 읽지 못하고 흘린 규칙이 없다 — 여는 괄호 수 = 규칙 수 + @media 수.
    assert text.count("{") == count + text.count("@media"), text
    return rules


def test_the_layout_style_caps_the_body_scrolls_inside_sticks_folds_stacks_and_prints() -> None:
    """사용자 요구의 핵심을 페이지 서식 규칙으로 못 박는다(브라우저 손 확인으로만 잡히던 것) —
    본문 칸은 창 높이 상한 안에서 세로로만 스크롤하고(페이지를 늘리지 않는다), 오른쪽 칸 감싸개는
    붙어 있으며(줄이 스크롤 칸이 되지 않게 `overflow: visible`), 두 칸 경계선은 왼쪽 감싸개의 오른쪽
    테두리라 영역 끝까지 간다. 칸막이 마운트는 경계선부터 칸 오른쪽 끝까지 덮되 눌림을 그대로
    통과시킨다. 접힘은 넓은 화면에서만 칸 자리를 0 으로 만들어 표가 줄을 다 쓰고(칸막이 밖은
    `display: none` — 그려 둔 채 숨김, 다시 마운트 없음) 표 위 작업 줄이 떠 있는 단추 자리를 비운다.
    640px 이하는 위아래로 쌓아 칸막이를 숨기며, 인쇄는 상한·sticky 를 풀어 다 찍는다."""
    rules = _css_rules(emg.side_layout_style())
    wrapper = '[data-testid="stLayoutWrapper"]'
    split = f".st-key-{emg.SPLIT_KEY}"
    left = f".st-key-{emg.LEFT_KEY}"
    right = f".st-key-{emg.RIGHT_KEY}"
    right_item = f"{wrapper}:has(> {right})"
    left_item = f"{wrapper}:has(> {left})"
    splitter = f".st-key-{emg.SPLITTER_KEY}"
    choice = f".st-key-{emg.SIDE_CHOICE_KEY}"
    tools = f".st-key-{emg.TOOLS_KEY}"
    body = f".st-key-{emg.SIDE_BODY_KEY}"
    folded = 'html[data-emd-side="min"]'
    top = f"var(--emd-top, {sp.SIDE_TOP_FALLBACK_PX}px)"
    wide = f"screen and (width > {sp.SIDE_STACK_MAX_PX}px)"
    narrow = f"(width <= {sp.SIDE_STACK_MAX_PX}px)"
    line = f"1px solid {tokens.BORDER}"
    cap = f"max({sp.SIDE_BODY_MIN_PX}px, calc(100vh - {top} - {sp.SIDE_BODY_RESERVE_PX}px))"

    # 본문 칸 — 창 높이 상한 안에서 세로 스크롤(가로 스크롤 없음, 스크롤 막대 자리 고정). 막대
    # 자리는 영역 안쪽 여백으로 내보내 내용 오른쪽 끝이 머리 접기 단추와 맞는다.
    assert rules[("", body)] == {
        "width": f"calc(100% + {sp.SIDE_SCROLLBAR_PX}px)",
        "max-width": "none",
        "max-height": cap,
        "overflow-y": "auto",
        "overflow-x": "hidden",
        "scrollbar-gutter": "stable",
    }
    # 1500×950 측정(붙는 높이 97px) — 본문 칸 653px, 낮은 창에서도 360px 아래로 줄지 않는다.
    assert max(sp.SIDE_BODY_MIN_PX, 950 - 97 - sp.SIDE_BODY_RESERVE_PX) == 653
    assert max(sp.SIDE_BODY_MIN_PX, 500 - 97 - sp.SIDE_BODY_RESERVE_PX) == 360
    # 내용이 짧아도 오른쪽 칸은 머리 + 상한만큼 높이를 잡는다 — 칸을 바꿔도 영역이 뛰지 않는다.
    assert rules[("", right)] == {"min-height": f"calc({cap} + {sp.SIDE_HEAD_PX}px)"}
    # 오른쪽 칸 감싸개 — 폭 한계 안에서 붙는다. 줄은 스크롤 칸이 아니다(아니면 sticky 가 줄 기준).
    assert rules[("", right_item)] == {
        "flex": f"0 0 {emg.side_width_rule()}",
        "min-width": "0",
        "padding-left": f"{sp.SIDE_INSET_PX}px",
        "position": "sticky",
        "top": top,
        "align-self": "flex-start",
    }
    assert rules[("", split)] == {"align-items": "flex-start", "overflow": "visible"}
    # 왼쪽 감싸개 — 줄 높이로 늘어 오른쪽 테두리가 두 칸 경계선이다.
    assert rules[("", left_item)] == {
        "flex": "1 1 0",
        "min-width": "0",
        "align-self": "stretch",
        "padding-right": f"{sp.SIDE_INSET_PX}px",
        "border-right": line,
    }
    # 칸막이 마운트 — 경계선 양쪽 절반부터 칸 오른쪽 끝까지 덮고, 눌림은 칸막이·접기 단추만 받는다.
    assert rules[("", splitter)] == {
        "position": "absolute",
        "top": "0",
        "bottom": "0",
        "left": f"-{sp.SIDE_GUTTER_PX // 2}px",
        "right": "0",
        "width": "auto",
        "min-width": "0",
        "max-width": "none",
        "z-index": "2",
        "pointer-events": "none",
    }
    # 칸 머리 — 고르기 칸이 접기 단추 자리를 비운다.
    assert rules[("", choice)] == {
        "padding-right": f"{sp.SIDE_TOGGLE_PX + sp.SIDE_TOGGLE_GAP_PX}px",
    }
    # 접힘 — 넓은 화면에서만. 칸 자리가 0 이고 표가 줄을 다 쓰며 칸막이(떠 있는 단추) 밖은 숨는다.
    assert rules[(wide, f"{folded} {right} > :not({splitter})")] == {"display": "none"}
    assert rules[(wide, f"{folded} {right}")] == {"min-height": "0"}
    assert rules[(wide, f"{folded} {right_item}")] == {
        "flex-basis": "0",
        "width": "0",
        "padding-left": "0",
        "z-index": str(sp.SIDE_REOPEN_Z_INDEX),
    }
    assert rules[(wide, f"{folded} {left_item}")] == {"padding-right": "0", "border-right": "none"}
    assert rules[(wide, f"{folded} {splitter}")] == {
        "left": "auto",
        "bottom": "auto",
        "width": "0",
        "height": "0",
    }
    assert rules[(wide, f"{folded} {tools}")] == {
        "padding-right": f"{sp.SIDE_REOPEN_RESERVE_PX}px",
    }
    assert not [key for key in rules if key[0] != wide and folded in key[1]]
    # 좁은 창 — 위아래로 쌓고 붙지 않으며 칸막이가 없다. 경계선은 가로로.
    assert rules[(narrow, split)] == {"flex-wrap": "wrap"}
    assert rules[(narrow, right_item)] == {
        "flex": "1 1 100%",
        "position": "static",
        "padding-left": "0",
        "padding-top": f"{sp.SIDE_INSET_PX}px",
        "border-top": line,
    }
    assert rules[(narrow, left_item)] == {
        "flex": "1 1 100%",
        "position": "static",
        "padding-right": "0",
        "border-right": "none",
    }
    assert rules[(narrow, right)] == {"min-height": "0"}
    assert rules[(narrow, splitter)] == {"display": "none"}
    assert rules[(narrow, choice)] == {"padding-right": "0"}
    # 인쇄 — 상한·sticky 를 풀어 다 찍고 칸막이는 찍지 않는다.
    assert rules[("print", right_item)] == {"position": "static"}
    assert rules[("print", right)] == {"min-height": "0"}
    assert rules[("print", body)] == {"width": "100%", "max-height": "none", "overflow": "visible"}
    assert rules[("print", splitter)] == {"display": "none"}
    assert rules[("print", choice)] == {"padding-right": "0"}
    assert {key[0] for key in rules} == {"", wide, narrow, "print"}


def test_the_splitter_names_the_open_panel_and_unfolds_when_the_table_opens_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """칸막이 data — 떠 있는 단추에 쓸 지금 칸 이름, 한계(CSS 와 같은 수), 줄·오른쪽 칸 key, 화면 탭
    줄 선택자. 표에서 설비명을 누르거나(`open`) 불러오기 「+ 새 호기」(`new`)로 오른쪽 칸을 연
    회차에만 `reveal` 이 오른다 — 접혀 있으면 편다(누른 것이 보이게). 다시 그리기·고르기 바꿈은
    올리지 않는다."""
    calls, splits = _install(monkeypatch)
    app = _app(tmp_path / "equipment.duckdb")
    _import(app, _rows("DA-01", "DA-02"))
    first = splits[-1]
    assert first["label"] == SIDE_DETAIL
    assert first["bounds"] == emg.side_bounds()
    assert first["keys"] == {
        "row": emg.SPLIT_KEY,
        "right": emg.RIGHT_KEY,
        "body": emg.SIDE_BODY_KEY,
    }
    # 저장소 · CSS 이름은 그대로다 — 사용자의 폭 기억을 잃지 않는다.
    assert first["names"] == {
        "store": "capa-equipment-side-v1",
        "width": "--emd-side-w",
        "top": "--emd-top",
        "attr": "data-emd-side",
    }
    assert first["cover"] == ".st-key-page_tabs_strip"
    assert set(first["palette"]) == {
        "font",
        "text",
        "muted",
        "surface",
        "border",
        "accent",
    }
    start = first["reveal"]
    app.run()
    assert splits[-1]["reveal"] == start

    view = last(calls, emg.GRID_KEY)["view"]
    send(app, emg.GRID_KEY, "open", {"view": view, "id": "n:DA-02"})
    assert splits[-1]["reveal"] == start + 1
    assert app.session_state[SIDE_REVEAL_KEY] == start + 1
    assert splits[-1]["label"] == SIDE_DETAIL

    send(app, emg.LOADER_KEY, "new", {})
    assert splits[-1]["reveal"] == start + 2
    assert splits[-1]["label"] == SIDE_NEW

    app.session_state[SIDE_KEY] = SIDE_CHANGES
    app.run()
    assert splits[-1]["label"] == SIDE_CHANGES
    assert splits[-1]["reveal"] == start + 2


# ---------------------------------------------------------------- 자산 글


def test_the_splitter_keeps_its_state_in_the_browser_only() -> None:
    """폭·접힘은 브라우저 전용 보기 상태 — 상태 값·트리거로 보내지 않는다(보내면 앱 전체가 다시
    돈다, AGENTS 9장). 저장소는 try 안에서만 만진다(사내 DRM 이 막아도 동작한다)."""
    assert "setStateValue" not in JS and "setTriggerValue" not in JS
    drawn = SOURCE[SOURCE.index("def render_side_splitter") : SOURCE.index("def split_frame")]
    assert "on_" not in drawn
    for match in re.finditer(r"localStorage", JS):
        before = JS[max(match.start() - 80, 0) : match.start()]
        assert "try {" in before, JS[match.start() - 80 : match.end() + 20]
    assert "navigator." not in JS


def test_the_splitter_colours_come_from_the_palette_and_text_goes_in_as_text() -> None:
    used = set(re.findall(r"var\(--ess-([a-z-]+)", CSS))
    assert used <= set(sp.splitter_palette()), used - set(sp.splitter_palette())
    # 페이지 서식에 든 색은 두 칸 경계선의 토큰 `BORDER` 하나다(영역 테두리와 같은 색 — 테마를
    # 따른다).
    for text in (CSS, JS, emg.side_layout_style().replace(tokens.BORDER, "")):
        assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", text)
        assert "rgb(" not in text and "rgba(" not in text
    assert "/*" not in CSS
    assert "position: fixed" not in CSS
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS
    assert "S.railLabel.textContent = S.label" in JS


def _css_block(selector: str) -> dict[str, str]:
    match = re.search(rf"(?m)^{re.escape(selector)} \{{\n(?P<body>[^}}]*)\}}", CSS)
    assert match, selector
    props = {}
    for declaration in filter(str.strip, match.group("body").split(";")):
        name, _, value = declaration.partition(":")
        props[name.strip()] = value.strip()
    return props


def test_the_fold_button_sits_in_the_head_and_the_reopen_button_floats_like_the_tray_tab() -> None:
    """접기 단추는 칸막이 위가 아니라 칸 머리 오른쪽 끝이다 — 고르기와 같은 높이고 고르기가 비운
    자리에 든다. 접으면 옛 Space 미배치 서랍 탭(`.sle-drawer-tab` — 높이 27 · 양옆 10 · 둥글기 8 ·
    13px 600 · 바탕 표면 · 테 한 겹 · 눌러 뜨는 윤곽)과 같은 생김의 단추가 영역 오른쪽 위에서 8px
    들어앉아 뜬다(영역 안쪽 여백 13 + 테 1 안쪽이라 칸 끝에서 −5). 세로 글·화살표가 없다. 눌림은
    칸막이·접기 단추·떠 있는 단추만 받는다."""
    toggle = _css_block(".ess-toggle")
    assert (toggle["position"], toggle["top"], toggle["right"]) == ("absolute", "0", "0")
    assert toggle["width"] == toggle["height"] == f"{sp.SIDE_TOGGLE_PX}px"
    assert toggle["pointer-events"] == "auto"

    rail = _css_block(".ess-rail")
    assert rail == {
        "display": "none",
        "position": "absolute",
        "top": "-5px",
        "right": "-5px",
        "height": "27px",
        "padding": "0 10px",
        "border": "1px solid var(--ess-border)",
        "border-radius": "8px",
        "background": "var(--ess-surface)",
        "color": "var(--ess-text)",
        "font": "600 13px/1 var(--ess-font)",
        "white-space": "nowrap",
        "align-items": "center",
        "justify-content": "center",
        "gap": "4px",
        "cursor": "pointer",
        "pointer-events": "auto",
    }
    assert _css_block(".ess-rail:hover") == {"border-color": "var(--ess-accent)"}
    assert _css_block(".ess-rail:focus-visible") == {
        "outline": "2px solid var(--ess-accent)",
        "outline-offset": "1px",
    }
    assert _css_block(".ess.is-min .ess-rail") == {"display": "inline-flex"}
    assert "writing-mode" not in CSS and "ess-chev" not in CSS and "ess-chev" not in JS

    assert _css_block(".ess")["pointer-events"] == "none"
    gutter = _css_block(".ess-gutter")
    assert gutter["pointer-events"] == "auto" and gutter["width"] == f"{sp.SIDE_GUTTER_PX}px"
    # 머리 한 줄이 최소 폭에 든다(고르기 넷의 자연 폭 310 — 1.63 측정) · 떠 있는 단추의 가장 긴 칸
    # 이름(「저장 전 변경」 89 — 측정)이 칸 끝에서 5 나가도 「내려받기」 를 덮지 않는다.
    head = 310 + sp.SIDE_TOGGLE_GAP_PX + sp.SIDE_TOGGLE_PX
    assert sp.SIDE_MIN_PX - sp.SIDE_INSET_PX >= head
    assert sp.SIDE_REOPEN_RESERVE_PX >= 89 - 5
    # 떠 있는 단추는 표 머리 위, 고치는 칸·목록 아래다.
    orders = {
        name: int(value)
        for name, value in re.findall(r"\n(\.emg-[\w.-]+) \{[^}]*?z-index: (\d+);", GRID_CSS)
    }
    assert orders[".emg-head"] < sp.SIDE_REOPEN_Z_INDEX < orders[".emg-c.is-editing"]
    # 영역 안쪽 여백(13)에 스크롤 막대 자리가 든다.
    assert sp.SIDE_SCROLLBAR_PX <= 13


def test_the_cleanup_releases_listeners_and_frames() -> None:
    cleanup = JS[JS.rindex("return () => {") :]
    for piece in ("removeEventListener", "cancelAnimationFrame(S.frame)", "S.built = false"):
        assert piece in cleanup, piece


def test_wide_side_panels_lay_their_fields_out_in_three_columns() -> None:
    """칸 안 너비 560px 이상이면 상세·새 호기 칸 묶음을 3열로(container query — 넓힌 칸에서 높이가
    준다). 기본 2열 규칙 뒤에 서야 이긴다."""
    assert re.search(r'\.emg\[data-mode="side"\]\s*\{\s*container-type: inline-size;', GRID_CSS)
    query = GRID_CSS.index("@container (min-width: 560px)")
    assert query > GRID_CSS.index("\n.emg-fields {")
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in GRID_CSS[query:]


# ---------------------------------------------------------------- node — 순수 구획

_SECTIONS = ("splitter-clamp", "splitter-drag", "splitter-keys")


def _sections() -> str:
    parts = []
    for name in _SECTIONS:
        match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert match, f"splitter.js 에 // <{name}> 구획이 없습니다"
        parts.append(match.group("body"))
    return "\n".join(parts)


_PURE_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const b = input.bounds
const out = {}
out.clamp = input.clamp.map(([px, row]) => clampWidth(px, row, b))
out.defaults = input.rows.map((row) => defaultWidth(row, b))
out.bounds = input.rows.map((row) => sideBounds(row, b))
out.drag = input.drag.map(([w, x0, x]) => widthFromPointer(w, x0, x))
out.keys = input.keys.map(([key, shift]) => keyAction(key, shift, 340, 320, 699))
out.stored = input.stored.map((raw) => storedState(raw, 4000))
process.stdout.write(JSON.stringify(out))
"""


def _css_width(row: float, px: float | None) -> float:
    """페이지 CSS 의 폭 식을 그 글자에서 읽어 계산한다 — JS 가 같은 값을 내는지 본다."""
    match = re.fullmatch(
        r"clamp\(min\((\d+)px, (\d+)%\), var\(--emd-side-w, calc\((\d+)% - (\d+)px\)\), "
        r"min\((\d+)px, (\d+)%\)\)",
        emg.side_width_rule(),
    )
    assert match, emg.side_width_rule()
    low_px, low_pct, def_pct, def_off, high_px, high_pct = (float(x) for x in match.groups())
    low = min(low_px, row * low_pct / 100)
    high = min(high_px, row * high_pct / 100)
    value = row * def_pct / 100 - def_off if px is None else px
    return max(low, min(value, high))


def test_the_width_formula_matches_the_page_css_clamp() -> None:
    """칸막이가 쓰는 폭(저장값·키·끌기)은 페이지 CSS clamp 와 같은 식 — 줄 1,137px(1500 창·
    사이드바 열림, 영역 테두리 안)에서 최소 360 · 최대 682 · 처음 360, 좁은 줄은 몫(40%)이 최소를
    이긴다."""
    rows = [1137, 1500, 1000, 700, 500]
    cases = [(px, row) for row in rows for px in (0, 150, 320, 400, 699, 760, 2000)]
    result = _node(
        {
            "bounds": emg.side_bounds(),
            "clamp": cases,
            "rows": rows,
            "drag": [[340, 800, 700], [340, 800, 900], [500, 10, 10]],
            "keys": [
                ["ArrowLeft", False],
                ["ArrowLeft", True],
                ["ArrowRight", False],
                ["ArrowRight", True],
                ["Home", False],
                ["End", False],
                ["Enter", False],
                ["Escape", False],
                ["a", False],
            ],
            "stored": [
                '{"w": 500, "min": true}',
                '{"w": "500"}',
                '{"w": -5, "min": 1}',
                '{"w": 9999999}',
                "not json",
                "",
                "[]",
            ],
        },
        _PURE_RUNNER,
        source=_sections(),
    )
    assert result["clamp"] == [round(_css_width(row, px)) for px, row in cases]
    assert result["defaults"] == [round(_css_width(row, None)) for row in rows]
    assert result["defaults"][0] == 360
    assert result["bounds"][0] == {"lo": 360, "hi": 682.1999999999999}
    assert result["bounds"][4] == {"lo": 200, "hi": 300}
    assert result["drag"] == [440, 240, 500]
    assert result["keys"] == [
        {"width": 356},
        {"width": 404},
        {"width": 324},
        {"width": 276},
        {"width": 699},
        {"width": 320},
        {"fold": True},
        None,
        None,
    ]
    assert result["stored"] == [
        {"w": 500, "min": True},
        {"w": None, "min": False},
        {"w": None, "min": False},
        {"w": None, "min": False},
        {"w": None, "min": False},
        {"w": None, "min": False},
        {"w": None, "min": False},
    ]


# ---------------------------------------------------------------- node — 가짜 DOM 마운트

_MOUNT_HEAD = "export default function (component) {"

_DOM_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
class Classes {
  constructor() { this.names = new Set() }
  toggle(name, on) { if (on) this.names.add(name); else this.names.delete(name) }
  add(name) { this.names.add(name) }
  remove(name) { this.names.delete(name) }
  contains(name) { return this.names.has(name) }
}
class Style {
  constructor() { this.props = {}; this.cursor = '' }
  setProperty(name, value) { this.props[name] = String(value) }
  removeProperty(name) { delete this.props[name] }
}
let windowListeners = 0
class Node {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase()
    this.children = []
    this.parentNode = null
    this.attributes = {}
    this.listeners = {}
    this.style = new Style()
    this.classList = new Classes()
    this.className = ''
    this.ownText = ''
  }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child }
  get textContent() { return this.ownText + this.children.map((c) => c.textContent).join('') }
  set textContent(value) { this.children = []; this.ownText = String(value) }
  setAttribute(name, value) { this.attributes[name] = String(value) }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null }
  removeAttribute(name) { delete this.attributes[name] }
  addEventListener(type, handler) {
    ;(this.listeners[type] = this.listeners[type] || []).push(handler)
  }
  removeEventListener(type, handler) {
    this.listeners[type] = (this.listeners[type] || []).filter((h) => h !== handler)
  }
  focus() { document.activeElement = this }
  click() { return fire(this, 'click') }
  setPointerCapture(id) { this.captured = id }
  querySelector(selector) {
    const name = selector.slice(1)
    const walk = (node) => {
      for (const child of node.children) {
        if (child.className.split(/\\s+/).includes(name)) return child
        const found = walk(child)
        if (found) return found
      }
      return null
    }
    return walk(this)
  }
}
function fire(target, type, extra) {
  const event = Object.assign({
    type, target, stopped: false, prevented: false,
    stopPropagation() { this.stopped = true },
    preventDefault() { this.prevented = true },
  }, extra || {})
  for (const handler of (target.listeners[type] || []).slice()) handler.call(target, event)
  return event
}

let html = new Node('html')
const ROW = 1137
let frames = []
// 오른쪽 칸 폭 — 페이지 CSS 식 그대로(문서의 --emd-side-w 를 clamp), 접히면 자리가 없다.
const cssWidth = () => {
  if (html.getAttribute('data-emd-side') === 'min') return 0
  const raw = html.style.props['--emd-side-w']
  const lo = Math.min(360, ROW * 0.4)
  const hi = Math.min(760, ROW * 0.6)
  const value = raw ? parseFloat(raw) : ROW * 0.3 - 28
  return Math.max(lo, Math.min(hi, value))
}
const row = { getBoundingClientRect: () => ({ width: ROW, left: 0, right: ROW }) }
const column = {
  getBoundingClientRect: () => ({ width: cssWidth(), left: ROW - cssWidth() }),
}
// 오른쪽 칸 본문 칸(스크롤 칸) — 오른쪽 칸 key 칸 안에서 찾는다.
const body = { scrollTop: 0 }
const right = {
  parentElement: column,
  querySelector: (selector) => (selector === '.st-key-' + input.data.keys.body ? body : null),
}
const outer = {
  closest: (selector) =>
    selector === '.st-key-' + input.data.keys.row ? row
      : selector === '.st-key-' + input.data.keys.right ? right : null,
}
const store = {}
let storageBroken = false
let writeBroken = false
globalThis.window = {
  localStorage: {
    getItem(key) {
      if (storageBroken) throw new Error('blocked')
      return key in store ? store[key] : null
    },
    setItem(key, value) {
      if (storageBroken || writeBroken) throw new Error('blocked')
      store[key] = String(value)
    },
  },
  requestAnimationFrame(fn) { frames.push(fn); return frames.length },
  cancelAnimationFrame() {},
  addEventListener() { windowListeners += 1 },
  removeEventListener() { windowListeners -= 1 },
}
let stripPosition = 'sticky'
window.getComputedStyle = (node) => node === stripNode
  ? { position: stripPosition, top: '52.5px' }
  : { position: 'static', top: 'auto' }
const stripNode = { getBoundingClientRect: () => ({ top: 56, bottom: 92, height: 36 }) }
globalThis.document = {
  activeElement: null,
  get documentElement() { return html },
  createElement: (tag) => new Node(tag),
  querySelector(selector) {
    if (selector === input.data.cover) return stripNode
    if (selector === '[data-testid="stMain"]') return { getBoundingClientRect: () => ({ top: 0 }) }
    return null
  },
}
const flush = () => { const run = frames; frames = []; for (const fn of run) fn() }

function mount(data) {
  const parentElement = new Node('div')
  const host = parentElement.appendChild(new Node('div'))
  host.className = 'ess'
  host.getRootNode = () => ({ host: outer })
  const component = { data, parentElement }
  const cleanup = globalThis.__mount(component)
  const rerender = (next) => globalThis.__mount({ ...component, data: next })
  return { host, cleanup, rerender }
}
const part = (host, cls) => host.querySelector('.' + cls)
const gutterOf = (host) => part(host, 'ess-gutter')
const snap = (host) => ({
  attr: html.getAttribute('data-emd-side'),
  width: html.style.props['--emd-side-w'] || null,
  top: html.style.props['--emd-top'] || null,
  min: host.classList.contains('is-min'),
  store: store['capa-equipment-side-v1'] ? JSON.parse(store['capa-equipment-side-v1']) : null,
  focus: document.activeElement ? document.activeElement.className : null,
  now: part(host, 'ess-gutter').getAttribute('aria-valuenow'),
  range: ['aria-valuemin', 'aria-valuemax'].map((name) => gutterOf(host).getAttribute(name)),
  label: part(host, 'ess-rail-label').textContent,
})
const out = {}

// 1. 저장해 둔 폭·접힘을 처음 마운트에서 문서에 다시 건다.
store['capa-equipment-side-v1'] = JSON.stringify({ w: 500, min: true })
body.scrollTop = 600
let m = mount(input.data)
out.restored = snap(m.host)
out.bodyFirstMount = body.scrollTop
out.palette = m.host.style.props['--ess-accent'] || null
// 2. 떠 있는 단추를 누르면 편다 — 초점은 접기 단추로.
part(m.host, 'ess-rail').click()
out.unfolded = snap(m.host)
// 3. 접기 단추 — 접고 초점은 떠 있는 단추로.
part(m.host, 'ess-toggle').click()
out.folded = snap(m.host)
// 4. 같은 reveal 의 다시 그리기는 그대로(본문 칸 스크롤도), reveal 이 오르면 펴고 본문 칸을
// 맨 위로.
body.scrollTop = 1489
m.rerender({ ...input.data })
out.sameReveal = snap(m.host).attr
out.bodySameReveal = body.scrollTop
m.rerender({ ...input.data, reveal: input.data.reveal + 1, label: '새 호기' })
out.revealed = snap(m.host)
out.bodyRevealed = body.scrollTop
// 펼쳐 있을 때도 reveal 이 오르면 본문 칸을 맨 위로(다른 호기를 연 회차).
body.scrollTop = 1489
m.rerender({ ...input.data, reveal: input.data.reveal + 2, label: '새 호기' })
out.bodyRevealedOpen = { attr: snap(m.host).attr, scroll: body.scrollTop }
// 5. 키 — ← 16px 넓힘, Shift+← 64px, Home 최대, End 최소, Enter 접기, 그 밖은 놓아 둔다.
const gutter = part(m.host, 'ess-gutter')
const key = (k, shift) => fire(gutter, 'keydown', { key: k, shiftKey: !!shift })
key('ArrowLeft')
out.left = snap(m.host).width
key('ArrowLeft', true)
out.leftWide = snap(m.host).width
key('Home')
out.home = snap(m.host).width
key('End')
out.end = snap(m.host).width
const other = key('a')
out.otherKey = { stopped: other.stopped, prevented: other.prevented }
const enter = key('Enter')
out.enter = { attr: snap(m.host).attr, stopped: enter.stopped, focus: snap(m.host).focus }
part(m.host, 'ess-rail').click()
// 6. 끌기 — 왼쪽으로 100px 끌면 100px 넓어지고, 한계를 넘으면 최대에서 멈춘다. 놓을 때 저장한다.
fire(gutter, 'pointerdown', { button: 0, clientX: 800, pointerId: 7 })
const startW = cssWidth()
fire(gutter, 'pointermove', { clientX: 700 })
fire(gutter, 'pointermove', { clientX: 690 })
const pending = frames.length
flush()
out.drag = { startW, pending, width: snap(m.host).width, storedBeforeUp: snap(m.host).store.w }
fire(gutter, 'pointermove', { clientX: -2000 })
flush()
fire(gutter, 'pointerup', {})
out.dragMax = { width: snap(m.host).width, store: snap(m.host).store.w, cursor: html.style.cursor }
// 7. 두 번 누르면 처음 폭.
fire(gutter, 'dblclick', {})
out.reset = { width: snap(m.host).width, store: snap(m.host).store }
// 8. 정리 — 창 듣기를 푼다.
out.windowBefore = windowListeners
m.cleanup()
out.windowAfter = windowListeners
// 9. 저장소가 막혀도 마운트·폭·접기가 된다. 탭 줄이 붙는 칸이 아니면 지금 아래 끝으로 잰다.
storageBroken = true
stripPosition = 'static'
html.removeAttribute('data-emd-side')
const storedBefore = JSON.stringify(store)
m = mount(input.data)
fire(part(m.host, 'ess-gutter'), 'keydown', { key: 'ArrowLeft', shiftKey: true })
part(m.host, 'ess-toggle').click()
const sideState = (host) => ({
  attr: snap(host).attr, min: snap(host).min, width: snap(host).width,
})
out.blocked = { ...sideState(m.host), top: snap(m.host).top }
// 10. 다시 마운트(안쪽 탭·화면을 옮겨 다시 그린 칸막이)해도 이 문서의 폭·접힘이 남는다 —
// 저장소는 손대지 않았다.
m.cleanup()
m = mount(input.data)
out.blockedRemount = { ...sideState(m.host), untouched: JSON.stringify(store) === storedBefore }
m.cleanup()
// 11. 새로 읽은 문서는 처음 상태다(저장소가 막혀 있으니 기억할 곳이 없다).
html = new Node('html')
m = mount(input.data)
out.blockedReload = { attr: snap(m.host).attr, width: snap(m.host).width }
m.cleanup()
// 12. 읽기는 되고 쓰기만 막힌 저장소 — 저장값으로 시작하고, 쓰기가 막힌 뒤 다시 마운트해도 이
// 문서의 접힘이 남는다.
storageBroken = false
writeBroken = true
html = new Node('html')
store['capa-equipment-side-v1'] = JSON.stringify({ w: 500, min: false })
m = mount(input.data)
out.writeBlockedStart = { attr: snap(m.host).attr, width: snap(m.host).width }
part(m.host, 'ess-toggle').click()
m.cleanup()
m = mount(input.data)
out.writeBlockedRemount = {
  attr: snap(m.host).attr, width: snap(m.host).width, store: snap(m.host).store,
}
process.stdout.write(JSON.stringify(out))
"""


def _dom_source() -> str:
    assert JS.count(_MOUNT_HEAD) == 1
    return JS.replace(_MOUNT_HEAD, "globalThis.__mount = function (component) {")


def test_the_splitter_mount_restores_folds_resizes_and_cleans_up() -> None:
    """마운트 한 바퀴(줄 1,137px · 화면 탭 줄 sticky top 52.5 + 높이 36 — 붙는 높이
    97px, 붙는 칸이 아니면 지금 아래 끝 92 + 8): 저장값(폭 500 · 접힘)을
    문서에 다시 걸고, 떠 있는 단추는 펴고 접기 단추는 접으며(초점은 서로에게), 표가 연 회차(`reveal`
    이 오름)에만 펴고 본문 칸을 맨 위로 올린다(key 칸이라 다른 호기를 그려도 스크롤 자리가 남아
    새 호기 이름 머리가 칸 위로 나가 있었다). 키는 폭을 바꿔 저장하고 모르는 키는 놓아 둔다.
    끌기는 한 프레임에 한 번 바꾸고 최대에서 멈추며 놓을 때 저장한다. 두 번 누르면 처음 폭.
    정리는 창 듣기를 푼다. 저장소가 막혀도 폭·접기가 되고, 다시 마운트(안쪽 탭·화면 옮김)해도
    `<html>` 에 걸린 이 문서의 폭·접힘이 남으며(전에는 처음으로 돌아갔다) 새로 읽으면 처음이다 —
    읽기만 되고 쓰기가 막혀도 같다."""
    data = {
        "palette": sp.splitter_palette(),
        "label": SIDE_DETAIL,
        "reveal": 3,
        "bounds": emg.side_bounds(),
        "keys": {"row": emg.SPLIT_KEY, "right": emg.RIGHT_KEY, "body": emg.SIDE_BODY_KEY},
        "names": {
            "store": "capa-equipment-side-v1",
            "width": "--emd-side-w",
            "top": "--emd-top",
            "attr": "data-emd-side",
        },
        "cover": ".st-key-page_tabs_strip",
    }

    out = _node({"data": data}, _DOM_RUNNER, source=_dom_source())

    assert out["restored"] == {
        "attr": "min",
        "width": "500px",
        "top": "97px",
        "min": True,
        "store": {"w": 500, "min": True},
        "focus": None,
        "now": "0",
        "range": ["360", "682"],
        "label": SIDE_DETAIL,
    }
    assert out["palette"] == sp.splitter_palette()["accent"]
    assert out["unfolded"]["attr"] is None and out["unfolded"]["min"] is False
    assert out["unfolded"]["store"] == {"w": 500, "min": False}
    assert out["unfolded"]["focus"] == "ess-toggle"
    assert out["unfolded"]["now"] == "500"
    assert out["folded"]["attr"] == "min" and out["folded"]["focus"] == "ess-rail"
    assert out["sameReveal"] == "min"
    assert out["revealed"]["attr"] is None and out["revealed"]["label"] == "새 호기"
    # 본문 칸 스크롤 — 처음 마운트·같은 reveal 은 그대로, reveal 이 오르면(접혔든 펼쳤든) 맨 위.
    assert out["bodyFirstMount"] == 600
    assert out["bodySameReveal"] == 1489
    assert out["bodyRevealed"] == 0
    assert out["bodyRevealedOpen"] == {"attr": None, "scroll": 0}
    assert out["left"] == "516px"
    assert out["leftWide"] == "580px"
    assert out["home"] == "682px"
    assert out["end"] == "360px"
    assert out["otherKey"] == {"stopped": False, "prevented": False}
    assert out["enter"] == {"attr": "min", "stopped": True, "focus": "ess-rail"}
    assert out["drag"] == {"startW": 360, "pending": 1, "width": "470px", "storedBeforeUp": 360}
    assert out["dragMax"] == {"width": "682px", "store": 682, "cursor": ""}
    assert out["reset"] == {"width": None, "store": {"w": None, "min": False}}
    assert out["windowBefore"] == 1 and out["windowAfter"] == 0
    assert out["blocked"] == {"attr": "min", "min": True, "top": "100px", "width": "424px"}
    assert out["blockedRemount"] == {
        "attr": "min",
        "min": True,
        "width": "424px",
        "untouched": True,
    }
    assert out["blockedReload"] == {"attr": None, "width": None}
    assert out["writeBlockedStart"] == {"attr": None, "width": "500px"}
    assert out["writeBlockedRemount"] == {
        "attr": "min",
        "width": "500px",
        "store": {"w": 500, "min": False},
    }
