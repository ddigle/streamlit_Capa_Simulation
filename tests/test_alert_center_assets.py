# Purpose: 알림 칸 자산의 층·누름·저장·색 계약을 글자로, 기록·지문·배지·툴바 차례 구획을 node 로
# 시험한다.

"""AppTest 는 알림 칸 JS 를 돌리지 못한다. 자산 글자로 드러나는 약속을 여기서 붙잡고, DOM 을 모르는
순수 구획 (`// <alerts-…>`)은 node(없으면 bun)로 떼어 돌린다 — 없으면 건너뛰고 CI 에서는 실패한다.
나머지 동작(알림창 · 시선 끌기 · 패널 · 새로고침 뒤 남음 · 대화상자 위 층 · 390px)은 브라우저로
본다."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from js_runner import run_js_json

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
    """패널 · 변경 판 · 공정 판은 브라우저 안에서만 열고 닫는다 — 트리거 · 상태 값을 보내지 않아
    파이썬 회차가 돌지 않는다(HOME 한 번 그리기가 85 ~ 300ms 라 중요하다, 설계 규칙 UI-PRF-01). 이
    JS 가 파이썬을 부르는 자리는 둘이다 — 다시 붙은 탭의 회차(2차 보드 R1 (가))와 공정 판 「모든
    화면에서 해제」(2026-11-09 보드 C1 (라)). 「공정 고르기」 는 사이드바 공정 칸 단추를 누른다(그
    칸이 연다)."""
    assert "setStateValue" not in JS
    assert JS.count("setTriggerValue") == 2
    assert "const { data, setTriggerValue } = component" in JS
    assert "C.ask = setTriggerValue" in JS
    assert JS.count("C.ask(") == 2
    asker = JS[JS.index("function connectionMoved(") : JS.index("function endReconnectWait(")]
    assert "C.ask('reconnected', Date.now())" in asker
    panel = JS[JS.index("function buildProcessPanel(") : JS.index("function processField(")]
    assert "C.ask('process_clear', Date.now())" in panel
    assert "if (field) field.click()" in panel
    source = Path(alert_center.__file__).read_text(encoding="utf-8")
    assert "on_reconnected_change=_reconnected" in source
    assert "on_process_clear_change=_clear_process" in source
    toggle = JS[JS.index("function togglePanel(") : JS.index("function closePanel(")]
    assert "C.ask" not in toggle


def test_the_process_chip_keeps_accent_for_this_screen_and_orange_only_for_missing() -> None:
    """공정 칩 — 걸리면 강조색 테두리 · 옅은 면, 아니면 흐린 테두리. 주황은 없는 공정 글 · 좁은 창의
    점에만 쓰고, 1400px 미만은 이름 · 없음 글을 숨긴다(변경 칩과 같은 문턱). 합성 샘플 표지는 변경
    칩(주황 면 알약)과 갈리게 점선 네모 · 주황 글이다."""
    assert "var(--ac-border)" in _rule(".chip.proc")
    on = _rule(".chip.proc.on")
    assert "var(--ac-accent) 45%" in on and "var(--ac-accent) 8%" in on
    assert "var(--ac-pending)" in _rule(".chip.proc .miss")
    narrow = CSS[CSS.index("@media (max-width: 1399.98px)") :]
    narrow = narrow[: narrow.index("\n}\n")]
    assert ".chip.proc.has-miss .mdot" in narrow and ".chip .top" in narrow
    sample = _rule(".sample")
    assert "dashed" in sample and "color: var(--ac-pending);" in sample
    assert "background" not in sample


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
    상시 MutationObserver 는 쓰지 않는다(큰 표 화면의 DOM 변화가 많다). 관찰자는 앱 뿌리의 표지
    두 칸(회차 · 연결)만 본다."""
    assert "attributeFilter: [RUN_STATE, CONNECTION_STATE]" in JS
    assert "subtree: true" not in JS and "childList: true" not in JS
    assert "const RUN_STATE = 'data-test-script-state'" in JS
    assert "const CONNECTION_STATE = 'data-test-connection-state'" in JS


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


def test_a_clipped_alarm_table_says_how_much_it_carries_and_offers_no_partial_csv() -> None:
    """앞부분만 실은 표(`alert_table(clip=True)`)의 머리는 「앞 n건 · 전체 m건」 이고, 그 표로 만든
    CSV 는 일부뿐이라 표 안 내려받기를 두지 않는다 — 전체는 그 화면 단추(알림 글이 부른다)."""
    out = _node(
        """
console.log(JSON.stringify([
  tableClipped({ rows: [[1], [2]], total: 3 }),
  tableClipped({ rows: [[1], [2]], total: 2 }),
  tableClipped({ rows: [[1], [2]] }),
]))
"""
    )
    assert out == [True, False, False]
    box = JS[JS.index("function tableBox(") :]
    box = box[: box.index("\n}\n")]
    assert "clipped ? fill(t.table_rows_clipped" in box
    assert "if (!clipped) head.append(csv)" in box
    assert alert_center.TEXT["table_rows_clipped"] == "앞 {n}건 · 전체 {total}건"
    pairs = JS[JS.index("function logPairs(") :]
    pairs = pairs[: pairs.index("\n}\n")]
    assert "t.log_table_value_clipped" in pairs


def test_top_level_names_are_declared_once() -> None:
    """맨 바깥 `const` · `let` · `function` 이름은 한 번만 선언한다 — 두 번이면 모듈이 구문 오류로
    서지 않아 알림창 · Alarm · 변경 칩이 통째로 사라진다. 순수 구획만 떼어 돌리는 시험은 구획 밖과
    겹친 이름을 못 본다."""
    names = re.findall(r"^(?:const|let|function|async function)\s+(\w+)", JS, re.M)
    assert sorted(name for name in set(names) if names.count(name) > 1) == []


_SECTIONS = ("alerts-rows", "alerts-focus", "alerts-storage", "alerts-reconnect")


def _sections() -> str:
    parts = []
    for name in _SECTIONS:
        match = re.search(rf"// <{name}>\n(?P<body>.*?)\n// </{name}>", JS, re.S)
        assert match, f"alert_center.js 에 // <{name}> 구획이 없습니다"
        parts.append(match.group("body"))
    return "\n".join(parts)


def _node(runner: str) -> Any:
    return run_js_json(_sections() + "\n" + runner, what="알림 칸 JS 구획 시험")


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
  { id: 'old', code: 'ST-14', last: 1, tables: [table] },
  { id: 'new', code: 'ST-14', last: 2, tables: [table, table] },
  { id: 'other', code: 'ST-15', last: 0, tables: [table] },
  { id: 'plain', code: 'ST-14', last: 3 },
]
out.tables = keepNewestTables(tabled).map((row) => [row.id, validTables(row.tables).length])
out.valid = [validTables(null).length, validTables([null, {}, { rows: [] }, table]).length]
const shed = [
  { id: 'a', last: 5, tables: [table] },
  { id: 'b', last: 1, tables: [table] },
  { id: 'c', last: 0 },
]
const lighter = withoutOldestTables(shed)
out.shed = lighter.map((row) => [row.id, Boolean(row.tables)])
out.shed_kept = Boolean(shed[1].tables)
out.shed_end = withoutOldestTables([{ id: 'c', last: 0 }])
out.tabs = [
  tabMatches('insights대당 Capa', '대당 Capa'),
  tabMatches(' precision_manufacturing 소요대수 ', '소요대수'),
  tabMatches('monitoring확보율', '대당 Capa'),
  tabMatches('anything', ''),
]
out.steps = [tabStep('Summary › Static 대비 일정'), tabStep('소요대수'), tabStep('')]
const button = (attrs) => ({ getAttribute: (name) => (name in attrs ? attrs[name] : null) })
out.chosen = [
  tabChosen(button({ 'aria-selected': 'true' })),
  tabChosen(button({ 'aria-checked': 'true' })),
  tabChosen(button({ 'aria-selected': 'false' })),
  tabChosen(button({ 'aria-checked': 'false' })),
  tabChosen(button({})),
]
out.go = [
  showsGo('reference_data', '', ''),
  showsGo('', '', ''),
  showsGo('', 'Past Data', ''),
  showsGo('reference_data', '', 'reference_data'),
  showsGo('reference_data', '효율', 'reference_data'),
  showsGo(undefined, '효율', ''),
]
const kept = { code: 'ST-20', short: '읽지 못함', id: 'page-a', keep: true }
out.kept = [
  keptRowMissing([], kept),
  keptRowMissing([{ kind: 'event', code: 'ST-20', short: '읽지 못함', noteId: 'page-a' }], kept),
  keptRowMissing([{ kind: 'event', code: 'ST-20', short: '읽지 못함', noteId: 'page-b' }], kept),
  keptRowMissing([{ kind: 'event', code: 'ST-20', short: '다른 글', noteId: 'page-a' }], kept),
  keptRowMissing([], { code: 'ST-20', short: '읽지 못함', id: 'page-a' }),
]
out.marks = [
  stateMark({ kind: 'state', state: 'open', resolvedWhy: '' }),
  stateMark({ kind: 'state', state: 'resolved', resolvedWhy: 'scope' }),
  stateMark({ kind: 'state', state: 'resolved', resolvedWhy: 'gone' }),
  stateMark({ kind: 'state', state: 'resolved', resolvedWhy: 'changed' }),
  stateMark({ kind: 'event', state: null }),
  stateMark(null),
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


def test_a_restart_is_a_different_boot_mark_stored_in_this_tab() -> None:
    """앞 표지가 있고 다를 때만 재시작이다(2026-11-07 통합 검수 D4 (가)) — 어느 경우든 지금 표지를
    적어 둔다. 저장소가 막힌 브라우저에서는 예외 없이 뜨지 않는다.

    `same` 은 재시작이 아니라는 뜻일 뿐 고침이 남았다는 뜻이 아니다 — 서버는 그대로이고 세션만
    사라진 탭도 여기로 온다. 그 탭은 `sessionLost` 가 맡는다."""
    out = _node(
        """
function fakeWindow(start) {
  const values = new Map(Object.entries(start))
  const sessionStorage = {
    getItem: (key) => (values.has(key) ? values.get(key) : null),
    setItem: (key, value) => values.set(key, value),
  }
  return { values, sessionStorage }
}
const KEY = 'capa-alerts-boot-v1'
const out = {}
const run = (start, key, mark) => {
  globalThis.window = fakeWindow(start)
  const changed = bootChanged(key, mark)
  return [changed, globalThis.window.values.get(KEY) ?? null]
}
out.first = run({}, KEY, 'b')
out.same = run({ [KEY]: '"b"' }, KEY, 'b')
out.different = run({ [KEY]: '"a"' }, KEY, 'b')
out.broken = run({ [KEY]: '{' }, KEY, 'b')
out.not_text = run({ [KEY]: '7' }, KEY, 'b')
out.no_mark = run({ [KEY]: '"a"' }, KEY, undefined)
out.no_key = run({ [KEY]: '"a"' }, undefined, 'b')

globalThis.window = fakeWindow({ [KEY]: '"a"' })
out.twice = [bootChanged(KEY, 'b'), bootChanged(KEY, 'b')]

globalThis.window = {
  sessionStorage: {
    getItem: () => {
      throw new Error('막힘')
    },
    setItem: () => {
      throw new Error('막힘')
    },
  },
}
out.calls_throw = bootChanged(KEY, 'b')
globalThis.window = {
  get sessionStorage() {
    throw new Error('SecurityError')
  },
}
out.access_throws = bootChanged(KEY, 'b')
console.log(JSON.stringify(out))
"""
    )
    assert out == {
        "first": [False, '"b"'],
        "same": [False, '"b"'],
        "different": [True, '"b"'],
        "broken": [False, '"b"'],
        "not_text": [False, '"b"'],
        "no_mark": [False, '"a"'],
        "no_key": [False, '"a"'],
        "twice": [True, False],
        "calls_throw": False,
        "access_throws": False,
    }


def test_the_restart_notice_goes_through_the_event_path_on_receiving_data() -> None:
    """data 를 받을 때 판정하고 보통 사건 알림 길(`handle` — 기록 · 알림창 · 본 사건 id)로 낸다. id
    로도 한 번이라 저장소를 못 고쳐 앞 표지가 남아도 거듭 뜨지 않는다. 세션 만료 알림도 같은
    길이다."""
    entry = JS[JS.index("export default function (component)") :]
    assert (
        "if (bootChanged((data.storage || {}).boot, boot.mark) && handle(C, boot.notice)) "
        "changed = true" in entry
    )
    assert entry.index("bootChanged(") < entry.index("if (changed) persist(C)")
    assert "C.seenSet.has(note.id)" in JS[JS.index("function handleEvent") :]
    assert (
        "if (sessionLost(before, data, C.dialogAtCut) && handle(C, data.session.notice)) "
        "changed = true" in entry
    )
    assert entry.index("sessionLost(") < entry.index("if (changed) persist(C)")
    # 앞 data 는 이번 data 로 고쳐 쓰기 전에 쥔다 — 그 뒤에 쥐면 늘 같은 값이라 뜨지 않는다.
    assert entry.index("const before = C.data") < entry.index("C.data = data")


def test_a_data_arrival_counts_as_a_run_the_marks_can_miss() -> None:
    """본 스레드가 묶인 사이 끝난 회차는 메시지가 한꺼번에 처리돼 회차 표지가 움직이지 않는다
    (Streamlit 1.63 `handleMessage` — 2026-11-08 사본 실측 HOME). 새 세션은 세션 표지로 data 가
    달라 JS 가 불리므로 그 도착을 회차로 센다 — 재시작 · 세션 만료 뒤 회차가 겹치지 않는다."""
    entry = JS[JS.index("export default function (component)") :]
    assert "C.runMoves += 1" in entry
    assert entry.index("C.runMoves += 1") < entry.index("if (changed) persist(C)")
    watcher = JS[JS.index("function watchRoot(") : JS.index("function connectionMoved(")]
    assert "C.runMoves += 1" in watcher


def test_a_lost_session_is_told_only_by_a_tab_that_had_something_to_lose() -> None:
    """같은 문서에서 세션 표지가 바뀌었고 서버는 그대로이며, 변경 목록이 있었거나 끊길 때 대화상자가
    열려 있던 탭에만 뜬다(2차 보드 R2 (가)). 새 문서(새로고침 · 테마 전환 · 새 탭 · 복제한 탭 · 첫
    접속)는 앞 data 가 없고, 재시작은 부트 표지가 달라 `GL-07` 이 맡고, 잃은 것이 없는 탭은 덮개를
    여닫아도 뜨지 않는다."""
    out = _node(
        """
const data = (session, boot, changes) => ({
  session: { mark: session },
  boot: { mark: boot },
  changes,
})
const one = [{ top: '목록 미저장' }]
console.log(JSON.stringify({
  changes: sessionLost(data('s1', 'b', one), data('s2', 'b', []), false),
  dialog: sessionLost(data('s1', 'b', []), data('s2', 'b', []), true),
  nothing: sessionLost(data('s1', 'b', []), data('s2', 'b', []), false),
  same_session: sessionLost(data('s1', 'b', one), data('s1', 'b', one), true),
  restart: sessionLost(data('s1', 'a', one), data('s2', 'b', []), true),
  new_document: sessionLost(undefined, data('s2', 'b', []), true),
  own_first_data: (() => {
    const first = data('s1', 'b', one)
    return sessionLost(first, first, true)
  })(),
  old_server_data: sessionLost({ boot: { mark: 'b' }, changes: one }, data('s2', 'b', []), true),
  no_list: sessionLost(data('s1', 'b', undefined), data('s2', 'b', []), false),
}))
"""
    )
    assert out == {
        "changes": True,
        "dialog": True,
        "nothing": False,
        "same_session": False,
        "restart": False,
        "new_document": False,
        "own_first_data": False,
        "old_server_data": False,
        "no_list": False,
    }


def test_a_reconnected_tab_asks_for_one_run_only_when_the_front_did_not() -> None:
    """붙어 있지 않다가 붙음으로 돌아온 순간만 다시 붙은 것이다. 다시 끊겼거나, 회차 표지가
    움직였거나(프런트가 스스로 돈 회차 — 겹치면 이중 회차다), 회차가 돌고 있으면 부르지 않는다."""
    out = _node(
        """
const step = (connection, runState, moves) => reconnectStep(connection, runState, moves, 300, 400)
console.log(JSON.stringify({
  back: [
    cameBack('PINGING_SERVER', 'CONNECTED'),
    cameBack('CONNECTING', 'CONNECTED'),
    cameBack('CONNECTED', 'CONNECTED'),
    cameBack('CONNECTED', 'PINGING_SERVER'),
    cameBack(null, 'CONNECTED'),
    cameBack(undefined, 'CONNECTED'),
  ],
  step: [
    step('CONNECTED', 'notRunning', 0),
    step('CONNECTED', 'initial', 0),
    step('CONNECTED', 'notRunning', 2),
    step('CONNECTED', 'running', 0),
    step('CONNECTED', 'rerunRequested', 0),
    step('PINGING_SERVER', 'notRunning', 0),
  ],
}))
"""
    )
    assert out == {
        "back": [True, True, False, False, False, False],
        "step": ["ask", "ask", "stop", "stop", "stop", "stop"],
    }


def test_the_wait_counts_quiet_time_on_the_main_thread_not_the_clock() -> None:
    """무거운 화면은 다시 붙자마자 다시 그리느라 1초 남짓 바쁘고, 그 사이 프런트가 스스로 돈 회차의
    표지는 메시지 큐에 묶여 있다 — 시계로 300ms 만 기다리면 표지를 못 보고 회차를 겹친다(2026-11-08
    사본 실측 HOME). 그래서 제때 깬 틱만 조용한 시간으로 세고, 늦게 깨면 처음부터 센다. 가려진 탭은
    타이머가 늘 늦어 조용한 시간이 쌓이지 않으므로 상한에서 부른다."""
    out = _node(
        """
const walk = (gaps) => {
  let quiet = 0
  let waited = 0
  return gaps.map((gap) => {
    quiet = quietAfter(quiet, gap)
    waited += gap
    return reconnectStep('CONNECTED', 'notRunning', 0, quiet, waited)
  })
}
console.log(JSON.stringify({
  idle: walk([50, 50, 50, 50, 50, 50]),
  busy: walk([800, 50, 50, 140, 50, 50, 50, 50, 50, 50]),
  hidden: walk([1000, 1000, 1000, 1000, 1000]),
}))
"""
    )
    assert out == {
        "idle": ["wait", "wait", "wait", "wait", "wait", "ask"],
        "busy": ["wait"] * 9 + ["ask"],
        "hidden": ["wait", "wait", "wait", "wait", "ask"],
    }
    assert "const RECONNECT_WAIT_MS = 300\n" in JS
    assert "const RECONNECT_TICK_MS = 50\n" in JS
    assert "const RECONNECT_LIMIT_MS = 5000\n" in JS


def test_a_press_during_the_wait_holds_the_run_until_its_mark_comes_back() -> None:
    """표지는 왕복해야 움직인다 — 누름이 서버로 가는 동안 부르면 누름의 회차를 끊어 그 누름이
    사라진다(2026-11-08 사본 실측, 왕복 200ms 에서 다시 붙은 뒤 240ms 에 누른 적용 단추). 손이
    닿으면 표지가 돌아오기를 더 기다리고, 끝내 움직이지 않으면 그때 부른다. 상한도 손을 넘지
    않는다."""
    out = _node(
        """
const need = RECONNECT_WAIT_MS
const step = (touched, moves = 0, waited = 400) =>
  reconnectStep('CONNECTED', 'notRunning', moves, need, waited, need, touched)
console.log(JSON.stringify({
  untouched: step(Infinity),
  just_touched: step(10),
  touched_inside: step(need + RECONNECT_TOUCH_MS - 1),
  touched_long_ago: step(need + RECONNECT_TOUCH_MS),
  run_came_back: step(10, 1),
  over_the_limit: step(10, 0, RECONNECT_LIMIT_MS + 1),
  events: TOUCH_EVENTS,
}))
"""
    )
    assert out == {
        "untouched": "ask",
        "just_touched": "wait",
        "touched_inside": "wait",
        "touched_long_ago": "ask",
        "run_came_back": "stop",
        "over_the_limit": "wait",
        "events": ["pointerdown", "click", "keydown"],
    }
    assert "const RECONNECT_TOUCH_MS = 700\n" in JS
    mover = JS[JS.index("function connectionMoved(") : JS.index("function endReconnectWait(")]
    # 기다리는 동안만 듣는다 — 듣기는 다시 붙을 때 서고 틱이 끝나면 걷힌다.
    assert "passive: true, signal: C.reconnectTouch.signal" in mover
    assert mover.index("addEventListener") < mover.index("setTimeout(tick")
    assert "at - touchedAt" in mover
    assert "endReconnectWait(C)\n    if (step === 'ask' && C.ask)" in mover


def test_the_wait_adds_the_round_trip_the_socket_took() -> None:
    """프런트가 스스로 돈 회차의 표지는 망을 왕복해야 닿는다 — 왕복 500ms 에서 300ms 만 기다리면
    표지가 닿기 전에 불러 회차가 두 번 돈다(2026-11-08 사본 실측). 소켓이 붙는 데 걸린 시간으로
    어림한다."""
    out = _node(
        """
console.log(JSON.stringify({
  local: reconnectWait(0),
  far: reconnectWait(500),
  odd: reconnectWait(-5),
  huge: reconnectWait(60000),
  far_early: reconnectStep('CONNECTED', 'notRunning', 0, 500, 500, reconnectWait(500)),
  far_quiet: reconnectStep('CONNECTED', 'notRunning', 0, 800, 800, reconnectWait(500)),
}))
"""
    )
    assert out == {
        "local": 300,
        "far": 800,
        "odd": 300,
        "huge": 5300,
        "far_early": "wait",
        "far_quiet": "ask",
    }
    mover = JS[JS.index("function connectionMoved(") : JS.index("function endReconnectWait(")]
    assert "if (now === CONNECTING) C.connectingAt = performance.now()" in mover
    assert "reconnectWait(before === CONNECTING ? begun - C.connectingAt : 0)" in mover


def test_one_observer_watches_both_marks_and_the_center_does_not_add_another() -> None:
    """회차 표지와 연결 표지는 관찰자 하나가 본다. 칸이 다시 그려져도 뿌리가 같으면 그대로이고,
    뿌리가 바뀌거나 칸을 새로 세우면 앞 관찰자를 끊는다 — 남으면 다시 붙을 때 회차를 두 번
    부른다."""
    assert JS.count("new MutationObserver") == 1
    watcher = JS[JS.index("function watchRoot(") : JS.index("function connectionMoved(")]
    assert "if (!root || (C.runRoot === root && C.runObserver)) return" in watcher
    assert "if (C.runObserver) C.runObserver.disconnect()" in watcher
    assert "attributeFilter: [RUN_STATE, CONNECTION_STATE]" in watcher
    entry = JS[JS.index("export default function (component)") :]
    assert entry.index("retireCenter(C)") < entry.index("createCenter(data)")
    retire = JS[JS.index("function retireCenter(") :]
    retire = retire[: retire.index("\n}\n")]
    assert "C.runObserver.disconnect()" in retire and "endReconnectWait(C)" in retire
    ending = JS[JS.index("function endReconnectWait(") : JS.index("function retireCenter(")]
    assert "clearTimeout(C.reconnectTimer)" in ending and "C.reconnectTouch.abort()" in ending


def test_the_dialog_is_read_at_the_moment_the_connection_leaves() -> None:
    """대화상자는 끊기는 순간에 읽는다 — 다시 붙은 뒤에는 새 회차가 걷고 있을 수 있다."""
    mover = JS[JS.index("function connectionMoved(") : JS.index("function endReconnectWait(")]
    assert (
        "if (before === CONNECTED) C.dialogAtCut = Boolean(document.querySelector(DIALOG))" in mover
    )
    assert mover.index("C.dialogAtCut =") < mover.index("cameBack(before, now)")
    assert "const DIALOG = '[data-testid=\"stDialog\"]'\n" in JS


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


def test_a_merged_event_row_takes_the_new_text_and_the_new_tables() -> None:
    """코드 + 짧은 글이 같은 사건은 한 줄에 합친다 — 글 · 자리와, 표지에 표가 들었으면 표도 새
    것이다(같은 수의 다른 등록 충돌 `SC-04`). 표가 없는 표지는 앞 표를 지우지 않는다."""
    out = _node(
        """
const table = (title) => ({ title, rows: [[1]] })
const fresh = (tables) => ({
  noteId: 'new', full: '새 글', page: '화면', href: 'home', tab: '', cause: '', detail: '',
  origin: '', level: 'check', tables,
})
const row = () => ({ noteId: 'old', full: '옛 글', tables: [table('옛 표')] })
const title = (item) => item.tables.map((one) => one.title)
console.log(JSON.stringify({
  replaced: title(freshenEventRow(row(), fresh([table('새 표')]))),
  kept: title(freshenEventRow(row(), fresh([]))),
  full: freshenEventRow(row(), fresh([])).full,
}))
"""
    )
    assert out == {"replaced": ["새 표"], "kept": ["옛 표"], "full": "새 글"}
    writer = JS[JS.index("function writeEventRow") : JS.index("function handleEvent")]
    assert "freshenEventRow(row, rowFor(note, now))" in writer


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
    assert out["tables"] == [["old", 0], ["new", 2], ["other", 1], ["plain", 0]]
    assert out["valid"] == [0, 2]
    # 저장소가 넘치면 저장본에서 표가 든 가장 오래된 줄의 표부터 뺀다 — 이 문서 안 줄은 그대로다.
    assert out["shed"] == [["a", True], ["b", False], ["c", False]]
    assert out["shed_kept"] is True and out["shed_end"] is None
    assert out["tabs"] == [True, True, False, False]
    # 탭 안 탭은 바깥 칸부터 한 칸씩 연다(가용설비 현황 「Summary › Static 대비 일정」).
    assert out["steps"] == [["Summary", "Static 대비 일정"], ["소요대수", ""], ["", ""]]
    # 탭은 aria-selected, 전환 단추(기준 정보 종류)는 aria-checked 로 고른 상태를 말한다.
    assert out["chosen"] == [True, True, False, False, False]
    # 지금 화면을 가리키는 줄은 열 탭이 있을 때만 「그 화면으로」 를 세운다. HOME 주소는 빈 글이다.
    assert out["go"] == [True, False, True, False, True, False]
    # 상태 알림 줄 표지 — 범위(리비전 · 시나리오 · 조회기간)가 바뀌어 닫힌 줄은 「해소」 가
    # 아니라 「범위 바뀜」 이다(2026-11-08 사용자 답 a3). 조건이 사라진 줄 · 내용이 바뀐 줄은
    # 「해소」 그대로.
    assert out["marks"] == ["open", "scope", "resolved", "resolved", None, None]
    # 로그 복사 글 — 빈 값 · 이름 없는 짝은 빼고, 여러 줄 값은 다음 줄부터 두 칸 들여 잇는다.
    assert out["copy"] == (
        "코드: ST-15 · 확인 필요 · 상태 알림(바뀔 때만)\n"
        "원본 오류:\n  Traceback\n    line 1\n  ValueError\n"
        "전문: 대당 Capa 가 없어 뺀 경로 2건"
    )


def test_a_row_closed_by_a_scope_change_reads_scope_moved_not_resolved() -> None:
    """리비전이 오르면 같은 상태 알림이 새 범위 줄로 다시 서고 앞 줄은 닫힌다 — 조건은 그대로라
    「해소」 로 읽히면 풀린 것처럼 보였다(2026-11-08 사용자 답 a3 · 재현 u3-09 Space 가정 배치
    `EQ-13`). 줄 표지와 로그 짝이 같은 판정(`stateMark`)을 쓰고, 모든 상태 알림에 걸린다."""
    assert alert_center.TEXT["scope_moved"] == "범위 바뀜 {time}"
    assert alert_center.TEXT["log_scope_moved"] == "범위 바뀜"
    assert alert_center.TEXT["resolved"] == "해소 {time}"
    assert "resolved_scope" not in alert_center.TEXT
    panel = JS[JS.index("const mark = stateMark(row)\n    if (mark) {") :]
    panel = panel[: panel.index("const acts = ")]
    assert "mark === 'scope' ? t.scope_moved : t.resolved" in panel
    pairs = JS[JS.index("function logPairs(") :]
    pairs = pairs[: pairs.index("\n}\n")]
    assert "pairs.push([t.log_scope_moved, (forCopy ? stamp : hm)(row.resolvedAt)])" in pairs
    # 줄을 닫는 까닭은 그대로 셋이다 — 범위 교체만 `scope` 다.
    state = JS[JS.index("function handleState(") :]
    state = state[: state.index("\n}\n")]
    assert "resolveRow(C, entry.row, now, 'scope')" in state
    assert "resolveRow(C, entry.row, now, 'gone')" in state
    assert "resolveRow(C, entry.row, now, 'changed')" in state


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
    assert "!tabChosen(button)" in settle and "button.click()" in settle
    # 전환 단추(기준 정보 종류)도 찾되 같은 글이면 탭이 먼저다.
    assert (
        "...document.querySelectorAll(TAB_BUTTON), ...document.querySelectorAll(SEGMENT_BUTTON)"
        in (settle)
    )
    assert "goTo(C, row.href, row.tab)" in JS
    # 변경 칩 줄도 같다 — 줄이 그 화면 안 탭을 들고 있으면 그 탭까지 연다.
    assert "goTo(C, item.href, item.tab)" in JS
    for name in ("table_open", "table_rows", "table_csv"):
        assert name in alert_center.TEXT
    assert "position: sticky;" in _rule(".tscroll th")
    # 칸 머리 풍선은 `title`, 뜻이 있는 칸임을 점선 밑줄로 보인다.
    box = JS[JS.index("function tableBox(") :]
    box = box[: box.index("\n}\n")]
    assert "cell.title = help" in box and "'hint'" in box
    assert "underline dotted" in _rule(".tscroll th.hint")
    # 한 줄의 표마다 단추 하나 · 펼침 칸 하나이고, 지문 표(새로고침에 다시 뜨지 않게)를 표가 든
    # 기록보다 먼저 쓴다.
    assert "validTables(row.tables).forEach((table, index)" in JS
    persist = JS[JS.index("function persist(") :]
    persist = persist[: persist.index("\n}\n")]
    assert persist.index("storage.states") < persist.index("storage.log")
    assert "withoutOldestTables(saving)" in persist


_FOCUS_FAKES = """
const node = (attrs, extra) => ({
  attrs: { ...attrs },
  focused: 0,
  hasAttribute(name) { return name in this.attrs },
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null },
  setAttribute(name, value) { this.attrs[name] = value },
  removeAttribute(name) { delete this.attrs[name] },
  focus() { this.focused += 1 },
  ...extra,
})
const hostOf = (button, attrs) => node(attrs, {
  querySelector: (selector) => {
    if (selector === 'button:disabled') return button && button.disabled ? button : null
    return button
  },
})
const docOf = (hosts, active) => ({
  querySelectorAll: () => hosts,
  activeElement: active,
  body: { body: true },
})
"""


def test_a_locked_button_lends_its_tab_stop_to_the_tip_host() -> None:
    """꺼진 단추를 감싼 칸이 탭 자리를 맡고 이름을 단다 — 단추가 풀리면 걷어 탭 자리가 둘이 되지
    않는다. 그 칸이 초점을 쥐고 있었으면 단추로 넘겨 Tab 이 제자리에서 잇는다. 잠긴 단추가 없던
    칸은 건드리지 않는다."""
    out = _node(
        _FOCUS_FAKES
        + """
const locked = node({ 'aria-label': '이전' }, { disabled: true })
const labelled = node({}, { disabled: true, querySelector: () => ({ textContent: ' 보관 실행 ' }) })
const freed = node({}, { disabled: false })
const plain = node({}, { disabled: false })
const hosts = [
  hostOf(locked, {}),
  hostOf(labelled, {}),
  hostOf(freed, { tabindex: '0', 'aria-label': '옛 이름' }),
  hostOf(plain, {}),
]
const doc = docOf(hosts, hosts[2])
syncLockedTips(doc)
process.stdout.write(JSON.stringify({
  attrs: hosts.map((host) => host.attrs),
  freedFocus: freed.focused,
}))
"""
    )
    assert out["attrs"] == [
        {"tabindex": "0", "aria-label": "이전"},
        {"tabindex": "0", "aria-label": "보관 실행"},
        {},
        {},
    ]
    assert out["freedFocus"] == 1


def test_tab_from_an_open_popover_button_steps_into_its_body() -> None:
    """팝오버 본문은 문서 끝 포털이라 Tab 이 단추 다음 칸으로 건너뛴다 — 열린 단추에서 Tab 을 누르면
    본문 첫 탭 자리(꺼진 단추만 있으면 감싼 칸)로 들어간다. 제목의 숨은 고리처럼 초점을 받지 못하는
    칸은 건너뛴다. 닫힌 단추 · Shift+Tab · 다른 칸 · 탭 자리가 없는 본문은 브라우저에 맡긴다."""
    out = _node(
        """
const run = ({ testid = 'stPopoverButton', expanded = 'true', shift = false, first = true }) => {
  const active = { getAttribute: (name) => (name === 'data-testid' ? testid : expanded) }
  const doc = { activeElement: active }
  const hidden = { focus() {} }
  const stop = { focused: 0, focus() { this.focused += 1; doc.activeElement = this } }
  const body = { querySelectorAll: () => (first ? [hidden, stop] : [hidden]) }
  doc.querySelector = () => body
  let prevented = 0
  const done = enterOpenPopover(doc, { shiftKey: shift, preventDefault: () => { prevented += 1 } })
  return [done, stop.focused, prevented]
}
process.stdout.write(JSON.stringify({
  open: run({}),
  closed: run({ expanded: 'false' }),
  back: run({ shift: true }),
  other: run({ testid: 'stBaseButton-secondary' }),
  empty: run({ first: false }),
}))
"""
    )
    assert out["open"] == [True, 1, 1]
    for case in ("closed", "back", "other", "empty"):
        assert out[case] == [False, 0, 0]


def test_a_tip_held_by_a_mouse_press_closes_when_the_pointer_leaves() -> None:
    """마우스로 누른 단추는 초점을 쥔 채 남고 Streamlit 풍선은 초점이 든 동안 닫지 않는다 — 마우스가
    칸을 떠날 때 칸에 초점 나감을 보낸다. 키보드 초점의 풍선은 그대로 두고, 칸 안에서 옮겨 다니거나
    다른 칸을 떠난 마우스에는 움직이지 않는다."""
    out = _node(
        """
globalThis.FocusEvent = class {
  constructor(type, init) {
    this.type = type
    this.bubbles = init.bubbles
    this.relatedTarget = init.relatedTarget
  }
}
const run = ({ keyboard = false, target = 'inside', related = 'outside', inTip = true }) => {
  const sent = []
  const host = { contains: (other) => other === 'inside' || other === 'held' }
  const held = {
    closest: () => (inTip ? host : null),
    matches: () => keyboard,
    dispatchEvent: (event) => sent.push([event.type, event.bubbles, event.relatedTarget]),
  }
  const done = releaseHeldTip({ activeElement: held }, { target, relatedTarget: related })
  return [done, sent]
}
process.stdout.write(JSON.stringify({
  mouse: run({}),
  keyboard: run({ keyboard: true }),
  within: run({ related: 'inside' }),
  elsewhere: run({ target: 'outside' }),
  noTip: run({ inTip: false }),
  nothing: releaseHeldTip({ activeElement: null }, { target: 'inside', relatedTarget: null }),
}))
"""
    )
    assert out["mouse"] == [True, [["focusout", True, None]]]
    assert out["keyboard"] == [False, []]
    assert out["within"] == [False, []]
    assert out["elsewhere"] == [False, []]
    assert out["noTip"] == [False, []]
    assert out["nothing"] is False


def test_focus_that_falls_out_of_an_open_dialog_comes_back() -> None:
    """대화상자의 Esc 는 그 안의 키 사건으로만 듣는다 — 초점이 문서로 빠지면 나간 칸으로, 그 칸이
    없거나 초점을 받지 못하면 대화상자로 되돌린다. 초점이 이미 다른 곳에 갔거나 대화상자가 닫혔으면
    두고 본다."""
    out = _node(
        _FOCUS_FAKES
        + """
const run = ({ open = true, leftAlive = true, elsewhere = false }) => {
  const doc = docOf([], null)
  doc.activeElement = elsewhere ? { other: true } : doc.body
  const dialog = node({}, { isConnected: open })
  const left = node({}, { isConnected: leftAlive })
  left.focus = () => { left.focused += 1; doc.activeElement = left }
  dialog.focus = () => { dialog.focused += 1; doc.activeElement = dialog }
  return [returnDialogFocus(doc, dialog, left), left.focused, dialog.focused]
}
const stuck = () => {
  const doc = docOf([], null)
  doc.activeElement = doc.body
  const dialog = node({}, { isConnected: true })
  const left = node({}, { isConnected: true })
  return [returnDialogFocus(doc, dialog, left), left.focused, dialog.focused]
}
process.stdout.write(JSON.stringify({
  back: run({}),
  gone: run({ leftAlive: false }),
  elsewhere: run({ elsewhere: true }),
  closed: run({ open: false }),
  unfocusable: stuck(),
}))
"""
    )
    assert out["back"] == [True, 1, 0]
    assert out["gone"] == [True, 0, 1]
    assert out["elsewhere"] == [False, 0, 0]
    assert out["closed"] == [False, 0, 0]
    # 나간 칸이 초점을 받지 못하는 꼴(꺼진 단추)이면 대화상자가 받는다.
    assert out["unfocusable"] == [True, 1, 1]


def test_the_focus_shell_is_one_set_of_listeners_that_never_runs_the_app() -> None:
    """처리기는 문서에 한 벌이고(알림 칸이 다시 서도 늘지 않는다), 세 일은 사건 자리에서 묶인다 —
    Tab 을 누른 순간 맞추어 회차 없이 열린 팝오버 안 단추도 들고 평소에는 값이 들지 않는다."""
    shell = JS[JS.index("function installFocusShell(") :]
    shell = shell[: shell.index("\n}\n")]
    assert "if (window.__capaFocusShell) return" in shell
    assert "event.key !== 'Tab'" in shell and "syncLockedTips(document)" in shell
    assert "enterOpenPopover(document, event)" in shell
    assert "'pointerout'" in shell and "releaseHeldTip(document, event)" in shell
    # 돌아온 초점의 풍선은 React 가 연 뒤에 닫는다 — 거품 단계이고, 마우스가 위에 있으면 두고 본다.
    arrived = shell[shell.index("'focusin'") : shell.index("'focusout'")]
    assert "!host.matches(':hover')" in arrived
    assert "\n  })\n" in arrived, "포착 단계(세 번째 인자 true)가 아니라 거품 단계다"
    assert "'focusout'" in shell and "!event.relatedTarget" in shell
    assert "returnDialogFocus(document, dialog, left), FOCUS_RETURN_MS" in shell
    assert "installFocusShell()" in JS[JS.index("export default function") :]
    assert "MutationObserver" not in shell


def test_tab_past_a_head_panel_edge_closes_it_back_to_its_button() -> None:
    """머리 띠 판(Alarm · 변경 · 공정)은 body 끝 호스트에 붙어 마지막 칸 다음 Tab 이 문서
    밖(body)으로 빠졌다(통합 재측정 — 공정 판 「모든 화면에서 해제」 다음). 가두지 않는다(모달이
    아니다): 마지막 칸 다음 Tab 은 판을 닫고 연 단추에 초점을 돌린 뒤 막지 않아 브라우저가 그 단추
    다음 차례로 넘기고, 첫 칸 · 판 자체 앞 Shift+Tab 은 판을 닫고 연 단추에 선다. 세 판이 문서
    처리기 한 벌의 같은 길이다."""
    out = _node(
        """
console.log(JSON.stringify([
  panelTabExit(3, 2, false),
  panelTabExit(3, 1, false),
  panelTabExit(3, -1, false),
  panelTabExit(0, -1, false),
  panelTabExit(3, 0, true),
  panelTabExit(3, -1, true),
  panelTabExit(3, 2, true),
]))
"""
    )
    assert out == ["next", None, None, "next", "back", "back", None]
    leave = JS[JS.index("function leavePanelByTab(") :]
    leave = leave[: leave.index("\n}\n")]
    assert "panelOf(C, C.open)" in leave and "PANEL_TABBABLE" in leave
    # 닫고 연 단추로 초점을 돌린 뒤, 앞으로 가는 Tab 은 막지 않는다(브라우저가 단추 다음 차례로
    # 넘긴다).
    closing = leave.index("closePanel(C, true)")
    assert closing < leave.index("if (exit === 'back') event.preventDefault()")
    keys = JS[JS.index("// 판 밖 누름 · Esc 로 닫는다") :]
    keys = keys[: keys.index("window.addEventListener('resize'")]
    assert "event.key === 'Tab' && C.open" in keys and "leavePanelByTab(C, event)" in keys
    assert "select:enabled" in JS[JS.index("const PANEL_TABBABLE") :].splitlines()[0]


_PROCESS_RUNNER = """
const process = {
  values: ['Mold', 'Underfill', 'PMC'],
  labels: ['몰드', '', 'PMC'],
  top: '몰드 외 2개',
  origin: '산출 결과',
  version: 3,
  here: { on: true, follows: true, missing: [] },
}
const live = {
  page: 'space_status',
  version: 3,
  here: { on: true, follows: true, missing: ['PMC'] },
}
const out = {}
out.none = processChipOf(null, null, '')
out.empty = processChipOf({ values: [] }, null, '')
out.guess = processChipOf(process, null, 'space_status')
out.live = processChipOf(process, live, 'space_status')
out.otherPage = processChipOf(process, live, 'calculation_result')
out.stale = processChipOf({ ...process, version: 4 }, live, 'space_status')
out.home = processChipOf({ ...process, here: null }, null, '')
const single = { on: false, follows: false, missing: ['PMC'] }
out.single = processChipOf({ ...process, here: single }, null, 'x')
const rest = '{first} 외 {n}개'
const ordered = {
  page: 'space_status',
  version: 3,
  here: { on: true, follows: true, inside: ['Underfill', 'Mold'], missing: ['PMC'] },
}
out.ordered = processChipOf(process, ordered, 'space_status', rest)
out.orderedHome = processChipOf({ ...process, here: null }, null, '', rest)
const one = { ...process, values: ['PMC'], labels: [''], here: null }
out.orderedOne = processChipOf(one, null, '', rest)
const marks = [
  { page: 'a', version: 1 },
  { page: 'space_status', version: 3, here: null, tab: { miss: true } },
]
out.mine = processLiveOf(marks, 'space_status', 3, false)
out.running = processLiveOf([], 'space_status', 3, false)
out.settled = processLiveOf([{ page: 'a' }], 'space_status', 3, true)
console.log(JSON.stringify(out))
"""


def test_the_process_chip_reads_the_screens_own_mark_over_the_python_guess() -> None:
    """공정 칩(`processChipOf`) — 값이 없으면 칩이 없다. 이 화면 · 같은 판의 회차 표지가 파이썬
    짐작보다 이기고, 다른 화면 · 옛 판의 표지는 쓰지 않는다. 없는 공정은 이 화면이 따르는 꼴일 때만
    센다. 회차 표지(`processLiveOf`) — 이 화면 주소의 마지막 표지, 회차가 끝났는데 없으면 「그리지
    않음」, 도는 동안 없으면 앞 값을 둔다(null)."""
    out = _node(_PROCESS_RUNNER)
    assert out["none"] is None and out["empty"] is None
    guess = out["guess"]
    assert (guess["count"], guess["top"], guess["origin"]) == (3, "몰드 외 2개", "산출 결과")
    assert [row["label"] for row in guess["rows"]] == ["몰드", "Underfill", "PMC"]
    assert (guess["on"], guess["follows"], guess["absent"]) == (True, True, 0)
    live = out["live"]
    assert live["absent"] == 1 and [row["absent"] for row in live["rows"]] == [False, False, True]
    assert out["otherPage"]["absent"] == 0
    assert out["stale"]["absent"] == 0
    assert (out["home"]["on"], out["home"]["follows"]) == (False, False)
    # 따르지 않는 꼴이면 없는 공정을 세지 않는다(하나 따라감 화면에 값이 여럿).
    assert out["single"]["absent"] == 0
    # 따르는 화면이면 이 화면 선택지 차례(걸린 공정 먼저, 없는 공정 뒤)로 줄과 첫 이름을 세운다 —
    # 사이드바 값 칸 · 탭 풍선과 첫 이름이 같다. 따르지 않는 화면은 보낸 차례다.
    ordered = out["ordered"]
    assert [row["value"] for row in ordered["rows"]] == ["Underfill", "Mold", "PMC"]
    assert [row["label"] for row in ordered["rows"]] == ["Underfill", "몰드", "PMC"]
    assert (ordered["top"], ordered["absent"]) == ("Underfill 외 2개", 1)
    assert out["orderedHome"]["top"] == "몰드 외 2개"
    assert out["orderedOne"]["top"] == "PMC"
    assert out["mine"]["tab"] == {"miss": True}
    assert out["running"] is None
    assert out["settled"] == {
        "page": "space_status",
        "version": 3,
        "here": None,
        "tab": None,
        "drawn": False,
    }
