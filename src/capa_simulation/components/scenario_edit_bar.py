# Purpose: 편집 페이지 상단의 활성 시나리오 상태와 원본 초기화 버튼을 한 모양으로 그린다.

"""Shared "활성 시나리오 · 수정본 N" bar with the reset control.

부하량과 공정별 Capa 가 같은 줄을 각자 복제하고 있었다. 편집 중인 표가 원본에서
얼마나 떨어져 있는지 알리고 되돌릴 수 있게 하는 자리이므로 두 화면이 같아야 한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import streamlit as st

from capa_simulation.scenario_state import ActiveScenario, reset_active_scenario


def render_scenario_edit_bar(
    active_scenario: ActiveScenario,
    reference_tables: dict[str, pd.DataFrame],
    reference_version: int,
    *,
    reset_key: str,
    clear_session_keys: Sequence[str] = (),
) -> None:
    """편집본 상태 한 줄과 원본 초기화 버튼을 그린다.

    `clear_session_keys` 는 초기화할 때 함께 비울 세션 키다. 페이지마다 붙잡고 있는
    임시 상태(편집기 위젯, 붙여넣기 대기분)가 달라서 인자로 받는다.
    """
    revision = active_scenario["revision"]
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"활성 시나리오 · 수정본 {revision}")
        if st.button(":material/restart_alt: 전체 입력 원본으로 초기화", key=reset_key):
            reset_active_scenario(reference_tables, reference_version)
            for key in clear_session_keys:
                st.session_state.pop(key, None)
            st.rerun()
