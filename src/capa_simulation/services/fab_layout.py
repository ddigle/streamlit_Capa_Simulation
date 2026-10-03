# Purpose: S.PKG FAB 의 동·층 정의와 FAB 전체 도면 기본 배치(층 블록·꾸밈 요소)의 순수 함수를 둔다.

"""S.PKG FAB 전체 도면의 계약.

동·층 정의(`BUILDINGS`·`FLOORS`)가 원천이다. FAB 전체 도면은 층 도면과 같은 편집기의 보기 전용
(`scope="fab"`)으로 그리고, 그 위의 **층 블록**(`kind="block"`)이 연결된 층을 연다. 블록은 연결이
필수다 — S.PKG 가 아닌 자리는 연결 없는 블록이 아니라 색을 고른 영역과 글자로 그린다(누르지 않는
꾸밈). 블록 색은 상태(단계) 색이 아니라 사용자가 고르는 자리 구분 색이고, 기본(빈 값)은 Space 기본
면이다.

`default_fab_layout` 은 저장본이 없을 때의 기본 배치다. 그리기만 하고 어디에도 쓰지 않는다.
좌표 계약은 층 도면과 같다: 원점은 왼쪽 아래, 상자는 (x, y) → (x+w, y+h).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from capa_simulation.services.floor_layout_mark import MARK_COLOR_KEYS
from capa_simulation.services.floor_layout_profile import CANVAS_DECIMALS, CanvasSize, FloorKey


@dataclass(frozen=True)
class BuildingSpec:
    """FAB 전체 도면에서 동 하나의 자리(옛 FAB 그림 단위 — 기본 배치가 `FAB_SCALE` 배로 키운다)."""

    name: str
    x: float
    width: float
    height: float


@dataclass(frozen=True)
class FloorSpec:
    building: str
    floor: str


BUILDINGS: Final[tuple[BuildingSpec, ...]] = (
    BuildingSpec("C5", x=0.5, width=1.45, height=3.3),
    BuildingSpec("C1", x=3.1, width=1.55, height=4.0),
    BuildingSpec("C2", x=4.65, width=1.75, height=4.7),
    BuildingSpec("C3", x=6.40, width=1.50, height=4.1),
    BuildingSpec("C4", x=7.90, width=1.70, height=3.5),
)
FLOORS: Final[tuple[FloorSpec, ...]] = tuple(
    FloorSpec(building, floor)
    for building in ("C5", "C1", "C2", "C3", "C4")
    for floor in ("6F", "5F", "4F", "3F", "2F", "1F")
)


def floors_for(building: str) -> list[FloorSpec]:
    return [floor for floor in FLOORS if floor.building == building]


# 이름 순(C1 1F, C1 2F, …) 층 목록 — 층 목록 표·층 바로 가기·「다른 층으로 보내기」의 순서다.
FLOOR_KEYS: Final[tuple[FloorKey, ...]] = tuple(
    sorted((floor.building, floor.floor) for floor in FLOORS)
)

FAB_BLOCK_KIND: Final = "block"
FAB_MARK_KINDS: Final = ("zone", "text", FAB_BLOCK_KIND)
# 옛 FAB 그림 단위 → 도면 단위. 층 도면과 같은 격자(1)·정밀도(0.1)에서 읽히는 크기다.
FAB_SCALE: Final = 10.0
FAB_CANVAS: Final[CanvasSize] = (101.0, 62.0)
_BASE_Y: Final = 5.0
# 블록 사이 틈. 이웃 블록의 테두리가 겹치지 않아 올려 두면 그 블록 테두리만 강조된다.
_BLOCK_INSET: Final = 0.2
_NAME_GAP: Final = 0.5
_NAME_HEIGHT: Final = 3.5
_ZONE_PAD: Final = 1.5
_ZONE_TAG_ROOM: Final = 3.0
_ZONE_BOTTOM: Final = 2.0
_FLOOR_PARAM_SEPARATOR: Final = "-"


@dataclass(frozen=True)
class FabLayoutMark:
    """FAB 전체 도면 요소 하나. `link` 는 층 블록만 가진다(연결 필수). `color` 는 영역·블록의
    색 키다 — 블록의 빈 값은 Space 기본 면이다."""

    mark_id: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    label: str = ""
    color: str = ""
    link: FloorKey | None = None

    def editor_payload(self) -> dict[str, Any]:
        """편집기(브라우저)에 보내는 모양. 층 도면 요소와 같은 키에 `link`(「C1 1F」)를 더한다."""
        return {
            "id": self.mark_id,
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "rot": 0,
            "label": self.label,
            "color": self.color,
            "hatch": False,
            "keepOut": False,
            "link": floor_label(self.link) if self.link is not None else "",
        }


def floor_label(key: FloorKey) -> str:
    """화면·편집기에 쓰는 층 이름(「C1 1F」)."""
    return f"{key[0]} {key[1]}"


def floor_from_label(value: object) -> FloorKey | None:
    """「C1 1F」 → ("C1", "1F"). FAB 의 30개 층이 아니면 None."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(" ")
    if len(parts) != 2:
        return None
    key = (parts[0], parts[1])
    return key if key in FLOOR_KEYS else None


def floor_param(key: FloorKey) -> str:
    """주소 조회 인자 값(「C1-1F」). 띄어쓰기가 주소에서 `+` 로 바뀌지 않게 붙임표로 잇는다."""
    return f"{key[0]}{_FLOOR_PARAM_SEPARATOR}{key[1]}"


def floor_from_param(value: object) -> FloorKey | None:
    """「C1-1F」 → ("C1", "1F"). 잘못된 값은 None(호출하는 쪽이 조용히 FAB 로 둔다)."""
    if not isinstance(value, str):
        return None
    building, separator, floor = value.strip().partition(_FLOOR_PARAM_SEPARATOR)
    if not separator:
        return None
    key = (building, floor)
    return key if key in FLOOR_KEYS else None


def _scaled(value: float) -> float:
    return round(value * FAB_SCALE, CANVAS_DECIMALS)


def _rounded(value: float) -> float:
    return round(value, CANVAS_DECIMALS)


def _zone_around(mark_id: str, label: str, buildings: Sequence[BuildingSpec]) -> FabLayoutMark:
    left = min(_scaled(building.x) for building in buildings) - _ZONE_PAD
    right = max(_scaled(building.x + building.width) for building in buildings) + _ZONE_PAD
    top = (
        _BASE_Y
        + max(_scaled(building.height) for building in buildings)
        + _NAME_GAP
        + _NAME_HEIGHT
        + _ZONE_TAG_ROOM
    )
    return FabLayoutMark(
        mark_id=mark_id,
        kind="zone",
        x=_rounded(left),
        y=_ZONE_BOTTOM,
        w=_rounded(right - left),
        h=_rounded(top - _ZONE_BOTTOM),
        label=label,
        color=MARK_COLOR_KEYS[-1],
    )


def default_fab_layout() -> tuple[CanvasSize, tuple[FabLayoutMark, ...]]:
    """저장본이 없을 때의 FAB 전체 도면 — (캔버스, 요소).

    동 사각형(`BUILDINGS`)을 동마다 6F(위)→1F(아래) 여섯 층 블록으로 나눈다. C5 는 「독립동」 영역,
    C1~C4 는 맞붙은 「연결 구간」 영역에 들고, 동 이름은 블록 위 글자다. 영역·글자는 꾸밈이라 누르지
    않고, 누르면 열리는 것은 층 블록뿐이다. 그리는 순서는 영역 → 글자 → 블록(키보드 초점 순서가
    동마다 위층부터다)."""
    standalone = [building for building in BUILDINGS if building.name == "C5"]
    connected = [building for building in BUILDINGS if building.name != "C5"]
    marks: list[FabLayoutMark] = [
        _zone_around("Z-C5", "독립동", standalone),
        _zone_around("Z-LINK", "C1 · C2 · C3 · C4 연결 구간", connected),
    ]
    blocks: list[FabLayoutMark] = []
    for building in BUILDINGS:
        left = _scaled(building.x)
        width = _scaled(building.width)
        height = _scaled(building.height)
        marks.append(
            FabLayoutMark(
                mark_id=f"T-{building.name}",
                kind="text",
                x=left,
                y=_rounded(_BASE_Y + height + _NAME_GAP),
                w=width,
                h=_NAME_HEIGHT,
                label=building.name,
            )
        )
        floors = floors_for(building.name)
        count = len(floors)
        for index, spec in enumerate(floors):
            level = count - 1 - index
            bottom = _rounded(_BASE_Y + height * level / count)
            top = _rounded(_BASE_Y + height * (level + 1) / count)
            blocks.append(
                FabLayoutMark(
                    mark_id=f"B-{building.name}-{spec.floor}",
                    kind=FAB_BLOCK_KIND,
                    x=_rounded(left + _BLOCK_INSET),
                    y=_rounded(bottom + _BLOCK_INSET),
                    w=_rounded(width - _BLOCK_INSET * 2),
                    h=_rounded(top - bottom - _BLOCK_INSET * 2),
                    link=(building.name, spec.floor),
                )
            )
    return FAB_CANVAS, (*marks, *blocks)


def fab_layout_fingerprint(canvas: CanvasSize, marks: Sequence[FabLayoutMark]) -> str:
    """FAB 도면(캔버스·요소, 그리는 순서 포함)의 지문. 뷰어 epoch 에 쓴다 — 블록 대수는 넣지
    않는다."""
    payload = json.dumps(
        {"canvas": list(canvas), "marks": [mark.editor_payload() for mark in marks]},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
