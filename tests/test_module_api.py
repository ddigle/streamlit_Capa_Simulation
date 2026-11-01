# Purpose: 사내 모듈 창구 module_api 의 문맥·키·데이터 자리·머리말·색·콜백·guard 동작을 고정한다.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from streamlit.errors import FragmentHandledException
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException, StopException
from streamlit.runtime.scriptrunner_utils.script_requests import RerunData
from streamlit.testing.v1 import AppTest

from capa_simulation import module_api, module_failures, module_registry
from capa_simulation.module_api import ModuleContextError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_OK = PROJECT_ROOT / "tests" / "fixtures" / "modules" / "demo_ok"
DEMO_OK_PAGE = DEMO_OK / "demo_ok_page.py"


def _tmp_module(root: Path, module_id: str, page: str, *, maturity: str = "L0") -> Path:
    """tmp 모듈 하나(화면 `page.py`). 화면 파일 경로를 돌려준다."""
    folder = root / module_id
    folder.mkdir(parents=True)
    declared = {
        "id": module_id,
        "name": "시험 모듈",
        "api": 1,
        "owner": "시험 담당",
        "enabled": True,
        "maturity": maturity,
        "pages": [{"slug": "main", "file": "page.py", "title": "시험 화면"}],
    }
    (folder / module_registry.MANIFEST_NAME).write_text(
        json.dumps(declared, ensure_ascii=False), encoding="utf-8"
    )
    path = folder / "page.py"
    path.write_text("# Purpose: 시험 화면.\n" + page, encoding="utf-8")
    return path


# ------------------------------------------------------------------ 문맥


def test_the_context_comes_from_the_nearest_manifest() -> None:
    context = module_api.context(DEMO_OK_PAGE)

    assert (context.id, context.name, context.owner, context.maturity) == (
        "demo_ok",
        "데모 모듈",
        "데모 담당",
        "L0",
    )
    assert context.folder == DEMO_OK
    assert context.api_version == module_api.API_VERSION
    # 문자열 경로(`__file__`)도 같다.
    assert module_api.context(str(DEMO_OK_PAGE)) == context


def test_a_file_outside_any_module_has_no_context(tmp_path: Path) -> None:
    with pytest.raises(ModuleContextError):
        module_api.context(tmp_path / "page.py")


def test_a_broken_manifest_is_a_context_error(tmp_path: Path) -> None:
    page = _tmp_module(tmp_path, "demo_a", "")
    (page.parent / module_registry.MANIFEST_NAME).write_text("{", encoding="utf-8")

    with pytest.raises(ModuleContextError, match="JSON 이 아닙니다"):
        module_api.context(page)


# ------------------------------------------------------------------ 키·데이터 자리


def test_keys_get_the_prefix_once_and_refuse_core_slots() -> None:
    context = module_api.context(DEMO_OK_PAGE)

    assert context.key("name") == "mod_demo_ok__name"
    assert context.key(context.key("name")) == "mod_demo_ok__name"
    for bad in ("", "_x", "mod_demo_ok__", "mod_demo_ok___core_callback_failure"):
        with pytest.raises(ValueError):
            context.key(bad)


def test_the_data_folder_is_made_only_when_read_and_follows_its_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(module_registry.DATA_ROOT_ENV_VAR, str(tmp_path / "data"))
    context = module_api.context(DEMO_OK_PAGE)

    assert not (tmp_path / "data").exists()
    folder = context.data_dir
    assert folder == tmp_path / "data" / "demo_ok" and folder.is_dir()


# ------------------------------------------------------------------ 머리말·색


def _header_script(page: str) -> None:
    from capa_simulation import module_api as api

    api.page_header(api.context(page), "시험 화면", description="설명 한 줄")


@pytest.mark.parametrize(("maturity", "badge"), [("L0", True), ("L1", True), ("L2", False)])
def test_the_header_marks_unfinished_maturity_and_makes_no_session_key(
    tmp_path: Path, maturity: str, badge: bool
) -> None:
    page = _tmp_module(tmp_path, "demo_a", "", maturity=maturity)

    app = AppTest.from_function(_header_script, args=(str(page),)).run()

    assert not app.exception
    assert [title.value for title in app.title] == ["시험 화면"]
    assert any("구현중" in str(markdown.value) for markdown in app.markdown) is badge
    assert [caption.value for caption in app.caption] == ["설명 한 줄"]
    assert list(app.session_state.filtered_state) == []


def test_the_palette_is_read_only() -> None:
    colors = module_api.palette()

    with pytest.raises(TypeError):
        colors["accent"] = "#000000"  # type: ignore[index]


# ------------------------------------------------------------------ 콜백


def test_a_wrapped_callback_passes_its_arguments_and_keeps_its_name() -> None:
    context = module_api.context(DEMO_OK_PAGE)
    seen: list[tuple[Any, ...]] = []

    def remember(*args: Any, **kwargs: Any) -> None:
        seen.append((args, kwargs))

    wrapped = context.callback(remember)
    wrapped(1, flag=True)

    assert seen == [((1,), {"flag": True})]
    assert wrapped.__name__ == "remember"
    assert module_failures.last_failures() == {}


@pytest.mark.parametrize("error", [RuntimeError("콜백 오류"), SystemExit(2)])
def test_a_wrapped_callback_swallows_errors_and_records_them(error: BaseException) -> None:
    context = module_api.context(DEMO_OK_PAGE)

    def boom() -> None:
        raise error

    context.callback(boom)()

    failure = module_failures.last_failures()["demo_ok"]
    assert (failure.where, failure.kind, failure.page) == ("callback", type(error).__name__, "")


@pytest.mark.parametrize("control", [StopException(), RerunException(RerunData())])
def test_a_wrapped_callback_lets_streamlit_control_through(control: BaseException) -> None:
    context = module_api.context(DEMO_OK_PAGE)

    def stop() -> None:
        raise control

    with pytest.raises(type(control)):
        context.callback(stop)()
    assert module_failures.last_failures() == {}


def test_a_failed_callback_leaves_its_marker_in_the_session(tmp_path: Path) -> None:
    page = _tmp_module(
        tmp_path,
        "demo_a",
        """
import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)


def boom() -> None:
    raise ValueError("눌러서 난 오류")


st.button("누르기", key=ctx.key("press"), on_click=ctx.callback(boom))
""",
    )
    app = AppTest.from_file(str(page)).run()
    app.button(key="mod_demo_a__press").click().run()

    assert not app.exception
    marker = app.session_state[module_failures.callback_failure_key("demo_a")]
    assert marker["kind"] == "ValueError" and marker["message"] == "눌러서 난 오류"
    assert marker["frames"] == ["demo_a/page.py:11 in boom"]
    assert module_failures.last_failures()["demo_a"].where == "callback"


# ------------------------------------------------------------------ guard


def test_guard_turns_an_error_into_a_card_in_place(tmp_path: Path) -> None:
    page = _tmp_module(
        tmp_path,
        "demo_a",
        """
import streamlit as st

from capa_simulation import module_api as api

ctx = api.context(__file__)
st.write("앞 줄")
with ctx.guard():
    raise KeyError("자리 오류")
st.write("뒤 줄")
""",
    )
    app = AppTest.from_file(str(page)).run()

    assert not app.exception
    assert [str(element.value) for element in app.markdown] == ["앞 줄", "뒤 줄"]
    (card,) = app.error
    assert "「시험 모듈」 모듈에서 오류가 났습니다" in card.value and "KeyError" in card.value
    assert any("이 자리만 멈췄습니다" in caption.value for caption in app.caption)
    assert module_failures.last_failures()["demo_a"].where == "guard"


@pytest.mark.parametrize(
    "control",
    [StopException(), RerunException(RerunData()), FragmentHandledException(RuntimeError("안쪽"))],
)
def test_guard_lets_control_and_handled_fragment_errors_through(control: BaseException) -> None:
    context = module_api.context(DEMO_OK_PAGE)

    with pytest.raises(type(control)), context.guard():
        raise control
    assert module_failures.last_failures() == {}


def test_the_demo_ok_page_stands_on_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """견본은 빈 데이터 자리로 선다(모듈 시험이 빈 tmp 뿌리로 도는 것과 같다)."""
    monkeypatch.setenv(module_registry.DATA_ROOT_ENV_VAR, str(tmp_path))

    app = AppTest.from_file(str(DEMO_OK_PAGE)).run()
    assert not app.exception
    assert [title.value for title in app.title] == ["데모 화면"]
    app.button(key="mod_demo_ok__add").click().run()

    assert not app.exception
    assert app.session_state["mod_demo_ok__count"] == 1
    assert (tmp_path / "demo_ok").is_dir()
    assert module_failures.last_failures() == {}
