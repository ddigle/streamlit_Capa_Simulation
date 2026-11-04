# Purpose: Space 층 도면의 비설비 도면 요소와 Main 설비명 위치의 계약·검증을 정의한다.

"""Space 층 도면의 비설비 도면 요소.

호기가 아닌 것 — 반입구(셔터)·여닫이문·영역·기둥·글자·동선 화살표·베이 화살표(U자)·도형(사각형·원·
ㄴ자 박스 등 프리셋) — 을 층마다 따로 둔다. 설비 마스터의 행이 아니고 설비 리비전과도 무관한
**현행값**이다(`floor_layout_profile` 의 캔버스와 같은 성격). 좌표 계약은 호기와 같다: 원점은 왼쪽
아래, 상자는 (x, y) → (x+w, y+h) 이고 회전은 상자 가운데를 축으로 90° 단위다(회전한 뒤의 축 정렬
상자를 저장한다).

저장 경로의 검증이라 **잘못된 항목을 조용히 버리지 않는다.** 층 단위 전체 교체라서 하나를
버리면 그 요소가 지워진다 — 그래서 하나라도 어긋나면 `ValueError` 로 저장을 거부한다.

같은 층 현행값으로 **Main 설비 모듈 묶음 이름표의 위치**(`GROUP_LABEL_POSITIONS` — 묶음 범위
가운데·위·아래, 2026-10-23 사용자 요청)도 여기 둔다. 설비 마스터 칸이 아니고, 행이 없는 묶음은
묶음 모양의 처음 위치(`space_layout_edit.default_group_label` — 한 줄 묶음은 위, 그 밖은
가운데)로 선다. 층 저장의 동시성 대조는 요소와 위치를 함께 본다(`floor_layout_fingerprint`).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from capa_simulation.services.floor_layout_profile import CANVAS_DECIMALS, CanvasSize
from capa_simulation.services.korean_particle import subject_particle, with_object_particle

MARK_KINDS: Final = ("zone", "shutter", "door", "column", "text", "arrow", "bay", "shape")
MARK_NAMES: Final[Mapping[str, str]] = {
    "zone": "영역",
    "shutter": "반입구",
    "door": "문",
    "column": "기둥",
    "text": "글자",
    "arrow": "동선",
    "bay": "베이",
    "shape": "도형",
}
# 호기가 덮으면 경고하는 요소(겹침처럼 저장은 막지 않는다). 영역은 「설비 금지」를 켠 것만. 도형은
# 꾸밈이라 들지 않는다(겹침 경고·「설비 금지」 없음).
BLOCKING_MARK_KINDS: Final = ("shutter", "door", "column")
MARK_ROTATIONS: Final = (0, 90, 180, 270)
# 영역 색 이름. 실제 색은 그리는 쪽이 테마 토큰(제품별 비중과 같은 검증된 범주 팔레트)에서 고른다.
MARK_COLOR_KEYS: Final = ("blue", "rose", "green", "violet", "sky", "gray")
MARK_LABEL_MAX: Final = 40
# 베이 화살표(U자) 가운데 글의 번호 칸 길이. 그릴 때 앞에 늘 「B」 를 붙이고 번호만
# 저장한다(`bay_label`).
BAY_LABEL_MAX: Final = 10
# 베이 번호 앞에서 떼는 머리 — B·b 와 그 뒤 빈칸이 거듭된 것 전부(편집기 `bayNumber` 와 같은 규칙).
_BAY_PREFIX: Final = re.compile(r"^(?:[Bb]\s*)+")
# 이름표 글자의 기준 크기. 빈 값(None)은 「자동」 — 글자 요소는 상자에 맞추고 나머지는 11 이다. 기준
# 크기는 도면 1칸이 화면 8px 일 때의 화면 px 이고, 확대·축소를 따라 0~2배로 바뀌며 화면 6px 아래면
# 숨는다(편집기 `// <text-scale>`, 2026-11-03 사용자 요청). 층·FAB 요소가 함께 쓴다.
MARK_FONT_SIZES: Final = (9, 11, 13, 16, 20, 24)
# 영역 테두리 모양(점선·실선)과 이름표 정렬(왼쪽·가운데·오른쪽). 첫 값이 처음 값이자 옛 행(빈
# 칸)의 값이다 — 지금 모습(점선 테두리, 왼쪽 위 꼬리표). 영역이 아닌 요소는 늘 처음 값이다.
# 층·FAB 요소가 함께 쓴다.
ZONE_BORDER_STYLES: Final = ("dashed", "solid")
ZONE_LABEL_ALIGNS: Final = ("left", "center", "right")
MARKS_PER_FLOOR_MAX: Final = 500
# Main 설비 모듈 묶음 이름표 위치 — 묶음 범위 정가운데, 범위 바깥 바로 위·아래. 고른 적이 없는
# 묶음은 모양에 따라 가운데(두 줄 이상) 또는 위(한 줄 — 모듈 2·3)다(`default_group_label`).
GROUP_LABEL_POSITIONS: Final = ("center", "top", "bottom")
_MARK_ID: Final = re.compile(r"[A-Za-z0-9_-]{1,40}")

# 요소 모양 값(`look` — 정규 JSON 글 한 칸, 설비 `0033` `look_json`, 2026-11-03 사용자 요청).
# 종류마다 받는 키가 다르고 처음 값인 키는 넣지 않는다(다 처음 값이면 빈 글 — 옛 행과 같다).
# - 화살표 머리 크기 `head`: 「너비·길이」 두 글자, 각 S·M·L(엑셀 머리 크기 3×3). MM 이 지금
#   동선 그림이다.
# - 선 색 `line`: accent(강조색)·ink(도면 글자색)·영역 색 키 여섯. 굵기 `lineWidth`(화면 px),
#   모양 `lineStyle`. 동선의 처음 값은 지금 모습(강조색 · 상자 높이를 따르는 굵기 · 점선)이라
#   굵기 처음 값이 없다(「자동」).
# - 뒤집기 `flip`: 좌우 거울(베이) — 상하 뒤집기는 180° 돌림 + 좌우 뒤집기와 같은 값이다.
HEAD_SIZES: Final = ("S", "M", "L")
ARROW_HEADS: Final = tuple(width + length for width in HEAD_SIZES for length in HEAD_SIZES)
LINE_COLOR_KEYS: Final = ("accent", "ink", *MARK_COLOR_KEYS)
LINE_WIDTHS: Final = (0.75, 1, 1.5, 2, 3, 4.5, 6)
LINE_STYLES: Final = ("solid", "dashed", "dotted")
# 도형(`shape`, 2026-11-03 사용자 요청 — 엑셀 도형처럼) — 한 종류에 프리셋 키 `look.shape` 를
# 둔다(「도형 바꾸기」 가 키 하나 바꾸기다). 꾸밈이라 막는 요소가 아니고 호기 아래 층에 그린다.
# 층·FAB 둘 다다.
# - 모양 조절 값 `look.adj`: 프리셋마다 0~2개(아래 (하한, 상한, 처음 값) — 0.01 단위의 비율,
#   노란 손잡이·선택 칸 숫자로 바꾼다). 처음 값과 모두 같으면 넣지 않는다. 무엇의 비율인가는
#   `SHAPE_ADJUST_BASE` 다 — 두께·둥글기·머리 길이는 엑셀처럼 짧은 변(min(폭, 높이)) 기준이고
#   (2026-11-04 Space 결정 보드 답 — 한쪽 팔만 늘이면 두께는 그대로, 손잡이·칸으로 크기를 바꾸면
#   편집기가 그린 두께를 지키게 값을 다시 셈한다), 삼각형 꼭짓점 자리만 폭, 블록 화살표 몸통
#   두께만 높이 기준이다. `min-w`·`min-h` 값은 상한이 그 축 길이까지라(엑셀처럼 — 넓은 ㄴ자의
#   굵은 세로 팔) 저장 상한이 상한 × `SHAPE_STRETCH_MAX` 이고, 편집기가 그릴 때 상자로 묶는다.
# - 채우기 색은 요소의 `color`(영역 색 키 여섯 + `ink` 진하게 + `surface` 바탕 — 모두 테마
#   토큰, 처음 `blue`), 투명도는 `look.fillAlpha`(채우기 불투명 0~100 — 5 단위, 처음 20, 0 은
#   채우기 없음).
# - 선 `look.line`(`auto` 채우기 색을 따름 · `none` 선 없음 · `ink` · 영역 색 키 여섯)·굵기
#   `lineWidth`(화면 px, 처음 1.5)·모양 `lineStyle`(처음 실선), 좌우 뒤집기 `flip`. 빗금은
#   영역처럼 `hatch` 다.
SHAPE_PRESETS: Final = (
    "rect",
    "ellipse",
    "lbox",
    "cbox",
    "frame",
    "triangle",
    "diamond",
    "cross",
    "arrowblock",
)
SHAPE_NAMES: Final[Mapping[str, str]] = {
    "rect": "사각형",
    "ellipse": "원",
    "lbox": "ㄴ자 박스",
    "cbox": "ㄷ자 박스",
    "frame": "테",
    "triangle": "삼각형",
    "diamond": "마름모",
    "cross": "십자",
    "arrowblock": "블록 화살표",
}
SHAPE_ADJUST: Final[Mapping[str, tuple[tuple[float, float, float], ...]]] = {
    "rect": ((0, 1, 0),),
    "ellipse": (),
    "lbox": ((0.05, 0.95, 0.35), (0.05, 0.95, 0.35)),
    "cbox": ((0.05, 0.95, 0.3), (0.05, 0.49, 0.3)),
    "frame": ((0.02, 0.49, 0.12),),
    "triangle": ((0, 1, 0.5),),
    "diamond": (),
    "cross": ((0.05, 0.95, 0.34),),
    "arrowblock": ((0.05, 1, 0.5), (0.05, 0.95, 0.7)),
}
# 모양 조절 값마다 무엇의 비율인가(편집기 `SHAPE_PRESETS[…].base`). `min` 짧은 변(상한 그대로) ·
# `min-w`·`min-h` 짧은 변이되 상한은 그 축(폭·높이) 길이까지 · `w` 폭 · `h` 높이.
SHAPE_ADJUST_BASE: Final[Mapping[str, tuple[str, ...]]] = {
    "rect": ("min",),
    "ellipse": (),
    "lbox": ("min-w", "min-h"),
    "cbox": ("min-w", "min-h"),
    "frame": ("min",),
    "triangle": ("w",),
    "diamond": (),
    "cross": ("min",),
    "arrowblock": ("h", "min-w"),
}
# `min-w`·`min-h` 값의 저장 상한 배수 — 긴 변이 짧은 변의 100배인 상자의 축 길이까지 받는다.
SHAPE_STRETCH_MAX: Final = 100
SHAPE_FILL_KEYS: Final = (*MARK_COLOR_KEYS, "ink", "surface")
SHAPE_LINE_KEYS: Final = ("auto", "none", "ink", *MARK_COLOR_KEYS)
FILL_ALPHA_STEP: Final = 5
# 종류마다 받는 키와 그 처음 값. 처음 값이 없는 키(동선 굵기)는 고른 값이면 늘 남는다. 도형의 모양
# 조절 값(`adj`)은 처음 값이 프리셋마다 달라 `SHAPE_ADJUST` 가 맡는다.
LOOK_KEYS: Final[Mapping[str, tuple[str, ...]]] = {
    "arrow": ("head", "line", "lineWidth", "lineStyle"),
    "bay": ("head", "line", "lineWidth", "lineStyle", "flip"),
    "shape": ("shape", "adj", "fillAlpha", "line", "lineWidth", "lineStyle", "flip"),
}
LOOK_DEFAULTS: Final[Mapping[str, Mapping[str, object]]] = {
    "arrow": {"head": "MM", "line": "accent", "lineStyle": "dashed"},
    "bay": {"head": "MM", "line": "ink", "lineWidth": 2, "lineStyle": "solid", "flip": False},
    "shape": {
        "shape": "rect",
        "fillAlpha": 20,
        "line": "auto",
        "lineWidth": 1.5,
        "lineStyle": "solid",
        "flip": False,
    },
}


@dataclass(frozen=True)
class FloorLayoutMark:
    """층 도면 요소 하나. `rotation` 은 0·90·180·270, 상자는 회전한 뒤의 축 정렬 상자다."""

    mark_id: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    rotation: int
    label: str
    color: str
    hatch: bool
    keep_out: bool
    # 이름표 글자 크기(`MARK_FONT_SIZES`, None 은 자동)와 색 키(`MARK_COLOR_KEYS`, 빈 값은 기본
    # 글자색). 기본값이 있어야 캐시에 실린 옛 모양(`**payload`)도 다시 만들어진다.
    font_size: int | None = None
    font_color: str = ""
    # 영역의 테두리 모양·이름표 정렬(`ZONE_BORDER_STYLES`·`ZONE_LABEL_ALIGNS`). 영역이 아니면
    # 처음 값이다.
    border_style: str = ZONE_BORDER_STYLES[0]
    label_align: str = ZONE_LABEL_ALIGNS[0]
    # 요소 모양 값(정규 JSON 글 — `mark_look`). 빈 글은 모두 처음 값이다(옛 행). 글이라 얼린
    # dataclass 의 해시·같음이 그대로 산다.
    look: str = ""

    @property
    def blocks(self) -> bool:
        """호기가 덮으면 경고할 요소인가 — 반입구·문·기둥, 「설비 금지」 영역."""
        return self.kind in BLOCKING_MARK_KINDS or (self.kind == "zone" and self.keep_out)

    @property
    def name(self) -> str:
        """화면 이름: 이름표가 있으면 그것, 없으면 종류 이름."""
        return self.label or MARK_NAMES[self.kind]

    def editor_payload(self) -> dict[str, Any]:
        """편집기(브라우저)에 보내는 모양. 키 이름은 편집기 JS 계약이다. 모양 값(`look`)은 처음 값이
        아닌 것이 있을 때만 싣는다 — 없는 요소의 모양·지문(`marks_fingerprint`)이 0033 전과 같다."""
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
            "keepOut": self.keep_out,
            "fontSize": self.font_size,
            "fontColor": self.font_color,
            "borderStyle": self.border_style,
            "labelAlign": self.label_align,
            **look_payload(self.look),
        }


class MarkBox(Protocol):
    """좌표·크기만 보는 쪽(`marks_extent`)이 받는 모양. 층 요소와 FAB 요소가 함께 맞는다."""

    @property
    def x(self) -> float: ...

    @property
    def y(self) -> float: ...

    @property
    def w(self) -> float: ...

    @property
    def h(self) -> float: ...


def _number(value: object, field: str, mark_id: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"도면 요소 {mark_id} 의 {field} 값이 비었습니다.")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"도면 요소 {mark_id} 의 {field} 값은 숫자여야 합니다.") from exc
    if not math.isfinite(number):
        raise ValueError(f"도면 요소 {mark_id} 의 {field} 값은 숫자여야 합니다.")
    return round(number, CANVAS_DECIMALS)


def mark_flag(value: object) -> bool:
    """`True`·「Y」·「TRUE」 만 참이다(브라우저·CSV 어느 쪽에서 와도)."""
    return value is True or (isinstance(value, str) and value.strip().upper() in ("Y", "TRUE"))


def mark_id_of(raw: Mapping[str, Any], seen: set[str]) -> str:
    """요소 id 를 검사하고 `seen` 에 더한다. 형식이 틀리거나 겹치면 `ValueError`."""
    mark_id = str(raw.get("id", "")).strip()
    if not _MARK_ID.fullmatch(mark_id):
        raise ValueError(f"도면 요소 id 는 영문·숫자·_·- 1~40자여야 합니다: {mark_id!r}")
    if mark_id in seen:
        raise ValueError(f"도면 요소 id 가 겹칩니다: {mark_id}")
    seen.add(mark_id)
    return mark_id


def mark_box(
    raw: Mapping[str, Any], mark_id: str, name: str, canvas: CanvasSize
) -> tuple[float, float, float, float]:
    """(x, y, w, h) 를 소수 첫째 자리로 맞추고 캔버스 안인지 본다. 어긋나면 `ValueError`."""
    x, y = _number(raw.get("x"), "X", mark_id), _number(raw.get("y"), "Y", mark_id)
    w, h = _number(raw.get("w"), "폭", mark_id), _number(raw.get("h"), "높이", mark_id)
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        raise ValueError(f"도면 요소 {mark_id} 의 좌표는 0 이상, 크기는 0 보다 커야 합니다.")
    width, height = canvas
    if x + w > width + 1e-9 or y + h > height + 1e-9:
        raise ValueError(
            f"도면 요소 {mark_id}({name}){subject_particle(mark_id)} 캔버스 {width:g} × "
            f"{with_object_particle(f'{height:g}')} 벗어났습니다."
        )
    return x, y, w, h


def mark_rotation(raw: Mapping[str, Any], mark_id: str) -> int:
    """회전(0·90·180·270). 아니면 `ValueError`."""
    rotation_value = raw.get("rot", 0)
    rotation = int(rotation_value) if isinstance(rotation_value, (int, float)) else -1
    if rotation not in MARK_ROTATIONS:
        raise ValueError(f"도면 요소 {mark_id} 의 회전은 0·90·180·270 중 하나여야 합니다.")
    return rotation


def mark_label(raw: Mapping[str, Any], mark_id: str) -> str:
    """이름표(앞뒤 공백을 떼고 `MARK_LABEL_MAX` 자까지)."""
    label = str(raw.get("label") or "").strip()
    if len(label) > MARK_LABEL_MAX:
        raise ValueError(f"도면 요소 {mark_id} 의 이름은 {MARK_LABEL_MAX}자까지입니다.")
    return label


def mark_font_size(raw: Mapping[str, Any], mark_id: str) -> int | None:
    """이름표 글자 크기. 비었거나 「자동」이면 None, `MARK_FONT_SIZES` 밖이면 `ValueError`."""
    value = raw.get("fontSize")
    if value is None or (isinstance(value, str) and value.strip() in ("", "자동", "auto")):
        return None
    size: float | None = None
    if not isinstance(value, bool):
        try:
            size = float(value)
        except (TypeError, ValueError):
            size = None
    if size is None or not size.is_integer() or int(size) not in MARK_FONT_SIZES:
        allowed = "·".join(str(size) for size in MARK_FONT_SIZES)
        raise ValueError(
            f"도면 요소 {mark_id} 의 글자 크기는 자동 또는 {allowed} 중 하나여야 합니다: {value!r}"
        )
    return int(size)


def mark_font_color(raw: Mapping[str, Any], mark_id: str) -> str:
    """이름표 글자 색 키. 비면 기본 글자색(빈 값)이고 `MARK_COLOR_KEYS` 밖이면 `ValueError`."""
    color = str(raw.get("fontColor") or "").strip()
    if color and color not in MARK_COLOR_KEYS:
        raise ValueError(f"도면 요소 {mark_id} 의 글자 색을 알 수 없습니다: {color!r}")
    return color


def _zone_choice(
    raw: Mapping[str, Any], key: str, allowed: Sequence[str], mark_id: str, what: str
) -> str:
    value = raw.get(key)
    text = value.strip() if isinstance(value, str) else value
    if text is None or text == "":
        return allowed[0]
    if not isinstance(text, str) or text not in allowed:
        raise ValueError(
            f"영역 {mark_id} 의 {with_object_particle(what)} 알 수 없습니다: {value!r} — "
            f"{'·'.join(allowed)} 중 하나입니다."
        )
    return text


def zone_border_style(raw: Mapping[str, Any], mark_id: str) -> str:
    """영역 테두리 모양(`borderStyle`). 비면 점선(처음 값)이고 `ZONE_BORDER_STYLES` 밖이면
    `ValueError`."""
    return _zone_choice(raw, "borderStyle", ZONE_BORDER_STYLES, mark_id, "테두리 모양")


def zone_label_align(raw: Mapping[str, Any], mark_id: str) -> str:
    """영역 이름표 정렬(`labelAlign`). 비면 왼쪽(처음 값)이고 `ZONE_LABEL_ALIGNS` 밖이면
    `ValueError`."""
    return _zone_choice(raw, "labelAlign", ZONE_LABEL_ALIGNS, mark_id, "이름표 정렬")


def zone_color(raw: Mapping[str, Any], mark_id: str) -> str:
    """영역 색 키. 비면 회색이고 `MARK_COLOR_KEYS` 밖이면 `ValueError`."""
    color = str(raw.get("color") or "") or "gray"
    if color not in MARK_COLOR_KEYS:
        raise ValueError(f"영역 {mark_id} 의 색을 알 수 없습니다: {color!r}")
    return color


def shape_fill(raw: Mapping[str, Any], mark_id: str) -> str:
    """도형 채우기 색 키(`SHAPE_FILL_KEYS` — 영역 색 여섯 + 진하게 `ink` + 바탕 `surface`). 비면
    파랑이고 목록 밖이면 `ValueError`."""
    color = str(raw.get("color") or "").strip() or "blue"
    if color not in SHAPE_FILL_KEYS:
        raise ValueError(f"도형 {mark_id} 의 채우기 색을 알 수 없습니다: {color!r}")
    return color


# 빗금을 갖는 종류(영역·도형). 다른 종류는 늘 거짓이고 보낸 값을 보지 않는다.
HATCH_MARK_KINDS: Final = ("zone", "shape")


def mark_color(raw: Mapping[str, Any], kind: str, mark_id: str) -> str:
    """요소 색 키 — 영역은 `zone_color`, 도형은 `shape_fill`, 그 밖은 빈 값(층 블록 색은 FAB 가
    따로 본다)."""
    if kind == "zone":
        return zone_color(raw, mark_id)
    if kind == "shape":
        return shape_fill(raw, mark_id)
    return ""


def prepare_floor_layout_marks(
    marks: Sequence[Mapping[str, Any]],
    canvas: CanvasSize,
) -> tuple[FloorLayoutMark, ...]:
    """한 층의 요소 목록을 검증·정규화한다. 하나라도 어긋나면 `ValueError`.

    받는 키는 편집기 계약(`id`·`kind`·`x`·`y`·`w`·`h`·`rot`·`label`·`color`·`hatch`·
    `keepOut`·`fontSize`·`fontColor`·`borderStyle`·`labelAlign`·`look`)이다. 좌표는 소수 첫째 자리로
    맞추고 상자가 캔버스 안이어야 한다. 글자 크기·색은 모든 종류가 갖는다(없으면 자동·기본). 테두리
    모양·이름표 정렬은 영역만 갖는다(없으면 점선·왼쪽, 다른 종류는 늘 처음 값이고 보낸 값을 보지
    않는다). 모양 값(`look`)은 동선·베이·도형만 갖는다(`mark_look`). 베이의 이름표는 번호다
    (`bay_label`). 색은 영역(`zone_color`)과 도형의 채우기(`shape_fill`)만, 빗금은 영역·도형만
    갖고 「설비 금지」는 영역만이다.
    """
    if len(marks) > MARKS_PER_FLOOR_MAX:
        raise ValueError(f"한 층의 도면 요소는 {MARKS_PER_FLOOR_MAX}개까지입니다: {len(marks)}개")
    prepared: list[FloorLayoutMark] = []
    seen: set[str] = set()
    for raw in marks:
        mark_id = mark_id_of(raw, seen)
        kind = str(raw.get("kind", ""))
        if kind not in MARK_KINDS:
            raise ValueError(f"도면 요소 {mark_id} 의 종류를 알 수 없습니다: {kind!r}")
        x, y, w, h = mark_box(raw, mark_id, MARK_NAMES[kind], canvas)
        prepared.append(
            FloorLayoutMark(
                mark_id=mark_id,
                kind=kind,
                x=x,
                y=y,
                w=w,
                h=h,
                rotation=mark_rotation(raw, mark_id),
                label=bay_label(raw, mark_id) if kind == "bay" else mark_label(raw, mark_id),
                color=mark_color(raw, kind, mark_id),
                hatch=kind in HATCH_MARK_KINDS and mark_flag(raw.get("hatch")),
                keep_out=kind == "zone" and mark_flag(raw.get("keepOut")),
                font_size=mark_font_size(raw, mark_id),
                font_color=mark_font_color(raw, mark_id),
                **zone_look(raw, kind, mark_id),
                look=mark_look(raw, kind, mark_id),
            )
        )
    return tuple(prepared)


def zone_look(raw: Mapping[str, Any], kind: str, mark_id: str) -> dict[str, str]:
    """영역이면 테두리 모양·이름표 정렬을 검사한 값, 아니면 처음 값(보낸 값을 보지 않는다)."""
    if kind != "zone":
        return {"border_style": ZONE_BORDER_STYLES[0], "label_align": ZONE_LABEL_ALIGNS[0]}
    return {
        "border_style": zone_border_style(raw, mark_id),
        "label_align": zone_label_align(raw, mark_id),
    }


def bay_label(raw: Mapping[str, Any], mark_id: str) -> str:
    """베이 화살표의 번호. 앞의 B·b 와 그 뒤 빈칸을 **모두** 뗀다(「80」·「B80」·「b 80」·「BB80」 →
    「80」) — 그릴 때 늘 「B」 를 붙이므로 저장값에 B 가 겹치지 않게 한다. 한 번 거친 값을 다시
    거쳐도 같다(편집기 `bayNumber` 가 입력 때, 이 함수가 적용 때, 저장 길이 대기분을 다시 검증할 때
    — 세 번 거쳐도 글이 바뀌지 않는다). `BAY_LABEL_MAX` 자를 넘으면 `ValueError`."""
    label = _BAY_PREFIX.sub("", str(raw.get("label") or "").strip())
    if len(label) > BAY_LABEL_MAX:
        raise ValueError(f"베이 {mark_id} 의 번호는 {BAY_LABEL_MAX}자까지입니다: {label!r}")
    return label


def _look_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _whole(number: float) -> float | int:
    """정수면 정수로 — JS 의 JSON 글(`1` · `0.5`)과 같은 정규 글이 나오게."""
    return int(number) if number.is_integer() else number


def _shape_adjust(preset: str, value: object, mark_id: str) -> list[float | int] | None:
    """도형 모양 조절 값(`adj`) — 프리셋의 개수·저장 범위(하한 ~ 상한, `min-w`·`min-h` 는 상한 ×
    `SHAPE_STRETCH_MAX`)·0.01 단위를 본다. 처음 값과 모두 같으면 None(넣지 않는다). 어긋나면
    `ValueError`."""
    spec = SHAPE_ADJUST[preset]
    bases = SHAPE_ADJUST_BASE[preset]
    name = SHAPE_NAMES[preset]
    if not isinstance(value, (list, tuple)) or len(value) != len(spec):
        raise ValueError(
            f"도형 {mark_id}({name})의 모양 조절 값은 {len(spec)}개여야 합니다: {value!r}"
        )
    normal: list[float | int] = []
    for item, (low, top, _default), base in zip(value, spec, bases, strict=True):
        high = top * SHAPE_STRETCH_MAX if base in ("min-w", "min-h") else top
        number = _look_number(item)
        if number is None or abs(number * 100 - round(number * 100)) > 1e-6:
            raise ValueError(
                f"도형 {mark_id}({name})의 모양 조절 값은 0.01 단위 숫자여야 합니다: {item!r}"
            )
        number = round(number * 100) / 100
        if not low - 1e-9 <= number <= high + 1e-9:
            raise ValueError(
                f"도형 {mark_id}({name})의 모양 조절 값은 {low:g}~{high:g} 사이여야 합니다: "
                f"{number:g}"
            )
        normal.append(_whole(number))
    if all(abs(got - default) < 1e-9 for got, (_, _, default) in zip(normal, spec, strict=True)):
        return None
    return normal


# 목록에서 고르는 모양 값의 화면 이름(거부 글).
_LOOK_WORDS: Final[Mapping[str, str]] = {
    "head": "머리 크기",
    "line": "선 색",
    "lineStyle": "선 모양",
    "shape": "도형 모양",
}


def _look_value(kind: str, key: str, value: object, mark_id: str) -> object:
    """모양 값 하나를 검사해 정규 값으로(숫자는 정수면 정수 — JS 의 JSON 글과 같게). 어긋나면
    `ValueError`. 도형의 모양 조절 값(`adj`)은 프리셋에 달려 `mark_look` 이 따로 본다."""
    name = MARK_NAMES.get(kind, kind)
    text = value.strip() if isinstance(value, str) else value
    allowed: Sequence[object]
    if key == "head":
        allowed = ARROW_HEADS
    elif key == "line":
        allowed = SHAPE_LINE_KEYS if kind == "shape" else LINE_COLOR_KEYS
    elif key == "shape":
        allowed = SHAPE_PRESETS
    elif key == "fillAlpha":
        number = _look_number(value)
        if (
            number is None
            or not number.is_integer()
            or not 0 <= number <= 100
            or int(number) % FILL_ALPHA_STEP
        ):
            raise ValueError(
                f"{name} {mark_id} 의 채우기 투명도는 0~100 의 {FILL_ALPHA_STEP} 단위여야 합니다: "
                f"{value!r}"
            )
        return int(number)
    elif key == "lineStyle":
        allowed = LINE_STYLES
    elif key == "lineWidth":
        number = _look_number(value)
        if number is None or number not in LINE_WIDTHS:
            raise ValueError(
                f"{name} {mark_id} 의 선 굵기를 알 수 없습니다: {value!r} — "
                f"{'·'.join(f'{width:g}' for width in LINE_WIDTHS)} 중 하나입니다."
            )
        return _whole(number)
    elif key == "flip":
        if not isinstance(value, bool):
            raise ValueError(f"{name} {mark_id} 의 뒤집기 값은 참·거짓이어야 합니다: {value!r}")
        return value
    else:  # `mark_look` 이 `LOOK_KEYS` 밖의 키를 먼저 거부한다
        raise ValueError(f"{name} {mark_id} 에 없는 모양 값입니다: {key!r}")
    if not isinstance(text, str) or text not in allowed:
        what = _LOOK_WORDS[key]
        raise ValueError(
            f"{name} {mark_id} 의 {with_object_particle(what)} 알 수 없습니다: {value!r} — "
            f"{'·'.join(str(item) for item in allowed)} 중 하나입니다."
        )
    return text


def mark_look(raw: Mapping[str, Any], kind: str, mark_id: str) -> str:
    """요소 모양 값(`look`)을 정규 JSON 글로. 받는 키는 종류마다 `LOOK_KEYS` 이고, 처음 값
    (`LOOK_DEFAULTS`)이거나 빈 값(None)인 키는 빼며, 다 빼면 빈 글이다. 모양 값이 없는 종류는 보낸
    값을 보지 않는다(빈 글 — 영역 아닌 요소의 테두리 모양과 같은 꼴). `look` 은 dict·JSON 글·빈 값을
    받는다. 도형은 프리셋(`shape` — 없으면 사각형)을 먼저 정하고 모양 조절 값(`adj`)을 그 프리셋의
    개수·범위로 본다(`SHAPE_ADJUST` — 처음 값과 같으면 뺀다). 어긋나면 `ValueError`(층 단위 전체
    교체라 버리지 않는다)."""
    keys = LOOK_KEYS.get(kind)
    if keys is None:
        return ""
    defaults = LOOK_DEFAULTS[kind]
    value = raw.get("look")
    if isinstance(value, str):
        text = value.strip()
        try:
            value = json.loads(text) if text else None
        except json.JSONDecodeError as exc:
            raise ValueError(f"도면 요소 {mark_id} 의 모양 값을 읽지 못했습니다.") from exc
    if value is None:
        return ""
    if not isinstance(value, Mapping):
        raise ValueError(f"도면 요소 {mark_id} 의 모양 값을 읽지 못했습니다.")
    look: dict[str, object] = {}
    for key in value:
        if key not in keys:
            raise ValueError(
                f"{MARK_NAMES.get(kind, kind)} {mark_id} 에 없는 모양 값입니다: {key!r}"
            )
    preset = "rect"
    if kind == "shape" and value.get("shape") is not None:
        preset = str(_look_value(kind, "shape", value["shape"], mark_id))
    for key, item in value.items():
        if item is None:
            continue
        if key == "adj":
            adjust = _shape_adjust(preset, item, mark_id)
            if adjust is not None:
                look[key] = adjust
            continue
        normal = _look_value(kind, key, item, mark_id)
        if key not in defaults or normal != defaults[key]:
            look[key] = normal
    return json.dumps(look, sort_keys=True, separators=(",", ":")) if look else ""


def look_payload(look: str) -> dict[str, Any]:
    """편집기로 보낼 모양 값 칸 — 처음 값이 아닌 것이 있으면 `{"look": {...}}`, 없으면 빈 dict."""
    return {"look": json.loads(look)} if look else {}


def marks_extent(marks: Sequence[MarkBox]) -> CanvasSize:
    """요소가 차지한 가장 먼 오른쪽·위. 캔버스를 이보다 줄이면 요소가 밖으로 나간다."""
    right = max((mark.x + mark.w for mark in marks), default=0.0)
    top = max((mark.y + mark.h for mark in marks), default=0.0)
    return right, top


def marks_fingerprint(marks: Sequence[FloorLayoutMark]) -> str:
    """한 층 요소 목록의 지문(그리는 순서 포함). 편집을 시작할 때 본 저장값과 저장 직전의 저장값이
    같은지 견줘, 다른 사람이 먼저 바꾼 층을 옛 목록으로 통째로 덮지 않게 한다."""
    payload = json.dumps(
        [mark.editor_payload() for mark in marks], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ Main 설비명 위치

# 한 층의 Main 설비명 위치 — Main 설비 → 위치(`GROUP_LABEL_POSITIONS`). 고른 적이 없거나 처음
# 위치로 되돌린 묶음은 넣지 않는다(`space_layout_edit.next_group_labels`).
GroupLabels = Mapping[str, str]


def prepare_group_labels(labels: Mapping[str, object]) -> dict[str, str]:
    """한 층의 Main 설비명 위치를 검증·정규화한다. 하나라도 어긋나면 `ValueError`(층 전체 교체라
    버리지 않는다). Main 설비 이름은 앞뒤 공백을 걷은 빈칸 아닌 글자이고 한 층에 한 번이다 — 길이·
    글자는 설비 마스터의 Main 설비 칸처럼 묶지 않는다(편집기 적용 `_parse_group_labels` 가 받은
    이름을 저장에서 거부하지 않게). 가운데도 행으로 남긴다 — 한 줄 묶음(모듈 2·3)은 처음 위치가
    위라 가운데를 고른 것을 지켜야 한다(옛 저장값에는 가운데 행이 없다). 이름 차례로 돌려준다."""
    prepared: dict[str, str] = {}
    seen: set[str] = set()
    for raw_name, raw_position in labels.items():
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            raise ValueError(f"Main 설비명 위치의 Main 설비 이름이 맞지 않습니다: {raw_name!r}")
        if name in seen:
            raise ValueError(f"Main 설비명 위치에 같은 Main 설비가 두 번 왔습니다: {name}")
        seen.add(name)
        position = raw_position.strip() if isinstance(raw_position, str) else raw_position
        if not isinstance(position, str) or position not in GROUP_LABEL_POSITIONS:
            raise ValueError(
                f"Main 설비 {name} 의 이름 위치를 알 수 없습니다: {raw_position!r} — "
                "가운데(center)·위(top)·아래(bottom) 중 하나입니다."
            )
        prepared[name] = position
    return dict(sorted(prepared.items()))


def floor_layout_fingerprint(marks: Sequence[FloorLayoutMark], labels: GroupLabels) -> str:
    """한 층의 도면 요소와 Main 설비명 위치를 함께 본 지문. 편집을 시작할 때 본 저장값
    (`FloorLayoutBase` 의 둘째 값)과 저장 직전 값을 견줘, 남이 먼저 바꾼 층을 옛 목록으로 덮지 않게
    한다. 위치 행이 없으면 요소 지문(`marks_fingerprint`)과 같다 — 위치를 한 번도 고르지 않은 층은
    지문이 그대로다."""
    if not labels:
        return marks_fingerprint(marks)
    payload = json.dumps(
        {
            "marks": [mark.editor_payload() for mark in marks],
            "groupLabels": sorted(labels.items()),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
