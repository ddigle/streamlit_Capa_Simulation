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
from alert_marks import active_state, states
from edit_grid_fake import install_fake_edit_grid, last, send_ops, shell_frame
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
from capa_simulation.auth.access import SourceProblem
from capa_simulation.auth.identity import Identity, identity_from_cookies
from capa_simulation.components import (
    access_list_admin,
    access_list_grid,
    admin_view,
    grade_ui,
    route_load_exception_admin,
    sso_identity,
    sso_status,
)
from capa_simulation.services.route_load_exceptions import ROUTE_LOAD_FORMULAS

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


ACCESS_ALERTS_SCRIPT = """
from capa_simulation.components import sso_status

sso_status.render_access_alerts()
sso_status.render_audit_alerts()
"""


def test_a_preview_leaves_the_developer_server_alerts_standing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """「이 등급으로 보기」 는 화면만 바꾼다 — 서 있던 개발자 상태 알림(등급 파일 못 읽음 `AD-25`)이
    미리 보기를 켜도 해소되지 않고(끄면 「새로 뜸」 으로 다시 서지 않고) 그대로 서 있다. 진단 글 ·
    Admin Area 는 미리 보기를 따른다(보는 등급으로 잠김)."""
    as_grade(monkeypatch, grades.DEVELOPER)
    monkeypatch.setattr(grade_store, "read_problem", lambda _cfg: SourceProblem("http", 503))

    seen = AppTest.from_string(ACCESS_ALERTS_SCRIPT, default_timeout=30).run()
    preview(monkeypatch, grades.VIEWER)
    previewed = AppTest.from_string(ACCESS_ALERTS_SCRIPT, default_timeout=30).run()

    for app in (seen, previewed):
        assert not list(app.exception), [element.message for element in app.exception]
        assert active_state(app, "AD-25") is not None
    assert [note["code"] for note in states(seen)] == [note["code"] for note in states(previewed)]
    assert admin_view.developer_alerts_visible()
    assert not admin_view.developer_notes_visible(), "진단 글은 미리 보기를 따른다"
    assert sso_identity.admin_area_locked()


def test_the_sso_status_counts_the_list_by_the_four_grades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """「통합인증 점검」 의 접속 명단 줄은 등급 넷으로 센다(「접속 명단」 표와 같은 판정 — 옛 두
    등급의 「일반」 이 없다)."""
    as_grade(monkeypatch, grades.DEVELOPER)
    line = sso_status.access_line(runtime.config())
    assert "· 켜짐 · 개발자 1 · 관리자 1 · 실무자 1 · 열람 1 · 읽지 못함 0" in line, line
    assert "일반" not in line


@GRADE_PARAMS
def test_developer_server_alerts_follow_the_real_grade(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    assert admin_view.developer_alerts_visible() is (grade == grades.DEVELOPER)


def test_off_the_operational_server_the_admin_area_opens_without_a_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unrestricted(monkeypatch)
    app = _admin(tmp_path)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not _locked(app)
    assert access_list_admin.PREVIEW_LABEL not in visible_labels(app)
    assert admin_view.developer_notes_visible()


def test_the_access_list_is_one_edit_grid_with_four_grades_and_locked_own_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """접속 명단은 범용 편집 그리드의 줄 규칙 표다(2026-11-18 구현 확인 보드 「고칠 것」) — 등급은
    고르기 칸(열람 · 실무자 · 관리자 · 개발자), 나 자신 · 환경변수 개발자 줄은 등급 칸 · 줄 지우기가
    잠기고, 옛 「사람 고르기」 · 「등급 바꾸기」 · 「추가」 창 · 「지우기」 는 없다."""
    calls = install_fake_edit_grid(monkeypatch)
    as_grade(monkeypatch, grades.DEVELOPER)
    app = _admin(tmp_path)

    shell = last(calls, access_list_grid.HOST)
    frame = shell_frame(shell)
    options = shell["fmts"][-1]["options"]
    assert options == ["열람", "실무자", "관리자", "개발자"]
    listed = frame[frame["계정"].notna()]
    shown = {row["계정"]: options[int(row["등급"])] for _, row in listed.iterrows()}
    assert shown == {
        DEMO_DEVELOPER: "개발자",
        DEMO_MANAGER: "관리자",
        DEMO_EDITOR: "실무자",
        DEMO_VIEWER: "열람",
    }
    editor = listed.set_index("계정").loc[DEMO_EDITOR]
    assert (editor["이름"], editor["부서"]) == ("DEMO 이대리", "DEMO 팀")
    kinds = dict(zip(shell["ids"], shell["locks"]["rows"], strict=True))
    assert kinds[DEMO_DEVELOPER] == access_list_grid.SELF, "나 자신(환경변수 개발자이기도)"
    assert kinds[DEMO_VIEWER] == access_list_grid.LISTED
    labels = visible_labels(app)
    for gone in ("등급 바꾸기", "추가", "지우기", "관리자로", "일반으로", "사람 고르기"):
        assert gone not in labels, gone
    # 옛 「사람 고르기」 다중 선택이 없다 — 남는 다중 선택은 같은 화면 「부하 예외」 탭의 산식마다
    # 공정 고르기 칸뿐이다(닫힌 탭에도 서야 값이 남는다).
    assert sorted(str(box.key) for box in app.multiselect) == sorted(
        route_load_exception_admin.pick_slot(formula).key for formula in ROUTE_LOAD_FORMULAS
    )
    captions = [str(caption.value) for caption in app.caption]
    assert any("개발자 1(환경변수 1)" in caption for caption in captions), captions
    save = app.button(key=access_list_admin.SAVE_KEY)
    assert not save.disabled and save.help == access_list_admin.SAVE_HELP, "늘 켜짐 — UI-INP-07"


def test_a_save_after_losing_the_developer_grade_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """보인 회차와 누른 회차의 등급이 다르면 저장 콜백이 쓰는 순간의 실제 등급으로 막고 알림창 ·
    Alarm 에 한 번."""
    calls = install_fake_edit_grid(monkeypatch)
    as_grade(monkeypatch, grades.DEVELOPER)
    app = _admin(tmp_path)
    app = send_ops(
        app,
        calls,
        {"op": "write", "rows": [DEMO_VIEWER], "cols": ["등급"], "values": [["관리자"]]},
        host=access_list_grid.HOST,
    )
    assert not app.button(key=access_list_admin.SAVE_KEY).disabled

    as_grade(monkeypatch, grades.MANAGER)
    app.button(key=access_list_admin.SAVE_KEY).click().run()

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


# ------------------------------------------------------------------ 화면 쪽 창구(grade_ui) 계약
STOP_PAGE = """
import streamlit as st
from capa_simulation.components import grade_ui

grade_ui.stop_unless("admin.area", place="page")
st.write("after")
"""

STOP_TAB = """
import streamlit as st
from capa_simulation.components import grade_ui

grade_ui.stop_unless(
    "scenario.db_register", place="tab", tab_key="demo_tabs", first_label="첫 탭"
)
st.write("after")
"""

PENDING_FRAGMENT = """
import streamlit as st
from capa_simulation.components import grade_ui

st.session_state["runs"] = st.session_state.get("runs", 0) + 1


@grade_ui.in_fragment
def body() -> None:
    st.write("body")


if st.session_state["runs"] == 1:
    st.session_state[grade_ui.PENDING_KEY] = True
body()
"""


def _written(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.markdown]


@GRADE_PARAMS
def test_stop_unless_stops_an_out_of_grade_page(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    app = AppTest.from_string(STOP_PAGE).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    if grade == grades.DEVELOPER:
        assert "after" in _written(app) and not list(app.warning)
    else:
        assert [item.value for item in app.warning] == ["개발자만 여는 화면입니다"]
        assert "after" not in _written(app)


def test_stop_unless_rewrites_a_hidden_tab_once(monkeypatch: pytest.MonkeyPatch) -> None:
    as_grade(monkeypatch, grades.VIEWER)
    app = AppTest.from_string(STOP_TAB)
    app.session_state["demo_tabs"] = "DB 등록"
    app.run(timeout=60)

    assert [item.value for item in app.warning] == ["실무자부터 여는 탭입니다"]
    assert app.session_state["demo_tabs"] == "첫 탭", "다음 회차는 첫 탭으로 정상"
    with pytest.raises(ValueError):
        grade_ui.stop_unless("scenario.db_register", place="tab", tab_key="demo_tabs")


@GRADE_PARAMS
def test_toolbar_scope_and_chart_config_hide_only_below_the_grade(
    monkeypatch: pytest.MonkeyPatch, grade: str
) -> None:
    as_grade(monkeypatch, grade)
    allowed = grades.at_least(grade, grades.MANAGER)
    key = grade_ui.toolbar_key("equipment.export", "equipment_master_table")
    assert (key == "equipment_master_table") is allowed
    assert key.startswith(grade_ui.HIDDEN_TOOLS_PREFIX) is not allowed
    config = grade_ui.chart_config("equipment.export", {"scrollZoom": False})
    assert config["scrollZoom"] is False
    assert ("displayModeBar" in config) is not allowed
    assert grade_ui.HIDDEN_TOOLS_PREFIX in grade_ui.TOOLBAR_STYLE
    assert 'data-testid="stElementToolbar"' in grade_ui.TOOLBAR_STYLE


def test_the_toolbar_style_hides_only_the_csv_download_button() -> None:
    """감춤 칸은 표 도구 막대의 CSV 내려받기 단추만 감춘다 — 찾기 · 크게 보기 · 칸 보이기는
    남는다(2026-11-17 정한 것 42 — 브라우저로 확인). 막대 줄 통째(`stElementToolbar` 자체)를 감추는
    규칙이 없고, 고른 단추 이름표가 설치된 Streamlit 프런트 묶음에 그대로 있다(이름표가 바뀌면
    단추가 다시 보이므로 판 올림 때 여기서 걸린다)."""
    import streamlit

    style = grade_ui.TOOLBAR_STYLE
    rules = [part.strip() for part in style.split("{")[0].removeprefix("<style>").split(",")]
    toolbar_rules = [
        rule for rule in rules if "stElementToolbar" in rule and grade_ui.CSV_DOWNLOAD_LABEL in rule
    ]
    assert toolbar_rules == [
        f'[class*="st-key-{grade_ui.HIDDEN_TOOLS_PREFIX}"] [data-testid="stElementToolbar"] '
        f'button[aria-label="{grade_ui.CSV_DOWNLOAD_LABEL}"]'
    ]
    assert not [rule for rule in rules if rule.endswith('[data-testid="stElementToolbar"]')]
    for kept in ("Search", "Fullscreen", "Show/hide columns", "Show data"):
        assert kept not in style
    assert ":has(" not in style
    bundle = Path(streamlit.__file__).parent / "static" / "static" / "js"
    needle = f"label:`{grade_ui.CSV_DOWNLOAD_LABEL}`"
    labelled = [path.name for path in bundle.glob("*.js") if needle in path.read_text("utf-8")]
    assert labelled, "설치된 Streamlit 표 도구 막대에 내려받기 단추 이름표가 없다"


def test_the_toolbar_style_hides_the_chart_image_and_spec_buttons() -> None:
    """감춤 칸 안 Altair 그림(가용설비 현황 Summary › Main 「주차별 설비 현황」 등)의 도구 막대도
    그림 저장(「Download as PNG」)과 그림 정의 복사(「Copy Vega-Lite spec」 — 그림의 값이 함께
    실린다)를 감춘다 — Plotly 그림 막대를 끄는 것(`chart_config`)과 같은 몫이다(2026-11-19 E2E
    E2-3 — 열람 · 실무자에게 PNG 내려받기가 남아 실제로 내려받아졌다, 6-34 「가용설비 현황 · Space
    현황 내려받기는 관리자부터」). 「Show data」 · 크게 보기는 남는다(값 보기). 두 이름표가 설치된
    Streamlit 프런트 묶음에 그대로 있다(판 올림 때 여기서 걸린다)."""
    import streamlit

    style = grade_ui.TOOLBAR_STYLE
    for label in grade_ui.CHART_EXPORT_LABELS:
        assert (
            f'[class*="st-key-{grade_ui.HIDDEN_TOOLS_PREFIX}"] [data-testid="stElementToolbar"]'
            f' button[aria-label="{label}"]'
        ) in style
    assert grade_ui.CHART_EXPORT_LABELS == ("Download as PNG", "Copy Vega-Lite spec")
    bundle = Path(streamlit.__file__).parent / "static" / "static" / "js"
    texts = [path.read_text("utf-8") for path in bundle.glob("*.js")]
    for label in grade_ui.CHART_EXPORT_LABELS:
        assert any(f"`{label}`" in text for text in texts), label


def test_toolbar_scope_writes_no_style_slot_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """칸마다 스타일을 보내지 않는다 — 프래그먼트 · 팝업 본문의 이벤트 칸 자리 수가 등급과 상관없이
    같다(스타일은 `app.py` 가 보내는 한 벌)."""
    script = """
import streamlit as st
from capa_simulation.components import grade_ui

with grade_ui.toolbar_scope("equipment.export", "demo_table"):
    st.write("table")
"""
    counts = []
    for grade in (grades.VIEWER, grades.MANAGER):
        as_grade(monkeypatch, grade)
        app = AppTest.from_string(script).run(timeout=60)
        counts.append(len(app.get("html")))
    assert counts == [0, 0]


def test_an_alarm_table_can_drop_its_csv_button() -> None:
    import pandas as pd

    from capa_simulation.components.state_alerts import alert_table

    frame = pd.DataFrame({"설비": ["DEMO-01"]})
    kept = alert_table(frame, title="표", file_name="demo.csv")
    dropped = alert_table(frame, title="표", file_name="demo.csv", csv=False)
    assert kept is not None and "csv" not in kept
    assert dropped is not None and dropped["csv"] is False


def test_a_pending_callback_refusal_reruns_the_whole_app_from_a_fragment_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """프래그먼트 · 팝업 안 콜백이 거절을 담으면(`on_press` 표지) 이어 도는 프래그먼트 회차의 본문
    첫머리가 앱 전체를 다시 그린다 — 그 회차에는 알림을 낼 `emit` 이 돌지 않는다."""
    monkeypatch.setattr(grade_ui, "fragment_only_run", lambda: True)
    app = AppTest.from_string(PENDING_FRAGMENT).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["runs"] == 2
    assert grade_ui.PENDING_KEY not in app.session_state
    assert "body" in _written(app)
