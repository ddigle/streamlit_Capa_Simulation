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
- **떠나기 신호**(`leave.js` — `LEAVE_JS` · `leave_js`) — 화면을 떠나는 누름이 쏘는 창 사건
  `capa-leaving` · 편집기 명부(busy) · 편집기 구역 회차 표지(AGENTS 9장 「구역 회차 규칙」 R8). 표
  공용 조각(`SHARED_JS`)에 들어 있고, 공용 조각을 잇지 않는 등록(범용 편집 그리드 · 화면 탭 줄)은
  `leave_js()` 글을 제 등록 글 앞에 잇는다.
- **묶음 길이**(`batch_ms`) — 편집기가 칸 고침을 모아 보내는 쉼을 편집기마다 결정값 상수로 두고 data
  로 JS 에 넘긴다. 개발 · 측정 사본은 실행 줄 환경변수 `CAPA_DEV_BATCH_MS` 로 덮어쓴다(운영에서는
  읽지 않는다). 편집기 구역 끄개(`CAPA_EDITOR_SCOPES=off` — `settings.editor_scopes_enabled`)가
  꺼지면 덮어쓰기보다 먼저 보아 모든 편집기가 `ORDINARY_SEND_MS` 다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.settings import editor_scopes_enabled

SHARED_ASSETS: Final = Path(__file__).with_name("grid_shared_assets")
LEAVE_JS: Final = "leave.js"
SHARED_JS: Final = ("nav.js", "outbox.js", "dom.js", LEAVE_JS)
SHARED_CSS: Final = ("cells.css", "changes.css")
# 편집기 묶음 길이 덮어쓰기(ms) — 개발 · 측정 사본의 실행 줄 환경변수 전용(`batch_ms`). 운영
# (`APP_ENV` 운영 값)에서는 읽지 않는다. 받는 범위는 `BATCH_OVERRIDE_RANGE` 다.
BATCH_OVERRIDE_ENV: Final = "CAPA_DEV_BATCH_MS"
BATCH_OVERRIDE_RANGE: Final = (50, 5000)
# 편집기 구역 끄개가 꺼졌을 때 모든 편집기의 묶음 쉼(ms) — 구역 없이 칸마다 앱 전체 회차로 돌 때의
# 값이다. Space 「호기 정보」 창도 이 쉼으로 묶는다.
ORDINARY_SEND_MS: Final = 300
# 단계 칩 바탕의 옅기 — 단계 색을 바탕 위에 이만큼 얹은 불투명 색(`tokens.opaque_mix`).
LEVEL_FILL_ALPHA: Final = 0.14


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
        # 단계 칩(시나리오 목록 「점검」 칸 「계산」) — 알림 단계 색과 같은 확인 필요 · 오류.
        "level-check": tokens.ALERT_CHECK,
        "level-check-fill": tokens.opaque_mix(tokens.ALERT_CHECK, tokens.SURFACE, LEVEL_FILL_ALPHA),
        "level-error": tokens.ALERT_ERROR,
        "level-error-fill": tokens.opaque_mix(tokens.ALERT_ERROR, tokens.SURFACE, LEVEL_FILL_ALPHA),
    }


def batch_ms(default_ms: int) -> int:
    """편집기가 칸 고침을 모아 보내는 쉼(ms) — 결정값 `default_ms`. 편집기 구역 끄개가 꺼졌으면
    무엇보다 먼저 `ORDINARY_SEND_MS` 다. 개발 실행 줄에 `CAPA_DEV_BATCH_MS` 가 있으면(범위 안 정수)
    그 값이다(측정 사본에서 묶음 길이를 바꿔 잰다). 운영 `APP_ENV` 에서는 덮어쓰기를 읽지 않는다."""
    if not editor_scopes_enabled():
        return ORDINARY_SEND_MS
    raw = os.environ.get(BATCH_OVERRIDE_ENV, "").strip()
    if not raw:
        return default_ms
    from capa_simulation.auth.config import app_env_is_production

    if app_env_is_production(os.environ.get("APP_ENV")):
        return default_ms
    try:
        value = int(raw)
    except ValueError:
        return default_ms
    low, high = BATCH_OVERRIDE_RANGE
    return value if low <= value <= high else default_ms


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


def leave_js() -> str:
    """떠나기 신호 조각 글(`leave.js`) — 공용 조각을 잇지 않는 등록이 제 글 앞에 잇는다."""
    return (SHARED_ASSETS / LEAVE_JS).read_text(encoding="utf-8")


def joined_assets(shared: Sequence[str], own: Sequence[Path]) -> str:
    """공용 조각 뒤에 화면 파일을 이은 등록 글."""
    parts = [(SHARED_ASSETS / name).read_text(encoding="utf-8") for name in shared]
    parts.extend(path.read_text(encoding="utf-8") for path in own)
    return "\n".join(parts)
