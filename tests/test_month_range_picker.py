# Purpose: 조회기간 달 고르기의 판정 구획(node) · 조각 계약 · 트리거 검증을 고정한다.

"""조회기간 팝업의 달 고르기(`components/month_range_picker.py` — 2026-11-04 검수 의견 home-19).

월 입력 두 칸을 걷고 연도 넘김 · 열두 달 격자 · 빠른 선택으로 바꿨다. AppTest 는 Components v2 를
돌리지 못한다 — DOM 을 모르는 판정 구획(`// <month-range-core>`)은 node(없으면 bun)로 떼어 돌리고,
조각(HTML · CSS)은 글자로 붙잡는다. 브라우저 동작(누름 · 키보드 · 「적용」 한 트리거)은 사본 앱으로
본다.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest
from js_runner import run_js_json

import capa_simulation.components.month_range_picker as month_range_picker
from capa_simulation.components.month_range_picker import (
    MONTH_RANGE_CSS,
    MONTH_RANGE_HTML,
    MONTH_RANGE_JS,
    render_month_range_apply,
)


def _node(runner: str) -> Any:
    match = re.search(
        r"// <month-range-core>\n(?P<body>.*?)\n// </month-range-core>", MONTH_RANGE_JS, re.S
    )
    assert match, "month_range.js 에 // <month-range-core> 구획이 없습니다"
    return run_js_json(match.group("body") + "\n" + runner, what="달 고르기 JS 구획 시험")


def test_two_presses_close_a_range_in_either_order() -> None:
    """시작 달 → 끝 달 두 번 누름이 범위를 닫는다. 먼저 누른 달이 늦으면 둘을 바꿔 잇고, 같은 달 두
    번은 그 한 달."""
    out = _node(
        """
const first = pickMonth({ start: '2026-01', end: '2028-12', anchor: null }, '2026-03')
const forward = pickMonth(first, '2027-02')
const backward = pickMonth(pickMonth(forward, '2027-06'), '2026-11')
const single = pickMonth(pickMonth(forward, '2026-05'), '2026-05')
process.stdout.write(JSON.stringify({ first, forward, backward, single }))
"""
    )
    assert out["first"] == {"start": "2026-03", "end": "2026-03", "anchor": "2026-03"}
    assert out["forward"] == {"start": "2026-03", "end": "2027-02", "anchor": None}
    assert out["backward"] == {"start": "2026-11", "end": "2027-06", "anchor": None}
    assert out["single"] == {"start": "2026-05", "end": "2026-05", "anchor": None}


def test_the_band_previews_up_to_the_pointed_month_while_waiting() -> None:
    """끝 달을 기다리는 동안은 먼저 누른 달과 가리킨 달 사이를 미리 칠한다(앞쪽을 가리켜도)."""
    out = _node(
        """
const waiting = { start: '2026-06', end: '2026-06', anchor: '2026-06' }
process.stdout.write(JSON.stringify({
  ahead: shownRange(waiting, '2026-09'),
  behind: shownRange(waiting, '2026-02'),
  none: shownRange(waiting, null),
  done: shownRange({ start: '2026-01', end: '2026-12', anchor: null }, '2026-05'),
}))
"""
    )
    assert out["ahead"] == {"start": "2026-06", "end": "2026-09", "preview": True}
    assert out["behind"] == {"start": "2026-02", "end": "2026-06", "preview": True}
    assert out["none"] == {"start": "2026-06", "end": "2026-06", "preview": True}
    assert out["done"] == {"start": "2026-01", "end": "2026-12", "preview": False}


def test_quick_ranges_count_from_this_or_last_month_and_stop_at_the_bounds() -> None:
    """빠른 선택 — 이번 달부터 n개월 · 지난달부터 6개월 · 전체. 범위 끝에 걸리면 자르고, 남는 달이
    없으면 잠근다."""
    out = _node(
        """
const q = (kind, length, now, low = '2025-01', high = '2030-12') =>
  quickRange(kind, length, now, low, high)
process.stdout.write(JSON.stringify({
  six: q('this', 6, '2026-11'),
  twelve: q('this', 12, '2026-11'),
  last: q('last', 6, '2026-01'),
  all: q('all', undefined, '2026-11'),
  clipped: q('this', 24, '2030-01'),
  floor: q('last', 6, '2025-01'),
  gone: q('this', 6, '2031-03'),
  noToday: q('this', 6, null),
}))
"""
    )
    assert out["six"] == {"start": "2026-11", "end": "2027-04"}
    assert out["twelve"] == {"start": "2026-11", "end": "2027-10"}
    assert out["last"] == {"start": "2025-12", "end": "2026-05"}
    assert out["all"] == {"start": "2025-01", "end": "2030-12"}
    assert out["clipped"] == {"start": "2030-01", "end": "2030-12"}
    assert out["floor"] == {"start": "2025-01", "end": "2025-05"}
    assert out["gone"] is None
    assert out["noToday"] is None


def test_arrow_keys_move_by_month_quarter_and_year_within_the_bounds() -> None:
    """←→ 한 달 · ↑↓ 한 분기(격자 세 칸) · PageUp/PageDown 한 해 · Home/End 그 해 끝. 해를 넘고,
    범위 끝에서 멈춘다."""
    out = _node(
        """
const s = (month, key) => stepMonth(month, key, '2025-01', '2030-12')
process.stdout.write(JSON.stringify({
  left: s('2026-01', 'ArrowLeft'),
  right: s('2026-12', 'ArrowRight'),
  up: s('2026-02', 'ArrowUp'),
  down: s('2026-11', 'ArrowDown'),
  pageUp: s('2026-05', 'PageUp'),
  pageDown: s('2030-05', 'PageDown'),
  home: s('2026-08', 'Home'),
  end: s('2026-08', 'End'),
  floor: s('2025-01', 'ArrowLeft'),
  other: s('2026-08', 'Tab'),
}))
"""
    )
    assert out == {
        "left": "2025-12",
        "right": "2027-01",
        "up": "2025-11",
        "down": "2027-02",
        "pageUp": "2025-05",
        "pageDown": "2030-12",
        "home": "2026-01",
        "end": "2026-12",
        "floor": "2025-01",
        "other": None,
    }


def test_apply_is_ready_only_for_a_closed_range_that_differs_from_now() -> None:
    """「적용」 상태 — 끝 달을 기다리면 `pending`, 지금 기간 그대로면 `same`, 범위 밖이면 `invalid`,
    그 밖은 `ready`."""
    out = _node(
        """
const now = { start: '2026-01', end: '2028-12' }
const a = (draft) => applyState(draft, now, '2025-01', '2030-12')
process.stdout.write(JSON.stringify({
  pending: a({ start: '2026-03', end: '2026-03', anchor: '2026-03' }),
  same: a({ start: '2026-01', end: '2028-12', anchor: null }),
  ready: a({ start: '2026-01', end: '2027-12', anchor: null }),
  outside: a({ start: '2024-12', end: '2026-12', anchor: null }),
  reversed: a({ start: '2027-01', end: '2026-12', anchor: null }),
  years: [2024, 2025, 2030, 2031].map((year) => yearHasMonths(year, '2025-01', '2030-12')),
  span: monthSpan('2026-01', '2028-12'),
  label: shortMonth('2026-07'),
}))
"""
    )
    assert out["pending"] == "pending"
    assert out["same"] == "same"
    assert out["ready"] == "ready"
    assert out["outside"] == "invalid"
    assert out["reversed"] == "invalid"
    assert out["years"] == [False, True, True, False]
    assert out["span"] == 36
    assert out["label"] == "26.07"


def test_enter_again_where_the_range_was_chosen_applies_it() -> None:
    """키보드 Enter 가 「적용」 인 자리(2026-11-04 재검 b-3 — 전에는 셋째 Enter 가 범위를
    풀었다) — 적용할 수 있는(`ready`) 범위의 띠 시작 · 끝 칸(거꾸로 고르면 닫은 칸이 시작), 또는
    그 범위를 놓은 빠른 선택 칩. 띠 안 · 밖의 다른 칸, 다른 칩, 끝을 기다리는 중 · 지금 기간
    그대로면 늘 누름이다."""
    out = _node(
        """
const now = { start: '2026-01', end: '2028-12' }
const closed = { start: '2026-02', end: '2026-05', anchor: null }
const e = (draft, target) => enterApplies(draft, now, target, '2025-01', '2030-12')
const six = quickRange('this', 6, '2026-11', '2025-01', '2030-12')
const all = quickRange('all', null, '2026-11', '2025-01', '2030-12')
process.stdout.write(JSON.stringify({
  end: e(closed, { month: '2026-05' }),
  start: e(closed, { month: '2026-02' }),
  inside: e(closed, { month: '2026-03' }),
  outside: e(closed, { month: '2026-09' }),
  waiting: e({ start: '2026-02', end: '2026-02', anchor: '2026-02' }, { month: '2026-02' }),
  same: e({ ...now, anchor: null }, { month: '2028-12' }),
  chip: e({ ...six, anchor: null }, { range: six }),
  otherChip: e({ ...six, anchor: null }, { range: all }),
  lockedChip: e({ ...six, anchor: null }, { range: null }),
  nothing: e(closed, null),
}))
"""
    )
    assert out == {
        "end": True,
        "start": True,
        "inside": False,
        "outside": False,
        "waiting": False,
        "same": False,
        "chip": True,
        "otherChip": False,
        "lockedChip": False,
        "nothing": False,
    }


def test_the_enter_apply_runs_only_from_keydown_and_keeps_the_native_press() -> None:
    """Enter 적용은 키 누름 처리기 안에서만 돈다 — 마우스로 띠 끝 칸을 다시 누르면 그대로 새
    범위를 시작한다(click 길은 `enterApplies` 를 보지 않는다). 적용할 때만 기본 누름을
    막고(`preventDefault`), 누르고 있는 키의 되풀이 · 한글 조합 중 Enter 는 적용하지 않는다."""
    keydown = MONTH_RANGE_JS.split("root.onkeydown", 1)[1].split("root.onpointerover", 1)[0]
    click = MONTH_RANGE_JS.split("root.onclick", 1)[1].split("root.onkeydown", 1)[0]
    assert "enterApplies(" in keydown
    assert "enterApplies(" not in click
    assert "!event.repeat" in keydown
    assert "!event.isComposing" in keydown
    assert keydown.index("event.preventDefault()") < keydown.index("applyDraft()")


def test_the_picker_has_a_year_header_twelve_month_cells_quick_chips_and_one_apply() -> None:
    """조각 계약 — 월 입력 칸은 없고, 해 넘김 둘 · 달 칸 열둘(1 ~ 12월 차례) · 빠른 선택 다섯 ·
    「적용」 하나다. 머리 설명 글(고를 수 있는 범위 · 「적용」 을 눌러야 바뀜)은 조각에도
    없다(home-19)."""
    assert 'type="month"' not in MONTH_RANGE_HTML
    assert MONTH_RANGE_HTML.count('class="capa-month-step"') == 2
    months = re.findall(r'class="capa-month-cell" data-month="(\d+)">(\d+)월<', MONTH_RANGE_HTML)
    assert [(int(a), int(b)) for a, b in months] == [(m, m) for m in range(1, 13)]
    chips = re.findall(r'data-quick="(\w+)"(?: data-length="(\d+)")?', MONTH_RANGE_HTML)
    assert chips == [("this", "6"), ("this", "12"), ("this", "24"), ("last", "6"), ("all", "")]
    assert MONTH_RANGE_HTML.count('id="capa-month-apply"') == 1
    assert ">적용</button>" in MONTH_RANGE_HTML
    assert "고를 수 있는 범위" not in MONTH_RANGE_HTML
    assert "바뀝니다" not in MONTH_RANGE_HTML


def test_the_picker_colors_come_from_the_theme_variables() -> None:
    """색은 Streamlit 테마 변수(`--st-*`)와 그 섞음뿐이다 — 밝게 · 어둡게 테마를 따른다. 그림자 DOM
    으로 가두지 않으므로 규칙은 모두 `capa-month-*` 클래스 아래다(앱의 다른 요소에 새지 않는다)."""
    without_comments = re.sub(r"/\*.*?\*/", "", MONTH_RANGE_CSS, flags=re.S)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", without_comments)
    assert not re.search(r"\brgba?\(", without_comments)
    assert "url(" not in without_comments
    selectors = re.findall(r"([^{}]+)\{", without_comments)
    for selector in selectors:
        for part in selector.split(","):
            assert part.strip().startswith(".capa-month-"), part


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        (None, None),
        ({"start": "2026-02", "end": "2026-07"}, ("2026-02", "2026-07")),
        ({"start": "2026-07", "end": "2026-02"}, None),
        ({"start": "2024-12", "end": "2026-02"}, None),
        ({"start": "2026-2", "end": "2026-07"}, ("2026-02", "2026-07")),
        ({"start": "nope", "end": "2026-07"}, None),
        ("2026-02", None),
    ],
)
def test_only_a_valid_applied_range_comes_back(
    monkeypatch: pytest.MonkeyPatch, trigger: object, expected: tuple[str, str] | None
) -> None:
    """파이썬도 트리거를 다시 본다 — 범위 밖 · 거꾸로 · 깨진 값은 받지 않는다(JS 가 막아도)."""
    sent: list[dict[str, Any]] = []

    def component(**kwargs: Any) -> SimpleNamespace:
        sent.append(kwargs)
        return SimpleNamespace(apply=trigger)

    monkeypatch.setattr(month_range_picker, "_MONTH_RANGE_APPLY", component)
    result = render_month_range_apply(
        start="2026-01",
        end="2028-12",
        min_month="2025-01",
        max_month="2030-12",
        key="picker",
        this_month="2026-11",
    )
    assert result == expected
    assert sent[0]["data"] == {
        "start": "2026-01",
        "end": "2028-12",
        "minMonth": "2025-01",
        "maxMonth": "2030-12",
        "thisMonth": "2026-11",
    }


def test_the_shown_range_is_clamped_and_a_missing_this_month_is_sent_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    def component(**kwargs: Any) -> SimpleNamespace:
        sent.append(kwargs)
        return SimpleNamespace(apply=None)

    monkeypatch.setattr(month_range_picker, "_MONTH_RANGE_APPLY", component)
    render_month_range_apply(
        start="2020-01", end="2040-12", min_month="2025-01", max_month="2030-12", key="picker"
    )
    assert sent[0]["data"]["start"] == "2025-01"
    assert sent[0]["data"]["end"] == "2030-12"
    assert sent[0]["data"]["thisMonth"] is None
