# Purpose: rerun 을 건너 살아남는 성공 문구를 세션에 담았다가 다음 실행에서 그린다.

"""저장했다는 말이 화면에 남게 한다.

`st.success(...)` 바로 뒤에 `st.rerun()` 을 부르면 **그 문구는 한 번도 그려지지 않는다.**
`rerun` 이 그 자리에서 실행을 끊고 화면을 처음부터 다시 그리기 때문이다. 사용자에게는
화면이 한 번 깜빡이고 제자리로 돌아온 것으로 보여서, 저장이 됐는지 알 수 없어 다시 누른다.

그래서 문구를 세션에 담아 두고 **다음 실행에서** 꺼내 그린다. 이 저장소가 이미 세 곳에서
같은 일을 하고 있다(`scenario_status.SIDEBAR_FLASH_KEY`,
`scenario_management.FLASH_KEY`, `reference_csv_tools.queue_reference_import_flash`).
네 번째 복제 대신 여기로 올린다.

**그리는 자리는 버튼과 같은 상자 안이다.** 실패는 이미 그 자리에 뜬다 — 각 편집기의
`st.error(bootstrap_error_message(exc))` 가 버튼 바로 옆이다. 성공만 화면 맨 위에 뜨면
어느 동작의 결과인지 사용자가 되짚어야 한다. 성공과 실패는 같은 자리에서 답해야 한다.

기존 세 곳은 각자 자기 화면의 사정(제목 줄 위, 페이지 머리말 아래)이 있어 이 변경에서
회수하지 않는다. 옮길 이유가 생기면 그때 한 번에 한다.
"""

from __future__ import annotations

import streamlit as st


def queue_flash(key: str, message: str) -> None:
    """저장 직후에 부른다. 곧바로 `st.rerun()` 을 불러도 문구가 살아남는다."""
    st.session_state[key] = message


def render_flash(key: str) -> bool:
    """담아 둔 문구가 있으면 그리고 비운다. 그렸으면 True.

    **한 번만 그린다.** 비우지 않으면 그 뒤 모든 rerun 에 같은 문구가 남아, 사용자가
    방금 저장한 것인지 아까 저장한 것인지 알 수 없게 된다.
    """
    message = st.session_state.pop(key, None)
    if not isinstance(message, str) or not message:
        return False
    st.success(message)
    return True
