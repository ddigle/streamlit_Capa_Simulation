# Purpose: 저장 구획의 「모두 버리기」 확인 팝오버를 화면끼리 같은 꼴로 그린다.

"""되돌릴 수 없는 「모두 버리기」 — 누르면 그 뜻을 적은 한 줄과 확인 단추가 뜬다(설계 규칙
UI-NTF-09 · UI-CON-04). 설비 마스터 저장 구획과 시나리오 목록 「저장 전 변경」 칸이 함께 쓴다."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import streamlit as st


def discard_popover(
    *,
    label: str,
    popover_key: str,
    confirm_key: str,
    note: str,
    on_confirm: Callable[..., None],
    args: Sequence[object] = (),
) -> None:
    """「모두 버리기」 팝오버 — 뜻 한 줄(`note`) · 확인 단추. 확인 콜백은 `on_confirm(*args)` 다."""
    with st.popover(label, icon=":material/delete_sweep:", key=popover_key):
        st.caption(note)
        st.button(
            f"{label} 확인",
            key=confirm_key,
            type="primary",
            icon=":material/delete_forever:",
            on_click=on_confirm,
            args=tuple(args),
        )
