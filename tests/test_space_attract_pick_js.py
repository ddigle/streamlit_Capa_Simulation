# Purpose: Space 「호기 정보」 창이 바꾼 도면 강조의 시선 끌기 대상 판정과 그 둘레를 검사한다.

"""2026-11-12 Space 시안 보드 답 5-2 (나) · 5-3 (가) — 창 줄을 눌러 고른 것이 바뀌거나 사람이 걸러
맞는 호기가 바뀌면(이 층 도면에 보이는 대상 5대 이하, 묶음 1대) 알림 칸의 같은 알림 시선 끌기와
같은 꼴 · 같은 값으로 그 테에 시선을 끈다(설계 규칙 UI-NAV-02 넷째 자리).

대상 판정은 `editor.js` 의 `// <attract-pick>` 구획이고 node 로 떼어 돌린다(node·bun 이 없으면
건너뛰고 CI 에서는 실패 — `test_space_module_group._node`). 테 그리기 · 거는 자리 · 걷는 자리는 자산
글자로 붙잡고 실제 움직임은 브라우저로 본다.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest
from test_space_module_group import _node

from capa_simulation import alerts
from capa_simulation.components import alert_center, space_layout_editor
from capa_simulation.services.space_layout_edit import EditorInputs

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
HTML = (ASSETS / "editor.html").read_text(encoding="utf-8")
ALERT_JS = (alert_center._ASSETS / "alert_center.js").read_text(encoding="utf-8")
_PICK = re.compile(r"// <attract-pick>\n(?P<body>.*?)\n\s*// </attract-pick>", re.S)

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
process.stdout.write(JSON.stringify(input.cases.map((c) => {
  const groups = new Map(Object.entries(c.groups || {}))
  const hidden = new Set(c.hidden || [])
  const keyOf = (id) => (groups.has(id) ? `g:${groups.get(id)}` : `u:${id}`)
  const seen = (id) => !hidden.has(id)
  return attractPick(c.before, c.after, keyOf, seen, c.most)
})))
"""


def _between(start: str, end: str) -> str:
    """`start` 부터 그 뒤 처음 나오는 `end` 앞까지."""
    at = JS.index(start)
    return JS[at : JS.index(end, at)]


def _pick(cases: list[dict[str, Any]]) -> list[list[str]]:
    block = _PICK.search(JS)
    assert block, "editor.js 에 // <attract-pick> 구획이 없습니다"
    result: Any = _node(block.group("body") + _RUNNER, {"cases": cases})
    return [list(keys) for keys in result]


def _case(
    before: list[str] | None,
    after: list[str] | None,
    *,
    groups: dict[str, str] | None = None,
    hidden: list[str] | None = None,
    most: int = 5,
) -> dict[str, Any]:
    return {
        "before": before,
        "after": after,
        "groups": groups or {},
        "hidden": hidden or [],
        "most": most,
    }


SINGLES = [f"DEMO-EQ-{n:02d}" for n in range(1, 8)]
BUNDLE = {"DEMO-MOD-A": "DEMO-MAIN-1", "DEMO-MOD-B": "DEMO-MAIN-1", "DEMO-MOD-C": "DEMO-MAIN-1"}


def test_five_targets_draw_and_six_do_not_with_a_bundle_counted_once() -> None:
    """셈은 대상 수다 — 낱 호기 하나가 1, Main 설비 모듈 묶음 하나가 1(모듈 셋이 맞아도). 5대는
    걸리고 6대는 걸리지 않는다. 걸 대상은 처음 만난 차례의 묶음 열쇠다."""
    bundle = list(BUNDLE)
    five = _case(None, SINGLES[:4] + bundle, groups=BUNDLE)
    six = _case(None, SINGLES[:5] + bundle, groups=BUNDLE)
    one = _case(None, bundle, groups=BUNDLE)
    assert _pick([five, six, one]) == [
        [f"u:{unit}" for unit in SINGLES[:4]] + ["g:DEMO-MAIN-1"],
        [],
        ["g:DEMO-MAIN-1"],
    ]


def test_the_count_covers_only_targets_seen_on_this_floor_drawing() -> None:
    """화면 밖도 센다 — 판정은 이 층 도면에 보이는가(`seen` — 보기는 기준일 · 겹쳐 숨김까지)만
    본다. 숨은 호기는 세지도 걸지도 않아, 맞음 6대 가운데 하나가 숨으면 5대로 걸린다. 묶음은 모듈
    하나라도 보이면 1대다."""
    six_one_hidden = _case(None, SINGLES[:6], hidden=[SINGLES[5]])
    bundle_half_hidden = _case(
        None, list(BUNDLE), groups=BUNDLE, hidden=["DEMO-MOD-A", "DEMO-MOD-B"]
    )
    all_hidden = _case(None, SINGLES[:2], hidden=SINGLES[:2])
    assert _pick([six_one_hidden, bundle_half_hidden, all_hidden]) == [
        [f"u:{unit}" for unit in SINGLES[:5]],
        ["g:DEMO-MAIN-1"],
        [],
    ]


def test_the_same_visible_targets_do_not_draw_again() -> None:
    """보이는 대상이 앞과 같으면 걸지 않는다 — 같은 묶음의 다른 모듈 줄을 누름(5-1 뒤 강조가
    그대로), 같은 줄을 다시 누름, 숨은 호기만 바뀐 거르기. 강조가 없어지거나(null · 빈 맞음)
    대상이 바뀌면 그에 따른다."""
    same_bundle = _case(["DEMO-MOD-A"], ["DEMO-MOD-B"], groups=BUNDLE)
    same_row = _case([SINGLES[0]], [SINGLES[0]])
    hidden_only = _case(SINGLES[:2], [*SINGLES[:2], SINGLES[2]], hidden=[SINGLES[2]])
    cleared = _case(SINGLES[:2], None)
    emptied = _case(SINGLES[:2], [])
    moved = _case(["DEMO-MOD-A"], [SINGLES[0]], groups=BUNDLE)
    narrowed = _case(SINGLES[:3], SINGLES[:2])
    assert _pick([same_bundle, same_row, hidden_only, cleared, emptied, moved, narrowed]) == [
        [],
        [],
        [],
        [],
        [],
        [f"u:{SINGLES[0]}"],
        [f"u:{unit}" for unit in SINGLES[:2]],
    ]


def test_only_a_hand_filter_or_a_row_press_draws_and_a_menu_waits_for_its_close() -> None:
    """사람의 거르기만 건다(Q4 (c)) — `refreshHits(fromUser)` 의 참은 칸 필터 규칙(`setRule` — 칩
    지우기 · 펼침 체크 · 범위), 모두 지우기, 「도면에서 강조」 셋뿐이다. 회차 · 페이더 · 받은 표
    (`adoptSheet`)가 부르는 `renderSheet()` 는 걸지 않는다. 칸 필터 펼침이 열린 동안의 체크는 처음
    맞음을 쥐고 펼침을 닫을 때 한 번 견준다 — 이어서 같은 손길이 다시 거르면 그쪽이 쥔 맞음을
    쓴다."""
    hits = _between("  function refreshHits(fromUser) {", "  function settleAttract() {")
    paint = "for (const [id, group] of S.groups) paintFilter(group, id)"
    assert hits.index(paint) < hits.index("if (!fromUser) return")
    assert "if (S.attractBase === undefined) S.attractBase = before || null" in hits
    assert "attractHits(base, S.filterHits)" in hits
    render = _between("  function renderSheet(fromUser) {", "  function drawSheetTable(")
    assert render.count("refreshHits(fromUser)") == 2 and "refreshHits()" not in render
    assert JS.count("renderSheet(true)") == 3
    rule = _between("  function setRule(", "  function menuColumn()")
    assert "renderSheet(true)" in rule
    assert "renderSheet(true)" in _between("sheetClear.onclick = () => {", "sheetHl.onchange")
    assert "renderSheet(true)" in _between("sheetHl.onchange = () => {", "sheetChips.onclick")
    assert "refreshHits(true)" not in JS
    adopt = _between("  function adoptSheet() {", "  function sheetRows() {")
    assert "refreshHits" not in adopt and "renderSheet" not in adopt
    close = _between("  function closeMenu(focusBack) {", "  function renderMenu() {")
    assert "if (S.attractBase !== undefined) queueMicrotask(settleAttract)" in close


def test_a_row_press_draws_after_the_view_has_moved_to_the_target() -> None:
    """줄 누르기(`goToUnit`)는 고르기 · 확대 · 창 비키기를 마친 뒤에 건다 — 그 전 고른 것과 묶음
    열쇠로 견주고, 닿을 테는 묶음 상자(보기 실선 · 편집 범위 테두리), 낱 호기는 상자다. 테 색은
    선택 강조색(`pick`)이다."""
    go = _between("  function goToUnit(id) {", "  function setRule(")
    assert go.index("const picked = [...S.selection]") < go.index("      select(id)\n")
    assert go.index("if (shift) panBy(") < go.index("attractPicked(picked, item)")
    picked = _between("  function attractPicked(before, item) {", "  function sheetDefault() {")
    assert "attractPick(before, after, attractKeyOf, () => true, ATTRACT_MOST)" in picked
    assert "overlay.querySelector('.sle-group-box')" in picked and "'.sle-rect'" in picked
    assert "attractTo([ring.getBoundingClientRect()], 'pick')" in picked
    hits = _between("  function attractHits(before, after) {", "  function attractPicked(")
    assert "attractPick(before, after, attractKeyOf, attractSeen, ATTRACT_MOST)" in hits
    assert "'.sle-filter-ring'" in hits and "'filter')" in hits
    assert "const ATTRACT_MOST = 5\n" in JS
    assert "return Boolean(item) && isUnit(item) && seenModule(item)" in JS


def test_the_motion_reads_its_numbers_from_data_and_stops_when_the_view_changes() -> None:
    """시간 · 곡선은 data `attention`(파이썬 `alerts.attention_payload` — 알림 칸 `limits` 와 같은
    사전)만 쓴다. 움직임 줄이기 설정이면 움직이지 않는 윤곽(`sle-attract-still`)이다. 테는 무대 안
    층(`.sle-attract` — 누름을 받지 않음, body 아님)에 서고 화면 밖 테에는 걸지 않으며, 확대 · 이동
    · 크기 바뀜(`applyView`) · 새 도면(epoch)이면 곧바로 걷는다."""
    draw = _between("  function attractTo(boxes, tone) {", "  function attractHits(")
    for name in ("attention_ms", "easing", "hit_ms", "fade_ms", "still_ms"):
        assert f"ATTENTION.{name}" in draw, name
    assert (
        not re.search(r"duration: \d", draw) and "setTimeout(() => hit.remove(), ATTENTION" in draw
    )
    assert "if (attractStill()) {" in draw and "'sle-attract-still'" in draw
    assert "document.body" not in draw and "attractLayer.append(node)" in draw
    assert "b.right > port.left && b.left < port.right" in draw
    still = _between("  function attractStill() {", "  function stopAttract() {")
    assert "(prefers-reduced-motion: reduce)" in still
    assert "const ATTENTION = data.attention && typeof data.attention === 'object'" in JS
    view = _between("  function applyView(", "  function zoomAt(")
    assert view.index("stopAttract()") < view.index("clampView()")
    assert "stopAttract()" in _between("if (S.epoch !== data.epoch) {", "initFromData()")
    stage = HTML[HTML.index('<div class="sle-stage">') : HTML.index('class="sle-split is-right')]
    assert stage.index("</svg>") < stage.index('<div class="sle-attract" aria-hidden="true"></div>')
    layer = re.search(r"\.sle-attract \{([^}]*)\}", CSS)
    assert layer and "pointer-events: none" in layer.group(1)
    assert "position: absolute; inset: 0" in layer.group(1)
    assert (
        "@media (prefers-reduced-motion: reduce) { .sle-attract-frame { display: none; } }" in CSS
    )
    # 테 색은 닿는 테의 색 — 줄 누르기는 선택 강조색, 필터는 필터 테 색(Q4 (d)).
    assert ".sle-attract-frame { border: 3px solid var(--sle-accent)" in CSS
    assert ".sle-attract-frame.is-filter, .sle-attract-hit.is-filter" in CSS
    assert "border-color: var(--sle-filter-ring)" in CSS


def test_the_alert_center_and_the_space_drawing_read_one_attention_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """움직임 값은 `alerts.py` 한 곳이다 — 알림 칸 data `limits` 와 Space 층 보기 · 편집 data
    `attention` 이 `attention_payload()` 를 그대로 받고, 두 JS 는 수를 직접 적지 않는다."""
    payload = alerts.attention_payload()
    assert payload == {
        "attention_ms": alerts.ATTENTION_MS,
        "easing": alerts.ATTENTION_EASING,
        "hit_ms": alerts.ATTENTION_HIT_MS,
        "fade_ms": alerts.ATTENTION_FADE_MS,
        "still_ms": alerts.ATTENTION_STILL_MS,
    }
    limits = alert_center.alert_center_data(changes=[], events=[])["limits"]
    assert {key: limits[key] for key in payload} == payload
    for name in ("STILL_MS", "HIT_MS", "FADE_MS"):
        assert f"const {name}" not in ALERT_JS, name
    attract = ALERT_JS[ALERT_JS.index("function attract(") :]
    attract = attract[: attract.index("\n}\n")]
    for name in ("still_ms", "hit_ms", "fade_ms", "attention_ms", "easing"):
        assert f"limits.{name}" in attract, name
    assert "|| 450" not in attract and "'ease-out'" not in attract

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        space_layout_editor, "_EDITOR", lambda **kwargs: calls.append(kwargs["data"])
    )
    today = date(2026, 11, 12)
    space_layout_editor.render_space_layout_viewer(
        key="attract_view",
        epoch="e1",
        items=[],
        canvas=(100.0, 60.0),
        floor=("C1", "1F"),
        marks=[],
        summary="",
        as_of=today,
        today=today,
        as_of_range=(date(2025, 11, 12), date(2027, 11, 12)),
        on_as_of=lambda _day: None,
    )
    space_layout_editor.render_space_layout_editor(
        key="attract_edit",
        epoch="e1",
        title="C1 1F",
        inputs=EditorInputs(
            items=(), reserved_extent=(0.0, 0.0), default_size=(12.0, 7.0), unplaced_floorless=0
        ),
        canvas=(100.0, 60.0),
        floor=("C1", "1F"),
        floors=[("C1", "1F")],
        marks=[],
        new_unit={},
        as_of=today,
    )
    assert [call["attention"] for call in calls] == [payload, payload]
