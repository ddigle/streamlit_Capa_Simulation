# Purpose: 누적 진척 「주차별」 그림의 까닭 꼬리표 자리를 가장 좁은 그림 칸에서 겹치지 않게 정한다.

"""누적 진척 「주차별」 까닭 꼬리표의 자리(2026-11-21 보드 답 중간-1 「점 곁 곧은 꼬리표」).

꼬리표는 그 주 점 바로 위(오름) · 아래(내림)에 곧은 짧은 지시선으로 붙는다 — 주 간격은 그대로다.
줄은 첫 줄이 「▲ +15일」 · 「▼ −13일」, 다음 줄이 항목(둘까지)이다. 자리가 막히면 항목 하나 → 대수를
뗀 항목 하나로 줄이고, 그래도 막히면 한 단 바깥으로 곧게 민다. 끝내 막히면 꼬리표 없이 표지 ·
풍선만이다.

**판정은 가장 좁은 그림 칸**(`NARROW_PLOT_WIDTH_PX`)에서 한다. 서버는 창 폭을 모르고, 꼬리표는 픽셀
고정 크기인데 주 간격은 폭에 비례하므로 좁은 칸에서 겹치지 않으면 넓은 칸에서도 겹치지 않는다. 결정
(줄 · 맞춤 · 단)은 데이터 자리(주 · 일수)와 픽셀 띄움(`PlacedTag.lift_px` · `shift_px`)으로 그림에
옮겨 어느 폭에서나 같은 자리에 선다. 세로는 그림 높이 · 여백이 고정이라 그대로 맞는다.

글 폭은 어림이다(한글 1em · 그 밖 0.58em · 굵은 첫 줄 8% 더). 이 모듈은 Streamlit 을 모르는 순수
계산이다 — 그리기는 `shortening_cumulative.weekly_figure` 다.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "ANCHORS",
    "DOWN_ROOM_PX",
    "FONT_PX",
    "GAP_TAG_PX",
    "GOAL_CLEAR_PX",
    "GOAL_LABEL_ROOM_PX",
    "INSET_PX",
    "LINE_HEIGHT_PX",
    "MARK_HALF_PX",
    "MAX_TAGS",
    "NARROW_PLOT_WIDTH_PX",
    "PAD_PX",
    "STEP_PX",
    "THRESHOLD_DAYS",
    "TIER_STEP_PX",
    "UP_ROOM_PX",
    "Box",
    "PlacedTag",
    "PlotFrame",
    "Scene",
    "TagWish",
    "overlaps",
    "place_tags",
    "tag_size",
    "text_width",
    "value_range",
    "value_ticks",
]

THRESHOLD_DAYS = 5
"""이 일수 미만 변동은 글 없이 표지만(풍선)."""
MAX_TAGS = 5
NARROW_PLOT_WIDTH_PX = 450
"""가장 좁은 그림 칸 어림 — 창 600px · 사이드바 접힘 → 본문 568 − 테두리 상자 안쪽 여백 ≈ 534 − 그림
여백(왼 56 · 오 24) ≈ 454."""
FONT_PX = 11
LINE_HEIGHT_PX = FONT_PX * 1.3
"""Plotly 글 줄 높이(`LINE_SPACING` 1.3)."""
PAD_PX = 3
"""꼬리표 판 안쪽 여백(annotation `borderpad`)."""
GAP_TAG_PX = 8
INSET_PX = 10
"""맞춤 「start」 · 「end」 에서 지시선이 꼬리표 끝에서 들어오는 자리."""
MARK_HALF_PX = 10
"""꼬리표가 붙는 큰 ▲ · ▼ 표지의 반 높이."""
STEP_PX = 5
TIER_STEP_PX = 56
GOAL_CLEAR_PX = 12
"""꼬리표 판 · 지시선이 목표선과 띄우는 최소 거리."""
GOAL_LABEL_ROOM_PX = 24
"""목표선 아래 목표 이름 자리 — 이름 판(선 아래 2 ~ 20px)과 그 아래 띄움. 세로축이 0 에서 잘려도
이만큼은 그림 칸 안에 남긴다(`value_range`)."""
UP_ROOM_PX = 64
"""가장 높은 점 위 자리 — 세 줄 꼬리표(머리 + 항목 둘)."""
DOWN_ROOM_PX = 52
"""가장 낮은 값(목표 · 기록) 아래 자리 — 목표 글, 또는 가장 낮은 기록 아래 두 줄 꼬리표(표지 반 높이
+ 띄움 + 두 줄 판 ≈ 50px — 목표가 없거나 목표 아래로 내려온 기록의 내림 꼬리표가 칸 밖으로 숨지
않게)."""

ANCHORS = ("middle", "start", "end")
_DOT_STEP_PX = 2.0

_Leader = tuple[float, float, float]
_Free = Callable[[int, "Box", _Leader], bool]


@dataclass(frozen=True)
class Box:
    """픽셀 네모 — y 는 아래로 는다."""

    x0: float
    y0: float
    x1: float
    y1: float

    def hit(self, other: Box, margin: float = 0.0) -> bool:
        return not (
            self.x1 + margin <= other.x0
            or other.x1 + margin <= self.x0
            or self.y1 + margin <= other.y0
            or other.y1 + margin <= self.y0
        )

    def has(self, x: float, y: float, margin: float = 0.0) -> bool:
        return (
            self.x0 - margin <= x <= self.x1 + margin and self.y0 - margin <= y <= self.y1 + margin
        )


@dataclass(frozen=True)
class PlotFrame:
    """그림 칸(Plotly plot area) — 가로 자리(주 위치 → px)와 세로 자리(일 → px)."""

    width: float
    height: float
    x_range: tuple[float, float]
    y_range: tuple[float, float]

    def x(self, value: float) -> float:
        low, high = self.x_range
        return self.width * (value - low) / (high - low)

    def y(self, value: float) -> float:
        low, high = self.y_range
        return self.height * (1 - (value - low) / (high - low))

    @property
    def days_per_px(self) -> float:
        low, high = self.y_range
        return (high - low) / self.height

    def resized(self, width: float) -> PlotFrame:
        return PlotFrame(width, self.height, self.x_range, self.y_range)


@dataclass(frozen=True)
class Scene:
    """꼬리표가 피할 것 — 점(주 위치, 일수) · 점선(남은 길) · 목표선과 그 글 · 끝 값 글 · 「+N일」
    글."""

    points: tuple[tuple[float, float], ...]
    projection: tuple[tuple[float, float], tuple[float, float]] | None = None
    goal_days: float | None = None
    goal_text: str = ""
    end_text: str = ""
    plain_labels: tuple[tuple[int, str], ...] = ()
    """점 위 「+N일」 글(점 차례, 글) — 꼬리표 없는 늘어난 주(근거 없음)."""


@dataclass(frozen=True)
class TagWish:
    """꼬리표를 달고 싶은 주 — 점 차례 · 변동 · 줄이는 차례대로의 줄 묶음."""

    position: int
    change: int
    levels: tuple[tuple[str, ...], ...]

    @property
    def up(self) -> bool:
        return self.change > 0


@dataclass(frozen=True)
class PlacedTag:
    """정한 꼬리표 — 줄 · 맞춤 · 단과 그 칸에서의 판 · 지시선(x, 점 끝 y, 판 끝 y)."""

    position: int
    up: bool
    lines: tuple[str, ...]
    anchor: str
    tier: int
    box: Box
    leader: tuple[float, float, float]

    @property
    def lift_px(self) -> float:
        """점에서 판 끝까지(위 · 아래) — Plotly annotation `yshift` 의 크기."""
        return MARK_HALF_PX + STEP_PX + self.tier * TIER_STEP_PX

    @property
    def shift_px(self) -> float:
        """맞춤에 따른 가로 띄움 — Plotly annotation `xshift`."""
        return {"middle": 0.0, "start": -INSET_PX, "end": float(INSET_PX)}[self.anchor]


def text_width(text: str, size: float) -> float:
    """글 폭 어림 — 한글 · 한자 1em, 그 밖 0.58em."""
    return sum(size if ord(char) > 0x2E80 else size * 0.58 for char in text)


def tag_size(lines: Sequence[str]) -> tuple[float, float]:
    """꼬리표 판 크기 — 첫 줄은 굵은 글이라 8% 넓게 어림한다."""
    widths = [
        text_width(line, FONT_PX) * (1.08 if index == 0 else 1.0)
        for index, line in enumerate(lines)
    ]
    return max(widths, default=0.0) + 2 * PAD_PX, LINE_HEIGHT_PX * len(lines) + 2 * PAD_PX


def value_range(
    values: Sequence[float], goal: float | None, plot_height: float
) -> tuple[float, float]:
    """세로축 — 목표(없으면 가장 낮은 기록) 아래부터(0 이 아님). 위로 세 줄 꼬리표 자리
    `UP_ROOM_PX`, 아래로 `DOWN_ROOM_PX` 를 둔다. 0 아래로는 내려가지 않되, 목표가 0일이거나
    기록보다 아주 낮아 0 에서 잘리면 목표 이름 자리(`GOAL_LABEL_ROOM_PX`)만큼만 0 아래로 내린다 —
    이름이 그림 칸 밖 가로축 눈금 글 위로 빠지지 않게. 그 칸에는 눈금을 두지 않는다
    (`value_ticks`)."""
    known = [*values, *([goal] if goal is not None else [])]
    if not known:
        return (0.0, 1.0)
    high, low = float(max(known)), float(min(known))
    if high <= low:
        # 값이 하나뿐 — 그 둘레로 넓힌다.
        pad = max(abs(high) * 0.1, 5.0)
        high, low = high + pad, low - pad
    data_px = max(plot_height - UP_ROOM_PX - DOWN_ROOM_PX, plot_height * 0.4)
    per_px = (high - low) / data_px
    bottom = max(low - DOWN_ROOM_PX * per_px, 0.0)
    if goal is not None:
        # 0 에서 잘리지 않았으면 목표 아래 자리가 `DOWN_ROOM_PX` 이상이라 그대로다. 잘려도 그림 칸이
        # 그만큼 짧아져 px 당 일수가 줄 뿐이라 이 자리는 `GOAL_LABEL_ROOM_PX` 이상으로 선다.
        bottom = min(bottom, float(goal) - GOAL_LABEL_ROOM_PX * per_px)
    return (bottom, high + UP_ROOM_PX * per_px)


def value_ticks(y_range: tuple[float, float]) -> tuple[int, ...] | None:
    """세로축 눈금 — 축이 0 아래로 내려간 때(목표 이름 자리 — `value_range`)만 0 부터 위로 고른
    눈금을 정해 0 아래 칸에 「−n일」 눈금이 서지 않게 한다. 그 밖에는 None(Plotly 자동 눈금)."""
    low, high = y_range
    if low >= 0:
        return None
    raw = max(high, 1.0) / 7
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(factor * magnitude for factor in (1, 2, 5, 10) if factor * magnitude >= raw)
    whole = max(1, round(step))
    return tuple(range(0, math.floor(high) + 1, whole))


# ---------------------------------------------------------------------- 장애물


def _points_px(frame: PlotFrame, scene: Scene) -> list[tuple[float, float]]:
    return [(frame.x(x), frame.y(y)) for x, y in scene.points]


def _sample(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    (x0, y0), (x1, y1) = start, end
    count = max(1, int(math.hypot(x1 - x0, y1 - y0) / _DOT_STEP_PX))
    return [(x0 + (x1 - x0) * t / count, y0 + (y1 - y0) * t / count) for t in range(count + 1)]


def _end_box(frame: PlotFrame, scene: Scene) -> Box | None:
    if not scene.points or not scene.end_text:
        return None
    x, y = _points_px(frame, scene)[-1]
    width = text_width(scene.end_text, 12) * 1.1 + 4
    return Box(x + 8, y - 21, x + 8 + width, y - 5)


def _goal_boxes(frame: PlotFrame, scene: Scene) -> list[Box]:
    if scene.goal_days is None:
        return []
    goal_y = frame.y(scene.goal_days)
    boxes = [Box(0, goal_y - GOAL_CLEAR_PX, frame.width, goal_y + GOAL_CLEAR_PX)]
    if scene.goal_text:
        width = text_width(scene.goal_text, 12) + 6
        bottom = goal_y + GOAL_LABEL_ROOM_PX - 4
        boxes.append(Box(frame.width - width, goal_y + 2, frame.width, bottom))
    return boxes


def _plain_boxes(frame: PlotFrame, scene: Scene) -> list[Box]:
    points = _points_px(frame, scene)
    boxes = []
    for position, text in scene.plain_labels:
        x, y = points[position]
        half = text_width(text, 12) / 2 + 2
        boxes.append(Box(x - half, y - 25, x + half, y - 7))
    return boxes


def _obstacles(
    frame: PlotFrame, scene: Scene, big: frozenset[int]
) -> tuple[list[tuple[float, float]], list[tuple[int | None, Box]]]:
    """선 표본(꺾은선 · 남은 길 점선)과 네모(점 — 차례 붙임 · 끝 값 글 · 목표선 띠와 글 ·
    「+N일」)."""
    points = _points_px(frame, scene)
    dots: list[tuple[float, float]] = []
    for start, end in zip(points, points[1:], strict=False):
        dots += _sample(start, end)
    if scene.projection is not None:
        (ax, ay), (bx, by) = scene.projection
        dots += _sample((frame.x(ax), frame.y(ay)), (frame.x(bx), frame.y(by)))
    rects: list[tuple[int | None, Box]] = []
    for position, (x, y) in enumerate(points):
        half = MARK_HALF_PX if position in big else 8
        rects.append((position, Box(x - half + 1, y - half, x + half - 1, y + half)))
    end_box = _end_box(frame, scene)
    if end_box is not None:
        rects.append((None, end_box))
    rects += [(None, box) for box in _goal_boxes(frame, scene)]
    rects += [(None, box) for box in _plain_boxes(frame, scene)]
    return dots, rects


def _geometry(
    frame: PlotFrame, scene: Scene, position: int, up: bool, lines: Sequence[str], anchor: str,
    tier: int,
) -> tuple[Box, tuple[float, float, float]]:  # fmt: skip
    x, y = _points_px(frame, scene)[position]
    width, height = tag_size(lines)
    lift = MARK_HALF_PX + STEP_PX + tier * TIER_STEP_PX
    edge = y - lift if up else y + lift
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "start":
        left = x - INSET_PX
    else:
        left = x + INSET_PX - width
    top = edge - height if up else edge
    leader = (x, y - MARK_HALF_PX if up else y + MARK_HALF_PX, edge)
    return Box(left, top, left + width, top + height), leader


def _leader_box(leader: tuple[float, float, float]) -> Box:
    x, start, end = leader
    return Box(x - 0.5, min(start, end), x + 0.5, max(start, end))


# ---------------------------------------------------------------------- 배치


def place_tags(
    frame: PlotFrame,
    scene: Scene,
    wishes: Sequence[TagWish],
    decided: Mapping[int, PlacedTag] | None = None,
) -> dict[int, PlacedTag]:
    """꼬리표 자리. 차례는 오름 먼저 → 큰 변동 → 최근 주이고 `MAX_TAGS` 까지다.

    `decided` 를 주면 그 결정(줄 · 맞춤 · 단)을 이 칸에 그대로 옮긴다(넓은 칸 확인용). 막힌 꼬리표는
    한 번 고쳐 놓는다 — 같은 쪽 이웃 하나의 맞춤 · 단을 바꿔 자리가 나면 둘 다 놓는다.
    """
    wanted = [wish for wish in wishes if abs(wish.change) >= THRESHOLD_DAYS and wish.levels]
    order = sorted(wanted, key=lambda wish: (not wish.up, -abs(wish.change), -wish.position))
    if decided is not None:
        placed: dict[int, PlacedTag] = {}
        for wish in order:
            chosen = decided.get(wish.position)
            if chosen is None:
                continue
            box, leader = _geometry(
                frame, scene, wish.position, wish.up, chosen.lines, chosen.anchor, chosen.tier
            )
            placed[wish.position] = PlacedTag(
                wish.position, wish.up, chosen.lines, chosen.anchor, chosen.tier, box, leader
            )
        return placed
    big = frozenset(wish.position for wish in order)
    dots, rects = _obstacles(frame, scene, big)
    points = _points_px(frame, scene)
    placed = {}

    def free(position: int, box: Box, leader: tuple[float, float, float]) -> bool:
        if box.x0 < 0 or box.x1 > frame.width or box.y0 < 0 or box.y1 > frame.height:
            return False
        if any(box.has(x, y, 3) for x, y in dots):
            return False
        lead = _leader_box(leader)
        long_leader = abs(leader[2] - leader[1]) > 1
        for owner, rect in rects:
            if owner == position:
                continue
            if box.hit(rect, 3) or (long_leader and lead.hit(rect, 1)):
                return False
        for other in placed.values():
            if box.hit(other.box, GAP_TAG_PX):
                return False
            if box.hit(_leader_box(other.leader), 3) or lead.hit(other.box, 2):
                return False
        return True

    def attempt(wish: TagWish, anchors: Sequence[str]) -> PlacedTag | None:
        for lines in wish.levels:
            for tier in (0, 1):
                for anchor in anchors:
                    box, leader = _geometry(
                        frame, scene, wish.position, wish.up, lines, anchor, tier
                    )
                    if free(wish.position, box, leader):
                        return PlacedTag(
                            wish.position, wish.up, tuple(lines), anchor, tier, box, leader
                        )
        return None

    for wish in order:
        if len(placed) >= MAX_TAGS:
            break
        x = points[wish.position][0]
        same = [other for other in placed.values() if other.up == wish.up]
        if same:
            nearest = min(same, key=lambda other: abs(points[other.position][0] - x))
            anchors = (
                ("middle", "start", "end")
                if points[nearest.position][0] < x
                else ("middle", "end", "start")
            )
        else:
            anchors = (
                ("middle", "end", "start")
                if wish.position > len(points) / 2
                else ("middle", "start", "end")
            )
        got = attempt(wish, anchors)
        if got is None:
            got = _retry_with_neighbour(frame, scene, wish, placed, points, free, attempt)
        if got is not None:
            placed[wish.position] = got
    return placed


def _retry_with_neighbour(
    frame: PlotFrame,
    scene: Scene,
    wish: TagWish,
    placed: dict[int, PlacedTag],
    points: Sequence[tuple[float, float]],
    free: _Free,
    attempt: Callable[[TagWish, Sequence[str]], PlacedTag | None],
) -> PlacedTag | None:
    """같은 쪽 이웃 하나의 맞춤 · 단을 바꿔(줄은 그대로) 자리가 나면 이웃을 그 자리에 두고 새
    꼬리표를 돌려준다. 안 되면 이웃을 되돌리고 None."""
    x = points[wish.position][0]
    neighbours = sorted(
        (other for other in placed.values() if other.up == wish.up),
        key=lambda other: abs(points[other.position][0] - x),
    )
    for old in neighbours:
        del placed[old.position]
        for tier in (0, 1):
            for anchor in ANCHORS:
                if (anchor, tier) == (old.anchor, old.tier):
                    continue
                box, leader = _geometry(frame, scene, old.position, old.up, old.lines, anchor, tier)
                if not free(old.position, box, leader):
                    continue
                placed[old.position] = PlacedTag(
                    old.position, old.up, old.lines, anchor, tier, box, leader
                )
                got = attempt(wish, ("middle", "end", "start"))
                if got is not None:
                    return got
                del placed[old.position]
        placed[old.position] = old
    return None


def overlaps(frame: PlotFrame, scene: Scene, placed: Mapping[int, PlacedTag]) -> list[str]:
    """정한 꼬리표를 이 칸에서 다시 잰 겹침 — 빈 목록이면 0(시험 · 넓은 칸 확인)."""
    big = frozenset(placed)
    dots, rects = _obstacles(frame, scene, big)
    bad: list[str] = []
    for position, tag in placed.items():
        box = tag.box
        if box.x0 < 0 or box.x1 > frame.width or box.y0 < 0 or box.y1 > frame.height:
            bad.append(f"{position} 칸 밖")
        if any(box.has(x, y, 1) for x, y in dots):
            bad.append(f"{position} 선과 겹침")
        for owner, rect in rects:
            if owner != position and box.hit(rect, 0):
                bad.append(f"{position} 네모와 겹침 {rect}")
        for other_position, other in placed.items():
            if other_position == position:
                continue
            if other_position > position and box.hit(other.box, 0):
                bad.append(f"{position} ↔ {other_position}")
            if box.hit(_leader_box(other.leader), 0):
                bad.append(f"{position} 판이 {other_position} 지시선을 덮음")
    return bad
