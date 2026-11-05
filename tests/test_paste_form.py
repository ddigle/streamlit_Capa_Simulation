# Purpose: 붙여넣기 · 양식 창 공통 부품의 줄 차례 · 알림 길 · 창 크기 JS 와 같은 꼴 그물을 본다.

"""붙여넣기 · 양식 창 공통 부품(`components/paste_form`, 2026-11-05 사용자 검수 static-37).

- 작업 줄은 창 제목 옆, 왼쪽 「적용」 · 오른쪽 「양식 다운로드」 한 줄이다(표 상자 안은 상자 맨 위).
- 글 칸 라벨은 화면에 보이지 않고 접근성 이름으로 남는다(보이는 창은 목록의 둘).
- 창을 연 회차에 꼭 알릴 말은 알림 한 번, 거부 · 안내는 알림창이다 — 창 안에 글을 그리지 않는다.
- 창 크기는 브라우저 안에서 끝난다(판정 구획을 node 로 떼어 시험한다 — 실제 끌기는 브라우저로 잰다).
- 그물: 「붙여넣기」 글 칸은 공통 부품에서만 서고, 그 창 함수는 글을 직접 그리지 않는다.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from alert_marks import alert_notes, flashed, place_errors
from js_runner import run_js_json
from streamlit.proto.LabelVisibility_pb2 import LabelVisibility
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
    ("src/capa_simulation/components/access_list_admin.py", "_add_dialog"),
)
# 글 칸 라벨을 화면에 보이는 창(파일 → 까닭) — 창 제목만으로는 무엇을 넣는 칸인지 모른다.
LABEL_VISIBLE_WINDOWS = {
    "src/capa_simulation/components/equipment_import_dialog.py": "곁의 CSV 업로드 칸과 짝",
    "src/capa_simulation/components/access_list_admin.py": "넣을 것을 말하는 글이 라벨뿐",
}
# 창 제목이 없는 표 상자 안 칸 — 작업 줄이 제목 줄이 아니라 그 상자 맨 위에 선다.
IN_BOX_FORMS = {"src/capa_simulation/components/past_data_management.py"}
HEAD_WINDOW_MARK = 'class*="st-key-capa_paste_head_"'
# 제목 줄 서식이 걸리는 창 — 본문 겹 바로 밑에 작업 줄이 든 팝업뿐이다.
HEAD_WINDOW_SCOPE = (
    '[role="dialog"]:has(> h2 + div > [data-testid="stVerticalBlock"]'
    ' > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]'
    f' > [data-testid="stLayoutWrapper"] > [{HEAD_WINDOW_MARK}])'
)
MEMO_FIELD = "메모 · 글 — 표를 붙여넣는 칸이 아니다"
# 공통 부품 밖의 글 칸 전부(파일 → (수, 까닭)). 표를 붙여넣는 칸을 새로 두면 라벨이 무엇이든 여기서
# 걸린다 — 공통 부품을 쓴다.
TEXT_AREA_OUTSIDE = {
    # 데이터와 잇지 않는 Qual 마감 계산기의 칸 — 양식 · 저장 · 되돌릴 수 없는 결과가 없고 창이
    # 아니라 계산기 안 펼침이다(UI-INP-08 예외).
    "src/capa_simulation/components/qual_deadline_calculator.py": (1, "계산기 안 펼침"),
    "src/capa_simulation/components/paste_form.py": (1, "공통 부품"),
    "src/capa_simulation/components/scenario_status.py": (1, MEMO_FIELD),
    "src/capa_simulation/components/scenario_management.py": (2, MEMO_FIELD),
    "src/capa_simulation/components/scenario_transform.py": (1, MEMO_FIELD),
    "src/capa_simulation/components/bigdataquery_registration.py": (1, MEMO_FIELD),
    "src/capa_simulation/components/home_preference.py": (1, MEMO_FIELD),
    "app_pages/voc.py": (2, MEMO_FIELD),
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


def _rows(app: AppTest) -> list[Any]:
    """가로 칸 전부(앞 차례)."""
    rows: list[Any] = []

    def walk(block: Any) -> None:
        for child in getattr(block, "children", {}).values():
            flex = getattr(getattr(child, "proto", None), "flex_container", None)
            if flex is not None and flex.direction == 2:
                rows.append(child)
            walk(child)

    walk(app.main)
    return rows


def _css_rules() -> list[tuple[str, str]]:
    """(선택자, 선언) 목록 — 주석이 없는 파일이라 괄호로 가른다."""
    return [
        (selector.strip(), body)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", WINDOW_CSS)
    ]


def _keyword_sites(name: str) -> set[str]:
    """`name=True` 를 건네는 파일."""
    return {
        relative
        for relative, call in _all_calls()
        if any(
            keyword.arg == name
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in call.keywords
        )
    }


def _codes(app: AppTest) -> list[str]:
    return [str(note.get("code")) for note in alert_notes(app)]


def _apply(app: AppTest) -> Any:
    return next(button for button in app.button if button.label == "적용")


def test_the_action_row_is_apply_on_the_left_and_the_template_on_the_right() -> None:
    """작업 줄은 한 줄이다 — 왼쪽 묶음에 「적용」, 그 오른쪽에 양식 내려받기(양끝 맞춤이라 좁아져
    접혀도 그 차례다)."""
    app = _window()
    assert not app.exception

    outer = next(row for row in _rows(app) if len(row.children) == 2)
    kinds = [type(child).__name__ for child in outer.children.values()]
    assert kinds == ["Block", "DownloadButton"], kinds
    (left, right) = outer.children.values()
    (apply_button,) = left.children.values()
    assert apply_button.label == "적용"
    assert right.proto.label == CSV_TEMPLATE_LABEL


@pytest.mark.parametrize(
    ("in_box", "name"),
    [(False, "capa_paste_head_demo"), (True, "capa_paste_row_demo")],
    ids=("창 제목 옆", "표 상자 맨 위"),
)
def test_the_action_row_is_named_for_where_it_stands(in_box: bool, name: str) -> None:
    """서식이 이 이름으로 옮긴다 — 창이면 제목 줄, 표 상자 안 칸이면 그 상자 맨 위다. 내용 폭으로
    왼쪽에 붙어 「적용」 과 양식이 나란하다(양끝으로 벌어지면 제목 옆에 서지 못한다)."""
    app = AppTest.from_string(
        f"""
from capa_simulation.components.paste_form import PasteTemplate, render_paste_form

render_paste_form(
    "demo",
    text_key="demo_text",
    text_label="표 붙여넣기",
    apply_label="적용",
    template=PasteTemplate(data=b"a,b", file_name="a.csv", key="demo_template"),
    in_box={in_box},
)
""",
        default_timeout=30,
    ).run()
    assert not app.exception
    outer = next(row for row in _rows(app) if len(row.children) == 2)
    assert name in outer.proto.id
    assert "JUSTIFY_START" in str(outer.proto.flex_container), "양끝 맞춤이 아니다"
    assert outer.proto.width_config.use_content


def test_a_window_without_a_template_has_only_the_apply_button() -> None:
    """양식이 없는 창의 작업 줄에는 내려받기가 없다 — 빈 칸이 남지 않는다."""
    app = AppTest.from_string(
        """
from capa_simulation.components.paste_form import render_paste_form

render_paste_form("demo", text_key="demo_text", text_label="표 붙여넣기", apply_label="넣기")
""",
        default_timeout=30,
    ).run()
    assert not app.exception
    assert not app.get("download_button")
    assert [button.label for button in app.button] == ["넣기"]
    assert any("capa_paste_head_demo" in row.proto.id for row in _rows(app))


def test_the_text_label_is_hidden_but_stays_the_accessible_name() -> None:
    """라벨은 창 제목과 거듭되는 말이라 화면에 보이지 않고, 글은 접근성 이름으로 남는다. 제목만으로
    무엇을 넣는 칸인지 모르는 창만 보인다."""
    (text,) = _window().text_area
    assert text.label == "표 붙여넣기"
    assert text.proto.label_visibility.value == LabelVisibility.LabelVisibilityOptions.COLLAPSED

    shown = AppTest.from_string(
        """
from capa_simulation.components.paste_form import paste_text_area

paste_text_area("demo", text_key="demo_text", label="loginid 붙여넣기", label_visible=True)
""",
        default_timeout=30,
    ).run()
    assert not shown.exception
    (text,) = shown.text_area
    assert text.proto.label_visibility.value == LabelVisibility.LabelVisibilityOptions.VISIBLE


def test_only_the_listed_windows_show_the_text_label() -> None:
    """라벨을 보이는 창이 늘면 여기서 걸린다 — 창에 글을 더 두는 일이라 까닭과 함께 목록에 둔다."""
    assert _keyword_sites("label_visible") == set(LABEL_VISIBLE_WINDOWS)


def test_only_the_past_data_form_stands_in_a_box() -> None:
    """창 제목이 없는 칸은 HOME 설정 Past Data 하나다 — 그 밖의 창은 모두 제목 옆 작업 줄이다."""
    assert _keyword_sites("in_box") == IN_BOX_FORMS


def test_the_action_row_names_match_the_window_stylesheet() -> None:
    """부품이 짓는 칸 이름과 서식이 고르는 이름이 같다 — 어긋나면 작업 줄이 글 칸 아래에 남는다."""
    assert f'class*="st-key-{paste_form._HEAD_ROW_PREFIX}"' == HEAD_WINDOW_MARK
    assert HEAD_WINDOW_MARK in WINDOW_CSS
    assert f'class*="st-key-{paste_form._BOX_ROW_PREFIX}"' in WINDOW_CSS


def test_the_title_row_layout_stays_on_windows_with_a_head_row() -> None:
    """팝업을 푸는 서식은 작업 줄이 그 겹 바로 밑에 든 창에만 걸린다 — 다른 팝업 · 작업 줄 없는 확인
    창은 그대로고, Streamlit 판올림으로 겹이 바뀌면 아무 규칙도 걸리지 않아 창이 그대로 쓰인다."""
    laid_out = [
        (selector, body)
        for selector, body in _css_rules()
        if re.search(r"display:\s*contents|flex-flow|order:\s*-[12]", body)
        and "capa_paste_row_" not in selector
    ]
    assert len(laid_out) == 4
    for selector, _body in laid_out:
        for part in selector.split(",\n"):
            assert part.strip().startswith(HEAD_WINDOW_SCOPE), part


def test_the_title_row_wraps_below_the_title_and_clears_the_close_button() -> None:
    """한 줄에 들지 못하면 줄바꿈으로 제목 아래에 내려가고, 제목 줄에서는 ✕ 자리를 비운다."""
    rules = _css_rules()
    (dialog,) = [body for selector, body in rules if selector == HEAD_WINDOW_SCOPE]
    assert re.search(r"flex-flow:\s*row wrap", dialog)
    (row,) = [
        body
        for selector, body in rules
        if selector.endswith(f'[data-testid="stLayoutWrapper"]:has(> [{HEAD_WINDOW_MARK}])')
    ]
    assert re.search(r"flex:\s*0 1 auto", row), "내용 폭 — 들지 못하면 내려간다"
    assert re.search(r"margin:\s*0 3\.25rem", row), "✕ 자리"
    (title,) = [body for selector, body in rules if selector == f"{HEAD_WINDOW_SCOPE} > h2"]
    assert re.search(r"max-width:\s*calc\(100% - 3\.25rem\)", title), "긴 제목도 ✕ 를 덮지 않는다"


def test_the_lock_reason_stands_below_the_button() -> None:
    """작업 줄이 창 위 끝이라 까닭 풍선은 아래로 선다 — 위로 서면 창 상자(`overflow: hidden`)에
    잘린다."""
    (body,) = [
        body
        for selector, body in _css_rules()
        if selector == "[data-capa-paste-locked]:hover::after"
    ]
    assert "top: calc(100% + 6px)" in body
    assert "bottom:" not in body


def test_the_lock_reason_wraps_inside_the_room_the_window_leaves() -> None:
    """풍선은 자기 글 폭으로 서되 창이 남긴 자리(`--capa-paste-tip-room` — 스크립트가 잰다)에서
    접힌다. 줄바꿈을 막으면 폭 360 화면의 제목 옆 단추에서 글 끝이 창 상자에 잘린다. 스크립트가 못
    돌았을 때의 폭도 정해 둔다."""
    (body,) = [
        body
        for selector, body in _css_rules()
        if selector == "[data-capa-paste-locked]:hover::after"
    ]
    assert "white-space: normal" in body
    assert "nowrap" not in body
    assert "width: max-content" in body
    assert re.search(r"max-width:\s*var\(--capa-paste-tip-room,\s*\S+\)", body), body
    assert "--capa-paste-tip-room" in WINDOW_JS


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
    assert not place_errors(app)
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
    return run_js_json(match.group("body") + "\n" + runner, what="창 크기 JS 구획 시험")


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


def test_the_text_limit_follows_the_measured_room_outside_the_text_box() -> None:
    """글 칸 밖 높이는 창마다 · 폭마다 다르다 — 좁아져 작업 줄이 제목 아래로 접히거나 확인 체크가
    있으면 커진다. 잰 값을 주면 그만큼 글 칸의 끝이 줄어 창이 화면 안에 든다. 잴 수 없으면 기본값이다.
    줄이는 쪽의 끝은 그대로 지킨다."""
    out = _node(
        """
const size = { width: 360, text: 5000 }
const viewport = { width: 1280, height: 800 }
process.stdout.write(JSON.stringify([
  clampSize(size, viewport),
  clampSize(size, viewport, 298),
  clampSize(size, { width: 1280, height: 300 }, 298),
]))
"""
    )
    assert out == [
        {"width": 360, "text": 570},
        {"width": 360, "text": 502},
        {"width": 360, "text": 100},
    ]


def test_the_lock_tip_fits_the_room_up_to_the_right_edge_of_the_window() -> None:
    """잠금 까닭 풍선은 단추 왼쪽 끝에서 창 오른쪽 끝까지만 쓴다 — 창 상자가 넘치는 것을 잘라 넘으면
    글 끝이 사라졌다(폭 360 화면, 제목 옆 단추). 자리가 아주 좁아도 읽을 폭은 남긴다."""
    out = _node(
        """
process.stdout.write(JSON.stringify([
  tipRoom(346, 156),
  tipRoom(1000, 100),
  tipRoom(346, 340),
]))
"""
    )
    assert out == [182, 892, 96]


_INSTALL_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const styles = {}
const holderStyles = {}
const attrs = {}
const rect = (top, height, left = 0, width = 300) => ({
  top, height, left, width, right: left + width, bottom: top + height,
})
const narrow = () => parseInt(styles['--capa-paste-w'], 10) <= 400
const root = {
  style: {
    setProperty: (name, value) => { styles[name] = value },
    removeProperty: (name) => { delete styles[name] },
  },
  setAttribute: () => {},
  removeAttribute: () => {},
}
// 좁으면 작업 줄이 접혀 글 칸이 아래로 내려간다 — 폭을 먼저 입혀야 이 차이가 재인다. 창이 스크롤되면
// 화면 자리는 그만큼 올라간다.
const textBox = { getBoundingClientRect: () => rect((narrow() ? 200 : 120) - input.scroll, 300) }
const confirmBox = { getBoundingClientRect: () => rect((narrow() ? 510 : 430) - input.scroll, 30) }
const area = { value: '' }
const applyButton = { disabled: false }
const holder = {
  querySelector: () => applyButton,
  setAttribute: (name, value) => { attrs[name] = value },
  removeAttribute: (name) => { delete attrs[name] },
  getBoundingClientRect: () => rect(90, 40, 156, 120),
  style: { setProperty: (name, value) => { holderStyles[name] = value } },
}
const box = {
  closest: () => ({ scrollTop: input.scroll }),
  getBoundingClientRect: () => rect(40, 500, 16, 330),
}
const dialog = {
  parentElement: box,
  addEventListener: () => {},
  removeEventListener: () => {},
  appendChild: () => {},
  querySelectorAll: () => [],
  querySelector: (selector) => {
    if (selector.includes('stTextArea')) return textBox
    if (selector.includes('textarea')) return area
    if (selector.includes('capa_paste_apply_')) return holder
    if (selector.includes('capa_paste_confirm_')) return input.confirm && !selector.includes('input') ? confirmBox : null
    return null
  },
}
const win = {
  innerWidth: 1280,
  innerHeight: 800,
  localStorage: { getItem: () => JSON.stringify({ width: input.width, text: 5000 }), setItem: () => {}, removeItem: () => {} },
  addEventListener: () => {},
  removeEventListener: () => {},
  MutationObserver: class { observe() {} disconnect() {} },
}
const document = {
  defaultView: win,
  documentElement: root,
  createElement: () => ({
    setAttribute: () => {}, addEventListener: () => {}, remove: () => {},
  }),
}
const host = { ownerDocument: document, closest: () => dialog }
install(host, {
  storagePrefix: 'p:', sizeKey: 'k', resizable: true, lock: true, marker: 'data-x', handleLabel: 'h',
  reasons: { empty: 'E', confirm: 'C' },
})
process.stdout.write(JSON.stringify({
  text: styles['--capa-paste-text-h'],
  width: styles['--capa-paste-w'],
  room: holderStyles['--capa-paste-tip-room'],
  locked: attrs['data-capa-paste-locked'],
}))
"""


def _run_install(*, width: int, confirm: bool = False, scroll: int = 0) -> Any:
    body = WINDOW_JS[: WINDOW_JS.index("export default function")]
    return run_js_json(
        body + _INSTALL_RUNNER,
        stdin=json.dumps({"width": width, "confirm": confirm, "scroll": scroll}),
        what="창 크기 install 시험",
    )


def test_a_narrow_window_counts_the_folded_row_in_the_text_limit() -> None:
    """폭을 먼저 입히고 글 칸 밖 높이를 잰다 — 좁아 작업 줄이 접히면 끝이 그만큼 줄어 창이 화면 안에
    든다(1280x800, 폭 360). 넓으면 접히지 않아 글 칸이 더 크다."""
    wide = _run_install(width=900)
    narrow = _run_install(width=360)

    # 화면 높이 800 − (글 칸 아래 끝 − 글 칸 높이 + 아래 틈 32).
    assert wide["text"] == f"{800 - (420 - 300 + 32)}px"
    assert narrow["text"] == f"{800 - (500 - 300 + 32)}px"
    assert narrow["width"] == "360px"


def test_the_confirm_check_and_a_scrolled_window_stay_in_the_text_limit() -> None:
    """확인 체크는 글 칸 아래 칸이라 끝에 든다. 창이 스크롤돼 있어도 같은 끝이다 — 스크롤만큼
    되돌려 잰다(그러지 않으면 스크롤할수록 글 칸이 커진다)."""
    plain = _run_install(width=360)
    checked = _run_install(width=360, confirm=True)
    scrolled = _run_install(width=360, scroll=40)

    assert int(checked["text"][:-2]) == int(plain["text"][:-2]) - 40
    assert scrolled["text"] == plain["text"]


def test_the_install_gives_the_lock_tip_its_room() -> None:
    """잠그는 회차에 풍선이 쓸 폭을 재어 단추 칸에 적는다 — 창 오른쪽(346) − 단추 왼쪽(156) − 틈."""
    out = _run_install(width=360)
    assert out["locked"] == "E"
    assert out["room"] == "182px"


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
    """창 함수는 캡션 · 상자를 직접 그리지 않는다 — 말은 알림창 길(`paste_form`)이다. 그 함수가
    부르는 같은 파일 도움 함수(미리보기 구획 등) 한 겹까지 본다."""
    relative, name = site
    function = _top_function(relative, name)
    tree = ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
    helpers = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    called = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    scopes = [function, *(helpers[each] for each in sorted(called & set(helpers)))]
    drawn = [
        f"{scope.name}:{node.func.attr}"
        for scope in scopes
        for node in ast.walk(scope)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in DRAWN_TEXT_METHODS
    ]
    assert not drawn, drawn


def _all_calls() -> list[tuple[str, ast.Call]]:
    found: list[tuple[str, ast.Call]] = []
    paths = [PROJECT_ROOT / "app.py"]
    for base in ("app_pages", "src/capa_simulation"):
        paths.extend(sorted((PROJECT_ROOT / base).rglob("*.py")))
    for path in paths:
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                found.append((relative, node))
    return found


def _text_area_calls() -> list[tuple[str, ast.Call]]:
    return [
        (relative, call)
        for relative, call in _all_calls()
        if isinstance(call.func, ast.Attribute) and call.func.attr == "text_area"
    ]


def test_paste_text_areas_stand_only_in_the_common_part() -> None:
    """같은 꼴은 공통 부품 하나다(설계 규칙 UI-CON-04) — 글 칸을 새로 두면 라벨과 상관없이
    실패한다. 메모 칸이면 까닭과 함께 목록에 두고, 표를 붙여넣는 칸이면 공통 부품을 쓴다."""
    found = Counter(relative for relative, _call in _text_area_calls())
    assert found == Counter({path: count for path, (count, _why) in TEXT_AREA_OUTSIDE.items()})


def test_every_paste_text_area_helper_has_no_tooltip_or_placeholder() -> None:
    """공통 글 칸에는 풍선도 안내 문장(placeholder)도 없다 — 칸의 규칙은 연 회차의 알림과 Guide 가
    말한다."""
    calls = [
        call
        for relative, call in _text_area_calls()
        if relative == "src/capa_simulation/components/paste_form.py"
    ]
    assert len(calls) == 1
    assert not [keyword for keyword in calls[0].keywords if keyword.arg in ("help", "placeholder")]
    app = _window()
    assert not app.exception
    (text,) = app.text_area
    assert not text.placeholder and not text.help


def test_the_templates_of_the_import_window_follow_the_chosen_table() -> None:
    """엑셀·CSV 창의 양식은 고른 표의 것이고 표 이름은 등록할 표 목록과 같다."""
    from capa_simulation.components.equipment_data_workspace import _TARGETS
    from capa_simulation.components.equipment_import_dialog import IMPORT_TEMPLATES

    assert set(IMPORT_TEMPLATES) == set(_TARGETS)
    keys = [entry[2] for entry in IMPORT_TEMPLATES.values()]
    assert len(keys) == len(set(keys))
