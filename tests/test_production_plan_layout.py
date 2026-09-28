# Purpose: 생산 계획 화면의 조건 카드·작업 줄 위치·Guide 가 사용자 결정대로 서는지 고정한다.

"""사이드바 조건 카드 + Guide 의 첫 샘플(2026-09-28 사용자 결정).

- 환산 조건(소요기준·상세·EDP)은 본문이 아니라 사이드바 조건 카드다. **환산 탭에서만** 서고,
  **기본은 접힘**, 한 번 편 카드는 **탭을 오가도 편 채**다.
- 적용 버튼은 표 **위**다(표 아래에 있으면 고친 뒤 보이지 않아 적용을 건너뛴다).
- 설명은 Guide 대화상자다.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_load_conversion_plan_apply import _isolated_custom_renderers, _script  # noqa: F401

from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY, load_guide
from capa_simulation.sidebar_status import CONDITION_CARD_PREFIX, remembered_box_key

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app_pages" / "load_conversion.py"
CARD_KEY = f"{CONDITION_CARD_PREFIX}load_conversion"
TAB_KEY = "load_conversion_active_tab"


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    yield tmp_path_factory.mktemp("production_plan_layout") / "scenario.duckdb"


def _app(database: Path) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=300).run()
    assert not list(app.exception)
    return app


def _card_widgets(app: AppTest) -> set[str]:
    keys = {widget.key for widget in app.sidebar.selectbox}
    keys |= {widget.key for widget in app.sidebar.toggle}
    return {key for key in keys if key}


def test_the_conversion_settings_live_in_a_collapsed_sidebar_card(database: Path) -> None:
    app = _app(database)

    assert {"monthly_volume_basis", "monthly_volume_detail", "monthly_volume_edp"} <= (
        _card_widgets(app)
    )
    # 본문에는 더 이상 없다 — 두 곳에서 같은 조건을 만지면 안 된다.
    assert "monthly_volume_basis" not in {widget.key for widget in app.main.selectbox}
    assert app.session_state[CARD_KEY] is False


def test_the_card_shows_only_on_the_conversion_tab_and_remembers_it_was_opened(
    database: Path,
) -> None:
    app = _app(database)
    app.session_state[CARD_KEY] = True
    app.run()

    app.session_state[TAB_KEY] = "PKG PLAN"
    app.run()
    assert not list(app.exception)
    assert "monthly_volume_basis" not in _card_widgets(app)
    # 안 그려진 동안에도 편 상태를 기억한다.
    assert app.session_state[remembered_box_key(CARD_KEY)][0] is True

    app.session_state[TAB_KEY] = "환산"
    app.run()
    assert "monthly_volume_basis" in _card_widgets(app)
    assert app.session_state[CARD_KEY] is True


@pytest.mark.parametrize(
    ("path", "label", "sheet"),
    [
        (PAGE, "PKG PLAN 변경사항 적용", "styled_plan_table"),
        (PAGE, "수율 변경사항 적용", "styled_yield_table"),
        (
            ROOT / "src" / "capa_simulation" / "components" / "month_editor.py",
            "변경사항 적용",
            "styled_table",
        ),
    ],
)
def test_apply_buttons_sit_above_their_sheets(path: Path, label: str, sheet: str) -> None:
    """적용 버튼은 표보다 **먼저** 그린다. 표가 높이 500px 이라 아래 두면 화면 밖이다."""
    calls = [
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
    ]
    button = [
        node.lineno
        for node in calls
        if ast.unparse(node.func) == "st.button"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == label
    ]
    editor = [
        node.lineno
        for node in calls
        if ast.unparse(node.func) == "st.data_editor"
        and node.args
        and ast.unparse(node.args[0]) == sheet
    ]
    assert len(button) == 1 and len(editor) == 1
    assert button[0] < editor[0]


def test_the_guide_opens_from_the_hidden_trigger(database: Path) -> None:
    app = _app(database)
    assert app.button(key=GUIDE_TRIGGER_KEY)

    app.button(key=GUIDE_TRIGGER_KEY).click().run()
    assert not list(app.exception)
    shown = " ".join(item.value for item in app.markdown)
    assert "환산 조건" in shown and "PKG PLAN 변경사항 적용" in shown


def test_leaving_the_page_forgets_an_open_popup() -> None:
    """닫지 않고 떠난 팝업이 돌아왔을 때 저절로 뜨면 안 된다(브라우저 뒤로 가기 경로)."""

    def app() -> None:
        import streamlit as st

        from capa_simulation.page_bootstrap import forget_page_dialogs

        st.session_state["load_conversion_open_dialog"] = "plan_paste"
        st.session_state["unrelated_state"] = "kept"
        forget_page_dialogs()

    test = AppTest.from_function(app).run()
    assert "load_conversion_open_dialog" not in test.session_state
    assert test.session_state["unrelated_state"] == "kept"


def test_registering_warns_before_it_drops_an_unapplied_paste(database: Path) -> None:
    """붙여넣고 아직 적용하지 않은 PKG PLAN 표가 있으면 등록 팝업이 먼저 경고한다."""
    from test_load_conversion_plan_apply import _clipboard_text, _paste

    app = _app(database)
    _paste(app, _clipboard_text(app, scale=0.5))
    assert "pkg_plan_staged_paste" in app.session_state

    app.button(key="open_virtual_product").click().run()
    assert not list(app.exception)
    assert any("등록하면 버려집니다" in item.value for item in app.warning)


def test_the_guide_explains_every_card_setting_and_action() -> None:
    """본문에서 뺀 설명이 Guide 에 다 옮겨졌는가. 카드 설정과 작업 버튼 이름으로 대조한다."""
    guide = load_guide("load_conversion")
    for label in (
        "소요기준",
        "상세",
        "EDP",
        "PKG PLAN 변경사항 적용",
        "수율 변경사항 적용",
        "Excel 붙여넣기",
        "가상 제품 등록",
        "신규 리비전 저장",
    ):
        assert label in guide, label
