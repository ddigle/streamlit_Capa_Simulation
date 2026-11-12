# Purpose: 「데이터 Error」 마크의 꼴 · 알림 짝과, 못 그리는 오류가 마크로만 서는 자리를 시험한다.

"""「데이터 Error」 마크(`components/data_error_mark.py` — 2026-11-05 사용자 지시 「페이지에는
데이터 Error 마크를 넣고 Alarm 확인 필요 문구까지만 배치, 나머지는 알람으로 확인」).

자리 그물은 화면 코드를 AST 로 훑는다 — `.error(` 는 (파일, 맨 바깥 함수)마다 수와 까닭을 허용
목록과 정확히 맞댄다(`PLACE_ERROR_SITES` — 그 자리 입력의 거부 · 누른 동작의 실패 · 알림 칸이 없는
멈춤 · 점검 판 · 모듈 카드 · 알림 길). `st.error` 뒤 `st.stop()` 은 그 자리에 고칠 입력이 있는
거부만 남고(나머지는 마크), 마크만 그리는 `render_data_error_mark` 와 따로 보내는
`alert_page_error` 는 한 오류의 마크가 탭 여럿에 서는 자리(산출 결과)만 쓰며, `render_data_error`
의 코드는 등록부의 오류 단계 사건 코드다.
"""

from __future__ import annotations

import ast
import re
from collections import Counter

import pytest
from alert_marks import alert_notes, data_error_marks, data_error_texts, events
from source_sites import (
    LOGGERS,
    called_name,
    method,
    receiver,
    relative,
    screen_calls,
    screen_files,
)
from streamlit.testing.v1 import AppTest

from capa_simulation import alerts
from capa_simulation.components.data_error_mark import (
    MARK_CLASS,
    MARK_LABEL,
    MARK_NEXT,
    data_error_mark_html,
)
from capa_simulation.design import theme, tokens

# (파일, 맨 바깥 함수) → `st.error` 바로 뒤 `st.stop()` 수 — 그 자리 입력으로 고치는 거부만이다.
STOPPING_BOXES: dict[tuple[str, str], int] = {
    # 조회 시작일 · 종료일 칸 바로 곁의 거부(입력을 고치면 풀린다).
    ("app_pages/standard_target_capa.py", ""): 1,
}
# (파일, 맨 바깥 함수) → 마크와 따로 알림을 보내는 수 — 마크가 세 탭에 서고 알림은 탭 밖에서 한 번.
SEPARATE_ALERTS: dict[tuple[str, str], int] = {
    ("app_pages/calculation_result.py", ""): 1,
}
# 자리에 남는 오류 상자의 까닭 — 데이터 때문에 못 그린 자리는 어느 까닭에도 들지 않는다(마크다).
BESIDE = "그 자리 입력의 거부 — 곁 입력을 고치면 풀린다(UI-NTF-03)"
PRESSED = "누른 동작의 실패 — 저장 · 적용 · 불러오기 단추 곁(UI-NTF-03)"
NO_ALARM = "앱이 서지 못해 알림 칸이 없는 멈춤(UI-NTF-08 예외)"
CHECK_BOARD = "판 자체 — 점검 화면의 결론 상자"
MODULE_CARD = "모듈 오류 카드(UI-NTF-08 예외)"
ALERT_PATH = "알림 길 — 눌린 회차의 곁 칸(`flash`, 곁 오류의 공통 그리기)"
ERROR_REASONS = frozenset({BESIDE, PRESSED, NO_ALARM, CHECK_BOARD, MODULE_CARD, ALERT_PATH})
# (파일, 맨 바깥 함수) → (`.error(` 수, 까닭). 새 자리는 실패한다 — 그리기 실패면
# `render_data_error`, 곁 거부 · 누른 동작의 실패면 까닭과 함께 여기에 둔다.
PLACE_ERROR_SITES: dict[tuple[str, str], tuple[int, str]] = {
    ("app.py", ""): (1, NO_ALARM),
    ("app_pages/load_conversion.py", ""): (4, PRESSED),
    ("app_pages/load_conversion.py", "_virtual_product_dialog"): (1, PRESSED),
    ("app_pages/reference_data.py", ""): (2, PRESSED),
    ("app_pages/reference_data.py", "_step_dialog"): (1, PRESSED),
    ("app_pages/reference_integrity.py", "_render_detail"): (1, BESIDE),
    ("app_pages/space_status.py", ""): (1, PRESSED),
    ("app_pages/space_status.py", "_render_fab_editor"): (1, PRESSED),
    ("app_pages/space_status.py", "_render_layout_editor"): (1, PRESSED),
    ("app_pages/space_status.py", "_render_unsaved_layout_panel"): (2, PRESSED),
    ("app_pages/standard_target_capa.py", ""): (1, BESIDE),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_run_now"): (3, PRESSED),
    ("src/capa_simulation/components/auto_official_update_tab.py", "_render_settings_form"): (
        6,
        PRESSED,
    ),
    ("src/capa_simulation/components/bigdataquery_registration.py", "_run_catalog_query"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/bigdataquery_registration.py", "_save_scenario"): (4, PRESSED),
    ("src/capa_simulation/components/bigdataquery_registration.py", "_submitted_detail_window"): (
        5,
        BESIDE,
    ),
    ("src/capa_simulation/components/bigdataquery_registration.py", "_submitted_window"): (
        2,
        BESIDE,
    ),
    ("src/capa_simulation/components/cutoff_management.py", "render_cutoff_management"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/display_order_management.py", "_render_direct_editor"): (
        3,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_data_workspace.py", "_render_history"): (1, BESIDE),
    ("src/capa_simulation/components/equipment_explorer.py", "_render_result"): (1, BESIDE),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_branch"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_clear_layout"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_legacy_trace"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_load"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_publish"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_rename"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_restore"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_management.py", "_render_revision_name"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/equipment_scenario_status.py", "_render_load"): (1, PRESSED),
    ("src/capa_simulation/components/flash.py", "_draw"): (1, ALERT_PATH),
    ("src/capa_simulation/components/floor_canvas_dialog.py", "_save"): (1, PRESSED),
    ("src/capa_simulation/components/home_preference.py", "_reject_key_process_write"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_execution_editor"): (4, PRESSED),
    ("src/capa_simulation/components/home_preference.py", "_render_key_process_editor"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_key_process_preset_actions"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_monthly_amount_editor"): (
        1,
        PRESSED,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_summary_note_editor"): (
        3,
        PRESSED,
    ),
    ("src/capa_simulation/components/home_preference.py", "_render_top5_band_editor"): (3, PRESSED),
    ("src/capa_simulation/components/home_preference.py", "render_threshold_editor"): (3, PRESSED),
    ("src/capa_simulation/components/manual_downtime_tab.py", "_render_editor"): (5, PRESSED),
    ("src/capa_simulation/components/module_failure_card.py", "render_failure_parts"): (
        1,
        MODULE_CARD,
    ),
    ("src/capa_simulation/components/past_data_management.py", "_render_save"): (1, PRESSED),
    ("src/capa_simulation/components/process_rename_management.py", "_render_direct_editor"): (
        3,
        PRESSED,
    ),
    ("src/capa_simulation/components/scenario_management.py", "_render_archive"): (1, PRESSED),
    ("src/capa_simulation/components/scenario_management.py", "_render_clone"): (3, PRESSED),
    ("src/capa_simulation/components/scenario_management.py", "_render_delete"): (1, PRESSED),
    ("src/capa_simulation/components/scenario_management.py", "_render_official"): (3, PRESSED),
    ("src/capa_simulation/components/scenario_management.py", "_restore_scenario"): (1, PRESSED),
    # 덧붙일 월 없음 · 합치기 거부 · 모듈수 막힘은 고를 칸 곁이고, 넷째는 저장 칸이 선 뒤 누른
    # 저장의 거부다 — 칸을 고치면 풀리는 것은 같다.
    ("src/capa_simulation/components/scenario_month_merge.py", "_render_merge"): (4, BESIDE),
    ("src/capa_simulation/components/scenario_month_merge.py", "render_scenario_month_merge"): (
        1,
        BESIDE,
    ),
    ("src/capa_simulation/components/scenario_status.py", "_render_load"): (1, PRESSED),
    ("src/capa_simulation/components/scenario_status.py", "_render_revision_save"): (2, PRESSED),
    ("src/capa_simulation/components/scenario_transform.py", "render_derived_save"): (4, BESIDE),
    ("src/capa_simulation/components/scenario_year_shift.py", "render_scenario_year_shift"): (
        1,
        BESIDE,
    ),
    ("src/capa_simulation/components/sso_identity.py", "_stop_without_gate"): (1, NO_ALARM),
    ("src/capa_simulation/components/sso_status.py", "render_sso_status"): (1, CHECK_BOARD),
    # 목표 확보율 팝업 직접 입력 칸 바로 밑 — 범위 밖 · 숫자 아님(2026-11-11 사용자 고칠 것 Q2-26).
    ("src/capa_simulation/components/target_level_field.py", "_pick"): (1, BESIDE),
}

PAGE = """
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.data_error_mark import render_data_error

alerts.note_page("산출 결과", "calculation_result")
message = st.session_state.get(
    "message",
    "RQ_RUN_RATE의 값이 빈 기준이 있습니다: 2건, 예시 [202704]\\n\\n- 수율 탭에서 고치세요",
)
render_data_error(message, code="ST-20", tab="소요대수")
st.stop()
"""


def test_the_mark_stands_alone_and_the_text_goes_only_to_the_alert() -> None:
    """자리에는 마크 · 「Alarm 확인 필요」 뿐이고(상자 · 글 없음) 오류 글은 오류 단계 사건 알림으로
    간다 — 같은 글이면 같은 id(회차마다 다시 그려도 알림창 한 번), `keep` 은 Alarm 줄을 지키라는
    표지다."""
    app = AppTest.from_string(PAGE).run()
    assert not app.exception
    assert data_error_marks(app) == 1
    assert not app.error and not app.warning and not app.info and not app.caption
    (first,) = alert_notes(app)
    assert (first["code"], first["kind"], first["level"]) == ("ST-20", "event", "error")
    assert first["short"] == "RQ_RUN_RATE의 값이 빈 기준이 있습니다: 2건, 예시 [202704]"
    assert first["full"].endswith("- 수율 탭에서 고치세요")
    assert (first["page"], first["tab"], first["keep"]) == ("산출 결과", "소요대수", True)
    assert first["cause"] == alerts.PAGE_ERROR_CAUSE
    assert str(first["id"]).startswith("page-")

    app.run()
    (again,) = alert_notes(app)
    assert again["id"] == first["id"]

    app.session_state["message"] = "계산을 멈췄습니다."
    app.run()
    assert data_error_texts(app) == ["계산을 멈췄습니다."]
    assert alert_notes(app)[0]["id"] != first["id"]


def test_a_mark_whose_input_lives_on_another_screen_sends_the_alarm_there() -> None:
    """채울 입력이 다른 화면에 있는 멈춤(재공 현황 주차별 가용대수 · 필요 단축 일정 Cut-off) —
    자리에는 같은 마크뿐이고 길 안내는 Alarm 줄의 「그 화면으로」 다. `goto` 를 안 주면 이번
    화면이다."""
    script = PAGE.replace(
        'code="ST-20", tab="소요대수"', 'code="WIP-01", goto=("표준 목표", "standard_target_capa")'
    )
    assert script != PAGE
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert data_error_marks(app) == 1
    (note,) = alert_notes(app)
    assert (note["page"], note["href"]) == ("표준 목표", "standard_target_capa")
    assert note["keep"] is True


def test_the_mark_shows_only_its_two_words() -> None:
    """서식 · 아이콘을 걷으면 마크 글은 두 낱말뿐이다 — 오류 글이 자리에 새지 않는다. `st.html` 이
    걷는 SVG 를 쓰지 않는다."""
    body = data_error_mark_html()
    assert MARK_CLASS in body and 'role="status"' in body and "<svg" not in body
    icon = rf'<span class="{MARK_CLASS}__icon" aria-hidden="true">!</span>'
    text = re.sub(rf"<style>.*?</style>|{icon}|<[^>]+>", " ", body, flags=re.S)
    assert text.split() == [*MARK_LABEL.split(), *MARK_NEXT.split()]


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_mark_paints_with_the_theme_tokens(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """두 테마 모두 그 테마의 알림 오류색이다 — 칠한 칸 글자는 면 색, 옆 글은 본문 색, 손으로 적은
    색이 없다. 좁은 폭에서는 두 칸이 줄을 바꾼다(`flex-wrap`, 폭은 칸을 넘지 않는다)."""
    monkeypatch.setattr(theme, "current_mode", lambda: mode)
    body = data_error_mark_html()
    error = tokens.palette_value(mode, "ALERT_ERROR")
    surface = tokens.palette_value(mode, "SURFACE")
    assert f"border:1.5px solid {error}" in body
    assert f"background:{error};color:{surface}" in body
    assert f"color:{tokens.palette_value(mode, 'TEXT')}" in body
    assert "flex-wrap:wrap" in body and "max-width:100%" in body


FRAGMENT = """
import streamlit as st

from capa_simulation.components.data_error_mark import render_data_error


@st.fragment
def body() -> None:
    if st.session_state.get("broken"):
        render_data_error("읽지 못했습니다.", code="ST-20")


body()
st.button("뒤", key="after")
"""


def test_the_mark_writes_no_event_slot_so_a_fragment_keeps_its_count() -> None:
    """마크와 표지가 한 칸이라 프래그먼트 · 팝업 본문의 이벤트 칸 자리 수가 갈래마다 같다(AGENTS
    9장) — 스타일만 든 `st.html` 을 쓰지 않는다."""
    app = AppTest.from_string(FRAGMENT).run()
    assert not app.get("html")
    app.session_state["broken"] = True
    app.run()
    (element,) = app.get("html")
    body = str(element.proto.body)
    assert MARK_CLASS in body and alerts.MARKER_ATTRIBUTE in body and "<div" in body


def test_a_held_event_leaves_with_the_mark_before_the_page_stops() -> None:
    """담아 둔 사건 알림도 마크 표지로 나간다 — 멈춘 화면에는 뒤 표지 자리가 없다."""
    script = """
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.data_error_mark import render_data_error

alerts.event("SB-14", text="옮겨 엶")
render_data_error("읽지 못했습니다.", code="ST-20")
st.stop()
"""
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert [note["code"] for note in alert_notes(app)] == ["SB-14", "ST-20"]
    assert len(events(app, "ST-20")) == 1


def _stopping_boxes() -> Counter[tuple[str, str]]:
    """`….error(…)` 바로 뒤 문장이 `st.stop()` 인 자리."""
    found: Counter[tuple[str, str]] = Counter()
    for path in screen_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, scope in _scopes(tree):
            for body in _bodies(scope):
                for left, right in zip(body, body[1:], strict=False):
                    if _is_error_box(left) and _is_stop(right):
                        found[(relative(path), name)] += 1
    return found


def _scopes(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """맨 바깥 함수 · 클래스 메서드마다 (이름, 노드), 모듈 본문은 ("", 함수를 뺀 모듈)."""
    scopes: list[tuple[str, ast.AST]] = []
    rest: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            scopes.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            scopes.extend(
                (item.name, item)
                for item in node.body
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            )
        else:
            rest.append(node)
    scopes.append(("", ast.Module(body=rest, type_ignores=[])))
    return scopes


def _bodies(node: ast.AST) -> list[list[ast.stmt]]:
    """문장 목록마다 — 차례로 이어 선 문장을 본다."""
    found: list[list[ast.stmt]] = []
    for child in ast.walk(node):
        for name in ("body", "orelse", "finalbody"):
            block = getattr(child, name, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                found.append(block)
    return found


def _is_error_box(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and method(statement.value) == "error"
        and receiver(statement.value) == "st"
    )


def _is_stop(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and method(statement.value) == "stop"
        and receiver(statement.value) == "st"
    )


def test_only_a_refusal_beside_its_input_stops_the_page_with_an_error_box() -> None:
    """화면을 못 그리는 오류는 마크다 — `st.error` + `st.stop()` 은 그 자리 입력으로 고치는 거부만.
    앱이 서지 못한 `app.py` 부트스트랩 실패는 사이에 「원본 오류」 펼침이 서고 알림 칸이 없다."""
    assert _stopping_boxes() == Counter(STOPPING_BOXES)


def _place_error_sites() -> Counter[tuple[str, str]]:
    """자리 오류 상자(`….error(글)`)마다 (파일, 맨 바깥 함수) — 로거와 인자 없는 `.error()` 는
    밖."""
    return Counter(
        (file, outer)
        for file, outer, _path, _scope, call in screen_calls(screen_files())
        if method(call) == "error" and receiver(call) not in LOGGERS and call.args
    )


def test_every_place_error_box_is_a_refusal_or_a_pressed_failure() -> None:
    """데이터 때문에 구획 · 화면을 못 그린 자리는 오류 상자가 아니라 마크다(UI-NTF-08) — `st.stop()`
    없이 함수가 끝나는 자리 · 칸(`slot.error`)까지 모두 세므로, 그리기 실패를 상자로 두면 새 자리로
    걸린다. 옮긴 자리는 목록에서도 지운다."""
    expected = {site: count for site, (count, _reason) in PLACE_ERROR_SITES.items()}
    assert _place_error_sites() == Counter(expected)
    assert {reason for _count, reason in PLACE_ERROR_SITES.values()} <= ERROR_REASONS


def test_only_the_tabbed_mark_sends_its_alert_separately() -> None:
    """알림만 따로 보내면 자리와 짝이 어긋나기 쉽다 — `render_data_error` 한 칸이 기본이고, 마크만
    그리면 「Alarm 확인 필요」 라는데 Alarm 에 글이 없다."""
    for name in ("alert_page_error", "render_data_error_mark"):
        found: Counter[tuple[str, str]] = Counter(
            (file, outer)
            for file, outer, _path, _scope, call in screen_calls(screen_files())
            if called_name(call) == name
        )
        assert found == Counter(SEPARATE_ALERTS), name


def test_every_mark_names_an_error_event_of_the_registry() -> None:
    """마크의 코드는 그 화면의 오류 단계 사건 코드다 — 글이 알림으로만 가니 등록부 밖이면 멈춘다."""
    codes: set[str] = set()
    for _file, _outer, _path, _scope, call in screen_calls(screen_files()):
        if called_name(call) != "render_data_error":
            continue
        value = next(item.value for item in call.keywords if item.arg == "code")
        assert isinstance(value, ast.Constant) and isinstance(value.value, str)
        codes.add(value.value)
    assert codes
    for code in sorted(codes):
        entry = alerts.spec(code)
        assert (entry.level, entry.kind) == ("error", "event"), code
