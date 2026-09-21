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


def source_token(
    reference_version: int,
    active_scenario: ActiveScenario,
    start_month: int,
    end_month: int,
) -> str:
    """편집기가 지금 보고 있는 원본을 한 문자열로 식별한다.

    기준정보 버전·활성 리비전·조회기간 중 하나라도 달라지면 표의 행과 월 구성이 달라진다.
    페이지마다 같은 f-string 을 다시 적으면 한쪽만 구성 요소가 늘어 편집기가 안 갈린다.
    """
    return f"duckdb:{reference_version}:{active_scenario['revision']}:{start_month}:{end_month}"


def reset_editors_on_source_change(token_key: str, token: str, editor_keys: Sequence[str]) -> bool:
    """원본이 바뀌었으면 편집기·임시 상태를 비우고 새 토큰을 기록한다. 바뀌었으면 True.

    `token_key` 는 페이지가 소유한다 — 두 편집 화면이 한 칸을 나눠 쓰면 한쪽을 열었다는
    이유로 다른 쪽 편집기가 안 갈린다.
    """
    if st.session_state.get(token_key) == token:
        return False
    for key in editor_keys:
        st.session_state.pop(key, None)
    st.session_state[token_key] = token
    return True


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
        if st.button(
            "전체 입력 원본으로 초기화",
            icon=":material/restart_alt:",
            key=reset_key,
        ):
            reset_active_scenario(reference_tables, reference_version)
            for key in clear_session_keys:
                st.session_state.pop(key, None)
            st.rerun()
