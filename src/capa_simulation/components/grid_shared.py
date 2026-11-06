# Purpose: 브라우저 표 컴포넌트들이 함께 쓰는 팔레트 · 받은 값 읽기 · 공용 자산 잇기를 둔다.

"""설비 마스터 표와 시나리오 목록 표가 함께 쓰는 것(설계 규칙 UI-CON-04). 등록이 없어 어디서 불러도
된다 — 화면 탭 줄 · 변경 칩이 읽는 세션 칸 쪽도 이 모듈은 쓸 수 있다.

- **팔레트**(`grid_palette`) — 색은 회차마다 토큰에서 읽어 data 로 넘긴다. 등록 CSS 는 테마를
  따라오지 않아 색을 적지 않는다(CSS `var(--emg-*)`).
- **받은 값**(`state_value` · `outbox_value` · `outbox_mount`) — CCv2 결과 객체는 매핑으로도
  속성으로도 온다(대역은 속성).
- **자산 잇기**(`joined_assets`) — 등록 글은 공용 조각(`grid_shared_assets/`) 뒤에 화면 파일을
  잇는다. 그림자 DOM 이라 클래스 이름이 다른 등록과 부딪히지 않는다. CSS 는 차례가 뜻을 가른다(같은
  특이도면 뒤가 이긴다) — 공용 조각을 **앞**에 둔다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import streamlit as st

from capa_simulation.design import tokens

SHARED_ASSETS: Final = Path(__file__).with_name("grid_shared_assets")
SHARED_JS: Final = ("nav.js", "outbox.js", "dom.js")
SHARED_CSS: Final = ("cells.css", "changes.css")


def grid_palette() -> dict[str, str]:
    """표 색 — 테마를 바꾸면 같은 표가 새 색을 받는다(CSS `var(--emg-*)`)."""
    return {
        "font": tokens.FONT_FAMILY,
        "text": tokens.TEXT,
        "muted": tokens.TEXT_MUTED,
        "surface": tokens.SURFACE,
        "subtle": tokens.SURFACE_SUBTLE,
        "header": tokens.HEADER_BACKGROUND,
        "border": tokens.BORDER,
        "border-strong": tokens.BORDER_STRONG,
        "accent": tokens.ACCENT,
        "on-accent": tokens.ACCENT_TEXT,
        "changed-fill": tokens.GRID_CHANGED_FILL,
        "changed-mark": tokens.GRID_CHANGED_MARK,
        "error-fill": tokens.GRID_ERROR_FILL,
        "error-line": tokens.GRID_ERROR_LINE,
        "warn-line": tokens.GRID_WARN_LINE,
        "lock-fill": tokens.GRID_LOCK_FILL,
        "scenario-head": tokens.GRID_SCENARIO_HEAD,
        "layout-head": tokens.GRID_LAYOUT_HEAD,
        "selected-fill": tokens.GRID_SELECTED_FILL,
        "new-fill": tokens.GRID_NEW_FILL,
    }


def state_value(key: str, name: str) -> object:
    """`st.session_state[key]` 의 `name` — 결과 객체는 매핑으로도 속성으로도 온다(대역은 속성)."""
    state = st.session_state.get(key)
    if isinstance(state, Mapping):
        return state.get(name)
    return getattr(state, name, None)


def outbox_value(key: str) -> object:
    """그 마운트의 상태 값 `outbox`(없으면 None). 처리 함수가 여러 마운트를 함께 읽는다."""
    return state_value(key, "outbox")


def outbox_mount(value: object) -> str | None:
    """출납의 마운트 id(꼴이 다르면 None) — 그 key 의 `ack` 를 그 마운트에 단다."""
    if isinstance(value, Mapping) and isinstance(value.get("mount"), str):
        return str(value["mount"])
    return None


def joined_assets(shared: Sequence[str], own: Sequence[Path]) -> str:
    """공용 조각 뒤에 화면 파일을 이은 등록 글."""
    parts = [(SHARED_ASSETS / name).read_text(encoding="utf-8") for name in shared]
    parts.extend(path.read_text(encoding="utf-8") for path in own)
    return "\n".join(parts)
