# Purpose: HOME 주요공정 프리셋 편집 카드가 프래그먼트 회차에도 최신 공용 프리셋에 저장하는지 본다.

"""주요공정 프리셋 편집 카드는 프래그먼트다 — 「고칠 프리셋」·삭제 확인·폼 제출은 카드만 다시 돈다.

프래그먼트 회차는 직전 **앱 전체 회차의 인자**를 그대로 쓴다. 저장·기본으로·삭제는 늘 프리셋
묶음 **전체의 교체**라, 인자로 받은 프로필로 묶음을 만들면 그 사이 다른 세션이 저장한 프리셋을 낡은
묶음으로 덮는다(lost update). 카드는 그래서 프로필을 인자로 받지 않고 회차마다 공용 캐시에서 다시
읽는다.

AppTest 는 프래그먼트만 다시 돌리지 못한다(회차마다 프래그먼트 저장소를 새로 만든다). 그래서
`test_home_page` 의 공정 필터 팝업 시험처럼, 첫 회차에 HOME 이 카드에 넘긴 인자를 적어 두고 다음
회차부터는 **카드 함수만 그 인자로** 부른다 — 프래그먼트 회차와 같은 조건이다.
"""

import inspect
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components import home_preference
from capa_simulation.persistence.cache import clear_global_key_process_cache
from capa_simulation.persistence.repository import DuckDBScenarioRepository

HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"
TARGET_KEY = "home_key_process_preset_edit"
EMULATE_KEY = "test_emulate_fragment_rerun"
A = ("A 그룹", ("DEMO_Chip_Attach",))
B = ("B 그룹", ("DEMO_Final_Test",))
C = ("C 그룹", ("DEMO_Wafer_Inspect",))


@pytest.fixture(autouse=True)
def _forget_key_process_cache() -> None:
    """공용 프리셋 캐시는 프로세스 전역이다. 앞 시험의 값이 첫 회차에 섞이지 않게 비운다."""
    clear_global_key_process_cache()


def _script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.home_preference as home_preference
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

_original_editor = home_preference._render_key_process_editor
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
horizontal_scrollbar.render_horizontal_scrollbar = lambda *_args, **_kwargs: None
try:
    if st.session_state.get({EMULATE_KEY!r}):
        # 프래그먼트 회차 — 카드만, 직전 전체 회차의 인자로 돈다.
        _original_editor(**st.session_state["test_editor_kwargs"])
    else:
        from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
        from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

        bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
        apply_pending_scenario_preset()

        def _recording_editor(**kwargs):
            st.session_state["test_editor_kwargs"] = dict(kwargs)
            return _original_editor(**kwargs)

        home_preference._render_key_process_editor = _recording_editor
        page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
        exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    home_preference._render_key_process_editor = _original_editor
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
"""


def _assert_clean(app: AppTest) -> None:
    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [element.value for element in app.error]


def _fragment_app(tmp_path: Path) -> tuple[AppTest, DuckDBScenarioRepository]:
    """프리셋 A·B 가 있는 HOME 을 한 번 그린 뒤, 다음 회차부터 카드만 도는 상태로 둔다.

    그 사이 다른 세션이 C 를 더한다 — 저장소에 쓰고 공용 캐시를 비운다(그 세션의 저장 단추가 하는
    일). 이 세션의 카드 인자는 C 를 모르는 첫 회차의 것이다.
    """
    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_key_process_presets([A, B], source="시험")
    clear_global_key_process_cache()
    app = AppTest.from_string(_script(database_path), default_timeout=300)
    app.run()
    _assert_clean(app)
    app.session_state[EMULATE_KEY] = True
    app.run()
    _assert_clean(app)

    repository.replace_global_key_process_presets([A, B, C], source="다른 세션")
    clear_global_key_process_cache()
    return app, repository


def test_deleting_a_preset_in_a_fragment_rerun_keeps_one_saved_meanwhile(tmp_path: Path) -> None:
    app, repository = _fragment_app(tmp_path)
    app.selectbox(key=TARGET_KEY).set_value(B[0]).run()
    next(box for box in app.checkbox if box.label == f"「{B[0]}」 삭제 확인").check().run()
    app.button(key="home_key_process_preset_delete").click().run()
    _assert_clean(app)

    assert repository.load_global_key_process().presets == (A, C)


def test_promoting_a_preset_in_a_fragment_rerun_keeps_one_saved_meanwhile(
    tmp_path: Path,
) -> None:
    app, repository = _fragment_app(tmp_path)
    app.selectbox(key=TARGET_KEY).set_value(B[0]).run()
    app.button(key="home_key_process_preset_default").click().run()
    _assert_clean(app)

    assert repository.load_global_key_process().presets == (B, A, C)


def test_saving_the_form_in_a_fragment_rerun_keeps_one_saved_meanwhile(tmp_path: Path) -> None:
    app, repository = _fragment_app(tmp_path)
    app.selectbox(key=TARGET_KEY).set_value(B[0]).run()
    # 다른 세션이 더한 프리셋이 이 카드의 선택지에도 보인다.
    assert C[0] in app.selectbox(key=TARGET_KEY).options
    next(widget for widget in app.text_input if widget.label == "프리셋 이름").set_value("B2")
    next(button for button in app.button if button.label == "프리셋 저장").click().run()
    _assert_clean(app)

    assert repository.load_global_key_process().presets == (A, ("B2", B[1]), C)


def test_the_preset_editor_is_a_fragment() -> None:
    """「고칠 프리셋」·삭제 확인·폼 제출이 HOME 전체가 아니라 이 카드만 다시 돌게 한다."""
    editor = home_preference._render_key_process_editor
    assert getattr(editor, "__wrapped__", None) is not None
    # 프로필을 인자로 받으면 프래그먼트 회차가 그 낡은 값으로 묶음을 만든다 — 위 세 시험의 까닭.
    assert "key_process_profile" not in inspect.signature(editor).parameters
