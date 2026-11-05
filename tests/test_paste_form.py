# Purpose: 붙여넣기 · 양식 창 공통 부품의 줄 차례 · 알림 길 · 창 크기 JS 와 같은 꼴 그물을 본다.

"""붙여넣기 · 양식 창 공통 부품(`components/paste_form`, 2026-11-05 사용자 검수 static-37).

- 작업 줄은 왼쪽 「적용」 · 오른쪽 「양식 다운로드」 한 줄이다.
- 창을 연 회차에 꼭 알릴 말은 알림 한 번, 거부 · 안내는 알림창이다 — 창 안에 글을 그리지 않는다.
- 창 크기는 브라우저 안에서 끝난다(판정 구획을 node 로 떼어 시험한다 — 실제 끌기는 브라우저로 잰다).
- 그물: 「붙여넣기」 글 칸은 공통 부품에서만 서고, 그 창 함수는 글을 직접 그리지 않는다.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from alert_marks import alert_notes, flashed
from streamlit.testing.v1 import AppTest

from capa_simulation.components import paste_form
from capa_simulation.components.table_toolbar import CSV_TEMPLATE_LABEL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT_ROOT / "src/capa_simulation/components/paste_window_assets"
WINDOW_JS = (ASSETS / "paste_window.js").read_text(encoding="utf-8")
WINDOW_CSS = (ASSETS / "paste_window.css").read_text(encoding="utf-8")

# 붙여넣기 · 확인 창을 그리는 함수(파일, 맨 바깥 함수) — 글을 직접 그리지 않는다.
PASTE_WINDOWS = (
    ("app_pages/standard_target_capa.py", "_paste_dialog"),
    ("app_pages/standard_target_capa.py", "_clear_dialog"),
    ("app_pages/load_conversion.py", "_plan_paste_dialog"),
    ("app_pages/load_conversion.py", "_yield_paste_dialog"),
    ("src/capa_simulation/components/month_editor.py", "paste_dialog"),
    ("src/capa_simulation/components/reference_csv_tools.py", "render_reference_clipboard_form"),
    ("src/capa_simulation/components/display_order_management.py", "_clipboard_dialog"),
    ("src/capa_simulation/components/process_rename_management.py", "_clipboard_dialog"),
    ("src/capa_simulation/components/past_data_management.py", "_render_paste_form"),
    ("src/capa_simulation/components/equipment_import_dialog.py", "_render_body"),
)
# 「붙여넣기」 글 칸을 공통 부품 밖에 둘 수 있는 자리(까닭).
TEXT_AREA_OUTSIDE = {
    # 데이터와 잇지 않는 Qual 마감 계산기의 칸 — 양식 · 저장 · 되돌릴 수 없는 결과가 없고 창이
    # 아니라 계산기 안 펼침이다.
    "src/capa_simulation/components/qual_deadline_calculator.py",
    "src/capa_simulation/components/paste_form.py",
}
DRAWN_TEXT_METHODS = frozenset({"caption", "info", "warning", "error", "success"})

WINDOW_SCRIPT = """
import streamlit as st

from capa_simulation.components.paste_form import (
    PasteTemplate,
    refuse_paste,
    render_paste_form,
    tell_paste,
)

if st.session_state.get("open_window", True):
    submit = render_paste_form(
        "demo",
        text_key="demo_text",
        text_label="표 붙여넣기",
        apply_label="적용",
        template=PasteTemplate(data=b"a,b", file_name="a.csv", key="demo_template"),
        opening="적용하면 표가 통째로 바뀌고 되돌릴 수 없습니다.",
        confirm_key=st.session_state.get("confirm_key"),
        confirm_label="확인했습니다.",
    )
    if submit is not None:
        st.session_state["pressed"] = (submit.text, submit.confirmed)
        if not submit.text.strip():
            refuse_paste("demo", "적용할 표를 붙여넣으세요.")
        elif submit.text.strip() == "same":
            tell_paste("demo", "바뀐 것이 없습니다.")
"""


def _window() -> AppTest:
    return AppTest.from_string(WINDOW_SCRIPT, default_timeout=30).run()


def _codes(app: AppTest) -> list[str]:
    return [str(note.get("code")) for note in alert_notes(app)]


def _apply(app: AppTest) -> Any:
    return next(button for button in app.button if button.label == "적용")


def test_the_action_row_is_apply_on_the_left_and_the_template_on_the_right() -> None:
    """작업 줄은 한 줄이다 — 왼쪽 묶음에 「적용」, 그 오른쪽에 양식 내려받기(양끝 맞춤이라 좁아져
    접혀도 그 차례다)."""
    app = _window()
    assert not app.exception

    rows = []

    def walk(block: Any) -> None:
        for child in getattr(block, "children", {}).values():
            proto = getattr(child, "proto", None)
            flex = getattr(proto, "flex_container", None)
            if flex is not None and flex.direction == 2:
                rows.append(child)
            walk(child)

    walk(app.main)
    outer = next(row for row in rows if len(row.children) == 2)
    kinds = [type(child).__name__ for child in outer.children.values()]
    assert kinds == ["Block", "DownloadButton"], kinds
    (left, right) = outer.children.values()
    (apply_button,) = left.children.values()
    assert apply_button.label == "적용"
    assert right.proto.label == CSV_TEMPLATE_LABEL


def test_the_opening_note_goes_up_once_per_opening() -> None:
    """창을 연 회차에 한 번 — 회차가 다시 돌아도 다시 뜨지 않고, 닫았다 열면 다시 뜬다."""
    app = _window()
    (opening,) = [note for note in alert_notes(app) if note["code"] == "PA-01"]
    assert opening["code"] == "PA-01"
    assert "되돌릴 수 없습니다" in opening["full"]
    assert not app.warning and not app.caption

    app.run()
    assert "PA-01" not in _codes(app)

    app.session_state["open_window"] = False
    app.run()
    app.session_state["open_window"] = True
    app.run()
    assert _codes(app).count("PA-01") == 1


def test_a_refusal_goes_to_the_alert_popup_and_not_the_window() -> None:
    """입력 곁 거부도 창 안에 그리지 않는다 — 글은 칸에 남아 고쳐 다시 누른다."""
    app = _window()
    _apply(app).click().run()
    assert not app.exception
    assert not app.error
    (refused,) = flashed(app, "error")
    assert refused.code == "FL-04"
    assert "붙여넣으세요" in refused.value


def test_a_note_goes_to_the_alert_popup_and_not_the_window() -> None:
    """「바뀐 것이 없습니다」 같은 안내도 창 안에 그리지 않는다."""
    app = _window()
    app.text_area(key="demo_text").set_value("same")
    _apply(app).click().run()
    assert not app.exception
    assert not app.info
    (told,) = flashed(app, "info")
    assert told.code == "FL-02"
    assert app.text_area(key="demo_text").value == "same"


def test_the_window_component_gets_its_size_slot_and_the_lock_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """크기는 칸 이름별로 기억하고 잠금 까닭은 데이터로 간다 — 회차마다 같은 값이다."""
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(paste_form, "_PASTE_WINDOW", lambda **kwargs: sent.append(kwargs))
    app = AppTest.from_string(
        """
from capa_simulation.components.paste_form import render_paste_window

render_paste_window("demo", size_key="import", lock=False)
""",
        default_timeout=30,
    ).run()
    assert not app.exception
    assert sent[0]["key"] == "capa_paste_host_demo"
    data = sent[0]["data"]
    assert data["sizeKey"] == "import"
    assert data["lock"] is False
    assert data["resizable"] is True
    assert data["storagePrefix"] == paste_form.PASTE_SIZE_STORAGE_PREFIX
    assert data["reasons"] == {
        "empty": paste_form.PASTE_EMPTY_WHY,
        "confirm": paste_form.PASTE_CONFIRM_WHY,
    }


def _node(runner: str) -> Any:
    match = re.search(
        r"// <paste-window-core>\n(?P<body>.*?)\n// </paste-window-core>", WINDOW_JS, re.S
    )
    assert match, "paste_window.js 에 // <paste-window-core> 구획이 없습니다"
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 창 크기 JS 구획 시험을 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", match.group("body") + "\n" + runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_the_size_stays_inside_the_viewport() -> None:
    """창 폭은 화면 폭 안, 글 칸은 창이 화면에 들 만큼이다. 줄이는 쪽에도 끝이 있다."""
    out = _node(
        """
const big = clampSize({ width: 5000, text: 5000 }, { width: 1500, height: 950 })
const small = clampSize({ width: 10, text: 10 }, { width: 1500, height: 950 })
const phone = clampSize({ width: 5000, text: 100 }, { width: 320, height: 500 })
process.stdout.write(JSON.stringify({ big, small, phone }))
"""
    )
    assert out["big"] == {"width": 1468, "text": 720}
    assert out["small"] == {"width": 360, "text": 100}
    assert out["phone"] == {"width": 360, "text": 100}


def test_a_stored_size_that_cannot_be_read_is_no_size() -> None:
    """저장된 값이 깨졌거나 비었으면 기본 크기로 연다(예외를 내지 않는다)."""
    out = _node(
        """
process.stdout.write(JSON.stringify([
  parseSize('{"width": 800, "text": 300}'),
  parseSize('{"width": "x", "text": 300}'),
  parseSize('not json'),
  parseSize(null),
]))
"""
    )
    assert out == [{"width": 800, "text": 300}, None, None, None]


def test_dragging_doubles_the_width_of_a_centered_window() -> None:
    """창이 가운데 놓여 양쪽으로 넓어지므로 손 이동의 두 배가 폭이다 — 손잡이가 손을 따라온다."""
    out = _node(
        """
const start = { width: 1000, text: 200 }
process.stdout.write(JSON.stringify([
  dragSize(start, { x: 50, y: 30 }, { x: true, y: true }),
  dragSize(start, { x: 50, y: 30 }, { x: true, y: false }),
  dragSize(start, { x: 50, y: 30 }, { x: false, y: true }),
]))
"""
    )
    assert out == [
        {"width": 1100, "text": 230},
        {"width": 1100, "text": 200},
        {"width": 1000, "text": 230},
    ]


def test_the_apply_lock_says_why() -> None:
    """글 칸이 비었으면 그 까닭, 확인 체크가 꺼져 있으면 그 까닭, 둘 다 되면 풀린다."""
    out = _node(
        """
const reasons = { empty: 'E', confirm: 'C' }
process.stdout.write(JSON.stringify([
  lockReason('', true, reasons),
  lockReason('   \\n', false, reasons),
  lockReason('a', false, reasons),
  lockReason('a', true, reasons),
]))
"""
    )
    assert out == ["E", "E", "C", ""]


def test_the_window_assets_keep_browser_state_safe() -> None:
    """`localStorage` 읽기 · 쓰기는 try/catch 안이고 서버로 보내지 않으며, 서식은 창 이름 아래다."""
    assert "setStateValue" not in WINDOW_JS and "setTriggerValue" not in WINDOW_JS
    for line in WINDOW_JS.splitlines():
        if "localStorage." in line and not line.lstrip().startswith("//"):
            start = WINDOW_JS.index(line)
            assert "try {" in WINDOW_JS[max(0, start - 120) : start], line
    assert "/*" not in WINDOW_CSS, "회차마다 다시 가는 서식에 CSS 주석을 싣지 않는다(AGENTS 9장)"
    selectors = [
        chunk.strip() for chunk in re.findall(r"(?:^|\})\s*([^{}]+)\{", WINDOW_CSS) if chunk.strip()
    ]
    assert selectors
    for selector in selectors:
        assert "capa-paste" in selector or "capa_paste" in selector, selector


def _top_function(relative: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{relative} 에 {name} 이 없습니다 — 표를 고치세요.")


@pytest.mark.parametrize("site", PASTE_WINDOWS, ids=lambda site: f"{site[0]}::{site[1]}")
def test_a_paste_window_draws_no_text_of_its_own(site: tuple[str, str]) -> None:
    """창 함수는 캡션 · 상자를 직접 그리지 않는다 — 말은 알림창 길(`paste_form`)이다."""
    function = _top_function(*site)
    drawn = [
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in DRAWN_TEXT_METHODS
    ]
    assert not drawn, drawn


def _text_area_calls() -> list[tuple[str, ast.Call]]:
    found: list[tuple[str, ast.Call]] = []
    paths = [PROJECT_ROOT / "app.py"]
    for base in ("app_pages", "src/capa_simulation"):
        paths.extend(sorted((PROJECT_ROOT / base).rglob("*.py")))
    for path in paths:
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "text_area"
            ):
                found.append((relative, node))
    return found


def test_paste_text_areas_stand_only_in_the_common_part() -> None:
    """같은 꼴은 공통 부품 하나다(설계 규칙 UI-CON-04) — 「붙여넣기」 글 칸을 새로 두면 실패한다."""
    outside = []
    for relative, call in _text_area_calls():
        if relative in TEXT_AREA_OUTSIDE:
            continue
        label = call.args[0] if call.args else None
        text = ast.unparse(label) if label is not None else ""
        if "붙여넣기" in text or "Ctrl+V" in ast.unparse(call):
            outside.append(f"{relative}:{call.lineno}")
    assert not outside, outside


def test_every_paste_text_area_helper_has_no_tooltip() -> None:
    """공통 글 칸에는 풍선이 없다 — 칸의 규칙은 연 회차의 알림과 Guide 가 말한다."""
    calls = [
        call
        for relative, call in _text_area_calls()
        if relative == "src/capa_simulation/components/paste_form.py"
    ]
    assert len(calls) == 1
    assert not [keyword for keyword in calls[0].keywords if keyword.arg == "help"]


def test_the_templates_of_the_import_window_follow_the_chosen_table() -> None:
    """엑셀·CSV 창의 양식은 고른 표의 것이고 표 이름은 등록할 표 목록과 같다."""
    from capa_simulation.components.equipment_data_workspace import _TARGETS
    from capa_simulation.components.equipment_import_dialog import IMPORT_TEMPLATES

    assert set(IMPORT_TEMPLATES) == set(_TARGETS)
    keys = [entry[2] for entry in IMPORT_TEMPLATES.values()]
    assert len(keys) == len(set(keys))
