# Purpose: 편집 페이지가 보는 원본을 토큰으로 식별하고, 원본이 바뀌면 편집기 상태를 비운다.

"""편집 화면(생산 계획·기준 정보)이 함께 쓰는 원본 식별과 편집기 초기화.

예전에는 본문 맨 위에 「활성 시나리오 · 수정본 N」 줄과 원본 초기화 버튼도 그렸다. 그 줄은
사이드바 시나리오 상자의 미저장 배지와 같은 말을 했고, 초기화는 모든 화면의 편집을 버리는
시나리오 단위 동작이라 사이드바 「편집 되돌리기」로 옮겼다(2026-09-29 사용자 결정).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import streamlit as st

from capa_simulation.components.editor_state import discard_editor, editor_has_edits
from capa_simulation.scenario_state import ActiveScenario

# 화면마다 「적용하지 않은 편집이 남을 수 있는 곳」의 목록. 사이드바가 저장·불러오기 전에 읽는다.
_PENDING_REGISTRY_KEY = "scenario_pending_edit_registry"


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


def register_pending_edits(
    page: str,
    title: str,
    editors: Mapping[str, str],
    staged: Mapping[str, str] | None = None,
    *,
    own_change_key: str | None = None,
) -> None:
    """이 화면의 편집표(`editors`: 키 → 이름)와 붙여넣기 대기(`staged`: 키 → 이름)를 적어 둔다.

    **적용하지 않은 편집은 시나리오에 들어 있지 않다.** 그래서 사이드바 「신규 리비전 저장」은 그
    편집을 저장하지 못하고, 저장·불러오기가 원본을 바꾸는 순간 편집표와 함께 사라진다(2026-09-29
    2차 리뷰에서 브라우저로 재현). 사이드바는 페이지보다 먼저 그려지므로 **앞 회차에 적어 둔**
    목록을 읽는다 — `pending_edit_labels`.

    `page` 는 그 화면의 파일 이름이다(`app_pages/<page>`). 편집표의 편집은 위젯 상태라 다른
    화면으로 옮기면 버려지므로 지금 화면의 것만 센다. 붙여넣기 대기는 위젯이 아닌 세션 칸이라
    화면을 옮겨도 남으므로 어느 화면에서나 센다.

    `own_change_key` 는 그 화면이 `mark_own_change` 에 넘기는 칸이다. 사이드바가 방금 적용한 표를
    빼고 세는 데 쓴다(`pending_edit_labels`).
    """
    registry = dict(st.session_state.get(_PENDING_REGISTRY_KEY) or {})
    registry[page] = (title, dict(editors), dict(staged or {}), own_change_key)
    st.session_state[_PENDING_REGISTRY_KEY] = registry


def pending_edit_labels(current_page: str | None) -> list[str]:
    """적용하지 않은 편집이 남은 곳 — 「기준 정보 · UPEH」. 없으면 빈 목록이다.

    **방금 적용한 표는 세지 않는다.** 적용한 회차는 `st.rerun()` 으로 끝나고, 다음 회차에는 이
    함수(사이드바)가 페이지보다 먼저 돈다. 그 편집표를 버리는 일(`reset_editors_on_source_change`)
    은 페이지 본문에서 뒤에 도므로, 그 사이에는 적용한 편집이 아직 위젯 상태에 남아 있다. 그것을
    세면 사이드바와 저장 팝업이 방금 적용한 표를 「적용 전 편집」으로 띄우고, 버릴 것도 없는 확인
    체크를 요구하며 「신규 리비전 저장」을 잠갔다(2026-10-01 브라우저 E2E 에서 재현). 페이지가
    `mark_own_change` 로 적어 둔 표·붙여넣기 대기는 그 적용이 버릴 것이므로 뺀다.
    """
    registry = st.session_state.get(_PENDING_REGISTRY_KEY)
    if not isinstance(registry, dict):
        return []
    labels: list[str] = []
    for page, (title, editors, staged, own_change_key) in registry.items():
        just_applied = st.session_state.get(own_change_key) if own_change_key else None
        skipped = set(just_applied) if isinstance(just_applied, list) else set()
        if page == current_page:
            labels += [
                f"{title} · {name}"
                for key, name in editors.items()
                if key not in skipped and editor_has_edits(key)
            ]
        labels += [
            f"{title} · {name}"
            for key, name in staged.items()
            if key not in skipped and st.session_state.get(key) is not None
        ]
    return labels


def mark_own_change(own_change_key: str, keys: Sequence[str]) -> None:
    """이 화면이 방금 **스스로** 적용한 편집을 적어 둔다. 적용한 뒤 `st.rerun()` 직전에 부른다.

    적용은 활성 리비전을 올려 원본 토큰을 바꾼다. 그대로 두면 다음 회차에 **모든** 편집표가
    비워져, 다른 탭에서 고치고 아직 적용하지 않은 편집까지 조용히 사라진다(2026-09-29 리뷰에서
    재현). 여기 적은 편집표·상태만 버리고 나머지는 그대로 두게 한다. `keys` 는 이 적용으로 행
    구성이 바뀐 편집표와 함께 비울 상태다. 페이지보다 먼저 도는 사이드바도 이 목록을 읽어, 버리기
    전인 그 표를 「적용 전 편집」으로 세지 않는다(`pending_edit_labels`).
    """
    st.session_state[own_change_key] = list(keys)


def reset_editors_on_source_change(
    token_key: str,
    token: str,
    editor_keys: Sequence[str],
    *,
    other_keys: Sequence[str] = (),
    own_change_key: str | None = None,
) -> bool:
    """원본이 바뀌었으면 편집기·임시 상태를 비우고 새 토큰을 기록한다. 바뀌었으면 True.

    편집표(`editor_keys`)는 `discard_editor` 로 **브라우저까지** 버린다 — 세션 칸만 지우면
    브라우저가 옛 편집을 다시 보낸다. 편집표가 아닌 상태(`other_keys` — 붙여넣기 대기, 선택
    위젯)는 칸만 지운다.

    바뀐 원본이 이 화면 자신의 적용이면(`mark_own_change`) 적어 둔 것만 비운다.

    `token_key` 는 페이지가 소유한다 — 두 편집 화면이 한 칸을 나눠 쓰면 한쪽을 열었다는
    이유로 다른 쪽 편집기가 안 갈린다.
    """
    own = st.session_state.pop(own_change_key, None) if own_change_key else None
    if isinstance(own, list):
        for key in own:
            if key in editor_keys:
                discard_editor(key)
            else:
                st.session_state.pop(key, None)
        st.session_state[token_key] = token
        return True
    if st.session_state.get(token_key) == token:
        return False
    for key in editor_keys:
        discard_editor(key)
    for key in other_keys:
        st.session_state.pop(key, None)
    st.session_state[token_key] = token
    return True
