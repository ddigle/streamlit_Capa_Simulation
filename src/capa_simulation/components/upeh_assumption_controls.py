# Purpose: 두 화면이 함께 쓰는 「UPEH 가정」 입력(%·적용 구간)과 배지·역산 단추를 그린다.

"""「UPEH 가정」 입력 — 두 화면의 조건 카드 끝에 서는 「이 세션만」 묶음.

- **% 칸**(`st.number_input`, 80~150, 1 단위 — 2026-10-22 사용자 결정 「바뀌면 곧바로 반영」). 100%
  가 기본이고 곧 「꺼짐」이다. 100% 가 아니면 「100% 로」 단추가 선다.
- **적용 구간** — 「UPEH 적용 시작」·「UPEH 적용 끝」(필요 단축 일정 카드의 공용 「시작 월/끝 월」과
  글자를 가른다). 선택지는 **한 함수**(`assumption_month_options` — 사이드바 조회기간 가운데 이번 달
  이후)로만 낸다 — 두 화면이 같은 선택지를 그려야 화면을 옮길 때 「선택지 밖 → 새 값」으로 구간이
  말없이 바뀌지 않는다. 100% 면 비활성이다.

**두 화면이 같은 세션 키 셋을 나눠 쓴다**(`upeh_assumption_state`). 위젯 id 에는 페이지가 들어가므로
페이지를 옮긴 첫 회차를 지키려고 세 칸 모두 위젯 앞에서 `carry_shared_widget_value` 를 부른다(AGENTS
9장 「두 페이지가 같은 key 를 그리면」). 선택지 밖 달은 지우지 않고 새 값을 적는다(9장 「pop 하지
말고 새 값을 적는다」).

계산은 하지 않는다 — 고른 값(`UpehAssumption`)을 돌려줄 뿐이고, 화면이 그 값으로 토큰을 만든다
(`services/upeh_assumption.py`). 역산 한 줄과 「이 값으로」 단추(`render_inverse`)도 여기서 그린다 —
값을 적는 것은 콜백이다(위젯을 그린 뒤에는 그 칸을 적을 수 없다).
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from capa_simulation.services.month_columns import month_label
from capa_simulation.services.upeh_assumption import (
    PERCENT_DEFAULT,
    PERCENT_MAX,
    PERCENT_MIN,
    InversePercent,
    UpehAssumption,
    UpehToken,
    assumption_label,
    clamp_percent,
    inverse_text,
    token_label,
)
from capa_simulation.shared_widget_state import carry_shared_widget_value
from capa_simulation.upeh_assumption_state import (
    UPEH_ASSUMPTION_END_KEY,
    UPEH_ASSUMPTION_PERCENT_KEY,
    UPEH_ASSUMPTION_START_KEY,
)

__all__ = [
    "UPEH_RESET_BUTTON_KEY",
    "apply_upeh_percent",
    "assumption_month_options",
    "render_inverse",
    "render_upeh_assumption_controls",
    "upeh_badge",
]

UPEH_RESET_BUTTON_KEY = "upeh_assumption_reset"
GROUP_CAPTION = (
    ":material/person: **이 세션만** · UPEH 가정 — 100% = 기준정보 그대로 · HOME·공식버전·공용 "
    "설정은 "
    "바뀌지 않습니다"
)
PERCENT_HELP = (
    "활성 시나리오 기준정보의 계획 UPEH(Main UPEH · MI 는 ST)를 적용 구간의 달에만 이 비율로 "
    "본다면 — "
    "+10%(110%)는 소요대수 −9.1%(1 − 1/1.1)입니다. 「확보율 보정」(HOME, 확보율 %p 덧셈)과 다른 "
    "것이라 "
    "둘을 함께 켜면 같은 개선이 두 번 들어갈 수 있습니다."
)


def assumption_month_options(start_month: int, end_month: int, *, today: date) -> list[int]:
    """적용 구간의 선택지 — 조회기간(`start_month`~`end_month`, `YYYYMM`) 가운데 이번 달 이후의 달.

    두 화면이 이 함수만 부른다(선택지가 같아야 공유 위젯 값이 화면을 옮겨도 살아남는다). 지난 달에
    UPEH 를 가정하는 것은 뜻이 없고, 지난 달 부족은 단축으로도 바꿀 수 없다.
    """
    first = max(int(start_month), today.year * 100 + today.month)
    months: list[int] = []
    year, month = divmod(first, 100)
    while year * 100 + month <= int(end_month):
        months.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def render_upeh_assumption_controls(
    *, owner: str, start_month: int, end_month: int, today: date
) -> UpehAssumption | None:
    """% 칸·적용 구간·「100% 로」 를 지금 컨테이너(조건 카드)에 그리고 고른 값을 돌려준다.

    `owner` 는 그리는 화면의 이름이다(`carry_shared_widget_value`). 선택지가 비면(조회기간이 모두
    지난 달) 구간을 그리지 않고 None 이다 — 걸 달이 없다. 100% 여도 구간이 있으면 값을
    돌려준다(역산이 그 구간을 본다, `UpehAssumption.active` 가 거짓).
    """
    options = assumption_month_options(start_month, end_month, today=today)
    carry_shared_widget_value(UPEH_ASSUMPTION_PERCENT_KEY, default=PERCENT_DEFAULT, owner=owner)
    if options:
        carry_shared_widget_value(UPEH_ASSUMPTION_START_KEY, default=options[0], owner=owner)
        carry_shared_widget_value(UPEH_ASSUMPTION_END_KEY, default=options[-1], owner=owner)
        # 조회기간이 바뀌어 옛 달이 선택지 밖이면 **새 값을 적는다**(지우면 브라우저가 옛 선택을
        # 계속 보인다).
        if st.session_state.get(UPEH_ASSUMPTION_START_KEY) not in options:
            st.session_state[UPEH_ASSUMPTION_START_KEY] = options[0]
        if st.session_state.get(UPEH_ASSUMPTION_END_KEY) not in options:
            st.session_state[UPEH_ASSUMPTION_END_KEY] = options[-1]
    held = st.session_state.get(UPEH_ASSUMPTION_PERCENT_KEY)
    if (
        not isinstance(held, int)
        or isinstance(held, bool)
        or not PERCENT_MIN <= held <= PERCENT_MAX
    ):
        st.session_state[UPEH_ASSUMPTION_PERCENT_KEY] = PERCENT_DEFAULT

    st.caption(GROUP_CAPTION)
    percent = st.number_input(
        "UPEH 가정 (%)",
        min_value=PERCENT_MIN,
        max_value=PERCENT_MAX,
        step=1,
        key=UPEH_ASSUMPTION_PERCENT_KEY,
        persist_state="session",
        help=PERCENT_HELP,
    )
    value = int(percent) if percent is not None else PERCENT_DEFAULT
    if not options:
        st.caption("조회기간에 이번 달 이후의 달이 없어 UPEH 가정을 걸 구간이 없습니다.")
        return None
    start_column, end_column = st.columns(2)
    with start_column:
        start = st.selectbox(
            "UPEH 적용 시작",
            options=options,
            format_func=month_label,
            key=UPEH_ASSUMPTION_START_KEY,
            persist_state="session",
            disabled=value == PERCENT_DEFAULT,
        )
    with end_column:
        end = st.selectbox(
            "UPEH 적용 끝",
            options=options,
            format_func=month_label,
            key=UPEH_ASSUMPTION_END_KEY,
            persist_state="session",
            disabled=value == PERCENT_DEFAULT,
        )
    first = int(start) if start is not None else options[0]
    last = int(end) if end is not None else options[-1]
    if first > last:
        st.caption("UPEH 적용 시작이 끝보다 늦어 바꿔 읽었습니다.")
    if value != PERCENT_DEFAULT:
        st.button(
            "100% 로",
            key=UPEH_RESET_BUTTON_KEY,
            icon=":material/restart_alt:",
            type="tertiary",
            on_click=apply_upeh_percent,
            args=(PERCENT_DEFAULT,),
            help="UPEH 가정을 끕니다(기준정보 그대로). 적용 구간은 그대로 둡니다.",
        )
    return UpehAssumption(percent=value, start=first, end=last)


def apply_upeh_percent(value: int) -> None:
    """% 칸에 값을 적는 콜백(범위 안으로 깎는다)."""
    st.session_state[UPEH_ASSUMPTION_PERCENT_KEY] = clamp_percent(value)


def upeh_badge(source: UpehAssumption | UpehToken) -> str:
    """머리 배지 — 「:orange-badge[UPEH 가정 110% · 26-07–26-12]」. 꺼졌거나 빈 토큰이면 빈 글자."""
    if isinstance(source, UpehAssumption):
        text = assumption_label(source) if source.active else ""
    else:
        text = token_label(source)
    return f":orange-badge[{text}]" if text else ""


def render_inverse(
    inverse: InversePercent,
    *,
    goal: str,
    key: str,
    current: int | None = None,
) -> None:
    """역산 한 줄 — 「구간 안 단축 0 → UPEH ≥ 118%」 과 「이 값으로」 단추(그 값이 지금 값과 다를
    때만)."""
    value = inverse.button_value
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption(inverse_text(goal, inverse), width="content")
        if value is not None and value != current:
            st.button(
                "이 값으로",
                key=key,
                type="tertiary",
                icon=":material/arrow_upward:" if current is None or value > current else None,
                on_click=apply_upeh_percent,
                args=(value,),
                help=f"UPEH 가정을 {value}% 로 둡니다(적용 구간은 그대로).",
            )
