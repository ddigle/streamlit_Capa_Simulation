# Purpose: 「데이터 Error」 마크의 꼴 · 알림 짝과, 못 그리는 오류가 마크로만 서는 자리를 시험한다.

"""「데이터 Error」 마크(`components/data_error_mark.py` — 2026-11-05 사용자 지시 「페이지에는
데이터 Error 마크를 넣고 Alarm 확인 필요 문구까지만 배치, 나머지는 알람으로 확인」).

자리 그물은 화면 코드를 AST 로 훑는다 — `st.error` 뒤 `st.stop()` 은 그 자리에 고칠 입력이 있는
거부만 남고(나머지는 마크), `alert_page_error` 는 한 오류의 마크가 탭 여럿에 서는 자리만 쓰며,
`render_data_error` 의 코드는 등록부의 오류 단계 사건 코드다.
"""

from __future__ import annotations

import ast
import re
from collections import Counter

import pytest
from alert_marks import alert_notes, data_error_marks, data_error_texts, events
from source_sites import called_name, method, receiver, relative, screen_calls, screen_files
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


def test_only_the_tabbed_mark_sends_its_alert_separately() -> None:
    """알림만 따로 보내면 자리와 짝이 어긋나기 쉽다 — `render_data_error` 한 칸이 기본이다."""
    found: Counter[tuple[str, str]] = Counter(
        (file, outer)
        for file, outer, _path, _scope, call in screen_calls(screen_files())
        if called_name(call) == "alert_page_error"
    )
    assert found == Counter(SEPARATE_ALERTS)


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
