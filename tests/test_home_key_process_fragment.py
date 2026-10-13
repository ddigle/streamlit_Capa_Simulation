# Purpose: HOME 주요공정 프리셋 편집 카드가 프래그먼트 회차에도 최신 공용 프리셋에 저장하는지 본다.

"""주요공정 프리셋 편집 카드는 프래그먼트다 — 「고칠 프리셋」·삭제 확인·폼 제출은 카드만 다시 돈다.

프래그먼트 회차는 직전 **앱 전체 회차의 인자**를 그대로 쓴다. 저장·기본으로·삭제는 늘 프리셋
묶음 **전체의 교체**라, 인자로 받은 프로필로 묶음을 만들면 그 사이 다른 세션이 저장한 프리셋을 낡은
묶음으로 덮는다(lost update). 카드는 그래서 프로필을 인자로 받지 않고 회차마다 공용 캐시에서 다시
읽는다.

AppTest 는 프래그먼트만 다시 돌리지 못한다(회차마다 프래그먼트 저장소를 새로 만든다). 그래서
시험은 두 갈래다.

- **흉내(위 세 시험)** — `test_home_page` 의 공정 필터 팝업 시험처럼, 첫 회차에 HOME 이 카드에 넘긴
  인자를 적어 두고 다음 회차부터는 **카드 함수만 그 인자로** 부른다. 공개 API 만 쓴다.
- **진짜 프래그먼트 회차(마지막 시험)** — AppTest 의 러너가 프래그먼트 저장소를 회차 사이에 쥐고,
  브라우저처럼 `fragment_id_queue` 로 카드만 돌린다. 카드만 도는지, 그 회차의
  `st.rerun(scope="app")` 이 앱 전체 회차로 바뀌는지, 카드 밖 위젯 상태가 남는지를 본다.
  **Streamlit 내부를 쓴다** —
  `LocalScriptRunner` 의 `_fragment_storage`·`_requests`·`require_widgets_deltas` 와 `RerunData`,
  델타의 `fragment_id`. `streamlit==1.63.0`(`pyproject.toml` 의 `>=1.63,<1.64`)에 기댄다. 판을 올려
  이 시험이 러너 쪽에서 깨지면 카드가 아니라 이 대역부터 그 판에 맞춘다.
"""

import inspect
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.runtime.fragment import MemoryFragmentStorage
from streamlit.runtime.scriptrunner import RerunData, ScriptRunnerEvent
from streamlit.runtime.scriptrunner_utils.script_requests import ScriptRequests
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1 import app_test as app_test_module
from streamlit.testing.v1.element_tree import ElementTree, parse_tree_from_messages
from streamlit.testing.v1.local_script_runner import LocalScriptRunner, require_widgets_deltas

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


TAB_KEY = "home_active_tab"
PREFERENCE = ":material/tune: Preference"
FULL_RUNS_KEY = "test_full_app_runs"


@dataclass
class _Browser:
    """브라우저 대역 — 회차 사이에 쥐는 프래그먼트 저장소와, 다음 회차에 돌릴 프래그먼트.

    `fragment_queue` 가 비어 있으면 앱 전체 회차다. `started` 는 마지막 `run()` 안에서 시작한
    회차마다의 `fragment_ids_this_run`(앱 전체 회차는 `[]`)이고, `messages` 는 그 `run()` 이 내보낸
    메시지다.
    """

    storage: MemoryFragmentStorage = field(default_factory=MemoryFragmentStorage)
    fragment_queue: list[str] = field(default_factory=list)
    started: list[list[str]] = field(default_factory=list)
    messages: list[ForwardMsg] = field(default_factory=list)

    def fragment_of(self, widget_key: str) -> str:
        """그 키의 위젯을 그린 프래그먼트 — 브라우저가 프래그먼트 회차를 청할 때 보내는 id 다."""
        for message in self.messages:
            if message.WhichOneof("type") != "delta":
                continue
            delta = message.delta
            if delta.WhichOneof("type") != "new_element":
                continue
            kind = delta.new_element.WhichOneof("type")
            widget = getattr(delta.new_element, kind) if kind else None
            if str(getattr(widget, "id", "")).endswith(f"-{widget_key}"):
                assert delta.fragment_id, f"{widget_key} 는 프래그먼트 안이 아니다"
                return str(delta.fragment_id)
        raise AssertionError(f"{widget_key} 위젯을 그린 메시지가 없다")


@pytest.fixture
def browser(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Browser]:
    """AppTest 의 러너를 프래그먼트 회차를 도는 러너로 바꾼다(이 시험 안에서만)."""
    state = _Browser()

    class _BrowserLikeRunner(LocalScriptRunner):
        def run(
            self,
            widget_state: WidgetStates | None = None,
            query_params: dict[str, Any] | None = None,
            timeout: float = 3,
            page_hash: str = "",
        ) -> ElementTree:
            # AppTest 는 `run()` 마다 러너를 새로 만들고 그때마다 저장소도 새로 만든다. 그러면
            # 프래그먼트 회차가 「모르는 프래그먼트」를 건너뛴다 — 서버처럼 하나를 계속 쥔다.
            self._fragment_storage = state.storage
            if state.fragment_queue:
                # 생성자가 넣어 둔 앱 전체 회차 요청을 버린다. 남기면 프래그먼트 요청과 합쳐져
                # 앱 전체 회차가 된다(`ScriptRequests.request_rerun` 의 합치기 규칙).
                self._requests = ScriptRequests()
                self.request_rerun(
                    RerunData(
                        widget_states=widget_state,
                        page_script_hash=page_hash,
                        fragment_id_queue=list(state.fragment_queue),
                    )
                )
                if not self._script_thread:
                    self.start()
                require_widgets_deltas(self, timeout)
                tree = parse_tree_from_messages(self.forward_msgs())
            else:
                tree = super().run(widget_state, query_params, timeout, page_hash)
            state.started = [
                list(data.get("fragment_ids_this_run") or [])
                for event, data in zip(self.events, self.event_data, strict=False)
                if event == ScriptRunnerEvent.SCRIPT_STARTED
            ]
            state.messages = list(self.forward_msgs())
            return tree

    monkeypatch.setattr(app_test_module, "LocalScriptRunner", _BrowserLikeRunner)
    yield state


def _counting_script(database_path: Path) -> str:
    """HOME 을 그대로 돌리되 **앱 전체 회차**만 센다.

    프래그먼트 회차는 스크립트 맨 위를 지나지 않는다.
    """
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})
st.session_state[{FULL_RUNS_KEY!r}] = st.session_state.get({FULL_RUNS_KEY!r}, 0) + 1

_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
horizontal_scrollbar.render_horizontal_scrollbar = lambda *_args, **_kwargs: None
try:
    from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
    from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    apply_pending_scenario_preset()
    page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
"""


def test_card_operations_rerun_only_the_card_and_saving_reruns_the_whole_app(
    tmp_path: Path, browser: _Browser
) -> None:
    """진짜 프래그먼트 회차로 본다 — 카드 조작은 카드만, 저장·삭제 뒤에는 앱 전체가 새 프로필로
    돈다.

    그 사이 다른 세션이 더한 프리셋도 남는다(위 흉내 시험과 같은 lost update 확인을 진짜 경로로).
    """
    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_key_process_presets([A, B], source="시험")
    clear_global_key_process_cache()
    app = AppTest.from_string(_counting_script(database_path), default_timeout=300)
    app.run()
    _assert_clean(app)
    # 사이드바에서 B 를 보고 있고, Preference 탭을 연다(탭 전환은 앱 전체 회차다).
    app.session_state[home_preference.KEY_PROCESS_PRESET_KEY] = B[0]
    app.session_state[TAB_KEY] = PREFERENCE
    app.run()
    _assert_clean(app)
    assert browser.started == [[]]
    full_runs = app.session_state[FULL_RUNS_KEY]

    # 「고칠 프리셋」 — 카드만 돈다.
    editor = browser.fragment_of(TARGET_KEY)
    browser.fragment_queue = [editor]
    app.selectbox(key=TARGET_KEY).set_value(B[0]).run()
    _assert_clean(app)
    assert browser.started == [[editor]]
    assert app.session_state[FULL_RUNS_KEY] == full_runs

    repository.replace_global_key_process_presets([A, B, C], source="다른 세션")
    clear_global_key_process_cache()

    # 폼 저장(B → B2) — 제출은 카드 회차이고, 저장 뒤 `st.rerun(scope="app")` 이 앱 전체 회차로
    # 바뀐다.
    next(widget for widget in app.text_input if widget.label == "프리셋 이름").set_value("B2")
    next(button for button in app.button if button.label == "프리셋 저장").click().run()
    _assert_clean(app)
    assert browser.started == [[editor], []]
    assert app.session_state[FULL_RUNS_KEY] == full_runs + 1
    assert repository.load_global_key_process().presets == (A, ("B2", B[1]), C)
    assert app.selectbox(key=TARGET_KEY).value == "B2"
    # 카드 밖 위젯 상태(열린 탭)는 카드 회차를 지나도 남는다.
    assert app.session_state[TAB_KEY] == PREFERENCE
    full_runs += 1

    # 삭제 확인은 카드만, 삭제는 앱 전체 회차로.
    editor = browser.fragment_of(TARGET_KEY)
    browser.fragment_queue = [editor]
    next(box for box in app.checkbox if box.label == "「B2」 삭제 확인").check().run()
    _assert_clean(app)
    assert browser.started == [[editor]]
    assert app.session_state[FULL_RUNS_KEY] == full_runs
    app.button(key="home_key_process_preset_delete").click().run()
    _assert_clean(app)
    assert browser.started == [[editor], []]
    assert app.session_state[FULL_RUNS_KEY] == full_runs + 1
    assert repository.load_global_key_process().presets == (A, C)
    # 보던 B2 가 지워졌다. 카드의 삭제 경로는 이 칸을 건드리지 않는다 — HOME 본문(앱 전체 회차)이
    # 새 프로필을 읽어 기본(A)으로 다시 적었다. 사이드바 `주요공정 히트맵` 줄이 보는 칸이다.
    assert app.session_state[home_preference.KEY_PROCESS_PRESET_KEY] == A[0]
    assert app.session_state[TAB_KEY] == PREFERENCE
