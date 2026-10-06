# Purpose: S.PKG FAB 의 동·층 정의와 FAB 전체 도면(기본 배치·층 블록·꾸밈 요소)의 계약·검증을 둔다.

"""S.PKG FAB 전체 도면의 계약.

동·층 정의(`BUILDINGS`·`FLOORS`)가 원천이다. FAB 전체 도면은 층 도면과 같은 편집기(`scope="fab"`)로
그리고, 그 위의 **층 블록**(`kind="block"`)이 연결된 층을 연다. 블록은 연결이 필수다 — S.PKG 가 아닌
자리는 연결 없는 블록이 아니라 색을 고른 영역과 글자로 그린다(누르지 않는 꾸밈). 블록 색은
상태(단계) 색이 아니라 사용자가 고르는 자리 구분 색이고, 기본(빈 값)은 Space 기본 면이다.

`default_fab_layout` 은 저장본이 없을 때의 기본 배치다. 그리기만 하고 어디에도 쓰지 않는다 — FAB
편집의 시작점이고, 처음 저장할 때 편집한 전체가 저장된다. 저장된 FAB 는 설비 DB 의
`fab_layout_profile` (캔버스·배경 도면 한 행)과 `fab_layout_mark`(요소)이고 설비 리비전과 무관한
현행값이다. **요소 행이 하나도 없으면 기본 배치의 요소를 그린다**(캔버스는 저장된 행, 없으면
`FAB_CANVAS`) — 배경 도면만 먼저 올려도 블록이 사라지지 않는다. 그래서 요소를 모두 지워 저장하면
기본 배치로 돌아간다.

좌표 계약은 층 도면과 같다: 원점은 왼쪽 아래, 상자는 (x, y) → (x+w, y+h), 회전은 상자 가운데를
축으로 90° 단위다. 저장 경로의 검증이라 잘못된 항목을 조용히 버리지 않는다(전체 교체라 버리면
지워진다).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from capa_simulation.services.floor_layout_mark import (
    MARK_COLOR_KEYS,
    MARKS_PER_FLOOR_MAX,
    mark_box,
    mark_flag,
    mark_font_color,
    mark_font_size,
    mark_id_of,
    mark_label,
    mark_rotation,
    marks_extent,
    zone_color,
)
from capa_simulation.services.floor_layout_profile import (
    CANVAS_DECIMALS,
    CanvasSize,
    FloorKey,
    normalize_canvas_size,
    rounded_to_canvas,
)


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
# FAB 편집기가 넣는 종류 — 영역·글자·동선(꾸밈)과 층 블록. 반입구·문·기둥은 층 도면 요소라 없다.
FAB_MARK_KINDS: Final = ("zone", "text", "arrow", FAB_BLOCK_KIND)
FAB_MARK_NAMES: Final[Mapping[str, str]] = {
    "zone": "영역",
    "text": "글자",
    "arrow": "동선",
    FAB_BLOCK_KIND: "층 블록",
}
# FAB 저장 행의 키(`fab_layout_profile.layout_key`). 한 행뿐이다.
FAB_LAYOUT_KEY: Final = "FAB"
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
    색 키다 — 블록의 빈 값은 Space 기본 면이다. 상태(단계) 색이 아니라 자리 구분 색이다."""

    mark_id: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    label: str = ""
    color: str = ""
    link: FloorKey | None = None
    rotation: int = 0
    hatch: bool = False
    # 이름표·블록 글자의 크기(None 은 자동)와 색 키(빈 값은 기본). 층 요소와 같은 계약이다.
    font_size: int | None = None
    font_color: str = ""

    def editor_payload(self) -> dict[str, Any]:
        """편집기(브라우저)에 보내는 모양. 층 도면 요소와 같은 키에 `link`(「C1 1F」)를 더한다.
        FAB 에는 설비가 없어 「설비 금지」(`keepOut`)는 늘 거짓이다."""
        return {
            "id": self.mark_id,
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "rot": self.rotation,
            "label": self.label,
            "color": self.color,
            "hatch": self.hatch,
            "keepOut": False,
            "link": floor_label(self.link) if self.link is not None else "",
            "fontSize": self.font_size,
            "fontColor": self.font_color,
        }


@dataclass(frozen=True)
class FabLayoutProfile:
    """저장된 FAB 캔버스와 배경 도면(data URI). 층의 `FloorLayoutProfile` 과 같은 몫이다."""

    canvas_width: float
    canvas_height: float
    image_data_uri: str | None
    image_name: str | None
    image_byte_count: int
    updated_at: datetime

    @property
    def canvas_size(self) -> CanvasSize:
        return self.canvas_width, self.canvas_height


# FAB 편집을 시작할 때 본 저장값: (저장된 캔버스 — 행이 없으면 None, 저장된 요소의 지문). 층의
# `FloorLayoutBase` 와 같은 꼴이다. 저장이 쓰기 잠금 안에서 이것과 지금 저장값을 견준다.
FabLayoutBase = tuple[CanvasSize | None, str]


@dataclass(frozen=True)
class FabLayoutApply:
    """FAB 편집기의 `적용` 한 번. 바꾼 것만 든다(안 바꾼 쪽은 None)."""

    canvas: CanvasSize | None
    marks: tuple[FabLayoutMark, ...] | None


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
        x=rounded_to_canvas(left),
        y=_ZONE_BOTTOM,
        w=rounded_to_canvas(right - left),
        h=rounded_to_canvas(top - _ZONE_BOTTOM),
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
                y=rounded_to_canvas(_BASE_Y + height + _NAME_GAP),
                w=width,
                h=_NAME_HEIGHT,
                label=building.name,
            )
        )
        floors = floors_for(building.name)
        count = len(floors)
        for index, spec in enumerate(floors):
            level = count - 1 - index
            bottom = rounded_to_canvas(_BASE_Y + height * level / count)
            top = rounded_to_canvas(_BASE_Y + height * (level + 1) / count)
            blocks.append(
                FabLayoutMark(
                    mark_id=f"B-{building.name}-{spec.floor}",
                    kind=FAB_BLOCK_KIND,
                    x=rounded_to_canvas(left + _BLOCK_INSET),
                    y=rounded_to_canvas(bottom + _BLOCK_INSET),
                    w=rounded_to_canvas(width - _BLOCK_INSET * 2),
                    h=rounded_to_canvas(top - bottom - _BLOCK_INSET * 2),
                    link=(building.name, spec.floor),
                )
            )
    return FAB_CANVAS, (*marks, *blocks)


def effective_fab_layout(
    profile: FabLayoutProfile | None, marks: Sequence[FabLayoutMark]
) -> tuple[CanvasSize, tuple[FabLayoutMark, ...]]:
    """저장값으로 그릴 FAB — 캔버스는 저장된 행(없으면 `FAB_CANVAS`), 요소는 저장된 요소(하나도
    없으면 기본 배치의 요소)."""
    canvas = profile.canvas_size if profile is not None else FAB_CANVAS
    return canvas, tuple(marks) if marks else default_fab_layout()[1]


def require_fab_layout_fits(canvas: CanvasSize, marks: Sequence[FabLayoutMark]) -> None:
    """`marks` 로 **그릴** FAB 요소가 `canvas` 안인가. 요소가 하나도 없으면 기본 배치를 그리므로
    그 기본 배치를 잰다 — 빈 목록도 작은 캔버스에서는 거부된다."""
    drawn = tuple(marks) if marks else default_fab_layout()[1]
    width, height = canvas
    right, top = marks_extent(drawn)
    if right > width + 1e-9 or top > height + 1e-9:
        hint = (
            " 요소를 모두 지우면 기본 배치를 그리므로 기본 배치가 들어갈 만큼 넓어야 합니다."
            if not marks
            else ""
        )
        raise ValueError(
            f"FAB 캔버스 {width:g} × {height:g} 밖에 도면 요소가 있습니다(필요한 크기 "
            f"{right:g} × {top:g}). FAB 배치 편집에서 요소를 옮기거나 캔버스를 넓히세요.{hint}"
        )


def prepare_fab_layout_marks(
    marks: Sequence[Mapping[str, Any]], canvas: CanvasSize
) -> tuple[FabLayoutMark, ...]:
    """FAB 요소 목록을 검증·정규화한다. 하나라도 어긋나면 `ValueError`(전체 교체라 버리지 않는다).

    받는 키는 편집기 계약(층 요소와 같고 `link` 를 더한다). 종류는 `FAB_MARK_KINDS`, 개수는 층과
    같은 상한이다. **층 블록은 연결(「C1 1F」, FAB 의 30개 층)이 필수**이고 색은 기본(빈 값) 또는
    `MARK_COLOR_KEYS` 다. 영역 색은 층 도면과 같다(비면 회색). 블록이 아닌 요소의 연결은 버린다.
    글자 크기·색(`fontSize`·`fontColor`)은 층 요소와 같은 규칙으로 모든 종류가 갖는다.
    두 블록이 같은 층을 가리키는 것은 막지 않는다(`duplicate_block_links` 로 경고만)."""
    if len(marks) > MARKS_PER_FLOOR_MAX:
        raise ValueError(f"FAB 도면 요소는 {MARKS_PER_FLOOR_MAX}개까지입니다: {len(marks)}개")
    prepared: list[FabLayoutMark] = []
    seen: set[str] = set()
    for raw in marks:
        mark_id = mark_id_of(raw, seen)
        kind = str(raw.get("kind", ""))
        if kind not in FAB_MARK_KINDS:
            raise ValueError(f"FAB 도면 요소 {mark_id} 의 종류를 알 수 없습니다: {kind!r}")
        x, y, w, h = mark_box(raw, mark_id, FAB_MARK_NAMES[kind], canvas)
        link: FloorKey | None = None
        color = ""
        if kind == FAB_BLOCK_KIND:
            link = _block_link(raw, mark_id)
            color = str(raw.get("color") or "")
            if color and color not in MARK_COLOR_KEYS:
                raise ValueError(f"층 블록 {mark_id} 의 색을 알 수 없습니다: {color!r}")
        elif kind == "zone":
            color = zone_color(raw, mark_id)
        prepared.append(
            FabLayoutMark(
                mark_id=mark_id,
                kind=kind,
                x=x,
                y=y,
                w=w,
                h=h,
                label=mark_label(raw, mark_id),
                color=color,
                link=link,
                rotation=mark_rotation(raw, mark_id),
                hatch=kind == "zone" and mark_flag(raw.get("hatch")),
                font_size=mark_font_size(raw, mark_id),
                font_color=mark_font_color(raw, mark_id),
            )
        )
    return tuple(prepared)


def _block_link(raw: Mapping[str, Any], mark_id: str) -> FloorKey:
    raw_link = raw.get("link")
    link = floor_from_label(raw_link)
    if link is not None:
        return link
    shown = str(raw_link or "").strip()
    problem = f"FAB 의 층이 아닙니다: {shown!r}" if shown else "없습니다"
    raise ValueError(
        f"층 블록 {mark_id} 의 연결 층이 {problem}. 층 블록은 연결이 필수입니다 — S.PKG 가 아닌 "
        "자리는 영역과 글자로 그리세요."
    )


def duplicate_block_links(marks: Sequence[FabLayoutMark]) -> list[str]:
    """둘 이상의 층 블록이 가리키는 층(「C1 1F」). 막지 않고 경고만 한다."""
    counts: dict[FloorKey, int] = {}
    for mark in marks:
        if mark.kind == FAB_BLOCK_KIND and mark.link is not None:
            counts[mark.link] = counts.get(mark.link, 0) + 1
    return [floor_label(key) for key in sorted(counts) if counts[key] > 1]


def parse_fab_editor_apply(payload: Mapping[str, Any], canvas: CanvasSize) -> FabLayoutApply:
    """FAB 편집기의 적용값(`canvas`·`marks`)을 검증한다. FAB 에는 호기가 없어 `changes` 가 오면
    거부한다. `canvas` 는 지금 편집 영역(적용 전)이다 — 요소는 새 영역(바꿨으면) 안이어야 한다."""
    if payload.get("changes"):
        raise ValueError("FAB 전체 도면에는 호기가 없습니다.")
    raw_canvas = payload.get("canvas")
    new_canvas: CanvasSize | None = None
    if isinstance(raw_canvas, Mapping):
        new_canvas = normalize_canvas_size(raw_canvas.get("width"), raw_canvas.get("height"))  # type: ignore[arg-type]
    elif raw_canvas is not None:
        raise ValueError("편집 영역 값을 읽지 못했습니다.")
    raw_marks = payload.get("marks")
    marks: tuple[FabLayoutMark, ...] | None = None
    if isinstance(raw_marks, list) and all(isinstance(raw, Mapping) for raw in raw_marks):
        marks = prepare_fab_layout_marks(raw_marks, new_canvas or canvas)
    elif raw_marks is not None:
        raise ValueError("FAB 도면 요소 값을 읽지 못했습니다.")
    return FabLayoutApply(canvas=new_canvas, marks=marks)


def fab_marks_fingerprint(marks: Sequence[FabLayoutMark]) -> str:
    """FAB 요소 목록의 지문(그리는 순서 포함). 편집을 시작할 때 본 저장값과 저장 직전의 저장값을
    견줘, 다른 사람이 먼저 바꾼 FAB 를 옛 목록으로 통째로 덮지 않게 한다."""
    payload = json.dumps(
        [mark.editor_payload() for mark in marks], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fab_layout_fingerprint(canvas: CanvasSize, marks: Sequence[FabLayoutMark]) -> str:
    """FAB 도면(캔버스·요소, 그리는 순서 포함)의 지문. 뷰어 epoch 에 쓴다 — 블록 대수는 넣지
    않는다."""
    payload = json.dumps(
        {"canvas": list(canvas), "marks": [mark.editor_payload() for mark in marks]},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
