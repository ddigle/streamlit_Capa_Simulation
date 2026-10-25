# Purpose: Space 층 상세 기준일 페이더의 눈금 글자 솎기와 좁은 창 칩 폭을 node·자산 글자로 검사한다.

"""390px 창에서 층 상세 기준일 페이더 트랙이 68px 로 줄어 분기 눈금 글자 8개 중 7쌍이 겹쳐
「26.0126.04…」 로 뭉개졌다(E2E 결함). editor.js 의 `// <fader-ticks>` 구획(`crowdedTicks`)을 글자
그대로 떼어 node 로 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`).

- 「오늘」 은 늘 선다. 나머지는 트랙 안에 들고 이미 선 글자와 틈 안으로 붙지 않을 때만 선다.
- 넓은 트랙(768·1400px 창)에서는 하나도 숨기지 않는다 — 날짜 거리로 이미 뺀 글자뿐이다.
- 좁은 창(기준일 줄 560px 아래)에서는 날짜 칩을 줄여 트랙에 자리를 준다(CSS 컨테이너 규칙).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from test_space_module_group import _node

from capa_simulation.components import space_layout_editor

ASSETS = space_layout_editor._ASSETS
JS = (ASSETS / "editor.js").read_text(encoding="utf-8")
CSS = (ASSETS / "editor.css").read_text(encoding="utf-8")
_TICKS = re.compile(r"// <fader-ticks>\n(?P<body>.*?)\n\s*// </fader-ticks>", re.S)

# 브라우저(Chrome, 10px 글꼴)에서 잰 글자 폭 — 「26.01」 꼴과 굵은 「오늘」(E2E 실측 25px·18px).
QUARTER_W = 25.0
TODAY_W = 18.0

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
const out = input.cases.map((c) => crowdedTicks(c.spots, c.width, c.gap))
process.stdout.write(JSON.stringify(out))
"""


def _block() -> str:
    match = _TICKS.search(JS)
    assert match, "editor.js 에 // <fader-ticks> 구획이 없습니다"
    return match.group("body")


def _thumb_px() -> float:
    match = re.search(r"\n  const THUMB_PX = ([0-9.]+)\n", JS)
    assert match
    return float(match.group(1))


def _gap_px() -> float:
    match = re.search(r"\n  const FADER_TICK_GAP_PX = ([0-9.]+)\n", JS)
    assert match, "눈금 글자 틈 상수가 없습니다"
    return float(match.group(1))


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    following = date(year + (month == 12), month % 12 + 1, 1)
    return date(year, month, min(day.day, (following - timedelta(days=1)).day))


def _spots(today: date, width: float) -> list[dict[str, Any]]:
    """`buildFader` 의 글자를 그 트랙 폭의 자리로.

    분기 「YY.MM」 은 오늘에서 40일·양 끝에서 20일 넘게 떨어진 것만, 그리고 「오늘」 이다.
    """
    low, high = _add_months(today, -12), _add_months(today, 12)
    span = max((high - low).days, 1)
    thumb = _thumb_px()

    def at(day: date) -> float:
        return thumb / 2 + (day - low).days / span * (width - thumb)

    spots: list[dict[str, Any]] = []
    month = _add_months(date(low.year, low.month, 1), 1)
    while month <= high:
        quarter = (month.month - 1) % 3 == 0
        if (
            quarter
            and abs((month - today).days) > 40
            and (month - low).days > 20
            and (high - month).days > 20
        ):
            spots.append(
                {"at": at(month), "w": QUARTER_W, "today": False, "text": f"{month:%y.%m}"}
            )
        month = _add_months(month, 1)
    spots.append({"at": at(today), "w": TODAY_W, "today": True, "text": "오늘"})
    return spots


def _hidden(cases: list[tuple[list[dict[str, Any]], float]]) -> list[list[bool]]:
    payload = {
        "cases": [{"spots": spots, "width": width, "gap": _gap_px()} for spots, width in cases]
    }
    result: Any = _node(_RUNNER % _block(), payload)
    return [list(map(bool, row)) for row in result]


def _shown(spots: list[dict[str, Any]], hidden: list[bool]) -> list[dict[str, Any]]:
    return [spot for spot, hide in zip(spots, hidden, strict=True) if not hide]


def _apart(a: dict[str, Any], b: dict[str, Any], gap: float) -> bool:
    return bool(
        a["at"] + a["w"] / 2 + gap <= b["at"] - b["w"] / 2
        or b["at"] + b["w"] / 2 + gap <= a["at"] - a["w"] / 2
    )


def test_a_narrow_track_keeps_today_and_no_two_labels_touch() -> None:
    """390px 창 — 예전 트랙 68px, 고친 뒤 146px(브라우저 실측).

    둘 다 서는 글자끼리 틈 안으로 붙지 않고 트랙 밖으로 나가지 않으며 「오늘」 은 선다. 146px
    에서는 분기 글자가 둘 넘게 남는다.
    """
    today = date(2026, 10, 26)
    old, new = _spots(today, 68.0), _spots(today, 146.0)
    assert len(old) == 8  # 26.01 · 26.04 · 26.07 · 27.01 · 27.04 · 27.07 · 27.10 · 오늘
    old_hidden, new_hidden = _hidden([(old, 68.0), (new, 146.0)])

    for spots, hidden, width in ((old, old_hidden, 68.0), (new, new_hidden, 146.0)):
        shown = _shown(spots, hidden)
        assert any(spot["today"] for spot in shown)
        for index, spot in enumerate(shown):
            assert spot["today"] or 0 <= spot["at"] - spot["w"] / 2
            assert spot["today"] or spot["at"] + spot["w"] / 2 <= width
            for other in shown[index + 1 :]:
                assert _apart(spot, other, _gap_px()), (spot["text"], other["text"])
    assert sum(not spot["today"] for spot in _shown(new, new_hidden)) >= 2


def test_wide_tracks_hide_nothing() -> None:
    """768·1400px 창(트랙 446·778px)에서는 어느 오늘이든 글자를 모두 그린다(두 해 사흘마다)."""
    cases = []
    today = date(2026, 1, 1)
    while today < date(2028, 1, 1):
        for width in (446.0, 778.0):
            cases.append((_spots(today, width), width))
        today += timedelta(days=3)
    for hidden in _hidden(cases):
        assert not any(hidden)


def test_today_stands_even_where_nothing_else_fits() -> None:
    """트랙이 글자 하나보다 좁아도 「오늘」 은 선다. 글자가 없으면 빈 목록이다."""
    spots = [
        {"at": 3.0, "w": QUARTER_W, "today": False},
        {"at": 10.0, "w": TODAY_W, "today": True},
        {"at": 17.0, "w": QUARTER_W, "today": False},
    ]
    assert _hidden([(spots, 20.0), ([], 100.0)]) == [[True, False, True], []]


def test_the_fader_thins_its_labels_whenever_it_draws_or_resizes() -> None:
    """솎기는 페이더를 그린 회차와 크기가 바뀔 때 다시 잰다.

    숨긴 글자는 자리를 지키고(visibility), 좁은 창에서는 날짜 칩이 줄어 트랙에 자리를 준다 — 칩
    폭은 거기서도 고정(글자 길이를 따르지 않음)이다.
    """
    assert "node.dataset.day = String(n)" in JS
    assert "    showFader()\n    fitFaderTicks()\n  }" in JS
    assert "    fitFabBar()\n    fitFaderTicks()\n  }" in JS
    assert ".sle-tick-label.is-crowded { visibility: hidden; }" in CSS
    assert ".sle-daterow { container: sle-daterow / inline-size; }" in CSS
    narrow = CSS[CSS.index("@container sle-daterow (width < 560px) {") :]
    narrow = narrow[: narrow.index("\n}")]
    chip = re.search(r"\.sle-fader-chip \{ width: ([0-9.]+)rem; \}", narrow)
    wide = re.search(r"\.sle-fader-chip \{[^}]*?width: ([0-9.]+)rem;", CSS)
    assert chip and wide
    assert float(chip.group(1)) < float(wide.group(1))
