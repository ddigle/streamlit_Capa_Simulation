# Purpose: 진짜 app.py 로 사내 모듈 상자·화면 감싸기·콜백·프래그먼트·키 알림·등록 실패 격리를 본다.

"""사내 모듈 런타임 — 진짜 `app.py` 를 `AppTest.from_file` 로 돈다(`_app` 준비는 내비 시험 꼴).

뿌리는 견본(`tests/fixtures/modules`) 이거나 tmp 모듈(`<tmp>/modules`)이다 — `CAPA_MODULES_ROOT`
환경변수로 돌린다. 기본(conftest)은 없는 자리라 모듈이 없을 때 사이드바·Admin 이 바탕과 같다.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import warnings
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from streamlit.errors import StreamlitPageNotFoundError
from streamlit.testing.v1 import AppTest

from capa_simulation import module_failures, module_registry, navigation
from capa_simulation.navigation import DYNAMIC_CAPA, HOME, PageSpec
from capa_simulation.page_tabs_state import valid_tabs
from capa_simulation.sidebar_status import APP_RUN_STATE_KEY, CONDITIONS_BOX_KEY

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "modules"
DEMO_OK_PAGE = "tests/fixtures/modules/demo_ok/demo_ok_page.py"
DEMO_OK_SECOND = "tests/fixtures/modules/demo_ok/demo_ok_second.py"
DEMO_CRASH_PAGE = "tests/fixtures/modules/demo_crash/demo_crash_page.py"
DEMO_CRASH_IMPORT = "tests/fixtures/modules/demo_crash/demo_crash_import.py"
DEMO_KEYS_PAGE = "tests/fixtures/modules/demo_keys/demo_keys_page.py"
MODULE_BOX = f"{navigation.MODULE_GROUP_SLUG}_box"
SUPPORT_BOX = "sidebar_admin_box"
CALLS: list[str] = []


@pytest.fixture
def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """빈 DuckDB 를 보는 `app.py`(내장 시드가 부트스트랩을 채운다). 뿌리는 시험이 고른다."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    CALLS.clear()
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    # 입장 화면(Components v2)은 부른 것만 센다.
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: CALLS.append("intro"))
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    real_warm = intro_summary.warm_intro_summary

    def counted_warm(path: str) -> None:
        CALLS.append("warm")
        real_warm(path)

    monkeypatch.setattr(intro_summary, "warm_intro_summary", counted_warm)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return AppTest.from_file(str(APP_PATH), default_timeout=300)


@pytest.fixture
def _fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(FIXTURES))


def _ok(app: AppTest) -> AppTest:
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _sidebar_keys(app: AppTest) -> list[str]:
    keys: list[str] = []
    for node in app.sidebar.children.values():
        identifier = str(getattr(getattr(node, "proto", None), "id", "") or "")
        keys.append(identifier.rsplit("-", 1)[-1] if identifier else "")
    return keys


def _find_block(node: Any, suffix: str) -> Any:
    for child in getattr(node, "children", {}).values():
        identifier = str(getattr(getattr(child, "proto", None), "id", "") or "")
        if identifier.endswith(suffix):
            return child
        found = _find_block(child, suffix)
        if found is not None:
            return found
    return None


def _box_links(app: AppTest) -> list[str]:
    box = _find_block(app.sidebar, MODULE_BOX)
    assert box is not None, _sidebar_keys(app)
    return [link.proto.label for link in box.get("page_link")]


def _expander_labels(app: AppTest) -> list[str]:
    """펼침 제목 — 아이콘이 달린 펼침을 AppTest 는 `status` 로 센다."""
    return [item.label for item in app.expander] + [item.label for item in app.status]


def _texts(app: AppTest, kind: str) -> list[str]:
    return [str(element.value) for element in getattr(app, kind)]


# ------------------------------------------------------------------ 상자


def test_the_module_box_stands_after_dynamic_and_before_support(
    _app: AppTest, _fixtures: None
) -> None:
    app = _ok(_app.run())
    keys = [key for key in _sidebar_keys(app) if key]

    dynamic = keys.index("dynamic_capa_box")
    assert keys.index(MODULE_BOX) == dynamic + 1
    assert keys.index(SUPPORT_BOX) > keys.index(MODULE_BOX)
    # 켜진 모듈 셋(demo_ok 둘, demo_crash 둘, demo_keys 하나)만 — 꺼짐·다음 판·틀린 선언은 없다.
    assert _box_links(app) == [
        "현황 요약",
        "데모 화면 (구현중)",
        "데모 둘째 (구현중)",
        "고장 데모 (구현중)",
        "패키지 없음 데모 (구현중)",
        "키 데모 (구현중)",
    ]


@pytest.mark.parametrize("root", ["absent", "off"])
def test_without_modules_the_sidebar_is_unchanged(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, root: str
) -> None:
    """모듈이 없으면(사외는 늘 그렇다) 상자도 Admin 펼침도 없다 — 사이드바가 바탕과 같다."""
    monkeypatch.setenv(
        module_registry.ROOT_ENV_VAR, "off" if root == "off" else str(tmp_path / "none")
    )
    app = _ok(_app.run())

    assert MODULE_BOX not in _sidebar_keys(app)
    assert all("사내 모듈" not in link.proto.label for link in app.sidebar.get("page_link"))
    app.switch_page("app_pages/admin_area.py").run()
    _ok(app)
    labels = _expander_labels(app)
    assert not any("사내 모듈 상태" in label for label in labels)


def test_every_module_switched_off_hides_the_box_but_admin_still_tells(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch, _fixtures: None
) -> None:
    monkeypatch.setenv(module_registry.DISABLED_ENV_VAR, "*")
    app = _ok(_app.run())

    assert MODULE_BOX not in _sidebar_keys(app)
    app.switch_page("app_pages/admin_area.py").run()
    _ok(app)
    labels = _expander_labels(app)
    assert "사내 모듈 상태 — 켜짐 0 · 꺼짐 4 · 실패 2" in labels


# ------------------------------------------------------------------ 화면 실행


def test_a_module_page_opens_at_its_address_without_the_condition_panel(
    _app: AppTest, _fixtures: None
) -> None:
    app = _ok(_app.run())
    app.switch_page(DEMO_OK_PAGE).run()
    _ok(app)

    assert app.session_state["sidebar_last_page"] == "mod-demo_ok-main"
    assert _texts(app, "title") == ["데모 화면"]
    assert CONDITIONS_BOX_KEY not in _sidebar_keys(app)
    # 거짓 키 알림이 없다 — 코어 사이드바 위젯 값을 읽어도 `id` 가 같다.
    assert not any("접두 없는 세션 키" in text for text in _texts(app, "warning"))
    assert module_failures.key_warnings() == {}
    assert "demo_ok" in module_failures.last_run_seconds()
    # 모듈 화면 회차도 끝까지 돈 회차다 — 입장 화면을 걸고 Summary 를 데운다.
    assert CALLS.count("intro") == 2 and CALLS.count("warm") == 2
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True


def test_a_crashing_page_shows_only_its_card_and_the_app_goes_on(
    _app: AppTest, _fixtures: None
) -> None:
    app = _ok(_app.run())
    app.switch_page(DEMO_CRASH_PAGE).run()
    _ok(app)

    (card,) = _texts(app, "error")
    assert "「데모 고장」 모듈의 「고장 데모」 화면에서 오류가 났습니다" in card
    assert "RuntimeError" in card and "데모 오류" in card
    assert any("이 화면만 멈췄습니다" in text for text in _texts(app, "caption"))
    assert "오류 앞까지 그린 줄입니다." in _texts(app, "markdown")
    assert module_failures.last_failures()["demo_crash"].where == "page"
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True
    # 사이드바·상자는 그대로이고, HOME 으로 옮겨도 정상이다.
    assert MODULE_BOX in _sidebar_keys(app) and "home_navigation" in _sidebar_keys(app)
    app.switch_page(HOME.path).run()
    _ok(app)
    assert not _texts(app, "error")


def test_a_missing_package_card_points_to_the_outside_request(
    _app: AppTest, _fixtures: None
) -> None:
    app = _ok(_app.run())
    app.switch_page(DEMO_CRASH_IMPORT).run()
    _ok(app)

    assert any("ModuleNotFoundError" in text for text in _texts(app, "error"))
    hint = [text for text in _texts(app, "caption") if "사외 요청" in text]
    assert hint and "demo_not_installed_package" in hint[0]
    assert "담당자가 앱 관리자에게" in hint[0]


def test_an_unprefixed_key_is_reported_and_recorded(_app: AppTest, _fixtures: None) -> None:
    app = _ok(_app.run())
    app.switch_page(DEMO_KEYS_PAGE).run()
    _ok(app)

    (warning,) = [text for text in _texts(app, "warning") if "접두 없는 세션 키" in text]
    assert "새로 1 · 바꿈 0 · 지움 0" in warning and "plain" in warning
    assert module_failures.key_warnings() == {"demo_keys": ("plain_key",)}


# ------------------------------------------------------------------ tmp 모듈


def _module(root: Path, module_id: str, pages: dict[str, str], *, title: str = "") -> Path:
    """tmp 모듈 — 화면 파일 이름 → 본문. 본문 앞에 문맥과 머리말을 붙인다."""
    folder = root / module_id
    folder.mkdir(parents=True)
    declared = {
        "id": module_id,
        "name": f"시험 {module_id.removeprefix('demo_')}",
        "api": 1,
        "owner": "시험 담당",
        "enabled": True,
        "maturity": "L0",
        "pages": [
            {
                "slug": Path(file).stem,
                "file": file,
                "title": title if title and index == 0 else f"{module_id[5:]} {Path(file).stem}",
            }
            for index, file in enumerate(pages)
        ],
    }
    (folder / module_registry.MANIFEST_NAME).write_text(
        json.dumps(declared, ensure_ascii=False), encoding="utf-8"
    )
    for file, body in pages.items():
        (folder / file).write_text(
            "# Purpose: 시험 화면.\nimport streamlit as st\n\n"
            "from capa_simulation import module_api as api\n\n"
            "ctx = api.context(__file__)\n" + body,
            encoding="utf-8",
        )
    return folder


LAB_PAGES = {
    "callback.py": (
        "def boom() -> None:\n    raise ValueError('누른 오류')\n\n"
        "st.write('콜백 화면 본문')\n"
        "st.button('누르기', key=ctx.key('press'), on_click=ctx.callback(boom))\n"
    ),
    "leave.py": "raise SystemExit(2)\n",
    "frag.py": ("@st.fragment\ndef part() -> None:\n    raise ValueError('조각 오류')\n\npart()\n"),
    "guarded.py": (
        "@st.fragment\ndef part() -> None:\n    with ctx.guard():\n"
        "        raise ValueError('감싼 조각 오류')\n\npart()\nst.write('조각 뒤 본문')\n"
    ),
    "stop.py": "st.session_state['plain_stop'] = 1\nst.write('멈춤 앞')\nst.stop()\n",
    "again.py": (
        "if st.button('다시', key=ctx.key('again')):\n    st.rerun()\nst.write('다시 화면')\n"
    ),
    "drop.py": "del st.session_state['plain_seed']\n",
    "swap.py": "st.session_state['plain_seed'] = 2\n",
}


@pytest.fixture
def _lab(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "modules"
    _module(root, "demo_lab", LAB_PAGES)
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(root))
    return root / "demo_lab"


def test_a_failing_callback_keeps_the_whole_shell_and_shows_a_card_on_top(
    _app: AppTest, _lab: Path
) -> None:
    app = _ok(_app.run())
    app.switch_page(str(_lab / "callback.py")).run()
    _ok(app)
    app.button(key="mod_demo_lab__press").click().run()
    _ok(app)

    (card,) = _texts(app, "error")
    assert card.startswith("방금 한 동작에서 오류가 났습니다")
    assert "ValueError" in card and "누른 오류" in card
    # 카드는 화면 맨 위(본문보다 앞)에 선다.
    main = [str(getattr(element, "value", "")) for element in app.main]
    assert main.index(card) < main.index("콜백 화면 본문")
    assert module_failures.last_failures()["demo_lab"].where == "callback"
    assert MODULE_BOX in _sidebar_keys(app) and "home_navigation" in _sidebar_keys(app)
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True


def test_system_exit_in_a_page_is_a_card_and_the_session_goes_on(_app: AppTest, _lab: Path) -> None:
    app = _ok(_app.run())
    app.switch_page(str(_lab / "leave.py")).run()
    _ok(app)

    assert any("SystemExit" in text for text in _texts(app, "error"))
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True
    app.switch_page(HOME.path).run()
    _ok(app)


def test_a_fragment_error_in_a_full_run_is_recorded_and_the_run_completes(
    _app: AppTest, _lab: Path
) -> None:
    app = _ok(_app.run())
    app.switch_page(str(_lab / "frag.py")).run()

    # Streamlit 이 프래그먼트 안에 그린 오류 하나뿐이고 모듈 카드는 없다.
    assert len(app.exception) == 1
    assert not _texts(app, "error")
    assert module_failures.last_failures()["demo_lab"].kind == "ValueError"
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True


def test_a_guarded_fragment_error_is_a_card_in_place(_app: AppTest, _lab: Path) -> None:
    app = _ok(_app.run())
    app.switch_page(str(_lab / "guarded.py")).run()
    _ok(app)

    (card,) = _texts(app, "error")
    assert "「시험 lab」 모듈에서 오류가 났습니다" in card and "감싼 조각 오류" in card
    assert "조각 뒤 본문" in _texts(app, "markdown")
    assert module_failures.last_failures()["demo_lab"].where == "guard"


CANCEL_PAGES = {
    "cancel.py": "import asyncio\n\nst.write('취소 앞')\nraise asyncio.CancelledError()\n",
    "cancelcb.py": (
        "import asyncio\n\n\ndef cancel() -> None:\n    raise asyncio.CancelledError()\n\n\n"
        "st.write('취소 콜백 화면')\n"
        "st.button('취소', key=ctx.key('cancel'), on_click=ctx.callback(cancel))\n"
    ),
    "cancelguard.py": (
        "import asyncio\n\nwith ctx.guard():\n    raise asyncio.CancelledError()\n"
        "st.write('취소 자리 뒤')\n"
    ),
}


def test_a_base_exception_outside_exception_is_a_card_and_the_session_goes_on(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`asyncio.CancelledError` 는 `Exception` 이 아니다(3.8~).

    `SystemExit` 처럼 두면 회차 스레드가 끝나 세션이 「실행 중」 에 머문다. 화면 본문·콜백·guard
    셋 다 카드로 바뀌고 회차가 끝나야 한다.
    """
    root = tmp_path / "modules"
    folder = _module(root, "demo_cancel", CANCEL_PAGES)
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(root))
    app = _ok(_app.run())

    app.switch_page(str(folder / "cancel.py")).run(timeout=60)
    _ok(app)
    assert any("CancelledError" in text for text in _texts(app, "error"))
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True

    app.switch_page(str(folder / "cancelcb.py")).run(timeout=60)
    app.button(key="mod_demo_cancel__cancel").click().run(timeout=60)
    _ok(app)
    (card,) = _texts(app, "error")
    assert card.startswith("방금 한 동작에서 오류가 났습니다") and "CancelledError" in card
    assert module_failures.last_failures()["demo_cancel"].where == "callback"

    app.switch_page(str(folder / "cancelguard.py")).run(timeout=60)
    _ok(app)
    assert any("CancelledError" in text for text in _texts(app, "error"))
    assert "취소 자리 뒤" in _texts(app, "markdown")
    assert module_failures.last_failures()["demo_cancel"].where == "guard"

    app.switch_page(HOME.path).run(timeout=60)
    _ok(app)


def test_a_stopping_page_reports_its_unprefixed_key_on_the_next_run(
    _app: AppTest, _lab: Path
) -> None:
    app = _ok(_app.run())
    app.switch_page(str(_lab / "stop.py")).run()
    _ok(app)

    assert not _texts(app, "error")
    assert app.session_state[APP_RUN_STATE_KEY]["complete"] is True
    assert module_failures.key_warnings() == {"demo_lab": ("plain_stop",)}
    # 멈춘 회차에는 그릴 수 없어 다음 회차 맨 위에 선다.
    app.run()
    _ok(app)
    assert any("접두 없는 세션 키" in text for text in _texts(app, "warning"))


def test_a_rerun_button_reruns_without_a_card(_app: AppTest, _lab: Path) -> None:
    app = _ok(_app.run())
    app.switch_page(str(_lab / "again.py")).run()
    app.button(key="mod_demo_lab__again").click().run()
    _ok(app)

    assert not _texts(app, "error")
    assert "다시 화면" in _texts(app, "markdown")


@pytest.mark.parametrize(("page", "expected"), [("drop.py", "지움 1"), ("swap.py", "바꿈 1")])
def test_deleting_or_replacing_an_unprefixed_key_is_reported(
    _app: AppTest, _lab: Path, page: str, expected: str
) -> None:
    app = _ok(_app.run())
    app.session_state["plain_seed"] = 1
    app.switch_page(str(_lab / page)).run()
    _ok(app)

    (warning,) = [text for text in _texts(app, "warning") if "접두 없는 세션 키" in text]
    assert expected in warning and "plain" in warning


@pytest.fixture
def _forget_modules_package() -> Iterator[None]:
    before = {name for name in sys.modules if name == "modules" or name.startswith("modules.")}
    yield
    for name in [name for name in sys.modules if name == "modules" or name.startswith("modules.")]:
        if name not in before:
            del sys.modules[name]


def test_a_helper_imports_through_the_modules_package_and_a_bare_name_breaks(
    _app: AppTest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    _forget_modules_package: None,
) -> None:
    root = tmp_path / "modules"
    folder = _module(
        root,
        "demo_helper",
        {
            "page.py": (
                "from modules.demo_helper import lab_helper\n\nst.write(lab_helper.GREETING)\n"
            ),
            "bare.py": "import lab_helper\n\nst.write(lab_helper.GREETING)\n",
        },
    )
    (folder / "lab_helper.py").write_text(
        "# Purpose: 도움 코드.\nGREETING = '도움 코드 인사'\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(root))
    app = _ok(_app.run())

    app.switch_page(str(folder / "page.py")).run()
    _ok(app)
    assert "도움 코드 인사" in _texts(app, "markdown")
    assert not _texts(app, "error")

    app.switch_page(str(folder / "bare.py")).run()
    _ok(app)
    assert any("ModuleNotFoundError" in text for text in _texts(app, "error"))
    captions = _texts(app, "caption")
    assert any("from modules.demo_helper import lab_helper" in text for text in captions)
    assert not any("사외 요청" in text for text in captions)


def test_a_page_that_cannot_be_registered_is_left_out_until_restart(
    _app: AppTest, monkeypatch: pytest.MonkeyPatch, _fixtures: None
) -> None:
    real_to_page = PageSpec.to_page

    def failing(self: PageSpec) -> Any:
        if self.url_path == "mod-demo_ok-second":
            raise StreamlitPageNotFoundError("demo_ok_second.py")
        return real_to_page(self)

    monkeypatch.setattr(PageSpec, "to_page", failing)
    app = _ok(_app.run())
    first = (_sidebar_keys(app), _box_links(app))
    app.run()
    _ok(app)

    assert (_sidebar_keys(app), _box_links(app)) == first
    assert "데모 둘째 (구현중)" not in first[1]
    assert ("demo_ok", "second") in module_failures.excluded_pages()
    failure = module_failures.last_failures()["demo_ok"]
    assert (failure.where, failure.page) == ("load", "second")
    assert DEMO_OK_SECOND not in valid_tabs() and DEMO_OK_PAGE in valid_tabs()

    monkeypatch.setattr(PageSpec, "to_page", real_to_page)
    app.run()
    _ok(app)
    assert "데모 둘째 (구현중)" not in _box_links(app)


def test_the_core_dynamic_box_is_untouched_by_modules(_app: AppTest, _fixtures: None) -> None:
    app = _ok(_app.run())
    app.switch_page(DYNAMIC_CAPA.path).run()
    _ok(app)

    assert app.session_state["dynamic_capa_box"] is True
    assert app.session_state[MODULE_BOX] is False


# ------------------------------------------------------------------ 지킴


def _top_level_imports(path: Path) -> set[str]:
    with warnings.catch_warnings():  # 남의 소스의 낡은 이스케이프 경고는 이 지킴과 상관없다
        warnings.simplefilter("ignore", DeprecationWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".", 1)[0])
    return names


def test_the_core_never_imports_the_modules_package() -> None:
    """의존 방향은 모듈 → 코어 창구 하나다 — 코어는 `modules` 를 import 하지 않는다(지킴)."""
    files = [APP_PATH, *(PROJECT_ROOT / "app_pages").glob("*.py")]
    files += [*(PROJECT_ROOT / "src").rglob("*.py"), *(PROJECT_ROOT / "scripts").glob("*.py")]

    offenders = [path for path in files if "modules" in _top_level_imports(path)]
    assert not offenders, offenders


def test_no_regular_modules_package_hides_the_namespace() -> None:
    """저장소 뿌리에 `__init__.py` 가 있는 `modules` 가 없다 — 있으면 이름공간을 가린다(지킴)."""
    spec = importlib.util.find_spec("modules")

    assert spec is None or spec.origin in (None, "namespace")
    assert not (PROJECT_ROOT / "modules" / "__init__.py").exists()


# ------------------------------------------------------------------ 키 견주기(가짜 세션)


class _FakeState(dict[str, Any]):
    """`to_dict()` 가 `fresh` 칸을 읽을 때마다 새 객체로 돌려주는 세션(Components v2 위젯 값 꼴)."""

    fresh: frozenset[str] = frozenset()

    def to_dict(self) -> dict[str, Any]:
        return {key: (object() if key in self.fresh else value) for key, value in self.items()}


def test_values_rebuilt_on_every_read_are_not_reported_as_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """브라우저 확인에서 입장 화면·Summary·탭 줄(Components v2) 칸이 「바꿈 3」 으로 거짓 알렸다."""
    from capa_simulation import module_runtime

    state = _FakeState(page_tabs_strip={}, plain=object())
    state.fresh = frozenset({"page_tabs_strip"})
    warned: list[str] = []
    monkeypatch.setattr(
        module_runtime,
        "st",
        SimpleNamespace(session_state=state, warning=lambda text, icon=None: warned.append(text)),
    )
    spec = PageSpec(
        "modules/demo_a/page.py", "시험 (구현중)", url_path="mod-demo_a-main", module="demo_a"
    )

    module_runtime.run_module_page(lambda: None, spec)
    assert warned == []

    def replace_plain() -> None:
        state["plain"] = object()

    module_runtime.run_module_page(replace_plain, spec)
    (warning,) = warned
    assert "새로 0 · 바꿈 1 · 지움 0" in warning and "plain" in warning
