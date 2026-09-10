# Purpose: 층별 배치 도면 이미지와 캔버스 치수의 계약·검증·기본값을 정의한다.

"""층별 배치 도면 이미지와 캔버스 치수의 계약·검증·기본값을 정의한다."""

from __future__ import annotations

import base64
import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

# 도면이 없는 층의 캔버스. 기존 좌표 계약(X 0~100, Y 0~60)이 그대로 산다.
DEFAULT_CANVAS_WIDTH: Final = 100.0
DEFAULT_CANVAS_HEIGHT: Final = 60.0

# 캔버스 치수 허용 범위. 폭은 도면을 올려도 100 으로 고정하지만 층마다 직접 고칠 수 있다.
MIN_CANVAS_EXTENT: Final = 10.0
MAX_CANVAS_EXTENT: Final = 400.0
CANVAS_DECIMALS: Final = 1

# 설비 DuckDB 는 통째로 S3 스냅샷에 실린다. 도면 한 장이 곧 매 전송의 고정 비용이라
# 층당 상한과 전 층 합계 상한을 코드에서 건다. 브라우저는 파일을 다 올린 뒤에야 이 검사가
# 도므로 전송 차단이 아니라 저장 거부다. 도면은 이미 압축된 PNG·JPEG 라 DuckDB 가 더
# 줄이지 못하고, 합계가 곧 스냅샷 증가분이다.
MAX_FLOOR_LAYOUT_BYTES: Final = 2 * 1024 * 1024
MAX_TOTAL_LAYOUT_BYTES: Final = 30 * 1024 * 1024
RECOMMENDED_FLOOR_LAYOUT_BYTES: Final = 1024 * 1024

# 헤더에서 읽은 픽셀 치수의 상식 범위. 난수 바이트에 SOI 만 붙인 파일이 가짜 SOF 마커를
# 만나 말도 안 되는 치수를 돌려주는 것을 막는다.
MIN_IMAGE_PIXEL_EXTENT: Final = 1
MAX_IMAGE_PIXEL_EXTENT: Final = 30_000

ALLOWED_IMAGE_EXTENSIONS: Final[Mapping[str, str]] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

FloorKey = tuple[str, str]
CanvasSize = tuple[float, float]
FloorCanvasMap = Mapping[FloorKey, CanvasSize]

_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE: Final = b"\xff\xd8"
# SOF0~SOF15 에서 허브만 뺀 마커가 가로·세로를 담는다(0xC4 DHT, 0xC8 JPG, 0xCC DAC).
_JPEG_SIZE_MARKERS: Final = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


@dataclass(frozen=True)
class FloorLayoutCanvas:
    """도면 바이트를 빼고 층별 캔버스 치수와 보유 여부만 담는다."""

    building: str
    floor: str
    canvas_width: float
    canvas_height: float
    image_name: str | None
    image_byte_count: int
    updated_at: datetime

    @property
    def has_image(self) -> bool:
        return self.image_byte_count > 0

    @property
    def canvas_size(self) -> CanvasSize:
        return self.canvas_width, self.canvas_height


@dataclass(frozen=True)
class FloorLayoutProfile:
    """한 층의 캔버스 치수와 Figure 에 바로 넘길 수 있는 도면 data URI."""

    building: str
    floor: str
    canvas_width: float
    canvas_height: float
    image_data_uri: str | None
    image_name: str | None
    image_byte_count: int
    updated_at: datetime

    @property
    def canvas_size(self) -> CanvasSize:
        return self.canvas_width, self.canvas_height


def canvas_for(canvases: FloorCanvasMap | None, building: str, floor: str) -> CanvasSize:
    """도면 프로필이 없는 층은 기본 캔버스를 돌려준다."""
    if not canvases:
        return DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT
    return canvases.get((building, floor), (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT))


def max_canvas_extent(canvases: FloorCanvasMap | None) -> CanvasSize:
    """모든 층을 하나의 편집기 상한으로 덮을 때 쓰는 최대 폭·높이."""
    width = DEFAULT_CANVAS_WIDTH
    height = DEFAULT_CANVAS_HEIGHT
    for canvas_width, canvas_height in (canvases or {}).values():
        width = max(width, canvas_width)
        height = max(height, canvas_height)
    return width, height


def normalize_canvas_size(width: float, height: float) -> CanvasSize:
    """사용자가 직접 넣은 캔버스 폭·높이를 검증하고 소수 첫째 자리로 맞춘다."""
    values: list[float] = []
    for value, label in ((width, "캔버스 폭"), (height, "캔버스 높이")):
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}은(는) 숫자여야 합니다.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{label}은(는) 숫자여야 합니다.")
        if number < MIN_CANVAS_EXTENT or number > MAX_CANVAS_EXTENT:
            raise ValueError(
                f"{label}은(는) {MIN_CANVAS_EXTENT:g}~{MAX_CANVAS_EXTENT:g} 범위여야 합니다."
            )
        values.append(round(number, CANVAS_DECIMALS))
    return values[0], values[1]


def canvas_from_pixel_size(width_px: int, height_px: int) -> CanvasSize:
    """폭 100 을 고정하고 도면 종횡비로 높이를 뽑는다."""
    if width_px <= 0 or height_px <= 0:
        return DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT
    height = DEFAULT_CANVAS_WIDTH * height_px / width_px
    clamped = min(max(height, MIN_CANVAS_EXTENT), MAX_CANVAS_EXTENT)
    return normalize_canvas_size(DEFAULT_CANVAS_WIDTH, clamped)


def normalize_image_upload(file_name: str, payload: bytes) -> tuple[str, str]:
    """확장자·용량을 검사하고 (파일명, MIME) 을 돌려준다."""
    normalized_name = file_name.strip()
    if not normalized_name:
        raise ValueError("도면 파일 이름이 비어 있습니다.")
    _, separator, extension = normalized_name.rpartition(".")
    mime = ALLOWED_IMAGE_EXTENSIONS.get(extension.lower()) if separator else None
    if mime is None:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise ValueError(f"도면은 {allowed} 파일만 올릴 수 있습니다: {normalized_name}")
    if not payload:
        raise ValueError("도면 파일이 비어 있습니다.")
    if len(payload) > MAX_FLOOR_LAYOUT_BYTES:
        # 거부 사유가 보이도록 실제 크기는 반올림하지 않고 바이트로 적는다.
        raise ValueError(
            f"도면은 층당 {format_bytes(MAX_FLOOR_LAYOUT_BYTES)} 이하만 저장합니다: "
            f"{len(payload):,}B"
        )
    if image_pixel_size(payload) is None:
        raise ValueError(f"도면 파일 형식을 읽지 못했습니다: {normalized_name}")
    signature_mime = _signature_mime(payload)
    if signature_mime is None or signature_mime != mime:
        # 확장자만 바꾼 파일을 그대로 저장하면 data URI 의 MIME 이 실제 내용과 달라
        # 배경이 조용히 안 그려진다. 내용을 정본으로 본다.
        raise ValueError(f"도면 파일 내용이 확장자와 다릅니다: {normalized_name}")
    return normalized_name, mime


def require_total_layout_budget(other_floors_bytes: int, payload_bytes: int) -> None:
    """이 층을 뺀 나머지 층 합계에 새 도면을 더해 전체 상한을 넘는지 본다."""
    total = other_floors_bytes + payload_bytes
    if total > MAX_TOTAL_LAYOUT_BYTES:
        raise ValueError(
            f"도면 전체 합계는 {format_bytes(MAX_TOTAL_LAYOUT_BYTES)} 이하만 저장합니다: "
            f"{total:,}B (이 층 {payload_bytes:,}B 포함). 다른 층 도면을 지우거나 줄이세요."
        )


def image_pixel_size(payload: bytes) -> tuple[int, int] | None:
    """PNG·JPEG 헤더에서 가로·세로 픽셀을 읽는다. 외부 의존성을 쓰지 않는다."""
    if payload.startswith(_PNG_SIGNATURE):
        size = _png_pixel_size(payload)
    elif payload[:2] == _JPEG_SIGNATURE:
        size = _jpeg_pixel_size(payload)
    else:
        return None
    if size is None or not all(
        MIN_IMAGE_PIXEL_EXTENT <= extent <= MAX_IMAGE_PIXEL_EXTENT for extent in size
    ):
        return None
    return size


def to_data_uri(mime: str, payload: bytes) -> str:
    """plotly `add_layout_image(source=...)` 가 그대로 받는 data URI 를 만든다."""
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.0f}KB"
    return f"{size}B"


def _signature_mime(payload: bytes) -> str | None:
    """앞 시그니처로 실제 형식을 판정한다. 확장자는 믿지 않는다."""
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ALLOWED_IMAGE_EXTENSIONS["png"]
    if payload.startswith(b"\xff\xd8"):
        return ALLOWED_IMAGE_EXTENSIONS["jpg"]
    return None


def _png_pixel_size(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 24 or payload[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", payload[16:24])
    if width <= 0 or height <= 0:
        return None
    return int(width), int(height)


def _jpeg_pixel_size(payload: bytes) -> tuple[int, int] | None:
    index = 2
    total = len(payload)
    while index + 3 < total:
        if payload[index] != 0xFF:
            # 마커 체인이 끊기면 JPEG 가 아니다. 건너뛰며 훑으면 난수에서도 우연히
            # SOF 처럼 보이는 바이트를 만나 통과한다(1.5MB 난수 표본 20회 중 4회).
            return None
        marker = payload[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
            index += 2
            continue
        (length,) = struct.unpack(">H", payload[index + 2 : index + 4])
        if length < 2:
            return None
        if marker in _JPEG_SIZE_MARKERS:
            segment = payload[index + 4 : index + 9]
            if len(segment) < 5:
                return None
            height, width = struct.unpack(">HH", segment[1:5])
            if width <= 0 or height <= 0:
                return None
            return int(width), int(height)
        index += 2 + length
    return None
