# Purpose: Space 「필요 단축」 배지 자리와 표시된 호기의 겹쳐 숨기기 면제를 node 로 검사한다.

"""명세 10-3 T-B5 — editor.js 의 `// <short-badge>` 구획(`badgeSpot`)과 `// <view-cover>`
구획(`coveredBy`)을 글자 그대로 떼어 node 로 돌린다(node·bun 이 없으면 건너뛰고 CI 에서는 실패 —
`test_space_module_group._node`).

- 배지는 그 호기의 보이는 모듈 상자 바깥 상자 위 가운데에 선다. 크기는 화면 px 로 정해 확대(화면 px
  당 데이터 단위 `upp`)에 따라 데이터 크기가 비례한다 — 화면에서는 같은 크기다.
- Main 설비 이름표가 「위」면 그 높이만큼 더 비킨다. 영역 위 끝을 넘으면 묶음 안쪽 위 띠로 뒤집는다.
- 「필요 단축」 에 표시된 호기(`layer`)는 반입 전이고 보이는 호기와 겹쳐도 숨지 않는다(같은 자리
  신규 호기의 배지가 빈 자리에 서지 않게).
"""

from __future__ import annotations

import re
from typing import Any

from test_space_module_group import _node

from capa_simulation.components import space_layout_editor

JS = (space_layout_editor._ASSETS / "editor.js").read_text(encoding="utf-8")
_BADGE = re.compile(r"// <short-badge>\n(?P<body>.*?)\n\s*// </short-badge>", re.S)
_COVER = re.compile(r"// <view-cover>\n(?P<body>.*?)\n\s*// </view-cover>", re.S)


def _block(pattern: re.Pattern[str]) -> str:
    match = pattern.search(JS)
    assert match, pattern.pattern
    return match.group("body")


def _constant(name: str) -> str:
    match = re.search(rf"\n  const {name} = ([0-9.]+)\n", JS)
    assert match, name
    return match.group(1)


_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const BADGE_MAIN_PX = %s
const BADGE_SUB_PX = %s
const BADGE_PAD_PX = %s
const BADGE_GAP_PX = %s
const GROUP_NAME_PX = %s
%s
const out = input.cases.map((c) => badgeSpot(c.rects, c.upp, c.above, c.em, c.canvasH))
process.stdout.write(JSON.stringify(out))
"""


def _spots(cases: list[dict[str, Any]]) -> list[dict[str, float]]:
    source = _RUNNER % (
        _constant("BADGE_MAIN_PX"),
        _constant("BADGE_SUB_PX"),
        _constant("BADGE_PAD_PX"),
        _constant("BADGE_GAP_PX"),
        _constant("GROUP_NAME_PX"),
        _block(_BADGE),
    )
    result: Any = _node(source, {"cases": cases})
    return list(result)


def test_a_badge_sits_centred_over_the_drawn_group_and_keeps_its_screen_size() -> None:
    group = [
        {"x": 10, "y": 10, "w": 4, "h": 3},
        {"x": 14, "y": 10, "w": 4, "h": 3},
        {"x": 10, "y": 13, "w": 4, "h": 3},
        {"x": 14, "y": 13, "w": 4, "h": 3},
    ]
    em = {"main": 2.4, "sub": 2.0}
    near, far, above, top_edge = _spots(
        [
            {"rects": group, "upp": 0.1, "above": False, "em": em, "canvasH": 100},
            {"rects": group, "upp": 0.05, "above": False, "em": em, "canvasH": 100},
            {"rects": group, "upp": 0.1, "above": True, "em": em, "canvasH": 100},
            {"rects": group, "upp": 0.1, "above": False, "em": em, "canvasH": 16.5},
        ]
    )
    # 묶음 바깥 상자(x 10~18, 위 끝 y 16) 위 가운데.
    assert near["x"] == 14
    assert near["y"] - near["h"] / 2 > 16
    # 화면 px 로 정한 크기 — 확대해 upp 가 반이면 데이터 크기도 반이다(화면에서는 같다).
    assert abs(far["w"] - near["w"] / 2) < 1e-9 and abs(far["h"] - near["h"] / 2) < 1e-9
    assert abs(far["mainSize"] - near["mainSize"] / 2) < 1e-9
    # Main 설비 이름표가 위면 그만큼 더 비킨다.
    assert above["y"] > near["y"]
    # 영역 위 끝을 넘으면 묶음 안쪽 위 띠로 뒤집는다.
    assert top_edge["y"] + top_edge["h"] / 2 <= 16.5
    assert top_edge["y"] < 16


_COVER_RUNNER = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
%s
const present = { visible: true, real: true }
const out = input.items.map((item) => coveredBy(item, { visible: true, real: false },
[input.neighbour],
  () => present))
process.stdout.write(JSON.stringify(out))
"""


def test_a_shortening_marked_unit_is_never_hidden_under_a_present_unit() -> None:
    source = _COVER_RUNNER % _block(_COVER)
    hidden: Any = _node(
        source,
        {
            "items": [{"id": "NEW"}, {"id": "NEW-L", "layer": "m"}],
            "neighbour": {"id": "OLD"},
        },
    )
    assert hidden == [True, False]
