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


_SECTIONS = ("alerts-rows", "alerts-focus", "alerts-storage")


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


def test_a_restart_is_a_different_boot_mark_stored_in_this_tab() -> None:
    """앞 표지가 있고 다를 때만 재시작이다(2026-11-07 통합 검수 D4 (가)) — 어느 경우든 지금 표지를
    적어 둔다. 저장소가 막힌 브라우저에서는 예외 없이 뜨지 않는다.

    `same` 은 재시작이 아니라는 뜻일 뿐 고침이 남았다는 뜻이 아니다 — 서버는 그대로이고 세션만
    사라진 탭도 여기로 온다(`docs/TODO.md` 4장 「세션만 사라진 탭」)."""
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
    로도 한 번이라 저장소를 못 고쳐 앞 표지가 남아도 거듭 뜨지 않는다. 회차를 스스로 돌리지 않는다
    (범위 밖 — 파이썬으로 가는 값이 없다는 것은 위 패널 시험이 본다)."""
    entry = JS[JS.index("export default function (component)") :]
    assert (
        "if (bootChanged((data.storage || {}).boot, boot.mark) && handle(C, boot.notice)) "
        "changed = true" in entry
    )
    assert entry.index("bootChanged(") < entry.index("if (changed) persist(C)")
    assert "C.seenSet.has(note.id)" in JS[JS.index("function handleEvent") :]


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
