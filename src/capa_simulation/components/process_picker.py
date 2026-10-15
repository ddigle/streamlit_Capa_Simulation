# Purpose: 확보율 구역별 공정 버튼을 그리되 표시명과 원본 선택값을 분리한다.

"""HOME 공정 필터(B/N 판정 대상) 팝업의 공정 버튼.

**버튼의 설명 풍선은 Streamlit `help` 가 아니라 CSS `:hover` 로 띄운다**(2026-09-29 사용자 신고).
`help` 풍선은 마우스가 들어오고 나가는 **사건**으로 열고 닫는다. 버튼을 누르면 팝업이 다시 그려지는
동안 버튼이 새로 서는데, 그 사이에 마우스가 떠나면 닫는 사건이 새 버튼에 닿지 않아 풍선이 열린 채
남는다. 여러 공정을 빠르게 누르면 누른 버튼마다 풍선이 남았다(70공정 앱에서 브라우저로 재현).
`:hover` 는 사건이 아니라 **지금 마우스가 위에 있는가**라서 다시 그려져도 남을 수가 없다.

풍선은 버튼을 감싼 칸(`home_bn_tile_<순번>`)의 `::after` 다. 버튼 key 는 원본 공정명이라 `st-key-`
클래스로 바뀔 때 영문·숫자 밖의 글자가 모두 `-` 가 된다 — 한글 공정명 둘이 같은 클래스가 될 수
있어 순번으로 감싼다.

**공식버전 자동 갱신이 뺀 공정**에는 표지를 단다(`marks` — 공정 → `자동 off(확보율 72%,
26.11)`). 꺼진 버튼은 아이콘이 `auto_mode` 로 바뀌고, 풍선 끝 줄과 목록 위 한 줄이 그 표지를
적는다. 버튼 글자는 그대로 공정 표시명이다 — 고정 폭이라 표지를 붙이면 공정명이 잘린다.
"""

from collections.abc import Callable, Mapping, Sequence

import streamlit as st

from capa_simulation.design import tokens
from capa_simulation.services.process_picker import ProcessPickerItem
from capa_simulation.settings import format_month

# 고정 폭과 한 줄 말줄임으로 긴 이름 하나가 전체 바둑판의 행 높이를 바꾸지 않는다.
PROCESS_TILE_WIDTH = 168
TILE_WRAPPER_PREFIX = "home_bn_tile_"


def tile_tooltip_text(
    item: ProcessPickerItem, label: str, *, enabled: bool, mark: str | None = None
) -> str:
    """버튼 위에 띄우는 설명. 표시명·원본 공정·기간 최저 확보율·누르면 무엇이 되는지·표지."""
    details = [label]
    if label != item.process:
        details.append(f"원본 공정: {item.process}")
    if item.minimum_rate is None or item.minimum_month is None:
        details.append("조회기간에 유효한 확보율이 없어 판정하지 않습니다.")
    else:
        details.append(
            f"기간 최저 {item.minimum_rate:.1%} · "
            f"{format_month(item.minimum_month)} "
            f"(유효 {item.valid_month_count}개월)"
        )
    details.append("ON · 누르면 제외" if enabled else "OFF · 누르면 포함")
    if mark:
        details.append(f"공식버전 자동 갱신: {mark}")
    return "\n".join(details)


def _css_string(text: str) -> str:
    """CSS `content` 문자열. 줄바꿈은 `\\A`, 따옴표·역슬래시는 이스케이프, `<` 는 코드로 적는다.

    `<` 를 그대로 두면 공정명에 `</style>` 이 들어올 때 스타일 블록이 거기서 끊긴다.
    """
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\3C ").replace("\n", "\\A ")
    )
    return f'"{escaped}"'


def tile_tooltip_style(tooltips: Sequence[str]) -> str:
    """순번대로 감싼 버튼 칸마다 `:hover` 풍선을 거는 CSS. `tooltips[i]` 가 `i` 번째 칸의 글이다."""
    if not tooltips:
        return ""
    root = f'[class*="st-key-{TILE_WRAPPER_PREFIX}"]'
    contents = "\n".join(
        f".st-key-{TILE_WRAPPER_PREFIX}{index}:hover::after {{ content: {_css_string(text)}; }}"
        for index, text in enumerate(tooltips)
    )
    return f"""
<style>
{root} {{
    position: relative;
}}
/* 버튼 위로 띄운다. 아래로 띄우면 맨 아래 줄에서 팝업에 스크롤이 생겨 화면이 흔들린다. 폭은
   버튼과 같게 두어 팝업 가장자리 버튼에서도 옆으로 넘치지 않는다. */
{root}:hover::after {{
    position: absolute;
    left: 0;
    right: 0;
    bottom: calc(100% + 6px);
    z-index: 20;
    padding: 6px 8px;
    border: 1px solid {tokens.BORDER};
    border-radius: 6px;
    background: {tokens.SURFACE};
    color: {tokens.TEXT};
    box-shadow: 0 4px 12px {tokens.NAV_SHADOW};
    font-size: 0.75rem;
    line-height: 1.35;
    white-space: pre-line;
    overflow-wrap: anywhere;
    pointer-events: none;
    animation: home-bn-tile-tip 0.12s ease-out 0.35s both;
}}
@keyframes home-bn-tile-tip {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
}}
{contents}
</style>
"""


def auto_off_mark_line(
    items: Sequence[ProcessPickerItem],
    marks: Mapping[str, str],
    format_func: Callable[[str], str],
) -> str | None:
    """목록 위 한 줄 — 자동 갱신이 뺀 공정과 그 표지. 이 화면의 공정에 표지가 없으면 None."""
    marked = [
        f"{format_func(item.process)} {marks[item.process]}"
        for item in items
        if item.process in marks
    ]
    if not marked:
        return None
    return f"공식버전 자동 갱신이 뺀 공정 {len(marked)}개 · " + " · ".join(marked)


def render_process_picker(
    items: Sequence[ProcessPickerItem],
    selected: set[str],
    *,
    format_func: Callable[[str], str],
    on_toggle: Callable[[str], None],
    marks: Mapping[str, str] | None = None,
) -> None:
    """버튼에만 표시명을 쓰고 콜백에는 언제나 원본 공정 키를 넘긴다."""
    marks = marks or {}
    mark_line = auto_off_mark_line(items, marks, format_func)
    if mark_line is not None:
        st.caption(mark_line)
    groups = (
        ("shortfall", "확보 기준 미달"),
        ("sufficient", "확보 기준 충족"),
        ("unavailable", "확보율 없음"),
    )
    if not any(item.group == "shortfall" for item in items):
        st.caption("조회기간에 확보 기준 미달인 공정이 없습니다.")
    tooltips: list[str] = []
    for group, title in groups:
        members = [item for item in items if item.group == group]
        if not members:
            continue
        with st.container(gap="xsmall"):
            st.markdown(f"**{title} · {len(members)}**")
            with st.container(horizontal=True, gap="xsmall"):
                for item in members:
                    label = format_func(item.process)
                    enabled = item.process in selected
                    mark = marks.get(item.process)
                    with st.container(key=f"{TILE_WRAPPER_PREFIX}{len(tooltips)}", width="content"):
                        st.button(
                            label,
                            key=f"home_bn_process_tile_{item.process}",
                            type="primary" if enabled else "secondary",
                            icon=_tile_icon(enabled=enabled, marked=mark is not None),
                            width=PROCESS_TILE_WIDTH,
                            wrap=False,
                            on_click=on_toggle,
                            args=(item.process,),
                        )
                    tooltips.append(tile_tooltip_text(item, label, enabled=enabled, mark=mark))
    # 스타일만 든 `st.html` 은 이벤트 칸에 들어가 자리를 차지하지 않는다.
    st.html(tile_tooltip_style(tooltips) or "<style></style>")


def _tile_icon(*, enabled: bool, marked: bool) -> str:
    """켜진 버튼은 체크, 꺼진 버튼은 빼기 — 자동 갱신이 뺀 공정이면 `auto_mode`."""
    if enabled:
        return ":material/check:"
    return ":material/auto_mode:" if marked else ":material/remove:"
