# Purpose: Space 층 도면의 비설비 도면 요소와 Main 설비명 위치의 계약·검증을 정의한다.

"""Space 층 도면의 비설비 도면 요소.

호기가 아닌 것 — 반입구(셔터)·여닫이문·영역·기둥·글자·동선 화살표 — 을 층마다 따로 둔다.
설비 마스터의 행이 아니고 설비 리비전과도 무관한 **현행값**이다(`floor_layout_profile` 의
캔버스와 같은 성격). 좌표 계약은 호기와 같다: 원점은 왼쪽 아래, 상자는 (x, y) → (x+w, y+h)
이고 회전은 상자 가운데를 축으로 90° 단위다(회전한 뒤의 축 정렬 상자를 저장한다).

저장 경로의 검증이라 **잘못된 항목을 조용히 버리지 않는다.** 층 단위 전체 교체라서 하나를
버리면 그 요소가 지워진다 — 그래서 하나라도 어긋나면 `ValueError` 로 저장을 거부한다.

같은 층 현행값으로 **Main 설비 모듈 묶음 이름표의 위치**(`GROUP_LABEL_POSITIONS` — 묶음 범위
가운데·위·아래, 2026-10-23 사용자 요청)도 여기 둔다. 설비 마스터 칸이 아니고, 가운데(기본)는
행을 두지 않는다. 층 저장의 동시성 대조는 요소와 위치를 함께 본다(`floor_layout_fingerprint`).
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

MARK_KINDS: Final = ("zone", "shutter", "door", "column", "text", "arrow")
MARK_NAMES: Final[Mapping[str, str]] = {
    "zone": "영역",
    "shutter": "반입구",
    "door": "문",
    "column": "기둥",
    "text": "글자",
    "arrow": "동선",
}
# 호기가 덮으면 경고하는 요소(겹침처럼 저장은 막지 않는다). 영역은 「설비 금지」를 켠 것만.
BLOCKING_MARK_KINDS: Final = ("shutter", "door", "column")
MARK_ROTATIONS: Final = (0, 90, 180, 270)
# 영역 색 이름. 실제 색은 그리는 쪽이 테마 토큰(제품별 비중과 같은 검증된 범주 팔레트)에서 고른다.
MARK_COLOR_KEYS: Final = ("blue", "rose", "green", "violet", "sky", "gray")
MARK_LABEL_MAX: Final = 40
# 이름표 글자 크기(화면 px). 빈 값(None)은 「자동」 — 글자 요소는 상자에 맞추고 나머지는 11px 다.
# 화면 px 라 확대해도 글자 크기는 그대로다(이름표가 도면을 덮지 않게). 층·FAB 요소가 함께 쓴다.
MARK_FONT_SIZES: Final = (9, 11, 13, 16, 20, 24)
# 영역 테두리 모양(점선·실선)과 이름표 정렬(왼쪽·가운데·오른쪽). 첫 값이 처음 값이자 옛 행(빈
# 칸)의 값이다 — 지금 모습(점선 테두리, 왼쪽 위 꼬리표). 영역이 아닌 요소는 늘 처음 값이다.
# 층·FAB 요소가 함께 쓴다.
ZONE_BORDER_STYLES: Final = ("dashed", "solid")
ZONE_LABEL_ALIGNS: Final = ("left", "center", "right")
MARKS_PER_FLOOR_MAX: Final = 500
# Main 설비 모듈 묶음 이름표 위치 — 묶음 범위 정가운데(기본), 범위 바깥 바로 위·아래.
GROUP_LABEL_POSITIONS: Final = ("center", "top", "bottom")
GROUP_LABEL_NAME_MAX: Final = 40
_MARK_ID: Final = re.compile(r"[A-Za-z0-9_-]{1,40}")


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

    @property
    def blocks(self) -> bool:
        """호기가 덮으면 경고할 요소인가 — 반입구·문·기둥, 「설비 금지」 영역."""
        return self.kind in BLOCKING_MARK_KINDS or (self.kind == "zone" and self.keep_out)

    @property
    def name(self) -> str:
        """화면 이름: 이름표가 있으면 그것, 없으면 종류 이름."""
        return self.label or MARK_NAMES[self.kind]

    def editor_payload(self) -> dict[str, Any]:
        """편집기(브라우저)에 보내는 모양. 키 이름은 편집기 JS 계약이다."""
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
            f"도면 요소 {mark_id}({name}) 가 캔버스 {width:g} × {height:g} 를 벗어났습니다."
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
            f"영역 {mark_id} 의 {what}을 알 수 없습니다: {value!r} — "
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


def prepare_floor_layout_marks(
    marks: Sequence[Mapping[str, Any]],
    canvas: CanvasSize,
) -> tuple[FloorLayoutMark, ...]:
    """한 층의 요소 목록을 검증·정규화한다. 하나라도 어긋나면 `ValueError`.

    받는 키는 편집기 계약(`id`·`kind`·`x`·`y`·`w`·`h`·`rot`·`label`·`color`·`hatch`·
    `keepOut`·`fontSize`·`fontColor`·`borderStyle`·`labelAlign`)이다. 좌표는 소수 첫째 자리로 맞추고
    상자가 캔버스 안이어야 한다. 글자 크기·색은 모든 종류가 갖는다(없으면 자동·기본). 테두리 모양·
    이름표 정렬은 영역만 갖는다(없으면 점선·왼쪽, 다른 종류는 늘 처음 값이고 보낸 값을 보지 않는다).
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
                label=mark_label(raw, mark_id),
                color=zone_color(raw, mark_id) if kind == "zone" else "",
                hatch=kind == "zone" and mark_flag(raw.get("hatch")),
                keep_out=kind == "zone" and mark_flag(raw.get("keepOut")),
                font_size=mark_font_size(raw, mark_id),
                font_color=mark_font_color(raw, mark_id),
                **zone_look(raw, kind, mark_id),
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

# 한 층의 Main 설비명 위치 — Main 설비 → 위치(`GROUP_LABEL_POSITIONS`). 가운데(기본)는 넣지 않는다.
GroupLabels = Mapping[str, str]


def prepare_group_labels(labels: Mapping[str, object]) -> dict[str, str]:
    """한 층의 Main 설비명 위치를 검증·정규화한다. 하나라도 어긋나면 `ValueError`(층 전체 교체라
    버리지 않는다). Main 설비 이름은 앞뒤 공백을 걷은 1~40자이고 한 층에 한 번이다. 가운데(기본)는
    행을 두지 않으므로 빼고, 이름 차례로 돌려준다."""
    prepared: dict[str, str] = {}
    seen: set[str] = set()
    for raw_name, raw_position in labels.items():
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name or len(name) > GROUP_LABEL_NAME_MAX or not name.isprintable():
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
        if position != GROUP_LABEL_POSITIONS[0]:
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
