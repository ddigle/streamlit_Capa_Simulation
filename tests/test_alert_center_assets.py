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
from pathlib import Path
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


def test_the_alarm_button_wears_the_toolbar_font_like_guide_print_and_theme() -> None:
    """Alarm 단추는 Guide · Print · 테마 단추와 같은 글꼴 · 크기 · 굵기 · 높이다(2026-11-04 검수
    의견 alarm-01) — 셋은 `font:inherit` 로 툴바 글꼴을 물려받고, Alarm 은 그림자 DOM 의
    `all: initial` 뒤 `:host(.capa-alert-alarm)` 이 같은 글꼴을 물려받는다. 변경 칩은 한글 글이라
    앱 글꼴 그대로다."""
    from capa_simulation.components import page_guide, print_button, theme_toggle

    assert "font-family: inherit;" in _rule(":host(.capa-alert-alarm)")
    assert "capa-alert-alarm" in JS
    button = _rule(".tb")
    for declaration in (
        "font-size: 13px;",
        "font-weight: 600;",
        "line-height: 1;",
        "padding: 6px 12px;",
        "border-radius: 8px;",
    ):
        assert declaration in button, declaration
    for module in (page_guide, print_button, theme_toggle):
        assert module.__file__ is not None
        source = Path(module.__file__).read_text(encoding="utf-8")
        for declaration in (
            '"font:inherit", "font-size:13px", "font-weight:600", "line-height:1"',
            '"padding:6px 12px"',
            '"border-radius:8px"',
        ):
            assert declaration in source, (module.__name__, declaration)


def test_the_alarm_and_change_panels_carry_no_description_footer() -> None:
    """Alarm 패널 · 변경 판 바닥 설명은 두지 않는다(2026-11-04 검수 의견 alarm-02 · alarm-11) —
    보관 · 판정 설명은 HOME Guide 가 맡는다."""
    assert "'foot'" not in JS and ".foot" not in CSS
    assert "footer" not in alert_center.TEXT and "changes_footer" not in alert_center.TEXT
    guide = (Path(alerts.__file__).parent / "guides" / "home.md").read_text(encoding="utf-8")
    assert "12시간 · 200줄까지" in guide


def test_the_log_copy_uses_the_clipboard_and_falls_back_to_selected_text() -> None:
    """「로그」 펼침의 「복사」(2026-11-04 검수 의견 alarm-05) — `navigator.clipboard` 로 넣고
    「복사했습니다」, 막히면 고른 글을 든 읽기 전용 칸 + 「Ctrl+C 로 복사하세요」. `execCommand` 는
    막힌 클립보드에서도 참을 돌려 쓰지 않는다. 복사 글은 날짜가 붙은 시각 · 전문 · 딸린 표 이름과
    행 수(행은 싣지 않음)다."""
    copy = JS[JS.index("function copyLog(") :]
    copy = copy[: copy.index("\n}\n")]
    assert "navigator.clipboard" in copy and "writeText(content).then(done, manual)" in copy
    assert "window.isSecureContext" in copy
    assert "document.execCommand" not in JS
    manual = JS[JS.index("function showManualCopy(") :]
    manual = manual[: manual.index("\n}\n")]
    assert "area.select()" in manual and "log_copy_manual" in manual
    pairs = JS[JS.index("function logPairs(") :]
    pairs = pairs[: pairs.index("\n}\n")]
    assert "forCopy ? stamp : hms" in pairs
    assert "t.log_full, row.full" in pairs and "t.log_table" in pairs
    assert "readOnly = true" in JS
    assert alert_center.TEXT["log_copied"] == "복사했습니다"
    assert alert_center.TEXT["log_copy_manual"] == "Ctrl+C 로 복사하세요"


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
const table = {
  columns: ['공정', 'STEP_SEQ', 'UPEH'],
  rows: [['DEMO-P1', 'P100', 0.123456], ['DEMO "P2", B', null, 3]],
  shown: { 공정: { 'DEMO-P1': '가공' } },
}
out.csv = tableCsv(table)
out.cells = [
  tableCell(table, '공정', 'DEMO-P1'),
  tableCell(table, '공정', 'DEMO-P9'),
  tableCell(table, 'UPEH', 0.123456),
  tableCell(table, 'UPEH', 3),
  tableCell(table, 'STEP_SEQ', null),
]
const tabled = [
  { id: 'old', code: 'ST-14', last: 1, table: table },
  { id: 'new', code: 'ST-14', last: 2, table: table },
  { id: 'other', code: 'ST-15', last: 0, table: table },
  { id: 'plain', code: 'ST-14', last: 3 },
]
out.tables = keepNewestTables(tabled).map((row) => [row.id, Boolean(row.table)])
out.tabs = [
  tabMatches('insights대당 Capa', '대당 Capa'),
  tabMatches(' precision_manufacturing 소요대수 ', '소요대수'),
  tabMatches('monitoring확보율', '대당 Capa'),
  tabMatches('anything', ''),
]
out.steps = [tabStep('Summary › Static 대비 일정'), tabStep('소요대수'), tabStep('')]
const kept = { code: 'ST-20', short: '읽지 못함', id: 'page-a', keep: true }
out.kept = [
  keptRowMissing([], kept),
  keptRowMissing([{ kind: 'event', code: 'ST-20', short: '읽지 못함', noteId: 'page-a' }], kept),
  keptRowMissing([{ kind: 'event', code: 'ST-20', short: '읽지 못함', noteId: 'page-b' }], kept),
  keptRowMissing([{ kind: 'event', code: 'ST-20', short: '다른 글', noteId: 'page-a' }], kept),
  keptRowMissing([], { code: 'ST-20', short: '읽지 못함', id: 'page-a' }),
]
out.copy = copyText([
  ['코드', 'ST-15 · 확인 필요 · 상태 알림(바뀔 때만)'],
  ['범위', ''],
  ['원본 오류', 'Traceback\\r\\n  line 1\\nValueError'],
  ['', '이름 없음'],
  ['해소', null],
  ['전문', ' 대당 Capa 가 없어 뺀 경로 2건 '],
])
console.log(JSON.stringify(out))
"""


def test_a_kept_error_row_comes_back_when_the_alarm_no_longer_carries_it() -> None:
    """자리에 마크만 남은 오류(`keep`)는 Alarm 줄이 글의 유일한 자리다 — 줄이 없거나(보관 끝) 같은
    짧은 글의 다른 오류가 덮었으면 다시 세운다. 그 밖의 알림은 한 번 본 id 면 끝이다."""
    assert _node(_RUNNER)["kept"] == [True, False, True, True, False]
    # 다시 세울 때는 알림창을 띄우지 않는다 — 같은 글이면 알림창은 이 탭에 한 번이다.
    handler = JS[JS.index("function handleEvent") : JS.index("function resolveRow")]
    restored = handler[handler.index("C.seenSet.has") : handler.index("remember(C")]
    assert "keptRowMissing" in restored and "showPopup" not in restored
    # 글을 읽는 자리다 — 로그를 펴면 두 줄 말줄임이 풀린다.
    assert "classList.toggle('logopen', now)" in JS and ".item.logopen .tx" in CSS


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
    # 알림에 딸린 표 — CSV 는 원본 값(따옴표 · 쉼표 감쌈), 화면 칸은 표시명 · 끝자리 넷, 표는
    # 코드마다 가장 새 줄에만, 탭 단추는 아이콘 글자 뒤 이름으로 맞댄다.
    assert out["csv"] == '공정,STEP_SEQ,UPEH\r\nDEMO-P1,P100,0.123456\r\n"DEMO ""P2"", B",,3'
    assert out["cells"] == ["가공", "DEMO-P9", "0.1235", "3", ""]
    assert out["tables"] == [["old", False], ["new", True], ["other", True], ["plain", False]]
    assert out["tabs"] == [True, True, False, False]
    # 탭 안 탭은 바깥 칸부터 한 칸씩 연다(가용설비 현황 「Summary › Static 대비 일정」).
    assert out["steps"] == [["Summary", "Static 대비 일정"], ["소요대수", ""], ["", ""]]
    # 로그 복사 글 — 빈 값 · 이름 없는 짝은 빼고, 여러 줄 값은 다음 줄부터 두 칸 들여 잇는다.
    assert out["copy"] == (
        "코드: ST-15 · 확인 필요 · 상태 알림(바뀔 때만)\n"
        "원본 오류:\n  Traceback\n    line 1\n  ValueError\n"
        "전문: 대당 Capa 가 없어 뺀 경로 2건"
    )


def test_the_js_limits_match_the_registry_constants() -> None:
    """반복 창 · 보관 줄 수의 대체값과 시선 끌기 꼴은 파이썬 상수가 data 로 준다 — JS 에 같은 값을
    두 벌 두지 않는다."""
    assert ".repeat_ms" in JS and "limits.rows" in JS and "limits.hours" in JS
    assert alerts.REPEAT_WINDOW_SECONDS * 1000 == 60000


def test_the_alarm_table_downloads_in_the_browser_and_the_tab_hop_waits_for_the_run() -> None:
    """딸린 표의 CSV 는 브라우저 안에서 만든다(BOM · 서버를 부르지 않는다). 「그 화면으로」 의 탭
    고르기는 그 화면 주소(`here`)에 닿고 회차가 끝난 뒤(`data-test-script-state` 가 running 이
    아님) 이름이 맞는 탭 단추를 누른다 — 이미 열린 탭이면 누르지 않는다."""
    download = JS[JS.index("function downloadTable(") :]
    download = download[: download.index("\n}\n")]
    assert "new Blob(['\\ufeff' + tableCsv(table)]" in download and "fetch(" not in download
    settle = JS[JS.index("function settleTab(") :]
    settle = settle[: settle.index("\n}\n")]
    assert "C.data.here !== pending.href || running()" in settle
    assert "aria-selected" in settle and "button.click()" in settle
    assert "goTo(C, row.href, row.tab)" in JS
    for name in ("table_open", "table_rows", "table_csv"):
        assert name in alert_center.TEXT
    assert "position: sticky;" in _rule(".tscroll th")
