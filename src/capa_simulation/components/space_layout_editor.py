# Purpose: Space 층·FAB 도면의 Components v2 편집기(끌어 놓아 배치 고치기)와 보기 전용 뷰어.

"""드래그앤드롭 배치 편집기. 같은 도면의 보기 전용 층 상세 뷰어(`mode="view"`)와 FAB 전체 도면
(`scope="fab"`, 보기 전용 뷰어와 편집기)도 이것이다 — 컴포넌트는 하나만 등록하고 범위 표시로 나눈다.

좌표 계약은 설비 마스터와 같다: 원점은 **왼쪽 아래**, Y 는 위로 커지고
호기 사각형은 (X좌표, Y좌표) → (X좌표+Xsize, Y좌표+Ysize) 다. SVG 는 위가 0 이라
화면 y = 캔버스 높이 − (Y좌표 + Ysize) 로 바꿔 그린다.

편집 상태는 **브라우저에 둔다.** 끌고 키우는 동안에는 파이썬으로 아무것도 보내지 않는다(Streamlit
은 값을 받을 때마다 페이지를 다시 돌린다). `적용` 을 누를 때 바뀐 호기·새로 넣은 호기·캔버스
크기·도면 요소를 한 번에 보낸다. 같은 `epoch` 로 다시 그려지는 회차(다른 위젯을 건드린 경우)에는
진행 중인 편집과 확대 배율을 그대로 두고 단계 색·라벨만 다시 칠한다. epoch 는 층·저장본·편집본
세대로 만들어, 편집본이 바뀌면(적용·설비 마스터 탭 제출·저장) 브라우저가 새 값으로 다시 선다.

뷰어 크기도 브라우저 몫이다. 무대 폭은 열을 채우고, 높이는 화면에 맞춘 기본값이거나 무대 아래
손잡이로 고른 값이다. 고른 높이는 브라우저(localStorage)에 범위(`scope`)별로 기억하고 파이썬으로
보내지 않는다 — 보내면 페이지가 다시 돈다. 같은 까닭으로 epoch 에도 넣지 않는다.

HTML·CSS·JS 는 `space_layout_editor_assets/` 의 파일이다(파이썬 문자열에 넣으면 줄 길이 검사와
이스케이프가 JS 를 망가뜨린다). 색은 등록 시점 CSS 에 적지 않고 회차마다 `data.palette` 로 넘긴다 —
`st.components.v2.component` 는 등록 때의 CSS 를 그대로 쓰므로 테마를 바꿔도 따라오지 않는다.
받은 적용값의 검증은 `services/space_layout_edit.parse_editor_apply` 가 맡는다. 「+ 호기 추가」 의
일정 칸은 앱의 날짜 칸과 같은 판이다 — `components/date_panel` 의 조각 · 서식 · 세우는 함수를 등록
때 함께 싣고(`DATE_PANEL_SLOT`) 값은 편집기 상태에 머문다.

FAB 도면의 층 블록을 누르면(또는 초점을 두고 Enter) 브라우저가 `navigate` 를 보낸다. 받는 쪽은
`on_navigate_change` 콜백이다 — 콜백은 본문보다 먼저 돌므로 그 자리에서 층을 바꾸면 재실행 한
번으로 층 상세가 선다(콜백 안에서 `st.session_state[key].navigate` 로 읽힌다). 층 상세 뷰어에서
호기를 누르면 같은 꼴로 `pick` 을 보내고 `on_pick_change` 콜백이 받는다(색 기준 「필요 단축」 을 켠
동안만 — 그 칸의 누른 호기 상세).

**「호기 정보」 창**(층 보기·편집, 2026-11-03 사용자 요청)도 브라우저 몫이다 — 도면 위에 뜨는 창에
고른 호기의 칸(`space_layout.FLOOR_TABLE_COLUMNS` 21칸)과, 칸마다 엑셀 자동 필터 꼴로 거른 호기
목록을 보이고 맞는 호기를 도면에서 강조한다. 표 재료는 data `sheet`(epoch 밖)이고 거르기·강조는
JS(`// <unit-sheet>`)라 필터를 고쳐도 앱이 다시 돌지 않는다. 창 자리·크기·접힘은 localStorage,
탭·필터·강조는 sessionStorage 다. 창 줄을 눌러 고른 것이 바뀌거나 사람이 걸러 맞는 호기가
바뀌면(이 층 도면에 보이는 맞음 5대 이하 — 묶음은 1대) 그 테에 알림 칸과 같은 시선 끌기를 한 번
건다(설계 규칙 UI-NAV-02 — 대상 판정은 `// <attract-pick>`). 시간 · 곡선은 data `attention`
(`alerts.attention_payload` — 알림 칸 `limits` 와 같은 사전)이다.

**기준일 페이더**(층 상세 보기, 도면 상자 맨 위 줄)도 브라우저 몫이다. 끄는 동안에는 파이썬으로
아무것도 보내지 않고 브라우저가 호기마다 받은 경계 날짜를 글자로 견주어 class·면색만 바꾼다. 손을
떼면 상태 값 `asOf`(`YYYY-MM-DD`)를 **한 번** 보내고(`setStateValue`), 받는 쪽 `on_asOf_change`
콜백이 세션 기준일을 바꿔 그 회차에 범례·요약·「호기 정보」 창이 맞춰진다. 기준일은 epoch 에 넣지
않는다 — data 의 `asOf` 는 새 epoch(층 이동 등)에서 쓰고, 같은 epoch 회차에 받은 값이 브라우저가 쥔
값과 같으면 아무것도 다시 칠하지 않는다. FAB 전체 뷰어는 페이더 없이 도구 줄에 기준일과
「오늘로」를, 배치 편집기는 도구 줄 제목 옆에 「YYYY-MM-DD 고정」 칩(핀 아이콘)을 둔다.

**편집기 몸은 가로 세 칸**이다(2026-11-03 사용자 요청) — 왼쪽 칸(층 보기는 범례, 편집은 범례·도면
요소·선택·서식·격자·캔버스) · 무대 · 오른쪽 미배치 칸(층 편집). 두 칸의 폭·접힘은
브라우저(localStorage)에만 둔다. 범례는 data `legend` (epoch 밖)로 보낸다. 도구 줄 「화면 고정」은
`<html data-space-lock>` 을 달고, 그 속성을 읽는 규칙은 페이지가 그리는 `space_lock_style()`
이다.

도면 요소의 **모양 값**(`marks[].look` — 동선·베이의 화살표 머리 크기·선·뒤집기, 발자국의
발 모양·간격·선 색·뒤집기, 도형의 프리셋·모양 조절·채우기 투명도·선·뒤집기, 설비 `0033`)은
처음 값이 아닌 것이 있을 때만 실려 오고 적용값에도 같은
키로 돌아간다(검증은 `floor_layout_mark.mark_look`). 도형(`kind="shape"`, 층·FAB)의 채우기 색은
요소의 `color`(영역 색 여섯 + `ink`·`surface`)다. 도면에 붙은 글자는 배율을 따라 커지고
작아진다(편집기 `// <text-scale>` — 고른 글자 크기 `fontSizes` 는 도면 1칸이 화면 8px 일 때의 크기).
둘 다 브라우저 몫이라 data 에 새 칸은 없다.
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

from capa_simulation import alerts
from capa_simulation.components.date_panel import (
    DATE_PANEL_CSS,
    DATE_PANEL_HTML,
    DATE_PANEL_MOUNT_JS,
)
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
from capa_simulation.services.space_shortening_layer import BUCKETS
from capa_simulation.services.space_unit_sheet import MAX_SHEET_ROWS, SHEET_TYPES

_ASSETS = Path(__file__).with_name("space_layout_editor_assets")
# FAB 도면의 범위 이름(편집기 `data.floor`). 층 이름과 겹치지 않으면 된다 — 뷰를 처음 크기로 돌릴지
# 가르는 데 쓴다.
FAB_VIEW_LABEL = "S.PKG FAB"
# FAB 도면의 도구 줄 제목(편집기 `data.title`). 층은 「C1 1F」 다 — 도면 위에는 머리 줄이 없어
# (2026-11-03 사용자 요청 — 여백 걷기) 지금 무엇을 보는지는 도구 줄 제목이 말한다.
FAB_TITLE = "S.PKG FAB 전체"
# 범례 칸 수의 상한(층 상세 범례는 열 칸 남짓 — 망가진 값만 거른다).
_LEGEND_LIMIT = 40
# 화면 고정(편집기 도구 줄 「화면 고정」)이 `<html>` 에 다는 속성. 그 속성을 읽는 규칙은 페이지 서식
# (`space_lock_style`)에 둔다 — 다른 화면으로 가면 그 서식이 사라져 정리 함수가 돌지 않아도
# 풀린다(AGENTS 9장 「브라우저 전용 보기 상태」).
SPACE_LOCK_ATTRIBUTE = "data-space-lock"

# 「+ 호기 추가」 의 날짜 칸 자리 — 앱의 날짜 칸과 같은 조각을 그대로 넣는다(설계 규칙 UI-INP-03).
DATE_PANEL_SLOT = "<!-- capa-date-panel -->"
_EDITOR = st.components.v2.component(
    "capa_space_layout_editor",
    html=(_ASSETS / "editor.html")
    .read_text(encoding="utf-8")
    .replace(DATE_PANEL_SLOT, DATE_PANEL_HTML),
    css=DATE_PANEL_CSS + (_ASSETS / "editor.css").read_text(encoding="utf-8"),
    js=DATE_PANEL_MOUNT_JS + (_ASSETS / "editor.js").read_text(encoding="utf-8"),
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
        "frame": tokens.SPACE_BORDER,
        "grid": tokens.SPACE_GRID,
        "grid-major": tokens.BORDER_STRONG,
        "border": tokens.BORDER,
        "border-strong": tokens.BORDER_STRONG,
        "surface": tokens.SURFACE,
        # FAB 층 블록의 기본 면(색 키를 고르지 않은 블록).
        "block": tokens.SPACE_BLOCK_FILL,
        # 비활성 층 블록의 면 — 위에 영역 빗금과 흐린 사유 글자(직접 적은 사유, 길면 줄임).
        "block-off": tokens.SPACE_BLOCK_OFF_FILL,
        # 무대 바탕 — 캔버스 둘레의 여백이 이 색이다.
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
        # 도형의 노란 모양 조절 손잡이(테는 `text` — 도면 글자색).
        "adjust": tokens.SPACE_ADJUST,
        "mark-ink": tokens.SPACE_TEXT,
        "mark-muted": tokens.SPACE_LABEL_TEXT,
        # 도면 요소 이름표의 「글자 색」(`fontColor`). 편집기가 `var(--sle-mark-text-<키>)` 로 쓴다.
        **{f"mark-text-{key}": tokens.SPACE_MARK_TEXT_COLORS[key] for key in MARK_COLOR_KEYS},
        # 색을 고른 FAB 층 블록의 불투명 면. 편집기가 `var(--sle-block-tint-<키>)` 로 쓴다.
        **{f"block-tint-{key}": tint for key, tint in block_tints().items()},
        # 색 기준 「필요 단축」 의 구간 면·글자(`var(--sle-short-<구간>-fill|ink)`)·임박 테·흐림
        # 정도. 끈 동안에도 싣는다(작은 값 몇 개) — CSS 의 `--sle-*` 는 모두 이 팔레트에 있어야
        # 한다.
        **{f"short-{key}-fill": fill for key, fill in tokens.SPACE_SHORT_FILLS.items()},
        **{f"short-{key}-ink": ink for key, ink in tokens.SPACE_SHORT_INKS.items()},
        "short-imminent": tokens.SPACE_SHORT_IMMINENT,
        "short-dim-opacity": tokens.SPACE_SHORT_DIM_OPACITY,
        # 「호기 정보」 창 필터에 맞는 호기의 테와 맞지 않는 호기의 흐림(필요 단축 흐림과 곱해진다).
        "filter-ring": tokens.SPACE_FILTER_RING,
        "filter-dim-opacity": tokens.SPACE_FILTER_DIM_OPACITY,
        # 배치 편집 「호기 정보」 창 칸 고치기 — 설비 마스터 표의 바뀐 칸 · 막힌 칸 · 잠긴 칸과 같은
        # 색(UI-CON-03).
        "cell-changed-fill": tokens.GRID_CHANGED_FILL,
        "cell-changed-mark": tokens.GRID_CHANGED_MARK,
        "cell-error-fill": tokens.GRID_ERROR_FILL,
        "cell-error-line": tokens.GRID_ERROR_LINE,
        "cell-lock-fill": tokens.GRID_LOCK_FILL,
    }


_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# 「필요 단축」 구간 이름(`services/space_shortening_layer.BUCKETS`).
_LAYER_BUCKETS = frozenset(BUCKETS)


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


def _share_or_one(value: object) -> float:
    """설비지분(`share`) — 0 이상의 유한한 수만(일부 모듈만 반입한 Main 설비의 반입 전 모듈은
    0), 아니면 한 대(1)."""
    number = finite_or_none(value)
    return number if number is not None and number >= 0 else 1.0


def _clean_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """브라우저로 보낼 호기. 숫자 아님은 None 으로, Main 설비는 글자일 때만 묶음으로.

    색 기준의 면·글자(`fill`·`ink`, `#RRGGBB` 만 — 아니면 빈 글자라 브라우저가 기본 회색)와 경계
    날짜(`realFrom`·`exitOn`·`stopOn`·`delays`·`offline`,
    `services/space_unit_state.boundary_payload`)· `storage`·`flag`·반입 일정(`arrivalPlan` —
    날짜 글자 또는 None, `arrivalDelayed`) 도 여기를 지난다. 이름에
    `group`(Main 설비 묶음)·`arrived`(다른 층에서 옴)는 이미 쓰인다. `share` 는 기준일
    설비지분(모듈 행 넷이 모두 반입했으면 0.25, 없으면 1 — 범례와 같은 칸)이고 층 상세 보기
    요약의 「겹쳐 숨긴 반입 예정 n대」를 설비 대수로 센다.

    색 기준 「필요 단축」 을 켠 층 보기는 `layer`(구간 `s|m|l|x` — 표시된 호기)·`dim`(흐릴 호기)을
    싣는다. **값이 있을 때만 키를 싣는다** — 끈 동안 payload 가 그 전과 같다.
    """
    return [_clean_item(item) for item in items]


def _clean_item(item: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = {
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
        "group": item["group"] if isinstance(item.get("group"), str) and item["group"] else None,
        "fill": item["fill"]
        if isinstance(item.get("fill"), str) and _HEX.match(item["fill"])
        else "",
        "ink": item["ink"] if isinstance(item.get("ink"), str) and _HEX.match(item["ink"]) else "",
        "storage": bool(item.get("storage")),
        "realFrom": _day_or_none(item.get("realFrom")),
        "exitOn": _day_or_none(item.get("exitOn")),
        "stopOn": _day_or_none(item.get("stopOn")),
        "delays": _spans(item.get("delays")),
        "offline": _spans(item.get("offline")),
        "flag": bool(item.get("flag")),
        "share": _share_or_one(item.get("share")),
        "arrivalPlan": _day_or_none(item.get("arrivalPlan")),
        "arrivalDelayed": bool(item.get("arrivalDelayed")),
    }
    if item.get("layer") in _LAYER_BUCKETS:
        cleaned["layer"] = str(item["layer"])
    if item.get("dim") is True:
        cleaned["dim"] = True
    return cleaned


def _clean_badges(badges: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """브라우저로 보낼 「필요 단축」 배지 — 설비키마다 하나(`space_shortening_layer.floor_layer`).
    `ids` 는 그 층에 그린 모듈 설비명 글자 목록(빈 배지는 버린다), 구간은 `s|m|l|x` 만."""
    cleaned: list[dict[str, Any]] = []
    for badge in badges:
        ids = [str(value) for value in badge.get("ids") or () if isinstance(value, str) and value]
        bucket = badge.get("bucket")
        if not ids or bucket not in _LAYER_BUCKETS:
            continue
        cleaned.append(
            {
                "key": str(badge.get("key") or ids[0]),
                "ids": ids,
                "main": str(badge.get("main") or ""),
                "sub": str(badge.get("sub") or ""),
                "bucket": str(bucket),
                "imminent": bool(badge.get("imminent")),
                "dim": bool(badge.get("dim")),
                "tip": str(badge.get("tip") or ""),
                "aria": str(badge.get("aria") or ""),
            }
        )
    return cleaned


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


def _clean_compare(compare: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """브라우저로 보낼 「공식과 견주기」 재료(`space_floor_layout.compare_payload`). 점선 상자는
    넷이 다 숫자인 것만, 꼬리표는 글자일 때만. 둘 다 비면 None(견주기 층을 비운다)."""
    if not compare:
        return None
    ghosts: list[dict[str, Any]] = []
    for ghost in compare.get("ghosts") or ():
        box = [finite_or_none(ghost.get(key)) for key in ("x", "y", "w", "h")]
        if any(value is None for value in box):
            continue
        tag = ghost.get("tag")
        x, y, w, h = box
        ghosts.append(
            {
                "id": str(ghost["id"]),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "tag": tag if isinstance(tag, str) and tag else None,
            }
        )
    arrivals = [
        {"id": str(arrival["id"]), "tag": arrival["tag"]}
        for arrival in compare.get("arrivals") or ()
        if isinstance(arrival.get("tag"), str) and arrival["tag"]
    ]
    if not ghosts and not arrivals:
        return None
    return {"ghosts": ghosts, "arrivals": arrivals}


def _clean_group_labels(labels: Mapping[str, str] | None) -> dict[str, str]:
    """브라우저로 보낼 Main 설비명 위치(Main 설비 → 가운데·위·아래). 모르는 값은 뺀다 — 브라우저는
    없는 묶음을 그 모양의 처음 위치(한 줄 묶음은 위, 그 밖은 가운데 — `groupLabelDefault`)로
    그린다."""
    return {
        str(name): position
        for name, position in (labels or {}).items()
        if position in GROUP_LABEL_POSITIONS
    }


def _clean_legend(legend: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """브라우저로 보낼 범례(편집기 왼쪽 칸 「범례」) — `{"entries": [{label, css, inner}], "asOf":
    글}`.

    칸은 `space_layout.space_legend_entries`·`shortening_legend_entries` 꼴이고 셋 다 글자일 때만
    싣는다. 편집기는 `css` 를 `style.cssText`, 글을 `textContent` 로만 단다(HTML 로 읽지 않는다).
    epoch 밖이다 — 기준일·체크·색 기준이 바뀌어도 다시 마운트하지 않고 범례만 다시 쓴다. None 이면
    범례 묶음이 없다(FAB)."""
    if legend is None:
        return None
    entries = [
        {"label": entry["label"], "css": entry["css"], "inner": entry["inner"]}
        for entry in legend.get("entries") or ()
        if isinstance(entry, Mapping)
        and all(isinstance(entry.get(name), str) for name in ("label", "css", "inner"))
    ][:_LEGEND_LIMIT]
    as_of = legend.get("asOf")
    return {"entries": entries, "asOf": as_of if isinstance(as_of, str) else ""}


def _sheet_cell(value: object) -> str | float | None:
    """창 표의 칸 값 — 글·유한한 수·None 만(그 밖은 None). 참·거짓은 글로."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None
    return value if isinstance(value, str) else None


def _clean_sheet(sheet: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """브라우저로 보낼 「호기 정보」 창 표(`services/space_unit_sheet.unit_sheet` 꼴).

    칸은 이름이 글이고 꼴이 `SHEET_TYPES` 인 것만, 행은 id 가 빈 글이 아니고 칸 수가 칸 목록과 같은
    것만 싣는다(값은 `_sheet_cell`). 줄 수는 `MAX_SHEET_ROWS` 를 넘지 않는다(넘친 수는 `cut` 에
    더한다). 창 「CSV」 의 도면에 선 호기 글(`csv` — `space_unit_sheet.floor_csv` 꼴 {text,
    file})은 둘 다 글일 때만 싣는다. epoch 밖이다 — 기준일(「단계」 칸)·공정 필터·편집본이 바뀌어도
    다시 마운트하지 않고 창만 다시 그린다. None 이면 창이 없다(FAB)."""
    if sheet is None:
        return None
    raw_columns = list(sheet.get("columns") or ())
    keep = [
        isinstance(column, Mapping)
        and isinstance(column.get("name"), str)
        and column.get("type") in SHEET_TYPES
        for column in raw_columns
    ]
    columns = [
        {"name": str(column["name"]), "type": str(column["type"])}
        for column, kept in zip(raw_columns, keep, strict=True)
        if kept
    ]
    rows: list[dict[str, Any]] = []
    for row in sheet.get("rows") or ():
        if not isinstance(row, Mapping):
            continue
        unit_id = row.get("id")
        cells = row.get("cells")
        if not isinstance(unit_id, str) or not unit_id.strip():
            continue
        if not isinstance(cells, (list, tuple)) or len(cells) != len(raw_columns):
            continue
        group = row.get("group")
        rows.append(
            {
                "id": unit_id.strip(),
                "group": group.strip() if isinstance(group, str) and group.strip() else None,
                "cells": [
                    _sheet_cell(cell) for cell, kept in zip(cells, keep, strict=True) if kept
                ],
            }
        )
    cut = sheet.get("cut")
    extra = max(len(rows) - MAX_SHEET_ROWS, 0)
    cleaned: dict[str, Any] = {
        "columns": columns,
        "rows": rows[:MAX_SHEET_ROWS],
        "cut": (cut if isinstance(cut, int) and not isinstance(cut, bool) and cut > 0 else 0)
        + extra,
    }
    csv = sheet.get("csv")
    if (
        isinstance(csv, Mapping)
        and isinstance(csv.get("text"), str)
        and isinstance(csv.get("file"), str)
        and csv["file"].strip()
    ):
        cleaned["csv"] = {"text": csv["text"], "file": csv["file"].strip()}
    return cleaned


def space_lock_style() -> str:
    """스크롤 고정의 페이지 서식 — `<html data-space-lock="1">` 인 동안 본문 스크롤 칸(`stMain`)을
    막는다.

    편집기 도구 줄 「화면 고정」 이 속성을 달고 뗀다(컴포넌트 밖 배치는 `<html>` 의 속성 + 페이지
    서식 — AGENTS 9장). 이 서식은 Space 현황이 그리므로 다른 화면으로 가면 사라져 속성이 남아도 막지
    않는다. 사이드바는 그대로 굴러간다. 본문 스크롤 칸이 `section[data-testid="stMain"]` 인 것은
    Streamlit 1.63 DOM 이다(판올림에서 다시 본다)."""
    return (
        f'<style>html[{SPACE_LOCK_ATTRIBUTE}="1"] [data-testid="stMain"]'
        "{overflow:hidden !important;overscroll-behavior:none}</style>"
    )


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
    group_labels: Mapping[str, str] | None = None,
    picked: str | None = None,
    on_pick: Callable[[str | None], None] | None = None,
    compare: Mapping[str, Any] | None = None,
    badges: Sequence[Mapping[str, Any]] | None = None,
    as_of_pinned: str | None = None,
    legend: Mapping[str, Any] | None = None,
    pending_save: bool = False,
    sheet: Mapping[str, Any] | None = None,
    pick_to_server: bool = True,
    arrival_dates: bool = False,
) -> None:
    """층 상세 **뷰어**. 편집기와 같은 도면을 보기 전용으로 그린다 — 편집 도구가 없고, 끌기는
    화면 이동, 누르기는 그 호기 정보 한 줄, Ctrl+휠·+/−·더블클릭은 확대다. `summary` 는 도구 줄
    오른쪽의 한 줄 요약(배치·미배치·점유율)이다. 돌려받는 값이 없다.

    호기를 누르면(끌지 않고) 브라우저가 `pick`(``{"epoch", "id"}``)을 보내고 `on_pick(설비명)` 이
    콜백에서 돈다 — 필요 단축 칸의 누른 호기 상세가 쓴다(`pick_to_server` 가 참인 동안만 보낸다).
    도면 요소·빈 곳을 누르거나 Esc 로 풀면 `on_pick(None)` 이다. 옛 epoch 값은 버린다
    (`_dispatch_pick`). `picked` 는 파이썬이 쥔 고른 호기이고, 바뀐 회차에 브라우저가 도면의
    고르기를 그것에 맞춘다(필요 단축 칸의 표에서 호기를 고르면 도면도 그 호기를 고른다).

    기준일에 반입 전인 호기가 그날 보이는 다른 호기(반입됐고 아직 도면에서 빠지지 않은)와 넓이가
    0 보다 크게 겹치면 브라우저가 그 호기를 그리지 않고, 요약 끝에 「겹쳐 숨긴 반입 예정 n대」를
    붙인다(같은 Main 설비 묶음의 모듈끼리는 셈하지 않는다). 범례 대수는 그대로다.

    도면 상자 맨 위 줄은 **기준일 페이더**다(오늘 ± 12개월 = `as_of_range`, 하루 단위). 끄는 동안은
    브라우저가 호기마다 받은 경계 날짜와 글자로 견주어 테(반입 전 주황 점선·반출/이설 예정 노랑)·
    빗금·「!」·운영 비가동 표식·지연 빨강·숨김을 바꾸고, 놓으면 `asOf` 를 한 번 보내
    `on_as_of(date)` 가 콜백에서 돈다. `items` 는 범위 어딘가에서 도면에 서는 호기의 합집합이어야
    한다(`space_unit_state.drawn_in_range`) — 기준일에 따라 목록이 달라지면 epoch 가 바뀌어 다시
    선다.
    `as_of`(세션 기준일)는 epoch 에 넣지 않는다 — 기준일·체크만 바뀐 회차는 같은 epoch 로 바뀐 것만
    다시 칠하고 보던 배율을 지킨다.

    Main 설비 모듈 묶음(모듈 둘 이상)은 묶음 범위에 Main 설비명을 그린다 — 위치는 `group_labels`
    (Main 설비 → 가운데·위·아래, 없으면 한 줄 묶음은 위·그 밖은 가운데)이고, 기준일에 묶음의 모듈이
    하나도 보이지 않으면 이름도 숨는다.

    `compare` 는 「공식과 견주기」 를 켠 회차의 재료다(`space_floor_layout.compare_payload` — 차이
    호기의 공식 자리 점선 상자·선·꼬리표, 설계 8-3). epoch 밖이라 토글로 다시 마운트하지 않고 견주기
    층만 다시 그린다. None 이면 그 층을 비운다.

    색 기준 「필요 단축」 을 켠 동안에는 `badges`(설비키마다 하나 — `shortBadges`)와
    `as_of_pinned`(기준일 고정 줄의 풍선 글 — `asOfPinned`)를 싣는다. 고정 줄이 있으면 브라우저는
    페이더 대신 그 줄을 세우고 (기준일 = 오늘), 겹친 반입 예정 숨기기를 표시된 호기에는 쓰지 않으며
    모든 호기의 지연·보관 면을 칠하지 않는다(결정 D12). 둘 다 epoch 밖이고 끈 동안에는 키가
    없다(payload 그대로).

    `legend` 는 왼쪽 칸 범례(`_clean_legend`), `pending_save` 는 위 「저장 안 한 배치」 상자가 선
    회차다 — 스크롤 고정 중에는 그 상자가 화면 밖이라 편집기가 한 줄로 알린다. 둘 다 epoch
    밖이다.

    `sheet` 는 도면 위 「호기 정보」 창의 표(`_clean_sheet` — 고른 호기의 칸·칸 필터로 맞는 호기
    목록과 도면 강조, 2026-11-03 사용자 요청)이고 epoch 밖이다. `pick_to_server` 가 거짓이면
    브라우저가 호기 누르기를 `pick` 으로 보내지 않는다(누를 때마다 앱 전체가 돌지 않게 — 받는 쪽이
    필요 단축 칸뿐이라 그 보기를 켠 동안만 참이다, 사양 D11).

    `arrival_dates` 는 사이드바 「반입 일정」 을 켠 회차다(2026-11-12 Space 보드 답 1-1 ~ 1-6) — 켠
    회차에만 data `arrivalDates` 가 실리고(epoch 밖) 브라우저가 반입 전 호기에 반입 일정을 쓴다.
    재료(호기마다 `arrivalPlan`·`arrivalDelayed`)는 늘 실린다 — 풍선이 토글과 상관없이 쓴다."""
    layer_fields: dict[str, Any] = {}
    if badges is not None:
        layer_fields["shortBadges"] = _clean_badges(badges)
    if isinstance(as_of_pinned, str) and as_of_pinned:
        layer_fields["asOfPinned"] = as_of_pinned
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
            "picked": picked if isinstance(picked, str) and picked else None,
            "compare": _clean_compare(compare),
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "canvasLimits": {"min": MIN_CANVAS_EXTENT, "max": MAX_CANVAS_EXTENT},
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "markColors": mark_colors(),
            "fontSizes": list(MARK_FONT_SIZES),
            "floor": floor_label(floor),
            "floors": [],
            "newUnit": {},
            "legend": _clean_legend(legend),
            "pendingSave": bool(pending_save),
            "sheet": _clean_sheet(sheet),
            "attention": alerts.attention_payload(),
            "pickToServer": bool(pick_to_server),
            **layer_fields,
            **({"arrivalDates": True} if arrival_dates else {}),
        },
        on_apply_change=lambda: None,
        on_asOf_change=partial(_dispatch_as_of, key, on_as_of),
        on_pick_change=partial(_dispatch_pick, key, epoch, on_pick),
        width="stretch",
    )


def _dispatch_pick(key: str, epoch: str, on_pick: Callable[[str | None], None] | None) -> None:
    """`on_pick_change` 콜백. 층 상세 뷰어에서 누른 호기(`{"epoch", "id"}`)를 `on_pick` 으로 넘긴다.

    id 가 None 이면 고른 호기가 없다는 뜻이다(도면 요소·빈 곳을 눌렀거나 Esc). 뷰어를 그린 epoch 와
    다른 값(도면이 다시 서기 전에 누른 옛 호기)과 글자가 아닌 id 는 버린다 — 블록 열기
    (`_dispatch_navigate`)와 같은 규칙이다."""
    if on_pick is None:
        return
    state = st.session_state.get(key)
    payload = state.get("pick") if isinstance(state, Mapping) else getattr(state, "pick", None)
    if not isinstance(payload, Mapping) or payload.get("epoch") != epoch:
        return
    raw = payload.get("id")
    if raw is None:
        on_pick(None)
    elif isinstance(raw, str) and raw.strip():
        on_pick(raw.strip())


def _dispatch_sheet_check(
    key: str, epoch: str, on_check: Callable[[Mapping[str, Any]], None] | None
) -> None:
    """`on_sheetCheck_change` 콜백. 배치 편집 「호기 정보」 창에서 칸을 확정할 때마다 브라우저가
    보낸 「확인만」 요청(``{"epoch", "seq", "cells"}``)을 `on_check` 로 넘긴다 — 본문보다 먼저 돌아
    판정 · 알림이 그 회차에 선다(2026-11-12 Space 시안 보드 답 5-6). 편집기를 그린 epoch 와 다른
    값(다시 서기 전에 보낸 옛 요청)과 seq 가 정수가 아닌 값은 버린다 — 블록
    열기(`_dispatch_navigate`)와 같은 규칙이다. 칸 꼴은 받는 쪽이 읽는다(`parse_sheet_cells`)."""
    if on_check is None:
        return
    state = st.session_state.get(key)
    payload = (
        state.get("sheetCheck")
        if isinstance(state, Mapping)
        else getattr(state, "sheetCheck", None)
    )
    if not isinstance(payload, Mapping) or payload.get("epoch") != epoch:
        return
    seq = payload.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool):
        return
    on_check(payload)


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
    pending_save: bool = False,
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
            "title": FAB_TITLE,
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
            "floor": FAB_VIEW_LABEL,
            "floors": [],
            "newUnit": {},
            "legend": None,
            "pendingSave": bool(pending_save),
            "sheet": None,
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
    pending_save: bool = False,
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
            "title": FAB_TITLE,
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
            "floor": FAB_VIEW_LABEL,
            "floors": [],
            "newUnit": {},
            "legend": None,
            "pendingSave": bool(pending_save),
            "sheet": None,
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
    group_labels: Mapping[str, str] | None = None,
    canvas_editable: bool = True,
    canvas_lock: str | None = None,
    overlay_extents: Sequence[tuple[str, float, float]] = (),
    order_editable: bool = True,
    order_lock: str | None = None,
    legend: Mapping[str, Any] | None = None,
    pending_save: bool = False,
    sheet: Mapping[str, Any] | None = None,
    sheet_edit: Mapping[str, Any] | None = None,
    sheet_refused: Mapping[str, Any] | None = None,
    sheet_verdict: Mapping[str, Any] | None = None,
    on_sheet_check: Callable[[Mapping[str, Any]], None] | None = None,
) -> EditorSubmission | None:
    """편집기를 그리고 `적용` 이 눌린 회차에만 받은 값을 돌려준다(검증 전 원본).

    `canvas_editable` 이 거짓이면 「캔버스」 칸(폭·높이·±·맞춤)을 끄고 `canvas_lock` 을 풍선으로
    둔다 — 층 캔버스는 공용 값이라 가정 설비 시나리오에서는 고치지 않는다(설계 8-4). 옛 브라우저가
    보낸 캔버스 값은 서버(`app_pages/space_status.py`)가 다시 거부한다(두 겹). `order_editable` 이
    거짓이면 선택 칸 「순서」 단추 넷과 순서 키를 끄고 `order_lock` 을 풍선으로 둔다 — 가정 배치
    차이는 요소 차례를 담지 않는다(2026-11-12 보드 7-4 — 화면 잠금 한 겹).

    「캔버스」 칸은 놓인 호기 · 요소, 도면에 안 보이는 이 층 호기(`EditorInputs.reserved_extent`)와
    `overlay_extents`(다른 가정 설비 시나리오의 이 층 배치 차이 — (시나리오 이름, 오른쪽, 위),
    `LayoutOverlayExtent.scenario_extents`)보다 작게 줄이지 못한다. 막은 글이 그 까닭 갈래를 말한다.

    면은 보기와 같은 규칙(지연 → 보관 → 체크한 그룹 → 기본, 기준일 `as_of`)이지만 **의미 테·덧표시는
    그리지 않는다** — 편집 화면의 테는 선택·묶음·다른 층·겹침 전용이다. 기준일은 편집 중 고정이다 —
    도구 줄 제목 옆 칩 「YYYY-MM-DD 고정」(핀 아이콘)이 말한다(기준일이 바뀌면 편집 대상 호기가
    바뀌어 적용하지 않은 편집이 버려진다). `legend` 는 왼쪽 칸 범례(채우기 뜻만), `pending_save` 는
    뷰어와 같다. `sheet` 는 뷰어와 같은 「호기 정보」 창 표다(이 층 편집본 행 + 편집기 호기 —
    「도면」 칸은 브라우저가 쥔 편집으로 덮어 쓴다). `sheet_edit` 는 그 창의 칸 고치기 재료
    (`space_sheet_edit.sheet_edit_data` — epoch 밖), `sheet_refused` 는 막힌 창 칸으로 거부한 적용의
    판정 ``{"epoch", "nonce", "blocked", "follow"}``(`space_sheet_edit.verdict_payload` — 브라우저가
    nonce 마다 한 번 받아 빨간 칸으로 짚는다). 창에서 칸을 확정할 때마다 브라우저가 「확인만」 요청
    ``{"epoch", "seq", "cells"}`` 을 트리거 `sheetCheck` 로 보내고 `on_sheet_check` 가 콜백에서
    받는다 (`_dispatch_sheet_check`). 그 판정은 다음 회차 `sheet_verdict` ``{"epoch", "seq",
    "blocked", "follow"}`` 로 돌려준다(브라우저는 마지막으로 보낸 seq 의 것만 받는다).

    적용값: ``{"epoch", "changes", "ghosts", "renames", "canvas", "marks", "groupLabels",
    "cells"}``.

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
    - ``canvas``: 캔버스를 바꿨을 때만 ``{width, height}``.
    - ``marks``: 도면 요소를 바꿨을 때만 이 층 요소 전체 목록, 아니면 None.
    - ``groupLabels``: 이 층에 남는 모듈 묶음마다의 Main 설비명 위치
      ``[{"group": 옛 Main 설비, "position": "center"|"top"|"bottom"}]``(다른 층으로 보낸 묶음은
      빠진다). 처음 위치는 `group_labels`(Main 설비 → 가운데·위·아래, 없으면 한 줄 묶음은 위·그
      밖은 가운데)이고 층 위치 목록으로 합치는 것은 `space_layout_edit.next_group_labels` 다.
    - ``cells``: 「호기 정보」 창에서 고친 칸 ``[{"id": 편집기에 실린 설비명, "col", "text"}]``
      (2026-11-12 Space 시안 보드 답 5-5). 꼴은 `parse_editor_apply`, 잠금 · 다듬기 · 규칙은
      `space_sheet_edit.check_sheet_cells` 다.
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
                "overlay": [
                    {
                        "name": str(name),
                        "right": finite_or_none(right) or 0.0,
                        "top": finite_or_none(top) or 0.0,
                    }
                    for name, right, top in overlay_extents
                ],
            },
            "decimals": CANVAS_DECIMALS,
            "palette": _palette(),
            "markColors": mark_colors(),
            "fontSizes": list(MARK_FONT_SIZES),
            "defaultSize": {"w": inputs.default_size[0], "h": inputs.default_size[1]},
            "floor": floor_label(floor),
            "floors": [floor_label(key) for key in floors],
            "newUnit": dict(new_unit),
            "canvasEditable": bool(canvas_editable),
            "canvasLock": canvas_lock or "",
            "orderEditable": bool(order_editable),
            "orderLock": order_lock or "",
            "legend": _clean_legend(legend),
            "pendingSave": bool(pending_save),
            "sheet": _clean_sheet(sheet),
            "attention": alerts.attention_payload(),
            "sheetEdit": dict(sheet_edit) if sheet_edit is not None else None,
            "sheetRefused": dict(sheet_refused) if sheet_refused is not None else None,
            "sheetVerdict": dict(sheet_verdict) if sheet_verdict is not None else None,
        },
        on_apply_change=lambda: None,
        on_sheetCheck_change=partial(_dispatch_sheet_check, key, epoch, on_sheet_check),
        width="stretch",
    )
    payload = getattr(result, "apply", None)
    if not isinstance(payload, Mapping):
        return None
    return EditorSubmission(payload=payload, stale=payload.get("epoch") != epoch)
