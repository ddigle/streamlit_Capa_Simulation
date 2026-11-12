# Purpose: Space 층 보기 「반입 일정」 의 상자 토글 · payload · 브라우저 글 판정을 검사한다.

"""2026-11-12 Space 보드 답 1-1 ~ 1-6 — 반입 예정 호기에 반입 일정을 쓰는 표기/미표기 토글.

- **토글**(1-4 sidebar): 사이드바 「Space 도면」 상자의 「공식과 견주기」 바로 아래 「반입 일정」.
  처음은 끔이고 켠 값은 세션에 남는다(층을 옮겨도). 층 배치 편집 중(1-6 view — 보기 화면만)과
  FAB 전체(호기 상자가 없다 — A5 (가))에는 다른 key 의 끈 채 잠근 토글이 같은 자리에 서고, 세션
  값은 그대로라 편집을 끄거나 층으로 가면 돌아온다.
- **payload**: 호기마다 `arrivalPlan`(반입실적, 없으면 반입일정 — A1 (가)) · `arrivalDelayed`
  (반입상태 지연, 실적이 없을 때만)는 늘 실리고(풍선이 토글과 상관없이 쓴다 — A4 (가)), 켠
  회차에만 data `arrivalDates` 가 실린다 — epoch 밖이라 켜고 꺼도 도면이 다시 서지 않는다.
- **글**(1-1 yy · 1-2 inside · 1-5 as-is): `27.05.09`, 지연이면 굵은 「지연」, 날짜가 없으면
  「미정」. 낱 호기는 상자 안 이름 아래(0.82배 · 7px 아래면 숨음), 모듈 묶음은 그날 보이는 반입 전
  모듈의 글이 모두 같으면 Main 설비명 알약 안 둘째 줄에 한 번(1-3 메모 · A3 (가)), 다르면 모듈마다
  상자 안 아래(1-1 메모). 반입한 · 겹쳐 숨긴 모듈은 판정에서 뺀다(A2 (가)).

브라우저 판정은 `// <view-arrival>` 구획을 글자 그대로 떼어 node 로 돌린다(node · bun 이 없으면
건너뛰고 CI 에서는 실패). 그리기 배선은 글자로 본다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from test_space_layout_edit import _master
from test_space_module_group import _node
from test_space_viewer_pick import _open, _viewer, calls

from capa_simulation.components import space_layout_editor

__all__ = ["calls"]

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")

_ARRIVAL = re.compile(r"// <view-arrival>\n(?P<body>.*?)\n\s*// </view-arrival>", re.S)

ARRIVAL_KEY = "space_arrival_dates_v1"
ARRIVAL_LOCKED_KEY = "space_arrival_dates_locked_v1"


def _block() -> str:
    match = _ARRIVAL.search(JS)
    assert match, "editor.js 에 // <view-arrival> 구획이 없습니다"
    return match.group("body")


def _between(start: str, end: str) -> str:
    return JS[JS.index(start) : JS.index(end, JS.index(start))]


# ---------------------------------------------------------------- 글 판정(node)

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
const words = input.words.map(([plan, late]) => {
  const w = arrivalWords(plan, late)
  return { day: w.day, late: w.late, text: arrivalText(w), tip: arrivalTipWords(plan, late) }
})
const modes = input.groups.map((mates) => groupArrivalMode(mates, (m) => m.shown))
const box = arrivalBoxLines(50, 4, 4 * ARRIVAL_FONT_K)
const pills = ['up', 'down', 'mid']
  .map((grow) => ({ grow, ...arrivalPill(20, 3, 3 * ARRIVAL_FONT_K, grow) }))
const k = ARRIVAL_FONT_K
const tall = ARRIVAL_PILL_TALL
process.stdout.write(JSON.stringify({ words, modes, box, pills, k, tall }))
"""


def _run(
    words: list[tuple[str | None, bool]] | None = None,
    groups: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    return _node(
        _RUNNER % _block(),
        {"words": [list(pair) for pair in (words or [])], "groups": groups or []},
    )


def test_the_arrival_words_are_short_dates_with_a_delay_tail_or_undecided() -> None:
    """1-1 yy — `27.05.09` 꼴, 지연이면 뒤에 「지연」, 날짜가 없으면 「미정」(지연이면 「미정
    지연」). 풍선은 토글과 상관없이 「반입 일정 2027-05-09」(지연이면 「(지연)」)다(A4 (가))."""
    out = _run(
        words=[
            ("2027-05-09", False),
            ("2027-03-15", True),
            (None, False),
            (None, True),
            ("2027-5-9", False),
        ]
    )
    assert [item["text"] for item in out["words"]] == [
        "27.05.09",
        "27.03.15 지연",
        "미정",
        "미정 지연",
        "미정",
    ]
    assert [item["late"] for item in out["words"]] == [False, True, False, True, False]
    assert [item["tip"] for item in out["words"]] == [
        "반입 일정 2027-05-09",
        "반입 일정 2027-03-15(지연)",
        "반입 일정 미정",
        "반입 일정 미정(지연)",
        "반입 일정 미정",
    ]


def _module(plan: str | None, *, late: bool = False, shown: bool = True) -> dict[str, Any]:
    return {"arrivalPlan": plan, "arrivalDelayed": late, "shown": shown}


def test_a_module_group_writes_once_when_its_shown_modules_agree_and_each_otherwise() -> None:
    """1-1 · 1-3 메모 — 모듈 일정이 모두 같으면 Main 설비명 밑 한 번(once), 다르면 모듈마다(each).
    날짜와 「지연」 이 모두 같아야 같다. 판정은 그날 보이는 반입 전 모듈끼리다(A2 (가) — 반입한 ·
    겹쳐 숨긴 모듈은 빠진다). 그런 모듈이 없으면 쓰지 않는다(none)."""
    out = _run(
        groups=[
            [_module("2027-05-09"), _module("2027-05-09"), _module("2027-05-09")],
            [_module("2027-05-09"), _module("2027-06-01")],
            [_module("2027-05-09"), _module("2027-05-09", late=True)],
            [_module("2027-05-09"), _module("2027-06-01", shown=False)],
            [_module(None), _module(None)],
            [_module("2027-05-09", shown=False), _module(None, shown=False)],
        ]
    )
    modes = out["modes"]
    assert [mode["mode"] for mode in modes] == ["once", "each", "each", "once", "once", "none"]
    assert modes[0]["words"] == {"day": "27.05.09", "late": False}
    assert modes[3]["words"] == {"day": "27.05.09", "late": False}
    assert modes[4]["words"] == {"day": "미정", "late": False}
    assert modes[1]["words"] is None and modes[5]["words"] is None


def test_the_box_lines_lift_the_name_and_the_pill_grows_away_from_the_range() -> None:
    """1-2 inside — 상자 안 두 줄은 이름을 올리고 날짜를 그 아래(0.82배)에 둔다. 두 줄 덩어리는 상자
    가운데에 선다. A3 (가) — Main 설비명 알약은 둘째 줄만큼 자라는데 바깥 위(up)는 아래 끝, 바깥
    아래(down)는 위 끝을 지키고 가운데(mid)는 가운데를 지킨다."""
    out = _run()
    k = out["k"]
    assert k == pytest.approx(0.82)
    box = out["box"]
    fs, fd = 4, 4 * k
    assert box["nameY"] < 50 < box["dayY"]
    top = box["nameY"] - fs / 2
    bottom = box["dayY"] + fd / 2
    assert (top + bottom) / 2 == pytest.approx(50, abs=fs * 0.2)
    up, down, mid = out["pills"]
    fs, fd = 3, 3 * k
    one_top, one_bottom = 20 - fs * 0.8, 20 + fs * 0.8
    assert up["top"] + up["h"] == pytest.approx(one_bottom)
    assert down["top"] == pytest.approx(one_top)
    assert mid["top"] + mid["h"] / 2 == pytest.approx(20)
    for pill in (up, down, mid):
        assert pill["h"] == pytest.approx(fs * 1.6 + fd * 1.25)
        assert pill["top"] < pill["nameY"] < pill["dayY"] < pill["top"] + pill["h"]
    assert out["tall"] == pytest.approx((fs * 1.6 + fd * 1.25) / (fs * 1.6))


# ---------------------------------------------------------------- 그리기 배선(글자)


def test_the_drawing_wires_the_dates_into_the_view_only() -> None:
    """보기 · 층 도면 · 토글 켬일 때만 쓴다(1-6 view — 편집기는 상자에 날짜 부품이 없다). 상자
    날짜는 이름 크기(`unitLabelSize`)의 0.82배이고 이름이나 날짜가 7px 아래면 숨는다. 칠(반입 전 ·
    겹쳐 숨김 · 보임)과 배율이 바뀔 때마다 다시 맞춘다."""
    assert "const ARRIVAL_ON = VIEW && !FAB && data.arrivalDates === true" in JS
    sync = _between("function syncArrival(group, item) {", "function writeArrival(")
    for part in (
        "const node = group.__parts && group.__parts.arrival",
        "ARRIVAL_ON && group.__visible !== false && group.classList.contains('is-pre')",
        "&& (!mode || mode.mode === 'each')",
        "if (!on) return hide()",
        "fs / upp < UNIT_LABEL_MIN_PX || fd / upp < UNIT_LABEL_MIN_PX",
        "Math.min(fs * ARRIVAL_FONT_K,",
        "node.style.fill = label.style.fill",
    ):
        assert part in sync, part
    shown = JS[JS.index("const arrivalShown = (m) => {") :]
    assert "group.__visible !== false && group.classList.contains('is-pre')" in shown[:400]
    # 상자 자신의 칠은 받은 group 에서 읽는다 — `buildGroup` 은 칠 · 자리를 맞춘 뒤에야
    # `S.groups` 에 넣는다(처음 그리는 회차의 낱 호기 날짜가 빠지지 않게).
    assert "arrivalShown(item)" not in sync
    build = _between("function buildGroup(item) {", "function paintUnit(")
    assert build.index("position(group, item)") < build.index("S.groups.set(item.id, group)")
    assert "arrival: el('text', { class: 'sle-arrival' })" in build
    assert "label, parts.arrival, parts.offline" in build
    assert "syncArrival(group, item)" in _between("function position(", "function unitLabelSize(")
    paint = _between("function paintUnit(", "function buildMark(")
    assert "syncArrival(group, item)" in paint
    assert "${item.arrivalPlan || ''}${+Boolean(item.arrivalDelayed)}" in paint
    late = _between("function writeArrival(", "// ----")
    assert "el('tspan', { class: 'sle-arrival-late' })" in late and "' 지연'" in late
    assert re.search(r"\.sle-arrival-late \{ font-weight: 800; \}", CSS)
    assert ".sle-arrival { fill: var(--sle-text); text-anchor: middle;" in CSS


def test_a_group_date_rides_in_the_main_name_pill_and_resyncs_the_modules() -> None:
    """묶음 날짜 자리는 Main 설비명을 그릴 때 묶음마다 정하고(`S.arrivalModes`), 한 번이면 알약 둘째
    줄이다 — 가운데 이름 글자 상한은 두 줄 높이로 다시 맞추고(`ARRIVAL_PILL_TALL`) 날짜가 7px
    아래면 한 줄 알약 그대로다. 정한 뒤 묶음 모듈의 상자 날짜를 다시 맞춘다. 페이더로 묶음 모듈의
    칠이 바뀌면(`arrivalTurned`) Main 설비명을 다시 그린다. 위 알약이 두 줄이면 「필요 단축」
    배지가 그만큼 더 비킨다."""
    draw = _between("function drawGroupNames() {", "const GUIDE_PX = ")
    for part in (
        "modes.set(key, groupArrivalMode(placed, arrivalShown))",
        "modes.get(key)?.mode === 'once' ? modes.get(key).words : null",
        "UNIT_LABEL_MIN_PX, bare, ARRIVAL_PILL_TALL)",
        "(tall * ARRIVAL_FONT_K) / upp >= UNIT_LABEL_MIN_PX",
        "arrivalPill(cy, fs, fd, position === 'center' ? 'mid'",
        "el('text', { class: 'sle-arrival sle-group-arrival'",
        "S.arrivalModes = modes",
        "if (group) syncArrival(group, m)",
        "nameK = tag && tag.classList.contains('has-arrival') ? ts * ARRIVAL_PILL_TALL : ts",
    ):
        assert part in draw, part
    # 이름표가 서지 않는 묶음도 자리를 먼저 정한다(한 번 쓸 묶음이면 모듈 상자에도 쓰지 않는다).
    assert draw.index("modes.set(key,") < draw.index("if (!whole || !groupShown(mods)) continue")
    units = _between("function paintUnits(ids) {", "function paintAsOf(")
    assert "if (arrivalTurned || flipped.some(" in units
    assert "UNIT_LABEL_MIN_PX, bare)" in draw  # 한 줄 알약 크기 부름은 그대로(시험 글자)


def test_the_toggle_redraws_in_the_same_epoch_and_the_tip_names_the_date() -> None:
    """토글은 epoch 밖이다 — 같은 epoch 회차에 켬 · 끔이 바뀌면 묶음 자리를 다시 정하고 모든 호기의
    이름 · 날짜 줄을 다시 맞춘다. 같은 epoch 회차의 받은 값 견줌(`sameLook`)과 읽기(`unitLook`)도 두
    키를 본다. 반입 전 호기 풍선에는 반입 일정이 붙는다(A4 (가))."""
    assert "S.lastArrival !== undefined && S.lastArrival !== ARRIVAL_ON" in JS
    assert "S.lastArrival = ARRIVAL_ON" in JS
    look = _between("const unitLook = (raw) => ({", "const readUnit = ")
    assert (
        "arrivalPlan: dayOr(raw.arrivalPlan), arrivalDelayed: raw.arrivalDelayed === true" in look
    )
    same = _between("const sameLook = (o, n) =>", "function refreshUnits(")
    assert "(o.arrivalPlan || null) === (n.arrivalPlan || null)" in same
    words = _between("function unitWords(item) {", "const zoneColor")
    assert (
        "words.push('반입 전(실물 없음)', arrivalTipWords(item.arrivalPlan, item.arrivalDelayed))"
        in words
    )


# ---------------------------------------------------------------- 상자 토글 · payload(AppTest)


def _arrival_open(tmp_path: Path) -> AppTest:
    """C1 1F — 반입 전 낱 호기 LATE-01(지연), 같은 날 묶음 SAME(모듈 넷), 다른 날 묶음 DIFF(모듈
    둘), 2F 에 UP-01. EQ-01 · EQ-02 는 반입한 호기다(바탕 표본)."""
    later = {"Qual일정": "2099-12-01", "Qual상태": "계획"}
    same = {"Main 설비": "SAME", "Xsize": 6, "Ysize": 4, "반입일정": "2099-07-01", **later}
    diff = {"Main 설비": "DIFF", "Xsize": 6, "Ysize": 4, **later}
    master = _master(
        {"설비명": "LATE-01", "X좌표": 40.0, "반입일정": "2099-05-09", "반입상태": "지연", **later},
        {**same, "설비명": "SAME-A", "X좌표": 60.0, "Y좌표": 10.0},
        {**same, "설비명": "SAME-B", "X좌표": 66.0, "Y좌표": 10.0},
        {**same, "설비명": "SAME-C", "X좌표": 60.0, "Y좌표": 14.0},
        {**same, "설비명": "SAME-D", "X좌표": 66.0, "Y좌표": 14.0},
        {**diff, "설비명": "DIFF-A", "X좌표": 60.0, "Y좌표": 30.0, "반입일정": "2099-08-01"},
        {**diff, "설비명": "DIFF-B", "X좌표": 66.0, "Y좌표": 30.0, "반입일정": "2099-09-01"},
        {"설비명": "UP-01", "층": "2F"},
    )
    return _open(tmp_path, master)


def test_the_toggle_starts_off_and_only_adds_the_flag_outside_the_epoch(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """처음은 끔 — data 에 `arrivalDates` 가 없다. 호기마다 재료 두 키는 늘 실린다. 켜면 같은
    epoch 로 `arrivalDates` 만 더해진다(도면이 다시 서지 않는다)."""
    app = _arrival_open(tmp_path)
    toggle = app.sidebar.toggle(key=ARRIVAL_KEY)
    assert (toggle.label, toggle.value, toggle.disabled) == ("반입 일정", False, False)
    assert toggle.help == "층 도면의 반입 전 호기에 반입 일정을 씁니다."
    before = _viewer(calls)
    assert "arrivalDates" not in before
    by_id = {item["id"]: item for item in before["items"]}
    late = by_id["LATE-01"]
    assert (late["arrivalPlan"], late["arrivalDelayed"]) == ("2099-05-09", True)
    assert by_id["SAME-A"]["arrivalPlan"] == "2099-07-01"
    assert by_id["DIFF-B"]["arrivalPlan"] == "2099-09-01"
    assert all("arrivalPlan" in item and "arrivalDelayed" in item for item in before["items"])

    toggle.set_value(True).run()
    assert not app.exception, [item.message for item in app.exception]
    after = _viewer(calls)
    assert after["arrivalDates"] is True
    assert after["epoch"] == before["epoch"]
    assert after["items"] == before["items"]


def test_the_toggle_survives_floors_and_locks_while_editing_or_on_the_fab(
    tmp_path: Path, calls: list[dict[str, Any]]
) -> None:
    """켠 값은 층을 옮겨도 남는다. 층 배치 편집 중에는 끈 채 잠긴 짝(1-6 view), FAB 전체에서도 끈 채
    잠긴 짝(A5 (가) — 호기 상자가 없다)이 같은 자리에 서고, 편집을 끄거나 층으로 가면 켠 값이
    돌아온다. 편집기 data 에는 `arrivalDates` 가 없다."""
    app = _arrival_open(tmp_path)
    app.sidebar.toggle(key=ARRIVAL_KEY).set_value(True).run()

    app.selectbox(key="space_status_floor_jump_C1-1F").set_value("C1 2F").run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.sidebar.toggle(key=ARRIVAL_KEY).value is True
    assert _viewer(calls)["arrivalDates"] is True

    app.selectbox(key="space_status_floor_jump_C1-2F").set_value("C1 1F").run()
    app.toggle(key="space_layout_edit_mode").set_value(True).run()
    assert not app.exception, [item.message for item in app.exception]
    locked = app.sidebar.toggle(key=ARRIVAL_LOCKED_KEY)
    assert (locked.value, locked.disabled) == (False, True)
    assert locked.help == "배치 편집 중에는 쓰지 않습니다."
    assert not [item for item in app.sidebar.toggle if item.key == ARRIVAL_KEY]
    editor = [c for c in calls if c.get("scope") == "floor" and c.get("mode") != "view"][-1]
    assert "arrivalDates" not in editor

    app.toggle(key="space_layout_edit_mode").set_value(False).run()
    assert app.sidebar.toggle(key=ARRIVAL_KEY).value is True

    app.button(key="space_status_fab_breadcrumb").click().run()
    assert not app.exception, [item.message for item in app.exception]
    fab = app.sidebar.toggle(key=ARRIVAL_LOCKED_KEY)
    assert (fab.value, fab.disabled, fab.help) == (False, True, "층 도면에서 씁니다.")

    app.selectbox(key="space_status_floor_jump_fab").set_value("C1 1F").run()
    assert app.sidebar.toggle(key=ARRIVAL_KEY).value is True


def test_the_toggle_stands_right_under_the_compare_toggle() -> None:
    """상자 줄 차례 — 견주기 바로 아래(1-4 sidebar). 줄마다 위젯 하나라 간격이 견주기와 같다."""
    page = (Path(__file__).resolve().parents[1] / "app_pages" / "space_status.py").read_text(
        encoding="utf-8"
    )
    box = page[page.index("with space_box:") : page.index("save_row_reserved = ")]
    assert box.index("COMPARE_LABEL, key=COMPARE_KEY") < box.index("ARRIVAL_LABEL, key=ARRIVAL_KEY")
    assert 'persist_state="session", help=ARRIVAL_HELP' in box
