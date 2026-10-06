# Purpose: Space 층·FAB 도면의 Components v2 편집기(끌어 놓아 배치 고치기)와 보기 전용 뷰어.

"""드래그앤드롭 배치 편집기. 같은 도면의 보기 전용 층 상세 뷰어(`mode="view"`)와 FAB 전체 도면
(`scope="fab"`, 보기 전용 뷰어와 편집기)도 이것이다 — 컴포넌트는 하나만 등록하고 범위 표시로 나눈다.

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

FAB 도면의 층 블록을 누르면(또는 초점을 두고 Enter) 브라우저가 `navigate` 를 보낸다. 받는 쪽은
`on_navigate_change` 콜백이다 — 콜백은 본문보다 먼저 돌므로 그 자리에서 층을 바꾸면 재실행 한
번으로 층 상세가 선다(콜백 안에서 `st.session_state[key].navigate` 로 읽힌다).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import streamlit as st

from capa_simulation.components.space_layout import keep_out_color, mark_colors
from capa_simulation.design import tokens
from capa_simulation.services.fab_layout import (
    FLOOR_KEYS,
    FabLayoutMark,
    floor_from_label,
    floor_label,
)
from capa_simulation.services.floor_layout_mark import (
    MARK_COLOR_KEYS,
    MARK_FONT_SIZES,
    FloorLayoutMark,
)
from capa_simulation.services.floor_layout_profile import (
    CANVAS_DECIMALS,
    MAX_CANVAS_EXTENT,
    MIN_CANVAS_EXTENT,
    CanvasSize,
    FloorKey,
)
from capa_simulation.services.space_layout_edit import EditorInputs, finite_or_none

_ASSETS = Path(__file__).with_name("space_layout_editor_assets")
# FAB 도면의 범위 이름(편집기 `data.floor`). 층 이름과 겹치지 않으면 된다 — 뷰를 처음 크기로 돌릴지
# 가르는 데 쓴다.
FAB_VIEW_LABEL = "S.PKG FAB"

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
        # FAB 층 블록의 기본 면(색 키를 고르지 않은 블록).
        "block": tokens.SPACE_BLOCK_FILL,
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
        # 도면 요소 이름표의 「글자 색」(`fontColor`). 편집기가 `var(--sle-mark-text-<키>)` 로 쓴다.
        **{f"mark-text-{key}": tokens.SPACE_MARK_TEXT_COLORS[key] for key in MARK_COLOR_KEYS},
    }


def _clean_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """브라우저로 보낼 호기. 숫자 아님은 None 으로, Main 설비는 글자일 때만 묶음으로."""
    return [
        {
            "id": str(item["id"]),
            "label": str(item.get("label", item["id"])),
            "stage": str(item.get("stage") or ""),
            "detail": str(item.get("detail") or ""),
            "x": finite_or_none(item.get("x")),
            "y": finite_or_none(item.get("y")),
            "w": finite_or_none(item.get("w")),
            "h": finite_or_none(item.get("h")),
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
            "fontSizes": list(MARK_FONT_SIZES),
            "backgroundImage": background_image,
            "floor": floor_label(floor),
            "floors": [],
            "newUnit": {},
        },
        on_apply_change=lambda: None,
        width="stretch",
    )


def _dispatch_navigate(key: str, epoch: str, on_open: Callable[[FloorKey], None]) -> None:
    """`on_navigate_change` 콜백. 누른 블록의 연결(「C1 1F」)이 FAB 의 층이면 연다.

    콜백은 인자가 없고 결과 객체도 아직 없다 — 값은 `st.session_state[key].navigate` 다. 연결이
    잘못됐으면 조용히 둔다(FAB 그대로). 뷰어를 그린 epoch 와 다른 값(도면이 다시 서기 전에 누른
    옛 블록)은 버린다 — 적용(`apply`)의 옛 epoch 거절과 같은 규칙이다."""
    state = st.session_state.get(key)
    payload = (
        state.get("navigate") if isinstance(state, Mapping) else getattr(state, "navigate", None)
    )
    if not isinstance(payload, Mapping) or payload.get("epoch") != epoch:
        return
    target = floor_from_label(payload.get("target"))
    if target is not None:
        on_open(target)


def render_fab_layout_viewer(
    *,
    key: str,
    epoch: str,
    canvas: CanvasSize,
    marks: Sequence[FabLayoutMark],
    link_stats: Mapping[str, Mapping[str, str | None]],
    summary: str,
    on_open: Callable[[FloorKey], None],
    background_image: str | None = None,
) -> None:
    """FAB 전체 **뷰어**. 층 도면과 같은 편집기의 보기 전용(`scope="fab"`)이다.

    누르면 열리는 것은 층 블록뿐이다(영역·글자는 꾸밈). 블록 글자의 대수(`link_stats`, 키는
    「C1 1F」)는 epoch 밖으로 따로 보낸다 — 같은 epoch 의 회차에는 블록 글자만 다시 쓴다. 블록을
    누르거나 Tab 으로 초점을 두고 Enter 를 누르면 `on_open((동, 층))` 이 콜백에서 돈다."""
    _EDITOR(
        key=key,
        data={
            "mode": "view",
            "scope": "fab",
            "epoch": epoch,
            "title": FAB_VIEW_LABEL,
            "summary": summary,
            "items": [],
            "marks": [mark.editor_payload() for mark in marks],
            "linkStats": {label: dict(stats) for label, stats in link_stats.items()},
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {"min": MIN_CANVAS_EXTENT, "max": MAX_CANVAS_EXTENT},
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "stageColors": dict(tokens.EQUIPMENT_STAGE_COLORS),
            "markColors": mark_colors(),
            "fontSizes": list(MARK_FONT_SIZES),
            "backgroundImage": background_image,
            "floor": FAB_VIEW_LABEL,
            "floors": [],
            "newUnit": {},
        },
        on_apply_change=lambda: None,
        on_navigate_change=partial(_dispatch_navigate, key, epoch, on_open),
        width="stretch",
    )


def render_fab_layout_editor(
    *,
    key: str,
    epoch: str,
    canvas: CanvasSize,
    marks: Sequence[FabLayoutMark],
    link_stats: Mapping[str, Mapping[str, str | None]],
    on_open: Callable[[FloorKey], None],
    background_image: str | None = None,
) -> EditorSubmission | None:
    """FAB 전체 **편집기**(`scope="fab"`). 층 편집기와 같은 컴포넌트이고 범위 표시로 나눈다.

    호기가 없어 트레이·호기 추가·다른 층 보내기·겹침 상태 줄이 없고, 팔레트는 영역·글자·동선·층
    블록이다(반입구·문·기둥은 층 도면 요소). 블록을 누르면 고르기이고(열지 않는다), 선택 칸에서 연결
    층(`linkTargets`, 30개 층)·색(기본 + 영역 색)을 고르며 [열기] 로 그 층을 연다 — 적용하지 않은
    편집이 있으면 잠긴다. 블록 대수(`link_stats`)는 보기와 같이 epoch 밖이다.

    `적용` 이 눌린 회차에만 받은 값(``{"epoch", "changes": [], "canvas", "marks"}``)을 돌려준다."""
    result = _EDITOR(
        key=key,
        data={
            "scope": "fab",
            "epoch": epoch,
            "title": FAB_VIEW_LABEL,
            "items": [],
            "marks": [mark.editor_payload() for mark in marks],
            "linkStats": {label: dict(stats) for label, stats in link_stats.items()},
            "linkTargets": [floor_label(target) for target in FLOOR_KEYS],
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {"min": MIN_CANVAS_EXTENT, "max": MAX_CANVAS_EXTENT},
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "stageColors": dict(tokens.EQUIPMENT_STAGE_COLORS),
            "markColors": mark_colors(),
            "fontSizes": list(MARK_FONT_SIZES),
            "backgroundImage": background_image,
            "floor": FAB_VIEW_LABEL,
            "floors": [],
            "newUnit": {},
        },
        on_apply_change=lambda: None,
        on_navigate_change=partial(_dispatch_navigate, key, epoch, on_open),
        width="stretch",
    )
    payload = getattr(result, "apply", None)
    if not isinstance(payload, Mapping):
        return None
    return EditorSubmission(payload=payload, stale=payload.get("epoch") != epoch)


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
      호기는 ``created`` 에 폼 값을 든다. 항목의 ``group``(Main 설비)이 같은 호기는 한 덩어리로
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
                "reservedW": finite_or_none(inputs.reserved_extent[0]) or 0.0,
                "reservedH": finite_or_none(inputs.reserved_extent[1]) or 0.0,
            },
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "stageColors": dict(tokens.EQUIPMENT_STAGE_COLORS),
            "markColors": mark_colors(),
            "fontSizes": list(MARK_FONT_SIZES),
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
