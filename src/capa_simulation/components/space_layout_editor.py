# Purpose: Space 층 도면의 Components v2 편집기(끌어 놓아 배치 고치기)와 보기 전용 뷰어를 그린다.

"""드래그앤드롭 배치 편집기. 같은 도면의 보기 전용 층 상세 뷰어(`mode="view"`)도 이것이다.

좌표 계약은 호기 마스터와 같다: 원점은 **왼쪽 아래**, Y 는 위로 커지고
호기 사각형은 (X좌표, Y좌표) → (X좌표+Xsize, Y좌표+Ysize) 다. SVG 는 위가 0 이라
화면 y = 캔버스 높이 − (Y좌표 + Ysize) 로 바꿔 그린다.

편집 상태는 **브라우저에 둔다.** 끌고 키우는 동안에는 파이썬으로 아무것도 보내지 않는다(Streamlit
은 값을 받을 때마다 페이지를 다시 돌린다). `적용` 을 누를 때 바뀐 호기·새로 넣은 호기·편집 영역
크기·도면 요소를 한 번에 보낸다. 같은 `epoch` 로 다시 그려지는 회차(다른 위젯을 건드린 경우)에는
진행 중인 편집과 확대 배율을 그대로 두고 단계 색·라벨만 다시 칠한다. epoch 는 층·저장본·편집본
세대로 만들어, 편집본이 바뀌면(적용·RawData 제출·저장) 브라우저가 새 값으로 다시 선다.

뷰어 크기도 브라우저 몫이다. 무대 폭은 열을 채우고, 높이는 화면에 맞춘 기본값이거나 무대 아래
손잡이로 고른 값이다. 고른 높이는 브라우저(localStorage)에 범위(`scope`)별로 기억하고 파이썬으로
보내지 않는다 — 보내면 페이지가 다시 돈다. 같은 까닭으로 epoch 에도 넣지 않는다.

HTML·CSS·JS 는 `space_layout_editor_assets/` 의 파일이다(파이썬 문자열에 넣으면 줄 길이 검사와
이스케이프가 JS 를 망가뜨린다). 색은 등록 시점 CSS 에 적지 않고 회차마다 `data.palette` 로 넘긴다 —
`st.components.v2.component` 는 등록 때의 CSS 를 그대로 쓰므로 테마를 바꿔도 따라오지 않는다.
받은 적용값의 검증은 `services/space_layout_edit.parse_editor_apply` 가 맡는다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from capa_simulation.components.space_layout import keep_out_color, mark_colors
from capa_simulation.design import tokens
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.floor_layout_profile import (
    CANVAS_DECIMALS,
    MAX_CANVAS_EXTENT,
    MIN_CANVAS_EXTENT,
    CanvasSize,
    FloorKey,
)
from capa_simulation.services.space_layout_edit import EditorInputs, floor_label

_ASSETS = Path(__file__).with_name("space_layout_editor_assets")

_EDITOR = st.components.v2.component(
    "capa_space_layout_editor",
    html=(_ASSETS / "editor.html").read_text(encoding="utf-8"),
    css=(_ASSETS / "editor.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "editor.js").read_text(encoding="utf-8"),
)


@dataclass(frozen=True)
class EditorSubmission:
    """`적용` 이 눌린 회차에 받은 값. `stale` 이면 편집기가 다시 서는 사이에 보낸 옛 적용이다."""

    payload: Mapping[str, Any]
    stale: bool


def _finite_or_none(value: object) -> float | None:
    """NaN·NA·무한대는 None — Components v2 가 NaN 을 JSON 에 실으면 브라우저가 거부한다."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _palette() -> dict[str, str]:
    """색은 회차마다 토큰에서 읽는다 — 테마를 바꾸면 같은 편집기가 새 색을 받는다."""
    return {
        "font": tokens.FONT_FAMILY,
        "text": tokens.SPACE_TEXT,
        "muted": tokens.TEXT_MUTED,
        "canvas": tokens.SPACE_CANVAS,
        "canvas-overlay": tokens.SPACE_CANVAS_OVERLAY,
        "image-opacity": "0.65",
        "frame": tokens.SPACE_BORDER,
        "grid": tokens.SPACE_GRID,
        "grid-major": tokens.BORDER_STRONG,
        "border": tokens.BORDER,
        "border-strong": tokens.BORDER_STRONG,
        "surface": tokens.SURFACE,
        # 무대 바탕 — 편집 영역 둘레의 여백이 이 색이다.
        "stage": tokens.SURFACE_PAGE,
        # 단추 글자는 앱 단추와 같은 TEXT(도면 글자 SPACE_TEXT 와 따로).
        "ui-text": tokens.TEXT,
        "accent": tokens.ACCENT,
        "on-accent": tokens.SURFACE,
        "danger": keep_out_color(),
        "fallback": tokens.EQUIPMENT_STAGE_FALLBACK,
        "mark-ink": tokens.SPACE_TEXT,
        "mark-muted": tokens.SPACE_LABEL_TEXT,
    }


def _clean_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """브라우저로 보낼 호기. 숫자 아님은 None 으로, 모체호기는 글자일 때만 묶음으로."""
    return [
        {
            "id": str(item["id"]),
            "label": str(item.get("label", item["id"])),
            "stage": str(item.get("stage") or ""),
            "detail": str(item.get("detail") or ""),
            "x": _finite_or_none(item.get("x")),
            "y": _finite_or_none(item.get("y")),
            "w": _finite_or_none(item.get("w")),
            "h": _finite_or_none(item.get("h")),
            "placed": bool(item.get("placed")),
            "isNew": bool(item.get("is_new")),
            "arrived": bool(item.get("arrived")),
            "floorless": bool(item.get("floorless")),
            "group": item["group"]
            if isinstance(item.get("group"), str) and item["group"]
            else None,
        }
        for item in items
    ]


def render_space_layout_viewer(
    *,
    key: str,
    epoch: str,
    items: Sequence[Mapping[str, Any]],
    canvas: CanvasSize,
    floor: FloorKey,
    marks: Sequence[FloorLayoutMark],
    summary: str,
    background_image: str | None = None,
) -> None:
    """층 상세 **뷰어**. 편집기와 같은 도면을 보기 전용으로 그린다 — 편집 도구가 없고, 끌기는
    화면 이동, 누르기는 그 호기 정보 한 줄, Ctrl+휠·+/−·더블클릭은 확대다. `summary` 는 도구 줄
    오른쪽의 한 줄 요약(배치·미배치·점유율)이다. 돌려받는 값이 없다."""
    _EDITOR(
        key=key,
        data={
            "mode": "view",
            "scope": "floor",
            "epoch": epoch,
            "title": floor_label(floor),
            "summary": summary,
            "items": _clean_items(items),
            "marks": [mark.editor_payload() for mark in marks],
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {"min": MIN_CANVAS_EXTENT, "max": MAX_CANVAS_EXTENT},
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "stageColors": dict(tokens.EQUIPMENT_STAGE_COLORS),
            "markColors": mark_colors(),
            "backgroundImage": background_image,
            "floor": floor_label(floor),
            "floors": [],
            "newUnit": {},
        },
        on_apply_change=lambda: None,
        width="stretch",
    )


def render_space_layout_editor(
    *,
    key: str,
    epoch: str,
    title: str,
    inputs: EditorInputs,
    canvas: CanvasSize,
    floor: FloorKey,
    floors: Sequence[FloorKey],
    marks: Sequence[FloorLayoutMark],
    new_unit: Mapping[str, Any],
    background_image: str | None = None,
) -> EditorSubmission | None:
    """편집기를 그리고 `적용` 이 눌린 회차에만 받은 값을 돌려준다(검증 전 원본).

    적용값: ``{"epoch", "changes", "canvas", "marks"}``.

    - ``changes``: 바뀐 호기. 놓인 호기는 좌표·크기, 트레이로 뺀 호기는 크기만(있으면) 든다.
      다른 층으로 보낸 호기는 ``moveTo`` 에 그 층 이름(「C2 2F」)을 단다. 편집기에서 새로 넣은
      호기는 ``created`` 에 폼 값을 든다. 항목의 ``group``(모체호기)이 같은 호기는 한 덩어리로
      움직인다.
    - ``canvas``: 편집 영역을 바꿨을 때만 ``{width, height}``.
    - ``marks``: 도면 요소를 바꿨을 때만 이 층 요소 전체 목록, 아니면 None.
    """
    items = _clean_items(inputs.items)
    result = _EDITOR(
        key=key,
        data={
            "scope": "floor",
            "epoch": epoch,
            "title": title,
            "items": items,
            "marks": [mark.editor_payload() for mark in marks],
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {
                "min": MIN_CANVAS_EXTENT,
                "max": MAX_CANVAS_EXTENT,
                "reservedW": _finite_or_none(inputs.reserved_extent[0]) or 0.0,
                "reservedH": _finite_or_none(inputs.reserved_extent[1]) or 0.0,
            },
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "stageColors": dict(tokens.EQUIPMENT_STAGE_COLORS),
            "markColors": mark_colors(),
            "defaultSize": {"w": inputs.default_size[0], "h": inputs.default_size[1]},
            "backgroundImage": background_image,
            "floor": floor_label(floor),
            "floors": [floor_label(key) for key in floors],
            "newUnit": dict(new_unit),
        },
        on_apply_change=lambda: None,
        width="stretch",
    )
    payload = getattr(result, "apply", None)
    if not isinstance(payload, Mapping):
        return None
    return EditorSubmission(payload=payload, stale=payload.get("epoch") != epoch)
