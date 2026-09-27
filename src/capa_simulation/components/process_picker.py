# Purpose: 확보율 구역별 공정 버튼을 그리되 표시명과 원본 선택값을 분리한다.

from collections.abc import Callable, Sequence

import streamlit as st

from capa_simulation.services.process_picker import ProcessPickerItem
from capa_simulation.settings import format_month

# 고정 폭과 한 줄 말줄임으로 긴 이름 하나가 전체 바둑판의 행 높이를 바꾸지 않는다.
PROCESS_TILE_WIDTH = 168


def render_process_picker(
    items: Sequence[ProcessPickerItem],
    selected: set[str],
    *,
    format_func: Callable[[str], str],
    on_toggle: Callable[[str], None],
) -> None:
    """버튼에만 표시명을 쓰고 콜백에는 언제나 원본 공정 키를 넘긴다."""
    groups = (
        ("shortfall", "확보 기준 미만"),
        ("sufficient", "기준 이상"),
        ("unavailable", "확보율 없음"),
    )
    if not any(item.group == "shortfall" for item in items):
        st.caption("조회기간에 확보 기준 미만인 공정이 없습니다.")
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
                    st.button(
                        label,
                        key=f"home_bn_process_tile_{item.process}",
                        type="primary" if enabled else "secondary",
                        icon=":material/check:" if enabled else ":material/remove:",
                        help="\n\n".join(details),
                        width=PROCESS_TILE_WIDTH,
                        wrap=False,
                        on_click=on_toggle,
                        args=(item.process,),
                    )
