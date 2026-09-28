# Purpose: 편집 페이지가 보는 원본을 토큰으로 식별하고, 원본이 바뀌면 편집기 상태를 비운다.

"""편집 화면(생산 계획·기준 정보)이 함께 쓰는 원본 식별과 편집기 초기화.

예전에는 본문 맨 위에 「활성 시나리오 · 수정본 N」 줄과 원본 초기화 버튼도 그렸다. 그 줄은
사이드바 시나리오 상자의 미저장 배지와 같은 말을 했고, 초기화는 모든 화면의 편집을 버리는
시나리오 단위 동작이라 사이드바 「편집 되돌리기」로 옮겼다(2026-09-29 사용자 결정).
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from capa_simulation.scenario_state import ActiveScenario


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
