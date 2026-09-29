# Purpose: 편집표(data_editor)의 편집 여부 판정과, 브라우저까지 확실히 버리는 초기화를 한 곳에 둔다.

"""편집표 상태의 두 가지 — 「고친 것이 남았는가」와 「고친 것을 정말로 버린다」.

**세션 칸을 지우는 것만으로는 편집이 버려지지 않는다**(2026-09-29 리뷰에서 브라우저로 재현).
키가 있는 `num_rows="fixed"` 편집표의 정체는 키와 컬럼 구성이고 데이터가 아니다. 서버에서
`st.session_state.pop(키)` 을 해도 브라우저는 제 편집 상태를 그대로 들고 있다가 다음 rerun 에
**다시 보낸다** — 「편집 취소」를 눌렀는데 다음 클릭에 편집이 되살아나 나중 적용에 섞였다.

그래서 버릴 때는 편집표의 **위젯 키를 바꾼다.** 편집표마다 세대 번호를 세션에 두고 위젯 키에
붙인다(`editor_widget_key`). 세대가 오르면 새 위젯이라 브라우저가 옛 편집을 보낼 곳이 없다.
세대 0 은 원래 키 그대로라 기존 키·테스트와 맞는다.

편집표를 그리는 쪽은 `key=editor_widget_key(키)` 로 그리고, 편집을 버리는 쪽은
`discard_editor(키)` 를 부른다. 세션을 직접 `pop` 하지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping

import streamlit as st

# `st.data_editor` 가 세션에 남기는 편집 상태의 세 칸. 하나라도 차 있으면 고친 것이 있다.
_EDIT_PARTS = ("edited_rows", "added_rows", "deleted_rows")


def _generation_key(key: str) -> str:
    return f"{key}__generation"


def editor_widget_key(key: str) -> str:
    """편집표를 그릴 때 쓰는 위젯 키. 버릴 때마다 바뀐다."""
    generation = st.session_state.get(_generation_key(key), 0)
    return key if not generation else f"{key}__g{generation}"


def discard_editor(key: str) -> None:
    """이 편집표의 적용하지 않은 편집을 브라우저까지 버린다. 다음 회차에 새 위젯으로 선다."""
    st.session_state.pop(editor_widget_key(key), None)
    st.session_state[_generation_key(key)] = int(st.session_state.get(_generation_key(key), 0)) + 1


def editor_has_edits(key: str) -> bool:
    """이 편집표에 적용하지 않은 편집이 남았는가.

    편집표의 상태는 위젯 값이라 **그리기 전에도** 세션에서 읽힌다 — 페이지가 탭을 만든 직후,
    표를 그리기 전에 판정할 수 있다. 한 번도 그리지 않은 편집표는 칸이 없어 `False` 다.
    """
    state = st.session_state.get(editor_widget_key(key))
    if not isinstance(state, Mapping):
        return False
    return any(bool(state.get(part)) for part in _EDIT_PARTS)
