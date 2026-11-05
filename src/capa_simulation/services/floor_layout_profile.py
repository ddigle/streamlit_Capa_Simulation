# Purpose: 층별 캔버스 치수의 계약·검증·기본값을 정의한다.

"""층별 캔버스 치수의 계약·검증·기본값을 정의한다."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from capa_simulation.services.korean_particle import with_topic_particle

# 캔버스를 저장하지 않은 층의 캔버스. 기존 좌표 계약(X 0~100, Y 0~60)이 그대로 산다.
DEFAULT_CANVAS_WIDTH: Final = 100.0
DEFAULT_CANVAS_HEIGHT: Final = 60.0

# 캔버스 치수 허용 범위.
MIN_CANVAS_EXTENT: Final = 10.0
MAX_CANVAS_EXTENT: Final = 400.0
CANVAS_DECIMALS: Final = 1

FloorKey = tuple[str, str]
CanvasSize = tuple[float, float]
FloorCanvasMap = Mapping[FloorKey, CanvasSize]


@dataclass(frozen=True)
class FloorLayoutCanvas:
    """저장된 층별 캔버스 치수."""

    building: str
    floor: str
    canvas_width: float
    canvas_height: float
    updated_at: datetime

    @property
    def canvas_size(self) -> CanvasSize:
        return self.canvas_width, self.canvas_height


@dataclass(frozen=True)
class FloorLayoutProfile:
    """한 층의 저장된 캔버스 치수."""

    building: str
    floor: str
    canvas_width: float
    canvas_height: float
    updated_at: datetime

    @property
    def canvas_size(self) -> CanvasSize:
        return self.canvas_width, self.canvas_height


def max_canvas_extent(canvases: FloorCanvasMap | None) -> CanvasSize:
    """모든 층을 하나의 편집기 상한으로 덮을 때 쓰는 최대 폭·높이."""
    width = DEFAULT_CANVAS_WIDTH
    height = DEFAULT_CANVAS_HEIGHT
    for canvas_width, canvas_height in (canvases or {}).values():
        width = max(width, canvas_width)
        height = max(height, canvas_height)
    return width, height


def rounded_to_canvas(value: float) -> float:
    """캔버스 좌표·치수를 저장 정밀도(소수 `CANVAS_DECIMALS` 자리)로 맞춘다."""
    return round(value, CANVAS_DECIMALS)


def normalize_canvas_size(width: float, height: float) -> CanvasSize:
    """사용자가 직접 넣은 캔버스 폭·높이를 검증하고 소수 첫째 자리로 맞춘다."""
    values: list[float] = []
    for value, label in ((width, "캔버스 폭"), (height, "캔버스 높이")):
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{with_topic_particle(label)} 숫자여야 합니다.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{with_topic_particle(label)} 숫자여야 합니다.")
        if number < MIN_CANVAS_EXTENT or number > MAX_CANVAS_EXTENT:
            raise ValueError(
                f"{with_topic_particle(label)} {MIN_CANVAS_EXTENT:g}~{MAX_CANVAS_EXTENT:g} "
                "범위여야 합니다."
            )
        values.append(rounded_to_canvas(number))
    return values[0], values[1]
