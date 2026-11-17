# Purpose: core 화면의 등급 넷마다 단추 · 탭 · 표지와 접속 명단 · 이 등급으로 보기 · 두 번째 벽.

"""등급 넷마다 core 화면(2026-11-18 접속 등급 — Admin Area · 접속 명단 · 이 등급으로 보기 · 앱 정보
카드 표지 · 개발자 몫 진단).

모든 화면 시험은 「운영 + 통합인증 켜짐」 판정을 거친다(`grade_support.operational_grades` — 가짜
버킷에 명단 · 등급 파일을 올려 넷 계정의 등급을 단언한다). 값은 모두 합성(`demo.*`)이다.
설계 규칙: UI-INP-07(예외 — 등급 밖 기능은 숨김) · UI-NTF-03 · UI-CON-03 · UI-TXT-05(예외) ·
UI-LAY-11 · UI-LAY-12 · UI-LAY-13 · UI-INP-08.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from grade_support import (
    DEMO_DEVELOPER,
    DEMO_EDITOR,
    DEMO_MANAGER,
    DEMO_VIEWER,
    GRADE_PARAMS,
    as_grade,
    assert_refusals_caught,
    preview,
    unrestricted,
    visible_labels,
)
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import grade_store, grades, runtime
from capa_simulation.auth.identity import Identity, identity_from_cookies
from capa_simulation.components import access_list_admin, admin_view, sso_identity

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app_pages" / "admin_area.py"
COVERED_ACTIONS = frozenset({"admin.area", "diag.full"})
# 이 갈래가 받는 자리를 다는 뿌리 파일(장부 쓰기에 이르는 콜백 · 팝업 · 프래그먼트).
ROOT_FILES = (
    "app.py",
    "src/capa_simulation/components/display_order_management.py",
    "src/capa_simulation/components/process_rename_management.py",
)


def _page_script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

source = Path({str(PAGE)!r})
exec(
    compile(source.read_text(encoding="utf-8"), str(source), "exec"),
    {{"__name__": "__main__"}},
)
"""


CARD_SCRIPT = """
from capa_simulation.components.app_credits import render_app_credits
from capa_simulation.components.sso_identity import sso_credit_line, verified_identity

render_app_credits(sso_credit_line(verified_identity()))
"""


def _admin(tmp_path: Path) -> AppTest:
    return AppTest.from_string(_page_script(tmp_path / "scenario.duckdb")).run(timeout=120)


def _locked(app: AppTest) -> bool:
    return [warning.value for warning in app.warning] == [sso_identity.ADMIN_ONLY_NOTICE]


def _identity(loginid: str) -> Identity:
    cfg = runtime.config()
    token = sso_identity.session_cookies()
    found = identity_from_cookies(token, cfg, int(time.time()), renewals=True)
    assert isinstance(found, Identity) and found.loginid == loginid
    return found


@GRADE_PARAMS
def test_only_the_developer_opens_the_admin_area(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    app = _admin(tmp_path)

    assert not list(app.exception), [element.message for element in app.exception]
    if grade == grades.DEVELOPER:
        assert not _locked(app)
        assert len(app.main.tabs) >= 3
        assert access_list_admin.EXPANDER_LABEL in visible_labels(app)
        assert access_list_admin.PREVIEW_LABEL in visible_labels(app)
    else:
        assert _locked(app)
        assert sso_identity.ADMIN_ONLY_NOTICE == "개발자만 여는 화면입니다"
        assert not list(app.main.tabs)
        assert access_list_admin.PREVIEW_LABEL not in visible_labels(app)
    assert sso_identity.admin_area_locked() is (grade != grades.DEVELOPER)
    assert sso_identity.viewer_can("admin.area") is (grade == grades.DEVELOPER)


@GRADE_PARAMS
def test_developer_notes_follow_the_screen_grade(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    assert admin_view.developer_notes_visible() is (grade == grades.DEVELOPER)
    if grade != grades.DEVELOPER:
        assert admin_view.diagnostic_message("짧은 글") == "짧은 글"


def test_off_the_operational_server_the_admin_area_opens_without_a_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unrestricted(monkeypatch)
    app = _admin(tmp_path)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not _locked(app)
    assert access_list_admin.PREVIEW_LABEL not in visible_labels(app)
    assert admin_view.developer_notes_visible()


def test_the_access_list_shows_four_grades_one_menu_and_a_grade_choice_when_adding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_grade(monkeypatch, grades.DEVELOPER)
    app = _admin(tmp_path)

    (frame,) = [table.value for table in app.dataframe if "등급" in table.value.columns]
    shown = dict(zip(frame["계정"], frame["등급"], strict=True))
    assert shown == {
        DEMO_DEVELOPER: "개발자(환경변수)",
        DEMO_MANAGER: "관리자",
        DEMO_EDITOR: "실무자",
        DEMO_VIEWER: "열람",
    }
    labels = visible_labels(app)
    assert access_list_admin.GRADE_MENU_LABEL in labels
    assert "관리자로" not in labels and "일반으로" not in labels, "옛 두 단추는 걷었다"
    assert {"열람", "실무자", "관리자", "개발자"} <= labels
    captions = [str(caption.value) for caption in app.caption]
    assert any("개발자 1(환경변수 1)" in caption for caption in captions), captions
    picker = app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY)
    assert picker.format_func(DEMO_EDITOR) == "demo.editor · DEMO 이대리 · DEMO 팀"
    assert picker.format_func(DEMO_VIEWER) == DEMO_VIEWER, "이름 없는 사람은 계정만"

    app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).set_value([DEMO_DEVELOPER]).run()
    for grade in (grades.VIEWER, grades.EDITOR, grades.MANAGER):
        button = app.button(key=access_list_admin.GRADE_BUTTON_KEY.format(grade=grade))
        assert button.disabled and button.help == access_list_admin.GRADE_LOCKED_WHY
    assert not app.button(key=access_list_admin.GRADE_BUTTON_KEY.format(grade="developer")).disabled

    app.button(key="admin_area_access_list_open_add").click().run()
    radio = app.radio(key=access_list_admin.ADD_GRADE_KEY)
    assert radio.label == "등급" and radio.value == grades.EDITOR, "처음 값 실무자"
    assert list(radio.options) == ["열람", "실무자", "관리자", "개발자"]


def test_a_menu_press_after_losing_the_developer_grade_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """보인 회차와 누른 회차의 등급이 다르면 쓰는 자리(두 번째 벽)가 막고 알림창 · Alarm 에
    한 번."""
    as_grade(monkeypatch, grades.DEVELOPER)
    app = _admin(tmp_path)
    app.multiselect(key=access_list_admin.ACCESS_LIST_REMOVE_KEY).set_value([DEMO_VIEWER]).run()

    as_grade(monkeypatch, grades.MANAGER)
    app.button(key=access_list_admin.GRADE_BUTTON_KEY.format(grade="manager")).click().run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert grade_store.grade_of(runtime.config(), DEMO_VIEWER) == grades.VIEWER
    # 관리자에게는 Admin Area 가 잠겨 펼침이 서지 않는다 — 거절 글은 알림 칸에 담겨 그 칸이 다시
    # 설 때 알림창 · Alarm 으로 나간다(곁에 그리지 않는 꼴 — popup_only).
    queued = app.session_state[access_list_admin.ACCESS_LIST_FLASH_KEY]
    assert queued.message == access_list_admin.NOT_ADMIN_MESSAGE and queued.popup_only
    assert _locked(app)


def test_the_preview_shows_the_chosen_grade_screen_and_ends_from_the_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_grade(monkeypatch, grades.DEVELOPER)
    app = _admin(tmp_path)
    app.radio(key=access_list_admin.PREVIEW_CHOICE_KEY).set_value(grades.EDITOR).run()
    app.button(key=access_list_admin.PREVIEW_START_KEY).click().run()

    assert app.session_state[sso_identity.GRADE_PREVIEW_KEY] == grades.EDITOR
    assert _locked(app), "보는 동안 Admin Area 는 스스로 잠긴다"

    card = AppTest.from_string(CARD_SCRIPT)
    card.session_state[sso_identity.GRADE_PREVIEW_KEY] = grades.EDITOR
    card.run(timeout=60)
    caption = str(card.sidebar.caption[0].value)
    assert "실무자 화면으로 보는 중" in caption
    end = card.button(key=sso_identity.PREVIEW_END_KEY)
    assert end.label == "끝내기"
    end.click().run(timeout=60)
    assert sso_identity.GRADE_PREVIEW_KEY not in card.session_state
    assert "보는 중" not in str(card.sidebar.caption[0].value)


@GRADE_PARAMS
def test_the_card_marks_only_viewer_and_editor(monkeypatch: pytest.MonkeyPatch, grade: str) -> None:
    account = as_grade(monkeypatch, grade)
    line = sso_identity.sso_credit_line(_identity(account))
    assert line is not None
    marked = grade in (grades.VIEWER, grades.EDITOR)
    assert (f" · {grades.label_of(grade)} · " in line) is marked, line
    for other in ("관리자", "개발자"):
        assert f" · {other} · " not in line


def test_the_preview_card_mark_names_the_seen_grade(monkeypatch: pytest.MonkeyPatch) -> None:
    preview(monkeypatch, grades.VIEWER)
    line = sso_identity.sso_credit_line(_identity(DEMO_DEVELOPER))
    assert line is not None and "열람 화면으로 보는 중" in line


def test_off_the_operational_server_the_card_has_no_grade(monkeypatch: pytest.MonkeyPatch) -> None:
    unrestricted(monkeypatch)
    assert sso_identity.sso_credit_line(None) is None
    assert sso_identity.screen_grade() == grades.DEVELOPER


@pytest.fixture
def real_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], AppTest]:
    """빈 DuckDB 를 보는 실제 `app.py` — 브라우저로 보내는 컴포넌트만 바꿔 끼운다
    (`tests/test_admin_area_lock.py` 와 같은 꼴)."""
    import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
    import capa_simulation.components.intro_overlay as intro_overlay
    import capa_simulation.components.intro_summary as intro_summary
    import capa_simulation.components.month_range_picker as month_range_picker
    import capa_simulation.settings as settings

    monkeypatch.setattr(settings, "DUCKDB_PATH", tmp_path / "scenario.duckdb")
    monkeypatch.setattr(settings, "EQUIPMENT_DUCKDB_PATH", tmp_path / "equipment.duckdb")
    monkeypatch.setattr(horizontal_scrollbar, "render_horizontal_scrollbar", lambda *a, **k: None)
    monkeypatch.setattr(intro_overlay, "render_intro_overlay", lambda: None)
    monkeypatch.setattr(intro_summary, "_SUMMARY", lambda **kwargs: None)
    monkeypatch.setattr(
        month_range_picker, "_MONTH_RANGE_APPLY", lambda **kwargs: SimpleNamespace(apply=None)
    )
    return lambda: AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)


def test_a_viewer_first_run_of_the_real_app_stands_on_a_fresh_database(
    real_app: Callable[[], AppTest], monkeypatch: pytest.MonkeyPatch
) -> None:
    """배포 날 모두가 열람이다 — 새 DB 의 첫 회차(첫 데이터 · 표시순서 첫 판은 앱 자신의 쓰기)가
    벽에 걸려 서는 일이 없다. 판정기는 `app.py` 맨 앞이 꽂는다. 화면 본문의 거절은 시험에서 감싸기를
    걷어 예외로 드러난다(conftest)."""
    as_grade(monkeypatch, grades.VIEWER)
    app = real_app().run()

    assert not list(app.exception), [element.message for element in app.exception]
    assert grades.caller_source() is sso_identity.real_caller
    assert "Admin Area" not in [str(link.proto.label) for link in app.sidebar.get("page_link")]
    caption = " ".join(str(item.value) for item in app.sidebar.caption)
    assert " · 열람 · " in caption, "앱 정보 카드의 등급 표지"


def test_this_lane_roots_catch_refusals() -> None:
    """장부 쓰기에 이르는 core 파일의 팝업 · 프래그먼트가 받는 자리를 달았다."""
    assert_refusals_caught(ROOT_FILES)


def test_the_covered_actions_are_known() -> None:
    assert COVERED_ACTIONS <= set(grades.ACTIONS)
