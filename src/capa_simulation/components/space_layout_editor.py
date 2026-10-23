# Purpose: Space 층·FAB 도면의 Components v2 편집기(끌어 놓아 배치 고치기)와 보기 전용 뷰어.

"""드래그앤드롭 배치 편집기. 같은 도면의 보기 전용 층 상세 뷰어(`mode="view"`)와 FAB 전체 도면
(`scope="fab"`, 보기 전용 뷰어와 편집기)도 이것이다 — 컴포넌트는 하나만 등록하고 범위 표시로 나눈다.

좌표 계약은 설비 마스터와 같다: 원점은 **왼쪽 아래**, Y 는 위로 커지고
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

**기준일 페이더**(층 상세 보기, 도면 상자 맨 위 줄)도 브라우저 몫이다. 끄는 동안에는 파이썬으로
아무것도 보내지 않고 브라우저가 호기마다 받은 경계 날짜를 글자로 견주어 class·면색만 바꾼다. 손을
떼면 상태 값 `asOf`(`YYYY-MM-DD`)를 **한 번** 보내고(`setStateValue`), 받는 쪽 `on_asOf_change`
콜백이 세션 기준일을 바꿔 그 회차에 범례·요약·호기 표가 맞춰진다. 기준일은 epoch 에 넣지 않는다 —
data 의 `asOf` 는 새 epoch(층 이동 등)에서 쓰고, 같은 epoch 회차에 받은 값이 브라우저가 쥔 값과
같으면 아무것도 다시 칠하지 않는다. FAB 전체 뷰어는 페이더 없이 도구 줄에 기준일과 「오늘로」를,
배치 편집기는 같은 자리에 「편집 중 고정」 줄을 둔다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

import streamlit as st

from capa_simulation.components.space_layout import block_tints, keep_out_color, mark_colors
from capa_simulation.design import tokens
from capa_simulation.services.fab_layout import (
    FLOOR_KEYS,
    FabLayoutMark,
    floor_from_label,
    floor_label,
)
from capa_simulation.services.floor_layout_mark import (
    GROUP_LABEL_POSITIONS,
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
        # 호기 상자의 기본 면·글자와 보관·지연 면·글자. 색 기준 그룹 면은 호기마다
        # data(`fill`·`ink`)로 온다.
        "unit-default-fill": tokens.SPACE_UNIT_DEFAULT_FILL,
        "unit-default-ink": tokens.SPACE_UNIT_DEFAULT_INK,
        "unit-storage-fill": tokens.SPACE_UNIT_STORAGE_FILL,
        "unit-storage-ink": tokens.SPACE_UNIT_STORAGE_INK,
        "unit-delay-fill": tokens.SPACE_UNIT_DELAY_FILL,
        "unit-delay-ink": tokens.SPACE_UNIT_DELAY_INK,
        # 보기 화면의 테(반입 전·반출/이설 예정)·선택 후광·미확인 「!」·정지 중 빗금.
        "ring-pre": tokens.SPACE_RING_PRE_ARRIVAL,
        "ring-exit": tokens.SPACE_RING_EXIT,
        "ring-exit-outline": tokens.SPACE_RING_EXIT_OUTLINE,
        "ring-halo": tokens.SPACE_RING_HALO,
        "flag": tokens.SPACE_FLAG_FILL,
        "flag-ink": tokens.SPACE_FLAG_INK,
        "hatch": tokens.SPACE_HATCH,
        # 배치 편집기 정렬선·놓을 자리 미리 보기.
        "guide": tokens.SPACE_GUIDE,
        "mark-ink": tokens.SPACE_TEXT,
        "mark-muted": tokens.SPACE_LABEL_TEXT,
        # 도면 요소 이름표의 「글자 색」(`fontColor`). 편집기가 `var(--sle-mark-text-<키>)` 로 쓴다.
        **{f"mark-text-{key}": tokens.SPACE_MARK_TEXT_COLORS[key] for key in MARK_COLOR_KEYS},
        # 색을 고른 FAB 층 블록의 불투명 면. 편집기가 `var(--sle-block-tint-<키>)` 로 쓴다.
        **{f"block-tint-{key}": tint for key, tint in block_tints().items()},
    }


_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _day_or_none(value: object) -> str | None:
    """`YYYY-MM-DD` 글자만, 아니면 None. 브라우저가 기준일과 글자로 견준다."""
    return value if isinstance(value, str) and _DAY.match(value) else None


def _spans(value: object) -> list[list[str | None]]:
    """``[[시작, 끝 | None], …]`` — 시작이 날짜 글자인 구간만 남긴다."""
    if not isinstance(value, (list, tuple)):
        return []
    return [
        [str(span[0]), _day_or_none(span[1])]
        for span in value
        if isinstance(span, (list, tuple)) and len(span) == 2 and _day_or_none(span[0])
    ]


def _clean_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """브라우저로 보낼 호기. 숫자 아님은 None 으로, Main 설비는 글자일 때만 묶음으로.

    색 기준의 면·글자(`fill`·`ink`, `#RRGGBB` 만 — 아니면 빈 글자라 브라우저가 기본 회색)와 경계
    날짜(`realFrom`·`exitOn`·`stopOn`·`delays`·`offline`,
    `services/space_unit_state.boundary_payload`)· `storage`·`flag` 도 여기를 지난다. 이름에
    `group`(Main 설비 묶음)·`arrived`(다른 층에서 옴)는 이미 쓰인다.
    """
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
            "fill": item["fill"]
            if isinstance(item.get("fill"), str) and _HEX.match(item["fill"])
            else "",
            "ink": item["ink"]
            if isinstance(item.get("ink"), str) and _HEX.match(item["ink"])
            else "",
            "storage": bool(item.get("storage")),
            "realFrom": _day_or_none(item.get("realFrom")),
            "exitOn": _day_or_none(item.get("exitOn")),
            "stopOn": _day_or_none(item.get("stopOn")),
            "delays": _spans(item.get("delays")),
            "offline": _spans(item.get("offline")),
            "flag": bool(item.get("flag")),
        }
        for item in items
    ]


def _clean_ghosts(ghosts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """브라우저로 보낼 숨은 모듈(`EditorInputs.ghosts`). 상자 넷이 다 숫자이고 Main 설비가 글자인
    것만 — 그리지 않고 묶음 바둑판의 칸만 차지한다."""
    cleaned: list[dict[str, Any]] = []
    for ghost in ghosts:
        box = [finite_or_none(ghost.get(key)) for key in ("x", "y", "w", "h")]
        group = ghost.get("group")
        if any(value is None for value in box) or not isinstance(group, str) or not group:
            continue
        x, y, w, h = box
        cleaned.append({"id": str(ghost["id"]), "group": group, "x": x, "y": y, "w": w, "h": h})
    return cleaned


def _clean_group_labels(labels: Mapping[str, str] | None) -> dict[str, str]:
    """브라우저로 보낼 Main 설비명 위치(Main 설비 → 위·아래). 가운데(기본)와 모르는 값은 뺀다 —
    브라우저는 없는 묶음을 가운데로 그린다."""
    return {
        str(name): position
        for name, position in (labels or {}).items()
        if position in GROUP_LABEL_POSITIONS[1:]
    }


def _dispatch_as_of(key: str, on_as_of: Callable[[date], None]) -> None:
    """`on_asOf_change` 콜백. 페이더를 놓거나 「오늘로」를 누를 때 브라우저가 보낸 기준일
    (`YYYY-MM-DD`)을 `on_as_of(date)` 로 넘긴다. 콜백은 본문보다 먼저 돌아 그 회차의 범례·요약이 새
    기준일이다. 날짜 글자가 아니면(없는 날 포함) 조용히 버린다."""
    state = st.session_state.get(key)
    raw = state.get("asOf") if isinstance(state, Mapping) else getattr(state, "asOf", None)
    day = _day_or_none(raw)
    if day is None:
        return
    try:
        chosen = date.fromisoformat(day)
    except ValueError:
        return
    on_as_of(chosen)


def _as_of_fields(as_of: date, today: date, as_of_range: tuple[date, date]) -> dict[str, str]:
    """data 의 기준일 칸 — 기준일·오늘·페이더 범위(양 끝 포함). 범위는 파이썬
    (`space_unit_state.as_of_range`)이 정해 보낸다 — 날짜 계산을 한 곳에 둔다."""
    return {
        "asOf": as_of.isoformat(),
        "today": today.isoformat(),
        "asOfMin": as_of_range[0].isoformat(),
        "asOfMax": as_of_range[1].isoformat(),
    }


def render_space_layout_viewer(
    *,
    key: str,
    epoch: str,
    items: Sequence[Mapping[str, Any]],
    canvas: CanvasSize,
    floor: FloorKey,
    marks: Sequence[FloorLayoutMark],
    summary: str,
    as_of: date,
    today: date,
    as_of_range: tuple[date, date],
    on_as_of: Callable[[date], None],
    background_image: str | None = None,
    group_labels: Mapping[str, str] | None = None,
) -> None:
    """층 상세 **뷰어**. 편집기와 같은 도면을 보기 전용으로 그린다 — 편집 도구가 없고, 끌기는
    화면 이동, 누르기는 그 호기 정보 한 줄, Ctrl+휠·+/−·더블클릭은 확대다. `summary` 는 도구 줄
    오른쪽의 한 줄 요약(배치·미배치·점유율)이다. 돌려받는 값이 없다.

    도면 상자 맨 위 줄은 **기준일 페이더**다(오늘 ± 12개월 = `as_of_range`, 하루 단위). 끄는 동안은
    브라우저가 호기마다 받은 경계 날짜와 글자로 견주어 테(반입 전 주황 점선·반출/이설 예정 노랑)·
    빗금·「!」·운영 비가동 표식·지연 빨강·숨김을 바꾸고, 놓으면 `asOf` 를 한 번 보내
    `on_as_of(date)` 가 콜백에서 돈다. `items` 는 범위 어딘가에서 도면에 서는 호기의 합집합이어야
    한다(`space_unit_state.drawn_in_range`) — 기준일에 따라 목록이 달라지면 epoch 가 바뀌어 다시
    선다.
    `as_of`(세션 기준일)는 epoch 에 넣지 않는다 — 기준일·체크만 바뀐 회차는 같은 epoch 로 바뀐 것만
    다시 칠하고 보던 배율을 지킨다.

    Main 설비 모듈 묶음(모듈 둘 이상)은 묶음 범위에 Main 설비명을 그린다 — 위치는 `group_labels`
    (Main 설비 → 위·아래, 없으면 가운데)이고, 기준일에 묶음의 모듈이 하나도 보이지 않으면 이름도
    숨는다."""
    _EDITOR(
        key=key,
        data={
            "mode": "view",
            "scope": "floor",
            "epoch": epoch,
            **_as_of_fields(as_of, today, as_of_range),
            "title": floor_label(floor),
            "summary": summary,
            "items": _clean_items(items),
            "marks": [mark.editor_payload() for mark in marks],
            "groupLabels": _clean_group_labels(group_labels),
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {"min": MIN_CANVAS_EXTENT, "max": MAX_CANVAS_EXTENT},
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "markColors": mark_colors(),
            "fontSizes": list(MARK_FONT_SIZES),
            "backgroundImage": background_image,
            "floor": floor_label(floor),
            "floors": [],
            "newUnit": {},
        },
        on_apply_change=lambda: None,
        on_asOf_change=partial(_dispatch_as_of, key, on_as_of),
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
    as_of: date,
    today: date,
    as_of_range: tuple[date, date],
    unconfirmed: int,
    on_as_of: Callable[[date], None],
    background_image: str | None = None,
) -> None:
    """FAB 전체 **뷰어**. 층 도면과 같은 편집기의 보기 전용(`scope="fab"`)이다.

    누르면 열리는 것은 층 블록뿐이다(영역·글자는 꾸밈). 블록 글자의 대수(`link_stats`, 키는
    「C1 1F」)는 epoch 밖으로 따로 보낸다 — 같은 epoch 의 회차에는 블록 글자만 다시 쓴다. 블록을
    누르거나 Tab 으로 초점을 두고 Enter 를 누르면 `on_open((동, 층))` 이 콜백에서 돈다.

    FAB 에는 페이더가 없다. 도구 줄 요약 앞에 「기준일 YYYY-MM-DD」(블록 대수의 기준일)와, 오늘이
    아니면 「오늘로」 단추(누르면 `asOf` = 오늘 → `on_as_of`), 그리고 `unconfirmed`(오늘 기준 미확인
    설비 수)가 0 보다 크면 「! 미확인 N대」를 단다. 기준일·대수는 epoch 밖이다."""
    _EDITOR(
        key=key,
        data={
            "mode": "view",
            "scope": "fab",
            "epoch": epoch,
            **_as_of_fields(as_of, today, as_of_range),
            "unconfirmed": max(int(unconfirmed), 0),
            "title": FAB_VIEW_LABEL,
            "summary": summary,
            "items": [],
            "marks": [mark.editor_payload() for mark in marks],
            "linkStats": {label: dict(stats) for label, stats in link_stats.items()},
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {"min": MIN_CANVAS_EXTENT, "max": MAX_CANVAS_EXTENT},
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "markColors": mark_colors(),
            "fontSizes": list(MARK_FONT_SIZES),
            "backgroundImage": background_image,
            "floor": FAB_VIEW_LABEL,
            "floors": [],
            "newUnit": {},
        },
        on_apply_change=lambda: None,
        on_navigate_change=partial(_dispatch_navigate, key, epoch, on_open),
        on_asOf_change=partial(_dispatch_as_of, key, on_as_of),
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
    as_of: date,
    background_image: str | None = None,
    group_labels: Mapping[str, str] | None = None,
) -> EditorSubmission | None:
    """편집기를 그리고 `적용` 이 눌린 회차에만 받은 값을 돌려준다(검증 전 원본).

    면은 보기와 같은 규칙(지연 → 보관 → 체크한 그룹 → 기본, 기준일 `as_of`)이지만 **의미 테·덧표시는
    그리지 않는다** — 편집 화면의 테는 선택·묶음·다른 층·겹침 전용이다. 기준일은 편집 중 고정이다 —
    페이더 자리에 같은 높이의 「기준일 YYYY-MM-DD · 편집 중 고정」 줄이 선다(기준일이 바뀌면 편집
    대상 호기가 바뀌어 적용하지 않은 편집이 버려진다).

    적용값: ``{"epoch", "changes", "ghosts", "renames", "canvas", "marks", "groupLabels"}``.

    - ``changes``: 바뀐 호기(배치). ``id`` 는 편집기에 보낸 **옛** 설비명이다. 놓인 호기는
      좌표·크기, 트레이로 뺀 호기는 크기만(있으면) 든다. 다른 층으로 보낸 호기는 ``moveTo`` 에 그
      층 이름(「C2 2F」)을 단다. 편집기에서 새로 넣은 호기는 ``created`` 에 폼 값을 들고 ``id`` 가
      지금 이름이다(적용 전에 이름을 고쳐도 이름 바꿈이 아니라 그 이름의 새 호기다). 항목의
      ``group``(Main 설비)이 같은 호기는 한 덩어리로 움직인다. 모듈이 둘 이상인 묶음은 묶음 범위만
      고치고 안의 모듈은 범위를 바둑판으로 똑같이 나눈 칸에 선다(모듈 하나만 옮기거나 키우는 길이
      없다) — 놓이거나 자리·크기가 바뀐 묶음은 `parse_editor_apply` 가 같은 규칙
      (`space_layout_edit.module_cells`·`assign_module_cells`)으로 견줘 한 눈금 안이면 바로잡고 더
      어긋나면 거부한다.
    - ``ghosts``: 묶음과 함께 옮겨진 숨은 모듈(`EditorInputs.ghosts` — 도면 대상이 아니라 그리지
      않지만 묶음 바둑판의 칸을 차지한다)의 새 자리 ``[{"id", "x", "y", "w", "h"}]``.
    - ``renames``: 선택 칸 `이름` 으로 바꾼 이름(배치와 따로 — 이름만 바꾸면 ``changes`` 가 비어
      있다). ``[{"kind": "unit", "from": 옛 설비명, "to": 새 설비명}]`` 과 모듈 묶음이면
      ``[{"kind": "group", "from": 옛 Main 설비, "to": 새 Main 설비}]``(묶음 하나에 한 항목,
      편집기에 없는 형제 행까지 바뀐다). 자기 설비명을 Main 설비로 적은 한 행짜리 묶음은 ``unit``
      한 항목이고 Main 설비가 따라간다. 이름 바꿈은 표시 별칭이 아니라 설비 마스터의 설비명
      자체다(2026-10-08 사용자 결정) — 검증·반영은 `services/space_layout_edit` 의
      `parse_editor_apply`·`apply_name_changes` 다.
    - ``canvas``: 편집 영역을 바꿨을 때만 ``{width, height}``.
    - ``marks``: 도면 요소를 바꿨을 때만 이 층 요소 전체 목록, 아니면 None.
    - ``groupLabels``: 이 층에 남는 모듈 묶음마다의 Main 설비명 위치
      ``[{"group": 옛 Main 설비, "position": "center"|"top"|"bottom"}]``(다른 층으로 보낸 묶음은
      빠진다). 처음 위치는 `group_labels`(Main 설비 → 위·아래, 없으면 가운데)이고 층 위치 목록으로
      합치는 것은 `space_layout_edit.next_group_labels` 다.
    """
    items = _clean_items(inputs.items)
    result = _EDITOR(
        key=key,
        data={
            "scope": "floor",
            "epoch": epoch,
            "asOf": as_of.isoformat(),
            "title": title,
            "items": items,
            "ghosts": _clean_ghosts(inputs.ghosts),
            "marks": [mark.editor_payload() for mark in marks],
            "groupLabels": _clean_group_labels(group_labels),
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {
                "min": MIN_CANVAS_EXTENT,
                "max": MAX_CANVAS_EXTENT,
                "reservedW": finite_or_none(inputs.reserved_extent[0]) or 0.0,
                "reservedH": finite_or_none(inputs.reserved_extent[1]) or 0.0,
            },
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
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
