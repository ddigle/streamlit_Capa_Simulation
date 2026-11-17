# Purpose: 등급 넷마다 모듈 화면이 모두 열리고 올리기 · 조회가 등급 벽 없이 기록되는지 본다.

"""모듈은 모두 열람부터(2026-11-17 접속 등급 답 「모듈 화면 '열람' 권한 ok」 — 2차 정한 것).

모듈 화면 · 그 안의 저장 · 올리기 · 공용 BigDataQuery 조회도 열람이 한다. 모듈은 동작 이름이 없어
`COVERED_ACTIONS` 가 비고, 장부 쓰기에 이르는 뿌리를 가진 모듈 파일도 없어 받는 자리 그물에 넘길
파일이 없다. 그래서 이 갈래는 「등급 넷 모두 같은 화면 · 같은 단추」 와 「올리기 · 조회는 벽에
닿지 않고 누가를 남긴다」 를 본다.

모든 화면 시험은 「운영 + 통합인증 켜짐」 판정을 거친다(`grade_support.operational_grades` — 넷
계정의 등급을 단언한다). 그리고 시험마다 지금 등급이 바라는 등급인지, 열람에게 실무자 몫 동작이
정말 막히는지를 함께 본다 — 제한 없는 회차에서 「다 열린다」 가 헛되이 지나가지 않게. 견본은
`tests/fixtures/modules/` 의 합성 `demo_*` 이다.
설계 규칙: UI-INP-07(예외 — 등급 밖 기능은 숨김 · 모듈은 숨길 것이 없음) · UI-TXT-02.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from grade_support import (
    GRADE_PARAMS,
    as_grade,
    assert_refusals_caught,
    judge_spy,
    visible_labels,
)
from streamlit.testing.v1 import AppTest

from capa_simulation import module_helpers, module_registry
from capa_simulation.audit import boot, recorder
from capa_simulation.auth import grades, runtime
from capa_simulation.components import audit_actor, sso_identity
from capa_simulation.io import company_bigdataquery_adapter as adapter
from capa_simulation.io import object_storage

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "modules"
INDEX_PAGE = "app_pages/internal_modules.py"
DEMO_OK_PAGE = "tests/fixtures/modules/demo_ok/demo_ok_page.py"
DEMO_OK_BUTTONS = {"하나 더", "올리기", "받기", "조회"}
# 모듈은 동작 이름이 없다 — 등급으로 가르는 단추가 없다.
COVERED_ACTIONS: frozenset[str] = frozenset()
# 이 갈래가 받는 자리를 다는 뿌리 파일 — 장부 쓰기에 이르는 모듈 화면 파일은 없다.
ROOT_FILES: tuple[str, ...] = ()


@pytest.fixture
def real_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], AppTest]:
    """빈 DuckDB 를 보는 실제 `app.py` + 견본 모듈 뿌리(`test_grade_ui_core.py` 와 같은 꼴)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, str(FIXTURES))
    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return lambda: AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)


def _ok(app: AppTest) -> AppTest:
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def _the_judge_is_live(grade: str) -> None:
    """지금 등급이 바라는 등급이고, 열람이면 실무자 몫이 정말 막힌다(헛돌기 막음)."""
    assert sso_identity.real_caller() == grades.Caller(grade)
    assert grades.allowed("scenario.revision_save") is grades.at_least(grade, grades.EDITOR)


@GRADE_PARAMS
def test_every_grade_opens_the_module_index_and_the_module_page_alike(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    """실제 `app.py` 로 색인 화면과 견본 모듈 화면을 연다 — 등급 넷 모두 멈춤 글 없이 같은 단추가
    선다(모듈은 열람부터 · 모듈 멈춤은 없다 — 2차 정한 것)."""
    as_grade(monkeypatch, grade)
    _the_judge_is_live(grade)
    app = _ok(real_app().run())

    app.switch_page(INDEX_PAGE).run()
    _ok(app)
    assert [title.value for title in app.title] == ["모듈"]
    assert not app.warning, [warning.value for warning in app.warning]
    heads = [str(markdown.value) for markdown in app.markdown if "담당" in str(markdown.value)]
    assert [head.split(" · ")[0] for head in heads] == [
        "**데모 모듈**",
        "**데모 고장**",
        "**데모 키**",
    ]

    app.switch_page(DEMO_OK_PAGE).run()
    _ok(app)
    assert [title.value for title in app.title] == ["데모 화면"]
    assert DEMO_OK_BUTTONS <= visible_labels(app)
    stops = [grades.stop_text(action, place="page") for action in grades.ACTIONS]
    assert not any(str(warning.value) in stops for warning in app.warning)


def _module_page_script(page: Path) -> str:
    """모듈 화면 원문을 판정기 꽂기 + 거절 알림 내기 + 실제 화면 감싸기로 두른 AppTest 원문
    (`grade_support.grade_page_script` 와 같은 차례 — 모듈 화면은 `api.context(__file__)` 로 제
    이름표를 받으므로 `__file__` 을 함께 준다)."""
    return f"""
import grade_support
from capa_simulation.components import grade_ui

grade_ui.install()
grade_ui.emit()


def _page() -> None:
    source = {str(page)!r}
    with open(source, encoding="utf-8") as handle:
        code = compile(handle.read(), source, "exec")
    exec(code, {{"__name__": "__main__", "__file__": source}})


grade_support.REAL_RUN_CORE_PAGE(_page, page="", href="")
"""


class _FakePackage:
    """`bigdataquery` 대역(합성 답)."""

    def getData(self, **_: object) -> pd.DataFrame:  # noqa: N802 — 패키지 이름 그대로
        return pd.DataFrame({"값": [1, 2]})


@pytest.mark.parametrize("grade", [grades.VIEWER, grades.EDITOR])
def test_a_low_grade_uploads_and_queries_from_a_module_and_the_work_log_names_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, grade: str
) -> None:
    """열람 · 실무자도 모듈 안에서 올리고 조회한다 — 등급 판정(`grades.require`)이 한 번도 서지
    않고, 작업 기록에는 그 사람 · 그 등급 · 대상 모듈 · 결과 낱말과 크기만 남는다(파일 이름 · 값
    없음)."""
    account = as_grade(monkeypatch, grade)
    _the_judge_is_live(grade)
    cfg = runtime.config()
    monkeypatch.setenv(module_registry.DATA_ROOT_ENV_VAR, str(tmp_path / "module-data"))
    monkeypatch.setenv(object_storage.MODE_ENV, object_storage.MODE_MANAGED)
    monkeypatch.setattr(adapter, "load_bigdataquery_module", _FakePackage)
    recorder.start(env="cdep", version="test", inst="abcabcabcabc")
    recorder.set_grader(boot.grader(cfg))
    audit_actor.install()

    app = _ok(AppTest.from_string(_module_page_script(ROOT / DEMO_OK_PAGE)).run(timeout=60))
    (tmp_path / "module-data" / "demo_ok" / "demo.csv").write_bytes(b"secret-value\n")
    with judge_spy() as seen:
        app.button(key="mod_demo_ok__upload").click().run()
        app.button(key="mod_demo_ok__ask").click().run()
    _ok(app)

    assert app.session_state["mod_demo_ok__store"] == "올림"
    assert app.session_state["mod_demo_ok__query"] == "2행"
    assert seen == [], "모듈 안의 일은 등급 벽에 닿지 않는다"
    lines = [
        line
        for line in recorder.take_pending()
        if line["ev"] in (module_helpers.AUDIT_UPLOAD, module_helpers.AUDIT_QUERY)
    ]
    assert [(line["ev"], line["actor"], line["grade"], line["out"]) for line in lines] == [
        (module_helpers.AUDIT_UPLOAD, account, grade, "success"),
        (module_helpers.AUDIT_QUERY, account, grade, "success"),
    ]
    assert [line["det"] for line in lines] == [
        {"result": module_helpers.AUDIT_RESULT_OK, "bytes": 13},
        {"result": module_helpers.AUDIT_RESULT_OK, "rows": 2},
    ]
    assert all(line["tgt"] == {"type": "module", "id": "demo_ok"} for line in lines)
    assert "demo.csv" not in repr(lines) and "secret-value" not in repr(lines)


def test_this_lane_roots_catch_refusals() -> None:
    """장부 쓰기에 이르는 모듈 화면 파일이 없다 — 넘길 뿌리 파일이 비어도 그물은 돈다."""
    assert_refusals_caught(ROOT_FILES)


def test_the_covered_actions_are_known() -> None:
    assert COVERED_ACTIONS <= set(grades.ACTIONS)
    assert not any(action.startswith("module") for action in grades.ACTIONS), (
        "모듈은 동작 이름이 없다 — 모두 열람부터(2차 정한 것)"
    )
