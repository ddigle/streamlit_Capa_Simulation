# Purpose: Space 2단 탐색(블록 열기·층 바로 가기·주소의 층 인자)이 층을 열고 되돌리는지 검사한다.

"""AppTest 는 편집기 JS 를 돌리지 못한다. `_EDITOR` 를 대역으로 바꿔, 블록을 누른 것처럼
`navigate` 값을 세션에 두고 `on_navigate_change` 콜백을 대역이 직접 부른다.

진짜 Streamlit 은 콜백을 본문보다 먼저 돌려 그 회차에 층 상세가 선다. 대역은 본문 안(뷰어를 그리는
자리)에서 부르므로 층 상세는 다음 회차에 선다 — 그래서 아래 테스트는 한 번 더 돈다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_equipment_pages import PROJECT_ROOT, _page_script

from capa_simulation.components import space_layout_editor

PAGE = PROJECT_ROOT / "app_pages" / "space_status.py"
FAKE_NAVIGATE_KEY = "test_fake_fab_navigate"


@pytest.fixture
def viewer_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> None:
        import streamlit as st

        calls.append(kwargs["data"])
        payload = st.session_state.pop(FAKE_NAVIGATE_KEY, None)
        if payload is not None and kwargs["data"].get("scope") == "fab":
            # 진짜 컴포넌트는 결과를 `st.session_state[key]` 에 `navigate` 로 싣는다.
            st.session_state[kwargs["key"]] = {"navigate": payload}
            kwargs["on_navigate_change"]()

    monkeypatch.setattr(space_layout_editor, "_EDITOR", _stub)
    return calls


def _app(tmp_path: Path, **query: str) -> AppTest:
    app = AppTest.from_string(_page_script(PAGE, tmp_path / "space_nav.duckdb"), default_timeout=60)
    for name, value in query.items():
        app.query_params[name] = value
    return app


def test_pressing_a_floor_block_opens_that_floor_and_writes_the_address(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    app = _app(tmp_path).run()
    assert not app.exception
    fab = viewer_calls[-1]
    assert fab["scope"] == "fab"

    app.session_state[FAKE_NAVIGATE_KEY] = {"epoch": fab["epoch"], "target": "C2 2F"}
    app.run()
    app.run()

    assert not app.exception
    floor = viewer_calls[-1]
    assert floor["scope"] == "floor" and floor["floor"] == "C2 2F"
    assert app.session_state["space_status_selected_building"] == "C2"
    assert app.session_state["space_status_selected_floor"] == "2F"
    assert app.query_params["floor"] == ["C2-2F"]


def test_a_block_that_points_nowhere_leaves_the_fab_overview(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    app = _app(tmp_path).run()
    fab = viewer_calls[-1]
    app.session_state[FAKE_NAVIGATE_KEY] = {"epoch": fab["epoch"], "target": "C9 1F"}
    app.run()
    app.run()

    assert not app.exception
    assert viewer_calls[-1]["scope"] == "fab"
    assert "floor" not in app.query_params


def test_a_press_from_an_old_epoch_is_ignored(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    """도면이 다시 서기 전에 누른 옛 블록은 열지 않는다(적용의 옛 epoch 거절과 같은 규칙)."""
    app = _app(tmp_path).run()
    assert viewer_calls[-1]["epoch"] != "fab|old"
    app.session_state[FAKE_NAVIGATE_KEY] = {"epoch": "fab|old", "target": "C2 2F"}
    app.run()
    app.run()

    assert not app.exception
    assert viewer_calls[-1]["scope"] == "fab"
    assert "space_status_selected_building" not in app.session_state
    assert "floor" not in app.query_params


def test_the_address_reopens_its_floor_after_a_reload(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    """새로고침은 새 세션이다. 주소의 `floor` 인자가 그 층을 연다."""
    app = _app(tmp_path, floor="C1-1F").run()

    assert not app.exception
    assert viewer_calls[-1]["scope"] == "floor" and viewer_calls[-1]["floor"] == "C1 1F"
    assert app.session_state["space_status_selected_floor"] == "1F"


@pytest.mark.parametrize("bad", ["C9-1F", "C1-9F", "C1 1F", "FAB"])
def test_a_bad_address_quietly_shows_the_fab_overview(
    tmp_path: Path, viewer_calls: list[dict[str, Any]], bad: str
) -> None:
    app = _app(tmp_path, floor=bad, theme="dark").run()

    assert not app.exception
    assert viewer_calls[-1]["scope"] == "fab"
    # 잘못된 `floor` 인자만 지운다. 테마 인자는 남는다.
    assert "floor" not in app.query_params
    assert app.query_params["theme"] == ["dark"]


def test_the_floor_jump_and_the_fab_breadcrumb_keep_the_theme_param(
    tmp_path: Path, viewer_calls: list[dict[str, Any]]
) -> None:
    """`floor` 키만 넣고 지운다. `st.query_params.clear()` 로 `theme` 까지 지우면 테마 스크립트가
    첫 방문으로 보고 다시 새로고침한다."""
    app = _app(tmp_path, theme="dark").run()
    assert viewer_calls[-1]["scope"] == "fab"

    app.selectbox(key="space_status_floor_jump_fab").set_value("C3 1F").run()

    assert not app.exception
    assert viewer_calls[-1]["scope"] == "floor" and viewer_calls[-1]["floor"] == "C3 1F"
    assert app.query_params["floor"] == ["C3-1F"]
    assert app.query_params["theme"] == ["dark"]
    # 층 화면의 바로 가기는 그 층을 가리킨 채 선다.
    assert app.selectbox(key="space_status_floor_jump_C3-1F").value == "C3 1F"

    app.button(key="space_status_fab_breadcrumb").click().run()

    assert not app.exception
    assert viewer_calls[-1]["scope"] == "fab"
    assert "floor" not in app.query_params
    assert app.query_params["theme"] == ["dark"]
    assert app.selectbox(key="space_status_floor_jump_fab").value is None
