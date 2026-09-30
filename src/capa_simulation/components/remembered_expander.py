# Purpose: 본문의 접는 상자가 탭·페이지 이동과 라벨 변경을 건너 펼침 상태를 기억하게 한다.

"""펼침을 기억하는 본문 확장 패널(2026-10-01 브라우저 점검).

`key` 없는 `st.expander` 는 서버가 펼침 상태를 모른다. 그래서 두 자리에서 사용자가 편 상자가
접힌다. 하나는 **그리지 않은 회차**다 — 닫힌 탭의 본문을 건너뛰는 화면(산출 결과 확보율 탭의
히트맵)은 다른 탭에 갔다 오면 상자가 새로 만들어진다. 다른 하나는 **라벨이 바뀐 회차**다 —
라벨이 요소 id 에 들어가므로 VOC 글의 「답변 N」처럼 라벨이 바뀌면 상자가 새로 만들어진다.

사이드바 상자(`sidebar_status.sidebar_expander`)와 같은 규칙을 본문에 쓴다. `key` 와 상태를
추적하는 `on_change` 를 함께 줘 서버가 `st.session_state[key]` 로 펼침을 읽게 하고, 위젯이 아닌
기억 칸에 `(펼침, 라벨)` 을 적어 두었다가 **값이 사라졌거나 라벨이 바뀐 회차에만** 되돌린다.
매 회차 덮어쓰면 방금 누른 클릭을 지운다. 여닫기 콜백은 사이드바와 같은 `on_box_toggle` 이라
여닫을 때 본문을 다시 돌리지 않는다. `expanded=` 는 주지 않는다 — 세션 값과 함께 주면 Streamlit 이
경고를 남긴다.
"""

from __future__ import annotations

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from capa_simulation.sidebar_status import on_box_toggle, remembered_box_key


def remembered_expander(
    label: str,
    *,
    key: str,
    icon: str | None = None,
    default: bool = False,
) -> DeltaGenerator:
    """지금 컨테이너에 펼침 상태를 세션 동안 기억하는 확장 패널을 연다."""
    memory = remembered_box_key(key)
    remembered = st.session_state.get(memory)
    expanded, remembered_label = (
        (bool(remembered[0]), str(remembered[1]))
        if isinstance(remembered, tuple) and len(remembered) == 2
        else (default, label)
    )
    if key not in st.session_state or remembered_label != label:
        st.session_state[key] = expanded
    box = st.expander(label, key=key, icon=icon, on_change=on_box_toggle, args=(key, label))
    st.session_state[memory] = (bool(st.session_state[key]), label)
    return box
