# Purpose: 편집기 두 칸 배치(칸막이 · 접기 · 폭 기억 · 서식 · 칸 고르기)를 화면끼리 함께 쓴다.

"""편집기 영역 안 왼쪽 표 · 오른쪽 칸 — 설비 마스터와 시나리오 목록 관리가 함께 쓴다(설계 규칙
UI-LAY-09 · UI-CON-04).

**두 칸 배치**는 테두리 하나의 key 칸(`frame_key`) 안 key 가로 칸(`split_key` › `left_key` ·
`right_key`)이고 서식은 페이지 CSS 한 덩이(`side_layout_style`)다 — 오른쪽 칸은 편집기 영역 안의
서브페이지다. 오른쪽 칸 맨 앞의 작은 등록 `capa_side_splitter`(`render_side_splitter`)가 칸막이와 칸
머리의 접기 단추, 접었을 때 편집기 영역 오른쪽 위에 떠 있는 단추를 그린다 — 끌어 폭 바꾸기(최소 ·
최대 한계 `SIDE_*`), 접기 · 펴기. 폭 · 접힘은 브라우저 저장소와 `<html>` 의 CSS 변수 · 속성에만 두고
파이썬으로 보내지 않는다(AGENTS 9장 「브라우저 전용 보기 상태」). 오른쪽 칸 본문(`body_key` — 고르기
아래 전부)은 창 높이로 정한 상한 안에서 스크롤한다.

화면마다 갈리는 것은 `SidePanel` 스펙 하나다 — key 앞붙이, 저장소 이름, CSS 변수 이름, 처음 폭.
수치와 식은 모두 같다. 스펙은 화면끼리 `<html>` 표지를 나눠 쓰지 않게 이름을 따로 둔다.

브라우저 쪽은 `side_panel_assets/` 의 파일이다. 모듈을 읽을 때 등록하므로 이 모듈은 그 편집기가 열린
회차에서만 불러온다 — 시험은 `tests/conftest.py` 의 대역이 바꾼다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.design import tokens
from capa_simulation.page_tabs_state import PAGE_TABS_COMPONENT_KEY

_ASSETS = Path(__file__).with_name("side_panel_assets")

_SPLITTER = st.components.v2.component(
    "capa_side_splitter",
    html='<div class="ess"></div>',
    css=(_ASSETS / "splitter.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "splitter.js").read_text(encoding="utf-8"),
)

# 오른쪽 칸 폭 한계(2026-11-02 사용자 결정 「너비에 한계를 두고」 — 명세 15-2). 최소 360px 는 칸
# 머리 한 줄(「오른쪽 칸」 고르기 넷의 자연 폭 310px + 사이 6 + 접기 단추 28)에 칸막이 곁 여백 14 를
# 더한 값, 최대 760px 은 표에 줄의 40% 이상을 남기는 몫 60% 와 함께 건다. 좁은 줄에서는 몫(최소
# 40%)이 이긴다. 시나리오 목록 관리의 고르기는 다섯이라 단추 좌우 안쪽 여백을 그 칸만 14 → 12px
# 로 좁힌다(`SidePanel.choice_pad_px` — 2026-11-11 입력 점검 검토 보드 F2 (라)). 단추 합이 338 →
# 318px 이 되어 창 1283 의 처음 폭(354px — 접기 단추 몫 34 를 빼면 320)에서 한 줄이다(남는 폭 2px
# 남짓 — 사본 측정 · 글꼴 흉내, 사내 글꼴에서는 다시 잰다). 창 1100 의 처음 폭(281px)은 넷일 때도
# 두 줄이었고 두 표 머리 맞춤(`list.js` `headFit`)이 받는다 — 처음 폭(40%)은 왼쪽 시나리오 표 최소
# 폭 몫이라 올리지 않는다.
SIDE_MIN_PX: Final = 360
SIDE_MIN_SHARE: Final = 0.4
SIDE_MAX_PX: Final = 760
SIDE_MAX_SHARE: Final = 0.6
# 왼쪽 칸 안쪽 폭의 아래 한계 — 오른쪽 칸 최대가 왼쪽에 이만큼은 남긴다. 설비 마스터 찾기 칸의
# 입력 칸 180 + 테 4 + 안쪽 여백 16 + 돋보기 18 + 사이 6(1.63 측정). 줄이 아주 좁으면 오른쪽 칸
# 최소가 이긴다.
SIDE_LEFT_MIN_PX: Final = 224
# 본문 높이 상한 = max(360px, 창 높이 − 붙는 높이 − 200px). 200px = 고르기 42 + 간격 16 +
# Streamlit 본문 아래 여백 약 140(1500×950 측정). 붙는 높이(CSS 변수 `top`)는 칸막이가 화면 탭 줄이
# 붙었을 때의 아래 끝 + 8px 로 잰다(1.63 — 탭 줄 sticky top 52.5 + 높이 36 → 97px). 재기 전에는 그
# 측정값을 쓴다. 오른쪽 칸은 내용이 짧아도 머리(고르기 28 + 간격 14) + 이 상한만큼 높이를 잡는다 —
# 칸을 바꿔도 영역 높이가 뛰지 않고 칸막이를 경계선을 따라 잡을 수 있다.
SIDE_BODY_MIN_PX: Final = 360
SIDE_BODY_RESERVE_PX: Final = 200
SIDE_TOP_FALLBACK_PX: Final = 97
SIDE_HEAD_PX: Final = 42
# 칸막이를 잡는 폭 — 두 칸 경계선이 그 한가운데다. 표 · 오른쪽 칸은 경계선에서 각각 이만큼 띄운다.
SIDE_GUTTER_PX: Final = 16
SIDE_INSET_PX: Final = 14
# 편집기 영역(`st.container(border=True)`)의 안쪽 여백(1.63 측정) — 경계선과 칸막이 잡는 칸이
# 이만큼 위아래로 나가 영역 테두리에 닿는다. 칸막이 쪽 값은 `splitter.css` 에 같게 적는다.
SIDE_FRAME_PAD_PX: Final = 13
# 줄에서 왼쪽 감싸개가 차지하는 아래 한계 — 안쪽 폭 + 경계선 쪽 여백 + 경계선 1px.
SIDE_LEFT_KEEP_PX: Final = SIDE_LEFT_MIN_PX + SIDE_INSET_PX + 1
# 본문 칸 스크롤 막대 자리(`scrollbar-gutter: stable`, 1.63 측정) — 편집기 영역 안쪽 여백(13px)으로
# 내보내 본문 내용의 오른쪽 끝이 칸 머리 접기 단추의 오른쪽 끝과 맞는다.
SIDE_SCROLLBAR_PX: Final = 10
# 칸 머리 접기 단추(고르기와 같은 높이)와 고르기 사이 간격 — 고르기 칸이 이만큼 자리를 비운다.
SIDE_TOGGLE_PX: Final = 28
SIDE_TOGGLE_GAP_PX: Final = 6
# 접은 동안 표 위 작업 줄이 비우는 오른쪽 자리 — 떠 있는 단추(가장 긴 칸 이름 「저장 전 변경」 89px,
# 측정)가 작업 줄 단추를 덮지 않게.
SIDE_REOPEN_RESERVE_PX: Final = 112
# 떠 있는 단추를 품은 오른쪽 칸 감싸개의 쌓임 차례 — 표 머리(`.emg-head` 6) 위, 고르는 칸(8)·목록
# (9·30) 아래. 글 편집 칸(5)은 머리 밑이라 단추 밑이기도 하다.
SIDE_REOPEN_Z_INDEX: Final = 7
# 이 창 폭 이하에서는 두 칸을 위아래로 쌓는다(옛 `st.columns` 와 같은 640px) — 칸막이 · 접기는 없다.
SIDE_STACK_MAX_PX: Final = 640


@dataclass(frozen=True)
class SidePanel:
    """화면 하나의 두 칸 배치 — key · 저장소 · CSS 이름과 처음 폭. 수치는 이 모듈 상수를 쓴다."""

    frame_key: str
    split_key: str
    left_key: str
    right_key: str
    tools_key: str
    choice_key: str
    next_key: str
    reveal_key: str
    body_key: str
    splitter_key: str
    # 브라우저 저장소 이름과 `<html>` 표지 — CSS 변수 `--<css_name>-side-w` · `--<css_name>-top`,
    # 속성 `data-<css_name>-side`.
    store: str
    css_name: str
    # 처음 폭 — `calc(몫% - 덜기px)`.
    default_share: float
    default_offset_px: int
    # 칸 고르기 단추의 좌우 안쪽 여백(px). None 이면 Streamlit 기본(14px) 그대로다 — 고르기가 많아
    # 기준 창의 처음 폭에서 두 줄로 접히는 화면만 좁힌다(시나리오 목록 관리 12 — 검토 보드 F2 (라)).
    choice_pad_px: int | None = None


def named_side_panel(
    prefix: str,
    *,
    store: str,
    css_name: str,
    default_share: float,
    default_offset_px: int,
    choice_pad_px: int | None = None,
) -> SidePanel:
    """key 를 앞붙이 하나로 짓는다(`<prefix>_frame` · `<prefix>_side_v1` …)."""
    return SidePanel(
        frame_key=f"{prefix}_frame",
        split_key=f"{prefix}_split",
        left_key=f"{prefix}_left",
        right_key=f"{prefix}_right",
        tools_key=f"{prefix}_tools",
        choice_key=f"{prefix}_side_v1",
        next_key=f"{prefix}_side_next_v1",
        reveal_key=f"{prefix}_side_reveal_v1",
        body_key=f"{prefix}_side_body",
        splitter_key=f"{prefix}_side_splitter",
        store=store,
        css_name=css_name,
        default_share=default_share,
        default_offset_px=default_offset_px,
        choice_pad_px=choice_pad_px,
    )


def side_bounds(spec: SidePanel) -> dict[str, float]:
    """칸막이 data 의 폭 한계 — JS `clampWidth` 가 페이지 CSS clamp 와 같은 식으로 쓴다."""
    return {
        "minPx": SIDE_MIN_PX,
        "minShare": SIDE_MIN_SHARE,
        "maxPx": SIDE_MAX_PX,
        "maxShare": SIDE_MAX_SHARE,
        "leftKeep": SIDE_LEFT_KEEP_PX,
        "defaultShare": spec.default_share,
        "defaultOffset": spec.default_offset_px,
    }


def _percent(share: float) -> str:
    return f"{share * 100:g}%"


def side_width_rule(spec: SidePanel) -> str:
    """오른쪽 칸 감싸개의 폭 — 창 폭이 바뀌어도 JS 없이 한계를 지킨다(칸막이는 폭 변수만 바꾼다)."""
    low = f"min({SIDE_MIN_PX}px, {_percent(SIDE_MIN_SHARE)})"
    default = f"calc({_percent(spec.default_share)} - {spec.default_offset_px}px)"
    keep = f"calc(100% - {SIDE_LEFT_KEEP_PX}px)"
    high = f"min({SIDE_MAX_PX}px, {_percent(SIDE_MAX_SHARE)}, {keep})"
    return f"clamp({low}, var(--{spec.css_name}-side-w, {default}), {high})"


def side_layout_style(spec: SidePanel) -> str:
    """두 칸 배치 CSS — 탭 본문이 회차마다 같은 글로 한 번 그린다(스타일만 든 `st.html` 이라
    이벤트 칸 한 자리).

    가로 칸의 flex 항목은 key 칸이 아니라 그것을 한 번 감싼 `stLayoutWrapper` 다(1.63 — Qual
    계산기와 같은 꼴). `:has()` 는 한 겹만 쓴다(겹치면 규칙 전체가 버려진다). `wrap=False` 가로
    칸은 스크롤 칸이 되어 sticky 가 줄 기준으로 잡히므로 줄에 `overflow: visible` 을 건다.
    테두리는 바깥 칸(`frame_key`) 하나이고 두 칸 경계선은 왼쪽 감싸개의 오른쪽 테두리다 — 왼쪽은 줄
    높이로 늘어난 뒤 음수 여백으로 영역 안쪽 여백까지 나가 경계선이 영역 테두리에 닿고, 같은 값의
    안쪽 여백이 내용 자리를 그대로 둔다. 칸막이 마운트는 붙는(sticky) 오른쪽 감싸개를 기준으로
    경계선부터 칸 오른쪽 끝까지 덮는 절대 위치(흐름 높이 0)이고, 눌림은 칸막이·접기 단추만 받는다
    (`pointer-events`). 접힘(`data-<이름>-side="min"`)은 넓은 화면에서만 — 칸 자리가 0 이 되어 표가
    줄을 다 쓰고 떠 있는 단추만 남는다. 좁은 화면(쌓임)과 인쇄는 펼친 꼴이다.
    """
    wrapper = '[data-testid="stLayoutWrapper"]'
    left = f".st-key-{spec.left_key}"
    right = f".st-key-{spec.right_key}"
    left_item = f"{wrapper}:has(> {left})"
    right_item = f"{wrapper}:has(> {right})"
    splitter = f".st-key-{spec.splitter_key}"
    choice = f".st-key-{spec.choice_key}"
    tools = f".st-key-{spec.tools_key}"
    body = f".st-key-{spec.body_key}"
    folded = f'html[data-{spec.css_name}-side="min"]'
    top = f"var(--{spec.css_name}-top, {SIDE_TOP_FALLBACK_PX}px)"
    line = f"1px solid {tokens.BORDER}"
    half = SIDE_GUTTER_PX // 2
    body_cap = f"max({SIDE_BODY_MIN_PX}px, calc(100vh - {top} - {SIDE_BODY_RESERVE_PX}px))"
    return "".join(
        [
            "<style>",
            f".st-key-{spec.split_key} {{ align-items: flex-start; overflow: visible; }}",
            f"{left} {{ flex: 1 1 0; min-width: 0; }}",
            (
                f"{left_item} {{ flex: 1 1 0; min-width: 0; align-self: stretch; "
                f"margin-block: -{SIDE_FRAME_PAD_PX}px; padding-block: {SIDE_FRAME_PAD_PX}px; "
                f"padding-right: {SIDE_INSET_PX}px; border-right: {line}; }}"
            ),
            (
                f"{right_item} {{ flex: 0 0 {side_width_rule(spec)}; min-width: 0; "
                f"padding-left: {SIDE_INSET_PX}px; "
                f"position: sticky; top: {top}; align-self: flex-start; }}"
            ),
            f"{right} {{ min-height: calc({body_cap} + {SIDE_HEAD_PX}px); }}",
            (
                f"{splitter} {{ position: absolute; top: 0; bottom: 0; left: -{half}px; right: 0; "
                "width: auto; min-width: 0; max-width: none; z-index: 2; pointer-events: none; }"
            ),
            f"{choice} {{ padding-right: {SIDE_TOGGLE_PX + SIDE_TOGGLE_GAP_PX}px; }}",
            choice_padding_rule(spec),
            (
                f"{body} {{ width: calc(100% + {SIDE_SCROLLBAR_PX}px); max-width: none; "
                f"max-height: {body_cap}; "
                "overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; }"
            ),
            f"@media screen and (width > {SIDE_STACK_MAX_PX}px) {{ ",
            f"{folded} {left_item} {{ padding-right: 0; border-right: none; }} ",
            (
                f"{folded} {right_item} {{ flex-basis: 0; width: 0; padding-left: 0; "
                f"z-index: {SIDE_REOPEN_Z_INDEX}; }} "
            ),
            f"{folded} {right} {{ min-height: 0; }} ",
            f"{folded} {right} > :not({splitter}) {{ display: none; }} ",
            f"{folded} {splitter} {{ left: auto; bottom: auto; width: 0; height: 0; }} ",
            f"{folded} {tools} {{ padding-right: {SIDE_REOPEN_RESERVE_PX}px; }} ",
            "}",
            f"@media (width <= {SIDE_STACK_MAX_PX}px) {{ ",
            f".st-key-{spec.split_key} {{ flex-wrap: wrap; }} ",
            (
                f"{left_item} {{ flex: 1 1 100%; position: static; margin-block: 0; "
                "padding-block: 0; padding-right: 0; border-right: none; } "
            ),
            (
                f"{right_item} {{ flex: 1 1 100%; position: static; padding-left: 0; "
                f"padding-top: {SIDE_INSET_PX}px; border-top: {line}; }} "
            ),
            f"{right} {{ min-height: 0; }} ",
            f"{splitter} {{ display: none; }} ",
            f"{choice} {{ padding-right: 0; }} ",
            "}",
            "@media print { ",
            f"{right_item} {{ position: static; }} ",
            f"{right} {{ min-height: 0; }} ",
            f"{body} {{ width: 100%; max-height: none; overflow: visible; }} ",
            f"{splitter} {{ display: none; }} ",
            f"{choice} {{ padding-right: 0; }} ",
            "}",
            "</style>",
        ]
    )


def choice_padding_rule(spec: SidePanel) -> str:
    """칸 고르기 단추의 좌우 안쪽 여백 — 그 화면 고르기(`choice_key`)에만 건다. 여백을 정하지 않은
    화면은 빈 글이다(다른 화면 고르기는 Streamlit 기본 그대로)."""
    if spec.choice_pad_px is None:
        return ""
    pad = f"{spec.choice_pad_px}px"
    return (
        f'.st-key-{spec.choice_key} [data-testid="stButtonGroup"] button '
        f"{{ padding-left: {pad}; padding-right: {pad}; }}"
    )


def splitter_palette() -> dict[str, str]:
    """칸막이 색 — 표와 같은 토큰(CSS `var(--ess-*)`). 등록 CSS 에는 색을 적지 않는다."""
    return {
        "font": tokens.FONT_FAMILY,
        "text": tokens.TEXT,
        "muted": tokens.TEXT_MUTED,
        "surface": tokens.SURFACE,
        "border": tokens.BORDER,
        "accent": tokens.ACCENT,
    }


def render_side_splitter(spec: SidePanel, label: str, reveal: int) -> None:
    """오른쪽 칸 맨 앞의 칸막이 — 오른쪽 칸 왼쪽 끝을 끌어 폭을 바꾸고(두 번 누르면 처음 폭,
    키보드 ←·→·Home·End), 칸 머리의 › 로 접고 편집기 영역 오른쪽 위에 떠 있는 단추(지금 칸 이름
    `label`)를 눌러 편다. 받는 값이 없다(상태 값·트리거 없음 — 회차를 부르지 않는다). `reveal` 은
    표·오른쪽 칸이 오른쪽 칸을 연 수(`switch_side`) — 늘면 접힌 칸을 펴고 본문 칸을 맨 위로 올린다
    (key 칸이라 다른 줄을 그려도 스크롤 자리가 남는다)."""
    _SPLITTER(
        key=spec.splitter_key,
        data={
            "palette": splitter_palette(),
            "label": label,
            "reveal": reveal,
            "bounds": side_bounds(spec),
            "keys": {"row": spec.split_key, "right": spec.right_key, "body": spec.body_key},
            "names": {
                "store": spec.store,
                "width": f"--{spec.css_name}-side-w",
                "top": f"--{spec.css_name}-top",
                "attr": f"data-{spec.css_name}-side",
            },
            "cover": f".st-key-{PAGE_TABS_COMPONENT_KEY}",
        },
        width="stretch",
    )


def split_frame(spec: SidePanel) -> tuple[DeltaGenerator, DeltaGenerator]:
    """테두리 하나의 편집기 영역 안 두 칸을 세운다 — (왼쪽, 오른쪽). 간격은 서식이 경계선 양쪽
    여백으로 둔다. 배치 서식은 늘 같은 글 한 덩이다."""
    st.html(side_layout_style(spec))
    with st.container(key=spec.frame_key, border=True):
        with st.container(key=spec.split_key, horizontal=True, gap=None, wrap=False):
            left = st.container(key=spec.left_key)
            right = st.container(key=spec.right_key)
    return left, right


def switch_side(spec: SidePanel, side: str) -> None:
    """오른쪽 칸을 바꾼다 — 받기 콜백이 고른 칸은 다음 고르기 위젯 앞에서 적는다(`next_key` — 그
    고르기 뒤에 그린 마운트의 콜백도 같은 길이다). 연 수(`reveal_key`)를 올려 접힌 칸을 편다."""
    st.session_state[spec.next_key] = side
    st.session_state[spec.reveal_key] = side_reveal(spec) + 1


def side_reveal(spec: SidePanel) -> int:
    value = st.session_state.get(spec.reveal_key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def render_side_head(
    spec: SidePanel, options: Sequence[str], default: str, *, label: str = "오른쪽 칸"
) -> tuple[str, DeltaGenerator]:
    """오른쪽 칸(안에서 부른다)의 머리 — 칸막이(절대 위치, 흐름 높이 0) → 칸 고르기 → 본문 칸.
    고른 칸과 본문 칸을 돌려준다. 고르기는 세션에 값을 적는 위젯이라 `default=` 없이 칸이 없거나
    목록 밖일 때만 심는다(AGENTS 9장)."""
    chosen = st.session_state.pop(spec.next_key, None)
    if chosen in options:
        st.session_state[spec.choice_key] = chosen
    if st.session_state.get(spec.choice_key) not in options:
        st.session_state[spec.choice_key] = default
    render_side_splitter(spec, str(st.session_state[spec.choice_key]), side_reveal(spec))
    side = st.segmented_control(
        label,
        list(options),
        key=spec.choice_key,
        required=True,
        persist_state="session",
        label_visibility="collapsed",
    )
    body = st.container(key=spec.body_key)
    return str(side), body
