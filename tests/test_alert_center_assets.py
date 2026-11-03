# Purpose: 알림 칸 자산의 층·누름·저장·색 계약을 글자로, 기록·지문·배지·툴바 차례 구획을 node 로
# 시험한다.

"""AppTest 는 알림 칸 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속을 여기서 붙잡고, DOM 을 모르는
순수 구획 (`// <alerts-…>`)은 node(없으면 bun)로 떼어 돌린다 — 없으면 건너뛰고 CI 에서는 실패한다.
나머지 동작(알림창 · 시선 끌기 · 패널 · 새로고침 뒤 남음 · 대화상자 위 층 · 390px)은 브라우저로
본다."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

import pytest

from capa_simulation import alerts
from capa_simulation.components import alert_center

ASSETS = alert_center._ASSETS
CSS = (ASSETS / "alert_center.css").read_text(encoding="utf-8")
JS = (ASSETS / "alert_center.js").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r" \{([^}]*)\}", CSS)
    assert match is not None, selector
    return match.group(1)


def test_the_panel_opens_in_the_browser_without_a_python_rerun() -> None:
    """패널 · 칩 판은 브라우저 안에서만 열고 닫는다 — 트리거 · 상태 값을 보내지 않아 파이썬 회차가
    돌지 않는다(HOME 한 번 그리기가 85 ~ 300ms 라 중요하다)."""
    assert "setTriggerValue" not in JS and "setStateValue" not in JS


def test_the_popup_stack_floats_above_dialogs_and_lets_presses_through() -> None:
    """알림창은 오른쪽 아래, 누름을 받지 않고(밑을 누를 수 있다) Streamlit 대화상자(1.63 — 1000059)
    위다. 시선 끌기 테두리도 누름 · 초점을 받지 않는다. 판은 머리 띠(999990) · 진행 막대(999991) 위,
    모바일 사이드바(999995) 아래."""
    stack = _rule(".stack")
    assert "position: fixed;" in stack and "right: 1rem;" in stack and "bottom: 1rem;" in stack
    assert "pointer-events: none;" in stack
    assert "max-width: min(36rem, calc(100vw - 2rem));" in stack
    stack_z = re.search(r"z-index: (\d+);", stack)
    assert stack_z is not None and int(stack_z.group(1)) > 1000059
    frame = _rule(".frame")
    assert "pointer-events: none;" in frame
    panel = _rule(".panel")
    panel_z = re.search(r"z-index: (\d+);", panel)
    assert panel_z is not None and 999991 < int(panel_z.group(1)) < 999995
    assert "stack.setAttribute('role', 'status')" in JS
    assert "stack.setAttribute('aria-live', 'polite')" in JS


def test_reduced_motion_shows_a_still_outline_and_no_moving_frame() -> None:
    """「움직임 줄이기」 에서는 테두리를 움직이지 않는다 — 알림창에 단계 색 윤곽만 잠깐 선다(D4)."""
    assert "prefers-reduced-motion: reduce" in JS
    assert re.search(
        r"@media \(prefers-reduced-motion: reduce\) \{\s*\.frame \{\s*display: none;", CSS
    )
    assert "outline: 2px solid var(--lv);" in _rule(".pop.is-still")
    attract = JS[JS.index("function attract(") :]
    attract = attract[: attract.index("\n}\n")]
    assert "reducedMotion()" in attract and "is-still" in attract
    assert "limits.attention_ms" in attract and "limits.easing" in attract


def test_storage_is_this_browser_tab_and_never_throws() -> None:
    """기록은 이 브라우저 탭의 `sessionStorage` 다(D1 (가)) — 읽기 · 쓰기를 모두 감싼다.
    `localStorage` · 서버로 보내는 길은 없다(L2 는 usage-log 와 함께 — D6)."""
    assert "localStorage" not in JS
    assert "fetch(" not in JS and "XMLHttpRequest" not in JS
    for name in ("function storageGet(", "function storageSet("):
        body = JS[JS.index(name) :]
        body = body[: body.index("\n}\n")]
        assert "try {" in body and "catch (error)" in body


def test_markers_are_read_once_per_run_state_change_without_a_document_observer() -> None:
    """표지는 앱 뿌리의 회차 표지(`data-test-script-state`)가 바뀔 때 훑는다 — 문서 전체를 지켜보는
    상시 MutationObserver 는 쓰지 않는다(큰 표 화면의 DOM 변화가 많다)."""
    assert "attributeFilter: [RUN_STATE]" in JS
    assert "subtree: true" not in JS and "childList: true" not in JS
    assert "const RUN_STATE = 'data-test-script-state'" in JS


def test_colours_come_from_the_palette_not_literals() -> None:
    """색은 파이썬 토큰(`alert_center.palette`)이 data 로 주고 CSS 변수로만 쓴다(두 테마)."""
    assert not re.search(r"#[0-9A-Fa-f]{3,6}\b", CSS)
    assert not re.search(r"rgba?\(", CSS)
    assert not re.search(r"'#[0-9A-Fa-f]{6}'", JS)
    for name in ("info", "check", "action", "error"):
        assert f'[data-level="{name}"] {{ --lv: var(--ac-{name}); }}' in CSS
    for key in alert_center.palette():
        assert f"colors.{key}" in JS


def test_narrow_windows_fold_the_chip_into_the_alarm_dot() -> None:
    """600px 미만에서는 칩을 숨기고 Alarm 왼쪽 위 주황 점 · 패널 맨 위 「이 세션의 변경」 으로
    합친다. 칩 글은 창 폭에 따라 줄어든다(1400 · 900px)."""
    narrow = CSS[CSS.index("@media (max-width: 599.98px) {") :]
    assert ":host(.capa-alert-chip) {\n    display: none;" in narrow
    assert ":host([data-changes]) .dot {\n    display: block;" in narrow
    assert "@media (max-width: 1399.98px)" in CSS and "@media (max-width: 899.98px)" in CSS


# ---------------------------------------------------------------- JS 순수 구획(node)

_SECTIONS = ("alerts-rows",)


def _sections() -> str:
    parts = []
    for name in _SECTIONS:
        match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert match, f"alert_center.js 에 // <{name}> 구획이 없습니다"
        parts.append(match.group("body"))
    return "\n".join(parts)


def _node(runner: str) -> Any:
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 알림 칸 JS 구획 시험을 건너뛸 수 없다")
        pytest.skip("node·bun 이 없다 — CI 에서 돈다")
    completed = subprocess.run(
        [runtime, "-e", _sections() + "\n" + runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


_RUNNER = """
const now = 1000000000
const hour = 3600000
const rows = []
for (let index = 0; index < 205; index += 1) rows.push({ id: String(index), last: now - index *
1000 })
rows.push({ id: 'old', last: now - 13 * hour })
const out = {}
out.pruned = pruneRows(rows, now, 200, 12 * hour).map((row) => row.id)
out.verdicts = [
  stateVerdict(undefined, { active: true, fp: 'a' }),
  stateVerdict({ active: true, fp: 'a' }, { active: true, fp: 'a' }),
  stateVerdict({ active: true, fp: 'a' }, { active: true, fp: 'b' }),
  stateVerdict({ active: true, fp: 'a' }, { active: false, fp: '' }),
  stateVerdict({ active: false, fp: 'a' }, { active: false, fp: '' }),
  stateVerdict({ active: false, fp: 'a' }, { active: true, fp: 'a' }),
]
out.repeat = [
  isRepeat(undefined, now, 60000),
  isRepeat({ visible: true }, now, 60000),
  isRepeat({ visible: false, goneAt: now - 59000 }, now, 60000),
  isRepeat({ visible: false, goneAt: now - 61000 }, now, 60000),
]
out.badge = [
  badgeOf([{ unread: true, level: 'info' }, { unread: true, level: 'action' }, { unread: false,
  level: 'error' }]),
  badgeOf([]),
  badgeOf(Array.from({ length: 120 }, () => ({ unread: true, level: 'check' }))),
]
out.chip = [
  chipOf([{ group: 'lose', top: '기준 정보 적용 전' }, { group: 'assume', top: 'UPEH 가정' }]),
  chipOf([{ group: 'assume', top: '설비 가정' }]),
  chipOf([]),
]
const list = [
  { level: 'info', page: 'HOME', state: null, last: 3 },
  { level: 'check', page: 'Static Capa', state: 'resolved', last: 5 },
  { level: 'check', page: 'HOME', state: 'open', last: 4 },
]
out.visible = [
  visibleRows(list, { level: 'all', page: '', hideResolved: false }).map((row) => row.last),
  visibleRows(list, { level: 'check', page: '', hideResolved: true }).map((row) => row.last),
  visibleRows(list, { level: 'all', page: 'HOME', hideResolved: false }).map((row) => row.last),
]
const order = ['chip', 'guide', 'alarm', 'print', 'theme']
out.before = [
  toolbarBefore(order, 'alarm', ['guide', 'print', 'theme']),
  toolbarBefore(order, 'chip', ['guide', 'alarm', 'theme']),
  toolbarBefore(order, 'alarm', ['guide']),
  toolbarBefore(order, 'other', ['guide']),
]
out.keys = [eventKey({ code: 'FL-01', short: '저장' }), stateKey({ code: 'ST-01', scope: 'abc' })]
console.log(JSON.stringify(out))
"""


def test_the_pure_sections_keep_history_states_badges_chip_and_toolbar_order() -> None:
    """보관(200줄 · 12시간) · 상태 지문 판정 · 반복 창(60초) · 안 읽음 배지(99+ · 가장 무거운 단계)
    · 칩(수 · 맨 위 · 가정만이면 회색) · 패널 거르기 · 툴바 차례(파이썬 `TOOLBAR_BUTTON_ORDER`
    규칙과 같다)."""
    out = _node(_RUNNER)
    assert len(out["pruned"]) == 200 and out["pruned"][0] == "0" and "old" not in out["pruned"]
    assert out["verdicts"] == ["new", "same", "change", "resolved", "none", "new"]
    assert out["repeat"] == [False, True, True, False]
    assert out["badge"] == [
        {"count": 2, "level": "action", "label": "2"},
        {"count": 0, "level": None, "label": "0"},
        {"count": 120, "level": "check", "label": "99+"},
    ]
    assert out["chip"] == [
        {"count": 2, "top": "기준 정보 적용 전", "onlyAssume": False},
        {"count": 1, "top": "설비 가정", "onlyAssume": True},
        {"count": 0, "top": "", "onlyAssume": False},
    ]
    assert out["visible"] == [[5, 4, 3], [4], [4, 3]]
    assert out["before"] == ["print", "guide", None, None]
    assert out["keys"] == ["FL-01\u0000저장", "ST-01|abc"]


def test_the_js_limits_match_the_registry_constants() -> None:
    """반복 창 · 보관 줄 수의 대체값과 시선 끌기 꼴은 파이썬 상수가 data 로 준다 — JS 에 같은 값을
    두 벌 두지 않는다."""
    assert ".repeat_ms" in JS and "limits.rows" in JS and "limits.hours" in JS
    assert alerts.REPEAT_WINDOW_SECONDS * 1000 == 60000
