# Purpose: Space FAB 층 블록 글자 줄 배치(단축 줄이 이름 크기를 끌어내리지 않음)를 node 로 본다.

"""editor.js 의 `// <block-text>` 구획(`blockTextLayout`)을 글자 그대로 떼어 node 로 돌린다
(node·bun 이 없으면 건너뛰고 CI 에서는 실패 — `test_space_module_group._node`).

색 기준 「필요 단축」 을 켜면 층 블록에 셋째 줄 「단축 5대 · 최대 −197일 · 추가 28」 이 붙는다.
예전에는 그 줄에 맞추느라 블록 글자 전체가 반으로 줄어 이 보기가 강조하려는 층 이름이 6~7px 이
됐다(E2E r1 — 개선 I69). 이제 위 줄(이름·대수)은 제 폭으로 맞추고 단축 줄만 따로 작아지거나 두
줄로 나뉜다.
"""

from __future__ import annotations

import re
from typing import Any

from test_space_module_group import _node

from capa_simulation.components import space_layout_editor

JS = (space_layout_editor._ASSETS / "editor.js").read_text(encoding="utf-8")
_BLOCK = re.compile(r"// <block-text>\n(?P<body>.*?)\n\s*// </block-text>", re.S)
_EM = re.compile(r"\n  (const emWidth = \(text\) => [^\n]+)\n")

_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
%s
const out = input.cases.map((c) => blockTextLayout(c.main, c.short, c.lw, c.lh, c.upp, emWidth))
process.stdout.write(JSON.stringify(out))
"""

HEAD = ["C1 3F", "배치 12대"]
SHORT = "단축 5대 · 최대 −197일 · 추가 28"


def _em(text: str) -> float:
    """editor.js `emWidth` 와 같은 어림 — 한글(U+1100 이상)은 1, 나머지는 0.6."""
    return sum(1.0 if ord(ch) >= 0x1100 else 0.6 for ch in text)


def _layout(cases: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    block = _BLOCK.search(JS)
    em = _EM.search(JS)
    assert block and em
    result: Any = _node(_RUNNER % (em.group(1), block.group("body")), {"cases": cases})
    return list(result)


def _case(lw: float, lh: float, *, short: str = SHORT, upp: float = 0.1) -> dict[str, Any]:
    return {"main": HEAD, "short": short, "lw": lw, "lh": lh, "upp": upp}


def test_the_short_line_no_longer_shrinks_the_floor_name() -> None:
    """위 줄은 제 폭으로 맞춘다 — 예전처럼 단축 줄 폭으로 정한 크기(반쯤)가 아니다."""
    lw, lh, upp = 18.0, 10.0, 0.1
    [rows] = _layout([_case(lw, lh, upp=upp)])

    head = [row for row in rows if row["role"] != "short"]
    short = [row for row in rows if row["role"] == "short"]
    assert [row["text"] for row in head] == HEAD
    assert short and "".join(row["text"] for row in short).replace(" · ", "") == SHORT.replace(
        " · ", ""
    )
    old = min(lh * 0.8 / (3 * 1.3), lw * 0.9 / _em(SHORT), 13 * upp)
    assert head[0]["size"] > old * 1.4
    assert all(row["size"] <= head[0]["size"] for row in short)
    assert all(row["size"] * _em(row["text"]) <= lw * 0.9 + 1e-9 for row in rows)


def test_a_long_short_line_splits_in_two_at_a_dot() -> None:
    """한 줄로는 위 줄의 0.75 배 아래로 줄면 「 · 」 경계에서 두 줄로 나눈다 — 넓은 쪽 폭이 가장
    좁아지는 자리. 두 줄은 같은 크기이고 한 줄일 때보다 크다."""
    lw, lh, upp = 14.0, 16.0, 0.1
    [rows] = _layout([_case(lw, lh, upp=upp)])

    short = [row for row in rows if row["role"] == "short"]
    texts = [row["text"] for row in short]
    assert len(texts) == 2 and " · ".join(texts) == SHORT
    assert max(_em(text) for text in texts) == min(
        max(_em(" · ".join(SHORT.split(" · ")[:k])), _em(" · ".join(SHORT.split(" · ")[k:])))
        for k in (1, 2)
    )
    assert len({row["size"] for row in short}) == 1
    assert short[0]["size"] > lw * 0.9 / _em(SHORT)


def test_a_low_block_keeps_the_name_size_instead_of_splitting_the_short_line() -> None:
    """낮은 블록에서 단축 줄을 두 줄로 나누면 줄 수 몫으로 이름이 작아진다 — 그때는 나누지 않고
    단축 줄만 한 줄로 작게 둔다."""
    lw, lh, upp = 13.0, 5.2, 0.1
    [rows] = _layout([_case(lw, lh, upp=upp)])

    short = [row for row in rows if row["role"] == "short"]
    assert [row["text"] for row in short] == [SHORT]
    assert abs(rows[0]["size"] - min(lh * 0.8 / (3 * 1.3), 1.3)) < 1e-9
    assert rows[0]["size"] > lw * 0.9 / _em(SHORT)


def test_a_tiny_block_keeps_only_the_name_and_a_too_small_short_line_drops_alone() -> None:
    """위 줄이 화면 7px 아래면 이름 줄만(예전 그대로). 단축 줄만 6px 아래면 그 줄만 뺀다."""
    tiny, cramped = _layout([_case(6.0, 2.0), _case(8.0, 9.0, short=SHORT + " · 지남 3")])

    assert [row["text"] for row in tiny] == ["C1 3F"]
    assert [row["role"] for row in cramped] in (["head", "sub"], ["head", "sub", "short"])
    assert all(row["size"] / 0.1 >= 6 for row in cramped if row["role"] == "short")


def test_no_short_line_is_the_old_two_line_block() -> None:
    [rows] = _layout([_case(18.0, 10.0, short="")])

    assert [(row["text"], row["role"]) for row in rows] == [("C1 3F", "head"), ("배치 12대", "sub")]
    expected = min(10.0 * 0.8 / (2 * 1.3), 18.0 * 0.9 / _em("배치 12대"), 1.3)
    assert abs(rows[0]["size"] - expected) < 1e-9
