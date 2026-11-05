# Purpose: 날짜 칸 · 기간 판의 판정 구획(node) · 조각 계약 · 값 칸 규칙과 앱의 한 꼴을 고정한다.

"""날짜 칸과 기간 판(`components/date_panel.py` — 2026-11-05 검수 static-35).

달 고르기(`tests/test_month_range_picker.py`)와 같은 꼴이다. AppTest 는 Components v2 를 돌리지
못한다 — DOM 을 모르는 판정 구획(`// <date-panel-core>`)은 node(없으면 bun)로 떼어 돌리고, 조각은
글자로 붙잡는다. 브라우저 동작(누름 · 키보드 · 「적용」 · 회차 0)은 사본 앱으로 본다.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import capa_simulation.components.date_panel as date_panel
from capa_simulation.components.date_panel import (
    DATE_PANEL_CSS,
    DATE_PANEL_HTML,
    DATE_PANEL_JS,
    DATE_PANEL_OWN_CSS,
    EMPTY_TEXT,
    accepted_range,
    panel_key,
)
from capa_simulation.components.month_range_picker import MONTH_RANGE_CSS

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _node(runner: str) -> Any:
    match = re.search(
        r"// <date-panel-core>\n(?P<body>.*?)\n// </date-panel-core>", DATE_PANEL_JS, re.S
    )
    assert match, "date_panel.js 에 // <date-panel-core> 구획이 없습니다"
    runtime = shutil.which("node") or shutil.which("bun")
    if runtime is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("CI 러너에 node 가 없다 — 기간 판 JS 구획 시험을 건너뛸 수 없다")
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


def test_two_presses_close_a_range_in_either_order() -> None:
    """시작 날 → 끝 날 두 번 누름이 범위를 닫는다. 먼저 누른 날이 늦으면 둘을 바꿔 잇고, 같은 날 두
    번은 그 하루. 한 날 칸은 한 번 누름이 그 날이다."""
    out = _node(
        """
const first = pickRange({ start: '2026-01-01', end: '2026-12-31', anchor: null }, '2026-03-05')
const forward = pickRange(first, '2026-04-02')
const backward = pickRange(pickRange(forward, '2026-06-10'), '2026-05-01')
const single = pickRange(pickRange(forward, '2026-05-07'), '2026-05-07')
const one = pickSingle('2026-02-03')
process.stdout.write(JSON.stringify({ first, forward, backward, single, one }))
"""
    )
    assert out["first"] == {"start": "2026-03-05", "end": "2026-03-05", "anchor": "2026-03-05"}
    assert out["forward"] == {"start": "2026-03-05", "end": "2026-04-02", "anchor": None}
    assert out["backward"] == {"start": "2026-05-01", "end": "2026-06-10", "anchor": None}
    assert out["single"] == {"start": "2026-05-07", "end": "2026-05-07", "anchor": None}
    assert out["one"] == {"start": "2026-02-03", "end": "2026-02-03", "anchor": None}


def test_the_band_previews_up_to_the_pointed_day_while_waiting() -> None:
    out = _node(
        """
const waiting = { start: '2026-06-10', end: '2026-06-10', anchor: '2026-06-10' }
process.stdout.write(JSON.stringify({
  ahead: shownRange(waiting, '2026-06-20'),
  behind: shownRange(waiting, '2026-06-02'),
  none: shownRange(waiting, null),
  done: shownRange({ start: '2026-01-01', end: '2026-12-31', anchor: null }, '2026-05-01'),
}))
"""
    )
    assert out["ahead"] == {"start": "2026-06-10", "end": "2026-06-20", "preview": True}
    assert out["behind"] == {"start": "2026-06-02", "end": "2026-06-10", "preview": True}
    assert out["none"] == {"start": "2026-06-10", "end": "2026-06-10", "preview": True}
    assert out["done"] == {"start": "2026-01-01", "end": "2026-12-31", "preview": False}


def test_the_month_grid_starts_on_sunday_and_keeps_six_rows() -> None:
    """2026-11-01 은 일요일, 2027-02-01 은 월요일이다. 그 달 밖 칸은 비고 칸은 늘 42개다(달을
    넘겨도 아래가 밀리지 않는다). 윤년 2월도 맞다. 없는 날은 날로 받지 않는다."""
    out = _node(
        """
const cells = (view) => monthCells(view)
const nov = viewOf('2026-11-15')
const feb = viewOf('2027-02-15')
const leap = viewOf('2028-02-15')
process.stdout.write(JSON.stringify({
  nov: cells(nov).slice(0, 2),
  novLength: cells(nov).length,
  novLast: cells(nov).filter(Boolean).pop(),
  febHead: cells(feb).slice(0, 3),
  febLength: cells(feb).length,
  leapLast: cells(leap).filter(Boolean).pop(),
  label: viewLabel(nov),
  badDay: dayIndex('2026-02-30'),
  badText: dayIndex('2026-2-3'),
  short: shortDay('2026-07-03'),
  span: daySpan('2026-01-30', '2026-02-02'),
  round: dayText(dayIndex('2026-12-31')),
}))
"""
    )
    assert out["nov"] == ["2026-11-01", "2026-11-02"]
    assert out["novLength"] == 42
    assert out["novLast"] == "2026-11-30"
    assert out["febHead"] == [None, "2027-02-01", "2027-02-02"]
    assert out["febLength"] == 42
    assert out["leapLast"] == "2028-02-29"
    assert out["label"] == "2026년 11월"
    assert out["badDay"] is None
    assert out["badText"] is None
    assert out["short"] == "26.07.03"
    assert out["span"] == 4
    assert out["round"] == "2026-12-31"


def test_quick_ranges_count_from_today_and_stop_at_the_bounds() -> None:
    """빠른 선택 — 오늘부터 · 오늘까지 n주, 이번 달, 전체, 비움. 범위 끝에 걸리면 자르고, 남는 날이
    없으면 잠근다."""
    out = _node(
        """
const q = (kind, length, today = '2026-11-05', low = '2026-01-01', high = '2027-03-31') =>
  quickRange(kind, length, today, low, high)
process.stdout.write(JSON.stringify({
  ahead4: q('ahead', 4),
  back4: q('back', 4),
  month: q('month'),
  all: q('all'),
  clear: q('clear'),
  clipped: q('ahead', 26),
  floor: q('back', 12, '2026-01-10'),
  gone: q('ahead', 4, '2028-01-01'),
  noToday: q('ahead', 4, ''),
  noLength: q('ahead', 0),
}))
"""
    )
    assert out["ahead4"] == {"start": "2026-11-05", "end": "2026-12-02"}
    assert out["back4"] == {"start": "2026-10-09", "end": "2026-11-05"}
    assert out["month"] == {"start": "2026-11-01", "end": "2026-11-30"}
    assert out["all"] == {"start": "2026-01-01", "end": "2027-03-31"}
    assert out["clear"] == {"start": None, "end": None}
    assert out["clipped"] == {"start": "2026-11-05", "end": "2027-03-31"}
    assert out["floor"] == {"start": "2026-01-01", "end": "2026-01-10"}
    assert out["gone"] is None
    assert out["noToday"] is None
    assert out["noLength"] is None


def test_quick_days_lock_outside_the_bounds() -> None:
    out = _node(
        """
const q = (kind, high = '2027-12-31') => quickDay(kind, '2026-11-05', '2026-01-01', high)
process.stdout.write(JSON.stringify({
  today: q('today'),
  yesterday: q('yesterday'),
  first: q('month_first'),
  next: q('next_month_first'),
  capped: q('next_month_first', '2026-11-30'),
  clear: q('clear'),
  unknown: q('nope'),
}))
"""
    )
    assert out["today"] == {"start": "2026-11-05", "end": "2026-11-05"}
    assert out["yesterday"] == {"start": "2026-11-04", "end": "2026-11-04"}
    assert out["first"] == {"start": "2026-11-01", "end": "2026-11-01"}
    assert out["next"] == {"start": "2026-12-01", "end": "2026-12-01"}
    assert out["capped"] is None
    assert out["clear"] == {"start": None, "end": None}
    assert out["unknown"] is None


def test_arrow_keys_move_by_day_week_month_and_year_within_the_bounds() -> None:
    """←→ 하루 · ↑↓ 한 주 · PageUp/PageDown 한 달 · Shift+PageUp/PageDown 한 해 · Home/End 그 달
    첫날 · 끝날. 그 달에 없는 날은 그 달 끝날로, 범위 끝에서는 멈춘다."""
    out = _node(
        """
const s = (day, key, shift = false) => stepDay(day, key, shift, '2025-01-01', '2030-12-31')
process.stdout.write(JSON.stringify({
  left: s('2026-11-01', 'ArrowLeft'),
  right: s('2026-11-30', 'ArrowRight'),
  up: s('2026-11-03', 'ArrowUp'),
  down: s('2026-11-28', 'ArrowDown'),
  pageUp: s('2026-03-31', 'PageUp'),
  pageDown: s('2026-01-31', 'PageDown'),
  yearUp: s('2028-02-29', 'PageUp', true),
  yearDown: s('2026-11-05', 'PageDown', true),
  home: s('2026-11-17', 'Home'),
  end: s('2026-11-17', 'End'),
  floor: s('2025-01-01', 'ArrowLeft'),
  ceiling: s('2030-12-20', 'PageDown'),
  other: s('2026-11-17', 'Tab'),
}))
"""
    )
    assert out == {
        "left": "2026-10-31",
        "right": "2026-12-01",
        "up": "2026-10-27",
        "down": "2026-12-05",
        "pageUp": "2026-02-28",
        "pageDown": "2026-02-28",
        "yearUp": "2027-02-28",
        "yearDown": "2027-11-05",
        "home": "2026-11-01",
        "end": "2026-11-30",
        "floor": "2025-01-01",
        "ceiling": "2030-12-31",
        "other": None,
    }


def test_apply_is_ready_only_for_a_closed_value_that_differs_from_now() -> None:
    """「적용」 상태 — 끝 날을 기다리면 `pending`, 지금 값 그대로면 `same`, 범위 밖 · 한쪽만 찬 값은
    `invalid`, 그 밖은 `ready`. 비움도 지금 값과 다르면 `ready` 다."""
    out = _node(
        """
const now = { start: '2026-01-01', end: '2026-12-31' }
const a = (draft, applied = now) => applyState(draft, applied, '2025-01-01', '2030-12-31')
process.stdout.write(JSON.stringify({
  pending: a({ start: '2026-03-01', end: '2026-03-01', anchor: '2026-03-01' }),
  same: a({ ...now, anchor: null }),
  ready: a({ start: '2026-01-01', end: '2026-06-30', anchor: null }),
  outside: a({ start: '2024-12-31', end: '2026-12-31', anchor: null }),
  reversed: a({ start: '2027-01-01', end: '2026-12-31', anchor: null }),
  half: a({ start: '2026-01-01', end: null, anchor: null }),
  cleared: a({ start: null, end: null, anchor: null }),
  stillEmpty: a({ start: null, end: null, anchor: null }, { start: null, end: null }),
  months: [
    viewHasDays(viewOf('2024-12-01'), '2025-01-01', '2030-12-31'),
    viewHasDays(viewOf('2025-01-01'), '2025-01-15', '2030-12-31'),
    viewHasDays(viewOf('2030-12-01'), '2025-01-01', '2030-12-01'),
    viewHasDays(viewOf('2031-01-01'), '2025-01-01', '2030-12-31'),
  ],
}))
"""
    )
    assert out["pending"] == "pending"
    assert out["same"] == "same"
    assert out["ready"] == "ready"
    assert out["outside"] == "invalid"
    assert out["reversed"] == "invalid"
    assert out["half"] == "invalid"
    assert out["cleared"] == "ready"
    assert out["stillEmpty"] == "same"
    assert out["months"] == [False, True, True, False]


def test_enter_again_where_the_value_was_chosen_applies_it() -> None:
    """조회기간 판과 같다 — 띠의 시작 · 끝 칸이나 그 값을 놓은 빠른 선택 칩에서 Enter 를 한 번 더
    누르면 「적용」 이고, 다른 칸 · 다른 칩 · 끝을 기다리는 중 · 지금 값 그대로면 늘 누름이다."""
    out = _node(
        """
const now = { start: '2026-01-01', end: '2026-12-31' }
const closed = { start: '2026-02-01', end: '2026-02-20', anchor: null }
const e = (draft, target) => enterApplies(draft, now, target, '2025-01-01', '2030-12-31')
const month = quickRange('month', null, '2026-11-05', '2025-01-01', '2030-12-31')
const all = quickRange('all', null, '2026-11-05', '2025-01-01', '2030-12-31')
process.stdout.write(JSON.stringify({
  end: e(closed, { day: '2026-02-20' }),
  start: e(closed, { day: '2026-02-01' }),
  inside: e(closed, { day: '2026-02-10' }),
  outside: e(closed, { day: '2026-09-10' }),
  waiting: e({ ...closed, end: '2026-02-01', anchor: '2026-02-01' }, { day: '2026-02-01' }),
  same: e({ ...now, anchor: null }, { day: '2026-12-31' }),
  chip: e({ ...month, anchor: null }, { range: month }),
  otherChip: e({ ...month, anchor: null }, { range: all }),
  lockedChip: e({ ...month, anchor: null }, { range: null }),
  clearChip: e({ start: null, end: null, anchor: null }, { range: { start: null, end: null } }),
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
        "clearChip": True,
        "nothing": False,
    }


def test_the_value_text_reads_like_the_sidebar_field() -> None:
    out = _node(
        """
process.stdout.write(JSON.stringify({
  range: valueText('range', '2026-11-02', '2027-03-31'),
  single: valueText('single', '2026-11-02', '2026-11-02'),
  empty: valueText('range', null, null),
  half: valueText('range', '2026-11-02', null),
}))
"""
    )
    assert out == {
        "range": "26.11.02 → 27.03.31",
        "single": "26.11.02",
        "empty": "",
        "half": "26.11.02 → —",
    }


def test_the_enter_apply_runs_only_from_keydown_and_keeps_the_native_press() -> None:
    """Enter 적용은 키 누름 처리기 안에서만 돈다 — 마우스로 띠 끝 칸을 다시 누르면 새 범위를
    시작한다. 누르고 있는 키의 되풀이 · 한글 조합 중 Enter 는 적용하지 않는다."""
    keydown = DATE_PANEL_JS.split("root.onkeydown", 1)[1].split("grid.onpointerover", 1)[0]
    click = DATE_PANEL_JS.split("root.onclick", 1)[1].split("root.onkeydown", 1)[0]
    assert "enterApplies(" in keydown
    assert "enterApplies(" not in click
    assert "!event.repeat" in keydown
    assert "!event.isComposing" in keydown
    assert keydown.index("event.preventDefault()") < keydown.index("applyDraft()")


def test_only_the_apply_goes_to_the_server() -> None:
    """고르는 동안은 회차 0 이다 — JS 가 서버로 보내는 길은 「적용」 트리거 하나다(UI-PRF-01 ·
    UI-PRF-04)."""
    assert DATE_PANEL_JS.count("setTriggerValue(") == 1
    assert "setTriggerValue('apply'" in DATE_PANEL_JS
    assert "setStateValue" not in DATE_PANEL_JS


def test_the_panel_has_month_steps_weekdays_quick_chips_and_one_apply() -> None:
    """조각 계약 — 값 칸 하나 · 달 · 해 넘김 넷 · 요일 일곱 · 빠른 선택 · 「적용」 하나. 조회기간
    판의 해 넘김 · 칩 · 바닥 줄과 같은 부품 이름을 쓰고, 날짜 입력 칸과 설명 글은 없다."""
    assert 'type="date"' not in DATE_PANEL_HTML
    assert DATE_PANEL_HTML.count('class="capa-date-field"') == 1
    steps = re.findall(r'class="capa-date-step" data-step="(-?\d+)"', DATE_PANEL_HTML)
    assert steps == ["-12", "-1", "1", "12"]
    assert re.findall(r"<span>(.)</span>", DATE_PANEL_HTML) == list("일월화수목금토")
    chips = re.findall(r'data-quick="(\w+)"(?: data-length="(\d+)")?', DATE_PANEL_HTML)
    assert chips == [
        ("ahead", "4"),
        ("ahead", "12"),
        ("ahead", "26"),
        ("back", "4"),
        ("back", "12"),
        ("month", ""),
        ("all", ""),
        ("clear", ""),
        ("today", ""),
        ("yesterday", ""),
        ("month_first", ""),
        ("next_month_first", ""),
        ("clear", ""),
    ]
    assert DATE_PANEL_HTML.count('class="capa-date-apply"') == 1
    assert ">적용</button>" in DATE_PANEL_HTML
    assert "<dialog" in DATE_PANEL_HTML
    assert "바뀝니다" not in DATE_PANEL_HTML


def test_the_panel_keeps_the_period_panel_look_and_theme_colors() -> None:
    """해 넘김 · 칩 · 바닥 줄 서식은 조회기간 판 서식을 이름만 옮겨 쓴다 — 한쪽만 고쳐 갈라지지
    않는다. 색은 테마 변수와 그 섞음뿐이고, 규칙은 모두 `capa-date-*` 아래다. DOM 이름은 조회기간
    판과 겹치지 않는다(판을 찾는 화면 확인 스크립트가 같은 화면의 날짜 칸을 집지 않게)."""
    assert DATE_PANEL_CSS.startswith(MONTH_RANGE_CSS.replace("capa-month-", "capa-date-"))
    assert "capa-month-" not in DATE_PANEL_CSS
    assert "capa-month-" not in DATE_PANEL_HTML
    assert "capa-month-" not in DATE_PANEL_JS
    without_comments = re.sub(r"/\*.*?\*/", "", DATE_PANEL_OWN_CSS, flags=re.S)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", without_comments)
    assert not re.search(r"\brgba?\(", without_comments)
    assert "url(" not in without_comments
    for selector in re.findall(r"([^{}]+)\{", without_comments):
        for part in selector.split(","):
            assert part.strip().startswith(".capa-date-"), part


D1, D2 = date(2026, 2, 1), date(2026, 7, 31)
LOW, HIGH = date(2026, 1, 1), date(2028, 12, 31)


@pytest.mark.parametrize(
    ("payload", "clearable", "expected"),
    [
        (None, False, None),
        ({"start": "2026-02-01", "end": "2026-07-31"}, False, (D1, D2)),
        ({"start": "2026-07-31", "end": "2026-02-01"}, False, None),
        ({"start": "2025-12-31", "end": "2026-02-01"}, False, None),
        ({"start": "2026-02-01", "end": "2029-01-01"}, False, None),
        ({"start": "2026-02-30", "end": "2026-07-31"}, False, None),
        ({"start": "nope", "end": "2026-07-31"}, False, None),
        ({"start": None, "end": None}, False, None),
        ({"start": None, "end": None}, True, (None, None)),
        ({"start": "2026-02-01", "end": None}, True, None),
        ("2026-02-01", False, None),
    ],
)
def test_only_a_valid_applied_value_comes_back(
    payload: object, clearable: bool, expected: object
) -> None:
    """파이썬도 트리거를 다시 본다 — 범위 밖 · 거꾸로 · 깨진 값은 받지 않는다(JS 가 막아도)."""
    assert accepted_range(payload, LOW, HIGH, clearable=clearable) == expected


class _FakeSession(dict[str, Any]):
    """`st.session_state` 대역 — 콜백 판정은 세션 칸만 본다."""


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    state = _FakeSession()
    monkeypatch.setattr(st, "session_state", state)
    return state


def _last_call(calls: list[dict[str, Any]]) -> dict[str, Any]:
    return calls[-1]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    def component(**kwargs: Any) -> SimpleNamespace:
        seen.append(kwargs)
        return SimpleNamespace(apply=None)

    monkeypatch.setattr(date_panel, "_DATE_PANEL", component)
    return seen


def test_a_range_field_seeds_clamps_and_settles_the_two_keys(
    session: _FakeSession, calls: list[dict[str, Any]]
) -> None:
    """빈 칸은 기본값을, 범위 밖은 끝으로, 거꾸로면 끝을 시작에 맞춰 세션 칸에 되적는다 — 값의
    정본은 세션 칸이고 보낸 data 와 돌려준 값이 그와 같다."""
    assert date_panel.date_range_field(
        "조회일", start_key="s", end_key="e", default=(D1, D2), min_date=LOW, max_date=HIGH
    ) == (D1, D2)
    assert session["s"] == D1 and session["e"] == D2
    sent = _last_call(calls)
    assert sent["key"] == panel_key("s")
    assert sent["data"]["mode"] == "range"
    assert sent["data"]["bounded"] is True
    assert sent["data"]["clearable"] is False
    assert (sent["data"]["minDay"], sent["data"]["maxDay"]) == (LOW.isoformat(), HIGH.isoformat())

    session["s"] = date(2020, 1, 1)
    session["e"] = date(2040, 1, 1)
    assert date_panel.date_range_field(
        "조회일", start_key="s", end_key="e", default=(D1, D2), min_date=LOW, max_date=HIGH
    ) == (LOW, HIGH)
    assert session["s"] == LOW and session["e"] == HIGH

    session["s"] = D2
    session["e"] = D1
    assert date_panel.date_range_field("조회일", start_key="s", end_key="e", default=(D1, D2)) == (
        D2,
        D2,
    )


def test_a_free_field_never_moves_the_value_outside_ten_years(
    session: _FakeSession, calls: list[dict[str, Any]]
) -> None:
    """끝을 주지 않은 칸은 오늘 앞뒤 십 년이고, 값이 그 밖이면 값까지 넓힌다 — 말없이 바꾸지
    않는다. 「전체」 는 양 끝을 준 칸에만 있다."""
    far = date(1990, 5, 5)
    session["s"] = far
    session["e"] = date.today()
    start, end = date_panel.date_range_field("조회일", start_key="s", end_key="e", default=(D1, D2))
    assert (start, end) == (far, date.today())
    data = _last_call(calls)["data"]
    assert data["minDay"] == far.isoformat()
    assert data["bounded"] is False
    assert date.fromisoformat(data["maxDay"]) >= date.today() + timedelta(days=3000)


def test_a_datetime_value_reads_as_its_day(
    session: _FakeSession, calls: list[dict[str, Any]]
) -> None:
    session["k"] = datetime(2026, 3, 4, 5, 6)
    assert date_panel.date_field("기준일", key="k", default=D1) == date(2026, 3, 4)
    assert session["k"] == date(2026, 3, 4)
    data = _last_call(calls)["data"]
    assert data["mode"] == "single"
    assert data["start"] == data["end"] == "2026-03-04"
    assert data["disabled"] is False


def test_optional_fields_stay_empty_and_offer_the_clear_chip(
    session: _FakeSession, calls: list[dict[str, Any]]
) -> None:
    """비운 칸은 기본값으로 채우지 않는다 — 세션 칸은 `None` 이고 값 칸 글은 `emptyText` 다."""
    assert date_panel.optional_date_range_field("상세", start_key="s", end_key="e") == (None, None)
    assert session["s"] is None and session["e"] is None
    data = _last_call(calls)["data"]
    assert data["clearable"] is True
    assert data["start"] is None and data["end"] is None
    assert data["emptyText"] == EMPTY_TEXT

    assert date_panel.optional_date_field("오늘", key="k", empty_text="없음") is None
    assert session["k"] is None
    assert _last_call(calls)["data"]["emptyText"] == "없음"


def _press_apply(
    session: _FakeSession, calls: list[dict[str, Any]], payload: dict[str, object]
) -> None:
    """누름 흉내 — 트리거 값을 위젯 칸에 넣고 받은 콜백을 부른다(`on_apply_change`)."""
    sent = _last_call(calls)
    session[sent["key"]] = SimpleNamespace(apply=payload)
    sent["on_apply_change"]()


def test_the_apply_callback_writes_the_session_keys_before_the_run_reads_them(
    session: _FakeSession, calls: list[dict[str, Any]]
) -> None:
    date_panel.date_range_field(
        "조회일", start_key="s", end_key="e", default=(D1, D2), min_date=LOW, max_date=HIGH
    )
    _press_apply(session, calls, {"start": "2026-03-01", "end": "2026-03-31"})
    assert session["s"] == date(2026, 3, 1)
    assert session["e"] == date(2026, 3, 31)

    # 범위 밖 트리거는 칸을 바꾸지 않는다.
    _press_apply(session, calls, {"start": "2030-01-01", "end": "2030-01-02"})
    assert session["s"] == date(2026, 3, 1)

    date_panel.optional_date_field("오늘", key="k")
    _press_apply(session, calls, {"start": "2026-04-05", "end": "2026-04-05"})
    assert session["k"] == date(2026, 4, 5)
    _press_apply(session, calls, {"start": None, "end": None})
    assert session["k"] is None


def test_a_field_draws_in_apptest_through_the_stub(
    date_panels: dict[str, dict[str, Any]],
) -> None:
    """페이지에서 쓰는 꼴 그대로 — 대역이 받은 값이 세션 칸과 같다."""

    def script() -> None:
        from datetime import date

        from capa_simulation.components.date_panel import date_range_field

        date_range_field(
            "조회일",
            start_key="start",
            end_key="end",
            default=(date(2026, 1, 1), date(2026, 3, 31)),
            width=240,
        )

    app = AppTest.from_function(script).run()
    assert not app.exception
    assert app.session_state["start"] == date(2026, 1, 1)
    assert date_panels[panel_key("start")]["end"] == "2026-03-31"


def _date_input_calls() -> list[str]:
    roots = [PROJECT_ROOT / "app.py", PROJECT_ROOT / "app_pages", PROJECT_ROOT / "src"]
    found: list[str] = []
    for root in roots:
        for path in [root] if root.is_file() else root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "date_input"
                ):
                    found.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}")
    return found


def test_the_app_has_no_native_date_input() -> None:
    """앱의 날짜 고르기는 값 칸 + 기간 판 한 꼴이다(UI-INP-03 · UI-CON-03) — 브라우저 기본 날짜
    칸을 다시 두면 실패한다. 편집 표 칸 안 날짜(`DateColumn`)는 표의 일이라 밖이다."""
    assert _date_input_calls() == []
